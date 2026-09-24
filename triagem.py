import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
from params_oficiais import ML_COMISSAO_POR_CATEGORIA

import planilha as _plan
# Nome vindo do ambiente: producao usa o padrao, homologacao usa a copia.
PLANILHA_NOME = _plan.nome()
ABA_NOME = "triagens"

COLUNAS = [
    # `id` PRIMEIRO, e por isso ele existe: sem identificador não se diz QUAL
    # linha editar ou apagar. A alternativa era o número da linha na planilha —
    # e ele é frágil: `carregar_triagens` é cacheada e `get_all_records` não
    # devolve o número da linha, então quem apagasse uma linha à mão na
    # planilha faria o índice guardado apontar para outra. É a mesma classe de
    # defeito de "escolher o item pelo texto da tela", que já custou caro aqui.
    #
    # `cheques.py` já usa este padrão (lá a FOLHA é a identidade). As linhas
    # antigas nasceram sem id; `_id_novo` preenche a primeira vez que a linha
    # é editada, e quem não tem continua sendo lido normalmente.
    "id",
    "data_hora", "usuario", "nome_comercial", "categoria", "material", "variacao_cores",
    "medidas", "peso", "caracteristicas", "diferenciais", "uso",
    "termos_busca", "termos_evitar", "foto_drive_id",
]


# Reutiliza a conexao entre reruns. Sem isso cada chamada refazia
# from_service_account_info + gspread.authorize + open() + worksheet() —
# quatro idas a rede antes de ler o primeiro dado, por modulo, a cada rerun.
def _crono(rotulo, seg, detalhe=""):
    """Registra quanto custou uma ida a planilha. Nunca derruba a leitura."""
    try:
        import cronometro
        cronometro.marcar(rotulo, seg, detalhe)
    except Exception:
        pass


def _cliente():
    """Cliente gspread compartilhado (ver sheets.py).

    Era um bloco proprio de credencial + authorize, identico em nove
    modulos: nove trocas de token por processo, todas no cold start.
    """
    import sheets as _sh
    return _sh.cliente()


@st.cache_resource
def _aba():
    # A planilha e aberta uma vez por processo em sheets.py. Aqui cada
    # modulo abria a sua, e abrir por nome custa uma varredura do Drive.
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        aba = planilha.worksheet(ABA_NOME)
        # Reconcilia o cabecalho, como atividades.py ja fazia.
        #
        # A aba foi criada antes de foto_drive_id existir. A linha gravada passou
        # a ter 14 valores para 13 cabecalhos, e o id da foto no Drive caia numa
        # coluna sem nome — get_all_records devolvia {"": "1c3GYCn..."}. Quem
        # lesse por foto_drive_id nao achava nada, e a miniatura da variante
        # nunca aparecia.
        cabecalho = aba.row_values(1)
        # Compara normalizado, como em atividades.py: "Peso" ou "peso " nao
        # batia e uma coluna repetida e vazia nascia no fim, apagando a boa na
        # leitura.
        _norm = lambda c: str(c).strip().lower()
        vistos = {_norm(c) for c in cabecalho}
        for col in COLUNAS:
            if _norm(col) not in vistos:
                aba.add_cols(1)
                aba.update_cell(1, len(cabecalho) + 1, col)
                cabecalho.append(col)
                vistos.add(_norm(col))
        return aba
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
        # Por NOME de coluna, nao por posicao — foi o que fez o peso se perder
        # no historico de atividades. Aqui a armadilha e a mesma.
        valores = dict(dados or {})
        valores["data_hora"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        valores["usuario"] = usuario
        # Toda triagem nova nasce com identificador. É ele que a edição e o
        # apagar usam depois para dizer QUAL linha.
        valores.setdefault("id", _id_novo())
        try:
            cabecalho_real = aba.row_values(1) or list(COLUNAS)
        except Exception:
            cabecalho_real = list(COLUNAS)
        linha = [valores.get(str(c).strip().lower(), "") for c in cabecalho_real]
        aba.append_row(linha, value_input_option="RAW")
        carregar_triagens.clear()
    except Exception as e:
        raise RuntimeError(f"Não consegui salvar a triagem no Google Sheets: {e}") from e


def _id_novo():
    """Identificador estável de uma triagem. Não depende do conteúdo.

    De propósito: se o id saísse do nome, renomear o produto mudaria a
    identidade da linha e a edição viraria uma linha nova — que é exatamente o
    defeito que esta função existe para acabar.
    """
    import uuid
    return uuid.uuid4().hex[:12]


def id_da_linha(linha):
    """O id de uma triagem já gravada, ou "" quando ela é das antigas."""
    return str((linha or {}).get("id", "") or "").strip()


def nome_ja_usado(nome_comercial, ignorando_id=""):
    """Já existe triagem com este nome? Devolve a linha achada, ou None.

    A REGRA É POR NOME, E FOI ESCOLHA DO DONO
    -----------------------------------------
    Foi posta ao lado da alternativa — barrar só quando repetem nome, medidas,
    peso e cores, deixando conviver "Caixa de relógio 5 posições" e "10
    posições" como variantes — e ele escolheu barrar por NOME, sabendo o que
    custa: variantes novas passam a se diferenciar no próprio nome.

    As variantes que já estão gravadas continuam onde estão, e
    `widget_seletor_produto` segue mostrando todas. O bloqueio vale para
    cadastro novo; ele não apaga nada.

    `ignorando_id` é a própria linha, ao editar: salvar sem mexer no nome não
    pode ser recusado por causa de si mesma.
    """
    alvo = _normalizar(str(nome_comercial)).strip()
    if not alvo:
        return None
    df = carregar_triagens()
    if df.empty or "nome_comercial" not in df.columns:
        return None
    nomes = df["nome_comercial"].astype(str).apply(_normalizar).str.strip()
    iguais = df[nomes == alvo]
    if iguais.empty:
        return None
    if ignorando_id:
        iguais = iguais[iguais.get("id", "").astype(str).str.strip()
                        != str(ignorando_id).strip()]
        if iguais.empty:
            return None
    return iguais.iloc[-1].to_dict()


def _linha_na_planilha(aba, id_triagem):
    """O número da linha daquele id na planilha. None quando não está lá.

    Lê a coluna do id de uma vez e procura nela, em vez de baixar a aba
    inteira: editar uma triagem não pode custar a leitura de todas.
    """
    cab = aba.row_values(1) or []
    norm = [str(c).strip().lower() for c in cab]
    if "id" not in norm:
        return None
    coluna = norm.index("id") + 1
    valores = aba.col_values(coluna)
    alvo = str(id_triagem).strip()
    for i, v in enumerate(valores[1:], start=2):     # pula o cabeçalho
        if str(v).strip() == alvo:
            return i
    return None


def preencher_identificadores_antigos():
    """Dá identificador às triagens gravadas antes de ele existir. (n, erro).

    POR QUE ISTO EXISTE
    -------------------
    Uma triagem sem `id` nao pode ser editada: `_editar_ou_apagar` recusa, e
    `atualizar_triagem` tambem — ela precisa do id para achar a linha. A tela
    dizia "cadastre-a de novo com outro nome, ou me avise para preencher os
    identificadores das antigas de uma vez".

    Cadastrar de novo com outro nome e pior do que parece: a busca devolve a
    mais recente, e passariam a existir duas triagens do mesmo produto
    discordando — o defeito que `nome_ja_usado` existe para impedir.

    E a segunda saida, a que a propria mensagem oferecia, nunca tinha sido
    construida. Resultado real: o album estava gravado com "weri-o" em dois
    campos, o conserto era digitar, e a tela nao deixava digitar.

    O QUE ELA NAO FAZ
    -----------------
    Nao toca em linha que JA tem id, nem em linha sem nome comercial — linha
    em branco no fim da aba nao vira cadastro. So preenche vazio.
    """
    try:
        aba = _aba()
        cab = aba.row_values(1) or []
        norm = [str(c).strip().lower() for c in cab]
        if "id" not in norm:
            return 0, "A aba não tem coluna `id`. Avise o Léo."
        col_id = norm.index("id") + 1
        col_nome = (norm.index("nome_comercial") + 1
                    if "nome_comercial" in norm else 0)

        ids = aba.col_values(col_id)
        nomes = aba.col_values(col_nome) if col_nome else []

        def _valor(lista, i):
            return str(lista[i - 1]).strip() if 0 < i <= len(lista) else ""

        # Quantas linhas a aba tem de fato: a coluna do id pode ser mais curta
        # que a do nome justamente porque o id falta.
        ultima = max(len(ids), len(nomes))
        celulas = []
        for linha_n in range(2, ultima + 1):
            if _valor(ids, linha_n):
                continue                      # ja tem id: nao se toca
            if col_nome and not _valor(nomes, linha_n):
                continue                      # linha sem produto: nao e cadastro
            celulas.append((linha_n, _id_novo()))

        if not celulas:
            return 0, ""

        import gspread.utils as _gu
        # A LETRA DA COLUNA PODE TER DUAS. `rowcol_to_a1(1, 28)` devolve
        # "AB1", e pegar `[0]` dali daria "A" — ou seja, o identificador
        # gravado na coluna errada, por cima do dado de outra pessoa. Hoje o
        # id e a coluna 1 e ninguem veria; no dia em que alguem reordenar a
        # aba, veria de uma vez so.
        letra = _gu.rowcol_to_a1(1, col_id).rstrip("0123456789")
        aba.batch_update([
            {"range": f"{letra}{n}", "values": [[v]]} for n, v in celulas
        ])
        return len(celulas), ""
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def atualizar_triagem(id_triagem, dados, usuario=""):
    """Reescreve UMA triagem. (ok, erro).

    `data_hora` NÃO é tocada de propósito. Ela é o critério de "mais recente"
    em `buscar_triagem_por_nome` (.iloc[-1]) e em `buscar_triagens_por_trecho`
    (keep="last"). Carimbar a edição com a hora de agora faria corrigir um
    produto antigo jogá-lo na frente dos novos — a correção mudaria de lugar
    coisas que ninguém pediu para mexer.
    """
    if not str(id_triagem or "").strip():
        return False, "Triagem sem identificador — não dá para saber qual editar."
    try:
        aba = _aba()
        linha_n = _linha_na_planilha(aba, id_triagem)
        if not linha_n:
            return False, "Não achei essa triagem na planilha. Recarregue a tela."
        cab = aba.row_values(1) or list(COLUNAS)
        atual = aba.row_values(linha_n) or []
        atual += [""] * (len(cab) - len(atual))
        valores = dict(dados or {})
        novo = []
        for i, c in enumerate(cab):
            chave = str(c).strip().lower()
            if chave in valores:
                novo.append(valores[chave])
            elif chave == "usuario" and usuario:
                novo.append(usuario)
            else:
                novo.append(atual[i] if i < len(atual) else "")
        # O intervalo sai do gspread, e não de `chr(64 + n)`: essa conta
        # quebra na coluna 27, onde o Excel passa a usar AA. A aba já tem 15
        # colunas e cresce sozinha em `_aba()` — contar com "nunca chega a 27"
        # é apostar que ninguém vai acrescentar campo.
        from gspread.utils import rowcol_to_a1 as _a1
        aba.update([novo], f"{_a1(linha_n, 1)}:{_a1(linha_n, len(cab))}")
        carregar_triagens.clear()
        return True, ""
    except Exception as e:
        return False, f"Não consegui salvar a triagem: {e}"


def apagar_triagem(id_triagem):
    """Remove UMA triagem. (ok, erro).

    Quem consome a triagem: `imagem.py`, `descricao.py`, `tit_ml.py`,
    `palavras_chave.py`, `video.py` e `ferramentas_chat.py`. Apagar tira a
    fonte de dados desses seis para aquele produto — aceitável quando é
    duplicata, e por isso a tela mostra o que vai sumir antes de perguntar.
    """
    if not str(id_triagem or "").strip():
        return False, "Triagem sem identificador — não dá para saber qual apagar."
    try:
        aba = _aba()
        linha_n = _linha_na_planilha(aba, id_triagem)
        if not linha_n:
            return False, "Não achei essa triagem na planilha. Recarregue a tela."
        aba.delete_rows(linha_n)
        carregar_triagens.clear()
        return True, ""
    except Exception as e:
        return False, f"Não consegui apagar a triagem: {e}"


@st.cache_data(ttl=600)
def carregar_triagens():
    try:
        aba = _aba()
        import time as _t_crono
        _t0_crono = _t_crono.perf_counter()
        registros = aba.get_all_records(value_render_option="UNFORMATTED_VALUE")
        _crono("Planilha: triagens", _t_crono.perf_counter() - _t0_crono,
               f"{len(registros)} linhas")
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
    # DATA ORDENADA COMO DATA, E NÃO COMO TEXTO.
    #
    # `data_hora` é gravada "%d/%m/%Y %H:%M" (triagem.py, salvar_triagem). Em
    # string, "31/12/2025" vem DEPOIS de "01/01/2026", porque a comparação
    # começa pelo dia. Como o `keep="last"` logo abaixo escolhe a "mais
    # recente" de cada variante por esta ordem, a mais recente podia ser a mais
    # antiga — e virar o mês inteiro sem ninguém notar.
    filtradas = filtradas.sort_values(
        "data_hora", key=lambda col: pd.to_datetime(
            col, format="%d/%m/%Y %H:%M", errors="coerce"))
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
    alvo = _normalizar(str(nome_comercial)).strip()
    if not alvo:
        return None
    # Exato primeiro; sem exato, por pedaco do nome.
    #
    # So a igualdade exata obrigava a digitar as 27 letras de "TESTE Caneca
    # Ceramica 350ml". Quem buscava "TESTE Caneca" ouvia que nao existia e
    # preenchia tudo de novo — triagem duplicada.
    nomes = df["nome_comercial"].astype(str).apply(_normalizar).str.strip()
    linhas = df[nomes == alvo]
    if linhas.empty:
        linhas = df[nomes.str.contains(alvo, na=False, regex=False)]
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

    # Semeia com o produto em que a pessoa ja esta trabalhando, para nao
    # redigitar o mesmo nome em cinco abas. ANTES do widget: escrever na chave
    # depois de ele existir derruba a tela.
    import contexto_produto as _ctx
    _ctx.semear(busca_key)

    busca = st.text_input(label, key=busca_key)

    # Limpa seleção sempre que o texto de busca muda
    if st.session_state.get(busca_prev_key) != busca:
        st.session_state[sel_key] = None
        st.session_state[busca_prev_key] = busca

    if not busca:
        return None, None

    encontrados = buscar_triagens_por_trecho(busca)

    if not encontrados:
        _ctx.definir(busca)
        return (
            {"nome_comercial": busca},
            ("warning", "Nenhuma triagem encontrada para esse produto ainda — preencha os campos abaixo.")
        )

    if len(encontrados) == 1:
        _ctx.definir(encontrados[0].get("nome_comercial", busca), dados=encontrados[0])
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
        _ctx.definir(v.get("nome_comercial", busca), dados=v)
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
            _ctx.definir(candidatos[0].get("nome_comercial", busca), dados=candidatos[0])
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

# Campos do formulário de triagem que devem ser zerados após salvar.
# A categoria fica de fora de propósito: o colaborador costuma cadastrar
# vários produtos da mesma categoria em sequência.
_CAMPOS_FORM_TRIAGEM = [
    "triagem_nome_comercial", "triagem_material", "triagem_variacao_cores",
    "triagem_medidas", "triagem_peso", "triagem_uso", "triagem_caracteristicas",
    "triagem_diferenciais", "triagem_termos_busca", "triagem_termos_evitar",
    "triagem_foto_upload",
]


def _limpar_form_triagem():
    for _k in _CAMPOS_FORM_TRIAGEM:
        st.session_state.pop(_k, None)


_ROTULOS_TRIAGEM = [
    ("nome_comercial", "Nome comercial"), ("categoria", "Categoria"),
    ("material", "Material"), ("variacao_cores", "Cores"),
    ("medidas", "Medidas"), ("peso", "Peso"), ("uso", "Uso / ocasião"),
    ("caracteristicas", "Características"), ("diferenciais", "Diferenciais"),
    ("termos_busca", "Termos de busca"), ("termos_evitar", "Termos a evitar"),
    ("usuario", "Cadastrada por"), ("data_hora", "Quando"),
]


def _cartao_triagem(dados):
    """Mostra a triagem como cartao legivel, nao como JSON cru.

    st.json despejava a linha inteira da planilha, com nome de coluna e o id do
    arquivo no Drive no meio. Quem le e o colaborador conferindo o produto, nao
    quem depura a planilha.
    """
    foto = str(dados.get("foto_drive_id", "")).strip()
    col_foto, col_dados = st.columns([1, 4]) if foto else (None, st.container())
    if foto:
        with col_foto:
            st.image(url_thumbnail(foto, 160), use_container_width=True)
    with col_dados:
        st.markdown(f"#### {dados.get('nome_comercial', '(sem nome)')}")
        linhas = []
        for chave, rotulo in _ROTULOS_TRIAGEM:
            if chave == "nome_comercial":
                continue
            valor = str(dados.get(chave, "") or "").strip()
            if valor:
                linhas.append(f"**{rotulo}:** {valor}")
        st.markdown("  \n".join(linhas) if linhas
                    else "_Só o nome foi preenchido nesta triagem._")
        _vazios = [rot for ch, rot in _ROTULOS_TRIAGEM
                   if ch not in ("usuario", "data_hora", "nome_comercial")
                   and not str(dados.get(ch, "") or "").strip()]
        if _vazios:
            st.caption("Em branco: " + ", ".join(_vazios))


def pagina_triagem(usuario_logado):
    st.subheader("Triagem do Produto")
    st.caption("Preenche uma vez por produto — essa informação alimenta palavras-chave, título e descrição.")

    # Mensagem de sucesso vinda do rerun que limpou o formulário
    # As mensagens aparecem no TOPO, e cada uma so uma vez.
    #
    # O aviso de validacao era escrito onde o codigo roda — depois do
    # formulario, ou seja, no rodape. Salvar com o formulario vazio fazia a
    # pagina saltar para o topo e "nao acontecer nada": a resposta estava la
    # embaixo, fora da tela. O pop garante que a mensagem some na interacao
    # seguinte, em vez de continuar na tela depois de resolvida.
    _msg_ok = st.session_state.pop("triagem_msg_ok", "")
    if _msg_ok:
        st.success(_msg_ok)
    _msg_erro = st.session_state.pop("triagem_msg_erro", "")
    if _msg_erro:
        st.warning(_msg_erro)

    # ── BUSCAR ANTES DE CADASTRAR ─────────────────────────────────────────
    #
    # A busca morava no rodape, depois do formulario inteiro e do botao
    # Salvar. Quem chegava para CONFERIR uma triagem ja salva tinha de rolar
    # a tela toda por cima de um formulario em branco para achar o campo — e
    # quem nao rolava cadastrava de novo, criando a segunda triagem do mesmo
    # produto que a busca depois devolvia pela data.
    #
    # Pedido do dono: "o campo de pesquisar uma triagem existente precisa
    # estar no topo".
    st.markdown("#### Buscar triagem existente")
    nome_busca = st.text_input(
        "Digite o nome comercial pra ver a triagem já salva", key="busca_nome")
    if nome_busca:
        encontrada = buscar_triagem_por_nome(nome_busca)
        if encontrada:
            _cartao_triagem(encontrada)
            _editar_ou_apagar(encontrada, usuario_logado)
        else:
            st.info("Nenhuma triagem encontrada com esse nome ainda.")
    st.markdown("---")

    # Persiste a última categoria selecionada entre reruns
    _CATS = sorted(ML_COMISSAO_POR_CATEGORIA.keys())
    if "triagem_ultima_categoria" not in st.session_state:
        st.session_state["triagem_ultima_categoria"] = _CATS[0]
    _cat_idx = _CATS.index(st.session_state["triagem_ultima_categoria"]) \
        if st.session_state["triagem_ultima_categoria"] in _CATS else 0

    with st.form("form_triagem", clear_on_submit=False):
        st.markdown("#### Dados do produto")
        col1, col2 = st.columns(2)
        # Todo campo tem key= de propósito: sem key, o Streamlit identifica o
        # widget pela posição na árvore. Qualquer remontagem da navegação
        # (troca de seção, mudança de perfil) gera IDs novos e o que já foi
        # digitado se perde. Com key, o valor fica no session_state e sobrevive.
        nome_comercial = col1.text_input("Nome comercial", key="triagem_nome_comercial")
        categoria = col2.selectbox(
            "Categoria no ML", _CATS, index=_cat_idx, key="triagem_categoria"
        )

        col1, col2 = st.columns(2)
        material = col1.text_input("Material", placeholder="ex: Plástico e Metal (o predominante primeiro)", key="triagem_material")
        variacao_cores = col2.text_input("Variação de cores", placeholder="ex: Preto, Vermelho, Azul (só uma se não tiver variação)", key="triagem_variacao_cores")

        col1, col2 = st.columns(2)
        medidas = col1.text_input("Medidas (AxLxP, cm)", placeholder="ex: 33x33x6", key="triagem_medidas")
        peso = col2.text_input("Peso", placeholder="ex: 700g", key="triagem_peso")

        uso = st.text_input("Uso / ocasião (ex: presente, uso pessoal, infantil)", key="triagem_uso")
        caracteristicas = st.text_area("Características técnicas (specs além de material/cor)", key="triagem_caracteristicas")
        diferenciais = st.text_area("Diferenciais (o que separa esse produto de um genérico)", key="triagem_diferenciais")

        st.markdown("#### Opcional")
        termos_busca = st.text_input("Termos que o cliente já costuma buscar (se souber)", key="triagem_termos_busca")
        termos_evitar = st.text_input("Termos a evitar (ex: marca registrada)", key="triagem_termos_evitar")

        st.markdown("#### Foto do produto")
        st.caption(
            "Envie uma foto de referência do produto (frente, ângulo limpo). "
            "Ela será exibida no seletor de variante quando houver produtos com o mesmo nome, "
            "para ajudar o colaborador a identificar o produto correto."
        )
        foto_upload = st.file_uploader(
            "Foto de referência (opcional)",
            type=None,
            key="triagem_foto_upload",
        )

        enviar = st.form_submit_button("Salvar Triagem", type="primary", use_container_width=True)

    if enviar:
        if not nome_comercial:
            st.session_state["triagem_msg_erro"] = (
                "Preencha pelo menos o **Nome comercial** para salvar a triagem.")
            st.rerun()

        # NOME REPETIDO NÃO ENTRA — regra escolhida pelo dono em 21/09.
        #
        # Antes, cada "Salvar" fazia uma linha nova. Corrigir um erro de
        # digitação criava uma segunda triagem do mesmo produto, e a busca
        # passava a devolver a mais recente das duas — sem ninguém saber que
        # havia duas.
        _ja = nome_ja_usado(nome_comercial)
        if _ja is not None:
            st.session_state["triagem_msg_erro"] = (
                f"Já existe uma triagem chamada **{nome_comercial}** "
                f"(cadastrada por {_ja.get('usuario') or '—'} em "
                f"{_ja.get('data_hora') or '—'}). Para mudar alguma coisa, use "
                f"**Buscar triagem existente**, no topo desta aba, e edite aquela — "
                f"salvar de novo aqui criaria uma segunda.")
            st.rerun()

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

            # Só limpa o formulário DEPOIS de a gravação ter dado certo.
            # Se falhar, o que foi digitado continua na tela para o
            # colaborador tentar de novo sem redigitar nada.
            st.session_state["triagem_msg_ok"] = (
                f"Triagem de '{nome_comercial}' salva com foto! ✅" if foto_drive_id
                else f"Triagem de '{nome_comercial}' salva!"
            )
            _limpar_form_triagem()
            st.rerun()
        except RuntimeError as e:
            st.error(str(e))
            st.info("Nada do que você preencheu foi perdido — corrija e tente salvar de novo.")



# ── Editar e apagar ──────────────────────────────────────────────────────────
# Antes não havia nem um nem outro: cada "Salvar" era uma linha nova, e o jeito
# de corrigir um erro de digitação era cadastrar tudo de novo. Ficavam duas
# triagens do mesmo produto, e a busca devolvia a mais recente das duas.

_EDITAVEIS = [
    ("nome_comercial", "Nome comercial", "texto"),
    ("material", "Material", "texto"),
    ("variacao_cores", "Variação de cores", "texto"),
    ("medidas", "Medidas (AxLxP, cm)", "texto"),
    ("peso", "Peso", "texto"),
    ("uso", "Uso / ocasião", "texto"),
    ("caracteristicas", "Características técnicas", "area"),
    ("diferenciais", "Diferenciais", "area"),
    ("termos_busca", "Termos que o cliente busca", "texto"),
    ("termos_evitar", "Termos a evitar", "texto"),
]


def _editar_ou_apagar(dados, usuario_logado):
    _id = id_da_linha(dados)
    if not _id:
        # A MENSAGEM PROMETIA UMA SAIDA QUE NAO EXISTIA.
        #
        # Ela dizia "me avise para preencher os identificadores das antigas de
        # uma vez" — e nao havia como fazer isso. Quem precisava corrigir um
        # dado numa triagem antiga ficava sem caminho: o conserto era digitar,
        # e a tela nao deixava digitar. Um album gravado com "weri-o" em dois
        # campos chegou assim aos oito prompts por causa disto.
        st.warning(
            "Esta triagem foi cadastrada antes de as triagens terem "
            "identificador, e por isso não dá para editá-la ainda.\n\n"
            "O botão abaixo dá identificador a **todas** as antigas de uma "
            "vez. Ele não altera nenhum dado do produto — só preenche a "
            "coluna que faltava — e não toca nas que já têm.")
        if st.button("🔑 Dar identificador às triagens antigas",
                     key=f"btn_ids_{abs(hash(str(dados.get('nome_comercial'))))}"):
            with st.spinner("Preenchendo os identificadores…"):
                quantas, erro_ids = preencher_identificadores_antigos()
            if erro_ids:
                st.error(f"Não consegui: {erro_ids}")
            elif quantas:
                st.success(
                    f"{quantas} triagem(ns) ganharam identificador. "
                    "Busque o produto de novo — agora ele abre para edição.")
                st.cache_data.clear()
            else:
                st.info("Nenhuma triagem estava sem identificador. "
                        "Recarregue a tela e busque de novo.")
        return

    with st.expander("✏️ Editar esta triagem"):
        # Formulário, e não botões soltos: um clique que tira o foco de uma
        # célula em edição é consumido pelo rerun, e o colaborador clica duas
        # vezes sem entender por quê.
        with st.form(f"form_edit_{_id}"):
            _novos = {}
            _cats = sorted(ML_COMISSAO_POR_CATEGORIA.keys())
            _cat_atual = str(dados.get("categoria", "") or "")
            c1, c2 = st.columns(2)
            _novos["nome_comercial"] = c1.text_input(
                "Nome comercial", value=str(dados.get("nome_comercial", "") or ""),
                key=f"ed_nome_{_id}")
            _novos["categoria"] = c2.selectbox(
                "Categoria no ML", _cats,
                index=_cats.index(_cat_atual) if _cat_atual in _cats else 0,
                key=f"ed_cat_{_id}")
            for _ch, _rot, _tipo in _EDITAVEIS:
                if _ch == "nome_comercial":
                    continue
                _fn = st.text_area if _tipo == "area" else st.text_input
                _novos[_ch] = _fn(_rot, value=str(dados.get(_ch, "") or ""),
                                  key=f"ed_{_ch}_{_id}")
            _salvar = st.form_submit_button("💾 Salvar alterações",
                                            type="primary",
                                            use_container_width=True)

        if _salvar:
            if not str(_novos["nome_comercial"]).strip():
                st.error("O nome comercial não pode ficar vazio.")
            else:
                # O nome pode ter mudado — e o novo não pode colidir com outra
                # triagem. `ignorando_id` é esta linha: salvar sem mexer no
                # nome não pode ser recusado por causa de si mesma.
                _colide = nome_ja_usado(_novos["nome_comercial"],
                                        ignorando_id=_id)
                if _colide is not None:
                    st.error(
                        f"Já existe outra triagem chamada "
                        f"**{_novos['nome_comercial']}**. Escolha outro nome.")
                else:
                    _ok, _erro = atualizar_triagem(_id, _novos, usuario_logado)
                    if _ok:
                        st.success("Triagem atualizada! ✅")
                        st.rerun()
                    else:
                        st.error(_erro)

    with st.expander("🗑️ Apagar esta triagem"):
        # O que some, dito ANTES de perguntar. Seis telas leem a triagem —
        # imagem, descrição, título, palavras-chave, vídeo e o chat — e o
        # colaborador que apaga a errada só descobre quando uma delas não
        # acha mais o produto.
        st.warning(
            f"**{dados.get('nome_comercial', '(sem nome)')}** sai da aba "
            "`triagens` e deixa de alimentar Imagem, Descrição, Título, "
            "Palavras-chave, Vídeo e o Assistente. Não tem desfazer.")
        _confirma = st.text_input(
            "Para confirmar, escreva APAGAR", key=f"del_conf_{_id}")
        if st.button("Apagar definitivamente", key=f"del_btn_{_id}",
                     disabled=_confirma.strip().upper() != "APAGAR"):
            _ok, _erro = apagar_triagem(_id)
            if _ok:
                st.success("Triagem apagada.")
                st.rerun()
            else:
                st.error(_erro)


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    _BASE = pd.DataFrame([
        {"id": "aaa", "nome_comercial": "Caixa de relógio 5 posições",
         "medidas": "20x10x8", "peso": "700g", "variacao_cores": "Preto",
         "data_hora": "31/12/2025 10:00", "usuario": "leo"},
        {"id": "bbb", "nome_comercial": "Caixa de relógio 5 posições",
         "medidas": "20x10x8", "peso": "700g", "variacao_cores": "Preto",
         "data_hora": "01/01/2026 09:00", "usuario": "leo"},
        {"id": "ccc", "nome_comercial": "Álbum de fotos 200",
         "medidas": "33x33x6", "peso": "900g", "variacao_cores": "Azul",
         "data_hora": "15/03/2026 08:00", "usuario": "bru"},
    ])
    globals()["carregar_triagens"] = lambda: _BASE

    # ── Nome repetido barra (opção B, escolhida pelo dono) ───────────────
    ok("nome ja usado e encontrado",
       (nome_ja_usado("Caixa de relógio 5 posições") or {}).get("id") == "bbb")
    ok("acento e caixa nao escapam da regra",
       nome_ja_usado("ALBUM DE FOTOS 200") is not None)
    ok("nome novo passa", nome_ja_usado("Bengala de metal") is None)
    ok("nome vazio nao acusa nada", nome_ja_usado("   ") is None)

    # Editar a propria linha sem mexer no nome NAO pode ser recusado por
    # causa de si mesma — e com duas gemeas, a outra ainda barra.
    ok("a propria linha nao se barra",
       nome_ja_usado("Álbum de fotos 200", ignorando_id="ccc") is None)
    ok("mas a gemea de outra linha continua barrando",
       nome_ja_usado("Caixa de relógio 5 posições",
                     ignorando_id="bbb") is not None)

    # ── A data ordenada como DATA, e nao como texto ──────────────────────
    # "31/12/2025" vem DEPOIS de "01/01/2026" em ordem alfabetica: a "mais
    # recente" de cada variante era a mais antiga, e virava o mes.
    _achadas = buscar_triagens_por_trecho("caixa de relogio")
    ok("uma entrada por variante", len(_achadas) == 1)
    ok("e a mais recente e a de 2026, nao a de 31/12/2025",
       _achadas and _achadas[0]["id"] == "bbb")

    # ── O identificador ──────────────────────────────────────────────────
    ok("id novo nao repete", _id_novo() != _id_novo())
    ok("id novo tem tamanho fixo", len(_id_novo()) == 12)
    ok("linha antiga sem id devolve vazio", id_da_linha({"nome_comercial": "x"}) == "")
    ok("e a linha com id devolve o id", id_da_linha({"id": " abc "}) == "abc")

    ok("COLUNAS comeca pelo id", COLUNAS[0] == "id")

    # Sem identificador, editar e apagar recusam em vez de mexer na linha
    # errada — que e o unico jeito de errar aqui que nao tem volta.
    ok("editar sem id recusa", atualizar_triagem("", {"nome_comercial": "x"})[0] is False)
    ok("apagar sem id recusa", apagar_triagem("")[0] is False)

    # ── PREENCHER OS IDs DAS ANTIGAS ─────────────────────────────────────
    #
    # Esta funcao ESCREVE na planilha, e escrever na coluna errada nao tem
    # volta. Entao ela e conferida contra uma aba de mentira antes de existir
    # de verdade: so pode tocar em linha SEM id, e so na coluna do id.
    class _AbaFalsa:
        def __init__(self, cab, linhas):
            self.cab, self.linhas, self.escritas = cab, linhas, []

        def row_values(self, n):
            return self.cab if n == 1 else []

        def col_values(self, c):
            return [self.cab[c - 1]] + [l[c - 1] for l in self.linhas]

        def batch_update(self, pedidos):
            self.escritas = [(p["range"], p["values"][0][0]) for p in pedidos]

    _falsa = _AbaFalsa(
        ["id", "data_hora", "nome_comercial"],
        [["aaa", "01/01/2026", "Com id"],     # linha 2: nao se toca
         ["",    "02/01/2026", "Sem id"],     # linha 3: preenche
         ["",    "",           ""]])          # linha 4: vazia, nao e cadastro
    globals()["_aba"] = lambda: _falsa
    _n, _e = preencher_identificadores_antigos()
    ok("so a linha sem id foi preenchida", (_n, _e) == (1, ""))
    ok("e foi na linha 3, na coluna do id",
       len(_falsa.escritas) == 1 and _falsa.escritas[0][0] == "A3")
    ok("o id gravado tem o tamanho de um id",
       _falsa.escritas and len(_falsa.escritas[0][1]) == 12)

    # Rodar de novo nao regrava nada: a linha 3 ja teria id na planilha real.
    _falsa.linhas[1][0] = _falsa.escritas[0][1]
    ok("segunda passada nao mexe em nada",
       preencher_identificadores_antigos() == (0, ""))

    # A COLUNA DO ID PODE PASSAR DO Z. `rowcol_to_a1(1, 28)` e "AB1": pegar a
    # primeira letra daria "A" — id gravado por cima da coluna de outro dado.
    _larga = _AbaFalsa(
        ["c%d" % i for i in range(1, 27)] + ["nome_comercial", "id"],
        [["x"] * 26 + ["Produto", ""]])
    globals()["_aba"] = lambda: _larga
    preencher_identificadores_antigos()
    ok("coluna depois do Z nao vira coluna A",
       _larga.escritas and _larga.escritas[0][0] == "AB2")

    # Aba sem coluna de id nao e adivinhada: avisa e nao escreve.
    _sem = _AbaFalsa(["data_hora", "nome_comercial"], [["01/01", "Produto"]])
    globals()["_aba"] = lambda: _sem
    _n2, _e2 = preencher_identificadores_antigos()
    ok("aba sem coluna de id avisa e nao escreve",
       _n2 == 0 and "id" in _e2 and _sem.escritas == [])

    print("\nfalhas:", falhas)
