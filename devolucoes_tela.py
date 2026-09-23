"""devolucoes_tela.py — a tela de devoluções, no layout aprovado em 23/09.

QUATRO BLOCOS, NA ORDEM DA PERGUNTA
    1. em aberto        o que ainda me deve resposta — fica no topo
    2. o mês            quanto, quanto voltou do que vendi, por que
    3. nova devolução    digita o pedido, o resto vem da BASE DE VENDAS
    4. o mês, editável   tudo que foi preenchido à mão se corrige aqui

A LISTA DE ITENS É O CORAÇÃO DO CADASTRO
Uma venda com dois produtos gera UMA devolução. Por isso o pedido abre a lista
dos itens com uma caixa para marcar, e Produto, SKU, Quantidade e Valor são a
soma do que ficou marcado. Uma linha por produto era o que a planilha fazia, e
foi o que fez o dono escrever "MEIÃO" para dois meiões.

O QUE ESTA TELA NÃO FAZ
Não zera valor por causa da situação. RECORRIDO quer dizer que a plataforma
reembolsou — às vezes parcialmente —, e quem apaga o valor é ele. Automatizar
isso acertaria na maioria e erraria calado no resto.
"""

from datetime import date, datetime

import streamlit as st


def _brl(v):
    return "R$ " + f"{float(v or 0):,.2f}".replace(",", "X").replace(
        ".", ",").replace("X", ".")


def _md(v):
    """Cifrão escapado — o markdown do Streamlit lê `$…$` como LaTeX."""
    return _brl(v).replace("R$", "R\\$")


MESES_PT = ("janeiro", "fevereiro", "março", "abril", "maio", "junho",
            "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")


def _rotulo_mes(m):
    try:
        return f"{MESES_PT[int(m[5:7]) - 1]}/{m[:4]}"
    except Exception:
        return m


def pagina(usuario_logado=None):
    import devolucoes as _dv

    st.markdown("#### 🔄 Devoluções")
    st.caption(
        "O preenchimento passa a ser aqui. A planilha vira histórico — o "
        "Studio a lê uma vez para montar os meses anteriores.")

    linhas = _dv.carregar()

    _em_aberto(_dv, linhas, usuario_logado)
    st.markdown("---")

    if not linhas:
        _importar(_dv, usuario_logado)
        st.markdown("---")
        _nova(_dv, usuario_logado)
        return

    mes = _o_mes(_dv, linhas)
    st.markdown("---")
    _nova(_dv, usuario_logado)
    st.markdown("---")
    _tabela(_dv, linhas, mes, usuario_logado)
    with st.expander("⤵️ Importar o histórico do Controle MS"):
        _importar(_dv, usuario_logado)


# ── 1. Em aberto ────────────────────────────────────────────────────────────

def _em_aberto(_dv, linhas, usuario_logado):
    abertos = _dv.em_aberto(linhas)
    st.markdown("##### ⚠️ Em aberto")
    if not abertos:
        st.caption("Nada em aberto." if linhas else
                   "Nenhuma devolução cadastrada ainda.")
        return
    st.caption(
        "Fica aqui até alguém marcar ✅ **Resolvido**. Não some quando o mês "
        "vira — foi por sumir que um caso ficou dois meses sem cobrança.")
    total = round(sum(_dv.num(a.get("valor")) for a in abertos), 2)
    st.metric("Em aberto", _brl(total), help=f"{len(abertos)} devolução(ões).")

    for a in abertos:
        c1, c2 = st.columns([6, 1])
        with c1:
            venda = f" · venda {a['pedido']}" if a.get("pedido") else ""
            st.markdown(
                f"**{_dv.data_br(a.get('data_solic'))}** · {a.get('produto')} "
                f"· {_md(a.get('valor'))} · *{a.get('situacao')}*{venda}")
            novo = st.text_input(
                "Status", value=a.get("status", ""), key=f"dv_st_{a['id']}",
                label_visibility="collapsed",
                placeholder="ex.: Recorrer — aguardando resposta da plataforma")
            if novo != a.get("status", ""):
                ok, msg = _dv.atualizar(a["id"], {"status": novo},
                                        usuario_logado or "")
                if not ok:
                    st.error(msg)
        with c2:
            if st.button("✅ Resolvido", key=f"dv_ok_{a['id']}",
                         use_container_width=True):
                ok, msg = _dv.atualizar(a["id"], {"resolvido": "TRUE"},
                                        usuario_logado or "")
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()


# ── 2. O mês ────────────────────────────────────────────────────────────────

def _o_mes(_dv, linhas):
    meses = _dv.meses(linhas)
    c1, _ = st.columns([1, 3])
    mes = c1.selectbox("Mês", meses, format_func=_rotulo_mes, key="dv_mes")
    doMes = _dv.do_mes(linhas, mes)
    r = _dv.resumo(doMes)

    m = st.columns(5)
    m[0].metric("Devoluções", r["n"])
    m[1].metric("Valor devolvido", _brl(r["valor"]))
    m[2].metric("Frete pago", _brl(r["frete"]),
                help="Frete só aparece quando a devolução foi culpa nossa — "
                     "produto errado, cor errada, defeito, quebrado.")
    m[3].metric("Tícket médio", _brl(r["ticket_medio"]),
                help="(valor das vendas + frete) ÷ quantidade de devoluções.")
    m[4].metric("Culpa nossa", f"{r['culpa_nossa']} de {r['n']}",
                help="Medido pelo frete: com valor = culpa nossa; sem = não foi.")

    if r["sem_nf"]:
        st.warning(
            f"**{len(r['sem_nf'])} devolução(ões) sem NF de devolução.** Sem "
            "cancelar a NF de venda ou emitir a de devolução, paga-se imposto "
            "sobre produto que voltou. Pedidos: "
            + ", ".join(x.get("pedido", "—") for x in r["sem_nf"][:6])
            + ("…" if len(r["sem_nf"]) > 6 else ""))

    _quanto_voltou(_dv, linhas, mes)
    _motivos(_dv, doMes, linhas, mes)
    return mes


def _quanto_voltou(_dv, linhas, mes):
    """A % sobre o faturado, do mês e do ano — a conta que o dono pediu."""
    st.markdown("##### Quanto do que vendi virou devolução")
    try:
        import base_vendas as _bv
        mapa, erro = _bv.somas_por_mes()
    except Exception as e:
        mapa, erro = {}, str(e)[:120]
    if erro or not mapa:
        st.caption("Sem a BASE DE VENDAS não dá para saber o faturado do mês, "
                   "e sem ele não há percentual." + (f" ({erro})" if erro else ""))
        return

    def faturado(chave):
        return (mapa.get(chave) or {}).get("faturamento", 0.0)

    ano, m = int(mes[:4]), int(mes[5:7])
    por_venda = _dv.por_mes_da_venda(linhas)
    fat_mes = faturado((ano, m))
    dev_mes = por_venda.get(mes, 0.0)
    fat_ano = sum(v.get("faturamento", 0.0) for k, v in mapa.items()
                  if k[0] == ano)
    dev_ano = sum(v for k, v in por_venda.items() if k[:4] == str(ano))

    g = st.columns(4)
    g[0].metric("Faturado no mês", _brl(fat_mes))
    g[1].metric("Voltou desse faturamento", _brl(dev_mes),
                help="Devoluções das vendas DESTE mês — é por isso que a data "
                     "da venda vem preenchida automaticamente.")
    p_mes = _dv.pct_do_faturado(dev_mes, fat_mes)
    p_ano = _dv.pct_do_faturado(dev_ano, fat_ano)
    g[2].metric("% do mês", "—" if p_mes is None
                else f"{p_mes:.2f}%".replace(".", ","))
    g[3].metric(f"% no ano ({ano})", "—" if p_ano is None
                else f"{p_ano:.2f}%".replace(".", ","),
                help=f"Proporcional ao já faturado: {_brl(dev_ano)} de "
                     f"{_brl(fat_ano)}. O ano não está fechado — é acumulado, "
                     "não projeção.")
    st.caption(
        "A conta é **devoluções ÷ faturado**, sem somar as devoluções de "
        "volta: na BASE DE VENDAS a coluna FAT TOTAL **já inclui** a venda "
        "devolvida. Somar de novo contaria a mesma venda duas vezes.")


def _motivos(_dv, doMes, linhas, mes):
    st.markdown("##### Top 5 motivos")
    t1, t2 = st.columns(2)
    with t1:
        st.markdown(f"**No mês ({_rotulo_mes(mes)})**")
        st.dataframe(
            [{"Motivo": m, "Qtd": n, "Valor": _brl(v),
              "% do mês": f"{p:.1f}%".replace(".", ",")}
             for m, n, v, p in _dv.top_motivos(doMes)],
            hide_index=True, use_container_width=True)
    with t2:
        st.markdown("**No período todo**")
        st.dataframe(
            [{"Motivo": m, "Qtd": n, "Valor": _brl(v),
              "% do período": f"{p:.1f}%".replace(".", ",")}
             for m, n, v, p in _dv.top_motivos(linhas)],
            hide_index=True, use_container_width=True)
    st.caption(
        "Motivo que **não custa frete** não é falha nossa — é o canal. O que "
        "custa é produto danificado e produto errado, e esses apontam para "
        "embalagem e separação, não para o cliente.")


# ── 3. Nova devolução ───────────────────────────────────────────────────────

def _itens_do_pedido(pedido):
    """Os itens do pedido na BASE DE VENDAS. ([], "") quando não acha."""
    if not str(pedido or "").strip():
        return [], ""
    try:
        import controle_ms as _cms
        import devolucoes as _dv
        df, erro = _cms.ler(_dv.ABA_VENDAS)
        if erro:
            return [], erro
        cp = _dv._coluna(df, "Pedido")
        if not cp:
            return [], "A BASE DE VENDAS não tem coluna «Pedido»."
        cols = {k: _dv._coluna(df, v) for k, v in
                (("produto", "Produto"), ("sku", "SKU"),
                 ("quantidade", "Quantidade"),
                 ("valor", "Total dos Produtos"), ("data", "Data"),
                 ("plataforma", "Plataforma"))}
        alvo = str(pedido).strip()
        fora = []
        for _, l in df.iterrows():
            if str(l.get(cp, "") or "").strip() == alvo:
                fora.append({k: (l.get(c) if c else "") for k, c in cols.items()})
        return fora, ""
    except Exception as e:
        return [], str(e)[:140]


def _nova(_dv, usuario_logado):
    st.markdown("##### Nova devolução")
    p1, p2 = st.columns([2, 5])
    pedido = p1.text_input("Nº do pedido", key="dv_ped")
    itens, erro_it = ([], "")
    if pedido:
        with st.spinner("Procurando na BASE DE VENDAS…"):
            itens, erro_it = _itens_do_pedido(pedido)

    marcados = None
    if itens and len(itens) > 1:
        p2.markdown("&nbsp;", unsafe_allow_html=True)
        p2.success(f"✅ Achei — este pedido tem **{len(itens)} produtos**. "
                   "Marque o que voltou; uma devolução só, com os valores "
                   "somados.")
        editado = st.data_editor(
            [{"↩️ Voltou": True, "SKU": str(i.get("sku", "")),
              "Produto": str(i.get("produto", "")),
              "Qtd": int(_dv.num(i.get("quantidade"), 1)),
              "Valor": _brl(i.get("valor"))} for i in itens],
            hide_index=True, use_container_width=True, key="dv_itens",
            disabled=["SKU", "Produto", "Qtd", "Valor"],
            column_config={
                "↩️ Voltou": st.column_config.CheckboxColumn(width="small"),
                "SKU": st.column_config.TextColumn(width="small"),
                "Qtd": st.column_config.NumberColumn(width="small")})
        marcados = [i for i, l in enumerate(editado) if l.get("↩️ Voltou")]
    elif itens:
        p2.markdown("&nbsp;", unsafe_allow_html=True)
        p2.success("✅ Achei na **BASE DE VENDAS** — preenchi os campos cinzas.")
    elif pedido:
        p2.markdown("&nbsp;", unsafe_allow_html=True)
        p2.warning(
            "Não achei este pedido na BASE DE VENDAS. Tudo abre para "
            "digitação." + (f" ({erro_it})" if erro_it else ""))

    auto = _dv.juntar(itens, marcados) if itens else {}
    achou = bool(itens)

    a = st.columns(4)
    a[0].text_input("Data da venda", _dv.data_br(auto.get("data_venda")),
                    disabled=achou, key="dv_dvenda")
    a[1].text_input("Produto *", auto.get("produto", ""), disabled=achou,
                    key="dv_prod")
    # Quando o valor vem da planilha ele e so para CONFERIR, e conferir se le
    # em real: `number_input` escreve 145.33, com ponto, ao lado de um
    # "R$ 145,33" tres linhas acima. Dois formatos do mesmo numero na mesma
    # tela e como se comeca a desconfiar do numero.
    if achou:
        a[2].text_input("Quantidade", str(auto.get("quantidade", 0)),
                        disabled=True, key="dv_qtd_txt")
        a[3].text_input("Valor", _brl(auto.get("valor")), disabled=True,
                        key="dv_valor_txt")
    else:
        a[2].number_input("Quantidade", value=1, step=1, key="dv_qtd")
        a[3].number_input("Valor", value=0.0, step=0.01, key="dv_valor")
    b = st.columns([1, 3])
    b[0].text_input("Conta", auto.get("conta", ""), disabled=achou,
                    key="dv_conta")
    b[1].text_input("SKU", auto.get("sku", ""), key="dv_sku",
                    help="Vem dos itens marcados e continua aberto para você "
                         "corrigir ou digitar.")
    if achou:
        st.caption("Cinza = veio da planilha de vendas, somando **só os itens "
                   "marcados**. O **SKU fica editável**.")

    c = st.columns(4)
    c[0].date_input("Data solicitação *", value=date.today(),
                    format="DD/MM/YYYY", key="dv_solic")
    c[1].selectbox("Envios *", _dv.ENVIOS, key="dv_envios")
    c[2].text_input("Usuário", key="dv_usuario")
    c[3].text_input("Nome", key="dv_nome")

    d = st.columns(4)
    d[0].selectbox("Motivo *", _dv.MOTIVOS, key="dv_motivo")
    d[1].number_input("Frete", value=0.0, step=0.01, key="dv_frete",
                      help="Só preencha quando a devolução foi culpa nossa. "
                           "É o frete que diz isso na hora de medir.")
    d[2].date_input("Conferência *", value=date.today(), format="DD/MM/YYYY",
                    key="dv_conf")
    d[3].selectbox("Situação *", _dv.SITUACOES, key="dv_situacao")

    e = st.columns([1, 3])
    e[0].text_input("NF devolução", key="dv_nf",
                    help="Número da NF de devolução ou do cancelamento — é o "
                         "que evita pagar imposto de produto que voltou.")
    e[1].text_input("Status (texto livre)", key="dv_status",
                    placeholder="ex.: Recorrer, aguardando a plataforma…")
    st.caption(
        "`*` = obrigatório. Todo o resto pode ficar em branco e não trava o "
        "cadastro. **RECORRIDO não zera valor nenhum sozinho** — o reembolso "
        "às vezes é parcial, e quem apaga o valor é você.")

    if st.button("Gravar devolução", type="primary", key="dv_gravar"):
        reg = {
            "data_venda": auto.get("data_venda", ""),
            "data_solic": st.session_state["dv_solic"],
            "pedido": pedido, "sku": st.session_state["dv_sku"],
            "produto": auto.get("produto") or st.session_state.get("dv_prod", ""),
            "quantidade": (auto.get("quantidade")
                           or st.session_state.get("dv_qtd", 1)),
            "valor": auto.get("valor") or st.session_state.get("dv_valor", 0.0),
            "conta": auto.get("conta") or st.session_state.get("dv_conta", ""),
            "envios": st.session_state["dv_envios"],
            "usuario": st.session_state["dv_usuario"],
            "nome": st.session_state["dv_nome"],
            "motivo": st.session_state["dv_motivo"],
            "frete": st.session_state["dv_frete"],
            "conferencia": st.session_state["dv_conf"],
            "situacao": st.session_state["dv_situacao"],
            "nf_devolucao": st.session_state["dv_nf"],
            "status": st.session_state["dv_status"],
        }
        falta = _dv.faltando(_dv.normalizar(reg))
        if falta:
            st.error("Falta preencher: **" + "**, **".join(falta) + "**.")
        else:
            n, rep, erro = _dv.gravar([reg], usuario_logado or "")
            if erro:
                st.error(f"Não consegui gravar: {erro}")
            elif rep:
                st.warning("Esta devolução já estava cadastrada.")
            else:
                st.success("Gravada.")
                st.rerun()


# ── 4. O mês, editável ──────────────────────────────────────────────────────

CAMPOS_TABELA = ("data_solic", "pedido", "envios", "usuario", "nome", "sku",
                 "produto", "quantidade", "valor", "frete", "motivo", "conta",
                 "conferencia", "situacao", "nf_devolucao", "status")

TITULOS = {"data_solic": "Data solic.", "pedido": "Pedido", "envios": "Envios",
           "usuario": "Usuário", "nome": "Nome", "sku": "SKU",
           "produto": "Produto", "quantidade": "Qtd", "valor": "Valor",
           "frete": "Frete", "motivo": "Motivo", "conta": "Conta",
           "conferencia": "Conferência", "situacao": "Situação",
           "nf_devolucao": "NF dev.", "status": "Status"}


def _tabela(_dv, linhas, mes, usuario_logado):
    doMes = _dv.do_mes(linhas, mes)
    st.markdown(f"##### As devoluções de {_rotulo_mes(mes)} — tudo editável")
    # As datas sao GRAVADAS em AAAA-MM-DD (ordena sozinho) e LIDAS em
    # dd/mm/aaaa. `texto_data` reconhece as duas na volta, entao editar no
    # formato daqui nao quebra nada.
    DATAS = ("data_solic", "conferencia")
    antes = [{TITULOS[c]: (_dv.data_br(l.get(c)) if c in DATAS
                           else l.get(c, ""))
              for c in CAMPOS_TABELA} for l in doMes]
    for i, l in enumerate(antes):
        l["Apagar"] = False
    editado = st.data_editor(
        antes, hide_index=True, use_container_width=True, key=f"dv_tb_{mes}",
        column_config={
            "Apagar": st.column_config.CheckboxColumn(width="small"),
            "Valor": st.column_config.NumberColumn(format="R$ %.2f"),
            "Frete": st.column_config.NumberColumn(format="R$ %.2f"),
            "Situação": st.column_config.SelectboxColumn(
                options=list(_dv.SITUACOES)),
            "Motivo": st.column_config.SelectboxColumn(
                options=list(_dv.MOTIVOS)),
            "Envios": st.column_config.SelectboxColumn(
                options=list(_dv.ENVIOS))})

    if not st.button("Salvar as alterações", key=f"dv_salvar_{mes}"):
        st.caption("Alterou alguma célula? Clique em **Salvar as alterações**. "
                   "Marcar *Apagar* remove a linha ao salvar.")
        return

    apagar, mudados = [], 0
    for orig, novo in zip(doMes, editado):
        if novo.get("Apagar"):
            apagar.append(orig["id"])
            continue
        campos = {}
        for c in CAMPOS_TABELA:
            atual = novo.get(TITULOS[c])
            antigo = (_dv.data_br(orig.get(c)) if c in DATAS
                      else orig.get(c, ""))
            if str(atual if atual is not None else "") != str(antigo or ""):
                campos[c] = (_dv.texto_data(atual) if c in DATAS else atual)
        if campos:
            ok, msg = _dv.atualizar(orig["id"], campos, usuario_logado or "")
            if ok:
                mudados += 1
            else:
                st.error(msg)
    if apagar:
        q, erro = _dv.apagar(apagar)
        if erro:
            st.error(erro)
        else:
            st.success(f"{q} apagada(s).")
    if mudados:
        st.success(f"{mudados} alterada(s).")
    if mudados or apagar:
        st.rerun()
    else:
        st.info("Nada mudou.")


# ── Importação do histórico ─────────────────────────────────────────────────

def _importar(_dv, usuario_logado):
    st.markdown("##### Importar o histórico do Controle MS")
    st.caption(
        "Roda uma vez. Reimportar não duplica — a identidade sai de data + "
        "pedido + produto + valor. Os pedidos de mais de um item são "
        "reconstruídos **pelo valor**; os ambíguos entram marcados, em aberto.")
    if not st.button("Importar", key="dv_importar"):
        return
    with st.spinner("Lendo o Controle MS…"):
        novas, avisos = _dv.do_controle_ms()
    for a in avisos:
        st.warning(a) if a.startswith("⚠️") else st.caption(f"· {a}")
    if not novas:
        st.error("Não achei devolução nenhuma para importar.")
        return
    with st.spinner(f"Gravando {len(novas)}…"):
        n, rep, erro = _dv.gravar(novas, usuario_logado or "")
    if erro:
        st.error(f"Não consegui gravar: {erro}")
    else:
        st.success(f"{n} importada(s); {rep} já existia(m).")
        st.rerun()
