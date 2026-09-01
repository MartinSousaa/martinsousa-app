"""Quem faz parte da equipe medida pelo painel.

Por que este módulo existe
--------------------------
A lista de colaboradores vivia escrita no código. Cada contratação exigia uma
alteração de código para a pessoa aparecer nas metas, no placar e na ociosidade —
e, até isso acontecer, o trabalho dela simplesmente não era contado.

Aqui a lista vive numa aba da planilha e é editável pelo gestor. O código
continua com a equipe de origem como reserva: planilha fora do ar não esvazia o
painel.

Campos por pessoa:
  username_trello — o @ exato como aparece no Trello (é a chave de tudo)
  nome            — como o painel mostra
  nome_rhid       — primeiro nome como está cadastrado no relógio de ponto
  ativo           — "não" tira a pessoa das medições sem apagar o histórico
  bate_ponto      — "não" para quem não usa o relógio (ver abaixo)

Sobre bate_ponto
----------------
Nem todo mundo da equipe bate ponto. Sem esse campo, as telas de Ponto tratavam
quem não usa o relógio igual a quem faltou: o Resumo por Colaborador dava "0% de
desempenho" e o Status Hoje pintava "Não registrado" em vermelho. Quem bate o
olho lê "essa pessoa rendeu zero" — e isso vira conversa de avaliação em cima de
um número que nunca existiu.
"""

import streamlit as st

import planilha as _plan
# Nome vindo do ambiente: producao usa o padrao, homologacao usa a copia.
PLANILHA_NOME = _plan.nome()
ABA_NOME = "equipe"
COLUNAS = ["username_trello", "nome", "nome_rhid", "ativo", "bate_ponto", "colunas_funcao"]


def _crono(rotulo, seg, detalhe=""):
    """Registra quanto custou uma ida a planilha. Nunca derruba a leitura."""
    try:
        import cronometro
        cronometro.marcar(rotulo, seg, detalhe)
    except Exception:
        pass


@st.cache_resource
def _aba():
    # A planilha e aberta uma vez por processo em sheets.py. Aqui cada
    # modulo abria a sua, e abrir por nome custa uma varredura do Drive.
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        return planilha.worksheet(ABA_NOME)
    except Exception:
        aba = planilha.add_worksheet(title=ABA_NOME, rows=100, cols=len(COLUNAS))
        aba.append_row(COLUNAS, value_input_option="RAW")
        return aba


@st.cache_data(ttl=600)
def carregar():
    """({username: nome}, {primeiro_nome_rhid: username}).

    Só pessoas com `ativo` diferente de "não". Vazio em qualquer falha — quem
    chama cai na equipe de origem.
    """
    try:
        import time as _t_crono
        _t0_crono = _t_crono.perf_counter()
        registros = _aba().get_all_records()
        _crono("Planilha: equipe", _t_crono.perf_counter() - _t0_crono,
               f"{len(registros)} linhas")
    except Exception:
        return {}, {}

    membros, mapa_rhid = {}, {}
    for linha in registros:
        user = str(linha.get("username_trello", "")).strip()
        nome = str(linha.get("nome", "")).strip()
        if not user or not nome:
            continue
        if str(linha.get("ativo", "sim")).strip().lower() in ("não", "nao", "0", "false"):
            continue
        membros[user] = nome
        rhid = str(linha.get("nome_rhid", "") or nome).strip().lower().split()[0]
        if rhid:
            mapa_rhid[rhid] = user
    return membros, mapa_rhid


def salvar(username_trello, nome, nome_rhid="", ativo=True, bate_ponto=True,
           colunas_funcao=""):
    """Grava ou atualiza uma pessoa."""
    aba = _aba()
    _garantir_colunas(aba)
    linha = [str(username_trello).strip(), str(nome).strip(),
             str(nome_rhid).strip(), "sim" if ativo else "não",
             "sim" if bate_ponto else "não", str(colunas_funcao or "").strip()]
    try:
        celula = aba.find(str(username_trello).strip(), in_column=1)
    except Exception:
        celula = None
    if celula:
        aba.update(f"A{celula.row}:F{celula.row}", [linha], value_input_option="RAW")
    else:
        aba.append_row(linha, value_input_option="RAW")
    carregar.clear()
    nao_batem.clear()
    colunas_da_funcao.clear()


def _garantir_colunas(aba):
    """Acrescenta ao cabeçalho as colunas que ainda não existem.

    A aba foi criada com quatro colunas. Sem isto, bate_ponto iria para uma
    coluna sem nome e ninguém conseguiria ler de volta — foi o que aconteceu com
    foto_drive_id na aba de triagem.
    """
    try:
        cabecalho = aba.row_values(1)
        for col in COLUNAS:
            if col not in cabecalho:
                aba.add_cols(1)
                aba.update_cell(1, len(cabecalho) + 1, col)
                cabecalho.append(col)
    except Exception:
        pass


@st.cache_data(ttl=600)
def nao_batem():
    """Usernames de quem NÃO bate ponto.

    Ausente ou vazio conta como "bate" — a coluna é nova, e o padrão tem que ser
    o comportamento de antes para ninguém sumir das telas de ponto sem querer.
    """
    try:
        registros = _aba().get_all_records()
    except Exception:
        return set()
    fora = set()
    for linha in registros:
        user = str(linha.get("username_trello", "")).strip()
        marca = str(linha.get("bate_ponto", "")).strip().lower()
        if user and marca in ("não", "nao", "0", "false", "n"):
            fora.add(user)
    return fora


@st.cache_data(ttl=600)
def colunas_da_funcao(username=None):
    """Colunas do Trello que sao da funcao de cada pessoa.

    Sem username devolve {usuario: [prefixo, ...]}; com username, a lista dela.
    Pessoa sem nada cadastrado devolve lista vazia, e isso quer dizer SEM
    RESTRICAO — nada e marcado na tela. Marcar por omissao acusaria todo mundo
    no dia em que o campo fosse criado.

    O valor e uma lista separada por ponto e virgula, comparada por prefixo:
    "CRIATIVO VÍDEO" pega "CRIATIVO VÍDEO (80)" mesmo se o numero mudar.
    """
    mapa = {}
    try:
        registros = _aba().get_all_records()
    except Exception:
        registros = []
    for linha in registros:
        u = str(linha.get("username_trello", "")).strip().lower()
        if not u:
            continue
        bruto = str(linha.get("colunas_funcao", "") or "").strip()
        mapa[u] = [p.strip() for p in bruto.split(";") if p.strip()]
    if username is not None:
        return mapa.get(str(username).strip().lower(), [])
    return mapa
