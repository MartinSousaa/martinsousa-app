"""queda_pontos.py — por que a pontuação mudou entre dois dias.

A PERGUNTA QUE ELE RESPONDE
---------------------------
28/09: *"o pessoal estava com 102% da meta coletiva na sexta e hoje caiu para
98%. Queda de 300 pontos, e a pontuação de 3 colaboradores reduziu também. Dá
para puxar o motivo?"*

O Studio lê o Trello AO VIVO: ele sabe quanto vale o quadro agora, e nada
sobre ontem. Um cartão arquivado simplesmente some do total — sem erro, sem
aviso, sem linha nenhuma dizendo que sumiu.

O Trello, esse, guarda o log. Toda mudança que mexe em ponto deixa uma ação
datada, e é dela que este módulo monta o extrato.

O QUE MEXE EM PONTO, E SÓ ISSO
------------------------------
    createCard em PENALIDADES      tira pontos de quem está no cartão
    updateCard com closed: true    o cartão foi ARQUIVADO — os pontos somem
    updateCard com listBefore/After  mudou de lista; pode entrar ou sair da conta
    updateCustomFieldItem          o campo PONTOS foi alterado
    addMemberToCard                alguém passou a receber o ponto
    removeMemberFromCard           alguém deixou de receber

Movimento de etiqueta, comentário, anexo e checklist não mexem em ponto, e
ficam de fora — extrato com ruído não se lê.

ELE NÃO ADIVINHA VALOR
----------------------
Quando o log não diz quanto o cartão valia (um arquivamento não carrega o
campo PONTOS), o valor sai vazio e a linha diz o que houve. Inventar o número
seria pior que deixá-lo em branco: daria a impressão de conta fechada.
"""

from datetime import datetime, timezone

# As ações do Trello que podem mudar um ponto. Os nomes saem do que este
# repositório já usa em `placar_core` — não de memória.
TIPOS = ("createCard", "updateCard", "updateCustomFieldItem",
         "addMemberToCard", "removeMemberFromCard", "deleteCard")

# O filtro para a consulta ao Trello, no formato que a API espera.
FILTRO = ",".join(TIPOS)


def _quando(acao):
    """A data da ação, com fuso. None quando o Trello não mandou data."""
    t = str((acao or {}).get("date") or "")
    if not t:
        return None
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return None


def _entre(acao, inicio, fim):
    """A ação aconteceu na janela? `inicio` e `fim` são datas com fuso."""
    d = _quando(acao)
    return bool(d and inicio <= d <= fim)


def _membros(acao):
    """Os nomes de quem a ação cita, quando ela cita alguém."""
    d = (acao or {}).get("data") or {}
    nomes = []
    for chave in ("member", "idMember"):
        v = d.get(chave)
        if isinstance(v, dict) and v.get("username"):
            nomes.append(v["username"])
        elif isinstance(v, str) and v:
            nomes.append(v)
    m = (acao or {}).get("member") or {}
    if m.get("username"):
        nomes.append(m["username"])
    return sorted(set(nomes))


def classificar(acao, listas_de_penalidade=("PENALIDADES",)):
    """O que esta ação fez com a pontuação. None quando não fez nada.

    Devolve {"o_que", "detalhe"} — o texto que a tela mostra. Quem soma o
    efeito em pontos é `mapear`, que tem o valor do cartão em mãos.
    """
    tipo = str((acao or {}).get("type") or "")
    d = (acao or {}).get("data") or {}
    card = d.get("card") or {}
    lista_agora = str((d.get("list") or {}).get("name") or "").upper()
    penal = {str(x).upper() for x in listas_de_penalidade}

    if tipo == "deleteCard":
        return {"o_que": "cartão excluído",
                "detalhe": "os pontos dele saíram do total"}

    if tipo == "createCard":
        if lista_agora in penal:
            return {"o_que": "penalidade criada",
                    "detalhe": f"na lista {lista_agora}"}
        return None

    if tipo == "updateCard":
        # ARQUIVAR é `closed` indo de false para true. O cartão continua
        # existindo no Trello e some do quadro — e do total.
        velho = d.get("old") or {}
        if "closed" in velho:
            if card.get("closed"):
                return {"o_que": "cartão arquivado",
                        "detalhe": "os pontos dele saíram do total"}
            return {"o_que": "cartão desarquivado",
                    "detalhe": "os pontos dele voltaram ao total"}
        antes = str((d.get("listBefore") or {}).get("name") or "")
        depois = str((d.get("listAfter") or {}).get("name") or "")
        if antes or depois:
            o_que = ("entrou em penalidade" if depois.upper() in penal
                     else "saiu de penalidade" if antes.upper() in penal
                     else "mudou de lista")
            return {"o_que": o_que, "detalhe": f"{antes or '?'} → {depois or '?'}"}
        return None

    if tipo == "updateCustomFieldItem":
        nome = str(((d.get("customField") or {}).get("name") or "")).upper()
        if "PONTO" not in nome:
            return None
        valor = ((d.get("customFieldItem") or {}).get("value") or {})
        novo = valor.get("number") or valor.get("text") or ""
        return {"o_que": "campo PONTOS alterado",
                "detalhe": f"passou a valer {novo}" if novo else "valor apagado"}

    if tipo in ("addMemberToCard", "removeMemberFromCard"):
        entrou = tipo == "addMemberToCard"
        quem = ", ".join(_membros(acao)) or "alguém"
        return {"o_que": "membro entrou no cartão" if entrou
                else "membro saiu do cartão",
                "detalhe": quem}
    return None


def mapear(acoes, inicio, fim, pontos_por_card=None,
           listas_de_penalidade=("PENALIDADES",)):
    """O extrato do que mexeu em ponto na janela. Lista de dicionários.

    `pontos_por_card` é {id_do_cartão: valor} lido do quadro de HOJE. Cartão
    arquivado ou excluído não está lá — e é por isso que `valor` pode vir
    vazio. Vazio é honesto; número inventado, não.

    A ordem é cronológica: quem lê quer ver a sequência do que aconteceu.
    """
    pontos = pontos_por_card or {}
    fora = []
    for ac in (acoes or []):
        if not _entre(ac, inicio, fim):
            continue
        o = classificar(ac, listas_de_penalidade)
        if not o:
            continue
        card = (ac.get("data") or {}).get("card") or {}
        fora.append({
            "quando": _quando(ac),
            "cartao": card.get("name") or "(sem nome)",
            "id": card.get("id") or "",
            "o_que": o["o_que"],
            "detalhe": o["detalhe"],
            "quem": ", ".join(_membros(ac)),
            "valor": pontos.get(card.get("id")),
        })
    return sorted(fora, key=lambda x: (x["quando"] or datetime.min.replace(
        tzinfo=timezone.utc)))


def resumo(extrato):
    """Uma linha por tipo de mudança, da mais frequente para a menos."""
    contas = {}
    for e in (extrato or []):
        contas[e["o_que"]] = contas.get(e["o_que"], 0) + 1
    return sorted(contas.items(), key=lambda x: -x[1])


# ── Conferência ──────────────────────────────────────────────────────────────
# `python3 queda_pontos.py`. Tudo aqui é função pura sobre o JSON do Trello —
# as ações de exemplo têm a forma que a API devolve, e é essa forma que o
# módulo precisa acertar.
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    SEX = datetime(2026, 9, 25, 18, 0, tzinfo=timezone.utc)
    SEG = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)

    def _ac(tipo, quando, data, membro=None):
        a = {"type": tipo, "date": quando, "data": data}
        if membro:
            a["member"] = {"username": membro}
        return a

    # ── O CARTAO ARQUIVADO, que e o ponto cego ──────────────────────────
    #
    # O Studio le os cartoes ATUAIS: arquivar faz o cartao sumir do total
    # sem erro, sem aviso e sem linha nenhuma dizendo que sumiu. No log do
    # Trello ele continua la.
    _arq = _ac("updateCard", "2026-09-26T14:00:00.000Z",
               {"card": {"id": "c1", "name": "Vídeo caneca", "closed": True},
                "old": {"closed": False}})
    _c = classificar(_arq)
    ok("arquivar e reconhecido", _c and _c["o_que"] == "cartão arquivado")
    ok("e a tela diz o efeito", "saíram do total" in _c["detalhe"])
    _des = _ac("updateCard", "2026-09-26T15:00:00.000Z",
               {"card": {"id": "c1", "name": "Vídeo caneca", "closed": False},
                "old": {"closed": True}})
    ok("desarquivar tambem, e com o efeito oposto",
       classificar(_des)["o_que"] == "cartão desarquivado")

    # ── A DATA DA ACAO, que decide se ela entra na janela ───────────────
    ok("a data do Trello vira data com fuso",
       _quando({"date": "2026-09-26T14:00:00.000Z"}).year == 2026)
    ok("e ela sabe a hora", _quando({"date": "2026-09-26T14:00:00.000Z"}).hour == 14)
    ok("acao sem data devolve None", _quando({}) is None and _quando(None) is None)
    ok("data que nao e data devolve None", _quando({"date": "ontem"}) is None)
    # SEM FUSO A COMPARACAO EXPLODE: o container roda em UTC e comparar data
    # com e sem fuso levanta TypeError — que so apareceria ao clicar.
    ok("a data volta com fuso, senao a comparacao da janela explode",
       _quando({"date": "2026-09-26T14:00:00.000Z"}).tzinfo is not None)

    # ── A PENALIDADE, que explica queda no coletivo E em pessoas ────────
    _pen = _ac("createCard", "2026-09-26T09:00:00.000Z",
               {"card": {"id": "c2", "name": "Atraso na entrega"},
                "list": {"name": "PENALIDADES"}})
    ok("penalidade criada e reconhecida",
       classificar(_pen)["o_que"] == "penalidade criada")
    # CARTAO NOVO EM LISTA COMUM NAO E EVENTO: todo dia nascem cartoes, e
    # lista-los encheria o extrato de ruido.
    ok("cartao novo em lista comum nao entra no extrato",
       classificar(_ac("createCard", "2026-09-26T09:00:00.000Z",
                       {"card": {"id": "c9", "name": "Arte nova"},
                        "list": {"name": "PENDENTE"}})) is None)

    # ── MUDANCA DE LISTA, com os dois sentidos nomeados ─────────────────
    _mv = _ac("updateCard", "2026-09-27T10:00:00.000Z",
              {"card": {"id": "c3", "name": "Álbum 30x30"},
               "listBefore": {"name": "CONCLUÍDO"},
               "listAfter": {"name": "PENALIDADES"}})
    ok("entrar em penalidade tem nome proprio",
       classificar(_mv)["o_que"] == "entrou em penalidade")
    _mv2 = _ac("updateCard", "2026-09-27T11:00:00.000Z",
               {"card": {"id": "c3", "name": "Álbum 30x30"},
                "listBefore": {"name": "PENALIDADES"},
                "listAfter": {"name": "CONCLUÍDO"}})
    ok("sair tambem", classificar(_mv2)["o_que"] == "saiu de penalidade")
    ok("e o caminho e mostrado", "→" in classificar(_mv2)["detalhe"])

    # ── O CAMPO PONTOS ──────────────────────────────────────────────────
    _cf = _ac("updateCustomFieldItem", "2026-09-27T12:00:00.000Z",
              {"card": {"id": "c4", "name": "Triagem caneca"},
               "customField": {"name": "PONTOS"},
               "customFieldItem": {"value": {"number": "40"}}})
    ok("alteracao do campo PONTOS entra",
       classificar(_cf)["o_que"] == "campo PONTOS alterado")
    ok("com o novo valor escrito", "40" in classificar(_cf)["detalhe"])
    # OUTRO CAMPO CUSTOMIZADO NAO MEXE EM PONTO.
    ok("outro campo customizado fica de fora",
       classificar(_ac("updateCustomFieldItem", "2026-09-27T12:00:00.000Z",
                       {"card": {"id": "c4", "name": "x"},
                        "customField": {"name": "TEMPO ACUMULADO"},
                        "customFieldItem": {"value": {"number": "90"}}})) is None)

    # ── MEMBRO ENTRANDO E SAINDO ────────────────────────────────────────
    _rm = _ac("removeMemberFromCard", "2026-09-27T13:00:00.000Z",
              {"card": {"id": "c5", "name": "Foto produto"},
               "member": {"username": "myrella"}})
    ok("membro que sai do cartao entra no extrato",
       classificar(_rm)["o_que"] == "membro saiu do cartão")
    ok("e o nome dele aparece", "myrella" in classificar(_rm)["detalhe"])

    # ── O QUE NAO MEXE EM PONTO NAO POLUI O EXTRATO ─────────────────────
    for _t, _d in (("addLabelToCard", {"card": {"id": "c6", "name": "x"}}),
                   ("commentCard", {"card": {"id": "c6", "name": "x"}}),
                   ("addAttachmentToCard", {"card": {"id": "c6", "name": "x"}})):
        ok(f"{_t} fica de fora", classificar(_ac(_t, "2026-09-26T10:00:00.000Z", _d)) is None)

    # ── A JANELA ────────────────────────────────────────────────────────
    _antes = _ac("updateCard", "2026-09-24T10:00:00.000Z",
                 {"card": {"id": "c7", "name": "Antigo", "closed": True},
                  "old": {"closed": False}})
    _depois = _ac("updateCard", "2026-09-29T10:00:00.000Z",
                  {"card": {"id": "c8", "name": "Futuro", "closed": True},
                   "old": {"closed": False}})
    _ext = mapear([_antes, _arq, _pen, _mv, _cf, _rm, _depois], SEX, SEG,
                  {"c3": 80, "c4": 40, "c5": 25})
    ok("o que aconteceu antes da sexta fica fora",
       not any(e["cartao"] == "Antigo" for e in _ext))
    ok("e o que aconteceu depois de hoje tambem",
       not any(e["cartao"] == "Futuro" for e in _ext))
    ok("os cinco da janela entram", len(_ext) == 5)

    # ORDEM CRONOLOGICA: quem le quer a sequencia do que aconteceu.
    ok("o extrato sai em ordem de tempo",
       [e["cartao"] for e in _ext][:2] == ["Atraso na entrega", "Vídeo caneca"])

    # O VALOR VEM DO QUADRO DE HOJE — e cartao arquivado NAO esta la.
    _arquivado = next(e for e in _ext if e["o_que"] == "cartão arquivado")
    ok("cartao arquivado sai sem valor, e nao com um valor inventado",
       _arquivado["valor"] is None)
    _com_valor = next(e for e in _ext if e["id"] == "c3")
    ok("cartao que ainda existe traz o valor dele", _com_valor["valor"] == 80)

    # ── BORDAS ──────────────────────────────────────────────────────────
    ok("lista vazia nao quebra", mapear([], SEX, SEG) == [])
    ok("None nao quebra", mapear(None, SEX, SEG) == [])
    ok("acao sem data nao entra",
       mapear([{"type": "deleteCard", "data": {"card": {"name": "x"}}}],
              SEX, SEG) == [])
    ok("data torta nao derruba",
       mapear([_ac("deleteCard", "ontem", {"card": {"name": "x"}})],
              SEX, SEG) == [])

    # O RESUMO conta por tipo, do mais frequente para o menos.
    _r = resumo(_ext)
    ok("o resumo conta cinco tipos", len(_r) == 5)
    ok("e cada um aparece uma vez", all(n == 1 for _t2, n in _r))
    ok("resumo de extrato vazio e vazio", resumo([]) == [] and resumo(None) == [])

    # O FILTRO que vai ao Trello tem de citar arquivamento e penalidade.
    ok("o filtro pede updateCard (arquivar e mover)", "updateCard" in FILTRO)
    ok("e createCard (penalidade nova)", "createCard" in FILTRO)
    ok("e o campo customizado", "updateCustomFieldItem" in FILTRO)

    print("\nfalhas:", falhas)
