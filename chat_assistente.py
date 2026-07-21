"""
chat_assistente.py
Painel flutuante de chat com IA — lateral direita, 280px.
- Começa FECHADO; botão 💬 abre/fecha
- Quando aberto, o conteúdo principal encolhe (classe chat-aberto no body)
- Chama API Anthropic direto do browser (JS fetch)
- window.msChatAbrir(msg) permite que o app Python abra o chat com uma msg automática
"""
import os
import streamlit as st


SYSTEM_PROMPT = """Você é o Assistente do MS Studio, aplicativo interno da MartinSousa para gestão de produtos em marketplaces.

Você ajuda colaboradores a:
- Preencher corretamente cada campo do formulário de viabilidade
- Entender os cálculos de UC (Unit Coverage), comissões e fretes
- Gerar sugestões de título para anúncios
- Interpretar os resultados (VIÁVEL / RESSALVAS / INVIÁVEL)
- Tirar dúvidas sobre regras de ML, Shopee e Shein

Regras do negócio que você conhece:
- UC mínimo aprovado: 0.8/1 (abaixo disso = INVIÁVEL)
- UC 0.7 = cenário de risco; UC 1.0 = equilíbrio ideal
- Mercado Livre: comissão por categoria (varia de 8% a 16%), frete calculado por peso cubado (altura × largura × profundidade ÷ 6000), usa sempre modalidade Premium
- Shopee: comissão entre 15% e 20% por faixa de preço + R$4 adicional em produtos até R$79,99; frete grátis (vendedor não paga)
- Shein: comissão 18% flat sobre o preço; frete por peso real (tabela por faixas de kg)
- LPV = custo fixo médio por venda (calculado mensalmente na aba Financeiro)
- NF = alíquota do Simples Nacional (calculada automaticamente)
- Custo operacional padrão inclui embalagem, logística, ADS e cross docking
- Peso e dimensões devem ser do produto JA EMBALADO

Se o colaborador não souber o que colocar em algum campo, explique com um exemplo prático.
Seja objetivo, use linguagem informal mas profissional. Responda em português."""


def renderizar_chat():
    """Injeta o painel de chat flutuante no app. Chamar uma vez por página."""
    api_key = ""
    try:
        api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:
        pass
    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    system_escaped = (SYSTEM_PROMPT
                      .replace("\\", "\\\\")
                      .replace("`", "'")
                      .replace("${", "\\${")
                      .replace("\n", "\\n")
                      .replace('"', '\\"'))

    html = f"""
<style>
/* ── BOTÃO FLUTUANTE ──────────────────────────────────────── */
#ms-chat-btn {{
  position: fixed !important;
  bottom: 20px !important;
  right: 20px !important;
  width: 46px !important;
  height: 46px !important;
  background: #666666 !important;
  border: 1.5px solid #888888 !important;
  border-radius: 50% !important;
  cursor: pointer !important;
  font-size: 18px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  z-index: 999999 !important;
  box-shadow: 0 3px 14px rgba(0,0,0,0.5) !important;
  color: #e0e0e0 !important;
  transition: background 0.15s !important;
  line-height: 1 !important;
  padding: 0 !important;
}}
#ms-chat-btn:hover {{ background: #777777 !important; }}

/* ── PAINEL LATERAL ───────────────────────────────────────── */
#ms-chat-painel {{
  position: fixed !important;
  top: 0 !important;
  right: 0 !important;
  width: 280px !important;
  height: 100vh !important;
  background: #666666 !important;
  border-left: 1px solid #888888 !important;
  display: flex !important;
  flex-direction: column !important;
  z-index: 999998 !important;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
  transition: transform 0.22s ease !important;
  box-shadow: -4px 0 20px rgba(0,0,0,0.35) !important;
  transform: translateX(280px) !important;
}}
#ms-chat-painel.aberto {{
  transform: translateX(0) !important;
}}

/* ── CABEÇALHO ────────────────────────────────────────────── */
#ms-chat-header {{
  padding: 13px 14px 12px !important;
  background: #515151 !important;
  border-bottom: 1px solid #888888 !important;
  display: flex !important;
  align-items: center !important;
  justify-content: space-between !important;
  flex-shrink: 0 !important;
  min-height: 56px !important;
  box-sizing: border-box !important;
}}
#ms-chat-titulo {{
  margin: 0 !important;
  font-size: 13px !important;
  font-weight: 600 !important;
  color: #e0e0e0 !important;
}}
#ms-chat-subtitulo {{
  font-size: 10px !important;
  color: #b8b8b8 !important;
  margin-top: 2px !important;
}}
#ms-chat-fechar {{
  background: none !important;
  border: none !important;
  color: #b8b8b8 !important;
  cursor: pointer !important;
  font-size: 18px !important;
  padding: 4px 7px !important;
  line-height: 1 !important;
  border-radius: 4px !important;
  flex-shrink: 0 !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
}}
#ms-chat-fechar:hover {{ color: #e0e0e0 !important; background: #777777 !important; }}

/* ── MENSAGENS ────────────────────────────────────────────── */
#ms-chat-msgs {{
  flex: 1 !important;
  overflow-y: auto !important;
  padding: 14px 12px !important;
  display: flex !important;
  flex-direction: column !important;
  gap: 10px !important;
  box-sizing: border-box !important;
}}
#ms-chat-msgs::-webkit-scrollbar {{ width: 3px !important; }}
#ms-chat-msgs::-webkit-scrollbar-track {{ background: transparent !important; }}
#ms-chat-msgs::-webkit-scrollbar-thumb {{ background: #888 !important; border-radius: 2px !important; }}

.ms-msg-wrapper {{ display: flex !important; flex-direction: column !important; }}
.ms-msg-wrapper.user {{ align-items: flex-end !important; }}
.ms-msg-wrapper.ia   {{ align-items: flex-start !important; }}
.ms-msg-label {{
  font-size: 10px !important;
  color: #b8b8b8 !important;
  margin-bottom: 3px !important;
  font-weight: 500 !important;
}}
.ms-msg {{
  padding: 9px 12px !important;
  border-radius: 10px !important;
  font-size: 12.5px !important;
  line-height: 1.55 !important;
  white-space: pre-wrap !important;
  word-break: break-word !important;
  max-width: 93% !important;
}}
.ms-msg.user {{
  background: #515151 !important;
  color: #e0e0e0 !important;
  border-bottom-right-radius: 3px !important;
}}
.ms-msg.ia {{
  background: #5a5a5a !important;
  color: #e0e0e0 !important;
  border: 1px solid #888888 !important;
  border-bottom-left-radius: 3px !important;
}}
.ms-typing {{
  color: #b8b8b8 !important;
  font-size: 11.5px !important;
  font-style: italic !important;
  align-self: flex-start !important;
  padding: 4px 0 !important;
}}

/* ── RODAPÉ ───────────────────────────────────────────────── */
#ms-chat-rodape {{
  padding: 10px 12px !important;
  background: #5a5a5a !important;
  border-top: 1px solid #888888 !important;
  flex-shrink: 0 !important;
  box-sizing: border-box !important;
}}
#ms-chat-area {{
  width: 100% !important;
  background: #666666 !important;
  border: 1px solid #888888 !important;
  border-radius: 7px !important;
  color: #e0e0e0 !important;
  font-size: 12.5px !important;
  padding: 9px 11px !important;
  resize: none !important;
  outline: none !important;
  font-family: inherit !important;
  line-height: 1.45 !important;
  box-sizing: border-box !important;
  transition: border-color 0.15s !important;
}}
#ms-chat-area::placeholder {{ color: #aaaaaa !important; }}
#ms-chat-area:focus {{ border-color: #b8b8b8 !important; }}
#ms-chat-rodape-acoes {{
  display: flex !important;
  align-items: center !important;
  justify-content: space-between !important;
  margin-top: 7px !important;
}}
.ms-hint {{ font-size: 10px !important; color: #b8b8b8 !important; }}
#ms-chat-enviar {{
  background: #515151 !important;
  border: 1px solid #888888 !important;
  border-radius: 6px !important;
  color: #e0e0e0 !important;
  font-size: 12px !important;
  font-weight: 600 !important;
  padding: 5px 13px !important;
  cursor: pointer !important;
  transition: background 0.15s !important;
}}
#ms-chat-enviar:hover {{ background: #626262 !important; }}
#ms-chat-enviar:disabled {{ opacity: 0.45 !important; cursor: default !important; }}
</style>

<div id="ms-chat-widget">
  <button id="ms-chat-btn" title="Assistente MS">💬</button>
  <div id="ms-chat-painel">
    <div id="ms-chat-header">
      <div>
        <div id="ms-chat-titulo">Assistente MS</div>
        <div id="ms-chat-subtitulo">Pergunte sobre qualquer campo</div>
      </div>
      <button id="ms-chat-fechar" title="Fechar">✕</button>
    </div>
    <div id="ms-chat-msgs"></div>
    <div id="ms-chat-rodape">
      <textarea id="ms-chat-area" rows="3" placeholder="Digite sua dúvida..."></textarea>
      <div id="ms-chat-rodape-acoes">
        <span class="ms-hint">Enter envia · Shift+Enter nova linha</span>
        <button id="ms-chat-enviar">Enviar</button>
      </div>
    </div>
  </div>
</div>

<script>
(function() {{
  const API_KEY = "{api_key}";
  const SYSTEM  = "{system_escaped}";
  const SS_HIST = "ms_chat_hist";
  const SS_EST  = "ms_chat_estado";

  let mensagens = [];
  let iniciado  = false;
  try {{ const s = sessionStorage.getItem(SS_HIST); if (s) mensagens = JSON.parse(s); }} catch(e) {{}}

  // ── Helpers de estado ─────────────────────────────────────────────────────
  function g(id) {{ return document.getElementById(id); }}

  function abrirChat() {{
    const p = g('ms-chat-painel'), b = g('ms-chat-btn');
    if (p) p.classList.add('aberto');
    if (b) b.textContent = '✕';
    document.body.classList.add('chat-aberto');
    sessionStorage.setItem(SS_EST, 'aberto');
    rolar();
  }}

  function fecharChat() {{
    const p = g('ms-chat-painel'), b = g('ms-chat-btn');
    if (p) p.classList.remove('aberto');
    if (b) b.textContent = '💬';
    document.body.classList.remove('chat-aberto');
    sessionStorage.setItem(SS_EST, 'fechado');
  }}

  function addMsgRaw(tipo, texto) {{
    const msgs = g('ms-chat-msgs');
    if (!msgs) return;
    const w = document.createElement('div');
    w.className = 'ms-msg-wrapper ' + tipo;
    const label = tipo === 'user' ? 'Você' : 'Assistente';
    const safe = texto.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    w.innerHTML = '<div class="ms-msg-label">' + label + '</div>' +
                  '<div class="ms-msg ' + tipo + '">' + safe + '</div>';
    msgs.appendChild(w);
  }}

  function addMsg(tipo, texto) {{ addMsgRaw(tipo, texto); rolar(); }}

  function rolar() {{
    setTimeout(function() {{
      const msgs = g('ms-chat-msgs');
      if (msgs) msgs.scrollTop = msgs.scrollHeight;
    }}, 40);
  }}

  function salvar() {{
    try {{ sessionStorage.setItem(SS_HIST, JSON.stringify(mensagens)); }} catch(e) {{}}
  }}

  async function enviarMsg() {{
    const area   = g('ms-chat-area');
    const enviar = g('ms-chat-enviar');
    const msgs   = g('ms-chat-msgs');
    if (!area || !enviar || !msgs) return;

    const texto = area.value.trim();
    if (!texto) return;
    area.value = '';

    addMsg('user', texto);
    mensagens.push({{ role: 'user', content: texto }});
    salvar();

    const typing = document.createElement('div');
    typing.className = 'ms-typing';
    typing.id = 'ms-typing';
    typing.textContent = 'Assistente digitando...';
    msgs.appendChild(typing);
    rolar();
    enviar.disabled = true;

    try {{
      if (!API_KEY) throw new Error('ANTHROPIC_API_KEY não configurada no Railway.');
      const resp = await fetch('https://api.anthropic.com/v1/messages', {{
        method: 'POST',
        headers: {{
          'Content-Type': 'application/json',
          'x-api-key': API_KEY,
          'anthropic-version': '2023-06-01',
          'anthropic-dangerous-direct-browser-access': 'true'
        }},
        body: JSON.stringify({{
          model: 'claude-haiku-4-5',
          max_tokens: 800,
          system: SYSTEM,
          messages: mensagens
        }})
      }});
      if (!resp.ok) {{
        const err = await resp.json().catch(() => ({{}}));
        throw new Error(err.error?.message || 'Erro ' + resp.status);
      }}
      const data = await resp.json();
      const resposta = data.content[0]?.text || '(sem resposta)';
      mensagens.push({{ role: 'assistant', content: resposta }});
      salvar();
      g('ms-typing')?.remove();
      addMsg('ia', resposta);
    }} catch(err) {{
      g('ms-typing')?.remove();
      addMsg('ia', '⚠️ ' + err.message);
    }}

    if (enviar) enviar.disabled = false;
    rolar();
  }}

  // ── Delegação no document — funciona mesmo após re-render do Streamlit ───
  document.addEventListener('click', function(e) {{
    const t = e.target;
    if (t.id === 'ms-chat-btn' || (t.closest && t.closest('#ms-chat-btn'))) {{
      const p = g('ms-chat-painel');
      if (p && p.classList.contains('aberto')) fecharChat();
      else abrirChat();
    }}
    if (t.id === 'ms-chat-fechar' || (t.closest && t.closest('#ms-chat-fechar'))) {{
      fecharChat();
    }}
    if (t.id === 'ms-chat-enviar' || (t.closest && t.closest('#ms-chat-enviar'))) {{
      enviarMsg();
    }}
  }}, true);

  document.addEventListener('keydown', function(e) {{
    if (e.key === 'Enter' && !e.shiftKey && e.target.id === 'ms-chat-area') {{
      e.preventDefault();
      enviarMsg();
    }}
  }}, true);

  // ── Inicialização do histórico (roda uma vez) ─────────────────────────────
  function init() {{
    if (iniciado) return;
    if (!g('ms-chat-msgs')) {{ setTimeout(init, 150); return; }}
    iniciado = true;

    if (mensagens.length === 0) {{
      addMsgRaw('ia', 'Olá! Estou aqui para ajudar com qualquer campo ou dúvida sobre viabilidade, ML, Shopee e Shein. O que precisa?');
    }} else {{
      mensagens.forEach(function(m) {{ addMsgRaw(m.role === 'user' ? 'user' : 'ia', m.content); }});
    }}
    rolar();

    if (sessionStorage.getItem(SS_EST) === 'aberto') abrirChat();
  }}
  setTimeout(init, 300);

  // ── API pública para o app Python abrir o chat ────────────────────────────
  window.msChatAbrir = function(msgInicial) {{
    abrirChat();
    if (msgInicial) {{
      addMsg('ia', msgInicial);
      mensagens.push({{ role: 'assistant', content: msgInicial }});
      salvar();
    }}
  }};
}})();
</script>
"""
    st.markdown(html, unsafe_allow_html=True)


def iniciar_conversa(mensagem: str):
    """
    Abre o chat automaticamente com uma mensagem do assistente.
    Chamar após renderizar_chat() quando o app detectar campo faltando ou quiser guiar o usuário.
    Exemplo:
        chat_assistente.iniciar_conversa("Percebi que você preencheu o preço da Shein mas não informou o peso. Qual é o peso do produto embalado?")
    """
    msg_escaped = (mensagem
                   .replace("\\", "\\\\")
                   .replace('"', '\\"')
                   .replace("\n", "\\n"))
    st.markdown(
        f'<script>setTimeout(function(){{ if(window.msChatAbrir) window.msChatAbrir("{msg_escaped}"); }}, 400);</script>',
        unsafe_allow_html=True
    )
