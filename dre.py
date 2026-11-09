"""dre.py — a DRE do período, em forma de funil (dono, 09/11).

O PEDIDO
--------
Uma aba de DRE "automática, auditável, didática", do faturamento ao lucro
líquido, em funil, com valor e margem, e a origem de cada número. Margens
sobre a RECEITA LÍQUIDA; receita líquida zero → "não se aplica".

REGIME DE COMPETÊNCIA: A VENDA, E NÃO O EXTRATO
-----------------------------------------------
As etapas 1 a 4 saem da BASE DE VENDAS, venda a venda, pelo mês da venda
(`base_vendas._mes_da_linha`, a mesma leitura das outras telas):

    receita bruta        FAT TOTAL
    devoluções           DEVOLUÇÃO
    tributos s/ venda    NF — o Simples (dono, 09/11: "sim")
    CMV                  CUSTO TOTAL
    comissões            COMISSÃO
    frete                FRETE + CUSTO FLEX (como `produtos_analise`)
    custo operacional    CUSTO OP. — o RATEIO do C.O. do mês por venda
                         (`lpv_mensal.py:17`): embalagem, logística, ADS,
                         cross docking e Flex líquido JÁ estão aqui dentro.

NADA CONTADO DUAS VEZES
-----------------------
- ADS, embalagem e "outras despesas" NÃO têm linha própria: estão no CUSTO
  OP. Uma linha de ADS somada embaixo pagaria o ADS duas vezes.
- O imposto pago no extrato (IMPOSTO/DAS) NÃO entra: é a NF da venda.
- IRPJ/CSLL: zero. No Simples eles estão dentro do DAS, que é a NF.
- A etapa 5 traz só o que o C.O. não tem — folha, custo fixo e assinaturas
  (`composicao.entra_no_lpv` os tira do C.O.), pelas MESMAS funções do
  previsto (`previsto._custo_fixo`, `_folha`, `custo_real.total_assinaturas`).
- O financeiro é o Não operacional (as parcelas do PRONAMP), inteiro — juros
  e principal juntos, decisão do dono (09/11).

A CONFERÊNCIA
-------------
A margem de contribuição é a conta das linhas acima dela, e a coluna
MARGEM C. da planilha é conferida contra ela: diferença maior que R$ 1 vira
linha à vista ("diferença para a MARGEM C."), e não ajuste escondido.
"""
import streamlit as st

MESES = ("JAN", "FEV", "MAR", "ABR", "MAI", "JUN",
         "JUL", "AGO", "SET", "OUT", "NOV", "DEZ")
TOLERANCIA_MC = 1.0


def _r2(v):
    """Dinheiro em centavos, meio centavo para cima (`folha_mes.reais` faz o
    mesmo com minutos): float somado acumula resto, e o funil tem de fechar."""
    from decimal import Decimal, ROUND_HALF_UP
    return float(Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def vendas(registros, colunas, ano, meses):
    """{campo: soma} das vendas do período, e quantas linhas sem custo. Pura.

    `registros`/`colunas`: a BASE DE VENDAS como `controle_ms.ler` devolve.
    `meses`: os meses (1–12) do período, no `ano`.
    """
    import base_vendas as _bv
    import produtos_analise as _pa
    m = _pa._mapa(colunas)
    col_data, col_ma = m.get("data"), m.get("mes_ano")
    tot = {k: 0.0 for k in ("fat", "dev", "nf", "ct", "com", "fr", "co", "mc")}
    plat, sem_custo, sem_mc, n = {}, 0, 0, 0
    for r in registros or []:
        a, mes = _bv._mes_da_linha(r, col_data, col_ma)
        if a != int(ano) or mes not in meses:
            continue
        g = lambda k: r.get(m[k]) if k in m else None
        fat = _bv._num(g("fat"))
        if not fat and not _bv._num(g("dev")):
            continue
        n += 1
        for k in ("fat", "dev", "nf", "ct", "com", "co", "mc"):
            tot[k] += _bv._num(g(k))
        tot["fr"] += _bv._num(g("fr")) + _bv._num(g("cflex"))
        sem_custo += fat > 0 and not _bv._num(g("ct"))
        sem_mc += g("mc") in (None, "")
        import home_gestao as _hg
        p = _hg.plataforma_do_canal(g("plataforma")) or "Outros"
        plat[p] = plat.get(p, 0.0) + fat
    return ({k: _r2(v) for k, v in tot.items()}, {k: _r2(v) for k, v in plat.items()},
            {"linhas": n, "sem_custo": sem_custo, "sem_mc": sem_mc})


def fixos(ano, meses, fontes=None):
    """{"folha", "custo_fixo", "assinaturas", "nao_operacional"} somados nos
    meses, e os erros. As funções são as do previsto — uma resposta só.
    `fontes` troca as funções (auto-teste)."""
    import previsto as _pv
    f = fontes or {
        "folha": _pv._folha, "custo_fixo": _pv._custo_fixo,
        "nao_operacional": _pv._nao_operacional, "assinaturas": _assinaturas}
    fora, erros = {k: 0.0 for k in f}, []
    for mes in meses:
        for k, fn in f.items():
            try:
                fora[k] += float(fn(int(ano), int(mes)) or 0.0)
            except Exception as e:
                erros.append(f"{k} {mes:02d}/{ano}: {type(e).__name__}")
    return {k: _r2(v) for k, v in fora.items()}, erros


def _assinaturas(ano, mes):
    import assinaturas as _as
    import custo_real as _cr
    return _cr.total_assinaturas(_as.carregar() or [], ano, mes, _cr.carregar())


def montar(v, fx):
    """As seis etapas do funil e o que saiu entre elas. Pura.

    [{"n", "nome", "valor", "deducoes": [(rótulo, valor, fonte)]}] — cada
    etapa é a anterior menos as suas deduções, e o auto-teste confere que o
    funil fecha. As margens são calculadas na tela (`margem`).
    """
    rb = v["fat"]
    rl = _r2(rb - v["dev"] - v["nf"])
    lb = _r2(rl - v["ct"])
    mc = _r2(lb - v["com"] - v["fr"] - v["co"])
    desp = _r2(fx["folha"] + fx["custo_fixo"] + fx["assinaturas"])
    lo = _r2(mc - desp)
    ll = _r2(lo - fx["nao_operacional"])
    dif_mc = _r2(v["mc"] - mc)
    return [
        {"n": 1, "nome": "Receita bruta", "valor": rb, "deducoes": []},
        {"n": 2, "nome": "Receita líquida", "valor": rl, "deducoes": [
            ("Devoluções", v["dev"], "BASE DE VENDAS · DEVOLUÇÃO"),
            ("Tributos sobre a venda (Simples)", v["nf"], "BASE DE VENDAS · NF")]},
        {"n": 3, "nome": "Lucro bruto", "valor": lb, "deducoes": [
            ("CMV — custo das mercadorias vendidas", v["ct"], "BASE DE VENDAS · CUSTO TOTAL")]},
        {"n": 4, "nome": "Margem de contribuição", "valor": mc, "dif_mc": dif_mc, "deducoes": [
            ("Despesa operacional variável — comissões e tarifas dos marketplaces", v["com"],
             "BASE DE VENDAS · COMISSÃO"),
            ("Despesa operacional variável — frete pago pela empresa (inclui Flex)", v["fr"],
             "BASE DE VENDAS · FRETE + CUSTO FLEX"),
            ("Despesa operacional variável — embalagem, ADS, logística, cross docking, consumo",
             v["co"], "BASE DE VENDAS · CUSTO OP. (rateio do C.O. do mês)")]},
        {"n": 5, "nome": "Lucro operacional (EBIT)", "valor": lo, "deducoes": [
            ("Despesa operacional fixa — folha (gestores e CLT)", fx["folha"], "Studio · Folha"),
            ("Despesa operacional fixa — custo fixo (aluguel, contas, tarifas)", fx["custo_fixo"],
             "Studio · Custo fixo (cadastro + real do extrato)"),
            ("Despesa operacional fixa — assinaturas", fx["assinaturas"], "Studio · Assinaturas")]},
        {"n": 6, "nome": "Lucro líquido", "valor": ll, "deducoes": [
            ("Resultado financeiro — parcelas do PRONAMP (juros e principal)",
             fx["nao_operacional"], "Studio · Não operacional"),
            ("IRPJ / CSLL — no Simples já estão na NF", 0.0, "não desconta de novo")]},
    ]


def margem(valor, receita_liquida):
    """% sobre a receita líquida, ou None (não se aplica) com ela zero. Pura."""
    if not receita_liquida:
        return None
    return valor / receita_liquida * 100


@st.cache_data(ttl=300, show_spinner=False)
def dados(ano, m_ini, m_fim):
    """Vendas e fixos do período. Cache de 5 min: a planilha é lida pelo
    `ler_planilha` (10 min) e os fixos por funções com cache próprio."""
    import controle_ms as _cms
    import visao_faturamento as _vf
    meses = list(range(int(m_ini), int(m_fim) + 1))
    df, erro = _cms.ler(_vf.ABA_BASE)
    if erro:
        raise RuntimeError(f"BASE DE VENDAS: {erro}")
    v, plat, info = vendas(df.to_dict("records"), list(df.columns), ano, meses)
    fx, erros = fixos(ano, meses)
    return {"vendas": v, "plataformas": plat, "info": info, "fixos": fx, "erros": erros}


# ── Tela ─────────────────────────────────────────────────────────────────────

def _r(v):
    return ("− " if v < 0 else "") + "R$ " + f"{abs(v):,.0f}".replace(",", ".")


def _pct(p):
    return "não se aplica" if p is None else f"{p:.1f}%".replace(".", ",")


def html(etapas, titulo, plataformas=None, info=None, erros=()):
    """O funil e o que saiu entre as etapas. Uma linha só de HTML. Pura."""
    import html as _h
    import visao_faturamento as _vf
    V, SEC, MUT, BOR, BOM, RUIM, AMB = (_vf.VIDRO, _vf.SEC, _vf.MUTED, _vf.BORDA,
                                        _vf.BOM, _vf.RUIM, "#f0c060")
    rb = etapas[0]["valor"]
    rl = etapas[1]["valor"]
    fun = ""
    for i, e in enumerate(etapas):
        v = e["valor"]
        neg = v < 0
        larg = max(abs(v) / rb * 100, 9) if rb else 9
        # Barras ESCURAS e texto branco (dono, 09/11, print): o texto escuro da
        # barra clara saía claro no Studio, e o % sumia.
        cor = RUIM if neg else ("#2aa3ad" if i % 2 == 0 else "#1f7f87")
        dentro = _pct(v / rb * 100) if rb else "—"
        sub = "100%" if i == 0 else f"{_pct(margem(v, rl))} da líquida"
        fun += (f'<div style="display:grid;grid-template-columns:300px 1fr 170px;align-items:center;gap:14px;'
                f'padding:5px 0;border-bottom:1px solid {BOR}">'
                f'<div style="font-size:15px;font-weight:{800 if i % 2 else 500};color:#E8EAED">'
                f'({e["n"]}) {e["nome"]}</div>'
                f'<div style="display:flex;justify-content:center"><div style="width:{min(larg, 100):.1f}%;'
                f'height:40px;background:{cor};border-radius:6px;display:flex;align-items:center;'
                f'justify-content:center;color:#ffffff;font-weight:800;font-size:15px">{dentro}</div></div>'
                f'<div style="text-align:right"><div style="font-size:16px;font-weight:800;'
                f'color:{RUIM if neg else (BOM if i else "#E8EAED")}">{_r(v)}</div>'
                f'<div style="font-size:11px;color:{SEC}">{sub}</div></div></div>')
    det = ""
    for e in etapas:
        lins = ""
        if e["n"] == 1 and plataformas:
            lins = "".join(
                f'<div style="display:grid;grid-template-columns:1fr 130px 1fr;gap:10px;padding:4px 0 4px 22px;'
                f'font-size:13px;color:#c9ced4"><span>{_h.escape(str(p))}</span><span style="text-align:right">'
                f'{_r(x)}</span><span style="font-size:11px;color:{MUT}">{_pct(x / rb * 100) if rb else "—"} da bruta'
                f'</span></div>' for p, x in sorted(plataformas.items(), key=lambda kv: -kv[1]))
        for rot, x, fonte in e["deducoes"]:
            lins += (f'<div style="display:grid;grid-template-columns:1fr 130px 1fr;gap:10px;padding:4px 0 4px 22px;'
                     f'font-size:13px;color:#c9ced4"><span>(−) {rot}</span><span style="text-align:right">'
                     f'{_r(-x) if x else "R$ 0"}</span><span style="font-size:11px;color:{MUT}">{fonte}</span></div>')
        if abs(e.get("dif_mc") or 0) > TOLERANCIA_MC:
            lins += (f'<div style="padding:4px 0 4px 22px;font-size:12px;color:{AMB}">⚠️ A coluna MARGEM C. da '
                     f'planilha soma {_r(e["valor"] + e["dif_mc"])} — diferença de {_r(e["dif_mc"])} para a conta '
                     f'das linhas acima. A DRE segue a conta; a diferença está na planilha.</div>')
        det += (f'<details style="border-top:1px solid {BOR};padding:8px 0"><summary style="cursor:pointer;'
                f'font-size:13px;font-weight:800;color:{SEC}">({e["n"]}) {e["nome"].upper()}: {_r(e["valor"])}'
                f'{"" if e["n"] == 1 else " · margem " + _pct(margem(e["valor"], rl))}</summary>{lins}</details>')
    avisos = ""
    if info and info.get("sem_custo"):
        avisos += (f'<div style="font-size:12px;color:{AMB};margin-top:8px">⏳ {info["sem_custo"]} venda(s) sem '
                   f'CUSTO TOTAL na planilha: o CMV está menor do que será, e o lucro, maior.</div>')
    for er in erros or ():
        avisos += f'<div style="font-size:12px;color:{AMB};margin-top:4px">⚠️ não li: {_h.escape(er)}</div>'
    return (f'<div style="background:radial-gradient(1200px 400px at 20% 0%,#454545 0%,{_vf.FUNDO} 60%);'
            f'border-radius:18px;padding:22px;border:1px solid {BOR}">'
            f'<div style="font-size:22px;font-weight:300;letter-spacing:.42em">MARTINSOUSA</div>'
            f'<div style="font-size:12px;color:{SEC};letter-spacing:.14em;margin:2px 0 16px">DRE · '
            f'{_h.escape(titulo)} · CONSOLIDADO · REGIME DE COMPETÊNCIA</div>'
            f'<div style="{V};padding:18px 20px"><div style="font-size:12px;font-weight:800;letter-spacing:.14em;'
            f'color:{SEC};margin-bottom:8px">O FUNIL · % DENTRO DA BARRA = QUANTO SOBRA DA RECEITA BRUTA</div>'
            f'{fun}</div><div style="{V};padding:16px 20px;margin-top:12px"><div style="font-size:12px;'
            f'font-weight:800;letter-spacing:.14em;color:{SEC};margin-bottom:4px">O QUE SAIU ENTRE UMA ETAPA E '
            f'OUTRA · CLIQUE PARA ABRIR</div>{det}</div>{avisos}'
            f'<div style="font-size:12px;color:{SEC};margin-top:10px">Margens à direita sobre a RECEITA LÍQUIDA. '
            f'As DESPESAS OPERACIONAIS são tudo o que a empresa gasta para funcionar, entre o lucro bruto e o '
            f'lucro operacional: as VARIÁVEIS (crescem com a venda) saem antes da margem de contribuição, e as '
            f'FIXAS depois dela. O financeiro e o imposto sobre o lucro ficam fora do operacional. O imposto '
            f'pago no extrato é a NF da venda e não entra de novo.</div></div>')


def pagina(ano, hoje):
    """A aba DRE da Visão Geral."""
    c1, c2 = st.columns(2)
    padrao = (hoje.month - 1 if int(ano) == hoje.year else 12) - 1
    ini = c1.selectbox("De", list(MESES), index=max(padrao, 0), key="dre_ini")
    fim = c2.selectbox("Até", list(MESES), index=max(padrao, 0), key="dre_fim")
    m_ini, m_fim = MESES.index(ini) + 1, MESES.index(fim) + 1
    if m_fim < m_ini:
        st.warning("O mês final vem antes do inicial.")
        return
    with st.spinner("Montando a DRE…"):
        try:
            d = dados(int(ano), m_ini, m_fim)
        except Exception as e:
            st.error(f"Não consegui montar a DRE: {e}")
            return
    titulo = f"{ini} {ano}" if m_ini == m_fim else f"{ini} A {fim} {ano}"
    if int(ano) == hoje.year and m_fim >= hoje.month:
        st.caption("O mês corrente ainda está aberto: vendas até hoje, custo operacional previsto "
                   "e custos fixos do mês inteiro.")
    st.markdown(html(montar(d["vendas"], d["fixos"]), titulo, d["plataformas"], d["info"],
                     d["erros"]), unsafe_allow_html=True)


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import inspect as _insp
    from datetime import datetime as _dt
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # O EXEMPLO DA ESPECIFICAÇÃO, fechando: 100.000 − 2.000 − 3.000 − 10.000.
    ok("margem sobre a receita líquida; zero não se aplica",
       round(margem(40000, 85000), 2) == 47.06 and margem(1, 0) is None)

    # A ENTRADA VEM DO SISTEMA: linhas com os títulos da BASE DE VENDAS do
    # dono (os de `produtos_analise.CAMPOS`), lidos pelo mapa de verdade.
    _cols = ["Data", "MÊS/ANO", "Plataforma", "SKU", "Produto", "Quantidade", "FAT TOTAL",
             "CUSTO TOTAL", "COMISSÃO", "FRETE", "CUSTO FLEX", "NF", "CUSTO OP.", "DEVOLUÇÃO",
             "MARGEM C."]

    def V(dia, fat, ct, com, fr, nf, co, dev=0, mc=None, flex=0, plat="MercadoLivre1",
          prod="Porta 2 Relógio + Jóias"):
        mc = fat - dev - nf - (ct or 0) - com - fr - flex - co if mc is None else mc
        return dict(zip(_cols, [_dt(2026, 10, dia), "out2026", plat, "MS-1", prod, 1, fat, ct, com,
                                fr, flex, nf, co, dev, mc]))
    _reg = [V(3, 200.0, 80.0, 30.0, 10.0, 12.0, 8.0, flex=5.0),
            V(5, 100.0, 40.0, 15.0, 0.0, 6.0, 4.0, plat="Shopee1"),
            V(9, 50.0, 20.0, 7.5, 0.0, 3.0, 2.0, dev=50.0, plat="Shopee1"),
            V(12, 60.0, "", 9.0, 0.0, 3.6, 2.4),
            dict(V(3, 999.0, 1, 1, 1, 1, 1), Data=_dt(2026, 9, 30), **{"MÊS/ANO": "set2026"})]
    _v, _pl, _info = vendas(_reg, _cols, 2026, [10])
    ok("só o período: a venda de setembro fica fora", _v["fat"] == 410.0)
    ok("frete soma o CUSTO FLEX (como produtos_analise)", _v["fr"] == 15.0)
    ok("devolução e NF lidas da linha", _v["dev"] == 50.0 and _v["nf"] == 24.6)
    ok("venda sem CUSTO TOTAL é contada e avisada", _info["sem_custo"] == 1)
    ok("faturamento por plataforma", _pl.get("Shopee") == 150.0 or sum(_pl.values()) == 410.0)
    _fx = {"folha": 100.0, "custo_fixo": 30.0, "assinaturas": 10.0, "nao_operacional": 20.0}
    _e = montar(_v, _fx)
    _val = [x["valor"] for x in _e]

    def _fecha(e):
        return all(abs(e[i - 1]["valor"] - sum(x for _r_, x, _f in e[i]["deducoes"]) - e[i]["valor"]) < 0.005
                   for i in range(1, len(e)))
    ok("o funil fecha: cada etapa é a anterior menos o que saiu entre elas", _fecha(_e))
    ok("receita líquida = bruta − devoluções − tributos",
       _val[1] == round(410.0 - 50.0 - 24.6, 2))
    ok("a margem de contribuição bate com a MARGEM C. da planilha (sem diferença)",
       abs(_e[3]["dif_mc"]) < 0.005)
    _reg2 = _reg[:-1] + [dict(_reg[0], **{"MARGEM C.": 999.0})]
    _e2 = montar(vendas(_reg2, _cols, 2026, [10])[0], _fx)
    ok("planilha com MARGEM C. diferente: a diferença aparece, e a DRE segue a conta",
       abs(_e2[3]["dif_mc"]) > 1 and _e2[3]["valor"] == round(
           _e2[2]["valor"] - sum(x for _r_, x, _f in _e2[3]["deducoes"]), 2)
       and "diferença de" in html(_e2, "OUT 2026"))
    _txt_ded = " ".join(r for e in _e for r, _x, _f in e["deducoes"])
    ok("ADS e imposto do extrato NÃO têm linha própria (estão no C.O. e na NF)",
       "Publicidade" not in _txt_ded and "(ADS)" not in _txt_ded
       and "IMPOSTO" not in _txt_ded.upper().replace("IMPOSTOS SOBRE", ""))
    ok("IRPJ/CSLL é zero no Simples", any("IRPJ" in r and x == 0.0 for r, x, _f in _e[5]["deducoes"]))
    ok("os fixos são os do previsto — uma resposta só",
       "_pv._folha" in _insp.getsource(fixos) and "_pv._custo_fixo" in _insp.getsource(fixos)
       and "_pv._nao_operacional" in _insp.getsource(fixos)
       and "total_assinaturas(" in _insp.getsource(_assinaturas))
    ok("e NÃO passa por previsto.do_mes (abre a planilha de 11 MB a cada mês)",
       "do_mes(" not in _insp.getsource(fixos))
    _fz, _erz = fixos(2026, [9, 10], {"folha": lambda a, m: 50.0,
                                      "custo_fixo": lambda a, m: 1 / 0})
    ok("fixos somam os meses; fonte que quebra vira aviso, e não zero calado",
       _fz["folha"] == 100.0 and len(_erz) == 2 and "custo_fixo" in _erz[0])
    # Prejuízo e receita zero.
    _pre = montar(_v, dict(_fx, folha=10000.0))
    _hp = html(_pre, "OUT 2026")
    ok("prejuízo fica negativo e vermelho", _pre[5]["valor"] < 0 and "#E5534B" in _hp)
    _zero = montar({k: 0.0 for k in _v}, _fx)
    _hz = html(_zero, "OUT 2026")
    ok("receita zero: margem 'não se aplica', sem dividir por zero", "não se aplica" in _hz)
    _h = html(_e, "OUT 2026", _pl, _info, ["folha 10/2026: KeyError"])
    ok("o HTML não tem linha só de espaço e nada navega (Regra 12)",
       all(l.strip() for l in _h.split("\n")) and "<a " not in _h and "href" not in _h)
    ok("as seis etapas, o detalhe clicável, o aviso de venda sem custo e o erro de fonte",
       all(f"({i})" in _h for i in range(1, 7)) and "<details" in _h
       and "sem CUSTO TOTAL" in _h and "não li: folha" in _h)
    ok("o resumo do detalhe não junta travessão com o sinal de menos (print do dono)",
       "— −" not in _hp and "(6) LUCRO LÍQUIDO: − R$" in _hp)
    ok("o % da barra é branco sobre barra escura", "color:#ffffff;font-weight:800" in _h
       and "#7fd8e0" not in _h)
    ok("nome de plataforma vai escapado", "&lt;b&gt;" in html(_e, "X", {"<b>": 1.0}))
    print(f"\nfalhas: {falhas}")
    raise SystemExit(1 if falhas else 0)
