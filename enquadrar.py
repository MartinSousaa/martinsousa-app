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


def janela(largura, altura, caixa, folga_pct=FOLGA_PCT,
           tem_texto=False):
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
        # ── AQUI O STUDIO DECEPAVA O TEXTO, E O COMENTARIO GARANTIA QUE NAO
        #
        # Dono, 30/09: "Imagem 2 e imagem 5 com texto cortando". O relato foi
        # exato: "todo o bloco de texto da esquerda esta cortado pela borda
        # esquerda; os titulos aparecem como 'TE DE MEDIDA / ISO'".
        #
        # A linha acima dizia "nao ha painel de texto para decepar". Isso era
        # SUPOSICAO, nao medida: numa peca de marketing o fundo tem conteudo
        # — cartoes, paineis, cenario — entao a caixa do assunto cobre o
        # quadro inteiro, e o recorte central come a lateral onde o texto
        # mora.
        #
        # Com texto, `coube=False`: quem chama PREENCHE em vez de recortar.
        # Margem e feia; titulo decepado torna a peca inutilizavel. Entre as
        # duas, a peca com margem ainda pode ser publicada — a com o titulo
        # cortado, nao.
        if tem_texto:
            return ((largura - lado) // 2, (altura - lado) // 2, lado, False)
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


def quadrar(dados, fundo_branco=False, lado_final=None,
            tem_texto=False):
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
        jx, jy, lado, coube = janela(w, h, caixa,
                                     tem_texto=tem_texto)
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

    # 4-bis. O CASO QUE DECEPOU O TEXTO EM PRODUCAO (30/09)
    #
    # Dono: "Imagem 2 e imagem 5 com texto cortando". O relato da conferencia
    # foi exato: "todo o bloco de texto da esquerda esta cortado pela borda
    # esquerda do quadro; os titulos aparecem como 'TE DE MEDIDA / ISO'".
    #
    # A causa esta em `janela`: quando a caixa do assunto cobre >=90% do
    # quadro, ela faz RECORTE CENTRAL e devolve `coube=True`, com o
    # comentario "nao ha painel de texto para decepar". Isso e SUPOSICAO, nao
    # medida. Numa peca de marketing o fundo tem conteudo — cartoes, paineis,
    # cenario — entao a caixa cobre tudo, e o corte central come a lateral
    # onde o texto mora.
    #
    # A peca com texto passa a PREENCHER em vez de recortar. Margem e feia;
    # titulo decepado torna a peca inutilizavel, e foi o que o dono recebeu.
    # O DADO DO TESTE E O CASO MEDIDO, E NAO UM QUE EU ACHEI PARECIDO.
    #
    # A primeira versao deste teste pintava um fundo quase liso: a caixa dava
    # 82% x 77%, nao chegava nos 90%, e o teste nem tocava o ramo que eu
    # tinha mudado. Passava verde sem medir nada.
    #
    # O caso REAL e a peca de marketing: cenario com conteudo ATE AS BORDAS,
    # entao a caixa do assunto cobre 100% x 100%. Medido: o corte central
    # comeca em x=200 e o painel de texto vai de 30 a 430 — decepado.
    import random as _rnd_tx
    _rnd_tx.seed(7)

    def _texto_com_fundo_vivo(d):
        for _ in range(9000):                                  # cenario ate a borda
            _x, _y = _rnd_tx.randint(0, 1399), _rnd_tx.randint(0, 999)
            d.point((_x, _y), fill=(_rnd_tx.randint(150, 230),) * 3)
        d.ellipse((800, 400, 1250, 850), fill=(20, 120, 40))   # produto a direita
        d.rectangle((30, 120, 430, 880), fill=(180, 30, 30))   # PAINEL DE TEXTO
    _marketing = png(1400, 1000, _texto_com_fundo_vivo)
    _cx = _md.caixa_do_assunto(_marketing)
    ok("o caso do teste e mesmo o que quebrou: a caixa cobre o quadro",
       _cx is not None and (_cx[2] - _cx[0]) >= 0.9 * 1400
       and (_cx[3] - _cx[1]) >= 0.9 * 1000)
    # Com o defeito de volta (sem `tem_texto`), o corte comeca DEPOIS do painel.
    _jx_sem, _, _lado_sem, _coube_sem = janela(1400, 1000, _cx)
    ok("e sem a correcao ele DECEPA mesmo o painel — senao o teste nao mede "
       "nada", _coube_sem and _jx_sem > 30)
    _jx, _jy, _lado, _coube = janela(1400, 1000, _cx, tem_texto=True)
    ok("peca COM TEXTO nao pode ser recortada quando a caixa cobre o quadro "
       "— o corte central decepa o painel lateral",
       (not _coube) or (_jx <= 30 and _jx + _lado >= 430))
    _saida_mk, _rel_mk = quadrar(_marketing, tem_texto=True)
    _pm = Image.open(io.BytesIO(_saida_mk)).convert("RGB")
    _achou_painel = any(
        _pm.getpixel((x, y))[0] > 140 and _pm.getpixel((x, y))[1] < 80
        for y in range(0, _pm.size[1], 5) for x in range(0, _pm.size[0], 5))
    ok("e o painel de texto continua inteiro na peca entregue", _achou_painel)
    # E A PECA SEM TEXTO continua recortando — senao eu troco um defeito por
    # outro: ambientacao com faixa nas laterais e o que o dono ja reclamou.
    _saida_amb, _rel_amb = quadrar(_marketing, tem_texto=False)
    ok("peca SEM texto continua recortando, e nao ganha faixa",
       "recortou" in _rel_amb)
    ok("e a peca COM texto preenche, dizendo isso no relato",
       "preencheu" in _rel_mk)

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
