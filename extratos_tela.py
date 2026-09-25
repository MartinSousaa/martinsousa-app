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

import rotulos as _rot


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
        # A FILA E DE TODOS OS ARQUIVOS, E A PERGUNTA E UMA SO.
        #
        # `_processar` perguntava dentro de si, uma vez por arquivo, e a
        # chave do widget era `ext_fin_{i}` com `i` recomeçando do zero a
        # cada arquivo. Dois extratos com nome novo derrubavam a tela:
        # "StreamlitDuplicateElementKey: ext_fin_0".
        #
        # Juntar também conserta o que a chave só denunciava: o mesmo
        # favorecido em dois extratos virava DUAS perguntas, e a resposta é
        # gravada por nome e sentido (`favorecidos.salvar`) — ou seja, a
        # segunda pergunta nunca teve resposta própria.
        fila_total = []
        for arq in arquivos:
            fila_total += _processar(
                arq, _itau, _inter, _fv, _lan, usuario_logado) or []
        fila_total = juntar_filas(fila_total)
        if fila_total:
            st.warning("Estes nomes não têm histórico. Responda uma vez e "
                       "eles nunca mais aparecem aqui.")
            _perguntar(fila_total, _fv, usuario_logado)

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
        return []
    if not lancs:
        st.warning(f"**{nome}:** nenhum lançamento reconhecido no arquivo.")
        return []

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
        return []

    _periodo = cab.get("periodo") or cab.get("período") or ""
    st.success(
        f"**{nome}** · {conta} · {_periodo}  \n"
        f"{novos} lançamento(s) novo(s) gravado(s)"
        + (f" · {repetidos} já estavam lá (não duplicados)" if repetidos else "")
    )

    # ── A BAIXA DOS CHEQUES, AQUI, JUNTO COM O RESTO ─────────────────────
    #
    # O débito do cheque já estava no extrato e ninguém ligava os dois. Pior: a
    # tela dos cheques AFIRMAVA que ligava, e quem lia aquilo deixava de dar
    # baixa esperando que o Studio desse — o cheque ficava em aberto para
    # sempre, inflando o comprometido do mês.
    #
    # É o mesmo momento em que o extrato já ensina a finalidade de cada linha:
    # o arquivo acabou de chegar, e é aqui que ele tem o que dizer.
    #
    # SÓ O CASAMENTO EXATO É APLICADO SOZINHO. O de data próxima é mostrado
    # para conferência: dois cheques de R$ 1.500 na mesma semana casariam com
    # a saída errada, e baixar o cheque errado tira do comprometido do mês um
    # valor que ainda vai sair — erro que se disfarça de conferência feita.
    try:
        import cheques as _chq
        _cert, _duv = _chq.baixas_pelo_extrato(_chq.carregar(), classificados)
        if _cert:
            _feitas, _erros_baixa = _chq.aplicar_baixas(_cert, usuario_logado)
            if _feitas:
                st.success(
                    f"🧾 **{_feitas} cheque(s) baixado(s) pelo extrato** — "
                    + ", ".join(
                        f"folha {b['cheque'].get('folha') or '—'} "
                        f"({_rot.tela('R$ ' + _fmt(_chq._num(b['cheque'].get('valor'))))})"
                        for b in _cert[:8])
                    + ("…" if len(_cert) > 8 else ""))
            for _e in _erros_baixa:
                st.warning(_e)
        if _duv:
            with st.expander(
                    f"🧾 {len(_duv)} cheque(s) podem ter sido debitados — "
                    "confira antes"):
                st.caption(
                    "O valor bate, mas a data do extrato não é a do "
                    "vencimento. Não dei baixa: se houver dois cheques do "
                    "mesmo valor na semana, a baixa iria no errado. Confirme "
                    "na aba Cheques.")
                import pandas as _pd_baixa
                st.dataframe(
                    _pd_baixa.DataFrame([{
                        "folha": b["cheque"].get("folha", ""),
                        "vencimento": _chq.data_br(b["cheque"].get("vencimento")),
                        "valor": _chq._num(b["cheque"].get("valor")),
                        "saiu em": _chq.data_br(b["lancamento"].get("data")),
                        "dias": b["dias"],
                    } for b in _duv]),
                    use_container_width=True, hide_index=True,
                    column_config=_rot.config(
                        ["folha", "vencimento", "valor", "saiu em", "dias"],
                        st, tipos={"valor": "brl"}))
    except Exception as _e_baixa:
        # A baixa nunca pode impedir a importação do extrato: o extrato é o
        # dado, a baixa é a conveniência.
        st.caption(f"Não consegui conferir os cheques deste extrato: "
                   f"{type(_e_baixa).__name__}")

    _saida = sum(-l["valor"] for l in classificados if l["valor"] < 0)
    _entrada = sum(l["valor"] for l in classificados if l["valor"] > 0)
    c1, c2, c3 = st.columns(3)
    c1.metric("Saiu", f"R$ {_fmt(_saida)}")
    c2.metric("Entrou", f"R$ {_fmt(_entrada)}")
    c3.metric("Sem classificação", f"{len(fila)} nome(s)")
    # A pergunta não é feita aqui: ela é feita UMA vez, com a fila de todos
    # os arquivos juntos. Ver `pagina`.
    return fila


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


def juntar_filas(filas):
    """As filas de vários extratos viram UMA, sem nome repetido. Pura.

    A RESPOSTA É POR NOME E SENTIDO — não por arquivo.
    `favorecidos.salvar(favorecido, finalidade, sentido, ...)` guarda assim,
    e vale para o passado inteiro. Então o mesmo APEXIMP saindo em dois
    extratos é UMA pergunta: responder a primeira já responde a segunda, e a
    segunda ficava na tela sem ter o que gravar.

    Entrada e saída continuam separadas de propósito: recebido da Little
    Glass é repasse de plataforma, enviado para ela é transferência entre
    contas. Mesmo nome, respostas opostas.

    Soma `n` e `total`, junta as datas e guarda as contas em que o nome
    apareceu — a pergunta fica com o quadro completo, não com o do primeiro
    arquivo que chegou.
    """
    junto = {}
    for item in (filas or []):
        chave = ((item.get("favorecido") or "").strip().upper(),
                 item.get("sentido") or "saida")
        d = junto.get(chave)
        if d is None:
            junto[chave] = dict(item, datas=list(item.get("datas") or []))
            continue
        d["n"] = (d.get("n") or 0) + (item.get("n") or 0)
        d["total"] = (d.get("total") or 0.0) + (item.get("total") or 0.0)
        d["datas"] = list(d.get("datas") or []) + list(item.get("datas") or [])
        d["exemplo"] = d.get("exemplo") or item.get("exemplo") or ""
        _c1, _c2 = str(d.get("conta") or ""), str(item.get("conta") or "")
        if _c2 and _c2 not in _c1:
            d["conta"] = f"{_c1} e {_c2}" if _c1 else _c2
    return sorted(junto.values(), key=lambda x: -(x.get("total") or 0.0))


def chave_do_item(item):
    """A chave do widget: identidade do item, não posição na lista.

    `ext_fin_{i}` era única dentro de UM arquivo e repetia entre arquivos —
    foi o que derrubou a tela. Identidade não repete, e ainda sobrevive a
    reordenar a fila sem trocar a resposta de lugar.
    """
    bruto = (f"{(item.get('favorecido') or '')}|{item.get('sentido') or ''}")
    return "".join(c if c.isalnum() else "_" for c in bruto.upper())[:60]


def _perguntar(fila, _fv, usuario_logado):
    """A fila de nomes novos, do maior valor para o menor."""
    ESCOLHA = "— escolher —"
    _opcoes = [ESCOLHA] + _finalidades_conhecidas(_fv)
    SETA = {"entrada": "🟢 ENTROU", "saida": "🔴 SAIU"}
    vistas = set()
    for item in fila[:15]:
        _k = chave_do_item(item)
        if _k in vistas:        # cinto e suspensório: chave nunca repete
            continue
        vistas.add(_k)
        c1, c2, c3 = st.columns([3, 2, 1])
        _quando = ""
        _datas = sorted(d for d in (item.get("datas") or []) if d)
        if _datas:
            _quando = (f" · {_datas[0][8:10]}/{_datas[0][5:7]}" if len(_datas) == 1
                       else f" · {_datas[0][8:10]}/{_datas[0][5:7]} a "
                            f"{_datas[-1][8:10]}/{_datas[-1][5:7]}")
        c1.markdown(_rot.tela(
            f"{SETA.get(item['sentido'], '')} **R$ {_fmt(item['total'])}**"
            f" · {item['n']}x{_quando}  \n"
            f"**{item['favorecido'][:46]}**  \n"
            f"<span style='font-size:11px;opacity:.65'>na conta "
            f"{item.get('conta', '')} · {item.get('exemplo', '')}</span>"),
            unsafe_allow_html=True)
        _fin = c2.selectbox("Finalidade", _opcoes, key=f"ext_fin_{_k}",
                            label_visibility="collapsed")
        if c3.button("Salvar", key=f"ext_sv_{_k}", use_container_width=True,
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
        column_config={**_rot.config(["data", "descricao", "descrição", "favorecido", "valor", "tipo", "finalidade", "conta", "observacao", "apagar", "forma", "total", "sentido", "exemplo", "datas"], st), 
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
    st.caption(_rot.tela(
        f"{len(linhas)} lançamento(s) · R$ {_fmt(_sai)} de saída"))

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
                column_config={**_rot.config(["data", "descricao", "descrição", "favorecido", "valor", "tipo", "finalidade", "conta", "observacao", "apagar", "forma", "total", "sentido", "exemplo", "datas"], st), "total": st.column_config.NumberColumn(
                    format="R$ %.2f")})
            st.caption("Transferência entre contas e aplicação ficam de fora: "
                       "não são despesa.")


# ── Conferência ──────────────────────────────────────────────────────────────
# `python3 extratos_tela.py`. Só o que é função pura — o resto é tela.
if __name__ == "__main__":
    import ast as _ast
    import inspect as _insp

    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # ── DOIS EXTRATOS COM NOME NOVO DERRUBAVAM A TELA ───────────────────
    #
    # "StreamlitDuplicateElementKey: ext_fin_0", em producao, 25/09. A chave
    # era `ext_fin_{i}` com `i` recomecando do zero a cada arquivo, e
    # `_processar` perguntava dentro de si, uma vez por arquivo.
    _f1 = [{"favorecido": "APEXIMP", "sentido": "saida", "conta": "itau-1",
            "n": 2, "total": 300.0, "exemplo": "Pix", "datas": ["2026-09-02"]}]
    _f2 = [{"favorecido": "APEXIMP", "sentido": "saida", "conta": "itau-2",
            "n": 1, "total": 100.0, "exemplo": "", "datas": ["2026-09-05"]},
           {"favorecido": "IOF", "sentido": "saida", "conta": "itau-2",
            "n": 1, "total": 10.61, "exemplo": "IOF", "datas": ["2026-09-02"]}]
    _junta = juntar_filas(_f1 + _f2)
    ok("o mesmo nome em dois extratos vira UMA pergunta", len(_junta) == 2)
    _apex = next(x for x in _junta if x["favorecido"] == "APEXIMP")
    ok("somando as vezes", _apex["n"] == 3)
    ok("e os valores", abs(_apex["total"] - 400.0) < 0.001)
    ok("guardando as duas contas",
       "itau-1" in _apex["conta"] and "itau-2" in _apex["conta"])
    ok("e as datas dos dois arquivos", len(_apex["datas"]) == 2)
    ok("a maior fica em cima", _junta[0]["favorecido"] == "APEXIMP")

    # ENTRADA E SAIDA SAO PERGUNTAS DIFERENTES: recebido da Little Glass e
    # repasse de plataforma, enviado para ela e transferencia entre contas.
    _dois = juntar_filas([
        {"favorecido": "LITTLE GLASS", "sentido": "saida", "n": 1, "total": 5.0},
        {"favorecido": "LITTLE GLASS", "sentido": "entrada", "n": 1, "total": 9.0}])
    ok("mesmo nome em sentidos opostos continua sendo duas perguntas",
       len(_dois) == 2)

    ok("fila vazia não quebra", juntar_filas([]) == [] and juntar_filas(None) == [])

    # ── A CHAVE DO WIDGET E IDENTIDADE, NAO POSICAO ─────────────────────
    ok("nomes diferentes dão chaves diferentes",
       chave_do_item(_f1[0]) != chave_do_item(_f2[1]))
    ok("o mesmo nome e sentido dá a mesma chave",
       chave_do_item(_f1[0]) == chave_do_item(_f2[0]))
    ok("sentido diferente muda a chave",
       chave_do_item({"favorecido": "X", "sentido": "saida"})
       != chave_do_item({"favorecido": "X", "sentido": "entrada"}))
    ok("espaço e acento não entram na chave",
       chave_do_item({"favorecido": "MERCADO LIVRE Ltda.", "sentido": "saida"})
       .replace("_", "").isalnum())
    _chaves = [chave_do_item(x) for x in _junta]
    ok("e a fila junta não tem chave repetida",
       len(_chaves) == len(set(_chaves)))

    # ── E A PERGUNTA E FEITA UMA VEZ SO ─────────────────────────────────
    _fonte = open(__file__, encoding="utf-8").read()
    _arv = _ast.parse(_fonte)
    _pg = next(n for n in _ast.walk(_arv)
               if isinstance(n, _ast.FunctionDef) and n.name == "pagina")
    _chamadas = [n for n in _ast.walk(_pg) if isinstance(n, _ast.Call)
                 and isinstance(n.func, _ast.Name) and n.func.id == "_perguntar"]
    ok("`pagina` pergunta uma vez", len(_chamadas) == 1)
    _pr = _insp.getsource(_processar)
    ok("e `_processar` não pergunta mais — ele devolve a fila",
       "_perguntar(" not in _pr and "return fila" in _pr)
    _pe = _insp.getsource(_perguntar)
    ok("nenhuma chave de widget sai da posição na lista",
       ("ext_fin_{" + "i}") not in _pe and ("ext_sv_{" + "i}") not in _pe)
    ok("elas saem da identidade do item", "chave_do_item(item)" in _pe)

    print("\nfalhas:", falhas)
