import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime

PLANILHA_NOME = "MartinSousa - Financeiro"
ABA_NOME = "atividades"
COLUNAS = ["data_hora", "usuario", "tipo", "produto", "resumo",
           "codigo", "cor", "medidas", "link_capa", "link_pasta"]


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
                        codigo="", cor="", medidas="",
                        link_capa="", link_pasta=""):
    """Grava uma linha no historico. Nunca deixa um erro aqui quebrar a
    tela principal -- se a gravacao falhar, so ignora silenciosamente."""
    try:
        aba = _aba()
        aba.append_row([
            datetime.now().strftime("%d/%m/%Y %H:%M"),
            usuario, tipo, produto, resumo,
            codigo, cor, medidas, link_capa, link_pasta,
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
    busca = col_busca.text_input("🔍 Buscar por produto ou código", placeholder="ex: Bengala, MS-BENG-...")
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

    # mais recente primeiro
    df_exibir = df_exibir.iloc[::-1].reset_index(drop=True)

    if df_exibir.empty:
        st.info("Nenhum resultado para essa busca.")
        return

    # ── CARDS (quando há código + pelo menos 1 campo de produto) ──────────────
    tem_codigo = "codigo" in df_exibir.columns
    linhas_com_codigo = df_exibir[tem_codigo & df_exibir["codigo"].astype(str).str.strip().ne("")]

    if not linhas_com_codigo.empty and busca:
        st.markdown("##### Resultados encontrados")
        for _, row in linhas_com_codigo.iterrows():
            with st.container(border=True):
                col_info, col_thumb, col_btn = st.columns([4, 1, 1])
                with col_info:
                    st.markdown(f"**{row.get('produto', '')}**")
                    detalhes = []
                    if row.get("codigo"): detalhes.append(f"📋 `{row['codigo']}`")
                    if row.get("cor"):    detalhes.append(f"🎨 {row['cor']}")
                    if row.get("medidas"): detalhes.append(f"📐 {row['medidas']}")
                    if detalhes:
                        st.caption("  ·  ".join(detalhes))
                    st.caption(f"{row.get('data_hora','')}  ·  {row.get('usuario','')}  ·  {row.get('tipo','')}")
                with col_thumb:
                    link_capa = row.get("link_capa", "")
                    if link_capa:
                        st.markdown(f"[🖼️ Capa]({link_capa})")
                with col_btn:
                    if st.button("Usar este código", key=f"usar_cod_{row.name}",
                                 help=f"Copia o código {row.get('codigo','')} para o módulo de Imagem"):
                        st.session_state["img_codigo_importado"] = row.get("codigo", "")
                        st.session_state["img_nome_importado"] = row.get("produto", "")
                        st.success(f"Código **{row.get('codigo','')}** copiado! Vá para a aba Imagem.")
        st.markdown("---")

    # ── TABELA COMPLETA ────────────────────────────────────────────────────────
    colunas_visiveis = [c for c in ["data_hora", "usuario", "tipo", "produto", "resumo", "codigo"]
                        if c in df_exibir.columns]
    st.dataframe(df_exibir[colunas_visiveis], use_container_width=True, hide_index=True)
