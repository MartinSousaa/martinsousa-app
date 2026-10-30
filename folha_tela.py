"""folha_tela.py — Financeiro › Apuração do mês: quanto o dono paga a cada um.

Dono, 30/10: salário pelo ponto (dia 30) e metas (5º dia útil), pessoa por
pessoa. A conta é `folha_mes`; a apuração é a do `meu_desempenho` — a mesma
que o colaborador vê no painel dele. Duas telas, um número.
"""
import streamlit as st


def _brl(v):
    return "R$ " + f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def linhas_salario(por_pessoa, nomes):
    """As linhas da tabela de salário e o total. Pura."""
    import folha_mes as _fm
    linhas, tot = [], {"base": 0.0, "desc": 0.0, "pagar": 0.0}
    for u, d in sorted(por_pessoa.items(), key=lambda kv: nomes.get(kv[0], kv[0])):
        if not d:
            continue
        f = d["folha"]
        tot["base"] += f["salario"]
        tot["desc"] += f["desconto"]
        tot["pagar"] += f["salario_se_fechasse_hoje"]
        linhas.append({
            "Colaborador": nomes.get(u, u),
            "Salário base": _brl(f["salario"]),
            "Saldo do mês": _fm.h(f["saldo_mes_min"]),
            # Texto, e nao numero: a coluna mistura 2 e "—", e o Streamlit
            # reclama de tipo misturado ao montar a tabela.
            "Faltas de dia inteiro": str(len(d["faltas"])) if d["faltas"] else "—",
            "Coberto pelo banco": _fm.h(f["usado_do_banco_min"]).lstrip("+") if f["usado_do_banco_min"] else "—",
            "Desconto": ("− " + _brl(f["desconto"])
                         + (f" ({f['semanas_falta']} domingo)" if f["semanas_falta"] else ""))
                        if f["desconto"] else "—",
            "Salário a pagar": _brl(f["salario_se_fechasse_hoje"]),
            "Banco de horas": _fm.h(f["banco_final_min"])})
    return linhas, tot


def linhas_metas(por_pessoa, nomes):
    """As linhas da tabela das quatro metas e o total. Pura."""
    linhas, total = [], 0.0
    for u, d in sorted(por_pessoa.items(), key=lambda kv: nomes.get(kv[0], kv[0])):
        if not d:
            continue
        r = {"Colaborador": nomes.get(u, u)}
        for rot, pct, v, bateu, mot, pago in d["metas"]:
            r[f"{rot} {pct:.0f}%"] = (("✓ " + _brl(v)) if pago else "✓ (a MAXX paga)") if bateu \
                else ("✗ " + mot if mot else "✗")
        r["% total"] = f"{d['pct_metas']:.0f}%"
        r["Metas a pagar"] = _brl(d["metas_valor"])
        total += d["metas_valor"]
        linhas.append(r)
    return linhas, total


_DIAS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


def faltas_para_marcar(por_pessoa, nomes):
    """[(username, data ISO, marcada)] de toda falta de dia inteiro do mês. Pura."""
    fora = []
    for u, d in sorted(por_pessoa.items(), key=lambda kv: nomes.get(kv[0], kv[0])):
        if not d:
            continue
        for dt in sorted(d.get("faltas") or []):
            fora.append((u, dt, dt in (d.get("domingo_nas") or [])))
    return fora


def marcas_escolhidas(base, marcadas):
    """{username: [datas]} com as caixas marcadas. `marcadas[i]` é a caixa da
    linha `base[i]`. Quem ficou sem nenhuma marca entra vazio — é assim que a
    desmarcada sai da planilha. Pura."""
    fora = {}
    for (u, dt, _), m in zip(base, marcadas):
        fora.setdefault(u, [])
        if m:
            fora[u].append(dt)
    return fora


def _marcar_domingos(por, nomes, ano, mes, usuario_logado):
    """A caixa do dono em cada falta de dia inteiro: desconta o domingo?"""
    import pandas as pd
    from datetime import date
    import folha_mes as _fm
    import meu_desempenho as _md
    base = faltas_para_marcar(por, nomes)
    with st.container(border=True):
        st.markdown("**FALTAS DE DIA INTEIRO — DESCONTAR O DOMINGO?**")
        if not base:
            st.caption("Nenhuma falta de dia inteiro no mês.")
            return
        st.caption("Sem marca, a falta desconta só as 8h dela. Marcada, desconta também o "
                   "domingo daquela semana (salário ÷ 30) — uma vez por semana. "
                   "O colaborador vê o mesmo no painel dele.")
        df = pd.DataFrame([{"Colaborador": nomes.get(u, u),
                            "Dia": f"{date.fromisoformat(dt):%d/%m} "
                                   f"({_DIAS[date.fromisoformat(dt).weekday()]})",
                            "Descontar domingo": m} for u, dt, m in base])
        ed = st.data_editor(df, hide_index=True, use_container_width=True,
                            disabled=["Colaborador", "Dia"],
                            key=f"folha_dom_{ano}_{mes}")
        novas = [bool(x) for x in ed["Descontar domingo"]]
        if novas == [m for _, _, m in base]:
            return
        if st.button("💾 Salvar marcações do domingo", type="primary",
                     key=f"folha_dom_salvar_{ano}_{mes}"):
            try:
                _fm.gravar_domingos(ano, mes, marcas_escolhidas(base, novas), usuario_logado)
            except Exception as e:
                st.error(f"Não consegui gravar as marcações: {e}")
                return
            # A apuração do mês fica 5 min em cache — a do colaborador também.
            # Sem limpar, a marca nova só apareceria daqui a 5 minutos.
            _md.resumo_do_mes.clear()
            st.rerun()


def pagina(usuario_logado=None):
    import auth
    import pandas as pd
    import placar_core as _pc
    import headcount as _hc
    import meu_desempenho as _md
    import folha_mes as _fm
    if not auth.eh_dono(usuario_logado):
        st.error("Acesso restrito ao dono do Studio.")
        return
    st.markdown("### 🧮 Apuração do mês — Headcount")
    hoje = _pc.agora_br()
    meses = [(hoje.year, hoje.month)]
    for _ in range(3):
        a, m = meses[-1]
        meses.append((a - 1, 12) if m == 1 else (a, m - 1))
    ano, mes = st.selectbox("Mês", meses, format_func=lambda am: f"{am[1]:02d}/{am[0]}",
                            key="folha_mes_sel")
    with st.spinner("Apurando o mês…"):
        res = _md.resumo_do_mes(ano, mes) or {}
    por = {u: r.get("dinheiro") for u, r in res.items()}
    erro = next((r.get("dinheiro_erro") for r in res.values() if r.get("dinheiro_erro")), "")
    if erro:
        st.error(f"Não consegui apurar: {erro}")
    if not any(por.values()):
        st.info("Sem salário cadastrado ou sem dado do mês. O salário vem da folha "
                "(Financeiro › Custos fixos › Colaboradores).")
        return
    fechado = (ano, mes) < (hoje.year, hoje.month)
    q = _hc.quinto_dia_util(ano, mes)
    st.caption(("Mês fechado" if fechado else "Mês aberto: o que seria se fechasse hoje")
               + " · ponto da RHiD até ontem · salário no dia 30 · metas no 5º dia útil"
               + (f" ({q:%d/%m})" if q else "")
               + " · valor da hora = salário ÷ horas do mês"
               + (f" ({next(d for d in por.values() if d)['horas_do_mes_min'] / 60:.0f}h)"
                  if any(por.values()) else ""))
    nomes = {u: str(n).split(" ")[0] for u, n in _pc.MEMBROS_ATIVOS.items()}
    sal, tot = linhas_salario(por, nomes)
    met, tot_m = linhas_metas(por, nomes)
    k = st.columns(4)
    k[0].metric("Salários · dia 30", _brl(tot["pagar"]))
    k[1].metric("Metas · 5º dia útil", _brl(tot_m))
    k[2].metric("Total do mês", _brl(tot["pagar"] + tot_m))
    k[3].metric("Descontos por falta", ("− " + _brl(tot["desc"])) if tot["desc"] else _brl(0))
    with st.container(border=True):
        st.markdown("**SALÁRIO — PELO PONTO**")
        st.dataframe(pd.DataFrame(sal), use_container_width=True, hide_index=True)
    _marcar_domingos(por, nomes, ano, mes, usuario_logado)
    with st.container(border=True):
        st.markdown("**METAS — % DO SALÁRIO BASE**")
        st.dataframe(pd.DataFrame(met), use_container_width=True, hide_index=True)
        st.caption("Cada metade paga o nível mais alto: a MAXX substitui a mensal. "
                   "Os critérios são os mesmos da Análise de Metas.")
    sem = [nomes.get(u, u) for u, d in por.items() if not d]
    if sem:
        st.caption("Sem salário cadastrado na folha: " + ", ".join(sorted(sem)))


if __name__ == "__main__":
    import folha_mes as _fm_t
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # Pela cadeia: a linha de cada pessoa sai de `folha_mes.apurar` e `metas`
    # de verdade, na forma que `do_mes` monta.
    _d = 22 * 480
    _f = _fm_t.apurar(2200, _d - 480, 0, _d, 0, ["2026-10-14"], True, horas_do_mes_min=_d)
    _l, _p, _v = _fm_t.metas(2200, {"col": True})
    _por = {"luiz": {"folha": _f, "metas": _l, "pct_metas": _p, "metas_valor": _v,
                     "faltas": ["2026-10-14"], "domingo_nas": [], "devidas_min": _d,
                     "total": 0},
            "fulano": None}
    _s, _t = linhas_salario(_por, {"luiz": "Luiz"})
    ok("salário: a falta sem banco desconta as 8h, sem domingo (dono, 30/10), e o total soma",
       _s[0]["Faltas de dia inteiro"] == "1" and _s[0]["Desconto"] == "− R$ 100,00"
       and _t["pagar"] == _f["salario_pagar"] and len(_s) == 1)
    _m, _tm = linhas_metas(_por, {"luiz": "Luiz"})
    ok("metas: coletiva paga R$ 264, as outras marcadas ✗", _tm == 264.0
       and _m[0]["Coletiva 12%"] == "✓ R$ 264,00" and _m[0]["Individual 8%"] == "✗")
    # A caixa: as faltas viram linhas, e a escolha volta no formato que
    # `folha_mes.linhas_com_marcas` grava.
    _por["bia"] = dict(_por["luiz"], faltas=["2026-10-07", "2026-10-21"],
                       domingo_nas=["2026-10-21"])
    _b = faltas_para_marcar(_por, {"luiz": "Luiz", "bia": "Beatriz"})
    ok("cada falta vira uma linha, já com a marca que está gravada",
       _b == [("bia", "2026-10-07", False), ("bia", "2026-10-21", True),
              ("luiz", "2026-10-14", False)])
    _e = marcas_escolhidas(_b, [True, False, False])
    ok("a escolha volta por pessoa, e quem desmarcou tudo entra vazio",
       _e == {"bia": ["2026-10-07"], "luiz": []})
    _rows = _fm_t.linhas_com_marcas(
        [{"mes": "2026-10", "username": "bia", "data": "2026-10-21"}], 2026, 10, _e, "dono", "x")
    ok("e gravada, a desmarcada sai e a marcada entra",
       _fm_t.domingos_de(_rows, 2026, 10) == {"bia": ["2026-10-07"]})
    print("\nfalhas:", falhas)
    raise SystemExit(1 if falhas else 0)
