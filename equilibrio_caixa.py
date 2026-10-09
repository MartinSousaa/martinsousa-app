"""equilibrio_caixa.py — quanto faturar para o dinheiro cobrir o que sai.

A CONTA, DITADA PELO DONO
-------------------------
    faturamento necessário  =  meta de gastos  ÷  o que cai na conta

*"Se eu coloquei como meta de gastos 170k… tenho os custos fixos, cheques, no
extrato dos cartões mostram o valor parcial… o que é variável que ainda será
gasto, tanto quanto compra de mercadoria, nós iremos olhar o quanto temos
disponível e priorizar."*

A meta de gastos é TUDO o que sai no mês. Então a pergunta é de CAIXA, e o
divisor não é margem de lucro nenhuma: é a fatia do faturamento que sobrevive
até a conta bancária.

POR QUE NÃO É A MARGEM BRUTA
-----------------------------
Tentei dividir pela margem bruta e a conta não fechava — a mercadoria entrava
duas vezes: uma dentro da meta de gastos (o cheque, o PIX do fornecedor) e
outra já descontada dentro da margem. Dividindo pela entrada de caixa isso
desaparece, porque a mercadoria não é descontada em lugar nenhum do divisor;
ela está inteira, uma vez só, no numerador.

De quebra, some a dependência da coluna `L.B` da planilha, que eu não consegui
reproduzir: `FAT − CUSTO TOTAL` bate em 325 das 17.792 linhas. Um número que
não se consegue refazer não pode ser o divisor de uma meta.

O QUE A PLATAFORMA TIRA ANTES — medido em jun–ago/2026
-------------------------------------------------------
    faturamento       R$ 776.478,55   100,0%
    − comissão        R$ 127.512,06    16,4%
    − frete           R$  60.045,61     7,7%
    − NF / imposto    R$  60.879,32     7,8%
    − devoluções      R$  21.471,76     2,8%
    = cai na conta    R$ 506.569,80    65,2%

    R$ 170.000 ÷ 65,2%  =  R$ 260.579 de faturamento necessário

A Home mostrava R$ 34.865. Com a meta certa, o faturado de R$ 178.618 no dia
23 deixa de estar R$ 151 mil ACIMA do ritmo e passa a estar R$ 18 mil ABAIXO.
A leitura vira o oposto — e era essa a leitura que decidia comprar.

A META DO DIA É PROPORCIONAL AO TEMPO DECORRIDO
------------------------------------------------
*"Pegando os 260k e dividir por 22 dias fechados e mais 17h do dia de hoje eu
deveria ter faturado até aqui XXX,XX."* Dias corridos, e a fração da hora do
dia de hoje — não o dia inteiro assim que ele começa, que é o que a tela fazia
e que deixava a manhã sempre parecendo atrasada.
"""

from datetime import datetime, timezone, timedelta

FUSO = timezone(timedelta(hours=-3))

# O que a plataforma tira do faturamento antes de o dinheiro chegar. São as
# colunas da BASE DE VENDAS, e nada além delas: o que sai DEPOIS de cair na
# conta já está dentro da meta de gastos e não pode ser descontado aqui.
DESCONTOS = ("comissao", "frete", "nf", "devolucao")

ROTULOS = {"comissao": "comissão", "frete": "frete", "nf": "NF / imposto",
           "devolucao": "devoluções"}

# Piso de sanidade. Uma taxa de entrada abaixo disto significa que a leitura
# da planilha veio torta — e dividir por um número pequeno explode a meta em
# vez de avisar. Em jun–ago/2026 a taxa medida foi 65,2%.
TAXA_MINIMA = 0.20


def _num(v, padrao=0.0):
    if v is None or v == "":
        return padrao
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace("R$", "").replace(" ", "")
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return padrao


def taxa_de_entrada(somas):
    """Quanto de cada real faturado cai na conta. (taxa, linhas, aviso).

    `somas` é o dicionário do `base_vendas.somar`. `linhas` traz cada desconto
    com valor e percentual, para a tela poder mostrar a conta inteira — número
    sem a conta ao lado é número que ninguém confere.
    """
    fat = _num(somas.get("faturamento") if somas else 0)
    if fat <= 0:
        return None, [], ("Sem faturamento na BASE DE VENDAS não dá para medir "
                          "quanto do faturamento cai na conta.")
    linhas, total = [], 0.0
    for c in DESCONTOS:
        v = abs(_num((somas or {}).get(c)))
        total += v
        linhas.append({"nome": ROTULOS[c], "valor": round(v, 2),
                       "pct": round(100.0 * v / fat, 1)})
    liquido = fat - total
    taxa = liquido / fat
    aviso = ""
    if taxa < TAXA_MINIMA:
        aviso = (f"A entrada de caixa medida ficou em {100 * taxa:.1f}%, abaixo "
                 f"do piso de {100 * TAXA_MINIMA:.0f}%. Isso quase sempre é "
                 "leitura torta da planilha, não o negócio — a meta não vai "
                 "ser calculada por cima disso.")
        return None, linhas, aviso
    return round(taxa, 4), linhas, aviso


def faturamento_necessario(meta_de_gastos, taxa):
    """meta ÷ taxa. None quando falta um dos dois.

    Sem taxa medida não se chuta: a Home prefere dizer que não sabe a mostrar
    uma meta plausível e errada — foi assim que R$ 34.865 ficou meses na tela
    parecendo número de verdade.
    """
    m = _num(meta_de_gastos)
    if not m or not taxa or taxa <= 0:
        return None
    return round(m / taxa, 2)


def fracao_do_mes(agora=None, dias_mes=None):
    """Quanto do mês já passou, contando a HORA de hoje. 0,0 a 1,0.

    22 dias fechados + 17h de hoje, num mês de 30, são 22,708 ÷ 30 = 0,757 —
    e não 23 ÷ 30 = 0,767. A diferença parece pequena no dia 23 e é enorme no
    dia 1º: às 9h da manhã do primeiro dia a tela cobrava um dia inteiro de
    faturamento que ainda não tinha tido como acontecer.
    """
    import calendar
    a = agora or datetime.now(FUSO)
    dias = int(dias_mes or calendar.monthrange(a.year, a.month)[1])
    fechados = a.day - 1
    do_dia = (a.hour * 3600 + a.minute * 60 + a.second) / 86400.0
    return min(max((fechados + do_dia) / dias, 0.0), 1.0)


def alvo_ate_agora(meta, agora=None, dias_mes=None):
    """A mini meta: a meta do mês vezes a fração do mês que já passou."""
    return round(_num(meta) * fracao_do_mes(agora, dias_mes), 2)


def projecao(realizado, agora=None, dias_mes=None):
    """Onde o mês fecha no ritmo de agora. None no primeiro instante do mês."""
    f = fracao_do_mes(agora, dias_mes)
    if f <= 0:
        return None
    return round(_num(realizado) / f, 2)


def situacao(realizado, meta, agora=None, dias_mes=None):
    """O quadro inteiro da meta de faturamento, pronto para a tela.

    {meta, alvo, realizado, diferenca, acima, fracao, projecao, fecha_a_meta}
    """
    alvo = alvo_ate_agora(meta, agora, dias_mes)
    r = _num(realizado)
    proj = projecao(r, agora, dias_mes)
    return {
        "meta": round(_num(meta), 2), "alvo": alvo, "realizado": round(r, 2),
        "diferenca": round(r - alvo, 2), "acima": r >= alvo,
        "fracao": round(fracao_do_mes(agora, dias_mes), 4),
        "projecao": proj,
        "fecha_a_meta": (proj is not None and proj >= _num(meta)),
    }


def montar(meta_de_gastos, somas, realizado, agora=None, dias_mes=None):
    """A meta de faturamento do mês, da meta de gastos até a mini meta de hoje.

    Devolve (quadro, avisos). `quadro` None quando não deu para medir a taxa —
    e aí o aviso diz o que faltou, em vez de a tela inventar um número.
    """
    avisos = []
    taxa, linhas, aviso = taxa_de_entrada(somas)
    if aviso:
        avisos.append(aviso)
    meta = faturamento_necessario(meta_de_gastos, taxa)
    if meta is None:
        if not _num(meta_de_gastos):
            avisos.append(
                "Sem **meta de gastos** cadastrada para o mês não há meta de "
                "faturamento: ela é a meta de gastos dividida pelo que cai na "
                "conta. Cadastre em Financeiro › Meta de gastos.")
        return None, avisos
    quadro = situacao(realizado, meta, agora, dias_mes)
    quadro["taxa_de_entrada"] = taxa
    quadro["descontos"] = linhas
    quadro["meta_de_gastos"] = round(_num(meta_de_gastos), 2)
    return quadro, avisos



def ponto_de_equilibrio(meta_gastos, margem_bruta_pct):
    """O faturamento que paga a meta de gastos do mês. None sem meta. Pura.

    Regra do dono, 07/10: "eu tenho que cadastrar a meta de gastos e esse
    valor precisa ser dividido pela nossa média de lucro bruto dos últimos 3
    meses, aí sim teremos o ponto de equilíbrio". A meta de gastos é TUDO o
    que sai no mês; o lucro bruto é o que sobra de cada real vendido.
    Sem meta cadastrada não há equilíbrio — a tela pede a meta, em vez de
    inventar um número com outra conta.
    """
    try:
        meta = float(meta_gastos or 0.0)
        mb = float(margem_bruta_pct or 0.0) / 100.0
    except (TypeError, ValueError):
        return None
    if meta <= 0 or mb <= 0:
        return None
    return round(meta / mb, 2)


def equilibrio_real(meta, gasto_real, origem_gasto, mapa_vendas, ano, mes):
    """O mês FECHADO, confrontado com a meta que se pôs no começo dele. Pura.

    Dono, 09/10: "se eu não bato a meta de faturamento com base na meta de
    gasto, eu preciso ter uma nova análise em cima daquilo que foi gasto e
    faturado, comparado com o ponto de equilíbrio real" — e o mês corrente
    não se mexe até fechar.

      planejado = meta ÷ % lucro bruto médio dos 3 meses ANTERIORES ao mês
                  (a régua de `ponto_de_equilibrio`, como estava no dia 1º)
      real      = o que saiu nos extratos ÷ % lucro bruto do PRÓPRIO mês
      resultado = faturamento líquido do mês − real

    Faturamento LÍQUIDO porque a margem é sobre ele (`base_vendas.indicadores`):
    comparar com o bruto mediria duas coisas diferentes. `mapa_vendas` é
    `base_vendas.somas_por_mes()`. `motivo` diz o que falta quando não fecha.
    """
    import base_vendas as _bv
    a, m = int(ano), int(mes)
    ant = (a, m - 1) if m > 1 else (a - 1, 12)
    chaves = _bv.meses_com_venda(mapa_vendas, ant[0], ant[1], 3)
    media = _bv.media_dos_meses(mapa_vendas, chaves) if chaves else None
    mb_media = (media or {}).get("margem_bruta")
    somas = (mapa_vendas or {}).get((a, m)) or {}
    ind = _bv.indicadores(somas) if somas.get("linhas") else {}
    mb_mes = ind.get("margem_bruta")
    faturado = ind.get("faturamento_liquido")
    planejado = ponto_de_equilibrio(meta, mb_media)
    gasto = float(gasto_real or 0.0)
    motivo = ""
    if origem_gasto == "sem dado" or gasto <= 0:
        motivo = "sem extrato do mês"
    elif not somas.get("linhas"):
        motivo = "a BASE DE VENDAS ainda não tem o mês"
    elif not mb_mes or mb_mes <= 0:
        motivo = "lucro bruto do mês em zero"
    real = None if motivo else round(gasto / (mb_mes / 100.0), 2)
    return {
        "meta": float(meta or 0.0), "planejado": planejado,
        "gasto_real": gasto, "origem_gasto": origem_gasto,
        "gasto_vs_meta": (round(gasto - float(meta), 2)
                          if meta and gasto else None),
        "mb_media": mb_media, "mb_mes": mb_mes,
        "periodo_media": _bv._texto_periodo(chaves) if chaves else "",
        "real": real, "faturado": faturado,
        "resultado": (round(faturado - real, 2)
                      if real is not None and faturado is not None else None),
        "motivo": motivo,
        # Gasto real abaixo da metade da meta é, quase sempre, extrato que
        # faltou ou veio cortado (setembro/2026: o Itaú exportou 1 linha).
        # O equilíbrio real sairia baixo e "cobriu" seria mentira.
        "suspeito": bool(meta and gasto and gasto < float(meta) * 0.5),
    }


def acompanhamento(meta, comprometido, mb_media, faturado, agora=None,
                   dias_mes=None):
    """O mês EM ANDAMENTO, projetado contra o real e proporcional ao dia. Pura.

    Dono, 09/10: a meta de gastos é o indicador principal; embaixo, o
    acompanhamento em tempo real, "considerando tudo que já está
    provisionado". `comprometido` é o total de `previsto.combinar` — o que
    já saiu mais custo fixo, folha, cheques e cartões que ainda vão sair.
    A margem é a média dos 3 meses lançados (o mês corrente não está na
    BASE DE VENDAS), a mesma do equilíbrio planejado.

      equilíbrio real  = comprometido ÷ margem
      necessário hoje  = equilíbrio real × fração do mês que passou
      fecha em         = faturado ÷ fração do mês (o ritmo de hoje)
    """
    eq_plan = ponto_de_equilibrio(meta, mb_media)
    eq_real = ponto_de_equilibrio(comprometido, mb_media)
    f = fracao_do_mes(agora, dias_mes)
    necessario = round(eq_real * f, 2) if eq_real else None
    fat = _num(faturado) if faturado is not None else None
    fecha = projecao(fat, agora, dias_mes) if fat is not None else None
    sobra = (round(fecha - eq_real, 2)
             if fecha is not None and eq_real else None)
    return {
        "meta": _num(meta), "comprometido": _num(comprometido),
        "eq_planejado": eq_plan, "eq_real": eq_real, "fracao": f,
        "necessario_hoje": necessario, "faturado": fat, "fecha_em": fecha,
        "sobra_no_fim": sobra,
        "grafico": [
            ("Gastos do mês", _num(meta) or None, _num(comprometido) or None),
            ("Equilíbrio do mês", eq_plan, eq_real),
            ("Faturamento até hoje", necessario, fat),
        ],
    }


def meses_fechados(ano, hoje):
    """Os meses de `ano` que já fecharam em `hoje`. O corrente fica de fora."""
    a = int(ano)
    if a < hoje.year:
        return list(range(1, 13))
    if a > hoje.year:
        return []
    return list(range(1, hoje.month))


# ── Conferência ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    falhas = []

    def ok(nome, cond):
        if not cond:
            falhas.append(nome)
        print(("  ok  " if cond else "FALHOU") + "  " + nome)

    # jun–ago/2026, medido na BASE DE VENDAS do Controle MS.
    JUN_AGO = {"faturamento": 776478.55, "comissao": 127512.06,
               "frete": 60045.61, "nf": 60879.32, "devolucao": 21471.76}

    taxa, linhas, aviso = taxa_de_entrada(JUN_AGO)
    ok("de cada real faturado, 65,2% caem na conta", abs(taxa - 0.6524) < 0.001)
    ok("sem aviso quando a medida é sadia", aviso == "")
    ok("a conta vem aberta, os quatro descontos", len(linhas) == 4)
    ok("comissão é o maior deles, 16,4%",
       linhas[0]["nome"] == "comissão" and linhas[0]["pct"] == 16.4)
    ok("os quatro somam 34,8% do faturamento",
       abs(sum(l["pct"] for l in linhas) - 34.8) < 0.2)

    ok("R$ 170.000 ÷ 65,2% = R$ 260.579",
       abs(faturamento_necessario(170000, taxa) - 260579) < 60)
    ok("sem meta de gastos não há meta de faturamento",
       faturamento_necessario(0, taxa) is None)
    ok("sem taxa também não", faturamento_necessario(170000, None) is None)

    # Uma taxa absurda é leitura torta, e dividir por ela explodiria a meta.
    _t, _l, _a = taxa_de_entrada({"faturamento": 1000.0, "comissao": 900.0})
    ok("taxa abaixo do piso não vira meta, vira aviso",
       _t is None and "piso" in _a)
    ok("e a conta aberta vem junto mesmo assim", len(_l) == 4)
    ok("faturamento zero não divide por zero",
       taxa_de_entrada({"faturamento": 0})[0] is None)

    # A mini meta: 22 dias fechados + 17h de hoje, num mês de 30.
    AGORA = datetime(2026, 9, 23, 17, 0, tzinfo=FUSO)
    f = fracao_do_mes(AGORA, 30)
    ok("22 dias fechados + 17h de 30 dias = 0,757",
       abs(f - (22 + 17 / 24) / 30) < 1e-6)
    ok("e NÃO é 23/30, que cobra o dia inteiro logo que ele começa",
       abs(f - 23 / 30) > 0.009)
    ok("à meia-noite do dia 1º nada é cobrado ainda",
       fracao_do_mes(datetime(2026, 9, 1, 0, 0, tzinfo=FUSO), 30) == 0.0)
    ok("às 9h do dia 1º cobra 9 horas, não um dia",
       abs(fracao_do_mes(datetime(2026, 9, 1, 9, 0, tzinfo=FUSO), 30)
           - (9 / 24) / 30) < 1e-6)
    ok("no último instante do mês a fração é 1",
       fracao_do_mes(datetime(2026, 9, 30, 23, 59, 59, tzinfo=FUSO), 30) > 0.9999)

    # O caso real do dia 23: a leitura vira o OPOSTO.
    s = situacao(178618.0, 260579.0, AGORA, 30)
    ok("o alvo até as 17h do dia 23 é R$ 197.216",
       abs(s["alvo"] - 197216) < 60)
    ok("com a meta certa ele está ABAIXO, não acima", not s["acima"])
    ok("e a diferença é de ~R$ 18,6 mil", abs(s["diferenca"] + 18598) < 60)
    # Com a meta velha de R$ 34.865 a mesma tela dizia o contrário.
    velha = situacao(178618.0, 34865.0, AGORA, 30)
    ok("a meta velha dizia 'acima do ritmo' — e era isso que decidia comprar",
       velha["acima"] and velha["diferenca"] > 150000)

    ok("a projeção é o ritmo de agora esticado até o fim do mês",
       abs(s["projecao"] - 178618.0 / f) < 1.0)
    ok("e ela não fecha a meta", not s["fecha_a_meta"])
    ok("no primeiro instante do mês não se projeta nada",
       projecao(0.0, datetime(2026, 9, 1, 0, 0, tzinfo=FUSO), 30) is None)

    q, avisos = montar(170000, JUN_AGO, 178618.0, AGORA, 30)
    ok("o quadro traz a meta, a taxa e a conta aberta",
       abs(q["meta"] - 260579) < 60 and q["taxa_de_entrada"] == taxa
       and len(q["descontos"]) == 4)
    ok("e a meta de gastos que a originou", q["meta_de_gastos"] == 170000.0)
    ok("sem meta de gastos, o aviso diz onde cadastrar",
       montar(0, JUN_AGO, 1.0, AGORA, 30)[0] is None
       and "Meta de gastos" in montar(0, JUN_AGO, 1.0, AGORA, 30)[1][0])

    # ── 07/10: equilíbrio = meta de gastos ÷ lucro bruto médio de 3 meses
    ok("equilíbrio é a meta de gastos dividida pelo lucro bruto médio",
       ponto_de_equilibrio(150000, 30.0) == 500000.0
       and ponto_de_equilibrio(150000, 74.3) == round(150000 / 0.743, 2))
    ok("sem meta de gastos não há equilíbrio — e nem com margem zero",
       ponto_de_equilibrio(0, 30.0) is None
       and ponto_de_equilibrio(150000, 0) is None
       and ponto_de_equilibrio(None, None) is None)

    # ── 09/10: O EQUILÍBRIO REAL DO MÊS FECHADO ──────────────────────────
    # O mapa na forma que `base_vendas.somas_por_mes` monta: cada mês com as
    # chaves de COLUNAS e a contagem de linhas.
    import base_vendas as _bv_t
    from datetime import date as _d_t

    def _mes_t(fat_liq, lb):
        d = {k: 0.0 for k in _bv_t.COLUNAS}
        # Bruto ≠ líquido de propósito: trocar um pelo outro tem de aparecer.
        d.update({"faturamento": fat_liq * 1.1, "fat_liquido": fat_liq,
                  "lucro_bruto": lb, "linhas": 10})
        return d
    _mapa_t = {(2026, 6): _mes_t(200000, 60000), (2026, 7): _mes_t(200000, 60000),
               (2026, 8): _mes_t(200000, 60000),     # média: 30%
               (2026, 9): _mes_t(220000, 55000)}     # setembro: 25%
    _r = equilibrio_real(60000, 66000, "extrato", _mapa_t, 2026, 9)
    ok("planejado = meta ÷ lucro bruto médio dos 3 meses anteriores",
       _r["planejado"] == 200000.0 and _r["mb_media"] == 30.0)
    ok("real = o que saiu ÷ lucro bruto do próprio mês",
       _r["mb_mes"] == 25.0 and _r["real"] == 264000.0)
    ok("resultado = faturamento líquido − real (faltou)",
       _r["faturado"] == 220000.0 and _r["resultado"] == -44000.0)
    ok("e diz quanto o gasto passou da meta",
       _r["gasto_vs_meta"] == 6000.0)
    # O MÊS EM ANDAMENTO: dia 16 às 0h de um mês de 30 = metade do mês.
    from datetime import datetime as _dt_t
    _ag = _dt_t(2026, 10, 16, 0, 0, tzinfo=FUSO)
    _a = acompanhamento(60000, 75000, 30.0, 110000, agora=_ag, dias_mes=30)
    ok("andamento: planejado pela meta, real pelo comprometido",
       _a["eq_planejado"] == 200000.0 and _a["eq_real"] == 250000.0)
    ok("andamento: o necessário até hoje é proporcional ao dia",
       _a["fracao"] == 0.5 and _a["necessario_hoje"] == 125000.0)
    ok("andamento: no ritmo de hoje fecha em 220 mil — faltam 30 mil",
       _a["fecha_em"] == 220000.0 and _a["sobra_no_fim"] == -30000.0)
    ok("andamento: o gráfico compara projetado e real nas três linhas",
       [g[0] for g in _a["grafico"]] == ["Gastos do mês", "Equilíbrio do mês",
                                          "Faturamento até hoje"]
       and _a["grafico"][2] == ("Faturamento até hoje", 125000.0, 110000.0))
    ok("andamento: sem margem não inventa equilíbrio",
       acompanhamento(60000, 75000, 0, 110000, agora=_ag,
                      dias_mes=30)["eq_real"] is None)
    ok("gasto real abaixo da metade da meta é marcado como suspeito",
       equilibrio_real(60000, 20000, "extrato", _mapa_t, 2026, 9)["suspeito"]
       and not _r["suspeito"])
    ok("mês sem extrato não inventa equilíbrio real",
       equilibrio_real(60000, 0, "sem dado", _mapa_t, 2026, 9)["real"] is None
       and "extrato" in equilibrio_real(60000, 0, "sem dado", _mapa_t,
                                        2026, 9)["motivo"])
    ok("mês fora da BASE DE VENDAS diz por quê",
       "BASE DE VENDAS" in equilibrio_real(60000, 66000, "extrato", _mapa_t,
                                           2026, 10)["motivo"])
    ok("o mês corrente fica de fora até fechar",
       meses_fechados(2026, _d_t(2026, 10, 9)) == list(range(1, 10))
       and meses_fechados(2025, _d_t(2026, 10, 9)) == list(range(1, 13))
       and meses_fechados(2027, _d_t(2026, 10, 9)) == [])

    print()
    if falhas:
        print("FALHOU: " + ", ".join(falhas))
        raise SystemExit(1)
    print("Tudo certo.")
