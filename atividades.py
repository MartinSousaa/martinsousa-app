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


# Reutiliza a conexao entre reruns. Sem isso cada chamada refazia
# from_service_account_info + gspread.authorize + open() + worksheet() —
# quatro idas a rede antes de ler o primeiro dado, por modulo, a cada rerun.
@st.cache_resource
def _cliente():
    creds_dict = dict(st.secrets["gcp_service_account"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)


@st.cache_resource
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
                        link_capa="", link_pasta="",
                        material="", caracteristicas="", diferenciais="", uso="", categoria=""):
    """Grava uma linha no historico. Retorna True/False.

    Uma falha aqui nunca derruba a tela principal -- mas tambem nao passa em
    silencio: o historico alimenta o placar e a analise de metas, entao um
    registro perdido vira credito perdido para o colaborador.
    """
    try:
        aba = _aba()
        aba.append_row([
            datetime.now().strftime("%d/%m/%Y %H:%M"),
            usuario, tipo, produto, resumo,
            codigo, cor, medidas, peso, link_capa, link_pasta,
            material, caracteristicas, diferenciais, uso, categoria,
        ], value_input_option="RAW")
        carregar_atividades.clear()
        return True
    except Exception:
        try:
            st.warning(
                f"⚠️ '{tipo}' foi concluído, mas não entrou no histórico. "
                "Isso afeta seu placar e suas metas — avise o administrador."
            )
        except Exception:
            pass
        return False


@st.cache_data(ttl=90)
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
            "material": ultimo.get("material", ""),
            "caracteristicas": ultimo.get("caracteristicas", ""),
            "diferenciais": ultimo.get("diferenciais", ""),
            "uso": ultimo.get("uso", ""),
            "categoria": ultimo.get("categoria", ""),
        }
    except Exception:
        return None



@st.cache_data(ttl=300, show_spinner=False)
def _imagens_da_pasta(pasta_id):
    """Lista as imagens de uma pasta do Drive. Retorna [(id, nome), ...].

    Cache de 5 min porque o Histórico redesenha a cada interação e uma chamada
    de rede por card tornaria a aba lenta de novo.
    """
    if not pasta_id:
        return []
    import gdrive
    arquivos = gdrive.listar(
        f"'{pasta_id}' in parents and trashed=false and mimeType contains 'image/'",
        fields="files(id,name)",
    )
    return [(a.get("id", ""), a.get("name", "")) for a in arquivos if a.get("id")]


def _id_da_pasta(link_pasta):
    """Extrai o ID da pasta a partir do link salvo no histórico."""
    import re as _re_pasta
    m = _re_pasta.search(r"/folders/([a-zA-Z0-9_-]+)", link_pasta or "")
    return m.group(1) if m else ""


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
    col_busca, col_filtro, col_ordem = st.columns([3, 1, 1])
    busca = col_busca.text_input(
        "🔍 Buscar por produto ou código",
        placeholder="ex: Bengala, MS-BENG-..."
    )
    usuarios_disponiveis = ["Todos"] + sorted(df["usuario"].dropna().unique().tolist())
    filtro_usuario = col_filtro.selectbox("Usuário", usuarios_disponiveis)
    ordem_escolhida = col_ordem.selectbox(
        "Ordenar por data",
        ["Mais recente primeiro", "Mais antiga primeiro"],
        key="hist_ordem",
    )
    _decrescente = ordem_escolhida == "Mais recente primeiro"

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

    # A data e gravada como texto "%d/%m/%Y %H:%M". Ordenar essa string coloca
    # 30/07 acima de 25/08, porque compara caractere a caractere — o dia vem
    # primeiro. Convertendo para data de verdade a ordem passa a ser a real.
    # Linhas com data ilegivel viram NaT e vao para o fim, em vez de derrubar a tela.
    df_exibir["_dt"] = pd.to_datetime(
        df_exibir["data_hora"], format="%d/%m/%Y %H:%M", errors="coerce"
    )
    df_exibir = df_exibir.sort_values(
        "_dt", ascending=not _decrescente, na_position="last"
    ).reset_index(drop=True)

    # ── AGRUPAMENTO POR PRODUTO + CÓDIGO ──────────────────────────────────────
    # Chave de grupo: código (se tiver) ou nome do produto
    def _chave_grupo(row):
        cod = str(row.get("codigo", "")).strip()
        prod = str(row.get("produto", "sem produto")).strip()
        return f"{prod}__{cod}" if cod else prod

    df_exibir["_grupo"] = df_exibir.apply(_chave_grupo, axis=1)

    # Ordem dos grupos: pelo timestamp mais recente de cada grupo
    # O grupo e posicionado pela atividade mais recente que ele contem, e a
    # ordem segue o que o colaborador escolheu no filtro.
    ordem_grupos = (
        df_exibir.groupby("_grupo")["_dt"].max()
        .sort_values(ascending=not _decrescente, na_position="last")
        .index.tolist()
    )

    # Extrai ID do Drive para thumbnail — definida fora do loop (evita redefinição)
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

        # ── Capa (imagem gerada mais recente, se houver link_capa no grupo)
        link_capa_vals = grupo["link_capa"].astype(str).str.strip().replace("", None).dropna()
        link_capa = link_capa_vals.iloc[-1] if not link_capa_vals.empty else ""

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
            # Thumbnail da imagem + metadados lado a lado
            # Sempre cria as 2 colunas (estrutura fixa — evita RemoveChild do React)
            _col_thumb, _col_meta = st.columns([1, 4])
            thumb = _thumb_url(link_capa)
            if thumb:
                _col_thumb.image(thumb, use_container_width=True)
            else:
                _col_thumb.empty()  # placeholder fixo — mantém estrutura DOM estável

            meta = []
            if cor_val.any():    meta.append(f"🎨 **Cor:** {cor_val.iloc[0]}")
            if med_val.any():    meta.append(f"📐 **Medidas:** {med_val.iloc[0]}")
            if codigo_principal: meta.append(f"📋 **Código:** `{codigo_principal}`")
            _col_meta.caption("  ·  ".join(meta) if meta else "")

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

            # Ações do card — colunas sempre renderizadas (estrutura fixa)
            col_drive, col_ver, col_btn = st.columns([1, 1, 1])
            col_drive.markdown(f"[📁 Abrir pasta no Drive]({link_pasta})" if link_pasta else "")

            # Visualizar as imagens sem sair do Studio.
            #
            # A listagem so acontece quando o colaborador pede: o Streamlit executa
            # o corpo de tudo que esta na tela a cada rerun, entao listar a pasta de
            # todo card faria uma chamada de rede por card, em toda interacao.
            _pasta_id = _id_da_pasta(link_pasta)
            _chave_ver = f"_hist_ver_imgs_{chave}"
            if _pasta_id:
                if col_ver.button("🖼️ Ver imagens", key=f"ver_imgs_{chave}",
                                  use_container_width=True):
                    st.session_state[_chave_ver] = not st.session_state.get(_chave_ver, False)
            else:
                col_ver.empty()  # placeholder fixo — mantém a estrutura estável

            if st.session_state.get(_chave_ver) and _pasta_id:
                _imgs = _imagens_da_pasta(_pasta_id)
                if not _imgs:
                    st.info(
                        "Nenhuma imagem encontrada nessa pasta. Ou elas não chegaram a "
                        "ser salvas no Drive, ou a pasta foi movida."
                    )
                else:
                    import gdrive as _gd_hist
                    _cols_img = st.columns(4)
                    for _i, (_fid, _fnome) in enumerate(_imgs):
                        with _cols_img[_i % 4]:
                            st.image(
                                _gd_hist.url_thumbnail(_fid, 400),
                                caption=_fnome[:28],
                                use_container_width=True,
                            )
                            st.markdown(
                                f"[abrir](https://drive.google.com/file/d/{_fid}/view)"
                            )
            if codigo_principal:
                if col_btn.button(
                    "📋 Usar este código na aba Imagem",
                    key=f"usar_cod_{chave}",
                    use_container_width=True,
                ):
                    st.session_state["img_codigo_importado"] = codigo_principal
                    st.session_state["img_nome_importado"] = produto_nome
                    # Armazena msg para renderizar FORA do expander (evita RemoveChild)
                    st.session_state["_hist_msg_sucesso"] = f"Código **{codigo_principal}** copiado! Vá para a aba Imagem."
                    st.rerun()
            else:
                col_btn.empty()  # placeholder fixo
