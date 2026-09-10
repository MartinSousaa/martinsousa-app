"""financeiro_equilibrio.py — Quanto precisa faturar para não dar prejuízo.

A CONTA
-------
    faturamento de equilíbrio  =  custo que não varia  ÷  margem de contribuição

A margem de contribuição é o que sobra de cada real faturado depois dos custos
que acompanham a venda. Foi MEDIDA na `BASE DE VENDAS 2026` — 17.793 vendas,
janeiro a agosto — e não estimada:

    custo do produto   35,95%   (±2,00 pp)
    comissão           18,92%   (±2,46 pp)
    frete               7,59%   (±1,52 pp)
    NF                  7,72%   (±0,11 pp)
    ─────────────────────────
    variável           70,18%   →  margem de contribuição 29,82%

DUAS LINHAS, NÃO UMA
--------------------
Os PRONAMPs (R$ 15.513/mês) são parcelas de empréstimo: saem do caixa, mas não
são custo de operar. Incluir ou não muda a resposta em R$ 52 mil, e a escolha
depende da pergunta que se está fazendo. Em vez de escolher por ele, este
módulo devolve as duas e o painel mostra as duas:

    equilíbrio OPERACIONAL   a operação se paga
    equilíbrio DE CAIXA      a operação se paga E as parcelas saem

SOBRE QUAL FATURAMENTO
----------------------
As taxas foram calculadas contra `FAT TOTAL` da base — que inclui o frete
cobrado do cliente, e é o que o Bling devolve no campo `total` do pedido. Usar
`Total dos Produtos` daria taxas 3% maiores e uma margem que não bate com o
número que chega da API. As duas pontas precisam falar da mesma coisa.

O QUE ESTE MÓDULO NÃO SABE
--------------------------
Compra de mercadoria não é custo da mercadoria vendida. Em 2026 a COMPRA
(mercadoria + embalagem) foi 42,7% do faturamento, enquanto o CUSTO DO VENDIDO
foi 35,95%. A diferença é estoque subindo. Para equilíbrio vale o custo do
vendido, que é o que está aqui; para fluxo de caixa valeria a compra — e essa é
outra conta, que ainda não existe.
"""

# ── Medido: BASE DE VENDAS 2026, jan-ago, 17.793 vendas ─────────────────────
# Cada taxa como fracao do FAT TOTAL. O comentario e o desvio entre os 8 meses.
TAXAS_VARIAVEIS = {
    "custo do produto": 0.3595,   # ±0.0200
    "comissão":         0.1892,   # ±0.0246
    "frete":            0.0759,   # ±0.0152
    "NF":               0.0772,   # ±0.0011
}

# ── Medido: aba CUSTOS FIXOS do Controle_MS ─────────────────────────────────
# Foto do mes vigente — a aba nao tem coluna de mes, entao nao ha historico.
# Por isso os dois entram como PADRAO e nao como verdade: toda funcao daqui
# aceita o valor por parametro, e a tela vai deixar o gestor informar o do mes.
CUSTO_FIXO_OPERACIONAL = 29838.0   # 17 itens: salarios, alugueis, Bling, contabilidade
CUSTO_NAO_OPERACIONAL = 15513.0    # 7 PRONAMPs

# Media medida dos gastos discricionarios de 2026 (OUTROS, SERVICOS, LIMPEZA,
# ESTACIONAMENTO fora do fixo). E um TETO que o gestor define, nao uma
# previsao: ele mesmo disse que consegue limitar esses gastos. Enquanto nao
# definir, a media serve de ponto de partida.
TETO_OUTROS_PADRAO = 9500.0


def margem_de_contribuicao(taxas=None):
    """Quanto sobra de cada real faturado. 0.2982 com as taxas medidas."""
    t = TAXAS_VARIAVEIS if taxas is None else taxas
    return 1.0 - sum(t.values())


def faturamento_de_equilibrio(custo_fixo, margem=None):
    """Faturamento que zera o resultado para esse custo fixo.

    Margem zero ou negativa não tem equilíbrio: nenhum faturamento paga a
    conta, porque cada venda a mais aumenta o prejuízo. Devolve None, e quem
    mostra na tela precisa dizer isso em vez de imprimir infinito.
    """
    m = margem_de_contribuicao() if margem is None else margem
    if m <= 0:
        return None
    try:
        return max(0.0, float(custo_fixo)) / m
    except (TypeError, ValueError):
        return None


def linhas_de_equilibrio(custo_fixo=None, nao_operacional=None,
                         teto_outros=None, margem=None):
    """As duas linhas: operacional e de caixa. Sempre as duas."""
    cf = CUSTO_FIXO_OPERACIONAL if custo_fixo is None else float(custo_fixo)
    no = CUSTO_NAO_OPERACIONAL if nao_operacional is None else float(nao_operacional)
    ou = TETO_OUTROS_PADRAO if teto_outros is None else float(teto_outros)
    m = margem_de_contribuicao() if margem is None else margem
    return {
        "margem": m,
        "custo_fixo": cf,
        "outros": ou,
        "nao_operacional": no,
        "operacional": faturamento_de_equilibrio(cf + ou, m),
        "caixa": faturamento_de_equilibrio(cf + ou + no, m),
    }


def _onde_cai(piso, teto, linha):
    """'acima' | 'abaixo' | 'na faixa' — a faixa da projeção contra uma linha.

    'na faixa' quando a linha cai dentro da projeção: aí a diferença não se
    distingue do erro do método, e afirmar direção seria inventar precisão.
    """
    if linha is None:
        return "sem margem"
    if piso > linha:
        return "acima"
    if teto < linha:
        return "abaixo"
    return "na faixa"


def avaliar(realizado, dia, custo_fixo=None, nao_operacional=None,
            teto_outros=None, margem=None):
    """O indicador: onde o mês vai fechar, contra as duas linhas.

    `realizado` é o faturamento do mês até hoje — o número que vem do Bling.
    A projeção vem do `financeiro_historico`, que mede quanto do mês já
    costuma estar faturado no dia N e quanto essa projeção erra.
    """
    import financeiro_historico as _fh
    proj, piso, teto = _fh.projetar_fechamento(realizado, dia)
    linhas = linhas_de_equilibrio(custo_fixo, nao_operacional, teto_outros, margem)
    linhas.update({
        "realizado": float(realizado),
        "projecao": proj,
        "projecao_piso": piso,
        "projecao_teto": teto,
        "situacao_operacional": _onde_cai(piso, teto, linhas["operacional"]),
        "situacao_caixa": _onde_cai(piso, teto, linhas["caixa"]),
        "sobra_operacional": (proj - linhas["operacional"]) if linhas["operacional"] else None,
        "sobra_caixa": (proj - linhas["caixa"]) if linhas["caixa"] else None,
    })
    return linhas


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    m = margem_de_contribuicao()
    ok("margem medida fica em 29,8%", abs(m - 0.2982) < 0.0001)
    ok("as quatro taxas somam 70,18%", abs(sum(TAXAS_VARIAVEIS.values()) - 0.7018) < 1e-9)

    ok("equilíbrio é custo ÷ margem",
       abs(faturamento_de_equilibrio(29838.0) - 29838.0 / m) < 0.01)
    ok("margem zero não tem equilíbrio",
       faturamento_de_equilibrio(1000, margem=0) is None)
    ok("margem negativa não tem equilíbrio",
       faturamento_de_equilibrio(1000, margem=-0.1) is None)
    ok("custo ilegível não derruba", faturamento_de_equilibrio("abc") is None)
    ok("custo zero dá equilíbrio zero", faturamento_de_equilibrio(0) == 0.0)

    L = linhas_de_equilibrio()
    ok("operacional fica em ~R$ 132 mil", 131_000 < L["operacional"] < 133_000)
    ok("caixa fica em ~R$ 184 mil", 183_000 < L["caixa"] < 185_000)
    ok("caixa é sempre maior que operacional", L["caixa"] > L["operacional"])
    ok("os PRONAMPs pesam ~R$ 52 mil na linha",
       50_000 < (L["caixa"] - L["operacional"]) < 54_000)

    # Setembro real: R$ 83.854 ate o dia 10, as duas contas
    r = avaliar(83854, 10)
    ok("setembro projeta ~R$ 239 mil", 238_000 < r["projecao"] < 241_000)
    ok("setembro fecha acima do equilíbrio operacional",
       r["situacao_operacional"] == "acima")
    ok("setembro fecha acima do equilíbrio de caixa",
       r["situacao_caixa"] == "acima")
    ok("a sobra sobre o caixa é positiva", r["sobra_caixa"] > 0)

    # Um mes fraco: mesma projecao, custo fixo dobrado
    r2 = avaliar(83854, 10, custo_fixo=70000)
    ok("com custo fixo alto, a linha sobe e a situação muda",
       r2["operacional"] > L["operacional"]
       and r2["situacao_operacional"] in ("na faixa", "abaixo"))

    r3 = avaliar(20000, 10)
    ok("faturamento baixo fica abaixo das duas linhas",
       r3["situacao_operacional"] == "abaixo" and r3["situacao_caixa"] == "abaixo")

    r4 = avaliar(83854, 10, margem=0)
    ok("sem margem, o painel diz 'sem margem' em vez de imprimir infinito",
       r4["situacao_operacional"] == "sem margem" and r4["operacional"] is None)

    ok("dia ilegível não derruba", avaliar(83854, None)["projecao"] >= 0)
    ok("as duas linhas sempre vêm juntas",
       "operacional" in r and "caixa" in r)

    print("\nfalhas:", falhas)
