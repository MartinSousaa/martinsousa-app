"""base_vendas.py — lucro, margem, LPV e UC saem da BASE DE VENDAS do Controle MS.

POR QUE DAQUI, E NÃO DO BLING
-----------------------------
O dono disse com todas as letras: "não temos os custos cadastrados no Bling
para que o sistema obtenha esses números". O Bling sabe o que VENDEU; quanto
cada peça custou está na planilha, digitado por eles.

Então a Home passa a beber de duas fontes, cada uma no que ela sabe:

    faturamento do mês   -> Bling, em tempo real (a venda cai lá na hora)
    lucro, margem, LPV,  -> BASE DE VENDAS 2026, conforme eles atualizam
    UC, devoluções

Os dois números de faturamento NÃO vão bater, e isso não é defeito: a planilha
é atualizada de tempos em tempos, o Bling é agora. Por isso a tela diz de onde
veio cada um — um número sem origem é um número que ninguém consegue conferir.

RAZÃO NÃO SE SOMA, NEM SE TIRA MÉDIA
------------------------------------
A aba tem uma linha por item de pedido, e colunas de percentual e de razão já
calculadas em cada linha (MARGEM %, LPV, UNI. CONT.). Tirar a média dessas
colunas dá número errado: uma venda de R$ 10 com 90% de margem e uma de
R$ 1.000 com 10% não fazem 50% — fazem 10,8%.

Aqui só se SOMA o que é somável (faturamento, custo, lucro, unidades, vendas),
e as razões são recalculadas a partir das somas. É a diferença entre o
indicador certo e um que parece certo.
"""

import unicodedata

import streamlit as st

ABA = "BASE DE VENDAS 2026"

# Meses como a coluna MÊS os escreve.
MESES = ("jan", "fev", "mar", "abr", "mai", "jun",
         "jul", "ago", "set", "out", "nov", "dez")


def _chave(nome):
    """O nome da coluna sem acento, sem espaço extra e em minúscula.

    A planilha é editada à mão: "MARGEM C." hoje pode virar "Margem C. " amanhã,
    e uma comparação literal faria a coluna sumir sem ninguém ser avisado — o
    indicador apareceria zerado, que é pior do que aparecer quebrado.
    """
    t = unicodedata.normalize("NFD", str(nome or ""))
    t = t.encode("ascii", "ignore").decode("ascii")
    return " ".join(t.replace(".", " ").split()).strip().lower()


# As colunas de que a Home precisa, e os nomes que cada uma já teve.
# Só entra aqui o que é SOMÁVEL.
COLUNAS = {
    "faturamento": ("fat total",),
    "fat_liquido": ("fat - dev", "fat-dev"),
    "custo_total": ("custo total",),
    "custo_op": ("custo op",),
    "devolucao": ("devolucao",),
    "comissao": ("comissao",),
    "frete": ("frete",),
    "nf": ("nf",),
    "lucro_bruto": ("l b",),
    "margem_contribuicao": ("margem c",),
    "vendas": ("vendas",),
    "unidades": ("uni cont",),
}


def _num(v, padrao=0.0):
    """Número, e só. Texto, vazio, NaN e infinito viram o padrão.

    `nan != nan` é o único jeito sem dependência de detectá-lo, e ele chega
    aqui por toda célula vazia do Excel. Somar um deles contamina o total
    inteiro — e um total NaN não aparece como erro, aparece como nada.
    """
    if isinstance(v, bool):
        return padrao
    if isinstance(v, (int, float)):
        f = float(v)
        if f != f or f in (float("inf"), float("-inf")):
            return padrao
        return f
    t = str(v or "").strip()
    if not t:
        return padrao
    t = t.replace("R$", "").replace("%", "").strip()
    # Formato brasileiro: 1.234,56. Trocar na ordem errada devolve 1.23456.
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        f = float(t)
    except ValueError:
        return padrao
    return f if f == f else padrao


def _mapa_de_colunas(colunas):
    """{nome_interno: nome_real_na_planilha} para o que foi encontrado."""
    por_chave = {}
    for c in colunas:
        por_chave.setdefault(_chave(c), c)
    fora = {}
    for interno, apelidos in COLUNAS.items():
        for a in apelidos:
            if a in por_chave:
                fora[interno] = por_chave[a]
                break
    return fora


def _mes_da_linha(linha, col_mes, col_mes_ano):
    """(ano, mes) da linha. (None, None) quando não dá para saber.

    A coluna Data é a fonte boa; MÊS/ANO ("jan2026") é a reserva, porque a
    planilha às vezes tem a data em branco e o rótulo preenchido.
    """
    d = linha.get(col_mes) if col_mes else None
    a, m = getattr(d, "year", None), getattr(d, "month", None)
    if isinstance(a, int) and isinstance(m, int):
        return a, m
    t = str(linha.get(col_mes_ano, "") if col_mes_ano else "").strip().lower()
    for i, nome in enumerate(MESES, start=1):
        if t.startswith(nome):
            resto = "".join(ch for ch in t[len(nome):] if ch.isdigit())
            if len(resto) >= 4:
                return int(resto[:4]), i
    return None, None


def somar(linhas, colunas, ano=None, mes=None):
    """Soma as colunas somáveis. {nome_interno: total}. Função pura.

    `ano`/`mes` None soma tudo — é como os testes conferem o método sem
    depender de data nenhuma.
    """
    mapa = _mapa_de_colunas(colunas)
    col_data = next((c for c in colunas if _chave(c) == "data"), None)
    col_mes_ano = next((c for c in colunas if _chave(c) in ("mes/ano", "mes ano")),
                       None)
    fora = {k: 0.0 for k in COLUNAS}
    fora["linhas"] = 0
    for l in (linhas or []):
        if ano is not None:
            a, m = _mes_da_linha(l, col_data, col_mes_ano)
            if a != ano or m != mes:
                continue
        fora["linhas"] += 1
        for interno, real in mapa.items():
            fora[interno] += _num(l.get(real))
    return fora


def indicadores(somas):
    """As razões, recalculadas A PARTIR DAS SOMAS. Função pura.

    Nunca da média das colunas de percentual da planilha: uma venda de R$ 10 a
    90% e uma de R$ 1.000 a 10% não fazem 50%, fazem 10,8%. A planilha tem
    MARGEM %, LPV e UNI. CONT. calculados por linha justamente para o dono
    olhar a linha — somá-los ou mediá-los é usar o número para o que ele não
    serve.

    Base do percentual é o FATURAMENTO LÍQUIDO (FAT - DEV) quando ele existe: a
    devolução não foi venda, e deixá-la na base faz toda margem parecer menor
    do que é.
    """
    base = somas.get("fat_liquido") or somas.get("faturamento") or 0.0
    vendas = somas.get("vendas") or 0.0
    lb = somas.get("lucro_bruto") or 0.0
    mc = somas.get("margem_contribuicao") or 0.0
    uni = somas.get("unidades") or 0.0

    def _div(a, b):
        return (a / b) if b else None

    return {
        "faturamento": somas.get("faturamento") or 0.0,
        "faturamento_liquido": base,
        "devolucao": somas.get("devolucao") or 0.0,
        "vendas": vendas,
        "unidades": uni,
        "lucro_bruto": lb,
        "margem_bruta": _div(lb * 100.0, base),
        "margem_contribuicao": mc,
        "margem_contribuicao_pct": _div(mc * 100.0, base),
        "lpv": _div(lb, vendas),
        "uc": _div(uni, vendas),
        "custo_total": somas.get("custo_total") or 0.0,
        "custo_op": somas.get("custo_op") or 0.0,
    }


@st.cache_data(ttl=600, show_spinner=False)
def do_mes(ano, mes):
    """Os indicadores do mês, lidos do Controle MS. (dados, erro).

    Cacheado dez minutos: a leitura abre um `.xlsx` de 11 MB vindo do OneDrive,
    e a Home redesenha a cada clique.
    """
    try:
        import controle_ms as _cms
        df, erro = _cms.ler(ABA)
        if erro:
            return None, erro
        if df is None or df.empty:
            return None, f"A aba «{ABA}» do Controle MS veio vazia."
        linhas = df.to_dict("records")
        somas = somar(linhas, list(df.columns), int(ano), int(mes))
        if not somas["linhas"]:
            return None, (f"Não achei nenhuma venda de {int(mes):02d}/{int(ano)} "
                          f"na aba «{ABA}».")
        fora = indicadores(somas)
        fora["linhas"] = somas["linhas"]
        return fora, ""
    except Exception as e:
        return None, f"Não consegui ler a BASE DE VENDAS: {str(e)[:200]}"


def limpar_cache():
    try:
        do_mes.clear()
    except Exception:
        pass


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    COLS = ["MÊS", "MÊS/ANO", "Data", "FAT TOTAL", "FAT - DEV", "CUSTO TOTAL",
            "CUSTO OP.", "DEVOLUÇÃO", "COMISSÃO", "FRETE", "NF", "L.B",
            "MARGEM C.", "VENDAS", "UNI. CONT.", "MARGEM %", "LPV"]

    # ── O nome da coluna sobrevive a quem edita a planilha ───────────────
    ok("acento nao separa a coluna", _chave("DEVOLUÇÃO") == "devolucao")
    ok("ponto e espaco tambem nao", _chave("UNI. CONT.") == "uni cont")
    ok("nem a caixa", _chave("  Margem C. ") == "margem c")
    ok("as colunas da Home sao achadas",
       set(_mapa_de_colunas(COLS)) >= {"faturamento", "fat_liquido",
                                       "lucro_bruto", "vendas", "unidades"})
    ok("coluna que nao existe nao inventa chave",
       "custo_flex" not in _mapa_de_colunas(COLS))

    # ── Numero, e so ─────────────────────────────────────────────────────
    ok("real brasileiro vira numero", _num("1.234,56") == 1234.56)
    ok("com cifrao tambem", _num("R$ 1.234,56") == 1234.56)
    ok("ponto decimal simples", _num("39.49") == 39.49)
    ok("vazio e zero", _num("") == 0.0 and _num(None) == 0.0)
    ok("texto nao vira numero", _num("Entregue") == 0.0)
    ok("nan nao contamina a soma", _num(float("nan")) == 0.0)
    ok("infinito tambem", _num(float("inf")) == 0.0)
    ok("booleano nao e numero", _num(True) == 0.0)

    # ── A SOMA, e a razao saindo dela ────────────────────────────────────
    # Duas vendas do mesmo mes: uma de R$ 10 com margem de 90%, outra de
    # R$ 1.000 com 10%. A media das margens daria 50%; a conta certa da 10,8%.
    from datetime import datetime as _dt
    L = [
        {"Data": _dt(2026, 9, 1), "MÊS/ANO": "set2026", "FAT TOTAL": 10.0,
         "FAT - DEV": 10.0, "L.B": 9.0, "VENDAS": 1, "UNI. CONT.": 1,
         "DEVOLUÇÃO": 0, "MARGEM C.": 9.0, "CUSTO TOTAL": 1.0, "CUSTO OP.": 0},
        {"Data": _dt(2026, 9, 2), "MÊS/ANO": "set2026", "FAT TOTAL": 1000.0,
         "FAT - DEV": 1000.0, "L.B": 100.0, "VENDAS": 1, "UNI. CONT.": 3,
         "DEVOLUÇÃO": 0, "MARGEM C.": 100.0, "CUSTO TOTAL": 900.0, "CUSTO OP.": 0},
        {"Data": _dt(2026, 8, 30), "MÊS/ANO": "ago2026", "FAT TOTAL": 5000.0,
         "FAT - DEV": 5000.0, "L.B": 2500.0, "VENDAS": 9, "UNI. CONT.": 9,
         "DEVOLUÇÃO": 0, "MARGEM C.": 2500.0, "CUSTO TOTAL": 2500.0, "CUSTO OP.": 0},
    ]
    s = somar(L, COLS, 2026, 9)
    ok("so as linhas do mes pedido entram", s["linhas"] == 2)
    ok("e agosto fica de fora", s["faturamento"] == 1010.0)

    i = indicadores(s)
    ok("a margem sai da SOMA, e nao da media das margens",
       abs(i["margem_bruta"] - 10.792) < 0.01)
    ok("e nao dos 50% que a media daria", i["margem_bruta"] < 20)
    ok("LPV e lucro por VENDA", abs(i["lpv"] - 54.5) < 0.01)
    ok("UC e unidade por venda", abs(i["uc"] - 2.0) < 0.001)

    # ── A devolucao sai da base do percentual ────────────────────────────
    # Deixa-la dentro faz toda margem parecer menor do que e.
    _com_dev = indicadores({"faturamento": 1000.0, "fat_liquido": 800.0,
                            "lucro_bruto": 400.0, "vendas": 10,
                            "unidades": 12, "margem_contribuicao": 0.0})
    ok("o percentual usa FAT - DEV, nao FAT TOTAL",
       abs(_com_dev["margem_bruta"] - 50.0) < 0.001)

    # Sem FAT - DEV na planilha, o FAT TOTAL serve de base — mas nunca se
    # inventa: a chave some e a razao vira None, nao zero.
    _sem = indicadores({"faturamento": 100.0, "lucro_bruto": 25.0, "vendas": 0,
                        "unidades": 0})
    ok("sem FAT - DEV usa o FAT TOTAL",
       abs(_sem["margem_bruta"] - 25.0) < 0.001)
    ok("sem venda nenhuma o LPV e None, e nao zero", _sem["lpv"] is None)
    ok("e o UC tambem", _sem["uc"] is None)

    # Mes sem venda nenhuma nao devolve zeros que parecem dado.
    ok("mes vazio soma zero linhas", somar(L, COLS, 2026, 1)["linhas"] == 0)

    # MÊS/ANO e a reserva de quem esta sem data.
    _sem_data = [{"Data": "", "MÊS/ANO": "set2026", "FAT TOTAL": 7.0,
                  "FAT - DEV": 7.0, "L.B": 1.0, "VENDAS": 1, "UNI. CONT.": 1}]
    ok("linha sem Data cai no MES/ANO",
       somar(_sem_data, COLS, 2026, 9)["faturamento"] == 7.0)

    print("\nfalhas:", falhas)
