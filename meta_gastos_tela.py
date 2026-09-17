"""meta_gastos_tela.py — a aba Meta de Gastos, no Financeiro.

Doze linhas, um ano. A meta se digita; o realizado vem dos extratos quando o
mês tem extrato, e do que o dono informou quando não tem — e a tela diz qual
dos dois está mostrando, porque "74.210,55" conferido e "74.210,55" de memória
não valem a mesma coisa na hora de decidir.
"""

import streamlit as st


def _fmt(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pagina(usuario_logado=None):
    from datetime import datetime
    import pandas as pd
    import placar_core as _pc
    import meta_gastos as _mg

    st.markdown("#### 🎯 Meta de gastos")
    st.caption(
        "Quanto se pode gastar no mês, e quanto já saiu. O realizado vem dos "
        "extratos; nos meses anteriores à entrada deles, do que você informar "
        "aqui."
    )

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
        st.caption(
            f"Gravado na planilha para **{_mg.rotulo(_hoje_txt)}**: meta "
            f"R$ {_fmt(_gravado['meta'])} · informado "
            f"R$ {_fmt(_gravado['informado'])}. É isto que a Home lê.")

    linhas = _mg.ano_inteiro(ano)
    atual = next((l for l in linhas if l["mes"] == _mg.texto_mes(ano, hoje.month)),
                 None)
    if atual and atual["meta"]:
        c1, c2, c3 = st.columns(3)
        c1.metric("Meta de " + atual["rotulo"].split()[0],
                  f"R$ {_fmt(atual['meta'])}")
        c2.metric("Realizado", f"R$ {_fmt(atual['realizado'])}",
                  help=f"origem: {atual['origem']}")
        c3.metric("Saldo", f"R$ {_fmt(atual['saldo'])}",
                  delta=f"{atual['pct']:.0f}% consumido",
                  delta_color="inverse")

    ORIGEM = {"extrato": "📄 extrato", "informado": "✍️ informado",
              "sem dado": "— sem dado"}
    df = pd.DataFrame([{
        "mês": l["rotulo"],
        "meta": l["meta"],
        "realizado": l["realizado"],
        "de onde": ORIGEM.get(l["origem"], l["origem"]),
        "saldo": l["saldo"],
        "informado": (l["realizado"] if l["origem"] == "informado" else 0.0),
        "observação": l["observacao"],
    } for l in linhas])

    st.caption("Edite **meta** e, nos meses sem extrato, **informado**. "
               "As demais colunas são calculadas.")

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
            column_config={
                "mês": st.column_config.TextColumn(disabled=True,
                                                   width="small"),
                "meta": st.column_config.NumberColumn("Meta", format="%.2f",
                                                      min_value=0.0,
                                                      step=100.0),
                "realizado": st.column_config.NumberColumn(
                    "Realizado", format="%.2f", disabled=True),
                "de onde": st.column_config.TextColumn(disabled=True,
                                                       width="small"),
                "saldo": st.column_config.NumberColumn("Saldo", format="%.2f",
                                                       disabled=True),
                "informado": st.column_config.NumberColumn(
                    "Informado por você", format="%.2f", min_value=0.0,
                    step=100.0,
                    help="Só vale nos meses sem extrato carregado. Quando o "
                         "extrato entra, ele manda — é o número conferível."),
                "observação": st.column_config.TextColumn(width="medium"),
            },
        )
        enviou = st.form_submit_button("💾 Salvar", type="primary",
                                       use_container_width=True)

    if enviou:
        _n = 0
        for i, r in editado.iterrows():
            antes = linhas[i]
            _inf_antes = (antes["realizado"] if antes["origem"] == "informado"
                          else 0.0)
            if (float(r["meta"]) == antes["meta"]
                    and float(r["informado"]) == _inf_antes
                    and str(r["observação"] or "") == antes["observacao"]):
                continue
            _ok, _msg = _mg.salvar(antes["mes"], meta=float(r["meta"]),
                                   informado=float(r["informado"]),
                                   observacao=str(r["observação"] or ""),
                                   usuario=usuario_logado)
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
            _grav = _mg.carregar()
            st.success(f"{_n} mês(es) salvo(s).")
            st.dataframe(pd.DataFrame(
                [{"mês": _mg.rotulo(m), "meta gravada": v["meta"],
                  "informado": v["informado"]}
                 for m, v in sorted(_grav.items()) if m.startswith(str(ano))
                 and (v["meta"] or v["informado"])]),
                use_container_width=True, hide_index=True)

    _com_dado = [l for l in linhas if l["origem"] != "sem dado"]
    if _com_dado:
        st.markdown("##### Realizado no ano")
        st.bar_chart(
            pd.DataFrame({"realizado": [l["realizado"] for l in _com_dado]},
                         index=[l["rotulo"].split()[0] for l in _com_dado]),
            use_container_width=True)
    _sem = [l["rotulo"].split()[0] for l in linhas if l["origem"] == "sem dado"]
    if _sem:
        st.caption("Sem dado ainda: " + ", ".join(_sem)
                   + ". Mês sem número não é mês sem gasto — preencha em "
                     "«Informado por você» ou suba o extrato.")
