"""ml_ads.py — quanto cada conta gastou em Product Ads, perguntado ao ML.

O PEDIDO (dono, 06/11)
----------------------
O diagnóstico de ADS mostrou que a publicidade do ML não passa no extrato
(é paga pelo saldo do Mercado Pago) e só existia na planilha ADS E CROSS —
digitada à mão, com out e nov zerados. As quatro contas já autorizaram o
"Sistema MS" com `urn:ml:mktp:ads:/read-write`. Faltava o Studio perguntar.

O QUE NÃO SE SABE, DITO EM VOZ ALTA
-----------------------------------
A documentação do ML é bloqueada no ambiente de desenvolvimento. O que se
achou dela traz DOIS caminhos para as campanhas, o novo e o antigo:

    /marketplace/advertising/{site}/advertisers/{adv}/product_ads/campaigns/search
    /advertising/advertisers/{adv}/product_ads/campaigns/search

Então se tenta o novo e, se o ML recusar, o antigo — e a tela diz QUAL
respondeu, e o erro de cada um quando nenhum responde. Resposta sem `cost`
reconhecível não vira zero: vira aviso com as chaves que vieram. Zero
inventado seria o pior número possível aqui.

CUSTO POR PASSADA
-----------------
Quatro contas × um mês por pergunta = até 48 idas ao ML. Só roda no botão,
e o resultado fica em cache por 1 h. As quatro contas em paralelo; o token
é buscado ANTES, na thread da tela (ele lê a planilha e pode renovar) — a
thread só faz rede e não toca em `st.session_state`.
"""
import calendar

import streamlit as st

import ml_api as _ml

CAMINHOS = (
    "/marketplace/advertising/{site}/advertisers/{adv}/product_ads/campaigns/search",
    "/advertising/advertisers/{adv}/product_ads/campaigns/search",
)
LIMITE = 50          # campanhas por página
MAX_PAGINAS = 10

# A JANELA DO ML (medida em produção, 09/11): "You cannot request metrics
# with a date greater than 90 days" — o ML só devolve os últimos 90 dias.
# Jan a ago voltavam 400 nas quatro contas. É limite da API, e não defeito:
# por isso o Studio GUARDA cada mês fechado que leu (aba `ml_ads_mes`), e o
# histórico se forma daqui para a frente. O que já saiu da janela vem só da
# planilha ADS E CROSS.
JANELA_DIAS = 89
ABA = "ml_ads_mes"
COLUNAS = ["conta", "mes", "custo", "lido_em"]


def anunciante(resp):
    """(advertiser_id, site_id) da resposta de /advertising/advertisers. Pura.

    Aceita a lista solta ou dentro de "advertisers"/"results". Sem id: ("", "").
    """
    lista = resp
    if isinstance(resp, dict):
        lista = resp.get("advertisers") or resp.get("results") or [resp]
    for a in lista if isinstance(lista, list) else []:
        if not isinstance(a, dict):
            continue
        adv = a.get("advertiser_id") or a.get("id")
        if adv:
            return (str(adv), str(a.get("site_id") or "MLB"))
    return ("", "")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def custo(resp):
    """(custo, completo) de UMA página da busca de campanhas. Pura.

    O total do ML (`metrics_summary.cost`) vale por todas as páginas; sem ele,
    soma `metrics.cost` de cada campanha e diz que precisa da próxima página.
    Sem `cost` em lugar nenhum: (None, True) — o chamador avisa, não zera.
    """
    if not isinstance(resp, dict):
        return (None, True)
    total = _num((resp.get("metrics_summary") or {}).get("cost"))
    if total is not None:
        return (total, True)
    res = resp.get("results")
    if not isinstance(res, list):
        return (None, True)
    custos = [_num(((r or {}).get("metrics") or {}).get("cost")) for r in res]
    achou = [c for c in custos if c is not None]
    if res and not achou:
        return (None, True)
    return (sum(achou), len(res) < LIMITE)


def _forma(resp):
    if isinstance(resp, dict):
        return "chaves: " + ", ".join(sorted(map(str, resp))[:12])
    return f"veio {type(resp).__name__}"


def periodos(ano, ate_mes, ate_dia):
    """[(mês, date_from, date_to)] de jan até o mês atual, o atual até hoje. Pura."""
    fora = []
    for m in range(1, int(ate_mes) + 1):
        ult = int(ate_dia) if m == int(ate_mes) else calendar.monthrange(int(ano), m)[1]
        fora.append((m, f"{int(ano)}-{m:02d}-01", f"{int(ano)}-{m:02d}-{ult:02d}"))
    return fora


def na_janela(meses, hoje, dias=JANELA_DIAS):
    """(perguntar, cortados, fora) dos `meses` de `periodos`. Pura.

    `perguntar`: [(mês, date_from, date_to)] dentro da janela do ML, o
    começo puxado para o limite quando o mês atravessa a borda.
    `cortados`: os meses puxados (o número deles é PARCIAL).
    `fora`: os meses inteiros antes da janela — nem se pergunta.
    """
    from datetime import date, timedelta
    lim = (hoje - timedelta(days=dias)).isoformat()
    perguntar, cortados, fora = [], set(), []
    for m, d0, d1 in meses:
        if d1 < lim:
            fora.append(m)
        elif d0 < lim:
            perguntar.append((m, lim, d1))
            cortados.add(m)
        else:
            perguntar.append((m, d0, d1))
    return perguntar, cortados, fora


def _mes(conta, tok, req, caminho, d0, d1):
    """(custo, erro) de um mês, paginando quando o ML não manda o total."""
    soma = 0.0
    for p in range(MAX_PAGINAS):
        resp, erro = req("GET", conta, tok, caminho,
                         {"date_from": d0, "date_to": d1, "metrics": "cost",
                          "metrics_summary": "true", "limit": LIMITE, "offset": p * LIMITE},
                         None, {"Api-Version": "2"})
        if erro:
            return (None, erro)
        c, completo = custo(resp)
        if c is None:
            return (None, f"resposta sem custo reconhecível ({_forma(resp)})")
        if (resp or {}).get("metrics_summary"):
            return (round(c, 2), "")
        soma += c
        if completo:
            return (round(soma, 2), "")
    return (None, f"mais de {MAX_PAGINAS * LIMITE} campanhas — parei de paginar")


def ler_conta(conta, tok, meses, req=None):
    """Tudo de UMA conta. Roda em thread: não toca em `st.session_state` nem
    no token (que chega pronto)."""
    req = req or _ml.requisitar
    fora = {"anunciante": "", "caminho": "", "por_mes": {}, "avisos": []}
    resp, erro = req("GET", conta, tok, "/advertising/advertisers",
                     {"product_id": "PADS"}, None, {"Api-Version": "1"})
    if erro:
        fora["avisos"].append(f"anunciante: {erro}")
        return fora
    adv, site = anunciante(resp)
    if not adv:
        fora["avisos"].append(f"o ML não devolveu anunciante de Product Ads ({_forma(resp)})")
        return fora
    fora["anunciante"] = adv
    candidatos = [c.format(site=site, adv=adv) for c in CAMINHOS]
    for m, d0, d1 in meses:
        if not fora["caminho"]:
            erros = []
            for cam in candidatos:
                v, e = _mes(conta, tok, req, cam, d0, d1)
                if not e:
                    fora["caminho"] = cam
                    fora["por_mes"][m] = v
                    break
                erros.append(f"{cam.split('/product_ads')[0]}…: {e}")
            if not fora["caminho"]:
                fora["avisos"].append(f"mês {m:02d}: nenhum caminho respondeu — " + " | ".join(erros))
            continue
        v, e = _mes(conta, tok, req, fora["caminho"], d0, d1)
        if e:
            fora["avisos"].append(f"mês {m:02d}: {e}")
        else:
            fora["por_mes"][m] = v
    return fora


@st.cache_data(ttl=3600, show_spinner="Perguntando ao Mercado Livre…")
def buscar(ano, ate_mes, ate_dia):
    """{conta: ler_conta(...)} das quatro, em paralelo. Cache de 1 h.

    Só pergunta o que cabe na janela de 90 dias do ML (`na_janela`); cada
    conta leva junto `cortados` (mês parcial) e `fora_janela`."""
    from concurrent.futures import ThreadPoolExecutor
    from datetime import date
    meses, cortados, fora_j = na_janela(periodos(ano, ate_mes, ate_dia),
                                        date(int(ano), int(ate_mes), int(ate_dia)))
    prontas, lidas = {}, {}
    for c in _ml.CONTAS:
        tok, erro = _ml.token(c)
        if erro:
            lidas[c] = {"anunciante": "", "caminho": "", "por_mes": {}, "avisos": [erro]}
        else:
            prontas[c] = tok
    with ThreadPoolExecutor(max_workers=4) as ex:
        fut = {c: ex.submit(ler_conta, c, t, meses) for c, t in prontas.items()}
        for c, f in fut.items():
            try:
                lidas[c] = f.result()
            except Exception as e:
                lidas[c] = {"anunciante": "", "caminho": "", "por_mes": {},
                            "avisos": [f"a leitura caiu: {type(e).__name__}"]}
    for d in lidas.values():
        d["cortados"], d["fora_janela"] = set(cortados), list(fora_j)
    return {c: lidas[c] for c in _ml.CONTAS if c in lidas}


# ── O que já foi lido fica guardado (a janela do ML é de 90 dias) ──────────

def _aba():
    import sheets as _sh
    pl = _sh.planilha()
    try:
        return pl.worksheet(ABA)
    except Exception:
        a = pl.add_worksheet(title=ABA, rows=200, cols=len(COLUNAS))
        a.append_row(COLUNAS, value_input_option="RAW")
        return a


def guardados_de(linhas, ano):
    """{conta: {mês: custo}} do ano, das linhas da aba. Pura."""
    fora = {}
    for l in linhas or []:
        mes, c = str(l.get("mes") or ""), str(l.get("conta") or "").strip()
        if not c or mes[:4] != str(int(ano)) or len(mes) < 7:
            continue
        try:
            fora.setdefault(c, {})[int(mes[5:7])] = round(float(str(l.get("custo")).replace(",", ".")), 2)
        except ValueError:
            continue
    return fora


@st.cache_data(ttl=600, show_spinner=False)
def guardados(ano):
    """Os meses já guardados. Cache de 10 min: a tela redesenha a cada clique."""
    return guardados_de(_aba().get_all_records(), ano)


def a_guardar(lidas, ano, mes_atual, ja):
    """[(conta, 'AAAA-MM', custo)] dos meses FECHADOS e inteiros que o ML
    respondeu e ainda não estão guardados com o mesmo valor. Pura.

    Mês corrente e mês cortado pela janela não se guardam: são parciais."""
    fora = []
    for c, d in (lidas or {}).items():
        for m, v in (d.get("por_mes") or {}).items():
            if m >= int(mes_atual) or m in (d.get("cortados") or ()):
                continue
            if (ja.get(c) or {}).get(m) != round(v, 2):
                fora.append((c, f"{int(ano):04d}-{m:02d}", round(v, 2)))
    return fora


def guardar(novas, quando):
    """Grava `novas` trocando a linha da mesma conta e mês. Levanta erro."""
    if not novas:
        return 0
    a = _aba()
    chave = {(c, m) for c, m, _v in novas}
    linhas = [l for l in a.get_all_records()
              if (str(l.get("conta")), str(l.get("mes"))) not in chave]
    linhas += [{"conta": c, "mes": m, "custo": v, "lido_em": quando} for c, m, v in novas]
    a.clear()
    a.update([COLUNAS] + [[str(l.get(k, "")) for k in COLUNAS] for l in linhas],
             value_input_option="RAW")
    guardados.clear()
    return len(novas)


def com_guardados(lidas, ja):
    """Uma CÓPIA de `lidas` com os meses guardados onde o ML não respondeu
    (fora da janela), marcados em `guardado`. A original é do cache. Pura."""
    import copy
    fora = copy.deepcopy(lidas or {})
    for c, d in fora.items():
        d.setdefault("guardado", set())
        for m, v in (ja.get(c) or {}).items():
            if m not in d.setdefault("por_mes", {}):
                d["por_mes"][m] = v
                d["guardado"].add(m)
    return fora


def por_mes(lidas):
    """({mês: soma das contas}, meses parciais). Soma o que veio; o mês em que
    uma conta com anunciante não respondeu sai em `faltou`, para a tela marcar. Pura."""
    soma, faltou = {}, set()
    for d in (lidas or {}).values():
        for m, v in d.get("por_mes", {}).items():
            soma[m] = round(soma.get(m, 0.0) + v, 2)
    meses = set(soma)
    for d in (lidas or {}).values():
        if d.get("anunciante"):
            faltou |= {m for m in meses if m not in d.get("por_mes", {})}
        # Mês puxado pela janela de 90 dias só tem o pedaço dentro dela.
        faltou |= set(d.get("cortados") or ()) & meses
    return soma, faltou


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    import threading

    # Um ML de mentira com a assinatura REAL de `ml_api.requisitar` — e que
    # explode se alguém tirar o Api-Version ou mandar sem token.
    def _ml_falso(caminho_novo_ok=True, com_resumo=True, sem_custo=False):
        visto = []

        def req(metodo, conta, tok, caminho, params=None, corpo=None, cabecalhos=None):
            visto.append((caminho, dict(params or {}), dict(cabecalhos or {})))
            assert tok == "TOK-" + conta and metodo == "GET"
            if caminho == "/advertising/advertisers":
                assert params == {"product_id": "PADS"} and cabecalhos == {"Api-Version": "1"}
                return ({"advertisers": [{"advertiser_id": 777, "site_id": "MLB",
                                          "advertiser_name": "MARTINSOUSA + Jóias (2)"}]}, "")
            if cabecalhos != {"Api-Version": "2"}:
                return (None, "Mercado Livre respondeu 400: missing api-version")
            if caminho.startswith("/marketplace/") and not caminho_novo_ok:
                return (None, "Mercado Livre respondeu 404: not found")
            mes = int(params["date_from"][5:7])
            if sem_custo:
                return ({"paging": {}, "data": []}, "")
            if com_resumo:
                return ({"results": [{"id": 1, "metrics": {"cost": 1.0}}],
                         "metrics_summary": {"cost": 100.0 * mes + 0.5}}, "")
            # sem resumo: 60 campanhas em duas páginas, R$ 1 cada
            n = 50 if params["offset"] == 0 else 10
            return ({"results": [{"id": i, "metrics": {"cost": 1.0}} for i in range(n)]}, "")
        return req, visto

    _meses = periodos(2026, 11, 6)
    ok("períodos: jan a nov, nov só até hoje",
       len(_meses) == 11 and _meses[1] == (2, "2026-02-01", "2026-02-28")
       and _meses[-1] == (11, "2026-11-01", "2026-11-06"))

    _req, _visto = _ml_falso()
    _r = ler_conta("ml1", "TOK-ml1", _meses[:3], _req)
    ok("acha o anunciante e usa o caminho novo", _r["anunciante"] == "777"
       and _r["caminho"].startswith("/marketplace/advertising/MLB/advertisers/777/"))
    ok("o custo do mês vem do total do ML", _r["por_mes"] == {1: 100.5, 2: 200.5, 3: 300.5})
    ok("toda busca de campanha leva Api-Version 2 e o período certo",
       all(h == {"Api-Version": "2"} for c, p, h in _visto if "campaigns" in c)
       and any(p.get("date_from") == "2026-02-01" and p.get("date_to") == "2026-02-28"
               for c, p, h in _visto))

    _req, _ = _ml_falso(caminho_novo_ok=False)
    _r = ler_conta("ml2", "TOK-ml2", _meses[:2], _req)
    ok("caminho novo recusado: cai no antigo, e diz qual respondeu",
       _r["caminho"] == "/advertising/advertisers/777/product_ads/campaigns/search"
       and _r["por_mes"] == {1: 100.5, 2: 200.5} and not _r["avisos"])

    _req, _ = _ml_falso(com_resumo=False)
    ok("sem total do ML: pagina e soma todas as campanhas",
       ler_conta("ml3", "TOK-ml3", _meses[:1], _req)["por_mes"] == {1: 60.0})

    _req, _ = _ml_falso(sem_custo=True)
    _r = ler_conta("ml4", "TOK-ml4", _meses[:2], _req)
    ok("resposta sem custo NÃO vira zero: vira aviso com a forma que veio",
       _r["por_mes"] == {} and any("data, paging" in a for a in _r["avisos"]))

    def _sem_anunciante(metodo, conta, tok, caminho, params=None, corpo=None, cabecalhos=None):
        return (None, "Mercado Livre respondeu 404: No permissions found for user_id")
    _r = ler_conta("ml1", "TOK-ml1", _meses[:2], _sem_anunciante)
    ok("conta sem Product Ads diz o porquê, e não pergunta mês nenhum",
       _r["anunciante"] == "" and "No permissions" in _r["avisos"][0] and _r["por_mes"] == {})

    # A cadeia de verdade, numa Thread de verdade, como `buscar` faz.
    _req, _ = _ml_falso()
    _saida = {}
    _t = threading.Thread(target=lambda: _saida.update(x=ler_conta("ml1", "TOK-ml1", _meses[:1], _req)))
    _t.start(); _t.join()
    ok("roda dentro de uma Thread sem ler session_state", _saida["x"]["por_mes"] == {1: 100.5})

    _s, _f = por_mes({"ml1": {"anunciante": "1", "por_mes": {1: 10.0, 2: 5.0}},
                      "ml2": {"anunciante": "2", "por_mes": {1: 2.5}},
                      "ml3": {"anunciante": "", "por_mes": {}}})
    ok("soma por mês, e marca o mês parcial (conta com anunciante e sem o mês)",
       _s == {1: 12.5, 2: 5.0} and _f == {2})

    # A JANELA DE 90 DIAS (09/11), pela cadeia: um ML de mentira que recusa
    # como o de verdade ("You cannot request metrics with a date greater than
    # 90 days"), e os meses de `periodos` passados por `na_janela`.
    from datetime import date as _d9, timedelta as _td9
    _hoje9 = _d9(2026, 11, 9)

    def _ml90(metodo, conta, tok, caminho, params=None, corpo=None, cabecalhos=None):
        if caminho == "/advertising/advertisers":
            return ({"advertisers": [{"advertiser_id": 777, "site_id": "MLB"}]}, "")
        if params["date_from"] < (_hoje9 - _td9(days=90)).isoformat():
            return (None, 'Mercado Livre respondeu 400: "You cannot request metrics with a date '
                          'greater than 90 days"')
        return ({"metrics_summary": {"cost": 10.0}}, "")
    _per, _cor, _fora = na_janela(periodos(2026, 11, 9), _hoje9)
    ok("janela: jan a jul nem são perguntados; ago é puxado para dentro, e é parcial",
       _fora == [1, 2, 3, 4, 5, 6, 7] and _cor == {8} and _per[0][0] == 8
       and _per[0][1] == (_hoje9 - _td9(days=JANELA_DIAS)).isoformat())
    _r9 = ler_conta("ml1", "TOK-ml1", _per, _ml90)
    ok("e o ML real não devolve mais 400: ago a nov respondem", not _r9["avisos"]
       and sorted(_r9["por_mes"]) == [8, 9, 10, 11])
    _r9.update(cortados=_cor, fora_janela=_fora)
    ok("o mês puxado sai como parcial na soma", 8 in por_mes({"ml1": _r9})[1])
    _novas = a_guardar({"ml1": _r9}, 2026, 11, {})
    ok("guardar: só os meses FECHADOS e inteiros (set e out); ago parcial e nov aberto ficam fora",
       _novas == [("ml1", "2026-09", 10.0), ("ml1", "2026-10", 10.0)])
    ok("o que já está guardado com o mesmo valor não regrava",
       a_guardar({"ml1": _r9}, 2026, 11, {"ml1": {9: 10.0, 10: 10.0}}) == [])

    class _AbaF:
        def __init__(self, linhas):
            self.linhas, self.escrito = linhas, None

        def get_all_records(self):
            return self.linhas

        def clear(self):
            pass

        def update(self, v, **k):
            self.escrito = v
    _af = _AbaF([{"conta": "ml1", "mes": "2026-09", "custo": "9", "lido_em": "x"},
                 {"conta": "ml2", "mes": "2026-09", "custo": "5", "lido_em": "x"}])
    _g9 = globals()["_aba"]
    globals()["_aba"] = lambda: _af
    try:
        guardar(_novas, "09/11/2026 11:00")
    finally:
        globals()["_aba"] = _g9
    _volta = guardados_de([dict(zip(_af.escrito[0], l)) for l in _af.escrito[1:]], 2026)
    ok("guardar troca a linha da mesma conta e mês, e não mexe na outra conta",
       _af.escrito[0] == COLUNAS and _volta == {"ml1": {9: 10.0, 10: 10.0}, "ml2": {9: 5.0}})
    globals()["_aba"] = lambda: _AbaF([{"conta": "ml3", "mes": "2026-08", "custo": "7,5"}])
    try:
        guardados.clear()
        _gd = guardados(2026)
    finally:
        globals()["_aba"] = _g9
        guardados.clear()
    ok("guardados lê a aba (vírgula vira número)", _gd == {"ml3": {8: 7.5}})
    _api9 = {"ml1": {"anunciante": "777", "por_mes": {11: 1.0}, "fora_janela": [6]}}
    _cg = com_guardados(_api9, {"ml1": {6: 50.0}})
    ok("o guardado preenche o mês fora da janela, marcado, numa CÓPIA (o original é do cache)",
       _cg["ml1"]["por_mes"] == {11: 1.0, 6: 50.0} and _cg["ml1"]["guardado"] == {6}
       and _api9["ml1"]["por_mes"] == {11: 1.0})

    import inspect as _insp
    ok("o token é buscado FORA da thread", _insp.getsource(buscar).index("_ml.token(")
       < _insp.getsource(buscar).index("ThreadPoolExecutor(")
       and "token(" not in _insp.getsource(ler_conta))
    print(f"\nfalhas: {falhas}")
    raise SystemExit(1 if falhas else 0)
