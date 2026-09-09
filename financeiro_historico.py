"""financeiro_historico.py — O que se espera do mês, medido em três anos.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
O indicador de Faturamento precisa responder uma pergunta com o mês ainda
aberto: *"estamos abaixo, dentro ou acima do esperado para este ponto do mês?"*

Responder isso exige três coisas, e nenhuma delas é opinião:

  1. quanto vale cada mês do ano em relação aos outros  (dezembro rende 1,40
     mês médio; abril, 0,77) — o INDICE_SAZONAL;
  2. quanto do mês já deveria estar faturado no dia N   (no dia 15, 51,8%) —
     a CURVA_DO_MES;
  3. quanto a projeção erra quando feita no dia N       (7,2% em média no dia
     15, 15,4% nos 10% piores) — o ERRO_PROJECAO.

Os três saíram do faturamento DIÁRIO de 2023, 2024 e 2025 — 1.096 dias, 36
meses completos, R$ 6.060.455 no total. O script que os gera é o
`gerar_params_historico.py`, ao lado.

POR QUE OS NÚMEROS ESTÃO CHUMBADOS AQUI, E NÃO CALCULADOS
----------------------------------------------------------
São 43 números que mudam uma vez por ano, quando um ano fecha. O histórico
mora em quatro arquivos de 12 MB no OneDrive, e o Studio lê Google Sheets.
Montar uma leitura de xlsx no Studio para derivar 43 constantes seria trocar um
incômodo pequeno por um permanente: mais uma dependência externa, mais um lugar
para quebrar, e uma tela mais lenta em troca de nada.

Quando 2026 fechar: roda o script, cola os números novos, e a linha do
histórico neste arquivo vira 2023-2026.

O ERRO É PARTE DO NÚMERO
------------------------
A projeção não vira um valor, vira uma FAIXA. O erro médio no dia 15 é 7,2%,
mas os 10% piores erram 15,4%, e o pior mês dos 36 errou 27,5%. Mostrar só a
média produziria um painel que acerta quase sempre e erra feio de vez em
quando — e é o "de vez em quando" que faz alguém parar de confiar no número.

Os erros foram medidos com leave-one-out: a curva usada para projetar um mês é
construída SEM aquele mês. Sem isso o teste mediria a memória da conta, não a
capacidade de prever.
"""

# ── Medido: faturamento anual (TT FAT - DEV, líquido de devolução) ───────────
TOTAL_ANUAL = {
    2023: 1_415_288.91,
    2024: 1_922_229.79,
    2025: 2_722_936.68,
}

# Crescimento de um ano para o outro.
CRESCIMENTO = {
    2024: 0.3582,
    2025: 0.4166,
}

# ── Medido: peso de cada mês (1,00 = mês médio do ano) ──────────────────────
# O comentário e o desvio entre os tres anos: quanto eles discordam. Maio e
# junho sao os mais previsiveis; outubro e o mais bagunçado.
INDICE_SAZONAL = {
     1: 0.9964,   # ±0.126
     2: 0.9084,   # ±0.076
     3: 0.8265,   # ±0.058
     4: 0.7685,   # ±0.098
     5: 0.8274,   # ±0.026
     6: 0.9048,   # ±0.028
     7: 0.9868,   # ±0.105
     8: 0.9587,   # ±0.110
     9: 0.9841,   # ±0.096
    10: 1.1656,   # ±0.144
    11: 1.2762,   # ±0.075
    12: 1.3966,   # ±0.119
}

# ── Medido: fração do mês já faturada ao fim do dia N ───────────────────────
# (média dos 36 meses, desvio entre eles)
CURVA_DO_MES = {
     1: (0.0302, 0.0079),   2: (0.0614, 0.0132),   3: (0.0949, 0.0191),
     4: (0.1318, 0.0252),   5: (0.1681, 0.0281),   6: (0.2050, 0.0292),
     7: (0.2425, 0.0286),   8: (0.2775, 0.0303),   9: (0.3136, 0.0356),
    10: (0.3506, 0.0381),  11: (0.3867, 0.0409),  12: (0.4191, 0.0439),
    13: (0.4540, 0.0459),  14: (0.4868, 0.0468),  15: (0.5184, 0.0461),
    16: (0.5520, 0.0491),  17: (0.5860, 0.0505),  18: (0.6179, 0.0518),
    19: (0.6528, 0.0527),  20: (0.6839, 0.0521),  21: (0.7143, 0.0495),
    22: (0.7451, 0.0475),  23: (0.7743, 0.0445),  24: (0.8043, 0.0406),
    25: (0.8336, 0.0384),  26: (0.8636, 0.0358),  27: (0.8944, 0.0351),
    28: (0.9249, 0.0315),  29: (0.9513, 0.0229),  30: (0.9811, 0.0174),
    31: (1.0000, 0.0000),
}

# ── Medido: erro da projeção feita no dia N (média, percentil 90) ───────────
ERRO_PROJECAO = {
     1: (0.2301, 0.4461),   2: (0.1807, 0.3784),   3: (0.1773, 0.3371),
     4: (0.1667, 0.2932),   5: (0.1376, 0.3034),   6: (0.1169, 0.2483),
     7: (0.1009, 0.1727),   8: (0.0923, 0.1880),   9: (0.1004, 0.2031),
    10: (0.0949, 0.1731),  11: (0.0887, 0.1715),  12: (0.0859, 0.1639),
    13: (0.0827, 0.1737),  14: (0.0764, 0.1643),  15: (0.0717, 0.1536),
    16: (0.0703, 0.1467),  17: (0.0685, 0.1328),  18: (0.0665, 0.1217),
    19: (0.0637, 0.1159),  20: (0.0626, 0.1191),  21: (0.0571, 0.1203),
    22: (0.0517, 0.1073),  23: (0.0475, 0.0883),  24: (0.0415, 0.0752),
    25: (0.0384, 0.0732),  26: (0.0350, 0.0775),  27: (0.0326, 0.0701),
    28: (0.0283, 0.0630),  29: (0.0226, 0.0512),  30: (0.0168, 0.0227),
    31: (0.0000, 0.0000),
}

# O ano mais recente que fechou e entrou nas contas acima.
ULTIMO_ANO_FECHADO = max(TOTAL_ANUAL)


def _limitar_dia(dia):
    """Dia dentro de 1..31. Mês de 30 dias no dia 30 já é o fechamento."""
    try:
        return max(1, min(31, int(dia)))
    except (TypeError, ValueError):
        return 1


def crescimento_medio():
    """Crescimento anual médio observado. Base do que se espera do ano novo."""
    vs = list(CRESCIMENTO.values())
    return sum(vs) / len(vs) if vs else 0.0


def estimativa_anual(ano, crescimento=None):
    """Faturamento esperado para o ano, a partir do último ano fechado.

    `crescimento` permite substituir o observado — é o campo que o gestor
    mexe quando sabe de algo que o histórico não sabe (uma meta nova, um canal
    que entrou, um que saiu). Sem ele, usa a média medida.
    """
    if crescimento is None:
        crescimento = crescimento_medio()
    base = TOTAL_ANUAL[ULTIMO_ANO_FECHADO]
    anos = max(0, int(ano) - ULTIMO_ANO_FECHADO)
    return base * ((1.0 + crescimento) ** anos)


def esperado_do_mes(ano, mes, base_anual=None, crescimento=None):
    """Quanto se espera faturar no mês inteiro."""
    if base_anual is None:
        base_anual = estimativa_anual(ano, crescimento)
    return (base_anual / 12.0) * INDICE_SAZONAL.get(int(mes), 1.0)


def esperado_ate_o_dia(ano, mes, dia, base_anual=None, crescimento=None):
    """Quanto já deveria estar faturado ao fim do dia N do mês."""
    fracao = CURVA_DO_MES[_limitar_dia(dia)][0]
    return esperado_do_mes(ano, mes, base_anual, crescimento) * fracao


def projetar_fechamento(realizado, dia):
    """Onde o mês fecha, a partir do que já foi faturado. (proj, piso, teto).

    O piso e o teto vêm do erro medido no percentil 90 daquele dia: em 9 de
    cada 10 meses o fechamento cai dentro dessa faixa. No dia 5 ela é larga de
    propósito — projetar um mês com cinco dias É impreciso, e a faixa dizer
    isso é mais honesto do que um número redondo que finge precisão.
    """
    d = _limitar_dia(dia)
    fracao = CURVA_DO_MES[d][0]
    if fracao <= 0:
        return (0.0, 0.0, 0.0)
    proj = float(realizado) / fracao
    p90 = ERRO_PROJECAO[d][1]
    return (proj, proj * (1.0 - p90), proj * (1.0 + p90))


def posicao(realizado, dia, ano, mes, base_anual=None, crescimento=None):
    """'abaixo' | 'dentro' | 'acima' — e os números que sustentam a resposta.

    A comparação é entre a PROJEÇÃO DE FECHAMENTO e o esperado do mês, não
    entre o realizado de hoje e o esperado de hoje. Os dois respondem coisas
    diferentes: o segundo diz onde você está, o primeiro diz onde vai dar — e
    é o primeiro que ainda dá tempo de mudar.

    'dentro' quando o esperado cabe na faixa da projeção: enquanto couber, a
    diferença não se distingue do erro do próprio método, e apontar direção
    seria inventar precisão.
    """
    esperado = esperado_do_mes(ano, mes, base_anual, crescimento)
    proj, piso, teto = projetar_fechamento(realizado, dia)
    if esperado <= 0:
        situacao = "indefinido"
    elif piso > esperado:
        situacao = "acima"
    elif teto < esperado:
        situacao = "abaixo"
    else:
        situacao = "dentro"
    return {
        "situacao": situacao,
        "realizado": float(realizado),
        "esperado_mes": esperado,
        "esperado_hoje": esperado_ate_o_dia(ano, mes, dia, base_anual, crescimento),
        "projecao": proj,
        "projecao_piso": piso,
        "projecao_teto": teto,
        "fracao_do_mes": CURVA_DO_MES[_limitar_dia(dia)][0],
        "erro_medio_do_dia": ERRO_PROJECAO[_limitar_dia(dia)][0],
    }


# ── Conferência ──────────────────────────────────────────────────────────────
# `python3 financeiro_historico.py`. Os casos moram aqui porque este
# repositório não tem suíte: teste que não viaja junto do código é teste que
# ninguém roda.
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    ok("os 12 meses do índice existem", sorted(INDICE_SAZONAL) == list(range(1, 13)))
    ok("os 31 dias da curva existem", sorted(CURVA_DO_MES) == list(range(1, 32)))
    ok("os 31 dias do erro existem", sorted(ERRO_PROJECAO) == list(range(1, 32)))
    ok("o índice sazonal soma 12 (é uma média de 1,00)",
       abs(sum(INDICE_SAZONAL.values()) - 12) < 0.02)
    ok("a curva termina em 100%", CURVA_DO_MES[31][0] == 1.0)
    ok("a curva só sobe",
       all(CURVA_DO_MES[d][0] < CURVA_DO_MES[d + 1][0] for d in range(1, 31)))
    ok("o erro da projeção só diminui ao longo do mês",
       ERRO_PROJECAO[5][0] > ERRO_PROJECAO[15][0] > ERRO_PROJECAO[25][0])

    ok("dezembro pesa mais que abril", INDICE_SAZONAL[12] > INDICE_SAZONAL[4])
    ok("no dia 15 espera-se pouco mais da metade do mês",
       0.50 < CURVA_DO_MES[15][0] < 0.53)

    # 2026 a partir de 2025 (2.722.937) com crescimento medio de 38,74%
    a26 = estimativa_anual(2026)
    ok("2026 estimado fica entre 3,7 e 3,9 milhões", 3_700_000 < a26 < 3_900_000)
    ok("2027 estimado é 2 anos de crescimento",
       abs(estimativa_anual(2027) - a26 * (1 + crescimento_medio())) < 1)

    dez = esperado_do_mes(2026, 12, base_anual=3_774_000)
    abr = esperado_do_mes(2026, 4, base_anual=3_774_000)
    ok("dezembro esperado > abril esperado", dez > abr)
    ok("dezembro esperado bate com índice × média mensal",
       abs(dez - (3_774_000 / 12) * INDICE_SAZONAL[12]) < 1)

    # Um mes que vai fechar exatamente no esperado
    esp = esperado_do_mes(2026, 9, base_anual=3_774_000)
    meio = esp * CURVA_DO_MES[15][0]
    r = posicao(meio, 15, 2026, 9, base_anual=3_774_000)
    ok("no ritmo exato, a projeção bate com o esperado",
       abs(r["projecao"] - esp) < 1)
    ok("no ritmo exato, a situação é 'dentro'", r["situacao"] == "dentro")

    r_alto = posicao(meio * 1.4, 15, 2026, 9, base_anual=3_774_000)
    ok("40% acima do ritmo é 'acima'", r_alto["situacao"] == "acima")
    r_baixo = posicao(meio * 0.6, 15, 2026, 9, base_anual=3_774_000)
    ok("40% abaixo do ritmo é 'abaixo'", r_baixo["situacao"] == "abaixo")
    r_pouco = posicao(meio * 1.08, 15, 2026, 9, base_anual=3_774_000)
    ok("8% acima no dia 15 ainda é 'dentro' (cabe no erro do método)",
       r_pouco["situacao"] == "dentro")

    r5 = posicao(esp * CURVA_DO_MES[5][0] * 1.08, 5, 2026, 9, base_anual=3_774_000)
    ok("os mesmos 8% no dia 5 também são 'dentro', com faixa mais larga",
       r5["situacao"] == "dentro"
       and (r5["projecao_teto"] - r5["projecao_piso"])
           > (r_pouco["projecao_teto"] - r_pouco["projecao_piso"]))

    ok("dia fora da faixa não derruba", posicao(1000, 99, 2026, 9)["situacao"] != "")
    ok("dia ilegível não derruba", posicao(1000, None, 2026, 9)["situacao"] != "")
    ok("realizado zero projeta zero e fica 'abaixo'",
       posicao(0, 15, 2026, 9, base_anual=3_774_000)["situacao"] == "abaixo")

    print("\nfalhas:", falhas)
