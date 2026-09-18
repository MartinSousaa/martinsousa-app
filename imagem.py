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
    """Retorna OPENAI_API_KEY das secrets ou variável de ambiente."""
    return st.secrets.get("OPENAI_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")


# ── PADRÃO VISUAL MARTINSOUSA (hardcoded em todos os prompts) ──────────────────
PADRAO_VISUAL = """
PADRÃO VISUAL OBRIGATÓRIO DA EMPRESA (aplique em todas as peças de marketing):

ATENÇÃO — ESCOPO DAS CORES DA MARCA (regra que precede todas as outras):
As cores abaixo valem EXCLUSIVAMENTE para fundo, texto, ícones, painéis e
elementos gráficos. Elas NUNCA se aplicam ao produto. O produto mantém a cor
real das fotos de referência, mesmo que ela destoe da paleta. É proibido
"harmonizar", tingir, esfriar ou aproximar a cor do produto da paleta da marca.

- Fundo: #E8EEF5 (azul-cinza claro suave)
- Cor de texto e elementos gráficos: #1A3A6B (azul marinho) — NUNCA no produto
- Cor de destaque secundária: #4A7EC7 (azul médio) — NUNCA no produto
- Fonte: Montserrat ou Poppins — nunca fontes serifadas
- Ícones: estilo line-art clean, traço fino, monocromáticos em azul marinho
- Elementos decorativos: círculos ou manchas suaves em azul marinho ou azul médio,
  usados como moldura ou destaque atrás do produto ou dos ícones
- Texto sempre em português do Brasil, sem erros ortográficos, sem caixa alta excessiva
- Visual limpo, arejado, profissional — sem poluição visual
- NÃO use marrom, laranja, vermelho ou verde como cores principais
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

INSTRUCAO_PROPORCAO = """
REGRA DE PROPORÇÃO E DESTAQUE DO PRODUTO (obrigatória):
- O produto deve ser o elemento principal e dominante da composição
- Ocupe o maior espaço possível no frame — o produto deve ser grande, imponente, bem visível
- NUNCA minimize ou reduza o produto para dar espaço a elementos decorativos
- Para imagens de marketing com texto (benefícios, características, frases): produto e texto coexistem de forma equilibrada — o texto é parte essencial da composição, não elemento secundário
- Para fotos limpas de produto (capa do anúncio): produto ocupa o máximo espaço, sem texto
- Mantenha as proporções exatas do produto: não alongue, não achate, não deforme
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
- Sem referência: use de 3 a 5 blocos informativos, conforme o conteúdo disponível
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
        "Produto centralizado e O MAIOR POSSÍVEL: deve ocupar 90-95% do frame, "
        "encostando quase nas bordas, sem cortar nenhuma parte e sem distorcer as "
        "proporções reais. Margem branca mínima — sobra de fundo é desperdício de "
        "área nesta imagem, que é a primeira que o comprador vê. "
        "Iluminação profissional de estúdio: luz suave e uniforme, sombra mínima e delicada embaixo. "
        "Posição: ângulo frontal ligeiramente 3/4 que mostra melhor o produto, ou frontal direto. "
        "Resultado: foto de e-commerce de alta qualidade — limpa, profissional, produto é tudo."
    ),
    "2 — Benefícios do produto": (
        "IMAGEM DE MARKETING — BENEFÍCIOS: produto em zona central limpa (SEM texto sobre ele). "
        "Fundo padrão da marca (#E8EEF5). De 3 a 5 benefícios em cartões laterais, inferiores ou em grade — siga a referência de layout quando houver: "
        "ícone line-art azul marinho + título curto (2-3 palavras) + frase direta (máximo 7 palavras). "
        "Visual arejado, muito whitespace — jamais comprima ou empilhe os blocos de benefício. "
        "Os textos dos benefícios vêm dos diferenciais e características do produto informados."
    ),
    "3 — Benefícios no cenário de uso": (
        "IMAGEM DE MARKETING — PRODUTO NO AMBIENTE DE USO REAL: escolha o cenário mais natural "
        "para este produto específico (escritório, quarto, sala de estudo, cozinha, etc.). "
        "Produto protagonista em cena aspiracional com iluminação natural suave. "
        "Máximo 2-3 frases de destaque em painéis fora do produto (nunca sobre ele). "
        "Cada frase: curta, impactante, máximo 6 palavras. Fundo e cores da marca presentes. "
        "Visual editorial — parece foto de lifestyle de qualidade, não montagem amadora."
    ),
    "4 — Close nos detalhes": (
        "CLOSE NO PRODUTO — ZOOM REAL EM DETALHE ESPECÍFICO: NÃO mostre o produto inteiro. "
        "Recorte e amplie UMA área específica do produto: textura do material, acabamento, encaixe, "
        "mecanismo, superfície, ou detalhe que justifique qualidade e diferencial. "
        "Fundo desfocado (bokeh) com produto em foco nítido no primeiro plano. "
        "Máximo 2 callouts discretos com linha fina + legenda de até 4 palavras, posicionados "
        "em área limpa FORA do produto. Tom: premium, artesanal, qualidade perceptível. "
        "ZERO medidas, ZERO setas de dimensão — isso é uma foto de qualidade, não infográfico técnico."
    ),
    "5 — Características técnicas (medidas/peso/material)": (
        "INFOGRÁFICO TÉCNICO DE MEDIDAS — estilo cota de catálogo: produto grande e "
        "centralizado, fotografado nítido, ocupando o miolo da peça. "
        "CADA dimensão recebe SEU PRÓPRIO indicador, nunca uma linha de texto corrida: "
        "uma seta ou linha de cota TRACEJADA saindo da borda exata que está sendo medida, "
        "terminando num CARTÃO de cantos arredondados, fundo branco e borda fina azul, "
        "contendo o rótulo em caixa alta pequena (ALTURA, LARGURA, PROFUNDIDADE, PESO) e, "
        "logo abaixo, o valor em número grande e negrito. "
        "Os cartões ficam distribuídos ao redor do produto — em cima, nas laterais e "
        "embaixo — cada um junto da medida que representa, nunca empilhados num canto. "
        "Setas nas duas pontas das linhas de cota, no eixo correto de cada medida. "
        "Fundo claro liso. ZERO ícones decorativos, ZERO blocos de benefício, ZERO frases de venda. "
        "Use APENAS os valores informados nos dados do produto — JAMAIS invente ou estime medidas. "
        "Se medidas não foram informadas, omita-as completamente — não crie números fictícios."
    ),
    "6 — Quebra de objeção": (
        "IMAGEM DE MARKETING — RESPONDENDO DÚVIDAS DO COMPRADOR: layout clean com produto "
        "em destaque e de 3 a 4 blocos de pergunta+resposta ao lado, em cartões de cantos arredondados — siga a referência de layout quando houver. "
        "Cada bloco: pergunta curta (máximo 5 palavras) em destaque + check verde + resposta direta "
        "(máximo 8 palavras). As objeções são baseadas nos diferenciais e características do produto. "
        "Visual arejado, muito whitespace, fundo padrão da marca (#E8EEF5)."
    ),
    "7 — Presenteie": (
        "IMAGEM EMOCIONAL — PRESENTEAR: composição elegante com produto como presente especial. "
        "Contexto visual de presente: laço de fita, embrulho decorativo, ou cena de entrega. "
        "Frase grande e impactante em destaque: 'Presenteie com' + nome do produto, ou frase emotiva. "
        "Visual limpo, clean, tons suaves e elegantes — produto e contexto de presente como únicos elementos. "
        "Se nenhuma frase específica foi fornecida, crie uma frase genérica adequada ao produto."
    ),
    "8 — Ambientação realista (sem texto)": (
        "FOTO EDITORIAL — PRODUTO NO AMBIENTE NATURAL DE USO: ZERO TEXTO, ZERO ÍCONE, ZERO BENEFÍCIO. "
        "Identifique o ambiente mais natural para este produto (escritório, quarto de estudos, sala, "
        "mesa de trabalho, estante de livros, etc.) e integre o produto como peça protagonista. "
        "Cena real com mobiliário, iluminação natural suave, tons neutros e composição editorial elegante. "
        "Apenas a frase discreta 'Imagem meramente ilustrativa' no canto inferior em tipografia fina. "
        "Tom: revista de decoração/lifestyle — parece uma foto editorial real, não montagem digital."
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

TAREFA: Para cada tipo, analise se é VIÁVEL gerar com as informações e fotos disponíveis.

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

Responda SOMENTE com JSON válido, sem texto antes ou depois:
{{
  "plano": [
    {{
      "tipo": "nome do tipo",
      "numero": 1,
      "composicao": "1-2 frases curtas descrevendo a imagem (só se viavel: true)",
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
            max_tokens=2048,
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
                "- Color distribution and use of whitespace\n"
                "- Grid/alignment structure (centered, left-aligned, asymmetric)\n"
                "- Element count and spacing feel\n"
                "- Overall aesthetic and professional mood\n\n"
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
            body = {
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": {
                    "responseModalities": ["IMAGE", "TEXT"],
                },
            }
            resp = requests.post(url, json=body, headers=headers, timeout=120,
                                 proxies={"http": None, "https": None})
            if resp.status_code == 429:
                try:
                    _ej = resp.json()
                    _msg = _ej.get("error", {}).get("message", resp.text[:300])
                    _st = _ej.get("error", {}).get("status", "")
                except Exception:
                    _msg = resp.text[:300]
                    _st = ""
                _cota = any(k in _msg.lower() for k in [
                    "quota", "exhausted", "resource_exhausted", "billing",
                ]) or _st == "RESOURCE_EXHAUSTED"
                if _cota:
                    return None, f"COTA_ESGOTADA:{_msg[:200]}"
                if tentativa >= MAX_TENTATIVAS:
                    return None, f"HTTP 429: {_msg[:200]}"
                _time.sleep(60)
                continue
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


def _chamar_openai_geracao(prompt_final, imagens_bytes=None, ref_layout=None,
                           ref_layout_nome="", diagnostico=None):
    """Chama gpt-image-2 da OpenAI (motor primário de geração). Retorna (img_bytes, erro).

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
                    model="gpt-image-2",
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
                    print("[DEBUG gpt-image-2] Operation: generate/edit | "
                          f"References sent: {len(imagens_bytes)} | size=1024x1024 | "
                          "input_fidelity=high", file=_sys.stderr)
                    if diagnostico is not None:
                        diagnostico["motor"] = "gpt-image-2 (Responses + tools)"
                        diagnostico["size_pedido"] = "1024x1024"
                        diagnostico["input_fidelity"] = "high"
                        diagnostico["refs_enviadas"] = len(imagens_bytes[:3])
                    return img, None
            except Exception as _e_tool:
                import sys as _sys
                print(f"[DEBUG gpt-image-2] tools recusado ({str(_e_tool)[:120]}) — "
                      "tentando images.edit", file=_sys.stderr)

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
                    model="gpt-image-2",
                    image=arquivos,
                    prompt=prompt_final,
                    size="1024x1024",
                    quality="high",
                    input_fidelity="high",
                )
                _d = edit.data[0]
                if getattr(_d, "b64_json", None):
                    import sys as _sys
                    print("[DEBUG gpt-image-2] Operation: edit | "
                          f"References sent: {len(arquivos)} | size=1024x1024 | "
                          "input_fidelity=high", file=_sys.stderr)
                    if diagnostico is not None:
                        diagnostico["motor"] = "gpt-image-2 (images.edit)"
                        diagnostico["size_pedido"] = "1024x1024"
                        diagnostico["input_fidelity"] = "high"
                        diagnostico["refs_enviadas"] = len(arquivos)
                    return base64.b64decode(_d.b64_json), None
            except Exception as _e_edit:
                import sys as _sys
                print(f"[DEBUG gpt-image-2] images.edit recusado ({str(_e_edit)[:120]}) — "
                      "usando chamada simples", file=_sys.stderr)

            resp = client.responses.create(model="gpt-image-2", input=entrada)
            img = _extrair(resp)
            if img:
                import sys as _sys
                print(f"[DEBUG gpt-image-2] Operation: generate/edit | References sent: {len(imagens_bytes)} | Model: gpt-image-2", file=_sys.stderr)
                if diagnostico is not None:
                    diagnostico["motor"] = "gpt-image-2 (Responses simples — SEM size)"
                    diagnostico["size_pedido"] = "nenhum (modelo escolhe)"
                    diagnostico["refs_enviadas"] = len(imagens_bytes[:3])
                return img, None
            return None, "Sem imagem na resposta Responses API."

        # ── SEM FOTOS: geração texto puro ──
        response = client.images.generate(
            model="gpt-image-2",
            prompt=prompt_final,
            n=1,
            size="1024x1024",
            quality="high",
        )
        img_data = response.data[0]
        # gpt-image-2 retorna b64_json por padrão
        if hasattr(img_data, "b64_json") and img_data.b64_json:
            import sys as _sys
            print(f"[DEBUG gpt-image-2] Operation: generate | References sent: 0 | Model: gpt-image-2 | Quality: high | Size: 1024x1024", file=_sys.stderr)
            return base64.b64decode(img_data.b64_json), None
        # Fallback: URL temporária
        if hasattr(img_data, "url") and img_data.url:
            r = requests.get(img_data.url, timeout=60)
            if r.status_code == 200:
                return r.content, None
        return None, "Sem dados de imagem na resposta OpenAI."
    except Exception as e:
        return None, f"Erro OpenAI gpt-image-2: {str(e)[:300]}"


def gerar_imagem_ia(prompt_texto, imagens_referencia, refs_layout=None,
                    refs_layout_nomes=None, tipo="", diagnostico=None):
    """Arquitetura de geração — fotos do produto vão diretamente ao modelo via Responses API.

    Fluxo:
    1. Claude Vision analisa fotos → descrição de apoio (usada apenas quando não há OpenAI)
    2. Claude descreve estilo das refs de layout (se houver) → texto de composição
    3. Monta prompt único preservando preset completo do tipo (sem double-prompt)
    4. Tenta gpt-image-2 (OpenAI) como motor primário — fotos enviadas diretamente
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
    descricao_produto, estilo_layout = _descrever_produto_via_claude(
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
    #   demais (2 a 7)  -> padrão da marca #E8EEF5
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
        _background = (
            "Soft blue-gray background (#E8EEF5) — clean, professional MS Studio brand standard. "
            "This is MANDATORY: do NOT use plain white for this image type."
        )

    _text_rule = (
        "ZERO TEXT RULE: This image MUST contain ABSOLUTELY NO text, titles, labels, icons, badges, "
        "callouts, or any written element whatsoever. Any visible text is a critical failure."
        if _is_clean_photo else
        "TEXT ZONES RULE: ALL text must appear ONLY in dedicated panel zones completely separate from the "
        "product area. NEVER overlay text directly on the product. Product zone must be clean and text-free."
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

    # ── Extrai conteúdo específico do preset (instruções do tipo, ex: Close, Fundo Branco…) ──
    # Isso resolve o problema do double-prompt: o preset não era passado ao gerador.
    _preset_match = _re.search(
        r"TIPO DE IMAGEM:[^\n]+\n(.*?)(?=\n(?:CONTEXTO INTERNO|REFERÊNCIAS|PADRÃO VISUAL|INSTRUÇÕES VISUAIS|REGRA DE|INSTRUÇÃO DE|MODO |$))",
        prompt_texto, _re.DOTALL
    )
    _preset_content = _preset_match.group(1).strip() if _preset_match else ""

    _tipo_match = _re.search(r"TIPO DE IMAGEM:\s*(.+?)(?:\n|$)", prompt_texto)
    _tipo_str = _tipo_match.group(1).strip() if _tipo_match else "produto"

    # ── Composição específica por tipo (sem regras conflitantes — a regra genérica só aparece
    #    quando o tipo não define a sua própria) ──
    _is_close = (
        "4 — Close" in prompt_texto or
        "CLOSE NO PRODUTO" in prompt_texto
    )
    _is_capa = "1 — Capa" in prompt_texto or "CAPA DO ANÚNCIO" in prompt_texto
    _is_beneficios = "2 — Benefícios do produto" in prompt_texto
    _is_beneficios_cena = "3 — Benefícios no cenário" in prompt_texto
    _is_lifestyle = "8 — Ambientação" in prompt_texto
    _is_presenteie = "7 — Presenteie" in prompt_texto

    # As ocupacoes subiram por decisao do dono: "a distribuicao da imagem dentro
    # dos 1200x1200 precisa ser a maior possivel". Os numeros antigos mandavam
    # o modelo deixar de 40% a 65% do quadro vazio — o produto saia pequeno e
    # longe, e isso nao era desobediencia do modelo, era o que o prompt pedia.
    #
    # "Contextual", sem numero, era pior ainda: sem piso, o modelo escolhia — e
    # escolhia pequeno. Todo tipo agora tem um MINIMO escrito.
    if _is_close:
        _product_dominance_rule = (
            "- COMPOSITION (Close): Detail occupancy 80–92% of frame. Macro close-up. "
            "Do NOT show the full product. Full product: NO."
        )
    elif _is_capa:
        _product_dominance_rule = (
            "- COMPOSITION (Capa): Product occupancy 85–92% of frame. Full product: YES — "
            "completely visible, no cropping. Minimal environment. "
            "The product must nearly touch the edges of the frame — leave only a thin "
            "breathing margin. Empty background is wasted space."
        )
    elif _is_beneficios:
        _product_dominance_rule = (
            "- COMPOSITION (Benefícios): Product occupancy 60–75% of frame — the product "
            "is the subject, the panels are the caption. Full product: preferably YES. "
            "Callouts and benefit panels live in the remaining margin, never shrinking "
            "the product to fit them."
        )
    elif _is_beneficios_cena:
        _product_dominance_rule = (
            "- COMPOSITION (Benefícios no Cenário): Product occupancy at least 45% of "
            "frame. Product is the protagonist; the environment supports it and never "
            "dominates. Full product: preferably YES."
        )
    elif _is_lifestyle:
        _product_dominance_rule = (
            "- COMPOSITION (Lifestyle): Product occupancy at least 35% of frame and "
            "clearly readable at thumbnail size. Full product: optional. "
            "Environment sets the mood but the product stays identifiable."
        )
    elif _is_presenteie:
        _product_dominance_rule = (
            "- COMPOSITION (Presenteie): Product occupancy 55–70% of frame. "
            "Full product: preferably YES. Gift props frame the product, never crowd it."
        )
    else:
        _product_dominance_rule = (
            "- Product occupancy at least 70% of frame — large, prominent, fully visible, "
            "nearly filling the canvas"
        )

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

        f"━━━ SECTION 1: TYPE-SPECIFIC INSTRUCTIONS ━━━\n"
        f"(Follow these exactly. They define the image type and override any conflicting generic rule below.)\n"
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
        + (f"Brand accents: Navy blue (#1A3A6B) for text and graphic elements, "
           f"medium blue (#4A7EC7) as secondary accent.\n"
           f"Typography: Clean geometric sans-serif (Montserrat or Poppins style).\n"
           if not _is_clean_photo else
           "NO brand color anywhere: this image has no text and no graphic "
           "elements, so no brand accent color may appear — not in the "
           "background, not as a tint, not as a gradient.\n")
        + f"Professional e-commerce aesthetic — clean, airy, high-end studio quality.\n\n"

        f"TEXT RULE: {_text_rule}\n\n"

        f"COMPOSITION:\n"
        f"{_product_dominance_rule}\n"
        f"- Maintain product exact proportions — NEVER stretch, compress, or distort\n"
        + ("- Maximum 3 information elements if text present — never cluttered\n"
           if not _is_clean_photo else
           "- No text elements at all, so no whitespace is needed for them: the "
           "product fills the canvas\n")
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
        f"- NEVER add people or human figures unless the image type or collaborator brief explicitly requests them\n"
        f"- All text visible in the image must be in Brazilian Portuguese\n"
        f"- Generate a completely new professional image — not a literal copy of any reference photo"
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

    # 4. Tenta gpt-image-2 (OpenAI) como motor primário
    img_bytes = None
    erro_primario = None
    _usando_openai = bool(_get_openai_api_key())

    if _usando_openai:
        # Passa as fotos do produto diretamente ao gpt-image-2 via Responses API
        # (igual ao ChatGPT) — o modelo VÊ as fotos em vez de receber só texto.
        # Se não houver fotos, cai em geração texto-puro.
        _fotos_para_openai = imagens_referencia if imagens_referencia else None
        img_bytes, erro = _chamar_openai_geracao(
            prompt_geracao, imagens_bytes=_fotos_para_openai,
            ref_layout=_ref_layout_bytes, ref_layout_nome=_ref_layout_nome,
            diagnostico=diagnostico
        )
        if not img_bytes:
            erro_primario = f"OpenAI gpt-image-2: {erro}"

    if diagnostico is not None:
        diagnostico["prompt_final"] = prompt_geracao
        diagnostico["fotos_disponiveis"] = len(imagens_referencia or [])
        if erro_primario:
            diagnostico["erro_openai"] = erro_primario

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
                return None, (
                    "⛔ Cota ou créditos da GEMINI_API_KEY esgotados. "
                    "Crie uma nova chave em aistudio.google.com/apikey vinculada ao projeto GCP "
                    f"e atualize GEMINI_API_KEY no Railway. Detalhe: {msg[:200]}"
                )
            erro_fallback = f"Gemini: {msg[:300]}"
            return None, (f"{erro_primario} | {erro_fallback}" if erro_primario else erro_fallback)

        if resp is None:
            return None, "Falha ao conectar ao gerador de imagem."

        if resp.status_code != 200:
            try:
                _err = resp.json().get("error", {}).get("message", resp.text[:300])
            except Exception:
                _err = resp.text[:300]
            return None, f"Erro HTTP {resp.status_code}: {_err}"

        try:
            dados = resp.json()
        except Exception:
            return None, "Resposta inválida do gerador (não é JSON)."

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
            return None, (
                f"Gerador não retornou imagem (possível bloqueio ou créditos esgotados). "
                f"Detalhe: {_detail}"
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

            # NÃO recortar. Uma tentativa anterior cortava até 18% do lado maior
            # para diminuir as faixas, e isso decepava os painéis de texto das
            # peças de marketing, que ficam justamente nas laterais — frases
            # saíam pela metade. Recorte só destrói conteúdo; preencher, no
            # máximo, deixa margem.
            #
            # A saída de verdade é a imagem já chegar quadrada (size=1024x1024
            # na geração). Isto aqui é o último recurso quando a API recusa o
            # parâmetro — e o log acima registra quando acontece.
            max_dim = max(pil_w, pil_h)
            if _is_fundo_branco:
                bg_color = (255, 255, 255, 255)
            elif _is_ambientacao or _is_personalizado:
                # Cena real: usa a cor média da borda para a faixa desaparecer
                # em vez de virar tarja lisa.
                bg_color = tuple(pil.resize((1, 1), _PILImage.LANCZOS).getpixel((0, 0)))
            else:
                bg_color = (232, 238, 245, 255)  # padrão da marca

            bg = _PILImage.new("RGBA", (max_dim, max_dim), bg_color)
            offset = ((max_dim - pil_w) // 2, (max_dim - pil_h) // 2)
            bg.paste(pil, offset, pil)
            pil = bg

        pil = pil.resize((1200, 1200), _PILImage.LANCZOS)
        buf = _io.BytesIO()
        pil.save(buf, format="PNG")
        img_bytes = buf.getvalue()
    except Exception:
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
            "É PROIBIDO recolorir o produto para harmonizar com a paleta azul da empresa, "
            "com o fundo, com o cenário ou com a iluminação. A paleta da marca vale para "
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
        f"É PROIBIDO recolorir o produto para harmonizar com a paleta da marca, com o "
        f"fundo, com o cenário ou com a iluminação. A paleta azul da empresa vale para "
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


def montar_prompt_imagem(tipo, instrucoes_extras, dados_descricao, nome_produto,
                         refs_layout_nomes=None, instrucao_layout="", plano_triagem=None):
    """Monta o prompt completo para geração.

    Para os tipos padrão (1-7): aplica PADRAO_VISUAL + INSTRUCAO_COMPOSICAO
    (imagens de marketing com identidade visual).

    Para 'Personalizado': aplica INSTRUCAO_PERSONALIZADO sem branding automático
    — a instrução do colaborador é a única fonte de verdade.

    refs_layout_nomes: lista de nomes de arquivo das imagens de referência de layout
    instrucao_layout: texto descrevendo o que cada referência representa
    """
    base = PRESETS.get(tipo, "")

    # ── Bloco do plano da triagem (composição e textos decididos pela IA antes da geração) ──
    bloco_plano_triagem = ""
    if plano_triagem and not (tipo == "Personalizado (descrevo o que quero)"):
        _composicao = plano_triagem.get("composicao", "").strip()
        _textos = [t for t in plano_triagem.get("textos", []) if t and str(t).strip()]
        if _composicao or _textos:
            bloco_plano_triagem = "\nPLANO DE CRIAÇÃO (definido pela análise do produto — siga este planejamento):\n"
            if _composicao:
                bloco_plano_triagem += f"Composição: {_composicao}\n"
            if _textos:
                # "Textos a incluir" era uma SUGESTAO, e o gerador a tratava
                # como tal: reescrevia a frase com as proprias palavras e
                # errava as letras no caminho. A copy ja vem pronta da triagem;
                # aqui ela deixa de ser sugestao e vira o texto literal.
                bloco_plano_triagem += bloco_texto_exato(_textos)

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
{bloco_contexto_interno}
{bloco_refs}

{PADRAO_VISUAL_FUNDO_BRANCO}
{INSTRUCAO_FIDELIDADE}
{INSTRUCAO_PROPORCAO}
{INSTRUCAO_COMPOSICAO}
"""
    elif eh_ambientacao:
        # Tipo 8: ambientação realista — SEM texto (exceto "Imagem meramente ilustrativa")
        PADRAO_VISUAL_AMBIENTACAO = """
PADRÃO VISUAL PARA AMBIENTAÇÃO REALISTA — REGRA ABSOLUTA:
- Cena editorial aspiracional com produto integrado ao ambiente natural de uso
- Use o contexto do produto para escolher o ambiente: escritório, quarto de estudos,
  sala de estar, mesa de trabalho, ou outro ambiente adequado ao produto específico
- Iluminação natural suave, tons neutros, composição elegante
- PROIBIÇÃO DE TEXTO: NENHUM título, headline, benefício, ícone, legenda ou elemento
  gráfico. APENAS a frase discreta "Imagem meramente ilustrativa" no canto inferior
  em tipografia fina e sem destaque. Nada mais escrito.
- Tom de revista de decoração/lifestyle — foto editorial, não peça de marketing
- NUNCA adicione pessoas, modelos ou figuras humanas nesta imagem
"""
        return f"""MS_FUNDO: ambiente
{contexto_produto}
TIPO DE IMAGEM: {tipo}
{base}
{bloco_plano_triagem}
{bloco_contexto_interno}
{bloco_refs}

{PADRAO_VISUAL_AMBIENTACAO}
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
{bloco_contexto_interno}
{bloco_refs}

{PADRAO_VISUAL}
{INSTRUCAO_LAYOUT_MARKETING}
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
    for it in itens:
        if str(it.get("tipo", "")).strip() == str(tipo or "").strip():
            return it
    return None


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
    try:
        chave = st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:
        chave = ""
    return chave or os.environ.get("ANTHROPIC_API_KEY", "")


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
        nova_img, erro_g = gerar(prompt_base + bloco_texto_exato(certo))
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
        _so_arte = bool(st.session_state.get("img_fotos_sao_arte"))
        for _c in refazer_pend:
            _i = int(_c.get("num", 1)) - 1
            if _i < 0 or _i >= len(galeria):
                _msgs_rf.append(f"⚠️ Imagem {_i + 1} não existe.")
                continue
            if not _fotos_rf or _so_arte:
                # Dizer "não dá" é o que faltava. Gerando do zero com a arte
                # errada como referência, ela voltava idêntica — e o
                # assistente anunciava sucesso em cima disso.
                _msgs_rf.append(
                    "⚠️ **Não dá para refazer do zero por aqui.** Esta imagem "
                    "entrou pelo modo Ajuste Fino: o que o Studio tem dela é a "
                    "própria arte, não as fotos do produto — e gerar de novo a "
                    "partir da arte devolve a arte.\n\n"
                    "Para recompor o quadro: aba **Imagem** › **1 imagem "
                    "específica**, suba as fotos do produto e descreva a "
                    "composição em «Descreva o que você quer nessa imagem». "
                    "Para mexer só num ponto, siga pelo Ajuste Fino mesmo.")
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
            try:
                import rascunho as _rasc_rf
                _rasc_rf.salvar(usuario_logado, _nome_rf, galeria,
                                _cfg_rf.get("codigo", ""))
            except Exception:
                pass
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
    with st.expander("🔧 Diagnóstico das APIs de Imagem", expanded=False):
        st.caption("Testa OpenAI gpt-image-2 (motor primário) e Gemini Flash (fallback) para confirmar que estão funcionando.")
        if st.button("Testar APIs agora", key="btn_diag_gemini"):
            # Testa OpenAI
            _oai_key = _get_openai_api_key()
            if _oai_key:
                with st.spinner("Testando OpenAI gpt-image-2..."):
                    import time as _td
                    _t0_oai = _td.time()
                    try:
                        from openai import OpenAI as _OAITest
                        _oai_client = _OAITest(api_key=_oai_key)
                        _oai_resp = _oai_client.images.generate(
                            model="gpt-image-2",
                            prompt="A small red circle on white background, minimal.",
                            n=1, size="1024x1024", quality="low",
                        )
                        _oai_ms = int((_td.time() - _t0_oai) * 1000)
                        _oai_img = getattr(_oai_resp.data[0], "b64_json", None) or getattr(_oai_resp.data[0], "url", None)
                        if _oai_img:
                            st.success(f"✅ **gpt-image-2** — gerou imagem ({_oai_ms}ms)")
                        else:
                            st.warning(f"⚠️ **gpt-image-2** — sem imagem na resposta ({_oai_ms}ms)")
                    except Exception as _e_oai:
                        _oai_ms = int((_td.time() - _t0_oai) * 1000)
                        st.error(f"❌ **gpt-image-2** — {str(_e_oai)[:300]} ({_oai_ms}ms)")
            else:
                st.warning("⚠️ **gpt-image-2** — OPENAI_API_KEY não configurada nas secrets do Railway.")

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
                # roda no Claude, enquanto as imagens saem no gpt-image-2 ou no
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

        # ── Itens viáveis ─────────────────────────────────────────────────────
        for item in itens_viaveis:
            flags = item.get("flags", [])
            with st.container(border=True):
                col_title, col_flag = st.columns([5, 1])
                col_title.markdown(f"**{item.get('numero', '')}. {item.get('tipo', '')}**")
                if flags:
                    col_flag.caption("⚠️ aviso")
                st.caption(item.get("composicao", ""))
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
                tipos_viaveis = [item["tipo"] for item in itens_viaveis]
                tipos = tipos_viaveis if tipos_viaveis else cfg["tipos"]

                import time as _time_gen
                import threading as _threading

                # Indexa os itens da triagem por tipo para lookup rápido
                _plano_por_tipo = {}
                _plano_items = st.session_state.get("img_triagem_plano", {}).get("plano", [])
                for _pi in _plano_items:
                    _plano_por_tipo[_pi.get("tipo", "")] = _pi

                for i, tipo in enumerate(tipos):
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
                        try:
                            import rascunho as _rasc
                            _rasc.salvar(usuario_logado, cfg.get("nome_produto", ""),
                                         galeria, cfg.get("codigo", ""))
                        except Exception:
                            pass
                    except Exception as _e_img:
                        st.warning(f"⚠️ Erro inesperado em '{tipo}': {_e_img}")
                        continue

                barra.progress(1.0, text=f"Concluído! {len(galeria)}/{len(tipos)} imagens geradas.")

                if galeria:
                    for k in [k for k in st.session_state if k.startswith("_pasta_")]:
                        del st.session_state[k]
                    st.session_state["img_galeria"] = galeria
                    st.session_state["img_nome_produto"] = cfg["nome_produto"]
                    st.session_state["img_codigo"] = cfg.get("codigo", "")
                    st.session_state["img_fotos_originais"] = cfg["fotos_bytes"]
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
    ok("registrar_revisao fora da tela nao derruba",
       registrar_revisao({"ok": None, "erro": "x"}) is None)

    conferir_texto = _real
    print("\nfalhas:", falhas)
