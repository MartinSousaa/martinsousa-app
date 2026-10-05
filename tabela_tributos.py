"""tabela_tributos.py — o INSS e o IRRF do EMPREGADO, pela tabela que o dono cadastra.

POR QUE A TABELA NÃO ESTÁ NO CÓDIGO
-----------------------------------
O bônus das metas paga imposto como salário — do dono (FGTS, reflexos) e do
colaborador (INSS e IRRF, descontados dele). A parte do dono sai das taxas de
`colaboradores.TAXAS`. A do colaborador depende da tabela do ano, que muda por
portaria todo janeiro.

Escrever a tabela aqui seria o número de cabeça que a Regra 2 proíbe: em
fevereiro ela estaria velha, e ninguém veria. Então ela mora numa aba da
planilha, cadastrada uma vez por ano na tela, e enquanto não existe o Studio
diz que não existe — em vez de devolver um desconto inventado.

A CONTA
-------
    INSS do empregado: progressivo, faixa a faixa, até o teto da última faixa.
    IRRF: base = bruto − INSS; alíquota da faixa menos a dedução dela.
          `isento_ate` > 0: quem ganha até ele não paga (a regra de 2026).

    Imposto DO BÔNUS = imposto(salário + bônus) − imposto(salário).
    É o que o bônus acrescenta ao desconto do mês; calcular o bônus sozinho
    pegaria a primeira faixa e descontaria de menos.
"""

from datetime import datetime, timezone, timedelta

import pandas as pd
import streamlit as st

ABA = "tabela_tributos"
COLUNAS = ["tributo", "ate", "aliquota", "deducao", "atualizado_em",
           "atualizado_por"]
TRIBUTOS = ["INSS", "IRRF", "IRRF_ISENTO_ATE"]

FUSO = timezone(timedelta(hours=-3))


def _num(v, padrao=0.0):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return padrao
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        f = float(v)
        return padrao if (f != f or f in (float("inf"), float("-inf"))) else f
    t = str(v).strip().replace("R$", "").replace("%", "").replace(" ", "")
    if not t:
        return padrao
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return padrao


def _aliq(v):
    """7,5 e 0,075 querem dizer a mesma coisa; devolve a fração."""
    a = _num(v)
    return a / 100.0 if a > 1 else a


def faixas(df):
    """{"inss": [(ate, aliq)], "irrf": [(ate, aliq, deducao)], "isento_ate"}."""
    d = pd.DataFrame(df) if df is not None else pd.DataFrame(columns=COLUNAS)
    inss, irrf, isento = [], [], 0.0
    for _, r in d.iterrows():
        t = str(r.get("tributo", "") or "").strip().upper()
        ate = _num(r.get("ate"))
        if t == "INSS" and ate > 0:
            inss.append((ate, _aliq(r.get("aliquota"))))
        elif t == "IRRF":
            # A última faixa do IR não tem teto: "ate" vazio vale infinito.
            irrf.append((ate if ate > 0 else float("inf"),
                         _aliq(r.get("aliquota")), _num(r.get("deducao"))))
        elif t == "IRRF_ISENTO_ATE":
            isento = max(ate, 0.0)
    return {"inss": sorted(inss), "irrf": sorted(irrf), "isento_ate": isento}


def inss(bruto, fx):
    """INSS progressivo do empregado. None sem tabela."""
    if not fx.get("inss"):
        return None
    b, ant, total = max(_num(bruto), 0.0), 0.0, 0.0
    for ate, a in fx["inss"]:
        if b <= ant:
            break
        total += (min(b, ate) - ant) * a
        ant = ate
    return round(total, 2)


def irrf(bruto, fx):
    """IRRF do mês sobre o bruto, já tirado o INSS. None sem tabela."""
    if not fx.get("irrf") or not fx.get("inss"):
        return None
    b = max(_num(bruto), 0.0)
    if fx.get("isento_ate") and b <= fx["isento_ate"]:
        return 0.0
    base = b - (inss(b, fx) or 0.0)
    for ate, a, ded in fx["irrf"]:
        if base <= ate:
            return round(max(base * a - ded, 0.0), 2)
    return 0.0


def do_bonus(salario, bonus, fx):
    """(INSS, IRRF) que o bônus ACRESCENTA ao desconto do mês. None sem tabela."""
    s, b = max(_num(salario), 0.0), max(_num(bonus), 0.0)
    i_c, i_s = inss(s + b, fx), inss(s, fx)
    r_c, r_s = irrf(s + b, fx), irrf(s, fx)
    return (None if i_c is None else round(i_c - i_s, 2),
            None if r_c is None else round(r_c - r_s, 2))


# ── Planilha ─────────────────────────────────────────────────────────────────

def _aba():
    import gspread
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        return planilha.worksheet(ABA)
    except gspread.exceptions.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA, rows=60, cols=len(COLUNAS))
        aba.append_row(COLUNAS, value_input_option="RAW")
        return aba


@st.cache_data(ttl=600, show_spinner=False)
def carregar():
    """(df, erro). O erro separa "não cadastrada" de "não consegui ler"."""
    try:
        registros = _aba().get_all_records(value_render_option="UNFORMATTED_VALUE")
    except Exception as e:
        return pd.DataFrame(columns=COLUNAS), f"{type(e).__name__}"
    df = pd.DataFrame(registros)
    if df.empty:
        return pd.DataFrame(columns=COLUNAS), ""
    df.columns = [str(c).strip().lower() for c in df.columns]
    for c in COLUNAS:
        if c not in df.columns:
            df[c] = ""
    return df[COLUNAS], ""


def salvar(df, usuario=""):
    agora = datetime.now(FUSO).strftime("%Y-%m-%d %H:%M")
    linhas = []
    for _, r in pd.DataFrame(df).iterrows():
        t = str(r.get("tributo", "") or "").strip().upper()
        if t not in TRIBUTOS:
            continue
        linhas.append([t, round(_num(r.get("ate")), 2),
                       round(_num(r.get("aliquota")), 4),
                       round(_num(r.get("deducao")), 2), agora,
                       str(usuario or "")[:60]])
    try:
        aba = _aba()
        aba.clear()
        aba.update("A1", [COLUNAS] + linhas, value_input_option="RAW")
    except Exception as e:
        return False, type(e).__name__
    carregar.clear()
    return True, f"{len(linhas)} faixa(s) gravada(s)"


# ── Conferência ──────────────────────────────────────────────────────────────
# Tabela de TESTE, não a do ano: os números abaixo só exercitam a conta. A de
# verdade vem da planilha — ver o cabeçalho.
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    _t = pd.DataFrame([
        {"tributo": "INSS", "ate": 1000, "aliquota": 10},
        {"tributo": "INSS", "ate": 3000, "aliquota": 0.20},
        {"tributo": "IRRF", "ate": 2000, "aliquota": 0, "deducao": 0},
        {"tributo": "IRRF", "ate": "", "aliquota": 10, "deducao": 200},
    ])
    fx = faixas(_t)
    ok("alíquota em % e em fração são a mesma", fx["inss"][0][1] == 0.10)
    ok("INSS é progressivo", inss(2000, fx) == 1000 * 0.10 + 1000 * 0.20)
    ok("e para no teto", inss(9000, fx) == inss(3000, fx))
    ok("IR sobre o bruto menos o INSS", irrf(3000, fx)
       == round((3000 - inss(3000, fx)) * 0.10 - 200, 2))
    ok("abaixo da primeira faixa não paga IR", irrf(1500, fx) == 0.0)
    _i, _r = do_bonus(2000, 500, fx)
    ok("o INSS do bônus é o que ele acrescenta",
       _i == round(inss(2500, fx) - inss(2000, fx), 2))
    ok("e o IR também", _r == round(irrf(2500, fx) - irrf(2000, fx), 2))
    fx2 = faixas(pd.concat([_t, pd.DataFrame([{"tributo": "IRRF_ISENTO_ATE",
                                                "ate": 5000}])]))
    ok("quem ganha até o limite de isenção não paga IR",
       irrf(4000, fx2) == 0.0 and irrf(6000, fx2) > 0)
    _vazia = faixas(pd.DataFrame(columns=COLUNAS))
    ok("sem tabela, não inventa desconto",
       do_bonus(2000, 500, _vazia) == (None, None))
    ok("tributo desconhecido é ignorado",
       faixas(pd.DataFrame([{"tributo": "XPTO", "ate": 1, "aliquota": 1}]))
       == {"inss": [], "irrf": [], "isento_ate": 0.0})
    print("\nfalhas:", falhas)
    raise SystemExit(falhas)
