import streamlit as st
import hashlib
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

PLANILHA_NOME = "MartinSousa - Financeiro"
ABA_USUARIOS = "usuarios"


# ── HASH ──────────────────────────────────────────────────────────────────────

def _hash(senha):
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


# ── SHEETS ────────────────────────────────────────────────────────────────────

def _cliente_sheets():
    creds_dict = dict(st.secrets["gcp_service_account"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)


def _aba_usuarios():
    """Acessa (ou cria) a aba de usuários na planilha."""
    cliente = _cliente_sheets()
    planilha = cliente.open(PLANILHA_NOME)
    try:
        return planilha.worksheet(ABA_USUARIOS)
    except gspread.exceptions.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA_USUARIOS, rows=500, cols=5)
        aba.append_row(
            ["login", "senha_hash", "ativo", "admin", "criado_em"],
            value_input_option="RAW",
        )
        return aba


@st.cache_data(ttl=60)
def _carregar_usuarios_sheets():
    """Carrega usuários do Sheets. Cache de 60s para não sobrecarregar a API."""
    try:
        aba = _aba_usuarios()
        registros = aba.get_all_records(value_render_option="UNFORMATTED_VALUE")
        df = pd.DataFrame(registros)
        if not df.empty:
            df.columns = [str(c).strip().lower() for c in df.columns]
        return df
    except Exception:
        return pd.DataFrame()


# ── VERIFICAÇÃO DE CREDENCIAL ─────────────────────────────────────────────────

def _verificar_credencial(login, senha):
    """Verifica o login em duas fontes:
    1. Secrets do Streamlit (texto plano, retrocompatível)
    2. Aba 'usuarios' no Google Sheets (senha com hash SHA-256)
    Retorna (autenticado: bool, fonte: str | None)."""

    # 1. Secrets — usuários originais e admin fallback
    usuarios_secrets = dict(st.secrets.get("usuarios", {}))
    if login in usuarios_secrets:
        return usuarios_secrets[login] == senha, "secrets"

    # 2. Sheets
    df = _carregar_usuarios_sheets()
    if df.empty or "login" not in df.columns:
        return False, None

    ativo_vals = {"sim", "true", "1", "yes", "ativo"}
    mask = (
        df["login"].astype(str) == login
    ) & (
        df.get("ativo", pd.Series(["Sim"] * len(df))).astype(str).str.lower().isin(ativo_vals)
    )
    row = df[mask]
    if row.empty:
        return False, None

    senha_correta = str(row.iloc[0].get("senha_hash", "")) == _hash(senha)
    return senha_correta, "sheets"


# ── VERIFICAÇÃO DE ADMIN ───────────────────────────────────────────────────────

def is_admin(usuario_logado):
    """Usuários das Secrets sempre têm acesso admin (são os donos do app).
    Usuários do Sheets precisam ter coluna admin = Sim."""
    if not usuario_logado:
        return False
    if usuario_logado in dict(st.secrets.get("usuarios", {})):
        return True
    df = _carregar_usuarios_sheets()
    if df.empty or "login" not in df.columns:
        return False
    row = df[df["login"].astype(str) == usuario_logado]
    if row.empty:
        return False
    return str(row.iloc[0].get("admin", "")).lower() in ("sim", "true", "1", "yes")


# ── LOGIN ──────────────────────────────────────────────────────────────────────

def verificar_login():
    """Tela de login. Verifica Secrets e Sheets. Bloqueia o app até autenticar.
    Retorna o nome do usuário logado."""
    if "usuario_logado" in st.session_state:
        return st.session_state["usuario_logado"]

    usuarios_secrets = dict(st.secrets.get("usuarios", {}))
    df_sheets = _carregar_usuarios_sheets()
    tem_alguem = bool(usuarios_secrets) or not df_sheets.empty

    st.title("MartinSousa App")
    st.subheader("Login")

    if not tem_alguem:
        st.warning(
            "Nenhum usuário configurado ainda. "
            "Adicione pelo menos um usuário no bloco [usuarios] das Secrets do Streamlit."
        )
        st.stop()

    with st.form("login_form"):
        login = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        entrar = st.form_submit_button("Entrar", type="primary", use_container_width=True)

    if entrar:
        ok, _ = _verificar_credencial(login, senha)
        if ok:
            st.session_state["usuario_logado"] = login
            _carregar_usuarios_sheets.clear()
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos.")

    st.stop()
