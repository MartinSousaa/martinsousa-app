"""extratos_tela.py — subir o extrato, ver o que entrou, corrigir na linha.

A FORMA VEIO DO DONO
--------------------
"Acho que pode entrar, mas haver um lápis para caso eu precise excluir alguma
linha, alterar alguma finalidade ou algo do tipo."

Então não há tela de confirmação: o arquivo sobe, é classificado pelo cadastro
de favorecidos e gravado. O que estiver errado se corrige depois, na própria
linha. É menos clique e menos espera — e exige que apagar e alterar sejam tão
fáceis quanto subir, senão o atalho cobra caro na primeira vez que algo entra
torto.

O QUE ESTA TELA NÃO FAZ
-----------------------
Não decide finalidade. Quem sabe que APEXIMP é mercadoria é `favorecidos`, e é
lá que a resposta fica guardada para valer também para o passado. Aqui só se
mostra o que ficou sem classificação, para o dono responder uma vez.
"""

import streamlit as st


def _fmt(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pagina(usuario_logado=None):
    import extrato_itau as _itau
    import extrato_inter as _inter
    import favorecidos as _fv
    import lancamentos as _lan

    st.markdown("#### 💳 Extratos — subir e conferir")
    st.caption(
        "Itaú em `.xlsx`, Inter em `.csv`. O que já tem histórico entra "
        "classificado; o que é novo cai na fila para você responder uma vez. "
        "Subir o mesmo arquivo duas vezes não duplica nada."
    )

    arquivos = st.file_uploader(
        "Extrato", type=["xlsx", "csv"], accept_multiple_files=True,
        key="ext_up", label_visibility="collapsed")

    if arquivos:
        for arq in arquivos:
            _processar(arq, _itau, _inter, _fv, _lan, usuario_logado)

    st.markdown("---")
    _ver_mes(_fv, _lan, usuario_logado)


def _processar(arq, _itau, _inter, _fv, _lan, usuario_logado):
    """Lê um arquivo, classifica e grava. Cada bloco diz o que aconteceu."""
    nome = arq.name
    dados = arq.getvalue()
    with st.spinner(f"Lendo {nome}…"):
        if nome.lower().endswith(".csv"):
            lancs, cab, erro = _inter.ler(dados)
            conta = f"inter-{cab.get('conta', '?')}"
        else:
            lancs, cab, erro = _itau.ler(dados)
            conta = f"itau-{cab.get('conta', '?')}"
    if erro:
        st.error(f"**{nome}:** {erro}")
        return
    if not lancs:
        st.warning(f"**{nome}:** nenhum lançamento reconhecido no arquivo.")
        return

    # O que o PRÓPRIO extrato já resolve não pode virar pergunta.
    #
    # "CH COMPENSADO 001 000504" é cheque, "SISPAG SALARIOS" é folha,
    # "BUSINESS 6202-5907" é fatura do cartão — está na descrição, e o leitor
    # já devolve isso em `tipo`. Sem esta linha, 49 lançamentos que o sistema
    # entende sozinho caíam na fila do dono para ele responder um a um.
    for _l in lancs:
        if not _l.get("finalidade") and _l.get("tipo") in POR_TIPO:
            _l["finalidade"] = POR_TIPO[_l["tipo"]]

    classificados, fila = _fv.classificar(lancs)
    # A fila ganha o que falta para a pergunta fazer sentido: de que conta,
    # em que sentido, e com que descrição. "MARTINSOUSA · 5x · 36.272,40" não
    # dá para responder — entrada e saída do mesmo nome são coisas opostas.
    fila = _enriquecer(fila, classificados, conta)
    novos, repetidos, erro_g = _lan.gravar(classificados, conta, usuario_logado)
    if erro_g:
        st.error(f"**{nome}:** li o arquivo, mas não consegui gravar — {erro_g}")
        return

    _periodo = cab.get("periodo") or cab.get("período") or ""
    st.success(
        f"**{nome}** · {conta} · {_periodo}  \n"
        f"{novos} lançamento(s) novo(s) gravado(s)"
        + (f" · {repetidos} já estavam lá (não duplicados)" if repetidos else "")
    )

    _saida = sum(-l["valor"] for l in classificados if l["valor"] < 0)
    _entrada = sum(l["valor"] for l in classificados if l["valor"] > 0)
    c1, c2, c3 = st.columns(3)
    c1.metric("Saiu", f"R$ {_fmt(_saida)}")
    c2.metric("Entrou", f"R$ {_fmt(_entrada)}")
    c3.metric("Sem classificação", f"{len(fila)} nome(s)")

    if fila:
        st.warning("Estes nomes não têm histórico. Responda uma vez e eles "
                   "nunca mais aparecem aqui.")
        _perguntar(fila, _fv, usuario_logado)


# O tipo que o leitor do extrato já identifica, e a finalidade dele.
# Cheque, fatura e boleto são FORMA de pagamento, não finalidade — entram com
# o próprio nome e ficam no bloco "falta abrir" da Home, esperando alguém dizer
# o que aquele cheque pagou.
POR_TIPO = {
    "cheque": "CHEQUES",
    "fatura_cartao": "FATURA DO CARTÃO",
    "boleto": "BOLETO",
    "folha": "FOLHA",
    "debito_auto": "CUSTO FIXO",
    "tarifa": "TARIFA BANCÁRIA",
    "emprestimo": "NÃO OPERACIONAL",
    "aplicacao": "APLICACAO",
}


def _enriquecer(fila, classificados, conta):
    """Põe sentido, conta e exemplo de descrição em cada item da fila.

    Sem isso a pergunta não tem resposta possível: o mesmo nome entrando e
    saindo são finalidades opostas — recebido da Little Glass é repasse de
    plataforma, enviado para ela é transferência entre contas.

    Quando o nome aparece nos dois sentidos, ele vira DUAS perguntas, porque
    são duas respostas.
    """
    porta = {}
    for l in classificados:
        if l.get("classificado"):
            continue
        nome = (l.get("favorecido") or l.get("razao_social")
                or l.get("descricao") or "")
        if not nome:
            continue
        sentido = "entrada" if float(l.get("valor") or 0) > 0 else "saida"
        d = porta.setdefault((nome, sentido), {
            "favorecido": nome, "sentido": sentido, "conta": conta,
            "n": 0, "total": 0.0, "exemplo": "", "datas": []})
        d["n"] += 1
        d["total"] += abs(float(l.get("valor") or 0))
        d["exemplo"] = d["exemplo"] or str(l.get("descricao") or "")[:58]
        d["datas"].append(str(l.get("data") or ""))
    return sorted(porta.values(), key=lambda x: -x["total"])


def _perguntar(fila, _fv, usuario_logado):
    """A fila de nomes novos, do maior valor para o menor."""
    ESCOLHA = "— escolher —"
    _opcoes = [ESCOLHA] + _finalidades_conhecidas(_fv)
    SETA = {"entrada": "🟢 ENTROU", "saida": "🔴 SAIU"}
    for i, item in enumerate(fila[:15]):
        c1, c2, c3 = st.columns([3, 2, 1])
        _quando = ""
        _datas = sorted(d for d in (item.get("datas") or []) if d)
        if _datas:
            _quando = (f" · {_datas[0][8:10]}/{_datas[0][5:7]}" if len(_datas) == 1
                       else f" · {_datas[0][8:10]}/{_datas[0][5:7]} a "
                            f"{_datas[-1][8:10]}/{_datas[-1][5:7]}")
        c1.markdown(
            f"{SETA.get(item['sentido'], '')} **R$ {_fmt(item['total'])}**"
            f" · {item['n']}x{_quando}  \n"
            f"**{item['favorecido'][:46]}**  \n"
            f"<span style='font-size:11px;opacity:.65'>na conta "
            f"{item.get('conta', '')} · {item.get('exemplo', '')}</span>",
            unsafe_allow_html=True)
        _fin = c2.selectbox("Finalidade", _opcoes, key=f"ext_fin_{i}",
                            label_visibility="collapsed")
        if c3.button("Salvar", key=f"ext_sv_{i}", use_container_width=True,
                     disabled=_fin == ESCOLHA):
            _ok, _msg = _fv.salvar(item["favorecido"], _fin, item["sentido"],
                                   "", usuario_logado)
            (st.success if _ok else st.error)(_msg)


def _finalidades_conhecidas(_fv):
    """As finalidades já usadas, mais as que a casa sempre teve."""
    base = ["MERCADORIA", "EMBALAGEM", "CUSTO FIXO", "NÃO OPERACIONAL",
            "IMPOSTO", "SERVIÇO", "ESTACIONAMENTO", "FLEX", "CONSUMO INTERNO", "TRANSFERENCIA ENTRE CONTAS",
            "MERCADO LIVRE", "SHOPEE", "SHEIN", "TIKTOK", "AMAZON", "SITE", "OUTROS"]
    try:
        usadas = {v["finalidade"] for v in (_fv.carregar() or {}).values()
                  if v.get("finalidade")}
    except Exception:
        usadas = set()
    return sorted(set(base) | usadas)


def _ver_mes(_fv, _lan, usuario_logado):
    """O mês gravado, com o lápis: alterar finalidade ou apagar a linha."""
    from datetime import datetime
    import placar_core as _pc

    st.markdown("##### 📋 Lançamentos do mês")
    _hoje = datetime.now(_pc.FUSO).date()
    c1, c2 = st.columns(2)
    _ano = c1.number_input("Ano", 2020, 2100, _hoje.year, 1, key="ext_ano")
    _mes = c2.number_input("Mês", 1, 12, _hoje.month, 1, key="ext_mes")

    linhas = _lan.do_mes(_ano, _mes)
    if not linhas:
        st.info("Nenhum lançamento gravado neste mês.")
        return

    import pandas as pd
    df = pd.DataFrame([{
        "apagar": False,
        "data": l["data"],
        "descrição": l["descricao"][:60],
        "favorecido": l["favorecido"][:34],
        "valor": l["valor"],
        "finalidade": l["finalidade"],
        "id": l["id"],
    } for l in linhas])

    editado = st.data_editor(
        df, use_container_width=True, hide_index=True, key="ext_ed",
        column_config={
            "apagar": st.column_config.CheckboxColumn("🗑️", width="small"),
            "data": st.column_config.TextColumn("Data", disabled=True,
                                                width="small"),
            "descrição": st.column_config.TextColumn(disabled=True),
            "favorecido": st.column_config.TextColumn(disabled=True),
            "valor": st.column_config.NumberColumn(format="%.2f",
                                                   disabled=True),
            "finalidade": st.column_config.SelectboxColumn(
                "Finalidade", options=_finalidades_conhecidas(_fv),
                help="Muda só esta linha. Para valer sempre, altere o "
                     "favorecido na aba Finalidades."),
            "id": None,
        },
    )

    _sai = sum(-float(l["valor"]) for l in linhas if float(l["valor"]) < 0)
    st.caption(f"{len(linhas)} lançamento(s) · R$ {_fmt(_sai)} de saída")

    ca, cb = st.columns(2)
    if ca.button("💾 Salvar alterações", type="primary",
                 use_container_width=True, key="ext_salvar"):
        _mudados = 0
        _antes = {l["id"]: l["finalidade"] for l in linhas}
        for _, r in editado.iterrows():
            if str(r["finalidade"]) != _antes.get(r["id"], ""):
                _ok, _m = _lan.atualizar(r["id"],
                                         {"finalidade": str(r["finalidade"])},
                                         usuario_logado)
                _mudados += bool(_ok)
        st.success(f"{_mudados} linha(s) alterada(s).") if _mudados else \
            st.info("Nada mudou.")

    _marcados = [r["id"] for _, r in editado.iterrows() if bool(r["apagar"])]
    if cb.button(f"🗑️ Apagar marcados ({len(_marcados)})",
                 use_container_width=True, key="ext_apagar",
                 disabled=not _marcados):
        _qtd, _msg = _lan.apagar(_marcados)
        (st.success if _qtd else st.error)(_msg)

    with st.expander("💰 Quanto cada finalidade consumiu neste mês"):
        _res = _lan.resumo_por_finalidade(linhas)
        if not _res:
            st.caption("Nenhuma saída classificada neste mês.")
        else:
            st.dataframe(
                pd.DataFrame([{"finalidade": k, "total": v}
                              for k, v in _res.items()]),
                use_container_width=True, hide_index=True,
                column_config={"total": st.column_config.NumberColumn(
                    format="R$ %.2f")})
            st.caption("Transferência entre contas e aplicação ficam de fora: "
                       "não são despesa.")
