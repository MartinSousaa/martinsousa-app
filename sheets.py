"""
sheets.py — uma conexão só com a planilha, para o Studio inteiro.

Por que este módulo existe
--------------------------
Nove módulos montavam a própria conexão, cada um com o mesmo bloco copiado:
credencial, `gspread.authorize()` e `cliente.open(PLANILHA_NOME)`. Numa máquina
já aquecida isso passava despercebido, porque cada um deles é `cache_resource` e
roda uma vez por processo. Num container recém-subido — depois de todo deploy —
é a primeira coisa que acontece, e o custo aparece inteiro na tela de login.

Duas idas à rede por módulo, nove vezes:

  authorize()            troca a chave do service account por um token OAuth
  open(PLANILHA_NOME)    NÃO abre a planilha: procura por nome no Drive inteiro
                         (files.list paginado, pageSize=1000, incluindo drives
                         compartilhados) e só então monta o objeto

A busca por nome é a parte cara. `open_by_key()` não faz requisição nenhuma —
monta a planilha direto do ID. Com o secret PLANILHA_ID configurado, o Studio
deixa de varrer o Drive; sem ele, continua abrindo por nome como antes.

Timeout
-------
O gspread aceita timeout e vem com `None`, que em `requests` significa esperar
para sempre. Uma conexão pendurada com o Google travava a tela de login sem
erro nenhum — o mesmo tipo de falha que já tinha derrubado a TV pelo lado do
Trello. Aqui ele é explícito.
"""

import streamlit as st

import planilha as _plan

# Conectar, ler. Generoso na leitura porque get_all_records de uma aba grande
# demora mesmo; curto na conexão porque conexão que não estabelece em 10s não
# vai estabelecer.
TIMEOUT = (10, 45)

ESCOPOS = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _id_configurado():
    """ID da planilha, quando houver. Sem ele, abre por nome como antes.

    Como configurar
    ---------------
    O segredo chega pela variavel de ambiente PLANILHA_ID, que o Procfile
    escreve no secrets.toml ANTES do bloco STREAMLIT_SECRETS. A ordem nao e
    detalhe: em TOML, chave solta escrita depois de um cabecalho [secao]
    pertence aquela secao. Acrescentada no fim do bloco de segredos, esta linha
    viraria trello.PLANILHA_ID -- sem erro nenhum, so o Drive sendo varrido de
    novo a cada container novo, que e exatamente o custo que ela existe para
    evitar. Variavel nao definida nao escreve linha alguma.

    O valor e o trecho entre /d/ e /edit da URL da planilha.
    """
    try:
        return str(st.secrets.get("PLANILHA_ID", "") or "").strip()
    except Exception:
        return ""


# ── Erro 429: a cota do Google por minuto ───────────────────────────────────
#
# O dono removeu uma colaboradora e a tela caiu com 429 (07/10). A cota do
# Sheets é por MINUTO: estourou, um pouco de espera resolve. Em vez de mostrar
# erro, o pedido é repetido até 3 vezes (2 s, 5 s, 10 s). O `BackOffHTTPClient`
# do gspread faz parecido, mas se declara "não pronto para produção", guarda a
# contagem de tentativas na CLASSE (compartilhada por toda a equipe) e espera
# até 128 s — a tela congelaria. Aqui as tentativas são locais a cada pedido.
ESPERAS_429 = (2, 5, 10)


def _repetir_429(fazer, dormir=None):
    """Chama `fazer()`; no 429, espera e repete. Pura no que importa."""
    import time
    dormir = dormir or time.sleep
    for espera in ESPERAS_429 + (None,):
        try:
            return fazer()
        except Exception as e:
            codigo = getattr(getattr(e, "response", None), "status_code", None)
            if codigo != 429 or espera is None:
                raise
            dormir(espera)


def _cliente_http():
    import gspread

    class _ComEspera(gspread.HTTPClient):
        def request(self, *a, **k):
            return _repetir_429(lambda: gspread.HTTPClient.request(self, *a, **k))
    return _ComEspera


def apagar_linhas(aba, numeros):
    """Apaga várias linhas numa ÚNICA requisição. Quantas apagou.

    Uma `delete_rows` por linha é uma gravação por linha — e foi assim que
    excluir um usuário com muitos logins salvos estourou a cota. As linhas
    viram faixas contíguas, de baixo para cima (dentro do lote o Google aplica
    em ordem, e apagar de cima deslocaria as de baixo).
    """
    nums = sorted({int(n) for n in (numeros or []) if int(n) >= 2},
                  reverse=True)
    if not nums:
        return 0
    faixas, ini, fim = [], nums[0], nums[0]
    for n in nums[1:]:
        if n == ini - 1:
            ini = n
        else:
            faixas.append((ini, fim))
            ini = fim = n
    faixas.append((ini, fim))
    lote = getattr(getattr(aba, "spreadsheet", None), "batch_update", None)
    if lote is None:
        # Aba sem lote (o duplo dos auto-testes): uma a uma, de baixo para
        # cima. A aba do gspread sempre tem `spreadsheet`.
        for n in nums:
            aba.delete_rows(n)
        return len(nums)
    lote({"requests": [
        {"deleteDimension": {"range": {"sheetId": aba.id, "dimension": "ROWS",
                                       "startIndex": a - 1, "endIndex": b}}}
        for a, b in faixas]})
    return len(nums)


@st.cache_resource
def cliente():
    """Cliente gspread compartilhado — uma troca de token por processo."""
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=ESCOPOS)
    gc = gspread.authorize(creds, http_client=_cliente_http())
    try:
        gc.set_timeout(TIMEOUT)
    except Exception:
        pass   # versão de gspread sem set_timeout: segue sem timeout, como antes
    return gc


# Motivo de a planilha ter sido aberta pelo nome, quando havia um ID. Lido pela
# tela para avisar; vazio quando nao houve problema.
ID_RECUSADO = {"motivo": ""}


@st.cache_resource
def planilha():
    """A planilha deste ambiente, aberta uma vez por processo.

    O ID so e aceito se o titulo bater com o nome esperado do ambiente.

    Sem essa conferencia, o ID de producao colado por engano no ambiente de
    teste faria o teste ESCREVER na planilha de verdade — com a faixa amarela
    de "nada aqui afeta o Studio de verdade" no topo da tela, dizendo o
    contrario. O nome e escolhido por ambiente em planilha.py; o ID nao passa
    por ali, entao ele tem que se justificar contra o nome.

    O titulo nao custa requisicao: gspread ja busca o metadata da planilha ao
    construir o objeto, tanto por ID quanto por nome.
    """
    gc = cliente()
    chave = _id_configurado()
    esperado = _plan.nome()
    ID_RECUSADO["motivo"] = ""
    if chave:
        try:
            pl = gc.open_by_key(chave)
            titulo = str(getattr(pl, "title", "") or "").strip()
            if titulo == esperado:
                return pl
            ID_RECUSADO["motivo"] = (
                f'PLANILHA_ID aponta para "{titulo}", mas este ambiente é '
                f'"{esperado}". Abri pelo nome e ignorei o ID.')
        except Exception as e:
            ID_RECUSADO["motivo"] = (
                f"PLANILHA_ID configurado, mas não consegui abrir por ele "
                f"({str(e)[:120]}). Abri pelo nome.")
    return gc.open(esperado)


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    class _Resp:
        def __init__(self, c):
            self.status_code = c

    class _Erro(Exception):
        def __init__(self, c):
            super().__init__(f"HTTP {c}")
            self.response = _Resp(c)

    _esperas, _tent = [], []

    def _faz(codigos):
        def f():
            _tent.append(1)
            c = codigos.pop(0)
            if c != 200:
                raise _Erro(c)
            return "ok"
        return f
    ok("429 duas vezes e depois responde: espera e devolve a resposta",
       _repetir_429(_faz([429, 429, 200]), _esperas.append) == "ok"
       and _esperas == [2, 5])
    _esperas.clear()
    try:
        _repetir_429(_faz([429, 429, 429, 429]), _esperas.append)
        _deu = False
    except _Erro:
        _deu = True
    ok("depois de 3 novas tentativas o 429 aparece — não fica preso",
       _deu and _esperas == [2, 5, 10])
    _esperas.clear(); _tent.clear()
    try:
        _repetir_429(_faz([500]), _esperas.append)
    except _Erro:
        pass
    ok("outro erro não espera nem repete", _esperas == [] and len(_tent) == 1)

    # A exclusão em lote: faixas contíguas, de baixo para cima, numa só ida.
    class _Planilha:
        def __init__(self):
            self.lotes = []

        def batch_update(self, corpo):
            self.lotes.append(corpo)

    class _Aba:
        id = 7

        def __init__(self):
            self.spreadsheet = _Planilha()
    _a = _Aba()
    ok("dez linhas viram UMA requisição",
       apagar_linhas(_a, [2, 3, 4, 9, 10, 15, 16, 17, 18, 30]) == 10
       and len(_a.spreadsheet.lotes) == 1)
    _faixas = [(r["deleteDimension"]["range"]["startIndex"],
                r["deleteDimension"]["range"]["endIndex"])
               for r in _a.spreadsheet.lotes[0]["requests"]]
    ok("faixas contíguas, de baixo para cima, índice 0 do Google",
       _faixas == [(29, 30), (14, 18), (8, 10), (1, 4)])
    ok("cabeçalho (linha 1) nunca é apagado, e lista vazia não chama nada",
       apagar_linhas(_Aba(), [1]) == 0 and apagar_linhas(_a, []) == 0
       and len(_a.spreadsheet.lotes) == 1)

    # E ninguém volta a apagar linha por linha dentro de laço — foi assim que
    # excluir um usuário com muitos logins estourou a cota. Varre só o código
    # (antes do `__main__`, onde os duplos dos testes definem `delete_rows`).
    import ast as _ast_s
    import os as _os_s
    _raiz_s = _os_s.path.dirname(_os_s.path.abspath(__file__))
    _em_laco = []
    for _arq in ("auth.py", "admin.py", "cheques.py", "devolucoes.py",
                 "meta_gastos.py", "abonos.py"):
        _src = open(_os_s.path.join(_raiz_s, _arq), encoding="utf-8").read()
        _src = _src.split('if __name__ == "__main__":')[0]
        for _n in _ast_s.walk(_ast_s.parse(_src)):
            if not isinstance(_n, (_ast_s.For, _ast_s.While)):
                continue
            # Gravar UMA vez e sair (`return` no mesmo bloco) é uma gravação
            # só — `admin._atualizar_campo`, `abonos.remover`. O que se procura
            # é o laço que grava a cada volta.
            for _bloco in [getattr(x, c) for x in _ast_s.walk(_n)
                           for c in ("body", "orelse")
                           if isinstance(getattr(x, c, None), list)]:
                if any(isinstance(st, _ast_s.Return) for st in _bloco):
                    continue
                for st in _bloco:
                    _c = getattr(st, "value", None)
                    if (isinstance(st, _ast_s.Expr) and isinstance(_c, _ast_s.Call)
                            and isinstance(_c.func, _ast_s.Attribute)
                            and _c.func.attr in ("delete_rows", "update_cell")):
                        _em_laco.append(f"{_arq}:{_c.lineno}")
    ok(f"nenhuma exclusão ou célula gravada uma a uma em laço: {_em_laco}",
       not _em_laco)

    import gspread as _gs
    ok("o cliente do Google usa a espera do 429",
       issubclass(_cliente_http(), _gs.HTTPClient)
       and "_cliente_http()" in open(__file__, encoding="utf-8").read()
       .split("def cliente():")[1].split("return gc")[0])

    print("\nfalhas:", falhas)
    sys.exit(1 if falhas else 0)
