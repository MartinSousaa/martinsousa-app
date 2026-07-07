import streamlit as st
import requests
import anthropic
from parametros_oficiais import (
    LPV_OFICIAL, NF_OFICIAL,
    ML_FAIXAS_PRECO, ML_FRETE_TABELA, ML_COMISSAO_POR_CATEGORIA,
)

st.set_page_config(page_title="MartinSousa - Análise de Viabilidade", layout="wide")

# ── FUNÇÕES DE CÁLCULO ─────────────────────────────────────────────────────────

def calcular_peso_taxado(peso_real_kg, altura_cm, largura_cm, comprimento_cm):
    peso_cubado = (altura_cm * largura_cm * comprimento_cm) / 6000
    return max(peso_real_kg, peso_cubado)

def calcular_frete_ml(preco, peso_kg):
    if preco < 19:
        return preco * 0.5
    idx_preco = len(ML_FAIXAS_PRECO) - 1
    for i, limite in enumerate(ML_FAIXAS_PRECO):
        if preco <= limite:
            idx_preco = i
            break
    for peso_limite, valores in ML_FRETE_TABELA:
        if peso_kg <= peso_limite:
            return valores[idx_preco]
    return ML_FRETE_TABELA[-1][1][idx_preco]

def calcular_comissao_ml(preco, categoria):
    taxas = ML_COMISSAO_POR_CATEGORIA.get(categoria, ML_COMISSAO_POR_CATEGORIA['Outros'])
    return preco * taxas[1]  # sempre Premium

def calcular_viabilidade(preco_venda, custo, peso_taxado_kg, categoria):
    comissao = calcular_comissao_ml(preco_venda, categoria)
    frete    = calcular_frete_ml(preco_venda, peso_taxado_kg)
    nf       = preco_venda * NF_OFICIAL
    lpv      = LPV_OFICIAL
    total_custos = custo + comissao + frete + nf + lpv
    lucro    = preco_venda - total_custos
    margem   = (lucro / preco_venda * 100) if preco_venda > 0 else 0
    uc       = round(lpv / lucro, 1) if lucro > 0 else None
    return {
        'preco':     preco_venda,
        'custo':     custo,
        'comissao':  comissao,
        'frete':     frete,
        'nf':        nf,
        'lpv':       lpv,
        'lucro':     lucro,
        'margem':    margem,
        'uc':        uc,
    }

# ── BUSCA NO MERCADO LIVRE ─────────────────────────────────────────────────────

def buscar_anuncios_ml(termo, client_id, client_secret):
    try:
        # Token de acesso
        resp = requests.post(
            "https://api.mercadolibre.com/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=10
        )
        token = resp.json().get("access_token")
        if not token:
            return None, "Erro ao obter token do ML"

        # Busca de anúncios
        resp2 = requests.get(
            "https://api.mercadolibre.com/sites/MLB/search",
            params={"q": termo, "limit": 50},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        resultados = resp2.json().get("results", [])
        return resultados, None
    except Exception as e:
        return None, str(e)

def analisar_anuncios(resultados):
    precos_com_vendas = []
    precos_sem_vendas = []
    for item in resultados:
        preco = item.get("price", 0)
        vendas = item.get("sold_quantity", 0)
        if vendas and vendas > 0:
            precos_com_vendas.append(preco)
        else:
            precos_sem_vendas.append(preco)
    return precos_com_vendas, precos_sem_vendas

# ── VEREDICTO COM IA ───────────────────────────────────────────────────────────

def gerar_veredicto(resultado_calculo, preco_min_com_venda, preco_max_com_venda, api_key):
    client = anthropic.Anthropic(api_key=api_key)
    prompt = f"""
Você é um especialista em viabilidade de produtos para Mercado Livre.
Com base nos dados abaixo, gere um veredicto objetivo em português:

DADOS DO PRODUTO:
- Preço de venda analisado: R${resultado_calculo['preco']:.2f}
- Custo: R${resultado_calculo['custo']:.2f}
- Comissão ML (Premium): R${resultado_calculo['comissao']:.2f}
- Frete: R${resultado_calculo['frete']:.2f}
- NF (10%): R${resultado_calculo['nf']:.2f}
- LPV: R${resultado_calculo['lpv']:.2f}
- Lucro líquido: R${resultado_calculo['lucro']:.2f}
- Margem: {resultado_calculo['margem']:.1f}%
- Unidade de contribuição: {resultado_calculo['uc']}

MERCADO:
- Faixa de preço dos anúncios COM vendas: R${preco_min_com_venda:.2f} a R${preco_max_com_venda:.2f}

Responda com:
1. Veredicto: VIÁVEL / VIÁVEL COM RESSALVAS / INVIÁVEL
2. Justificativa em 2-3 linhas
3. Recomendação de preço ideal (se aplicável)

Seja direto e objetivo.
"""
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text

# ── INTERFACE ──────────────────────────────────────────────────────────────────

st.title("📊 Análise de Viabilidade — Mercado Livre")
st.markdown("---")

with st.sidebar:
    st.header("⚙️ Configurações")
    api_key_claude = st.text_input("Chave API Claude", type="password")
    ml_client_id   = st.text_input("ML Client ID")
    ml_secret      = st.text_input("ML Client Secret", type="password")
    st.markdown("---")
    st.caption("MartinSousa App v1.0")

col1, col2 = st.columns(2)

with col1:
    st.subheader("📦 Dados do Produto")
    nome_produto  = st.text_input("Nome do produto (para busca no ML)")
    custo         = st.number_input("Preço de custo (R$)", min_value=0.0, step=0.50, format="%.2f")
    preco_venda   = st.number_input("Preço de venda pretendido (R$)", min_value=0.0, step=0.50, format="%.2f")
    categoria     = st.selectbox("Categoria no ML", sorted(ML_COMISSAO_POR_CATEGORIA.keys()))

with col2:
    st.subheader("📐 Dimensões e Peso")
    peso_real = st.number_input("Peso real (kg)", min_value=0.0, step=0.05, format="%.3f")
    altura    = st.number_input("Altura (cm)", min_value=0.0, step=0.5)
    largura   = st.number_input("Largura (cm)", min_value=0.0, step=0.5)
    comprimento = st.number_input("Comprimento (cm)", min_value=0.0, step=0.5)

st.markdown("---")
analisar = st.button("🔍 Analisar Viabilidade", type="primary", use_container_width=True)

if analisar:
    if not nome_produto or not custo or not preco_venda:
        st.warning("Preencha nome do produto, custo e preço de venda.")
    elif not api_key_claude or not ml_client_id or not ml_secret:
        st.warning("Preencha as configurações na barra lateral.")
    else:
        peso_taxado = calcular_peso_taxado(peso_real, altura, largura, comprimento)
        resultado   = calcular_viabilidade(preco_venda, custo, peso_taxado, categoria)

        with st.spinner("Buscando anúncios no Mercado Livre..."):
            anuncios, erro = buscar_anuncios_ml(nome_produto, ml_client_id, ml_secret)

        if erro:
            st.error(f"Erro na busca do ML: {erro}")
            anuncios = []

        precos_com, precos_sem = analisar_anuncios(anuncios or [])
        min_com = min(precos_com) if precos_com else 0
        max_com = max(precos_com) if precos_com else 0
        min_sem = min(precos_sem) if precos_sem else 0
        max_sem = max(precos_sem) if precos_sem else 0

        st.markdown("---")
        st.subheader(f"📈 Resultado — {nome_produto}")

        # Mercado
        c1, c2 = st.columns(2)
        with c1:
            st.metric("Anúncios COM vendas encontrados", len(precos_com))
            if precos_com:
                st.info(f"Faixa de preço: R${min_com:.2f} a R${max_com:.2f}")
        with c2:
            st.metric("Anúncios SEM vendas encontrados", len(precos_sem))
            if precos_sem:
                st.info(f"Faixa de preço: R${min_sem:.2f} a R${max_sem:.2f}")

        st.markdown("---")

        # Resumo de viabilidade
        st.subheader("💰 Resumo de Viabilidade")
        cols = st.columns(4)
        cols[0].metric("Custo do produto", f"R${resultado['custo']:.2f}")
        cols[1].metric("Comissão ML (Premium)", f"R${resultado['comissao']:.2f}")
        cols[2].metric("Frete", f"R${resultado['frete']:.2f}")
        cols[3].metric("NF (10%)", f"R${resultado['nf']:.2f}")

        cols2 = st.columns(4)
        cols2[0].metric("LPV", f"R${resultado['lpv']:.2f}")
        cols2[1].metric("Lucro líquido", f"R${resultado['lucro']:.2f}")
        cols2[2].metric("Margem", f"{resultado['margem']:.1f}%")
        cols2[3].metric("Unidade de contribuição", f"1/{resultado['uc']}" if resultado['uc'] else "—")

        st.caption(f"Peso taxado utilizado: {peso_taxado:.3f} kg")

        # Veredicto IA
        if api_key_claude and precos_com:
            st.markdown("---")
            with st.spinner("Gerando veredicto com IA..."):
                veredicto = gerar_veredicto(resultado, min_com, max_com, api_key_claude)
            st.subheader("🤖 Veredicto")
            if "VIÁVEL COM RESSALVAS" in veredicto:
                st.warning(veredicto)
            elif "INVIÁVEL" in veredicto:
                st.error(veredicto)
            else:
                st.success(veredicto)
        elif not precos_com:
            st.info("Nenhum anúncio com vendas encontrado — veredicto de mercado indisponível.")
