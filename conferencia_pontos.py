"""conferencia_pontos.py — a contagem CRUA do Trello, ao lado do que o Studio diz.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
O dono, 29/09: *"o pessoal continua reclamando que a pontuação deles no painel
continua caindo, evidenciando inclusive com imagens"*.

O Painel mostra um número. Ninguém consegue conferir esse número sem refazer a
conta à mão, cartão por cartão, no Trello — e é isso que a equipe vem fazendo,
com print de tela. Enquanto a conferência custar uma tarde, a discussão continua
sendo "o sistema está errado" contra "o sistema está certo", sem ninguém poder
provar nada.

Aqui a conta é feita DUAS vezes, a partir dos MESMOS cartões:

  CRUA     todo cartão concluído com pontuação, somado sem nenhuma regra de mês
  SISTEMA  o que `placar._processar` devolveu, que é o que a tela mostra

E a diferença vem NOMEADA: cada cartão que a conta crua tem e o sistema não,
com o MOTIVO. Não é opinião — o motivo sai das mesmas condições que
`placar.py:660-692` aplica, lidas uma a uma.

O MOTIVO QUE IMPORTA, E POR QUE ELE É SILENCIOSO
-------------------------------------------------
A pontuação só conta no MÊS DA CONCLUSÃO, e esse mês vem da AÇÃO do Trello que
virou `dueComplete` para verdadeiro (`placar_core.py:2224`).

Quando essa ação não está na janela de histórico lida, `_mes_card` cai para a
última atividade do cartão — e se essa atividade for recente, devolve `None`
(`placar_core.py:2246`). Mês indeterminado não bate com mês nenhum, então o
cartão **sai da soma**.

A janela é de 120 dias no teto de 5 páginas × 1000 ações = 5.000
(`placar_core.py:604,654`). Board movimentado gera mais ações; as 5.000 cobrem
cada vez menos dias; mais cartões perdem a data de conclusão. **A perda é
progressiva** — e é exatamente o formato da queixa.

O código JÁ SABE quando isso acontece: `_buscar_acoes_board` marca
`diag["truncado"] = True` (`placar_core.py:698`). Nenhuma tela lia essa marca.
"""

MOTIVOS = {
    "mes_desconhecido": (
        "conclusão mais antiga que o histórico lido — o Studio não sabe em que "
        "mês este cartão foi concluído, então ele não entra em mês nenhum"),
    "outro_mes": "concluído em outro mês",
    "sem_pontuacao": "o campo de pontuação está vazio",
    "coluna_sem_pontuacao": "a coluna não pontua",
    "nao_concluido": "não está marcado como concluído",
}


def _pontos_do_card(card, id_pontos):
    """O número do campo de pontuação, ou None. Nunca levanta."""
    for it in (card.get("customFieldItems") or []):
        if it.get("idCustomField") != id_pontos:
            continue
        v = (it.get("value") or {}).get("number")
        if v in (None, ""):
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    return None


def contagem_crua(cards, listas, membros_map, id_pontos, membros_ativos,
                  listas_sem_pontuacao):
    """A soma sem regra de mês: todo concluído com pontuação, e de quem é.

    É de propósito que ela ignore o mês. O mês é justamente a regra sob
    suspeita: comparar o sistema com uma conta que aplica a MESMA regra não
    responde nada.
    """
    total = 0.0
    por_membro = {u: 0.0 for u in membros_ativos}
    qtd = {"cards": len(cards), "concluidos": 0, "com_pontos": 0,
           "com_membro": 0, "concluido_sem_membro": 0,
           "pontos_fora_do_quadro": 0.0}
    itens = []
    for card in cards:
        nl = listas.get(card.get("idList"), "")
        concl = bool(card.get("dueComplete"))
        pt = _pontos_do_card(card, id_pontos)
        us = [membros_map.get(m) for m in (card.get("idMembers") or [])]
        us = [u for u in us if u]
        if concl:
            qtd["concluidos"] += 1
        if pt is not None:
            qtd["com_pontos"] += 1
        if us:
            qtd["com_membro"] += 1
        if not (concl and pt is not None):
            continue
        if nl in listas_sem_pontuacao:
            continue
        total += pt
        if not us:
            qtd["concluido_sem_membro"] += 1
        ativos = [u for u in us if u in membros_ativos]
        if ativos:
            cada = pt / len(ativos)
            for u in ativos:
                por_membro[u] += cada
        else:
            # PONTO QUE EXISTE NO TOTAL E EM NINGUÉM.
            #
            # `placar.py:700` só divide entre quem está em MEMBROS_ATIVOS. Um
            # cartão de quem saiu da equipe — ou de quem ainda não foi
            # cadastrado na aba `equipe` — soma no time e não soma em pessoa
            # nenhuma. A soma dos individuais fica MENOR que o coletivo, e
            # ninguém sabe por quê.
            qtd["pontos_fora_do_quadro"] += pt
        itens.append({"id": card.get("id"), "card": card.get("name", ""),
                      "lista": nl, "pts": pt, "membros": us})
    return {"total": total, "por_membro": por_membro, "qtd": qtd,
            "itens": itens}


def motivo_de_fora(card, listas, id_pontos, listas_sem_pontuacao,
                   mes_do_card, filtro_mes):
    """Por que este cartão não somou no sistema? None quando ele somou.

    A ordem é a MESMA de `placar.py:660-692`, e isso não é detalhe: lá o
    primeiro `continue` que bate é o que decide, e um cartão pode ter dois
    motivos ao mesmo tempo. Trocar a ordem aqui daria um motivo verdadeiro e
    diferente do que de fato aconteceu.
    """
    if not card.get("dueComplete"):
        return "nao_concluido"
    if filtro_mes:
        if mes_do_card is None:
            return "mes_desconhecido"
        if mes_do_card != filtro_mes:
            return "outro_mes"
    if _pontos_do_card(card, id_pontos) is None:
        return "sem_pontuacao"
    if listas.get(card.get("idList"), "") in listas_sem_pontuacao:
        return "coluna_sem_pontuacao"
    return None


def comparar(crua, sistema):
    """(diferenca_total, por_membro) entre a conta crua e a do sistema.

    `por_membro` traz TODO mundo que aparece em qualquer um dos dois lados —
    quem some de um deles é justamente o caso interessante.
    """
    dif_total = round(crua["total"] - float(sistema.get("pts_equipe", 0.0)), 2)
    sis = sistema.get("pts_membro", {}) or {}
    por_membro = {}
    for u in sorted(set(crua["por_membro"]) | set(sis)):
        a = round(crua["por_membro"].get(u, 0.0), 2)
        b = round(float(sis.get(u, 0.0)), 2)
        por_membro[u] = {"crua": a, "sistema": b, "diferenca": round(a - b, 2)}
    return dif_total, por_membro


def resumo_dos_descartes(descartes):
    """{motivo: {"qtd": n, "pts": soma}} — o que cada motivo custou em pontos."""
    fora = {}
    for d in descartes:
        m = fora.setdefault(d["motivo"], {"qtd": 0, "pts": 0.0})
        m["qtd"] += 1
        m["pts"] += d.get("pts") or 0.0
    for m in fora.values():
        m["pts"] = round(m["pts"], 2)
    return fora


# ── Conferência ──────────────────────────────────────────────────────────────
#
# `python3 conferencia_pontos.py` roda os casos abaixo.
#
# A ENTRADA VEM DA CADEIA REAL, E NÃO DA MINHA CABEÇA (passo 6 do protocolo).
# Os cartões são montados no formato que o Trello devolve — `customFieldItems`
# com `{"value": {"number": "30"}}`, `idMembers` com IDs que o `membros_map`
# traduz — e a comparação parte de `placar._processar` DE VERDADE, com a rede
# desligada. Testar `comparar()` contra um dicionário que eu escrevesse mediria
# o meu entendimento do sistema, que é justamente o que costuma estar errado.
if __name__ == "__main__":
    import sys

    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    ID_P = "idp"
    LISTAS = {"l1": "EM ANDAMENTO", "l2": "CONCLUÍDO", "l3": "TRIAGEM"}
    MEMBROS = {"m1": "ana", "m2": "bruno", "m3": "ex_pessoa"}
    ATIVOS = {"ana": "Ana", "bruno": "Bruno"}
    SEM_PTS = {"TRIAGEM"}

    def card(i, lista, membros, pts, concl=True, atividade="2026-09-20"):
        c = {"id": f"c{i}", "name": f"Card {i}", "idList": lista,
             "idMembers": membros, "labels": [], "idLabels": [],
             "dueComplete": concl,
             "dateLastActivity": f"{atividade}T10:00:00.000Z"}
        if pts is not None:
            c["customFieldItems"] = [
                {"idCustomField": ID_P, "value": {"number": str(pts)}}]
        else:
            c["customFieldItems"] = []
        return c

    CARDS = [
        card(1, "l2", ["m1"], 30),              # Ana, 30
        card(2, "l2", ["m2"], 25),              # Bruno, 25
        card(3, "l2", ["m1", "m2"], 50),        # 25 para cada
        card(4, "l1", ["m1"], 20, concl=False),  # aberto
        card(5, "l2", [], 15),                  # concluído sem membro
        card(6, "l3", ["m1"], 60),              # coluna que não pontua
        card(7, "l2", ["m1"], 40, pts=None) if False else card(7, "l2", ["m1"], None),
        card(8, "l2", ["m3"], 80),              # de quem NÃO está na equipe
    ]

    crua = contagem_crua(CARDS, LISTAS, MEMBROS, ID_P, ATIVOS, SEM_PTS)

    # 30 + 25 + 50 + 15 + 80 = 200. O da coluna TRIAGEM e o sem pontuação ficam
    # de fora; o aberto também.
    ok("a soma crua pega todo concluído com pontuação", crua["total"] == 200.0)
    ok("e o cartão de coluna que não pontua fica fora",
       all(i["id"] != "c6" for i in crua["itens"]))
    ok("o aberto não entra", all(i["id"] != "c4" for i in crua["itens"]))
    ok("Ana fica com 30 + 25 = 55", crua["por_membro"]["ana"] == 55.0)
    ok("Bruno fica com 25 + 25 = 50", crua["por_membro"]["bruno"] == 50.0)

    # O CASO QUE NINGUÉM VÊ: 15 do cartão sem membro + 80 de quem saiu da
    # equipe = 95 pontos que existem no total do time e em pessoa nenhuma.
    ok("o total do time é MAIOR que a soma dos individuais",
       crua["total"] > sum(crua["por_membro"].values()))
    ok("e a diferença é nomeada: ponto que não tem dono",
       crua["qtd"]["pontos_fora_do_quadro"] == 95.0)
    ok("com o cartão concluído sem membro contado à parte",
       crua["qtd"]["concluido_sem_membro"] == 1)

    # ── O MOTIVO SAI NA MESMA ORDEM DO `placar._processar` ───────────────
    ok("cartão aberto: o motivo é não estar concluído",
       motivo_de_fora(CARDS[3], LISTAS, ID_P, SEM_PTS, None, (2026, 9))
       == "nao_concluido")
    ok("mês indeterminado tem motivo PRÓPRIO, e não vira 'outro mês'",
       motivo_de_fora(CARDS[0], LISTAS, ID_P, SEM_PTS, None, (2026, 9))
       == "mes_desconhecido")
    ok("concluído em agosto: outro mês",
       motivo_de_fora(CARDS[0], LISTAS, ID_P, SEM_PTS, (2026, 8), (2026, 9))
       == "outro_mes")
    ok("sem pontuação, estando no mês certo",
       motivo_de_fora(CARDS[6], LISTAS, ID_P, SEM_PTS, (2026, 9), (2026, 9))
       == "sem_pontuacao")
    ok("coluna que não pontua",
       motivo_de_fora(CARDS[5], LISTAS, ID_P, SEM_PTS, (2026, 9), (2026, 9))
       == "coluna_sem_pontuacao")
    ok("e quem somou não tem motivo nenhum",
       motivo_de_fora(CARDS[0], LISTAS, ID_P, SEM_PTS, (2026, 9), (2026, 9))
       is None)
    ok("todo motivo tem texto escrito para a tela",
       all(m in MOTIVOS for m in ("mes_desconhecido", "outro_mes",
                                  "sem_pontuacao", "coluna_sem_pontuacao",
                                  "nao_concluido")))

    _res = resumo_dos_descartes([
        {"motivo": "mes_desconhecido", "pts": 30.0},
        {"motivo": "mes_desconhecido", "pts": 25.0},
        {"motivo": "outro_mes", "pts": 10.0}])
    ok("o resumo diz quanto cada motivo custou em PONTOS",
       _res["mes_desconhecido"] == {"qtd": 2, "pts": 55.0})

    # ── E A COMPARAÇÃO PARTE DO `_processar` DE VERDADE ──────────────────
    #
    # Não de um dicionário que eu escrevesse: é a cadeia real, com a rede
    # desligada. Foi exatamente isto que faltou quando o botão dos oito
    # prompts quebrou com a guarda verde.
    try:
        import checar_tela as _ct
        _ct.instalar()
        import placar_core as _pc
        import placar as _pl

        _pc.tempos_do_board = lambda *a, **k: {}
        _pc.entradas_se_preciso = lambda *a, **k: {}
        _pc.acoes_movimento = lambda *a, **k: {}
        _pc.MEMBROS_ATIVOS.clear()
        _pc.MEMBROS_ATIVOS.update(ATIVOS)
        _pl.MEMBROS_ATIVOS = _pc.MEMBROS_ATIVOS
        _pl.LISTAS_SEM_PONTUACAO = SEM_PTS

        _sis = _pl._processar(LISTAS, CARDS, MEMBROS, ID_P, "idt", "idi",
                              filtro_mes=(2026, 9))
        _dif, _por = comparar(crua, _sis)
        ok("a comparação roda contra o _processar de verdade",
           isinstance(_dif, float))
        # Com as ações desligadas, NENHUM cartão tem data de conclusão: é
        # exatamente o estado que o board produz quando a janela é truncada.
        # O sistema devolve zero e a conta crua devolve 200 — a diferença é o
        # tamanho do buraco.
        ok("sem data de conclusão, o sistema perde TODOS os pontos",
           _sis["pts_equipe"] == 0.0 and _dif == 200.0)
        ok("e a diferença aparece por colaborador",
           _por["ana"]["crua"] == 55.0 and _por["ana"]["sistema"] == 0.0)
    except Exception as _e:
        ok(f"a comparação contra o _processar real rodou ({type(_e).__name__}: "
           f"{str(_e)[:80]})", False)

    print("\nfalhas:", falhas)
    sys.exit(1 if falhas else 0)
