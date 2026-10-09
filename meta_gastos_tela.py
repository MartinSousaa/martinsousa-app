"""meta_gastos_tela.py — a aba Meta de Gastos, no Financeiro.

Doze linhas, um ano. A meta se digita; o realizado vem dos extratos quando o
mês tem extrato, e do que o dono informou quando não tem — e a tela diz qual
dos dois está mostrando, porque "74.210,55" conferido e "74.210,55" de memória
não valem a mesma coisa na hora de decidir.
"""

import streamlit as st

import rotulos as _rot


def _fmt(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _de_onde_vem(ano, hoje):
    """O realizado de um mês, aberto: por conta, por finalidade, o que ficou
    fora da meta e as linhas com data que não cai em mês nenhum.

    Existe por causa de setembro/2026: a tela dizia R$ 46 mil com todos os
    extratos subidos, e não havia onde olhar o porquê. A conta mora em
    `lancamentos.explicar_mes`; aqui só se desenha.
    """
    import pandas as pd
    import lancamentos as _lan
    MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
             "agosto", "setembro", "outubro", "novembro", "dezembro"]
    with st.expander("🔎 De onde vem o realizado", expanded=False):
        mes = st.selectbox("Mês", list(range(1, 13)), index=hoje.month - 1,
                           format_func=lambda m: MESES[m - 1], key="mg_explica_mes")
        try:
            x = _lan.explicar_mes(int(ano), int(mes))
        except Exception as e:
            st.error(f"Não consegui ler os lançamentos: {str(e)[:150]}")
            return
        st.markdown(_rot.tela(
            f"**{x['linhas']} lançamento(s)** em {MESES[mes - 1]}/{ano} · "
            f"realizado da meta **R$ {_fmt(x['realizado'])}**"))
        if x["por_conta"]:
            st.caption("Por conta — confira se todas as contas e todo o período "
                       "do mês estão aqui:")
            st.dataframe(pd.DataFrame([
                {"conta": k, "linhas": v["linhas"], "saídas": v["saidas"],
                 "entradas": v["entradas"], "primeiro dia": v["de"],
                 "último dia": v["ate"]} for k, v in x["por_conta"].items()]),
                use_container_width=True, hide_index=True)
        if x["consome"]:
            st.caption("Entra na meta, por finalidade:")
            st.dataframe(pd.DataFrame([{"finalidade": k, "valor": v}
                                       for k, v in x["consome"].items()]),
                         use_container_width=True, hide_index=True)
        _cart = x.get("cartao") or {}
        if _cart.get("pago") or _cart.get("detalhado"):
            # O cartão conta UMA vez: pelas compras da fatura lançada, cada
            # uma na finalidade dela, no mês do vencimento; o pagamento só
            # entra pelo que essas compras ainda não explicam.
            st.caption(_rot.tela(
                f"💳 Cartão no mês: extrato pagou **R$ {_fmt(_cart['pago'])}** · "
                f"compras de fatura lançadas **R$ {_fmt(_cart['detalhado'])}** "
                f"(cada uma na sua finalidade) · sem detalhe, como FATURA DO "
                f"CARTÃO, **R$ {_fmt(_cart['sem_detalhe'])}**."
                + (" Anexe a fatura e confirme para separar esse valor por "
                   "finalidade." if _cart["sem_detalhe"] else "")))
        if x["fora"]:
            st.caption("Saídas que **não** entram na meta — transferência entre "
                       "contas, aplicação e resgate não são gasto. Se um "
                       "pagamento de verdade está aqui, a finalidade do "
                       "favorecido está errada (Financeiro › Finalidades):")
            st.dataframe(pd.DataFrame([{"finalidade": k, "valor": t, "linhas": n}
                                       for k, (t, n) in x["fora"].items()]),
                         use_container_width=True, hide_index=True)
        if x["por_dia"]:
            st.caption("Saídas que contam, dia a dia:")
            st.bar_chart(pd.DataFrame({"saídas": list(x["por_dia"].values())},
                                      index=[d[-2:] for d in x["por_dia"]]),
                         use_container_width=True)
        if x["data_invalida"]:
            st.warning(_rot.tela(
                f"**{x['data_invalida']} lançamento(s) com data fora do formato "
                "AAAA-MM-DD** na aba inteira. Eles não caem em mês nenhum e "
                "não somam em lugar nenhum. Exemplos:"))
            st.dataframe(pd.DataFrame(x["exemplos_invalidos"]),
                         use_container_width=True, hide_index=True)


def pagina(usuario_logado=None):
    from datetime import datetime
    import pandas as pd
    import placar_core as _pc
    import meta_gastos as _mg

    st.markdown("#### 🎯 Meta de gastos")

    hoje = datetime.now(_pc.FUSO).date()
    _ca, _cb = st.columns([2, 1])
    ano = _ca.number_input("Ano", 2020, 2100, hoje.year, 1, key="mg_ano")
    # Fica ACIMA do editor de propósito: botão embaixo dele é o clique que se
    # perde quando a célula ainda está aberta.
    if _cb.button("🔄 Reler a planilha", key="mg_reler"):
        _mg.carregar.clear()

    # O que a PLANILHA tem para o mês corrente, dito antes de qualquer edição.
    #
    # Sem esta linha, "não gravou" e "gravou zero" ficam iguais na tela, e a
    # única forma de saber qual dos dois é abrir a planilha na mão. Em 17/09
    # isso custou três idas e vindas.
    _hoje_txt = _mg.texto_mes(ano, hoje.month)
    _gravado = (_mg.carregar() or {}).get(_hoje_txt)
    if _gravado is None:
        st.warning(
            f"**Nada gravado para {_mg.rotulo(_hoje_txt)}.** A planilha não tem "
            "linha deste mês — digite a meta na tabela abaixo e clique em "
            "**Salvar**. Enquanto não houver linha, a Home mostra «—».")
    else:
        _m = _gravado["meta"]
        st.caption(
            f"Gravado na planilha para **{_mg.rotulo(_hoje_txt)}**: meta "
            + (f"**R$ {_fmt(_m)}** — é este o número que a Home mostra."
               if _m else
               "**R$ 0,00**. Enquanto a meta for zero, a Home mostra «—», "
               "mesmo com gasto informado no mês."))

    # A aba crua, do jeito que o Google devolve. Existe porque durante horas
    # a tela e a planilha discordaram e não havia como saber qual das duas
    # mentia — nem para o dono, nem para quem mexe no código.
    with st.expander("🔍 O que está na aba `meta_gastos` (linha por linha)"):
        try:
            import pandas as _pd
            _cru = _mg.linhas_cruas()
            st.dataframe(_pd.DataFrame(_cru), use_container_width=True,
                         hide_index=True)
            _rep = {}
            for _r in _cru:
                _k = _mg.mes_chave(_r.get("mes"))
                if _k:
                    _rep[_k] = _rep.get(_k, 0) + 1
            _dobradas = sorted(k for k, n in _rep.items() if n > 1)
            if _dobradas:
                st.warning(
                    "Mês repetido na aba: " + ", ".join(_dobradas)
                    + ". Salvar o mês unifica as linhas.")
            else:
                st.caption("Nenhum mês repetido.")
        except Exception as _e:
            st.caption(f"Não consegui ler a aba: {str(_e)[:160]}")

    linhas = _mg.ano_inteiro(ano)
    atual = next((l for l in linhas if l["mes"] == _mg.texto_mes(ano, hoje.month)),
                 None)
    if atual and atual["meta"]:
        # O COMPROMETIDO, e não só o que já saiu.
        #
        # A tabela abaixo é do ano inteiro e mostra o REALIZADO, que é o que o
        # extrato viu — está certo para mês fechado. Mas para o mês corrente
        # essa é a metade barata da história: cheque a vencer, folha, aluguel e
        # fatura do cartão já estão devidos. Decidir compra pelo realizado do
        # dia 18 é decidir com metade do mês escondida.
        #
        # Só do mês corrente: o previsto custa caro (uma das fontes abre o
        # Controle MS inteiro) e, para os meses fechados, não acrescenta nada.
        _prev, _erros_prev, _comp, _a_sair = {}, [], atual["realizado"], 0.0
        try:
            import previsto as _pv
            import lancamentos as _lan_t
            _prev, _erros_prev = _pv.do_mes(ano, hoje.month)
            _lancs_t = _lan_t.do_mes(ano, hoje.month)
            _res_t = _lan_t.resumo_por_finalidade(_lancs_t)
            _linhas_c, _comp = _pv.combinar(_res_t, _prev,
                                            _lan_t.cartao_detalhado(_lancs_t))
            _a_sair = round(sum(x["falta_sair"] for x in _linhas_c), 2)
        except Exception as _e_prev:
            _erros_prev = [str(_e_prev)[:120]]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Meta de " + atual["rotulo"].split()[0],
                  f"R$ {_fmt(atual['meta'])}")
        c2.metric("Já saiu", f"R$ {_fmt(atual['realizado'])}",
                  help=f"o que o extrato mostra · origem: {atual['origem']}")
        c3.metric("Comprometido", f"R$ {_fmt(_comp)}",
                  delta=(f"+{_fmt(_a_sair)} ainda vai sair" if _a_sair else None),
                  delta_color="inverse",
                  help="já saiu, mais custo fixo, folha, não operacional, "
                       "cheque a vencer e fatura do cartão deste mês")
        _sobra = round(atual["meta"] - _comp, 2)
        c4.metric("Sobra da meta", f"R$ {_fmt(_sobra)}",
                  delta=f"{(_comp / atual['meta'] * 100):.0f}% comprometido",
                  delta_color="inverse")
        if _erros_prev:
            st.caption("⚠️ Não consegui ler o previsto de: "
                       + " · ".join(_erros_prev))
        if _prev:
            st.caption("Provisionado neste mês — " + " · ".join(
                f"{k} R$ {_fmt(v)}" for k, v in _prev.items() if v))
        _acompanhar_mes(ano, hoje, atual["meta"], _comp)

    ORIGEM = {"extrato": "📄 extrato", "informado": "✍️ informado",
              "sem dado": "— sem dado"}
    df = pd.DataFrame([{
        "mês": l["rotulo"],
        "meta": l["meta"],
        "realizado": l["realizado"],
        "de onde": ORIGEM.get(l["origem"], l["origem"]),
        "saldo": l["saldo"],
        "informado": l["informado"],
        "projeção de vendas": int(l.get("projecao_vendas") or 0),
        "observação": l["observacao"],
    } for l in linhas])

    st.caption("**Digita-se a META e a PROJEÇÃO DE VENDAS.** As outras são "
               "calculadas ou vieram do extrato. A projeção é quantas vendas "
               "você espera no mês: com ela o LPV do mês corrente é calculado "
               "(custo fixo + salários da gerência + não operacional ÷ vendas).")

    # Editor e botão dentro do MESMO formulário, e não por capricho.
    #
    # Com o botão solto, o clique que sai da célula ainda em edição fazia duas
    # coisas ao mesmo tempo: fechava a célula e disparava o rerun. O rerun
    # consumia o clique, o botão nunca rodava, e a tela não dizia nada — o
    # gestor digitava a meta, clicava, e ia embora achando que tinha salvo.
    # Foi exatamente o que aconteceu com a meta de setembro em 17/09. Dentro do
    # formulário, a edição e o envio viram um evento só.
    with st.form("mg_form"):
        editado = st.data_editor(
            df, use_container_width=True, hide_index=True, key="mg_ed",
            column_config={**_rot.config(["mês", "meta", "realizado", "de onde", "saldo", "informado", "observação"], st), 
                "mês": st.column_config.TextColumn(disabled=True,
                                                   width="small"),
                "meta": st.column_config.NumberColumn(
                    "🎯 META — digite aqui", format="R$ %.2f", min_value=0.0,
                    step=100.0,
                    help="Quanto se pode gastar no mês. É esta a coluna que a "
                         "Home lê em «Meta do mês», e é a única que se "
                         "digita."),
                "realizado": st.column_config.NumberColumn(
                    "Realizado", format="R$ %.2f", disabled=True),
                "de onde": st.column_config.TextColumn(disabled=True,
                                                       width="small"),
                "saldo": st.column_config.NumberColumn("Saldo", format="R$ %.2f",
                                                       disabled=True),
                "informado": st.column_config.NumberColumn(
                    "Gasto informado (histórico)", format="R$ %.2f",
                    disabled=True,
                    help="O gasto dos meses anteriores ao extrato, vindo da "
                         "sua planilha. Não se digita aqui: quando o extrato "
                         "entra, é ele que manda."),
                "projeção de vendas": st.column_config.NumberColumn(
                    "📦 PROJEÇÃO DE VENDAS — digite aqui", format="%d",
                    min_value=0, step=100,
                    help="Quantas vendas você espera no mês. O LPV do mês "
                         "corrente divide o custo fixo por este número; "
                         "quando o mês fecha, vale o número real."),
                "observação": st.column_config.TextColumn(width="medium"),
            },
        )
        enviou = st.form_submit_button("💾 Salvar", type="primary",
                                       use_container_width=True)

    if enviou:
        _n = 0
        for i, r in editado.iterrows():
            antes = linhas[i]
            _proj = float(r.get("projeção de vendas") or 0)
            if _proj != _proj:            # NaN da célula apagada
                _proj = 0.0
            if (float(r["meta"]) == antes["meta"]
                    and float(r["informado"]) == antes["informado"]
                    and str(r["observação"] or "") == antes["observacao"]
                    and _proj == float(antes.get("projecao_vendas") or 0)):
                continue
            _ok, _msg = _mg.salvar(antes["mes"], meta=float(r["meta"]),
                                   informado=float(r["informado"]),
                                   observacao=str(r["observação"] or ""),
                                   usuario=usuario_logado, projecao=_proj)
            if not _ok:
                st.error(_msg)
                return
            _n += 1
        if not _n:
            st.info(
                "Nada mudou — os valores da tabela são iguais aos que já "
                "estão gravados. Se você digitou e não salvou, o número volta "
                "ao anterior assim que a tela recarrega.")
        else:
            # A prova, relida da planilha. Sem ela, "salvo" é promessa: já
            # aconteceu de o botão não rodar e a tela não dizer nada.
            _mg.carregar.clear()
            try:
                import lpv_mensal as _lm_c
                _lm_c.lpv_projetado.clear()
            except Exception:
                pass
            _grav = _mg.carregar()
            st.success(f"{_n} mês(es) salvo(s).")
            st.dataframe(pd.DataFrame(
                [{"mês": _mg.rotulo(m), "meta gravada": v["meta"],
                  "informado": v["informado"]}
                 for m, v in sorted(_grav.items()) if m.startswith(str(ano))
                 and (v["meta"] or v["informado"])]),
                use_container_width=True, hide_index=True)

    _de_onde_vem(ano, hoje)

    _com_dado = [l for l in linhas if l["origem"] != "sem dado"]
    if _com_dado:
        st.markdown("##### Realizado no ano")
        st.bar_chart(
            pd.DataFrame({"realizado": [l["realizado"] for l in _com_dado]},
                         index=[l["rotulo"].split()[0] for l in _com_dado]),
            use_container_width=True)
    _equilibrio_real(ano, hoje, linhas)

    _sem = [l["rotulo"].split()[0] for l in linhas if l["origem"] == "sem dado"]
    if _sem:
        st.caption("Sem dado ainda: " + ", ".join(_sem)
                   + ". Mês sem número não é mês sem gasto — preencha em "
                     "«Informado por você» ou suba o extrato.")


def _equilibrio_real(ano, hoje, linhas):
    """Os meses FECHADOS: a meta do dia 1º contra o que saiu e o que entrou.

    O mês corrente não aparece (dono, 09/10): ele só se compara depois de
    fechar. As contas são `equilibrio_caixa.equilibrio_real`.
    """
    import pandas as pd
    import base_vendas as _bv
    import equilibrio_caixa as _ec
    fechados = set(_ec.meses_fechados(ano, hoje))
    meses = [(i, l) for i, l in enumerate(linhas, start=1)
             if i in fechados and l.get("meta")]
    if not meses:
        return
    mapa, erro = _bv.somas_por_mes()
    st.markdown("##### ⚖️ Equilíbrio real — meses fechados")
    if erro:
        st.warning(f"Não consegui ler a BASE DE VENDAS: {erro}")
        return
    tabela = []
    for i, l in meses:
        r = _ec.equilibrio_real(l["meta"], l["realizado"], l["origem"],
                                mapa, ano, i)
        tabela.append({
            "mês": l["rotulo"].split()[0].capitalize(),
            "meta de gastos": r["meta"],
            "equilíbrio planejado": r["planejado"],
            "gasto real": r["gasto_real"] or None,
            "equilíbrio real": r["real"],
            "faturado (líquido)": r["faturado"],
            "resultado": r["resultado"],
            "situação": (r["motivo"] or
                         (("⚠️ gasto real menos da metade da meta — "
                           "extratos completos?") if r["suspeito"] else
                          ("✅ cobriu" if (r["resultado"] or 0) >= 0
                           else "❌ faltou"))
                         + (" · gasto informado à mão"
                            if r["origem_gasto"] == "informado" else "")),
        })
    _dinheiro = ["meta de gastos", "equilíbrio planejado", "gasto real",
                 "equilíbrio real", "faturado (líquido)", "resultado"]
    st.dataframe(pd.DataFrame(tabela), use_container_width=True,
                 hide_index=True,
                 column_config=_rot.config(list(tabela[0]), st,
                                           tipos={c: "brl" for c in _dinheiro}))


def _acompanhar_mes(ano, hoje, meta, comprometido):
    """O mês em andamento, projetado × real (dono, 09/10).

    A meta de gastos continua sendo o número de cima; isto é o
    acompanhamento embaixo dela. As contas são
    `equilibrio_caixa.acompanhamento`; a margem é a média dos 3 meses
    lançados (`base_vendas.media_recente`, a mesma da Home) e o faturado é o
    do Bling (`home_gestao._faturamento_bling`, com cache).
    """
    from datetime import datetime
    import pandas as pd
    import base_vendas as _bv
    import equilibrio_caixa as _ec
    import home_gestao as _hg
    import placar_core as _pc
    if int(ano) != hoje.year:
        return
    ind, erro_bv = _bv.media_recente(hoje.year, hoje.month, quantos=3)
    fat, avisos_fat = _hg._faturamento_bling(hoje.year, hoje.month)
    a = _ec.acompanhamento(meta, comprometido, (ind or {}).get("margem_bruta"),
                           fat, agora=datetime.now(_pc.FUSO))
    st.markdown("##### 📈 Acompanhamento do mês — projetado × real")
    if erro_bv:
        st.warning(f"Sem a margem da BASE DE VENDAS: {erro_bv}")
    for _a in (avisos_fat or []):
        st.caption(f"⚠️ {_a}")
    linhas = [(r, p, v) for r, p, v in a["grafico"]
              if p is not None or v is not None]
    if linhas:
        st.bar_chart(
            pd.DataFrame([{"linha": r, "Projetado": p or 0.0, "Real": v or 0.0}
                          for r, p, v in linhas]).set_index("linha"),
            horizontal=True, stack=False, color=["#8A93A3", "#E0A13A"])
    if a["fecha_em"] is not None and a["eq_real"]:
        _txt = (f"No ritmo de hoje o mês fecha em {_rot.brl(a['fecha_em'])} — "
                + (f"sobram {_rot.brl(a['sobra_no_fim'])}"
                   if a["sobra_no_fim"] >= 0 else
                   f"faltam {_rot.brl(-a['sobra_no_fim'])}")
                + f" para o equilíbrio real de {_rot.brl(a['eq_real'])}.")
        (st.success if a["sobra_no_fim"] >= 0 else st.warning)(_rot.tela(_txt))

