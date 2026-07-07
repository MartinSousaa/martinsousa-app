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

# ── HOSPEDAGEM IMGUR ───────────────────────────────────────────────────────────

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

def filtrar_por_plataforma(visual_matches):
    ml_links, outros = [], {}
    for item in visual_matches:
        source = item.get("source", "").lower()
        price  = item.get("price", {})
        preco  = price.get("extracted_value") if price else None
        link   = item.get("link", "")
        titulo = item.get("title", "")
        if ("mercadolivre.com.br" in source or "mercadolivre.com.br" in link):
            if link:
                ml_links.append({"link": link, "title": titulo})
        elif preco:
            plat = source.split(".")[0].capitalize()
            outros.setdefault(plat, []).append(preco)
    return ml_links, outros

# ── MERCADO LIVRE API ──────────────────────────────────────────────────────────

def obter_token_ml():
    # Usa o token OAuth do usuario se disponivel (retorna sold_quantity real)
    if ML_ACCESS_TOKEN:
        return ML_ACCESS_TOKEN
    resp = requests.post(
        "https://api.mercadolibre.com/oauth/token",
        data={"grant_type": "client_credentials",
              "client_id": ML_CLIENT_ID, "client_secret": ML_CLIENT_SECRET},
        timeout=10
    )
    return resp.json().get("access_token")

def extrair_item_id(link):
    match = re.search(r'MLB-?(\d+)', link)
    return f"MLB{match.group(1)}" if match else None

def buscar_anuncio(item_id, token):
    try:
        r = requests.get(
            f"https://api.mercadolibre.com/items/{item_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"include_attributes": "all"},
            timeout=10
        )
        return r.json()
    except:
        return None

def buscar_vendas_publico(item_id, token=""):
    """Busca sold_quantity via endpoint de busca do ML."""
    try:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        r = requests.get(
            "https://api.mercadolibre.com/sites/MLB/search",
            params={"iids": item_id},
            headers=headers,
            timeout=10
        )
        data = r.json()
        resultados = data.get("results", [])
        if resultados:
            return resultados[0].get("sold_quantity", 0)
        return 0
    except:
        return 0

def extrair_medidas(anuncio):
    medidas = []
    titulo = anuncio.get("title", "")
    for m in re.findall(r'(\d+[.,]?\d*)\s*[xX]\s*(\d+[.,]?\d*)', titulo):
        medidas.append((float(m[0].replace(',','.')), float(m[1].replace(',','.'))))
    for attr in anuncio.get("attributes", []):
        nome  = attr.get("name", "").lower()
        valor = attr.get("value_name", "") or ""
        if any(p in nome for p in ["comprimento", "largura", "dimensao", "tamanho", "medida"]):
            nums = re.findall(r'\d+[.,]?\d*', valor)
            if len(nums) >= 2:
                medidas.append((float(nums[0].replace(',','.')), float(nums[1].replace(',','.'))))
    return medidas

def medida_compativel(medidas, dims_ref, tolerancia=2.0):
    if not dims_ref or all(d == 0 for d in dims_ref):
        return True
    dims_validas = [d for d in dims_ref if d > 0]
    if not medidas:
        return False
    ref = sorted(dims_validas)
    for m in medidas:
        ms = sorted(m[:2])
        if len(ref) >= 2:
            if abs(ms[0]-ref[0]) <= tolerancia and abs(ms[1]-ref[1]) <= tolerancia:
                return True
        elif len(ref) == 1:
            if any(abs(v-ref[0]) <= tolerancia for v in ms):
                return True
    return False

def extrair_quantidade(anuncio):
    titulo = anuncio.get("title", "").lower()
    nums = re.findall(r'(\d+)\s*(?:unid|pcs|pecas|kit|pack|par|folhas)', titulo)
    if nums:
        return int(nums[0])
    for attr in anuncio.get("attributes", []):
        nome = attr.get("name", "").lower()
        if any(p in nome for p in ["quantidade", "unidades", "pecas", "itens"]):
            ns = re.findall(r'\d+', attr.get("value_name", "") or "")
            if ns:
                return int(ns[0])
    return 1

def preco_promocional(anuncio):
    sp = anuncio.get("sale_price")
    if sp and sp.get("amount"):
        return float(sp["amount"])
    return float(anuncio.get("price", 0))

def processar_anuncios_ml(ml_links, token, dims_ref, qtd_ref):
    validos, sem_medida, descartados, kits = [], [], [], []
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
        if vendas == 0:
            vendas = buscar_vendas_publico(item_id, token)
        titulo  = anuncio.get("title", "")
        qtd     = extrair_quantidade(anuncio)
        tem_dims = any(d > 0 for d in dims_ref)
        if tem_dims:
            if medidas and not medida_compativel(medidas, dims_ref):
                descartados.append({"titulo": titulo, "preco": preco})
                continue
        if qtd_ref > 1 and qtd != qtd_ref:
            kits.append({"titulo": titulo, "preco": preco, "vendas": vendas, "qtd": qtd})
            continue
        medida_ok = bool(medidas) and (not tem_dims or medida_compativel(medidas, dims_ref))
        validos.append({"titulo": titulo, "preco": preco, "vendas": vendas, "qtd": qtd, "medida_ok": medida_ok})
    return validos, sem_medida, descartados, kits

# ── VEREDICTO IA ───────────────────────────────────────────────────────────────

def gerar_veredicto(anuncios, kits, outros_precos, custo, peso_taxado, categoria, modalidade, nome, dims_ref, qtd_ref):
    com_vendas = [a for a in anuncios if a["vendas"] > 0]
    sem_vendas = [a for a in anuncios if a["vendas"] == 0]
    precos_com = sorted([a["preco"] for a in com_vendas])
    precos_sem = sorted([a["preco"] for a in sem_vendas])

    faixas_str = ""
    if precos_com:
        for p in sorted(set([round(p, 2) for p in precos_com])):
            r = calcular_resultado(p, custo, peso_taxado, categoria, modalidade)
            faixas_str += f"  R${p:.2f} -> lucro R${r['lucro']:.2f} | margem {r['margem']:.1f}% | UC 1/{r['uc']}\n"

    outros_str = "\n".join([f"- {p}: media R${sum(v)/len(v):.2f} ({len(v)} anuncios)"
                             for p, v in outros_precos.items()]) or "Nao encontrado"

    kits_str = ""
    if kits:
        kits_str = "KITS (quantidade diferente):\n"
        for k in kits[:5]:
            kits_str += f"  {k['titulo']} - R${k['preco']:.2f} | {k['qtd']} un | {k['vendas']} vendas\n"

    alerta_variacao = ""
    if precos_com and len(precos_com) > 1:
        variacao = max(precos_com) / min(precos_com)
        if variacao > 1.5:
            alerta_variacao = f"ATENCAO: variacao de preco de {((variacao-1)*100):.0f}% detectada ({min(precos_com):.2f} a {max(precos_com):.2f}). Investigue se ha tamanhos ou quantidades diferentes misturados."

    dims_str = f"{dims_ref[0]}x{dims_ref[1]}x{dims_ref[2]}cm" if any(d > 0 for d in dims_ref) else "nao informado"

    prompt = f"""Voce e um especialista em viabilidade de produtos para Mercado Livre.

PRODUTO: {nome}
Quantidade: {qtd_ref} unidade(s)
Medidas: {dims_str}
Custo: R${custo:.2f}
Modalidade: {modalidade}
LPV necessario: R${LPV_OFICIAL:.2f}

ANUNCIOS COM VENDAS ({len(com_vendas)} encontrados):
{"Faixa: R$" + f"{min(precos_com):.2f}" + " a R$" + f"{max(precos_com):.2f}" if precos_com else "Nenhum com vendas registradas"}

CALCULO POR FAIXA:
{faixas_str}

ANUNCIOS SEM VENDAS ({len(sem_vendas)} encontrados):
{f'Faixa: R${min(precos_sem):.2f} a R${max(precos_sem):.2f}' if precos_sem else 'Nenhum'}

{kits_str}

OUTROS CANAIS:
{outros_str}

{alerta_variacao}

REGRAS:
1. Sugira o melhor preco: equilibrio entre VENDER e DAR LUCRO.
2. Margem para promocao: acima 10% OTIMO, 3-10% OK, abaixo 3% SEM MARGEM.
3. UC minimo: 6/1. Abaixo disso inviavel.
4. Se margem abaixo 10%, alerte sobre esforco operacional.
5. Se unitario inviavel mas kits encontrados, sugira kit.
6. Se inviavel, diga claramente.

CENARIOS:
- VIAVEL: lucro bom + margem promocao acima 10%
- VIAVEL COM RESSALVAS: lucro ok + promocao 3-10% OU UC 6/1 a 8/1
- INVIAVEL: margem baixa + sem promocao + UC abaixo 6/1

ESTRUTURE ASSIM:
1. VEREDICTO: [VIAVEL / VIAVEL COM RESSALVAS / INVIAVEL]
2. PRECO SUGERIDO: R$X,XX
3. CALCULO: custo | comissao | frete | nf | lpv | lucro | margem | UC
4. ANALISE DE PROMOCAO: margem disponivel e recomendacao
5. ANALISE DE MERCADO: distribuicao de precos e onde estao as vendas
6. ALERTAS: (se houver)
7. RECOMENDACAO FINAL: 2-3 linhas objetivas
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
    st.caption("v4.2")
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
analisar = st.button("Analisar Viabilidade", type="primary", use_container_width=True)

if analisar:
    erros = []
    if not foto:           erros.append("Foto do produto")
    if not nome_produto:   erros.append("Nome do produto")
    if not custo:          erros.append("Preco de custo")
    if erros:
        st.warning(f"Preencha: {', '.join(erros)}")
    else:
        peso_taxado = calcular_peso_taxado(peso_kg, dim1 or 0, dim2 or 0, dim3 or 0)

        with st.spinner("Hospedando imagem..."):
            imagem_bytes = foto.read()
            url_imagem, erro_imgur = hospedar_imgur(imagem_bytes)

        if erro_imgur:
            st.error(f"Erro ao hospedar imagem: {erro_imgur}")
            st.stop()

        with st.spinner("Buscando produto por foto no Google Lens..."):
            visual_matches, erro = buscar_por_foto(url_imagem)

        if erro:
            st.error(f"Erro Google Lens: {erro}")
            st.stop()

        ml_links, outros_precos = filtrar_por_plataforma(visual_matches)
        st.success(f"Google Lens: {len(visual_matches)} resultados — {len(ml_links)} no ML")

        with st.spinner("Acessando anuncios e validando medidas/quantidades..."):
            token = obter_token_ml()
            validos, sem_medida, descartados, kits = processar_anuncios_ml(
                ml_links, token, dims_ref, qtd_ref
            )

        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("Confirmados", len(validos))
        col_b.metric("Kits (qtd diferente)", len(kits))
        col_c.metric("Sem medida", len(sem_medida))
        col_d.metric("Descartados", len(descartados))

        if outros_precos:
            st.markdown("---")
            st.subheader("Outros canais (referencia)")
            cols = st.columns(len(outros_precos))
            for i, (plat, precos) in enumerate(outros_precos.items()):
                cols[i].metric(plat, f"R${sum(precos)/len(precos):.2f}", f"{len(precos)} anuncio(s)")

        if validos or kits:
            with st.spinner("Gerando analise completa com IA..."):
                veredicto = gerar_veredicto(
                    validos, kits, outros_precos, custo, peso_taxado,
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

            with st.expander("Ver todos os anuncios analisados"):
                if validos:
                    com = [a for a in validos if a["vendas"] > 0]
                    sem = [a for a in validos if a["vendas"] == 0]
                    if com:
                        st.markdown("**Com vendas:**")
                        for a in com:
                            st.write(f"- {a['titulo']} — R${a['preco']:.2f} | {a['vendas']} vendas | {a['qtd']} un")
                    if sem:
                        st.markdown("**Sem vendas:**")
                        for a in sem:
                            st.write(f"- {a['titulo']} — R${a['preco']:.2f} | {a['qtd']} un")
                if kits:
                    st.markdown("**Kits (quantidade diferente):**")
                    for k in kits:
                        st.write(f"- {k['titulo']} — R${k['preco']:.2f} | {k['qtd']} un | {k['vendas']} vendas")
        else:
            st.warning("Nenhum anuncio encontrado. Tente outra foto ou ajuste as dimensoes/quantidade.")
