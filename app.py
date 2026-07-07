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
    return preco * taxas[1]

def calcular_viabilidade(preco_venda, custo, peso_taxado_kg, categoria):
    comissao = calcular_comissao_ml(preco_venda, categoria)
    frete    = calcular_frete_ml(preco_venda, peso_taxado_kg)
    nf       = preco_venda * NF_OFICIAL
    lpv      = LPV_OFICIAL
    lucro    = preco_venda - (custo + comissao + frete + nf + lpv)
    margem   = (lucro / preco_venda * 100) if preco_venda > 0 else 0
    uc       = round(lpv / lucro, 1) if lucro > 0 else None
    return {'preco': preco_venda, 'custo': custo, 'comissao': comissao,
            'frete': frete, 'nf': nf, 'lpv': lpv, 'lucro': lucro, 'margem': margem, 'uc': uc}

def buscar_por_foto(imagem_bytes, serpapi_key):
    try:
        img_b64 = base64.b64encode(imagem_bytes).decode()
        resp = requests.post(
            "https://serpapi.com/search",
            data={"engine": "google_lens", "api_key": serpapi_key,
                  "image_content": img_b64, "country": "br", "hl": "pt"},
            timeout=30
        )
        data = resp.json()
        return data.get("visual_matches", []), None
    except Exception as e:
        return [], str(e)

def filtrar_por_plataforma(visual_matches):
    ml_links, outros = [], {}
    for item in visual_matches:
        source = item.get("source", "").lower()
        price  = item.get("price", {})
        preco  = price.get("extracted_value") if price else None
        link   = item.get("link", "")
        titulo = item.get("title", "")
        if "mercadolivre" in source or "mercado livre" in source:
            if link:
                ml_links.append({"link": link, "title": titulo, "preco_lens": preco})
        elif preco:
            plat = source.split(".")[0].capitalize()
            outros.setdefault(plat, []).append(preco)
    return ml_links, outros

def obter_token_ml(client_id, client_secret):
    resp = requests.post(
        "https://api.mercadolibre.com/oauth/token",
        data={"grant_type": "client_credentials",
              "client_id": client_id, "client_secret": client_secret},
        timeout=10
    )
    return resp.json().get("access_token")

def extrair_item_id(link):
    match = re.search(r'MLB-?(\d+)', link)
    return f"MLB{match.group(1)}" if match else None

def buscar_anuncio(item_id, token):
    try:
        r = requests.get(f"https://api.mercadolibre.com/items/{item_id}",
                         headers={"Authorization": f"Bearer {token}"}, timeout=10)
        return r.json()
    except:
        return None

def extrair_medidas(anuncio):
    medidas = []
    titulo = anuncio.get("title", "")
    for m in re.findall(r'(\d+)\s*[xX]\s*(\d+)', titulo):
        medidas.append((int(m[0]), int(m[1])))
    for attr in anuncio.get("attributes", []):
        nome  = attr.get("name", "").lower()
        valor = attr.get("value_name", "") or ""
        if any(p in nome for p in ["comprimento", "largura", "dimensao", "tamanho", "medida"]):
            nums = re.findall(r'\d+', valor)
            if len(nums) >= 2:
                medidas.append((int(nums[0]), int(nums[1])))
    return medidas

def medida_compativel(medidas, largura_ref, comprimento_ref, tolerancia=2):
    if not medidas:
        return False
    ref = sorted([largura_ref, comprimento_ref])
    for m in medidas:
        if len(m) >= 2:
            vals = sorted(m[:2])
            if abs(vals[0]-ref[0]) <= tolerancia and abs(vals[1]-ref[1]) <= tolerancia:
                return True
    return False

def preco_promocional(anuncio):
    sp = anuncio.get("sale_price")
    if sp and sp.get("amount"):
        return float(sp["amount"])
    return float(anuncio.get("price", 0))

def processar_anuncios_ml(ml_links, token, largura, comprimento):
    validos, sem_medida, descartados = [], [], []
    for item_link in ml_links[:20]:
        item_id = extrair_item_id(item_link["link"])
        if not item_id:
            continue
        anuncio = buscar_anuncio(item_id, token)
        if not anuncio:
            continue
        medidas = extrair_medidas(anuncio)
        preco   = preco_promocional(anuncio)
        vendas  = anuncio.get("sold_quantity", 0)
        titulo  = anuncio.get("title", "")
        if not medidas:
            sem_medida.append({"titulo": titulo, "preco": preco})
        elif medida_compativel(medidas, largura, comprimento):
            validos.append({"titulo": titulo, "preco": preco, "vendas": vendas})
        else:
            descartados.append({"titulo": titulo, "preco": preco})
    return validos, sem_medida, descartados

def gerar_veredicto(resultado, anuncios, outros_precos, api_key, nome, largura, comprimento):
    com_vendas = [a for a in anuncios if a["vendas"] > 0]
    sem_vendas = [a for a in anuncios if a["vendas"] == 0]
    precos_com = [a["preco"] for a in com_vendas]
    precos_sem = [a["preco"] for a in sem_vendas]

    alerta = ""
    if precos_com and len(precos_com) > 1:
        variacao = max(precos_com) / min(precos_com)
        if variacao > 1.5:
            alerta = f"ALERTA: Variacao de preco elevada ({((variacao-1)*100):.0f}%) entre R${min(precos_com):.2f} e R${max(precos_com):.2f}. Investigue se ha tamanhos ou materiais diferentes misturados. Explique isso no veredicto."

    outros_str = "\n".join([f"- {p}: media R${sum(v)/len(v):.2f} ({len(v)} anuncios)"
                             for p, v in outros_precos.items()]) or "Nao encontrado"

    prompt = f"""Voce e um especialista em viabilidade de produtos para Mercado Livre.

PRODUTO: {nome} ({largura:.0f}x{comprimento:.0f}cm)

DADOS FINANCEIROS:
- Preco de venda: R${resultado['preco']:.2f}
- Custo: R${resultado['custo']:.2f}
- Comissao ML Premium: R${resultado['comissao']:.2f}
- Frete: R${resultado['frete']:.2f}
- NF (10%): R${resultado['nf']:.2f}
- LPV: R${resultado['lpv']:.2f}
- Lucro: R${resultado['lucro']:.2f}
- Margem: {resultado['margem']:.1f}%
- Unidade de contribuicao: 1/{resultado['uc']}

MERCADO (medida {largura:.0f}x{comprimento:.0f}cm confirmada):
- COM vendas: {len(com_vendas)} anuncios | R${min(precos_com):.2f} a R${max(precos_com):.2f}
- SEM vendas: {len(sem_vendas)} anuncios | R${min(precos_sem):.2f} a R${max(precos_sem):.2f}

OUTROS CANAIS:
{outros_str}

{alerta}

Responda em portugues com:
1. Veredicto: VIAVEL / VIAVEL COM RESSALVAS / INVIAVEL
2. Justificativa objetiva (3-4 linhas)
3. Preco ideal recomendado
4. Se houver alerta de variacao, explique a causa provavel
"""
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=600,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text, com_vendas, sem_vendas

st.title("Analise de Viabilidade - Mercado Livre")
st.markdown("---")

with st.sidebar:
    st.header("Configuracoes")
    api_key_claude = st.text_input("Chave API Claude", type="password")
    ml_client_id   = st.text_input("ML Client ID")
    ml_secret      = st.text_input("ML Client Secret", type="password")
    serpapi_key    = st.text_input("Chave SerpApi", type="password")
    st.markdown("---")
    st.caption("MartinSousa App v2.0")

col1, col2 = st.columns(2)
with col1:
    st.subheader("Dados do Produto")
    foto         = st.file_uploader("Foto do produto", type=["jpg","jpeg","png","webp"])
    nome_produto = st.text_input("Nome do produto")
    custo        = st.number_input("Preco de custo (R$)", min_value=0.0, step=0.50, format="%.2f")
    preco_venda  = st.number_input("Preco de venda pretendido (R$)", min_value=0.0, step=0.50, format="%.2f")
    categoria    = st.selectbox("Categoria no ML", sorted(ML_COMISSAO_POR_CATEGORIA.keys()))

with col2:
    st.subheader("Dimensoes e Peso")
    peso_real   = st.number_input("Peso real (kg)", min_value=0.0, step=0.05, format="%.3f")
    altura      = st.number_input("Altura (cm)", min_value=0.0, step=0.5)
    largura     = st.number_input("Largura (cm)", min_value=0.0, step=0.5)
    comprimento = st.number_input("Comprimento (cm)", min_value=0.0, step=0.5)
    if foto:
        st.image(foto, caption="Foto enviada", use_container_width=True)

st.markdown("---")
analisar = st.button("Analisar Viabilidade", type="primary", use_container_width=True)

if analisar:
    erros = []
    if not foto:           erros.append("Foto do produto")
    if not nome_produto:   erros.append("Nome do produto")
    if not custo:          erros.append("Preco de custo")
    if not preco_venda:    erros.append("Preco de venda")
    if not largura or not comprimento: erros.append("Largura e Comprimento")
    if not api_key_claude: erros.append("Chave API Claude")
    if not ml_client_id:   erros.append("ML Client ID")
    if not ml_secret:      erros.append("ML Client Secret")
    if not serpapi_key:    erros.append("Chave SerpApi")

    if erros:
        st.warning(f"Preencha: {', '.join(erros)}")
    else:
        peso_taxado = calcular_peso_taxado(peso_real, altura, largura, comprimento)
        resultado   = calcular_viabilidade(preco_venda, custo, peso_taxado, categoria)

        with st.spinner("Buscando produto por foto no Google Lens..."):
            imagem_bytes = foto.read()
            visual_matches, erro = buscar_por_foto(imagem_bytes, serpapi_key)

        if erro:
            st.error(f"Erro Google Lens: {erro}")
            st.stop()

        ml_links, outros_precos = filtrar_por_plataforma(visual_matches)
        st.success(f"Google Lens: {len(visual_matches)} resultados - {len(ml_links)} no ML")

        with st.spinner("Acessando anuncios e validando medidas..."):
            token = obter_token_ml(ml_client_id, ml_secret)
            validos, sem_medida, descartados = processar_anuncios_ml(ml_links, token, largura, comprimento)

        st.info(f"{len(validos)} anuncios confirmados ({largura:.0f}x{comprimento:.0f}cm) | "
                f"{len(sem_medida)} sem medida (descartados) | {len(descartados)} tamanho diferente (descartados)")

        st.markdown("---")
        st.subheader(f"Viabilidade - {nome_produto} ({largura:.0f}x{comprimento:.0f}cm)")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Custo", f"R${resultado['custo']:.2f}")
        c2.metric("Comissao ML", f"R${resultado['comissao']:.2f}")
        c3.metric("Frete", f"R${resultado['frete']:.2f}")
        c4.metric("NF (10%)", f"R${resultado['nf']:.2f}")

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("LPV", f"R${resultado['lpv']:.2f}")
        c6.metric("Lucro", f"R${resultado['lucro']:.2f}")
        c7.metric("Margem", f"{resultado['margem']:.1f}%")
        c8.metric("UC", f"1/{resultado['uc']}" if resultado['uc'] else "-")
        st.caption(f"Peso taxado: {peso_taxado:.3f} kg")

        if outros_precos:
            st.markdown("---")
            st.subheader("Outros canais (referencia de mercado)")
            cols = st.columns(len(outros_precos))
            for i, (plat, precos) in enumerate(outros_precos.items()):
                cols[i].metric(plat, f"R${sum(precos)/len(precos):.2f}", f"{len(precos)} anuncio(s)")

        if validos:
            with st.spinner("Gerando veredicto com IA..."):
                veredicto, com_vendas, sem_vendas = gerar_veredicto(
                    resultado, validos, outros_precos,
                    api_key_claude, nome_produto, largura, comprimento
                )
            st.markdown("---")
            st.subheader("Veredicto")
            if "RESSALVAS" in veredicto:
                st.warning(veredicto)
            elif "INVIAVEL" in veredicto or "INVIAVEL" in veredicto:
                st.error(veredicto)
            else:
                st.success(veredicto)

            with st.expander("Ver anuncios analisados"):
                if com_vendas:
                    st.markdown("**Com vendas:**")
                    for a in com_vendas:
                        st.write(f"- {a['titulo']} - R${a['preco']:.2f} | {a['vendas']} vendas")
                if sem_vendas:
                    st.markdown("**Sem vendas:**")
                    for a in sem_vendas:
                        st.write(f"- {a['titulo']} - R${a['preco']:.2f}")
        else:
            st.warning("Nenhum anuncio com medida confirmada encontrado. Tente outra foto ou verifique as dimensoes.")