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

# ── GOOGLE LENS (apenas outros canais) ────────────────────────────────────────

def buscar_outros_canais(url_imagem):
    MARKETPLACES_ACEITOS = {
        "shopee": "Shopee", "amazon": "Amazon",
        "magazineluiza": "Magazine Luiza", "magazinevoce": "Magazine Luiza",
        "carrefour": "Carrefour", "casasbahia": "Casas Bahia",
        "americanas": "Americanas", "submarino": "Americanas",
        "extra": "Extra", "pontofrio": "Ponto Frio",
    }
    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={"engine": "google_lens", "api_key": SERPAPI_KEY,
                    "url": url_imagem, "country": "br", "hl": "pt",
                    "type": "visual_matches"},
            timeout=30
        )
        outros = {}
        for item in resp.json().get("visual_matches", []):
            source = item.get("source", "").lower()
            link   = item.get("link", "").lower()
            price  = item.get("price", {})
            preco  = price.get("extracted_value") if price else None
            if "mercadolivre.com.br" in source or "mercadolivre.com.br" in link:
                continue
            if preco:
                for dominio, nome in MARKETPLACES_ACEITOS.items():
                    if dominio in source or dominio in link:
                        outros.setdefault(nome, []).append(preco)
                        break
        return outros
    except:
        return {}

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

def buscar_anuncios_ml(query, token, limit=30):
    try:
        r = requests.get(
            "https://api.mercadolibre.com/sites/MLB/search",
            params={"q": query, "limit": limit},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15
        )
        return r.json().get("results", [])
    except:
        return []

def buscar_detalhes_anuncio(item_id, token):
    try:
        r = requests.get(
            f"https://api.mercadolibre.com/items/{item_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"include_attributes": "all"},
            timeout=10
        )
        data = r.json()
        if "error" in data:
            return None
        return data
    except:
        return None

def extrair_medidas_texto(texto):
    """Extrai medidas de qualquer texto (titulo, descricao, atributos)."""
    medidas = []
    for m in re.findall(r'(\d+[.,]?\d*)\s*[xX×]\s*(\d+[.,]?\d*)', texto):
        medidas.append((float(m[0].replace(',','.')), float(m[1].replace(',','.'))))
    return medidas

def medida_compativel(medidas, dims_ref, tolerancia=2.0):
    if not dims_ref or all(d == 0 for d in dims_ref):
        return True, "sem_filtro"
    dims_validas = [d for d in dims_ref if d > 0]
    if not medidas:
        return False, "sem_medida"
    ref = sorted(dims_validas[:2])
    for m in medidas:
        ms = sorted(m[:2])
        if len(ref) >= 2:
            if abs(ms[0]-ref[0]) <= tolerancia and abs(ms[1]-ref[1]) <= tolerancia:
                return True, "compativel"
        elif len(ref) == 1:
            if any(abs(v-ref[0]) <= tolerancia for v in ms):
                return True, "compativel"
    return False, "incompativel"

def verificar_medidas_anuncio(anuncio, dims_ref):
    """Verifica medidas em titulo, atributos e descricao."""
    titulo = anuncio.get("title", "")
    descricao = anuncio.get("description", "") or ""

    # 1. Titulo
    medidas = extrair_medidas_texto(titulo)
    ok, status = medida_compativel(medidas, dims_ref)
    if status == "compativel":
        return True, "titulo"
    if status == "incompativel":
        return False, "titulo_incompativel"

    # 2. Atributos
    for attr in anuncio.get("attributes", []):
        nome  = attr.get("name", "").lower()
        valor = attr.get("value_name", "") or ""
        if any(p in nome for p in ["comprimento", "largura", "dimensao", "tamanho", "medida", "altura"]):
            medidas = extrair_medidas_texto(valor)
            if not medidas:
                nums = re.findall(r'\d+[.,]?\d*', valor)
                if nums:
                    medidas = [(float(nums[0].replace(',','.')), float(nums[0].replace(',','.')))]
            ok, status = medida_compativel(medidas, dims_ref)
            if status == "compativel":
                return True, "atributos"
            if status == "incompativel":
                return False, "atributos_incompativel"

    # 3. Descricao
    if descricao:
        medidas = extrair_medidas_texto(descricao)
        ok, status = medida_compativel(medidas, dims_ref)
        if status == "compativel":
            return True, "descricao"
        if status == "incompativel":
            return False, "descricao_incompativel"

    return False, "sem_medida_encontrada"

def preco_promocional(anuncio):
    sp = anuncio.get("sale_price")
    if sp and sp.get("amount"):
        return float(sp["amount"])
    return float(anuncio.get("price", 0))

# ── ANALISE VISUAL CLAUDE ──────────────────────────────────────────────────────

def confirmar_produto_visualmente(fotos_referencia_b64, fotos_anuncio_urls, titulo_anuncio):
    """Claude compara fotos de referencia com todas as fotos do anuncio."""
    try:
        content = []

        # Fotos de referencia
        content.append({"type": "text", "text": f"FOTOS DE REFERENCIA DO PRODUTO ({len(fotos_referencia_b64)} imagens):"})
        for i, img_b64 in enumerate(fotos_referencia_b64[:4]):
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}
            })

        # Fotos do anuncio
        content.append({"type": "text", "text": f"\nFOTOS DO ANUNCIO ML '{titulo_anuncio}' ({len(fotos_anuncio_urls)} imagens):"})
        for url in fotos_anuncio_urls[:6]:
            try:
                r = requests.get(url, timeout=8)
                if r.status_code == 200:
                    img_data = base64.b64encode(r.content).decode()
                    content.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": img_data}
                    })
            except:
                pass

        content.append({"type": "text", "text": """
Analise as imagens e responda APENAS com JSON no formato:
{"confirmado": true/false, "motivo": "explicacao curta"}

Confirme como o MESMO PRODUTO se:
- Tipo/categoria identico (ex: album de fotos = album de fotos, nao caderno)
- Material visualmente compativel (capa dura, espiral metalico, etc)
- Estilo geral compativel

Rejeite se:
- Tipo diferente (caderno, sketchbook, agenda vs album de fotos)
- Material claramente diferente
- Produto completamente diferente
"""})

        client = anthropic.Anthropic(api_key=API_KEY_CLAUDE)
        msg = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=100,
            messages=[{"role": "user", "content": content}]
        )
        texto = msg.content[0].text.strip()
        import json
        resultado = json.loads(texto)
        return resultado.get("confirmado", False), resultado.get("motivo", "")
    except:
        return True, "erro na analise visual - incluido por precaucao"

# ── VEREDICTO IA ───────────────────────────────────────────────────────────────

def gerar_veredicto(anuncios, outros_precos, custo, peso_taxado, categoria, modalidade, nome, dims_ref, qtd_ref):
    com_vendas = [a for a in anuncios if a.get("vendas", 0) > 0]
    sem_vendas = [a for a in anuncios if a.get("vendas", 0) == 0]
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
            alerta_variacao = f"ATENCAO: variacao de preco elevada ({((variacao-1)*100):.0f}%). Verifique se ha tamanhos diferentes misturados."

    dims_str = f"{dims_ref[0]}x{dims_ref[1]}x{dims_ref[2]}cm" if any(d > 0 for d in dims_ref) else "nao informado"

    prompt = f"""Voce e um especialista em viabilidade de produtos para Mercado Livre.

PRODUTO: {nome}
Quantidade: {qtd_ref} unidade(s)
Medidas: {dims_str}
Custo: R${custo:.2f}
Modalidade: {modalidade}
LPV necessario: R${LPV_OFICIAL:.2f}

ANUNCIOS COM VENDAS ({len(com_vendas)} confirmados por medida e visao):
{"Faixa: R$" + f"{min(precos_com):.2f}" + " a R$" + f"{max(precos_com):.2f}" if precos_com else "Nenhum"}

CALCULO POR FAIXA:
{faixas_str}

ANUNCIOS SEM VENDAS ({len(sem_vendas)} confirmados):
{f'Faixa: R${min(precos_sem):.2f} a R${max(precos_sem):.2f}' if precos_sem else 'Nenhum'}

OUTROS CANAIS (referencia):
{outros_str}

{alerta_variacao}

REGRAS RIGIDAS:
1. UC MINIMO: 6/1. Abaixo disso = INVIAVEL sem excecao.
2. So sugira preco com UC >= 6/1.
3. Margem promocao: >10% OTIMO, 3-10% OK, <3% SEM MARGEM.
4. Se margem <10%, alerte sobre esforco operacional.
5. Seja honesto. Nao salve produto inviavel.

CENARIOS:
- VIAVEL: UC >= 6/1 + margem >10%
- VIAVEL COM RESSALVAS: UC 6/1-8/1 OU margem 3-10%
- INVIAVEL: UC < 6/1

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
    st.caption("v6.0")
    st.markdown("---")
    modalidade = st.selectbox("Modalidade ML", ["Premium", "Classico"])
    st.markdown("---")
    st.caption("Chaves configuradas automaticamente")

col1, col2 = st.columns(2)
with col1:
    st.subheader("Dados do Produto")
    fotos = st.file_uploader("Fotos do produto (pode enviar varias)", 
                              type=["jpg","jpeg","png","webp"], 
                              accept_multiple_files=True)
    nome_produto = st.text_input("Nome do produto (para busca no ML)")
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
    if fotos:
        cols_f = st.columns(min(len(fotos), 3))
        for i, f in enumerate(fotos[:3]):
            cols_f[i].image(f, use_container_width=True)

st.markdown("---")
analisar = st.button("Analisar Viabilidade", type="primary", use_container_width=True)

if analisar:
    erros = []
    if not fotos:        erros.append("Pelo menos 1 foto do produto")
    if not nome_produto: erros.append("Nome do produto")
    if not custo:        erros.append("Preco de custo")
    if erros:
        st.warning(f"Preencha: {', '.join(erros)}")
        st.stop()

    peso_taxado = calcular_peso_taxado(peso_kg, dim1 or 0, dim2 or 0, dim3 or 0)

    # Converte fotos para base64
    fotos_b64 = []
    for f in fotos:
        fotos_b64.append(base64.b64encode(f.read()).decode())

    # Hospeda primeira foto para o Lens
    url_imagem = None
    with st.spinner("Hospedando imagem..."):
        url_imagem, erro = hospedar_imgur(base64.b64decode(fotos_b64[0]))
        if erro:
            st.warning(f"Imgur indisponivel: {erro} — continuando sem outros canais")

    # Busca outros canais via Lens (em paralelo)
    outros_precos = {}
    if url_imagem:
        with st.spinner("Buscando precos em outros canais..."):
            outros_precos = buscar_outros_canais(url_imagem)

    # Busca anuncios ativos no ML por nome
    token = obter_token_ml()
    with st.spinner(f"Buscando anuncios ativos no ML para '{nome_produto}'..."):
        resultados_busca = buscar_anuncios_ml(nome_produto, token, limit=30)

    st.info(f"ML: {len(resultados_busca)} anuncios encontrados na busca")

    # Filtra por medida e analise visual
    confirmados = []
    descartados_medida = []
    descartados_visual = []
    sem_medida = []

    progress = st.progress(0, text="Analisando anuncios...")
    total = len(resultados_busca)

    for idx, resultado in enumerate(resultados_busca):
        progress.progress((idx+1)/total, text=f"Analisando {idx+1}/{total}...")
        item_id = resultado.get("id")
        if not item_id:
            continue

        # Busca detalhes completos
        anuncio = buscar_detalhes_anuncio(item_id, token)
        if not anuncio:
            continue

        # Filtra por medida
        tem_dims = any(d > 0 for d in dims_ref)
        if tem_dims:
            medida_ok, onde = verificar_medidas_anuncio(anuncio, dims_ref)
            if not medida_ok:
                if onde == "sem_medida_encontrada":
                    sem_medida.append(anuncio.get("title", ""))
                else:
                    descartados_medida.append(anuncio.get("title", ""))
                continue

        # Analise visual pelo Claude
        fotos_anuncio = [p.get("secure_url", p.get("url", ""))
                         for p in anuncio.get("pictures", [])]

        if fotos_anuncio:
            confirmado, motivo = confirmar_produto_visualmente(
                fotos_b64, fotos_anuncio, anuncio.get("title", "")
            )
            if not confirmado:
                descartados_visual.append(f"{anuncio.get('title', '')} ({motivo})")
                continue

        preco  = preco_promocional(anuncio)
        vendas = anuncio.get("sold_quantity", 0) or resultado.get("sold_quantity", 0)
        confirmados.append({
            "item_id": item_id,
            "titulo": anuncio.get("title", ""),
            "preco": preco,
            "vendas": vendas
        })

    progress.empty()

    # Resumo
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Confirmados", len(confirmados))
    col_b.metric("Descartados medida", len(descartados_medida))
    col_c.metric("Descartados visual", len(descartados_visual))
    col_d.metric("Sem medida", len(sem_medida))

    if outros_precos:
        st.markdown("---")
        st.subheader("Outros canais (referencia)")
        cols = st.columns(len(outros_precos))
        for i, (plat, precos) in enumerate(outros_precos.items()):
            cols[i].metric(plat, f"R${sum(precos)/len(precos):.2f}", f"{len(precos)} anuncio(s)")

    if confirmados:
        with st.spinner("Gerando veredicto com IA..."):
            veredicto = gerar_veredicto(
                confirmados, outros_precos, custo, peso_taxado,
                categoria, modalidade, nome_produto, dims_ref, qtd_ref
            )

        st.markdown("---")
        st.subheader("Resultado da Analise")
        if "INVIAVEL" in veredicto.upper():
            st.error(veredicto)
        elif "RESSALVAS" in veredicto.upper():
            st.warning(veredicto)
        else:
            st.success(veredicto)

        with st.expander("Ver anuncios confirmados"):
            com = [a for a in confirmados if a["vendas"] > 0]
            sem = [a for a in confirmados if a["vendas"] == 0]
            if com:
                st.markdown("**Com vendas:**")
                for a in com:
                    st.write(f"- {a['titulo']} — R${a['preco']:.2f} | {a['vendas']} vendas")
            if sem:
                st.markdown("**Sem vendas registradas:**")
                for a in sem:
                    st.write(f"- {a['titulo']} — R${a['preco']:.2f}")

        with st.expander("Ver descartados"):
            if descartados_medida:
                st.markdown("**Medida diferente:**")
                for t in descartados_medida:
                    st.write(f"- {t}")
            if descartados_visual:
                st.markdown("**Produto diferente (analise visual):**")
                for t in descartados_visual:
                    st.write(f"- {t}")
    else:
        st.warning("Nenhum anuncio confirmado. Tente um nome de produto mais especifico ou ajuste as medidas.")
