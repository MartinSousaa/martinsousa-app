import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime

PLANILHA_NOME = "MartinSousa - Financeiro"
ABA_NOME = "atividades"
COLUNAS = ["data_hora", "usuario", "tipo", "produto", "resumo",
           "codigo", "cor", "medidas", "peso", "link_capa", "link_pasta",
           "material", "caracteristicas", "diferenciais", "uso", "categoria"]


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
        # Garante que colunas novas existem no cabeÃ§alho sem apagar dados
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
                        link_capa="", link_pasta="",
                        material="", caracteristicas="", diferenciais="", uso="", categoria=""):
    """Grava uma linha no historico. Nunca deixa um erro aqui quebrar a
    tela principal -- se a gravacao falhar, so ignora silenciosamente."""
    try:
        aba = _aba()
        aba.append_row([
            datetime.now().strftime("%d/%m/%Y %H:%M"),
            usuario, tipo, produto, resumo,
            codigo, cor, medidas, peso, link_capa, link_pasta,
            material, caracteristicas, diferenciais, uso, categoria,
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
        for col in ["codigo", "cor", "medidas", "peso", "link_capa", "link_pasta",
                    "material", "caracteristicas", "diferenciais", "uso", "categoria"]:
            if col not in df.columns:
                df[col] = ""
    return df


def buscar_por_codigo(codigo):
    """Retorna o dict de dados da Ãºltima atividade de DescriÃ§Ã£o com esse cÃ³digo,
    ou None se nÃ£o encontrar. Usado pelo mÃ³dulo de Imagem."""
    try:
        df = carregar_atividades()
        if df.empty or "codigo" not in df.columns:
            return None
        mask = (df["codigo"].astype(str).str.strip() == str(codigo).strip()) & \
               (df["tipo"].str.contains("DescriÃ§Ã£o", case=False, na=False))
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
            "material": ultimo.get("material", ""),
            "caracteristicas": ultimo.get("caracteristicas", ""),
            "diferenciais": ultimo.get("diferenciais", ""),
            "uso": ultimo.get("uso", ""),
            "categoria": ultimo.get("categoria", ""),
        }
    except Exception:
        return None


def pagina_historico():
    st.subheader("HistÃ³rico de Atividades")

    try:
        df = carregar_atividades()
    except Exception as e:
        st.error(f"NÃ£o consegui carregar o histÃ³rico: {e}")
        return

    if df.empty:
        st.info("Nenhuma atividade registrada ainda.")
        return

    # ââ FILTROS ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    col_busca, col_filtro = st.columns([3, 1])
    busca = col_busca.text_input(
        "ð Buscar por produto ou cÃ³digo",
        placeholder="ex: Bengala, MS-BENG-..."
    )
    usuarios_disponiveis = ["Todos"] + sorted(df["usuario"].dropna().unique().tolist())
    filtro_usuario = col_filtro.selectbox("UsuÃ¡rio", usuarios_disponiveis)

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

    # ââ AGRUPAMENTO POR PRODUTO + CÃDIGO ââââââââââââââââââââââââââââââââââââââ
    # Chave de grupo: cÃ³digo (se tiver) ou nome do produto
    def _chave_grupo(row):
        cod = str(row.get("codigo", "")).strip()
        prod = str(row.get("produto", "sem produto")).strip()
        return f"{prod}__{cod}" if cod else prod

    df_exibir["_grupo"] = df_exibir.apply(_chave_grupo, axis=1)

    # Ordem dos grupos: pelo timestamp mais recente de cada grupo
    ordem_grupos = df_exibir.groupby("_grupo")["data_hora"].max().sort_values(ascending=False).index.tolist()

    # Extrai ID do Drive para thumbnail â definida fora do loop (evita redefiniÃ§Ã£o)
    import re as _re_hist
    def _thumb_url(drive_link):
        m = _re_hist.search(r'/d/([a-zA-Z0-9_-]+)', drive_link or "")
        return f"https://drive.google.com/uc?export=view&id={m.group(1)}" if m else None

    # Placeholder para mensagem de sucesso fora dos expanders (evita RemoveChild do React)
    _msg_sucesso = st.empty()
    if st.session_state.get("_hist_msg_sucesso"):
        _msg_sucesso.success(st.session_state.pop("_hist_msg_sucesso"))

    for chave in ordem_grupos:
        grupo = df_exibir[df_exibir["_grupo"] == chave].copy()

        # Metadados do grupo
        produto_nome = grupo["produto"].dropna().iloc[0] if not grupo["produto"].dropna().empty else "â"
        codigos = grupo["codigo"].astype(str).str.strip().replace("", None).dropna().unique().tolist()
        codigo_principal = codigos[0] if codigos else ""
        usuarios_grupo = sorted(grupo["usuario"].dropna().unique().tolist())
        data_ultima = grupo["data_hora"].max()
        n_atividades = len(grupo)

        # ââ Label de tipo de atividade (Ã­cones por etapa)
        tipos_presentes = grupo["tipo"].dropna().unique().tolist()
        icones = []
        for t in tipos_presentes:
            tl = t.lower()
            if "descriÃ§" in tl:  icones.append("ð")
            elif "imagem" in tl: icones.append("ð¼ï¸")
            elif "ajuste" in tl: icones.append("âï¸")
            elif "tÃ­tulo" in tl: icones.append("ð¤")
            elif "palavra" in tl: icones.append("ð")
            elif "viab" in tl:   icones.append("ð")
            else:                icones.append("ð")
        etapas_str = " ".join(dict.fromkeys(icones))  # sem duplicatas, mantÃ©m ordem

        # ââ Link do Drive (mais recente)
        link_pasta_vals = grupo["link_pasta"].astype(str).str.strip().replace("", None).dropna()
        link_pasta = link_pasta_vals.iloc[-1] if not link_pasta_vals.empty else ""

        # ââ Capa (imagem gerada mais recente, se houver link_capa no grupo)
        link_capa_vals = grupo["link_capa"].astype(str).str.strip().replace("", None).dropna()
        link_capa = link_capa_vals.iloc[-1] if not link_capa_vals.empty else ""

        # ââ Detalhes rÃ¡pidos (cor, medidas)
        cor_val   = grupo["cor"].astype(str).str.strip().replace("", None).dropna()
        med_val   = grupo["medidas"].astype(str).str.strip().replace("", None).dropna()

        # ââ Header do card ââââââââââââââââââââââââââââââââââââââââââââââââââââ
        label_expander = (
            f"{etapas_str}  **{produto_nome}**"
            + (f"  Â·  `{codigo_principal}`" if codigo_principal else "")
            + f"  Â·  {n_atividades} etapa(s)"
            + f"  Â·  {', '.join(usuarios_grupo)}"
            + f"  Â·  {data_ultima}"
        )

        with st.expander(label_expander, expanded=False):
            # Thumbnail da imagem + metadados lado a lado
            # Sempre cria as 2 colunas (estrutura fixa â evita RemoveChild do React)
            _col_thumb, _col_meta = st.columns([1, 4])
            thumb = _thumb_url(link_capa)
            if thumb:
                _col_thumb.image(thumb, use_container_width=True)
            else:
                _col_thumb.empty()  # placeholder fixo â mantÃ©m estrutura DOM estÃ¡vel

            meta = []
            if cor_val.any():    meta.append(f"ð¨ **Cor:** {cor_val.iloc[0]}")
            if med_val.any():    meta.append(f"ð **Medidas:** {med_val.iloc[0]}")
            if codigo_principal: meta.append(f"ð **CÃ³digo:** `{codigo_principal}`")
            _col_meta.caption("  Â·  ".join(meta) if meta else "")

            st.markdown("---")

            # Lista de etapas (mais recente primeiro)
            for _, row in grupo.iterrows():
                resumo_txt = str(row.get("resumo", "")).strip()
                resumo_curto = resumo_txt[:120] + ("â¦" if len(resumo_txt) > 120 else "")
                col_d, col_u, col_t, col_r = st.columns([2, 1, 2, 4])
                col_d.caption(str(row.get("data_hora", "")))
                col_u.caption(str(row.get("usuario", "")))
                col_t.markdown(f"**{row.get('tipo', '')}**")
                col_r.caption(resumo_curto or "â")

            st.markdown("---")

            # AÃ§Ãµes do card â colunas sempre renderizadas (estrutura fixa)
            col_drive, col_btn = st.columns([1, 1])
            col_drive.markdown(f"[ð Abrir pasta no Drive]({link_pasta})" if link_pasta else "")
            if codigo_principal:
                if col_btn.button(
                    "ð Usar este cÃ³digo na aba Imagem",
                    key=f"usar_cod_{chave}",
                    use_container_width=True,
                ):
                    st.session_state["img_codigo_importado"] = codigo_principal
                    st.session_state["img_nome_importado"] = produto_nome
                    # Armazena msg para renderizar FORA do expander (evita RemoveChild)
                    st.session_state["_hist_msg_sucesso"] = f"CÃ³digo **{codigo_principal}** copiado! VÃ¡ para a aba Imagem."
                    st.rerun()
            else:
                col_btn.empty()  # placeholder fixo
