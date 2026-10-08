import json
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
from params_oficiais import ML_COMISSAO_POR_CATEGORIA

import planilha as _plan
import placar_core as _pc_br   # a porta unica da hora de Brasilia
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
    # AS VARIACOES DO MESMO PRODUTO — pedido do dono, 07/10.
    #
    # Mesma medida, mesmo material, mesmo peso; muda a cor ou a estampa. Elas
    # moram DENTRO da linha do produto, e nao em linhas separadas, porque
    # separar duplicaria material, medidas e peso — e campo duplicado passa a
    # discordar, que e a forma de retrabalho mais cara desta base.
    #
    # JSON numa celula: [{"nome": "Camuflado", "fotos": ["id1", "id2"]}, ...].
    # Vinte variacoes com dez fotos cada dao ~7 mil caracteres; o limite de
    # uma celula do Sheets e 50 mil.
    "variacoes",
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


def baixar_foto_triagem(foto_drive_id):
    """Os bytes de uma foto de triagem. (bytes, erro).

    IRMÃ DE `upload_foto_triagem`, e por isso mora aqui: quem guarda a foto da
    triagem é este módulo, e quem a lê de volta tem de ser ele também. A aba
    Imagem precisa dos BYTES das fotos de variação para alimentar o gerador —
    `url_thumbnail` devolve URL para o navegador desenhar, que é outra coisa.
    """
    import gdrive
    return gdrive.baixar(foto_drive_id)


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
        valores["data_hora"] = _pc_br.agora_br().strftime("%d/%m/%Y %H:%M")
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


def variacoes_da_triagem(row):
    """As variacoes desta triagem: [{"nome": str, "fotos": [drive_id]}].

    PORTA UNICA DE LEITURA, e e por isso que ela existe: a celula guarda
    JSON, e cada leitor que fizesse o proprio `json.loads` teria o proprio
    jeito de errar. Hoje leem daqui a tela da triagem e a aba Imagem.

    TOLERANTE DE PROPOSITO. Linha antiga nao tem a coluna; celula vazia,
    JSON cortado ou formato inesperado devolvem lista vazia em vez de
    derrubar a tela — triagem sem variacao e o caso normal, nao um erro.
    """
    bruto = (row or {}).get("variacoes", "")
    if isinstance(bruto, list):
        itens = bruto
    else:
        texto = str(bruto or "").strip()
        if not texto:
            return []
        try:
            itens = json.loads(texto)
        except Exception:
            return []
    if not isinstance(itens, list):
        return []
    fora = []
    for it in itens:
        if not isinstance(it, dict):
            continue
        nome = str(it.get("nome", "") or "").strip()
        fotos = [str(f).strip() for f in (it.get("fotos") or [])
                 if str(f).strip()]
        # Variacao sem nome nao e variacao: ninguem consegue escolher nem
        # dizer na tela qual peca saiu de qual. Entra so o que da para usar.
        if nome:
            fora.append({"nome": nome, "fotos": fotos})
    return fora


def texto_das_variacoes(variacoes):
    """Os nomes das variacoes em uma linha: "Camuflado, Preto, Areia".

    E o que passa a alimentar a coluna `variacao_cores`, que antes era
    digitada a mao. O dono mandou tirar o campo em 07/10: "esse novo processo
    substituira ele".

    GRAVAR O DERIVADO E DE PROPOSITO, e nao duplicacao: seis telas ja leem
    `variacao_cores` (`imagem.py`, `descricao.py`, `tit_ml.py`,
    `palavras_chave.py`, `video.py`, `ferramentas_chat.py`), e a cor do
    produto alimenta a trava de cor do gerador. Parar de escrever a coluna
    tiraria a cor de todas elas de uma vez, em silencio. A fonte passa a ser
    uma so — os nomes das variacoes —, e a coluna continua sendo a mesma
    resposta de sempre para quem pergunta "que cores este produto tem?".
    """
    return ", ".join(v["nome"] for v in (variacoes or []) if v.get("nome"))


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
    "triagem_nome_comercial", "triagem_material",
    "triagem_medidas", "triagem_peso", "triagem_uso", "triagem_caracteristicas",
    "triagem_diferenciais", "triagem_termos_busca", "triagem_termos_evitar",
    "triagem_foto_upload",
]


# ── OS CAMPOS DE VARIACAO, QUE NASCEM E MORREM NA TELA ───────────────────
#
# O estado e uma LISTA DE IDS, e nao um contador. Com contador, remover a
# variacao 2 de quatro faria as de baixo subirem de indice — e as chaves dos
# widgets (`triagem_var_nome_3`) continuariam coladas no valor antigo: o nome
# da variacao 3 apareceria na linha da 2. E a mesma classe de defeito de
# "escolher o item pelo texto da tela", que esta base ja pagou.
#
# Com id proprio e estavel, remover uma nao mexe em nenhuma outra.
_VAR_IDS = "triagem_var_ids"
_VAR_SEQ = "triagem_var_seq"


def _ids_das_variacoes():
    return list(st.session_state.get(_VAR_IDS) or [])


def _abrir_variacao():
    """Mais um bloco de variacao na tela. Chamado pelo botao do dono."""
    _n = int(st.session_state.get(_VAR_SEQ, 0)) + 1
    st.session_state[_VAR_SEQ] = _n
    st.session_state[_VAR_IDS] = _ids_das_variacoes() + [f"v{_n}"]


def _fechar_variacao(vid):
    """Tira UM bloco e o que foi digitado nele. Os outros nao se mexem."""
    st.session_state[_VAR_IDS] = [i for i in _ids_das_variacoes() if i != vid]
    st.session_state.pop(f"triagem_var_nome_{vid}", None)
    st.session_state.pop(f"triagem_var_fotos_{vid}", None)


def _zerar_variacoes():
    """Produto novo comeca sem variacao nenhuma.

    SEM ISTO O PRODUTO SEGUINTE HERDA AS VARIACOES DO ANTERIOR — e herdaria
    em silencio, que e o pior jeito: o colaborador salvaria a segunda triagem
    com as fotos da primeira sem ver. `_limpar_form_triagem` nao alcancava
    estas chaves porque elas nao existem ate alguem clicar no botao.
    """
    for _vid in _ids_das_variacoes():
        st.session_state.pop(f"triagem_var_nome_{_vid}", None)
        st.session_state.pop(f"triagem_var_fotos_{_vid}", None)
    st.session_state.pop(_VAR_IDS, None)
    st.session_state.pop(_VAR_SEQ, None)


def _limpar_form_triagem():
    for _k in _CAMPOS_FORM_TRIAGEM:
        st.session_state.pop(_k, None)
    _zerar_variacoes()


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

    # ── AS VARIACOES CADASTRADAS, COM A FOTO DE CADA UMA ─────────────────
    #
    # Sem isto o colaborador cadastra vinte variacoes e nao tem como conferir
    # o que ficou gravado — e a aba Imagem passaria a listar nomes que
    # ninguem nunca viu na tela onde foram criados. O sistema conta o que
    # sabe, na tela onde a pergunta nasce.
    _vars_cartao = variacoes_da_triagem(dados)
    if _vars_cartao:
        st.markdown(f"**Variações cadastradas ({len(_vars_cartao)}):**")
        _cols_vc = st.columns(min(len(_vars_cartao), 5))
        for _i_vc, _v_vc in enumerate(_vars_cartao):
            with _cols_vc[_i_vc % len(_cols_vc)]:
                if _v_vc["fotos"]:
                    try:
                        st.image(url_thumbnail(_v_vc["fotos"][0], 160),
                                 use_container_width=True)
                    except Exception:
                        st.markdown("📦")
                else:
                    st.markdown("📦")
                st.caption(f"**{_v_vc['nome']}** · "
                           f"{len(_v_vc['fotos'])} foto(s)")


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
        # O CAMPO "Variacao de cores" SAIU DAQUI em 07/10, por ordem do dono:
        # "esse novo processo substituira ele". A coluna continua existindo e
        # continua sendo lida por seis telas — ela passa a ser PREENCHIDA
        # pelos nomes das variacoes cadastradas abaixo (`texto_das_variacoes`),
        # em vez de digitada. Um dono, e a mesma resposta de sempre para quem
        # pergunta "que cores este produto tem?".

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

        # ── VARIACOES DO MESMO PRODUTO ───────────────────────────────
        #
        # Pedido do dono, 07/10: "um campo Variacoes e um botao Cadastrar
        # Variacao para o sistema ir abrindo uma nova opcao a cada vez que o
        # colaborador clicar". Quatro variacoes, quatro cliques; vinte,
        # vinte.
        #
        # POR QUE `form_submit_button` E NAO `st.button`: `st.button` dentro
        # de um `st.form` levanta excecao — e esta tela inteira vive dentro
        # de `form_triagem`. O submit guarda o que ja foi digitado (todo
        # campo tem `key`), entao abrir mais um bloco nao perde nada.
        #
        # E CADA BOTAO LEVA UM ROTULO PROPRIO: `form_submit_button` nao
        # aceita `key` (medido, Streamlit 1.46.1), e o Streamlit identifica o
        # widget pelo rotulo. Vinte botoes "Remover" iguais derrubariam a
        # tela com DuplicateElementId — que e exatamente como a aba Extratos
        # caiu em 25/09.
        st.markdown("#### Variações")
        st.caption(
            "Mesmo produto, mesma medida, mesmo material — muda a cor ou a "
            "estampa. Cadastre uma por vez; todas herdam os dados "
            "preenchidos acima.")
        st.caption(
            "⚠️ **Produto de cor única também se cadastra aqui**, como uma "
            "variação só: é daqui que sai a cor do produto, e sem ela o "
            "gerador de imagem perde a trava que impede ele de pintar o "
            "produto de outra cor.")
        _ids_var = _ids_das_variacoes()
        _tirar_var = None
        _blocos_var = []
        for _n_var, _vid_var in enumerate(_ids_var, 1):
            with st.container(border=True):
                _c_nome_v, _c_del_v = st.columns([5, 2])
                _c_nome_v.text_input(
                    f"Nome da variação {_n_var}",
                    key=f"triagem_var_nome_{_vid_var}",
                    placeholder="ex: Camuflado, Preto, Rosa Bebê")
                # O rotulo leva o numero para ser unico. Ver o comentario
                # acima: sem `key`, o rotulo E a identidade do widget.
                if _c_del_v.form_submit_button(
                        f"🗑️ Remover variação {_n_var}",
                        use_container_width=True):
                    _tirar_var = _vid_var
                _fotos_v = st.file_uploader(
                    f"Fotos da variação {_n_var} — quantas quiser",
                    type=None, accept_multiple_files=True,
                    key=f"triagem_var_fotos_{_vid_var}")
                if _fotos_v:
                    st.caption(f"📷 {len(_fotos_v)} foto(s) anexada(s).")
                # O que a tela leu vai inteiro para quem grava. Reler o
                # `session_state` la embaixo seria uma segunda fonte para o
                # mesmo dado, e elas passam a discordar.
                _blocos_var.append({
                    "n": _n_var,
                    "nome": str(st.session_state.get(
                        f"triagem_var_nome_{_vid_var}", "") or "").strip(),
                    "fotos": list(_fotos_v or []),
                })
        _add_var = st.form_submit_button(
            "➕ Cadastrar variação", use_container_width=True)

        enviar = st.form_submit_button("Salvar Triagem", type="primary", use_container_width=True)

    # OS DOIS BOTOES DE VARIACAO SAO TRATADOS ANTES DO SALVAR, e cada um
    # devolve a tela na hora: eles nao sao "salvar", so mudam quantos blocos
    # existem. Sem o `st.rerun()` o bloco novo so apareceria no clique
    # seguinte, e o colaborador clicaria duas vezes achando que nao pegou.
    if _tirar_var:
        _fechar_variacao(_tirar_var)
        st.rerun()
    if _add_var:
        _abrir_variacao()
        st.rerun()

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

        # ── AS VARIACOES: CONFERIR ANTES DE GASTAR UPLOAD ────────────
        #
        # Bloco vazio (sem nome e sem foto) e so um clique a mais no botao:
        # ignora em silencio. Bloco PELA METADE e erro operacional, e trava —
        # variacao sem nome ninguem consegue escolher na aba Imagem, e
        # variacao sem foto nao tem o que gerar. Reprovar aqui custa um
        # aviso; deixar passar custa uma geracao inteira do produto errado.
        _vars_boas, _vars_erro = [], []
        _nomes_vistos = {}
        for _b_var in _blocos_var:
            _nm_v, _ft_v, _n_v = _b_var["nome"], _b_var["fotos"], _b_var["n"]
            if not _nm_v and not _ft_v:
                continue
            if not _nm_v:
                _vars_erro.append(
                    f"a variação {_n_v} tem foto mas **não tem nome** — "
                    f"escreva a cor ou a estampa dela")
                continue
            if not _ft_v:
                _vars_erro.append(
                    f"a variação **{_nm_v}** não tem foto nenhuma — "
                    f"anexe pelo menos uma")
                continue
            # Nome repetido e ambiguidade pura: a aba Imagem lista as
            # variacoes pelo nome, e duas "Preto" seriam indistinguiveis na
            # hora de escolher qual gerar.
            _chave_nm = _normalizar(_nm_v).strip()
            if _chave_nm in _nomes_vistos:
                _vars_erro.append(
                    f"a variação **{_nm_v}** está cadastrada duas vezes "
                    f"(blocos {_nomes_vistos[_chave_nm]} e {_n_v})")
                continue
            _nomes_vistos[_chave_nm] = _n_v
            _vars_boas.append({"nome": _nm_v, "arquivos": _ft_v})
        if _vars_erro:
            st.session_state["triagem_msg_erro"] = (
                "Corrija as variações antes de salvar: "
                + "; ".join(_vars_erro) + ".")
            st.rerun()

        # Salva a categoria escolhida para a próxima triagem
        st.session_state["triagem_ultima_categoria"] = categoria

        # Upload da foto para o Drive (se enviada)
        foto_drive_id = ""
        if foto_upload is not None:
            with st.spinner("Enviando foto para o Drive..."):
                imagem_bytes = foto_upload.read()
                ext = foto_upload.name.rsplit(".", 1)[-1].lower() if "." in foto_upload.name else "jpg"
                nome_arquivo = f"{nome_comercial.replace(' ', '_')}_{_pc_br.agora_br().strftime('%Y%m%d%H%M%S')}.{ext}"
                file_id, err_foto = upload_foto_triagem(imagem_bytes, nome_arquivo)
                if err_foto:
                    st.warning(
                        f"⚠️ Não foi possível enviar a foto. A triagem será salva "
                        f"normalmente, mas sem a foto de referência.\n\n{err_foto}"
                    )
                else:
                    foto_drive_id = file_id

        # ── AS FOTOS DAS VARIACOES VAO PARA O DRIVE ──────────────────
        #
        # So no clique de salvar, e nunca no desenho da tela: a tela redesenha
        # a cada tecla digitada, e subir dez fotos por tecla tornaria o
        # formulario inutilizavel. E o mesmo defeito que fez a gravacao das
        # fotos da aba Imagem escrever 30 MB por tecla.
        _variacoes_salvas = []
        _falhas_var = []
        if _vars_boas:
            _total_ft = sum(len(v["arquivos"]) for v in _vars_boas)
            _barra_var = st.progress(
                0.0, text=f"Enviando {_total_ft} foto(s) das variações…")
            _feitas = 0
            for _v_ok in _vars_boas:
                _ids_fotos = []
                for _arq_v in _v_ok["arquivos"]:
                    _feitas += 1
                    _barra_var.progress(
                        _feitas / max(_total_ft, 1),
                        text=f"{_v_ok['nome']}: foto {_feitas} de {_total_ft}…")
                    try:
                        _bytes_v = _arq_v.read()
                        _ext_v = (_arq_v.name.rsplit(".", 1)[-1].lower()
                                  if "." in _arq_v.name else "jpg")
                        _nm_arq_v = (
                            f"{nome_comercial.replace(' ', '_')}"
                            f"_{_v_ok['nome'].replace(' ', '_')}"
                            f"_{_pc_br.agora_br().strftime('%Y%m%d%H%M%S')}"
                            f"_{_feitas}.{_ext_v}")
                        _id_v, _err_v = upload_foto_triagem(_bytes_v, _nm_arq_v)
                    except Exception as _e_v:
                        _id_v, _err_v = "", f"{type(_e_v).__name__}: {_e_v}"
                    if _err_v or not _id_v:
                        _falhas_var.append(f"{_v_ok['nome']}: {_err_v}")
                    else:
                        _ids_fotos.append(_id_v)
                # VARIACAO QUE PERDEU TODAS AS FOTOS NAO ENTRA.
                #
                # Gravar o nome sem foto nenhuma criaria uma variacao que a
                # aba Imagem lista e nao consegue gerar — e o colaborador so
                # descobriria isso la, depois de escolher.
                if _ids_fotos:
                    _variacoes_salvas.append(
                        {"nome": _v_ok["nome"], "fotos": _ids_fotos})
            _barra_var.empty()
        if _falhas_var:
            st.warning(
                "⚠️ Algumas fotos de variação não subiram para o Drive. O que "
                "subiu foi salvo; o que falhou está listado aqui para você "
                "anexar de novo:\n\n- " + "\n- ".join(_falhas_var))

        dados = {
            "nome_comercial": nome_comercial, "categoria": categoria,
            "material": material,
            # DERIVADA, E NAO DIGITADA (07/10). Ver `texto_das_variacoes`.
            "variacao_cores": texto_das_variacoes(_variacoes_salvas),
            "variacoes": json.dumps(_variacoes_salvas, ensure_ascii=False),
            "medidas": medidas, "peso": peso,
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

    # ── AS VARIACOES DO MESMO PRODUTO (07/10) ────────────────────────────
    #
    # A ENTRADA VEM DA FORMA QUE A GRAVACAO PRODUZ, e nao da minha cabeca:
    # `json.dumps([{"nome":..., "fotos": [...]}])` e literalmente a linha que
    # `pagina_triagem` escreve na celula. Valor de teste escrito a mao mede o
    # meu entendimento do sistema — foi o que quebrou o botao dos oito
    # prompts nesta base.
    _VARS = [{"nome": "Camuflado", "fotos": ["id1", "id2"]},
             {"nome": "Preto", "fotos": ["id3"]}]
    _CELULA = json.dumps(_VARS, ensure_ascii=False)

    ok("a coluna existe no cabecalho", "variacoes" in COLUNAS)
    ok("a celula gravada volta inteira",
       variacoes_da_triagem({"variacoes": _CELULA}) == _VARS)
    ok("e o resumo vira o texto da coluna de cores",
       texto_das_variacoes(variacoes_da_triagem({"variacoes": _CELULA}))
       == "Camuflado, Preto")

    # LINHA ANTIGA NAO TEM A COLUNA, e isso e o caso NORMAL — nao um erro.
    ok("linha sem a coluna devolve lista vazia",
       variacoes_da_triagem({"nome_comercial": "x"}) == [])
    ok("celula vazia tambem", variacoes_da_triagem({"variacoes": ""}) == [])
    ok("e None nao quebra", variacoes_da_triagem(None) == [])

    # CELULA CORROMPIDA NAO PODE DERRUBAR A TELA DA TRIAGEM.
    ok("JSON cortado devolve lista vazia em vez de estourar",
       variacoes_da_triagem({"variacoes": '[{"nome": "Pret'}) == [])
    ok("JSON que nao e lista tambem",
       variacoes_da_triagem({"variacoes": '{"nome": "Preto"}'}) == [])
    ok("item que nao e dicionario e descartado, e os bons ficam",
       variacoes_da_triagem({"variacoes": json.dumps(
           ["lixo", {"nome": "Preto", "fotos": ["a"]}])})
       == [{"nome": "Preto", "fotos": ["a"]}])

    # VARIACAO SEM NOME NAO ENTRA: ninguem consegue escolher na aba Imagem.
    ok("variacao sem nome e descartada na leitura",
       variacoes_da_triagem({"variacoes": json.dumps(
           [{"nome": "", "fotos": ["a"]}])}) == [])
    ok("e o nome vem sem espaco sobrando",
       variacoes_da_triagem({"variacoes": json.dumps(
           [{"nome": "  Preto  ", "fotos": ["a"]}])})[0]["nome"] == "Preto")
    ok("foto vazia na lista nao vira id",
       variacoes_da_triagem({"variacoes": json.dumps(
           [{"nome": "Preto", "fotos": ["a", "", "  "]}])})[0]["fotos"]
       == ["a"])

    # ── A FOTO DA TRIAGEM VOLTA DO DRIVE ─────────────────────────────────
    #
    # Ela existe para a aba Imagem nao obrigar o colaborador a subir de novo a
    # foto que acabou de cadastrar. O duplo substitui o DRIVE, e nao a funcao
    # que eu escrevi: e o caminho inteiro — `baixar_foto_triagem` -> `gdrive`
    # — que precisa estar certo, inclusive o repasse do erro.
    import sys as _sys_dl, types as _types_dl
    _gd_falso = _types_dl.ModuleType("gdrive")
    _pedidos_dl = []

    def _baixar_gd(fid):
        _pedidos_dl.append(fid)
        if fid == "quebrado":
            return b"", "arquivo nao encontrado"
        return b"conteudo-da-foto", None
    _gd_falso.baixar = _baixar_gd
    _antes_gd = _sys_dl.modules.get("gdrive")
    try:
        _sys_dl.modules["gdrive"] = _gd_falso
        ok("a foto volta do Drive como bytes",
           baixar_foto_triagem("abc") == (b"conteudo-da-foto", None))
        ok("e o id pedido e o que foi passado", _pedidos_dl == ["abc"])
        # ERRO DO DRIVE E REPASSADO, E NAO ENGOLIDO: quem chama precisa poder
        # dizer na tela QUAL foto nao veio.
        _b_q, _e_q = baixar_foto_triagem("quebrado")
        ok("erro do Drive chega inteiro a quem chamou",
           _b_q == b"" and _e_q == "arquivo nao encontrado")
    finally:
        if _antes_gd is not None:
            _sys_dl.modules["gdrive"] = _antes_gd
        else:
            _sys_dl.modules.pop("gdrive", None)

    ok("sem variacao, a coluna de cores fica vazia",
       texto_das_variacoes([]) == "" and texto_das_variacoes(None) == "")

    # ── OS BLOCOS DA TELA: ID ESTAVEL, E NAO INDICE ──────────────────────
    #
    # O defeito que isto mede: com contador, remover a variacao 2 de quatro
    # faria as de baixo subirem de indice e as chaves dos widgets ficarem
    # coladas no valor antigo — o nome da 3 apareceria na linha da 2.
    _sessao_real = st.session_state
    try:
        st.session_state = {}
        _abrir_variacao(); _abrir_variacao(); _abrir_variacao()
        ok("tres cliques abrem tres blocos", len(_ids_das_variacoes()) == 3)
        _ids_antes = _ids_das_variacoes()
        ok("e cada bloco tem id proprio", len(set(_ids_antes)) == 3)
        st.session_state[f"triagem_var_nome_{_ids_antes[2]}"] = "Areia"
        _fechar_variacao(_ids_antes[1])
        ok("remover o do meio deixa dois", len(_ids_das_variacoes()) == 2)
        ok("e NAO mexe no que o terceiro tinha digitado",
           st.session_state.get(f"triagem_var_nome_{_ids_antes[2]}") == "Areia")
        ok("o id removido some da lista",
           _ids_antes[1] not in _ids_das_variacoes())
        ok("e o que foi digitado NELE e apagado junto",
           f"triagem_var_nome_{_ids_antes[1]}" not in st.session_state)
        # O id nao volta a ser usado: senao o bloco novo nasceria com a foto
        # do que acabou de ser removido.
        _abrir_variacao()
        ok("o bloco novo nao reusa o id do que saiu",
           _ids_antes[1] not in _ids_das_variacoes())

        # PRODUTO NOVO NAO HERDA AS VARIACOES DO ANTERIOR.
        st.session_state[f"triagem_var_nome_{_ids_das_variacoes()[0]}"] = "x"
        _limpar_form_triagem()
        ok("salvar zera os blocos", _ids_das_variacoes() == [])
        ok("e nao sobra chave de widget de variacao nenhuma",
           not [k for k in st.session_state if k.startswith("triagem_var_")])
    finally:
        st.session_state = _sessao_real

    print("\nfalhas:", falhas)
    # O CÓDIGO DE SAÍDA, QUE FALTAVA — e o `checar_mutacao` acusou.
    #
    # Este auto-teste imprimia "falhas: N" e saía com 0 SEMPRE. Quem lê o
    # código de saída — e o `checar_mutacao` lê, para conferir que o comando
    # PASSA antes de mutar — via sempre verde, e as três entradas novas que
    # apontam para cá estavam verdes por acidente.
    #
    # É o mesmo defeito que o `varredura_formas.py` teve nesta base: ninguém
    # tinha visto porque ninguém lia o código de saída.
    import sys as _sys_saida
    _sys_saida.exit(1 if falhas else 0)
