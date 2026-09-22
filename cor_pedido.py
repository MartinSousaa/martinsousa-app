"""cor_pedido.py — qual cor a pessoa está pedindo, e qual ela está recusando.

O DEFEITO QUE ESTE ARQUIVO CORRIGE
-----------------------------------
`imagem.py` montava o prompt de ajuste com a cor do CADASTRO da triagem e a
chamava de regra inviolável:

    COR REAL DO PRODUTO: amarelo
    TRAVA DE COR (regra inviolável): o produto DEVE aparecer em amarelo

No mesmo texto ia a instrução da colaboradora: *"as meias não sao amarela e sim
laranja"*. O gerador recebia duas ordens opostas e obedeceu a que se declarava
inviolável. Foram dezoito rodadas — nenhuma delas por falha do modelo.

A REGRA NOVA, EM UMA FRASE
--------------------------
**Quem está olhando a imagem tem razão.** A pessoa vê o produto e vê o
resultado; o campo da triagem foi digitado à mão semanas antes. Quando os dois
discordam, vale o que a pessoa acabou de dizer — e o Studio avisa que o
cadastro está errado, porque senão o erro volta no próximo produto.

POR QUE NÃO USAR IA PARA LER A FRASE
-------------------------------------
Esta checagem roda antes de CADA geração, e existe justamente para reduzir
custo de IA. Além disso ela precisa ser determinística: a mesma frase tem de
dar a mesma cor toda vez, senão não há como testar nem como explicar à pessoa
por que o Studio entendeu o que entendeu.

O VOCABULÁRIO TEM OS ERROS DE DIGITAÇÃO DENTRO
-----------------------------------------------
"larnja", "amarlea", "brnao", "oreto", "cir". Não é desleixo: é como a equipe
escreve, e um analisador que só entende português correto não serve para este
chat. Cada erro aqui saiu de uma mensagem real do log.
"""

import re
import unicodedata

# ── O vocabulário de cor ────────────────────────────────────────────────────
# {forma escrita: cor canônica}. Inclui feminino, masculino e os erros de
# digitação que aparecem no log real.
CORES = {}


def _reg(canonica, *formas):
    for f in (canonica,) + formas:
        CORES[f] = canonica


_reg("laranja", "laranjas", "larnja", "laranga", "lranja", "cenoura")
_reg("amarelo", "amarela", "amarelas", "amarelos", "amarlea", "amarles",
     "amrelo", "amarleo")
_reg("preto", "preta", "pretas", "pretos", "oreto", "pretp", "negro")
_reg("branco", "branca", "brancas", "brancos", "brnao", "brnaco", "brranco")
_reg("azul", "azuis", "azull")
_reg("verde", "verdes")
_reg("vermelho", "vermelha", "vermelhas", "vermelhos", "vermlho")
_reg("rosa", "rosas", "pink")
_reg("roxo", "roxa", "lilas", "lilás", "violeta")
_reg("cinza", "cinzas", "grafite", "chumbo")
_reg("bege", "beges", "creme", "nude")
_reg("marrom", "marrons", "caramelo", "castanho")
_reg("dourado", "dourada", "ouro", "gold")
_reg("prateado", "prateada", "prata", "silver")
_reg("mostarda", "ocre", "amarelo-ocre", "amarelo ocre")
_reg("vinho", "bordo", "bordô")
_reg("turquesa", "tiffany")
_reg("salmao", "salmão", "coral")

# ── Os marcadores de RECUSA ─────────────────────────────────────────────────
# A cor que vem logo depois de um destes está sendo DESCARTADA, não pedida.
# Sem isto, "coloque a cor da meia laranja em vez de amarelo" devolveria
# amarelo — a última cor da frase —, que é exatamente a cor errada.
RECUSA = (
    "em vez de", "em vez do", "em vez da", "no lugar de", "no lugar do",
    "no lugar da", "ao inves de", "ao inves do", "inves de",
    "nao e", "nao sao", "nao eh", "nao era", "nao sera", "nao ta", "nao esta",
    "onde esta", "onde ta", "que esta", "esta escrito", "escrito",
    "tira essa cor", "tirar essa cor", "retira essa cor", "tira a cor",
    "tira esse", "tira essa", "retira o", "retira a", "sai o", "sai a",
    "deixa de ser", "trocar o", "troca o", "trocar a", "troca a",
)

# "de ", "do " e "da " JA ESTIVERAM nesta lista e foram tirados.
#
# A ideia era pegar "em vez de amarelo" — que ja tem marcador proprio. O que
# eles pegavam de verdade era a frase real "colocqque a cir DA MEIA larnja":
# a preposicao caia dentro da janela de 14 caracteres e marcava LARANJA como
# recusada. O analisador entao devolvia amarelo — exatamente a cor errada, e
# exatamente o defeito que este arquivo existe para corrigir.

# Quantos caracteres depois do marcador ainda contam como "logo depois".
# "em vez de amarelo" são 10; "onde esta amarelo" idem. Uma janela maior
# começaria a capturar a cor da frase seguinte.
JANELA_RECUSA = 14


def _sem_acento(t):
    t = unicodedata.normalize("NFKD", str(t or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def _ocorrencias(texto):
    """[(posição, cor canônica)] de cada cor citada, na ordem da frase."""
    t = _sem_acento(texto)
    fora = []
    for forma, canonica in CORES.items():
        f = _sem_acento(forma)
        for m in re.finditer(r"(?<![a-z0-9])" + re.escape(f) + r"(?![a-z0-9])",
                             t):
            fora.append((m.start(), canonica, len(f)))
    # Uma forma longa engole a curta: "amarelo-ocre" não vira "amarelo" + "ocre".
    fora.sort(key=lambda x: (x[0], -x[2]))
    limpo, fim_anterior = [], -1
    for pos, cor, tam in fora:
        if pos < fim_anterior:
            continue
        limpo.append((pos, cor))
        fim_anterior = pos + tam
    return limpo


def _recusada(texto_sem_acento, posicao):
    """A cor nesta posição vem logo depois de um marcador de recusa?"""
    trecho = texto_sem_acento[max(0, posicao - JANELA_RECUSA):posicao]
    return any(m in trecho for m in RECUSA)


def analisar(texto):
    """{"pedidas": [...], "recusadas": [...]} — as cores da frase, separadas.

    `pedidas` é o que deve passar a existir; `recusadas` é o que a pessoa disse
    que está errado. Uma frase pode ter as duas ("não é amarela e sim
    laranja"), só pedidas ("deixa laranja") ou nenhuma.
    """
    t = _sem_acento(texto)
    pedidas, recusadas = [], []
    for pos, cor in _ocorrencias(texto):
        (recusadas if _recusada(t, pos) else pedidas).append(cor)
    # Ordem preservada, sem repetir.
    def _unicas(lista):
        vistas, fora = set(), []
        for c in lista:
            if c not in vistas:
                vistas.add(c)
                fora.append(c)
        return fora
    return {"pedidas": _unicas(pedidas), "recusadas": _unicas(recusadas)}


def cor_alvo(texto):
    """A ÚNICA cor que o produto deve passar a ter. "" quando não é única.

    Devolve vazio de propósito quando a frase cita várias cores pedidas: isso
    é lista de card ("Branco, Laranja, Preto"), não recolorir o produto. Trocar
    a trava do produto nesse caso pintaria a peça inteira de preto.
    """
    p = analisar(texto)["pedidas"]
    return p[0] if len(p) == 1 else ""


def conflito_com_cadastro(instrucao, cor_cadastrada):
    """A pessoa está pedindo uma cor diferente da que está cadastrada?

    Devolve (tem_conflito, cor_a_usar, aviso). `cor_a_usar` é o que deve entrar
    na trava do prompt — e vale a da PESSOA, nunca a do cadastro: ela está
    olhando a imagem, o campo foi digitado semanas antes.
    """
    cad = _sem_acento(cor_cadastrada).strip()
    cad = CORES.get(cad, cad)
    alvo = cor_alvo(instrucao)
    if not alvo:
        return False, cor_cadastrada, ""
    if not cad:
        return False, alvo, ""
    if alvo == cad:
        return False, cor_cadastrada, ""
    aviso = (f"O cadastro da triagem diz **{cor_cadastrada}** e o pedido diz "
             f"**{alvo}**. Vale o pedido — mas corrija a cor na triagem, "
             f"senão o próximo produto nasce errado de novo.")
    return True, alvo, aviso


# ── O pedido é sobre o próprio produto? ─────────────────────────────────────
# Serve para desarmar a trava que reverte a imagem quando "o produto mudou".
# Ela existe porque o gerador redesenhava a peça ao mexer no fundo — mas
# quando o pedido É sobre a peça, mudar a peça é o objetivo, e reverter
# transforma um acerto em falha. Foi o que produziu quatro "❌ não consegui".
_SOBRE_O_PRODUTO = (
    "cor", "cores", "tom", "pint", "colorir", "recolor",
    "dedo", "dedos", "pata", "garra", "perna", "pernas", "pe ", "pes",
    "rosto", "cara", "olho", "bico", "cano", "punho", "solado",
    "produto", "meia", "meias", "peca", "peça", "formato", "textura",
    "estampa", "desenho da", "modelo do", "anatomia",
)


def pedido_mexe_no_produto(instrucao):
    """A instrução pede para mudar a PEÇA (e não o fundo, o texto ou a cena)?"""
    t = " " + _sem_acento(instrucao) + " "
    if any(_sem_acento(c) in t for c in CORES):
        return True
    return any(_sem_acento(p) in t for p in _SOBRE_O_PRODUTO)


def contradicoes(prompt_montado):
    """As ordens opostas dentro do prompt PRONTO, antes de ele ser enviado.

    É a checagem que custa zero e que teria travado as dezoito rodadas na
    primeira: o texto carregava "COR REAL DO PRODUTO: amarelo" e, mais abaixo,
    o pedido "mude para laranja".

    Devolve [] quando está limpo.
    """
    m = re.search(r"COR REAL DO PRODUTO:\s*(.+)", prompt_montado or "")
    if not m:
        return []
    travada = _sem_acento(m.group(1).strip().split("\n")[0])
    travada = CORES.get(travada, travada)
    if not travada:
        return []
    # O pedido fica abaixo da trava; olhar o prompt inteiro faria a própria
    # trava ("É PROIBIDO reinterpretar como: azul, bege…") virar contradição.
    depois = (prompt_montado or "")[m.end():]
    depois = re.sub(r"(?im)^.*PROIBIDO.*$", "", depois)
    pedidas = analisar(depois)["pedidas"]
    fora = []
    for cor in pedidas:
        if cor != travada:
            fora.append(
                f"a trava manda o produto ser {travada}, e o pedido diz {cor}")
    return fora


# ── Conferência ──────────────────────────────────────────────────────────────
# `python3 cor_pedido.py`. As frases são as REAIS da conversa de 22/09 — com os
# erros de digitação, que é o ponto: um analisador que só entende português
# correto não serve para este chat.
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # ── a frase que começou tudo ─────────────────────────────────────────
    r = analisar("chat as meias não sao amarela e sim laranja")
    ok("pede laranja", r["pedidas"] == ["laranja"])
    ok("e recusa amarelo", r["recusadas"] == ["amarelo"])

    # A armadilha: a cor recusada vem DEPOIS da pedida.
    r = analisar("e na iamgem 7 colocquqe a cir da meia larnja em vez de "
                 "amarelo")
    ok("erro de digitação não atrapalha", r["pedidas"] == ["laranja"])
    ok("'em vez de amarelo' é recusa, mesmo vindo no fim",
       r["recusadas"] == ["amarelo"])
    ok("e a cor alvo é a pedida, não a última da frase",
       cor_alvo("colocqque a cir da meia larnja em vez de amarelo")
       == "laranja")

    ok("'onde esta amarelo colocar laranja' pede laranja",
       cor_alvo("quero que voce mude as cores da meia onde esta amarelo "
                "colocar laranja") == "laranja")

    # Lista de card não é recolorir o produto.
    r = analisar("na imagem 5 tira essa cor ocre e so deixei a branca amarelo "
                 "e oreto")
    ok("a lista do card tem três cores pedidas", len(r["pedidas"]) == 3)
    ok("e o ocre está recusado", "mostarda" in r["recusadas"])
    ok("com três cores, NÃO se troca a trava do produto",
       cor_alvo("tira essa cor ocre e so deixei a branca amarelo e oreto")
       == "")

    ok("frase sem cor devolve vazio", cor_alvo("tira esse 3 e que ta estranho")
       == "")
    ok("'cor' sozinho não nomeia cor nenhuma", cor_alvo("cor") == "")

    # Forma longa não vira duas cores.
    ok("'amarelo-ocre' é uma cor só",
       analisar("CORES: Branco, Preto, Amarelo-Ocre")["pedidas"]
       == ["branco", "preto", "mostarda"])

    # ── o conflito com o cadastro ────────────────────────────────────────
    tem, cor, aviso = conflito_com_cadastro(
        "as meias não sao amarela e sim laranja", "amarelo")
    ok("o conflito é detectado", tem)
    ok("e QUEM VENCE é o pedido, não o cadastro", cor == "laranja")
    ok("com aviso para corrigir a triagem", "triagem" in aviso)

    tem, cor, _ = conflito_com_cadastro("deixa laranja", "laranja")
    ok("cor igual não é conflito", not tem)
    tem, cor, _ = conflito_com_cadastro("tira o texto de cima", "amarelo")
    ok("pedido sem cor mantém o cadastro", not tem and cor == "amarelo")
    tem, cor, _ = conflito_com_cadastro("deixa laranja", "")
    ok("cadastro vazio adota a cor pedida", not tem and cor == "laranja")
    tem, cor, _ = conflito_com_cadastro("as meias não sao amarela e sim "
                                        "laranja", "AMARELA")
    ok("o cadastro escrito de outro jeito ainda casa", tem and cor == "laranja")

    # ── o pedido mexe no produto? ────────────────────────────────────────
    ok("cor mexe no produto",
       pedido_mexe_no_produto("muda a cor da meia para laranja"))
    ok("dedo mexe no produto",
       pedido_mexe_no_produto("os pe da meia esta esranho sao so 3 dedos"))
    ok("trocar texto de card NÃO mexe no produto",
       not pedido_mexe_no_produto("troca o titulo para ALTURA"))
    ok("trocar cenário NÃO mexe no produto",
       not pedido_mexe_no_produto("em vez de encma da cama coloque em uma "
                                  "academia"))

    # ── a contradição dentro do prompt pronto ────────────────────────────
    PROMPT_RUIM = (
        "PRODUTO: Meia Pé de Galinha\n"
        "COR REAL DO PRODUTO: amarelo\n"
        "TRAVA DE COR (regra inviolável): o produto DEVE aparecer em amarelo.\n"
        "É PROIBIDO reinterpretar essa cor como: azul, bege, marrom.\n"
        "\nPEDIDO: mude a faixa da perna para laranja cenoura vivo.\n"
    )
    c = contradicoes(PROMPT_RUIM)
    ok("a contradição do prompt real é pega", len(c) == 1)
    ok("e ela nomeia as duas cores",
       "amarelo" in c[0] and "laranja" in c[0])

    PROMPT_BOM = PROMPT_RUIM.replace("amarelo", "laranja") \
                            .replace("para laranja cenoura", "para laranja")
    ok("prompt coerente não acusa nada", contradicoes(PROMPT_BOM) == [])
    ok("a própria lista de proibições não vira contradição",
       not any("azul" in x for x in contradicoes(PROMPT_RUIM)))
    ok("prompt sem trava não acusa nada", contradicoes("qualquer texto") == [])
    ok("prompt vazio não quebra", contradicoes("") == [])
    ok("None não quebra", contradicoes(None) == [])

    print("\nfalhas:", falhas)
    raise SystemExit(falhas)
