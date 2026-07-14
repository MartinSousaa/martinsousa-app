import streamlit as st
import anthropic
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


def gerar_descricao(dados):
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "")

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
        model="claude-sonnet-4-6", max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text.strip()


def pagina_descricao(usuario_logado):
    st.subheader("Descrição")
    st.caption("Formulário sempre novo (não puxa Triagem salva) -- garante que a descrição usa dados atuais do produto, sem risco de informação desatualizada.")

    with st.form("form_descricao"):
        col1, col2 = st.columns(2)
        nome_produto = col1.text_input("Nome do produto", key="desc_nome_produto")
        categoria = col2.selectbox("Categoria no ML", sorted(ML_COMISSAO_POR_CATEGORIA.keys()), key="desc_categoria")

        col1, col2 = st.columns(2)
        medidas = col1.text_input("Medidas (AxLxP, cm)", placeholder="ex: 33x33x6")
        peso = col2.text_input("Peso", placeholder="ex: 700g")

        col1, col2 = st.columns(2)
        material = col1.text_input("Material")
        cor = col2.text_input("Cor / variação de cores")

        uso = st.text_input("Uso / ocasião", key="desc_uso")
        caracteristicas = st.text_area("Características adicionais")
        diferenciais = st.text_area("Diferenciais", key="desc_diferenciais")
        palavras_chave_txt = st.text_area("Palavras-chave pra usar com naturalidade (opcional -- cola aqui as que já geramos, se quiser)")

        gerar = st.form_submit_button("Gerar Descrição", type="primary", use_container_width=True)

    if gerar:
        if not nome_produto:
            st.warning("Preencha pelo menos o Nome do produto.")
            return

        dados = {
            "nome_produto": nome_produto, "categoria": categoria, "medidas": medidas, "peso": peso,
            "material": material, "cor": cor, "uso": uso, "caracteristicas": caracteristicas,
            "diferenciais": diferenciais, "palavras_chave": palavras_chave_txt,
        }
        with st.spinner("Gerando descrição..."):
            descricao = gerar_descricao(dados)

        import atividades
        atividades.registrar_atividade(usuario_logado, "Descrição", nome_produto, f"{len(descricao)} caracteres")

        st.markdown("---")
        st.markdown(f"#### Descrição — {nome_produto}")
        st.text_area("Pronta pra copiar", value=descricao, height=350, key="desc_resultado")
        st.caption(f"{len(descricao)}/10.000 caracteres (limite do Mercado Livre pra descrição)")
