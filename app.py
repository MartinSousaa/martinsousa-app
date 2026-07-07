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

# ── CÁLCULO ────────────────────────────────────────────────────────────────────

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

def calcular_resultado(preco_venda, custo, peso_taxado_kg, categoria):
    comissao = calcular_comissao_ml(preco_venda, categoria)
    frete    = calcular_frete_ml(preco_venda, peso_taxado_kg)
    nf       = preco_venda * NF_OFICIAL
    lpv      = LPV_OFICIAL
    lucro    = preco_venda - (custo + comissao + frete + nf + lpv)
    margem   = (lucro / preco_venda * 100) if preco_venda > 0 else 0
    uc       = round(lpv / lucro, 1) if lucro > 0 else None
    return {
        'preco': preco_venda, 'custo': custo, 'comissao': comissao,
        'frete': frete, 'nf': nf, 'lpv': lpv, 'lucro': lucro,
        'margem': margem, 'uc': uc
    }

# ── GOOGLE LENS ────────────────────────────────────────────────────────────────

def buscar_por_foto(imagem_bytes, serpapi_key):
    try:
        img_b64 = base64.b64encode(imagem_bytes).decode()
        resp = requests.post(
            "https://serpapi.com/search",
            data={"engine": "google_lens", "api_key": serpapi_key,
                  "image_content": img_b64, "country": "br", "hl": "pt"},
            timeout=30
        )
        return resp.json().get("visual_matches", []), None
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
                ml_links.append({"link": link, "title": titulo})
        elif preco:
            plat = source.split(".")[0].capitalize()
            outros.setdefault(plat, []).append(preco)
    return ml_links, outros

# ── MERCADO LIVRE API ──────────────────────────────────────────────────────────

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
    if not largura_ref or not comprimento_ref:
        return True  # se nao informou medidas, nao filtra
    if not medidas:
        return False
    ref = sorted([largura_ref, comprimento_ref])
    for m in medidas:
        if len(m) >= 2:
            vals = sorted(m[:2])
            if abs(vals[0]-ref[0]) <= tolerancia and abs(vals[1]-ref[1]) <= tolerancia:
                return True
    return False

def extrair_quantidade(anuncio):
    titulo = anuncio.get("title", "").lower()
    nums_titulo = re.findall(r'(\d+)\s*(?:unid|pcs|pecas|kit|pack|par)', titulo)
    if nums_titulo:
        return int(nums_titulo[0])
    for attr in anuncio.get("attributes", []):
        nome = attr.get("name", "").lower()
        if any(p in nome for p in ["quantidade", "unidades", "pecas"]):
            nums = re.findall(r'\d+', attr.get("value_name", "") or "")
            if nums:
                return int(nums[0])
    return 1

def preco_promocional(anuncio):
    sp = anuncio.get("sale_price")
    if sp and sp.get("amount"):
        return float(sp["amount"])
    return float(anuncio.get("price", 0))

def processar_anuncios_ml(ml_links, token, largura, comprimento, qtd_ref):
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
        titulo  = anuncio.get("title", "")
        qtd     = extrair_quantidade(anuncio)

        # verifica medida
        if largura and comprimento:
            if not medidas:
                sem_medida.append({"titulo": titulo, "preco": preco, "qtd": qtd})
                continue
            if not medida_compativel(medidas, largura, comprimento):
                descartados.append({"titulo": titulo, "preco": preco})
                continue

        # verifica quantidade
        if qtd_ref and qtd_ref > 1:
            if qtd != qtd_ref:
                kits.append({"titulo": titulo, "preco": preco, "vendas": vendas, "qtd": qtd})
                continue

        validos.append({"titulo": titulo, "preco": preco, "vendas": vendas, "qtd": qtd})

    return validos, sem_medida, descartados, kits

# ── VEREDICTO IA ───────────────────────────────────────────────────────────────

def gerar_veredicto(anuncios, kits, outros_precos, custo, peso_taxado, categoria, api_key, nome, largura, comprimento, qtd_ref):
    com_vendas = [a for a in anuncios if a["vendas"] > 0]
    sem_vendas = [a for a in anuncios if a["vendas"] == 0]
    precos_com = sorted([a["preco"] for a in com_vendas])
    precos_sem = sorted([a["preco"] for a in sem_vendas])

    # calcula resultado para cada faixa de preco
    faixas_str = ""
    if precos_com:
        faixas_unicas = sorted(set([round(p, 2) for p in precos_com]))
        for p in faixas_unicas:
            r = calcular_resultado(p, custo, peso_taxado, categoria)
            faixas_str += f"  R${p:.2f} → lucro R${r['lucro']:.2f} | margem {r['margem']:.1f}% | UC 1/{r['uc']}\n"

    outros_str = "\n".join([f"- {p}: media R${sum(v)/len(v):.2f} ({len(v)} anuncios)"
                             for p, v in outros_precos.items()]) or "Nao encontrado"

    kits_str = ""
    if kits:
        kits_str = "KITS ENCONTRADOS (quantidade diferente da solicitada):\n"
        for k in kits[:5]:
            kits_str += f"  {k['titulo']} - R${k['preco']:.2f} | {k['qtd']} unidades | {k['vendas']} vendas\n"

    alerta_variacao = ""
    if precos_com and len(precos_com) > 1:
        variacao = max(precos_com) / min(precos_com)
        if variacao > 1.5:
            alerta_variacao = f"ATENCAO: variacao de preco de {((variacao-1)*100):.0f}% detectada. Investigue se ha produtos de tamanhos ou quantidades diferentes misturados."

    prompt = f"""Voce e um especialista em viabilidade de produtos para Mercado Livre.
Analise os dados abaixo e gere um veredicto completo em portugues.

PRODUTO: {nome}
Quantidade por unidade/kit: {qtd_ref if qtd_ref else 1}
{f'Medidas: {largura:.0f}x{comprimento:.0f}cm' if largura and comprimento else ''}
Custo: R${custo:.2f}
LPV necessario: R${LPV_OFICIAL:.2f}

ANUNCIOS COM VENDAS NO MERCADO ({len(com_vendas)} encontrados):
Faixa de precos: R${min(precos_com):.2f} a R${max(precos_com):.2f}

CALCULO POR FAIXA DE PRECO:
{faixas_str}

ANUNCIOS SEM VENDAS ({len(sem_vendas)} encontrados):
{f'Faixa: R${min(precos_sem):.2f} a R${max(precos_sem):.2f}' if precos_sem else 'Nenhum'}

{kits_str}

OUTROS CANAIS (referencia):
{outros_str}

{alerta_variacao}

REGRAS DE ANALISE:
1. Sugira o melhor preco de venda considerando competitividade E lucro — nem o mais barato nem o mais caro, mas o melhor ponto de equilibrio onde o produto VENDE e da lucro
2. Calcule o lucro, margem e UC no preco sugerido
3. Verifique se ha margem para promocao:
   - Acima de 10% entre preco viavel e media de mercado: OTIMO — boa margem para promocao
   - Entre 3% e 10%: OK — mas com atencao nas promocoes
   - Abaixo de 3%: SEM MARGEM — nao recomenda promocao
4. UC minimo aceitavel: 6/1 (lucro minimo ~R$3,67). Abaixo disso e inviavel.
5. Se margem for baixa (abaixo de 10%), adicione alerta: "Considerando a margem desse produto, avalie o processo operacional de embalagem — pode nao valer o esforço."
6. Se encontrou kits mas nao encontrou unitario viavel, sugira anunciar em kit informando qual quantidade faz mais sentido
7. Se nenhuma faixa de preco for viavel, seja honesto e diga que o produto nao e viavel no ML unitario

CENARIOS DE VEREDICTO:
- VIAVEL: bom lucro + margem para promocao acima de 10%
- VIAVEL COM RESSALVAS: lucro ok mas promocao entre 3-10% OU UC entre 6/1 e 8/1
- INVIAVEL: margem baixa + sem promocao + UC abaixo de 6/1

Estruture a resposta assim:
1. VEREDICTO: [VIAVEL / VIAVEL COM RESSALVAS / INVIAVEL]
2. PRECO SUGERIDO: R$X,XX
3. CALCULO NO PRECO SUGERIDO: (custo, comissao, frete, nf, lpv, lucro, margem, UC)
4. ANALISE DE PROMOCAO: (com percentual de margem disponivel)
5. ANALISE DE MERCADO: (distribuicao de precos, onde estao as vendas)
6. ALERTAS: (se houver)
7. RECOMENDACAO FINAL: (objetiva, 2-3 linhas)
"""

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text

# ── INTERFACE ──────────────────────────────────────────────────────────────────

st.title("Analise de Viabilidade - Mercado Livre")
st.markdown("---")

with st.sidebar:
    st.header("Configuracoes")
    api_key_claude = st.text_input("Chave API Claude", type="password")
    ml_client_id   = st.text_input("ML Client ID")
    ml_secret      = st.text_input("ML Client Secret", type="password")
    serpapi_key    = st.text_input("Chave SerpApi", type="password")
    st.markdown("---")
    st.caption("MartinSousa App v3.0")

col1, col2 = st.columns(2)
with col1:
    st.subheader("Dados do Produto")
    foto         = st.file_uploader("Foto do produto", type=["jpg","jpeg","png","webp"])
    nome_produto = st.text_input("Nome do produto")
    custo        = st.number_input("Preco de custo (R$)", min_value=0.0, step=0.50, format="%.2f")
    qtd_ref      = st.number_input("Quantidade por unidade/kit", min_value=1, step=1, value=1)
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
    if not api_key_claude: erros.append("Chave API Claude")
    if not ml_client_id:   erros.append("ML Client ID")
    if not ml_secret:      erros.append("ML Client Secret")
    if not serpapi_key:    erros.append("Chave SerpApi")

    if erros:
        st.warning(f"Preencha: {', '.join(erros)}")
    else:
        peso_taxado = calcular_peso_taxado(peso_real, altura, largura, comprimento)

        with st.spinner("Buscando produto por foto no Google Lens..."):
            imagem_bytes = foto.read()
            visual_matches, erro = buscar_por_foto(imagem_bytes, serpapi_key)

        if erro:
            st.error(f"Erro Google Lens: {erro}")
            st.stop()

        ml_links, outros_precos = filtrar_por_plataforma(visual_matches)
        st.success(f"Google Lens: {len(visual_matches)} resultados — {len(ml_links)} no ML")

        with st.spinner("Acessando anuncios e validando medidas/quantidades..."):
            token = obter_token_ml(ml_client_id, ml_secret)
            validos, sem_medida, descartados, kits = processar_anuncios_ml(
                ml_links, token, largura, comprimento, qtd_ref
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
                    categoria, api_key_claude, nome_produto, largura, comprimento, qtd_ref
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
            st.warning("Nenhum anuncio encontrado com as especificacoes informadas. Tente outra foto ou ajuste as dimensoes/quantidade.")
