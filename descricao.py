import streamlit as st
import anthropic
import math
from params_oficiais import ML_COMISSAO_POR_CATEGORIA


EXEMPLO_1 = """A Bengala 3 Pontas com Apoio foi desenvolvida para auxiliar pessoas com mobilidade reduzida, proporcionando apoio e estabilidade para prevenir quedas durante a caminhada.

O recurso é resistente, leve e possui apoio de mão com cantos arredondados e design ergonômico, que contribui para melhor distribuição da pressão palmar e proporciona conforto durante o uso.

O dispositivo conta com 10 níveis de ajuste de altura.

A bengala contém base de apoio ampliada, com 3 ponteiras que oferecem melhor aderência ao solo, gerando estabilidade e segurança ao caminhar.

Tamanho único ajustável.
Produto compatível com usuários que tenham altura de 1,50m a 2mt

Composição:
- Parte metálica: Alumínio
- Apoio de mão: Polipropileno
- Ponteira: Borracha

MEDIDAS DO PRODUTO;
Altura mínima: 64 cm
Altura máxima: 101,50 cm

Contém; 1 peça"""

EXEMPLO_2 = """Benefícios da viseira: Ao contrário de um boné, a viseira apresenta materiais mais leves e que permitem transpiração adequada, sem deixar de lado a proteção. Os raios ultravioletas podem causar grande desconforto quando em contato direto com os olhos, além dos danos à visão.

DIMENSÕES:
- Modelo: Adulto
- Aba: 7cm X 18cm
- Ajuste de tamanho traseiro em velcro

- Onde usar minha viseira?
Em corridas ou atividades mais longas a viseira tende a ser a melhor opção porque protege o rosto como o boné, porém, ao contrário dele, a viseira deixa os fios de cabelo da parte superior da cabeça livres para transpirarem. Com isso, a sensação de calor diminui.

- Como conservar minha viseira
- Use sabão neutro
- Produtos de limpeza com aromatizantes e corantes costumam ser agressivos com tecidos mais leves. Por isso, o sabão neutro é o mais indicado
- Amaciantes e alvejantes são dispensáveis
- Deixe secando na sombra"""


# ── CALCULO DE CAPACIDADE DE FOTOS (deterministico, em Python -- nunca a IA "chutando") ──

def parse_dimensoes(texto):
    """Aceita '30x30x2', '30,5 x 30,5', '8.6x10.7' etc. Retorna lista de floats ou None."""
    if not texto:
        return None
    texto = texto.strip().lower().replace(",", ".").replace(" ", "")
    partes = [p for p in texto.replace("cm", "").split("x") if p]
    try:
        return [float(p) for p in partes]
    except ValueError:
        return None


def fotos_por_pagina(pagina_w, pagina_h, foto_w, foto_h):
    """Maior encaixe entre as 2 orientacoes possiveis da foto na pagina."""
    opcao1 = math.floor(pagina_w / foto_w) * math.floor(pagina_h / foto_h)
    opcao2 = math.floor(pagina_w / foto_h) * math.floor(pagina_h / foto_w)
    return max(opcao1, opcao2)


def calcular_capacidade(medidas_album, num_folhas, tam_polaroid, tam_padrao):
    """Retorna (texto_capacidade, formula_explicativa, erro)."""
    dims_album = parse_dimensoes(medidas_album)
    if not dims_album or len(dims_album) < 2:
        return None, None, "Preencha as Medidas do produto (AxL) pra eu calcular a capacidade de fotos."
    if not num_folhas:
        return None, None, "Informe o Número de folhas do álbum pra eu calcular a capacidade de fotos."
    try:
        num_folhas_val = float(str(num_folhas).replace(",", "."))
    except ValueError:
        return None, None, "Número de folhas inválido -- use só números."

    pagina_w, pagina_h = dims_album[0], dims_album[1]
    bullets = []
    dados_padrao_para_formula = None
    for nome, tam_txt in [("Polaroid clássica", tam_polaroid), ("Foto padrão", tam_padrao)]:
        dims_foto = parse_dimensoes(tam_txt)
        if not dims_foto or len(dims_foto) < 2:
            continue
        foto_w, foto_h = dims_foto[0], dims_foto[1]
        por_pagina = fotos_por_pagina(pagina_w, pagina_h, foto_w, foto_h)
        if por_pagina <= 0:
            bullets.append(f"- {nome} ({tam_foto_str(foto_w, foto_h)}cm): não cabe nessa página.")
            continue
        total_1_lado = int(por_pagina * num_folhas_val)
        total_2_lados = total_1_lado * 2
        bullets.append(
            f"- {nome} ({tam_foto_str(foto_w, foto_h)}cm): até {total_1_lado} fotos "
            f"(até {total_2_lados} usando frente e verso)"
        )
        if nome == "Foto padrão":
            dados_padrao_para_formula = (foto_w, foto_h, por_pagina)

    if not bullets:
        return None, None, "Não consegui calcular -- confira o formato dos tamanhos de foto (ex: 8,6x10,7)."

    texto_capacidade = "Capacidade de fotos:\n" + "\n".join(bullets)

    # Formula explicativa pro cliente calcular outro tamanho de foto -- usa a
    # foto padrao como exemplo concreto, com os numeros reais desse produto.
    formula = None
    if dados_padrao_para_formula:
        fw, fh, ppag = dados_padrao_para_formula
        formula = (
            f"Para saber até quantas fotos de outro tamanho cabem, basta fazer a conta abaixo:\n\n"
            f"Tamanho da folha: {tam_foto_str(pagina_w, pagina_h)}cm\n"
            f"Conta: divida a largura da folha pela largura da foto, e a altura da folha pela "
            f"altura da foto (arredondando pra baixo). Multiplique os dois resultados -- esse é "
            f"o total de fotos que cabem por página.\n"
            f"Exemplo com a foto padrão ({tam_foto_str(fw, fh)}cm): "
            f"{tam_foto_str(pagina_w, pagina_h)} ÷ {tam_foto_str(fw, fh)} = {int(pagina_w//fw)} x {int(pagina_h//fh)} = {ppag} fotos por página"
        )

    return texto_capacidade, formula, None


def tam_foto_str(w, h):
    def fmt(v):
        return str(int(v)) if v == int(v) else str(v).replace(".", ",")
    return f"{fmt(w)}x{fmt(h)}"


# ── CALCULO DE CAPACIDADE DE FOLHAS POR ARGOLA/ESPIRAL (deterministico) ──

def parse_lista_numeros(texto):
    """Aceita '1, 1.5, 2' ou '1;1,5;2' etc -- retorna lista de floats."""
    if not texto:
        return []
    texto = texto.replace(";", ",")
    partes = [p.strip() for p in texto.split(",") if p.strip()]
    resultado = []
    for p in partes:
        try:
            resultado.append(float(p.replace(",", ".") if p.count(",") == 1 and "." not in p else p))
        except ValueError:
            continue
    return resultado


def calcular_capacidade_argola(medida_interna_mm, espessuras_texto):
    """Retorna (texto_capacidade, erro). Formula: medida_interna / espessura_folha,
    arredondando pra baixo -- mesmo padrao usado pela empresa (imagem de referencia)."""
    if not medida_interna_mm:
        return None, "Informe a medida interna da argola/espiral (mm) pra eu calcular a capacidade de folhas."
    try:
        medida_val = float(str(medida_interna_mm).replace(",", "."))
    except ValueError:
        return None, "Medida interna inválida -- use só números."

    espessuras = parse_lista_numeros(espessuras_texto) or [1.0, 1.5, 2.0]
    linhas = []
    for esp in espessuras:
        if esp <= 0:
            continue
        qtd = int(medida_val // esp)
        esp_str = str(esp) if esp != int(esp) else str(int(esp))
        esp_str = esp_str.replace(".", ",")
        med_str = str(medida_val) if medida_val != int(medida_val) else str(int(medida_val))
        med_str = med_str.replace(".", ",")
        linhas.append(f"- Espessura {esp_str}mm: {med_str}÷{esp_str} = {qtd} folhas")

    if not linhas:
        return None, "Informe pelo menos uma espessura de folha válida."

    texto = (
        f"Para saber quantas folhas cabem, divida a medida interna ({str(medida_val).replace('.', ',') if medida_val != int(medida_val) else int(medida_val)}mm) "
        f"pela espessura de cada folha em milímetros:\n" + "\n".join(linhas) +
        "\n\n*Cálculo aproximado. A quantidade pode variar ligeiramente conforme o tipo de papel."
    )
    return texto, None


# ── PESQUISA DE USOS DO PRODUTO NA INTERNET (opcional, via SerpAPI) ──

def pesquisar_usos_produto(nome_produto):
    """Busca real na internet pra encontrar usos comuns desse tipo de produto que o
    colaborador pode ter esquecido de mencionar no campo Uso/ocasião. Retorna
    (resumo_para_ia, erro)."""
    import requests
    api_key = st.secrets.get("SERPAPI_KEY", "")
    if not api_key:
        return None, "SERPAPI_KEY não configurada nas Secrets."
    try:
        resp = requests.get("https://serpapi.com/search", params={
            "engine": "google", "q": f"{nome_produto} para que serve usado",
            "hl": "pt-br", "gl": "br", "num": 5, "api_key": api_key,
        }, timeout=30)
        if resp.status_code != 200:
            return None, f"Busca indisponível agora (HTTP {resp.status_code})."
        dados = resp.json()
        snippets = []
        for r in dados.get("organic_results", [])[:5]:
            s = r.get("snippet", "")
            if s:
                snippets.append(f"- {s}")
        if not snippets:
            return None, "Nenhum resultado relevante encontrado pra esse produto."
        return "\n".join(snippets), None
    except Exception as e:
        return None, str(e)


def gerar_descricao(dados):
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "")

    bloco_capacidade = ""
    if dados.get("capacidade_texto"):
        bloco_capacidade = f"""
CAPACIDADE DE FOTOS JÁ CALCULADA (use estes números EXATAMENTE como estão, não recalcule
nem estime por conta própria -- inclua esse bloco na descrição, com o cabeçalho "Capacidade de
fotos:" e os itens em lista, exatamente como estruturado abaixo):
{dados['capacidade_texto']}

Logo depois, inclua também esta explicação (em suas próprias palavras, mas mantendo a conta exata)
pra o cliente conseguir calcular sozinho quantas fotos de OUTRO tamanho cabem:
{dados.get('formula_texto','')}
"""

    bloco_capacidade_argola = ""
    if dados.get("capacidade_argola_texto"):
        bloco_capacidade_argola = f"""
CAPACIDADE DE FOLHAS JÁ CALCULADA (use estes números EXATAMENTE como estão, não recalcule --
inclua esse bloco na descrição, com um cabeçalho tipo "Capacidade:" e o conteúdo abaixo,
adaptando a linguagem ao tom da descrição mas mantendo a conta exata):
{dados['capacidade_argola_texto']}
"""

    bloco_usos_pesquisados = ""
    if dados.get("usos_pesquisados"):
        bloco_usos_pesquisados = f"""
CONTEXTO ENCONTRADO EM PESQUISA REAL NA INTERNET sobre esse tipo de produto (pode revelar usos
que o colaborador esqueceu de mencionar no campo Uso/ocasião acima). NÃO copie trechos literalmente
-- reescreva com suas próprias palavras, e só incorpore na descrição se fizer sentido real pro
produto (ignore o que não se aplicar):
{dados['usos_pesquisados']}
"""

    bloco_observacoes = ""
    if dados.get("observacoes"):
        bloco_observacoes = f"""
INSTRUÇÃO ESPECÍFICA DO COLABORADOR PRA ESSA DESCRIÇÃO (siga isso com prioridade, incorporando
na estrutura acima -- se pedir pra enfatizar algo, dedica um parágrafo curto e específico a isso):
{dados['observacoes']}
"""

    prompt = f"""Crie a descrição de anúncio para o produto abaixo, seguindo EXATAMENTE o padrão de
estilo e estrutura da empresa, mostrado nos 2 exemplos reais abaixo (mesma voz, mesmo jeito de
organizar em blocos com cabeçalho, mesmo tom direto e técnico).

=== EXEMPLO REAL 1 (produto: bengala) ===
{EXEMPLO_1}

=== EXEMPLO REAL 2 (produto: viseira) ===
{EXEMPLO_2}

=== PADRÃO A SEGUIR ===
- Abre com 1-2 frases ligando produto + benefício/uso principal (sem repetir o título literalmente)
- Parágrafos curtos descrevendo características e o que elas proporcionam na prática
- Usa cabeçalho em blocos quando fizer sentido pro produto, no estilo dos exemplos (ex: "DIMENSÕES:",
  "MEDIDAS DO PRODUTO;", "Composição:", "Contém;") -- só inclua os blocos que fizerem sentido pra
  esse produto especificamente, não force bloco que não se aplica
- Se o produto se beneficiar de explicar "onde usar" ou "como conservar/cuidar", pode usar o formato
  de pergunta como nos exemplos ("- Onde usar...", "- Como conservar...") -- só se fizer sentido,
  não é obrigatório em todo produto
- Frases objetivas, sem enrolação, tom técnico mas acessível
- IMPORTANTE -- ANTECIPE DÚVIDAS: pense em qualquer dúvida prática que o cliente teria e que, se não
  respondida, faria ele hesitar na compra ou procurar em outro anúncio. Baseado nos atributos
  específicos desse produto, responda proativamente coisas como:
  * Se a cor/material de uma superfície de escrita não for branca ou clara (ex: folhas pretas),
    oriente qual tipo de caneta/material funciona bem nela (ex: folha preta pede caneta gel branca,
    marcador metálico ou paint pen -- caneta comum não aparece)
  * Se o produto usa energia (pilha, bateria recarregável, tomada), informe a fonte de energia e,
    se souber, a autonomia
  * Se o material pede cuidado especial de limpeza/conservação, oriente como cuidar
  Só inclua esses pontos se fizerem sentido pro produto em questão -- não force pergunta que não
  se aplica

PRODUTO: {dados.get('nome_produto','')}
Categoria: {dados.get('categoria','')}
Medidas: {dados.get('medidas','')}
Peso: {dados.get('peso','')}
Material: {dados.get('material','')}
Cor: {dados.get('cor','')}
Diferenciais: {dados.get('diferenciais','')}
Uso/ocasião: {dados.get('uso','')}
Características adicionais: {dados.get('caracteristicas','')}
Palavras-chave pra usar com naturalidade (sem forçar todas): {dados.get('palavras_chave','') or 'nenhuma informada'}
{bloco_capacidade}{bloco_capacidade_argola}{bloco_usos_pesquisados}{bloco_observacoes}
REGRAS OBRIGATÓRIAS (política oficial do Mercado Livre):
- NÃO inclua links externos, nome de loja, telefone, e-mail ou qualquer contato fora da plataforma
- NÃO inclua informações de entrega/frete (isso é campo separado do anúncio)
- NÃO inclua condição do produto (novo/usado) -- isso já é campo separado
- NÃO use texto em caixa alta pra frases inteiras, nem promoção/desconto/frete grátis
- NÃO force todas as palavras-chave no texto -- use as que fizerem sentido natural

Responda SOMENTE com o texto da descrição, pronta pra colar no anúncio, sem comentário extra.
"""
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=900,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text.strip()


def editar_descricao(descricao_atual, instrucao):
    """Ajuste pontual em cima do texto ja gerado -- recebe o texto completo atual
    e devolve o texto completo ja ajustado, sem regerar do zero."""
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    prompt = f"""Esta é a descrição atual de um anúncio de e-commerce:

=== DESCRIÇÃO ATUAL ===
{descricao_atual}
=== FIM DA DESCRIÇÃO ATUAL ===

O colaborador pediu este ajuste pontual: "{instrucao}"

Aplique SOMENTE esse ajuste, mantendo o resto do texto exatamente como está (mesma estrutura,
mesmo estilo, mesmos blocos). Não regere a descrição do zero, apenas edite o que foi pedido.

Continue seguindo as regras do Mercado Livre: sem link externo, sem contato, sem informação de
frete/entrega, sem condição do produto, sem caixa alta, sem termo promocional.

Responda SOMENTE com o texto completo da descrição já ajustada, sem comentário extra.
"""
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=900,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text.strip()


def pagina_descricao(usuario_logado):
    st.subheader("Descrição")
    st.caption("Busca a Triagem do produto automaticamente (editável). Antes de gerar, você confere um resumo dos dados que serão usados.")

    import triagem

    busca = st.text_input("Nome do produto", key="desc_busca_nome")

    dados_iniciais = {"nome_produto": "", "categoria": "", "medidas": "", "peso": "",
                       "material": "", "cor": "", "uso": "", "caracteristicas": "",
                       "diferenciais": ""}
    aviso = None

    if busca:
        encontrados = triagem.buscar_triagens_por_trecho(busca)
        if len(encontrados) == 1:
            t = encontrados[0]
            dados_iniciais.update({
                "nome_produto": t.get("nome_comercial", ""), "categoria": t.get("categoria", ""),
                "medidas": t.get("medidas", ""), "peso": t.get("peso", ""),
                "material": t.get("material", ""), "cor": t.get("variacao_cores", ""),
                "uso": t.get("uso", ""), "caracteristicas": t.get("caracteristicas", ""),
                "diferenciais": t.get("diferenciais", ""),
            })
            aviso = ("info", f"Triagem encontrada: **{t['nome_comercial']}**. Confira os dados abaixo -- pode editar antes de gerar.")
        elif len(encontrados) > 1:
            nomes = [e["nome_comercial"] for e in encontrados]
            escolha = st.selectbox("Mais de um produto encontrado com esse nome -- qual é?", nomes, key="desc_escolha")
            t = next(e for e in encontrados if e["nome_comercial"] == escolha)
            dados_iniciais.update({
                "nome_produto": t.get("nome_comercial", ""), "categoria": t.get("categoria", ""),
                "medidas": t.get("medidas", ""), "peso": t.get("peso", ""),
                "material": t.get("material", ""), "cor": t.get("variacao_cores", ""),
                "uso": t.get("uso", ""), "caracteristicas": t.get("caracteristicas", ""),
                "diferenciais": t.get("diferenciais", ""),
            })
            aviso = ("info", "Confira os dados abaixo -- pode editar antes de gerar.")
        else:
            dados_iniciais["nome_produto"] = busca
            aviso = ("warning", "Nenhuma triagem encontrada pra esse produto ainda -- preencha os campos abaixo.")

    if aviso:
        getattr(st, aviso[0])(aviso[1])

    with st.form("form_descricao"):
        col1, col2 = st.columns(2)
        nome_produto = col1.text_input("Nome do produto", value=dados_iniciais["nome_produto"], key="desc_nome_produto")
        categorias = sorted(ML_COMISSAO_POR_CATEGORIA.keys())
        cat_atual = dados_iniciais["categoria"]
        idx_cat = categorias.index(cat_atual) if cat_atual in categorias else 0
        categoria = col2.selectbox("Categoria no ML", categorias, index=idx_cat, key="desc_categoria")

        col1, col2 = st.columns(2)
        medidas = col1.text_input("Medidas (AxLxP, cm)", value=dados_iniciais["medidas"], placeholder="ex: 33x33x6")
        peso = col2.text_input("Peso", value=dados_iniciais["peso"], placeholder="ex: 700g")

        col1, col2 = st.columns(2)
        material = col1.text_input("Material", value=dados_iniciais["material"])
        cor = col2.text_input("Cor / variação de cores", value=dados_iniciais["cor"])

        uso = st.text_input("Uso / ocasião", value=dados_iniciais["uso"], key="desc_uso")
        caracteristicas = st.text_area("Características adicionais", value=dados_iniciais["caracteristicas"])
        diferenciais = st.text_area("Diferenciais", value=dados_iniciais["diferenciais"], key="desc_diferenciais")
        palavras_chave_txt = st.text_area("Palavras-chave pra usar com naturalidade (opcional -- cola aqui as que já geramos, se quiser)")

        st.markdown("---")
        st.markdown("##### Cálculo auxiliar (opcional)")
        modo_calculo = st.selectbox(
            "Esse produto precisa de algum cálculo de capacidade na descrição?",
            ["Nenhum", "Álbum de fotos (capacidade de fotos por página)", "Argola/espiral (capacidade de folhas)"],
            key="desc_modo_calculo",
        )

        num_folhas = tam_polaroid = tam_padrao = ""
        medida_interna_mm = espessuras_texto = ""

        if modo_calculo.startswith("Álbum"):
            st.caption("Tamanhos clássicos/padrão de mercado -- ajusta se o seu fornecedor usar outro tamanho.")
            col1, col2, col3 = st.columns(3)
            num_folhas = col1.text_input("Número de folhas do álbum", placeholder="ex: 20")
            tam_polaroid = col2.text_input("Tamanho Polaroid clássica (cm)", value="10x11")
            tam_padrao = col3.text_input("Tamanho foto padrão (cm)", value="10x15")
        elif modo_calculo.startswith("Argola"):
            st.caption("Use a medida INTERNA real (meça com régua) -- o tamanho vendido/nominal (ex: '30mm') costuma ser maior que o espaço útil de verdade.")
            col1, col2 = st.columns(2)
            medida_interna_mm = col1.text_input("Medida interna da argola/espiral (mm)", placeholder="ex: 29")
            espessuras_texto = col2.text_input("Espessuras de folha a calcular (mm)", value="1, 1.5, 2")

        observacoes = st.text_area("Observações (peça aqui o que quiser destacar na descrição)",
                                     placeholder="ex: Quero que ressalte os diferenciais e o que o produto oferece ao comprador, com um parágrafo curto sobre durabilidade da capa dura...")

        pesquisar_usos = st.checkbox("🔎 Pesquisar usos possíveis desse produto na internet (opcional -- adiciona tempo, útil se o campo Uso/ocasião pode estar incompleto)")

        confirmar = st.form_submit_button("Conferir dados e gerar", type="primary", use_container_width=True)

    if confirmar:
        if not nome_produto:
            st.warning("Preencha pelo menos o Nome do produto.")
        else:
            capacidade_texto = formula_texto = erro_capacidade = None
            capacidade_argola_texto = erro_capacidade_argola = None

            if modo_calculo.startswith("Álbum") and (num_folhas or (medidas and (tam_polaroid or tam_padrao))):
                capacidade_texto, formula_texto, erro_capacidade = calcular_capacidade(medidas, num_folhas, tam_polaroid, tam_padrao)
            elif modo_calculo.startswith("Argola") and (medida_interna_mm or espessuras_texto):
                capacidade_argola_texto, erro_capacidade_argola = calcular_capacidade_argola(medida_interna_mm, espessuras_texto)

            usos_pesquisados = erro_pesquisa = None
            if pesquisar_usos:
                with st.spinner("Pesquisando usos possíveis na internet..."):
                    usos_pesquisados, erro_pesquisa = pesquisar_usos_produto(nome_produto)

            st.session_state["desc_dados_pendentes"] = {
                "nome_produto": nome_produto, "categoria": categoria, "medidas": medidas, "peso": peso,
                "material": material, "cor": cor, "uso": uso, "caracteristicas": caracteristicas,
                "diferenciais": diferenciais, "palavras_chave": palavras_chave_txt,
                "observacoes": observacoes, "capacidade_texto": capacidade_texto,
                "formula_texto": formula_texto, "erro_capacidade": erro_capacidade,
                "capacidade_argola_texto": capacidade_argola_texto, "erro_capacidade_argola": erro_capacidade_argola,
                "usos_pesquisados": usos_pesquisados, "erro_pesquisa": erro_pesquisa,
            }

    if "desc_dados_pendentes" in st.session_state:
        dados = st.session_state["desc_dados_pendentes"]

        st.markdown("---")
        st.markdown("##### Confirme os dados antes de gerar")
        st.markdown(
            f"- **Produto:** {dados['nome_produto']}\n"
            f"- **Categoria:** {dados['categoria']}\n"
            f"- **Medidas:** {dados['medidas'] or '_(vazio)_'}\n"
            f"- **Peso:** {dados['peso'] or '_(vazio)_'}\n"
            f"- **Material:** {dados['material'] or '_(vazio)_'}\n"
            f"- **Cor:** {dados['cor'] or '_(vazio)_'}\n"
            f"- **Uso/ocasião:** {dados['uso'] or '_(vazio)_'}\n"
            f"- **Características:** {dados['caracteristicas'] or '_(vazio)_'}\n"
            f"- **Diferenciais:** {dados['diferenciais'] or '_(vazio)_'}\n"
            f"- **Observações:** {dados['observacoes'] or '_(vazio)_'}"
        )
        if dados["capacidade_texto"]:
            st.success("Capacidade de fotos calculada:\n\n" + dados["capacidade_texto"])
        elif dados["erro_capacidade"]:
            st.warning(f"Capacidade de fotos não incluída: {dados['erro_capacidade']}")

        if dados.get("capacidade_argola_texto"):
            st.success("Capacidade de folhas calculada:\n\n" + dados["capacidade_argola_texto"])
        elif dados.get("erro_capacidade_argola"):
            st.warning(f"Capacidade de folhas não incluída: {dados['erro_capacidade_argola']}")

        if dados.get("usos_pesquisados"):
            st.info("Usos encontrados na pesquisa (a IA vai considerar incluir se fizer sentido):\n\n" + dados["usos_pesquisados"])
        elif dados.get("erro_pesquisa"):
            st.warning(f"Pesquisa de usos não incluída: {dados['erro_pesquisa']}")

        st.caption("Se algo estiver errado ou desatualizado, ajusta no formulário acima e clica em 'Conferir dados e gerar' de novo.")

        if st.button("✅ Está tudo certo, gerar descrição", type="primary", use_container_width=True):
            with st.spinner("Gerando descrição..."):
                descricao = gerar_descricao(dados)

            import atividades
            atividades.registrar_atividade(usuario_logado, "Descrição", dados["nome_produto"], f"{len(descricao)} caracteres")

            del st.session_state["desc_dados_pendentes"]
            st.session_state["desc_texto_atual"] = descricao
            st.session_state["desc_nome_atual"] = dados["nome_produto"]
            st.session_state["desc_chat_log"] = []

    # Resultado + chat de ajuste pontual -- fica fora do "if confirmar" pra
    # sobreviver aos reruns disparados pelo proprio chat_input
    if "desc_texto_atual" in st.session_state:
        st.markdown("---")
        st.markdown(f"#### Descrição — {st.session_state['desc_nome_atual']}")
        st.text_area("Pronta pra copiar", value=st.session_state["desc_texto_atual"], height=350, key="desc_resultado")
        st.caption(f"{len(st.session_state['desc_texto_atual'])}/10.000 caracteres (limite do Mercado Livre pra descrição)")

        st.markdown("##### Precisa ajustar algo pontual?")
        st.caption("Ex: 'deixa mais curto', 'troca X por Y', 'tira o parágrafo sobre Z' -- ajusta só o que pedir, sem regerar do zero.")

        for autor, texto in st.session_state.get("desc_chat_log", []):
            with st.chat_message(autor):
                st.markdown(texto)

        instrucao = st.chat_input("Digite o ajuste que precisa...")
        if instrucao:
            st.session_state["desc_chat_log"].append(("user", instrucao))
            with st.spinner("Ajustando..."):
                novo_texto = editar_descricao(st.session_state["desc_texto_atual"], instrucao)
            st.session_state["desc_texto_atual"] = novo_texto
            st.session_state["desc_chat_log"].append(("assistant", "Ajustado! ✅ (confira o texto atualizado acima)"))

            import atividades
            atividades.registrar_atividade(usuario_logado, "Ajuste de Descrição", st.session_state["desc_nome_atual"], instrucao[:100])

            st.rerun()
