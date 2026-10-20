"""lembretes.py — os pagamentos que NÃO são débito automático, no topo da Home.

O PEDIDO, NAS PALAVRAS DO DONO (15/10)
--------------------------------------
"Precisa estar na aba Home, logo acima em destaque, os pagamentos (...) onde
não são débito automático com base no dia dos seus vencimentos, só lembrete
sem informar valor". Layout escolhido: a opção A (cartões dos próximos 7 dias
e o resto numa linha), com um botão para sumir "conforme eu faça, para não
ficar lá o dia inteiro".

DE ONDE VEM CADA LEMBRETE
-------------------------
    Bling                todo dia 10                          REGRAS
    Salários             todo dia 30 (fevereiro: o último)    REGRAS
    Bônus headcount      5º dia útil — seg a sex, sem feriado REGRAS
    TM Logística         dias 05 e 20                         REGRAS
    DAS                  dia 20; sem dia útil, o ANTERIOR     REGRAS
    Demais impostos      dia 20; sem dia útil, o SEGUINTE     REGRAS
    Boletos              os em aberto da aba Boletos          `cheques`
    Não operacional      o dia do débito de cada contrato     `nao_operacional`
                         ativo no mês, com a conta de onde ele sai

Dia útil é de segunda a sexta, sem feriado nacional (dono, 15/10).

O "FEITO" É GRAVADO NA PLANILHA, E NÃO NA SESSÃO
-------------------------------------------------
Quem marca é uma pessoa e quem olha pode ser outra, noutro computador, depois
de um deploy. Gravado na sessão, o lembrete voltaria a cada reinício — que é o
defeito da Forma 9. Cada marca vale para UMA data: o Bling feito em outubro
volta em novembro.

QUANTO TEMPO UM LEMBRETE FICA
-----------------------------
Até alguém marcar Feito. O que passou da data e não foi marcado fica como
ATRASADO por até `DIAS_PARA_TRAS` dias; mais velho que isso some sozinho, para
o primeiro dia no ar não despejar meses de lembretes que ninguém marcou.
"""

from datetime import date, datetime, timedelta

import streamlit as st

ABA = "lembretes_feitos"
COLUNAS = ["chave", "vencimento", "feito_em", "feito_por"]
DIAS_PARA_FRENTE = 31
DIAS_PARA_TRAS = 5

# (id, nome, regra, detalhe). A regra: ("dia", n) | ("dia_util", n)
# | ("dia_antecipa", n) | ("dia_adia", n) — o dia n, ou, quando ele não é dia
# útil, o dia útil anterior / seguinte.
REGRAS = [
    ("bling", "Bling", ("dia", 10), "todo dia 10"),
    ("salarios", "Salários", ("dia", 30), "todo dia 30"),
    ("bonus_headcount", "Bônus headcount", ("dia_util", 5), "5º dia útil"),
    ("tm_05", "TM Logística", ("dia", 5), "dias 05 e 20"),
    ("tm_20", "TM Logística", ("dia", 20), "dias 05 e 20"),
    # Dono, 20/10: "não me alertou sobre o pagamento dos impostos mensais que
    # vencem todo dia 20". Faltava na lista desde o dia em que ela nasceu.
    # Dono, 20/10, de novo: "o DAS antecipa para o dia anterior, porém o
    # restante dos impostos caem para o dia seguinte".
    ("das_20", "DAS", ("dia_antecipa", 20), "dia 20 · sem dia útil, antecipa"),
    ("impostos_20", "Demais impostos", ("dia_adia", 20), "dia 20 · sem dia útil, adia"),
]


def _pascoa(ano):
    """Domingo de Páscoa (algoritmo de Meeus). Para a Sexta-feira Santa."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    mes = (h + l_ - 7 * m + 114) // 31
    dia = ((h + l_ - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def feriados_nacionais(ano):
    fixos = [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15),
             (11, 20), (12, 25)]
    return {date(ano, m, d) for m, d in fixos} | {_pascoa(ano) - timedelta(days=2)}


def dia_util(ano, mes, n):
    """O n-ésimo dia útil do mês: seg a sex, sem feriado nacional."""
    fer = feriados_nacionais(ano)
    d, conta = date(ano, mes, 1), 0
    while d.month == mes:
        if d.weekday() < 5 and d not in fer:
            conta += 1
            if conta == n:
                return d
        d += timedelta(days=1)
    return None


def _dia_no_mes(ano, mes, dia):
    """O dia `dia` do mês, ou o último quando o mês é mais curto."""
    prox = date(ano + (mes == 12), mes % 12 + 1, 1)
    ultimo = (prox - timedelta(days=1)).day
    return date(ano, mes, min(max(int(dia), 1), ultimo))


def _meses(inicio, fim):
    a, m = inicio.year, inicio.month
    while (a, m) <= (fim.year, fim.month):
        yield a, m
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)


def das_regras(inicio, fim):
    """[{chave, data, nome, detalhe}] das REGRAS fixas entre `inicio` e `fim`."""
    fora = []
    for a, m in _meses(inicio, fim):
        for id_, nome, (tipo, n), det in REGRAS:
            if tipo == "dia_util":
                d = dia_util(a, m, n)
            else:
                d = _dia_no_mes(a, m, n)
                if tipo == "dia_antecipa":
                    d = dia_util_anterior(d)
                elif tipo == "dia_adia":
                    d = dia_util_seguinte(d)
            if d and inicio <= d <= fim:
                fora.append({"chave": f"{id_}|{d.isoformat()}", "data": d,
                             "nome": nome, "detalhe": det})
    return fora


def dos_boletos(linhas, inicio, fim):
    """Os boletos em aberto da aba Boletos, pelo vencimento. Pura."""
    import cheques as _ch
    fora = []
    for c in (linhas or []):
        if not (_ch.eh_tipo(c, "BOLETO") and _ch.esta_aberto(c)):
            continue
        try:
            d = date.fromisoformat(_ch.texto_data(c.get("vencimento"))[:10])
        except ValueError:
            continue
        if inicio <= d <= fim:
            quem = str(c.get("favorecido") or "").strip() or "sem beneficiário"
            ident = str(c.get("id") or c.get("numero") or quem).strip()
            fora.append({"chave": f"boleto:{ident}|{d.isoformat()}", "data": d,
                         "nome": f"Boleto · {quem}",
                         "detalhe": "importado no sistema"})
    return fora


def do_nao_operacional(linhas, inicio, fim):
    """Cada contrato ativo, no dia do débito dele, com a conta. Pura."""
    import nao_operacional as _no
    fora = []
    for a, m in _meses(inicio, fim):
        for r in (linhas or []):
            dia = int(_no._num(r.get("dia_debito"), 0))
            if not dia or not _no.esta_ativo(r, a, m):
                continue
            d = _dia_no_mes(a, m, dia)
            if not inicio <= d <= fim:
                continue
            prog = str(r.get("programa") or "").strip() or "contrato"
            conta = str(r.get("conta_aporte") or "").strip()
            fora.append({"chave": f"naoop:{prog}|{d.isoformat()}", "data": d,
                         "nome": f"Não operacional · {prog}",
                         "detalhe": f"conta {conta}" if conta else "conta do débito"})
    return fora


def pendentes(hoje, feitos, boletos=(), nao_op=()):
    """Os lembretes que valem hoje, do mais atrasado ao mais longe. Pura.

    `feitos` é o conjunto de chaves já marcadas. Cada um ganha `dias`
    (negativo = atrasado).
    """
    inicio = hoje - timedelta(days=DIAS_PARA_TRAS)
    fim = hoje + timedelta(days=DIAS_PARA_FRENTE)
    todos = (das_regras(inicio, fim) + dos_boletos(boletos, inicio, fim)
             + do_nao_operacional(nao_op, inicio, fim))
    fora = []
    for x in todos:
        if x["chave"] in feitos:
            continue
        x["dias"] = (x["data"] - hoje).days
        fora.append(x)
    return sorted(fora, key=lambda x: (x["data"], x["nome"]))


def _eh_util(d):
    return d.weekday() < 5 and d not in feriados_nacionais(d.year)


def dia_util_anterior(d):
    """`d` se for dia útil; senão o último dia útil ANTES dele."""
    while not _eh_util(d):
        d -= timedelta(days=1)
    return d


def dia_util_seguinte(d):
    """`d` se for dia útil; senão o primeiro dia útil DEPOIS dele."""
    while not _eh_util(d):
        d += timedelta(days=1)
    return d


def proximo_dia_util(d):
    """O primeiro dia útil DEPOIS de `d`: seg a sex, sem feriado nacional."""
    d += timedelta(days=1)
    while d.weekday() >= 5 or d in feriados_nacionais(d.year):
        d += timedelta(days=1)
    return d


def para_mostrar(itens, hoje):
    """O que vai para a Home (dono, 16/10). Pura.

    "Somente é para aparecer quando o vencimento for no dia seguinte" —
    "sempre considerando dia útil": aparece no dia útil anterior. Na sexta,
    entra o que vence no sábado, no domingo e na segunda.
    O que vence hoje, ou venceu e ninguém marcou Feito, "continua".
    """
    limite = proximo_dia_util(hoje)
    return [x for x in itens if x["data"] <= limite]


def quando(dias):
    if dias < 0:
        return f"atrasado {-dias} dia(s)"
    return "hoje" if dias == 0 else ("amanhã" if dias == 1 else f"em {dias} dias")


# ── Planilha ─────────────────────────────────────────────────────────────────

def _aba():
    import gspread
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        return planilha.worksheet(ABA)
    except gspread.exceptions.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA, rows=500, cols=len(COLUNAS))
        aba.append_row(COLUNAS, value_input_option="RAW")
        return aba


@st.cache_data(ttl=120, show_spinner=False)
def carregar_feitos():
    """(chaves marcadas, erro). Falha não apaga a tela: volta vazio e diz."""
    try:
        regs = _aba().get_all_records()
    except Exception as e:
        return frozenset(), type(e).__name__
    return frozenset(str(r.get("chave") or "").strip() for r in regs
                     if str(r.get("chave") or "").strip()), ""


def marcar_feito(item, usuario=""):
    """Grava o Feito. (ok, erro)."""
    import placar_core as _pc
    agora = datetime.now(_pc.FUSO).strftime("%Y-%m-%d %H:%M")
    try:
        _aba().append_row([item["chave"], item["data"].isoformat(), agora,
                           str(usuario or "")], value_input_option="RAW")
    except Exception as e:
        return False, type(e).__name__
    carregar_feitos.clear()
    return True, ""


# ── Tela ─────────────────────────────────────────────────────────────────────

AMBAR, VERMELHO, SEC, TILE = "#E0A13A", "#E5534B", "#9AA3AE", "#2c2c2c"


def _cor(dias):
    return VERMELHO if dias <= 0 else AMBAR


def _cartao(x):
    return (f'<div style="background:{TILE};border-left:4px solid {_cor(x["dias"])};'
            f'border-radius:10px;padding:10px 12px;">'
            f'<div style="font-size:11px;font-weight:800;color:{_cor(x["dias"])};">'
            f'{quando(x["dias"]).upper()} · {x["data"]:%d/%m}</div>'
            f'<div style="font-size:15px;font-weight:700;">{x["nome"]}</div>'
            f'<div style="font-size:11px;color:{SEC};">{x["detalhe"]}</div></div>')


def mostrar(st_, usuario, hoje):
    """O quadro do topo da Home: o que vence amanhã, em cartões com ✓ Feito.
    Nada vencendo amanhã, nada aparece. Nada de valor — só lembrete."""
    import cheques as _ch
    import nao_operacional as _no
    feitos, erro = carregar_feitos()
    try:
        bol = _ch.carregar()
    except Exception:
        bol = []
    try:
        _df = _no.carregar()
        nao_op = _df.to_dict("records") if not _df.empty else []
    except Exception:
        nao_op = []
    perto = para_mostrar(pendentes(hoje, feitos, bol, nao_op), hoje)
    if not perto:
        return          # nada vence amanhã: a Home não mostra o quadro
    with st_.container(border=True):
        st_.markdown(f'<div style="font-size:12px;font-weight:800;letter-spacing:.08em;'
                     f'color:{AMBAR};">🔔 PAGAMENTOS A FAZER · ATÉ O PRÓXIMO DIA ÚTIL</div>',
                     unsafe_allow_html=True)
        if erro:
            st_.caption(f"Não consegui ler o que já foi marcado como feito "
                        f"({erro}) — mostrando todos.")
        for i in range(0, len(perto), 4):
            cols = st_.columns(4)
            for col, x in zip(cols, perto[i:i + 4]):
                with col:
                    st_.markdown(_cartao(x), unsafe_allow_html=True)
                    # O CALLBACK grava antes do redesenho: o cartão já some
                    # nesta passada, sem `st.rerun()` (que apagava a tela).
                    st_.button("✓ Feito", key=f"lem_{x['chave']}",
                               on_click=marcar_feito, args=(x, usuario),
                               use_container_width=True)


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    ok("5º dia útil de novembro/2026 é 09/11 (02/11 é Finados, sábado não conta)",
       dia_util(2026, 11, 5) == date(2026, 11, 9))
    ok("5º dia útil de outubro/2026 é 07/10",
       dia_util(2026, 10, 5) == date(2026, 10, 7))
    ok("Sexta-feira Santa de 2026 é feriado (03/04)",
       date(2026, 4, 3) in feriados_nacionais(2026))
    ok("salário em fevereiro cai no último dia",
       _dia_no_mes(2026, 2, 30) == date(2026, 2, 28))

    _hoje = date(2026, 10, 15)
    _p = pendentes(_hoje, frozenset())
    _nomes = [(x["data"], x["nome"]) for x in _p]
    ok("os fixos do dono, a partir de 15/10",
       (date(2026, 10, 20), "TM Logística") in _nomes
       and (date(2026, 10, 30), "Salários") in _nomes
       and (date(2026, 11, 9), "Bônus headcount") in _nomes
       and (date(2026, 11, 10), "Bling") in _nomes
       and (date(2026, 11, 5), "TM Logística") in _nomes)
    ok(f"o que passou há mais de {DIAS_PARA_TRAS} dias some (o Bling de 10/10 fica, o 7/10 não)",
       (date(2026, 10, 10), "Bling") in _nomes
       and (date(2026, 10, 7), "Bônus headcount") not in _nomes)
    ok("atrasado tem dias negativos e diz que atrasou",
       quando([x for x in _p if x["nome"] == "Bling"][0]["dias"]) == "atrasado 5 dia(s)")

    # A ENTRADA VEM DO SISTEMA: o boleto na forma das colunas de `cheques`,
    # e o contrato pela normalização de verdade de `nao_operacional`.
    import cheques as _ch_t
    import nao_operacional as _no_t
    _bol = [dict({c: "" for c in _ch_t.COLUNAS}, id="b1", tipo="BOLETO",
                 vencimento="2026-10-22", favorecido="Fornecedor X",
                 situacao="EM ABERTO", valor=500.0),
            dict({c: "" for c in _ch_t.COLUNAS}, id="b2", tipo="BOLETO",
                 vencimento="2026-10-18", favorecido="Pago Ltda",
                 situacao="PAGO", valor=80.0)]
    _contr = _no_t._normalizar([{
        "programa": "PRONAMP 1", "conta_aporte": "Itaú 99275-0",
        "data_contratacao": "2025-01-10", "carencia_meses": 6,
        "prazo_meses": 36, "aporte": 100000, "dia_debito": 18}])
    _p2 = pendentes(_hoje, frozenset(), _bol, _contr)
    _n2 = {(x["data"], x["nome"], x["detalhe"]) for x in _p2}
    ok("boleto em aberto entra pelo vencimento; o pago não",
       (date(2026, 10, 22), "Boleto · Fornecedor X", "importado no sistema") in _n2
       and not any("Pago Ltda" in x["nome"] for x in _p2))
    ok("o não operacional entra no dia do débito, com a conta",
       (date(2026, 10, 18), "Não operacional · PRONAMP 1",
        "conta Itaú 99275-0") in _n2)

    # O FEITO PELA CADEIA: o que `marcar_feito` grava é o que `carregar_feitos`
    # lê e o que `pendentes` deixa de mostrar.
    _linhas = []

    class _Aba:
        def append_row(self, r, value_input_option=None):
            _linhas.append(dict(zip(COLUNAS, r)))

        def get_all_records(self):
            return list(_linhas)
    _g = _aba
    try:
        globals()["_aba"] = lambda: _Aba()
        _tm = [x for x in _p if x["data"] == date(2026, 10, 20)][0]
        _ok, _err = marcar_feito(_tm, "leo")
        _feitos, _e2 = carregar_feitos()
        ok("Feito grava e o lembrete sai",
           _ok and not _err and _tm["chave"] in _feitos
           and all(x["chave"] != _tm["chave"]
                   for x in pendentes(_hoje, _feitos)))
        ok("e só daquela data: a TM de 05/11 continua",
           any(x["data"] == date(2026, 11, 5) and x["nome"] == "TM Logística"
               for x in pendentes(_hoje, _feitos)))
    finally:
        globals()["_aba"] = _g
        carregar_feitos.clear()
    ok("o lembrete não mostra valor nenhum",
       "R$" not in _cartao(dict(_p2[0], dias=0)))
    # 16/10, o dono: só o que vence no próximo dia útil; o de hoje e o
    # atrasado sem Feito continuam.
    _qui, _sex = date(2026, 10, 15), date(2026, 10, 16)
    _it = [{"data": _qui + timedelta(days=k), "dias": k, "nome": str(k)} for k in (-3, 0, 1, 2, 3, 4, 5)]
    ok("quinta: aparece o atrasado, o de hoje e o de sexta — o de sábado não",
       [x["dias"] for x in para_mostrar(_it, _qui)] == [-3, 0, 1])
    ok("sexta: entram sábado, domingo e segunda (o próximo dia útil)",
       [x["data"] for x in para_mostrar(_it, _sex)][-1] == date(2026, 10, 19)
       and date(2026, 10, 20) not in [x["data"] for x in para_mostrar(_it, _sex)])
    ok("dia comum: ter 10/11 → qua 11/11",
       proximo_dia_util(date(2026, 11, 10)) == date(2026, 11, 11))
    ok("feriado no meio: sex 13/11 → seg 16/11 (15/11 é domingo)",
       proximo_dia_util(date(2026, 11, 13)) == date(2026, 11, 16))
    ok("feriado no dia útil seguinte: qui 19/11 → seg 23/11 (20/11 é feriado)",
       proximo_dia_util(date(2026, 11, 19)) == date(2026, 11, 23))
    ok("pela cadeia: em 09/10 (sex) aparece o Bling de 10/10 (sáb) e nada da TM de 20/10",
       [(x["data"], x["nome"]) for x in para_mostrar(pendentes(date(2026, 10, 9), frozenset()), date(2026, 10, 9))]
       == [(date(2026, 10, 5), "TM Logística"), (date(2026, 10, 7), "Bônus headcount"), (date(2026, 10, 10), "Bling")])
    # IMPOSTOS DO DIA 20 (20/10): na segunda 19/10 o próximo dia útil é a
    # terça 20/10, e o lembrete dos impostos tem de estar na Home.
    _imp = [x for x in para_mostrar(pendentes(date(2026, 10, 19), frozenset()), date(2026, 10, 19))
            if x["nome"] in ("DAS", "Demais impostos")]
    ok("os impostos do dia 20 aparecem no dia útil anterior (DAS e demais)",
       sorted(x["nome"] for x in _imp) == ["DAS", "Demais impostos"]
       and all(x["data"] == date(2026, 10, 20) for x in _imp))
    # FIM DE SEMANA (20/10): 20/12/2026 é domingo. O DAS antecipa para a
    # sexta 18/12; os demais adiam para a segunda 21/12. Pela cadeia das REGRAS.
    _dez = {x["nome"]: x["data"] for x in das_regras(date(2026, 12, 1), date(2026, 12, 31))
            if x["nome"] in ("DAS", "Demais impostos")}
    ok("dia 20 no domingo: DAS antecipa para sex 18/12, demais adiam para seg 21/12",
       _dez == {"DAS": date(2026, 12, 18), "Demais impostos": date(2026, 12, 21)})
    ok("dia 20 em dia útil não mexe: ter 20/10 fica 20/10 nos dois sentidos",
       dia_util_anterior(date(2026, 10, 20)) == dia_util_seguinte(date(2026, 10, 20)) == date(2026, 10, 20))
    ok("feriado também desloca: sex 20/11 (Consciência Negra) → DAS qui 19/11, demais seg 23/11",
       (dia_util_anterior(date(2026, 11, 20)), dia_util_seguinte(date(2026, 11, 20)))
       == (date(2026, 11, 19), date(2026, 11, 23)))

    print(f"\nfalhas: {falhas}")
    sys.exit(1 if falhas else 0)
