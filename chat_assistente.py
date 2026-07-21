"""
chat_assistente.py
Painel flutuante de chat com IA -- lateral direita, 280px.

ARQUITETURA:
- CSS + estrutura HTML: st.markdown (css funciona; scripts sao ignorados)
- JavaScript: components.html() cria iframe real onde scripts executam
- window.parent = pagina principal do Streamlit (same-origin)
- Listeners sao adicionados via P.document.addEventListener -- nao dependem
  de onclick no HTML (que o Streamlit remove no sanitize)
"""
import os
import streamlit as st
import streamlit.components.v1 as components


SYSTEM_PROMPT = """Voce e o Assistente do MS Studio, aplicativo interno da MartinSousa para gestao de produtos em marketplaces.

Voce ajuda colaboradores a:
- Preencher corretamente cada campo do formulario de viabilidade
- Entender os calculos de UC (Unit Coverage), comissoes e fretes
- Gerar sugestoes de titulo para anuncios
- Interpretar os resultados (VIAVEL / RESSALVAS / INVIAVEL)
- Tirar duvidas sobre regras de ML, Shopee e Shein

Regras do negocio que voce conhece:
- UC minimo aprovado: 0.8/1 (abaixo disso = INVIAVEL)
- UC 0.7 = cenario de risco; UC 1.0 = equilibrio ideal
- Mercado Livre: comissao por categoria (varia de 8% a 16%), frete calculado por peso cubado (altura x largura x profundidade / 6000), usa sempre modalidade Premium
- Shopee: comissao entre 15% e 20% por faixa de preco + R$4 adicional em produtos ate R$79,99; frete gratis (vendedor nao paga)
- Shein: comissao 18% flat sobre o preco; frete por peso real (tabela por faixas de kg)
- LPV = custo fixo medio por venda (calculado mensalmente na aba Financeiro)
- NF = aliquota do Simples Nacional (calculada automaticamente)
- Custo operacional padrao inclui embalagem, logistica, ADS e cross docking
- Peso e dimensoes devem ser do produto JA EMBALADO

Se o colaborador nao souber o que colocar em algum campo, explique o campo com um exemplo pratico.
Seja objetivo, use linguagem informal mas profissional. Responda em portugues."""


def renderizar_chat():
    """Injeta o painel de chat flutuante lateral direito no app."""
    api_key = ""
    try:
        api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:
        pass
    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    system_escaped = (SYSTEM_PROMPT
                      .replace("\\", "\\\\")
                      .replace('"', '\\"')
                      .replace("\n", "\\n"))

    # ── CSS + HTML (style tags funcionam; scripts sao removidos pelo Streamlit) ─
    st.markdown("""
<style>
#ms-chat-btn {
  position: fixed !important; bottom: 20px !important; left: 20px !important;
  width: 46px !important; height: 46px !important;
  background: var(--ms-chat-bg, #666666) !important;
  border: 1.5px solid var(--ms-borda, #888888) !important;
  border-radius: 50% !important; cursor: pointer !important;
  font-size: 18px !important; display: flex !important;
  align-items: center !important; justify-content: center !important;
  z-index: 999999 !important; box-shadow: 0 3px 14px rgba(0,0,0,0.4) !important;
  color: var(--ms-texto, #e0e0e0) !important;
  transition: opacity 0.15s !important; line-height: 1 !important; padding: 0 !important;
}
#ms-chat-btn:hover { opacity: 0.8 !important; }

#ms-chat-painel {
  position: fixed !important; top: 0 !important; left: 0 !important;
  width: 280px !important; height: 100vh !important;
  background: var(--ms-chat-bg, #666666) !important;
  border-right: 1px solid var(--ms-borda, #888888) !important;
  display: flex !important; flex-direction: column !important;
  z-index: 999998 !important;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
  transition: transform 0.22s ease !important;
  box-shadow: 4px 0 20px rgba(0,0,0,0.25) !important;
  transform: translateX(-280px) !important;
}
#ms-chat-painel.aberto { transform: translateX(0) !important; }

#ms-chat-header {
  padding: 13px 14px 12px !important;
  background: var(--ms-chat-header, #515151) !important;
  border-bottom: 1px solid var(--ms-divisor, #888888) !important;
  display: flex !important; align-items: center !important;
  justify-content: space-between !important; flex-shrink: 0 !important;
  min-height: 56px !important; box-sizing: border-box !important;
}
#ms-chat-titulo {
  margin: 0 !important; font-size: 13px !important; font-weight: 600 !important;
  color: var(--ms-texto, #e0e0e0) !important;
}
#ms-chat-subtitulo {
  font-size: 10px !important; color: var(--ms-texto-sec, #b8b8b8) !important;
  margin-top: 2px !important;
}
#ms-chat-fechar {
  background: none !important; border: none !important;
  color: var(--ms-texto-sec, #b8b8b8) !important; cursor: pointer !important;
  font-size: 18px !important; padding: 4px 7px !important; line-height: 1 !important;
  border-radius: 4px !important; flex-shrink: 0 !important;
  display: flex !important; align-items: center !important; justify-content: center !important;
}
#ms-chat-fechar:hover {
  color: var(--ms-texto, #e0e0e0) !important;
  background: var(--ms-hover, #777777) !important;
}

#ms-chat-msgs {
  flex: 1 !important; overflow-y: auto !important;
  padding: 14px 12px !important; display: flex !important;
  flex-direction: column !important; gap: 10px !important; box-sizing: border-box !important;
}
#ms-chat-msgs::-webkit-scrollbar { width: 3px !important; }
#ms-chat-msgs::-webkit-scrollbar-track { background: transparent !important; }
#ms-chat-msgs::-webkit-scrollbar-thumb {
  background: var(--ms-borda, #888) !important; border-radius: 2px !important;
}

.ms-msg-wrapper { display: flex !important; flex-direction: column !important; }
.ms-msg-wrapper.user { align-items: flex-end !important; }
.ms-msg-wrapper.ia   { align-items: flex-start !important; }
.ms-msg-label {
  font-size: 10px !important; color: var(--ms-texto-sec, #b8b8b8) !important;
  margin-bottom: 3px !important; font-weight: 500 !important;
}
.ms-msg {
  padding: 9px 12px !important; border-radius: 10px !important;
  font-size: 12.5px !important; line-height: 1.55 !important;
  white-space: pre-wrap !important; word-break: break-word !important; max-width: 93% !important;
}
.ms-msg.user {
  background: var(--ms-msg-user, #515151) !important;
  color: var(--ms-texto, #e0e0e0) !important; border-bottom-right-radius: 3px !important;
}
.ms-msg.ia {
  background: var(--ms-msg-ia, #5a5a5a) !important;
  color: var(--ms-texto, #e0e0e0) !important;
  border: 1px solid var(--ms-msg-ia-bd, #888888) !important;
  border-bottom-left-radius: 3px !important;
}
.ms-typing {
  color: var(--ms-texto-sec, #b8b8b8) !important; font-size: 11.5px !important;
  font-style: italic !important; align-self: flex-start !important; padding: 4px 0 !important;
}

#ms-chat-rodape {
  padding: 10px 12px !important;
  background: var(--ms-chat-footer, #5a5a5a) !important;
  border-top: 1px solid var(--ms-divisor, #888888) !important;
  flex-shrink: 0 !important; box-sizing: border-box !important;
}
#ms-chat-area {
  width: 100% !important; background: var(--ms-chat-input, #666666) !important;
  border: 1px solid var(--ms-borda, #888888) !important; border-radius: 7px !important;
  color: var(--ms-texto, #e0e0e0) !important; font-size: 12.5px !important;
  padding: 9px 11px !important; resize: none !important; outline: none !important;
  font-family: inherit !important; line-height: 1.45 !important;
  box-sizing: border-box !important; transition: border-color 0.15s !important;
}
#ms-chat-area::placeholder { color: var(--ms-texto-sec, #aaaaaa) !important; }
#ms-chat-area:focus { border-color: var(--ms-texto, #b8b8b8) !important; }
#ms-chat-rodape-acoes {
  display: flex !important; align-items: center !important;
  justify-content: space-between !important; margin-top: 7px !important;
}
.ms-hint { font-size: 10px !important; color: var(--ms-texto-sec, #b8b8b8) !important; }
#ms-chat-enviar {
  background: var(--ms-chat-header, #515151) !important;
  border: 1px solid var(--ms-borda, #888888) !important; border-radius: 6px !important;
  color: var(--ms-texto, #e0e0e0) !important; font-size: 12px !important;
  font-weight: 600 !important; padding: 5px 13px !important;
  cursor: pointer !important; transition: background 0.15s !important;
}
#ms-chat-enviar:hover { background: var(--ms-hover, #626262) !important; }
#ms-chat-enviar:disabled { opacity: 0.45 !important; cursor: default !important; }
</style>

<div id="ms-chat-widget">
  <button id="ms-chat-btn" title="Assistente MS">&#x1F4AC;</button>
  <div id="ms-chat-painel">
    <div id="ms-chat-header">
      <div>
        <div id="ms-chat-titulo">Assistente MS</div>
        <div id="ms-chat-subtitulo">Pergunte sobre qualquer campo</div>
      </div>
      <button id="ms-chat-fechar" title="Fechar">&#x2715;</button>
    </div>
    <div id="ms-chat-msgs"></div>
    <div id="ms-chat-rodape">
      <textarea id="ms-chat-area" rows="3" placeholder="Digite sua duvida..."></textarea>
      <div id="ms-chat-rodape-acoes">
        <span class="ms-hint">Enter envia &middot; Shift+Enter nova linha</span>
        <button id="ms-chat-enviar">Enviar</button>
      </div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

    # ── JS via components.html(): executa de verdade (iframe real) ────────────
    # IMPORTANTE: listeners adicionados em P.document sobrevivem a rerenders
    # do Streamlit (que substituem o conteudo mas nao o document em si).
    js = f"""<script>
(function() {{
  var P = window.parent;
  var API_KEY = "{api_key}";
  var SYSTEM  = "{system_escaped}";
  var SS_HIST = "ms_chat_hist";
  var SS_EST  = "ms_chat_estado";

  var mensagens = [];
  try {{
    var _s = P.sessionStorage.getItem(SS_HIST);
    if (_s) mensagens = JSON.parse(_s);
  }} catch(e) {{}}

  function g(id) {{ return P.document.getElementById(id); }}

  function addMsgRaw(tipo, texto) {{
    var msgs = g('ms-chat-msgs');
    if (!msgs) return;
    var w = P.document.createElement('div');
    w.className = 'ms-msg-wrapper ' + tipo;
    var label = tipo === 'user' ? 'Voce' : 'Assistente';
    var safe = texto.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    w.innerHTML = '<div class="ms-msg-label">' + label + '</div>' +
                  '<div class="ms-msg ' + tipo + '">' + safe + '</div>';
    msgs.appendChild(w);
  }}

  function rolar() {{
    setTimeout(function() {{
      var msgs = g('ms-chat-msgs');
      if (msgs) msgs.scrollTop = msgs.scrollHeight;
    }}, 40);
  }}

  function popularMsgs() {{
    var msgs = g('ms-chat-msgs');
    if (!msgs) {{ setTimeout(popularMsgs, 100); return; }}
    msgs.innerHTML = '';
    if (mensagens.length === 0) {{
      addMsgRaw('ia', 'Ola! Estou aqui para ajudar com qualquer campo ou duvida sobre viabilidade, ML, Shopee e Shein. O que precisa?');
    }} else {{
      mensagens.forEach(function(m) {{ addMsgRaw(m.role === 'user' ? 'user' : 'ia', m.content); }});
    }}
    rolar();
  }}

  function restaurarEstado() {{
    var p = g('ms-chat-painel'), b = g('ms-chat-btn');
    if (P.sessionStorage.getItem(SS_EST) === 'aberto') {{
      if (p) p.classList.add('aberto');
      if (b) b.innerHTML = '&#x2715;';
    }} else {{
      if (p) p.classList.remove('aberto');
      if (b) b.innerHTML = '&#x1F4AC;';
    }}
  }}

  // Streamlit rerender: DOM foi substituido, repopula e restaura
  if (P._msChat) {{
    popularMsgs();
    restaurarEstado();
    return;
  }}

  // ── Primeira execucao: inicializacao completa ─────────────────────────────

  function addMsg(tipo, texto) {{ addMsgRaw(tipo, texto); rolar(); }}

  function salvar() {{
    try {{ P.sessionStorage.setItem(SS_HIST, JSON.stringify(mensagens)); }} catch(e) {{}}
  }}

  function abrirChat() {{
    var p = g('ms-chat-painel'), b = g('ms-chat-btn');
    if (p) p.classList.add('aberto');
    if (b) b.innerHTML = '&#x2715;';
    P.sessionStorage.setItem(SS_EST, 'aberto');
    rolar();
  }}

  function fecharChat() {{
    var p = g('ms-chat-painel'), b = g('ms-chat-btn');
    if (p) p.classList.remove('aberto');
    if (b) b.innerHTML = '&#x1F4AC;';
    P.sessionStorage.setItem(SS_EST, 'fechado');
  }}

  function enviarMsg() {{
    var area   = g('ms-chat-area');
    var enviar = g('ms-chat-enviar');
    var msgs   = g('ms-chat-msgs');
    if (!area || !msgs) return;
    var texto = area.value.trim();
    if (!texto) return;
    area.value = '';

    addMsg('user', texto);
    mensagens.push({{ role: 'user', content: texto }});
    salvar();

    var typing = P.document.createElement('div');
    typing.className = 'ms-typing';
    typing.id = 'ms-typing';
    typing.textContent = 'Assistente digitando...';
    msgs.appendChild(typing);
    rolar();
    if (enviar) enviar.disabled = true;

    fetch('https://api.anthropic.com/v1/messages', {{
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
    }})
    .then(function(resp) {{
      if (!resp.ok) return resp.json().then(function(e) {{
        throw new Error((e.error && e.error.message) || 'Erro ' + resp.status);
      }});
      return resp.json();
    }})
    .then(function(data) {{
      var r = (data.content && data.content[0] && data.content[0].text) || '(sem resposta)';
      mensagens.push({{ role: 'assistant', content: r }});
      salvar();
      var t = g('ms-typing'); if (t) t.remove();
      addMsg('ia', r);
    }})
    .catch(function(err) {{
      var t = g('ms-typing'); if (t) t.remove();
      addMsg('ia', 'Erro: ' + (err.message || String(err)));
    }})
    .finally(function() {{
      var e = g('ms-chat-enviar'); if (e) e.disabled = false;
      rolar();
    }});
  }}

  // API publica (usada por msChatAbrir e pelo toggle do tema)
  P._msChat = {{
    toggle: function() {{
      var p = g('ms-chat-painel');
      if (p && p.classList.contains('aberto')) fecharChat(); else abrirChat();
    }},
    fechar: function() {{ fecharChat(); }},
    enviar: function() {{ enviarMsg(); }}
  }};

  // Para o Python abrir o chat com mensagem automatica
  P.msChatAbrir = function(msgInicial) {{
    abrirChat();
    if (msgInicial) {{
      addMsg('ia', msgInicial);
      mensagens.push({{ role: 'assistant', content: msgInicial }});
      salvar();
    }}
  }};

  // ── Listeners no document da pagina principal ─────────────────────────────
  // Adicionados UMA VEZ e sobrevivem a todos os rerenders do Streamlit.
  // NAO dependem de onclick no HTML (que o Streamlit remove).
  if (!P._msChatListeners) {{
    P._msChatListeners = true;

    P.document.addEventListener('click', function(e) {{
      var el = e.target;
      // sobe ate 3 niveis para pegar o botao mesmo se clicar no emoji interno
      for (var i = 0; i < 3; i++) {{
        if (!el) break;
        var id = el.id;
        if (id === 'ms-chat-btn')    {{ P._msChat.toggle(); return; }}
        if (id === 'ms-chat-fechar') {{ P._msChat.fechar(); return; }}
        if (id === 'ms-chat-enviar') {{ P._msChat.enviar(); return; }}
        el = el.parentElement;
      }}
    }}, true);  // capture = intercepta antes do React

    P.document.addEventListener('keydown', function(e) {{
      var el = P.document.activeElement;
      if (el && el.id === 'ms-chat-area' && e.key === 'Enter' && !e.shiftKey) {{
        e.preventDefault();
        P._msChat.enviar();
      }}
    }}, true);
  }}

  // Init: popula historico e restaura estado
  function init() {{
    var msgs = g('ms-chat-msgs');
    if (!msgs) {{ setTimeout(init, 150); return; }}
    popularMsgs();
    restaurarEstado();
  }}
  setTimeout(init, 200);
}})();
</script>"""
    components.html(js, height=0)


def iniciar_conversa(mensagem: str):
    """
    Abre o chat automaticamente com uma mensagem do assistente.
    Chamar apos renderizar_chat() quando o app detectar campo faltando.
    """
    msg_escaped = (mensagem
                   .replace("\\", "\\\\")
                   .replace('"', '\\"')
                   .replace("\n", "\\n"))
    components.html(
        f'<script>setTimeout(function(){{ if(window.parent.msChatAbrir) window.parent.msChatAbrir("{msg_escaped}"); }}, 500);</script>',
        height=0
    )
