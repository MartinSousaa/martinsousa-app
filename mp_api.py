"""mp_api.py — O dinheiro a liberar no Mercado Pago, conta por conta e dia por dia.

POR QUE EXISTE (dono, 12/11)
----------------------------
"Quero integrar o Mercado Pago para a gente ter acesso ao dinheiro a liberar."
Toda venda do Mercado Livre vira um pagamento no Mercado Pago da conta que
vendeu, e o dinheiro fica preso até a data de liberação. Somar essas datas
responde "quanto entra no caixa, e quando".

DE ONDE VEM O NÚMERO
--------------------
`GET /v1/payments/search`, com `range=money_release_date`. Os nomes dos campos
foram conferidos no SDK oficial (`mercadopago` 2.0.15 no npm,
`dist/clients/payment/search/types.d.ts` e `commonTypes.d.ts`):
`money_release_date`, `money_release_status`, `status`,
`transaction_details.net_received_amount` e `transaction_amount_refunded`.

O valor de cada pagamento é o LÍQUIDO (`net_received_amount`, já sem tarifa)
menos o que foi devolvido. A devolução vem em valor BRUTO, então num pagamento
com devolução parcial o número sai menor do que o real, nunca maior. A tela
conta quantos são.

A LIBERAR E RETIDO
------------------
"A liberar" é pagamento aprovado com a data de liberação no futuro.
"Retido" é pagamento cuja data já passou e o Mercado Pago ainda diz que NÃO
liberou (`money_release_status` diferente de "released"), como numa
reclamação. Quando a resposta não traz esse campo, a data decide sozinha, e o
retido sai zero: a tela diz quantos pagamentos vieram sem ele.

QUAL TOKEN
----------
1. `MP_TOKEN_ML1` … `MP_TOKEN_ML4`, nas Variáveis do Railway (o Access Token
   de produção do aplicativo criado no Mercado Pago de cada conta).
2. Se a variável não existe, o token que o Studio JÁ TEM daquela conta do
   Mercado Livre (`ml_api.token`). O Mercado Pago e o Mercado Livre usam a
   mesma conta, mas NÃO está confirmado que o token do ML abre a busca de
   pagamentos. A tela mostra qual dos dois foi usado e o erro, se houver:
   é ali que a dúvida se resolve, na primeira leitura.

LIMITES, DITOS EM VOZ ALTA
--------------------------
A busca devolve no máximo `LIMITE` por página e o Studio lê até
`MAX_PAGINAS` páginas por conta. Passou disso, a tela avisa que o número está
INCOMPLETO e quantos ficaram de fora. O total que o Mercado Pago informa
(`paging.total`) é o juiz, e não o que coube.

Rede só no clique do botão, nunca no desenho da tela (custo por passada).
As quatro contas são lidas em paralelo, e os tokens são buscados ANTES, fora
da thread: `st.session_state` não se lê dentro de uma `threading.Thread`.
"""

from datetime import datetime, timedelta

import requests

import chaves

BASE = "https://api.mercadopago.com"
TIMEOUT = (10, 30)
LIMITE = 100          # pagamentos por página
MAX_PAGINAS = 40      # por conta: 4.000 pagamentos
JANELA_DIAS = 120     # para trás (retido) e para a frente (a liberar)
LIBERADO = "released"

CONTAS = ("ml1", "ml2", "ml3", "ml4")


def nome_da_variavel(conta):
    return f"MP_TOKEN_{str(conta).strip().upper()}"


def token(conta):
    """(token, fonte, erro). fonte é "mp" (variável própria) ou "ml"."""
    conta = str(conta).strip().lower()
    if conta not in CONTAS:
        return ("", "", f"conta desconhecida: {conta}")
    proprio = chaves.ler(nome_da_variavel(conta))
    if proprio:
        return (proprio, "mp", "")
    try:
        import ml_api
        tok, erro = ml_api.token(conta)
    except Exception as e:
        tok, erro = "", f"não consegui ler o token do Mercado Livre: {type(e).__name__}"
    if tok:
        return (tok, "ml", "")
    return ("", "", f"sem {nome_da_variavel(conta)} no Railway, e o token do Mercado "
                    f"Livre não serviu: {erro}")


def _buscar(tok, params):
    """A ÚNICA ida à API. (json, erro), nunca levanta. Não lê session_state."""
    for tentativa in range(2):
        try:
            r = requests.get(BASE + "/v1/payments/search", params=params,
                             timeout=TIMEOUT, headers={"Authorization": f"Bearer {tok}"})
        except Exception as e:
            return (None, f"Mercado Pago não respondeu: {type(e).__name__}")
        if r.status_code == 429 and tentativa == 0:
            import time
            time.sleep(1.5)
            continue
        break
    if r.status_code == 401:
        return (None, "Mercado Pago recusou o token (401)")
    if r.status_code == 403:
        return (None, "o token não tem permissão para ler pagamentos (403)")
    if not r.ok:
        return (None, f"Mercado Pago respondeu {r.status_code}: {(r.text or '')[:200]}")
    try:
        return (r.json(), "")
    except Exception:
        return (None, "Mercado Pago devolveu resposta que não é JSON")


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000-03:00")


def ler_conta(tok, agora, buscar=None):
    """Todos os pagamentos da janela, página a página.

    Devolve {"pagamentos": [...], "total": int, "lidos": int, "erro": str}.
    `total` é o que o Mercado Pago diz que existe; `lidos`, o que veio.
    """
    buscar = buscar or _buscar
    params = {"range": "money_release_date", "sort": "money_release_date",
              "criteria": "asc", "status": "approved", "limit": LIMITE,
              "begin_date": _iso(agora - timedelta(days=JANELA_DIAS)),
              "end_date": _iso(agora + timedelta(days=JANELA_DIAS))}
    todos, total = [], 0
    for pagina in range(MAX_PAGINAS):
        corpo, erro = buscar(tok, {**params, "offset": pagina * LIMITE})
        if erro:
            return {"pagamentos": todos, "total": max(total, len(todos)),
                    "lidos": len(todos), "erro": erro}
        res = (corpo or {}).get("results") or []
        total = int(((corpo or {}).get("paging") or {}).get("total") or 0)
        todos.extend(res)
        if not res or len(todos) >= total:
            break
    return {"pagamentos": todos, "total": max(total, len(todos)),
            "lidos": len(todos), "erro": ""}


def _data(txt):
    """A data de liberação como datetime com fuso, ou None."""
    try:
        return datetime.fromisoformat(str(txt).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def valor_liquido(p):
    """Líquido menos devolvido, nunca negativo. (valor, teve_devolucao)."""
    td = p.get("transaction_details") or {}
    try:
        liq = float(td.get("net_received_amount") or 0)
    except (TypeError, ValueError):
        liq = 0.0
    try:
        dev = float(p.get("transaction_amount_refunded") or 0)
    except (TypeError, ValueError):
        dev = 0.0
    return (max(liq - dev, 0.0), dev > 0)


def classificar(pagamentos, agora):
    """Soma por situação e por dia de liberação (no fuso de Brasília).

    {"a_liberar": R$, "retido": R$, "por_dia": {"AAAA-MM-DD": R$},
     "qtd_a_liberar": n, "qtd_retido": n, "sem_status": n,
     "com_devolucao": n, "sem_data": n, "ignorados": n}
    """
    fuso = agora.tzinfo
    r = {"a_liberar": 0.0, "retido": 0.0, "por_dia": {}, "qtd_a_liberar": 0,
         "qtd_retido": 0, "sem_status": 0, "com_devolucao": 0, "sem_data": 0,
         "ignorados": 0}
    for p in pagamentos:
        if str(p.get("status", "")).lower() != "approved":
            r["ignorados"] += 1
            continue
        quando = _data(p.get("money_release_date"))
        if quando is None:
            r["sem_data"] += 1
            continue
        situacao = p.get("money_release_status")
        if situacao is None:
            r["sem_status"] += 1
        if situacao == LIBERADO:
            continue
        valor, devolveu = valor_liquido(p)
        if valor <= 0:
            continue
        r["com_devolucao"] += devolveu
        if quando > agora:
            r["a_liberar"] += valor
            r["qtd_a_liberar"] += 1
            dia = quando.astimezone(fuso).date().isoformat() if fuso else quando.date().isoformat()
            r["por_dia"][dia] = r["por_dia"].get(dia, 0.0) + valor
        elif situacao is not None:
            r["retido"] += valor
            r["qtd_retido"] += 1
    return r


def ler_todas(agora=None, contas=CONTAS, buscar=None, obter_token=None):
    """{conta: {fonte, erro, total, lidos, incompleto, **classificar}}.

    Os tokens saem ANTES das threads, na thread da tela.
    """
    from concurrent.futures import ThreadPoolExecutor
    if agora is None:
        import placar_core
        agora = datetime.now(placar_core.FUSO)
    obter_token = obter_token or token
    tokens = {c: obter_token(c) for c in contas}
    vazio = classificar([], agora)

    def _uma(c):
        tok, fonte, erro = tokens[c]
        if erro:
            return c, {"fonte": fonte, "erro": erro, "total": 0, "lidos": 0,
                       "incompleto": False, **vazio}
        lido = ler_conta(tok, agora, buscar)
        return c, {"fonte": fonte, "erro": lido["erro"], "total": lido["total"],
                   "lidos": lido["lidos"], "incompleto": lido["lidos"] < lido["total"],
                   **classificar(lido["pagamentos"], agora)}

    with ThreadPoolExecutor(max_workers=4) as ex:
        return dict(ex.map(_uma, contas))


def calendario(lidas, dias=30, hoje=None):
    """Linhas [{dia, ml1.., total}] dos próximos `dias`, só dias com dinheiro,
    e uma última linha "depois" com o que cai além deles."""
    contas = list(lidas)
    hoje = hoje or min((d for v in lidas.values() for d in v["por_dia"]), default="")
    if not hoje:
        return []
    limite = (datetime.fromisoformat(hoje) + timedelta(days=dias)).date().isoformat()
    datas = sorted({d for v in lidas.values() for d in v["por_dia"]})
    linhas, depois = [], {c: 0.0 for c in contas}
    for d in datas:
        if d >= limite:
            for c in contas:
                depois[c] += lidas[c]["por_dia"].get(d, 0.0)
            continue
        linha = {"dia": d, **{c: lidas[c]["por_dia"].get(d, 0.0) for c in contas}}
        linha["total"] = sum(linha[c] for c in contas)
        linhas.append(linha)
    if any(depois.values()):
        linhas.append({"dia": "depois", **depois, "total": sum(depois.values())})
    return linhas


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os
    import threading
    from datetime import timezone

    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    BR = timezone(timedelta(hours=-3))
    AGORA = datetime(2026, 11, 12, 13, 0, tzinfo=BR)

    # Pagamento NA FORMA do SDK oficial (PaymentSearchResult): o líquido mora
    # em transaction_details, a data é texto ISO com fuso.
    def pg(dia_hora, liq, status="approved", rel="pending", dev=0, bruto=None):
        p = {"id": "1", "status": status, "money_release_date": dia_hora,
             "transaction_amount": bruto or liq * 1.15,
             "transaction_amount_refunded": dev,
             "transaction_details": {"net_received_amount": liq,
                                     "total_paid_amount": bruto or liq * 1.15}}
        if rel is not None:
            p["money_release_status"] = rel
        return p

    lista = [
        pg("2026-11-13T10:00:00.000-04:00", 100.0),                 # a liberar amanhã
        pg("2026-11-13T23:30:00.000-04:00", 50.0),                  # 00:30 de 14/11 em Brasília
        pg("2026-11-20T10:00:00.000-04:00", 200.0, dev=80.0),       # devolução parcial
        pg("2026-11-01T10:00:00.000-04:00", 70.0),                  # passou e não liberou: retido
        pg("2026-11-01T10:00:00.000-04:00", 999.0, rel=LIBERADO),   # já liberado
        pg("2026-11-25T10:00:00.000-04:00", 30.0, status="refunded"),
        pg("2026-11-02T10:00:00.000-04:00", 40.0, rel=None),        # sem o campo, passado
        pg("2026-11-26T10:00:00.000-04:00", 10.0, rel=None),        # sem o campo, futuro
        pg("", 5.0),
    ]
    c = classificar(lista, AGORA)
    ok("a liberar soma só o futuro, líquido menos devolvido",
       abs(c["a_liberar"] - (100 + 50 + 120 + 10)) < 1e-6)
    ok("retido é o que passou e o MP diz que não liberou", abs(c["retido"] - 70) < 1e-6)
    ok("liberado e devolvido não entram", c["qtd_a_liberar"] == 4 and c["qtd_retido"] == 1)
    ok("o dia é o de Brasília, não o do servidor",
       c["por_dia"].get("2026-11-14") == 50.0 and c["por_dia"].get("2026-11-13") == 100.0)
    ok("conta quem veio sem o status de liberação", c["sem_status"] == 2)
    ok("conta a devolução parcial", c["com_devolucao"] == 1)
    ok("conta quem veio sem data, e quem não está aprovado",
       c["sem_data"] == 1 and c["ignorados"] == 1)

    # Paginação: o total do MP é o juiz.
    def fabrica(n_total, falha_em=None):
        chamadas = []

        def buscar(tok, params):
            chamadas.append(params)
            off = params["offset"]
            if falha_em is not None and off >= falha_em:
                return (None, "Mercado Pago respondeu 500: erro")
            n = max(0, min(LIMITE, n_total - off))
            return ({"paging": {"total": n_total, "limit": LIMITE, "offset": off},
                     "results": [pg("2026-11-20T10:00:00.000-04:00", 1.0)] * n}, "")
        return buscar, chamadas

    b, ch = fabrica(250)
    lido = ler_conta("t", AGORA, b)
    ok("lê todas as páginas até o total", lido["lidos"] == 250 and len(ch) == 3)
    ok("pede por data de liberação, só aprovados",
       ch[0]["range"] == "money_release_date" and ch[0]["status"] == "approved"
       and ch[1]["offset"] == LIMITE)
    ok("a janela vai JANELA_DIAS para trás e para a frente",
       ch[0]["begin_date"] == _iso(AGORA - timedelta(days=JANELA_DIAS))
       and ch[0]["end_date"] == _iso(AGORA + timedelta(days=JANELA_DIAS)))
    b, ch = fabrica(LIMITE * MAX_PAGINAS + 7)
    lido = ler_conta("t", AGORA, b)
    ok("passou do teto: lidos < total, e não esconde",
       lido["lidos"] == LIMITE * MAX_PAGINAS and lido["total"] == LIMITE * MAX_PAGINAS + 7)
    b, ch = fabrica(250, falha_em=100)
    lido = ler_conta("t", AGORA, b)
    ok("erro no meio: guarda o que leu e diz o erro",
       lido["lidos"] == 100 and "500" in lido["erro"] and lido["total"] == 250)

    # Token: a variável própria vence; sem ela, o do ML; sem os dois, o porquê.
    _antes = os.environ.get("MP_TOKEN_ML1")
    os.environ["MP_TOKEN_ML1"] = "tok-mp"
    ok("a variável própria vence", token("ml1")[:2] == ("tok-mp", "mp"))
    os.environ.pop("MP_TOKEN_ML1", None)
    import ml_api as _ml
    _tk = _ml.token
    _ml.token = lambda c: ("tok-ml", "")
    ok("sem a variável, usa o token do ML e diz que usou", token("ml1")[:2] == ("tok-ml", "ml"))
    _ml.token = lambda c: ("", "ML1 ainda não foi autorizada")
    _t, _f, _e = token("ml1")
    ok("sem os dois, o erro nomeia a variável e o motivo do ML",
       not _t and "MP_TOKEN_ML1" in _e and "autorizada" in _e)
    _ml.token = _tk
    if _antes:
        os.environ["MP_TOKEN_ML1"] = _antes
    ok("conta desconhecida é recusada", token("ml9")[2] != "")

    # Quatro contas em paralelo, token buscado FORA da thread.
    _thr = []

    def _tok(c):
        _thr.append(threading.current_thread() is threading.main_thread())
        return ("", "", "sem token") if c == "ml4" else ("t-" + c, "mp", "")

    b, ch = fabrica(3)
    todas = ler_todas(AGORA, buscar=b, obter_token=_tok)
    ok("token buscado na thread principal", _thr and all(_thr))
    ok("as quatro voltam, a sem token com o erro dela",
       set(todas) == set(CONTAS) and todas["ml4"]["erro"] == "sem token"
       and todas["ml1"]["a_liberar"] == 3.0 and not todas["ml1"]["incompleto"])
    b, ch = fabrica(LIMITE * MAX_PAGINAS + 1)
    ok("conta que passou do teto sai marcada incompleta",
       ler_todas(AGORA, contas=("ml1",), buscar=b, obter_token=_tok)["ml1"]["incompleto"])

    # Calendário: dias com dinheiro, total da linha, e o "depois".
    lidas = {"ml1": {"por_dia": {"2026-11-13": 10.0, "2027-01-30": 5.0}},
             "ml2": {"por_dia": {"2026-11-13": 1.0, "2026-11-20": 2.0}}}
    cal = calendario(lidas, dias=30, hoje="2026-11-12")
    ok("calendário soma as contas por dia",
       cal[0] == {"dia": "2026-11-13", "ml1": 10.0, "ml2": 1.0, "total": 11.0})
    ok("o que cai depois da janela vai para a linha 'depois'",
       cal[-1]["dia"] == "depois" and cal[-1]["total"] == 5.0 and len(cal) == 3)
    ok("sem dinheiro, calendário vazio", calendario({"ml1": {"por_dia": {}}}) == [])

    # A cadeia real: requests.get trocado, ler_conta usa o _buscar de verdade.
    _rg = requests.get

    class _R:
        status_code, ok, text = 200, True, "x"

        def json(self):
            return {"paging": {"total": 1}, "results": [pg("2026-11-20T10:00:00.000-04:00", 9.0)]}

    _vistos = []
    requests.get = lambda url, **kw: (_vistos.append((url, kw["headers"])), _R())[1]
    try:
        lido = ler_conta("segredo", AGORA)
    finally:
        requests.get = _rg
    ok("a cadeia real vai à busca de pagamentos com o token no cabeçalho",
       lido["lidos"] == 1 and _vistos[0][0] == BASE + "/v1/payments/search"
       and _vistos[0][1]["Authorization"] == "Bearer segredo")

    class _R401(_R):
        status_code, ok = 401, False
    requests.get = lambda url, **kw: _R401()
    try:
        ok("401 vira frase, não exceção", "401" in _buscar("x", {})[1])
    finally:
        requests.get = _rg

    print("\nfalhas:", falhas)
    raise SystemExit(1 if falhas else 0)
