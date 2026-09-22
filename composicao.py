"""composicao.py — o que entra no ponto de equilíbrio, e de que lado.

O DEFEITO QUE ELE CORRIGE
--------------------------
`home_gestao.py` chamava `linhas_de_equilibrio()` SEM ARGUMENTO. Isso usa as
constantes de `financeiro_equilibrio.py` — uma foto de custo tirada em 2026 e
chumbada no código. O custo fixo que o dono cadastra, a folha que ele mantém,
as assinaturas que ele acabou de levantar: nada disso chegava à conta.

Ele perguntou exatamente isso: *"Quais custos o sistema está considerando para
traçar a meta? Se é com base no meu preenchimento…"*. Não era.

A REGRA QUE DECIDE O LADO, E ELA É UMA SÓ
------------------------------------------
    faturamento de equilíbrio  =  custo fixo  ÷  margem de contribuição
                                  ─────────      ──────────────────────
                                  NUMERADOR          DENOMINADOR

    numerador    o que sai igual vendendo 100 ou 3.000
    denominador  o que sobe junto com a venda

Um gasto no lado errado não erra um pouco: ele erra a conta inteira. Somar
mercadoria ao numerador e ainda dividir por 29,82% conta o mesmo custo duas
vezes e leva o equilíbrio de R$ 132 mil para R$ 269 mil.

O QUE FOI DECIDIDO COM O DONO, ITEM A ITEM
-------------------------------------------
    NUMERADOR    despesas operacionais (água, luz, internet, aluguéis,
                 estacionamento FIXO), serviços/assinaturas, Folha Gerência
    DENOMINADOR  mercadoria, embalagem, comissão, frete, NF/impostos, FLEX,
                 ADS, e o custo operacional por venda
    2ª LINHA     PRONAMPs — parcela de empréstimo sai do caixa, mas não é
                 custo de operar
    FORA         transferência entre contas, aplicação, rateio de custo fixo
                 — dinheiro mudando de lugar não é gasto

O HEADCOUNT TEM DUAS RESPOSTAS, E AS DUAS SÃO CERTAS
-----------------------------------------------------
Enquanto a Reserva cobre, a folha do quadro não pesa no equilíbrio de hoje —
quem a paga é a verba aplicada. Mas ela volta no dia em que a reserva acabar.

Por isso saem SEMPRE os dois números: o equilíbrio de hoje e o equilíbrio com
o Headcount dentro. A distância entre eles é quanto o faturamento precisa
subir, e é a resposta para a pergunta que ele fez.

AS ASSINATURAS SAEM DO CUSTO OPERACIONAL
-----------------------------------------
Elas são fixas — paga-se o mesmo Trello vendendo 100 ou 3.000 — e por isso vão
ao numerador. Mas elas TAMBÉM aparecem nos baldes SERVIÇO do PIX e do cartão,
que compõem o custo operacional por venda. Sem subtraí-las de lá, o mesmo
Trello conta duas vezes: uma como fixo, outra diluído em cada venda.
"""

import unicodedata

# ── De que lado cada finalidade cai ─────────────────────────────────────────
# Só os nomes que o Studio usa (`finalidades_tela.py:118`). O que não estiver
# aqui cai em DESCONHECIDA e APARECE na tela — finalidade nova entrando muda
# de lado sozinha em silêncio é como a conta passa a mentir sem ninguém ver.
NUMERADOR = ("CUSTO FIXO", "SERVIÇO", "SERVIÇOS")

# JÁ MEDIDO DENTRO DA MARGEM — e por isso NÃO pode ser somado de novo.
#
# As taxas de `financeiro_equilibrio.TAXAS_VARIAVEIS` foram medidas em 17.793
# vendas: custo do produto 35,95%, comissão 18,92%, frete 7,59%, NF 7,72%.
# MERCADORIA é o custo do produto; IMPOSTO é a NF; o repasse das plataformas é
# a comissão. Eles já estão descontados na margem.
#
# Somá-los outra vez como se fossem custo novo foi o defeito que os testes
# pegaram aqui dentro: a margem despencou de 29,82% para 8,43% e o equilíbrio
# saltou para R$ 560 mil. O erro que este arquivo existe para impedir,
# cometido dentro dele.
MEDIDO_NA_MARGEM = ("MERCADORIA", "IMPOSTO",
                    "MERCADO LIVRE", "SHOPEE", "SHEIN", "TIKTOK", "AMAZON",
                    "SITE", "SITE MS")

# O CUSTO OPERACIONAL POR VENDA — o que a margem medida NÃO conhece.
#
# É o balde que o dono montou na planilha (DIN FINANÇAS, "PIX PARA LPV" e
# "CARTÃO PARA LPV"): tudo que sai por PIX e cartão MENOS mercadoria e NF,
# mais a fatura do ML e o líquido do Flex.
#
# Ele rateia isso por PARTICIPAÇÃO NO FATURAMENTO de cada venda — que é o
# mesmo que uma taxa sobre o faturamento. Por isso entra no denominador, ao
# lado de comissão e frete, e não no numerador.
OPERACIONAL = ("EMBALAGEM", "FLEX", "ADS", "ESTACIONAMENTO", "LIMPEZA",
               "OUTROS", "CONSUMO INTERNO")

SEGUNDA_LINHA = ("NÃO OPERACIONAL", "NAO OPERACIONAL", "EMPRESTIMO PRONAMP",
                 "REEMBOLSO PRONAMP")

FORA = ("TRANSFERENCIA ENTRE CONTAS", "TRANSFERÊNCIA ENTRE CONTAS",
        "TRANSFERENCIA", "APLICACAO", "APLICAÇÃO", "RATEIO CUSTO FIXO",
        "REEMBOLSO")


def _chave(t):
    t = unicodedata.normalize("NFKD", str(t or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).upper().strip()


_MAPA = {}
for _grupo, _nome in ((NUMERADOR, "numerador"),
                      (OPERACIONAL, "operacional"),
                      (MEDIDO_NA_MARGEM, "ja_na_margem"),
                      (SEGUNDA_LINHA, "segunda_linha"), (FORA, "fora")):
    for _f in _grupo:
        _MAPA[_chave(_f)] = _nome


def lado(finalidade):
    """'numerador' | 'denominador' | 'segunda_linha' | 'fora' | 'desconhecida'.

    Devolve 'desconhecida' em vez de escolher um lado. Finalidade nova entrando
    calada num dos lados é como a conta passa a mentir: o número muda, ninguém
    mexeu em nada, e não há onde olhar.
    """
    return _MAPA.get(_chave(finalidade), "desconhecida")


def _num(v):
    """Valor da planilha como número. Texto impossível vira 0, e não exceção.

    Uma célula com "a confirmar" no meio do resumo derrubava a `separar` com
    ValueError — e a Home inteira junto, porque é ela que chama. Gasto que não
    dá para ler não pode ser o motivo de o dono não ver número nenhum.
    """
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace("R$", "").replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return 0.0


def separar(resumo_por_finalidade):
    """{lado: total} a partir de {finalidade: valor}, mais a lista do que
    não foi reconhecido.

    Os valores entram como MÓDULO: o resumo de gastos vem com saída negativa,
    e somar negativo com positivo daria um numerador menor do que a realidade.
    """
    fora = {"numerador": 0.0, "operacional": 0.0, "ja_na_margem": 0.0,
            "segunda_linha": 0.0, "fora": 0.0, "desconhecida": 0.0}
    nao_reconhecidas = []
    for fin, valor in (resumo_por_finalidade or {}).items():
        onde = lado(fin)
        v = abs(_num(valor))
        fora[onde] += v
        if onde == "desconhecida" and v > 0:
            nao_reconhecidas.append((str(fin), v))
    return {k: round(v, 2) for k, v in fora.items()}, \
        sorted(nao_reconhecidas, key=lambda x: -x[1])


def taxa_operacional(gasto_denominador, faturamento):
    """O custo operacional como FRAÇÃO do faturamento.

    Ratear por participação no faturamento — a mudança que o dono aplicou na
    planilha — é matematicamente o mesmo que cobrar um percentual. Em janeiro:
    14.266,34 / 205.891,79 = 6,93%.

    Era isto que faltava no denominador: a margem media de 29,82% não conhece
    esse custo, e por isso o equilíbrio saía baixo demais.
    """
    try:
        f = float(faturamento or 0.0)
        if f <= 0:
            return 0.0
        return max(0.0, float(gasto_denominador or 0.0)) / f
    except (TypeError, ValueError):
        return 0.0


def margem(taxas_medidas, taxa_op=0.0):
    """Quanto sobra de cada real, já descontado o custo operacional.

    `taxas_medidas` é `financeiro_equilibrio.TAXAS_VARIAVEIS` — custo do
    produto, comissão, frete e NF, medidos em 17.793 vendas. O custo
    operacional entra ao lado delas, como mais uma taxa.
    """
    variavel = sum(float(v) for v in (taxas_medidas or {}).values())
    return 1.0 - variavel - max(0.0, float(taxa_op or 0.0))


def numerador(custo_fixo=0.0, assinaturas=0.0, gerencia=0.0, headcount=0.0,
              teto_outros=0.0):
    """O custo que não varia com a venda, somado.

    `headcount` entra como ZERO no equilíbrio de hoje — enquanto a Reserva
    cobre, quem paga a folha do quadro é a verba aplicada, e não a operação.
    Quem quer o outro número chama de novo com ele preenchido.
    """
    return round(sum(max(0.0, float(v or 0.0)) for v in
                     (custo_fixo, assinaturas, gerencia, headcount,
                      teto_outros)), 2)


def equilibrio(num, marg):
    """O faturamento que zera o resultado. None quando não há margem.

    Margem zero ou negativa não tem equilíbrio: cada venda a mais aumenta o
    prejuízo, e nenhum faturamento paga a conta. Devolver um número enorme
    daria a impressão de que basta vender mais.
    """
    try:
        m = float(marg)
        n = max(0.0, float(num or 0.0))
    except (TypeError, ValueError):
        return None
    if m <= 0:
        return None
    return round(n / m, 2)


def montar(resumo_por_finalidade, faturamento, taxas_medidas,
           custo_fixo=0.0, assinaturas=0.0, gerencia=0.0, headcount=0.0,
           teto_outros=0.0):
    """Tudo de uma vez: os dois lados, as duas linhas e o que falta subir.

    Devolve um dicionário só, porque a tela precisa dos números E da origem
    deles. Número sem origem é número que ninguém consegue conferir.
    """
    lados, desconhecidas = separar(resumo_por_finalidade)
    # SÓ o balde operacional entra na taxa. O que já está na margem medida
    # fica de fora daqui — contá-lo de novo derruba a margem e infla o
    # equilíbrio, que é o erro mais caro que esta conta pode cometer.
    t_op = taxa_operacional(lados["operacional"], faturamento)
    m = margem(taxas_medidas, t_op)

    num_hoje = numerador(custo_fixo, assinaturas, gerencia, 0.0, teto_outros)
    num_depois = numerador(custo_fixo, assinaturas, gerencia, headcount,
                           teto_outros)

    hoje = equilibrio(num_hoje, m)
    depois = equilibrio(num_depois, m)
    caixa = equilibrio(num_hoje + lados["segunda_linha"], m)

    return {
        "margem": round(m, 4),
        "taxa_operacional": round(t_op, 4),
        "numerador_hoje": num_hoje,
        "numerador_com_headcount": num_depois,
        "equilibrio_hoje": hoje,
        "equilibrio_com_headcount": depois,
        "equilibrio_de_caixa": caixa,
        "falta_subir": (round(depois - hoje, 2)
                        if (hoje is not None and depois is not None) else None),
        "segunda_linha": lados["segunda_linha"],
        "gasto_operacional": lados["operacional"],
        "ja_na_margem": lados["ja_na_margem"],
        "fora_da_conta": lados["fora"],
        "desconhecidas": desconhecidas,
        "partes": {"custo fixo": round(float(custo_fixo or 0), 2),
                   "assinaturas": round(float(assinaturas or 0), 2),
                   "folha gerência": round(float(gerencia or 0), 2),
                   "teto de outros": round(float(teto_outros or 0), 2),
                   "folha headcount": round(float(headcount or 0), 2)},
    }


# ── Conferência ──────────────────────────────────────────────────────────────
# `python3 composicao.py`. Os números vêm da planilha do dono (DIN FINANÇAS,
# jan-ago/2026) e das taxas medidas em 17.793 vendas.
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    TAXAS = {"custo do produto": 0.3595, "comissão": 0.1892,
             "frete": 0.0759, "NF": 0.0772}

    # ── de que lado cai cada finalidade ──────────────────────────────────
    ok("custo fixo é numerador", lado("CUSTO FIXO") == "numerador")
    ok("assinatura é numerador", lado("SERVIÇO") == "numerador")
    ok("embalagem é custo operacional — o dono mudou de ideia e está certo",
       lado("EMBALAGEM") == "operacional")
    ok("FLEX é operacional: varia com a venda e com o destino",
       lado("FLEX") == "operacional")
    ok("ADS é operacional", lado("ADS") == "operacional")

    # A DISTINÇÃO QUE DECIDE A CONTA INTEIRA.
    ok("mercadoria JÁ ESTÁ na margem medida",
       lado("MERCADORIA") == "ja_na_margem")
    ok("imposto também — é a NF dos 7,72%",
       lado("IMPOSTO") == "ja_na_margem")
    ok("o repasse das plataformas também — é a comissão dos 18,92%",
       lado("MERCADO LIVRE") == "ja_na_margem"
       and lado("SHOPEE") == "ja_na_margem")

    ok("PRONAMP é 2ª linha", lado("NÃO OPERACIONAL") == "segunda_linha")
    ok("transferência entre contas fica FORA",
       lado("TRANSFERENCIA ENTRE CONTAS") == "fora")
    ok("aplicação fica fora — é investimento, não gasto",
       lado("APLICACAO") == "fora")
    ok("acento não muda o lado", lado("SERVICO") == lado("SERVIÇO"))
    ok("minúscula também não", lado("mercadoria") == "ja_na_margem")
    ok("finalidade nova cai em DESCONHECIDA, e não num lado qualquer",
       lado("CRIPTOMOEDA") == "desconhecida")

    # ── separar, com o sinal que o extrato usa ───────────────────────────
    RESUMO = {"MERCADORIA": -41773.23, "EMBALAGEM": -2271.69,
              "CUSTO FIXO": -22842.00, "SERVIÇO": -897.04,
              "FLEX": -2099.85, "OUTROS": -1627.98,
              "NÃO OPERACIONAL": -15512.93,
              "TRANSFERENCIA ENTRE CONTAS": -80000.00,
              "XPTO NOVA": -1234.00}
    lados, desc = separar(RESUMO)
    ok("saída negativa entra como módulo", lados["numerador"] > 0)
    ok("o numerador soma custo fixo e serviço",
       abs(lados["numerador"] - (22842.00 + 897.04)) < 0.01)
    ok("o operacional soma embalagem, flex e outros",
       abs(lados["operacional"] - (2271.69 + 2099.85 + 1627.98)) < 0.01)
    ok("mercadoria vai para o balde do que já está na margem",
       lados["ja_na_margem"] == 41773.23)
    ok("a 2ª linha fica separada", lados["segunda_linha"] == 15512.93)
    ok("transferência não entra em lado nenhum da conta",
       lados["fora"] == 80000.00)
    ok("a finalidade nova é DEVOLVIDA para aparecer na tela",
       desc and desc[0][0] == "XPTO NOVA")

    # ── a taxa operacional ───────────────────────────────────────────────
    # Janeiro real: C.O.P.M 14.266,34 sobre faturamento 205.891,79 = 6,93%.
    ok("a taxa operacional de janeiro dá 6,93%",
       abs(taxa_operacional(14266.34, 205891.79) - 0.0693) < 0.0001)
    ok("faturamento zero não vira divisão por zero",
       taxa_operacional(1000, 0) == 0.0)

    # ── a margem ─────────────────────────────────────────────────────────
    ok("sem custo operacional a margem é a medida, 29,82%",
       abs(margem(TAXAS) - 0.2982) < 0.0001)
    ok("com 6,93% de operacional ela cai para ~22,9%",
       abs(margem(TAXAS, 0.0693) - 0.2289) < 0.0001)

    # ── o equilíbrio ─────────────────────────────────────────────────────
    ok("o equilíbrio é numerador ÷ margem",
       equilibrio(39338.0, 0.2982) == round(39338.0 / 0.2982, 2))
    ok("margem zero não tem equilíbrio", equilibrio(1000, 0) is None)
    ok("margem negativa também não", equilibrio(1000, -0.1) is None)
    ok("numerador zero dá equilíbrio zero", equilibrio(0, 0.3) == 0.0)

    # ── o mês real, montado inteiro ──────────────────────────────────────
    r = montar(RESUMO, 205891.79, TAXAS, custo_fixo=22842.0,
               assinaturas=2350.35, gerencia=22000.0, headcount=9900.0)
    ok("a margem do mês fica entre 25% e 29%", 0.25 < r["margem"] < 0.29)
    ok("o que já está na margem NÃO entra na taxa operacional",
       r["taxa_operacional"] < 0.04)
    ok("o equilíbrio de hoje NÃO tem o Headcount dentro",
       r["numerador_hoje"] == round(22842.0 + 2350.35 + 22000.0, 2))
    ok("e o de depois tem", r["numerador_com_headcount"]
       == round(r["numerador_hoje"] + 9900.0, 2))
    ok("o de depois é maior", r["equilibrio_com_headcount"] > r["equilibrio_hoje"])
    ok("e o 'falta subir' é a diferença entre os dois",
       abs(r["falta_subir"] - (r["equilibrio_com_headcount"]
                               - r["equilibrio_hoje"])) < 0.01)
    ok("o equilíbrio de caixa inclui o PRONAMP e é o maior de todos",
       r["equilibrio_de_caixa"] > r["equilibrio_hoje"])

    # A ARMADILHA: contar de novo o que já está na margem.
    _errado = equilibrio(r["numerador_hoje"],
                         margem(TAXAS, taxa_operacional(
                             r["gasto_operacional"] + r["ja_na_margem"],
                             205891.79)))
    ok("contar a mercadoria duas vezes infla o equilíbrio em mais de R$ 100 mil",
       _errado - r["equilibrio_hoje"] > 100_000)

    # ── bordas ───────────────────────────────────────────────────────────
    _vazio, _d = separar({})
    ok("resumo vazio não quebra", sum(_vazio.values()) == 0.0 and _d == [])
    ok("sem faturamento a margem cai para a medida",
       abs(montar(RESUMO, 0, TAXAS)["margem"] - 0.2982) < 0.0001)
    ok("None em valor não derruba", separar({"CUSTO FIXO": None})[0] is not None)
    ok("texto impossível não derruba",
       separar({"CUSTO FIXO": "abc"})[0]["numerador"] == 0.0)

    print("\nfalhas:", falhas)
    raise SystemExit(falhas)
