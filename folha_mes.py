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
ABA_DOMINGO = "folha_domingo"
COLUNAS_DOMINGO = ["mes", "username", "data", "marcado_por", "marcado_em"]
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
           faltas_dia_inteiro=(), fechado=False, domingo_nas=()):
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
    valor_hora = salario / DIVISOR_HORAS if salario else 0.0
    desc_h = round(negativo / 60 * valor_hora, 2)
    _faltas = {str(x)[:10] for x in faltas_dia_inteiro or ()}
    semanas = semanas_com_falta([x for x in domingo_nas or () if str(x)[:10] in _faltas])
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


def do_mes(ano, mes, dados, pont, bonus, hoje, salarios=None, bancos_anteriores=None,
           domingos=None):
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
    if domingos is None:
        domingos = domingos_marcados(ano, mes)
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
        marcados = [d for d in domingos.get(u, []) if d in faltas]
        f = apurar(sal, p.get("min_trab", 0.0), p.get("min_abono", 0.0), devidas,
                   bancos_anteriores.get(u, 0.0), faltas, fechado, marcados)
        linhas, pct, valor = metas(sal, (bonus or {}).get(u))
        fora[u] = {"folha": f, "metas": linhas, "pct_metas": pct, "metas_valor": valor,
                   "faltas": faltas, "domingo_nas": marcados, "devidas_min": devidas,
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
    _sem = apurar(2200, _d - 480, 0, _d, 0, ["2026-10-14"], True)
    ok("falta SEM marca do dono: desconta as 8h, e o domingo NÃO",
       _sem["desconto_horas"] == 88.0 and _sem["desconto_domingo"] == 0
       and _sem["semanas_falta"] == 0 and _sem["salario_pagar"] == 2112.0)
    c = apurar(2200, _d - 480, 0, _d, 0, ["2026-10-14"], True, ["2026-10-14"])
    ok("falta MARCADA pelo dono: 8h + o domingo da semana",
       c["desconto_horas"] == 88.0 and c["desconto_domingo"] == round(2200 / 30, 2)
       and c["semanas_falta"] == 1)
    c2 = apurar(2200, _d - 480, 0, _d, 600, ["2026-10-14"], True, ["2026-10-14"])
    ok("marcada com banco cobrindo as horas: o banco cobre as 8h, o domingo é a marca dele",
       c2["desconto_horas"] == 0 and c2["desconto"] == round(2200 / 30, 2)
       and c2["banco_final_min"] == 120)
    ok("marca que não é falta (abonada depois) não desconta nada",
       apurar(2200, _d, 0, _d, 0, [], True, ["2026-10-14"])["desconto"] == 0)
    ok("duas marcadas na mesma semana: um domingo só",
       apurar(2200, _d - 960, 0, _d, 0, ["2026-10-13", "2026-10-14"], True,
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
    ok("ler: só o mês pedido", domingos_de(_nov, 2026, 10) == {"luiz": ["2026-10-14", "2026-10-21"]}
       and domingos_de(_nov, 2026, 9) == {"luiz": ["2026-09-15"]})
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
                salarios={_u: 3000.0}, bancos_anteriores={_u: 120.0}, domingos={})
    _f = _r[_u]["folha"]
    ok("cadeia: setembro fechado, devendo 8h com 2h de banco → −6h, só as 6h descontadas",
       _f["fechado"] and _f["banco_final_min"] == -360 and _f["desconto_horas"] == 90.0
       and _f["desconto_domingo"] == 0 and _f["salario_pagar"] == 2910.0
       and _r[_u]["faltas"] == ["2026-09-15"] and _r[_u]["metas_valor"] == 360.0)
    # A marca do dono pela cadeia, no formato que `domingos_de` devolve da
    # aba — e a da data que é só "incompleta" não conta.
    _r2 = do_mes(2026, 9, _dados, _pont, {_u: {"col": True}}, _hoje,
                 salarios={_u: 3000.0}, bancos_anteriores={_u: 120.0},
                 domingos=domingos_de([{"mes": "2026-09", "username": _u, "data": "2026-09-15"},
                                       {"mes": "2026-09", "username": _u, "data": "2026-09-16"}],
                                      2026, 9))
    ok("cadeia: com a falta de 15/09 marcada, soma o domingo (R$ 100) e só ele",
       _r2[_u]["domingo_nas"] == ["2026-09-15"] and _r2[_u]["folha"]["desconto_domingo"] == 100.0
       and _r2[_u]["folha"]["salario_pagar"] == 2810.0)
    ok("cadeia: quem não tem salário na folha fica de fora, e não recebendo zero",
       all(v is None for k, v in _r.items() if k != _u))
    ok("valor-hora = salário ÷ DIVISOR_HORAS (200: 40h semanais)",
       DIVISOR_HORAS == 200 and apurar(2200, 0, 0, 0)["valor_hora"] == 11.0)
    ok("h: formata saldo com sinal", h(380) == "+6h20" and h(-75) == "−1h15" and h(0) == "0h00")
    print("\nfalhas:", falhas)
    raise SystemExit(1 if falhas else 0)
