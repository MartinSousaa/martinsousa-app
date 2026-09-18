"""comprovantes.py — o comprovante CONFERE o extrato, e nunca soma junto.

A REGRA, DITA PELO DONO
-----------------------
    "o que vier de comprovante deverá estar no extrato"

Dela sai tudo o que este módulo faz, e principalmente o que ele NÃO faz:

    quem chega primeiro conta, e o segundo não soma de novo.
    finalidade   -> vem do comprovante, e é aplicada na linha do extrato.
    sem par      -> conta como gasto E fica na lista de conferência.

QUEM CHEGA PRIMEIRO CONTA
-------------------------
O comprovante quase sempre chega antes: é enviado no dia do pagamento, e o
extrato só sobe no fim do mês. Esperar o extrato para contar o gasto deixaria o
mês inteiro parecendo mais barato do que é, justamente enquanto as decisões de
compra estão sendo tomadas.

Então o comprovante conta desde o minuto em que chega. Quando o extrato sobe e
a linha dele aparece, o par se forma e o comprovante PARA de contar — quem
conta passa a ser o extrato, que é o dado conferido. O total não muda no
caminho: o mesmo pagamento nunca é somado duas vezes.

É a mesma regra do `previsto`, e a razão é a mesma: dois lados do mesmo
pagamento, um só na conta.

O QUE ELE GANHA, ENTÃO
----------------------
O extrato diz PARA QUEM o dinheiro foi, e quase nada sobre o quê. Em cheque e
em fatura de cartão ele não diz nem isso: "CH COMPENSADO 001 000504" e "DEB.AUT.
FATURA" são formas de pagar, não compras. O comprovante preenche esse buraco —
e é por isso que ele vale mesmo sem mexer em nenhum total.

O SEGUNDO ACHADO, QUE NINGUÉM PEDIU E É DE GRAÇA
------------------------------------------------
Comprovante sem linha no extrato significa uma de quatro coisas, e todas
merecem ser olhadas: saiu de outra conta, o valor digitado está errado, o
pagamento não compensou, ou alguém mandou um comprovante que não corresponde a
nada. O sistema não decide qual é — ele mostra a lista.
"""

import hashlib
from datetime import date, datetime, timedelta, timezone

import streamlit as st

ABA_NOME = "comprovantes"
COLUNAS = ["id", "recebido_em", "origem", "quem_enviou", "valor",
           "data_pagamento", "favorecido", "finalidade", "observacao",
           "lancamento_id", "conferido_em", "arquivo"]

FUSO = timezone(timedelta(hours=-3))

# Quantos dias o pagamento pode demorar para aparecer no extrato.
#
# Pix cai na hora; boleto e cheque não. Três dias cobrem o fim de semana, que é
# o caso comum: pago na sexta, compensa na segunda. Uma janela maior começaria
# a casar comprovante de um pagamento com a linha de OUTRO de valor igual — e
# um casamento errado é pior que nenhum, porque ninguém confere de novo.
TOLERANCIA_DIAS = 3


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


def texto_data(v):
    """Qualquer data virando "AAAA-MM-DD". "" quando não dá para ler."""
    a, m, d = (getattr(v, "year", None), getattr(v, "month", None),
               getattr(v, "day", None))
    if all(isinstance(x, int) for x in (a, m, d)):
        return f"{a:04d}-{m:02d}-{d:02d}"
    t = str(v or "").strip()[:10]
    if not t or t.lower() in ("nat", "nan", "none"):
        return ""
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(t, f).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def _dia(texto):
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def identidade(comp):
    """A digital do comprovante: valor + data + favorecido.

    Serve para o mesmo comprovante reenviado no WhatsApp — o que vai
    acontecer — não virar dois registros.
    """
    bruto = "|".join([
        f"{_num(comp.get('valor')):.2f}",
        texto_data(comp.get("data_pagamento")),
        " ".join(str(comp.get("favorecido") or "").upper().split()),
    ])
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()[:16]


def normalizar(comp, origem="upload", quem=""):
    fora = {
        "recebido_em": datetime.now(FUSO).strftime("%Y-%m-%d %H:%M"),
        "origem": str(origem or "upload")[:20],
        "quem_enviou": str(quem or "")[:60],
        "valor": round(abs(_num(comp.get("valor"))), 2),
        "data_pagamento": texto_data(comp.get("data_pagamento")),
        "favorecido": str(comp.get("favorecido") or "").strip()[:80],
        "finalidade": str(comp.get("finalidade") or "").strip().upper()[:40],
        "observacao": str(comp.get("observacao") or "").strip()[:200],
        "lancamento_id": str(comp.get("lancamento_id") or "").strip(),
        "conferido_em": str(comp.get("conferido_em") or "").strip(),
        "arquivo": str(comp.get("arquivo") or "").strip()[:200],
    }
    fora["id"] = identidade(fora)
    return fora


def casar(comprovantes, lancamentos, tolerancia_dias=TOLERANCIA_DIAS):
    """Liga cada comprovante à linha do extrato que é ele. (pares, sem_par).

    O casamento é por VALOR e DATA, nesta ordem de preferência:
      1. mesma data, mesmo valor
      2. valor igual dentro da tolerância, a data mais próxima

    O nome NÃO entra: o extrato escreve "Cp :60701190-APEXIMP" e o comprovante
    diz "Apeximp Comercio", e exigir que batessem faria o casamento falhar
    justamente onde ele é mais útil.

    Uma linha do extrato só casa UMA vez. Dois pagamentos de R$ 1.000 no mesmo
    dia são duas linhas e dois comprovantes — deixar um comprovante casar com a
    linha já usada criaria um par falso e deixaria o outro órfão, que é o pior
    dos dois mundos: um erro que se disfarça de conferência feita.
    """
    saidas = []
    for l in (lancamentos or []):
        v = _num(l.get("valor"))
        if v >= 0:                      # comprovante de pagamento é saída
            continue
        saidas.append({"id": l.get("id"), "valor": round(abs(v), 2),
                       "data": texto_data(l.get("data")),
                       "favorecido": l.get("favorecido", ""),
                       "descricao": l.get("descricao", ""),
                       "finalidade": l.get("finalidade", "")})

    usados, pares, sem_par = set(), [], []
    # Data exata primeiro, para todos, ANTES de qualquer aproximação: senão um
    # comprovante aproximado toma a linha exata de outro.
    pendentes = []
    for c in (comprovantes or []):
        alvo_v = round(abs(_num(c.get("valor"))), 2)
        alvo_d = texto_data(c.get("data_pagamento"))
        exato = next((s for s in saidas
                      if s["id"] not in usados
                      and s["valor"] == alvo_v and s["data"] == alvo_d), None)
        if exato and alvo_v:
            usados.add(exato["id"])
            pares.append({"comprovante": c, "lancamento": exato,
                          "dias": 0, "exato": True})
        else:
            pendentes.append((c, alvo_v, alvo_d))

    for c, alvo_v, alvo_d in pendentes:
        d0 = _dia(alvo_d)
        candidatos = []
        for s in saidas:
            if s["id"] in usados or s["valor"] != alvo_v or not alvo_v:
                continue
            d1 = _dia(s["data"])
            if d0 and d1:
                dist = abs((d1 - d0).days)
                if dist <= tolerancia_dias:
                    candidatos.append((dist, s))
        if candidatos:
            candidatos.sort(key=lambda x: x[0])
            dist, s = candidatos[0]
            usados.add(s["id"])
            pares.append({"comprovante": c, "lancamento": s,
                          "dias": dist, "exato": False})
        else:
            sem_par.append(c)
    return pares, sem_par


def finalidades_a_aplicar(pares):
    """[(lancamento_id, finalidade)] — o que o comprovante ensina ao extrato.

    Só onde o comprovante tem finalidade e a linha do extrato ainda não tem, ou
    tem outra. O extrato manda no VALOR; o comprovante manda no SIGNIFICADO —
    é ele que sabe o que aquele cheque pagou.
    """
    fora = []
    for p in (pares or []):
        fin = str(p["comprovante"].get("finalidade") or "").strip().upper()
        if not fin:
            continue
        atual = str(p["lancamento"].get("finalidade") or "").strip().upper()
        if fin != atual:
            fora.append((p["lancamento"]["id"], fin))
    return fora


def a_contar(comprovantes, lancamentos, tolerancia_dias=TOLERANCIA_DIAS):
    """Os comprovantes que ainda contam como gasto. (lista, pares).

    São os SEM par: o pagamento existe, o dinheiro saiu, e o extrato ainda não
    chegou. Assim que ele chega, o par se forma e o comprovante sai desta lista
    sozinho — sem ninguém dar baixa em nada.
    """
    pares, sem_par = casar(comprovantes, lancamentos, tolerancia_dias)
    return sem_par, pares


def por_finalidade(sem_par):
    """{finalidade: total} dos comprovantes que ainda contam.

    Sai no mesmo formato de `lancamentos.resumo_por_finalidade`, para somar
    com ele sem tradução no meio — tradução é onde os dois começam a discordar.
    """
    fora = {}
    for c in (sem_par or []):
        fin = (str(c.get("finalidade") or "").strip().upper()
               or "SEM CLASSIFICAÇÃO")
        fora[fin] = round(fora.get(fin, 0.0) + abs(_num(c.get("valor"))), 2)
    return dict(sorted(fora.items(), key=lambda x: -x[1]))


def resumo(pares, sem_par):
    """Os três números da tela de conferência."""
    return {
        "conferidos": len(pares),
        "aproximados": sum(1 for p in pares if not p["exato"]),
        "sem_extrato": len(sem_par),
        # O que este número É: o gasto que só o comprovante conhece ainda. Ele
        # encolhe sozinho conforme os extratos sobem — e o que sobrar depois do
        # extrato do mês fechado é a lista para olhar de perto.
        "valor_sem_extrato": round(sum(abs(_num(c.get("valor")))
                                       for c in (sem_par or [])), 2),
    }


# ── Planilha ─────────────────────────────────────────────────────────────────

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
    try:
        registros = _aba().get_all_records()
    except Exception:
        return []
    return [{c: r.get(c, "") for c in COLUNAS}
            for r in registros if str(r.get("id", "") or "").strip()]


def gravar(novos, origem="upload", quem=""):
    """Acrescenta o que ainda não existe. (novos, repetidos, erro)."""
    try:
        aba = _aba()
        ja = {str(r.get("id", "")).strip()
              for r in aba.get_all_records() if str(r.get("id", "")).strip()}
        linhas, vistos, repetidos = [], set(), 0
        for c in (novos or []):
            n = normalizar(c, origem, quem)
            if not n["valor"] or not n["data_pagamento"]:
                repetidos += 1          # sem valor ou sem data não confere nada
                continue
            if n["id"] in ja or n["id"] in vistos:
                repetidos += 1
                continue
            vistos.add(n["id"])
            linhas.append([n.get(col, "") for col in COLUNAS])
        if linhas:
            aba.append_rows(linhas, value_input_option="RAW")
    except Exception as e:
        return 0, 0, str(e)[:200]
    carregar.clear()
    return len(linhas), repetidos, ""


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    ok("data brasileira vira AAAA-MM-DD", texto_data("04/09/2026") == "2026-09-04")
    ok("date tambem", texto_data(date(2026, 9, 4)) == "2026-09-04")
    ok("lixo nao vira data", texto_data("--") == "" and texto_data(None) == "")
    ok("valor brasileiro e lido", _num("1.409,89") == 1409.89)

    EXTRATO = [
        {"id": "L1", "data": "2026-09-04", "valor": -1409.89,
         "favorecido": "APEXIMP", "finalidade": "MERCADORIA"},
        {"id": "L2", "data": "2026-09-08", "valor": -600.00,
         "favorecido": "Vanda Maria Martinez", "finalidade": ""},
        {"id": "L3", "data": "2026-09-14", "valor": -2500.00,
         "favorecido": "CH COMPENSADO 001 000504", "finalidade": "CHEQUES"},
        {"id": "L4", "data": "2026-09-14", "valor": 4006.92,
         "favorecido": "MAREE", "finalidade": "SHOPEE"},
    ]

    # 1. O caso simples: mesmo valor, mesmo dia.
    _p, _s = casar([{"valor": 1409.89, "data_pagamento": "2026-09-04",
                     "favorecido": "Apeximp Comercio"}], EXTRATO)
    ok("casa por valor e data, mesmo com o nome escrito diferente",
       len(_p) == 1 and _p[0]["lancamento"]["id"] == "L1" and _p[0]["exato"])
    ok("e nada fica sem par", _s == [])

    # 2. Pago na sexta, compensou na segunda.
    _p, _s = casar([{"valor": 2500.00, "data_pagamento": "2026-09-11",
                     "favorecido": "Fornecedor X", "finalidade": "MERCADORIA"}],
                   EXTRATO)
    ok("cheque pago antes casa dentro da tolerancia",
       len(_p) == 1 and _p[0]["lancamento"]["id"] == "L3" and _p[0]["dias"] == 3)
    ok("e fica marcado como aproximado", _p[0]["exato"] is False)

    # 3. Fora da tolerancia NAO casa — casamento errado e pior que nenhum.
    _p, _s = casar([{"valor": 2500.00, "data_pagamento": "2026-09-01"}], EXTRATO)
    ok("dez dias de distancia nao casa", _p == [] and len(_s) == 1)

    # 4. A REGRA DO DONO: o que veio de comprovante tem de estar no extrato.
    _p, _s = casar([{"valor": 999.00, "data_pagamento": "2026-09-05",
                     "favorecido": "Alguem"}], EXTRATO)
    ok("comprovante sem linha no extrato vira ACHADO, e nao erro",
       _p == [] and len(_s) == 1 and _s[0]["valor"] == 999.00)

    # 5. Entrada nunca casa com comprovante de pagamento.
    _p, _s = casar([{"valor": 4006.92, "data_pagamento": "2026-09-14"}], EXTRATO)
    ok("entrada no extrato nao e pagamento", _p == [] and len(_s) == 1)

    # 6. Dois pagamentos iguais no mesmo dia sao DOIS pares, e nao um duplo.
    DUPLO = [
        {"id": "A", "data": "2026-09-10", "valor": -1000.0, "favorecido": "X"},
        {"id": "B", "data": "2026-09-10", "valor": -1000.0, "favorecido": "Y"},
    ]
    _p, _s = casar([{"valor": 1000.0, "data_pagamento": "2026-09-10"},
                    {"valor": 1000.0, "data_pagamento": "2026-09-10"}], DUPLO)
    ok("cada linha do extrato casa uma vez so",
       len(_p) == 2 and {x["lancamento"]["id"] for x in _p} == {"A", "B"})

    # E o terceiro comprovante igual fica sem par, em vez de roubar uma linha.
    _p, _s = casar([{"valor": 1000.0, "data_pagamento": "2026-09-10"}] * 3, DUPLO)
    ok("o terceiro fica sem par", len(_p) == 2 and len(_s) == 1)

    # 7. A data EXATA tem preferencia sobre a aproximada de outro comprovante.
    PREF = [{"id": "E", "data": "2026-09-10", "valor": -500.0}]
    _p, _s = casar([{"valor": 500.0, "data_pagamento": "2026-09-08"},
                    {"valor": 500.0, "data_pagamento": "2026-09-10"}], PREF)
    ok("quem tem a data exata leva a linha",
       len(_p) == 1 and _p[0]["comprovante"]["data_pagamento"] == "2026-09-10")

    # 8. O que o comprovante ENSINA ao extrato.
    _p, _s = casar([{"valor": 2500.00, "data_pagamento": "2026-09-14",
                     "finalidade": "mercadoria"}], EXTRATO)
    ok("o cheque aprende o que pagou",
       finalidades_a_aplicar(_p) == [("L3", "MERCADORIA")])
    _p2, _ = casar([{"valor": 1409.89, "data_pagamento": "2026-09-04",
                     "finalidade": "MERCADORIA"}], EXTRATO)
    ok("e nao reescreve o que ja estava igual", finalidades_a_aplicar(_p2) == [])
    _p3, _ = casar([{"valor": 600.00, "data_pagamento": "2026-09-08"}], EXTRATO)
    ok("comprovante sem finalidade nao ensina nada",
       finalidades_a_aplicar(_p3) == [])

    # 9. O mesmo comprovante reenviado no WhatsApp e UM registro.
    _c = {"valor": 1409.89, "data_pagamento": "04/09/2026", "favorecido": "Apeximp"}
    ok("reenvio do mesmo comprovante tem o mesmo id",
       normalizar(_c)["id"] == normalizar(dict(_c))["id"])
    ok("data escrita de outro jeito nao cria outro id",
       normalizar(_c)["id"]
       == normalizar({**_c, "data_pagamento": "2026-09-04"})["id"])
    ok("valor diferente e outro comprovante",
       normalizar({**_c, "valor": 10})["id"] != normalizar(_c)["id"])

    # 10. O resumo da tela.
    _p, _s = casar([{"valor": 1409.89, "data_pagamento": "2026-09-04"},
                    {"valor": 2500.00, "data_pagamento": "2026-09-11"},
                    {"valor": 777.00, "data_pagamento": "2026-09-05"}], EXTRATO)
    _r = resumo(_p, _s)
    ok("o resumo conta conferidos, aproximados e orfaos",
       _r == {"conferidos": 2, "aproximados": 1, "sem_extrato": 1,
              "valor_sem_extrato": 777.00})

    # 11. QUEM CHEGA PRIMEIRO CONTA — e o segundo nao soma de novo.
    COMPS = [
        {"valor": 1409.89, "data_pagamento": "2026-09-04",
         "finalidade": "MERCADORIA"},                    # ja esta no extrato
        {"valor": 3100.00, "data_pagamento": "2026-09-20",
         "finalidade": "MERCADORIA"},                    # extrato ainda nao veio
        {"valor": 450.00, "data_pagamento": "2026-09-21",
         "finalidade": "CUSTO FIXO"},
    ]
    _falta, _pares = a_contar(COMPS, EXTRATO)
    ok("comprovante sem extrato ainda conta", len(_falta) == 2)
    ok("e o que ja esta no extrato parou de contar",
       all(abs(_num(c["valor"])) != 1409.89 for c in _falta))
    ok("o total a contar e so o que o extrato nao viu",
       round(sum(abs(_num(c["valor"])) for c in _falta), 2) == 3550.00)
    ok("e ele vem por finalidade, no mesmo formato do extrato",
       por_finalidade(_falta) == {"MERCADORIA": 3100.00, "CUSTO FIXO": 450.00})

    # Quando o extrato daquele pagamento sobe, o comprovante sai da conta
    # SOZINHO — ninguem da baixa em nada.
    EXTRATO_DEPOIS = EXTRATO + [{"id": "L9", "data": "2026-09-20",
                                 "valor": -3100.00, "favorecido": "APEXIMP"}]
    _falta2, _ = a_contar(COMPS, EXTRATO_DEPOIS)
    ok("chegou o extrato, o comprovante para de contar",
       len(_falta2) == 1 and por_finalidade(_falta2) == {"CUSTO FIXO": 450.00})

    ok("comprovante sem finalidade nao vira gasto sem nome",
       por_finalidade([{"valor": 10}]) == {"SEM CLASSIFICAÇÃO": 10.0})

    ok("lista vazia nao derruba", casar([], []) == ([], []) and
       casar(None, None) == ([], []))

    print("\nfalhas:", falhas)
