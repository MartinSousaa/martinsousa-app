"""promocoes_auto.py — o que as promoções do ML fazem sozinhas (dono, 28/10).

TRÊS PEDIDOS, UMA ROTINA POR DIA
--------------------------------
1. Sinalizar o anúncio que SAIU de promoção e não voltou ("finalizadas sem
   recriar"). O ML só mostra o que está ativo; quem lembra o que estava é o
   Studio, numa aba da planilha (`promo_vistos`), atualizada a cada rodada.
2. Recriar o DESCONTO DO VENDEDOR (PRICE_DISCOUNT) dos anúncios da lista
   recorrente quando ele expira. Campanha do ML não se recria: ela vem dele.
3. Entrar sozinho nos convites cujo desconto, no BOLSO DO VENDEDOR, fique
   igual ou abaixo do % máximo do anúncio.

A LISTA é a aba `promo_regras` da planilha, uma linha por produto (o título,
que junta as quatro contas): `titulo`, `pct_maximo`, `recriar_pct`,
`recriar_dias`, `estoque_relampago`, `ativo`. Relâmpago só entra com o
estoque da linha preenchido — o ML exige reservar estoque.

O DESCONTO QUE CONTA (dono, 28/10)
----------------------------------
"Se o sistema está dando 11%, mas o reembolso da tarifa faz cair para 10%,
volta a se enquadrar." O % comparado ao máximo é o que sai do bolso do
vendedor: preço cheio menos o que o comprador paga, menos o que o ML devolve
— a parte que ele banca (`meli_percentage`) e o desconto na tarifa
(`discount_meli_boost_amount`, presente quando `boosted_offer` é true; ver
a documentação de campanhas-tradicionais, campanhas-smart-price-matching e
gerenciar-ofertas, lidas em 28/10). A amostra real da ML1 não trouxe esses
campos de boost: a fórmula está pela documentação, e a tela mostra o valor de
cada parte para quem confere.

SIMULAÇÃO PRIMEIRO
------------------
O modo nasce SIMULAÇÃO: a rodada decide, registra em `promo_log` e não grava
nada no ML. Só o dono liga, na tela. Combinado: uma semana simulando.
"""
import json
from datetime import timedelta

ABA_REGRAS = "promo_regras"
ABA_VISTOS = "promo_vistos"
ABA_LOG = "promo_log"
ABA_ESTADO = "promo_auto_estado"
COLUNAS_REGRAS = ["titulo", "pct_maximo", "recriar_pct", "recriar_dias",
                  "estoque_relampago", "ativo"]
COLUNAS_VISTOS = ["chave", "conta", "item", "titulo", "promocao", "tipo", "fim",
                  "situacao", "visto_em", "saiu_em"]
COLUNAS_LOG = ["quando", "modo", "acao", "conta", "item", "titulo", "promocao",
               "pct", "pct_efetivo", "resultado"]
HORA_DA_RODADA = 8          # a primeira passada da rotina depois das 8h
TIPOS_COM_ESTOQUE = ("LIGHTNING", "SMART_LIGHTNING")


# ── Puras ─────────────────────────────────────────────────────────────────────
def _f(v):
    try:
        return float(str(v).replace(",", ".")) if str(v).strip() else 0.0
    except (TypeError, ValueError):
        return 0.0


def reembolso(oferta, base, com_boost=True):
    """R$ que o ML devolve ao vendedor nesta oferta. Pura.

    O boost é desconto que o ML põe POR CIMA do preço que o vendedor deu, e
    devolve na tarifa (documentação, "campos de boost"): ele entra quando se
    mede o preço que o COMPRADOR paga, e não quando se mede o preço que o
    vendedor está escolhendo — ali ele ainda não existe."""
    parte_ml = base * _f(oferta.get("meli_percentage")) / 100
    tarifa = (_f(oferta.get("discount_meli_boost_amount"))
              if com_boost and oferta.get("boosted_offer") else 0.0)
    return round(parte_ml + tarifa, 2)


def efetivo(oferta, preco=None):
    """% do preço cheio que sai do bolso do vendedor. Pura.

    `preco` é o preço que o VENDEDOR está escolhendo (o da tela): o boost
    ainda não existe nele. Sem `preco`, mede o que o ML mandou — e, com boost,
    o que o comprador paga (`total_price_for_boosted_offer`) menos o que o ML
    devolve na tarifa. No exemplo do dono: o comprador vê 11%, o ML devolve 1%
    na tarifa, o bolso fica com 10%."""
    import promocoes_ml as _pm
    base = _pm.preco_hoje(oferta)
    if not base:
        return 0.0
    if preco is not None:
        return round((base - preco - reembolso(oferta, base, com_boost=False)) / base * 100, 2)
    if preco is None:
        preco = (_f(oferta.get("total_price_for_boosted_offer"))
                 if oferta.get("boosted_offer") else 0.0) or _f(oferta.get("price"))
        if not preco:
            return 0.0
    return round((base - preco - reembolso(oferta, base)) / base * 100, 2)


def ler_regras(linhas):
    """{titulo normalizado: regra} da aba `promo_regras`. Linha sem título
    ou com `ativo` = Não fica de fora. Pura."""
    import promocoes_ml as _pm
    saida = {}
    for r in linhas or []:
        t = str(r.get("titulo", "")).strip()
        if not t or str(r.get("ativo", "Sim")).strip().lower() in ("não", "nao", "n", "0", "false"):
            continue
        dias = int(_f(r.get("recriar_dias")) or _pm.DIAS_MAX)
        saida[_pm.normalizar(t)] = {
            "titulo": t, "pct_maximo": _f(r.get("pct_maximo")),
            "recriar_pct": _f(r.get("recriar_pct")),
            "recriar_dias": max(1, min(dias, _pm.DIAS_MAX)),
            "estoque_relampago": int(_f(r.get("estoque_relampago")))}
    return saida


def decidir_entradas(produtos, regras):
    """[(oferta, pct, estoque, motivo_ou_'')] para os convites dos produtos com
    % máximo. motivo '' = entra. Pura.

    Na que aceita %, usa o sugerido do ML; se ele passar do máximo, desce
    até onde o bolso fica no máximo (o reembolso do ML vem somado). Na que o
    ML define, entra se o efetivo couber."""
    import promocoes_ml as _pm
    saida = []
    for pr in produtos:
        rg = regras.get(pr["chave"])
        if not rg or rg["pct_maximo"] <= 0:
            continue
        for cx in pr["promocoes"]:
            for l in cx["linhas"]:
                est = None
                if l["tipo"] in TIPOS_COM_ESTOQUE:
                    est = rg["estoque_relampago"] or None
                    if not est:
                        saida.append((l, None, None, "relâmpago sem estoque na lista"))
                        continue
                if cx["editavel"]:
                    base = _pm.preco_hoje(l)
                    reemb_pct = (reembolso(l, base, com_boost=False) / base * 100
                                 if base else 0.0)
                    pct = min(_pm.pct_sugerido(l) or rg["pct_maximo"],
                              round(rg["pct_maximo"] + reemb_pct, 1))
                    preco, erro = _pm.validar(l, pct, est)
                    ef = efetivo(l, preco) if preco else 0.0
                else:
                    pct = _pm.pct_sugerido(l)
                    preco, erro = _pm.validar(l, None, est)
                    ef = efetivo(l)
                if not erro and ef > rg["pct_maximo"] + 1e-9:
                    erro = f"no bolso {ef:.1f}% passa do máximo {rg['pct_maximo']:g}%"
                saida.append((dict(l, _preco=preco, _efetivo=ef), pct, est, erro))
    return saida


def decidir_recriacoes(anuncios_por_titulo, ativos_do_vendedor, regras, hoje):
    """[(conta, item, titulo, pct, inicio, fim)] do desconto do vendedor que
    precisa ser recriado. Pura.

    anuncios_por_titulo {titulo normalizado: {conta: [item]}}
    ativos_do_vendedor  {(conta, item)} com PRICE_DISCOUNT ativo ou programado
    """
    saida = []
    for chave, rg in regras.items():
        if rg["recriar_pct"] <= 0:
            continue
        for conta, itens in sorted((anuncios_por_titulo.get(chave) or {}).items()):
            for it in itens:
                if (conta, it) in ativos_do_vendedor:
                    continue
                saida.append((conta, it, rg["titulo"], rg["recriar_pct"], hoje,
                              hoje + timedelta(days=rg["recriar_dias"] - 1)))
    return saida


def atualizar_vistos(antes, andamento, hoje_txt):
    """O retrato novo de quem está em promoção. Pura.

    antes     {chave: linha} da aba `promo_vistos`
    andamento [oferta] em andamento agora (com conta, item, titulo, nome, tipo, fim)
    Quem estava "em promoção" e não está mais vira "saiu" (com a data); quem
    volta, volta. Quem já tinha saído continua sinalizado até voltar."""
    novo = {k: dict(v) for k, v in (antes or {}).items()}
    agora = set()
    for o in andamento:
        k = f"{o['conta']}|{o['item']}"
        agora.add(k)
        novo[k] = {"chave": k, "conta": o["conta"], "item": o["item"],
                   "titulo": o.get("titulo", ""), "promocao": o.get("nome", ""),
                   "tipo": o.get("tipo", ""), "fim": str(o.get("fim", ""))[:10],
                   "situacao": "em promoção", "visto_em": hoje_txt, "saiu_em": ""}
    for k, v in novo.items():
        if k not in agora and v.get("situacao") == "em promoção":
            v["situacao"], v["saiu_em"] = "saiu", hoje_txt
    return novo


def finalizadas(vistos):
    """As linhas que saíram e não voltaram, da saída mais recente. Pura."""
    return sorted([v for v in (vistos or {}).values() if v.get("situacao") == "saiu"],
                  key=lambda v: (v.get("saiu_em", ""), v.get("titulo", "")), reverse=True)


def deve_rodar(estado, agora):
    """Uma rodada por dia, na primeira passada depois das 8h. Pura."""
    return agora.hour >= HORA_DA_RODADA and estado.get("ultimo_dia") != agora.strftime("%Y-%m-%d")


# ── Planilha ──────────────────────────────────────────────────────────────────
def _aba(nome, colunas):
    import sheets as _sh
    pl = _sh.planilha()
    try:
        return pl.worksheet(nome)
    except Exception:
        a = pl.add_worksheet(title=nome, rows=200, cols=max(len(colunas), 1))
        a.append_row(colunas, value_input_option="RAW")
        return a


def carregar_regras():
    try:
        return _aba(ABA_REGRAS, COLUNAS_REGRAS).get_all_records()
    except Exception:
        return []


def gravar_regras(linhas):
    a = _aba(ABA_REGRAS, COLUNAS_REGRAS)
    a.clear()
    a.update([COLUNAS_REGRAS] + [[r.get(c, "") for c in COLUNAS_REGRAS] for r in linhas],
             value_input_option="RAW")


def carregar_vistos():
    try:
        return {str(r.get("chave")): r for r in _aba(ABA_VISTOS, COLUNAS_VISTOS).get_all_records()
                if r.get("chave")}
    except Exception:
        return {}


def _gravar_vistos(vistos):
    a = _aba(ABA_VISTOS, COLUNAS_VISTOS)
    a.clear()
    a.update([COLUNAS_VISTOS] + [[str(v.get(c, "")) for c in COLUNAS_VISTOS]
                                 for v in vistos.values()], value_input_option="RAW")


def carregar_log(n=200):
    try:
        return _aba(ABA_LOG, COLUNAS_LOG).get_all_records()[-n:][::-1]
    except Exception:
        return []


def _registrar(linhas):
    if linhas:
        try:
            _aba(ABA_LOG, COLUNAS_LOG).append_rows(linhas, value_input_option="RAW")
        except Exception:
            pass


def estado():
    try:
        return json.loads(_aba(ABA_ESTADO, ["estado"]).acell("A2").value or "{}")
    except Exception:
        return {}


def gravar_estado(e):
    try:
        _aba(ABA_ESTADO, ["estado"]).update_acell("A2", json.dumps(e, ensure_ascii=False))
    except Exception:
        pass


def ligado():
    """O modo real só vale com o dono tendo ligado na tela."""
    return estado().get("modo") == "ligado"


# ── A rodada ──────────────────────────────────────────────────────────────────
def rodar(agora, simular=False, log=print, forcar=False):
    """Lê as quatro contas, atualiza o retrato, decide e (no modo ligado) grava.

    Devolve um resumo. Cada decisão vai ao `promo_log`, inclusive as que não
    entraram — com o motivo."""
    import promocoes_ml as _pm
    import ml_api as _ml
    est = estado()
    if not forcar and not deve_rodar(est, agora):
        return {"rodou": False}
    real = (est.get("modo") == "ligado") and not simular
    modo = "real" if real else "simulação"
    lidas = _pm.ler_todas()
    dados = _pm.agrupar(lidas)
    hoje_txt = agora.strftime("%Y-%m-%d")
    quando = agora.strftime("%Y-%m-%d %H:%M")
    regras = ler_regras(carregar_regras())

    # O desconto do vendedor não aparece nas listas de campanha: ele é lido
    # por anúncio, e só dos que estão na lista recorrente.
    por_titulo = {}
    for pr in dados["produtos"]:
        por_titulo.setdefault(pr["chave"], {}).update(pr["anuncios"])
    for o in dados["andamento"]:
        lst = por_titulo.setdefault(_pm.normalizar(o["titulo"]), {}).setdefault(o["conta"], [])
        if o["item"] not in lst:
            lst.append(o["item"])
    ativos_vend, andamento = set(), list(dados["andamento"])
    for chave, rg in regras.items():
        if rg["recriar_pct"] <= 0:
            continue
        for conta, itens in (por_titulo.get(chave) or {}).items():
            for it in itens:
                resp, erro = _ml.get(conta, f"/seller-promotions/items/{it}", {"app_version": "v2"})
                for p in resp if isinstance(resp, list) else []:
                    if (isinstance(p, dict) and p.get("type") == "PRICE_DISCOUNT"
                            and p.get("status") in ("started", "pending")):
                        ativos_vend.add((conta, it))
                        andamento.append({"conta": conta, "item": it, "titulo": rg["titulo"],
                                          "nome": _pm.NOMES["PRICE_DISCOUNT"],
                                          "tipo": "PRICE_DISCOUNT",
                                          "fim": p.get("finish_date", "")})

    vistos = atualizar_vistos(carregar_vistos(), andamento, hoje_txt)
    if not simular:
        _gravar_vistos(vistos)

    log_linhas, feitos = [], 0
    for of, pct, estq, motivo in decidir_entradas(dados["produtos"], regras):
        ok, res = False, motivo
        if not motivo:
            if real:
                cam, par, corpo = _pm.pedido_de_entrada(of, of.get("_preco"), estq)
                _, erro = _ml.escrever(of["conta"], "POST", cam, par, corpo)
                ok, res = not erro, (erro or "entrou")
            else:
                ok, res = True, "entraria"
        feitos += ok and real
        log_linhas.append([quando, modo, "entrar", of["conta"], of["item"], of.get("titulo", ""),
                           of.get("nome", ""), pct, of.get("_efetivo", ""), res])
    for conta, it, titulo, pct, ini, fim in decidir_recriacoes(por_titulo, ativos_vend,
                                                               regras, agora.date()):
        of, erro = _pm.faixa_do_desconto(conta, it)
        preco = None
        if not erro:
            preco, erro = _pm.validar(of, pct)
        res = erro or ("recriado" if real else "recriaria")
        if not erro and real:
            cam, par, corpo = _pm.pedido_de_entrada(of, preco, inicio=ini.isoformat(),
                                                    fim=fim.isoformat())
            _, e2 = _ml.escrever(conta, "POST", cam, par, corpo)
            res = e2 or "recriado"
            feitos += not e2
        log_linhas.append([quando, modo, "recriar", conta, it, titulo, "Desconto do vendedor",
                           pct, "", res])
    if not simular:
        _registrar(log_linhas)
        est["ultimo_dia"] = hoje_txt
        gravar_estado(est)
    log(f"Promoções: {len(log_linhas)} decisão(ões) em modo {modo}, {feitos} gravada(s) no ML; "
        f"{len(finalizadas(vistos))} anúncio(s) fora de promoção.")
    return {"rodou": True, "modo": modo, "decisoes": log_linhas, "feitos": feitos}


def main(simular=False, agora=None, log=print):
    """Chamada pelo `fechar_expediente` a cada passada; roda uma vez por dia."""
    import placar_core as _pc
    from datetime import datetime
    agora = agora or datetime.now(_pc.FUSO)
    return rodar(agora, simular=simular, log=log)


if __name__ == "__main__":
    from datetime import date, datetime
    import promocoes_ml as _pm
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # O BOLSO DO VENDEDOR, com as respostas na forma real do ML (amostra da ML1
    # e os campos de boost da documentação).
    _smart = {"tipo": "SMART", "price": 130.94, "original_price": 134.99,
              "meli_percentage": 0.5, "seller_percentage": 2.5}
    ok("automática: o bolso é o % do vendedor (2,5%), não o total de 3%",
       abs(efetivo(_smart) - 2.5) < 0.05)
    _deal = {"tipo": "DEAL", "original_price": 100.0, "price": 90.0, "boosted_offer": True,
             "discount_meli_boost_amount": 1.0, "total_price_for_boosted_offer": 89.0}
    ok("o exemplo do dono: o comprador vê 11%, o ML devolve R$ 1 na tarifa → 10% no bolso",
       efetivo(_deal) == 10.0)
    ok("o preço que o vendedor escolhe não desconta o boost, que ainda não existe",
       efetivo(_deal, 89.0) == 11.0)
    ok("sem boost o reembolso é zero", reembolso({"boosted_offer": False,
                                                  "discount_meli_boost_amount": 5}, 100) == 0)

    _rg = ler_regras([
        {"titulo": "Escultura Cavaleiro Medieval", "pct_maximo": "10", "recriar_pct": "8",
         "recriar_dias": "30", "estoque_relampago": "", "ativo": "Sim"},
        {"titulo": "Desligado", "pct_maximo": 50, "ativo": "Não"},
        {"titulo": "", "pct_maximo": 50}])
    _k = _pm.normalizar("Escultura Cavaleiro Medieval")
    ok("regras: lê o título normalizado, ignora inativo e vazio, e corta os dias em 14",
       list(_rg) == [_k] and _rg[_k]["recriar_dias"] == 14 and _rg[_k]["pct_maximo"] == 10.0)

    # PELA CADEIA: as ofertas passam pelo `agrupar` de verdade.
    _base = {"promo_id": "P1", "status": "candidate", "original_price": 100.0}
    _lidas = {"ml1": {"titulos": {"A": {"title": "Escultura Cavaleiro Medieval"}},
                      "ofertas": [
        dict(_base, item="A", tipo="DEAL", nome="11.11", suggested_discounted_price=88.0,
             min_discounted_price=20, max_discounted_price=98, meli_percentage=1.0),
        dict(_base, item="A", tipo="SMART", nome="Impulsione", price=85.0, offer_id="O1",
             meli_percentage=1.0, seller_percentage=14.0),
        dict(_base, item="A", tipo="LIGHTNING", nome="Relâmpago", suggested_discounted_price=90.0,
             min_discounted_price=20, stock={"min": 5, "max": 50}, offer_id="R1")]},
              "ml2": {"titulos": {"B": {"title": "escultura cavaleiro medieval"}},
                      "ofertas": [dict(_base, item="B", tipo="DEAL", nome="11.11",
                                       suggested_discounted_price=95.0,
                                       min_discounted_price=20, max_discounted_price=98)]}}
    _g = _pm.agrupar(_lidas)
    _d = {(o["conta"], o["tipo"]): (pct, motivo, o.get("_efetivo"))
          for o, pct, est, motivo in decidir_entradas(_g["produtos"], _rg)}
    ok("campanha: sugerido de 12% com 1% bancado pelo ML passa do máximo de 10% — "
       "desce para 11% dados, 10% no bolso, e entra",
       _d[("ml1", "DEAL")][0] == 11.0 and _d[("ml1", "DEAL")][1] == ""
       and _d[("ml1", "DEAL")][2] == 10.0)
    ok("campanha que já cabe (5%) entra com o sugerido do ML",
       _d[("ml2", "DEAL")] == (5.0, "", 5.0))
    ok("automática com 14% no bolso NÃO entra num máximo de 10%, e diz por quê",
       "passa do máximo" in _d[("ml1", "SMART")][1])
    ok("relâmpago sem estoque na lista fica de fora, com o motivo",
       _d[("ml1", "LIGHTNING")][1] == "relâmpago sem estoque na lista")

    _hoje = date(2026, 10, 28)
    _rc = decidir_recriacoes({_k: {"ml1": ["A"], "ml2": ["B"]}}, {("ml2", "B")}, _rg, _hoje)
    ok("recriar: só a conta sem desconto ativo, com o % e os 14 dias da lista",
       _rc == [("ml1", "A", "Escultura Cavaleiro Medieval", 8.0, _hoje,
                _hoje + timedelta(days=13))])

    _v1 = atualizar_vistos({}, [{"conta": "ml1", "item": "A", "titulo": "T", "nome": "11.11",
                                 "tipo": "DEAL", "fim": "2026-11-12T03:00:00Z"}], "2026-10-27")
    _v2 = atualizar_vistos(_v1, [], "2026-10-28")
    ok("finalizada: estava em promoção, saiu, e é sinalizada com a data",
       [(v["item"], v["saiu_em"]) for v in finalizadas(_v2)] == [("A", "2026-10-28")])
    _v3 = atualizar_vistos(_v2, [], "2026-10-29")
    ok("finalizada: continua sinalizada nos dias seguintes, com a data em que saiu",
       finalizadas(_v3)[0]["saiu_em"] == "2026-10-28")
    _v4 = atualizar_vistos(_v3, [{"conta": "ml1", "item": "A", "titulo": "T", "nome": "Black",
                                  "tipo": "DEAL", "fim": ""}], "2026-10-30")
    ok("finalizada: voltou para promoção, sai da lista", finalizadas(_v4) == [])

    _F = __import__("placar_core").FUSO
    ok("uma rodada por dia, depois das 8h",
       deve_rodar({}, datetime(2026, 10, 28, 8, 5, tzinfo=_F))
       and not deve_rodar({}, datetime(2026, 10, 28, 7, 55, tzinfo=_F))
       and not deve_rodar({"ultimo_dia": "2026-10-28"}, datetime(2026, 10, 28, 15, 0, tzinfo=_F)))

    # A RODADA INTEIRA EM SIMULAÇÃO não grava nada no ML — nem com o modo
    # ligado, quando `simular` vem da rotina. A rede e a planilha são dubladas.
    import ml_api as _ml_t
    _g_t = (_pm.ler_todas, _ml_t.escrever, _ml_t.get, globals()["carregar_regras"],
            globals()["carregar_vistos"], globals()["estado"], _pm.faixa_do_desconto)
    _escritas = []
    try:
        _pm.ler_todas = lambda: _lidas
        _ml_t.escrever = lambda *a, **k: (_escritas.append(a), ({}, ""))[1]
        _ml_t.get = lambda c, cam, p=None: ([], "")
        globals()["carregar_regras"] = lambda: [{"titulo": "Escultura Cavaleiro Medieval",
                                                 "pct_maximo": 10, "recriar_pct": 8}]
        globals()["carregar_vistos"] = lambda: {}
        globals()["estado"] = lambda: {"modo": "ligado"}
        _pm.faixa_do_desconto = lambda c, i: ({"item": i, "tipo": "PRICE_DISCOUNT", "conta": c,
                                               "promo_id": "", "original_price": 100.0,
                                               "min_discounted_price": 20,
                                               "max_discounted_price": 95}, "")
        _r = rodar(datetime(2026, 10, 28, 9, 0, tzinfo=_F), simular=True, log=lambda *a: None)
        ok("rodada simulada: decide entradas e recriações e NÃO escreve no ML",
           _r["modo"] == "simulação" and not _escritas
           and {x[2] for x in _r["decisoes"]} == {"entrar", "recriar"}
           and any(x[9] == "entraria" for x in _r["decisoes"])
           and any(x[9] == "recriaria" for x in _r["decisoes"]))
        globals()["estado"] = lambda: {}
        _r2 = rodar(datetime(2026, 10, 28, 9, 0, tzinfo=_F), simular=True, forcar=True,
                    log=lambda *a: None)
        ok("modo que nunca foi ligado é simulação", _r2["modo"] == "simulação")
    finally:
        (_pm.ler_todas, _ml_t.escrever, _ml_t.get, globals()["carregar_regras"],
         globals()["carregar_vistos"], globals()["estado"], _pm.faixa_do_desconto) = _g_t
    # A PLANILHA: a lista volta como foi gravada, nas colunas de COLUNAS_REGRAS,
    # e o modo gravado é o que `ligado` lê. A aba é dublada em memória.
    class _AbaFalsa:
        def __init__(self):
            self.linhas, self.celula = [], ""

        def clear(self):
            self.linhas = []

        def update(self, linhas, **k):
            self.linhas = linhas

        def get_all_records(self):
            cab = self.linhas[0]
            return [dict(zip(cab, l)) for l in self.linhas[1:]]

        def acell(self, a):
            return type("C", (), {"value": self.celula})()

        def update_acell(self, a, v):
            self.celula = v
    _abas = {}
    _g_aba = globals()["_aba"]
    globals()["_aba"] = lambda nome, cols: _abas.setdefault(nome, _AbaFalsa())
    try:
        gravar_regras([{"titulo": "Caneca", "pct_maximo": 12, "ativo": "Sim"}])
        _lr = carregar_regras()
        ok("lista: grava e relê nas colunas de COLUNAS_REGRAS, campo vazio fica vazio",
           list(_lr[0]) == COLUNAS_REGRAS and _lr[0]["pct_maximo"] == 12
           and _lr[0]["recriar_pct"] == "")
        ok("modo: nunca ligado é simulação", not ligado())
        gravar_estado({"modo": "ligado", "ultimo_dia": "2026-10-28"})
        ok("modo: gravar_estado liga, e o dia da rodada fica guardado",
           ligado() and estado()["ultimo_dia"] == "2026-10-28")
    finally:
        globals()["_aba"] = _g_aba
    ok("a rodada é depois das 8h (HORA_DA_RODADA)", HORA_DA_RODADA == 8)

    print("\nfalhas:", falhas)
    raise SystemExit(1 if falhas else 0)
