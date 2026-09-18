"""cheques_tela.py — a carteira de cheques no Studio.

Três perguntas, nesta ordem, porque é a ordem da decisão:

    quanto ainda vai sair?      em aberto
    o que já devia ter saído?   pendente — venceu e não baixou
    quanto sai neste mês?       a vencer no mês

EM ABERTO e PENDENTE não são campos: são conta, feita na hora, contra a data de
hoje. Escritas à mão na planilha elas erram no dia seguinte — o cheque de 25/09
vira pendente sozinho em 26/09, e ninguém reabre a planilha para mover a
célula.
"""

from datetime import datetime

import streamlit as st


def _brl(v):
    return "R$ " + f"{float(v or 0):,.2f}".replace(",", "X").replace(
        ".", ",").replace("X", ".")


def pagina(usuario_logado=None):
    import pandas as pd
    import cheques as _ch
    import placar_core as _pc

    st.markdown("#### 🧾 Cheques")
    st.caption(
        "O cheque emitido, que o extrato só conhece no dia em que compensa. "
        "Aqui ele existe desde que foi dado — e é assim que entra no "
        "comprometido do mês, na Home."
    )

    hoje = datetime.now(_pc.FUSO).date()
    linhas = _ch.carregar()

    # ── importar ─────────────────────────────────────────────────────────
    # Fora e ACIMA de qualquer editor: botão embaixo de grade é o clique que
    # se perde quando a célula ainda está aberta.
    ci, cb = st.columns([3, 1])
    ci.caption(
        "A primeira carga vem da aba **CHEQUES** do seu Controle MS. Depois "
        "disso o cadastro vive aqui: importar de novo não duplica (o número da "
        "folha é a identidade) nem desfaz baixa dada nesta tela."
    )
    if cb.button("📥 Importar do Controle MS", use_container_width=True,
                 key="ch_importar"):
        brutos, erro = _ch.do_controle_ms()
        if erro:
            st.error(f"Não consegui ler: {erro}")
        else:
            novas, repetidas, erro_g = _ch.gravar(brutos, usuario_logado)
            if erro_g:
                st.error(f"Li {len(brutos)} da planilha e não gravei: {erro_g}")
            else:
                st.success(
                    f"{novas} cheque(s) novo(s) gravado(s)"
                    + (f" · {repetidas} já estavam aqui" if repetidas else "")
                )
                linhas = _ch.carregar()

    if not linhas:
        st.info("Nenhum cheque cadastrado ainda. Importe do Controle MS ou "
                "cadastre um abaixo.")

    # ── os três números ──────────────────────────────────────────────────
    aberto = _ch.em_aberto(linhas)
    atrasado = _ch.pendente(linhas, hoje)
    no_mes = _ch.a_vencer(linhas, hoje.year, hoje.month)
    c1, c2, c3 = st.columns(3)
    c1.metric("Em aberto", _brl(aberto), help="tudo que ainda não baixou")
    c2.metric("Pendente", _brl(atrasado),
              delta=f"{len(_ch.vencidos_sem_baixa(linhas, hoje))} cheque(s)",
              delta_color="inverse",
              help="venceu e não baixou. Ou a baixa não foi dada, ou o cheque "
                   "não foi apresentado — nos dois casos é trabalho parado.")
    c3.metric(f"Vence em {hoje.month:02d}/{hoje.year}", _brl(no_mes))

    # As linhas cuja conta não fecha. A planilha é mantida à mão desde 2023, e
    # uma linha fora da soma é erro de digitação lá — o Studio mostra, e não
    # corrige: trocar o número dele pelo meu sem pedir seria inventar dado.
    _tortas = _ch.nao_fecham(linhas)
    if _tortas:
        with st.expander(f"🧮 {len(_tortas)} linha(s) em que valor ≠ frete + "
                         "mercadoria"):
            st.caption("Vieram assim da planilha. Confira lá — aqui nada foi "
                       "alterado.")
            st.dataframe(
                pd.DataFrame([{
                    "folha": l.get("folha", ""),
                    "vencimento": l.get("vencimento"),
                    "valor": _ch._num(l.get("valor")),
                    "frete": _ch._num(l.get("envio")),
                    "mercadoria": _ch._num(l.get("estoque")),
                    "diferença": _ch.divergencia_da_soma(l),
                } for l in _tortas[:50]]),
                use_container_width=True, hide_index=True,
                column_config={c: st.column_config.NumberColumn(format="R$ %.2f")
                               for c in ("valor", "frete", "mercadoria",
                                         "diferença")})

    atrasados = _ch.vencidos_sem_baixa(linhas, hoje)
    if atrasados:
        with st.expander(f"⚠️ {len(atrasados)} venceram e não baixaram"):
            st.dataframe(
                pd.DataFrame([{"folha": l.get("folha", ""),
                               "vencimento": l.get("vencimento"),
                               "valor": _ch._num(l.get("valor")),
                               "favorecido": l.get("favorecido", "")}
                              for l in atrasados]),
                use_container_width=True, hide_index=True,
                column_config={"valor": st.column_config.NumberColumn(
                    format="R$ %.2f")})

    # ── cadastrar ────────────────────────────────────────────────────────
    with st.expander("➕ Cadastrar cheque"):
        with st.form("ch_novo"):
            f1, f2, f3 = st.columns(3)
            folha = f1.text_input("Folha (nº do cheque)")
            tipo = f2.selectbox("Tipo", _ch.TIPOS)
            valor = f3.number_input("Valor (R$)", min_value=0.0, step=100.0,
                                    format="%.2f")
            g1, g2, g3 = st.columns(3)
            compra = g1.date_input("Compra", value=hoje, format="DD/MM/YYYY")
            venc = g2.date_input("Vencimento", value=hoje, format="DD/MM/YYYY")
            situacao = g3.selectbox("Situação", _ch.SITUACOES)
            h1, h2 = st.columns(2)
            # ESTOQUE saiu do formulário: ele é VALOR − ENVIO, e campo que se
            # calcula e mesmo assim se pede é convite a erro de digitação —
            # um erro que não aparece em lugar nenhum, porque a soma do cheque
            # continua certa.
            #
            # Também não dá para mostrá-lo vivo AQUI: dentro de `st.form` o
            # Streamlit só entrega o que foi digitado no envio, então um campo
            # "calculado" ficaria parado em zero enquanto a pessoa digita — e
            # número parado na tela é pior do que número nenhum.
            envio = h1.number_input(
                "Envio (frete)", min_value=0.0, step=50.0, format="%.2f",
                help="Quanto deste cheque foi frete. O resto é mercadoria, e o "
                     "Studio calcula sozinho.")
            favorecido = h2.text_input("Favorecido")
            st.caption("**Estoque (mercadoria) = valor − envio**, calculado ao "
                       "cadastrar. Não precisa digitar.")
            obs = st.text_input("Observação")
            criar = st.form_submit_button("💾 Cadastrar", type="primary",
                                          use_container_width=True)
        if criar:
            if not valor:
                st.error("Cheque sem valor não entra — seria uma linha que "
                         "ocupa lugar e não conta nada.")
            else:
                if envio > valor:
                    st.warning(
                        f"O frete ({_brl(envio)}) é maior que o cheque "
                        f"({_brl(valor)}) — a mercadoria fica negativa em "
                        f"{_brl(valor - envio)}. Acontece quando o cheque paga "
                        "só parte do frete; se não for o caso, confira o envio.")
                novas, repetidas, erro = _ch.gravar([{
                    "folha": folha, "tipo": tipo, "compra": compra,
                    "vencimento": venc, "valor": valor, "envio": envio,
                    "favorecido": favorecido,
                    "situacao": situacao, "observacao": obs,
                }], usuario_logado)
                if erro:
                    st.error(f"Não consegui gravar: {erro}")
                elif repetidas:
                    st.warning("Este cheque já estava cadastrado — nada mudou.")
                else:
                    st.success(
                        f"Cheque {folha or ''} cadastrado · valor "
                        f"{_brl(valor)} = frete {_brl(envio)} + mercadoria "
                        f"{_brl(round(valor - envio, 2))}.")
                    linhas = _ch.carregar()

    if not linhas:
        return

    # ── a carteira ───────────────────────────────────────────────────────
    st.markdown("##### A carteira")
    sit = sorted({_ch.situacao_de(l.get("situacao")) for l in linhas})
    s1, s2 = st.columns([2, 1])
    filtro = s1.multiselect("Situação", sit, default=["EM ABERTO"]
                            if "EM ABERTO" in sit else sit, key="ch_filtro")
    so_ano = s2.number_input("Ano do vencimento", 2020, 2100, hoje.year, 1,
                             key="ch_ano")
    vis = [l for l in linhas
           if _ch.situacao_de(l.get("situacao")) in (filtro or sit)
           and _ch.texto_data(l.get("vencimento")).startswith(str(so_ano))]
    if not vis:
        st.caption("Nenhum cheque com esses filtros.")
        return

    vis.sort(key=lambda l: _ch.texto_data(l.get("vencimento")))
    df = pd.DataFrame([{
        "id": l.get("id"),
        "folha": str(l.get("folha", "") or ""),
        "vencimento": _ch.texto_data(l.get("vencimento")),
        "valor": _ch._num(l.get("valor")),
        "envio": _ch._num(l.get("envio")),
        "estoque": _ch._num(l.get("estoque")),
        "favorecido": str(l.get("favorecido", "") or ""),
        "situação": _ch.situacao_de(l.get("situacao")),
        "apagar": False,
    } for l in vis])

    with st.form("ch_grade"):
        editado = st.data_editor(
            df, use_container_width=True, hide_index=True, key="ch_ed",
            column_config={
                "id": None,
                "folha": st.column_config.TextColumn(width="small",
                                                     disabled=True),
                "vencimento": st.column_config.TextColumn(width="small",
                                                          disabled=True),
                "valor": st.column_config.NumberColumn(format="R$ %.2f",
                                                       disabled=True),
                "envio": st.column_config.NumberColumn(format="R$ %.2f",
                                                       disabled=True),
                "estoque": st.column_config.NumberColumn(format="R$ %.2f",
                                                         disabled=True),
                "favorecido": st.column_config.TextColumn(width="medium"),
                "situação": st.column_config.SelectboxColumn(
                    options=list(_ch.SITUACOES), width="small",
                    help="Dar baixa aqui tira o cheque do comprometido do mês. "
                         "O extrato faz isso sozinho quando o débito aparece."),
                "apagar": st.column_config.CheckboxColumn(
                    "🗑️", help="Marque e salve para remover a linha."),
            })
        gravar = st.form_submit_button("💾 Salvar alterações", type="primary",
                                       use_container_width=True)

    if gravar:
        antes = {l["id"]: l for l in vis}
        mudou, erros = 0, []
        apagar = [r["id"] for _, r in editado.iterrows() if r["apagar"]]
        for _, r in editado.iterrows():
            if r["apagar"]:
                continue
            a = antes.get(r["id"], {})
            campos = {}
            if _ch.situacao_de(a.get("situacao")) != r["situação"]:
                campos["situacao"] = r["situação"]
            if str(a.get("favorecido", "") or "") != str(r["favorecido"] or ""):
                campos["favorecido"] = str(r["favorecido"] or "")
            if not campos:
                continue
            ok, msg = _ch.atualizar(r["id"], campos, usuario_logado)
            mudou += ok
            if not ok:
                erros.append(msg)
        n_apagados, erro_ap = (_ch.apagar(apagar) if apagar else (0, ""))
        if erros or erro_ap:
            st.error(" · ".join(erros + ([erro_ap] if erro_ap else [])))
        if mudou or n_apagados:
            st.success(f"{mudou} alterado(s)"
                       + (f" · {n_apagados} apagado(s)" if n_apagados else ""))
            _atual = _ch.carregar()
            st.caption(
                f"Agora: em aberto {_brl(_ch.em_aberto(_atual))} · pendente "
                f"{_brl(_ch.pendente(_atual, hoje))}")
        elif not erros and not erro_ap:
            st.info("Nada mudou.")
