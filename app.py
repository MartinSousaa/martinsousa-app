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

def gerar_veredicto(preco_mercado, custo, peso_taxado, categoria, modalidade,
                     nome, dims_ref, qtd_ref, nf_pct, custo_operacional, lpv, lpv_origem):
    pontos = sorted(set([
        round(preco_mercado * 0.9, 2),
        round(preco_mercado, 2),
        round(preco_mercado * 1.1, 2),
    ]))

    # Calcula tudo em Python (numeros exatos) e manda pronto pra IA --
    # ela NAO deve recalcular comissao/frete/nf por conta propria.
    faixas_str = ""
    resultados = {}
    for p in pontos:
        r = calcular_resultado(p, custo, peso_taxado, categoria, modalidade, nf_pct, custo_operacional, lpv)
        resultados[p] = r
        uc_str = f"{r['uc']}/1" if r['uc'] is not None else "sem lucro"
        faixas_str += (
            f"  Preco R${p:.2f}:\n"
            f"    Custo do produto: R${custo:.2f}\n"
            f"    Custo operacional: R${custo_operacional:.2f}\n"
            f"    Comissao do Mercado Livre ({modalidade}): R${r['comissao']:.2f}\n"
            f"    Frete (peso taxado {peso_taxado:.2f}kg): R${r['frete']:.2f}\n"
            f"    Nota fiscal ({nf_pct*100:.1f}%): R${r['nf']:.2f}\n"
            f"    Lucro bruto (preco - comissao - frete): R${r['lucro_bruto']:.2f}\n"
            f"    Lucro liquido (depois de TODOS os custos acima): R${r['lucro_liquido']:.2f}\n"
            f"    Margem liquida: {r['margem']:.1f}%\n"
            f"    UC (lucro liquido / LPV): {uc_str}\n\n"
        )

    dims_str = f"{dims_ref[0]}x{dims_ref[1]}x{dims_ref[2]}cm (produto embalado)" if any(d > 0 for d in dims_ref) else "nao informado"
    lpv_str = f"R${lpv:.2f} (origem: {lpv_origem})" if lpv else "nao disponivel (sem dados financeiros ainda)"

    prompt = f"""Voce e um especialista em viabilidade de produtos para Mercado Livre, escrevendo
para a equipe operacional de uma empresa (colaboradores que NAO sao da area financeira).

PRODUTO: {nome}
Quantidade: {qtd_ref} unidade(s)
Medidas (produto embalado): {dims_str}
Custo do produto: R${custo:.2f}
Custo operacional (embalagem/logistica/ADS/cross docking): R${custo_operacional:.2f}
Modalidade: {modalidade}
Nota fiscal: {nf_pct*100:.1f}% (aliquota vigente da empresa)
LPV (meta de lucro por venda pra cobrir custo fixo): {lpv_str}
Preco de mercado informado pelo usuario (pesquisa manual): R${preco_mercado:.2f}

CALCULO EXATO JA FEITO (use estes numeros EXATAMENTE como estao -- nao recalcule
nem estime comissao, frete, NF ou qualquer valor por conta propria; eles ja vieram
calculados certos, inclusive o frete, que segue a regra oficial do Mercado Livre
-- maior valor entre peso fisico e peso cubado (altura x largura x profundidade / 6000)):

{faixas_str}

REGRA DE APROVACAO (definida pela empresa, USE COMO CORTE RIGIDO):
UC minimo para aprovar o produto = {UC_MINIMO}/1
- VIAVEL: UC >= 1,0/1 (a venda cobre a meta de lucro com folga)
- VIAVEL COM RESSALVAS: UC entre {UC_MINIMO}/1 e 1,0/1 (a venda ajuda mas nao cobre tudo sozinha)
- INVIAVEL: UC abaixo de {UC_MINIMO}/1 (nao aprova)

LINGUAGEM -- MUITO IMPORTANTE:
Escreva em portugues simples e direto, como se estivesse explicando pra um colega de
equipe que nunca trabalhou com financeiro. NAO use jargao sem explicar. Toda vez que
usar um termo tecnico (UC, margem, LPV), explique em 1 frase simples o que ele significa
na pratica, tipo "essa venda ajuda a pagar X% da meta do mes" em vez de so falar "UC de
0,8/1". O objetivo e que a pessoa ENTENDA o motivo da decisao, nao so veja um veredicto
e concorde sem saber por que. Evite tabelas cheias de termos financeiros sem contexto --
prefira frases curtas explicando cada numero.

ESTRUTURE ASSIM:
1. VEREDICTO: [VIAVEL / VIAVEL COM RESSALVAS / INVIAVEL] -- 1 frase simples explicando o motivo
2. PRECO SUGERIDO: R$X,XX -- por que esse preco
3. DETALHAMENTO DOS CUSTOS: liste cada custo SEPARADO (produto, operacional, comissao ML,
   frete, nota fiscal) em linguagem simples, cada um numa linha, explicando o que e
4. LUCRO E O QUE ISSO SIGNIFICA: quanto sobra por venda e se isso e suficiente pra ajudar
   a pagar as contas da empresa (explicando o UC de forma simples, sem so citar o numero)
5. E SE PRECISAR DAR DESCONTO: o que acontece nos cenarios de -10% e +10%, em linguagem simples
6. ALERTAS: qualquer risco (ex: frete pode mudar se a medida embalada estiver errada)
7. RECOMENDACAO FINAL: 2-3 linhas resumindo pra quem só quer saber "pode vender ou não"
"""

    client = anthropic.Anthropic(api_key=API_KEY_CLAUDE)
    msg = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=1200,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text

# ── INTERFACE ──────────────────────────────────────────────────────────────────

st.title("MartinSousa App")

with st.sidebar:
    st.header("MartinSousa App")
    st.caption("v9.0")
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
            veredicto = gerar_veredicto(
                preco_mercado, custo, peso_taxado, categoria, modalidade,
                nome_produto, dims_ref, qtd_ref, nf_pct_usado, custo_operacional,
                lpv_usado, lpv_origem_usada,
            )

        st.markdown("---")
        st.subheader("Resultado da Analise")
        if "INVIAVEL" in veredicto.upper() and "RESSALVAS" not in veredicto.upper():
            st.error(veredicto)
        elif "RESSALVAS" in veredicto.upper():
            st.warning(veredicto)
        else:
            st.success(veredicto)
