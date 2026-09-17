"""lancamentos.py — o que saiu e entrou, vindo do extrato e editável depois.

A DECISÃO QUE DEU A FORMA
------------------------
O dono escolheu: o extrato **entra sozinho**, sem tela de confirmação, e o que
precisar de correção se corrige depois — "um lápis na linha". É menos clique e
menos espera, e o custo é ter que desfazer quando algo entra errado. Daí as
duas capacidades obrigatórias deste módulo: alterar e apagar uma linha.

SUBIR O MESMO ARQUIVO DUAS VEZES NÃO PODE DOBRAR O MÊS
------------------------------------------------------
É o que vai acontecer: extrato baixado de novo, arquivo reenviado, o mesmo
período subindo duas vezes. Sem identidade, cada lançamento entraria outra vez
e o gasto do mês dobraria — em silêncio, porque nenhuma das duas cópias está
errada sozinha.

A identidade é conta + data + valor + descrição. Não é o número do documento:
o Inter não tem, e o Itaú repete o dele. Duas linhas realmente idênticas no
mesmo dia (dois Pix de R$ 10,00 para o mesmo fornecedor) são raras, e quando
acontecem o `seq` as separa.

O QUE ELE NÃO DECIDE
--------------------
Nada de finalidade. Isso é `favorecidos.py`, e a separação é de propósito: aqui
mora o fato (saiu R$ 1.303,00 para a APEXIMP em 03/08), lá mora o significado
(APEXIMP é mercadoria). O fato não muda; o significado o dono corrige quando
quiser, e a correção vale para o passado inteiro.
"""

import hashlib
from datetime import date, datetime, timezone, timedelta

import streamlit as st

ABA_NOME = "lancamentos"
COLUNAS = ["id", "conta", "data", "descricao", "favorecido", "valor",
           "tipo", "finalidade", "observacao", "atualizado_em", "atualizado_por"]

FUSO = timezone(timedelta(hours=-3))


def _txt_data(v):
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    return str(v or "").strip()[:10]


def identidade(lanc, conta="", seq=0):
    """A impressão digital de um lançamento. Sempre a mesma para o mesmo fato.

    `seq` só entra quando duas linhas do arquivo são idênticas em tudo — é o
    que impede que a segunda seja tomada pela primeira e descartada.
    """
    bruto = "|".join([
        str(conta or "").strip(),
        _txt_data(lanc.get("data")),
        f"{float(lanc.get('valor') or 0):.2f}",
        " ".join(str(lanc.get("descricao") or "").upper().split()),
        str(seq) if seq else "",
    ])
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()[:16]


def com_identidade(lancamentos, conta=""):
    """A lista com `id` em cada item, resolvendo os idênticos com `seq`."""
    fora, vistos = [], {}
    for l in (lancamentos or []):
        base = identidade(l, conta)
        n = vistos.get(base, 0)
        vistos[base] = n + 1
        novo = dict(l)
        novo["id"] = base if n == 0 else identidade(l, conta, seq=n)
        novo["conta"] = conta
        fora.append(novo)
    return fora


def _aba():
    import gspread
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        return planilha.worksheet(ABA_NOME)
    except gspread.WorksheetNotFound:
        nova = planilha.add_worksheet(title=ABA_NOME, rows=2000,
                                      cols=len(COLUNAS))
        nova.append_row(COLUNAS, value_input_option="RAW")
        return nova


@st.cache_data(ttl=120)
def carregar():
    """Todos os lançamentos gravados. [] em qualquer falha."""
    try:
        registros = _aba().get_all_records()
    except Exception:
        return []
    fora = []
    for r in registros:
        if not str(r.get("id", "")).strip():
            continue
        try:
            valor = float(str(r.get("valor", 0) or 0).replace(",", "."))
        except ValueError:
            valor = 0.0
        fora.append({**{c: str(r.get(c, "") or "") for c in COLUNAS},
                     "valor": valor})
    return fora


def ids_gravados():
    """{id} do que já está na planilha. Para não subir duas vezes."""
    return {l["id"] for l in carregar()}


def gravar(lancamentos, conta="", usuario=""):
    """Acrescenta o que ainda não existe. (novos, repetidos, erro).

    Nunca reescreve linha existente: o dono pode ter corrigido a finalidade à
    mão, e subir o extrato de novo não pode desfazer a correção dele.
    """
    itens = com_identidade(lancamentos, conta)
    if not itens:
        return 0, 0, ""
    try:
        ja = ids_gravados()
    except Exception as e:
        return 0, 0, f"Não consegui ler o que já está gravado: {str(e)[:120]}"
    novos = [l for l in itens if l["id"] not in ja]
    repetidos = len(itens) - len(novos)
    if not novos:
        return 0, repetidos, ""
    agora = datetime.now(FUSO).strftime("%Y-%m-%d %H:%M")
    linhas = [[
        l["id"], l.get("conta", ""), _txt_data(l.get("data")),
        str(l.get("descricao", ""))[:180], str(l.get("favorecido", ""))[:120],
        round(float(l.get("valor") or 0), 2), str(l.get("tipo", "")),
        str(l.get("finalidade", "")), str(l.get("observacao", ""))[:200],
        agora, str(usuario or "")[:60],
    ] for l in novos]
    try:
        _aba().append_rows(linhas, value_input_option="RAW")
    except Exception as e:
        return 0, repetidos, str(e)[:200]
    carregar.clear()
    return len(novos), repetidos, ""


def atualizar(id_lanc, campos, usuario=""):
    """Muda campos de UMA linha. (ok, mensagem). É o lápis da tela."""
    alvo = str(id_lanc or "").strip()
    if not alvo:
        return False, "Sem identificador."
    try:
        aba = _aba()
        registros = aba.get_all_records()
        pos = next((i for i, r in enumerate(registros)
                    if str(r.get("id", "")).strip() == alvo), None)
        if pos is None:
            return False, "Lançamento não encontrado."
        linha = dict(registros[pos])
        linha.update({k: v for k, v in (campos or {}).items() if k in COLUNAS})
        linha["atualizado_em"] = datetime.now(FUSO).strftime("%Y-%m-%d %H:%M")
        linha["atualizado_por"] = str(usuario or "")[:60]
        fim = chr(ord("A") + len(COLUNAS) - 1)
        aba.update([[linha.get(c, "") for c in COLUNAS]],
                   f"A{pos + 2}:{fim}{pos + 2}", value_input_option="RAW")
    except Exception as e:
        return False, str(e)[:200]
    carregar.clear()
    return True, "Alterado."


def apagar(ids):
    """Apaga as linhas destes ids. (quantos, mensagem).

    Reescreve a aba sem elas em vez de apagar linha por linha: cada
    `delete_rows` é uma chamada, e apagar vinte linhas do extrato daria vinte
    idas ao Google — com o índice mudando a cada uma, que é como se apaga a
    linha errada.
    """
    alvo = {str(i).strip() for i in (ids or []) if str(i).strip()}
    if not alvo:
        return 0, "Nada selecionado."
    try:
        aba = _aba()
        registros = aba.get_all_records()
        ficam = [r for r in registros if str(r.get("id", "")).strip() not in alvo]
        apagados = len(registros) - len(ficam)
        if not apagados:
            return 0, "Nenhuma dessas linhas está gravada."
        aba.clear()
        aba.update([COLUNAS] + [[r.get(c, "") for c in COLUNAS] for r in ficam],
                   value_input_option="RAW")
    except Exception as e:
        return 0, str(e)[:200]
    carregar.clear()
    return apagados, f"{apagados} lançamento(s) apagado(s)."


def do_mes(ano, mes, lista=None):
    """Os lançamentos de um mês. Ordenados por data."""
    alvo = f"{int(ano):04d}-{int(mes):02d}"
    fora = [l for l in (carregar() if lista is None else lista)
            if str(l.get("data", "")).startswith(alvo)]
    return sorted(fora, key=lambda l: str(l.get("data", "")))


def resumo_por_finalidade(lancamentos, so_saida=True):
    """{finalidade: total} — o que alimenta a meta de gastos.

    Transferência entre contas e as demais entradas que não são venda ficam de
    fora pela regra de `favorecidos`, e não por uma segunda lista escrita aqui.
    """
    import favorecidos as _fv
    fora = {}
    for l in (lancamentos or []):
        valor = float(l.get("valor") or 0)
        if so_saida and valor >= 0:
            continue
        fin = (l.get("finalidade") or "").strip().upper() or "SEM CLASSIFICAÇÃO"
        if so_saida and not _fv.consome_meta(fin):
            continue
        fora[fin] = fora.get(fin, 0.0) + abs(valor)
    return dict(sorted(fora.items(), key=lambda x: -x[1]))


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    L1 = {"data": date(2026, 8, 3), "descricao": "Pix enviado APEXIMP",
          "valor": -1303.0, "favorecido": "APEXIMP"}
    ok("o mesmo fato da a mesma identidade",
       identidade(L1, "inter") == identidade(dict(L1), "inter"))
    ok("data como texto ou como date dao a mesma identidade",
       identidade(L1, "inter")
       == identidade({**L1, "data": "2026-08-03"}, "inter"))
    ok("espaco a mais na descricao nao cria lancamento novo",
       identidade(L1, "inter")
       == identidade({**L1, "descricao": "Pix  enviado   APEXIMP"}, "inter"))
    ok("conta diferente e lancamento diferente",
       identidade(L1, "inter") != identidade(L1, "itau"))
    ok("centavo diferente e lancamento diferente",
       identidade(L1, "inter") != identidade({**L1, "valor": -1303.01}, "inter"))

    # Duas linhas identicas no mesmo dia existem: dois Pix de R$ 10 para o
    # mesmo nome. A segunda nao pode ser tomada pela primeira e descartada.
    IGUAIS = [L1, dict(L1), {**L1, "valor": -10.0}]
    _ci = com_identidade(IGUAIS, "inter")
    ok("linhas identicas recebem ids diferentes",
       len({x["id"] for x in _ci}) == 3)

    class _AbaFalsa:
        def __init__(self):
            self.linhas = [COLUNAS]

        def get_all_records(self):
            return [dict(zip(self.linhas[0], l)) for l in self.linhas[1:]]

        def clear(self):
            self.linhas = []

        def update(self, values, range_name=None, **kw):
            assert isinstance(values, list), "values vem PRIMEIRO no gspread 6"
            if range_name and range_name.startswith("A") and ":" in range_name:
                i = int(range_name.split(":")[0][1:]) - 1
                self.linhas[i] = [str(c) for c in values[0]]
            else:
                self.linhas = [[str(c) for c in v] for v in values]

        def append_row(self, linha, **kw):
            self.linhas.append([str(c) for c in linha])

        def append_rows(self, linhas, **kw):
            for l in linhas:
                self.append_row(l)

    _aba_falsa = _AbaFalsa()
    globals()["_aba"] = lambda: _aba_falsa

    carregar.clear()
    _n, _r, _e = gravar(IGUAIS, "inter", "leo")
    ok("gravou as tres", (_n, _r, _e) == (3, 0, ""))
    # O caso que este modulo existe para impedir.
    carregar.clear()
    _n2, _r2, _e2 = gravar(IGUAIS, "inter", "leo")
    ok("subir o MESMO extrato de novo nao dobra o mes",
       _n2 == 0 and _r2 == 3)

    carregar.clear()
    _id = carregar()[0]["id"]
    _ok_u, _ = atualizar(_id, {"finalidade": "MERCADORIA"}, "leo")
    carregar.clear()
    ok("o lapis altera a finalidade de uma linha so",
       _ok_u and carregar()[0]["finalidade"] == "MERCADORIA"
       and carregar()[1]["finalidade"] == "")
    ok("id inexistente nao altera nada",
       atualizar("nao-existe", {"finalidade": "X"})[0] is False)

    # Subir de novo NAO pode desfazer a correcao feita a mao.
    carregar.clear()
    gravar(IGUAIS, "inter", "leo")
    carregar.clear()
    ok("reenviar o extrato preserva a finalidade corrigida",
       carregar()[0]["finalidade"] == "MERCADORIA")

    carregar.clear()
    _qtd, _msg = apagar([_id])
    carregar.clear()
    ok("apagar tira so a linha pedida",
       _qtd == 1 and len(carregar()) == 2
       and _id not in {l["id"] for l in carregar()})
    ok("apagar nada nao derruba", apagar([])[0] == 0)

    carregar.clear()
    _mes = do_mes(2026, 8)
    ok("o mes filtra pela data", len(_mes) == 2)
    ok("outro mes vem vazio", do_mes(2026, 7) == [])

    _res = resumo_por_finalidade([
        {"valor": -100.0, "finalidade": "MERCADORIA"},
        {"valor": -50.0, "finalidade": "MERCADORIA"},
        {"valor": -170000.0, "finalidade": "TRANSFERENCIA ENTRE CONTAS"},
        {"valor": 2000.0, "finalidade": "SHOPEE"},
        {"valor": -30.0, "finalidade": ""},
    ])
    ok("o resumo soma a finalidade", _res.get("MERCADORIA") == 150.0)
    ok("transferencia entre contas nao entra na meta",
       "TRANSFERENCIA ENTRE CONTAS" not in _res)
    ok("entrada nao entra na meta de gastos", "SHOPEE" not in _res)
    ok("sem classificacao aparece, e nao desaparece",
       _res.get("SEM CLASSIFICAÇÃO") == 30.0)

    print("\nfalhas:", falhas)
