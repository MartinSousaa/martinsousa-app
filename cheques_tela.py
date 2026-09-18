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
    with st.expander("➕ Cadastrar cheque(s) de uma compra"):
        # QUANTOS CHEQUES — fora do formulário, de propósito.
        #
        # O número de linhas do formulário depende dele, e dentro de `st.form`
        # o Streamlit só entrega o valor no envio: escolher "3" não desenharia
        # as três linhas até alguém enviar. Aqui ele é um seletor solto, que é
        # seguro — o problema do botão solto era o clique perdido ao lado de
        # uma grade em edição, e não existe grade aqui.
        n = st.number_input(
            "Quantos cheques nesta compra?", min_value=1, max_value=12,
            value=1, step=1, key="ch_qtd",
            help="Uma compra fechada em vários cheques. Compra, favorecido, "
                 "valor total e frete são os mesmos; folha e vencimento são "
                 "de cada um.")

        with st.form("ch_novo"):
            st.markdown("**A compra** — vale para todos os cheques")
            f1, f2, f3 = st.columns(3)
            favorecido = f1.text_input("Favorecido")
            tipo = f2.selectbox("Tipo", _ch.TIPOS)
            compra = f3.date_input("Data da compra", value=hoje,
                                   format="DD/MM/YYYY")
            g1, g2, g3 = st.columns(3)
            valor_total = g1.number_input(
                "Valor TOTAL da compra (R$)", min_value=0.0, step=100.0,
                format="%.2f",
                help="O total fechado com o fornecedor. O Studio divide em "
                     "partes iguais entre os cheques.")
            envio_total = g2.number_input(
                "Frete TOTAL (R$)", min_value=0.0, step=50.0, format="%.2f",
                help="Também dividido entre os cheques. O que sobra do valor "
                     "é mercadoria.")
            situacao = g3.selectbox("Situação", _ch.SITUACOES)

            st.markdown(f"**Os {int(n)} cheque(s)** — folha e vencimento de cada")
            folhas, vencs = [], []
            for _i in range(int(n)):
                c1, c2 = st.columns([1, 2])
                folhas.append(c1.text_input(
                    f"Folha do {_i + 1}º", key=f"ch_folha_{_i}"))
                vencs.append(c2.date_input(
                    f"Vencimento do {_i + 1}º", value=hoje,
                    format="DD/MM/YYYY", key=f"ch_venc_{_i}"))

            obs = st.text_input("Observação (vale para todos)")
            criar = st.form_submit_button("💾 Cadastrar", type="primary",
                                          use_container_width=True)

        if criar:
            if not valor_total:
                st.error("Compra sem valor não entra — seriam linhas que "
                         "ocupam lugar e não contam nada.")
            elif envio_total > valor_total:
                st.error(
                    f"O frete ({_brl(envio_total)}) é maior que a compra "
                    f"({_brl(valor_total)}). Confira antes de cadastrar.")
            else:
                cheques_do_lote = _ch.lote(
                    {"favorecido": favorecido, "tipo": tipo, "compra": compra,
                     "situacao": situacao, "observacao": obs},
                    folhas, vencs, valor_total, envio_total)
                novas, repetidas, erro = _ch.gravar(cheques_do_lote,
                                                    usuario_logado)
                if erro:
                    st.error(f"Não consegui gravar: {erro}")
                elif not novas:
                    st.warning("Todos já estavam cadastrados — nada mudou.")
                else:
                    _v = cheques_do_lote[0]["valor"]
                    _e = cheques_do_lote[0]["envio"]
                    st.success(
                        f"{novas} cheque(s) cadastrado(s)"
                        + (f" · {repetidas} já existia(m)" if repetidas else "")
                        + f"\n\nCada um: {_brl(_v)} = frete {_brl(_e)} + "
                        f"mercadoria {_brl(round(_v - _e, 2))}")
                    # A prova de que a divisão fechou: a soma tem de ser a
                    # compra. Centavo perdido numa divisão só aparece no
                    # fechamento do mês, e lá ninguém sabe de onde veio.
                    st.dataframe(
                        pd.DataFrame([{
                            "folha": c["folha"], "vencimento": c["vencimento"],
                            "valor": c["valor"], "frete": c["envio"],
                            "mercadoria": round(c["valor"] - c["envio"], 2),
                        } for c in cheques_do_lote]),
                        use_container_width=True, hide_index=True,
                        column_config={x: st.column_config.NumberColumn(
                            format="R$ %.2f")
                            for x in ("valor", "frete", "mercadoria")})
                    st.caption(
                        "Soma dos cheques: "
                        + _brl(round(sum(c["valor"] for c in cheques_do_lote), 2))
                        + f" · compra: {_brl(valor_total)}")
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
                # Vencimento, valor e frete ABREM para edição: cheque
                # cadastrado com a data errada tem de ser corrigido aqui, e não
                # apagado e digitado de novo — apagar perde a baixa e o
                # histórico da linha.
                "vencimento": st.column_config.TextColumn(
                    width="small",
                    help="AAAA-MM-DD ou DD/MM/AAAA. O Studio entende os dois."),
                "valor": st.column_config.NumberColumn(format="R$ %.2f",
                                                       min_value=0.0),
                "envio": st.column_config.NumberColumn(format="R$ %.2f",
                                                       min_value=0.0),
                # A mercadoria continua travada: ela é conta, não campo.
                "estoque": st.column_config.NumberColumn(
                    format="R$ %.2f", disabled=True,
                    help="valor − frete, recalculado ao salvar"),
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

            # Data digitada que o Studio não entende NÃO vira data vazia: a
            # linha é recusada com o número da folha, e o resto da grade salva
            # normalmente. Gravar "" aqui tiraria o cheque do mês sem aviso.
            _venc_novo = _ch.texto_data(r["vencimento"])
            if str(r["vencimento"] or "").strip() and not _venc_novo:
                erros.append(
                    f"Cheque {a.get('folha') or '(sem folha)'}: não entendi a "
                    f"data «{r['vencimento']}» — use 02/10/2026 ou 2026-10-02.")
                continue
            if _venc_novo and _venc_novo != _ch.texto_data(a.get("vencimento")):
                campos["vencimento"] = _venc_novo

            _v_novo = round(float(r["valor"] or 0), 2)
            _e_novo = round(float(r["envio"] or 0), 2)
            _mudou_dinheiro = (_v_novo != round(_ch._num(a.get("valor")), 2)
                               or _e_novo != round(_ch._num(a.get("envio")), 2))
            if _mudou_dinheiro:
                campos["valor"] = _v_novo
                campos["envio"] = _e_novo
                # A mercadoria acompanha, sempre: ela é valor − frete, e deixá-la
                # com o número antigo faria a linha parar de fechar.
                campos["estoque"] = round(_v_novo - _e_novo, 2)

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
