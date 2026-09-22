"""bonus.py — quanto cada pessoa recebe a mais no mês, e por quê.

POR QUE ESTE ARQUIVO PASSOU A EXISTIR
-------------------------------------
A regra já estava certa e já rodava — mas morava DENTRO do desenho da tela do
colaborador (`analise_metas.py`), uma pessoa por vez, presa a variáveis locais
do Streamlit. Isso bastava para a pessoa ver o próprio bônus e não bastava para
mais nada: não dava para somar o mês inteiro, não dava para projetar quanto a
Reserva do Headcount precisa cobrir, não dava para o WhatsApp responder.

Aqui a mesma regra vira função. A tela passa a chamá-la em vez de repeti-la —
duas contas para a mesma pergunta é como a tela do colaborador passa a
discordar da lista do gestor, e a questão é só quando.

A REGRA, EM QUATRO FRASES
-------------------------
1. São quatro metas: coletiva e individual, cada uma com um nível MAXX.
2. Cada metade paga o nível MAIS ALTO alcançado. A MAXX TOMA O LUGAR da
   mensal — ninguém recebe 20% + 30%.
3. As duas metades SOMAM entre si, inclusive de níveis diferentes: dá para
   receber a coletiva mensal (12%) com a individual MAXX (12%).
4. Para receber a metade do TIME é preciso ter ENTRADO nela. São dois
   porteiros, e os dois valem por mês: contribuição mínima sobre a PRÓPRIA
   meta de pontos (80% para a coletiva, 100% para a MAXX) e teto de
   advertências (2 e 1).

ENTRAR NA COLETIVA E BATER A INDIVIDUAL SÃO CONTAS DIFERENTES
--------------------------------------------------------------
Entrar olha só PONTUAÇÃO. Bater a própria meta olha os seis critérios do card:
pontuação, ociosidade, tempo de execução, tolerâncias, atrasos e advertências.

Por isso é possível entrar na coletiva MAXX — 100% dos pontos — e ainda assim
não bater a própria individual, por ociosidade ou atraso. As duas colunas são
independentes de propósito, e misturá-las pagaria a quem não deveria.

CRITÉRIO QUE NÃO DÁ PARA MEDIR NÃO REPROVA
-------------------------------------------
Sem relógio de ponto, sem alvo de tempo no mês, sem cartão medido — o critério
fica "aguardando" e passa. Reprovar por dado que falta zeraria o bônus de todo
mundo no dia em que a RHiD saísse do ar, e ninguém entenderia por quê.
"""

import explicacao_metas as _ex

# Os percentuais e os limites vivem em `explicacao_metas`, que é quem os
# mostra ao colaborador. Copiá-los para cá criaria a segunda resposta.
PCT_COLETIVO_MENSAL = _ex.PCT_COLETIVO_MENSAL
PCT_COLETIVO_MAXX = _ex.PCT_COLETIVO_MAXX
PCT_INDIVIDUAL_MENSAL = _ex.PCT_INDIVIDUAL_MENSAL
PCT_INDIVIDUAL_MAXX = _ex.PCT_INDIVIDUAL_MAXX
MIN_CONTRIB_NORMAL = _ex.MIN_CONTRIB_NORMAL
MIN_CONTRIB_MAXX = _ex.MIN_CONTRIB_MAXX
MAX_ADV_NORMAL = _ex.MAX_ADV_NORMAL
MAX_ADV_MAXX = _ex.MAX_ADV_MAXX


def porteiros(pct_contribuicao, advertencias, min_contrib, max_adv):
    """(entra, motivos) — a pessoa entrou nesta metade do time?

    Os dois porteiros numa função só porque a mesma pergunta é feita em três
    lugares: o card do colaborador, a lista de elegibilidade do gestor e a
    apuração do mês. Em três cópias elas passariam a discordar.

    Devolve também POR QUE não, porque bônus que some sem explicação vira
    conversa no corredor.
    """
    motivos = []
    pct = float(pct_contribuicao or 0.0)
    advs = int(advertencias or 0)
    if pct < float(min_contrib):
        motivos.append(f"{pct:.0f}% da meta individual (mín. {min_contrib:.0f}%)")
    if advs > int(max_adv):
        motivos.append(f"{advs} advertência(s) (máx. {int(max_adv)})")
    return (not motivos), motivos


def apurar(salario_base=0.0, time_bateu_col=False, time_bateu_maxx=False,
           pct_contribuicao=0.0, advertencias=0,
           individual_batida=False, individual_maxx_batida=False,
           min_contrib_n=None, min_contrib_x=None,
           max_adv_n=None, max_adv_x=None):
    """O bônus de uma pessoa num mês. Tudo entra por parâmetro, nada é lido.

    Devolve {"pct_time","pct_individual","pct","valor","entra_col",
             "entra_maxx","motivos_col","motivos_maxx","nivel"}.

    Função pura de propósito: ela decide dinheiro que as pessoas recebem, e o
    que se pode testar linha a linha é o que se pode conferir quando alguém
    reclamar do valor.
    """
    mn = MIN_CONTRIB_NORMAL if min_contrib_n is None else min_contrib_n
    mx = MIN_CONTRIB_MAXX if min_contrib_x is None else min_contrib_x
    an = MAX_ADV_NORMAL if max_adv_n is None else max_adv_n
    ax = MAX_ADV_MAXX if max_adv_x is None else max_adv_x

    entra_col, mot_col = porteiros(pct_contribuicao, advertencias, mn, an)
    entra_maxx, mot_maxx = porteiros(pct_contribuicao, advertencias, mx, ax)

    # O time bateu E a pessoa entrou. Uma coisa sem a outra não paga.
    col_mensal = bool(time_bateu_col) and entra_col
    col_maxx = bool(time_bateu_maxx) and entra_maxx

    pct_time, pct_seu = _ex.bonus_percentuais(
        col_mensal, col_maxx, bool(individual_batida),
        bool(individual_maxx_batida))

    pct = pct_time + pct_seu
    return {"pct_time": pct_time, "pct_individual": pct_seu, "pct": pct,
            "valor": round(float(salario_base or 0.0) * pct / 100.0, 2),
            "entra_col": entra_col, "entra_maxx": entra_maxx,
            "motivos_col": mot_col, "motivos_maxx": mot_maxx,
            "nivel": _nivel(col_mensal, col_maxx, bool(individual_batida),
                            bool(individual_maxx_batida))}


def _nivel(col_mensal, col_maxx, ind, ind_maxx):
    """Uma frase curta do que foi alcançado — para a tela e para o WhatsApp."""
    time = ("coletiva MAXX" if col_maxx else
            "coletiva" if col_mensal else None)
    seu = ("individual MAXX" if ind_maxx else
           "individual" if ind else None)
    partes = [p for p in (time, seu) if p]
    return " + ".join(partes) if partes else "nenhuma meta"


def do_mes(pessoas):
    """A apuração de todo mundo. `pessoas` é {nome: kwargs de `apurar`}.

    Devolve ({nome: apuração}, total). O total é o que sai do caixa no 5º dia
    útil do mês seguinte — e é o número que a Reserva do Headcount precisa.
    """
    fora = {nome: apurar(**kw) for nome, kw in (pessoas or {}).items()}
    return fora, round(sum(a["valor"] for a in fora.values()), 2)


def teto(pessoas):
    """O máximo que a apuração poderia custar: todo mundo batendo tudo.

    Serve para a Reserva projetar o pior caso enquanto o mês não fechou. É
    regra, não palpite — ninguém pode receber mais do que a coletiva MAXX mais
    a individual MAXX.
    """
    pct = (PCT_COLETIVO_MAXX + PCT_INDIVIDUAL_MAXX) / 100.0
    return round(sum(float(kw.get("salario_base") or 0.0)
                     for kw in (pessoas or {}).values()) * pct, 2)


# ── Conferência ──────────────────────────────────────────────────────────────
# `python3 bonus.py`. Os casos são os nove cenários que a tela do colaborador
# já mostra em tabela, mais as bordas que a tabela não mostra.
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    S = 2000.0

    def ap(**kw):
        return apurar(salario_base=S, **kw)

    # ── os quatro percentuais ────────────────────────────────────────────
    ok("coletiva sozinha paga 12%",
       ap(time_bateu_col=True, pct_contribuicao=85)["pct"] == 12.0)
    ok("individual sozinha paga 8%",
       ap(individual_batida=True)["pct"] == 8.0)
    ok("as duas somam 20%",
       ap(time_bateu_col=True, pct_contribuicao=85,
          individual_batida=True)["pct"] == 20.0)
    ok("coletiva MAXX sozinha paga 18%",
       ap(time_bateu_col=True, time_bateu_maxx=True,
          pct_contribuicao=100)["pct"] == 18.0)
    ok("as duas MAXX somam 30%",
       ap(time_bateu_col=True, time_bateu_maxx=True, pct_contribuicao=100,
          individual_batida=True, individual_maxx_batida=True)["pct"] == 30.0)

    # A REGRA MAIS IMPORTANTE: a MAXX toma o lugar, não se soma.
    r = ap(time_bateu_col=True, time_bateu_maxx=True, pct_contribuicao=100,
           individual_batida=True, individual_maxx_batida=True)
    ok("ninguém recebe 20% + 30%", r["pct"] == 30.0 and r["pct"] != 50.0)
    ok("e o valor em reais bate", r["valor"] == 600.00)

    # Metades de níveis diferentes somam entre si.
    ok("coletiva mensal + individual MAXX = 24%",
       ap(time_bateu_col=True, pct_contribuicao=85, individual_batida=True,
          individual_maxx_batida=True)["pct"] == 24.0)

    # ── os porteiros ─────────────────────────────────────────────────────
    r = ap(time_bateu_col=True, pct_contribuicao=79, individual_batida=True)
    ok("abaixo de 80% não recebe a metade do time", r["pct_time"] == 0.0)
    ok("mas a metade dele continua sendo dele", r["pct_individual"] == 8.0)
    ok("e a tela sabe dizer por quê", "79%" in r["motivos_col"][0])

    ok("exatamente 80% entra",
       ap(time_bateu_col=True, pct_contribuicao=80)["entra_col"])
    ok("99% NÃO entra na MAXX",
       not ap(time_bateu_col=True, time_bateu_maxx=True,
              pct_contribuicao=99)["entra_maxx"])
    ok("99% ainda entra na coletiva normal, que paga 12%",
       ap(time_bateu_col=True, time_bateu_maxx=True,
          pct_contribuicao=99)["pct"] == 12.0)

    ok("duas advertências ainda entram na coletiva",
       ap(time_bateu_col=True, pct_contribuicao=100,
          advertencias=2)["entra_col"])
    ok("a terceira tira da coletiva",
       not ap(time_bateu_col=True, pct_contribuicao=100,
              advertencias=3)["entra_col"])
    ok("mas uma só já tira da MAXX",
       not ap(time_bateu_col=True, time_bateu_maxx=True, pct_contribuicao=100,
              advertencias=2)["entra_maxx"])

    # ── o time não bateu: nada da metade dele, mesmo entrando ────────────
    r = ap(pct_contribuicao=100, individual_batida=True)
    ok("entrar sem o time bater não paga a metade do time",
       r["entra_col"] and r["pct_time"] == 0.0)

    # ── o cenário que a regra criou ──────────────────────────────────────
    r = ap(time_bateu_col=True, pct_contribuicao=60, individual_batida=False)
    ok("time comemora e a pessoa não recebe nada", r["pct"] == 0.0)
    ok("e o motivo está escrito", r["motivos_col"])

    # ── a frase do nível ─────────────────────────────────────────────────
    ok("o nível descreve o que foi alcançado",
       ap(time_bateu_col=True, time_bateu_maxx=True, pct_contribuicao=100,
          individual_batida=True)["nivel"] == "coletiva MAXX + individual")
    ok("sem meta nenhuma o nível diz isso", ap()["nivel"] == "nenhuma meta")

    # ── o mês inteiro ────────────────────────────────────────────────────
    TIME = {
        "Beatriz": {"salario_base": 2000.0, "time_bateu_col": True,
                    "pct_contribuicao": 100, "individual_batida": True},
        "Gabriel": {"salario_base": 2200.0, "time_bateu_col": True,
                    "pct_contribuicao": 70, "individual_batida": True},
        "Myrella": {"salario_base": 1800.0, "time_bateu_col": True,
                    "pct_contribuicao": 90, "individual_batida": False},
    }
    apur, total = do_mes(TIME)
    ok("Beatriz recebe 20%", apur["Beatriz"]["valor"] == 400.00)
    ok("Gabriel só a metade dele, 8%", apur["Gabriel"]["valor"] == 176.00)
    ok("Myrella só a metade do time, 12%", apur["Myrella"]["valor"] == 216.00)
    ok("o total do mês soma os três", total == 792.00)

    # O teto é regra: 30% de todo mundo.
    ok("o teto do mês é 30% da folha base", teto(TIME) == round(6000.0 * .3, 2))
    ok("e o total apurado nunca passa dele", total <= teto(TIME))
    ok("time vazio não quebra", do_mes({}) == ({}, 0.0) and teto({}) == 0.0)

    # ── limites configuráveis ────────────────────────────────────────────
    ok("o mínimo de contribuição pode mudar por configuração",
       ap(time_bateu_col=True, pct_contribuicao=70,
          min_contrib_n=70)["pct_time"] == 12.0)

    # ── a mesma conta que a tela já usa ──────────────────────────────────
    ok("os percentuais vêm de explicacao_metas, não são cópia",
       (PCT_COLETIVO_MENSAL, PCT_COLETIVO_MAXX, PCT_INDIVIDUAL_MENSAL,
        PCT_INDIVIDUAL_MAXX) == (12.0, 18.0, 8.0, 12.0))

    print("\nfalhas:", falhas)
    raise SystemExit(falhas)
