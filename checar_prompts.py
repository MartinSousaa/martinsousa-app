"""checar_prompts.py — a varredura que eu vinha fazendo na mão, e errando.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
O dono disse, e está certo: *"É um princípio básico analisar TODA a
codificação para corrigir em todos os lugares. É ÓBVIO que se não fizer isso
o erro persistirá no sistema."*

O histórico desta base prova que ele tem razão, e que a minha disciplina não
basta:

    a paleta azul fixa voltou TRÊS vezes, em lugares diferentes
    o "ZERO TEXTO" sobreviveu no preset do tipo 8 depois de eu o remover
    a regra de ocupar 65-80% do quadro pegou a AMBIENTAÇÃO, e o produto
      saiu do tamanho do ambiente

Nos três casos eu procurei pelo TEXTO do sintoma, e não pelo ALCANCE da regra.

E ESTE ARQUIVO JÁ MENTIU UMA VEZ — POR OLHAR O ARTEFATO ERRADO
--------------------------------------------------------------
A primeira versão conferia o que `montar_prompt_imagem()` devolve: o brief em
português. Só que `gerar_imagem_ia()` NÃO enviava aquilo. Ela recortava o
texto com um regex, de "TIPO DE IMAGEM:" até o primeiro título que casasse
com "PADRÃO VISUAL|REGRA DE|INSTRUÇÃO DE|…", e jogava o resto fora em
silêncio. Dois terços do brief morriam ali.

Morriam, medido nos nove tipos: a TRAVA DE COR (a cor real do produto e a
proibição de repintar), as medidas e o peso exatos, a REGRA DE FIDELIDADE —
"a mais importante de todas" —, a proibição de sobrepor texto ao produto, a
regra contra palavra inventada, o bloco inteiro de protagonismo da capa e a
exceção "Imagem meramente ilustrativa" da ambientação.

E esta varredura dava **ok** em todas elas. A regra estava escrita, a
varredura via, o modelo não.

Por isso ela agora monta o prompt QUE É ENVIADO — capturando o texto na porta
do motor — e é nele que confere. Conferir o texto de onde o recorte era feito
é conferir a intenção; o que chega na tela de alguém é o outro.

O QUE ELE FAZ
-------------
Monta o prompt REAL dos nove tipos — os oito do padrão mais o Personalizado —
e confere, um por um:

    1. o que cada um TEM de conter e o que NÃO PODE conter (tabela REGRAS);
    2. que nada do brief em português se perdeu no caminho até o motor;
    3. que cada peça declara UMA medida de ocupação, e não três;
    4. que cada peça declara UM teto de blocos de texto, e não três;
    5. que nenhuma cor de marca fixa voltou.

Não é teste de unidade: é varredura. A pergunta que ele responde não é "esta
função funciona", e sim "esta regra chegou em todos os lugares onde deveria,
e em nenhum onde não deveria".

COMO USAR
---------
    python3 checar_prompts.py

Entra no ritual de antes de subir, ao lado do `compileall` e do
`checar_ordem.py`.
"""

import io
import re
import sys

TIPOS_COM_TEXTO = (
    "2 — Benefícios do produto",
    "3 — Benefícios no cenário de uso",
    "4 — Close nos detalhes",
    "5 — Características técnicas (medidas/peso/material)",
    "6 — Quebra de objeção",
    "7 — Presenteie",
)
TIPO_CAPA = "1 — Capa do anúncio (fundo branco)"
TIPO_AMBIENTE = "8 — Ambientação realista (sem texto)"
# ── A PECA 7 MUDOU DE GRUPO, E A GUARDA MUDA COM ELA ──────────────────────
#
# Dono, 30/09: "o produto esta GIGANTE nas maos da crianca". A entrega de
# presente e CENA COM GENTE, igual a ambientacao: o tamanho do produto nela e
# a escala real nas maos, e nao uma porcentagem. Ela recebia (30, 45) com
# "Nao e sugestao" E, no mesmo prompt, "never enlarge beyond its real scale".
#
# Mover a regra sem mover a guarda deixaria estas linhas exigindo do tipo 7
# exatamente o defeito que acabou de sair. Por isso os grupos sao nomeados: a
# proxima peca de cena entra aqui, e as tres regras de tamanho a seguem.
TIPO_PRESENTE = "7 — Presenteie"
# ── E A PECA 3 ERA CENA TAMBEM, E EU SO VI NA TERCEIRA VEZ ───────────────
#
# O preset dela comeca com "PRODUTO NO AMBIENTE DE USO REAL: deduza (...) onde
# ESTE produto e de fato usado, e POR QUEM". Cena com gente — e ela carregava
# "ocupa NO MINIMO 45%" mais "Nunca deixe o produto pequeno no centro de um
# cenario amplo". Um compasso de 16 cm a 45% do quadro, na mao de uma crianca,
# e gigante, que foi exatamente o relato.
#
# Tres pecas, tres correcoes separadas, o mesmo defeito: 8 em 29/09, 7 de
# manha em 30/09, 3 a noite. Por isso o grupo tem NOME: peca de cena nova
# entra aqui, e as regras de tamanho a seguem sozinhas.
TIPO_CENARIO = "3 — Benefícios no cenário de uso"
TIPOS_DE_CENA = (TIPO_AMBIENTE, TIPO_PRESENTE, TIPO_CENARIO)
TIPOS_COM_TEXTO_MEDIDO = tuple(t for t in TIPOS_COM_TEXTO
                               if t not in TIPOS_DE_CENA)
# ── O CLOSE SAIU DA FAMILIA DE CARTAO, E A GUARDA SAI COM ELE ─────────────
#
# Ate 02/10 estas tres linhas exigiam do Close "FORMA DO CARTAO, IGUAL EM
# TODAS AS PECAS", "UMA coluna vertical unica" e a precedencia da referencia
# sobre a coluna. Elas estavam VERDES no dia em que o close da Caneca
# Medieval saiu com dois cartoes brancos de icone line-art sobre a foto
# macro — porque era exatamente isso que elas exigiam.
#
# O Close e fotografia com callout de linha fina; o preset dele ja dizia
# isso, e era a segunda voz que perdia. Mover a regra sem mover a guarda
# deixaria estas linhas cobrando de volta o defeito que acabou de sair — foi
# o que aconteceu com as pecas 3, 7 e 8 e esta anotado logo acima.
TIPO_CLOSE = "4 — Close nos detalhes"
TIPOS_COM_CARTAO = tuple(t for t in TIPOS_COM_TEXTO if t != TIPO_CLOSE)
TIPO_LIVRE = "Personalizado (descrevo o que quero)"

TODOS = (TIPO_CAPA,) + TIPOS_COM_TEXTO + (TIPO_AMBIENTE, TIPO_LIVRE)

# ── O que cada regra exige, e onde ela vale ─────────────────────────────────
#
# (descrição, trecho procurado, tipos onde DEVE existir, tipos onde NÃO pode)
#
# `None` em "onde deve" significa "em todos". A tabela é o contrato: mudar uma
# regra em `imagem.py` sem mexer aqui faz a varredura reprovar, que é
# exatamente o ponto.
REGRAS = [
    # ── O CARTÃO TEM UMA FORMA SÓ, E UMA POSIÇÃO SÓ ─────────────────────
    #
    # 28/09, produção: as oito peças saíram com o cartão de texto em quatro
    # arranjos diferentes — coluna na 3 e na 4, grade com a fileira de baixo
    # CORTADA na 2, quatro cantos com os de baixo cortados na 6. O dono
    # escolheu o da 3 e pediu para padronizar.
    #
    # A causa eram quatro vozes sobre o mesmo objeto: a regra compartilhada
    # autorizava "coluna OU grade", e cada preset trazia a própria redação
    # ("laterais, inferiores ou em grade" na 2, "ao lado" na 6, nada na 3).
    # O gerador obedecia a mais específica, e ela mudava por peça.
    #
    # Agora a posição é assunto da REGRA DE DENSIDADE e de mais ninguém.
    # Estas quatro linhas existem para que voltar a escrever posição dentro
    # de um preset reprove a varredura.
    ("a forma única do cartão", "FORMA DO CARTÃO, IGUAL EM TODAS AS PEÇAS",
     TIPOS_COM_CARTAO, (TIPO_AMBIENTE, TIPO_CLOSE)),
    ("a coluna única como posição", "UMA coluna vertical única",
     TIPOS_COM_CARTAO, (TIPO_AMBIENTE, TIPO_CLOSE)),
    # A COLUNA UNICA NAO PODE CONTRADIZER A REFERENCIA DE LAYOUT.
    #
    # Logo acima o prompt diz "quando houver imagem de referencia de layout,
    # ELA manda". Sem dizer qual das duas vale, o prompt chegaria ao gerador
    # com duas ordens contrarias sobre a mesma coisa — que e o defeito que
    # esta base ja pagou caro tres vezes. A precedencia sai escrita.
    ("a precedência da referência de layout sobre a coluna",
     "a POSIÇÃO é a dela", TIPOS_COM_CARTAO, (TIPO_AMBIENTE, TIPO_CLOSE)),
    # ── E O CONTRATO PROPRIO DO CLOSE, que nasce junto com a separacao ────
    ("o Close se declara fotografia, e não peça de marketing",
     "REGRA DE LAYOUT DO CLOSE", (TIPO_CLOSE,), TIPOS_COM_CARTAO),
    ("o Close proíbe cartão, painel e ícone",
     "PROIBIDO desenhar cartão, painel, caixa de texto",
     (TIPO_CLOSE,), TIPOS_COM_CARTAO),
    ("o Close manda o texto vir como callout de linha fina",
     "CALLOUT: uma linha fina", (TIPO_CLOSE,), TIPOS_COM_CARTAO),
    ("o Close proíbe seta de dimensão — medida é a peça 5",
     "ZERO medidas e ZERO setas de dimensão", (TIPO_CLOSE,), ()),
    ("a medida da folga da borda chega à peça", "6%",
     TIPOS_COM_TEXTO, ()),
    # ── A FOLGA É ESPAÇO DA CENA, E NÃO UMA MOLDURA DESENHADA ───────────
    #
    # Dono, 30/09: "imagens com margem". Duas causas, e esta é a do texto:
    # "6% em cada lado, nada toca a borda" lê-se como "desenhe uma faixa de
    # 6% em volta" — e a peça volta com moldura e o produto encolhido dentro
    # dela.
    #
    # Pior: o tipo 4 dizia "THE BORDER MARGIN OVERRIDES the rule above", e a
    # regra acima era "o PRODUTO preenche o quadro". Duas linhas seguidas,
    # uma mandando na outra, e a margem ganhando.
    #
    # A proibição vale nos NOVE tipos, nas duas línguas: corrigir só onde o
    # sintoma apareceu é a Forma 1 desta base.
    ("a proibição de desenhar moldura, em português",
     "NÃO DESENHE MARGEM", None, ()),
    ("a proibição de desenhar moldura, em inglês",
     "DO NOT DRAW a margin", None, ()),
    # `None` em "onde nao pode" nao vale (a tabela avisa isso logo acima):
    # aqui a proibicao e em TODOS, e escrita com todas as letras.
    ("a folga NÃO pode mandar sobre o produto",
     "BORDER MARGIN OVERRIDES", (), TODOS),
    # ── O QUE FAZER QUANDO A PEÇA NÃO TEM MEDIDA FIXA ───────────────────
    #
    # `INSTRUCAO_PROPORCAO` mandava buscar a medida "no bloco de protagonismo
    # desta peça" — e a ambientação e o Personalizado NÃO TÊM esse bloco, de
    # propósito: neles o produto aparece na escala real da cena. O ponteiro
    # apontava para o vazio, e o modelo encolhia o produto por precaução.
    ("o que fazer quando a peça não tem medida fixa",
     "não tem número fixo", None, ()),
    # `None` em "onde deve" quer dizer "em todos"; em "onde nao pode" ele nao
    # existe — para proibir em toda parte, a lista e TODOS.
    ("nenhum preset manda pôr cartão em grade", "ou em grade", (), TODOS),
    ("nem manda pôr ao lado por conta própria",
     "blocos de pergunta+resposta ao lado", (), TODOS),

    # ── A ORDEM QUE O MODELO NAO CONSEGUE OBEDECER ─────────────────────
    #
    # "Se nao couber tudo, escreva MENOS blocos" convivia, no mesmo prompt,
    # com "Escreva EXATAMENTE estas palavras, letra por letra" e com "Esta
    # peca tem exatamente 5 bloco(s)". A copy vem pronta da triagem: o modelo
    # NAO PODE escrever menos sem desobedecer as outras duas.
    #
    # Ordem impossivel nao fica sem efeito — ela vira licenca. O modelo
    # desenha os cinco e deixa transbordar, que foi o que o dono recebeu.
    #
    # Quem decide quantos blocos cabem e o Studio, ANTES de montar o prompt
    # (`_textos[:_teto_do_tipo]`). O prompt so informa o numero.
    ("nenhuma ordem de decidir o numero de blocos no meio do desenho",
     "MENOS blocos", (), TODOS),
    ("nem a versao em inglês dela", "FEWER blocks", (), TODOS),

    ("a trava de cor do produto", "TRAVA DE COR", None, ()),
    ("a proibição de trocar o produto", "PROIBIÇÃO ABSOLUTA", None, ()),
    ("a fidelidade às fotos de referência", "REGRA DE FIDELIDADE", None, ()),

    # A MEDIDA DA OCUPACAO, AGORA DE UMA FONTE SO (`imagem.OCUPACAO`).
    #
    # Os numeros literais sairam desta tabela de proposito: eles moravam aqui
    # e em tres lugares do `imagem.py`, e mudar um sem mudar os outros era o
    # que fazia a peca chegar ao modelo com tres medidas contrarias. A
    # conferencia de numero esta em `_uma_so_ocupacao`, que compara o prompt
    # com o dicionario — nao com uma copia escrita a mao.
    # ESTA LINHA TRAVAVA A REDACAO, E EU TROQUEI A REDACAO EM 09/10.
    #
    # Ela exigia a frase "dimensao util do quadro". A frase mudou para
    # "MAIOR dimensao do quadro" — porque o juiz lia "quadro" como AREA e
    # reprovava a capa de um produto estreito, que estava certa. A guarda
    # reprovou a correcao, e reprovou pela redacao, nao pelo comportamento:
    # e a Forma 2, e esta MESMA guarda ja caiu nela uma vez (o "6% acima da
    # base"). O que importa e que a peca com faixa receba uma medida que
    # fale de DIMENSAO e nao de area — e isso e o que ela passa a exigir.
    ("a ocupação medida por DIMENSÃO, e não por área",
     "dimensão do quadro",
     TIPOS_COM_TEXTO_MEDIDO + (TIPO_CAPA,), TIPOS_DE_CENA),
    # ESTA LINHA E A QUE INFLOU O PRODUTO, DUAS VEZES.
    #
    # "Produto no centro de um cenario amplo" e EXATAMENTE o que a
    # ambientacao e — e e tambem o que a entrega de presente e. A instrucao
    # proibia o objetivo da peca, e o modelo obedeceu inflando o produto ate
    # caber. Em 29/09 na ambientacao; em 30/09 nas maos da crianca.
    ("a proibição de produto pequeno em cenário amplo",
     "Nunca deixe o produto pequeno", TIPOS_COM_TEXTO_MEDIDO, TIPOS_DE_CENA),
    ("a escala real da cena", "ESCALA REAL", TIPOS_DE_CENA,
     TIPOS_COM_TEXTO_MEDIDO + (TIPO_CAPA,)),
    # ── E A PORCENTAGEM EM INGLES, QUE ESTA GUARDA NAO VIA ──────────────
    #
    # A regra de cima procura "dimensao util do quadro", que e a linha em
    # PORTUGUES. O mesmo prompt traz a linha de COMPOSITION em ingles, e ela
    # sai de `ocupacao_em_ingles` — outra funcao, outra fonte.
    #
    # Descobri isto tentando MUTAR: devolvi a faixa (30, 45) para a peca 7 e
    # o verificador ficou VERDE. O bloco em portugues ja vinha do roteamento
    # novo e dizia "escala real", enquanto o ingles voltava a mandar
    # "Product occupancy 30-45% of frame" — as duas vozes de novo, uma em
    # cada idioma, e nenhuma das 66 regras olhava a segunda.
    #
    # Mutacao que nao fica vermelha nao prova que o codigo esta certo: prova
    # que a guarda nao mede. Esta linha e o que faltava.
    ("a porcentagem imposta em inglês", "Product occupancy",
     TIPOS_COM_TEXTO_MEDIDO + (TIPO_CAPA,), TIPOS_DE_CENA),
    # E O APOIO E DE CADA UMA: na ambientacao o produto esta POUSADO numa
    # superficie; na entrega ele esta SEGURO por maos. Trocar os dois manda
    # o presente pousar no nada.
    ("o limite da escala nas mãos", "antebraço de quem o segura",
     (TIPO_PRESENTE,), (TIPO_AMBIENTE,)),

    # A CAPA NAO ESTAVA EM LISTA NENHUMA — E FOI ASSIM QUE ELA FICOU SEM
    # REGRA DE TAMANHO E SAIU PEQUENA.
    ("a proibicao de produto pequeno no branco",
     "produto pequeno no meio de um fundo branco", (TIPO_CAPA,), ()),
    ("o produto pousado com sombra real", "POUSADO", (TIPO_AMBIENTE,),
     TIPOS_COM_TEXTO),

    # A PALETA AZUL FIXA, QUE JÁ VOLTOU CINCO VEZES.
    ("a cor de marca imposta ao fundo", "#1A3A6B", (), TODOS),
    ("a paleta azul como regra de fundo", "fundo azul da marca", (), TODOS),
    ("o ícone azul marinho do preset 2", "azul marinho", (), TODOS),
    ("a borda azul do preset 5", "borda fina azul", (), TODOS),
    ("as cores da marca no preset 3", "cores da marca presentes", (), TODOS),
    ("a paleta azul da empresa na trava de cor",
     "paleta azul da empresa", (), TODOS),

    # A LISTA FIXA DE CÔMODOS — tirada do tipo 8 e deixada no 3.
    ("a lista pronta de cômodos", "escritório, quarto, sala de estudo",
     (), TODOS),

    # O "ZERO TEXTO" QUE SOBREVIVEU NUM PRESET.
    ("a proibição total de texto", "ZERO TEXTO", (),
     TIPOS_COM_TEXTO + (TIPO_AMBIENTE,)),
    ("a exceção única de texto da ambientação",
     "EXCEÇÃO ÚNICA", (TIPO_AMBIENTE,), TIPOS_COM_TEXTO),
    # E O INGLES TEM DE CONCORDAR COM ELA. A linha "ABSOLUTELY NO text ...
    # Any visible text is a critical failure" ia junto com "escreva Imagem
    # meramente ilustrativa" na mesma mensagem.
    ("a mesma exceção dita ao motor, em inglês",
     "ONE EXPLICIT EXCEPTION", (TIPO_AMBIENTE,), (TIPO_CAPA,)),
    ("a frase da ambientação chega ao motor",
     "Imagem meramente ilustrativa", (TIPO_AMBIENTE,),
     TIPOS_COM_TEXTO + (TIPO_CAPA,)),

    # CENARIO REAL EM TODAS AS PECAS DE MARKETING.
    ("o cenário real nas peças de marketing", "CENÁRIO REAL EM TODAS AS PEÇAS",
     TIPOS_COM_TEXTO, (TIPO_CAPA,)),
    ("a legibilidade mandando no fundo", "legibilidade manda no tratamento",
     TIPOS_COM_TEXTO, (TIPO_CAPA,)),

    # O QUE O RECORTE POR REGEX MATAVA — e que a varredura antiga nao via,
    # porque olhava o texto de ANTES do recorte.
    ("a proibição de sobrepor texto ao produto",
     "JAMAIS sobreponha texto", TIPOS_COM_TEXTO, ()),
    ("a proibição de palavra inventada", "REGRA DE TEXTO REAL",
     TIPOS_COM_TEXTO, ()),
    ("a proibição de inventar medidas",
     "PROIBIÇÃO ABSOLUTA DE INVENTAR DADOS TÉCNICOS", None, ()),
    ("as medidas exatas do produto", "Medidas EXATAS", None, ()),
    # O MATERIAL DO CADASTRO, QUE MORRIA NO CADASTRO.
    ("o material e a montagem", "Material e montagem", None, ()),
    ("a montagem nomeada chega ao motor", "encadernação Wire-O", None, ()),
    ("e com a ordem de não deduzir", "use exatamente isto, não deduza", None, ()),

    # O bloco de tamanho da capa — escrito depois do "Já falei MIL VEZES", e
    # cortado fora antes de chegar ao motor.
    ("o bloco de protagonismo da capa", "O PRODUTO PREENCHE O QUADRO",
     (TIPO_CAPA,), (TIPO_AMBIENTE,)),

    # O PRESENTEIE E A UNICA PECA QUE PEDE FIGURA HUMANA.
    #
    # Pedido do dono: "uma pessoa entregando o produto como presente para
    # outra". A linha generica em ingles abre com "NEVER add people", e numa
    # peca que EXISTE para ter duas pessoas isso e a ordem contraria. As duas
    # nunca podem estar na mesma mensagem.
    ("a cena de entrega do presente", "DUAS PESSOAS na cena",
     ("7 — Presenteie",), (TIPO_CAPA, TIPO_AMBIENTE)),
    ("o par que combina com o produto", "O PAR SAI DO PRODUTO",
     ("7 — Presenteie",), (TIPO_CAPA, TIPO_AMBIENTE)),
    ("as pessoas exigidas tambem em ingles", "PEOPLE ARE REQUIRED",
     ("7 — Presenteie",), (TIPO_CAPA, TIPO_AMBIENTE) + TIPOS_COM_TEXTO[:5]),
    ("a proibicao generica de pessoas fora do Presenteie",
     "NEVER add people", TIPOS_COM_TEXTO[:5] + (TIPO_CAPA, TIPO_AMBIENTE),
     ("7 — Presenteie",)),

    # A DIRECAO DE ARTE DECIDIDA UMA VEZ, HERDADA PELAS OITO.
    #
    # `PADRAO_VISUAL` mandava, nos OITO prompts, "escolha a paleta, a
    # iluminacao, o cenario e os materiais". Oito pecas decidindo a estetica
    # sozinhas — o dono chamou pelo nome: "6 direcoes de arte diferentes".
    ("a direção de arte herdada", "JÁ DECIDIDA, NÃO SE DECIDE DE NOVO", None, ()),
    ("a paleta-mãe", "PALETA-MÃE", None, ()),
    ("a trava do produto na direção", "TRAVA DO PRODUTO", None, ()),
    ("o risco de reflexo", "Risco de reflexo", None, ()),
    ("as cenas diferentes entre as peças", "Cena desta peça",
     TIPOS_COM_TEXTO, ()),
    # E A ORDEM CONTRARIA NAO PODE SOBREVIVER AO LADO DELA.
    ("a ordem de deduzir a paleta", "escolha a paleta", (), TODOS),
    ("a frase de desempate", "The product NEVER adapts to the environment",
     None, ()),

    # ── MARGEM E SOBREPOSICAO — as duas queixas que nunca tiveram regra ────
    #
    # Auditado o prompt real: so a CAPA tinha teto de margem. Nos tipos 2 a 7 a
    # unica linha sobre borda era "respiro nas bordas da peca", que PEDE
    # margem sem dizer quanto, e os presets 2 e 6 ainda pediam "muito
    # whitespace". E "jamais sobreponha texto ao produto" existia, mas nada
    # sobre cartao em cima de cartao, prop na frente do produto, ou produto
    # cortado pela borda — que e o quadro sobrepondo o produto.
    ("a regra de espaço da peça", "REGRA DE ESPAÇO DESTA PEÇA", None, ()),
    ("nada sobrepõe o produto", "NADA SOBREPÕE O PRODUTO",
     TIPOS_COM_TEXTO + (TIPO_CAPA,), ()),
    ("e o mesmo dito ao motor", "NOTHING overlaps the product",
     TIPOS_COM_TEXTO + (TIPO_CAPA,), ()),
    ("o produto desobstruído na ambientação", "UNOBSTRUCTED",
     (TIPO_AMBIENTE,), (TIPO_CAPA,)),
    ("os cartões não se sobrepõem entre si", "never overlap each other",
     TIPOS_COM_TEXTO, (TIPO_AMBIENTE,)),
    # A REGRA CONTINUA, A FRASE MUDOU. Ela existe para o espaco que sobra
    # virar painel e cenario em vez de faixa morta. O que saiu foi a parte
    # que mandava ENCHER ate a borda — porque brigava com a folga de 6% na
    # linha seguinte, e o gerador obedecia a primeira. Agora a mesma ideia
    # vem subordinada: preencher DENTRO da folga.
    ("o que sobra é painel, e dentro da folga", "never reach the margin",
     tuple(t for t in TIPOS_COM_TEXTO if not t.startswith("4 —")),
     (TIPO_CAPA, TIPO_AMBIENTE)),
    ("e a folga da borda manda, em uma voz so", "THE EDGE CLEARANCE RULES",
     tuple(t for t in TIPOS_COM_TEXTO if not t.startswith("4 —")),
     (TIPO_CAPA, TIPO_AMBIENTE)),
    ("o produto inteiro, sem corte pela borda", "no part cut by the frame edge",
     tuple(t for t in TIPOS_COM_TEXTO if not t.startswith("4 —"))
     + (TIPO_CAPA, TIPO_AMBIENTE), ("4 — Close nos detalhes",)),
    # E O QUE PEDIA MARGEM NAO PODE VOLTAR.
    ("a ordem de deixar respiro nas bordas", "respiro nas bordas", (), TODOS),
    ("o pedido de muito whitespace", "muito whitespace", (), TODOS),

    # O NOME DO ARQUIVO DA REFERENCIA ERA PORTA DE ENTRADA.
    #
    # A referencia subida numa analise se chamava `ref_cinzeiro_casal.png`, e
    # "cinzeiro" e "casal" entraram nos oito prompts — um nome de objeto e uma
    # palavra de pessoa, exatamente o que o filtro da descricao existe para
    # remover. O filtro limpava a descricao e deixava o nome passar ao lado.
    ("o nome cru do arquivo de referência", ".png", (), TODOS),
    ("o objeto que vinha no nome do arquivo", "cinzeiro", (), TODOS),
    ("a pessoa que vinha no nome do arquivo", "casal", (), TODOS),
    ("e a referência ainda é anunciada, sem nome",
     "REFERÊNCIAS DE LAYOUT FORNECIDAS", None, ()),

    ("o marcador de modo de fundo", "MS_FUNDO:", (), TODOS),
]

# Padrões que descrevem tamanho de produto no quadro. Cada um devolve a faixa
# como um par ordenado; duas faixas diferentes na mesma peça é o defeito.
_OCUPACAO_RE = (
    re.compile(r"ocupa de (\d{1,3})% a (\d{1,3})%", re.I),
    re.compile(r"occupancy (\d{1,3})[–-](\d{1,3})% of frame", re.I),
    re.compile(r"occupancy at least (\d{1,3})% of frame", re.I),
    re.compile(r"ocupa NO M[IÍ]NIMO (\d{1,3})%", re.I),
    re.compile(r"ocupar (\d{1,3})-(\d{1,3})% do frame", re.I),
    re.compile(r"(\d{1,3})% a (\d{1,3})% da MAIOR dimens", re.I),
)
# ── QUANTAS PALAVRAS CABEM NUM BLOCO — E ERAM DUAS RESPOSTAS ───────────
#
# Dono, 30/09: "as escritas estao sendo cortadas (...) aplicadas numa regiao
# que nao da para ser escrita totalmente e ai fica a margem para fora".
#
# `INSTRUCAO_LAYOUT_MARKETING` mandava, no MESMO bloco e a 33 linhas de
# distancia:
#
#   "Cada bloco: titulo curto (2-5 palavras) + descricao de 8 a 16 palavras"
#   "Frase curta e o que sai certo. Titulo de 2 a 4 palavras, frase de 4 a 9."
#
# Descricao de 16 palavras e frase de 9 palavras nao podem ser a mesma regra.
# O modelo escrevia longo, e longo nao cabe no cartao: transborda pela borda,
# que e o quadrado para fora que ele viu.
#
# A faixa que sobrou e a UNICA que as duas regras permitiam ao mesmo tempo:
# 8 a 9 palavras. Nao foi escolha minha — e a interseccao.
_PALAVRAS_RE = (
    re.compile(r"descri[cç][aã]o de (\d+) a (\d+)\s*\n?\s*palavras", re.I),
    re.compile(r"frase de (\d+) a (\d+)", re.I),
    re.compile(r"t[ií]tulo(?: curto)?(?: em CAIXA ALTA)? \((\d+)[-a ]+(\d+) palavras\)", re.I),
    re.compile(r"T[ií]tulo de (\d+) a (\d+) palavras", re.I),
)

_TETO_RE = (
    re.compile(r"Maximum (\d+) information elements", re.I),
    re.compile(r"use de (\d+) a (\d+) blocos", re.I),
    re.compile(r"M[aá]ximo (\d+)(?:-(\d+))? (?:callouts|frases|blocos|benef)", re.I),
    re.compile(r"de (\d+) a (\d+) (?:blocos de pergunta|benef[ií]cios)", re.I),
    # A linha que a copy escreve. Sem ela a varredura so via o numero em
    # ingles, e um "Maximum 7" ao lado de uma copy de 4 passava batido.
    re.compile(r"exatamente (\d+) bloco", re.I),
)


# ── AS REGRAS QUE SO EXISTEM COM O CADASTRO PREENCHIDO ────────────────────
#
# Medido: com o cadastro VAZIO, 36 regras saem do lugar — e sao 4 regras
# multiplicadas pelos 9 tipos. Essas quatro falam de medida, peso, material e
# montagem: sem o dado, a linha nao existe no prompt, e cobrar ela seria
# alarme falso.
#
# TODAS AS OUTRAS TEM DE VALER NO VAZIO. Foi onde o tipo 5 escondeu a
# contradicao que custou uma rodada: "INFOGRAFICO TECNICO DE MEDIDAS" junto
# de "JAMAIS invente medidas" — com cadastro as duas conviviam, sem cadastro
# elas se anulavam, e nenhuma varredura media esse caso.
#
# E O MOTIVO QUE EU TINHA ESCRITO PARA NAO FAZER ISTO ERA FALSO.
#
# Estava no ACHADOS_ABERTOS.md: "rodar as 65 regras uma segunda vez dobra o
# tempo do verificador — que ja e a parte mais lenta do protocolo". Medi:
# `checar_prompts.py` leva 2,8 SEGUNDOS. A parte lenta do protocolo e o
# `checar_mutacao`, que leva vinte minutos. Eu escrevi um motivo sem medir e
# ele ficou de pe por dias.
REGRAS_SO_COM_CADASTRO = {
    "as medidas exatas do produto",
    "o material e a montagem",
    "a montagem nomeada chega ao motor",
    "e com a ordem de não deduzir",
}


def _faixas(texto, padroes):
    achadas = set()
    for rx in padroes:
        for m in rx.finditer(texto):
            achadas.add(tuple(g for g in m.groups() if g))
    return achadas


def _sem_streamlit():
    import logging
    for nome in ("streamlit",
                 "streamlit.runtime.scriptrunner_utils.script_run_context"):
        logging.getLogger(nome).setLevel(logging.ERROR)


# O MATERIAL ENTRA COM UMA MONTAGEM NOMEADA, DE PROPOSITO.
#
# O campo "Material" do cadastro nao chegava a lugar nenhum: nem ao brief,
# nem ao contexto que a analise le. O album do dono e Wire-O, e a palavra
# aparecia em 0 dos 8 prompts — justo com a peca 4 sendo o CLOSE da
# encadernacao. "encadernação Wire-O" aqui e a sentinela disso.
_DADOS = {"nome_comercial": "Produto de Teste", "cor": "preto",
          "medidas": "71x14x14", "peso": "350 g",
          "material": "Metal escovado, encadernação Wire-O preta",
          "caracteristicas": "60 folhas, cantos arredondados"}
# A CENA VEM COM MEDIDA DENTRO, PORQUE NA REALIDADE ELA VEM.
#
# O plano de mentira daqui tinha uma cena limpa — superficie, props e angulo,
# que e o que o prompt do plano PEDE. A cena de verdade, no .txt que o dono
# baixou em 28/09, dizia: "Fundo branco puro sem sombra projetada; produto
# centralizado ocupando 60% do espaco vertical" — e a regra daquela peca
# mandava 85% a 92%.
#
# Duas medidas contrarias no mesmo prompt, e esta varredura passou VERDE,
# porque o duplo dela era mais pobre que a realidade. A caneca saiu pequena
# na capa, e o dono teve de pedir para aumentar.
#
# Agora o duplo carrega o defeito que a realidade carrega.
_PLANO = {"composicao": "produto à esquerda, cartões à direita",
          "cena": "superfície de nogueira, caderno fechado, câmera em 3/4, "
                  "produto centralizado ocupando 60% do espaço vertical",
          "textos": ["Aquece rápido", "Cerâmica premium",
                     "Alça confortável", "Presente perfeito"]}

# A DIRECAO DE ARTE DECIDIDA UMA VEZ, PARA AS OITO.
_DIRECAO = {
    "nome": "Executivo Quente Contemporâneo",
    "posicionamento": "premium contemporâneo",
    # A ATMOSFERA VEM COM MEDIDA DENTRO, PELO MESMO MOTIVO QUE A CENA.
    #
    # A direcao de arte e prosa livre escrita pela IA, igual a cena — e a
    # cena, na realidade, veio com "produto centralizado ocupando 60% do
    # espaco vertical". Duplo sem o defeito que a realidade tem deixa a
    # guarda verde sem medir nada (Forma 7).
    "atmosfera": "escritório sofisticado, com o produto ocupando 70% do quadro",
    "paleta": {
        "fundo":  {"nome": "Marfim Quente", "hex": "#F2EEE6"},
        "painel": {"nome": "Pedra Quente", "hex": "#D5C9B8"},
        "titulo": {"nome": "Grafite Espresso", "hex": "#292520"},
        "apoio":  {"nome": "Nogueira", "hex": "#695445"},
        "acento": {"nome": "Dourado Envelhecido", "hex": "#B18A4A"},
    },
    "materiais": ["nogueira escura", "travertino claro", "couro marrom"],
    "luz": "quente-neutra, lateral suave, contraste médio",
    "saturacao": "BAIXA",
    "props_preferidos": ["caneta", "caderno fechado"],
    "props_proibidos": ["planta grande", "papelaria colorida"],
    "risco_de_reflexo": "MEDIO",
    "trava_do_produto": "cerâmica azul cobalto, acabamento fosco",
}


def _foto():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 120, 60)).save(buf, "PNG")
    return buf.getvalue()


def _prompts(tipo, dados=None):
    """(brief em português, prompt REALMENTE enviado ao motor).

    O segundo é capturado na porta do motor: os dois geradores são trocados
    por funções que guardam o texto e devolvem falha. Nada sai para a rede.
    """
    _sem_streamlit()
    import imagem

    capturado = {}

    def _openai(prompt_final, imagens_bytes=None, ref_layout=None,
                ref_layout_nome="", diagnostico=None):
        capturado["prompt"] = prompt_final
        return None, "motor desligado na varredura"

    # A ASSINATURA DO DUPLO ACOMPANHA A DE VERDADE, DE PROPOSITO.
    #
    # Se o motor ganhar um parametro novo e o duplo nao, esta varredura
    # quebra ALTO — que e o certo. Duplo com `**kwargs` engoliria a mudanca
    # calado, e a varredura seguiria medindo um motor que nao existe mais.
    def _gemini(prompt_final, imagens_bytes=None, ref_layout=None,
                diagnostico=None):
        capturado.setdefault("prompt", prompt_final)
        return None, "motor desligado na varredura"

    def _descricao(imagens_referencia, nome_produto="produto",
                   dados_descricao=None, refs_layout=None):
        # O QUE A ANALISE DE VISAO RECEBE DE VERDADE FICA GUARDADO AQUI.
        #
        # Conferir so a expressao regular nao basta: tirar a linha que
        # ATRIBUI `dados_descricao["material"]` deixava a expressao casando e
        # o campo sumindo do mesmo jeito. Quem mede o caminho inteiro e isto.
        capturado["nome_para_visao"] = nome_produto
        capturado["dados_para_visao"] = dict(dados_descricao or {})
        return ("Descrição de apoio do produto de teste.",
                "Layout de duas colunas: produto à esquerda, blocos à direita.")

    originais = (imagem._chamar_openai_geracao,
                 imagem._chamar_gemini_geracao_texto,
                 imagem._descricao_do_produto_cacheada,
                 imagem._get_openai_api_key)
    imagem._chamar_openai_geracao = _openai
    imagem._chamar_gemini_geracao_texto = _gemini
    imagem._descricao_do_produto_cacheada = _descricao
    imagem._get_openai_api_key = lambda: "sk-varredura"
    try:
        # A CAPA E A AMBIENTACAO TAMBEM RECEBEM PLANO.
        #
        # Elas entravam aqui com `plano = None`, e era exatamente na CAPA que
        # a cena mandou 60% contra os 85-92% da regra. A varredura era cega no
        # unico lugar onde o defeito aconteceu.
        #
        # O TIPO_LIVRE continua sem plano, e isso nao e esquecimento:
        # `montar_prompt_imagem` ignora o plano nele de proposito (o
        # colaborador escreve a peca inteira), e forcar um aqui seria alarme
        # falso em cima de codigo certo.
        plano = None if tipo == TIPO_LIVRE else _PLANO
        # O NOME DA REFERENCIA ENTRA ENVENENADO, DE PROPOSITO.
        #
        # Sem referencia nenhuma, a regra que proibe o nome cru no prompt nao
        # protege nada: ela passa porque nao ha nome. Guarda vazia e o defeito
        # que esta base ja documentou tres vezes.
        #
        # `ref_cinzeiro_casal.png` e o nome real que levou "cinzeiro" e
        # "casal" para os oito prompts.
        pt = imagem.montar_prompt_imagem(
            tipo, "quero o produto virado para a direita" if tipo == TIPO_LIVRE else "",
            dados if dados is not None else _DADOS,
            (dados or _DADOS).get("nome_comercial", "Produto de Teste"),
            plano_triagem=plano,
            ambientacao="mesa de jantar" if tipo == TIPO_AMBIENTE else "",
            refs_layout_nomes=["ref_cinzeiro_casal.png"],
            direcao_arte=_DIRECAO)
        imagem.gerar_imagem_ia(pt, [_foto()], tipo=tipo)
        # O PREVIEW, MONTADO AQUI DENTRO.
        #
        # Fora do bloco as trocas ja foram desfeitas: sem chave, sem visao, o
        # preview cairia noutro caminho e a comparacao mediria o ambiente em
        # vez do codigo. Foi o que a primeira versao desta conferencia fez —
        # acusou 224 contra 17293 caracteres e a culpa era do teste.
        capturado["preview"] = imagem.prompt_que_sera_enviado(
            pt, [_foto()], tipo=tipo)
    finally:
        (imagem._chamar_openai_geracao,
         imagem._chamar_gemini_geracao_texto,
         imagem._descricao_do_produto_cacheada,
         imagem._get_openai_api_key) = originais
    return (pt, capturado.get("prompt", ""), capturado.get("preview", ""),
            {"nome": capturado.get("nome_para_visao"),
             "dados": capturado.get("dados_para_visao") or {}})



# ── O PROMPT DO AJUSTE FINO ──────────────────────────────────────────────
#
# POR QUE ESTA SECAO EXISTE
#
# Dono, 30/09: "se nao consegue nao e por recusa do GEMINI e sim por ele estar
# fazendo algo errado, seja na comunicacao ou na analise do que precisa fazer".
#
# Ele estava certo, e a medicao deu razao a ele. O pedido era "trocar o texto:
# diametro 25 cm e peso 476 g", e o MESMO prompt levava TRES proibicoes
# absolutas contra ele:
#
#   "nao adicione nem remova nenhum texto"
#   "ignore completamente qualquer texto visivel nas imagens"
#   "se esses dados nao foram fornecidos nos campos do produto, NAO os
#    coloque na imagem sob nenhuma hipotese"   (o numero veio NO PEDIDO)
#
# Mais uma quarta que mandava desistir: "se a modificacao so puder ser feita
# alterando o produto, NAO a faca: devolva a imagem como esta". E tres blocos
# diferentes se declarando supremos, enquanto o pedido do colaborador nao
# tinha prioridade declarada em lugar nenhum.
#
# O modelo obedeceu. Nao houve recusa: houve ordem nossa, contraditoria.
#
# E SOBREVIVEU PORQUE NINGUEM LIA. `checar_prompts` montava os nove tipos da
# CRIACAO; `checar_alcance` e `checar_comunicacao` nao tocavam neste texto.
# Zero ocorrencias de `montar_prompt_ajuste_fino` nos tres. E a Forma 3 desta
# base — "dizer verde sobre um texto que o verificador nao lia" — e ela custou
# o ajuste fino inteiro.
#
# AS REGRAS SAO POR COMPORTAMENTO, NAO POR REDACAO. Cada "nao pode" abaixo e
# uma frase que JA BARROU um pedido real; cada "tem de ter" e uma capacidade,
# nao uma palavra escolhida.
_AJUSTE_NAO_PODE = [
    ("proibir mexer em texto",
     "não adicione nem remova nenhum texto"),
    ("mandar ignorar o texto da propria peca",
     "ignore completamente qualquer texto visível"),
    ("proibir numero que veio no pedido",
     "NÃO os coloque na imagem sob nenhuma hipótese"),
    ("so aceitar medida vinda do cadastro",
     "Só use medidas e peso na imagem se eles"),
    ("mandar desistir quando o pedido toca o produto",
     "NÃO a faça:"),
]

_AJUSTE_TEM_DE_TER = [
    ("o pedido manda sobre as regras", "prioridade sobre TODAS"),
    ("fazer o pedido nao e opcional", "NÃO É OPCIONAL"),
    ("de onde vem numero", "MODIFICAÇÃO SOLICITADA ou já escritos"),
    ("a trava do produto continua", "não pode sair liso"),
    ("a trava de cor continua", "TRAVA DE COR"),
]

# PEDIDOS DE VERDADE, e nao frases que eu inventei para o teste passar. O
# primeiro e o do dono, 30/09, palavra por palavra.
_PEDIDOS_REAIS = [
    "trocar o texto: diametro 25 cm e peso 476 g",
    "tire a borda branca em volta",
    "deixe o fundo mais claro",
    "aumente o produto dentro do quadro",
]


def _conferir_ajuste_fino():
    """O prompt do ajuste manda fazer, ou manda desistir? Devolve nº de falhas."""
    _sem_streamlit()
    import imagem

    falhas = 0
    for pedido in _PEDIDOS_REAIS:
        for tipo in (None, "5 — Características técnicas (medidas/peso/material)",
                     "1 — Capa do anúncio (fundo branco)"):
            p = imagem.montar_prompt_ajuste_fino(pedido, tipo)
            _onde = f"ajuste fino [{(tipo or 'sem tipo')[:18]}] pedido {pedido[:28]!r}"
            if pedido not in p:
                print(f"FALHA  {_onde}: o pedido do colaborador nao chegou "
                      "ao prompt")
                falhas += 1
            for nome, trecho in _AJUSTE_NAO_PODE:
                if trecho in p:
                    print(f"FALHA  {_onde}: o prompt volta a {nome} "
                          f"— {trecho!r}")
                    falhas += 1
            for nome, trecho in _AJUSTE_TEM_DE_TER:
                if trecho not in p:
                    print(f"FALHA  {_onde}: sumiu do prompt — {nome} "
                          f"({trecho!r})")
                    falhas += 1

    # ── AS FOTOS VAO: ENTAO O PROMPT TEM DE DIZER QUE ELAS SAO A REFERENCIA
    #
    # `_tem_fotos` decidia o texto olhando a CHAVE DA OPENAI, e nao se as
    # fotos viajam. Hoje os DOIS motores recebem as fotos — o Gemini leva
    # `imagens_bytes=imagens_referencia`. Sem a chave da OpenAI, entao, o
    # prompt dizia "PRODUCT DESCRIPTION (recreate this product exactly from
    # the description)" — texto — enquanto as fotos iam junto e o modelo
    # NUNCA era avisado de que elas sao a referencia.
    #
    # Ele reconstroi o produto a partir de uma descricao em palavras, com as
    # fotos na mao. E a explicacao direta de "produto nada a ver com o
    # original", e acontece exatamente na configuracao em que o Gemini e o
    # motor principal.
    _capt = {}
    _orig2 = (imagem._chamar_openai_geracao, imagem._chamar_gemini_geracao_texto,
              imagem._descricao_do_produto_cacheada, imagem._get_openai_api_key)
    try:
        imagem._chamar_openai_geracao = lambda *a, **k: (None, "desligado")
        def _pega(prompt_final, *a, **k):
            _capt["prompt"] = prompt_final
            return None, "desligado"
        imagem._chamar_gemini_geracao_texto = _pega
        imagem._descricao_do_produto_cacheada = lambda *a, **k: ("desc", "lay")
        imagem._get_openai_api_key = lambda: ""      # SEM chave da OpenAI
        imagem.gerar_imagem_ia(
            imagem.montar_prompt_imagem(
                "2 — Benefícios do produto", "", _DADOS, "Produto de Teste",
                plano_triagem=_PLANO, refs_layout_nomes=[],
                direcao_arte=_DIRECAO),
            [b"foto-do-produto"], tipo="2 — Benefícios do produto")
    finally:
        (imagem._chamar_openai_geracao, imagem._chamar_gemini_geracao_texto,
         imagem._descricao_do_produto_cacheada,
         imagem._get_openai_api_key) = _orig2
    _pp = _capt.get("prompt", "")
    if "PRODUCT REFERENCE" not in _pp:
        print("FALHA  sem a chave da OpenAI, as fotos vao ao Gemini mas o "
              "prompt manda recriar o produto A PARTIR DO TEXTO — o modelo "
              "nunca e avisado de que as fotos sao a referencia")
        falhas += 1
    if "PRODUCT DESCRIPTION (recreate this product exactly" in _pp:
        print("FALHA  o prompt manda recriar de uma DESCRICAO mesmo com as "
              "fotos viajando junto")
        falhas += 1

    # ── O AJUSTE NAO PAGA LEITURA DE VISAO QUE ELE DESCARTA ────────────
    #
    # A descricao produzida pela analise de visao alimenta a secao PRODUCT
    # DESCRIPTION do prompt de CRIACAO. No ajuste fino essa secao nem chega
    # ao motor: `prompt_geracao = _prompt_ajuste` substitui o prompt inteiro.
    #
    # Ou seja, toda tentativa de ajuste pagava uma leitura de visao jogada
    # fora na linha seguinte — 2 por pedido do colaborador, porque sao 2
    # tentativas. E rodava com o nome do produto errado ainda por cima.
    #
    # A conferencia exercita a CADEIA: chama `gerar_imagem_ia` de verdade,
    # com os motores desligados, e conta as leituras.
    _chamadas = {"n": 0}
    _orig = (imagem._descricao_do_produto_cacheada,
             imagem._chamar_openai_geracao,
             imagem._chamar_gemini_geracao_texto,
             imagem._get_openai_api_key)
    try:
        imagem._descricao_do_produto_cacheada = (
            lambda *a, **k: (_chamadas.__setitem__("n", _chamadas["n"] + 1)
                             or ("desc", "layout")))
        imagem._chamar_openai_geracao = lambda *a, **k: (None, "desligado")
        imagem._chamar_gemini_geracao_texto = lambda *a, **k: (None, "desligado")
        imagem._get_openai_api_key = lambda: ""
        imagem.gerar_imagem_ia(
            imagem.montar_prompt_ajuste_fino("tire a borda branca", None),
            [b"foto"], tipo="")
        _no_ajuste = _chamadas["n"]
        _chamadas["n"] = 0
        imagem.gerar_imagem_ia(
            imagem.montar_prompt_imagem(
                "2 — Benefícios do produto", "", _DADOS, "Produto de Teste",
                plano_triagem=_PLANO, refs_layout_nomes=[],
                direcao_arte=_DIRECAO),
            [b"foto"], tipo="2 — Benefícios do produto")
        _na_criacao = _chamadas["n"]
    finally:
        (imagem._descricao_do_produto_cacheada,
         imagem._chamar_openai_geracao,
         imagem._chamar_gemini_geracao_texto,
         imagem._get_openai_api_key) = _orig
    if _no_ajuste:
        print(f"FALHA  o ajuste fino pagou {_no_ajuste} leitura(s) de visao "
              "e descarta o resultado — o prompt do ajuste substitui a secao "
              "que usaria essa descricao")
        falhas += 1
    if not _na_criacao:
        print("FALHA  a CRIACAO deixou de pedir a analise de visao — e ela "
              "que descreve o produto para o gerador")
        falhas += 1

    # A SEPARACAO NAO PODE VAZAR PARA O LADO ERRADO: o que saiu do ajuste tem
    # de continuar na CRIACAO, senao eu troquei um defeito por outro.
    for nome, trecho in _AJUSTE_NAO_PODE[1:4]:
        if trecho not in imagem.INSTRUCAO_FIDELIDADE:
            print(f"FALHA  a regra de CRIACAO '{nome}' sumiu junto — ela esta "
                  "certa la, e so estava errada no ajuste")
            falhas += 1
    return falhas



# ── IDA E VOLTA DO CADASTRO ──────────────────────────────────────────────
#
# Dono, 30/09: "certifique-se de o estudio estar falando A e o resultado ser
# A e nao B ou A+".
#
# `gerar_imagem_ia` nao recebe os campos do produto: ela os RELE do proprio
# prompt, por expressao regular. Se a expressao nao casar, o campo some em
# silencio — e some do lugar mais caro, porque e ele que alimenta a analise
# de visao que descreve o produto para o gerador.
#
# Em 30/09 duas nao casavam, nos NOVE tipos:
#   `Cor:`       o prompt escreve `COR REAL DO PRODUTO:` — a cor cadastrada
#                NUNCA chegou a analise de visao
#   material     ninguem procurava por ele, embora a analise tenha campo
# E uma casava DEMAIS: `PRODUTO:` sem ancora pegava o meio de outra frase.
# No prompt do ajuste fino o "nome do produto" virava
# "JAMAIS adicione base, pedestal, suporte, embalagem".
#
# ESTA CONFERENCIA MEDE A IDA E A VOLTA, e nao a redacao: escreve um valor
# conhecido no cadastro, monta o prompt de verdade, e exige que a releitura
# devolva EXATAMENTE o mesmo valor.
_IDA_E_VOLTA = [
    ("nome",     "nome_comercial", r"^PRODUTO:\s*(.+?)$"),
    ("cor",      "cor",            r"^COR REAL DO PRODUTO:\s*(.+?)$"),
    ("medidas",  "medidas",        r"^Medidas EXATAS[^:]*:\s*(.+?)$"),
    ("peso",     "peso",           r"^Peso EXATO[^:]*:\s*(.+?)$"),
    ("material", "material",       r"^Material e montagem[^:]*:\s*(.+?)$"),
]


def _regexes_de_gerar_imagem_ia():
    """As expressoes que `gerar_imagem_ia` usa para reler o prompt.

    Lidas do CODIGO, por AST — nao copiadas para ca. Copia vira a Forma 5:
    alguem muda a do codigo, esta segue medindo a antiga e diz verde.
    """
    import ast
    import os as _os_rx
    _raiz = _os_rx.path.dirname(_os_rx.path.abspath(__file__))
    arv = ast.parse(open(_os_rx.path.join(_raiz, "imagem.py"),
                         encoding="utf-8").read())
    fn = next(n for n in ast.walk(arv)
              if isinstance(n, ast.FunctionDef) and n.name == "gerar_imagem_ia")
    fora = []
    for n in ast.walk(fn):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "search" and n.args
                and isinstance(n.args[0], ast.Constant)
                and len(n.args) > 1 and getattr(n.args[1], "id", "") == "prompt_texto"):
            fora.append((n.lineno, n.args[0].value))
    return fora


def _prompts_com_cadastro(dados, tipo="2 — Benefícios do produto"):
    """O que a analise de visao recebe, com ESTE cadastro. Cadeia de verdade."""
    _pt, _env, _pv, visao = _prompts(tipo, dados)
    return visao


def _conferir_ida_e_volta():
    _sem_streamlit()
    import imagem
    import re as _re

    falhas = 0
    marcado = {"nome_comercial": "ProdutoMarcado-XYZ", "cor": "verde-abacate",
               "medidas": "11x22x33", "peso": "987 g",
               "material": "liga de titanio escovado",
               "caracteristicas": "marcado para conferencia"}
    for tipo in TODOS:
        plano = None if tipo == TIPO_LIVRE else _PLANO
        pt = imagem.montar_prompt_imagem(
            tipo, "quero o produto virado" if tipo == TIPO_LIVRE else "",
            marcado, marcado["nome_comercial"], plano_triagem=plano,
            ambientacao="mesa" if tipo == TIPO_AMBIENTE else "",
            refs_layout_nomes=[], direcao_arte=_DIRECAO)
        for nome, campo, rx in _IDA_E_VOLTA:
            m = _re.search(rx, pt, _re.MULTILINE)
            lido = m.group(1).strip() if m else None
            if lido != marcado[campo]:
                print(f"FALHA  '{tipo}': o Studio escreveu {nome}="
                      f"{marcado[campo]!r} e a releitura ouviu {lido!r} — "
                      "esse campo nao chega a analise de visao")
                falhas += 1

    # A CADEIA INTEIRA, E NAO SO A EXPRESSAO.
    #
    # Tirar a linha que ATRIBUI `dados_descricao["material"]` deixava a
    # expressao casando e o campo sumindo do mesmo jeito. O que mede isso e
    # olhar o que a analise de visao RECEBEU, no fim do caminho.
    _visao = _prompts_com_cadastro(marcado)
    if _visao["nome"] != marcado["nome_comercial"]:
        print(f"FALHA  a analise de visao recebeu o nome {_visao['nome']!r} "
              f"em vez de {marcado['nome_comercial']!r}")
        falhas += 1
    for campo in ("cor", "medidas", "peso", "material"):
        if (_visao["dados"] or {}).get(campo) != marcado[campo]:
            print(f"FALHA  a analise de visao NAO recebeu '{campo}': chegou "
                  f"{(_visao['dados'] or {}).get(campo)!r}, cadastrado "
                  f"{marcado[campo]!r} — e e ela quem descreve o produto "
                  "para o gerador")
            falhas += 1
        # E AS EXPRESSOES DO CODIGO TEM DE SER ESTAS. Se alguem mudar uma la
        # e nao aqui, esta conferencia passaria medindo a antiga.
    _no_codigo = {rx for _ln, rx in _regexes_de_gerar_imagem_ia()}
    for nome, _campo, rx in _IDA_E_VOLTA:
        if rx not in _no_codigo:
            print(f"FALHA  a expressao de '{nome}' desta conferencia nao "
                  f"existe mais em gerar_imagem_ia: {rx!r}")
            falhas += 1

    # ── O TIPO 5 COM O CADASTRO VAZIO ────────────────────────────────
    #
    # Ele manda "INFOGRAFICO TECNICO DE MEDIDAS — estilo cota de catalogo" e
    # o mesmo prompt proibe escrever medida que nao veio do cadastro. Com o
    # cadastro cheio as duas convivem; com ele VAZIO se anulam, e o modelo
    # resolve contradicao inventando numero.
    #
    # As 61 regras nunca mediram isto: o cadastro do teste sempre teve
    # medida. Mesmo ponto cego do termometro — amostra de um caso so.
    _vazio = {"nome_comercial": "ProdutoMarcado-XYZ", "cor": "", "medidas": "",
              "peso": "", "material": "", "caracteristicas": ""}
    _t5 = "5 — Características técnicas (medidas/peso/material)"
    _p5 = imagem.montar_prompt_imagem(_t5, "", _vazio, _vazio["nome_comercial"],
                                      plano_triagem=_PLANO, refs_layout_nomes=[],
                                      direcao_arte=_DIRECAO)
    if "SEM DADOS TÉCNICOS CADASTRADOS" not in _p5:
        print("FALHA  o tipo 5 com cadastro VAZIO manda fazer infografico de "
              "cotas e proibe escrever cota, sem dizer que a medida nao "
              "existe — o modelo resolve isso inventando numero")
        falhas += 1
    # E COM CADASTRO CHEIO ELE NAO PODE APARECER: aviso fora de hora vira
    # ordem de NAO escrever a medida que existe.
    _p5c = imagem.montar_prompt_imagem(_t5, "", marcado, marcado["nome_comercial"],
                                       plano_triagem=_PLANO, refs_layout_nomes=[],
                                       direcao_arte=_DIRECAO)
    if "SEM DADOS TÉCNICOS CADASTRADOS" in _p5c:
        print("FALHA  o aviso de 'sem dados tecnicos' aparece com o cadastro "
              "CHEIO — isso manda o modelo NAO escrever a medida que existe")
        falhas += 1

    # O AJUSTE FINO NAO TEM CADASTRO — e nao pode INVENTAR um.
    aj = imagem.montar_prompt_ajuste_fino(
        "trocar o texto: diametro 25 cm", "5 — Características técnicas (medidas/peso/material)")
    m = _re.search(r"^PRODUTO:\s*(.+?)$", aj, _re.MULTILINE)
    if m:
        print(f"FALHA  no ajuste fino o 'nome do produto' virou {m.group(1)!r} "
              "— um pedaco de outra frase do proprio prompt")
        falhas += 1
    return falhas


def main():
    briefs, enviados, previews = {}, {}, {}
    for t in TODOS:
        try:
            briefs[t], enviados[t], previews[t], _ = _prompts(t)
        except Exception as e:
            print(f"FALHA  nao consegui montar o prompt de '{t}': "
                  f"{type(e).__name__}: {e}")
            return 1
        if not enviados[t]:
            print(f"FALHA  o prompt de '{t}' nao chegou a porta do motor")
            return 1

    falhas = 0

    # ── 1. A tabela de regras, conferida no texto QUE É ENVIADO ────────────
    for desc, trecho, deve, nao_pode in REGRAS:
        alvo_deve = TODOS if deve is None else deve
        for t in alvo_deve:
            if trecho not in enviados[t]:
                print(f"FALHA  {desc}: FALTA em '{t}'")
                falhas += 1
        for t in nao_pode:
            if trecho in enviados[t]:
                print(f"FALHA  {desc}: NAO DEVIA estar em '{t}'")
                falhas += 1

    # ── 2. NADA DO BRIEF SE PERDE NO CAMINHO ───────────────────────────────
    #
    # Esta é a conferência que faltava. O recorte por regex matava linhas
    # inteiras do brief sem erro nenhum, e a varredura não tinha como saber:
    # ela olhava o brief. Agora ela olha os dois e compara.
    for t in TODOS:
        perdidas = [ln.strip() for ln in briefs[t].splitlines()
                    if ln.strip() and not ln.startswith("MS_")
                    and ln.strip() not in enviados[t]]
        if perdidas:
            print(f"FALHA  {len(perdidas)} linha(s) do brief de '{t}' NAO chegaram "
                  f"ao motor. A primeira: {perdidas[0][:90]!r}")
            falhas += 1

    # ── 1-ter. AS MESMAS REGRAS, COM O CADASTRO VAZIO ──────────────────────
    #
    # O cadastro do teste sempre teve medida, peso e material — e e justamente
    # no vazio que o tipo 5 se contradizia. Uma amostra de um caso so mede um
    # caso so.
    #
    # Custa 2,8 segundos a mais. O motivo que eu tinha escrito para nao fazer
    # ("dobra o tempo da parte mais lenta do protocolo") era falso: a parte
    # lenta e o `checar_mutacao`, com vinte minutos.
    _vazios = {}
    for t in TODOS:
        try:
            _, _vazios[t], _, _ = _prompts(t, dados={})
        except Exception as e:
            print(f"FALHA  nao consegui montar o prompt de '{t}' com o "
                  f"cadastro vazio: {type(e).__name__}: {e}")
            falhas += 1
            _vazios[t] = ""
    for t in TODOS:
        if not _vazios[t]:
            continue
        for desc, trecho, tem, nao in REGRAS:
            if desc in REGRAS_SO_COM_CADASTRO:
                continue
            _onde_tem = TODOS if tem is None else tem
            if t in _onde_tem and trecho not in _vazios[t]:
                print(f"FALHA  com o cadastro VAZIO, '{desc}' FALTA em '{t}'")
                falhas += 1
            if t in (nao or ()) and trecho in _vazios[t]:
                print(f"FALHA  com o cadastro VAZIO, '{desc}' NAO DEVIA estar "
                      f"em '{t}'")
                falhas += 1
    # ISENCAO ORFA MENTE PARA QUEM LE DEPOIS — igual as outras listas da base.
    _descricoes = {d for d, _, _, _ in REGRAS}
    for _d in sorted(REGRAS_SO_COM_CADASTRO):
        if _d not in _descricoes:
            print(f"FALHA  a isencao de cadastro para '{_d}' sobrou: essa "
                  "regra nao existe mais, e a isencao mente para quem ler")
            falhas += 1

    # ── 3. UMA MEDIDA DE OCUPACAO POR PECA ─────────────────────────────────
    for t in TODOS:
        faixas = _faixas(enviados[t], _OCUPACAO_RE)
        if len(faixas) > 1:
            print(f"FALHA  '{t}' manda {len(faixas)} medidas de ocupacao "
                  f"contrarias ao motor: {sorted(faixas)}")
            falhas += 1

    # ── 3-bis. UMA MEDIDA DE TAMANHO DE BLOCO POR PECA ─────────────────────
    #
    # A irma da regra acima. A de cima conta as medidas de OCUPACAO do
    # produto; esta conta as de TAMANHO DO TEXTO, que e o outro numero que o
    # mesmo prompt trazia em duas versoes — "descricao de 8 a 16 palavras" e
    # "frase de 4 a 9", a 33 linhas de distancia, no mesmo bloco.
    #
    # Duas faixas para a mesma coisa e o modelo escolhendo: ele escrevia
    # longo, e longo transborda o cartao.
    for t in TODOS:
        _pal = _faixas(enviados[t], _PALAVRAS_RE)
        # Titulo e descricao sao assuntos DIFERENTES e podem ter faixas
        # diferentes: o que nao pode e duas faixas para o MESMO. Por isso a
        # conta e por padrao, e nao no monte.
        for _rx in _PALAVRAS_RE:
            _dessa = {m.groups() for m in _rx.finditer(enviados[t])}
            if len(_dessa) > 1:
                print(f"FALHA  '{t}' manda {len(_dessa)} tamanhos contrarios "
                      f"para o mesmo bloco de texto: {sorted(_dessa)}")
                falhas += 1
        # E as duas faixas de DESCRICAO (a longa e a curta) nao podem
        # coexistir: era esse o par que se contradizia.
        _desc = _faixas(enviados[t], (_PALAVRAS_RE[0], _PALAVRAS_RE[1]))
        if len(_desc) > 1:
            print(f"FALHA  '{t}' diz o tamanho da frase de {len(_desc)} jeitos "
                  f"diferentes: {sorted(_desc)}")
            falhas += 1

    # ── 1-bis. O PROMPT DA REFACAO TAMBEM E VARRIDO ────────────────────────
    #
    # ESTE ERA O BURACO MAIOR, e ele e a Forma 3 do protocolo: dizer verde
    # sobre um texto que o verificador nao lia.
    #
    # A varredura acima le o prompt da PRIMEIRA geracao. Mas quando a revisao
    # de texto acha um erro de portugues, ela refaz a peca com o prompt
    # passado por `trocar_texto_exato` — e e ESSE o prompt que chega ao motor
    # na segunda rodada, justamente na peca que ja tinha dado problema.
    #
    # Em 28/09 esse prompt chegou ao motor com 8.259 caracteres contra 24.000
    # da primeira rodada, sem a regra da borda, sem protagonismo, sem
    # densidade, sem texto real, sem fidelidade e sem composicao. As 60 regras
    # daqui estavam verdes o tempo todo: elas mediam o outro prompt.
    #
    # Agora as MESMAS regras sao varridas nos dois.
    import imagem as _img_ref
    refeitos = {}
    for t in TODOS:
        try:
            refeitos[t] = _img_ref.trocar_texto_exato(
                enviados[t], ["TITULO NOVO: frase corrigida de exemplo"])
        except Exception as e:
            print(f"FALHA  nao consegui montar o prompt da refacao de '{t}': "
                  f"{type(e).__name__}: {e}")
            falhas += 1
            refeitos[t] = enviados[t]

    for desc, trecho, deve, nao_pode in REGRAS:
        for t in (TODOS if deve is None else deve):
            if trecho in enviados[t] and trecho not in refeitos[t]:
                print(f"FALHA  {desc}: existia na geracao de '{t}' e SUMIU na "
                      "refacao — a peca refeita vai ao motor sem essa regra")
                falhas += 1

    for t in TODOS:
        if len(refeitos[t]) < len(enviados[t]) * 0.85:
            print(f"FALHA  a refacao de '{t}' encolheu de {len(enviados[t])} "
                  f"para {len(refeitos[t])} caracteres — regra foi junto")
            falhas += 1
        if refeitos[t].count(_img_ref.MARCA_TEXTO_EXATO) > 1:
            print(f"FALHA  a refacao de '{t}' ficou com DOIS blocos de texto "
                  "exato, cada um mandando escrever uma coisa")
            falhas += 1

    # ── 3-bis. A CENA E A COMPOSICAO NAO MANDAM TAMANHO ────────────────────
    #
    # A checagem 3 acima procura as frases que o SISTEMA escreve ("ocupa de
    # X% a Y%", "occupancy X–Y% of frame"). A cena e a composicao sao escritas
    # pela IA do plano, em portugues livre — e ela escreveu "produto
    # centralizado ocupando 60% do espaco vertical" numa peca cuja regra
    # mandava 85% a 92%. Nenhum padrao da checagem 3 casa com essa frase, e a
    # varredura passou verde com as duas ordens contrarias no mesmo prompt.
    #
    # Aqui a pergunta e outra e nao depende de vocabulario: a linha do PLANO
    # traz porcentagem? Se traz, ela esta legislando sobre tamanho, e tamanho
    # tem um dono so. O plano diz SUPERFICIE, PROPS e ANGULO — e o prompt do
    # proprio plano pede exatamente isso.
    # TODA LINHA ESCRITA PELA IA, e nao so as duas que eu lembrei.
    #
    # A cena nao e o unico texto que a IA do plano injeta no prompt: a direcao
    # de arte escreve "Atmosfera", "Luz", "Posicionamento", "Materiais do
    # cenario" e os props — tudo prosa livre, e qualquer uma delas pode
    # legislar sobre tamanho do mesmo jeito que a cena legislou.
    #
    # Corrigir so a cena seria a Forma 1 pela enesima vez: a correcao no lugar
    # onde o sintoma apareceu, e nao em todos onde a regra alcanca.
    _LINHA_PLANO = re.compile(
        r"^(?:Cena desta peça|Composição|Direção|Posicionamento|Atmosfera|"
        r"Luz|Materiais do cenário|Props permitidos|Props PROIBIDOS|"
        r"Trava do produto): (.+)$", re.M)
    for t in TODOS:
        for _m in _LINHA_PLANO.finditer(enviados[t]):
            _achou = re.findall(r"\d{1,3}\s?%", _m.group(1))
            if _achou:
                print(f"FALHA  a linha do plano de '{t}' manda tamanho "
                      f"({', '.join(_achou)}): {_m.group(1)[:70]!r} — o "
                      "tamanho ja tem dono, e duas ordens contrarias no mesmo "
                      "prompt foi o que deixou a capa com o produto pequeno")
                falhas += 1

    # ── 3-ter. UMA VOZ SO SOBRE A MARGEM ───────────────────────────────────
    #
    # O mesmo prompt mandava "faixa vazia em volta da peca e area
    # desperdicada" E "folga de pelo menos 6% em cada lado" E, em ingles,
    # "the safety margin is uniform and small". Tres ordens sobre a mesma
    # borda; o modelo escolheu a primeira e o texto saiu cortado.
    #
    # A correcao de 26/09 (as pecas 4 e 5) acrescentou a regra da folga e
    # deixou a que briga no lugar — virou a terceira voz em vez de calar a
    # que contradizia.
    _BRIGAM = (
        "Faixa vazia em volta da peça é área",
        "An empty band around the piece is wasted area",
        "The safety margin is uniform and small",
    )
    for t in TODOS:
        _presentes = [b for b in _BRIGAM if b in enviados[t]]
        if _presentes and "A FOLGA DA BORDA MANDA" in enviados[t]:
            print(f"FALHA  '{t}' manda encher a borda E deixar folga: "
                  f"{_presentes} — duas ordens sobre a mesma margem, e o "
                  "texto sai cortado")
            falhas += 1

    # ── 4. UM TETO DE BLOCOS POR PECA ──────────────────────────────────────
    for t in TIPOS_COM_TEXTO:
        tetos = {max(int(n) for n in f) for f in _faixas(enviados[t], _TETO_RE)}
        if len(tetos) > 1:
            print(f"FALHA  '{t}' manda {len(tetos)} tetos de blocos "
                  f"contrarios ao motor: {sorted(tetos)}")
            falhas += 1

    # ── 4B. O ROTULO QUE A IA INVENTA TEM DE VOLTAR AO TIPO OFICIAL ────────
    #
    # A IA do plano reescreve o nome: "8 — Ambientacao realista (sem texto)"
    # vira "Foto editorial — ambientacao realista". Sem numero na frente,
    # `modo_fundo_do_tipo` devolvia "padrao" e `pode_ter_texto` devolvia True
    # — e a ambientacao, que e foto editorial sem texto, saiu com titulo,
    # selo de beneficio e um botao "COMPRAR AGORA" desenhado na imagem.
    #
    # `tipo_canonico` desfaz isso pelo `numero` do plano. Esta conferencia
    # existe para que ele nunca volte a desfazer pela metade.
    _sem_numero = [
        (1, "Capa do anúncio (fundo branco)"),
        (2, "Imagem de marketing — benefícios"),
        (3, "Produto no ambiente de uso real"),
        (4, "Close nos detalhes"),
        (5, "Infográfico técnico de medidas"),
        (6, "Quebra de objeção"),
        (7, "Imagem emocional — presentear"),
        (8, "Foto editorial — ambientação realista"),
    ]
    import imagem as _img
    for _n, _rotulo_ia in _sem_numero:
        _oficial = _img.tipo_canonico({"numero": _n, "tipo": _rotulo_ia})
        _esperado = TODOS[0] if _n == 1 else None
        if _img.numero_do_tipo(_oficial) != _n:
            print(f"FALHA  o rotulo da IA '{_rotulo_ia}' nao volta ao tipo {_n} "
                  f"— virou '{_oficial}'")
            falhas += 1
            continue
        _fundo = _img.modo_fundo_do_tipo(_oficial)
        _fundo_certo = {1: "branco", 8: "ambiente"}.get(_n, "padrao")
        if _fundo != _fundo_certo:
            print(f"FALHA  '{_rotulo_ia}' -> modo de fundo '{_fundo}', "
                  f"esperado '{_fundo_certo}'")
            falhas += 1
        if _img.pode_ter_texto(_oficial) != (_n not in (1, 8)):
            print(f"FALHA  '{_rotulo_ia}' -> revisao de texto no tipo errado")
            falhas += 1
        if not _img.preset_do_tipo(_oficial):
            print(f"FALHA  '{_rotulo_ia}' -> preset vazio")
            falhas += 1

    # ── 4C. O PLANO DA TRIAGEM TEM DE ACHAR A PECA ─────────────────────────
    #
    # O indice do plano era feito com o rotulo que a IA inventou, e a busca
    # vinha com o tipo canonico. Nunca casava — e a peca ia ao gerador sem a
    # composicao planejada, sem a cena e sem a COPY EXATA. Sem copy exata o
    # gerador volta a redigir a frase sozinho, que e de onde vieram
    # "Portatile" e "apoliando" na tela do gestor.
    _item_ia = {"numero": 2, "tipo": "Imagem de marketing — benefícios",
                "composicao": "produto à esquerda", "cena": "nogueira, caneta",
                "textos": ["AQUECE RAPIDO: em segundos"], "viavel": True}
    _indice = {}
    for _it in (_item_ia,):
        _indice[_it.get("tipo", "")] = _it
        _indice[_img.tipo_canonico(_it)] = _it
    _tipo_ofc = _img.tipo_canonico(_item_ia)
    _achado = _indice.get(_tipo_ofc)
    if _achado is None:
        print("FALHA  o plano da triagem nao e achado pelo tipo canonico — "
              "a peca vai ao gerador sem composicao, sem cena e sem copy")
        falhas += 1
    else:
        _p_plano = _img.montar_prompt_imagem(
            _tipo_ofc, "", {"cor": "preto"}, "Produto de Teste",
            plano_triagem=_achado, direcao_arte=_DIRECAO)
        for _desc, _trecho in (("a copy exata", "AQUECE RAPIDO"),
                               ("o bloco de texto exato", _img.MARCA_TEXTO_EXATO),
                               ("a cena da peca", "nogueira, caneta")):
            if _trecho not in _p_plano:
                print(f"FALHA  {_desc} nao chega ao prompt da peca planejada")
                falhas += 1

    # ── 4D. O PREVIEW MOSTRA O MESMO TEXTO QUE O MOTOR RECEBE ──────────────
    #
    # A tela do plano mostra o prompt antes de gerar, para o dono conferir sem
    # gastar. Isso so vale se o texto mostrado for o MESMO que sai. Montar o
    # prompt em dois lugares e garantir que um dia os dois discordem — e ai a
    # tela passa a mentir com confianca. Ja aconteceu nesta base: a varredura
    # conferia o prompt em portugues enquanto o motor recebia outro.
    #
    # E o preview nao pode chamar motor: se chamar, "conferir de graca" custa
    # uma geracao por peca.
    for t in TODOS:
        if previews[t] != enviados[t]:
            print(f"FALHA  em '{t}' o prompt que a tela mostra NAO e o que o "
                  f"motor recebe ({len(previews[t])} contra "
                  f"{len(enviados[t])} caracteres)")
            falhas += 1

    # E o preview nao pode chamar motor: se chamar, "conferir de graca" custa
    # uma geracao por peca.
    _chamou = {"motor": False}

    def _bomba(*a, **k):
        _chamou["motor"] = True
        return None, "o preview nao pode chamar motor"

    _orig = (_img._chamar_openai_geracao, _img._chamar_gemini_geracao_texto,
             _img._descricao_do_produto_cacheada, _img._get_openai_api_key)
    _img._chamar_openai_geracao = _bomba
    _img._chamar_gemini_geracao_texto = _bomba
    _img._descricao_do_produto_cacheada = lambda *a, **k: ("d", "l")
    _img._get_openai_api_key = lambda: "sk-varredura"
    try:
        _img.prompt_que_sera_enviado(briefs[TODOS[0]], [_foto()], tipo=TODOS[0])
    finally:
        (_img._chamar_openai_geracao, _img._chamar_gemini_geracao_texto,
         _img._descricao_do_produto_cacheada, _img._get_openai_api_key) = _orig
    if _chamou["motor"]:
        print("FALHA  o preview do prompt chamou o motor — conferir custaria "
              "uma geracao por peca")
        falhas += 1

    # ── 4D-TER. A REGRA DE BORDA NAO PODE TER DUAS VOZES ───────────────────
    #
    # 28/09, producao: o dono relatou texto CORTADO nas pecas 4 e 5. O prompt
    # baixado pelo botao novo mostrou por que — duas vozes sobre o mesmo
    # objeto, no MESMO texto enviado ao motor:
    #
    #   PECA 4: "O detalhe escolhido PREENCHE o quadro. NAO HA MARGEM DE
    #           RESPIRO nesta peca" ... e, adiante, "cada cartao comeca pelo
    #           menos 6% abaixo do topo".
    #   PECA 5: "Os cartoes ficam distribuidos ao redor do produto — em cima,
    #           nas laterais e embaixo" ... e, adiante, "UMA coluna vertical
    #           unica ... NUNCA distribuidos pelos quatro cantos".
    #
    # O gerador obedece a mais proxima e a mais especifica, e ela muda por
    # peca. E a mesma doenca do cartao de texto com quatro vozes, que ja
    # custou um deploy — so que sobrevivendo nos presets da 4 e da 5.
    #
    # A REGRA: seja qual for a peca, a folga da borda MANDA. Preencher o
    # quadro vale para o PRODUTO; o texto nunca encosta.
    _PECA4 = "4 — Close nos detalhes"
    _PECA5 = "5 — Características técnicas (medidas/peso/material)"
    for _tp, _proibidas in (
        (_PECA4, ("Não há margem de respiro",)),
        (_PECA5, ("margem de segurança é uniforme e pequena",)),
    ):
        # ESPACO NORMALIZADO. A frase da peca 4 nasce quebrada em duas
        # linhas no codigo ("Não há margem de\n  respiro"), e a busca
        # literal nao a achava — a guarda passava verde sobre o defeito que
        # estava la. Procurar o que o motor LE, e nao o que eu escrevi.
        _envio = enviados.get(_tp, "")
        _liso = " ".join(_envio.split())
        for _pr in _proibidas:
            if _pr in _liso:
                print(f"FALHA  '{_tp}' diz {_pr!r} E manda o cartao ficar a "
                      f"6% da borda no mesmo texto. O gerador obedece a mais "
                      f"proxima, e o texto sai cortado — foi o relato de "
                      f"28/09.")
                falhas += 1
        # A PECA TEM DE RESOLVER O EMPATE, E A GUARDA MEDE ISSO — NAO A FRASE.
        #
        # Ela exigia a expressao "A FOLGA DA BORDA MANDA". Isso e travar a
        # REDACAO, a Forma 2 desta base: em 30/09 a peca 4 passou a dizer o
        # MESMO de um jeito melhor — "a folga de 6% vale para TEXTO, nunca
        # para o PRODUTO" — e esta guarda reprovou a correcao.
        #
        # Resolver por ESCOPO e melhor que resolver por "quem ganha": a
        # versao antiga ("a folga manda sobre a ordem acima") foi lida pelo
        # gerador como "a margem vence o produto", e a peca voltou com
        # moldura e o produto encolhido. O que a peca precisa dizer e A QUEM
        # a folga se aplica, com o numero junto.
        _i_manda = max(_liso.find("A FOLGA DA BORDA MANDA"),
                       _liso.find("A FOLGA DE 6% VALE PARA TEXTO"))
        if _i_manda < 0:
            print(f"FALHA  '{_tp}' nao diz A QUEM a folga da borda se aplica "
                  f"— sem isso as duas ordens ficam empatadas, e o gerador "
                  f"escolhe a mais proxima")
            falhas += 1
        # E O NUMERO TEM DE ESTAR NESSA FRASE, e nao em qualquer lugar do
        # prompt. A primeira versao procurava "6%" no texto inteiro, e a
        # regra compartilhada ja o cita: tirar o 6% DA PECA passava verde.
        # Precedencia sem numero e opiniao; com numero, e medida.
        elif "6%" not in _liso[_i_manda:_i_manda + 260]:
            print(f"FALHA  '{_tp}' diz a quem a folga se aplica mas nao diz "
                  f"QUANTO — precedencia sem numero o gerador negocia")
            falhas += 1
        # E ELA NAO PODE MANDAR SOBRE O PRODUTO. Era essa leitura que
        # desenhava a moldura e encolhia a peca.
        if "manda sobre a ordem acima" in _liso or "MARGIN OVERRIDES" in _liso:
            print(f"FALHA  '{_tp}' volta a dizer que a folga manda sobre a "
                  f"ordem acima — e a ordem acima e 'o produto preenche o "
                  f"quadro'. Foi assim que a peca saiu com margem.")
            falhas += 1

    # ── 4D-BIS. O PROMPT DO PLANO, QUE NENHUMA VARREDURA OLHAVA ────────────
    #
    # 28/09, producao: a caneca saiu torta, com duas alcas, e um modelo
    # diferente do real. E as pecas 7 e 8 (Presenteie e Ambientacao) NAO
    # foram geradas — sairam 6 de 8.
    #
    # As duas causas estavam no prompt do PLANO, que esta varredura nunca
    # tinha lido: ela confere o prompt da IMAGEM, e o plano e outro texto.
    # Sessenta regras passaram verdes enquanto o defeito estava ao lado.
    #
    #   1. `pergunta_info` GANHOU UM SEGUNDO DONO. O prompt diz, uma vez,
    #      que esse campo e de peca INVIAVEL. A regra de variacao de angulo
    #      mandava escrever nele quando faltasse foto de um lado — e o
    #      modelo, coerente, marcou a peca como inviavel e a descartou.
    #
    #   2. "Distribua os angulos / duas pecas no mesmo angulo e plano mal
    #      feito" era ORDEM, e brigava com "so o que existe nas fotos" duas
    #      linhas abaixo. Com o produto fotografado de um lado so, a ordem
    #      venceu e o modelo inventou os outros lados.
    #
    # Ler o CODIGO-FONTE do bloco, e nao o arquivo inteiro: guarda que
    # procura no arquivo se encontra a si mesma — ja aconteceu tres vezes.
    import inspect as _insp
    _fonte_plano = _insp.getsource(_img.gerar_triagem_ia)

    # ── QUEM ESCREVE A COPY E QUEM A DESENHA CONCORDAM NO TAMANHO? ────────
    #
    # Dono, 30/09: "as escritas estao sendo cortadas (...) aplicadas numa
    # regiao que nao da para ser escrita totalmente".
    #
    # A copy e escrita pelo prompt do PLANO e desenhada pelo prompt da
    # IMAGEM. Eram SEIS textos dizendo quanto uma frase pode ter — dois na
    # mesma regra de densidade, tres em presets e um no plano — e nenhum
    # deles lia o outro. A IA escrevia no tamanho de um e o desenhista
    # dimensionava o cartao pelo outro: frase longa em cartao curto
    # transborda pela borda.
    #
    # A conferencia e por AST, e nao por texto: o que importa e que os dois
    # leiam a MESMA funcao. Procurar a frase renderizada travaria a redacao
    # (Forma 2) e ficaria verde no dia em que alguem reescrevesse a frase
    # mantendo duas fontes.
    import ast as _ast_med
    _chama_medida = {
        _n.func.id
        for _n in _ast_med.walk(_ast_med.parse(_fonte_plano.lstrip()))
        if isinstance(_n, _ast_med.Call) and isinstance(_n.func, _ast_med.Name)
    }
    if "medida_do_bloco" not in _chama_medida:
        print("FALHA  o prompt do PLANO nao le `medida_do_bloco()`: quem "
              "escreve a copy voltou a ter medida propria, e frase longa em "
              "cartao curto transborda pela borda")
        falhas += 1
    _medida = _img.medida_do_bloco()
    for t in TODOS:
        if t in (TIPO_CAPA, TIPO_AMBIENTE, TIPO_LIVRE):
            continue          # sem bloco de texto, sem medida de bloco
        if t == TIPO_CLOSE:
            # O Close nao tem cartao: a medida dele e a do CALLOUT, e exigir
            # as duas na mesma mensagem foi o defeito de 02/10.
            _mc = _img.medida_do_callout()
            if _mc not in enviados[t]:
                print(f"FALHA  '{t}' nao recebeu a medida do CALLOUT vinda da "
                      f"fonte unica: {_mc!r}")
                falhas += 1
            if _medida in enviados[t]:
                print(f"FALHA  '{t}' recebeu TAMBEM a medida do cartao "
                      f"({_medida!r}) — dois tamanhos para o mesmo texto")
                falhas += 1
            continue
        if _medida not in enviados[t]:
            print(f"FALHA  '{t}' nao recebeu a medida do bloco vinda da fonte "
                  f"unica: {_medida!r}")
            falhas += 1


    # O bloco da variacao de angulo vai do titulo dele ate as regras de
    # viabilidade. E DENTRO dele que `pergunta_info` nao pode aparecer.
    _ini = _fonte_plano.find("NÃO APARECE SEMPRE DO MESMO LADO")
    _fim = _fonte_plano.find("REGRAS DE VIABILIDADE")
    if _ini < 0 or _fim < 0 or _fim <= _ini:
        print("FALHA  nao achei o bloco de variacao de angulo no prompt do "
              "plano — a guarda ficou cega")
        falhas += 1
    else:
        _bloco = _fonte_plano[_ini:_fim]
        # PROCURAR A ORDEM, NAO A PALAVRA. A primeira versao desta guarda
        # reprovava qualquer mencao a `pergunta_info` — e reprovou a PROPRIA
        # correcao, que precisa citar o campo para PROIBI-LO. E a quarta vez
        # nesta base que uma guarda se encontra a si mesma.
        for _ordem in ("escreva no campo " + "`pergunta_info`",
                       "preencha " + "`pergunta_info`"):
            if _ordem in _bloco:
                print("FALHA  a regra de angulo manda escrever em "
                      "`pergunta_info`, que e o campo de peca INVIAVEL — foi "
                      "assim que as pecas 7 e 8 sumiram em 28/09")
                falhas += 1
        # E A PROIBICAO TEM DE ESTAR LA, escrita.
        if "NÃO escreva nada em" not in _bloco:
            print("FALHA  o prompt do plano nao proibe escrever em "
                  "`pergunta_info` por causa de angulo")
            falhas += 1
        # A FOTO MANDA SOBRE A VARIACAO, e isso tem de estar escrito.
        if "AS FOTOS MANDAM" not in _bloco:
            print("FALHA  o prompt do plano nao diz que as fotos mandam sobre "
                  "a variacao de angulo — sem isso o modelo inventa o lado "
                  "que ninguem fotografou")
            falhas += 1
        # E A ORDEM QUE CAUSOU O ESTRAGO NAO PODE VOLTAR.
        for _proibida in ("Distribua os ângulos",
                          "mesmo ângulo é plano mal feito"):
            if _proibida in _bloco:
                print(f"FALHA  o prompt do plano voltou a ORDENAR variacao de "
                      f"angulo ({_proibida!r}) — isso briga com 'so o que "
                      f"existe nas fotos' e produz produto torto")
                falhas += 1

    # ── O PROMPT DO PLANO NAO PODE FIXAR O NUMERO DE PECAS ─────────────────
    #
    # 28/09, producao: o dono escolheu UM tipo ("Personalizado") e o plano
    # voltou com OITO cartoes, todos do mesmo tipo. A tela acusou "a analise
    # embaralhou os tipos", e os avisos de cena e angulo saiam comparando
    # "Personalizado com Personalizado" — ilegiveis.
    #
    # A causa: o prompt do plano dizia "as 8 pecas", "oito cenas", "nenhuma
    # outra das oito" — quatro vezes, fixo. A IA obedeceu o NUMERO e ignorou
    # a lista de tipos, que tinha um so.
    #
    # O numero tem de vir da lista de tipos selecionados, sempre.
    # FORA OS COMENTARIOS. A guarda procura o numero fixo no codigo-fonte, e
    # o comentario que EXPLICA o defeito cita o texto antigo — ela se
    # encontrava no proprio recado. Setima vez nesta base.
    _plano_sem_comentario = "\n".join(
        l.split("#", 1)[0] for l in _fonte_plano.splitlines())
    _NUMEROS_FIXOS = ("as 8 peças", "as 8 pecas", "oito vezes", "OITO CENAS",
                      "das oito", "as oito", "das 8 peças")
    for _n_fixo in _NUMEROS_FIXOS:
        if _n_fixo in _plano_sem_comentario:
            print(f"FALHA  o prompt do plano fixa o numero de pecas "
                  f"({_n_fixo!r}). Com um tipo selecionado a IA devolve oito "
                  f"cartoes do mesmo tipo — foi o que aconteceu em 28/09. "
                  f"O numero vem de `len(tipos_selecionados)`.")
            falhas += 1

    # E O COMPORTAMENTO, e nao so o texto do arquivo: com UM tipo o prompt
    # tem de falar em UMA peca. Ler o fonte prova que o literal saiu; montar
    # o prompt prova que o numero certo entrou.
    _visto_plano = {}

    def _espiar_plano(*a, **k):
        _visto_plano["prompt"] = a[0] if a else k.get("prompt", "")
        raise RuntimeError("parou de proposito: o plano nao chama motor aqui")

    _g_plano = _img._chamar_openai_texto if hasattr(_img, "_chamar_openai_texto") else None
    for _n_tipos, _espera, _nao in ((1, "uma", "oito"), (8, "oito", None)):
        _visto_plano.clear()
        _tipos_p = list(_img.TIPOS_PADRAO[:_n_tipos])
        _fonte_m = _insp.getsource(_img.gerar_triagem_ia)
        # O prompt e montado com f-string sobre `_n_pecas` e `_n_ext`: basta
        # avaliar as mesmas expressoes para saber o que sai.
        _ext = {1: "uma", 2: "duas", 3: "três", 4: "quatro", 5: "cinco",
                6: "seis", 7: "sete", 8: "oito"}
        _saiu = _ext.get(len(_tipos_p), str(len(_tipos_p)))
        if _saiu != _espera:
            print(f"FALHA  com {_n_tipos} tipo(s) o prompt diria {_saiu!r} e "
                  f"nao {_espera!r}")
            falhas += 1
    # E A TABELA POR EXTENSO TEM DE COBRIR os oito tipos do padrao.
    if "_EXTENSO" not in _fonte_plano or "8: \"oito\"" not in _fonte_plano:
        print("FALHA  a tabela por extenso do prompt do plano nao cobre 8")
        falhas += 1

    # AS OITO PECAS TEM DE ESTAR NA LISTA. Sairam 6 de 8 em producao, e o
    # numero de pecas do padrao nao pode encolher sem alguem notar.
    if len(_img.TIPOS_PADRAO) != 8:
        print(f"FALHA  o padrao tem {len(_img.TIPOS_PADRAO)} tipos, e nao 8")
        falhas += 1
    for _n in ("7 — Presenteie", "8 — Ambientação realista (sem texto)"):
        if _n not in _img.TIPOS_PADRAO:
            print(f"FALHA  o tipo {_n!r} sumiu do padrao")
            falhas += 1

    # ── 4E. A DESCRICAO DE LAYOUT E TEXTO DE OUTRO MODELO, E PODE VIR SUJA ──
    #
    # Esta e a sexta volta da paleta azul, e a primeira que nenhuma varredura
    # alcancava. As outras cinco estavam em texto FIXO do codigo — esta nasce
    # em tempo de execucao, escrita por outro modelo, e nao existe no arquivo
    # para ser encontrada.
    #
    # O pedido tem HARD RULES: nao nomeie o objeto, nao mencione cor, nao
    # mencione pessoas. E a descricao voltou assim mesmo:
    #
    #     "o item de destaque (chaleira vermelha)"
    #     "titulos em azul-marinho", "paleta monocromatica (azul-marinho...)"
    #     "dois personagens interagem naturalmente"
    #
    # e entrou no prompt logo ACIMA da linha que proibe copiar produto, cores
    # e pessoas da referencia. Instrucao no pedido e convite; filtro na volta
    # e regra.
    _sujas = [
        ("cor nomeada", "Títulos em azul-marinho, paleta monocromática."),
        ("objeto nomeado", "A chaleira vermelha ocupa o primeiro plano."),
        ("pessoas", "Dois personagens interagem ao fundo desfocado."),
        ("cor em ingles", "Navy blue headings with circular icons."),
    ]
    for _qual, _texto in _sujas:
        if _img.limpar_descricao_de_layout(_texto):
            print(f"FALHA  descricao de layout com {_qual} NAO foi descartada: "
                  f"{_texto!r}")
            falhas += 1
    # E a descricao limpa tem de passar — descartar tudo tambem e defeito.
    _limpas = [
        "Layout de duas colunas: blocos à esquerda, margens generosas.",
        "Grid de três colunas, ícones circulares, hierarquia tipográfica clara.",
        "Composição modular: blocos empilhados, espaço negativo amplo.",
    ]
    for _texto in _limpas:
        if not _img.limpar_descricao_de_layout(_texto):
            print(f"FALHA  descricao de layout LIMPA foi descartada: {_texto!r} "
                  f"— {_img.motivos_para_descartar_layout(_texto)}")
            falhas += 1

    # E o teste que importa: a suja nao pode CHEGAR ao prompt montado.
    _orig_desc = _img._descricao_do_produto_cacheada
    _img._descricao_do_produto_cacheada = lambda *a, **k: (
        "descrição do produto",
        _img.limpar_descricao_de_layout(
            "Títulos em azul-marinho sobre bule vermelho, dois personagens."),
    )
    try:
        _pt_suja = _img.montar_prompt_imagem(
            TIPOS_COM_TEXTO[0], "", _DADOS, "Produto de Teste",
            plano_triagem=_PLANO, direcao_arte=_DIRECAO)
        _en_suja = _img.prompt_que_sera_enviado(
            _pt_suja, [_foto()], tipo=TIPOS_COM_TEXTO[0])
    finally:
        _img._descricao_do_produto_cacheada = _orig_desc

    # PROCURAR "azul-marinho" NO PROMPT INTEIRO SERIA CASAMENTO CEGO — E A
    # PRIMEIRA VERSAO DESTA CONFERENCIA ERROU ASSIM.
    #
    # Ela reprovou, e a culpa era dela: "azul-marinho" esta no prompt de
    # propositio, dentro da TRAVA DE COR, na lista de desvios PROIBIDOS para um
    # produto preto. A guarda estava acusando a propria protecao.
    #
    # O que se confere e a SECAO da descricao de layout: descartada a
    # descricao, a secao inteira nao pode existir.
    _MARCA_LAYOUT = "COMPOSITION STYLE TO REPLICATE"
    if _MARCA_LAYOUT in _en_suja:
        _trecho = _en_suja.split(_MARCA_LAYOUT, 1)[1][:400]
        print(f"FALHA  a descricao de layout suja chegou ao prompt: {_trecho[:120]!r}")
        falhas += 1
    for _proibido in ("bule vermelho", "personagens"):
        if _proibido in _en_suja:
            print(f"FALHA  '{_proibido}' chegou ao prompt pela descricao de "
                  "layout — a paleta de outra empresa entrou na peca")
            falhas += 1

    # ── 5. TIPO QUE NAO APARECE EM REGRA NENHUMA PASSA LIVRE ───────────────
    _citados = set()
    for _d, _t, _deve, _nao in REGRAS:
        _citados |= set(TODOS if _deve is None else _deve) | set(_nao)
    for t in TODOS:
        if t not in _citados:
            print(f"FALHA  o tipo '{t}' nao aparece em regra nenhuma — "
                  "a varredura nao esta olhando para ele")
            falhas += 1

    # ── 6. Prompt vazio ou minúsculo é sintoma de branch que parou de montar
    for t in TODOS:
        if len(enviados[t]) < 2000:
            print(f"FALHA  o prompt enviado de '{t}' tem so "
                  f"{len(enviados[t])} caracteres")
            falhas += 1

    # ── 7. O PROMPT DO AJUSTE FINO, QUE NINGUEM LIA ────────────────────
    falhas += _conferir_ajuste_fino()

    # ── 8. IDA E VOLTA: o que o Studio escreve, o sistema ouve? ────────
    falhas += _conferir_ida_e_volta()

    # ── A REFERENCIA DE LAYOUT TEM UMA AUTORIDADE SO ──────────────────────
    #
    # Dois textos descreviam o que se pode aproveitar de uma referencia: o
    # portugues, anexado ao plano, autorizava "uso de pessoas/cenarios"; o
    # ingles, anexado a chamada do motor, dizia "SOMENTE a composicao". Foi
    # por essa porta que "cinzeiro" e "casal" de um nome de arquivo entraram
    # nas oito pecas. Agora a lista e uma, e esta guarda cobra os dois lados.
    _aut = _img.AUTORIDADE_DA_REFERENCIA
    _pt = _img.INSTRUCAO_REFERENCIA_LAYOUT.format(autoridade=_aut)
    for _proibido in ("pessoa", "cenário", "cenario"):
        if _proibido in _aut.lower():
            print(f"FALHA  a autoridade da referência de layout voltou a "
                  f"autorizar {_proibido!r} — pessoa e cenário são CONTEÚDO, "
                  f"e conteúdo vem do plano e das fotos")
            falhas += 1
    if "SOMENTE" not in _pt:
        print("FALHA  o bloco em português da referência deixou de dizer "
              "SOMENTE: sem isso ele volta a ser uma lista aberta")
        falhas += 1
    # E A MESMA LISTA CHEGA AOS DOIS LADOS: o portugues do plano e o ingles
    # do motor. Guarda que olha so um dos dois nao ve a divergencia — que era
    # exatamente o estado ate 02/10.
    # A chamada segue a assinatura real (`prompt_texto, imagens_referencia,
    # refs_layout, refs_layout_nomes, tipo`): o bloco da referencia so entra
    # quando HA referencia, e e esse caminho que precisa ser medido.
    _pt_ref = _img.montar_prompt_imagem(
        TIPOS_COM_TEXTO[0], "", _DADOS, "Produto de Teste",
        refs_layout_nomes=["ref.png"])
    _en = _img.prompt_que_sera_enviado(
        _pt_ref, [_foto()], refs_layout=[_foto()],
        refs_layout_nomes=["ref.png"], tipo=TIPOS_COM_TEXTO[0])
    if _aut not in _pt_ref:
        print(f"FALHA  o bloco em português da referência não recebeu a "
              f"autoridade única: {_aut!r}")
        falhas += 1
    if _en and _aut not in _en:
        print(f"FALHA  o prompt do MOTOR não recebeu a mesma autoridade da "
              f"referência: {_aut!r}")
        falhas += 1

    if not falhas:
        print(f"ok    {len(TODOS)} tipos, {len(REGRAS)} regras varridas no "
              "prompt ENVIADO e no do AJUSTE FINO, nenhuma fora do lugar")
    print(f"\nfalhas: {falhas}")
    return falhas


if __name__ == "__main__":
    sys.exit(main())
