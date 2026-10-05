import idioma as _idioma
import os
import streamlit as st
import requests
import base64
import io
import zipfile
import json
import anthropic
import threading as _threading_limiter
# APELIDO PROPRIO, E DE PROPOSITO.
#
# Meia duzia de funcoes desta tela fazem `import log_imagem` DENTRO do corpo,
# e isso torna o nome LOCAL na funcao inteira: uma chamada antes daquela linha
# estoura UnboundLocalError — que e o defeito que derrubou o Painel de Metas
# duas vezes e o motivo de `checar_ordem.py` existir. Um apelido que ninguem
# mais usa nao pode ser sombreado.
import log_imagem as _li_thread
import time as _time_limiter
from collections import deque as _deque

# Geração de imagem via Imagen 3 (Vertex AI) — fatura no Google Cloud, sem GEMINI_API_KEY.
# Modelo geralmente disponível, sem acesso especial necessário.
# Autenticação: service account gcp_service_account (o mesmo do Sheets/Drive).
MODELO_IMAGEM = "imagen-3.0-generate-001"


class _GeminiRateLimiter:
    """Rate limiter global para a API Gemini — respeita 10 RPM automaticamente.
    Compartilhado entre todas as threads/sessões do processo.
    """
    def __init__(self, rpm=8, window=60):
        self._lock = _threading_limiter.Lock()
        self._calls = _deque()
        self._rpm = rpm        # 8 de 10 disponíveis — margem de segurança
        self._window = window  # janela deslizante de 60s

    def aguardar(self):
        """Bloqueia até que seja seguro fazer uma nova chamada à API."""
        while True:
            with self._lock:
                agora = _time_limiter.time()
                # Descarta chamadas fora da janela
                while self._calls and agora - self._calls[0] >= self._window:
                    self._calls.popleft()
                if len(self._calls) < self._rpm:
                    self._calls.append(agora)
                    return
                # Quanto falta até a chamada mais antiga sair da janela
                espera = self._window - (agora - self._calls[0]) + 0.2
            _time_limiter.sleep(min(espera, 2))

# Singleton por processo — usa st.cache_resource para sobreviver a reruns E hot-reloads
@st.cache_resource
def _get_gemini_limiter():
    return _GeminiRateLimiter(rpm=8, window=60)

_GEMINI_LIMITER = _get_gemini_limiter()


def _get_openai_api_key():
    """A chave da OpenAI, pelo módulo que lê os dois lugares sem levantar."""
    import chaves as _ch
    return _ch.ler("OPENAI_API_KEY")


# ── PADRÃO VISUAL MARTINSOUSA (hardcoded em todos os prompts) ──────────────────
# ── O SISTEMA VISUAL DA LOJA ────────────────────────────────────────────────
#
# A PALETA FIXA ERA O QUE IMPEDIA A IMAGEM BOA.
#
# Aqui estava escrito "Fundo: #E8EEF5", "texto #1A3A6B", "destaque #4A7EC7" e
# "NÃO use marrom, laranja, vermelho ou verde". Em todas as peças, de todos os
# produtos.
#
# O dono mostrou três referências que ele quer copiar: um álbum marfim (madeira
# clara, flores brancas, luz alta), uma caixa de relógios preta (nogueira
# escura, mármore, dourado, luz baixa) e marcadores coloridos (branco com
# acentos nas cores das peças). A regra acima PROIBIA a segunda — nogueira e
# dourado são marrom e laranja — e achatava as três na mesma cara azul.
#
# A identidade de uma loja não é uma cor repetida. É tipografia, hierarquia,
# desenho dos ícones e dos cards, espaçamento e acabamento. A cor é direção de
# arte, e direção de arte é do produto.
#
# Decidido pelo dono em 21/09/2026: "o azul deixa de ser obrigatório sim".
PADRAO_VISUAL = """
SISTEMA VISUAL DA LOJA — IDENTIDADE FIXA, DIREÇÃO DE ARTE ADAPTATIVA

Todas as imagens desta loja pertencem à mesma família visual, mas NÃO
compartilham a mesma paleta de cores.

IDENTIDADE FIXA (igual em todo produto, é ela que diz "mesma loja"):
- Tipografia: Montserrat ou Poppins — limpa, moderna, sem serifa. Nunca serifada.
- Hierarquia: título curto e forte; texto secundário menor e leve.
- Ícones: line-art clean, traço fino, geometria simples e consistente.
- Cards e callouts: cantos arredondados, construção minimalista, acabamento premium.
- Espaçamento: composição arejada, alinhamentos precisos, margens consistentes.
- Texto sempre em português do Brasil, sem erro de ortografia, sem caixa alta excessiva.
- Fotografia: produto nítido e protagonista, luz profissional, integração realista.

{direcao}
- O PRODUTO NUNCA É RECOLORIDO para combinar com a direção de arte. A paleta
  vale para fundo, texto e elementos gráficos — jamais para o produto.
- Quando houver imagem de referência de layout, copie a ESTRUTURA: hierarquia,
  densidade, organização dos blocos. NÃO copie a paleta, o cenário, a
  iluminação nem os objetos dela.

CENÁRIO REAL EM TODAS AS PEÇAS — NÃO APENAS NA 3 E NA 8:
- O fundo é o AMBIENTE DE USO do produto, fotografado: o cômodo, a bancada, a
  mesa, o espaço onde ele de fato vive. Nunca superfície chapada, nunca
  gradiente liso, nunca "estúdio neutro" como cenário.
- O ambiente aparece em profundidade de campo SUAVE — presente e reconhecível,
  desfocado o bastante para não competir com o produto nem com o texto.
- Onde houver cartão, bloco ou frase, a área atrás dele fica mais desfocada e
  com contraste controlado, para o texto permanecer legível sobre a cena. A
  legibilidade manda no tratamento do fundo; o fundo nunca manda na
  legibilidade.
- Se a peça exigir área limpa para informação técnica, use uma faixa ou cartão
  sólido SOBRE a cena — e não a cena inteira trocada por fundo liso.
"""

# O QUE ENTRA NO BURACO `{direcao}` DO PADRAO VISUAL.
#
# Sem direcao herdada, vale o texto de sempre: a peca deduz. Com direcao
# herdada, a peca NAO deduz — e a diferenca precisa estar escrita, senao o
# prompt manda decidir e entrega a decisao pronta na mesma mensagem.
DIRECAO_A_DEDUZIR = """DIREÇÃO DE ARTE ADAPTATIVA (muda a cada produto):
- NÃO existe cor de fundo obrigatória. Analise o produto — cor, material,
  categoria, ocasião de uso e público provável — e escolha a paleta, a
  iluminação, o cenário e os materiais que melhor valorizem ESTE produto.
- As cores dos elementos gráficos saem da direção de arte escolhida para esta
  peça, com contraste suficiente para legibilidade.
- Produtos diferentes podem ter paletas completamente diferentes. Produto claro
  e delicado pede cena clara e suave; produto preto e premium pede cena escura
  e dramática; produto colorido pede fundo neutro com acentos nas cores dele."""

DIRECAO_JA_DECIDIDA = """DIREÇÃO DE ARTE: JÁ DECIDIDA PARA ESTE PRODUTO.
- Ela está escrita no bloco DIREÇÃO DE ARTE DESTE PRODUTO, acima. NÃO escolha
  paleta, material, luz ou cenário: herde os de lá.
- Esta peça é uma das oito do mesmo catálogo, e as oito herdam a mesma."""


def padrao_visual(direcao=None):
    """O padrão visual da loja, com ou sem direção de arte herdada."""
    return PADRAO_VISUAL.format(
        direcao=(DIRECAO_JA_DECIDIDA if direcao else DIRECAO_A_DEDUZIR))


# ── O PRODUTO É O DESTAQUE, E ISSO VIRA NÚMERO ──────────────────────────────
#
# "o maior possível" não é instrução: é opinião, e o modelo tem a dele. O
# resultado era produto pequeno no meio de um cenário amplo, que foi a primeira
# reclamação do dono — "imagens extremamente pequenas considerando a dimensão".
#
# Ocupação medida resolve, e a ordem de montagem importa tanto quanto o número:
# enquadrar o produto PRIMEIRO e distribuir o resto no que sobrar é diferente
# de desenhar a peça e encaixar o produto num quadrante.
# ── A OCUPACAO DO QUADRO TEM UMA FONTE SO ───────────────────────────────────
#
# Ela estava escrita em TRES lugares que nao se falavam:
#
#   o preset do tipo         — a capa pedia "90-95% do frame"
#   o bloco de protagonismo  — "55% a 70%" com texto, "65% a 80%" sem
#   a composicao em ingles   — a capa, "Product occupancy 85-92% of frame"
#
# Os tres chegavam na MESMA mensagem ao modelo, e a parte em portugues ia
# rotulada como "override any conflicting generic rule below". Tres numeros
# diferentes para a mesma medida, com um deles mandando nos outros: o gerador
# escolhia, e escolhia pequeno.
#
# Numero que aparece duas vezes e numero que vai discordar de si mesmo. Aqui
# ele aparece uma vez, e as duas linguas saem dele.
#
# (minimo, maximo ou None para "pelo menos", complemento em ingles)
OCUPACAO = {
    1: (85, 92,
        "Full product: YES — completely visible, no cropping. Minimal environment. "
        "The product must nearly touch the edges of the frame — leave only a thin "
        "breathing margin. Empty background is wasted space."),
    2: (60, 75,
        "The product is the subject, the panels are the caption. Full product: "
        "preferably YES. Callouts and benefit panels live in the remaining margin, "
        "never shrinking the product to fit them."),
    # ── A PECA 3 TAMBEM E CENA, E EU A DEIXEI PARA TRAS ────────────────
    #
    # Dono, 30/09: "o produto esta GIGANTE nas maos da crianca". Eu atribui
    # isso a peca 7, corrigi a 7 e a 8, e deixei a 3 — que e "PRODUTO NO
    # AMBIENTE DE USO REAL: deduza (...) onde ESTE produto e de fato usado, e
    # POR QUEM". Cena com gente, igual as outras duas.
    #
    # Ela mandava "o produto ocupa NO MINIMO 45% da dimensao util do quadro"
    # e, no mesmo prompt, "Nunca deixe o produto pequeno no centro de um
    # cenario amplo" — a linha que ja tinha inflado a ambientacao em 29/09.
    # Um compasso de 16 cm a 45% do quadro, na mao de uma crianca, E gigante.
    #
    # Esta e a Forma 1 pela TERCEIRA vez no mesmo defeito: 29/09 na peca 8,
    # 30/09 de manha na 7, e agora na 3. Por isso o grupo passa a ser uma
    # lista com nome: a proxima peca de cena entra nela, e nao num quarto
    # lugar que alguem esquece.
    3: None,
    4: (80, 92,
        "Macro close-up of ONE detail. Do NOT show the full product. Full product: NO."),
    5: (50, 65,
        "The text panels occupy a dedicated zone of the remaining frame — they never "
        "overlap the product, and the product is never shrunk to make room for them. "
        "The number of blocks is fixed by the Studio: render exactly those, and keep "
        "every one of them fully inside the frame."),
    6: (50, 65,
        "The text panels occupy a dedicated zone of the remaining frame — they never "
        "overlap the product, and the product is never shrunk to make room for them. "
        "The number of blocks is fixed by the Studio: render exactly those, and keep "
        "every one of them fully inside the frame."),
    # ── A PECA 7 TAMBEM E CENA, E TAMBEM PERDEU A PORCENTAGEM ──────────
    #
    # Dono, 30/09: "o produto esta GIGANTE nas maos da crianca".
    #
    # Ela tinha (30, 45) com a frase "Nao e sugestao: e a medida desta peca"
    # — e, no MESMO prompt, "Never enlarge the product beyond its real scale
    # in the hands that hold it". Duas ordens sobre o mesmo assunto, e a que
    # ganha e a que se declara inegociavel. Um compasso de 16 cm ocupando
    # 30% a 45% de um quadro, na mao de uma crianca, E gigante: a escala
    # real dele ali e um terco disso.
    #
    # O raciocinio ja estava escrito duas linhas abaixo, para a peca 8 — "Por
    # um numero aqui e o produto volta gigante" — e eu o apliquei so la. Esta
    # e a Forma 1 do CLAUDE.md na forma mais pura: a correcao chegou num
    # irmao e nao no outro, com o comentario que a explica logo ao lado.
    #
    # Entrega de presente e cena com gente: o tamanho do produto nela e a
    # escala real dele nas maos, e nenhuma porcentagem sabe disso.
    7: None,
    # A ambientacao NAO tem faixa: o tamanho dela e a escala real do objeto no
    # ambiente. Por um numero aqui e o produto volta gigante.
    8: None,
}


# ── QUANTOS BLOCOS DE INFORMACAO, TAMBEM DE UMA FONTE SO ────────────────────
#
# O Close chegava ao modelo com TRES numeros para a mesma coisa: "Máximo 2
# callouts" (preset), "use de 3 a 5 blocos" (regra generica de layout) e
# "Maximum 4 information elements" (montado a partir da copy da triagem).
# Nenhum deles sabia dos outros. Na Caneca Medieval o gerador empilhou os
# quatro cartoes e passou por cima do produto.
#
# (minimo, maximo) de blocos de texto por tipo.
BLOCOS = {
    1: (0, 0),   # capa: zero texto
    2: (3, 5),   # beneficios em cartoes
    3: (2, 3),   # frases de destaque sobre a cena
    4: (1, 2),   # callouts discretos de close
    # SEIS, E NAO QUATRO. A caneca veio com cinco cotas — altura, largura,
    # alca profundidade, alca abertura e peso — e um teto de 4 cortaria a
    # ultima da copy, apagando o peso da peca. Cartao de cota e DADO, nao
    # argumento de venda: o teto existe para impedir parede de texto, e
    # medida informada nao vira parede.
    5: (1, 6),   # um cartao de cota por medida informada
    6: (3, 4),   # pergunta + resposta
    7: (1, 1),   # uma frase emocional
    8: (0, 0),   # ambientacao: so "Imagem meramente ilustrativa"
}


def faixa_de_blocos(tipo):
    """(minimo, maximo) de blocos de texto do tipo. (0, 0) quando nao ha texto."""
    return BLOCOS.get(numero_do_tipo(tipo), (3, 5))


# A LINHA DO "SEM COPY" PRECISA DE MARCA, PORQUE ALGUEM A REESCREVE.
#
# ACHADO EM PRODUCAO, 05/10, na peca 5 da Caneca Termica Medieval.
#
# Ate 02/10 a peca sem copy recebia "- Esta peca tem exatamente N bloco(s)",
# e `trocar_texto_exato` — o caminho do AJUSTE, que injeta a copy corrigida
# — reescrevia aquele N com um regex de `exatamente \d+ bloco`. Troquei a
# frase por uma SEM NUMERO, e o regex deixou de casar: o prompt foi ao
# Gemini dizendo "NAO escreva nenhuma palavra" e, doze linhas abaixo,
# "escreva EXATAMENTE estas palavras, letra por letra".
#
# O acoplamento era por TEXTO, e por isso `checar_impacto` nao viu: ele
# procura nome com leitor fora, e aqui o leitor le uma FRASE. A marca
# resolve: quem injeta copy tem onde apagar a ordem antiga.
MARCA_SEM_COPY = "- Esta peça NÃO recebeu copy:"


def blocos_em_portugues(tipo, pedidos=0):
    """A linha de densidade que entra no prompt em portugues.

    `pedidos` e quantos blocos a copy da triagem de fato trouxe. Quando ela
    existe, o numero deixa de ser faixa: a peca tem AQUELES blocos, e o
    prompt nao pode dizer "use de 3 a 5" ao lado de uma copy de 4 — sao dois
    numeros sobre a mesma coisa, e o gerador escolhe.
    """
    minimo, maximo = faixa_de_blocos(tipo)
    if maximo == 0:
        return "- Esta peça não tem blocos de texto."
    if pedidos:
        return (f"- Esta peça tem exatamente {pedidos} bloco(s) de texto, e são "
                f"os do bloco de TEXTO EXATO. Não acrescente nenhum outro.")
    # SEM COPY NAO SE PEDE CARTAO NENHUM — O TESTE DE 02/10 PROVOU O PORQUE.
    #
    # Aqui havia DOIS ramos, e os dois tinham o mesmo defeito. Um dizia "Sem
    # referencia: exatamente 1 bloco de texto" (tipo 7); o outro, "Esta peca
    # tem exatamente {maximo} bloco(s) de texto. Nao acrescente nenhum outro,
    # e nao entregue menos". Os dois fechavam o NUMERO e esqueciam as
    # PALAVRAS: quando o plano volta com `textos: []`, o modelo recebia ordem
    # de desenhar N cartoes e zero palavras para escrever neles. Ele nao
    # deixa em branco — ele preenche.
    #
    # O que ele preencheu, medido na Caneca Termica Medieval em 02/10:
    #   peca 4 (Close, sem copy): escreveu a DESCRICAO DO CAMPO dentro do
    #     cartao — "TITULO CURTO EM CAIXA ALTA: TEXTURA UNICA E PROFUNDA".
    #     A regra de redacao do prompt virou o texto da peca.
    #   peca 5 (Tecnicas, sem copy): inventou sete cotas, duas repetidas, e
    #     uma seta de "ALTURA DA ALCA" apontando para o corpo da caneca.
    #
    # Nos dois casos as guardas estavam verdes e o prompt estava coerente
    # consigo mesmo: ele pediu exatamente o que recebeu. O defeito e PEDIR.
    #
    # Entao sem copy a peca sai SEM TEXTO. Peca limpa e aproveitavel; peca com
    # medida inventada e pior que peca nenhuma, porque mente com cara de dado.
    return (MARCA_SEM_COPY + " o plano voltou sem texto para ela. "
            "Por isso ela não tem bloco de texto nenhum. NÃO escreva nenhuma "
            "palavra, nenhum título, nenhum cartão, nenhuma legenda, nenhum "
            "rótulo e nenhuma medida na imagem — nem para preencher espaço, "
            "nem copiando esta instrução. A peça é só a fotografia.")


# ── O ESPACO DO QUADRO: QUEM OCUPA O QUE, E O QUE NAO ENCOSTA EM NADA ──────
#
# Duas queixas do dono que nunca tiveram regra propria: "margem" e "quadrados
# sobrepondo a imagem". Auditado o prompt real, os dois buracos:
#
#   MARGEM — so a capa tinha teto. Nos tipos 2 a 7 a unica linha sobre borda
#   era "respiro nas bordas da peca", que PEDE margem sem dizer quanto, e os
#   presets 2 e 6 ainda pediam "muito whitespace". Faltava a frase que fecha:
#   o que nao e produto e painel ou cenario — nao e vazio.
#
#   SOBREPOSICAO — "jamais sobreponha texto ao produto" existia. Nao existia
#   nada sobre cartao em cima de cartao, prop na frente do produto, nem
#   produto cortado pela borda do quadro. Cortar o produto na borda e o quadro
#   sobrepondo o produto, e nos tipos 2 a 7 nao havia uma linha proibindo.
#
# As duas sao a mesma pergunta — quem ocupa cada pedaco do quadro — e por isso
# saem de um lugar so, variando por tipo.
# ── A GEOMETRIA DEIXA DE SER ADIVINHADA PELO MODELO ───────────────────────
#
# ACHADO NO TESTE DE 05/10, comparando o prompt que gerou errado com o que
# gerou certo. Os OITO prompts iniciais sao identicos aos finais — medido,
# byte a byte. A unica coisa que mudou foi o que as CORRECOES acrescentaram
# depois de o dono olhar a imagem e reclamar tres vezes.
#
# E o que elas acrescentaram nao foi uma regra NOVA: foi a MESMA regra em
# outra unidade.
#
#   o primeiro prompt dizia: "nao sobreponha" · "pelo menos 6% em cada lado"
#   a correcao que funcionou: "ZONA ESQUERDA (0% a 50%): a caneca"
#                             "ZONA DIREITA (55% a 97%): quatro cartoes"
#                             "corredor livre de 5% entre as duas"
#
# Modelo de imagem nao calcula 6% de nada — ele desenha. Ordem abstrata ele
# interpreta; zona com numero ele obedece. O dono gastou tres rodadas pagas
# virando, a mao, o validador geometrico que o Python podia ter rodado antes
# da primeira chamada: o sistema JA SABIA, antes de gerar, quantos cartoes
# existem, quanto o produto ocupa e qual a folga.
#
# O LADO EM PIXEL VEM DO QUE O MOTOR DEVOLVE, e nao de um numero escrito
# aqui: 1024 e o `size` pedido a OpenAI (`imagem.py` ~3433) e o `imageSize`
# "1K" pedido ao Gemini (~2543). Escrever 61px direto seria a Forma 5 — dois
# donos para a mesma medida, discordando no dia em que o tamanho mudar.
LADO_GERADO_PX = 1024
FOLGA_BORDA_PCT = 6
# O CORREDOR ENTRE O PRODUTO E OS CARTOES. Cinco por cento foi a medida que
# funcionou na peca 6 do teste, e esta escrita no prompt que deu certo.
CORREDOR_PCT = 5


def em_px(pct):
    """A porcentagem traduzida em pixel do quadro gerado. Um dono, duas vozes.

    A porcentagem continua mandando; o pixel vai AO LADO dela. Trocar uma
    pela outra seria perder a regra quando o tamanho do quadro mudar.
    """
    return int(round(float(pct) / 100.0 * LADO_GERADO_PX))


def zonas_da_peca(tipo, blocos=0):
    """O desenho do quadro em ZONAS, para a peca que tem cartao. "" se nao tem.

    Calculado, nao adivinhado: a faixa do produto sai de `OCUPACAO[tipo]`, a
    folga de `FOLGA_BORDA_PCT` e o corredor de `CORREDOR_PCT`. O modelo
    recebe a conta pronta em vez de ter de fazer a conta.

    `blocos` e quantos cartoes a peca tem de fato. Zero — peca sem copy —
    devolve "": sem cartao nao ha zona de cartao, e inventar uma seria
    oferecer cartao a quem o prompt acabou de proibir.
    """
    n = numero_do_tipo(tipo)
    if not blocos or n in (1, 4, 8):
        return ""
    # AS PECAS DE CENA NAO TEM ZONA, E ISSO E DE PROPOSITO.
    #
    # `OCUPACAO[3]`, `[7]` e `[8]` sao None: nelas o tamanho do produto e a
    # ESCALA REAL na mao de alguem, e nao uma porcentagem do quadro — foi
    # exigir porcentagem delas que produziu "o produto esta GIGANTE nas maos
    # da crianca", tres vezes, em 29 e 30/09. Desenhar zona a partir de uma
    # ocupacao que nao existe seria ressuscitar aquele defeito com outro
    # nome.
    _faixa = OCUPACAO.get(n)
    if not _faixa:
        return ""
    _ocup_min = _faixa[0]
    folga = FOLGA_BORDA_PCT
    # A ZONA DO PRODUTO E A LARGURA QUE A OCUPACAO JA EXIGE, encostada num
    # lado; a dos cartoes e o que sobra do outro, menos o corredor. Quando a
    # conta nao fecha, a peca NAO recebe zona nenhuma em vez de receber uma
    # zona impossivel — regra que nao cabe e pior que regra nenhuma.
    _lado_produto = min(_ocup_min, 100 - folga * 2 - CORREDOR_PCT - 20)
    if _lado_produto < 30:
        return ""
    _ini_cart = folga + _lado_produto + CORREDOR_PCT
    _fim_cart = 100 - folga
    if _fim_cart - _ini_cart < 20:
        return ""
    return (
        "GEOMETRIA DESTA PEÇA — já calculada, não a recalcule:\n"
        f"- ZONA DO PRODUTO: de {folga}% a {folga + _lado_produto}% da largura\n"
        f"  do quadro. O produto vive AQUI, inteiro, sem nada por cima.\n"
        f"- CORREDOR VAZIO: de {folga + _lado_produto}% a {_ini_cart}% da\n"
        f"  largura. Nada ocupa esta faixa — nem cartão, nem prop, nem texto.\n"
        f"  São {em_px(CORREDOR_PCT)} pixels de respiro num quadro de\n"
        f"  {LADO_GERADO_PX}px, e é o que impede o cartão de encostar no\n"
        f"  produto.\n"
        f"- ZONA DOS CARTÕES: de {_ini_cart}% a {_fim_cart}% da largura. Os\n"
        f"  {blocos} cartões vivem AQUI, empilhados numa coluna, todos com a\n"
        f"  mesma largura.\n"
        f"- A folga de {folga}% da borda são {em_px(folga)} pixels num quadro\n"
        f"  de {LADO_GERADO_PX}px. Nenhum cartão, seta ou legenda entra\n"
        f"  nesses {em_px(folga)} pixels, em nenhum dos quatro lados.\n"
        "- As duas zonas NÃO se tocam. Se um cartão não couber na zona dele,\n"
        "  diminua a ALTURA do cartão — nunca invada o corredor.\n")


def regra_de_espaco(tipo):
    """(texto em portugues, linha em ingles) sobre margem e sobreposicao."""
    n = numero_do_tipo(tipo)

    # A FOLGA E ESPACO DA CENA, E NAO UMA MOLDURA DESENHADA.
    #
    # Dono, 30/09: "imagens com margem". Uma das causas e o motor devolver
    # retangular e o Studio preencher (isso agora aparece no diagnostico). A
    # OUTRA e esta: "6% em cada lado, nada toca a borda" e facil de ler como
    # "desenhe uma faixa de 6% em volta" — e ai a peca volta com moldura e o
    # produto encolhido dentro dela.
    #
    # A regra vale nos NOVE tipos, e nao so no Close: corrigir onde o
    # sintoma apareceu e a Forma 1 desta base.
    # UM ASSUNTO, UM DONO: a frase da moldura mora aqui e e usada por
    # todos — inclusive pelo tipo 8, que tinha a SUA propria versao dela.
    # Duas redacoes que concordam hoje sao a Forma 5 esperando acontecer.
    _SEM_MOLDURA_PT = (
        "- NÃO DESENHE MARGEM, moldura, faixa lisa ou borda de cor em volta\n"
        "  da imagem. A folga é espaço da própria cena, e não um quadro\n"
        "  desenhado. A imagem sangra até a borda.\n")
    _SEM_MOLDURA_EN = (
        "- DO NOT DRAW a margin, frame, flat band or coloured border around "
        "the image. The clearance is scene space, not a drawn frame. The "
        "image bleeds to the edge.\n")
    comum_pt = (
        "- NADA SOBREPÕE O PRODUTO: nem texto, nem ícone, nem cartão, nem\n"
        "  faixa, nem prop de cenário. Objeto de cena fica ATRÁS ou AO LADO,\n"
        "  nunca à frente tampando parte dele.\n"
        "- Os blocos de texto não se sobrepõem entre si: cada cartão tem sua\n"
        "  área, com folga visível entre um e outro.\n"
        + _SEM_MOLDURA_PT)
    comum_en = (
        "- NOTHING overlaps the product: not text, not icons, not cards, not "
        "bands, not scene props. Scene objects sit BEHIND or BESIDE it, never "
        "in front covering any part of it.\n"
        "- Text blocks never overlap each other: every card has its own area, "
        "with visible clearance between them.\n"
        + _SEM_MOLDURA_EN)

    if n == 4:
        # O close corta de proposito: o recorte E a peca.
        # "PREENCHE O QUADRO" E DO PRODUTO, E NAO DO TEXTO.
        #
        # 28/09: o dono relatou texto CORTADO nesta peca. O prompt dizia
        # "nao ha margem de respiro nesta peca" e, adiante, "cada cartao
        # comeca pelo menos 6% abaixo do topo" — duas vozes sobre a mesma
        # borda, no mesmo texto. O gerador obedece a mais proxima, e ela
        # muda por peca. Mesma doenca do cartao com quatro vozes.
        pt = ("REGRA DE ESPAÇO DESTA PEÇA:\n"
              "- O PRODUTO preenche o quadro: borda vazia em volta do\n"
              "  detalhe, num macro, é erro. Isto vale para o PRODUTO.\n"
              "- A FOLGA DE 6% VALE PARA TEXTO, NUNCA PARA O PRODUTO:\n"
              "  callout, legenda e cartão ficam a pelo menos 6% da borda,\n"
              "  inteiros dentro do quadro. O produto continua preenchendo\n"
              "  o quadro — preenchê-lo nunca autoriza cortar texto.\n"

              + comum_pt)
        en = ("- The PRODUCT fills the frame: an empty border around the "
              "detail, in a macro shot, is a mistake. This applies to the "
              "PRODUCT.\n"
              "- THE 6% CLEARANCE APPLIES TO TEXT, NEVER TO THE PRODUCT: "
              "callouts, captions and cards stay at least 6% from the edge, "
              "whole inside the frame. The product keeps filling the frame — "
              "filling it never authorises cropping text.\n"
 + comum_en)
        return pt, en

    if n == 8:
        pt = ("REGRA DE ESPAÇO DESTA PEÇA:\n"
              + _SEM_MOLDURA_PT +
              "- O quadro é cena inteira: existe ambiente até a borda.\n"
              "- O produto aparece DESOBSTRUÍDO: nada do cenário passa na\n"
              "  frente dele, nem em parte.\n"
              "- O produto aparece INTEIRO: nenhuma parte cortada pela borda\n"
              "  do quadro.\n")
        en = (_SEM_MOLDURA_EN +
              "- The frame is a full scene: environment all the way to the "
              "edge.\n"
              "- The product is UNOBSTRUCTED: nothing in the scene passes in "
              "front of it, not even partly.\n"
              "- The product appears WHOLE: no part cut by the frame edge.\n")
        return pt, en

    if n == 1:
        pt = ("REGRA DE ESPAÇO DESTA PEÇA:\n"
              "- A margem branca é UNIFORME e MÍNIMA nos quatro lados — só o\n"
              "  suficiente para o produto não encostar na borda. Vazio\n"
              "  concentrado em cima, embaixo ou de um lado é erro.\n"
              "- O produto aparece INTEIRO: nenhuma parte cortada pela borda.\n"
              + comum_pt)
        en = ("- The white margin is UNIFORM and MINIMAL on all four sides — "
              "only enough to keep the product off the edge. Empty space "
              "concentrated at the top, bottom or one side is a mistake.\n"
              "- The product appears WHOLE: no part cut by the frame edge.\n"
              + comum_en)
        return pt, en

    # Tipos 2, 3, 5, 6, 7 e Personalizado: produto mais painel de texto.
    # UMA VOZ SOBRE A MARGEM, E ELA E A DA FOLGA.
    #
    # Aqui havia DUAS ordens contrarias, uma embaixo da outra: "faixa vazia em
    # volta da peca e area desperdicada, e o anuncio paga por ela" e "folga de
    # pelo menos 6% em cada lado". Mais uma terceira em ingles, logo abaixo:
    # "the safety margin is uniform and small". O gerador obedeceu a primeira,
    # encostou os cartoes na borda, e o texto saiu cortado — na peca 2, na 5, e
    # de novo depois de eu "corrigir".
    #
    # Porque a minha correcao de 26/09 (as pecas 4 e 5) ACRESCENTOU a regra da
    # folga e deixou a que brigava no lugar. Virei a terceira voz em vez de
    # calar a que contradizia, e o defeito voltou.
    #
    # O trabalho que a linha removida fazia — nao deixar o produto pequeno
    # perdido num quadro amplo — ja tem dono: e o bloco de protagonismo, que
    # diz a porcentagem exata de cada tipo. Duas respostas para a mesma
    # pergunta discordam; a questao e so quando.
    pt = ("REGRA DE ESPAÇO DESTA PEÇA:\n"
          "- A FOLGA DA BORDA MANDA: pelo menos 6% em cada lado, e nenhum\n"
          "  cartão de cota, seta ou legenda cruza ou toca a borda. Nada\n"
          "  encosta na margem — nem texto, nem ícone, nem cartão, nem seta.\n"
          "- DENTRO dessa folga, o espaço que sobra depois de enquadrar o\n"
          "  produto pertence aos blocos de texto e ao ambiente: distribua a\n"
          "  informação nele, sem nunca alcançar a margem.\n"
          "- O produto aparece INTEIRO: nenhuma parte cortada pela borda do\n"
          "  quadro.\n"
          + comum_pt)
    en = ("- THE EDGE CLEARANCE RULES: at least 6% on every side, and no card, "
          "callout, arrow or caption may cross or touch the frame edge.\n"
          "- INSIDE that clearance, whatever remains after framing the "
          "product belongs to the text blocks and the environment — fill it, "
          "but never reach the margin.\n"
          "- The product appears WHOLE: no part cut by the frame edge.\n"
          + comum_en)
    return pt, en


import re as _re_quadro

# TAMANHO DE QUADRO — nas duas formas em que alguém o escreve.
#
# Em porcentagem ("ocupando 60%") é como o SISTEMA escreve. Por extenso
# ("ocupando mais da metade do quadro") é como a IA que critica a peça
# escreve, em português livre — e foi por aí que a ordem de tamanho voltou ao
# prompt do Tigre, contra os 30% a 45% escritos acima no mesmo texto.
_MEDIDA_DE_QUADRO = _re_quadro.compile(
    r"[^,;.]*?(?:\d{1,3}\s?%|"
    r"(?:mais\s+da\s+|menos\s+da\s+|cerca\s+de\s+|quase\s+)?"
    r"(?:metade|dois\s+ter[c\u00e7]os|um\s+ter[c\u00e7]o|tr[e\u00ea]s\s+quartos|"
    r"um\s+quarto)\s+(?:d[oa]\s+)?(?:quadro|imagem|enquadramento|frame))"
    r"[^,;.]*", _re_quadro.I)

# O QUE SEPARA DUAS ORDENS DENTRO DA MESMA ORAÇÃO.
#
# "Reenquadre os cartões para dentro e deixe o produto ocupando 80% do quadro"
# não tem vírgula nenhuma. Cortar pelo padrão guloso comia a frase inteira e
# o gerador recebia a refação SEM instrução — trocar ordem contraditória por
# ordem nenhuma é pior, não melhor.
_CONECTIVO_DE_ORACAO = _re_quadro.compile(
    r"\s+(?:e|com|que|deixe|mantenha|mas)\s+", _re_quadro.I)


def sem_medida_de_quadro(texto):
    """A frase do plano, sem a porcentagem de quadro que ela não pode mandar.

    POR QUE ESTA FUNÇÃO EXISTE

    O campo `cena` é escrito pela IA do plano, e o prompt dela pede
    SUPERFÍCIE, PROPS e ÂNGULO — nada de tamanho. Em 28/09 ela escreveu
    "Fundo branco puro sem sombra projetada; produto centralizado ocupando
    60% do espaço vertical" numa peça cuja regra mandava 85% a 92%.

    Duas ordens contrárias sobre a mesma coisa, no mesmo prompt. O gerador
    obedeceu a do plano, a caneca saiu pequena na capa, e o dono teve de pedir
    para aumentar — uma rodada inteira por causa de uma frase.

    E a varredura passou VERDE: ela procura as frases que o SISTEMA escreve
    ("ocupa de X% a Y%"), e a IA escreve em português livre. Guarda que só
    conhece o próprio vocabulário não vê a voz de fora.

    POR QUE LIMPAR E NÃO PEDIR

    Pedir no prompt do plano seria mais uma regra de texto — e regra de texto
    é justamente o que o modelo ignora. O tamanho tem um dono só
    (`ocupacao_em_portugues`), e quem não é dono não fala.

    Corta a ORAÇÃO inteira, e não só o número: "ocupando 60%" sem o número
    vira "ocupando", que continua mandando tamanho sem dizer quanto.
    """
    t = str(texto or "").strip()
    if not t or not _MEDIDA_DE_QUADRO.search(t):
        return t

    saida = []
    for parte in _re_quadro.split(r"([,;.])", t):
        if parte in (",", ";", "."):
            if saida:
                saida.append(parte)
            continue
        if not parte.strip():
            continue
        # Dentro da oração, o conectivo pode separar duas ordens: uma útil e
        # uma de tamanho. Fica a primeira que não fala de tamanho.
        pedacos = _CONECTIVO_DE_ORACAO.split(parte)
        bons = [p for p in pedacos
                if p.strip() and not _MEDIDA_DE_QUADRO.fullmatch(p.strip())]
        if len(bons) == len(pedacos):
            saida.append(parte)
        elif bons:
            saida.append(bons[0].strip())
    limpo = "".join(saida)
    limpo = _re_quadro.sub(r"\s*([,;])\s*(?=[,;.]|$)", "", limpo)
    limpo = _re_quadro.sub(r"\s{2,}", " ", limpo).strip(" ,;.")
    # Sobrou frase? Se a limpeza comeu tudo, o certo é devolver vazio: cena
    # que só falava de tamanho não tinha nada a dizer sobre cenário.
    return (limpo + ".") if limpo else ""


def definir_produto_da_sessao(nome, codigo=None):
    """A porta ÚNICA para dizer qual produto a aba Imagem está tratando.

    POR QUE ESTA FUNÇÃO EXISTE

    `img_nome_produto` era escrito em TRÊS lugares — recuperar rascunho,
    ajuste fino avulso e fim da geração — e `img_codigo` em dois. Três
    escritores para a mesma pergunta é a Forma 5 desta base: um nome, duas
    respostas, e elas passam a discordar. Foi por um buraco dessa família que
    o Tigre foi gerado com o brief de um pêndulo.

    NOME VAZIO NÃO APAGA O QUE ESTAVA. O ajuste fino avulso escrevia
    `nome_produto or "produto-ajustado"`: um campo em branco trocava o produto
    da sessão por um rótulo genérico, e a geração seguinte saía sem nome — o
    mesmo defeito que fez o log gravar produto vazio em toda linha.

    A unificação do estado inteiro da aba continua aberta e declarada: é
    mudança grande, e o risco tem de ser mapeado antes.
    """
    nome = str(nome or "").strip()
    if nome:
        st.session_state["img_nome_produto"] = nome
    if codigo:
        st.session_state["img_codigo"] = str(codigo).strip()
    return st.session_state.get("img_nome_produto", "")


def divergencia_de_produto(cfg, nome_da_tela, dados_da_tela):
    """O plano congelado é de OUTRO produto? Devolve o aviso, ou "" quando bate.

    POR QUE ESTA FUNÇÃO EXISTE

    Dono, 29/09. A tela dizia, em verde: "Descrição encontrada: Tigre ·
    Dourado com Strass · 10x21x5 · 299 · Resina". O prompt das oito peças saiu
    com "PRODUTO: pendulo balança / 14x13x11 / 202g / Plástico", direção de
    arte "Técnico Automotivo Minimalista", cena "Interior de carro" e o texto
    "CABE EM MEU CARRO?".

    Um tigre decorativo gerado com o brief de um pêndulo automotivo. Oito
    peças pagas, todas do produto errado, sem um aviso.

    A tela relê a descrição a cada abertura; o `img_triagem_config` é
    congelado quando o PLANO é gerado, e é dele que o prompt tira nome,
    medidas, peso e material. Trocar o código na tela sem refazer o plano
    deixa os dois discordando — e o sistema tinha os DOIS dados na mão e
    nunca os comparou.

    Nenhuma regra de prompt conserta isso: o prompt estava obedecendo
    direitinho ao produto que lhe deram. O que faltava era perguntar.

    O aviso nomeia os dois lados. "Os dados não batem" manda o colaborador
    adivinhar qual está errado — e adivinhar custa outra rodada.
    """
    if not cfg:
        return ""

    def _norm(v):
        return " ".join(str(v or "").split()).strip().lower()

    nome_cfg = _norm(cfg.get("nome_produto"))
    nome_tela = _norm(nome_da_tela)
    dd_cfg = cfg.get("dados_descricao") or {}
    dd_tela = dados_da_tela or {}

    difs = []
    if nome_cfg and nome_tela and nome_cfg != nome_tela:
        difs.append(f"nome: o plano tem «{cfg.get('nome_produto')}» e a tela "
                    f"tem «{nome_da_tela}»")
    for campo, rotulo in (("medidas", "medidas"), ("peso", "peso"),
                          ("material", "material")):
        a_, b_ = _norm(dd_cfg.get(campo)), _norm(dd_tela.get(campo))
        if a_ and b_ and a_ != b_:
            difs.append(f"{rotulo}: o plano tem «{dd_cfg.get(campo)}» e a "
                        f"tela tem «{dd_tela.get(campo)}»")
    if not difs:
        return ""
    return ("O plano foi feito para OUTRO produto — gerar agora produz peças "
            "do produto errado. " + "; ".join(difs)
            + ". Refaça o plano ('Analisar e mostrar plano') antes de gerar.")


def _sem_acento(texto):
    import unicodedata as _u
    return "".join(c for c in _u.normalize("NFD", str(texto or "").lower())
                   if _u.category(c) != "Mn")


# ── PROMESSA QUE O PRODUTO NAO FEZ ────────────────────────────────────────
#
# A copy da peca 2 da Caneca Termica Medieval veio com "INOX POR DENTRO:
# DURAVEL e diferente de canecas decorativas". Os dados do produto dizem
# "interior em inox diferencia de canecas decorativas" — e nao dizem
# "duravel" em lugar nenhum. A palavra nasceu do material: a IA viu inox e
# concluiu durabilidade.
#
# Isso e propaganda sem lastro, e e a classe de defeito mais cara das oito:
# ela nao quebra nada, nao aparece em nenhuma guarda, e vai impressa para a
# pagina do produto. "Mantem a temperatura" numa caneca que nao e termica, ou
# "impermeavel" num caderno, e o mesmo defeito com outro substantivo.
#
# A LISTA SO ACUSA, NAO BLOQUEIA. Casamento por palavra erra: "ideal para
# festas" pode estar no campo de uso, e bloquear a geracao inteira por uma
# palavra seria a maquina de alarme falso que esta base ja decidiu nao ter.
# O aviso aparece ao lado do texto, ANTES de pagar a geracao, e quem decide e
# quem conhece o produto.
TERMOS_DE_PROMESSA = (
    "mantém", "mantem", "temperatura", "térmic", "termic", "conserva",
    "durável", "duravel", "durabilidade", "resistente", "resistência",
    "resistencia", "protege", "proteção", "protecao", "impermeável",
    "impermeavel", "à prova", "a prova", "garante", "garantia", "antiderrapante",
    "não risca", "nao risca", "não quebra", "nao quebra", "atóxico", "atoxico",
    "lava-louças", "lava loucas", "micro-ondas", "microondas",
)


def promessas_sem_lastro(textos, dados_descricao=None):
    """[(texto, [termos])] — as promessas que os dados do produto não sustentam.

    O lastro e o que o COLABORADOR escreveu: material, diferenciais,
    caracteristicas e uso. Se a palavra da promessa aparece la, ela tem
    origem e passa. Se nasceu so na copy, ela aparece aqui.

    Guarda de CONTEUDO, e nao de "nao explodiu": o texto sai perfeito em
    portugues, cabe no cartao e passa por todas as outras conferencias.
    """
    dd = dados_descricao or {}
    lastro = _sem_acento(" ".join(
        str(dd.get(c, "") or "") for c in
        ("material", "diferenciais", "caracteristicas", "uso",
         "nome_comercial", "nome_produto")))
    fora = []
    for t in (textos or []):
        alvo = _sem_acento(t)
        # A lista tem a forma com e sem acento do mesmo termo (o campo do
        # colaborador vem dos dois jeitos). Reportar as duas mostraria
        # "durável, duravel" para uma palavra só — a deduplicacao e pela
        # forma SEM acento, que e a que foi comparada.
        achados = {}
        for x in TERMOS_DE_PROMESSA:
            chave = _sem_acento(x)
            if chave in alvo and chave not in lastro:
                achados.setdefault(chave, x)
        if achados:
            fora.append((str(t), sorted(achados.values())))
    return fora


# ── NUMERO QUE O CADASTRO NAO TEM NAO VIRA ORDEM ──────────────────────────
#
# ACHADO EM 05/10, no prompt real da peca 5, e e a pior classe de defeito
# desta cadeia: o sistema LAVA a invencao do modelo em ordem do Studio.
#
# O MESMO prompt dizia as duas coisas:
#
#   dados do produto: "Medidas EXATAS (use esses números, não invente): 12x14"
#                     "Peso EXATO (use esse número, não invente): 326"
#   TEXTO EXATO:      "ALTURA 30mm ALTURA DA ALÇA 5,2cm PROFUNDIDADE 25mm
#                      PESO 326g LARGURA INTERNA 17mm LARGURA DA ALÇA 2,4cm
#                      LARGURA 35mm"
#
# 30mm, 25mm, 17mm e 35mm NAO EXISTEM no cadastro. E o bloco do TEXTO EXATO
# diz de si mesmo "acima de qualquer outra instrucao de texto" — entao o
# Gemini obedeceu a ordem mais forte, e estava certo em obedecer.
#
# DE ONDE VIERAM: a peca 5 veio SEM copy do plano. `revisar_texto` pede ao
# juiz visual o "texto_correto" (`imagem.py` ~7375) — e sem copy nao ha
# fonte de verdade para comparar, entao o juiz TRANSCREVE o que ve na
# imagem, so arrumando a grafia. As medidas que o Gemini inventou na
# primeira tentativa viraram o TEXTO EXATO da segunda.
#
# E a correcao automatica piorou: em vez de voltar a fonte, mandou
# "padronize as medidas do corpo para a escala real da caneca em cm" —
# pediu ao modelo que INFERISSE um numero que o Python ja tinha.
#
# A regra fecha a classe inteira: numero com unidade que o cadastro nao
# sustenta nao entra no TEXTO EXATO. Nao e sobre medida de caneca — e sobre
# o sistema nunca mandar escrever um dado que ele nao tem.
_NUMERO_COM_UNIDADE = __import__("re").compile(
    r"(\d+(?:[.,]\d+)?)\s*(mm|cm|m|kg|g|ml|l|litros?|un|pe[çc]as?|folhas?)\b",
    __import__("re").I)


def _numeros_do_cadastro(dados_descricao):
    """Todo numero que aparece nos campos do produto, sem unidade.

    "12x14" da {12, 14}; "altura: 5,2cm largura: 2,4" da {5.2, 2.4}. A
    unidade nao entra na comparacao de proposito: o colaborador escreve
    "5,2cm" num campo e "52" noutro, e as duas sao a mesma medida.
    """
    dd = dados_descricao or {}
    bruto = " ".join(str(dd.get(c, "") or "") for c in
                     ("medidas", "peso", "material", "caracteristicas",
                      "diferenciais", "uso", "nome_comercial", "nome_produto"))
    fora = set()
    for n in __import__("re").findall(r"\d+(?:[.,]\d+)?", bruto):
        try:
            fora.add(float(n.replace(",", ".")))
        except ValueError:
            pass
    return fora


def medidas_sem_lastro(textos, dados_descricao=None):
    """[(texto, [medidas])] — os blocos com numero que o cadastro nao tem.

    So olha numero COM UNIDADE: "4 cartoes" e contagem, "400ml" e dado do
    produto. Sem a unidade a guarda acusaria o inocente, e verificador que
    da alarme falso ensina a ser ignorado.
    """
    conhecidos = _numeros_do_cadastro(dados_descricao)
    fora = []
    for t in (textos or []):
        achados = []
        for valor, unidade in _NUMERO_COM_UNIDADE.findall(str(t)):
            try:
                v = float(valor.replace(",", "."))
            except ValueError:
                continue
            if v not in conhecidos:
                achados.append(f"{valor}{unidade}")
        if achados:
            fora.append((str(t), achados))
    return fora


def copy_sem_medida_inventada(textos, dados_descricao=None):
    """(textos_limpos, removidos) — a copy sem numero que o cadastro nao tem.

    Mesma politica de `copy_sem_promessa`: o BLOCO sai inteiro, porque tirar
    so o numero deixaria "ALTURA" sozinho num cartao de cota.
    """
    _fora = {t for t, _ in medidas_sem_lastro(textos, dados_descricao)}
    if not _fora:
        return list(textos or []), []
    return ([t for t in (textos or []) if str(t) not in _fora],
            [t for t in (textos or []) if str(t) in _fora])


def copy_sem_promessa(textos, dados_descricao=None):
    """(textos_limpos, removidos) — a copy sem o que os dados não sustentam.

    A BARREIRA ENTRE O PLANO E O MOTOR, e ela estava faltando.
    ----------------------------------------------------------
    `promessas_sem_lastro` já existia e já AVISAVA na tela. Mas aviso não é
    barreira: a peça 6 do teste de 05/10 foi ao Gemini com "MANTÉM BEBIDA
    QUENTE? Sim, térmica em metal e resina" — e o cadastro do produto não
    tem ensaio térmico nenhum. A IA viu inox e concluiu.

    Gastar uma geração para desenhar perfeitamente um texto que já nasceu
    errado é o desperdício mais caro desta cadeia: a arte sai boa, o
    conferidor aprova, e o claim falso vai para a página do produto.

    O BLOCO SAI INTEIRO, E NÃO A PALAVRA. Apagar só "mantém quente" de "A
    CANECA MANTÉM QUENTE? Sim, térmica" deixaria uma pergunta sem resposta
    desenhada no cartão. Bloco com promessa sem lastro não vai — e a tela
    diz qual e por quê, para quem conhece o produto decidir.

    Ela NÃO bloqueia a geração: a peça sai com os blocos que sobraram, e a
    contagem acompanha (`blocos_em_portugues` lê o número real). Bloquear o
    lote inteiro por uma palavra seria a máquina de alarme falso que esta
    base já decidiu não ter.
    """
    _fora = {t for t, _ in promessas_sem_lastro(textos, dados_descricao)}
    if not _fora:
        return list(textos or []), []
    limpos = [t for t in (textos or []) if str(t) not in _fora]
    removidos = [t for t in (textos or []) if str(t) in _fora]
    return limpos, removidos


def plano_misturado(plano, nome_produto):
    """O plano descreve MAIS DE UM produto? Devolve o aviso, ou "".

    POR QUE ESTA FUNÇÃO EXISTE (30/09)
    ----------------------------------
    O dono gerou oito peças do «Compasso Cortador Colorido» e recebeu:
    ambientação "completamente errada", produto irreconhecível nas mãos de
    uma criança, e texto cortado. Ele mandou ler o prompt que o sistema
    enviou, e o prompt estava obedecendo — ao produto ERRADO:

        peça 8: "Caixa aberta ... RELÓGIO DE PULSO elegante dentro"
        peça 7: "duas mãos ... a CAIXA DE MADEIRA entre elas"
        peça 4: "textura do GRÃO DA MADEIRA ... construção da CAIXA"

    Cinco dos nove planos descreviam uma caixa de madeira para relógios; os
    outros quatro diziam "Compasso cortador". Um plano, dois produtos.

    POR QUE `divergencia_de_produto` NÃO PEGOU
    Ela compara nome, medidas, peso e material entre o plano congelado e a
    tela — e esses quatro estavam CERTOS. O que o plano DESCREVE, que é o
    texto que vira a imagem, nunca era comparado com nada.

    A MEDIDA, E NÃO O PALPITE
    Cada peça do plano nomeia o produto (uma palavra do nome dele) ou fala
    dele genericamente ("o produto"). Quando ALGUMAS nomeiam e outras não, o
    plano não é de um produto só — e foi exatamente esse o padrão medido:
    4 peças citavam "Compasso", 5 não citavam nem isso nem "produto".

    Exigir que TODAS nomeiem daria alarme falso numa peça de close legítima
    ("ampliação da textura em foco"). Por isso a pergunta é sobre a MISTURA:
    o plano concorda consigo mesmo?
    """
    itens = (plano or {}).get("plano") or []
    if len(itens) < 3:
        return ""
    palavras = [p for p in _sem_acento(nome_produto).split() if len(p) > 3]
    if not palavras:
        return ""

    citam, mudas = [], []
    for item in itens:
        texto = _sem_acento(" ".join(str(item.get(c, "") or "")
                                     for c in ("composicao", "cena")))
        if not texto.strip():
            continue
        rotulo = str(item.get("tipo", "") or "?")[:28]
        if any(p in texto for p in palavras) or "produto" in texto:
            citam.append(rotulo)
        else:
            mudas.append(rotulo)

    if not citam or not mudas:
        return ""
    return (
        "O plano não é de um produto só. "
        f"{len(citam)} peça(s) descrevem «{nome_produto}» e {len(mudas)} "
        f"descrevem outra coisa: {', '.join(mudas[:4])}"
        + ("…" if len(mudas) > 4 else "")
        + ". Gerar agora produz peças do produto errado — foi assim que o "
          "Compasso Cortador virou uma caixa de madeira em cinco das nove. "
          "Refaça o plano ('Analisar e mostrar plano') antes de gerar."
    )


def faixa_de_ocupacao(tipo):
    """(minimo, maximo, complemento) do tipo, ou None quando nao ha faixa."""
    return OCUPACAO.get(numero_do_tipo(tipo))


def ocupacao_em_portugues(tipo):
    """A linha de ocupacao que entra no prompt em portugues."""
    faixa = faixa_de_ocupacao(tipo)
    if not faixa:
        return ("- O tamanho do produto no quadro e a ESCALA REAL dele no ambiente, "
                "nunca uma porcentagem imposta.")
    minimo, maximo, _ = faixa
    if maximo is None:
        return (f"- O produto ocupa NO MINIMO {minimo}% da dimensao util do quadro.")
    return (f"- O produto ocupa de {minimo}% a {maximo}% da dimensao util do quadro. "
            f"Nao e sugestao: e a medida desta peca.")


def ocupacao_em_ingles(tipo):
    """A mesma medida, na linha de COMPOSITION do prompt final."""
    faixa = faixa_de_ocupacao(tipo)
    if not faixa:
        return ("- COMPOSITION: the product appears at its REAL SCALE inside the "
                "scene — never enlarged to fill the frame. It leads by focus and "
                "light, not by size: sharp and well lit in the foreground, the "
                "environment softer behind it.")
    minimo, maximo, complemento = faixa
    medida = (f"at least {minimo}% of frame" if maximo is None
              else f"{minimo}\u2013{maximo}% of frame")
    return f"- COMPOSITION: Product occupancy {medida}. {complemento}"


INSTRUCAO_PROTAGONISMO = """
O PRODUTO É O DESTAQUE — SEMPRE, E ANTES DE TUDO:
{faixa}
- Determine o enquadramento do produto PRIMEIRO. Só depois distribua cenário,
  props e texto no espaço que sobrar.
- Faltando espaço, reduza os elementos secundários — NUNCA o produto.
- Nunca deixe o produto pequeno no centro de um cenário amplo.
- Quando o cenário ou o texto competirem com o produto, use profundidade de
  campo: fundo desfocado, produto nítido. O olho vai no produto primeiro, na
  informação depois, no cenário por último.
"""

# ── O PROTAGONISMO NA AMBIENTAÇÃO É OUTRO, E POR ISSO TEM TEXTO PRÓPRIO ─────
#
# A regra de cima manda o produto ocupar de 65% a 80% do quadro nas peças sem
# texto — e a ambientação é uma peça sem texto. O resultado foi o relato do
# dono: *"criando ambientação com o produto desproporcional ao que ele é no
# ambiente, parece que ele é GIGANTE"*.
#
# Ele está certo, e a culpa é desta linha: "Nunca deixe o produto pequeno no
# centro de um cenário amplo." Produto no centro de um cenário amplo é
# EXATAMENTE o que uma foto de ambientação é. A instrução proibia o objetivo
# da peça, e o modelo obedeceu inflando o produto até caber nos 70%.
#
# Numa foto ambientada o produto não domina por TAMANHO — domina por FOCO:
# ele está nítido, iluminado, em primeiro plano, e o resto é contexto
# desfocado. A escala continua sendo a real: uma meia sobre a cama é do
# tamanho de uma meia.
INSTRUCAO_PROTAGONISMO_AMBIENTE = """
O PRODUTO É O DESTAQUE — MAS PELA ATENÇÃO, NÃO PELO TAMANHO:
- ESCALA REAL, REGRA INVIOLÁVEL: o produto aparece no tamanho que ele tem de
  verdade em relação ao que está ao redor dele.
- Ele domina a cena por FOCO e por LUZ: nítido e bem iluminado em primeiro
  plano, com o ambiente em profundidade de campo mais suave atrás.
- O enquadramento é fechado ou médio NO PRODUTO — a câmera chega perto dele.
  Aproximar a câmera é o que o destaca; ampliar o objeto o deforma.
- É correto e desejável que o produto ocupe uma fração modesta do quadro se é
  isso que a escala real determina. Cenário amplo com o produto em evidência
  pelo foco é o objetivo desta peça, não um defeito dela.
{apoio}
"""

# O QUE MUDA ENTRE A AMBIENTACAO E A ENTREGA E SO ONDE O PRODUTO SE APOIA.
#
# Duas copias do bloco inteiro seriam a Forma 5: a terceira regra que alguem
# acrescentar num deles nao chega no outro, e os dois passam a discordar. O
# que difere sao duas linhas, e sao elas que viram parametro.
APOIO_AMBIENTE = """- Uma peça de vestuário sobre uma cama tem o tamanho de uma peça de
  vestuário; um objeto de mesa não pode ficar do tamanho da mesa.
- Nada de objeto flutuando, apoio impossível ou sombra que não bate com a
  superfície: o produto está POUSADO no ambiente, com contato e sombra reais."""

APOIO_USO = """- O produto aparece no tamanho que ele tem na mao ou no movel de quem o usa:
  se uma crianca o segura, ele NAO pode ser maior que o antebraco dela, nem
  tapar o tronco dela. Produto competindo em tamanho com a pessoa esta errado.
- Nada de objeto flutuando: ele esta apoiado, seguro ou pousado de verdade,
  com contato e sombra que batem com a superficie."""

APOIO_PRESENTE = """- O que cabe na mão tem o tamanho do que cabe na mão: o produto NUNCA fica
  maior que o antebraço de quem o segura, nem tapa o tronco dessa pessoa. Se
  ele estiver competindo em tamanho com a pessoa, está errado.
- Nada de objeto flutuando entre as mãos: os dedos ENCOSTAM nele, seguram
  mesmo, com contato e sombra reais — e nunca escondem parte dele."""

# ── QUAL BLOCO DE TAMANHO CADA PECA RECEBE — UMA PORTA SO ─────────────────
#
# A escolha vivia inline no montador, e era um `if` de dois ramos: capa ou
# resto. A ambientacao escapava por outro caminho (ela monta o proprio
# f-string), e a peca 7 — que e cena com gente, igual a ambientacao — caia no
# "resto" e recebia "Nunca deixe o produto pequeno no centro de um cenario
# amplo". Produto no centro de uma cena com duas pessoas e EXATAMENTE o que a
# peca 7 e: a instrucao proibia o objetivo da peca, e o modelo obedeceu
# inflando o produto. Foi o mesmo texto, palavra por palavra, que ja tinha
# feito a ambientacao sair gigante em 29/09.
#
# Tres perguntas e tres respostas, num lugar so. Peca nova entra aqui e nao em
# tres `if` espalhados.
TIPOS_DE_CENA = (3, 7, 8)   # o tamanho delas e a escala real, nunca porcentagem


def protagonismo_do_tipo(tipo):
    """O bloco de TAMANHO desta peca, ja formatado. Uma pergunta, uma resposta."""
    if modo_fundo_do_tipo(tipo) == "branco":
        return INSTRUCAO_PROTAGONISMO_CAPA.format(
            faixa=ocupacao_em_portugues(tipo))
    if numero_do_tipo(tipo) in TIPOS_DE_CENA:
        return INSTRUCAO_PROTAGONISMO_AMBIENTE.format(
            apoio={8: APOIO_AMBIENTE, 7: APOIO_PRESENTE,
                   3: APOIO_USO}[numero_do_tipo(tipo)])
    return INSTRUCAO_PROTAGONISMO.format(faixa=ocupacao_em_portugues(tipo))


# ── A CAPA É A MAIS EXIGENTE DAS TRÊS, E NÃO TINHA REGRA NENHUMA ───────────
#
# O dono, depois de ver a capa sair pequena: *"Já falei MIL VEZES que a
# prioridade é destacar o produto, ele tem que preencher o máximo possível da
# dimensão da imagem!!!"*
#
# Ele tinha razão de estar irritado. A capa (tipo 1) não recebia
# `INSTRUCAO_PROTAGONISMO` nem nada equivalente: o prompt dela não falava de
# tamanho em lugar nenhum, e o modelo escolhia. Saía produtinho no meio de um
# quadro branco vazio.
#
# Ela é foto limpa em fundo branco: não tem texto, não tem cenário, não tem
# nada para dividir espaço. Então é a única peça em que o produto deve mesmo
# encher o quadro.
INSTRUCAO_PROTAGONISMO_CAPA = """
O PRODUTO PREENCHE O QUADRO — ESTA É A REGRA MAIS IMPORTANTE DESTA PEÇA:
{faixa}
- Margem de respiro uniforme e MÍNIMA em volta — só o suficiente para o
  produto não encostar na borda. Nada de vazio grande em cima, embaixo ou dos
  lados.
- Produto inteiro, centralizado, nenhuma parte cortada.
- É ERRO grave entregar o produto pequeno no meio de um fundo branco vazio:
  esta é a foto que aparece na busca do marketplace, e produto pequeno ali
  perde a venda antes de alguém clicar.
- Se a proporção do produto não preencher os dois eixos, aproxime a câmera até
  encher o eixo mais longo dele.
"""

INSTRUCAO_FIDELIDADE_ABERTURA = """
REGRA DE FIDELIDADE AO PRODUTO (a mais importante de todas — sem exceções):
- Reproduza o produto EXATAMENTE como aparece nas imagens de referência: mesma cor,
  mesmo formato, mesmas proporções, mesmos detalhes visíveis
- PROIBIÇÃO ABSOLUTA: JAMAIS substitua o produto das fotos de referência por um
  produto diferente, inventado ou genérico. Se não conseguir reproduzir o produto
  num ângulo específico, use o ângulo disponível nas fotos — mas NUNCA crie outro
  produto. Gerar um produto diferente é o erro mais grave possível nesta tarefa.
- Se uma característica do produto não estiver visível nas fotos de referência e for
  necessária para a composição, adapte a cena para evitar mostrar esse ângulo —
  não invente como o produto seria naquele ângulo
- Nunca deforme, alongue, encurte ou altere qualquer parte do produto
- Nunca crie detalhes que não aparecem nas fotos de referência
- PROIBIÇÃO DE MODIFICAR O PRODUTO: JAMAIS adicione base, pedestal, suporte, embalagem
  ou qualquer componente AO PRODUTO em si que não apareça explicitamente nas fotos de
  referência. Esta restrição se aplica ao PRODUTO — não ao cenário. Elementos de CENÁRIO
  (mesa, laço decorativo, props, ambiente, contexto) são permitidos quando o tipo de
  imagem exige (ex: Presenteie, Ambientação). O produto deve ser apresentado exatamente
  como aparece nas fotos — sem modificações nos seus componentes.
"""

# ─────────────────────────────────────────────────────────────────────────
# O QUE VALE SO NA CRIACAO, E NAO NO AJUSTE FINO
#
# Dono, 30/09, sobre o ajuste que nao saiu: "o erro esta na solicitacao
# do sistema (...) por ele estar fazendo algo errado, seja na comunicacao
# ou na analise do que precisa fazer". Ele estava certo.
#
# Estas duas clausulas sao CERTAS quando o sistema CRIA uma peca a
# partir de fotos do produto: a foto pode ter texto de embalagem, e
# medida inventada e pior que medida ausente.
#
# No AJUSTE FINO elas viram o contrario. Ali a imagem enviada e a
# PROPRIA PECA, com o texto dela — e "ignore completamente qualquer
# texto visivel nas imagens" manda ignorar justamente o texto que o
# colaborador pediu para trocar. E o numero que ele digitou no pedido
# nao esta "nos campos do produto", entao a segunda clausula manda NAO
# escreve-lo. Pedido: "trocar o texto: diametro 25 cm e peso 476 g".
# Duas regras absolutas proibindo, e o modelo obedeceu.
#
# UM TEXTO SO, usado em dois lugares — e nao duas copias que discordam
# daqui a tres semanas. A criacao recebe nucleo + estas; o ajuste
# recebe o nucleo e diz a SUA propria regra sobre inventar numero.
# ─────────────────────────────────────────────────────────────────────────
INSTRUCAO_FIDELIDADE_SO_CRIACAO = """
- NÃO copie nem reproduza nenhum texto, palavra ou rótulo que apareça escrito
  nas fotos de referência — ignore completamente qualquer texto visível nas imagens
- PROIBIÇÃO ABSOLUTA DE INVENTAR DADOS TÉCNICOS: JAMAIS crie, estime ou invente
  medidas, dimensões, peso ou material do produto. Se esses dados não foram
  fornecidos nos campos do produto, NÃO os coloque na imagem sob nenhuma hipótese.
  Imagem com dados inventados é pior do que imagem sem dados.
- Só use medidas e peso na imagem se eles estiverem EXPLICITAMENTE informados
  nos dados do produto fornecidos — nunca estime por conta própria
"""

_FIDELIDADE_ESTRUTURAL = """

INTEGRIDADE ESTRUTURAL (o que fazer quando você NÃO sabe como o produto funciona):
- NÃO invente mecânica interna: folhas soltas, páginas saindo, miolo exposto,
  abas, encaixes, dobradiças, camadas extras, peças móveis ou vãos que não
  aparecem nas fotos de referência
- Quando um ângulo ou parte interna não estiver visível nas fotos, a saída correta
  é NÃO MOSTRAR essa região — escolha um ângulo que ela não apareça. Preencher o
  desconhecido com algo plausível é erro grave, não criatividade
- Mantenha a estrutura visível exatamente como está: espessura, encadernação,
  acabamento, quantidade de partes"""

# A CRIACAO RECEBE EXATAMENTE O QUE RECEBIA ANTES — byte por byte. O ajuste
# recebe o nucleo. Uma fonte para os dois: a regra do produto nao pode ter
# duas versoes que passam a discordar.
INSTRUCAO_FIDELIDADE = (INSTRUCAO_FIDELIDADE_ABERTURA
                        + INSTRUCAO_FIDELIDADE_SO_CRIACAO.strip("\n")
                        + _FIDELIDADE_ESTRUTURAL)
INSTRUCAO_FIDELIDADE_NUCLEO = (INSTRUCAO_FIDELIDADE_ABERTURA
                               + _FIDELIDADE_ESTRUTURAL)

INSTRUCAO_COMPOSICAO = """
INSTRUÇÃO DE COMPOSIÇÃO:
- Use as imagens de referência APENAS para manter o produto reconhecível e fiel
- Componha uma cena/layout NOVO e apropriado para o tipo de imagem solicitado
- "Peça nova" refere-se a CENÁRIO, ENQUADRAMENTO e LAYOUT — nunca ao produto.
  Não reaproveite o fundo nem o enquadramento da foto de referência; o PRODUTO,
  ao contrário, deve ser reproduzido fielmente, sem reinterpretação. Criar um
  produto diferente do fotografado nunca é uma composição nova — é um erro.
"""

# ── ESTE BLOCO FALAVA DE TAMANHO, E ERA A TERCEIRA VOZ A FAZER ISSO ────────
#
# Ele ia colado em TODOS os tipos, ambientacao inclusive, dizendo "Ocupe o
# maior espaço possível no frame" e "NUNCA minimize o produto" — ao lado do
# bloco de ESCALA REAL, que diz o contrario com todas as letras: "é correto e
# desejável que o produto ocupe uma fração modesta do quadro". Enquanto o
# recorte por regex cortava os dois, ninguem via; sem o recorte, as duas
# ordens chegam juntas.
#
# O tamanho agora e assunto de `OCUPACAO`, e de mais ninguem. O que sobra
# aqui e o que so este bloco dizia: a proibicao de deformar.
INSTRUCAO_PROPORCAO = """
REGRA DE PROPORÇÃO DO PRODUTO (obrigatória):
- O produto é o elemento principal da composição — o olho vai nele primeiro.
- Mantenha as proporções exatas do produto: não alongue, não achate, não deforme.
- A medida de quanto ele ocupa do quadro está no bloco de protagonismo desta
  peça, e é de lá que ela sai — não estime outra. Se esta peça NÃO trouxer
  essa medida, é porque ela não tem número fixo: o produto aparece na escala
  real da cena. Nesse caso NÃO invente uma porcentagem e NÃO encolha o
  produto por precaução.
"""

# ── QUANTAS PALAVRAS CABEM NUM BLOCO — UMA FONTE, DOIS LEITORES ───────────
#
# Dono, 30/09: "as escritas estao sendo cortadas (...) aplicadas numa regiao
# que nao da para ser escrita totalmente e ai fica a margem para fora".
#
# A copy e escrita por um prompt (o do PLANO) e desenhada por outro (o da
# IMAGEM), e os dois nunca concordaram sobre o tamanho dela. Eram CINCO vozes:
#
#   - regra de densidade:  titulo 2-5 palavras, descricao de 8 a 16
#   - a mesma regra, 33 linhas abaixo: titulo de 2 a 4, frase de 4 a 9
#   - preset da peca 2:    titulo 2-3 palavras, frase maximo 7
#   - preset da peca 3:    frase maximo 6 palavras
#   - preset da peca 6:    pergunta maximo 5, resposta maximo 8
#   - prompt do PLANO:     titulo de 2 a 4; frase de 4 a 9
#
# Seis, contando o plano. A IA da copy escrevia no tamanho de uma delas e o
# desenhista recebia outra — frase longa num cartao dimensionado para frase
# curta transborda pela borda, e e o quadrado para fora que ele viu.
#
# A faixa da frase e a UNICA que as duas regras de densidade permitiam ao
# mesmo tempo: 8 a 9. Nao foi escolha minha, e a interseccao de [8,16] com
# [4,9]. Se o dono quiser outra, muda aqui e muda nos dois prompts.
PALAVRAS_TITULO = (2, 4)
PALAVRAS_FRASE = (8, 9)


# O CALLOUT DO CLOSE TEM MEDIDA PROPRIA, E ELA NAO E A DO CARTAO.
#
# O "ate 4 palavras" vivia dentro do texto do preset do tipo 4
# (`PRESETS["4 — Close nos detalhes"]`), onde nenhuma varredura o lia, e o
# prompt do Close recebia AO LADO dele a medida do cartao — "titulo curto em
# CAIXA ALTA (2 a 4 palavras) + frase de 8 a 9 palavras". Dois tamanhos para
# o mesmo texto na mesma mensagem: e o padrao que o oitavo verificador existe
# para pegar, e ele passou porque os dois numeros estavam em blocos
# diferentes.
PALAVRAS_CALLOUT = 4


def medida_do_callout():
    """A frase, em portugues, sobre o tamanho da legenda de um callout."""
    return (f"- Cada legenda de callout: no máximo {PALAVRAS_CALLOUT} "
            "palavras, sem título e sem frase de apoio. Legenda é etiqueta, "
            "não argumento de venda.")


def medida_do_bloco():
    """A frase, em portugues, sobre o tamanho de um bloco de texto.

    UMA FUNCAO, E NAO UM TEXTO COPIADO: o prompt da IMAGEM e o prompt do
    PLANO leem os dois daqui. Era a copia entre eles que fazia a IA escrever
    num tamanho e o desenhista dimensionar para outro.
    """
    return (f"titulo curto em CAIXA ALTA ({PALAVRAS_TITULO[0]} a "
            f"{PALAVRAS_TITULO[1]} palavras) + frase de {PALAVRAS_FRASE[0]} a "
            f"{PALAVRAS_FRASE[1]} palavras").replace("titulo", "título")


# O texto renderizado obedece as mesmas regras no cartao e no callout: ele
# e o mesmo defeito nos dois ("Profess commerco" nao fica menos
# constrangedor por estar numa legenda fina). Por isso vive fora das duas
# instrucoes de layout e e costurado nas duas — um texto, um dono.
INSTRUCAO_TEXTO_REAL = """REGRA DE TEXTO REAL (o erro mais constrangedor):
- TODO texto renderizado deve ser português correto e existir de verdade. É
  PROIBIDO inventar palavras, misturar idiomas ou desenhar texto decorativo
  ilegível que "pareça" escrita. Nada de "Profess commerco", "High-resolução"
  ou variações — isso destrói a credibilidade do anúncio.
- NENHUMA palavra em inglês na peça, em lugar nenhum. Isso inclui o CENÁRIO:
  lombada de livro, capa de caderno, tela de computador, etiqueta, embalagem e
  placa. Se um objeto do cenário teria texto, escreva-o em português do Brasil
  — ou desenhe o objeto sem texto legível.
- Quanto mais longa a frase, mais letra inventada aparece nela: a medida do
  bloco está escrita uma vez só, e em um lugar só nesta mensagem.
- Pontuação fechada: parêntese que abre, fecha. Nada de "(exemplo," solto no
  meio de uma frase.
- NÃO INVENTE TEXTO: o que se escreve já veio pronto no bloco de TEXTO
  EXATO. Não há nada a inventar, e a quantidade continua sendo a que esta
  mensagem já fechou — aconteça o que acontecer.
- PROIBIDO desenhar logotipo, marca, monograma ou assinatura sobre o produto ou
  na peça. O produto não tem logo — não crie um.
"""

# "Nada sobre o produto" vale no cartao e no callout, e por isso mora fora
# dos dois. Escrita duas vezes, ela viraria duas redacoes — e `checar_prompts`
# procura a FRASE: a copia que mudasse uma palavra passaria a faltar numa das
# peças sem ninguem ver.
INSTRUCAO_NADA_SOBRE_O_PRODUTO = (
    "- PROIBIÇÃO ABSOLUTA: JAMAIS sobreponha texto, ícone, título ou qualquer "
    "elemento gráfico\n  diretamente sobre o produto. O produto deve estar em "
    "zona limpa, sem nada sobre ele.")

# ── O CLOSE NAO E PECA DE MARKETING, E RECEBIA A REGRA DELAS ───────────────
#
# `INSTRUCAO_LAYOUT_MARKETING` dizia "obrigatória para tipos 2, 3, 4, 5, 6 e 7"
# e mandava, para TODOS eles: zona de texto com painel, cartao retangular de
# cantos arredondados, fundo claro solido, icone line-art, coluna vertical
# encostada num lado.
#
# O preset do proprio tipo 4 manda o CONTRARIO, e esta escrito duas telas
# acima: "Callouts discretos com linha fina + legenda de ate 4 palavras",
# "ZERO medidas, ZERO setas de dimensao", "isso e uma foto de qualidade, nao
# infografico tecnico". Duas vozes sobre a mesma peca, e o gerador escolhe —
# e escolheu a que tinha mais linhas: o close da Caneca Medieval em 02/10
# saiu com dois cartoes brancos de icone line-art, do tamanho de um terco do
# quadro, sobre a foto macro.
#
# Entao a regra passa a ser POR TIPO. O que vale para os dois caminhos — nada
# sobre o produto, folga da borda, texto real em portugues, nao inventar —
# fica no bloco comum; o que e de cartao fica so com quem tem cartao.
INSTRUCAO_LAYOUT_CLOSE = """
REGRA DE LAYOUT DO CLOSE (esta peça NÃO é peça gráfica de marketing):
- Esta é uma FOTOGRAFIA MACRO. Não é infográfico, não é peça de anúncio com
  cartões. PROIBIDO desenhar cartão, painel, caixa de texto, faixa, selo,
  ícone line-art, tag ou qualquer bloco gráfico sobre a imagem.
{nada_sobre_o_produto}
- Quando — e SOMENTE quando — houver TEXTO EXATO para esta peça, ele aparece
  como CALLOUT: uma linha fina saindo do ponto do produto até uma legenda
  curta, em área limpa FORA do produto. Sem fundo, sem moldura, sem ícone.
- ZERO medidas e ZERO setas de dimensão. Medida é a peça 5, não esta.
{blocos}
{palavras_close}
{texto_real}
"""

INSTRUCAO_LAYOUT_SEM_TEXTO = """
REGRA DE LAYOUT DESTA PEÇA (ela NÃO tem bloco de texto):
{nada_sobre_o_produto}
- Esta peça é FOTOGRAFIA. Não é peça gráfica: PROIBIDO desenhar cartão,
  painel, caixa de texto, faixa, selo, ícone line-art, tag, callout ou
  qualquer bloco gráfico sobre a imagem.
{blocos}
{texto_real}
"""

INSTRUCAO_LAYOUT_MARKETING = """
REGRA DE LAYOUT PARA IMAGENS DE MARKETING (obrigatória para tipos 2, 3, 5, 6 e 7):
{nada_sobre_o_produto}
- A composição é dividida em ZONAS DISTINTAS e separadas:
    ZONA DO PRODUTO: área exclusiva do produto, sem texto, sem overlays, sem elementos
    gráficos sobre ele. O produto é exibido em fundo limpo dentro dessa zona.
    ZONA DE TEXTO: painéis laterais, faixas superiores/inferiores ou blocos ao lado do produto,
    com fundo sólido ou semi-transparente, onde ficam títulos, ícones, benefícios e frases.
- O produto NUNCA serve de fundo para texto — qualquer legenda, benefício ou frase
  deve estar em área própria adjacente ao produto, não sobreposta a ele.
- A imagem final deve ter aparência de peça gráfica profissional de e-commerce,
  criada por um estúdio de marketing — não de uma foto com texto editado por cima.

REGRA DE DENSIDADE:
- A IMAGEM DE REFERÊNCIA DE LAYOUT, QUANDO HOUVER, MANDA NO ESTILO: posição
  dos cartões, forma, cor, tipografia, ícones e espaçamento. Ela NÃO manda na
  QUANTIDADE de cartões nem no TAMANHO do texto — esses dois já vêm resolvidos
  nas linhas abaixo, e nada nesta peça os altera.
{blocos}
- Cada bloco: {palavras}. Descrição de 3 palavras deixa a peça pobre e sem
  argumento de venda; descrição longa não cabe no cartão e transborda pela
  borda.
- FORMA DO CARTÃO, IGUAL EM TODAS AS PEÇAS: retângulo de cantos arredondados,
  fundo claro sólido, ícone line-art próprio, todos com a MESMA largura e o
  mesmo estilo dentro da peça.
- POSIÇÃO, quando NÃO houver referência de layout: UMA coluna vertical única,
  encostada em UM dos lados do quadro (esquerda ou direita), com os cartões
  empilhados e espaçamento igual entre eles. NUNCA em grade, NUNCA
  distribuídos pelos quatro cantos, NUNCA uma fileira no rodapé, NUNCA metade
  de um lado e metade do outro.
- QUANDO HOUVER referência de layout, a POSIÇÃO é a dela — inclusive se for
  grade. A referência é o padrão aprovado da empresa e manda sobre a coluna
  única; o que NÃO muda com ela é a folga das bordas logo abaixo: mesmo
  copiando a referência, nenhum cartão toca ou cruza a borda.
- CADA CARTÃO INTEIRO DENTRO DO QUADRO, respeitando a folga da borda definida
  na REGRA DE ESPAÇO DESTA PEÇA: o primeiro começa abaixo do topo e o último
  termina acima da base, com o fundo da cena aparecendo acima do primeiro e
  abaixo do último. Cartão que toca a borda é peça reprovada.
- A QUANTIDADE DE CARTÕES JÁ CABE: ela foi calculada para ESTA peça, com ESTA
  folga, antes de este texto ser escrito. Não reduza o número para fazer caber,
  não junte dois num só, não deixe nenhum de fora. Faltando espaço, diminua a
  ALTURA e o ESPAÇAMENTO dos cartões — nunca a quantidade, nunca comprima o
  texto a ponto de cortar, nunca empilhe até a borda, nunca deixe um pela
  metade.
- Espaçamento uniforme entre blocos, sem que um encoste no outro
- NUNCA adicione tags, selos, rodapés, ícones de compatibilidade ou elementos
  decorativos além dos blocos pedidos

{texto_real}
"""

def instrucao_de_layout(tipo, blocos, palavras):
    """A regra de layout DESTA peça. Um dono por tipo, e não uma só para seis.

    O tipo 4 (Close) recebia a regra das peças de marketing e saía
    infográfico: cartão retangular, fundo claro, ícone line-art — enquanto o
    preset dele, duas telas acima no mesmo prompt, pedia "callouts discretos
    com linha fina" e "ZERO setas de dimensão". Duas vozes sobre a mesma
    peça; o gerador seguiu a que tinha mais linhas.

    Quem não tem texto nenhum (1 e 8) não recebe regra de layout de texto:
    mandar regra de cartão para a capa em fundo branco é oferecer cartão.
    """
    n = numero_do_tipo(tipo)
    if n in (1, 8):
        return ""
    if n == 4:
        return INSTRUCAO_LAYOUT_CLOSE.format(
            blocos=blocos, palavras_close=medida_do_callout(),
            nada_sobre_o_produto=INSTRUCAO_NADA_SOBRE_O_PRODUTO,
            texto_real=INSTRUCAO_TEXTO_REAL)
    # ── A MEDIDA DO CARTAO SO VAI QUANDO HA CARTAO ───────────────────────
    #
    # ACHADO EM PRODUCAO, 05/10, e e a METADE QUE FALTOU da correcao de
    # 02/10 — a Forma 1 cometida dentro do conserto da Forma 1.
    #
    # Em 02/10 eu travei a linha que PEDE os blocos: sem copy, ela passou a
    # dizer "NAO escreva nenhuma palavra". E deixei `{palavras}` saindo
    # incondicionalmente. Resultado medido no prompt real das pecas 5 e 7:
    #
    #   - Esta peca NAO recebeu copy (...) NAO escreva nenhuma palavra
    #   - Cada bloco: titulo curto em CAIXA ALTA (2 a 4 palavras) + frase...
    #
    # Duas linhas seguidas, uma proibindo e a outra ensinando a escrever — e
    # a segunda e LITERALMENTE o texto que o Gemini desenhou dentro do
    # cartao no teste anterior ("TITULO CURTO EM CAIXA ALTA: TEXTURA UNICA E
    # PROFUNDA").
    #
    # Sem bloco de texto, nada que fale de cartao entra: nem a medida, nem a
    # forma, nem a posicao, nem a contagem. O que sobra e a zona limpa e o
    # texto real — que valem de qualquer jeito.
    if MARCA_SEM_COPY in blocos:
        return INSTRUCAO_LAYOUT_SEM_TEXTO.format(
            blocos=blocos,
            nada_sobre_o_produto=INSTRUCAO_NADA_SOBRE_O_PRODUTO,
            texto_real=INSTRUCAO_TEXTO_REAL)
    return INSTRUCAO_LAYOUT_MARKETING.format(
        blocos=blocos, palavras=palavras,
        nada_sobre_o_produto=INSTRUCAO_NADA_SOBRE_O_PRODUTO,
        texto_real=INSTRUCAO_TEXTO_REAL)


# ── MODO PERSONALIZADO — sem branding automático ──────────────────────────────
INSTRUCAO_PERSONALIZADO = """
MODO PERSONALIZADO — REGRAS ABSOLUTAS:
- Execute EXATAMENTE e SOMENTE o que o colaborador descreveu nas instruções
- NÃO adicione texto, legenda, título, rótulo ou qualquer elemento escrito
  que não tenha sido pedido explicitamente nas instruções
- NÃO aplique cores da empresa, fontes específicas, ícones ou branding
  a não ser que as instruções peçam explicitamente por isso
- NÃO crie uma composição "nova" ou "melhorada" por conta própria —
  siga a instrução, nada mais
- NÃO invente diferenciais, características ou frases de marketing
- As instruções do colaborador são a ÚNICA fonte de verdade para
  o que deve aparecer nesta imagem
"""

# ── MODO AJUSTE FINO — edição cirúrgica, sem alterar nada além do pedido ─────
INSTRUCAO_AJUSTE_FINO = """
MODO AJUSTE FINO — EDIÇÃO CIRÚRGICA — REGRAS ABSOLUTAS E INVIOLÁVEIS:

1. Faça SOMENTE a modificação descrita na instrução — absolutamente nada mais
2. Preserve a composição inteira: fundo, cenário, iluminação, cores, perspectiva,
   todos os objetos e todos os detalhes visuais
3. Preserve os textos que já existem na imagem — EXCETO o texto que a
   modificação pedida mandar trocar, corrigir ou acrescentar. Se o pedido
   for sobre texto, faça exatamente esse texto e deixe todos os outros
   intactos. Não mexa em texto que o pedido não citou.
4. Preserve a aparência do produto: mesma cor, mesmos detalhes, mesmos
   elementos visíveis (furos, padrões, logotipos na embalagem, etc.) —
   EXCETO no ponto que a modificação pedida citar. Preservar o produto
   nunca é motivo para deixar de fazer o que foi pedido.
5. NÃO "melhore", "enriqueça", "atualize" ou "harmonize" nada além do pedido
6. NÃO aplique identidade visual, branding, cores ou fontes da empresa
7. NÃO adicione nenhum objeto, efeito, texto ou elemento não mencionado
8. Se a instrução pedir redimensionar o produto: altere APENAS o tamanho relativo
   do produto dentro da cena — todo o resto permanece pixel-a-pixel idêntico
9. Se não tiver certeza de algo que não foi mencionado, mantenha como está
"""

# ── PRESETS ATUALIZADOS COM IDENTIDADE VISUAL ─────────────────────────────────
TIPOS_PADRAO = [
    "1 — Capa do anúncio (fundo branco)",
    "2 — Benefícios do produto",
    "3 — Benefícios no cenário de uso",
    "4 — Close nos detalhes",
    "5 — Características técnicas (medidas/peso/material)",
    "6 — Quebra de objeção",
    "7 — Presenteie",
    "8 — Ambientação realista (sem texto)",
]

# O rotulo do botao dizia "As 7 imagens do padrao" com oito tipos na lista: o
# plano listava ate a 8 e o resumo falava em "6 de 8 viaveis". Contar a lista
# mantem os dois numeros amarrados quando um tipo entrar ou sair.
_OPCAO_PADRAO = f"As {len(TIPOS_PADRAO)} imagens do padrão"

PRESETS = {
    "Personalizado (descrevo o que quero)": "",
    "1 — Capa do anúncio (fundo branco)": (
        "CAPA DO ANÚNCIO — FOTO PRINCIPAL DO PRODUTO: REGRA ABSOLUTA: ZERO TEXTO, ZERO TÍTULO, ZERO ÍCONE. "
        "APENAS o produto sobre fundo branco puro — esta é a primeira imagem que o comprador vê. "
        "FUNDO: branco puro (#FFFFFF), absolutamente liso, sem gradiente, sem sombra, sem elementos. "
        "Produto centralizado e O MAIOR POSSÍVEL, encostando quase nas bordas, sem "
        "cortar nenhuma parte e sem distorcer as proporções reais. Margem branca "
        "mínima — sobra de fundo é desperdício de área nesta imagem, que é a "
        "primeira que o comprador vê. A medida exata da ocupação está no bloco de "
        "protagonismo, mais abaixo. "
        "Iluminação profissional de estúdio: luz suave e uniforme, sombra mínima e delicada embaixo. "
        "Posição: ângulo frontal ligeiramente 3/4 que mostra melhor o produto, ou frontal direto. "
        "Resultado: foto de e-commerce de alta qualidade — limpa, profissional, produto é tudo."
    ),
    "2 — Benefícios do produto": (
        "IMAGEM DE MARKETING — BENEFÍCIOS: produto em zona central limpa (SEM texto sobre ele). "
        "Fundo deduzido do produto — sem cor de marca fixa. Benefícios em cartões — a POSIÇÃO, a FORMA e a quantidade deles saem da regra de densidade, não daqui; siga a referência de layout quando houver: "
        "ícone line-art na cor da direção de arte escolhida para ESTE produto — não existe cor "
        "de ícone fixa — + título curto + frase direta, no tamanho que a REGRA DE "
        "DENSIDADE manda. "
        "Visual arejado — jamais comprima ou empilhe os blocos de benefício, e jamais deixe faixa vazia em volta da peça. "
        "Os textos dos benefícios vêm dos diferenciais e características do produto informados."
    ),
    "3 — Benefícios no cenário de uso": (
        "IMAGEM DE MARKETING — PRODUTO NO AMBIENTE DE USO REAL: deduza das fotos e dos dados "
        "onde ESTE produto é de fato usado, e por quem — não escolha de uma lista pronta de "
        "cômodos. Produto protagonista em cena aspiracional, com a luz e a paleta que "
        "valorizem este produto. Frases de destaque em cartões fora do produto (nunca sobre "
        "ele) — posição, forma, quantidade e TAMANHO saem da regra de densidade. "
        "Cada frase: curta e impactante. Sem cor de "
        "marca fixa: fundo e elementos gráficos saem da direção de arte deste produto. "
        "Visual editorial — parece foto de lifestyle de qualidade, não montagem amadora."
    ),
    "4 — Close nos detalhes": (
        "CLOSE NO PRODUTO — ZOOM REAL EM DETALHE ESPECÍFICO: NÃO mostre o produto inteiro. "
        "Recorte e amplie UMA área específica do produto: textura do material, acabamento, encaixe, "
        "mecanismo, superfície, ou detalhe que justifique qualidade e diferencial. "
        "Fundo desfocado (bokeh) com produto em foco nítido no primeiro plano. "
        "A MONTAGEM TEM NOME, E ELE ESTÁ NOS DADOS: se o campo de material disser "
        "espiral, Wire-O, costura, colagem, rebite ou encaixe, é ESSA a montagem "
        "que aparece no close. Não escreva nem desenhe outra — um álbum de espiral "
        "ampliado numa costura que ele não tem é a pior imagem possível desta peça, "
        "porque é justamente a que existe para provar a construção. "
        "A SUPERFÍCIE É A DAS FOTOS, NÃO UMA INVENTADA: aproxime APENAS de uma área "
        "que apareça nítida nas fotos de referência, e reproduza o relevo, a "
        "granulação, as marcas e as manchas exatamente como estão lá. Não acrescente "
        "textura, poro, rachadura, desgaste, veio ou mancha de cor que não exista na "
        "foto. Se nenhuma área estiver nítida o bastante para um macro, aproxime "
        "menos — enquadramento mais aberto e fiel vale mais que macro inventado. "
        # O TAMANHO DA LEGENDA SAIU DAQUI, e foi para `medida_do_callout()`.
        # Escrito aqui, ele chegava ao modelo ao lado da medida do CARTAO
        # ("titulo curto em CAIXA ALTA (2 a 4) + frase de 8 a 9"), que o
        # bloco de layout mandava para todos os seis tipos. Dois tamanhos
        # para o mesmo texto, em blocos diferentes da mesma mensagem.
        "Callouts discretos com linha fina, na medida que a regra de layout "
        "desta peça define, posicionados "
        "em área limpa FORA do produto. Tom: premium, artesanal, qualidade perceptível. "
        "ZERO medidas, ZERO setas de dimensão — isso é uma foto de qualidade, não infográfico técnico."
    ),
    "5 — Características técnicas (medidas/peso/material)": (
        "INFOGRÁFICO TÉCNICO DE MEDIDAS — estilo cota de catálogo: produto grande e "
        "centralizado, fotografado nítido, ocupando o miolo da peça. "
        "CADA dimensão recebe SEU PRÓPRIO indicador, nunca uma linha de texto corrida: "
        "uma seta ou linha de cota TRACEJADA saindo da borda exata que está sendo medida, "
        "terminando num CARTÃO de cantos arredondados, fundo branco e borda fina na cor da "
        "direção de arte deste produto — não existe cor de borda fixa —, "
        "contendo o rótulo em caixa alta pequena (ALTURA, LARGURA, PROFUNDIDADE, PESO) e, "
        "logo abaixo, o valor em número grande e negrito. "
        "Os cartões ficam distribuídos ao redor do produto — em cima, nas laterais e "
        "embaixo — cada um junto da medida que representa, nunca empilhados num canto. "
        "Setas nas duas pontas das linhas de cota, no eixo correto de cada medida. "
        "CADA MEDIDA APARECE UMA VEZ SÓ na peça inteira, e apenas dentro do cartão "
        "dela: a linha de cota não leva número solto ao lado da seta. Valor repetido "
        "em dois lugares é erro. "
        "Os cartões de cota são áreas sólidas SOBRE a cena — a cena não vira fundo chapado "
        "por causa deles. ZERO ícones decorativos, ZERO blocos de benefício, ZERO frases de venda. "
        "Use APENAS os valores informados nos dados do produto — JAMAIS invente ou estime medidas. "
        "Se medidas não foram informadas, omita-as completamente — não crie números fictícios."
    ),
    "6 — Quebra de objeção": (
        "IMAGEM DE MARKETING — RESPONDENDO DÚVIDAS DO COMPRADOR: layout clean com produto "
        "em destaque e blocos de pergunta+resposta em cartões — posição, forma e "
        "quantidade saem da regra de densidade, não daqui; siga a referência de layout quando houver. "
        "Cada bloco: pergunta em destaque + check verde + resposta direta, as duas no "
        "tamanho que a REGRA DE DENSIDADE manda. As objeções são baseadas nos "
        "diferenciais e características do produto. "
        "Visual arejado, sem faixa vazia em volta da peça; fundo e paleta deduzidos do produto e da ocasião."
    ),
    "7 — Presenteie": (
        "IMAGEM EMOCIONAL — A ENTREGA DO PRESENTE: DUAS PESSOAS na cena, uma "
        "ENTREGANDO o produto à outra como presente. Não é o produto sozinho com um "
        "laço: é o momento da entrega, com as mãos de quem dá e de quem recebe "
        "visíveis e o produto entre elas. "
        "O PAR SAI DO PRODUTO, não de uma escolha aleatória — deduza das fotos e dos "
        "dados para quem este produto é: "
        "produto infantil, um pai ou mãe entregando ao filho ou filha; "
        "produto de adulto, um homem entregando a uma mulher; "
        "quando as fotos e os dados não permitirem decidir, duas pessoas adultas numa "
        "entrega afetuosa, sem forçar relação nenhuma. "
        "O produto aparece INTEIRO e NÍTIDO, no primeiro plano, entre as mãos — nunca "
        "escondido pelos dedos, nunca cortado, nunca desfocado. As pessoas são o "
        "contexto: enquadre do tronco para baixo, ou com os rostos suaves e em segundo "
        "plano, para que o olho vá ao produto primeiro. "
        "Contexto visual de presente — embrulho, fita ou caixa — quando fizer sentido "
        "para o produto, sempre secundário à entrega. "
        "Frase grande e impactante em destaque: \'Presenteie com\' + nome do produto, "
        "ou frase emotiva. "
        "Visual limpo, tons suaves e elegantes, luz natural. "
        "Se nenhuma frase específica foi fornecida, crie uma frase genérica adequada ao produto."
    ),
    # A contradição morava AQUI também, e não só no bloco de padrão visual:
    # "ZERO TEXTO" e, duas linhas depois, "escreva Imagem meramente
    # ilustrativa". E a lista de cômodos — escritório, quarto de estudos,
    # estante de livros — é semanticamente errada para metade do catálogo: um
    # marcador de taça não pertence a nenhum deles.
    "8 — Ambientação realista (sem texto)": (
        "FOTO EDITORIAL — PRODUTO NO AMBIENTE NATURAL DE USO. "
        "Deduza das fotos e dos dados onde ESTE produto é de fato usado, e por "
        "quem; não escolha de uma lista pronta de cômodos. Construa a cena com "
        "a paleta, a luz e os materiais que valorizem este produto — sem cor "
        "de fundo padrão. O produto é a peça protagonista, grande e nítido; "
        "quando o cenário competir com ele, desfoque o fundo. "
        "Tom: revista de decoração/lifestyle — parece fotografia real, não "
        "montagem digital. A regra de texto está detalhada mais abaixo."
    ),
}


# ── TRIAGEM POR IA (análise textual, sem gastar com geração) ──────────────────

def gerar_triagem_ia(nome_produto, tipos_selecionados, dados_descricao, instrucoes_extras, fotos_bytes):
    """Pede para a IA analisar o que ela criaria para cada tipo de imagem,
    ANTES de gastar com a geração real. Retorna lista de dicts com o plano."""
    # PELA FUNCAO, E NAO POR `st.secrets.get` DIRETO.
    #
    # `st.secrets.get` nao e dicionario comum: sem arquivo de secrets ele
    # LEVANTA em vez de devolver o padrao — e o `or os.environ.get(...)` que
    # vinha depois nunca chegava a rodar. Numa maquina que guarda a chave so
    # em variavel de ambiente, a triagem morria com
    # `StreamlitSecretNotFoundError` em vez de usar a chave que estava la.
    #
    # `_chave_anthropic` existe exatamente por isso, e o comentario dela
    # descreve esta armadilha. Tres lugares nao a usavam.
    api_key = _chave_anthropic()
    if not api_key:
        return None, "ANTHROPIC_API_KEY não configurada."

    # NUMERADA PELA POSICAO, E DITO COM TODAS AS LETRAS.
    #
    # A IA reordenava e renomeava os tipos, e devolvia `numero` como a
    # sequencia do plano DELA. So que `tipo_canonico` usa esse numero como
    # indice na lista — entao o cartao "Caracteristicas Tecnicas" com
    # numero 2 virava "2 — Beneficios do produto", e o infografico de medidas
    # ia ao gerador com as regras de painel de beneficios.
    tipos_str = "\n".join(
        f"[{i}] {t}\n     {PRESETS.get(t, '')[:300]}..."
        for i, t in enumerate(tipos_selecionados, 1))

    # QUANTAS PEÇAS, E POR EXTENSO — o número vem da LISTA, nunca escrito.
    #
    # 28/09, produção: o dono escolheu UM tipo e o plano voltou com OITO
    # cartões, todos iguais. O prompt dizia "as 8 peças", "oito cenas",
    # "nenhuma outra das oito" — quatro vezes, fixo. A IA obedeceu o NÚMERO
    # e ignorou a lista de tipos, que tinha um só. A tela acusou "a análise
    # embaralhou os tipos" e os avisos saíam comparando "Personalizado com
    # Personalizado".
    _n_pecas = len(tipos_selecionados)
    _EXTENSO = {1: "uma", 2: "duas", 3: "três", 4: "quatro", 5: "cinco",
                6: "seis", 7: "sete", 8: "oito", 9: "nove", 10: "dez"}
    _n_ext = _EXTENSO.get(_n_pecas, str(_n_pecas))

    contexto_descricao = ""
    if dados_descricao:
        contexto_descricao = f"""
DADOS DA DESCRIÇÃO DO PRODUTO (vinculados pelo código):
- Cor: {dados_descricao.get('cor', 'não informada')}
- Material e montagem: {dados_descricao.get('material', 'não informado')}
- Medidas: {dados_descricao.get('medidas', 'não informadas')}
- Peso: {dados_descricao.get('peso', 'não informado')}
- Categoria: {dados_descricao.get('categoria', 'não informada')}
- Diferenciais: {dados_descricao.get('diferenciais', 'não informados')}
- Características: {dados_descricao.get('caracteristicas', 'não informadas')}
- Uso: {dados_descricao.get('uso', 'não informado')}
"""

    # Verifica quais dados técnicos estão disponíveis para informar a IA
    dados_disponiveis = []
    dados_faltantes = []
    if dados_descricao:
        if dados_descricao.get("medidas"): dados_disponiveis.append(f"medidas: {dados_descricao['medidas']}")
        else: dados_faltantes.append("medidas (altura × largura × profundidade)")
        if dados_descricao.get("peso"): dados_disponiveis.append(f"peso: {dados_descricao['peso']}")
        else: dados_faltantes.append("peso")
        if dados_descricao.get("cor"): dados_disponiveis.append(f"cor: {dados_descricao['cor']}")
        if dados_descricao.get("material"):
            # DIZER "MATERIAL INFORMADO" NAO E INFORMAR O MATERIAL.
            #
            # Era isto que a analise recebia: a palavra "informados", sem o
            # valor. Com o valor ela pode nomear a encadernacao Wire-O na
            # peca de close em vez de inventar uma costura.
            dados_disponiveis.append(f"material: {dados_descricao['material']}")
        elif dados_descricao.get("caracteristicas"):
            dados_disponiveis.append("características informadas")
        else: dados_faltantes.append("material")
    else:
        dados_faltantes = ["medidas", "peso", "material"]

    resumo_dados = ""
    if dados_disponiveis:
        resumo_dados += f"Dados disponíveis: {', '.join(dados_disponiveis)}\n"
    if dados_faltantes:
        resumo_dados += f"Dados NÃO informados (não inventar): {', '.join(dados_faltantes)}\n"

    prompt = f"""Você é especialista em imagens para e-commerce no Mercado Livre. Seja BREVE e DIRETO.

PRODUTO: {nome_produto}
{contexto_descricao}
{resumo_dados}
FOTOS ENVIADAS: {len(fotos_bytes)} foto(s) de referência
{f"INSTRUÇÕES EXTRAS: {instrucoes_extras}" if instrucoes_extras else ""}

TIPOS A CRIAR — são estes, nesta ordem, e o número entre colchetes é o que
vale:
{tipos_str}

REGRA DE IDENTIDADE DOS TIPOS, ANTES DE QUALQUER OUTRA COISA:
- O campo "numero" é o NÚMERO ENTRE COLCHETES do tipo, e nada mais. Não é a
  ordem do seu plano, não é uma contagem sua.
- O campo "tipo" é o nome do tipo COPIADO LETRA POR LETRA da lista acima,
  incluindo o prefixo "N — ". Não reescreva, não resuma, não melhore, não
  traduza.
- Devolva UM item por tipo, na MESMA ORDEM da lista. Não junte dois tipos num
  item, não invente tipo que não está na lista, não troque a posição.
- Isto não é formalidade: o Studio acha as regras de cada peça por esse
  número. Número trocado gera a peça com as regras da peça errada.

TAREFA: duas coisas, nesta ordem.

PRIMEIRO — A DIREÇÃO DE ARTE DO PRODUTO, DECIDIDA UMA VEZ SÓ
-------------------------------------------------------------
Antes de planejar qualquer imagem, olhe as fotos e decida o universo visual
DESTE produto. Essa decisão vale para as {_n_pecas} peça(s) e não se repete: cada peça
vai HERDAR o que você decidir aqui, não decidir de novo.

Como decidir, em ordem de peso:
1. Cor real e distribuição de cor do produto (30%) — dominante, secundárias,
   detalhes de contraste, temperatura.
2. Material e acabamento (20%) — fosco, acetinado, brilhante, metálico,
   translúcido, texturizado, natural, sintético. O cenário complementa o
   material.
3. Posicionamento (20%) — premium, elegante, técnico, divertido, delicado,
   romântico, industrial, minimalista, contemporâneo, rústico, prático.
4. Ambiente natural de uso (15%) — deduzido do produto, nunca de uma lista
   pronta de cômodos.
5. Ocasião e público (10%) — uso pessoal, profissional, decoração,
   organização, presente, celebração.
6. Legibilidade gráfica (5%) — contraste para título, cota, ícone e callout.

O AMBIENTE SE ADAPTA AO PRODUTO, NUNCA O CONTRÁRIO. A paleta manda em fundo,
superfície, props, painel, tipografia e ícone — e em nada do produto. Nunca
escolha uma direção que exija repintar o produto.

SEPARAÇÃO, NÃO COMBINAÇÃO. Não derive o fundo da cor do produto: produto
escuro pede entorno mais claro ou contraste controlado; produto claro pede
separação média ou mais escura; produto muito colorido pede entorno neutro.
Fundo parecido demais com o produto mata a separação, que é o contrário de
valorizar.

REFLEXO. Se o produto é brilhante, metálico, espelhado ou transparente,
evite superfície grande e saturada perto dele: o reflexo do ambiente muda a
cor percebida do produto. Classifique o risco em BAIXO, MEDIO ou ALTO.

SEGUNDO — O PLANO DAS 8, COM CENAS DIFERENTES
----------------------------------------------

DUAS PEÇAS NUNCA REPETEM O MESMO AMBIENTE. Dito pelo dono em 28/09:
"temos diversas opções de ambientação, então o estúdio não pode utilizar dois
ambientes iguais, exatamente iguais".
- Consistência é mesma PALETA, mesmo MATERIAL e mesma LUZ — não a mesma mesa.
- Duas cenas sobre madeira são a mesma cena, ainda que uma diga "madeira
  clara" e a outra "madeira escura". Vale para linho, mármore, concreto,
  couro, vidro, cerâmica: a SUPERFÍCIE só aparece uma vez no plano inteiro.
- Antes de escrever a cena de uma peça, olhe as que você já escreveu e
  escolha uma superfície e um ambiente que ainda não usou.
- Se acabarem as superfícies plausíveis para este produto, mude o ÂNGULO e a
  distância em vez de repetir a mesa — nunca repita para preencher.

E O PRODUTO NÃO APARECE SEMPRE DO MESMO LADO. Também dito pelo dono:
"o produto às vezes tem dois lados com desenhos diferentes; o estúdio precisa
variar, não colocar sempre o mesmo lado. Não sempre de frente, às vezes de
lado, mostrar a parte de trás também, caso tenha".
- OLHE AS FOTOS: se elas mostram frente, verso, lateral, tampa ou base com
  acabamentos, gravações ou desenhos DIFERENTES, o plano tem de mostrar essas
  faces ao longo das peças — não a mesma foto {_n_ext} vezes.
- AS FOTOS MANDAM, E ESTA REGRA VEM DEPOIS DELAS. Varie o ângulo APENAS entre
  os ângulos que as fotos realmente mostram. Se todas as fotos mostram o mesmo
  lado, TODAS as peças usam esse lado — repetir o ângulo que existe é certo;
  inventar um que não existe é o mesmo erro de inventar textura, e produz
  produto torto, alça a mais e produto diferente do real.
- NÃO escreva nada em `pergunta_info` por causa de ângulo. Esse campo é
  EXCLUSIVO de peça inviável, e preenchê-lo aqui faz a peça ser descartada.
  Falta de foto de um ângulo NUNCA torna uma peça inviável.
- No campo "cena" de cada peça, diga qual face e qual ângulo aparecem.

Para cada tipo, analise se é VIÁVEL gerar com as informações e fotos disponíveis.

REGRAS DE VIABILIDADE — CRÍTICO:
1. "Características técnicas (medidas/peso/material)" → SOMENTE viável se medidas E peso estiverem nos dados disponíveis acima. Se qualquer um faltar, marque viavel: false e peça os dados exatos.
2. "Close nos detalhes" → SEMPRE viável se houver pelo menos 1 foto do produto. A IA faz zoom em detalhe das fotos existentes — NUNCA peça foto adicional de close para este tipo.
3. Qualquer tipo que necessite de informação específica ausente (ex: cores disponíveis, voltagem, compatibilidade) → viavel: false, peça a informação.
4. NUNCA marque como viável se for necessário INVENTAR qualquer dado técnico, dimensão ou característica.

Quando viavel: false, preencha "pergunta_info" com pergunta direta e específica ao colaborador explicando exatamente o que falta e por quê é necessário. Essa imagem será DESCARTADA até a informação ser fornecida.

Quando viavel: true, descreva em 1-2 frases o que será criado.

O CAMPO "textos" É A COPY FINAL, PALAVRA POR PALAVRA — leia com atenção:
- O gerador de imagem NÃO escreve texto: ele DESENHA letras. Quando ele
  precisa inventar a frase, sai coisa como "Apretica newtona estético" e
  "relievarriamento do stresse" — palavras que não existem, numa peça que foi
  parar na tela do gestor. Quem escreve a frase é VOCÊ, aqui, e ele só copia.
- Escreva cada bloco já pronto, no formato "TÍTULO CURTO: frase curta".
  {medida_do_bloco()}. Frase longa é o que ele erra: quanto mais palavra, mais
  letra inventada — e frase que não cabe no cartão transborda pela borda.
- Português do Brasil, e SÓ português do Brasil. Nenhuma palavra em inglês,
  nem "premium", "design", "kit", "home office" ou nome técnico em inglês.
  Se o termo só existe em inglês, escreva o equivalente em português.
- Ortografia e acentuação corretas, frase que faz sentido sozinha. Nada de
  parêntese aberto e não fechado, nada de "(exemplo," no meio da frase.
- De 2 a 5 blocos, conforme o tipo pedir. Bloco a menos é melhor que bloco
  com texto inventado — se falta informação para um bloco, não o escreva.
- Nada de dado técnico que não esteja nas informações acima.
- Para os tipos SEM texto (capa em fundo branco e ambientação), "textos" vem
  como lista vazia.

PORTUGUÊS EM TODOS OS CAMPOS, E NÃO SÓ NA COPY:
- "atmosfera", "luz", "composicao", "cena" e "trava_do_produto" também são
  português do Brasil. Saíram "moments de intimidade", "sem harshness" e
  "background desfocado" — em campos que ninguém estava conferindo.
- Escreva "momentos", "sem dureza", "ao fundo". Nome de cor, de material e de
  tipografia seguem a mesma regra.

A MONTAGEM SÓ TEM O NOME QUE OS DADOS DEREM:
- Se o campo de material nomear a montagem — espiral, Wire-O, costura, colagem,
  rebite, encaixe —, use ESSE nome. Não troque por outro que soe parecido.
- Se os dados NÃO nomearem a montagem, não invente uma: escreva "a montagem
  visível nas fotos". A peça de close existe para provar a construção, e
  ampliar uma costura num álbum de espiral é o pior erro que ela pode ter.

O CAMPO "trava_do_produto" CONSTATA, NUNCA DEDUZ:
- Escreva o que as fotos MOSTRAM: material, acabamento, geometria, montagem.
- NÃO escreva cor deduzida, nem "cor não informada", nem "provavelmente", nem
  "harmoniza com". A cor do produto tem trava própria, montada pelo sistema a
  partir do cadastro e das fotos — e ela PROÍBE deduzir cor para harmonizar.
  Duas travas discordando na mesma mensagem é pior que uma só.

O CAMPO "cena" — {_n_ext.upper()} CENA(S), UM UNIVERSO SÓ
--------------------------------------------
Consistência NÃO é repetir o mesmo cenário. Oito imagens com a mesma mesa, os
mesmos props e o mesmo ângulo estão tecnicamente consistentes e o anúncio
fica repetitivo — foi o que aconteceu: escrivaninha com caneta na 3, na 7 e
na 8.

Pense como fotógrafo de produto planejando o catálogo inteiro de uma vez.
Mantenha igual em todas: família de cor, vocabulário de materiais, caráter da
luz, nível de acabamento, posicionamento. Varie de propósito em cada uma:
superfície, arquitetura do fundo, ângulo de câmera, recorte, profundidade,
escolha e arranjo de props, espaço negativo.

Escreva em "cena" UMA frase curta com a superfície, os props e o ângulo DESTA
peça — e confira que nenhuma outra das {_n_ext} repete a mesma combinação. Não
reutilize o mesmo prop decorativo em duas peças sem motivo forte.

Capa (fundo branco) e Características técnicas são as exceções: nelas "cena"
descreve só a superfície e a sombra, sem props.

Responda SOMENTE com JSON válido, sem texto antes ou depois:
{{
  "direcao_de_arte": {{
    "nome": "nome curto da direção, ex: Executivo Quente Contemporâneo",
    "posicionamento": "premium / delicado / técnico / divertido / ...",
    "atmosfera": "uma frase sobre o universo visual deste produto",
    "paleta": {{
      "fundo":   {{"nome": "Marfim Quente", "hex": "#F2EEE6"}},
      "painel":  {{"nome": "Pedra Quente", "hex": "#D5C9B8"}},
      "titulo":  {{"nome": "Grafite Espresso", "hex": "#292520"}},
      "apoio":   {{"nome": "Nogueira", "hex": "#695445"}},
      "acento":  {{"nome": "Dourado Envelhecido", "hex": "#B18A4A"}}
    }},
    "materiais": ["3 a 5 materiais de cenário deste universo"],
    "luz": "temperatura, qualidade e contraste numa frase",
    "saturacao": "MUITO BAIXA / BAIXA / MEDIA / ALTA",
    "props_preferidos": ["props que reforçam uso, escala ou posicionamento"],
    "props_proibidos": ["props que competem com o produto ou parecem acompanhar"],
    "risco_de_reflexo": "BAIXO / MEDIO / ALTO",
    "trava_do_produto": "uma frase com o que JAMAIS muda: cor, material e acabamento reais"
  }},
  "plano": [
    {{
      "tipo": "nome do tipo",
      "numero": 1,
      "composicao": "1-2 frases curtas descrevendo a imagem (só se viavel: true)",
      "cena": "superfície, props e ângulo desta peça — diferente das outras sete",
      "textos": ["TÍTULO CURTO: frase pronta em português", "OUTRO TÍTULO: outra frase pronta"],
      "flags": [],
      "viavel": true,
      "pergunta_info": ""
    }}
  ],
  "observacao_geral": "uma frase resumindo o conjunto, ou string vazia"
}}
"""

    client = anthropic.Anthropic(api_key=api_key)
    try:
        # SETE MINUTOS DE SPINNER SEM MENSAGEM NENHUMA.
        #
        # Aconteceu na analise de 24/09, com 14 imagens: a chamada ficou
        # pendurada mais de sete minutos, sem plano e sem erro, e quem estava
        # na tela teve de recarregar e refazer — gastando duas analises.
        #
        # Sem prazo, a espera e infinita, e o colaborador le "travou". Com
        # prazo, ela vira erro em tres minutos, e o erro tem nome — que e o
        # que o `except` abaixo transforma em plano de emergencia.
        msg = client.messages.create(
            model="claude-haiku-4-5",
            timeout=180.0,
            max_tokens=6144,
            messages=[{"role": "user", "content": _idioma.com_regra(prompt)}]
        )
        texto = msg.content[0].text.strip()

        # Se a resposta foi cortada (max_tokens atingido), avisa mas tenta salvar
        truncado = msg.stop_reason == "max_tokens"

        # ── Extração robusta de JSON ───────────────────────────────────────────
        import re as _re

        def _tentar_parse(s):
            try:
                return json.loads(s)
            except Exception:
                return None

        resultado = None

        # 1. Texto direto
        resultado = _tentar_parse(texto)

        # 2. Bloco ```json ... ``` (regex, mais confiável que split)
        if resultado is None:
            m = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texto, _re.DOTALL)
            if m:
                resultado = _tentar_parse(m.group(1))

        # 3. Primeiro { até o último }
        if resultado is None:
            start = texto.find("{")
            end = texto.rfind("}")
            if start != -1 and end > start:
                resultado = _tentar_parse(texto[start:end + 1])

        if resultado is not None:
            return resultado, None

        # ── Fallback: plano básico com presets ────────────────────────────────
        motivo = (
            "resposta da IA truncada (max_tokens atingido)" if truncado
            else "resposta da IA não estava em formato JSON válido"
        )
        plano_fallback = {
            "plano": [
                {
                    "tipo": t,
                    "numero": i + 1,
                    "composicao": PRESETS.get(t, ""),
                    "cena": "",
                    "textos": [],
                    "flags": [],
                    "viavel": True,
                    "pergunta_info": "",
                }
                for i, t in enumerate(tipos_selecionados)
            ],
            "observacao_geral": (
                f"⚠️ A triagem detalhada não pôde ser gerada ({motivo}). "
                "O plano abaixo usa os presets padrão de cada tipo. "
                "Revise as instruções antes de confirmar a geração."
            ),
        }
        return plano_fallback, None

    except Exception as e:
        return None, str(e)


# ── GERAÇÃO DE IMAGEM (Imagen 3 via Vertex AI) ────────────────────────────────

# Nome legivel de cada formato, para a mensagem que o colaborador le. Ele nao
# tem que saber o que e "image/avif" — tem que saber que mandou um AVIF.
NOME_FORMATO = {
    "image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WebP",
    "image/gif": "GIF", "image/bmp": "BMP", "image/tiff": "TIFF",
    "image/avif": "AVIF", "image/heic": "HEIC (foto de iPhone)",
    "image/svg+xml": "SVG (desenho vetorial)", "application/pdf": "PDF",
}


def _detectar_mime(data: bytes) -> str:
    """MIME real pelos magic bytes. "" quando não dá para reconhecer.

    O fallback antigo era `return "image/jpeg"`, comentado como "fallback
    seguro". Ele era o contrário disso: dizia que TODO arquivo irreconhecível
    era JPEG, e como JPEG está em _MIMES_ACEITOS, `normalizar_imagem` devolvia
    o arquivo intocado. A conversão de HEIC, AVIF, GIF, BMP e TIFF que a função
    promete no docstring nunca chegava a rodar — era código morto desde o
    primeiro `if`. O arquivo seguia para o gerador e para a tela como se fosse
    JPEG, e o Pillow estourava lá na frente, com um traceback que não diz nada
    a quem só anexou uma imagem.

    Mentir sobre o tipo não é um fallback. "Não sei" é uma resposta melhor:
    quem chama decide o que fazer, e agora pode converter ou avisar.
    """
    if not data:
        return ""
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if data[:2] == b'\xff\xd8':
        return "image/jpeg"
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return "image/webp"
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return "image/gif"
    if data[:2] == b'BM':
        return "image/bmp"
    if data[:4] in (b'II*\x00', b'MM\x00*'):
        return "image/tiff"
    if data[:4] == b'%PDF':
        return "application/pdf"
    # AVIF e HEIC sao caixas ISO-BMFF: o tipo esta na marca logo apos "ftyp".
    if data[4:8] == b'ftyp':
        marca = data[8:12]
        if marca in (b'avif', b'avis'):
            return "image/avif"
        if marca in (b'heic', b'heix', b'hevc', b'heim', b'heis', b'mif1',
                     b'msf1'):
            return "image/heic"
    cabeca = data[:400].lstrip()
    if cabeca[:5] == b'<?xml' or cabeca[:4] == b'<svg':
        return "image/svg+xml"
    return ""


def _normalizar_nome(texto):
    """Minúsculas, sem acento e só letras/números — para casar nome de arquivo com tipo."""
    import unicodedata as _ud
    import re as _re_nome
    t = _ud.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii").lower()
    return _re_nome.sub(r"[^a-z0-9]+", " ", t).strip()


_SINONIMOS_TIPO = {
    "1 —": {"capa", "principal", "branco", "fundo"},
    "2 —": {"beneficios", "beneficio", "vantagens", "features"},
    "3 —": {"cenario", "uso", "lifestyle", "contexto", "pessoas", "rotina"},
    "4 —": {"close", "detalhe", "detalhes", "zoom", "macro"},
    "5 —": {"medidas", "medida", "dimensoes", "dimensao", "tecnicas", "tecnica",
            "caracteristicas", "especificacoes", "specs", "tamanho", "peso", "material"},
    "6 —": {"objecao", "objecoes", "duvidas", "duvida", "perguntas", "faq"},
    "7 —": {"presente", "presentear", "presenteie", "gift", "brinde"},
    "8 —": {"ambiente", "ambientacao", "ambientada", "editorial", "cena"},
}

# Palavras que aparecem em quase todo nome de arquivo e em varios tipos. Contar
# essas como acerto fazia "Produto com fundo branco" casar com "Beneficios do
# produto" — layout errado copiado por causa de uma palavra generica.
_PALAVRAS_VAZIAS = {
    "de", "do", "da", "no", "na", "em", "com", "os", "as", "nos", "que", "ele",
    "produto", "produtos", "anuncio", "imagem", "imagens", "foto", "fotos",
    "arquivo", "referencia", "layout", "modelo", "exemplo", "cliente", "final",
}


def _palavras_uteis(texto):
    return {
        p for p in _normalizar_nome(texto).split()
        if len(p) > 2 and p not in _PALAVRAS_VAZIAS
    }


def _pontuar_ref(tipo, nome_arquivo):
    """Quantas palavras significativas o nome do arquivo tem em comum com o tipo."""
    alvo = _palavras_uteis(tipo)
    for prefixo, sinonimos in _SINONIMOS_TIPO.items():
        if tipo.startswith(prefixo):
            alvo |= sinonimos
            break
    return len(alvo & _palavras_uteis(nome_arquivo.rsplit(".", 1)[0]))


def ref_layout_do_tipo(tipo, refs_bytes, refs_nomes):
    """Escolhe a imagem de referencia de layout que pertence a este tipo.

    O colaborador nomeia os arquivos pelo que eles representam — "Presenteie
    (frases impactantes)", "Caracteristicas (medidas/peso/material).webp". A
    escolha e por essas palavras, nao por ordem de upload: enviar as referencias
    fora de ordem nao pode embaralhar as pecas.

    O casamento e MUTUO: a referencia so e usada por este tipo se este tipo for
    tambem a melhor correspondencia dela. Sem isso, uma peca sem referencia
    propria roubava a de outra por uma palavra solta em comum — foi assim que
    "Beneficios do produto" ficou com a referencia de fundo branco.

    Retorna (bytes, nome) ou (None, None). Sem correspondencia a peca e gerada
    sem referencia, o que e melhor do que gerar com a referencia de outro tipo.
    """
    if not refs_bytes or not refs_nomes:
        return None, None

    melhor_i, melhor_nota = None, 0
    for i, nome in enumerate(refs_nomes):
        if i >= len(refs_bytes):
            break
        nota = _pontuar_ref(tipo, nome)
        if nota <= 0 or nota <= melhor_nota:
            continue
        # A referencia pertence a este tipo? Se ela pontua mais alto em outro,
        # e daquele outro.
        if any(_pontuar_ref(t, nome) > nota for t in TIPOS_PADRAO):
            continue
        melhor_i, melhor_nota = i, nota

    if melhor_i is None:
        return None, None
    return refs_bytes[melhor_i], refs_nomes[melhor_i]


def _gerar_imagem_thread(prompt_texto, imagens_ref, resultado, refs_layout=None,
                         refs_layout_nomes=None, tipo=""):
    """Executa gerar_imagem_ia em thread separada para não bloquear o WebSocket."""
    try:
        _diag = {}
        img, erro = gerar_imagem_ia(
            prompt_texto, imagens_ref, refs_layout=refs_layout,
            refs_layout_nomes=refs_layout_nomes, tipo=tipo, diagnostico=_diag
        )
        resultado["img"] = img
        resultado["erro"] = erro
        resultado["diag"] = _diag
    except Exception as e:
        resultado["img"] = None
        resultado["erro"] = str(e)
    finally:
        resultado["done"] = True


def _get_gemini_api_key():
    """Retorna a GEMINI_API_KEY das secrets ou variável de ambiente."""
    # Mesma armadilha do `st.secrets.get` que levanta sem arquivo de secrets.
    import chaves as _ch_gem
    key = _ch_gem.ler("GEMINI_API_KEY")
    return key


# A descrição de produto e de layout, guardada por conteúdo. Vive no processo:
# uma geração de 8 peças acontece numa passada só, e é aí que os 7 repetidos
# acontecem. Pequeno de propósito — não é cache de sessão, é de lote.
_DESCRICAO_CACHE = {}
_DESCRICAO_CACHE_MAX = 8


def _assinatura_das_fotos(imagens, refs_layout, nome_produto, dados):
    """A chave do cache: o conteúdo, não o nome. Trocar a foto troca a chave."""
    import hashlib
    h = hashlib.sha1()
    h.update(str(nome_produto or "").encode("utf-8"))
    h.update(repr(sorted((dados or {}).items())).encode("utf-8"))
    for grupo in (imagens or [], refs_layout or []):
        h.update(b"|")
        for b in grupo:
            try:
                h.update(hashlib.sha1(bytes(b)).digest())
            except Exception:
                h.update(b"?")
    return h.hexdigest()


def _descricao_do_produto_cacheada(imagens_referencia, nome_produto="produto",
                                   dados_descricao=None, refs_layout=None):
    """`_descrever_produto_via_claude`, uma vez por conjunto de fotos."""
    chave = _assinatura_das_fotos(imagens_referencia, refs_layout,
                                  nome_produto, dados_descricao)
    if chave in _DESCRICAO_CACHE:
        return _DESCRICAO_CACHE[chave]
    fora = _descrever_produto_via_claude(
        imagens_referencia, nome_produto, dados_descricao, refs_layout)
    # Só guarda o que deu certo: descrição vazia por falha de rede não pode
    # virar a resposta das sete peças seguintes.
    if fora and fora[0]:
        if len(_DESCRICAO_CACHE) >= _DESCRICAO_CACHE_MAX:
            _DESCRICAO_CACHE.pop(next(iter(_DESCRICAO_CACHE)))
        _DESCRICAO_CACHE[chave] = fora
    return fora


def _descrever_produto_via_claude(imagens_referencia, nome_produto="produto", dados_descricao=None, refs_layout=None):
    """Claude Vision analisa as fotos do produto e retorna:
    - descricao_produto: descrição ultra-detalhada em inglês (substitui inlineData)
    - estilo_layout: descrição textual do estilo/composição das refs de layout

    NENHUMA foto vai ao modelo gerador — apenas estas descrições em texto.
    Esta é a peça mais crítica da nova arquitetura: a qualidade da descrição
    determina diretamente a qualidade da imagem gerada.
    """
    api_key = _chave_anthropic()

    descricao_produto = f"Product: {nome_produto}. Visual details not available."
    estilo_layout = ""

    if not api_key:
        return descricao_produto, estilo_layout

    # ── PARTE 1: Descrever o produto com ultra-detalhe ────────────────────────
    if imagens_referencia:
        content = [{"type": "text", "text": "Analyze these product photos:"}]
        for img_bytes in imagens_referencia[:4]:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": _detectar_mime(img_bytes),
                    "data": base64.b64encode(img_bytes).decode("utf-8"),
                }
            })

        dados_str = ""
        if dados_descricao:
            partes = []
            if dados_descricao.get("cor"):
                partes.append(f"Color: {dados_descricao['cor']}")
            if dados_descricao.get("medidas"):
                partes.append(f"Dimensions: {dados_descricao['medidas']}")
            if dados_descricao.get("peso"):
                partes.append(f"Weight: {dados_descricao['peso']}")
            mat = dados_descricao.get("material") or dados_descricao.get("caracteristicas", "")
            if mat:
                partes.append(f"Material: {mat[:100]}")
            if partes:
                dados_str = f"\nKnown specs: {' | '.join(partes)}"

        content.append({
            "type": "text",
            "text": (
                f"You are a hyper-detailed visual analyst. An AI image generator will recreate "
                f"this product based ONLY on your text description — it will NEVER see these photos. "
                f"Your description is the only bridge.\n\n"
                f"Product: {nome_produto}{dados_str}\n\n"
                "Write a HYPER-DETAILED visual description in English (15-20 sentences) structured as:\n\n"
                "SHAPE & GEOMETRY: Exact 3D form, overall silhouette, proportions (estimated "
                "width:height:depth ratio), curvature or angularity, primary and secondary geometric shapes.\n\n"
                "COLORS: Every color present, precisely named with intensity/saturation "
                "(e.g., \"deep sapphire blue\", \"warm ivory white\", \"brushed silver-gray\"). "
                "Which surfaces carry which color. Any gradients or transitions.\n\n"
                "SURFACE & MATERIALS: Texture quality (matte/semi-gloss/glossy/metallic), "
                "material type (hard plastic, rubber, brushed metal, glass, wood, etc.), "
                "surface finish details, tactile quality implied visually.\n\n"
                "COMPONENTS & DETAILS: Every distinct visible element — buttons, ports, seams, joints, "
                "decorative lines, raised/recessed areas, logos, patterns. Each described with "
                "position and visual appearance.\n\n"
                "SCALE & PROPORTIONS: Estimated real-world size relative to familiar objects, "
                "visual weight, overall footprint.\n\n"
                "LIGHTING & REFLECTIVITY: How light interacts with each surface — highlights, "
                "reflections, matte absorption, any translucency.\n\n"
                "Rules:\n"
                "- Extremely specific — every adjective matters for the generator\n"
                "- Only describe what is ACTUALLY VISIBLE in the photos\n"
                "- Do NOT invent details not clearly visible\n"
                "- This description must enable recreation of the product from words alone\n\n"
                "Write ONLY the description. Start immediately with \"SHAPE & GEOMETRY:\"."
            )
        })

        try:
            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=2000,
                messages=[{"role": "user", "content": _idioma.com_regra(content)}]
            )
            descricao_produto = msg.content[0].text.strip()
        except Exception:
            pass

    # ── PARTE 2: Descrever estilo das refs de layout em texto ─────────────────
    if refs_layout:
        content_layout = [{"type": "text", "text": "Analyze the visual composition style of these marketing reference images:"}]
        for img_bytes in refs_layout[:2]:
            content_layout.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": _detectar_mime(img_bytes),
                    "data": base64.b64encode(img_bytes).decode("utf-8"),
                }
            })
        content_layout.append({
            "type": "text",
            "text": (
                "Describe the COMPOSITION STYLE of these reference images for an AI that will "
                "replicate this layout structure (not the specific product, just the layout).\n\n"
                "Cover in 6-8 sentences:\n"
                "- Overall layout zones (product placement, text placement, proportions)\n"
                "- Text hierarchy (headers vs subheads vs callouts — size, weight, position)\n"
                "- Visual style (clean/dense, flat/layered, minimal/rich)\n"
                "- Use of whitespace and breathing room\n"
                "- Grid/alignment structure (centered, left-aligned, asymmetric)\n"
                "- Element count and spacing feel\n\n"
                # NEM COR, NEM O QUE O PRODUTO DA REFERÊNCIA É.
                #
                # Aqui se pedia "Color distribution", e a descrição voltava
                # com "aquecedor vermelho", "azul-marinho corporativo",
                # "personagens interagindo" — o produto e a paleta de OUTRA
                # empresa. Esse texto entrava no prompt logo acima da linha
                # que PROÍBE copiar produto e cores da referência: ordem e
                # contraordem na mesma mensagem, e o gerador pegava a cor.
                #
                # A referência serve para POSIÇÃO, HIERARQUIA e RESPIRO. A
                # cor sai do produto, e só dele.
                "HARD RULES for your description:\n"
                "- NEVER name or describe the object shown in the reference. "
                "Call it only 'the product'. Writing 'red heater', 'red "
                "kettle' or any object name is a failure.\n"
                "- NEVER mention any colour, hue, palette or tone — not of "
                "the product, not of the text, not of the background.\n"
                "- NEVER mention people, hands, models or scenes.\n"
                "- Describe ONLY geometry: where blocks sit, how big, how "
                "they align, how much space between them.\n\n"
                "Write ONLY the composition description. Start directly."
            )
        })

        try:
            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=800,
                messages=[{"role": "user", "content": _idioma.com_regra(content_layout)}]
            )
            estilo_layout = limpar_descricao_de_layout(
                msg.content[0].text.strip())
        except Exception:
            pass

    return descricao_produto, estilo_layout


# ── PEDIR GENTILMENTE AO MODELO NAO E GARANTIA ──────────────────────────────
#
# A descricao da referencia de layout e pedida com HARD RULES claras: nao
# nomeie o objeto, nao mencione cor nenhuma, nao mencione pessoas, descreva so
# geometria. Mesmo assim ela voltou com "chaleira vermelha", "bule vermelho",
# "titulos em azul-marinho", "paleta monocromatica (azul-marinho + preto +
# branco)" e "dois personagens interagem naturalmente".
#
# E esse texto entra no prompt final logo acima da linha que PROIBE copiar
# produto, cores e pessoas da referencia. Ordem e contraordem na mesma
# mensagem — com a contraordem em quatro paragrafos e a ordem em uma linha.
#
# E A PALETA AZUL VOLTANDO PELA SEXTA VEZ, por um caminho que nenhuma
# varredura alcancava: as outras cinco estavam em texto FIXO do codigo, e
# `checar_prompts.py` pega cor fixa em template. Esta nasce em tempo de
# execucao, escrita por outro modelo, e nao existe no arquivo para ser
# encontrada.
#
# Instrucao no pedido e um convite. Filtro na volta e uma regra. Isto e o
# filtro: a descricao que desobedece e DESCARTADA inteira, porque uma
# descricao contaminada vale menos que nenhuma — sem ela o tipo ainda tem as
# proprias regras de layout; com ela, o gerador recebe a cor de outra empresa.
_CORES_PROIBIDAS_NO_LAYOUT = (
    "azul", "vermelh", "verde", "amarel", "laranja", "roxo", "rosa",
    "marrom", "bege", "dourad", "prate", "preto", "branco", "cinza",
    "marinho", "turquesa", "violeta", "bordo", "salmao", "salmão",
    "blue", "red", "green", "yellow", "orange", "purple", "pink",
    "brown", "beige", "gold", "silver", "black", "white", "grey", "gray",
    "navy", "teal", "crimson", "magenta", "cyan",
    "colour", "color", "palette", "paleta", "tonalidade", "matiz",
)
# Pessoa na descricao contradiz "NEVER add people" na mesma mensagem.
# OS RADICAIS SAO BILINGUES; O AVISO NA TELA, NAO.
#
# O aviso saiu assim: "Ela voltou mencionando menciona cor ou paleta: branco,
# red". Duas coisas numa frase — o verbo duplicado, porque o motivo ja trazia
# "menciona" e o texto do aviso acrescentava "mencionando"; e "red" em ingles
# num aviso em portugues, porque o radical achado ia cru para a tela.
#
# Quem le esse aviso e o colaborador, e ele decide trocar a referencia por
# causa dele.
_EM_PORTUGUES = {
    "blue": "azul", "red": "vermelho", "green": "verde", "yellow": "amarelo",
    "orange": "laranja", "purple": "roxo", "pink": "rosa", "brown": "marrom",
    "beige": "bege", "gold": "dourado", "silver": "prateado", "black": "preto",
    "white": "branco", "grey": "cinza", "gray": "cinza", "navy": "azul-marinho",
    "teal": "verde-azulado", "crimson": "carmesim", "magenta": "magenta",
    "cyan": "ciano", "colour": "cor", "color": "cor", "palette": "paleta",
    "person": "pessoa", "people": "pessoas", "character": "personagem",
    "hand": "mão", "vermelh": "vermelho", "amarel": "amarelo",
    "dourad": "dourado", "prate": "prateado", "deduzid": "deduzido",
}

# ── FIGURA HUMANA TEM UMA LISTA SO ──────────────────────────────────────────
#
# Eram DUAS, e elas discordavam. A do layout nao tinha "casal", "familia",
# "bebe", "menino", "menina" nem "maos" no plural; a da cena nao tinha
# "person", "people", "character" nem "hand". Uma descricao de referencia com
# "um casal ao fundo" passava pelo filtro; um plano em ingles passava pelo
# aviso da tela.
#
# O CLAUDE.md desta base chama isso pelo nome: uma regra e uma regra, e nao
# uma copia. Quando a mesma pergunta tem duas respostas no codigo, elas passam
# a discordar — a questao e so quando.
PESSOAS = (
    "pessoa", "personagem", "homem", "mulher", "crianca", "criança",
    "casal", "familia", "família", "bebe", "bebê", "menino", "menina",
    "mao", "mão", "maos", "mãos",
    "person", "people", "character", "hand", "couple", "family",
    "child", "kid", "baby", "man", "woman",
    # "model" e "modelo" ficam de fora: "modelo de grade" e "composicao
    # modular" sao legitimos, e descartar uma descricao boa tambem e defeito.
)

# Os dois nomes antigos continuam existindo para quem ja lia por eles, mas
# apontam para a MESMA lista — que e o ponto.
_PESSOAS_NO_LAYOUT = PESSOAS


def _acha_radicais(texto, radicais):
    """Os radicais que aparecem NO COMECO de uma palavra do texto.

    INICIO DE PALAVRA, E NAO PEDACO DELA — a diferenca nao e detalhe.
    A primeira versao disto procurava por pedaco, e o meu proprio teste
    reprovou na primeira linha: "margens generosas" foi descartada por conter
    "rosa" dentro de "generosas". Uma descricao de layout perfeita, jogada
    fora por casamento cego.
    
    Casar por pedaco de palavra ja trocou produto por produto nesta base, e a
    regra do dono e explicita sobre isso. Com `\b` no inicio e `\w*` no fim,
    "azul" pega "azul", "azulado" e "azul-marinho" (o hifen e limite de
    palavra), e nao pega "generosas".
    """
    import re as _re_rad
    achados = set()
    for radical in radicais:
        if _re_rad.search(r"\b" + _re_rad.escape(radical) + r"\w*", texto):
            achados.add(radical)
    return sorted(achados)


# ── DUAS TRAVAS DE COR NO MESMO PROMPT, DE FONTES DIFERENTES ────────────────
#
# A analise escreveu, no campo `trava_do_produto`:
#
#     "peso 700g — cor nao informada, mas deducao visual e tom neutro/escuro
#      que harmoniza com universo de repouso visual"
#
# E no MESMO prompt, `_trava_cor_produto` escreve:
#
#     "a cor do produto e a que aparece nas fotos. Reproduza-a exatamente,
#      seja ela qual for. E PROIBIDO recolorir o produto para harmonizar com
#      a direcao de arte"
#
# A analise fez exatamente o que a outra trava proibe: DEDUZIU cor para
# harmonizar. E as cinco fotos eram inequivocamente pretas — nao era "cor nao
# informada", era cor nao DIGITADA no cadastro.
#
# A regra da casa e uma fonte por regra. A cor do produto tem dona:
# `_trava_cor_produto`, que sai do cadastro e das fotos. O campo da analise
# descreve material, acabamento e geometria — nunca cor deduzida.
#
# O corte e por FRASE, e nao o campo inteiro: "Album quadrado 30x30 com capa
# dura fosca" e informacao boa, e jogar fora junto com a deducao seria trocar
# um defeito por outro.
_DEDUCAO_NA_TRAVA = (
    "deducao", "dedução", "deduzid", "deduzo", "nao informada", "não informada",
    "nao informado", "não informado", "harmoniza", "harmonizar", "presumo",
    "presumivel", "presumível", "provavelmente", "suponho", "imagino",
    "aparenta ser", "parece ser", "estimad",
)


def limpar_trava_do_produto(texto):
    """A trava da analise, sem as frases que DEDUZEM em vez de constatar.

    Devolve ("", motivo) quando nao sobra frase nenhuma.
    """
    bruto = str(texto or "").strip()
    if not bruto:
        return "", ""
    import re as _re_tv
    # CORTAR SO NO PONTO NAO BASTA — a deducao vem colada por travessao.
    #
    # O caso real: "Album quadrado 30x30 com capa dura fosca, folhas pretas
    # internas, peso 700g — cor nao informada, mas deducao visual e tom
    # neutro/escuro". Uma frase so, pelo ponto: cortando so no ponto, ou some
    # tudo (inclusive a informacao boa) ou nao some nada. A primeira versao
    # disto apagou a trava inteira, e o teste pegou.
    #
    # Entao o corte tambem e no travessao e no ", mas " — que e onde a
    # constatacao acaba e a especulacao comeca.
    frases = [f.strip(" ,;")
              for f in _re_tv.split(r"(?<=[.;])\s+|\s+—\s+|,\s+mas\s+", bruto)
              if f and f.strip(" ,;")]
    ficam, saem = [], []
    for f in frases:
        if _acha_radicais(f.lower(), _DEDUCAO_NA_TRAVA):
            saem.append(f)
        else:
            ficam.append(f)
    if not saem:
        return bruto, ""
    motivo = "frase(s) de dedução removida(s): " + " | ".join(s[:90] for s in saem[:3])
    try:
        import log_imagem
        log_imagem.registrar("trava_deduzida", "", resultado=motivo[:400])
    except Exception:
        pass
    return " ".join(ficam).strip(), motivo


def motivos_para_descartar_layout(texto):
    """Por que esta descricao de layout nao pode entrar no prompt. [] se pode."""
    t = str(texto or "").lower()
    if not t.strip():
        return []
    motivos = []
    achadas = _acha_radicais(t, _CORES_PROIBIDAS_NO_LAYOUT)
    if achadas:
        motivos.append("cor ou paleta (" + ", ".join(
            _EM_PORTUGUES.get(c, c) for c in achadas[:6]) + ")")
    pessoas = _acha_radicais(t, _PESSOAS_NO_LAYOUT)
    if pessoas:
        motivos.append("pessoas (" + ", ".join(
            _EM_PORTUGUES.get(p, p) for p in pessoas[:4]) + ")")
    return motivos


# O ULTIMO DESCARTE, PARA A TELA PODER CONTAR.
#
# O filtro jogava a descricao fora em silencio. O colaborador subia uma
# referencia de layout, ela ia para o lixo, e ele achava que o layout tinha
# sido copiado — as oito pecas saiam sem orientacao de composicao nenhuma e
# ninguem ficava sabendo que pagou esse preco.
#
# Vive no processo, como o modelo descoberto: a tela le logo depois de montar
# o prompt, e um registro por container basta.
#
# LIMITE CONHECIDO, E DITO: o `session_state` do Streamlit e por sessao, mas
# isto aqui e do PROCESSO. Com dois colaboradores no mesmo container, um
# descarte de um poderia aparecer na tela do outro. A tela chama
# `esquecer_descarte_de_layout()` imediatamente antes de montar os prompts e
# le logo depois, o que fecha quase toda a janela — mas nao toda.
#
# Fica assim de proposito: `limpar_descricao_de_layout` roda de dentro de uma
# thread, onde `session_state` nao existe (e a mesma armadilha documentada em
# `registrar_revisao`), e o pior caso aqui e um aviso a mais na tela de
# alguem. Prompt errado, nao — o texto enviado nao depende deste registro.
_ULTIMO_DESCARTE_LAYOUT = {"motivo": "", "trecho": ""}


def descarte_de_layout():
    """O ultimo descarte de descricao de layout. {} quando nao houve."""
    return dict(_ULTIMO_DESCARTE_LAYOUT) if _ULTIMO_DESCARTE_LAYOUT["motivo"] else {}


def esquecer_descarte_de_layout():
    _ULTIMO_DESCARTE_LAYOUT.update({"motivo": "", "trecho": ""})


def limpar_descricao_de_layout(texto):
    """A descricao, ou "" quando ela desobedeceu as regras do pedido."""
    motivos = motivos_para_descartar_layout(texto)
    if motivos:
        _ULTIMO_DESCARTE_LAYOUT.update(
            {"motivo": "; ".join(motivos), "trecho": str(texto)[:200]})
        try:
            import log_imagem
            log_imagem.registrar(
                "layout_descartado", "",
                resultado="; ".join(motivos) + " | " + str(texto)[:300])
        except Exception:
            pass
        return ""
    return str(texto or "").strip()


# Quando a resposta do gerador significa DINHEIRO ACABANDO, e não sorte.
#
# Só o 429 era tratado como cota. O 402 — que é o que o Google devolve quando o
# SALDO PRÉ-PAGO zera, e não a cota por minuto — passava direto pelo
# `return resp, None` como se fosse resposta boa, e chegava à tela como
# "Erro HTTP 402: Your prepayment credits are depleted", sem dizer que o que
# faltava era saldo. Tentar de novo nunca resolve este caso.
_HTTP_SEM_CREDITO = (402,)  # Payment Required — saldo zerado, jamais transitório
_PALAVRAS_DE_COTA = (
    "quota", "exhausted", "resource_exhausted", "billing", "credit",
    "prepayment", "depleted", "insufficient", "saldo",
)


def _resposta_sem_credito(status, mensagem="", estado=""):
    """A resposta do gerador é 'acabou o crédito'? Vale para qualquer motor.

    O que muda entre motores é o código e o texto; a consequência é a mesma —
    repetir a chamada não traz imagem, e quem lê a tela precisa saber que o que
    falta é saldo. Um 429 sem nenhuma dessas palavras continua sendo lentidão,
    e continua valendo a pena repetir.
    """
    if status in _HTTP_SEM_CREDITO:
        return True
    if estado == "RESOURCE_EXHAUSTED":
        return True
    texto = (mensagem or "").lower()
    return any(p in texto for p in _PALAVRAS_DE_COTA)


def _chamar_gemini_geracao_texto(prompt_final, imagens_bytes=None,
                                 ref_layout=None, diagnostico=None):
    """Chama Gemini Flash Image COM as fotos do produto como referência visual.

    Antes esta função mandava só texto — havia até um comentário declarando
    "TEXTO APENAS — zero inlineData". Isso nunca foi limitação da ferramenta: o
    endpoint generateContent aceita partes inline_data desde sempre. Era escolha
    do código.

    A consequência era grave e silenciosa: quando o gerador principal falhava, a
    imagem era montada por um modelo que NUNCA VIU o produto. Ele reconstruía o
    item a partir da descrição em texto, e a cor mais afirmada no prompt é a
    paleta azul da marca — foi assim que um álbum preto saiu azul-marinho
    repetidas vezes, com folhas brancas e proporções que não batiam.

    Agora as fotos vão junto, como no caminho da OpenAI. Fidelidade ao produto
    não pode depender de qual motor atendeu.
    """
    import time as _time
    MAX_TENTATIVAS = 2
    MODELO = "gemini-3.1-flash-image"

    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            _GEMINI_LIMITER.aguardar()
            api_key = _get_gemini_api_key()
            if not api_key:
                return None, "GEMINI_API_KEY não configurada nas secrets do Railway."
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO}:generateContent"
            headers = {
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            }
            # As fotos do produto vão PRIMEIRO, para o modelo ancorar nelas, e o
            # texto depois. Mesmo limite de 3 usado no caminho da OpenAI.
            parts = []
            for img_b in fotos_para_o_motor(imagens_bytes):
                _d_norm, _m_norm, _ = normalizar_imagem(img_b)
                parts.append({
                    "inline_data": {
                        "mime_type": _m_norm,
                        "data": base64.b64encode(_d_norm).decode("utf-8"),
                    }
                })
            # Referência de layout por último, como no caminho da OpenAI.
            if ref_layout:
                _d_rl, _m_rl, _ = normalizar_imagem(ref_layout)
                parts.append({
                    "inline_data": {
                        "mime_type": _m_rl,
                        "data": base64.b64encode(_d_rl).decode("utf-8"),
                    }
                })
            parts.append({"text": prompt_final})
            # A PROPORÇÃO, QUE NUNCA IA — e era ela que criava as tarjas.
            #
            # O corpo só tinha `responseModalities`. O modelo escolhia o
            # formato, costumava devolver retangular, e o enquadramento do
            # Studio preenchia as sobras com faixa de cor lisa: as "margens
            # laterais" que o dono viu, e o produto encolhido no meio.
            #
            # PEDIR E, SE FOR RECUSADO, REPETIR SEM PEDIR.
            #
            # A documentação do Google se contradiz sobre o nome do campo —
            # `responseFormat.image.aspectRatio` no generateContent, e
            # `response_format.aspect_ratio` na Interactions API, que é outra
            # coisa. Não dá para ter certeza sem tentar, e chutar errado em
            # silêncio seria o pior dos dois mundos: acharíamos que está
            # resolvido. Então manda; se a API recusar o formato (400), repete
            # sem ele, e o log diz qual das duas valeu.
            _base_body = {"contents": [{"role": "user", "parts": parts}]}

            # PEDIR O QUADRADO DE TODOS OS JEITOS DOCUMENTADOS, ATE UM COLAR.
            #
            # 30/09: o Studio mandava UM nome de campo — `responseFormat` —,
            # a API respondia 400, e ele desistia da proporcao. Toda peca
            # voltava retangular, o enquadramento preenchia as sobras, e a
            # pessoa recebia a peca COM MARGEM. Eu cheguei a dizer ao dono que
            # isso "nao tinha conserto por codigo". Tinha: era o nome do campo.
            #
            # A documentacao do Google descreve DOIS formatos diferentes, e os
            # dois sao oficiais, para endpoints diferentes:
            #   generateContent .... generationConfig.imageConfig.aspectRatio
            #   Interactions API ... response_format.aspect_ratio
            # Chutar qual vale nesta versao do modelo e o que nos trouxe ate
            # aqui. Entao o Studio nao chuta: ele TENTA, na ordem documentada,
            # e GUARDA qual colou — igual ao que ja faz com o modelo da OpenAI
            # ("pergunta a propria conta" em vez de confiar num nome escrito
            # a mao). Um rename futuro custa uma tentativa a mais, e nao
            # semanas de peca com margem.
            _formas = [
                ("imageConfig", {
                    "responseModalities": ["IMAGE"],
                    "imageConfig": {"aspectRatio": "1:1", "imageSize": "1K"}}),
                ("imageConfig sem tamanho", {
                    "responseModalities": ["IMAGE"],
                    "imageConfig": {"aspectRatio": "1:1"}}),
                ("responseFormat", {
                    "responseModalities": ["IMAGE"],
                    "responseFormat": {"image": {"aspectRatio": "1:1",
                                                 "imageSize": "1K"}}}),
                # A FORMA "SEM PROPORCAO" SAIU DAQUI, EM 01/10.
                #
                # Ela era a ultima da fila e dizia, em comentario: "peca com
                # margem e pior que peca nenhuma? Nao. Entregar e melhor."
                # Estava errado, e o dono disse por que sem saber que estava
                # dizendo: "margem nas fotos" e um dos oito defeitos que ele
                # quer que parem de acontecer.
                #
                # Recusadas as formas documentadas, esta passava, o Gemini
                # escolhia o formato, devolvia retangular, e o enquadramento
                # preenchia as sobras com faixa lisa. O sistema SABIA que o
                # pedido tinha falhado — gravava `proporcao_recusada` — e
                # entregava a peca torta assim mesmo.
                #
                # Agora: recusadas todas as formas documentadas, e ERRO, com
                # o motivo da API no texto. Peca nenhuma, e a pessoa sabe o
                # que aconteceu, e melhor que peca paga com margem.
            ]
            # UMA VARIAVEL POR VEZ, SENAO NAO SE APRENDE NADA. A versao antiga
            # mudava a proporcao E os `responseModalities` na mesma tentativa:
            # quando a API recusava, era impossivel saber qual das duas.
            if _FORMA_PROPORCAO["nome"]:
                _formas = ([f for f in _formas if f[0] == _FORMA_PROPORCAO["nome"]]
                           or _formas)

            resp = None
            for _nome_forma, _cfg_forma in _formas:
                _corpo = dict(_base_body)
                _corpo["generationConfig"] = _cfg_forma
                resp = requests.post(url, json=_corpo, headers=headers,
                                     timeout=120,
                                     proxies={"http": None, "https": None})
                if resp.status_code != 400:
                    _FORMA_PROPORCAO["nome"] = _nome_forma
                    if diagnostico is not None:
                        diagnostico["proporcao_pedida"] = _nome_forma
                    break
                import sys as _sys_ar
                print(f"[gemini] proporcao por '{_nome_forma}' recusada — "
                      f"tentando a proxima. {resp.text[:400]}",
                      file=_sys_ar.stderr, flush=True)
            # TODAS AS FORMAS DOCUMENTADAS RECUSADAS: ERRO, NAO DEGRADACAO.
            if resp is not None and resp.status_code == 400:
                # E A COLABORADORA PRECISA SABER, NAO SO O LOG DO RAILWAY.
                #
                # Recusado o pedido de quadrada, a imagem volta retangular, o
                # Studio preenche as sobras — e a pessoa recebe a peca com
                # MARGEM sem uma linha explicando por que. Dono, 30/09:
                # "imagens com margem". O sistema sabia; so nao contava.
                # TODAS AS FORMAS FORAM RECUSADAS — inclusive a sem
                # proporcao. Ai o 400 nao e sobre a proporcao, e o aviso nao
                # pode dizer que e: mentir sobre a causa custa a proxima hora
                # de quem for procurar.
                if diagnostico is not None:
                    try:
                        _det = resp.json().get("error", {}).get("message", "")
                    except Exception:
                        _det = ""
                    diagnostico["proporcao_recusada"] = (
                        _det or resp.text[:200] or "a API respondeu 400")
                try:
                    _det400 = resp.json().get("error", {}).get("message", "")
                except Exception:
                    _det400 = ""
                return None, (
                    "O motor recusou TODAS as formas documentadas de pedir a "
                    "imagem quadrada, e o Studio não gera sem pedir — peça "
                    "sem proporção volta retangular e ganha margem. "
                    + (f"A API respondeu: {_det400[:200]}" if _det400
                       else f"A API respondeu 400: {resp.text[:200]}"))
            if resp.status_code == 429:
                try:
                    _ej = resp.json()
                    _msg = _ej.get("error", {}).get("message", resp.text[:1500])
                    _st = _ej.get("error", {}).get("status", "")
                except Exception:
                    _msg = resp.text[:1500]
                    _st = ""
                if _resposta_sem_credito(429, _msg, _st):
                    return None, f"COTA_ESGOTADA:{_msg[:200]}"
                if tentativa >= MAX_TENTATIVAS:
                    return None, f"HTTP 429: {_msg[:200]}"
                _time.sleep(60)
                continue
            if resp.status_code != 200:
                # QUALQUER não-200 pode ser falta de crédito, não só o 429 —
                # e era exatamente aqui que o 402 escapava.
                try:
                    _ej = resp.json()
                    _msg = _ej.get("error", {}).get("message", "") or resp.text[:1500]
                    _st = _ej.get("error", {}).get("status", "")
                except Exception:
                    _msg, _st = resp.text[:1500], ""
                if _resposta_sem_credito(resp.status_code, _msg, _st):
                    return None, f"COTA_ESGOTADA:HTTP {resp.status_code} — {_msg[:200]}"
            return resp, None
        except Exception as e:
            if tentativa >= MAX_TENTATIVAS:
                return None, str(e)
            _time.sleep(5)
    return None, "Máximo de tentativas atingido."



# Formatos que os endpoints de imagem aceitam receber diretamente.
_MIMES_ACEITOS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def normalizar_imagem(img_bytes):
    """Converte qualquer imagem para um formato que os geradores aceitem.

    Retorna (bytes, mime, extensao).

    O colaborador não deveria precisar saber quais extensões o fornecedor de IA
    aceita nesta semana. Ele fotografa com o celular, baixa do fornecedor, tira
    print — e o arquivo pode vir HEIC, AVIF, GIF, BMP, TIFF. Antes, qualquer
    coisa fora de png/jpeg virava erro genérico de geração, sem dizer o motivo.

    PNG e JPEG e WEBP passam direto. O resto é convertido: JPEG quando a imagem
    é opaca (foto de produto costuma ser, e PNG de foto fica muitas vezes maior),
    PNG quando tem transparência a preservar.
    """
    import io as _io_norm
    mime = _detectar_mime(img_bytes)
    ext = _MIMES_ACEITOS.get(mime)
    if ext:
        return img_bytes, mime, ext

    try:
        from PIL import Image as _PILnorm
        # HEIC/HEIF é o padrão de foto do iPhone e o Pillow não abre sozinho.
        # Sem isto, o colaborador que fotografa o produto no celular e envia
        # direto recebia falha de geração sem explicação.
        try:
            import pillow_heif as _heif
            _heif.register_heif_opener()
        except Exception:
            pass
        im = _PILnorm.open(_io_norm.BytesIO(img_bytes))
        tem_alpha = (
            im.mode in ("RGBA", "LA")
            or (im.mode == "P" and "transparency" in im.info)
        )
        buf = _io_norm.BytesIO()
        if tem_alpha:
            im.convert("RGBA").save(buf, format="PNG")
            return buf.getvalue(), "image/png", "png"
        im.convert("RGB").save(buf, format="JPEG", quality=92)
        return buf.getvalue(), "image/jpeg", "jpg"
    except Exception:
        # Não dá para converter — devolve como está e deixa o gerador recusar
        # com a própria mensagem, que é mais informativa do que um palpite nosso.
        return img_bytes, mime or "application/octet-stream", "png"


def revisar_arquivo(dados, nome=""):
    """(bytes_prontos, aviso, erro) de um arquivo que o colaborador anexou.

    Quando dá para converter, converte e devolve o aviso do que fez — a pessoa
    merece saber que o HEIC dela virou JPEG. Quando não dá, devolve o erro
    dizendo O QUE ele é e o que fazer, e `bytes_prontos` vem vazio.

    Existe porque a tela quebrava inteira num arquivo que o Pillow não abre:
    o preview chamava st.image() com os bytes crus, o Pillow estourava, e o
    colaborador via um traceback de sessenta linhas terminando em
    `UnidentifiedImageError`. Ele não tem como saber que aquilo é sobre o
    formato do arquivo dele — o que ele lê é "o site quebrou".
    """
    rotulo = f"**{nome}**" if nome else "O arquivo"
    if not dados:
        return b"", "", f"{rotulo} chegou vazio (0 bytes)."

    mime = _detectar_mime(dados)
    nome_fmt = NOME_FORMATO.get(mime, "")

    if mime == "application/pdf":
        return b"", "", (
            f"{rotulo} é um **PDF**, não uma imagem. Abra o PDF, exporte a "
            f"página como JPG ou PNG, e anexe o resultado.")
    if mime == "image/svg+xml":
        return b"", "", (
            f"{rotulo} é um **SVG**, que é desenho vetorial e não foto. "
            f"Exporte como PNG antes de anexar.")

    if mime in _MIMES_ACEITOS:
        # Formato aceito não é o mesmo que arquivo íntegro: download pela
        # metade tem o cabeçalho certo e o corpo truncado.
        try:
            import io as _io_rev
            from PIL import Image as _PILrev
            _PILrev.open(_io_rev.BytesIO(dados)).verify()
            return dados, "", ""
        except Exception:
            return b"", "", (
                f"{rotulo} diz ser {nome_fmt} mas está corrompido ou veio pela "
                f"metade. Baixe o arquivo de novo e anexe outra vez.")

    prontos, novo_mime, _ = normalizar_imagem(dados)
    if novo_mime in _MIMES_ACEITOS and prontos is not dados:
        virou = NOME_FORMATO.get(novo_mime, novo_mime)
        de = nome_fmt or "um formato incomum"
        return prontos, f"{rotulo}: convertido de {de} para {virou}.", ""

    if nome_fmt:
        return b"", "", (
            f"{rotulo} é um **{nome_fmt}**, e não consegui converter aqui. "
            f"Abra a imagem e salve como **JPG** ou **PNG** antes de anexar.")
    return b"", "", (
        f"{rotulo} não é um arquivo de imagem que eu consiga ler — os "
        f"primeiros bytes dele não batem com nenhum formato conhecido. "
        f"Confira se o arquivo abre no seu computador; se abrir, salve como "
        f"**JPG** ou **PNG** e anexe de novo.")


def revisar_anexos(arquivos):
    """([bytes prontos], [nomes], [avisos], [erros]) de uma lista de uploads.

    Um arquivo ruim tira só ele da lista, não o lote: quem anexou cinco fotos e
    errou uma não deve perder as outras quatro.

    Os nomes saem junto e na MESMA ordem dos bytes. Quem chama precisa dos dois
    lado a lado — a referência de layout casa com a peça pelo nome do arquivo —,
    e reconstruir a lista de nomes do upload original desalinharia tudo a partir
    do primeiro arquivo recusado.
    """
    prontos, nomes, avisos, erros = [], [], [], []
    _perdidos = 0
    for arq in (arquivos or []):
        # O ARQUIVO QUE O NAVEGADOR AINDA LISTA E O SERVIDOR JA PERDEU.
        #
        # Os bytes do upload moram na memoria do PROCESSO do Streamlit
        # (`memory_uploaded_file_manager.py`, `file_storage`), e a lista de
        # NOMES fica no NAVEGADOR. Reiniciou o processo — deploy, queda, troca
        # de container — e os dois deixam de concordar: os nomes seguem na
        # tela, os bytes nao existem mais.
        #
        # Nesse caso o Streamlit devolve `DeletedFile(file_id=...)` no lugar do
        # arquivo (`file_uploader.py`, `_get_upload_files`), e `deserialize`
        # NAO tira esses objetos da lista — eles chegam aqui misturados com os
        # bons. `DeletedFile` e uma tupla: tem fatia, e nao tem `.getvalue()`
        # nem `.name`. O codigo antigo mandava o objeto inteiro para
        # `_detectar_mime`, que faz `data[:400].lstrip()`, e a tela caia com
        # `AttributeError: 'tuple' object has no attribute 'lstrip'`.
        if hasattr(arq, "getvalue"):
            dados = arq.getvalue()
        elif isinstance(arq, (bytes, bytearray)):
            dados = bytes(arq)
        else:
            _perdidos += 1
            continue
        nome = getattr(arq, "name", "")
        ok, aviso, erro = revisar_arquivo(dados, nome)
        if erro:
            erros.append(erro)
            continue
        if aviso:
            avisos.append(aviso)
        prontos.append(ok)
        nomes.append(nome)
    if _perdidos:
        # Um erro so para o lote inteiro: repetir a mesma frase seis vezes nao
        # informa mais, so enche a tela.
        erros.append(
            f"O servidor perdeu o conteudo de **{_perdidos} arquivo(s)** que o "
            f"seu navegador ainda mostra na lista. Isso acontece quando o "
            f"Studio reinicia com a pagina aberta — o nome fica, o arquivo "
            f"nao. **Recarregue a pagina (F5) e anexe de novo**, ou use o "
            f"botao de recuperar as fotos anexadas antes.")
    return prontos, nomes, avisos, erros


def mostrar_anexos(avisos, erros):
    """Põe na tela o que a revisão achou. Chame logo depois de revisar_anexos."""
    for e in erros:
        st.error(f"❌ {e}")
    for a in avisos:
        st.caption(f"↻ {a}")


# Limite de peso das plataformas de venda.
#
# A Shopee recusa arquivo acima de 2,0 MB, e a recusa acontece la, na hora de
# montar o anuncio — depois que o colaborador ja gerou, revisou e baixou tudo.
# Uma peca 1200x1200 salva em PNG passa de 2 MB com facilidade, entao o corte
# precisa acontecer aqui, na saida da geracao, e nao virar tarefa manual.
#
# O alvo e 1,9 MB e nao 2,0: nao da para saber se a plataforma conta MB como
# 1.000.000 ou 1.048.576 bytes, e a margem cobre as duas leituras.
LIMITE_PLATAFORMA_BYTES = 1_900_000


def _tem_transparencia(pil):
    """True so quando existe pixel realmente translucido.

    Modo RGBA nao basta: a geracao converte tudo para RGBA no enquadramento, e
    quase toda peca sai com alfa 255 em todo lugar. Perguntar pelo modo faria
    todas as imagens caírem no caminho do PNG, que e justamente o pesado.
    """
    if pil.mode not in ("RGBA", "LA", "P"):
        return False
    try:
        alpha = pil.convert("RGBA").getchannel("A")
        return (alpha.getextrema() or (255, 255))[0] < 255
    except Exception:
        return True


def extensao_de(img_bytes):
    """Extensao que corresponde ao conteudo real dos bytes.

    Depois da compressao a imagem pode ter deixado de ser PNG. Nome de arquivo
    escrito na mao como ".png" entregaria um JPEG disfarcado, e plataforma que
    confere o conteudo recusa.
    """
    return _MIMES_ACEITOS.get(_detectar_mime(img_bytes or b""), "png")


def comprimir_para_limite(img_bytes, limite=LIMITE_PLATAFORMA_BYTES):
    """Deixa a imagem abaixo do limite de peso perdendo o minimo de qualidade.

    Da tentativa menos destrutiva para a mais:

    1. PNG otimizado — resolve quando o excesso e pequeno.
    2. JPEG com qualidade decrescente (92 ate 62). Um JPEG 88 de peca de
       marketing fica na casa das centenas de KB e e visualmente indistinguivel
       do PNG. Vale para imagem opaca, que e o caso de praticamente toda peca
       gerada aqui.
    3. Reducao de resolucao, em ultimo caso. 1200x1200 e o tamanho que as
       plataformas pedem; encolher antes de tentar qualidade estragaria o
       anuncio a toa.

    Imagem com transparencia de verdade nunca vira JPEG — o fundo transparente
    viraria preto. Ela passa so por PNG otimizado e, se nao couber, por reducao.

    Devolve os bytes originais quando ja cabem, e o menor resultado obtido caso
    nenhuma tentativa caiba. Nunca devolve None e nunca levanta: imagem grande
    demais ainda e melhor do que imagem nenhuma.
    """
    if not img_bytes or len(img_bytes) <= limite:
        return img_bytes
    try:
        import io as _io_c
        from PIL import Image as _PILc
        pil = _PILc.open(_io_c.BytesIO(img_bytes))
        pil.load()
    except Exception:
        return img_bytes

    alpha = _tem_transparencia(pil)
    larg, alt = pil.size
    melhor = img_bytes

    def _tenta(dados):
        nonlocal melhor
        if len(dados) < len(melhor):
            melhor = dados
        return dados if len(dados) <= limite else None

    for escala in (1.0, 0.85, 0.72, 0.6, 0.5):
        if escala == 1.0:
            base = pil
        else:
            base = pil.resize((max(1, int(larg * escala)), max(1, int(alt * escala))),
                              _PILc.LANCZOS)

        try:
            buf = _io_c.BytesIO()
            base.convert("RGBA" if alpha else "RGB").save(buf, format="PNG",
                                                          optimize=True)
            cabe = _tenta(buf.getvalue())
            if cabe:
                return cabe
        except Exception:
            pass

        if alpha:
            continue

        for qualidade in (92, 88, 84, 80, 75, 70, 62):
            try:
                buf = _io_c.BytesIO()
                base.convert("RGB").save(buf, format="JPEG", quality=qualidade,
                                         optimize=True, progressive=True)
                cabe = _tenta(buf.getvalue())
                if cabe:
                    return cabe
            except Exception:
                break

    return melhor


def _arquivo_para_openai(img_bytes, nome_base):
    """Prepara (nome, buffer, mime) coerentes para o endpoint de edição.

    O nome do arquivo e o mime PRECISAM concordar. Antes a extensão era decidida
    por `"png" if "png" in mime else "jpg"`, então todo .webp era enviado como
    "arquivo.jpg" declarando mime image/webp — incoerência que a API recusa, e o
    erro chegava ao colaborador como falha genérica de geração.
    """
    import io as _io_prep
    dados, mime, ext = normalizar_imagem(img_bytes)
    return (f"{nome_base}.{ext}", _io_prep.BytesIO(dados), mime)


# ── QUANTAS FOTOS DO PRODUTO VAO AO MOTOR ───────────────────────────────────
#
# Era `[:3]`, escrito a mao em CINCO lugares. O colaborador subia nove fotos e
# o diagnostico dizia "3 de 9 disponiveis" — seis angulos do produto jogados
# fora sem ninguem decidir isso. Num produto de acabamento metalico, cada
# angulo a menos e detalhe que o gerador inventa.
#
# Tres nao era uma decisao: era um numero que ficou. Sobe para seis, que e o
# que os modelos de imagem aceitam com folga, e passa a ter UM lugar. Se um
# dia precisar mudar, muda aqui — e nao em cinco arquivos que discordam.
MAX_FOTOS_AO_MOTOR = 6

# E UM TETO DE BYTES, PORQUE CONTAR FOTO NAO BASTA.
#
# As fotos vao CRUAS: `revisar_arquivo` confere formato e integridade e
# devolve os bytes como vieram, sem comprimir. Seis fotos de 10MB sao 60MB,
# que em base64 viram uns 80MB numa chamada — e ai nao e "menos qualidade", e
# timeout ou recusa da API. Subir de tres para seis sem este teto era trocar
# um limite arbitrario por um risco de travar.
#
# Doze megabytes e o orcamento. Acima disso entram menos fotos, que e
# exatamente o comportamento antigo — nunca menos de uma.
ORCAMENTO_FOTOS_BYTES = 12 * 1024 * 1024


def fotos_para_o_motor(imagens_bytes):
    """As fotos do produto que cabem numa chamada. Lista, nunca None.

    Corta por quantidade E por peso. A primeira entra sempre, mesmo sozinha e
    grande: uma foto pesada e melhor que nenhuma — sem nenhuma, o modelo nao
    ve o produto e inventa.
    """
    escolhidas = []
    total = 0
    for foto in list(imagens_bytes or [])[:MAX_FOTOS_AO_MOTOR]:
        try:
            peso = len(foto)
        except TypeError:
            peso = 0
        if escolhidas and total + peso > ORCAMENTO_FOTOS_BYTES:
            break
        escolhidas.append(foto)
        total += peso
    return escolhidas


def _data_url(img_bytes):
    """data: URL já normalizada, para os caminhos que enviam imagem embutida."""
    dados, mime, _ = normalizar_imagem(img_bytes)
    return f"data:{mime};base64,{base64.b64encode(dados).decode('utf-8')}"


# ── O MODELO DE IMAGEM, NUM LUGAR SÓ ────────────────────────────────────────
#
# O NOME ESTAVA ERRADO, E ESCRITO À MÃO EM CINCO LUGARES.
#
# `gpt-image-2` não existe. Os modelos de imagem da OpenAI são
# `gpt-image-2.5-sunburst` (o mais capaz) e `gpt-image-2.5-flare` (rápido) —
# confirmado na documentação, em duas páginas. Toda chamada devolvia
# `404 model_not_found`, o motor primário nunca gerava nada, e TUDO caía no
# Gemini: o reserva, que não aceita `size` nem `input_fidelity`.
#
# Daí as duas reclamações do dono na mesma tela: "imagens extremamente
# pequenas" e "fotos com margens laterais". Sem `size=1024x1024`, o Gemini
# devolve retangular; o enquadramento então preenche as sobras com faixa lisa
# (imagem.py, passo 6) e o produto encolhe no meio do quadro. Não era o prompt.
#
# E O CONSERTO NÃO É TROCAR O NOME NOS CINCO LUGARES.
#
# Trocar o nome resolve hoje e reabre no dia em que a OpenAI renomear de novo —
# que é exatamente o que acabou de acontecer. O defeito é o Studio DEPENDER de
# um nome que alguém escreveu à mão e que ninguém confere.
#
# Então: o nome mora aqui, vem do Railway quando configurado, e quando a conta
# responde `model_not_found` o Studio PERGUNTA À PRÓPRIA CONTA quais modelos de
# imagem ela tem e usa o primeiro. Um rename futuro passa a custar uma chamada
# extra, e não um dia de geração perdida.
import re as _re_imp
import inspect as _inspect_g

MODELO_IMAGEM_PADRAO = "gpt-image-2.5-sunburst"

# A ORDEM DE PREFERÊNCIA, E NÃO UMA LISTA DE EXIGÊNCIA.
#
# Ela diz qual escolher PRIMEIRO entre os que a conta tem — nunca qual a
# conta precisa ter. Era aí que o Studio se cegava: nome fora desta lista
# não era considerado, e a conta de 30/09 não tinha nenhum deles.
#
# `dall-e-3` entra no fim de propósito: ele desenha, mas não aceita
# `input_fidelity` nem foto de referência. É melhor que nenhuma imagem e
# pior que qualquer `gpt-image` — e a tela diz qual motor fez a peça.
# A ORDEM E DE CAPACIDADE, e ela mudou em 02/10 com o print da conta do dono.
#
# `gpt-image-2` ESTA na conta dele e nao estava nesta lista — entrava como
# "qualquer outro", depois dos conhecidos. E ele e o melhor que a conta tem:
# o `gpt-image-1` e aposentado em 23/10/2026, e o `gpt-image-2` ja trabalha em
# alta fidelidade por padrao, sem precisar do `input_fidelity` (que ele nem
# aceita — mandar o parametro faz a requisicao falhar).
MODELOS_IMAGEM_CONHECIDOS = ("gpt-image-2.5-sunburst", "gpt-image-2.5-flare",
                             "gpt-image-2", "gpt-image-1.5", "gpt-image-1",
                             "dall-e-3", "dall-e-2")

# Descoberto em execução, quando o nome configurado não existe. Vive no
# processo: perguntar uma vez por container basta, e uma chamada a cada geração
# seria custo recorrente para resolver um problema de uma vez só.
_MODELO_DESCOBERTO = {"nome": None}

# MODELOS QUE A CONTA JA DISSE NAO TER. Nao e cache de otimizacao: e memoria
# de uma prova. A conta respondeu 404 para este nome, entao insistir nele e
# gastar a proxima geracao para receber o mesmo 404.
_MODELO_INVALIDO = set()

# A FORMA DE PEDIR IMAGEM QUADRADA QUE ESTA API ACEITA, descoberta em execucao.
#
# Vive no processo, igual ao modelo descoberto da OpenAI: perguntar uma vez por
# container basta, e tentar tres corpos a cada peca seria pagar toda geracao
# para responder uma pergunta de uma vez so.
_FORMA_PROPORCAO = {"nome": None}


def marcar_modelo_invalido(nome):
    """A conta respondeu que este modelo nao existe. Ele perde a vez."""
    if nome:
        _MODELO_INVALIDO.add(str(nome))


def aviso_de_modelo_invalido():
    """Texto para a tela quando a variavel do Railway aponta para o vazio.

    RECUPERAR CALADO ESCONDERIA A CONFIGURACAO ERRADA PARA SEMPRE. O Studio
    passa a funcionar sozinho, mas quem configurou precisa saber que configurou
    errado — senao o dia em que a descoberta tambem falhar ninguem entende por
    que, e o defeito volta com outra cara.
    """
    import chaves as _ch_av
    cfg = _ch_av.ler("OPENAI_MODELO_IMAGEM")
    if not cfg or cfg not in _MODELO_INVALIDO:
        return ""
    return (f"A variavel `OPENAI_MODELO_IMAGEM` esta com «{cfg}», e esta conta "
            f"da OpenAI nao tem esse modelo. O Studio esta usando "
            f"«{modelo_de_imagem()}» no lugar e segue funcionando — mas "
            f"corrija a variavel no Railway.")


def modelo_de_imagem():
    """O modelo que a geração usa. Configurável pelo Railway.

    `OPENAI_MODELO_IMAGEM` manda, depois o que foi descoberto na conta, depois
    o padrão. O dia em que a OpenAI lançar um modelo melhor, trocar é uma
    variável — não é deploy.

    MAS ELA PARA DE MANDAR DEPOIS DE PROVADA ERRADA, e foi isto que faltou.

    Dono, 29/09: "ja trouxe esse problema aqui umas 10 vezes e voce nao
    resolve". A variavel estava com um modelo que NAO existe naquela conta. O
    Studio chamava, tomava 404, redescobria um modelo bom (`_MODELO_DESCOBERTO`)
    e usava UMA vez — e na chamada seguinte lia a variavel de novo e voltava ao
    nome inexistente. A descoberta era jogada fora a cada geracao, e toda
    geracao recomecava errada. Para sempre, ate alguem lembrar de editar a
    variavel.

    O que faltava nao era o dono configurar certo: era o sistema parar de
    obedecer a uma configuracao que ele JA SABIA estar errada. Regra 5.
    """
    import chaves as _ch_mod
    cfg = _ch_mod.ler("OPENAI_MODELO_IMAGEM")
    if cfg and cfg not in _MODELO_INVALIDO:
        return cfg
    return _MODELO_DESCOBERTO["nome"] or MODELO_IMAGEM_PADRAO


def capacidade_do_motor(modelos):
    """O que a conta CONSEGUE garantir numa peça com fotos. (ok, recado).

    Função pura. `ok` é True quando a conta tem um modelo que aceita foto de
    referência com preservação do produto.

    POR QUE ESTA FUNÇÃO EXISTE
    --------------------------
    Dono, 30/09 e 01/10: *"margem nas fotos"*, *"criação de uma foto totalmente
    errada comparada ao produto original anexado"*.

    As duas vêm da MESMA causa, e ela não é o prompt: a peça foi feita pelo
    motor reserva, que não aceita `size=1024x1024` nem `input_fidelity=high`.
    Sem o primeiro a imagem volta retangular e o Studio preenche as sobras —
    é a margem. Sem o segundo o produto é redesenhado em vez de preservado.

    O Studio SABIA disso e não contava. A tela de diagnóstico listava os
    modelos da conta e parava aí: um nome de modelo não diz a ninguém que as
    peças vão sair com margem. É a mesma falha que o oitavo verificador existe
    para pegar — o sistema tem a informação e não a transforma em recado.

    Dizer isto em voz alta é o conserto possível: o resto está fora do código,
    e fingir o contrário custaria mais um dia procurando no lugar errado.
    """
    nomes = [str(m).lower() for m in (modelos or [])]
    if not nomes:
        return False, ("Não consegui listar os modelos desta conta — então "
                       "não sei dizer o que ela consegue garantir.")
    tem_gpt_image = any("gpt-image" in n for n in nomes)
    if tem_gpt_image:
        return True, ("Esta conta tem um modelo `gpt-image-*`: as peças podem "
                      "ser pedidas **quadradas** (`size=1024x1024`) e **com "
                      "preservação do produto** (`input_fidelity=high`). É o "
                      "cenário em que margem e produto redesenhado não "
                      "deveriam acontecer.")
    return False, (
        "**Esta conta NÃO tem nenhum modelo `gpt-image-*`** — e é isso que "
        "causa dois dos defeitos relatados:\n\n"
        "- **Margem nas fotos:** sem `size=1024x1024` a imagem volta "
        "retangular e o Studio preenche as sobras com faixa lisa.\n"
        "- **Produto diferente do real:** sem `input_fidelity=high` o produto "
        "é redesenhado a partir do texto em vez de preservado das fotos.\n\n"
        "Os outros modelos da conta não aceitam foto de referência nas "
        "chamadas que o Studio usa, então toda peça COM fotos cai no motor "
        "reserva. **Nenhuma regra de prompt conserta isso.** O Studio "
        "compensa: ele mede a peça pronta e manda refazer quando a cor não "
        "bate com as fotos ou quando há faixa — mas compensar custa gerações "
        "e não garante o resultado.")


def modelos_de_imagem_da_conta(cliente=None):
    """Que modelos de imagem ESTA conta tem. [] quando não dá para saber.

    É a pergunta que faltava. Enquanto ninguém a fazia, o Studio insistia num
    nome inventado e o erro chegava à tela como "404" — um número que não diz
    a ninguém o que fazer.
    """
    try:
        if cliente is None:
            from openai import OpenAI as _OAI_list
            _k = _get_openai_api_key()
            if not _k:
                return []
            cliente = _OAI_list(api_key=_k)
        nomes = [getattr(m, "id", "") for m in cliente.models.list()]
    except Exception:
        return []
    # ── O FILTRO EXIGIA "gpt" E "image", E ISSO CEGOU O STUDIO ──────────
    #
    # 30/09, produção: a tela disse «gpt-image-2.5-sunburst» não existe nesta
    # conta da OpenAI, e não achei nenhum outro". A redescoberta RODOU e
    # voltou vazia — e as oito peças saíram do motor reserva, sem pedido de
    # imagem quadrada e sem preservação do produto. Daí o texto cortado nas
    # bordas, o produto encolhido e a peça 6 com um produto que não era o do
    # cliente.
    #
    # A causa: `dall-e-3` É modelo de imagem da OpenAI e NÃO tem "gpt" no
    # nome. A conta tinha motor e o Studio não enxergava.
    #
    # O comentário antigo dizia que "gpt-image" cobria "a família inteira".
    # Cobria UMA família. Agora a pergunta é a certa: este nome é de um
    # modelo que faz IMAGEM? — e ela aceita as duas famílias, além de
    # qualquer nome futuro que traga "image".
    _n = lambda x: str(x).lower()
    achados = sorted(n for n in nomes
                     if "image" in _n(n) or "dall-e" in _n(n))
    # Os conhecidos primeiro, na ordem de capacidade; o resto depois.
    preferidos = [m for m in MODELOS_IMAGEM_CONHECIDOS if m in achados]
    return preferidos + [a for a in achados if a not in preferidos]


# As frases com que a OpenAI diz "esse modelo não é seu". São TEXTO da API, e
# por isso são procuradas por pedaço: o formato muda, o sentido não.
_DIZ_QUE_NAO_EXISTE = ("does not exist", "model_not_found",
                       "do not have access")


def _e_modelo_inexistente(exc):
    """O erro é o NOME do modelo, e não a chamada? Função pura.

    Separar isso é o que liga a redescoberta. Enquanto os dois erros eram a
    mesma coisa, o Studio insistia no nome errado em dois endpoints seguidos.
    """
    t = str(exc or "").lower()
    return any(p in t for p in _DIZ_QUE_NAO_EXISTE)


def redescobrir_modelo_de_imagem(cliente=None):
    """A conta não tem o modelo configurado: acha um que ela tenha. "" se não há.

    Chamado SÓ depois de um `model_not_found` — não no caminho normal. Listar
    modelos a cada geração seria pagar todo dia por um problema que acontece
    uma vez por rename.
    """
    for nome in modelos_de_imagem_da_conta(cliente):
        _MODELO_DESCOBERTO["nome"] = nome
        import sys as _sys_desc
        print(f"[imagem] modelo de imagem redescoberto na conta: {nome}",
              file=_sys_desc.stderr, flush=True)
        return nome
    return ""


def _modelo_nao_existe(excecao):
    """O erro é «esse modelo não existe / você não tem acesso»?"""
    t = str(excecao).lower()
    return ("model_not_found" in t
            or "does not exist" in t
            or "do not have access to it" in t)


# Falha da OpenAI que as OUTRAS tentativas não resolvem.
#
# `_chamar_openai_geracao` tenta três endpoints em sequência e as duas
# primeiras tentativas mandavam o motivo só para o stderr do Railway. Quando o
# motivo é saldo, chave ou acesso ao modelo, as três falham igual — e o que
# sobrava na tela era a mensagem genérica da terceira, enquanto a causa real
# ficava num log que ninguém abre. Se é terminal, o motivo sobe na hora.
_OPENAI_TERMINAL = (
    "insufficient_quota", "billing", "quota", "credit", "exceeded your current",
    "invalid_api_key", "incorrect api key", "authentication", "401",
    "does not have access to model", "model_not_found",
)


def parametro_recusado(exc, enviados):
    """Qual parametro a API recusou, ou "". Funcao pura.

    POR QUE ELA EXISTE, E POR QUE ELA LE O NOME EM VEZ DE SUPOR
    -----------------------------------------------------------
    O caminho sem fotos mandava `quality="high"` e `response_format` porque e
    o que a familia `gpt-image-*` aceita. O `dall-e-3` nao aceita os dois, e a
    chamada morria com 400 — depois de o Studio ter ENCONTRADO o modelo na
    conta. Era o item "a conta tinha motor e o Studio nao sabia falar com ele".

    Escrever a mao o que cada modelo aceita e o defeito que ja custou um dia
    inteiro nesta base: o nome do modelo, o campo da proporcao. Todo valor
    escrito a mao sobre a API de outro envelhece sem avisar.

    Entao o Studio le o nome do parametro NA RESPOSTA DE ERRO e tira aquele —
    e so aquele. Devolve "" quando o erro nao e sobre parametro, porque tirar
    um parametro por causa de falta de credito nao conserta nada e esconde a
    causa.

    `model`, `prompt` e `n` nunca saem: sem eles nao ha chamada nenhuma, e
    tira-los transformaria um erro legivel num erro pior.
    """
    texto = str(exc or "").lower()
    if not texto:
        return ""
    if not any(p in texto for p in ("unsupported", "unknown parameter",
                                    "invalid value", "not supported",
                                    "does not support", "unrecognized")):
        return ""
    for nome in sorted(enviados or (), key=len, reverse=True):
        if nome in ("model", "prompt", "n"):
            continue
        if nome in texto:
            return nome
    return ""


def _erro_openai_terminal(excecao):
    """O texto do erro quando repetir não adianta; "" quando vale tentar o próximo."""
    texto = str(excecao)
    baixo = texto.lower()
    if any(p in baixo for p in _OPENAI_TERMINAL):
        return texto[:300]
    return ""


def guardar_rascunho(usuario, motivo=""):
    """Grava a galeria da sessao no disco. Devolve (ok, erro).

    POR QUE ELA PASSOU A SER CHAMADA EM TODO LUGAR

    O rascunho so era gravado durante a GERACAO — `_rasc.salvar` aparecia uma
    unica vez no arquivo inteiro, dentro do laco das oito imagens. Nenhum
    ajuste era gravado.

    Entao uma tarde inteira de correcoes vivia so em `st.session_state`. Quando
    o processo reiniciou, ela sumiu: nem a sessao tinha, nem o disco — o disco
    guardava as oito ORIGINAIS, sem nenhuma correcao. Recuperar traria o
    trabalho de antes das horas de ajuste.

    E FALHA AQUI NAO PODE MAIS SER MUDA

    A gravacao vivia dentro de `except Exception: pass`. Disco cheio, volume
    desmontado, permissao errada — tudo dava no mesmo: silencio, e o
    colaborador so descobria quando ja tinha perdido. O erro continua nao
    derrubando a tela, mas agora ele APARECE.
    """
    try:
        import rascunho as _rasc
        galeria = st.session_state.get("img_galeria") or []
        if not galeria:
            return True, ""
        _rasc.salvar(st.session_state.get("usuario") or usuario or "anon",
                     st.session_state.get("img_nome_produto", ""),
                     galeria, st.session_state.get("img_codigo", ""))
        return True, ""
    except Exception as e:
        erro = f"{type(e).__name__}: {str(e)[:120]}"
        st.session_state["img_rascunho_erro"] = erro
        return False, erro


def aviso_de_rascunho():
    """Mostra, uma vez, que a copia de seguranca falhou.

    Fica separado de `guardar_rascunho` porque a gravacao acontece dentro de
    laco e de thread, onde escrever na tela ou nao aparece ou aparece no lugar
    errado. Aqui e o comeco da pagina, que e onde a pessoa olha.
    """
    erro = st.session_state.pop("img_rascunho_erro", "")
    if erro:
        st.error(
            "💾 **A copia de seguranca das imagens falhou.** Elas existem "
            "apenas nesta sessao: se a tela reiniciar agora, o trabalho se "
            "perde. Salve no Drive antes de continuar.\n\n"
            f"Motivo tecnico: {erro}")


def _chamar_openai_geracao(prompt_final, imagens_bytes=None, ref_layout=None,
                           ref_layout_nome="", diagnostico=None,
                           _ja_redescobriu=False):
    """Chama o motor primário de imagem da OpenAI. Retorna (img_bytes, erro).

    Quando `imagens_bytes` é fornecido, usa a Responses API com as fotos do produto
    como referência visual direta — o mesmo comportamento do ChatGPT.
    Sem fotos, usa images.generate() (texto puro).
    """
    api_key = _get_openai_api_key()
    if not api_key:
        return None, "OPENAI_API_KEY não configurada."
    try:
        from openai import OpenAI as _OpenAI
        client = _OpenAI(api_key=api_key)
        _modelo = modelo_de_imagem()

        # ── COM FOTOS: Responses API (fotos como referência visual direta, igual ao ChatGPT) ──
        if imagens_bytes:
            content = []
            for img_b in fotos_para_o_motor(imagens_bytes):
                content.append({"type": "input_image", "image_url": _data_url(img_b)})
            # Referência de layout por ÚLTIMO — a ordem é o que diz ao modelo
            # que ela é molde de composição, não o produto a reproduzir.
            if ref_layout:
                content.append({"type": "input_image", "image_url": _data_url(ref_layout)})
            content.append({"type": "input_text", "text": prompt_final})
            entrada = [{"role": "user", "content": content}]

            def _extrair(resposta):
                for out in resposta.output:
                    if getattr(out, "type", None) == "image_generation_call":
                        result = getattr(out, "result", None)
                        if result:
                            return base64.b64decode(result)
                return None

            # Tentativa 1: declara a ferramenta de imagem com os controles que
            # resolvem dois problemas reais de produção:
            #   size=1024x1024   -> saída JÁ quadrada. Sem isso o modelo escolhe
            #                       o formato (costuma vir 1536x1024) e o
            #                       pós-processamento precisava criar faixas.
            #   input_fidelity=high -> obriga a preservar cor e estrutura das
            #                       fotos de referência. É o que impedia um
            #                       álbum preto de sair azul ou bege.
            # Se a API recusar esse formato de chamada, cai na chamada antiga —
            # o pior caso é exatamente o comportamento de hoje, nunca menos.
            # O PARAMETRO RECUSADO SAI, E A CHAMADA SE REPETE SEM ELE.
            #
            # Este laco existia so no caminho SEM fotos. Os dois caminhos que
            # mandam foto — este e o `images.edit` — morriam no primeiro 400
            # e caiam no Gemini, que e o motor sem preservacao de produto.
            #
            # 02/10 isto deixou de ser hipotese: o `gpt-image-2`, que a conta
            # do dono TEM, REMOVEU o `input_fidelity` — ele ja trabalha em
            # alta fidelidade por padrao, e manda a requisicao falhar quando o
            # parametro vai junto. Sem este laco, trocar para o modelo novo
            # devolveria exatamente o defeito que ele veio consertar.
            #
            # Le o nome NA RESPOSTA DE ERRO, e tira so aquele. Escrever a mao
            # o que cada modelo aceita e o defeito que ja custou um dia aqui.
            _tools_cfg = {
                "type": "image_generation",
                "size": "1024x1024",
                "quality": "high",
                "input_fidelity": "high",
            }
            try:
                for _tentativa_tool in range(3):
                    try:
                        resp = client.responses.create(
                            model=_modelo, input=entrada,
                            tools=[dict(_tools_cfg)])
                        break
                    except Exception as _e_par:
                        _qual = parametro_recusado(_e_par, list(_tools_cfg))
                        if not _qual or _qual == "type":
                            raise
                        import sys as _sys_par
                        print(f"[DEBUG {_modelo}] «{_qual}» recusado pelo "
                              f"modelo — repetindo sem ele",
                              file=_sys_par.stderr)
                        _tools_cfg.pop(_qual, None)
                        if diagnostico is not None:
                            diagnostico.setdefault("parametros_recusados",
                                                   []).append(_qual)
                img = _extrair(resp)
                if img:
                    import sys as _sys
                    print(f"[DEBUG {_modelo}] Operation: generate/edit | "
                          f"References sent: {len(imagens_bytes)} | "
                          f"enviados: {sorted(_tools_cfg)}", file=_sys.stderr)
                    if diagnostico is not None:
                        diagnostico["motor"] = f"{_modelo} (Responses + tools)"
                        # O QUE FOI MANDADO DE VERDADE, e nao o que o codigo
                        # queria mandar: a tela dizia "input_fidelity=high"
                        # mesmo quando o parametro tinha sido recusado.
                        diagnostico["size_pedido"] = _tools_cfg.get("size", "")
                        diagnostico["input_fidelity"] = _tools_cfg.get(
                            "input_fidelity",
                            "não aceito por este modelo (ele já preserva)")
                        diagnostico["refs_enviadas"] = len(fotos_para_o_motor(imagens_bytes))
                    return img, None
            except Exception as _e_tool:
                import sys as _sys
                # MODELO QUE NÃO EXISTE NÃO É "TOOLS RECUSADO".
                #
                # O 404 `The model does not exist or you do not have access`
                # caía aqui, virava "tools recusado" e ia para o images.edit —
                # com o MESMO nome de modelo, que também não existe. A
                # redescoberta (`redescobrir_modelo_de_imagem`) existia e
                # nunca era chamada, porque este ramo nunca perguntava se o
                # problema era o NOME.
                #
                # O log de 24/09 mostrou o preço: 404 em toda geração, a
                # OpenAI nunca rodando, e todas as imagens saindo do Gemini
                # sem controle de proporção.
                if _e_modelo_inexistente(_e_tool) and not _ja_redescobriu:
                    # A CONTA PROVOU QUE ESTE NOME NAO EXISTE. Sem marcar, a
                    # descoberta valia so para esta chamada: a proxima lia a
                    # variavel do Railway de novo e voltava ao mesmo 404.
                    marcar_modelo_invalido(_modelo)
                    _novo = redescobrir_modelo_de_imagem()
                    if _novo and _novo != _modelo:
                        print(f"[imagem] {_modelo} não existe nesta conta; "
                              f"refazendo com {_novo}", file=_sys.stderr,
                              flush=True)
                        # UMA vez só: `_ja_redescobriu` impede o laço quando
                        # nem o modelo achado servir.
                        return _chamar_openai_geracao(
                            prompt_final, imagens_bytes, ref_layout,
                            ref_layout_nome, diagnostico,
                            _ja_redescobriu=True)
                    return None, (
                        f"O modelo de imagem «{_modelo}» não existe nesta "
                        "conta da OpenAI, e não achei nenhum outro. Configure "
                        "`OPENAI_MODELO_IMAGEM` no Railway com um modelo que "
                        "a conta tenha.")
                print(f"[DEBUG {_modelo}] tools recusado ({str(_e_tool)[:120]}) — "
                      "tentando images.edit", file=_sys.stderr)
                _term = _erro_openai_terminal(_e_tool)
                if _term:
                    return None, f"Erro OpenAI {_modelo}: {_term}"

            # Tentativa 2: endpoint de edição — aceita as fotos como referência e,
            # diferente da Responses API, size e input_fidelity são parâmetros
            # documentados e estáveis aqui. Garante saída quadrada mesmo que a
            # tentativa 1 não seja aceita.
            try:
                import io as _io_edit
                arquivos = [
                    _arquivo_para_openai(img_b, f"produto{_i}")
                    for _i, img_b in enumerate(fotos_para_o_motor(imagens_bytes))
                ]
                if ref_layout:
                    arquivos.append(_arquivo_para_openai(ref_layout, "layout_referencia"))
                _args_edit = {"size": "1024x1024", "quality": "high",
                              "input_fidelity": "high"}
                for _tentativa_ed in range(3):
                    try:
                        edit = client.images.edit(
                            model=_modelo, image=arquivos,
                            prompt=prompt_final, **_args_edit)
                        break
                    except Exception as _e_pe:
                        _qual_e = parametro_recusado(_e_pe, list(_args_edit))
                        if not _qual_e:
                            raise
                        import sys as _sys_pe
                        print(f"[DEBUG {_modelo}] «{_qual_e}» recusado no "
                              f"images.edit — repetindo sem ele",
                              file=_sys_pe.stderr)
                        _args_edit.pop(_qual_e, None)
                        if diagnostico is not None:
                            diagnostico.setdefault("parametros_recusados",
                                                   []).append(_qual_e)
                _d = edit.data[0]
                if getattr(_d, "b64_json", None):
                    import sys as _sys
                    print(f"[DEBUG {_modelo}] Operation: edit | "
                          f"References sent: {len(arquivos)} | "
                          f"enviados: {sorted(_args_edit)}", file=_sys.stderr)
                    if diagnostico is not None:
                        diagnostico["motor"] = f"{_modelo} (images.edit)"
                        diagnostico["size_pedido"] = _args_edit.get("size", "")
                        diagnostico["input_fidelity"] = _args_edit.get(
                            "input_fidelity",
                            "não aceito por este modelo (ele já preserva)")
                        diagnostico["refs_enviadas"] = len(arquivos)
                    return base64.b64decode(_d.b64_json), None
            except Exception as _e_edit:
                import sys as _sys
                print(f"[DEBUG {_modelo}] images.edit recusado ({str(_e_edit)[:120]}) — "
                      "usando chamada simples", file=_sys.stderr)
                _term = _erro_openai_terminal(_e_edit)
                if _term:
                    return None, f"Erro OpenAI {_modelo}: {_term}"

            resp = client.responses.create(model=_modelo, input=entrada)
            img = _extrair(resp)
            if img:
                import sys as _sys
                print(f"[DEBUG {_modelo}] Operation: generate/edit | "
                      f"References sent: {len(imagens_bytes)}", file=_sys.stderr)
                if diagnostico is not None:
                    diagnostico["motor"] = f"{_modelo} (Responses simples — SEM size)"
                    diagnostico["size_pedido"] = "nenhum (modelo escolhe)"
                    diagnostico["refs_enviadas"] = len(fotos_para_o_motor(imagens_bytes))
                return img, None
            return None, "Sem imagem na resposta Responses API."

        # ── SEM FOTOS: geração texto puro ──
        #
        # ESTE CAMINHO ENTREGAVA A PECA SEM DIZER QUEM ELE ERA.
        #
        # Os outros tres gravam `diagnostico["motor"]`; este nao gravava
        # nada — nem motor, nem tamanho, nem quantas fotos foram. A tela de
        # diagnostico mostrava "Motor —", e quem olhava nao tinha como saber
        # que aquela peca saiu por um caminho que NEM RECEBEU as fotos do
        # produto, e portanto reconstruiu tudo a partir do texto.
        #
        # E o caminho onde a peca tem mais chance de sair "nada a ver com o
        # produto original" — justamente o menos identificado.
        if diagnostico is not None:
            diagnostico["motor"] = f"{_modelo} (images.generate — SEM fotos)"
            diagnostico["size_pedido"] = "1024x1024"
            diagnostico["refs_enviadas"] = 0
            diagnostico["sem_fotos"] = (
                "esta peça foi gerada SEM as fotos do produto: o modelo "
                "reconstruiu o produto a partir do texto, então ele pode "
                "não ter nada a ver com o real")
        # ── A CHAMADA SE ADAPTA AO MODELO, EM VEZ DE EU CHUTAR ──────────
        #
        # Este caminho mandava `quality="high"` e lia `b64_json`. Os dois sao
        # da familia `gpt-image-*`. O `dall-e-3` — que o filtro corrigido em
        # 30/09 passou a ENCONTRAR na conta — nao aceita `quality="high"` e
        # devolve URL em vez de base64 quando ninguem pede o contrario.
        #
        # Resultado: o Studio achava o modelo, chamava, levava 400, e a peca
        # morria no caminho que existe justamente para quando nao ha fotos.
        # "A conta tinha motor e o Studio nao sabia falar com ele" ficou
        # ABERTO no ACHADOS_ABERTOS.md por isso.
        #
        # E O CONSERTO NAO E ESCREVER O QUE EU ACHO QUE O `dall-e-3` ACEITA.
        #
        # Foi assim que o nome do modelo e o campo da proporcao viraram
        # defeito: um valor escrito a mao, que ninguem confere, e que a OpenAI
        # muda quando quiser. A chamada tenta a forma rica e, se a API recusar
        # POR CAUSA DE UM PARAMETRO, tira aquele parametro e repete. Modelo
        # novo passa a funcionar sozinho.
        _args_gen = {"model": _modelo, "prompt": prompt_final, "n": 1,
                     "size": "1024x1024", "quality": "high",
                     "response_format": "b64_json"}
        _tirados = []
        while True:
            try:
                response = client.images.generate(**_args_gen)
                break
            except Exception as _e_gen:
                _qual = parametro_recusado(_e_gen, _args_gen)
                if not _qual:
                    raise
                _tirados.append(_qual)
                _args_gen.pop(_qual, None)
                import sys as _sys_gen
                print(f"[DEBUG {_modelo}] images.generate recusou "
                      f"`{_qual}` — repetindo sem ele", file=_sys_gen.stderr,
                      flush=True)
        if _tirados and diagnostico is not None:
            diagnostico["motor"] = (
                f"{_modelo} (images.generate — SEM fotos, sem "
                + ", ".join(_tirados) + ")")
        img_data = response.data[0]
        # O modelo retorna b64_json por padrão
        if hasattr(img_data, "b64_json") and img_data.b64_json:
            import sys as _sys
            print(f"[DEBUG {_modelo}] Operation: generate | References sent: 0 | "
                  f"Quality: high | Size: 1024x1024", file=_sys.stderr)
            return base64.b64decode(img_data.b64_json), None
        # Fallback: URL temporária
        if hasattr(img_data, "url") and img_data.url:
            r = requests.get(img_data.url, timeout=60)
            if r.status_code == 200:
                return r.content, None
        return None, "Sem dados de imagem na resposta OpenAI."
    except Exception as e:
        # O NOME DO MODELO NÃO EXISTE — E ISSO TEM CONSERTO SOZINHO.
        #
        # Foi o que derrubou a geração inteira: `gpt-image-2` escrito à mão,
        # 404 em toda chamada, tudo caindo no reserva. Em vez de devolver o
        # erro e esperar alguém ler o log, o Studio pergunta à conta o que ela
        # tem e tenta outra vez — UMA vez, para um nome que não existe não
        # virar laço infinito.
        if _modelo_nao_existe(e) and not _ja_redescobriu:
            # O IRMAO DA MARCACAO ACIMA. Sao dois endpoints, e corrigir so um
            # deles e a Forma 1 desta base: o nome invalido continuaria
            # voltando pelo caminho que ficou sem marca.
            marcar_modelo_invalido(_modelo)
            _novo = redescobrir_modelo_de_imagem(client)
            if _novo and _novo != _modelo:
                return _chamar_openai_geracao(
                    prompt_final, imagens_bytes=imagens_bytes,
                    ref_layout=ref_layout, ref_layout_nome=ref_layout_nome,
                    diagnostico=diagnostico, _ja_redescobriu=True)
            _quais = modelos_de_imagem_da_conta(client)
            return None, (
                f"O modelo «{_modelo}» não existe nesta conta da OpenAI. "
                + (f"Os que ela tem: {', '.join(_quais[:6])}. Configure "
                   f"OPENAI_MODELO_IMAGEM no Railway com um deles."
                   if _quais else
                   "E a conta não devolveu nenhum modelo de imagem — é acesso "
                   "ao modelo, em platform.openai.com → Settings."))
        return None, f"Erro OpenAI {modelo_de_imagem()}: {str(e)[:300]}"


def gerar_imagem_ia(prompt_texto, imagens_referencia, refs_layout=None,
                    refs_layout_nomes=None, tipo="", diagnostico=None,
                    _ja_repetiu_quadrada=False, so_montar=False):
    """Arquitetura de geração — fotos do produto vão diretamente ao modelo via Responses API.

    Fluxo:
    1. Claude Vision analisa fotos → descrição de apoio (usada apenas quando não há OpenAI)
    2. Claude descreve estilo das refs de layout (se houver) → texto de composição
    3. Monta prompt único preservando preset completo do tipo (sem double-prompt)
    4. Tenta o motor primário da OpenAI — fotos enviadas diretamente
    5. Reserva: Gemini Flash Image — COM as fotos do produto
    6. Retorna imagem com proporções exatas preservadas (sem deformação)
    """
    import re as _re

    # Extrai metadados do prompt para contextualizar a descrição
    # ── O QUE O STUDIO ESCREVEU, E O QUE ESTA LEITURA OUVIA ──────────────
    #
    # Dono, 30/09: "certifique-se de o estudio estar falando A e o resultado
    # ser A e nao B". Aqui ele falava A e esta leitura ouvia outra coisa —
    # em silencio, nos NOVE tipos.
    #
    #   COR       o prompt escreve "COR REAL DO PRODUTO: preto"; a busca
    #             procurava "Cor:" e NUNCA casava. A cor cadastrada jamais
    #             entrou em "Known specs" da analise de visao — e a analise
    #             e quem descreve o produto para o gerador.
    #   MATERIAL  o prompt escreve "Material e montagem (...): ..." e ninguem
    #             procurava por ele, embora `_descrever_produto_via_claude`
    #             tenha campo proprio para material (linha ~1612).
    #   NOME      `PRODUTO:` sem ancora casava NO MEIO de outra frase. No
    #             prompt do AJUSTE FINO ele casava dentro de "PROIBICAO DE
    #             MODIFICAR O PRODUTO: JAMAIS adicione base, pedestal..." — e
    #             esse pedaco virava o NOME DO PRODUTO na analise de visao e
    #             na CHAVE DO CACHE.
    #
    # Cor e material sao justamente os dois campos que decidem se a peca
    # parece o produto. Eram os dois que nunca chegavam.
    #
    # ANCORADAS NO INICIO DA LINHA, as tres: rotulo de cadastro comeca linha.
    nome_produto = ""
    _m = _re.search(r"^PRODUTO:\s*(.+?)$", prompt_texto, _re.MULTILINE)
    if _m:
        nome_produto = _m.group(1).strip()

    dados_descricao = {}
    _m_cor = _re.search(r"^COR REAL DO PRODUTO:\s*(.+?)$", prompt_texto,
                        _re.MULTILINE)
    _m_med = _re.search(r"^Medidas EXATAS[^:]*:\s*(.+?)$", prompt_texto,
                        _re.MULTILINE)
    _m_pes = _re.search(r"^Peso EXATO[^:]*:\s*(.+?)$", prompt_texto,
                        _re.MULTILINE)
    _m_mat = _re.search(r"^Material e montagem[^:]*:\s*(.+?)$", prompt_texto,
                        _re.MULTILINE)
    if _m_cor:
        dados_descricao["cor"] = _m_cor.group(1).strip()
    if _m_med:
        dados_descricao["medidas"] = _m_med.group(1).strip()
    if _m_pes:
        dados_descricao["peso"] = _m_pes.group(1).strip()
    if _m_mat:
        dados_descricao["material"] = _m_mat.group(1).strip()

    # 1. Claude descreve produto e layout em texto puro
    #
    # UMA LEITURA POR PRODUTO, NÃO UMA POR PEÇA.
    #
    # Isto rodava a cada uma das 8 gerações, sobre as MESMAS fotos e as
    # MESMAS referências. Oito chamadas de visão, oito textos diferentes —
    # no produto de 24/09 a mesma dupla de referências virou "chaleira
    # vermelha" numa peça, "bule vermelho" noutra e "aquecedor vermelho" na
    # sexta. Cada peça recebia uma instrução de layout distinta, e não havia
    # como o conjunto sair coerente.
    #
    # A chave é o conteúdo: as mesmas fotos e as mesmas referências dão a
    # mesma descrição. Foto nova, leitura nova.
    # ── NO AJUSTE FINO, A ANALISE DE VISAO E DINHEIRO JOGADO FORA ────────
    #
    # A descricao que ela produz alimenta a secao PRODUCT DESCRIPTION do
    # prompt de CRIACAO. No ajuste fino essa secao nem chega ao motor: o
    # prompt do ajuste SUBSTITUI o de criacao inteiro (`prompt_geracao =
    # _prompt_ajuste`, adiante neste mesmo arquivo).
    #
    # Ou seja: toda tentativa de ajuste pagava uma leitura de visao cujo
    # resultado era descartado na linha seguinte. Sao 2 tentativas por
    # ajuste, entao 2 leituras pagas por pedido do colaborador.
    #
    # E ela rodava com o nome do produto ERRADO, ainda por cima: o regex sem
    # ancora pegava "JAMAIS adicione base, pedestal, suporte, embalagem" de
    # dentro de uma proibicao do proprio prompt.
    #
    # O marcador do ajuste esta na PRIMEIRA linha do texto, entao da para
    # saber antes de gastar.
    _eh_ajuste_fino = "MODO AJUSTE FINO" in prompt_texto[:400]
    if _eh_ajuste_fino:
        descricao_produto, estilo_layout = "", ""
    else:
        descricao_produto, estilo_layout = _descricao_do_produto_cacheada(
            imagens_referencia, nome_produto, dados_descricao, refs_layout
        )

    # 2. Modo de fundo — lido do marcador que montar_prompt_imagem escreve.
    #
    # Antes isto era adivinhado procurando "fundo branco" DENTRO do prompt
    # inteiro. Só que INSTRUCAO_PROPORCAO — colada em todo prompt — contém a
    # frase "Para fotos limpas de produto (fundo branco)". Resultado: os 8
    # tipos eram classificados como fundo branco, e o app mandava ao modelo
    # "Pure white background" e "ZERO TEXT RULE" até nas peças de marketing
    # que existem justamente para ter texto. Daí os fundos brancos fora do
    # padrão e as frases saindo pela metade — o modelo recebia ordens opostas.
    _modo_fundo = "padrao"
    _m_fundo = _re.search(r"^MS_FUNDO:\s*(\w+)", prompt_texto, _re.MULTILINE)
    if _m_fundo:
        _modo_fundo = _m_fundo.group(1).strip().lower()

    _is_fundo_branco = _modo_fundo == "branco"       # só a capa do anúncio
    _is_ambientacao = _modo_fundo == "ambiente"      # fundo é a cena real
    _is_personalizado = _modo_fundo == "personalizado"
    # Sem texto: capa (foto limpa) e ambientação (foto editorial).
    _is_clean_photo = _is_fundo_branco or _is_ambientacao
    _PREFIXOS_MARKETING = ("2 —", "3 —", "4 —", "5 —", "6 —", "7 —")
    _is_marketing = any(f"TIPO DE IMAGEM: {p}" in prompt_texto for p in _PREFIXOS_MARKETING)

    # Regra de fundo definida pelo dono do produto:
    #   capa            -> branco puro
    #   ambientação     -> o próprio ambiente da cena, sem cor imposta
    #   personalizado   -> o colaborador manda, não impomos nada
    #   demais (2 a 7)  -> DEDUZIDO DO PRODUTO, e não mais o azul da marca
    if _is_fundo_branco:
        _background = (
            "Pure white background (#FFFFFF) — absolutely clean, no gradients, no shadows, "
            "no textures. Studio product photography look."
        )
    elif _is_ambientacao:
        _background = (
            "Background is the REAL ENVIRONMENT of the scene (room, desk, shelf, natural setting). "
            "Do NOT paint a flat studio backdrop and do NOT apply any brand background color — "
            "the environment itself is the background, with natural light and real depth."
        )
    elif _is_personalizado:
        _background = (
            "Background follows the collaborator's instructions. Do not impose a brand background."
        )
    else:
        # AQUI ESTAVA O AZUL OBRIGATÓRIO PELA SEGUNDA VEZ.
        #
        # Tirar a paleta fixa do `PADRAO_VISUAL` e deixar esta linha em pé
        # seria trocar a regra num lugar e manter a ordem contrária no outro —
        # e o modelo recebe as duas na mesma mensagem. A cor do fundo agora
        # sai do produto, aqui também.
        _background = (
            "Background color is DERIVED FROM THE PRODUCT, not from a fixed "
            "brand palette. Analyse the product colour, material, category and "
            "occasion, then choose a background that makes THIS product stand "
            "out: light and airy for delicate products, deep and dramatic for "
            "dark premium products, neutral with accents from the product's own "
            "colours for colourful ones. Never recolour the product to match "
            "the background. Do not default to plain white for this image type."
        )

    # A AMBIENTACAO TEM UMA EXCECAO DE TEXTO, E ELA ERA NEGADA AQUI.
    #
    # O brief em portugues da ambientacao diz: "A ÚNICA sequência de caracteres
    # permitida na imagem inteira é: Imagem meramente ilustrativa". Esta linha
    # dizia, na mesma mensagem, "ABSOLUTELY NO text ... Any visible text is a
    # critical failure". Duas ordens opostas sobre a mesma frase — e o modelo
    # resolve contradicao escrevendo mais coisa, nao menos.
    if _is_fundo_branco:
        _text_rule = (
            "ZERO TEXT RULE: This image MUST contain ABSOLUTELY NO text, titles, labels, "
            "icons, badges, callouts, or any written element whatsoever. Any visible text "
            "is a critical failure."
        )
    elif _is_ambientacao:
        _text_rule = (
            "ZERO TEXT RULE, ONE EXPLICIT EXCEPTION: no title, headline, caption, badge, "
            "logo, icon with text, number or decorative word anywhere. The ONLY string "
            "allowed in the whole image is the Portuguese sentence \"Imagem meramente "
            "ilustrativa\", rendered once, small and discreet in the footer. Scene props "
            "(books, packaging, screens, labels) carry no readable text at all."
        )
    else:
        _text_rule = (
            "TEXT ZONES RULE: ALL text must appear ONLY in dedicated panel zones completely "
            "separate from the product area. NEVER overlay text directly on the product. "
            "Product zone must be clean and text-free."
        )

    # ── Extrai conteúdo visual do colaborador (modo Personalizado) ou contexto interno (padrão) ──
    _colab_match = _re.search(
        r"INSTRUÇÕES VISUAIS DO COLABORADOR[^:]*:\s*(.*?)(?:\n(?:REFERÊNCIAS|PADRÃO|INSTRUÇÃO|REGRA|MODO|$))",
        prompt_texto, _re.DOTALL
    )
    _context_match = _re.search(
        r"CONTEXTO INTERNO DO PRODUTO[^:]*:\s*(.*?)(?:\n(?:REFERÊNCIAS|PADRÃO|INSTRUÇÃO|REGRA|MODO|$))",
        prompt_texto, _re.DOTALL
    )
    _colaborador_brief = _colab_match.group(1).strip() if _colab_match else ""
    _colaborador_contexto = _context_match.group(1).strip() if _context_match else ""

    # ── O BRIEF INTEIRO VAI PARA O MODELO — ANTES, DOIS TERCOS DELE ERAM
    #    CORTADOS FORA, E NINGUEM VIA ────────────────────────────────────────
    #
    # Aqui havia um recorte por regex: pegava de "TIPO DE IMAGEM:" ate o
    # primeiro titulo que casasse com "PADRÃO VISUAL|REGRA DE|INSTRUÇÃO DE|
    # CONTEXTO INTERNO|REFERÊNCIAS|INSTRUÇÕES VISUAIS|MODO ". Tudo depois
    # disso era JOGADO FORA, em silencio.
    #
    # O que nunca chegava ao gerador, medido nos nove tipos:
    #
    #   TRAVA DE COR       — a cor real do produto e a proibicao de repintar.
    #                        Em TODOS os tipos. O album preto que saiu
    #                        azul-marinho tinha a trava escrita no prompt
    #                        portugues e cortada do prompt que foi enviado.
    #   Medidas e peso     — os numeros exatos. E o tipo 5 e o INFOGRAFICO DE
    #                        MEDIDAS: ele pedia "use APENAS os valores
    #                        informados" com os valores ausentes da mensagem.
    #   REGRA DE FIDELIDADE — "a mais importante de todas".
    #   REGRA DE LAYOUT     — "JAMAIS sobreponha texto sobre o produto" (os
    #                        quadrados em cima da caneca) e a REGRA DE TEXTO
    #                        REAL, que proibe palavra inventada (o erro de
    #                        portugues).
    #   Capa               — o bloco inteiro de "O PRODUTO PREENCHE O QUADRO",
    #                        escrito depois do "Já falei MIL VEZES".
    #   Ambientacao        — a ESCALA REAL e a excecao "Imagem meramente
    #                        ilustrativa".
    #
    # E `checar_prompts.py` dava "ok" em todas elas, porque conferia o prompt
    # em portugues — o texto de onde o recorte era feito, nao o que era
    # enviado. A regra estava escrita, a varredura via, o modelo nao.
    #
    # Nao ha recorte mais. Sai so a linha de controle `MS_`, que e marcador
    # interno e nao instrucao.
    _preset_content = "\n".join(
        linha for linha in prompt_texto.splitlines()
        if not linha.startswith("MS_")
    ).strip()
    # Tres linhas em branco seguidas viravam quatro e cinco a cada bloco vazio
    # concatenado. Ruido no meio de instrucao e instrucao mais fraca.
    _preset_content = _re.sub(r"\n{3,}", "\n\n", _preset_content)

    _tipo_match = _re.search(r"TIPO DE IMAGEM:\s*(.+?)(?:\n|$)", prompt_texto)
    _tipo_str = _tipo_match.group(1).strip() if _tipo_match else "produto"

    # Seis sinalizadores de tipo (_is_close, _is_capa, _is_beneficios…) moravam
    # aqui só para escolher a porcentagem de ocupação. A porcentagem agora sai
    # de `OCUPACAO`, pelo número do tipo, e eles não tinham mais leitor: nome
    # vivo sem uso é o que faz a próxima pessoa achar que a regra está aqui.
    #
    # A peça tem painel de texto? É o que decide o teto de blocos de informação.
    _tem_texto_em_painel = MARCA_TEXTO_EXATO in prompt_texto
    # Quantos blocos a copy pediu de fato. O prompt numera "  1. ", "  2. "…
    _teto_blocos = faixa_de_blocos(_tipo_str)[1]
    _max_blocos = _teto_blocos or 3
    _pedidos_fechados = False
    if _tem_texto_em_painel:
        import re as _re_bl
        _pedidos = len(_re_bl.findall(r"^  \d+\. ", prompt_texto, _re_bl.M))
        if _pedidos:
            _pedidos_fechados = True
            # O teto da peça manda. Antes o piso era 3 e o teto 5 para todo
            # tipo: o Close, que comporta 2 callouts, recebia "Maximum 4".
            _max_blocos = min(_pedidos, _teto_blocos or _pedidos)

    # A MEDIDA VEM DE `OCUPACAO`, A MESMA QUE ALIMENTA O PROMPT EM PORTUGUES.
    #
    # Aqui existia uma segunda tabela de porcentagens, escrita a mao, que
    # discordava da primeira em TODOS os tipos: capa 85-92 contra 90-95 do
    # preset e 80-92 do bloco de protagonismo; close 80-92 contra os 55-70
    # genericos; ambientacao "at least 35%" contra "escala real". O modelo
    # recebia as duas e escolhia.
    _product_dominance_rule = ocupacao_em_ingles(_tipo_str)
    _, _espaco_en = regra_de_espaco(_tipo_str)

    # O Presenteie e a UNICA peca do padrao que pede figura humana, e o pedido
    # e do dono: "uma pessoa entregando o produto como presente para outra".
    _pede_pessoas = numero_do_tipo(_tipo_str) == 7

    # Referencia de layout nao se aplica a foto limpa.
    #
    # A capa e o produto sobre branco puro; a ambientacao e a cena real. O
    # estilo descrito das referencias e sempre o das pecas de marketing — fundo
    # azul-cinza da marca, faixas, blocos de texto —, e mandar "replique este
    # layout" junto com "fundo branco puro" da ao modelo duas ordens opostas.
    # Entre as duas ele escolhia a que vinha com mais detalhe, e a capa saia com
    # o fundo azul.
    _layout_section = (
        f"\n\nCOMPOSITION STYLE TO REPLICATE (apply this exact layout to the product above):\n{estilo_layout}"
        if estilo_layout and not _is_clean_photo else ""
    )

    _marketing_content = (
        f"\n\nCONTENT FROM COLLABORATOR (render these EXACT words as text in the image — "
        f"Brazilian Portuguese — in dedicated text zones):\n{_colaborador_brief}"
        if _is_marketing and _colaborador_brief else ""
    )

    # _instrucao_colaborador foi incorporado em _user_brief_section no prompt_geracao

    # 3. Monta prompt de geração
    # Quando enviado via Responses API (com fotos), a seção PRODUCT DESCRIPTION é
    # substituída por uma instrução de referência visual — o modelo VÊ as fotos.
    # ── AS FOTOS VIAJAM NOS DOIS MOTORES, ENTAO O TEXTO TEM DE DIZER ISSO
    #
    # Isto olhava a CHAVE DA OPENAI para decidir o TEXTO do prompt. Era certo
    # quando so o caminho da OpenAI levava fotos. Hoje o Gemini tambem leva
    # (`imagens_bytes=imagens_referencia`, adiante neste arquivo).
    #
    # Sem a chave da OpenAI, entao, o prompt dizia "PRODUCT DESCRIPTION —
    # recreate this product exactly from the description" enquanto as fotos
    # iam junto, e o modelo NUNCA era avisado de que elas sao a referencia.
    # Ele reconstruia o produto a partir de palavras, com as fotos na mao.
    #
    # E a explicacao direta de "produto nada a ver com o original", e ela
    # acontece exatamente na configuracao em que o Gemini e o motor
    # principal.
    #
    # A pergunta certa nao e "qual motor vai atender", e sim "as fotos vao?".
    _tem_fotos = bool(imagens_referencia)
    _product_section = (
        "PRODUCT REFERENCE: Use the product photos provided as the exact visual reference. "
        "Reproduce EVERY detail visible in those photos — same colors, shapes, proportions, "
        "textures, finishes and components. Do NOT invent or substitute any detail.\n\n"
        if _tem_fotos else
        f"PRODUCT DESCRIPTION (recreate this product exactly — match every detail described):\n"
        f"{descricao_produto}\n\n"
    )
    # ── Seção de USER/COLLABORATOR BRIEF (intenção específica) ──
    _user_brief_section = ""
    if _colaborador_brief:
        if _is_marketing:
            _user_brief_section = (
                f"\nUSER/COLLABORATOR BRIEF (specific intent — render these words as text in the image, "
                f"Brazilian Portuguese, in dedicated text zones):\n{_colaborador_brief}"
            )
        else:
            _user_brief_section = (
                f"\nUSER/COLLABORATOR BRIEF (specific visual intent — apply to composition):\n{_colaborador_brief}"
            )
    elif _colaborador_contexto:
        _user_brief_section = (
            f"\nPRODUCT CONTEXT (reference only — do NOT render as text in the image):\n{_colaborador_contexto}"
        )

    # ── AJUSTE FINO: editar, nao recriar ─────────────────────────────────────
    # O prompt de ajuste fino era descartado aqui. Este trecho remonta um prompt
    # de CRIACAO a partir de pedacos extraidos por regex ("TIPO DE IMAGEM:",
    # "CONTEXTO INTERNO..."), que o prompt de ajuste nao tem. Resultado: a
    # instrucao do colaborador — "deixe o album mais reto, com o weri-o virado a
    # direita" — nao chegava ao modelo, e ele recebia apenas "crie uma imagem de
    # produto sobre fundo branco". Por isso a foto voltava recomposta, com objetos
    # que ninguem pediu, e sem a mudanca solicitada.
    _prompt_ajuste = None
    if "MODO AJUSTE FINO" in prompt_texto:
        _m_instr = _re.search(
            r"MODIFICAÇÃO SOLICITADA[^\n]*:\n(.*?)(?=\n[A-ZÀ-Ú][A-ZÀ-Ú ]{4,}|\Z)",
            prompt_texto, _re.DOTALL
        )
        _instr_edicao = (_m_instr.group(1).strip() if _m_instr else "").strip()

        prompt_geracao = (
            "EDIT the provided image. This is not a new image — it is a surgical "
            "edit of the image supplied as reference.\n\n"
            "━━━ THE ONLY CHANGE TO MAKE ━━━\n"
            f"{_instr_edicao or '(no instruction provided)'}\n\n"
            "━━━ EVERYTHING ELSE IS UNTOUCHABLE ━━━\n"
            "- Keep the exact same product, colors, materials, lighting and framing\n"
            "- Do NOT add, remove or move any object that the instruction did not mention\n"
            "- Do NOT recompose, re-stage or re-render the scene from scratch\n"
            "- Do NOT add props, accessories, pens, pencils, plants, hands or decorations\n"
            "- Do NOT change the background style\n\n"
            f"BACKGROUND (must stay as it is): {_background}\n"
            f"TEXT RULE: {_text_rule}\n\n"
            "Return the same image with the single requested change applied. "
            "If the change is about position, angle or orientation of the product, "
            "reposition the product itself — do not compensate by changing anything else."
        )
        _prompt_ajuste = prompt_geracao

    prompt_geracao = (
        f"Create a professional e-commerce marketing image.\n\n"
        f"IMAGE TYPE: {_tipo_str}\n\n"

        f"━━━ SECTION 1: THE COMPLETE BRIEF FOR THIS PIECE (Brazilian Portuguese) ━━━\n"
        f"(This is the contract. Follow every line of it. The English sections below "
        f"restate it for the renderer and never replace it — if you ever read a "
        f"conflict, this section wins.)\n"
        f"{_preset_content}\n\n"

        f"━━━ SECTION 2: PRODUCT REFERENCE ━━━\n"
        f"{_product_section}"

        f"━━━ SECTION 3: USER / COLLABORATOR BRIEF ━━━\n"
        f"{_user_brief_section if _user_brief_section else '(none — follow type instructions only)'}\n\n"

        f"━━━ VISUAL STYLE ━━━\n"
        f"BACKGROUND: {_background}\n"
        # As cores da marca valem para TEXTO e elementos graficos. Numa foto
        # limpa nao existe nem um nem outro — e uma cor de marca sem onde ser
        # aplicada vira cor de fundo. Era a segunda ordem contraria que a capa
        # recebia junto com "branco puro".
        + (f"Graphic accents: derive text and graphic element colours from the "
           f"art direction chosen for THIS product, keeping enough contrast for "
           f"legibility. There is no fixed brand colour.\n"
           f"Typography: Clean geometric sans-serif (Montserrat or Poppins style) "
           f"— this IS fixed, and it is what makes every piece look like the "
           f"same shop.\n"
           if not _is_clean_photo else
           "NO brand color anywhere: this image has no text and no graphic "
           "elements, so no brand accent color may appear — not in the "
           "background, not as a tint, not as a gradient.\n")
        + f"Professional e-commerce aesthetic — clean, airy, high-end studio quality.\n\n"

        f"TEXT RULE: {_text_rule}\n\n"

        f"COMPOSITION:\n"
        f"{_product_dominance_rule}\n"
        f"- Maintain product exact proportions — NEVER stretch, compress, or distort\n"
        # O LIMITE DE BLOCOS SAI DO TEXTO QUE FOI PEDIDO.
        #
        # Estava fixo em 3. O plano da triagem pede 4 cartões e a composição
        # manda no máximo 3 — duas ordens contrárias no mesmo prompt, e o
        # gerador decide sozinho o que cortar. Na Caneca Medieval ele
        # empilhou os quatro e passou por cima do produto.
        #
        # Agora o teto é o que a copy pediu, com um máximo de 5: mais que
        # isso vira parede de texto em miniatura de marketplace.
        # "MAXIMUM N" PERMITE MENOS. O portugues ja disse "exatamente N".
        #
        # Quando a copy existe, `_max_blocos` E o numero exato — e dizer
        # "maximo" ao lado de "exatamente" e enfraquecer a propria ordem, na
        # metade do prompt que fica mais perto do fim. Com copy: EXACTLY.
        # Sem copy, nao ha numero fechado, e "maximum" continua certo.
        + ((f"- EXACTLY {_max_blocos} information element(s) — "
            f"never fewer, never more, never merged\n"
            if _pedidos_fechados else
            f"- Maximum {_max_blocos} information elements if text present — never cluttered\n")
           if not _is_clean_photo else
           "- No text elements at all: no whitespace has to be reserved for "
           "them. The occupancy stated above is the only rule about size.\n")
        + _espaco_en
        + f"- Professional studio quality — high-end e-commerce agency standard"
        f"{_layout_section}\n\n"
        f"{_marketing_content}"

        f"━━━ PRODUCT INTEGRITY RULES ━━━\n"
        f"PRODUCT (absolute fidelity — never alter):\n"
        f"- Reproduce EXACTLY: same colors, shape, proportions, every visible detail\n"
        f"- NEVER invent, remove, redesign or alter: components, controls, mechanisms, "
        f"openings, connectors, or accessories presented as included with the product\n"
        f"- NEVER deform or stretch the product — maintain exact proportions always\n\n"
        f"SCENE ELEMENTS (controlled freedom):\n"
        f"- Environmental objects may be created when required by the image type or user brief\n"
        f"- Scene elements must remain visually secondary and must not be confused with "
        f"included product accessories\n\n"
        f"ACCESSORIES / ITEMS THAT MAY SEEM INCLUDED (extreme care):\n"
        f"- NEVER add objects beside the product that could be mistaken for included accessories\n"
        f"- Example: do NOT place 20 drill bits next to a drill — this implies they are included\n"
        f"- Only include accessories explicitly mentioned in product data or user brief\n\n"
        f"ADDITIONAL RULES:\n"
        + (
            "- PEOPLE ARE REQUIRED in this image type: two people, one handing the "
            "product to the other. The pair must match the product's audience, as "
            "SECTION 1 defines. Hands and the product must read clearly; faces stay "
            "secondary.\n"
            if _pede_pessoas else
            "- NEVER add people or human figures unless the image type or collaborator "
            "brief explicitly requests them\n"
        )
        +
        f"- All text visible in the image must be in Brazilian Portuguese\n"
        f"- Generate a completely new professional image — not a literal copy of any reference photo\n\n"
        f"━━━ THE TIE-BREAKER ━━━\n"
        f"The environment adapts to the product. The product NEVER adapts to the "
        f"environment.\n"
        f"The real product photographs have higher priority than the palette, the art "
        f"direction, the lighting, the styling and the scene.\n"
        f"If any instruction in this message conflicts with the real product reference, "
        f"IGNORE that instruction and preserve the product exactly as photographed."
    )

    # Ajuste fino manda sobre o prompt de criacao: aqui a imagem ja existe e o
    # pedido e cirurgico, nao "crie uma imagem de produto".
    if _prompt_ajuste:
        prompt_geracao = _prompt_ajuste

    # 3.5 Referência de layout desta peça, escolhida pelo nome do arquivo.
    #
    # Antes, as referências de layout só viravam TEXTO: o Claude descrevia as duas
    # primeiras e o gerador nunca via imagem nenhuma de composição. Descrição em
    # palavras perde o que a referência tem de útil — posição dos blocos, peso
    # tipográfico, respiro. Agora a imagem vai junto.
    #
    # Vai UMA só, a que corresponde a este tipo, e sempre por último, depois das
    # fotos do produto. A ordem importa: o modelo precisa saber que as primeiras
    # são o produto a reproduzir e a última é só molde de composição — senão ele
    # copia o produto da referência, que é o erro mais caro possível aqui.
    _ref_layout_bytes, _ref_layout_nome = ref_layout_do_tipo(
        tipo, refs_layout, refs_layout_nomes
    )
    if _ref_layout_bytes:
        prompt_geracao += (
            "\n\nIMAGENS ENVIADAS — o que é cada uma:\n"
            f"- As primeiras imagens são FOTOS DO PRODUTO REAL. Reproduza o produto "
            f"exatamente como aparece nelas: cor, forma, proporções, acabamento.\n"
            # O nome do arquivo saiu daqui tambem: a ordem ja identifica a
            # referencia, e o nome era porta para objeto e pessoa entrarem.
            f"- A ÚLTIMA imagem é apenas REFERÊNCIA DE LAYOUT (a última das "
            f"enviadas"
            f"). Use dela SOMENTE a composição: "
            f"{AUTORIDADE_DA_REFERENCIA}.\n"
            f"- PROIBIDO copiar o produto, as cores do produto, marcas ou textos da "
            f"imagem de referência de layout. O produto da peça final é o das "
            f"primeiras fotos, nunca o da referência."
        )
    if diagnostico is not None:
        diagnostico["ref_layout"] = _ref_layout_nome or "nenhuma correspondeu ao tipo"
        diagnostico["prompt"] = prompt_geracao

    # ── PARAR AQUI, SEM GASTAR ────────────────────────────────────────────
    #
    # O prompt esta pronto e nenhum motor foi chamado ainda. `so_montar`
    # devolve exatamente este texto — o que SERIA enviado — para a tela do
    # plano mostrar antes de o dono confirmar.
    #
    # Tem de sair daqui, e nao de uma segunda montagem numa funcao de
    # preview: duas montagens do mesmo prompt discordam, e a discordancia
    # aparece tres semanas depois na tela de alguem. Ja aconteceu nesta base
    # com a varredura, que conferia o prompt em portugues enquanto o motor
    # recebia outro.
    #
    # A tupla continua sendo (imagem, erro); o texto viaja no diagnostico.
    if so_montar:
        return None, ""

    # ── O PROMPT QUE FOI AO MOTOR FICA GRAVADO ────────────────────────────
    #
    # Pedido do dono em 25/09: *"preciso ter acesso do prompt original que
    # gerou as imagens, e do prompt que o sistema utilizou para corrigir"* —
    # para cruzar um com o outro.
    #
    # AQUI, E NÃO EM CADA CHAMADOR. Esta é a única porta do motor: geração,
    # ajuste fino, refação e o que vier depois passam todos por ela. Registrar
    # em cada chamador é a receita para o quinto esquecer.
    #
    # O marcador do ajuste está no próprio texto (`montar_prompt_ajuste_fino`
    # abre com "MODO AJUSTE FINO"), então a linha sabe qual dos dois é sem
    # precisar de parâmetro novo em quinze lugares.
    #
    # NUNCA pode derrubar a geração: `registrar` engole a própria exceção, e
    # este `try` cobre até o import.
    try:
        import log_imagem as _li
        _eh_ajuste = "MODO AJUSTE FINO" in (prompt_geracao or "")
        # A PEÇA É A CHAVE DA CADEIA. Na geração ela é o número do tipo (a
        # peça 4 é a peça 4 do plano); no ajuste, a que o chat marcou.
        _peca = (peca_em_ajuste() if _eh_ajuste
                 else str(numero_do_tipo(tipo) or ""))
        _li.registrar(
            "prompt_ajuste" if _eh_ajuste else "prompt_geracao",
            instrucao="", imagem=_peca, tipo=(tipo or ""),
            resultado="enviado ao motor", prompt=prompt_geracao)
    except Exception:
        pass

    # 4. Tenta o motor primário da OpenAI
    img_bytes = None
    erro_primario = None
    _usando_openai = bool(_get_openai_api_key())
    if not _usando_openai:
        # SEM CHAVE, O MOTOR PRIMÁRIO NÃO É TENTADO — e isso precisa ter nome.
        #
        # Antes, a ausência da chave fazia o `if` abaixo ser pulado e
        # `erro_primario` continuava None: TODA geração ia para o Gemini, que é
        # o reserva, e ninguém era avisado. Os créditos do Gemini acabaram
        # porque ele estava fazendo o trabalho dos dois, e a mensagem que
        # sobrou na tela falava só de crédito do Gemini — escondendo que o
        # primário nunca tinha entrado em campo.
        erro_primario = ("OPENAI_API_KEY não está configurada no Railway — o "
                         "motor primário de imagem não chegou a ser "
                         "tentado, e TODA a geração caiu no reserva.")
        if diagnostico is not None:
            diagnostico["erro_openai"] = erro_primario

    if _usando_openai:
        # Passa as fotos do produto diretamente ao modelo via Responses API
        # (igual ao ChatGPT) — o modelo VÊ as fotos em vez de receber só texto.
        # Se não houver fotos, cai em geração texto-puro.
        _fotos_para_openai = imagens_referencia if imagens_referencia else None
        img_bytes, erro = _chamar_openai_geracao(
            prompt_geracao, imagens_bytes=_fotos_para_openai,
            ref_layout=_ref_layout_bytes, ref_layout_nome=_ref_layout_nome,
            diagnostico=diagnostico
        )
        if not img_bytes:
            erro_primario = f"OpenAI {modelo_de_imagem()}: {erro}"

    if diagnostico is not None:
        diagnostico["prompt_final"] = prompt_geracao
        diagnostico["fotos_disponiveis"] = len(imagens_referencia or [])
        if erro_primario:
            diagnostico["erro_openai"] = erro_primario

    def _falha(motivo, cota=False):
        """A ÚNICA saída de erro da geração — e ela SEMPRE diz dos dois motores.

        Havia seis `return None, ...` no bloco abaixo e só dois carregavam
        `erro_primario`. Foi assim que a tela mostrou oito vezes "Erro HTTP 402"
        do RESERVA sem uma palavra sobre o primário, que é quem devia ter
        gerado — e o dono ficou sem a única informação que explicava o resto:
        por que o reserva estava em campo.

        Corrigir a linha que apareceu não resolve: o defeito é uma função com
        várias saídas de erro, onde consertar uma deixa as outras. Por isso a
        montagem da mensagem mora aqui, e não em cada `return`.
        """
        if cota:
            motivo = (
                "⛔ Cota ou créditos da GEMINI_API_KEY esgotados. Crie uma nova "
                "chave em aistudio.google.com/apikey vinculada ao projeto GCP e "
                f"atualize GEMINI_API_KEY no Railway. Detalhe: {motivo[:200]}"
            )
        if erro_primario:
            return None, (f"{motivo}\n\n**E o motor primário falhou antes:** "
                          f"{erro_primario}")
        return None, (f"{motivo}\n\nO motor primário de imagem também não "
                      "entregou nesta tentativa.")

    # 5. RESERVA: Gemini Flash Image — E ELE RECEBE AS FOTOS.
    #
    # ESTE COMENTARIO MENTIA, E A MENTIRA CUSTOU HORAS.
    #
    # Ele dizia "ATENCAO: este caminho NAO recebe as fotos do produto — so o
    # texto". Isso foi verdade um dia; hoje a linha logo abaixo manda
    # `imagens_bytes=imagens_referencia`. Alguem corrigiu o codigo e nao o
    # comentario.
    #
    # Em 30/09 eu li este comentario, acreditei nele, e por isso demorei a
    # ver que `_tem_fotos` decidia o TEXTO do prompt pela chave da OpenAI
    # enquanto as fotos viajavam de qualquer jeito. O defeito estava a vinte
    # linhas daqui, escondido atras de uma documentacao desatualizada.
    #
    # O que continua verdade: este motor NAO aceita `size` nem
    # `input_fidelity`. Sem eles a imagem volta retangular (o Studio
    # preenche, e isso e a margem) e o produto e redesenhado. Por isso o
    # diagnostico marca este caminho de forma bem visivel, e a tela diz.
    if not img_bytes:
        if diagnostico is not None:
            _n_refs = len(fotos_para_o_motor(imagens_referencia))
            diagnostico["motor"] = "Gemini 3.1 Flash Image (fallback, COM fotos)"
            diagnostico["refs_enviadas"] = _n_refs
            diagnostico["size_pedido"] = "não suportado neste motor"
        resp, erro_fatal = _chamar_gemini_geracao_texto(
            prompt_geracao, imagens_bytes=imagens_referencia,
            ref_layout=_ref_layout_bytes, diagnostico=diagnostico
        )
        if erro_fatal:
            msg = erro_fatal.replace("COTA_ESGOTADA:", "")
            if erro_fatal.startswith("COTA_ESGOTADA:"):
                return _falha(msg, cota=True)
            return _falha(f"Gemini: {msg[:300]}")

        if resp is None:
            return _falha("Falha ao conectar ao gerador de imagem.")

        if resp.status_code != 200:
            try:
                _err = resp.json().get("error", {}).get("message", resp.text[:1500])
            except Exception:
                _err = resp.text[:1500]
            # Mesmo com a peneira de crédito já aplicada no motor, este ramo
            # repete a pergunta: um código novo não pode voltar a virar só
            # "Erro HTTP nnn" na tela.
            _sem_credito = _resposta_sem_credito(resp.status_code, _err)
            return _falha(f"Erro HTTP {resp.status_code}: {_err}"
                          if not _sem_credito else _err, cota=_sem_credito)

        try:
            dados = resp.json()
        except Exception:
            return _falha("Resposta inválida do gerador (não é JSON).")

        img_b64 = ""
        for candidate in dados.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                inline = part.get("inlineData") or part.get("inline_data", {})
                if inline and inline.get("data"):
                    img_b64 = inline["data"]
                    break
            if img_b64:
                break

        if not img_b64:
            try:
                _detail = dados.get("error", {}).get("message", "") or str(dados)[:300]
            except Exception:
                _detail = str(dados)[:300]
            return _falha(
                "Gerador não retornou imagem (possível bloqueio ou créditos "
                f"esgotados). Detalhe: {_detail}",
                cota=_resposta_sem_credito(200, _detail),
            )

        img_bytes = base64.b64decode(img_b64)
        # ── AQUI MORAVA UM `st.warning` QUE NINGUEM NUNCA VIU ─────────────
        #
        # Dono, 30/09: "fotos menores que a dimensao da imagem, informacoes
        # recortadas, fotos nada a ver com o produto original, imagens com
        # margem". Os quatro sao o MESMO estado: o motor primario nao
        # atendeu e tudo caiu no reserva, que NAO aceita `size` nem
        # `input_fidelity` — volta retangular, o Studio preenche (margem), o
        # produto encolhe, e sem `input_fidelity` ele e redesenhado.
        #
        # A unica mensagem que explicava isso era este `st.warning`. E
        # `gerar_imagem_ia` roda DENTRO de uma `threading.Thread`
        # (`_gerar_imagem_thread`): thread nao fala com a tela do Streamlit,
        # e a frase era descartada em silencio, toda vez.
        #
        # E a Forma 6 desta base — restricao de ambiente aplicada a UM
        # leitor. `st.session_state` ja tinha sido varrido; `st.warning`
        # ficou. Agora a varredura pega as duas (checar_alcance).
        #
        # O recado passa a viajar no DIAGNOSTICO, que a thread pode escrever,
        # e quem desenha e a tela — do lado certo do balcao.
        if erro_primario and diagnostico is not None:
            diagnostico["motor_reserva"] = (
                f"{erro_primario} — a peça foi feita pelo motor reserva, que "
                "não aceita pedido de imagem quadrada nem preservação do "
                "produto. É por isso que ela pode vir com margem, com o "
                "produto menor ou com o produto redesenhado.")

    # 6. Processa imagem — preserva proporções exatas (sem deformação)
    try:
        from PIL import Image as _PILImage
        import io as _io
        pil = _PILImage.open(_io.BytesIO(img_bytes)).convert("RGBA")
        if diagnostico is not None:
            diagnostico["tamanho_bruto"] = f"{pil.size[0]}x{pil.size[1]}"

        # Enquadramento para 1200x1200.
        #
        # A geração agora pede size=1024x1024, então o normal é a imagem JÁ chegar
        # quadrada e nada acontecer aqui. O tratamento abaixo é rede de segurança
        # para quando a API recusa o parâmetro e devolve 1536x1024 ou 1024x1536.
        #
        # Nesse caso, preencher com faixas de cor lisa era o que produzia as
        # "tarjas" brancas e encolhia o produto no meio do quadro. Agora recorta
        # o excedente até o limite do que é seguro (_CROP_MAX) e só preenche o
        # que sobrar — em vez de preencher tudo. Crop total nunca é opção: a zona
        # de texto das peças de marketing fica nas laterais e seria decepada.
        pil_w, pil_h = pil.size
        if pil_w != pil_h:
            import sys as _sys_fmt
            print(f"[DEBUG enquadramento] modelo devolveu {pil_w}x{pil_h} "
                  "(esperado 1024x1024) — preenchendo", file=_sys_fmt.stderr)
            # O PREENCHIMENTO PASSA A APARECER NA TELA.
            #
            # Ele existia só no stderr do Railway — e foi assim que as tarjas
            # ficaram sem explicação por semanas: o Studio SABIA que estava
            # preenchendo, anotava, e ninguém lia. Quem vê a imagem com margem
            # é a colaboradora, e é a ela que a informação serve.
            #
            # A rede fica: devolver imagem com margem é melhor do que devolver
            # imagem quebrada. Mas deixa de ser invisível.
            if diagnostico is not None:
                diagnostico["enquadramento"] = (
                    f"o motor devolveu {pil_w}x{pil_h} em vez de quadrada — "
                    f"as faixas laterais foram preenchidas pelo Studio")

            # UMA REPETIÇÃO ANTES DE ENTREGAR TORTA.
            #
            # O Studio SABIA que estava preenchendo faixa — anotava no
            # diagnóstico — e entregava assim mesmo. A colaboradora recebia a
            # imagem com margem, pedia correção, e a correção quebrava outra
            # coisa: o laço que custou 41 gerações num produto só.
            #
            # Uma geração automática custa menos que três rodadas dela. Só
            # UMA: se o motor devolver torta duas vezes seguidas, é o motor
            # ignorando o pedido de 1024x1024, e insistir vira dinheiro
            # queimado sem mudar o resultado.
            if not _ja_repetiu_quadrada:
                import sys as _sys_rep
                print(f"[DEBUG enquadramento] repetindo UMA vez para tentar "
                      f"sair quadrada (veio {pil_w}x{pil_h})",
                      file=_sys_rep.stderr, flush=True)
                _nova, _erro_rep = gerar_imagem_ia(
                    prompt_texto, imagens_referencia, refs_layout,
                    refs_layout_nomes, tipo, diagnostico,
                    _ja_repetiu_quadrada=True)
                if _nova and not _erro_rep:
                    return _nova, None
                # Falhou a repetição: segue com a imagem que já existe. Ela
                # está paga, e entregar com margem é melhor que não entregar.
                if diagnostico is not None:
                    diagnostico["enquadramento"] = (
                        diagnostico.get("enquadramento", "")
                        + " · repeti uma vez e voltou torta de novo")

            # O ENQUADRAMENTO SAIU DAQUI PARA `enquadrar.py`.
            #
            # Aqui morava "NÃO recortar": recortar já tinha sido tentado, às
            # cegas, 18% do lado maior, e decepava os painéis de texto. A
            # conclusão foi preencher sempre — e o log de 24/09 mostrou o
            # preço disso: 768x1365 virando quadrado com 597 px de faixa, em
            # TODA geração, porque o Gemini nunca devolve quadrado.
            #
            # `enquadrar.quadrar` recorta em volta da CAIXA DO ASSUNTO, que
            # inclui o painel de texto — e só preenche quando o assunto
            # realmente não cabe. Não é o recorte cego com outro nome.
            import enquadrar as _enq
            _cru = _io.BytesIO()
            pil.save(_cru, format="PNG")
            # A PECA DIZ SE TEM TEXTO, E O ENQUADRAMENTO OBEDECE.
            #
            # Dono, 30/09: "Imagem 2 e imagem 5 com texto cortando". O corte
            # para quadrado decepava o painel lateral: `enquadrar.janela`
            # fazia recorte CENTRAL sempre que a caixa do assunto cobria o
            # quadro, com o comentario "nao ha painel de texto para decepar".
            #
            # Numa peca de marketing o cenario vai ate as bordas, entao a
            # caixa cobre 100% — e o corte come a lateral onde o texto mora.
            # Medido: corte comecando em x=200 com o painel indo de 30 a 430.
            #
            # `_is_clean_photo` ja sabia a resposta: capa e ambientacao sao
            # as duas sem texto. Ela so nunca tinha sido passada adiante.
            img_bytes, _relato = _enq.quadrar(
                _cru.getvalue(), fundo_branco=_is_fundo_branco,
                lado_final=1200, tem_texto=not _is_clean_photo)
            if _relato and diagnostico is not None:
                diagnostico["enquadramento"] = _relato
            pil = _PILImage.open(_io.BytesIO(img_bytes)).convert("RGBA")

        pil = pil.resize((1200, 1200), _PILImage.LANCZOS)
        buf = _io.BytesIO()
        pil.save(buf, format="PNG")
        img_bytes = buf.getvalue()
    except Exception:
        pass

    # ── QUAL MOTOR FEZ ESTA PEÇA — NA LINHA DO LOG, E NÃO SÓ NA TELA ─────
    #
    # Dono, 30/09, quando pedi que ele conferisse numa tela qual motor a conta
    # tinha: *"eu que tenho que confirmar? você que codificou o sistema..."*.
    #
    # Ele estava certo, e o defeito é este: o Studio SABE qual motor fez cada
    # peça — grava em `diagnostico["motor"]` nos cinco caminhos — e a linha
    # do log, que é o registro que sobrevive à sessão, dizia
    # `resultado="enviado ao motor"`. "O motor". Sem dizer qual.
    #
    # E é a pergunta mais importante que existe sobre uma peça torta: margem
    # e produto redesenhado vêm de a peça ter sido feita pelo RESERVA, que
    # não aceita `size=1024x1024` nem `input_fidelity=high`. Sem o nome do
    # motor na linha, o `.txt` do histórico não responde isso, e a pergunta
    # cai numa pessoa.
    #
    # Uma linha por peça, no mesmo lugar em que a peça fica pronta — não é
    # laço de tela, não roda por tecla.
    try:
        import log_imagem as _li_motor
        _d_mot = diagnostico or {}
        _motor_usado = str(_d_mot.get("motor") or "").strip()
        _li_motor.registrar(
            "motor_da_peca",
            instrucao=str(_d_mot.get("enquadramento") or ""),
            imagem=(peca_em_ajuste() if "MODO AJUSTE FINO" in (prompt_texto or "")
                    else str(numero_do_tipo(tipo) or "")),
            tipo=(tipo or ""),
            resultado=(_motor_usado or "motor não registrado"),
        )
    except Exception:
        # Registro é apoio, não requisito: nunca pode derrubar a geração.
        pass

    # ── A RÉGUA PASSA NA IMAGEM ANTES DE ELA SAIR DAQUI ──────────────────
    #
    # Cobrança do dono: "Eu testo o código, não a imagem. Você precisa
    # conferir isso!!!". Estava certo — todo teste desta base conferia que o
    # prompt tinha a frase certa, e quem via o resultado era a colaboradora,
    # depois de gerado e pago.
    #
    # A medição é geométrica e determinística: formato, faixa lisa na borda e
    # ocupação do produto. Ela NÃO julga fidelidade — haste virar três
    # cilindros não se mede com régua, e isso continua sendo da conferência
    # por visão. Medir o que dá para medir não é medir tudo, e é honesto
    # dizer onde a régua acaba.
    #
    # Em cena ambientada a ocupação NÃO é cobrada: ali a escala do produto é
    # a real, e exigir que ele encha o quadro foi exatamente o que produziu o
    # produto gigante.
    try:
        import medir_imagem as _md
        # `com_texto` LIGA a medida do texto cortado, e `_is_clean_photo` ja
        # sabia a resposta: capa e ambientacao sao as duas SEM texto. Era a
        # mesma informacao que faltava chegar ao enquadramento, duas funcoes
        # atras — a diferenca e que agora ela chega aos dois.
        _probs = _md.problemas(img_bytes, fundo_chapado=_is_fundo_branco,
                               ambientada=_is_ambientacao,
                               com_texto=not _is_clean_photo)
        # ── E A PECA SE PARECE COM O PRODUTO DAS FOTOS? ─────────────────
        #
        # Dono, 30/09: "por que que as imagens acabam sendo geradas diferente
        # do que o produto de fato e?".
        #
        # O prompt manda "TRAVA DE COR (regra inviolavel)" e "PROIBICAO
        # ABSOLUTA: JAMAIS substitua o produto das fotos" — e o Studio
        # entregava sem NUNCA comparar a peca com as fotos. Regra que ninguem
        # confere e torcida, nao regra.
        #
        # A medida compara a PALETA DO ASSUNTO dos dois lados, e basta casar
        # com UMA das fotos: elas sao angulos do mesmo produto. Ela entra no
        # mesmo `_probs`, entao reprovar aqui ja refaz a peca uma vez — o
        # caminho que a faixa lisa ja usava.
        _dif_prod = _md.produto_diferente(img_bytes, imagens_referencia)
        if _dif_prod:
            _probs = list(_probs) + [_dif_prod]
        if diagnostico is not None and _probs:
            diagnostico["medida"] = " · ".join(_probs)
        if _probs and not _ja_repetiu_quadrada:
            import sys as _sys_md
            print(f"[DEBUG medida] {'; '.join(_probs)} — repetindo uma vez",
                  file=_sys_md.stderr, flush=True)
            _nova2, _err2 = gerar_imagem_ia(
                prompt_texto, imagens_referencia, refs_layout,
                refs_layout_nomes, tipo, diagnostico,
                _ja_repetiu_quadrada=True)
            if _nova2 and not _err2:
                return _nova2, None
    except Exception:
        # A régua nunca pode impedir a entrega: a imagem já foi paga.
        pass

    # Fora do try acima de proposito: mesmo que o enquadramento falhe, o peso
    # maximo da plataforma continua valendo.
    img_bytes = comprimir_para_limite(img_bytes)
    if diagnostico is not None:
        diagnostico["peso_final"] = f"{len(img_bytes or b'') / 1048576:.2f} MB"
        diagnostico["formato_final"] = extensao_de(img_bytes)

    return img_bytes, None



# ── A REFERENCIA DE LAYOUT TINHA DUAS AUTORIDADES, E ELAS DISCORDAVAM ─────
#
# Em portugues, o bloco anexado ao plano dizia: "USE das referencias:
# posicionamento, hierarquia de elementos, estilo de texto, USO DE
# PESSOAS/CENARIOS". Em ingles, o bloco anexado a CHAMADA DO MOTOR dizia:
# "Use dela SOMENTE a composicao: posicao dos blocos, hierarquia, estilo dos
# textos, uso do espaco".
#
# A segunda e a certa, e a primeira e a porta por onde entraram o "cinzeiro"
# e o "casal" de uma referencia chamada `ref_cinzeiro_casal.png` — o mesmo
# vazamento que `limpar_descricao_de_layout` existe para impedir, entrando
# pelo lado. Uma referencia de layout empresta ESTRUTURA; pessoa e cenario
# sao conteudo, e conteudo vem do plano e das fotos do produto.
#
# Agora a lista e UMA, e os dois textos a leem daqui.
AUTORIDADE_DA_REFERENCIA = ("posição dos blocos, hierarquia dos elementos, "
                            "estilo dos textos, uso do espaço")

INSTRUCAO_REFERENCIA_LAYOUT = """
IMAGENS DE REFERÊNCIA DE LAYOUT — REGRAS ABSOLUTAS:
- As imagens de referência de layout mostram COMPOSIÇÃO, POSIÇÃO, ESTILO e ESTRUTURA visual
- O produto nessas imagens de referência NÃO É o produto a ser gerado — é apenas um exemplo de layout
- USE das referências SOMENTE isto: {autoridade}
- NÃO USE delas pessoa, cenário, objeto, prop nem clima: isso é CONTEÚDO, e o conteúdo vem do plano e das fotos do produto
- NÃO USE das referências: o produto em si, cores do produto de referência, marcas ou logotipos visíveis
- Aplique o layout/composição da referência ao PRODUTO DO COLABORADOR com as cores MartinSousa
- Se o arquivo de referência tiver nome indicando o tipo (ex: "fundo_branco", "beneficios"), essa referência se aplica especificamente àquele tipo de imagem
"""


def _trava_cor_produto(cor):
    """Trava a cor do produto no prompt, citando o que NÃO pode acontecer.

    Dizer "mesma cor" é semântico demais: o gerador trata como sugestão e
    "harmoniza" o produto com a paleta azul da marca ou com o cenário. Foi assim
    que um álbum preto saiu azul-marinho (#1A3A6B, exatamente a cor da marca) e
    outro saiu bege. Nomear a cor real e listar os desvios proibidos deixa a
    instrução verificável em vez de interpretável.
    """
    cor = str(cor).strip()

    # Desvios que já aconteceram em produção, mais a paleta da marca — que é a
    # fonte da contaminação e por isso precisa ser negada nominalmente.
    desvios = ["azul", "azul-marinho", "azul médio", "bege", "marrom", "cinza-azulado"]
    cor_norm = cor.lower()
    desvios = [d for d in desvios if d not in cor_norm]

    if not cor:
        # Sem a cor informada na triagem não dá para nomeá-la — mas a proibição
        # de repintar continua valendo. Antes, campo vazio significava nenhuma
        # trava, e o álbum preto voltava azul-marinho (o hex da marca).
        return (
            "TRAVA DE COR (regra inviolável): a cor do produto é a que aparece nas fotos "
            "de referência. Reproduza-a exatamente, seja ela qual for.\n"
            "É PROIBIDO recolorir o produto para harmonizar com a direção de arte da peça, "
            "com o fundo, com o cenário ou com a iluminação. A direção de arte vale para "
            "fundo, texto e elementos gráficos — nunca para o produto.\n"
            f"É PROIBIDO tingir o produto de: {', '.join(desvios)}, "
            "a menos que essa seja de fato a cor nas fotos.\n"
        )

    return (
        f"COR REAL DO PRODUTO: {cor}\n"
        f"TRAVA DE COR (regra inviolável): a cor do produto é uma propriedade física, "
        f"não uma escolha estética. O produto DEVE aparecer em {cor} exatamente como "
        f"nas fotos de referência.\n"
        f"É PROIBIDO reinterpretar essa cor como: {', '.join(desvios)}.\n"
        f"É PROIBIDO recolorir o produto para harmonizar com a direção de arte da peça, "
        f"com o fundo, com o cenário ou com a iluminação. A direção de arte vale para "
        f"fundo, texto e elementos gráficos — nunca para o produto.\n"
    )


# O rótulo que o Ajuste Fino escreve no lugar do tipo. Ele é texto para o
# colaborador ler — "Ajuste Fino — aumente o produto" —, e NÃO é um tipo: não
# está em PRESETS, e `PRESETS.get` devolve "" para ele.
AJUSTE_FINO_PREFIXO = "Ajuste Fino —"

PERSONALIZADO = "Personalizado (descrevo o que quero)"


def eh_rotulo_de_ajuste(tipo):
    return str(tipo or "").strip().startswith(AJUSTE_FINO_PREFIXO)


def tipo_para_gerar(item):
    """O tipo a usar ao GERAR de novo. Aceita o dicionário da galeria ou o texto.

    Uma imagem nascida do Ajuste Fino não tem preset: o rótulo dela é a frase
    que o colaborador escreveu. Mandada como tipo para `montar_prompt_imagem`,
    `PRESETS.get` devolvia "" — e, como o rótulo também não casava com nenhuma
    regra de fundo, ela caía no "padrao" e recebia o branding genérico INTEIRO
    sem composição nenhuma por baixo.

    O resultado é o que o colaborador viu: pediu para recompor o quadro, o
    Studio disse "refazendo do zero", e voltou a mesma imagem. Sem erro, sem
    aviso, quatro rodadas.

    Quando a imagem guarda de que tipo ela nasceu, vale esse. Quando não
    guarda, vale Personalizado: sem preset, quem manda é a instrução — que é
    justamente o que o colaborador acabou de escrever.
    """
    if isinstance(item, dict):
        base = str(item.get("tipo_base") or "").strip()
        if base and base in PRESETS:
            return base
        tipo = str(item.get("tipo") or "").strip()
    else:
        tipo = str(item or "").strip()
    if tipo in PRESETS and tipo != PERSONALIZADO:
        return tipo
    return PERSONALIZADO


def modo_fundo_do_tipo(tipo):
    """Qual regra de fundo o tipo de imagem segue: branco, ambiente, personalizado, padrao.

    Regra do dono do produto: só a capa tem fundo branco; as ambientadas usam o
    fundo do próprio ambiente; as demais usam o azul-cinza da marca.
    """
    tipo = tipo or ""
    if tipo == PERSONALIZADO:
        return "personalizado"
    # Rótulo de Ajuste Fino não é tipo, e cair no "padrao" fazia a imagem
    # receber o branding inteiro sem preset nenhum embaixo.
    if eh_rotulo_de_ajuste(tipo):
        return "personalizado"
    if tipo.startswith("1 —") or "fundo branco" in tipo.lower() or "capa" in tipo.lower():
        return "branco"
    if tipo.startswith("8 —"):
        return "ambiente"
    return "padrao"


def bloco_texto_exato(textos):
    """O trecho do prompt que manda DESENHAR estas palavras, e nenhuma outra.

    Um gerador de imagem não escreve: ele desenha letras. Dada uma ideia
    ("fale dos benefícios"), ele redige a frase sozinho e erra as letras no
    caminho — "Apretica newtona estético", "relievarriamento do stresse",
    "Portátile e compacto". Dada a frase pronta, ele copia, e copiar é o que
    ele faz bem.

    Por isso o mesmo bloco serve às duas horas em que o texto é conhecido: na
    primeira geração, com a copy que a triagem escreveu, e na refação, com a
    correção que a revisão devolveu. Uma redação só — se as duas divergissem,
    a peça refeita sairia diferente da peça planejada.
    """
    # UMA LINHA QUEBRADA NÃO É UM BLOCO NOVO.
    #
    # O texto corrigido volta da revisão como TEXTO, e texto volta com quebra
    # de linha onde a frase era longa. Cortar por linha transformava
    # "METAL E INOX: durável para uso diário intenso" em três blocos, e a
    # numeração saía 1., 4., 7. nos títulos — foi o "embaralhado" que o dono
    # viu na peça 2 em 28/09.
    #
    # O que começa um bloco é o TÍTULO: palavra(s) em caixa alta seguidas de
    # dois-pontos, que é o formato que a triagem escreve e que a revisão
    # devolve. Linha sem título é continuação da anterior.
    if isinstance(textos, str):
        linhas = []
        for bruto in textos.splitlines():
            t = bruto.strip()
            if not t:
                continue
            if linhas and not _INICIO_DE_BLOCO.match(t):
                linhas[-1] = (linhas[-1] + " " + t).strip()
            else:
                linhas.append(t)
    else:
        linhas = [" ".join(str(t).split()) for t in (textos or [])
                  if str(t).strip()]
    if not linhas:
        return ""
    corpo = "\n".join(f"  {i}. {t}" for i, t in enumerate(linhas, 1))
    return (
        "\n━━━ TEXTO EXATO A ESCREVER (copie letra por letra) ━━━\n"
        + corpo + "\n"
        "REGRAS DESTE TEXTO, acima de qualquer outra instrução de texto:\n"
        "- Escreva EXATAMENTE estas palavras, letra por letra, com os mesmos "
        "acentos. Não reescreva, não resuma, não traduza, não melhore.\n"
        # O NÚMERO É MEU, NÃO É DA PEÇA.
        #
        # "1. ", "2. " servem para contar os blocos — e o gerador copiava o
        # número junto com o texto, porque a linha acima manda escrever
        # EXATAMENTE o que está escrito. Os cartões do dono saíram com
        # "1. METAL E INOX", "2. DESIGN ÚNICO", "3. 400ML", e o mesmo formato
        # está no histórico de outro produto, de semanas antes.
        "- Os números **1.**, **2.**, **3.** são apenas a contagem dos blocos: "
        "NÃO desenhe o número na imagem. O que se escreve é só o que vem "
        "depois do ponto.\n"
        "- NÃO escreva nenhuma outra palavra na imagem além destas.\n"
        "- Tudo em português do Brasil. NENHUMA palavra em inglês na imagem, "
        "em lugar nenhum — nem em livro, tela, etiqueta, embalagem ou objeto "
        "do cenário. Texto de cenário que apareceria em inglês deve aparecer "
        "em português, ou não aparecer.\n"
        "- Nunca invente palavra "
        "para preencher espaço.\n"
        + MARCA_FIM_TEXTO_EXATO + "\n"
    )


_INICIO_DE_BLOCO = __import__("re").compile(r"^[0-9A-ZÀ-Ú][^:]{0,44}:")

MARCA_TEXTO_EXATO = "━━━ TEXTO EXATO A ESCREVER (copie letra por letra) ━━━"
# O BLOCO DIZ ONDE ELE ACABA.
#
# Sem esta marca, quem troca a copy tinha de adivinhar o fim do bloco, e
# adivinhou pela proxima "━━━" — que e a SECTION 2, doze mil caracteres
# adiante. Tudo que estava no meio (as seis regras da peca) ia junto.
MARCA_FIM_TEXTO_EXATO = "━━━ FIM DO TEXTO EXATO ━━━"


def _sincronizar_contagem(prompt, bloco_novo):
    """O prompt com a CONTAGEM de blocos alinhada ao texto que entrou.

    Trocar o texto sem trocar o numero e deixar duas vozes sobre a mesma
    coisa — o defeito que mais custou nesta base.

    DOIS FORMATOS, E O SEGUNDO QUASE PASSOU. A peca com copy diz "- Esta
    peca tem exatamente N bloco(s)", e basta trocar o N. A peca SEM copy diz
    "- Esta peca NAO recebeu copy (...) NAO escreva nenhuma palavra" — uma
    frase sem numero nenhum. Injetar copy nela e dizer que agora HA copy: a
    frase inteira sai e a contagem entra no lugar, com a mesma redacao do
    caminho normal.

    Medido no prompt real de 05/10: sem isto, a peca 5 recebeu as duas
    ordens, e o gerador escolheu.
    """
    _n = len([l for l in bloco_novo.splitlines()
              if _re_quadro.match(r"^\s+\d+\.\s", l)])
    if not _n:
        return prompt
    saida = _re_quadro.sub(
        r"(- Esta peça tem exatamente )\d+( bloco)",
        lambda _m: f"{_m.group(1)}{_n}{_m.group(2)}", prompt)
    if MARCA_SEM_COPY in saida:
        saida = "\n".join(
            (f"- Esta peça tem exatamente {_n} bloco(s) de texto, e são os "
             f"do bloco de TEXTO EXATO. Não acrescente nenhum outro.")
            if l.startswith(MARCA_SEM_COPY) else l
            for l in saida.split("\n"))
    return saida


def trocar_texto_exato(prompt, textos):
    """O prompt com o bloco de texto SUBSTITUÍDO — nunca somado.

    O QUE ISTO CONSERTA
    -------------------
    A revisão fazia `prompt_base + bloco_texto_exato(corrigido)`. Só que
    `prompt_base` JÁ trazia o bloco com o texto errado, escrito pela triagem.
    A peça refeita ia para o gerador com DOIS blocos "TEXTO EXATO A
    ESCREVER", cada um mandando escrever uma coisa, e os dois dizendo "acima
    de qualquer outra instrução de texto".

    Era por isso que refazer não consertava: em 24/09 a peça saiu três vezes
    com "Interior em inox atua isolante" e "400ml ideal para todas bebidas",
    e as três rodadas de revisão foram gastas mandando o gerador escolher
    entre duas ordens contrárias.
    """
    # O FIM DO BLOCO VEM DA MARCA DELE, E NÃO DE ADIVINHAÇÃO.
    #
    # O QUE ISTO CONSERTA — e é um estrago que esta função causava:
    #
    # A versão anterior procurava a próxima "━━━" depois do bloco de texto.
    # A próxima "━━━" é a SECTION 2 — doze mil caracteres adiante. Entre uma e
    # outra está TODA a Seção 1 depois da copy: a regra da borda, o bloco de
    # protagonismo, a regra de densidade, a de texto real, a de fidelidade e a
    # instrução de composição. Tudo isso era apagado.
    #
    # Medido no prompt real de 28/09 às 18:17: a peça 2 foi ao motor com 8.259
    # caracteres contra 24.000 das irmãs, sem nenhuma dessas regras. E como
    # `revisar_texto` chama esta troca SEMPRE que acha erro de português, toda
    # peça refeita pela revisão ia ao motor sem regra nenhuma — justamente a
    # peça que já tinha dado problema.
    #
    # Agora `bloco_texto_exato` fecha com `MARCA_FIM_TEXTO_EXATO`, e a troca
    # recorta exatamente entre as duas marcas. O bloco novo entra NO LUGAR do
    # antigo, e não no fim do prompt: ordem importa, e o texto tem de continuar
    # antes das regras que falam dele.
    base = str(prompt or "")
    i = base.find(MARCA_TEXTO_EXATO)
    novo = bloco_texto_exato(textos)
    if i < 0:
        # PROMPT SEM BLOCO DE TEXTO — e exatamente o caminho da peca que o
        # plano devolveu sem copy. Ele saia por aqui ANTES de qualquer
        # sincronia, e foi assim que a peca 5 da Caneca Termica Medieval foi
        # ao Gemini com "NAO escreva nenhuma palavra" e "escreva EXATAMENTE
        # estas palavras" na mesma mensagem (05/10, medido no prompt real).
        return _sincronizar_contagem(base + novo, novo)
    f = base.find(MARCA_FIM_TEXTO_EXATO, i)
    if f >= 0:
        fim = f + len(MARCA_FIM_TEXTO_EXATO)
    else:
        # PROMPT ANTIGO, sem a marca de fim: o bloco termina na última linha
        # que `bloco_texto_exato` escreve. Cortar até a próxima "━━━" é o que
        # levava as regras junto, e não se faz mais.
        _ultima = "para preencher espaço."
        _u = base.find(_ultima, i)
        fim = (_u + len(_ultima)) if _u >= 0 else i + len(MARCA_TEXTO_EXATO)
    trocado = (base[:i].rstrip("\n") + "\n" + novo.lstrip("\n")
               + "\n" + base[fim:].lstrip("\n")).rstrip() + "\n"

    # ── A CONTAGEM VAI JUNTO COM O BLOCO ────────────────────────────────
    #
    # ACHADO NO ARQUIVO DO DONO, 30/09, peça 2, e reproduzido linha a linha.
    #
    # O prompt da geração dizia "esta peça tem exatamente 3 bloco(s)" e
    # listava três. A revisão de texto devolveu a correção como UMA STRING
    # com os três colados — e esta função troca só o bloco TEXTO EXATO. A
    # linha da contagem ficou da geração.
    #
    # O que foi ao motor na refação:
    #
    #     - Esta peça tem exatamente 3 bloco(s) de texto.
    #     1. PROTEÇÃO contra poeira e impactos ORGANIZAÇÃO espaço organizado
    #        e seguro MADEIRA NATURAL durável e elegante
    #
    # Três blocos pedidos, um entregue — e uma frase corrida de 108
    # caracteres, sem pontuação, para ser partida em três cartões. O modelo
    # parte onde consegue: é daí que saem os cartões embaralhados e
    # sobrepostos que o dono chamou de "quadrados sobressaindo o outro".
    #
    # Trocar o texto sem trocar o número é deixar duas vozes sobre a mesma
    # coisa — o defeito que mais custou nesta base.
    return _sincronizar_contagem(trocado, novo)


def _campo_ambientacao(sufixo):
    """O campo onde quem vende diz em que ambiente o produto é usado.

    OPCIONAL, e a palavra importa. Quem vende sabe coisa que nenhuma análise da
    foto descobre: um marcador de taça é jantar, casamento, confraternização —
    olhando a peça de silicone colorido não se chega nisso.

    Três telas perguntam a mesma coisa (uma imagem, selecionar, as oito), e por
    isso a pergunta mora aqui: escrita em três lugares, as três passam a
    divergir — a questão é só quando.
    """
    return st.text_area(
        "Ambientação (opcional) — onde e como o produto é usado",
        height=68, key=f"img_ambientacao_{sufixo}",
        placeholder="ex: jantar entre amigos, mesa posta, taças de vinho, "
                    "festa de casamento, confraternização",
        help="É TEMA, não roteiro: o Studio varia a cena entre as imagens sem "
             "sair desse universo. A paleta e a luz continuam saindo do "
             "produto. Deixe em branco e o Studio deduz sozinho.")


def tipo_canonico(item, tipos_selecionados=None):
    """O rótulo OFICIAL da peça, a partir do item do plano de triagem.

    A IA que escreve o plano reescreve o nome do tipo: "2 — Benefícios do
    produto" vira "Imagem de marketing — benefícios", "8 — Ambientação
    realista (sem texto)" vira "Foto editorial — ambientação realista". O
    rótulo dela é bonito e é o que aparecia na galeria — e era com ele que o
    Studio ia procurar o preset, que é indexado pelo nome oficial.

    O `numero` do plano é o índice do tipo escolhido, e é ele que não muda
    quando a IA reescreve. Por isso a ordem é: número primeiro, rótulo
    depois, cru por último.
    """
    it = item if isinstance(item, dict) else {}
    lista = list(tipos_selecionados or TIPOS_PADRAO)
    try:
        n = int(it.get("numero"))
    except (TypeError, ValueError):
        n = None
    if n and 1 <= n <= len(lista):
        return lista[n - 1]
    rotulo = str(it.get("tipo", "") or "").strip()
    if rotulo in PRESETS:
        return rotulo
    alvo = _chave_tipo(rotulo)
    for chave in PRESETS:
        if alvo and _chave_tipo(chave) == alvo:
            return chave
    return rotulo


# ── A DIRECAO DE ARTE, DECIDIDA UMA VEZ E HERDADA PELAS OITO ───────────────
#
# O DEFEITO QUE ISTO FECHA
# ------------------------
# `PADRAO_VISUAL` dizia, nos OITO prompts: "NÃO existe cor de fundo
# obrigatória. Analise o produto ... e escolha a paleta, a iluminação, o
# cenário e os materiais". Oito pecas recebendo, cada uma, a ordem de decidir
# a estetica sozinha. O dono viu o resultado e chamou pelo nome: "6 direcoes
# de arte diferentes" no mesmo anuncio.
#
# Nao era desobediencia do gerador. Era o que o prompt pedia.
#
# A decisao agora acontece UMA vez, na triagem — que ja e uma chamada com as
# fotos, antes das oito, e por isso isto nao custa chamada nenhuma. As pecas
# HERDAM.
def bloco_direcao_de_arte(direcao):
    """O universo visual do produto, em texto, para entrar no brief.

    "" quando nao ha direcao — plano antigo, triagem que falhou, geracao
    avulsa. Nesses casos o `PADRAO_VISUAL` de sempre continua valendo: sem
    direcao herdada, mandar a peca decidir e o comportamento menos ruim.
    """
    d = direcao if isinstance(direcao, dict) else {}
    if not d:
        return ""
    # A DIREÇÃO DE ARTE TAMBÉM NÃO MANDA TAMANHO.
    #
    # Ela é prosa livre escrita pela mesma IA que escreve a cena — e a cena
    # veio com "produto centralizado ocupando 60% do espaço vertical" numa
    # peça cuja regra mandava 85% a 92%. Nada impedia a atmosfera, a luz ou o
    # posicionamento de fazerem igual.
    #
    # Limpar só a cena teria sido a Forma 1 de novo: a correção no lugar onde
    # o sintoma apareceu, e não em todos onde a regra alcança. O tamanho tem
    # um dono, e é `ocupacao_em_portugues`.
    d = {k: (sem_medida_de_quadro(v) if isinstance(v, str) else v)
         for k, v in d.items()}
    _p = d.get("paleta") if isinstance(d.get("paleta"), dict) else {}

    def _cor(chave, rotulo, onde):
        c = _p.get(chave) if isinstance(_p.get(chave), dict) else {}
        nome = str(c.get("nome", "") or "").strip()
        hexa = str(c.get("hex", "") or "").strip()
        if not nome and not hexa:
            return ""
        medida = f"{nome} ({hexa})" if nome and hexa else (nome or hexa)
        return f"- {rotulo}: {medida} — {onde}\n"

    def _lista(chave):
        v = d.get(chave)
        return ", ".join(str(x).strip() for x in v if str(x).strip()) if isinstance(v, list) else ""

    linhas = ["\nDIREÇÃO DE ARTE DESTE PRODUTO — JÁ DECIDIDA, NÃO SE DECIDE DE NOVO:"]
    if d.get("nome"):
        linhas.append(f"Direção: {d['nome']}")
    if d.get("posicionamento"):
        linhas.append(f"Posicionamento: {d['posicionamento']}")
    if d.get("atmosfera"):
        linhas.append(f"Atmosfera: {d['atmosfera']}")

    paleta = ("".join([
        _cor("fundo",  "FUNDO",  "fundo e superfícies do ambiente"),
        _cor("painel", "PAINEL", "cartões, faixas e áreas secundárias"),
        _cor("titulo", "TÍTULO", "tipografia principal"),
        _cor("apoio",  "APOIO",  "texto secundário, linhas e ícones"),
        _cor("acento", "ACENTO", "ênfase pontual, selo, detalhe — com parcimônia"),
    ]))
    if paleta:
        linhas.append("\nPALETA-MÃE (o hex é âncora visual, não ordem de pintar o produto):")
        linhas.append(paleta.rstrip("\n"))

    if _lista("materiais"):
        linhas.append(f"\nMateriais do cenário: {_lista('materiais')}")
    if d.get("luz"):
        linhas.append(f"Luz: {d['luz']}")
    if d.get("saturacao"):
        linhas.append(f"Saturação: {d['saturacao']}")
    if _lista("props_preferidos"):
        linhas.append(f"Props permitidos: {_lista('props_preferidos')}")
    if _lista("props_proibidos"):
        linhas.append(f"Props PROIBIDOS: {_lista('props_proibidos')}")
    if str(d.get("risco_de_reflexo", "")).strip().upper() in ("MEDIO", "MÉDIO", "ALTO"):
        linhas.append(
            "Risco de reflexo " + str(d["risco_de_reflexo"]).strip().upper() +
            ": nada de superfície grande e saturada perto do produto — o "
            "reflexo do ambiente muda a cor percebida dele.")
    _trava_limpa, _ = limpar_trava_do_produto(d.get("trava_do_produto"))
    if _trava_limpa:
        linhas.append(f"\nTRAVA DO PRODUTO (material, acabamento e geometria — "
                      f"a COR tem trava própria, acima): {_trava_limpa}")

    linhas.append(
        "\nCOMO ESTA DIREÇÃO SE APLICA:\n"
        "- Ela vale para fundo, superfície, cenário, props, painel, tipografia,\n"
        "  ícone e elemento gráfico. NÃO vale para o produto.\n"
        "- O AMBIENTE SE ADAPTA AO PRODUTO, NUNCA O CONTRÁRIO. As fotos do\n"
        "  produto têm prioridade maior que a paleta, a luz e o cenário: se\n"
        "  qualquer instrução conflitar com o que está na foto, IGNORE a\n"
        "  instrução e preserve o produto.\n"
        "- Esta peça é UMA das oito do mesmo catálogo. Ela não escolhe paleta\n"
        "  nova, material novo nem outra família de luz.\n"
        "- Consistência NÃO é repetir o cenário. A cena desta peça é a que\n"
        "  está escrita no plano, e ela é diferente das outras sete de\n"
        "  propósito: mesma campanha, cenas diferentes.\n"
        "- Cor incidental do mundo real pode aparecer onde for fisicamente\n"
        "  inevitável; cor dominante fora da paleta, não.")
    return "\n".join(linhas) + "\n"


def _chave_tipo(tipo):
    """O rótulo do tipo sem o número, sem acento e sem caixa.

    "1 — Capa do anúncio (fundo branco)" e "Capa do anúncio (fundo branco)"
    viram a mesma coisa. Comparação exata depois disso — nunca por pedaço:
    "Capa" casaria com qualquer rótulo que tivesse "capa" dentro, e casar por
    pedaço de palavra já trocou produto por produto nesta base.
    """
    import unicodedata as _u
    t = str(tipo or "").strip()
    # tira "N — ", "N - ", "N. " e o que mais venha antes do nome
    i = 0
    while i < len(t) and (t[i].isdigit() or t[i] in " -—–.:"):
        i += 1
    t = t[i:] if i < len(t) else t
    t = _u.normalize("NFKD", t)
    return "".join(c for c in t if not _u.combining(c)).lower().strip()


def numero_do_tipo(tipo):
    """O número que abre o rótulo do tipo. None quando não há.

    "1 — Capa do anúncio (fundo branco)" -> 1
    "Capa do anúncio (fundo branco)"     -> None
    """
    t = str(tipo or "").strip()
    n = ""
    for c in t:
        if c.isdigit():
            n += c
        else:
            break
    return int(n) if n else None


def preset_do_tipo(tipo):
    """As regras daquele tipo de imagem. "" quando o tipo não é um dos padrão.

    POR QUE NÃO É `PRESETS.get(tipo)` DIRETO — E O QUE ISSO CUSTOU
    ---------------------------------------------------------------
    As chaves dos presets são "1 — Capa do anúncio (fundo branco)". O tipo
    que chega na geração vem do PLANO DE TRIAGEM, escrito pela IA
    (`imagem.py`, `tipos_viaveis`), e ela escreve "Capa do anúncio (fundo
    branco)" — SEM o número. `PRESETS.get` devolvia "" e a peça era gerada
    sem as regras do tipo. Nos oito, nenhum casava.

    O prompt real de 24/09 provou: a SEÇÃO 1 levava só o plano da triagem, e
    o "produto ocupa 90-95% do frame" da capa, o "ZERO TEXTO", a escala real
    da ambientação e o enquadramento do close simplesmente não iam. Sobrava o
    genérico "at least 70%" — que é o produto pequeno que o dono via.

    Então a busca passa a ser pelo NÚMERO, que é o que não muda quando a IA
    reescreve o rótulo. Nome exato primeiro (o caminho de sempre), número
    depois, e nada de casar por pedaço de palavra: "Capa" casaria com
    qualquer coisa que tivesse "capa" dentro.
    """
    t = str(tipo or "").strip()
    if t in PRESETS:
        return PRESETS[t]
    n = numero_do_tipo(t)
    if n is None:
        # Sem número na frente: casa pelo RESTO do rótulo, ignorando o
        # prefixo numérico das chaves. É o caso do plano da triagem.
        alvo = _chave_tipo(t)
        for chave, texto in PRESETS.items():
            if alvo and _chave_tipo(chave) == alvo:
                return texto
        return ""
    for chave, texto in PRESETS.items():
        if numero_do_tipo(chave) == n:
            return texto
    return ""


def montar_prompt_imagem(tipo, instrucoes_extras, dados_descricao, nome_produto,
                         refs_layout_nomes=None, instrucao_layout="",
                         plano_triagem=None, ambientacao="", direcao_arte=None):
    """Monta o prompt completo para geração.

    Para os tipos padrão (1-7): aplica PADRAO_VISUAL + INSTRUCAO_COMPOSICAO
    (imagens de marketing com identidade visual).

    Para 'Personalizado': aplica INSTRUCAO_PERSONALIZADO sem branding automático
    — a instrução do colaborador é a única fonte de verdade.

    refs_layout_nomes: lista de nomes de arquivo das imagens de referência de layout
    instrucao_layout: texto descrevendo o que cada referência representa
    """
    base = preset_do_tipo(tipo)

    # ── Bloco do plano da triagem (composição e textos decididos pela IA antes da geração) ──
    bloco_plano_triagem = ""
    _blocos_da_copy = 0
    if plano_triagem and not (tipo == "Personalizado (descrevo o que quero)"):
        _composicao = sem_medida_de_quadro(plano_triagem.get("composicao", ""))
        plano_triagem_item_cena = plano_triagem.get("cena", "")
        _textos = [t for t in plano_triagem.get("textos", []) if t and str(t).strip()]
        # BLOCO REPETIDO SAI ANTES DO TETO, E A ORDEM IMPORTA.
        #
        # A peca 4 do dono recebeu "MADEIRA TRABALHADA: / Acabamento e
        # textura" DUAS vezes. Cortar primeiro pelo teto e depois deduplicar
        # entregaria dois cartoes onde cabiam tres — a repeticao gastaria uma
        # vaga e o terceiro bloco sairia espremido ou cortado.
        _textos, _repetidos = blocos_sem_repeticao(_textos)
        # O TETO DA PECA CORTA A COPY AQUI, E NAO NO GERADOR.
        #
        # A triagem nao sabe quantos blocos o tipo comporta: ela escrevia 4
        # frases para um Close de 2 callouts, o bloco de texto exato mandava
        # escrever as 4 "letra por letra" e a regra de densidade dizia 2. Tres
        # ordens sobre a mesma coisa. Cortar aqui e a unica forma de as duas
        # que sobram concordarem.
        # A BARREIRA DE CLAIM FICA ANTES DO TETO, e a ordem importa: cortar
        # pelo teto primeiro poderia manter a promessa sem lastro e jogar
        # fora um bloco bom que vinha depois dela.
        #
        # ACHADO EM PRODUCAO, 05/10. A peca 6 foi ao Gemini com "MANTEM
        # BEBIDA QUENTE? Sim, termica em metal e resina" — e o cadastro do
        # produto nao tem ensaio termico nenhum. A IA viu inox e concluiu.
        # Gastar uma geracao desenhando perfeitamente um texto que ja nasceu
        # errado e o desperdicio mais caro desta cadeia: a arte sai boa, o
        # conferidor aprova, e o claim falso vai para a pagina do produto.
        _textos, _sem_lastro = copy_sem_promessa(_textos, dados_descricao)
        _textos, _sem_medida = copy_sem_medida_inventada(_textos, dados_descricao)
        _teto_do_tipo = faixa_de_blocos(tipo)[1]
        if _teto_do_tipo:
            _textos = _textos[:_teto_do_tipo]
        _blocos_da_copy = len(_textos)
        if _composicao or _textos:
            bloco_plano_triagem = "\nPLANO DE CRIAÇÃO (definido pela análise do produto — siga este planejamento):\n"
            if _composicao:
                bloco_plano_triagem += f"Composição: {_composicao}\n"
            # A CENA DESTA PECA, QUE E DIFERENTE DAS OUTRAS SETE DE PROPOSITO.
            #
            # Sem isto, "consistencia" virava "mesmo cenario": escrivaninha
            # com caneta na 3, na 7 e na 8. A triagem planeja as oito de uma
            # vez e por isso consegue variar superficie, props e angulo sem
            # sair do universo.
            _cena = sem_medida_de_quadro(plano_triagem_item_cena)
            if _cena:
                bloco_plano_triagem += f"Cena desta peça: {_cena}\n"
            if _textos:
                # "Textos a incluir" era uma SUGESTAO, e o gerador a tratava
                # como tal: reescrevia a frase com as proprias palavras e
                # errava as letras no caminho. A copy ja vem pronta da triagem;
                # aqui ela deixa de ser sugestao e vira o texto literal.
                bloco_plano_triagem += bloco_texto_exato(_textos)

    # ── O TEMA DA AMBIENTAÇÃO, quando o colaborador escreveu um ───────────
    #
    # Campo OPCIONAL, e a palavra importa: quem vende sabe onde o produto é
    # usado melhor do que qualquer dedução a partir da foto. Um marcador de
    # taça é "jantar, casamento, confraternização" — nenhuma análise de imagem
    # chega nisso olhando uma peça de silicone colorido.
    #
    # É TEMA, NÃO ROTEIRO. O dono foi explícito: "ele não deve manter o mesmo
    # padrão de ambientação em todas as fotos, o ideal é ir mudando sem fugir
    # do tema". Então o texto dele delimita o universo, e cada uma das oito
    # imagens escolhe uma cena diferente dentro dele.
    bloco_ambientacao = ""
    _amb = str(ambientacao or "").strip()
    if _amb:
        bloco_ambientacao = (
            "\nAMBIENTAÇÃO PEDIDA POR QUEM VENDE O PRODUTO (é TEMA, não roteiro):\n"
            f"{_amb}\n"
            "- Use isto para entender o universo de uso: lugar, ocasião, quem usa.\n"
            "- NÃO repita a mesma cena nas outras imagens do conjunto. Varie o\n"
            "  ângulo, o momento, os props e o recorte DENTRO desse tema.\n"
            "- O tema orienta o cenário; a direção de arte (paleta, luz,\n"
            "  materiais) continua saindo do produto.\n")

    contexto_produto = f"PRODUTO: {nome_produto}\n"
    # ── O TIPO 5 SEM CADASTRO: A PEÇA QUE PEDIA O QUE ELA MESMA PROIBIA ──
    #
    # Dono, 30/09: "informações recortadas".
    #
    # O tipo 5 manda "INFOGRÁFICO TÉCNICO DE MEDIDAS — estilo cota de
    # catálogo". E o mesmo prompt traz "JAMAIS crie, estime ou invente
    # medidas (...) se esses dados não foram fornecidos nos campos do
    # produto, NÃO os coloque na imagem sob nenhuma hipótese".
    #
    # Com o cadastro preenchido as duas convivem. Com o cadastro VAZIO elas
    # se anulam: infográfico de cotas sem poder escrever cota nenhuma — e o
    # prompt não dizia em lugar nenhum que a medida não existe. O modelo
    # resolve contradição inventando, e a peça sai com número errado.
    #
    # As 61 regras nunca mediram este caso: o cadastro do teste sempre teve
    # medida. É o mesmo ponto cego do termômetro — amostra de um caso só.
    _dd = dados_descricao or {}
    if (str(tipo).startswith("5 —")
            and not any(str(_dd.get(_c, "")).strip()
                        for _c in ("medidas", "peso", "material"))):
        contexto_produto += (
            "SEM DADOS TÉCNICOS CADASTRADOS: este produto não tem medidas, "
            "peso nem material informados. Faça a peça técnica SEM nenhuma "
            "cota, seta de dimensão, número ou unidade — destaque o produto "
            "e os detalhes construtivos que a FOTO mostra. NÃO estime e NÃO "
            "invente nenhum número: peça sem cota é correta, peça com cota "
            "inventada é peça errada.\n")
    # A trava entra SEMPRE — com a cor nomeada quando a triagem tem o campo,
    # e na versão genérica quando não tem. Condicioná-la ao campo preenchido
    # era o que deixava o produto livre para ser repintado de azul da marca.
    contexto_produto += _trava_cor_produto(
        (dados_descricao or {}).get("cor", "")
    )
    if dados_descricao:
        if dados_descricao.get("medidas"):
            contexto_produto += f"Medidas EXATAS (use esses números, não invente): {dados_descricao['medidas']}\n"
        if dados_descricao.get("peso"):
            contexto_produto += f"Peso EXATO (use esse número, não invente): {dados_descricao['peso']}\n"
        # O MATERIAL NUNCA CHEGAVA — NEM AQUI, NEM NA TRIAGEM.
        #
        # O cadastro tem o campo "Material" e ele nao era escrito em lugar
        # nenhum: nem no brief, nem no contexto que a analise le. O album do
        # dono e Wire-O, e a palavra aparecia em 0 dos 8 prompts — justo com a
        # peca 4 sendo o CLOSE da encadernacao. Ela ia ampliar uma montagem
        # que o texto nunca descreveu, e o gerador desenhava a que achasse.
        # O CORTE PRECISA DE TEXTO, E A PLANILHA NEM SEMPRE MANDA TEXTO.
        #
        # `[:200]` num inteiro levanta TypeError, e a tela cai inteira. Uma
        # celula de gramatura digitada como "300" volta do gspread como int —
        # e o campo Material com "300" e realista. O mesmo valia para
        # diferenciais, caracteristicas e uso, que ja faziam o corte direto
        # antes desta linha existir: o defeito e antigo, so nunca tinha
        # encostado num campo que fosse numero.
        def _texto_do_campo(chave, limite):
            valor = dados_descricao.get(chave)
            if valor is None:
                return ""
            return str(valor).strip()[:limite]

        if _texto_do_campo("material", 200):
            contexto_produto += (
                f"Material e montagem (use exatamente isto, não deduza): "
                f"{_texto_do_campo('material', 200)}\n")
        # DUZENTOS CARACTERES CORTAVAM ESPECIFICACAO DE VERDADE.
        #
        # "60 folhas, encadernacao Wire-O preta, papel 300g, cantos
        # arredondados, capa dura revestida" ja passa disso. O corte existe
        # para o campo nao virar um texto inteiro no prompt; quatrocentos
        # cabem a especificacao e continuam sendo teto.
        if _texto_do_campo("diferenciais", 400):
            contexto_produto += f"Diferenciais principais: {_texto_do_campo('diferenciais', 400)}\n"
        if _texto_do_campo("caracteristicas", 400):
            contexto_produto += f"Características: {_texto_do_campo('caracteristicas', 400)}\n"
        if _texto_do_campo("uso", 100):
            contexto_produto += f"Uso principal: {_texto_do_campo('uso', 100)}\n"

    # IMPORTANTE: instrucoes_extras é CONTEXTO INTERNO para a IA, não conteúdo visual.
    # Para tipos padrão (1-8), é marcado como contexto — nunca renderizado na imagem.
    # Para Personalizado, é marcado como instrução visual.
    bloco_contexto_interno = (
        f"\nCONTEXTO INTERNO DO PRODUTO (informação de apoio para a IA — NÃO renderize estes dados como texto na imagem):\n{instrucoes_extras}"
        if instrucoes_extras else ""
    )
    bloco_instrucao_visual = (
        f"\nINSTRUÇÕES VISUAIS DO COLABORADOR (aparecem na imagem conforme descrito):\n{instrucoes_extras}"
        if instrucoes_extras else ""
    )

    # Bloco de referências de layout
    bloco_refs = ""
    if refs_layout_nomes:
        # O NOME DO ARQUIVO NAO VAI AO MODELO. ELE E PORTA DE ENTRADA.
        #
        # A referencia subida numa analise se chamava `ref_cinzeiro_casal.png`,
        # e "cinzeiro" e "casal" entraram nos oito prompts: um nome de objeto
        # e uma palavra de pessoa — exatamente o que
        # `limpar_descricao_de_layout` existe para remover da descricao.
        #
        # O filtro limpava a descricao e deixava o nome passar ao lado dela.
        # Higienizar o nome seria caçar as mesmas palavras num segundo lugar;
        # o conserto barato e ele nao ir. O modelo ja sabe qual imagem e a
        # referencia pela ORDEM — ela vai sempre por ultimo, e o prompt diz
        # isso com todas as letras. O nome do arquivo nao acrescenta nada a
        # ele; serve so aqui dentro, para `ref_layout_do_tipo` casar a
        # referencia com a peca.
        bloco_refs = (f"\nREFERÊNCIAS DE LAYOUT FORNECIDAS: "
                      f"{len(refs_layout_nomes)} imagem(ns)")
        if instrucao_layout:
            bloco_refs += f"\nO que cada referência representa: {instrucao_layout}"
        bloco_refs += "\n" + INSTRUCAO_REFERENCIA_LAYOUT.format(
            autoridade=AUTORIDADE_DA_REFERENCIA)

    # A MEDIDA DA OCUPACAO SAI DE `OCUPACAO`, E DE MAIS LUGAR NENHUM.
    # O mesmo numero alimenta esta linha e a linha de COMPOSITION do prompt
    # final em ingles — foi a divergencia entre as duas que mandava tres
    # numeros contrarios ao modelo na mesma mensagem.
    _protagonismo = protagonismo_do_tipo(tipo)
    _layout_marketing = instrucao_de_layout(
        tipo,
        blocos=blocos_em_portugues(tipo, _blocos_da_copy),
        palavras=medida_do_bloco(),
    )
    # A direcao de arte vem decidida da triagem e e HERDADA por esta peca. Sem
    # ela — plano antigo, triagem que falhou, geracao avulsa — o bloco sai
    # vazio e o padrao visual volta a mandar a peca deduzir, que e o
    # comportamento de antes e o menos ruim dos dois.
    _bloco_direcao = bloco_direcao_de_arte(direcao_arte)
    _padrao_visual = padrao_visual(direcao_arte)
    # Margem e sobreposicao saem do MESMO lugar, e variam por tipo.
    _espaco_pt, _ = regra_de_espaco(tipo)
    # A GEOMETRIA ENTRA JUNTO DA REGRA DE ESPACO, e nao solta: as duas falam
    # da mesma coisa — onde cada parte da peca mora — e separa-las seria
    # criar a quinta voz sobre a borda, que e o defeito que esta base ja
    # pagou cinco vezes.
    _zonas = zonas_da_peca(tipo, _blocos_da_copy)
    if _zonas:
        _espaco_pt = _espaco_pt.rstrip("\n") + "\n" + _zonas

    _modo = modo_fundo_do_tipo(tipo)
    eh_personalizado = _modo == "personalizado"
    eh_fundo_branco  = _modo == "branco"
    eh_ambientacao   = _modo == "ambiente"

    if eh_personalizado:
        # Modo personalizado: SEM branding automático, SEM nova composição forçada
        # A instrução do colaborador define tudo — e é conteúdo visual, não contexto interno.
        return f"""MS_FUNDO: personalizado
{contexto_produto}
TIPO DE IMAGEM: Personalizado
{bloco_instrucao_visual}
{bloco_refs}
{_bloco_direcao}
{_espaco_pt}

{INSTRUCAO_PERSONALIZADO}
{INSTRUCAO_FIDELIDADE}
{INSTRUCAO_PROPORCAO}
"""
    elif eh_fundo_branco:
        # Tipo 1 (Capa): fundo BRANCO PURO — o PADRAO_VISUAL (azul-cinza) não se aplica aqui
        PADRAO_VISUAL_FUNDO_BRANCO = """
PADRÃO VISUAL PARA FOTO DE PRODUTO — REGRA ABSOLUTA:
- Fundo: BRANCO PURO (#FFFFFF) — sem gradiente, sem textura, sem cor de fundo
- Iluminação de estúdio profissional: luz suave, sem sombras duras
- PROIBIÇÃO TOTAL DE TEXTO: NENHUM texto, título, headline, legenda, ícone, selo, tag,
  logotipo ou qualquer elemento gráfico além do produto em si. ZERO elementos escritos.
- Visual limpo, minimalista, focado 100% no produto — apenas produto sobre branco puro
"""
        return f"""MS_FUNDO: branco
{contexto_produto}
TIPO DE IMAGEM: {tipo}
{base}
{bloco_plano_triagem}
{bloco_contexto_interno}{bloco_ambientacao}
{bloco_refs}
{_bloco_direcao}
{_espaco_pt}

{PADRAO_VISUAL_FUNDO_BRANCO}
{_protagonismo}
{INSTRUCAO_FIDELIDADE}
{INSTRUCAO_PROPORCAO}
{INSTRUCAO_COMPOSICAO}
"""
    elif eh_ambientacao:
        # Tipo 8: ambientação realista — SEM texto (exceto "Imagem meramente ilustrativa")
        # ── AMBIENTAÇÃO: a cena é deduzida do produto, não escolhida de uma lista
        #
        # O que estava aqui: "escritório, quarto de estudos, sala de estar, mesa
        # de trabalho" + "tons neutros" + "iluminação natural suave". Três
        # problemas de uma vez:
        #
        #   a lista de ambientes é semanticamente errada para metade dos
        #   produtos — um marcador de taça não pertence a estante de livros;
        #
        #   "tons neutros" e "luz natural suave" achatam todo produto na mesma
        #   cena clara e bege, e proíbem a cena escura da caixa de relógios que
        #   o dono mostrou como referência;
        #
        #   "ZERO TEXTO" seguido de "escreva Imagem meramente ilustrativa" é
        #   uma contradição, e contradição em prompt é brecha: o modelo resolve
        #   escrevendo mais coisa.
        PADRAO_VISUAL_AMBIENTACAO = """
DIREÇÃO DE ARTE ADAPTATIVA — A CENA É DEDUZIDA DESTE PRODUTO:
- Analise primeiro as fotos e os dados. ANTES de compor, decida qual contexto,
  atmosfera, paleta e iluminação valorizam ESTE produto.
- NÃO existe ambiente, paleta, material ou luz padrão. Nada de lista fixa de
  cômodos: deduza o lugar onde este produto é de fato usado, e por quem.
- Raciocínio de exemplo, para NÃO copiar literalmente: produto claro e
  delicado, ligado a casamento ou presente, pede madeira clara, tecidos
  suaves, flores discretas e luz difusa; acessório preto e premium pede
  madeira escura, pedra, couro, metal quente e luz dramática; produto pequeno
  e colorido pede fundo claro e pequenos elementos nas cores dele.
- Escolha props com relação direta ao uso, ao comprador ou à ocasião. Nada de
  objeto decorativo genérico só para preencher espaço.
- A cena tem de parecer feita para ESTE produto. Produtos diferentes devem
  resultar em cenários claramente diferentes.
- Integre o produto fotograficamente: sombra de contato, perspectiva coerente,
  profundidade real. O resultado é fotografia comercial — não produto
  recortado sobre um fundo.
- A luz do cenário pode mudar; a cor percebida do produto, não.

REGRA DE TEXTO — EXCEÇÃO ÚNICA E EXPLÍCITA:
- Não gere título, headline, benefício, legenda, selo, marca, logotipo, ícone
  com texto, número ou palavra decorativa.
- A ÚNICA sequência de caracteres permitida na imagem inteira é:
  "Imagem meramente ilustrativa"
- Renderize essa frase UMA vez, discreta, no rodapé, pequena e legível. Ela não
  vira selo, headline nem elemento promocional.
- Os objetos do cenário não podem ter texto legível: livro, embalagem, tela,
  etiqueta e demais props aparecem sem inscrição.
- Nenhuma outra letra ou número em qualquer parte da imagem.

- Sem pessoas nem figuras humanas nesta imagem.
"""

        return f"""MS_FUNDO: ambiente
{contexto_produto}
TIPO DE IMAGEM: {tipo}
{base}
{bloco_plano_triagem}
{bloco_contexto_interno}{bloco_ambientacao}
{bloco_refs}
{_bloco_direcao}
{_espaco_pt}

{PADRAO_VISUAL_AMBIENTACAO}
{_protagonismo}
{INSTRUCAO_FIDELIDADE}
{INSTRUCAO_PROPORCAO}
{INSTRUCAO_COMPOSICAO}
"""
    else:
        # Tipos padrão (2-7): imagens de marketing com identidade visual completa
        # instrucoes_extras é CONTEXTO INTERNO — não conteúdo visual renderizado
        return f"""MS_FUNDO: padrao
{contexto_produto}
TIPO DE IMAGEM: {tipo}
{base}
{bloco_plano_triagem}
{bloco_contexto_interno}{bloco_ambientacao}
{bloco_refs}
{_bloco_direcao}
{_espaco_pt}

{_padrao_visual}
{_protagonismo}
{_layout_marketing}
{INSTRUCAO_FIDELIDADE}
{INSTRUCAO_PROPORCAO}
{INSTRUCAO_COMPOSICAO}
"""


def cor_do_produto_atual():
    """A cor que a triagem apurou para o produto aberto. "" quando não há.

    Existe para que a trava de cor valha nos DOIS prompts — o de geração e o
    de ajuste — sem que cada um dos quatro lugares que ajustam imagem tenha de
    lembrar de buscá-la. Foi a falta disso que deixou a trava só na geração.
    """
    try:
        return str((st.session_state.get("img_dados_descricao") or {})
                   .get("cor", "") or "").strip()
    except Exception:
        return ""


def plano_do_tipo(tipo):
    """O plano que a triagem fez para este tipo de imagem. None quando não há.

    Ele carrega a composição decidida e — mais importante — a COPY FINAL,
    palavra por palavra, que `bloco_texto_exato` manda desenhar. É a correção
    que acabou com "Portátile" e "apoliando" nas peças.

    Existe como função porque o laço principal de geração a montava inline, e
    os dois caminhos de regerar UMA imagem não a montavam de jeito nenhum: a
    peça refeita saía sem a composição planejada e sem a copy pronta, e o
    gerador voltava a redigir a frase sozinho. Uma regra num lugar só.
    """
    try:
        itens = plano_da_geracao().get("plano") or []
    except Exception:
        return None
    # A BUSCA E PELO TIPO CANONICO, E NAO PELO ROTULO CRU.
    #
    # `it["tipo"]` e o nome que a IA do plano inventou — "Imagem de marketing
    # — beneficios". O `tipo` que chega aqui ja passou por `tipo_canonico` e e
    # "2 — Beneficios do produto". Comparar os dois crus nunca casava, e o
    # plano inteiro — composicao, CENA e a COPY EXATA — sumia do prompt. O
    # gerador voltava a redigir a frase sozinho, que e de onde vieram
    # "Portatile" e "apoliando".
    alvo = tipo_canonico({"tipo": tipo, "numero": numero_do_tipo(tipo)})
    for it in itens:
        if str(it.get("tipo", "")).strip() == str(tipo or "").strip():
            return it
    for it in itens:
        if tipo_canonico(it) == alvo:
            return it
    return None


def prompt_que_sera_enviado(prompt_texto, imagens_referencia, refs_layout=None,
                            refs_layout_nomes=None, tipo=""):
    """O texto EXATO que iria ao motor, sem chamar motor nenhum. ("" em erro.)

    Existe para o plano de criacao poder mostrar o prompt antes de o dono
    confirmar. O pedido dele foi direto: *"economiza dinheiro, fazendo testes
    gerando imagens com prompt ainda errado"*.

    Ele passa pelo MESMO caminho da geracao — `gerar_imagem_ia` com
    `so_montar` — e nao por uma segunda montagem. Montar o prompt em dois
    lugares e garantir que um dia os dois discordem, e ai o que a tela mostra
    deixa de ser o que o motor recebe. Foi exatamente o que aconteceu com a
    varredura desta base.

    Custo: a leitura de visao do produto, que e CACHEADA por produto e que a
    geracao pagaria de qualquer jeito. Nenhuma imagem e gerada.
    """
    diag = {}
    try:
        gerar_imagem_ia(prompt_texto, imagens_referencia,
                        refs_layout=refs_layout,
                        refs_layout_nomes=refs_layout_nomes,
                        tipo=tipo, diagnostico=diag, so_montar=True)
    except Exception as e:
        return f"(não consegui montar o prompt: {type(e).__name__}: {e})"
    return diag.get("prompt", "") or "(o prompt saiu vazio — isso é defeito)"


# ── O PLANO E ESCRITO POR IA, E POR ISSO NAO SE CONFERE UMA VEZ SO ─────────
#
# A analise de 24/09 voltou limpa de seis defeitos que a rodada anterior tinha:
# a peca 3 pedindo "maos do casal" numa peca que proibe pessoas, sete das sete
# pecas falando em "costura" num album Wire-O, "ouro" como material do produto,
# a palavra inventada "sobas", e madeira em quatro das sete cenas.
#
# Eles nao foram CORRIGIDOS. Eles NAO APARECERAM naquela rodada.
#
# A diferenca e tudo. O prompt e montado por codigo: conferir uma vez basta,
# porque ele nao muda sozinho. O plano e escrito por um modelo a cada analise,
# e pode voltar diferente amanha — com os mesmos defeitos ou com outros.
#
# Entao a conferencia dele tem de rodar SEMPRE, na tela, antes de gastar. Duas
# destas sao verificaveis sem ambiguidade; as outras quatro dependem do
# produto e ficam para o olho humano.
# A MESMA lista do filtro de layout — ver `PESSOAS`, la em cima. Eram duas, e
# discordavam: esta nao tinha "person", "people", "character" nem "hand",
# entao um plano escrito em ingles passava pelo aviso da tela.
_PESSOAS_NA_CENA = PESSOAS


# Os angulos que uma peca pode mostrar, e as palavras com que o plano os
# escreve. Sao SINONIMOS agrupados: "de frente" e "frontal" sao o mesmo
# angulo, e contar os dois como distintos deixaria passar a repeticao.
ANGULOS = {
    "frontal": ("frontal", "de frente", "frente do produto", "vista frontal"),
    "tres quartos": ("tres quartos", "três quartos", "3/4", "tres-quartos",
                     "três-quartos", "diagonal"),
    "lateral": ("lateral", "de lado", "perfil", "vista lateral"),
    "traseiro": ("traseir", "de costas", "verso", "parte de tras",
                 "parte de trás", "fundo do produto"),
    "superior": ("superior", "de cima", "vista de cima", "topo", "aereo",
                 "aéreo", "flat lay"),
    "macro": ("macro", "close", "aproximad"),
}


def blocos_sem_repeticao(textos):
    """(copy sem blocos repetidos, os que sairam). Funcao pura.

    POR QUE ESTA FUNCAO EXISTE
    --------------------------
    Dono, 30/09: *"as escritas estao sendo cortadas (...) aplicadas numa
    regiao que nao da para ser escrita totalmente"*. O item ficou aberto
    porque eu dizia precisar do prompt real para separar "o layout nao cabe"
    de "o modelo desobedeceu". O arquivo dele tinha o prompt real, e a peca 4
    respondeu sozinha:

        1. MADEIRA TRABALHADA: / Acabamento e textura
        2. MADEIRA TRABALHADA: / Acabamento e textura
        3. MONTAGEM: / Construcao precisa

    Os blocos 1 e 2 sao IDENTICOS. A IA do plano escreveu o mesmo callout
    duas vezes e o Studio mandou os dois ao gerador sem notar. Nao foi o
    modelo que desobedeceu: foi a nossa copy que pediu dois cartoes iguais —
    e o teto da peca gastou uma vaga com a repeticao, espremendo o terceiro.

    E ESTA BASE JA FAZIA ISSO PARA OS IRMAOS. `faces_repetidas` confere se
    duas pecas mostram a mesma face; `cenas_repetidas`, se duas repetem a
    cena. Ninguem conferia o bloco de texto repetido DENTRO da peca — a
    Forma 1 outra vez, a mesma capacidade faltando num irmao.

    A COMPARACAO IGNORA SO RUIDO: caixa, acento, espaco e dois-pontos
    sobrando. "MONTAGEM: construcao precisa" e "Montagem: Construcao
    Precisa" sao o mesmo cartao. O que difere em PALAVRA fica.
    """
    import re as _re_rep
    import unicodedata as _uni_rep

    def _chave(t):
        v = str(t or "").strip().upper()
        v = "".join(c for c in _uni_rep.normalize("NFD", v)
                    if _uni_rep.category(c) != "Mn")
        return _re_rep.sub(r"[\s:/]+", " ", v).strip()

    vistos, fica, sai = set(), [], []
    for t in (textos or []):
        k = _chave(t)
        if not k:
            continue
        if k in vistos:
            sai.append(t)
            continue
        vistos.add(k)
        fica.append(t)
    return fica, sai


def faces_repetidas(itens, tipos_selecionados=None):
    """Pares de pecas que mostram o produto no MESMO angulo. [] se nenhum.

    POR QUE ISTO EXISTE
    -------------------
    Ditado pelo dono em 28/09: *"o produto as vezes tem dois lados com
    desenhos diferentes; o estudio precisa variar, nao colocar sempre o mesmo
    lado. Nao sempre de frente, as vezes de lado, mostrar a parte de tras
    tambem, caso tenha"*.

    Oito pecas com o produto na mesma pose vendem uma face so — e um produto
    com gravacao no verso fica com metade do argumento de venda sem aparecer.

    A peca 4 (close) fica de fora: o angulo dela E o macro, por definicao, e
    apontar isso como repeticao seria ruido em toda analise.
    """
    por_peca = []
    for it in itens or []:
        if not isinstance(it, dict):
            continue
        oficial = tipo_canonico(it, tipos_selecionados)
        if numero_do_tipo(oficial) == 4:
            continue
        texto = " ".join(str(it.get(c, "") or "")
                         for c in ("cena", "composicao")).lower()
        achados = {nome for nome, palavras in ANGULOS.items()
                   if _acha_radicais(texto, palavras)}
        if achados:
            por_peca.append((oficial, achados))
    pares = []
    for i in range(len(por_peca)):
        for j in range(i + 1, len(por_peca)):
            comuns = por_peca[i][1] & por_peca[j][1]
            if comuns:
                pares.append((por_peca[i][0], por_peca[j][0],
                              ", ".join(sorted(comuns))))
    return pares


def pessoas_em_peca_errada(itens, tipos_selecionados=None):
    """Pecas cujo plano pede pessoas, mas cujo tipo as proibe. [] se nenhuma.

    So a peca 7 (Presenteie) leva figura humana — e ela EXIGE duas. Em
    qualquer outra, pessoa no plano vira ordem contraria a "NEVER add people"
    que o proprio prompt carrega, e o gerador resolve contradicao desenhando
    mais coisa, nao menos.
    """
    achadas = []
    for it in itens or []:
        if not isinstance(it, dict):
            continue
        oficial = tipo_canonico(it, tipos_selecionados)
        if numero_do_tipo(oficial) == 7:
            continue
        texto = " ".join(str(it.get(c, "") or "")
                         for c in ("composicao", "cena")).lower()
        achou = _acha_radicais(texto, _PESSOAS_NA_CENA)
        if achou:
            achadas.append((oficial, ", ".join(achou[:3])))
    return achadas


def cenas_repetidas(itens, tipos_selecionados=None):
    """Pares de pecas cuja cena descreve a mesma superficie. [] se nenhum.

    Consistencia e mesma paleta, mesmo material e mesma luz — nao a mesma
    mesa. Eram escrivaninha com caneta na 3, na 7 e na 8; depois madeira em
    quatro das sete. Comparar por SUPERFICIE, e nao pela frase inteira, porque
    a frase sempre muda um pouco e a mesa continua a mesma.
    """
    superficies = (
        "madeira", "nogueira", "carvalho", "marmore", "mármore", "pedra",
        "travertino", "linho", "algodao", "algodão", "tecido", "veludo",
        "couro", "vidro", "concreto", "cimento", "papel", "ceramica",
        "cerâmica", "metal", "escrivaninha", "mesa de jantar", "bancada",
        "prateleira", "estante", "sofa", "sofá", "cama", "tapete",
    )
    por_peca = []
    for it in itens or []:
        if not isinstance(it, dict):
            continue
        cena = str(it.get("cena", "") or "").lower()
        if not cena.strip():
            continue
        achadas = set(_acha_radicais(cena, superficies))
        if achadas:
            por_peca.append((tipo_canonico(it, tipos_selecionados), achadas))
    pares = []
    for i in range(len(por_peca)):
        for j in range(i + 1, len(por_peca)):
            comum = por_peca[i][1] & por_peca[j][1]
            if comum:
                pares.append((por_peca[i][0], por_peca[j][0],
                              ", ".join(sorted(comum))))
    return pares


# ── O PLANO SOBREVIVE À GERAÇÃO QUE ELE MANDOU FAZER ────────────────────────
#
# O DEFEITO, provado pelo .txt do dono em 28/09 17:34: a linha 47 do prompt
# enviado ao modelo era `PRODUTO: ` — vazia. A caneca tinha nome; o prompt não.
#
# Por quê: `img_triagem_config` e `img_triagem_plano` eram APAGADAS no fim do
# laço de geração, e é nelas que quem refaz UMA peça busca tudo — o nome do
# produto, a composição planejada, a COPY EXATA palavra por palavra, a direção
# de arte, a referência de layout e a ambientação. Toda peça refeita pelo chat
# nascia cega, e o gerador voltava a redigir a frase sozinho (que é de onde
# vieram "Portátile" e "apoliando").
#
# E o nome aparecia no LOG porque o log lê OUTRA chave (`img_nome_produto`).
# Duas respostas para a mesma pergunta — a Forma 5 —, e elas discordaram.
#
# POR QUE NÃO BASTA TIRAR O `del`: aquela chave faz DOIS trabalhos. Ela também
# é o sinal de "plano já consumido" que impede o painel de confirmação de
# reaparecer por cima da galeria (`imagem.py`, o `if` que desenha o painel).
# Apagar continua sendo certo para o SINAL e errado para o DADO. Então o dado
# muda de chave antes de o sinal cair.
CHAVE_PLANO_GERADO = "img_plano_gerado"
CHAVE_CONFIG_GERADA = "img_config_gerada"


def guardar_plano_gerado():
    """Copia plano e config para as chaves que sobrevivem ao fim da geração.

    Chame ANTES de apagar as chaves vivas. Nunca levanta.
    """
    try:
        _pl = st.session_state.get("img_triagem_plano")
        _cf = st.session_state.get("img_triagem_config")
        if _pl:
            st.session_state[CHAVE_PLANO_GERADO] = _pl
        if _cf:
            st.session_state[CHAVE_CONFIG_GERADA] = _cf
    except Exception:
        pass


def pecas_bloqueadas_da_geracao(plano=None):
    """As peças que a triagem bloqueou e que NÃO chegaram a ser geradas.

    POR QUE ISTO EXISTE
    -------------------
    Dono, 30/09: *"não gerou a imagem presenteando"*, e depois *"investigue as
    fotos não geradas"*.

    Não havia bug — havia um buraco. A peça bloqueada é listada com nome e
    motivo na tela do PLANO; no fim da geração o Studio apaga
    `img_triagem_plano` (ela é o sinal de "plano consumido"), o painel das
    bloqueadas vive dentro do `if` dessa chave e some junto, e o placar compara
    a galeria com as peças VIÁVEIS — então ele diz "8 de 8", em verde.

    A peça sumia por completo no instante em que a galeria abria: sem nome, sem
    motivo, sem aviso. Quem gerou via a ausência; a tela nunca a mencionava.

    O dado nunca se perdeu: `guardar_plano_gerado` salva o plano inteiro, com
    as bloqueadas e o `pergunta_info` de cada uma. Faltava LER essa parte.
    """
    itens = ((plano if plano is not None else plano_da_geracao()) or {}
             ).get("plano") or []
    return [it for it in itens if not it.get("viavel", True)]


def limpar_plano_gerado():
    """Descarta a cópia. É o que o Cancelar faz: não houve geração nenhuma."""
    try:
        st.session_state.pop(CHAVE_PLANO_GERADO, None)
        st.session_state.pop(CHAVE_CONFIG_GERADA, None)
    except Exception:
        pass


def plano_da_geracao():
    """O plano em vigor: o vivo, e a cópia da geração quando ele já caiu."""
    try:
        return (st.session_state.get("img_triagem_plano")
                or st.session_state.get(CHAVE_PLANO_GERADO) or {})
    except Exception:
        return {}


def config_da_geracao():
    """A config em vigor: a viva, e a cópia da geração quando ela já caiu."""
    try:
        return (st.session_state.get("img_triagem_config")
                or st.session_state.get(CHAVE_CONFIG_GERADA) or {})
    except Exception:
        return {}


def _direcao_de_arte_da_sessao():
    """A direção de arte que a triagem decidiu para o produto aberto. {} se não há."""
    try:
        return plano_da_geracao().get("direcao_de_arte") or {}
    except Exception:
        return {}


def prompt_para_regerar(tipo, instrucoes, dados_descricao, nome_produto):
    """O prompt de quem vai gerar UMA imagem de novo — com tudo o que o laço
    principal usa, e não com metade.

    Quem regera não pode receber menos do que quem gera: era essa a diferença
    entre a peça nascida na geração e a mesma peça refeita pelo botão ou pelo
    chat.
    """
    cfg = config_da_geracao()
    return montar_prompt_imagem(
        tipo, instrucoes, dados_descricao, nome_produto,
        refs_layout_nomes=cfg.get("refs_layout_nomes", []),
        instrucao_layout=cfg.get("instrucao_layout", ""),
        plano_triagem=plano_do_tipo(tipo),
        ambientacao=cfg.get("ambientacao", ""),
        direcao_arte=_direcao_de_arte_da_sessao(),
    )


def filtrar_por_produto(linhas, nome):
    """As linhas do log deste produto. Sem nome, devolve tudo.

    O FILTRO ERA IGUALDADE EXATA DE STRING, e "Caneca Medieval" não batia com
    "caneca medieval " — o histórico voltava vazio dizendo "nenhum prompt
    registrado", que é outra afirmação.

    Normaliza caixa e espaço, e SÓ isso. Continua sendo comparação exata
    depois de normalizar: afrouxar para "contém" faria a caneca de pedra
    puxar material da caneca de metal, que é o defeito que a colaboradora
    relatou em 28/09.
    """
    alvo = " ".join(str(nome or "").split()).casefold()
    if not alvo:
        return list(linhas or [])
    return [l for l in (linhas or [])
            if " ".join(str(l.get("produto", "")).split()).casefold() == alvo]


def recado_do_historico(todas, achadas, nome):
    """O que dizer quando o histórico volta vazio. "" quando não voltou.

    DUAS COISAS MUITO DIFERENTES cabiam na mesma frase:
      - o log está vazio (a geração foi antes de a coluna existir), e
      - o log tem linhas, mas nenhuma é deste produto.

    Dizer "nenhum prompt registrado" no segundo caso é afirmar o que não se
    sabe, e manda quem lê procurar no lugar errado.
    """
    if achadas:
        return ""
    if not todas:
        return ("O log de prompts ainda está vazio — **não há nenhum** "
                "registro. Ele começa na próxima geração: cada peça grava o "
                "texto que foi ao motor, e cada correção grava o dela. "
                "Imagens geradas antes desta atualização não têm prompt "
                "guardado.")
    return (f"O log tem **{len(todas)}** registro(s), mas nenhum com o nome "
            f"**{nome}**. O nome é o que foi digitado na geração — se lá "
            f"estava escrito de outro jeito, não bate. Apague o nome do "
            f"produto e prepare de novo para baixar **todos** os prompts, "
            f"sem filtrar.")


def prompt_de_cada_peca(itens, cfg, tipos_selecionados=None, direcao_arte=""):
    """O prompt EXATO de cada peça do plano. [(rótulo, texto), ...].

    FONTE ÚNICA. A tela mostra um por um dentro de um expander, e o `.txt`
    consolidado sai daqui também — se cada um montasse o seu, os dois
    discordariam, e a questão seria só quando (Forma 5 do CLAUDE.md).

    NÃO CHAMA MOTOR NENHUM: `prompt_que_sera_enviado` só monta o texto. Ver o
    prompt continua custando zero geração, que é o motivo de ele existir.
    """
    fora = []
    for item in (itens or []):
        oficial = tipo_canonico(item, tipos_selecionados)
        bruto = montar_prompt_imagem(
            oficial,
            cfg.get("instrucoes_extras", ""),
            cfg.get("dados_descricao"),
            cfg.get("nome_produto", ""),
            refs_layout_nomes=cfg.get("refs_layout_nomes", []),
            instrucao_layout=cfg.get("instrucao_layout", ""),
            plano_triagem=item,
            ambientacao=cfg.get("ambientacao", ""),
            direcao_arte=direcao_arte,
        )
        fora.append((oficial, prompt_que_sera_enviado(
            bruto,
            cfg.get("fotos_bytes") or [],
            refs_layout=cfg.get("refs_layout_bytes") or None,
            refs_layout_nomes=cfg.get("refs_layout_nomes", []),
            tipo=oficial,
        )))
    return fora


def txt_dos_prompts(pares, nome_produto="", direcao_arte=""):
    """Os prompts de todas as peças num arquivo só.

    Dono, 28/09: *"não tem como ter um botão que consolida o que será enviado
    de todas as imagens para que eu não precise abrir e copiar um por um?"*.
    Eram oito expanders, oito cliques e oito colagens — e a chance de errar
    uma no meio.

    O cabeçalho diz o que o arquivo é e o que ele NÃO é: a ambientação lida
    das referências entra só na hora de gerar, e não aparece aqui.
    """
    from datetime import datetime as _dt_txt
    import placar_core as _pc_txt
    linhas = [
        "=" * 78,
        "MS STUDIO — PROMPTS QUE SERÃO ENVIADOS AO MOTOR",
        "=" * 78,
        "",
        f"Produto: {nome_produto or '(sem nome)'}",
        f"Gerado em: {_pc_txt.agora_br():%d/%m/%Y %H:%M}",
        f"Peças: {len(pares)}",
        "",
        "COMO LER",
        "-" * 78,
        "Este é o texto EXATO que vai ao gerador de cada peça, montado antes",
        "de gastar geração nenhuma. Uma única diferença na hora de gerar:",
        "quando houver referências de AMBIENTAÇÃO, o cenário lido delas é",
        "acrescentado no fim — ele não aparece aqui porque ainda não foi lido.",
        "",
    ]
    # A DIREÇÃO DE ARTE É UM DICIONÁRIO, e não texto.
    #
    # `imagem.py:6681` — `plano.get("direcao_de_arte") or {}`. Chamar
    # `.strip()` nela levantava `AttributeError: 'dict' object has no
    # attribute 'strip'`, e o botão quebrava com a guarda verde: o teste
    # passava uma string que eu mesmo tinha escrito.
    #
    # `bloco_direcao_de_arte` é a MESMA função que o prompt usa para
    # renderizá-la. Escrever um segundo renderizador aqui seria a Forma 5:
    # dois textos para a mesma direção, discordando um dia.
    _dir_txt = (direcao_arte if isinstance(direcao_arte, str)
                else bloco_direcao_de_arte(direcao_arte))
    if str(_dir_txt or "").strip():
        linhas += ["DIREÇÃO DE ARTE (a mesma para todas as peças)",
                   "-" * 78, str(_dir_txt).strip(), ""]
    for i, (rotulo, texto) in enumerate(pares, 1):
        linhas += ["=" * 78,
                   f"PEÇA {i} — {rotulo}",
                   f"{len(texto)} caracteres",
                   "=" * 78, "", texto.strip(), ""]
    return "\n".join(linhas) + "\n"


def _baixar_historico_de_prompts(sufixo=""):
    """Um botão que leva TODO o histórico de prompts deste produto num .txt.

    POR QUE AQUI, NA TELA DE QUEM GERA
    ----------------------------------
    O dono: *"copiar todos os prompts vai gerar muito trabalho e a
    possibilidade de erros manuais... nem que tenha um botão de extração TXT
    de todo o histórico de prompts daquela sessão"*. Quem vive esta tela é
    quem gera e quem corrige; obrigá-la a ir até Gargalos para levar o
    histórico é uma ida a mais por rodada.

    DOIS CLIQUES, E É DE PROPÓSITO. O `download_button` precisa do arquivo
    PRONTO para desenhar — ou seja, um botão de um clique só leria a planilha
    a cada vez que esta tela fosse desenhada, que é a cada clique em qualquer
    coisa. O primeiro clique monta, o segundo baixa, e a tela não fica lenta
    para quem só queria ver a copy.
    """
    _produto = str(st.session_state.get("img_nome_produto", "")
                   or st.session_state.get("nome_produto", "") or "").strip()
    if st.button("📄 Preparar histórico de prompts (.txt)",
                 use_container_width=True, key=f"btn_hist_prompts{sufixo}"):
        try:
            import log_imagem as _li
            _todas = _li.ler(500)
            _linhas = filtrar_por_produto(_todas, _produto)
            import comparar_prompt as _cmp
            st.session_state[f"img_hist_txt{sufixo}"] = _cmp.relatorio_txt(_linhas)
            st.session_state[f"img_hist_recado{sufixo}"] = recado_do_historico(
                _todas, _linhas, _produto or "(sem nome)")
        except Exception as e:
            st.session_state[f"img_hist_txt{sufixo}"] = ""
            st.error(f"Não consegui montar o histórico: {type(e).__name__}")
    _recado = st.session_state.get(f"img_hist_recado{sufixo}") or ""
    if _recado:
        st.info(_recado)
    _txt = st.session_state.get(f"img_hist_txt{sufixo}") or ""
    if _txt:
        st.download_button(
            "⬇️ Baixar o histórico de prompts",
            data=_txt.encode("utf-8"),
            file_name=f"prompts_{(_produto or 'studio').replace(' ', '_')}.txt",
            mime="text/plain", use_container_width=True,
            key=f"btn_hist_prompts_baixar{sufixo}")
        st.caption(f"{len(_txt):,} caracteres · geração e todas as correções "
                   "de cada peça deste produto".replace(",", "."))


def marcar_peca_em_ajuste(num):
    """Diz qual peça da galeria está sendo ajustada agora. `None` limpa.

    POR QUE POR AQUI, E NÃO POR PARÂMETRO
    -------------------------------------
    O registro do prompt acontece na PORTA DO MOTOR (`gerar_imagem_ia`), que
    é o único ponto por onde geração e ajuste passam os dois. Mas a peça só é
    conhecida lá em cima, no comando do chat — e levá-la até a porta exigiria
    um parâmetro novo em três assinaturas e em todas as chamadas delas, com a
    certeza de que a quarta chamada nasceria sem ele.

    Sem a peça, a rastreabilidade que o dono pediu não existe: as correções
    de oito imagens diferentes virariam uma fila só, e a cadeia de cada uma
    ficaria impossível de reconstruir.

    O rótulo não serve de chave: depois de um ajuste ele vira outra coisa
    (ver `tipo_canonico`), e a cadeia se partiria no meio.

    POR QUE NÃO VAI SÓ NO `session_state`
    -------------------------------------
    O ajuste roda numa THREAD (`_rodar_cmd`, `_rodar_afg`), e é de dentro
    dela que `gerar_imagem_ia` registra o prompt. Fora da thread do script,
    `st.session_state` não tem contexto: a leitura volta vazia. A peça
    chegaria em branco ao registro e a cadeia — a coisa inteira que isto
    existe para montar — ficaria sem chave, em silêncio.

    Então o valor mora também num global do módulo, que a thread enxerga. O
    `session_state` continua sendo escrito porque é onde a tela procura.

    O QUE ISSO CUSTA, DITO EM VOZ ALTA: o global é do processo, não da
    sessão. Dois colaboradores ajustando peças diferentes no mesmo segundo
    podem trocar o número entre si. A consequência é uma linha de REGISTRO
    com a peça errada — nunca uma imagem errada, e nunca um erro de tela.
    Resolver de vez pede a peça viajando por parâmetro até o motor, que são
    três assinaturas e todas as chamadas delas.
    """
    _valor = "" if num is None else str(num)
    # PELO CONTEXTO POR THREAD, e nao mais por um global do processo.
    #
    # O global aqui era do PROCESSO: dois colaboradores ajustando pecas
    # diferentes no mesmo segundo trocavam o numero entre si, e a linha de
    # registro saia com a peca errada. O custo estava declarado em voz alta
    # nesta docstring — mas declarar nao e consertar, e era o MESMO defeito
    # que `produto` e `usuario` tinham no mesmo registro, tres campos lado a
    # lado. Eu tinha corrigido dois e deixado o terceiro.
    try:
        import log_imagem as _li_peca
        _li_peca.marcar_contexto(peca=_valor)
    except Exception:
        pass
    try:
        st.session_state["img_peca_em_ajuste"] = _valor
    except Exception:
        pass


def peca_em_ajuste():
    """A peça marcada, ou "" quando o ajuste não é de uma peça da galeria.

    Lê do contexto POR THREAD — o mesmo que carrega produto e usuário, e o
    mesmo que a thread de trabalho herda de quem a criou.
    """
    try:
        import log_imagem as _li_peca
        return _li_peca.contexto_atual().get("peca", "") or ""
    except Exception:
        return ""


_PEDIDO_DE_COR = _re_imp.compile(
    r"(?i)\b(cor(?:es)?|colorir|recolorir|pint(?:ar|e)|tingir|tonalidade|"
    r"preto|preta|branco|branca|vermelh[oa]|azul|verde|amarel[oa]|"
    r"dourad[oa]|pratead[oa]|prata|bege|marrom|cinza|rosa|roxo|laranja)\b")


def _pedido_fala_de_cor(instrucao):
    """O pedido autoriza mexer em cor? Então a trava de cor não vale inteira.

    Larga de propósito: errar para o lado de NÃO travar faz o ajuste pedido
    acontecer e deixa a conferência julgar o resultado. Errar para o lado de
    travar faz o que aconteceu em 01/10 — cinco pedidos recusados em sequência
    porque o prompt proibia aquilo que o colaborador tinha pedido.
    """
    return bool(_PEDIDO_DE_COR.search(str(instrucao or "")))


# ── AJUSTAR OU REFAZER: QUEM DECIDE É O SISTEMA, E NÃO O COLABORADOR ──────
#
# 01/10. O dono pediu, na mesma frase: "mudar a cor interior para preta, e
# mudar a quantidade de divisorias para 6". São duas coisas de naturezas
# diferentes, e ele não tem por que saber disso:
#
#   cor do interior ..... uma propriedade de uma região que já existe. O
#                         ajuste fino edita isso bem.
#   12 nichos -> 6 ...... a geometria interna da caixa muda. Não há o que
#                         editar: a peça precisa nascer de novo.
#
# O ajuste fino é edição cirúrgica — ele preserva o resto do quadro. Pedir
# recomposição a ele passa do que ele faz, e ele devolve a imagem INTACTA,
# sem erro nenhum. Foram quatro rodadas assim, e o Studio ainda anunciou
# "instrução enviada" em cada uma.
#
# A REGRA PRÁTICA, e ela é a melhor que achamos: se cumprir o pedido exige
# INVENTAR PIXEL ESTRUTURAL de uma parte relevante da cena, em vez de editar
# uma propriedade ou a posição de algo que já está lá, é REFAZER.
#
# ELA SÓ ESCALA, NUNCA REBAIXA. "refazer" pedido com todas as letras pelo
# colaborador continua sendo refazer: a dúvida do sistema não revoga a
# certeza de quem pediu. Errar para o lado de refazer custa uma geração;
# errar para o lado de ajustar custa a rodada inteira e devolve a imagem
# igual — foi o que aconteceu.
_MARCAS_DE_RECOMPOSICAO = (
    # quantidade de peças do próprio produto
    # O NUMERO SOZINHO JA BASTA, desde que venha colado numa PEÇA.
    #
    # A primeira versao exigia "para|em|com|ter|sejam" antes do numero, e
    # deixou passar "colocar 6 divisorias" — que e como alguem pede isso na
    # vida real. Exigir a preposicao era travar a REDACAO, e nao o assunto.
    (r"(?:quantidade|n[úu]mero)\s+de\s+\w+|"
     r"\b\d+\s+"
     r"(?:divis[óo]ri|nicho|comparti|al[çc]a|gaveta|prateleira|furo|"
     r"bot[ãa]o|bot[õo]es|pe[çc]a)",
     "muda a quantidade de peças do produto"),
    # gente, pose, ação
    (r"\b(pessoa|pessoas|modelo|m[ãa]o de|crian[çc]a|homem|mulher|casal|"
     r"entregando|segurando|usando|vestindo|sentad|em p[ée])\b",
     "muda quem aparece na cena ou o que essa pessoa faz"),
    # ambiente inteiro
    (r"\b(cen[áa]rio|ambiente|fundo de|local|lugar|sala|cozinha|quarto|"
     r"escrit[óo]rio|loja|mesa de|ambienta)\w*\b",
     "troca o ambiente da cena"),
    # aberto <-> fechado, ângulo, face
    #
    # AS PALAVRAS DE POSIÇÃO SÓ VALEM QUANDO FALAM DO PRODUTO.
    #
    # ACHADO EM PRODUÇÃO, 05/10. O dono pediu "apenas troque a palavra
    # «Metal» para «inox»" — um retoque de uma palavra. O chat, para ser
    # preciso, escreveu ONDE a palavra estava: "o cartão DE BAIXO à
    # esquerda". A regex casou "de baixo", escalou para REFAZER com o motivo
    # "pede uma geometria ou uma face que a arte atual não mostra", e a
    # refação do zero devolveu uma caneca com DUAS alças.
    #
    # "de baixo" num cartão é POSIÇÃO DE UM BLOCO DE TEXTO; "de baixo" na
    # foto é ÂNGULO DE CÂMERA. A regra travava a REDAÇÃO e não o assunto —
    # a Forma 2 do CLAUDE.md, do lado que acusa o inocente. E alarme falso
    # aqui não é barato: ele custa uma geração E a imagem que estava certa.
    #
    # O recorte: a palavra não escala quando vem ligada a um elemento
    # GRÁFICO. O resto da lista continua intacto.
    (r"(?<!cart[ãa]o )(?<!card )(?<!bloco )(?<!selo )(?<![íi]cone )"
     r"(?<!texto )(?<!legenda )(?<!faixa )"
     r"\b(aberta?|fechada?|abrir|fechar|de costas|traseir|lateral|"
     r"de cima|de baixo|outro [âa]ngulo|girar|virar)\b",
     "pede uma geometria ou uma face que a arte atual não mostra"),
    # recompor o quadro
    (r"\b(recompor|reorganizar|refazer o layout|trocar a composi)\w*\b",
     "reorganiza a composição"),
)
_RECOMPOSICAO = tuple(
    (_re_imp.compile(_p, _re_imp.I), _m) for _p, _m in _MARCAS_DE_RECOMPOSICAO)


def classificar_edicao(instrucao):
    """("ajustar"|"refazer", motivo) para o pedido. O sistema é quem decide.

    O motivo volta junto porque o colaborador merece saber por que a peça
    inteira está sendo refeita em vez de retocada — e porque, quando a
    classificação errar, é o motivo que diz onde.
    """
    txt = str(instrucao or "")
    for rx, motivo in _RECOMPOSICAO:
        if rx.search(txt):
            return "refazer", motivo
    return "ajustar", ""


def montar_prompt_ajuste_fino(instrucao, tipo=None, cor_produto=None):
    """Monta prompt para edição cirúrgica de uma imagem existente.

    NÃO aplica PADRAO_VISUAL, NÃO aplica INSTRUCAO_COMPOSICAO.
    Instrui a IA a fazer SOMENTE a modificação descrita, preservando tudo o mais.

    O marcador MS_FUNDO é obrigatório: sem ele, gerar_imagem_ia trata a imagem
    como "padrão" e injeta no prompt "fundo azul-cinza da marca, OBRIGATÓRIO" e
    "todo texto em painéis dedicados". Numa capa — que é branca e sem texto —
    essas duas linhas contradizem o "não mude mais nada" logo acima, e o modelo
    obedece a instrução mais específica: devolve a capa com fundo colorido e
    títulos. Foi exatamente isso que aconteceu ao pedir "aumente a estátua".
    """
    # Sem tipo conhecido, o correto é NÃO impor nada: a imagem já existe e a
    # edição é cirúrgica. "padrao" imporia o fundo da marca a uma foto qualquer.
    _modo = modo_fundo_do_tipo(tipo) if tipo else "personalizado"
    # A TRAVA DE COR NÃO PODE SER APLICADA CEGAMENTE.
    #
    # `_trava_cor_produto` diz "é PROIBIDO recolorir o produto". Colada num
    # ajuste cujo pedido é "mudar a cor interior do produto para preta", ela
    # proíbe exatamente o que se pediu — e era a terceira voz contra o mesmo
    # pedido, junto com o cabeçalho "O PRODUTO NÃO É PARTE DO AJUSTE" e o
    # booleano do juiz.
    #
    # Quando o pedido fala de cor, a trava sai e entra no lugar a regra que
    # vale de verdade: muda a cor PEDIDA, preserva as outras.
    _trava = ("" if _pedido_fala_de_cor(instrucao) else
              _trava_cor_produto(cor_do_produto_atual()
                                 if cor_produto is None else cor_produto))
    if _pedido_fala_de_cor(instrucao):
        _trava = ("TRAVA DE COR — PARCIAL NESTE AJUSTE: a MODIFICAÇÃO "
                  "SOLICITADA fala de cor, então a cor que ela cita MUDA. "
                  "Toda outra cor do produto permanece exatamente como está "
                  "na imagem, e nenhuma cor é 'harmonizada' com a direção de "
                  "arte, com o fundo, com o cenário ou com a iluminação.\n")
    return f"""MS_FUNDO: {_modo}
MODO AJUSTE FINO — EDIÇÃO CIRÚRGICA DE IMAGEM EXISTENTE

A imagem fornecida é a imagem atual que deve ser editada.

MODIFICAÇÃO SOLICITADA — o único e exclusivo ponto a alterar:
{instrucao}

QUEM MANDA NESTE PEDIDO (leia antes de tudo o que vem abaixo):
A MODIFICAÇÃO SOLICITADA acima é o objetivo, e ela tem prioridade sobre TODAS
as regras deste texto. As regras abaixo existem para dizer o que NÃO muda
junto — elas nunca proíbem aquilo que foi pedido. Se alguma regra abaixo
parecer proibir a modificação pedida, entenda que ela vale para TODO O RESTO
da imagem, e não para o ponto pedido.
FAZER O QUE FOI PEDIDO NÃO É OPCIONAL. Devolver a imagem sem a modificação é
falha, não segurança.
NÚMEROS: use os que estiverem na MODIFICAÇÃO SOLICITADA ou já escritos na
imagem. Não estime, não arredonde e não invente nenhum outro.

{INSTRUCAO_AJUSTE_FINO}

{INSTRUCAO_FIDELIDADE_NUCLEO}
{_trava}
PRESERVAÇÃO DO PRODUTO — É O COMPLEMENTO DO PEDIDO, NUNCA O CONTRÁRIO:
- O produto PODE ser alterado exatamente nas características que a
  MODIFICAÇÃO SOLICITADA mandar alterar. Essas mudanças são o objetivo.
- Toda característica do produto que o pedido NÃO citou é intocável: mesma
  textura, mesmo acabamento, mesmo brilho, mesmos detalhes, mesma superfície.
- Pedra, strass, cravejado, relevo, textura, costura, grão: se está no produto
  da imagem e o pedido não falou dela, continua ali, no mesmo lugar e na mesma
  quantidade. Um urso cravejado de strass no corpo inteiro não pode sair liso
  porque pediram outra cor de fundo.
- "Melhorar", "realçar", "deixar mais bonito" NÃO citam característica
  nenhuma, e portanto não autorizam mudar nada no produto. Pedido sobre cor,
  luz ou fundo mexe na cor, na luz ou no fundo.
- Exemplos, para não restar dúvida:
    pedido muda a COR do produto -> mude a cor pedida e preserve forma,
    textura, material, acabamento, peças e os demais detalhes;
    pedido muda a QUANTIDADE de peças (divisórias, nichos, alças) -> faça
    exatamente a quantidade pedida e preserve material, acabamento, cor e o
    resto;
    pedido muda só o FUNDO -> nenhuma característica do produto muda;
    pedido muda o TAMANHO do produto na cena -> mude só a escala aparente,
    sem redesenhar geometria nem superfície.

Reproduza a imagem fornecida com fidelidade absoluta, aplicando a modificação
acima. Trate como intocável todo elemento que a instrução não mencionou.
"""


# ── GOOGLE DRIVE — GESTÃO DE PASTAS ───────────────────────────────────────────

# ── CONFERÊNCIA DO AJUSTE — o passo que faltava ──────────────────────────────
#
# O caminho do ajuste era: instrução -> prompt -> gera -> salva na galeria.
# Entre "gera" e "salva" não havia nada. Ninguém — nem o modelo, nem o
# assistente do chat — comparava o que saiu com o que foi pedido, e o
# assistente respondia "instrução enviada" como se fosse "pronto", quando ele
# literalmente não tinha como saber. O erro só aparecia quando o colaborador
# abria o arquivo, e a rodada inteira estava perdida.
#
# Com o ChatGPT o colaborador cola a imagem, o modelo OLHA, ele corrige, o
# modelo olha de novo. Ciclo fechado. A diferença nunca foi de compreensão da
# linguagem: era que um lado tem olhos e o outro não.
#
# Aqui o antes e o depois vão juntos para um modelo com visão, com o pedido
# original, e a pergunta é dupla de propósito:
#
#   foi feito?      — o que a pessoa pediu aconteceu de verdade?
#   mudou mais?     — o ajuste fino promete não mexer em nada além do pedido, e
#                     essa promessa nunca era verificada. Regerar o produto
#                     inteiro para trocar uma cor de fundo é falha, mesmo com a
#                     cor certa.

MODELO_CONFERENCIA = "claude-opus-5"

_ESQUEMA_CONFERENCIA = {
    "type": "object",
    "properties": {
        "feito": {
            "type": "boolean",
            "description": "true apenas se a mudança pedida está claramente "
                           "visível na imagem DEPOIS.",
        },
        "o_que_saiu": {
            "type": "string",
            "description": "Em uma frase, o que de fato mudou entre ANTES e "
                           "DEPOIS, em português do Brasil.",
        },
        "o_que_falta": {
            "type": "string",
            "description": "Se feito=false, o que ainda precisa acontecer, em "
                           "português do Brasil e em linguagem de instrução "
                           "para o gerador. Vazio se feito=true.",
        },
        "colateral": {
            "type": "string",
            "description": "O que mudou SEM ter sido pedido (produto, "
                           "enquadramento, cores, texto). Vazio se nada além "
                           "do pedido mudou.",
        },
        # BOOLEANO TAMBEM PARA O COLATERAL GERAL, pela mesma razao do campo
        # do produto: `colateral` e texto livre, e texto livre nao decide
        # fluxo. Ou o programa le uma resposta fechada, ou segue adiante sem
        # ter lido nada.
        "houve_colateral": {
            "type": "boolean",
            "description": "true se algum elemento mudou ALÉM do que era "
                           "necessário para executar a alteração pedida. "
                           "Mudança que o pedido autorizou NÃO é colateral.",
        },
        "produto_colateral": {
            "type": "string",
            "description": "O que mudou no PRODUTO sem o pedido ter "
                           "autorizado. Vazio quando o produto só mudou "
                           "naquilo que foi pedido.",
        },
        # Campo separado, e booleano, porque `colateral` é texto livre: dava
        # para relatar "removeu o strass do corpo do urso" e o código seguir
        # adiante sem nunca ter lido aquilo. Pergunta fechada tem resposta que
        # o programa consegue obedecer.
        # O NOME MUDOU, E O NOME ERA METADE DO DEFEITO.
        #
        # Chamava-se `produto_alterado`, e dizia: "true se o PRODUTO em si
        # mudou — forma, textura, acabamento, material, detalhes, pecas, COR
        # DO PROPRIO PRODUTO". O laco revertia a imagem quando vinha true.
        #
        # O dono pediu, em 01/10: "mudar a cor interior do produto para
        # preta" e "mudar a quantidade de divisorias para 6". O gerador fez.
        # O juiz respondeu true — CERTISSIMO, pela definicao acima. E o
        # codigo reverteu, cinco vezes seguidas, dizendo "toda vez o produto
        # mudava junto".
        #
        # NENHUM pedido que mexesse no produto conseguia passar: a trava era
        # inatingivel por construcao. Ela nasceu de outro caso — um urso de
        # strass que voltou liso depois de um ajuste no FUNDO — e passou a
        # bloquear o pedido explicito.
        #
        # Renomear e parte do conserto, e nao enfeite: a analise externa
        # disse a frase exata — "mesmo mudando a descricao, daqui a seis
        # meses alguem le o nome e volta a tratar como 'qualquer mudanca no
        # produto'". O nome agora carrega a condicao.
        "produto_alterado_fora_do_pedido": {
            "type": "boolean",
            "description": "true APENAS se o produto mudou em alguma "
                           "característica que o pedido NÃO mandou alterar — "
                           "forma, textura, acabamento, material, peças ou "
                           "cor não citadas no pedido. Strass, pedra, relevo "
                           "ou textura que sumiu sem ter sido pedido conta "
                           "como true. Se o pedido mandou mudar aquilo, a "
                           "mudança é intencional e NÃO conta. Fundo, luz, "
                           "cenário, texto e enquadramento não são o produto.",
        },
    },
    "required": ["feito", "o_que_saiu", "o_que_falta", "colateral",
                 "houve_colateral", "produto_colateral",
                 "produto_alterado_fora_do_pedido"],
    "additionalProperties": False,
}


def _bloco_imagem(img_bytes):
    return {"type": "image",
            "source": {"type": "base64",
                       "media_type": _detectar_mime(img_bytes),
                       "data": base64.b64encode(img_bytes).decode("utf-8")}}


def _chave_anthropic():
    """A chave da IA de conferência, ou "" quando não há.

    `st.secrets.get` não é um dicionário comum: sem arquivo de secrets ele
    LEVANTA em vez de devolver o padrão. Chamado de dentro de um try alheio,
    isso virava "falha ao conferir" com uma mensagem que não dizia o motivo.
    """
    import chaves as _ch
    return _ch.ler("ANTHROPIC_API_KEY")


def motores_de_imagem():
    """(ok, aviso) — os dois motores estão de pé? Não gasta API nenhuma.

    Serve à mesma regra do aviso da revisão de texto: dizer ANTES de gastar, e
    não depois. Sem a chave da OpenAI, o Studio não tem motor primário — e
    descobrir isso pelo crédito do RESERVA acabando é descobrir tarde, com as
    imagens já pagas e erradas.
    """
    import chaves as _ch
    tem_openai = _ch.tem("OPENAI_API_KEY")
    tem_gemini = _ch.tem("GEMINI_API_KEY")

    if tem_openai and tem_gemini:
        return True, ""
    if not tem_openai and not tem_gemini:
        return False, ("**Nenhum motor de imagem configurado.** Nem "
                       "`OPENAI_API_KEY` nem `GEMINI_API_KEY` estão no "
                       "Railway — nada vai ser gerado.")
    if not tem_openai:
        return False, (
            "**O motor primário está desligado.** `OPENAI_API_KEY` não está "
            "configurada no Railway, então TODA imagem está sendo gerada pelo "
            "reserva (Gemini) — que recebe menos informação do produto e tem "
            "cota própria. Foi assim que os créditos do reserva acabaram: ele "
            "estava fazendo o trabalho dos dois.")
    return True, ("O motor reserva está desligado (`GEMINI_API_KEY` ausente). "
                  "Se o primário falhar, não há para onde cair.")


def revisao_de_texto_disponivel():
    """A revisão de texto tem como rodar? (ok, motivo). NÃO gasta API.

    "Está funcionando?" não pode depender de alguém clicar um botão de teste.
    Quando a resposta é não, as peças saem sem ninguém ler o texto delas — e
    foi assim que uma peça com palavra inventada chegou ao gestor. A tela
    pergunta isto sozinha, toda vez que abre.

    Duas perguntas em uma: a chave existe? e a última leitura funcionou? A
    segunda cobre o que a primeira não vê — API fora do ar, cota estourada,
    modelo recusado.
    """
    if not _chave_anthropic():
        return False, ("ANTHROPIC_API_KEY não está configurada neste serviço.")
    try:
        ultimo = st.session_state.get("img_revisao_erro", "")
    except Exception:
        ultimo = ""
    if ultimo:
        return False, ultimo
    return True, ""


def registrar_revisao(relato):
    """Guarda se a última revisão conseguiu rodar. Só na thread principal.

    Chamada de dentro de uma thread, `st.session_state` não existe — por isso
    o try. Errar para o lado de não registrar é seguro; o contrário apagaria o
    aviso de uma falha que continua de pé.
    """
    if not relato:
        return
    try:
        if relato.get("ok") is None and relato.get("erro"):
            st.session_state["img_revisao_erro"] = relato["erro"]
        elif relato.get("ok") is not None:
            st.session_state.pop("img_revisao_erro", None)
    except Exception:
        pass


def conferir_ajuste(antes, depois, instrucao):
    """A mudança pedida aconteceu? Devolve (veredito, erro).

    `veredito` é o dicionário do esquema acima; `erro` é texto quando não deu
    para conferir. Os dois nunca vêm preenchidos juntos.

    Falha de conferência NÃO é falha do ajuste: sem chave, sem rede ou com a
    API fora do ar, quem chama segue com a imagem que tem. O que não pode
    acontecer é o contrário — dizer "conferido" sem ter conferido, que é
    exatamente o hábito que esta função existe para quebrar.
    """
    api_key = _chave_anthropic()
    if not api_key:
        return None, "ANTHROPIC_API_KEY não configurada."
    if not antes or not depois:
        return None, "Faltou a imagem de antes ou a de depois."

    conteudo = [
        {"type": "text", "text": "IMAGEM ANTES (a que existia):"},
        _bloco_imagem(antes),
        {"type": "text", "text": "IMAGEM DEPOIS (a que o gerador devolveu):"},
        _bloco_imagem(depois),
        {"type": "text", "text": (
            "Um colaborador pediu esta alteração, em português do Brasil:\n\n"
            f"\"{instrucao.strip()}\"\n\n"
            "O PEDIDO ACIMA DEFINE O QUE ESTÁ AUTORIZADO A MUDAR.\n"
            "Uma característica não é colateral só porque mudou: se o "
            "colaborador pediu explicitamente que ela mudasse, a mudança é "
            "intencional, e é o que se esperava.\n\n"
            "Compare ANTES e DEPOIS sempre em relação ao PEDIDO.\n\n"
            "1. O PEDIDO FOI CUMPRIDO? Responda em `feito`. Confira CADA "
            "alteração pedida, uma a uma; só responda true se todas estão "
            "claramente visíveis no DEPOIS. Mudança parcial, ou que só se "
            "percebe procurando, conta como NÃO feita. Havendo QUANTIDADE no "
            "pedido, conte na imagem: pedido de '6 divisórias' não se cumpre "
            "com 5, 7 ou 12. Em `o_que_saiu`, diga o que foi realizado; em "
            "`o_que_falta`, o que ainda precisa acontecer.\n\n"
            "2. MUDOU ALGO ALÉM DO PEDIDO? Responda em `houve_colateral`. "
            "Olhe o que o pedido NÃO mandou mudar: cenário, fundo, "
            "enquadramento, luz, textos, objetos e as partes do produto que "
            "o pedido não citou. NÃO marque como colateral aquilo que foi "
            "pedido. NÃO marque consequência visual inevitável da própria "
            "edição — a sombra que acompanha uma peça que mudou de lugar, o "
            "reflexo que muda junto com a cor pedida. Em `colateral`, "
            "descreva só o que mudou sem autorização.\n\n"
            "3. O PRODUTO MUDOU ALÉM DO QUE O PEDIDO AUTORIZOU? Responda em "
            "`produto_alterado_fora_do_pedido`. Primeiro liste, para você "
            "mesmo, quais características do produto o pedido autorizou "
            "mudar. Depois olhe TODAS AS OUTRAS de perto: strass, pedra, "
            "cravejado, relevo, textura, brilho, costura, acabamento, "
            "material, forma, número de peças. Um urso cravejado que ficou "
            "liso é true — ninguém pediu isso. A cor interior que ficou "
            "preta porque pediram 'interior preto' é false. Em "
            "`produto_colateral`, descreva só o que mudou no produto sem o "
            "pedido ter autorizado.\n\n"
            "Escreva em português do Brasil, direto, sem elogio e sem rodeio. "
            "O texto de 'o_que_falta' vai ser usado como instrução para o "
            "gerador tentar de novo, então escreva o que ELE deve fazer — e "
            "positivamente, dizendo o que deve existir, nunca o que não deve: "
            "instrução negativa é ignorada por gerador de imagem."
        )},
    ]

    try:
        cliente = anthropic.Anthropic(api_key=api_key)
        resposta = cliente.messages.create(
            model=MODELO_CONFERENCIA,
            max_tokens=2000,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium",
                           "format": {"type": "json_schema",
                                      "schema": _ESQUEMA_CONFERENCIA}},
            messages=[{"role": "user", "content": _idioma.com_regra(conteudo)}],
        )
        if resposta.stop_reason == "refusal":
            return None, "A conferência foi recusada pelo modelo."
        texto = next(b.text for b in resposta.content if b.type == "text")
        return json.loads(texto), ""
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:160]}"


# ── Revisão do texto escrito DENTRO da imagem ────────────────────────────────
#
# O gerador escreve o texto como PIXEL, não como texto: ele desenha as letras.
# E erra — "Portátile e compacto", "Sem a ene esar sem energia elétrica",
# "Limpeza rápida e bruush, apoliando coma ser comforido". Saiu assim numa peça
# de benefícios que foi parar na tela do gestor.
#
# Corretor ortográfico não pega isso, porque não há texto para corrigir: há uma
# imagem. A única forma de conferir é LER a imagem — e é o que esta função faz,
# comparando o que está escrito com o que foi pedido.
#
# Só nos tipos que têm texto. Capa e ambientação não têm, e mandá-las para cá
# seria pagar uma leitura para ouvir "não há texto".
_ESQUEMA_TEXTO = {
    "type": "object",
    "properties": {
        "tem_texto": {
            "type": "boolean",
            "description": "A imagem contém alguma palavra escrita?",
        },
        "correto": {
            "type": "boolean",
            "description": "true apenas se TODAS as palavras estão escritas "
                           "corretamente em português do Brasil e fazem "
                           "sentido. Uma única palavra inventada, truncada ou "
                           "com letra trocada torna isto false.",
        },
        "erros": {
            "type": "string",
            "description": "As palavras erradas, entre aspas, separadas por "
                           "vírgula. Vazio se correto=true.",
        },
        "texto_correto": {
            "type": "string",
            "description": "Se correto=false, TODO o texto que deve aparecer "
                           "na imagem, já escrito certo, na mesma ordem e "
                           "posição. É isto que vai para o gerador refazer.",
        },
    },
    "required": ["tem_texto", "correto", "erros", "texto_correto"],
    "additionalProperties": False,
}

# Os tipos que levam texto. Capa (1) e ambientação (8) são foto limpa.
#
# O 4 (close nos detalhes) entrou depois: o preset dele pede "2 callouts com
# legenda de até 4 palavras" (PRESETS["4 — Close nos detalhes"]) — é texto
# desenhado como qualquer outro, e ficava fora da revisão sem nenhum motivo.
TIPOS_COM_TEXTO = ("2 —", "3 —", "4 —", "5 —", "6 —", "7 —")


# Os dois tipos que comprovadamente NÃO levam texto. Tudo o mais pode levar —
# inclusive "Ajuste Fino — …" e "Personalizado", que não têm número e por isso
# escapavam da revisão inteira.
TIPOS_SEM_TEXTO = ("1 —", "8 —")


def tipo_tem_texto(tipo):
    return str(tipo or "").strip().startswith(TIPOS_COM_TEXTO)


def pode_ter_texto(tipo):
    """Vale a pena LER esta imagem? Só capa e ambientação não valem.

    `tipo_tem_texto` responde pela lista dos oito tipos, e é o certo na hora de
    gerar, onde o tipo é sempre um deles. Depois de um ajuste o rótulo vira
    "Ajuste Fino — aumente o produto", que não começa com número nenhum: pela
    outra pergunta, a peça saía do ajuste sem ninguém ler o texto dela.
    """
    return not str(tipo or "").strip().startswith(TIPOS_SEM_TEXTO)


def conferir_texto(imagem, pedido=""):
    """O texto escrito na imagem está correto? (veredito, erro).

    Falha de conferência NÃO reprova a imagem: sem chave ou sem rede, quem
    chama segue com o que tem. O que não pode acontecer é o contrário — dar por
    conferido sem ter lido.
    """
    api_key = _chave_anthropic()
    if not api_key:
        return None, "ANTHROPIC_API_KEY não configurada."
    if not imagem:
        return None, "Sem imagem para conferir."

    conteudo = [
        _bloco_imagem(imagem),
        {"type": "text", "text": (
            "Leia TODO o texto escrito nesta imagem — títulos, subtítulos, "
            "rótulos, selos, qualquer palavra.\n\n"
            + (f"O texto que o colaborador pediu era, em português do "
               f"Brasil:\n{pedido.strip()}\n\n" if pedido.strip() else "")
            + "Responda se está tudo escrito corretamente em português do "
            "Brasil.\n\n"
            "Seja rigoroso. Gerador de imagem desenha letras e inventa "
            "palavras: 'Portátile', 'apoliando', 'comforido', 'bruush', "
            "'seis materia' são erros, mesmo parecendo palavra. Palavra "
            "truncada, letra trocada, concordância errada e frase sem "
            "sentido contam como erro.\n\n"
            "NÃO são erro, e reprovar por elas é o defeito oposto:\n"
            "- estrangeirismo consagrado no comércio brasileiro — premium, "
            "design, kit, gift, home, office, light, fit, blend, style — "
            "escrito corretamente;\n"
            "- palavra em CAIXA ALTA, que é escolha de tipografia;\n"
            "- nome próprio, marca ou nome de produto;\n"
            "- unidade e abreviação (cm, ml, g, kg, un.);\n"
            "- frase curta sem ponto final, que é estilo de peça gráfica.\n"
            "Só reprove o que um leitor brasileiro leria como escrito "
            "ERRADO. Reprovar palavra certa custa três gerações pagas e "
            "barra uma peça boa.\n\n"
            "Em `texto_correto`, escreva TODO o texto da imagem já "
            "corrigido, mantendo a mesma ordem e a mesma divisão em blocos "
            "— é isso que vai ser mandado ao gerador para refazer a peça."
        )},
    ]
    try:
        cliente = anthropic.Anthropic(api_key=api_key)
        resposta = cliente.messages.create(
            model=MODELO_CONFERENCIA,
            max_tokens=2000,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium",
                           "format": {"type": "json_schema",
                                      "schema": _ESQUEMA_TEXTO}},
            messages=[{"role": "user", "content": _idioma.com_regra(conteudo)}],
        )
        if resposta.stop_reason == "refusal":
            return None, "A conferência de texto foi recusada pelo modelo."
        texto = next(b.text for b in resposta.content if b.type == "text")
        return json.loads(texto), ""
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:160]}"


# ── A PEÇA É OLHADA, E NÃO SÓ LIDA ──────────────────────────────────────────
#
# Dono, 28/09: "por que o prompt continua gerando imagens erradas mudando o
# produto e posicionando informações cortadas?"
#
# A resposta estava nos 9 prompts dele — as regras violadas estavam TODAS
# escritas: "A FOLGA DA BORDA MANDA" 5 vezes, "NADA SOBREPÕE O PRODUTO" 6,
# "JAMAIS substitua o produto" 7. Pela legenda do próprio .txt: regra nos dois
# lados → o modelo ignorou, e escrever de novo não resolve.
#
# E a conferência que existia pergunta UMA coisa: o que está escrito é
# português correto? `revisar_texto` não vê texto CORTADO pela borda, cartão
# SOBRE o produto, nem alça a mais. A peça saía com o português perfeito e a
# caneca com duas alças — conferida, aprovada e errada.
#
# Estas duas funções fazem as outras quatro perguntas, e fazem a única que
# resolve fidelidade: comparando a peça COM AS FOTOS DO PRODUTO, lado a lado.
_PERGUNTAS_DA_PECA = (
    "1. Alguma palavra, número, seta, cartão ou selo está CORTADO pela borda "
    "do quadro, ou encostando nela sem folga?",
    "2. Algum texto, ícone, cartão, faixa ou objeto de cenário está POR CIMA "
    "do produto, tampando qualquer parte dele?",
    "3. O produto da peça é o MESMO das fotos de referência? Compare peça a "
    "peça: número de alças, formato, acabamento, componentes, cor.",
)


# ── A QUARTA PERGUNTA SAI DA MEDIDA DA PEÇA, E NÃO DE UM "METADE" FIXO ────
#
# Ela era: *"o produto está DEFORMADO (...) ou pequeno demais, ocupando menos
# de metade do quadro?"* — com "metade" escrito à mão.
#
# Isso é o defeito do produto gigante, outra vez, e agora DENTRO da
# conferência. Nas peças de CENA (3, 7 e 8) o produto ocupa uma fração modesta
# porque é essa a escala real dele: um compasso de 16 cm na mão de uma criança
# não chega perto de metade do quadro. A pergunta mandava REPROVAR a peça
# certa — e cada reprovação aqui é uma geração paga que volta com o produto
# inflado. A conferência fabricaria o defeito que o prompt acabou de parar de
# pedir.
#
# E eram duas vozes sobre o mesmo número: a faixa em `OCUPACAO` e o "metade"
# daqui. Já aconteceu com a regra de densidade, com a ocupação e com o tamanho
# da frase. Aqui a medida vem de `OCUPACAO`, que é a fonte única — e nas peças
# de cena a pergunta deixa de falar em fração e passa a falar em ESCALA REAL,
# que é o que a peça pede.
def pergunta_do_tamanho(tipo):
    """A quarta pergunta da conferência, na medida DESTA peça."""
    base = ("4. O produto está DEFORMADO — esticado, achatado ou torto — "
            "em relação às fotos?")
    if numero_do_tipo(tipo) in TIPOS_DE_CENA:
        return (base + " E ele aparece na ESCALA REAL que teria nessa cena, "
                "ou foi inflado — maior que a mão, o móvel ou a pessoa que "
                "está com ele? Produto ocupando uma fração modesta do quadro "
                "NÃO é defeito nesta peça: é o que se espera dela.")
    faixa = faixa_de_ocupacao(tipo)
    if not faixa or faixa[0] is None:
        return base
    return (base + f" E ele ocupa MENOS de {faixa[0]}% do quadro, que é a "
            f"medida desta peça?")


def perguntas_da_peca(tipo=""):
    """As quatro perguntas da conferência, para ESTE tipo."""
    return tuple(_PERGUNTAS_DA_PECA) + (pergunta_do_tamanho(tipo),)


def conferir_peca(imagem, fotos_ref=None, tipo=""):
    """A peça está certa como IMAGEM? (veredito, erro).

    veredito = {"aprovada": bool, "problemas": [str], "instrucao": str}

    `instrucao` é o texto que vai para a refação, escrito por quem VIU o
    defeito — e não uma regra genérica repetida mais uma vez. Foi a regra
    genérica que já falhou sete vezes no mesmo arquivo.

    Falha de conferência NÃO reprova a peça: sem chave ou sem rede, quem chama
    segue com o que tem. O contrário — dar por conferido sem ter olhado — é
    que não pode.
    """
    api_key = _chave_anthropic()
    if not api_key:
        return None, "ANTHROPIC_API_KEY não configurada."
    if not imagem:
        return None, "Sem imagem para conferir."
    if not fotos_ref:
        return None, "Sem foto de referência para comparar."

    conteudo = [{"type": "text", "text":
                 "A PRIMEIRA imagem é a peça de anúncio que acabou de ser "
                 "gerada. As seguintes são as FOTOS REAIS do produto."},
                _bloco_imagem(imagem)]
    # No máximo três fotos: a comparação é de forma e componentes, e a
    # quarta foto não acrescenta nada que a terceira já não mostre — mas
    # custa tokens em toda peça de toda geração.
    for _f in list(fotos_ref)[:3]:
        conteudo.append(_bloco_imagem(_f))
    conteudo.append({"type": "text", "text": (
        f"Tipo da peça: {tipo}" + "\n\n"
        "Responda estas quatro perguntas olhando a peça e comparando com "
        "as fotos:\n" + "\n".join(perguntas_da_peca(tipo)) + "\n\n"
        "SEJA CONSERVADOR. Só reprove o que uma pessoa olhando a peça "
        "chamaria de errado sem hesitar: uma palavra que não se lê inteira, "
        "um cartão pela metade, uma alça que existe na peça e não existe nas "
        "fotos. NÃO reprove por gosto, por enquadramento apertado que ainda "
        "mostra tudo, por cenário, por paleta, nem por diferença de "
        "iluminação ou de ângulo — a peça é uma composição nova de "
        "propósito, e o cenário não é o produto. Reprovar peça boa custa uma "
        "geração paga e atrasa quem está esperando.\n\n"
        "Em `problemas`, uma frase curta por defeito real, dizendo ONDE ele "
        "está. Em `instrucao`, escreva para o gerador o que fazer diferente "
        "— concreto e no imperativo, nomeando o defeito. Se estiver tudo "
        "certo, `aprovada: true`, `problemas: []` e `instrucao` vazia."
    )})

    esquema = {
        "name": "veredito_da_peca",
        "description": "O que está errado na peça, olhando-a junto das fotos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "aprovada": {"type": "boolean"},
                "problemas": {"type": "array", "items": {"type": "string"}},
                "instrucao": {"type": "string"},
            },
            "required": ["aprovada", "problemas", "instrucao"],
            "additionalProperties": False,
        },
    }
    try:
        cliente = anthropic.Anthropic(api_key=api_key)
        resposta = cliente.messages.create(
            model=MODELO_CONFERENCIA,
            max_tokens=900,
            timeout=120.0,
            tools=[esquema],
            tool_choice={"type": "tool", "name": "veredito_da_peca"},
            messages=[{"role": "user", "content": conteudo}],
        )
        for bloco in resposta.content:
            if getattr(bloco, "type", "") == "tool_use":
                return dict(bloco.input), ""
        return None, "A revisão não devolveu veredito."
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:160]}"


# ── 8 NA GALERIA NAO E 8 ENTREGUES ────────────────────────────────────────
#
# ACHADO NA CONVERSA REAL DO CHAT, 05/10. O dono escreveu "quais nao foram
# geradas" e o chat respondeu:
#
#     "Nenhuma deixou de ser gerada — as 8 estao na galeria."
#
# Era verdade e era inutil. Duas daquelas oito estavam com cartao vermelho
# na tela — "A peca saiu com defeito e nao consegui consertar em 2
# tentativa(s). Nao publique assim." — e uma terceira com "Texto com erro de
# portugues (...) em 3 tentativa(s)".
#
# O motivo esta em `chat_assistente.py`: o contexto da galeria listava
# `tipo` e mais nada. O chat nao enxergava veredito nenhum, entao contou
# slots. E contar slot como entrega e o defeito que o oitavo verificador
# existe para pegar: o sistema SABE e nao conta.
#
# UM DONO SO. A tela e o chat leem daqui. Duas contagens da mesma coisa
# passam a discordar — a questao e so quando.
def placar_do_lote(galeria, planejadas=0):
    """{planejadas, geradas, aprovadas, reprovadas, nao_conferidas, pendentes}.

    APROVADA e a peca cujas DUAS conferencias passaram: a do texto e a da
    imagem. Uma peca com portugues perfeito e a alca errada nao esta pronta,
    e uma com a arte certa e "PROFUNDITUDE" escrito tambem nao.

    NAO_CONFERIDA e diferente de reprovada, e a distincao importa: `ok is
    None` quer dizer que a conferencia nao rodou — a peca pode estar otima
    ou pessima, e ninguem olhou. Somar as duas esconderia justamente o caso
    em que o Studio nao sabe.
    """
    g = list(galeria or [])
    planejadas = int(planejadas or 0) or len(g)
    aprovadas = reprovadas = nao_conferidas = 0
    for item in g:
        _vereditos = [(item.get("peca") or {}).get("ok"),
                      (item.get("texto") or {}).get("ok")]
        _vistos = [v for v in _vereditos if v is not None]
        if any(v is False for v in _vereditos):
            reprovadas += 1
        elif not _vistos:
            nao_conferidas += 1
        else:
            aprovadas += 1
    return {
        "planejadas": planejadas,
        "geradas": len(g),
        "aprovadas": aprovadas,
        "reprovadas": reprovadas,
        "nao_conferidas": nao_conferidas,
        "pendentes": max(0, planejadas - len(g)),
    }


def frase_do_placar(placar):
    """A linha que a tela e o chat dizem sobre o lote. Uma redacao so.

    Ela NUNCA diz "8 de 8" quando ha reprovada: era essa a frase que fazia o
    dono e o chat discutirem sobre fatos diferentes.
    """
    p = placar or {}
    _ap, _rp = p.get("aprovadas", 0), p.get("reprovadas", 0)
    _nc, _pd = p.get("nao_conferidas", 0), p.get("pendentes", 0)
    _pl = p.get("planejadas", 0)
    partes = [f"{_ap} de {_pl} aprovada(s)"]
    if _rp:
        partes.append(f"{_rp} reprovada(s) — não publique")
    if _nc:
        partes.append(f"{_nc} não conferida(s)")
    if _pd:
        partes.append(f"{_pd} ainda não gerada(s)")
    return " · ".join(partes)


def peca_em_aviso(relato):
    """A frase que a tela mostra sobre a conferência da peça. "" quando não há.

    Separada do desenho da galeria porque o chat diz a mesma coisa, e duas
    redações da mesma regra discordam — a questão é só quando.
    """
    if not relato:
        return ""
    if relato.get("ok") is True:
        return ""
    _probs = "; ".join(relato.get("problemas") or [])
    if relato.get("ok") is None:
        return ("⚠️ **Esta peça NÃO foi conferida como imagem** "
                f"({(relato.get('erro') or '')[:80]}). Olhe antes de publicar.")
    return ("❌ **A peça saiu com defeito** e não consegui consertar em "
            f"{relato.get('rodadas', 1)} tentativa(s). Não publique assim."
            + (f" Achei: {_probs}" if _probs else ""))


def revisar_peca(img, tipo, fotos_ref=None, gerar=None, prompt_base="",
                 rodadas=2, aviso=None):
    """Olha a peça e refaz até sair certa. (imagem, relato).

    Gêmea de `revisar_texto`, e de propósito: mesma assinatura, mesmo formato
    de relato, mesma regra de que falha de leitura NÃO é aprovação.

    Três diferenças, e cada uma tem motivo:

    - RODA EM TODO TIPO, inclusive capa e ambientação. Alça a mais não é erro
      de português: a peça sem texto também pode trazer o produto errado, e
      era justamente a capa que saía com duas alças.
    - PRECISA DAS FOTOS. Sem elas não dá para julgar fidelidade, e julgar sem
      ter com o que comparar é o alarme falso mais caro que existe — então
      sem fotos ela não roda e diz isso.
    - DUAS RODADAS, e não três. Cada rodada aqui é uma geração inteira paga; a
      de texto troca a copy, que é barato. Duas rodadas gastam UMA refação.
    """
    def _diz(t):
        if aviso:
            try:
                aviso(t)
            except Exception:
                pass

    # ── SEM FOTO, A PECA SAIA SEM VEREDITO E SEM AVISO ──────────────────
    #
    # Dono, 01/10: "criacao de uma foto totalmente errada comparada ao produto
    # original anexado nas imagens do produto".
    #
    # Esta funcao devolvia `None` quando faltava foto de referencia, e
    # `peca_em_aviso(None)` devolve "". A peca ia para a galeria com a mesma
    # cara de uma peca CONFERIDA E APROVADA: sem veredito, sem aviso, sem
    # nada. E "sem foto" e exatamente o caso em que o produto tem mais chance
    # de sair errado, porque o motor o reconstroi a partir do texto.
    #
    # O limite silencioso de novo: o sistema sabia que nao tinha conferido e
    # nao contava. A diferenca entre "conferi e esta boa" e "nao consegui
    # conferir" e a diferenca entre publicar e nao publicar.
    if not img:
        return img, None
    if not fotos_ref:
        return img, {"ok": None, "rodadas": 0, "problemas": [],
                     "erro": "sem foto do produto para comparar — o motor "
                             "montou a peça a partir do texto"}

    # A MELHOR DAS DUAS, E NAO A ULTIMA.
    #
    # `img = nova_img` incondicional entregava a segunda peca mesmo quando ela
    # saia PIOR. Na revisao de texto isso e razoavel — a refacao recebe a copy
    # certa e tende a melhorar. Aqui nao: o gerador pode responder a "tire a
    # alca a mais" tirando as duas, e o Studio entregaria a pior das duas com
    # um aviso dizendo que esta errada. Isso e retrabalho fabricado pela
    # propria correcao.
    #
    # O criterio e a CONTAGEM de problemas vistos, que e o unico numero
    # comparavel que a conferencia devolve. Empate fica com a mais nova, que
    # e a que ao menos recebeu a instrucao.
    melhor_img, melhor_n = img, None
    problemas_1a = []
    for n in range(1, max(1, rodadas) + 1):
        _diz(f"Olhando a peça ({n}ª conferência)…")
        veredito, erro_conf = conferir_peca(img, fotos_ref, tipo)
        if erro_conf:
            return img, {"ok": None, "rodadas": n, "erro": erro_conf,
                         "problemas": problemas_1a}
        if veredito.get("aprovada"):
            return img, {"ok": True, "rodadas": n, "erro": "",
                         "problemas": problemas_1a}
        problemas = [str(p) for p in (veredito.get("problemas") or []) if p]
        problemas_1a = problemas_1a or problemas
        if melhor_n is None or len(problemas) <= melhor_n:
            melhor_img, melhor_n = img, len(problemas)
            melhores_problemas = problemas
        instrucao = (veredito.get("instrucao") or "").strip()
        if n >= rodadas or not gerar or not instrucao:
            return melhor_img, {"ok": False, "rodadas": n, "erro": "",
                                "problemas": melhores_problemas}
        _diz(f"Peça com defeito ({'; '.join(problemas)[:60]}). Refazendo…")
        # O TAMANHO TEM UM DONO SO, E A CRITICA NAO E ELE.
        #
        # `problemas` e `instrucao` sao escritos pela IA que OLHA a peca, e
        # ela escreve em portugues livre: "ocupando mais da metade do quadro".
        # Esse texto entra DEPOIS da regra de ocupacao, entao fala por ultimo
        # — e o gerador obedeceu a ele, com 30% a 45% escrito acima no mesmo
        # prompt (historico do Tigre, peca 7). Aqui a medida sai; o resto da
        # critica, que e o que importa, passa inteiro.
        _probs = [sem_medida_de_quadro(p) for p in problemas]
        _probs = [p for p in _probs if p.strip()]
        _instr = sem_medida_de_quadro(instrucao).strip()
        # SE NADA SOBROU, NAO SE PAGA UMA GERACAO PARA NAO PEDIR NADA.
        #
        # A guarda de `instrucao` vazia ja existe la em cima, mas ela roda
        # ANTES deste corte — ve o texto inteiro, nao o que resta dele.
        # Quando o unico defeito da peca e o enquadramento (o mais comum
        # nestas pecas), tudo e cortado e o pedido chegava em branco ao
        # gerador: dinheiro gasto para nao pedir coisa nenhuma, com o risco
        # conhecido de a refacao voltar com o produto trocado.
        #
        # Os problemas CRUS seguem para a tela em `melhores_problemas`:
        # quem trabalha le a medida e decide. O sistema e que para.
        if not _probs and not _instr:
            return melhor_img, {"ok": False, "rodadas": n, "erro": "",
                                "problemas": melhores_problemas}
        nova_img, erro_g = gerar(
            prompt_base + "\n\n"
            + "CORREÇÃO OBRIGATÓRIA — a versão anterior desta peça saiu com "
              "estes defeitos, e eles foram VISTOS na imagem gerada:\n"
            + "\n".join(f"- {p}" for p in _probs)
            + "\n\nO que fazer diferente agora: " + _instr)
        if erro_g or not nova_img:
            return melhor_img, {"ok": False, "rodadas": n, "erro": "",
                                "problemas": melhores_problemas}
        img = nova_img
    return melhor_img, {"ok": False, "rodadas": rodadas, "erro": "",
                        "problemas": melhores_problemas}


def revisar_tudo(img, tipo, fotos_ref=None, gerar=None, prompt_base="",
                 pedido="", aviso=None, dados_descricao=None):
    """Lê o texto E olha a peça. Devolve (imagem, relato_texto, relato_peca).

    A PORTA ÚNICA, e ela existe por um motivo medido: quatro lugares desta
    base escrevem bytes novos na galeria, e cada um fazia uma coisa diferente.
    Os dois que geram do zero — o "refazer" do chat e o botão de refazer da
    tela — não faziam NENHUMA das duas. Era o caminho mais usado no dia em que
    o dono passou dez rodadas corrigindo uma caneca à mão.

    A ORDEM É TEXTO PRIMEIRO, e é uma questão de dinheiro: trocar a copy é uma
    troca de string no prompt; refazer o quadro é uma geração paga. O barato
    antes do caro.

    O AJUSTE não usa esta porta, e isso não é esquecimento. Ele promete
    preservar o quadro, e o conserto de `revisar_peca` é recompor — as duas
    brigariam, e quem perde é quem pediu para mexer só numa palavra.
    """
    # O CADASTRO VIAJA ATE A REVISAO: e com ele que a correcao sabe que
    # "ALTURA 30mm" nao e dado do produto, e sim invencao do modelo lida de
    # volta na imagem.
    img, rel_txt, prompt_base = revisar_texto(
        img, tipo, pedido=pedido, gerar=gerar, prompt_base=prompt_base,
        aviso=aviso, dados_descricao=dados_descricao)
    # A BASE CORRIGIDA SEGUE PARA A SEGUNDA REVISAO.
    #
    # Sem isto, `revisar_peca` refazia a partir do prompt ORIGINAL — com a
    # copy errada que a revisao de texto acabou de gastar uma geracao para
    # tirar. A peca voltava com "Portatile" de novo, e a segunda correcao
    # desfazia a primeira.
    #
    # O prompt SAI do relato aqui: senao ele viajaria com a peca ate a galeria
    # e o disco, 24 mil caracteres por imagem, sem ninguem ler.
    img, rel_peca = revisar_peca(img, tipo, fotos_ref=fotos_ref, gerar=gerar,
                                 prompt_base=prompt_base, aviso=aviso)
    return img, rel_txt, rel_peca


def revisar_texto(img, tipo, pedido="", gerar=None, prompt_base="",
                  rodadas=3, aviso=None, dados_descricao=None):
    """Lê o texto escrito na imagem e refaz até sair certo.

    Devolve (imagem, relato, prompt_final) — TRÊS coisas, e a terceira é de
    propósito.

    POR QUE NÃO VAI DENTRO DO RELATO

    O prompt com que esta função terminou é o que a revisão seguinte precisa
    para refazer sem desfazer a correção da copy. Ele chegou a viajar dentro
    do `relato`, e o relato é guardado em `galeria[i]["texto"]`: são 24 mil
    caracteres por imagem, 200 mil numa geração de oito, redesenhados a cada
    tecla digitada. `revisar_tudo` tirava ele de lá — e o outro leitor,
    `ajustar_com_conferencia`, não tirava. Corrigir um leitor e esquecer o
    irmão é a Forma 1, e ela já custou caro nesta base.

    Com três valores, quem chama não tem como esquecer: ou desempacota, ou
    não compila.

    `gerar(prompt) -> (bytes, erro)` é como esta função pede outra imagem. Ela
    não conhece o gerador de propósito: a tela gera numa thread (para o
    WebSocket do Railway não cair no meio) e o chat gera direto, e as duas
    precisam da mesma revisão.

    `relato` = {"ok": True|False|None, "rodadas": n, "erros": str, "erro": str}
      ok=True   conferido e certo
      ok=False  conferido e errado — e não deu para consertar em `rodadas`
      ok=None   NÃO foi conferido (sem chave, sem rede, API fora). Não é
                aprovação: quem chama tem que dizer isso na tela.

    A refação agora é RECONFERIDA. Antes a segunda imagem valia sem ninguém
    ler: saía com o aviso "foi refeita, confira antes de publicar" mesmo
    quando continuava errada — e foi assim que uma peça com "Apretica newtona
    estético" chegou à tela do gestor, depois de passar pela revisão.
    """
    def _diz(t):
        if aviso:
            try:
                aviso(t)
            except Exception:
                pass

    if not img or not pode_ter_texto(tipo):
        return img, None, prompt_base

    erros_1a = ""
    for n in range(1, max(1, rodadas) + 1):
        _diz(f"Lendo o texto escrito na imagem ({n}ª leitura)…")
        veredito, erro_conf = conferir_texto(img, pedido)
        if erro_conf:
            return img, {"ok": None, "rodadas": n, "erro": erro_conf,
                         "erros": erros_1a}, prompt_base
        if not veredito.get("tem_texto") or veredito.get("correto"):
            return img, {"ok": True, "rodadas": n, "erro": "",
                         "erros": erros_1a}, prompt_base
        erros = (veredito.get("erros") or "").strip()
        erros_1a = erros_1a or erros
        certo = (veredito.get("texto_correto") or "").strip()
        if n >= rodadas or not gerar or not certo:
            return img, {"ok": False, "rodadas": n, "erro": "",
                         "erros": erros or erros_1a}, prompt_base
        _diz(f"Texto errado ({erros[:60]}). Refazendo com as palavras certas…")
        # A BASE MUDA JUNTO COM A COPY.
        #
        # Quem revisar esta peça depois — `revisar_peca` — vai refazer a
        # partir de um prompt, e esse prompt tem de ser o CORRIGIDO. Com o
        # original, a peça voltaria com a palavra inventada que acabou de
        # custar uma geração para sair: a segunda correção desfazendo a
        # primeira.
        # O TEXTO QUE O JUIZ LEU NA IMAGEM NAO PODE TRAZER NUMERO NOVO.
        #
        # ACHADO EM 05/10, peca 5. Sem copy do plano nao ha fonte de verdade
        # para o juiz comparar: ele TRANSCREVE o que ve, so arrumando a
        # grafia. As medidas que o Gemini inventou na primeira tentativa —
        # ALTURA 30mm, PROFUNDIDADE 25mm, LARGURA INTERNA 17mm, LARGURA 35mm
        # — viraram o "TEXTO EXATO (copie letra por letra)" da segunda, num
        # bloco que diz de si mesmo "acima de qualquer outra instrucao de
        # texto". O cadastro, no MESMO prompt, dizia "Medidas EXATAS (use
        # esses numeros, nao invente): 12x14".
        #
        # O sistema estava lavando a invencao do modelo em ordem do Studio.
        # Esta linha e a barreira: numero com unidade que o cadastro nao
        # sustenta nao vira ordem, venha de onde vier.
        # O JUIZ DEVOLVE UMA STRING COM VARIAS LINHAS, e nao uma lista.
        #
        # Filtrar a string inteira como um bloco so jogava fora a copy
        # corrigida completa por causa de UMA medida inventada numa linha —
        # a guarda pegou isso. Ela e partida pelo MESMO criterio que
        # `bloco_texto_exato` usa (`_INICIO_DE_BLOCO`), senao sao dois jeitos
        # de contar bloco e eles passam a discordar.
        _blocos_certo = [l.strip() for l in str(certo).splitlines() if l.strip()]
        _certo_limpo, _num_fora = copy_sem_medida_inventada(
            _blocos_certo or [str(certo)], dados_descricao)
        if _num_fora:
            _diz("Removi {} bloco(s) com medida que o cadastro não tem."
                 .format(len(_num_fora)))
        if not _certo_limpo:
            # Sem nada que o cadastro sustente, refazer so repetiria a
            # invencao. A peca para aqui, reprovada e dita em voz alta.
            return img, {"ok": False, "rodadas": n, "erro": "",
                         "erros": (erros or erros_1a)
                         + " · a correção trazia medida que o cadastro não "
                           "tem, e foi descartada"}, prompt_base
        prompt_base = trocar_texto_exato(prompt_base, _certo_limpo)
        nova_img, erro_g = gerar(prompt_base)
        if erro_g or not nova_img:
            return img, {"ok": False, "rodadas": n, "erro": "",
                         "erros": erros or erros_1a}, prompt_base
        img = nova_img
    return img, {"ok": False, "rodadas": rodadas, "erro": "", "erros": erros_1a}, prompt_base


def texto_em_aviso(relato):
    """A frase que a tela mostra sobre a revisão de texto. "" quando não há.

    Separada do desenho da galeria porque o chat diz a mesma coisa, e duas
    redações da mesma regra discordam — a questão é só quando.
    """
    if not relato:
        return ""
    _e = (relato.get("erros") or "").strip()
    if relato.get("ok") is True:
        return ""
    if relato.get("ok") is None:
        return ("⚠️ **O texto desta imagem NÃO foi conferido** "
                f"({(relato.get('erro') or '')[:80]}). Leia antes de publicar.")
    return ("❌ **Texto com erro de português** e não consegui consertar em "
            f"{relato.get('rodadas', 1)} tentativa(s). Não publique assim."
            + (f" Erros: {_e}" if _e else ""))


def ajustar_com_conferencia(imagem, instrucao, tipo=None, tentativas=2,
                            aviso=None, referencias=None,
                            dados_descricao=None):
    """Ajusta, confere o pedido, e depois confere o PORTUGUÊS do que ficou.

    As duas conferências são perguntas diferentes: `conferir_ajuste` responde
    "o que ele pediu aconteceu?", e a revisão de texto responde "o que está
    escrito na peça existe em português?". Só a primeira rodava aqui — e o
    ajuste fino redesenha a peça inteira, texto incluído. Uma peça que chegou
    correta ao ajuste saía dele com palavra inventada, sem ninguém ler.
    """
    img, relato = _ajustar_bruto(imagem, instrucao, tipo=tipo,
                                 tentativas=tentativas, aviso=aviso,
                                 referencias=referencias)
    if not img or not pode_ter_texto(tipo):
        return img, relato
    if img is imagem or img == imagem:
        # O ajuste nao saiu e a imagem voltou como estava. Revisar o texto dela
        # aqui significaria REDESENHAR a peca que o relato acabou de prometer
        # que ficou intacta — e ela ja foi revisada quando foi gerada.
        return img, relato

    _refs_fix = [r for r in (referencias or []) if r]

    def _refazer(prompt_corrigido, _t=tipo):
        return gerar_imagem_ia(prompt_corrigido, [img] + _refs_fix,
                               tipo=_t or "")

    img_ok, rel_txt, _ = revisar_texto(
        img, tipo,
        dados_descricao=dados_descricao,
        pedido=instrucao,
        gerar=_refazer,
        prompt_base=montar_prompt_ajuste_fino(
            "Corrija APENAS a ortografia do texto escrito na peça. Mantenha "
            "idêntico o produto, o enquadramento, as cores e o layout.", tipo),
        rodadas=2,
        aviso=aviso,
    )
    relato["texto"] = rel_txt

    # QUALQUER ETAPA QUE REGERE PIXEL INVALIDA A APROVACAO ANTERIOR.
    #
    # `revisar_texto` pode REDESENHAR a peca para consertar o portugues. O
    # juiz do pedido olhou a imagem de ANTES dessa regeracao e disse "feito".
    # A imagem que vai para a galeria e OUTRA, e ninguem a julgou: o relato
    # dizia `ok: True` sobre uma imagem que o conferidor nunca viu.
    #
    # A analise externa de 01/10 nomeou isto como invariavel do sistema, e
    # ela esta certa: "nenhuma imagem pode ser chamada de ajustada porque uma
    # geracao terminou; so porque o pedido que originou aquela geracao foi
    # conferido na imagem que efetivamente sera salva".
    #
    # So reconfere quando a imagem MUDOU — `revisar_texto` devolve a mesma
    # quando nao houve o que corrigir, e julgar de novo seria uma chamada
    # paga por nada.
    if relato.get("ok") and img_ok is not None and img_ok != img:
        _v2, _e2 = conferir_ajuste(imagem, img_ok, instrucao)
        if _e2 or not _v2:
            # Nao consegui conferir a imagem FINAL. Ela nao pode sair como
            # aprovada: `ok=None` e o estado "ninguem olhou", e a tela ja
            # sabe dizer isso.
            relato["ok"] = None
            relato["erro"] = (_e2 or "não consegui conferir a imagem final")
        elif not (_v2.get("feito")
                  and not _v2.get("houve_colateral")
                  and not _v2.get("produto_alterado_fora_do_pedido")):
            relato["ok"] = False
            relato["falta"] = ((_v2.get("o_que_falta") or "").strip()
                               or "a correção do texto desfez o ajuste")
            relato["colateral"] = ((_v2.get("produto_colateral")
                                    or _v2.get("colateral") or "").strip())
            relato["produto_alterado_fora_do_pedido"] = bool(
                _v2.get("produto_alterado_fora_do_pedido")
                or _v2.get("houve_colateral"))
            return img, relato      # a imagem que o juiz TINHA aprovado
    return img_ok, relato


def _ajustar_bruto(imagem, instrucao, tipo=None, tentativas=2,
                   aviso=None, referencias=None):
    """Ajusta, confere e — se não saiu — tenta de novo com a crítica na mão.

    Devolve (bytes_finais, relato). `relato` é o que se conta ao colaborador:
    o que foi feito, o que não foi, e o que mudou sem ter sido pedido. Ele
    nunca mente por omissão — quando as tentativas acabam sem sucesso, a
    imagem volta assim mesmo, com o relato dizendo o que falta.

    Entregar errado calado é o que estava travando o processo. Entregar errado
    dizendo o que faltou é uma rodada perdida; entregar errado em silêncio são
    três, mais a ida da equipe para o ChatGPT.

    `aviso` é uma função de um argumento para mostrar progresso na tela.
    """
    def _diz(txt):
        if aviso:
            try:
                aviso(txt)
            except Exception:
                pass

    atual = imagem
    pedido = instrucao
    historico = []

    for n in range(1, max(1, tentativas) + 1):
        _diz(f"Ajustando (tentativa {n} de {tentativas})…")
        # A imagem ATUAL primeiro (é ela que está sendo editada), e depois as
        # fotos de REFERÊNCIA do produto.
        #
        # Antes só a atual ia. "Replique o padrão desta imagem que anexei" era
        # impossível de atender: a referência ficava na mão do colaborador e
        # chegava aqui como descrição em texto — e descrever um layout em
        # palavras com fidelidade suficiente para o modelo copiá-lo não
        # funciona. Foram quatro tentativas sem NENHUMA mudança na imagem antes
        # de alguém abrir este arquivo.
        _refs = [atual] + [r for r in (referencias or []) if r and r != atual]
        nova, erro = gerar_imagem_ia(montar_prompt_ajuste_fino(pedido, tipo),
                                     _refs, tipo=tipo or "")
        if erro or not nova:
            return atual, {"ok": False, "tentativas": n,
                           "erro": erro or "o gerador não devolveu imagem.",
                           "falta": "", "colateral": "", "historico": historico}

        _diz(f"Conferindo o resultado (tentativa {n})…")
        veredito, erro_conf = conferir_ajuste(atual, nova, instrucao)

        # Sem conferência, a imagem nova vale — ela pode estar certa, e
        # descartá-la por causa de uma falha nossa seria pior. Mas o relato diz
        # que ninguém olhou, para o colaborador saber que precisa olhar.
        if erro_conf:
            return nova, {"ok": None, "tentativas": n, "erro": erro_conf,
                          "falta": "", "colateral": "", "historico": historico}

        historico.append(veredito)
        # TRES PERGUNTAS, TRES BOOLEANOS — E O PEDIDO MANDA NOS TRES.
        #
        # Era `feito and not produto_alterado`, e `produto_alterado` queria
        # dizer "o produto mudou", sem olhar se tinham PEDIDO que mudasse.
        # Pedido de "cor interior preta" cumprido virava fracasso.
        _dano_produto = bool(veredito.get("produto_alterado_fora_do_pedido"))
        _colateral = bool(veredito.get("houve_colateral"))
        if veredito.get("feito") and not _colateral and not _dano_produto:
            return nova, {"ok": True, "tentativas": n, "erro": "",
                          "falta": "", "saiu": veredito.get("o_que_saiu", ""),
                          "colateral": veredito.get("colateral", ""),
                          "historico": historico}

        # Pedido atendido MAS o produto mudou onde ninguém mandou não é
        # sucesso — é a peça errada com a cor certa. Foi o urso de strass: o
        # veredito disse que o corpo tinha ficado liso, e a tela anunciou
        # "✅ atualizada".
        #
        # A próxima tentativa parte da imagem ORIGINAL e leva o dano por
        # escrito. A instrução nomeia o que PRESERVAR, e nunca manda desfazer
        # o pedido: preservar é o complemento do pedido, não o contrário.
        if _dano_produto:
            _dano = (veredito.get("produto_colateral")
                     or veredito.get("colateral")
                     or "o produto foi alterado onde não foi pedido").strip()
            _diz("O produto mudou onde não foi pedido — refazendo.")
            pedido = (f"{instrucao.strip()}\n\n"
                      f"ATENÇÃO — a tentativa anterior cumpriu o pedido, mas "
                      f"mudou no produto uma coisa que NÃO foi pedida: "
                      f"{_dano}. Faça de novo exatamente a alteração pedida "
                      f"acima e preserve essa característica como está na "
                      f"imagem original, com a mesma textura, o mesmo "
                      f"acabamento e os mesmos detalhes de superfície.")
            continue

        # Colateral FORA do produto — cenário, fundo, enquadramento, texto.
        # Mesmo tratamento: volta à original e nomeia o que não podia mudar.
        if _colateral:
            _col = (veredito.get("colateral")
                    or "algo mudou sem ter sido pedido").strip()
            _diz("Mudou algo que não foi pedido — refazendo.")
            pedido = (f"{instrucao.strip()}\n\n"
                      f"ATENÇÃO — a tentativa anterior mudou, sem ter sido "
                      f"pedido: {_col}. Faça SOMENTE a alteração pedida "
                      f"acima e deixe esse ponto como está na imagem "
                      f"original.")
            continue

        # Nao saiu. A critica vira a instrucao da proxima tentativa — e a
        # partir da imagem ORIGINAL, nao da tentativa falha: encadear falha
        # sobre falha afasta o resultado do produto a cada rodada.
        falta = (veredito.get("o_que_falta") or "").strip()
        pedido = (f"{instrucao.strip()}\n\n"
                  f"A tentativa anterior não conseguiu. O que ainda precisa "
                  f"acontecer: {falta}") if falta else instrucao

    ultimo = historico[-1] if historico else {}
    # DUAS DERROTAS DIFERENTES, E A MENSAGEM TEM DE SABER QUAL FOI.
    #
    # "produto errado é pior que peça sem correção" foi dito ao dono cinco
    # vezes num pedido em que o produto só mudou NAQUILO QUE ELE PEDIU. Dizer
    # a causa errada custa a próxima hora de quem for procurar.
    _estragou = bool(ultimo.get("produto_alterado_fora_do_pedido")
                     or ultimo.get("houve_colateral"))
    return atual, {"ok": False, "tentativas": tentativas, "erro": "",
                   "falta": ((ultimo.get("o_que_falta") or "").strip()
                             if not _estragou else
                             "a alteração pedida só saiu junto com mudanças "
                             "que ninguém pediu, então a imagem foi mantida "
                             "como estava"),
                   "saiu": ultimo.get("o_que_saiu", ""),
                   "colateral": ((ultimo.get("produto_colateral")
                                  or ultimo.get("colateral") or "").strip()),
                   "produto_alterado_fora_do_pedido": _estragou,
                   "historico": historico}


def relato_em_texto(num, relato):
    """A linha que o colaborador lê. Nunca diz "pronto" sem ter conferido.

    O veredito do português entra em QUALQUER desfecho: ajuste que deu certo
    também sai com palavra inventada, e era justamente o caso em que ninguém
    ia olhar de novo.
    """
    _txt = texto_em_aviso(relato.get("texto"))
    _sufixo = f"\n   {_txt}" if _txt else ""
    return _relato_base(num, relato) + _sufixo


def _relato_base(num, relato):
    if relato.get("erro") and relato.get("ok") is False:
        return f"⚠️ Imagem {num}: não consegui gerar — {relato['erro']}"
    if relato.get("ok") is None:
        return (f"⚠️ Imagem {num}: ajuste aplicado, mas **não consegui "
                f"conferir** o resultado ({relato.get('erro','')}). "
                f"Confira você antes de usar.")
    colateral = (relato.get("colateral") or "").strip()
    if relato.get("ok"):
        txt = f"✅ Imagem {num}: {relato.get('saiu') or 'ajuste aplicado'}"
        if relato["tentativas"] > 1:
            txt += f" (na {relato['tentativas']}ª tentativa)"
        if colateral:
            txt += f"\n   ⚠️ Mudou também, sem ter sido pedido: {colateral}"
        return txt
    # ── A FALHA NÃO DEVOLVE A LIÇÃO DE CASA PARA QUEM PEDIU ─────────────
    #
    # Esta mensagem dizia: "Tente descrever de outro jeito, dizendo o que
    # DEVE existir em vez do que não deve". Em 25/09 a colaboradora recebeu
    # isso em quatro das sete peças, depois de ter descrito cada defeito com
    # clareza — "a frase está cortada nas laterais", "o material está errado,
    # é veludo e acrílico". O pedido dela estava certo; quem não conseguiu
    # traduzir foi o sistema, e a conta voltava para ela.
    #
    # E o texto de `falta` vem do conferidor, escrito para o GERADOR: sai
    # cheio de "6% da base do quadro" e "grade 2x2". Na tela de quem
    # trabalha, isso é ruído — o dono pediu em 25/09 que a comunicação seja
    # didática e simples.
    falta = (relato.get("falta") or "").strip()
    _pedaco = f" O que faltou: {falta}" if falta and len(falta) < 180 else ""
    if relato.get("produto_alterado_fora_do_pedido"):
        # A TERCEIRA TENTATIVA É DELE, E NÃO MINHA.
        #
        # Dono, 29/09: "o chat vai conseguir realizar o que hoje ele informa
        # não conseguir em 2 ou mais tentativas?".
        #
        # São 2 tentativas fixas (`ajustar_com_conferencia`, tentativas=2), e
        # quando o produto muda o sistema ENCERRAVA: oferecia refazer do zero
        # ou deixar como está. Quando o ajuste apenas NÃO SAI, ele diz "me
        # peça de novo e eu tento por outro caminho" — dá para insistir.
        #
        # Exatamente no caso mais difícil, o sistema tirava do colaborador a
        # opção de insistir, e a decisão de parar era minha, escrita no
        # código. O número de tentativas aparece, e insistir volta a ser uma
        # das saídas.
        # E A FRASE MUDOU, PORQUE A ANTIGA MENTIA SOBRE A CAUSA.
        #
        # Ela dizia "toda vez o produto mudava junto". No pedido de 01/10 o
        # produto mudou NAQUILO QUE O DONO PEDIU — a cor interior — e ele
        # leu cinco vezes que o produto tinha mudado, como se fosse defeito.
        # Agora a frase diz o que de fato impede: veio junto o que ninguém
        # pediu.
        _n_tent = relato.get("tentativas") or 2
        _col_rb = (relato.get("colateral") or "").strip()
        _por_que = (f" Veio junto, sem ter sido pedido: {_col_rb}."
                    if _col_rb and len(_col_rb) < 160 else "")
        return (f"❌ Imagem {num}: a alteração não foi aplicada. Em "
                f"{_n_tent} tentativa(s) ela veio acompanhada de mudanças "
                f"que ninguém pediu, então mantive a versão original."
                f"{_por_que}\n"
                f"   Três saídas, e a escolha é sua: **me peça de novo** "
                f"(cada rodada parte da imagem original, não da tentativa "
                f"falha), **refazer a peça do zero** com esse ajuste desde o "
                f"começo, ou **deixar como está**.")
    return (f"❌ Imagem {num}: não consegui em {relato['tentativas']} "
            f"tentativa(s), e a imagem ficou como estava.{_pedaco}\n"
            f"   Não precisa reescrever nada — me peça de novo e eu tento "
            f"por outro caminho.")


def _drive_service():
    """Mantido por compatibilidade — delega para o módulo gdrive."""
    import gdrive
    return gdrive.service()


# Palavras que descrevem QUALQUER produto e não identificam nenhum. Buscar
# pasta por uma delas foi o que mandou as imagens do "Globo Preto Portátil"
# para a pasta da "Lixeira Aramada 12 litros Preto": as duas são pretas.
PALAVRAS_GENERICAS = {
    "preto", "preta", "branco", "branca", "cinza", "prata", "dourado",
    "dourada", "azul", "verde", "vermelho", "vermelha", "amarelo", "amarela",
    "rosa", "roxo", "roxa", "marrom", "bege", "transparente", "colorido",
    "colorida", "grande", "pequeno", "pequena", "medio", "media", "litros",
    "litro", "cm", "mm", "kit", "com", "sem", "para", "de", "da", "do", "e",
    "em", "por", "novo", "nova", "portatil", "portátil",
}


def _palavras_que_identificam(nome):
    """As palavras do nome que servem para achar ESTE produto, e não qualquer um."""
    fora = []
    for p in str(nome or "").split():
        limpa = "".join(c for c in p if c.isalnum())
        if len(limpa) >= 4 and limpa.lower() not in PALAVRAS_GENERICAS:
            fora.append(limpa)
    return fora


def buscar_pasta_produto(nome_produto, codigo, pasta_pai_id, diagnostico=None):
    """Busca a pasta deste produto. Lista de (id, name), vazia quando não há.

    A ORDEM É A DA CERTEZA, E NÃO A DA CONVENIÊNCIA
    -----------------------------------------------
    1. nome exato "[Nome] - [Código]"
    2. o CÓDIGO, quando existe — ele é único, e é para isso que ele serve
    3. e só sem código: as palavras do nome que identificam o produto

    O passo 3 era o único fallback, e buscava por CADA uma das duas primeiras
    palavras, devolvendo a primeira pasta que casasse. "Globo **Preto**
    Portátil" casou com "Lixeira Aramada 12 litros **Preto**", e as imagens do
    globo iam ser salvas na pasta da lixeira — com o código do globo
    preenchido na tela, e sem ninguém ser avisado.

    Cor não identifica produto. Código identifica. Com código preenchido, a
    busca por palavra não acontece: melhor não achar pasta (e criar a certa)
    do que achar a pasta errada.

    Quando `diagnostico` recebe um dict, uma falha da API é registrada lá em
    vez de virar lista vazia — quem chama precisa distinguir "não existe" de
    "não consegui verificar", porque no primeiro caso criar a pasta é certo e
    no segundo cria duplicata.
    """
    import gdrive

    def _buscar(condicao):
        q = (f"'{pasta_pai_id}' in parents and "
             f"mimeType='application/vnd.google-apps.folder' "
             f"and {condicao} and trashed=false")
        achados = gdrive.listar(q, diagnostico=diagnostico)
        if diagnostico is not None and diagnostico.get("erro"):
            return None
        return [(f["id"], f["name"]) for f in (achados or [])]

    nome_exato = f"{nome_produto} - {codigo}".strip(" -")
    if nome_exato:
        r = _buscar(f"name='{nome_exato}'")
        if r is None:
            return []
        if r:
            return r

    # O código é único. Com ele em mãos, nada mais precisa ser adivinhado.
    cod = str(codigo or "").strip()
    if cod:
        r = _buscar(f"name contains '{cod}'")
        if r is None:
            return []
        return r

    # Sem código: as palavras que identificam, e TODAS elas juntas. Uma só
    # ("Preto") acha o produto de outra pessoa.
    palavras = _palavras_que_identificam(nome_produto)[:2]
    if palavras:
        condicao = " and ".join(f"name contains '{p}'" for p in palavras)
        r = _buscar(condicao)
        if r is None:
            return []
        return r
    return []


def criar_pasta_produto(nome_pasta, pasta_pai_id):
    """Cria nova pasta no Drive. Retorna (id, erro)."""
    import gdrive
    return gdrive.criar_pasta(nome_pasta, pasta_pai_id)


def upload_para_pasta(imagem_bytes, nome_arquivo, pasta_id):
    """Faz upload de imagem para pasta específica. Retorna (link, erro)."""
    import gdrive
    # O tipo vem dos bytes, nao de um valor fixo: depois da compressao a peca
    # pode ter saido em JPEG, e o Drive gravaria um JPEG rotulado como PNG.
    info, err = gdrive.upload(imagem_bytes, nome_arquivo, pasta_id,
                              mimetype=_detectar_mime(imagem_bytes))
    if err:
        return None, err
    if info.get("na_raiz"):
        import streamlit as _st_av
        _st_av.warning("⚠️ " + info.get("aviso", ""))
    return info.get("webViewLink"), None


def salvar_prompts_na_pasta(pasta_id, nome_produto, quando=None):
    """Sobe o histórico de prompts deste produto para a pasta dele. (nome, erro).

    POR QUE AUTOMÁTICO, JUNTO COM AS IMAGENS
    ----------------------------------------
    O dono: *"ele precisa salvar automaticamente quando o colaborador clicar
    em salvar as imagens — isso evita do colaborador esquecer de salvar esse
    prompt também"*.

    Um passo a mais para quem salva é um passo que vai ser esquecido, e o
    esquecimento só aparece meses depois, quando alguém procura o prompt de
    um caso específico e ele não está lá. O arquivo entra na MESMA pasta das
    imagens: quem achar a imagem acha o prompt dela, sem precisar saber que
    existe um lugar separado.

    NUNCA PODE DERRUBAR O SALVAMENTO DAS IMAGENS. As imagens são o trabalho;
    o prompt é o rastro. Quem chama trata o erro como recado, não como falha.
    """
    try:
        import log_imagem as _li
        import comparar_prompt as _cmp
        linhas = _li.ler(500)
        nome = str(nome_produto or "").strip()
        if nome:
            linhas = [l for l in linhas
                      if str(l.get("produto", "")).strip() == nome]
        if not _cmp.cadeias(linhas):
            return "", "nenhum prompt registrado para este produto"
        texto = _cmp.relatorio_txt(linhas)
    except Exception as e:
        return "", f"{type(e).__name__}: {str(e)[:120]}"

    # O NOME CARREGA A DATA, e é de propósito: salvar de novo amanhã não pode
    # sobrescrever o arquivo de hoje. O histórico de um produto é a sequência
    # das rodadas dele, e uma rodada apagando a anterior seria o contrário
    # do que isto existe para fazer.
    # O RELÓGIO DO CONTAINER É UTC (CLAUDE.md). Sem o fuso, um arquivo
    # salvo às 22h daqui sai com a data do dia seguinte no nome.
    from datetime import datetime as _dt
    try:
        import placar_core as _pc
        _agora = quando or _dt.now(_pc.FUSO)
    except Exception:
        _agora = quando or _dt.now()
    nome_arq = ("prompts - "
                + "".join(c if c.isalnum() or c in " -_" else "_"
                          for c in (nome_produto or "produto"))[:40].strip()
                + f" - {_agora.strftime('%Y-%m-%d %H%M')}.txt")

    # O `import` TAMBÉM PRECISA ESTAR COBERTO. `gdrive.upload` já devolve o
    # erro em vez de levantar, mas o import dele não: uma dependência do
    # Google fora do lugar levantaria AQUI, depois de as imagens já terem
    # subido — o pior ponto possível para uma exceção nascer.
    try:
        import gdrive
        info, err = gdrive.upload(texto.encode("utf-8"), nome_arq, pasta_id,
                                  mimetype="text/plain")
    except Exception as e:
        return "", f"{type(e).__name__}: {str(e)[:120]}"
    if err:
        return "", err
    return nome_arq, ""


def criar_zip_galeria(galeria, nome_produto):
    """Cria ZIP em memória com todas as imagens da galeria. Retorna bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for g in galeria:
            nome_arquivo = (f"{nome_produto}_{g['tipo'][:30]}"
                            f".{extensao_de(g['bytes'])}")
            nome_arquivo = "".join(c if c.isalnum() or c in "._- " else "_" for c in nome_arquivo)
            zf.writestr(nome_arquivo, g["bytes"])
    buf.seek(0)
    return buf.read()


# ── INTERFACE PRINCIPAL ────────────────────────────────────────────────────────

def _testar_gemini_api():
    """Testa a API Gemini Image Generation com um prompt mínimo (generateContent API).
    Usa o mesmo modelo e endpoint da geração real para diagnóstico preciso.
    Retorna dict com resultados.
    """
    import time as _t_diag
    MODELO = "gemini-3.1-flash-image"

    api_key = _get_gemini_api_key()
    resultados = {"api_key": "configurada" if api_key else "NÃO CONFIGURADA"}

    if not api_key:
        return {"erro_geral": "GEMINI_API_KEY não configurada nas secrets do Railway."}

    headers_teste = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    body_teste = {
        "contents": [{"role": "user", "parts": [
            {"text": "A small red circle on a white background. Simple and minimal."}
        ]}],
        "generationConfig": {
            "responseModalities": ["IMAGE", "TEXT"],
        },
    }

    t0 = _t_diag.time()
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO}:generateContent"
        r = requests.post(url, json=body_teste, headers=headers_teste, timeout=25,
                          proxies={"http": None, "https": None})
        ms = int((_t_diag.time() - t0) * 1000)
        if r.status_code == 200:
            dados = r.json()
            # Verifica imagem no formato generateContent
            img_data = ""
            for candidate in dados.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    inline = part.get("inlineData") or part.get("inline_data", {})
                    if inline and inline.get("data"):
                        img_data = inline["data"]
                        break
                if img_data:
                    break
            tem_imagem = bool(img_data)
            resultados[MODELO] = {"ok": True, "ms": ms, "tem_imagem": tem_imagem}
        else:
            try:
                err = r.json().get("error", {})
                msg = f"HTTP {r.status_code} — {err.get('status','')} — {err.get('message','')[:250]}"
            except Exception:
                msg = f"HTTP {r.status_code} — {r.text[:250]}"
            resultados[MODELO] = {"ok": False, "ms": ms, "erro": msg}
    except Exception as e:
        resultados[MODELO] = {"ok": False, "ms": int((_t_diag.time() - t0)*1000), "erro": str(e)}
    return resultados


def consumir_comandos_do_chat(usuario_logado=""):
    """Executa o que o Assistente IA deixou na fila. Roda em QUALQUER modo.

    ONDE ISTO ESTAVA, E POR QUE NÃO FUNCIONAVA
    ------------------------------------------
    Este bloco vivia dentro do `else` do seletor de modo da aba Imagem — o
    ramo de "1 imagem específica" e "Selecionar". No modo **✏️ Ajuste Fino**,
    que é o outro ramo, ele simplesmente não era alcançado.

    O efeito para quem usa: o chat aceitava o pedido, respondia "🔁 Imagem 1
    será refeita do zero", e a fila ficava parada em `session_state` para
    sempre. Nenhum erro, nenhum aviso — e a colaboradora pediu, conferiu,
    pediu de novo, e o assistente confirmou que a imagem estava igual sem
    conseguir dizer por quê. Quatro rodadas.

    Uma tela em que o chat responde depende do chat ser ouvido em toda ela.
    Por isso agora é uma função só, chamada no começo da página, antes de
    qualquer ramo.
    """
    galeria = st.session_state.get("img_galeria") or []
    if not galeria:
        # Sem galeria não há o que ajustar nem refazer. A fila de "refazer
        # todas" não depende dela e por isso é lida antes de sair.
        if st.session_state.get("chat_refazer_todas") is None:
            st.session_state.pop("chat_refazer_imagem", None)
            st.session_state.pop("chat_img_pendente", None)
            return


    # ── COMANDOS PENDENTES DO ASSISTENTE IA ──────────────────────────────
    # O Assistente IA envia comandos de correção. Tratamos sempre como
    # Ajuste Fino (NÃO aplica PADRAO_VISUAL nem INSTRUCAO_COMPOSICAO).
    _refazer = st.session_state.pop("chat_refazer_todas", None)
    if _refazer is not None:
        _inst = (_refazer or {}).get("instrucao", "").strip()
        if _inst:
            _cfg_rf = dict(config_da_geracao())
            _cfg_rf["instrucoes_extras"] = (
                (_cfg_rf.get("instrucoes_extras", "") + "\n\n" + _inst).strip()
            )
            st.session_state["img_triagem_config"] = _cfg_rf
        st.session_state["img_galeria"] = []
        st.session_state.pop("img_confirma_descarte", None)
        try:
            import log_imagem
            log_imagem.registrar("refazer_todas_aplicado", _inst,
                                 resultado="galeria descartada")
        except Exception:
            pass
        st.rerun()

    # ── REFAZER uma imagem, pedido pelo chat ─────────────────────────
    #
    # Diferente do ajuste: aqui a imagem nasce de novo, com a composição
    # definida no prompt de geração. O ajuste preserva o resto do quadro e
    # por isso não recompõe — e devolvia a imagem intacta sem erro nenhum,
    # o que custou quatro rodadas até alguém abrir este arquivo.
    refazer_pend = st.session_state.pop("chat_refazer_imagem", [])
    if refazer_pend:
        _fotos_rf = st.session_state.get("img_fotos_originais") or []
        _cfg_rf = config_da_geracao()
        _dados_rf = st.session_state.get("img_dados_descricao") or {}
        _nome_rf = _cfg_rf.get("nome_produto", "")
        _msgs_rf, _mudou_rf = [], False
        for _c in refazer_pend:
            _i = int(_c.get("num", 1)) - 1
            if _i < 0 or _i >= len(galeria):
                _msgs_rf.append(f"⚠️ Imagem {_i + 1} não existe.")
                continue
            # A recusa vale so quando NAO HA foto de produto nenhuma. Ter a
            # marca ligada com fotos na mao era o caso falso que travava a
            # colaboradora: o Studio tinha tudo de que precisava e dizia que
            # nao tinha.
            if not _fotos_rf:
                # Dizer "não dá" é o que faltava. Gerando do zero com a arte
                # errada como referência, ela voltava idêntica — e o
                # assistente anunciava sucesso em cima disso.
                _msgs_rf.append(
                    "⚠️ **Preciso das fotos do produto para refazer do zero.** "
                    "O Studio não tem nenhuma nesta sessão — e gerar a partir "
                    "da própria arte devolve a arte.\n\n"
                    "Suba as fotos do produto em **Fotos de referência do "
                    "produto**, aqui mesmo na aba Imagem, e me peça de novo. "
                    "Para mexer só num ponto sem refazer, o Ajuste Fino "
                    "funciona sem elas.")
                break
            _tp = tipo_para_gerar(galeria[_i])
            _ins = (_c.get("instrucao") or "").strip()
            # A PECA DE ANTES, guardada antes de ser sobrescrita: e com ela
            # que o juiz vai comparar para dizer se o pedido aconteceu.
            _antes_rf = galeria[_i].get("bytes")
            # A REFERÊNCIA ANEXADA NO CHAT, quando houver.
            #
            # Ela chegava só na fila do AJUSTE. No refazer, o motor recebia a
            # frase e as fotos do produto, e a imagem de exemplo que a pessoa
            # anexou para mostrar o que queria ficava no chat.
            #
            # ORDEM IMPORTA, e é a mesma do ajuste: a referência primeiro, as
            # fotos do produto depois. As fotos são a trava de fidelidade; a
            # referência é o que se pede.
            _ref_ped_rf = [b for b in (_c.get("referencia") or []) if b]
            _fotos_desta = _ref_ped_rf + list(_fotos_rf)
            _prompt = prompt_para_regerar(_tp, _ins, _dados_rf, _nome_rf)
            _r = {"img": None, "erro": None, "done": False}
            _b = st.progress(0.0, text=f"Refazendo a Imagem {_i + 1}…")
            import threading as _th_rf, time as _tm_rf
            # O TIPO E AS REFERENCIAS DE LAYOUT VAO JUNTO — e nao iam.
            #
            # ACHADO EM PRODUCAO, 05/10. Este Thread passava TRES argumentos:
            # prompt, fotos e o dicionario de resultado. O `tipo` ficava ""
            # e as referencias de layout ficavam None, enquanto o laco da
            # geracao (`imagem.py` ~9867) passa os tres por kwargs.
            #
            # DOIS ESTRAGOS, e os dois apareceram no teste do dono:
            #
            # 1. `ref_layout_do_tipo` nao casava referencia nenhuma, entao a
            #    peca refeita vinha SEM o padrao aprovado da empresa. Foi por
            #    isso que a peca 6, refeita pelo chat, voltou com os cartoes
            #    nos quatro cantos em vez da coluna unica da peca 3 — e o
            #    dono teve de descobrir isso sozinho, em tres rodadas.
            #
            # 2. `numero_do_tipo("")` devolve "", e o registro saiu com
            #    "peca ?" e `tipo:` vazio. O historico de prompts perdeu de
            #    qual peca aquela geracao era.
            #
            # E a Forma 1 do CLAUDE.md na forma mais cara: a capacidade
            # existia num caminho e faltava nos irmaos dele.
            _refs_lay_rf = _cfg_rf.get("refs_layout_bytes") or None
            _th_rf.Thread(target=_li_thread.alvo_com_contexto(_gerar_imagem_thread),
                          args=(_prompt, _fotos_desta, _r),
                          kwargs={"refs_layout": _refs_lay_rf,
                                  "refs_layout_nomes": _cfg_rf.get(
                                      "refs_layout_nomes", []),
                                  "tipo": _tp},
                          daemon=True).start()
            _t0 = _tm_rf.time()
            while not _r["done"]:
                _sg = int(_tm_rf.time() - _t0)
                if _sg >= 300:
                    _r["erro"], _r["done"] = "Tempo limite de 5 min.", True
                    break
                _b.progress(min(0.9, _sg / 60),
                            text=f"Refazendo a Imagem {_i + 1}… ({_sg}s)")
                _tm_rf.sleep(1)
            _b.progress(1.0, text="Concluído!")
            if _r["erro"] or not _r["img"]:
                _msgs_rf.append(f"❌ Imagem {_i + 1}: {_r['erro'] or 'sem retorno'}")
                continue
            # AS DUAS CONFERENCIAS, como no laco da geracao.
            #
            # Este caminho gera uma peca INTEIRA do zero — e entregava sem ler
            # o texto e sem olhar a imagem. Foi por aqui que sairam as pecas
            # com texto cortado e a caneca de duas alcas, uma atras da outra,
            # enquanto o dono corrigia a mao.
            def _gerar_rf(_p, _fr=_fotos_desta, _t=_tp):
                _rr = {"img": None, "erro": None, "done": False}
                # A conferencia refaz a peca: ela precisa dos MESMOS
                # argumentos da primeira tentativa, senao a correcao vem com
                # outro layout que a peca que ela deveria consertar.
                _tt = _th_rf.Thread(target=_li_thread.alvo_com_contexto(_gerar_imagem_thread),
                                    args=(_p, _fr, _rr),
                                    kwargs={"refs_layout": _refs_lay_rf,
                                            "refs_layout_nomes": _cfg_rf.get(
                                                "refs_layout_nomes", []),
                                            "tipo": _t},
                                    daemon=True)
                _tt.start()
                _t0g = _tm_rf.time()
                while not _rr["done"]:
                    if int(_tm_rf.time() - _t0g) >= 300:
                        _rr["erro"] = "tempo limite ao refazer."
                        break
                    _tm_rf.sleep(1)
                return _rr["img"], _rr["erro"]

            _img_rf, _rel_t_rf, _rel_p_rf = revisar_tudo(
                _r["img"], _tp, fotos_ref=_fotos_rf, gerar=_gerar_rf,
                prompt_base=_prompt, pedido=_ins,
                dados_descricao=_dados_rf,
                aviso=lambda t: _b.progress(1.0, text=t[:70]))
            registrar_revisao(_rel_t_rf)
            galeria[_i]["bytes"] = _img_rf
            galeria[_i]["texto"] = _rel_t_rf
            galeria[_i]["peca"] = _rel_p_rf
            galeria[_i]["aprovado"] = False
            st.session_state["img_galeria"] = list(galeria)
            _mudou_rf = True

            # "GERADA" NAO E "CUMPRIU O PEDIDO" — e aqui as duas eram a
            # mesma coisa.
            #
            # 01/10: o dono pediu "6 divisorias", a peca foi refeita, e o
            # Studio anunciou "🔁 Imagem 3 refeita do zero". Ela voltou com
            # os mesmos 12 nichos. O anuncio saia porque a GERACAO terminou,
            # sem ninguem perguntar se o pedido tinha acontecido.
            #
            # `revisar_tudo` ja conferiu o texto e mediu a peca — mas nenhuma
            # das duas responde "o que ele pediu esta na imagem?". Quem
            # responde isso e `conferir_ajuste`, comparando a peca ANTERIOR
            # com a nova, com o pedido na mao. So faz sentido quando houve
            # pedido: refazer sem instrucao nao tem o que conferir.
            _ant_rf = _antes_rf if (_ins and _antes_rf) else None
            if _ant_rf:
                _vp_rf, _ep_rf = conferir_ajuste(_ant_rf, _img_rf, _ins)
                if _ep_rf or not _vp_rf:
                    _msgs_rf.append(
                        f"⚠️ Imagem {_i + 1} refeita, mas **não consegui "
                        f"conferir** se «{_ins[:60]}» aconteceu "
                        f"({(_ep_rf or '')[:60]}). Olhe antes de usar.")
                elif _vp_rf.get("feito"):
                    _msgs_rf.append(
                        f"✅ Imagem {_i + 1} refeita: "
                        f"{_vp_rf.get('o_que_saiu') or _ins[:70]}.")
                else:
                    _falta_rf = (_vp_rf.get("o_que_falta") or "").strip()
                    _msgs_rf.append(
                        f"❌ Imagem {_i + 1} foi refeita, mas o pedido NÃO "
                        f"saiu: «{_ins[:60]}»."
                        + (f" Falta: {_falta_rf[:120]}" if _falta_rf else "")
                        + "\n   Me peça de novo e eu tento por outro caminho.")
            else:
                _msgs_rf.append(f"🔁 Imagem {_i + 1} refeita do zero.")
        if _mudou_rf:
            # Pelo helper, e nao direto: e ele que faz a falha aparecer na
            # tela em vez de sumir num `except: pass`.
            # UMA gravacao, e nao duas. A chamada direta ao `rascunho.salvar`
            # que existia aqui sobreviveu a criacao do helper e virava a
            # segunda escrita do mesmo dado — silenciosa, porque tinha o
            # `except: pass` proprio. Duas respostas para a mesma pergunta:
            # se uma falhasse, ninguem saberia qual.
            guardar_rascunho(usuario_logado, "refazer do zero")
        if _msgs_rf:
            st.session_state.setdefault("ms_chat_hist", []).append(
                {"role": "assistant", "content": "\n".join(_msgs_rf)})
        st.rerun()

    cmds_pendentes = st.session_state.pop("chat_img_pendente", [])
    if cmds_pendentes:
        fotos_ref_aj = st.session_state.get("img_fotos_originais") or []
        msgs_result, _mudou = [], False
        for cmd in cmds_pendentes:
            num_foto  = cmd.get("num", 1)
            instrucao = cmd.get("instrucao", "")
            idx_alvo  = num_foto - 1
            if idx_alvo < 0 or idx_alvo >= len(galeria):
                msgs_result.append(f"⚠️ Imagem {num_foto} não existe na galeria.")
                continue
            tipo_alvo = galeria[idx_alvo]["tipo"]
            # Usa a imagem ATUAL como referência + prompt de ajuste fino
            img_ref_cmd = [galeria[idx_alvo]["bytes"]] if galeria[idx_alvo]["bytes"] else fotos_ref_aj
            import time as _time_cmd
            import threading as _threading_cmd
            # Gera, CONFERE e tenta de novo se nao saiu. O assistente do
            # chat era justamente quem nao via nada: ele mandava a
            # instrucao e respondia como se estivesse resolvido. Agora a
            # resposta dele sai do veredito, e nao do envio.
            _res_cmd = {"img": None, "relato": None, "done": False}
            _barra_cmd = st.progress(0.0, text=f"Assistente IA: ajuste na Imagem {num_foto}...")

            # Antes de ajustar, diz QUAL peça é — é o que liga o prompt da
            # correção ao prompt que gerou esta imagem, e não a outra.
            marcar_peca_em_ajuste(num_foto)

            # A IMAGEM QUE O COLABORADOR ANEXOU ENTRA COMO REFERÊNCIA.
            #
            # Dono, 29/09: "eles mandaram a imagem no chat para ficar claro o
            # que ele pediu". Ela chegava ao chat e parava lá: o motor recebia
            # a peça mais uma frase, e ONDE está cortado, QUAL cota trocar e o
            # que foi circulado se perdia na tradução para texto — que é o
            # trabalho que anexar a imagem existe para evitar.
            #
            # Ela entra ANTES das fotos do produto, e não no lugar delas: as
            # fotos são a trava de fidelidade (é delas que sai a cor e a
            # forma), a referência é o que se pede. Trocar uma pela outra faria
            # o motor copiar a arte marcada em vez de corrigir a peça.
            _ref_pedido = [b for b in (cmd.get("referencia") or []) if b]
            _refs_cmd = _ref_pedido + list(fotos_ref_aj or [])

            def _rodar_cmd(_ref=img_ref_cmd[0] if img_ref_cmd else None,
                           _ins=instrucao, _tp=tipo_alvo,
                           _rf=_refs_cmd, _r=_res_cmd):
                try:
                    _r["img"], _r["relato"] = ajustar_com_conferencia(
                        _ref, _ins, tipo=_tp, referencias=_rf,
                        dados_descricao=st.session_state.get(
                            "img_dados_descricao") or {},
                        aviso=lambda t: _r.__setitem__("fase", t))
                except Exception as _e:
                    _r["img"], _r["relato"] = None, {
                        "ok": False, "tentativas": 0, "erro": str(_e)[:160],
                        "falta": "", "colateral": ""}
                finally:
                    _r["done"] = True

            _threading_cmd.Thread(target=_li_thread.alvo_com_contexto(_rodar_cmd),
                                  daemon=True).start()
            _t0_cmd = _time_cmd.time()
            while not _res_cmd["done"]:
                _seg_cmd = int(_time_cmd.time() - _t0_cmd)
                if _seg_cmd >= 600:
                    _res_cmd["relato"] = {
                        "ok": False, "tentativas": 0, "falta": "",
                        "colateral": "",
                        "erro": "tempo limite de 10 min atingido."}
                    _res_cmd["done"] = True
                    break
                _barra_cmd.progress(
                    min(0.9, _seg_cmd / 120),
                    text=(f"Imagem {num_foto}: "
                          f"{_res_cmd.get('fase') or 'ajustando'}… "
                          f"({_seg_cmd}s)"))
                _time_cmd.sleep(1)
            _barra_cmd.progress(1.0, text="Concluído!")
            nova_img = _res_cmd["img"]
            _relato = _res_cmd["relato"] or {"ok": None, "tentativas": 0,
                                             "erro": "sem relato",
                                             "falta": "", "colateral": ""}
            err_aj = _relato.get("erro") if _relato.get("ok") is False and not nova_img else None
            msgs_result.append(relato_em_texto(num_foto, _relato))
            _resultado_log = ("ok" if _relato.get("ok") else
                              f"nao confirmado: {_relato.get('falta') or _relato.get('erro','')}"[:120])
            # `nova_img` volta preenchida mesmo quando o ajuste FALHOU —
            # nesse caso ela e a imagem original, devolvida intacta. Dizer
            # "atualizada" aqui contradizia o proprio relato duas linhas
            # acima, e era o "✅" que o colaborador lia enquanto a imagem
            # continuava errada.
            if nova_img and _relato.get("ok") is not False:
                st.session_state["img_galeria"][idx_alvo]["bytes"] = nova_img
                _mudou = True
                _resultado_log = "imagem atualizada"
                # A copia de seguranca acompanha o ajuste. Sem esta linha o
                # disco continuava com a imagem de antes da correcao.
                guardar_rascunho(usuario_logado, "ajuste do chat")
            try:
                import log_imagem
                log_imagem.registrar("ajuste_aplicado", instrucao, num_foto,
                                     tipo_alvo, _resultado_log)
            except Exception:
                pass
        # A galeria ja foi desenhada acima, com os bytes ANTIGOS. Sem recarregar
        # a pagina, a imagem na tela continua a de antes e so a mensagem de
        # sucesso aparece — que era exatamente o sintoma: "diz que corrige,
        # mas a imagem permanece a mesma". As correcoes feitas pelos paineis
        # manuais ja faziam st.rerun(); a do Assistente IA nao fazia.
        # O veredito volta para a CONVERSA, e nao so para esta aba.
        #
        # Sem isto o assistente mandava o comando e nunca ficava sabendo no
        # que deu: na mensagem seguinte ele falava como se tivesse dado
        # certo, porque para ele a historia terminava no envio. Agora a
        # ultima coisa que ele leu sobre aquela imagem e o resultado real —
        # e a instrucao dele diz para nao chamar de pronto o que o veredito
        # nao confirmou.
        if msgs_result:
            try:
                _hist_chat = st.session_state.get("ms_chat_hist")
                if _hist_chat is not None:
                    _hist_chat.append({
                        "role": "assistant",
                        "content": "**Resultado do ajuste, conferido na "
                                   "imagem:**\n\n" + "\n\n".join(msgs_result)})
            except Exception:
                pass
        if _mudou:
            st.session_state["chat_img_msgs"] = msgs_result
            st.rerun()
        if msgs_result:
            st.info("\n\n".join(msgs_result))


def pagina_imagem(usuario_logado):
    st.subheader("Imagem")
    st.caption("Gere imagens profissionais para o anúncio. A IA mostra o que vai criar antes de gastar com a geração.")

    # ── QUEM ESTÁ GERANDO, E O QUE — marcado AQUI, na thread principal ───────
    #
    # A geração roda em `threading.Thread` (linha ~7162), e de dentro de uma
    # thread `st.session_state` volta VAZIO — sem erro, sem aviso. O registro
    # do prompt lia produto e usuário de lá, então TODA linha do log gravou
    # produto em branco: o filtro por nome nunca batia e o histórico de
    # prompts voltava sempre vazio.
    #
    # AQUI, e não junto de cada `Thread(...)`: são seis lugares que abrem
    # thread nesta tela, e marcar em cada um é a receita para o sétimo
    # esquecer — o mesmo motivo de o registro do prompt morar na porta do
    # motor. Esta linha roda uma vez por desenho da página, antes de todas.
    try:
        import log_imagem as _li_ctx
        _li_ctx.marcar_contexto(
            produto=(st.session_state.get("img_nome_produto", "")
                     or st.session_state.get("nome_produto", "")),
            usuario=usuario_logado)
    except Exception:
        # Marcar contexto é apoio, não requisito: nunca pode derrubar a tela.
        pass

    # O que o Assistente IA pediu roda AQUI, antes de qualquer ramo de modo.
    # Dentro do `else` do seletor, como estava, ele era mudo no ✏️ Ajuste Fino:
    # o chat prometia "Imagem 1 será refeita do zero" e a fila ficava parada.
    consumir_comandos_do_chat(usuario_logado)

    # ── A revisão de texto está de pé? ───────────────────────────────────────
    #
    # Sozinha, sem botão e sem ninguém pedir. O que aconteceu foi isto: a
    # revisão estava lá, o colaborador achava que estava conferindo, e as peças
    # saíam sem leitura nenhuma — o único sinal era uma legenda cinza embaixo
    # da imagem. Se ela não tem como rodar, a tela avisa ANTES de gastar com a
    # geração, e não depois.
    _rev_ok, _rev_motivo = revisao_de_texto_disponivel()
    if not _rev_ok:
        st.error(
            "🔤 **A revisão de texto não está funcionando.** As imagens vão "
            "ser geradas, mas **ninguém vai ler o que está escrito nelas** — "
            "palavra inventada e erro de português passam direto.\n\n"
            f"Motivo: {_rev_motivo}"
        )

    # Os motores de imagem, ditos ANTES de gastar — mesma regra do aviso acima.
    _mot_ok, _mot_aviso = motores_de_imagem()
    if _mot_aviso:
        (st.error if not _mot_ok else st.warning)("🖼️ " + _mot_aviso)

    # A VARIAVEL DO RAILWAY APONTA PARA UM MODELO QUE A CONTA NAO TEM?
    #
    # O Studio agora se recupera sozinho e segue gerando — mas recuperar
    # CALADO esconderia a configuracao errada para sempre, e o dia em que a
    # descoberta tambem falhar ninguem entenderia por que. Funciona E diz o
    # que esta torto.
    _av_modelo = aviso_de_modelo_invalido()
    if _av_modelo:
        st.warning("🖼️ " + _av_modelo)

    # A copia de seguranca falhou na passada anterior? Aqui e onde se diz.
    aviso_de_rascunho()

    # ── Recuperacao apos queda de conexao ────────────────────────────────────
    # Se a sessao morreu no meio de uma geracao, o session_state veio vazio mas o
    # rascunho em disco continua la. Sem isto, o colaborador so via o formulario
    # em branco e concluia que nao gerou nada — com as imagens ja pagas.
    if not st.session_state.get("img_galeria"):
        try:
            import rascunho as _rasc
            # SÓ A FICHA. Ler os bytes aqui significava abrir do disco todas as
            # imagens do rascunho a cada tecla digitada nesta tela — e é o que
            # travava o Ajuste Fino e derrubava a conexão.
            _pend = _rasc.resumo(usuario_logado)
        except Exception:
            _pend = None
        if _pend:
            _n = len(_pend["galeria"])
            _quando = (f"há {_pend['idade_min']} min" if _pend["idade_min"] >= 1
                       else "agora há pouco")
            _motivo = ("uma geração nova começou e não terminou"
                       if _pend.get("de_geracao_interrompida")
                       else "a conexão caiu no meio")
            st.warning(
                f"🛟 Encontrei **{_n} imagem(ns)** de **{_pend['nome_produto'] or 'um produto'}** "
                f"geradas {_quando} que não chegaram a aparecer na tela — {_motivo}. "
                "Elas já foram pagas: recupere antes de gerar de novo."
            )
            _c_rec, _c_desc = st.columns(2)
            if _c_rec.button(f"🛟 Recuperar as {_n} imagens", type="primary",
                             use_container_width=True, key="img_recuperar_rascunho"):
                # AQUI, sim, os bytes: é o único momento em que alguém precisa
                # deles, e é um clique por vez.
                _cheio = _rasc.carregar(usuario_logado)
                if not _cheio:
                    st.error("As imagens do rascunho não estão mais no disco.")
                else:
                    st.session_state["img_galeria"] = _cheio["galeria"]
                    definir_produto_da_sessao(_cheio["nome_produto"])
                    st.rerun()
            if _c_desc.button("Descartar", use_container_width=True,
                              key="img_descartar_rascunho"):
                try:
                    _rasc.limpar(usuario_logado)
                except Exception:
                    pass
                st.rerun()

    MODELO_DIAG = "gemini-3.1-flash-image"
    # ── Saúde do processo ────────────────────────────────────────────────
    #
    # A faixa "Reconectando ao servidor" tem três causas possíveis, e só uma
    # delas apaga o histórico do chat: o processo REINICIAR. As outras duas —
    # deploy e script preso — não apagam nada.
    #
    # Sem este número, a diferença entre elas é opinião. Com ele, é uma linha:
    # se o "de pé há" volta para segundos toda vez que a tela reconecta, o
    # processo está morrendo e voltando, e a causa é memória.
    try:
        import saude as _sd
        _sd.contar_passada()
        _s = _sd.resumo(st.session_state)
        _linha = (f"⚙️ Processo de pé há **{_s['de_pe_ha']}** · "
                  f"{_s['passadas']} passada(s) · memória "
                  f"**{_s['memoria_mb']} MB**"
                  + (f" de {_s['limite_mb']} MB ({_s['pct_memoria']}%)"
                     if _s['limite_mb'] else "")
                  + (f" · imagens nesta sessão: {_s['imagens_na_sessao_mb']} MB"
                     if _s['imagens_na_sessao_mb'] else ""))
        if _s["pct_memoria"] >= 80:
            st.warning(_linha + "  \n⚠️ Memória perto do limite do container — "
                       "é aqui que ele reinicia e o histórico do chat some.")
        else:
            st.caption(_linha)
    except Exception:
        pass

    with st.expander("🔧 Diagnóstico das APIs de Imagem", expanded=False):
        st.caption("Testa o motor primário da OpenAI e Gemini Flash (fallback) para confirmar que estão funcionando.")
        if st.button("Testar APIs agora", key="btn_diag_gemini"):
            # Testa OpenAI
            _oai_key = _get_openai_api_key()
            if _oai_key:
                _modelo = modelo_de_imagem()
                # O QUE A CONTA TEM, DITO ANTES DO TESTE.
                #
                # Era esta a pergunta que faltava: o Studio insistia num nome
                # inventado e a tela mostrava "404", um número que não diz a
                # ninguém o que fazer. Agora a lista vem junto, e escolher o
                # certo deixa de depender de alguém adivinhar.
                _disp = modelos_de_imagem_da_conta()
                if _disp:
                    st.caption("Modelos de imagem desta conta: "
                               + ", ".join(_disp[:8])
                               + f"  ·  em uso: **{_modelo}**")
                    if _modelo not in _disp:
                        st.error(
                            f"O modelo em uso (**{_modelo}**) NÃO está na "
                            f"conta. Configure `OPENAI_MODELO_IMAGEM` no "
                            f"Railway com um da lista acima — ou deixe como "
                            f"está: o Studio troca sozinho na primeira falha.")
                else:
                    st.caption("Não consegui listar os modelos desta conta.")
                # ── E O QUE ISSO SIGNIFICA PARA AS PEÇAS ─────────────────
                #
                # A lista de modelos não diz a ninguém que as peças vão sair
                # com margem. O Studio SABIA e parava no nome do modelo — a
                # mesma falha que o oitavo verificador existe para pegar:
                # tem a informação e não a transforma em recado.
                _cap_ok, _cap_recado = capacidade_do_motor(_disp)
                (st.success if _cap_ok else st.error)(_cap_recado)
                with st.spinner(f"Testando {_modelo}…"):
                    import time as _td
                    _t0_oai = _td.time()
                    try:
                        from openai import OpenAI as _OAITest
                        _oai_client = _OAITest(api_key=_oai_key)
                        # O TESTE SE ADAPTA IGUAL À GERAÇÃO.
                        #
                        # Ele mandava `quality="low"` — o mesmo parâmetro que
                        # o `dall-e-3` recusa e que acabou de ser corrigido no
                        # caminho de geração. Corrigir num irmão e deixar o
                        # outro é a Forma 1 desta base, e aqui ela doía duas
                        # vezes: a tela de diagnóstico diria que o motor não
                        # funciona quando o problema é o parâmetro do teste.
                        _args_t = {"model": _modelo,
                                   "prompt": "A small red circle on white "
                                             "background, minimal.",
                                   "n": 1, "size": "1024x1024",
                                   "quality": "low"}
                        while True:
                            try:
                                _oai_resp = _oai_client.images.generate(**_args_t)
                                break
                            except Exception as _e_t:
                                _q_t = parametro_recusado(_e_t, _args_t)
                                if not _q_t:
                                    raise
                                _args_t.pop(_q_t, None)
                        _oai_ms = int((_td.time() - _t0_oai) * 1000)
                        _oai_img = getattr(_oai_resp.data[0], "b64_json", None) or getattr(_oai_resp.data[0], "url", None)
                        if _oai_img:
                            st.success(f"✅ **{_modelo}** — gerou imagem ({_oai_ms}ms)")
                        else:
                            st.warning(f"⚠️ **{_modelo}** — sem imagem na resposta ({_oai_ms}ms)")
                    except Exception as _e_oai:
                        _oai_ms = int((_td.time() - _t0_oai) * 1000)
                        st.error(f"❌ **{_modelo}** — {str(_e_oai)[:300]} ({_oai_ms}ms)")
            else:
                st.warning("⚠️ **Motor primário** — OPENAI_API_KEY não configurada nas "
                           "variáveis do Railway.")

            # Testa Gemini
            with st.spinner(f"Testando {MODELO_DIAG} via Gemini API (pode levar ~30s)..."):
                d = _testar_gemini_api()
            if "erro_geral" in d:
                st.error(d["erro_geral"])
            else:
                st.caption(f"Gemini API Key: `{d.get('api_key','?')}`")
                info = d.get(MODELO_DIAG, {})
                if info.get("ok"):
                    icone = "✅" if info.get("tem_imagem") else "⚠️"
                    label = "gerou imagem" if info.get("tem_imagem") else "respondeu mas sem imagem (créditos podem estar esgotados)"
                    st.success(f"{icone} **{MODELO_DIAG}** — {label} ({info['ms']}ms)")
                else:
                    st.error(f"❌ **{MODELO_DIAG}** — {info.get('erro','erro desconhecido')} ({info.get('ms',0)}ms)")

    # ── RE-RUN AUTOMÁTICO DA TRIAGEM (disparado pelo chat ao preencher dados) ──
    if st.session_state.pop("img_rerun_triagem", False):
        cfg = st.session_state.get("img_triagem_config")
        if cfg and cfg.get("tipos"):
            with st.spinner("♻️ O Assistente IA atualizou os dados — refazendo a análise..."):
                try:
                    plano, erro = gerar_triagem_ia(
                        cfg["nome_produto"],
                        cfg["tipos"],
                        cfg.get("dados_descricao"),
                        cfg.get("instrucoes_extras", ""),
                        cfg.get("fotos_bytes", []),
                    )
                    if not erro and plano:
                        st.session_state["img_triagem_plano"] = plano
                except Exception:
                    pass  # silencioso — triagem antiga continua visível
            st.rerun()

    # ── LINHA 1: Nome + Código ─────────────────────────────────────────────────
    # Pré-preenche via session_state (evita bug RemoveChild do React ao usar
    # value= com pop() durante re-renders causados por paste/autocomplete)
    if "img_nome_importado" in st.session_state:
        st.session_state["img_nome_produto_input"] = st.session_state.pop("img_nome_importado")
    if "img_codigo_importado" in st.session_state:
        st.session_state["img_codigo_input"] = st.session_state.pop("img_codigo_importado")

    col_nome, col_cod = st.columns(2)
    with col_nome:
        # Semeado com o produto em que a pessoa ja esta trabalhando, para nao
        # redigitar o mesmo nome em cinco abas. ANTES do widget: escrever na
        # chave depois de ele existir derruba a tela.
        import contexto_produto as _ctx_img
        _ctx_img.semear("img_nome_produto_input")
        nome_produto = st.text_input(
            "Nome do produto",
            key="img_nome_produto_input",
        )
    with col_cod:
        if _ctx_img.codigo() and not str(
                st.session_state.get("img_codigo_input", "")).strip():
            st.session_state["img_codigo_input"] = _ctx_img.codigo()
        codigo_input = st.text_input(
            "Código da descrição (opcional)",
            key="img_codigo_input",
            placeholder="ex: MS-BENG-07174K2  (gerado na aba Descrição)",
            help="Gere uma descrição na aba Descrição — o código aparece num bloco azul no final. Copie e cole aqui. O nome do produto não é o código.",
        )

    # Busca dados da descrição pelo código
    dados_descricao = None
    if codigo_input:
        import atividades as _atv
        dados_descricao = _atv.buscar_por_codigo(codigo_input)
        if dados_descricao:
            st.success(
                f"✅ Descrição encontrada: **{dados_descricao.get('nome_produto','')}** · "
                f"Cor: {dados_descricao.get('cor') or '—'} · "
                f"Medidas: {dados_descricao.get('medidas') or '—'} · "
                f"Peso: {dados_descricao.get('peso') or '—'} · "
                f"Material: {dados_descricao.get('material') or '—'}"
            )
            # O codigo ser reconhecido nao quer dizer que a descricao esteja
            # completa: quem a gerou pode ter deixado peso e material em branco.
            # Antes isso so aparecia la na frente, como imagem bloqueada, depois
            # de a pessoa ter montado a triagem inteira.
            _vazios = [rot for rot, ch in (("Peso", "peso"), ("Material", "material"),
                                           ("Cor", "cor"), ("Medidas", "medidas"))
                       if not str(dados_descricao.get(ch) or "").strip()]
            if _vazios:
                # Diagnostico ao lado do aviso: quando a tela acusa falta de um
                # dado que a pessoa preencheu, da para ver a linha crua em vez de
                # discutir de memoria.
                with st.expander("🔎 O que a planilha realmente tem neste código"):
                    _diag_cod = _atv.diagnostico_codigo(codigo_input)
                    if _diag_cod.get("erro"):
                        st.error(_diag_cod["erro"])
                    else:
                        if _diag_cod.get("duplicadas"):
                            st.error("Colunas repetidas no cabeçalho: **"
                                     + "**, **".join(_diag_cod["duplicadas"])
                                     + "**. A leitura fica com a última, que "
                                       "costuma estar vazia — é preciso apagar a "
                                       "coluna repetida na planilha.")
                        st.caption("Cabeçalho da aba `atividades`, na ordem real:")
                        st.code(" | ".join(str(c) for c in _diag_cod.get("cabecalho", [])))
                        for _ln in _diag_cod.get("linhas", []):
                            st.caption(f"Linha de {_ln.get('data_hora','?')} · {_ln.get('tipo','?')}")
                            st.json({k: v for k, v in _ln.items()
                                     if k in ("codigo", "cor", "medidas", "peso",
                                              "material", "categoria", "uso")})
                st.warning(
                    "⚠️ A descrição foi encontrada, mas está sem **"
                    + "**, **".join(_vazios) + "**. Estes campos ficaram em branco "
                    "quando a descrição foi gerada — imagens que dependem deles "
                    "vão aparecer bloqueadas. Dá para preencher aqui mesmo, no "
                    "passo da análise."
                )
        else:
            st.warning("Código não encontrado no histórico. Pode continuar — só não haverá vínculo com a descrição.")

    # Também usa dados do session_state do módulo de descrição se o usuário
    # acabou de gerar na mesma sessão e ainda não copiou o código
    if not dados_descricao and st.session_state.get("desc_codigo_atual") == codigo_input and codigo_input:
        dados_descricao = st.session_state.get("desc_dados_atual")

    # ── TRIAGEM: specs do produto (quando não veio de código de descrição) ─────
    # Preenche medidas/peso/material/etc. automaticamente a partir da triagem.
    # Se houver múltiplas variantes com o mesmo nome, exibe seletor visual.
    #
    # ── O CAMPO NÃO PODE ACEITAR O NOME E NÃO FAZER NADA ──────────────────
    #
    # Relatado em 28/09: "anexei primeiro o código da descrição, o sistema
    # identificou, mas quando preencho o nome do produto e dou enter para
    # buscar a triagem, não busca, não faz nada".
    #
    # Não fazia mesmo, e é a condição da linha abaixo: com uma descrição que
    # já traz medidas, a triagem inteira é pulada — de propósito, porque a
    # descrição é a fonte mais específica. O defeito não é a regra: é o
    # SILÊNCIO. O campo continua aceitando texto, o Enter recarrega a tela, e
    # nada aparece — nem o dado, nem o motivo.
    if nome_produto and dados_descricao and dados_descricao.get("medidas"):
        st.caption(
            "ℹ️ Os dados deste produto estão vindo da **descrição** "
            f"(código `{codigo_input}`), que é a fonte mais completa — por "
            "isso a triagem não é consultada agora, e digitar o nome aqui não "
            "muda nada. Para usar a triagem no lugar, apague o código."
        )

    if nome_produto and not (dados_descricao and dados_descricao.get("medidas")):
        import triagem as _triagem_img
        _sel_triagem_key = "img_triagem_sel_idx"
        _busca_prev_key = "img_triagem_busca_prev"

        # Limpa seleção se nome_produto mudou. O "ignorar" vai junto: ele é
        # a resposta sobre UM produto, e levá-la para o próximo faria a
        # triagem certa ser descartada sem ninguém pedir.
        if st.session_state.get(_busca_prev_key) != nome_produto:
            st.session_state[_sel_triagem_key] = None
            st.session_state["img_triagem_ignorar"] = False
            st.session_state[_busca_prev_key] = nome_produto

        _encontrados_t = _triagem_img.buscar_triagens_por_trecho(nome_produto)

        if len(_encontrados_t) == 1:
            # ── UMA TRIAGEM SÓ TAMBÉM PRECISA SER ANUNCIADA ──────────────
            #
            # O DEFEITO QUE ISTO CORRIGE, relatado em 25/09: "ele puxou da
            # triagem da caneca de pedra e colocou que o porta-joias é de
            # veludo e resina".
            #
            # A busca é por TRECHO do nome (`buscar_triagens_por_trecho`), e
            # quando ela devolvia UMA, esta tela preenchia material, medidas,
            # peso, cor e características **em silêncio** — nenhuma linha na
            # tela dizia de qual produto aquilo tinha vindo. Com duas ou mais
            # ela avisa e deixa trocar; com uma, não avisava nada. A pessoa
            # só descobria o produto errado na imagem pronta, depois de
            # gastar a geração.
            #
            # E não havia como recusar. Ela pediu ao chat para ignorar a
            # triagem, e o chat não tem como: o material entra aqui, antes de
            # qualquer conversa.
            _t = _encontrados_t[0]
            _ignora_key = "img_triagem_ignorar"
            _ignorando = bool(st.session_state.get(_ignora_key))

            _c_tri, _c_btn_tri = st.columns([5, 1])
            if _ignorando:
                _c_tri.warning(
                    f"🚫 Triagem **ignorada** por sua escolha: "
                    f"{_t.get('nome_comercial', '')}. Material, medidas e "
                    f"peso NÃO serão preenchidos por ela — use o campo de "
                    f"instruções para dizer o material certo.")
                if _c_btn_tri.button("Usar de novo", key="img_tri_voltar",
                                     use_container_width=True):
                    st.session_state[_ignora_key] = False
                    st.rerun()
            else:
                _c_tri.info(
                    f"📋 Usando a triagem **{_t.get('nome_comercial', '')}**"
                    f"{' · ' + _triagem_img._label_variante(_t) if _triagem_img._label_variante(_t) else ''}"
                    f"  \nMaterial: **{_t.get('material') or '—'}** · "
                    f"Medidas: {_t.get('medidas') or '—'} · "
                    f"Peso: {_t.get('peso') or '—'}")
                if _c_btn_tri.button("Não é esta", key="img_tri_ignorar",
                                     use_container_width=True,
                                     help="Ignora esta triagem nesta geração"):
                    st.session_state[_ignora_key] = True
                    st.rerun()

            if not _ignorando:
                if not dados_descricao:
                    dados_descricao = {}
                for _fld, _val in [
                    ("medidas", _t.get("medidas")), ("peso", _t.get("peso")),
                    ("material", _t.get("material")), ("cor", _t.get("variacao_cores")),
                    ("caracteristicas", _t.get("caracteristicas")),
                    ("diferenciais", _t.get("diferenciais")),
                ]:
                    if _val and not dados_descricao.get(_fld):
                        dados_descricao[_fld] = _val

        elif len(_encontrados_t) > 1:
            _selecionado_t_idx = st.session_state.get(_sel_triagem_key)

            if _selecionado_t_idx is not None and _selecionado_t_idx < len(_encontrados_t):
                # Variante já escolhida — exibe resumo e permite trocar
                _t = _encontrados_t[_selecionado_t_idx]
                _col_tinfo, _col_ttrocar = st.columns([5, 1])
                _col_tinfo.success(f"✅ Variante selecionada: {_triagem_img._label_variante(_t)}")
                if _col_ttrocar.button("Trocar variante", key="img_triagem_trocar"):
                    st.session_state[_sel_triagem_key] = None
                    st.rerun()
                if not dados_descricao:
                    dados_descricao = {}
                for _fld, _val in [
                    ("medidas", _t.get("medidas")), ("peso", _t.get("peso")),
                    ("material", _t.get("material")), ("cor", _t.get("variacao_cores")),
                    ("caracteristicas", _t.get("caracteristicas")),
                    ("diferenciais", _t.get("diferenciais")),
                ]:
                    if _val and not dados_descricao.get(_fld):
                        dados_descricao[_fld] = _val
            else:
                # Ainda sem seleção → mostra cards de variante
                _nome_p = _encontrados_t[0].get("nome_comercial", nome_produto)
                st.info(
                    f"**{_nome_p}** tem {len(_encontrados_t)} variante(s) na triagem. "
                    "Selecione a correta para carregar as specs automaticamente:"
                )
                _n_cols_t = min(len(_encontrados_t), 4)
                _cols_t = st.columns(_n_cols_t)
                for _i_t, _var_t in enumerate(_encontrados_t):
                    with _cols_t[_i_t % _n_cols_t]:
                        _foto_id_t = str(_var_t.get("foto_drive_id", "")).strip()
                        if _foto_id_t:
                            try:
                                st.image(_triagem_img.url_thumbnail(_foto_id_t), use_container_width=True)
                            except Exception:
                                st.markdown("📦")
                        else:
                            st.markdown("📦")
                        st.caption(_triagem_img._label_variante(_var_t))
                        if st.button("Selecionar", key=f"img_triagem_btn_{_i_t}", use_container_width=True):
                            st.session_state[_sel_triagem_key] = _i_t
                            st.rerun()

    # ── O QUE GERAR — escolha antes de ver opções específicas ─────────────────
    st.markdown("---")
    modo = st.radio(
        "O que gerar?",
        ["1 imagem específica", "Selecionar", _OPCAO_PADRAO, "✏️ Ajuste Fino"],
        horizontal=True,
        key="img_modo",
    )

    # ══════════════════════════════════════════════════════════════════════════
    # MODO AJUSTE FINO — edição cirúrgica de imagem existente
    # ══════════════════════════════════════════════════════════════════════════
    if modo == "✏️ Ajuste Fino":
        st.info(
            "**✏️ Ajuste Fino** — envie a imagem que deseja modificar e descreva "
            "**somente** o que deve mudar. A IA preservará tudo o mais exatamente igual."
        )

        fotos_ajuste_upload = st.file_uploader(
            "Imagem a ajustar — qualquer formato, inclusive foto de iPhone",
            type=None,  # qualquer formato — normalizar_imagem converte o que precisar
            accept_multiple_files=True,
            key="img_ajuste_upload",
            help="Suba a(s) imagem(ns) que deseja editar. Pode enviar mais de uma variante ao mesmo tempo.",
        )
        # Revisa ANTES de qualquer coisa: converte o que der, e tira da lista
        # o que nao der, dizendo por que. Antes os bytes crus iam direto para o
        # st.image logo abaixo, e um arquivo que o Pillow nao abre derrubava a
        # pagina inteira com um traceback.
        fotos_bytes_ajuste, _nm_aj, _av_aj, _er_aj = revisar_anexos(fotos_ajuste_upload)
        mostrar_anexos(_av_aj, _er_aj)

        # AS FOTOS DO PRODUTO, e não só a arte.
        #
        # Sem elas este modo trabalhava pela metade: a única referência que a
        # IA recebia era a própria peça já montada. Dá para mexer num detalhe
        # assim, mas não dá para recompor o quadro nem mostrar o produto de
        # outro ângulo — e o Studio ainda assim oferecia "refazer do zero",
        # que devolvia a mesma imagem.
        #
        # Opcional de propósito: quem só quer corrigir uma palavra não precisa
        # ir atrás das fotos. Quem quer recompor, precisa — e agora pode.
        fotos_prod_upload = st.file_uploader(
            "Fotos do produto (opcional — só se quiser recompor a imagem)",
            type=None, accept_multiple_files=True, key="img_ajuste_prod",
            help="As fotos originais do produto. Com elas a IA pode mudar o "
                 "enquadramento e mostrar o produto de outro jeito. Sem elas, "
                 "o ajuste fica limitado a editar a peça que já existe.",
        )
        fotos_bytes_prod, _nm_pr, _av_pr, _er_pr = revisar_anexos(fotos_prod_upload)
        mostrar_anexos(_av_pr, _er_pr)
        if fotos_bytes_prod:
            st.caption(f"📷 {len(fotos_bytes_prod)} foto(s) do produto — "
                       "recompor o quadro está liberado.")

        if fotos_bytes_ajuste:
            _cols_aj = st.columns(4)
            for _i, _fb in enumerate(fotos_bytes_ajuste[:4]):
                _cols_aj[_i].image(_fb, use_container_width=True)
            if len(fotos_bytes_ajuste) > 4:
                st.caption(f"+ {len(fotos_bytes_ajuste) - 4} imagem(ns) adicional(is) carregada(s).")

        instrucao_ajuste = st.text_area(
            "O que você quer modificar? (descreva SOMENTE o que deve mudar — não explique o que deve ficar igual)",
            height=120,
            placeholder=(
                "ex: Diminua o tamanho do produto para que fique em proporção realista ao cenário. "
                "O produto mede aproximadamente 18cm.\n\n"
                "NÃO descreva o que já está certo — a IA vai preservar tudo que você não mencionar."
            ),
            key="img_instrucao_ajuste",
        )

        st.markdown("---")
        if st.button(
            "✏️ Aplicar Ajuste Fino",
            type="primary",
            use_container_width=True,
            disabled=(not fotos_bytes_ajuste or not instrucao_ajuste.strip()),
        ):
            if not fotos_bytes_ajuste:
                st.warning("Suba a imagem que deseja ajustar.")
                st.stop()
            if not instrucao_ajuste.strip():
                st.warning("Descreva o que você quer modificar.")
                st.stop()

            import time as _time_af
            import threading as _threading_af
            _res_af = {"img": None, "relato": None, "done": False}

            def _rodar_af(_ref=fotos_bytes_ajuste[0], _ins=instrucao_ajuste.strip(),
                          _rf=list(fotos_bytes_prod or []), _r=_res_af):
                try:
                    # `referencias` é o que faltava aqui e as outras duas
                    # modalidades já passavam. Vazio quando ninguém subiu foto
                    # — e aí é vazio de verdade, não vazio por esquecimento.
                    _r["img"], _r["relato"] = ajustar_com_conferencia(
                        _ref, _ins, referencias=_rf,
                        dados_descricao=st.session_state.get(
                            "img_dados_descricao") or {},
                        aviso=lambda t: _r.__setitem__("fase", t))
                except Exception as _e:
                    _r["img"], _r["relato"] = None, {
                        "ok": False, "tentativas": 0, "erro": str(_e)[:160],
                        "falta": "", "colateral": ""}
                finally:
                    _r["done"] = True

            _threading_af.Thread(target=_li_thread.alvo_com_contexto(_rodar_af),
                                 daemon=True).start()
            _barra_af = st.progress(0.0, text="Aplicando ajuste fino...")
            _t0_af = _time_af.time()
            while not _res_af["done"]:
                _seg_af = int(_time_af.time() - _t0_af)
                if _seg_af >= 600:
                    _res_af["relato"] = {
                        "ok": False, "tentativas": 0, "falta": "",
                        "colateral": "",
                        "erro": "tempo limite de 10 min atingido."}
                    _res_af["done"] = True
                    break
                _barra_af.progress(
                    min(0.9, _seg_af / 120),
                    text=(f"{_res_af.get('fase') or 'Aplicando ajuste fino'}… "
                          f"({_seg_af}s)"))
                _time_af.sleep(1)
            _barra_af.progress(1.0, text="Concluído!")
            img_bytes_af = _res_af["img"]
            _rel_af = _res_af["relato"] or {"ok": None, "tentativas": 0,
                                            "erro": "sem relato", "falta": "",
                                            "colateral": ""}

            if not img_bytes_af:
                st.error(f"❌ {relato_em_texto(1, _rel_af)}")
            else:
                galeria_atual = st.session_state.get("img_galeria", [])
                galeria_atual.append({
                    "tipo": f"Ajuste Fino — {instrucao_ajuste[:40]}...",
                    # De que tipo ela nasceu, para o dia em que alguém pedir
                    # para refazê-la. Sem isto, o rótulo acima ia como tipo e
                    # o prompt saía sem preset nenhum.
                    "tipo_base": PERSONALIZADO,
                    "bytes": img_bytes_af,
                    "aprovado": False,
                })
                st.session_state["img_galeria"] = galeria_atual
                guardar_rascunho(usuario_logado, "ajuste fino (imagem nova)")
                # O veredito viaja com o indice da imagem nova, para aparecer
                # ao lado dela na galeria depois do rerun.
                st.session_state["img_af_relato"] = (len(galeria_atual) - 1,
                                                     _rel_af)
                # `or "produto-ajustado"` SAIU: nome em branco trocava o
                # produto da sessão por um rótulo genérico, e a geração
                # seguinte saía sem nome. A porta ignora o vazio.
                definir_produto_da_sessao(nome_produto, codigo=codigo_input)
                # A imagem que ela subiu é a ARTE PRONTA, e não foto do
                # produto. Gravá-la como "fotos originais" fazia o refazer
                # gerar do zero usando a própria arte errada como referência —
                # e devolver exatamente a mesma imagem, depois de anunciar
                # "refeita do zero". Era a resposta para "ele confirma o que eu
                # pedi, diz que corrigiu, e não corrigiu".
                st.session_state["img_fotos_ajuste"] = fotos_bytes_ajuste
                # Com fotos do produto, o refazer do zero passa a ser possível
                # — e elas, e não a arte, é que são "as fotos originais".
                if fotos_bytes_prod:
                    st.session_state["img_fotos_originais"] = fotos_bytes_prod
                    st.session_state["img_fotos_sao_arte"] = False
                else:
                    st.session_state["img_fotos_sao_arte"] = True
                st.session_state["img_dados_descricao"] = dados_descricao or {}
                st.session_state["img_instrucoes_originais"] = instrucao_ajuste
                import atividades
                atividades.registrar_atividade(
                    usuario_logado,
                    "Imagem (ajuste fino)",
                    nome_produto or "produto",
                    instrucao_ajuste[:80],
                    codigo=codigo_input,
                )
                st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # MODOS PADRÃO — fotos de referência + triagem + geração
    # ══════════════════════════════════════════════════════════════════════════
    else:
        # ── FOTOS DE REFERÊNCIA DO PRODUTO ────────────────────────────────────
        st.markdown("**Fotos de referência do produto**")
        st.caption("Suba quantas fotos quiser — ângulos diferentes ajudam a IA a ser mais fiel.")
        fotos_upload = st.file_uploader(
            "Fotos do produto — qualquer formato, inclusive foto de iPhone",
            type=None,  # qualquer formato — normalizar_imagem converte o que precisar
            accept_multiple_files=True,
            key="img_fotos_upload",
        )
        fotos_bytes, _nomes_ft, _av_ft, _er_ft = revisar_anexos(fotos_upload)
        mostrar_anexos(_av_ft, _er_ft)

        # ── AS FOTOS ANEXADAS TEM DE SOBREVIVER AO REINICIO ──────────────────
        #
        # O que se perdia: os bytes do upload moram na memoria do processo do
        # Streamlit, e a lista de nomes fica no navegador. Quando o Studio
        # reinicia com a pagina aberta — deploy, queda, troca de container — a
        # tela continua mostrando "3 fotos anexadas" e o Python recebe zero.
        # O botao entao respondia "Suba pelo menos uma foto do produto" com as
        # fotos ali na tela, e nao havia nada a fazer alem de refazer tudo.
        #
        # O disco do `rascunho` ja guardava o RESULTADO. Agora guarda tambem a
        # ENTRADA, que e a parte cara de refazer (achar de novo as fotos certas
        # do produto).
        #
        # A recuperacao e um BOTAO, e nunca automatica: repor foto sozinho
        # ressuscitaria justamente a que a pessoa acabou de tirar com o X, e
        # ela geraria oito pecas do produto errado sem saber por que.
        import rascunho as _rasc_ft
        if fotos_bytes:
            # GRAVAR SO QUANDO MUDOU.
            #
            # A primeira versao desta linha chamava `salvar_fotos` a cada
            # passada. O Streamlit redesenha a pagina A CADA TECLA digitada no
            # campo de contexto — seis fotos de 5 MB seriam 30 MB escritos no
            # disco por tecla, e a tela ficaria inutilizavel. E o mesmo defeito
            # que fez a Home levar 15 segundos para abrir.
            #
            # A assinatura e nome + tamanho: nao le byte nenhum, e muda quando
            # a pessoa troca, tira ou acrescenta foto — que e exatamente
            # quando gravar de novo faz sentido.
            _assin_ft = tuple(zip(_nomes_ft, (len(b) for b in fotos_bytes)))
            if st.session_state.get("img_fotos_no_disco") != _assin_ft:
                if _rasc_ft.salvar_fotos(usuario_logado, fotos_bytes, _nomes_ft):
                    st.session_state["img_fotos_no_disco"] = _assin_ft
            st.session_state.pop("img_fotos_recuperadas", None)
        else:
            _usar = st.session_state.get("img_fotos_recuperadas") or []
            if _usar:
                fotos_bytes = [f["bytes"] for f in _usar]
                _nomes_ft = [f["nome"] for f in _usar]
                st.success(
                    f"✅ Usando **{len(fotos_bytes)} foto(s)** recuperadas do "
                    "disco: " + ", ".join(n or "sem nome" for n in _nomes_ft[:5])
                    + ". Para trocar, anexe outras no campo acima.")
                if st.button("Descartar essas e anexar outras",
                             key="img_descartar_fotos"):
                    st.session_state.pop("img_fotos_recuperadas", None)
                    _rasc_ft.limpar_fotos(usuario_logado)
                    st.rerun()
            else:
                # `resumo_fotos` e nao `carregar_fotos`: esta linha roda a cada
                # tecla digitada na pagina, e ler 3 MB de foto do disco a cada
                # passada trava a tela. Os bytes so sobem no clique do botao.
                _guardadas = _rasc_ft.resumo_fotos(usuario_logado)
                if _guardadas:
                    st.info(
                        f"📎 Tenho **{len(_guardadas)} foto(s)** que você "
                        "anexou antes guardadas em disco: "
                        + ", ".join(f["nome"] or "sem nome"
                                    for f in _guardadas[:5])
                        + (f" (+{len(_guardadas) - 5})"
                           if len(_guardadas) > 5 else "")
                        + ". Se a lista de arquivos acima parece cheia mas o "
                          "Studio diz que não há foto, é isto: o Studio "
                          "reiniciou e perdeu os arquivos que o navegador "
                          "ainda mostra.")
                    if st.button("📎 Usar essas fotos de novo",
                                 key="img_recuperar_fotos",
                                 use_container_width=True):
                        st.session_state["img_fotos_recuperadas"] = \
                            _rasc_ft.carregar_fotos(usuario_logado)
                        st.rerun()

        if fotos_bytes:
            LIMITE_MB = 10
            # Pelos nomes que a revisao devolveu, e nao pelo upload original:
            # com um arquivo recusado no meio, o indice do upload aponta para
            # outra foto e o aviso acusa a errada.
            fotos_grandes = [
                (_nomes_ft[i], len(b) / 1_048_576)
                for i, b in enumerate(fotos_bytes)
                if len(b) > LIMITE_MB * 1_048_576
            ]
            if fotos_grandes:
                nomes = ", ".join(f"{n} ({s:.1f}MB)" for n, s in fotos_grandes)
                st.warning(
                    f"⚠️ {len(fotos_grandes)} foto(s) com mais de {LIMITE_MB}MB: {nomes}. "
                    f"Fotos muito grandes podem causar timeout — considere reduzir a resolução antes de enviar."
                )

            # Sempre 5 colunas fixas — evita RemoveChild do React ao mudar nº de colunas
            _cols_prev = st.columns(5)
            for _i, _fb in enumerate(fotos_bytes[:5]):
                _cols_prev[_i].image(_fb, use_container_width=True)
            if len(fotos_bytes) > 5:
                st.caption(f"+ {len(fotos_bytes) - 5} foto(s) adicionais carregadas.")

        # ── IMAGENS DE REFERÊNCIA DE LAYOUT (opcional) ────────────────────────
        # ── REFERÊNCIAS DE AMBIENTAÇÃO ───────────────────────────────────
        #
        # Separadas das de LAYOUT porque a escolha é feita de outro jeito, e
        # essa é a diferença inteira. Layout casa pelo NOME do arquivo — o
        # colaborador batiza "presentear.jpg" e a peça 7 pega. Para cenário
        # isso não funciona: ninguém nomeia uma foto de bar por tipo de peça,
        # e a mesma sala cabe em três peças diferentes.
        #
        # Pedido do dono: "não tem que ir pelo nome da imagem, tem que olhar
        # todas e entender qual ambientação se enquadra melhor em cada tipo".
        with st.expander("🏙️ Imagens de referência de AMBIENTAÇÃO (opcional)",
                         expanded=False):
            st.caption(
                "Suba fotos de **cenários** que você quer como clima das "
                "peças — o cômodo, a luz, os materiais. O Studio **olha "
                "todas** e decide sozinho qual cabe em cada tipo de imagem: "
                "não vai pelo nome do arquivo."
            )
            st.info(
                "🎯 O produto que aparece nessas fotos é **ignorado de "
                "propósito**. O Studio copia o ambiente, a luz e o clima — "
                "e coloca o SEU produto dentro dele, no tamanho real dele."
            )
            refs_amb_upload = st.file_uploader(
                "Referências de ambientação — qualquer formato",
                type=None, accept_multiple_files=True,
                key="img_refs_amb_upload",
                help="Ex.: a foto de um bar à noite para o clima das peças "
                     "deste cinzeiro.",
            )
            refs_amb_bytes = []
            if refs_amb_upload:
                (refs_amb_bytes, _nomes_amb,
                 _av_ra, _er_ra) = revisar_anexos(refs_amb_upload)
                mostrar_anexos(_av_ra, _er_ra)
                _cols_ra = st.columns(4)
                for _i, _rb in enumerate(refs_amb_bytes[:4]):
                    _cols_ra[_i].image(_rb, use_container_width=True)
                if len(refs_amb_bytes) > 8:
                    st.caption(f"Subiu {len(refs_amb_bytes)} — o Studio lê as "
                               "8 primeiras. Acima disso a leitura fica cara "
                               "e a escolha não melhora.")
            st.session_state["img_refs_ambientacao"] = refs_amb_bytes

        with st.expander("🖼️ Imagens de referência de layout (opcional)", expanded=False):
            st.caption(
                "Suba imagens de outros produtos que mostram o **layout, posições, estilo ou texto** "
                "que você quer replicar. A IA vai entender a composição e aplicar ao SEU produto, "
                "mantendo o padrão visual MartinSousa."
            )
            st.info(
                f"💡 **Como nomear os arquivos para as {len(TIPOS_PADRAO)} imagens padrão:** "
                "`fundo_branco.jpg`, `beneficios.jpg`, `cenario.jpg`, `detalhes.jpg`, "
                "`medidas_peso.jpg`, `quebra_objecao.jpg`, `presentear.jpg` — "
                "o nome do arquivo indica para qual tipo de imagem a referência se aplica."
            )
            refs_layout_upload = st.file_uploader(
                "Imagens de referência de layout — qualquer formato",
                type=None,  # qualquer formato — normalizar_imagem converte o que precisar
                accept_multiple_files=True,
                key="img_refs_layout_upload",
                help="Ex: uma imagem de bengala mostrando como você quer que fique o layout — a IA reproduz o estilo no seu produto.",
            )
            refs_layout_bytes = []
            refs_layout_nomes = []
            if refs_layout_upload:
                (refs_layout_bytes, refs_layout_nomes,
                 _av_rl, _er_rl) = revisar_anexos(refs_layout_upload)
                mostrar_anexos(_av_rl, _er_rl)
                # Sempre 4 colunas fixas — evita RemoveChild do React
                _cols_rl = st.columns(4)
                for _i, _rb in enumerate(refs_layout_bytes[:4]):
                    _cols_rl[_i].image(_rb, caption=refs_layout_nomes[_i][:20], use_container_width=True)

                # ── A QUAL PEÇA CADA REFERÊNCIA VAI ───────────────────────────
                # A referência é escolhida pelo nome do arquivo. Sem mostrar o
                # resultado desse casamento ANTES de gerar, o colaborador só
                # descobria que o nome não bateu depois de pagar a geração
                # inteira — e sem saber que o problema era o nome.
                _pares = []
                _usadas = set()
                for _t in TIPOS_PADRAO:
                    _b, _n = ref_layout_do_tipo(_t, refs_layout_bytes, refs_layout_nomes)
                    _pares.append((_t, _n))
                    if _n:
                        _usadas.add(_n)

                _orfas = [n for n in refs_layout_nomes if n not in _usadas]

                with st.expander(
                    f"🔗 Qual referência vai para cada peça "
                    f"({len(_usadas)} de {len(refs_layout_nomes)} em uso)",
                    expanded=bool(_orfas),
                ):
                    for _t, _n in _pares:
                        if _n:
                            st.markdown(f"**{_t}**  →  `{_n}`")
                        else:
                            st.markdown(
                                f"<span style='opacity:.55'>{_t}  →  sem referência "
                                f"(será gerada só pelo padrão)</span>",
                                unsafe_allow_html=True,
                            )
                    if _orfas:
                        st.warning(
                            "Estes arquivos **não serão usados** porque o nome não "
                            "corresponde a nenhuma peça: "
                            + ", ".join(f"`{n}`" for n in _orfas)
                            + ".\n\nRenomeie usando uma palavra da peça — por exemplo "
                            "`beneficios`, `medidas`, `presente`, `cenario`, `close`, "
                            "`objecao`, `ambiente` ou `capa`."
                        )

            instrucao_layout = ""
            if refs_layout_bytes:
                instrucao_layout = st.text_area(
                    "Descreva o que cada imagem de referência representa (opcional)",
                    height=80,
                    placeholder=(
                        "ex: 'fundo_branco.jpg' — quero esse estilo de sombra suave e centralização. "
                        "'beneficios.jpg' — replicar os ícones à direita com texto ao lado."
                    ),
                    key="img_instrucao_layout",
                )

        # ── TIPOS ─────────────────────────────────────────────────────────────
        tipos_selecionados = []
        instrucoes_extras = ""

        if modo == "1 imagem específica":
            tipo_unico = st.selectbox("Tipo de imagem", list(PRESETS.keys()), key="img_tipo_unico")
            instrucoes_extras = st.text_area(
                "Descreva o que você quer nessa imagem (textos, cenas, destaque)",
                value=PRESETS[tipo_unico],
                height=120,
                key=f"img_instr_{tipo_unico}",
                placeholder="ex: título 'Guarda suas memórias com estilo', 3 benefícios: durabilidade, capa dura, folhas pretas...",
            )
            tipos_selecionados = [tipo_unico]
            ambientacao = _campo_ambientacao("unico")

        elif modo == "Selecionar":
            tipos_selecionados = st.multiselect(
                "Quais imagens gerar?",
                TIPOS_PADRAO,
                default=TIPOS_PADRAO[:3],
                key="img_tipos_multi",
            )
            instrucoes_extras = st.text_area(
                "Contexto do produto (dados internos para a IA — não aparecem nas imagens)",
                height=80,
                placeholder="ex: produto tem versão preta e branca, foca nos dois no fundo branco",
                key="img_instr_multi",
            )
            ambientacao = _campo_ambientacao("multi")

        else:  # todas as do padrão
            tipos_selecionados = TIPOS_PADRAO
            st.info(
                "💡 **Contexto do produto** — escreva aqui dados que a IA precisa saber para gerar bem as imagens. "
                "Esses dados são **internos para a IA** e não aparecem escritos nas imagens."
            )
            instrucoes_extras = st.text_area(
                "Contexto do produto (dados internos para a IA — não aparecem nas imagens)",
                height=80,
                placeholder="ex: produto vem em 3 cores (preto, branco e azul) — destaque o preto. "
                            "Rotação de 360°. Base estável. Ideal para presente.",
                key="img_instr_lote",
            )
            ambientacao = _campo_ambientacao("lote")

        # ── BOTÃO DE TRIAGEM ──────────────────────────────────────────────────
        st.markdown("---")
        iniciar_triagem = st.button(
            "🔍 Analisar e mostrar plano antes de gerar",
            type="primary",
            use_container_width=True,
            disabled=not tipos_selecionados,
        )

        if iniciar_triagem:
            # Validações FORA do try/except para evitar que st.stop() seja capturado como erro
            if not nome_produto:
                st.warning("Informe o nome do produto.")
                st.stop()
            if not fotos_bytes:
                st.warning(
                    "Suba pelo menos uma foto do produto — é ela que garante "
                    "fidelidade.\n\n"
                    "Se o campo acima **está mostrando arquivos** e mesmo "
                    "assim eu digo que não há foto, o Studio reiniciou com "
                    "esta página aberta: a lista de nomes fica no navegador, "
                    "o conteúdo dos arquivos fica no servidor. **Recarregue a "
                    "página (F5) e anexe de novo.**")
                st.stop()

            try:
                # A ESPERA TEM DE DIZER QUANTO E O QUE, SENAO E "TRAVOU".
                #
                # O spinner dizia so "Analisando produto...". Numa analise que
                # passou de sete minutos, quem olhava nao tinha como saber se
                # estava andando, quanto faltava, ou se ja tinha morrido.
                _n_fotos = len(fotos_bytes or [])
                with st.spinner(
                    f"Analisando {_n_fotos} foto(s) e montando o plano das "
                    f"{len(tipos_selecionados)} peças… costuma levar de 20 a 60 "
                    "segundos, e o limite é 3 minutos. Não feche a aba."
                ):
                    plano, erro_triagem = gerar_triagem_ia(
                        nome_produto, tipos_selecionados, dados_descricao,
                        instrucoes_extras, fotos_bytes,
                    )

                # A triagem e um PLANEJAMENTO, nao um pre-requisito tecnico: ela
                # roda no Claude, enquanto as imagens saem no motor primário ou no
                # Gemini. Fazer a falha dela travar tudo significa que uma conta
                # sem saldo em UM fornecedor derruba o Studio inteiro — foi o que
                # aconteceu em producao com "credit balance is too low".
                #
                # Agora, quando a triagem falha, seguimos com um plano neutro:
                # todos os tipos escolhidos marcados como viaveis, sem composicao
                # sugerida. O colaborador perde a previa e a checagem de dados
                # faltantes, mas continua conseguindo gerar.
                if erro_triagem:
                    _e_txt = str(erro_triagem)
                    if "credit balance" in _e_txt or "billing" in _e_txt.lower():
                        st.warning(
                            "⚠️ A análise prévia não rodou: a conta da Anthropic está sem "
                            "crédito. **Isso é ajuste de administrador** — avise o Léo "
                            "(console.anthropic.com → Plans & Billing).\n\n"
                            "A geração das imagens continua funcionando normalmente; você "
                            "só não vai ver o plano de criação antes."
                        )
                    elif "timeout" in _e_txt.lower() or "timed out" in _e_txt.lower():
                        # O TEMPO ESGOTADO TEM CONSELHO PROPRIO.
                        #
                        # Antes a espera era infinita: uma analise ficou sete
                        # minutos no spinner sem plano e sem erro, e quem
                        # estava na tela recarregou achando que tinha travado.
                        # Agora ela morre em tres minutos — e morrer sem dizer
                        # o que fazer seria trocar um silencio por outro.
                        st.warning(
                            "⏱️ A análise passou de 3 minutos e foi encerrada. "
                            "Costuma ser volume de imagem: cada foto e cada "
                            "referência de ambientação entra na leitura.\n\n"
                            "**Você pode gerar assim mesmo** — o plano abaixo "
                            "traz os tipos escolhidos, só sem a prévia.\n\n"
                            "Para ter a prévia: clique em **Analisar "
                            "novamente** com menos referências de ambientação, "
                            "ou com fotos menores."
                        )
                    else:
                        st.warning(
                            f"⚠️ Não consegui montar a prévia do plano, mas você pode gerar "
                            f"assim mesmo.\n\nDetalhe técnico: {_e_txt[:200]}"
                        )
                    plano = {
                        "plano": [
                            {"tipo": _t, "numero": _i + 1, "composicao": "",
                             # `cena` existe aqui tambem, para o plano neutro
                             # ter a mesma forma do plano cheio: campo que
                             # existe num e falta no outro e o comeco de um
                             # `KeyError` tres telas adiante.
                             "cena": "", "textos": [], "flags": [], "viavel": True,
                             "pergunta_info": ""}
                            for _i, _t in enumerate(tipos_selecionados)
                        ],
                        "observacao_geral": "",
                    }

                if plano:
                    st.session_state["img_triagem_plano"] = plano
                    st.session_state["img_triagem_config"] = {
                        "nome_produto": nome_produto,
                        "codigo": codigo_input,
                        "tipos": tipos_selecionados,
                        "instrucoes_extras": instrucoes_extras,
                        # Viaja no cfg como o resto: sem isto, o botão de
                        # regerar e o chat montariam o prompt SEM a ambientação
                        # e a peça refeita sairia diferente da que nasceu —
                        # que é exatamente o defeito que `prompt_para_regerar`
                        # existe para não deixar acontecer.
                        "ambientacao": ambientacao,
                        # As fotos de cenario viajam na config, e nao numa
                        # variavel solta: a geracao roda em thread e o
                        # `st.session_state` nao existe la dentro. Foi por
                        # isso que a referencia de layout ja viaja assim.
                        "refs_ambientacao": st.session_state.get(
                            "img_refs_ambientacao") or [],
                        "fotos_bytes": fotos_bytes,
                        "dados_descricao": dados_descricao,
                        # Referências de layout (opcional)
                        "refs_layout_bytes": refs_layout_bytes,
                        "refs_layout_nomes": refs_layout_nomes,
                        "instrucao_layout": instrucao_layout,
                    }
                    # Sem st.rerun() — o plano é exibido diretamente abaixo
                    # sem resetar a página nem perder os campos preenchidos
            except Exception as _e_triagem:
                st.error(
                    f"❌ Ocorreu um erro ao montar a prévia: {_e_triagem}\n\n"
                    "Verifique se o nome do produto está preenchido e tente novamente. "
                    "Se o erro persistir, reduza o tamanho das fotos ou escolha menos tipos de imagem."
                )

    # ── EXIBIÇÃO DA TRIAGEM ───────────────────────────────────────────────────
    if "img_triagem_plano" in st.session_state and "img_triagem_config" in st.session_state:
        plano = st.session_state["img_triagem_plano"]
        cfg = st.session_state["img_triagem_config"]

        st.markdown("---")
        st.markdown("### 🗂️ Plano de criação")
        st.caption("Corrija o que precisar antes de confirmar a geração.")

        itens_plano = plano.get("plano", [])
        itens_viaveis   = [item for item in itens_plano if item.get("viavel", True)]
        itens_bloqueados = [item for item in itens_plano if not item.get("viavel", True)]

        # ── O PLANO É DESTE PRODUTO? ANTES DE GASTAR ──────────────────────────
        #
        # 29/09: a tela dizia "Descrição encontrada: Tigre · 10x21x5 · 299 ·
        # Resina" e as oito peças saíram com "PRODUTO: pendulo balança /
        # 14x13x11 / 202g / Plástico", direção "Técnico Automotivo
        # Minimalista" e o texto "CABE EM MEU CARRO?".
        #
        # O `cfg` é congelado quando o plano é gerado; a descrição é relida a
        # cada abertura. Trocar o código sem refazer o plano deixa os dois
        # discordando — e o sistema tinha os dois na mão sem nunca comparar.
        # Oito peças pagas do produto errado, em silêncio.
        _div_prod = divergencia_de_produto(cfg, nome_produto, dados_descricao)
        if _div_prod:
            st.error("🚫 " + _div_prod)

        # ── E O PLANO CONCORDA CONSIGO MESMO? ────────────────────────────────
        #
        # 30/09. A guarda acima comparou nome, medidas, peso e material do
        # «Compasso Cortador Colorido» — e os quatro batiam. As oito peças
        # saíram assim mesmo: a peça 8 descrevia "caixa aberta com um RELÓGIO
        # DE PULSO dentro", a 7 "a CAIXA DE MADEIRA entre duas mãos", a 4 "o
        # GRÃO DA MADEIRA". Um plano, dois produtos, e nenhuma das duas metades
        # sabia da outra.
        #
        # O que o plano DESCREVE — a cena e a composição, que é o texto que
        # vira a imagem — nunca era comparado com nada. Comparar campo de
        # cadastro não alcança isso: os campos estavam certos.
        _plano_mist = plano_misturado(plano, nome_produto)
        if _plano_mist:
            st.error("🚫 " + _plano_mist)

        # ── A DIREÇÃO DE ARTE, ANTES DE GASTAR ────────────────────────────────
        #
        # Ela era escrita só depois do clique em Confirmar, no meio da barra de
        # progresso. Quem precisa conferir se a estética está certa é o dono, e
        # o momento de conferir é ANTES da geração — depois já são oito peças
        # pagas. O plano existe justamente para isso.
        _dir_plano = plano.get("direcao_de_arte") or {}
        if _dir_plano:
            with st.container(border=True):
                st.markdown(
                    "🎨 **Direção de arte das 8** — "
                    + str(_dir_plano.get("nome", "sem nome"))
                    + (f" · {_dir_plano['posicionamento']}"
                       if _dir_plano.get("posicionamento") else ""))
                if _dir_plano.get("atmosfera"):
                    st.caption(str(_dir_plano["atmosfera"]))
                _pal = _dir_plano.get("paleta") or {}
                if isinstance(_pal, dict) and _pal:
                    # Tarja de cor em vez de nome de cor: ler "#D5C9B8" não diz
                    # nada a ninguém, e é a paleta que decide o conjunto.
                    _quadros = ""
                    for _ch in ("fundo", "painel", "titulo", "apoio", "acento"):
                        _c = _pal.get(_ch) or {}
                        _hex = str(_c.get("hex", "") or "").strip()
                        if not _hex.startswith("#"):
                            continue
                        _quadros += (
                            f"<span style='display:inline-block;width:56px;"
                            f"height:26px;background:{_hex};border-radius:5px;"
                            f"margin-right:6px;border:1px solid #0003' "
                            f"title='{_ch}: {_c.get('nome','')} {_hex}'></span>")
                    if _quadros:
                        st.markdown(_quadros, unsafe_allow_html=True)
                        st.caption(" · ".join(
                            f"{_ch}: {(_pal.get(_ch) or {}).get('nome', '')}"
                            for _ch in ("fundo", "painel", "titulo", "apoio", "acento")
                            if (_pal.get(_ch) or {}).get("nome")))
                _mat = _dir_plano.get("materiais")
                if isinstance(_mat, list) and _mat:
                    st.caption("Materiais: " + ", ".join(str(m) for m in _mat))
                if _dir_plano.get("luz"):
                    st.caption("Luz: " + str(_dir_plano["luz"]))
                if _dir_plano.get("trava_do_produto"):
                    st.caption("Trava do produto: " + str(_dir_plano["trava_do_produto"]))
        else:
            st.info(
                "Este plano não tem direção de arte — cada peça vai deduzir a "
                "própria paleta, que é o comportamento antigo. Clique em "
                "**Analisar novamente** para a triagem decidir uma só para as oito."
            )

        # ── Itens viáveis ─────────────────────────────────────────────────────
        # O TITULO DO CARTAO E O TIPO OFICIAL — E O QUE VAI DECIDIR AS REGRAS.
        #
        # O cartao mostrava o apelido que a IA inventou ("Caracteristicas
        # Tecnicas"), e o Studio gerava pelo tipo que o `numero` apontava
        # ("2 — Beneficios do produto"). Os dois divergiam e a tela escondia
        # a divergencia: so dava para descobrir olhando a imagem pronta.
        _tipos_cfg = cfg.get("tipos") or TIPOS_PADRAO

        # ── O PROMPT DE CADA PECA, ANTES DE PAGAR POR ELA ─────────────────
        #
        # Pedido do dono: *"coloque para que o Studio carregue nessa aba de
        # plano de criacao os prompts que ele enviara para a criacao de cada
        # imagem. Dessa forma podemos fazer testes e verificar se esta correto
        # ou nao. E isso economiza dinheiro, fazendo testes gerando imagens
        # com prompt ainda errado."*
        #
        # Atras de um botao de proposito: montar os oito le a descricao de
        # visao do produto, e o plano nao pode ficar lento para quem so quer
        # conferir a copy.
        _ver_prompts = st.session_state.get("img_ver_prompts", False)
        _c_btn1, _c_btn2 = st.columns([3, 1])
        if _c_btn1.button(
                "🔍 Esconder os prompts" if _ver_prompts
                else "🔍 Ver o prompt que será enviado em cada peça",
                use_container_width=True, key="btn_ver_prompts"):
            st.session_state["img_ver_prompts"] = not _ver_prompts
        # O `st.rerun()` QUE ESTAVA AQUI APAGAVA A TELA.
        #
        # Dono, 28/09: "cliquei em ver o prompt de cada imagem para copiar e
        # te mandar, e ao clicar a tela atualizou e voltou do zero".
        #
        # `st.rerun()` interrompe a execução atual e recomeça a página — tudo
        # que esta passada ainda não tinha desenhado é perdido. Ele estava aí
        # porque `_ver_prompts` foi lido ANTES do clique, então sem recomeçar
        # o bloco abaixo ainda veria o valor velho.
        #
        # Reler a chave depois do clique resolve o mesmo problema sem jogar a
        # tela fora: o clique já provoca um rerun do Streamlit por si só.
        _ver_prompts = st.session_state.get("img_ver_prompts", False)
        if _ver_prompts:
            _c_btn2.caption("não gera imagem · não gasta geração")
            # ── OS OITO PROMPTS NUM ARQUIVO SO ────────────────────────────
            #
            # Dono, 28/09: "nao tem como ter um botao que consolida o que
            # sera enviado de todas as imagens para que eu nao precise abrir
            # e copiar um por um?". Eram oito expanders, oito cliques e oito
            # colagens — e a chance de perder uma no meio.
            #
            # DOIS CLIQUES, e e de proposito: `download_button` precisa do
            # arquivo PRONTO para desenhar, entao um botao de um clique so
            # montaria os oito prompts a cada redesenho da tela.
            if st.button("📄 Preparar os prompts de TODAS as peças (.txt)",
                         use_container_width=True, key="btn_txt_prompts"):
                try:
                    st.session_state["img_txt_prompts"] = txt_dos_prompts(
                        prompt_de_cada_peca(itens_viaveis, cfg, _tipos_cfg,
                                            _dir_plano),
                        cfg.get("nome_produto", ""), _dir_plano)
                except Exception as _e_txt:
                    st.session_state["img_txt_prompts"] = ""
                    st.error(f"Não consegui montar o arquivo: "
                             f"{type(_e_txt).__name__}: {str(_e_txt)[:160]}")
            _txt_pr = st.session_state.get("img_txt_prompts") or ""
            if _txt_pr:
                _nm_pr = (cfg.get("nome_produto", "") or "studio").replace(" ", "_")
                st.download_button(
                    f"⬇️ Baixar os {len(itens_viaveis)} prompts",
                    data=_txt_pr.encode("utf-8"),
                    file_name=f"prompts_que_serao_enviados_{_nm_pr}.txt",
                    mime="text/plain", use_container_width=True,
                    key="btn_txt_prompts_baixar")
                st.caption(f"{len(_txt_pr):,} caracteres · os "
                           f"{len(itens_viaveis)} prompts, na ordem do plano"
                           .replace(",", "."))
            _baixar_historico_de_prompts(sufixo="_plano")
            # O DESCARTE DA REFERENCIA DEIXA DE SER SILENCIOSO.
            #
            # A descricao da referencia de layout e jogada fora quando menciona
            # cor, paleta ou pessoa — e ate agora isso acontecia calado. Quem
            # subiu a imagem achava que o layout tinha sido copiado, e as oito
            # pecas saiam sem orientacao de composicao nenhuma.
            #
            # A leitura vem DEPOIS de montar os prompts: e ali que o filtro
            # roda. Por isso o aviso mora junto do botao, e nao no topo.
            esquecer_descarte_de_layout()

        for item in itens_viaveis:
            flags = item.get("flags", [])
            _oficial = tipo_canonico(item, _tipos_cfg)
            _apelido = str(item.get("tipo", "") or "").strip()
            with st.container(border=True):
                col_title, col_flag = st.columns([5, 1])
                col_title.markdown(f"**{_oficial}**")
                if _apelido and _chave_tipo(_apelido) != _chave_tipo(_oficial):
                    col_title.caption(f"a análise chamou de: “{_apelido}”")
                if flags:
                    col_flag.caption("⚠️ aviso")
                st.caption(item.get("composicao", ""))
                # A cena e o que impede as oito de sairem com a mesma mesa. Se
                # duas vierem iguais, da para ver aqui — antes de pagar.
                _cena_item = str(item.get("cena", "") or "").strip()
                if _cena_item:
                    st.caption("🎬 Cena: " + _cena_item)
                textos = item.get("textos", [])
                if textos:
                    st.caption("Textos: " + " · ".join(f'"{t}"' for t in textos[:4]))
                # PECA QUE DEVERIA TER TEXTO E VEIO SEM APARECE AQUI, ANTES DE
                # PAGAR. Medido na Caneca Termica Medieval em 02/10: o plano
                # voltou com `textos: []` nas pecas 4 e 5, e ate entao isso era
                # mudo. A peca 4 saiu com "TITULO CURTO EM CAIXA ALTA" escrito
                # dentro do cartao, e a 5 com sete cotas inventadas.
                #
                # Hoje o prompt proibe escrever qualquer palavra quando nao ha
                # copy (`blocos_em_portugues`), entao a peca sai limpa — mas
                # limpa sem aviso parece bug. Quem le aqui refaz o plano antes
                # de gastar a geracao.
                elif faixa_de_blocos(_oficial)[1]:
                    st.warning(
                        "✏️ **A análise não escreveu texto para esta peça.** "
                        "Ela vai sair só como fotografia, sem cartão e sem "
                        "legenda — o Studio não inventa palavra. Se esta peça "
                        "precisa de texto, refaça o plano."
                    )
                # BLOCO REPETIDO APARECE AQUI, ANTES DE PAGAR.
                #
                # A peça 4 do dono recebeu "MADEIRA TRABALHADA: / Acabamento e
                # textura" DUAS vezes, e as duas foram ao gerador. O Studio
                # agora descarta a repetida — e dizer isso em voz alta é parte
                # do conserto: descarte calado é o defeito que o oitavo
                # verificador existe para pegar, e quem lê aqui pode refazer o
                # plano em vez de receber uma peça com um argumento a menos.
                # PROMESSA SEM LASTRO APARECE AQUI, ANTES DE PAGAR.
                #
                # "INOX POR DENTRO: DURÁVEL e diferente de canecas
                # decorativas" saiu em 02/10 com todas as guardas verdes: o
                # português está correto, cabe no cartão, não repete outro
                # bloco. Só que "durável" não está em lugar nenhum dos dados
                # do produto — nasceu de a IA ver inox e concluir.
                #
                # É aviso, não bloqueio: casamento por palavra erra, e
                # verificador que dá alarme falso ensina a ser ignorado.
                # Quem conhece o produto decide, e decide antes de gastar.
                _promessas = promessas_sem_lastro(
                    textos, cfg.get("dados_descricao"))
                if _promessas:
                    # DEIXOU DE SER AVISO E VIROU BARREIRA (05/10). Antes a
                    # tela dizia "confira" e o bloco ia ao motor assim mesmo
                    # — a peça 6 saiu com "MANTÉM BEBIDA QUENTE? Sim,
                    # térmica" e o cadastro não tem ensaio térmico nenhum.
                    # Agora `copy_sem_promessa` tira o bloco antes do prompt,
                    # e a tela diz QUAL saiu e por quê.
                    st.warning(
                        "📣 **Bloco(s) removidos: promessa que os dados do "
                        "produto não sustentam.** A peça vai sair SEM eles — "
                        "claim que o cadastro não comprova não chega ao "
                        "gerador. Para que volte, cadastre o dado que o "
                        "sustenta:\n\n"
                        + "\n".join(
                            f'- ~~“{_t}”~~ — a palavra **{", ".join(_x)}** não '
                            f'aparece no material, nos diferenciais, nas '
                            f'características nem no uso cadastrados.'
                            for _t, _x in _promessas))
                _, _repetidos_item = blocos_sem_repeticao(textos)
                if _repetidos_item:
                    st.warning(
                        f"🔁 **{len(_repetidos_item)} bloco(s) de texto "
                        "repetido(s)** — a análise escreveu o mesmo cartão "
                        "mais de uma vez. O repetido é descartado (ele "
                        "gastaria uma vaga e espremeria os outros): "
                        + " · ".join(f'"{t}"' for t in _repetidos_item[:3])
                        + ". Para ter outro argumento no lugar, clique em "
                        "**Analisar novamente**.")
                if flags:
                    with st.expander("Ver aviso", expanded=False):
                        st.warning(flags[0])

                if _ver_prompts:
                    with st.expander("🔍 Prompt que será enviado ao motor",
                                     expanded=False):
                        # PELA FUNCAO UNICA, e nao por uma copia daqui: o
                        # `.txt` consolidado sai da mesma, e duas montagens
                        # discordariam — a questao seria so quando.
                        _en_peca = prompt_de_cada_peca(
                            [item], cfg, _tipos_cfg, _dir_plano)[0][1]
                        st.caption(
                            f"{len(_en_peca)} caracteres · é este texto, exato, "
                            "que vai ao gerador. Uma diferença na hora de gerar: "
                            "quando houver referências de AMBIENTAÇÃO, o cenário "
                            "lido delas é acrescentado no fim."
                        )
                        st.code(_en_peca, language=None)

        _desc = descarte_de_layout() if _ver_prompts else {}
        if _desc:
            st.warning(
                "🧹 **A descrição da referência de layout foi descartada.**\n\n"
                "Ela voltou mencionando " + _desc["motivo"] + ", e isso entraria "
                "no prompt logo acima da linha que proíbe copiar cor, produto e "
                "pessoas da referência — foi assim que um prompt de caneca "
                "ganhou \"chaleira vermelha\".\n\n"
                "**O preço:** as peças ficam sem a orientação de composição "
                "dessa referência. A imagem foi enviada ao gerador; a descrição "
                "dela, não.\n\n"
                "Para aproveitar a referência, suba uma peça de layout mais "
                "neutra — sem pessoas e sem cor dominante."
            )

        # ── O PLANO COBRE OS TIPOS PEDIDOS? ───────────────────────────────────
        #
        # A IA reordenou e renomeou, e dois itens caíram no mesmo tipo oficial:
        # a peça de medidas foi gerada com as regras de painel de benefícios, e
        # ninguém viu até a imagem ficar pronta. Isto deixa de ser silencioso.
        _resolvidos = [tipo_canonico(_it, _tipos_cfg) for _it in itens_plano]
        _repetidos = sorted({_t for _t in _resolvidos if _resolvidos.count(_t) > 1})
        _faltando = [_t for _t in _tipos_cfg if _t not in _resolvidos]
        if _repetidos or _faltando:
            _linhas = []
            if _repetidos:
                _linhas.append("Dois ou mais cartões caíram no MESMO tipo: "
                               + ", ".join(f"**{_t}**" for _t in _repetidos))
            if _faltando:
                _linhas.append("Tipo(s) pedido(s) que ficaram de fora: "
                               + ", ".join(f"**{_t}**" for _t in _faltando))
            st.error(
                "⚠️ **A análise embaralhou os tipos.**\n\n"
                + "\n\n".join(_linhas)
                + "\n\nGerar assim entrega peça com as regras de outra peça — "
                "infográfico de medidas com painel de benefícios, por exemplo. "
                "Clique em **Analisar novamente** antes de confirmar."
            )

        # ── O PLANO PEDE PESSOAS ONDE O TIPO AS PROIBE? ───────────────────────
        _pessoas_erradas = pessoas_em_peca_errada(itens_viaveis, _tipos_cfg)
        if _pessoas_erradas:
            st.warning(
                "👥 **Pessoas planejadas em peça que as proíbe.** Só a "
                "*7 — Presenteie* leva figura humana; nas outras, pessoa no "
                "plano vira ordem contrária à regra que o próprio prompt "
                "carrega.\n\n"
                + "\n".join(f"- **{_t}** — {_p}" for _t, _p in _pessoas_erradas)
                + "\n\nCorrija no texto da peça ou clique em **Analisar "
                "novamente**."
            )

        # ── DUAS PEÇAS NA MESMA SUPERFÍCIE? ───────────────────────────────────
        _repetidas = cenas_repetidas(itens_viaveis, _tipos_cfg)
        if _repetidas:
            st.warning(
                "🎬 **Cenas repetidas entre peças.** Consistência é mesma "
                "paleta, mesmo material e mesma luz — não a mesma mesa. Oito "
                "peças no mesmo cenário deixam o anúncio repetitivo.\n\n"
                + "\n".join(f"- **{_a}** e **{_b}** — {_c}"
                             for _a, _b, _c in _repetidas[:6])
            )

        # ── DUAS PEÇAS NO MESMO ÂNGULO? ───────────────────────────────────────
        #
        # Pedido do dono em 28/09: o produto não pode aparecer sempre do mesmo
        # lado. Um produto com gravação no verso vende metade do argumento
        # quando as oito peças o mostram de frente.
        _mesmas_faces = faces_repetidas(itens_viaveis, _tipos_cfg)
        if _mesmas_faces:
            st.warning(
                "🔄 **O produto aparece no mesmo ângulo em mais de uma peça.** "
                "Se ele tem faces diferentes — gravação no verso, acabamento "
                "na lateral, tampa —, o anúncio inteiro mostra só um lado.\n\n"
                + "\n".join(f"- **{_a}** e **{_b}** — {_c}"
                             for _a, _b, _c in _mesmas_faces[:6])
                + "\n\nSe as fotos não mostram outras faces, isso é o certo: "
                "o Studio não inventa o lado que ninguém fotografou. Para "
                "variar, suba uma foto do verso ou da lateral."
            )

        # ── Itens bloqueados (informação faltante) ────────────────────────────
        if itens_bloqueados:
            st.markdown("---")
            st.markdown(
                "### 🚫 Imagens bloqueadas — informação insuficiente\n"
                "As imagens abaixo **não serão geradas** porque falta alguma informação essencial. "
                "Responda as perguntas no **Assistente IA** (menu lateral) ou preencha os dados e "
                "clique em **Analisar novamente**."
            )
            for item in itens_bloqueados:
                with st.container(border=True):
                    st.markdown(
                        f"<div style='padding:2px 0'>"
                        f"<span class='ms-bloqueada'>🚫 BLOQUEADA</span> &nbsp; "
                        f"<strong>{item.get('numero', '')}. {item.get('tipo', '')}</strong>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    pergunta = item.get("pergunta_info", "").strip()
                    if pergunta:
                        st.error(f"**O que falta:** {pergunta}")
                    else:
                        st.error("Informação necessária não fornecida. Forneça os dados e analise novamente.")

            # Campos de dados técnicos + reanálise.
            #
            # Antes, a mensagem mandava clicar em "Analisar novamente" e esse botão
            # NÃO EXISTIA em lugar nenhum do arquivo. O colaborador digitava o peso
            # na caixa de correção abaixo, que vai para instrucoes_extras — campo
            # marcado no prompt como "NÃO renderize estes dados como texto na
            # imagem". Ou seja: o dado informado era proibido de aparecer e o item
            # continuava bloqueado. Agora medidas e peso vão para dados_descricao,
            # que é o campo que a regra de viabilidade lê e que o prompt autoriza
            # a desenhar.
            _dd_atual = cfg.get("dados_descricao") or {}
            # Havia so Medidas e Peso aqui, e o bloqueio pedia MATERIAL. Nao
            # existia campo de material em lugar nenhum da tela: a imagem
            # bloqueada por falta de material nao tinha como ser desbloqueada.
            st.markdown("**Preencha o que falta e analise de novo:**")
            _c_med, _c_peso = st.columns(2)
            _medidas_novo = _c_med.text_input(
                "Medidas (AxLxP)",
                value=str(_dd_atual.get("medidas", "") or ""),
                placeholder="ex: 30x30x6",
                key="img_fix_medidas",
            )
            _peso_novo = _c_peso.text_input(
                "Peso",
                value=str(_dd_atual.get("peso", "") or ""),
                placeholder="ex: 780g",
                key="img_fix_peso",
            )
            _c_mat, _c_cor = st.columns(2)
            _material_novo = _c_mat.text_input(
                "Material",
                value=str(_dd_atual.get("material", "") or ""),
                placeholder="ex: capa em couro sintético, miolo em papel 180g",
                key="img_fix_material",
            )
            _cor_novo = _c_cor.text_input(
                "Cor / variação de cores",
                value=str(_dd_atual.get("cor", "") or ""),
                placeholder="ex: preto, marrom",
                key="img_fix_cor",
            )

            if st.button("🔄 Analisar novamente", use_container_width=True,
                         key="img_reanalisar"):
                _dd_novo = dict(_dd_atual)
                if _medidas_novo.strip():
                    _dd_novo["medidas"] = _medidas_novo.strip()
                if _peso_novo.strip():
                    _dd_novo["peso"] = _peso_novo.strip()
                if _material_novo.strip():
                    _dd_novo["material"] = _material_novo.strip()
                if _cor_novo.strip():
                    _dd_novo["cor"] = _cor_novo.strip()

                cfg["dados_descricao"] = _dd_novo
                st.session_state["img_triagem_config"] = cfg

                with st.spinner("Reanalisando com os dados novos..."):
                    _plano_novo, _erro_novo = gerar_triagem_ia(
                        cfg["nome_produto"], cfg["tipos"], _dd_novo,
                        cfg.get("instrucoes_extras", ""), cfg["fotos_bytes"],
                    )
                if _erro_novo:
                    st.error(f"Não consegui reanalisar: {_erro_novo}")
                else:
                    st.session_state["img_triagem_plano"] = _plano_novo
                    st.rerun()

        if plano.get("observacao_geral"):
            st.info(plano["observacao_geral"])

        # O campo de "correção que vale para todas" foi removido de propósito.
        # Qualquer ajuste depois da geração é por imagem, pelo Assistente IA,
        # citando o número: imagem não mencionada não pode ser tocada.
        correcao = ""

        n_viaveis = len(itens_viaveis)
        n_bloqueadas = len(itens_bloqueados)

        # Os botões vivem dentro de um placeholder para poderem
        # ser APAGADOS assim que a geração começa. No Streamlit o corpo do
        # `if botao:` roda no mesmo run em que o botão foi desenhado — sem isso, o
        # os dois botões ficavam na tela durante os minutos de geração, ainda
        # clicáveis: um segundo clique em "Confirmar" reiniciava o run e gerava
        # tudo de novo, e "Cancelar" matava a geração
        # em curso, perdendo as imagens que só existem em memória.
        _painel_confirmacao = st.empty()
        with _painel_confirmacao.container():
            if n_viaveis == 0:
                st.error(
                    "⛔ Nenhuma imagem pode ser gerada agora — todas estão bloqueadas por falta de informação. "
                    "Forneça os dados solicitados e clique em **Analisar novamente**."
                )
            else:
                aviso_bloqueadas = (
                    f" ({n_bloqueadas} bloqueada(s) por dados insuficientes — serão ignoradas)"
                    if n_bloqueadas else ""
                )
                if aviso_bloqueadas:
                    st.info(f"Serão geradas **{n_viaveis} imagem(ns)**{aviso_bloqueadas}.")

            # Gerar por cima de uma galeria pronta descarta tudo o que já foi
            # aprovado. Antes isso acontecia com um clique e sem aviso.
            _ja_tem = len(st.session_state.get("img_galeria") or [])
            _ciente = True

            if _ja_tem:
                st.warning(
                    f"⚠️ Você já tem **{_ja_tem} imagem(ns) gerada(s)**. Gerar de novo "
                    "**descarta todas** e recomeça do zero.\n\n"
                    "Para mudar só uma, peça no **Assistente IA** citando o número "
                    "(ex.: *\"na Imagem 1, deixa o fundo totalmente branco\"*) — "
                    "as demais ficam intactas."
                )
                _ciente = st.checkbox(
                    f"Sim, descartar as {_ja_tem} imagens e gerar tudo de novo",
                    key="img_confirma_descarte",
                )

            # A TRAVA DO PLANO MISTURADO SAIU DAQUI — E A RETIRADA E O PONTO.
            #
            # Ela ficou pronta e medida em 30/09, e eu a tirei no mesmo dia.
            #
            # A prova de que "o plano estava misturado entre dois produtos"
            # vinha do .txt do historico que o dono baixou. Aquele arquivo
            # misturava as rodadas de DUAS pessoas, porque o contexto do log
            # era um global de processo (`log_imagem.py`, corrigido no mesmo
            # commit). A mistura era do LOG, nao do plano.
            #
            # `plano_misturado` continua avisando la em cima, porque com um
            # plano coerente ela devolve "" e nao custa nada. Mas TRANCAR o
            # botao com base num defeito que eu nao consigo provar e alarme
            # falso — e alarme falso ensina a desviar do alarme verdadeiro
            # junto. A trava volta quando um plano real vier misturado.

            col_cancelar, col_confirmar = st.columns(2)
            cancelar_clicado = col_cancelar.button("❌ Cancelar", use_container_width=True)
            confirmar_clicado = col_confirmar.button(
                "✅ Confirmar e gerar",
                type="primary",
                use_container_width=True,
                disabled=(n_viaveis == 0 or not _ciente),
            )

        if cancelar_clicado:
            # Cancelar nao gerou nada: a copia nao pode ficar para tras e ser
            # lida como "o plano da geracao" numa proxima peca refeita.
            limpar_plano_gerado()
            del st.session_state["img_triagem_plano"]
            del st.session_state["img_triagem_config"]
            st.rerun()

        if confirmar_clicado:
            # Primeira coisa: some com o painel. Daqui pra frente a tela mostra
            # só a barra de progresso — não há mais botão para clicar por engano.
            _painel_confirmacao.empty()
            try:
                # Aplica correção ao config se houver
                if correcao:
                    cfg["instrucoes_extras"] = (cfg.get("instrucoes_extras", "") + "\n\nCORREÇÃO DO COLABORADOR:\n" + correcao).strip()
                    st.session_state["img_triagem_config"] = cfg

                galeria = []
                st.session_state["img_fotos_originais"] = cfg["fotos_bytes"]
                st.session_state["img_fotos_sao_arte"] = False
                # O MOTIVO DA FALHA PRECISA SOBREVIVER AO RERUN.
                #
                # Cada peca que falhava escrevia `st.warning("Falhou em X:
                # motivo")` na pagina. No fim do laco vem `st.rerun()`, que
                # redesenha a tela do zero — e leva os avisos junto. O
                # colaborador via "8 no plano, 1 na galeria" e nada mais. Foi
                # literalmente a frase dele: "gerou somente 4 imagens sem
                # motivo algum". O motivo tinha sido escrito, e apagado.
                falhas_geracao = []
                st.session_state.pop("img_falhas_geracao", None)
                st.session_state.pop("img_galeria_salva", None)
                # ARQUIVAR, nao apagar. Apagar aqui desarmava a rede de
                # seguranca exatamente no momento em que ela era necessaria:
                # entre o clique e a primeira imagem nova nao havia nem sessao
                # nem disco, e uma recarga de tela levava as imagens antigas —
                # ja pagas — junto com o pedido de correcao.
                try:
                    import rascunho as _rasc
                    _rasc.arquivar(usuario_logado)
                except Exception:
                    pass
                barra = st.progress(0.0, text="Iniciando geração...")
                try:
                    import log_imagem
                    log_imagem.registrar(
                        "gerar_tudo", cfg.get("instrucoes_extras", ""),
                        resultado=f"{len(itens_viaveis)} imagem(ns) a gerar"
                        + (f" · descartou {_ja_tem}" if _ja_tem else ""),
                    )
                except Exception:
                    pass

                # Gera APENAS os tipos viáveis aprovados na triagem
                # O RÓTULO OFICIAL, NÃO O QUE A IA ESCREVEU.
                #
                # `item["tipo"]` é o nome que a IA do plano inventou —
                # "Imagem de marketing — benefícios" no lugar de "2 —
                # Benefícios do produto". Levar esse nome adiante fazia o
                # preset do tipo não ser achado, e a peça ia para o gerador
                # SEM as regras dela. O prompt real de 24/09 mostrou isso nas
                # oito de uma vez.
                tipos_viaveis = [tipo_canonico(item, cfg.get("tipos"))
                                 for item in itens_viaveis]
                tipos = tipos_viaveis if tipos_viaveis else cfg["tipos"]

                # SE AINDA SOBROU TIPO SEM NUMERO, ISSO TEM DE APARECER.
                #
                # Tipo sem numero nao acha preset, cai em `modo_fundo_do_tipo`
                # = "padrao" e em `pode_ter_texto` = True. Foi assim que a
                # ambientacao — foto editorial sem texto — saiu com titulo,
                # selo de beneficio e um "COMPRAR AGORA" desenhado. O
                # `tipo_canonico` resolve pelo numero do plano; quando nem
                # isso houver, o Studio diz, em vez de gerar errado calado.
                _sem_numero = [t for t in tipos
                               if numero_do_tipo(t) is None
                               and t != PERSONALIZADO
                               and not eh_rotulo_de_ajuste(t)]
                if _sem_numero:
                    st.warning(
                        "⚠️ Não reconheci o tipo oficial de: "
                        + ", ".join(f"**{t}**" for t in _sem_numero)
                        + ". Essas peças vão sair com as regras genéricas — "
                        "sem o preset do tipo, e a de ambientação pode vir "
                        "com texto. Clique em **Analisar novamente** antes de "
                        "publicar o que sair delas."
                    )

                import time as _time_gen
                import threading as _threading

                # A DIRECAO DE ARTE DECIDIDA NA TRIAGEM, HERDADA PELAS OITO.
                #
                # Ela sai da MESMA chamada que ja montava o plano — nao ha
                # chamada nova. Plano antigo, salvo antes deste campo existir,
                # devolve {} e cada peca volta a deduzir: e o comportamento de
                # antes, que continua valendo enquanto o colaborador nao
                # clicar em "Analisar novamente".
                _direcao_arte = (st.session_state.get("img_triagem_plano", {})
                                 .get("direcao_de_arte") or {})
                if _direcao_arte.get("nome"):
                    st.caption(f"🎨 Direção de arte das 8: **{_direcao_arte['nome']}**"
                               + (f" · {_direcao_arte.get('posicionamento','')}"
                                  if _direcao_arte.get("posicionamento") else ""))

                # Indexa os itens da triagem por tipo para lookup rápido
                # INDEXADO PELO TIPO CANONICO — e pelo rotulo cru tambem.
                #
                # A chave era so `_pi["tipo"]`, o nome inventado pela IA, e a
                # busca vinha com o tipo canonico: nunca casava, e a peca ia
                # ao gerador sem a composicao planejada, sem a cena e sem a
                # copy exata.
                _plano_por_tipo = {}
                _plano_items = st.session_state.get("img_triagem_plano", {}).get("plano", [])
                for _pi in _plano_items:
                    _plano_por_tipo[_pi.get("tipo", "")] = _pi
                    _plano_por_tipo[tipo_canonico(_pi, cfg.get("tipos"))] = _pi

                # ── O NOME DO PRODUTO, MARCADO AQUI E NÃO SÓ NO TOPO ───
                #
                # O contexto do log é marcado uma vez por desenho da tela,
                # lá em cima, lendo `img_nome_produto` do `session_state`.
                # E `definir_produto_da_sessao` só escreve esse campo no FIM
                # da geração.
                #
                # Resultado, medido no Studio do dono em 02/10: ele gerou a
                # "Caneca Térmica Medieval 400Ml" pelo código da descrição,
                # as 7 peças saíram, e o histórico de prompts dela veio com
                # 143 CARACTERES — só o cabeçalho. O log gravou
                # `produto = ""` nas sete linhas, e o filtro por nome não
                # achou nenhuma. É a mesma causa das seis peças "sem nome"
                # no .txt que ele mandou antes.
                #
                # Na passada em que a geração roda, o nome ainda não está no
                # `session_state` — mas ESTÁ no `cfg`, que é de onde o prompt
                # tira tudo. Então marca-se aqui, com a fonte certa, antes de
                # qualquer thread nascer: `alvo_com_contexto` captura o
                # contexto no NASCIMENTO da thread, e daqui para baixo ele já
                # tem nome.
                #
                # A marcação do topo continua, para os caminhos que não
                # passam por aqui (ajuste fino avulso, refazer).
                try:
                    import log_imagem as _li_ger
                    _li_ger.marcar_contexto(
                        produto=cfg.get("nome_produto", ""),
                        usuario=usuario_logado)
                except Exception:
                    # Marcar contexto é apoio, não requisito.
                    pass

                # ── O STUDIO OLHA AS REFERÊNCIAS DE AMBIENTAÇÃO ─────────
                #
                # UMA leitura para as oito peças. Uma por imagem seria pagar
                # oito vezes pela mesma foto — e a escolha não melhora, porque
                # a pergunta ("que cenário é este?") é a mesma nas oito.
                #
                # Falhar aqui não pode impedir a geração: sem descrição, a
                # peça sai com a ambientação que o colaborador escreveu, que é
                # exatamente o comportamento de antes deste bloco.
                _amb_desc = {"cenarios": []}
                _refs_amb = cfg.get("refs_ambientacao") or []
                if _refs_amb:
                    barra.progress(0.0, text="Olhando as referências de "
                                             "ambientação…")
                    import ambientacao_ref as _ar
                    _amb_desc = _ar.descrever(_refs_amb, list(tipos),
                                              cfg.get("nome_produto", ""))
                    if _amb_desc.get("erro"):
                        st.warning(
                            "🏙️ Não consegui ler as referências de "
                            f"ambientação ({_amb_desc['erro']}). As imagens "
                            "saem com o tema escrito, sem elas.")
                    else:
                        for _l in _ar.resumo(_amb_desc, list(tipos)):
                            st.caption("🏙️ " + _l)

                # TRES FALHAS IGUAIS SEGUIDAS NAO SAO AZAR — E O MOTOR FORA
                # DO AR, E INSISTIR CUSTA O TEMPO DELE.
                #
                # Com o primario 404 e o reserva sem cota, cada peca ainda
                # esperava ate 5 minutos antes de desistir. Oito pecas assim
                # sao 40 minutos de barra andando para entregar o que ja se
                # sabia na terceira. Quando o motivo e o MESMO tres vezes, o
                # laco para e diz por que.
                _abortou = ""
                for i, tipo in enumerate(tipos):
                    _ultimas = [m for _t, m in falhas_geracao[-3:]]
                    if len(_ultimas) == 3 and len(set(_ultimas)) == 1:
                        _abortou = _ultimas[0]
                        for _t_resto in tipos[i:]:
                            falhas_geracao.append(
                                (_t_resto, "não foi tentada: os três motores "
                                           "anteriores falharam pelo mesmo "
                                           "motivo, então parei."))
                        st.session_state["img_falhas_geracao"] = list(falhas_geracao)
                        break
                    barra.progress(i / len(tipos), text=f"Gerando {i+1}/{len(tipos)}: {tipo[:50]}...")
                    # Sem sleep aqui — o _GEMINI_LIMITER em gerar_imagem_ia já respeita o RPM
                    try:
                        # A MESMA função que o botão de regerar e o chat usam.
                        # Duas montagens do mesmo prompt discordam — é só
                        # questão de quando.
                        prompt_final = montar_prompt_imagem(
                            tipo,
                            cfg.get("instrucoes_extras", ""),
                            cfg.get("dados_descricao"),
                            cfg["nome_produto"],
                            refs_layout_nomes=cfg.get("refs_layout_nomes", []),
                            instrucao_layout=cfg.get("instrucao_layout", ""),
                            plano_triagem=(_plano_por_tipo.get(tipo)
                                           or plano_do_tipo(tipo)),
                            direcao_arte=_direcao_arte,
                            # O que o colaborador escreveu MAIS o cenário
                            # que a visão escolheu para ESTE tipo. O texto
                            # dele vem primeiro: quem digitou manda.
                            ambientacao=(
                                (cfg.get("ambientacao", "") or "")
                                + ("\n\n" + _bloco_amb if (_bloco_amb := (
                                    __import__("ambientacao_ref")
                                    .para_o_tipo(_amb_desc, tipo))) else "")),
                        )
                        # ── Geração em thread separada ──────────────────────────
                        # Mantém o WebSocket vivo durante a chamada Gemini (30-60s)
                        # enviando atualizações a cada segundo para o Railway não
                        # fechar a conexão por inatividade.
                        # Passa fotos do produto e refs de layout SEPARADAMENTE para o Gemini
                        # As fotos do produto são âncora visual; as refs de layout guiam a composição
                        _refs_layout_arg = cfg.get("refs_layout_bytes") or None
                        _res = {"img": None, "erro": None, "done": False}
                        _thread = _threading.Thread(
                            target=_li_thread.alvo_com_contexto(_gerar_imagem_thread),
                            args=(prompt_final, cfg["fotos_bytes"], _res),
                            kwargs={
                                "refs_layout": _refs_layout_arg,
                                "refs_layout_nomes": cfg.get("refs_layout_nomes", []),
                                "tipo": tipo,
                            },
                            daemon=True,
                        )
                        _thread.start()
                        _t0 = _time_gen.time()
                        while not _res["done"]:
                            _seg = int(_time_gen.time() - _t0)
                            if _seg >= 300:
                                _res["erro"] = "Tempo limite de 5 min atingido. Tente novamente."
                                _res["done"] = True
                                break
                            barra.progress(i / len(tipos), text=f"Gerando {i+1}/{len(tipos)}: {tipo[:40]}... ({_seg}s)")
                            _time_gen.sleep(1)
                        img_bytes, erro_gen = _res["img"], _res["erro"]
                        # ────────────────────────────────────────────────────────
                        if erro_gen:
                            falhas_geracao.append((tipo, str(erro_gen)))
                            st.session_state["img_falhas_geracao"] = list(falhas_geracao)
                            try:
                                log_imagem.registrar(
                                    "gerar_falhou", cfg.get("instrucoes_extras", ""),
                                    tipo=tipo, resultado=str(erro_gen)[:400])
                            except Exception:
                                pass
                            st.warning(f"⚠️ Falhou em '{tipo}': {erro_gen}")
                            continue

                        # ── O texto escrito na imagem foi conferido? ────────
                        #
                        # O gerador desenha as letras, e erra: saiu "Portátile
                        # e compacto", "Apretica newtona estético", "função
                        # relievarriamento do stresse" numa peça de benefícios
                        # que chegou até a tela do gestor.
                        #
                        # Corretor não pega — não há texto, há pixel. A única
                        # forma é LER a imagem, e é o que revisar_texto faz,
                        # refazendo com as palavras certas e LENDO DE NOVO. A
                        # refação sem releitura era o buraco: a peça saía com
                        # "foi refeita, confira" e continuava errada.
                        def _gerar_de_novo(_p, _refs=_refs_layout_arg, _t=tipo):
                            _r = {"img": None, "erro": None, "done": False}
                            _th = _threading.Thread(
                                target=_li_thread.alvo_com_contexto(_gerar_imagem_thread),
                                args=(_p, cfg["fotos_bytes"], _r),
                                kwargs={"refs_layout": _refs,
                                        "refs_layout_nomes": cfg.get("refs_layout_nomes", []),
                                        "tipo": _t},
                                daemon=True)
                            _th.start()
                            _t0r = _time_gen.time()
                            while not _r["done"]:
                                if int(_time_gen.time() - _t0r) >= 300:
                                    _r["erro"] = "tempo limite ao refazer."
                                    break
                                _time_gen.sleep(1)
                            return _r["img"], _r["erro"]

                        # AS DUAS CONFERENCIAS, pela porta unica.
                        #
                        # A revisao de texto le o que esta ESCRITO; a da peca
                        # OLHA a imagem ao lado das fotos. Texto primeiro
                        # porque trocar a copy e uma troca de string, e
                        # refazer o quadro e uma geracao paga.
                        #
                        # Pela porta, e nao pelas duas soltas: este laco e os
                        # dois caminhos de refazer respondem a MESMA pergunta,
                        # e duas respostas passam a discordar — a questao e so
                        # quando. Foi a Forma 5 dentro da propria correcao que
                        # a criou.
                        img_bytes, _rel_txt, _rel_peca = revisar_tudo(
                            img_bytes, tipo,
                            fotos_ref=cfg["fotos_bytes"],
                            gerar=_gerar_de_novo,
                            prompt_base=prompt_final,
                            pedido=cfg.get("instrucoes_extras", ""),
                            dados_descricao=cfg.get("dados_descricao") or {},
                            aviso=lambda t, _i=i: barra.progress(
                                _i / len(tipos), text=t[:70]),
                        )
                        # Falha de revisao vira aviso no topo da aba, e nao so
                        # embaixo desta imagem: quem chega depois precisa saber
                        # que a revisao esta fora do ar ANTES de gerar de novo.
                        registrar_revisao(_rel_txt)

                        galeria.append({
                            "tipo": tipo,
                            "bytes": img_bytes,
                            "aprovado": False,
                            # O veredito de IMAGEM viaja com a peca, como o de
                            # texto: a tela diz o defeito na peca certa.
                            "peca": _rel_peca,
                            # O veredito da revisao de texto viaja com a imagem:
                            # a tela precisa poder dizer "confira antes de
                            # publicar" na peca certa, e nao num aviso geral.
                            "texto": _rel_txt,
                            # Guarda o prompt exato e o motor que gerou ESTA imagem.
                            # Sem isso não dá para saber se o resultado ruim veio de
                            # prompt errado ou de ter caído no fallback texto-puro.
                            "diag": _res.get("diag") or {},
                        })
                        # Grava a cada imagem, nao so no fim do laco.
                        #
                        # A galeria so era publicada depois da ultima imagem. Uma
                        # queda de WebSocket no meio (aconteceu em 27/08, na
                        # quarta de seis) matava a sessao e levava junto tudo que
                        # ja tinha sido gerado — e pago. Agora cada imagem pronta
                        # ja esta no session_state e em disco.
                        st.session_state["img_galeria"] = list(galeria)
                        st.session_state.setdefault("img_nome_produto",
                                                    cfg.get("nome_produto", ""))
                        st.session_state.setdefault("img_codigo",
                                                    cfg.get("codigo", ""))
                        # Pelo helper: falha de gravacao deixa de ser muda.
                        guardar_rascunho(usuario_logado, "geracao")
                    except Exception as _e_img:
                        falhas_geracao.append(
                            (tipo, f"{type(_e_img).__name__}: {_e_img}"))
                        st.session_state["img_falhas_geracao"] = list(falhas_geracao)
                        try:
                            log_imagem.registrar(
                                "gerar_falhou", cfg.get("instrucoes_extras", ""),
                                tipo=tipo,
                                resultado=f"{type(_e_img).__name__}: {_e_img}"[:400])
                        except Exception:
                            pass
                        st.warning(f"⚠️ Erro inesperado em '{tipo}': {_e_img}")
                        continue

                barra.progress(1.0, text=f"Concluído! {len(galeria)}/{len(tipos)} imagens geradas.")
                if _abortou:
                    st.session_state["img_abortou_geracao"] = _abortou
                else:
                    st.session_state.pop("img_abortou_geracao", None)
                # Este placar morre no rerun como os avisos. Guardado, ele
                # aparece em cima da galeria: "1 de 8" com nome e motivo das 7.
                st.session_state["img_placar_geracao"] = (len(galeria), len(tipos))
                st.session_state["img_falhas_geracao"] = list(falhas_geracao)

                if galeria:
                    for k in [k for k in st.session_state if k.startswith("_pasta_")]:
                        del st.session_state[k]
                    st.session_state["img_galeria"] = galeria
                    definir_produto_da_sessao(cfg["nome_produto"],
                                              codigo=cfg.get("codigo", ""))
                    st.session_state["img_fotos_originais"] = cfg["fotos_bytes"]
                    # A MARCA DE "ISSO E ARTE" TEM DE SER DESLIGADA AQUI.
                    #
                    # `img_fotos_sao_arte` so era LIGADA, nunca desligada. Quem
                    # usasse o Ajuste Fino avulso uma vez carregava a marca
                    # para sempre na sessao — e a geracao seguinte, com fotos
                    # de produto de verdade, ainda recusava refazer dizendo
                    # "esta imagem entrou pelo modo Ajuste Fino". Era mentira,
                    # e foi o que a colaboradora leu tres vezes seguidas
                    # enquanto pedia para refazer a Imagem 1.
                    #
                    # O que esta em `cfg["fotos_bytes"]` aqui sao as fotos do
                    # PRODUTO, subidas nesta geracao. Entao a marca cai.
                    st.session_state["img_fotos_sao_arte"] = False
                    st.session_state["img_dados_descricao"] = cfg.get("dados_descricao") or {}
                    if st.session_state["img_dados_descricao"] and not st.session_state["img_dados_descricao"].get("peso"):
                        st.session_state["img_dados_descricao"]["peso"] = st.session_state.get("desc_dados_atual", {}).get("peso", "")
                    st.session_state["img_instrucoes_originais"] = cfg.get("instrucoes_extras", "")
                    st.session_state["img_chat_log"] = []
                    import atividades
                    atividades.registrar_atividade(
                        usuario_logado,
                        f"Imagem ({len(galeria)} geradas)",
                        cfg["nome_produto"],
                        ", ".join(t[:20] for t in tipos_viaveis[:3]) + ("..." if len(tipos_viaveis) > 3 else ""),
                        codigo=cfg.get("codigo", ""),
                        cor=cfg.get("dados_descricao", {}).get("cor", "") if cfg.get("dados_descricao") else "",
                        medidas=cfg.get("dados_descricao", {}).get("medidas", "") if cfg.get("dados_descricao") else "",
                    )
                    # O DADO ANTES DO SINAL. As duas chaves abaixo sao o
                    # sinal de "plano ja consumido", e e ele que impede o
                    # painel de confirmacao de voltar por cima da galeria.
                    # Elas caem; o que estava dentro delas fica.
                    guardar_plano_gerado()
                    del st.session_state["img_triagem_plano"]
                    del st.session_state["img_triagem_config"]
                    st.rerun()
                else:
                    st.error("❌ Nenhuma imagem foi gerada com sucesso. Verifique os avisos acima e tente novamente.")
            except Exception as _e_gerar:
                st.error(
                    f"❌ Erro durante a geração: {_e_gerar}\n\n"
                    "Suas sessões e dados estão preservados. Tente novamente ou reduza o número de imagens."
                )

    # ── O PLACAR DA ÚLTIMA GERAÇÃO, E O MOTIVO DE CADA FALTA ──────────────────
    #
    # Fica FORA do `if img_galeria`: quando nenhuma peça sai, é justamente
    # quando o motivo é mais necessário.
    #
    # Ele existe porque o laço de geração termina em `st.rerun()`, e o rerun
    # redesenha a página do zero. Os `st.warning("Falhou em X: motivo")` que o
    # laço escreveu morrem ali, e o que sobra na tela é a galeria com menos
    # peças do que o plano prometeu — sem uma palavra sobre as que faltam.
    _placar = st.session_state.get("img_placar_geracao")
    _falhas_ger = st.session_state.get("img_falhas_geracao") or []

    # ── A PECA QUE NEM CHEGOU A SER TENTADA ──────────────────────────────
    #
    # Dono, 30/09: "nao gerou a imagem presenteando". E depois: "investigue as
    # fotos nao geradas".
    #
    # O caminho, e ele nao tem bug nenhum — tem um BURACO:
    #   1. a triagem marca a peca como nao viavel por falta de informacao;
    #   2. a tela do PLANO lista essa peca, com nome e com o que falta;
    #   3. a geracao roda so as viaveis;
    #   4. no fim, `img_triagem_plano` e apagada — ela e o sinal de "plano
    #      consumido", que impede o painel de voltar por cima da galeria;
    #   5. o painel das bloqueadas vive DENTRO do `if` dessa chave, e some
    #      junto;
    #   6. o placar compara a galeria com `len(tipos)`, e `tipos` ja sao so as
    #      viaveis — entao ele diz "8 de 8", em verde.
    #
    # A peca desaparece por completo na hora em que a galeria abre: sem nome,
    # sem motivo, sem aviso. Quem gerou ve a ausencia; a tela nunca a menciona.
    #
    # O DADO NAO SE PERDEU: `guardar_plano_gerado` salva o plano inteiro, com
    # as bloqueadas e o `pergunta_info` de cada uma, numa chave que sobrevive.
    # Ninguem lia essa parte dele. Uma leitura resolve — e ela fica FORA do
    # `if` do placar, porque bloqueada nao e falha de geracao: sao duas
    # coisas diferentes e as duas precisam de nome.
    _bloqueadas_ger = pecas_bloqueadas_da_geracao()
    if _bloqueadas_ger and st.session_state.get("img_galeria"):
        st.markdown("---")
        st.warning(
            f"🚫 **{len(_bloqueadas_ger)} peça(s) não foram geradas** — elas "
            "ficaram bloqueadas por falta de informação e nem chegaram a ser "
            "tentadas. Isto é diferente de falha na geração: nada foi gasto "
            "com elas."
        )
        for _it_b in _bloqueadas_ger:
            _falta = str(_it_b.get("pergunta_info", "") or "").strip()
            st.markdown(
                f"- **{_it_b.get('numero', '')}. {_it_b.get('tipo', '?')}** — "
                + (f"falta: {_falta}" if _falta
                   else "faltou informação e a triagem não disse qual"))
        st.caption("Responda no **Assistente IA** ou preencha os dados e "
                   "clique em **Analisar novamente** para gerar só estas.")

    if _placar and _placar[0] < _placar[1]:
        _feitas, _pedidas = _placar
        st.markdown("---")
        st.error(
            f"⚠️ A última geração entregou **{_feitas} de {_pedidas}** imagens. "
            f"As {_pedidas - _feitas} que faltam falharam — o motivo de cada uma "
            "está abaixo."
        )
        _motivo_aborto = st.session_state.get("img_abortou_geracao")
        if _motivo_aborto:
            st.info(
                "⏹️ Parei antes do fim: três peças seguidas falharam pelo mesmo "
                "motivo, e insistir nas outras só gastaria tempo. Resolva o "
                "motivo abaixo e clique em **Analisar novamente**.\n\n"
                + str(_motivo_aborto).replace("$", r"\$")
            )
        for _t_falha, _motivo in _falhas_ger:
            # Cifrão cru vira fórmula no markdown do Streamlit, e mensagem de
            # erro de cobrança tem cifrão.
            st.warning(f"**{_t_falha}** — " + str(_motivo).replace("$", r"\$"))
        if st.button("Entendi, esconder este aviso", key="img_limpa_placar"):
            st.session_state.pop("img_placar_geracao", None)
            st.session_state.pop("img_falhas_geracao", None)
            st.session_state.pop("img_abortou_geracao", None)
            st.rerun()

    # ── GALERIA ───────────────────────────────────────────────────────────────
    if "img_galeria" in st.session_state and st.session_state["img_galeria"]:
        st.markdown("---")
        _msgs_chat = st.session_state.pop("chat_img_msgs", None)
        if _msgs_chat:
            st.info("\n\n".join(_msgs_chat))
        galeria = st.session_state["img_galeria"]
        nome_gal = st.session_state.get("img_nome_produto", "produto")
        codigo_gal = st.session_state.get("img_codigo", "")

        # ── O PLACAR DO LOTE, ANTES DE QUALQUER OUTRA COISA ──────────────────
        #
        # "8 na galeria" nao e "8 entregues". No teste de 05/10 havia DUAS
        # pecas com cartao vermelho de "nao publique assim" e o chat
        # respondeu ao dono "nenhuma deixou de ser gerada — as 8 estao na
        # galeria". Os dois estavam falando de coisas diferentes.
        _placar = placar_do_lote(
            galeria, st.session_state.get("img_planejadas") or len(galeria))
        if _placar["reprovadas"] or _placar["nao_conferidas"] or _placar["pendentes"]:
            st.warning(f"📋 **Lote:** {frase_do_placar(_placar)}")
        else:
            st.success(f"📋 **Lote:** {frase_do_placar(_placar)}")

        # ── DIAGNÓSTICO DA GERAÇÃO ────────────────────────────────────────────
        # Sem isto não há como saber se uma imagem ruim veio de prompt errado ou
        # de ter caído no fallback do Gemini, que gera SEM ver as fotos.
        _sem_foto = [g for g in galeria if (g.get("diag") or {}).get("refs_enviadas", 1) == 0]
        if _sem_foto:
            st.error(
                f"⚠️ **{len(_sem_foto)} de {len(galeria)} imagens foram geradas SEM as suas fotos.** "
                "O gerador principal falhou e o sistema caiu no motor reserva, que só recebe texto — "
                "ele nunca viu o produto real, então inventou um. É por isso que a cor e o formato saem "
                "errados. Abra o painel abaixo e me mande o erro."
            )

        with st.expander("🔍 Prompt e motor usados em cada imagem", expanded=bool(_sem_foto)):
            # Pelo índice, pelo mesmo motivo do seletor de cima: com rótulos
            # repetidos, o diagnóstico mostrado era o da primeira imagem.
            _i_diag = st.selectbox(
                "Imagem", list(range(len(galeria))), key="img_diag_sel",
                label_visibility="collapsed",
                format_func=lambda i: f"Imagem {i + 1} · {galeria[i].get('tipo', '?')}")
            _g_diag = galeria[_i_diag] if 0 <= _i_diag < len(galeria) else None
            _d = (_g_diag or {}).get("diag") or {}

            if not _d:
                st.caption("Sem diagnóstico — imagem gerada antes desta atualização.")
            else:
                _c1, _c2, _c3 = st.columns(3)
                _c1.markdown(f"**Motor**  \n{_d.get('motor', '—')}")
                _c2.markdown(
                    f"**Fotos enviadas**  \n{_d.get('refs_enviadas', '—')} "
                    f"de {_d.get('fotos_disponiveis', '—')} disponíveis"
                )
                _c3.markdown(
                    f"**Tamanho pedido / recebido**  \n"
                    f"{_d.get('size_pedido', '—')} → {_d.get('tamanho_bruto', '—')}"
                )
                # O QUE O SISTEMA MEDIU E NÃO CONTAVA A NINGUÉM.
                #
                # `checar_comunicacao.py` achou cinco campos gravados no
                # diagnóstico e nunca mostrados. Três deles respondem
                # exatamente as perguntas que custaram o dia 29/09:
                #
                #   input_fidelity  a peça foi gerada PRESERVANDO o produto?
                #                   O Gemini não aceita esse parâmetro; sem
                #                   ele, o produto é redesenhado — e era isso
                #                   que fazia o Ajuste Fino reprovar sem que
                #                   ninguém soubesse por quê.
                #   medida          os defeitos MEDIDOS na peça, por
                #                   `medir_imagem.problemas`. O sistema já
                #                   media e guardava para si.
                #   ref_layout      a referência de layout enviada
                #                   correspondeu ao tipo, ou foi ignorada?
                #
                # `size_pedido` já estava na tela e `input_fidelity` não, a
                # duas linhas de distância no código que os grava: a Forma 1
                # desta base, de novo.
                _fid = _d.get("input_fidelity")
                st.markdown(
                    "**Produto preservado**  \n"
                    + ("✅ sim — `input_fidelity=" + str(_fid) + "`" if _fid
                       else "⚠️ NÃO — este motor não preserva o produto, "
                            "então ele foi redesenhado")
                )
                if _d.get("ref_layout"):
                    st.markdown(f"**Referência de layout**  \n{_d['ref_layout']}")
                if _d.get("medida"):
                    st.warning(
                        "📐 **O que a medição encontrou nesta peça:** "
                        + str(_d["medida"]))
                _pf, _ff = _d.get("peso_final"), _d.get("formato_final")
                if _pf or _ff:
                    st.caption(f"Arquivo final: {_ff or '—'} · {_pf or '—'}")
                if _d.get("enquadramento"):
                    # A EXPLICACAO DA MARGEM, QUE O SISTEMA SABIA E NAO DIZIA.
                    #
                    # Dono, 30/09: "imagens com margem". O Studio MEDIA isso —
                    # gravava "o motor devolveu 1536x1024 em vez de quadrada,
                    # as faixas laterais foram preenchidas pelo Studio" — e o
                    # campo nao chegava a tela. O oitavo verificador dava verde
                    # porque a unica leitura dele era a linha que concatena a
                    # mensagem NELA MESMA, do mesmo lado do balcao.
                    st.warning(
                        "🖼️ **Por que esta peça tem margem:** "
                        + str(_d["enquadramento"]))
                if _d.get("proporcao_recusada"):
                    # A MESMA FAMILIA: o pedido de imagem quadrada foi RECUSADO
                    # pela API, o Studio repetiu sem ele, e a unica pista disso
                    # morava no stderr do Railway.
                    st.warning(
                        "📏 **O motor recusou o pedido de imagem quadrada** — "
                        "por isso ela voltou retangular e precisou de "
                        "preenchimento. Detalhe: "
                        + str(_d["proporcao_recusada"]))
                if _d.get("proporcao_pedida"):
                    # QUAL FORMA DE PEDIR O QUADRADO COLOU — e ela precisa
                    # aparecer, nao so ser guardada.
                    #
                    # O oitavo verificador reprovou esta linha antes de ela
                    # existir: eu tinha acabado de gravar `proporcao_pedida` e
                    # nao mostrava a ninguem — o defeito que ele foi escrito
                    # para pegar, cometido por mim na mesma hora.
                    #
                    # E ela responde a pergunta mais cara do dia: "esta peca
                    # saiu quadrada porque o motor aceitou o pedido, ou por
                    # acaso?". Com "sem proporcao" aqui, a margem da proxima
                    # peca ja tem explicacao antes de alguem perguntar.
                    _forma = str(_d["proporcao_pedida"])
                    if _forma == "sem proporcao":
                        st.warning(
                            "📏 **O motor não aceitou nenhuma forma de pedir "
                            "imagem quadrada** — a peça vem no formato que ele "
                            "escolher, e o Studio preenche as sobras. É daí "
                            "que vem a margem.")
                    else:
                        st.caption(f"📏 Imagem quadrada pedida ao motor por "
                                   f"`{_forma}` — e aceita.")
                if _d.get("sem_fotos"):
                    st.error("📷 **Esta peça foi feita SEM as fotos do "
                             "produto.** " + str(_d["sem_fotos"]))
                if _d.get("motor_reserva"):
                    # O AVISO QUE MORAVA NUMA THREAD E NUNCA APARECIA.
                    st.error(
                        "⚙️ **Esta peça NÃO foi feita pelo motor principal.** "
                        + str(_d["motor_reserva"]))
                if _d.get("erro_openai"):
                    st.warning(f"**Erro do gerador principal:**\n\n{_d['erro_openai']}")
                st.markdown("**Prompt exato enviado ao modelo:**")
                st.code(_d.get("prompt_final", "—"), language="text")

        # Miniaturas clicáveis
        _cols_gal = st.columns(4)
        for i, g in enumerate(galeria):
            with _cols_gal[i % 4]:
                # 20 caracteres cortavam o nome no meio ("Capa do", "Imagem
                # emocional — P") e o colaborador não sabia qual peça era qual.
                # O numero vem na legenda porque e assim que o colaborador e o
                # Assistente IA se referem a cada imagem ("Imagem 1", "Imagem 2"). Sem ele na tela, o
                # colaborador conta de cabeca — e a conta erra quando algum tipo
                # foi bloqueado na triagem e nao entrou na galeria.
                _rotulo = g["tipo"]
                _legenda = f"Imagem {i+1} · {_rotulo}"
                st.image(
                    g["bytes"],
                    caption=(_legenda[:52] + "…") if len(_legenda) > 52 else _legenda,
                    use_container_width=True,
                )
                # O aviso fica NA PECA, nao num alerta geral no topo: com oito
                # imagens na tela, "uma delas tem erro de texto" obriga a
                # procurar qual, e procurar e o que ninguem faz.
                _t = g.get("texto") or {}
                _aviso_txt = texto_em_aviso(_t)
                if _aviso_txt:
                    # "Nao conferido" era uma legenda cinza de 60 caracteres, do
                    # tamanho de um rodape — e por isso ninguem viu que a revisao
                    # estava falhando em TODAS as imagens. Falha de revisao agora
                    # grita: ela nao e aprovacao.
                    (st.error if _t.get("ok") is False else st.warning)(_aviso_txt)
                # E O QUE FOI VISTO NA IMAGEM, no mesmo lugar.
                #
                # Texto e peca sao duas perguntas diferentes e os dois
                # vereditos aparecem: portugues perfeito com a caneca de duas
                # alcas passava verde no primeiro e ninguem fazia o segundo.
                _pc_rel = g.get("peca") or {}
                _aviso_pc = peca_em_aviso(_pc_rel)
                if _aviso_pc:
                    (st.error if _pc_rel.get("ok") is False
                     else st.warning)(_aviso_pc)

        # Seleção da imagem ativa — pelo ÍNDICE, e não pelo rótulo.
        #
        # A lista era `[g["tipo"] for g in galeria]` e o índice saía de
        # `nomes_galeria.index(escolha)`. Duas imagens com o mesmo rótulo
        # faziam `.index()` devolver SEMPRE a primeira: a colaboradora
        # selecionava a Imagem 3, aparecia a 1, e os botões de salvar e
        # ajustar agiam na 1. Ela mexia numa e via outra.
        #
        # Rótulo igual não é acidente: três ajustes finos seguidos com a mesma
        # instrução geram três "Ajuste Fino — chat melhora a cor dourada…".
        # Índice é único por construção, e não depende de ninguém escrever
        # nomes diferentes.
        idx_ativo = st.selectbox(
            "Imagem ativa (para ajustar ou baixar individualmente)",
            list(range(len(galeria))), key="img_escolha",
            format_func=lambda i: f"Imagem {i + 1} · {galeria[i].get('tipo', '?')}")
        imagem_ativa = galeria[idx_ativo]["bytes"]
        tipo_ativo = galeria[idx_ativo]["tipo"]

        # Exibe imagem ativa grande
        # use_container_width esticava a imagem para a largura inteira da tela:
        # 1200px de altura, ~3 telas de rolagem antes de chegar nos botoes.
        st.image(imagem_ativa, width=520)

        # Ações individuais
        # Ler o texto DESTA imagem, sob demanda.
        #
        # Serve a duas perguntas que antes so tinham resposta no meu chute: a
        # revisao esta funcionando? e o que exatamente esta escrito errado
        # nesta peca? Quando a revisao automatica falha (sem chave, API fora),
        # o erro aparece aqui em letra grande, e nao numa legenda cinza.
        # A revisao automatica ja leu esta imagem quando ela foi gerada; este
        # botao e para reler quando se quer ver A LISTA das palavras erradas,
        # ou depois de um ajuste feito fora do fluxo.
        # ── CONFERIR A PECA, SEM GERAR NADA ──────────────────────────────
        #
        # A conferencia automatica decide sozinha se REFAZ, e refazer custa
        # uma geracao. Antes de confiar nela para gastar, o dono tem de poder
        # ver o veredito dela numa peca que ele JA tem — inclusive numa que
        # ele sabe que esta errada. Uma leitura custa centavos.
        #
        # Sem este botao, a unica forma de descobrir se o leitor enxerga o
        # defeito seria gerar um produto inteiro de teste, que e o retrabalho
        # que esta correcao existe para acabar.
        _fotos_conf = st.session_state.get("img_fotos_originais") or []
        if st.button("🔎 Conferir esta peça (não gera nada)",
                     use_container_width=True,
                     key=f"conf_peca_{idx_ativo}",
                     disabled=not _fotos_conf,
                     help=("Olha a peça ao lado das fotos do produto e diz o "
                           "que achou de errado. Só lê — não refaz, não gasta "
                           "geração.")
                     if _fotos_conf else
                     "Precisa das fotos do produto desta sessão."):
            with st.spinner("Olhando a peça ao lado das fotos…"):
                _vd, _er_vd = conferir_peca(imagem_ativa, _fotos_conf,
                                            tipo_ativo)
            if _er_vd:
                st.error(f"**Não consegui conferir:** {_er_vd}\n\n"
                         "Enquanto isto aparecer, NENHUMA peça está sendo "
                         "olhada na geração — elas saem sem ninguém ver.")
            elif _vd.get("aprovada"):
                st.success("✅ Sem defeito de imagem: nada cortado, nada por "
                           "cima do produto, e o produto bate com as fotos.")
            else:
                st.error("❌ **A peça tem defeito:**\n\n"
                         + "\n".join(f"- {p}" for p in
                                      (_vd.get("problemas") or []))
                         + (f"\n\n**Como refazer:** {_vd['instrucao']}"
                            if _vd.get("instrucao") else ""))

        if st.button("🔤 Ler o texto desta imagem", use_container_width=True,
                     key=f"ler_txt_{idx_ativo}"):
            with st.spinner("Lendo o que está escrito na imagem…"):
                # Sem "pedido": aqui a pergunta e so se o que esta escrito
                # existe em portugues, e nao se bate com o que foi pedido.
                _v, _e = conferir_texto(imagem_ativa, "")
            # A leitura manual tambem conta como sinal de saude: se ela deu
            # certo, o aviso do topo sai sozinho no proximo rerun.
            registrar_revisao({"ok": None if _e else True, "erro": _e})
            if _e:
                st.error(f"**A revisão de texto não está funcionando:** {_e}\n\n"
                         "Enquanto isto aparecer, NENHUMA imagem está sendo "
                         "conferida — as peças saem sem ninguém ler.")
            elif not _v.get("tem_texto"):
                st.info("Nenhuma palavra escrita nesta imagem.")
            elif _v.get("correto"):
                st.success("✅ Texto conferido: português correto.")
            else:
                st.error(f"❌ Erros: {_v.get('erros', '')}")
                st.caption("Como deveria estar escrito:")
                st.code(_v.get("texto_correto", ""), language=None)

        col_dl, col_drive_ind = st.columns(2)
        col_dl.download_button(
            "⬇️ Baixar esta imagem",
            data=imagem_ativa,
            file_name=(f"{nome_gal}_{tipo_ativo[:20]}"
                       f".{extensao_de(imagem_ativa)}"),
            mime=_detectar_mime(imagem_ativa),
            use_container_width=True,
            key=f"dl_{idx_ativo}",
        )
        if col_drive_ind.button("☁️ Salvar esta no Drive", use_container_width=True, key=f"drive_ind_{idx_ativo}"):
            pasta_pai = st.secrets.get("DRIVE_PASTA_IMAGENS_ID", "")
            if not pasta_pai:
                st.error("DRIVE_PASTA_IMAGENS_ID não configurada.")
            else:
                with st.spinner("Enviando..."):
                    nome_pasta = f"{nome_gal} - {codigo_gal}".strip(" -")
                    # `diagnostico` aqui pelo mesmo motivo do botão de salvar
                    # tudo (que já o passava): sem ele, "a API falhou" e "a
                    # pasta não existe" viram a mesma lista vazia, e o Studio
                    # cria uma pasta duplicada do produto que já tem a dele.
                    _diag_ind = {}
                    pastas = buscar_pasta_produto(nome_gal, codigo_gal,
                                                  pasta_pai,
                                                  diagnostico=_diag_ind)
                    pasta_id = None
                    if _diag_ind.get("erro"):
                        st.error(
                            "Não consegui verificar se já existe pasta deste "
                            "produto no Drive, então não salvei — salvar agora "
                            "criaria uma pasta duplicada. Tente de novo em "
                            f"instantes.\n\n{_diag_ind['erro']}")
                    elif pastas:
                        pasta_id = pastas[0][0]
                    else:
                        pasta_id, err_pasta = criar_pasta_produto(nome_pasta, pasta_pai)
                        if err_pasta:
                            st.error(f"Erro ao criar pasta: {err_pasta}")
                            pasta_id = None
                    if pasta_id:
                        link, err_up = upload_para_pasta(
                            imagem_ativa,
                            f"{tipo_ativo[:20]}.{extensao_de(imagem_ativa)}",
                            pasta_id
                        )
                        if err_up:
                            st.error(f"Erro no upload: {err_up}")
                        else:
                            # Atualiza galeria com o link e registra no histórico
                            st.session_state["img_galeria"][idx_ativo]["link_drive"] = link
                            import atividades as _atv_ind
                            _atv_ind.registrar_atividade(
                                usuario_logado,
                                "Imagem (individual salva)",
                                nome_gal,
                                f"Tipo: {tipo_ativo[:40]}",
                                codigo=codigo_gal,
                                link_capa=link,
                            )
                            st.success(f"Salvo! [Abrir no Drive]({link})")

        # ── REGENERAR DO ZERO NA GALERIA ─────────────────────────────────────
        with st.expander("🔄 Regenerar esta imagem do zero", expanded=False):
            st.caption(
                "Use esta opção se a imagem gerou o produto **errado** ou está completamente incorreta. "
                "Vai gerar uma imagem completamente nova usando as fotos originais do produto."
            )
            if st.button(
                "🔄 Regenerar esta imagem agora",
                key=f"regen_btn_{idx_ativo}",
                type="primary",
                use_container_width=True,
            ):
                fotos_orig = st.session_state.get("img_fotos_originais") or []
                instrucoes_orig = st.session_state.get("img_instrucoes_originais", "")
                dados_desc = st.session_state.get("img_dados_descricao") or {}
                if not fotos_orig:
                    st.error("❌ Fotos originais não encontradas. Tente gerar novamente do início.")
                else:
                    import time as _time_regen
                    import threading as _threading_regen
                    prompt_regen = prompt_para_regerar(
                        tipo_ativo, instrucoes_orig, dados_desc, nome_gal)
                    _res_regen = {"img": None, "erro": None, "done": False}
                    # O MESMO BURACO DO REFAZER DO CHAT, no botao da galeria:
                    # sem `tipo` a peca perde a referencia de layout dela e o
                    # registro sai como "peca ?"; sem `refs_layout` ela e
                    # regerada ignorando o padrao aprovado da empresa.
                    _cfg_regen = config_da_geracao()
                    _threading_regen.Thread(
                        target=_li_thread.alvo_com_contexto(_gerar_imagem_thread),
                        args=(prompt_regen, fotos_orig, _res_regen),
                        kwargs={
                            "refs_layout": _cfg_regen.get("refs_layout_bytes") or None,
                            "refs_layout_nomes": _cfg_regen.get("refs_layout_nomes", []),
                            "tipo": tipo_ativo,
                        },
                        daemon=True,
                    ).start()
                    _barra_regen = st.progress(0.0, text=f"Regenerando {tipo_ativo[:30]}...")
                    _t0_regen = _time_regen.time()
                    while not _res_regen["done"]:
                        _seg_regen = int(_time_regen.time() - _t0_regen)
                        if _seg_regen >= 300:
                            _res_regen["erro"] = "Tempo limite de 5 min atingido."
                            _res_regen["done"] = True
                            break
                        _barra_regen.progress(min(0.9, _seg_regen / 60), text=f"Regenerando {tipo_ativo[:30]}... ({_seg_regen}s)")
                        _time_regen.sleep(1)
                    _barra_regen.progress(1.0, text="Concluído!")
                    nova_img_regen, err_regen = _res_regen["img"], _res_regen["erro"]
                    if err_regen:
                        st.error(f"❌ Erro: {err_regen}")
                    else:
                        # AS DUAS CONFERENCIAS, pela mesma porta do laco.
                        # Este botao tambem gera uma peca inteira do zero, e
                        # entregava sem ler o texto e sem olhar a imagem.
                        def _gerar_rg(_p, _fo=fotos_orig, _t=tipo_ativo):
                            _rr = {"img": None, "erro": None, "done": False}
                            # A conferencia refaz a peca: mesmos argumentos
                            # da primeira tentativa, senao a correcao volta
                            # com outro layout.
                            _tt = _threading_regen.Thread(
                                target=_li_thread.alvo_com_contexto(_gerar_imagem_thread),
                                args=(_p, _fo, _rr),
                                kwargs={
                                    "refs_layout": _cfg_regen.get(
                                        "refs_layout_bytes") or None,
                                    "refs_layout_nomes": _cfg_regen.get(
                                        "refs_layout_nomes", []),
                                    "tipo": _t,
                                },
                                daemon=True)
                            _tt.start()
                            _t0g = _time_regen.time()
                            while not _rr["done"]:
                                if int(_time_regen.time() - _t0g) >= 300:
                                    _rr["erro"] = "tempo limite ao refazer."
                                    break
                                _time_regen.sleep(1)
                            return _rr["img"], _rr["erro"]

                        nova_img_regen, _rel_t_rg, _rel_p_rg = revisar_tudo(
                            nova_img_regen, tipo_ativo, fotos_ref=fotos_orig,
                            gerar=_gerar_rg, prompt_base=prompt_regen,
                            pedido=instrucoes_orig,
                            dados_descricao=dados_desc,
                            aviso=lambda t: _barra_regen.progress(
                                1.0, text=t[:70]))
                        registrar_revisao(_rel_t_rg)
                        st.session_state["img_galeria"][idx_ativo]["bytes"] = nova_img_regen
                        st.session_state["img_galeria"][idx_ativo]["texto"] = _rel_t_rg
                        st.session_state["img_galeria"][idx_ativo]["peca"] = _rel_p_rg
                        guardar_rascunho(usuario_logado, "regerar imagem")
                        st.rerun()

        # ── AJUSTE FINO NA GALERIA ────────────────────────────────────────────
        with st.expander("✏️ Ajuste Fino — modificar somente algo específico nesta imagem", expanded=False):
            st.caption(
                "Descreva **somente o que deve mudar** — a IA vai preservar tudo o mais "
                "exatamente igual (fundo, cores, cena, textos existentes, detalhes do produto)."
            )
            instrucao_af_gal = st.text_area(
                "O que você quer modificar?",
                placeholder=(
                    "ex: Diminua o tamanho do produto para que fique em proporção realista ao cenário. "
                    "O produto mede aproximadamente 18cm.\n\n"
                    "ex: Remova a sombra embaixo do produto.\n\n"
                    "ex: Mude o fundo para branco puro, mantendo o produto igual."
                ),
                height=120,
                key=f"img_af_gal_{idx_ativo}",
            )
            # O que a conferencia achou da ultima tentativa nesta imagem.
            # Fica aqui, colado no botao, e nao numa mensagem que passa.
            _rel_ant = st.session_state.get("img_af_relato")
            if _rel_ant and _rel_ant[0] == idx_ativo:
                _txt_ant = relato_em_texto(idx_ativo + 1, _rel_ant[1])
                if _rel_ant[1].get("ok"):
                    st.success(_txt_ant)
                elif _rel_ant[1].get("ok") is None:
                    st.warning(_txt_ant)
                else:
                    st.error(_txt_ant)

            if st.button(
                "✏️ Aplicar Ajuste Fino nesta imagem",
                key=f"img_af_btn_{idx_ativo}",
                type="primary",
                use_container_width=True,
                disabled=not instrucao_af_gal.strip(),
            ):
                if not instrucao_af_gal.strip():
                    st.warning("Descreva o que deseja modificar.")
                else:
                    # Usa a imagem ATUAL da galeria como referência para o
                    # ajuste — e confere o resultado antes de devolver.
                    import time as _time_afg
                    import threading as _threading_afg
                    _res_afg = {"img": None, "relato": None, "done": False}
                    # A peça que está na tela é a que vai ser ajustada — sem
                    # isto a correção entraria na cadeia de outra imagem.
                    marcar_peca_em_ajuste(idx_ativo + 1)

                    def _rodar_afg(_ref=imagem_ativa,
                                   _ins=instrucao_af_gal.strip(),
                                   _tp=galeria[idx_ativo].get("tipo"),
                                   _rf=list(st.session_state.get(
                                       "img_fotos_originais") or []),
                                   _r=_res_afg):
                        try:
                            _r["img"], _r["relato"] = ajustar_com_conferencia(
                                _ref, _ins, tipo=_tp, referencias=_rf,
                                dados_descricao=st.session_state.get(
                                    "img_dados_descricao") or {},
                                aviso=lambda t: _r.__setitem__("fase", t))
                        except Exception as _e:
                            _r["img"], _r["relato"] = None, {
                                "ok": False, "tentativas": 0,
                                "erro": str(_e)[:160], "falta": "",
                                "colateral": ""}
                        finally:
                            _r["done"] = True

                    _threading_afg.Thread(target=_li_thread.alvo_com_contexto(_rodar_afg),
                                          daemon=True).start()
                    _barra_afg = st.progress(0.0, text="Aplicando ajuste fino...")
                    _t0_afg = _time_afg.time()
                    while not _res_afg["done"]:
                        _seg_afg = int(_time_afg.time() - _t0_afg)
                        if _seg_afg >= 600:
                            _res_afg["relato"] = {
                                "ok": False, "tentativas": 0, "falta": "",
                                "colateral": "",
                                "erro": "tempo limite de 10 min atingido."}
                            _res_afg["done"] = True
                            break
                        _barra_afg.progress(
                            min(0.9, _seg_afg / 120),
                            text=(f"{_res_afg.get('fase') or 'Aplicando ajuste fino'}… "
                                  f"({_seg_afg}s)"))
                        _time_afg.sleep(1)
                    _barra_afg.progress(1.0, text="Concluído!")
                    nova_img_af = _res_afg["img"]
                    _rel_afg = _res_afg["relato"] or {
                        "ok": None, "tentativas": 0, "erro": "sem relato",
                        "falta": "", "colateral": ""}
                    # O veredito fica guardado para aparecer DEPOIS do rerun,
                    # ao lado da imagem: dito antes, some junto com a tela.
                    st.session_state["img_af_relato"] = (idx_ativo, _rel_afg)
                    if nova_img_af:
                        st.session_state["img_galeria"][idx_ativo]["bytes"] = nova_img_af
                        guardar_rascunho(usuario_logado, "ajuste fino")
                        st.rerun()
                    else:
                        st.error(f"❌ {relato_em_texto(idx_ativo + 1, _rel_afg)}")
        # Os comandos do Assistente IA saíram daqui: viviam dentro
        # do `else` do modo e não rodavam no ✏️ Ajuste Fino. Agora
        # são `consumir_comandos_do_chat()`, chamada no começo da
        # página, antes de qualquer ramo.

        st.caption("💬 Para ajustar imagens, use o **Assistente IA** no menu lateral ou o painel **✏️ Ajuste Fino** acima.")
        st.markdown("---")

        # ── APROVAÇÃO E SALVAMENTO ─────────────────────────────────────────────
        # As imagens existem so na memoria da sessao ate serem salvas. Quem
        # encerra o expediente sem clicar perde a geracao inteira — ja aconteceu.
        if st.session_state.get("img_galeria_salva") != len(galeria):
            st.warning(
                f"⚠️ **As {len(galeria)} imagens ainda não estão no Drive.** "
                "Elas existem apenas nesta sessão: se você fechar o navegador, "
                "sair do Studio ou o site reiniciar, elas se perdem e a geração "
                "precisa ser refeita do zero. Salve antes de encerrar."
            )

        st.markdown("### ✅ Aprovar e salvar todas as imagens")
        pasta_pai = st.secrets.get("DRIVE_PASTA_IMAGENS_ID", "")

        # Busca pasta existente (cacheada em session_state para não bater na API a cada rerender)
        _cache_key = f"_pasta_{nome_gal}__{codigo_gal}"
        _busca_falhou = False
        if _cache_key not in st.session_state:
            if pasta_pai and nome_gal:
                _diag_busca = {}
                with st.spinner("Verificando pasta no Drive..."):
                    st.session_state[_cache_key] = buscar_pasta_produto(
                        nome_gal, codigo_gal, pasta_pai, diagnostico=_diag_busca
                    )
                if _diag_busca.get("erro"):
                    # Nao guarda em cache: a proxima tentativa deve consultar de novo
                    # em vez de tratar a falha como "pasta nao existe" para sempre.
                    del st.session_state[_cache_key]
                    _busca_falhou = True
                    st.warning(
                        "Não consegui verificar se já existe pasta desse produto no "
                        "Drive. Salvar agora criaria uma pasta duplicada — tente de "
                        f"novo em instantes.\n\n{_diag_busca['erro']}"
                    )
            else:
                st.session_state[_cache_key] = []
        pastas_encontradas = st.session_state.get(_cache_key, [])

        nome_pasta_novo = f"{nome_gal} - {codigo_gal}".strip(" -") if codigo_gal else nome_gal

        if pastas_encontradas:
            st.info(
                f"📁 Pasta encontrada no Drive: **{pastas_encontradas[0][1]}**\n\n"
                f"As imagens serão adicionadas a essa pasta (sem apagar o que já está lá)."
            )
            pasta_destino_id = pastas_encontradas[0][0]
            if len(pastas_encontradas) > 1:
                escolha_pasta = st.selectbox(
                    "Mais de uma pasta encontrada — qual usar?",
                    [p[1] for p in pastas_encontradas],
                    key="img_escolha_pasta",
                )
                pasta_destino_id = next(p[0] for p in pastas_encontradas if p[1] == escolha_pasta)
        else:
            st.info(f"📁 Será criada uma nova pasta no Drive: **{nome_pasta_novo}**")
            pasta_destino_id = None  # será criada no momento do clique

        # QUAIS imagens, e não "todas ou uma".
        #
        # Os dois botões abaixo eram tudo-ou-nada, e o seletor de imagem ativa
        # servia só para ver e baixar de uma em uma. Quem quer 2 das 3 tinha
        # que baixar as três e apagar uma, ou clicar três vezes no botão
        # individual. Aqui ela marca as que quer, e os dois botões passam a
        # agir sobre a marcação.
        _sel_idx = st.multiselect(
            "Quais imagens salvar / baixar",
            list(range(len(galeria))),
            default=list(range(len(galeria))),
            key="img_sel_salvar",
            format_func=lambda i: f"Imagem {i + 1} · {galeria[i].get('tipo', '?')}")
        _escolhidas = [galeria[i] for i in _sel_idx] or list(galeria)
        if not _sel_idx:
            st.caption("Nenhuma marcada — os botões abaixo valem para as "
                       f"{len(galeria)} imagens.")

        col_aprovar, col_zip = st.columns(2)

        if col_aprovar.button(
            f"☁️ APROVAR E SALVAR no Drive ({len(_escolhidas)} imagens)",
            type="primary",
            use_container_width=True,
            disabled=_busca_falhou,
        ):
            err_pasta = None
            if not pasta_pai:
                err_pasta = "DRIVE_PASTA_IMAGENS_ID não configurada nas Secrets."
                st.error(err_pasta)
            elif pasta_destino_id is None:
                with st.spinner("Criando pasta..."):
                    pasta_destino_id, err_pasta = criar_pasta_produto(nome_pasta_novo, pasta_pai)
                if err_pasta:
                    st.error(f"Não foi possível criar a pasta no Drive.\n\n{err_pasta}")
                else:
                    # Registra a pasta recem-criada no cache da sessao. Sem isto, o
                    # cache continuava dizendo "nao existe" e um segundo clique —
                    # comum quando o upload falha — criava OUTRA pasta com o mesmo
                    # nome. Foi assim que apareceram duas pastas vazias do mesmo
                    # album no Drive.
                    st.session_state[_cache_key] = [(pasta_destino_id, nome_pasta_novo)]

            # NÃO usar st.stop() aqui: isso impediria o botão de ZIP abaixo de
            # renderizar, e as imagens só existem em memória — o colaborador
            # perderia todo o trabalho. Em caso de falha, o ZIP é a saída.
            if err_pasta or not pasta_destino_id:
                st.info(
                    "⬇️ Suas imagens **não foram perdidas** — use o botão "
                    "\"Baixar todas em ZIP\" ao lado para salvá-las no seu computador."
                )
            else:
                links_salvos = []
                falhas = []
                barra_salvar = st.progress(0.0, text="Salvando imagens...")
                for i, g in enumerate(_escolhidas):
                    barra_salvar.progress(
                        i / len(_escolhidas),
                        text=f"Salvando: {g['tipo'][:30]}...")
                    # O número entra no nome do arquivo: três ajustes finos
                    # com a mesma instrução geram três rótulos idênticos, e no
                    # Drive um sobrescreveria o outro sem ninguém ver.
                    nome_arq = (f"{i + 1:02d} - {g['tipo'][:30]}"
                                f".{extensao_de(g['bytes'])}")
                    link, err_up = upload_para_pasta(g["bytes"], nome_arq, pasta_destino_id)
                    if err_up:
                        falhas.append((g["tipo"], err_up))
                    else:
                        links_salvos.append(link)

                # ── O HISTÓRICO DE PROMPTS VAI JUNTO, SOZINHO ─────────
                #
                # Pedido do dono: "ele precisa salvar automaticamente quando
                # o colaborador clicar em salvar as imagens — isso evita do
                # colaborador esquecer de salvar esse prompt também".
                #
                # Na MESMA pasta das imagens: quem achar a imagem acha o
                # prompt dela. E o erro aqui é recado, não falha — as imagens
                # são o trabalho, o prompt é o rastro.
                barra_salvar.progress(0.98, text="Salvando o histórico de prompts...")
                _arq_prompts, _err_prompts = salvar_prompts_na_pasta(
                    pasta_destino_id, nome_gal)

                barra_salvar.progress(1.0, text="Concluído!")
                link_pasta = f"https://drive.google.com/drive/folders/{pasta_destino_id}"

                if _arq_prompts:
                    st.caption(f"📄 Histórico de prompts salvo na mesma pasta: "
                               f"**{_arq_prompts}**")
                elif _err_prompts:
                    st.caption(f"📄 As imagens foram salvas. O histórico de "
                               f"prompts, não — {_err_prompts}. Use o botão "
                               f"\"Preparar histórico de prompts\" para "
                               f"baixá-lo e guardá-lo à mão.")

                if links_salvos:
                    import atividades
                    atividades.registrar_atividade(
                        usuario_logado, "Imagem (aprovada e salva)",
                        nome_gal,
                        f"{len(links_salvos)} imagens salvas na pasta {nome_pasta_novo}",
                        codigo=codigo_gal,
                        link_pasta=link_pasta,
                    )
                    # Só conta como "tudo salvo" quando o que se salvou foi a
                    # galeria inteira. Salvar 2 de 3 e o aviso sumir esconderia
                    # que a terceira ainda só existe nesta sessão.
                    st.session_state["img_galeria_salva"] = (
                        len(galeria) if len(links_salvos) >= len(galeria) else 0)
                    st.success(
                        f"✅ {len(links_salvos)} imagem(ns) salvas no Drive! "
                        f"[Abrir pasta]({link_pasta})"
                    )

                if falhas:
                    st.warning(
                        f"⚠️ {len(falhas)} imagem(ns) não foram salvas: "
                        + ", ".join(t for t, _ in falhas)
                        + f"\n\n{falhas[0][1]}"
                    )
                    st.info(
                        "⬇️ Use o botão \"Baixar todas em ZIP\" ao lado para "
                        "garantir que nada se perca."
                    )

        # ZIP sempre disponível, com o que estiver marcado
        zip_bytes = criar_zip_galeria(_escolhidas, nome_gal)
        col_zip.download_button(
            f"⬇️ Baixar em ZIP ({len(_escolhidas)} imagens)",
            data=zip_bytes,
            file_name=f"{nome_gal}_imagens.zip",
            mime="application/zip",
            use_container_width=True,
        )

        # ── O HISTÓRICO DE PROMPTS, AQUI ──────────────────────────────────
        #
        # Dono, 28/09: "precisa ter um botão Baixar histórico de prompt, onde
        # terá desde o primeiro até o último de todas as imagens geradas".
        #
        # Ele já existia — escondido atrás do botão "Ver o prompt que será
        # enviado", lá no PLANO, antes de gerar. Ou seja: no único momento em
        # que não há prompt nenhum para baixar. Quem acabou de ver o
        # resultado ruim e quer o prompt que o produziu estava aqui embaixo,
        # e daqui não havia caminho.
        st.markdown("---")
        st.markdown("**📄 Histórico de prompts**")
        st.caption(
            "Geração e TODAS as correções de cada peça deste produto, da "
            "primeira à última, em um .txt.")
        _baixar_historico_de_prompts(sufixo="_galeria")


# ── Conferência da revisão de texto ──────────────────────────────────────────
# `python3 imagem.py` roda os casos abaixo. Eles moram aqui, e não num arquivo
# à parte, porque este repositório não tem suíte: teste que não viaja junto do
# código é teste que ninguém roda.
#
# Só a parte que decide — `conferir_texto` fala com a API e é substituída aqui
# por um leitor de mentira. O que se confere é o LAÇO: ele relê depois de
# refazer? ele desiste na hora certa? falha de leitura vira aprovação?
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    _b = bloco_texto_exato(["TÍTULO: frase", "OUTRO: frase"])
    ok("o bloco lista as duas frases", "1. TÍTULO: frase" in _b
       and "2. OUTRO: frase" in _b)
    ok("o bloco proíbe inglês na peça", "NENHUMA palavra em inglês" in _b)
    ok("sem texto, sem bloco — prompt não ganha seção vazia",
       bloco_texto_exato([]) == "" and bloco_texto_exato("") == ""
       and bloco_texto_exato(None) == "")
    ok("string com linhas vira lista", "1. a" in bloco_texto_exato("a\nb"))

    ok("o tipo 4 (close) entrou na revisão", tipo_tem_texto("4 — Close nos detalhes"))
    ok("capa e ambientação continuam fora",
       not tipo_tem_texto("1 — Capa do anúncio (fundo branco)")
       and not tipo_tem_texto("8 — Ambientação realista (sem texto)"))

    # Leitor de mentira: devolve o veredito da vez a cada chamada.
    _real = conferir_texto

    def _leitor(*vereditos):
        fila = list(vereditos)

        def _f(img, pedido=""):
            v = fila.pop(0) if fila else fila_ultimo
            return (None, v) if isinstance(v, str) else (v, "")
        return _f

    _ERRADO = {"tem_texto": True, "correto": False, "erros": '"Apretica"',
               "texto_correto": "PERFEITO PARA ESCRITÓRIO: enfeite que acalma"}
    _CERTO = {"tem_texto": True, "correto": True, "erros": "",
              "texto_correto": ""}
    fila_ultimo = _ERRADO

    _geradas = []

    def _gera(prompt):
        _geradas.append(prompt)
        return b"nova", None

    conferir_texto = _leitor(_CERTO)
    _img, _rel, _ = revisar_texto(b"x", "2 — Benefícios do produto", gerar=_gera)
    ok("texto certo passa de primeira, sem refazer",
       _rel["ok"] is True and _rel["rodadas"] == 1 and not _geradas)

    # O caso que deixou a peça errada chegar ao gestor: refez e ninguem releu.
    _geradas.clear()
    conferir_texto = _leitor(_ERRADO, _CERTO)
    _img, _rel, _ = revisar_texto(b"x", "2 — Benefícios do produto", gerar=_gera,
                               prompt_base="BASE")
    ok("texto errado é refeito e RELIDO, e a segunda leitura aprova",
       _rel["ok"] is True and _rel["rodadas"] == 2 and _img == b"nova")
    ok("a refação recebe as palavras certas, letra por letra",
       len(_geradas) == 1 and "PERFEITO PARA ESCRITÓRIO" in _geradas[0]
       and _geradas[0].startswith("BASE"))

    _geradas.clear()
    conferir_texto = _leitor(_ERRADO, _ERRADO, _ERRADO)
    _img, _rel, _ = revisar_texto(b"x", "2 — Benefícios do produto", gerar=_gera,
                               rodadas=3)
    ok("errado até o fim sai como errado, e não como “refeita, confira”",
       _rel["ok"] is False and _rel["rodadas"] == 3)
    ok("três leituras gastam duas refações, não três",
       len(_geradas) == 2)

    conferir_texto = _leitor("sem chave")
    _img, _rel, _ = revisar_texto(b"x", "2 — Benefícios do produto", gerar=_gera)
    ok("falha de leitura NÃO vira aprovação", _rel["ok"] is None)
    ok("e a tela avisa em voz alta",
       "NÃO foi conferido" in texto_em_aviso(_rel))

    conferir_texto = _leitor(_ERRADO)
    _img, _rel, _ = revisar_texto(b"x", "2 — Benefícios", gerar=None)
    ok("sem gerador, confere e reporta — não trava",
       _rel["ok"] is False and _img == b"x")

    conferir_texto = _leitor(_ERRADO)
    _img, _rel, _ = revisar_texto(b"x", "1 — Capa do anúncio (fundo branco)",
                               gerar=_gera)
    ok("tipo sem texto nem é lido", _rel is None and _img == b"x")
    conferir_texto = _leitor(_CERTO)
    _img, _rel, _ = revisar_texto(b"x", "Ajuste Fino — aumente o produto",
                               gerar=_gera)
    ok("peça já ajustada, sem número no rótulo, continua sendo lida",
       _rel is not None and _rel["ok"] is True)
    ok("pode_ter_texto só dispensa capa e ambientação",
       pode_ter_texto("Personalizado (descrevo o que quero)")
       and not pode_ter_texto("8 — Ambientação realista (sem texto)"))

    # ── A TROCA DA COPY APAGAVA TODAS AS REGRAS DA PECA ─────────────────
    #
    # O DEFEITO, medido no prompt real de 28/09 as 18:17: a peca 2 foi ao
    # motor com 8.259 caracteres; as irmas, com 24.000. Ela nao recebeu a
    # regra da borda, nem a de protagonismo, nem a de densidade, nem a de
    # texto real, nem a de fidelidade. Foi gerada praticamente sem regra — e
    # e a peca que o dono refez QUATRO vezes.
    #
    # A causa: `trocar_texto_exato` apagava do bloco de texto ate a
    # "━━━ SECTION 2", e na Secao 1 TODAS as regras vem DEPOIS do bloco de
    # texto. Como `revisar_texto` chama essa troca sempre que acha erro de
    # portugues, toda peca refeita pela revisao ia ao motor sem regra nenhuma.
    #
    # E o defeito e meu: essa funcao nasceu para consertar os DOIS blocos de
    # texto contrarios, e levou junto tudo o que estava entre um e outro.
    _BLOCOS_DE_REGRA = ("REGRA DE ESPAÇO DESTA PEÇA", "O PRODUTO É O DESTAQUE",
                        "REGRA DE DENSIDADE", "REGRA DE TEXTO REAL",
                        "REGRA DE FIDELIDADE AO PRODUTO",
                        "INSTRUÇÃO DE COMPOSIÇÃO")
    _p_int = montar_prompt_imagem(
        "2 — Benefícios do produto", "", {"cor": "Cinza"}, "Caneca",
        plano_triagem={"composicao": "caneca ao centro", "cena": "bancada",
                       "textos": ["METAL E INOX: durável para uso diário",
                                  "ACABAMENTO ÚNICO: imita pedra medieval",
                                  "400ML: ideal para café e chá"]},
        refs_layout_nomes=["r.jpg"], instrucao_layout="coluna à direita")
    ok("o prompt inteiro tem as seis regras",
       all(b in _p_int for b in _BLOCOS_DE_REGRA))

    _p_troc = trocar_texto_exato(_p_int, ["METAL E INOX: durável para uso"])
    _perdidos = [b for b in _BLOCOS_DE_REGRA if b not in _p_troc]
    ok("e trocar a copy NAO apaga nenhuma delas", not _perdidos)
    ok("a copy nova entra", "durável para uso" in _p_troc)
    ok("e a copy velha sai — nunca DOIS blocos de texto contrarios",
       "imita pedra medieval" not in _p_troc
       and _p_troc.count(MARCA_TEXTO_EXATO) == 1)
    ok("e o prompt nao encolhe pela metade",
       len(_p_troc) > len(_p_int) * 0.85)

    # O PROMPT SEM A MARCA DE FIM — o formato de ontem, que ainda chega aqui
    # por um rascunho recuperado ou por um prompt guardado no log. E tambem o
    # unico caso em que a mutacao de verdade aparece: com a marca presente, o
    # codigo velho acerta por tabela, porque a marca TAMBEM e uma "━━━".
    _p_velho = _p_int.replace(MARCA_FIM_TEXTO_EXATO, "")
    _t_velho = trocar_texto_exato(_p_velho, ["METAL E INOX: durável"])
    ok("prompt sem a marca de fim tambem nao perde as regras",
       not [b for b in _BLOCOS_DE_REGRA if b not in _t_velho])
    ok("e nele a copy velha sai do mesmo jeito",
       "imita pedra medieval" not in _t_velho)

    # ── A COPY QUEBRADA EM LINHAS VIRAVA UM ITEM POR LINHA ───────────────
    #
    # No mesmo prompt de 18:17: "METAL E INOX: durável para uso diário
    # intenso" chegou quebrada e virou os itens 1, 2 e 3. Os titulos ficaram
    # numerados 1., 4. e 7. — o "embaralhado" que o dono apontou, e que eu na
    # hora chamei de coisa do modelo. O texto abaixo e o do arquivo dele.
    _CRU = ("METAL E INOX: durável para uso\ndiário intenso\n"
            "ACABAMENTO ÚNICO: acabamento que\nimita pedra medieval\n"
            "400ML: ideal para café, chá\ne bebidas quentes")
    _b_cru = bloco_texto_exato(_CRU)
    # A ASSERCAO ERRADA ERA MINHA: com tres blocos, o item "3." existe e esta
    # certo. O que nao pode existir e o QUARTO — nove linhas viravam nove.
    ok("linha quebrada NAO vira bloco novo — tres blocos, e nao nove",
       "  3. " in _b_cru and "  4. " not in _b_cru)
    ok("e cada bloco volta inteiro",
       "1. METAL E INOX: durável para uso diário intenso" in _b_cru
       and "3. 400ML: ideal para café, chá e bebidas quentes" in _b_cru)

    # ── O NUMERO DA LISTA NAO E PARA DESENHAR ───────────────────────────
    #
    # Isto e antigo e vale para TODO produto: o bloco manda "escreva
    # EXATAMENTE estas palavras" com "1. ", "2. " colados, e nada diz que o
    # numero nao faz parte. O gerador copia o numero. Na tela do dono, os
    # cartoes sairam escritos "1. METAL E INOX", "2. DESIGN ÚNICO",
    # "3. 400ML" — e o mesmo formato esta no historico do Guerreiro Porta
    # Caneta, de semanas antes.
    ok("o bloco avisa que o numero nao vai para a imagem",
       "não desenhe o número" in _b_cru.lower()
       or "não escreva o número" in _b_cru.lower())

    # ── O PLANO NAO MANDA TAMANHO ───────────────────────────────────────
    #
    # 28/09: a capa saiu com a caneca pequena, e o dono pediu para aumentar.
    # Nao era o modelo desobedecendo: o prompt mandava DUAS coisas.
    #
    #   regra da peca : "O produto ocupa de 85% a 92% da dimensao util"
    #   cena do plano : "produto centralizado ocupando 60% do espaco vertical"
    #
    # A cena e escrita pela IA do plano, e o prompt dela pede superficie,
    # props e angulo — nada de tamanho. Ela legislou fora da area dela, e o
    # gerador obedeceu a ela.
    #
    # A ENTRADA DESTE TESTE VEM DO .TXT DO DONO, palavra por palavra, e nao
    # de uma frase que eu inventaria (Forma 7). A frase abaixo e a que
    # realmente foi ao motor em 28/09 as 18:47.
    _CENA_REAL = ("Fundo branco puro sem sombra projetada; produto "
                  "centralizado ocupando 60% do espaço vertical.")
    ok("a medida sai da cena, e a cena continua dizendo o cenario",
       sem_medida_de_quadro(_CENA_REAL) == "Fundo branco puro sem sombra projetada.")
    ok("cena sem medida passa intacta",
       sem_medida_de_quadro("superfície de nogueira, caderno fechado, câmera em 3/4")
       == "superfície de nogueira, caderno fechado, câmera em 3/4")
    ok("a medida no MEIO sai sem levar o resto junto",
       sem_medida_de_quadro("Bancada de mármore, produto ocupando 85% da altura, luz lateral")
       == "Bancada de mármore, luz lateral.")
    # A ORACAO INTEIRA, e nao so o numero: "ocupando" sem o numero continua
    # mandando tamanho, so que sem dizer quanto — que e pior.
    ok("nao sobra 'ocupando' orfao",
       "ocupando" not in sem_medida_de_quadro(_CENA_REAL)
       and "ocupando" not in sem_medida_de_quadro(
           "produto ocupando 70% do quadro"))
    ok("cena que so falava de tamanho vira vazia, e nao lixo",
       sem_medida_de_quadro("produto ocupando 70% do quadro") == "")

    # ══ A CORRECAO OBRIGATORIA TAMBEM MANDAVA TAMANHO ═══════════════════
    #
    # Dono, 29/09, com o historico de prompts do Tigre na mao. No MESMO
    # prompt da peca 7:
    #
    #   linha 163: "O produto ocupa de 30% a 45% da dimensao util do quadro.
    #               Nao e sugestao: e a medida desta peca."
    #   linha 289: "mostre o pendulo apoiado e desobstruido, OCUPANDO MAIS DA
    #               METADE DO QUADRO"
    #
    # Duas ordens contrarias sobre a mesma coisa, no mesmo prompt — o defeito
    # que `sem_medida_de_quadro` existe para impedir. Eu a apliquei em `cena`,
    # `composicao` e `direcao_arte` e deixei DE FORA o texto que o proprio
    # conferidor escreve, que e o unico que entra DEPOIS da regra de tamanho e
    # por isso fala por ultimo. Forma 1: corrigir onde doeu, nao onde a regra
    # alcanca.
    #
    # O tamanho tem um dono so (`ocupacao_em_portugues`). Quem nao e dono nao
    # fala — nem o plano, nem a direcao de arte, nem a critica da peca.
    _crit = ["O cartao branco esta cortado pela borda direita",
             "mostre o pendulo desobstruido, ocupando mais da metade do quadro",
             "o produto deve ocupar 80% do quadro"]
    _limpo = [sem_medida_de_quadro(_c) for _c in _crit]
    ok("a critica que nao fala de tamanho passa inteira",
       _limpo[0] == _crit[0])
    ok("'mais da metade do quadro' sai da critica",
       "metade do quadro" not in _limpo[1])
    ok("e o resto da critica sobrevive",
       "desobstruido" in _limpo[1])
    ok("porcentagem na critica tambem sai",
       "80%" not in _limpo[2])

    # A CADEIA REAL, E NAO O NO DA CHAMADA.
    #
    # A primeira versao desta guarda procurava por AST se `revisar_peca`
    # CHAMAVA `sem_medida_de_quadro`. Ela achava UMA das duas chamadas — a
    # dos `problemas` ou a da `instrucao` — e ficava verde com a outra
    # removida. A mutacao pegou as duas, uma de cada vez.
    #
    # Aqui quem responde e o PROMPT que de fato sai: `revisar_peca` recebe o
    # gerador como parametro, entao um duplo captura o texto inteiro e a
    # pergunta passa a ser a unica que importa — o gerador recebeu ordem de
    # tamanho?
    _capturado = {}

    def _gerar_falso(prompt_recebido):
        _capturado["prompt"] = prompt_recebido
        return b"nova-imagem", ""

    _conf_antes = globals()["conferir_peca"]
    try:
        globals()["conferir_peca"] = lambda *a, **k: ({
            "aprovada": False,
            "problemas": [
                "os cartoes estao cortados pela borda direita",
                "o produto aparece ocupando mais da metade do quadro"],
            "instrucao": ("Reenquadre os cartoes para dentro e deixe o "
                          "produto ocupando 80% do quadro"),
        }, "")
        revisar_peca(b"img", "6 — Quebra de objeção", fotos_ref=[b"foto"],
                     gerar=_gerar_falso,
                     prompt_base="PROMPT BASE DA PECA", rodadas=2)
        _pf = _capturado.get("prompt", "")
        ok("o gerador recebeu o prompt da refacao", "CORREÇÃO" in _pf)
        ok("e a critica chegou nele", "cortados pela borda" in _pf)
        ok("mas NENHUMA ordem de tamanho foi junto",
           "metade do quadro" not in _pf and "80%" not in _pf)
        ok("o resto da instrucao sobreviveu", "Reenquadre" in _pf)
    finally:
        globals()["conferir_peca"] = _conf_antes

    # ══ O PRODUTO DA SESSÃO TEM UMA PORTA SÓ ════════════════════════════
    #
    # Dono, 29/09, depois do Tigre gerado com brief de pêndulo: *"ataque
    # tudo"*.
    #
    # `img_nome_produto` era escrito em TRÊS lugares e `img_codigo` em dois,
    # cada um a seu modo — recuperar rascunho, ajuste fino avulso, fim da
    # geração. Três escritores para a mesma pergunta é a Forma 5 desta base:
    # um nome, duas respostas, e elas passam a discordar.
    #
    # A unificação do ESTADO INTEIRO da aba é mudança grande e a produção
    # está em uso; o que dá para fazer com segurança hoje é a porta única —
    # os três momentos continuam existindo, mas escrevem pelo mesmo lugar.
    import checar_tela as _ct_prod
    _ct_prod.instalar()
    st.session_state.clear()
    definir_produto_da_sessao("Tigre", codigo="MS-TIGR-0929GUF")
    ok("a porta grava o nome", st.session_state.get("img_nome_produto") == "Tigre")
    ok("e o código", st.session_state.get("img_codigo") == "MS-TIGR-0929GUF")

    # NOME VAZIO NÃO APAGA O QUE ESTAVA. O ajuste fino avulso passava
    # `nome_produto or "produto-ajustado"`; um None ali zerava o produto da
    # sessão e a geração seguinte saía sem nome.
    definir_produto_da_sessao("", codigo="")
    ok("nome vazio não apaga o produto que já estava",
       st.session_state.get("img_nome_produto") == "Tigre")
    ok("nem o código", st.session_state.get("img_codigo") == "MS-TIGR-0929GUF")

    definir_produto_da_sessao("Pêndulo", codigo="MS-PEND-01")
    ok("mas trocar de produto de verdade funciona",
       st.session_state.get("img_nome_produto") == "Pêndulo")

    # E NINGUÉM ESCREVE POR FORA — por AST, no arquivo inteiro.
    import ast as _ast_pp
    _arv_pp = _ast_pp.parse(open(__file__, encoding="utf-8").read()
                            .split('if __name__ == "__main__":')[0])
    _porta = next((_x for _x in _ast_pp.walk(_arv_pp)
                   if isinstance(_x, _ast_pp.FunctionDef)
                   and _x.name == "definir_produto_da_sessao"), None)
    _linhas_da_porta = ({_x.lineno for _x in _ast_pp.walk(_porta)
                         if hasattr(_x, "lineno")} if _porta else set())
    _por_fora = []
    for _n_pp in _ast_pp.walk(_arv_pp):
        if isinstance(_n_pp, _ast_pp.Assign) and _n_pp.lineno not in _linhas_da_porta:
            for _t_pp in _n_pp.targets:
                if (isinstance(_t_pp, _ast_pp.Subscript)
                        and isinstance(_t_pp.slice, _ast_pp.Constant)
                        and _t_pp.slice.value in ("img_nome_produto",
                                                  "img_codigo")):
                    _por_fora.append(_n_pp.lineno)
    ok(f"ninguém escreve o produto por fora da porta "
       f"({len(_por_fora)} fora: {_por_fora[:3]})", not _por_fora)

    # ══ O LIMITE DE TENTATIVAS APARECE, E INSISTIR É UMA SAÍDA ══════════
    #
    # Dono, 29/09: "o chat vai conseguir realizar o que hoje ele informa não
    # conseguir em 2 ou mais tentativas?". São 2 fixas, e quando o produto
    # mudava o sistema ENCERRAVA — sem oferecer a terceira. Quando o ajuste
    # apenas não sai, ele já dizia "me peça de novo". No caso mais difícil,
    # tirava essa opção.
    _rel_alt = {"ok": False, "produto_alterado_fora_do_pedido": True,
                "tentativas": 2, "falta": "",
                "colateral": "o produto foi redesenhado",
                "saiu": "", "erro": ""}
    _txt_alt = relato_em_texto(2, _rel_alt)
    ok("a recusa por mudança não pedida diz QUANTAS tentativas houve",
       "2 tentativa" in _txt_alt)
    ok("e oferece insistir, não só refazer ou desistir",
       "me peça de novo" in _txt_alt.lower())
    ok("e continua dizendo que manteve a versão original",
       "versão original" in _txt_alt)
    # E NOMEIA O QUE VEIO JUNTO, em vez de acusar o produto em geral.
    ok("a recusa diz O QUE mudou sem ter sido pedido",
       "o produto foi redesenhado" in _txt_alt)
    ok("e nao diz mais 'produto errado' — a causa antiga era mentira "
       "quando a mudanca tinha sido pedida",
       "produto errado" not in _txt_alt)
    # E A RECUSA COMUM NÃO PERDEU O CONVITE que ela já tinha.
    _txt_nao = relato_em_texto(2, {"ok": False, "produto_alterado_fora_do_pedido": False,
                                   "tentativas": 2, "erro": "",
                                   "falta": "os cartões seguem cortados",
                                   "colateral": "", "saiu": ""})
    ok("a recusa comum segue convidando a pedir de novo",
       "me peça de novo" in _txt_nao.lower())

    # ══ A REFERÊNCIA DO PEDIDO CHEGA AO MOTOR ═══════════════════════════
    #
    # Dono, 29/09: "eles mandaram a imagem no chat para ficar claro o que ele
    # pediu". A imagem anexada parava no chat: o motor recebia a peça e uma
    # frase, e ONDE está cortado, QUAL cota trocar e o que foi circulado se
    # perdia na tradução para texto.
    #
    # A ORDEM IMPORTA, e é o que esta guarda mede. A referência entra ANTES
    # das fotos do produto e NÃO no lugar delas: as fotos são a trava de
    # fidelidade (é delas que saem a cor e a forma), a referência é o que se
    # pede. Trocar uma pela outra faria o motor copiar a arte marcada em vez
    # de corrigir a peça — e produto errado é o defeito mais grave daqui.
    import ast as _ast_rp, inspect as _insp_rp
    _src_pi = _insp_rp.getsource(consumir_comandos_do_chat)
    _arv_pi = _ast_rp.parse(_ast_rp.unparse(_ast_rp.parse(_src_pi.lstrip())))
    _nomes_pi = {getattr(_x, "id", "") for _x in _ast_rp.walk(_arv_pi)
                 if isinstance(_x, _ast_rp.Name)}
    ok("o ajuste do chat lê a referência que veio no comando",
       "_ref_pedido" in _nomes_pi)
    ok("e ela é somada às fotos do produto, não trocada por elas",
       "_refs_cmd" in _nomes_pi
       and "_ref_pedido + list(fotos_ref_aj" in _src_pi.replace("\n", " "))
    # A PECA A CORRIGIR CONTINUA SENDO A PECA. A referencia nao pode virar o
    # alvo do ajuste: o motor editaria a arte marcada e devolveria ela.
    ok("a peça ajustada continua saindo da galeria",
       "img_ref_cmd[0] if img_ref_cmd else None" in _src_pi)

    # ══ O PROMPT SAIU COM OUTRO PRODUTO ═════════════════════════════════
    #
    # Dono, 29/09, com o histórico do Tigre e o print da tela na mão. A tela
    # dizia, em verde:
    #
    #   "Descrição encontrada: Tigre · Dourado com Strass · 10x21x5 · 299 ·
    #    Resina"
    #
    # E o prompt das oito peças saiu com:
    #
    #   PRODUTO: pendulo balança / 14x13x11 / 202g / Plástico
    #   Direção: "Técnico Automotivo Minimalista"
    #   Cena: "Interior de carro"
    #   Texto: "CABE EM MEU CARRO?"
    #
    # Um tigre decorativo gerado com o brief de um pêndulo automotivo. Oito
    # peças pagas, todas do produto errado, sem um aviso.
    #
    # POR QUE: a tela relê a descrição a cada abertura; o `img_triagem_config`
    # é congelado quando o PLANO é gerado (`imagem.py:7364`) e é dele que o
    # prompt tira nome, medidas, peso e material (`:7993-7994`). Trocar o
    # código na tela sem refazer o plano deixa os dois discordando — e o
    # sistema tinha os dois dados na mão e não comparava.
    #
    # Nenhuma regra de prompt conserta isto: o prompt estava obedecendo
    # direitinho ao produto que lhe deram.
    ok("mesmo produto nos dois lados: nada a dizer",
       not divergencia_de_produto(
           {"nome_produto": "Tigre", "dados_descricao": {"medidas": "10x21x5"}},
           "Tigre", {"medidas": "10x21x5"}))
    _div = divergencia_de_produto(
        {"nome_produto": "pendulo balança",
         "dados_descricao": {"medidas": "14x13x11", "peso": "202g",
                             "material": "Plástico"}},
        "Tigre", {"medidas": "10x21x5", "peso": "299", "material": "Resina"})
    ok("produto diferente é acusado", bool(_div))
    ok("e o aviso nomeia OS DOIS, para não virar adivinhação",
       "pendulo balança" in _div and "Tigre" in _div)
    ok("as medidas divergentes também aparecem",
       "14x13x11" in _div and "10x21x5" in _div)
    ok("plano sem config nenhuma não inventa divergência",
       not divergencia_de_produto(None, "Tigre", {"medidas": "10x21x5"}))
    ok("e tela sem descrição carregada também não",
       not divergencia_de_produto(
           {"nome_produto": "Tigre", "dados_descricao": {}}, "", None))
    # CAIXA E ESPAÇO NÃO SÃO DIVERGÊNCIA. Alarme falso aqui trava a geração
    # de quem não fez nada errado, e verificador que dá alarme falso ensina a
    # ignorá-lo.
    ok("caixa e espaço sobrando não acusam nada",
       not divergencia_de_produto(
           {"nome_produto": " tigre ", "dados_descricao": {"medidas": "10x21x5"}},
           "TIGRE", {"medidas": "10x21x5"}))

    # E A TELA PARA ANTES DE GASTAR — por AST, na chamada.
    import ast as _ast_dv, inspect as _insp_dv
    _arv_dv = _ast_dv.parse(_ast_dv.unparse(_ast_dv.parse(
        _insp_dv.getsource(pagina_imagem).lstrip())))
    ok("a tela confere o produto antes de gerar",
       any(isinstance(_x, _ast_dv.Call)
           and (getattr(_x.func, "id", "") or getattr(_x.func, "attr", ""))
           == "divergencia_de_produto"
           for _x in _ast_dv.walk(_arv_dv)))

    # ── A REGUA MEDE O TEXTO DA PECA QUE TEM TEXTO ──────────────────────
    #
    # Dono, 30/09, duas vezes: "os textos cortados foram corrigidos na causa
    # raiz?". A resposta honesta foi NAO ate esta linha existir: tirar a
    # contradicao do prompt trata a causa, mas sem medir o resultado e
    # hipotese — e hipotese foi o que me fez errar o dia inteiro.
    #
    # `medir_imagem.texto_na_borda` so roda quando quem chama diz que a peca
    # TEM texto. Se a chamada perder esse argumento, a medida some em
    # silencio e a regua volta a aprovar peca com o titulo decepado — que e
    # exatamente o estado de antes. Por isso a conferencia e na CHAMADA.
    import inspect as _insp_tx
    _arv_tx = _ast_dv.parse(_ast_dv.unparse(_ast_dv.parse(
        _insp_tx.getsource(gerar_imagem_ia).lstrip())))
    _chamadas_regua = [
        _x for _x in _ast_dv.walk(_arv_tx)
        if isinstance(_x, _ast_dv.Call)
        and (getattr(_x.func, "attr", "") or getattr(_x.func, "id", "")) == "problemas"
    ]
    ok("a regua e chamada na porta do motor", bool(_chamadas_regua))
    ok("e ela recebe se a peca tem texto — senao a medida some calada",
       all(any(k.arg == "com_texto" for k in _c.keywords)
           for _c in _chamadas_regua))
    # E A CADEIA, COM A PECA DE VERDADE: nao basta o argumento existir, a
    # medida tem de REPROVAR uma peca com o titulo decepado.
    import medir_imagem as _md_tx
    from PIL import Image as _ImgTx, ImageDraw as _DrwTx, ImageFont as _FntTx
    def _fnt_tx(t):
        for _c in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            try:
                return _FntTx.truetype(_c, t)
            except Exception:
                pass
        return _FntTx.load_default()
    def _peca_tx(x):
        _im = _ImgTx.new("RGB", (1200, 1200), (235, 230, 220))
        _d = _DrwTx.Draw(_im)
        _d.ellipse([620, 400, 1100, 880], fill=(40, 90, 150))
        _f = _fnt_tx(54)
        for _i, _t in enumerate(("FITA DE MEDIDA", "PRECISO", "ATE 150 MM")):
            _y = 260 + _i * 180
            _d.rounded_rectangle([x, _y, x + 470, _y + 130], 18,
                                 fill=(255, 255, 255))
            _d.text((x + 28, _y + 40), _t, font=_f, fill=(20, 20, 20))
        import io as _io_tx
        _b = _io_tx.BytesIO()
        _im.save(_b, format="PNG")
        return _b.getvalue()
    ok("peca com o titulo decepado e REPROVADA pela regua",
       any("texto cortado" in _p
           for _p in _md_tx.problemas(_peca_tx(-120), com_texto=True)))
    ok("e a mesma peca inteira passa",
       not any("texto cortado" in _p
               for _p in _md_tx.problemas(_peca_tx(60), com_texto=True)))

    # ── A PECA E COMPARADA COM AS FOTOS, NA PORTA DO MOTOR ──────────────
    #
    # Mesma logica da regua do texto: nao basta a funcao existir, ela tem de
    # ser CHAMADA no caminho que entrega a peca — e com as fotos de
    # referencia, nao com outra coisa.
    _chamadas_dif = [
        _x for _x in _ast_dv.walk(_arv_tx)
        if isinstance(_x, _ast_dv.Call)
        and (getattr(_x.func, "attr", "") or getattr(_x.func, "id", ""))
        == "produto_diferente"
    ]
    # ── A PECA QUE NEM CHEGOU A SER TENTADA TEM NOME NA TELA ────────────
    #
    # Dono: "nao gerou a imagem presenteando" / "investigue as fotos nao
    # geradas". A peca bloqueada sumia no instante em que a galeria abria, e
    # o placar dizia "8 de 8" em verde porque contava so as viaveis.
    #
    # A ENTRADA DO TESTE E A FORMA REAL DO PLANO: `viavel: False` e
    # `pergunta_info` sao os campos que a triagem escreve (imagem.py, o
    # esquema que `gerar_triagem_ia` pede). Valor inventado aqui mediria o
    # meu entendimento, e e ele que costuma estar errado.
    _PLANO_BLOQ = {"plano": [
        {"numero": 1, "tipo": "1 — Capa do anúncio (fundo branco)",
         "viavel": True},
        {"numero": 7, "tipo": "7 — Presenteie", "viavel": False,
         "pergunta_info": "Para quem este produto é presenteado?"},
    ]}
    _bloq = pecas_bloqueadas_da_geracao(_PLANO_BLOQ)
    # ── O BLOCO DE TEXTO REPETIDO DENTRO DA PECA ────────────────────────
    #
    # A ENTRADA VEM DO ARQUIVO DO DONO, NAO DA MINHA CABECA. E a copy real
    # que a peca 4 recebeu em 30/09, copiada do .txt que ele baixou:
    #
    #     1. MADEIRA TRABALHADA: / Acabamento e textura
    #     2. MADEIRA TRABALHADA: / Acabamento e textura
    #     3. MONTAGEM: / Construcao precisa
    #
    # Dois cartoes identicos foram ao gerador. Nao foi o modelo que
    # desobedeceu — foi a nossa copy que pediu a repeticao, e o teto da peca
    # gastou uma vaga com ela.
    _COPY_REAL_PECA4 = ["MADEIRA TRABALHADA: / Acabamento e textura",
                        "MADEIRA TRABALHADA: / Acabamento e textura",
                        "MONTAGEM: / Construção precisa"]
    _fica, _sai = blocos_sem_repeticao(_COPY_REAL_PECA4)
    ok("o bloco repetido da peca 4 do dono e descartado",
       len(_fica) == 2 and len(_sai) == 1)
    ok("e quem fica e a PRIMEIRA ocorrencia, na ordem do plano",
       _fica == ["MADEIRA TRABALHADA: / Acabamento e textura",
                 "MONTAGEM: / Construção precisa"])
    # RUIDO DE DIGITACAO E O MESMO CARTAO: caixa, acento e dois-pontos.
    ok("caixa e acento nao fazem dois cartoes de um so",
       blocos_sem_repeticao(["MONTAGEM: Construção precisa",
                             "montagem: construcao precisa"])[0] ==
       ["MONTAGEM: Construção precisa"])
    # E O QUE DIFERE EM PALAVRA FICA — acusar o inocente aqui apagaria um
    # argumento de venda da peca.
    ok("cartoes diferentes continuam os dois",
       len(blocos_sem_repeticao(["MADEIRA: textura",
                                 "MONTAGEM: encaixe"])[0]) == 2)
    ok("copy vazia nao quebra", blocos_sem_repeticao([]) == ([], [])
       and blocos_sem_repeticao(None) == ([], []))
    # E A DEDUPLICACAO ACONTECE ANTES DO TETO: senao a repeticao gasta a vaga
    # e o terceiro bloco e que sai.
    # A PRIMEIRA VERSAO DESTA GUARDA FICOU VERDE COM O DEFEITO DE VOLTA.
    #
    # Ela era `fonte.find("blocos_sem_repeticao") < fonte.find("_teto_do_tipo")`
    # — e `find` devolve -1 quando NAO ACHA. Tirando a chamada inteira, -1 <
    # indice do teto e VERDADEIRO: a guarda aprovava justamente o estado em
    # que a deduplicacao nao existe. Foi a mutacao que mostrou, nao a leitura.
    #
    # Agora ela exige as duas coisas: que a chamada EXISTA, e que venha antes.
    _fonte_mp = _insp_tx.getsource(montar_prompt_imagem)
    _i_dedup = _fonte_mp.find("blocos_sem_repeticao")
    _i_teto = _fonte_mp.find("_teto_do_tipo")
    ok("o prompt deduplica a copy antes de montar", _i_dedup >= 0)
    ok("e o repetido sai ANTES do teto da peca cortar",
       _i_dedup >= 0 and _i_teto >= 0 and _i_dedup < _i_teto)

    ok("a peca bloqueada e encontrada depois da geracao", len(_bloq) == 1)
    ok("e ela vem com o nome, nao so a contagem",
       _bloq[0].get("tipo") == "7 — Presenteie")
    ok("e com o que faltou",
       "presenteado" in _bloq[0].get("pergunta_info", ""))
    ok("plano sem bloqueio nao inventa peca sumida",
       pecas_bloqueadas_da_geracao({"plano": [{"tipo": "x", "viavel": True}]}) == [])
    ok("plano vazio nao quebra",
       pecas_bloqueadas_da_geracao({}) == []
       and pecas_bloqueadas_da_geracao(None) is not None)
    # E A TELA LE ISSO — senao a funcao existe e a peca continua sumindo.
    ok("a tela procura as pecas nao geradas depois da galeria",
       any(isinstance(_x, _ast_dv.Call)
           and (getattr(_x.func, "id", "") or getattr(_x.func, "attr", ""))
           == "pecas_bloqueadas_da_geracao"
           for _x in _ast_dv.walk(_arv_dv)))

    # ── O STUDIO SABE FALAR COM O MODELO QUE ELE ACHOU ──────────────────
    #
    # O filtro corrigido em 30/09 passou a ENCONTRAR o `dall-e-3` na conta — e
    # a chamada sem fotos mandava `quality="high"` e `response_format`, que
    # sao da familia `gpt-image-*`. O Studio achava o motor e levava 400.
    #
    # A ENTRADA DO TESTE E A MENSAGEM QUE A API DEVOLVE, nao uma inventada:
    # "Unknown parameter: 'response_format'" e o formato que a OpenAI usa.
    _ENVIADOS = {"model": "dall-e-3", "prompt": "x", "n": 1,
                 "size": "1024x1024", "quality": "high",
                 "response_format": "b64_json"}
    ok("a API recusando `quality` aponta `quality`",
       parametro_recusado(
           Exception("400 Unsupported value: 'quality' does not support 'high'"),
           _ENVIADOS) == "quality")
    ok("e recusando `response_format` aponta ele",
       parametro_recusado(
           Exception("Unknown parameter: 'response_format'."),
           _ENVIADOS) == "response_format")
    # O QUE NAO PODE SAIR NUNCA: sem eles nao ha chamada.
    ok("`model` e `prompt` nunca sao apontados",
       parametro_recusado(Exception("Unknown parameter: 'model'"),
                          _ENVIADOS) == ""
       and parametro_recusado(Exception("invalid value for 'prompt'"),
                              _ENVIADOS) == "")
    # E ERRO QUE NAO E DE PARAMETRO NAO PODE VIRAR "TIRA UM PARAMETRO":
    # esconder falta de credito atras de uma repeticao muda a causa de lugar.
    ok("falta de credito nao vira parametro recusado",
       parametro_recusado(Exception("You exceeded your current quota"),
                          _ENVIADOS) == "")
    ok("modelo inexistente tambem nao",
       parametro_recusado(Exception("The model `dall-e-9` does not exist"),
                          _ENVIADOS) == "")
    ok("erro vazio nao quebra",
       parametro_recusado(None, _ENVIADOS) == ""
       and parametro_recusado(Exception("x"), None) == "")
    # E A CHAMADA USA ISSO — senao a funcao existe e o 400 continua matando.
    _fonte_gen = _insp_tx.getsource(_chamar_openai_geracao)
    # A GUARDA PRECISOU FICAR ESTREITA.
    #
    # Ela perguntava se "parametro_recusado" aparecia na funcao. Em 02/10 os
    # caminhos COM foto ganharam o mesmo laco, e o nome passou a aparecer tres
    # vezes: tirar o do caminho SEM fotos deixava a guarda verde, porque os
    # outros dois respondiam por ele. Guarda que pergunta "existe em algum
    # lugar" nao ve a peca que deixou de ser conferida — e esta base ja pagou
    # por isso antes, com o `checar_tela`.
    ok("a chamada sem fotos se adapta ao que o modelo recusa",
       "_qual = parametro_recusado(_e_gen, _args_gen)" in _fonte_gen)

    # ── A CONFERENCIA NAO PODE COBRAR "METADE DO QUADRO" DE UMA CENA ────
    #
    # A quarta pergunta era "pequeno demais, ocupando menos de METADE do
    # quadro?", com o numero escrito a mao. Nas pecas de cena (3, 7, 8) o
    # produto ocupa uma fracao modesta porque e essa a escala real dele — e a
    # pergunta mandava REPROVAR a peca certa. Cada reprovacao aqui e uma
    # geracao paga que volta com o produto inflado: a conferencia fabricaria
    # o defeito que o prompt acabou de parar de pedir.
    #
    # Era a terceira voz sobre o mesmo numero, depois da faixa em OCUPACAO e
    # do bloco de protagonismo.
    for _t_cena in ("3 — Benefícios no cenário de uso", "7 — Presenteie",
                    "8 — Ambientação realista (sem texto)"):
        _pq = pergunta_do_tamanho(_t_cena)
        ok(f"a conferencia de '{_t_cena[:14]}' nao cobra fracao do quadro",
           "ESCALA REAL" in _pq and "%" not in _pq)
    # E A PECA DE PRODUTO CONTINUA COBRANDO A MEDIDA DELA, da fonte unica.
    ok("a capa cobra os 85% que estao em OCUPACAO",
       f"{faixa_de_ocupacao('1 — Capa do anúncio (fundo branco)')[0]}%"
       in pergunta_do_tamanho("1 — Capa do anúncio (fundo branco)"))
    ok("e a peca 2 cobra os 60% dela",
       f"{faixa_de_ocupacao('2 — Benefícios do produto')[0]}%"
       in pergunta_do_tamanho("2 — Benefícios do produto"))
    ok("nenhuma pergunta traz 'metade' escrito a mao",
       not any("metade" in _q.lower()
               for _t in ("1 — Capa do anúncio (fundo branco)",
                          "2 — Benefícios do produto", "7 — Presenteie")
               for _q in perguntas_da_peca(_t)))
    ok("e sao sempre QUATRO perguntas",
       len(perguntas_da_peca("2 — Benefícios do produto")) == 4
       and len(perguntas_da_peca("")) == 4)
    # E A CONFERENCIA USA A FUNCAO, nao a tupla crua — senao o tipo nunca
    # chega e todas as pecas voltam a receber a mesma pergunta.
    _fonte_cp = _insp_tx.getsource(conferir_peca)
    ok("a conferencia monta as perguntas PARA O TIPO da peca",
       "perguntas_da_peca(tipo)" in _fonte_cp)

    # ── O STUDIO DIZ O QUE A CONTA CONSEGUE GARANTIR ────────────────────
    #
    # Dono: "margem nas fotos" e "criacao de uma foto totalmente errada
    # comparada ao produto original". As duas vem da MESMA causa — a peca foi
    # feita pelo motor reserva, que nao aceita `size` nem `input_fidelity`.
    #
    # O Studio SABIA e parava no nome do modelo. Um nome de modelo nao diz a
    # ninguem que as pecas vao sair com margem.
    _ok_cap, _rec_cap = capacidade_do_motor(["dall-e-3", "dall-e-2"])
    ok("conta sem gpt-image e reprovada", not _ok_cap)
    ok("e o recado NOMEIA os dois defeitos que isso causa",
       "Margem" in _rec_cap and "redesenhado" in _rec_cap)
    ok("e diz que nenhuma regra de prompt conserta",
       "Nenhuma regra de prompt" in _rec_cap)
    _ok2, _rec2 = capacidade_do_motor(["gpt-image-1", "dall-e-3"])
    ok("conta com gpt-image passa", _ok2 and "input_fidelity" in _rec2)
    # LISTA VAZIA NAO E "A CONTA NAO TEM": e "nao consegui olhar". Afirmar o
    # que nao se sabe manda quem le procurar no lugar errado.
    _ok3, _rec3 = capacidade_do_motor([])
    ok("sem conseguir listar, ele nao afirma que a conta nao tem",
       not _ok3 and "não sei dizer" in _rec3)
    # E A TELA MOSTRA ISSO — senao e mais um dado que o sistema tem e nao conta.
    _fonte_tela = _insp_tx.getsource(pagina_imagem)
    ok("a tela de diagnostico mostra a capacidade da conta",
       "capacidade_do_motor" in _fonte_tela)
    # E O TESTE DA TELA SE ADAPTA IGUAL A GERACAO: ele mandava `quality="low"`,
    # o mesmo parametro que o dall-e-3 recusa. Corrigir num irmao e deixar o
    # outro diria "o motor nao funciona" quando o defeito e o teste.
    ok("o teste da tela tambem se adapta ao que o modelo recusa",
       _fonte_tela.count("parametro_recusado") >= 1)

    # ── SEM FOTO, A PECA NAO PODE SAIR CALADA ───────────────────────────
    #
    # `revisar_peca` devolvia `None` quando faltava foto, e `peca_em_aviso`
    # devolve "" para `None`: a peca chegava a galeria com a mesma cara de uma
    # peca CONFERIDA E APROVADA. E "sem foto" e justamente o caso em que o
    # produto tem mais chance de sair errado — o motor o reconstroi do texto.
    _, _rel_sf = revisar_peca(b"bytes", "1 — Capa do anúncio (fundo branco)",
                              fotos_ref=None)
    ok("sem foto, a peca volta com veredito em vez de silencio",
       isinstance(_rel_sf, dict) and _rel_sf.get("ok") is None)
    ok("e o motivo diz que foi montada a partir do texto",
       "a partir do texto" in (_rel_sf.get("erro") or ""))
    ok("e a tela avisa que ela NAO foi conferida",
       "NÃO foi conferida" in peca_em_aviso(_rel_sf))
    # SEM IMAGEM continua devolvendo None: nao ha peca para avisar sobre.
    ok("sem imagem nenhuma, nao inventa veredito",
       revisar_peca(None, "1 — Capa do anúncio (fundo branco)",
                    fotos_ref=[b"x"])[1] is None)

    # ── A CONTAGEM DE BLOCOS SEGUE O BLOCO, NA REFACAO ──────────────────
    #
    # ACHADO NO ARQUIVO DO DONO e reproduzido linha a linha. A peca 2 foi ao
    # motor, na refacao, dizendo "exatamente 3 bloco(s)" e listando UM — uma
    # frase corrida de 108 caracteres sem pontuacao, para ser partida em tres
    # cartoes. O modelo parte onde consegue: sao os cartoes embaralhados e
    # sobrepostos que ele chamou de "quadrados sobressaindo o outro".
    #
    # A ENTRADA E A COPY REAL dele, copiada do .txt, e a string colada e a que
    # a revisao devolveu de verdade.
    import re as _re_tte
    _COPY_REAL_P2 = ["PROTEÇÃO: contra poeira e impactos",
                     "ORGANIZAÇÃO: espaço organizado e seguro",
                     "MADEIRA NATURAL: durável e elegante"]
    # O CADASTRO SUSTENTA A COPY, e isso passou a importar em 05/10: a
    # barreira de claim (`copy_sem_promessa`) tira o bloco cuja promessa o
    # cadastro nao comprova, e "MADEIRA NATURAL: DURAVEL e elegante" com
    # cadastro de `medidas` so saia — a guarda media 3 blocos e recebia 2.
    #
    # A entrada passa a ser a de um produto REAL, com material e
    # diferenciais preenchidos. Enfraquecer a barreira para a guarda passar
    # seria consertar o termometro; completar o cadastro e o que um produto
    # de verdade tem.
    _p1_tte = montar_prompt_imagem(
        "2 — Benefícios do produto", "",
        {"medidas": "8x33x11", "material": "madeira natural maciça",
         "diferenciais": "madeira durável, proteção contra poeira e impactos, "
                         "espaço organizado e seguro"},
        "caixa",
        plano_triagem={"composicao": "x", "cena": "y",
                       "textos": _COPY_REAL_P2})

    def _conta(txt):
        return (len(_re_tte.findall(r"^  \d+\. ", txt, _re_tte.M)),
                int(_re_tte.search(r"exatamente (\d+) bloco", txt).group(1)))

    ok("na geracao, listados e declarados ja batiam", _conta(_p1_tte) == (3, 3))
    _COLADO = ("PROTEÇÃO contra poeira e impactos ORGANIZAÇÃO espaço "
               "organizado e seguro MADEIRA NATURAL durável e elegante")
    ok("a refacao que cola os tres num so NAO deixa o numero para tras",
       _conta(trocar_texto_exato(_p1_tte, _COLADO)) == (1, 1))
    ok("e com dois blocos o numero vira dois",
       _conta(trocar_texto_exato(_p1_tte, ["A: um", "B: dois"])) == (2, 2))
    ok("e com quatro, quatro",
       _conta(trocar_texto_exato(
           _p1_tte, ["A: um", "B: dois", "C: tres", "D: quatro"])) == (4, 4))
    # PROMPT SEM A LINHA DA CONTAGEM nao quebra — a capa nao tem bloco de texto.
    ok("prompt sem linha de contagem nao quebra",
       "TEXTO EXATO" in trocar_texto_exato("prompt qualquer", ["A: um"]))

    ok("a peca e comparada com as fotos antes de sair", bool(_chamadas_dif))
    ok("e a comparacao recebe as FOTOS DE REFERENCIA, nao outra coisa",
       any(any(getattr(_a, "id", "") == "imagens_referencia" for _a in _c.args)
           for _c in _chamadas_dif))
    # E A CADEIA, com produto repintado de verdade.
    def _bola_tx(cor):
        _im = _ImgTx.new("RGB", (900, 900), (250, 250, 250))
        _DrwTx.Draw(_im).ellipse([180, 180, 720, 720], fill=cor)
        import io as _io_bx
        _b = _io_bx.BytesIO()
        _im.save(_b, format="PNG")
        return _b.getvalue()
    ok("produto repintado e REPROVADO contra as fotos",
       "nao bate com as fotos" in _md_tx.produto_diferente(
           _bola_tx((40, 70, 170)), [_bola_tx((40, 160, 70))]))
    ok("e o produto da cor certa passa",
       not _md_tx.produto_diferente(
           _bola_tx((40, 160, 70)), [_bola_tx((40, 160, 70))]))

    # ── O PEDIDO DE IMAGEM QUADRADA, QUE VIROU MARGEM ───────────────────
    #
    # Dono, 30/09: "imagem 3 esta com margem na foto" — e eu cheguei a
    # responder que aquilo "nao tinha conserto por codigo". Tinha: o Studio
    # mandava UM nome de campo, a API respondia 400, e ele desistia da
    # proporcao. Voltava retangular, o enquadramento preenchia as sobras, e a
    # peca saia com margem. O nome do campo estava errado.
    #
    # Esta guarda nao chama a API: ela troca o `requests.post` por um duplo
    # que RECUSA o nome antigo e ACEITA o documentado, e confere que o Studio
    # encontra o certo sozinho — e que na proxima peca vai direto nele, sem
    # pagar as tentativas de novo.
    import requests as _rq_pr
    _corpos_vistos = []

    class _RespFalsa:
        def __init__(self, code):
            self.status_code = code
            self.text = "{}" if code == 200 else '{"error":{"message":"unknown name"}}'
        def json(self):
            return ({"candidates": [{"content": {"parts": []}}]} if self.status_code == 200
                    else {"error": {"message": "Unknown name"}})

    def _post_falso(url, json=None, headers=None, **kw):
        _cfg = (json or {}).get("generationConfig", {})
        _corpos_vistos.append(sorted(k for k in _cfg if k != "responseModalities"))
        # A API DESTE DUPLO so aceita `imageConfig` — que e o nome documentado
        # para o endpoint generateContent.
        return _RespFalsa(200 if "imageConfig" in _cfg else 400)

    _post_real = _rq_pr.post
    _chave_real = globals().get("_get_gemini_api_key")
    _forma_antes = dict(_FORMA_PROPORCAO)
    try:
        _rq_pr.post = _post_falso
        globals()["_get_gemini_api_key"] = lambda: "chave-de-teste"
        _FORMA_PROPORCAO["nome"] = None
        _chamar_gemini_geracao_texto("prompt de teste", [])
        ok("o Studio acha sozinho a forma que a API aceita",
           _FORMA_PROPORCAO["nome"] == "imageConfig")
        ok("e ela foi a PRIMEIRA tentada — o nome documentado vem antes",
           _corpos_vistos and _corpos_vistos[0] == ["imageConfig"])
        # E NAO PAGA A DESCOBERTA DE NOVO NA PROXIMA PECA.
        _corpos_vistos.clear()
        _chamar_gemini_geracao_texto("outra peca", [])
        ok("na peca seguinte ele vai direto na forma aprendida",
           len(_corpos_vistos) == 1 and _corpos_vistos[0] == ["imageConfig"])
        # E SE A API PASSAR A RECUSAR TUDO: ERRO, E NAO PECA COM MARGEM.
        #
        # ESTA ASSERCAO DIZIA O CONTRARIO ATE 01/10, e exigia o defeito:
        # "recusando tudo, ele ainda tenta a ultima sem proporcao". Era a
        # Forma 2 — a guarda travando a REDACAO do comportamento errado. O
        # comentario ao lado ate justificava: "peca com margem e melhor que
        # peca nenhuma". Nao e: "margem nas fotos" e um dos oito defeitos
        # que o dono quer que parem, e peca paga torta custa mais que um
        # erro na tela.
        #
        # Agora mede o oposto, e mede as DUAS metades: nenhum corpo sai sem
        # pedir proporcao, E a funcao devolve erro em vez de resposta.
        _FORMA_PROPORCAO["nome"] = None
        _corpos_vistos.clear()
        _rq_pr.post = lambda url, json=None, headers=None, **kw: (
            _corpos_vistos.append(sorted(k for k in (json or {}).get(
                "generationConfig", {}) if k != "responseModalities"))
            or _RespFalsa(400))
        _r3, _e3 = _chamar_gemini_geracao_texto("terceira", [])
        ok("recusando tudo, NENHUM corpo sai sem pedir proporcao",
           _corpos_vistos and [] not in _corpos_vistos)
        ok("recusando tudo, a funcao devolve ERRO em vez de peca com margem",
           _r3 is None and bool(_e3) and "quadrada" in str(_e3))
    finally:
        _rq_pr.post = _post_real
        if _chave_real is not None:
            globals()["_get_gemini_api_key"] = _chave_real
        _FORMA_PROPORCAO.clear()
        _FORMA_PROPORCAO.update(_forma_antes)
    # ── QUANTOS CARTOES O PROMPT PEDE — NUNCA UMA FAIXA ───────────────────
    #
    # `blocos_em_portugues` dizia, quando nao havia copy da triagem: "use de
    # 2 a 5 blocos informativos, CONFORME O CONTEUDO DISPONIVEL". Quem
    # decidia quantos cartoes desenhar era o gerador — que nao sabe o que e
    # "conteudo disponivel" e escolhe pelo que couber no desenho.
    #
    # Achado na auditoria externa de 01/10, junto com outras tres rotas de
    # emergencia. O sistema SABE o numero: e o teto do tipo. Entao ele fecha.
    #
    # A guarda mede os dois caminhos, porque so o primeiro tinha cobertura:
    # com copy o prompt ja dizia "exatamente N"; sem copy e que mandava a
    # faixa, e e esse o caminho que nenhum verificador percorria.
    _bp_tipos = [t for t in TIPOS_PADRAO if faixa_de_blocos(t)[1]]
    ok("ha tipo com bloco de texto para medir", bool(_bp_tipos))
    _bp_com = [blocos_em_portugues(t, 3) for t in _bp_tipos]
    ok("com copy, o prompt diz EXATAMENTE quantos blocos a copy trouxe",
       all("exatamente 3 bloco" in x for x in _bp_com))
    # ── SEM COPY, ZERO BLOCO. As tres guardas que viviam aqui exigiam o
    # CONTRARIO — "sem copy o prompt tambem fecha o numero" — e por isso
    # ficaram verdes enquanto a peca 4 escrevia "TITULO CURTO EM CAIXA ALTA"
    # dentro do cartao e a peca 5 inventava sete cotas. Elas guardavam o
    # defeito. Forma 2 do CLAUDE.md, com um agravante: a guarda nao travava a
    # redacao, travava a REGRA ERRADA.
    _bp_sem = [blocos_em_portugues(t, 0) for t in _bp_tipos]
    ok("sem copy, o prompt NAO pede numero nenhum de bloco",
       not any(_re_imp.search(r"exatamente \d+ bloco", x) for x in _bp_sem))
    ok("sem copy, nenhuma frase do tipo 'de N a M blocos'",
       not any(_re_imp.search(r"de \d+ a \d+ blocos", x) for x in _bp_sem))
    ok("sem copy, nenhum 'conforme o conteudo'",
       not any("conforme o conte" in x.lower() for x in _bp_sem))
    ok("sem copy, o prompt PROIBE escrever qualquer palavra",
       all("NÃO escreva nenhuma palavra" in x for x in _bp_sem))
    ok("e diz POR QUE, para a peca limpa nao parecer bug",
       all("não recebeu copy" in x.lower() for x in _bp_sem))
    # O tipo 7 tem teto 1 e caia num ramo proprio, que tambem pedia 1 bloco
    # sem ter palavra. Ele precisa cair na mesma regra dos outros.
    _t7 = [t for t in TIPOS_PADRAO if numero_do_tipo(t) == 7]
    ok("o tipo de teto 1 (Presenteie) nao escapa pela porta do lado",
       _t7 and "NÃO escreva nenhuma palavra" in blocos_em_portugues(_t7[0], 0))

    # ── SEM COPY, NADA QUE FALE DE CARTAO ENTRA NO PROMPT ────────────────
    #
    # A METADE QUE FALTOU da correcao de 02/10, achada no prompt real de
    # 05/10 (pecas 5 e 7). Eu travei a linha que PEDE os blocos e deixei a
    # medida do cartao saindo incondicionalmente. O prompt dizia, em duas
    # linhas seguidas: "NAO escreva nenhuma palavra" e "Cada bloco: titulo
    # curto em CAIXA ALTA (2 a 4 palavras) + frase de 8 a 9 palavras".
    #
    # A segunda e LITERALMENTE o texto que o Gemini desenhou dentro do
    # cartao no teste anterior. Proibir a frase e deixar a receita dela ao
    # lado e a Forma 1 cometida dentro do conserto da Forma 1.
    _marcas_de_cartao = ("CAIXA ALTA", "FORMA DO CARTÃO", "UMA coluna vertical",
                         "QUANTIDADE DE CARTÕES", "cartões empilhados")
    for _t_sc in TIPOS_PADRAO:
        _r_sc = instrucao_de_layout(
            _t_sc, blocos_em_portugues(_t_sc, 0), medida_do_bloco())
        _achou = [m for m in _marcas_de_cartao if m in _r_sc]
        ok(f"sem copy, o tipo {numero_do_tipo(_t_sc)} nao recebe regra de cartao",
           not _achou)
        if _achou:
            print("      ainda fala de:", ", ".join(_achou))
    # E COM COPY nada mudou: quem TEM texto continua recebendo a regra.
    ok("com copy, a peca de cartao continua recebendo a medida",
       "CAIXA ALTA" in instrucao_de_layout(
           "2 — Benefícios do produto",
           blocos_em_portugues("2 — Benefícios do produto", 3),
           medida_do_bloco()))
    ok("e a de cartao continua recebendo a forma",
       "FORMA DO CARTÃO" in instrucao_de_layout(
           "6 — Quebra de objeção",
           blocos_em_portugues("6 — Quebra de objeção", 3),
           medida_do_bloco()))
    # A peca sem texto NAO perde o que vale de qualquer jeito.
    _r_sem = instrucao_de_layout(
        "5 — Características técnicas (medidas/peso/material)",
        blocos_em_portugues("5 — Características técnicas (medidas/peso/material)", 0),
        medida_do_bloco())
    ok("mas ela mantem a proibicao de sobrepor o produto",
       "JAMAIS sobreponha texto" in _r_sem)
    ok("e mantem a regra de texto real",
       "REGRA DE TEXTO REAL" in _r_sem)

    # ── A GEOMETRIA E CALCULADA, E NAO ADIVINHADA PELO MODELO ───────────
    #
    # ACHADO comparando o prompt que gerou errado com o que gerou certo no
    # teste de 05/10: os oito prompts iniciais sao IDENTICOS aos finais. O
    # que mudou foi so o que as correcoes acrescentaram depois de o dono
    # reclamar tres vezes — e nao era regra nova, era a MESMA regra em outra
    # unidade: "nao sobreponha" virou "ZONA ESQUERDA 0-50%, ZONA DIREITA
    # 55-97%, corredor vazio entre as duas".
    ok("a folga em pixel sai da porcentagem, e nao de um numero escrito",
       em_px(FOLGA_BORDA_PCT) == round(FOLGA_BORDA_PCT / 100 * LADO_GERADO_PX))
    _z6 = zonas_da_peca("6 — Quebra de objeção", 4)
    ok("a peca de cartao recebe zona do produto, corredor e zona dos cartoes",
       all(x in _z6 for x in ("ZONA DO PRODUTO", "CORREDOR VAZIO",
                              "ZONA DOS CARTÕES")))
    ok("e a quantidade de cartoes da zona e a que a copy trouxe",
       "4 cartões vivem AQUI" in _z6)
    ok("a folga aparece em PIXEL ao lado da porcentagem",
       f"{em_px(FOLGA_BORDA_PCT)} pixels" in _z6)
    # AS ZONAS NAO PODEM SE TOCAR — e esta e a conta, nao a frase.
    import re as _re_z
    _nums = [int(x) for x in _re_z.findall(r"de (\d+)% a (\d+)%", _z6)[0]]
    _fim_prod = int(_re_z.findall(r"ZONA DO PRODUTO: de \d+% a (\d+)%", _z6)[0])
    _ini_cart = int(_re_z.findall(r"ZONA DOS CARTÕES: de (\d+)%", _z6)[0])
    # O CORREDOR SE MEDE CONTRA UM MINIMO REAL, E NAO CONTRA A CONSTANTE.
    #
    # A primeira versao desta linha dizia `>= CORREDOR_PCT`. Com a mutacao
    # `CORREDOR_PCT = 0` ela virava `>= 0` — verdade sem medir nada, e a
    # guarda ficou VERDE com as duas zonas encostadas. E a 16a entrada do
    # `checar_mutacao` de novo: assercao que usa o valor mutado como
    # referencia nao mede o valor, mede a si mesma.
    ok("entre o fim do produto e o inicio dos cartoes ha corredor de verdade",
       _ini_cart - _fim_prod >= 3)
    ok("e o corredor em pixel nao e zero",
       em_px(_ini_cart - _fim_prod) >= 30)
    # PECA SEM COPY NAO GANHA ZONA DE CARTAO: seria oferecer cartao a quem o
    # prompt acabou de proibir de escrever.
    ok("peca sem copy nao recebe zona nenhuma",
       zonas_da_peca("6 — Quebra de objeção", 0) == "")
    # AS PECAS DE CENA TAMBEM NAO: nelas o tamanho e a escala real, e exigir
    # porcentagem delas foi o que produziu o produto gigante na mao da
    # crianca, tres vezes.
    for _t_cena in TIPOS_PADRAO:
        if OCUPACAO.get(numero_do_tipo(_t_cena)) is None:
            ok(f"a peca de cena {numero_do_tipo(_t_cena)} nao recebe zona",
               zonas_da_peca(_t_cena, 3) == "")
    # E A GEOMETRIA CHEGA AO PROMPT, nao basta a funcao existir.
    _p_z = montar_prompt_imagem(
        "6 — Quebra de objeção", "", {}, "Caneca",
        plano_triagem={"composicao": "x", "cena": "y",
                       "textos": ["A: um", "B: dois", "C: tres", "D: quatro"]})
    ok("a geometria calculada chega ao prompt da peca",
       "GEOMETRIA DESTA PEÇA" in _p_z and "CORREDOR VAZIO" in _p_z)

    # ── 8 NA GALERIA NAO E 8 ENTREGUES ──────────────────────────────────
    #
    # ACHADO NA CONVERSA REAL DE 05/10: o dono perguntou quais nao sairam e
    # o chat respondeu "nenhuma deixou de ser gerada — as 8 estao na
    # galeria", com DUAS delas marcadas "nao publique assim" na tela.
    #
    # A ENTRADA E A FORMA QUE A TELA MONTA: cada item tem `peca` e `texto`,
    # os dois relatos que `revisar_tudo` devolve (imagem.py ~10136). Nao e
    # um dicionario inventado aqui.
    _gal = [
        {"tipo": "1 — Capa", "peca": {"ok": True}, "texto": {"ok": True}},
        {"tipo": "2 — Benefícios", "peca": {"ok": False,
                                            "problemas": ["cartões sobre o produto"]},
         "texto": {"ok": True}},
        {"tipo": "5 — Técnicas", "peca": {"ok": True},
         "texto": {"ok": False, "problemas": ["PROFUNDITUDE"]}},
        {"tipo": "6 — Objeção", "peca": {"ok": None}, "texto": {"ok": None}},
    ]
    _pl = placar_do_lote(_gal, 8)
    ok("a peca com defeito de IMAGEM conta como reprovada",
       _pl["reprovadas"] == 2)
    ok("a peca com defeito de TEXTO tambem — portugues errado nao publica",
       any(g.get("texto", {}).get("ok") is False for g in _gal))
    ok("so conta aprovada quem passou nas DUAS conferencias",
       _pl["aprovadas"] == 1)
    ok("nao conferida e diferente de reprovada", _pl["nao_conferidas"] == 1)
    ok("e o que nao foi gerado aparece como pendente", _pl["pendentes"] == 4)
    ok("a frase NUNCA diz '8 de 8' havendo reprovada",
       "8 de 8" not in frase_do_placar(_pl)
       and "reprovada" in frase_do_placar(_pl))
    # LOTE PERFEITO: a frase nao inventa problema que nao existe.
    _pl_ok = placar_do_lote([{"peca": {"ok": True}, "texto": {"ok": True}}] * 8, 8)
    ok("lote inteiro aprovado diz 8 de 8 e mais nada",
       frase_do_placar(_pl_ok) == "8 de 8 aprovada(s)")
    ok("galeria vazia nao derruba o placar",
       placar_do_lote([], 8)["pendentes"] == 8
       and placar_do_lote(None)["geradas"] == 0)

    # E O PLACAR CHEGA AOS DOIS LEITORES: a tela e o chat. Guarda que mede
    # so a funcao deixa passar o dia em que ninguem a chama.
    # `_fonte_tela` e a fonte de `pagina_imagem` SO — esta guarda vive no
    # bloco `__main__`, entao ela nao pode se encontrar a si mesma, que e o
    # defeito que as guardas desta base ja cometeram tres vezes.
    ok("a tela mostra o placar do lote", "placar_do_lote(" in _fonte_tela)
    ok("e usa a frase unica, nao uma redacao propria",
       "frase_do_placar(" in _fonte_tela)
    import chat_assistente as _chat_pl
    _fonte_ctx = _inspect_g.getsource(_chat_pl)
    ok("o contexto do chat carrega o veredito de cada peca",
       "REPROVADA — não publique" in _fonte_ctx)
    ok("e o chat e avisado de que estar na galeria nao e estar pronta",
       "ESTAR NA GALERIA NÃO É ESTAR PRONTA" in _fonte_ctx)

    # ── A PROMESSA SEM LASTRO NAO CHEGA AO MOTOR ────────────────────────
    #
    # `promessas_sem_lastro` ja AVISAVA desde 02/10. Aviso nao e barreira: a
    # peca 6 do teste de 05/10 foi ao Gemini com "MANTEM BEBIDA QUENTE? Sim,
    # termica em metal e resina" e o cadastro nao tem ensaio termico nenhum.
    # A arte saiu boa, o conferidor aprovou, e o claim falso iria para a
    # pagina do produto.
    # O CADASTRO E O DO PRODUTO REAL, com a medida da alca que a copy cita.
    # Sem ela a barreira de MEDIDA tirava "A ALCA CABE NA MAO?: Sim, medidas
    # 5,2cm" — e estava certa: 5,2 nao existia em cadastro nenhum. Completar
    # a entrada e o conserto; afrouxar a barreira seria consertar o
    # termometro.
    _dd_cl = {"material": "Metal e Resina",
              "caracteristicas": "altura: 5,2cm largura: 2,4",
              "diferenciais": "interior em inox diferencia de canecas decorativas"}
    _copy_cl = ["A ALÇA CABE NA MÃO?: Sim, medidas 5,2cm",
                "MANTÉM BEBIDA QUENTE?: Sim, térmica em metal e resina",
                "É SÓ DECORATIVA?: Não, interior inox"]
    _limpos, _fora_cl = copy_sem_promessa(_copy_cl, _dd_cl)
    ok("o bloco sem lastro sai da copy", len(_fora_cl) == 1
       and "MANTÉM BEBIDA QUENTE" in _fora_cl[0])
    ok("e os que o cadastro sustenta ficam", len(_limpos) == 2)
    # O BLOCO SAI INTEIRO, e nao so a palavra: apagar "mantem quente" de uma
    # PERGUNTA deixaria o cartao com pergunta e sem resposta.
    ok("o bloco sai inteiro, nao a palavra",
       all("MANTÉM" not in t for t in _limpos))
    ok("sem dados cadastrados, nada passa com promessa",
       copy_sem_promessa(["RESISTENTE: aguenta queda"], {})[0] == [])
    ok("copy sem promessa nenhuma atravessa inteira",
       copy_sem_promessa(["DESIGN ÚNICO: foge do padrão"], _dd_cl)[0]
       == ["DESIGN ÚNICO: foge do padrão"])
    # E A BARREIRA ESTA NO CAMINHO, nao so na funcao: a cadeia inteira.
    _p_cl = montar_prompt_imagem(
        "6 — Quebra de objeção", "", _dd_cl, "Caneca",
        plano_triagem={"composicao": "x", "cena": "y", "textos": _copy_cl})
    ok("o claim sem lastro NAO chega ao prompt",
       "MANTÉM BEBIDA QUENTE" not in _p_cl)
    ok("e os dois que tem lastro chegam",
       "A ALÇA CABE NA MÃO" in _p_cl and "SÓ DECORATIVA" in _p_cl)
    # A CONTAGEM ACOMPANHA: tirar bloco e nao corrigir o numero deixaria o
    # prompt pedindo 3 cartoes com 2 textos — o defeito de 30/09.
    ok("a contagem de blocos acompanha a remocao",
       "exatamente 2 bloco" in _p_cl)
    ok("a tela diz que o bloco foi REMOVIDO, e nao so que e suspeito",
       "Bloco(s) removidos" in _fonte_tela)

    # A ORDEM — BARREIRA ANTES DO TETO — E ISSO SE MEDE, nao se declara.
    #
    # A primeira versao deste bloco tinha um comentario dizendo que a ordem
    # importa, e a mutacao que trocava a ordem passou VERDE: nenhuma guarda
    # media. Comentario que afirma o que nenhuma assercao cobre e a Forma 3
    # — dizer verde sobre o que o verificador nao le.
    #
    # Ela importa quando a copy vem com MAIS blocos que o teto e um dos
    # primeiros nao tem lastro: cortar pelo teto primeiro guarda o ruim e
    # joga fora um bom que vinha depois.
    _dd_ord = {"material": "inox", "diferenciais": "cabe na mao, nao escorrega, "
                                                   "lava na maquina, empilha, "
                                                   "nao enferruja"}
    _copy_ord = ["RESISTENTE: aguenta queda",          # <- SEM lastro
                 "CABE NA MÃO: pega confortável",
                 "NÃO ESCORREGA: base firme",
                 "LAVA NA MÁQUINA: sem cuidado especial",
                 "EMPILHA: ocupa pouco armário",
                 "NÃO ENFERRUJA: inox de verdade"]      # <- bom, e e o 6o
    _p_ord = montar_prompt_imagem(
        "2 — Benefícios do produto", "", _dd_ord, "Caneca",
        plano_triagem={"composicao": "x", "cena": "y", "textos": _copy_ord})
    ok("com a barreira ANTES do teto, o bloco sem lastro sai",
       "RESISTENTE: aguenta queda" not in _p_ord)
    ok("e o bom que vinha depois do teto ENTRA no lugar dele",
       "NÃO ENFERRUJA" in _p_ord)
    ok("a peca fica com o teto cheio de blocos bons",
       f"exatamente {faixa_de_blocos('2 — Benefícios do produto')[1]} bloco"
       in _p_ord)

    # ── NUMERO QUE O CADASTRO NAO TEM NAO VIRA ORDEM ────────────────────
    #
    # A PIOR CLASSE DE DEFEITO DESTA CADEIA, achada em 05/10 na peca 5: o
    # sistema LAVA a invencao do modelo em ordem do Studio.
    #
    # O MESMO prompt dizia "Medidas EXATAS (use esses numeros, nao invente):
    # 12x14" e, mais abaixo, "TEXTO EXATO (copie letra por letra): ALTURA
    # 30mm (...) PROFUNDIDADE 25mm (...) LARGURA INTERNA 17mm (...) LARGURA
    # 35mm" — num bloco que se declara "acima de qualquer outra instrucao de
    # texto". O Gemini obedeceu a ordem mais forte, e estava certo.
    #
    # A ENTRADA E O CADASTRO REAL da Caneca, como a tela monta.
    _dd_med = {"nome_produto": "Caneca Térmica Medieval 400Ml",
               "medidas": "12x14", "peso": "326",
               "caracteristicas": "altura: 5,2cm largura: 2,4",
               "material": "Metal e Resina",
               "diferenciais": "400ml bom tamanho para todas as bebidas"}
    _copy_med = ["ALTURA 30mm PROFUNDIDADE 25mm LARGURA INTERNA 17mm LARGURA 35mm",
                 "CAPACIDADE VERSÁTIL: 400ml perfeito para todas as bebidas",
                 "ALÇA ERGONÔMICA: medidas 5,2cm x 2,4cm",
                 "PESO 326g",
                 "ALTURA 12cm LARGURA 14cm"]
    _limpos_m, _fora_m = copy_sem_medida_inventada(_copy_med, _dd_med)
    ok("o bloco com medida inventada sai", len(_fora_m) == 1
       and "30mm" in _fora_m[0])
    ok("e os quatro que o cadastro sustenta ficam", len(_limpos_m) == 4)
    # OS NUMEROS REAIS NAO PODEM SER ACUSADOS — alarme falso aqui apagaria a
    # copy boa do produto.
    ok("400ml nao e acusado: esta no nome e nos diferenciais",
       not medidas_sem_lastro(["CAPACIDADE: 400ml"], _dd_med))
    ok("5,2cm e 2,4cm nao sao acusados: estao nas caracteristicas",
       not medidas_sem_lastro(["ALÇA: 5,2cm x 2,4cm"], _dd_med))
    ok("326g nao e acusado: esta no peso",
       not medidas_sem_lastro(["PESO 326g"], _dd_med))
    # CONTAGEM SEM UNIDADE NAO E MEDIDA, e confundir as duas seria apagar
    # "4 cartoes" de uma copy legitima.
    ok("numero sem unidade nao e medida",
       not medidas_sem_lastro(["4 cartões bem distribuídos"], _dd_med))
    # E O BLOCO SAI INTEIRO: tirar so o numero deixaria "ALTURA" sozinho num
    # cartao de cota.
    ok("o bloco sai inteiro, nao o numero",
       all("30mm" not in t for t in _limpos_m))
    # SEM CADASTRO NENHUM, toda medida e inventada — e a peca sai sem cota,
    # que e correto: peca sem cota e certa, peca com cota inventada e errada.
    ok("sem cadastro, nenhuma medida passa",
       copy_sem_medida_inventada(["ALTURA 12cm"], {})[0] == [])
    # E A BARREIRA ESTA NOS DOIS CAMINHOS: o do plano e o da REVISAO.
    #
    # O da revisao e o que importa: foi por ele que a invencao do Gemini
    # voltou como ordem. `revisar_texto` passa a limpar o "texto_correto"
    # que o juiz leu na imagem antes de injeta-lo.
    # A GUARDA EXERCITA O CAMINHO, e nao pergunta se o nome existe.
    #
    # A primeira versao dizia `"copy_sem_medida_inventada" in _fonte_rev` e
    # ficou VERDE com a mutacao que voltava a injetar o texto cru: a funcao
    # continuava escrita ali, so nao era usada. E a guarda que pergunta
    # "existe em algum lugar" em vez de "passa por aqui" — o mesmo defeito
    # que o `checar_tela` cometeu com a conferencia fora do laco.
    #
    # Agora ela ROTEIA a revisao de verdade: um juiz de mentira devolve a
    # medida inventada, e a assercao olha o prompt que saiu.
    _conf_orig = globals()["conferir_texto"]
    _prompts_vistos = []

    def _juiz_falso(_img, _pedido=""):
        return {"tem_texto": True, "correto": False,
                "erros": "PROFUNDITUDE",
                # O TIPO VEM DO ESQUEMA REAL (`imagem.py` ~6915): string,
                # nao lista. A primeira versao deste duplo devolveu lista e
                # a guarda estourou com AttributeError — a Forma 7, cometida
                # dentro da guarda que mede a Forma 7.
                "texto_correto": "ALTURA 30mm PROFUNDIDADE 25mm"}, ""

    def _gera_falso(_p):
        _prompts_vistos.append(_p)
        return b"nova", ""

    globals()["conferir_texto"] = _juiz_falso
    try:
        _p_rev = montar_prompt_imagem(
            "5 — Características técnicas (medidas/peso/material)", "",
            _dd_med, "Caneca",
            plano_triagem={"composicao": "x", "cena": "y",
                           "textos": ["ALTURA 12cm", "PESO 326g"]})
        _, _rel_rev, _ = revisar_texto(
            b"img", "5 — Características técnicas (medidas/peso/material)",
            gerar=_gera_falso, prompt_base=_p_rev, rodadas=2,
            dados_descricao=_dd_med)
    finally:
        globals()["conferir_texto"] = _conf_orig
    # CASO A — o juiz devolveu SO invencao. A revisao NAO gera: refazer com
    # a mesma invencao so repetiria o erro, e cada rodada e uma geracao paga.
    ok("texto todo inventado: a revisao nao gasta geracao",
       not _prompts_vistos)
    ok("e ela diz por que, em vez de reprovar calada",
       "medida que o cadastro não tem" in (_rel_rev or {}).get("erros", ""))

    # CASO B — o juiz devolveu invencao MAIS algo que o cadastro sustenta.
    # Agora ela gera, e o que vai ao motor e so a parte com lastro.
    _prompts_b = []

    def _juiz_misto(_img, _pedido=""):
        return {"tem_texto": True, "correto": False, "erros": "PROFUNDITUDE",
                "texto_correto": "ALTURA 30mm\nPESO 326g"}, ""

    def _gera_b(_p):
        _prompts_b.append(_p)
        return b"nova", ""

    globals()["conferir_texto"] = _juiz_misto
    try:
        revisar_texto(b"img",
                      "5 — Características técnicas (medidas/peso/material)",
                      gerar=_gera_b, prompt_base=_p_rev, rodadas=2,
                      dados_descricao=_dd_med)
    finally:
        globals()["conferir_texto"] = _conf_orig
    ok("com algo que o cadastro sustenta, a revisao refaz", bool(_prompts_b))
    ok("e a medida inventada NAO vai ao motor",
       all("30mm" not in _p for _p in _prompts_b))
    ok("mas a que o cadastro tem vai",
       any("326g" in _p for _p in _prompts_b))
    _fonte_mp = _inspect_g.getsource(montar_prompt_imagem)
    ok("o caminho do plano tambem limpa",
       "copy_sem_medida_inventada" in _fonte_mp)
    # COM copy nada mudou: a peca que TEM texto continua pedindo o numero.
    ok("com copy, o numero continua fechado",
       all("exatamente 3 bloco" in x for x in _bp_com))

    ok("vazio e None nao derrubam",
       sem_medida_de_quadro("") == "" and sem_medida_de_quadro(None) == "")

    # E A LIMPEZA TEM DE ESTAR NO CAMINHO, nao so existir. Nenhum teste de
    # unidade pega uma funcao que ninguem chama — foi o erro de hoje de manha,
    # duas vezes.
    _p_capa = montar_prompt_imagem(
        "1 — Capa do anúncio (fundo branco)", "", {}, "Caneca",
        plano_triagem={"composicao": "produto centralizado",
                       "cena": _CENA_REAL, "textos": []})
    ok("e a cena chega ao prompt JA limpa",
       "60%" not in _p_capa and "Fundo branco puro" in _p_capa)

    # ── E O AVISO DE PECA SEM COPY ESTA NA TELA, NAO SO NO PROMPT ─────────
    #
    # O prompt ja proibe escrever palavra sem copy. Mas peca que sai limpa
    # sem explicacao parece bug, e quem paga a geracao e o dono. A guarda le
    # a ARVORE da tela (`ast`), e nao o texto do arquivo: guarda que varre o
    # arquivo se encontra a si mesma — ja aconteceu tres vezes nesta base.
    import ast as _ast_g
    _fonte_tela = _inspect_g.getsource(pagina_imagem)
    _tem_aviso = any(
        isinstance(_no, _ast_g.If) and _no.orelse
        and "faixa_de_blocos" in _ast_g.dump(_ast_g.Module(body=_no.orelse,
                                                           type_ignores=[]))
        and "não escreveu texto" in _ast_g.dump(
            _ast_g.Module(body=_no.orelse, type_ignores=[]))
        for _no in _ast_g.walk(_ast_g.parse(_fonte_tela)))
    ok("peca sem copy avisa NA TELA, antes de gastar a geracao", _tem_aviso)

    # ── INJETAR COPY NUMA PECA "SEM COPY" APAGA A ORDEM CONTRARIA ────────
    #
    # ACHADO EM PRODUCAO, 05/10, no prompt real da Caneca Termica Medieval:
    # a peca 5 foi ao Gemini com "NAO escreva nenhuma palavra, nenhum titulo,
    # nenhum cartao" E, doze linhas abaixo, "escreva EXATAMENTE estas
    # palavras, letra por letra, acima de qualquer outra instrucao de texto".
    #
    # O defeito foi MEU e nasceu da correcao de 02/10: a linha do "sem copy"
    # deixou de ter numero, e `trocar_texto_exato` — que sincroniza a
    # contagem por um regex de `exatamente \d+ bloco` — nao tinha mais o que
    # casar. Pior: num prompt SEM bloco de texto ela saia por um `return`
    # antecipado e nem chegava na sincronia.
    #
    # A cadeia e exercitada INTEIRA: o prompt nasce de `montar_prompt_imagem`
    # com `textos: []`, como a tela monta, e nao de uma string escrita aqui.
    _p_sem = montar_prompt_imagem(
        "5 — Características técnicas (medidas/peso/material)", "",
        {"medidas": "altura 30mm", "peso": "326g"}, "Caneca",
        plano_triagem={"composicao": "x", "cena": "y", "textos": []})
    ok("a peca sem copy nasce proibindo escrever", MARCA_SEM_COPY in _p_sem)
    ok("e sem bloco de TEXTO EXATO", MARCA_TEXTO_EXATO not in _p_sem)
    _p_aj = trocar_texto_exato(_p_sem, ["ALTURA 30mm", "PESO 326g",
                                        "MATERIAL metal e resina"])
    ok("injetada a copy, a ordem de NAO escrever SAI",
       MARCA_SEM_COPY not in _p_aj)
    ok("e o bloco de TEXTO EXATO entra", MARCA_TEXTO_EXATO in _p_aj)
    ok("com a contagem batendo com o que entrou",
       "exatamente 3 bloco" in _p_aj)
    # E O CAMINHO QUE JA FUNCIONAVA continua funcionando: peca COM copy.
    _p_com = montar_prompt_imagem(
        "2 — Benefícios do produto", "", {}, "Caneca",
        plano_triagem={"composicao": "x", "cena": "y",
                       "textos": ["UM: frase", "DOIS: frase", "TRES: frase"]})
    _p_com2 = trocar_texto_exato(_p_com, ["UM: outra", "DOIS: outra"])
    ok("peca COM copy: a contagem segue o texto novo",
       "exatamente 2 bloco" in _p_com2)
    ok("e ela nunca ganha a frase de 'sem copy'",
       MARCA_SEM_COPY not in _p_com2)

    # ── PROMESSA SEM LASTRO ───────────────────────────────────────────────
    #
    # A ENTRADA VEM NA FORMA QUE A TELA MONTA: `dados_descricao` e um
    # dicionario de campos do colaborador, e nao um texto solto. Escrever uma
    # string aqui mediria o meu entendimento do sistema — foi assim que o
    # botao dos oito prompts quebrou em producao com a guarda verde.
    _dd_real = {"material": "Metal e Resina",
                "diferenciais": "interior em inox diferencia de canecas "
                                "decorativas, visual inspirado em pedra",
                "caracteristicas": "altura: 5,2cm largura: 2,4",
                "uso": "uso diário, bar, festas temáticas"}
    _copy_real = ["VERSÁTIL E FUNCIONAL: cabe em qualquer bebida e ocasião",
                  "INOX POR DENTRO: durável e diferente de canecas decorativas",
                  "DESIGN ÚNICO: foge do padrão medieval com realismo"]
    _pr = promessas_sem_lastro(_copy_real, _dd_real)
    ok("acusa 'durável' — a palavra nao esta em dado nenhum do produto",
       len(_pr) == 1 and "durável" in _pr[0][1])
    ok("e NAO acusa as outras duas, que sao atributo e nao promessa",
       all("VERSÁTIL" not in t and "DESIGN" not in t for t, _ in _pr))
    ok("promessa que ESTA nos dados passa",
       not promessas_sem_lastro(
           ["MANTÉM A TEMPERATURA: por horas"],
           dict(_dd_real, diferenciais="mantém a temperatura por 6 horas")))
    ok("sem dados cadastrados, toda promessa e sem lastro",
       len(promessas_sem_lastro(["RESISTENTE: aguenta queda"], {})) == 1)
    ok("texto sem promessa nenhuma nao vira aviso",
       promessas_sem_lastro(["DESIGN ÚNICO: foge do padrão"], _dd_real) == [])
    ok("o mesmo termo nao sai duas vezes por causa do acento",
       len(promessas_sem_lastro(["DURÁVEL de verdade"], {})[0][1]) == 1)

    # E o aviso esta NA TELA, pela arvore — nao basta a funcao existir.
    _tem_promessa = "promessas_sem_lastro" in _ast_g.dump(
        _ast_g.parse(_fonte_tela))
    ok("promessa sem lastro avisa NA TELA, antes de gastar a geracao",
       _tem_promessa)

    # ── A PECA E OLHADA, E NAO SO LIDA ──────────────────────────────────
    #
    # O dono, 28/09: "por que o prompt continua gerando imagens erradas
    # mudando o produto e posicionando informacoes cortadas?"
    #
    # A resposta estava nos 9 prompts dele: as regras violadas estavam TODAS
    # escritas. "A FOLGA DA BORDA MANDA" aparecia 5 vezes, "NADA SOBREPOE O
    # PRODUTO" 6, "JAMAIS substitua o produto" 7. Pela legenda do proprio
    # .txt: regra nos dois lados -> o modelo ignorou, e escrever de novo nao
    # resolve.
    #
    # E a conferencia que existia — `revisar_texto` — pergunta UMA coisa: o
    # que esta escrito e portugues correto? Ela nao ve texto CORTADO pela
    # borda, cartao SOBRE o produto, nem alca a mais. A peca saia com o
    # portugues perfeito e a caneca com duas alcas.
    #
    # `revisar_peca` faz as outras quatro perguntas, olhando a peca AO LADO
    # das fotos de referencia. E a correcao dela nao e trocar a copy: e
    # refazer com uma instrucao que nomeia o defeito.
    _olhos = []

    def _olho(*vereditos):
        fila = list(vereditos)

        def _f(img, fotos_ref=None, tipo=""):
            _olhos.append((img, tuple(fotos_ref or ()), tipo))
            v = fila.pop(0) if fila else _APROVADA
            return (None, v) if isinstance(v, str) else (v, "")
        return _f

    _APROVADA = {"aprovada": True, "problemas": [], "instrucao": ""}
    _CORTADA = {"aprovada": False, "problemas": ["texto cortado pela borda"],
                "instrucao": "Todos os cartoes inteiros dentro do quadro, "
                             "com folga de 6% em cada lado."}
    _DUAS_ALCAS = {"aprovada": False,
                   "problemas": ["produto diferente das fotos: alca a mais"],
                   "instrucao": "A caneca tem UMA alca, a direita, como nas "
                                "fotos. Nao acrescente uma segunda."}

    # DE ONDE VEIO ESTE DADO (passo 6 do protocolo).
    #
    # Os tres vereditos acima sao escritos a mao, e valor de teste escrito a
    # mao e suspeito por definicao: foi assim que o botao dos oito prompts
    # quebrou com a guarda verde, porque eu passei um texto onde o sistema
    # tem um dicionario. Quem PRODUZ o veredito de verdade e o esquema de
    # ferramenta dentro de `conferir_peca` — entao e contra ele que os
    # duplos sao conferidos, e nao contra a minha lembranca.
    import ast as _ast_esq
    import inspect as _insp_img
    _src_cp = _insp_img.getsource(conferir_peca)
    _chaves_esq = set()
    for _n in _ast_esq.walk(_ast_esq.parse(_src_cp.lstrip())):
        if (isinstance(_n, _ast_esq.Dict)
                and any(getattr(k, "value", None) == "required"
                        for k in _n.keys)):
            for _k, _v in zip(_n.keys, _n.values):
                if getattr(_k, "value", None) == "required":
                    _chaves_esq = {e.value for e in _v.elts}
    ok("o esquema da conferencia pede as tres chaves que a guarda usa",
       _chaves_esq == {"aprovada", "problemas", "instrucao"})
    for _nome_v, _v in (("aprovada", _APROVADA), ("cortada", _CORTADA),
                        ("duas alcas", _DUAS_ALCAS)):
        ok(f"o duplo '{_nome_v}' tem a MESMA forma que o esquema produz",
           set(_v) == _chaves_esq)
    ok("e os tipos batem: problemas e lista, instrucao e texto",
       all(isinstance(_v["problemas"], list)
           and isinstance(_v["instrucao"], str)
           and isinstance(_v["aprovada"], bool)
           for _v in (_APROVADA, _CORTADA, _DUAS_ALCAS)))

    _real_peca = conferir_peca
    _geradas.clear()
    conferir_peca = _olho(_APROVADA)
    _img, _rel = revisar_peca(b"x", "2 — Benefícios do produto",
                              fotos_ref=[b"foto1"], gerar=_gera,
                              prompt_base="BASE")
    ok("peca aprovada passa de primeira, sem refazer",
       _rel["ok"] is True and not _geradas)
    ok("e as FOTOS DE REFERENCIA vao junto na leitura",
       _olhos and _olhos[-1][1] == (b"foto1",))

    _geradas.clear(); _olhos.clear()
    conferir_peca = _olho(_CORTADA, _APROVADA)
    _img, _rel = revisar_peca(b"x", "5 — Características técnicas (medidas/peso/material)",
                              fotos_ref=[b"foto1"], gerar=_gera,
                              prompt_base="BASE")
    ok("texto cortado e refeito e RELIDO, e a segunda leitura aprova",
       _rel["ok"] is True and _rel["rodadas"] == 2 and _img == b"nova")
    ok("a refacao recebe a instrucao que NOMEIA o defeito",
       len(_geradas) == 1 and "inteiros dentro do quadro" in _geradas[0]
       and _geradas[0].startswith("BASE"))

    _geradas.clear()
    conferir_peca = _olho(_DUAS_ALCAS, _DUAS_ALCAS)
    _img, _rel = revisar_peca(b"x", "1 — Capa do anúncio (fundo branco)",
                              fotos_ref=[b"foto1"], gerar=_gera,
                              prompt_base="BASE", rodadas=2)
    ok("A PECA SEM TEXTO TAMBEM E OLHADA — alca a mais nao e erro de portugues",
       _rel is not None and _rel["rodadas"] == 2)
    ok("reprovada ate o fim sai como reprovada, e nao como aprovada",
       _rel["ok"] is False)
    ok("duas rodadas gastam UMA refacao, e nao duas", len(_geradas) == 1)

    # ── A SEGUNDA REVISAO NAO PODE DESFAZER A PRIMEIRA ──────────────────
    #
    # `revisar_tudo` corrige o texto e DEPOIS olha a peca. Se a peca tambem
    # tiver defeito de imagem, ela e refeita — e era refeita com o prompt
    # ORIGINAL, que ainda traz a copy ERRADA que acabou de ser corrigida.
    #
    # Ou seja: a peca voltava com "Portatile" e "apoliando" de novo, depois de
    # a revisao de texto ja ter gasto uma geracao para tirar. Duas correcoes
    # brigando, e a segunda desfazendo a primeira.
    #
    # Achado pelo passo 5 — "quem mais le o que mudou?" —, e nao em producao.
    _base_vista = []

    def _gera_vendo(prompt):
        _base_vista.append(prompt)
        return b"nova", None

    conferir_texto = _leitor(_ERRADO, _CERTO)
    conferir_peca = _olho(_CORTADA, _APROVADA)
    _base_ini = montar_prompt_imagem(
        "2 — Benefícios do produto", "", {"cor": "Cinza"}, "Caneca",
        plano_triagem={"composicao": "x", "cena": "y",
                       "textos": ["TITULO ERRADO: apoliando o stresse"]})
    _img_t, _rt, _rp = revisar_tudo(
        b"x", "2 — Benefícios do produto", fotos_ref=[b"foto"],
        gerar=_gera_vendo, prompt_base=_base_ini)
    ok("a revisao de texto e a da peca rodaram as duas",
       _rt and _rp and len(_base_vista) == 2)
    ok("e a refacao DA PECA ja parte da copy CORRIGIDA",
       len(_base_vista) == 2 and "apoliando" not in _base_vista[1])
    ok("nao havendo, ela levaria de volta o erro que a primeira tirou",
       len(_base_vista) == 2
       and "PERFEITO PARA ESCRITÓRIO" in _base_vista[1])
    # E O PROMPT NAO VIAJA COM A PECA.
    #
    # O relato de texto e guardado em `galeria[i]["texto"]` e vai para a tela
    # e para o disco. Com o prompt dentro, sao 24 mil caracteres por imagem —
    # 200 mil numa geracao de oito — carregados a cada passada do Streamlit,
    # sem ninguem ler. E o mesmo custo por passada do passo 8.
    #
    # A primeira versao desta conferencia perguntou isso a um dicionario
    # VAZIO que eu montei na hora, e passou verde sem medir nada. Agora ela
    # olha o relato que `revisar_tudo` REALMENTE devolve.
    # O PROMPT NAO VIAJA NO RELATO — em nenhuma saida, e nao so na que eu
    # lembrei de testar.
    #
    # A primeira versao desta guarda chamava `ajustar_com_conferencia` e
    # passou VERDE sem chegar perto de `revisar_texto`: sem chave de API
    # aquela funcao retorna antes. Verde por caminho nao percorrido e pior que
    # vermelho.
    #
    # Agora a pergunta e feita a TODAS as saidas de `revisar_texto`, forcando
    # cada uma: aprovou de primeira, reprovou ate o fim, e falhou a leitura.
    conferir_texto = _leitor(_CERTO)
    _s1 = revisar_texto(b"x", "2 — Benefícios do produto", gerar=_gera,
                        prompt_base="BASE")
    conferir_texto = _leitor(_ERRADO, _ERRADO)
    _s2 = revisar_texto(b"x", "2 — Benefícios do produto", gerar=_gera,
                        prompt_base="BASE", rodadas=2)
    conferir_texto = _leitor("sem chave")
    _s3 = revisar_texto(b"x", "2 — Benefícios do produto", gerar=_gera,
                        prompt_base="BASE")
    _s4 = revisar_texto(b"x", "1 — Capa do anúncio (fundo branco)",
                        gerar=_gera, prompt_base="BASE")
    ok("revisar_texto devolve TRES coisas em toda saida",
       all(len(_s) == 3 for _s in (_s1, _s2, _s3, _s4)))
    ok("e NENHUM relato dela carrega o prompt",
       all("prompt" not in (_s[1] or {}) for _s in (_s1, _s2, _s3, _s4)))
    ok("e a base final volta separada, sempre",
       all(isinstance(_s[2], str) and _s[2] for _s in (_s1, _s2, _s3, _s4)))
    ok("o prompt sai do relato — ele nao viaja ate a galeria",
       "prompt" not in (_rt or {}))
    ok("e o que a peca precisa saber continua la",
       set(_rt or {}) >= {"ok", "rodadas", "erros"})

    conferir_peca = _real_peca

    # ── A REFACAO PIOR NAO PODE SUBSTITUIR A ORIGINAL ───────────────────
    #
    # Achado pela pergunta "que estrago isto pode causar?", e nao por um
    # defeito em producao — desta vez antes, e nao depois.
    #
    # `img = nova_img` era incondicional: a segunda peca virava a entregue
    # mesmo reprovada. Na revisao de TEXTO isso e razoavel, porque a refacao
    # recebe a copy certa e tende a melhorar. Aqui nao: o gerador pode
    # responder a "tire a alca a mais" tirando as duas, e eu entregaria a
    # pior das duas com um aviso dizendo que esta errada.
    _UM_PROBLEMA = {"aprovada": False, "problemas": ["texto cortado"],
                    "instrucao": "cartoes inteiros dentro do quadro"}
    _TRES_PROBLEMAS = {"aprovada": False,
                       "problemas": ["texto cortado", "alca a mais",
                                     "produto deformado"],
                       "instrucao": "refaca"}
    _geradas.clear()
    conferir_peca = _olho(_UM_PROBLEMA, _TRES_PROBLEMAS)
    _img, _rel = revisar_peca(b"original", "2 — Benefícios do produto",
                              fotos_ref=[b"f"], gerar=_gera,
                              prompt_base="BASE", rodadas=2)
    ok("refacao PIOR e descartada — fica a original",
       _img == b"original")
    ok("e o relato reporta os problemas da que FICOU",
       _rel["problemas"] == ["texto cortado"])

    _geradas.clear()
    conferir_peca = _olho(_TRES_PROBLEMAS, _UM_PROBLEMA)
    _img, _rel = revisar_peca(b"original", "2 — Benefícios do produto",
                              fotos_ref=[b"f"], gerar=_gera,
                              prompt_base="BASE", rodadas=2)
    ok("refacao MELHOR substitui — mesmo sem chegar a passar",
       _img == b"nova" and _rel["problemas"] == ["texto cortado"])

    conferir_peca = _olho("sem chave")
    _img, _rel = revisar_peca(b"x", "2 — Benefícios do produto",
                              fotos_ref=[b"f"], gerar=_gera)
    ok("falha de leitura da peca NAO vira aprovacao", _rel["ok"] is None)
    ok("e a tela avisa em voz alta",
       "NÃO foi conferida" in peca_em_aviso(_rel))

    # ── NADA SOBROU PARA PEDIR: NAO SE PAGA UMA GERACAO EM BRANCO ──────
    #
    # `sem_medida_de_quadro` tira a medida de quadro da critica, porque o
    # tamanho tem um dono so e a critica nao e ele. Quando a peca sai com
    # UM defeito e ele e justamente o enquadramento — o caso mais comum
    # nestas pecas — tudo e cortado, e a lista de correcao chegava VAZIA
    # ao gerador: "CORRECAO OBRIGATORIA: (nada). O que fazer diferente
    # agora: (nada)".
    #
    # Isso e uma geracao PAGA que nao pede coisa nenhuma, e o proprio dono
    # relatou o estrago de refazer a toa: a peca volta com o produto
    # trocado. A guarda de `instrucao` vazia ja existia, mas roda ANTES do
    # corte — ela nao via o que sobrava depois dele.
    #
    # Os problemas CRUS continuam indo para a tela: quem trabalha le "o
    # produto ocupa 30% do quadro" e decide. O que nao acontece e o sistema
    # gastar dinheiro para nao pedir nada.
    _geradas.clear()
    _SO_ENQUADRAMENTO = {
        "aprovada": False,
        "problemas": ["o produto ocupa 30% do quadro",
                      "deveria ocupar mais da metade do quadro"],
        "instrucao": "aumente o produto para ocupar 65% do quadro"}
    conferir_peca = _olho(_SO_ENQUADRAMENTO, _SO_ENQUADRAMENTO)
    _img, _rel = revisar_peca(b"original", "2 — Benefícios do produto",
                              fotos_ref=[b"f"], gerar=_gera,
                              prompt_base="BASE", rodadas=2)
    ok("defeito SO de enquadramento NAO paga uma geracao pedindo nada",
       not _geradas)
    ok("e a peca original e a que fica", _img == b"original")
    ok("e os problemas CRUS chegam a quem trabalha, com a medida e tudo",
       any("30%" in _p for _p in (_rel or {}).get("problemas") or []))

    conferir_peca = _olho(_CORTADA)
    _img, _rel = revisar_peca(b"x", "2 — Benefícios", fotos_ref=[b"f"],
                              gerar=None)
    ok("sem gerador, confere e reporta — nao trava",
       _rel["ok"] is False and _img == b"x")

    conferir_peca = _olho(_CORTADA)
    _img, _rel = revisar_peca(b"x", "2 — Benefícios", fotos_ref=[],
                              gerar=_gera)
    # ESTA GUARDA MUDOU DE PROPRIEDADE, E DE PROPOSITO.
    #
    # Ela exigia `_rel is None` — e `peca_em_aviso(None)` devolve "". Ou
    # seja: ela assinava embaixo do silencio. A peca sem foto chegava a
    # galeria com a mesma cara de uma peca conferida e aprovada, e "sem foto"
    # e justamente o caso em que o produto tem mais chance de sair errado.
    #
    # O que continua valendo: ela NAO RODA a conferencia (nao ha com o que
    # comparar, e julgar sem comparar e o alarme falso mais caro que existe) e
    # NAO GASTA geracao. O que mudou: ela devolve o veredito "nao conferida",
    # com o motivo, em vez de nada.
    ok("SEM FOTO DE REFERENCIA ela nao roda nem gasta geracao",
       _img == b"x" and _rel.get("rodadas") == 0 and not _rel.get("problemas"))
    ok("mas ela DIZ que nao conferiu, em vez de sair calada",
       _rel.get("ok") is None and "NÃO foi conferida" in peca_em_aviso(_rel))

    # O AVISO DIZ O DEFEITO, e nao "confira antes de publicar".
    ok("o aviso nomeia o problema encontrado",
       "alca a mais" in peca_em_aviso(
           {"ok": False, "rodadas": 2,
            "problemas": ["produto diferente das fotos: alca a mais"],
            "erro": ""}))
    conferir_peca = _real_peca

    # ── A pasta do Drive ─────────────────────────────────────────────────
    #
    # O estrago real: as imagens do "Globo Preto Portátil" iam ser salvas na
    # pasta da "Lixeira Aramada 12 litros Preto", porque a busca antiga
    # procurava por CADA uma das duas primeiras palavras do nome e as duas são
    # pretas. O código do globo estava preenchido na tela e não era usado.
    import sys as _sys_p, types as _types_p, re as _re_p
    _PASTAS = [
        {"id": "1", "name": "Lixeira Aramada 12 litros Preto - MS-LIXE-0911GN1"},
        {"id": "2", "name": "Globo Preto Portátil - MS-GLOB-0917EMD"},
        {"id": "3", "name": "Caneca Branca 300ml - MS-CANE-0101AB2"},
    ]

    class _DriveFalso(_types_p.ModuleType):
        @staticmethod
        def listar(q, diagnostico=None):
            fora = list(_PASTAS)
            _ex = _re_p.search(r"name='([^']*)'", q)
            if _ex:
                fora = [p for p in fora if p["name"] == _ex.group(1)]
            for _t in _re_p.findall(r"name contains '([^']*)'", q):
                fora = [p for p in fora if _t.lower() in p["name"].lower()]
            return fora

    _antigo_gdrive = _sys_p.modules.get("gdrive")
    _sys_p.modules["gdrive"] = _DriveFalso("gdrive")

    def _achou(nome, cod):
        _r = buscar_pasta_produto(nome, cod, "PAI")
        return _r[0][1] if _r else None

    ok("a pasta exata continua sendo a primeira resposta",
       _achou("Globo Preto Portátil", "MS-GLOB-0917EMD")
       == "Globo Preto Portátil - MS-GLOB-0917EMD")
    ok("nome escrito diferente acha pelo codigo, que e unico",
       _achou("Globo Portatil", "MS-GLOB-0917EMD")
       == "Globo Preto Portátil - MS-GLOB-0917EMD")
    ok("codigo que nao existe nao cai na pasta de outro produto",
       _achou("Globo Preto Portátil", "MS-XXXX-0000ZZ9") is None)
    ok("sem codigo, a cor sozinha nao acha pasta nenhuma",
       _achou("Preto", "") is None)
    ok("sem codigo, palavra que identifica acha",
       _achou("Caneca Branca 300ml", "")
       == "Caneca Branca 300ml - MS-CANE-0101AB2")
    ok("cor e medida nao identificam produto",
       _palavras_que_identificam("Globo Preto Portátil 12 litros") == ["Globo"])

    if _antigo_gdrive is None:
        _sys_p.modules.pop("gdrive", None)
    else:
        _sys_p.modules["gdrive"] = _antigo_gdrive

    # ── O tipo, depois de um Ajuste Fino ─────────────────────────────────
    ok("rotulo de ajuste nao e tipo, e vira Personalizado",
       tipo_para_gerar("Ajuste Fino — aumente o produto") == PERSONALIZADO)
    ok("mas o tipo que a imagem guarda manda",
       tipo_para_gerar({"tipo": "Ajuste Fino — x",
                        "tipo_base": "2 — Benefícios do produto"})
       == "2 — Benefícios do produto")
    ok("tipo de verdade passa inteiro",
       tipo_para_gerar("1 — Capa (fundo branco)").startswith("1 —")
       if "1 — Capa (fundo branco)" in PRESETS else True)
    ok("rotulo de ajuste deixa de cair no padrao de branding",
       modo_fundo_do_tipo("Ajuste Fino — aumente o produto") == "personalizado")

    # ── A trava do produto, no prompt do ajuste ──────────────────────────
    # PEDIDO QUE NAO FALA DE COR: a trava de cor vale inteira.
    _pf = montar_prompt_ajuste_fino("aumente o produto na cena", None, "prata")
    ok("o ajuste passou a levar a regra de fidelidade",
       "REGRA DE FIDELIDADE AO PRODUTO" in _pf)
    ok("e a trava de cor, que so a geracao tinha", "prata" in _pf.lower())
    ok("strass e textura estao nomeados na preservacao",
       "strass" in _pf.lower())

    # ── PIXEL REGERADO INVALIDA A APROVACAO ANTERIOR ───────────────────
    #
    # `ajustar_com_conferencia` aprova o ajuste e DEPOIS pode chamar
    # `revisar_texto`, que REDESENHA a peca para consertar o portugues. A
    # imagem que ia para a galeria era outra, e o juiz nunca a tinha visto.
    _pt_conf = []

    def _conf_2x(antes, depois, instrucao):
        _pt_conf.append(depois)
        if depois == b"ajustada":
            return {"feito": True, "o_que_saiu": "ok", "o_que_falta": "",
                    "colateral": "", "houve_colateral": False,
                    "produto_colateral": "",
                    "produto_alterado_fora_do_pedido": False}, ""
        # a imagem que a revisao de texto devolveu DESFEZ o ajuste
        return {"feito": False, "o_que_saiu": "", "o_que_falta": "o interior "
                "voltou a ser bege", "colateral": "", "houve_colateral": False,
                "produto_colateral": "",
                "produto_alterado_fora_do_pedido": False}, ""

    _a_conf, _a_bruto, _a_rev, _a_pode = (
        conferir_ajuste, _ajustar_bruto, revisar_texto, pode_ter_texto)
    globals()["conferir_ajuste"] = _conf_2x
    globals()["_ajustar_bruto"] = lambda *a, **k: (
        b"ajustada", {"ok": True, "tentativas": 1, "erro": "", "falta": "",
                      "saiu": "interior preto", "colateral": "",
                      "historico": []})
    globals()["pode_ter_texto"] = lambda *a, **k: True
    globals()["revisar_texto"] = lambda *a, **k: (
        b"redesenhada", {"ok": True, "rodadas": 2, "erro": "", "erros": ""}, "")
    try:
        _i_f, _r_f = ajustar_com_conferencia(b"original", "interior preto",
                                             tipo="2. Benefícios do produto")
        ok("a imagem FINAL, redesenhada pela revisao, tambem e julgada",
           b"redesenhada" in _pt_conf)
        ok("e se a revisao desfez o ajuste, nao sai como sucesso",
           _r_f.get("ok") is False)
        ok("e o que volta e a imagem que o juiz TINHA aprovado",
           _i_f == b"ajustada")
    finally:
        globals()["conferir_ajuste"] = _a_conf
        globals()["_ajustar_bruto"] = _a_bruto
        globals()["revisar_texto"] = _a_rev
        globals()["pode_ter_texto"] = _a_pode

    # ── A REFERENCIA ANEXADA CHEGA AO MOTOR NO REFAZER ─────────────────
    #
    # Ela so viajava na fila do AJUSTE. Quem anexava uma imagem de exemplo
    # e caia no refazer — por pedido proprio ou pelo roteador — perdia o
    # anexo: o motor recebia a frase e as fotos do produto, e a imagem que
    # a pessoa anexou para mostrar o que queria ficava no chat.
    #
    # Por AST, no caminho real: as duas chamadas de geracao do refazer usam
    # a lista que SOMA a referencia, e nao `_fotos_rf` cru.
    import ast as _ast_rr
    _fonte_cc = _insp_img.getsource(consumir_comandos_do_chat)
    _arv_cc = _ast_rr.parse(_fonte_cc.lstrip())
    ok("o refazer monta a lista com a referencia do pedido",
       "_ref_ped_rf = [b for b in (_c.get(\"referencia\") or []) if b]"
       in _fonte_cc
       and "_fotos_desta = _ref_ped_rf + list(_fotos_rf)" in _fonte_cc)
    # E NENHUMA das geracoes do refazer pode usar `_fotos_rf` direto: foi
    # exatamente isso que deixou o anexo para tras.
    _usos_crus = _fonte_cc.count("_fotos_rf, _r)") + _fonte_cc.count(
        "_fr=_fotos_rf")
    ok("nenhuma geracao do refazer usa as fotos sem a referencia",
       _usos_crus == 0)
    ok("e a referencia vem ANTES das fotos do produto — as fotos sao a "
       "trava de fidelidade, a referencia e o pedido",
       _fonte_cc.index("_ref_ped_rf + list(_fotos_rf)") > 0)

    # ── O LOG GRAVA O NOME DO PRODUTO DA GERAÇÃO QUE ESTÁ RODANDO ──────
    #
    # 02/10, Studio do dono: gerou a "Caneca Térmica Medieval 400Ml" pelo
    # código da descrição, 7 peças saíram, e o histórico de prompts dela veio
    # com 143 CARACTERES — só o cabeçalho.
    #
    # O contexto do log era marcado UMA vez por desenho da tela, no topo,
    # lendo `img_nome_produto` do `session_state`; e `definir_produto_da_sessao`
    # só escreve esse campo no FIM da geração. Na passada em que a geração
    # roda, o nome ainda não existe ali — a thread herda contexto vazio, o log
    # grava `produto = ""`, e o filtro por nome não acha nada.
    #
    # Era também a causa das seis peças "sem nome" no .txt dele.
    #
    # A guarda é por AST e mede a ORDEM, que é o que estava errado: a marcação
    # com `cfg` tem de vir ANTES da primeira Thread da geração.
    import ast as _ast_ctx
    _fonte_pg = _insp_img.getsource(pagina_imagem)
    ok("a geração marca o contexto do log com o nome do `cfg`",
       'produto=cfg.get("nome_produto", "")' in _fonte_pg)
    _i_marca = _fonte_pg.find('_li_ger.marcar_contexto(')
    _i_thread = _fonte_pg.find('_th_rf.Thread(')
    ok("e marca ANTES de abrir thread — é no nascimento dela que o "
       "contexto é capturado",
       _i_marca > 0 and (_i_thread < 0 or _i_marca < _i_thread))
    # A marcação do TOPO continua: ela cobre os caminhos que não passam pela
    # geração (ajuste fino avulso, refazer pelo chat).
    ok("a marcação do topo da tela continua existindo",
       _fonte_pg.count("marcar_contexto(") >= 2)
    # E o que o log grava sai do contexto, e não de uma leitura de tela que a
    # thread não consegue fazer.
    import log_imagem as _li_g
    _ctx_antes = _li_g.contexto_atual()
    try:
        _li_g.marcar_contexto(produto="Caneca Térmica Medieval 400Ml")
        ok("o contexto por thread guarda o produto marcado",
           _li_g.contexto_atual().get("produto")
           == "Caneca Térmica Medieval 400Ml")
        import threading as _th_g
        _visto = {}
        _alvo = _li_g.alvo_com_contexto(
            lambda: _visto.__setitem__("p",
                                       _li_g.contexto_atual().get("produto")))
        _t_g = _th_g.Thread(target=_alvo)
        _t_g.start(); _t_g.join()
        ok("e a THREAD enxerga o nome — é lá que o log grava",
           _visto.get("p") == "Caneca Térmica Medieval 400Ml")
    finally:
        _li_g.marcar_contexto(produto=_ctx_antes.get("produto", ""))

    # ── O PARAMETRO RECUSADO SAI, NOS CAMINHOS COM FOTO ────────────────
    #
    # 02/10: o print da conta do dono mostrou `gpt-image-2`, que REMOVEU o
    # `input_fidelity` — ele ja preserva por padrao, e a requisicao FALHA
    # quando o parametro vai junto.
    #
    # O laco que tira o parametro recusado existia so no caminho SEM fotos.
    # Os dois que mandam foto morriam no primeiro 400 e caiam no Gemini —
    # o motor sem preservacao de produto. Trocar para o modelo novo teria
    # devolvido exatamente o defeito que ele vem consertar.
    _fonte_ger = _insp_img.getsource(_chamar_openai_geracao)
    ok("o caminho Responses+tools tira o parametro recusado",
       "_qual = parametro_recusado(_e_par, list(_tools_cfg))" in _fonte_ger)
    ok("o caminho images.edit tira o parametro recusado",
       "_qual_e = parametro_recusado(_e_pe, list(_args_edit))" in _fonte_ger)
    ok("nenhum dos dois manda input_fidelity escrito fixo na chamada",
       'input_fidelity="high",\n                )' not in _fonte_ger)
    # E O DIAGNOSTICO DIZ O QUE FOI MANDADO, nao o que o codigo queria.
    #
    # A tela escrevia "input_fidelity=high" mesmo quando o parametro tinha
    # sido recusado — mentira sobre a capacidade, no campo que existe
    # justamente para dizer se a peca preservou o produto.
    ok("o diagnostico le o que sobrou, e nao um valor fixo",
       'diagnostico["input_fidelity"] = _tools_cfg.get(' in _fonte_ger
       and 'diagnostico["input_fidelity"] = _args_edit.get(' in _fonte_ger)
    ok("e quando o modelo nao aceita, ele DIZ isso em vez de mentir",
       _fonte_ger.count("não aceito por este modelo (ele já preserva)") == 2)
    # O modelo da conta do dono entra na ordem de preferencia.
    ok("gpt-image-2 e conhecido, e vem antes do gpt-image-1",
       "gpt-image-2" in MODELOS_IMAGEM_CONHECIDOS
       and (MODELOS_IMAGEM_CONHECIDOS.index("gpt-image-2")
            < MODELOS_IMAGEM_CONHECIDOS.index("gpt-image-1")))
    ok("a descoberta acha o gpt-image-2 numa conta que so tem ele",
       modelos_de_imagem_da_conta(
           type("C", (), {"models": type("M", (), {
               "list": staticmethod(lambda: [
                   type("X", (), {"id": "gpt-4o"})(),
                   type("X", (), {"id": "gpt-image-2"})()])})()})()
       ) == ["gpt-image-2"])

    # ── O ROTEADOR AJUSTAR x REFAZER, MEDIDO NOS PEDIDOS REAIS ─────────
    #
    # 01/10. "mudar a quantidade de divisorias para 6" foi parar no ajuste
    # fino, que e edicao cirurgica e nao recompoe geometria: ele devolveu a
    # imagem INTACTA, sem erro nenhum, quatro rodadas seguidas.
    #
    # Os casos abaixo sao os da conversa daquele dia, copiados dela — e nao
    # frases que eu inventei para o teste passar.
    for _ped_r, _esp_r in (
            ("mudar a cor interior do produto para a cor preta", "ajustar"),
            ("mudar a cor interio do produto para a cor preta", "ajustar"),
            ("mudar a quantidade de divisorias para 6 divisorias", "refazer"),
            ("na imagem 3 mudar a cor interior para a cor preta, e mudar a "
             "quantidade de divisorias para 6 divisorias", "refazer"),
            ("colocar 6 divisorias", "refazer"),
            ("aumente o produto em 20%", "ajustar"),
            ("tirar a faixa branca da borda", "ajustar"),
            ("deixar o fundo mais claro", "ajustar"),
            ("corrigir o texto do primeiro cartao", "ajustar"),
            ("uma pessoa entregando o produto para outra", "refazer"),
            ("mudar a caixa fechada para aberta mostrando seis nichos",
             "refazer")):
        ok(f"roteador: «{_ped_r[:46]}» -> {_esp_r}",
           classificar_edicao(_ped_r)[0] == _esp_r)
    ok("quando roteia para refazer, o motivo nao vem vazio",
       bool(classificar_edicao("colocar 6 divisorias")[1]))
    ok("e quando fica no ajuste, nao inventa motivo",
       classificar_edicao("deixar o fundo mais claro")[1] == "")
    # ELE SO ESCALA: a duvida do sistema nao revoga a certeza de quem pediu.
    ok("nenhum pedido de recomposicao e rebaixado para ajuste",
       classificar_edicao("6 nichos")[0] == "refazer")
    # Pedido vazio nao derruba e nao vira refazer por engano.
    ok("pedido vazio nao derruba o roteador",
       classificar_edicao("")[0] == "ajustar"
       and classificar_edicao(None)[0] == "ajustar")

    # ── POSICAO DE CARTAO NAO E ANGULO DE CAMERA ───────────────────────
    #
    # ACHADO EM PRODUCAO, 05/10, e custou uma geracao MAIS a imagem que ja
    # estava certa. O dono pediu "apenas troque a palavra «Metal» para
    # «inox»". O chat, para ser preciso, escreveu ONDE a palavra estava: "o
    # cartao DE BAIXO a esquerda". A regex de angulo casou "de baixo",
    # escalou para REFAZER, e a refacao do zero devolveu uma caneca com
    # DUAS alcas.
    #
    # Errar para o lado de refazer "custa uma geracao" — e a nota de cima
    # diz isso. Mas quando a imagem anterior ESTAVA CERTA, custa as duas.
    for _ped_c, _esp_c in (
            # o caso real, letra por letra
            ('Na 5 é o cartão de baixo à esquerda: "MATERIAL / metal e '
             'resina". Trocar metal por inox', "ajustar"),
            ("troque a palavra metal por inox no cartão lateral", "ajustar"),
            ("o bloco de cima diz PROFUNDITUDE, corrija", "ajustar"),
            ("corrija o texto do selo de baixo", "ajustar"),
            # e o que a regra existe para pegar continua pegando
            ("fotografe o produto de baixo", "refazer"),
            ("mostre a caneca de costas", "refazer"),
            ("mostre a lateral do produto", "refazer"),
            ("mudar a caixa fechada para aberta", "refazer")):
        ok(f"posicao x angulo: «{_ped_c[:42]}» -> {_esp_c}",
           classificar_edicao(_ped_c)[0] == _esp_c)

    # ── A TRAVA DE COR NAO PODE PROIBIR O QUE O PEDIDO MANDOU ───────────
    #
    # 01/10: "mudar a cor interior do produto para a cor preta". O prompt
    # levava `_trava_cor_produto`, que diz "e PROIBIDO recolorir o produto",
    # e um cabecalho "O PRODUTO NAO E PARTE DO AJUSTE — regra acima de
    # qualquer instrucao". Duas vozes proibindo o pedido, dentro do mesmo
    # texto que dizia "a MODIFICACAO SOLICITADA tem prioridade sobre TODAS
    # as regras deste texto". Tres autoridades, cada uma acima da outra.
    _pf_cor = montar_prompt_ajuste_fino(
        "mudar a cor interior do produto para preta", None, "bege")
    ok("pedido de cor: o prompt NAO proibe recolorir o produto",
       "É PROIBIDO recolorir" not in _pf_cor)
    ok("pedido de cor: a trava vira parcial, e diz o que ainda nao muda",
       "PARCIAL NESTE AJUSTE" in _pf_cor)
    ok("o cabecalho 'o produto nao e parte do ajuste' saiu de vez",
       "NÃO É PARTE DO AJUSTE" not in _pf_cor
       and "NÃO É PARTE DO AJUSTE" not in _pf)
    ok("e a preservacao aparece como COMPLEMENTO do pedido",
       "COMPLEMENTO DO PEDIDO" in _pf_cor)
    ok("pedido de quantidade de pecas tem exemplo proprio no prompt",
       "QUANTIDADE de peças" in _pf_cor)
    # ── O PROMPT NUNCA MANDA DESISTIR ───────────────────────────────────
    #
    # Ele ja teve a linha "se a modificacao pedida so puder ser feita
    # alterando o produto, NAO a faca: devolva a imagem como esta". Devolver
    # a imagem intacta e o unico desfecho que NAO resolve nada, e era
    # exatamente o que o dono via: cinco pedidos, cinco imagens iguais.
    #
    # Esta era a unica das 33 guardas deste modulo que continuava fraca
    # depois do codigo de saida — a mutacao reintroduzia a frase e nada
    # reprovava.
    for _nome_pf, _txt_pf in (("sem cor", _pf), ("com cor", _pf_cor)):
        ok(f"o prompt do ajuste ({_nome_pf}) nao manda devolver a imagem "
           f"como esta",
           "devolva a imagem como está" not in _txt_pf
           and "NÃO a faça" not in _txt_pf)
        ok(f"e diz, ao contrario, que fazer o pedido nao e opcional "
           f"({_nome_pf})",
           "NÃO É OPCIONAL" in _txt_pf)
    # A pergunta "o pedido fala de cor?" e medida nos dois sentidos.
    ok("'interior preto' fala de cor", _pedido_fala_de_cor("interior preto"))
    ok("'6 divisorias' nao fala de cor",
       not _pedido_fala_de_cor("mudar a quantidade de divisorias para 6"))

    # ── Pedido atendido com produto estragado NAO e sucesso ──────────────
    #
    # O caso real: a colaboradora pediu melhor cor, o ajuste melhorou a cor E
    # tirou o strass do corpo do urso prata. O veredito dizia isso, e o codigo
    # entregava assim mesmo com "atualizada".
    _chamadas = []

    def _conf_falsa(antes, depois, instrucao):
        _chamadas.append(instrucao)
        if len(_chamadas) == 1:
            return {"feito": True, "o_que_saiu": "cor melhorou",
                    "o_que_falta": "", "colateral": "o strass do corpo sumiu",
                    "houve_colateral": True,
                    "produto_colateral": "o strass do corpo sumiu",
                    "produto_alterado_fora_do_pedido": True}, ""
        return {"feito": True, "o_que_saiu": "cor melhorou",
                "o_que_falta": "", "colateral": "", "houve_colateral": False,
                "produto_colateral": "",
                "produto_alterado_fora_do_pedido": False}, ""

    # O gerador guarda o prompt: e nele que a segunda tentativa tem de levar o
    # estrago por escrito. A conferencia recebe sempre a instrucao ORIGINAL,
    # de proposito — ela julga o que a pessoa pediu, e nao o que o codigo
    # acrescentou.
    _prompts = []

    def _ger_ok(prompt, *a, **k):
        _prompts.append(prompt)
        return b"nova", None

    _antes_conf, _antes_ger = conferir_ajuste, gerar_imagem_ia
    globals()["conferir_ajuste"] = _conf_falsa
    globals()["gerar_imagem_ia"] = _ger_ok
    _img, _rel = _ajustar_bruto(b"original", "melhore a cor dourada",
                                tentativas=2)
    ok("produto estragado nao volta como sucesso na primeira",
       len(_chamadas) == 2)
    ok("e a segunda tentativa leva o estrago por escrito, no prompt",
       len(_prompts) == 2 and "strass" in _prompts[1].lower())
    ok("com o produto intacto, a segunda e aceita", _rel["ok"] is True)

    # E quando nem a ultima tentativa poupa o produto: volta a ORIGINAL.
    _chamadas.clear()
    globals()["conferir_ajuste"] = lambda a, d, i: (
        _chamadas.append(i) or {"feito": True, "o_que_saiu": "cor melhorou",
                                "o_que_falta": "",
                                "colateral": "o strass do corpo sumiu",
                                "houve_colateral": True,
                                "produto_colateral": "o strass do corpo sumiu",
                                "produto_alterado_fora_do_pedido": True}, "")
    _img2, _rel2 = _ajustar_bruto(b"original", "melhore a cor", tentativas=2)
    ok("produto estragado ate o fim devolve a imagem ORIGINAL",
       _img2 == b"original")
    ok("e o relato diz que nao entregou, em vez de anunciar sucesso",
       _rel2["ok"] is False
       and _rel2.get("produto_alterado_fora_do_pedido") is True)

    # ── O CASO QUE TRAVOU O DONO EM 01/10, E QUE FALTAVA MEDIR ──────────
    #
    # "mudar a cor interior do produto para a cor preta". O produto MUDA —
    # e muda porque foi isso que pediram. O juiz novo responde
    # `produto_alterado_fora_do_pedido = False`, e o ajuste tem de ser
    # ACEITO na primeira. Antes disto o sistema revertia, cinco pedidos
    # seguidos, dizendo "toda vez o produto mudava junto".
    _ch_ped = []
    globals()["conferir_ajuste"] = lambda a, d, i: (
        _ch_ped.append(i) or {"feito": True,
                              "o_que_saiu": "o interior ficou preto",
                              "o_que_falta": "", "colateral": "",
                              "houve_colateral": False,
                              "produto_colateral": "",
                              "produto_alterado_fora_do_pedido": False}, "")
    _img3, _rel3 = _ajustar_bruto(
        b"original", "mudar a cor interior do produto para preta",
        tentativas=2)
    ok("mudar o PRODUTO porque foi pedido e sucesso, na primeira",
       _rel3["ok"] is True and len(_ch_ped) == 1 and _img3 == b"nova")
    ok("e a tela nao diz mais que o produto mudou junto",
       "produto errado" not in relato_em_texto(3, _rel3))

    # E O COLATERAL FORA DO PRODUTO tambem reprova — cenario, fundo, texto.
    _ch_col = []
    globals()["conferir_ajuste"] = lambda a, d, i: (
        _ch_col.append(i) or {"feito": True, "o_que_saiu": "interior preto",
                              "o_que_falta": "",
                              "colateral": "o criado-mudo virou uma mesa",
                              "houve_colateral": True,
                              "produto_colateral": "",
                              "produto_alterado_fora_do_pedido": False}, "")
    _img4, _rel4 = _ajustar_bruto(b"original", "interior preto", tentativas=2)
    ok("colateral fora do produto tambem impede o sucesso",
       _rel4["ok"] is False and _img4 == b"original")
    ok("e a segunda tentativa nomeia o colateral no prompt",
       len(_ch_col) == 2 and "criado-mudo" in _prompts[-1].lower())
    globals()["conferir_ajuste"] = _antes_conf
    globals()["gerar_imagem_ia"] = _antes_ger

    # ── Os motores, ditos antes de gastar ────────────────────────────────
    # Sem tocar em `st.secrets`: sem arquivo de secrets ele LEVANTA, e foi essa
    # mesma armadilha que ja tinha derrubado `_chave_anthropic`.
    _env_antes = {k: os.environ.get(k) for k in ("OPENAI_API_KEY", "GEMINI_API_KEY")}

    def _com_chaves(openai, gemini):
        for k, v in (("OPENAI_API_KEY", openai), ("GEMINI_API_KEY", gemini)):
            if v:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        globals()["_get_openai_api_key"] = lambda: os.environ.get("OPENAI_API_KEY", "")
        return motores_de_imagem()

    _ok_m, _av_m = _com_chaves("", "g")
    ok("sem a chave do primario, a tela avisa ANTES de gerar",
       _ok_m is False and "primário" in _av_m)
    ok("e explica por que o credito do reserva acaba", "reserva" in _av_m)
    _ok_m, _av_m = _com_chaves("o", "")
    ok("sem o reserva, avisa sem bloquear", _ok_m is True and _av_m)
    _ok_m, _av_m = _com_chaves("", "")
    ok("sem nenhum dos dois, e erro", _ok_m is False and "Nenhum motor" in _av_m)
    _ok_m, _av_m = _com_chaves("o", "g")
    ok("com os dois, a tela nao avisa a toa", _ok_m is True and _av_m == "")

    # ── "Acabou o credito" reconhecido em qualquer codigo ────────────────────
    # O 402 do saldo pre-pago zerado passava pelo `return resp, None` como se
    # fosse resposta boa, e chegava a tela como "Erro HTTP 402".
    ok("402 e falta de credito, seja qual for o texto",
       _resposta_sem_credito(402) is True)
    ok("e a mensagem do Google e reconhecida pelo texto tambem",
       _resposta_sem_credito(402, "Your prepayment credits are depleted") is True)
    ok("429 com RESOURCE_EXHAUSTED e cota",
       _resposta_sem_credito(429, "rate", "RESOURCE_EXHAUSTED") is True)
    ok("429 com 'quota' no texto e cota",
       _resposta_sem_credito(429, "You exceeded your current quota") is True)
    ok("429 sem nada disso continua sendo lentidao — vale repetir",
       _resposta_sem_credito(429, "Too many requests, slow down") is False)
    ok("200 limpo nunca e falta de credito",
       _resposta_sem_credito(200, "tudo certo") is False)
    ok("403 de faturamento tambem e credito",
       _resposta_sem_credito(403, "Billing account not configured") is True)

    # ── A saida de erro carrega SEMPRE os dois motores ───────────────────────
    # Eram seis `return None, ...` e so dois levavam `erro_primario`: a tela
    # mostrou oito vezes o erro do RESERVA sem dizer nada do primario.
    import ast as _ast_saida
    _fonte = open(__file__, encoding="utf-8").read()
    _arv = _ast_saida.parse(_fonte)
    _ger = next(n for n in _ast_saida.walk(_arv)
                if isinstance(n, _ast_saida.FunctionDef) and n.name == "gerar_imagem_ia")
    _falha_def = next((n for n in _ast_saida.walk(_ger)
                       if isinstance(n, _ast_saida.FunctionDef) and n.name == "_falha"), None)
    ok("gerar_imagem_ia tem a saida unica de erro", _falha_def is not None)

    # Nenhum `return None, <texto>` solto sobrou no corpo da geracao — se um
    # voltar, ele volta escondendo o motor primario de novo.
    _soltos = []
    _dentro_da_falha = {id(_x) for _x in _ast_saida.walk(_falha_def)} if _falha_def else set()
    # A SAIDA DE `so_montar` NAO E SAIDA DE ERRO, E POR ISSO E ISENTA — MAS
    # NOMINALMENTE, E NAO AFROUXANDO A REGRA.
    #
    # Ela devolve (None, "") depois de montar o prompt e antes de chamar motor
    # nenhum: e o caminho que a tela do plano usa para mostrar o texto sem
    # gastar geracao. Isentar "qualquer return que volte None" abriria de novo
    # a porta que esta conferencia fechou — os seis `return None, <erro>` que
    # escondiam o motor primario. Entao a isencao e so a de dentro do
    # `if so_montar:`.
    for _if in _ast_saida.walk(_ger):
        if (isinstance(_if, _ast_saida.If)
                and isinstance(_if.test, _ast_saida.Name)
                and _if.test.id == "so_montar"):
            _dentro_da_falha |= {id(_x) for _x in _ast_saida.walk(_if)}
    for _n in _ast_saida.walk(_ger):
        if not isinstance(_n, _ast_saida.Return) or id(_n) in _dentro_da_falha:
            continue
        _v = _n.value
        if (isinstance(_v, _ast_saida.Tuple) and len(_v.elts) == 2
                and isinstance(_v.elts[0], _ast_saida.Constant)
                and _v.elts[0].value is None):
            _soltos.append(getattr(_n, "lineno", "?"))
    ok("nenhum return de erro escapa da saida unica (linhas: %s)" % _soltos,
       _soltos == [])

    # O texto montado nomeia os DOIS motores, com e sem erro do primario.
    def _falha_simulada(erro_primario, motivo, cota=False):
        if cota:
            motivo = ("⛔ Cota ou créditos da GEMINI_API_KEY esgotados. Crie uma nova "
                      "chave em aistudio.google.com/apikey vinculada ao projeto GCP e "
                      f"atualize GEMINI_API_KEY no Railway. Detalhe: {motivo[:200]}")
        if erro_primario:
            return None, (f"{motivo}\n\n**E o motor primário falhou antes:** "
                          f"{erro_primario}")
        return None, (f"{motivo}\n\nO motor primário de imagem também não "
                      "entregou nesta tentativa.")

    _, _t = _falha_simulada("OpenAI: sem saldo", "Erro HTTP 402")
    ok("a mensagem do reserva leva junto o erro do primario",
       "motor primário falhou antes" in _t and "sem saldo" in _t)
    _, _t = _falha_simulada("", "Erro HTTP 402")
    ok("e sem erro do primario ela ainda fala dele",
       "motor primário" in _t)

    # ── A OpenAI nao engole mais o motivo terminal ───────────────────────────
    ok("saldo da OpenAI e terminal — nao adianta tentar os outros endpoints",
       _erro_openai_terminal(Exception("Error code: 429 - insufficient_quota")) != "")
    ok("chave invalida tambem",
       _erro_openai_terminal(Exception("invalid_api_key")) != "")
    ok("erro passageiro nao e terminal — segue para a proxima tentativa",
       _erro_openai_terminal(Exception("Connection reset by peer")) == "")

    # ── O MODELO DE IMAGEM, E UMA AFIRMACAO MINHA QUE ERA FALSA ──────────
    #
    # ESTE BLOCO DIZIA: "`gpt-image-2` nao existe". E a guarda abaixo exigia
    # que o nome NAO estivesse em lugar nenhum.
    #
    # Era mentira, e ela ficou escrita aqui como se fosse fato medido. Em
    # 02/10 o dono mandou o print do painel da conta dele: `gpt-image-2`
    # esta la, com 100.000 TPM e 5 imagens por minuto. A guarda nao media o
    # sistema — media a minha crenca, e TRAVAVA a correcao: enquanto ela
    # existisse, ninguem podia pôr na lista o unico modelo bom que a conta
    # tem.
    #
    # O que de fato aconteceu em 30/09 foi outra coisa: o nome configurado
    # era `gpt-image-2.5-sunburst`, que a conta NAO tem. Dava 404, o
    # primario nunca gerava, e tudo caia no Gemini — que nao aceita `size`
    # nem preserva o produto. Dai "imagens extremamente pequenas" e "fotos
    # com margens laterais" na mesma tela. O defeito era o nome errado, e
    # nao a existencia do `gpt-image-2`.
    #
    # Guarda escrita em cima de uma crenca minha e pior que nenhuma: ela
    # defende o erro.
    ok("o padrao continua sendo um nome da familia certa",
       MODELO_IMAGEM_PADRAO.startswith("gpt-image-"))
    ok("e `gpt-image-2`, que a conta do dono TEM, e reconhecido",
       "gpt-image-2" in MODELOS_IMAGEM_CONHECIDOS)

    _env_mod = os.environ.get("OPENAI_MODELO_IMAGEM")
    _desc_antes = _MODELO_DESCOBERTO["nome"]
    _MODELO_DESCOBERTO["nome"] = None
    os.environ.pop("OPENAI_MODELO_IMAGEM", None)
    ok("sem nada configurado, vale o padrao",
       modelo_de_imagem() == MODELO_IMAGEM_PADRAO)

    # O descoberto em execucao vale mais que o padrao: e ele que existe DE FATO
    # na conta, e o padrao e so o palpite bom.
    _MODELO_DESCOBERTO["nome"] = "gpt-image-9-novo"
    ok("o descoberto na conta manda no padrao",
       modelo_de_imagem() == "gpt-image-9-novo")

    # E a variavel do Railway manda em todos: trocar de modelo nao pode ser
    # deploy.
    os.environ["OPENAI_MODELO_IMAGEM"] = "gpt-image-2.5-flare"
    ok("e a variavel do Railway manda em todos",
       modelo_de_imagem() == "gpt-image-2.5-flare")

    # ══ MAS A VARIAVEL NAO MANDA DEPOIS DE PROVADA ERRADA ═══════════════
    #
    # Dono, 29/09: "ja trouxe esse problema aqui umas 10 vezes e voce nao
    # resolve". Ele tem razao, e o motivo estava nesta linha.
    #
    # `OPENAI_MODELO_IMAGEM` estava com "gpt-image-2.5-sunburst", que NAO
    # existe naquela conta. O Studio chamava, tomava 404, redescobria um
    # modelo bom, usava UMA vez — e na chamada seguinte lia a variavel de
    # novo e voltava ao nome inexistente. Toda geracao recomecava errada,
    # para sempre, e a unica saida era alguem lembrar de editar a variavel.
    #
    # Isso e a Regra 5 do CLAUDE.md: o que faltava nao era o dono configurar
    # certo — era o sistema parar de obedecer a uma configuracao que ele JA
    # SABIA estar errada.
    _inv_antes = set(_MODELO_INVALIDO)
    try:
        _MODELO_INVALIDO.clear()
        _MODELO_DESCOBERTO["nome"] = None
        os.environ["OPENAI_MODELO_IMAGEM"] = "gpt-image-que-nao-existe"
        ok("antes de provar, a variavel manda — e tem de mandar",
           modelo_de_imagem() == "gpt-image-que-nao-existe")

        # A conta respondeu "esse modelo nao existe". A partir daqui a
        # variavel perdeu a autoridade DELA, e so dela.
        marcar_modelo_invalido("gpt-image-que-nao-existe")
        _MODELO_DESCOBERTO["nome"] = "gpt-image-9-novo"
        ok("depois de provada errada, ela para de mandar",
           modelo_de_imagem() == "gpt-image-9-novo")
        ok("e a geracao seguinte NAO volta ao nome inexistente",
           modelo_de_imagem() != "gpt-image-que-nao-existe")

        # SEM DESCOBERTO, cai no padrao — nunca no nome provado errado.
        _MODELO_DESCOBERTO["nome"] = None
        ok("sem descoberto, cai no padrao e nao no invalido",
           modelo_de_imagem() == MODELO_IMAGEM_PADRAO)

        # E O AVISO EXISTE, para o dono poder arrumar a variavel quando
        # quiser. Recuperar calado esconderia a configuracao errada para
        # sempre — o sistema tem de funcionar E dizer o que esta torto.
        ok("o Studio sabe dizer que a variavel esta errada",
           bool(aviso_de_modelo_invalido()))
        ok("e o aviso nomeia o modelo que nao existe",
           "gpt-image-que-nao-existe" in aviso_de_modelo_invalido())

        # UMA VARIAVEL ERRADA NAO DERRUBA UMA CERTA.
        _MODELO_DESCOBERTO["nome"] = None
        os.environ["OPENAI_MODELO_IMAGEM"] = "gpt-image-2.5-flare"
        ok("outro modelo configurado continua mandando",
           modelo_de_imagem() == "gpt-image-2.5-flare")
        ok("e sem invalido nenhum nao ha aviso",
           not aviso_de_modelo_invalido() if not _MODELO_INVALIDO else True)
        # OS DOIS CAMINHOS MARCAM — por AST, e nao por leitura minha.
        #
        # `_chamar_openai_geracao` tenta DOIS endpoints, e cada um tem o seu
        # proprio `if modelo nao existe`. Marcar so no primeiro deixaria o
        # nome invalido voltando pelo segundo: a Forma 1 desta base, corrigir
        # onde o problema apareceu e nao onde a regra alcanca.
        import ast as _ast_mi, inspect as _insp_mi
        _arv_mi = _ast_mi.parse(
            _insp_mi.getsource(_chamar_openai_geracao).lstrip())
        _marcou = sum(
            1 for _x in _ast_mi.walk(_arv_mi)
            if isinstance(_x, _ast_mi.Call)
            and (getattr(_x.func, "id", "") or getattr(_x.func, "attr", ""))
            == "marcar_modelo_invalido")
        _redesc = sum(
            1 for _x in _ast_mi.walk(_arv_mi)
            if isinstance(_x, _ast_mi.Call)
            and (getattr(_x.func, "id", "") or getattr(_x.func, "attr", ""))
            == "redescobrir_modelo_de_imagem")
        ok(f"todo caminho que redescobre tambem marca o invalido "
           f"({_marcou} marca / {_redesc} redescobre)", _marcou >= _redesc >= 2)

        # E A TELA DIZ, por AST. Recuperar calado esconde a configuracao
        # errada para sempre. O nome sobrevive nos comentarios que explicam
        # por que ele existe, entao a pergunta se faz na CHAMADA.
        _arv_tela = _ast_mi.parse(_ast_mi.unparse(_ast_mi.parse(
            _insp_mi.getsource(pagina_imagem).lstrip())))
        ok("a tela avisa quando a variavel aponta para modelo inexistente",
           any(isinstance(_x, _ast_mi.Call)
               and (getattr(_x.func, "id", "")
                    or getattr(_x.func, "attr", ""))
               == "aviso_de_modelo_invalido"
               for _x in _ast_mi.walk(_arv_tela)))
    finally:
        _MODELO_INVALIDO.clear()
        _MODELO_INVALIDO.update(_inv_antes)

    os.environ.pop("OPENAI_MODELO_IMAGEM", None)
    _MODELO_DESCOBERTO["nome"] = _desc_antes
    if _env_mod:
        os.environ["OPENAI_MODELO_IMAGEM"] = _env_mod

    # Reconhecer "esse modelo nao existe" e o que dispara a redescoberta. Se
    # esta funcao errar, o Studio volta a insistir num nome inventado.
    ok("404 de modelo inexistente e reconhecido",
       _modelo_nao_existe(Exception(
           "Error code: 404 - {'error': {'message': \"The model "
           "'gpt-image-2' does not exist or you do not have access to it.\", "
           "'code': 'model_not_found'}}")) is True)
    ok("pelo codigo tambem", _modelo_nao_existe(Exception("model_not_found")))
    ok("falta de saldo NAO e modelo inexistente",
       _modelo_nao_existe(Exception("insufficient_quota")) is False)
    ok("nem queda de rede",
       _modelo_nao_existe(Exception("Connection reset by peer")) is False)

    # A lista da conta poe os conhecidos na frente, na ordem de capacidade —
    # e nao descarta o que nao conhece, senao um modelo novo ficaria invisivel.
    class _FakeModelos:
        def list(self):
            class _M:
                def __init__(self, i):
                    self.id = i
            return [_M("gpt-4o"), _M("gpt-image-2.5-flare"),
                    _M("gpt-image-3-futuro"), _M("gpt-image-2.5-sunburst"),
                    _M("whisper-1")]

    class _FakeCliente:
        models = _FakeModelos()

    # ── O TEXTO DA PECA NAO PODE SER DECEPADO PELO ENQUADRAMENTO ────────
    #
    # Dono, 30/09: "Imagem 2 e imagem 5 com texto cortando".
    #
    # A CADEIA INTEIRA, e nao a chamada: o motor devolve uma peca RETANGULAR
    # de marketing (cenario ate as bordas, painel de texto na esquerda), e o
    # que se mede e se o painel sobrevive na imagem ENTREGUE. Conferir que a
    # chamada leva `tem_texto=` nao mede nada — foi assim que a guarda do
    # material passou verde com o campo sumindo.
    import io as _io_tx, random as _rnd_tx
    from PIL import Image as _Im_tx, ImageDraw as _Dr_tx

    def _peca_retangular_com_texto():
        _rnd_tx.seed(7)
        im = _Im_tx.new("RGB", (1400, 1000), (255, 255, 255))
        d = _Dr_tx.Draw(im)
        for _ in range(9000):                       # cenario ate a borda
            d.point((_rnd_tx.randint(0, 1399), _rnd_tx.randint(0, 999)),
                    fill=(_rnd_tx.randint(150, 230),) * 3)
        d.ellipse((800, 400, 1250, 850), fill=(20, 120, 40))   # produto
        d.rectangle((30, 120, 430, 880), fill=(180, 30, 30))   # PAINEL DE TEXTO
        # A PRIMEIRA LETRA DO TITULO, marcada em azul.
        #
        # Sem esta marca a guarda era fraca: o corte comeca em x=200 e o
        # painel vai de 30 a 430, entao SOBRA metade dele — e "achei
        # vermelho" continuava verdadeiro com o titulo decepado, que e
        # exatamente o defeito. O dono viu 'TE DE MEDIDA' no lugar de
        # 'CORTE DE MEDIDA': o que se perde e o COMECO da linha.
        d.rectangle((35, 200, 95, 320), fill=(30, 60, 220))
        _b = _io_tx.BytesIO()
        im.save(_b, format="PNG")
        return _b.getvalue()

    def _tem_painel(dados):
        """O COMECO do titulo continua na peca? (a marca azul)"""
        _p = _Im_tx.open(_io_tx.BytesIO(dados)).convert("RGB")
        return any(_p.getpixel((x, y))[2] > 150
                   and _p.getpixel((x, y))[0] < 90
                   and _p.getpixel((x, y))[1] < 110
                   for y in range(0, _p.size[1], 3)
                   for x in range(0, _p.size[0], 3))

    _orig_tx = (_chamar_openai_geracao, _chamar_gemini_geracao_texto,
                _descricao_do_produto_cacheada, _get_openai_api_key)
    try:
        import base64 as _b64_tx

        class _RespFalsa:
            status_code = 200

            @staticmethod
            def json():
                return {"candidates": [{"content": {"parts": [
                    {"inlineData": {"data": _b64_tx.b64encode(
                        _peca_retangular_com_texto()).decode()}}]}}]}

        globals()["_chamar_openai_geracao"] = lambda *a, **k: (None, "desligado")
        globals()["_chamar_gemini_geracao_texto"] = \
            lambda *a, **k: (_RespFalsa(), None)
        globals()["_descricao_do_produto_cacheada"] = \
            lambda *a, **k: ("desc", "lay")
        globals()["_get_openai_api_key"] = lambda: ""
        _saida_mk, _err_mk = gerar_imagem_ia(
            "MS_FUNDO: padrao\nTIPO DE IMAGEM: 2 — Benefícios do produto\n",
            [b"foto"], tipo="2 — Benefícios do produto")
        ok("peca COM texto: o painel lateral sobrevive ao enquadramento",
           bool(_saida_mk) and _tem_painel(_saida_mk))
    finally:
        (globals()["_chamar_openai_geracao"],
         globals()["_chamar_gemini_geracao_texto"],
         globals()["_descricao_do_produto_cacheada"],
         globals()["_get_openai_api_key"]) = _orig_tx

    _achados = modelos_de_imagem_da_conta(_FakeCliente())
    ok("so os modelos de imagem entram",
       all("image" in m or "dall-e" in m for m in _achados))

    # ── A CONTA QUE NAO TEM NENHUM `gpt-image` ───────────────────────────
    #
    # 30/09, producao: a tela disse "«gpt-image-2.5-sunburst» nao existe
    # nesta conta da OpenAI, e nao achei nenhum outro". A redescoberta RODOU
    # e voltou vazia — entao TODAS as oito pecas sairam do motor reserva,
    # que nao aceita `size` nem `input_fidelity`. Dai o texto cortado, o
    # produto encolhido e a peca 6 com um produto que nao era o do cliente.
    #
    # A causa era o filtro exigir "gpt" E "image" no nome. `dall-e-3` e
    # modelo de imagem da OpenAI e nao tem "gpt" no nome: a conta tinha um
    # motor e o Studio nao enxergava.
    #
    # E a conta falsa desta propria guarda so tinha `gpt-image-*` — ela
    # media a familia feliz. Dado de teste saido da minha cabeca, de novo.
    class _ContaSoDallE:
        class models:
            @staticmethod
            def list():
                class _M:
                    def __init__(self, i):
                        self.id = i
                return [_M("gpt-4o"), _M("dall-e-3"), _M("dall-e-2"),
                        _M("whisper-1"), _M("text-embedding-3-small")]

    _so_dalle = modelos_de_imagem_da_conta(_ContaSoDallE())
    ok("conta que so tem dall-e NAO fica sem motor de imagem", bool(_so_dalle))
    ok("e o dall-e-3 vem antes do dall-e-2",
       _so_dalle[:2] == ["dall-e-3", "dall-e-2"] if len(_so_dalle) > 1 else True)
    ok("e nenhum modelo que NAO e de imagem entra",
       not any(m in _so_dalle for m in ("gpt-4o", "whisper-1",
                                        "text-embedding-3-small")))
    ok("o mais capaz vem primeiro",
       _achados[0] == "gpt-image-2.5-sunburst")
    ok("e o modelo novo, que o codigo nao conhece, NAO fica invisivel",
       "gpt-image-3-futuro" in _achados)
    ok("conta que nao responde nao derruba nada",
       modelos_de_imagem_da_conta(object()) == [])

    # ── A DIRECAO DE ARTE DEIXOU DE SER AZUL FIXO ────────────────────────
    #
    # "Fundo: #E8EEF5" e "NAO use marrom, laranja, vermelho ou verde" em toda
    # peca de todo produto. Era essa regra que proibia a cena da caixa de
    # relogios — nogueira e dourado sao marrom e laranja — e achatava os tres
    # produtos de referencia na mesma cara azul.
    ok("a paleta fixa saiu do padrao visual",
       "#E8EEF5" not in PADRAO_VISUAL and "#1A3A6B" not in PADRAO_VISUAL)
    ok("e a proibicao de marrom e laranja tambem",
       "marrom" not in PADRAO_VISUAL.lower())
    ok("a identidade fixa continua: tipografia",
       "Montserrat" in PADRAO_VISUAL)
    ok("e a trava do produto continua",
       "NUNCA É RECOLORIDO" in PADRAO_VISUAL)

    # O produto e o destaque, e isso virou numero — "o maior possivel" e
    # opiniao, e o modelo tem a dele.
    # A medida saiu do texto e virou dicionario: `INSTRUCAO_PROTAGONISMO` tem
    # o buraco `{faixa}`, e quem o preenche e `OCUPACAO` — a mesma fonte que
    # alimenta a linha de COMPOSITION em ingles. Conferir o numero literal
    # aqui era o que permitia os dois discordarem.
    ok("a ocupacao e medida, e o texto so tem o buraco dela",
       "{faixa}" in INSTRUCAO_PROTAGONISMO
       and "%" not in INSTRUCAO_PROTAGONISMO)
    ok("e ela sai de OCUPACAO, nas duas linguas",
       "60% a 75%" in ocupacao_em_portugues("2 — Benefícios do produto")
       and "60\u201375% of frame" in ocupacao_em_ingles("2 — Benefícios do produto"))
    ok("a ambientacao NAO ganha porcentagem em lingua nenhuma",
       "%" not in ocupacao_em_portugues("8 — Ambientação realista (sem texto)")
       and "%" not in ocupacao_em_ingles("8 — Ambientação realista (sem texto)"))
    ok("o teto de blocos tambem tem fonte unica",
       faixa_de_blocos("4 — Close nos detalhes") == (1, 2)
       and faixa_de_blocos("2 — Benefícios do produto") == (3, 5))
    ok("e a copy da triagem e cortada nesse teto",
       len(montar_prompt_imagem(
           "4 — Close nos detalhes", "", {"cor": "preto"}, "Teste",
           plano_triagem={"composicao": "x",
                          "textos": ["um", "dois", "tres", "quatro"]}
       ).split("  3. ")) == 1)
    ok("e a ordem de montagem esta dita",
       "PRIMEIRO" in INSTRUCAO_PROTAGONISMO)
    ok("o fundo desfocado tem lugar",
       "desfocado" in INSTRUCAO_PROTAGONISMO)

    # ── O PRODUTO GIGANTE NA AMBIENTACAO ────────────────────────────────
    #
    # O dono: "criando ambientacao com o produto desproporcional ao que ele e
    # no ambiente, parece que ele e GIGANTE". A causa era a regra de cima
    # aplicada a ambientacao: 65% a 80% do quadro numa peca sem texto, mais a
    # linha "Nunca deixe o produto pequeno no centro de um cenario amplo" —
    # que e exatamente o que uma foto ambientada e. O modelo obedeceu
    # inflando o produto ate caber nos 70%.
    _amb = montar_prompt_imagem("8 — Ambientação realista (sem texto)", "",
                                {"nome_comercial": "Meia"}, "Meia")
    ok("a ambientacao NAO carrega a regra de 65% a 80%",
       "65% a 80%" not in _amb)
    ok("nem a proibicao de produto pequeno em cenario amplo",
       "Nunca deixe o produto pequeno" not in _amb)
    ok("ela exige ESCALA REAL", "ESCALA REAL" in _amb)
    ok("e diz que o destaque vem do foco, nao do tamanho",
       "FOCO" in _amb and "tamanho" in _amb.lower())
    ok("o produto pousado, com contato e sombra reais",
       "POUSADO" in _amb)

    # E as pecas de marketing continuam com a regra de tamanho — elas TEM
    # texto e o produto precisa dominar o quadro.
    # ── AS FOTOS DO PRODUTO QUE CHEGAM AO MOTOR ─────────────────────────
    #
    # Era `[:3]` escrito a mao em cinco lugares. O colaborador subia nove
    # fotos e o diagnostico dizia "3 de 9 disponiveis": seis angulos jogados
    # fora sem ninguem decidir isso. Num produto de acabamento metalico, cada
    # angulo a menos e detalhe que o gerador inventa.
    ok("o limite de fotos tem um lugar so",
       MAX_FOTOS_AO_MOTOR >= 6)
    ok("e ele corta de verdade",
       len(fotos_para_o_motor([b"x"] * 20)) == MAX_FOTOS_AO_MOTOR)
    # O TETO DE BYTES, QUE E O QUE IMPEDE DE TRAVAR.
    #
    # As fotos vao cruas. Seis de 10MB sao 60MB numa chamada, e isso nao e
    # "menos qualidade": e timeout. Subir de tres para seis sem este teto era
    # trocar um limite arbitrario por um risco de travar.
    _pesada = b"x" * (5 * 1024 * 1024)
    ok("seis fotos pesadas nao passam do orcamento",
       sum(len(f) for f in fotos_para_o_motor([_pesada] * 6))
       <= ORCAMENTO_FOTOS_BYTES)
    ok("mas seis fotos leves passam todas",
       len(fotos_para_o_motor([b"x" * 1000] * 6)) == 6)
    ok("uma foto gigante sozinha AINDA vai — melhor que nenhuma",
       len(fotos_para_o_motor([b"x" * (40 * 1024 * 1024)])) == 1)
    ok("lista vazia ou None nao quebra",
       fotos_para_o_motor(None) == [] and fotos_para_o_motor([]) == [])
    ok("nove fotos passam a ir alem de tres",
       len(fotos_para_o_motor(list(range(9)))) > 3)
    # O TESTE ESTAVA SE ENCONTRANDO. A primeira versao procurava o literal
    # o literal do corte antigo e reprovava — porque a unica ocorrencia no
    # arquivo era ela mesma, escrita aqui. Montado em pedacos, o texto nao
    # existe no fonte, e a conferencia volta a medir o codigo.
    _alvo_corte = "imagens_bytes" + "[:" + "3]"
    ok("nenhum corte de fotos sobrou espalhado no codigo",
       open(__file__, encoding="utf-8").read().count(_alvo_corte) == 0)

    # ── O PLANO E ESCRITO POR IA, E VOLTA DIFERENTE A CADA ANALISE ──────
    #
    # A rodada de 24/09 voltou limpa de seis defeitos que a anterior tinha.
    # Eles nao foram corrigidos — nao apareceram. Montagem se confere uma vez;
    # plano se confere SEMPRE, porque um modelo o reescreve a cada analise.
    _plano_ruim = [
        {"numero": 3, "tipo": "3 — Benefícios no cenário de uso",
         "composicao": "as mãos do casal folheiam o álbum",
         "cena": "mesa de madeira clara com fotos"},
        {"numero": 7, "tipo": "7 — Presenteie",
         "composicao": "entrega do presente",
         "cena": "mesa de linho, duas pessoas"},
        {"numero": 8, "tipo": "8 — Ambientação realista (sem texto)",
         "composicao": "álbum na estante",
         "cena": "prateleira de madeira escura"},
        {"numero": 1, "tipo": "1 — Capa do anúncio (fundo branco)",
         "composicao": "álbum de frente", "cena": "superfície branca pura"},
    ]
    _pess = pessoas_em_peca_errada(_plano_ruim, TIPOS_PADRAO)
    ok("pessoa planejada na peca 3 e apontada",
       any(numero_do_tipo(t) == 3 for t, _ in _pess))
    ok("e a peca 7 NAO e apontada — ela exige duas pessoas",
       not any(numero_do_tipo(t) == 7 for t, _ in _pess))
    ok("capa sem pessoa passa limpa",
       not any(numero_do_tipo(t) == 1 for t, _ in _pess))
    _rep = cenas_repetidas(_plano_ruim, TIPOS_PADRAO)
    ok("madeira na 3 e na 8 e apontada como cena repetida",
       any("madeira" in c for _a, _b, c in _rep))
    ok("cena sem superficie conhecida nao inventa par",
       cenas_repetidas([{"numero": 1, "tipo": "1 — Capa do anúncio (fundo branco)",
                         "cena": "composição centralizada"}], TIPOS_PADRAO) == [])
    ok("plano vazio nao quebra nenhuma das duas",
       pessoas_em_peca_errada([], TIPOS_PADRAO) == []
       and cenas_repetidas(None, TIPOS_PADRAO) == [])

    # ── FIGURA HUMANA TINHA DUAS LISTAS, E ELAS DISCORDAVAM ─────────────
    #
    # A do filtro de layout nao tinha "casal", "familia", "bebe", "menino",
    # "menina" nem "maos"; a da cena nao tinha "person", "people",
    # "character" nem "hand". "Um casal ao fundo" passava pelo filtro; um
    # plano em ingles passava pelo aviso da tela.
    ok("as duas leituras de pessoa saem da MESMA lista",
       _PESSOAS_NO_LAYOUT is PESSOAS and _PESSOAS_NA_CENA is PESSOAS)
    ok("casal e pego no filtro de layout",
       limpar_descricao_de_layout("Blocos à esquerda, um casal ao fundo.") == "")
    ok("familia tambem",
       limpar_descricao_de_layout("Composição com uma família na mesa.") == "")
    ok("e o plano em ingles e pego pelo aviso da tela",
       pessoas_em_peca_errada(
           [{"numero": 3, "tipo": "3 — Benefícios no cenário de uso",
             "cena": "a couple holding the album", "composicao": ""}],
           TIPOS_PADRAO))
    # E NAO PODE CASAR DEMAIS: "modular" e "modelo de grade" sao legitimos.
    ok("composição modular continua passando",
       limpar_descricao_de_layout(
           "Blocos à esquerda, margens generosas, composição modular.") != "")

    # O AVISO DA TELA E EM PORTUGUES, E O RADICAL ACHADO PODE SER EM INGLES.
    #
    # Saiu assim: "Ela voltou mencionando menciona cor ou paleta: branco,
    # red" — verbo duplicado, porque o motivo ja trazia "menciona", e "red"
    # cru num aviso em portugues.
    _mot = "; ".join(motivos_para_descartar_layout(
        "White background with red accents and two people."))
    ok("o motivo nao repete o verbo do aviso", "menciona" not in _mot)
    ok("e sai em portugues",
       "vermelho" in _mot and "red" not in _mot)

    # ── O CAMPO MATERIAL, E O CORTE QUE EXIGIA TEXTO ────────────────────
    #
    # O album do dono e Wire-O, esta escrito na triagem, e a palavra aparecia
    # em 0 dos 8 prompts — justo com a peca 4 sendo o close da encadernacao.
    # O campo "Material" nao era escrito em lugar nenhum.
    _p_mat = montar_prompt_imagem(
        "4 — Close nos detalhes", "",
        {"cor": "preto", "material": "Capa dura, encadernação Wire-O preta"},
        "Álbum")
    # ── O CAMPO DE NOME NAO PODE FICAR MUDO ─────────────────────────────
    #
    # 28/09: "anexei o codigo da descricao, o sistema identificou, mas quando
    # preencho o nome do produto e dou enter para buscar a triagem, nao
    # busca, nao faz nada". Nao fazia: com descricao que ja traz medidas, a
    # triagem e pulada de proposito — e a tela nao dizia isso.
    _corpo_tela = (open(__file__, encoding="utf-8").read()
                   .split("TRIAGEM: specs do produto")[1][:1400])
    ok("com descricao completa, a tela explica por que nao busca",
       "a triagem não é consultada agora" in _corpo_tela)
    ok("e diz como usar a triagem no lugar",
       "apague o código" in _corpo_tela)
    # O AVISO SO APARECE QUANDO HA NOME DIGITADO: sem nome, nao ha pergunta
    # a responder, e o recado viraria ruido em toda abertura da tela.
    ok("o aviso exige nome digitado",
       "if nome_produto and dados_descricao and dados_descricao.get" in _corpo_tela)

    # ── DOIS AMBIENTES IGUAIS, E O PRODUTO SEMPRE DO MESMO LADO ─────────
    #
    # Dono, 28/09: "temos diversas opcoes de ambientacao, entao o estudio nao
    # pode utilizar dois ambientes iguais" e "o produto as vezes tem dois
    # lados com desenhos diferentes; o estudio precisa variar, nao colocar
    # sempre o mesmo lado".
    _plano_faces = [
        {"numero": 1, "tipo": "1 — Capa do anúncio (fundo branco)",
         "cena": "produto de frente sobre fundo branco"},
        {"numero": 2, "tipo": "2 — Benefícios do produto",
         "cena": "vista frontal do produto com cartões ao lado"},
        {"numero": 3, "tipo": "3 — Benefícios no cenário de uso",
         "cena": "produto de lado sobre bancada"},
        {"numero": 4, "tipo": "4 — Close nos detalhes",
         "cena": "macro da alça, aproximado"},
    ]
    _fr = faces_repetidas(_plano_faces, TIPOS_PADRAO)
    ok("duas pecas de frente sao apontadas",
       any("frontal" in c for _a, _b, c in _fr))
    ok("e a peca de lado nao entra no par",
       not any("lateral" in c for _a, _b, c in _fr))
    # A PECA 4 E MACRO POR DEFINICAO: aponta-la seria ruido em toda analise.
    ok("o close nao conta como angulo repetido",
       not any("Close" in a or "Close" in b for a, b, _c in _fr))
    ok("sinonimo e o mesmo angulo: 'de frente' e 'vista frontal'",
       len(_fr) == 1)
    ok("plano sem angulo declarado nao inventa par",
       faces_repetidas([{"numero": 1, "tipo": "1 — Capa do anúncio (fundo branco)",
                         "cena": "produto sobre fundo branco"}],
                       TIPOS_PADRAO) == [])
    ok("plano vazio nao quebra",
       faces_repetidas([], TIPOS_PADRAO) == [] and faces_repetidas(None) == [])

    # E AS DUAS REGRAS TEM DE CHEGAR A ANALISE, que e quem escreve o plano.
    import inspect as _insp_tri
    _corpo_tri = _insp_tri.getsource(gerar_triagem_ia)
    ok("a analise e proibida de repetir ambiente",
       "NUNCA REPETEM O MESMO AMBIENTE" in _corpo_tri)
    ok("e sabe que madeira clara e madeira escura sao a mesma cena",
       "madeira\n  clara" in _corpo_tri and "são a mesma cena" in _corpo_tri)
    # ESTES DOIS TESTES NASCERAM ERRADOS, e o custo apareceu em producao.
    #
    # A versao original exigia a frase "frontal, tres-quartos, lateral,
    # traseiro" dentro do prompt — ou seja, exigia a ORDEM de variar o
    # angulo. Eles foram escritos DEPOIS da mudanca, entao sairam parecidos
    # com o que eu tinha acabado de escrever: travavam a redacao em vez de
    # conferir o comportamento. Passaram verdes enquanto o Studio entregava
    # caneca torta, caneca com duas alcas e um modelo que nao existe.
    #
    # Agora eles conferem a PRECEDENCIA, que e o que importa: a foto manda
    # sobre a variacao. Repetir o angulo que existe e certo; inventar um que
    # nao existe e o mesmo erro de inventar textura.
    ok("a analise varia o angulo",
       "NÃO APARECE SEMPRE DO MESMO LADO" in _corpo_tri)
    ok("mas a foto manda sobre a variacao",
       "AS FOTOS MANDAM" in _corpo_tri)
    ok("e ordenar variacao de angulo nao volta",
       "Distribua os ângulos" not in _corpo_tri)
    # FALTA DE FOTO DE UM ANGULO NAO TORNA A PECA INVIAVEL. Foi por aqui que
    # as pecas 7 e 8 sumiram: `pergunta_info` ganhou um segundo dono.
    ok("falta de angulo nao descarta a peca",
       "NUNCA torna uma peça inviável" in _corpo_tri)

    # ── A FALHA DO AJUSTE NAO DEVOLVE A LICAO DE CASA ───────────────────
    #
    # Em 25/09 a colaboradora recebeu "tente descrever de outro jeito" em
    # quatro das sete pecas, depois de ter descrito cada defeito com clareza.
    # O pedido dela estava certo; quem nao conseguiu traduzir foi o sistema.
    _r_prod = _relato_base(5, {"tentativas": 2, "ok": False,
                               "produto_alterado_fora_do_pedido": True, "falta": "x" * 300})
    ok("a falha nao manda a pessoa reescrever o pedido",
       ("Tente descrever de outro " + "jeito") not in _r_prod)
    # A FRASE "produto mudava junto" SAIU — ela acusava o produto mesmo
    # quando a mudanca tinha sido PEDIDA, e o dono leu isso cinco vezes
    # seguidas num pedido legitimo. O que a tela explica agora e que veio
    # junto o que ninguem pediu.
    ok("quando veio mudanca nao pedida, a tela explica e oferece o caminho",
       "que ninguém pediu" in _r_prod and "refazer a peça do zero" in _r_prod)
    _r_falta = _relato_base(5, {"tentativas": 2, "ok": False,
                                "falta": "os cards devem caber inteiros"})
    ok("o que faltou sai quando e curto o bastante para ajudar",
       "os cards devem caber inteiros" in _r_falta)
    # O TEXTO DO CONFERIDOR E ESCRITO PARA O GERADOR: sai com "6% da base do
    # quadro" e "grade 2x2". Na tela de quem trabalha isso e ruido.
    _r_tec = _relato_base(5, {"tentativas": 2, "ok": False,
                              "falta": "Reduza os quatro cards e organize-os "
                                       "em grade 2x2 ocupando a metade "
                                       "inferior, com a borda terminando a "
                                       "pelo menos 6% da base do quadro, e os "
                                       "textos completos e legiveis em cada "
                                       "um dos quatro."})
    ok("instrucao tecnica longa nao vai para a tela dela",
       "6%" not in _r_tec and "grade 2x2" not in _r_tec)
    ok("e ela sabe que nao precisa reescrever",
       "Não precisa reescrever nada" in _r_tec)

    # ── O HISTORICO DE PROMPTS VAI PARA A PASTA DO PRODUTO ──────────────
    #
    # "Ele precisa salvar automaticamente quando o colaborador clicar em
    # salvar as imagens" — dono, 25/09. Um passo a mais para quem salva e um
    # passo que vai ser esquecido, e o esquecimento so aparece meses depois.
    _subido = {}

    class _GdriveFalso:
        @staticmethod
        def upload(dados, nome, pasta, mimetype="image/png", publico=True):
            _subido.update({"dados": dados, "nome": nome, "pasta": pasta,
                            "mime": mimetype})
            return {"webViewLink": "http://exemplo", "na_raiz": False}, None

    class _LogFalso:
        @staticmethod
        def ler(n=500):
            return [
                {"quando": "25/09/2026 10:00:00", "produto": "Caneca",
                 "imagem": "1", "acao": "prompt_geracao", "usuario": "myrella",
                 "prompt": "O produto ocupa 85-92% do quadro."},
                {"quando": "25/09/2026 10:10:00", "produto": "Caneca",
                 "imagem": "1", "acao": "prompt_ajuste", "usuario": "myrella",
                 "prompt": "MODO AJUSTE FINO\nA alca virada para a direita."},
                {"quando": "25/09/2026 10:20:00", "produto": "Outro produto",
                 "imagem": "1", "acao": "prompt_geracao", "usuario": "leo",
                 "prompt": "Prompt de outro produto qualquer aqui."},
            ]

    import sys as _sys_t
    sys = _sys_t
    _mods = dict(sys.modules)
    sys.modules["gdrive"] = _GdriveFalso
    sys.modules["log_imagem"] = _LogFalso
    try:
        _nome_arq, _err = salvar_prompts_na_pasta("PASTA123", "Caneca")
    finally:
        sys.modules.clear()
        sys.modules.update(_mods)

    ok("o historico sobe sozinho, sem erro", _err == "" and _nome_arq)
    ok("vai para a pasta das imagens", _subido.get("pasta") == "PASTA123")
    ok("e como texto, nao como imagem", _subido.get("mime") == "text/plain")
    ok("o nome diz o que e e de que produto",
       "prompts" in _nome_arq and "Caneca" in _nome_arq)
    # SALVAR DE NOVO NAO PODE SOBRESCREVER A RODADA ANTERIOR: o historico de
    # um produto e a sequencia das rodadas dele.
    ok("o nome carrega a data e a hora",
       len([c for c in _nome_arq if c.isdigit()]) >= 10)
    ok("e o arquivo e texto legivel",
       b"O produto ocupa 85-92%" in _subido.get("dados", b""))
    # O PRODUTO DO LADO NAO ENTRA NO ARQUIVO DESTE.
    ok("so os prompts deste produto entram",
       b"Prompt de outro produto" not in _subido.get("dados", b""))

    # O ERRO AQUI E RECADO, NUNCA EXCECAO: as imagens ja subiram quando esta
    # funcao roda, e uma excecao aqui estragaria o salvamento delas.
    class _GdriveQueExplode:
        @staticmethod
        def upload(*a, **k):
            raise RuntimeError("Google fora do ar")

    _mods2 = dict(sys.modules)
    sys.modules["gdrive"] = _GdriveQueExplode
    sys.modules["log_imagem"] = _LogFalso
    try:
        _n2, _e2 = salvar_prompts_na_pasta("PASTA123", "Caneca")
    finally:
        sys.modules.clear()
        sys.modules.update(_mods2)
    ok("Drive fora do ar vira recado, e nao excecao",
       _n2 == "" and "Google fora do ar" in _e2)

    # SEM PROMPT REGISTRADO, tambem nao explode — so diz que nao ha o que subir.
    class _LogVazio:
        @staticmethod
        def ler(n=500):
            return []

    _mods3 = dict(sys.modules)
    sys.modules["log_imagem"] = _LogVazio
    try:
        _n3, _e3 = salvar_prompts_na_pasta("PASTA123", "Caneca")
    finally:
        sys.modules.clear()
        sys.modules.update(_mods3)
    ok("sem prompt registrado, avisa em vez de subir arquivo vazio",
       _n3 == "" and "nenhum prompt" in _e3)

    # ── A PECA PRECISA SER VISIVEL DE DENTRO DA THREAD ──────────────────
    #
    # O ajuste roda em `threading.Thread`, e e de la que o prompt e
    # registrado. Se a peca morasse so no `session_state`, a leitura de
    # dentro da thread voltaria vazia e a cadeia ficaria sem chave — em
    # silencio, que e o pior jeito de um registro falhar.
    import threading as _th_teste
    import log_imagem as _li_pc
    marcar_peca_em_ajuste(4)
    _visto = {}
    # A THREAD DE TRABALHO HERDA, e a herança é explícita — `alvo_com_contexto`
    # captura na criação, que é o único instante em que as duas se conhecem.
    _t = _th_teste.Thread(target=_li_pc.alvo_com_contexto(
        lambda: _visto.__setitem__("n", peca_em_ajuste())))
    _t.start(); _t.join()
    ok("a peca marcada e vista de dentro de uma thread", _visto.get("n") == "4")

    # ── E DOIS COLABORADORES NAO TROCAM A PECA ENTRE SI ─────────────────
    #
    # ESTE ERA O CUSTO DECLARADO E NAO CONSERTADO. A docstring de
    # `marcar_peca_em_ajuste` dizia, com todas as letras: "o global e do
    # processo, nao da sessao. Dois colaboradores ajustando pecas diferentes
    # no mesmo segundo podem trocar o numero entre si". Declarar e melhor que
    # esconder, mas nao e conserto — e era o MESMO defeito que produto e
    # usuario tinham, tres campos lado a lado no mesmo registro. Eu corrigi
    # dois e deixei o terceiro.
    #
    # A guarda anterior marcava UMA peca e conferia que ela chegava: com um
    # dono so, global e por-thread dao a mesma resposta. O defeito so aparece
    # com DOIS, e e por isso que ele sobreviveu a ela.
    _porta_pc = _th_teste.Barrier(2)
    _lidos = {}

    def _colab_pc(peca):
        def _corpo():
            marcar_peca_em_ajuste(peca)
            _porta_pc.wait()          # os dois marcam ANTES de qualquer leitura
            _lidos[peca] = peca_em_ajuste()
        return _li_pc.alvo_com_contexto(_corpo)

    _a_pc = _th_teste.Thread(target=_colab_pc(3))
    _b_pc = _th_teste.Thread(target=_colab_pc(7))
    _a_pc.start(); _b_pc.start(); _a_pc.join(); _b_pc.join()
    ok("dois colaboradores ajustando ao mesmo tempo nao trocam a peca",
       _lidos.get(3) == "3" and _lidos.get(7) == "7")

    marcar_peca_em_ajuste(None)
    ok("e limpar limpa", peca_em_ajuste() == "")
    ok("ajuste de foto avulsa nao inventa numero de peca",
       peca_em_ajuste() == "")

    ok("o material do cadastro chega ao brief",
       "Material e montagem" in _p_mat and "Wire-O" in _p_mat)
    ok("e com a ordem de nao deduzir",
       "use exatamente isto, não deduza" in _p_mat)

    # E O CORTE PRECISA DE TEXTO. `[:200]` num inteiro levanta TypeError e
    # derruba a tela: uma celula de gramatura digitada como "300" volta do
    # gspread como int. O defeito era antigo — diferenciais, caracteristicas
    # e uso ja cortavam direto — e so nunca tinha encostado num numero.
    for _campo in ("material", "diferenciais", "caracteristicas", "uso"):
        for _v in (None, "", 123, 3.5, ["a"], {"a": 1}):
            try:
                montar_prompt_imagem("4 — Close nos detalhes", "",
                                     {"cor": "preto", _campo: _v}, "T")
                _quebrou = False
            except Exception:
                _quebrou = True
            ok(f"campo {_campo} com {type(_v).__name__} nao derruba a tela",
               not _quebrou)

    # ── DUAS TRAVAS DE COR NO MESMO PROMPT ──────────────────────────────
    #
    # A analise escreveu "cor nao informada, mas deducao visual e tom
    # neutro/escuro que harmoniza com universo de repouso visual" no mesmo
    # prompt em que a trava de cor diz "e PROIBIDO recolorir o produto para
    # harmonizar". Ela fez o que a outra trava proibe — e as cinco fotos eram
    # pretas: nao era cor nao informada, era cor nao DIGITADA no cadastro.
    _trava_suja = ("Álbum quadrado 30x30 com capa dura fosca, folhas pretas "
                   "internas, peso 700g — cor não informada, mas dedução "
                   "visual é tom neutro/escuro que harmoniza com o universo")
    _limpa, _motivo = limpar_trava_do_produto(_trava_suja)
    ok("a frase que deduz cor sai da trava",
       "dedução" not in _limpa and "harmoniza" not in _limpa)
    ok("mas o que a foto MOSTRA fica",
       "capa dura fosca" in _limpa and "folhas pretas" in _limpa)
    ok("e o motivo e registrado, nao engolido", bool(_motivo))
    # CORTAR DEMAIS TAMBEM E DEFEITO: a primeira versao apagou a trava inteira
    # porque a deducao vinha colada por travessao, e o teste pegou.
    ok("trava que so constata passa inteira",
       limpar_trava_do_produto(
           "Resina dourada escura com acabamento acetinado. Nunca rosé."
       )[0].startswith("Resina dourada"))
    ok("trava vazia nao quebra",
       limpar_trava_do_produto(None) == ("", "")
       and limpar_trava_do_produto("") == ("", ""))

    # ── A DESCRICAO DE LAYOUT E TEXTO DE OUTRO MODELO ────────────────────
    #
    # Sexta volta da paleta azul, e a primeira por um caminho que nenhuma
    # varredura de template alcanca: o texto nasce em tempo de execucao.
    ok("descricao com cor e descartada",
       limpar_descricao_de_layout("Títulos em azul-marinho, paleta fria.") == "")
    ok("descricao que nomeia o objeto e descartada",
       limpar_descricao_de_layout("A chaleira vermelha ao centro.") == "")
    ok("descricao com pessoas e descartada",
       limpar_descricao_de_layout("Dois personagens ao fundo.") == "")
    # E O CONTRARIO TAMBEM E DEFEITO: descartar tudo nao protege, cega.
    ok("descricao limpa PASSA — 'generosas' nao e 'rosa'",
       limpar_descricao_de_layout(
           "Duas colunas, blocos à esquerda, margens generosas.") != "")
    ok("e 'modular' nao e 'model'",
       limpar_descricao_de_layout(
           "Composição modular, blocos empilhados, respiro amplo.") != "")

    # ── A DIRECAO DE ARTE DECIDIDA UMA VEZ, HERDADA PELAS OITO ──────────
    #
    # O dono, vendo o conjunto: "6 direcoes de arte diferentes". A causa
    # estava escrita em `PADRAO_VISUAL`, e ia nos OITO prompts: "escolha a
    # paleta, a iluminacao, o cenario e os materiais". Oito pecas decidindo a
    # estetica sozinhas — nao era desobediencia do gerador, era o pedido.
    _dir = {"nome": "Executivo Quente", "posicionamento": "premium",
            "paleta": {"fundo": {"nome": "Marfim", "hex": "#F2EEE6"}},
            "materiais": ["nogueira"], "risco_de_reflexo": "ALTO",
            "trava_do_produto": "resina dourada fosca"}
    _com_dir = montar_prompt_imagem("2 — Benefícios do produto", "",
                                    {"cor": "dourado"}, "x", direcao_arte=_dir)
    _sem_dir = montar_prompt_imagem("2 — Benefícios do produto", "",
                                    {"cor": "dourado"}, "x")
    ok("com direcao herdada, a peca NAO escolhe a paleta",
       "escolha a paleta" not in _com_dir)
    ok("e sem direcao ela volta a deduzir — o comportamento de antes",
       "escolha a paleta" in _sem_dir)
    ok("a paleta-mae chega inteira", "#F2EEE6" in _com_dir
       and "PALETA-MÃE" in _com_dir)
    ok("a trava do produto vem junto",
       "resina dourada fosca" in _com_dir)
    ok("risco de reflexo alto vira instrucao",
       "Risco de reflexo ALTO" in _com_dir)
    ok("direcao vazia nao quebra nem inventa bloco",
       bloco_direcao_de_arte(None) == ""
       and bloco_direcao_de_arte({}) == "")
    ok("a cena da peca entra quando o plano traz",
       "Cena desta peça: nogueira, caneta" in montar_prompt_imagem(
           "2 — Benefícios do produto", "", {}, "x",
           plano_triagem={"composicao": "c", "cena": "nogueira, caneta",
                          "textos": []}))

    _mkt = montar_prompt_imagem("2 — Benefícios do produto", "",
                                {"nome_comercial": "Meia"}, "Meia")
    ok("a peca de marketing mantem a ocupacao medida",
       "60% a 75%" in _mkt)
    ok("e ela NAO recebe a regra da ambientacao",
       "ESCALA REAL" not in _mkt)

    # ── A MARGEM: repetir UMA vez antes de entregar torta ───────────────
    #
    # O Studio media que tinha preenchido faixa e entregava assim mesmo. A
    # pessoa recebia a imagem com margem, pedia correcao, e a correcao
    # quebrava outra coisa — o laco que custou 41 geracoes num produto so.
    import inspect as _insp
    _corpo_g = _insp.getsource(gerar_imagem_ia)
    ok("a geracao aceita a marca de repeticao",
       "_ja_repetiu_quadrada" in _corpo_g)
    ok("e ela repete quando a imagem vem torta",
       "if not _ja_repetiu_quadrada:" in _corpo_g)
    ok("uma unica vez — a segunda chamada ja vai marcada",
       "_ja_repetiu_quadrada=True" in _corpo_g)
    ok("e se voltar torta de novo, entrega em vez de descartar o que foi pago",
       "repeti uma vez e voltou torta" in _corpo_g)

    # ── A REGUA NA IMAGEM, E NAO SO NO PROMPT ───────────────────────────
    ok("a geracao mede a imagem antes de entregar",
       "medir_imagem" in _corpo_g and "_md.problemas(" in _corpo_g)
    ok("e repete quando a medida acusa", "repetindo uma vez" in _corpo_g)
    ok("a ambientacao NAO tem ocupacao cobrada",
       "ambientada=_is_ambientacao" in _corpo_g)
    ok("a regua nunca impede a entrega do que ja foi pago",
       "A régua nunca pode impedir a entrega" in _corpo_g)

    # ── A AMBIENTACAO DO COLABORADOR: tema, e nao roteiro ────────────────
    _DADOS_T = {"nome_comercial": "Marcador de Taça", "material": "Acrílico"}
    _sem = montar_prompt_imagem("8 — Ambientação realista (sem texto)", "",
                                _DADOS_T, "Marcador de Taça")
    ok("sem ambientacao, o prompt nao inventa bloco nenhum",
       "AMBIENTAÇÃO PEDIDA" not in _sem)

    _com = montar_prompt_imagem("8 — Ambientação realista (sem texto)", "",
                                _DADOS_T, "Marcador de Taça",
                                ambientacao="jantar entre amigos, mesa posta")
    ok("com ambientacao, o texto do colaborador chega inteiro",
       "jantar entre amigos, mesa posta" in _com)
    ok("e chega como TEMA, mandando variar a cena",
       "NÃO repita a mesma cena" in _com)
    ok("espaco em branco nao vira bloco",
       "AMBIENTAÇÃO PEDIDA" not in montar_prompt_imagem(
           "8 — Ambientação realista (sem texto)", "", _DADOS_T, "x",
           ambientacao="   "))

    # A contradicao do tipo 8: "ZERO TEXTO" seguido de "escreva esta frase".
    # Contradicao em prompt e brecha: o modelo resolve escrevendo mais coisa.
    ok("o tipo 8 nao diz mais ZERO TEXTO e depois manda escrever",
       "ZERO TEXTO" not in _sem)
    ok("e a excecao esta dita como excecao unica",
       "EXCEÇÃO ÚNICA" in _sem and "Imagem meramente ilustrativa" in _sem)

    # A lista fixa de comodos era semanticamente errada para metade dos
    # produtos: marcador de taca nao pertence a estante de livros.
    ok("a lista fixa de ambientes saiu",
       "quarto de estudos" not in _sem.split("PADRÃO VISUAL")[0]
       or "NÃO existe ambiente" in _sem)

    # O protagonismo vale nos tipos COM texto tambem, e nao so na ambientacao.
    _t2 = montar_prompt_imagem("2 — Benefícios do produto", "", _DADOS_T, "x")
    ok("o protagonismo entra tambem nas pecas com texto",
       "O PRODUTO É O DESTAQUE" in _t2)
    ok("e a direcao de arte adaptativa tambem",
       "DIREÇÃO DE ARTE ADAPTATIVA" in _t2)

    # A VARREDURA, porque a correcao ficou num caminho so TRES vezes seguidas.
    #
    # Trocar a paleta no PADRAO_VISUAL e deixar "#E8EEF5" no preset do tipo 2,
    # no preset do 7 e no bloco em ingles de gerar_imagem_ia seria mandar ao
    # modelo a regra nova e a ordem contraria na MESMA mensagem. Este caso
    # reprova qualquer cor de marca que volte a ser escrita como obrigatoria,
    # em qualquer um dos oito tipos.
    import re as _re_cor
    _cores_fixas = ("#E8EEF5", "#1A3A6B", "#4A7EC7")
    _com_cor = []

    # A PALETA FIXA SOBREVIVEU UMA QUARTA VEZ — FORA DO PROMPT.
    #
    # Tiramos o azul do texto tres vezes, e ele continuava sendo PINTADO no
    # pos-processamento: a faixa de preenchimento das pecas de marketing usava
    # (232, 238, 245), o azul-claro da marca. E literalmente o que o dono viu
    # — "faixas azul-claras nas laterais das imagens 2, 3, 4, 6, 7 e 8".
    #
    # Procurar a cor so no PADRAO_VISUAL nunca ia achar isso. Este caso olha o
    # arquivo inteiro.
    _fonte_img = open(__file__, encoding="utf-8").read()
    # Sem comentarios E sem o proprio bloco de conferencia: a linha que
    # procura pela cor CONTEM a cor, e o teste reprovaria a si mesmo. E a
    # segunda vez hoje que caio nisso.
    _codigo_img = _fonte_img.split('if __name__ == "__main__":')[0]
    _sem_comentario = "\n".join(
        l for l in _codigo_img.split("\n") if not l.lstrip().startswith("#"))
    ok("a cor da marca nao e PINTADA em faixa nenhuma",
       "232, 238, 245" not in _sem_comentario)
    # ── A MARCA QUE SO ERA LIGADA ───────────────────────────────────────
    #
    # `img_fotos_sao_arte` era ligada pelo Ajuste Fino avulso e NUNCA
    # desligada. Quem usasse o Ajuste Fino uma vez carregava a marca pela
    # sessao inteira, e a geracao seguinte — com fotos de produto de verdade —
    # ainda recusava refazer: "esta imagem entrou pelo modo Ajuste Fino".
    # Era mentira, e a colaboradora leu isso tres vezes seguidas enquanto
    # pedia para refazer a Imagem 1.
    ok("a marca de arte e ligada em algum lugar",
       '_sao_arte"] = True' in _sem_comentario)
    ok("E DESLIGADA quando ha fotos de produto",
       _sem_comentario.count('_sao_arte"] = False') >= 2)
    ok("a recusa de refazer olha a FOTO, e nao a marca",
       "if not _fotos_rf:" in _sem_comentario
       and "_so_arte" not in _sem_comentario)
    # ── REFERENCIA DE AMBIENTACAO: OLHAR, E NAO LER O NOME ──────────────
    #
    # Pedido do dono: "nao tem que ir pelo nome da imagem, tem que olhar todas
    # e entender qual ambientacao se enquadra melhor em cada tipo".
    ok("existe campo proprio para referencia de ambientacao",
       "img_refs_ambientacao" in _sem_comentario)
    ok("as fotos viajam na config, e nao em variavel solta",
       '"refs_ambientacao": st.session_state.get(' in _sem_comentario)
    ok("a leitura acontece UMA vez, antes do laco das pecas",
       _sem_comentario.index("_ar.descrever(")
       < _sem_comentario.index("for i, tipo in enumerate(tipos):"))
    ok("e o cenario escolhido entra na ambientacao daquele tipo",
       "para_o_tipo(_amb_desc, tipo)" in _sem_comentario)
    ok("o texto do colaborador vem antes do cenario da visao",
       _sem_comentario.index('cfg.get("ambientacao", "") or ""')
       < _sem_comentario.index("para_o_tipo(_amb_desc, tipo)"))
    ok("falha de visao NAO impede a geracao",
       '_amb_desc.get("erro")' in _sem_comentario
       and "saem com o tema escrito" in _sem_comentario)

    ok("e a mensagem diz o que falta, nao de onde a imagem veio",
       "Preciso das fotos do produto para refazer" in _sem_comentario)

    # O PREENCHIMENTO SAIU DESTE ARQUIVO.
    #
    # Ele morava aqui e pintava a faixa; agora quem enquadra e
    # `enquadrar.py`, que RECORTA em volta do assunto e so preenche no caso
    # em que o assunto nao cabe. A guarda muda de forma junto: aqui nao pode
    # sobrar pintura nenhuma, e a guarda da cor vive la, no teste do proprio
    # `enquadrar`.
    ok("imagem.py nao pinta mais faixa nenhuma",
       "bg_color = (" not in _sem_comentario)
    ok("e delega o enquadramento para o modulo proprio",
       "enquadrar" in _sem_comentario and "_enq.quadrar(" in _sem_comentario)
    import enquadrar as _enq_t
    ok("o modulo de enquadramento passa na propria conferencia",
       hasattr(_enq_t, "quadrar") and hasattr(_enq_t, "janela"))

    for _t in TIPOS_PADRAO:
        _p = montar_prompt_imagem(_t, "", _DADOS_T, "x")
        for _c in _cores_fixas:
            if _c in _p:
                _com_cor.append(f"{_t}: {_c}")
    ok("nenhum tipo manda mais cor de marca fixa (%s)" % (_com_cor or "limpo"),
       _com_cor == [])

    # O branco da capa CONTINUA obrigatorio: ele nao e cor de marca, e
    # exigencia de marketplace. Soltar a cor nao pode soltar isso junto.
    _capa = montar_prompt_imagem("1 — Capa do anúncio (fundo branco)", "",
                                 _DADOS_T, "x")
    ok("mas o fundo branco da capa continua de pe",
       "branco" in _capa.lower())
    for _k, _v in _env_antes.items():
        if _v:
            os.environ[_k] = _v
        else:
            os.environ.pop(_k, None)

    ok("aprovado não polui a tela", texto_em_aviso({"ok": True}) == "")
    ok("relato sem revisão não inventa aviso", texto_em_aviso(None) == "")

    # Sem chave nao ha revisao, e a tela tem que dizer isso sozinha, antes de
    # gerar. Este e o caso que passou meses invisivel.
    import os as _os_t
    _guardado = _os_t.environ.pop("ANTHROPIC_API_KEY", None)
    ok("sem chave, a aba avisa antes de gerar",
       revisao_de_texto_disponivel()[0] is False)
    _os_t.environ["ANTHROPIC_API_KEY"] = "teste"
    ok("com chave, a aba nao avisa a toa",
       revisao_de_texto_disponivel() == (True, ""))
    if _guardado is None:
        _os_t.environ.pop("ANTHROPIC_API_KEY", None)
    else:
        _os_t.environ["ANTHROPIC_API_KEY"] = _guardado
    # ── A COPIA DE SEGURANCA ACOMPANHA TODO AJUSTE ──────────────────────
    #
    # O defeito que estes casos travam: `_rasc.salvar` existia uma vez so, no
    # laco da geracao. Uma tarde de ajustes vivia apenas em session_state, e o
    # disco guardava as originais. Reiniciou, perdeu — e recuperar traria o
    # trabalho de antes das correcoes.
    #
    # E como o defeito e "faltou chamar em algum lugar", o teste tem de olhar
    # o ARQUIVO, e nao uma funcao. Nenhum teste de unidade pega uma chamada
    # que nao existe.
    import re as _re_conf
    _src = open(__file__, encoding="utf-8").read()
    _corpo = "\n".join(l for l in _src.split("\n")
                       if not l.lstrip().startswith("#"))

    _chamadas = len(_re_conf.findall(r"(?<!def )guardar_rascunho\(", _corpo))
    ok("o rascunho e gravado em varios pontos, nao so na geracao",
       _chamadas >= 6)

    # Todo lugar que troca os bytes de uma imagem da galeria tem de gravar.
    _trocas = [m.start() for m in
               _re_conf.finditer(r'img_galeria"\]\[\w+\]\["bytes"\]\s*=', _corpo)]
    _sem_guarda = [i for i in _trocas
                   if "guardar_rascunho" not in _corpo[i:i + 400]]
    ok("toda troca de bytes na galeria grava o rascunho logo depois",
       _trocas and not _sem_guarda)

    ok("a falha de gravacao tem onde aparecer",
       "def aviso_de_rascunho" in _src and "aviso_de_rascunho()" in _corpo)
    ok("e ela NAO e mais engolida em silencio",
       "img_rascunho_erro" in _src)

    ok("registrar_revisao fora da tela nao derruba",
       registrar_revisao({"ok": None, "erro": "x"}) is None)

    # ── O ARQUIVO QUE O NAVEGADOR AINDA LISTA E O SERVIDOR JA PERDEU ─────
    #
    # 28/09, 17:17: a tela mostrava tres fotos anexadas e o botao respondia
    # "Suba pelo menos uma foto do produto". O dono tinha as fotos na tela,
    # e o Studio dizia que nao tinha nenhuma.
    #
    # O que acontece por baixo: os bytes do upload moram na MEMORIA DO
    # PROCESSO (streamlit/runtime/memory_uploaded_file_manager.py,
    # `file_storage` — um dicionario), e o navegador guarda a LISTA DE NOMES
    # por conta propria. Quando o processo reinicia — deploy, queda, troca de
    # container — os nomes continuam na tela e os bytes nao existem mais.
    # O Streamlit entao devolve `DeletedFile(file_id=...)` no lugar do
    # arquivo (streamlit/elements/widgets/file_uploader.py,
    # `_get_upload_files`), e `deserialize` NAO tira esses objetos da lista:
    # eles chegam em `revisar_anexos` misturados com os arquivos bons.
    #
    # `DeletedFile` nao tem `.getvalue()` nem `.name`, e e verdadeiro num
    # `if`. O codigo antigo mandava o objeto inteiro para `_detectar_mime`,
    # que faz `data[:8]` — e a tela inteira caia com
    # `TypeError: 'DeletedFile' object is not subscriptable`.
    #
    # A entrada deste teste vem do Streamlit, e nao da minha cabeca: e a
    # classe de verdade, a mesma que a tela recebe.
    from streamlit.runtime.uploaded_file_manager import DeletedFile as _DelFile

    class _UpFalso:
        def __init__(self, nome, dados):
            self.name, self._d = nome, dados

        def getvalue(self):
            return self._d

    _png1x1 = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
               b'\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
               b'\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01'
               b'\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')

    _perdido = _DelFile("id-que-o-servidor-nao-tem")
    try:
        _b_del, _n_del, _a_del, _e_del = revisar_anexos([_perdido])
        _caiu = ""
    except Exception as _e_dl:
        _b_del = _n_del = _a_del = _e_del = []
        _caiu = f"{type(_e_dl).__name__}: {_e_dl}"

    ok("arquivo perdido pelo servidor NAO derruba a tela", not _caiu)
    ok("e ele nao entra como foto boa", _b_del == [])
    ok("o erro diz o que fazer — recarregar e anexar de novo",
       len(_e_del) == 1 and "recarregue" in _e_del[0].lower()
       and "anexe" in _e_del[0].lower())

    # E o lote nao pode morrer junto: quem anexou tres e o servidor perdeu
    # uma ainda tem duas boas.
    _b_mix, _n_mix, _a_mix, _e_mix = revisar_anexos(
        [_UpFalso("boa1.png", _png1x1), _perdido, _UpFalso("boa2.png", _png1x1)])
    ok("as fotos que sobreviveram continuam valendo", len(_b_mix) == 2)
    ok("e os nomes seguem alinhados com os bytes",
       _n_mix == ["boa1.png", "boa2.png"])
    ok("o arquivo perdido vira um erro so", len(_e_mix) == 1)

    conferir_texto = _real
    print("\nfalhas:", falhas)
    # O CODIGO DE SAIDA, QUE NUNCA EXISTIU AQUI — e 33 mutacoes dependiam dele.
    #
    # Este auto-teste imprimia "falhas: N" e saia com 0 SEMPRE. O `conferir.py`
    # lia o texto e enxergava a falha; o `checar_mutacao` le o CODIGO DE SAIDA,
    # e para ele este arquivo nunca reprovava. Resultado: 33 das 122 entradas
    # de mutacao — toda guarda deste modulo — estavam verdes por acidente,
    # medindo coisa nenhuma.
    #
    # Foi assim que o defeito apareceu: escrevi a guarda da trava de cor,
    # reintroduzi o defeito, vi "falhas: 2" na tela E "VERDE" no veredito. A
    # mesma doenca que o CLAUDE.md ja registra para o `varredura_formas.py`,
    # pelo lado espelhado: la o codigo era 1 sempre, aqui e 0 sempre, e nos
    # dois casos ninguem lia.
    import sys as _sys_fim
    _sys_fim.exit(1 if falhas else 0)
