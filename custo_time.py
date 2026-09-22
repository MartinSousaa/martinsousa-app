"""custo_time.py — quanto o time custa no mês, separado em Gerência e Headcount.

POR QUE OS DOIS NÃO PODEM SER UM NÚMERO SÓ
------------------------------------------
Eles pesam em lugares diferentes do ponto de equilíbrio, e é o dono quem
definiu assim:

    Folha Gerência    entra no numerador. Sempre.
    Folha Headcount   fica FORA enquanto a Reserva cobrir, e volta quando ela
                      acabar.

Somar os dois num campo só apagaria a única pergunta que a Home precisa
responder — *"falta muito para o faturamento suprir o custo que a reserva vem
suprindo?"* —, porque a resposta é exatamente a diferença entre as duas contas.

QUEM ESTÁ EM CADA UM NÃO SE ESCREVE AQUI
-----------------------------------------
A coluna `no_aporte` da grade de colaboradores já decide isso, e
`colaboradores.entra_no_aporte` já a lê. Repetir a lista de nomes neste arquivo
seria a segunda resposta para a mesma pergunta — e nesta base uma lista de
gente escrita em código já escondeu dois colaboradores do painel.

O BÔNUS DE META ENTRA COM UM MÊS DE ATRASO
-------------------------------------------
O salário cai no dia 30; o bônus só depois da apuração, no 5º dia útil do mês
seguinte (`explicacao_metas.py:38`). Então o dinheiro que sai em outubro é a
folha DE OUTUBRO mais o bônus DE SETEMBRO. Projetar a Reserva com o bônus no
mês em que foi ganho antecipa cada saque em um mês — e o último mês, que é o
que decide se a reserva chega, sairia errado.

O BÔNUS AINDA NÃO É CALCULADO AQUI
-----------------------------------
A conta que decide quem bateu cada meta existe, está certa e roda todo dia —
mas mora DENTRO do desenho da tela (`analise_metas.py:1771-1826`), uma pessoa
por vez, amarrada a variáveis locais do Streamlit. Extraí-la é um trabalho
próprio, e é dinheiro que as pessoas recebem: merece um passo só dele, com
teste comparando o resultado extraído contra o que a tela mostra hoje.

Enquanto isso este módulo aceita o bônus por parâmetro e sabe dizer o TETO
dele (`teto_do_bonus`), que é o que a Reserva precisa para mostrar o pior caso.
Chutar um valor no meio seria inventar número; o teto é regra, não palpite.
"""

# O custo de contabilidade que EXISTE POR CAUSA do quadro CLT, informado pelo
# dono em 22/09/2026. Não se confunde com a contabilidade da empresa
# (R$ 885, item do Custo fixo): aquela existiria com zero funcionários.
CONTABILIDADE_HEADCOUNT = 600.00

# O teto do bônus, da regra que já está no Studio: coletiva MAXX (18%) +
# individual MAXX (12%). Os níveis não somam entre si — a MAXX toma o lugar da
# normal —, então 30% é o máximo que alguém pode receber a mais.
TETO_BONUS_PCT = 0.30


def _num(v, padrao=0.0):
    if v is None or v == "":
        return padrao
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace("R$", "").replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return padrao


def separar(folha_clt):
    """(cobertos_pela_reserva, fora_dela) a partir de `colaboradores.folha_clt`.

    A marca vem pronta de lá, no campo `no_aporte` de cada linha.
    """
    dentro, fora = [], []
    for p in (folha_clt or []):
        (dentro if p.get("no_aporte", True) else fora).append(p)
    return dentro, fora


def _somar(pessoas, campo="total"):
    return round(sum(_num(p.get(campo)) for p in (pessoas or [])), 2)


def headcount(folha_clt, bonus=0.0, contabilidade=None):
    """O custo do quadro coberto pela Reserva, no mês.

    `bonus` é o valor JÁ APURADO do mês anterior — quem chama decide de qual
    mês ele veio, porque só quem chama sabe qual mês está montando.
    """
    dentro, _ = separar(folha_clt)
    salarios = _somar(dentro)
    cont = CONTABILIDADE_HEADCOUNT if contabilidade is None \
        else _num(contabilidade)
    b = max(0.0, _num(bonus))
    return {"pessoas": len(dentro),
            "salarios": salarios,
            "contabilidade": round(cont, 2),
            "bonus": round(b, 2),
            "total": round(salarios + cont + b, 2)}


def fora_da_reserva(folha_clt):
    """O quadro CLT que a Reserva NÃO cobre — este sempre pesa no equilíbrio."""
    _, fora = separar(folha_clt)
    return {"pessoas": len(fora), "salarios": _somar(fora),
            "total": _somar(fora)}


def gerencia(folha_gestores):
    """O total da Folha Gerência, que vem de `folha_salarial.total_da_folha`."""
    return {"total": round(_num(folha_gestores), 2)}


def teto_do_bonus(folha_clt, pct=TETO_BONUS_PCT):
    """O máximo que o bônus pode custar neste mês.

    Sobre o SALÁRIO BASE, e não sobre o custo total da pessoa: o bônus é um
    percentual do salário (`explicacao_metas.py`), e encargos, refeição e
    vale-transporte não se multiplicam por ele. Usar o total inflaria o teto em
    torno de um terço e faria a Reserva parecer mais curta do que é.
    """
    dentro, _ = separar(folha_clt)
    base = round(sum(_num(p.get("base")) for p in dentro), 2)
    return round(base * float(pct), 2)


def faixa_do_mes(folha_clt, folha_gestores=0.0, bonus=None,
                 contabilidade=None):
    """(piso, teto) do custo do time no mês — o intervalo honesto.

    Com o bônus já apurado, piso e teto são iguais: não há mais faixa, há um
    número. Sem ele, o piso é ninguém bater meta e o teto é todo mundo bater
    tudo. A Reserva projeta os dois, e a diferença entre eles é o risco que o
    dono está correndo sem saber — que é justamente o que ele quer ver.
    """
    g = gerencia(folha_gestores)["total"]
    if bonus is not None:
        t = headcount(folha_clt, bonus, contabilidade)["total"] + g
        return round(t, 2), round(t, 2)
    piso = headcount(folha_clt, 0.0, contabilidade)["total"] + g
    teto = piso + teto_do_bonus(folha_clt)
    return round(piso, 2), round(teto, 2)


# ── Conferência ──────────────────────────────────────────────────────────────
# `python3 custo_time.py`.
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # Como `colaboradores.folha_clt` devolve: base é o salário, total já traz
    # encargos, provisões, refeição e vale-transporte por cima.
    FOLHA = [
        {"funcionario": "Beatriz", "base": 2000.0, "total": 3100.0,
         "no_aporte": True},
        {"funcionario": "Gabriel", "base": 2200.0, "total": 3350.0,
         "no_aporte": True},
        {"funcionario": "Myrella", "base": 1800.0, "total": 2850.0,
         "no_aporte": True},
        {"funcionario": "Antigo", "base": 3000.0, "total": 4400.0,
         "no_aporte": False},
    ]

    dentro, fora = separar(FOLHA)
    ok("quem está no aporte é separado", len(dentro) == 3 and len(fora) == 1)
    ok("e é pela marca da grade, não por nome",
       all(p["no_aporte"] for p in dentro))

    h = headcount(FOLHA)
    ok("os salários somam só os cobertos", h["salarios"] == 9300.0)
    ok("a contabilidade do quadro entra", h["contabilidade"] == 600.0)
    ok("sem bônus o total é salários + contabilidade", h["total"] == 9900.0)

    h2 = headcount(FOLHA, bonus=1500.0)
    ok("o bônus apurado entra no total", h2["total"] == 11400.0)
    ok("bônus negativo não vira desconto", headcount(FOLHA, -500)["bonus"] == 0.0)

    f = fora_da_reserva(FOLHA)
    ok("quem está fora do aporte é contado à parte",
       f["pessoas"] == 1 and f["total"] == 4400.0)

    # O teto é sobre o SALÁRIO, não sobre o custo total.
    ok("o teto do bônus é 30% do salário base",
       teto_do_bonus(FOLHA) == round(6000.0 * 0.30, 2))
    ok("e NÃO 30% do custo total", teto_do_bonus(FOLHA) != round(9300.0 * .30, 2))

    piso, teto = faixa_do_mes(FOLHA, folha_gestores=22_000.0)
    ok("o piso é ninguém bater meta", piso == 31_900.0)
    ok("o teto é todo mundo bater tudo", teto == 31_900.0 + 1800.0)
    ok("a gerência entra sempre", piso - 22_000.0 == 9_900.0)

    p2, t2 = faixa_do_mes(FOLHA, folha_gestores=22_000.0, bonus=1200.0)
    ok("com o bônus apurado não há mais faixa", p2 == t2)
    ok("e o número é o real", p2 == 9300.0 + 600.0 + 1200.0 + 22_000.0)

    # Bordas: folha vazia não pode virar erro nem número inventado.
    ok("folha vazia custa só a contabilidade", headcount([])["total"] == 600.0)
    ok("folha vazia tem teto de bônus zero", teto_do_bonus([]) == 0.0)
    ok("ninguém no aporte não quebra",
       headcount([{"base": 1, "total": 2, "no_aporte": False}])["salarios"]
       == 0.0)
    ok("valor em texto da planilha é lido",
       headcount([{"base": "1.000,00", "total": "2.500,50",
                   "no_aporte": True}])["salarios"] == 2500.50)
    ok("contabilidade pode ser sobrescrita",
       headcount(FOLHA, contabilidade=0)["total"] == 9300.0)

    print("\nfalhas:", falhas)
    raise SystemExit(falhas)
