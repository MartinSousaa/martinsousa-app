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

    st.markdown("#### 💳 Extratos e faturas — subir e conferir")
    st.caption(
        "Suba tudo aqui: extrato do Itaú (`.xlsx`), do Inter (`.csv`) e "
        "fatura do cartão (`.csv` ou `.pdf`). O Studio identifica o que é "
        "cada um pelo conteúdo, não pelo nome do arquivo. O que já tem "
        "histórico entra classificado; o que é novo cai na fila para você "
        "responder uma vez. Subir o mesmo arquivo duas vezes não duplica nada."
    )

    # ── TUDO NO MESMO LUGAR ──────────────────────────────────────────────
    #
    # Pedido do dono, repetido em 25/09: "eu quero poder anexar tudo no mesmo
    # lugar, o sistema identifica o que é extrato da conta e o que é fatura
    # do cartão". Ele tentou a tarde inteira e o seletor apagava os PDFs —
    # `type=["xlsx","csv"]` — sem que nada na tela dissesse por quê.
    arquivos = st.file_uploader(
        "Extrato ou fatura", type=["xlsx", "csv", "pdf"],
        accept_multiple_files=True,
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
            import fatura_pdf as _fpdf
            _tipo_arq = _fpdf.identificar(arq.name, arq.getvalue())
            if _tipo_arq in ("fatura_pdf", "fatura_inter"):
                # A FATURA TAMBÉM PERGUNTA. Até 05/10 ela pulava a fila: as
                # compras do cartão entravam sem finalidade e nenhum nome
                # novo virava pergunta — e saída sem finalidade fica FORA do
                # LPV (`lpv_mensal.py:51`) e dos gastos do mês.
                fila_total += _fatura(arq, _tipo_arq, usuario_logado) or []
                continue
            fila_total += _processar(
                arq, _itau, _inter, _fv, _lan, usuario_logado) or []
        fila_total = juntar_filas(fila_total)
        if fila_total:
            st.warning("Estes nomes não têm histórico. Responda uma vez e "
                       "eles nunca mais aparecem aqui.")
            _perguntar(fila_total, _fv, usuario_logado)

    st.markdown("---")
    _ver_mes(_fv, _lan, usuario_logado)


def _fatura(arq, tipo_arq, usuario_logado):
    """A fatura do cartão: lê, MOSTRA e deixa a pessoa conferir. Não grava.

    POR QUE ELA NÃO ENTRA SOZINHA
    -----------------------------
    O extrato é uma planilha com colunas: o banco garante a forma. A fatura
    em PDF é um desenho, e o texto sai na ordem em que foi impresso — o banco
    muda o layout numa atualização e o leitor passa a devolver número errado,
    sem erro nenhum na tela. Num sistema de dinheiro, essa é a pior falha
    possível.

    Então aqui se lê, se mostra, E SE PEDE CONFIRMAÇÃO. Gravar sozinho
    continua fora — o layout de um banco não se confere sozinho.

    O QUE MUDOU EM 28/09: antes o caminho era ler, mostrar, o dono conferir
    contra a fatura aberta, me avisar, eu ligar o lançamento e subir um
    deploy. Dias, para um clique — e enquanto isso o cartão ficava de fora
    do financeiro.

    Quem confere é quem tem a fatura aberta na frente, e é ele quem clica.
    Nada é gravado sem esse clique. Clicar duas vezes não duplica: a
    identidade de `lancamentos` é a mesma para o mesmo fato, e `gravar`
    devolve quantos foram repetidos — número que esta tela mostra, porque
    gravar 12 de 40 sem dizer por quê faz o dono achar que perdeu 28.
    """
    import fatura_pdf as _fpdf
    nome = arq.name
    with st.spinner(f"Lendo {nome}…"):
        if tipo_arq == "fatura_pdf":
            lancs, texto, erro = _fpdf.ler(arq.getvalue())
            _venc_txt = _vencimento_no_texto(texto)
        else:
            import fatura_inter as _fi
            lancs, cab, erro = _fi.ler(arq.getvalue())
            texto = ""
            _venc_txt = (cab or {}).get("vencimento", "")

    st.markdown(f"##### 🧾 {nome} — fatura de cartão")
    if erro:
        st.warning(f"**{nome}:** {erro}")
        if texto:
            with st.expander("O texto que saiu do PDF"):
                st.code(texto[:20000], language=None)
        return []

    # CLASSIFICADA COMO O EXTRATO: o cadastro de favorecidos dá a finalidade,
    # e o que não tem cadastro volta como fila — a mesma pergunta, uma vez.
    _conta_fat = f"cartão · {nome}"
    classificados, fila = classificar_fatura(lancs)
    fila = _enriquecer(fila, classificados, _conta_fat)

    _compras = [l for l in lancs if not l.get("pagamento")]
    _total = sum(abs(float(l.get("valor") or 0)) for l in _compras)
    c1, c2, c3 = st.columns(3)
    c1.metric("Lançamentos lidos", len(lancs))
    c2.metric("Compras", len(_compras))
    c3.metric("Total das compras", f"R$ {_fmt(_total)}")

    st.info(
        "**Confira antes de lançar.** A fatura foi lida e **ainda não foi "
        "gravada**. O Studio não lança fatura sozinho de propósito: ela é um "
        "desenho, e uma mudança de layout do banco vira número errado sem "
        "erro na tela. Compare a tabela abaixo com a fatura aberta — os "
        "valores, o total e as parcelas. Batendo, clique no botão no fim.")
    import pandas as _pd
    st.dataframe(
        _pd.DataFrame([{
            "data": l.get("data", ""), "descrição": l.get("descricao", ""),
            "valor": l.get("valor"),
            "parcela": (f"{l['parcela_n']}/{l['parcela_de']}"
                        if l.get("parcela_n") else ""),
            "é pagamento da fatura": "sim" if l.get("pagamento") else "",
        } for l in lancs]),
        use_container_width=True, hide_index=True,
        column_config={"valor": st.column_config.NumberColumn(
            format="R$ %.2f")})
    if texto:
        with st.expander("O texto cru do PDF — para conferir o que ficou de fora"):
            st.code(texto[:20000], language=None)

    # ── O CLIQUE QUE LANÇA ────────────────────────────────────────────────
    #
    # A chave carrega o NOME DO ARQUIVO: duas faturas na mesma tela têm dois
    # botões, e não um que grava a errada. Foi chave repetida que derrubou
    # esta tela em 25/09 (`StreamlitDuplicateElementKey: ext_fin_0`).
    _k_fat = "fat_ok_" + "".join(c for c in nome if c.isalnum())[:40]

    # O MÊS DO CAIXA. A compra do cartão pesa no mês em que a fatura é paga
    # (regra do dono: "a régua é o CAIXA"), e não na data da compra — a
    # parcela 7/10 vem com a data de março. O vencimento lido vem marcado;
    # quem tem a fatura aberta confirma junto com os valores.
    _comp_lida = competencia_da_fatura(lancs, _venc_txt)
    _opcoes = _meses_para_fatura(lancs, _comp_lida)
    _comp = st.selectbox(
        "Mês em que esta fatura é paga (vencimento) — é nele que as compras "
        "contam na meta e no LPV",
        _opcoes, index=(_opcoes.index(_comp_lida) if _comp_lida in _opcoes
                        else None),
        format_func=_rotulo_mes, placeholder="escolha o mês do vencimento",
        key=_k_fat + "_mes")
    if not _comp_lida:
        st.warning("Não achei o vencimento nesta fatura: escolha o mês acima.")
    st.caption(
        "Ao clicar você declara que conferiu estes valores contra a fatura. "
        "Nada foi gravado até aqui.")
    if st.button(f"✅ CONFIRMO que confere — lançar {len(lancs)} lançamento(s)",
                 key=_k_fat, use_container_width=True, disabled=not _comp):
        # O IMPORT VEM AQUI, e nao de fora: `_fatura` recebe (arq, tipo_arq,
        # usuario_logado) e NAO o modulo. A primeira versao usava `_lan` como
        # se ele existisse neste escopo — `NameError` no clique, e so no
        # clique. Foi o segundo verificador que pegou, que e para isso que
        # ele existe: nome lido antes de existir nao aparece no import.
        import lancamentos as _lan_fat
        _novos, _reps, _marc, _err = _lan_fat.gravar_fatura(
            classificados, _conta_fat, _comp, usuario_logado)
        if _err:
            st.error(f"Não consegui gravar: {_err}")
        else:
            # OS REPETIDOS TÊM NOME. Sem este número, gravar 12 de 40 parece
            # perda de 28 — e o dono refaz o trabalho à toa.
            _msg = (f"✅ {_novos} lançamento(s) gravado(s) em "
                    f"{_rotulo_mes(_comp)}.")
            if _reps:
                _msg += (f" {_reps} já estavam lá e foram ignorados — é o "
                         f"esperado se você já subiu esta fatura antes.")
            if _marc:
                _msg += (f" {_marc} já gravado(s) passaram a contar em "
                         f"{_rotulo_mes(_comp)}.")
            st.success(_msg)
    return fila


_MESES_TXT = ("janeiro", "fevereiro", "março", "abril", "maio", "junho",
              "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")


def _rotulo_mes(aaaa_mm):
    try:
        a, m = str(aaaa_mm).split("-")[:2]
        return f"{_MESES_TXT[int(m) - 1]}/{int(a)}"
    except (ValueError, IndexError):
        return str(aaaa_mm or "")


def _vencimento_no_texto(texto):
    """O "Vencimento 10/10/2026" do PDF. "" quando não acha."""
    import re as _re
    m = _re.search(r"vencimento\D{0,20}(\d{1,2}/\d{1,2}(?:/\d{2,4})?)",
                   str(texto or ""), _re.IGNORECASE)
    return m.group(1) if m else ""


def _datas_das_compras(lancs):
    fora = []
    for l in (lancs or []):
        d = str(l.get("data") or "")[:10]
        if len(d) == 10 and d[4] == "-" and not l.get("pagamento"):
            fora.append(d)
    return fora


def competencia_da_fatura(lancs, vencimento_txt):
    """AAAA-MM do vencimento. "" quando não dá para saber. Função pura.

    O Inter escreve "01/10", sem ano: o ano é o da compra mais recente, mais
    um quando o mês do vencimento vem antes dela (fatura de dezembro que
    vence em janeiro).
    """
    partes = [p for p in str(vencimento_txt or "").strip().split("/") if p]
    if len(partes) < 2 or not all(p.isdigit() for p in partes):
        return ""
    mes = int(partes[1])
    if not 1 <= mes <= 12:
        return ""
    if len(partes) >= 3:
        ano = int(partes[2])
        ano = ano + 2000 if ano < 100 else ano
        return f"{ano:04d}-{mes:02d}"
    datas = _datas_das_compras(lancs)
    if not datas:
        return ""
    ultima = max(datas)
    ano, mes_ultima = int(ultima[:4]), int(ultima[5:7])
    if mes < mes_ultima:
        ano += 1
    return f"{ano:04d}-{mes:02d}"


def _meses_para_fatura(lancs, lida=""):
    """Os meses que a pessoa pode escolher: da compra mais recente a dois
    meses depois dela, e o lido, se vier de fora disso."""
    datas = _datas_das_compras(lancs)
    from datetime import date as _d
    base = max(datas) if datas else _d.today().strftime("%Y-%m-%d")
    a, m = int(base[:4]), int(base[5:7])
    fora = []
    for i in range(-1, 3):
        mm = m + i
        aa = a + (mm - 1) // 12
        mm = (mm - 1) % 12 + 1
        fora.append(f"{aa:04d}-{mm:02d}")
    if lida and lida not in fora:
        fora.append(lida)
    return sorted(fora)


def sem_finalidade(linhas):
    """{"n", "total", "maiores"} das SAÍDAS sem finalidade. Função pura."""
    por_nome, n, total = {}, 0, 0.0
    for l in (linhas or []):
        try:
            v = float(l.get("valor") or 0)
        except (TypeError, ValueError):
            continue
        if v >= 0 or str(l.get("finalidade") or "").strip():
            continue
        n += 1
        total += -v
        nome = str(l.get("favorecido") or l.get("descricao") or "?")[:40]
        por_nome[nome] = por_nome.get(nome, 0.0) + (-v)
    maiores = sorted(por_nome.items(), key=lambda kv: -kv[1])[:5]
    return {"n": n, "total": round(total, 2),
            "maiores": [(k, round(v, 2)) for k, v in maiores]}


def classificar_fatura(lancs, cadastro=None):
    """(classificados, fila) das linhas de uma fatura de cartão.

    O pagamento da fatura anterior (a linha que a própria fatura marca como
    pagamento) não é compra: vai como FATURA DO CARTÃO, que fica fora do LPV
    e dos gastos — o dinheiro dele já saiu pelo extrato.
    """
    import favorecidos as _fv
    _base = []
    for l in (lancs or []):
        l = dict(l)
        if l.get("pagamento") and not l.get("finalidade"):
            l["finalidade"] = "FATURA DO CARTÃO"
        _base.append(l)
    return _fv.classificar(_base, cadastro)


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

    # ── O CUSTO FIXO E AS ASSINATURAS DO MÊS, PELO EXTRATO (06/10) ────────
    # O mesmo momento: o arquivo acabou de chegar. Onde o item veio com valor
    # diferente do cadastro, o real passa a valer naquele mês (`custo_real`).
    try:
        import custo_real as _cr
        _meses_arq = sorted({(int(str(l.get("data"))[:4]),
                              int(str(l.get("data"))[5:7]))
                             for l in classificados
                             if str(l.get("data") or "")[:7].count("-") == 1})
        _, _feitas_cr, _erro_cr = _cr.conferir_meses(_meses_arq)
        if _feitas_cr:
            st.info(f"📌 {_feitas_cr} valor(es) de custo fixo / assinatura "
                    "atualizado(s) no mês pelo extrato — veja em Custos fixos.")
        if _erro_cr:
            st.warning(f"Não consegui gravar o valor real do custo fixo: {_erro_cr}")
    except Exception as _e_cr:
        st.warning(f"Não consegui conferir o custo fixo: {type(_e_cr).__name__}")

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
    """As finalidades já usadas, mais as que a casa sempre teve.

    A lista vem de `favorecidos.FINALIDADES_BASE` — dono único. Esta cópia
    tinha quatro nomes a menos que a de `finalidades_tela.py`.
    """
    return _fv.finalidades_conhecidas()


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
    # SAÍDA SEM FINALIDADE NÃO ENTRA EM CONTA NENHUMA — nem no LPV
    # (`lpv_mensal.py:51`) nem nos gastos. Isso ficava calado nesta tela.
    _sf = sem_finalidade(linhas)
    if _sf["n"]:
        st.warning(_rot.tela(
            f"**{_sf['n']} saída(s) sem finalidade, R$ {_fmt(_sf['total'])}** "
            "— estão FORA do LPV e da meta de gastos deste mês até ganharem "
            "uma finalidade (no lápis acima, ou de vez em Finalidades). "
            "Maiores: " + " · ".join(f"{n} (R$ {_fmt(v)})"
                                     for n, v in _sf["maiores"])))

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

    # ── A FATURA TAMBÉM CLASSIFICA E PERGUNTA (05/10) ────────────────────
    # A ENTRADA VEM DO LEITOR: uma fatura no formato do CSV do Inter, lida
    # por `fatura_inter.ler` de verdade.
    import fatura_inter as _fi_t
    _csv = ('",""10/09/2026"",""•••• 1924"",""XPTONOVOFORNECEDOR 1"",'
            '""SERVICOS"",""Compra à vista"",""-R$ 150,00""";\n'
            '",""01/09/2026"",""•••• 8095"",""PAGTO DEBITO AUTOMATICO"",'
            '""OUTROS"",""Compra à vista"",""R$ 900,00""";\n')
    _lf, _cab_f, _err_f = _fi_t.ler(_csv)
    _cl, _fila_f = classificar_fatura(_lf, {})
    _nomes_f = [x.get("favorecido") or x.get("descricao") for x in _fila_f]
    ok("o leitor do Inter leu a fatura de teste", len(_lf) >= 1 and not _err_f)
    ok("compra sem cadastro na fatura vira pergunta, como no extrato",
       any("XPTONOVOFORNECEDOR" in str(n) for n in _nomes_f))
    ok("o pagamento da fatura não vira pergunta: é FATURA DO CARTÃO",
       all(l["finalidade"] == "FATURA DO CARTÃO" for l in _cl
           if l.get("pagamento")))
    _src_fat = _insp.getsource(_fatura)
    ok("a fatura grava o que foi CLASSIFICADO, não as linhas cruas",
       "_lan_fat.gravar_fatura(\n            classificados," in _src_fat
       and "classificar_fatura(lancs)" in _src_fat and "return fila" in _src_fat)
    ok("e a fila dela entra na mesma pergunta dos extratos",
       "fila_total += _fatura(" in _insp.getsource(pagina))
    # ── O CARTÃO CONTA UMA VEZ, NO MÊS DO VENCIMENTO (06/10) ─────────────
    # A CADEIA INTEIRA, com a entrada vinda do leitor: CSV do Inter -> ler ->
    # classificar -> mês do vencimento -> gravar -> meta de gastos. A parcela
    # 7/10 vem com a data da compra (março) e tem de pesar em outubro.
    ok("vencimento sem ano pega o ano da compra mais recente",
       competencia_da_fatura([{"data": "2026-09-16"}], "01/10") == "2026-10")
    ok("fatura de dezembro que vence em janeiro vira o ano",
       competencia_da_fatura([{"data": "2026-12-20"}], "05/01") == "2027-01")
    ok("vencimento com ano manda",
       competencia_da_fatura([], "10/10/2026") == "2026-10")
    ok("sem vencimento, nao inventa", competencia_da_fatura([{"data": "2026-09-01"}], "") == "")
    ok("o vencimento do PDF e achado no texto",
       _vencimento_no_texto("Vencimento 10/10/2026   Total R$ 1,00") == "10/10/2026")
    _csv_c = ('"Vencimento,""01/10"","""","""","""","""",""""";\n'
              '",""16/09/2026"",""•••• 1924"",""ZUL 1 cartao 2DKM8I"",""TRANSPORTE"",'
              '""Compra à vista"",""-R$ 6,95""";MERCADORIA\n'
              '",""17/03/2026"",""•••• 1924"",""MERCADOLIVRE 4PRODUTOS"",""OUTROS"",'
              '""Parcela 7/10"",""-R$ 73,99""";MERCADORIA\n'
              '",""01/09/2026"",""•••• 8095"",""PAGTO DEBITO AUTOMATICO"",""OUTROS"",'
              '""Compra à vista"",""R$ 900,00""";\n')
    _lc_c, _cab_c, _ = _fi_t.ler(_csv_c)
    _cl_c, _ = classificar_fatura(_lc_c, {})
    _comp_c = competencia_da_fatura(_lc_c, _cab_c.get("vencimento"))
    import lancamentos as _lan_c

    class _AbaC:
        def __init__(self):
            self.linhas = [_lan_c.COLUNAS]

        def get_all_records(self):
            return [dict(zip(self.linhas[0], l)) for l in self.linhas[1:]]

        def append_rows(self, linhas, **kw):
            self.linhas += [[str(c) for c in l] for l in linhas]

        def update(self, values, range_name=None, **kw):
            self.linhas = [[str(c) for c in v] for v in values]

    _aba_c = _AbaC()
    _g_aba_c = _lan_c._aba
    _lan_c._aba = lambda: _aba_c
    try:
        _lan_c.carregar.clear()
        _lan_c.gravar([{"data": "2026-10-01", "descricao": "DEB AUT FATURA CARTAO",
                        "valor": -80.94, "finalidade": "FATURA DO CARTÃO"}],
                      "inter", "t")
        _lan_c.carregar.clear()
        _gc = _lan_c.gravar_fatura(_cl_c, "cartão · t.csv", _comp_c, "t")
        _lan_c.carregar.clear()
        _out = _lan_c.do_mes(2026, 10, _lan_c.carregar())
        import meta_gastos as _mg_c
        _real_c = _mg_c.realizado_dos_lancamentos(2026, 10, _out)
        ok("a cadeia grava a fatura no mes do vencimento",
           _comp_c == "2026-10" and _gc[0] == 3 and len(_out) == 4)
        # Pagamento 80,94 = 6,95 + 73,99. O mês gastou 80,94, e não 161,88.
        ok("a meta conta o cartao uma vez, pelas compras",
           _real_c == 80.94
           and _lan_c.resumo_por_finalidade(_out).get("MERCADORIA") == 80.94)
        ok("e a parcela de marco nao cai em marco",
           _lan_c.do_mes(2026, 3, _lan_c.carregar()) == [])
    finally:
        _lan_c._aba = _g_aba_c
        _lan_c.carregar.clear()
    _src_fat2 = _insp.getsource(_fatura)
    ok("o clique so lanca com o mes do vencimento escolhido",
       "disabled=not _comp" in _src_fat2
       and "competencia_da_fatura(lancs, _venc_txt)" in _src_fat2)

    _sf_t = sem_finalidade([{"valor": -100.0, "finalidade": "", "favorecido": "A"},
                            {"valor": -50.0, "finalidade": "ADS"},
                            {"valor": 300.0, "finalidade": ""}])
    ok("saída sem finalidade é contada e nomeada (entrada não)",
       _sf_t["n"] == 1 and _sf_t["total"] == 100.0
       and _sf_t["maiores"] == [("A", 100.0)])

    print("\nfalhas:", falhas)

    # O CODIGO DE SAIDA. Sem ele, quem le `returncode` ve este modulo como
    # aprovado SEMPRE — e o `conferir.py` e o `checar_mutacao.py` leem
    # exatamente isso. Era assim que as entradas apontadas para ca ficavam
    # verdes por acidente, medindo nada.
    __import__("sys").exit(1 if falhas else 0)
