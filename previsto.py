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
PREVISIVEIS = ("CUSTO FIXO", "FOLHA", "NÃO OPERACIONAL")


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


def do_mes(ano, mes):
    """{finalidade: valor} do que o mês já deve. Fonte que falha vira 0,00.

    Uma grade fora do ar não pode derrubar a tela de gastos inteira — mas
    também não pode passar por "não há custo fixo neste mês". Por isso o
    `erros` sai junto, e a tela diz o que não conseguiu ler.
    """
    fora, erros = {}, []
    for nome, fn in (("CUSTO FIXO", _custo_fixo), ("FOLHA", _folha),
                     ("NÃO OPERACIONAL", _nao_operacional)):
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
        if fin in PREVISIVEIS:
            # O maior dos dois: o previsto ainda vai sair, e o que saiu a mais
            # do que se previa é gasto real que a previsão não enxergou.
            conta = max(r, p)
            origem = ("previsto" if conta == p and p > r
                      else ("extrato" if r else "previsto"))
        else:
            conta, origem = r, "extrato"
        if not conta:
            continue
        linhas.append({"finalidade": fin, "realizado": round(r, 2),
                       "previsto": round(p, 2), "conta": round(conta, 2),
                       "falta_sair": round(max(p - r, 0.0), 2),
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
