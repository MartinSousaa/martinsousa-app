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
    # A planilha é a dona (dono, 09/10): o Studio lê a aba DEVOLUÇÕES 2026 do
    # Controle MS e guarda só o acompanhamento — Status e ✅ Resolvido.
    linhas, so_no_studio, avisos = _dv.carregar_tudo()
    for a in avisos:
        st.warning(a) if (a.startswith("⚠️") or "Não consegui" in a
                          or "Mostrando" in a) else st.caption(f"· {a}")

    _em_aberto(_dv, linhas, usuario_logado)
    st.markdown("---")
    if not linhas:
        st.info("Nenhuma devolução na aba DEVOLUÇÕES 2026 do Controle MS.")
        return
    mes = _o_mes(_dv, linhas)
    st.markdown("---")
    _tabela(_dv, linhas, mes)
    if so_no_studio:
        with st.expander(f"🔎 {len(so_no_studio)} devolução(ões) só no Studio "
                         "— não estão na planilha e ficam fora da conta"):
            st.dataframe(
                [{TITULOS[c]: (_dv.data_br(l.get(c)) if c in ("data_solic",
                                                              "conferencia")
                               else l.get(c, ""))
                  for c in CAMPOS_TABELA} for l in so_no_studio],
                hide_index=True, use_container_width=True)


# ── 1. Em aberto ────────────────────────────────────────────────────────────

def _em_aberto(_dv, linhas, usuario_logado):
    abertos = _dv.em_aberto(linhas)
    st.markdown("##### ⚠️ Em aberto")
    if not abertos:
        st.caption("Nada em aberto." if linhas else
                   "Nenhuma devolução cadastrada ainda.")
        return
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
                ok, msg = _dv.acompanhar(a, {"status": novo},
                                         usuario_logado or "")
                if not ok:
                    st.error(msg)
        with c2:
            if st.button("✅ Resolvido", key=f"dv_ok_{a['id']}",
                         use_container_width=True):
                ok, msg = _dv.acompanhar(a, {"resolvido": "TRUE"},
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


# ── 3. O mês, como está na planilha ──────────────────────────────────────────────────────

CAMPOS_TABELA = ("data_solic", "pedido", "envios", "usuario", "nome", "sku",
                 "produto", "quantidade", "valor", "frete", "motivo", "conta",
                 "conferencia", "situacao", "nf_devolucao", "status")

TITULOS = {"data_solic": "Data solic.", "pedido": "Pedido", "envios": "Envios",
           "usuario": "Usuário", "nome": "Nome", "sku": "SKU",
           "produto": "Produto", "quantidade": "Qtd", "valor": "Valor",
           "frete": "Frete", "motivo": "Motivo", "conta": "Conta",
           "conferencia": "Conferência", "situacao": "Situação",
           "nf_devolucao": "NF dev.", "status": "Status"}


def _tabela(_dv, linhas, mes):
    """As devoluções do mês, só para ler: quem edita é a planilha."""
    doMes = _dv.do_mes(linhas, mes)
    st.markdown(f"##### As devoluções de {_rotulo_mes(mes)}")
    DATAS = ("data_solic", "conferencia")
    st.dataframe(
        [{TITULOS[c]: (_dv.data_br(l.get(c)) if c in DATAS else l.get(c, ""))
          for c in CAMPOS_TABELA} for l in doMes],
        hide_index=True, use_container_width=True,
        column_config={
            "Valor": st.column_config.NumberColumn(format="R$ %.2f"),
            "Frete": st.column_config.NumberColumn(format="R$ %.2f")})


