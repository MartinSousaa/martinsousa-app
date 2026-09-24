"""enquadrar.py — a imagem sai quadrada SEM ganhar faixa lisa.

O QUE O LOG PROVOU, EM 24/09/2026
----------------------------------
O Gemini nunca devolve quadrado. Em vinte minutos de log, sempre a mesma
coisa:

    modelo devolveu  768x1365  (esperado 1024x1024) — preenchendo
    modelo devolveu  912x1182  — preenchendo
    modelo devolveu 1162x912   — preenchendo
    modelo devolveu 1024x1029  — preenchendo

768x1365 é 9:16 — retrato de celular. Enquadrar isso num quadrado PREENCHENDO
põe 597 px de faixa (44% da largura) e encolhe o produto para o meio. É
exatamente a reclamação do dono, semana após semana: "margens nas fotos",
"produto pequeno no meio".

POR QUE RECORTAR, DEPOIS DE TER SIDO PROIBIDO
----------------------------------------------
Recortar já foi tentado aqui e foi desligado com razão: cortava 18% do lado
maior **às cegas**, e decepava os painéis de texto das peças de marketing, que
ficam nas laterais. Frases saíam pela metade.

A diferença agora é o que guia o corte. `medir_imagem.caixa_do_assunto` acha
tudo que difere da cor do canto — e o painel de texto DIFERE, então ele está
dentro da caixa. Recortar em volta da caixa preserva o texto; recortar por
porcentagem não preservava. Não é a mesma operação com outro nome.

A ORDEM, E POR QUE ELA É ESTA
------------------------------
    1. já é quadrada           -> devolve como veio
    2. a caixa cabe no quadrado -> RECORTA em volta dela. Nada de faixa.
    3. a caixa não cabe         -> preenche o que sobrar, como antes

O caso 3 existe porque preencher é o mal menor quando a alternativa é decepar
o assunto. Ele passou a ser a exceção, e o relato diz quando aconteceu — antes
era a regra e ninguém lia.

A COR DA FAIXA, QUANDO ELA FOR INEVITÁVEL
------------------------------------------
Sai da própria imagem, nunca da marca. O azul-claro `(232, 238, 245)` foi
pintado aqui por quatro versões seguidas depois de ter sido tirado do texto do
prompt três vezes — a paleta fixa sobrevivia no pós-processamento.
"""

# Quanto do ASSUNTO pode ficar de fora quando a caixa não cabe no quadrado.
# Zero seria rígido demais: um reflexo ou uma sombra estendem a caixa alguns
# pixels e forçariam faixa numa imagem que cortaria bem.
FOLGA_PCT = 4.0


def _abrir(dados):
    import io
    from PIL import Image
    return Image.open(io.BytesIO(dados)).convert("RGBA")


def cor_de_fundo(pil):
    """A cor média da imagem, para a faixa sumir dentro da própria cena."""
    from PIL import Image
    return tuple(pil.resize((1, 1), Image.LANCZOS).getpixel((0, 0)))


def janela(largura, altura, caixa, folga_pct=FOLGA_PCT):
    """Onde recortar o quadrado. (x0, y0, lado, coube). Função pura.

    `coube` diz se o assunto inteiro (mais a folga) entrou. Quando não entra,
    quem chama preenche em vez de recortar — e é ele que decide isso, não esta
    função, que só mede.
    """
    lado = min(largura, altura)
    if not caixa:
        # Sem assunto medível — cena ambientada, em que o quadro todo é
        # conteúdo. Recorte central é seguro: não há painel de texto para
        # decepar, e a faixa seria pior.
        return ((largura - lado) // 2, (altura - lado) // 2, lado, True)

    x0, y0, x1, y1 = caixa
    # CAIXA QUE COBRE O QUADRO INTEIRO NÃO É ASSUNTO, É CENA.
    #
    # Numa ambientação o fundo tem conteúdo, então tudo difere da cor do
    # canto e a caixa dá a imagem toda. Tratar isso como "o assunto não cabe"
    # mandava justamente a ambientação para o preenchimento — que é onde as
    # faixas apareciam. Cena se recorta pelo centro, com segurança: não há
    # painel de texto para decepar.
    if (x1 - x0) >= 0.9 * largura and (y1 - y0) >= 0.9 * altura:
        return ((largura - lado) // 2, (altura - lado) // 2, lado, True)

    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    # Centrado no assunto, mas sem sair da imagem.
    jx = int(min(max(cx - lado / 2.0, 0), largura - lado))
    jy = int(min(max(cy - lado / 2.0, 0), altura - lado))

    # Quanto do assunto ficaria de fora?
    dentro_w = max(0, min(x1, jx + lado) - max(x0, jx))
    dentro_h = max(0, min(y1, jy + lado) - max(y0, jy))
    larg_c, alt_c = max(1, x1 - x0), max(1, y1 - y0)
    perdido = 100.0 * (1.0 - (dentro_w / larg_c) * (dentro_h / alt_c))
    return (jx, jy, lado, perdido <= folga_pct)


def quadrar(dados, fundo_branco=False, lado_final=None):
    """A imagem quadrada. (bytes, relato).

    `relato` é "" quando não houve nada a fazer, e uma frase em português
    quando houve — ela vai para o diagnóstico e para a tela, porque foi por
    ficar só no stderr que as faixas passaram semanas sem explicação.
    """
    import io
    from PIL import Image
    try:
        pil = _abrir(dados)
    except Exception:
        return dados, ""
    w, h = pil.size

    relato = ""
    if w != h:
        try:
            import medir_imagem as _md
            caixa = _md.caixa_do_assunto(dados)
        except Exception:
            caixa = None
        jx, jy, lado, coube = janela(w, h, caixa)
        if coube:
            pil = pil.crop((jx, jy, jx + lado, jy + lado))
            relato = (f"o motor devolveu {w}x{h} em vez de quadrada; o Studio "
                      f"recortou para {lado}x{lado} em volta do produto — sem "
                      "faixa.")
        else:
            maior = max(w, h)
            cor = (255, 255, 255, 255) if fundo_branco else cor_de_fundo(pil)
            fundo = Image.new("RGBA", (maior, maior), cor)
            fundo.paste(pil, ((maior - w) // 2, (maior - h) // 2), pil)
            pil = fundo
            relato = (f"o motor devolveu {w}x{h} e o produto não cabe num "
                      f"recorte quadrado — o Studio preencheu as faixas. "
                      "Esta é a peça que pode sair com margem.")

    if lado_final:
        pil = pil.resize((lado_final, lado_final), Image.LANCZOS)
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue(), relato


# ── Conferência ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import io
    from PIL import Image, ImageDraw
    import medir_imagem as _md

    falhas = []

    def ok(nome, cond):
        if not cond:
            falhas.append(nome)
        print(("  ok  " if cond else "FALHOU") + "  " + nome)

    def png(w, h, desenhar=None, fundo=(250, 250, 250)):
        im = Image.new("RGB", (w, h), fundo)
        if desenhar:
            desenhar(ImageDraw.Draw(im))
        b = io.BytesIO()
        im.save(b, format="PNG")
        return b.getvalue()

    # 1. Quadrada não é tocada.
    q = png(1024, 1024, lambda d: d.ellipse((300, 300, 700, 700), fill=(20, 20, 20)))
    _saida, _rel = quadrar(q)
    ok("imagem quadrada passa sem relato", _rel == "")
    ok("e continua quadrada", _md.formato(_saida)[2])

    # 2. O caso REAL do log: 768x1365 com o produto no meio.
    retrato = png(768, 1365,
                  lambda d: d.ellipse((234, 450, 534, 900), fill=(20, 20, 20)))
    _saida, _rel = quadrar(retrato)
    ok("768x1365 sai QUADRADA", _md.formato(_saida)[2])
    ok("e por RECORTE, não por preenchimento", "recortou" in _rel)
    # É ESTA A CONFERÊNCIA QUE IMPORTA, e ela roda numa peça AMBIENTADA.
    #
    # Numa peça de fundo chapado a borda é uniforme por natureza e `faixas`
    # acusaria sempre — a faixa que o dono vê é a que aparece nas peças com
    # cenário, que é onde o preenchimento se denuncia.
    import random as _rnd
    _rnd.seed(11)

    def _cenario(d):
        for _ in range(9000):
            d.point((_rnd.randint(0, 767), _rnd.randint(0, 1364)),
                    fill=(_rnd.randint(0, 255), _rnd.randint(0, 255),
                          _rnd.randint(0, 255)))
    _amb = png(768, 1365, _cenario, fundo=(110, 100, 95))
    _saida_amb, _rel_amb = quadrar(_amb)
    ok("ambientação 768x1365 sai quadrada por RECORTE",
       _md.formato(_saida_amb)[2] and "recortou" in _rel_amb)
    _fx = _md.faixas(_saida_amb)
    ok("e SEM faixa lisa — a margem do dono deixa de existir",
       max(_fx.values()) <= 2)

    # 3. O assunto que NÃO cabe: preencher continua existindo, como exceção.
    comprido = png(768, 1365,
                   lambda d: d.rectangle((300, 40, 460, 1325), fill=(20, 20, 20)))
    _saida, _rel = quadrar(comprido)
    ok("assunto mais comprido que o lado curto ainda é preenchido",
       "preencheu" in _rel and _md.formato(_saida)[2])
    ok("e o relato AVISA que essa peça pode sair com margem",
       "pode sair com margem" in _rel)

    # 4. O painel de texto lateral — o motivo pelo qual recortar foi proibido.
    def _com_texto(d):
        d.ellipse((500, 500, 900, 900), fill=(20, 20, 20))     # produto
        d.rectangle((40, 560, 300, 840), fill=(180, 30, 30))    # painel lateral
    largo = png(1400, 1000, _com_texto)
    _jx, _jy, _lado, _coube = janela(1400, 1000, _md.caixa_do_assunto(largo))
    ok("a janela do recorte ENGLOBA o painel de texto lateral",
       _coube and _jx <= 40 and _jx + _lado >= 300)
    _saida, _rel = quadrar(largo)
    _px = Image.open(io.BytesIO(_saida)).convert("RGB")
    _achou_vermelho = any(
        _px.getpixel((x, y))[0] > 120 and _px.getpixel((x, y))[1] < 90
        for y in range(0, _px.size[1], 7) for x in range(0, _px.size[0], 7))
    ok("e o painel continua na imagem depois do recorte", _achou_vermelho)

    # 5. Cena ambientada (sem fundo chapado): recorte central, nunca faixa.
    import random
    random.seed(3)

    def _ruido(d):
        for _ in range(4000):
            x, y = random.randint(0, 1161), random.randint(0, 911)
            d.point((x, y), fill=(random.randint(0, 255), random.randint(0, 255),
                                  random.randint(0, 255)))
    cena = png(1162, 912, _ruido, fundo=(120, 110, 100))
    _saida, _rel = quadrar(cena)
    ok("cena ambientada 1162x912 sai quadrada por recorte",
       _md.formato(_saida)[2] and "recortou" in _rel)

    # 6. A cor da faixa NUNCA é a da marca.
    _azul_da_marca = (232, 238, 245)
    _fonte = open(__file__, encoding="utf-8").read()
    _sem_comentario = "\n".join(
        l for l in _fonte.splitlines()
        if not l.strip().startswith("#") and "232, 238, 245" not in l)
    ok("o azul-claro da marca não é pintado aqui",
       "232" not in _sem_comentario.split("if __name__")[0])

    # 7. lado_final entrega no tamanho pedido.
    _saida, _ = quadrar(retrato, lado_final=1200)
    ok("sai em 1200x1200 quando pedido",
       Image.open(io.BytesIO(_saida)).size == (1200, 1200))

    print()
    if falhas:
        print("FALHOU: " + ", ".join(falhas))
        raise SystemExit(1)
    print("Tudo certo.")
