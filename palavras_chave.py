import streamlit as st
import anthropic
import requests
import triagem
from params_oficiais import ML_COMISSAO_POR_CATEGORIA

CAMPOS_TRIAGEM = ["nome_comercial", "categoria", "material", "variacao_cores",
                   "diferenciais", "uso", "termos_busca", "termos_evitar"]


def obter_token_ml():
    """Sempre gera um token novo via client_credentials -- o ML_ACCESS_TOKEN
    fixo (se ainda estiver nas Secrets de uma configuracao antiga) expira em
    poucas horas e nao deve ser usado aqui."""
    client_id = st.secrets.get("ML_CLIENT_ID", "")
    client_secret = st.secrets.get("ML_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return None
    try:
        resp = requests.post(
            "https://api.mercadolibre.com/oauth/token",
            data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        return resp.json().get("access_token")
    except Exception:
        return None


def buscar_tendencias_ml():
    """Consulta a API OFICIAL de Tendencias do Mercado Livre (termos em alta
    no site agora). Nao e volume de busca -- e so uma lista de termos que o
    proprio ML sinaliza como em alta. Retorna (lista_de_termos, erro)."""
    token = obter_token_ml()
    if not token:
        return None, "Credenciais do Mercado Livre não configuradas nas Secrets (ML_CLIENT_ID/ML_CLIENT_SECRET)."
    try:
        r = requests.get(
            "https://api.mercadolibre.com/trends/MLB",
            headers={"Authorization": f"Bearer {token}"}, timeout=10,
        )
        if r.status_code != 200:
            return None, f"API de Tendências indisponível agora (HTTP {r.status_code})."
        dados = r.json()
        termos = [item.get("keyword", "").lower() for item in dados if isinstance(item, dict) and item.get("keyword")]
        return termos, None
    except Exception as e:
        return None, str(e)


def bate_com_tendencia(termo, tendencias):
    termo_l = termo.lower()
    return any(t and (t in termo_l or termo_l in t) for t in tendencias)


def gerar_palavras_chave(dados):
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    prompt = f"""Gere de 10 a 15 palavras-chave de busca para o produto abaixo, pensando em como
CLIENTES REAIS pesquisam no Mercado Livre -- a maioria busca termos amplos e curtos, poucos
buscam especificações exatas. Misture:
- Termos amplos e genéricos (o essencial do produto, o que mais gente busca)
- Termos por uso/ocasião
- Só alguns termos mais específicos (material, medida, cor) quando fizer sentido de busca real --
  não force encaixar toda especificação técnica numa palavra-chave, isso não é como as pessoas buscam

PRODUTO: {dados.get('nome_comercial','')}
Categoria: {dados.get('categoria','')}
Material: {dados.get('material','')}
Variação de cores: {dados.get('variacao_cores','')}
Diferenciais: {dados.get('diferenciais','')}
Uso/ocasião: {dados.get('uso','')}
Termos que o time já sabe que os clientes buscam: {dados.get('termos_busca','') or 'nenhum informado'}
Termos a evitar: {dados.get('termos_evitar','') or 'nenhum'}

Responda SOMENTE com a lista de palavras-chave, uma por linha, sem numeração, sem marcador, sem explicação.
"""
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )
    texto = msg.content[0].text.strip()
    linhas = [l.strip("-•* \t") for l in texto.split("\n") if l.strip()]
    return linhas


def pagina_palavras_chave(usuario_logado):
    st.subheader("Palavras-chave")
    st.caption("Busca a Triagem do produto automaticamente. Se não encontrar, preenche na hora.")

    busca = st.text_input("Nome do produto", key="pc_busca_nome")

    dados_iniciais = {c: "" for c in CAMPOS_TRIAGEM}
    aviso = None

    if busca:
        encontrados = triagem.buscar_triagens_por_trecho(busca)
        if len(encontrados) == 1:
            dados_iniciais.update(encontrados[0])
            aviso = ("info", f"Triagem encontrada: **{encontrados[0]['nome_comercial']}**. Confira os dados abaixo antes de gerar.")
        elif len(encontrados) > 1:
            nomes = [e["nome_comercial"] for e in encontrados]
            escolha = st.selectbox("Mais de um produto encontrado com esse nome -- qual é?", nomes, key="pc_escolha")
            selecionado = next(e for e in encontrados if e["nome_comercial"] == escolha)
            dados_iniciais.update(selecionado)
            aviso = ("info", "Confira os dados abaixo antes de gerar.")
        else:
            dados_iniciais["nome_comercial"] = busca
            aviso = ("warning", "Nenhuma triagem encontrada pra esse produto ainda -- preencha os campos abaixo.")

    if aviso:
        getattr(st, aviso[0])(aviso[1])

    with st.form("form_palavras_chave"):
        col1, col2 = st.columns(2)
        nome_comercial = col1.text_input("Nome comercial", value=dados_iniciais.get("nome_comercial", ""))
        categorias = sorted(ML_COMISSAO_POR_CATEGORIA.keys())
        cat_atual = dados_iniciais.get("categoria", "")
        idx_cat = categorias.index(cat_atual) if cat_atual in categorias else 0
        categoria = col2.selectbox("Categoria no ML", categorias, index=idx_cat, key="pc_categoria")

        col1, col2 = st.columns(2)
        material = col1.text_input("Material", value=dados_iniciais.get("material", ""))
        variacao_cores = col2.text_input("Variação de cores", value=dados_iniciais.get("variacao_cores", ""))

        uso = st.text_input("Uso / ocasião", value=dados_iniciais.get("uso", ""))
        diferenciais = st.text_area("Diferenciais", value=dados_iniciais.get("diferenciais", ""), key="pc_diferenciais")

        col1, col2 = st.columns(2)
        termos_busca = col1.text_input("Termos que já sabe que buscam", value=dados_iniciais.get("termos_busca", ""))
        termos_evitar = col2.text_input("Termos a evitar", value=dados_iniciais.get("termos_evitar", ""))

        gerar = st.form_submit_button("Gerar Palavras-chave", type="primary", use_container_width=True)

    if gerar:
        if not nome_comercial:
            st.warning("Preencha pelo menos o Nome comercial.")
            return

        dados = {
            "nome_comercial": nome_comercial, "categoria": categoria, "material": material,
            "variacao_cores": variacao_cores, "uso": uso, "diferenciais": diferenciais,
            "termos_busca": termos_busca, "termos_evitar": termos_evitar,
        }
        with st.spinner("Gerando palavras-chave..."):
            palavras = gerar_palavras_chave(dados)

        with st.spinner("Conferindo tendências oficiais do Mercado Livre..."):
            tendencias, erro_tendencia = buscar_tendencias_ml()

        import atividades
        atividades.registrar_atividade(usuario_logado, "Palavras-chave", nome_comercial, f"{len(palavras)} termos gerados")

        st.markdown("---")
        st.markdown(f"#### Palavras-chave — {nome_comercial}")

        if erro_tendencia:
            st.caption(f"⚠️ Não consegui comparar com as Tendências oficiais do ML agora ({erro_tendencia}). Lista abaixo é só a sugestão da IA, sem confirmação de tendência.")
            st.code("\n".join(palavras), language=None)
        else:
            st.caption("🔥 = esse termo bate com algo que está de fato em alta agora na API oficial de Tendências do Mercado Livre. Os demais são sugestão da IA, sem dado de volume real.")
            linhas_marcadas = []
            for p in palavras:
                marca = "🔥 " if bate_com_tendencia(p, tendencias) else "   "
                linhas_marcadas.append(f"{marca}{p}")
            st.code("\n".join(linhas_marcadas), language=None)
