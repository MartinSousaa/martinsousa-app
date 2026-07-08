import streamlit as st
import anthropic
from datetime import date
from parametros_oficiais import (
    LPV_OFICIAL, NF_OFICIAL,
    ML_FAIXAS_PRECO, ML_FRETE_TABELA, ML_COMISSAO_POR_CATEGORIA,
)
import financeiro

st.set_page_config(page_title="MartinSousa - Analise de Viabilidade", layout="wide")

API_KEY_CLAUDE = st.secrets.get("ANTHROPIC_API_KEY", "")

# ── CÁLCULO ────────────────────────────────────────────────────────────────────

def calcular_peso_taxado(peso_kg, d1, d2, d3):
    peso_cubado = (d1 * d2 * d3) / 6000
    return max(peso_kg, peso_cubado)

def calcular_frete_ml(preco, peso_kg):
    if preco < 19:
        return preco * 0.5
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

def gerar_veredicto(preco_mercado, custo, peso_taxado, categoria, modalidade,
                     nome, dims_ref, qtd_ref, nf_pct, custo_operacional, lpv, lpv_origem):
    pontos = sorted(set([
        round(preco_mercado * 0.9, 2),
        round(preco_mercado, 2),
        round(preco_mercado * 1.1, 2),
    ]))

    faixas_str = ""
    for p in pontos:
        r = calcular_resultado(p, custo, peso_taxado, categoria, modalidade, nf_pct, custo_operacional, lpv)
        uc_str = f"{r['uc']}/1" if r['uc'] is not None else "sem lucro"
        faixas_str += (f"  R${p:.2f} -> lucro bruto R${r['lucro_bruto']:.2f} | "
                        f"lucro liquido R${r['lucro_liquido']:.2f} | margem {r['margem']:.1f}% | UC {uc_str}\n")

    dims_str = f"{dims_ref[0]}x{dims_ref[1]}x{dims_ref[2]}cm" if any(d > 0 for d in dims_ref) else "nao informado"
    lpv_str = f"R${lpv:.2f} (origem: {lpv_origem})" if lpv else "nao disponivel (sem dados financeiros suficientes)"

    prompt = f"""Voce e um especialista em viabilidade de produtos para Mercado Livre.

PRODUTO: {nome}
Quantidade: {qtd_ref} unidade(s)
Medidas: {dims_str}
Custo do produto: R${custo:.2f}
Custo operacional (embalagem/logistica/ADS/cross docking): R${custo_operacional:.2f}
Modalidade: {modalidade}
Nota fiscal: {nf_pct*100:.1f}% (aliquota vigente da empresa)
LPV (meta de lucro por venda pra cobrir custo fixo): {lpv_str}
Preco de mercado informado pelo usuario (pesquisa manual): R${preco_mercado:.2f}

CALCULO NO PRECO DE MERCADO E VARIACOES (-10% / preco informado / +10%):
{faixas_str}

CONCEITO DE UC (Unidade de Contribuicao):
UC = Lucro liquido da venda dividido pelo LPV.
UC = 1/1 significa que a venda cobre exatamente a meta de lucro necessaria.
UC < 1/1 significa que a venda contribui parcialmente (precisa de outras vendas pra compensar).
UC > 1/1 significa que a venda contribui com folga, gerando reserva.
NAO existe ainda um minimo de UC oficialmente confirmado pelo usuario para aprovar produto -- avalie de forma
transparente mostrando o UC de cada cenario, sem inventar um corte rigido. Use como guia razoavel (nao uma regra
travada): UC >= 1/1 e saudavel, UC entre 0,5/1 e 1/1 e aceitavel mas contribui parcialmente, UC abaixo de 0,5/1
e fraco.

ESTRUTURE ASSIM:
1. VEREDICTO: [VIAVEL / VIAVEL COM RESSALVAS / INVIAVEL] (deixe claro que o corte de UC ainda nao foi confirmado pelo usuario)
2. PRECO SUGERIDO: R$X,XX
3. CALCULO: custo | comissao | frete | nf | custo operacional | lucro bruto | lucro liquido | margem | UC
4. ANALISE DE PROMOCAO
5. ALERTAS
6. RECOMENDACAO FINAL: 2-3 linhas
"""

    client = anthropic.Anthropic(api_key=API_KEY_CLAUDE)
    msg = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text

# ── INTERFACE ──────────────────────────────────────────────────────────────────

st.title("MartinSousa App")

with st.sidebar:
    st.header("MartinSousa App")
    st.caption("v8.0")
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

    col_info1, col_info2 = st.columns(2)
    col_info1.metric("LPV vigente", f"R${lpv_usado:.2f}")
    col_info2.metric("NF (alíquota)", f"{nf_pct_usado*100:.1f}%")
    st.caption(f"LPV calculado com base em: {lpv_origem_usada}")
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Dados do Produto")
        fotos = st.file_uploader("Foto do produto (opcional, so pra registro)",
                                  type=["jpg","jpeg","png","webp"],
                                  accept_multiple_files=True)
        nome_produto  = st.text_input("Nome do produto")
        custo         = st.number_input("Preco de custo (R$)", min_value=0.0, value=None, step=0.50, format="%.2f", placeholder="0,00")
        preco_mercado = st.number_input("Preco de mercado (pesquisado por voce)", min_value=0.0, value=None, step=0.50, format="%.2f", placeholder="0,00")
        qtd_ref       = st.number_input("Quantidade por unidade/kit", min_value=1, step=1, value=1)
        categoria     = st.selectbox("Categoria no ML", sorted(ML_COMISSAO_POR_CATEGORIA.keys()))
        custo_operacional = st.number_input("Custo operacional (embalagem/logistica/ADS/cross docking)",
                                             min_value=0.0, value=5.0, step=0.50, format="%.2f")

    with col2:
        st.subheader("Dimensoes e Peso")
        col_peso, col_unit = st.columns([3,1])
        peso_val  = col_peso.number_input("Peso", min_value=0.0, value=None, step=1.0, format="%.0f", placeholder="ex: 700")
        peso_unit = col_unit.selectbox("", ["g", "kg"], label_visibility="hidden")
        peso_kg   = (peso_val / 1000 if peso_val else 0) if peso_unit == "g" else (peso_val or 0)
        st.caption("Informe as 3 medidas (usadas no calculo de frete por peso cubado)")
        dim1 = st.number_input("Medida 1 (cm)", min_value=0.0, value=None, step=0.5, format="%.1f", placeholder="ex: 30")
        dim2 = st.number_input("Medida 2 (cm)", min_value=0.0, value=None, step=0.5, format="%.1f", placeholder="ex: 30")
        dim3 = st.number_input("Medida 3 (cm)", min_value=0.0, value=None, step=0.5, format="%.1f", placeholder="ex: 2")
        dims_ref = [dim1 or 0, dim2 or 0, dim3 or 0]
        if fotos:
            cols_f = st.columns(min(len(fotos), 3))
            for i, f in enumerate(fotos[:3]):
                cols_f[i].image(f, use_container_width=True)

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
            veredicto = gerar_veredicto(
                preco_mercado, custo, peso_taxado, categoria, modalidade,
                nome_produto, dims_ref, qtd_ref, nf_pct_usado, custo_operacional,
                lpv_usado, lpv_origem_usada,
            )

        st.markdown("---")
        st.subheader("Resultado da Analise")
        if "INVIAVEL" in veredicto.upper():
            st.error(veredicto)
        elif "RESSALVAS" in veredicto.upper():
            st.warning(veredicto)
        else:
            st.success(veredicto)
