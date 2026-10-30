"""holerite.py — o demonstrativo do salário, dia a dia, e a assinatura dele.

O PEDIDO (dono, 30/10)
----------------------
"Um holerite constando o descritivo do que está sendo pago e o que está
sendo descontado (...) o que for descontado precisa ter informação de data,
hora e o motivo." E depois: o valor em cada linha, o consolidado embaixo, e o
colaborador vê o mesmo holerite e ASSINA a folha de ponto no dia 30, depois
do fechamento — "assim eles já ficarão cientes dos descontos".

DE ONDE VEM CADA NÚMERO
-----------------------
Nada é contado aqui. A pessoa chega pronta de `folha_mes.do_mes` (o mesmo
dicionário da aba do dono e do "Meu mês em dinheiro"): `folha` é a conta,
`dias` são os registros da RHiD do período. Este arquivo só ARRUMA em linhas
e desenha — a conta tem um dono só.

A LINHA DO DIA
--------------
Cada dia fechado do período em que o feito (trabalhado + abonado) difere do
devido (a jornada no dia útil, zero fora dele) vira uma linha: data, batidas
do relógio, motivo, horas e valor (horas × valor da hora). A soma das linhas
é o saldo do período; o consolidado tira o banco anterior e mostra o que
sobra para descontar — que é exatamente `folha["desconto_horas"]`.

ASSINATURA
----------
Aba `folha_assinaturas` da planilha, uma linha por pessoa e período, com o
líquido e o desconto do momento da assinatura: se a conta mudar depois (um
abono lançado tarde), dá para ver que a assinatura foi de outro número.
"""
import html as _html

ABA_ASSINATURAS = "folha_assinaturas"
COLUNAS_ASSINATURAS = ["periodo", "username", "nome", "assinado_em", "liquido",
                       "desconto", "saldo_horas"]
_DIAS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
ENTRADA_PADRAO = "09:00"
SAIDA_PADRAO = "18:00"


def _brl(v):
    return "R$ " + f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _sinal_brl(v):
    v = round(float(v or 0), 2)
    return ("− " if v < 0 else "+ " if v > 0 else "") + _brl(abs(v))


def _dia(iso):
    from datetime import date
    d = date.fromisoformat(str(iso)[:10])
    return f"{d:%d/%m} ({_DIAS[d.weekday()]})"


def _min(hhmm):
    try:
        h, m = str(hhmm).split(":")[:2]
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def motivo(d, jornada=480.0):
    """O motivo de um dia, em português, das batidas do relógio. Pura."""
    import folha_mes as _fm
    feito = float(d.get("min_trab") or 0) + float(d.get("min_abono") or 0)
    devido = jornada if d.get("dia_util") else 0.0
    abono = float(d.get("min_abono") or 0)
    pend = d.get("pendencia") or ""
    if pend == "sem_batida":
        return "Falta de dia inteiro, sem abono"
    partes = []
    if pend == "incompleta":
        partes.append(f"Marcação faltando ({len(d.get('batidas') or [])} batidas)")
    if not d.get("dia_util") and feito > 0:
        partes.append("Trabalho fora de dia útil")
    ent, s_alm, v_alm, sai = (_min(d.get(k)) for k in
                              ("entrada", "saida_almoco", "volta_almoco", "saida"))
    if ent is not None and ent > _min(ENTRADA_PADRAO):
        partes.append(f"Entrada às {d['entrada']}")
    if s_alm is not None and v_alm is not None and v_alm - s_alm > 60:
        partes.append(f"Almoço de {_fm.h(v_alm - s_alm).lstrip('+')}")
    if sai is not None and sai < _min(SAIDA_PADRAO) and pend != "incompleta":
        partes.append(f"Saída às {d['saida']}")
    if d.get("dia_util") and len(d.get("batidas") or []) == 2 and feito > devido:
        partes.append("Sem almoço")
    if abono:
        partes.append(f"abono de {_fm.h(abono).lstrip('+')}")
    resumo = f"{_fm.h(feito).lstrip('+')} de {_fm.h(devido).lstrip('+')}"
    return (" · ".join(partes) + " — " if partes else "") + resumo


def linhas(pessoa, jornada=480.0):
    """As linhas do holerite de uma pessoa (o dicionário de `do_mes`). Pura.

    Uma linha por dia fechado em que o feito difere do devido, e uma pelo
    domingo de cada falta que o dono marcou."""
    f = pessoa["folha"]
    vh = float(f["valor_hora"] or 0)
    fora = []
    for d in pessoa.get("dias") or []:
        if not d.get("fechado"):
            continue
        feito = float(d.get("min_trab") or 0) + float(d.get("min_abono") or 0)
        devido = jornada if d.get("dia_util") else 0.0
        dif = feito - devido
        if abs(dif) < 0.5:
            continue
        fora.append({"data": d["data"], "dia": _dia(d["data"]),
                     "batidas": " · ".join(d.get("batidas") or []) or "nenhuma",
                     "motivo": motivo(d, jornada), "min": dif,
                     "valor": round(dif / 60 * vh, 2),
                     "falta": d.get("pendencia") == "sem_batida", "domingo": False})
    if f.get("desconto_domingo"):
        por_dom = round(float(f["salario"]) / 30, 2)
        vistas = set()
        from datetime import date, timedelta
        for dt in sorted(pessoa.get("domingo_nas") or []):
            d0 = date.fromisoformat(dt)
            dom = d0 + timedelta(days=6 - d0.weekday())
            if dom in vistas:
                continue
            vistas.add(dom)
            fora.append({"data": dom.isoformat(), "dia": _dia(dom.isoformat()),
                         "batidas": "—", "motivo": f"Repouso semanal da semana da falta de "
                         f"{d0:%d/%m} (marcado pelo dono)", "min": None,
                         "valor": -por_dom, "falta": False, "domingo": True})
    return sorted(fora, key=lambda x: x["data"])


def consolidado(pessoa, lins):
    """O resumo embaixo das linhas: faltou, a mais, banco, descontado. Pura.

    A última conta é a de `folha_mes.apurar` — não é refeita aqui. As linhas
    acima dela EXPLICAM o número, e a soma delas bate com o saldo do período
    (o auto-teste confere)."""
    f = pessoa["folha"]
    vh = float(f["valor_hora"] or 0)
    falta = sum(-x["min"] for x in lins if x["min"] is not None and x["min"] < 0)
    mais = sum(x["min"] for x in lins if x["min"] is not None and x["min"] > 0)
    ant = float(f.get("banco_anterior_min") or 0)
    fora = [("Horas que faltaram nos dias acima", -falta,
             -round(sum(-x["valor"] for x in lins if not x["domingo"] and x["valor"] < 0), 2)),
            ("Horas a mais (crédito)", mais,
             round(sum(x["valor"] for x in lins if not x["domingo"] and x["valor"] > 0), 2))]
    if ant > 0:
        fora.append(("Coberto pelo banco de horas anterior", f["usado_do_banco_min"],
                     round(f["usado_do_banco_min"] / 60 * vh, 2)))
    elif ant < 0:
        fora.append(("Banco de horas negativo que veio do período anterior", ant,
                     round(ant / 60 * vh, 2)))
    fora.append(("Horas descontadas", -f["negativo_min"], -f["desconto_horas"]))
    if f.get("desconto_domingo"):
        fora.append((f"Repouso semanal ({f['semanas_falta']} domingo)", None,
                     -f["desconto_domingo"]))
    return fora


def _tab(cab, rows, alinhar):
    th = "".join(f'<th style="text-align:{a} !important;padding:6px 8px;">{c}</th>'
                 for c, a in zip(cab, alinhar))
    tr = "".join("<tr>" + "".join(f'<td style="text-align:{a};padding:6px 8px;{st}">{c}</td>'
                                  for (c, st), a in zip(r, alinhar)) + "</tr>" for r in rows)
    return f'<table style="width:100%;border-collapse:collapse;"><tr>{th}</tr>{tr}</table>'


def html(pessoa, nome, assinatura=None):
    """O holerite inteiro em HTML de UMA linha só (o markdown do Streamlit
    fecha o bloco numa linha em branco). Pura."""
    import folha_mes as _fm
    from datetime import date
    f = pessoa["folha"]
    e = _html.escape
    ini, fim = pessoa["periodo"]
    pag = date.fromisoformat(pessoa["pagamento"])
    lins = linhas(pessoa)
    neg, pos = "color:#E34948;", "color:#3FAE6A;"
    rows = [[(e(x["dia"]), ""), (e(x["batidas"]), ""), (e(x["motivo"]), ""),
             (_fm.h(x["min"]) if x["min"] is not None else "1 dia",
              neg if (x["min"] or -1) < 0 else pos),
             (_sinal_brl(x["valor"]), neg if x["valor"] < 0 else pos)] for x in lins]
    cons = [[(e(r), "font-weight:700;" if r.startswith("Horas descontadas") else ""),
             (_fm.h(m) if m is not None else "—", ""),
             (_sinal_brl(v), neg if v < 0 else pos if v > 0 else "")]
            for r, m, v in consolidado(pessoa, lins)]
    cons.append([("<b>Total de descontos</b>", ""), ("", ""),
                 (f"<b>{_sinal_brl(-f['desconto'])}</b>", neg)])
    met = [[(e(rot), ""), ("✓ batida" if bateu else ("✗ " + e(mot) if mot else "✗ não batida"),
                            pos if bateu else neg),
            (f"{pct:.0f}%", ""), (_brl(v) if pago else ("a MAXX paga" if bateu else "—"), "")]
           for rot, pct, v, bateu, mot, pago in pessoa["metas"]]
    q = _quinto(pag)
    cab = ('<div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;'
           'border-bottom:2px solid var(--ms-texto);padding-bottom:8px;">'
           f'<div><div style="font-size:20px;font-weight:800;">Holerite — {e(nome)}</div>'
           '<div style="font-size:12px;color:var(--ms-texto-sec);">MS Studio · demonstrativo de '
           'pagamento</div></div><div style="text-align:right;font-size:12px;">'
           f'Pagamento: <b>{pag:%d/%m/%Y}</b><br>Período apurado: <b>'
           f'{date.fromisoformat(ini):%d/%m} a {date.fromisoformat(fim):%d/%m/%Y}</b></div></div>')
    info = ('<div style="display:flex;gap:28px;flex-wrap:wrap;margin:10px 0;font-size:13px;">'
            f'<div>Horas do período<br><b>{_fm.h(pessoa["horas_do_mes_min"]).lstrip("+")}</b></div>'
            f'<div>Devidas até agora<br><b>{_fm.h(pessoa["devidas_min"]).lstrip("+")}</b></div>'
            f'<div>Valor da hora<br><b>{_brl(f["salario"])} ÷ '
            f'{_fm.h(pessoa["horas_do_mes_min"]).lstrip("+")} = {_brl(f["valor_hora"])}</b></div>'
            f'<div>Banco de horas<br><b>{_fm.h(f.get("banco_anterior_min", 0))} → '
            f'{_fm.h(f["banco_final_min"])}</b></div></div>')
    tit = lambda t: f'<div style="font-size:12px;font-weight:800;letter-spacing:.06em;margin:16px 0 4px;">{t}</div>'
    prov = _tab(["Descrição", "Valor"], [[("Salário base", ""), (_brl(f["salario"]), pos)]],
                ["left", "right"])
    desc = (_tab(["Data", "Batidas no relógio", "Motivo", "Horas", "Valor"], rows,
                 ["left", "left", "left", "right", "right"]) if rows
            else '<div style="font-size:13px;">Nenhum dia fora da jornada no período.</div>')
    liq_v = f["salario_pagar"] if f["fechado"] else f["salario_se_fechasse_hoje"]
    liq = ('<div style="display:flex;justify-content:space-between;background:var(--ms-texto);'
           'color:var(--ms-bg, #222);border-radius:8px;padding:12px 16px;margin-top:12px;'
           f'font-size:17px;font-weight:800;"><span>{"Líquido a receber" if f["fechado"] else "Se o período fechasse hoje"}'
           f' em {pag:%d/%m}</span><span>{_brl(liq_v)}</span></div>')
    metas = _tab(["Meta", "Situação", "%", "Valor"], met, ["left", "left", "right", "right"])
    ass = ""
    if assinatura:
        ass = ('<div style="margin-top:14px;font-size:13px;color:#3FAE6A;font-weight:700;">'
               f'✓ Folha de ponto assinada por {e(assinatura.get("nome", ""))} em '
               f'{e(str(assinatura.get("assinado_em", "")))}</div>')
    return ('<div style="border:1px solid var(--ms-borda);border-radius:10px;padding:16px 18px;">'
            + cab + info + tit("PROVENTOS") + prov + tit("DESCONTOS — DIA A DIA") + desc
            + tit("CONSOLIDADO") + _tab(["", "Horas", "Valor"], cons, ["left", "right", "right"])
            + liq + tit(f"METAS — PAGAS NO 5º DIA ÚTIL{f' ({q:%d/%m})' if q else ''}") + metas
            + f'<div style="text-align:right;font-weight:800;margin-top:6px;">Total de metas: '
            f'{_brl(pessoa["metas_valor"])}</div>' + ass
            + '<div style="font-size:11px;color:var(--ms-texto-sec);margin-top:10px;">Ponto: '
            'relógio RHiD · ajuste de batida e abono são feitos no app da RHiD</div></div>')


def _quinto(pag):
    try:
        import headcount as _hc
        a, m = (pag.year + 1, 1) if pag.month == 12 else (pag.year, pag.month + 1)
        return _hc.quinto_dia_util(a, m) if pag.day >= 28 else _hc.quinto_dia_util(pag.year, pag.month)
    except Exception:
        return None


# ── Assinatura ────────────────────────────────────────────────────────────────
def pode_assinar(ano, mes, hoje):
    """Assina-se o período FECHADO, a partir do dia do pagamento. Pura."""
    import folha_mes as _fm
    d = hoje.date() if hasattr(hoje, "date") else hoje
    return d >= _fm.dia_do_pagamento(ano, mes)


def chave(ano, mes):
    return f"{ano:04d}-{mes:02d}"


def assinaturas_de(linhas_aba, ano, mes):
    """{username: linha} das assinaturas do período. Pura."""
    k = chave(ano, mes)
    return {str(l["username"]): l for l in linhas_aba or []
            if str(l.get("periodo", "")) == k and l.get("username")}


def linha_de_assinatura(ano, mes, username, nome, pessoa, quando):
    """A linha gravada: o que a pessoa viu ao assinar. Pura."""
    import folha_mes as _fm
    f = pessoa["folha"]
    return [chave(ano, mes), username, nome, quando, f"{f['salario_pagar']:.2f}",
            f"{f['desconto']:.2f}", _fm.h(f["banco_final_min"])]


def _aba():
    import sheets as _sh
    pl = _sh.planilha()
    try:
        return pl.worksheet(ABA_ASSINATURAS)
    except Exception:
        a = pl.add_worksheet(title=ABA_ASSINATURAS, rows=500, cols=len(COLUNAS_ASSINATURAS))
        a.append_row(COLUNAS_ASSINATURAS, value_input_option="RAW")
        return a


def assinaturas(ano, mes):
    """As assinaturas do período, da planilha. Levanta erro: a tela diz."""
    return assinaturas_de(_aba().get_all_records(), ano, mes)


def assinar(ano, mes, username, nome, pessoa):
    """Grava a assinatura. Recusa a segunda do mesmo período — a primeira vale."""
    import placar_core as _pc
    a = _aba()
    if username in assinaturas_de(a.get_all_records(), ano, mes):
        return False
    a.append_row(linha_de_assinatura(ano, mes, username, nome, pessoa,
                                     _pc.agora_br().strftime("%d/%m/%Y %H:%M")),
                 value_input_option="RAW")
    return True


if __name__ == "__main__":
    import folha_mes as _fm
    from datetime import date
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # A pessoa no formato de `folha_mes.do_mes`, com a conta de verdade
    # (`apurar`) e os dias no formato de `relogio_ponto` (`dias`).
    def _dia_t(iso, trab, bat, util=True, pend="", abono=0.0, ent=None, s_a=None, v_a=None, sai=None):
        return {"data": iso, "dia_util": util, "fechado": True, "batidas": bat,
                "min_trab": trab, "min_abono": abono, "entrada": ent, "saida_almoco": s_a,
                "volta_almoco": v_a, "saida": sai, "saldo_banco": None, "pendencia": pend}
    _dias = [_dia_t("2026-10-07", 0, [], pend="sem_batida"),
             _dia_t("2026-10-08", 480, ["09:00", "12:00", "13:00", "18:00"], ent="09:00",
                    s_a="12:00", v_a="13:00", sai="18:00"),
             _dia_t("2026-10-14", 458, ["09:22", "12:00", "13:00", "18:00"], ent="09:22",
                    s_a="12:00", v_a="13:00", sai="18:00"),
             _dia_t("2026-10-21", 435, ["09:00", "12:00", "13:15", "17:30"], ent="09:00",
                    s_a="12:00", v_a="13:15", sai="17:30"),
             _dia_t("2026-10-23", 580, ["09:00", "18:40"], ent="09:00", sai="18:40")]
    _H = 168 * 60
    _trab = sum(d["min_trab"] for d in _dias)
    _dev = 5 * 480
    _f = _fm.apurar(2100, _trab, 0, _dev, 120, ["2026-10-07"], True, ["2026-10-07"],
                    horas_do_mes_min=_H)
    _f["banco_anterior_min"] = 120
    _l, _p, _v = _fm.metas(2100, {"col": True})
    _pes = {"folha": _f, "metas": _l, "pct_metas": _p, "metas_valor": _v, "dias": _dias,
            "domingo_nas": ["2026-10-07"], "faltas": ["2026-10-07"],
            "periodo": ("2026-09-30", "2026-10-29"), "pagamento": "2026-10-30",
            "horas_do_mes_min": _H, "devidas_min": _dev}
    _li = linhas(_pes)
    ok("_DIAS: o dia da semana do holerite (e da caixa do domingo, folha_tela)",
       _DIAS[date(2026, 10, 7).weekday()] == "qua" and _li[0]["dia"] == "07/10 (qua)")
    ok("uma linha por dia fora da jornada, mais o domingo marcado; o dia certo fica fora",
       [x["data"] for x in _li] == ["2026-10-07", "2026-10-11", "2026-10-14",
                                    "2026-10-21", "2026-10-23"])
    ok("motivos: falta, entrada atrasada, almoço longo e saída cedo, sem almoço",
       _li[0]["motivo"].startswith("Falta de dia inteiro")
       and "Entrada às 09:22" in _li[2]["motivo"]
       and "Almoço de 1h15" in _li[3]["motivo"] and "Saída às 17:30" in _li[3]["motivo"]
       and "Sem almoço" in _li[4]["motivo"])
    ok("valor de cada linha = horas × valor da hora (R$ 12,50)",
       _li[0]["valor"] == -100.0 and _li[2]["valor"] == round(-22 / 60 * 12.5, 2)
       and _li[4]["valor"] == round(100 / 60 * 12.5, 2) and _li[1]["valor"] == -70.0)
    ok("a soma das linhas de hora é o saldo do período da conta",
       sum(x["min"] for x in _li if x["min"] is not None) == _f["saldo_mes_min"])
    _c = consolidado(_pes, _li)
    _desc = [v for r, m, v in _c if r == "Horas descontadas"][0]
    ok("consolidado: o descontado é o de `apurar`, e o banco anterior aparece",
       _desc == -_f["desconto_horas"]
       and any(r.startswith("Coberto pelo banco") for r, m, v in _c))
    _ht = html(_pes, "Beatriz", {"nome": "Beatriz", "assinado_em": "30/10/2026 09:14"})
    ok("html de uma linha só, com o líquido, as metas e a assinatura",
       "\n" not in _ht and _brl(_f["salario_pagar"]) in _ht and "Coletiva" in _ht
       and "assinada por Beatriz" in _ht and "!important" in _ht)
    ok("pode assinar a partir do dia do pagamento, não antes",
       pode_assinar(2026, 10, date(2026, 10, 30)) and not pode_assinar(2026, 10, date(2026, 10, 29))
       and pode_assinar(2026, 8, date(2026, 8, 28)))
    _lin = linha_de_assinatura(2026, 10, "bia", "Beatriz", _pes, "30/10/2026 09:14")
    _back = assinaturas_de([dict(zip(COLUNAS_ASSINATURAS, _lin))], 2026, 10)
    ok("a assinatura grava o período, quem, quando e o líquido que ela viu",
       _back["bia"]["assinado_em"] == "30/10/2026 09:14"
       and _back["bia"]["liquido"] == f"{_f['salario_pagar']:.2f}"
       and assinaturas_de([dict(zip(COLUNAS_ASSINATURAS, _lin))], 2026, 11) == {})

    class _AbaFalsa:
        def __init__(self):
            self.linhas = []

        def get_all_records(self):
            return [dict(zip(COLUNAS_ASSINATURAS, l)) for l in self.linhas]

        def append_row(self, l, **k):
            self.linhas.append(l)
    _af = _AbaFalsa()
    _g = globals()["_aba"]
    globals()["_aba"] = lambda: _af
    try:
        _1 = assinar(2026, 10, "bia", "Beatriz", _pes)
        _2 = assinar(2026, 10, "bia", "Beatriz", _pes)
    finally:
        globals()["_aba"] = _g
    ok("assinar grava uma vez; a segunda do mesmo período é recusada",
       _1 and not _2 and len(_af.linhas) == 1 and _af.linhas[0][0] == "2026-10")
    print("\nfalhas:", falhas)
    raise SystemExit(1 if falhas else 0)
