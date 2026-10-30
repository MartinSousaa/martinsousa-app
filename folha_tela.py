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
               + f" · valor-hora = salário ÷ {_fm.DIVISOR_HORAS} (40h semanais)")
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
    _f = _fm_t.apurar(2200, _d - 480, 0, _d, 0, ["2026-10-14"], True)
    _l, _p, _v = _fm_t.metas(2200, {"col": True})
    _por = {"luiz": {"folha": _f, "metas": _l, "pct_metas": _p, "metas_valor": _v,
                     "faltas": ["2026-10-14"], "devidas_min": _d, "total": 0},
            "fulano": None}
    _s, _t = linhas_salario(_por, {"luiz": "Luiz"})
    ok("salário: a falta sem banco desconta as 8h, sem domingo (dono, 30/10), e o total soma",
       _s[0]["Faltas de dia inteiro"] == "1" and _s[0]["Desconto"] == "− R$ 88,00"
       and _t["pagar"] == _f["salario_pagar"] and len(_s) == 1)
    _m, _tm = linhas_metas(_por, {"luiz": "Luiz"})
    ok("metas: coletiva paga R$ 264, as outras marcadas ✗", _tm == 264.0
       and _m[0]["Coletiva 12%"] == "✓ R$ 264,00" and _m[0]["Individual 8%"] == "✗")
    print("\nfalhas:", falhas)
    raise SystemExit(1 if falhas else 0)
