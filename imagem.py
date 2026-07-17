import streamlit as st
import requests
import base64
import io
import zipfile
import json
import anthropic

MODELO_IMAGEM = "gemini-3-pro-image-preview"  # Nano Banana Pro

# ── PADRÃO VISUAL MARTINSOUSA (hardcoded em todos os prompts) ──────────────────
PADRAO_VISUAL = """
PADRÃO VISUAL OBRIGATÓRIO DA EMPRESA (aplique em todas as peças de marketing):
- Fundo: #E8EEF5 (azul-cinza claro suave)
- Cor principal / texto e elementos gráficos: #1A3A6B (azul marinho)
- Cor de destaque secundária: #4A7EC7 (azul médio)
- Fonte: Montserrat ou Poppins — nunca fontes serifadas
- Ícones: estilo line-art clean, traço fino, monocromáticos em azul marinho
- Elementos decorativos: círculos ou manchas suaves em azul marinho ou azul médio,
  usados como moldura ou destaque atrás do produto ou dos ícones
- Texto sempre em português do Brasil, sem erros ortográficos, sem caixa alta excessiva
- Visual limpo, arejado, profissional — sem poluição visual
- NÃO use marrom, laranja, vermelho ou verde como cores principais
"""

INSTRUCAO_FIDELIDADE = """
REGRA DE FIDELIDADE AO PRODUTO (não negocie):
- Reproduza o produto EXATAMENTE como aparece nas imagens de referência: mesma cor,
  mesmo formato, mesmas proporções, mesmos detalhes visíveis
- Se uma característica do produto não estiver visível nas fotos de referência e for
  necessária para a composição, SINALIZE ISSO no plano em vez de inventar
- Nunca deforme, alongue, encurte ou altere qualquer parte do produto
- Nunca crie detalhes que não aparecem nas fotos de referência
"""

INSTRUCAO_COMPOSICAO = """
INSTRUÇÃO DE COMPOSIÇÃO:
- Use as imagens de referência APENAS para manter o produto reconhecível e fiel
- Componha uma cena/layout NOVO e apropriado para o tipo de imagem solicitado
- Não reaproveite a foto de referência literalmente — crie uma peça nova
"""

# ── PRESETS ATUALIZADOS COM IDENTIDADE VISUAL ─────────────────────────────────
TIPOS_PADRAO = [
    "1 — Produto com fundo branco",
    "2 — Benefícios do produto",
    "3 — Benefícios no cenário de uso",
    "4 — Close nos detalhes",
    "5 — Características técnicas (medidas/peso/material)",
    "6 — Quebra de objeção",
    "7 — Presenteie",
]

PRESETS = {
    "Personalizado (descrevo o que quero)": "",
    "1 — Produto com fundo branco": (
        "Foto de produto limpa e profissional, fundo branco liso, produto centralizado e bem iluminado, "
        "iluminação de estúdio suave sem sombras duras, sem texto sobreposto, sem elementos extras. "
        "O produto deve ocupar 70-80% do frame."
    ),
    "2 — Benefícios do produto": (
        "Peça de marketing mostrando os principais benefícios do produto. "
        "Layout: produto em destaque no centro ou à esquerda, à direita blocos verticais empilhados "
        "com ícone line-art + título curto (2-3 palavras) + frase explicativa (1 linha). "
        "Máximo 4 benefícios. Título principal em destaque no topo."
    ),
    "3 — Benefícios no cenário de uso": (
        "Peça de marketing mostrando o produto sendo usado em um cenário real do dia a dia. "
        "Cena realista e aspiracional com iluminação natural. "
        "Frases curtas de destaque flutuando sobre ou ao lado do produto, explicando o benefício "
        "daquele momento de uso específico. Tom acolhedor e moderno."
    ),
    "4 — Close nos detalhes": (
        "Imagem em zoom aproximado valorizando os acabamentos e qualidade do produto. "
        "Pequenas setas ou linhas finas apontando para cada detalhe, com legenda curta ao lado. "
        "Foco em textura, material, costuras, encaixe, ou qualquer acabamento que diferencie o produto. "
        "Máximo 4 pontos de destaque."
    ),
    "5 — Características técnicas (medidas/peso/material)": (
        "Imagem técnica do produto com linhas de medida estilo desenho técnico, mostrando as dimensões "
        "exatas (altura, largura, profundidade). Peso e material indicados com ícones técnicos. "
        "Dados anotados de forma clara e legível. Fundo claro, visual limpo e técnico."
    ),
    "6 — Quebra de objeção": (
        "Peça de marketing respondendo as principais dúvidas de quem está prestes a comprar. "
        "Formato: 3 a 4 blocos, cada um com uma objeção comum em forma de pergunta curta e a "
        "resposta direta e tranquilizadora ao lado ou abaixo. Ícone de check ou escudo. "
        "Tom de confiança e credibilidade."
    ),
    "7 — Presenteie": (
        "Peça de marketing emocional incentivando a compra do produto como presente. "
        "Frase principal de impacto emocional em destaque (ex: 'O presente certo para quem você ama'). "
        "Composição com laço, embrulho ou contexto de presente. Tom acolhedor e especial. "
        "Cena mostrando a entrega ou o momento de surpresa com reação positiva."
    ),
}


# ── TRIAGEM POR IA (análise textual, sem gastar com geração) ──────────────────

def gerar_triagem_ia(nome_produto, tipos_selecionados, dados_descricao, instrucoes_extras, fotos_bytes):
    """Pede para a IA analisar o que ela criaria para cada tipo de imagem,
    ANTES de gastar com a geração real. Retorna lista de dicts com o plano."""
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None, "ANTHROPIC_API_KEY não configurada."

    tipos_str = "\n".join(f"- {t}: {PRESETS.get(t,'')[:120]}..." for t in tipos_selecionados)

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

    prompt = f"""Você é especialista em imagens para e-commerce no Mercado Livre. Seja BREVE e DIRETO.

PRODUTO: {nome_produto}
{contexto_descricao}
FOTOS ENVIADAS: {len(fotos_bytes)}
{f"INSTRUÇÕES EXTRAS: {instrucoes_extras}" if instrucoes_extras else ""}

TIPOS A CRIAR:
{tipos_str}

TAREFA: Para cada tipo, informe em 1-2 frases curtas o que será criado (composição principal e textos).
Só inclua flag ⚠️ se faltar uma informação CRÍTICA que vai comprometer a fidelidade da imagem. Máximo 1 flag por tipo.

Responda SOMENTE com JSON válido, sem texto antes ou depois:
{{
  "plano": [
    {{
      "tipo": "nome do tipo",
      "numero": 1,
      "composicao": "1-2 frases curtas descrevendo a imagem",
      "textos": ["texto 1", "texto 2"],
      "flags": ["⚠️ aviso crítico apenas se necessário"],
      "viavel": true
    }}
  ],
  "observacao_geral": "uma frase resumindo o conjunto, ou string vazia"
}}
"""

    client = anthropic.Anthropic(api_key=api_key)
    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}]
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


# ── GERAÇÃO DE IMAGEM (Gemini) ─────────────────────────────────────────────────

def gerar_imagem_ia(prompt_texto, imagens_referencia):
    """imagens_referencia: lista de bytes. Retorna (imagem_bytes, erro)."""
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    if not api_key:
        return None, "GEMINI_API_KEY não configurada nas Secrets."

    parts = [{"text": prompt_texto}]
    for img_bytes in imagens_referencia:
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": base64.b64encode(img_bytes).decode("utf-8"),
            }
        })

    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {"aspectRatio": "1:1", "imageSize": "2K"},
        },
    }

    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO_IMAGEM}:generateContent",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json=body, timeout=90,
        )
        if resp.status_code != 200:
            return None, f"Erro da API (HTTP {resp.status_code}): {resp.text[:300]}"
        dados = resp.json()
        candidatos = dados.get("candidates", [])
        if not candidatos:
            return None, "A IA não retornou nenhuma imagem (resposta vazia)."
        for parte in candidatos[0].get("content", {}).get("parts", []):
            inline = parte.get("inlineData") or parte.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"]), None
        return None, "A IA respondeu, mas não veio nenhuma imagem (pode ter bloqueado o pedido)."
    except Exception as e:
        return None, str(e)


def montar_prompt_imagem(tipo, instrucoes_extras, dados_descricao, nome_produto):
    """Monta o prompt completo para geração, incorporando identidade visual e dados do produto."""
    base = PRESETS.get(tipo, "")

    contexto_produto = f"PRODUTO: {nome_produto}\n"
    if dados_descricao:
        if dados_descricao.get("cor"):
            contexto_produto += f"Cor: {dados_descricao['cor']}\n"
        if dados_descricao.get("medidas"):
            contexto_produto += f"Medidas: {dados_descricao['medidas']}\n"
        if dados_descricao.get("diferenciais"):
            contexto_produto += f"Diferenciais principais: {dados_descricao['diferenciais'][:200]}\n"

    bloco_instrucoes = (
        f"\nINSTRUÇÕES ADICIONAIS DO COLABORADOR (prioridade máxima — aplique antes de tudo):\n{instrucoes_extras}"
        if instrucoes_extras else ""
    )

    return f"""{contexto_produto}
TIPO DE IMAGEM: {tipo}
{base}
{bloco_instrucoes}

{PADRAO_VISUAL}
{INSTRUCAO_FIDELIDADE}
{INSTRUCAO_COMPOSICAO}
"""


# ── GOOGLE DRIVE — GESTÃO DE PASTAS ───────────────────────────────────────────

def _drive_service():
    from googleapiclient.discovery import build
    from google.oauth2.service_account import Credentials
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(
        creds_dict, scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)


def buscar_pasta_produto(nome_produto, codigo, pasta_pai_id):
    """Busca pasta exata '[Nome] - [Código]' ou pelo nome aproximado.
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
    """Faz upload de imagem para pasta específica. Retorna (link, erro)."""
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
    """Cria ZIP em memória com todas as imagens da galeria. Retorna bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for g in galeria:
            nome_arquivo = f"{nome_produto}_{g['tipo'][:30]}.png"
            nome_arquivo = "".join(c if c.isalnum() or c in "._- " else "_" for c in nome_arquivo)
            zf.writestr(nome_arquivo, g["bytes"])
    buf.seek(0)
    return buf.read()


# ── INTERFACE PRINCIPAL ────────────────────────────────────────────────────────

def pagina_imagem(usuario_logado):
    st.subheader("Imagem")
    st.caption("Gere imagens profissionais para o anúncio. A IA mostra o que vai criar antes de gastar com a geração.")

    # ── LINHA 1: Nome + Código ─────────────────────────────────────────────────
    col_nome, col_cod = st.columns(2)
    with col_nome:
        nome_produto = st.text_input(
            "Nome do produto",
            value=st.session_state.pop("img_nome_importado", ""),
            key="img_nome_produto_input",
        )
    with col_cod:
        codigo_input = st.text_input(
            "Código da descrição (opcional)",
            value=st.session_state.pop("img_codigo_importado", ""),
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
                f"Medidas: {dados_descricao.get('medidas') or '—'}"
            )
        else:
            st.warning("Código não encontrado no histórico. Pode continuar — só não haverá vínculo com a descrição.")

    # Também usa dados do session_state do módulo de descrição se o usuário
    # acabou de gerar na mesma sessão e ainda não copiou o código
    if not dados_descricao and st.session_state.get("desc_codigo_atual") == codigo_input and codigo_input:
        dados_descricao = st.session_state.get("desc_dados_atual")

    # ── FOTOS DE REFERÊNCIA ────────────────────────────────────────────────────
    st.markdown("**Fotos de referência do produto**")
    st.caption("Suba quantas fotos quiser — ângulos diferentes ajudam a IA a ser mais fiel.")
    fotos_upload = st.file_uploader(
        "Fotos do produto (JPG, PNG, WebP)",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        key="img_fotos_upload",
    )
    fotos_bytes = [f.getvalue() for f in fotos_upload] if fotos_upload else []

    if fotos_bytes:
        cols_prev = st.columns(min(len(fotos_bytes), 5))
        for i, fb in enumerate(fotos_bytes[:5]):
            cols_prev[i].image(fb, use_container_width=True)
        if len(fotos_bytes) > 5:
            st.caption(f"+ {len(fotos_bytes) - 5} foto(s) adicionais carregadas.")

    # ── O QUE GERAR ───────────────────────────────────────────────────────────
    st.markdown("---")
    modo = st.radio(
        "O que gerar?",
        ["1 imagem específica", "Selecionar tipos", "As 7 imagens do padrão"],
        horizontal=True,
        key="img_modo",
    )

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

    elif modo == "Selecionar tipos":
        tipos_selecionados = st.multiselect(
            "Quais imagens gerar?",
            TIPOS_PADRAO,
            default=TIPOS_PADRAO[:3],
            key="img_tipos_multi",
        )
        instrucoes_extras = st.text_area(
            "Observações gerais (aplicadas a todas as imagens selecionadas)",
            height=80,
            placeholder="ex: produto tem versão preta e branca, foca nos dois no fundo branco",
            key="img_instr_multi",
        )

    else:  # As 7 imagens do padrão
        tipos_selecionados = TIPOS_PADRAO
        instrucoes_extras = st.text_area(
            "Observações gerais (aplicadas a todas as 7 imagens)",
            height=80,
            placeholder="ex: produto vem em 3 cores, destaque a vermelha nas peças de marketing",
            key="img_instr_lote",
        )

    # ── BOTÃO DE TRIAGEM ──────────────────────────────────────────────────────
    st.markdown("---")
    iniciar_triagem = st.button(
        "🔍 Analisar e mostrar plano antes de gerar",
        type="primary",
        use_container_width=True,
        disabled=not tipos_selecionados,
    )

    if iniciar_triagem:
        if not nome_produto:
            st.warning("Informe o nome do produto.")
            st.stop()
        if not fotos_bytes:
            st.warning("Suba pelo menos uma foto do produto — é ela que garante fidelidade.")
            st.stop()

        with st.spinner("Analisando produto e montando o plano de criação..."):
            plano, erro_triagem = gerar_triagem_ia(
                nome_produto, tipos_selecionados, dados_descricao,
                instrucoes_extras, fotos_bytes,
            )

        if erro_triagem:
            st.error(f"Não consegui montar a triagem: {erro_triagem}")
        else:
            st.session_state["img_triagem_plano"] = plano
            st.session_state["img_triagem_config"] = {
                "nome_produto": nome_produto,
                "codigo": codigo_input,
                "tipos": tipos_selecionados,
                "instrucoes_extras": instrucoes_extras,
                "fotos_bytes": fotos_bytes,
                "dados_descricao": dados_descricao,
            }
            st.rerun()

    # ── EXIBIÇÃO DA TRIAGEM ───────────────────────────────────────────────────
    if "img_triagem_plano" in st.session_state and "img_triagem_config" in st.session_state:
        plano = st.session_state["img_triagem_plano"]
        cfg = st.session_state["img_triagem_config"]

        st.markdown("---")
        st.markdown("### 🗂️ Plano de criação — confira antes de gastar")
        st.caption("Esta etapa não custou nada. Corrija o que precisar antes de confirmar a geração.")

        itens_plano = plano.get("plano", [])
        tem_flags = any(item.get("flags") for item in itens_plano)

        for item in itens_plano:
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
                # Mostra no máximo 1 flag, colapsada
                if flags:
                    with st.expander("Ver aviso", expanded=False):
                        st.warning(flags[0])

        if plano.get("observacao_geral"):
            st.info(plano["observacao_geral"])

        correcao = st.text_area(
            "✏️ Correção ou instrução adicional (opcional — a IA aplicará antes de gerar)",
            placeholder="ex: O produto é azul, não branco. Nas imagens de cenário, use ambiente externo, não doméstico.",
            key="img_correcao_triagem",
            height=80,
        )

        n_imagens = len(itens_plano)
        custo_est = n_imagens * 1.0
        st.warning(
            f"💰 Isso vai gerar **{n_imagens} imagem(ns)** com custo estimado de **~R${custo_est:.2f}**. "
            f"Confirma?"
        )

        col_cancelar, col_confirmar = st.columns(2)
        if col_cancelar.button("❌ Cancelar", use_container_width=True):
            del st.session_state["img_triagem_plano"]
            del st.session_state["img_triagem_config"]
            st.rerun()

        if col_confirmar.button("✅ Confirmar e gerar", type="primary", use_container_width=True):
            # Aplica correção ao config se houver
            if correcao:
                cfg["instrucoes_extras"] = (cfg.get("instrucoes_extras", "") + "\n\nCORREÇÃO DO COLABORADOR:\n" + correcao).strip()
                st.session_state["img_triagem_config"] = cfg

            galeria = []
            barra = st.progress(0.0, text="Iniciando geração...")
            tipos = cfg["tipos"]

            for i, tipo in enumerate(tipos):
                barra.progress(i / len(tipos), text=f"Gerando: {tipo[:50]}...")
                prompt_final = montar_prompt_imagem(
                    tipo,
                    cfg.get("instrucoes_extras", ""),
                    cfg.get("dados_descricao"),
                    cfg["nome_produto"],
                )
                if correcao and tipo in cfg.get("instrucoes_extras", ""):
                    pass  # já incorporado acima

                img_bytes, erro_gen = gerar_imagem_ia(prompt_final, cfg["fotos_bytes"])
                if erro_gen:
                    st.warning(f"Falhou em '{tipo}': {erro_gen}")
                    continue
                galeria.append({"tipo": tipo, "bytes": img_bytes, "aprovado": False})

            barra.progress(1.0, text="Concluído!")

            if galeria:
                st.session_state["img_galeria"] = galeria
                st.session_state["img_nome_produto"] = cfg["nome_produto"]
                st.session_state["img_codigo"] = cfg.get("codigo", "")
                st.session_state["img_fotos_originais"] = cfg["fotos_bytes"]
                st.session_state["img_dados_descricao"] = cfg.get("dados_descricao")
                st.session_state["img_instrucoes_originais"] = cfg.get("instrucoes_extras", "")
                st.session_state["img_chat_log"] = []
                import atividades
                atividades.registrar_atividade(
                    usuario_logado,
                    f"Imagem ({len(galeria)} geradas)",
                    cfg["nome_produto"],
                    ", ".join(t[:20] for t in tipos[:3]) + ("..." if len(tipos) > 3 else ""),
                    codigo=cfg.get("codigo", ""),
                    cor=cfg.get("dados_descricao", {}).get("cor", "") if cfg.get("dados_descricao") else "",
                    medidas=cfg.get("dados_descricao", {}).get("medidas", "") if cfg.get("dados_descricao") else "",
                )
                del st.session_state["img_triagem_plano"]
                del st.session_state["img_triagem_config"]
                st.rerun()
            else:
                st.error("Nenhuma imagem foi gerada com sucesso.")

    # ── GALERIA ───────────────────────────────────────────────────────────────
    if "img_galeria" in st.session_state and st.session_state["img_galeria"]:
        st.markdown("---")
        galeria = st.session_state["img_galeria"]
        nome_gal = st.session_state.get("img_nome_produto", "produto")
        codigo_gal = st.session_state.get("img_codigo", "")

        # Miniaturas clicáveis
        nomes_galeria = [g["tipo"] for g in galeria]
        n_cols = min(len(galeria), 4)
        cols_gal = st.columns(n_cols)
        for i, g in enumerate(galeria):
            with cols_gal[i % n_cols]:
                st.image(g["bytes"], caption=g["tipo"][:20], use_container_width=True)

        # Seleção da imagem ativa
        escolha = st.selectbox("Imagem ativa (para ajustar ou baixar individualmente)", nomes_galeria, key="img_escolha")
        idx_ativo = nomes_galeria.index(escolha)
        imagem_ativa = galeria[idx_ativo]["bytes"]
        tipo_ativo = galeria[idx_ativo]["tipo"]

        # Exibe imagem ativa grande
        st.image(imagem_ativa, use_container_width=True)

        # Ações individuais
        col_dl, col_drive_ind = st.columns(2)
        col_dl.download_button(
            "⬇️ Baixar esta imagem",
            data=imagem_ativa,
            file_name=f"{nome_gal}_{tipo_ativo[:20]}.png",
            mime="image/png",
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
                            st.success(f"Salvo! [Abrir no Drive]({link})")

        # ── CHAT DE AJUSTE ────────────────────────────────────────────────────
        st.markdown("##### Ajustar imagens")
        st.caption(
            "Use o número da foto para indicar qual ajustar. "
            "Pode dar vários comandos de uma vez: **foto 1: fundo branco · foto 3: remova os textos**"
        )

        for autor, conteudo in st.session_state.get("img_chat_log", []):
            with st.chat_message(autor):
                if isinstance(conteudo, bytes):
                    st.image(conteudo, use_container_width=True)
                else:
                    st.markdown(conteudo)

        instrucao_img = st.chat_input(
            "Ex: foto 1: fundo branco · foto 2: destaque os benefícios · foto 5: remova o texto do topo"
        )

        if instrucao_img:
            import re as _re

            def _parsear_comandos(texto):
                """Extrai pares (numero, instrucao) quando o usuário usa 'foto N:' ou 'imagem N:'."""
                padrao = r'(?:foto|imagem)\s*(\d+)\s*[:\-]\s*(.+?)(?=(?:foto|imagem)\s*\d+\s*[:\-]|$)'
                matches = _re.findall(padrao, texto, _re.IGNORECASE | _re.DOTALL)
                if matches:
                    return [(int(n), inst.strip().rstrip('·,').strip()) for n, inst in matches]
                return None

            comandos = _parsear_comandos(instrucao_img)
            fotos_ref = st.session_state.get("img_fotos_originais") or [imagem_ativa]
            dados_desc_aj = st.session_state.get("img_dados_descricao")
            instr_orig = st.session_state.get("img_instrucoes_originais", "")

            st.session_state["img_chat_log"].append(("user", instrucao_img))

            if comandos:
                # ── Modo multi-foto: processa cada comando separadamente ──────
                msgs = []
                for num_foto, instrucao in comandos:
                    idx_alvo = num_foto - 1
                    if idx_alvo < 0 or idx_alvo >= len(galeria):
                        msgs.append(f"⚠️ Foto {num_foto} não existe na galeria ({len(galeria)} imagens geradas).")
                        continue
                    tipo_alvo = galeria[idx_alvo]["tipo"]
                    prompt_aj = montar_prompt_imagem(tipo_alvo, instr_orig, dados_desc_aj, nome_gal) \
                        + f"\n\nCORREÇÃO OBRIGATÓRIA (aplique antes de tudo):\n{instrucao}"
                    with st.spinner(f"Regenerando foto {num_foto} ({tipo_alvo[:30]})..."):
                        nova_img, err_aj = gerar_imagem_ia(prompt_aj, fotos_ref)
                    if err_aj:
                        msgs.append(f"⚠️ Foto {num_foto}: não consegui gerar — {err_aj}")
                    else:
                        st.session_state["img_galeria"][idx_alvo]["bytes"] = nova_img
                        msgs.append(f"✅ Foto {num_foto} ({tipo_alvo[:25]}) atualizada.")
                st.session_state["img_chat_log"].append(("assistant", "\n\n".join(msgs)))

            else:
                # ── Modo foto ativa (sem número informado) ───────────────────
                prompt_aj = montar_prompt_imagem(tipo_ativo, instr_orig, dados_desc_aj, nome_gal) \
                    + f"\n\nCORREÇÃO OBRIGATÓRIA (aplique antes de tudo):\n{instrucao_img}"
                with st.spinner(f"Regenerando {tipo_ativo[:40]}..."):
                    nova_img, err_aj = gerar_imagem_ia(prompt_aj, fotos_ref)
                if err_aj:
                    st.session_state["img_chat_log"].append(("assistant", f"⚠️ Não consegui gerar: {err_aj}"))
                else:
                    st.session_state["img_galeria"][idx_ativo]["bytes"] = nova_img
                    st.session_state["img_chat_log"].append(("assistant", nova_img))

            st.rerun()

        st.markdown("---")

        # ── APROVAÇÃO E SALVAMENTO ─────────────────────────────────────────────
        st.markdown("### ✅ Aprovar e salvar todas as imagens")
        pasta_pai = st.secrets.get("DRIVE_PASTA_IMAGENS_ID", "")

        # Busca pasta existente para mostrar ao colaborador
        pastas_encontradas = []
        if pasta_pai and nome_gal:
            with st.spinner("Verificando pasta no Drive..."):
                pastas_encontradas = buscar_pasta_produto(nome_gal, codigo_gal, pasta_pai)

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

        col_aprovar, col_zip = st.columns(2)

        if col_aprovar.button(
            f"☁️ APROVAR E SALVAR no Drive ({len(galeria)} imagens)",
            type="primary",
            use_container_width=True,
        ):
            if not pasta_pai:
                st.error("DRIVE_PASTA_IMAGENS_ID não configurada nas Secrets.")
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

                barra_salvar.progress(1.0, text="Concluído!")
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
                    f"✅ {len(links_salvos)} imagem(ns) salvas no Drive! "
                    f"[Abrir pasta]({link_pasta})"
                )

        # ZIP sempre disponível
        zip_bytes = criar_zip_galeria(galeria, nome_gal)
        col_zip.download_button(
            f"⬇️ Baixar todas em ZIP ({len(galeria)} imagens)",
            data=zip_bytes,
            file_name=f"{nome_gal}_imagens.zip",
            mime="application/zip",
            use_container_width=True,
        )
