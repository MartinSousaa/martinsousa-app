"""
chat_assistente.py
Chat IA unificado — Python puro, renderizado no sidebar do Streamlit.
Acesso total ao session_state: conhece produto ativo, títulos gerados,
descrição atual e galeria de imagens. Detecta intenção (Q&A vs comando)
e executa ações diretamente no session_state.
"""
import streamlit as st
import streamlit.components.v1 as components
import anthropic
import os
import re
import json
import base64


# ── PROMPT DO SISTEMA ─────────────────────────────────────────────────────────

SYSTEM_BASE = """Você é o Assistente do MS Studio, aplicativo interno da MartinSousa para
gestão de produtos em marketplaces (Mercado Livre, Shopee, Shein).

=== ESTRUTURA DO APP ===
O MS Studio tem as seguintes abas (menu lateral esquerdo):

• Título — gera 2 opções de título para uso em qualquer marketplace (ML, Shopee, Shein) — o mesmo título serve para todas as plataformas.
  Campos obrigatórios: nome do produto, categoria, material, diferenciais.
  Ação principal: botão "Gerar Título". Resultado: 2 títulos aparecem na tela (máximo 60 caracteres cada, limite do ML).

• Descrição — gera descrição completa do produto.
  Campos obrigatórios: nome do produto, diferenciais, público-alvo.
  Ação principal: botão "Gerar Descrição".

• Imagem — gera imagens tratadas do produto (fundo removido, artes para marketplace).
  Campos obrigatórios: upload de foto(s) do produto, nome, peso/dimensões.
  Ação principal: botão "Gerar Imagens". Para refazer uma imagem já gerada: botão "Regenerar" abaixo de cada foto.
  BLOQUEADA aparece quando falta peso ou gramatura — preencher esses campos e regenerar.

• Financeiro — configuração de LPV (custo fixo por venda) e alíquota tributária, mês a mês por ano.
  O LPV informado aqui alimenta os cálculos de viabilidade (UC) em Título.

• Histórico — registro de atividades da equipe (leitura).

• Usuários — gestão de usuários (apenas admins).

=== FLUXO TÍPICO ===
1. Aba Título → preenche nome, preço, categoria, peso/dimensões → clica Gerar Títulos
2. Aba Descrição → preenche os campos → clica Gerar Descrição
3. Aba Imagem → faz upload de fotos → preenche peso/dimensões → clica Gerar Imagens

=== ORIENTAÇÃO SEM PRODUTO ABERTO ===
Quando não há produto em edição, o usuário ainda pode usar qualquer aba.
Oriente assim (NUNCA mencione botões que não existem, como "Editar", "Salvar produto", "Cadastrar"):
- Para gerar título: "Vá até a aba Título, preencha o nome do produto, preço e categoria, e clique em Gerar Títulos."
- Para gerar imagem: "Vá até a aba Imagem, faça o upload da foto do produto, preencha o peso embalado e clique em Gerar Imagens."
- Para configurar financeiro: "Vá até a aba Financeiro, selecione o ano, preencha o LPV de cada mês e salve."
- Para regenerar uma imagem: "Na aba Imagem, clique em Regenerar abaixo da foto que quer refazer."

=== REGRAS DE NEGÓCIO ===
- UC mínimo aprovado: 0,8/1 (abaixo = INVIÁVEL)
- UC 0,7 = cenário de risco; UC 1,0 = equilíbrio ideal
- Mercado Livre: comissão por categoria (8%–16%), frete por peso cubado
  (comprimento × largura × altura / 6.000 — produto embalado)
- Shopee: comissão 15%–20% + R$4 adicional em produtos até R$79,99; frete grátis (vendedor não paga)
- Shein: comissão 18% flat; frete por peso real (tabela por faixas de kg)
- LPV = custo fixo médio por venda (informado manualmente na aba Financeiro)
- NF = alíquota tributária (configurada na aba Financeiro — não é calculada automaticamente)
- Custo operacional padrão inclui embalagem, logística, ADS e cross docking
- Peso e dimensões devem ser sempre do produto JÁ EMBALADO

Tom: objetivo, informal mas profissional. Responda sempre em português do Brasil.
Quando não souber algo, diga claramente em vez de inventar."""


def _mime_tipo(data: bytes) -> str:
    """Detecta o MIME type pelos magic bytes."""
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if data[:2] == b'\xff\xd8':
        return "image/jpeg"
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return "image/webp"
    return "image/jpeg"


def _api_key():
    try:
        k = st.secrets.get("ANTHROPIC_API_KEY", "")
        if k:
            return k
    except Exception:
        pass
    return os.environ.get("ANTHROPIC_API_KEY", "")


def _contexto_atual() -> str:
    """Monta bloco de contexto com o que está aberto no app."""
    partes = []

    # Nome do produto (várias fontes possíveis)
    nome = (
        (st.session_state.get("tt_dados_produto") or {}).get("nome_comercial")
        or st.session_state.get("desc_nome_atual")
        or st.session_state.get("img_nome_atual")
        or None
    )
    if nome:
        partes.append(f"PRODUTO EM EDIÇÃO: {nome}")

    # Títulos gerados
    titulos = st.session_state.get("tt_titulos_gerados")
    if titulos:
        linhas = "\n".join(f"  Opção {i+1}: {t}" for i, t in enumerate(titulos))
        partes.append(f"TÍTULOS ATUAIS:\n{linhas}")

    # Descrição
    desc = st.session_state.get("desc_texto_atual", "")
    if desc:
        trecho = desc[:500] + ("…" if len(desc) > 500 else "")
        partes.append(f"DESCRIÇÃO ATUAL (trecho):\n{trecho}")

    # Galeria de imagens
    galeria = st.session_state.get("img_galeria")
    if galeria:
        tipos = [f"  Foto {i+1}: {g.get('tipo','?')}" for i, g in enumerate(galeria)]
        partes.append(f"GALERIA DE IMAGENS ({len(galeria)} foto(s)):\n" + "\n".join(tipos))

    return "\n\n".join(partes) if partes else "Nenhum produto em edição no momento."


def _montar_system() -> str:
    """Monta o system prompt completo com contexto dinâmico."""
    ctx = _contexto_atual()

    tem_titulos = bool(st.session_state.get("tt_titulos_gerados"))
    tem_desc    = bool(st.session_state.get("desc_texto_atual"))
    tem_imgs    = bool(st.session_state.get("img_galeria"))

    if not (tem_titulos or tem_desc or tem_imgs):
        # Só Q&A — sem conteúdo gerado disponível para editar
        nota_orientacao = (
            "\n\n--- CONTEXTO DO APP ---\n"
            + ctx
            + "\n\nNota: não há títulos, descrição nem imagens gerados no momento. "
            "Se o usuário pedir ajuda para usar o app, oriente-o a acessar a aba correta "
            "e preencher os campos necessários conforme descrito na seção ORIENTAÇÃO SEM PRODUTO ABERTO acima. "
            "Nunca sugira ações como clicar em 'Editar' ou 'Salvar produto' — esses botões não existem."
        )
        return f"{SYSTEM_BASE}{nota_orientacao}"

    cmds_exemplo = []
    if tem_titulos:
        cmds_exemplo.append('{"acao":"alterar_titulo","titulos":["Título 1 ajustado","Título 2 ajustado"]}')
    if tem_desc:
        cmds_exemplo.append('{"acao":"alterar_descricao","texto":"nova descrição completa aqui"}')
    if tem_imgs:
        cmds_exemplo.append('{"acao":"ajustar_imagem","foto":1,"instrucao":"instrução de edição para a foto"}')

    exemplos_str = "\n".join(f"- <CMD>{c}</CMD>" for c in cmds_exemplo)

    instrucao_cmd = f"""
--- CONTEXTO DO APP ---
{ctx}

--- COMANDOS DISPONÍVEIS ---
Quando o colaborador pedir alteração em conteúdo já gerado, faça o ajuste E inclua ao final
da sua resposta um bloco <CMD>...</CMD> com o JSON do comando:

{exemplos_str}

REGRAS DOS COMANDOS:
- "alterar_titulo": inclua os 2 títulos COMPLETOS e já ajustados (não coloque placeholders)
- "alterar_descricao": inclua o texto COMPLETO da nova descrição
- "ajustar_imagem": descreva a instrução de edição claramente; a foto será regenerada na aba Imagem
- Use APENAS UM bloco <CMD> por resposta
- Para dúvidas sem alteração de conteúdo: responda normalmente, SEM bloco <CMD>"""

    return f"{SYSTEM_BASE}{instrucao_cmd}"


def _executar_comando(cmd: dict) -> str | None:
    """Executa o comando extraído da resposta da IA. Retorna texto de feedback."""
    acao = cmd.get("acao", "")

    if acao == "alterar_titulo":
        novos = cmd.get("titulos", [])
        if novos and isinstance(novos, list) and st.session_state.get("tt_titulos_gerados") is not None:
            validos = [str(t).strip() for t in novos if str(t).strip()]
            if validos:
                st.session_state["tt_titulos_gerados"] = validos
                return "✅ Títulos atualizados — veja na aba **Título**."
        return None

    if acao == "alterar_descricao":
        novo = cmd.get("texto", "").strip()
        if novo and st.session_state.get("desc_texto_atual") is not None:
            st.session_state["desc_texto_atual"] = novo
            return "✅ Descrição atualizada — veja na aba **Descrição**."
        return None

    if acao == "ajustar_imagem":
        try:
            foto_num  = int(cmd.get("foto", 1))
        except (ValueError, TypeError):
            foto_num  = 1
        instrucao = str(cmd.get("instrucao", "")).strip()
        galeria   = st.session_state.get("img_galeria")
        if galeria and instrucao:
            if foto_num < 1 or foto_num > len(galeria):
                return f"⚠️ Foto {foto_num} não existe (há {len(galeria)} foto(s) na galeria)."
            if "chat_img_pendente" not in st.session_state:
                st.session_state["chat_img_pendente"] = []
            st.session_state["chat_img_pendente"].append(
                {"num": foto_num, "instrucao": instrucao}
            )
            return (
                f"🔄 Instrução enviada para a **Foto {foto_num}** — "
                "abra a aba **Imagem** para ver o resultado sendo gerado."
            )
    return None


def _chamar_ia(historico: list, mensagem_usuario: str, imagens_bytes: list = None) -> tuple:
    """Chama a API Anthropic. Retorna (texto_resposta, comando_ou_None).
    imagens_bytes: lista de bytes de imagens para envio via visão (opcional)."""
    api_key = _api_key()
    if not api_key:
        return "⚠️ ANTHROPIC_API_KEY não configurada no Railway/Secrets.", None

    # Janela de contexto: últimas 14 mensagens (7 trocas) — sem imagens no histórico
    msgs_hist = historico[-14:]
    msgs = [{"role": m["role"], "content": m["content"]} for m in msgs_hist]

    # Monta conteúdo da mensagem atual (texto + imagens opcionais)
    if imagens_bytes:
        content = [{"type": "text", "text": mensagem_usuario}]
        for img_b in imagens_bytes:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": _mime_tipo(img_b),
                    "data": base64.b64encode(img_b).decode(),
                },
            })
        msgs.append({"role": "user", "content": content})
    else:
        msgs.append({"role": "user", "content": mensagem_usuario})

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1500,
            system=_montar_system(),
            messages=msgs,
        )
        texto_raw = resp.content[0].text

        # Extrai bloco <CMD>{...}</CMD>
        cmd = None
        match = re.search(r"<CMD>\s*(\{.*?\})\s*</CMD>", texto_raw, re.DOTALL)
        if match:
            try:
                cmd = json.loads(match.group(1))
            except Exception:
                cmd = None
            texto_raw = re.sub(r"\s*<CMD>.*?</CMD>", "", texto_raw, flags=re.DOTALL).strip()

        return texto_raw, cmd

    except Exception as e:
        return f"⚠️ Erro ao conectar com o assistente: {e}", None


def renderizar_chat(usuario_logado=""):
    """
    Renderiza o chat IA no sidebar.
    Chamar dentro de `with st.sidebar:` (já no contexto certo).
    """
    if "ms_chat_hist" not in st.session_state:
        st.session_state["ms_chat_hist"] = []

    hist = st.session_state["ms_chat_hist"]

    # Nome de exibição: primeiro nome em maiúscula
    partes = usuario_logado.split() if usuario_logado else []
    nome_exib = partes[0].capitalize() if partes else "você"

    # ── Container que agrupa visualmente todo o chat (box com borda via CSS :has) ──
    with st.container():
        st.markdown('<div id="ms-chat-topo"></div>', unsafe_allow_html=True)
        st.markdown(
            '<span style="font-size:10px; font-weight:700; letter-spacing:1.5px; '
            'color:var(--ms-texto-sec); text-transform:uppercase; display:block; margin-bottom:4px;">Assistente IA</span>',
            unsafe_allow_html=True,
        )

        # ── Área de mensagens com scroll ──────────────────────────────────────
        with st.container(height=430, border=False):
            if not hist:
                with st.chat_message("assistant"):
                    st.markdown(f"Olá **{nome_exib}**, como posso ajudar?")
            else:
                for msg in hist:
                    with st.chat_message(msg["role"]):
                        if msg.get("img_bytes"):
                            for ib in msg["img_bytes"]:
                                st.image(ib, use_container_width=True)
                        st.markdown(msg["content"])

        # ── Formulário de envio ───────────────────────────────────────────────
        with st.form("ms_chat_form", clear_on_submit=True):
            img_chat = st.file_uploader(
                "📎",
                type=["jpg", "jpeg", "png", "webp"],
                accept_multiple_files=False,
                key="chat_img_upload",
                label_visibility="collapsed",
            )
            user_input = st.text_area(
                "msg",
                placeholder="",
                label_visibility="collapsed",
                height=68,
            )
            # Submit fora da tela — acionado pelo JS quando Enter pressionado
            enviar = st.form_submit_button("Enviar", use_container_width=False)

        # JS: Enter envia o form; textarea auto-expande; caixa visual do chat
        components.html("""
    <script>
    (function() {
      var P = window.parent;

      // ── Injeta estilo da caixa visual uma única vez no head do pai ────────────
      if (!P.document.getElementById('ms-chat-box-style')) {
        var st = P.document.createElement('style');
        st.id = 'ms-chat-box-style';
        st.textContent = [
          '#ms-chat-box-dynamic {',
          '  border: 1px solid var(--ms-divisor) !important;',
          '  border-radius: 10px !important;',
          '  background-color: var(--ms-chat-bg) !important;',
          '  padding: 8px 10px 6px !important;',
          '  margin-top: 4px !important;',
          '  overflow: hidden !important;',
          '}'
        ].join('');
        P.document.head.appendChild(st);
      }

      function setup() {
        var sidebar = P.document.querySelector('[data-testid="stSidebar"]');
        if (!sidebar) return;

        // ── Caixa visual: remove ID anterior e re-aplica no container certo ─────
        var old = P.document.getElementById('ms-chat-box-dynamic');
        if (old) old.removeAttribute('id');

        var topoEl = sidebar.querySelector('#ms-chat-topo');
        if (topoEl) {
          // Sobe pelo DOM até o primeiro stVerticalBlock que contenha o #ms-chat-topo
          var el = topoEl.parentElement;
          while (el && el !== sidebar) {
            if (el.getAttribute && el.getAttribute('data-testid') === 'stVerticalBlock') {
              el.id = 'ms-chat-box-dynamic';
              break;
            }
            el = el.parentElement;
          }
        }

        // ── Enter para enviar; auto-expande textarea ───────────────────────────
        var form = sidebar.querySelector('[data-testid="stForm"]');
        if (!form) return;
        var ta = form.querySelector('textarea');
        if (!ta || ta._msChat) return;
        ta._msChat = true;
        function resize() {
          ta.style.height = 'auto';
          ta.style.height = Math.min(ta.scrollHeight, 150) + 'px';
        }
        ta.addEventListener('input', resize);
        ta.addEventListener('keydown', function(e) {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            var btn = form.querySelector('.stFormSubmitButton button');
            if (btn) { btn.click(); }
          }
        });
      }

      setup();
      // Guard: registra o setInterval uma única vez — sem acumular a cada st.rerun()
      if (!P._msChatIntervalId) {
        P._msChatIntervalId = setInterval(setup, 800);
      }
    })();
    </script>
    """, height=0)

    if enviar and (user_input.strip() or img_chat):
        msg_user = user_input.strip() or "Veja a imagem que enviei."
        imagens_bytes = [img_chat.getvalue()] if img_chat else []

        # Guarda no histórico — incluindo bytes para exibição
        entry = {"role": "user", "content": msg_user}
        if imagens_bytes:
            entry["img_bytes"] = imagens_bytes
        hist.append(entry)

        with st.spinner("Assistente digitando…"):
            resposta, cmd = _chamar_ia(hist[:-1], msg_user, imagens_bytes)

        feedback = _executar_comando(cmd) if cmd else None

        texto_final = resposta
        if feedback:
            texto_final = (texto_final + "\n\n" + feedback).strip() if texto_final else feedback

        hist.append({"role": "assistant", "content": texto_final})
        st.rerun()


def iniciar_conversa(mensagem: str):
    """
    Adiciona uma mensagem do assistente ao histórico.
    Útil para alertas automáticos do app (ex: campo obrigatório faltando).
    """
    if "ms_chat_hist" not in st.session_state:
        st.session_state["ms_chat_hist"] = []
    st.session_state["ms_chat_hist"].append({"role": "assistant", "content": mensagem})
