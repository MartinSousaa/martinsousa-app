import streamlit as st
import anthropic
import triagem
import palavras_chave
from params_oficiais import ML_COMISSAO_POR_CATEGORIA

LIMITE_CARACTERES = 60  # limite do Mercado Livre -- o mais apertado entre as plataformas,
                         # usado como regra unica pra garantir que o titulo sirva em todas

# Inclui todos os campos relevantes da triagem (inclusive uso e termos)
CAMPOS_TRIAGEM = ["nome_comercial", "categoria", "material", "variacao_cores",
                   "diferenciais", "uso", "termos_busca", "termos_evitar"]


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
Uso/ocasião: {dados.get('uso','')}

PALAVRAS-CHAVE DISPONÍVEIS (use as mais relevantes, não precisa usar todas):
{chr(10).join('- ' + p for p in palavras_lista)}

Responda SOMENTE com os 2 títulos, um por linha, sem numeração, sem aspas, sem explicação.
"""
    client = anthropic.Anthropic(api_key=api_key)
    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        texto = msg.content[0].text.strip()
        linhas = [l.strip("-•* \t\"") for l in texto.split("\n") if l.strip()]
        return linhas[:2], None
    except Exception as e:
        return [], str(e)


def ajustar_titulos(titulos_atuais, instrucao, dados, palavras_lista):
    """Recebe os títulos atuais e uma instrução. Retorna 2 títulos ajustados."""
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    titulos_str = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titulos_atuais))
    prompt = f"""Você gerou os seguintes títulos para o produto "{dados.get('nome_comercial','')}":

{titulos_str}

O colaborador pediu o seguinte ajuste:
"{instrucao}"

Regras que continuam valendo:
- Máximo {LIMITE_CARACTERES} caracteres cada (conte os espaços)
- Os 2 títulos devem ser diferentes entre si
- Sem "novo", "frete grátis", "promoção" ou termos de venda
{"- NÃO inclua a cor (produto com variação de cor)" if "," in (dados.get("variacao_cores") or "") else ""}

Retorne SOMENTE os 2 títulos ajustados, um por linha, sem numeração, sem aspas, sem explicação.
"""
    client = anthropic.Anthropic(api_key=api_key)
    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        texto = msg.content[0].text.strip()
        linhas = [l.strip("-•* \t\"") for l in texto.split("\n") if l.strip()]
        return linhas[:2], None
    except Exception as e:
        return titulos_atuais, str(e)


def _exibir_titulos(titulos):
    """Renderiza os títulos com contador de caracteres colorido."""
    for i, t in enumerate(titulos, start=1):
        n_chars = len(t)
        cor = "#4ade80" if n_chars <= LIMITE_CARACTERES else "#f87171"
        st.markdown(f"**Opção {i}:** {t}")
        st.markdown(
            f"<span style='color:{cor}; font-size:13px;'>{n_chars}/{LIMITE_CARACTERES} caracteres</span>",
            unsafe_allow_html=True,
        )
        st.markdown("")


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

        uso = st.text_input("Uso / ocasião", value=dados_iniciais.get("uso", ""))
        diferenciais = st.text_area("Diferenciais", value=dados_iniciais.get("diferenciais", ""))

        gerar = st.form_submit_button("Gerar Título", type="primary", use_container_width=True)

    if gerar:
        if not nome_comercial:
            st.warning("Preencha pelo menos o Nome comercial.")
            return

        dados = {
            "nome_comercial": nome_comercial, "categoria": categoria, "material": material,
            "variacao_cores": variacao_cores, "diferenciais": diferenciais,
            "uso": uso,
        }

        with st.spinner("Gerando palavras-chave de apoio..."):
            palavras_lista, erro_pc = palavras_chave.gerar_palavras_chave(dados)

        if erro_pc:
            st.error(f"Erro ao gerar palavras-chave: {erro_pc}")
            return

        with st.spinner("Montando títulos..."):
            titulos, erro_tit = gerar_titulos(dados, palavras_lista)

        if erro_tit:
            st.error(f"Erro ao gerar títulos: {erro_tit}")
            return

        import atividades
        atividades.registrar_atividade(usuario_logado, "Título", nome_comercial, f"{len(titulos)} títulos gerados")

        # Persiste no session_state para não perder ao trocar de aba
        st.session_state["tt_titulos_gerados"] = titulos
        st.session_state["tt_palavras_usadas"] = palavras_lista
        st.session_state["tt_dados_produto"] = dados
        st.session_state["tt_chat_log"] = []
        st.rerun()

    # ── RESULTADO E CHAT ──────────────────────────────────────────────────────
    titulos_salvos = st.session_state.get("tt_titulos_gerados")
    if not titulos_salvos:
        return

    palavras_salvas = st.session_state.get("tt_palavras_usadas", [])
    dados_produto = st.session_state.get("tt_dados_produto", {})
    nome_exibir = dados_produto.get("nome_comercial", "produto")

    st.markdown("---")
    st.markdown(f"#### Títulos — {nome_exibir}")
    _exibir_titulos(titulos_salvos)

    with st.expander("Ver palavras-chave usadas como base"):
        st.write(palavras_salvas)

    st.caption("💬 Para ajustar os títulos, use o **Assistente IA** no menu lateral.")
