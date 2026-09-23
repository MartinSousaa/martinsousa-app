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
# cenário, não há nada dividindo espaço — 70% é o piso do aceitável, e o
# prompt pede de 80% a 92%.
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


def ocupacao(dados, tolerancia=12):
    """Quanto do quadro o assunto ocupa, em %, contra um fundo chapado.

    Mede a caixa que envolve tudo que NÃO é da cor do canto. Só faz sentido
    em peça de fundo limpo; numa cena ambientada o "fundo" tem conteúdo e a
    caixa daria o quadro inteiro. Devolve None quando não dá para medir.
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
    return round(max((x1 - x0) / w, (y1 - y0) / h) * 100.0, 1)


def problemas(dados, fundo_chapado=False, ambientada=False):
    """O que está errado nesta imagem, em português. [] quando está boa.

    `ambientada` desliga a checagem de ocupação: numa cena a escala do
    produto é a REAL, e exigir que ele encha o quadro foi exatamente o que
    produziu o produto gigante que o dono reclamou.
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
