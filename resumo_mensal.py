"""resumo_mensal.py — o mês em quadros: pago e provisionado, e item a item.

Pedido do dono, 07/10: uma aba "Resumo Mensal" no Financeiro, antes de Custos
fixos, com um quadro para Custo fixo, Assinaturas, Folha, Cartões, Cheques,
Não operacionais e Outros. Cada quadro mostra o PAGO e o PROVISIONADO; mês
fechado mostra só o pago. Embaixo, o detalhe item a item pela data do débito,
atualizado pelos extratos.

AS CONTAS NÃO SÃO NOVAS
-----------------------
O pago de cada lançamento é o que `lancamentos.resumo_por_finalidade` conta
dele — reembolso negativo, transferência fora, e o pagamento da fatura só
pelo que as compras anexadas não explicam. O provisionado é o de
`previsto.do_mes` e, para as assinaturas, `custo_real.total_assinaturas`. A
assinatura é reconhecida por `custo_real.nomes_do_item`, a mesma regra da
fila de finalidades e do valor real do mês. Nada aqui é uma segunda resposta.

COMPRA NO CARTÃO CONTA NO LUGAR DELA
------------------------------------
Compra de fatura classificada como custo fixo, assinatura ou ADS conta no
quadro dela, e não em Cartões — senão o mesmo aluguel apareceria em dois
quadros. Cartões é o resto: as compras de fatura das outras finalidades e o
pagamento de fatura ainda não anexada.
"""
import streamlit as st

QUADROS = ("Custo fixo", "Assinaturas", "Folha", "Cartões", "Cheques",
           "Não operacionais", "Outros")

# Finalidade → quadro. O que não está aqui (e não é compra de cartão) vai
# para Outros.
_POR_FINALIDADE = {
    "CUSTO FIXO": "Custo fixo",
    "FOLHA": "Folha",
    "NÃO OPERACIONAL": "Não operacionais",
    "NAO OPERACIONAL": "Não operacionais",
    "CHEQUES": "Cheques",
}

# Compra de fatura com estas finalidades NÃO vai para Cartões (dono, 07/10).
# ADS não tem quadro próprio: cai em Outros, com o nome no detalhe.
_CARTAO_FICA_NO_LUGAR = {"CUSTO FIXO", "ADS", "FOLHA", "NÃO OPERACIONAL",
                         "NAO OPERACIONAL", "CHEQUES"}


def nomes_das_assinaturas(assinaturas):
    """[(item, [nomes no extrato])] do cadastro de assinaturas."""
    import custo_real as _cr
    fora = []
    for a in (assinaturas or []):
        item = str(a.get("item") or "").strip()
        nomes = _cr.nomes_do_item(a)
        if item and nomes:
            fora.append((item, nomes))
    return fora


def _assinatura_de(lanc, nomes_assin):
    import assinaturas as _as
    for item, nomes in nomes_assin:
        if any(_as._casa(lanc, {"favorecido": n}) for n in nomes):
            return item
    return ""


def quadro_de(lanc, finalidade, nomes_assin):
    """Em que quadro este lançamento conta."""
    import lancamentos as _lan
    if _assinatura_de(lanc, nomes_assin):
        return "Assinaturas"
    fin = str(finalidade or "").strip().upper()
    if _lan.eh_do_cartao(lanc) and fin not in _CARTAO_FICA_NO_LUGAR:
        return "Cartões"
    return _POR_FINALIDADE.get(fin, "Outros")


def itens_pagos(lancs, nomes_assin):
    """Os lançamentos do mês que consomem a meta, um por linha, com o quadro.

    Soma o mesmo que `lancamentos.resumo_por_finalidade(lancs)`: cada
    lançamento entra com o que o resumo conta dele, e o pagamento da fatura
    entra numa linha só, pelo resto que as compras anexadas não explicam.
    """
    import lancamentos as _lan
    fora = []
    pagamentos = []
    for l in (lancs or []):
        if _lan.cartao_pago([l]):
            pagamentos.append(l)
            continue
        r = _lan.resumo_por_finalidade([l])
        v = round(sum(r.values()), 2)
        if not v:
            continue
        fin = next(iter(r))
        fora.append({"data": str(l.get("data") or "")[:10],
                     "quadro": quadro_de(l, fin, nomes_assin),
                     "favorecido": str(l.get("favorecido")
                                       or l.get("descricao") or "")[:60],
                     "finalidade": fin, "valor": v,
                     "conta": str(l.get("conta") or "")})
    resto = round(_lan.cartao_pago(lancs) - _lan.cartao_detalhado(lancs), 2)
    if pagamentos and resto > 0:
        fora.append({"data": max(str(p.get("data") or "")[:10]
                                 for p in pagamentos),
                     "quadro": "Cartões",
                     "favorecido": "Fatura paga, compras não anexadas",
                     "finalidade": _lan.FATURA, "valor": resto,
                     "conta": " e ".join(sorted({str(p.get("conta") or "")
                                                 for p in pagamentos}))})
    return sorted(fora, key=lambda i: (i["data"], -i["valor"]))


def montar(itens, prev, assinaturas_prov, fechado):
    """{quadro: {"pago", "provisionado"}}. Pura.

    `prev` = `previsto.do_mes`; `assinaturas_prov` = o cadastro das
    assinaturas no mês. Cheque soma o que já baixou com o que vence: são
    cheques diferentes (`previsto.PREVISIVEIS_SOMA`). Outros não tem
    provisão — o Studio não sabe quanta mercadoria será comprada. Mês
    fechado: provisionado None, só o pago vale.
    """
    pago = {q: 0.0 for q in QUADROS}
    for i in (itens or []):
        pago[i["quadro"]] = pago.get(i["quadro"], 0.0) + float(i["valor"])
    prev = {str(k).strip().upper(): float(v) for k, v in (prev or {}).items()}
    prov = {
        "Custo fixo": prev.get("CUSTO FIXO", 0.0),
        "Assinaturas": float(assinaturas_prov or 0.0),
        "Folha": prev.get("FOLHA", 0.0),
        "Cartões": prev.get("FATURA DO CARTÃO", 0.0),
        "Cheques": pago["Cheques"] + prev.get("CHEQUES", 0.0),
        "Não operacionais": prev.get("NÃO OPERACIONAL", 0.0),
        "Outros": None,
    }
    return {q: {"pago": round(pago[q], 2),
                "provisionado": (None if fechado or prov[q] is None
                                 else round(prov[q], 2))}
            for q in QUADROS}


def itens_provisionados(grade_cf, ajustes_df, assinaturas, ano, mes, mapa,
                        lancs):
    """Custo fixo e assinaturas item a item: o do mês e se já saiu. Pura.

    O valor do mês é o de `custo_real` (cadastro com ajustes, e o real onde o
    extrato disse); "saiu" é `custo_real.cobrado_no_mes`, a mesma leitura.
    """
    import pandas as pd
    import ajustes as _aj
    import assinaturas as _as
    import custo_real as _cr
    fora = []
    d = pd.DataFrame(grade_cf)
    por_item = _aj.por_item(ajustes_df)
    for _, r in (d.iterrows() if not d.empty else []):
        item = str(r.get("item", "") or "").strip()
        if not item:
            continue
        cad = _aj.valor_no_mes(r.get("valor_mensal"), r.get("vigente_desde"),
                               por_item.get(("custo_fixo", item)), ano, mes)
        fora.append(("Custo fixo", item, r.get("dia_debito"),
                     _cr.valor_do_mes("custo_fixo", item, ano, mes, cad, mapa),
                     _cr.cobrado_no_mes(dict(r), lancs)))
    for a in (assinaturas or []):
        item = str(a.get("item") or "").strip()
        if not item:
            continue
        fora.append(("Assinaturas", item, "",
                     _cr.valor_do_mes("assinaturas", item, ano, mes,
                                      _as.custo_mensal(a), mapa),
                     _cr.cobrado_no_mes(a, lancs)))
    linhas = []
    for quadro, item, dia, valor, saiu in fora:
        try:
            dia = int(float(dia)) if str(dia).strip() else None
        except (TypeError, ValueError):
            dia = None
        linhas.append({"dia do débito": dia, "quadro": quadro, "item": item,
                       "do mês": round(float(valor or 0.0), 2),
                       "saiu no extrato": saiu,
                       "situação": "pago" if saiu is not None else "a pagar"})
    return sorted(linhas, key=lambda x: (x["dia do débito"] is None,
                                         x["dia do débito"] or 0, x["item"]))


def _html_quadros(q):
    """Os sete quadros numa grade. Mês fechado: só o pago."""
    import rotulos as _rot
    cel = []
    for nome in QUADROS:
        v = q[nome]
        prov = v["provisionado"]
        linha_prov = (f'<div style="font-size:12px;opacity:.75;">Provisionado '
                      f'<b>{_rot.brl(prov)}</b></div>' if prov is not None else "")
        cel.append(
            '<div style="border:1px solid rgba(128,128,128,.35);border-radius:12px;'
            'padding:12px 14px;">'
            f'<div style="font-size:12px;font-weight:700;opacity:.8;">{nome}</div>'
            f'<div style="font-size:20px;font-weight:800;">{_rot.brl(v["pago"])}</div>'
            f'<div style="font-size:12px;opacity:.75;">pago</div>{linha_prov}</div>')
    return ('<div style="display:grid;grid-template-columns:repeat(auto-fill,'
            'minmax(170px,1fr));gap:10px;margin:6px 0 14px;">'
            + "".join(cel) + "</div>")


def pagina(usuario_logado=None):
    from datetime import datetime
    import pandas as pd
    import placar_core as _pc
    import lancamentos as _lan
    import assinaturas as _as
    import custo_real as _cr
    import rotulos as _rot

    st.markdown("#### 📊 Resumo Mensal")
    hoje = datetime.now(_pc.FUSO).date()
    c1, c2, _ = st.columns([1, 1, 3])
    mes = c1.selectbox(
        "Mês", list(range(1, 13)), index=hoje.month - 1, key="rm_mes",
        format_func=lambda m: ["janeiro", "fevereiro", "março", "abril",
                               "maio", "junho", "julho", "agosto", "setembro",
                               "outubro", "novembro", "dezembro"][m - 1])
    ano = int(c2.number_input("Ano", 2020, 2100, hoje.year, 1, key="rm_ano"))
    fechado = (ano, mes) < (hoje.year, hoje.month)

    try:
        lancs = _lan.do_mes(ano, mes)
        assin = _as.carregar()
    except Exception as e:
        st.error(f"Não consegui ler os lançamentos: {str(e)[:140]}")
        return
    prev, erros = {}, []
    assin_prov = 0.0
    if not fechado:
        # O previsto só para mês aberto: uma das fontes abre o Controle MS
        # inteiro, e para mês fechado ele não aparece na tela.
        import previsto as _pv
        prev, erros = _pv.do_mes(ano, mes)
        try:
            assin_prov = _cr.total_assinaturas(assin, ano, mes, _cr.carregar())
        except Exception as e:
            erros = list(erros) + [f"ASSINATURAS: {str(e)[:80]}"]

    itens = itens_pagos(lancs, nomes_das_assinaturas(assin))
    q = montar(itens, prev, assin_prov, fechado)
    st.markdown(_html_quadros(q), unsafe_allow_html=True)
    total = round(sum(v["pago"] for v in q.values()), 2)
    st.caption(_rot.tela(
        f"Pago no mês: {_rot.brl(total)}"
        + (" · mês fechado: só o pago." if fechado else
           " · provisionado = o que o mês deve pelas grades do Studio, pela "
           "aba CARTÕES e pelos cheques a vencer.")))
    if erros:
        st.caption("⚠️ Não consegui ler: " + " · ".join(erros))

    st.markdown("##### Pago, item a item")
    if itens:
        st.dataframe(
            pd.DataFrame(itens), use_container_width=True, hide_index=True,
            column_config=_rot.config(
                ["data", "quadro", "favorecido", "finalidade", "valor", "conta"],
                st, tipos={"valor": "brl"}))
    else:
        st.info("Nenhum lançamento neste mês. Os pagos entram quando o "
                "extrato ou a fatura é anexado em Financeiro › 💳 Extratos.")

    st.markdown("##### Custo fixo e assinaturas, pela data do débito")
    try:
        import ajustes as _aj
        import custo_fixo as _cf
        prov_itens = itens_provisionados(_cf.carregar("custo_fixo"),
                                         _aj.carregar(), assin, ano, mes,
                                         _cr.carregar(), lancs)
    except Exception as e:
        st.caption(f"Não consegui ler as grades: {str(e)[:140]}")
        return
    if prov_itens:
        st.dataframe(
            pd.DataFrame(prov_itens), use_container_width=True,
            hide_index=True,
            column_config=_rot.config(
                ["dia do débito", "quadro", "item", "do mês",
                 "saiu no extrato", "situação"], st,
                tipos={"do mês": "brl", "saiu no extrato": "brl"}))
        st.caption("«Saiu no extrato» vem dos extratos e faturas anexados, "
                   "pelo nome do item ou por «Como aparece no extrato». Em "
                   "branco: ainda não apareceu.")


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    import lancamentos as _lan_t
    # Lançamentos na forma que `lancamentos.do_mes` devolve (COLUNAS de
    # lancamentos.py: conta, data, descricao, favorecido, valor, finalidade).
    _CART = _lan_t.CONTA_CARTAO + "Inter"
    _l = [
        {"data": "2026-10-05", "descricao": "PIX ALUGUEL", "favorecido": "IMOB",
         "valor": -3000.0, "finalidade": "CUSTO FIXO", "conta": "Itaú"},
        {"data": "2026-10-06", "descricao": "CLAUDE.AI SUBSCRIPTION",
         "favorecido": "", "valor": -550.0, "finalidade": "CUSTO FIXO",
         "conta": _CART},
        {"data": "2026-10-06", "descricao": "MERCADO LIVRE ADS",
         "favorecido": "", "valor": -800.0, "finalidade": "ADS", "conta": _CART},
        {"data": "2026-10-07", "descricao": "LOJA X", "favorecido": "",
         "valor": -200.0, "finalidade": "MERCADORIA", "conta": _CART},
        {"data": "2026-10-08", "descricao": "SALARIOS", "favorecido": "",
         "valor": -9000.0, "finalidade": "FOLHA", "conta": "Itaú"},
        {"data": "2026-10-09", "descricao": "CHEQUE 12", "favorecido": "",
         "valor": -1500.0, "finalidade": "CHEQUES", "conta": "Itaú"},
        {"data": "2026-10-09", "descricao": "PRONAMP", "favorecido": "",
         "valor": -700.0, "finalidade": "NÃO OPERACIONAL", "conta": "Itaú"},
        {"data": "2026-10-10", "descricao": "FORNECEDOR", "favorecido": "",
         "valor": -4000.0, "finalidade": "MERCADORIA", "conta": "Itaú"},
        {"data": "2026-10-11", "descricao": "PAG FATURA", "favorecido": "",
         "valor": -2000.0, "finalidade": "FATURA DO CARTÃO", "conta": "Itaú"},
        {"data": "2026-10-12", "descricao": "ENTRE CONTAS", "favorecido": "",
         "valor": -5000.0, "finalidade": "TRANSFERENCIA ENTRE CONTAS",
         "conta": "Itaú"},
    ]
    _assin = [{"item": "Claude", "valor_mensal": 550.0, "periodicidade": "Mensal",
               "favorecido": ""}]
    _nomes = nomes_das_assinaturas(_assin)
    _it = itens_pagos(_l, _nomes)
    _por = {}
    for _i in _it:
        _por[_i["quadro"]] = _por.get(_i["quadro"], 0.0) + _i["valor"]
    ok("o pago do resumo soma o mesmo que o resumo por finalidade",
       round(sum(i["valor"] for i in _it), 2)
       == round(sum(_lan_t.resumo_por_finalidade(_l).values()), 2))
    ok("a assinatura no cartão conta em Assinaturas, não em Cartões nem em "
       "Custo fixo", _por.get("Assinaturas") == 550.0
       and _por.get("Custo fixo") == 3000.0)
    ok("ADS no cartão fica fora de Cartões",
       not any(i["quadro"] == "Cartões" and i["finalidade"] == "ADS" for i in _it)
       and any(i["quadro"] == "Outros" and i["finalidade"] == "ADS" for i in _it))
    # Fatura de 2.000 paga; compras anexadas que consomem a meta: 550 + 800 +
    # 200 = 1.550. O resto, 450, é Cartões — com a compra de 200: 650.
    ok("Cartões = compras das outras finalidades + o resto da fatura",
       _por.get("Cartões") == 650.0)
    ok("transferência entre contas não entra",
       not any("TRANSF" in i["finalidade"] for i in _it))
    _q = montar(_it, {"CUSTO FIXO": 3500.0, "FOLHA": 12000.0,
                      "NÃO OPERACIONAL": 700.0, "CHEQUES": 2500.0,
                      "FATURA DO CARTÃO": 3000.0}, 550.0, fechado=False)
    ok("cada quadro traz pago e provisionado",
       _q["Custo fixo"] == {"pago": 3000.0, "provisionado": 3500.0}
       and _q["Folha"] == {"pago": 9000.0, "provisionado": 12000.0}
       and _q["Assinaturas"]["provisionado"] == 550.0)
    ok("cheque provisionado = o que já baixou + o que vence",
       _q["Cheques"] == {"pago": 1500.0, "provisionado": 4000.0})
    ok("Outros não tem provisão", _q["Outros"]["provisionado"] is None
       and _q["Outros"]["pago"] == 4800.0)
    _qf = montar(_it, {"CUSTO FIXO": 3500.0}, 550.0, fechado=True)
    ok("mês fechado mostra só o pago",
       all(v["provisionado"] is None for v in _qf.values())
       and _qf["Custo fixo"]["pago"] == 3000.0)
    _h = _html_quadros(_q)
    ok("os sete quadros aparecem, com o dinheiro no formato do dono",
       all(n in _h for n in QUADROS) and "R$ 3.000,00" in _h
       and "Provisionado" in _h)
    ok("mês fechado não desenha a linha do provisionado",
       "Provisionado" not in _html_quadros(_qf))

    # Item a item do provisionado, pela cadeia: a grade na forma que
    # `custo_fixo.carregar` devolve (DataFrame com COLUNAS de custo_fixo.py).
    import pandas as _pd_t
    import custo_fixo as _cf_t
    _grade = _pd_t.DataFrame([
        {"item": "Aluguel", "valor_mensal": 3000.0, "vigente_desde": "2026-01",
         "dia_debito": 5, "forma_pagamento": "PIX", "favorecido": "IMOB"},
        {"item": "Luz", "valor_mensal": 500.0, "vigente_desde": "2026-01",
         "dia_debito": "", "forma_pagamento": "Boleto", "favorecido": ""},
    ], columns=_cf_t.COLUNAS)
    _pi = itens_provisionados(_grade, _pd_t.DataFrame(), _assin, 2026, 10,
                              {}, _l)
    _pi_por = {p["item"]: p for p in _pi}
    ok("o item que saiu no extrato aparece pago, o outro a pagar",
       _pi_por["Aluguel"]["situação"] == "pago"
       and _pi_por["Aluguel"]["saiu no extrato"] == 3000.0
       and _pi_por["Luz"]["situação"] == "a pagar")
    ok("a assinatura casa pelo nome do item, no cartão",
       _pi_por["Claude"]["situação"] == "pago"
       and _pi_por["Claude"]["quadro"] == "Assinaturas")
    ok("ordenado pela data do débito, sem dia por último",
       _pi[0]["item"] == "Aluguel" and _pi[-1]["dia do débito"] is None)

    # A aba está no Financeiro, ANTES de Custos fixos.
    import gestao as _g_t
    _abas = list(_g_t.SUBTELAS)
    ok("Resumo Mensal é a aba antes de Custos fixos",
       "📊 Resumo Mensal" in _abas
       and _abas.index("📊 Resumo Mensal") + 1 == _abas.index("🧱 Custos fixos"))

    print("\nfalhas:", falhas)
    sys.exit(1 if falhas else 0)
