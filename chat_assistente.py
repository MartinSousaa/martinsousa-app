"""
chat_assistente.py
Chat IA unificado — Python puro, renderizado no sidebar do Streamlit.
Acesso total ao session_state: conhece produto ativo, títulos gerados,
descrição atual e galeria de imagens. Detecta intenção (Q&A vs comando)
e executa ações diretamente no session_state.
"""
import streamlit as st
import anthropic
import os
import re
import json
import base64


# ── PROMPT DO SISTEMA ─────────────────────────────────────────────────────────

SYSTEM_BASE = """Você é o Assistente do MS Studio, aplicativo interno da MartinSousa para
gestão de produtos em marketplaces (Mercado Livre, Shopee, Shein).

=== COMO RESPONDER: CURTO ===
De 3 a 6 linhas. Sempre.

Esta é a regra mais quebrada e a mais cobrada. O dono do Studio já pediu
resumo em quase toda mensagem, e o motivo é prático: quem lê está no meio de
uma tarefa, com o time esperando. Texto longo não é zelo — é conta que ele
paga em atenção.

Na prática:
- Tabela em vez de parágrafo, sempre que houver mais de dois itens.
- "Sim ou não" recebe "sim" ou "não" na PRIMEIRA palavra, e só depois o porquê.
- Nada de recapitular o que ele acabou de dizer antes de responder.
- Nada de listar o que você NÃO fez, nem de explicar seu raciocínio.
- Passo a passo numerado só quando pedirem como fazer.
- Confirmação de comando é UMA linha: o que foi disparado e onde ver.

A exceção é uma só: quando ele pedir explicitamente um relatório ou detalhe.

=== ESTRUTURA DO APP ===
O MS Studio tem as seguintes abas (menu lateral esquerdo):

• Título — gera 2 opções de título para uso em qualquer marketplace (ML, Shopee, Shein) — o mesmo título serve para todas as plataformas.
  Campos obrigatórios: nome do produto, categoria, material, diferenciais.
  Ação principal: botão "Gerar Título". Resultado: 2 títulos aparecem na tela (máximo 60 caracteres cada, limite do ML).

• Descrição — gera descrição completa do produto.
  Campos obrigatórios: nome do produto, diferenciais, público-alvo.
  Ação principal: botão "Gerar Descrição".

• Imagem — gera imagens profissionais 1200x1200 para o anúncio (todas as plataformas).
  CAMPOS:
    - Nome do produto (obrigatório)
    - Código da descrição (opcional) — gerado na aba Descrição; ao informar aqui, a IA usa
      automaticamente as medidas, peso e cor da descrição vinculada
    - Fotos de referência: upload de quantas fotos o colaborador quiser (obrigatório para gerar)
    - "Descreva o que você quer nessa imagem": campo de texto livre onde o colaborador pode
      especificar textos, cenas, ângulos, cores, destaque — aparece quando o modo for
      "1 imagem específica" (para um tipo só), "Selecionar" ou "As 8 imagens do padrão"
      (observações gerais que se aplicam a todas as imagens)
  FLUXO (2 etapas obrigatórias — não tem como pular):
    1. Clicar em "🔍 Analisar e mostrar plano antes de gerar" → a IA mostra o plano de cada
       imagem (o que vai criar, textos, aviso se faltar informação). Imagens com dado faltante
       ficam marcadas como BLOQUEADAS e não são geradas.
    2. Revisar o plano → clicar "✅ Confirmar e gerar" para iniciar a geração.
  BLOQUEADA: aparece no PLANO quando um TIPO ESPECÍFICO de imagem precisa de dado que não foi
  fornecido. Exemplo: "Características técnicas" bloqueia se medidas e peso não estiverem no
  código de descrição vinculado. Solução: informar o código da descrição (que tem medidas/peso)
  ou escolher outro tipo de imagem.
  AJUSTE PÓS-GERAÇÃO: não há botão "Regenerar" — o colaborador pede ajuste aqui no chat.
  Ex: "refaça a Imagem 2 com fundo azul". O assistente envia o comando para a aba Imagem.
  O colaborador se refere às imagens pelo NÚMERO que aparece na legenda da galeria
  ("Imagem 1", "Imagem 2"...) ou pelo nome do tipo ("a capa", "a ambientação").
  TODAS as imagens geradas têm 1200x1200 px (padrão da empresa).

• Vídeo — gera o prompt de texto otimizado para o gerador de vídeo do Envato Elements.
  Campos obrigatórios: nome do produto e descrição da ação ("o que acontece no vídeo").
  Opcional mas recomendado: upload do frame inicial e frame final do vídeo.
  Ação principal: botão "Gerar Prompt". Resultado: prompt curto (2–4 frases) que o colaborador
  copia e cola manualmente no Envato Elements junto com as imagens dos frames.
  Após gerar, é possível pedir ajustes via chat de ajuste inline ou aqui mesmo no assistente.

• Financeiro — configuração de LPV (custo fixo por venda) e alíquota tributária, mês a mês por ano.
  O LPV informado aqui alimenta os cálculos de viabilidade (UC) em Título.

• Administrativo (apenas admin) — é AQUI que ficam: configuração de metas,
  cadastro da equipe/colaboradores, colunas do Trello e gestão de usuários.
  NÃO existe aba "Usuários" nem aba "Histórico" — nunca cite esses nomes.

=== ABAS QUE EXISTEM, LISTA COMPLETA ===
Gestão (só admin): Painel de Metas · Análise de Metas · Ponto · Financeiro · Administrativo
Operação: Triagem · Palavras-chave · Título · Descrição · Imagem · Vídeo
Colaborador não-admin vê apenas Painel de Metas e Análise de Metas em Gestão.
Nunca invente nome de aba. Se não souber onde fica algo, diga que não sabe.

=== FLUXO TÍPICO ===
1. Aba Título → preenche nome do produto, categoria, material e diferenciais → clica Gerar Título
2. Aba Descrição → preenche os campos → clica Gerar Descrição
3. Aba Imagem → faz upload de fotos de referência → escolhe tipos → analisa plano → confirma e gera

=== ORIENTAÇÃO SEM PRODUTO ABERTO ===
Quando não há produto em edição, o usuário ainda pode usar qualquer aba.
Oriente assim (NUNCA mencione botões que não existem, como "Editar", "Salvar produto", "Cadastrar", "Regenerar"):
- Para gerar título: "Vá até a aba Título, preencha o nome do produto, categoria, material e diferenciais, e clique em Gerar Título."
- Para gerar imagem: "Vá até a aba Imagem, faça o upload das fotos do produto, escolha o tipo de imagem, analise o plano e confirme para gerar."
- Para configurar financeiro: "Vá até a aba Financeiro, selecione o ano, preencha o LPV de cada mês e salve."
- Para ajustar uma imagem gerada: "Descreva o ajuste aqui no chat — eu envio o comando para a aba Imagem, ou você pode usar o modo Ajuste Fino diretamente na aba Imagem."

=== REGRAS DE NEGÓCIO ===
- UC mínimo aprovado: 0,8/1 (abaixo = INVIÁVEL)
- UC 0,7 = cenário de risco; UC 1,0 = equilíbrio ideal
- Mercado Livre: comissão por categoria (8%–16%), frete por peso cubado
  (comprimento × largura × altura / 6.000 — produto embalado)
- Shopee: comissão 15%–20% + R$4 adicional em produtos até R$79,99; frete grátis (vendedor não paga)
- Shein: comissão 18% flat; frete por peso real (tabela por faixas de kg)
- LPV = custo fixo médio por venda (informado manualmente na aba Financeiro)
- NF = alíquota tributária (configurada na aba Financeiro — não é calculada automaticamente)
- Custo operacional padrão inclui embalagem, logística, ADS e cross docking
- Peso e dimensões devem ser sempre do produto JÁ EMBALADO

Tom: objetivo, informal mas profissional. Responda sempre em português do Brasil.
Quando não souber algo, diga claramente em vez de inventar.

=== ACESSO AO BANCO DE DADOS ===
Você TEM acesso TOTAL ao banco de dados do MS Studio via Google Sheets.
Quando o colaborador mencionar um código de produto (ex: MS-LBUM-0731K1H), os dados
completos desse produto aparecerão no CONTEXTO DO APP abaixo — cor, medidas, peso,
material, características, diferenciais, uso e categoria.
Se aparecerem dados do produto no contexto, USE-OS para responder perguntas e
para preencher informações que estavam faltando na triagem de imagens.

=== PREENCHIMENTO DE DADOS DA TRIAGEM ===
Quando o colaborador fornecer informações que estavam faltando para imagens BLOQUEADAS
(peso, medidas, material, capacidade, etc.), você deve:
1. Confirmar os dados recebidos
2. Usar o CMD "preencher_dados_triagem" para atualizar o banco de dados da triagem
3. A tela será atualizada automaticamente e a triagem será refeita com os novos dados

Exemplo do CMD:
<CMD>{"acao":"preencher_dados_triagem","dados":{"peso":"850g","medidas":"30x30x2cm","material":"capa dura, folhas de papel fotográfico pretas","capacidade":"120 fotos","diferenciais":"folhas pretas sofisticadas"}}</CMD>"""


def _buscar_dados_produto_db(codigo: str) -> dict | None:
    """Busca dados completos do produto no banco de dados pelo código."""
    if not codigo or not codigo.strip():
        return None
    try:
        import atividades as _atv
        return _atv.buscar_por_codigo(codigo.strip())
    except Exception:
        return None


def _mime_tipo(data: bytes) -> str:
    """Detecta o MIME type pelos magic bytes."""
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if data[:2] == b'\xff\xd8':
        return "image/jpeg"
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return "image/webp"
    return "image/jpeg"


def _api_key():
    """Pelo módulo `chaves`: um jeito só de ler, em todo o Studio."""
    import chaves as _ch
    return _ch.ler("ANTHROPIC_API_KEY")


def _contexto_atual() -> str:
    """Monta bloco de contexto com o que está aberto no app."""
    partes = []

    # Nome do produto (várias fontes possíveis)
    nome = (
        (st.session_state.get("tt_dados_produto") or {}).get("nome_comercial")
        or st.session_state.get("desc_nome_atual")
        or st.session_state.get("img_nome_produto")
        or st.session_state.get("img_nome_produto_input")
        or None
    )
    if nome:
        partes.append(f"PRODUTO EM EDIÇÃO: {nome}")

    # Títulos gerados
    titulos = st.session_state.get("tt_titulos_gerados")
    if titulos:
        linhas = "\n".join(f"  Opção {i+1}: {t}" for i, t in enumerate(titulos))
        partes.append(f"TÍTULOS ATUAIS:\n{linhas}")

    # Descrição — inclui código para referência
    desc_codigo = st.session_state.get("desc_codigo_atual", "")
    desc = st.session_state.get("desc_texto_atual", "")
    if desc:
        trecho = desc[:500] + ("…" if len(desc) > 500 else "")
        codigo_info = f" (código: {desc_codigo})" if desc_codigo else ""
        partes.append(f"DESCRIÇÃO ATUAL{codigo_info} (trecho):\n{trecho}")

    # Estado atual do formulário de imagem (o que o colaborador está configurando)
    img_nome_form = st.session_state.get("img_nome_produto_input", "")
    img_codigo_form = st.session_state.get("img_codigo_input", "")
    img_triagem = st.session_state.get("img_triagem_plano")
    img_triagem_cfg = st.session_state.get("img_triagem_config", {})

    if img_nome_form or img_codigo_form or img_triagem:
        info_img = []
        if img_nome_form:
            info_img.append(f"  Produto no formulário: {img_nome_form}")
        if img_codigo_form:
            info_img.append(f"  Código da descrição informado: {img_codigo_form}")
            # Busca dados completos do produto no banco de dados
            dados_db = _buscar_dados_produto_db(img_codigo_form)
            if dados_db:
                info_img.append(f"  DADOS DO PRODUTO NO BANCO DE DADOS (código {img_codigo_form}):")
                for campo, label in [("nome_produto","Nome"), ("cor","Cor"), ("medidas","Medidas"),
                                      ("peso","Peso"), ("material","Material"),
                                      ("caracteristicas","Características"),
                                      ("diferenciais","Diferenciais"), ("uso","Uso"),
                                      ("categoria","Categoria")]:
                    val = dados_db.get(campo, "")
                    if val:
                        info_img.append(f"    {label}: {val}")
            else:
                info_img.append(f"  ⚠️ Código {img_codigo_form} não encontrado no banco de dados")
        # Também busca pelo código já vinculado na triagem
        if not img_codigo_form and img_triagem_cfg.get("codigo"):
            dados_db = _buscar_dados_produto_db(img_triagem_cfg["codigo"])
            if dados_db:
                info_img.append(f"  DADOS DO PRODUTO VINCULADO À TRIAGEM (código {img_triagem_cfg['codigo']}):")
                for campo, label in [("cor","Cor"), ("medidas","Medidas"), ("peso","Peso"),
                                      ("material","Material"), ("caracteristicas","Características"),
                                      ("diferenciais","Diferenciais"), ("uso","Uso")]:
                    val = dados_db.get(campo, "")
                    if val:
                        info_img.append(f"    {label}: {val}")
        if img_triagem:
            plano = img_triagem.get("plano", [])
            bloqueadas = [i for i in plano if not i.get("viavel", True)]
            viaveis = [i for i in plano if i.get("viavel", True)]
            info_img.append(f"  Plano de triagem: {len(viaveis)} imagem(ns) viável(is), {len(bloqueadas)} bloqueada(s)")
            for b in bloqueadas:
                info_img.append(f"    BLOQUEADA: {b.get('tipo','')} — {b.get('pergunta_info','')}")
        if info_img:
            partes.append("CONFIGURAÇÃO DE IMAGEM EM ANDAMENTO:\n" + "\n".join(info_img))

    # Galeria de imagens geradas
    galeria = st.session_state.get("img_galeria")
    if galeria:
        tipos = [f"  Imagem {i+1}: {g.get('tipo','?')}" for i, g in enumerate(galeria)]
        partes.append(
            f"GALERIA DE IMAGENS ({len(galeria)} imagem(ns)):\n" + "\n".join(tipos)
            + "\n(É por este número que o colaborador se refere a cada imagem — "
              "é o mesmo que aparece na legenda da tela.)"
        )

    return "\n\n".join(partes) if partes else "Nenhum produto em edição no momento."


def _bloco_quem_fala(usuario="", eh_admin=None):
    """Diz ao assistente com quem ele esta falando e o que essa pessoa enxerga.

    Sem isso ele cumprimentava pelo nome e na frase seguinte respondia "se voce
    for admin, pode consultar la" — o nome vinha da saudacao, o perfil nao vinha
    de lugar nenhum.
    """
    if not usuario:
        return ""
    if eh_admin is None:
        try:
            import auth as _auth
            eh_admin = _auth.is_admin(usuario)
        except Exception:
            eh_admin = False
    if eh_admin:
        acesso = ("É ADMIN: enxerga Gestão inteira (Painel de Metas, Análise de "
                  "Metas, Ponto, Financeiro, Administrativo) e toda a Operação. "
                  "NUNCA responda 'se você for admin' — ele é. Diga direto onde fica.")
    else:
        acesso = ("NÃO é admin: em Gestão vê apenas Painel de Metas e Análise de "
                  "Metas, e vê toda a Operação. Não tem acesso a Ponto, "
                  "Financeiro nem Administrativo — não mande ele para lá.")
    return (f"\n\n=== QUEM ESTÁ FALANDO COM VOCÊ ===\n"
            f"Usuário logado: {usuario}\n{acesso}\n"
            + REGRA_FERRAMENTAS)


REGRA_FERRAMENTAS = """
=== CONSULTE ANTES DE RESPONDER ===
Você tem ferramentas de leitura e está DENTRO do Studio. A regra é uma só:

  Se a pergunta é sobre um dado que existe no sistema, CONSULTE e responda com
  o número. Nunca explique onde encontrar um dado que você mesmo pode ler.

Exemplos de como agir:
- "quanto está o LPV?" -> ler_financeiro -> "R$ 19,68, de Junho/2026 — e está 2
  meses atrasado." NÃO mande a pessoa até a aba Financeiro.
- "quantos cartões atrasados temos?" -> ler_painel_metas. "Cartão" aqui é
  cartão do TRELLO, trabalho da equipe. Nunca é cartão de crédito, e o Studio
  não tem contas a receber.
- "qual o título atual?" -> ler_produto_aberto. Se não houver, a primeira frase
  é "Ainda não há título gerado nesta sessão".
- "gera o título da caneca" -> buscar_triagem ANTES de pedir categoria,
  material ou diferenciais: quase sempre já estão salvos. Só pergunte o que
  faltar de verdade, dizendo o que já encontrou.
- "quantos colaboradores temos?" -> ler_equipe.

Nunca invente número. Se a ferramenta falhar, diga que não conseguiu consultar
agora — não caia no passo a passo.
Depois de consultar, responda em 1 a 3 frases. Passo a passo só quando
perguntarem COMO FAZER alguma coisa.
"""


# ── A LINGUAGEM COM QUEM USA, E ELA VALE SEMPRE ─────────────────────────────
#
# Relato de 25/09: "ele está exigindo linguagem técnica, está falando sobre
# diminuir a imagem com % e sobre espaçamento". E a mensagem de falha do
# ajuste devolvia a lição de casa para quem pediu: "tente descrever de outro
# jeito".
#
# Esta regra morava no ramo de quem JÁ tem conteúdo gerado — e a conversa
# começa antes disso. Agora ela é do sistema inteiro.
LINGUAGEM = """

COMO VOCÊ FALA COM A PESSOA
Duas linguagens, e não se misturam:
- A instrução que vai DENTRO do <CMD> é para o gerador de imagem. Ali pode e
  deve ser técnica: porcentagem de margem, posição, tamanho relativo.
- O que você escreve FORA do <CMD> é para uma pessoa que está trabalhando.
  Ali nada de pixel, porcentagem, "espaçamento", "enquadramento", "resolução"
  ou "proporção". Diga em palavras do dia a dia: "os textos estão encostando
  na borda", "a caixa preta aparece e não devia", "a frase está cortada".

E NUNCA peça que ela escreva de outro jeito, nem que divida o pedido, nem que
use termo técnico. O pedido dela já está claro — o trabalho de traduzir para
o gerador é SEU. Se uma correção não saiu, diga o que você já tentou e o que
vai tentar agora, em uma linha."""


def _montar_system(usuario="", eh_admin=None) -> str:
    """Monta o system prompt completo com contexto dinâmico."""
    ctx = _contexto_atual() + _bloco_quem_fala(usuario, eh_admin)

    tem_titulos = bool(st.session_state.get("tt_titulos_gerados"))
    tem_desc    = bool(st.session_state.get("desc_texto_atual"))
    tem_imgs    = bool(st.session_state.get("img_galeria"))

    if not (tem_titulos or tem_desc or tem_imgs):
        # Só Q&A — sem conteúdo gerado disponível para editar
        nota_orientacao = (
            "\n\n--- CONTEXTO DO APP ---\n"
            + ctx
            + "\n\nNota: não há títulos, descrição nem imagens gerados no momento.\n"
            "RESPONDA A PERGUNTA ANTES DE ENSINAR. Quando perguntarem sobre algo que "
            "não existe ainda ('qual o título atual?', 'como está a descrição?'), a "
            "primeira frase tem que ser a resposta: 'Ainda não há título gerado nesta "
            "sessão.' Só DEPOIS, e em uma linha, diga onde se faz. Passo a passo "
            "numerado só quando pedirem como fazer — perguntar o que existe não é "
            "pedir tutorial.\n"
            "Se o usuário pedir ajuda para usar o app, oriente-o a acessar a aba correta "
            "e preencher os campos necessários conforme descrito na seção ORIENTAÇÃO SEM PRODUTO ABERTO acima. "
            "Nunca sugira ações como clicar em 'Editar' ou 'Salvar produto' — esses botões não existem."
        )
        return f"{SYSTEM_BASE}{nota_orientacao}{LINGUAGEM}"

    cmds_exemplo = []
    if tem_titulos:
        cmds_exemplo.append('{"acao":"alterar_titulo","titulos":["Título 1 ajustado","Título 2 ajustado"]}')
    if tem_desc:
        cmds_exemplo.append('{"acao":"alterar_descricao","texto":"nova descrição completa aqui"}')
    if tem_imgs:
        cmds_exemplo.append('{"acao":"ajustar_imagem","imagem":1,"instrucao":"instrução de edição para a imagem"}')
        cmds_exemplo.append('{"acao":"refazer_imagem","imagem":1,"instrucao":"como a imagem deve ficar, do zero"}')
        cmds_exemplo.append('{"acao":"refazer_todas_imagens","instrucao":"o que mudar em todas"}')
        cmds_exemplo.append('{"acao":"gerar_imagens_faltantes"}')

    # Sempre disponível quando há triagem com bloqueios — independe de imgs geradas
    tem_triagem_bloqueada = bool(
        (st.session_state.get("img_triagem_plano") or {}).get("plano") and
        any(not i.get("viavel", True) for i in (st.session_state.get("img_triagem_plano") or {}).get("plano", []))
    )
    if tem_triagem_bloqueada:
        cmds_exemplo.append('{"acao":"preencher_dados_triagem","dados":{"peso":"valor","medidas":"valor","material":"valor"}}')

    exemplos_str = "\n".join(f"- <CMD>{c}</CMD>" for c in cmds_exemplo)

    instrucao_cmd = f"""
--- CONTEXTO DO APP ---
{ctx}

--- COMANDOS DISPONÍVEIS ---
Quando o colaborador pedir alteração em conteúdo já gerado, faça o ajuste E inclua ao final
da sua resposta um bloco <CMD>...</CMD> com o JSON do comando:

{exemplos_str}

REGRAS DOS COMANDOS:
- "alterar_titulo": inclua os 2 títulos COMPLETOS e já ajustados (não coloque placeholders)
- "alterar_descricao": inclua o texto COMPLETO da nova descrição
- "refazer_imagem": quando a mudança pedida for de COMPOSIÇÃO — outro
  enquadramento, outro arranjo dos objetos, "siga o padrão desta referência",
  mudar o que está onde. O ajuste NÃO faz isso: ele edita regiões e preserva o
  resto, então devolve a imagem intacta e ninguém entende por quê. Na dúvida
  entre ajustar e refazer, olhe o tamanho da mudança: mexer num objeto é
  ajuste; reorganizar o quadro é refazer.

- "ajustar_imagem": use o NÚMERO da imagem na galeria (o mesmo da legenda). Descreva
  apenas o que muda — o resto da imagem é preservado. Um comando POR IMAGEM, e
  TODOS na mesma resposta: se ele pedir a mesma mudança nas imagens 2, 3 e 6,
  emita os três blocos <CMD> de uma vez. Nunca faça um e prometa os outros para
  a mensagem seguinte — isso já aconteceu e obrigou o colaborador a cobrar duas
  vezes o que ele tinha pedido uma.
  REGRA CENTRAL: imagem que o colaborador NÃO citou não pode ser tocada. Se ele
  pedir "deixa a imagem 1 com fundo branco", só a imagem 1 muda — as outras ficam
  exatamente como estão. Na dúvida sobre qual imagem é, PERGUNTE o número antes de
  emitir o comando; nunca chute e nunca aplique a todas por precaução.

  OLHE ANTES. Sempre. Chame `ver_imagem` na imagem citada ANTES de emitir o
  comando — nesta conversa, para esta imagem, mesmo que você já a tenha visto
  antes de um ajuste anterior (ela mudou desde então). Emitir o comando sem ter
  olhado é proibido, e não tem exceção: "parece simples" e "ele foi claro" são
  justamente os casos em que se erra.
  O motivo: o colaborador descreve o que ELE está vendo. "Tira essa borda", "o
  produto ficou pequeno", "a cor está errada" só querem dizer alguma coisa para
  quem olhou. Sem olhar você não sabe se existe borda, de que lado, quanto ela
  ocupa, quão pequeno é "pequeno", nem qual cor está errada.

  DEPOIS DE OLHAR, faça três coisas, nesta ordem:

  1. Diga numa linha o que você viu e vai mudar, com número: "Vi uma faixa
     branca de uns 15% na base da imagem 3 — é essa que sai?". É assim que o
     colaborador descobre que vocês falam da mesma coisa ANTES de gastar a
     rodada, e não depois.

  2. Escreva a instrução do comando para o GERADOR, não para o colaborador. Ela
     descreve o ESTADO FINAL da imagem, sempre no positivo, com referência
     espacial e proporção. Nunca repita as palavras dele como instrução — a
     instrução é a sua tradução do que você viu com o que ele quer.
       ele diz              você escreve
       "tira a borda"       "produto preenchendo todo o quadro, fundo branco
                            contínuo até o limite do arquivo, sem faixa nem
                            moldura em nenhuma das quatro bordas"
       "produto pequeno"    "produto ocupando cerca de 85% da altura do quadro,
                            centralizado"
       "cor errada"         "a alça do produto em azul-marinho, igual à foto de
                            referência; o corpo permanece branco"
     INSTRUÇÃO NEGATIVA NÃO FUNCIONA em geração de imagem: "sem borda", "não
     coloque texto", "tire a sombra" são pedidos que o modelo tende a ignorar,
     porque para atendê-los ele precisa primeiro imaginar a coisa. Diga o que
     DEVE existir, nunca o que não deve.

  3. Se depois de olhar ainda restarem duas leituras possíveis, PERGUNTE — com
     as opções que você viu, não em aberto: "vi uma faixa branca na base e uma
     sombra à direita; qual das duas?". Perguntar custa uma mensagem. Errar
     custa a rodada inteira, e o colaborador tem que pedir de novo.

  O QUE VOLTA: o ajuste é conferido automaticamente — a imagem antes e depois
  são comparadas com o pedido. Você recebe o veredito na tela. Se disser que
  não saiu, NÃO diga "pronto": diga o que faltou e proponha outra formulação.
  Você nunca sabe que um ajuste deu certo por ter enviado o comando; só por ter
  olhado o resultado ou lido o veredito.
- "gerar_imagens_faltantes": quando faltarem tipos do padrão na galeria e o
  colaborador pedir para completar ("faltam 2 imagens", "gera as que faltam").
  NÃO mande ele fazer o processo na aba Imagem — o comando faz isso. As imagens
  já geradas não são tocadas; as novas entram no fim da galeria.
- "refazer_todas_imagens": SOMENTE quando o colaborador pedir explicitamente que
  TODAS sejam refeitas ("refaz tudo", "gera tudo de novo"). Descarta a galeria e
  gera de novo do zero. Confirme com ele antes de emitir, dizendo quantas imagens
  serão perdidas.
- "preencher_dados_triagem": use quando o colaborador fornecer dados que estavam faltando para imagens BLOQUEADAS.
  O campo "dados" deve conter APENAS os campos que o colaborador informou (peso, medidas, material, capacidade, etc.).
  A triagem será refeita automaticamente com esses dados e as imagens bloqueadas serão reavaliadas.
- EMITA TODOS OS COMANDOS NA MESMA RESPOSTA. Três pedidos numa mensagem viram
  três blocos <CMD>, um embaixo do outro. Nunca faça o primeiro e deixe os
  outros para depois: quem pediu três coisas e viu uma acontecer tem de cobrar
  as outras duas, e você não é quem decide o que fica para a próxima mensagem.
  (Esta linha dizia o contrário — "APENAS UM bloco por resposta" — e era por
  isso que o segundo e o terceiro pedido sumiam sem explicação.)
- Para dúvidas sem alteração de conteúdo: responda normalmente, SEM bloco <CMD>"""

    return f"{SYSTEM_BASE}{instrucao_cmd}{LINGUAGEM}"


def _log(acao, instrucao="", imagem=None, tipo="", resultado=""):
    """Registra o comando na planilha. Nunca interrompe o fluxo."""
    try:
        import log_imagem
        log_imagem.registrar(acao, instrucao, imagem, tipo, resultado)
    except Exception:
        pass


def _norm_texto(v):
    """Minusculas, sem acento, so letras e numeros separados por espaco."""
    import re as _re
    import unicodedata as _ud
    s = _ud.normalize("NFKD", str(v)).encode("ascii", "ignore").decode("ascii").lower()
    return _re.sub(r"[^a-z0-9]+", " ", s).strip()


def _resolver_imagem(alvo, galeria):
    """Qual imagem da galeria o comando quer. Devolve o numero (1-based) ou None.

    Antes, qualquer valor que nao virasse numero caia num `foto_num = 1`. O
    prompt manda a IA perguntar quando estiver em duvida, mas o codigo escolhia
    por ela — e a duvida virava um ajuste silencioso na primeira imagem, que e
    justamente o erro que nao pode acontecer.

    Agora aceita as duas formas que o colaborador usa naturalmente: o numero
    ("imagem 3") e o nome do tipo ("a do fundo branco"). O nome so vale quando
    casa com UMA imagem — dois candidatos viram duvida, e duvida vira pergunta.
    """
    if not galeria:
        return None
    if isinstance(alvo, bool):
        return None
    if isinstance(alvo, int):
        return alvo if 1 <= alvo <= len(galeria) else None

    texto = _norm_texto(alvo or "")
    if not texto:
        return None
    if texto.isdigit():
        n = int(texto)
        return n if 1 <= n <= len(galeria) else None

    # "imagem 3", "foto 2", "a 4a" — pega o numero solto se houver so um.
    import re as _re_alvo
    numeros = _re_alvo.findall(r"\d+", texto)
    if len(numeros) == 1:
        n = int(numeros[0])
        if 1 <= n <= len(galeria):
            return n

    # Pelo nome do tipo: "fundo branco", "beneficios", "medidas".
    #
    # Texto que junta mais de um alvo ("a do fundo e a de medidas") nao e
    # resolvido por nome: so um dos nomes casaria, e o comando ajustaria uma
    # imagem calado enquanto a pessoa pediu duas. Melhor devolver a pergunta.
    if _re_alvo.search(r"(^| )(e|ou|todas|ambas|as duas)( |$)|,", texto):
        return None

    casos = []
    for i, g in enumerate(galeria):
        tipo = _norm_texto(g.get("tipo", ""))
        # O rotulo vem numerado ("1 fundo branco"); o numero atrapalha a
        # comparacao com o jeito que a pessoa fala ("a do fundo branco").
        nucleo = _re_alvo.sub(r"^[\d\s]+", "", tipo).strip()
        if not nucleo:
            continue
        if nucleo in texto or texto in nucleo:
            casos.append(i + 1)
    if len(casos) == 1:
        return casos[0]
    return None


def _executar_comando(cmd: dict) -> str | None:
    """Executa o comando extraído da resposta da IA. Retorna texto de feedback."""
    acao = cmd.get("acao", "")

    if acao == "alterar_titulo":
        novos = cmd.get("titulos", [])
        if novos and isinstance(novos, list) and st.session_state.get("tt_titulos_gerados") is not None:
            validos = [str(t).strip() for t in novos if str(t).strip()]
            if validos:
                st.session_state["tt_titulos_gerados"] = validos
                return "✅ Títulos atualizados — veja na aba **Título**."
        return None

    if acao == "alterar_descricao":
        novo = cmd.get("texto", "").strip()
        if novo and st.session_state.get("desc_texto_atual") is not None:
            st.session_state["desc_texto_atual"] = novo
            return "✅ Descrição atualizada — veja na aba **Descrição**."
        return None

    if acao == "ajustar_imagem":
        # Aceita "imagem" (nome atual) e "foto" (comandos antigos).
        alvo = cmd.get("imagem", cmd.get("foto"))
        instrucao = str(cmd.get("instrucao", "")).strip()
        galeria   = st.session_state.get("img_galeria")
        foto_num  = _resolver_imagem(alvo, galeria)
        if galeria and instrucao:
            if foto_num is None:
                nomes = "\n".join(
                    f"- **Imagem {i+1}** — {g.get('tipo','?')}"
                    for i, g in enumerate(galeria)
                )
                return (
                    "⚠️ Não ficou claro **qual imagem** ajustar, então não mexi "
                    "em nenhuma. Me diga o número:\n" + nomes
                )
            if "chat_img_pendente" not in st.session_state:
                st.session_state["chat_img_pendente"] = []
            st.session_state["chat_img_pendente"].append(
                {"num": foto_num, "instrucao": instrucao}
            )
            _log("ajustar_imagem", instrucao, imagem=foto_num,
                 tipo=galeria[foto_num - 1].get("tipo", ""))
            return (
                f"🔄 Instrução enviada para a **Imagem {foto_num}** — "
                "abra a aba **Imagem** para ver o resultado sendo gerado. "
                "As demais imagens não serão alteradas."
            )

    if acao == "refazer_imagem":
        # REFAZER uma, e nao AJUSTAR uma. Sao coisas diferentes e a diferenca
        # custou quatro rodadas sem resultado: o ajuste edita regioes e
        # preserva o resto, entao recompor o quadro inteiro passa do que ele
        # faz — e ele devolve a imagem intacta, sem erro nenhum. Aqui a imagem
        # nasce de novo, com a composicao definida no nascimento.
        alvo = cmd.get("imagem", cmd.get("foto"))
        galeria = st.session_state.get("img_galeria") or []
        foto_num = _resolver_imagem(alvo, galeria)
        if not galeria:
            return "⚠️ Não há imagens geradas para refazer."
        if foto_num is None:
            nomes = "\n".join(f"- **Imagem {i+1}** — {g.get('tipo','?')}"
                              for i, g in enumerate(galeria))
            return ("⚠️ Não ficou claro **qual imagem** refazer. Me diga o "
                    "número:\n" + nomes)
        instrucao = str(cmd.get("instrucao", "")).strip()
        st.session_state.setdefault("chat_refazer_imagem", []).append(
            {"num": foto_num, "instrucao": instrucao})
        _log("refazer_imagem", instrucao, imagem=foto_num,
             tipo=galeria[foto_num - 1].get("tipo", ""))
        return (f"🔁 **Imagem {foto_num}** será refeita do zero. As outras "
                f"{len(galeria) - 1} não são tocadas.")

    if acao == "gerar_imagens_faltantes":
        galeria = st.session_state.get("img_galeria") or []
        cfg = st.session_state.get("img_triagem_config") or {}
        if not cfg.get("nome_produto"):
            return ("⚠️ Não há produto aberto na aba Imagem para completar a galeria.")
        try:
            import imagem as _img
            padrao = list(_img.TIPOS_PADRAO)
        except Exception:
            return "⚠️ Não consegui ler a lista de tipos padrão."
        ja_tem = {g.get("tipo") for g in galeria}
        faltam = [t for t in padrao if t not in ja_tem]
        if not faltam:
            return "✅ A galeria já tem todos os tipos do padrão."
        st.session_state["chat_gerar_faltantes"] = faltam
        _log("gerar_faltantes", ", ".join(faltam), resultado=f"{len(faltam)} tipo(s)")
        lista = "\n".join(f"- {t}" for t in faltam)
        return (
            f"🖼️ Vou gerar as **{len(faltam)} imagens que faltam**:\n{lista}\n\n"
            "Abra a aba **Imagem** para acompanhar. As que já existem não serão tocadas."
        )

    if acao == "refazer_todas_imagens":
        galeria = st.session_state.get("img_galeria")
        if not galeria:
            return "⚠️ Não há imagens geradas para refazer."
        instrucao = str(cmd.get("instrucao", "")).strip()
        st.session_state["chat_refazer_todas"] = {"instrucao": instrucao}
        _log("refazer_todas", instrucao, resultado=f"{len(galeria)} imagem(ns) a descartar")
        return (
            f"🔁 Preparei para refazer as **{len(galeria)} imagens** do zero. "
            "Abra a aba **Imagem** e clique em **Confirmar e gerar** para começar — "
            "as imagens atuais serão descartadas."
        )

    if acao == "preencher_dados_triagem":
        novos_dados = cmd.get("dados", {})
        if not novos_dados or not isinstance(novos_dados, dict):
            return None
        cfg = st.session_state.get("img_triagem_config")
        if cfg is None:
            return "⚠️ Não há triagem em andamento no momento. Vá até a aba **Imagem** e clique em **Analisar** primeiro."
        # Mescla os novos dados no dados_descricao do config
        dados_atuais = cfg.get("dados_descricao") or {}
        dados_atuais.update({k: v for k, v in novos_dados.items() if v})
        cfg["dados_descricao"] = dados_atuais
        st.session_state["img_triagem_config"] = cfg
        # Sinaliza para imagem.py refazer a triagem automaticamente
        st.session_state["img_rerun_triagem"] = True
        campos_str = ", ".join(f"{k}: {v}" for k, v in novos_dados.items() if v)
        return (
            f"✅ Dados atualizados ({campos_str}). "
            "A triagem está sendo refeita — veja na aba **Imagem** que as imagens bloqueadas serão reavaliadas."
        )

    return None


# Modelo do assistente. Com ferramentas ele passou a decidir o que consultar
# antes de responder, e isso e trabalho de raciocinio, nao de completar texto.
MODELO_CHAT = "claude-opus-5"


def _chamar_ia(historico: list, mensagem_usuario: str, imagens_bytes: list = None,
               usuario: str = "", eh_admin: bool = False) -> tuple:
    """Chama a API Anthropic. Retorna (texto_resposta, comando_ou_None).
    imagens_bytes: lista de bytes de imagens para envio via visão (opcional).
    usuario: quem está logado — vai para o system prompt junto com o perfil."""
    api_key = _api_key()
    if not api_key:
        return "⚠️ ANTHROPIC_API_KEY não configurada no Railway/Secrets.", None

    # Janela de contexto: últimas 14 mensagens (7 trocas) — sem imagens no histórico
    msgs_hist = historico[-14:]
    msgs = [{"role": m["role"], "content": m["content"]} for m in msgs_hist]

    # Monta conteúdo da mensagem atual (texto + imagens opcionais)
    if imagens_bytes:
        content = [{"type": "text", "text": mensagem_usuario}]
        for img_b in imagens_bytes:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": _mime_tipo(img_b),
                    "data": base64.b64encode(img_b).decode(),
                },
            })
        msgs.append({"role": "user", "content": content})
    else:
        msgs.append({"role": "user", "content": mensagem_usuario})

    # ── Laço de ferramentas ──────────────────────────────────────────────────
    #
    # O assistente sabia explicar o site e não sabia ler o site: o contexto era
    # um resumo montado ANTES da pergunta, e nada nele conseguia buscar um dado
    # depois de ler o que a pessoa perguntou. Daí "quanto está o LPV?" virar um
    # passo a passo até a tela do Financeiro, com o valor na tela ao lado.
    #
    # Agora ele escolhe a consulta depois de ler a pergunta, lê o resultado e
    # responde com o número na mão. As ferramentas são só de LEITURA; alterar
    # continua pelo bloco <CMD>, que confirma e nomeia o que vai mudar.
    #
    # O teto de 4 rodadas é o freio: 4 consultas resolvem qualquer pergunta que
    # esta tela faz, e um laço sem teto seria uma conta aberta a cada mensagem.
    try:
        import ferramentas_chat as _fer
        ferramentas = _fer.para_o_modelo(eh_admin)
    except Exception:
        _fer, ferramentas = None, []

    try:
        client = anthropic.Anthropic(api_key=api_key)
        sistema = [{"type": "text", "text": _montar_system(usuario, eh_admin),
                    "cache_control": {"type": "ephemeral"}}]

        resp = None
        for _ in range(5):
            resp = client.messages.create(
                model=MODELO_CHAT,
                # ── SETE COMANDOS NÃO CABIAM EM 2000 ──────────────────────
                #
                # 25/09, produção: a colaboradora pediu correção nas sete
                # peças de uma vez. A resposta cortou no meio do JSON do
                # quarto comando — sem `</CMD>` —, o `findall` abaixo não
                # casou nada, NENHUM comando foi executado, e o JSON cru
                # apareceu na tela dela.
                #
                # Do lado dela isso se leu como "ele diz que vai fazer e se
                # recusa a fazer". Não era recusa: era a resposta cortada.
                #
                # Um comando de ajuste com a instrução escrita por extenso dá
                # uns 250 tokens; sete passam de 1.700 só neles, antes da
                # tabela que o assistente escreve antes. 8000 cobre as nove
                # peças com folga.
                max_tokens=8000,
                system=sistema,
                messages=msgs,
                **({"tools": ferramentas} if ferramentas else {}),
            )
            usos = [b for b in resp.content if getattr(b, "type", "") == "tool_use"]
            if resp.stop_reason != "tool_use" or not usos or not _fer:
                break
            msgs.append({"role": "assistant", "content": resp.content})
            # O resultado pode vir texto OU blocos de conteudo — `ver_imagem`
            # devolve a imagem de verdade, para o assistente OLHAR. Os dois
            # cabem no mesmo campo `content` do tool_result.
            msgs.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": u.id,
                 "content": _fer.executar(u.name, u.input, eh_admin)}
                for u in usos
            ]})

        def _texto_de(r):
            return "\n".join(b.text for b in (r.content if r else [])
                              if getattr(b, "type", "") == "text")

        texto_raw = _texto_de(resp)

        # ── A RESPOSTA CORTADA CONTINUA SOZINHA ───────────────────────────
        #
        # O DEFEITO, 25/09, em produção: a colaboradora pediu correção nas
        # sete peças de uma vez. A resposta cortou no meio do JSON do quarto
        # comando, sem `</CMD>`, NENHUM comando foi executado, e o JSON cru
        # apareceu na tela dela. Do lado dela isso se leu como "ele diz que
        # vai fazer e se recusa a fazer".
        #
        # NÃO PODE HAVER LIMITE DE COMANDOS — ordem do dono, e ela está
        # certa: pedir para dividir em duas mensagens é empurrar o problema
        # para quem já fez a parte dele. Então quando a resposta corta, ela
        # é CONTINUADA de onde parou, e os pedaços viram um texto só.
        #
        # A continuação é o próprio texto parcial devolvido como turno do
        # assistente: o modelo segue de onde estava, sem repetir o que já
        # escreveu — é por isso que os pedaços podem ser simplesmente
        # colados.
        #
        # O teto de 8 rodadas existe porque laço sem fim é conta aberta: são
        # 64 mil tokens de resposta, muito além das nove peças. Se ele for
        # alcançado, a tela diz — não se finge que a resposta veio inteira.
        _rodadas_cont = 0
        while (getattr(resp, "stop_reason", "") == "max_tokens"
               and _rodadas_cont < 8):
            _rodadas_cont += 1
            msgs_cont = list(msgs) + [
                {"role": "assistant", "content": texto_raw}]
            try:
                resp = client.messages.create(
                    model=MODELO_CHAT, max_tokens=8000, system=sistema,
                    messages=msgs_cont,
                    **({"tools": ferramentas} if ferramentas else {}),
                )
            except Exception:
                break
            _pedaco = _texto_de(resp)
            if not _pedaco:
                break
            texto_raw += _pedaco

        _cortada = getattr(resp, "stop_reason", "") == "max_tokens"
        texto_raw = texto_raw.strip()
        if not texto_raw:
            texto_raw = ("Consultei os dados mas não consegui formar a resposta. "
                         "Pergunte de novo, por favor.")

        # TODOS os blocos <CMD>{...}</CMD>, nao so o primeiro.
        #
        # Era `re.search`: o primeiro comando era executado e os demais caiam
        # fora em silencio. Quem pedisse tres mudancas numa mensagem via uma
        # acontecer e tinha de cobrar as outras duas — e o proprio assistente
        # passou a dizer "so posso um comando por vez", que nunca foi verdade:
        # era este `search` no lugar de um `findall`. A fila do lado da aba
        # Imagem sempre foi uma lista e sempre rodou em laco.
        cmds = ler_comandos(texto_raw)
        # ── O MARCADOR NUNCA APARECE PARA QUEM USA ────────────────────
        #
        # A limpeza só rodava quando ALGUM comando tinha sido lido (`if
        # cmds:`) — então justamente no caso ruim, o do bloco cortado, o
        # `<CMD>{"acao":"refazer_imagem"...` ia inteiro para a tela.
        #
        # Agora limpa sempre: os blocos fechados e também o fragmento sem
        # fechamento, que é o rastro da resposta cortada.
        texto_raw, _teve_fragmento = limpar_marcadores(texto_raw)

        # Só sobra aviso quando nem oito continuações deram conta — e aí o
        # que se diz é o que aconteceu, com o número de comandos que saiu.
        if _cortada or _teve_fragmento:
            texto_raw = ((texto_raw + "\n\n") if texto_raw else "") + (
                "⚠️ **A resposta ficou grande demais mesmo continuando.** "
                + (f"Foram enviados {len(cmds)} comando(s); pode haver mais "
                   "que não saiu." if cmds else
                   "Nenhum comando foi enviado — nada foi alterado.")
                + " Me peça de novo e eu sigo daqui.")

        return texto_raw, cmds

    except Exception as e:
        return f"⚠️ Erro ao conectar com o assistente: {e}", []


def ler_comandos(texto):
    """Os comandos <CMD>{...}</CMD> do texto. Lista, na ordem. Função pura.

    TODOS os blocos, nao so o primeiro. Era `re.search`: o primeiro comando
    era executado e os demais caiam fora em silencio. Quem pedisse tres
    mudancas via uma acontecer — e o proprio assistente passou a dizer "so
    posso um comando por vez", que nunca foi verdade.

    Um JSON torto nao derruba os outros que vieram certos na mesma resposta.
    """
    fora = []
    for bloco in re.findall(r"<CMD>\s*(\{.*?\})\s*</CMD>", str(texto or ""),
                            re.DOTALL):
        try:
            fora.append(json.loads(bloco))
        except Exception:
            continue
    return fora


def limpar_marcadores(texto):
    """Tira do texto tudo que é marcador de comando. (texto, tinha_fragmento).

    O DEFEITO QUE ISTO CORRIGE: a limpeza só rodava quando algum comando
    tinha sido LIDO. Na resposta cortada — o caso ruim — nenhum era lido, a
    limpeza não rodava, e o `<CMD>{"acao":"refazer_imagem"…` cru ia para a
    tela da colaboradora, em 25/09.

    O fragmento sem fechamento é o rastro de uma resposta cortada, e quem
    chama usa esse `True` para dizer o que houve.
    """
    t = re.sub(r"\s*<CMD>.*?</CMD>", "", str(texto or ""), flags=re.DOTALL)
    tinha = "<CMD>" in t
    return re.sub(r"\s*<CMD>.*$", "", t, flags=re.DOTALL).strip(), tinha


def renderizar_chat(usuario_logado=""):
    """
    Renderiza o chat IA no sidebar.
    Chamar dentro de `with st.sidebar:` (já no contexto certo).
    """
    if "ms_chat_hist" not in st.session_state:
        st.session_state["ms_chat_hist"] = []

    hist = st.session_state["ms_chat_hist"]

    # Nome de exibição: primeiro nome em maiúscula
    partes = usuario_logado.split() if usuario_logado else []
    nome_exib = partes[0] if partes else "você"

    # ── Container que agrupa visualmente todo o chat ──────────────────────────
    with st.container(border=True):
        st.markdown('<div id="ms-chat-topo"></div>', unsafe_allow_html=True)
        st.markdown(
            '<span style="font-size:10px; font-weight:700; letter-spacing:1.5px; '
            'color:var(--ms-texto-sec); text-transform:uppercase; display:block; margin-bottom:4px;">Assistente IA</span>',
            unsafe_allow_html=True,
        )

        # ── Área de mensagens com scroll ──────────────────────────────────────
        with st.container(height=800, border=False):
            if not hist:
                with st.chat_message("assistant"):
                    st.markdown(f"Olá **{nome_exib}**, como posso ajudar?")
            else:
                for msg in hist:
                    with st.chat_message(msg["role"]):
                        if msg.get("img_bytes"):
                            for ib in msg["img_bytes"]:
                                st.image(ib, use_container_width=True)
                        st.markdown(msg["content"])

            # Balão de espera DENTRO da área de mensagens.
            #
            # Antes, a pergunta era guardada e a chamada à IA acontecia na mesma
            # passada — depois que a lista de mensagens já tinha sido desenhada.
            # Resultado: durante a espera a própria pergunta não aparecia, e o
            # spinner entrava embaixo do quadro, empurrando o campo de escrita
            # para cima. Parecia travamento; era a tela mostrando um estado que
            # ainda não existia.
            #
            # Agora a pergunta é gravada e a tela recarrega ANTES de chamar a IA:
            # quando a espera começa, a mensagem já está no lugar e o campo de
            # escrita já está no lugar dele.
            if st.session_state.get("chat_pendente"):
                with st.chat_message("assistant"):
                    st.markdown("_digitando…_")

        # ── Anexo de imagem ───────────────────────────────────────────────────
        # O campo tinha sumido da tela, mas o resto do caminho continuou de pé:
        # o histórico já desenhava as imagens e _chamar_ia já sabia enviá-las.
        # Faltava só por onde entrar.
        versao_anexo = st.session_state.get("chat_anexo_versao", 0)
        anexos = st.file_uploader(
            "📎 Anexar imagem",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            key=f"chat_anexos_{versao_anexo}",
            label_visibility="collapsed",
            help="Anexe uma imagem para o assistente analisar junto da sua mensagem.",
        )

        # ── Campo de texto — Enter envia, Shift+Enter nova linha ──────────────
        user_input = st.chat_input("Digite sua mensagem…")

    # ── Resposta da IA ────────────────────────────────────────────────────────
    # Fora do container e numa passada só dela: a tela já está desenhada quando
    # a chamada começa. Tira do estado ANTES de chamar — se a chamada quebrar, a
    # pergunta não fica presa repetindo para sempre.
    pendente = st.session_state.pop("chat_pendente", None)
    if pendente:
        try:
            try:
                import auth as _auth_chat
                _adm = _auth_chat.is_admin(usuario_logado)
            except Exception:
                _adm = False
            resposta, cmds = _chamar_ia(
                hist[:-1], pendente["texto"], pendente.get("imagens") or [],
                usuario=usuario_logado, eh_admin=_adm)
        except Exception as e:
            resposta, cmds = f"⚠️ Erro ao falar com o assistente: {e}", []

        # Um comando que falha nao pode levar os outros junto: pedir tres
        # mudancas e receber zero por causa de uma e pior do que receber duas.
        retornos = []
        for _c in (cmds or []):
            try:
                _fb = _executar_comando(_c)
            except Exception as _e_cmd:
                _fb = f"⚠️ Não consegui executar `{_c.get('acao','?')}`: {str(_e_cmd)[:120]}"
            if _fb:
                retornos.append(_fb)
        feedback = "\n\n".join(retornos)

        texto_final = resposta
        if feedback:
            texto_final = (texto_final + "\n\n" + feedback).strip() if texto_final else feedback

        hist.append({"role": "assistant", "content": texto_final})
        st.rerun()

    if user_input:
        msg_user = user_input.strip()
        imagens_bytes = []
        for arq in (anexos or []):
            try:
                imagens_bytes.append(arq.getvalue())
            except Exception:
                pass

        entry = {"role": "user", "content": msg_user}
        if imagens_bytes:
            entry["img_bytes"] = imagens_bytes
        hist.append(entry)

        st.session_state["chat_pendente"] = {"texto": msg_user, "imagens": imagens_bytes}
        # Troca a chave do anexo para esvaziar o campo — o mesmo arquivo iria
        # junto de toda mensagem seguinte.
        if imagens_bytes:
            st.session_state["chat_anexo_versao"] = versao_anexo + 1
        st.rerun()


def iniciar_conversa(mensagem: str):
    """
    Adiciona uma mensagem do assistente ao histórico.
    Útil para alertas automáticos do app (ex: campo obrigatório faltando).
    """
    if "ms_chat_hist" not in st.session_state:
        st.session_state["ms_chat_hist"] = []
    st.session_state["ms_chat_hist"].append({"role": "assistant", "content": mensagem})


# ── Conferência ──────────────────────────────────────────────────────────────
# `python3 chat_assistente.py`. Só as funções puras — a conversa com o modelo
# não se testa sem rede, e a tela se confere em `checar_tela.py`.
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # ── O CASO DE 25/09, EM PRODUCAO ────────────────────────────────────
    #
    # Sete correcoes pedidas de uma vez. A resposta cortou no meio do JSON do
    # quarto comando, sem `</CMD>`. Nenhum comando foi executado, e o texto
    # cru apareceu na tela da colaboradora. Do lado dela: "ele diz que vai
    # fazer e se recusa a fazer".
    _CORTADA = (
        'Olhei as 7. Vou de ajuste fino.\n'
        '<CMD>{"acao":"refazer_imagem","imagem":1,"instrucao":"so a cinza"}</CMD>\n'
        '<CMD>{"acao":"refazer_imagem","imagem":2,"instrucao":"cards inteiros"}</CMD>\n'
        '<CMD>{"acao":"refazer_imagem","imagem":4,"instrucao":"Close macro do '
        'interior do porta-joias CINZA, com tres callouts brancos e margem de '
        'pelo menos 6% ate as bordas: VELUDO PREMIUM - toque macio; '
        'DIVISORIAS PRECISAS - espaco')

    _cmds = ler_comandos(_CORTADA)
    ok("os comandos inteiros continuam sendo lidos", len(_cmds) == 2)
    ok("e na ordem em que foram escritos",
       [c["imagem"] for c in _cmds] == [1, 2])
    ok("o bloco cortado NAO vira comando",
       all(c["imagem"] != 4 for c in _cmds))

    # O QUE A TELA MOSTRA: nunca o marcador.
    _txt, _frag = limpar_marcadores(_CORTADA)
    ok("o fragmento cortado e detectado", _frag is True)
    ok("e o marcador nao sobra no texto da tela", "<CMD>" not in _txt)
    ok("nem o JSON dele", "refazer_imagem" not in _txt)
    ok("o que o assistente escreveu para a pessoa continua",
       _txt.startswith("Olhei as 7"))

    # RESPOSTA INTEIRA: limpa igual, e sem acusar fragmento.
    _INTEIRA = ('Vou corrigir as tres.\n'
                '<CMD>{"acao":"ajustar_imagem","imagem":1}</CMD>\n'
                '<CMD>{"acao":"ajustar_imagem","imagem":2}</CMD>\n'
                '<CMD>{"acao":"ajustar_imagem","imagem":3}</CMD>')
    _c2 = ler_comandos(_INTEIRA)
    _t2, _f2 = limpar_marcadores(_INTEIRA)
    ok("os tres comandos saem", len(_c2) == 3)
    ok("sem fragmento, nao acusa corte", _f2 is False)
    ok("e o texto fica so com a frase", _t2 == "Vou corrigir as tres.")

    # UM JSON TORTO NO MEIO nao pode derrubar os que vieram certos.
    _TORTO = ('<CMD>{"acao":"a","imagem":1}</CMD>'
              '<CMD>{isso nao e json}</CMD>'
              '<CMD>{"acao":"a","imagem":3}</CMD>')
    ok("o torto e pulado e os bons passam",
       [c["imagem"] for c in ler_comandos(_TORTO)] == [1, 3])
    ok("e nenhum marcador sobra na tela",
       "<CMD>" not in limpar_marcadores(_TORTO)[0])

    # BORDAS
    ok("texto vazio nao quebra",
       ler_comandos("") == [] and limpar_marcadores("") == ("", False))
    ok("None tambem nao",
       ler_comandos(None) == [] and limpar_marcadores(None) == ("", False))
    ok("texto sem comando nenhum passa inteiro",
       limpar_marcadores("Oi, tudo bem?") == ("Oi, tudo bem?", False))

    # ── E A RESPOSTA CORTADA CONTINUA SOZINHA ───────────────────────────
    #
    # "NAO PODE HAVER LIMITE DE COMANDOS" — dono, 25/09. Mandar dividir em
    # duas mensagens e empurrar o problema para quem ja fez a parte dele.
    import inspect as _insp
    _corpo = _insp.getsource(_chamar_ia)
    ok("a resposta cortada e continuada, e nao devolvida pela metade",
       'stop_reason", "") == "max_tokens"' in _corpo and "while" in _corpo)
    ok("a continuacao devolve o texto parcial como turno do assistente",
       '"role": "assistant", "content": texto_raw' in _corpo)
    ok("os pedacos sao colados", "texto_raw += _pedaco" in _corpo)
    ok("e o laco tem teto, para nao virar conta aberta",
       "_rodadas_cont < 8" in _corpo)
    _aviso = _corpo.split("_cortada or _teve_fragmento")[1][:600]
    ok("o aviso da tela nao manda a pessoa dividir a mensagem",
       ("duas " + "mensagens") not in _aviso)
    ok("o teto de tokens comporta as nove pecas", "max_tokens=8000" in _corpo)

    # ── A LINGUAGEM COM QUEM USA ────────────────────────────────────────
    #
    # Relato de 25/09: "ele esta exigindo linguagem tecnica, esta falando
    # sobre diminuir a imagem com % e sobre espacamento". E a mensagem de
    # falha do ajuste ainda devolvia a lição de casa para ela: "tente
    # descrever de outro jeito".
    # OS DOIS RAMOS: sem conteudo gerado (so perguntas) e com conteudo. A
    # regra tem de valer nos dois — ela morava so no segundo, e a conversa
    # comeca no primeiro.
    _sis = _montar_system("myrella", False)
    st.session_state["img_galeria"] = [{"tipo": "1", "bytes": b""}]
    _sis_com = _montar_system("myrella", False)
    st.session_state.pop("img_galeria", None)
    ok("a regra vale tambem com conteudo gerado na tela",
       "COMO VOCÊ FALA COM A PESSOA" in _sis_com)
    ok("a regra das duas linguagens esta no system",
       "COMO VOCÊ FALA COM A PESSOA" in _sis)
    ok("e ela nomeia os termos proibidos na conversa",
       "pixel" in _sis and "espaçamento" in _sis)
    ok("e proibe devolver a licao de casa para quem pediu",
       "NUNCA peça que ela escreva de outro jeito" in _sis)
    ok("dizendo de quem e o trabalho de traduzir",
       "o trabalho de traduzir para\no gerador é SEU" in _sis
       or "traduzir para o gerador é SEU" in _sis.replace("\n", " "))

    # ── O AVISO AUTOMATICO DO APP ───────────────────────────────────────
    # Ele entra na conversa como fala do assistente; se a lista nao existir,
    # nasce. O aviso que nao chega ao chat e aviso que ninguem le.
    st.session_state.pop("ms_chat_hist", None)
    iniciar_conversa("Faltou o peso do produto.")
    _h = st.session_state.get("ms_chat_hist") or []
    ok("o aviso do app entra no historico do chat", len(_h) == 1)
    ok("e entra como fala do assistente", _h[0]["role"] == "assistant")
    iniciar_conversa("E as medidas.")
    ok("o segundo aviso nao apaga o primeiro",
       len(st.session_state["ms_chat_hist"]) == 2)

    print("\nfalhas:", falhas)
