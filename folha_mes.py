"""folha_mes.py — quanto cada colaborador recebe no mês, pelo ponto e pelas metas.

O PEDIDO (dono, 30/10)
----------------------
Dia 30 sai o SALÁRIO, e ele tem de bater com o ponto. No 5º dia útil saem as
METAS. Uma aba para o dono ver quanto paga a cada um, e o mesmo resumo para o
colaborador, no fim do "Meu desempenho".

AS HORAS (as palavras dele)
---------------------------
"O saldo total de horas trabalhadas precisa ser o mesmo que eles precisam
cumprir." Por isso a conta é de HORAS, e não de batidas:

    saldo do mês = trabalhadas + abonadas − devidas      (devidas: 8h por dia
                                                          útil, até ontem)
    banco final  = banco do fim do mês anterior (RHiD) + saldo do mês

Quem não saiu para almoçar e fechou 8h não deve nada — a batida faltando não
desconta. Dia que devia horas consome o banco; sem banco, o banco fica
NEGATIVO, e o colaborador vê o alerta. Se o mês FECHAR negativo:

    desconto = horas negativas × valor da hora
    valor da hora = salário ÷ horas do mês (dias úteis do mês × 8h)

O VALOR DA HORA É DO MÊS (dono, 30/10: "são as horas disponíveis de cada
mês"). Outubro/2026 tem 21 dias úteis no calendário do Studio (feriado de
12/10 fora) = 168h; novembro, 19 = 152h. A hora vale mais no mês curto. O
divisor é o mês INTEIRO mesmo com o mês aberto: dividir pelas horas "até
ontem" faria a hora de quem falta no dia 5 valer quatro vezes mais.

O DOMINGO SÓ ONDE O DONO MARCAR (30/10): "deixe um botão de flegar quando
houver falta do dia inteiro, caso for aplicar a regra do domingo eu flego".
Sem marca, a falta desconta só as 8h dela (que deixam o banco negativo).
Marcada, soma o domingo (salário ÷ 30) daquela semana — Lei 605/49, art. 6º —
uma vez por semana, mesmo com duas faltas marcadas nela. A marca é decisão
dele: vale mesmo com banco cobrindo as horas. Fica na aba `folha_domingo` da
planilha (uma linha por falta marcada), e não na memória: deploy não apaga.

Banco positivo só é mostrado (dono: "só mostra o saldo").

O QUE DEPENDE DE CONFIRMAÇÃO FORA DAQUI
---------------------------------------
- O divisor do mês foi decisão do dono (30/10). O padrão da CLT para 40h
  semanais é 200 fixo, com o repouso remunerado dentro; a contabilidade
  confirma qual vai no holerite oficial.
- Banco de horas cobrindo falta exige acordo escrito com o colaborador — o
  dono está alinhando (30/10).

DE ONDE VEM CADA NÚMERO (nada é contado de novo aqui)
----------------------------------------------------
    salário base   colaboradores.folha_clt (com os reajustes do mês)
    horas e abono  analise_metas._pontualidade_do_periodo (a RHiD)
    devidas        analise_metas.horas_devidas_min
    faltas         os dias "sem_batida" de relogio_ponto.pendencia_do_dia
    metas          analise_metas.apuracao_bonus — a mesma do card
"""
from datetime import date

ABA_DOMINGO = "folha_domingo"
COLUNAS_DOMINGO = ["mes", "username", "data", "marcado_por", "marcado_em"]
NIVEIS = (("col", "Coletiva"), ("maxx", "Coletiva MAXX"),
          ("ind", "Individual"), ("ind_maxx", "Individual MAXX"))


def reais(minutos, salario, horas_do_mes_min):
    """O valor em R$ de `minutos` de trabalho: minutos × salário ÷ horas do
    mês, arredondado em CENTAVOS, meio centavo para cima. Pura.

    Conta exata (frações), e não em ponto flutuante: 5h27 × R$ 12,50 dá
    R$ 68,125, que o `round` do Python deixava em 68,12 — o holerite saía um
    centavo diferente da conta feita à mão (30/10). Uma regra só, usada pela
    folha e pelo holerite."""
    from decimal import Decimal, ROUND_HALF_UP
    from fractions import Fraction
    if not horas_do_mes_min:
        return 0.0
    q = Fraction(str(minutos)) * Fraction(str(salario)) / Fraction(str(horas_do_mes_min))
    neg = q < 0
    v = (Decimal(abs(q.numerator)) / Decimal(q.denominator)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(-v if neg else v)


def semanas_com_falta(datas_iso):
    """Quantas semanas (seg–dom) têm ao menos uma falta de dia inteiro. Pura."""
    sem = set()
    for d in datas_iso or []:
        try:
            sem.add(date.fromisoformat(str(d)[:10]).isocalendar()[:2])
        except ValueError:
            continue
    return len(sem)


def apurar(salario, trab_min, abono_min, devido_min, banco_anterior_min=0.0,
           faltas_dia_inteiro=(), fechado=False, domingo_nas=(), horas_do_mes_min=None):
    """O salário de uma pessoa no mês. Pura.

    Devolve {"salario","saldo_mes_min","banco_final_min","usado_do_banco_min",
             "negativo_min","valor_hora","desconto_horas","semanas_falta",
             "desconto_domingo","desconto","salario_pagar","fechado"}.
    Mês aberto: o desconto é o que SERIA se fechasse hoje; o salário a pagar
    ainda é o base — quem decide é o fechamento.
    `domingo_nas`: as faltas que o dono marcou para descontar o domingo. Só
    conta a marca que é falta de dia inteiro deste mês — marca que sobrou de
    uma falta abonada depois não desconta nada.
    """
    salario = float(salario or 0)
    saldo = float(trab_min or 0) + float(abono_min or 0) - float(devido_min or 0)
    anterior = float(banco_anterior_min or 0)
    final = anterior + saldo
    usado = min(max(anterior, 0.0), max(-saldo, 0.0))
    negativo = max(-final, 0.0)
    # Sem as horas do mês não há valor da hora — e um padrão escondido aqui
    # seria um salário errado em silêncio.
    if not horas_do_mes_min:
        raise ValueError("apurar: falta horas_do_mes_min (dias úteis do mês × jornada)")
    valor_hora = salario / (float(horas_do_mes_min) / 60) if salario else 0.0
    desc_h = reais(negativo, salario, horas_do_mes_min)
    _faltas = {str(x)[:10] for x in faltas_dia_inteiro or ()}
    semanas = semanas_com_falta([x for x in domingo_nas or () if str(x)[:10] in _faltas])
    desc_dom = reais(semanas, salario, 30)
    desconto = round(desc_h + desc_dom, 2)
    return {"salario": salario, "saldo_mes_min": round(saldo, 1),
            "banco_final_min": round(final, 1), "usado_do_banco_min": round(usado, 1),
            "negativo_min": round(negativo, 1), "valor_hora": round(valor_hora, 4),
            "desconto_horas": desc_h, "semanas_falta": semanas,
            "desconto_domingo": desc_dom, "desconto": desconto,
            "salario_pagar": round(salario - (desconto if fechado else 0.0), 2),
            "salario_se_fechasse_hoje": round(salario - desconto, 2),
            "fechado": bool(fechado)}


def metas(salario, b):
    """[(rotulo, %, valor, batida, motivo)] das quatro metas e o total. Pura.

    `b` é a linha de `analise_metas.apuracao_bonus` da pessoa. A MAXX toma o
    lugar da mensal em cada metade (`explicacao_metas.bonus_percentuais`),
    então a mensal batida junto com a MAXX aparece batida, mas não paga."""
    import explicacao_metas as _ex
    salario = float(salario or 0)
    pcts = {"col": _ex.PCT_COLETIVO_MENSAL, "maxx": _ex.PCT_COLETIVO_MAXX,
            "ind": _ex.PCT_INDIVIDUAL_MENSAL, "ind_maxx": _ex.PCT_INDIVIDUAL_MAXX}
    b = b or {}
    pct_time, pct_seu = _ex.bonus_percentuais(bool(b.get("col")), bool(b.get("maxx")),
                                              bool(b.get("ind")), bool(b.get("ind_maxx")))
    pagas = {"col": bool(b.get("col")) and not b.get("maxx"), "maxx": bool(b.get("maxx")),
             "ind": bool(b.get("ind")) and not b.get("ind_maxx"),
             "ind_maxx": bool(b.get("ind_maxx"))}
    linhas = []
    for chave, rot in NIVEIS:
        bateu = bool(b.get(chave))
        motivo = ""
        if not bateu:
            if chave == "col" and not (b.get("el") or {}).get("entra_col", True):
                motivo = "não entrou"
            elif chave == "maxx" and not (b.get("el") or {}).get("entra_maxx", True):
                motivo = "não entrou"
        valor = round(salario * pcts[chave] / 100, 2) if pagas[chave] else 0.0
        linhas.append((rot, pcts[chave], valor, bateu, motivo, pagas[chave]))
    total_pct = pct_time + pct_seu
    return linhas, total_pct, round(salario * total_pct / 100, 2)


def dia_do_pagamento(ano, mes):
    """O dia em que o salário cai (dono, 30/10): dia 30; em fevereiro, dia 28;
    em sábado ou domingo, na sexta antes. Feriado não entra — o Studio não
    tem o calendário de feriados para isto. Pura."""
    from datetime import timedelta
    d = date(ano, mes, 28 if mes == 2 else 30)
    return d - timedelta(days=max(d.weekday() - 4, 0))


def periodo(ano, mes):
    """(início, fim) do ponto que paga o salário de (ano, mes). Pura.

    Dono, 30/10: "do dia 30 do mês anterior até dia 29", porque o depósito sai
    no dia 30 e não dá para esperar ele acabar. Em regra geral: do dia do
    pagamento anterior até a véspera do pagamento deste mês."""
    from datetime import timedelta
    a, m = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
    return dia_do_pagamento(a, m), dia_do_pagamento(ano, mes) - timedelta(days=1)


def competencia(hoje):
    """(ano, mes) do período ABERTO em `hoje`: depois da véspera do pagamento
    o período já é o do mês seguinte. Pura."""
    d = hoje.date() if hasattr(hoje, "date") else hoje
    if d > periodo(d.year, d.month)[1]:
        return (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return d.year, d.month


def _dias_uteis(ini, fim):
    import placar_core as _pc
    from datetime import timedelta
    n, d = 0, ini
    while d <= fim:
        n += bool(_pc.eh_dia_util(d))
        d += timedelta(days=1)
    return n


def ponto_da_pessoa(dias, ini, fim, hoje, jornada=480.0):
    """O ponto de uma pessoa no período, a partir dos `dias` da RHiD
    (`relogio_ponto._pontualidade_rhid_intervalo`). Pura.

    Só conta dia FECHADO (o de hoje ainda não acabou) e dentro do período.
    Devolve trabalhado, abonado, devido (dias úteis fechados × jornada),
    horas do período inteiro (o divisor do valor da hora), as faltas de dia
    inteiro, as pendências e os dias em ordem."""
    from datetime import timedelta
    d_hoje = hoje.date() if hasattr(hoje, "date") else hoje
    i_s, f_s = ini.isoformat(), fim.isoformat()
    meus = sorted([x for x in dias or [] if i_s <= str(x.get("data", ""))[:10] <= f_s],
                  key=lambda x: x["data"])
    fech = [x for x in meus if x.get("fechado")]
    ate = min(fim, d_hoje - timedelta(days=1))
    return {"min_trab": sum(float(x.get("min_trab") or 0) for x in fech),
            "min_abono": sum(float(x.get("min_abono") or 0) for x in fech),
            "devidas_min": (_dias_uteis(ini, ate) if ate >= ini else 0) * jornada,
            "horas_do_mes_min": _dias_uteis(ini, fim) * jornada,
            "faltas": [x["data"] for x in fech if x.get("pendencia") == "sem_batida"],
            "pendencias": [{"data": x["data"], "tipo": x["pendencia"],
                            "batidas": list(x.get("batidas") or [])}
                           for x in fech if x.get("pendencia")],
            "dias": meus}


def banco_antes(dias, ini):
    """O saldo do banco da RHiD no último dia ANTES do período (minutos). O
    campo da RHiD já é acumulado; o último valor preenchido é o saldo. Pura."""
    for x in sorted(dias or [], key=lambda x: x["data"], reverse=True):
        if str(x["data"])[:10] < ini.isoformat() and x.get("saldo_banco") not in (None, ""):
            return float(x["saldo_banco"])
    return 0.0


def do_mes(ano, mes, dados, ponto, bonus, hoje, salarios=None, domingos=None):
    """{username: {"folha", "metas", "pct_metas", "metas_valor", "total", ...}}.

    O SALÁRIO é do PERÍODO (`periodo`: do dia 30 ao 29); as METAS são do mês
    do calendário, da apuração já feita (`bonus`, a do `meu_desempenho`).
    `ponto` é a leitura da RHiD por intervalo, começando uma semana antes do
    período — de lá sai o banco anterior (`banco_antes`). Quem não tem
    salário cadastrado fica de fora (None), em vez de aparecer recebendo zero."""
    import placar_core as _pc
    if salarios is None:
        salarios = salarios_do_mes(ano, mes)
    if domingos is None:
        domingos = domingos_marcados(ano, mes)
    ini, fim = periodo(ano, mes)
    d_hoje = hoje.date() if hasattr(hoje, "date") else hoje
    fechado = d_hoje > fim
    jornada = float(((dados[-1] or {}).get("cfg") or {}).get("jornada_diaria_min", 480) or 480) \
        if dados else 480.0
    fora = {}
    for u in _pc.MEMBROS_ATIVOS:
        sal = salarios.get(u)
        if not sal:
            fora[u] = None
            continue
        dias = ((ponto or {}).get(u) or {}).get("dias") or []
        pp = ponto_da_pessoa(dias, ini, fim, hoje, jornada)
        faltas = pp["faltas"]
        marcados = [d for d in domingos.get(u, []) if d in faltas]
        anterior = banco_antes(dias, ini)
        f = apurar(sal, pp["min_trab"], pp["min_abono"], pp["devidas_min"], anterior,
                   faltas, fechado, marcados, horas_do_mes_min=pp["horas_do_mes_min"])
        f["banco_anterior_min"] = anterior
        linhas, pct, valor = metas(sal, (bonus or {}).get(u))
        fora[u] = {"folha": f, "metas": linhas, "pct_metas": pct, "metas_valor": valor,
                   "faltas": faltas, "domingo_nas": marcados,
                   "devidas_min": pp["devidas_min"], "horas_do_mes_min": pp["horas_do_mes_min"],
                   "pendencias": pp["pendencias"], "dias": pp["dias"],
                   "periodo": (ini.isoformat(), fim.isoformat()),
                   "pagamento": dia_do_pagamento(ano, mes).isoformat(),
                   "total": round(f["salario_pagar"] + valor, 2)}
    return fora


def _aba_domingo():
    import sheets as _sh
    pl = _sh.planilha()
    try:
        return pl.worksheet(ABA_DOMINGO)
    except Exception:
        a = pl.add_worksheet(title=ABA_DOMINGO, rows=200, cols=len(COLUNAS_DOMINGO))
        a.append_row(COLUNAS_DOMINGO, value_input_option="RAW")
        return a


def domingos_de(linhas, ano, mes):
    """{username: [datas ISO]} marcadas no mês, das linhas da aba. Pura."""
    chave = f"{ano:04d}-{mes:02d}"
    fora = {}
    for l in linhas or []:
        if str(l.get("mes", "")).strip() == chave and l.get("username") and l.get("data"):
            fora.setdefault(str(l["username"]).strip(), []).append(str(l["data"]).strip()[:10])
    return fora


def domingos_marcados(ano, mes):
    """As faltas marcadas pelo dono para descontar o domingo. NÃO engole erro:
    planilha fora do ar vira `dinheiro_erro` na tela, e não domingo esquecido."""
    return domingos_de(_aba_domingo().get_all_records(), ano, mes)


def linhas_com_marcas(linhas, ano, mes, marcas, por, quando):
    """As linhas da aba depois de trocar as marcas do mês. Pura.

    `marcas`: {username: [datas]} — a escolha INTEIRA do mês, como a tela
    mostra. Os outros meses ficam como estão; quem marcou e quando, também,
    para a marca que não mudou."""
    chave = f"{ano:04d}-{mes:02d}"
    antes = {(str(l.get("username")), str(l.get("data"))[:10]): l for l in linhas or []
             if str(l.get("mes", "")).strip() == chave}
    fora = [l for l in linhas or [] if str(l.get("mes", "")).strip() != chave]
    for u, datas in sorted((marcas or {}).items()):
        for d in sorted(set(datas)):
            fora.append(antes.get((u, d)) or {"mes": chave, "username": u, "data": d,
                                               "marcado_por": por, "marcado_em": quando})
    return fora


def gravar_domingos(ano, mes, marcas, por):
    """Grava a escolha do mês (`linhas_com_marcas`). Levanta erro: a tela diz."""
    import placar_core as _pc
    a = _aba_domingo()
    novas = linhas_com_marcas(a.get_all_records(), ano, mes, marcas, por,
                              _pc.agora_br().strftime("%d/%m/%Y %H:%M"))
    a.clear()
    a.update([COLUNAS_DOMINGO] + [[str(l.get(c, "")) for c in COLUNAS_DOMINGO] for l in novas],
             value_input_option="RAW")


def salarios_do_mes(ano, mes):
    """{username: salário base do mês}, pela folha (com os reajustes).

    NÃO engole erro (30/10): devolver {} com a planilha fora do ar fazia a
    tela dizer "sem salário cadastrado" — o defeito virava cadastro. O erro
    sobe e vira `dinheiro_erro`, que a tela mostra."""
    import colaboradores as _co
    import placar_core as _pc
    df = _co.carregar()
    aj = _co._aj().carregar()
    linhas = _co.folha_clt(df, ano, mes, _co.carregar_taxas(), aj)
    return {_pc.username_do_login(l.get("funcionario", "")): float(l.get("base") or 0)
            for l in linhas if l.get("funcionario")}


def h(minutos):
    """Minutos em "+6h20" / "−1h15" / "0h00". Pura."""
    m = int(round(float(minutos or 0)))
    s = "−" if m < 0 else ("+" if m > 0 else "")
    m = abs(m)
    return f"{s}{m // 60}h{m % 60:02d}"


if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    _d = 22 * 480
    # As contas puras com um mês de 22 dias úteis: 176h, e R$ 2.200 ÷ 176 = R$ 12,50/h.
    _ap = lambda *a, **k: apurar(*a, horas_do_mes_min=_d, **k)
    a = _ap(2200, _d - 120, 0, _d, 0, [], fechado=True)
    ok("o exemplo do dono: sem almoço, fechou as horas do dia → nada a descontar",
       _ap(2200, _d, 0, _d, 0, ["2026-10-14"], True)["desconto"] == 0)
    ok("devendo 2h sem banco: banco −2h e desconto de 2h (2200 ÷ 176h = R$ 12,50/h)",
       a["banco_final_min"] == -120 and a["desconto_horas"] == 25.0
       and a["salario_pagar"] == 2175.0)
    b = _ap(2200, _d - 120, 0, _d, 300, [], True)
    ok("devendo 2h com 5h de banco: o banco cobre, fica +3h, sem desconto",
       b["banco_final_min"] == 180 and b["usado_do_banco_min"] == 120 and b["desconto"] == 0)
    _sem = _ap(2200, _d - 480, 0, _d, 0, ["2026-10-14"], True)
    ok("falta SEM marca do dono: desconta as 8h, e o domingo NÃO",
       _sem["desconto_horas"] == 100.0 and _sem["desconto_domingo"] == 0
       and _sem["semanas_falta"] == 0 and _sem["salario_pagar"] == 2100.0)
    c = _ap(2200, _d - 480, 0, _d, 0, ["2026-10-14"], True, ["2026-10-14"])
    ok("falta MARCADA pelo dono: 8h + o domingo da semana",
       c["desconto_horas"] == 100.0 and c["desconto_domingo"] == round(2200 / 30, 2)
       and c["semanas_falta"] == 1)
    c2 = _ap(2200, _d - 480, 0, _d, 600, ["2026-10-14"], True, ["2026-10-14"])
    ok("marcada com banco cobrindo as horas: o banco cobre as 8h, o domingo é a marca dele",
       c2["desconto_horas"] == 0 and c2["desconto"] == round(2200 / 30, 2)
       and c2["banco_final_min"] == 120)
    ok("marca que não é falta (abonada depois) não desconta nada",
       _ap(2200, _d, 0, _d, 0, [], True, ["2026-10-14"])["desconto"] == 0)
    ok("duas marcadas na mesma semana: um domingo só",
       _ap(2200, _d - 960, 0, _d, 0, ["2026-10-13", "2026-10-14"], True,
              ["2026-10-13", "2026-10-14"])["semanas_falta"] == 1)
    # A aba da planilha: trocar as marcas do mês não mexe nos outros meses,
    # e a marca que ficou guarda quem marcou primeiro.
    _ant = [{"mes": "2026-09", "username": "luiz", "data": "2026-09-15",
             "marcado_por": "MartinSousa", "marcado_em": "30/09/2026 10:00"},
            {"mes": "2026-10", "username": "luiz", "data": "2026-10-14",
             "marcado_por": "MartinSousa", "marcado_em": "29/10/2026 09:00"},
            {"mes": "2026-10", "username": "bia", "data": "2026-10-07",
             "marcado_por": "MartinSousa", "marcado_em": "29/10/2026 09:00"}]
    _nov = linhas_com_marcas(_ant, 2026, 10, {"luiz": ["2026-10-14", "2026-10-21"]},
                             "MartinSousa", "30/10/2026 12:00")
    ok("gravar: setembro intacto, a desmarcada sai, a nova entra, a antiga guarda a data",
       _nov[0] == _ant[0] and len(_nov) == 3
       and _nov[1]["marcado_em"] == "29/10/2026 09:00" and _nov[2]["data"] == "2026-10-21"
       and not any(l["username"] == "bia" for l in _nov))
    # GRAVAR DE VERDADE contra uma aba de mentira: escreve o cabeçalho e as
    # linhas na ordem de COLUNAS_DOMINGO, e lê de volta o que a tela escolheu.
    class _AbaFalsa:
        def __init__(self, linhas):
            self.linhas, self.escrito = linhas, None

        def get_all_records(self):
            return self.linhas

        def clear(self):
            self.escrito = []

        def update(self, valores, **k):
            self.escrito = valores
    _af = _AbaFalsa(list(_ant))
    _g_aba = globals()["_aba_domingo"]
    globals()["_aba_domingo"] = lambda: _af
    try:
        gravar_domingos(2026, 10, {"luiz": ["2026-10-21"]}, "MartinSousa")
    finally:
        globals()["_aba_domingo"] = _g_aba
    _volta = [dict(zip(_af.escrito[0], l)) for l in _af.escrito[1:]]
    ok("gravar_domingos: cabeçalho certo, setembro intacto, outubro só com a escolha nova",
       _af.escrito[0] == COLUNAS_DOMINGO
       and domingos_de(_volta, 2026, 10) == {"luiz": ["2026-10-21"]}
       and domingos_de(_volta, 2026, 9) == {"luiz": ["2026-09-15"]}
       and _volta[-1]["marcado_por"] == "MartinSousa")
    ok("ler: só o mês pedido", domingos_de(_nov, 2026, 10) == {"luiz": ["2026-10-14", "2026-10-21"]}
       and domingos_de(_nov, 2026, 9) == {"luiz": ["2026-09-15"]})
    ok("duas faltas na mesma semana tiram um domingo; em semanas diferentes, dois",
       semanas_com_falta(["2026-10-13", "2026-10-14"]) == 1
       and semanas_com_falta(["2026-10-13", "2026-10-21"]) == 2)
    d = _ap(2200, _d - 120, 60, _d, 0, [], False)
    ok("abono conta como hora; mês aberto mostra o desconto mas não o aplica ainda",
       d["banco_final_min"] == -60 and d["salario_pagar"] == 2200.0
       and d["salario_se_fechasse_hoje"] == 2187.5)
    ok("banco positivo só é mostrado, não vira dinheiro",
       _ap(2200, _d + 300, 0, _d, 0, [], True)["salario_pagar"] == 2200.0)

    # METAS pela regra do card (explicacao_metas): a MAXX toma o lugar.
    _l, _p, _v = metas(2200, {"col": True, "maxx": False, "ind": False, "ind_maxx": False})
    ok("coletiva batida: 12% de R$ 2.200 = R$ 264", _p == 12.0 and _v == 264.0
       and _l[0][2] == 264.0 and _l[0][3])
    _l, _p, _v = metas(2400, {"col": True, "maxx": True, "ind": True, "ind_maxx": True})
    ok("as duas MAXX: 18% + 12% = 30%, e a mensal batida não paga em dobro",
       _p == 30.0 and _v == 720.0 and _l[0][2] == 0.0 and _l[1][2] == 432.0)
    _l, _p, _v = metas(2000, {"el": {"entra_col": False}})
    ok("quem não entrou na coletiva vê o motivo", _l[0][4] == "não entrou" and _v == 0)
    # PELA CADEIA, DA RHiD À FOLHA: os registros no formato de
    # `rhid_api.get_registros_diarios`, passados pela leitura de verdade
    # (`relogio_ponto.get_ponto_do_periodo`); só a rede é trocada.
    # Setembro/2026 paga o período 28/08 (sexta, pagamento de agosto) a 29/09:
    # 22 dias úteis (07/09 é feriado) = 176h; R$ 3.000 ÷ 176 = R$ 17,045/h.
    import placar_core as _pc_t
    import relogio_ponto as _rp_t
    import rhid_api as _rh_t
    from datetime import datetime as _dt_t, timedelta as _td_t
    _u = next(u for u in _pc_t.MEMBROS_ATIVOS if u in _rp_t.MEMBROS)
    _hoje = _dt_t(2026, 10, 30, 10, 0, tzinfo=_pc_t.FUSO)
    ok("período de setembro: 28/08 (sexta) a 29/09; pagamento 30/09",
       periodo(2026, 9) == (date(2026, 8, 28), date(2026, 9, 29))
       and dia_do_pagamento(2026, 9) == date(2026, 9, 30))
    ok("período de outubro: 30/09 a 29/10 — o do dono",
       periodo(2026, 10) == (date(2026, 9, 30), date(2026, 10, 29)))
    ok("competência: até 29/10 é outubro; no dia 30, novembro",
       competencia(date(2026, 10, 29)) == (2026, 10) and competencia(date(2026, 10, 30)) == (2026, 11))

    def _reg(d, bat, trab, banco=None):
        return {"data": d, "batidas": bat, "entrada": bat[0] if bat else None,
                "saida_almoco": None, "volta_almoco": None,
                "saida": bat[-1] if len(bat) > 1 else None, "minutos_atraso": 0.0,
                "minutos_trabalhados": trab, "faltou": not bat,
                "saldo_banco": banco, "minutos_abonados": 0.0}
    _regs = [_reg(date(2026, 8, 21), ["09:00", "18:00"], 480.0, banco=120.0)]
    _dt = date(2026, 8, 28)
    while _dt <= date(2026, 9, 29):
        if _pc_t.eh_dia_util(_dt):
            if _dt == date(2026, 9, 15):
                _regs.append(_reg(_dt, [], 0.0))                         # falta
            elif _dt == date(2026, 9, 16):
                _regs.append(_reg(_dt, ["09:00", "12:00", "13:00"], 420.0))  # ímpar, 7h
            else:
                _regs.append(_reg(_dt, ["09:00", "12:00", "13:00", "18:00"], 480.0))
        _dt += _td_t(days=1)
    _g = (_rh_t.get_persons, _rh_t.get_registros_diarios, _rp_t._rhid_nome_para_trello)
    try:
        _rh_t.get_persons = lambda: [{"id": 1, "name": "X"}]
        _rh_t.get_registros_diarios = lambda a, b, c: (_regs, {})
        _rp_t._rhid_nome_para_trello = lambda n: _u
        getattr(_rp_t._pontualidade_rhid_intervalo, "clear", lambda: None)()
        _ponto = _rp_t.get_ponto_do_periodo(date(2026, 8, 21), date(2026, 9, 29))[0]
    finally:
        _rh_t.get_persons, _rh_t.get_registros_diarios, _rp_t._rhid_nome_para_trello = _g
    _dados = [{"filtro_mes": (2026, 9), "cfg": {}}]
    _r = do_mes(2026, 9, _dados, _ponto, {_u: {"col": True}}, _hoje,
                salarios={_u: 3000.0}, domingos={})
    _f = _r[_u]["folha"]
    ok("cadeia: 22 dias úteis no período = 176h, e o banco anterior (2h) vem do dia 21/08",
       _r[_u]["horas_do_mes_min"] == 22 * 480 and _r[_u]["devidas_min"] == 22 * 480
       and _f["banco_anterior_min"] == 120.0 and _r[_u]["periodo"] == ("2026-08-28", "2026-09-29"))
    ok("cadeia: falta 8h + 1h do dia ímpar − 2h de banco = 7h descontadas (R$ 119,32)",
       _f["fechado"] and _f["saldo_mes_min"] == -540 and _f["banco_final_min"] == -420
       and _f["desconto_horas"] == 119.32 and _f["salario_pagar"] == 2880.68
       and _r[_u]["faltas"] == ["2026-09-15"] and _r[_u]["metas_valor"] == 360.0)
    ok("cadeia: a pendência ímpar do período chega, para o aviso e o holerite",
       [(x["data"], x["tipo"]) for x in _r[_u]["pendencias"]]
       == [("2026-09-15", "sem_batida"), ("2026-09-16", "incompleta")]
       and _r[_u]["dias"][0]["data"] == "2026-08-28")
    # A marca do dono pela cadeia, no formato que `domingos_de` devolve da
    # aba — e a da data que é só "incompleta" não conta.
    _r2 = do_mes(2026, 9, _dados, _ponto, {_u: {"col": True}}, _hoje,
                 salarios={_u: 3000.0},
                 domingos=domingos_de([{"mes": "2026-09", "username": _u, "data": "2026-09-15"},
                                       {"mes": "2026-09", "username": _u, "data": "2026-09-16"}],
                                      2026, 9))
    ok("cadeia: com a falta de 15/09 marcada, soma o domingo (R$ 100) e só ele",
       _r2[_u]["domingo_nas"] == ["2026-09-15"] and _r2[_u]["folha"]["desconto_domingo"] == 100.0
       and _r2[_u]["folha"]["salario_pagar"] == 2780.68)
    ok("cadeia: quem não tem salário na folha fica de fora, e não recebendo zero",
       all(v is None for k, v in _r.items() if k != _u))
    ok("valor-hora = salário ÷ horas do mês (176h → R$ 12,50; 152h → R$ 14,47)",
       _ap(2200, 0, 0, 0)["valor_hora"] == 12.5
       and round(apurar(2200, 0, 0, 0, horas_do_mes_min=19 * 480)["valor_hora"], 2) == 14.47)
    try:
        apurar(2200, 0, 0, 0)
        _sem_div = False
    except ValueError:
        _sem_div = True
    ok("sem as horas do mês, recusa em vez de inventar um divisor", _sem_div)
    # O período ABERTO divide pelo período inteiro, e não pelas horas até ontem.
    _ro = do_mes(2026, 10, [{"filtro_mes": (2026, 10), "cfg": {}}], {}, {},
                 _dt_t(2026, 10, 6, 10, tzinfo=_pc_t.FUSO), salarios={_u: 2100.0}, domingos={})
    ok("período aberto: valor da hora por 30/09–29/10 inteiro (21 dias = 168h → R$ 12,50)",
       _ro[_u]["horas_do_mes_min"] == 21 * 480 and _ro[_u]["folha"]["valor_hora"] == 12.5
       and not _ro[_u]["folha"]["fechado"] and _ro[_u]["devidas_min"] == 4 * 480)
    # O SALÁRIO DA FOLHA pela cadeia: `colaboradores.folha_clt` de verdade,
    # com a grade sugerida; só a planilha trocada.
    import colaboradores as _co_t
    import pandas as _pd_t
    _g_co = (_co_t.carregar, _co_t._aj, _co_t.carregar_taxas)
    _pad = {"cargo": _co_t.CARGO_PADRAO, "registrado": "Sim",
            "salario_base": _co_t.SALARIO_PADRAO, "admissao": "2026-01",
            "dias_uteis": 22, "no_aporte": "Sim"}
    try:
        _co_t.carregar = lambda *a, **k: _pd_t.DataFrame([{**_pad, **p} for p in _co_t.SUGESTOES])
        _aj_mod = _co_t._aj()
        _co_t._aj = lambda: type("A", (), {"carregar": staticmethod(
            lambda *a, **k: _pd_t.DataFrame(columns=_aj_mod.COLUNAS))})
        _co_t.carregar_taxas = lambda *a, **k: _co_t.taxas_padrao()
        _sal_t = salarios_do_mes(2026, 10)
        _ok_sal = _sal_t.get(_pc_t.username_do_login("Gabriel"), 0) > 0
        _co_t.carregar = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("planilha fora"))
        try:
            salarios_do_mes(2026, 10)
            _sobe = False
        except RuntimeError:
            _sobe = True
    finally:
        _co_t.carregar, _co_t._aj, _co_t.carregar_taxas = _g_co
    ok("salarios_do_mes: o salário da folha chega por username; planilha fora sobe erro",
       _ok_sal and _sobe)
    ok("reais: meio centavo para cima, em conta exata (5h27 × R$ 12,50 = R$ 68,13)",
       reais(327, 2100, 168 * 60) == 68.13 and reais(-327, 2100, 168 * 60) == -68.13
       and _ap(2100, 9600 - 327, 0, 9600)["desconto_horas"] == round(327 * 2100 / (176 * 60) + 1e-9, 2))
    ok("h: formata saldo com sinal", h(380) == "+6h20" and h(-75) == "−1h15" and h(0) == "0h00")
    print("\nfalhas:", falhas)
    raise SystemExit(1 if falhas else 0)
