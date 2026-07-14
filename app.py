import streamlit as st
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


def buscar_desconto_maximo(preco_base, custo, peso_kg, categoria, modalidade, nf_pct, custo_op, lpv):
    """Testa descontos de 5 em 5% e acha o maior que ainda mantem UC >= UC_MINIMO."""
    testados = []
    desconto_maximo = None
    for pct in [5, 10, 15, 20, 25, 30]:
        preco_teste = round(preco_base * (1 - pct/100), 2)
        r = calcular_resultado(preco_teste, custo, peso_kg, categoria, modalidade, nf_pct, custo_op, lpv)
        ok = r['uc'] is not None and r['uc'] >= UC_MINIMO
        testados.append((pct, preco_teste, r, ok))
        if ok:
            desconto_maximo = pct
    return desconto_maximo, testados


def buscar_teto_preco(preco_base, custo, peso_kg, categoria, modalidade, nf_pct, custo_op, lpv):
    """Quando nao ha margem pra desconto: mostra o efeito de precificar mais
    alto, ate atingir uma UC saudavel de referencia (1,5/1)."""
    testados = []
    preco_referencia = None
    for pct in [5, 10, 15, 20, 25, 30]:
        preco_teste = round(preco_base * (1 + pct/100), 2)
        r = calcular_resultado(preco_teste, custo, peso_kg, categoria, modalidade, nf_pct, custo_op, lpv)
        testados.append((pct, preco_teste, r))
        if preco_referencia is None and r['uc'] is not None and r['uc'] >= 1.5:
            preco_referencia = preco_teste
    return preco_referencia, testados


def montar_tabela_horizontal_pct(testados, coluna_pct_label):
    linhas = [
        f"| {coluna_pct_label} | Preço | Lucro | UC |",
        "|---|---|---|---|",
    ]
    for item in testados:
        pct, preco_teste, r = item[0], item[1], item[2]
        uc_str = f"{r['uc']}/1" if r['uc'] is not None else "sem lucro"
        linhas.append(f"| {pct}% | R${preco_teste:.2f} | R${r['lucro_liquido']:.2f} | {uc_str} |")
    return "\n".join(linhas)


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

    tabela_principal = montar_tabela_vertical(r_base)

    # Analise de promocao
    desconto_max, testados_desc = buscar_desconto_maximo(
        preco_mercado, custo, peso_taxado, categoria, modalidade, nf_pct, custo_operacional, lpv)

    if desconto_max:
        texto_promo = f"✅ Dá pra promover em até **{desconto_max}%** de desconto e ainda manter o UC mínimo ({UC_MINIMO}/1)."
        tabela_promo = montar_tabela_horizontal_pct(
            [t for t in testados_desc if t[0] <= desconto_max], "Desconto")
    else:
        preco_ref, testados_alta = buscar_teto_preco(
            preco_mercado, custo, peso_taxado, categoria, modalidade, nf_pct, custo_operacional, lpv)
        if preco_ref:
            texto_promo = (
                f"⚠️ Não tem margem pra dar desconto nesse preço. Vale checar o mercado: se der pra anunciar um "
                f"pouco mais caro e ainda ficar competitivo, o teto sugerido (pra abrir espaço de promoção depois) "
                f"é em torno de **R${preco_ref:.2f}** — confirme se esse valor ainda compete bem antes de aplicar."
            )
        else:
            texto_promo = "⚠️ Não tem margem pra desconto nesse preço, e mesmo subindo o preço em até 30% a margem continua apertada. Vale revisar o custo do produto ou o custo operacional antes de anunciar."
        tabela_promo = montar_tabela_horizontal_pct(testados_alta, "Aumento")

    # Alerta de cubagem (so mostra se o peso volumetrico for o que decidiu o frete)
    alerta_cubagem = ""
    if any(d > 0 for d in dims_ref):
        peso_cubado = (dims_ref[0] * dims_ref[1] * dims_ref[2]) / 6000
        if peso_cubado > peso_taxado - 0.001 and peso_cubado > 0:
            alerta_cubagem = f"⚠️ **Atenção:** o frete foi calculado pelo volume da embalagem ({dims_ref[0]:.0f}x{dims_ref[1]:.0f}x{dims_ref[2]:.0f}cm), não pelo peso — o Mercado Livre pode reconferir essa medida depois e mudar o custo."

    return {
        "tag": tag,
        "resumo": resumo,
        "tabela_principal": tabela_principal,
        "texto_promo": texto_promo,
        "tabela_promo": tabela_promo,
        "alerta_cubagem": alerta_cubagem,
        "preco_sugerido": preco_mercado,
    }

# ── INTERFACE ──────────────────────────────────────────────────────────────────

st.title("MartinSousa App")

with st.sidebar:
    st.header("MartinSousa App")
    st.caption("v10.0")
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
            resultado = gerar_analise(
                preco_mercado, custo, peso_taxado, categoria, modalidade,
                nome_produto, dims_ref, qtd_ref, nf_pct_usado, custo_operacional,
                lpv_usado,
            )

        st.markdown("---")

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

        st.markdown("#### Conta detalhada")
        st.markdown(resultado["tabela_principal"])

        st.markdown("#### Viabilidade de promoção")
        st.markdown(resultado["texto_promo"])
        st.markdown(resultado["tabela_promo"])

        if resultado["alerta_cubagem"]:
            st.markdown("---")
            st.markdown(resultado["alerta_cubagem"])
