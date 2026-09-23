"""fatura_ml_tela.py — a fatura do Mercado Livre conferida em uma tela.

O QUE ESTA TELA RESPONDE, NESTA ORDEM
-------------------------------------
    1. quanto saiu de verdade?      o pagamento, não o relatório
    2. o que não me cobraram?       linha a linha, com nome
    3. o que preciso conferir?      imposto, multa e devolução
    4. o que ficou em aberto?       e continua aberto no mês que vem

O DONO JÁ FAZIA ISSO À MÃO, E POR ISSO PAGOU R$ 69,60 QUE NÃO DEVIA
--------------------------------------------------------------------
A tela do ML mostra R$ 28.086,54 de tarifas em agosto. Desses, R$ 24.480,85 já
tinham sido abatidos nas vendas; R$ 3.420,90 viraram fatura; e o cartão foi
debitado em R$ 3.200,18. Três números diferentes para a mesma coisa, e nenhum
deles escrito em lugar nenhum: era isso que ele estava tentando separar
olhando 3.192 linhas.

A SALVAGUARDA É A ÚLTIMA SEÇÃO, NÃO A PRIMEIRA
-----------------------------------------------
A cobrança contestada não morre quando o mês vira. Ela fica na aba
`cobrancas_ml` até o ML devolver — e o Studio reconhece o estorno pela coluna
"Tarifa cancelada" do próprio ML, não por valor parecido. Ele tem um caso de
venda cancelada com imposto nunca estornado, aberto até hoje; com esta tela
aquele caso teria um lugar onde não some.
"""

import streamlit as st


def _brl(v):
    """Para st.metric e tabela — o cifrão cru, que ali não vira fórmula."""
    import fatura_ml as _fm
    return _fm.moeda(v)


def _md(v):
    """Para texto em markdown — cifrão escapado.

    O markdown do Streamlit lê `$...$` como LaTeX. Duas cifras no mesmo
    parágrafo e o texto entre elas some dentro de uma fórmula: foi assim que
    o alerta do ICMS-DIFAL, o aviso mais importante desta tela, saiu ilegível
    na primeira versão.
    """
    import fatura_ml as _fm
    return _fm.moeda(v, markdown=True)


def pagina(usuario_logado=None):
    import fatura_ml as _fm

    st.markdown("#### 🛒 ADS-Cross — a fatura do Mercado Livre")
    st.caption(
        "Suba o **Relatório de faturamento** e o **Relatório de pagamento de "
        "faturas** do mês. O primeiro diz o que cada tarifa é; o segundo diz "
        "o que saiu do cartão. Os dois juntos fecham a conta sozinhos."
    )

    arquivos = st.file_uploader(
        "Relatórios do ML", type=["xlsx"], accept_multiple_files=True,
        key="ml_up", label_visibility="collapsed")

    if not arquivos:
        _casos_em_aberto(_fm, usuario_logado, sep=None)
        return

    with st.spinner("Lendo os relatórios…"):
        sep, pag, avisos = _fm.ler_arquivos(
            [(a.name, a.getvalue()) for a in arquivos])
    for a in avisos:
        st.markdown(a)

    if not sep:
        st.warning(
            "Sem o **relatório de faturamento** não dá para saber o que cada "
            "tarifa é. Ele é o que tem a coluna *Descontado da operação*.")
        _casos_em_aberto(_fm, usuario_logado, sep=None)
        return

    st.markdown("---")
    _resumo(_fm, sep, pag)
    st.markdown("---")
    _conferencia(_fm, sep, pag, usuario_logado)
    st.markdown("---")
    _casos_em_aberto(_fm, usuario_logado, sep=sep)


def _resumo(_fm, sep, pag):
    """Os três números que não são o mesmo número."""
    st.markdown("##### Quanto saiu de verdade")
    c1, c2, c3 = st.columns(3)
    c1.metric("Abatido na operação", _brl(sep["total_operacao"]),
              help="Já foi descontado de cada venda. NUNCA sai do seu bolso — "
                   "somar isto como gasto multiplicaria a conta por sete.")
    c2.metric("Virou fatura", _brl(sep["total_fatura"]),
              help="O que o relatório de faturamento lança como cobrança.")
    if pag:
        c3.metric("Pago no cartão", _brl(pag["total_pago"]),
                  help="O débito de verdade. É ESTE o valor que vai para as "
                       "saídas do mês.")
    else:
        c3.metric("Pago no cartão", "—",
                  help="Suba o relatório de pagamento de faturas para saber.")

    if sep["total_nao_se_aplica"]:
        st.caption(
            f"Fora das duas contas: {_md(sep['total_nao_se_aplica'])} em "
            f"{len(sep['nao_se_aplica'])} linhas marcadas pelo ML como *Não "
            "se aplica* — pares de lançamento e cancelamento. Elas não se "
            "anulam exatamente, e por isso ficam visíveis em vez de sumirem.")

    if not pag:
        st.info("Sem o relatório de pagamento, o Studio mostra o que foi "
                "cobrado, mas não o que foi **pago** — e em ago/2026 a "
                "diferença foi de R\\$ 220,72.")
    else:
        dif, nao_cobradas = _fm.conciliar(sep, pag)
        if nao_cobradas:
            st.success(
                f"**{_md(dif)} cobrados e não pagos** — o ML abateu. "
                f"São {len(nao_cobradas)} linhas, todas listadas abaixo.")
            # Valor como TEXTO já formatado em real: a métrica logo acima
            # mostra "R$ 3.420,90" e a NumberColumn mostraria "R$ 3420.90" na
            # mesma tela. Dois formatos para o mesmo número na mesma tela é
            # como se começa a desconfiar do número.
            st.dataframe(
                [{"Data": r["data"], "Cobrança": r["detalhe"],
                  "Venda": r["venda"], "Valor": _brl(r["valor"])}
                 for r in nao_cobradas],
                hide_index=True, use_container_width=True)
        elif abs(dif) >= 0.01:
            # Diferença sem linha que a explique é o caso que merece susto:
            # significa que foi pago algo que a fatura não lista.
            st.error(
                f"Sobrou {_md(dif)} de diferença que NENHUMA linha explica. "
                "Isso não é abatimento — confira no painel do ML antes de "
                "lançar o mês.")
        else:
            st.success("Fatura e pagamento batem exatamente.")

        if pag["estornos"]:
            st.info(
                f"**{_md(pag['total_estornos'])} em estorno** "
                f"({len(pag['estornos'])} lançamentos) — o ML ainda está "
                "processando. É dinheiro voltando; confira no mês que vem se "
                "entrou.")

    st.markdown("###### O que foi cobrado, por tipo")
    tipos = _fm.por_tipo(sep["na_fatura"])
    st.dataframe(
        [{"Cobrança": k, "Valor": _brl(v)} for k, v in tipos.items()],
        hide_index=True, use_container_width=True)
    st.caption(
        "É esta a quebra que faltava: sem ela, a fatura inteira entrava nas "
        "saídas como se fosse tudo ADS.")


def _conferencia(_fm, sep, pag, usuario_logado):
    """Imposto, multa e devolução — as linhas que ninguém pode pagar no piloto."""
    st.markdown("##### O que precisa do seu olho")
    # Com o relatório de pagamento, avisa só o que SAIU da conta: o que o ML
    # não cobrou já está na tabela de não-cobradas, alguns centímetros acima.
    frases = _fm.alertas(sep, pag, so_pagas=bool(pag))
    if not frases:
        st.success("Nada de imposto, multa ou devolução saiu da sua conta "
                   "neste mês.")
    for f in frases:
        st.warning(f)
    if pag:
        nao_pagas = len(sep["conferir"]) - len(frases)
        if nao_pagas:
            st.caption(
                f"Outras {nao_pagas} cobrança(s) de devolução apareceram na "
                "fatura e não foram cobradas — estão na tabela acima.")

    repetidas = _fm.fiscais_repetidas(sep, _fm.carregar())
    for r, datas in repetidas:
        st.error(
            f"**Valor fiscal repetido: {_md(r['valor'])}** em "
            f"*{r['detalhe']}* ({r['data']}) — o mesmo nome e o mesmo centavo "
            f"já apareceram em {', '.join(datas)}. Na conta Little Glass o ML "
            "lançou R\\$ 69,60 de ICMS-DIFAL em 15/07/2026 e de novo em "
            "30/07/2026. Confira as duas guias antes de aceitar a segunda.")

    sem_venda = _fm.fiscais_sem_venda(sep)
    devolvidas = _fm.vendas_devolvidas(sep)
    if sem_venda and devolvidas:
        # Regra 5: dizer em voz alta o que o sistema NÃO consegue fazer, em
        # vez de fingir um cruzamento que os dados não permitem.
        st.error(
            f"**O cruzamento imposto × venda devolvida não é automático "
            f"neste mês.** {len(sem_venda)} cobrança(s) fiscal(is) vieram sem "
            f"Número da venda, e há {len(devolvidas)} venda(s) com devolução. "
            "Sem esse número, só dá para conferir no painel do ML — vendas: "
            + ", ".join(devolvidas))

    novos = _fm.casos_a_abrir(sep, pag)
    if not novos:
        return
    st.markdown("###### Deixar em aberto até o ML resolver")
    st.caption(
        f"{len(novos)} cobrança(s) paga(s) de natureza fiscal ou de "
        "devolução. Gravadas, elas continuam aparecendo todo mês até o "
        "estorno cair ou você marcar como aceita.")
    if st.button("Abrir os casos", type="primary", key="ml_abrir"):
        n, ja, erro = _fm.abrir(novos, usuario_logado or "")
        if erro:
            st.error(f"Não consegui gravar: {erro}")
        else:
            st.success(f"{n} aberto(s); {ja} já existia(m).")
            st.rerun()


def _casos_em_aberto(_fm, usuario_logado, sep=None):
    """A memória que atravessa o mês — o caso do dono que nunca foi estornado."""
    st.markdown("##### Cobranças em aberto")
    casos = _fm.carregar()
    abertos = _fm.em_aberto(casos)

    if sep and abertos:
        pares = _fm.estornos_encontrados(abertos, sep)
        if pares:
            st.success(
                f"O ML estornou {len(pares)} das cobranças em aberto — "
                "achado pelo número da tarifa, na coluna *Tarifa cancelada*.")
            if st.button("Dar baixa nesses estornos", key="ml_baixa"):
                n, erro = _fm.aplicar_estornos(pares, usuario_logado or "")
                if erro:
                    st.error(f"Não consegui gravar: {erro}")
                else:
                    st.success(f"{n} caso(s) fechado(s).")
                    st.rerun()

    if not abertos:
        st.caption("Nada em aberto." if casos
                   else "Nenhum caso gravado ainda.")
        return

    total = round(sum(float(c.get("valor") or 0) for c in abertos), 2)
    st.metric("Em aberto com o ML", _brl(total),
              help="Cobranças pagas que ainda precisam de resposta do ML.")

    for c in abertos:
        with st.expander(
                f"{c.get('data', '')} · {c.get('detalhe', '')} · "
                f"{_md(c.get('valor'))}"):
            st.caption(c.get("motivo", ""))
            if c.get("venda"):
                st.caption(f"Venda {c['venda']} · tarifa {c.get('numero', '')}")
            obs = st.text_input("Observação", value=c.get("observacao", ""),
                                key=f"ml_obs_{c['id']}")
            b1, b2 = st.columns(2)
            if b1.button("Aceitar a cobrança", key=f"ml_ok_{c['id']}"):
                ok, msg = _fm.encerrar(c["id"], _fm.ACEITA, obs,
                                       usuario_logado or "")
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()
            if b2.button("Marcar como estornada", key=f"ml_est_{c['id']}"):
                ok, msg = _fm.encerrar(c["id"], _fm.ESTORNADO, obs,
                                       usuario_logado or "")
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()
