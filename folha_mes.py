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

    desconto = horas negativas × (salário ÷ DIVISOR_HORAS)
             + o domingo (salário ÷ 30) de cada semana com falta de dia
               inteiro sem batida e sem abono — Lei 605/49, art. 6º: falta
               sem justificativa na semana tira o repouso remunerado

Banco positivo só é mostrado (dono: "só mostra o saldo").

O QUE DEPENDE DE CONFIRMAÇÃO FORA DAQUI
---------------------------------------
- DIVISOR_HORAS = 200: jornada de 40h semanais (8h, segunda a sexta,
  `analise_metas.horas_devidas_min`). A contabilidade confirma.
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

DIVISOR_HORAS = 200
NIVEIS = (("col", "Coletiva"), ("maxx", "Coletiva MAXX"),
          ("ind", "Individual"), ("ind_maxx", "Individual MAXX"))


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
           faltas_dia_inteiro=(), fechado=False):
    """O salário de uma pessoa no mês. Pura.

    Devolve {"salario","saldo_mes_min","banco_final_min","usado_do_banco_min",
             "negativo_min","valor_hora","desconto_horas","semanas_falta",
             "desconto_domingo","desconto","salario_pagar","fechado"}.
    Mês aberto: o desconto é o que SERIA se fechasse hoje; o salário a pagar
    ainda é o base — quem decide é o fechamento.
    """
    salario = float(salario or 0)
    saldo = float(trab_min or 0) + float(abono_min or 0) - float(devido_min or 0)
    anterior = float(banco_anterior_min or 0)
    final = anterior + saldo
    usado = min(max(anterior, 0.0), max(-saldo, 0.0))
    negativo = max(-final, 0.0)
    valor_hora = salario / DIVISOR_HORAS if salario else 0.0
    desc_h = round(negativo / 60 * valor_hora, 2)
    semanas = semanas_com_falta(faltas_dia_inteiro) if negativo > 0 else 0
    desc_dom = round(semanas * salario / 30, 2)
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


def do_mes(ano, mes, dados, pont, bonus, hoje, salarios=None, bancos_anteriores=None):
    """{username: {"folha", "metas", "pct_metas", "metas_valor", "total"}} do mês.

    Recebe a apuração JÁ FEITA (a do `meu_desempenho.resumo_do_mes`): nada de
    Trello lido duas vezes. Só busca o que ela não tem — o salário do mês e o
    banco da RHiD no fim do mês anterior. Quem não tem salário cadastrado
    fica de fora (None), em vez de aparecer recebendo zero."""
    import analise_metas as _am
    import placar_core as _pc
    if salarios is None:
        salarios = salarios_do_mes(ano, mes)
    if bancos_anteriores is None:
        bancos_anteriores = bancos_do_mes_anterior(ano, mes)
    devidas = _am.horas_devidas_min(dados, (dados[-1] or {}).get("cfg") if dados else None, hoje)
    fechado = (ano, mes) < (hoje.year, hoje.month)
    fora = {}
    for u in _pc.MEMBROS_ATIVOS:
        sal = salarios.get(u)
        if not sal:
            fora[u] = None
            continue
        p = (pont or {}).get(u) or {}
        faltas = [x.get("data") for x in p.get("pend") or [] if x.get("tipo") == "sem_batida"]
        f = apurar(sal, p.get("min_trab", 0.0), p.get("min_abono", 0.0), devidas,
                   bancos_anteriores.get(u, 0.0), faltas, fechado)
        linhas, pct, valor = metas(sal, (bonus or {}).get(u))
        fora[u] = {"folha": f, "metas": linhas, "pct_metas": pct, "metas_valor": valor,
                   "faltas": faltas, "devidas_min": devidas,
                   "total": round(f["salario_pagar"] + valor, 2)}
    return fora


def salarios_do_mes(ano, mes):
    """{username: salário base do mês}, pela folha (com os reajustes)."""
    import colaboradores as _co
    import placar_core as _pc
    try:
        df = _co.carregar()
        aj = _co._aj().carregar()
        linhas = _co.folha_clt(df, ano, mes, _co.carregar_taxas(), aj)
    except Exception:
        return {}
    return {_pc.username_do_login(l.get("funcionario", "")): float(l.get("base") or 0)
            for l in linhas if l.get("funcionario")}


def bancos_do_mes_anterior(ano, mes):
    """{username: banco da RHiD no fim do mês anterior, em minutos}."""
    import relogio_ponto as _rp
    a, m = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
    try:
        return {u: float((r or {}).get("banco_min", 0.0) or 0.0)
                for u, r in (_rp.get_pontualidade_mes(a, m) or {}).items()}
    except Exception:
        return {}


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
    a = apurar(2200, _d - 120, 0, _d, 0, [], fechado=True)
    ok("o exemplo do dono: sem almoço, fechou as horas do dia → nada a descontar",
       apurar(2200, _d, 0, _d, 0, ["2026-10-14"], True)["desconto"] == 0)
    ok("devendo 2h sem banco: banco −2h e desconto de 2h (2200 ÷ 200 = R$ 11/h)",
       a["banco_final_min"] == -120 and a["desconto_horas"] == 22.0
       and a["salario_pagar"] == 2178.0)
    b = apurar(2200, _d - 120, 0, _d, 300, [], True)
    ok("devendo 2h com 5h de banco: o banco cobre, fica +3h, sem desconto",
       b["banco_final_min"] == 180 and b["usado_do_banco_min"] == 120 and b["desconto"] == 0)
    c = apurar(2200, _d - 480, 0, _d, 0, ["2026-10-14"], True)
    ok("falta de dia inteiro sem banco: 8h + o domingo da semana",
       c["desconto_horas"] == 88.0 and c["desconto_domingo"] == round(2200 / 30, 2)
       and c["semanas_falta"] == 1)
    c2 = apurar(2200, _d - 480, 0, _d, 600, ["2026-10-14"], True)
    ok("falta de dia inteiro coberta pelo banco: não perde o domingo",
       c2["desconto"] == 0 and c2["banco_final_min"] == 120)
    ok("duas faltas na mesma semana tiram um domingo; em semanas diferentes, dois",
       semanas_com_falta(["2026-10-13", "2026-10-14"]) == 1
       and semanas_com_falta(["2026-10-13", "2026-10-21"]) == 2)
    d = apurar(2200, _d - 120, 60, _d, 0, [], False)
    ok("abono conta como hora; mês aberto mostra o desconto mas não o aplica ainda",
       d["banco_final_min"] == -60 and d["salario_pagar"] == 2200.0
       and d["salario_se_fechasse_hoje"] == 2189.0)
    ok("banco positivo só é mostrado, não vira dinheiro",
       apurar(2200, _d + 300, 0, _d, 0, [], True)["salario_pagar"] == 2200.0)

    # METAS pela regra do card (explicacao_metas): a MAXX toma o lugar.
    _l, _p, _v = metas(2200, {"col": True, "maxx": False, "ind": False, "ind_maxx": False})
    ok("coletiva batida: 12% de R$ 2.200 = R$ 264", _p == 12.0 and _v == 264.0
       and _l[0][2] == 264.0 and _l[0][3])
    _l, _p, _v = metas(2400, {"col": True, "maxx": True, "ind": True, "ind_maxx": True})
    ok("as duas MAXX: 18% + 12% = 30%, e a mensal batida não paga em dobro",
       _p == 30.0 and _v == 720.0 and _l[0][2] == 0.0 and _l[1][2] == 432.0)
    _l, _p, _v = metas(2000, {"el": {"entra_col": False}})
    ok("quem não entrou na coletiva vê o motivo", _l[0][4] == "não entrou" and _v == 0)
    # PELA CADEIA: `do_mes` com o `pont` na forma de
    # `analise_metas._pontualidade_do_periodo` (as chaves são as dela, lidas
    # no código: min_trab, min_abono, pend) e as horas devidas pela função de
    # verdade — setembro fechado, 21 dias úteis.
    import analise_metas as _am_t
    import placar_core as _pc_t
    from datetime import datetime as _dt_t
    _u = next(iter(_pc_t.MEMBROS_ATIVOS))
    _hoje = _dt_t(2026, 10, 30, 10, 0, tzinfo=_pc_t.FUSO)
    _dados = [{"filtro_mes": (2026, 9), "cfg": {}}]
    _dev = _am_t.horas_devidas_min(_dados, {}, _hoje)
    _pont = {_u: {"min_trab": _dev - 480, "min_abono": 0.0,
                  "pend": [{"data": "2026-09-15", "tipo": "sem_batida"},
                           {"data": "2026-09-16", "tipo": "incompleta"}]}}
    _r = do_mes(2026, 9, _dados, _pont, {_u: {"col": True}}, _hoje,
                salarios={_u: 3000.0}, bancos_anteriores={_u: 120.0})
    _f = _r[_u]["folha"]
    ok("cadeia: setembro fechado, devendo 8h com 2h de banco → −6h, 6h e o domingo descontados",
       _f["fechado"] and _f["banco_final_min"] == -360 and _f["desconto_horas"] == 90.0
       and _f["desconto_domingo"] == 100.0 and _f["salario_pagar"] == 2810.0
       and _r[_u]["faltas"] == ["2026-09-15"] and _r[_u]["metas_valor"] == 360.0)
    ok("cadeia: quem não tem salário na folha fica de fora, e não recebendo zero",
       all(v is None for k, v in _r.items() if k != _u))
    ok("valor-hora = salário ÷ DIVISOR_HORAS (200: 40h semanais)",
       DIVISOR_HORAS == 200 and apurar(2200, 0, 0, 0)["valor_hora"] == 11.0)
    ok("h: formata saldo com sinal", h(380) == "+6h20" and h(-75) == "−1h15" and h(0) == "0h00")
    print("\nfalhas:", falhas)
    raise SystemExit(1 if falhas else 0)
