"""medir_imagem.py — conferir a IMAGEM, e não só o código que a pediu.

A COBRANÇA QUE ORIGINOU ESTE ARQUIVO
-------------------------------------
O dono: *"Eu testo o código, não a imagem. Você precisa conferir isso!!!"*

Ele está certo. Todo teste desta base conferia que o prompt tinha a frase
certa. Se a frase produzia a foto certa, ninguém sabia — descobria-se pela
colaboradora, depois de gerada e paga.

Parte disso é mensurável sem IA nenhuma, em milissegundos, e é a parte que
mais apareceu nos relatos:

    faixa lateral      o quadro tem barra lisa na borda
    formato            veio retangular em vez de quadrado
    ocupação           o produto é uma manchinha no meio, ou estoura o quadro

O QUE ELE NÃO MEDE, E ISSO PRECISA SER DITO
--------------------------------------------
Fidelidade ao produto — se a haste do cinzeiro virou três cilindros grossos —
NÃO se mede por geometria. Isso continua sendo a conferência por visão do
`conferir_ajuste`, que olha a imagem com um modelo. Aqui é só o que uma régua
resolve, e é honesto dizer onde a régua acaba.

POR QUE SEM IA
--------------
Esta medição roda a cada imagem gerada. Chamar um modelo para medir margem
custaria mais que a própria geração em alguns casos, e demoraria. Pixel é
determinístico: a mesma imagem dá o mesmo número toda vez, e isso é o que
permite REPETIR automaticamente antes de entregar.
"""

import io

# Quanto a borda pode variar e ainda ser considerada "faixa lisa". Faixa de
# preenchimento é cor chapada; foto real tem ruído. 6 de 255 separa as duas
# sem acusar um fundo de estúdio bem iluminado.
TOLERANCIA_FAIXA = 6

# A partir de quantos por cento do lado a faixa deixa de ser borda de
# composição e vira defeito. 1,5% de 1200px são 18px — abaixo disso ninguém
# vê, acima disso é a "margem" que o dono reclamou.
FAIXA_MINIMA_PCT = 1.5

# Fora desta janela o produto está pequeno demais ou estourando o quadro.
# Só vale para peça de fundo limpo: em cena ambientada a escala é a real, e
# medir ocupação ali seria repetir o erro que fez o produto ficar gigante.
#
# O MÍNIMO COMEÇOU EM 35% E ESTAVA ERRADO.
#
# 35% deixava passar exatamente a capa que o dono reclamou: produtinho no meio
# de um quadro branco vazio. A frase dele é a medida: "ele tem que preencher o
# máximo possível da dimensão da imagem". Numa foto limpa, sem texto e sem
# cenário, não há nada dividindo espaço — 70% é o piso do aceitável.
#
# O que o PROMPT pede é outro número, de propósito mais apertado, e ele mora
# em `imagem.OCUPACAO` — não copie o valor para cá. Foi copiar porcentagem de
# um lugar para outro que pôs três medidas contrárias no mesmo prompt.
OCUPACAO_MINIMA_PCT = 70.0
OCUPACAO_MAXIMA_PCT = 96.0


def _abrir(dados):
    from PIL import Image
    return Image.open(io.BytesIO(dados)).convert("RGB")


def formato(dados):
    """(largura, altura, é_quadrada). (0, 0, False) quando não abre."""
    try:
        im = _abrir(dados)
    except Exception:
        return 0, 0, False
    w, h = im.size
    return w, h, w == h


def _linha_uniforme(px, w, y, tol):
    base = px[0, y]
    for x in range(1, w, max(1, w // 64)):
        c = px[x, y]
        if (abs(c[0] - base[0]) > tol or abs(c[1] - base[1]) > tol
                or abs(c[2] - base[2]) > tol):
            return False
    return True


def _coluna_uniforme(px, h, x, tol):
    base = px[x, 0]
    for y in range(1, h, max(1, h // 64)):
        c = px[x, y]
        if (abs(c[0] - base[0]) > tol or abs(c[1] - base[1]) > tol
                or abs(c[2] - base[2]) > tol):
            return False
    return True


def faixas(dados, tolerancia=TOLERANCIA_FAIXA):
    """{'esq','dir','topo','baixo'} em pixels de faixa lisa em cada borda.

    Uma faixa lisa na borda é o rastro de preenchimento: a arte veio 4:5, o
    Studio encaixou no quadrado e sobrou barra dos dois lados. Foi o que o
    dono viu — "faixas azul-claras nas laterais das imagens 2, 3, 4, 6, 7 e 8".

    Fundo branco de estúdio TAMBÉM é liso, e por isso a medida sozinha não
    acusa: quem decide é `problemas()`, que só chama isto quando o tipo da
    peça não é de fundo chapado.
    """
    try:
        im = _abrir(dados)
    except Exception:
        return {"esq": 0, "dir": 0, "topo": 0, "baixo": 0}
    w, h = im.size
    px = im.load()
    fora = {}
    x = 0
    while x < w and _coluna_uniforme(px, h, x, tolerancia):
        x += 1
    fora["esq"] = x
    x = w - 1
    n = 0
    while x >= 0 and _coluna_uniforme(px, h, x, tolerancia):
        x -= 1
        n += 1
    fora["dir"] = n
    y = 0
    while y < h and _linha_uniforme(px, w, y, tolerancia):
        y += 1
    fora["topo"] = y
    y = h - 1
    n = 0
    while y >= 0 and _linha_uniforme(px, w, y, tolerancia):
        y -= 1
        n += 1
    fora["baixo"] = n
    # Imagem inteiramente lisa: não são quatro faixas, é uma imagem em branco.
    if fora["esq"] >= w or fora["topo"] >= h:
        return {"esq": 0, "dir": 0, "topo": 0, "baixo": 0, "chapada": True}
    return fora


def caixa_do_assunto(dados, tolerancia=12):
    """(x0, y0, x1, y1) do que NÃO é da cor do canto. None quando não dá.

    É a mesma medida que `ocupacao` usava por dentro, agora com nome próprio:
    quem enquadra precisa da CAIXA, e quem mede precisa da porcentagem. Duas
    contas separadas da mesma coisa acabariam discordando.

    Atenção ao que a caixa CONTÉM: numa peça de marketing, o painel de texto
    lateral também difere do fundo, então ele entra na caixa. É por isso que
    recortar em volta dela preserva o texto — o recorte cego de antes decepava
    justamente essas frases.
    """
    try:
        im = _abrir(dados)
    except Exception:
        return None
    w, h = im.size
    px = im.load()
    fundo = px[0, 0]

    def _difere(c):
        return (abs(c[0] - fundo[0]) > tolerancia
                or abs(c[1] - fundo[1]) > tolerancia
                or abs(c[2] - fundo[2]) > tolerancia)

    passo = max(1, min(w, h) // 200)
    x0, y0, x1, y1 = w, h, -1, -1
    for y in range(0, h, passo):
        for x in range(0, w, passo):
            if _difere(px[x, y]):
                x0, y0 = min(x0, x), min(y0, y)
                x1, y1 = max(x1, x), max(y1, y)
    if x1 < 0:
        return None
    # O passo pula pixels: devolve a caixa com a folga de um passo, para não
    # cortar a borda do assunto por causa da amostragem.
    return (max(0, x0 - passo), max(0, y0 - passo),
            min(w - 1, x1 + passo), min(h - 1, y1 + passo))


def ocupacao(dados, tolerancia=12):
    """Quanto do quadro o assunto ocupa, em %. None quando não dá para medir.

    Só faz sentido em peça de fundo limpo; numa cena ambientada o "fundo" tem
    conteúdo e a caixa daria o quadro inteiro.
    """
    caixa = caixa_do_assunto(dados, tolerancia)
    if not caixa:
        return None
    try:
        w, h = _abrir(dados).size
    except Exception:
        return None
    x0, y0, x1, y1 = caixa
    return round(max((x1 - x0) / w, (y1 - y0) / h) * 100.0, 1)


# ── TEXTO CORTADO PELA BORDA — O QUE ELE PARECE, EM PIXEL ─────────────────
#
# Dono, 30/09: "imagem 2 e imagem 5 com texto cortando (...) elas sao aplicadas
# numa regiao que nao da para ser escrita totalmente e ai fica a margem para
# fora, quadrados para fora". E depois, duas vezes: "os textos cortados foram
# corrigidos na causa raiz?".
#
# A resposta honesta era NAO enquanto esta funcao nao existisse: a regua
# conferia formato, faixa lisa e ocupacao, e ninguem olhava se o texto tinha
# ficado inteiro dentro do quadro. Tirar a contradicao do prompt e tratar a
# causa; sem medir o resultado, e hipotese.
#
# COMO SE RECONHECE, E POR QUE NAO E O OBVIO
#
# A primeira versao contou as trocas claro/escuro na coluna da borda. Medido:
#
#   painel inteiro dentro ....... 0 trocas
#   painel cortado .............. 8 a 14 trocas
#   AMBIENTACAO (ruido ate a borda) 469 trocas
#
# Ou seja: a medida obvia acusaria TODA ambientacao — verificador que da
# alarme falso ensina a ignora-lo. O que separa os dois nao e a quantidade de
# troca: e que o cartao cortado e um bloco de DUAS CORES (o cartao claro e o
# glifo escuro), enquanto a cena e um continuo. Medido na mesma bateria:
#
#   caso                 tom dominante  e claro?  pixels escuros
#   inteiro dentro ..... 100%           sim       0
#   cortado ............ 94 a 95%       sim       56 a 73
#   ambientacao ........ 28%            NAO       456
#
# Os limites abaixo saem desses numeros, com folga dos dois lados.
DOMINANTE_MINIMA_PCT = 70    # medido: 94-95 no defeito, 28 na ambientacao
ESCUROS_MINIMOS = 20         # medido: 56-73 no defeito, 0 quando esta inteiro
TROCAS_MINIMAS = 4           # medido: 8-14 no defeito, 0 quando esta inteiro
_NIVEL_CLARO = 5             # em passos de 32: 5 -> 160 de luminancia
_NIVEL_ESCURO = 2            # 2 -> ate 95


def texto_na_borda(dados):
    """{'esq','dir','topo','baixo'}: True onde ha cartao de texto cortado.

    Funcao pura. So faz sentido em peca COM texto — numa capa ou numa
    ambientacao o que encosta na borda e produto ou cenario, e acusar ali
    seria alarme falso. Quem sabe disso e quem chama.
    """
    try:
        im = _abrir(dados).convert("L")
    except Exception:
        return {}
    w, h = im.size
    px = im.load()

    def _corta(valores):
        if not valores:
            return False
        q = [v // 32 for v in valores]
        trocas = sum(1 for a, b in zip(q, q[1:]) if a != b)
        escuros = sum(1 for v in q if v <= _NIVEL_ESCURO)
        dominante = max(set(q), key=q.count)
        dom_pct = 100.0 * q.count(dominante) / len(q)
        # UM CARTAO: fundo claro dominando a borda, com glifo escuro dentro.
        return (dominante >= _NIVEL_CLARO
                and dom_pct >= DOMINANTE_MINIMA_PCT
                and escuros >= ESCUROS_MINIMOS
                and trocas >= TROCAS_MINIMAS)

    return {
        "esq": _corta([px[0, y] for y in range(h)]),
        "dir": _corta([px[w - 1, y] for y in range(h)]),
        "topo": _corta([px[x, 0] for x in range(w)]),
        "baixo": _corta([px[x, h - 1] for x in range(w)]),
    }


# ── A PECA SE PARECE COM O PRODUTO DAS FOTOS? ─────────────────────────────
#
# Dono, 30/09: "por que que as imagens acabam sendo geradas diferente do que o
# produto de fato e, onde que esta o erro para ele ser corrigido?". E, duas
# vezes: "foram corrigidos NA CAUSA RAIZ?".
#
# A resposta era NAO enquanto isto nao existisse. O Studio manda "TRAVA DE COR
# (regra inviolavel)" e "PROIBICAO ABSOLUTA: JAMAIS substitua o produto das
# fotos" — e entregava sem NUNCA comparar a peca com as fotos. Regra que
# ninguem confere e torcida, nao regra.
#
# O QUE ESTA MEDIDA VE, E O QUE ELA NAO VE
#
# Ela compara a PALETA DO ASSUNTO: recorta a caixa do assunto dos dois lados,
# quantiza a cor em passos de 48 e mede quanto da paleta da foto reaparece na
# peca. Pega o defeito mais relatado e mais caro — o produto repintado, a cor
# trocada, o objeto substituido por outro de cor diferente.
#
# Ela NAO ve forma: produto da cor certa e formato errado passa. Isso esta
# declarado no ACHADOS_ABERTOS.md — responder forma exige visao, e visao custa
# uma chamada paga por peca. Medida barata que pega o caso comum vale mais que
# medida cara que ninguem liga.
#
# OS LIMITES SAIRAM DE MEDICAO, e a bateria esta no auto-teste:
#
#   mesma cor, mesma forma ................. 99%
#   mesma cor, forma diferente ............. 75%
#   produto tricolor reproduzido ........... 94%
#   foto limpa x peca ambientada, mesma cor  75%
#   ---------------------------------------------
#   tricolor virou monocromatico ........... 30%
#   cor trocada ............................ 21%
#   cor trocada, peca ambientada ............  0%
#
# O piso fica em 45: folga de 30 pontos para o pior caso legitimo e de 15 para
# o melhor caso defeituoso.
PARECENCA_MINIMA_PCT = 45
_PASSO_COR = 48
_MAX_FOTOS_COMPARADAS = 3


def paleta_do_assunto(dados, cores=6):
    """[(cor_quantizada, pct)] do ASSUNTO — nao do quadro inteiro.

    Recortar a caixa do assunto e o que faz a medida funcionar numa peca
    ambientada: sem isso, a paleta seria a do cenario, e cenario e livre.
    """
    try:
        im = _abrir(dados).convert("RGB")
    except Exception:
        return []
    caixa = caixa_do_assunto(dados)
    if caixa:
        try:
            im = im.crop(caixa)
        except Exception:
            pass
    try:
        im = im.resize((64, 64))
    except Exception:
        return []
    from collections import Counter
    q = [(r // _PASSO_COR, g // _PASSO_COR, b // _PASSO_COR)
         for r, g, b in im.getdata()]
    if not q:
        return []
    return [(c, 100.0 * n / len(q)) for c, n in Counter(q).most_common(cores)]


def parecenca(peca, foto):
    """Quanto da paleta do assunto da FOTO reaparece na PECA, em %.

    Funcao pura. 0 quando nao da para medir um dos dois — e quem chama
    decide o que fazer com isso, porque "nao consegui medir" nao e "esta
    errado" (acusar o inocente e pior que nao medir).
    """
    p_foto = paleta_do_assunto(foto)
    p_peca = {c for c, _ in paleta_do_assunto(peca)}
    if not p_foto or not p_peca:
        return None
    return sum(pct for c, pct in p_foto if c in p_peca)


def produto_diferente(peca, fotos):
    """O aviso quando a peca nao se parece com NENHUMA das fotos, ou "".

    NENHUMA, e nao "a primeira": as fotos mostram angulos e recortes
    diferentes do mesmo produto, e uma delas pode ser um detalhe. Basta a
    peca casar com uma para a trava de cor ter sido respeitada.
    """
    notas = []
    for foto in (fotos or [])[:_MAX_FOTOS_COMPARADAS]:
        n = parecenca(peca, foto)
        if n is not None:
            notas.append(n)
    if not notas:
        return ""
    melhor = max(notas)
    if melhor >= PARECENCA_MINIMA_PCT:
        return ""
    return (f"o produto da peca nao bate com as fotos: so {melhor:.0f}% da cor "
            f"do produto reapareceu (minimo {PARECENCA_MINIMA_PCT}%)")


def problemas(dados, fundo_chapado=False, ambientada=False,
              com_texto=False):
    """O que está errado nesta imagem, em português. [] quando está boa.

    `ambientada` desliga a checagem de ocupação: numa cena a escala do
    produto é a REAL, e exigir que ele encha o quadro foi exatamente o que
    produziu o produto gigante que o dono reclamou.

    `com_texto` LIGA a checagem de texto cortado, e só ela: numa capa ou numa
    ambientação o que encosta na borda é produto ou cenário, e acusar ali
    seria alarme falso.
    """
    fora = []
    w, h, quadrada = formato(dados)
    if not w:
        return ["não consegui abrir a imagem"]
    if not quadrada:
        fora.append(f"veio {w}x{h} em vez de quadrada")

    if not fundo_chapado:
        f = faixas(dados)
        limite = max(4, int(min(w, h) * FAIXA_MINIMA_PCT / 100))
        for lado, nome in (("esq", "esquerda"), ("dir", "direita"),
                           ("topo", "topo"), ("baixo", "base")):
            if f.get(lado, 0) >= limite:
                fora.append(f"faixa lisa de {f[lado]}px na {nome}")

    if com_texto:
        # UMA medicao, e nao uma por lado: `texto_na_borda` abre a imagem e
        # varre as quatro bordas de uma vez. Chamar dentro do laco a abriria
        # quatro vezes por peca.
        _bordas = texto_na_borda(dados)
        for lado, nome in (("esq", "esquerda"), ("dir", "direita"),
                           ("topo", "topo"), ("baixo", "base")):
            if _bordas.get(lado):
                fora.append(f"texto cortado pela borda {nome}")

    if fundo_chapado and not ambientada:
        oc = ocupacao(dados)
        if oc is not None:
            if oc < OCUPACAO_MINIMA_PCT:
                fora.append(f"o produto ocupa só {oc:.0f}% do quadro")
            elif oc > OCUPACAO_MAXIMA_PCT:
                fora.append(f"o produto ocupa {oc:.0f}% e está estourando "
                            "o quadro")
    return fora


# ── Conferência ──────────────────────────────────────────────────────────────
# `python3 medir_imagem.py`. As imagens são montadas aqui mesmo, com defeito
# conhecido: é a única forma de provar que a régua mede o que diz medir.
if __name__ == "__main__":
    import sys
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    from PIL import Image, ImageDraw

    def _png(im):
        b = io.BytesIO()
        im.save(b, format="PNG")
        return b.getvalue()

    def _com_faixa(lado_px, cor=(232, 238, 245)):
        """O defeito real: arte 4:5 encaixada em 1200x1200, barra dos dois
        lados, na cor de marca que o Studio usa para preencher.

        A ARTE PRECISA TER RUÍDO NOS DOIS EIXOS, e esse detalhe reprovou a
        primeira versão deste teste: eu desenhava listras VERTICAIS, então
        toda coluna da arte era uniforme e a medição achava que a imagem
        inteira era faixa. O defeito estava no teste, não na régua — e foi o
        teste que me mostrou isso.
        """
        import random
        random.seed(7)
        im = Image.new("RGB", (1200, 1200), cor)
        larg = 1200 - 2 * lado_px
        arte = Image.new("RGB", (larg, 1200), (10, 10, 10))
        px_a = arte.load()
        for y in range(0, 1200, 3):
            for x in range(0, larg, 3):
                v = random.randint(20, 200)
                for dy in range(3):
                    for dx in range(3):
                        if x + dx < larg and y + dy < 1200:
                            px_a[x + dx, y + dy] = (v, (v * 3) % 255, 90)
        im.paste(arte, (lado_px, 0))
        return _png(im)

    def _limpa(ocupa_pct):
        im = Image.new("RGB", (1200, 1200), (255, 255, 255))
        lado = int(1200 * ocupa_pct / 100)
        c = (1200 - lado) // 2
        d = ImageDraw.Draw(im)
        d.ellipse([c, c, c + lado, c + lado], fill=(20, 20, 20))
        return _png(im)

    # ── formato ──────────────────────────────────────────────────────────
    ok("quadrada e reconhecida", formato(_limpa(50))[2])
    _ret = _png(Image.new("RGB", (1536, 1024), (255, 255, 255)))
    ok("retangular e acusada", not formato(_ret)[2])
    ok("e o tamanho vem junto", formato(_ret)[:2] == (1536, 1024))
    ok("lixo nao derruba", formato(b"nao sou imagem") == (0, 0, False))

    # ── a faixa que o dono viu ───────────────────────────────────────────
    f = faixas(_com_faixa(120))
    ok("a faixa da esquerda e medida", 110 <= f["esq"] <= 130)
    ok("a da direita tambem", 110 <= f["dir"] <= 130)
    ok("e o topo continua limpo", f["topo"] < 5)

    # ── O TEXTO CORTADO PELA BORDA ───────────────────────────────────────
    #
    # As imagens sao montadas aqui com o defeito REAL: um painel de texto que
    # comeca fora do quadro, como o dono descreveu — "os titulos aparecem
    # como 'TE DE MEDIDA / ISO'".
    def _fonte_t(tam):
        from PIL import ImageFont
        for c in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(c, tam)
            except Exception:
                pass
        return ImageFont.load_default()

    def _peca_com_texto(x_painel):
        """Peca de marketing: produto a direita, tres cartoes a esquerda.

        `x_painel` negativo = o painel comeca fora do quadro, que e o defeito.
        """
        im = Image.new("RGB", (1200, 1200), (235, 230, 220))
        d = ImageDraw.Draw(im)
        d.ellipse([620, 400, 1100, 880], fill=(40, 90, 150))
        f = _fonte_t(54)
        for i, txt in enumerate(("FITA DE MEDIDA", "PRECISO", "ATE 150 MM")):
            y = 260 + i * 180
            d.rounded_rectangle([x_painel, y, x_painel + 470, y + 130], 18,
                                fill=(255, 255, 255))
            d.text((x_painel + 28, y + 40), txt, font=f, fill=(20, 20, 20))
        return _png(im)

    def _ambientada_ruidosa():
        """Cena com ruido ate a borda — o caso que a medida obvia acusaria."""
        import random
        random.seed(3)
        im = Image.new("RGB", (1200, 1200))
        px = im.load()
        for y in range(0, 1200, 2):
            for x in range(0, 1200, 2):
                v = random.randint(60, 210)
                for dy in range(2):
                    for dx in range(2):
                        px[x + dx, y + dy] = (v, int(v * 0.8), int(v * 0.6))
        ImageDraw.Draw(im).ellipse([400, 500, 800, 900], fill=(30, 30, 40))
        return _png(im)

    ok("painel inteiro dentro do quadro nao acusa nada",
       not any(texto_na_borda(_peca_com_texto(60)).values()))
    ok("painel que comeca fora do quadro e acusado na esquerda",
       texto_na_borda(_peca_com_texto(-120)).get("esq"))
    ok("e mesmo muito cortado continua sendo acusado",
       texto_na_borda(_peca_com_texto(-300)).get("esq"))
    ok("so a borda que tem o defeito e acusada",
       not any(texto_na_borda(_peca_com_texto(-120))[k]
               for k in ("dir", "topo", "baixo")))
    # O ALARME FALSO QUE A PRIMEIRA VERSAO DARIA.
    #
    # Contar trocas claro/escuro na borda acusava a ambientacao com 469
    # trocas — toda cena ambientada seria reprovada. Verificador que da
    # alarme falso e pior que nenhum: ensina a ignora-lo.
    ok("cena ambientada com ruido ate a borda NAO e acusada",
       not any(texto_na_borda(_ambientada_ruidosa()).values()))
    ok("e ela so e medida quando a peca TEM texto",
       not any("texto cortado" in p
               for p in problemas(_peca_com_texto(-120)))
       and any("texto cortado" in p
               for p in problemas(_peca_com_texto(-120), com_texto=True)))
    ok("lixo nao derruba a medida", texto_na_borda(b"nao sou imagem") == {})

    # ── A PECA SE PARECE COM O PRODUTO DAS FOTOS? ────────────────────────
    #
    # A bateria que produziu os limites da medida. Ela esta aqui inteira de
    # proposito: se alguem mexer no piso, tem de ver o que cada caso dava.
    def _prod(cor, forma="elipse"):
        im = Image.new("RGB", (900, 900), (250, 250, 250))
        d = ImageDraw.Draw(im)
        if forma == "elipse":
            d.ellipse([180, 180, 720, 720], fill=cor)
        else:
            d.rectangle([180, 180, 720, 720], fill=cor)
        return _png(im)

    def _tricolor(cores):
        im = Image.new("RGB", (900, 900), (250, 250, 250))
        d = ImageDraw.Draw(im)
        for i, c in enumerate(cores):
            d.rectangle([180 + i * 180, 300, 180 + (i + 1) * 180, 600], fill=c)
        return _png(im)

    def _ambientada(cor):
        """Produto sobre mesa de madeira, fundo com textura — o caso em que
        medir o QUADRO em vez do ASSUNTO daria alarme falso."""
        import random
        random.seed(11)
        im = Image.new("RGB", (900, 900), (150, 120, 90))
        px = im.load()
        for y in range(0, 900, 3):
            for x in range(0, 900, 3):
                v = random.randint(-25, 25)
                r, g, b = im.getpixel((x, y))
                for dy in range(3):
                    for dx in range(3):
                        px[x + dx, y + dy] = (max(0, min(255, r + v)),
                                              max(0, min(255, g + v)),
                                              max(0, min(255, b + v)))
        ImageDraw.Draw(im).ellipse([330, 330, 570, 570], fill=cor)
        return _png(im)

    _VERDE, _AZUL, _VERM = (40, 160, 70), (40, 70, 170), (200, 50, 40)

    ok("mesma cor e mesma forma: parecenca quase total",
       parecenca(_prod(_VERDE), _prod(_VERDE)) >= 90)
    ok("forma diferente com a cor certa ainda passa",
       parecenca(_prod(_VERDE, "quad"), _prod(_VERDE)) >= PARECENCA_MINIMA_PCT)
    ok("produto tricolor reproduzido passa",
       parecenca(_tricolor([_VERDE, _AZUL, _VERM]),
                 _tricolor([_VERDE, _AZUL, _VERM])) >= PARECENCA_MINIMA_PCT)
    # O DEFEITO: o produto repintado.
    ok("cor trocada e REPROVADA",
       parecenca(_prod(_AZUL), _prod(_VERDE)) < PARECENCA_MINIMA_PCT)
    ok("tricolor que virou monocromatico tambem",
       parecenca(_tricolor([_AZUL, _AZUL, _AZUL]),
                 _tricolor([_VERDE, _AZUL, _VERM])) < PARECENCA_MINIMA_PCT)
    # O ALARME FALSO QUE MEDIR O QUADRO INTEIRO DARIA: numa peca ambientada o
    # cenario domina os pixels. Recortar a caixa do assunto e o que salva.
    ok("peca ambientada com a cor certa NAO e acusada",
       parecenca(_ambientada(_VERDE), _prod(_VERDE)) >= PARECENCA_MINIMA_PCT)
    ok("e ambientada com a cor trocada e acusada",
       parecenca(_ambientada(_AZUL), _prod(_VERDE)) < PARECENCA_MINIMA_PCT)

    # BASTA CASAR COM UMA DAS FOTOS: elas sao angulos do mesmo produto, e uma
    # pode ser um detalhe de outra cor.
    ok("casar com a segunda foto ja basta",
       not produto_diferente(_prod(_VERDE), [_prod(_VERM), _prod(_VERDE)]))
    ok("nao casar com nenhuma vira aviso",
       "nao bate com as fotos" in produto_diferente(
           _prod(_AZUL), [_prod(_VERM), _prod(_VERDE)]))
    # NAO CONSEGUI MEDIR NAO E "ESTA ERRADO": acusar o inocente e pior que
    # nao medir, e foi assim que a primeira versao do checar_tela nasceu.
    ok("sem foto nenhuma nao acusa nada",
       produto_diferente(_prod(_AZUL), []) == "")
    ok("foto ilegivel nao acusa nada",
       produto_diferente(_prod(_AZUL), [b"nao sou imagem"]) == "")

    ok("120px de faixa viram problema",
       any("faixa" in p for p in problemas(_com_faixa(120))))
    ok("4px de borda NAO viram problema",
       not any("faixa" in p for p in problemas(_com_faixa(4))))

    # Fundo branco de estudio e liso de proposito: nao pode virar defeito.
    ok("peca de fundo chapado nao acusa faixa",
       not any("faixa" in p
               for p in problemas(_limpa(60), fundo_chapado=True)))

    # ── ocupacao ─────────────────────────────────────────────────────────
    ok("ocupacao de 60% e medida como ~60", 55 <= ocupacao(_limpa(60)) <= 65)
    ok("produto minusculo e acusado",
       any("ocupa" in p for p in problemas(_limpa(12), fundo_chapado=True)))
    ok("o piso e 70%, e nao os 35% que deixavam a capa passar",
       OCUPACAO_MINIMA_PCT == 70.0)
    ok("produto estourando tambem",
       any("estourando" in p
           for p in problemas(_limpa(97), fundo_chapado=True)))
    ok("ocupacao boa nao acusa nada",
       not problemas(_limpa(85), fundo_chapado=True))
    # A CAPA QUE O DONO RECLAMOU: produtinho no meio do branco.
    ok("capa com 40% do quadro e reprovada",
       any("ocupa" in p for p in problemas(_limpa(40), fundo_chapado=True)))
    ok("e com 65% tambem — 'o maximo possivel' e a medida dele",
       any("ocupa" in p for p in problemas(_limpa(65), fundo_chapado=True)))

    # A REGRA QUE FEZ O PRODUTO FICAR GIGANTE NAO PODE VOLTAR POR AQUI.
    ok("em cena ambientada a ocupacao NAO e cobrada",
       not any("ocupa" in p for p in
               problemas(_limpa(15), fundo_chapado=True, ambientada=True)))

    # ── bordas ───────────────────────────────────────────────────────────
    ok("imagem toda chapada nao vira quatro faixas",
       faixas(_png(Image.new("RGB", (100, 100), (1, 2, 3)))).get("chapada"))
    ok("imagem toda chapada nao tem ocupacao mensuravel",
       ocupacao(_png(Image.new("RGB", (100, 100), (1, 2, 3)))) is None)
    ok("lixo devolve um problema legivel",
       problemas(b"xxx") == ["não consegui abrir a imagem"])

    print("\nfalhas:", falhas)
    sys.exit(falhas)
