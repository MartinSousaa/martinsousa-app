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
    3: (45, None,
        "Product is the protagonist; the environment supports it and never "
        "dominates. Full product: preferably YES."),
    4: (80, 92,
        "Macro close-up of ONE detail. Do NOT show the full product. Full product: NO."),
    5: (50, 65,
        "The text panels occupy a dedicated zone of the remaining frame — they never "
        "overlap the product, and the product is never shrunk to make room for them. "
        "If the text does not fit in its zone, write FEWER blocks."),
    6: (50, 65,
        "The text panels occupy a dedicated zone of the remaining frame — they never "
        "overlap the product, and the product is never shrunk to make room for them. "
        "If the text does not fit in its zone, write FEWER blocks."),
    7: (30, 45,
        "This is a HANDOVER SCENE with two people, so the product does not fill the "
        "frame — it leads by position and focus: front and centre between the hands, "
        "sharp, fully visible and uncropped, while the people stay softer behind it. "
        "Full product: YES. Never enlarge the product beyond its real scale in the "
        "hands that hold it."),
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
    if minimo == maximo:
        return (f"- Sem referência: exatamente {maximo} bloco de texto. "
                f"É o teto desta peça — nenhuma outra instrução autoriza mais.")
    return (f"- Sem referência: use de {minimo} a {maximo} blocos informativos, "
            f"conforme o conteúdo disponível. {maximo} é o teto desta peça — "
            f"nenhuma outra instrução autoriza mais.")


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
  verdade em relação ao ambiente e aos objetos ao redor. Uma peça de vestuário
  sobre uma cama tem o tamanho de uma peça de vestuário; um objeto de mesa não
  pode ficar do tamanho da mesa.
- Ele domina a cena por FOCO e por LUZ: nítido e bem iluminado em primeiro
  plano, com o ambiente em profundidade de campo mais suave atrás.
- O enquadramento é fechado ou médio NO PRODUTO — a câmera chega perto dele.
  Aproximar a câmera é o que o destaca; ampliar o objeto o deforma.
- É correto e desejável que o produto ocupe uma fração modesta do quadro se é
  isso que a escala real determina. Cenário amplo com o produto em evidência
  pelo foco é o objetivo desta peça, não um defeito dela.
- Nada de objeto flutuando, apoio impossível ou sombra que não bate com a
  superfície: o produto está POUSADO no ambiente, com contato e sombra reais.
"""

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

INSTRUCAO_FIDELIDADE = """
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
- NÃO copie nem reproduza nenhum texto, palavra ou rótulo que apareça escrito
  nas fotos de referência — ignore completamente qualquer texto visível nas imagens
- PROIBIÇÃO ABSOLUTA DE INVENTAR DADOS TÉCNICOS: JAMAIS crie, estime ou invente
  medidas, dimensões, peso ou material do produto. Se esses dados não foram
  fornecidos nos campos do produto, NÃO os coloque na imagem sob nenhuma hipótese.
  Imagem com dados inventados é pior do que imagem sem dados.
- Só use medidas e peso na imagem se eles estiverem EXPLICITAMENTE informados
  nos dados do produto fornecidos — nunca estime por conta própria

INTEGRIDADE ESTRUTURAL (o que fazer quando você NÃO sabe como o produto funciona):
- NÃO invente mecânica interna: folhas soltas, páginas saindo, miolo exposto,
  abas, encaixes, dobradiças, camadas extras, peças móveis ou vãos que não
  aparecem nas fotos de referência
- Quando um ângulo ou parte interna não estiver visível nas fotos, a saída correta
  é NÃO MOSTRAR essa região — escolha um ângulo que ela não apareça. Preencher o
  desconhecido com algo plausível é erro grave, não criatividade
- Mantenha a estrutura visível exatamente como está: espessura, encadernação,
  acabamento, quantidade de partes"""

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
  peça, e é de lá que ela sai — não estime outra.
"""

INSTRUCAO_LAYOUT_MARKETING = """
REGRA DE LAYOUT PARA IMAGENS DE MARKETING (obrigatória para tipos 2, 3, 4, 5, 6 e 7):
- PROIBIÇÃO ABSOLUTA: JAMAIS sobreponha texto, ícone, título ou qualquer elemento gráfico
  diretamente sobre o produto. O produto deve estar em zona limpa, sem nada sobre ele.
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
- QUANDO HOUVER IMAGEM DE REFERÊNCIA DE LAYOUT, ELA MANDA. Reproduza a mesma
  quantidade de blocos, o mesmo tamanho de texto e a mesma densidade que ela
  mostra — mesmo que sejam 5 ou 6 blocos. A referência é o padrão aprovado da
  empresa; qualquer número abaixo desta regra não se aplica a ela.
{blocos}
- Cada bloco: título curto em CAIXA ALTA (2-5 palavras) + descrição de 8 a 16
  palavras. Descrição de 3 palavras deixa a peça pobre e sem argumento de venda.
- Blocos em cartões de cantos arredondados, com ícone próprio, alinhados em
  coluna ou grade — não como texto solto sobre o fundo
- Espaçamento uniforme entre blocos; respiro nas bordas da peça
- NUNCA adicione tags, selos, rodapés, ícones de compatibilidade ou elementos
  decorativos além dos blocos pedidos

REGRA DE TEXTO REAL (o erro mais constrangedor):
- TODO texto renderizado deve ser português correto e existir de verdade. É
  PROIBIDO inventar palavras, misturar idiomas ou desenhar texto decorativo
  ilegível que "pareça" escrita. Nada de "Profess commerco", "High-resolução"
  ou variações — isso destrói a credibilidade do anúncio.
- NENHUMA palavra em inglês na peça, em lugar nenhum. Isso inclui o CENÁRIO:
  lombada de livro, capa de caderno, tela de computador, etiqueta, embalagem e
  placa. Se um objeto do cenário teria texto, escreva-o em português do Brasil
  — ou desenhe o objeto sem texto legível.
- Frase curta é o que sai certo. Título de 2 a 4 palavras, frase de 4 a 9.
  Quanto mais longa a frase, mais letra inventada aparece nela.
- Pontuação fechada: parêntese que abre, fecha. Nada de "(exemplo," solto no
  meio de uma frase.
- Se não houver informação suficiente para preencher um bloco, use MENOS blocos.
  Bloco a menos é melhor que bloco com texto inventado.
- PROIBIDO desenhar logotipo, marca, monograma ou assinatura sobre o produto ou
  na peça. O produto não tem logo — não crie um.
"""

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
3. Preserve exatamente todos os textos que já existem na imagem
   (não adicione nem remova nenhum texto)
4. Preserve a aparência exata do produto: mesma cor, mesmos detalhes,
   mesmos elementos visíveis (furos, padrões, logotipos na embalagem, etc.)
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
        "Fundo deduzido do produto — sem cor de marca fixa. Benefícios em cartões laterais, inferiores ou em grade — a quantidade vem da regra de densidade; siga a referência de layout quando houver: "
        "ícone line-art na cor da direção de arte escolhida para ESTE produto — não existe cor "
        "de ícone fixa — + título curto (2-3 palavras) + frase direta (máximo 7 palavras). "
        "Visual arejado, muito whitespace — jamais comprima ou empilhe os blocos de benefício. "
        "Os textos dos benefícios vêm dos diferenciais e características do produto informados."
    ),
    "3 — Benefícios no cenário de uso": (
        "IMAGEM DE MARKETING — PRODUTO NO AMBIENTE DE USO REAL: deduza das fotos e dos dados "
        "onde ESTE produto é de fato usado, e por quem — não escolha de uma lista pronta de "
        "cômodos. Produto protagonista em cena aspiracional, com a luz e a paleta que "
        "valorizem este produto. Frases de destaque em painéis fora do produto (nunca sobre "
        "ele) — a quantidade vem da regra de densidade. Cada frase: curta, impactante, "
        "máximo 6 palavras. Sem cor de "
        "marca fixa: fundo e elementos gráficos saem da direção de arte deste produto. "
        "Visual editorial — parece foto de lifestyle de qualidade, não montagem amadora."
    ),
    "4 — Close nos detalhes": (
        "CLOSE NO PRODUTO — ZOOM REAL EM DETALHE ESPECÍFICO: NÃO mostre o produto inteiro. "
        "Recorte e amplie UMA área específica do produto: textura do material, acabamento, encaixe, "
        "mecanismo, superfície, ou detalhe que justifique qualidade e diferencial. "
        "Fundo desfocado (bokeh) com produto em foco nítido no primeiro plano. "
        "A SUPERFÍCIE É A DAS FOTOS, NÃO UMA INVENTADA: aproxime APENAS de uma área "
        "que apareça nítida nas fotos de referência, e reproduza o relevo, a "
        "granulação, as marcas e as manchas exatamente como estão lá. Não acrescente "
        "textura, poro, rachadura, desgaste, veio ou mancha de cor que não exista na "
        "foto. Se nenhuma área estiver nítida o bastante para um macro, aproxime "
        "menos — enquadramento mais aberto e fiel vale mais que macro inventado. "
        "Callouts discretos com linha fina + legenda de até 4 palavras — a quantidade vem da "
        "regra de densidade —, posicionados "
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
        "em destaque e blocos de pergunta+resposta ao lado, em cartões de cantos arredondados "
        "— a quantidade vem da regra de densidade; siga a referência de layout quando houver. "
        "Cada bloco: pergunta curta (máximo 5 palavras) em destaque + check verde + resposta direta "
        "(máximo 8 palavras). As objeções são baseadas nos diferenciais e características do produto. "
        "Visual arejado, muito whitespace, fundo e paleta deduzidos do produto e da ocasião."
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
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None, "ANTHROPIC_API_KEY não configurada."

    tipos_str = "\n".join(f"- {t}: {PRESETS.get(t,'')[:300]}..." for t in tipos_selecionados)

    contexto_descricao = ""
    if dados_descricao:
        contexto_descricao = f"""
DADOS DA DESCRIÇÃO DO PRODUTO (vinculados pelo código):
- Cor: {dados_descricao.get('cor', 'não informada')}
- Medidas: {dados_descricao.get('medidas', 'não informadas')}
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
        if dados_descricao.get("material") or dados_descricao.get("caracteristicas"):
            dados_disponiveis.append("material/características informados")
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

TIPOS A CRIAR:
{tipos_str}

TAREFA: duas coisas, nesta ordem.

PRIMEIRO — A DIREÇÃO DE ARTE DO PRODUTO, DECIDIDA UMA VEZ SÓ
-------------------------------------------------------------
Antes de planejar qualquer imagem, olhe as fotos e decida o universo visual
DESTE produto. Essa decisão vale para as 8 peças e não se repete: cada peça
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
  Título de 2 a 4 palavras; frase de 4 a 9 palavras. Frase longa é o que ele
  erra: quanto mais palavra, mais letra inventada.
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

O CAMPO "cena" — OITO CENAS, UM UNIVERSO SÓ
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
peça — e confira que nenhuma outra das oito repete a mesma combinação. Não
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
        msg = client.messages.create(
            model="claude-haiku-4-5",
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
    key = st.secrets.get("GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
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
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", "")

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
            estilo_layout = msg.content[0].text.strip()
        except Exception:
            pass

    return descricao_produto, estilo_layout


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


def _chamar_gemini_geracao_texto(prompt_final, imagens_bytes=None, ref_layout=None):
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
            for img_b in (imagens_bytes or [])[:3]:
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
            _com_proporcao = dict(_base_body)
            _com_proporcao["generationConfig"] = {
                "responseModalities": ["IMAGE"],
                "responseFormat": {"image": {"aspectRatio": "1:1",
                                             "imageSize": "1K"}},
            }
            _sem_proporcao = dict(_base_body)
            _sem_proporcao["generationConfig"] = {
                "responseModalities": ["IMAGE", "TEXT"],
            }

            resp = requests.post(url, json=_com_proporcao, headers=headers,
                                 timeout=120,
                                 proxies={"http": None, "https": None})
            if resp.status_code == 400:
                import sys as _sys_ar
                print("[gemini] proporcao recusada pela API — repetindo sem "
                      f"ela. Resposta: {resp.text[:1500]}",
                      file=_sys_ar.stderr, flush=True)
                resp = requests.post(url, json=_sem_proporcao, headers=headers,
                                     timeout=120,
                                     proxies={"http": None, "https": None})
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
    for arq in (arquivos or []):
        dados = arq.getvalue() if hasattr(arq, "getvalue") else arq
        nome = getattr(arq, "name", "")
        ok, aviso, erro = revisar_arquivo(dados, nome)
        if erro:
            erros.append(erro)
            continue
        if aviso:
            avisos.append(aviso)
        prontos.append(ok)
        nomes.append(nome)
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
MODELO_IMAGEM_PADRAO = "gpt-image-2.5-sunburst"

# A ordem em que se tenta quando é preciso escolher sozinho: o mais capaz
# primeiro, porque a fidelidade ao produto é o que o Studio está comprando.
MODELOS_IMAGEM_CONHECIDOS = ("gpt-image-2.5-sunburst", "gpt-image-2.5-flare")

# Descoberto em execução, quando o nome configurado não existe. Vive no
# processo: perguntar uma vez por container basta, e uma chamada a cada geração
# seria custo recorrente para resolver um problema de uma vez só.
_MODELO_DESCOBERTO = {"nome": None}


def modelo_de_imagem():
    """O modelo que a geração usa. Configurável pelo Railway.

    `OPENAI_MODELO_IMAGEM` manda, depois o que foi descoberto na conta, depois
    o padrão. O dia em que a OpenAI lançar um modelo melhor, trocar é uma
    variável — não é deploy.
    """
    import chaves as _ch_mod
    return (_ch_mod.ler("OPENAI_MODELO_IMAGEM")
            or _MODELO_DESCOBERTO["nome"]
            or MODELO_IMAGEM_PADRAO)


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
    # "gpt-image" cobre a família inteira sem depender da versão — que é o que
    # este bloco existe para parar de fazer.
    achados = sorted(n for n in nomes if "image" in str(n).lower()
                     and "gpt" in str(n).lower())
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
            for img_b in imagens_bytes[:3]:
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
            try:
                resp = client.responses.create(
                    model=_modelo,
                    input=entrada,
                    tools=[{
                        "type": "image_generation",
                        "size": "1024x1024",
                        "quality": "high",
                        "input_fidelity": "high",
                    }],
                )
                img = _extrair(resp)
                if img:
                    import sys as _sys
                    print(f"[DEBUG {_modelo}] Operation: generate/edit | "
                          f"References sent: {len(imagens_bytes)} | size=1024x1024 | "
                          "input_fidelity=high", file=_sys.stderr)
                    if diagnostico is not None:
                        diagnostico["motor"] = f"{_modelo} (Responses + tools)"
                        diagnostico["size_pedido"] = "1024x1024"
                        diagnostico["input_fidelity"] = "high"
                        diagnostico["refs_enviadas"] = len(imagens_bytes[:3])
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
                    for _i, img_b in enumerate(imagens_bytes[:3])
                ]
                if ref_layout:
                    arquivos.append(_arquivo_para_openai(ref_layout, "layout_referencia"))
                edit = client.images.edit(
                    model=_modelo,
                    image=arquivos,
                    prompt=prompt_final,
                    size="1024x1024",
                    quality="high",
                    input_fidelity="high",
                )
                _d = edit.data[0]
                if getattr(_d, "b64_json", None):
                    import sys as _sys
                    print(f"[DEBUG {_modelo}] Operation: edit | "
                          f"References sent: {len(arquivos)} | size=1024x1024 | "
                          "input_fidelity=high", file=_sys.stderr)
                    if diagnostico is not None:
                        diagnostico["motor"] = f"{_modelo} (images.edit)"
                        diagnostico["size_pedido"] = "1024x1024"
                        diagnostico["input_fidelity"] = "high"
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
                    diagnostico["refs_enviadas"] = len(imagens_bytes[:3])
                return img, None
            return None, "Sem imagem na resposta Responses API."

        # ── SEM FOTOS: geração texto puro ──
        response = client.images.generate(
            model=_modelo,
            prompt=prompt_final,
            n=1,
            size="1024x1024",
            quality="high",
        )
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
                    _ja_repetiu_quadrada=False):
    """Arquitetura de geração — fotos do produto vão diretamente ao modelo via Responses API.

    Fluxo:
    1. Claude Vision analisa fotos → descrição de apoio (usada apenas quando não há OpenAI)
    2. Claude descreve estilo das refs de layout (se houver) → texto de composição
    3. Monta prompt único preservando preset completo do tipo (sem double-prompt)
    4. Tenta o motor primário da OpenAI — fotos enviadas diretamente
    5. Fallback: Gemini Flash Image com texto-apenas
    6. Retorna imagem com proporções exatas preservadas (sem deformação)
    """
    import re as _re

    # Extrai metadados do prompt para contextualizar a descrição
    nome_produto = ""
    _m = _re.search(r"PRODUTO:\s*(.+?)(?:\n|$)", prompt_texto)
    if _m:
        nome_produto = _m.group(1).strip()

    dados_descricao = {}
    _m_cor = _re.search(r"Cor:\s*(.+?)(?:\n|$)", prompt_texto)
    _m_med = _re.search(r"Medidas EXATAS[^:]*:\s*(.+?)(?:\n|$)", prompt_texto)
    _m_pes = _re.search(r"Peso EXATO[^:]*:\s*(.+?)(?:\n|$)", prompt_texto)
    if _m_cor:
        dados_descricao["cor"] = _m_cor.group(1).strip()
    if _m_med:
        dados_descricao["medidas"] = _m_med.group(1).strip()
    if _m_pes:
        dados_descricao["peso"] = _m_pes.group(1).strip()

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
    if _tem_texto_em_painel:
        import re as _re_bl
        _pedidos = len(_re_bl.findall(r"^  \d+\. ", prompt_texto, _re_bl.M))
        if _pedidos:
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
    _tem_fotos = bool(imagens_referencia) and bool(_get_openai_api_key())
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
        + (f"- Maximum {_max_blocos} information elements if text present — never cluttered\n"
           if not _is_clean_photo else
           "- No text elements at all: no whitespace has to be reserved for "
           "them. The occupancy stated above is the only rule about size.\n")
        + 
        f"- Professional studio quality — high-end e-commerce agency standard"
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
            f"- A ÚLTIMA imagem é apenas REFERÊNCIA DE LAYOUT (arquivo "
            f"\"{_ref_layout_nome}\"). Use dela SOMENTE a composição: posição dos "
            f"blocos, hierarquia, estilo dos textos, uso do espaço.\n"
            f"- PROIBIDO copiar o produto, as cores do produto, marcas ou textos da "
            f"imagem de referência de layout. O produto da peça final é o das "
            f"primeiras fotos, nunca o da referência."
        )
    if diagnostico is not None:
        diagnostico["ref_layout"] = _ref_layout_nome or "nenhuma correspondeu ao tipo"

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

    # 5. Fallback: Gemini texto-apenas
    #
    # ATENCAO: este caminho NAO recebe as fotos do produto — so o texto. O
    # modelo nunca ve o produto real, entao inventa um a partir da descricao.
    # E a explicacao mais provavel para um produto preto sair azul-marinho:
    # sem foto, sobra a paleta da marca. Por isso o diagnostico marca este
    # caminho de forma bem visivel.
    if not img_bytes:
        if diagnostico is not None:
            _n_refs = len((imagens_referencia or [])[:3])
            diagnostico["motor"] = "Gemini 3.1 Flash Image (fallback, COM fotos)"
            diagnostico["refs_enviadas"] = _n_refs
            diagnostico["size_pedido"] = "não suportado neste motor"
        resp, erro_fatal = _chamar_gemini_geracao_texto(
            prompt_geracao, imagens_bytes=imagens_referencia, ref_layout=_ref_layout_bytes
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
        # OpenAI falhou mas Gemini funcionou — avisa para o usuário saber
        if erro_primario:
            st.warning(f"⚠️ {erro_primario} → usando Gemini como fallback.")

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
            img_bytes, _relato = _enq.quadrar(
                _cru.getvalue(), fundo_branco=_is_fundo_branco,
                lado_final=1200)
            if _relato and diagnostico is not None:
                diagnostico["enquadramento"] = _relato
            pil = _PILImage.open(_io.BytesIO(img_bytes)).convert("RGBA")

        pil = pil.resize((1200, 1200), _PILImage.LANCZOS)
        buf = _io.BytesIO()
        pil.save(buf, format="PNG")
        img_bytes = buf.getvalue()
    except Exception:
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
        _probs = _md.problemas(img_bytes, fundo_chapado=_is_fundo_branco,
                               ambientada=_is_ambientacao)
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



INSTRUCAO_REFERENCIA_LAYOUT = """
IMAGENS DE REFERÊNCIA DE LAYOUT — REGRAS ABSOLUTAS:
- As imagens de referência de layout mostram COMPOSIÇÃO, POSIÇÃO, ESTILO e ESTRUTURA visual
- O produto nessas imagens de referência NÃO É o produto a ser gerado — é apenas um exemplo de layout
- USE das referências: posicionamento, hierarquia de elementos, estilo de texto, uso de pessoas/cenários
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
    if isinstance(textos, str):
        linhas = [t.strip() for t in textos.splitlines() if t.strip()]
    else:
        linhas = [str(t).strip() for t in (textos or []) if str(t).strip()]
    if not linhas:
        return ""
    corpo = "\n".join(f"  {i}. {t}" for i, t in enumerate(linhas, 1))
    return (
        "\n━━━ TEXTO EXATO A ESCREVER (copie letra por letra) ━━━\n"
        + corpo + "\n"
        "REGRAS DESTE TEXTO, acima de qualquer outra instrução de texto:\n"
        "- Escreva EXATAMENTE estas palavras, letra por letra, com os mesmos "
        "acentos. Não reescreva, não resuma, não traduza, não melhore.\n"
        "- NÃO escreva nenhuma outra palavra na imagem além destas.\n"
        "- Tudo em português do Brasil. NENHUMA palavra em inglês na imagem, "
        "em lugar nenhum — nem em livro, tela, etiqueta, embalagem ou objeto "
        "do cenário. Texto de cenário que apareceria em inglês deve aparecer "
        "em português, ou não aparecer.\n"
        "- Se não couber tudo, escreva MENOS blocos — nunca invente palavra "
        "para preencher espaço.\n"
    )


MARCA_TEXTO_EXATO = "━━━ TEXTO EXATO A ESCREVER (copie letra por letra) ━━━"


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
    base = str(prompt or "")
    i = base.find(MARCA_TEXTO_EXATO)
    if i >= 0:
        # O bloco vai até a próxima seção "━━━" ou até o fim.
        j = base.find("━━━", i + len(MARCA_TEXTO_EXATO))
        # `find` acha o fecho da própria marca; pula os dois do cabeçalho.
        j = base.find("━━━", i + len(MARCA_TEXTO_EXATO) + 1)
        base = (base[:i].rstrip("\n") + ("\n\n" + base[j:] if j > 0 else "")).rstrip()
    return base + bloco_texto_exato(textos)


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
    if d.get("trava_do_produto"):
        linhas.append(f"\nTRAVA DO PRODUTO: {d['trava_do_produto']}")

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
        _composicao = plano_triagem.get("composicao", "").strip()
        plano_triagem_item_cena = plano_triagem.get("cena", "")
        _textos = [t for t in plano_triagem.get("textos", []) if t and str(t).strip()]
        # O TETO DA PECA CORTA A COPY AQUI, E NAO NO GERADOR.
        #
        # A triagem nao sabe quantos blocos o tipo comporta: ela escrevia 4
        # frases para um Close de 2 callouts, o bloco de texto exato mandava
        # escrever as 4 "letra por letra" e a regra de densidade dizia 2. Tres
        # ordens sobre a mesma coisa. Cortar aqui e a unica forma de as duas
        # que sobram concordarem.
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
            _cena = str(plano_triagem_item_cena or "").strip()
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
        if dados_descricao.get("diferenciais"):
            contexto_produto += f"Diferenciais principais: {dados_descricao['diferenciais'][:200]}\n"
        if dados_descricao.get("caracteristicas"):
            contexto_produto += f"Características: {dados_descricao['caracteristicas'][:200]}\n"
        if dados_descricao.get("uso"):
            contexto_produto += f"Uso principal: {dados_descricao['uso'][:100]}\n"

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
        nomes_str = ", ".join(refs_layout_nomes)
        bloco_refs = f"\nREFERÊNCIAS DE LAYOUT FORNECIDAS: {nomes_str}"
        if instrucao_layout:
            bloco_refs += f"\nO que cada referência representa: {instrucao_layout}"
        bloco_refs += f"\n{INSTRUCAO_REFERENCIA_LAYOUT}"

    # A MEDIDA DA OCUPACAO SAI DE `OCUPACAO`, E DE MAIS LUGAR NENHUM.
    # O mesmo numero alimenta esta linha e a linha de COMPOSITION do prompt
    # final em ingles — foi a divergencia entre as duas que mandava tres
    # numeros contrarios ao modelo na mesma mensagem.
    _protagonismo = (
        INSTRUCAO_PROTAGONISMO_CAPA if modo_fundo_do_tipo(tipo) == "branco"
        else INSTRUCAO_PROTAGONISMO
    ).format(faixa=ocupacao_em_portugues(tipo))
    _layout_marketing = INSTRUCAO_LAYOUT_MARKETING.format(
        blocos=blocos_em_portugues(tipo, _blocos_da_copy)
    )
    # A direcao de arte vem decidida da triagem e e HERDADA por esta peca. Sem
    # ela — plano antigo, triagem que falhou, geracao avulsa — o bloco sai
    # vazio e o padrao visual volta a mandar a peca deduzir, que e o
    # comportamento de antes e o menos ruim dos dois.
    _bloco_direcao = bloco_direcao_de_arte(direcao_arte)
    _padrao_visual = padrao_visual(direcao_arte)

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

{PADRAO_VISUAL_AMBIENTACAO}
{INSTRUCAO_PROTAGONISMO_AMBIENTE}
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
        itens = (st.session_state.get("img_triagem_plano") or {}).get("plano") or []
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


def _direcao_de_arte_da_sessao():
    """A direção de arte que a triagem decidiu para o produto aberto. {} se não há."""
    try:
        return (st.session_state.get("img_triagem_plano") or {}).get("direcao_de_arte") or {}
    except Exception:
        return {}


def prompt_para_regerar(tipo, instrucoes, dados_descricao, nome_produto):
    """O prompt de quem vai gerar UMA imagem de novo — com tudo o que o laço
    principal usa, e não com metade.

    Quem regera não pode receber menos do que quem gera: era essa a diferença
    entre a peça nascida na geração e a mesma peça refeita pelo botão ou pelo
    chat.
    """
    cfg = {}
    try:
        cfg = st.session_state.get("img_triagem_config") or {}
    except Exception:
        cfg = {}
    return montar_prompt_imagem(
        tipo, instrucoes, dados_descricao, nome_produto,
        refs_layout_nomes=cfg.get("refs_layout_nomes", []),
        instrucao_layout=cfg.get("instrucao_layout", ""),
        plano_triagem=plano_do_tipo(tipo),
        ambientacao=cfg.get("ambientacao", ""),
        direcao_arte=_direcao_de_arte_da_sessao(),
    )


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
    return f"""MS_FUNDO: {_modo}
MODO AJUSTE FINO — EDIÇÃO CIRÚRGICA DE IMAGEM EXISTENTE

A imagem fornecida é a imagem atual que deve ser editada.

MODIFICAÇÃO SOLICITADA — o único e exclusivo ponto a alterar:
{instrucao}

{INSTRUCAO_AJUSTE_FINO}

{INSTRUCAO_FIDELIDADE}
{_trava_cor_produto(cor_do_produto_atual() if cor_produto is None else cor_produto)}

O PRODUTO NÃO É PARTE DO AJUSTE — regra acima de qualquer instrução:
- O produto que está na imagem continua EXATAMENTE como está: mesma textura,
  mesmo acabamento, mesmo brilho, mesmos detalhes, mesma superfície.
- Pedra, strass, cravejado, relevo, textura, costura, grão: se está no produto
  da imagem, continua ali, no mesmo lugar e na mesma quantidade. Um urso
  cravejado de strass no corpo inteiro não pode sair liso.
- "Melhorar", "realçar", "deixar mais bonito" NUNCA autorizam redesenhar o
  produto. Se o pedido for sobre cor, luz ou fundo, mexa na cor, na luz ou no
  fundo — e no produto, em nada.
- Se a modificação pedida só puder ser feita alterando o produto, NÃO a faça:
  devolva a imagem como está. Entregar o produto errado é pior do que não
  atender ao pedido.

Reproduza a imagem fornecida com fidelidade absoluta, aplicando APENAS a modificação acima.
Trate qualquer elemento que não foi mencionado na instrução como intocável.
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
        # Campo separado, e booleano, porque `colateral` é texto livre: dava
        # para relatar "removeu o strass do corpo do urso" e o código seguir
        # adiante sem nunca ter lido aquilo. Pergunta fechada tem resposta que
        # o programa consegue obedecer.
        "produto_alterado": {
            "type": "boolean",
            "description": "true se o PRODUTO em si mudou — forma, textura, "
                           "acabamento, material, detalhes, peças, cor do "
                           "próprio produto. Strass, pedra, relevo ou textura "
                           "que sumiu, diminuiu ou apareceu conta como true. "
                           "Fundo, luz, cenário, texto e enquadramento NÃO "
                           "são o produto.",
        },
    },
    "required": ["feito", "o_que_saiu", "o_que_falta", "colateral",
                 "produto_alterado"],
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
            "Compare as duas imagens e responda duas coisas.\n\n"
            "1. A alteração pedida aconteceu? Julgue SÓ o que foi pedido. "
            "Seja rigoroso: mudança parcial, ou que só se percebe procurando, "
            "conta como NÃO feita. Se o pedido foi 'sem borda' e ainda há "
            "borda, é não. Se foi 'produto maior' e ele cresceu de forma "
            "imperceptível, é não.\n\n"
            "2. Mudou alguma coisa que NÃO foi pedida? Este é um modo de "
            "edição cirúrgica: o produto, o enquadramento, as cores, o texto e "
            "o fundo deviam continuar idênticos, exceto no ponto pedido. "
            "Produto redesenhado, objeto que apareceu ou sumiu, cena "
            "recomposta, texto reescrito — tudo isso é alteração colateral, e "
            "vale reportar mesmo que o pedido tenha sido atendido.\n\n"
            "3. O PRODUTO mudou? Responda em `produto_alterado`. Olhe a "
            "superfície de perto: strass, pedra, cravejado, relevo, textura, "
            "brilho, costura, acabamento. Um urso cravejado que ficou liso é "
            "produto alterado, mesmo que a cor pedida tenha melhorado. Fundo, "
            "luz, cenário, texto e enquadramento não são o produto.\n\n"
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


def revisar_texto(img, tipo, pedido="", gerar=None, prompt_base="",
                  rodadas=3, aviso=None):
    """Lê o texto escrito na imagem e refaz até sair certo. (imagem, relato).

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
        return img, None

    erros_1a = ""
    for n in range(1, max(1, rodadas) + 1):
        _diz(f"Lendo o texto escrito na imagem ({n}ª leitura)…")
        veredito, erro_conf = conferir_texto(img, pedido)
        if erro_conf:
            return img, {"ok": None, "rodadas": n, "erro": erro_conf,
                         "erros": erros_1a}
        if not veredito.get("tem_texto") or veredito.get("correto"):
            return img, {"ok": True, "rodadas": n, "erro": "",
                         "erros": erros_1a}
        erros = (veredito.get("erros") or "").strip()
        erros_1a = erros_1a or erros
        certo = (veredito.get("texto_correto") or "").strip()
        if n >= rodadas or not gerar or not certo:
            return img, {"ok": False, "rodadas": n, "erro": "",
                         "erros": erros or erros_1a}
        _diz(f"Texto errado ({erros[:60]}). Refazendo com as palavras certas…")
        nova_img, erro_g = gerar(trocar_texto_exato(prompt_base, certo))
        if erro_g or not nova_img:
            return img, {"ok": False, "rodadas": n, "erro": "",
                         "erros": erros or erros_1a}
        img = nova_img
    return img, {"ok": False, "rodadas": rodadas, "erro": "", "erros": erros_1a}


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
                            aviso=None, referencias=None):
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

    img_ok, rel_txt = revisar_texto(
        img, tipo,
        pedido=instrucao,
        gerar=_refazer,
        prompt_base=montar_prompt_ajuste_fino(
            "Corrija APENAS a ortografia do texto escrito na peça. Mantenha "
            "idêntico o produto, o enquadramento, as cores e o layout.", tipo),
        rodadas=2,
        aviso=aviso,
    )
    relato["texto"] = rel_txt
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
        _mexeu_no_produto = bool(veredito.get("produto_alterado"))
        if veredito.get("feito") and not _mexeu_no_produto:
            return nova, {"ok": True, "tentativas": n, "erro": "",
                          "falta": "", "saiu": veredito.get("o_que_saiu", ""),
                          "colateral": veredito.get("colateral", ""),
                          "historico": historico}

        # Pedido atendido MAS produto alterado não é sucesso — é a peça errada
        # com a cor certa. A conferência já enxergava isso e o código seguia
        # adiante mesmo assim: o urso de strass voltou liso, o veredito disse
        # que o corpo tinha ficado liso, e a tela anunciou "✅ atualizada".
        #
        # Aqui a próxima tentativa parte da imagem ORIGINAL e leva o que foi
        # destruído por escrito. Se nem assim der, volta a original: entregar
        # o produto errado é pior do que não atender ao pedido.
        if _mexeu_no_produto:
            _dano = (veredito.get("colateral") or "o produto foi alterado").strip()
            _diz("O produto mudou — refazendo sem tocar nele.")
            pedido = (f"{instrucao.strip()}\n\n"
                      f"ATENÇÃO — a tentativa anterior estragou o produto: "
                      f"{_dano}. O produto da imagem original tem de ser "
                      f"reproduzido EXATAMENTE como está, com a mesma "
                      f"textura, o mesmo acabamento e os mesmos detalhes de "
                      f"superfície. Faça a alteração pedida sem redesenhar o "
                      f"produto.")
            continue

        # Nao saiu. A critica vira a instrucao da proxima tentativa — e a
        # partir da imagem ORIGINAL, nao da tentativa falha: encadear falha
        # sobre falha afasta o resultado do produto a cada rodada.
        falta = (veredito.get("o_que_falta") or "").strip()
        pedido = (f"{instrucao.strip()}\n\n"
                  f"A tentativa anterior não conseguiu. O que ainda precisa "
                  f"acontecer: {falta}") if falta else instrucao

    ultimo = historico[-1] if historico else {}
    _estragou = bool(ultimo.get("produto_alterado"))
    return atual, {"ok": False, "tentativas": tentativas, "erro": "",
                   "falta": ((ultimo.get("o_que_falta") or "").strip()
                             if not _estragou else
                             "o ajuste só saiu alterando o produto, então a "
                             "imagem foi mantida como estava"),
                   "saiu": ultimo.get("o_que_saiu", ""),
                   "colateral": (ultimo.get("colateral") or "").strip(),
                   "produto_alterado": _estragou,
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
    falta = relato.get("falta") or "a alteração pedida não apareceu"
    return (f"❌ Imagem {num}: **não consegui fazer** em "
            f"{relato['tentativas']} tentativa(s). Falta: {falta}\n"
            f"   A imagem ficou como estava. Tente descrever de outro jeito, "
            f"dizendo o que DEVE existir em vez do que não deve.")


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
            _cfg_rf = st.session_state.get("img_triagem_config") or {}
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
        _cfg_rf = st.session_state.get("img_triagem_config") or {}
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
            _prompt = prompt_para_regerar(_tp, _ins, _dados_rf, _nome_rf)
            _r = {"img": None, "erro": None, "done": False}
            _b = st.progress(0.0, text=f"Refazendo a Imagem {_i + 1}…")
            import threading as _th_rf, time as _tm_rf
            _th_rf.Thread(target=_gerar_imagem_thread,
                          args=(_prompt, _fotos_rf, _r), daemon=True).start()
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
            galeria[_i]["bytes"] = _r["img"]
            galeria[_i]["aprovado"] = False
            st.session_state["img_galeria"] = list(galeria)
            _mudou_rf = True
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

            def _rodar_cmd(_ref=img_ref_cmd[0] if img_ref_cmd else None,
                           _ins=instrucao, _tp=tipo_alvo,
                           _rf=list(fotos_ref_aj or []), _r=_res_cmd):
                try:
                    _r["img"], _r["relato"] = ajustar_com_conferencia(
                        _ref, _ins, tipo=_tp, referencias=_rf,
                        aviso=lambda t: _r.__setitem__("fase", t))
                except Exception as _e:
                    _r["img"], _r["relato"] = None, {
                        "ok": False, "tentativas": 0, "erro": str(_e)[:160],
                        "falta": "", "colateral": ""}
                finally:
                    _r["done"] = True

            _threading_cmd.Thread(target=_rodar_cmd, daemon=True).start()
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
                    st.session_state["img_nome_produto"] = _cheio["nome_produto"]
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
                with st.spinner(f"Testando {_modelo}…"):
                    import time as _td
                    _t0_oai = _td.time()
                    try:
                        from openai import OpenAI as _OAITest
                        _oai_client = _OAITest(api_key=_oai_key)
                        _oai_resp = _oai_client.images.generate(
                            model=_modelo,
                            prompt="A small red circle on white background, minimal.",
                            n=1, size="1024x1024", quality="low",
                        )
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
    if nome_produto and not (dados_descricao and dados_descricao.get("medidas")):
        import triagem as _triagem_img
        _sel_triagem_key = "img_triagem_sel_idx"
        _busca_prev_key = "img_triagem_busca_prev"

        # Limpa seleção se nome_produto mudou
        if st.session_state.get(_busca_prev_key) != nome_produto:
            st.session_state[_sel_triagem_key] = None
            st.session_state[_busca_prev_key] = nome_produto

        _encontrados_t = _triagem_img.buscar_triagens_por_trecho(nome_produto)

        if len(_encontrados_t) == 1:
            # Variante única → auto-seleciona e completa specs faltantes
            _t = _encontrados_t[0]
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
            "Imagem a ajustar (JPG, PNG, WebP)",
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
                        aviso=lambda t: _r.__setitem__("fase", t))
                except Exception as _e:
                    _r["img"], _r["relato"] = None, {
                        "ok": False, "tentativas": 0, "erro": str(_e)[:160],
                        "falta": "", "colateral": ""}
                finally:
                    _r["done"] = True

            _threading_af.Thread(target=_rodar_af, daemon=True).start()
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
                st.session_state["img_nome_produto"] = nome_produto or "produto-ajustado"
                st.session_state["img_codigo"] = codigo_input
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
            "Fotos do produto (JPG, PNG, WebP)",
            type=None,  # qualquer formato — normalizar_imagem converte o que precisar
            accept_multiple_files=True,
            key="img_fotos_upload",
        )
        fotos_bytes, _nomes_ft, _av_ft, _er_ft = revisar_anexos(fotos_upload)
        mostrar_anexos(_av_ft, _er_ft)

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
                "Referências de ambientação (JPG, PNG, WebP)",
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
                "Imagens de referência de layout (JPG, PNG, WebP)",
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
                st.warning("Suba pelo menos uma foto do produto — é ela que garante fidelidade.")
                st.stop()

            try:
                with st.spinner("Analisando produto e montando o plano de criação..."):
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
                    else:
                        st.warning(
                            f"⚠️ Não consegui montar a prévia do plano, mas você pode gerar "
                            f"assim mesmo.\n\nDetalhe técnico: {_e_txt[:200]}"
                        )
                    plano = {
                        "plano": [
                            {"tipo": _t, "numero": _i + 1, "composicao": "",
                             "textos": [], "flags": [], "viavel": True,
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
        for item in itens_viaveis:
            flags = item.get("flags", [])
            with st.container(border=True):
                col_title, col_flag = st.columns([5, 1])
                col_title.markdown(f"**{item.get('numero', '')}. {item.get('tipo', '')}**")
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
                if flags:
                    with st.expander("Ver aviso", expanded=False):
                        st.warning(flags[0])

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

            col_cancelar, col_confirmar = st.columns(2)
            cancelar_clicado = col_cancelar.button("❌ Cancelar", use_container_width=True)
            confirmar_clicado = col_confirmar.button(
                "✅ Confirmar e gerar",
                type="primary",
                use_container_width=True,
                disabled=(n_viaveis == 0 or not _ciente),
            )

        if cancelar_clicado:
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
                            target=_gerar_imagem_thread,
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
                                target=_gerar_imagem_thread,
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

                        img_bytes, _rel_txt = revisar_texto(
                            img_bytes, tipo,
                            pedido=cfg.get("instrucoes_extras", ""),
                            gerar=_gerar_de_novo,
                            prompt_base=prompt_final,
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
                    st.session_state["img_nome_produto"] = cfg["nome_produto"]
                    st.session_state["img_codigo"] = cfg.get("codigo", "")
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
                    _threading_regen.Thread(
                        target=_gerar_imagem_thread,
                        args=(prompt_regen, fotos_orig, _res_regen),
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
                        st.session_state["img_galeria"][idx_ativo]["bytes"] = nova_img_regen
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

                    def _rodar_afg(_ref=imagem_ativa,
                                   _ins=instrucao_af_gal.strip(),
                                   _tp=galeria[idx_ativo].get("tipo"),
                                   _rf=list(st.session_state.get(
                                       "img_fotos_originais") or []),
                                   _r=_res_afg):
                        try:
                            _r["img"], _r["relato"] = ajustar_com_conferencia(
                                _ref, _ins, tipo=_tp, referencias=_rf,
                                aviso=lambda t: _r.__setitem__("fase", t))
                        except Exception as _e:
                            _r["img"], _r["relato"] = None, {
                                "ok": False, "tentativas": 0,
                                "erro": str(_e)[:160], "falta": "",
                                "colateral": ""}
                        finally:
                            _r["done"] = True

                    _threading_afg.Thread(target=_rodar_afg, daemon=True).start()
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

                barra_salvar.progress(1.0, text="Concluído!")
                link_pasta = f"https://drive.google.com/drive/folders/{pasta_destino_id}"

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
    _img, _rel = revisar_texto(b"x", "2 — Benefícios do produto", gerar=_gera)
    ok("texto certo passa de primeira, sem refazer",
       _rel["ok"] is True and _rel["rodadas"] == 1 and not _geradas)

    # O caso que deixou a peça errada chegar ao gestor: refez e ninguem releu.
    _geradas.clear()
    conferir_texto = _leitor(_ERRADO, _CERTO)
    _img, _rel = revisar_texto(b"x", "2 — Benefícios do produto", gerar=_gera,
                               prompt_base="BASE")
    ok("texto errado é refeito e RELIDO, e a segunda leitura aprova",
       _rel["ok"] is True and _rel["rodadas"] == 2 and _img == b"nova")
    ok("a refação recebe as palavras certas, letra por letra",
       len(_geradas) == 1 and "PERFEITO PARA ESCRITÓRIO" in _geradas[0]
       and _geradas[0].startswith("BASE"))

    _geradas.clear()
    conferir_texto = _leitor(_ERRADO, _ERRADO, _ERRADO)
    _img, _rel = revisar_texto(b"x", "2 — Benefícios do produto", gerar=_gera,
                               rodadas=3)
    ok("errado até o fim sai como errado, e não como “refeita, confira”",
       _rel["ok"] is False and _rel["rodadas"] == 3)
    ok("três leituras gastam duas refações, não três",
       len(_geradas) == 2)

    conferir_texto = _leitor("sem chave")
    _img, _rel = revisar_texto(b"x", "2 — Benefícios do produto", gerar=_gera)
    ok("falha de leitura NÃO vira aprovação", _rel["ok"] is None)
    ok("e a tela avisa em voz alta",
       "NÃO foi conferido" in texto_em_aviso(_rel))

    conferir_texto = _leitor(_ERRADO)
    _img, _rel = revisar_texto(b"x", "2 — Benefícios", gerar=None)
    ok("sem gerador, confere e reporta — não trava",
       _rel["ok"] is False and _img == b"x")

    conferir_texto = _leitor(_ERRADO)
    _img, _rel = revisar_texto(b"x", "1 — Capa do anúncio (fundo branco)",
                               gerar=_gera)
    ok("tipo sem texto nem é lido", _rel is None and _img == b"x")
    conferir_texto = _leitor(_CERTO)
    _img, _rel = revisar_texto(b"x", "Ajuste Fino — aumente o produto",
                               gerar=_gera)
    ok("peça já ajustada, sem número no rótulo, continua sendo lida",
       _rel is not None and _rel["ok"] is True)
    ok("pode_ter_texto só dispensa capa e ambientação",
       pode_ter_texto("Personalizado (descrevo o que quero)")
       and not pode_ter_texto("8 — Ambientação realista (sem texto)"))

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
    _pf = montar_prompt_ajuste_fino("deixe o dourado mais vivo", None, "prata")
    ok("o ajuste passou a levar a regra de fidelidade",
       "REGRA DE FIDELIDADE AO PRODUTO" in _pf)
    ok("e a trava de cor, que so a geracao tinha", "prata" in _pf.lower())
    ok("strass e textura estao nomeados na trava", "strass" in _pf.lower())

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
                    "produto_alterado": True}, ""
        return {"feito": True, "o_que_saiu": "cor melhorou",
                "o_que_falta": "", "colateral": "", "produto_alterado": False}, ""

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
                                "produto_alterado": True}, "")
    _img2, _rel2 = _ajustar_bruto(b"original", "melhore a cor", tentativas=2)
    ok("produto estragado ate o fim devolve a imagem ORIGINAL",
       _img2 == b"original")
    ok("e o relato diz que nao entregou, em vez de anunciar sucesso",
       _rel2["ok"] is False and _rel2.get("produto_alterado") is True)
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

    # ── O MODELO DE IMAGEM: o defeito que derrubou a geracao inteira ─────
    #
    # `gpt-image-2` nao existe. Estava escrito a mao em CINCO lugares, dava
    # 404 em toda chamada, o primario nunca gerava, e tudo caia no Gemini —
    # que nao aceita size nem input_fidelity. Dai "imagens extremamente
    # pequenas" e "fotos com margens laterais" na mesma tela.
    ok("o padrao e um modelo que existe",
       MODELO_IMAGEM_PADRAO == "gpt-image-2.5-sunburst")
    ok("e o nome antigo nao esta mais em lugar nenhum",
       "gpt-image-2" not in MODELOS_IMAGEM_CONHECIDOS)

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

    _achados = modelos_de_imagem_da_conta(_FakeCliente())
    ok("so os modelos de imagem entram",
       all("image" in m for m in _achados))
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

    conferir_texto = _real
    print("\nfalhas:", falhas)
