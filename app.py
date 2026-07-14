import streamlit as st
import anthropic
from datetime import date
from params_oficiais import (
    LPV_OFICIAL, NF_OFICIAL,
    ML_FAIXAS_PRECO, ML_FRETE_TABELA, ML_COMISSAO_POR_CATEGORIA,
)
import financeiro

st.set_page_config(page_title="MartinSousa - Analise de Viabilidade", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0e0e0e; color: #f5f5f5; }
    table { color: #f5f5f5 !important; }
    th { background-color: #1a1a1a !important; color: #ffffff !important; }
    td { background-color: #0e0e0e !important; }
</style>
""", unsafe_allow_html=True)

API_KEY_CLAUDE = st.secrets.get("ANTHROPIC_API_KEY", "")

# UC minimo pra aprovar produto -- definido pelo Léo em 14/07/2026,
# provisorio ate ele analisar as UCs reais da operacao.
UC_MINIMO = 0.8

# ── CÁLCULO ────────────────────────────────────────────────────────────────────

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
        # Produtos abaixo de R$19 pagam no maximo metade do preco.
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

# ── VEREDICTO IA ───────────────────────────────────────────────────────────────

def montar_tabela_cenarios(pontos, resultados):
    """Monta a tabela markdown com os 3 cenarios de preco -- pura
    formatacao em Python, sem gastar tokens de IA pra isso."""
    linhas = [
        "| Cenário | Preço | Custo produto | Operacional | Comissão | Frete | NF | Lucro líquido | Margem | UC |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    nomes = {0: "-10%", 1: "Preço atual", 2: "+10%"}
    for i, p in enumerate(pontos):
        r = resultados[p]
        uc_str = f"{r['uc']}/1" if r['uc'] is not None else "sem lucro"
        linhas.append(
            f"| {nomes.get(i, '')} | R${p:.2f} | R${r['custo']:.2f} | R${r['custo_operacional']:.2f} | "
            f"R${r['comissao']:.2f} | R${r['frete']:.2f} | R${r['nf']:.2f} | "
            f"**R${r['lucro_liquido']:.2f}** | {r['margem']:.1f}% | **{uc_str}** |"
        )
    return "\n".join(linhas)


def gerar_veredicto(preco_mercado, custo, peso_taxado, categoria, modalidade,
                     nome, dims_ref, qtd_ref, nf_pct, custo_operacional, lpv, lpv_origem):
    pontos = sorted(set([
        round(preco_mercado * 0.9, 2),
        round(preco_mercado, 2),
        round(preco_mercado * 1.1, 2),
    ]))

    resultados = {}
    for p in pontos:
        resultados[p] = calcular_resultado(p, custo, peso_taxado, categoria, modalidade, nf_pct, custo_operacional, lpv)

    tabela_md = montar_tabela_cenarios(pontos, resultados)

    # Veredicto e decidido em Python, direto pela regra -- nao depende da IA
    r_base = calcular_resultado(preco_mercado, custo, peso_taxado, categoria, modalidade, nf_pct, custo_operacional, lpv)
    uc_base = r_base['uc']
    if uc_base is None or uc_base < UC_MINIMO:
        veredicto_tag = "INVIAVEL"
    elif uc_base < 1.0:
        veredicto_tag = "RESSALVAS"
    else:
        veredicto_tag = "VIAVEL"

    dims_str = f"{dims_ref[0]}x{dims_ref[1]}x{dims_ref[2]}cm (embalado)" if any(d > 0 for d in dims_ref) else "nao informado"
    lpv_str = f"R${lpv:.2f}" if lpv else "reserva (sem dado financeiro ainda)"
    uc_str_base = f"{uc_base}/1" if uc_base is not None else "sem lucro"

    # Prompt curto: a IA so escreve o texto de recomendacao/alerta, nao repete
    # numeros nem monta tabela -- isso economiza bastante token de saida.
    prompt = f"""Produto: {nome} | Medidas embaladas: {dims_str} | LPV: {lpv_str}
Preco de mercado: R${preco_mercado:.2f} | UC nesse preco: {uc_str_base} | Veredicto: {veredicto_tag} (corte minimo {UC_MINIMO}/1)

Em no MAXIMO 4 linhas curtas, escreva pra um colaborador que nao entende de financeiro:
1. Uma frase dizendo se pode vender ou nao e por que (em linguagem simples, sem repetir os numeros da tabela que ele ja vai ver)
2. Se tiver algo de risco a avisar (ex: medida embalada pode ser reavaliada pelo ML e mudar o frete), 1 linha de alerta
Nao repita valores em R$ que ja aparecem em tabela. Seja direto, sem enrolação, sem explicar conceito de UC/margem de novo.
"""

    client = anthropic.Anthropic(api_key=API_KEY_CLAUDE)
    msg = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=250,
        messages=[{"role": "user", "content": prompt}]
    )
    texto_ia = msg.content[0].text.strip()

    return {
        "tag": veredicto_tag,
        "tabela_md": tabela_md,
        "texto_ia": texto_ia,
        "preco_sugerido": preco_mercado,
    }

# ── INTERFACE ──────────────────────────────────────────────────────────────────

st.title("MartinSousa App")

with st.sidebar:
    st.header("MartinSousa App")
    st.caption("v9.1")
    st.markdown("---")
    modalidade = st.selectbox("Modalidade ML", ["Premium", "Classico"])
    st.markdown("---")
    st.caption("Chaves configuradas automaticamente")

aba_viabilidade, aba_financeiro = st.tabs(["Análise de Viabilidade", "Financeiro"])

with aba_financeiro:
    financeiro.pagina_financeiro()

with aba_viabilidade:
    # Busca LPV e aliquota calculados a partir dos dados financeiros reais.
    # Se ainda nao houver dado suficiente, cai pros valores fixos antigos
    # (parametros_oficiais.py) so como reserva, deixando isso claro na tela.
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

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Dados do Produto")
        nome_produto  = st.text_input("Nome do produto")
        custo         = st.number_input("Preco de custo (R$)", min_value=0.0, value=None, step=0.50, format="%.2f", placeholder="0,00")
        preco_mercado = st.number_input("Preco de mercado (pesquisado por voce)", min_value=0.0, value=None, step=0.50, format="%.2f", placeholder="0,00")
        qtd_ref       = st.number_input("Quantidade por unidade/kit", min_value=1, step=1, value=1)
        categoria     = st.selectbox("Categoria no ML", sorted(ML_COMISSAO_POR_CATEGORIA.keys()))
        custo_operacional = st.number_input("Custo operacional (embalagem/logistica/ADS/cross docking)",
                                             min_value=0.0, value=8.13, step=0.50, format="%.2f")

    with col2:
        st.subheader("Dimensões e Peso (produto EMBALADO)")
        st.caption("Use o peso e as medidas do pacote pronto pra envio, não só do produto — é isso que o Mercado Livre mede de verdade.")
        col_peso, col_unit = st.columns([3,1])
        peso_val  = col_peso.number_input("Peso embalado", min_value=0.0, value=None, step=1.0, format="%.0f", placeholder="ex: 700")
        peso_unit = col_unit.selectbox("", ["g", "kg"], label_visibility="hidden")
        peso_kg   = (peso_val / 1000 if peso_val else 0) if peso_unit == "g" else (peso_val or 0)
        st.caption("Informe as 3 medidas da embalagem (usadas no cálculo de frete por peso cubado)")
        dim1 = st.number_input("Medida 1 (cm)", min_value=0.0, value=None, step=0.5, format="%.1f", placeholder="ex: 30")
        dim2 = st.number_input("Medida 2 (cm)", min_value=0.0, value=None, step=0.5, format="%.1f", placeholder="ex: 30")
        dim3 = st.number_input("Medida 3 (cm)", min_value=0.0, value=None, step=0.5, format="%.1f", placeholder="ex: 2")
        dims_ref = [dim1 or 0, dim2 or 0, dim3 or 0]

    st.markdown("---")
    analisar = st.button("Analisar Viabilidade", type="primary", use_container_width=True)

    if analisar:
        erros = []
        if not nome_produto:  erros.append("Nome do produto")
        if not custo:         erros.append("Preco de custo")
        if not preco_mercado: erros.append("Preco de mercado")
        if erros:
            st.warning(f"Preencha: {', '.join(erros)}")
            st.stop()

        peso_taxado = calcular_peso_taxado(peso_kg, dim1 or 0, dim2 or 0, dim3 or 0)

        with st.spinner("Calculando viabilidade..."):
            resultado = gerar_veredicto(
                preco_mercado, custo, peso_taxado, categoria, modalidade,
                nome_produto, dims_ref, qtd_ref, nf_pct_usado, custo_operacional,
                lpv_usado, lpv_origem_usada,
            )

        st.markdown("---")

        SELOS = {
            "VIAVEL":    ("🟢", "VIÁVEL — pode vender", "#1e4620", "#4ade80"),
            "RESSALVAS": ("🟡", "VIÁVEL COM RESSALVAS", "#4d3a10", "#facc15"),
            "INVIAVEL":  ("🔴", "INVIÁVEL — não vender nesse preço", "#4a1414", "#f87171"),
        }
        emoji, texto_selo, cor_fundo, cor_borda = SELOS[resultado["tag"]]

        st.markdown(f"""
        <div style="background-color:{cor_fundo}; border-left: 5px solid {cor_borda};
                    border-radius: 8px; padding: 14px 18px; margin-bottom: 18px;">
            <span style="font-size: 20px; font-weight: 700; color: {cor_borda};">
                {emoji} {texto_selo}
            </span><br>
            <span style="color: #e5e5e5; font-size: 15px;">
                {nome_produto} · Preço sugerido: <b>R${resultado['preco_sugerido']:.2f}</b>
            </span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(resultado["tabela_md"])
        st.markdown("")
        st.markdown(resultado["texto_ia"])
