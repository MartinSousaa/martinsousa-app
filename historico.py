import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime

PLANILHA_NOME = "MartinSousa - Financeiro"
ABA_NOME = "atividades"
COLUNAS = ["data_hora", "usuario", "tipo", "produto", "resumo"]


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


def registrar_atividade(usuario, tipo, produto, resumo):
    """Grava uma linha no historico. Nunca deixa um erro aqui quebrar a
    tela principal -- se a gravacao falhar, so ignora silenciosamente."""
    try:
        aba = _aba()
        aba.append_row([
            datetime.now().strftime("%d/%m/%Y %H:%M"),
            usuario, tipo, produto, resumo,
        ], value_input_option="RAW")
        carregar_atividades.clear()
    except Exception:
        pass


@st.cache_data(ttl=30)
def carregar_atividades():
    aba = _aba()
    registros = aba.get_all_records(value_render_option="UNFORMATTED_VALUE")
    df = pd.DataFrame(registros)
    if not df.empty:
        df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def pagina_historico():
    st.subheader("Histórico de Atividades")

    try:
        df = carregar_atividades()
    except Exception as e:
        st.error(f"Não consegui carregar o histórico: {e}")
        return

    if df.empty:
        st.info("Nenhuma atividade registrada ainda.")
        return

    usuarios_disponiveis = ["Todos"] + sorted(df["usuario"].dropna().unique().tolist())
    filtro = st.selectbox("Filtrar por usuário", usuarios_disponiveis)
    df_exibir = df if filtro == "Todos" else df[df["usuario"] == filtro]

    # mais recente primeiro
    df_exibir = df_exibir.iloc[::-1]

    st.dataframe(df_exibir, use_container_width=True, hide_index=True)
