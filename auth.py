import streamlit as st
import hashlib
import pandas as pd
from datetime import datetime, timedelta
import time as _time_auth
import gspread
from google.oauth2.service_account import Credentials
import secrets as _secrets

import planilha as _plan
# Nome vindo do ambiente: producao usa o padrao, homologacao usa a copia.
PLANILHA_NOME = _plan.nome()
ABA_USUARIOS = "usuarios"
_TOKEN_TTL_DIAS = 30  # tokens expiram após 30 dias

# Tokens em memória — cache rápido para WebSocket reconnections no mesmo processo.
# Ao iniciar, carregados do Sheets para sobreviver a redeploys do Railway.
_TOKENS: dict = {}
_tokens_sheets_carregados: bool = False
_tokens_sheets_ultimo_erro: float = 0  # evita retry em loop quando Sheets está fora


# ── PERSISTÊNCIA DE TOKENS NO SHEETS ─────────────────────────────────────────

def _crono(rotulo, seg, detalhe=""):
    """Registra quanto custou uma ida a planilha. Nunca derruba a leitura."""
    try:
        import cronometro
        cronometro.marcar(rotulo, seg, detalhe)
    except Exception:
        pass


@st.cache_resource
def _aba_tokens():
    """Acessa (ou cria) a aba de tokens na planilha."""
    # A planilha e aberta uma vez por processo em sheets.py. Aqui cada
    # modulo abria a sua, e abrir por nome custa uma varredura do Drive.
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        return planilha.worksheet("auth_tokens")
    except gspread.exceptions.WorksheetNotFound:
        aba = planilha.add_worksheet(title="auth_tokens", rows=1000, cols=3)
        aba.append_row(["token", "usuario", "criado_em"], value_input_option="RAW")
        return aba


def _garantir_tokens_carregados():
    """Carrega tokens do Sheets para _TOKENS (só uma vez por processo).
    Se o Sheets falhou, retenta após 5 minutos — evita que erro temporário
    bloqueie a reconexão por toda a vida do processo."""
    global _tokens_sheets_carregados, _tokens_sheets_ultimo_erro
    if _tokens_sheets_carregados:
        return
    # Se o Sheets deu erro recentemente, não fica tentando em loop
    if _tokens_sheets_ultimo_erro and _time_auth.time() - _tokens_sheets_ultimo_erro < 300:
        return
    try:
        aba = _aba_tokens()
        registros = aba.get_all_records(value_render_option="UNFORMATTED_VALUE")
        limite = datetime.now() - timedelta(days=_TOKEN_TTL_DIAS)
        linhas_expiradas = []
        for i, r in enumerate(registros, start=2):  # linha 1 = cabeçalho
            tok = str(r.get("token", "")).strip()
            usr = str(r.get("usuario", "")).strip()
            criado = str(r.get("criado_em", "")).strip()
            if not tok or not usr:
                continue
            # Verifica TTL — descarta tokens expirados
            try:
                dt = datetime.strptime(criado, "%d/%m/%Y %H:%M")
                if dt < limite:
                    linhas_expiradas.append(i)
                    continue
            except Exception:
                pass  # data inválida — mantém o token
            _TOKENS[tok] = usr
        # Limpa tokens expirados do Sheets (em lote, de baixo pra cima)
        if linhas_expiradas:
            try:
                for ln in sorted(linhas_expiradas, reverse=True):
                    aba.delete_rows(ln)
            except Exception:
                pass
        _tokens_sheets_carregados = True  # só marca sucesso aqui
    except Exception:
        _tokens_sheets_ultimo_erro = _time_auth.time()
        # falha silenciosa — pede login normalmente, retenta em 5 min


def _salvar_token_sheets(token, usuario):
    """Grava novo token no Sheets para sobreviver a redeploys."""
    try:
        aba = _aba_tokens()
        aba.append_row(
            [token, usuario, datetime.now().strftime("%d/%m/%Y %H:%M")],
            value_input_option="RAW",
        )
    except Exception:
        pass  # falha silenciosa — token ainda funciona na sessão atual


# ── HASH ──────────────────────────────────────────────────────────────────────

def _hash(senha):
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


# ── SHEETS ────────────────────────────────────────────────────────────────────

# Reutiliza a conexao entre reruns. Sem isso cada chamada refazia
# from_service_account_info + gspread.authorize + open() + worksheet() —
# quatro idas a rede antes de ler o primeiro dado, por modulo, a cada rerun.
def _cliente_sheets():
    """Cliente gspread compartilhado (ver sheets.py).

    Era um bloco proprio de credencial + authorize, identico em nove
    modulos: nove trocas de token por processo, todas no cold start.
    """
    import sheets as _sh
    return _sh.cliente()


@st.cache_resource
def _aba_usuarios():
    """Acessa (ou cria) a aba de usuários na planilha."""
    # A planilha e aberta uma vez por processo em sheets.py. Aqui cada
    # modulo abria a sua, e abrir por nome custa uma varredura do Drive.
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        return planilha.worksheet(ABA_USUARIOS)
    except gspread.exceptions.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA_USUARIOS, rows=500, cols=5)
        aba.append_row(
            ["login", "senha_hash", "ativo", "admin", "criado_em"],
            value_input_option="RAW",
        )
        return aba


# Último resultado bem-sucedido da leitura de usuários.
# Serve de rede de segurança: uma falha transitória do Sheets NÃO pode fazer o
# sistema concluir que ninguém é admin — isso trocaria o layout inteiro do app
# embaixo do usuário que está trabalhando.
_ULTIMOS_USUARIOS_OK = {"df": None}


@st.cache_data(ttl=600)
def _carregar_usuarios_sheets():
    """Carrega usuários do Sheets. Cache de 60s para não sobrecarregar a API.

    Em caso de erro devolve a última leitura bem-sucedida em vez de um
    DataFrame vazio. Um vazio faria is_admin() retornar False para todo mundo
    e remontar a navegação no meio da operação.
    """
    try:
        aba = _aba_usuarios()
        import time as _t_crono
        _t0_crono = _t_crono.perf_counter()
        registros = aba.get_all_records(value_render_option="UNFORMATTED_VALUE")
        _crono("Planilha: usuarios", _t_crono.perf_counter() - _t0_crono,
               f"{len(registros)} linhas")
        df = pd.DataFrame(registros)
        if not df.empty:
            df.columns = [str(c).strip().lower() for c in df.columns]
        _ULTIMOS_USUARIOS_OK["df"] = df
        return df
    except Exception:
        anterior = _ULTIMOS_USUARIOS_OK.get("df")
        if anterior is not None:
            return anterior
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

# Quem é admin quando o secret ADMINS não está configurado.
# Só o dono — qualquer outro perfil precisa ser dito em voz alta, no secret ou
# na coluna `admin` da aba de usuários.
ADMINS_PADRAO = {"martinsousa"}


def eh_dono(usuario_logado):
    """O dono do Studio — não é o mesmo que ter perfil admin.

    Serve para o que é só dele ver, como o painel de quem está no Studio agora.
    Um gestor a mais no secret ADMINS ganha as telas de gestão, não a vigilância
    de quem está online.
    """
    return str(usuario_logado or "").strip().lower() in ADMINS_PADRAO


def eh_gestor(usuario_logado):
    """Quem manda: enxerga o desempenho dos outros e entra em Ponto, Financeiro
    e Administrativo.

    Vem do secret ADMINS (ou, sem ele, do dono) — e NUNCA da coluna `admin` da
    planilha. A diferença importa: a coluna é editável pelo próprio Studio, por
    quem já tem acesso ao Administrativo. Se ela concedesse este perfil, quem
    entrasse lá uma vez poderia se promover, e passaria a ver a meta individual
    de cada colega.

    `is_admin` continua valendo para o que é acesso comum de gestão. Este aqui é
    para o que não pode ser delegado por engano.
    """
    u = str(usuario_logado or "").strip().lower()
    return bool(u) and u in (_admins_configurados() or ADMINS_PADRAO)


def _admins_configurados():
    """Logins com perfil admin, do secret ADMINS. None quando não configurado.

    Formato: ADMINS = "MartinSousa, Renan"
    """
    try:
        bruto = str(st.secrets.get("ADMINS", "") or "").strip()
    except Exception:
        bruto = ""
    if not bruto:
        return None
    return {p.strip().lower() for p in bruto.replace(";", ",").split(",") if p.strip()}


def _calcular_is_admin(usuario_logado):
    """Perfil admin: lista explícita do secret ADMINS, ou coluna admin no Sheets.

    Antes, TODO usuário do bloco `usuarios` das Secrets era admin — só por estar
    lá. Como as colaboradoras estão nesse bloco, as quatro tinham Administrativo
    aberto: lista de usuários, criar e desativar gente, e o Financeiro. A senha
    pedida na entrada do Administrativo é a da própria pessoa, então não segurava
    nada.

    Estar cadastrado é uma coisa; ser administrador é outra, e agora precisa ser
    dito: no secret ADMINS ou na coluna `admin` da aba de usuários.
    """
    u = str(usuario_logado or "").strip().lower()
    if not u:
        return False
    if u in (_admins_configurados() or ADMINS_PADRAO):
        return True
    df = _carregar_usuarios_sheets()
    if df.empty or "login" not in df.columns:
        return False
    row = df[df["login"].astype(str) == usuario_logado]
    if row.empty:
        return False
    return str(row.iloc[0].get("admin", "")).lower() in ("sim", "true", "1", "yes")


def is_admin(usuario_logado):
    """Perfil admin do usuário, FIXADO na primeira checagem da sessão.

    Por que fixar: o valor decide qual navegação é montada (acordeão
    Gestão/Operação para admin, barra plana para colaborador). Se ele oscilar
    no meio da sessão — por uma falha momentânea do Sheets, por exemplo — o
    Streamlit remonta a árvore de widgets inteira e o usuário perde tudo o que
    estava preenchendo. O perfil só muda ao sair e entrar de novo.
    """
    if not usuario_logado:
        return False
    chave = f"_perfil_admin__{usuario_logado}"
    if chave not in st.session_state:
        st.session_state[chave] = _calcular_is_admin(usuario_logado)
    return st.session_state[chave]


# ── LOGIN ──────────────────────────────────────────────────────────────────────

def _logo_b64():
    """Lê a logo branca (para painel escuro da tela de login)."""
    import os, base64
    # Tenta logo_branco.png primeiro (criado para fundo escuro), depois logo.png como fallback
    for nome in ("logo_branco.png", "logo.png"):
        path = os.path.join(os.path.dirname(__file__), nome)
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

    # ── Reconexão automática via token de URL ─────────────────────────────────
    # Se o WebSocket caiu e o Streamlit criou uma nova sessão, o token ainda
    # está na URL. Tenta restaurar sem pedir senha.
    # _garantir_tokens_carregados() busca tokens do Sheets se o container
    # reiniciou (redeploy Railway) e _TOKENS estava vazio.
    _tok = st.query_params.get("_s", "")
    if _tok:
        _garantir_tokens_carregados()
        if _tok in _TOKENS:
            st.session_state["usuario_logado"] = _TOKENS[_tok]
            return _TOKENS[_tok]

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

    header[data-testid="stHeader"]  {{ display: none !important; }}
    [data-testid="stSidebar"]        {{ display: none !important; }}
    .stDeployButton                  {{ display: none !important; }}
    #MainMenu                        {{ display: none !important; }}
    footer                           {{ display: none !important; }}
    #stDecoration                    {{ display: none !important; }}

    /* ── TELA INTEIRA: zera TODOS os paddings/margens/backgrounds ── */
    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stAppViewBlockContainer"],
    .main,
    [data-testid="stMain"],
    [data-testid="stMainBlockContainer"],
    .main .block-container {{
        padding: 0 !important;
        margin: 0 !important;
        max-width: 100% !important;
        background-color: #0d0d0d !important;
    }}
    /* Em qualquer tema, o fundo da tela de login é sempre escuro */
    body.tema-claro .stApp,
    body.tema-claro [data-testid="stMain"],
    body.tema-claro [data-testid="stMainBlockContainer"],
    body.tema-claro [data-testid="stAppViewContainer"],
    body.tema-claro .main {{
        background-color: #0d0d0d !important;
    }}

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

    /* ── PAINEL ESQUERDO: imagem de fundo ── */
    [data-testid="stColumn"]:first-child > div {{
        {bg_css}
        min-height: 100vh !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 60px 40px;
    }}

    /* ── PAINEL DIREITO: sempre escuro ── */
    [data-testid="stColumn"]:last-child > div {{
        background-color: #111111 !important;
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

    /* ── PAINEL DIREITO: força texto claro em qualquer tema ──────────────── */
    /* Anula o CSS global que força texto escuro no tema claro                */
    [data-testid="stColumn"]:last-child *,
    body.tema-claro [data-testid="stColumn"]:last-child,
    body.tema-claro [data-testid="stColumn"]:last-child * {{
        color: #f0f0f0 !important;
    }}

    /* ── INPUTS: sempre escuros no painel de login ── */
    [data-testid="stColumn"]:last-child .stTextInput input,
    body.tema-claro [data-testid="stColumn"]:last-child .stTextInput input,
    body.tema-claro [data-testid="stColumn"]:last-child [data-baseweb="input"] input {{
        background-color: #1c1c1c !important;
        border: 1px solid #2e2e2e !important;
        color: #f0f0f0 !important;
        font-family: Arial, sans-serif !important;
        border-radius: 6px !important;
        padding: 10px 14px !important;
        box-shadow: none !important;
        height: 46px !important;
        min-height: 46px !important;
    }}
    [data-testid="stColumn"]:last-child .stTextInput input:focus,
    body.tema-claro [data-testid="stColumn"]:last-child .stTextInput input:focus {{
        border-color: #555 !important;
        box-shadow: 0 0 0 2px rgba(255,255,255,0.06) !important;
    }}

    /* Labels dos inputs: cinza suave */
    [data-testid="stColumn"]:last-child .stTextInput label,
    [data-testid="stColumn"]:last-child [data-testid="stWidgetLabel"] p,
    body.tema-claro [data-testid="stColumn"]:last-child .stTextInput label,
    body.tema-claro [data-testid="stColumn"]:last-child [data-testid="stWidgetLabel"] p,
    body.tema-claro [data-testid="stColumn"]:last-child [data-testid="stWidgetLabel"] * {{
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

    /* ── MOBILE: esconde painel da imagem, login ocupa tela toda ── */
    @media screen and (max-width: 768px) {{
        [data-testid="stColumn"]:first-child {{
            display: none !important;
        }}
        [data-testid="stColumn"]:last-child {{
            width: 100% !important;
            min-width: 100% !important;
            flex: none !important;
        }}
        [data-testid="stColumn"]:last-child > div {{
            background-image: linear-gradient(rgba(0,0,0,0.72), rgba(0,0,0,0.72)),
                              url('data:image/jpeg;base64,{bg_data}') !important;
            background-size: cover !important;
            background-position: center !important;
            padding: 60px 28px !important;
        }}
        [data-testid="stColumn"]:last-child .stTextInput input,
        body.tema-claro [data-testid="stColumn"]:last-child .stTextInput input {{
            font-size: 16px !important;
            background-color: rgba(30,30,30,0.9) !important;
        }}
    }}
    </style>
    """, unsafe_allow_html=True)

    col_left, col_right = st.columns([3, 2])

    # ── PAINEL ESQUERDO ────────────────────────────────────────────────────────
    with col_left:
        st.markdown("""
        <div style="
            text-align: center;
            font-family: Arial, sans-serif;
            font-size: 10px;
            letter-spacing: 4px;
            color: rgba(255,255,255,0.3);
            text-transform: uppercase;
            margin-top: auto;
            padding-top: 80vh;
        ">v17.0 · MS Studio</div>
        """, unsafe_allow_html=True)

    # ── PAINEL DIREITO ─────────────────────────────────────────────────────────
    with col_right:
        logo_b64 = _logo_b64()
        logo_html = (
            f'<img src="data:image/png;base64,{logo_b64}" '
            f'style="width:320px; max-width:85%; display:block; margin:0 auto 28px;" alt="MS Studio"/>'
            if logo_b64 else
            '<div style="font-family:Georgia,serif;font-size:72px;color:#fff;letter-spacing:-2px;text-align:center;margin-bottom:20px;">MS</div>'
        )
        st.markdown(f"""
        <div style="width:100%; max-width:380px; margin:0 auto 24px; text-align:center;">
            {logo_html}
            <div style="
                font-family: Georgia, 'Times New Roman', serif;
                font-size: 28px;
                font-weight: 400;
                color: #ffffff;
                letter-spacing: 2px;
                margin-bottom: 8px;
            ">MS Studio</div>
            <div style="
                font-family: Arial, sans-serif;
                font-size: 13px;
                color: #cccccc;
                letter-spacing: 0.5px;
            ">Conecte-se para continuar</div>
        </div>
        """, unsafe_allow_html=True)

        if not tem_alguem:
            st.warning(
                "Nenhum usuário configurado ainda. "
                "Adicione pelo menos um usuário no bloco [usuarios] das Secrets do Streamlit."
            )
            st.stop()

        with st.form("login_form"):
            login = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            entrar = st.form_submit_button("ENTRAR", use_container_width=True)

    if entrar:
        ok, _ = _verificar_credencial(login, senha)
        if ok:
            st.session_state["usuario_logado"] = login
            # Gera token de reconexão: fica na URL (WebSocket reconnect) e no Sheets (redeploy)
            _tok = _secrets.token_hex(24)
            _TOKENS[_tok] = login
            _salvar_token_sheets(_tok, login)  # persiste no Sheets para sobreviver a redeploys
            st.query_params["_s"] = _tok
            _carregar_usuarios_sheets.clear()
            st.rerun()
        else:
            with col_right:
                st.error("Usuário ou senha incorretos.")

    st.stop()
