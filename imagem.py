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

# Modelo que suporta geraÃ§Ã£o de imagem via generateContent + responseModalities:["IMAGE"]
# gemini-2.0-flash-exp Ã© o modelo confirmado para geraÃ§Ã£o nativa de imagem via generateContent
MODELO_IMAGEM = "gemini-2.0-flash-exp"


class _GeminiRateLimiter:
    """Rate limiter global para a API Gemini â respeita 10 RPM automaticamente.
    Compartilhado entre todas as threads/sessÃµes do processo.
    """
    def __init__(self, rpm=8, window=60):
        self._lock = _threading_limiter.Lock()
        self._calls = _deque()
        self._rpm = rpm        # 8 de 10 disponÃ­veis â margem de seguranÃ§a
        self._window = window  # janela deslizante de 60s

    def aguardar(self):
        """Bloqueia atÃ© que seja seguro fazer uma nova chamada Ã  API."""
        while True:
            with self._lock:
                agora = _time_limiter.time()
                # Descarta chamadas fora da janela
                while self._calls and agora - self._calls[0] >= self._window:
                    self._calls.popleft()
                if len(self._calls) < self._rpm:
                    self._calls.append(agora)
                    return
                # Quanto falta atÃ© a chamada mais antiga sair da janela
                espera = self._window - (agora - self._calls[0]) + 0.2
            _time_limiter.sleep(min(espera, 2))

# Singleton por processo â usa st.cache_resource para sobreviver a reruns E hot-reloads
@st.cache_resource
def _get_gemini_limiter():
    return _GeminiRateLimiter(rpm=8, window=60)

_GEMINI_LIMITER = _get_gemini_limiter()

# ââ PADRÃO VISUAL MARTINSOUSA (hardcoded em todos os prompts) ââââââââââââââââââ
PADRAO_VISUAL = """
PADRÃO VISUAL OBRIGATÃRIO DA EMPRESA (aplique em todas as peÃ§as de marketing):
- Fundo: #E8EEF5 (azul-cinza claro suave)
- Cor principal / texto e elementos grÃ¡ficos: #1A3A6B (azul marinho)
- Cor de destaque secundÃ¡ria: #4A7EC7 (azul mÃ©dio)
- Fonte: Montserrat ou Poppins â nunca fontes serifadas
- Ãcones: estilo line-art clean, traÃ§o fino, monocromÃ¡ticos em azul marinho
- Elementos decorativos: cÃ­rculos ou manchas suaves em azul marinho ou azul mÃ©dio,
  usados como moldura ou destaque atrÃ¡s do produto ou dos Ã­cones
- Texto sempre em portuguÃªs do Brasil, sem erros ortogrÃ¡ficos, sem caixa alta excessiva
- Visual limpo, arejado, profissional â sem poluiÃ§Ã£o visual
- NÃO use marrom, laranja, vermelho ou verde como cores principais
"""

INSTRUCAO_FIDELIDADE = """
REGRA DE FIDELIDADE AO PRODUTO (a mais importante de todas â sem exceÃ§Ãµes):
- Reproduza o produto EXATAMENTE como aparece nas imagens de referÃªncia: mesma cor,
  mesmo formato, mesmas proporÃ§Ãµes, mesmos detalhes visÃ­veis
- PROIBIÃÃO ABSOLUTA: JAMAIS substitua o produto das fotos de referÃªncia por um
  produto diferente, inventado ou genÃ©rico. Se nÃ£o conseguir reproduzir o produto
  num Ã¢ngulo especÃ­fico, use o Ã¢ngulo disponÃ­vel nas fotos â mas NUNCA crie outro
  produto. Gerar um produto diferente Ã© o erro mais grave possÃ­vel nesta tarefa.
- Se uma caracterÃ­stica do produto nÃ£o estiver visÃ­vel nas fotos de referÃªncia e for
  necessÃ¡ria para a composiÃ§Ã£o, adapte a cena para evitar mostrar esse Ã¢ngulo â
  nÃ£o invente como o produto seria naquele Ã¢ngulo
- Nunca deforme, alongue, encurte ou altere qualquer parte do produto
- Nunca crie detalhes que nÃ£o aparecem nas fotos de referÃªncia
- NÃO copie nem reproduza nenhum texto, palavra ou rÃ³tulo que apareÃ§a escrito
  nas fotos de referÃªncia â ignore completamente qualquer texto visÃ­vel nas imagens
- PROIBIÃÃO ABSOLUTA DE INVENTAR DADOS TÃCNICOS: JAMAIS crie, estime ou invente
  medidas, dimensÃµes, peso ou material do produto. Se esses dados nÃ£o foram
  fornecidos nos campos do produto, NÃO os coloque na imagem sob nenhuma hipÃ³tese.
  Imagem com dados inventados Ã© pior do que imagem sem dados.
- SÃ³ use medidas e peso na imagem se eles estiverem EXPLICITAMENTE informados
  nos dados do produto fornecidos â nunca estime por conta prÃ³pria
"""

INSTRUCAO_COMPOSICAO = """
INSTRUÃÃO DE COMPOSIÃÃO:
- Use as imagens de referÃªncia APENAS para manter o produto reconhecÃ­vel e fiel
- Componha uma cena/layout NOVO e apropriado para o tipo de imagem solicitado
- NÃ£o reaproveite a foto de referÃªncia literalmente â crie uma peÃ§a nova
"""

# ââ MODO PERSONALIZADO â sem branding automÃ¡tico ââââââââââââââââââââââââââââââ
INSTRUCAO_PERSONALIZADO = """
MODO PERSONALIZADO â REGRAS ABSOLUTAS:
- Execute EXATAMENTE e SOMENTE o que o colaborador descreveu nas instruÃ§Ãµes
- NÃO adicione texto, legenda, tÃ­tulo, rÃ³tulo ou qualquer elemento escrito
  que nÃ£o tenha sido pedido explicitamente nas instruÃ§Ãµes
- NÃO aplique cores da empresa, fontes especÃ­ficas, Ã­cones ou branding
  a nÃ£o ser que as instruÃ§Ãµes peÃ§am explicitamente por isso
- NÃO crie uma composiÃ§Ã£o "nova" ou "melhorada" por conta prÃ³pria â
  siga a instruÃ§Ã£o, nada mais
- NÃO invente diferenciais, caracterÃ­sticas ou frases de marketing
- As instruÃ§Ãµes do colaborador sÃ£o a ÃNICA fonte de verdade para
  o que deve aparecer nesta imagem
"""

# ââ MODO AJUSTE FINO â ediÃ§Ã£o cirÃºrgica, sem alterar nada alÃ©m do pedido âââââ
INSTRUCAO_AJUSTE_FINO = """
MODO AJUSTE FINO â EDIÃÃO CIRÃRGICA â REGRAS ABSOLUTAS E INVIOLÃVEIS:

1. FaÃ§a SOMENTE a modificaÃ§Ã£o descrita na instruÃ§Ã£o â absolutamente nada mais
2. Preserve a composiÃ§Ã£o inteira: fundo, cenÃ¡rio, iluminaÃ§Ã£o, cores, perspectiva,
   todos os objetos e todos os detalhes visuais
3. Preserve exatamente todos os textos que jÃ¡ existem na imagem
   (nÃ£o adicione nem remova nenhum texto)
4. Preserve a aparÃªncia exata do produto: mesma cor, mesmos detalhes,
   mesmos elementos visÃ­veis (furos, padrÃµes, logotipos na embalagem, etc.)
5. NÃO "melhore", "enriqueÃ§a", "atualize" ou "harmonize" nada alÃ©m do pedido
6. NÃO aplique identidade visual, branding, cores ou fontes da empresa
7. NÃO adicione nenhum objeto, efeito, texto ou elemento nÃ£o mencionado
8. Se a instruÃ§Ã£o pedir redimensionar o produto: altere APENAS o tamanho relativo
   do produto dentro da cena â todo o resto permanece pixel-a-pixel idÃªntico
9. Se nÃ£o tiver certeza de algo que nÃ£o foi mencionado, mantenha como estÃ¡
"""

# ââ PRESETS ATUALIZADOS COM IDENTIDADE VISUAL âââââââââââââââââââââââââââââââââ
TIPOS_PADRAO = [
    "1 â Produto com fundo branco",
    "2 â BenefÃ­cios do produto",
    "3 â BenefÃ­cios no cenÃ¡rio de uso",
    "4 â Close nos detalhes",
    "5 â CaracterÃ­sticas tÃ©cnicas (medidas/peso/material)",
    "6 â Quebra de objeÃ§Ã£o",
    "7 â Presenteie",
]

PRESETS = {
    "Personalizado (descrevo o que quero)": "",
    "1 â Produto com fundo branco": (
        "Foto de produto limpa e profissional, fundo branco liso, produto centralizado e bem iluminado, "
        "iluminaÃ§Ã£o de estÃºdio suave sem sombras duras, sem texto sobreposto, sem elementos extras. "
        "O produto deve ocupar 70-80% do frame."
    ),
    "2 â BenefÃ­cios do produto": (
        "PeÃ§a de marketing mostrando os principais benefÃ­cios do produto. "
        "Layout: produto em destaque no centro ou Ã  esquerda, Ã  direita blocos verticais empilhados "
        "com Ã­cone line-art + tÃ­tulo curto (2-3 palavras) + frase explicativa (1 linha). "
        "MÃ¡ximo 4 benefÃ­cios. TÃ­tulo principal em destaque no topo."
    ),
    "3 â BenefÃ­cios no cenÃ¡rio de uso": (
        "PeÃ§a de marketing mostrando o produto sendo usado em um cenÃ¡rio real do dia a dia. "
        "Cena realista e aspiracional com iluminaÃ§Ã£o natural. "
        "Frases curtas de destaque flutuando sobre ou ao lado do produto, explicando o benefÃ­cio "
        "daquele momento de uso especÃ­fico. Tom acolhedor e moderno."
    ),
    "4 â Close nos detalhes": (
        "Imagem em zoom aproximado valorizando os acabamentos e qualidade do produto. "
        "Pequenas setas ou linhas finas apontando para cada detalhe, com legenda curta ao lado. "
        "Foco em textura, material, costuras, encaixe, ou qualquer acabamento que diferencie o produto. "
        "MÃ¡ximo 4 pontos de destaque."
    ),
    "5 â CaracterÃ­sticas tÃ©cnicas (medidas/peso/material)": (
        "Imagem tÃ©cnica do produto com linhas de medida estilo desenho tÃ©cnico, mostrando as dimensÃµes "
        "exatas (altura, largura, profundidade). Peso e material indicados com Ã­cones tÃ©cnicos. "
        "Dados anotados de forma clara e legÃ­vel. Fundo claro, visual limpo e tÃ©cnico."
    ),
    "6 â Quebra de objeÃ§Ã£o": (
        "PeÃ§a de marketing respondendo as principais dÃºvidas de quem estÃ¡ prestes a comprar. "
        "Formato: 3 a 4 blocos, cada um com uma objeÃ§Ã£o comum em forma de pergunta curta e a "
        "resposta direta e tranquilizadora ao lado ou abaixo. Ãcone de check ou escudo. "
        "Tom de confianÃ§a e credibilidade."
    ),
    "7 â Presenteie": (
        "PeÃ§a de marketing emocional incentivando a compra do produto como presente. "
        "Frase principal de impacto emocional em destaque (ex: 'O presente certo para quem vocÃª ama'). "
        "ComposiÃ§Ã£o com laÃ§o, embrulho ou contexto de presente. Tom acolhedor e especial. "
        "Cena mostrando a entrega ou o momento de surpresa com reaÃ§Ã£o positiva."
    ),
}


# ââ TRIAGEM POR IA (anÃ¡lise textual, sem gastar com geraÃ§Ã£o) ââââââââââââââââââ

def gerar_triagem_ia(nome_produto, tipos_selecionados, dados_descricao, instrucoes_extras, fotos_bytes):
    """Pede para a IA analisar o que ela criaria para cada tipo de imagem,
    ANTES de gastar com a geraÃ§Ã£o real. Retorna lista de dicts com o plano."""
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None, "ANTHROPIC_API_KEY nÃ£o configurada."

    tipos_str = "\n".join(f"- {t}: {PRESETS.get(t,'')[:120]}..." for t in tipos_selecionados)

    contexto_descricao = ""
    if dados_descricao:
        contexto_descricao = f"""
DADOS DA DESCRIÃÃO DO PRODUTO (vinculados pelo cÃ³digo):
- Cor: {dados_descricao.get('cor', 'nÃ£o informada')}
- Medidas: {dados_descricao.get('medidas', 'nÃ£o informadas')}
- Categoria: {dados_descricao.get('categoria', 'nÃ£o informada')}
- Diferenciais: {dados_descricao.get('diferenciais', 'nÃ£o informados')}
- CaracterÃ­sticas: {dados_descricao.get('caracteristicas', 'nÃ£o informadas')}
- Uso: {dados_descricao.get('uso', 'nÃ£o informado')}
"""

    # Verifica quais dados tÃ©cnicos estÃ£o disponÃ­veis para informar a IA
    dados_disponiveis = []
    dados_faltantes = []
    if dados_descricao:
        if dados_descricao.get("medidas"): dados_disponiveis.append(f"medidas: {dados_descricao['medidas']}")
        else: dados_faltantes.append("medidas (altura Ã largura Ã profundidade)")
        if dados_descricao.get("peso"): dados_disponiveis.append(f"peso: {dados_descricao['peso']}")
        else: dados_faltantes.append("peso")
        if dados_descricao.get("cor"): dados_disponiveis.append(f"cor: {dados_descricao['cor']}")
        if dados_descricao.get("material") or dados_descricao.get("caracteristicas"):
            dados_disponiveis.append("material/caracterÃ­sticas informados")
        else: dados_faltantes.append("material")
    else:
        dados_faltantes = ["medidas", "peso", "material"]

    resumo_dados = ""
    if dados_disponiveis:
        resumo_dados += f"Dados disponÃ­veis: {', '.join(dados_disponiveis)}\n"
    if dados_faltantes:
        resumo_dados += f"Dados NÃO informados (nÃ£o inventar): {', '.join(dados_faltantes)}\n"

    prompt = f"""VocÃª Ã© especialista em imagens para e-commerce no Mercado Livre. Seja BREVE e DIRETO.

PRODUTO: {nome_produto}
{contexto_descricao}
{resumo_dados}
FOTOS ENVIADAS: {len(fotos_bytes)} foto(s) de referÃªncia
{f"INSTRUÃÃES EXTRAS: {instrucoes_extras}" if instrucoes_extras else ""}

TIPOS A CRIAR:
{tipos_str}

TAREFA: Para cada tipo, analise se Ã© VIÃVEL gerar com as informaÃ§Ãµes e fotos disponÃ­veis.

REGRAS DE VIABILIDADE â CRÃTICO:
1. "CaracterÃ­sticas tÃ©cnicas (medidas/peso/material)" â SOMENTE viÃ¡vel se medidas E peso estiverem nos dados disponÃ­veis acima. Se qualquer um faltar, marque viavel: false e peÃ§a os dados exatos.
2. "Close nos detalhes" ou qualquer tipo que exija Ã¢ngulo do produto NÃO disponÃ­vel nas fotos â viavel: false, peÃ§a a foto naquele Ã¢ngulo.
3. Qualquer tipo que necessite de informaÃ§Ã£o especÃ­fica ausente (ex: cores disponÃ­veis, voltagem, compatibilidade) â viavel: false, peÃ§a a informaÃ§Ã£o.
4. NUNCA marque como viÃ¡vel se for necessÃ¡rio INVENTAR qualquer dado tÃ©cnico, dimensÃ£o ou caracterÃ­stica.

Quando viavel: false, preencha "pergunta_info" com pergunta direta e especÃ­fica ao colaborador explicando exatamente o que falta e por quÃª Ã© necessÃ¡rio. Essa imagem serÃ¡ DESCARTADA atÃ© a informaÃ§Ã£o ser fornecida.

Quando viavel: true, descreva em 1-2 frases o que serÃ¡ criado.

Responda SOMENTE com JSON vÃ¡lido, sem texto antes ou depois:
{{
  "plano": [
    {{
      "tipo": "nome do tipo",
      "numero": 1,
      "composicao": "1-2 frases curtas descrevendo a imagem (sÃ³ se viavel: true)",
      "textos": ["texto 1", "texto 2"],
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
            messages=[{"role": "user", "content": prompt}]
        )
        texto = msg.content[0].text.strip()

        # Se a resposta foi cortada (max_tokens atingido), avisa mas tenta salvar
        truncado = msg.stop_reason == "max_tokens"

        # ââ ExtraÃ§Ã£o robusta de JSON âââââââââââââââââââââââââââââââââââââââââââ
        import re as _re

        def _tentar_parse(s):
            try:
                return json.loads(s)
            except Exception:
                return None

        resultado = None

        # 1. Texto direto
        resultado = _tentar_parse(texto)

        # 2. Bloco ```json ... ``` (regex, mais confiÃ¡vel que split)
        if resultado is None:
            m = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texto, _re.DOTALL)
            if m:
                resultado = _tentar_parse(m.group(1))

        # 3. Primeiro { atÃ© o Ãºltimo }
        if resultado is None:
            start = texto.find("{")
            end = texto.rfind("}")
            if start != -1 and end > start:
                resultado = _tentar_parse(texto[start:end + 1])

        if resultado is not None:
            return resultado, None

        # ââ Fallback: plano bÃ¡sico com presets ââââââââââââââââââââââââââââââââ
        motivo = (
            "resposta da IA truncada (max_tokens atingido)" if truncado
            else "resposta da IA nÃ£o estava em formato JSON vÃ¡lido"
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
                f"â ï¸ A triagem detalhada nÃ£o pÃ´de ser gerada ({motivo}). "
                "O plano abaixo usa os presets padrÃ£o de cada tipo. "
                "Revise as instruÃ§Ãµes antes de confirmar a geraÃ§Ã£o."
            ),
        }
        return plano_fallback, None

    except Exception as e:
        return None, str(e)


# ââ GERAÃÃO DE IMAGEM (Gemini) âââââââââââââââââââââââââââââââââââââââââââââââââ

def _detectar_mime(data: bytes) -> str:
    """Detecta o MIME type real da imagem pelos magic bytes."""
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if data[:2] == b'\xff\xd8':
        return "image/jpeg"
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return "image/webp"
    return "image/jpeg"  # fallback seguro


def _gerar_imagem_thread(prompt_texto, imagens_ref, resultado):
    """Executa gerar_imagem_ia em thread separada para nÃ£o bloquear o WebSocket."""
    try:
        img, erro = gerar_imagem_ia(prompt_texto, imagens_ref)
        resultado["img"] = img
        resultado["erro"] = erro
    except Exception as e:
        resultado["img"] = None
        resultado["erro"] = str(e)
    finally:
        resultado["done"] = True


def _chamar_gemini(api_key, modelo, body):
    """Faz uma chamada ao Gemini com retry em 429 e retorna (resp, erro_fatal).
    erro_fatal = string â nÃ£o tente mais. resp = None â erro recuperÃ¡vel.
    """
    import time as _time
    MAX_TENTATIVAS = 2
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            _GEMINI_LIMITER.aguardar()
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=body, timeout=120,
            )
            if resp.status_code == 429:
                try:
                    _ej = resp.json()
                    _msg = _ej.get("error", {}).get("message", resp.text[:300])
                    _st  = _ej.get("error", {}).get("status", "")
                except Exception:
                    _msg = resp.text[:300]
                    _st  = ""
                _cota = any(k in _msg.lower() for k in [
                    "quota", "daily", "exhausted", "exceeded your current quota",
                    "resource_exhausted",
                ]) or _st == "RESOURCE_EXHAUSTED"
                if _cota:
                    # Cota esgotada â nÃ£o adianta esperar; sinaliza para tentar fallback
                    return None, f"COTA_ESGOTADA:{_msg[:200]}"
                if tentativa >= MAX_TENTATIVAS:
                    return None, f"HTTP 429: {_msg[:200]}"
                _ra = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
                espera = max(int(_ra), 5) if _ra and _ra.isdigit() else 60
                _time.sleep(espera)
                continue
            return resp, None
        except Exception as e:
            if tentativa >= MAX_TENTATIVAS:
                return None, str(e)
            _time.sleep(5)
    return None, "MÃ¡ximo de tentativas atingido."


def gerar_imagem_ia(prompt_texto, imagens_referencia):
    """Gera imagem via Gemini. Retorna (imagem_bytes, erro_ou_None)."""
    api_key = st.secrets.get("GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None, "GEMINI_API_KEY nÃ£o configurada nas Secrets."

    parts = [{"text": prompt_texto}]
    for img_bytes in imagens_referencia:
        parts.append({
            "inline_data": {
                "mime_type": _detectar_mime(img_bytes),
                "data": base64.b64encode(img_bytes).decode("utf-8"),
            }
        })
    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }

    resp, erro_fatal = _chamar_gemini(api_key, MODELO_IMAGEM, body)
    if erro_fatal:
        msg_detalhe = erro_fatal.replace("COTA_ESGOTADA:", "")
        if erro_fatal.startswith("COTA_ESGOTADA:"):
            return None, (
                f"â Cota diÃ¡ria da API Gemini esgotada (modelo: {MODELO_IMAGEM}). "
                "Aguarde atÃ© amanhÃ£ (meia-noite horÃ¡rio de BrasÃ­lia) ou verifique "
                "console.cloud.google.com â APIs â Gemini API â Cotas. "
                f"Detalhe: {msg_detalhe[:200]}"
            )
        return None, f"Erro ao chamar a API Gemini: {msg_detalhe[:300]}"

    if resp is None:
        return None, f"Falha ao conectar ao modelo {MODELO_IMAGEM}."

    if resp.status_code != 200:
        try:
            _err = resp.json().get("error", {}).get("message", resp.text[:300])
        except Exception:
            _err = resp.text[:300]
        return None, f"Erro HTTP {resp.status_code}: {_err}"

    try:
        dados = resp.json()
    except Exception:
        return None, "Resposta invÃ¡lida da API (nÃ£o Ã© JSON)."

    candidatos = dados.get("candidates", [])
    if not candidatos:
        return None, "A IA nÃ£o retornou nenhuma imagem (resposta vazia â possÃ­vel bloqueio de conteÃºdo)."

    for parte in candidatos[0].get("content", {}).get("parts", []):
        inline = parte.get("inlineData") or parte.get("inline_data")
        if inline and inline.get("data"):
            img_bytes_raw = base64.b64decode(inline["data"])
            try:
                from PIL import Image as _PILImage
                import io as _io
                pil = _PILImage.open(_io.BytesIO(img_bytes_raw)).convert("RGBA")
                pil = pil.resize((1200, 1200), _PILImage.LANCZOS)
                buf = _io.BytesIO()
                pil.save(buf, format="PNG")
                img_bytes_raw = buf.getvalue()
            except Exception:
                pass
            return img_bytes_raw, None

    return None, "A IA respondeu mas nÃ£o incluiu imagem (pode ter bloqueado o conteÃºdo)."


INSTRUCAO_REFERENCIA_LAYOUT = """
IMAGENS DE REFERÃNCIA DE LAYOUT â REGRAS ABSOLUTAS:
- As imagens de referÃªncia de layout mostram COMPOSIÃÃO, POSIÃÃO, ESTILO e ESTRUTURA visual
- O produto nessas imagens de referÃªncia NÃO Ã o produto a ser gerado â Ã© apenas um exemplo de layout
- USE das referÃªncias: posicionamento, hierarquia de elementos, estilo de texto, uso de pessoas/cenÃ¡rios
- NÃO USE das referÃªncias: o produto em si, cores do produto de referÃªncia, marcas ou logotipos visÃ­veis
- Aplique o layout/composiÃ§Ã£o da referÃªncia ao PRODUTO DO COLABORADOR com as cores MartinSousa
- Se o arquivo de referÃªncia tiver nome indicando o tipo (ex: "fundo_branco", "beneficios"), essa referÃªncia se aplica especificamente Ã quele tipo de imagem
"""


def montar_prompt_imagem(tipo, instrucoes_extras, dados_descricao, nome_produto,
                         refs_layout_nomes=None, instrucao_layout=""):
    """Monta o prompt completo para geraÃ§Ã£o.

    Para os tipos padrÃ£o (1-7): aplica PADRAO_VISUAL + INSTRUCAO_COMPOSICAO
    (imagens de marketing com identidade visual).

    Para 'Personalizado': aplica INSTRUCAO_PERSONALIZADO sem branding automÃ¡tico
    â a instruÃ§Ã£o do colaborador Ã© a Ãºnica fonte de verdade.

    refs_layout_nomes: lista de nomes de arquivo das imagens de referÃªncia de layout
    instrucao_layout: texto descrevendo o que cada referÃªncia representa
    """
    base = PRESETS.get(tipo, "")

    contexto_produto = f"PRODUTO: {nome_produto}\n"
    if dados_descricao:
        if dados_descricao.get("cor"):
            contexto_produto += f"Cor: {dados_descricao['cor']}\n"
        if dados_descricao.get("medidas"):
            contexto_produto += f"Medidas EXATAS (use esses nÃºmeros, nÃ£o invente): {dados_descricao['medidas']}\n"
        if dados_descricao.get("peso"):
            contexto_produto += f"Peso EXATO (use esse nÃºmero, nÃ£o invente): {dados_descricao['peso']}\n"
        if dados_descricao.get("diferenciais"):
            contexto_produto += f"Diferenciais principais: {dados_descricao['diferenciais'][:200]}\n"

    bloco_instrucoes = (
        f"\nINSTRUÃÃES DO COLABORADOR (siga com precisÃ£o):\n{instrucoes_extras}"
        if instrucoes_extras else ""
    )

    # Bloco de referÃªncias de layout
    bloco_refs = ""
    if refs_layout_nomes:
        nomes_str = ", ".join(refs_layout_nomes)
        bloco_refs = f"\nREFERÃNCIAS DE LAYOUT FORNECIDAS: {nomes_str}"
        if instrucao_layout:
            bloco_refs += f"\nO que cada referÃªncia representa: {instrucao_layout}"
        bloco_refs += f"\n{INSTRUCAO_REFERENCIA_LAYOUT}"

    eh_personalizado = (tipo == "Personalizado (descrevo o que quero)")

    if eh_personalizado:
        # Modo personalizado: SEM branding automÃ¡tico, SEM nova composiÃ§Ã£o forÃ§ada
        # A instruÃ§Ã£o do colaborador define tudo.
        return f"""{contexto_produto}
TIPO DE IMAGEM: Personalizado
{bloco_instrucoes}
{bloco_refs}

{INSTRUCAO_PERSONALIZADO}
{INSTRUCAO_FIDELIDADE}
"""
    else:
        # Tipos padrÃ£o (1-7): imagens de marketing com identidade visual completa
        return f"""{contexto_produto}
TIPO DE IMAGEM: {tipo}
{base}
{bloco_instrucoes}
{bloco_refs}

{PADRAO_VISUAL}
{INSTRUCAO_FIDELIDADE}
{INSTRUCAO_COMPOSICAO}
"""


def montar_prompt_ajuste_fino(instrucao):
    """Monta prompt para ediÃ§Ã£o cirÃºrgica de uma imagem existente.

    NÃO aplica PADRAO_VISUAL, NÃO aplica INSTRUCAO_COMPOSICAO.
    Instrui a IA a fazer SOMENTE a modificaÃ§Ã£o descrita, preservando tudo o mais.
    """
    return f"""MODO AJUSTE FINO â EDIÃÃO CIRÃRGICA DE IMAGEM EXISTENTE

A imagem fornecida Ã© a imagem atual que deve ser editada.

MODIFICAÃÃO SOLICITADA â o Ãºnico e exclusivo ponto a alterar:
{instrucao}

{INSTRUCAO_AJUSTE_FINO}

Reproduza a imagem fornecida com fidelidade absoluta, aplicando APENAS a modificaÃ§Ã£o acima.
Trate qualquer elemento que nÃ£o foi mencionado na instruÃ§Ã£o como intocÃ¡vel.
"""


# ââ GOOGLE DRIVE â GESTÃO DE PASTAS âââââââââââââââââââââââââââââââââââââââââââ

def _drive_service():
    from googleapiclient.discovery import build
    from google.oauth2.service_account import Credentials
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(
        creds_dict, scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)


def buscar_pasta_produto(nome_produto, codigo, pasta_pai_id):
    """Busca pasta exata '[Nome] - [CÃ³digo]' ou pelo nome aproximado.
    Retorna lista de (id, name) encontrados."""
    try:
        service = _drive_service()
        nome_exato = f"{nome_produto} - {codigo}".strip(" -")

        # Tenta nome exato primeiro
        q = (f"'{pasta_pai_id}' in parents and mimeType='application/vnd.google-apps.folder' "
             f"and name='{nome_exato}' and trashed=false")
        res = service.files().list(q=q, fields="files(id,name)").execute()
        if res.get("files"):
            return [(f["id"], f["name"]) for f in res["files"]]

        # Busca por trecho do nome do produto (fuzzy)
        if nome_produto:
            palavras = nome_produto.split()[:2]  # primeiras 2 palavras
            for palavra in palavras:
                if len(palavra) < 3:
                    continue
                q2 = (f"'{pasta_pai_id}' in parents and mimeType='application/vnd.google-apps.folder' "
                      f"and name contains '{palavra}' and trashed=false")
                res2 = service.files().list(q=q2, fields="files(id,name)").execute()
                if res2.get("files"):
                    return [(f["id"], f["name"]) for f in res2["files"]]
        return []
    except Exception:
        return []


def criar_pasta_produto(nome_pasta, pasta_pai_id):
    """Cria nova pasta no Drive. Retorna (id, erro)."""
    try:
        service = _drive_service()
        metadata = {
            "name": nome_pasta,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [pasta_pai_id],
        }
        pasta = service.files().create(body=metadata, fields="id").execute()
        return pasta["id"], None
    except Exception as e:
        return None, str(e)


def upload_para_pasta(imagem_bytes, nome_arquivo, pasta_id):
    """Faz upload de imagem para pasta especÃ­fica. Retorna (link, erro)."""
    from googleapiclient.http import MediaInMemoryUpload
    try:
        service = _drive_service()
        metadata = {"name": nome_arquivo, "parents": [pasta_id]}
        media = MediaInMemoryUpload(imagem_bytes, mimetype="image/png")
        arquivo = service.files().create(
            body=metadata, media_body=media, fields="id, webViewLink"
        ).execute()
        service.permissions().create(
            fileId=arquivo["id"],
            body={"role": "reader", "type": "anyone"}
        ).execute()
        return arquivo.get("webViewLink"), None
    except Exception as e:
        return None, str(e)


def criar_zip_galeria(galeria, nome_produto):
    """Cria ZIP em memÃ³ria com todas as imagens da galeria. Retorna bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for g in galeria:
            nome_arquivo = f"{nome_produto}_{g['tipo'][:30]}.png"
            nome_arquivo = "".join(c if c.isalnum() or c in "._- " else "_" for c in nome_arquivo)
            zf.writestr(nome_arquivo, g["bytes"])
    buf.seek(0)
    return buf.read()


# ââ INTERFACE PRINCIPAL ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def _testar_gemini_api():
    """Testa a API Gemini com geraÃ§Ã£o real de imagem (prompt mÃ­nimo, sem foto de referÃªncia).
    Retorna dict com resultados por modelo.
    """
    import time as _t_diag
    api_key = st.secrets.get("GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return {"erro_geral": "GEMINI_API_KEY nÃ£o configurada nas Secrets do Railway."}

    body_teste = {
        "contents": [{"parts": [{"text": "Draw a small red circle on a white background. Simple and minimal."}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }

    resultados = {"key_prefixo": f"{api_key[:6]}â¦{api_key[-4:]}"}
    for modelo in [MODELO_IMAGEM]:
        t0 = _t_diag.time()
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=body_teste, timeout=60,
            )
            ms = int((_t_diag.time() - t0) * 1000)
            if r.status_code == 200:
                dados = r.json()
                tem_imagem = any(
                    (p.get("inlineData") or p.get("inline_data", {}))
                    for c in dados.get("candidates", [])
                    for p in c.get("content", {}).get("parts", [])
                )
                resultados[modelo] = {"ok": True, "ms": ms, "tem_imagem": tem_imagem}
            else:
                try:
                    err = r.json().get("error", {})
                    msg = f"HTTP {r.status_code} â {err.get('status','')} â {err.get('message','')[:250]}"
                except Exception:
                    msg = f"HTTP {r.status_code} â {r.text[:250]}"
                resultados[modelo] = {"ok": False, "ms": ms, "erro": msg}
        except Exception as e:
            resultados[modelo] = {"ok": False, "ms": int((_t_diag.time() - t0)*1000), "erro": str(e)}
    return resultados


def pagina_imagem(usuario_logado):
    st.subheader("Imagem")
    st.caption("Gere imagens profissionais para o anÃºncio. A IA mostra o que vai criar antes de gastar com a geraÃ§Ã£o.")

    with st.expander("ð§ DiagnÃ³stico da API Gemini", expanded=False):
        st.caption("Gera uma imagem de teste em cada modelo para confirmar qual estÃ¡ funcionando. Gasta um pouco de cota.")
        if st.button("Testar geraÃ§Ã£o agora", key="btn_diag_gemini"):
            with st.spinner(f"Testando modelo {MODELO_IMAGEM} (pode levar ~30s)..."):
                d = _testar_gemini_api()
            if "erro_geral" in d:
                st.error(d["erro_geral"])
            else:
                st.caption(f"Chave: `{d.get('key_prefixo','?')}`")
                info = d.get(MODELO_IMAGEM, {})
                if info.get("ok"):
                    icone = "â" if info.get("tem_imagem") else "â ï¸"
                    label = "gerou imagem" if info.get("tem_imagem") else "respondeu mas sem imagem"
                    st.success(f"{icone} **{MODELO_IMAGEM}** â {label} ({info['ms']}ms)")
                else:
                    st.error(f"â **{MODELO_IMAGEM}** â {info.get('erro','erro desconhecido')} ({info.get('ms',0)}ms)")

    # ââ RE-RUN AUTOMÃTICO DA TRIAGEM (disparado pelo chat ao preencher dados) ââ
    if st.session_state.pop("img_rerun_triagem", False):
        cfg = st.session_state.get("img_triagem_config")
        if cfg and cfg.get("tipos"):
            with st.spinner("â»ï¸ O Assistente IA atualizou os dados â refazendo a anÃ¡lise..."):
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
                    pass  # silencioso â triagem antiga continua visÃ­vel
            st.rerun()

    # ââ LINHA 1: Nome + CÃ³digo âââââââââââââââââââââââââââââââââââââââââââââââââ
    # PrÃ©-preenche via session_state (evita bug RemoveChild do React ao usar
    # value= com pop() durante re-renders causados por paste/autocomplete)
    if "img_nome_importado" in st.session_state:
        st.session_state["img_nome_produto_input"] = st.session_state.pop("img_nome_importado")
    if "img_codigo_importado" in st.session_state:
        st.session_state["img_codigo_input"] = st.session_state.pop("img_codigo_importado")

    col_nome, col_cod = st.columns(2)
    with col_nome:
        nome_produto = st.text_input(
            "Nome do produto",
            key="img_nome_produto_input",
        )
    with col_cod:
        codigo_input = st.text_input(
            "CÃ³digo da descriÃ§Ã£o (opcional)",
            key="img_codigo_input",
            placeholder="ex: MS-BENG-07174K2  (gerado na aba DescriÃ§Ã£o)",
            help="Gere uma descriÃ§Ã£o na aba DescriÃ§Ã£o â o cÃ³digo aparece num bloco azul no final. Copie e cole aqui. O nome do produto nÃ£o Ã© o cÃ³digo.",
        )

    # Busca dados da descriÃ§Ã£o pelo cÃ³digo
    dados_descricao = None
    if codigo_input:
        import atividades as _atv
        dados_descricao = _atv.buscar_por_codigo(codigo_input)
        if dados_descricao:
            st.success(
                f"â DescriÃ§Ã£o encontrada: **{dados_descricao.get('nome_produto','')}** Â· "
                f"Cor: {dados_descricao.get('cor') or 'â'} Â· "
                f"Medidas: {dados_descricao.get('medidas') or 'â'}"
            )
        else:
            st.warning("CÃ³digo nÃ£o encontrado no histÃ³rico. Pode continuar â sÃ³ nÃ£o haverÃ¡ vÃ­nculo com a descriÃ§Ã£o.")

    # TambÃ©m usa dados do session_state do mÃ³dulo de descriÃ§Ã£o se o usuÃ¡rio
    # acabou de gerar na mesma sessÃ£o e ainda nÃ£o copiou o cÃ³digo
    if not dados_descricao and st.session_state.get("desc_codigo_atual") == codigo_input and codigo_input:
        dados_descricao = st.session_state.get("desc_dados_atual")

    # ââ O QUE GERAR â escolha antes de ver opÃ§Ãµes especÃ­ficas âââââââââââââââââ
    st.markdown("---")
    modo = st.radio(
        "O que gerar?",
        ["1 imagem especÃ­fica", "Selecionar", "As 7 imagens do padrÃ£o", "âï¸ Ajuste Fino"],
        horizontal=True,
        key="img_modo",
    )

    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    # MODO AJUSTE FINO â ediÃ§Ã£o cirÃºrgica de imagem existente
    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    if modo == "âï¸ Ajuste Fino":
        st.info(
            "**âï¸ Ajuste Fino** â envie a imagem que deseja modificar e descreva "
            "**somente** o que deve mudar. A IA preservarÃ¡ tudo o mais exatamente igual."
        )

        fotos_ajuste_upload = st.file_uploader(
            "Imagem a ajustar (JPG, PNG, WebP)",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            key="img_ajuste_upload",
            help="Suba a(s) imagem(ns) que deseja editar. Pode enviar mais de uma variante ao mesmo tempo.",
        )
        fotos_bytes_ajuste = [f.getvalue() for f in fotos_ajuste_upload] if fotos_ajuste_upload else []

        if fotos_bytes_ajuste:
            _cols_aj = st.columns(4)
            for _i, _fb in enumerate(fotos_bytes_ajuste[:4]):
                _cols_aj[_i].image(_fb, use_container_width=True)
            if len(fotos_bytes_ajuste) > 4:
                st.caption(f"+ {len(fotos_bytes_ajuste) - 4} imagem(ns) adicional(is) carregada(s).")

        instrucao_ajuste = st.text_area(
            "O que vocÃª quer modificar? (descreva SOMENTE o que deve mudar â nÃ£o explique o que deve ficar igual)",
            height=120,
            placeholder=(
                "ex: Diminua o tamanho do produto para que fique em proporÃ§Ã£o realista ao cenÃ¡rio. "
                "O produto mede aproximadamente 18cm.\n\n"
                "NÃO descreva o que jÃ¡ estÃ¡ certo â a IA vai preservar tudo que vocÃª nÃ£o mencionar."
            ),
            key="img_instrucao_ajuste",
        )

        st.markdown("---")
        if st.button(
            "âï¸ Aplicar Ajuste Fino",
            type="primary",
            use_container_width=True,
            disabled=(not fotos_bytes_ajuste or not instrucao_ajuste.strip()),
        ):
            if not fotos_bytes_ajuste:
                st.warning("Suba a imagem que deseja ajustar.")
                st.stop()
            if not instrucao_ajuste.strip():
                st.warning("Descreva o que vocÃª quer modificar.")
                st.stop()

            import time as _time_af
            import threading as _threading_af
            prompt_af = montar_prompt_ajuste_fino(instrucao_ajuste.strip())
            _res_af = {"img": None, "erro": None, "done": False}
            _threading_af.Thread(
                target=_gerar_imagem_thread,
                args=(prompt_af, fotos_bytes_ajuste, _res_af),
                daemon=True,
            ).start()
            _slot_af = st.empty()
            _t0_af = _time_af.time()
            while not _res_af["done"]:
                _seg_af = int(_time_af.time() - _t0_af)
                if _seg_af >= 300:
                    _res_af["erro"] = "Tempo limite de 5 min atingido. Tente novamente."
                    _res_af["done"] = True
                    break
                _slot_af.caption(f"â³ Aplicando ajuste fino... {_seg_af}s")
                _time_af.sleep(1)
            _slot_af.empty()
            img_bytes_af, erro_af = _res_af["img"], _res_af["erro"]

            if erro_af:
                st.error(f"â Erro ao aplicar ajuste: {erro_af}")
            else:
                galeria_atual = st.session_state.get("img_galeria", [])
                galeria_atual.append({
                    "tipo": f"Ajuste Fino â {instrucao_ajuste[:40]}...",
                    "bytes": img_bytes_af,
                    "aprovado": False,
                })
                st.session_state["img_galeria"] = galeria_atual
                st.session_state["img_nome_produto"] = nome_produto or "produto-ajustado"
                st.session_state["img_codigo"] = codigo_input
                st.session_state["img_fotos_originais"] = fotos_bytes_ajuste
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

    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    # MODOS PADRÃO â fotos de referÃªncia + triagem + geraÃ§Ã£o
    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    else:
        # ââ FOTOS DE REFERÃNCIA DO PRODUTO ââââââââââââââââââââââââââââââââââââ
        st.markdown("**Fotos de referÃªncia do produto**")
        st.caption("Suba quantas fotos quiser â Ã¢ngulos diferentes ajudam a IA a ser mais fiel.")
        fotos_upload = st.file_uploader(
            "Fotos do produto (JPG, PNG, WebP)",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            key="img_fotos_upload",
        )
        fotos_bytes = [f.getvalue() for f in fotos_upload] if fotos_upload else []

        if fotos_bytes:
            LIMITE_MB = 10
            fotos_grandes = [
                (fotos_upload[i].name, len(b) / 1_048_576)
                for i, b in enumerate(fotos_bytes)
                if len(b) > LIMITE_MB * 1_048_576
            ]
            if fotos_grandes:
                nomes = ", ".join(f"{n} ({s:.1f}MB)" for n, s in fotos_grandes)
                st.warning(
                    f"â ï¸ {len(fotos_grandes)} foto(s) com mais de {LIMITE_MB}MB: {nomes}. "
                    f"Fotos muito grandes podem causar timeout â considere reduzir a resoluÃ§Ã£o antes de enviar."
                )

            # Sempre 5 colunas fixas â evita RemoveChild do React ao mudar nÂº de colunas
            _cols_prev = st.columns(5)
            for _i, _fb in enumerate(fotos_bytes[:5]):
                _cols_prev[_i].image(_fb, use_container_width=True)
            if len(fotos_bytes) > 5:
                st.caption(f"+ {len(fotos_bytes) - 5} foto(s) adicionais carregadas.")

        # ââ IMAGENS DE REFERÃNCIA DE LAYOUT (opcional) ââââââââââââââââââââââââ
        with st.expander("ð¼ï¸ Imagens de referÃªncia de layout (opcional)", expanded=False):
            st.caption(
                "Suba imagens de outros produtos que mostram o **layout, posiÃ§Ãµes, estilo ou texto** "
                "que vocÃª quer replicar. A IA vai entender a composiÃ§Ã£o e aplicar ao SEU produto, "
                "mantendo o padrÃ£o visual MartinSousa."
            )
            st.info(
                "ð¡ **Como nomear os arquivos para as 7 imagens padrÃ£o:** "
                "`fundo_branco.jpg`, `beneficios.jpg`, `cenario.jpg`, `detalhes.jpg`, "
                "`medidas_peso.jpg`, `quebra_objecao.jpg`, `presentear.jpg` â "
                "o nome do arquivo indica para qual tipo de imagem a referÃªncia se aplica."
            )
            refs_layout_upload = st.file_uploader(
                "Imagens de referÃªncia de layout (JPG, PNG, WebP)",
                type=["jpg", "jpeg", "png", "webp"],
                accept_multiple_files=True,
                key="img_refs_layout_upload",
                help="Ex: uma imagem de bengala mostrando como vocÃª quer que fique o layout â a IA reproduz o estilo no seu produto.",
            )
            refs_layout_bytes = []
            refs_layout_nomes = []
            if refs_layout_upload:
                refs_layout_bytes = [f.getvalue() for f in refs_layout_upload]
                refs_layout_nomes = [f.name for f in refs_layout_upload]
                # Sempre 4 colunas fixas â evita RemoveChild do React
                _cols_rl = st.columns(4)
                for _i, _rb in enumerate(refs_layout_bytes[:4]):
                    _cols_rl[_i].image(_rb, caption=refs_layout_nomes[_i][:20], use_container_width=True)

            instrucao_layout = ""
            if refs_layout_bytes:
                instrucao_layout = st.text_area(
                    "Descreva o que cada imagem de referÃªncia representa (opcional)",
                    height=80,
                    placeholder=(
                        "ex: 'fundo_branco.jpg' â quero esse estilo de sombra suave e centralizaÃ§Ã£o. "
                        "'beneficios.jpg' â replicar os Ã­cones Ã  direita com texto ao lado."
                    ),
                    key="img_instrucao_layout",
                )

        # ââ TIPOS âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
        tipos_selecionados = []
        instrucoes_extras = ""

        if modo == "1 imagem especÃ­fica":
            tipo_unico = st.selectbox("Tipo de imagem", list(PRESETS.keys()), key="img_tipo_unico")
            instrucoes_extras = st.text_area(
                "Descreva o que vocÃª quer nessa imagem (textos, cenas, destaque)",
                value=PRESETS[tipo_unico],
                height=120,
                key=f"img_instr_{tipo_unico}",
                placeholder="ex: tÃ­tulo 'Guarda suas memÃ³rias com estilo', 3 benefÃ­cios: durabilidade, capa dura, folhas pretas...",
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
                "ObservaÃ§Ãµes gerais (aplicadas a todas as imagens selecionadas)",
                height=80,
                placeholder="ex: produto tem versÃ£o preta e branca, foca nos dois no fundo branco",
                key="img_instr_multi",
            )

        else:  # As 7 imagens do padrÃ£o
            tipos_selecionados = TIPOS_PADRAO
            instrucoes_extras = st.text_area(
                "ObservaÃ§Ãµes gerais (aplicadas a todas as 7 imagens)",
                height=80,
                placeholder="ex: produto vem em 3 cores, destaque a vermelha nas peÃ§as de marketing",
                key="img_instr_lote",
            )

        # ââ BOTÃO DE TRIAGEM ââââââââââââââââââââââââââââââââââââââââââââââââââ
        st.markdown("---")
        iniciar_triagem = st.button(
            "ð Analisar e mostrar plano antes de gerar",
            type="primary",
            use_container_width=True,
            disabled=not tipos_selecionados,
        )

        if iniciar_triagem:
            # ValidaÃ§Ãµes FORA do try/except para evitar que st.stop() seja capturado como erro
            if not nome_produto:
                st.warning("Informe o nome do produto.")
                st.stop()
            if not fotos_bytes:
                st.warning("Suba pelo menos uma foto do produto â Ã© ela que garante fidelidade.")
                st.stop()

            try:
                with st.spinner("Analisando produto e montando o plano de criaÃ§Ã£o..."):
                    plano, erro_triagem = gerar_triagem_ia(
                        nome_produto, tipos_selecionados, dados_descricao,
                        instrucoes_extras, fotos_bytes,
                    )

                if erro_triagem:
                    st.error(f"NÃ£o consegui montar a triagem: {erro_triagem}")
                else:
                    st.session_state["img_triagem_plano"] = plano
                    st.session_state["img_triagem_config"] = {
                        "nome_produto": nome_produto,
                        "codigo": codigo_input,
                        "tipos": tipos_selecionados,
                        "instrucoes_extras": instrucoes_extras,
                        "fotos_bytes": fotos_bytes,
                        "dados_descricao": dados_descricao,
                        # ReferÃªncias de layout (opcional)
                        "refs_layout_bytes": refs_layout_bytes,
                        "refs_layout_nomes": refs_layout_nomes,
                        "instrucao_layout": instrucao_layout,
                    }
                    # Sem st.rerun() â o plano Ã© exibido diretamente abaixo
                    # sem resetar a pÃ¡gina nem perder os campos preenchidos
            except Exception as _e_triagem:
                st.error(
                    f"â Ocorreu um erro ao montar a prÃ©via: {_e_triagem}\n\n"
                    "Verifique se o nome do produto estÃ¡ preenchido e tente novamente. "
                    "Se o erro persistir, reduza o tamanho das fotos ou escolha menos tipos de imagem."
                )

    # ââ EXIBIÃÃO DA TRIAGEM âââââââââââââââââââââââââââââââââââââââââââââââââââ
    if "img_triagem_plano" in st.session_state and "img_triagem_config" in st.session_state:
        plano = st.session_state["img_triagem_plano"]
        cfg = st.session_state["img_triagem_config"]

        st.markdown("---")
        st.markdown("### ðï¸ Plano de criaÃ§Ã£o")
        st.caption("Esta etapa nÃ£o custou nada. Corrija o que precisar antes de confirmar a geraÃ§Ã£o.")

        itens_plano = plano.get("plano", [])
        itens_viaveis   = [item for item in itens_plano if item.get("viavel", True)]
        itens_bloqueados = [item for item in itens_plano if not item.get("viavel", True)]

        # ââ Itens viÃ¡veis âââââââââââââââââââââââââââââââââââââââââââââââââââââ
        for item in itens_viaveis:
            flags = item.get("flags", [])
            with st.container(border=True):
                col_title, col_flag = st.columns([5, 1])
                col_title.markdown(f"**{item.get('numero', '')}. {item.get('tipo', '')}**")
                if flags:
                    col_flag.caption("â ï¸ aviso")
                st.caption(item.get("composicao", ""))
                textos = item.get("textos", [])
                if textos:
                    st.caption("Textos: " + " Â· ".join(f'"{t}"' for t in textos[:4]))
                if flags:
                    with st.expander("Ver aviso", expanded=False):
                        st.warning(flags[0])

        # ââ Itens bloqueados (informaÃ§Ã£o faltante) ââââââââââââââââââââââââââââ
        if itens_bloqueados:
            st.markdown("---")
            st.markdown(
                "### ð« Imagens bloqueadas â informaÃ§Ã£o insuficiente\n"
                "As imagens abaixo **nÃ£o serÃ£o geradas** porque falta alguma informaÃ§Ã£o essencial. "
                "Responda as perguntas no **Assistente IA** (menu lateral) ou preencha os dados e "
                "clique em **Analisar novamente**."
            )
            for item in itens_bloqueados:
                with st.container(border=True):
                    st.markdown(
                        f"<div style='padding:2px 0'>"
                        f"<span class='ms-bloqueada'>ð« BLOQUEADA</span> &nbsp; "
                        f"<strong>{item.get('numero', '')}. {item.get('tipo', '')}</strong>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    pergunta = item.get("pergunta_info", "").strip()
                    if pergunta:
                        st.error(f"**O que falta:** {pergunta}")
                    else:
                        st.error("InformaÃ§Ã£o necessÃ¡ria nÃ£o fornecida. ForneÃ§a os dados e analise novamente.")

        if plano.get("observacao_geral"):
            st.info(plano["observacao_geral"])

        correcao = st.text_area(
            "âï¸ CorreÃ§Ã£o ou instruÃ§Ã£o adicional (opcional â a IA aplicarÃ¡ antes de gerar)",
            placeholder="ex: O produto Ã© azul, nÃ£o branco. Nas imagens de cenÃ¡rio, use ambiente externo, nÃ£o domÃ©stico.",
            key="img_correcao_triagem",
            height=80,
        )

        n_viaveis = len(itens_viaveis)
        n_bloqueadas = len(itens_bloqueados)
        custo_est = n_viaveis * 1.0

        if n_viaveis == 0:
            st.error(
                "â Nenhuma imagem pode ser gerada agora â todas estÃ£o bloqueadas por falta de informaÃ§Ã£o. "
                "ForneÃ§a os dados solicitados e clique em **Analisar novamente**."
            )
        else:
            aviso_bloqueadas = (
                f" ({n_bloqueadas} bloqueada(s) por dados insuficientes â serÃ£o ignoradas)"
                if n_bloqueadas else ""
            )
            st.warning(
                f"ð° Isso vai gerar **{n_viaveis} imagem(ns)**{aviso_bloqueadas} "
                f"com custo estimado de **~R${custo_est:.2f}**. Confirma?"
            )

        col_cancelar, col_confirmar = st.columns(2)
        if col_cancelar.button("â Cancelar", use_container_width=True):
            del st.session_state["img_triagem_plano"]
            del st.session_state["img_triagem_config"]
            st.rerun()

        confirmar_disabled = n_viaveis == 0
        if col_confirmar.button(
            "â Confirmar e gerar",
            type="primary",
            use_container_width=True,
            disabled=confirmar_disabled,
        ):
            try:
                # Aplica correÃ§Ã£o ao config se houver
                if correcao:
                    cfg["instrucoes_extras"] = (cfg.get("instrucoes_extras", "") + "\n\nCORREÃÃO DO COLABORADOR:\n" + correcao).strip()
                    st.session_state["img_triagem_config"] = cfg

                galeria = []
                barra = st.progress(0.0, text="Iniciando geraÃ§Ã£o...")

                # Gera APENAS os tipos viÃ¡veis aprovados na triagem
                tipos_viaveis = [item["tipo"] for item in itens_viaveis]
                tipos = tipos_viaveis if tipos_viaveis else cfg["tipos"]

                import time as _time_gen
                import threading as _threading
                for i, tipo in enumerate(tipos):
                    barra.progress(i / len(tipos), text=f"Gerando {i+1}/{len(tipos)}: {tipo[:50]}...")
                    # Sem sleep aqui â o _GEMINI_LIMITER em gerar_imagem_ia jÃ¡ respeita o RPM
                    try:
                        prompt_final = montar_prompt_imagem(
                            tipo,
                            cfg.get("instrucoes_extras", ""),
                            cfg.get("dados_descricao"),
                            cfg["nome_produto"],
                            refs_layout_nomes=cfg.get("refs_layout_nomes", []),
                            instrucao_layout=cfg.get("instrucao_layout", ""),
                        )
                        # ââ GeraÃ§Ã£o em thread separada ââââââââââââââââââââââââââ
                        # MantÃ©m o WebSocket vivo durante a chamada Gemini (30-60s)
                        # enviando atualizaÃ§Ãµes a cada segundo para o Railway nÃ£o
                        # fechar a conexÃ£o por inatividade.
                        # Combina fotos do produto + refs de layout para o Gemini
                        todas_fotos = cfg["fotos_bytes"] + cfg.get("refs_layout_bytes", [])
                        _res = {"img": None, "erro": None, "done": False}
                        _thread = _threading.Thread(
                            target=_gerar_imagem_thread,
                            args=(prompt_final, todas_fotos, _res),
                            daemon=True,
                        )
                        _thread.start()
                        _contador = st.empty()
                        _t0 = _time_gen.time()
                        while not _res["done"]:
                            _seg = int(_time_gen.time() - _t0)
                            if _seg >= 300:
                                _res["erro"] = "Tempo limite de 5 min atingido. Tente novamente."
                                _res["done"] = True
                                break
                            _contador.caption(f"â³ Aguardando Gemini... {_seg}s")
                            _time_gen.sleep(1)
                        _contador.empty()
                        img_bytes, erro_gen = _res["img"], _res["erro"]
                        # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
                        if erro_gen:
                            st.warning(f"â ï¸ Falhou em '{tipo}': {erro_gen}")
                            continue
                        galeria.append({"tipo": tipo, "bytes": img_bytes, "aprovado": False})
                    except Exception as _e_img:
                        st.warning(f"â ï¸ Erro inesperado em '{tipo}': {_e_img}")
                        continue

                barra.progress(1.0, text=f"ConcluÃ­do! {len(galeria)}/{len(tipos)} imagens geradas.")

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
                    st.error("â Nenhuma imagem foi gerada com sucesso. Verifique os avisos acima e tente novamente.")
            except Exception as _e_gerar:
                st.error(
                    f"â Erro durante a geraÃ§Ã£o: {_e_gerar}\n\n"
                    "Suas sessÃµes e dados estÃ£o preservados. Tente novamente ou reduza o nÃºmero de imagens."
                )

    # ââ GALERIA âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    if "img_galeria" in st.session_state and st.session_state["img_galeria"]:
        st.markdown("---")
        galeria = st.session_state["img_galeria"]
        nome_gal = st.session_state.get("img_nome_produto", "produto")
        codigo_gal = st.session_state.get("img_codigo", "")

        # Miniaturas clicÃ¡veis
        nomes_galeria = [g["tipo"] for g in galeria]
        _cols_gal = st.columns(4)
        for i, g in enumerate(galeria):
            with _cols_gal[i % 4]:
                st.image(g["bytes"], caption=g["tipo"][:20], use_container_width=True)

        # SeleÃ§Ã£o da imagem ativa
        escolha = st.selectbox("Imagem ativa (para ajustar ou baixar individualmente)", nomes_galeria, key="img_escolha")
        idx_ativo = nomes_galeria.index(escolha)
        imagem_ativa = galeria[idx_ativo]["bytes"]
        tipo_ativo = galeria[idx_ativo]["tipo"]

        # Exibe imagem ativa grande
        st.image(imagem_ativa, use_container_width=True)

        # AÃ§Ãµes individuais
        col_dl, col_drive_ind = st.columns(2)
        col_dl.download_button(
            "â¬ï¸ Baixar esta imagem",
            data=imagem_ativa,
            file_name=f"{nome_gal}_{tipo_ativo[:20]}.png",
            mime="image/png",
            use_container_width=True,
            key=f"dl_{idx_ativo}",
        )
        if col_drive_ind.button("âï¸ Salvar esta no Drive", use_container_width=True, key=f"drive_ind_{idx_ativo}"):
            pasta_pai = st.secrets.get("DRIVE_PASTA_IMAGENS_ID", "")
            if not pasta_pai:
                st.error("DRIVE_PASTA_IMAGENS_ID nÃ£o configurada.")
            else:
                with st.spinner("Enviando..."):
                    nome_pasta = f"{nome_gal} - {codigo_gal}".strip(" -")
                    pastas = buscar_pasta_produto(nome_gal, codigo_gal, pasta_pai)
                    if pastas:
                        pasta_id = pastas[0][0]
                    else:
                        pasta_id, err_pasta = criar_pasta_produto(nome_pasta, pasta_pai)
                        if err_pasta:
                            st.error(f"Erro ao criar pasta: {err_pasta}")
                            pasta_id = None
                    if pasta_id:
                        link, err_up = upload_para_pasta(
                            imagem_ativa, f"{tipo_ativo[:20]}.png", pasta_id
                        )
                        if err_up:
                            st.error(f"Erro no upload: {err_up}")
                        else:
                            # Atualiza galeria com o link e registra no histÃ³rico
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

        # ââ AJUSTE FINO NA GALERIA ââââââââââââââââââââââââââââââââââââââââââââ
        with st.expander("âï¸ Ajuste Fino â modificar somente algo especÃ­fico nesta imagem", expanded=False):
            st.caption(
                "Descreva **somente o que deve mudar** â a IA vai preservar tudo o mais "
                "exatamente igual (fundo, cores, cena, textos existentes, detalhes do produto)."
            )
            instrucao_af_gal = st.text_area(
                "O que vocÃª quer modificar?",
                placeholder=(
                    "ex: Diminua o tamanho do produto para que fique em proporÃ§Ã£o realista ao cenÃ¡rio. "
                    "O produto mede aproximadamente 18cm.\n\n"
                    "ex: Remova a sombra embaixo do produto.\n\n"
                    "ex: Mude o fundo para branco puro, mantendo o produto igual."
                ),
                height=120,
                key=f"img_af_gal_{idx_ativo}",
            )
            if st.button(
                "âï¸ Aplicar Ajuste Fino nesta imagem",
                key=f"img_af_btn_{idx_ativo}",
                type="primary",
                use_container_width=True,
                disabled=not instrucao_af_gal.strip(),
            ):
                if not instrucao_af_gal.strip():
                    st.warning("Descreva o que deseja modificar.")
                else:
                    # Usa a imagem ATUAL da galeria como referÃªncia para o ajuste
                    import time as _time_afg
                    import threading as _threading_afg
                    prompt_af_gal = montar_prompt_ajuste_fino(instrucao_af_gal.strip())
                    _res_afg = {"img": None, "erro": None, "done": False}
                    _threading_afg.Thread(
                        target=_gerar_imagem_thread,
                        args=(prompt_af_gal, [imagem_ativa], _res_afg),
                        daemon=True,
                    ).start()
                    _slot_afg = st.empty()
                    _t0_afg = _time_afg.time()
                    while not _res_afg["done"]:
                        _seg_afg = int(_time_afg.time() - _t0_afg)
                        if _seg_afg >= 300:
                            _res_afg["erro"] = "Tempo limite de 5 min atingido. Tente novamente."
                            _res_afg["done"] = True
                            break
                        _slot_afg.caption(f"â³ Aplicando ajuste fino... {_seg_afg}s")
                        _time_afg.sleep(1)
                    _slot_afg.empty()
                    nova_img_af, err_af_gal = _res_afg["img"], _res_afg["erro"]
                    if err_af_gal:
                        st.error(f"â Erro: {err_af_gal}")
                    else:
                        st.session_state["img_galeria"][idx_ativo]["bytes"] = nova_img_af
                        st.rerun()

        # ââ COMANDOS PENDENTES DO ASSISTENTE IA ââââââââââââââââââââââââââââââ
        # O Assistente IA envia comandos de correÃ§Ã£o. Tratamos sempre como
        # Ajuste Fino (NÃO aplica PADRAO_VISUAL nem INSTRUCAO_COMPOSICAO).
        cmds_pendentes = st.session_state.pop("chat_img_pendente", [])
        if cmds_pendentes:
            fotos_ref_aj = st.session_state.get("img_fotos_originais") or []
            msgs_result = []
            for cmd in cmds_pendentes:
                num_foto  = cmd.get("num", 1)
                instrucao = cmd.get("instrucao", "")
                idx_alvo  = num_foto - 1
                if idx_alvo < 0 or idx_alvo >= len(galeria):
                    msgs_result.append(f"â ï¸ Foto {num_foto} nÃ£o existe na galeria.")
                    continue
                tipo_alvo = galeria[idx_alvo]["tipo"]
                # Usa a imagem ATUAL como referÃªncia + prompt de ajuste fino
                img_ref_cmd = [galeria[idx_alvo]["bytes"]] if galeria[idx_alvo]["bytes"] else fotos_ref_aj
                prompt_aj = montar_prompt_ajuste_fino(instrucao)
                import time as _time_cmd
                import threading as _threading_cmd
                _res_cmd = {"img": None, "erro": None, "done": False}
                _threading_cmd.Thread(
                    target=_gerar_imagem_thread,
                    args=(prompt_aj, img_ref_cmd, _res_cmd),
                    daemon=True,
                ).start()
                _slot_cmd = st.empty()
                _t0_cmd = _time_cmd.time()
                while not _res_cmd["done"]:
                    _seg_cmd = int(_time_cmd.time() - _t0_cmd)
                    if _seg_cmd >= 300:
                        _res_cmd["erro"] = "Tempo limite de 5 min atingido. Tente novamente."
                        _res_cmd["done"] = True
                        break
                    _slot_cmd.caption(f"â³ Assistente IA: ajuste fino na foto {num_foto}... {_seg_cmd}s")
                    _time_cmd.sleep(1)
                _slot_cmd.empty()
                nova_img, err_aj = _res_cmd["img"], _res_cmd["erro"]
                if err_aj:
                    msgs_result.append(f"â ï¸ Foto {num_foto}: erro ao gerar â {err_aj}")
                else:
                    st.session_state["img_galeria"][idx_alvo]["bytes"] = nova_img
                    msgs_result.append(f"â Foto {num_foto} ({tipo_alvo[:25]}) atualizada pelo Assistente IA.")
            if msgs_result:
                st.info("\n\n".join(msgs_result))

        st.caption("ð¬ Para ajustar imagens, use o **Assistente IA** no menu lateral ou o painel **âï¸ Ajuste Fino** acima.")
        st.markdown("---")

        # ââ APROVAÃÃO E SALVAMENTO âââââââââââââââââââââââââââââââââââââââââââââ
        st.markdown("### â Aprovar e salvar todas as imagens")
        pasta_pai = st.secrets.get("DRIVE_PASTA_IMAGENS_ID", "")

        # Busca pasta existente (cacheada em session_state para nÃ£o bater na API a cada rerender)
        _cache_key = f"_pasta_{nome_gal}__{codigo_gal}"
        if _cache_key not in st.session_state:
            if pasta_pai and nome_gal:
                with st.spinner("Verificando pasta no Drive..."):
                    st.session_state[_cache_key] = buscar_pasta_produto(nome_gal, codigo_gal, pasta_pai)
            else:
                st.session_state[_cache_key] = []
        pastas_encontradas = st.session_state[_cache_key]

        nome_pasta_novo = f"{nome_gal} - {codigo_gal}".strip(" -") if codigo_gal else nome_gal

        if pastas_encontradas:
            st.info(
                f"ð Pasta encontrada no Drive: **{pastas_encontradas[0][1]}**\n\n"
                f"As imagens serÃ£o adicionadas a essa pasta (sem apagar o que jÃ¡ estÃ¡ lÃ¡)."
            )
            pasta_destino_id = pastas_encontradas[0][0]
            if len(pastas_encontradas) > 1:
                escolha_pasta = st.selectbox(
                    "Mais de uma pasta encontrada â qual usar?",
                    [p[1] for p in pastas_encontradas],
                    key="img_escolha_pasta",
                )
                pasta_destino_id = next(p[0] for p in pastas_encontradas if p[1] == escolha_pasta)
        else:
            st.info(f"ð SerÃ¡ criada uma nova pasta no Drive: **{nome_pasta_novo}**")
            pasta_destino_id = None  # serÃ¡ criada no momento do clique

        col_aprovar, col_zip = st.columns(2)

        if col_aprovar.button(
            f"âï¸ APROVAR E SALVAR no Drive ({len(galeria)} imagens)",
            type="primary",
            use_container_width=True,
        ):
            if not pasta_pai:
                st.error("DRIVE_PASTA_IMAGENS_ID nÃ£o configurada nas Secrets.")
            else:
                if pasta_destino_id is None:
                    with st.spinner("Criando pasta..."):
                        pasta_destino_id, err_pasta = criar_pasta_produto(nome_pasta_novo, pasta_pai)
                    if err_pasta:
                        st.error(f"Erro ao criar pasta: {err_pasta}")
                        st.stop()

                links_salvos = []
                barra_salvar = st.progress(0.0, text="Salvando imagens...")
                for i, g in enumerate(galeria):
                    barra_salvar.progress(i / len(galeria), text=f"Salvando: {g['tipo'][:30]}...")
                    nome_arq = f"{g['tipo'][:30]}.png"
                    link, err_up = upload_para_pasta(g["bytes"], nome_arq, pasta_destino_id)
                    if err_up:
                        st.warning(f"Falhou '{g['tipo']}': {err_up}")
                    else:
                        links_salvos.append(link)

                barra_salvar.progress(1.0, text="ConcluÃ­do!")
                link_pasta = f"https://drive.google.com/drive/folders/{pasta_destino_id}"

                import atividades
                atividades.registrar_atividade(
                    usuario_logado, "Imagem (aprovada e salva)",
                    nome_gal,
                    f"{len(links_salvos)} imagens salvas na pasta {nome_pasta_novo}",
                    codigo=codigo_gal,
                    link_pasta=link_pasta,
                )

                st.success(
                    f"â {len(links_salvos)} imagem(ns) salvas no Drive! "
                    f"[Abrir pasta]({link_pasta})"
                )

        # ZIP sempre disponÃ­vel
        zip_bytes = criar_zip_galeria(galeria, nome_gal)
        col_zip.download_button(
            f"â¬ï¸ Baixar todas em ZIP ({len(galeria)} imagens)",
            data=zip_bytes,
            file_name=f"{nome_gal}_imagens.zip",
            mime="application/zip",
            use_container_width=True,
        )
