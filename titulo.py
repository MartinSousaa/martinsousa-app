import streamlit as st
import anthropic
import triagem
import palavras_chave
from params_oficiais import ML_COMISSAO_POR_CATEGORIA

LIMITE_CARACTERES = 60  # limite do Mercado Livre -- o mais apertado entre as plataformas,
                         # usado como regra unica pra garantir que o titulo sirva em todas

CAMPOS_TRIAGEM = ["nome_comercial", "categoria", "material", "variacao_cores", "diferenciais"]


def gerar_titulos(dados, palavras_lista):
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    tem_variacao_cor = "," in (dados.get("variacao_cores") or "")

    prompt = f"""Gere 2 títulos de anúncio para o produto abaixo, pra usar em qualquer marketplace
(Mercado Livre, Shopee, Shein). Regras obrigatórias:

1. Cada título deve ter NO MÁXIMO {LIMITE_CARACTERES} caracteres (limite do Mercado Livre, o mais
   apertado -- conte os caracteres com cuidado, incluindo espaços)
2. Os 2 títulos devem ser BEM DIFERENTES entre si (não pode ser quase a mesma frase reorganizada) --
   varie a ordem, o foco (um pode focar em uso/ocasião, outro em característica física) e as palavras
   escolhidas
3. Use as palavras-chave abaixo como base -- priorize as que fazem mais sentido de busca real,
   coloque o termo mais importante no INÍCIO do título (é o que mais pesa pra indexação)
4. {"NÃO inclua a cor no título -- esse produto tem variação de cor, e o Mercado Livre recomenda não especificar cor quando há variação (fica agrupado no mesmo anúncio)" if tem_variacao_cor else "Pode incluir a cor se ajudar a identificar o produto, já que não há variação"}
5. NÃO inclua: "novo", "usado", "frete grátis", "promoção", desconto, ou qualquer característica de
   venda -- só características do PRODUTO
6. Estrutura recomendada: Produto + característica principal + diferencial/uso

PRODUTO: {dados.get('nome_comercial','')}
Categoria: {dados.get('categoria','')}
Material: {dados.get('material','')}
Diferenciais: {dados.get('diferenciais','')}

PALAVRAS-CHAVE DISPONÍVEIS (use as mais relevantes, não precisa usar todas):
{chr(10).join('- ' + p for p in palavras_lista)}

Responda SOMENTE com os 2 títulos, um por linha, sem numeração, sem aspas, sem explicação.
"""
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )
    texto = msg.content[0].text.strip()
    linhas = [l.strip("-•* \t\"") for l in texto.split("\n") if l.strip()]
    return linhas[:2]


def pagina_titulo(usuario_logado):
    st.subheader("Título")
    st.caption("Busca a Triagem do produto e gera palavras-chave automaticamente, depois monta os títulos em cima delas.")

    busca = st.text_input("Nome do produto", key="tt_busca_nome")

    dados_iniciais = {c: "" for c in CAMPOS_TRIAGEM}
    aviso = None

    if busca:
        encontrados = triagem.buscar_triagens_por_trecho(busca)
        if len(encontrados) == 1:
            dados_iniciais.update(encontrados[0])
            aviso = ("info", f"Triagem encontrada: **{encontrados[0]['nome_comercial']}**. Confira os dados abaixo antes de gerar.")
        elif len(encontrados) > 1:
            nomes = [e["nome_comercial"] for e in encontrados]
            escolha = st.selectbox("Mais de um produto encontrado com esse nome -- qual é?", nomes, key="tt_escolha")
            selecionado = next(e for e in encontrados if e["nome_comercial"] == escolha)
            dados_iniciais.update(selecionado)
            aviso = ("info", "Confira os dados abaixo antes de gerar.")
        else:
            dados_iniciais["nome_comercial"] = busca
            aviso = ("warning", "Nenhuma triagem encontrada pra esse produto ainda -- preencha os campos abaixo.")

    if aviso:
        getattr(st, aviso[0])(aviso[1])

    with st.form("form_titulo"):
        col1, col2 = st.columns(2)
        nome_comercial = col1.text_input("Nome comercial", value=dados_iniciais.get("nome_comercial", ""))
        categorias = sorted(ML_COMISSAO_POR_CATEGORIA.keys())
        cat_atual = dados_iniciais.get("categoria", "")
        idx_cat = categorias.index(cat_atual) if cat_atual in categorias else 0
        categoria = col2.selectbox("Categoria no ML", categorias, index=idx_cat, key="tt_categoria")

        col1, col2 = st.columns(2)
        material = col1.text_input("Material", value=dados_iniciais.get("material", ""))
        variacao_cores = col2.text_input("Variação de cores", value=dados_iniciais.get("variacao_cores", ""))

        diferenciais = st.text_area("Diferenciais", value=dados_iniciais.get("diferenciais", ""))

        gerar = st.form_submit_button("Gerar Título", type="primary", use_container_width=True)

    if gerar:
        if not nome_comercial:
            st.warning("Preencha pelo menos o Nome comercial.")
            return

        dados = {
            "nome_comercial": nome_comercial, "categoria": categoria, "material": material,
            "variacao_cores": variacao_cores, "diferenciais": diferenciais,
        }

        with st.spinner("Gerando palavras-chave de apoio..."):
            palavras_lista = palavras_chave.gerar_palavras_chave(dados)

        with st.spinner("Montando títulos..."):
            titulos = gerar_titulos(dados, palavras_lista)

        import atividades
        atividades.registrar_atividade(usuario_logado, "Título", nome_comercial, f"{len(titulos)} títulos gerados")

        st.markdown("---")
        st.markdown(f"#### Títulos — {nome_comercial}")
        for i, t in enumerate(titulos, start=1):
            n_chars = len(t)
            cor = "#4ade80" if n_chars <= LIMITE_CARACTERES else "#f87171"
            st.markdown(f"**Opção {i}:** {t}")
            st.markdown(f"<span style='color:{cor}; font-size:13px;'>{n_chars}/{LIMITE_CARACTERES} caracteres</span>", unsafe_allow_html=True)
            st.markdown("")

        with st.expander("Ver palavras-chave usadas como base"):
            st.write(palavras_lista)
