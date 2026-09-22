"""gargalos.py — onde o trabalho de imagem trava, e de quem é a trava.

A PERGUNTA QUE ESTE MÓDULO RESPONDE
-----------------------------------
O dono a formulou assim: *"é na solicitação do colaborador que não está
sabendo se comunicar, ou o sistema não está entendendo, ou está solicitando o
reajuste errado?"*

São três culpados possíveis e a resposta muda o que fazer: treinar a equipe,
melhorar o prompt do Assistente ou consertar o gerador. Sem separar os três,
qualquer conserto é palpite — e já se perderam dias ajustando o texto do
pedido de correção quando o problema real era outro.

O DADO JÁ EXISTE, SÓ NÃO ERA LIDO
----------------------------------
`log_imagem.py` grava uma linha por comando desde o episódio do Gladiador:
quando, quem, qual produto, qual imagem, o que foi pedido e o que saiu. São
meses de conversa real guardados e nunca somados.

Este módulo não cria dado novo: ele lê o que está lá e responde as cinco
perguntas do dono — quantas refeitas, o que foi pedido, quantas vezes a mesma
coisa, quantas tentativas até acertar, quanto tempo levou.

O PROBLEMA DIFÍCIL: CADA UM ESCREVE DE UM JEITO
------------------------------------------------
"tira essa cor ocre", "as meias não sao amarela e sim laranja", "muda as cores
da meia onde esta amarelo colocar laranja" e "cor" são o MESMO pedido. Contar
texto literal daria quatro pedidos diferentes e nenhum padrão.

Por isso existe `intencao()`: ela reduz a frase a uma INTENÇÃO e um ALVO, por
palavra-chave e sem chamar modelo nenhum. Duas razões para não usar IA aqui:

  1. custo — esta tela existe justamente para investigar custo de IA;
  2. determinismo — o mesmo log tem que dar o mesmo número toda vez, senão
     ninguém consegue comparar a semana que vem com esta.

A lista de palavras é de português de teclado, com erro de digitação incluído:
"iamgem", "imagen", "larnja", "eras" — porque é assim que a equipe escreve, e
um classificador que só entende português correto não serve para este log.

ESTA TELA NÃO É PARA A EQUIPE
------------------------------
Pedido explícito do dono. Ela mede as pessoas pelo nome, e medir gente em
público muda o que a gente escreve — a partir daí o log passa a descrever o
que a equipe acha que o chefe quer ler, e o dado morre.
"""

import re
import unicodedata
from datetime import datetime

# ── As intenções, na ordem em que são testadas ──────────────────────────────
#
# A ordem importa: "tira essa cor ocre" fala em tirar E em cor, e é um pedido
# de COR. O mais específico vem primeiro; REMOVER é o balde largo e fica no
# fim, antes de OUTRO.
#
# Os termos incluem os erros de digitação que aparecem no log real. Não é
# desleixo: é o vocabulário que a tela precisa entender para servir para algo.
INTENCOES = [
    ("COR", (
        "cor", "cores", "corr", "laranja", "larnja", "amarelo", "amarela",
        "amarlea", "amarles", "ocre", "mostarda", "preto", "preta", "branco",
        "branca", "brnao", "azul", "verde", "vermelho", "rosa", "tom",
        "colorido", "pintar", "pinta",
    )),
    ("TEXTO", (
        "escrito", "escrita", "escritas", "texto", "titulo", "título",
        "escreve", "escrever", "palavra", "frase", "ortografia", "portugues",
        "português", "erro de", "card", "cards", "balao", "balão", "selo",
        "bullet", "numeracao", "numeração", "tamanho unico", "tamanho único",
        "38 ao 43", "medida", "medidas", "altura", "largura", "peso",
        "comprimento",
    )),
    ("CENARIO", (
        "fundo", "cenario", "cenário", "ambiente", "ambientacao",
        "ambientação", "academia", "cama", "presente", "mesa", "estudio",
        "estúdio", "parede", "piso", "paisagem", "clima", "local", "lugar",
        "coloque em", "coloca em", "em vez de", "simples", "rica", "melhore",
    )),
    ("ANATOMIA", (
        "dedo", "dedos", "perna", "pernas", "pe ", "pés", "pe,", "pata",
        "garra", "rosto", "cara", "olho", "olhos", "bico", "estranho",
        "estranha", "deformado", "torto", "anatomia", "3 dedos", "tres dedos",
    )),
    ("ENQUADRAMENTO", (
        "enquadramento", "zoom", "afast", "aproxim", "corta", "cortado",
        "centraliz", "desloc", "maior", "menor", "posicao", "posição",
        "alinha",
    )),
    ("REFERENCIA", (
        "referencia", "referência", "refenrecia", "refencia", "igual a",
        "igual à", "igual a imagem", "mesma da", "modelo da", "foto ref",
    )),
    ("REMOVER", (
        "tira", "tirar", "tire", "retira", "retirar", "remove", "remover",
        "some", "sumir", "apaga", "apagar", "sem o", "sem a", "exclui",
    )),
    ("REFAZER", (
        "refaz", "refazer", "refaça", "refaca", "de novo", "do zero",
        "novamente", "outra vez",
    )),
]

# O que o `resultado` gravado diz sobre como terminou.
FALHOU = "❌"          # ❌
DEU_CERTO = "✅"       # ✅
EFEITO_COLATERAL = "⚠"  # ⚠️

# Quantas vezes o MESMO pedido precisa se repetir para virar gargalo. Duas é
# normal — uma tentativa e uma correção. Da terceira em diante é sintoma.
REPETICOES_PARA_GARGALO = 3


def _sem_acento(t):
    t = unicodedata.normalize("NFKD", str(t or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def intencao(texto):
    """A intenção do pedido, independente de como a pessoa escreveu.

    Devolve uma das chaves de INTENCOES, ou "OUTRO". Uma frase pode conter
    várias palavras de baldes diferentes; vence o balde mais específico, que é
    o que aparece primeiro na lista.
    """
    t = " " + _sem_acento(texto) + " "
    for nome, termos in INTENCOES:
        for termo in termos:
            if _sem_acento(termo) in t:
                return nome
    return "OUTRO"


def imagens_citadas(texto):
    """Os números de imagem mencionados no pedido. [] quando não há nenhum.

    "na imagem 6 e 7 e a 8" devolve [6, 7, 8]; "8 4 6 7" também. O segundo
    formato é comum no log: a pessoa responde só com os números.
    """
    t = _sem_acento(texto)
    nums = [int(n) for n in re.findall(r"\b([1-9]\d?)\b", t)]
    # Número grande não é índice de imagem: "40 cm", "38 ao 43", "46 g".
    return [n for n in nums if 1 <= n <= 20]


def tentativas(resultado):
    """Quantas tentativas aquela rodada consumiu, lendo o texto do resultado.

    O Studio já escreve "na 2ª tentativa" e "não consegui fazer em 2
    tentativa(s)". Uma rodada sem essa marca custou uma tentativa.
    """
    t = _sem_acento(resultado)
    m = re.search(r"(\d+)\s*(?:a|ª)?\s*tentativa", t)
    if m:
        try:
            return max(1, int(m.group(1)))
        except ValueError:
            return 1
    return 1


def desfecho(resultado):
    """'falhou' | 'colateral' | 'ok' — como aquela rodada terminou.

    'colateral' é o caso que mais importa: o pedido foi atendido E a imagem
    mudou em coisa que ninguém pediu. É o que fabrica a próxima rodada.
    """
    r = str(resultado or "")
    if FALHOU in r or "nao consegui" in _sem_acento(r):
        return "falhou"
    if EFEITO_COLATERAL in r or "sem ter sido pedido" in _sem_acento(r):
        return "colateral"
    if DEU_CERTO in r:
        return "ok"
    return "ok"


def _quando(v):
    """datetime a partir do carimbo 'dd/mm/aaaa HH:MM:SS'. None se não der."""
    t = str(v or "").strip()
    for formato in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
                    "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(t, formato)
        except ValueError:
            continue
    return None


def _acoes_de_ajuste(linhas):
    """Só as linhas que são pedido de mudança. Geração inicial não é gargalo."""
    fora = []
    for l in (linhas or []):
        acao = _sem_acento(l.get("acao"))
        if acao.startswith("gerar_tudo"):
            continue
        if not str(l.get("instrucao", "")).strip():
            continue
        fora.append(l)
    return fora


def _so_numeros(texto):
    """A frase é só uma lista de imagens, sem dizer o que fazer nelas?

    "8 4 6 7" e "na 1 na 3 6 e pricinamente na 5" são mensagens reais do log.
    Sozinhas não dizem assunto nenhum — elas CONTINUAM o pedido anterior.
    """
    t = _sem_acento(texto)
    t = re.sub(r"[0-9]+", " ", t)
    # O que sobra depois de tirar os números e as palavras de ligação.
    ligacao = {"na", "no", "e", "a", "o", "de", "da", "do", "em", "nas", "nos",
               "tambem", "tbm", "pricinamente", "principalmente", "so",
               "somente", "as", "os", "imagem", "imagens", "iamgem", "imagen",
               "foto", "fotos", "img"}
    resto = [w for w in t.split() if w and w not in ligacao]
    return not resto


def _herdar_assunto(linhas):
    """[(linha, intenção)] — a mensagem que é só número herda o assunto anterior.

    POR QUE ISTO EXISTE
    A conversa real tem este par, um minuto depois do outro:

        "chat as meias não sao amarela e sim laranja"
        "na 1 na 3 6 e pricinamente na 5"

    A segunda é a MESMA conversa, e classificá-la como OUTRO espalharia as
    falhas de cor por um balde sem nome — justamente o gargalo que a tela
    existe para achar. Quem fala continua falando do mesmo assunto até mudar
    de assunto.

    A herança vale por pessoa e só para frente, nunca entre colaboradores
    diferentes: dois chats abertos ao mesmo tempo são duas conversas.
    """
    ultimo = {}
    fora = []
    for l in linhas:
        instrucao = str(l.get("instrucao", ""))
        alvo = intencao(instrucao)
        u = str(l.get("usuario", "") or "?")
        if alvo == "OUTRO" and _so_numeros(instrucao) and ultimo.get(u):
            alvo = ultimo[u]
        elif alvo != "OUTRO":
            ultimo[u] = alvo
        fora.append((l, alvo))
    return fora


def agrupar(linhas):
    """Os pedidos juntados por (produto, imagem, intenção).

    Este é o coração da tela: é o agrupamento que responde "quantas vezes
    precisou pedir a mesma coisa", mesmo quando as quatro frases não se
    parecem em nada.

    Devolve [{produto, imagem, intencao, pedidos, tentativas, falhas,
              colaterais, minutos, usuarios, frases, diagnostico}].
    """
    grupos = {}
    for l, _intencao in _herdar_assunto(_acoes_de_ajuste(linhas)):
        instrucao = str(l.get("instrucao", ""))
        alvo = l.get("imagem")
        alvo = str(alvo).strip() if alvo not in (None, "") else ""
        if not alvo:
            citadas = imagens_citadas(instrucao)
            alvo = str(citadas[0]) if citadas else "—"
        chave = (str(l.get("produto", "")).strip(), alvo, _intencao)
        g = grupos.setdefault(chave, {
            "produto": chave[0], "imagem": chave[1], "intencao": chave[2],
            "pedidos": 0, "tentativas": 0, "falhas": 0, "colaterais": 0,
            "usuarios": set(), "frases": [], "quandos": [],
        })
        g["pedidos"] += 1
        g["tentativas"] += tentativas(l.get("resultado"))
        d = desfecho(l.get("resultado"))
        g["falhas"] += d == "falhou"
        g["colaterais"] += d == "colateral"
        u = str(l.get("usuario", "") or "").strip()
        if u:
            g["usuarios"].add(u)
        g["frases"].append(instrucao[:120])
        q = _quando(l.get("quando"))
        if q:
            g["quandos"].append(q)

    fora = []
    for g in grupos.values():
        qs = sorted(g.pop("quandos"))
        g["minutos"] = round((qs[-1] - qs[0]).total_seconds() / 60.0, 1) \
            if len(qs) > 1 else 0.0
        g["usuarios"] = sorted(g["usuarios"])
        g["diagnostico"] = diagnosticar(g)
        fora.append(g)
    # Do mais caro para o mais barato: tentativa é geração, e geração é dinheiro.
    return sorted(fora, key=lambda g: (-g["tentativas"], -g["pedidos"]))


def diagnosticar(g):
    """De quem é a trava deste grupo. A pergunta que o dono fez.

    Quatro respostas, e cada uma leva a uma ação diferente:

      GERADOR      o pedido estava claro e o gerador não entregou
      COLATERAL    entregou o pedido e quebrou outra coisa junto
      ASSISTENTE   disse que fez, e a pessoa teve que pedir de novo
      PEDIDO       a frase não diz o suficiente para alguém executar

    A ordem é deliberada. Falha explícita do gerador é fato registrado e vence
    qualquer interpretação; efeito colateral também está escrito. Só quando
    nada disso aconteceu é que se pergunta se a pessoa se explicou mal — e
    acusar a equipe é a última hipótese, nunca a primeira.
    """
    if g["falhas"]:
        return "GERADOR"
    if g["colaterais"]:
        return "COLATERAL"
    if g["pedidos"] >= REPETICOES_PARA_GARGALO:
        return "ASSISTENTE"
    if g["pedidos"] > 1 and _vago(g["frases"][0]):
        return "PEDIDO"
    return "OK"


def _vago(frase):
    """A frase diz o bastante para alguém executar sem adivinhar?

    Curta demais ("cor", "8 4 6 7") ou sem verbo de ação e sem alvo. Não é
    julgamento de escrita: é a diferença entre um pedido executável e um que
    obriga o Assistente a chutar — e chute vira rodada perdida.
    """
    t = _sem_acento(frase).strip()
    if len(t.split()) <= 2:
        return True
    return intencao(frase) == "OUTRO"


def resumo(linhas):
    """Os números do topo da tela, para o mês inteiro de uma vez."""
    grupos = agrupar(linhas)
    ajustes = _acoes_de_ajuste(linhas)
    refeitas = sum(1 for l in ajustes
                   if "refazer" in _sem_acento(l.get("acao")))
    total_tent = sum(g["tentativas"] for g in grupos)
    por_diag = {}
    for g in grupos:
        por_diag[g["diagnostico"]] = por_diag.get(g["diagnostico"], 0) + \
            g["tentativas"]
    gargalos = [g for g in grupos
                if g["pedidos"] >= REPETICOES_PARA_GARGALO]
    return {
        "pedidos": len(ajustes),
        "tentativas": total_tent,
        "refeitas_do_zero": refeitas,
        "assuntos": len(grupos),
        "gargalos": len(gargalos),
        # Quantas tentativas foram gastas repetindo assunto já pedido antes.
        "tentativas_repetindo": sum(g["tentativas"] - 1 for g in grupos
                                    if g["pedidos"] > 1),
        "por_diagnostico": por_diag,
        "grupos": grupos,
    }


def por_pessoa(linhas):
    """Quanto cada pessoa gastou de tentativa, e quanto disso foi repetição.

    Serve para achar treinamento, não para cobrar ninguém: quem repete muito
    num assunto só precisa saber como pedir aquilo, e isso se ensina em cinco
    minutos.
    """
    fora = {}
    for g in agrupar(linhas):
        for u in (g["usuarios"] or ["?"]):
            d = fora.setdefault(u, {"usuario": u, "tentativas": 0,
                                    "pedidos": 0, "repetidos": 0,
                                    "por_intencao": {}})
            d["tentativas"] += g["tentativas"]
            d["pedidos"] += g["pedidos"]
            d["repetidos"] += max(0, g["pedidos"] - 1)
            d["por_intencao"][g["intencao"]] = \
                d["por_intencao"].get(g["intencao"], 0) + g["tentativas"]
    return sorted(fora.values(), key=lambda d: -d["tentativas"])


def por_intencao(linhas):
    """Em que assunto o trabalho se perde. Ordenado pelo mais caro."""
    fora = {}
    for g in agrupar(linhas):
        d = fora.setdefault(g["intencao"], {"intencao": g["intencao"],
                                            "tentativas": 0, "pedidos": 0,
                                            "falhas": 0, "colaterais": 0})
        d["tentativas"] += g["tentativas"]
        d["pedidos"] += g["pedidos"]
        d["falhas"] += g["falhas"]
        d["colaterais"] += g["colaterais"]
    return sorted(fora.values(), key=lambda d: -d["tentativas"])


# ── Conferência ──────────────────────────────────────────────────────────────
# `python3 gargalos.py`. O caso principal é a conversa REAL do produto "Meia Pé
# de Galinha", de 22/09/2026 — a mesma que o dono mandou. Log inventado provaria
# que a conta bate com ela mesma; este log tem os erros de digitação, os
# pedidos de duas palavras e as falhas de verdade.
if __name__ == "__main__":
    falhas_teste = 0

    def ok(nome, cond):
        global falhas_teste
        falhas_teste += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # ── a intenção, escrita de todo jeito ────────────────────────────────
    ok("'tira essa cor ocre' é COR",
       intencao("na imagem 5 tira essa cor ocre e so deixei a branca") == "COR")
    ok("'as meias não sao amarela e sim laranja' é COR",
       intencao("chat as meias não sao amarela e sim laranja") == "COR")
    ok("'muda as cores da meia' é COR",
       intencao("quero que voce mude as cores da meia onde esta amarelo "
                "colocar laranja") == "COR")
    ok("'cor' sozinho é COR", intencao("cor") == "COR")
    ok("erro de digitação não atrapalha",
       intencao("e na iamgem 7 colocquqe a cir da meia larnja") == "COR")

    # Esta frase fala do texto do card, mas o assunto dela E cor — e agrupar
    # com os outros pedidos de cor e o comportamento certo para a tela.
    ok("card que fala de cor agrupa com COR",
       intencao("que esta escrito amarelo branco e preto") == "COR")
    ok("card sem cor e TEXTO",
       intencao("não é tamanho unico e sim do 38 ao 43") == "TEXTO")
    ok("numeração é TEXTO",
       intencao("não é tamanho unico e sim do 38 ao 43") == "TEXTO")
    ok("cenário é CENARIO",
       intencao("em vez de voce colocar encma da cama coloque em uma "
                "academia") == "CENARIO")
    ok("anatomia é ANATOMIA",
       intencao("tira esse 3 e que ta estranho ne") == "ANATOMIA")
    ok("dedo é ANATOMIA",
       intencao("os pe da meia esta esranho arruma sao so 3 dedos")
       == "ANATOMIA")
    ok("referência é REFERENCIA",
       intencao("quero que voce faça a image 6 igual a uma que vou te "
                "mandaar de refenrecia") == "REFERENCIA")
    ok("remover puro é REMOVER",
       intencao("retira esse bloco de baixo") == "REMOVER")
    ok("frase sem assunto conhecido é OUTRO", intencao("cade que demora")
       == "OUTRO")

    # ── os números da imagem ─────────────────────────────────────────────
    ok("pega os números soltos", imagens_citadas("8 4 6 7") == [8, 4, 6, 7])
    ok("pega dentro da frase",
       imagens_citadas("na imagen 6 e 7 e a 8") == [6, 7, 8])
    ok("medida grande não vira imagem",
       imagens_citadas("so deixa a altura de 40 cm") == [])

    # ── tentativas e desfecho, lidos do que o Studio já escreve ──────────
    ok("'na 2ª tentativa' conta duas", tentativas("✅ ok (na 2ª tentativa)")
       == 2)
    ok("'em 2 tentativa(s)' conta duas",
       tentativas("❌ não consegui fazer em 2 tentativa(s)") == 2)
    ok("sem marca conta uma", tentativas("✅ feito") == 1)
    ok("o ❌ é falha", desfecho("❌ não consegui fazer") == "falhou")
    ok("o ⚠️ é colateral",
       desfecho("✅ feito ⚠️ Mudou também, sem ter sido pedido: o "
                "enquadramento") == "colateral")
    ok("só o ✅ é ok", desfecho("✅ feito") == "ok")

    # ── a conversa real ──────────────────────────────────────────────────
    P = "Meia Pé de Galinha"

    def L(h, u, img, acao, instr, res=""):
        return {"quando": f"22/09/2026 {h}", "usuario": u, "produto": P,
                "acao": acao, "imagem": img, "tipo": "", "instrucao": instr,
                "resultado": res}

    LOG = [
        L("09:00", "Beatriz", "", "gerar_tudo", "", "8 imagem(ns) a gerar"),
        L("09:12", "Beatriz", 5, "ajuste_aplicado",
          "anlise a imagem 5 e retira a largurae o peso so deixa a altura de "
          "40 cm",
          "✅ restaram os dois cards ⚠️ Mudou também, sem ter sido pedido: a "
          "meia ficou levemente maior"),
        L("09:20", "Beatriz", 5, "refazer_uma",
          "da onde voe tirou essa cara de galinha na imagem 5", "🔁 refeita"),
        L("09:31", "Beatriz", 5, "ajuste_aplicado",
          "na iamgem 5 tira essa cor ocre e so deixei a branca amarelo e oreto",
          "✅ card trocado ⚠️ Mudou também, sem ter sido pedido: a meia "
          "deslocada"),
        L("09:48", "Beatriz", 7, "refazer_uma",
          "quero que você melhore essa foto de pressente esta muito simples",
          "🔁 refeita"),
        L("10:02", "Beatriz", 7, "ajuste_aplicado",
          "nada haver esas laranja q voe coloco na foto de presente",
          "✅ removidas ⚠️ Mudou também, sem ter sido pedido: a cena "
          "recomposta ❌ Texto com erro de português em 2 tentativa(s)"),
        L("10:20", "Beatriz", 8, "refazer_uma",
          "essa imagem 8 em vez de voce colocar encma da cama coloque em uma "
          "academia", "🔁 refeita"),
        L("10:26", "Beatriz", 8, "refazer_uma",
          "ficou bom orem tira esse 3 e que ta estranho ne", "🔁 refeita"),
        # A virada: a cor estava errada na origem.
        L("10:40", "Beatriz", "", "ajuste_aplicado",
          "chat as meias não sao amarela e sim laranja", ""),
        L("10:41", "Beatriz", 1, "ajuste_aplicado",
          "na 1 na 3 6 e pricinamente na 5",
          "✅ laranja (na 2ª tentativa) ⚠️ Mudou também, sem ter sido pedido: "
          "enquadramento afastado"),
        L("10:41", "Beatriz", 3, "ajuste_aplicado",
          "na 1 na 3 6 e pricinamente na 5",
          "❌ não consegui fazer em 2 tentativa(s)"),
        L("10:41", "Beatriz", 5, "ajuste_aplicado",
          "na 1 na 3 6 e pricinamente na 5",
          "❌ não consegui fazer em 2 tentativa(s)"),
        L("10:41", "Beatriz", 6, "ajuste_aplicado",
          "na 1 na 3 6 e pricinamente na 5",
          "❌ não consegui fazer em 2 tentativa(s)"),
        L("10:55", "Beatriz", 5, "ajuste_aplicado",
          "eu reciso que voce faça a mesma cor laranja das ooutras fotos",
          "❌ não consegui fazer em 2 tentativa(s)"),
        L("11:10", "Beatriz", 5, "refazer_uma",
          "cade meu amigo qe dfficuldade quero que voce mude as cores da meia "
          "onde esta amarelo colocar laranja", "🔁 refeita"),
        L("11:30", "Beatriz", 5, "refazer_uma",
          "eu pedi pra voce trocar a cor e nao alterar a image", "🔁 refeita"),
        L("11:45", "Beatriz", 7, "ajuste_aplicado",
          "e na iamgem 7 colocquqe a cir da meia larnja em vez de amarelo",
          "✅ laranja (na 2ª tentativa) ⚠️ Mudou também, sem ter sido pedido: "
          "a cena mais afastada"),
        L("11:50", "Beatriz", "", "ajuste_aplicado", "cor", ""),
        L("11:58", "Beatriz", "", "ajuste_aplicado", "8 4 6 7", ""),
        L("12:20", "Beatriz", 6, "ajuste_aplicado",
          "quero que na imagem 6 voce tira que cabe em qualquer pe a "
          "numerração e de 38 ao 43",
          "✅ trocado ⚠️ Mudou também, sem ter sido pedido: foto reenquadrada"),
        L("12:35", "Beatriz", 6, "ajuste_aplicado",
          "na iamgem 6 reira essa arte da numeração pq ja tem na imagem 2",
          "✅ removido ⚠️ Mudou também, sem ter sido pedido: cartões "
          "reposicionados"),
    ]

    r = resumo(LOG)
    ok("a geração inicial não conta como gargalo", r["pedidos"] == len(LOG) - 1)
    ok("as refeitas do zero são contadas", r["refeitas_do_zero"] == 6)
    ok("as tentativas somam mais que os pedidos",
       r["tentativas"] > r["pedidos"])

    # A pergunta central: qual assunto custou mais?
    top = por_intencao(LOG)[0]
    ok("o assunto mais caro do dia foi COR", top["intencao"] == "COR")
    ok("e ele concentra as falhas do gerador", top["falhas"] >= 4)

    ok("a mensagem que é só número herda o assunto anterior",
       _so_numeros("na 1 na 3 6 e pricinamente na 5")
       and _so_numeros("8 4 6 7"))
    ok("frase com assunto não é só número",
       not _so_numeros("na imagem 6 tira a numeração"))

    # O agrupamento tem que juntar frases que não se parecem.
    g5 = [g for g in agrupar(LOG)
          if g["imagem"] == "5" and g["intencao"] == "COR"]
    ok("as cinco frases de cor da imagem 5 viram UM assunto", len(g5) == 1)
    ok("e o assunto acusa a repetição", g5[0]["pedidos"] >= 4)
    ok("com o tempo que levou", g5[0]["minutos"] > 100)
    ok("e guarda as frases originais para o dono ler", len(g5[0]["frases"]) >= 4)

    # O diagnóstico, que é a pergunta do dono.
    ok("falha explícita do gerador é do GERADOR",
       g5[0]["diagnostico"] == "GERADOR")
    g_texto = [g for g in agrupar(LOG)
               if g["imagem"] == "6" and g["intencao"] == "TEXTO"]
    ok("pedido atendido que quebrou outra coisa é COLATERAL",
       g_texto and g_texto[0]["diagnostico"] == "COLATERAL")

    # "cor" e "8 4 6 7" são os pedidos vagos do log real.
    ok("'cor' é pedido vago", _vago("cor"))
    ok("'8 4 6 7' é pedido vago", _vago("8 4 6 7"))
    ok("uma frase com assunto e alvo não é vaga",
       not _vago("na imagem 6 tira a numeração e coloca do 38 ao 43"))

    # Por pessoa: serve para achar treinamento, e precisa dizer em QUÊ.
    p = por_pessoa(LOG)
    ok("a pessoa aparece com o total dela", p and p[0]["usuario"] == "Beatriz")
    ok("e com o assunto em que ela mais repetiu", "COR" in p[0]["por_intencao"])

    # ── bordas ───────────────────────────────────────────────────────────
    ok("log vazio não quebra", resumo([])["pedidos"] == 0)
    ok("linha sem instrução é ignorada",
       resumo([L("09:00", "x", 1, "ajuste_aplicado", "")])["pedidos"] == 0)
    ok("carimbo ilegível não derruba o grupo",
       agrupar([{"quando": "?", "usuario": "x", "produto": "p", "imagem": 1,
                 "acao": "ajuste_aplicado", "instrucao": "muda a cor",
                 "resultado": ""}])[0]["minutos"] == 0.0)

    print("\nfalhas:", falhas_teste)
    raise SystemExit(falhas_teste)
