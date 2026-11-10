"""folha_tela.py — Financeiro › Apuração do mês: quanto o dono paga a cada um.

Dono, 30/10: salário pelo ponto (dia 30) e metas (5º dia útil), pessoa por
pessoa. A conta é `folha_mes`; a apuração é a do `meu_desempenho` — a mesma
que o colaborador vê no painel dele. Duas telas, um número.
"""
import streamlit as st


def _brl(v):
    return "R$ " + f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def linhas_salario(por_pessoa, nomes, assinadas=None):
    """As linhas da tabela de salário e o total. Pura.

    `assinadas`: {username: linha da aba de assinaturas}; None quando o
    período ainda não pode ser assinado (a coluna não aparece)."""
    import folha_mes as _fm
    linhas, tot = [], {"base": 0.0, "desc": 0.0, "pagar": 0.0}
    for u, d in sorted(por_pessoa.items(), key=lambda kv: nomes.get(kv[0], kv[0])):
        if not d:
            continue
        f = d["folha"]
        tot["base"] += f["salario"]
        tot["desc"] += f["desconto_no_salario"]
        tot["pagar"] += f["salario_se_fechasse_hoje"]
        linhas.append({
            "Colaborador": nomes.get(u, u),
            "Salário base": _brl(f["salario"]),
            "Saldo do mês": _fm.h(f["saldo_mes_min"]),
            # Texto, e nao numero: a coluna mistura 2 e "—", e o Streamlit
            # reclama de tipo misturado ao montar a tabela.
            "Faltas de dia inteiro": str(len(d["faltas"])) if d["faltas"] else "—",
            "Coberto pelo banco": _fm.h(f["usado_do_banco_min"]).lstrip("+") if f["usado_do_banco_min"] else "—",
            "Desconto": ("nas metas" if f.get("desconto_no_bonus") and f.get("desconto_total")
                         else ("− " + _brl(f["desconto_no_salario"])
                               + (f" ({f['semanas_falta']} domingo)" if f["semanas_falta"] else "")
                               + (" (manual)" if f.get("desconto_manual") else ""))
                         if f["desconto_no_salario"] else "—"),
            "Salário a pagar": _brl(f["salario_se_fechasse_hoje"]),
            "Banco de horas": _fm.h(f["banco_final_min"])})
        if assinadas is not None:
            _a = assinadas.get(u)
            linhas[-1]["Folha de ponto"] = (f"✓ {str(_a.get('assinado_em', ''))[:5]}"
                                            if _a else "pendente")
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
        # OS DESCONTOS QUE O DONO MANDOU PARA AS METAS (09/11).
        r["Descontos"] = (("− " + _brl(d["desconto_das_metas"]) if d.get("desconto_das_metas") else "—")
                          + (f" · {_brl(d['nao_coberto'])} sem metas para cobrir"
                             if d.get("nao_coberto") else ""))
        r["Metas a pagar"] = _brl(d.get("metas_pagar", d["metas_valor"]))
        total += d.get("metas_pagar", d["metas_valor"])
        linhas.append(r)
    return linhas, total


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
    import holerite as _hl
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
                                   f"({_hl._DIAS[date.fromisoformat(dt).weekday()]})",
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


def ajuste_da_pessoa(d):
    """O ajuste gravado de uma pessoa, na forma que `folha_mes.gravar_ajuste`
    recebe. Pura."""
    f = d["folha"]
    saldos = {x for x in (d.get("saldos_recebidos") or [])}
    return {"descontos": [x for x in (f.get("descontos_manuais") or []) if x not in saldos],
            "no_bonus": bool(f.get("desconto_no_bonus")), "obs": d.get("observacao", ""),
            "ponto": f.get("desconto_ponto_gestor")}


def ajuste_do_formulario(linhas, no_bonus, obs, ponto=None):
    """O que a tela devolve vira o ajuste. Linha sem valor fica de fora;
    célula vazia do editor vem NaN (str(NaN) seria "nan"). Pura."""
    desc = []
    for l in linhas or []:
        d, v = l.get("Descrição"), l.get("Valor (R$)")
        d = d.strip() if isinstance(d, str) else ""
        try:
            v = float(str(v).replace(",", ".")) if v is not None and v == v else 0.0
        except ValueError:
            v = 0.0
        if v:
            desc.append((d or "Desconto", round(abs(v), 2)))
    return {"descontos": desc, "no_bonus": bool(no_bonus), "obs": str(obs or "").strip(),
            "ponto": (round(abs(float(ponto)), 2) if ponto is not None else None)}


def _ajustes_manuais(por, nomes, ano, mes, usuario_logado):
    """Desconto manual, a marca "descontar nas metas" e a observação (dono, 09/11)."""
    import pandas as pd
    import folha_mes as _fm
    import meu_desempenho as _md
    quem = [u for u, d in sorted(por.items(), key=lambda kv: nomes.get(kv[0], kv[0])) if d]
    with st.container(border=True):
        st.markdown("**DESCONTOS MANUAIS E OBSERVAÇÕES**")
        st.caption("Sem a marca, todo desconto (o do ponto e o manual) sai do salário. Marcada, "
                   "o salário fica integral e o desconto sai das metas do 5º dia útil. A "
                   "observação aparece no holerite, para o colaborador.")
        u = st.selectbox("Colaborador", quem, format_func=lambda x: nomes.get(x, x),
                         key=f"folha_aj_quem_{ano}_{mes}")
        if not u:
            return
        # O SALVAR DIZ QUE SALVOU (dono, 09/11: "clico em salvar e parece que
        # não está salvando"). O redesenho apagava qualquer aviso; ele
        # atravessa o rerun pela sessão, como os avisos da fila do Extratos.
        _ok = st.session_state.pop(AVISO_AJUSTE, None)
        if _ok:
            st.success(_ok)
        d = por[u]
        f, aj = d["folha"], ajuste_da_pessoa(d)
        if d.get("saldos_recebidos"):
            st.caption(("Vindo do mês anterior: " + " · ".join(
                f"{x} ({_brl(v)})" for x, v in d["saldos_recebidos"])).replace("$", "\\$"))
        st.caption("Gravado agora para " + nomes.get(u, u) + ": "
                   + (f"{len(aj['descontos'])} desconto(s) manual(is)" if aj["descontos"]
                      else "nenhum desconto manual")
                   + (" · descontar nas metas" if aj["no_bonus"] else "")
                   + (" · observação ✓" if aj["obs"] else " · sem observação"))
        # O $ escapado: dois "R$" na mesma linha viram fórmula no markdown.
        st.caption((f"Desconto do ponto neste mês: {_brl(f['desconto'])} · "
                    f"metas do mês: {_brl(d['metas_valor'])}").replace("$", "\\$"))
        with st.form(f"folha_aj_form_{ano}_{mes}_{u}"):
            df = pd.DataFrame([{"Descrição": x, "Valor (R$)": v} for x, v in aj["descontos"]]
                              or [{"Descrição": "", "Valor (R$)": None}])
            ed = st.data_editor(df, num_rows="dynamic", hide_index=True, use_container_width=True,
                                key=f"folha_aj_ed_{ano}_{mes}_{u}",
                                column_config={"Valor (R$)": st.column_config.NumberColumn(
                                    "Valor (R$)", min_value=0.0, format="R$ %.2f")})
            # O DESCONTO DO PONTO QUE O DONO CALCULOU (10/11): marcado, o valor
            # dele substitui o do sistema; o do sistema continua na legenda.
            usa_p = st.checkbox("Usar o desconto do ponto que eu calculei",
                                value=aj["ponto"] is not None, key=f"folha_aj_up_{ano}_{mes}_{u}")
            val_p = st.number_input("Desconto do ponto (R$)", min_value=0.0, step=1.0, format="%.2f",
                                    value=float(aj["ponto"] if aj["ponto"] is not None else f["desconto"]),
                                    key=f"folha_aj_vp_{ano}_{mes}_{u}")
            nb = st.checkbox("Descontar nas metas (5º dia útil) — o salário fica integral",
                             value=aj["no_bonus"], key=f"folha_aj_nb_{ano}_{mes}_{u}")
            obs = st.text_area("Observações (aparecem no holerite)", value=aj["obs"],
                               key=f"folha_aj_obs_{ano}_{mes}_{u}")
            enviou = st.form_submit_button("💾 Salvar ajustes", type="primary")
        if not enviou:
            return
        novo = ajuste_do_formulario(ed.to_dict("records"), nb, obs, val_p if usa_p else None)
        # O QUE NÃO COUBE NAS METAS VAI PARA O MÊS SEGUINTE (dono, 10/11) —
        # com os saldos que já vieram de antes, que também podem não caber.
        saldo = _fm.saldo_a_levar(f["desconto"], dict(novo, saldos=d.get("saldos_recebidos") or []),
                                  d["metas_valor"])
        try:
            _fm.gravar_ajuste(ano, mes, u, novo, usuario_logado)
            _fm.gravar_saldo(ano, mes, u, saldo, usuario_logado)
        except Exception as e:
            st.error(f"Não consegui gravar os ajustes: {e}")
            return
        # A apuração fica 5 min em cache — a do colaborador também.
        _md.resumo_do_mes.clear()
        _prox = f"{(mes % 12) + 1:02d}/{ano + (mes == 12)}"
        st.session_state[AVISO_AJUSTE] = (f"✅ Ajustes de {nomes.get(u, u)} gravados — o holerite "
                                          "abaixo já mostra."
                                          + (f" R$ {saldo:,.2f}".replace(",", "X").replace(".", ",")
                                             .replace("X", ".") + f" não couberam nas metas e foram "
                                             f"levados para {_prox}." if saldo else ""))
        # O HOLERITE DE BAIXO ABRE NA PESSOA QUE ACABOU DE SER AJUSTADA: ele
        # abria na primeira da lista, e o ajuste "não aparecia".
        st.session_state[f"folha_holerite_{ano}_{mes}"] = u
        st.rerun()


AVISO_AJUSTE = "folha_aj_aviso"


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
    import holerite as _hl
    _d0 = next(d for d in por.values() if d)
    fechado = _d0["folha"]["fechado"]
    q = _hc.quinto_dia_util(ano, mes)
    _ini, _fim = _d0["periodo"]
    st.caption(("Período fechado" if fechado else "Período aberto: o que seria se fechasse hoje")
               + f" · ponto de {_ini[8:10]}/{_ini[5:7]} a {_fim[8:10]}/{_fim[5:7]} (RHiD, até ontem)"
               + f" · salário em {_d0['pagamento'][8:10]}/{_d0['pagamento'][5:7]} · metas do mês no 5º dia útil"
               + (f" ({q:%d/%m})" if q else "")
               + " · valor da hora = salário ÷ horas do mês"
               + (f" ({next(d for d in por.values() if d)['horas_do_mes_min'] / 60:.0f}h)"
                  if any(por.values()) else ""))
    nomes = {u: str(n).split(" ")[0] for u, n in _pc.MEMBROS_ATIVOS.items()}
    assinadas = None
    if _hl.pode_assinar(ano, mes, hoje):
        try:
            assinadas = _md._assinaturas_guardadas(ano, mes)
        except Exception as e:
            st.warning(f"Não consegui ler as assinaturas: {str(e)[:120]}")
    sal, tot = linhas_salario(por, nomes, assinadas)
    met, tot_m = linhas_metas(por, nomes)
    k = st.columns(4)
    k[0].metric("Salários · dia 30", _brl(tot["pagar"]))
    k[1].metric("Metas · 5º dia útil", _brl(tot_m))
    k[2].metric("Total do mês", _brl(tot["pagar"] + tot_m))
    _desc_tot = round(sum(d["folha"].get("desconto_total", d["folha"]["desconto"])
                          for d in por.values() if d), 2)
    k[3].metric("Descontos (ponto + manuais)", ("− " + _brl(_desc_tot)) if _desc_tot else _brl(0))
    with st.container(border=True):
        st.markdown("**SALÁRIO — PELO PONTO**")
        st.dataframe(pd.DataFrame(sal), use_container_width=True, hide_index=True)
    _marcar_domingos(por, nomes, ano, mes, usuario_logado)
    _ajustes_manuais(por, nomes, ano, mes, usuario_logado)
    with st.container(border=True):
        st.markdown("**METAS — % DO SALÁRIO BASE**")
        st.dataframe(pd.DataFrame(met), use_container_width=True, hide_index=True)
        st.caption("Cada metade paga o nível mais alto: a MAXX substitui a mensal. "
                   "Os critérios são os mesmos da Análise de Metas.")
    with st.container(border=True):
        st.markdown("**🧾 HOLERITE**")
        _quem = [u for u, d in sorted(por.items(), key=lambda kv: nomes.get(kv[0], kv[0])) if d]
        _u = st.selectbox("Colaborador", _quem, format_func=lambda u: nomes.get(u, u),
                          key=f"folha_holerite_{ano}_{mes}")
        if _u:
            st.markdown(_hl.html(por[_u], _pc.MEMBROS_ATIVOS.get(_u, _u),
                                 (assinadas or {}).get(_u)), unsafe_allow_html=True)
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
                     **_fm_t.aplicar_ajustes(_f, _v),
                     "faltas": ["2026-10-14"], "domingo_nas": [], "devidas_min": _d,
                     "total": 0},
            "fulano": None}
    _s, _t = linhas_salario(_por, {"luiz": "Luiz"})
    _sa, _ = linhas_salario(_por, {"luiz": "Luiz"}, {"luiz": {"assinado_em": "30/10/2026 09:14"}})
    ok("coluna da folha de ponto: só com o período assinável, e com a data",
       "Folha de ponto" not in _s[0] and _sa[0]["Folha de ponto"] == "✓ 30/10"
       and linhas_salario(_por, {}, {})[0][0]["Folha de ponto"] == "pendente")
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
    # 09/11: OS AJUSTES DO DONO pela cadeia — `aplicar_ajustes` de verdade.
    _f2 = _fm_t.apurar(2200, _d - 480, 0, _d, 0, ["2026-10-14"], True, horas_do_mes_min=_d)
    _aj = ajuste_do_formulario([{"Descrição": "Faltas não remuneradas", "Valor (R$)": 50.0},
                                {"Descrição": float("nan"), "Valor (R$)": float("nan")},
                                {"Descrição": "Porta 2 Relógio + Jóias", "Valor (R$)": "12,5"}],
                               True, "  Descontos aplicados no repasse do lucro.  ")
    ok("o formulário vira o ajuste: linha vazia fora, vírgula vira número, obs aparada",
       _aj == {"descontos": [("Faltas não remuneradas", 50.0), ("Porta 2 Relógio + Jóias", 12.5)],
               "no_bonus": True, "obs": "Descontos aplicados no repasse do lucro.", "ponto": None})
    ok("o desconto do ponto informado vai no ajuste, em valor positivo",
       ajuste_do_formulario([], False, "", -376.13)["ponto"] == 376.13
       and ajuste_do_formulario([], False, "")["ponto"] is None)
    _pb = {"luiz": {"folha": _f2, "metas": _l, "pct_metas": _p, "metas_valor": _v,
                    **_fm_t.aplicar_ajustes(_f2, _v, _aj),
                    "faltas": ["2026-10-14"], "domingo_nas": [], "devidas_min": _d}}
    _sb, _tb = linhas_salario(_pb, {"luiz": "Luiz"})
    _mb, _tmb = linhas_metas(_pb, {"luiz": "Luiz"})
    ok("marcado: o salário sai integral e a coluna diz que o desconto vai nas metas",
       _sb[0]["Salário a pagar"] == "R$ 2.200,00" and _sb[0]["Desconto"] == "nas metas"
       and _tb["desc"] == 0)
    ok("e as metas pagam o que sobra: 264 − (100 do ponto + 62,50 manuais) = 101,50",
       _tmb == 101.5 and _mb[0]["Descontos"] == "− R$ 162,50"
       and _mb[0]["Metas a pagar"] == "R$ 101,50")
    _f3 = _fm_t.apurar(2200, _d - 480, 0, _d, 0, ["2026-10-14"], True, horas_do_mes_min=_d)
    _p3 = {"folha": _f3, "metas": _l, "pct_metas": _p, "metas_valor": _v,
           **_fm_t.aplicar_ajustes(_f3, _v, {"descontos": [("faltas", 10.0)], "no_bonus": True,
                                             "saldos": [("Saldo de 09/2026 não coberto pelas metas", 50.0)]})}
    ok("o saldo que veio do mês anterior não volta ao formulário como desconto digitado",
       ajuste_da_pessoa(_p3)["descontos"] == [("faltas", 10.0)]
       and _p3["saldos_recebidos"] == [("Saldo de 09/2026 não coberto pelas metas", 50.0)])
    ok("o ajuste gravado volta ao formulário igual",
       ajuste_da_pessoa(_pb["luiz"]) == _aj)
    # 09/11, medido no Chromium com o Streamlit real (aba de mentira): salvar
    # mostra o aviso, a legenda diz o que está gravado, e o holerite de baixo
    # abre na pessoa ajustada — ele abria na primeira da lista.
    import inspect as _insp_t
    _src_aj = _insp_t.getsource(_ajustes_manuais)
    ok("salvar deixa o aviso para depois do redesenho e abre o holerite na pessoa ajustada",
       "st.session_state[AVISO_AJUSTE] =" in _src_aj
       and 'st.session_state[f"folha_holerite_{ano}_{mes}"] = u' in _src_aj
       and _src_aj.index("st.session_state[AVISO_AJUSTE] =") < _src_aj.index("st.rerun()")
       and "st.session_state.pop(AVISO_AJUSTE" in _src_aj)
    ok("salvar leva ao mês seguinte o que não coube nas metas (dono, 10/11)",
       "_fm.saldo_a_levar(" in _src_aj and "_fm.gravar_saldo(ano, mes, u, saldo" in _src_aj
       and _src_aj.index("_fm.gravar_ajuste(") < _src_aj.index("_fm.gravar_saldo("))
    print("\nfalhas:", falhas)
    raise SystemExit(1 if falhas else 0)
