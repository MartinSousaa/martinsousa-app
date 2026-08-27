"""
ferramentas_chat.py — O que o assistente pode CONSULTAR dentro do Studio.

O problema que isto resolve
--------------------------
O assistente sabia explicar o site e não sabia ler o site. Perguntado o LPV
vigente, devolvia o caminho até a tela do Financeiro — com o valor escrito na
tela ao lado. Perguntado quantos cartões estavam atrasados, dizia que o Studio
não tem essa informação, com o Painel de Metas mostrando ATRASADOS: 3. Seis de
seis perguntas terminaram em tutorial.

Não era falta de instrução no prompt: era falta de caminho. O chat só recebia um
resumo de texto montado uma vez, antes da pergunta. Nada nele conseguia ir
buscar um dado depois de ler o que a pessoa perguntou.

Como funciona
-------------
Cada função aqui é uma ferramenta que o modelo pode chamar por conta própria,
no meio da resposta. Ele lê a pergunta, decide de que dado precisa, chama, lê o
resultado e responde com o número na mão.

Todas são de LEITURA. Alterar título, descrição ou imagem continua pelo bloco
<CMD>, que já pede confirmação e nomeia o que vai mudar — o teste de 27/08
mostrou esse caminho funcionando bem, e ele não vai ser trocado por outro sem
motivo.

Regras que valem para toda ferramenta daqui:

* Nunca levanta. Erro vira texto explicando o que faltou — o modelo sabe dizer
  "não consegui ler o financeiro agora" e é melhor do que a tela quebrar.
* Devolve texto pronto para leitura, não JSON. O destinatário é um modelo de
  linguagem, e número com unidade e rótulo em português rende resposta melhor
  do que uma estrutura que ele teria que interpretar.
* Respeita perfil: o que é de admin só responde para admin.
"""
import streamlit as st


# ── Definições enviadas à API ────────────────────────────────────────────────

FERRAMENTAS = [
    {
        "name": "ler_produto_aberto",
        "description": (
            "O que está aberto AGORA no Studio: nome e código do produto, se há "
            "título, descrição, palavras-chave e imagens geradas nesta sessão. "
            "Use SEMPRE que a pergunta for sobre 'o produto', 'o título atual', "
            "'a descrição', 'as imagens' ou 'o que já foi feito'."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "buscar_triagem",
        "description": (
            "Dados salvos na triagem de um produto: categoria, material, medidas, "
            "peso, cores, uso, diferenciais, termos de busca. Use ANTES de pedir "
            "esses dados ao colaborador — quase sempre já estão salvos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string",
                         "description": "Nome ou pedaço do nome do produto."}
            },
            "required": ["nome"],
        },
    },
    {
        "name": "ler_financeiro",
        "description": (
            "LPV vigente (custo fixo por venda), alíquota, de que mês veio o LPV "
            "e há quantos meses ele não é atualizado. Use para qualquer pergunta "
            "sobre LPV, alíquota, imposto ou custo fixo."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "ler_painel_metas",
        "description": (
            "Números do Painel de Metas do mês: pontuação, meta, percentual, "
            "cartões pendentes, atrasados, em andamento, urgentes, sem membro e "
            "penalidades. 'Cartões' aqui são cartões do TRELLO — trabalho da "
            "equipe. Nada a ver com cartão de crédito. Demora alguns segundos."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "ler_equipe",
        "description": "Colaboradores cadastrados no Studio e o usuário de cada um no Trello.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "ler_colunas_trello",
        "description": (
            "Colunas do Trello com a prioridade e o tempo estimado de cada uma. "
            "Use para perguntas sobre quanto tempo uma etapa deveria levar."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]


# ── Implementações ───────────────────────────────────────────────────────────

def _txt(v):
    return str(v).strip() if v is not None else ""


def _ler_produto_aberto():
    s = st.session_state
    nome = (_txt((s.get("tt_dados_produto") or {}).get("nome_comercial"))
            or _txt(s.get("desc_nome_atual"))
            or _txt(s.get("img_nome_produto"))
            or _txt(s.get("img_nome_produto_input")))
    if not nome:
        return ("Nenhum produto aberto nesta sessão. Nada foi gerado ainda: sem "
                "título, sem descrição, sem imagens.")

    linhas = [f"Produto aberto: {nome}"]
    codigo = _txt(s.get("desc_codigo_atual")) or _txt(s.get("img_codigo_input"))
    if codigo:
        linhas.append(f"Código da descrição: {codigo}")

    titulos = s.get("tt_titulos_gerados")
    if titulos:
        linhas.append("Títulos gerados nesta sessão:")
        for i, t in enumerate(titulos, 1):
            linhas.append(f"  {i}. {t} ({len(str(t))} caracteres)")
    else:
        linhas.append("Título: nenhum gerado nesta sessão.")

    desc = _txt(s.get("desc_texto_atual"))
    linhas.append(f"Descrição: {len(desc)} caracteres gerados." if desc
                  else "Descrição: nenhuma gerada nesta sessão.")

    palavras = s.get("pc_palavras_geradas") or s.get("tt_palavras_usadas")
    if palavras:
        termos = [str(p.get("termo", p) if isinstance(p, dict) else p) for p in palavras]
        linhas.append(f"Palavras-chave ({len(termos)}): " + ", ".join(termos[:20]))
    else:
        linhas.append("Palavras-chave: nenhuma gerada nesta sessão.")

    galeria = s.get("img_galeria") or []
    if galeria:
        linhas.append(f"Imagens geradas ({len(galeria)}):")
        for i, g in enumerate(galeria, 1):
            linhas.append(f"  Imagem {i}: {g.get('tipo', '?')}")
    else:
        linhas.append("Imagens: nenhuma gerada nesta sessão.")
    return "\n".join(linhas)


def _buscar_triagem(nome):
    if not _txt(nome):
        return "Preciso do nome do produto para procurar a triagem."
    try:
        import triagem as _tri
        achada = _tri.buscar_triagem_por_nome(nome)
    except Exception as e:
        return f"Não consegui ler as triagens agora: {e}"
    if not achada:
        return (f"Nenhuma triagem salva com '{nome}'. O colaborador precisa "
                "preencher a triagem na aba Triagem, ou informar os dados aqui.")
    rotulos = [
        ("nome_comercial", "Nome comercial"), ("categoria", "Categoria"),
        ("material", "Material"), ("variacao_cores", "Cores"),
        ("medidas", "Medidas"), ("peso", "Peso"), ("uso", "Uso/ocasião"),
        ("caracteristicas", "Características"), ("diferenciais", "Diferenciais"),
        ("termos_busca", "Termos de busca"), ("termos_evitar", "Termos a evitar"),
    ]
    linhas = ["Triagem salva:"]
    for chave, rot in rotulos:
        v = _txt(achada.get(chave))
        linhas.append(f"  {rot}: {v}" if v else f"  {rot}: (em branco)")
    return "\n".join(linhas)


def _ler_financeiro():
    try:
        import financeiro as _fin
        df = _fin.carregar_dados()
        lpv, origem = _fin.lpv_vigente(df)
        aliq = _fin.aliquota_vigente(df)
        atraso = _fin.meses_de_atraso_lpv(df)
    except Exception as e:
        return f"Não consegui ler o Financeiro agora: {e}"
    if lpv is None:
        return f"Não há LPV informado ({origem}). Precisa ser preenchido em Gestão → Financeiro."
    linhas = [f"LPV vigente: R$ {lpv:.2f} (custo fixo médio por venda)",
              f"Mês de origem do LPV: {origem}",
              f"Alíquota tributária: {aliq:.1f}%"]
    if atraso >= 1:
        linhas.append(f"ATENÇÃO: o LPV está {atraso} mês(es) atrasado. Toda análise "
                      "de viabilidade está saindo com custo defasado.")
    else:
        linhas.append("O LPV está em dia.")
    return "\n".join(linhas)


def _ler_painel_metas():
    try:
        import placar_core as _pc
        import placar as _placar
        from datetime import datetime
        listas, cards, membros_map, id_p, id_t, id_i = _pc._buscar_board()
        if not cards:
            return "Não consegui falar com o Trello agora."
        agora = datetime.now()
        d = _placar._processar(listas, cards, membros_map, id_p, id_t, id_i,
                               filtro_mes=(agora.year, agora.month))
    except Exception as e:
        return f"Não consegui ler o Painel de Metas agora: {e}"

    pend = sum((d.get("pend_lista") or {}).values())
    saldo = d.get("pts_equipe", 0) - d.get("pen_total", 0)
    return "\n".join([
        f"Painel de Metas — {agora.strftime('%m/%Y')} (cartões do Trello):",
        f"  Pontuação do mês: {saldo:,.0f} pts (já com -{d.get('pen_total', 0):.0f} de penalidades)",
        f"  Cartões pendentes: {pend}",
        f"  Cartões atrasados: {d.get('atrasados', 0)}",
        f"  Atrasados em coluna prioritária (P8-P10): {d.get('atrasados_pri', 0)}",
        f"  Em andamento: {d.get('em_andamento', 0)}",
        f"  Urgentes: {d.get('urgentes', 0)}",
        f"  Sem membro atribuído: {d.get('sem_membro', 0)}",
        f"  Falta informação: {d.get('falta_info', 0)}",
        f"  Penalidades: {d.get('pen_total', 0):.0f} pontos",
    ])


def _ler_equipe():
    try:
        import placar_core as _pc
        membros = dict(_pc.MEMBROS_ATIVOS)
    except Exception as e:
        return f"Não consegui ler a equipe agora: {e}"
    if not membros:
        return "Nenhum colaborador cadastrado."
    linhas = [f"{len(membros)} colaborador(es) cadastrado(s):"]
    linhas += [f"  {nome} (Trello: {user})" for user, nome in membros.items()]
    linhas.append("O cadastro fica em Gestão → Administrativo.")
    return "\n".join(linhas)


def _ler_colunas_trello():
    try:
        import placar_core as _pc
        nomes = sorted(set(_pc.COLUNAS_CONFIG) | set(_pc.carregar_colunas_extra())
                       if hasattr(_pc, "carregar_colunas_extra") else _pc.COLUNAS_CONFIG)
    except Exception as e:
        return f"Não consegui ler as colunas agora: {e}"
    linhas = ["Colunas do Trello (prioridade · tempo estimado):"]
    for nome in nomes:
        cfg = _pc.cfg_coluna(nome)
        t = cfg.get("tempo_min")
        linhas.append(f"  {nome} — P{cfg.get('prioridade', 5)} · "
                      + (f"{t} min estimados" if t else "sem tempo configurado"))
    linhas.append("O tempo estimado é a meta definida pelo gestor, não uma média automática.")
    return "\n".join(linhas)


_SO_ADMIN = {"ler_financeiro", "ler_painel_metas", "ler_equipe", "ler_colunas_trello"}


def para_o_modelo(eh_admin=False):
    """Ferramentas que este usuário pode usar."""
    if eh_admin:
        return FERRAMENTAS
    return [f for f in FERRAMENTAS if f["name"] not in _SO_ADMIN]


def executar(nome, entrada, eh_admin=False):
    """Roda uma ferramenta. Devolve sempre texto — nunca levanta."""
    entrada = entrada or {}
    if nome in _SO_ADMIN and not eh_admin:
        return ("Esse dado é da área de Gestão e este usuário não tem perfil de "
                "administrador. Diga isso a ele em vez de mostrar o número.")
    try:
        if nome == "ler_produto_aberto":
            return _ler_produto_aberto()
        if nome == "buscar_triagem":
            return _buscar_triagem(entrada.get("nome", ""))
        if nome == "ler_financeiro":
            return _ler_financeiro()
        if nome == "ler_painel_metas":
            return _ler_painel_metas()
        if nome == "ler_equipe":
            return _ler_equipe()
        if nome == "ler_colunas_trello":
            return _ler_colunas_trello()
    except Exception as e:
        return f"A consulta '{nome}' falhou: {e}"
    return f"Ferramenta desconhecida: {nome}"
