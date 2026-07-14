import streamlit as st
import anthropic
from params_oficiais import ML_COMISSAO_POR_CATEGORIA


EXEMPLO_1 = """A Bengala 3 Pontas com Apoio foi desenvolvida para auxiliar pessoas com mobilidade reduzida, proporcionando apoio e estabilidade para prevenir quedas durante a caminhada.

O recurso é resistente, leve e possui apoio de mão com cantos arredondados e design ergonômico, que contribui para melhor distribuição da pressão palmar e proporciona conforto durante o uso.

O dispositivo conta com 10 níveis de ajuste de altura.

A bengala contém base de apoio ampliada, com 3 ponteiras que oferecem melhor aderência ao solo, gerando estabilidade e segurança ao caminhar.

Tamanho único ajustável.
Produto compatível com usuários que tenham altura de 1,50m a 2mt

Composição:
- Parte metálica: Alumínio
- Apoio de mão: Polipropileno
- Ponteira: Borracha

MEDIDAS DO PRODUTO;
Altura mínima: 64 cm
Altura máxima: 101,50 cm

Contém; 1 peça"""

EXEMPLO_2 = """Benefícios da viseira: Ao contrário de um boné, a viseira apresenta materiais mais leves e que permitem transpiração adequada, sem deixar de lado a proteção. Os raios ultravioletas podem causar grande desconforto quando em contato direto com os olhos, além dos danos à visão.

DIMENSÕES:
- Modelo: Adulto
- Aba: 7cm X 18cm
- Ajuste de tamanho traseiro em velcro

- Onde usar minha viseira?
Em corridas ou atividades mais longas a viseira tende a ser a melhor opção porque protege o rosto como o boné, porém, ao contrário dele, a viseira deixa os fios de cabelo da parte superior da cabeça livres para transpirarem. Com isso, a sensação de calor diminui.

- Como conservar minha viseira
- Use sabão neutro
- Produtos de limpeza com aromatizantes e corantes costumam ser agressivos com tecidos mais leves. Por isso, o sabão neutro é o mais indicado
- Amaciantes e alvejantes são dispensáveis
- Deixe secando na sombra"""


def gerar_descricao(dados):
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "")

    prompt = f"""Crie a descrição de anúncio para o produto abaixo, seguindo EXATAMENTE o padrão de
estilo e estrutura da empresa, mostrado nos 2 exemplos reais abaixo (mesma voz, mesmo jeito de
organizar em blocos com cabeçalho, mesmo tom direto e técnico).

=== EXEMPLO REAL 1 (produto: bengala) ===
{EXEMPLO_1}

=== EXEMPLO REAL 2 (produto: viseira) ===
{EXEMPLO_2}

=== PADRÃO A SEGUIR ===
- Abre com 1-2 frases ligando produto + benefício/uso principal (sem repetir o título literalmente)
- Parágrafos curtos descrevendo características e o que elas proporcionam na prática
- Usa cabeçalho em blocos quando fizer sentido pro produto, no estilo dos exemplos (ex: "DIMENSÕES:",
  "MEDIDAS DO PRODUTO;", "Composição:", "Contém;") -- só inclua os blocos que fizerem sentido pra
  esse produto especificamente, não force bloco que não se aplica
- Se o produto se beneficiar de explicar "onde usar" ou "como conservar/cuidar", pode usar o formato
  de pergunta como nos exemplos ("- Onde usar...", "- Como conservar...") -- só se fizer sentido,
  não é obrigatório em todo produto
- Frases objetivas, sem enrolação, tom técnico mas acessível

PRODUTO: {dados.get('nome_produto','')}
Categoria: {dados.get('categoria','')}
Medidas: {dados.get('medidas','')}
Peso: {dados.get('peso','')}
Material: {dados.get('material','')}
Cor: {dados.get('cor','')}
Diferenciais: {dados.get('diferenciais','')}
Uso/ocasião: {dados.get('uso','')}
Características adicionais: {dados.get('caracteristicas','')}
Palavras-chave pra usar com naturalidade (sem forçar todas): {dados.get('palavras_chave','') or 'nenhuma informada'}

REGRAS OBRIGATÓRIAS (política oficial do Mercado Livre):
- NÃO inclua links externos, nome de loja, telefone, e-mail ou qualquer contato fora da plataforma
- NÃO inclua informações de entrega/frete (isso é campo separado do anúncio)
- NÃO inclua condição do produto (novo/usado) -- isso já é campo separado
- NÃO use texto em caixa alta pra frases inteiras, nem promoção/desconto/frete grátis
- NÃO force todas as palavras-chave no texto -- use as que fizerem sentido natural

Responda SOMENTE com o texto da descrição, pronta pra colar no anúncio, sem comentário extra.
"""
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text.strip()


def pagina_descricao(usuario_logado):
    st.subheader("Descrição")
    st.caption("Busca a Triagem do produto automaticamente (editável). Antes de gerar, você confere um resumo dos dados que serão usados.")

    import triagem

    busca = st.text_input("Nome do produto", key="desc_busca_nome")

    dados_iniciais = {"nome_produto": "", "categoria": "", "medidas": "", "peso": "",
                       "material": "", "cor": "", "uso": "", "caracteristicas": "",
                       "diferenciais": ""}
    aviso = None

    if busca:
        encontrados = triagem.buscar_triagens_por_trecho(busca)
        if len(encontrados) == 1:
            t = encontrados[0]
            dados_iniciais.update({
                "nome_produto": t.get("nome_comercial", ""), "categoria": t.get("categoria", ""),
                "medidas": t.get("medidas", ""), "peso": t.get("peso", ""),
                "material": t.get("material", ""), "cor": t.get("variacao_cores", ""),
                "uso": t.get("uso", ""), "caracteristicas": t.get("caracteristicas", ""),
                "diferenciais": t.get("diferenciais", ""),
            })
            aviso = ("info", f"Triagem encontrada: **{t['nome_comercial']}**. Confira os dados abaixo -- pode editar antes de gerar.")
        elif len(encontrados) > 1:
            nomes = [e["nome_comercial"] for e in encontrados]
            escolha = st.selectbox("Mais de um produto encontrado com esse nome -- qual é?", nomes, key="desc_escolha")
            t = next(e for e in encontrados if e["nome_comercial"] == escolha)
            dados_iniciais.update({
                "nome_produto": t.get("nome_comercial", ""), "categoria": t.get("categoria", ""),
                "medidas": t.get("medidas", ""), "peso": t.get("peso", ""),
                "material": t.get("material", ""), "cor": t.get("variacao_cores", ""),
                "uso": t.get("uso", ""), "caracteristicas": t.get("caracteristicas", ""),
                "diferenciais": t.get("diferenciais", ""),
            })
            aviso = ("info", "Confira os dados abaixo -- pode editar antes de gerar.")
        else:
            dados_iniciais["nome_produto"] = busca
            aviso = ("warning", "Nenhuma triagem encontrada pra esse produto ainda -- preencha os campos abaixo.")

    if aviso:
        getattr(st, aviso[0])(aviso[1])

    with st.form("form_descricao"):
        col1, col2 = st.columns(2)
        nome_produto = col1.text_input("Nome do produto", value=dados_iniciais["nome_produto"], key="desc_nome_produto")
        categorias = sorted(ML_COMISSAO_POR_CATEGORIA.keys())
        cat_atual = dados_iniciais["categoria"]
        idx_cat = categorias.index(cat_atual) if cat_atual in categorias else 0
        categoria = col2.selectbox("Categoria no ML", categorias, index=idx_cat, key="desc_categoria")

        col1, col2 = st.columns(2)
        medidas = col1.text_input("Medidas (AxLxP, cm)", value=dados_iniciais["medidas"], placeholder="ex: 33x33x6")
        peso = col2.text_input("Peso", value=dados_iniciais["peso"], placeholder="ex: 700g")

        col1, col2 = st.columns(2)
        material = col1.text_input("Material", value=dados_iniciais["material"])
        cor = col2.text_input("Cor / variação de cores", value=dados_iniciais["cor"])

        uso = st.text_input("Uso / ocasião", value=dados_iniciais["uso"], key="desc_uso")
        caracteristicas = st.text_area("Características adicionais", value=dados_iniciais["caracteristicas"])
        diferenciais = st.text_area("Diferenciais", value=dados_iniciais["diferenciais"], key="desc_diferenciais")
        palavras_chave_txt = st.text_area("Palavras-chave pra usar com naturalidade (opcional -- cola aqui as que já geramos, se quiser)")

        confirmar = st.form_submit_button("Conferir dados e gerar", type="primary", use_container_width=True)

    if confirmar:
        if not nome_produto:
            st.warning("Preencha pelo menos o Nome do produto.")
        else:
            st.session_state["desc_dados_pendentes"] = {
                "nome_produto": nome_produto, "categoria": categoria, "medidas": medidas, "peso": peso,
                "material": material, "cor": cor, "uso": uso, "caracteristicas": caracteristicas,
                "diferenciais": diferenciais, "palavras_chave": palavras_chave_txt,
            }

    if "desc_dados_pendentes" in st.session_state:
        dados = st.session_state["desc_dados_pendentes"]

        st.markdown("---")
        st.markdown("##### Confirme os dados antes de gerar")
        st.markdown(
            f"- **Produto:** {dados['nome_produto']}\n"
            f"- **Categoria:** {dados['categoria']}\n"
            f"- **Medidas:** {dados['medidas'] or '_(vazio)_'}\n"
            f"- **Peso:** {dados['peso'] or '_(vazio)_'}\n"
            f"- **Material:** {dados['material'] or '_(vazio)_'}\n"
            f"- **Cor:** {dados['cor'] or '_(vazio)_'}\n"
            f"- **Uso/ocasião:** {dados['uso'] or '_(vazio)_'}\n"
            f"- **Características:** {dados['caracteristicas'] or '_(vazio)_'}\n"
            f"- **Diferenciais:** {dados['diferenciais'] or '_(vazio)_'}"
        )
        st.caption("Se algo estiver errado ou desatualizado, ajusta no formulário acima e clica em 'Conferir dados e gerar' de novo.")

        if st.button("✅ Está tudo certo, gerar descrição", type="primary", use_container_width=True):
            with st.spinner("Gerando descrição..."):
                descricao = gerar_descricao(dados)

            import atividades
            atividades.registrar_atividade(usuario_logado, "Descrição", dados["nome_produto"], f"{len(descricao)} caracteres")

            del st.session_state["desc_dados_pendentes"]

            st.markdown("---")
            st.markdown(f"#### Descrição — {dados['nome_produto']}")
            st.text_area("Pronta pra copiar", value=descricao, height=350, key="desc_resultado")
            st.caption(f"{len(descricao)}/10.000 caracteres (limite do Mercado Livre pra descrição)")
