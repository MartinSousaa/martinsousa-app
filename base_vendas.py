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
def somas_por_mes():
    """{(ano, mes): somas} de TODOS os meses da aba. (mapa, erro).

    UMA LEITURA, TODOS OS MESES.
    ---------------------------
    Abrir a aba custa baixar um `.xlsx` de 11 MB do OneDrive. Enquanto a Home
    pedia um mês só, um download por tela era caro mas tolerável. Agora ela
    pede a média dos três últimos — e um download por mês seriam TRÊS, na tela
    que passou a ser a primeira que o dono vê ao entrar.

    Então lê uma vez e soma tudo. Quem quer um mês pega um; quem quer três,
    pega três, sem voltar ao disco.
    """
    try:
        import controle_ms as _cms
        df, erro = _cms.ler(ABA)
        if erro:
            return {}, erro
        if df is None or df.empty:
            return {}, f"A aba «{ABA}» do Controle MS veio vazia."
        colunas = list(df.columns)
        mapa = _mapa_de_colunas(colunas)
        col_data = next((c for c in colunas if _chave(c) == "data"), None)
        col_mes_ano = next(
            (c for c in colunas if _chave(c) in ("mes/ano", "mes ano")), None)

        fora = {}
        for l in df.to_dict("records"):
            a, m = _mes_da_linha(l, col_data, col_mes_ano)
            if a is None:
                continue
            alvo = fora.setdefault((a, m), {k: 0.0 for k in COLUNAS})
            alvo.setdefault("linhas", 0)
            alvo["linhas"] += 1
            for interno, real in mapa.items():
                alvo[interno] += _num(l.get(real))
        return fora, ""
    except Exception as e:
        return {}, f"Não consegui ler a BASE DE VENDAS: {str(e)[:200]}"


def meses_com_venda(mapa, ate_ano=None, ate_mes=None, quantos=3):
    """Os `quantos` meses mais recentes que TÊM venda, do mais novo para trás.

    "Últimos três meses" não é "os três meses anteriores ao de hoje": em
    22/09/2026 a planilha ia até agosto, e contar julho–setembro daria um mês
    vazio no meio da conta. O que vale é o que está lançado.
    """
    chaves = sorted((k for k, v in (mapa or {}).items() if v.get("linhas")),
                    reverse=True)
    if ate_ano is not None:
        chaves = [(a, m) for (a, m) in chaves
                  if (a, m) <= (int(ate_ano), int(ate_mes))]
    return chaves[:int(quantos)]


def media_dos_meses(mapa, chaves):
    """Os indicadores médios desses meses. Função pura.

    DUAS MÉDIAS DIFERENTES, E CONFUNDI-LAS DÁ NÚMERO ERRADO:

    - Valor em R$ (lucro bruto, devolução) -> MÉDIA ARITMÉTICA dos meses. É a
      resposta para "quanto costuma dar num mês".
    - Razão (margem, LPV, UC) -> das SOMAS do período. Média de três margens
      trataria um mês de R$ 10 mil igual a um de R$ 250 mil, e o resultado não
      seria a margem de ninguém.
    """
    if not chaves:
        return None
    total = {k: 0.0 for k in COLUNAS}
    total["linhas"] = 0
    for k in chaves:
        for campo, valor in (mapa.get(k) or {}).items():
            total[campo] = total.get(campo, 0.0) + valor
    fora = indicadores(total)          # as razões, já a partir das somas
    n = len(chaves)
    # Os valores em R$ viram média do período; as razões ficam como estão.
    for campo in ("faturamento", "faturamento_liquido", "devolucao",
                  "lucro_bruto", "margem_contribuicao", "custo_total",
                  "custo_op", "vendas", "unidades"):
        if fora.get(campo) is not None:
            fora[campo] = fora[campo] / n
    fora["meses"] = n
    fora["linhas"] = total["linhas"]
    # As SOMAS cruas viajam junto. `indicadores` devolve só as razões e os
    # valores que a Home desenha, e comissão, frete e NF ficavam de fora —
    # mas são justamente eles que dizem quanto do faturamento cai na conta,
    # que é o divisor da meta. Recalcular isso noutro lugar seria ler a
    # planilha de 11 MB uma segunda vez.
    fora["somas"] = dict(total)
    return fora


def do_mes(ano, mes):
    """Os indicadores de UM mês. (dados, erro). Mantida para quem já usava."""
    mapa, erro = somas_por_mes()
    if erro:
        return None, erro
    somas = mapa.get((int(ano), int(mes)))
    if not somas or not somas.get("linhas"):
        return None, (f"Não achei nenhuma venda de {int(mes):02d}/{int(ano)} "
                      f"na aba «{ABA}».")
    fora = indicadores(somas)
    fora["linhas"] = somas["linhas"]
    fora["somas"] = dict(somas)
    return fora, ""


def media_recente(ate_ano, ate_mes, quantos=3):
    """A média dos `quantos` meses lançados mais recentes. (dados, erro).

    É o que a Home usa: o dono pediu "média dos últimos 3 meses" justamente
    porque o mês corrente ainda não foi lançado na planilha, e um mês pela
    metade não descreve o negócio.
    """
    mapa, erro = somas_por_mes()
    if erro:
        return None, erro
    chaves = meses_com_venda(mapa, ate_ano, ate_mes, quantos)
    if not chaves:
        return None, f"A aba «{ABA}» não tem venda lançada em mês nenhum."
    fora = media_dos_meses(mapa, chaves)
    fora["periodo"] = _texto_periodo(chaves)
    fora["chaves"] = chaves
    return fora, ""


_MES_CURTO = ("jan", "fev", "mar", "abr", "mai", "jun",
              "jul", "ago", "set", "out", "nov", "dez")


def _texto_periodo(chaves):
    """"jun–ago/2026" ou "ago/2026" — o que a tela mostra ao lado do número.

    Número sem período é número que ninguém consegue conferir, e aqui o
    período muda sozinho conforme eles lançam a planilha.
    """
    if not chaves:
        return ""
    novos = sorted(chaves)
    (a1, m1), (a2, m2) = novos[0], novos[-1]
    if (a1, m1) == (a2, m2):
        return f"{_MES_CURTO[m1 - 1]}/{a1}"
    if a1 == a2:
        return f"{_MES_CURTO[m1 - 1]}–{_MES_CURTO[m2 - 1]}/{a1}"
    return f"{_MES_CURTO[m1 - 1]}/{a1}–{_MES_CURTO[m2 - 1]}/{a2}"


def limpar_cache():
    try:
        somas_por_mes.clear()
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

    # ── A MEDIA DOS ULTIMOS MESES ────────────────────────────────────────
    #
    # O dono pediu isso porque o mes corrente ainda nao foi lancado na
    # planilha: "setembro ainda nao, precisamos configurar para que o sistema
    # considere o faturamento atraves do bling (...) os outros indicadores
    # preciso que seja considerado a media dos ultimos 3 meses".
    _MAPA = {
        (2026, 6): {"linhas": 1, "faturamento": 100.0, "fat_liquido": 100.0,
                    "lucro_bruto": 10.0, "vendas": 1, "unidades": 1,
                    "devolucao": 0.0, "margem_contribuicao": 0.0,
                    "custo_total": 0.0, "custo_op": 0.0},
        (2026, 7): {"linhas": 1, "faturamento": 200.0, "fat_liquido": 200.0,
                    "lucro_bruto": 20.0, "vendas": 1, "unidades": 3,
                    "devolucao": 0.0, "margem_contribuicao": 0.0,
                    "custo_total": 0.0, "custo_op": 0.0},
        (2026, 8): {"linhas": 1, "faturamento": 300.0, "fat_liquido": 300.0,
                    "lucro_bruto": 30.0, "vendas": 2, "unidades": 2,
                    "devolucao": 0.0, "margem_contribuicao": 0.0,
                    "custo_total": 0.0, "custo_op": 0.0},
        (2026, 5): {"linhas": 1, "faturamento": 999.0, "fat_liquido": 999.0,
                    "lucro_bruto": 999.0, "vendas": 1, "unidades": 1,
                    "devolucao": 0.0, "margem_contribuicao": 0.0,
                    "custo_total": 0.0, "custo_op": 0.0},
        (2026, 9): {"linhas": 0},          # setembro existe e esta VAZIO
    }

    # "Ultimos tres meses" e os tres LANCADOS, e nao os tres anteriores ao de
    # hoje: em 22/09 a planilha ia ate agosto, e contar jul-set poria um mes
    # vazio no meio da conta.
    _ch = meses_com_venda(_MAPA, 2026, 9, 3)
    ok("os tres meses lancados mais recentes, do novo para tras",
       _ch == [(2026, 8), (2026, 7), (2026, 6)])
    ok("o mes vazio fica de fora", (2026, 9) not in _ch)
    ok("e o quarto mais antigo tambem", (2026, 5) not in _ch)
    ok("pedindo 2, vem 2", len(meses_com_venda(_MAPA, 2026, 9, 2)) == 2)
    ok("mapa vazio nao devolve mes nenhum", meses_com_venda({}, 2026, 9) == [])

    _m = media_dos_meses(_MAPA, _ch)
    # Valor em R$ -> media aritmetica: (100+200+300)/3 = 200
    ok("o faturamento e a MEDIA dos meses", abs(_m["faturamento"] - 200.0) < 0.01)
    ok("e o lucro tambem", abs(_m["lucro_bruto"] - 20.0) < 0.01)
    # Razao -> das SOMAS: 60/600 = 10%. A media das tres margens daria 10%
    # tambem neste exemplo simetrico; o caso que separa as duas contas esta
    # logo abaixo.
    ok("a margem sai das somas", abs(_m["margem_bruta"] - 10.0) < 0.01)
    ok("o LPV e lucro total / vendas totais, e nao media de LPVs",
       abs(_m["lpv"] - (60.0 / 4)) < 0.01)
    ok("e o UC idem", abs(_m["uc"] - (6.0 / 4)) < 0.01)
    ok("o periodo vem junto do numero", _m["meses"] == 3)

    # O CASO QUE SEPARA AS DUAS CONTAS: um mes pequeno com margem alta e um
    # grande com margem baixa. Media de margens diria 50%; a conta certa, 10,8%.
    _DESIGUAL = {
        (2026, 7): {"linhas": 1, "faturamento": 10.0, "fat_liquido": 10.0,
                    "lucro_bruto": 9.0, "vendas": 1, "unidades": 1},
        (2026, 8): {"linhas": 1, "faturamento": 1000.0, "fat_liquido": 1000.0,
                    "lucro_bruto": 100.0, "vendas": 1, "unidades": 1},
    }
    _md = media_dos_meses(_DESIGUAL, [(2026, 8), (2026, 7)])
    ok("margem do periodo e ponderada, nao media de percentuais",
       abs(_md["margem_bruta"] - 10.792) < 0.01)
    ok("e nao os 50% que a media de margens daria", _md["margem_bruta"] < 20)

    # O texto do periodo, que e o que impede o numero de ficar sem origem.
    ok("periodo de tres meses do mesmo ano",
       _texto_periodo([(2026, 6), (2026, 7), (2026, 8)]) == "jun–ago/2026")
    ok("um mes so nao vira intervalo",
       _texto_periodo([(2026, 8)]) == "ago/2026")
    ok("virada de ano aparece inteira",
       _texto_periodo([(2025, 12), (2026, 1)]) == "dez/2025–jan/2026")
    ok("sem mes, sem periodo", _texto_periodo([]) == "")

    ok("sem mes nenhum, a media nao inventa numero",
       media_dos_meses(_MAPA, []) is None)

    print("\nfalhas:", falhas)
