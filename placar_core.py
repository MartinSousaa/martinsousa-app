"""
placar_core.py — Constantes e funções puras compartilhadas entre placar.py e analise_metas.py.

IMPORTANTE: Este módulo NÃO importa streamlit e NÃO contém nenhuma UI.
Pode ser importado com segurança por qualquer módulo sem causar efeitos colaterais.
"""
import requests
from datetime import datetime, timezone, timedelta, time

# ── Tenta ler secrets do Streamlit; falha silenciosa fora do contexto ──────────
try:
    import streamlit as st
    TRELLO_KEY   = st.secrets["trello"]["api_key"]
    TRELLO_TOKEN = st.secrets["trello"]["token"]
    BOARD_ID     = st.secrets["trello"]["board_id"]
except Exception:
    TRELLO_KEY = TRELLO_TOKEN = BOARD_ID = ""

# ── Constantes ─────────────────────────────────────────────────────────────────
# Equipe de origem. A lista real vem da planilha (aba "equipe") e e aplicada por
# recarregar_membros(); esta serve de reserva quando a planilha nao responde.
MEMBROS_ATIVOS = {
    "myrelladesouza": "Myrella",
    "beatriz51":      "Beatriz",
    "gabriel_borges": "Gabriel",
}
MAPA_RHID = {}   # primeiro nome na RHiD -> username do Trello


def recarregar_membros():
    """Aplica a equipe cadastrada na planilha, sem trocar o objeto.

    Muda o conteudo do dicionario no lugar de substitui-lo: modulos que ja
    importaram MEMBROS_ATIVOS continuam vendo a mesma lista. Contratacao passa a
    ser cadastro, nao alteracao de codigo.
    """
    try:
        import equipe_config as _ec
        membros, mapa = _ec.carregar()
    except Exception:
        return False
    if not membros:
        return False
    MEMBROS_ATIVOS.clear()
    MEMBROS_ATIVOS.update(membros)
    MAPA_RHID.clear()
    MAPA_RHID.update(mapa)
    return True
MASTERS = {"martinsousa", "renan"}
LISTAS_SEM_PONTUACAO = {
    "TABELA DE PONTUAÇÃO","TRIAGEM","CORREÇÃO DE FOTOS: 0 PONTOS",
    "RENAN","GUSTAVO","MYRELLA","URGENTES!!!!","Vídeos pendentes",
    "CRIAR ANÚNCIO","CRIAR ANÚNCIO DO ZERO",
}
LISTAS_PENALIDADE = {"PENALIDADES"}
MESES_PT = {1:"Janeiro",2:"Fevereiro",3:"Março",4:"Abril",5:"Maio",
            6:"Junho",7:"Julho",8:"Agosto",9:"Setembro",10:"Outubro",
            11:"Novembro",12:"Dezembro"}

COLUNAS_CONFIG = {
    "DESATIVAR (50)":                                  {"prioridade":10,"tempo_min":50},
    "AJUSTE DE PREÇO (MS-20)":                        {"prioridade":9, "tempo_min":120},
    "AJUSTE DE PREÇO (EQ-70)":                        {"prioridade":9, "tempo_min":60},
    "URGENTES!!!!":                                   {"prioridade":8, "tempo_min":210},
    "REATIVAR (20)":                                  {"prioridade":7, "tempo_min":150},
    "CORREÇÃO DE FOTOS: 0 PONTOS":                    {"prioridade":7, "tempo_min":120},
    "CRIATIVO VÍDEO (80)":                            {"prioridade":7, "tempo_min":180},
    "RETIRADA DE ETIQUETAS (30)":                     {"prioridade":7, "tempo_min":90},
    "CRIATIVO VARIAÇÃO (50)":                         {"prioridade":6, "tempo_min":120},
    "CRIATIVO DO ZERO: (FINALIZAR NO INTEGRAÇÃO!!!)": {"prioridade":6, "tempo_min":240},
    "INTEGRAÇÃO NOVOS ANÚNCIOS (100)":                {"prioridade":6, "tempo_min":60},
    "CRIATIVO FOTOS (NOVAS: 10/VAR.:2)":              {"prioridade":6, "tempo_min":180},
    "INTEGRAÇÃO VÍDEO (PONTUA NA CONFERIENCIA)":      {"prioridade":6, "tempo_min":60},
    "CONFERENCIA VÍDEO (10)":                         {"prioridade":6, "tempo_min":60},
    "TÍTULO/DESCRIÇÃO/EDIÇÃO (10)":                   {"prioridade":6, "tempo_min":60},
    "ANÚNCIAR DE CATÁLOGO (10)":                      {"prioridade":6, "tempo_min":60},
    "ESPELHAMENTO DE ANÚNCIO (30)":                   {"prioridade":5, "tempo_min":120},
    "CHAT (PROBLEMAS-30)":                            {"prioridade":5, "tempo_min":120},
    "DEMANDAS BLING":                                 {"prioridade":5, "tempo_min":150},
    "VARIAÇÃO DE ANÚNCIO (20)":                       {"prioridade":4, "tempo_min":120},
    # "espera_h" e tempo de terceiro, nao de execucao: o cartao fica fora da
    # fila enquanto se aguarda a resposta da plataforma e so aparece quando o
    # prazo esta vencendo. Sem isso, 36 horas de espera entrariam na conta como
    # 36 horas de trabalho da equipe.
    "CONFERENCIA DE CHAMADOS (20)":                   {"prioridade":6, "tempo_min":30,
                                                       "espera_h":36},
    "CORREÇÕES/RETRABALHOS: 0 PONTOS":                {"prioridade":7, "tempo_min":120},
}
COLUNAS_SKIP = {
    "TABELA DE PONTUAÇÃO","TRIAGEM","PENALIDADES",
    "RENAN","GUSTAVO","MYRELLA","Vídeos pendentes",
    "CRIAR ANÚNCIO","CRIAR ANÚNCIO DO ZERO",
}
CAPACIDADE_MIN = 390

# ── API ────────────────────────────────────────────────────────────────────────
# Cache manual simples (evita decorator @st.cache_data que exige streamlit importado)
_board_cache = {}

def _buscar_board():
    """Busca listas, cards, membros e campos customizados do Trello.
    Usa cache interno simples (sem streamlit) para não bater na API em todo rerun.
    Para invalidar: chame _buscar_board.clear() — ou simplesmente espere 30s."""
    import time
    now = time.time()
    if _board_cache.get("ts") and now - _board_cache["ts"] < 30:
        return _board_cache["data"]

    if not TRELLO_KEY:
        return None, None, None, None, None, None
    base = "https://api.trello.com/1"
    auth = {"key": TRELLO_KEY, "token": TRELLO_TOKEN}
    r_l = requests.get(f"{base}/boards/{BOARD_ID}/lists", params={**auth, "fields": "id,name"})
    listas = {l["id"]: l["name"] for l in r_l.json()} if r_l.ok else {}
    r_c = requests.get(f"{base}/boards/{BOARD_ID}/cards", params={
        **auth,
        # idLabels e o estado ATUAL das etiquetas do cartao. E a ancora final da
        # reconstrucao da linha do tempo: o estado depois da ultima mudanca.
        "fields": ("id,name,idList,idMembers,labels,idLabels,due,dueComplete,"
                   "customFieldItems,dateLastActivity"),
        "customFieldItems": "true",
    })
    cards = r_c.json() if r_c.ok else []
    r_m = requests.get(f"{base}/boards/{BOARD_ID}/members", params={**auth, "fields": "id,username"})
    membros_map = {m["id"]: m["username"] for m in r_m.json()} if r_m.ok else {}
    r_cf = requests.get(f"{base}/boards/{BOARD_ID}/customFields", params=auth)
    campos = r_cf.json() if r_cf.ok else []
    id_p = next((c["id"] for c in campos if c.get("name", "").upper() == "PONTOS"), None)
    id_t = next((c["id"] for c in campos if "TEMPO ACUMULADO" in c.get("name", "").upper()), None)
    id_i = next((c["id"] for c in campos if "INTERROMPIDO" in c.get("name", "").upper()), None)

    result = (listas, cards, membros_map, id_p, id_t, id_i)
    _board_cache["ts"] = now
    _board_cache["data"] = result
    return result

def _buscar_board_clear():
    """Invalida o cache de _buscar_board."""
    _board_cache.clear()


# ── Tempo de execução medido pelas etiquetas ───────────────────────────────────
# O tempo NÃO é a idade do cartão. Um cartão pode ficar dias em PENDENTE sem
# ninguém tocar nele. O relógio corre enquanto EM ANDAMENTO (ou FILMAGEM) está no
# cartão e PARA enquanto houver etiqueta de interrupção — inclusive se a pessoa
# esquecer de tirar EM ANDAMENTO. Interrupção pausa; não desconta.
LABEL_FILMAGEM        = "FILMAGEM"
LABEL_EM_ANDAMENTO    = "EM ANDAMENTO"
LABEL_INTERROMPIDO_MS = "INTERROMPIDO MS"
LABEL_INTERROMPIDO    = "INTERROMPIDO"
# Posta no fim do dia no que ficou pela metade, para retomar amanha. Conta como
# interrupcao, nao como "sem etiqueta": se alguem esquecer EM ANDAMENTO no
# cartao, o relogio voltaria a andar sozinho as 9h do dia seguinte e a pessoa
# apareceria trabalhando sem ter tocado no cartao — o que esconde ociosidade.
# Com ela ativa o relogio so volta quando alguem a tira.
LABEL_FIM_EXPEDIENTE  = "FIM DE EXPEDIENTE"
LABELS_TRABALHO    = {LABEL_FILMAGEM, LABEL_EM_ANDAMENTO}
LABELS_INTERRUPCAO = {LABEL_INTERROMPIDO_MS, LABEL_INTERROMPIDO,
                      LABEL_FIM_EXPEDIENTE,
                      # variacao provavel na hora de digitar no Trello
                      "FIM DO EXPEDIENTE"}

# Fuso de Brasília. As ações do Trello vêm em UTC e o expediente é local: sem
# converter, o corte pelo horário de trabalho erraria em 3 horas.
FUSO = timezone(timedelta(hours=-3))

# Expediente — fonte única (relogio_ponto.py importa daqui).
HORARIO_PADRAO = {"entrada": time(9, 0), "fim": time(18, 0)}
HORARIOS = {"myrelladesouza": {"entrada": time(8, 45), "fim": time(17, 45)}}
# Horario contratual lido da RHiD: 09:00-13:30 / 14:30-18:00. O intervalo real
# e 13h30 as 14h30 — antes o codigo descontava 12h as 13h, hora em que a equipe
# esta trabalhando, e contava 13h30 as 14h30, hora em que esta almocando.
ALMOCO = (time(13, 30), time(14, 30))
# Tres faixas, nao duas. Ate FOLGA nao registra nada; de FOLGA ate TOLERANCIA
# consome uma tolerancia; passou de TOLERANCIA, e atraso.
#
#   entrada 09:00 ->  ate 09:05 nada · 09:06 a 09:10 tolerancia · 09:11 atraso
#
# Antes so havia duas faixas (ate 09:05 tolerancia, depois atraso), e chegar
# 09:01 ja gastava uma tolerancia.
FOLGA_ENTRADA_MIN = 5
TOLERANCIA_ENTRADA_MIN = 10
ALMOCO_MINUTOS = 60
# A volta do almoco tem DUAS faixas, nao tres: cinco minutos livres e, passando
# disso, atraso direto. A faixa de tolerancia existe so na entrada do
# expediente.
FOLGA_ALMOCO_MIN = 5

# Teto de segurança: etiqueta esquecida por meses não vira varredura infinita.
MAX_DIAS_INTERVALO = 60


def horario_de(username):
    """Expediente do colaborador (quem não tem exceção usa o padrão)."""
    return HORARIOS.get(username, HORARIO_PADRAO)


_acoes_cache = {}   # chave -> {"ts": float, "data": {card_id: [acoes]}}

# Última consulta de ações: por que veio vazia, quando vier. Sem isso, uma falha
# na API do Trello vira "0 minutos" em todo cartão — indistinguível de "ninguém
# trabalhou", que foi exatamente o que aconteceu.
ULTIMO_DIAGNOSTICO_ACOES = {
    "erro": None, "paginas": 0, "acoes": 0, "cartoes": 0, "http": None,
}

# Por que um cartao com historico acaba com tempo zero. Sem estes numeros, "161
# cartoes concluidos, nenhum com tempo medido" nao diz onde a conta se perde.
ULTIMO_DIAGNOSTICO_TEMPOS = {
    "cards": 0, "com_acoes": 0, "com_trecho": 0, "com_tempo_util": 0,
    "com_membro": 0, "etiquetas_vistas": {}, "tipos_vistos": {},
}

# Um diagnostico por filtro. As duas consultas (etiquetas e movimentacao)
# escreviam no MESMO dicionario, e a segunda apagava a primeira: a tela dizia
# "5000 acoes de etiqueta" quando aquilo era o resultado dos updateCard. Se a
# consulta de etiqueta falhasse, ninguem ficava sabendo.
DIAGNOSTICO_POR_FILTRO = {}


FILTRO_ETIQUETAS = ("addLabelToCard,removeLabelFromCard,"
                    "addMemberToCard,removeMemberFromCard")
FILTRO_MOVIMENTO = "updateCard"


def _buscar_acoes_board(desde_iso=None, max_paginas=10, filtro=None,
                        _sem_filtro=False):
    """Histórico do board inteiro, agrupado por cartão.

    Uma chamada por página em vez de uma por cartão: a análise mensal passa por
    centenas de cartões, e um GET por cartão deixaria a tela inviável.

    As etiquetas e os updateCard sao buscados SEPARADAMENTE de proposito. Juntos
    numa consulta so, os updateCard — que sao a maioria esmagadora das acoes de
    um board ativo — enchiam as paginas e empurravam as etiquetas para fora da
    janela: 18 mil acoes lidas e nenhum trecho de trabalho encontrado.
    """
    import time as _t
    global _FILTRO_ETIQUETA_SERVE
    filtro = FILTRO_ETIQUETAS if filtro is None else filtro
    chave = f"{desde_iso or 'tudo'}|{filtro or 'sem-filtro'}|{max_paginas}"
    agora = _t.time()
    cache = _acoes_cache.get(chave)
    if cache and agora - cache["ts"] < 300:
        # Repõe o diagnóstico da busca que gerou este cache. Sem isso a tela
        # mostrava "HTTP None · 0 ações" — parecendo falha, quando na verdade a
        # consulta tinha dado certo e só não foi refeita.
        _publicar_diag(filtro, cache.get("diag", {}))
        return cache["data"]

    if filtro == FILTRO_ETIQUETAS and _FILTRO_ETIQUETA_SERVE is False:
        diag = {"erro": None, "paginas": 0, "acoes": 0, "cartoes": 0, "http": None,
                "filtro": filtro, "tipos": {}, "direto_sem_filtro": True}
        por_card = _acoes_sem_filtro(desde_iso, diag)
        _publicar_diag(filtro, diag)
        _acoes_cache[chave] = {"ts": agora, "data": por_card, "diag": dict(diag)}
        return por_card

    diag = {"erro": None, "paginas": 0, "acoes": 0, "cartoes": 0, "http": None,
            "filtro": filtro, "tipos": {}}

    if not TRELLO_KEY:
        diag["erro"] = "Credenciais do Trello não configuradas."
        _publicar_diag(filtro, diag)
        return {}

    base = "https://api.trello.com/1"
    auth = {"key": TRELLO_KEY, "token": TRELLO_TOKEN}
    por_card = {}
    antes = None
    for _ in range(max_paginas):
        params = {**auth, "limit": 1000, **CAMPOS_ACAO}
        if filtro:
            params["filter"] = filtro
        if desde_iso:
            params["since"] = desde_iso
        if antes:
            params["before"] = antes
        try:
            r = requests.get(f"{base}/boards/{BOARD_ID}/actions", params=params, timeout=30)
        except Exception as e:
            diag["erro"] = f"Falha de conexão com o Trello: {str(e)[:150]}"
            break
        diag["http"] = r.status_code
        if not r.ok:
            diag["erro"] = f"Trello respondeu {r.status_code}: {r.text[:150]}"
            break
        try:
            lote = r.json()
        except Exception:
            diag["erro"] = "Trello devolveu resposta que não é JSON."
            break
        diag["paginas"] += 1
        if not lote:
            break
        diag["acoes"] += len(lote)
        for ac in lote:
            t = ac.get("type", "?")
            diag["tipos"][t] = diag["tipos"].get(t, 0) + 1
            cid = ac.get("data", {}).get("card", {}).get("id")
            if cid:
                por_card.setdefault(cid, []).append(ac)
        if len(lote) < 1000:
            break
        # Se a PRIMEIRA pagina cheia de uma consulta de etiqueta nao trouxe uma
        # unica acao de etiqueta, o filtro nao esta sendo respeitado — insistir
        # nas outras nove paginas so gasta tempo. Custava dez idas ao Trello em
        # toda partida do servidor.
        if (filtro == FILTRO_ETIQUETAS and not _sem_filtro
                and not any(t in diag["tipos"] for t in TIPOS_ETIQUETA)):
            break
        antes = lote[-1].get("date")
    else:
        # Saiu pelo teto de paginas: existe historico mais antigo que nao foi
        # lido. Sem marcar isso, tempo faltando parece "ninguem trabalhou".
        diag["truncado"] = True

    diag["cartoes"] = len(por_card)
    if not por_card and not diag["erro"]:
        diag["erro"] = ("O Trello respondeu, mas não devolveu nenhuma ação "
                        f"para o filtro {filtro} no período.")

    # A consulta de etiquetas voltou sem NENHUMA acao de etiqueta: ou o board nao
    # emite addLabelToCard, ou o filtro nao foi respeitado. Em vez de medir zero
    # em silencio, refaz uma vez sem filtro e separa aqui — custa uma consulta a
    # cada cinco minutos e e o que faz o tempo de execucao existir.
    if filtro == FILTRO_ETIQUETAS and not diag["erro"] and not _sem_filtro:
        _FILTRO_ETIQUETA_SERVE = any(t in diag["tipos"] for t in TIPOS_ETIQUETA)
        if not _FILTRO_ETIQUETA_SERVE:
            por_card = _acoes_sem_filtro(desde_iso, diag)

    _publicar_diag(filtro, diag)
    _acoes_cache[chave] = {"ts": agora, "data": por_card, "diag": dict(diag)}
    return por_card


TIPOS_ETIQUETA = ("addLabelToCard", "removeLabelFromCard")

# Cache do mapa id-da-etiqueta -> nome. Preenchido sob demanda.
_MAPA_LABELS = {}

# Uma acao de troca de etiqueta, como o Trello mandou. A leitura crua acha 2463
# delas e o motor extrai zero evento — sem ver o JSON de verdade nao da para
# saber se o campo tem outro nome, se vem vazio, ou se o card do payload nao
# carrega idLabels. Deduzir ja custou duas rodadas.
AMOSTRA_ACAO_ETIQUETA = {"acao": None, "mapa_labels": 0}


def mapa_labels(forcar=False):
    """{id_da_etiqueta: NOME} do board.

    Necessario porque a mudanca de etiqueta nao vem como addLabelToCard neste
    board: ela aparece dentro do updateCard, e la so existem os IDs.
    """
    if _MAPA_LABELS and not forcar:
        return _MAPA_LABELS
    if not TRELLO_KEY:
        return _MAPA_LABELS
    try:
        r = requests.get(f"https://api.trello.com/1/boards/{BOARD_ID}/labels",
                         params={"key": TRELLO_KEY, "token": TRELLO_TOKEN,
                                 "limit": 1000}, timeout=20)
        if r.ok:
            for lb in r.json():
                if lb.get("id"):
                    _MAPA_LABELS[lb["id"]] = (lb.get("name") or "").upper().strip()
            AMOSTRA_ACAO_ETIQUETA["mapa_labels"] = len(_MAPA_LABELS)
    except Exception:
        pass
    return _MAPA_LABELS


def _mudanca_de_etiqueta(ac):
    """(adicionadas, removidas) de um updateCard que mexeu em idLabels.

    O board nao emite addLabelToCard: 8416 acoes lidas com filter=all e nenhuma
    de etiqueta. A troca de etiqueta esta aqui, na diferenca entre os idLabels
    de antes e os de depois.
    """
    dados = ac.get("data") or {}
    velho_ = dados.get("old") or {}
    if "idLabels" not in velho_:
        return (), ()
    antes = set(velho_.get("idLabels") or [])
    depois = set((dados.get("card") or {}).get("idLabels") or [])
    return tuple(depois - antes), tuple(antes - depois)
TIPOS_UTEIS = TIPOS_ETIQUETA + ("addMemberToCard", "removeMemberFromCard")

# O parametro filter do Trello nao reconhece addLabelToCard/removeLabelFromCard:
# ele devolve so as acoes de membro e descarta as de etiqueta em silencio. Era
# por isso que 314 cartoes tinham historico e NENHUM tinha etiqueta — e, sem
# etiqueta, nenhum trecho de trabalho e nenhum tempo de execucao.
#
# Depois da primeira resposta sem etiqueta, para de insistir na consulta
# filtrada: ela nao voltaria nada util e custa uma ida ao Trello.
_FILTRO_ETIQUETA_SERVE = None


def _publicar_diag(filtro, diag):
    """Guarda o diagnostico deste filtro e espelha o de etiquetas no global.

    O painel le ULTIMO_DIAGNOSTICO_ACOES; ele passa a ser sempre o da consulta
    de etiquetas, que e a que responde pelo tempo de execucao.
    """
    DIAGNOSTICO_POR_FILTRO[diag.get("filtro") or filtro] = dict(diag)
    if (diag.get("filtro") or filtro) == FILTRO_ETIQUETAS:
        ULTIMO_DIAGNOSTICO_ACOES.clear()
        ULTIMO_DIAGNOSTICO_ACOES.update(diag)


# Ritmo observado no board: cerca de 155 acoes por dia, contando updateCard. Uma
# pagina leva 1000. Com folga, seis dias por pagina.
DIAS_POR_PAGINA = 6
PAGINAS_MIN, PAGINAS_MAX = 5, 20


def _paginas_para(desde_iso):
    """Quantas paginas cobrem a janela pedida, sem filtro."""
    try:
        ini = datetime.fromisoformat((desde_iso or "").replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return PAGINAS_MAX
    dias = max(1, (datetime.now(timezone.utc) - ini).days)
    return max(PAGINAS_MIN, min(PAGINAS_MAX, -(-dias // DIAS_POR_PAGINA)))


# Campos que realmente usamos de cada acao. Sem isto o Trello manda junto o autor
# inteiro de cada uma das mil acoes da pagina — payload varias vezes maior para
# baixar e desserializar, em cada uma das paginas.
CAMPOS_ACAO = {"fields": "type,date,data", "memberCreator": "false",
               "reactions": "false"}

# Quantas fatias do periodo buscar ao mesmo tempo. A paginacao do Trello e
# sequencial (cada pagina depende da data da anterior), entao vinte paginas em
# fila eram vinte esperas somadas. Cortando o periodo em fatias independentes,
# cada uma pagina por conta propria e todas correm juntas.
FATIAS_PARALELAS = 6


def _fatias_do_periodo(desde_iso, n):
    """Divide [desde, agora] em n intervalos (mais novo primeiro)."""
    try:
        ini = datetime.fromisoformat((desde_iso or "").replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return [(desde_iso, None)]
    fim = datetime.now(timezone.utc)
    if fim <= ini:
        return [(desde_iso, None)]
    passo = (fim - ini) / n
    saida = []
    for i in range(n):
        a = ini + passo * i
        b = ini + passo * (i + 1)
        # Um minuto de sobreposicao entre fatias vizinhas: se o Trello tratar
        # since/before como exclusivos, uma acao exatamente na fronteira se
        # perderia. Acao repetida e inofensiva — as etiquetas entram num
        # conjunto e os dicionarios sao por cartao —, acao faltando nao e.
        a = a - timedelta(minutes=1)
        saida.append((a.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                      None if i == n - 1 else b.strftime("%Y-%m-%dT%H:%M:%S.000Z")))
    return list(reversed(saida))


def _paginar_fatia(desde_iso, ate_iso, max_paginas):
    """Paginacao de UMA fatia. Devolve (acoes, tipos, erro, http, paginas, truncado)."""
    base = "https://api.trello.com/1"
    auth = {"key": TRELLO_KEY, "token": TRELLO_TOKEN}
    acoes, tipos, antes = [], {}, ate_iso
    erro, http, paginas, truncado = None, None, 0, False
    for _ in range(max_paginas):
        # filter=all EXPLICITO. Omitir o parametro nao significa "tudo": o Trello
        # aplica um subconjunto padrao, e a leitura crua voltou com 8411 acoes e
        # nenhuma de etiqueta. Pedindo all, ou as acoes de etiqueta aparecem, ou
        # fica provado que o feed do board realmente nao as tem.
        params = {**auth, "limit": 1000, "filter": "all", **CAMPOS_ACAO}
        if desde_iso:
            params["since"] = desde_iso
        if antes:
            params["before"] = antes
        try:
            r = requests.get(f"{base}/boards/{BOARD_ID}/actions",
                             params=params, timeout=30)
        except Exception as e:
            erro = f"Falha de conexão com o Trello: {str(e)[:150]}"
            break
        http = r.status_code
        if not r.ok:
            erro = f"Trello respondeu {r.status_code}: {r.text[:150]}"
            break
        try:
            lote = r.json()
        except Exception:
            erro = "Trello devolveu resposta que não é JSON."
            break
        paginas += 1
        if not lote:
            break
        for ac in lote:
            t = ac.get("type", "?")
            tipos[t] = tipos.get(t, 0) + 1
        acoes.extend(lote)
        if len(lote) < 1000:
            break
        antes = lote[-1].get("date")
    else:
        truncado = True
    return acoes, tipos, erro, http, paginas, truncado


def _acoes_cru(desde_iso, max_paginas, diag):
    """Historico sem filtro do periodo inteiro, em fatias buscadas em paralelo.

    Devolve {card_id: [acoes]} com TODOS os tipos — a mesma leitura serve para
    etiqueta, membro e movimentacao, em vez de uma consulta para cada.
    """
    from concurrent.futures import ThreadPoolExecutor

    n = min(FATIAS_PARALELAS, max(1, max_paginas))
    fatias = _fatias_do_periodo(desde_iso, n)
    # Folga de uma pagina: as fatias nao tem o mesmo volume de acoes.
    por_fatia = max(2, -(-max_paginas // len(fatias)) + 1)

    with ThreadPoolExecutor(max_workers=len(fatias)) as ex:
        resultados = list(ex.map(
            lambda f: _paginar_fatia(f[0], f[1], por_fatia), fatias))

    por_card = {}
    for acoes, tipos, erro, http, paginas, truncado in resultados:
        diag["paginas"] += paginas
        diag["acoes"] += len(acoes)
        if http is not None:
            diag["http"] = http
        if erro and not diag.get("erro"):
            diag["erro"] = erro
        if truncado:
            diag["truncado"] = True
        for t, q in tipos.items():
            diag["tipos"][t] = diag["tipos"].get(t, 0) + q
        for ac in acoes:
            cid = (ac.get("data") or {}).get("card", {}).get("id")
            if cid:
                por_card.setdefault(cid, []).append(ac)
    return por_card


def _cru_que_cobre(desde_iso, agora):
    """Leitura crua ja em cache que alcance MAIS longe que a pedida.

    A fila olha 30 dias e a Analise olha 120. Sem isto, abrir as duas telas
    varria o board duas vezes — sendo que a leitura de 120 dias ja contem, por
    definicao, tudo o que a de 30 dias traria.
    """
    melhor = None
    # list(): o cache e escrito pelas buscas em paralelo e por execucoes
    # sobrepostas do script (todo Enter num campo dispara uma). Percorrer o dict
    # vivo levanta "dictionary changed size during iteration" e derruba a pagina
    # inteira — o painel some e sobra o traceback.
    for chave, c in list(_acoes_cache.items()):
        if not str(chave).startswith("cru|") or agora - c["ts"] >= 300:
            continue
        desde_cache = str(chave).split("|")[1]
        if desde_cache <= (desde_iso or ""):
            if melhor is None or desde_cache < melhor[0]:
                melhor = (desde_cache, c)
    return melhor[1] if melhor else None


def _acoes_cru_cache(desde_iso, max_paginas):
    """_acoes_cru com cache de 5 min — a leitura crua e cara e serve a todos."""
    import time as _t
    chave = f"cru|{desde_iso}|{max_paginas}"
    agora = _t.time()
    c = _acoes_cache.get(chave) or _cru_que_cobre(desde_iso, agora)
    if c and agora - c["ts"] < 300:
        DIAGNOSTICO_POR_FILTRO["cru"] = dict(c.get("diag", {}))
        return c["data"]
    diag = {"erro": None, "paginas": 0, "acoes": 0, "cartoes": 0, "http": None,
            "filtro": "cru", "tipos": {}}
    por_card = _acoes_cru(desde_iso, max_paginas, diag)
    diag["cartoes"] = len(por_card)
    DIAGNOSTICO_POR_FILTRO["cru"] = dict(diag)
    _acoes_cache[chave] = {"ts": agora, "data": por_card, "diag": dict(diag)}
    return por_card


def acoes_movimento(desde_iso, max_paginas=5):
    """Acoes updateCard do periodo.

    Quando o filtro de etiqueta nao serve, a leitura crua ja foi feita e ja tem
    os updateCard dentro: reaproveita em vez de gastar mais cinco paginas.
    """
    if _FILTRO_ETIQUETA_SERVE is False:
        cru = _acoes_cru_cache(desde_iso, _paginas_para(desde_iso))
        return {cid: [a for a in acoes if a.get("type") == "updateCard"]
                for cid, acoes in cru.items()}
    return _buscar_acoes_board(desde_iso, max_paginas=max_paginas,
                               filtro=FILTRO_MOVIMENTO)


def _acoes_sem_filtro(desde_iso, diag):
    """Historico sem filtro, guardando so etiqueta e membro.

    Plano B para quando o parametro filter nao devolve as acoes de etiqueta.
    """
    diag["plano_b"] = True
    # Sem filtro, os updateCard sao a maioria esmagadora das acoes. Com teto fixo
    # de 5 paginas, uma janela de 120 dias so enxergaria o ultimo mes de
    # etiquetas — e o resto do periodo ficaria sem tempo medido, em silencio.
    # O teto passa a acompanhar o tamanho da janela.
    bruto = _acoes_cru_cache(desde_iso, _paginas_para(desde_iso))
    por_card, achou = {}, 0
    AMOSTRA_ACAO_ETIQUETA["acao"] = None
    for cid, acoes in bruto.items():
        uteis = [a for a in acoes
                 if a.get("type") in TIPOS_UTEIS
                 or "idLabels" in ((a.get("data") or {}).get("old") or {})]
        if uteis:
            por_card[cid] = uteis
            achou += sum(1 for a in uteis
                         if a.get("type") in TIPOS_ETIQUETA
                         or "idLabels" in ((a.get("data") or {}).get("old") or {}))
            if AMOSTRA_ACAO_ETIQUETA["acao"] is None:
                for a in uteis:
                    if "idLabels" in ((a.get("data") or {}).get("old") or {}):
                        AMOSTRA_ACAO_ETIQUETA["acao"] = a
                        # Carrega o mapa agora: se ele vier vazio (endpoint fora
                        # do ar, board sem etiqueta nomeada), o contador na tela
                        # denuncia isso em vez de mostrar zero por nunca ter
                        # sido chamado.
                        mapa_labels()
                        break
    diag["plano_b_etiquetas"] = achou
    diag["plano_b_cartoes"] = len(por_card)
    diag["cartoes"] = len(por_card)
    sub = DIAGNOSTICO_POR_FILTRO.get("cru", {})
    diag["plano_b_acoes"] = sub.get("acoes", 0)
    diag["plano_b_truncado"] = sub.get("truncado", False)
    # Os tipos da leitura CRUA — sem isto nao da para saber o que sao as milhares
    # de acoes que chegam, so que etiqueta nao esta entre elas.
    diag["plano_b_tipos"] = dict(sub.get("tipos", {}))
    # Sobe os numeros da leitura crua para a linha principal. Sem isto o painel
    # mostrava "HTTP None · 0 pagina(s) · 0 acao(oes)" logo depois de ler oito
    # mil acoes — parecia falha de conexao onde houve leitura completa.
    for campo in ("paginas", "acoes"):
        diag[campo] = (diag.get(campo) or 0) + (sub.get(campo) or 0)
    diag["http"] = sub.get("http") or diag.get("http")
    if not achou:
        diag["erro"] = ("Nem com filtro nem sem filtro o Trello devolveu ação de "
                        "etiqueta neste período — o tempo de execução fica zerado.")
    return por_card


def _membros_no_inicio(acoes, membros_agora):
    """Quem estava no cartão ANTES da primeira ação da janela consultada.

    O histórico só cobre os últimos meses. Quem entrou no cartão antes disso não
    tem addMemberToCard dentro da janela e, sem esta reconstrução, o cartão
    parecia não ter membro nenhum — o tempo era medido mas não ia para ninguém,
    e o painel individual ficava vazio.

    Reconstrói desfazendo, de trás para frente, o que aconteceu na janela.
    """
    inicio = set(membros_agora or [])
    for ac in sorted(acoes, key=lambda a: a.get("date", ""), reverse=True):
        tipo = ac.get("type", "")
        dados = ac.get("data", {}) or {}
        mid = dados.get("idMember") or (dados.get("member") or {}).get("id")
        if not mid:
            continue
        if tipo == "addMemberToCard":
            inicio.discard(mid)     # entrou na janela: antes não estava
        elif tipo == "removeMemberFromCard":
            inicio.add(mid)         # saiu na janela: antes estava
    return inicio


def labels_do_card(card):
    """IDs das etiquetas que o cartao tem agora.

    Aceita as duas formas que a API devolve: idLabels (lista de ids) e labels
    (lista de objetos). Pedir so uma delas ja custou uma rodada — a consulta
    pedia labels e o codigo lia idLabels, entao a ancora vinha vazia.
    """
    ids = (card or {}).get("idLabels")
    if ids:
        return list(ids)
    return [l.get("id") for l in ((card or {}).get("labels") or []) if l.get("id")]


def _olds_do_cartao(acoes):
    """[(data, conjunto_de_ids)] de cada updateCard que mexeu em idLabels."""
    saida = []
    for ac in acoes:
        old = ((ac.get("data") or {}).get("old") or {})
        if "idLabels" not in old:
            continue
        try:
            dt = datetime.fromisoformat(ac["date"].replace("Z", "+00:00"))
        except Exception:
            continue
        saida.append((dt, set(old.get("idLabels") or [])))
    saida.sort(key=lambda m: m[0])
    return saida


# Como interpretar data.old.idLabels: "antes" (o estado anterior a mudanca, que
# e o que a documentacao do Trello descreve) ou "depois" (o estado ja
# atualizado). Descoberto a partir dos proprios dados por _detectar_alinhamento.
ALINHAMENTO_OLD = {"modo": "depois", "iguais": 0, "diferentes": 0}


def _detectar_alinhamento(cards, acoes_board):
    """Descobre, pelos dados, o que data.old.idLabels significa neste board.

    O criterio e o ultimo registro de cada cartao: se o old da ultima mudanca
    ja bate com as etiquetas que o cartao tem AGORA, entao old traz o estado
    depois da mudanca. Se nao bate, old traz o estado de antes e a ultima
    transicao levou justamente ate as etiquetas atuais.

    Amostra que motivou isto — card e old identicos na mesma acao:
        "card": {"idLabels": ["6a16e9df..."]}
        "old":  {"idLabels": ["6a16e9df..."]}
    Comparar um com o outro dava diferenca vazia em todas as 2463 acoes.
    """
    iguais = diferentes = 0
    for c in cards:
        olds = _olds_do_cartao(acoes_board.get(c["id"], []))
        if not olds:
            continue
        if olds[-1][1] == set(labels_do_card(c)):
            iguais += 1
        else:
            diferentes += 1
    ALINHAMENTO_OLD.update({
        "modo": "depois" if iguais >= diferentes else "antes",
        "iguais": iguais, "diferentes": diferentes,
    })
    return ALINHAMENTO_OLD["modo"]


def _eventos_de_etiqueta(acoes, labels_agora=None, modo=None):
    """[(data, id_etiqueta, entrou)] a partir dos updateCard do cartao.

    Este board nao emite addLabelToCard: a troca de etiqueta vem como updateCard.
    Comparar data.old.idLabels com data.card.idLabels nao funciona — os dois vem
    IGUAIS, entao a diferenca era sempre vazia (1838 acoes entrando, zero evento
    saindo).

    A transicao esta entre acoes CONSECUTIVAS, nao dentro de uma. Com a lista de
    estados em ordem no tempo, cada mudanca e a diferenca entre um estado e o
    seguinte; a ponta que falta e o estado atual do cartao, que ja temos.
    """
    olds = _olds_do_cartao(acoes)
    if not olds:
        return []
    modo = modo or ALINHAMENTO_OLD["modo"]
    atual = set(labels_agora or [])

    # Sequencia (data_da_mudanca, estado_resultante).
    if modo == "depois":
        # old ja e o estado apos aquela acao.
        passos = list(olds)
        if atual != passos[-1][1]:
            # Houve mudanca depois da ultima acao lida (ou a janela cortou).
            passos.append((passos[-1][0], atual))
        estado_inicial = set()
    else:
        # old e o estado anterior: o resultado de cada acao e o old da seguinte.
        passos = [(olds[i][0], olds[i + 1][1] if i + 1 < len(olds) else atual)
                  for i in range(len(olds))]
        estado_inicial = olds[0][1]

    eventos, anterior = [], estado_inicial
    for dt, estado in passos:
        for lid in estado - anterior:
            eventos.append((dt, lid, True))
        for lid in anterior - estado:
            eventos.append((dt, lid, False))
        anterior = estado
    return eventos


def intervalos_do_cartao(acoes, agora=None, membros_agora=None,
                         labels_agora=None):
    """Trechos em que o cartão esteve efetivamente em execução.

    Devolve [{"ini": dt, "fim": dt, "tipo": "filmagem"|"andamento",
              "membros": {id_membro}}], em UTC.

    Um trecho existe enquanto houver etiqueta de trabalho E nenhuma etiqueta de
    interrupção. É assim que INTERROMPIDO e INTERROMPIDO MS param o relógio
    mesmo com EM ANDAMENTO ainda no cartão — que é como a equipe usa.
    """
    agora = agora or datetime.now(timezone.utc)
    eventos = []
    for ac in acoes:
        try:
            dt = datetime.fromisoformat(ac["date"].replace("Z", "+00:00"))
        except Exception:
            continue
        tipo = ac.get("type", "")
        dados = ac.get("data", {}) or {}
        if tipo in ("addLabelToCard", "removeLabelFromCard"):
            nome = ((dados.get("label") or {}).get("name") or "").upper().strip()
            if nome in LABELS_TRABALHO or nome in LABELS_INTERRUPCAO:
                eventos.append((dt, "label", nome, tipo == "addLabelToCard"))
        elif tipo in ("addMemberToCard", "removeMemberFromCard"):
            mid = dados.get("idMember") or (dados.get("member") or {}).get("id")
            if mid:
                eventos.append((dt, "membro", mid, tipo == "addMemberToCard"))
    # Etiquetas reconstruidas a partir dos updateCard (ver _eventos_de_etiqueta).
    _mapa = None
    for dt, lid, entrou in _eventos_de_etiqueta(acoes, labels_agora):
        if _mapa is None:
            _mapa = mapa_labels()
        nome = _mapa.get(lid, "")
        if nome in LABELS_TRABALHO or nome in LABELS_INTERRUPCAO:
            eventos.append((dt, "label", nome, entrou))

    eventos.sort(key=lambda e: (e[0], e[1], str(e[2])))

    labels, segs = set(), []
    membros = _membros_no_inicio(acoes, membros_agora)
    ini, tipo_seg = None, None

    def _trabalhando():
        return bool(labels & LABELS_TRABALHO) and not (labels & LABELS_INTERRUPCAO)

    for dt, especie, valor, entrou in eventos:
        if _trabalhando() and ini is not None and dt > ini:
            segs.append({"ini": ini, "fim": dt, "tipo": tipo_seg, "membros": set(membros)})
        alvo = labels if especie == "label" else membros
        alvo.add(valor) if entrou else alvo.discard(valor)
        if _trabalhando():
            ini = dt
            tipo_seg = "filmagem" if LABEL_FILMAGEM in labels else "andamento"
        else:
            ini = None

    if _trabalhando() and ini is not None and agora > ini:
        segs.append({"ini": ini, "fim": agora, "tipo": tipo_seg, "membros": set(membros)})
    return segs


def _janelas_uteis(ini_local, fim_local, username=None):
    """Pedaços do intervalo que caem dentro do expediente da pessoa.

    Fora disso não é tempo de trabalho: etiqueta esquecida na sexta à noite não
    pode render o fim de semana inteiro.
    """
    h = horario_de(username)
    if (fim_local - ini_local).days > MAX_DIAS_INTERVALO:
        fim_local = ini_local + timedelta(days=MAX_DIAS_INTERVALO)

    janelas = []
    dia = ini_local.date()
    ultimo = fim_local.date()
    while dia <= ultimo:
        if dia.weekday() < 5:   # sem sábado e domingo
            for abre, fecha in ((h["entrada"], ALMOCO[0]), (ALMOCO[1], h["fim"])):
                ja = datetime.combine(dia, abre, tzinfo=FUSO)
                jb = datetime.combine(dia, fecha, tzinfo=FUSO)
                s, e = max(ini_local, ja), min(fim_local, jb)
                if e > s:
                    janelas.append((s, e))
        dia += timedelta(days=1)
    return janelas


_tempos_cache = {}   # chave -> {"ts": float, "data": {...}}


def _desde_padrao():
    """Início da janela de histórico, arredondado para o dia.

    Arredondar é o que faz o cache existir: com hora, minuto e segundo, a chave
    mudava a cada chamada e nada era reaproveitado — o board inteiro era relido
    e revarrido em toda renderização.
    """
    return (datetime.now(timezone.utc) - timedelta(days=120)).strftime(
        "%Y-%m-%dT00:00:00.000Z")


def _desde_curto(dias=30):
    """Janela curta, para o que nao precisa de meses de historico."""
    return (datetime.now(timezone.utc) - timedelta(days=dias)).strftime(
        "%Y-%m-%dT00:00:00.000Z")


def alguma_coluna_espera(listas=None):
    """Se existe coluna com espera de terceiro configurada.

    Sem nenhuma, nao ha por que buscar quando cada cartao entrou na coluna — e
    essa busca custa uma consulta paginada ao Trello.
    """
    nomes = list((listas or {}).values()) if listas else list(COLUNAS_CONFIG)
    for nome in nomes:
        if cfg_coluna(nome).get("espera_h"):
            return True
    return False


def entradas_se_preciso(listas=None):
    """Entradas na coluna, buscadas so quando alguma coluna espera terceiro.

    Antes essa consulta era feita sempre, ao abrir o Painel — e com janela de 120
    dias. Uma espera de 36 horas nao precisa de quatro meses de historico.
    """
    if not alguma_coluna_espera(listas):
        return {}
    return entradas_na_coluna(acoes_movimento(_desde_curto(30), max_paginas=3))


def tempos_do_board(cards, membros_map, desde_iso=None):
    """tempos_dos_cartoes com cache — o resultado não depende do mês analisado.

    A análise de metas chama _processar uma vez por mês do período (e de novo
    para o ano inteiro). Sem cache, a varredura do board inteiro rodava nove ou
    mais vezes por clique.
    """
    import time as _t
    desde_iso = desde_iso or _desde_padrao()
    # Busca sempre (ela tem cache proprio e e barata no acerto). Alem de simples,
    # e o que mantem o diagnostico das acoes atualizado: pulando esta chamada, a
    # tela mostrava "HTTP None · 0 acoes" como se o Trello tivesse falhado.
    acoes = _buscar_acoes_board(desde_iso)

    agora = _t.time()
    chave = f"{desde_iso}|{len(cards)}|{len(acoes)}"
    c = _tempos_cache.get(chave)
    if c and agora - c["ts"] < 300:
        return c["data"]
    dados = tempos_dos_cartoes(cards, acoes, membros_map)
    _tempos_cache[chave] = {"ts": agora, "data": dados}
    return dados


# ── OCIOSIDADE ────────────────────────────────────────────────────────────────
# Ocioso e o tempo do expediente em que a pessoa NAO tem nenhum cartao com
# EM ANDAMENTO no qual ela seja membro. Duas folgas:
GRACA_INICIO_MIN = 10   # do ponto de entrada ate pegar o primeiro cartao
GRACA_ENTRE_MIN = 5     # de um cartao ao seguinte
# Alem das folgas por troca de tarefa, uma hora por dia trabalhado: banheiro,
# cafe, agua, conversa rapida. A jornada e de 9h, menos 1h de almoco dao 8h no
# relogio de ponto, e destas 8h so 7h sao cobradas como tempo de atividade.
PAUSA_PESSOAL_MIN = 60


def _unir(intervalos):
    """Une trechos que se sobrepoem ou se encostam."""
    if not intervalos:
        return []
    ordenados = sorted(intervalos, key=lambda x: x[0])
    saida = [list(ordenados[0])]
    for ini, fim in ordenados[1:]:
        if ini <= saida[-1][1]:
            saida[-1][1] = max(saida[-1][1], fim)
        else:
            saida.append([ini, fim])
    return [tuple(x) for x in saida]


def intervalos_por_membro(cards, acoes_board, membros_map=None, agora=None):
    """{username: [(ini, fim)]} em hora local — trechos com ao menos um cartao
    EM ANDAMENTO atribuido aquela pessoa.

    Diferente de tempos_dos_cartoes, que reparte o minuto entre cartoes
    simultaneos: aqui interessa so SE havia algum cartao ativo, nao quantos.
    """
    membros_map = membros_map or {}
    agora = agora or datetime.now(timezone.utc)
    por_membro = {}
    for c in cards:
        acoes_c = acoes_board.get(c["id"], [])
        for s in intervalos_do_cartao(acoes_c, agora, c.get("idMembers"),
                                      labels_do_card(c)):
            for m in s["membros"]:
                ator = membros_map.get(m, m)
                por_membro.setdefault(ator, []).append(
                    (s["ini"].astimezone(FUSO), s["fim"].astimezone(FUSO)))
    return {u: _unir(v) for u, v in por_membro.items()}


def _buracos(janelas, ativos):
    """Trechos das janelas que NAO estao cobertos pelos ativos."""
    ativos = _unir(ativos)
    saida = []
    for jini, jfim in sorted(janelas, key=lambda x: x[0]):
        cursor = jini
        for aini, afim in ativos:
            if afim <= cursor or aini >= jfim:
                continue
            if aini > cursor:
                saida.append((cursor, min(aini, jfim)))
            cursor = max(cursor, afim)
            if cursor >= jfim:
                break
        if cursor < jfim:
            saida.append((cursor, jfim))
    return saida


def ociosidade_do_dia(janelas, ativos, graca_inicio=None, graca_entre=None):
    """Minutos ociosos de um dia. Devolve (minutos, detalhe_dos_buracos).

    janelas: trechos de expediente efetivo, do relogio de ponto (entrada ate a
             saida para o almoco, e a volta ate a saida do dia).
    ativos:  trechos com cartao EM ANDAMENTO da pessoa.

    O buraco que comeca junto com o expediente tem 10 minutos de folga — e o
    tempo de sentar e abrir o Trello. Os demais tem 5, que e a troca de uma
    demanda para a outra. So o que passa disso e ocioso.
    """
    graca_inicio = GRACA_INICIO_MIN if graca_inicio is None else graca_inicio
    graca_entre = GRACA_ENTRE_MIN if graca_entre is None else graca_entre
    if not janelas:
        return 0.0, []
    inicio_dia = min(j[0] for j in janelas)
    total, detalhe = 0.0, []
    for ini, fim in _buracos(janelas, ativos):
        bruto = (fim - ini).total_seconds() / 60
        folga = graca_inicio if ini <= inicio_dia else graca_entre
        ocioso = max(bruto - folga, 0.0)
        total += ocioso
        if ocioso > 0:
            detalhe.append({"ini": ini, "fim": fim, "minutos": ocioso,
                            "folga": folga})
    return total, detalhe


def tempos_dos_cartoes(cards, acoes_board, membros_map=None, agora=None):
    """Minutos de trabalho por cartão e por pessoa.

    {card_id: {"total": min, "por_membro": {username: min}, "bruto": min}}

    Dois cuidados que mudam o número em ordem de grandeza:

    - Só conta minuto dentro do expediente da pessoa.
    - Minuto em que a pessoa tinha N cartões em execução ao mesmo tempo vale
      1/N para cada. É isso que rateia a filmagem: a sessão de duas horas com
      oito produtos etiquetados juntos dá quinze minutos a cada um, e não duas
      horas a cada um. Vale igual para quem edita três cartões em paralelo.

    "bruto" é o tempo antes dos dois cortes — serve para achar etiqueta
    esquecida.
    """
    membros_map = membros_map or {}
    agora = agora or datetime.now(timezone.utc)

    diag = ULTIMO_DIAGNOSTICO_TEMPOS
    diag.update({"cards": len(cards), "com_acoes": 0, "com_trecho": 0,
                 "com_tempo_util": 0, "com_membro": 0, "etiquetas_vistas": {},
                 "tipos_vistos": {}})

    _detectar_alinhamento(cards, acoes_board)
    diag["alinhamento_old"] = dict(ALINHAMENTO_OLD)

    brutos, bruto_min = {}, {}
    for c in cards:
        acoes_c = acoes_board.get(c["id"], [])
        if acoes_c:
            diag["com_acoes"] += 1
            for ac in acoes_c:
                t = ac.get("type", "?")
                diag["tipos_vistos"][t] = diag["tipos_vistos"].get(t, 0) + 1
                nome = ((ac.get("data") or {}).get("label") or {}).get("name")
                if nome:
                    n = nome.upper().strip()
                    diag["etiquetas_vistas"][n] = diag["etiquetas_vistas"].get(n, 0) + 1

            _m = mapa_labels()
            for _dt, _lid, _e in _eventos_de_etiqueta(acoes_c, labels_do_card(c)):
                n = _m.get(_lid) or f"(id {_lid[:6]})"
                diag["etiquetas_vistas"][n] = diag["etiquetas_vistas"].get(n, 0) + 1
        segs = intervalos_do_cartao(acoes_c, agora, c.get("idMembers"),
                                    labels_do_card(c))
        if segs:
            diag["com_trecho"] += 1
            brutos[c["id"]] = segs

    # ator = username do membro na época; "" quando o cartão não tinha membro
    linhas = {}
    for cid, segs in brutos.items():
        for s in segs:
            bruto_min[cid] = bruto_min.get(cid, 0.0) + (s["fim"] - s["ini"]).total_seconds() / 60
            atores = {membros_map.get(m, m) for m in s["membros"]} or {""}
            ini_l, fim_l = s["ini"].astimezone(FUSO), s["fim"].astimezone(FUSO)
            for ator in atores:
                for a, b in _janelas_uteis(ini_l, fim_l, ator or None):
                    linhas.setdefault(ator, []).append((a, b, cid))

    por_membro = {}
    for ator, ivs in linhas.items():
        eventos = [(a, 1, cid) for a, b, cid in ivs] + [(b, -1, cid) for a, b, cid in ivs]
        eventos.sort(key=lambda e: (e[0], e[1], e[2]))
        ativos, anterior = {}, None
        for t, delta, cid in eventos:
            if anterior is not None and t > anterior and ativos:
                fatia = (t - anterior).total_seconds() / 60 / len(ativos)
                for c2 in ativos:
                    por_membro.setdefault(c2, {})
                    por_membro[c2][ator] = por_membro[c2].get(ator, 0.0) + fatia
            ativos[cid] = ativos.get(cid, 0) + delta
            if ativos[cid] <= 0:
                ativos.pop(cid, None)
            anterior = t

    resultado = {}
    for cid in brutos:
        fatias = por_membro.get(cid, {})
        if fatias:
            diag["com_tempo_util"] += 1
        if any(u for u in fatias):
            diag["com_membro"] += 1
        # Total do cartão = quanto tempo UMA pessoa gastou nele. Dois membros
        # trabalhando juntos não fazem o cartão durar o dobro.
        total = max(fatias.values()) if fatias else 0.0
        resultado[cid] = {
            "total": total,
            "por_membro": {u: v for u, v in fatias.items() if u},
            "bruto": bruto_min.get(cid, 0.0),
        }
    return resultado


def tempo_execucao_min(card_id, acoes_board=None):
    """Minutos de um cartão só, sem rateio entre cartões simultâneos.

    Usado pelo painel da TV, que pergunta "há quanto tempo este cartão está
    rodando". Para média e ociosidade use tempos_dos_cartoes, que rateia.
    """
    if acoes_board is None:
        if not TRELLO_KEY:
            return 0.0, None
        try:
            r = requests.get(
                f"https://api.trello.com/1/cards/{card_id}/actions",
                params={"key": TRELLO_KEY, "token": TRELLO_TOKEN,
                        "filter": ("addLabelToCard,removeLabelFromCard,"
                                   "addMemberToCard,removeMemberFromCard"),
                        "limit": 200},
                timeout=30,
            )
        except Exception:
            return 0.0, None
        acoes = r.json() if r.ok else []
    else:
        acoes = acoes_board.get(card_id, [])

    segs = intervalos_do_cartao(acoes)
    minutos = 0.0
    for s in segs:
        for a, b in _janelas_uteis(s["ini"].astimezone(FUSO), s["fim"].astimezone(FUSO)):
            minutos += (b - a).total_seconds() / 60

    primeiro_membro = None
    for ac in sorted(acoes, key=lambda a: a.get("date", "")):
        if ac.get("type") == "addMemberToCard":
            try:
                primeiro_membro = datetime.fromisoformat(ac["date"].replace("Z", "+00:00"))
            except Exception:
                pass
            break
    return minutos, primeiro_membro


# Colunas que existem no Trello mas nao estao em COLUNAS_CONFIG. O codigo pulava
# esses cartoes por completo — sem fila, sem alerta, sem atraso — e em silencio.
# Basta alguem criar ou renomear uma coluna no Trello para o trabalho dela sumir
# do painel sem ninguem perceber.
COLUNAS_DESCONHECIDAS = set()

CFG_PADRAO_COLUNA = {"prioridade": 5, "tempo_min": 60}


# Quantas horas antes de a espera vencer o cartao aparece na fila, para alguem
# pegar assim que a resposta chegar.
MARGEM_ENTRA_FILA_H = 2


def entradas_na_coluna(acoes_board):
    """{card_id: datetime} da ultima vez que o cartao mudou de coluna."""
    entrada = {}
    for cid, acoes in (acoes_board or {}).items():
        for ac in acoes:
            if ac.get("type") != "updateCard":
                continue
            if not (ac.get("data") or {}).get("listAfter"):
                continue
            try:
                dt = datetime.fromisoformat(ac["date"].replace("Z", "+00:00"))
            except Exception:
                continue
            if cid not in entrada or dt > entrada[cid]:
                entrada[cid] = dt
    return entrada


def _criacao_card(card):
    """Data de criacao, extraida do proprio id do cartao."""
    cid = card.get("id", "")
    if len(cid) >= 8:
        try:
            return datetime.fromtimestamp(int(cid[:8], 16), timezone.utc)
        except Exception:
            pass
    return None


def espera_restante_h(card, nome_lista, entradas=None):
    """Horas que faltam para a espera de terceiro vencer. None se a coluna nao espera."""
    horas = cfg_coluna(nome_lista).get("espera_h")
    if not horas:
        return None
    inicio = (entradas or {}).get(card.get("id")) or _criacao_card(card)
    if not inicio:
        return None
    passadas = (datetime.now(timezone.utc) - inicio).total_seconds() / 3600
    return horas - passadas


def aguardando_terceiro(card, nome_lista, entradas=None):
    """Se o cartao ainda esta no prazo de espera e nao deve ocupar a fila."""
    restante = espera_restante_h(card, nome_lista, entradas)
    return restante is not None and restante > MARGEM_ENTRA_FILA_H


def _data_entrega(card):
    """Data de entrega do cartao (campo `due` do Trello), ou None."""
    d = card.get("due")
    if not d:
        return None
    try:
        return datetime.fromisoformat(str(d).replace("Z", "+00:00"))
    except Exception:
        return None


def _card_atrasado(card, nome_lista, tempos=None, entradas=None):
    """Cartao aberto esta atrasado se passou da entrega OU do tempo estimado.

    Sao coisas diferentes: um cartao pode estourar o prazo sem ninguem ter
    trabalhado nele, e outro pode consumir o dobro do tempo previsto ainda
    dentro do prazo. Os dois merecem alerta.
    """
    if aguardando_terceiro(card, nome_lista, entradas):
        return False
    entrega = _data_entrega(card)
    if entrega and datetime.now(timezone.utc) > entrega:
        return True
    est = cfg_coluna(nome_lista).get("tempo_min") or 0
    decorrido = (tempos or {}).get(card.get("id"), {}).get("total", 0.0)
    return est > 0 and decorrido > est


def cfg_coluna(nome_lista):
    """Configuracao da coluna, com a planilha mandando sobre o codigo.

    Ordem: o que o gestor editou na planilha > os valores de origem no codigo >
    o padrao. Coluna que nao esta em lugar nenhum fica registrada, para virar
    aviso em vez de sumir.
    """
    base = dict(COLUNAS_CONFIG.get(nome_lista) or {})
    try:
        import colunas_config as _cc
        editado = _cc.carregar().get(nome_lista)
    except Exception:
        editado = None
    if editado:
        base.update(editado)
    if base:
        return base
    if nome_lista and nome_lista not in COLUNAS_SKIP:
        COLUNAS_DESCONHECIDAS.add(nome_lista)
    return dict(CFG_PADRAO_COLUNA)


def colunas_do_board():
    """Nomes das colunas que existem no Trello agora, fora as ignoradas."""
    listas = (_buscar_board() or (None,))[0] or {}
    return sorted(n for n in listas.values() if n and n not in COLUNAS_SKIP)


def _num(card, id_c):
    if not id_c:
        return None
    for cf in card.get("customFieldItems", []):
        if cf.get("idCustomField") == id_c:
            n = cf.get("value", {}).get("number")
            if n is not None:
                try:
                    return float(n)
                except Exception:
                    pass
    return None

def _labels(card):
    return {lb.get("name", "").upper() for lb in card.get("labels", [])}

def _users(card, mm):
    return [mm.get(mid, mid) for mid in card.get("idMembers", [])]

def _data_card(card):
    d = card.get("dateLastActivity", "")
    if d:
        try:
            return datetime.fromisoformat(d.replace("Z", "+00:00"))
        except Exception:
            pass
    return datetime.now(timezone.utc)

def datas_de_conclusao(acoes_board):
    """{card_id: datetime} do momento em que cada cartão foi marcado como concluído.

    Vem da ação que virou dueComplete para verdadeiro. Sem isso o mês saía da
    última atividade do cartão: um cartão concluído em julho que recebesse um
    comentário em agosto migrava a pontuação para agosto.
    """
    fim = {}
    for cid, acoes in (acoes_board or {}).items():
        for ac in acoes:
            if ac.get("type") != "updateCard":
                continue
            dados = ac.get("data", {}) or {}
            if (dados.get("old") or {}).get("dueComplete") is False and \
               (dados.get("card") or {}).get("dueComplete") is True:
                try:
                    dt = datetime.fromisoformat(ac["date"].replace("Z", "+00:00"))
                except Exception:
                    continue
                # Mais de uma? Vale a última — reabrir e concluir de novo conta
                # como concluído na segunda vez.
                if cid not in fim or dt > fim[cid]:
                    fim[cid] = dt
    return fim


def _mes_card(card, conclusoes=None, inicio_janela=None):
    """Mês em que o cartão foi CONCLUÍDO. None quando não dá para saber.

    A pontuação só pode contar no mês da conclusão. Editar ou comentar um cartão
    antigo não pode trazer os pontos dele para o mês atual.

    Quando não há registro de conclusão dentro da janela de histórico, a última
    atividade só serve se ela também for anterior à janela — aí ninguém mexeu no
    cartão desde então e ela equivale à conclusão. Se o cartão foi tocado dentro
    da janela sem ter sido concluído nela, a conclusão é mais antiga que o
    histórico: devolve None, e o cartão fica de fora do mês analisado em vez de
    pontuar de novo.
    """
    dt_fim = (conclusoes or {}).get(card.get("id"))
    if dt_fim:
        return (dt_fim.year, dt_fim.month)

    d = card.get("dateLastActivity", "")
    if not d:
        return None
    try:
        dt = datetime.fromisoformat(d.replace("Z", "+00:00"))
    except Exception:
        return None
    if inicio_janela and dt >= inicio_janela:
        return None
    return (dt.year, dt.month)

def _mes_card_criacao(card):
    """Mês do cartão pela data de CRIAÇÃO (ID Trello = ObjectID MongoDB) —
    usado para penalidades e sem_membro, evitando que cartões antigos
    vazem para o mês atual quando são modificados."""
    card_id = card.get("id", "")
    if card_id and len(card_id) >= 8:
        try:
            ts = int(card_id[:8], 16)
            dt = datetime.fromtimestamp(ts, timezone.utc)
            return (dt.year, dt.month)
        except Exception:
            pass
    return None

def _fmt_tempo(m):
    if m < 60:
        return f"{int(m)}min"
    h = int(m // 60); mm = int(m % 60)
    return f"{h}h{mm:02d}" if mm > 0 else f"{h}h"

def _calcular_fila(listas, cards, membros_map):
    _entradas_fila = entradas_se_preciso(listas)
    pendentes = []
    for card in cards:
        nl = listas.get(card["idList"], "")
        if nl in COLUNAS_SKIP:
            continue
        if card.get("dueComplete", False):
            continue
        lb = _labels(card)
        if "EM ANDAMENTO" in lb:
            continue
        # Espera de terceiro nao e trabalho: o cartao so entra na fila quando o
        # prazo esta vencendo.
        if aguardando_terceiro(card, nl, _entradas_fila):
            continue
        cfg = cfg_coluna(nl)
        us = _users(card, membros_map)
        pendentes.append({
            "nome": card["name"], "lista": nl,
            "prioridade": cfg["prioridade"], "tempo_min": cfg["tempo_min"],
            "data": _data_card(card),
            "membros": ", ".join(MEMBROS_ATIVOS.get(u, u) for u in us) or "—",
            "is_urgente": cfg["prioridade"] >= 10 or "URGENTE" in nl.upper(),
        })
    pendentes.sort(key=lambda x: (-x["prioridade"], x["data"]))
    acum = 0
    for i, p in enumerate(pendentes):
        p["posicao"] = i + 1
        acum += p["tempo_min"]
        p["eta_min"] = acum
    return pendentes

def _processar(listas, cards, membros_map, id_p, id_t, id_i, filtro_mes=None):
    """
    filtro_mes=(year,month) filtra APENAS:
      - pontuação de cartões concluídos  (pts_equipe / pts_membro)
      - penalidades
    Cartões abertos/pendentes são exibidos SEMPRE, independente do mês.
    """
    d = {
        "pts_equipe": 0.0, "pen_total": 0.0,
        "pts_membro": {u: 0.0 for u in MEMBROS_ATIVOS},
        "pen_membro": {u: 0.0 for u in MEMBROS_ATIVOS},
        "abertos": 0, "urgentes": 0, "atrasados": 0, "atrasados_pri": 0,
        "atrasados_pri_lista": [], "em_andamento": 0,
        "falta_conf": 0, "falta_info": 0, "sem_membro": 0, "falta_pts": 0,
        "pts_pendentes": 0.0, "pen_cards": [], "andamento_lista": [],
        "tempo_lista": {}, "desativar": 0, "reativar": 0, "pend_lista": {},
        "qtd_membro": {u: 0 for u in MEMBROS_ATIVOS},  # cartões concluídos por membro
        "pts_lista": {},   # pontos por coluna (cartões concluídos com pontuação)
        "qtd_lista": {},   # quantidade de cartões concluídos por coluna
        "correcao_concl": 0,  # cartões "CORREÇÃO DE FOTOS" concluídos no mês (retrabalho)
        "total_concl": 0,     # total de cartões concluídos no mês
        "concluido_sem_membro": [],  # cartões concluídos no mês sem membro atribuído
        "tempo_membro_lista": {},  # membro -> coluna -> [minutos] (medido por etiqueta)
        # membro -> [(ini, fim)] com cartao EM ANDAMENTO. E a linha do tempo que
        # a ociosidade precisa: sem ela so da para subtrair totais, e as folgas
        # de 10 e de 5 minutos exigem saber QUANDO cada buraco aconteceu.
        "intervalos_membro": {},
    }

    # O rateio entre cartões simultâneos precisa enxergar o board inteiro, então
    # os tempos são calculados de uma vez, antes do laço.
    _desde = _desde_padrao()
    _tempos = tempos_do_board(cards, membros_map, _desde)
    # A consulta de movimentacao e a mais volumosa de um board ativo. Limitada em
    # paginas: perder o registro de conclusao de um cartao muito antigo apenas o
    # deixa de fora do mes, que ja e o comportamento seguro.
    _acoes_mov = acoes_movimento(_desde, max_paginas=5)
    d["intervalos_membro"] = intervalos_por_membro(
        cards, _buscar_acoes_board(_desde), membros_map)
    _conclusoes = datas_de_conclusao(_acoes_mov)
    _entradas = entradas_na_coluna(_acoes_mov)
    try:
        _janela_ini = datetime.fromisoformat(_desde.replace("Z", "+00:00"))
    except Exception:
        _janela_ini = None

    for card in cards:
        nl = listas.get(card["idList"], "")
        if nl == "TABELA DE PONTUAÇÃO":
            continue
        lb = _labels(card)
        us = _users(card, membros_map)
        ok = card.get("dueComplete", False)
        pt = _num(card, id_p)
        tempo = _num(card, id_t)
        interr = _num(card, id_i) or 0

        # ── PENALIDADES ────────────────────────────────────────────────────────
        if nl in LISTAS_PENALIDADE:
            if filtro_mes:
                mc = _mes_card_criacao(card)  # data de CRIAÇÃO — não vaza penalidades antigas
                if mc and mc != filtro_mes:
                    continue
            if pt:
                v = abs(pt)
                d["pen_total"] += v
                d["pen_cards"].append({"card": card["name"], "valor": v, "membros": us})
                for u in us:
                    if u in d["pen_membro"]:
                        d["pen_membro"][u] += v
            continue

        # ── EM ANDAMENTO ───────────────────────────────────────────────────────
        if "EM ANDAMENTO" in lb:
            d["em_andamento"] += 1
            d["andamento_lista"].append({"card": card["name"], "lista": nl, "membros": us})

        # ── CARTÕES ABERTOS/PENDENTES ──────────────────────────────────────────
        if not ok:
            d["abertos"] += 1
            if "URGENTE" in lb or "URGENTES" in nl.upper():
                d["urgentes"] += 1
            # Atraso, agora com dois criterios. So o tempo de execucao nao
            # bastava: cartao que ninguem tocou tem tempo zero e nunca ficava
            # atrasado, mesmo aberto ha semanas.
            if _card_atrasado(card, nl, _tempos, _entradas):
                d["atrasados"] += 1
                # A meta fala em "prioritarios P8-P10", mas o numero usado era o
                # de TODOS os cartoes atrasados. Rotulo e conta mediam coisas
                # diferentes, e a barra ficava vermelha por atraso em coluna de
                # prioridade baixa.
                if int(cfg_coluna(nl).get("prioridade", 5) or 5) >= 8:
                    d["atrasados_pri"] += 1
                    d["atrasados_pri_lista"].append({"nome": card["name"], "lista": nl})
            if "FALTA CONFERÊNCIA" in lb:
                d["falta_conf"] += 1
            if "FALTA INFORMAÇÃO" in lb:
                d["falta_info"] += 1
            if not us:
                if not filtro_mes or _mes_card_criacao(card) == filtro_mes:
                    d["sem_membro"] += 1  # data de CRIAÇÃO — conta no mês em que o cartão foi aberto
            if pt is None:
                d["falta_pts"] += 1
            if "PENDENTE" in lb:
                d["pend_lista"][nl] = d["pend_lista"].get(nl, 0) + 1
                if pt:
                    d["pts_pendentes"] += pt
            if "DESATIVAR" in nl.upper():
                d["desativar"] += 1
            if "REATIVAR" in nl.upper():
                d["reativar"] += 1
            continue

        # ── CARTÃO CONCLUÍDO ───────────────────────────────────────────────────
        if filtro_mes:
            # Sem mes de conclusao confiavel, o cartao fica FORA do mes
            # analisado. Errar para menos e melhor que pontuar duas vezes.
            if _mes_card(card, _conclusoes, _janela_ini) != filtro_mes:
                continue

        _t = _tempos.get(card["id"], {})
        if tempo and tempo > 0:
            # Quem preencheu TEMPO ACUMULADO à mão manda.
            minutos = max(tempo - interr, 0)
            por_membro = {u: minutos for u in us if u in MEMBROS_ATIVOS}
        else:
            minutos = _t.get("total", 0.0)
            # A atribuição segue quem estava no cartão NA ÉPOCA, não quem está
            # agora: em vídeo, quem filma sai do cartão e o editor entra depois.
            por_membro = {u: v for u, v in _t.get("por_membro", {}).items()
                          if u in MEMBROS_ATIVOS}

        if minutos > 0:
            d["tempo_lista"].setdefault(nl, []).append(minutos)
        for u, v in por_membro.items():
            if v > 0:
                d["tempo_membro_lista"].setdefault(u, {}).setdefault(nl, []).append(v)

        # Contagem de concluídos para retrabalho
        d["total_concl"] += 1
        if nl == "CORREÇÃO DE FOTOS: 0 PONTOS":
            d["correcao_concl"] += 1

        # Alerta: concluído sem membro atribuído
        if not us:
            d["concluido_sem_membro"].append({"card": card["name"], "lista": nl})

        if pt is None:
            continue
        if nl in LISTAS_SEM_PONTUACAO:
            continue
        d["pts_equipe"] += pt
        d["pts_lista"][nl]  = d["pts_lista"].get(nl, 0.0)  + pt
        d["qtd_lista"][nl]  = d["qtd_lista"].get(nl, 0)    + 1
        ma = [u for u in us if u in MEMBROS_ATIVOS]
        if ma:
            cada = pt / len(ma)
            for u in ma:
                d["pts_membro"][u] += cada
                d["qtd_membro"][u] = d["qtd_membro"].get(u, 0) + 1
    return d
