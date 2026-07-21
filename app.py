import streamlit as st
import streamlit.components.v1 as components
from datetime import date
from params_oficiais import (
    LPV_OFICIAL, NF_OFICIAL,
    ML_FAIXAS_PRECO, ML_FRETE_TABELA, ML_COMISSAO_POR_CATEGORIA,
    SHOPEE_FAIXAS, SHOPEE_FRETE_LIQUIDO,
    SHEIN_COMISSAO, SHEIN_FRETE_TABELA,
)
import financeiro
import atividades
import auth
import admin
import triagem
import palavras_chave
import tit_ml as titulo
import descricao
import imagem
import chat_assistente

st.set_page_config(page_title="MS Studio", layout="wide")

st.markdown("""
<style>
/* ══ TEMA ESCURO — padrão / após 18h ═══════════════════════════════════════ */
body, body.tema-escuro {
  --ms-fundo:         #3c3c3c;
  --ms-sidebar:       #515151;
  --ms-chat-bg:       #666666;
  --ms-chat-header:   #515151;
  --ms-chat-footer:   #5a5a5a;
  --ms-chat-input:    #666666;
  --ms-divisor:       #666666;
  --ms-input:         #666666;
  --ms-borda:         #888888;
  --ms-texto:         #e0e0e0;
  --ms-texto-sec:     #b8b8b8;
  --ms-hover:         #5c5c5c;
  --ms-metric-bg:     #666666;
  --ms-metric-bd:     #888888;
  --ms-msg-user:      #515151;
  --ms-msg-ia:        #5a5a5a;
  --ms-msg-ia-bd:     #888888;
}
/* ══ TEMA CLARO — diurno / antes das 18h ═══════════════════════════════════ */
body.tema-claro {
  --ms-fundo:         #E0E0E0;
  --ms-sidebar:       #EEEEEE;
  --ms-chat-bg:       #EEEEEE;
  --ms-chat-header:   #E8E8E8;
  --ms-chat-footer:   #E8E8E8;
  --ms-chat-input:    #E0E0E0;
  --ms-divisor:       #BDBDBD;
  --ms-input:         #EEEEEE;
  --ms-borda:         #9E9E9E;
  --ms-texto:         #212121;
  --ms-texto-sec:     #424242;
  --ms-hover:         #D0D0D0;
  --ms-metric-bg:     #EEEEEE;
  --ms-metric-bd:     #BDBDBD;
  --ms-msg-user:      #D0D0D0;
  --ms-msg-ia:        #F5F5F5;
  --ms-msg-ia-bd:     #BDBDBD;
}

/* ── REMOVE BARRA DO TOPO ───────────────────────────────────────────────── */
[data-testid="stHeader"]  { background-color: var(--ms-fundo) !important; border-bottom: none !important; }
[data-testid="stToolbar"] { background-color: var(--ms-fundo) !important; }
#stDecoration             { display: none !important; }

/* ── FUNDO GERAL ────────────────────────────────────────────────────────── */
.stApp { background-color: var(--ms-fundo) !important; color: var(--ms-texto) !important; }
.main, [data-testid="stMain"] { background-color: var(--ms-fundo) !important; }
.main .block-container,
[data-testid="stMainBlockContainer"] {
    background-color: var(--ms-fundo) !important;
    color: var(--ms-texto) !important;
    transition: padding-right 0.22s ease !important;
}
body.chat-aberto .main .block-container,
body.chat-aberto [data-testid="stMainBlockContainer"] { padding-right: 296px !important; }
h1, h2, h3, h4, h5, h6 { color: var(--ms-texto) !important; }
p, span, label, div     { color: var(--ms-texto) !important; }

/* ── SIDEBAR ESQUERDO ───────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background-color: var(--ms-sidebar) !important;
    border-right: 1px solid var(--ms-divisor) !important;
}
[data-testid="stSidebar"] * { color: var(--ms-texto) !important; }

/* ── INPUTS ─────────────────────────────────────────────────────────────── */
.stTextInput input, .stNumberInput input {
    background-color: var(--ms-input) !important;
    border: 1px solid var(--ms-borda) !important;
    color: var(--ms-texto) !important;
    border-radius: 5px !important;
    font-size: 14px !important;
    padding: 6px 10px !important;
    height: 36px !important;
    min-height: unset !important;
}
.stTextInput input::placeholder,
.stNumberInput input::placeholder { color: var(--ms-texto-sec) !important; font-size: 13px !important; }
.stTextInput input:focus,
.stNumberInput input:focus { border-color: var(--ms-texto) !important; box-shadow: none !important; }

/* Labels */
.stTextInput label, .stNumberInput label, .stSelectbox label,
[data-testid="stWidgetLabel"] p {
    color: var(--ms-texto-sec) !important;
    font-size: 13px !important;
    margin-bottom: 3px !important;
}

/* Select */
.stSelectbox > div > div {
    background-color: var(--ms-input) !important;
    border: 1px solid var(--ms-borda) !important;
    color: var(--ms-texto) !important;
    font-size: 14px !important;
    min-height: 36px !important;
}
.stSelectbox [data-baseweb="select"] > div {
    padding-top: 4px !important; padding-bottom: 4px !important; min-height: 36px !important;
}
/* Botões +/- */
.stNumberInput [data-testid="stNumberInputStepUp"],
.stNumberInput [data-testid="stNumberInputStepDown"] {
    height: 36px !important; width: 30px !important; font-size: 15px !important;
    background-color: var(--ms-input) !important;
    color: var(--ms-texto) !important;
    border-color: var(--ms-borda) !important;
}
/* Espaçamento */
.stTextInput, .stNumberInput, .stSelectbox { margin-bottom: 4px !important; }
.element-container { margin-bottom: 6px !important; }

/* ── TABELAS ────────────────────────────────────────────────────────────── */
table { color: var(--ms-texto) !important; border-collapse: collapse !important;
        width: 100% !important; border: none !important; background: transparent !important; }
th    { background-color: transparent !important; color: var(--ms-texto-sec) !important;
        font-size: 11px !important; font-weight: 600 !important; letter-spacing: 0.07em !important;
        text-transform: uppercase !important; border: none !important;
        border-bottom: 1px solid var(--ms-divisor) !important; padding: 8px 12px !important; text-align: left !important; }
td    { background-color: transparent !important; border: none !important;
        border-bottom: 1px solid var(--ms-divisor) !important; padding: 8px 12px !important; color: var(--ms-texto) !important; }
tr:last-child td { border-bottom: none !important; }
tr:hover td      { background-color: var(--ms-hover) !important; }

/* ── MÉTRICAS ───────────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background-color: var(--ms-metric-bg) !important;
    border-radius: 8px !important; padding: 12px 16px !important;
    border: 1px solid var(--ms-metric-bd) !important;
}
[data-testid="stMetricLabel"] p { color: var(--ms-texto-sec) !important; font-size: 12px !important; }
[data-testid="stMetricValue"]   { color: var(--ms-texto) !important; }

/* ── TABS ───────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background-color: transparent !important;
    border-bottom: 1px solid var(--ms-divisor) !important; gap: 4px !important;
}
.stTabs [data-baseweb="tab"] {
    color: var(--ms-texto-sec) !important; background: transparent !important; font-size: 14px !important;
}
.stTabs [aria-selected="true"] {
    color: var(--ms-texto) !important; border-bottom-color: var(--ms-texto) !important;
}

/* ── BOTÕES ─────────────────────────────────────────────────────────────── */
.stButton > button[kind="primary"] {
    background-color: var(--ms-metric-bg) !important; color: var(--ms-texto) !important;
    border: 1px solid var(--ms-metric-bd) !important; border-radius: 6px !important;
    font-weight: 600 !important; letter-spacing: 0.4px !important; transition: all 0.15s ease !important;
}
.stButton > button[kind="primary"]:hover {
    background-color: var(--ms-hover) !important; border-color: var(--ms-texto-sec) !important;
}
.stButton > button:not([kind="primary"]) {
    background-color: transparent !important; color: var(--ms-texto-sec) !important;
    border: 1px solid var(--ms-metric-bd) !important; border-radius: 6px !important;
}
.stButton > button:not([kind="primary"]):hover {
    color: var(--ms-texto) !important; border-color: var(--ms-texto-sec) !important;
}

/* ── CAPTION / ALERTAS / DIVISORES ─────────────────────────────────────── */
.stCaption, [data-testid="stCaptionContainer"] p { color: var(--ms-texto-sec) !important; }
[data-testid="stAlert"] { background-color: var(--ms-metric-bg) !important; border-color: var(--ms-metric-bd) !important; }
hr { border-color: var(--ms-divisor) !important; margin: 16px 0 !important; }

/* ── BOTÃO TOGGLE DE TEMA ───────────────────────────────────────────────── */
#ms-tema-toggle {
  position: fixed !important; bottom: 74px !important; right: 20px !important;
  z-index: 999997 !important;
  background: var(--ms-sidebar) !important;
  border: 1.5px solid var(--ms-borda) !important;
  border-radius: 50% !important; width: 46px !important; height: 46px !important;
  font-size: 18px !important; cursor: pointer !important;
  display: flex !important; align-items: center !important; justify-content: center !important;
  box-shadow: 0 3px 12px rgba(0,0,0,0.35) !important;
  transition: opacity 0.15s !important; line-height: 1 !important; padding: 0 !important;
}
#ms-tema-toggle:hover { opacity: 0.75 !important; }
</style>
""", unsafe_allow_html=True)

# ── TEMA JS — via components.html p/ garantir execução real do script ──────────
components.html("""
<script>
(function() {
  var P = window.parent;

  function temaAuto() { return new Date().getHours() >= 18 ? 'tema-escuro' : 'tema-claro'; }

  function aplicarTema(tema, salvar) {
    P.document.body.classList.remove('tema-claro','tema-escuro');
    P.document.body.classList.add(tema);
    var btn = P.document.getElementById('ms-tema-toggle');
    if (btn) {
      btn.textContent = tema === 'tema-escuro' ? '☀️' : '🌙';
      btn.title = tema === 'tema-escuro' ? 'Mudar para tema claro' : 'Mudar para tema escuro';
    }
    if (salvar) {
      P.sessionStorage.setItem('ms_tema', tema);
      P.sessionStorage.setItem('ms_tema_dia', new Date().toDateString());
    }
  }

  if (P._msTemaIniciado) {
    // Streamlit rerender — re-aplica o tema salvo (botão já existe no body)
    var t = P.sessionStorage.getItem('ms_tema');
    var d = P.sessionStorage.getItem('ms_tema_dia');
    aplicarTema((t && d === new Date().toDateString()) ? t : temaAuto(), false);
    return;
  }
  P._msTemaIniciado = true;

  // Aplica tema inicial
  var temaSalvo = P.sessionStorage.getItem('ms_tema');
  var diaSalvo  = P.sessionStorage.getItem('ms_tema_dia');
  if (temaSalvo && diaSalvo === new Date().toDateString()) {
    aplicarTema(temaSalvo, false);
  } else {
    P.sessionStorage.removeItem('ms_tema');
    P.sessionStorage.removeItem('ms_tema_dia');
    aplicarTema(temaAuto(), false);
  }

  // Injeta botão toggle (uma única vez, direto no body — sobrevive rerenders)
  if (!P.document.getElementById('ms-tema-toggle')) {
    var btn = P.document.createElement('button');
    btn.id = 'ms-tema-toggle';
    btn.onclick = function() {
      var claro = P.document.body.classList.contains('tema-claro');
      aplicarTema(claro ? 'tema-escuro' : 'tema-claro', true);
    };
    P.document.body.appendChild(btn);
    // Ícone inicial
    aplicarTema(P.document.body.classList.contains('tema-claro') ? 'tema-claro' : 'tema-escuro', false);
  }

  // Auto-switch ao cruzar 18h (só se não houver override manual)
  setInterval(function() {
    if (!P.sessionStorage.getItem('ms_tema')) aplicarTema(temaAuto(), false);
  }, 60000);
})();
</script>
""", height=0)

usuario_logado = auth.verificar_login()

# UC minimo pra aprovar produto -- definido pelo Léo em 14/07/2026,
# provisorio ate ele analisar as UCs reais da operacao.
UC_MINIMO = 0.8

# ── CÁLCULO MERCADO LIVRE ──────────────────────────────────────────────────────

def calcular_peso_taxado(peso_kg, d1, d2, d3):
    """Peso taxado = maior entre peso fisico e peso cubado (altura x largura
    x profundidade / 6000), conforme politica oficial do Mercado Livre.
    IMPORTANTE: peso e dimensoes devem ser do produto JA EMBALADO."""
    peso_cubado = (d1 * d2 * d3) / 6000
    return max(peso_kg, peso_cubado)

def calcular_frete_ml(preco, peso_kg):
    """Tabela oficial do Mercado Livre pos-reforma de marco/2026
    (MercadoLider / reputacao verde / sem reputacao)."""
    if preco < 19:
        valor_tabela = ML_FRETE_TABELA[-1][1][0]
        for peso_lim, vals in ML_FRETE_TABELA:
            if peso_kg <= peso_lim:
                valor_tabela = vals[0]
                break
        return min(valor_tabela, preco * 0.5)
    idx = len(ML_FAIXAS_PRECO) - 1
    for i, lim in enumerate(ML_FAIXAS_PRECO):
        if preco <= lim:
            idx = i
            break
    for peso_lim, vals in ML_FRETE_TABELA:
        if peso_kg <= peso_lim:
            return vals[idx]
    return ML_FRETE_TABELA[-1][1][idx]

def calcular_comissao_ml(preco, categoria, modalidade="Premium"):
    taxas = ML_COMISSAO_POR_CATEGORIA.get(categoria, ML_COMISSAO_POR_CATEGORIA['Outros'])
    return preco * taxas[1 if modalidade == "Premium" else 0]

def calcular_resultado(preco, custo, peso_kg, categoria, modalidade, nf_pct, custo_operacional, lpv):
    comissao     = calcular_comissao_ml(preco, categoria, modalidade)
    frete        = calcular_frete_ml(preco, peso_kg)
    nf           = preco * nf_pct
    lucro_bruto  = preco - (comissao + frete)
    lucro_liq    = preco - (custo + comissao + frete + nf + custo_operacional)
    margem       = (lucro_liq / preco * 100) if preco > 0 else 0
    uc           = round(lucro_liq / lpv, 2) if lpv else None
    return {'preco': preco, 'custo': custo, 'comissao': comissao, 'frete': frete,
            'nf': nf, 'custo_operacional': custo_operacional, 'lpv': lpv,
            'lucro_bruto': lucro_bruto, 'lucro_liquido': lucro_liq,
            'margem': margem, 'uc': uc}

# ── CÁLCULO SHOPEE ─────────────────────────────────────────────────────────────

def calcular_comissao_shopee(preco):
    """Retorna (comissao_valor, adicional_fixo) conforme tabela SHOPEE_FAIXAS.
    Formato: (preco_min, preco_max, comissao_pct, adicional_fixo, frete_liquido)."""
    for pmin, pmax, pct, adicional, _ in SHOPEE_FAIXAS:
        if pmin <= preco <= pmax:
            return preco * pct, adicional
    # fallback: ultima faixa
    _, _, pct, adicional, _ = SHOPEE_FAIXAS[-1]
    return preco * pct, adicional

def calcular_resultado_shopee(preco, custo, nf_pct, custo_operacional, lpv):
    comissao_pct, adicional = calcular_comissao_shopee(preco)
    comissao_total = comissao_pct + adicional
    frete     = SHOPEE_FRETE_LIQUIDO  # R$0,00 — Frete Gratis obrigatorio, vendedor nao paga
    nf        = preco * nf_pct
    lucro_liq = preco - (custo + comissao_total + frete + nf + custo_operacional)
    margem    = (lucro_liq / preco * 100) if preco > 0 else 0
    uc        = round(lucro_liq / lpv, 2) if lpv else None
    return {
        'preco': preco, 'custo': custo, 'comissao': comissao_total, 'frete': frete,
        'nf': nf, 'custo_operacional': custo_operacional, 'lpv': lpv,
        'lucro_bruto': preco - (comissao_total + frete),
        'lucro_liquido': lucro_liq, 'margem': margem, 'uc': uc,
    }

# ── CÁLCULO SHEIN ──────────────────────────────────────────────────────────────

def calcular_frete_shein(peso_kg):
    """Frete da Shein por peso (tabela oficial do vendedor).
    Formato: (peso_maximo_kg, valor_frete_reais)."""
    for peso_lim, valor in SHEIN_FRETE_TABELA:
        if peso_kg <= peso_lim:
            return valor
    return SHEIN_FRETE_TABELA[-1][1]

def calcular_resultado_shein(preco, custo, peso_kg, nf_pct, custo_operacional, lpv):
    comissao  = preco * SHEIN_COMISSAO  # 18% flat
    frete     = calcular_frete_shein(peso_kg)
    nf        = preco * nf_pct
    lucro_liq = preco - (custo + comissao + frete + nf + custo_operacional)
    margem    = (lucro_liq / preco * 100) if preco > 0 else 0
    uc        = round(lucro_liq / lpv, 2) if lpv else None
    return {
        'preco': preco, 'custo': custo, 'comissao': comissao, 'frete': frete,
        'nf': nf, 'custo_operacional': custo_operacional, 'lpv': lpv,
        'lucro_bruto': preco - (comissao + frete),
        'lucro_liquido': lucro_liq, 'margem': margem, 'uc': uc,
    }

# ── VEREDICTO (100% Python, sem chamada de IA -- mais rapido e sem custo) ──────

def montar_tabela_vertical(r):
    """Tabela vertical (Item | Valor) na ordem pedida pelo usuario."""
    uc_str = f"{r['uc']}/1" if r['uc'] is not None else "sem lucro"
    linhas = [
        "| Item | Valor |",
        "|---|---|",
        f"| Valor do anúncio | R${r['preco']:.2f} |",
        f"| Taxa da plataforma (comissão) | R${r['comissao']:.2f} |",
        f"| Frete | R${r['frete']:.2f} |",
        f"| NF | R${r['nf']:.2f} |",
        f"| Custos operacionais | R${r['custo_operacional']:.2f} |",
        f"| Custo do produto | R${r['custo']:.2f} |",
        f"| **Lucro** | **R${r['lucro_liquido']:.2f}** |",
        f"| Margem | {r['margem']:.1f}% |",
        f"| **UC** | **{uc_str}** |",
    ]
    return "\n".join(linhas)


def classificar_uc(uc):
    if uc is None or uc < UC_MINIMO:
        return "INVIAVEL"
    elif uc < 1.0:
        return "RESSALVAS"
    return "VIAVEL"


def montar_tabela_horizontal_completa(cenarios):
    """cenarios: lista de (nome, resultado_dict)"""
    campos = [
        ("Valor do anúncio", lambda r: f"R${r['preco']:.2f}"),
        ("Taxa da plataforma", lambda r: f"R${r['comissao']:.2f}"),
        ("Frete", lambda r: f"R${r['frete']:.2f}"),
        ("NF", lambda r: f"R${r['nf']:.2f}"),
        ("Custos operacionais", lambda r: f"R${r['custo_operacional']:.2f}"),
        ("Custo do produto", lambda r: f"R${r['custo']:.2f}"),
        ("**Lucro**", lambda r: f"**R${r['lucro_liquido']:.2f}**"),
        ("Margem", lambda r: f"{r['margem']:.1f}%"),
        ("**UC**", lambda r: f"**{r['uc']}/1**" if r['uc'] is not None else "**sem lucro**"),
    ]
    header = "| Item | " + " | ".join(nome for nome, _ in cenarios) + " |"
    sep = "|---" * (len(cenarios) + 1) + "|"
    linhas = [header, sep]
    for label, fn in campos:
        linhas.append(f"| {label} | " + " | ".join(fn(r) for _, r in cenarios) + " |")
    return "\n".join(linhas)

# ── RESOLVER E PROMOÇÃO GENÉRICOS (funciona pra ML, Shopee e Shein) ───────────

def resolver_preco_para_uc_fn(uc_alvo, calc_fn, lpv, preco_max=2000.0):
    """Bissecao generica: acha preco que resulta exatamente em uc_alvo
    dado um calc_fn(preco) -> resultado_dict."""
    if not lpv:
        return None
    lo, hi = 0.01, float(preco_max)
    for _ in range(80):
        mid = (lo + hi) / 2
        r = calc_fn(mid)
        uc = r['uc'] if r['uc'] is not None else -999
        if uc < uc_alvo:
            lo = mid
        else:
            hi = mid
    return round(hi, 2)

def analisar_promocao_fn(preco_mercado, uc_mercado, calc_fn, lpv):
    """Analise de promocao generica usando calc_fn(preco) -> resultado_dict."""
    if uc_mercado is None or uc_mercado < 1.0:
        return None

    preco_10pct = round(preco_mercado * 0.9, 2)
    r_10pct = calc_fn(preco_10pct)

    preco_uc1 = resolver_preco_para_uc_fn(1.0, calc_fn, lpv, preco_max=preco_mercado * 2)
    desconto_teorico_uc1 = round(100 * (preco_mercado - preco_uc1) / preco_mercado, 1) if preco_uc1 else 0

    if r_10pct['uc'] is not None and r_10pct['uc'] >= 1.0:
        desconto_recomendado = 10.0
        r_recomendado = r_10pct
        nota_extra = (
            f"Isso ainda deixa a UC em {r_10pct['uc']}/1. Se quiser ir além, o limite pra não cair "
            f"abaixo de 1/1 é **{desconto_teorico_uc1}%** de desconto (informativo, não é a sugestão)."
        ) if desconto_teorico_uc1 > 10 else ""
        texto = "✅ Dá pra promover em até **10%** de desconto (o teto padrão da empresa)."
    else:
        desconto_recomendado = desconto_teorico_uc1
        r_recomendado = calc_fn(preco_uc1) if preco_uc1 else None
        nota_extra = ""
        texto = (
            f"⚠️ 10% de desconto derrubaria a UC abaixo de 1/1. O desconto máximo recomendado pra manter "
            f"UC ≥ 1/1 é **{desconto_recomendado}%**."
        )

    if r_recomendado is None:
        return None

    tabela = montar_tabela_horizontal_completa([
        ("Preço de mercado", calc_fn(preco_mercado)),
        (f"Promoção ({desconto_recomendado}% off)", r_recomendado),
    ])

    return {"texto": texto, "nota_extra": nota_extra, "tabela": tabela}

def gerar_analise_fn(preco_mercado, custo, nome, nf_pct, custo_op, lpv, calc_fn,
                     preco_max_busca=None, alerta_cubagem=""):
    """Motor de analise generico. Recebe calc_fn(preco)->resultado e produz
    o mesmo dicionario de saida que gerar_analise() (ML-especifico)."""
    r_base = calc_fn(preco_mercado)
    tag = classificar_uc(r_base['uc'])
    preco_max = preco_max_busca or max(custo * 20, 2000)

    RESUMOS = {
        "VIAVEL":    f"Esse anúncio sobra R${r_base['lucro_liquido']:.2f} de lucro por venda (margem de {r_base['margem']:.1f}%), cobrindo a meta de lucro com folga.",
        "RESSALVAS": f"Esse anúncio sobra R${r_base['lucro_liquido']:.2f} de lucro por venda (margem de {r_base['margem']:.1f}%) — ajuda a pagar as contas, mas não cobre a meta sozinho.",
        "INVIAVEL":  f"Esse anúncio {'dá prejuízo' if r_base['lucro_liquido'] < 0 else 'sobra pouco lucro'} (R${r_base['lucro_liquido']:.2f} por venda) — fica abaixo do mínimo aceitável pra empresa.",
    }

    preco_uc07 = resolver_preco_para_uc_fn(0.7, calc_fn, lpv, preco_max)
    preco_uc10 = resolver_preco_para_uc_fn(1.0, calc_fn, lpv, preco_max)
    r_uc07 = calc_fn(preco_uc07) if preco_uc07 else None
    r_uc10 = calc_fn(preco_uc10) if preco_uc10 else None

    cenarios = [("Risco (UC 0,7/1)", r_uc07), ("Preço de mercado", r_base), ("Equilíbrio (UC 1,0/1)", r_uc10)]
    cenarios = [(n, r) for n, r in cenarios if r is not None]
    tabela_cenarios = montar_tabela_horizontal_completa(cenarios)

    promo = analisar_promocao_fn(preco_mercado, r_base['uc'], calc_fn, lpv)
    if promo is None:
        if tag == "INVIAVEL":
            texto_promo = "⚠️ Não tem margem pra promoção nesse preço — o produto já está abaixo do UC mínimo. Considere revisar custo ou anunciar mais caro (veja o cenário de Equilíbrio acima)."
        else:
            texto_promo = f"⚠️ Margem apertada (UC entre {UC_MINIMO}/1 e 1/1) — não recomendamos promoção nesse preço, só se aproximar do valor de Equilíbrio (UC 1,0/1) mostrado acima."
        tabela_promo = ""
        nota_extra_promo = ""
    else:
        texto_promo = promo["texto"]
        tabela_promo = promo["tabela"]
        nota_extra_promo = promo["nota_extra"]

    return {
        "tag": tag,
        "resumo": RESUMOS[tag],
        "tabela_cenarios": tabela_cenarios,
        "texto_promo": texto_promo,
        "tabela_promo": tabela_promo,
        "nota_extra_promo": nota_extra_promo,
        "alerta_cubagem": alerta_cubagem,
        "preco_sugerido": preco_mercado,
    }

# ── FUNÇÕES ML LEGADAS (mantidas intactas) ────────────────────────────────────

def resolver_preco_para_uc(uc_alvo, custo, peso_kg, categoria, modalidade, nf_pct, custo_op, lpv, preco_max=None):
    """Acha por bissecao o preco de anuncio que resulta exatamente no UC alvo."""
    if not lpv:
        return None
    preco_max = preco_max or max(custo * 20, 2000)
    lo, hi = 0.01, preco_max
    for _ in range(80):
        mid = (lo + hi) / 2
        r = calcular_resultado(mid, custo, peso_kg, categoria, modalidade, nf_pct, custo_op, lpv)
        uc = r['uc'] if r['uc'] is not None else -999
        if uc < uc_alvo:
            lo = mid
        else:
            hi = mid
    return round(hi, 2)


def analisar_promocao(preco_mercado, uc_mercado, custo, peso_taxado, categoria, modalidade, nf_pct, custo_operacional, lpv):
    """Regra definida pelo usuario (14/07/2026):
    - Teto de promocao recomendado: 10% de desconto.
    - Mas nunca deixar o UC final cair abaixo de 1/1."""
    if uc_mercado is None or uc_mercado < 1.0:
        return None

    preco_10pct = round(preco_mercado * 0.9, 2)
    r_10pct = calcular_resultado(preco_10pct, custo, peso_taxado, categoria, modalidade, nf_pct, custo_operacional, lpv)

    preco_uc1 = resolver_preco_para_uc(1.0, custo, peso_taxado, categoria, modalidade, nf_pct, custo_operacional, lpv)
    desconto_teorico_uc1 = round(100 * (preco_mercado - preco_uc1) / preco_mercado, 1) if preco_uc1 else 0

    if r_10pct['uc'] is not None and r_10pct['uc'] >= 1.0:
        desconto_recomendado = 10.0
        preco_recomendado = preco_10pct
        r_recomendado = r_10pct
        nota_extra = (f"Isso ainda deixa a UC em {r_10pct['uc']}/1. Se quiser ir além, o limite pra não cair "
                      f"abaixo de 1/1 é **{desconto_teorico_uc1}%** de desconto (informativo, não é a sugestão).") \
                      if desconto_teorico_uc1 > 10 else ""
        texto = f"✅ Dá pra promover em até **10%** de desconto (o teto padrão da empresa)."
    else:
        desconto_recomendado = desconto_teorico_uc1
        preco_recomendado = preco_uc1
        r_recomendado = calcular_resultado(preco_uc1, custo, peso_taxado, categoria, modalidade, nf_pct, custo_operacional, lpv)
        nota_extra = ""
        texto = (f"⚠️ 10% de desconto derrubaria a UC abaixo de 1/1. O desconto máximo recomendado pra manter "
                 f"UC ≥ 1/1 é **{desconto_recomendado}%**.")

    tabela = montar_tabela_horizontal_completa([
        ("Preço de mercado", calcular_resultado(preco_mercado, custo, peso_taxado, categoria, modalidade, nf_pct, custo_operacional, lpv)),
        (f"Promoção ({desconto_recomendado}% off)", r_recomendado),
    ])

    return {"texto": texto, "nota_extra": nota_extra, "tabela": tabela}


def gerar_analise(preco_mercado, custo, peso_taxado, categoria, modalidade,
                   nome, dims_ref, qtd_ref, nf_pct, custo_operacional, lpv):
    r_base = calcular_resultado(preco_mercado, custo, peso_taxado, categoria, modalidade, nf_pct, custo_operacional, lpv)
    tag = classificar_uc(r_base['uc'])

    RESUMOS = {
        "VIAVEL": f"Esse anúncio sobra R${r_base['lucro_liquido']:.2f} de lucro por venda (margem de {r_base['margem']:.1f}%), cobrindo a meta de lucro com folga.",
        "RESSALVAS": f"Esse anúncio sobra R${r_base['lucro_liquido']:.2f} de lucro por venda (margem de {r_base['margem']:.1f}%) — ajuda a pagar as contas, mas não cobre a meta sozinho.",
        "INVIAVEL": f"Esse anúncio {'dá prejuízo' if r_base['lucro_liquido'] < 0 else 'sobra pouco lucro'} (R${r_base['lucro_liquido']:.2f} por venda) — fica abaixo do mínimo aceitável pra empresa.",
    }
    resumo = RESUMOS[tag]

    preco_uc07 = resolver_preco_para_uc(0.7, custo, peso_taxado, categoria, modalidade, nf_pct, custo_operacional, lpv)
    preco_uc10 = resolver_preco_para_uc(1.0, custo, peso_taxado, categoria, modalidade, nf_pct, custo_operacional, lpv)
    r_uc07 = calcular_resultado(preco_uc07, custo, peso_taxado, categoria, modalidade, nf_pct, custo_operacional, lpv) if preco_uc07 else None
    r_uc10 = calcular_resultado(preco_uc10, custo, peso_taxado, categoria, modalidade, nf_pct, custo_operacional, lpv) if preco_uc10 else None

    cenarios = [("Risco (UC 0,7/1)", r_uc07), ("Preço de mercado", r_base), ("Equilíbrio (UC 1,0/1)", r_uc10)]
    cenarios = [(n, r) for n, r in cenarios if r is not None]
    tabela_cenarios = montar_tabela_horizontal_completa(cenarios)

    promo = analisar_promocao(preco_mercado, r_base['uc'], custo, peso_taxado, categoria, modalidade, nf_pct, custo_operacional, lpv)
    if promo is None:
        if tag == "INVIAVEL":
            texto_promo = "⚠️ Não tem margem pra promoção nesse preço — o produto já está abaixo do UC mínimo. Considere revisar custo ou anunciar mais caro (veja o cenário de Equilíbrio acima)."
        else:
            texto_promo = f"⚠️ Margem apertada (UC entre {UC_MINIMO}/1 e 1/1) — não recomendamos promoção nesse preço, só se aproximar do valor de Equilíbrio (UC 1,0/1) mostrado acima."
        tabela_promo = ""
        nota_extra_promo = ""
    else:
        texto_promo = promo["texto"]
        tabela_promo = promo["tabela"]
        nota_extra_promo = promo["nota_extra"]

    alerta_cubagem = ""
    if any(d > 0 for d in dims_ref):
        peso_cubado = (dims_ref[0] * dims_ref[1] * dims_ref[2]) / 6000
        if peso_cubado > peso_taxado - 0.001 and peso_cubado > 0:
            alerta_cubagem = f"⚠️ **Atenção:** o frete foi calculado pelo volume da embalagem ({dims_ref[0]:.0f}x{dims_ref[1]:.0f}x{dims_ref[2]:.0f}cm), não pelo peso — o Mercado Livre pode reconferir essa medida depois e mudar o custo."

    return {
        "tag": tag,
        "resumo": resumo,
        "tabela_cenarios": tabela_cenarios,
        "texto_promo": texto_promo,
        "tabela_promo": tabela_promo,
        "nota_extra_promo": nota_extra_promo,
        "alerta_cubagem": alerta_cubagem,
        "preco_sugerido": preco_mercado,
    }

# ── RENDERIZAÇÃO DE RESULTADO (compartilhada pelas 3 plataformas) ──────────────

def _mostrar_resultado(resultado, nome_produto):
    SELOS = {
        "VIAVEL":    ("✅", "VIÁVEL",            "#0d2b1a", "#34d399"),
        "RESSALVAS": ("⚠️", "VIÁVEL COM ATENÇÃO", "#2b1f06", "#fbbf24"),
        "INVIAVEL":  ("🚫", "INVIÁVEL",           "#2b0d0d", "#f87171"),
    }
    emoji, texto_selo, cor_fundo, cor_borda = SELOS[resultado["tag"]]

    st.markdown(f"""
    <div style="background-color:{cor_fundo}; border-left: 4px solid {cor_borda};
                border-radius: 6px; padding: 12px 16px; margin-bottom: 12px;">
        <span style="font-size: 14px; font-weight: 700; color: {cor_borda};
                     letter-spacing: 0.05em; text-transform: uppercase;">
            {emoji} {texto_selo}
        </span><br>
        <span style="color: #aaaaaa; font-size: 13px; margin-top: 2px; display:block;">
            {nome_produto} · R${resultado['preco_sugerido']:.2f}
        </span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown(resultado["resumo"])

    st.markdown("#### Cenários (risco / mercado / equilíbrio)")
    st.markdown(resultado["tabela_cenarios"])

    st.markdown("#### Viabilidade de promoção")
    st.markdown(resultado["texto_promo"])
    if resultado["tabela_promo"]:
        st.markdown(resultado["tabela_promo"])
    if resultado["nota_extra_promo"]:
        st.caption(resultado["nota_extra_promo"])

    if resultado.get("alerta_cubagem"):
        st.markdown("---")
        st.markdown(resultado["alerta_cubagem"])

# ── INTERFACE ──────────────────────────────────────────────────────────────────

st.title("MS Studio")

with st.sidebar:
    st.header("MS Studio")
    st.caption("v17.0")
    st.markdown("---")
    st.caption(f"Logado como **{usuario_logado}**")
    if st.button("Sair"):
        del st.session_state["usuario_logado"]
        st.rerun()
    st.markdown("---")
    modalidade = st.selectbox("Modalidade ML", ["Premium", "Classico"])
    st.markdown("---")
    st.caption("Chaves configuradas automaticamente")

_eh_admin = auth.is_admin(usuario_logado)
_nomes_abas = ["Análise de Viabilidade", "Triagem", "Palavras-chave", "Título",
               "Descrição", "Imagem", "Histórico"]
if _eh_admin:
    _nomes_abas.append("Administrativo")

_abas = st.tabs(_nomes_abas)
(aba_viabilidade, aba_triagem, aba_palavras, aba_titulo,
 aba_descricao, aba_imagem, aba_historico) = _abas[:7]

with aba_historico:
    atividades.pagina_historico()

if _eh_admin:
    with _abas[7]:
        _sub_admin, _sub_financeiro = st.tabs(["⚙️ Administrativo", "💰 Financeiro"])
        with _sub_admin:
            admin.pagina_admin(usuario_logado)
        with _sub_financeiro:
            financeiro.pagina_financeiro(usuario_logado)

with aba_triagem:
    triagem.pagina_triagem(usuario_logado)

with aba_palavras:
    palavras_chave.pagina_palavras_chave(usuario_logado)

with aba_titulo:
    titulo.pagina_titulo(usuario_logado)

with aba_imagem:
    imagem.pagina_imagem(usuario_logado)

with aba_descricao:
    descricao.pagina_descricao(usuario_logado)

with aba_viabilidade:
    # Busca LPV e aliquota calculados a partir dos dados financeiros reais.
    # Se ainda nao houver dado suficiente, cai pros valores fixos antigos
    # (params_oficiais.py) so como reserva, deixando isso claro na tela.
    lpv_dinamico, lpv_origem, aliquota_dinamica = None, None, None
    try:
        df_financeiro = financeiro.carregar_dados()
        lpv_dinamico, lpv_origem = financeiro.lpv_vigente(df_financeiro)
        aliquota_dinamica, _ = financeiro.aliquota_vigente(df_financeiro)
    except Exception:
        pass

    lpv_usado = lpv_dinamico if lpv_dinamico else LPV_OFICIAL
    lpv_origem_usada = lpv_origem if lpv_dinamico else "valor fixo de reserva (sem dados financeiros ainda)"
    nf_pct_usado = (aliquota_dinamica / 100) if aliquota_dinamica else NF_OFICIAL

    col_info1, col_info2, col_info3 = st.columns(3)
    col_info1.metric("LPV vigente", f"R${lpv_usado:.2f}")
    col_info2.metric("NF (alíquota)", f"{nf_pct_usado*100:.1f}%")
    col_info3.metric("UC mínimo p/ aprovar", f"{UC_MINIMO}/1")
    st.caption(f"LPV calculado com base em: {lpv_origem_usada}")
    st.markdown("---")

    # ── FORMULÁRIO ÚNICO ───────────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Dados do Produto")
        nome_produto      = st.text_input("Nome do produto")
        custo             = st.number_input("Preço de custo (R$)", min_value=0.0, value=None, step=0.50, format="%.2f", placeholder="0,00")
        qtd_ref           = st.number_input("Quantidade por unidade/kit", min_value=1, step=1, value=1)
        categoria         = st.selectbox("Categoria no ML", sorted(ML_COMISSAO_POR_CATEGORIA.keys()), key="viab_categoria")
        custo_operacional = st.number_input("Custo operacional (embalagem/logística/ADS/cross docking)",
                                             min_value=0.0, value=8.13, step=0.50, format="%.2f")

    with col2:
        st.subheader("Dimensões e Peso (produto EMBALADO)")
        st.caption("Peso e medidas do pacote pronto pra envio — usados no cálculo de frete do ML (cubagem) e da Shein (por peso).")
        col_peso, col_unit = st.columns([3, 1])
        peso_val  = col_peso.number_input("Peso embalado", min_value=0.0, value=None, step=1.0, format="%.0f", placeholder="ex: 700")
        peso_unit = col_unit.selectbox("", ["g", "kg"], label_visibility="hidden")
        peso_kg   = (peso_val / 1000 if peso_val else 0) if peso_unit == "g" else (peso_val or 0)
        st.caption("Medidas da embalagem — usadas no cálculo de peso cubado do ML")
        dim1 = st.number_input("Medida 1 (cm)", min_value=0.0, value=None, step=0.5, format="%.1f", placeholder="ex: 30")
        dim2 = st.number_input("Medida 2 (cm)", min_value=0.0, value=None, step=0.5, format="%.1f", placeholder="ex: 30")
        dim3 = st.number_input("Medida 3 (cm)", min_value=0.0, value=None, step=0.5, format="%.1f", placeholder="ex: 2")
        dims_ref = [dim1 or 0, dim2 or 0, dim3 or 0]

    # ── PREÇOS DE MERCADO POR PLATAFORMA ──────────────────────────────────────
    st.markdown("---")
    st.subheader("Preço de mercado por plataforma")
    st.caption("Preencha o preço pesquisado em cada plataforma. Deixe em branco as que não forem analisar.")

    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        preco_ml = st.number_input("🛒 Mercado Livre", min_value=0.0, value=None, step=0.50,
                                    format="%.2f", placeholder="0,00", key="preco_ml")
    with col_p2:
        preco_sp = st.number_input("🛍️ Shopee", min_value=0.0, value=None, step=0.50,
                                    format="%.2f", placeholder="0,00", key="preco_sp")
    with col_p3:
        preco_sh = st.number_input("👗 Shein", min_value=0.0, value=None, step=0.50,
                                    format="%.2f", placeholder="0,00", key="preco_sh")

    st.markdown("---")
    analisar = st.button("Analisar Viabilidade", type="primary", use_container_width=True)

    if analisar:
        erros = []
        if not nome_produto: erros.append("Nome do produto")
        if custo is None:    erros.append("Preço de custo")
        if not any([preco_ml, preco_sp, preco_sh]):
            erros.append("Pelo menos um preço de mercado (ML, Shopee ou Shein)")
        if preco_sh and peso_kg == 0:
            erros.append("Peso do produto (necessário para calcular o frete da Shein)")
        if erros:
            st.warning(f"Preencha: {', '.join(erros)}")
            # Abre o chat automaticamente com orientação sobre o que falta
            msg_chat = f"Atenção! Faltam informações para calcular a viabilidade:\n\n"
            for e in erros:
                msg_chat += f"• {e}\n"
            msg_chat += "\nMe fala o que não sabe preencher que te explico."
            chat_assistente.iniciar_conversa(msg_chat)
            st.stop()

        peso_taxado_ml = calcular_peso_taxado(peso_kg, dim1 or 0, dim2 or 0, dim3 or 0)

        # ── CALCULA AS 3 PLATAFORMAS ───────────────────────────────────────────
        with st.spinner("Calculando viabilidade nas plataformas..."):
            res_ml, res_sp, res_sh = None, None, None

            if preco_ml:
                res_ml = gerar_analise(
                    preco_ml, custo, peso_taxado_ml, categoria, modalidade,
                    nome_produto, dims_ref, qtd_ref, nf_pct_usado, custo_operacional, lpv_usado,
                )

            if preco_sp:
                calc_sp = lambda p: calcular_resultado_shopee(p, custo, nf_pct_usado, custo_operacional, lpv_usado)
                res_sp = gerar_analise_fn(preco_sp, custo, nome_produto, nf_pct_usado,
                                          custo_operacional, lpv_usado, calc_sp)

            if preco_sh:
                calc_sh = lambda p: calcular_resultado_shein(p, custo, peso_kg, nf_pct_usado, custo_operacional, lpv_usado)
                res_sh = gerar_analise_fn(preco_sh, custo, nome_produto, nf_pct_usado,
                                          custo_operacional, lpv_usado, calc_sh)

        # registra no histórico
        plataformas_log = " / ".join(
            f"{p}: {r['tag']} R${pr:.2f}"
            for p, r, pr in [("ML", res_ml, preco_ml or 0), ("Shopee", res_sp, preco_sp or 0), ("Shein", res_sh, preco_sh or 0)]
            if r is not None
        )
        atividades.registrar_atividade(
            usuario_logado, "Análise de Viabilidade", nome_produto,
            f"custo R${custo:.2f} · {plataformas_log}"
        )

        # ── RESULTADO LADO A LADO ──────────────────────────────────────────────
        st.markdown("---")

        # cores de marca de cada plataforma
        PLATAFORMAS = {
            "ml": ("#e8e8e8", "#ffe600", "Mercado Livre"),   # texto branco, borda amarela ML
            "sp": ("#ee4d2d", "#ee4d2d", "Shopee"),           # laranja Shopee
            "sh": ("#fe4a7b", "#fe4a7b", "Shein"),            # rosa Shein
        }

        col_r1, col_r2, col_r3 = st.columns(3)

        for col, chave, resultado, preco in [
            (col_r1, "ml", res_ml, preco_ml),
            (col_r2, "sp", res_sp, preco_sp),
            (col_r3, "sh", res_sh, preco_sh),
        ]:
            cor_texto, cor_borda, nome_plataforma = PLATAFORMAS[chave]
            with col:
                st.markdown(
                    f'<h2 style="color:{cor_texto}; border-bottom: 2px solid {cor_borda}; '
                    f'padding-bottom: 8px; margin-bottom: 20px; font-size: 20px; '
                    f'font-weight: 600; letter-spacing: 0.02em;">{nome_plataforma}</h2>',
                    unsafe_allow_html=True,
                )
                if resultado is not None:
                    _mostrar_resultado(resultado, nome_produto)
                else:
                    st.markdown(
                        '<div style="color:#444; font-style:italic; font-size:13px; '
                        'padding: 16px 0;">Preço não informado</div>',
                        unsafe_allow_html=True,
                    )

# ── ASSISTENTE IA FLUTUANTE ────────────────────────────────────────────────────
chat_assistente.renderizar_chat()
