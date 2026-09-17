"""previsto.py — o que o mês JÁ DEVE, antes de aparecer no extrato.

O PROBLEMA
----------
A tela de gastos só sabia o que o extrato já mostrou. No dia 17 de setembro
isso são R$ 22.468,01 contra uma meta de R$ 170.000 — 13% consumidos — e a
leitura que a tela oferece é "dá para comprar à vontade". Não dá: o aluguel, a
luz, a folha e as parcelas do não operacional já estão comprometidos, só ainda
não bateram na conta.

Esperar o extrato para contar o que já se sabe é decidir com a metade do mês
escondida.

DE ONDE SAI
-----------
Das grades que o Studio já mantém, e de nenhum cadastro novo:

    CUSTO FIXO       custo_fixo + Ajuste de valor      (aluguel, luz, Anvisa…)
    FOLHA            folha_salarial + colaboradores    (gestores + CLT)
    NÃO OPERACIONAL  nao_operacional                   (parcelas de emprestimo)
    CHEQUES          cheques                           (emitidos, sem baixa)
    FATURA DO CARTÃO Controle MS, aba CARTÕES          (compras do vencimento)

O QUE ESTE MÓDULO NÃO FAZ: SOMAR DUAS VEZES
-------------------------------------------
Parte do previsto JÁ está no extrato — em setembro, R$ 208,55 de custo fixo e
R$ 27,00 de folha já passaram. Somar previsto + realizado contaria o mesmo
aluguel duas vezes e estouraria a meta no papel.

A regra é a que o dono deu: *"o que vier nos extratos servirá de conferência
dos valores contidos no custo fixo"*. Então, nessas três finalidades, vale o
MAIOR entre o previsto e o que já saiu:

    previsto 4.500 e saiu 208  ->  conta 4.500   (ainda vai sair o resto)
    previsto 4.500 e saiu 4.900 ->  conta 4.900   (saiu mais do que se previa)

Nas outras finalidades — mercadoria, embalagem, serviço — não há previsão: vale
o extrato, e só ele.
"""

from datetime import timezone, timedelta

FUSO = timezone(timedelta(hours=-3))

# As três finalidades que têm previsão. Fora delas, previsão seria chute: o
# Studio não sabe quanta mercadoria será comprada em outubro.
# Previsto que é o TOTAL do mês, e o extrato só confere: o aluguel do mês é
# 1.350, e os 1.350 que aparecem no extrato são o MESMO aluguel. Vale o maior
# dos dois — o que saiu acima do previsto é gasto que a previsão não enxergou.
PREVISIVEIS_TOTAL = ("CUSTO FIXO", "FOLHA", "NÃO OPERACIONAL",
                     "FATURA DO CARTÃO")

# Previsto que é o que FALTA: `cheques.a_vencer` já tira do cálculo todo cheque
# que baixou. Aqui o extrato e a previsão falam de cheques DIFERENTES, e o
# certo é somar.
#
# Usar o maior aqui subtraía o mês pela metade: três cheques compensados
# (3.000 no extrato) e dois em aberto (2.000 previstos) dariam 3.000, quando o
# mês tem 5.000 de cheque.
PREVISIVEIS_SOMA = ("CHEQUES",)

PREVISIVEIS = PREVISIVEIS_TOTAL + PREVISIVEIS_SOMA


def _custo_fixo(ano, mes):
    import ajustes as _aj
    import custo_fixo as _cf
    grade = _cf.carregar("custo_fixo")
    return round(float(_aj.aplicar(grade, _aj.carregar(), "custo_fixo",
                                   ano, mes)), 2)


def _folha(ano, mes):
    """Gestores + CLT. Duas grades, um número — é uma folha só para a meta."""
    import ajustes as _aj
    import folha_salarial as _fs
    import colaboradores as _co
    ajustes = _aj.carregar()
    gestores = _fs.total_da_folha(_fs.carregar(), ano, mes, ajustes)
    equipe = sum(p.get("total", 0.0)
                 for p in _co.folha_clt(_co.carregar(), ano, mes,
                                        _co.carregar_taxas(), ajustes))
    return round(float(gestores) + float(equipe), 2)


def _nao_operacional(ano, mes):
    import nao_operacional as _no
    return round(float(_no.total_no_mes(_no.carregar(), ano, mes)), 2)


def _cheques(ano, mes):
    """Os cheques que vencem no mês e ainda não baixaram.

    Só os em aberto: o que já foi debitado vem pelo extrato, e somar os dois
    contaria o mesmo cheque duas vezes.
    """
    import cheques as _ch
    return _ch.a_vencer(_ch.carregar(), ano, mes)


def _cartoes(ano, mes):
    """A fatura que vence no mês, pela aba CARTÕES do Controle MS.

    Não precisa de upload: o dono já lança cada compra ali, com o vencimento
    da fatura. Pedir que ele suba o PDF do cartão seria pedir de novo o que
    ele já digitou — e criaria uma segunda resposta para a mesma pergunta.
    """
    import controle_ms as _cms
    df, erro = _cms.ler("CARTÕES")
    if erro:
        raise RuntimeError(erro)
    if df.empty:
        return 0.0
    col = {str(c).strip().upper(): c for c in df.columns}
    c_mes, c_val = col.get("MÊS/ANO"), col.get("VALOR")
    if not c_mes or not c_val:
        raise RuntimeError("A aba CARTÕES não tem MÊS/ANO e Valor.")
    MES3 = ("jan", "fev", "mar", "abr", "mai", "jun",
            "jul", "ago", "set", "out", "nov", "dez")
    alvo = f"{MES3[int(mes) - 1]}{int(ano)}"
    total = 0.0
    for _, r in df.iterrows():
        if str(r.get(c_mes) or "").strip().lower().replace(" ", "") != alvo:
            continue
        try:
            total += float(str(r.get(c_val) or 0).replace(",", "."))
        except (TypeError, ValueError):
            continue
    return round(total, 2)


def do_mes(ano, mes):
    """{finalidade: valor} do que o mês já deve. Fonte que falha vira 0,00.

    Uma grade fora do ar não pode derrubar a tela de gastos inteira — mas
    também não pode passar por "não há custo fixo neste mês". Por isso o
    `erros` sai junto, e a tela diz o que não conseguiu ler.
    """
    fora, erros = {}, []
    for nome, fn in (("CUSTO FIXO", _custo_fixo), ("FOLHA", _folha),
                     ("NÃO OPERACIONAL", _nao_operacional),
                     ("CHEQUES", _cheques), ("FATURA DO CARTÃO", _cartoes)):
        try:
            fora[nome] = fn(ano, mes)
        except Exception as e:
            fora[nome] = 0.0
            erros.append(f"{nome}: {str(e)[:80]}")
    return fora, erros


def combinar(realizado_por_finalidade, previsto):
    """O gasto do mês com o previsto dentro, sem contar nada duas vezes.

    Devolve (linhas, total). Cada linha diz de onde veio o número, porque
    "4.500 previstos" e "4.500 que saíram" não valem o mesmo na hora de decidir.
    """
    real = {str(k).strip().upper(): float(v)
            for k, v in (realizado_por_finalidade or {}).items()}
    prev = {str(k).strip().upper(): float(v)
            for k, v in (previsto or {}).items()}
    linhas, total = [], 0.0
    for fin in sorted(set(real) | set(prev)):
        r, p = real.get(fin, 0.0), prev.get(fin, 0.0)
        if fin in PREVISIVEIS_SOMA:
            # Extrato e previsão falam de cheques diferentes: somam.
            conta, falta = r + p, p
            origem = "extrato+previsto" if r and p else ("extrato" if r
                                                         else "previsto")
        elif fin in PREVISIVEIS_TOTAL:
            # O maior dos dois: é o mesmo aluguel, e o que saiu a mais do que
            # se previa é gasto real que a previsão não enxergou.
            conta, falta = max(r, p), max(p - r, 0.0)
            origem = ("previsto" if conta == p and p > r
                      else ("extrato" if r else "previsto"))
        else:
            conta, falta, origem = r, 0.0, "extrato"
        if not conta:
            continue
        linhas.append({"finalidade": fin, "realizado": round(r, 2),
                       "previsto": round(p, 2), "conta": round(conta, 2),
                       "falta_sair": round(falta, 2),
                       "origem": origem})
        total += conta
    linhas.sort(key=lambda x: -x["conta"])
    return linhas, round(total, 2)


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    REAL = {"MERCADORIA": 20169.46, "CUSTO FIXO": 208.55, "FOLHA": 27.00}
    PREV = {"CUSTO FIXO": 6942.00, "FOLHA": 41000.00, "NÃO OPERACIONAL": 8500.0}
    _l, _t = combinar(REAL, PREV)
    _por = {x["finalidade"]: x for x in _l}

    ok("mercadoria vem do extrato, e nao ganha previsao",
       _por["MERCADORIA"]["conta"] == 20169.46
       and _por["MERCADORIA"]["origem"] == "extrato")
    # O caso que motivou o modulo: 208,55 de custo fixo no extrato nao quer
    # dizer que o mes custa 208,55 de custo fixo.
    ok("custo fixo vale o previsto enquanto o extrato nao alcanca",
       _por["CUSTO FIXO"]["conta"] == 6942.00
       and _por["CUSTO FIXO"]["falta_sair"] == 6733.45)
    ok("a folha inteira entra antes de bater na conta",
       _por["FOLHA"]["conta"] == 41000.00)
    ok("nao operacional entra mesmo sem nada no extrato",
       _por["NÃO OPERACIONAL"]["conta"] == 8500.0)
    ok("o total soma o previsto UMA vez, e nao previsto + realizado",
       _t == round(20169.46 + 6942.00 + 41000.00 + 8500.0, 2))

    # Gasto maior que o previsto e gasto real: a previsao errou para menos.
    _l2, _t2 = combinar({"CUSTO FIXO": 9000.0}, {"CUSTO FIXO": 6942.0})
    ok("extrato acima do previsto manda", _l2[0]["conta"] == 9000.0
       and _l2[0]["origem"] == "extrato" and _l2[0]["falta_sair"] == 0.0)

    # Cheque NAO segue a regra do aluguel: tres compensados no extrato e dois
    # em aberto sao cinco cheques, e nao os tres maiores.
    _lc, _tc = combinar({"CHEQUES": 3000.0}, {"CHEQUES": 2000.0})
    ok("cheque soma extrato e previsto, em vez de pegar o maior",
       _tc == 5000.0 and _lc[0]["falta_sair"] == 2000.0
       and _lc[0]["origem"] == "extrato+previsto")
    ok("fatura do cartao continua sendo a regra do maior",
       combinar({"FATURA DO CARTÃO": 1503.8},
                {"FATURA DO CARTÃO": 16062.68})[1] == 16062.68)

    ok("sem previsao nenhuma, o total e o extrato",
       combinar(REAL, {})[1] == round(20169.46 + 208.55 + 27.00, 2))
    ok("sem extrato nenhum, o total e a previsao",
       combinar({}, PREV)[1] == round(6942.00 + 41000.00 + 8500.0, 2))
    ok("finalidade zerada nao vira linha",
       combinar({"OUTROS": 0.0}, {})[0] == [])
    ok("nada de nada nao derruba", combinar(None, None) == ([], 0.0))
    ok("a ordem e do maior para o menor",
       [x["conta"] for x in _l] == sorted((x["conta"] for x in _l),
                                          reverse=True))
    ok("caixa e acento nao criam finalidade nova",
       len(combinar({"custo fixo": 100.0}, {"CUSTO FIXO": 500.0})[0]) == 1)

    print("\nfalhas:", falhas)
