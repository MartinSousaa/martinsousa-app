"""
video.py
Gerador de prompt para vídeo no Envato Elements.
Fluxo: busca triagem/descrição → colaborador descreve a ação →
upload dos frames inicial/final → IA gera o prompt otimizado.
"""
import streamlit as st
import anthropic
import base64
import triagem as _triagem
import chat_assistente

CAMPOS_TRIAGEM = ["nome_comercial", "material", "variacao_cores", "diferenciais", "uso"]


def _mime(data: bytes) -> str:
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if data[:2] == b'\xff\xd8':
        return "image/jpeg"
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return "image/webp"
    return "image/jpeg"


def _gerar_prompt_video(dados_produto: dict, acao: str, observacoes: str,
                         frame_inicial: bytes | None, frame_final: bytes | None) -> tuple:
    """Chama a API Anthropic para gerar o prompt de vídeo.
    Retorna (prompt_gerado, aviso_imagens, erro)."""
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None, None, "ANTHROPIC_API_KEY não configurada."

    nome    = dados_produto.get("nome_comercial", "produto")
    material = dados_produto.get("material", "")
    cores    = dados_produto.get("variacao_cores", "")
    difs     = dados_produto.get("diferenciais", "")
    uso      = dados_produto.get("uso", "")

    contexto_produto = f"PRODUTO: {nome}"
    if material:   contexto_produto += f"\nMaterial: {material}"
    if cores:      contexto_produto += f"\nCor/variações: {cores}"
    if difs:       contexto_produto += f"\nDiferenciais: {difs}"
    if uso:        contexto_produto += f"\nUso/ocasião: {uso}"

    tem_frames = bool(frame_inicial or frame_final)

    system = """You are an expert at writing prompts for AI video generators, specifically Envato Elements.

CRITICAL CONSTRAINT — ENVATO ELEMENTS LIMITATION:
The Envato Elements video generator accepts ONLY two reference images: the opening frame and the
closing frame. There is NO way to attach additional product reference photos. This means the
text prompt must carry all the descriptive weight for product fidelity — describe visible color,
shape and key features explicitly in the prompt text itself.

LANGUAGE: Always write the output prompt in ENGLISH. English produces significantly better
results in Envato Elements' AI model than Portuguese.

OUTPUT FORMAT:
- 3 to 4 short sentences describing the scene in chronological order
- Vivid, visual, screenplay-style language
- Always end with: "natural hand movements, product maintains exact proportions and shape
  from the reference frames, smooth continuous motion."

REQUIRED ELEMENTS IN EVERY PROMPT:
A) MOVEMENT INTENSITY — always specify exactly how heavy or light the gesture is:
   - Light: "with gentle pressure", "light touch", "softly presses", "barely pressing"
   - Moderate: "with steady, even pressure", "firm but controlled"
   - Heavy: "presses firmly downward", "with deliberate force"
   Never leave movement intensity ambiguous — the generator will invent it and usually gets it wrong.

B) PRODUCT PROPORTIONS — NEVER use centimeters or millimeters. Use these anchor phrases instead:
   - "product appears in its natural real-world proportions"
   - "product scale exactly matches the reference frames"
   - "product occupies the same visual area as shown in the reference frames"
   Reason: measurements cause the generator to distort the product to fit numbers. Proportion
   anchors tell it to replicate what it sees in the frames.

C) PRODUCT SHAPE LOCK — include one of these to prevent deformation:
   - "product shape remains completely unchanged throughout"
   - "product stays as one solid piece, no parts separate or open"
   - "product maintains its exact form and structure"

ABSOLUTE RULES — NEVER VIOLATE:
1. Describe ONLY what is visible in the frames or explicitly stated. Never invent colors, shapes,
   mechanisms or details not confirmed in the information given.
2. FORBIDDEN: inventing mechanisms. Only describe what was informed. Never create actions
   that do not exist.
3. FORBIDDEN: scenes or elements outside what appears in the frames.
4. SHORT: maximum 4 sentences. Longer prompts confuse the generator and reduce consistency.
5. Do NOT describe what the product does NOT do (e.g. "without opening", "without tilting") —
   state what it DOES do instead. Negative instructions confuse AI video generators.

SECONDARY TASK — EVALUATE THE FRAMES:
If frames were provided, assess whether they give the generator enough visual information.
Field "aviso_frames":
- Sufficient: empty string ""
- Insufficient: direct message explaining what is missing and why it matters for the video.

RESPOND ONLY with valid JSON:
{
  "prompt": "generated prompt here (in English)",
  "aviso_frames": "warning if any, empty string if ok"
}"""

    # Monta o conteúdo da mensagem
    partes_user = []

    partes_user.append({
        "type": "text",
        "text": (
            f"{contexto_produto}\n\n"
            f"AÇÃO DESEJADA NO VÍDEO:\n{acao}\n\n"
            + (f"OBSERVAÇÕES EXTRAS:\n{observacoes}\n\n" if observacoes.strip() else "")
            + (
                f"Frames de referência enviados: {('frame inicial' if frame_inicial else '')} "
                f"{('e frame final' if frame_final else '')}\n"
                if tem_frames else
                "Nenhum frame de referência enviado.\n"
            )
            + "\nGere o prompt de vídeo conforme as instruções."
        )
    })

    if frame_inicial:
        partes_user.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": _mime(frame_inicial),
                "data": base64.b64encode(frame_inicial).decode(),
            }
        })
        partes_user.append({"type": "text", "text": "↑ Frame inicial (quadro de abertura do vídeo)"})

    if frame_final:
        partes_user.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": _mime(frame_final),
                "data": base64.b64encode(frame_final).decode(),
            }
        })
        partes_user.append({"type": "text", "text": "↑ Frame final (quadro de encerramento do vídeo)"})

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=system,
            messages=[{"role": "user", "content": partes_user}],
        )
        import json, re
        texto = msg.content[0].text.strip()
        # Remove bloco de código markdown se vier embrulhado
        texto = re.sub(r"^```(?:json)?\s*", "", texto)
        texto = re.sub(r"\s*```$", "", texto)
        dados = json.loads(texto)
        return dados.get("prompt", ""), dados.get("aviso_frames", ""), None
    except Exception as e:
        return None, None, str(e)


def _ajustar_prompt_video(prompt_atual: str, instrucao: str, dados_produto: dict) -> tuple:
    """Ajusta o prompt via chat. Retorna (novo_prompt, erro)."""
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return prompt_atual, "ANTHROPIC_API_KEY não configurada."

    nome = dados_produto.get("nome_comercial", "produto")

    system = """You adjust prompts for AI video generators (Envato Elements).
Keep all rules: short (max 4 sentences), always in English, movement intensity explicitly stated,
product proportions anchored without measurements (use "natural real-world proportions" or
"exact proportions from reference frames"), product shape locked, no invented mechanisms or scenes.
Return ONLY the adjusted prompt, no explanation, no extra quotes."""

    prompt_msg = (
        f"Prompt atual para o produto \"{nome}\":\n\n{prompt_atual}\n\n"
        f"Ajuste solicitado: {instrucao}\n\n"
        "Retorne SOMENTE o prompt ajustado."
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            system=system,
            messages=[{"role": "user", "content": prompt_msg}],
        )
        return msg.content[0].text.strip().strip('"'), None
    except Exception as e:
        return prompt_atual, str(e)


# ── INTERFACE ──────────────────────────────────────────────────────────────────

def pagina_video(usuario_logado):
    st.subheader("Vídeo")
    st.caption(
        "Busca a Triagem do produto, descreva o que acontece no vídeo e (opcional) "
        "suba os frames inicial e final. A IA monta o prompt otimizado para o Envato Elements."
    )

    # ── BUSCA TRIAGEM ──────────────────────────────────────────────────────────
    busca = st.text_input("Nome do produto", key="vid_busca_nome")

    dados_iniciais = {c: "" for c in CAMPOS_TRIAGEM}
    aviso_triagem = None

    if busca:
        try:
            encontrados = _triagem.buscar_triagens_por_trecho(busca)
        except Exception:
            encontrados = []

        if len(encontrados) == 1:
            dados_iniciais.update(encontrados[0])
            aviso_triagem = ("info", f"Triagem encontrada: **{encontrados[0]['nome_comercial']}**. Confira os dados abaixo.")
        elif len(encontrados) > 1:
            nomes = [e["nome_comercial"] for e in encontrados]
            escolha = st.selectbox("Mais de um produto encontrado — qual é?", nomes, key="vid_escolha")
            selecionado = next(e for e in encontrados if e["nome_comercial"] == escolha)
            dados_iniciais.update(selecionado)
            aviso_triagem = ("info", "Confira os dados abaixo antes de gerar.")
        else:
            dados_iniciais["nome_comercial"] = busca
            aviso_triagem = ("warning", "Nenhuma triagem encontrada — preencha os campos abaixo.")

    if aviso_triagem:
        getattr(st, aviso_triagem[0])(aviso_triagem[1])

    # ── FORMULÁRIO ─────────────────────────────────────────────────────────────
    with st.form("form_video"):
        col1, col2 = st.columns(2)
        nome_comercial = col1.text_input(
            "Nome comercial",
            value=dados_iniciais.get("nome_comercial", ""),
            key="vid_nome"
        )
        material = col2.text_input(
            "Material",
            value=dados_iniciais.get("material", ""),
            key="vid_material"
        )

        col3, col4 = st.columns(2)
        cores = col3.text_input(
            "Cor / variações",
            value=dados_iniciais.get("variacao_cores", ""),
            key="vid_cores"
        )
        uso = col4.text_input(
            "Uso / ocasião",
            value=dados_iniciais.get("uso", ""),
            key="vid_uso"
        )

        diferenciais = st.text_area(
            "Diferenciais do produto",
            value=dados_iniciais.get("diferenciais", ""),
            key="vid_diferenciais",
            height=68,
        )

        st.markdown("---")
        acao = st.text_area(
            "O que acontece no vídeo?",
            placeholder=(
                "Descreva o que a pessoa faz com o produto — inclua a intensidade do gesto. "
                "Ex: A mulher pressiona levemente o furador, retira o papel e o exibe para a câmera mostrando os furos."
            ),
            key="vid_acao",
            height=100,
        )

        intensidade = st.select_slider(
            "Intensidade do movimento principal",
            options=["Muito leve / delicado", "Leve", "Moderado", "Firme", "Forte / brusco"],
            value="Leve",
            key="vid_intensidade",
        )

        observacoes = st.text_area(
            "Observações extras (opcional)",
            placeholder="Ângulo de câmera, posição do produto, contexto da cena...",
            key="vid_obs",
            height=68,
        )

        st.markdown("---")
        st.markdown("**Frames de referência** (obrigatório para melhor resultado)")
        st.caption(
            "⚠️ **Limitação do Envato Elements:** o gerador de vídeo aceita APENAS o frame inicial "
            "e o frame final como referência visual — não é possível anexar fotos extras do produto. "
            "Por isso, os frames precisam mostrar o produto com clareza total."
        )
        col_f1, col_f2 = st.columns(2)
        frame_inicial_up = col_f1.file_uploader(
            "Quadro inicial", type=["jpg", "jpeg", "png", "webp"],
            key="vid_frame_ini"
        )
        frame_final_up = col_f2.file_uploader(
            "Quadro final", type=["jpg", "jpeg", "png", "webp"],
            key="vid_frame_fim"
        )

        gerar = st.form_submit_button("Gerar Prompt", type="primary", use_container_width=True)

    if gerar:
        if not nome_comercial:
            st.warning("Preencha pelo menos o Nome comercial.")
            return
        if not acao.strip():
            st.warning("Descreva o que acontece no vídeo antes de gerar.")
            return

        intensidade = st.session_state.get("vid_intensidade", "Leve")

        dados = {
            "nome_comercial": nome_comercial,
            "material": material,
            "variacao_cores": cores,
            "diferenciais": diferenciais,
            "uso": uso,
        }

        frame_ini_bytes = frame_inicial_up.getvalue() if frame_inicial_up else None
        frame_fim_bytes = frame_final_up.getvalue() if frame_final_up else None

        # Incorpora intensidade nas observações para passar à API
        obs_completas = observacoes.strip()
        obs_completas = f"Intensidade do movimento: {intensidade}.\n{obs_completas}".strip()

        with st.spinner("Gerando prompt de vídeo..."):
            prompt_gerado, aviso_frames, erro = _gerar_prompt_video(
                dados, acao, obs_completas, frame_ini_bytes, frame_fim_bytes
            )

        if erro:
            st.error(f"Erro ao gerar prompt: {erro}")
            return

        import atividades
        atividades.registrar_atividade(
            usuario_logado, "Vídeo", nome_comercial, "Prompt de vídeo gerado"
        )

        # Comunica ao colaborador via chatbot lateral
        if aviso_frames:
            chat_assistente.iniciar_conversa(
                f"⚠️ **Atenção sobre os frames do vídeo de \"{nome_comercial}\":** {aviso_frames}\n\n"
                "Suba frames melhores e clique em **Gerar Prompt** novamente para um resultado mais fiel."
            )
        else:
            chat_assistente.iniciar_conversa(
                f"✅ Prompt de vídeo gerado para **{nome_comercial}**! "
                "Copie o texto na aba **Vídeo** e cole no Envato Elements junto com as imagens dos frames. "
                "Se precisar de ajustes, use o chat de ajuste abaixo do prompt ou me peça aqui."
            )

        st.session_state["vid_prompt_atual"] = prompt_gerado
        st.session_state["vid_dados_produto"] = dados
        st.session_state["vid_aviso_frames"] = aviso_frames
        st.session_state["vid_chat_log"] = []
        st.rerun()

    # ── RESULTADO ──────────────────────────────────────────────────────────────
    prompt_atual = st.session_state.get("vid_prompt_atual")
    if not prompt_atual:
        return

    dados_produto = st.session_state.get("vid_dados_produto", {})
    aviso_frames  = st.session_state.get("vid_aviso_frames", "")
    nome_exibir   = dados_produto.get("nome_comercial", "produto")

    st.markdown("---")
    st.markdown(f"#### Prompt de vídeo — {nome_exibir}")

    if aviso_frames:
        st.warning(f"⚠️ **Atenção sobre os frames:** {aviso_frames}")

    st.code(prompt_atual, language=None)
    st.caption("Copie o texto acima e cole no Envato Elements junto com as imagens dos frames.")

    # ── CHAT DE AJUSTE ─────────────────────────────────────────────────────────
    st.markdown("##### Ajustar prompt")
    st.caption(
        "Peça alterações no prompt. "
        "Ex: *mencione que a câmera faz um zoom suave* · *tire qualquer menção a cores* · *deixe mais curto*"
    )

    for autor, mensagem in st.session_state.get("vid_chat_log", []):
        with st.chat_message(autor):
            st.markdown(mensagem)

    instrucao_vid = st.chat_input(
        "Peça um ajuste no prompt — ex: adicione movimento de câmera, remova detalhes de cor..."
    )

    if instrucao_vid:
        st.session_state["vid_chat_log"].append(("user", instrucao_vid))

        with st.spinner("Ajustando prompt..."):
            novo_prompt, erro_aj = _ajustar_prompt_video(
                prompt_atual, instrucao_vid, dados_produto
            )

        if erro_aj:
            st.session_state["vid_chat_log"].append(("assistant", f"⚠️ Erro ao ajustar: {erro_aj}"))
        else:
            st.session_state["vid_prompt_atual"] = novo_prompt
            st.session_state["vid_chat_log"].append(
                ("assistant", f"✅ Prompt atualizado.")
            )

        st.rerun()