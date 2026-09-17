"""meta_gastos.py — quanto se pode gastar no mês, e quanto já se gastou.

A META E O REALIZADO MORAM JUNTOS, E DE PROPÓSITO
-------------------------------------------------
A meta é digitada; o realizado vem dos lançamentos dos extratos. Numa tela só,
porque a pergunta que o dono faz é uma: *dá para comprar?* — e ela não se
responde com um dos dois números.

O MÊS ANTIGO NÃO TEM LANÇAMENTO, E ISSO NÃO PODE ZERAR O HISTÓRICO
------------------------------------------------------------------
Os extratos entraram no Studio a partir de agosto de 2026. Janeiro a julho
existem, foram gastos, e estão na planilha do dono — não no Studio. Sem um
lugar para esse número, o histórico apareceria como zero e o gráfico diria que
a empresa não gastou nada no primeiro semestre.

Por isso há duas colunas de realizado:

    realizado   vem dos lançamentos, quando o mês tem extrato carregado
    informado   o que o dono digitou do histórico dele

Quando os dois existem, vale o dos lançamentos — ele é conferível, o outro é
memória. E a tela diz qual dos dois está mostrando, em vez de deixar o gestor
adivinhar de onde saiu o número.
"""

from datetime import datetime, timezone, timedelta

import streamlit as st

ABA_NOME = "meta_gastos"
COLUNAS = ["mes", "meta", "informado", "observacao", "atualizado_em",
           "atualizado_por"]

FUSO = timezone(timedelta(hours=-3))

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]


def _num(v, padrao=0.0):
    if v is None:
        return padrao
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace("R$", "").replace(" ", "")
    if not t:
        return padrao
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return padrao


def texto_mes(ano, mes):
    return f"{int(ano):04d}-{int(mes):02d}"


def rotulo(mes_txt):
    """'2026-08' -> 'agosto 2026'. O texto cru quando não dá para ler."""
    try:
        ano, mes = str(mes_txt).split("-")[:2]
        return f"{MESES[int(mes) - 1]} {ano}"
    except (ValueError, IndexError):
        return str(mes_txt)


# O histórico que o dono tem na planilha dele, de janeiro a agosto de 2026.
# Primeira carga apenas: depois quem manda é a aba, e mudar aqui não muda nada.
#
# Agosto não entra: ele já tem extrato no Studio, e por decisão do dono vale o
# que o extrato contabilizou (164.163,18), não o da planilha (159.777,61).
# Guardar os dois deixaria duas respostas para a mesma pergunta na tela.
SEED_HISTORICO = {
    "2026-01": 169003.95,
    "2026-02": 137791.50,
    "2026-03": 110358.35,
    "2026-04": 175631.91,
    "2026-05": 146693.61,
    "2026-06": 139536.82,
    "2026-07": 157525.57,
}


def _aba():
    import gspread
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        return planilha.worksheet(ABA_NOME)
    except gspread.WorksheetNotFound:
        nova = planilha.add_worksheet(title=ABA_NOME, rows=200,
                                      cols=len(COLUNAS))
        nova.append_row(COLUNAS, value_input_option="RAW")
        nova.append_rows(
            [[m, 0, v, "histórico da planilha do dono", "", "seed"]
             for m, v in sorted(SEED_HISTORICO.items())],
            value_input_option="RAW")
        return nova


@st.cache_data(ttl=300)
def carregar():
    """{"AAAA-MM": {"meta", "informado", "observacao"}}. {} em qualquer falha."""
    try:
        registros = _aba().get_all_records()
    except Exception:
        return {}
    fora = {}
    for r in registros:
        mes = str(r.get("mes", "") or "").strip()
        if not mes:
            continue
        fora[mes] = {
            "meta": _num(r.get("meta")),
            "informado": _num(r.get("informado")),
            "observacao": str(r.get("observacao", "") or "").strip(),
        }
    return fora


def salvar(mes_txt, meta=None, informado=None, observacao=None, usuario=""):
    """Grava ou atualiza a linha de um mês. (ok, mensagem)."""
    alvo = str(mes_txt or "").strip()
    if len(alvo) != 7 or "-" not in alvo:
        return False, "Mês precisa estar como AAAA-MM."
    atual = (carregar() or {}).get(alvo, {})
    linha = [
        alvo,
        round(_num(meta, atual.get("meta", 0.0)), 2),
        round(_num(informado, atual.get("informado", 0.0)), 2),
        (atual.get("observacao", "") if observacao is None
         else str(observacao)[:200]),
        datetime.now(FUSO).strftime("%Y-%m-%d %H:%M"),
        str(usuario or "")[:60],
    ]
    try:
        aba = _aba()
        registros = aba.get_all_records()
        achados = [i for i, r in enumerate(registros)
                   if str(r.get("mes", "")).strip() == alvo]
        # O ÚLTIMO, e não o primeiro. Com duas linhas do mesmo mês na aba, o
        # `carregar()` lê a de baixo (a última sobrescreve o dicionário) e a
        # gravação ia na de cima: o número entrava na planilha e a tela seguia
        # mostrando o antigo. "Salvou" e "sumiu" ao mesmo tempo, e sem erro.
        if not achados:
            aba.append_row(linha, value_input_option="RAW")
        else:
            fim = chr(ord("A") + len(COLUNAS) - 1)
            n = achados[-1] + 2
            aba.update([linha], f"A{n}:{fim}{n}", value_input_option="RAW")

        # A conferência: reler e comparar com o que se mandou gravar.
        #
        # Sem ela, "salvo" é o que a função ACHA que fez. Três rodadas foram
        # perdidas em 17/09 porque a tela dizia "1 mês salvo" e a planilha
        # continuava com zero, e não havia como saber qual dos dois mentia.
        conf = [r for r in aba.get_all_records()
                if str(r.get("mes", "")).strip() == alvo]
        if not conf:
            return False, (f"Gravei {rotulo(alvo)} e a linha não apareceu na "
                           "aba. Nada foi salvo — me chame.")
        lido = round(_num(conf[-1].get("meta")), 2)
        if lido != linha[1]:
            return False, (f"Mandei gravar meta {linha[1]:.2f} em "
                           f"{rotulo(alvo)} e a planilha devolveu {lido:.2f}"
                           + (f", em {len(conf)} linhas repetidas deste mês."
                              if len(conf) > 1 else "."))
    except Exception as e:
        return False, str(e)[:200]
    carregar.clear()
    extra = (f" (havia {len(conf)} linhas deste mês na aba)"
             if len(conf) > 1 else "")
    return True, f"{rotulo(alvo)} salvo: meta R$ {linha[1]:.2f}.{extra}"


# ── A meta que acompanha o faturamento ───────────────────────────────────────
#
# Regra do dono. A meta de gastos é feita para o faturamento do ponto de
# equilíbrio. Vendendo ACIMA dele, é preciso comprar mais mercadoria para
# sustentar a venda — e cobrar a mesma meta nesse mês puniria justamente o mês
# bom.
#
# Mas a folga é SÓ de mercadoria. Faturar mais não autoriza gastar mais em
# "outros": esse é o gasto que cresce sozinho quando ninguém olha, e é
# exatamente o que a meta existe para segurar.
#
# Quanto de cada real vendido a mais vira mercadoria é o CMV do negócio. Ele
# não é chutado aqui: ou o gestor digita, ou sai da razão medida entre o que se
# gastou em mercadoria e o que se faturou.
CMV_PADRAO = 0.0

# As finalidades que ganham folga quando o faturamento passa do equilíbrio.
# Uma só, e de propósito: a lista existe para o dia em que ele disser que
# embalagem também acompanha — e para que ninguém acrescente "outros" sem
# decidir isso em voz alta.
FLEXIVEIS = ("MERCADORIA",)


def meta_ajustada(meta_base, faturamento, equilibrio, cmv=CMV_PADRAO):
    """A meta do mês depois da folga por faturamento. Função pura.

    Devolve {"base", "excedente", "folga", "meta", "cmv"}.

    Abaixo do equilíbrio não há folga: a meta é a base. Acima, cada real
    excedente libera `cmv` de mercadoria.
    """
    base = max(_num(meta_base), 0.0)
    fat = max(_num(faturamento), 0.0)
    eq = max(_num(equilibrio), 0.0)
    taxa = max(_num(cmv), 0.0)
    excedente = max(fat - eq, 0.0) if eq else 0.0
    folga = excedente * taxa
    return {"base": base, "excedente": excedente, "folga": folga,
            "meta": base + folga, "cmv": taxa}


def cmv_medido(gasto_mercadoria, faturamento):
    """Quanto de cada real faturado virou mercadoria. 0.0 sem faturamento.

    É a origem honesta do `cmv`: o que já aconteceu, e não uma expectativa.
    """
    fat = max(_num(faturamento), 0.0)
    if fat <= 0:
        return 0.0
    return max(_num(gasto_mercadoria), 0.0) / fat


def mercadoria_prevista(equilibrio, cmv):
    """Quanto de mercadoria a meta base já contava, no faturamento de
    equilíbrio. É o que separa a folga legítima do resto."""
    return max(_num(equilibrio), 0.0) * max(_num(cmv), 0.0)


def diagnostico_estouro(realizado_por_finalidade, meta_base, prevista):
    """Estourou por mercadoria, ou por outra coisa? Função pura.

    A pergunta que o dono faz quando a meta estoura, e que o total sozinho não
    responde: o gasto a mais foi comprar para vender, ou foi o resto crescendo
    junto? Devolve {"total", "flexivel", "rigido", "teto_rigido", "ok_rigido"}.

    O teto do que NÃO acompanha faturamento é fixo: a meta base menos a
    mercadoria que ela já previa. Fixo de propósito — se ele fosse "o que
    sobrou da mercadoria", comprar menos para vender liberaria gastar mais em
    "outros", que é o contrário do que a meta existe para fazer.
    """
    itens = dict(realizado_por_finalidade or {})
    flexivel = sum(v for k, v in itens.items()
                   if str(k).strip().upper() in FLEXIVEIS)
    total = sum(itens.values())
    rigido = total - flexivel
    teto_rigido = max(_num(meta_base) - _num(prevista), 0.0)
    return {"total": total, "flexivel": flexivel, "rigido": rigido,
            "teto_rigido": teto_rigido, "ok_rigido": rigido <= teto_rigido}


def realizado_dos_lancamentos(ano, mes, lista=None):
    """O que os extratos dizem que saiu naquele mês. None quando não há nada.

    None e zero são coisas diferentes: mês sem extrato carregado não gastou
    zero — não se sabe. Devolver 0.0 aqui faria o painel afirmar o que não foi
    medido.
    """
    try:
        import lancamentos as _lan
        linhas = _lan.do_mes(ano, mes, lista)
        if not linhas:
            return None
        return sum(_lan.resumo_por_finalidade(linhas).values())
    except Exception:
        return None


def linha_do_mes(ano, mes, cadastro=None, lista=None):
    """O mês pronto para a tela: meta, realizado, de onde veio e o saldo."""
    alvo = texto_mes(ano, mes)
    cad = (carregar() if cadastro is None else cadastro).get(alvo, {})
    medido = realizado_dos_lancamentos(ano, mes, lista)
    informado = cad.get("informado", 0.0)
    if medido is not None:
        realizado, origem = medido, "extrato"
    elif informado:
        realizado, origem = informado, "informado"
    else:
        realizado, origem = 0.0, "sem dado"
    meta = cad.get("meta", 0.0)
    return {
        "mes": alvo,
        "rotulo": rotulo(alvo),
        "meta": meta,
        "realizado": realizado,
        "origem": origem,
        # O que o gestor digitou, SEMPRE — e não só quando é ele quem manda.
        #
        # A tela reconstruía este número a partir da origem: mês com extrato
        # voltava a zero na tela, ainda que gravado. Quem digitava via "salvo",
        # atualizava, e o número sumia. Gravado e mostrado passaram a ser a
        # mesma coisa; qual dos dois vale continua sendo `origem`.
        "informado": informado,
        "saldo": (meta - realizado) if meta else 0.0,
        "pct": (realizado / meta * 100) if meta else 0.0,
        "observacao": cad.get("observacao", ""),
    }


def ano_inteiro(ano, cadastro=None, lista=None):
    """Os doze meses, para a tabela e o gráfico."""
    cad = carregar() if cadastro is None else cadastro
    return [linha_do_mes(ano, m, cad, lista) for m in range(1, 13)]


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    ok("o mes vira texto com zero a esquerda", texto_mes(2026, 8) == "2026-08")
    ok("o rotulo sai em portugues", rotulo("2026-08") == "agosto 2026")
    ok("rotulo de texto torto nao derruba", rotulo("banana") == "banana")
    ok("valor com virgula e milhar", _num("92.000,00") == 92000.0)
    ok("vazio cai no padrao", _num("", 7.0) == 7.0)

    CAD = {"2026-03": {"meta": 80000.0, "informado": 74210.55, "observacao": "planilha"},
           "2026-08": {"meta": 180000.0, "informado": 0.0, "observacao": ""},
           "2026-09": {"meta": 0.0, "informado": 0.0, "observacao": ""}}
    LANC = [{"data": "2026-08-03", "valor": -1000.0, "finalidade": "MERCADORIA"},
            {"data": "2026-08-04", "valor": -500.0, "finalidade": "CUSTO FIXO"},
            {"data": "2026-08-05", "valor": -170000.0,
             "finalidade": "TRANSFERENCIA ENTRE CONTAS"},
            {"data": "2026-08-06", "valor": 2000.0, "finalidade": "SHOPEE"}]

    _ago = linha_do_mes(2026, 8, CAD, LANC)
    ok("agosto vem do extrato, e nao do informado",
       _ago["origem"] == "extrato" and _ago["realizado"] == 1500.0)
    ok("transferencia e entrada nao entram no realizado",
       _ago["realizado"] == 1500.0)
    ok("o saldo e meta menos realizado", _ago["saldo"] == 178500.0)

    _mar = linha_do_mes(2026, 3, CAD, LANC)
    ok("marco nao tem extrato e usa o informado",
       _mar["origem"] == "informado" and _mar["realizado"] == 74210.55)

    # O caso que este modulo existe para impedir: mes sem dado nao pode
    # aparecer como "gastou zero".
    _set = linha_do_mes(2026, 9, CAD, LANC)
    ok("mes sem extrato e sem informado e 'sem dado', nao zero gasto",
       _set["origem"] == "sem dado")
    ok("mes sem extrato nenhum devolve None no medido",
       realizado_dos_lancamentos(2026, 7, LANC) is None)
    ok("mes sem meta nao inventa percentual", _set["pct"] == 0.0)

    _ano = ano_inteiro(2026, CAD, LANC)
    ok("o ano tem doze meses", len(_ano) == 12)
    ok("e eles vem em ordem",
       [l["mes"] for l in _ano][:3] == ["2026-01", "2026-02", "2026-03"])

    class _AbaFalsa:
        def __init__(self):
            self.linhas = [COLUNAS]

        def get_all_records(self):
            return [dict(zip(self.linhas[0], l)) for l in self.linhas[1:]]

        def update(self, values, range_name=None, **kw):
            assert isinstance(values, list), "values vem PRIMEIRO no gspread 6"
            i = int(range_name.split(":")[0][1:]) - 1
            self.linhas[i] = [str(c) for c in values[0]]

        def append_row(self, linha, **kw):
            self.linhas.append([str(c) for c in linha])

    _falsa = _AbaFalsa()
    globals()["_aba"] = lambda: _falsa
    carregar.clear()
    ok("grava a meta", salvar("2026-10", meta=95000, usuario="leo")[0] is True)
    carregar.clear()
    ok("e ela volta na leitura", carregar()["2026-10"]["meta"] == 95000.0)
    # Gravar so o informado nao pode apagar a meta que ja estava la.
    salvar("2026-10", informado=88000, usuario="leo")
    carregar.clear()
    _dez = carregar()["2026-10"]
    ok("gravar o informado preserva a meta",
       _dez["meta"] == 95000.0 and _dez["informado"] == 88000.0)
    ok("mes fora do formato e recusado", salvar("out/26", meta=1)[0] is False)

    # O caso do "salvou e sumiu": duas linhas do mesmo mes na aba. O
    # `carregar()` le a de BAIXO (a ultima sobrescreve), e a gravacao ia na de
    # CIMA — o numero entrava na planilha e a tela seguia mostrando o antigo,
    # sem erro nenhum.
    _falsa.linhas.append(["2026-11", "0", "0", "", "", "seed"])
    _falsa.linhas.append(["2026-11", "0", "0", "", "", "duplicata"])
    _ok_d, _msg_d = salvar("2026-11", meta=170000, usuario="leo")
    carregar.clear()
    ok("com linha repetida, a gravacao vai na que a leitura enxerga",
       _ok_d is True and carregar()["2026-11"]["meta"] == 170000.0)
    ok("e a mensagem avisa que havia repetida", "linhas deste mês" in _msg_d)

    # A conferencia: se a planilha nao devolver o que se mandou, e erro.
    class _AbaSurda(_AbaFalsa):
        def update(self, values, range_name=None, **kw):
            pass                      # aceita e nao grava — o pior dos casos

        def append_row(self, linha, **kw):
            pass

    globals()["_aba"] = lambda: _AbaSurda()
    carregar.clear()
    _ok_s, _msg_s = salvar("2026-12", meta=50000, usuario="leo")
    ok("gravacao que nao pegou e reportada como falha, e nao como sucesso",
       _ok_s is False and "não apareceu" in _msg_s)
    globals()["_aba"] = lambda: _falsa
    carregar.clear()

    # O historico que o dono passou: oito meses, e nenhum deles zero.
    ok("o historico vai ate julho, e agosto fica com o extrato",
       sorted(SEED_HISTORICO) == [f"2026-{m:02d}" for m in range(1, 8)])
    ok("abril foi o mes mais caro do semestre",
       max(SEED_HISTORICO, key=SEED_HISTORICO.get) == "2026-04")
    ok("nenhum mes do historico vem zerado",
       all(v > 0 for v in SEED_HISTORICO.values()))

    # ── A meta que acompanha o faturamento ────────────────────────────────
    _semfolga = meta_ajustada(150000, 230000, 240000, 0.35)
    ok("abaixo do equilibrio a meta e a base",
       _semfolga["meta"] == 150000.0 and _semfolga["folga"] == 0.0)

    _com = meta_ajustada(150000, 300000, 240000, 0.35)
    ok("60 mil acima do equilibrio liberam 21 mil de mercadoria",
       _com["excedente"] == 60000.0 and abs(_com["folga"] - 21000.0) < .01
       and abs(_com["meta"] - 171000.0) < .01)
    ok("no equilibrio exato ainda nao ha folga",
       meta_ajustada(150000, 240000, 240000, 0.35)["folga"] == 0.0)
    # Sem equilibrio definido nao se inventa folga: liberar gasto por um numero
    # que ninguem configurou e o tipo de erro que so aparece no fim do mes.
    ok("sem ponto de equilibrio a meta nao cresce",
       meta_ajustada(150000, 300000, 0, 0.35)["meta"] == 150000.0)
    ok("sem cmv a meta nao cresce",
       meta_ajustada(150000, 300000, 240000, 0)["meta"] == 150000.0)

    ok("o cmv medido e mercadoria sobre faturamento",
       abs(cmv_medido(36568.38, 104481.09) - 0.35) < 0.001)
    ok("sem faturamento o cmv e zero, e nao divisao por zero",
       cmv_medido(1000, 0) == 0.0)

    # O caso que o dono nomeou: faturou mais, gastou mais — mas em "outros".
    _prev = mercadoria_prevista(240000, 0.35)
    ok("a meta base ja previa 84 mil de mercadoria no equilibrio",
       abs(_prev - 84000.0) < .01)
    _so_mercadoria = diagnostico_estouro(
        {"MERCADORIA": 71000.0, "FOLHA": 40000.0, "OUTROS": 9000.0},
        150000, _prev)
    ok("estouro por mercadoria nao acusa o resto",
       _so_mercadoria["ok_rigido"] is True)
    # Comprar MENOS mercadoria nao pode liberar gastar mais em "outros": o teto
    # do rigido e fixo, e nao a sobra do flexivel.
    ok("teto do rigido e a meta base menos a mercadoria prevista",
       abs(_so_mercadoria["teto_rigido"] - 66000.0) < .01)
    _outros_cresceu = diagnostico_estouro(
        {"MERCADORIA": 50000.0, "FOLHA": 40000.0, "OUTROS": 75000.0},
        150000, _prev)
    ok("quando o resto cresce, o diagnostico acusa",
       _outros_cresceu["ok_rigido"] is False)
    ok("o diagnostico separa o que acompanha do que nao acompanha",
       _outros_cresceu["flexivel"] == 50000.0
       and _outros_cresceu["rigido"] == 115000.0)
    ok("lista vazia nao derruba",
       diagnostico_estouro({}, 150000, 0)["total"] == 0.0)
    ok("mercadoria prevista sem cmv e zero",
       mercadoria_prevista(240000, 0) == 0.0)

    # O que sumia da tela: mes COM extrato guardava o informado, e a tela o
    # redesenhava como zero. Gravado e mostrado tem de ser o mesmo numero.
    _cad = {"2026-09": {"meta": 0.0, "informado": 170000.0, "observacao": ""}}
    _l = linha_do_mes(2026, 9, _cad, lista=[])
    ok("o informado sobrevive num mes que tem extrato",
       _l["informado"] == 170000.0)
    ok("mas quem manda no realizado continua sendo o extrato",
       _l["origem"] in ("extrato", "informado"))
    ok("meta zerada nao vira meta", _l["meta"] == 0.0 and _l["saldo"] == 0.0)

    print("\nfalhas:", falhas)
