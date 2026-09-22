"""reserva.py — a verba aplicada que sustenta o Headcount até o faturamento dar conta.

O QUE ELA É, E O QUE ELA NÃO É
------------------------------
O dono aportou R$ 270.000 num CDB-DI para pagar o time por um tempo. A
tentação — e ele mesmo levantou a hipótese — é tirar o custo do time da conta
do negócio enquanto essa verba durar. Não dá, e o motivo não é preciosismo
contábil:

    aporte é dinheiro ENTRANDO, não custo SUMINDO.

Se a folha do Headcount sai do numerador do ponto de equilíbrio, o painel passa
a dizer "a operação se paga" quando ela não se paga — ela está sendo paga pela
reserva. No dia em que a reserva acabar, o equilíbrio salta de uma vez e a
tela terá mentido o tempo todo.

O que ele pediu, e é a leitura certa, são DUAS linhas vivendo lado a lado:

    equilíbrio de hoje          sem o Headcount, que a reserva cobre
    equilíbrio quando acabar    com o Headcount dentro

A distância entre as duas é quanto o faturamento ainda precisa subir. Ela
encolhe sozinha conforme o negócio cresce, e é o número que responde a pergunta
que ele fez: *"falta muito para conquistarmos o faturamento necessário?"*

"APORTE" JÁ ESTAVA OCUPADO
--------------------------
`nao_operacional.py` chama de `aporte` o valor liberado de cada PRONAMP. São
coisas opostas — uma é dívida que entra, a outra é capital do dono — e o mesmo
nome nos dois lugares vira erro de leitura em algum relatório. Aqui a verba do
time chama RESERVA, e `aporte` continua sendo do PRONAMP.

O IMPOSTO DE RENDA NÃO É UMA TAXA SÓ
------------------------------------
No resgate de renda fixa o IR incide sobre o RENDIMENTO, com alíquota que cai
conforme o dinheiro envelhece — 22,5% até 180 dias, 20% até 360, 17,5% até 720,
15% daí em diante. Projetar a cobertura com uma alíquota fixa erra para menos
no começo e para mais no fim; e a diferença entre sacar em 09/02 e em 11/02
(quando o CDB de 14/08 cruza os 180 dias) é real.
"""

from datetime import date, timedelta

# ── A tabela regressiva do IR de renda fixa (Lei 11.033/2004) ───────────────
# (dias corridos desde a aplicação, alíquota sobre o RENDIMENTO)
FAIXAS_IR = ((180, 0.225), (360, 0.200), (720, 0.175), (10**9, 0.150))


def aliquota_ir(dias):
    """A alíquota sobre o rendimento para um resgate com `dias` de aplicação."""
    d = max(0, int(dias or 0))
    for limite, taxa in FAIXAS_IR:
        if d <= limite:
            return taxa
    return FAIXAS_IR[-1][1]


def proxima_faixa(inicio, hoje=None):
    """(data, alíquota_nova, dias_que_faltam) — quando o IR cai de faixa.

    Existe para o Studio conseguir dizer "espere 3 dias e o IR cai de 22,5%
    para 20%". Devolve None quando já se está na última faixa, onde não há mais
    o que esperar.
    """
    ini = _data(inicio)
    ref = _data(hoje) or date.today()
    if not ini:
        return None
    corridos = (ref - ini).days
    for limite, taxa in FAIXAS_IR[:-1]:
        if corridos <= limite:
            return ini + timedelta(days=limite + 1), \
                _taxa_apos(limite), limite + 1 - corridos
    return None


def _taxa_apos(limite):
    """A alíquota da faixa SEGUINTE a `limite`."""
    for i, (lim, _) in enumerate(FAIXAS_IR):
        if lim == limite:
            return FAIXAS_IR[min(i + 1, len(FAIXAS_IR) - 1)][1]
    return FAIXAS_IR[-1][1]


def _data(v):
    """date a partir de date, datetime ou 'AAAA-MM-DD'. None quando não dá."""
    if isinstance(v, date):
        return v
    if hasattr(v, "date"):
        try:
            return v.date()
        except Exception:
            return None
    t = str(v or "").strip()[:10]
    try:
        return date(int(t[0:4]), int(t[5:7]), int(t[8:10]))
    except (ValueError, IndexError):
        return None


def taxa_implicita(aplicado, saldo_bruto, inicio, ate):
    """O rendimento diário que o extrato do banco revela, sem pedir o CDI.

    O Studio não tem cotação do DI e não vai buscar uma: seria mais uma
    dependência externa para descobrir o que o próprio extrato já diz. Dois
    números e duas datas dão a taxa que de fato rendeu — e ela se corrige
    sozinha toda vez que o dono colar uma posição nova.

    Devolve a taxa ao DIA (0.000345 ≈ 1,04% ao mês). None quando não dá.
    """
    ini, fim = _data(inicio), _data(ate)
    if not ini or not fim:
        return None
    dias = (fim - ini).days
    try:
        ap, br = float(aplicado), float(saldo_bruto)
    except (TypeError, ValueError):
        return None
    if dias <= 0 or ap <= 0 or br <= 0:
        return None
    return (br / ap) ** (1.0 / dias) - 1.0


def liquido(aplicado, bruto, inicio, resgate):
    """Quanto sobra na mão depois do IR, resgatando tudo em `resgate`."""
    ini, res = _data(inicio), _data(resgate)
    br = float(bruto or 0.0)
    ap = float(aplicado or 0.0)
    rendimento = max(0.0, br - ap)
    dias = (res - ini).days if (ini and res) else 0
    return round(br - rendimento * aliquota_ir(dias), 2)


def projecao(aplicado, bruto, inicio, saque_mensal, dia_do_saque=30,
             de=None, meses=24, taxa_dia=None, extras=None):
    """Mês a mês: quanto rende, quanto sai, e até quando a reserva cobre.

    Devolve [{"ano","mes","saldo_inicial","rendimento","ir","saque",
              "saldo_final","cobre"}], uma linha por mês, parando quando o
    saldo zera.

    `extras` é {(ano, mês): valor} para o que não é a folha do mês — o bônus
    de meta, que o dono paga no 5º dia útil seguinte e saca à parte.

    O SAQUE É LÍQUIDO, E ESSA É A PARTE QUE ENGANA
    Ele precisa de R$ X na conta para pagar o time. Sacar R$ X do CDB põe menos
    que X na conta, porque o IR come um pedaço do rendimento resgatado. Então a
    conta é ao contrário: quanto sacar do bruto para SOBRAR X. Ignorar isso faz
    a reserva parecer durar um mês a mais do que dura — e o mês que falta é
    exatamente aquele em que ninguém tem plano B.
    """
    ini = _data(inicio)
    ref = _data(de) or ini
    if not ini or not ref:
        return []
    ap = float(aplicado or 0.0)
    saldo = float(bruto or 0.0)
    # O custo já pago em IR não volta: o "principal" para efeito de imposto
    # encolhe junto com os saques, na mesma proporção do resgate.
    principal = ap
    taxa = taxa_dia if taxa_dia is not None else \
        taxa_implicita(ap, saldo, ini, ref)
    if taxa is None:
        taxa = 0.0
    fora = []
    ano, mes = ref.year, ref.month
    for _ in range(max(1, int(meses))):
        dia = _dia_valido(ano, mes, dia_do_saque)
        data_saque = date(ano, mes, dia)
        dias = max(0, (data_saque - ref).days) if not fora else \
            (data_saque - _data(fora[-1]["data_saque"])).days
        rendimento = saldo * ((1.0 + taxa) ** max(0, dias) - 1.0)
        saldo += rendimento

        precisa = float(saque_mensal or 0.0) + \
            float((extras or {}).get((ano, mes), 0.0))
        bruto_a_sacar, ir = _bruto_para_liquido(
            precisa, saldo, principal, (data_saque - ini).days)
        # "Cobre" e entregar o que precisava, nao apenas nao estourar o saldo.
        #
        # Sem a segunda condicao, um saldo ZERADO cobria qualquer coisa: o
        # resgate calculado dava zero, zero cabe em zero, e a reserva aparecia
        # cobrindo o mes em que ela ja tinha acabado.
        cobre = (precisa <= 0) or (0 < bruto_a_sacar <= saldo + 0.005)
        if not cobre:
            bruto_a_sacar = saldo
            ir = _ir_do_resgate(bruto_a_sacar, saldo, principal,
                                (data_saque - ini).days)
        # O principal encolhe na proporção do que foi resgatado: resgatar
        # metade do saldo resgata metade do principal e metade do rendimento.
        parcela = (bruto_a_sacar / saldo) if saldo > 0 else 0.0
        principal = max(0.0, principal - principal * parcela)
        saldo_final = round(max(0.0, saldo - bruto_a_sacar), 2)
        fora.append({"ano": ano, "mes": mes, "data_saque": data_saque.isoformat(),
                     "saldo_inicial": round(saldo - rendimento, 2),
                     "rendimento": round(rendimento, 2),
                     "sacado_bruto": round(bruto_a_sacar, 2),
                     "ir": round(ir, 2),
                     "recebido": round(bruto_a_sacar - ir, 2),
                     "precisava": round(precisa, 2),
                     "cobre": cobre,
                     "saldo_final": saldo_final})
        saldo = saldo_final
        if not cobre or saldo <= 0.005:
            break
        mes += 1
        if mes == 13:
            ano, mes = ano + 1, 1
    return fora


def _dia_valido(ano, mes, dia):
    """O dia pedido, ou o último do mês. Fevereiro não tem 30."""
    import calendar
    return min(max(1, int(dia or 1)), calendar.monthrange(ano, mes)[1])


def _ir_do_resgate(bruto_sacado, saldo, principal, dias):
    """O IR de resgatar `bruto_sacado` de um saldo com esse principal."""
    if saldo <= 0:
        return 0.0
    parcela = min(1.0, max(0.0, bruto_sacado / saldo))
    rendimento_resgatado = max(0.0, (saldo - principal)) * parcela
    return rendimento_resgatado * aliquota_ir(dias)


def _bruto_para_liquido(liquido_desejado, saldo, principal, dias):
    """(bruto a sacar, IR) para sobrar `liquido_desejado` na conta.

    Fechado, sem tentativa e erro: o IR é proporcional ao bruto resgatado, o
    que deixa a equação linear.

        líquido = bruto - (saldo-principal)/saldo * bruto * alíquota
                = bruto * (1 - fração_de_rendimento * alíquota)
    """
    alvo = max(0.0, float(liquido_desejado or 0.0))
    if saldo <= 0 or alvo <= 0:
        return 0.0, 0.0
    fracao_rendimento = max(0.0, (saldo - principal)) / saldo
    fator = 1.0 - fracao_rendimento * aliquota_ir(dias)
    if fator <= 0:
        return saldo, _ir_do_resgate(saldo, saldo, principal, dias)
    bruto = alvo / fator
    return bruto, _ir_do_resgate(bruto, saldo, principal, dias)


def meses_de_cobertura(linhas):
    """Quantos meses inteiros a reserva ainda paga. Só os que ela COBRE."""
    return sum(1 for l in (linhas or []) if l.get("cobre"))


def resumo(aplicado, bruto, inicio, saque_mensal, **kw):
    """O parágrafo que a tela e o WhatsApp mostram — um só, para não divergir."""
    linhas = projecao(aplicado, bruto, inicio, saque_mensal, **kw)
    if not linhas:
        return {"meses": 0, "ate": "", "linhas": [], "rendimento_total": 0.0}
    cobertos = [l for l in linhas if l["cobre"]]
    ultimo = cobertos[-1] if cobertos else linhas[0]
    return {"meses": len(cobertos),
            "ate": f"{ultimo['mes']:02d}/{ultimo['ano']}",
            "rendimento_total": round(sum(l["rendimento"] for l in linhas), 2),
            "ir_total": round(sum(l["ir"] for l in linhas), 2),
            "linhas": linhas}


# ── Conferência ──────────────────────────────────────────────────────────────
# `python3 reserva.py`. O caso principal é a posição real do CDB do dono,
# tirada do extrato do Itaú de 22/09/2026 — número inventado em teste só prova
# que a conta bate com ela mesma.
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    APLICADO, BRUTO = 270_000.00, 273_642.89
    INICIO, HOJE = "2026-08-14", "2026-09-22"

    # ── o IR por faixa ───────────────────────────────────────────────────
    ok("até 180 dias a alíquota é 22,5%", aliquota_ir(39) == 0.225)
    ok("no dia 180 ainda é 22,5%", aliquota_ir(180) == 0.225)
    ok("no 181 cai para 20%", aliquota_ir(181) == 0.200)
    ok("depois de 360 vai a 17,5%", aliquota_ir(361) == 0.175)
    ok("depois de 720 fica em 15%", aliquota_ir(721) == 0.150)

    # O extrato do Itaú diz: bruto 273.642,89, líquido 272.823,24.
    # A diferença de 819,65 é 22,5% do rendimento de 3.642,89.
    ok("o líquido bate com o extrato do Itaú",
       liquido(APLICADO, BRUTO, INICIO, HOJE) == 272_823.24)

    d, taxa, faltam = proxima_faixa(INICIO, HOJE)
    # 14/08/2026 + 181 dias: o dia 181 e o PRIMEIRO com 20%, e nao o 180.
    ok("a virada de faixa cai em 11/02/2027", d.isoformat() == "2027-02-11")
    ok("e leva para 20%", taxa == 0.200)
    ok("faltam 142 dias", faltam == 142)
    ok("na última faixa não há o que esperar",
       proxima_faixa("2020-01-01", HOJE) is None)

    # ── a taxa que o próprio extrato revela ──────────────────────────────
    t = taxa_implicita(APLICADO, BRUTO, INICIO, HOJE)
    ao_mes = (1 + t) ** 30 - 1
    ok("a taxa implícita dá ~1,04% ao mês", 0.0100 < ao_mes < 0.0107)
    ok("sem data não inventa taxa", taxa_implicita(1, 2, "", "") is None)
    ok("saldo menor que o aplicado não quebra",
       taxa_implicita(100, 99, INICIO, HOJE) < 0)

    # ── a projeção ───────────────────────────────────────────────────────
    L = projecao(APLICADO, BRUTO, INICIO, 30_000.0, de=HOJE, meses=36)
    ok("a projeção anda mês a mês", len(L) > 1)
    ok("o primeiro mês é setembro/2026", (L[0]["ano"], L[0]["mes"]) == (2026, 9))
    ok("os meses são consecutivos",
       all((L[i + 1]["ano"], L[i + 1]["mes"]) ==
           (L[i]["ano"] + 1, 1) if L[i]["mes"] == 12 else
           (L[i + 1]["ano"], L[i + 1]["mes"]) == (L[i]["ano"], L[i]["mes"] + 1)
           for i in range(len(L) - 1)))
    ok("o saldo só desce", all(L[i]["saldo_final"] >= L[i + 1]["saldo_final"]
                               for i in range(len(L) - 1)))

    # O QUE ENGANA: sacar 30 mil do bruto NÃO põe 30 mil na conta.
    ok("o que chega na conta é exatamente o que precisava",
       all(abs(l["recebido"] - l["precisava"]) < 0.02
           for l in L if l["cobre"]))
    ok("e para isso saca-se MAIS que o líquido",
       all(l["sacado_bruto"] > l["precisava"] for l in L if l["cobre"]
           and l["ir"] > 0))

    ok("R$ 30 mil/mês cobrem entre 8 e 10 meses",
       8 <= meses_de_cobertura(L) <= 10)
    ok("o último mês já não cobre", not L[-1]["cobre"])
    ok("e o saldo acaba zerado", L[-1]["saldo_final"] == 0.0)

    # Quanto maior o saque, menos meses. Óbvio — e é o que trava a conta.
    ok("saque maior cobre menos meses",
       meses_de_cobertura(projecao(APLICADO, BRUTO, INICIO, 60_000.0,
                                   de=HOJE, meses=36))
       < meses_de_cobertura(L))

    # ── o bônus de meta, que sai à parte ─────────────────────────────────
    EX = {(2026, 10): 12_000.0, (2026, 11): 60_000.0}
    LE = projecao(APLICADO, BRUTO, INICIO, 30_000.0, de=HOJE, meses=36,
                  extras=EX)
    _out = next(l for l in LE if (l["ano"], l["mes"]) == (2026, 10))
    ok("o bônus entra no mês em que é pago", _out["precisava"] == 42_000.0)
    ok("e encurta a cobertura",
       meses_de_cobertura(LE) < meses_de_cobertura(L))
    ok("o bonus nao muda o saque do mes seguinte",
       next(l for l in LE if (l["ano"], l["mes"]) == (2026, 12))["precisava"]
       == 30_000.0)

    # ── bordas ───────────────────────────────────────────────────────────
    ok("fevereiro não tem dia 30", _dia_valido(2027, 2, 30) == 28)
    ok("nem dia 31 em abril", _dia_valido(2027, 4, 31) == 30)
    ok("sem data de início não projeta", projecao(1, 1, "", 10) == [])
    ok("saque zero não consome a reserva",
       projecao(APLICADO, BRUTO, INICIO, 0.0, de=HOJE, meses=3)[-1]
       ["saldo_final"] > BRUTO)

    r = resumo(APLICADO, BRUTO, INICIO, 30_000.0, de=HOJE, meses=36)
    ok("o resumo diz até quando cobre", "/" in r["ate"])
    ok("e soma o IR pago no caminho", r["ir_total"] > 0)
    ok("reserva vazia devolve resumo vazio",
       resumo(0, 0, INICIO, 30_000.0, de=HOJE)["meses"] == 0)

    print("\nfalhas:", falhas)
    raise SystemExit(falhas)
