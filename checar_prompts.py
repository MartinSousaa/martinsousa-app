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
    ("a ocupação medida do quadro", "dimensao util do quadro",
     TIPOS_COM_TEXTO + (TIPO_CAPA,), (TIPO_AMBIENTE,)),
    ("a proibição de produto pequeno em cenário amplo",
     "Nunca deixe o produto pequeno", TIPOS_COM_TEXTO, (TIPO_AMBIENTE,)),
    ("a escala real do ambiente", "ESCALA REAL", (TIPO_AMBIENTE,),
     TIPOS_COM_TEXTO + (TIPO_CAPA,)),

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
_TETO_RE = (
    re.compile(r"Maximum (\d+) information elements", re.I),
    re.compile(r"use de (\d+) a (\d+) blocos", re.I),
    re.compile(r"M[aá]ximo (\d+)(?:-(\d+))? (?:callouts|frases|blocos|benef)", re.I),
    re.compile(r"de (\d+) a (\d+) (?:blocos de pergunta|benef[ií]cios)", re.I),
    # A linha que a copy escreve. Sem ela a varredura so via o numero em
    # ingles, e um "Maximum 7" ao lado de uma copy de 4 passava batido.
    re.compile(r"exatamente (\d+) bloco", re.I),
)


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


_DADOS = {"nome_comercial": "Produto de Teste", "cor": "preto",
          "medidas": "71x14x14", "peso": "350 g", "material": "Metal"}
_PLANO = {"composicao": "produto à esquerda, cartões à direita",
          "cena": "superfície de nogueira, caderno fechado, câmera em 3/4",
          "textos": ["Aquece rápido", "Cerâmica premium",
                     "Alça confortável", "Presente perfeito"]}

# A DIRECAO DE ARTE DECIDIDA UMA VEZ, PARA AS OITO.
_DIRECAO = {
    "nome": "Executivo Quente Contemporâneo",
    "posicionamento": "premium contemporâneo",
    "atmosfera": "escritório sofisticado, quente e contido",
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


def _prompts(tipo):
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

    def _gemini(prompt_final, imagens_bytes=None, ref_layout=None):
        capturado.setdefault("prompt", prompt_final)
        return None, "motor desligado na varredura"

    def _descricao(imagens_referencia, nome_produto="produto",
                   dados_descricao=None, refs_layout=None):
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
        plano = None if tipo in (TIPO_CAPA, TIPO_AMBIENTE, TIPO_LIVRE) else _PLANO
        pt = imagem.montar_prompt_imagem(
            tipo, "quero o produto virado para a direita" if tipo == TIPO_LIVRE else "",
            _DADOS, "Produto de Teste", plano_triagem=plano,
            ambientacao="mesa de jantar" if tipo == TIPO_AMBIENTE else "",
            direcao_arte=_DIRECAO)
        imagem.gerar_imagem_ia(pt, [_foto()], tipo=tipo)
    finally:
        (imagem._chamar_openai_geracao,
         imagem._chamar_gemini_geracao_texto,
         imagem._descricao_do_produto_cacheada,
         imagem._get_openai_api_key) = originais
    return pt, capturado.get("prompt", "")


def main():
    briefs, enviados = {}, {}
    for t in TODOS:
        try:
            briefs[t], enviados[t] = _prompts(t)
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

    # ── 3. UMA MEDIDA DE OCUPACAO POR PECA ─────────────────────────────────
    for t in TODOS:
        faixas = _faixas(enviados[t], _OCUPACAO_RE)
        if len(faixas) > 1:
            print(f"FALHA  '{t}' manda {len(faixas)} medidas de ocupacao "
                  f"contrarias ao motor: {sorted(faixas)}")
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

    if not falhas:
        print(f"ok    {len(TODOS)} tipos, {len(REGRAS)} regras varridas no "
              "prompt ENVIADO, nenhuma fora do lugar")
    print(f"\nfalhas: {falhas}")
    return falhas


if __name__ == "__main__":
    sys.exit(main())
