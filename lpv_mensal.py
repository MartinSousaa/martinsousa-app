"""lpv_mensal.py — o LPV que o Studio CALCULA, mês a mês.

ATÉ 02/10 O LPV ERA DIGITADO
----------------------------
O dono fazia a conta na planilha DIN FINANÇAS e digitava o resultado em
Gestão → Financeiro → LPV Mensal. A conta, conferida contra os números dele
(jan/2026: 3.610,87 + 7.614,05 + 3.262,37 = 14.487,29):

    C.O do mês = saídas por PIX que não são mercadoria
               + compras no cartão que não são mercadoria
               + (o que se pagou de Flex − o reembolso do Flex nas vendas)
    LPV        = C.O do mês ÷ número de vendas do mês

O QUE ENTRA, E DE ONDE VEM
--------------------------
- As saídas: `lancamentos`, com o cadastro de favorecidos aplicado (é a mesma
  leitura da Home). Entra quem `composicao.entra_no_lpv` disser — a regra mora
  lá, num lugar só, e não aqui.
- O reembolso do Flex e as vendas: a BASE DE VENDAS 2026 (`base_vendas.py`),
  colunas REEMBOLSO FLEX e VENDAS.
- A FATURA DO CARTÃO inteira NÃO entra: as compras dela já entram uma a uma.

O QUE ELE NÃO SABE, E DIZ
-------------------------
Saída sem finalidade não entra na conta e sai escrita ao lado do número:
somada calada, ela inventaria custo; jogada fora calada, esconderia custo.
"""

import streamlit as st

import composicao as _comp

def calcular(lancamentos_do_mes, somas_vendas):
    """O LPV de UM mês. Função pura — não lê planilha nenhuma.

    `lancamentos_do_mes`: as linhas de `lancamentos` daquele mês, como
    `lancamentos.carregar` as devolve (valor float, o resto texto).
    `somas_vendas`: o dicionário que `base_vendas.somar` devolve para o mês,
    ou None quando a BASE DE VENDAS não tem o mês.
    """
    por_finalidade, flex_pago, sem_finalidade = {}, 0.0, 0.0
    desconhecidas = {}
    for l in (lancamentos_do_mes or []):
        try:
            v = float(l.get("valor") or 0)
        except (TypeError, ValueError):
            continue
        if v >= 0:
            continue                      # só SAÍDAS, como na DIN FINANÇAS
        fin = str(l.get("finalidade") or "").strip()
        if not fin:
            sem_finalidade += -v
            continue
        if _comp._chave(fin) == "FLEX":
            flex_pago += -v
            continue
        if _comp.entra_no_lpv(fin):
            por_finalidade[fin] = por_finalidade.get(fin, 0.0) + (-v)
            if _comp.lado(fin) == "desconhecida":
                desconhecidas[fin] = round(desconhecidas.get(fin, 0.0) + (-v), 2)

    sv = somas_vendas or {}
    # O reembolso entra pelo tamanho: a coluna pode vir com sinal de entrada
    # ou de saída conforme quem preencheu, e o que importa é quanto voltou.
    reembolso = abs(float(sv.get("reembolso_flex") or 0.0))
    vendas = float(sv.get("vendas") or 0.0)
    saidas = sum(por_finalidade.values())
    flex_liquido = flex_pago - reembolso
    co = saidas + flex_liquido

    motivo = ""
    if not lancamentos_do_mes:
        motivo = "nenhum extrato lançado neste mês"
    elif vendas <= 0:
        motivo = "a BASE DE VENDAS não tem vendas neste mês"
    elif co <= 0:
        # LPV ZERO OU NEGATIVO NÃO EXISTE: é mês com saídas faltando. Em
        # setembro/2026 o reembolso do Flex (planilha) passou o Flex pago
        # (extrato incompleto), o C.O ficou negativo e a Home mostrou LPV de
        # R$ -0,20 e UC de -126 — e a Viabilidade decidiria com isso.
        motivo = ("C.O zero ou negativo — faltam saídas do mês nos extratos "
                  "(o Flex pago, provavelmente)")
    return {
        "por_finalidade": {k: round(v, 2) for k, v in
                           sorted(por_finalidade.items(),
                                  key=lambda kv: -kv[1])},
        "saidas": round(saidas, 2),
        "flex_pago": round(flex_pago, 2),
        "reembolso_flex": round(reembolso, 2),
        "flex_liquido": round(flex_liquido, 2),
        "co": round(co, 2),
        "vendas": vendas,
        "lpv": (round(co / vendas, 2) if not motivo else None),
        "sem_finalidade": round(sem_finalidade, 2),
        # Entraram por não estarem em lista nenhuma: a tela as nomeia, para
        # o dono dizer se alguma é mercadoria, custo fixo ou imposto.
        "desconhecidas": desconhecidas,
        "motivo": motivo,
    }


@st.cache_data(ttl=120, show_spinner=False)
def do_ano(ano):
    """({mes: calcular(...)}, erro). Uma leitura de cada fonte para o ano todo.

    Cache de 120s, o mesmo de `lancamentos.carregar`: a tela de LPV redesenha
    a cada tecla digitada nos campos do mês, e reaplicar o cadastro de
    favorecidos ao ano inteiro a cada tecla seria trabalho jogado fora.
    """
    import lancamentos as _lan
    import base_vendas as _bv
    prefixo = f"{int(ano):04d}-"
    do_ano_todo = _lan.aplicar_cadastro(
        [l for l in _lan.carregar()
         if str(l.get("data", "")).startswith(prefixo)])
    somas, erro = _bv.somas_por_mes()
    fora = {}
    for m in range(1, 13):
        alvo = f"{int(ano):04d}-{m:02d}"
        do_mes = [l for l in do_ano_todo
                  if str(l.get("data", "")).startswith(alvo)]
        fora[m] = calcular(do_mes, (somas or {}).get((int(ano), m)))
    return fora, erro


def mes_fechado(ano, mes, hoje):
    """O mês já terminou? Mês corrente tem LPV parcial e não se grava."""
    return (int(ano), int(mes)) < (hoje.year, hoje.month)


if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    import base_vendas as _bv
    from datetime import datetime as _dt, date as _date

    # A ENTRADA VEM DO SISTEMA. As vendas saem de `base_vendas.somar` com os
    # nomes de coluna da BASE DE VENDAS; as saídas, no formato que
    # `lancamentos.carregar` devolve (valor float, data "AAAA-MM-DD").
    COLS = ["MÊS", "MÊS/ANO", "Data", "FAT TOTAL", "VENDAS", "REEMBOLSO FLEX"]
    BASE = [{"Data": _dt(2026, 1, 5), "MÊS/ANO": "jan2026", "FAT TOTAL": 100,
             "VENDAS": 400, "REEMBOLSO FLEX": 1442.77},
            {"Data": _dt(2026, 1, 20), "MÊS/ANO": "jan2026", "FAT TOTAL": 100,
             "VENDAS": 379, "REEMBOLSO FLEX": 2000.00},
            {"Data": _dt(2026, 2, 1), "MÊS/ANO": "fev2026", "FAT TOTAL": 100,
             "VENDAS": 999, "REEMBOLSO FLEX": 9999}]
    _sv_jan = _bv.somar(BASE, COLS, 2026, 1)
    ok("base_vendas soma o reembolso do Flex do mês",
       round(_sv_jan["reembolso_flex"], 2) == 3442.77)

    def L(valor, fin, data="2026-01-10"):
        return {"id": f"{fin}{valor}", "data": data, "valor": float(valor),
                "finalidade": fin, "favorecido": "TESTE LPV", "fixada": "",
                "descricao": "", "observacao": ""}

    # JANEIRO DO DONO: PIX 3.610,87 + cartão 7.614,05 + Flex pago 6.705,14
    # menos reembolso 3.442,77 = C.O 14.487,29 (o print da DIN FINANÇAS).
    JAN = [L(-3610.87, "OUTROS"), L(-7614.05, "ADS"), L(-6705.14, "FLEX"),
           L(-50000.00, "MERCADORIA"), L(-900.00, "COMPRA DE MERCADORIA"),
           L(-2500.00, "CUSTO FIXO"), L(-300.00, "SERVIÇO"),
           L(-1200.00, "IMPOSTO"), L(-90000.00, "TRANSFERENCIA ENTRE CONTAS"),
           L(-7614.05, "FATURA DO CARTÃO"), L(-4000.00, "FOLHA"),
           L(5000.00, "MERCADO LIVRE"), L(-12.34, ""),
           # Estorno de ADS: ENTRADA com finalidade que entra no LPV. A
           # DIN FINANÇAS soma só SAÍDAS — ele não abate o custo.
           L(500.00, "ADS")]
    r = calcular(JAN, _sv_jan)
    ok("o C.O de janeiro bate com a planilha do dono (14.487,29)",
       r["co"] == 14487.29)
    ok("flex líquido = pago − reembolso", r["flex_liquido"] == 3262.37)
    ok("as vendas vêm da BASE DE VENDAS", r["vendas"] == 779)
    ok("LPV = C.O ÷ vendas", r["lpv"] == round(14487.29 / 779, 2))
    ok("mercadoria (as duas grafias), custo fixo, assinatura, imposto, "
       "folha, transferência e fatura inteira ficam fora",
       set(r["por_finalidade"]) == {"OUTROS", "ADS"})
    ok("entrada (mesmo com finalidade do LPV) não reduz o custo",
       r["saidas"] == 11224.92)
    ok("saída sem finalidade não entra, e sai escrita",
       r["sem_finalidade"] == 12.34)

    r2 = calcular([L(-99.0, "PÁGINA DO ML"), L(-10.0, "BOLETO"),
                   L(-2.5, "TARIFA BANCÁRIA")], {"vendas": 10})
    ok("página do ML, boleto e tarifa bancária entram", r2["co"] == 111.5)
    r3 = calcular([L(-100.0, "FLEX")], {"vendas": 10,
                                        "reembolso_flex": -300.0})
    ok("reembolso maior que o pago deixa o Flex negativo, como em março",
       r3["flex_liquido"] == -200.0 and r3["co"] == -200.0)
    _r_nova = calcular([L(-50.0, "MOTOBOY")], {"vendas": 10})
    ok("finalidade nova entra no C.O e sai nomeada",
       _r_nova["co"] == 50.0 and _r_nova["desconhecidas"] == {"MOTOBOY": 50.0})
    ok("mês sem venda não inventa LPV",
       calcular([L(-1.0, "ADS")], {"vendas": 0})["lpv"] is None)
    ok("mês sem extrato não inventa LPV",
       calcular([], _sv_jan)["lpv"] is None)
    ok("C.O negativo (extrato incompleto) não vira LPV negativo",
       calcular([L(-100.0, "FLEX")], {"vendas": 10, "reembolso_flex": 900.0})
       ["lpv"] is None)
    ok("e diz por quê", "negativo" in calcular(
        [L(-100.0, "FLEX")], {"vendas": 10, "reembolso_flex": 900.0})["motivo"])
    ok("mês fora da BASE DE VENDAS não inventa LPV",
       calcular([L(-1.0, "ADS")], None)["lpv"] is None)

    # A CADEIA INTEIRA: `do_ano` lê `lancamentos.carregar`, aplica o cadastro
    # de favorecidos de verdade e lê `base_vendas.somas_por_mes`. Só as duas
    # leituras de planilha são trocadas.
    import lancamentos as _lan
    import favorecidos as _fv
    _g = (_lan.carregar, _bv.somas_por_mes, _fv._aba)

    def _sem_planilha():
        raise RuntimeError("sem planilha no auto-teste")

    _lan.carregar = lambda: JAN + [L(-1.0, "ADS", "2025-12-31"),
                                   L(-7.0, "ADS", "2026-02-03")]
    _bv.somas_por_mes = lambda: ({(2026, 1): _sv_jan,
                                  (2026, 2): _bv.somar(BASE, COLS, 2026, 2)},
                                 "")
    _fv._aba = _sem_planilha
    try:
        _fv.carregar.clear()
        do_ano.clear()
        _ano, _erro = do_ano(2026)
        ok("pela cadeia, janeiro dá o mesmo C.O", _ano[1]["co"] == 14487.29)
        ok("e o ano anterior não vaza para janeiro",
           _ano[1]["por_finalidade"].get("ADS") == 7614.05)
        ok("fevereiro sai separado", _ano[2]["saidas"] == 7.0)
        ok("mês sem nada diz por quê", _ano[5]["lpv"] is None
           and "extrato" in _ano[5]["motivo"])
    finally:
        _lan.carregar, _bv.somas_por_mes, _fv._aba = _g
        _fv.carregar.clear()
        do_ano.clear()

    ok("setembro está fechado em outubro",
       mes_fechado(2026, 9, _date(2026, 10, 2)))
    ok("o mês corrente não está fechado",
       not mes_fechado(2026, 10, _date(2026, 10, 2)))

    print("\nfalhas:", falhas)
    raise SystemExit(1 if falhas else 0)
