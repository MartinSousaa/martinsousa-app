import streamlit as st
import requests
import anthropic
import base64
import re
import io
from PIL import Image
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
        # Converte qualquer formato (webp, heic, png, etc) para JPEG antes de enviar,
        # pra evitar erro "We don't support that file type" do Imgur.
        img = Image.open(io.BytesIO(imagem_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=90)
        imagem_jpeg = buffer.getvalue()

        img_b64 = base64.b64encode(imagem_jpeg).decode()
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

def extrair_ml_candidato(link):
    """Identifica se o link do ML e uma pagina de catalogo (/p/MLB...) ou
    um anuncio direto (permalink .../MLB-123456789-titulo...), e extrai o ID certo.
    Retorna ('produto', id) ou ('item', id) ou None."""
    m_produto = re.search(r'/p/(MLB\d{6,15})', link, re.IGNORECASE)
    if m_produto:
        return ("produto", m_produto.group(1).upper())
    m_item = re.search(r'(MLB-\d{9,15})-', link, re.IGNORECASE)
    if m_item:
        return ("item", m_item.group(1).upper().replace("-", ""))
    return None

def resolver_produto_catalogo(product_id, token):
    """Dado um ID de produto de catalogo, retorna o item_id do anuncio
    vencedor (buy_box_winner) daquela pagina."""
    try:
        r = requests.get(
            f"https://api.mercadolibre.com/products/{product_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        data = r.json()
        if r.status_code != 200:
            return None, f"HTTP {r.status_code} - {data.get('message', data.get('error', 'erro'))}"
        winner = data.get("buy_box_winner") or {}
        item_id = winner.get("item_id")
        if not item_id:
            return None, "sem buy_box_winner (produto sem anuncio ganhador no momento)"
        return item_id, None
    except Exception as e:
        return None, str(e)

def buscar_outros_canais(url_imagem):
    """Busca via Google Lens (SerpApi). Retorna precos de outros canais
    e os concorrentes do Mercado Livre encontrados -- usando titulo, preco
    e foto que o proprio Lens ja devolve, sem depender da API do ML (que
    esta bloqueando busca por texto e consulta de item/produto para a
    maioria dos apps de terceiros)."""
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
        ml_resultados = []
        for item in resp.json().get("visual_matches", []):
            source    = item.get("source", "").lower()
            link      = item.get("link", "")
            price     = item.get("price", {})
            preco     = price.get("extracted_value") if price else None
            titulo    = item.get("title", "")
            thumbnail = item.get("thumbnail", "")

            if "mercadolivre.com.br" in source or "mercadolivre.com.br" in link.lower():
                if preco and titulo:
                    ml_resultados.append({
                        "titulo": titulo, "preco": preco,
                        "link": link, "thumbnail": thumbnail,
                    })
                continue

            if preco:
                for dominio, nome in MARKETPLACES_ACEITOS.items():
                    if dominio in source or dominio in link.lower():
                        outros.setdefault(nome, []).append(preco)
                        break
        return outros, ml_resultados
    except:
        return {}, []

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
        if "error" in data or r.status_code != 200:
            return None, f"HTTP {r.status_code} - {data.get('message', data.get('error', 'erro desconhecido'))}"
        return data, None
    except Exception as e:
        return None, str(e)

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
    precos = sorted([a["preco"] for a in anuncios])

    faixas_str = ""
    if precos:
        for p in sorted(set([round(p, 2) for p in precos])):
            r = calcular_resultado(p, custo, peso_taxado, categoria, modalidade)
            faixas_str += f"  R${p:.2f} -> lucro R${r['lucro']:.2f} | margem {r['margem']:.1f}% | UC 1/{r['uc']}\n"

    outros_str = "\n".join([f"- {p}: media R${sum(v)/len(v):.2f} ({len(v)} anuncios)"
                             for p, v in outros_precos.items()]) or "Nao encontrado"

    alerta_variacao = ""
    if precos and len(precos) > 1:
        variacao = max(precos) / min(precos)
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

ANUNCIOS CONCORRENTES CONFIRMADOS ({len(anuncios)} confirmados por medida e visao):
{"Faixa: R$" + f"{min(precos):.2f}" + " a R$" + f"{max(precos):.2f}" if precos else "Nenhum"}

OBS: numero de vendas de concorrentes nao esta disponivel (API do Mercado Livre nao libera esse dado para anuncios de terceiros). A analise abaixo considera apenas preco de mercado, nao volume de vendas.

CALCULO POR FAIXA:
{faixas_str}

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
    st.caption("v6.2")
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

    # Busca outros canais + concorrentes do ML via Lens. A API do ML esta
    # bloqueando busca por texto e consulta de item/produto pra apps de
    # terceiros, entao usamos os dados que o proprio Lens ja devolve
    # (titulo, preco, foto) -- o mesmo jeito que ja funciona pra Shopee.
    outros_precos = {}
    ml_resultados = []
    if url_imagem:
        with st.spinner("Buscando concorrentes (Lens)..."):
            outros_precos, ml_resultados = buscar_outros_canais(url_imagem)

    st.info(f"ML: {len(ml_resultados)} anuncios candidatos encontrados (Lens)")

    # Filtra por medida e analise visual
    confirmados = []
    descartados_medida = []
    descartados_visual = []
    sem_medida = []

    progress = st.progress(0, text="Analisando anuncios...")
    total = len(ml_resultados)

    for idx, resultado in enumerate(ml_resultados):
        if total:
            progress.progress((idx+1)/total, text=f"Analisando {idx+1}/{total}...")

        titulo = resultado["titulo"]

        # Filtra por medida (usando o titulo que o Lens devolveu)
        tem_dims = any(d > 0 for d in dims_ref)
        if tem_dims:
            medidas = extrair_medidas_texto(titulo)
            medida_ok, status = medida_compativel(medidas, dims_ref)
            if not medida_ok:
                if status == "sem_medida":
                    sem_medida.append(titulo)
                else:
                    descartados_medida.append(titulo)
                continue

        # Analise visual pelo Claude (usando a miniatura que o Lens devolveu)
        if resultado["thumbnail"]:
            confirmado, motivo = confirmar_produto_visualmente(
                fotos_b64, [resultado["thumbnail"]], titulo
            )
            if not confirmado:
                descartados_visual.append(f"{titulo} ({motivo})")
                continue

        confirmados.append({
            "titulo": titulo,
            "preco": resultado["preco"],
            "link": resultado["link"],
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

        with st.expander("Ver anuncios concorrentes confirmados"):
            for a in sorted(confirmados, key=lambda x: x["preco"]):
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
