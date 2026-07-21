"""
chat_assistente.py
Painel flutuante de chat com IA lateral direita.
Chama a API da Anthropic direto do browser (JS fetch).
A chave ANTHROPIC_API_KEY deve estar em st.secrets ou como variável de ambiente.
"""
import os, json
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

Se o colaborador não souber o que colocar em algum campo, explique o campo com um exemplo prático.
Seja objetivo, use linguagem informal mas profissional. Responda em português."""


def renderizar_chat():
    """Injeta o painel de chat flutuante lateral direito no app."""
    # Tenta ler a chave de ambiente ou secrets
    api_key = ""
    try:
        api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:
        pass
    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    # Escapa o system prompt pra JS (remove backticks e aspas problemáticas)
    system_escaped = (SYSTEM_PROMPT
                      .replace("\\", "\\\\")
                      .replace("`", "'")
                      .replace("${", "\\${")
                      .replace("\n", "\\n"))

    html = f"""
<style>
/* ── BOTÃO FLUTUANTE ───────────────────────────────────────── */
#ms-chat-btn {{
  position: fixed !important;
  bottom: 20px !important;
  right: 20px !important;
  width: 46px !important;
  height: 46px !important;
  background: #515151 !important;
  border: 1.5px solid #666666 !important;
  border-radius: 50% !important;
  cursor: pointer !important;
  font-size: 18px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  z-index: 999999 !important;
  box-shadow: 0 3px 12px rgba(0,0,0,0.45) !important;
  color: #e0e0e0 !important;
  transition: background 0.15s !important;
  line-height: 1 !important;
}}
#ms-chat-btn:hover {{ background: #626262 !important; }}

/* ── PAINEL LATERAL ────────────────────────────────────────── */
#ms-chat-painel {{
  position: fixed !important;
  top: 0 !important;
  right: 0 !important;
  width: 280px !important;
  height: 100vh !important;
  background: #424242 !important;
  border-left: 1px solid #606060 !important;
  display: flex !important;
  flex-direction: column !important;
  z-index: 999998 !important;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
  transition: transform 0.22s ease !important;
  box-shadow: -4px 0 20px rgba(0,0,0,0.3) !important;
}}
#ms-chat-painel.fechado {{
  transform: translateX(280px) !important;
}}

/* ── CABEÇALHO ─────────────────────────────────────────────── */
#ms-chat-header {{
  padding: 13px 14px 12px !important;
  background: #515151 !important;
  border-bottom: 1px solid #606060 !important;
  display: flex !important;
  align-items: center !important;
  justify-content: space-between !important;
  flex-shrink: 0 !important;
  min-height: 56px !important;
  box-sizing: border-box !important;
}}
#ms-chat-titulo {{ margin: 0 !important; font-size: 13px !important; font-weight: 600 !important; color: #e0e0e0 !important; }}
#ms-chat-subtitulo {{ font-size: 10px !important; color: #b8b8b8 !important; margin-top: 2px !important; }}
#ms-chat-fechar {{
  background: none !important;
  border: none !important;
  color: #b8b8b8 !important;
  cursor: pointer !important;
  font-size: 16px !important;
  padding: 4px 6px !important;
  line-height: 1 !important;
  border-radius: 4px !important;
  flex-shrink: 0 !important;
}}
#ms-chat-fechar:hover {{ color: #e0e0e0 !important; background: #606060 !important; }}

/* ── ÁREA DE MENSAGENS ─────────────────────────────────────── */
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
#ms-chat-msgs::-webkit-scrollbar-thumb {{ background: #666 !important; border-radius: 2px !important; }}

.ms-msg-wrapper {{ display: flex !important; flex-direction: column !important; max-width: 100% !important; }}
.ms-msg-wrapper.user {{ align-items: flex-end !important; }}
.ms-msg-wrapper.ia   {{ align-items: flex-start !important; }}

.ms-msg-label {{
  font-size: 10px !important;
  color: #999 !important;
  margin-bottom: 3px !important;
  font-weight: 500 !important;
  letter-spacing: 0.03em !important;
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
  background: #3a3a3a !important;
  color: #e0e0e0 !important;
  border: 1px solid #555 !important;
  border-bottom-left-radius: 3px !important;
}}
.ms-typing {{
  color: #888 !important;
  font-size: 11.5px !important;
  font-style: italic !important;
  padding: 2px 0 !important;
  align-self: flex-start !important;
}}

/* ── RODAPÉ / INPUT ────────────────────────────────────────── */
#ms-chat-rodape {{
  padding: 10px 12px !important;
  background: #424242 !important;
  border-top: 1px solid #555 !important;
  flex-shrink: 0 !important;
  box-sizing: border-box !important;
}}
#ms-chat-area {{
  width: 100% !important;
  background: #515151 !important;
  border: 1px solid #666 !important;
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
#ms-chat-area::placeholder {{ color: #888 !important; }}
#ms-chat-area:focus {{ border-color: #8c8c8c !important; }}
#ms-chat-rodape-acoes {{
  display: flex !important;
  align-items: center !important;
  justify-content: space-between !important;
  margin-top: 7px !important;
}}
.ms-hint {{ font-size: 10px !important; color: #777 !important; }}
#ms-chat-enviar {{
  background: #515151 !important;
  border: 1px solid #666 !important;
  border-radius: 6px !important;
  color: #e0e0e0 !important;
  font-size: 12px !important;
  font-weight: 600 !important;
  padding: 5px 12px !important;
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
      <button id="ms-chat-fechar">✕</button>
    </div>
    <div id="ms-chat-msgs" id="ms-msgs"></div>
    <div id="ms-chat-rodape">
      <textarea id="ms-chat-area" rows="3" placeholder="Digite sua dúvida..."></textarea>
      <div id="ms-chat-rodape-acoes">
        <span class="ms-hint">Enter envia · Shift+Enter quebra linha</span>
        <button id="ms-chat-enviar">Enviar</button>
      </div>
    </div>
  </div>
</div>

<script>
(function() {{
  const API_KEY = "{api_key}";
  const SYSTEM  = "{system_escaped}";
  const SS_KEY  = "ms_chat_historico";

  // Recupera histórico do sessionStorage (sobrevive a rerenders do Streamlit)
  let mensagens = [];
  try {{
    const salvo = sessionStorage.getItem(SS_KEY);
    if (salvo) mensagens = JSON.parse(salvo);
  }} catch(e) {{}}

  const painel  = document.getElementById('ms-chat-painel');
  const btn     = document.getElementById('ms-chat-btn');
  const msgs    = document.getElementById('ms-chat-msgs');
  const area    = document.getElementById('ms-chat-area');
  const enviar  = document.getElementById('ms-chat-enviar');

  // ── ESTADO INICIAL ──────────────────────────────────────────────
  // Recupera estado aberto/fechado do sessionStorage
  const estaFechado = sessionStorage.getItem('ms_chat_estado') === 'fechado';
  if (estaFechado) {{
    painel.classList.add('fechado');
    btn.textContent = '💬';
  }} else {{
    btn.textContent = '✕';
  }}

  // Renderiza histórico salvo
  if (mensagens.length === 0) {{
    adicionarMsgRender('ia', 'Olá! Estou aqui para ajudar com qualquer campo ou dúvida sobre viabilidade, ML, Shopee e Shein. O que precisa?');
  }} else {{
    mensagens.forEach(m => adicionarMsgRender(m.role === 'user' ? 'user' : 'ia', m.content));
  }}
  rolarParaBaixo();

  // ── TOGGLE ABRIR/FECHAR ─────────────────────────────────────────
  function togglePainel(forcarFechar) {{
    const fechar = forcarFechar !== undefined ? forcarFechar : !painel.classList.contains('fechado');
    if (fechar) {{
      painel.classList.add('fechado');
      btn.textContent = '💬';
      sessionStorage.setItem('ms_chat_estado', 'fechado');
    }} else {{
      painel.classList.remove('fechado');
      btn.textContent = '✕';
      sessionStorage.setItem('ms_chat_estado', 'aberto');
      rolarParaBaixo();
    }}
  }}

  btn.addEventListener('click', () => togglePainel());
  document.getElementById('ms-chat-fechar').addEventListener('click', () => togglePainel(true));

  // ── ENVIAR MENSAGEM ─────────────────────────────────────────────
  area.addEventListener('keydown', (e) => {{
    if (e.key === 'Enter' && !e.shiftKey) {{
      e.preventDefault();
      enviar.click();
    }}
  }});

  enviar.addEventListener('click', async () => {{
    const texto = area.value.trim();
    if (!texto) return;

    area.value = '';
    adicionarMsgRender('user', texto);
    mensagens.push({{ role: 'user', content: texto }});
    salvarHistorico();

    // Indicador "digitando"
    const typing = document.createElement('div');
    typing.className = 'ms-typing';
    typing.id = 'ms-typing';
    typing.textContent = 'Assistente digitando...';
    msgs.appendChild(typing);
    rolarParaBaixo();
    enviar.disabled = true;

    try {{
      if (!API_KEY) throw new Error('Configure ANTHROPIC_API_KEY no Railway (variável de ambiente).');

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
      salvarHistorico();

      document.getElementById('ms-typing')?.remove();
      adicionarMsgRender('ia', resposta);

    }} catch(e) {{
      document.getElementById('ms-typing')?.remove();
      adicionarMsgRender('ia', '⚠️ ' + e.message);
    }}

    enviar.disabled = false;
    rolarParaBaixo();
  }});

  // ── FUNÇÕES AUXILIARES ──────────────────────────────────────────
  function adicionarMsgRender(tipo, texto) {{
    const w = document.createElement('div');
    w.className = 'ms-msg-wrapper ' + tipo;
    const label = tipo === 'user' ? 'Você' : 'Assistente';
    // Escapa HTML basico
    const safe = texto.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    w.innerHTML =
      '<div class="ms-msg-label">' + label + '</div>' +
      '<div class="ms-msg ' + tipo + '">' + safe + '</div>';
    msgs.appendChild(w);
  }}

  function rolarParaBaixo() {{
    setTimeout(() => {{ msgs.scrollTop = msgs.scrollHeight; }}, 30);
  }}

  function salvarHistorico() {{
    try {{ sessionStorage.setItem(SS_KEY, JSON.stringify(mensagens)); }} catch(e) {{}}
  }}
}})();
</script>
"""
    st.markdown(html, unsafe_allow_html=True)