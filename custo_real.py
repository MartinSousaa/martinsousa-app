"""custo_real.py — o custo fixo e as assinaturas do mês, conferidos no extrato.

O PEDIDO, NAS PALAVRAS DO DONO (25/09)
--------------------------------------
"O extrato é somente para atualizar os gastos mensais, atualizar as saídas e
conferir os valores dos custos fixos e caso esteja diferente do que está
projetado ele alterará na base do custo fixo daquele mês para o valor real
contido no extrato ou nas faturas dos cartões!!!"

Em 06/10 ele viu que nada disso acontecia — e não acontecia mesmo: o Studio só
AVISAVA quando o extrato passava do cadastro (`composicao.py`), e a vigilância
das assinaturas só APONTAVA a diferença.

COMO FUNCIONA
-------------
1. Cada item do Custo fixo e cada Assinatura tem "Como aparece no extrato"
   (coluna `favorecido`; vários nomes separados por `;`). O casamento é o das
   assinaturas — palavra inteira, nunca pedaço (`assinaturas._casa`).
2. Para cada mês com lançamentos, soma o que saiu para aquele item.
3. Bateu com o cadastro (até R$ 0,50): nada a fazer. Diferente: o valor REAL
   vale NAQUELE MÊS — gravado na aba `custo_real_mes`. O cadastro não muda, e
   o mês seguinte volta ao cadastrado (reajuste é outra coisa: Ajuste de valor).
4. Quem soma o custo fixo do mês (`total_custo_fixo`, `total_assinaturas`)
   usa o real onde ele existe e o cadastro no resto.

Item sem cobrança no mês NÃO vira zero: pode ser fatura ainda não importada.
Ele continua com o cadastro, e a tela de Assinaturas aponta o que não apareceu.
"""

from datetime import datetime, timezone, timedelta

import pandas as pd
import streamlit as st

ABA = "custo_real_mes"
COLUNAS = ["grade", "item", "mes", "valor", "cadastro", "origem",
           "atualizado_em"]
TOLERANCIA = 0.50
FUSO = timezone(timedelta(hours=-3))


def _num(v):
    try:
        f = float(str(v).replace(",", ".")) if not isinstance(v, (int, float)) else float(v)
        return f if f == f else 0.0
    except (TypeError, ValueError):
        return 0.0


def apelidos(linha):
    """Os nomes que este item tem no extrato. `;` separa mais de um."""
    return [a.strip() for a in str(linha.get("favorecido") or "").split(";")
            if a.strip()]


# O nome do item vale como "Como aparece no extrato" a partir de 5 letras.
# Dono, 06/10: "o nome já diz o que é e meu custo fixo está exatamente com
# esse nome" (HOSTGATOR, CLAUDE). Nome curto continua de fora: "Luz" e "Água"
# casariam com qualquer descrição que tivesse a palavra.
NOME_MINIMO = 5


def nomes_do_item(linha):
    """Como este item aparece no extrato. UMA regra: a fila de finalidades
    (`extratos_tela.sugerir_fixos`) e o valor real do mês leem daqui."""
    import favorecidos as _fv
    nomes = apelidos(linha)
    # Coluna preenchida MANDA: o dono escreveu ali exatamente como o item
    # aparece. Somar o nome do item por cima alargaria o que ele restringiu —
    # "Estacionamento" (ROBSON; VANDA) passaria a pegar qualquer linha com a
    # palavra ESTACIONAMENTO, e o custo do mês subiria sozinho.
    if nomes:
        return nomes
    item = str(linha.get("item") or "").strip()
    if len(_fv.chave(item).replace(" ", "")) >= NOME_MINIMO:
        return [item]
    return []


# A PALAVRA PARECIDA (dono, 09/10: "o sistema precisa analisar os extratos e
# cruzar com os nomes dos custos fixos"). O cadastro dizia KLING e a fatura
# escreve KLINGAI.COM: palavra inteira não casa, e o item nunca era achado.
# Começo de palavra casa — mas só como SUGESTÃO na fila, nunca direto na
# conta: "CANVA" também é o começo de "CANVAS ARTESANAL", o fornecedor de
# tecido. Confirmada no Salvar, a grafia do extrato vira apelido do item
# (`com_apelido`) e daí em diante o casamento é exato.
PARECIDO_MINIMO = 4


def parecido(lanc, nome):
    """A palavra do lançamento que COMEÇA com `nome` e é maior. "" se não há."""
    import assinaturas as _as
    alvo = _as._chave(nome).replace(" ", "")
    if len(alvo) < PARECIDO_MINIMO:
        return ""
    texto = (_as._chave(lanc.get("descricao")) + " "
             + _as._chave(lanc.get("favorecido")))
    for w in texto.split():
        if w != alvo and w.startswith(alvo) and w.isalpha():
            return w
    return ""


def com_apelido(linha, palavra):
    """O "Como aparece no extrato" do item com `palavra` acrescentada.

    Sem a coluna preenchida, o nome do item entra junto: senão o apelido novo
    restringiria o item a ele só (`nomes_do_item`), e o que casava pelo nome
    deixaria de casar.
    """
    atuais = nomes_do_item(linha)
    if str(palavra or "").strip().upper() in {n.strip().upper() for n in atuais}:
        return str(linha.get("favorecido") or "")
    return "; ".join([n.strip() for n in atuais if n.strip()]
                     + [str(palavra).strip().upper()])


def cobrado_no_mes(linha, lancamentos_do_mes):
    """Quanto saiu para este item no mês. None quando não apareceu.

    Casa por "Como aparece no extrato" e pelo nome do item com 5+ letras
    (`nomes_do_item`). Sem nenhum dos dois também é None.
    """
    import assinaturas as _as
    nomes = nomes_do_item(linha)
    if not nomes:
        return None
    total, achou = 0.0, False
    for l in (lancamentos_do_mes or []):
        if any(_as._casa(l, {"favorecido": n}) for n in nomes):
            # SÓ SAÍDA: nos lançamentos gravados a saída é negativa, no
            # extrato e na fatura (`fatura_pdf.py:152`). `assinaturas.
            # _valor_de_saida` usa abs() e contaria o PIX recebido.
            v = _num(l.get("valor"))
            if v < 0:
                total += -v
                achou = True
    return round(total, 2) if achou else None


def divergencias(grade, linhas, ano, mes, lancamentos_do_mes, cadastro_de):
    """[{grade, item, mes, cadastro, valor}] — o que o extrato diz diferente.

    `cadastro_de(linha)` devolve o valor cadastrado daquele item no mês (com
    os ajustes de valor já aplicados).
    """
    fora = []
    alvo = f"{int(ano):04d}-{int(mes):02d}"
    for l in (linhas or []):
        item = str(l.get("item") or "").strip()
        if not item:
            continue
        cob = cobrado_no_mes(l, lancamentos_do_mes)
        if cob is None:
            continue
        cad = round(float(cadastro_de(l) or 0.0), 2)
        if abs(cob - cad) > TOLERANCIA:
            fora.append({"grade": grade, "item": item, "mes": alvo,
                         "cadastro": cad, "valor": cob})
    return fora


# ── Planilha ─────────────────────────────────────────────────────────────────

def _aba():
    import gspread
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        return planilha.worksheet(ABA)
    except gspread.exceptions.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA, rows=500, cols=len(COLUNAS))
        aba.append_row(COLUNAS, value_input_option="RAW")
        return aba


@st.cache_data(ttl=300, show_spinner=False)
def carregar():
    """{(grade, item, 'AAAA-MM'): valor}. Vazio quando a aba falha."""
    try:
        registros = _aba().get_all_records(value_render_option="UNFORMATTED_VALUE")
    except Exception:
        return {}
    fora = {}
    for r in registros:
        k = (str(r.get("grade") or "").strip(), str(r.get("item") or "").strip(),
             str(r.get("mes") or "").strip()[:7])
        if all(k):
            fora[k] = round(_num(r.get("valor")), 2)
    return fora


def gravar(novas, mapa=None):
    """Grava as divergências que ainda não estão lá. (quantas, erro)."""
    mapa = carregar() if mapa is None else mapa
    agora = datetime.now(FUSO).strftime("%Y-%m-%d %H:%M")
    linhas = [[d["grade"], d["item"], d["mes"], d["valor"], d["cadastro"],
               "extrato", agora] for d in (novas or [])
              if mapa.get((d["grade"], d["item"], d["mes"])) != d["valor"]]
    if not linhas:
        return 0, ""
    try:
        _aba().append_rows(linhas, value_input_option="RAW")
    except Exception as e:
        return 0, type(e).__name__
    carregar.clear()
    return len(linhas), ""


# ── Quem soma o mês ──────────────────────────────────────────────────────────

def valor_do_mes(grade, item, ano, mes, valor_cadastro, mapa):
    """O real do mês, quando o extrato trouxe; senão o cadastro.

    A ÚLTIMA leitura vale: `carregar` monta o dicionário na ordem da aba, e a
    linha mais nova sobrescreve a anterior do mesmo mês.
    """
    k = (grade, str(item or "").strip(), f"{int(ano):04d}-{int(mes):02d}")
    return mapa.get(k, valor_cadastro) if mapa else valor_cadastro


def total_custo_fixo(grade_df, ajustes_df, ano, mes, mapa):
    """O custo fixo do mês: cadastro com ajustes, e o real onde o extrato disse."""
    import ajustes as _aj
    d = pd.DataFrame(grade_df)
    if d.empty:
        return 0.0
    por_item = _aj.por_item(ajustes_df)
    total = 0.0
    for _, r in d.iterrows():
        item = str(r.get("item", "") or "").strip()
        if not item:
            continue
        cad = _aj.valor_no_mes(r.get("valor_mensal"), r.get("vigente_desde"),
                               por_item.get(("custo_fixo", item)), ano, mes)
        total += valor_do_mes("custo_fixo", item, ano, mes, cad, mapa)
    return round(float(total), 2)


def total_assinaturas(linhas, ano, mes, mapa):
    """As assinaturas do mês: o cadastro (anual rateada), e o real do extrato."""
    import assinaturas as _as
    total = 0.0
    for l in (linhas or []):
        item = str(l.get("item") or "").strip()
        if not item:
            continue
        total += valor_do_mes("assinaturas", item, ano, mes,
                              _as.custo_mensal(l), mapa)
    return round(total, 2)


def conferir_meses(meses, lancamentos=None, gravar_agora=True):
    """Confere Custo fixo e Assinaturas nos `meses` [(ano, mes)].

    (divergencias, gravadas, erro). É o que a tela de Custo fixo, a de
    Assinaturas e o anexo de extrato chamam. Só grava o que ainda não está
    gravado — conferir de novo não escreve nada.
    """
    import ajustes as _aj
    import assinaturas as _as
    import custo_fixo as _cf
    import lancamentos as _lan
    todos = (_lan.aplicar_cadastro(_lan.carregar()) if lancamentos is None
             else lancamentos)
    grade = _cf.carregar("custo_fixo")
    linhas_cf = grade.to_dict("records") if not grade.empty else []
    ajustes_df = _aj.carregar()
    por_item = _aj.por_item(ajustes_df)
    linhas_as = _as.carregar() or []
    achadas = []
    for ano, mes in meses:
        alvo = f"{int(ano):04d}-{int(mes):02d}"
        do_mes = [l for l in todos if str(l.get("data", "")).startswith(alvo)]
        if not do_mes:
            continue
        achadas += divergencias(
            "custo_fixo", linhas_cf, ano, mes, do_mes,
            lambda l: _aj.valor_no_mes(l.get("valor_mensal"),
                                       l.get("vigente_desde"),
                                       por_item.get(("custo_fixo",
                                                     str(l.get("item")).strip())),
                                       ano, mes))
        achadas += divergencias("assinaturas", linhas_as, ano, mes, do_mes,
                                _as.custo_mensal)
    if not gravar_agora:
        return achadas, 0, ""
    feitas, erro = gravar(achadas)
    return achadas, feitas, erro


def quadro(grade, linhas, meses, mapa):
    """[{Item, Mês, Cadastro, No extrato}] do que foi conferido diferente."""
    fora = []
    nomes = {str(l.get("item") or "").strip() for l in (linhas or [])}
    for (g, item, mes), valor in sorted((mapa or {}).items()):
        if g != grade or item not in nomes:
            continue
        if (int(mes[:4]), int(mes[5:7])) not in set(meses):
            continue
        fora.append({"Item": item, "Mês": f"{mes[5:7]}/{mes[:4]}",
                     "No extrato": valor})
    return fora


def mostrar(st_, grade, linhas, hoje):
    """Confere os últimos 4 meses e mostra o que veio diferente. Na tela."""
    meses = ultimos_meses(hoje, 4)
    try:
        _ach, feitas, erro = conferir_meses(meses)
    except Exception as e:
        st_.warning(f"Não consegui conferir com os extratos: {type(e).__name__}")
        return
    if erro:
        st_.warning(f"Conferi, mas não consegui gravar o valor real: {erro}")
    sem = [str(l.get("item")) for l in (linhas or [])
           if str(l.get("item") or "").strip() and not nomes_do_item(l)]
    q = quadro(grade, linhas, meses, carregar())
    st_.markdown("##### 🔍 Conferido nos extratos")
    if feitas:
        st_.success(f"{feitas} valor(es) real(is) atualizado(s) agora pelos "
                    "extratos.")
    if q:
        st_.dataframe(pd.DataFrame(q), hide_index=True, use_container_width=True)
    else:
        st_.caption("Nada diferente do cadastro nos últimos 4 meses.")
    if sem:
        st_.info("Sem «Como aparece no extrato», o Studio não acha estes "
                 "itens no extrato: **" + ", ".join(sem[:20]) + "**.")


def ultimos_meses(hoje, quantos=4):
    a, m, fora = hoje.year, hoje.month, []
    for _ in range(quantos):
        fora.append((a, m))
        a, m = (a - 1, 12) if m == 1 else (a, m - 1)
    return fora


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # A ENTRADA NA FORMA DO SISTEMA: lançamentos como `lancamentos.carregar`
    # (valor float, saída negativa no extrato), linhas como as grades gravam.
    L = lambda desc, v, data="2026-09-10", fav="": {
        "data": data, "descricao": desc, "favorecido": fav, "valor": v}
    luz = {"item": "Luz", "valor_mensal": 450.0, "favorecido": "ENEL"}
    est = {"item": "Estacionamento", "valor_mensal": 550.0,
           "favorecido": "ROBSON; VANDA"}
    sem = {"item": "Água", "valor_mensal": 70.0, "favorecido": ""}
    lanc = [L("PIX ENVIADO ENEL DISTRIBUICAO", -512.37),
            L("PIX ENVIADO ROBSON SILVA", -200.0),
            L("PIX ENVIADO VANDA MARIA", -350.0),
            L("PIX RECEBIDO ENEL", 30.0),
            L("PIX ENVIADO AGUA E CIA", -70.0)]
    ok("soma o que saiu para o item no mês", cobrado_no_mes(luz, lanc) == 512.37)
    ok("vários nomes separados por ; somam juntos",
       cobrado_no_mes(est, lanc) == 550.0)
    ok("entrada não é cobrança", cobrado_no_mes(
        luz, [L("PIX RECEBIDO ENEL", 30.0)]) is None)
    ok("nome curto ('Água') sem 'Como aparece no extrato' não casa",
       cobrado_no_mes(sem, lanc) is None)
    # 06/10: "o nome já diz o que é". Hostgator e Claude, sem a coluna
    # preenchida, casam pelo nome — na fatura do cartão, com a parcela no fim.
    _host = {"item": "Hostgator", "valor_mensal": 47.72, "favorecido": ""}
    _cla = {"item": "Claude", "valor_mensal": 550.0, "favorecido": ""}
    ok("nome do item com 5+ letras casa sem preencher a coluna",
       cobrado_no_mes(_host, [L("HOSTGATOR 02/06", -47.72)]) == 47.72
       and cobrado_no_mes(_cla, [L("ANTHROPIC* CLAUDE SUB BRL550,00 "
                                   "US$108,45 R$5,47", -593.22)]) == 593.22)
    ok("nomes_do_item: a coluna preenchida manda; vazia, vale o nome do item",
       nomes_do_item({"item": "Hostgator", "favorecido": "HOSTGATOR; HG"})
       == ["HOSTGATOR", "HG"]
       and nomes_do_item({"item": "Hostgator", "favorecido": ""}) == ["Hostgator"]
       and nomes_do_item({"item": "Luz", "favorecido": ""}) == [])
    _est = {"item": "Estacionamento", "valor_mensal": 550.0,
            "favorecido": "ROBSON; VANDA"}
    ok("item com a coluna preenchida NAO casa pela palavra do nome",
       cobrado_no_mes(_est, [L("PAGTO ESTACIONAMENTO SHOPPING", -30.0)]) is None)
    ok("palavra inteira: ENEL não casa com ENELTON",
       cobrado_no_mes(luz, [L("PIX ENELTON LTDA", -10.0)]) is None)
    dv = divergencias("custo_fixo", [luz, est, sem], 2026, 9, lanc,
                      lambda l: l["valor_mensal"])
    ok("só o que veio diferente vira divergência",
       [(d["item"], d["valor"], d["mes"]) for d in dv]
       == [("Luz", 512.37, "2026-09")])
    _mapa = {("custo_fixo", "Luz", "2026-09"): 512.37}
    ok("diferença até R$ 0,50 não é divergência (arredondamento do banco)",
       TOLERANCIA == 0.50 and not divergencias(
           "custo_fixo", [luz], 2026, 9, [L("PIX ENEL", -450.40)],
           lambda l: l["valor_mensal"]))
    ok("o real vale naquele mês", valor_do_mes("custo_fixo", "Luz", 2026, 9,
                                                450.0, _mapa) == 512.37)
    ok("e o mês seguinte volta ao cadastro",
       valor_do_mes("custo_fixo", "Luz", 2026, 10, 450.0, _mapa) == 450.0)
    _g = pd.DataFrame([{"item": "Luz", "valor_mensal": 450.0,
                        "vigente_desde": ""},
                       {"item": "Bling", "valor_mensal": 400.0,
                        "vigente_desde": ""}])
    import ajustes as _aj_t
    _aj_vazio = pd.DataFrame(columns=_aj_t.COLUNAS)
    ok("o total do custo fixo usa o real onde existe",
       total_custo_fixo(_g, _aj_vazio, 2026, 9, _mapa) == 512.37 + 400.0)
    ok("e o cadastro no resto",
       total_custo_fixo(_g, _aj_vazio, 2026, 10, _mapa) == 850.0)
    import assinaturas as _as_t
    _ass = _as_t.sugestoes_como_linhas()
    ok("sem divergência, as assinaturas do mês são o total do cadastro",
       total_assinaturas(_ass, 2026, 9, {}) == _as_t.total_mensal(_ass))
    _gravou = []
    _g_carr, _g_aba = carregar, _aba
    try:
        globals()["carregar"] = lambda: {("custo_fixo", "Luz", "2026-09"): 512.37}
        class _A:
            def append_rows(self, r, value_input_option=None):
                _gravou.extend(r)
        globals()["_aba"] = lambda: _A()
        carregar.clear = lambda: None
        n, e = gravar(dv + [{"grade": "custo_fixo", "item": "Bling",
                             "mes": "2026-09", "valor": 410.0,
                             "cadastro": 400.0}])
        ok("conferir de novo não grava o que já está lá",
           n == 1 and [r[1] for r in _gravou] == ["Bling"])
    finally:
        globals()["carregar"], globals()["_aba"] = _g_carr, _g_aba
    # A CADEIA: quem soma o custo fixo do mês para a Home, o LPV e a meta é
    # `previsto._custo_fixo` — ele tem de chegar ao valor real.
    import previsto as _pv_t
    import custo_fixo as _cf_t
    # `previsto` importa `custo_real` pelo nome — outro objeto que este
    # `__main__`; é nele que a leitura é trocada.
    import custo_real as _cr_mod
    _gg = (_cf_t.carregar, _aj_t.carregar, _cr_mod.carregar)
    try:
        _cf_t.carregar = lambda aba: _g
        _aj_t.carregar = lambda: _aj_vazio
        _cr_mod.carregar = lambda: _mapa
        ok("pela cadeia, o custo fixo do mês (Home, LPV, meta) usa o real",
           _pv_t._custo_fixo(2026, 9) == 512.37 + 400.0
           and _pv_t._custo_fixo(2026, 10) == 850.0)
    finally:
        _cf_t.carregar, _aj_t.carregar, _cr_mod.carregar = _gg
    import inspect as _insp
    import home_gestao as _hg_t
    import lpv_mensal as _lm_t
    import extratos_tela as _et_t
    import assinaturas_tela as _at_t
    ok("as assinaturas do mês na Home e no LPV usam o real do extrato",
       "_cr.total_assinaturas(" in _insp.getsource(_hg_t._partes_fixas)
       and "_cr.total_assinaturas(" in _insp.getsource(_lm_t._partes_do_mes))
    ok("o anexo do extrato (e o da fatura) confere o custo fixo do mês",
       "_conferir_custo_real(classificados)" in _insp.getsource(_et_t._processar)
       and "_cr.conferir_meses(" in _insp.getsource(_et_t._conferir_custo_real))
    ok("as telas de Custo fixo e Assinaturas conferem ao abrir",
       '_cr.mostrar(st, "custo_fixo"' in _insp.getsource(_cf_t.pagina)
       and '_cr.mostrar(st, "assinaturas"' in _insp.getsource(_at_t.pagina))

    # ── A PALAVRA PARECIDA (09/10): KLING no cadastro, KLINGAI.COM na fatura ─
    # O lançamento com o texto que a fatura grava de verdade (print do dono).
    _kl = {"descricao": "KLINGAI.COM BRL53,28 US$10,50 R$5,42",
           "favorecido": "KLINGAI.COM BRL53,28 US$10,50 R$5,42", "valor": -56.91}
    _item_kl = {"item": "KlingAI", "valor_mensal": 51.13, "favorecido": "KLING"}
    ok("palavra inteira não casa KLING com KLINGAI — e por isso existe parecido",
       cobrado_no_mes(_item_kl, [_kl]) is None)
    ok("parecido acha a grafia do extrato", parecido(_kl, "KLING") == "KLINGAI")
    ok("parecido não repete a palavra exata nem aceita nome curto",
       parecido(_kl, "KLINGAI") == "" and parecido(_kl, "KLI") == "")
    ok("depois de aprender, o casamento é exato e o valor do mês é lido",
       com_apelido(_item_kl, "KLINGAI") == "KLING; KLINGAI"
       and cobrado_no_mes({**_item_kl, "favorecido": "KLING; KLINGAI"},
                          [_kl]) == 56.91)
    ok("aprender de novo não duplica",
       com_apelido({**_item_kl, "favorecido": "KLING; KLINGAI"}, "klingai")
       == "KLING; KLINGAI")
    # Sem a coluna preenchida, o nome do item entra junto: senão o apelido
    # novo restringiria o item a ele só, e "HOSTGATOR" deixaria de casar.
    ok("sem apelido, o nome do item entra junto com o aprendido",
       com_apelido({"item": "Hostgator", "favorecido": ""}, "HOSTGATORBR")
       == "Hostgator; HOSTGATORBR")

    print("\nfalhas:", falhas)
    __import__("sys").exit(1 if falhas else 0)
