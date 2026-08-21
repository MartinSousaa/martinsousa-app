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
    "termos_busca", "termos_evitar", "foto_drive_id",
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


# ── GOOGLE DRIVE — FOTO DE TRIAGEM ────────────────────────────────────────────

def _drive_service_triagem():
    """Mantido por compatibilidade — delega para o módulo gdrive."""
    import gdrive
    return gdrive.service()


def _pasta_triagens_id():
    """Retorna o ID da pasta de fotos de triagem no Drive.
    Usa DRIVE_PASTA_TRIAGENS_ID se configurado, senão usa DRIVE_PASTA_IMAGENS_ID."""
    import gdrive
    return gdrive.pasta_triagens_id()


def upload_foto_triagem(imagem_bytes, nome_arquivo):
    """Faz upload da foto de referência do produto para o Drive.
    Retorna (file_id, erro).

    O upload passa pelo módulo gdrive, que trata Unidade Compartilhada,
    impersonation e OAuth conforme as secrets configuradas.
    """
    import gdrive
    info, err = gdrive.upload(
        imagem_bytes,
        nome_arquivo,
        gdrive.pasta_triagens_id(),
        mimetype=gdrive.mimetype_por_nome(nome_arquivo),
    )
    if err:
        return None, err
    return info["id"], None


def url_thumbnail(foto_drive_id, tamanho=200):
    """Retorna URL de thumbnail do Google Drive (imagem deve ser pública)."""
    import gdrive
    return gdrive.url_thumbnail(foto_drive_id, tamanho)


# ── SHEETS — LEITURA E GRAVAÇÃO ───────────────────────────────────────────────

def salvar_triagem(usuario, dados):
    """dados: dict com as chaves de COLUNAS (exceto data_hora/usuario, que
    a funcao preenche sozinha). Cada triagem vira uma linha nova -- se o
    mesmo SKU for triado de novo, fica um historico, e buscar_triagem_por_sku
    sempre pega a mais recente. Lança RuntimeError se a gravação falhar."""
    try:
        aba = _aba()
        linha = [datetime.now().strftime("%d/%m/%Y %H:%M"), usuario] + [
            dados.get(c, "") for c in COLUNAS if c not in ("data_hora", "usuario")
        ]
        aba.append_row(linha, value_input_option="RAW")
        carregar_triagens.clear()
    except Exception as e:
        raise RuntimeError(f"Não consegui salvar a triagem no Google Sheets: {e}") from e


@st.cache_data(ttl=30)
def carregar_triagens():
    try:
        aba = _aba()
        registros = aba.get_all_records(value_render_option="UNFORMATTED_VALUE")
        df = pd.DataFrame(registros)
        if not df.empty:
            df.columns = [str(c).strip().lower() for c in df.columns]
        return df
    except Exception as e:
        raise RuntimeError(f"Não consegui carregar as triagens do Google Sheets: {e}") from e


def _normalizar(texto):
    """Remove acentos e converte para minúsculas para busca tolerante.
    'álbum' e 'album' passam a ser equivalentes."""
    import unicodedata
    return unicodedata.normalize("NFD", str(texto)).encode("ascii", "ignore").decode("ascii").lower()


def _chave_variante(row):
    """Chave composta que identifica variantes distintas do mesmo produto.
    Produtos com mesmo nome mas medidas/peso/cores diferentes retornam chaves diferentes."""
    return "|".join([
        str(row.get("nome_comercial", "")).strip().lower(),
        str(row.get("medidas", "")).strip().lower(),
        str(row.get("peso", "")).strip().lower(),
        str(row.get("variacao_cores", "")).strip().lower(),
    ])


def buscar_triagens_por_trecho(trecho):
    """Busca por pedaco do nome comercial (case-insensitive, ignora acentos).
    Retorna lista de dicts — um por variante distinta (nome_comercial + medidas +
    peso + variacao_cores), pegando a triagem mais recente de cada variante.

    Diferente do comportamento anterior, produtos com o MESMO nome mas specs
    diferentes (ex: 'Caixa de relógio 5 posições' vs '10 posições') aparecem
    como entradas separadas."""
    df = carregar_triagens()
    if df.empty or "nome_comercial" not in df.columns:
        return []
    trecho_l = _normalizar(trecho).strip()
    if not trecho_l:
        return []
    filtradas = df[df["nome_comercial"].astype(str).apply(_normalizar).str.contains(trecho_l, na=False)]
    if filtradas.empty:
        return []
    filtradas = filtradas.sort_values("data_hora")
    # Deduplica por variante composta (não só pelo nome)
    filtradas = filtradas.copy()
    filtradas["_chave"] = filtradas.apply(_chave_variante, axis=1)
    unicas = filtradas.drop_duplicates(subset="_chave", keep="last")
    unicas = unicas.drop(columns=["_chave"])
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


# ── WIDGET REUTILIZÁVEL — SELETOR DE PRODUTO ─────────────────────────────────

def _label_variante(v):
    """Monta um rótulo legível para uma variante (usado nos cards e avisos)."""
    partes = []
    if v.get("medidas"):
        partes.append(f"📐 {v['medidas']}")
    if v.get("peso"):
        partes.append(f"⚖️ {v['peso']}")
    if v.get("variacao_cores"):
        partes.append(f"🎨 {v['variacao_cores']}")
    if v.get("material"):
        partes.append(f"🧱 {v['material']}")
    return " · ".join(partes) if partes else "Sem detalhes adicionais"


def widget_seletor_produto(key_prefix, label="Nome do produto"):
    """Widget reutilizável de busca e seleção de produto via triagem.

    Exibe um campo de busca. Se encontrar exatamente 1 variante, auto-seleciona.
    Se encontrar múltiplas variantes com o mesmo nome, exibe cards visuais
    (com foto do Drive se disponível, ou texto com specs) para o colaborador escolher.

    Retorna:
        (dados_selecionados: dict | None, aviso: (tipo, msg) | None)

    dados_selecionados é None enquanto o colaborador ainda não escolheu uma variante.
    Quando não há triagem cadastrada, retorna {"nome_comercial": busca} para
    pré-preencher o nome no formulário abaixo.
    """
    busca_key = f"{key_prefix}_busca"
    sel_key = f"{key_prefix}_sel_idx"
    busca_prev_key = f"{key_prefix}_busca_prev"

    busca = st.text_input(label, key=busca_key)

    # Limpa seleção sempre que o texto de busca muda
    if st.session_state.get(busca_prev_key) != busca:
        st.session_state[sel_key] = None
        st.session_state[busca_prev_key] = busca

    if not busca:
        return None, None

    encontrados = buscar_triagens_por_trecho(busca)

    if not encontrados:
        return (
            {"nome_comercial": busca},
            ("warning", "Nenhuma triagem encontrada para esse produto ainda — preencha os campos abaixo.")
        )

    if len(encontrados) == 1:
        return (
            encontrados[0],
            ("info", f"Triagem encontrada: **{encontrados[0]['nome_comercial']}**. Confira os dados abaixo antes de gerar.")
        )

    # Múltiplas variantes encontradas
    nomes_unicos = list(dict.fromkeys(v.get("nome_comercial", "") for v in encontrados))

    # Se algum já foi selecionado, exibe resumo + botão Trocar
    selecionado_idx = st.session_state.get(sel_key)
    if selecionado_idx is not None and selecionado_idx < len(encontrados):
        v = encontrados[selecionado_idx]
        col_info, col_trocar = st.columns([5, 1])
        col_info.success(f"✅ **{v.get('nome_comercial', '')}** — {_label_variante(v)}")
        if col_trocar.button("Trocar", key=f"{key_prefix}_trocar", use_container_width=True):
            st.session_state[sel_key] = None
            st.rerun()
        return v, None

    # Nomes diferentes → selectbox por nome (comportamento original)
    if len(nomes_unicos) > 1:
        sel_nome_key = f"{key_prefix}_sel_nome"
        escolha_nome = st.selectbox(
            "Mais de um produto encontrado com esse nome — qual é?",
            nomes_unicos,
            key=sel_nome_key,
        )
        candidatos = [v for v in encontrados if v.get("nome_comercial") == escolha_nome]
        if len(candidatos) == 1:
            return candidatos[0], ("info", "Confira os dados abaixo antes de gerar.")
        # Mesmo nome → prossegue para cards visuais com este subconjunto
        encontrados = candidatos

    # Mesmo nome, specs diferentes → cards visuais
    nome_prod = encontrados[0].get("nome_comercial", busca)
    st.info(f"**{nome_prod}** tem {len(encontrados)} variante(s) cadastrada(s). Selecione a correta:")

    n_cols = min(len(encontrados), 4)
    cols = st.columns(n_cols)
    for i, variante in enumerate(encontrados):
        with cols[i % n_cols]:
            foto_id = str(variante.get("foto_drive_id", "")).strip()
            if foto_id:
                thumb = url_thumbnail(foto_id)
                try:
                    st.image(thumb, use_container_width=True)
                except Exception:
                    st.markdown("📦")
            else:
                st.markdown("📦")
            st.caption(_label_variante(variante))
            if st.button("Selecionar", key=f"{key_prefix}_btn_{i}", use_container_width=True):
                st.session_state[sel_key] = i
                st.rerun()

    return None, None  # aguardando seleção do colaborador


# ── PÁGINA DE TRIAGEM ─────────────────────────────────────────────────────────

def pagina_triagem(usuario_logado):
    st.subheader("Triagem do Produto")
    st.caption("Preenche uma vez por produto — essa informação alimenta palavras-chave, título e descrição.")

    # Persiste a última categoria selecionada entre reruns
    _CATS = sorted(ML_COMISSAO_POR_CATEGORIA.keys())
    if "triagem_ultima_categoria" not in st.session_state:
        st.session_state["triagem_ultima_categoria"] = _CATS[0]
    _cat_idx = _CATS.index(st.session_state["triagem_ultima_categoria"]) \
        if st.session_state["triagem_ultima_categoria"] in _CATS else 0

    with st.form("form_triagem", clear_on_submit=False):
        st.markdown("#### Dados do produto")
        col1, col2 = st.columns(2)
        nome_comercial = col1.text_input("Nome comercial")
        categoria = col2.selectbox(
            "Categoria no ML", _CATS, index=_cat_idx, key="triagem_categoria"
        )

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

        st.markdown("#### Foto do produto")
        st.caption(
            "Envie uma foto de referência do produto (frente, ângulo limpo). "
            "Ela será exibida no seletor de variante quando houver produtos com o mesmo nome, "
            "para ajudar o colaborador a identificar o produto correto."
        )
        foto_upload = st.file_uploader(
            "Foto de referência (opcional)",
            type=["jpg", "jpeg", "png", "webp"],
            key="triagem_foto_upload",
        )

        enviar = st.form_submit_button("Salvar Triagem", type="primary", use_container_width=True)

    if enviar:
        if not nome_comercial:
            st.warning("Preencha pelo menos o Nome comercial.")
            return

        # Salva a categoria escolhida para a próxima triagem
        st.session_state["triagem_ultima_categoria"] = categoria

        # Upload da foto para o Drive (se enviada)
        foto_drive_id = ""
        if foto_upload is not None:
            with st.spinner("Enviando foto para o Drive..."):
                imagem_bytes = foto_upload.read()
                ext = foto_upload.name.rsplit(".", 1)[-1].lower() if "." in foto_upload.name else "jpg"
                nome_arquivo = f"{nome_comercial.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}"
                file_id, err_foto = upload_foto_triagem(imagem_bytes, nome_arquivo)
                if err_foto:
                    st.warning(
                        f"⚠️ Não foi possível enviar a foto. A triagem será salva "
                        f"normalmente, mas sem a foto de referência.\n\n{err_foto}"
                    )
                else:
                    foto_drive_id = file_id

        dados = {
            "nome_comercial": nome_comercial, "categoria": categoria,
            "material": material, "variacao_cores": variacao_cores, "medidas": medidas, "peso": peso,
            "caracteristicas": caracteristicas, "diferenciais": diferenciais, "uso": uso,
            "termos_busca": termos_busca, "termos_evitar": termos_evitar,
            "foto_drive_id": foto_drive_id,
        }
        try:
            with st.spinner("Salvando..."):
                salvar_triagem(usuario_logado, dados)
            import atividades
            atividades.registrar_atividade(usuario_logado, "Triagem de Produto", nome_comercial, categoria)
            if foto_drive_id:
                st.success(f"Triagem de '{nome_comercial}' salva com foto! ✅")
            else:
                st.success(f"Triagem de '{nome_comercial}' salva!")
        except RuntimeError as e:
            st.error(str(e))

    st.markdown("---")
    st.markdown("#### Buscar triagem existente")
    nome_busca = st.text_input("Digite o nome comercial pra ver a triagem já salva", key="busca_nome")
    if nome_busca:
        encontrada = buscar_triagem_por_nome(nome_busca)
        if encontrada:
            st.json(encontrada)
        else:
            st.info("Nenhuma triagem encontrada com esse nome ainda.")
