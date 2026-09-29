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


# ── O QUE É REGRA, E O QUE É PERDA ──────────────────────────────────────────
#
# 29/09, com a tela já no ar, o cabeçalho anunciou "Diferença 12506 pts". Dos
# 12506, 11836 eram cartões concluídos em OUTRO MÊS — e `contagem_crua` ignora
# o mês DE PROPÓSITO, porque o mês é justamente a regra sob suspeita. Ou seja:
# 94,6% do alarme era o sistema funcionando, anunciado como rombo.
#
# "Verificador que dá alarme falso é pior que nenhum: ensina a ignorá-lo"
# (CLAUDE.md). A tela feita para ENCERRAR a discussão ia ensinar a equipe a
# desconfiar dela também.
#
# Por isso todo motivo cai num dos dois grupos, e o autoteste reprova motivo
# novo que não caia em nenhum: motivo sem grupo é o alarme falso de volta.
MOTIVOS_ESPERADOS = frozenset({
    "outro_mes",            # a conta crua é que ignora o mês, não o sistema
    "coluna_sem_pontuacao",  # a coluna não pontua, por configuração
    "nao_concluido",        # ainda não terminou
})

MOTIVOS_SILENCIOSOS = frozenset({
    "mes_desconhecido",  # o Studio PERDEU a data de conclusão — some do total
    "sem_pontuacao",     # concluído e sem valor no campo: ninguém preencheu
})


def perda_silenciosa(descartes):
    """Pontos que somem sem que nenhuma regra explique. É ESTE o número.

    É o que a equipe chama de "minha pontuação caiu": cartão concluído, com
    pontos, dentro do quadro — e que não soma em mês nenhum.
    """
    return round(sum(d.get("pts") or 0.0 for d in descartes
                     if d.get("motivo") not in MOTIVOS_ESPERADOS), 2)


def explicado_pela_regra(descartes):
    """O resto: pontos que ficaram de fora porque alguma regra mandou."""
    return round(sum(d.get("pts") or 0.0 for d in descartes
                     if d.get("motivo") in MOTIVOS_ESPERADOS), 2)


def por_coluna(cards_pts):
    """{coluna: {"qtd", "pts"}} — onde os pontos DO MÊS estão, coluna a coluna.

    É a resposta a "quanto tem na TRIAGEM?" saindo da MESMA lista que soma o
    total (`cards_pts`, montada em `placar.py:698`). Uma segunda varredura do
    quadro daria um segundo número, e o dia em que discordassem ninguém
    saberia qual acreditar — `_processar` já duplicado nesta base discordou em
    330 pontos no mesmo mês.
    """
    fora = {}
    for c in (cards_pts or []):
        e = fora.setdefault(c.get("lista") or "(sem coluna)",
                            {"qtd": 0, "pts": 0.0})
        e["qtd"] += 1
        e["pts"] += c.get("pts") or 0.0
    for e in fora.values():
        e["pts"] = round(e["pts"], 2)
    return fora


def perda_por_membro(descartes, membros_ativos):
    """{usuario: pontos que sumiram DELE sem regra que explique}.

    A subtração "Trello menos Studio" por pessoa não serve: a coluna crua soma
    todos os meses e a do Studio só o mês filtrado, então ela acusa o mês dos
    outros como perda. A pessoa lê 5.699 e entende que foi roubada.

    A divisão é a MESMA do placar (`placar.py:700-702`): o cartão se reparte
    igual entre os ativos marcados nele.
    """
    por = {}
    for d in descartes or []:
        if d.get("motivo") in MOTIVOS_ESPERADOS:
            continue
        ativos = [u for u in (d.get("membros") or []) if u in membros_ativos]
        if not ativos:
            continue
        cada = (d.get("pts") or 0.0) / len(ativos)
        for u in ativos:
            por[u] = round(por.get(u, 0.0) + cada, 2)
    return por


def sem_dono_no_mes(cards_pts, membros_ativos):
    """Pontos que somam no time e em pessoa nenhuma, DENTRO do mês analisado.

    `contagem_crua` responde a mesma pergunta sem filtro de mês — e foi assim
    que o aviso da tela anunciou o acumulado de quatro meses embaixo de um
    painel de setembro. A entrada certa é `cards_pts`, a lista que o
    `_processar` devolve com o mês já aplicado (`placar.py:698`).

    É este o número que explica a soma dos individuais dar MENOS que o
    coletivo: `placar.py:700` só divide entre quem está em `MEMBROS_ATIVOS`.
    """
    return round(sum(
        c.get("pts") or 0.0 for c in (cards_pts or [])
        if not any(u in membros_ativos for u in (c.get("membros") or []))), 2)


# A LEITURA DA PONTUAÇÃO NÃO MORA AQUI — E ISSO É O PONTO.
#
# A primeira versão deste arquivo tinha um `_pontos_do_card` próprio, lendo
# `customFieldItems`. `placar.py:372` já tem `_num`, que faz exatamente isso,
# e é ele que produz o número que a tela mostra.
#
# Duas leituras do mesmo campo, na tela criada para ENCERRAR a discussão
# sobre o número: se divergissem em qualquer borda — valor com vírgula, campo
# vazio, texto no lugar de número —, a conferência acusaria uma diferença que
# não existe, e a equipe passaria a desconfiar da ferramenta de conferir.
#
# `checar_impacto` pegou isto: "nome mudado com leitor em outro arquivo e sem
# guarda nenhuma". Uma pergunta, uma resposta.
#
# Quem chama PASSA a função de ler. Sem valor padrão de propósito: um padrão
# aqui seria a segunda resposta de volta, escondida atrás de um
# `ler_pontos=None`.


def contagem_crua(cards, listas, membros_map, id_pontos, membros_ativos,
                  listas_sem_pontuacao, ler_pontos):
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
        pt = ler_pontos(card, id_pontos)
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
                   mes_do_card, filtro_mes, ler_pontos):
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
    if ler_pontos(card, id_pontos) is None:
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

    # A LEITURA VEM DO `placar._num`, que e quem produz o numero da tela.
    # Escrever uma leitura so para o teste seria a segunda resposta de volta.
    import checar_tela as _ct0
    _ct0.instalar()
    import placar as _pl0
    LER = _pl0._num

    crua = contagem_crua(CARDS, LISTAS, MEMBROS, ID_P, ATIVOS, SEM_PTS, LER)

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
       motivo_de_fora(CARDS[3], LISTAS, ID_P, SEM_PTS, None, (2026, 9), LER)
       == "nao_concluido")
    ok("mês indeterminado tem motivo PRÓPRIO, e não vira 'outro mês'",
       motivo_de_fora(CARDS[0], LISTAS, ID_P, SEM_PTS, None, (2026, 9), LER)
       == "mes_desconhecido")
    ok("concluído em agosto: outro mês",
       motivo_de_fora(CARDS[0], LISTAS, ID_P, SEM_PTS, (2026, 8), (2026, 9), LER)
       == "outro_mes")
    ok("sem pontuação, estando no mês certo",
       motivo_de_fora(CARDS[6], LISTAS, ID_P, SEM_PTS, (2026, 9), (2026, 9), LER)
       == "sem_pontuacao")
    ok("coluna que não pontua",
       motivo_de_fora(CARDS[5], LISTAS, ID_P, SEM_PTS, (2026, 9), (2026, 9), LER)
       == "coluna_sem_pontuacao")
    ok("e quem somou não tem motivo nenhum",
       motivo_de_fora(CARDS[0], LISTAS, ID_P, SEM_PTS, (2026, 9), (2026, 9), LER)
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

    # ── UMA LEITURA SÓ, E ISSO É ESTRUTURA, NÃO NÚMERO ──────────────────
    #
    # A mutação que devolveu uma leitura própria a este arquivo passou VERDE:
    # nos cartões do teste ela dava o mesmo número. Guarda que compara
    # RESULTADO não vê duas fontes concordando por acaso — e o dia em que
    # divergirem é justamente o dia em que a conferência acusa uma diferença
    # que não existe.
    #
    # A pergunta certa é estrutural: este arquivo lê `customFieldItems`?
    import ast as _ast_cf
    _fonte_cf = open(__file__, encoding="utf-8").read()
    _corpo_cf = _fonte_cf.split('if __name__ == "__main__":')[0]
    _le_campo = any(
        isinstance(_n, _ast_cf.Constant) and _n.value == "customFieldItems"
        for _n in _ast_cf.walk(_ast_cf.parse(_corpo_cf)))
    ok("este arquivo NÃO lê o campo de pontuação por conta própria",
       not _le_campo)

    # E QUEM CHAMA PASSA A LEITURA DA TELA — por AST, no `placar.py`.
    import inspect as _insp_cf
    _arv_pl = _ast_cf.parse(_ast_cf.unparse(_ast_cf.parse(
        _insp_cf.getsource(_pl.bloco_conferencia_de_pontos).lstrip())))
    _passou_num = False
    for _n in _ast_cf.walk(_arv_pl):
        if (isinstance(_n, _ast_cf.Call)
                and (getattr(_n.func, "attr", "")
                     or getattr(_n.func, "id", "")) == "contagem_crua"):
            _passou_num = any(
                isinstance(_a, _ast_cf.Name) and _a.id == "_num"
                for _a in list(_n.args) + [k.value for k in _n.keywords])
    ok("e a tela passa o `_num` dela para a contagem crua", _passou_num)

    # ── O CABEÇALHO NÃO PODE CHAMAR DE PERDA O QUE É REGRA ──────────────
    #
    # 29/09, com a tela no ar: "Diferença 12506 pts" em vermelho. Dos 12506,
    # 11836 eram cartões concluídos em OUTRO MÊS — e a conta crua ignora o mês
    # DE PROPÓSITO (`contagem_crua`, logo acima). Ou seja: 94,6% do alarme era
    # comportamento correto, anunciado como rombo.
    #
    # "Verificador que dá alarme falso é pior que nenhum: ensina a ignorá-lo"
    # — CLAUDE.md. A tela feita para encerrar a discussão ia ensinar a equipe
    # a não olhar para ela.
    #
    # Então todo motivo é CLASSIFICADO: ou a regra explica, ou é perda.
    ok("todo motivo está classificado — esperado ou silencioso",
       MOTIVOS_ESPERADOS | MOTIVOS_SILENCIOSOS == set(MOTIVOS))
    ok("e os dois grupos não se sobrepõem",
       not (MOTIVOS_ESPERADOS & MOTIVOS_SILENCIOSOS))
    ok("'outro mês' é regra, e não perda", "outro_mes" in MOTIVOS_ESPERADOS)
    ok("'mês desconhecido' é perda, e não regra",
       "mes_desconhecido" in MOTIVOS_SILENCIOSOS)

    _dsc = [{"motivo": "outro_mes", "pts": 11836.0},
            {"motivo": "mes_desconhecido", "pts": 1070.0},
            {"motivo": "coluna_sem_pontuacao", "pts": 400.0}]
    ok("a perda sem explicação deixa 'outro mês' de fora",
       perda_silenciosa(_dsc) == 1070.0)
    ok("e o que a regra explica sai somado à parte",
       explicado_pela_regra(_dsc) == 12236.0)
    ok("sem descarte nenhum, a perda é zero", perda_silenciosa([]) == 0.0)

    # ── O PONTO SEM DONO TAMBÉM É DO MÊS, E NÃO DE SEMPRE ───────────────
    #
    # O mesmo erro do cabeçalho, no aviso amarelo: "800 pontos somam no time e
    # em pessoa nenhuma" saía de `contagem_crua`, que ignora o mês. O Painel
    # mostra SETEMBRO, e o aviso somava cartão sem dono de qualquer mês.
    #
    # A entrada vem de `cards_pts`, que é a lista que o `_processar` já
    # devolve — mês aplicado, cartão a cartão (`placar.py:698`).
    ok("sem dono conta só o cartão que o MÊS já aprovou",
       sem_dono_no_mes(_sis["cards_pts"], ATIVOS) == 0.0)
    _cp = [{"pts": 15.0, "membros": []},
           {"pts": 80.0, "membros": ["ex_pessoa"]},
           {"pts": 30.0, "membros": ["ana"]},
           {"pts": 50.0, "membros": ["ana", "ex_pessoa"]}]
    ok("cartão sem membro e cartão de quem saiu da equipe somam",
       sem_dono_no_mes(_cp, ATIVOS) == 95.0)
    ok("e cartão com UM ativo junto não entra — ele já tem dono",
       sem_dono_no_mes(_cp[3:], ATIVOS) == 0.0)

    # ── A TABELA POR PESSOA NÃO PODE ACUSAR O MÊS DOS OUTROS ────────────
    #
    # "Myrella — Trello 7772, Studio 2073, Diferença 5699". Ela leu isso como
    # 5.699 pontos roubados dela. Eram os meses de junho, julho e agosto: a
    # coluna crua soma todos os meses e a do Studio só setembro, então a
    # subtração das duas NÃO é o que ela perdeu.
    #
    # O que ela perdeu é a fatia DELA nos descartes silenciosos — e só isso.
    _dsc_m = [
        {"motivo": "outro_mes", "pts": 300.0, "membros": ["ana"]},
        {"motivo": "mes_desconhecido", "pts": 60.0, "membros": ["ana"]},
        {"motivo": "mes_desconhecido", "pts": 40.0, "membros": ["ana", "bruno"]},
        {"motivo": "mes_desconhecido", "pts": 90.0, "membros": []},
    ]
    _pm = perda_por_membro(_dsc_m, ATIVOS)
    ok("a perda da pessoa ignora o que é de outro mês", _pm["ana"] == 80.0)
    ok("e cartão de dois divide igual, como o placar divide",
       _pm["bruno"] == 20.0)
    ok("cartão sem dono não vira perda de ninguém",
       sum(_pm.values()) == 100.0)

    # ESTA GUARDA JA NASCEU FRACA UMA VEZ, e a mutação a pegou no mesmo dia.
    #
    # A primeira versão perguntava "a tela CHAMA `perda_por_membro`?". A
    # mutação trocou o valor da coluna de volta para `_v["diferenca"]` e
    # deixou a chamada onde estava — guarda verde, alarme falso de volta na
    # tela. Chamar não é usar. A pergunta certa é de onde sai o VALOR daquela
    # coluna, e ela se responde no nó do dicionário, não no arquivo.
    _COL = "Perdeu sem explicação"
    _valor_ok = False
    for _n in _ast_cf.walk(_arv_pl):
        if not isinstance(_n, _ast_cf.Dict):
            continue
        for _k, _v_no in zip(_n.keys, _n.values):
            if isinstance(_k, _ast_cf.Constant) and _k.value == _COL:
                _valor_ok = any(
                    isinstance(_x, _ast_cf.Name) and _x.id == "_perda_pm"
                    for _x in _ast_cf.walk(_v_no))
    ok(f"a coluna '{_COL}' sai de `perda_por_membro`, e não da subtração",
       _valor_ok)

    # ── ONDE OS PONTOS DO MÊS ESTÃO, COLUNA A COLUNA ───────────────────
    #
    # Dono, 29/09: "quero o resumo geral, por colaborador, e o que tem na
    # TRIAGEM". As duas primeiras a tela já dava; a terceira não — e era
    # justamente a TRIAGEM que estava comendo a pontuação.
    #
    # A entrada é `cards_pts`, a MESMA lista que soma o total.
    _pc_col = por_coluna(_sis["cards_pts"])
    ok("o por-coluna soma o mesmo total que a equipe",
       round(sum(v["pts"] for v in _pc_col.values()), 2)
       == round(_sis["pts_equipe"], 2))
    _cp_col = [{"lista": "TRIAGEM", "pts": 100.0},
               {"lista": "TRIAGEM", "pts": 70.0},
               {"lista": "DESATIVAR (50)", "pts": 50.0}]
    ok("e diz quanto cada coluna tem, com a contagem",
       por_coluna(_cp_col)["TRIAGEM"] == {"qtd": 2, "pts": 170.0})
    ok("cartão sem coluna não some da conta",
       por_coluna([{"pts": 10.0}])["(sem coluna)"]["pts"] == 10.0)

    _mostra_col = any(
        isinstance(_n, _ast_cf.Call)
        and (getattr(_n.func, "attr", "") or getattr(_n.func, "id", ""))
        == "por_coluna"
        for _n in _ast_cf.walk(_arv_pl))
    ok("e a tela mostra o por-coluna", _mostra_col)

    _mostra_sem_dono = any(
        isinstance(_n, _ast_cf.Call)
        and (getattr(_n.func, "attr", "") or getattr(_n.func, "id", ""))
        == "sem_dono_no_mes"
        for _n in _ast_cf.walk(_arv_pl))
    ok("e o aviso da tela chama `sem_dono_no_mes`", _mostra_sem_dono)

    # E A TELA MOSTRA A PERDA, não a diferença crua — por AST.
    _mostra_perda = any(
        isinstance(_n, _ast_cf.Call)
        and (getattr(_n.func, "attr", "") or getattr(_n.func, "id", ""))
        == "perda_silenciosa"
        for _n in _ast_cf.walk(_arv_pl))
    ok("e o cabeçalho da tela chama `perda_silenciosa`", _mostra_perda)

    print("\nfalhas:", falhas)
    sys.exit(1 if falhas else 0)
