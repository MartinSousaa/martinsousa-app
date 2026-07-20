import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime

PLANILHA_NOME = "MartinSousa - Financeiro"
ABA_NOME = "atividades"
COLUNAS = ["data_hora", "usuario", "tipo", "produto", "resumo",
           "codigo", "cor", "medidas", "peso", "link_capa", "link_pasta"]


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
        aba = planilha.worksheet(ABA_NOME)
        # Garante que colunas novas existem no cabeçalho sem apagar dados
        cabecalho = aba.row_values(1)
        for col in COLUNAS:
            if col not in cabecalho:
                aba.add_cols(1)
                col_idx = len(cabecalho) + 1
                aba.update_cell(1, col_idx, col)
                cabecalho.append(col)
        return aba
    except gspread.exceptions.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA_NOME, rows=2000, cols=len(COLUNAS))
        aba.append_row(COLUNAS, value_input_option="RAW")
        return aba


def registrar_atividade(usuario, tipo, produto, resumo,
                        codigo="", cor="", medidas="", peso="",
                        link_capa="", link_pasta=""):
    """Grava uma linha no historico. Nunca deixa um erro aqui quebrar a
    tela principal -- se a gravacao falhar, so ignora silenciosamente."""
    try:
        aba = _aba()
        aba.append_row([
            datetime.now().strftime("%d/%m/%Y %H:%M"),
            usuario, tipo, produto, resumo,
            codigo, cor, medidas, peso, link_capa, link_pasta,
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
        # Garante que colunas novas existem mesmo em planilhas antigas
        for col in ["codigo", "cor", "medidas", "link_capa", "link_pasta"]:
            if col not in df.columns:
                df[col] = ""
    return df


def buscar_por_codigo(codigo):
    """Retorna o dict de dados da última atividade de Descrição com esse código,
    ou None se não encontrar. Usado pelo módulo de Imagem."""
    try:
        df = carregar_atividades()
        if df.empty or "codigo" not in df.columns:
            return None
        mask = (df["codigo"].astype(str).str.strip() == str(codigo).strip()) & \
               (df["tipo"].str.contains("Descrição", case=False, na=False))
        encontrados = df[mask]
        if encontrados.empty:
            return None
        ultimo = encontrados.iloc[-1]
        return {
            "nome_produto": ultimo.get("produto", ""),
            "codigo": ultimo.get("codigo", ""),
            "cor": ultimo.get("cor", ""),
            "medidas": ultimo.get("medidas", ""),
            "peso": ultimo.get("peso", ""),
            "link_capa": ultimo.get("link_capa", ""),
            "resumo": ultimo.get("resumo", ""),
        }
    except Exception:
        return None


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

    # ── FILTROS ────────────────────────────────────────────────────────────────
    col_busca, col_filtro = st.columns([3, 1])
    busca = col_busca.text_input(
        "🔍 Buscar por produto ou código",
        placeholder="ex: Bengala, MS-BENG-..."
    )
    usuarios_disponiveis = ["Todos"] + sorted(df["usuario"].dropna().unique().tolist())
    filtro_usuario = col_filtro.selectbox("Usuário", usuarios_disponiveis)

    df_exibir = df.copy()
    if filtro_usuario != "Todos":
        df_exibir = df_exibir[df_exibir["usuario"] == filtro_usuario]
    if busca:
        termo = busca.strip().lower()
        mask = (
            df_exibir["produto"].astype(str).str.lower().str.contains(termo, na=False) |
            df_exibir.get("codigo", pd.Series([""] * len(df_exibir))).astype(str).str.lower().str.contains(termo, na=False)
        )
        df_exibir = df_exibir[mask]

    if df_exibir.empty:
        st.info("Nenhum resultado para essa busca.")
        return

    # mais recente primeiro
    df_exibir = df_exibir.iloc[::-1].reset_index(drop=True)

    # ── AGRUPAMENTO POR PRODUTO + CÓDIGO ──────────────────────────────────────
    # Chave de grupo: código (se tiver) ou nome do produto
    def _chave_grupo(row):
        cod = str(row.get("codigo", "")).strip()
        prod = str(row.get("produto", "sem produto")).strip()
        return f"{prod}__{cod}" if cod else prod

    df_exibir["_grupo"] = df_exibir.apply(_chave_grupo, axis=1)

    # Ordem dos grupos: pelo timestamp mais recente de cada grupo
    ordem_grupos = df_exibir.groupby("_grupo")["data_hora"].max().sort_values(ascending=False).index.tolist()

    for chave in ordem_grupos:
        grupo = df_exibir[df_exibir["_grupo"] == chave].copy()

        # Metadados do grupo
        produto_nome = grupo["produto"].dropna().iloc[0] if not grupo["produto"].dropna().empty else "—"
        codigos = grupo["codigo"].astype(str).str.strip().replace("", None).dropna().unique().tolist()
        codigo_principal = codigos[0] if codigos else ""
        usuarios_grupo = sorted(grupo["usuario"].dropna().unique().tolist())
        data_ultima = grupo["data_hora"].max()
        n_atividades = len(grupo)

        # ── Label de tipo de atividade (ícones por etapa)
        tipos_presentes = grupo["tipo"].dropna().unique().tolist()
        icones = []
        for t in tipos_presentes:
            tl = t.lower()
            if "descriç" in tl:  icones.append("📝")
            elif "imagem" in tl: icones.append("🖼️")
            elif "ajuste" in tl: icones.append("✏️")
            elif "título" in tl: icones.append("🔤")
            elif "palavra" in tl: icones.append("🔍")
            elif "viab" in tl:   icones.append("📊")
            else:                icones.append("📌")
        etapas_str = " ".join(dict.fromkeys(icones))  # sem duplicatas, mantém ordem

        # ── Link do Drive (mais recente)
        link_pasta_vals = grupo["link_pasta"].astype(str).str.strip().replace("", None).dropna()
        link_pasta = link_pasta_vals.iloc[-1] if not link_pasta_vals.empty else ""

        # ── Detalhes rápidos (cor, medidas)
        cor_val   = grupo["cor"].astype(str).str.strip().replace("", None).dropna()
        med_val   = grupo["medidas"].astype(str).str.strip().replace("", None).dropna()

        # ── Header do card ────────────────────────────────────────────────────
        label_expander = (
            f"{etapas_str}  **{produto_nome}**"
            + (f"  ·  `{codigo_principal}`" if codigo_principal else "")
            + f"  ·  {n_atividades} etapa(s)"
            + f"  ·  {', '.join(usuarios_grupo)}"
            + f"  ·  {data_ultima}"
        )

        with st.expander(label_expander, expanded=False):
            # Metadados do produto
            meta = []
            if cor_val.any():   meta.append(f"🎨 **Cor:** {cor_val.iloc[0]}")
            if med_val.any():   meta.append(f"📐 **Medidas:** {med_val.iloc[0]}")
            if codigo_principal: meta.append(f"📋 **Código:** `{codigo_principal}`")
            if meta:
                st.caption("  ·  ".join(meta))

            st.markdown("---")

            # Lista de etapas (mais recente primeiro)
            for _, row in grupo.iterrows():
                resumo_txt = str(row.get("resumo", "")).strip()
                resumo_curto = resumo_txt[:120] + ("…" if len(resumo_txt) > 120 else "")
                col_d, col_u, col_t, col_r = st.columns([2, 1, 2, 4])
                col_d.caption(str(row.get("data_hora", "")))
                col_u.caption(str(row.get("usuario", "")))
                col_t.markdown(f"**{row.get('tipo', '')}**")
                col_r.caption(resumo_curto or "—")

            st.markdown("---")

            # Ações do card
            col_drive, col_btn = st.columns([1, 1])
            if link_pasta:
                col_drive.markdown(f"[📁 Abrir pasta no Drive]({link_pasta})")
            if codigo_principal:
                if col_btn.button(
                    "📋 Usar este código na aba Imagem",
                    key=f"usar_cod_{chave}",
                    use_container_width=True,
                ):
                    st.session_state["img_codigo_importado"] = codigo_principal
                    st.session_state["img_nome_importado"] = produto_nome
                    st.success(f"Código **{codigo_principal}** copiado! Vá para a aba Imagem.")
