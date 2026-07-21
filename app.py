import streamlit as st
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

st.set_page_config(page_title="MS Studio", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0e0e0e; color: #f5f5f5; }
    table { color: #f5f5f5 !important; }
    th { background-color: #1a1a1a !important; color: #ffffff !important; }
    td { background-color: #0e0e0e !important; }
</style>
""", unsafe_allow_html=True)

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
        "VIAVEL":    ("🟢", "VIÁVEL", "#1e4620", "#4ade80"),
        "RESSALVAS": ("🟡", "VIÁVEL COM ATENÇÃO", "#4d3a10", "#facc15"),
        "INVIAVEL":  ("🔴", "INVIÁVEL", "#4a1414", "#f87171"),
    }
    emoji, texto_selo, cor_fundo, cor_borda = SELOS[resultado["tag"]]

    st.markdown(f"""
    <div style="background-color:{cor_fundo}; border-left: 5px solid {cor_borda};
                border-radius: 8px; padding: 14px 18px; margin-bottom: 10px;">
        <span style="font-size: 20px; font-weight: 700; color: {cor_borda};">
            {emoji} {texto_selo}
        </span><br>
        <span style="color: #e5e5e5; font-size: 15px;">
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
               "Descrição", "Imagem", "Financeiro", "Histórico"]
if _eh_admin:
    _nomes_abas.append("Administrativo")

_abas = st.tabs(_nomes_abas)
(aba_viabilidade, aba_triagem, aba_palavras, aba_titulo,
 aba_descricao, aba_imagem, aba_financeiro, aba_historico) = _abas[:8]

with aba_financeiro:
    financeiro.pagina_financeiro(usuario_logado)

with aba_historico:
    atividades.pagina_historico()

if _eh_admin:
    with _abas[8]:
        admin.pagina_admin(usuario_logado)

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

    # ── SUB-ABAS POR PLATAFORMA ────────────────────────────────────────────────
    tab_ml, tab_shopee, tab_shein = st.tabs(["🛒 Mercado Livre", "🛍️ Shopee", "👗 Shein"])

    # ══════════════════════════════════════════════════════════════════════════
    # MERCADO LIVRE
    # ══════════════════════════════════════════════════════════════════════════
    with tab_ml:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Dados do Produto")
            nome_produto  = st.text_input("Nome do produto", key="ml_nome")
            custo         = st.number_input("Preco de custo (R$)", min_value=0.0, value=None, step=0.50, format="%.2f", placeholder="0,00", key="ml_custo")
            preco_mercado = st.number_input("Preco de mercado (pesquisado por voce)", min_value=0.0, value=None, step=0.50, format="%.2f", placeholder="0,00", key="ml_preco")
            qtd_ref       = st.number_input("Quantidade por unidade/kit", min_value=1, step=1, value=1, key="ml_qtd")
            categoria     = st.selectbox("Categoria no ML", sorted(ML_COMISSAO_POR_CATEGORIA.keys()), key="ml_categoria")
            custo_operacional = st.number_input("Custo operacional (embalagem/logistica/ADS/cross docking)",
                                                 min_value=0.0, value=8.13, step=0.50, format="%.2f", key="ml_custo_op")

        with col2:
            st.subheader("Dimensões e Peso (produto EMBALADO)")
            st.caption("Use o peso e as medidas do pacote pronto pra envio, não só do produto — é isso que o Mercado Livre mede de verdade.")
            col_peso, col_unit = st.columns([3, 1])
            peso_val  = col_peso.number_input("Peso embalado", min_value=0.0, value=None, step=1.0, format="%.0f", placeholder="ex: 700", key="ml_peso_val")
            peso_unit = col_unit.selectbox("", ["g", "kg"], label_visibility="hidden", key="ml_peso_unit")
            peso_kg   = (peso_val / 1000 if peso_val else 0) if peso_unit == "g" else (peso_val or 0)
            st.caption("Informe as 3 medidas da embalagem (usadas no cálculo de frete por peso cubado)")
            dim1 = st.number_input("Medida 1 (cm)", min_value=0.0, value=None, step=0.5, format="%.1f", placeholder="ex: 30", key="ml_dim1")
            dim2 = st.number_input("Medida 2 (cm)", min_value=0.0, value=None, step=0.5, format="%.1f", placeholder="ex: 30", key="ml_dim2")
            dim3 = st.number_input("Medida 3 (cm)", min_value=0.0, value=None, step=0.5, format="%.1f", placeholder="ex: 2", key="ml_dim3")
            dims_ref = [dim1 or 0, dim2 or 0, dim3 or 0]

        st.markdown("---")
        analisar_ml = st.button("Analisar Viabilidade ML", type="primary", use_container_width=True, key="btn_ml")

        if analisar_ml:
            erros = []
            if not nome_produto:      erros.append("Nome do produto")
            if custo is None:         erros.append("Preco de custo")
            if preco_mercado is None: erros.append("Preco de mercado")
            if erros:
                st.warning(f"Preencha: {', '.join(erros)}")
                st.stop()

            peso_taxado = calcular_peso_taxado(peso_kg, dim1 or 0, dim2 or 0, dim3 or 0)

            with st.spinner("Calculando viabilidade..."):
                resultado = gerar_analise(
                    preco_mercado, custo, peso_taxado, categoria, modalidade,
                    nome_produto, dims_ref, qtd_ref, nf_pct_usado, custo_operacional,
                    lpv_usado,
                )

            atividades.registrar_atividade(
                usuario_logado, "Análise de Viabilidade — ML", nome_produto,
                f"{resultado['tag']} · R${preco_mercado:.2f} · custo R${custo:.2f}"
            )

            st.markdown("---")
            _mostrar_resultado(resultado, nome_produto)

    # ══════════════════════════════════════════════════════════════════════════
    # SHOPEE
    # ══════════════════════════════════════════════════════════════════════════
    with tab_shopee:
        st.caption("Comissão por faixa de preço · Frete Grátis obrigatório (vendedor paga R$0,00 de frete)")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Dados do Produto")
            sp_nome     = st.text_input("Nome do produto", key="sp_nome")
            sp_custo    = st.number_input("Preco de custo (R$)", min_value=0.0, value=None, step=0.50, format="%.2f", placeholder="0,00", key="sp_custo")
            sp_preco    = st.number_input("Preco de mercado (pesquisado por voce)", min_value=0.0, value=None, step=0.50, format="%.2f", placeholder="0,00", key="sp_preco")
            sp_custo_op = st.number_input("Custo operacional (embalagem/logistica/ADS/cross docking)",
                                           min_value=0.0, value=8.13, step=0.50, format="%.2f", key="sp_custo_op")

        with col2:
            st.subheader("Tabela de comissões Shopee")
            st.markdown("""
| Faixa de preço | Comissão | Adicional fixo |
|---|---|---|
| R$8,00 – R$79,99 | 20% | + R$4,00 |
| R$80,00 – R$159,99 | 18% | — |
| R$160,00 em diante | 15% | — |
""")
            st.caption("Frete líquido do vendedor: R$0,00 · Não há cubagem nem dimensões para informar")

        st.markdown("---")
        analisar_sp = st.button("Analisar Viabilidade Shopee", type="primary", use_container_width=True, key="btn_sp")

        if analisar_sp:
            erros = []
            if not sp_nome:      erros.append("Nome do produto")
            if sp_custo is None: erros.append("Preco de custo")
            if sp_preco is None: erros.append("Preco de mercado")
            if erros:
                st.warning(f"Preencha: {', '.join(erros)}")
                st.stop()

            calc_fn_sp = lambda p: calcular_resultado_shopee(p, sp_custo, nf_pct_usado, sp_custo_op, lpv_usado)

            with st.spinner("Calculando viabilidade Shopee..."):
                resultado_sp = gerar_analise_fn(
                    sp_preco, sp_custo, sp_nome, nf_pct_usado, sp_custo_op,
                    lpv_usado, calc_fn_sp,
                )

            atividades.registrar_atividade(
                usuario_logado, "Análise de Viabilidade — Shopee", sp_nome,
                f"{resultado_sp['tag']} · R${sp_preco:.2f} · custo R${sp_custo:.2f}"
            )

            st.markdown("---")
            _mostrar_resultado(resultado_sp, sp_nome)

    # ══════════════════════════════════════════════════════════════════════════
    # SHEIN
    # ══════════════════════════════════════════════════════════════════════════
    with tab_shein:
        st.caption("Comissão 18% flat · Frete pago pelo vendedor (tabela por peso)")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Dados do Produto")
            sh_nome     = st.text_input("Nome do produto", key="sh_nome")
            sh_custo    = st.number_input("Preco de custo (R$)", min_value=0.0, value=None, step=0.50, format="%.2f", placeholder="0,00", key="sh_custo")
            sh_preco    = st.number_input("Preco de mercado (pesquisado por voce)", min_value=0.0, value=None, step=0.50, format="%.2f", placeholder="0,00", key="sh_preco")
            sh_custo_op = st.number_input("Custo operacional (embalagem/logistica/ADS/cross docking)",
                                           min_value=0.0, value=8.13, step=0.50, format="%.2f", key="sh_custo_op")

            st.markdown("---")
            st.subheader("Peso do Produto Embalado")
            st.caption("Na Shein o vendedor paga o frete — o custo varia conforme o peso do pacote.")
            col_peso_sh, col_unit_sh = st.columns([3, 1])
            sh_peso_val  = col_peso_sh.number_input("Peso embalado", min_value=0.0, value=None, step=1.0, format="%.0f", placeholder="ex: 700", key="sh_peso_val")
            sh_peso_unit = col_unit_sh.selectbox("", ["g", "kg"], label_visibility="hidden", key="sh_peso_unit")
            sh_peso_kg   = (sh_peso_val / 1000 if sh_peso_val else 0) if sh_peso_unit == "g" else (sh_peso_val or 0)

        with col2:
            st.subheader("Tabela de frete Shein")
            st.markdown("""
| Peso máximo | Frete (vendedor paga) |
|---|---|
| até 300 g | R$4,00 |
| até 500 g | R$5,00 |
| até 1 kg | R$7,00 |
| até 2 kg | R$10,00 |
| até 3 kg | R$13,00 |
| até 5 kg | R$18,00 |
| até 7 kg | R$23,00 |
| até 10 kg | R$31,00 |
| até 15 kg | R$44,00 |
| até 23 kg | R$62,00 |
| acima de 23 kg | R$106,00 |
""")

        st.markdown("---")
        analisar_sh = st.button("Analisar Viabilidade Shein", type="primary", use_container_width=True, key="btn_sh")

        if analisar_sh:
            erros = []
            if not sh_nome:      erros.append("Nome do produto")
            if sh_custo is None: erros.append("Preco de custo")
            if sh_preco is None: erros.append("Preco de mercado")
            if sh_peso_kg == 0:  erros.append("Peso do produto (necessário para calcular o frete)")
            if erros:
                st.warning(f"Preencha: {', '.join(erros)}")
                st.stop()

            calc_fn_sh = lambda p: calcular_resultado_shein(p, sh_custo, sh_peso_kg, nf_pct_usado, sh_custo_op, lpv_usado)

            with st.spinner("Calculando viabilidade Shein..."):
                resultado_sh = gerar_analise_fn(
                    sh_preco, sh_custo, sh_nome, nf_pct_usado, sh_custo_op,
                    lpv_usado, calc_fn_sh,
                )

            atividades.registrar_atividade(
                usuario_logado, "Análise de Viabilidade — Shein", sh_nome,
                f"{resultado_sh['tag']} · R${sh_preco:.2f} · custo R${sh_custo:.2f}"
            )

            st.markdown("---")
            _mostrar_resultado(resultado_sh, sh_nome)
