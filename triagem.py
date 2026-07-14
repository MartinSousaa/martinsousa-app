import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
from params_oficiais import ML_COMISSAO_POR_CATEGORIA

PLANILHA_NOME = "MartinSousa - Financeiro"
ABA_NOME = "triagens"

COLUNAS = [
    "data_hora", "usuario", "nome_comercial", "categoria", "material", "variacao_cores",
    "medidas", "peso", "caracteristicas", "diferenciais", "uso",
    "termos_busca", "termos_evitar",
]


def _cliente():
    creds_dict = dict(st.secrets["gcp_service_account"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)


def _aba():
    cliente = _cliente()
    planilha = cliente.open(PLANILHA_NOME)
    try:
        return planilha.worksheet(ABA_NOME)
    except gspread.exceptions.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA_NOME, rows=2000, cols=len(COLUNAS))
        aba.append_row(COLUNAS, value_input_option="RAW")
        return aba


def salvar_triagem(usuario, dados):
    """dados: dict com as chaves de COLUNAS (exceto data_hora/usuario, que
    a funcao preenche sozinha). Cada triagem vira uma linha nova -- se o
    mesmo SKU for triado de novo, fica um historico, e buscar_triagem_por_sku
    sempre pega a mais recente."""
    aba = _aba()
    linha = [datetime.now().strftime("%d/%m/%Y %H:%M"), usuario] + [
        dados.get(c, "") for c in COLUNAS if c not in ("data_hora", "usuario")
    ]
    aba.append_row(linha, value_input_option="RAW")
    carregar_triagens.clear()


@st.cache_data(ttl=30)
def carregar_triagens():
    aba = _aba()
    registros = aba.get_all_records(value_render_option="UNFORMATTED_VALUE")
    df = pd.DataFrame(registros)
    if not df.empty:
        df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def buscar_triagens_por_trecho(trecho):
    """Busca por pedaco do nome comercial (case-insensitive). Retorna lista
    de dicts, um por produto unico (pega a triagem mais recente de cada nome,
    caso o mesmo produto tenha sido triado mais de uma vez)."""
    df = carregar_triagens()
    if df.empty or "nome_comercial" not in df.columns:
        return []
    trecho_l = str(trecho).strip().lower()
    if not trecho_l:
        return []
    filtradas = df[df["nome_comercial"].astype(str).str.lower().str.contains(trecho_l, na=False)]
    if filtradas.empty:
        return []
    filtradas = filtradas.sort_values("data_hora")
    unicas = filtradas.drop_duplicates(subset="nome_comercial", keep="last")
    return unicas.to_dict("records")


def buscar_triagem_por_nome(nome_comercial):
    """Retorna a triagem mais recente daquele nome comercial como dict, ou None."""
    df = carregar_triagens()
    if df.empty or "nome_comercial" not in df.columns:
        return None
    linhas = df[df["nome_comercial"].astype(str).str.strip().str.lower() == str(nome_comercial).strip().lower()]
    if linhas.empty:
        return None
    return linhas.iloc[-1].to_dict()


def pagina_triagem(usuario_logado):
    st.subheader("Triagem do Produto")
    st.caption("Preenche uma vez por produto -- essa informação alimenta palavras-chave, título e descrição.")

    with st.form("form_triagem", clear_on_submit=False):
        st.markdown("#### Dados do produto")
        col1, col2 = st.columns(2)
        nome_comercial = col1.text_input("Nome comercial")
        categoria = col2.selectbox("Categoria no ML", sorted(ML_COMISSAO_POR_CATEGORIA.keys()), key="triagem_categoria")

        col1, col2 = st.columns(2)
        material = col1.text_input("Material", placeholder="ex: Plástico e Metal (o predominante primeiro)")
        variacao_cores = col2.text_input("Variação de cores", placeholder="ex: Preto, Vermelho, Azul (só uma se não tiver variação)")

        col1, col2 = st.columns(2)
        medidas = col1.text_input("Medidas (AxLxP, cm)", placeholder="ex: 33x33x6")
        peso = col2.text_input("Peso", placeholder="ex: 700g")

        uso = st.text_input("Uso / ocasião (ex: presente, uso pessoal, infantil)")
        caracteristicas = st.text_area("Características técnicas (specs além de material/cor)")
        diferenciais = st.text_area("Diferenciais (o que separa esse produto de um genérico)")

        st.markdown("#### Opcional")
        termos_busca = st.text_input("Termos que o cliente já costuma buscar (se souber)")
        termos_evitar = st.text_input("Termos a evitar (ex: marca registrada)")

        enviar = st.form_submit_button("Salvar Triagem", type="primary", use_container_width=True)

    if enviar:
        if not nome_comercial:
            st.warning("Preencha pelo menos o Nome comercial.")
            return

        dados = {
            "nome_comercial": nome_comercial, "categoria": categoria,
            "material": material, "variacao_cores": variacao_cores, "medidas": medidas, "peso": peso,
            "caracteristicas": caracteristicas, "diferenciais": diferenciais, "uso": uso,
            "termos_busca": termos_busca, "termos_evitar": termos_evitar,
        }
        with st.spinner("Salvando..."):
            salvar_triagem(usuario_logado, dados)
        import atividades
        atividades.registrar_atividade(usuario_logado, "Triagem de Produto", nome_comercial, categoria)
        st.success(f"Triagem de '{nome_comercial}' salva!")

    st.markdown("---")
    st.markdown("#### Buscar triagem existente")
    nome_busca = st.text_input("Digite o nome comercial pra ver a triagem já salva", key="busca_nome")
    if nome_busca:
        encontrada = buscar_triagem_por_nome(nome_busca)
        if encontrada:
            st.json(encontrada)
        else:
            st.info("Nenhuma triagem encontrada com esse nome ainda.")
