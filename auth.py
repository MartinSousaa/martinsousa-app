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

def _logo_b64():
    """Lê a logo do arquivo logo.png (inclua no repositório ao lado de auth.py)."""
    import os, base64
    path = os.path.join(os.path.dirname(__file__), "logo.png")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return ""


def _bg_b64():
    """Lê o fundo do arquivo bg.jpg (inclua no repositório ao lado de auth.py)."""
    import os, base64
    path = os.path.join(os.path.dirname(__file__), "bg.jpg")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return ""


def verificar_login():
    """Tela de login. Verifica Secrets e Sheets. Bloqueia o app até autenticar.
    Retorna o nome do usuário logado."""
    if "usuario_logado" in st.session_state:
        return st.session_state["usuario_logado"]

    usuarios_secrets = dict(st.secrets.get("usuarios", {}))
    df_sheets = _carregar_usuarios_sheets()
    tem_alguem = bool(usuarios_secrets) or not df_sheets.empty

    # ── CSS DA TELA DE LOGIN ───────────────────────────────────────────────────
    bg_data = _bg_b64()
    bg_css = (
        f"background-image: url('data:image/jpeg;base64,{bg_data}'); "
        "background-size: cover; background-position: center;"
        if bg_data else
        "background-color: #0d0d0d; "
        "background-image: radial-gradient(circle, rgba(255,255,255,0.08) 1px, transparent 1px); "
        "background-size: 22px 22px;"
    )

    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;400;600&display=swap');

    header[data-testid="stHeader"]  {{ display: none !important; }}
    [data-testid="stSidebar"]        {{ display: none !important; }}
    .stDeployButton                  {{ display: none !important; }}
    #MainMenu                        {{ display: none !important; }}
    footer                           {{ display: none !important; }}

    /* Remove todo padding da área principal */
    .main {{ padding: 0 !important; }}
    .main .block-container {{
        padding: 0 !important;
        max-width: 100% !important;
        min-height: 100vh;
    }}

    /* App ocupa tela inteira */
    .stApp {{ min-height: 100vh; }}

    /* Linha de colunas ocupa a altura toda e não tem gap */
    [data-testid="stHorizontalBlock"] {{
        gap: 0 !important;
        min-height: 100vh !important;
        align-items: stretch !important;
        padding: 0 !important;
        margin: 0 !important;
    }}

    /* Cada coluna ocupa altura total */
    [data-testid="stColumn"] {{
        min-height: 100vh !important;
        padding: 0 !important;
    }}

    /* ── PAINEL ESQUERDO: textura do fundo real ── */
    [data-testid="stColumn"]:first-child > div {{
        {bg_css}
        min-height: 100vh !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 60px 40px;
    }}

    /* ── PAINEL DIREITO: preto igual ao fundo da logo ── */
    [data-testid="stColumn"]:last-child > div {{
        background-color: #000000;
        min-height: 100vh !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 60px 52px;
    }}

    /* Conteúdo interno das colunas centralizado */
    [data-testid="stColumn"] > div > div[data-testid="stVerticalBlock"] {{
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        justify-content: center !important;
        flex: 1 !important;
        width: 100% !important;
    }}

    /* ── INPUTS ── */
    .stTextInput input {{
        background-color: #1c1c1c !important;
        border: 1px solid #2e2e2e !important;
        color: #f0f0f0 !important;
        font-family: Arial, sans-serif !important;
        border-radius: 6px !important;
        padding: 10px 14px !important;
    }}
    .stTextInput input:focus {{
        border-color: #555 !important;
        box-shadow: 0 0 0 2px rgba(255,255,255,0.06) !important;
    }}
    .stTextInput label {{
        color: #888 !important;
        font-family: Arial, sans-serif !important;
        font-size: 12px !important;
        letter-spacing: 0.5px;
    }}

    /* ── BOTÃO ENTRAR ── */
    .stFormSubmitButton button {{
        background-color: #C0392B !important;
        color: #fff !important;
        border: none !important;
        font-family: Arial, sans-serif !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        letter-spacing: 1px !important;
        border-radius: 6px !important;
        height: 46px !important;
        margin-top: 8px;
        transition: background 0.2s;
    }}
    .stFormSubmitButton button:hover {{
        background-color: #A93226 !important;
    }}
    </style>
    """, unsafe_allow_html=True)

    col_left, col_right = st.columns([3, 2])

    # ── PAINEL ESQUERDO: apenas fundo (logo vem do bg.jpg que o usuário fornece) ──
    with col_left:
        st.markdown("""
        <div style="
            font-family: Arial, sans-serif;
            font-size: 10px;
            letter-spacing: 5px;
            color: rgba(255,255,255,0.20);
            text-transform: uppercase;
            text-align: center;
            position: absolute;
            bottom: 32px;
            left: 0; right: 0;
        ">v17.0 &nbsp;·&nbsp; MS Studio</div>
        """, unsafe_allow_html=True)

    # ── PAINEL DIREITO ─────────────────────────────────────────────────────────
    with col_right:
        if not tem_alguem:
            st.warning(
                "Nenhum usuário configurado ainda. "
                "Adicione pelo menos um usuário no bloco [usuarios] das Secrets do Streamlit."
            )
            st.stop()

        logo_b64 = _logo_b64()
        logo_html = (
            f'<img src="data:image/png;base64,{logo_b64}" '
            f'style="width:min(380px,85%); display:block; margin:0 auto 28px auto;" alt="MS Studio"/>'
            if logo_b64 else ""
        )

        st.markdown(f"""
        <div style="width:100%; max-width:420px; margin:0 auto 0px; text-align:center;">
            {logo_html}
            <div style="
                font-family: Arial, sans-serif;
                font-size: 26px;
                font-weight: 700;
                color: #f0f0f0;
                margin-bottom: 4px;
            ">MS Studio</div>
            <div style="
                font-family: Arial, sans-serif;
                font-size: 13px;
                color: #555;
                margin-bottom: 20px;
            ">Conecte-se para continuar</div>
        </div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            login = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            entrar = st.form_submit_button("ENTRAR", use_container_width=True)

    if entrar:
        ok, _ = _verificar_credencial(login, senha)
        if ok:
            st.session_state["usuario_logado"] = login
            _carregar_usuarios_sheets.clear()
            st.rerun()
        else:
            with col_right:
                st.error("Usuário ou senha incorretos.")

    st.stop()
