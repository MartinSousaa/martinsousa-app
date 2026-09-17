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
# Agosto entra nos dois lugares — aqui como informado (159.777,61) e nos
# extratos como medido (164.163,18). A diferença de 4.385,57 não é erro de
# nenhum dos dois: é o que a planilha dele conta de um jeito e o extrato de
# outro, e vale perguntar antes de fechar o ano. Por isso o valor informado
# fica registrado mesmo no mês que já tem extrato.
SEED_HISTORICO = {
    "2026-01": 169003.95,
    "2026-02": 137791.50,
    "2026-03": 110358.35,
    "2026-04": 175631.91,
    "2026-05": 146693.61,
    "2026-06": 139536.82,
    "2026-07": 157525.57,
    "2026-08": 159777.61,
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
        pos = next((i for i, r in enumerate(registros)
                    if str(r.get("mes", "")).strip() == alvo), None)
        if pos is None:
            aba.append_row(linha, value_input_option="RAW")
        else:
            fim = chr(ord("A") + len(COLUNAS) - 1)
            aba.update([linha], f"A{pos + 2}:{fim}{pos + 2}",
                       value_input_option="RAW")
    except Exception as e:
        return False, str(e)[:200]
    carregar.clear()
    return True, f"{rotulo(alvo)} salvo."


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

    # O historico que o dono passou: oito meses, e nenhum deles zero.
    ok("o historico tem janeiro a agosto",
       sorted(SEED_HISTORICO) == [f"2026-{m:02d}" for m in range(1, 9)])
    ok("abril foi o mes mais caro do semestre",
       max(SEED_HISTORICO, key=SEED_HISTORICO.get) == "2026-04")
    ok("nenhum mes do historico vem zerado",
       all(v > 0 for v in SEED_HISTORICO.values()))

    print("\nfalhas:", falhas)
