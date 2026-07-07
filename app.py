import streamlit as st
import requests
import anthropic
import base64
import re
from parametros_oficiais import (
    LPV_OFICIAL, NF_OFICIAL,
    ML_FAIXAS_PRECO, ML_FRETE_TABELA, ML_COMISSAO_POR_CATEGORIA,
)

st.set_page_config(page_title="MartinSousa - Analise de Viabilidade", layout="wide")

API_KEY_CLAUDE   = st.secrets.get("ANTHROPIC_API_KEY", "")
ML_CLIENT_ID     = st.secrets.get("ML_CLIENT_ID", "")
ML_CLIENT_SECRET = st.secrets.get("ML_CLIENT_SECRET", "")
SERPAPI_KEY      = st.secrets.get("SERPAPI_KEY", "")
ML_ACCESS_TOKEN  = st.secrets.get("ML_ACCESS_TOKEN", "")

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

def calcular_resultado(preco, custo, peso_kg, categoria, modalidade):
    comissao = calcular_comissao_ml(preco, categoria, modalidade)
    frete    = calcular_frete_ml(preco, peso_kg)
    nf       = preco * NF_OFICIAL
    lpv      = LPV_OFICIAL
    lucro    = preco - (custo + comissao + frete + nf + lpv)
    margem   = (lucro / preco * 100) if preco > 0 else 0
    uc       = round(lpv / lucro, 1) if lucro > 0 else None
    return {'preco': preco, 'custo': custo, 'comissao': comissao,
            'frete': frete, 'nf': nf, 'lpv': lpv, 'lucro': lucro,
            'margem': margem, 'uc': uc}

# ── IMGUR ──────────────────────────────────────────────────────────────────────

def hospedar_imgur(imagem_bytes):
    try:
        img_b64 = base64.b64encode(imagem_bytes).decode()
        resp = requests.post(
            "https://api.imgur.com/3/image",
            headers={"Authorization": "Client-ID 546c25a59c58ad7"},
            data={"image": img_b64, "type": "base64"},
            timeout=20
        )
        data = resp.json()
        if data.get("success"):
            return data["data"]["link"], None
        return None, data.get("data", {}).get("error", "Erro Imgur")
    except Exception as e:
        return None, str(e)

# ── GOOGLE LENS ────────────────────────────────────────────────────────────────

def buscar_por_foto(url_imagem):
    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={
                "engine": "google_lens",
                "api_key": SERPAPI_KEY,
                "url": url_imagem,
                "country": "br",
                "hl": "pt",
                "type": "visual_matches"
            },
            timeout=30
        )
        data = resp.json()
        if "error" in data:
            return [], data["error"]
        return data.get("visual_matches", []), None
    except Exception as e:
        return [], str(e)

MARKETPLACES_ACEITOS = {
    "shopee": "Shopee",
    "amazon": "Amazon",
    "magazineluiza": "Magazine Luiza",
    "magazinevoce": "Magazine Luiza",
    "carrefour": "Carrefour",
    "casasbahia": "Casas Bahia",
    "americanas": "Americanas",
    "submarino": "Americanas",
    "shoptime": "Americanas",
    "extra": "Extra",
    "pontofrio": "Ponto Frio",
}

def separar_resultados(visual_matches):
    ml_resultados, outros = [], {}
    for item in visual_matches:
        source = item.get("source", "").lower()
        link   = item.get("link", "")
        titulo = item.get("title", "")
        thumb  = item.get("thumbnail", "")
        price  = item.get("price", {})
        preco  = price.get("extracted_value") if price else None

        if "mercadolivre.com.br" in source or "mercadolivre.com.br" in link.lower():
            match = re.search(r'MLB-?(\d+)', link)
            if match:
                item_id = f"MLB{match.group(1)}"
                ml_resultados.append({
                    "item_id": item_id,
                    "titulo": titulo,
                    "thumbnail": thumb,
                    "link": link,
                    "preco_lens": preco
                })
        elif preco:
            for dominio, nome in MARKETPLACES_ACEITOS.items():
                if dominio in source or dominio in link.lower():
                    outros.setdefault(nome, []).append(preco)
                    break
    return ml_resultados, outros

# ── MERCADO LIVRE API ──────────────────────────────────────────────────────────

def obter_token_ml():
    if ML_ACCESS_TOKEN:
        return ML_ACCESS_TOKEN
    resp = requests.post(
        "https://api.mercadolibre.com/oauth/token",
        data={"grant_type": "client_credentials",
              "client_id": ML_CLIENT_ID, "client_secret": ML_CLIENT_SECRET},
        timeout=10
    )
    return resp.json().get("access_token")

def buscar_anuncio_ativo(item_id, token):
    """Busca anuncio pelo ID. Se retornar erro, tenta busca por titulo no ML."""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.get(
            f"https://api.mercadolibre.com/items/{item_id}",
            headers=headers,
            params={"include_attributes": "all"},
            timeout=10
        )
        data = r.json()
        if "error" in data or data.get("status") in [404, 403]:
            return None
        return data
    except:
        return None

def buscar_anuncios_ativos_por_texto(query, token, limit=20):
    """Busca anuncios ATIVOS no ML por texto — retorna sold_quantity real."""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.get(
            "https://api.mercadolibre.com/sites/MLB/search",
            params={"q": query, "limit": limit, "status": "active"},
            headers=headers,
            timeout=15
        )
        return r.json().get("results", [])
    except:
        return []

def preco_promocional(anuncio):
    sp = anuncio.get("sale_price")
    if sp and sp.get("amount"):
        return float(sp["amount"])
    return float(anuncio.get("price", 0))

# ── VEREDICTO IA ───────────────────────────────────────────────────────────────

def gerar_veredicto(anuncios_selecionados, outros_precos, custo, peso_taxado, categoria, modalidade, nome, dims_ref, qtd_ref):
    com_vendas = [a for a in anuncios_selecionados if a.get("vendas", 0) > 0]
    sem_vendas = [a for a in anuncios_selecionados if a.get("vendas", 0) == 0]
    precos_com = sorted([a["preco"] for a in com_vendas])
    precos_sem = sorted([a["preco"] for a in sem_vendas])

    faixas_str = ""
    if precos_com:
        for p in sorted(set([round(p, 2) for p in precos_com])):
            r = calcular_resultado(p, custo, peso_taxado, categoria, modalidade)
            faixas_str += f"  R${p:.2f} -> lucro R${r['lucro']:.2f} | margem {r['margem']:.1f}% | UC 1/{r['uc']}\n"

    outros_str = "\n".join([f"- {p}: media R${sum(v)/len(v):.2f} ({len(v)} anuncios)"
                             for p, v in outros_precos.items()]) or "Nao encontrado"

    alerta_variacao = ""
    if precos_com and len(precos_com) > 1:
        variacao = max(precos_com) / min(precos_com)
        if variacao > 1.5:
            alerta_variacao = f"ATENCAO: variacao de preco de {((variacao-1)*100):.0f}% detectada. Investigue se ha tamanhos ou quantidades diferentes misturados."

    dims_str = f"{dims_ref[0]}x{dims_ref[1]}x{dims_ref[2]}cm" if any(d > 0 for d in dims_ref) else "nao informado"

    prompt = f"""Voce e um especialista em viabilidade de produtos para Mercado Livre.

PRODUTO: {nome}
Quantidade: {qtd_ref} unidade(s)
Medidas: {dims_str}
Custo: R${custo:.2f}
Modalidade: {modalidade}
LPV necessario: R${LPV_OFICIAL:.2f}

ANUNCIOS COM VENDAS ({len(com_vendas)} selecionados e confirmados):
{"Faixa: R$" + f"{min(precos_com):.2f}" + " a R$" + f"{max(precos_com):.2f}" if precos_com else "Nenhum com vendas"}

CALCULO POR FAIXA:
{faixas_str}

ANUNCIOS SEM VENDAS ({len(sem_vendas)} selecionados):
{f'Faixa: R${min(precos_sem):.2f} a R${max(precos_sem):.2f}' if precos_sem else 'Nenhum'}

OUTROS CANAIS:
{outros_str}

{alerta_variacao}

REGRAS RIGIDAS:
1. UC MINIMO ABSOLUTO: 6/1. Se UC abaixo de 6/1, veredicto e INVIAVEL sem excecao.
2. So sugira preco com UC >= 6/1. Se impossivel no mercado, declare INVIAVEL.
3. Margem para promocao: acima 10% OTIMO, 3-10% OK, abaixo 3% SEM MARGEM.
4. Se margem abaixo 10%, alerte sobre esforco operacional.
5. Se inviavel unitario mas kits possiveis, sugira kit.

CENARIOS:
- VIAVEL: UC >= 6/1 + margem promocao acima 10%
- VIAVEL COM RESSALVAS: UC 6/1 a 8/1 OU promocao 3-10%
- INVIAVEL: UC abaixo 6/1 em qualquer preco do mercado

ESTRUTURE ASSIM:
1. VEREDICTO: [VIAVEL / VIAVEL COM RESSALVAS / INVIAVEL]
2. PRECO SUGERIDO: R$X,XX
3. CALCULO: custo | comissao | frete | nf | lpv | lucro | margem | UC
4. ANALISE DE PROMOCAO
5. ANALISE DE MERCADO
6. ALERTAS
7. RECOMENDACAO FINAL: 2-3 linhas
"""

    client = anthropic.Anthropic(api_key=API_KEY_CLAUDE)
    msg = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text

# ── INTERFACE ──────────────────────────────────────────────────────────────────

st.title("Analise de Viabilidade - Mercado Livre")
st.markdown("---")

with st.sidebar:
    st.header("MartinSousa App")
    st.caption("v5.0")
    st.markdown("---")
    modalidade = st.selectbox("Modalidade ML", ["Premium", "Classico"])
    st.markdown("---")
    st.caption("Chaves configuradas automaticamente")

col1, col2 = st.columns(2)
with col1:
    st.subheader("Dados do Produto")
    foto         = st.file_uploader("Foto do produto", type=["jpg","jpeg","png","webp"])
    nome_produto = st.text_input("Nome do produto")
    custo        = st.number_input("Preco de custo (R$)", min_value=0.0, value=None, step=0.50, format="%.2f", placeholder="0,00")
    qtd_ref      = st.number_input("Quantidade por unidade/kit", min_value=1, step=1, value=1)
    categoria    = st.selectbox("Categoria no ML", sorted(ML_COMISSAO_POR_CATEGORIA.keys()))

with col2:
    st.subheader("Dimensoes e Peso")
    col_peso, col_unit = st.columns([3,1])
    peso_val  = col_peso.number_input("Peso", min_value=0.0, value=None, step=1.0, format="%.0f", placeholder="ex: 700")
    peso_unit = col_unit.selectbox("", ["g", "kg"], label_visibility="hidden")
    peso_kg   = (peso_val / 1000 if peso_val else 0) if peso_unit == "g" else (peso_val or 0)
    st.caption("Informe as 3 medidas — o sistema identifica automaticamente")
    dim1 = st.number_input("Medida 1 (cm)", min_value=0.0, value=None, step=0.5, format="%.1f", placeholder="ex: 30")
    dim2 = st.number_input("Medida 2 (cm)", min_value=0.0, value=None, step=0.5, format="%.1f", placeholder="ex: 30")
    dim3 = st.number_input("Medida 3 (cm)", min_value=0.0, value=None, step=0.5, format="%.1f", placeholder="ex: 2")
    dims_ref = [dim1 or 0, dim2 or 0, dim3 or 0]
    if foto:
        st.image(foto, caption="Foto enviada", use_container_width=True)

st.markdown("---")

# ETAPA 1: Buscar por foto
if "ml_resultados" not in st.session_state:
    st.session_state.ml_resultados = []
if "outros_precos" not in st.session_state:
    st.session_state.outros_precos = {}
if "etapa" not in st.session_state:
    st.session_state.etapa = 1

buscar = st.button("🔍 Buscar por foto", type="primary", use_container_width=True)

if buscar:
    if not foto or not nome_produto or not custo:
        st.warning("Preencha foto, nome do produto e custo.")
    else:
        with st.spinner("Hospedando imagem..."):
            imagem_bytes = foto.read()
            url_imagem, erro = hospedar_imgur(imagem_bytes)
        if erro:
            st.error(f"Erro Imgur: {erro}")
            st.stop()

        with st.spinner("Buscando no Google Lens..."):
            matches, erro = buscar_por_foto(url_imagem)
        if erro:
            st.error(f"Erro Google Lens: {erro}")
            st.stop()

        ml_resultados, outros_precos = separar_resultados(matches)
        st.session_state.ml_resultados = ml_resultados
        st.session_state.outros_precos = outros_precos
        st.session_state.etapa = 2
        st.rerun()

# ETAPA 2: Confirmacao visual
if st.session_state.etapa >= 2 and st.session_state.ml_resultados:
    st.markdown("---")
    st.subheader("Selecione os anuncios que sao o mesmo produto")
    st.caption(f"{len(st.session_state.ml_resultados)} anuncios encontrados no ML — marque apenas os corretos")

    selecionados_ids = []
    cols_por_linha = 4
    resultados = st.session_state.ml_resultados[:20]

    for i in range(0, len(resultados), cols_por_linha):
        cols = st.columns(cols_por_linha)
        for j, item in enumerate(resultados[i:i+cols_por_linha]):
            with cols[j]:
                if item["thumbnail"]:
                    st.image(item["thumbnail"], use_container_width=True)
                preco_str = f"R${item['preco_lens']:.2f}" if item['preco_lens'] else "Sem preço"
                titulo_curto = item["titulo"][:50] + "..." if len(item["titulo"]) > 50 else item["titulo"]
                selecionado = st.checkbox(
                    f"{titulo_curto}\n{preco_str}",
                    key=f"sel_{item['item_id']}"
                )
                if selecionado:
                    selecionados_ids.append(item["item_id"])

    st.markdown("---")
    analisar = st.button(
        f"📊 Analisar {len(selecionados_ids)} anuncio(s) selecionado(s)",
        type="primary",
        use_container_width=True,
        disabled=len(selecionados_ids) == 0
    )

    if analisar and selecionados_ids:
        peso_taxado = calcular_peso_taxado(peso_kg, dim1 or 0, dim2 or 0, dim3 or 0)
        token = obter_token_ml()

        with st.spinner("Buscando dados dos anuncios selecionados..."):
            anuncios_dados = []
            for item_id in selecionados_ids:
                anuncio = buscar_anuncio_ativo(item_id, token)
                if anuncio:
                    preco  = preco_promocional(anuncio)
                    vendas = anuncio.get("sold_quantity", 0)
                    titulo = anuncio.get("title", "")
                    anuncios_dados.append({
                        "item_id": item_id,
                        "titulo": titulo,
                        "preco": preco,
                        "vendas": vendas
                    })

        if st.session_state.outros_precos:
            st.subheader("Outros canais (referencia)")
            cols = st.columns(len(st.session_state.outros_precos))
            for i, (plat, precos) in enumerate(st.session_state.outros_precos.items()):
                cols[i].metric(plat, f"R${sum(precos)/len(precos):.2f}", f"{len(precos)} anuncio(s)")

        with st.spinner("Gerando analise com IA..."):
            veredicto = gerar_veredicto(
                anuncios_dados, st.session_state.outros_precos,
                custo, peso_taxado, categoria, modalidade,
                nome_produto, dims_ref, qtd_ref
            )

        st.markdown("---")
        st.subheader("Resultado da Analise")
        if "INVIAVEL" in veredicto.upper():
            st.error(veredicto)
        elif "RESSALVAS" in veredicto.upper():
            st.warning(veredicto)
        else:
            st.success(veredicto)

        with st.expander("Ver anuncios analisados"):
            for a in anuncios_dados:
                st.write(f"- {a['titulo']} — R${a['preco']:.2f} | {a['vendas']} vendas")
