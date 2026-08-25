"""
placar_core.py — Constantes e funções puras compartilhadas entre placar.py e analise_metas.py.

IMPORTANTE: Este módulo NÃO importa streamlit e NÃO contém nenhuma UI.
Pode ser importado com segurança por qualquer módulo sem causar efeitos colaterais.
"""
import requests
from datetime import datetime, timezone, timedelta

# ── Tenta ler secrets do Streamlit; falha silenciosa fora do contexto ──────────
try:
    import streamlit as st
    TRELLO_KEY   = st.secrets["trello"]["api_key"]
    TRELLO_TOKEN = st.secrets["trello"]["token"]
    BOARD_ID     = st.secrets["trello"]["board_id"]
except Exception:
    TRELLO_KEY = TRELLO_TOKEN = BOARD_ID = ""

# ── Constantes ─────────────────────────────────────────────────────────────────
MEMBROS_ATIVOS = {
    "myrelladesouza": "Myrella",
    "beatriz51":      "Beatriz",
    "gabriel_borges": "Gabriel",
}
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
        "fields": "id,name,idList,idMembers,labels,dueComplete,customFieldItems,dateLastActivity",
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
# O tempo NÃO é a idade do cartão. Um cartão pode ficar dias em "PENDENTE" sem
# ninguém tocar nele — isso não é tempo de trabalho. O relógio só corre enquanto
# a etiqueta "EM ANDAMENTO" (ou "FILMAGEM") está no cartão, e para quando ela sai
# ou quando entra "INTERROMPIDO MS".
LABEL_FILMAGEM        = "FILMAGEM"
LABEL_EM_ANDAMENTO    = "EM ANDAMENTO"
LABEL_INTERROMPIDO_MS = "INTERROMPIDO MS"

_acoes_cache = {}   # chave -> {"ts": float, "data": {card_id: [acoes]}}


def _buscar_acoes_board(desde_iso=None, max_paginas=10):
    """Histórico de etiquetas do board inteiro, agrupado por cartão.

    Uma chamada por página em vez de uma por cartão: a análise mensal passa por
    centenas de cartões, e um GET por cartão deixaria a tela inviável.
    """
    import time
    chave = desde_iso or "tudo"
    agora = time.time()
    cache = _acoes_cache.get(chave)
    if cache and agora - cache["ts"] < 300:
        return cache["data"]

    if not TRELLO_KEY:
        return {}

    base = "https://api.trello.com/1"
    auth = {"key": TRELLO_KEY, "token": TRELLO_TOKEN}
    por_card = {}
    antes = None
    for _ in range(max_paginas):
        params = {**auth,
                  "filter": "addLabelToCard,removeLabelFromCard,addMemberToCard",
                  "limit": 1000}
        if desde_iso:
            params["since"] = desde_iso
        if antes:
            params["before"] = antes
        try:
            r = requests.get(f"{base}/boards/{BOARD_ID}/actions", params=params, timeout=30)
        except Exception:
            break
        if not r.ok:
            break
        lote = r.json()
        if not lote:
            break
        for ac in lote:
            cid = ac.get("data", {}).get("card", {}).get("id")
            if cid:
                por_card.setdefault(cid, []).append(ac)
        if len(lote) < 1000:
            break
        antes = lote[-1].get("date")

    _acoes_cache[chave] = {"ts": agora, "data": por_card}
    return por_card


def _tempo_por_acoes(acoes, agora=None):
    """Minutos trabalhados a partir do histórico de etiquetas de um cartão.

    tempo_FILMAGEM + tempo_EM_ANDAMENTO − tempo_INTERROMPIDO_MS.
    Retorna (minutos, datetime do primeiro membro atribuído ou None).
    """
    agora = agora or datetime.now(timezone.utc)
    acoes_ord = sorted(acoes, key=lambda a: a.get("date", ""))

    filmagem_ini  = None; filmagem_total  = 0.0
    andamento_ini = None; andamento_total = 0.0
    interr_ini    = None; interr_total    = 0.0
    membro_em     = None

    for ac in acoes_ord:
        try:
            dt = datetime.fromisoformat(ac["date"].replace("Z", "+00:00"))
        except Exception:
            continue
        tipo    = ac.get("type", "")
        nome_lb = (ac.get("data", {}).get("label", {}).get("name") or "").upper()

        if tipo == "addLabelToCard":
            if nome_lb == LABEL_FILMAGEM and filmagem_ini is None:
                filmagem_ini = dt
            elif nome_lb == LABEL_EM_ANDAMENTO and andamento_ini is None:
                andamento_ini = dt
            elif nome_lb == LABEL_INTERROMPIDO_MS and interr_ini is None:
                interr_ini = dt
        elif tipo == "removeLabelFromCard":
            if nome_lb == LABEL_FILMAGEM and filmagem_ini is not None:
                filmagem_total += (dt - filmagem_ini).total_seconds() / 60
                filmagem_ini = None
            elif nome_lb == LABEL_EM_ANDAMENTO and andamento_ini is not None:
                andamento_total += (dt - andamento_ini).total_seconds() / 60
                andamento_ini = None
            elif nome_lb == LABEL_INTERROMPIDO_MS and interr_ini is not None:
                interr_total += (dt - interr_ini).total_seconds() / 60
                interr_ini = None
        elif tipo == "addMemberToCard" and membro_em is None:
            membro_em = dt

    # Períodos ainda abertos contam até agora.
    if filmagem_ini:
        filmagem_total  += (agora - filmagem_ini).total_seconds()  / 60
    if andamento_ini:
        andamento_total += (agora - andamento_ini).total_seconds() / 60
    if interr_ini:
        interr_total    += (agora - interr_ini).total_seconds()    / 60

    return max(0.0, filmagem_total + andamento_total - interr_total), membro_em


def tempo_execucao_min(card_id, acoes_board=None):
    """Minutos trabalhados no cartão, medidos pelas etiquetas.

    `acoes_board` é o mapa devolvido por _buscar_acoes_board; passar o mapa evita
    uma requisição por cartão. Sem ele, busca as ações só deste cartão.
    """
    if acoes_board is not None:
        return _tempo_por_acoes(acoes_board.get(card_id, []))

    if not TRELLO_KEY:
        return 0.0, None
    base = "https://api.trello.com/1"
    try:
        r = requests.get(
            f"{base}/cards/{card_id}/actions",
            params={"key": TRELLO_KEY, "token": TRELLO_TOKEN,
                    "filter": "addLabelToCard,removeLabelFromCard,addMemberToCard",
                    "limit": 200},
            timeout=30,
        )
    except Exception:
        return 0.0, None
    return _tempo_por_acoes(r.json() if r.ok else [])

# ── Funções auxiliares puras ───────────────────────────────────────────────────
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

def _mes_card(card):
    """Mês do cartão pela última atividade — usado para cartões CONCLUÍDOS (quando foi feito)."""
    d = card.get("dateLastActivity", "")
    if d:
        try:
            dt = datetime.fromisoformat(d.replace("Z", "+00:00"))
            return (dt.year, dt.month)
        except Exception:
            pass
    return None

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
    pendentes = []
    for card in cards:
        nl = listas.get(card["idList"], "")
        if nl in COLUNAS_SKIP or nl not in COLUNAS_CONFIG:
            continue
        if card.get("dueComplete", False):
            continue
        lb = _labels(card)
        if "EM ANDAMENTO" in lb:
            continue
        cfg = COLUNAS_CONFIG[nl]
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
        "abertos": 0, "urgentes": 0, "atrasados": 0, "em_andamento": 0,
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
    }

    # O histórico de etiquetas só é buscado se algum cartão precisar dele — quando
    # o campo TEMPO ACUMULADO está preenchido, o valor da equipe manda.
    _acoes = {"mapa": None}

    def _tempo_etiquetas(c):
        if _acoes["mapa"] is None:
            desde = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
            _acoes["mapa"] = _buscar_acoes_board(desde)
        minutos, _ = tempo_execucao_min(c["id"], _acoes["mapa"])
        return minutos

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
            if "ATRASADO" in lb:
                d["atrasados"] += 1
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
            mc = _mes_card(card)
            if mc and mc != filtro_mes:
                continue

        if tempo and tempo > 0:
            minutos = max(tempo - interr, 0)
        else:
            # Ninguém preencheu o tempo: mede pelas etiquetas. O relógio corre a
            # partir de quando o cartão recebeu "EM ANDAMENTO", não de quando foi
            # criado — cartão parado em PENDENTE não é tempo de trabalho.
            minutos = _tempo_etiquetas(card)

        if minutos > 0:
            d["tempo_lista"].setdefault(nl, []).append(minutos)
            for u in us:
                if u in MEMBROS_ATIVOS:
                    d["tempo_membro_lista"].setdefault(u, {}).setdefault(nl, []).append(minutos)

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
