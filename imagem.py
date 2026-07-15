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
    st.caption("Sobe a foto real do produto. Você pode gerar 1 imagem por vez, ou as 7 do padrão de uma vez (cada uma é uma geração separada, não uma imagem só com tudo junto).")

    nome_produto = st.text_input("Nome do produto", key="img_nome_produto_input")

    foto_produto = st.file_uploader("Foto real do produto (referência)", type=["jpg", "jpeg", "png", "webp"])

    modo = st.radio("O que gerar?", ["1 imagem específica", "As 7 imagens do padrão (separadas)"], horizontal=True)

    INSTRUCAO_VARIACAO = (
        "IMPORTANTE: use a imagem de referência anexada só pra manter o PRODUTO reconhecível e fiel "
        "ao original (mesma cor, mesmo formato, mesmos detalhes) -- mas componha uma cena/imagem "
        "NOVA e apropriada pra esse pedido específico, não reaproveite a foto de referência literalmente "
        "sem mudança nenhuma. Paleta de cores: azul e branco. Texto sempre correto, sem erro de "
        "ortografia, em português do Brasil."
    )

    if modo == "1 imagem específica":
        tipo = st.selectbox("Tipo de imagem", list(PRESETS.keys()))
        prompt_base = PRESETS[tipo]

        instrucoes = st.text_area(
            "Descreva o que você quer nessa imagem (textos, cenas, destaque)",
            value=prompt_base, height=140, key=f"img_instrucoes_{tipo}",
            placeholder="ex: título 'Guarda suas memórias com estilo', 3 benefícios: durabilidade, capa dura, folhas pretas...",
        )

        conferir = st.button("Conferir pedido antes de gerar", type="primary", use_container_width=True)

        if conferir:
            if not foto_produto:
                st.warning("Sobe a foto real do produto -- é a referência que garante que o produto gerado é reconhecível.")
            elif not instrucoes:
                st.warning("Descreve o que você quer na imagem.")
            else:
                st.session_state["img_pedido_pendente"] = {
                    "modo": "unico", "tipo": tipo, "instrucoes": instrucoes,
                    "foto_bytes": foto_produto.getvalue(), "nome_produto": nome_produto or "produto",
                }

    else:
        st.caption("Gera as 7 imagens do padrão, uma por vez -- cada uma é uma peça separada, não um grid único.")
        conferir_todas = st.button("Conferir pedido antes de gerar", type="primary", use_container_width=True)

        if conferir_todas:
            if not foto_produto:
                st.warning("Sobe a foto real do produto -- é a referência que garante que o produto gerado é reconhecível.")
            else:
                st.session_state["img_pedido_pendente"] = {
                    "modo": "lote", "foto_bytes": foto_produto.getvalue(),
                    "nome_produto": nome_produto or "produto",
                }

    # ── ETAPA DE CONFERENCIA -- mostra em TEXTO o que vai ser pedido, sem gastar
    # nada com a IA ainda. So depois de confirmar aqui e que a chamada paga acontece.
    if "img_pedido_pendente" in st.session_state:
        pedido = st.session_state["img_pedido_pendente"]
        st.markdown("---")
        st.markdown("##### Confira antes de gerar (essa etapa não gasta nada)")
        st.image(pedido["foto_bytes"], caption="Foto de referência que será usada", width=200)

        if pedido["modo"] == "unico":
            n_imagens = 1
            st.markdown(f"**Tipo de imagem:** {pedido['tipo']}")
            st.markdown("**Instrução que será enviada pra IA:**")
            st.info(pedido["instrucoes"])
        else:
            tipos_reais = [t for t in PRESETS.keys() if t != "Personalizado (descrevo o que quero)"]
            n_imagens = len(tipos_reais)
            st.markdown(f"**{n_imagens} imagens serão geradas, uma por vez:**")
            for t in tipos_reais:
                with st.expander(t):
                    st.write(PRESETS[t])

        custo_estimado = n_imagens * 1.0  # ~R$1,00 por imagem em 2K (aproximado, varia com cambio)
        st.warning(f"💰 Isso vai gerar {n_imagens} imagem(ns) de verdade, com custo estimado de **~R${custo_estimado:.2f}** (aproximado). Confirma?")

        col1, col2 = st.columns(2)
        cancelar = col1.button("❌ Cancelar", use_container_width=True)
        confirmar_gerar = col2.button("✅ Confirmar e gerar", type="primary", use_container_width=True)

        if cancelar:
            del st.session_state["img_pedido_pendente"]
            st.rerun()

        if confirmar_gerar:
            if pedido["modo"] == "unico":
                prompt_final = f"{pedido['instrucoes']}\n\n{INSTRUCAO_VARIACAO}"
                with st.spinner("Gerando imagem (pode levar alguns segundos)..."):
                    imagem_bytes, erro = gerar_imagem_ia(prompt_final, [pedido["foto_bytes"]])

                if erro:
                    st.error(f"Não consegui gerar a imagem: {erro}")
                else:
                    st.session_state["img_galeria"] = [{"tipo": pedido["tipo"], "bytes": imagem_bytes}]
                    st.session_state["img_nome_produto"] = pedido["nome_produto"]
                    st.session_state["img_chat_log"] = []
                    import atividades
                    atividades.registrar_atividade(usuario_logado, "Imagem", pedido["nome_produto"], pedido["tipo"])
                    del st.session_state["img_pedido_pendente"]
                    st.rerun()
            else:
                tipos_reais = [t for t in PRESETS.keys() if t != "Personalizado (descrevo o que quero)"]
                galeria = []
                barra = st.progress(0.0, text="Gerando imagens...")
                for i, t in enumerate(tipos_reais):
                    prompt_final = f"{PRESETS[t]}\n\n{INSTRUCAO_VARIACAO}"
                    barra.progress(i / len(tipos_reais), text=f"Gerando: {t}")
                    img_bytes, erro = gerar_imagem_ia(prompt_final, [pedido["foto_bytes"]])
                    if erro:
                        st.warning(f"Falhou em '{t}': {erro}")
                        continue
                    galeria.append({"tipo": t, "bytes": img_bytes})
                barra.progress(1.0, text="Concluído!")

                st.session_state["img_galeria"] = galeria
                st.session_state["img_nome_produto"] = pedido["nome_produto"]
                st.session_state["img_chat_log"] = []
                import atividades
                atividades.registrar_atividade(usuario_logado, "Imagem (lote de 7)", pedido["nome_produto"], f"{len(galeria)} imagens geradas")
                del st.session_state["img_pedido_pendente"]
                st.rerun()

    if "img_galeria" in st.session_state and st.session_state["img_galeria"]:
        st.markdown("---")
        galeria = st.session_state["img_galeria"]

        if len(galeria) == 1:
            idx_ativo = 0
            st.image(galeria[0]["bytes"], caption=galeria[0]["tipo"], use_container_width=True)
        else:
            nomes_galeria = [g["tipo"] for g in galeria]
            escolha_galeria = st.selectbox("Qual imagem ver/ajustar/salvar?", nomes_galeria, key="img_escolha_galeria")
            idx_ativo = nomes_galeria.index(escolha_galeria)
            cols = st.columns(len(galeria))
            for i, g in enumerate(galeria):
                with cols[i]:
                    st.image(g["bytes"], caption=g["tipo"][:12], use_container_width=True)

        imagem_ativa = galeria[idx_ativo]["bytes"]
        tipo_ativo = galeria[idx_ativo]["tipo"]

        col1, col2 = st.columns(2)
        col1.download_button("⬇️ Baixar essa imagem", data=imagem_ativa,
                              file_name=f"{st.session_state['img_nome_produto']}_{tipo_ativo[:20]}.png", mime="image/png",
                              use_container_width=True, key=f"download_{idx_ativo}")

        if col2.button("☁️ Salvar no Google Drive", use_container_width=True, key=f"salvar_drive_{idx_ativo}"):
            with st.spinner("Enviando pro Drive..."):
                link, erro_drive = upload_imagem_drive(
                    imagem_ativa, f"{st.session_state['img_nome_produto']}_{tipo_ativo[:20]}.png",
                )
            if erro_drive:
                st.error(f"Não consegui salvar no Drive: {erro_drive}")
            else:
                st.success(f"Salvo! [Abrir no Drive]({link})")
                import atividades
                atividades.registrar_atividade(usuario_logado, "Imagem (salva no Drive)", st.session_state["img_nome_produto"], tipo_ativo)

        st.markdown("##### Precisa ajustar algo pontual? (na imagem selecionada acima)")
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
                nova_imagem, erro_ajuste = gerar_imagem_ia(prompt_ajuste, [imagem_ativa])

            if erro_ajuste:
                st.session_state["img_chat_log"].append(("assistant", f"⚠️ Não consegui ajustar: {erro_ajuste}"))
            else:
                st.session_state["img_galeria"][idx_ativo]["bytes"] = nova_imagem
                st.session_state["img_chat_log"].append(("assistant", nova_imagem))

                import atividades
                atividades.registrar_atividade(usuario_logado, "Ajuste de Imagem", st.session_state["img_nome_produto"], instrucao_img[:100])

            st.rerun()
