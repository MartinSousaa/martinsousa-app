import streamlit as st
import requests
import base64

MODELO_IMAGEM = "gemini-3-pro-image-preview"  # Nano Banana Pro -- melhor renderização de texto em imagem

PRESETS = {
    "Personalizado (descrevo o que quero)": "",
    "1 -- Produto com fundo branco": (
        "Foto de produto limpa e profissional, fundo branco liso, produto centralizado, "
        "iluminação de estúdio, sem texto sobreposto."
    ),
    "2 -- Benefícios do produto": (
        "Peça de marketing com título curto no topo destacando o principal benefício do produto, "
        "abaixo blocos lado a lado, cada um com um ícone simples, um título curto e uma frase "
        "explicando um benefício diferente que o produto agrega. Fundo azul e branco, visual "
        "limpo e moderno."
    ),
    "3 -- Benefícios no cenário de uso": (
        "Peça de marketing mostrando o produto sendo usado em cenários reais do dia a dia, com "
        "frases curtas de destaque explicando o que o produto agrega na prática em cada cena. "
        "Fundo azul e branco, visual limpo e moderno."
    ),
    "4 -- Close nos detalhes do produto": (
        "Imagem em zoom aproximado valorizando os detalhes de acabamento e qualidade do produto, "
        "com pequenas legendas apontando pra cada detalhe importante. Fundo azul e branco."
    ),
    "5 -- Características (medidas/peso/material)": (
        "Imagem técnica do produto com linhas de medida (estilo desenho técnico) mostrando altura, "
        "largura e profundidade exatas, além de peso e material, com os dados anotados de forma "
        "clara. Fundo branco, visual limpo e técnico."
    ),
    "6 -- Quebra de objeção": (
        "Peça de marketing respondendo de forma direta e visual as principais dúvidas que um "
        "cliente teria antes de comprar esse produto (ex: qualidade, durabilidade, garantia, "
        "funcionamento) -- formato de perguntas curtas com respostas objetivas ao lado. Fundo "
        "azul e branco, visual limpo, transmitindo confiança."
    ),
    "7 -- Presenteie": (
        "Peça de marketing emocional incentivando a compra do produto como presente, com frase "
        "impactante de destaque e uma cena mostrando o momento de presentear (entrega/reação "
        "positiva). Fundo azul e branco, visual acolhedor."
    ),
}


def gerar_imagem_ia(prompt_texto, imagens_referencia):
    """imagens_referencia: lista de bytes de imagem (a foto real do produto, e/ou
    outras referencias). Retorna (imagem_bytes, erro)."""
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
            json=body, timeout=60,
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
        return None, "A IA respondeu, mas não veio nenhuma imagem no resultado (pode ter bloqueado o pedido)."
    except Exception as e:
        return None, str(e)


# ── UPLOAD PRO GOOGLE DRIVE ─────────────────────────────────────────────────

def _drive_service():
    from googleapiclient.discovery import build
    from google.oauth2.service_account import Credentials
    creds_dict = dict(st.secrets["gcp_service_account"])
    scopes = ["https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return build("drive", "v3", credentials=creds)


def upload_imagem_drive(imagem_bytes, nome_arquivo):
    """Sobe a imagem pra pasta do Drive configurada e devolve o link publico
    de visualizacao. Retorna (link, erro)."""
    from googleapiclient.http import MediaInMemoryUpload

    pasta_id = st.secrets.get("DRIVE_PASTA_IMAGENS_ID", "")
    if not pasta_id:
        return None, "DRIVE_PASTA_IMAGENS_ID não configurada nas Secrets."
    try:
        service = _drive_service()
        metadata = {"name": nome_arquivo, "parents": [pasta_id]}
        media = MediaInMemoryUpload(imagem_bytes, mimetype="image/png")
        arquivo = service.files().create(body=metadata, media_body=media, fields="id, webViewLink").execute()
        service.permissions().create(fileId=arquivo["id"], body={"role": "reader", "type": "anyone"}).execute()
        return arquivo.get("webViewLink"), None
    except Exception as e:
        return None, str(e)


# ── INTERFACE ──────────────────────────────────────────────────────────────────

def pagina_imagem(usuario_logado):
    st.subheader("Imagem")
    st.caption("Sobe a foto real do produto, escolhe o tipo de imagem e a IA gera a peça completa (texto, layout e fotos juntos).")

    nome_produto = st.text_input("Nome do produto", key="img_nome_produto_input")

    foto_produto = st.file_uploader("Foto real do produto (referência)", type=["jpg", "jpeg", "png", "webp"])

    tipo = st.selectbox("Tipo de imagem", list(PRESETS.keys()))
    prompt_base = PRESETS[tipo]

    instrucoes = st.text_area(
        "Descreva o que você quer nessa imagem (textos, cenas, destaque)",
        value=prompt_base,
        height=140,
        placeholder="ex: título 'Guarda suas memórias com estilo', 3 benefícios: durabilidade, capa dura, folhas pretas...",
    )

    st.caption("Paleta: azul + branco (padrão da empresa) -- já incluída automaticamente no pedido.")

    gerar = st.button("Gerar Imagem", type="primary", use_container_width=True)

    if gerar:
        if not foto_produto:
            st.warning("Sobe a foto real do produto -- é a referência que garante que o produto gerado é reconhecível.")
            return
        if not instrucoes:
            st.warning("Descreve o que você quer na imagem.")
            return

        prompt_final = (
            f"{instrucoes}\n\n"
            f"IMPORTANTE: use a imagem de referência anexada como base real do produto -- mantenha o "
            f"produto reconhecível e fiel ao original, não invente um produto diferente. "
            f"Paleta de cores: azul e branco (fundo/detalhes em azul, texto e áreas neutras em branco). "
            f"Texto sempre correto, sem erro de ortografia, em português do Brasil."
        )

        foto_bytes = foto_produto.read()

        with st.spinner("Gerando imagem (pode levar alguns segundos)..."):
            imagem_bytes, erro = gerar_imagem_ia(prompt_final, [foto_bytes])

        if erro:
            st.error(f"Não consegui gerar a imagem: {erro}")
            return

        st.session_state["img_gerada"] = imagem_bytes
        st.session_state["img_nome_produto"] = nome_produto or "produto"
        st.session_state["img_chat_log"] = []

        import atividades
        atividades.registrar_atividade(usuario_logado, "Imagem", st.session_state["img_nome_produto"], tipo)

    if "img_gerada" in st.session_state:
        st.markdown("---")
        st.image(st.session_state["img_gerada"], caption="Imagem gerada", use_container_width=True)

        col1, col2 = st.columns(2)
        col1.download_button("⬇️ Baixar imagem", data=st.session_state["img_gerada"],
                              file_name=f"{st.session_state['img_nome_produto']}.png", mime="image/png",
                              use_container_width=True)

        if col2.button("☁️ Salvar no Google Drive", use_container_width=True):
            with st.spinner("Enviando pro Drive..."):
                link, erro_drive = upload_imagem_drive(
                    st.session_state["img_gerada"],
                    f"{st.session_state['img_nome_produto']}_{tipo[:20]}.png",
                )
            if erro_drive:
                st.error(f"Não consegui salvar no Drive: {erro_drive}")
            else:
                st.success(f"Salvo! [Abrir no Drive]({link})")
                import atividades
                atividades.registrar_atividade(usuario_logado, "Imagem (salva no Drive)", st.session_state["img_nome_produto"], tipo)

        st.markdown("##### Precisa ajustar algo pontual?")
        st.caption("Ex: 'troca a foto da direita por uma cena de presente', 'deixa o fundo mais escuro', 'aumenta o título' -- a IA edita em cima da imagem atual, sem começar do zero.")

        for autor, conteudo in st.session_state.get("img_chat_log", []):
            with st.chat_message(autor):
                if isinstance(conteudo, bytes):
                    st.image(conteudo, use_container_width=True)
                else:
                    st.markdown(conteudo)

        instrucao_img = st.chat_input("Digite o ajuste que precisa...")
        if instrucao_img:
            st.session_state["img_chat_log"].append(("user", instrucao_img))

            prompt_ajuste = (
                f"Ajuste essa imagem exatamente assim: {instrucao_img}\n\n"
                f"Mantenha tudo o resto da imagem igual (mesmo layout, mesmas fotos, mesmo texto), "
                f"só aplique o que foi pedido. Continue com a paleta azul e branco, texto sempre "
                f"correto em português do Brasil."
            )
            with st.spinner("Ajustando imagem..."):
                nova_imagem, erro_ajuste = gerar_imagem_ia(prompt_ajuste, [st.session_state["img_gerada"]])

            if erro_ajuste:
                st.session_state["img_chat_log"].append(("assistant", f"⚠️ Não consegui ajustar: {erro_ajuste}"))
            else:
                st.session_state["img_gerada"] = nova_imagem
                st.session_state["img_chat_log"].append(("assistant", nova_imagem))

                import atividades
                atividades.registrar_atividade(usuario_logado, "Ajuste de Imagem", st.session_state["img_nome_produto"], instrucao_img[:100])

            st.rerun()
