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
# O tempo NÃO é a idade do cartão. Um cartão pode ficar dias em PENDENTE sem
# ninguém tocar nele. O relógio corre enquanto EM ANDAMENTO (ou FILMAGEM) está no
# cartão e PARA enquanto houver etiqueta de interrupção — inclusive se a pessoa
# esquecer de tirar EM ANDAMENTO. Interrupção pausa; não desconta.
LABEL_FILMAGEM        = "FILMAGEM"
LABEL_EM_ANDAMENTO    = "EM ANDAMENTO"
LABEL_INTERROMPIDO_MS = "INTERROMPIDO MS"
LABEL_INTERROMPIDO    = "INTERROMPIDO"
LABELS_TRABALHO    = {LABEL_FILMAGEM, LABEL_EM_ANDAMENTO}
LABELS_INTERRUPCAO = {LABEL_INTERROMPIDO_MS, LABEL_INTERROMPIDO}

# Fuso de Brasília. As ações do Trello vêm em UTC e o expediente é local: sem
# converter, o corte pelo horário de trabalho erraria em 3 horas.
FUSO = timezone(timedelta(hours=-3))

# Expediente — fonte única (relogio_ponto.py importa daqui).
HORARIO_PADRAO = {"entrada": time(9, 0), "fim": time(18, 0)}
HORARIOS = {"myrelladesouza": {"entrada": time(8, 45), "fim": time(17, 45)}}
ALMOCO = (time(12, 0), time(13, 0))
TOLERANCIA_ENTRADA_MIN = 5
ALMOCO_MINUTOS = 60

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


def _buscar_acoes_board(desde_iso=None, max_paginas=10):
    """Histórico de etiquetas e membros do board inteiro, agrupado por cartão.

    Uma chamada por página em vez de uma por cartão: a análise mensal passa por
    centenas de cartões, e um GET por cartão deixaria a tela inviável.
    """
    import time as _t
    chave = desde_iso or "tudo"
    agora = _t.time()
    cache = _acoes_cache.get(chave)
    if cache and agora - cache["ts"] < 300:
        # Repõe o diagnóstico da busca que gerou este cache. Sem isso a tela
        # mostrava "HTTP None · 0 ações" — parecendo falha, quando na verdade a
        # consulta tinha dado certo e só não foi refeita.
        ULTIMO_DIAGNOSTICO_ACOES.update(cache.get("diag", {}))
        return cache["data"]

    diag = ULTIMO_DIAGNOSTICO_ACOES
    diag.update({"erro": None, "paginas": 0, "acoes": 0, "cartoes": 0, "http": None})

    if not TRELLO_KEY:
        diag["erro"] = "Credenciais do Trello não configuradas."
        return {}

    base = "https://api.trello.com/1"
    auth = {"key": TRELLO_KEY, "token": TRELLO_TOKEN}
    por_card = {}
    antes = None
    for _ in range(max_paginas):
        params = {**auth,
                  "filter": ("addLabelToCard,removeLabelFromCard,"
                             "addMemberToCard,removeMemberFromCard"),
                  "limit": 1000}
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
            cid = ac.get("data", {}).get("card", {}).get("id")
            if cid:
                por_card.setdefault(cid, []).append(ac)
        if len(lote) < 1000:
            break
        antes = lote[-1].get("date")

    diag["cartoes"] = len(por_card)
    if not por_card and not diag["erro"]:
        diag["erro"] = "O Trello respondeu, mas não devolveu nenhuma ação de etiqueta no período."

    _acoes_cache[chave] = {"ts": agora, "data": por_card, "diag": dict(diag)}
    return por_card


def intervalos_do_cartao(acoes, agora=None):
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
    eventos.sort(key=lambda e: (e[0], e[1], str(e[2])))

    labels, membros, segs = set(), set(), []
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


def tempos_do_board(cards, membros_map, desde_iso):
    """tempos_dos_cartoes com cache — o resultado não depende do mês analisado.

    A análise de metas chama _processar uma vez por mês do período (e de novo
    para o ano inteiro). Sem cache, a varredura do board inteiro rodava nove ou
    mais vezes por clique.
    """
    import time as _t
    agora = _t.time()
    chave = f"{desde_iso}|{len(cards)}"
    c = _tempos_cache.get(chave)
    if c and agora - c["ts"] < 300:
        return c["data"]
    dados = tempos_dos_cartoes(cards, _buscar_acoes_board(desde_iso), membros_map)
    _tempos_cache[chave] = {"ts": agora, "data": dados}
    return dados


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

    brutos, bruto_min = {}, {}
    for c in cards:
        segs = intervalos_do_cartao(acoes_board.get(c["id"], []), agora)
        if segs:
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

    # O rateio entre cartões simultâneos precisa enxergar o board inteiro, então
    # os tempos são calculados de uma vez, antes do laço.
    _desde = (datetime.now(timezone.utc) - timedelta(days=120)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z")
    _tempos = tempos_do_board(cards, membros_map, _desde)

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
            # A etiqueta ATRASADO foi retirada do board: o atraso agora sai do
            # tempo medido. Cartão aberto que já passou do tempo estimado da
            # coluna está atrasado. Sem essa troca o contador ficaria em zero
            # para sempre, parecendo "tudo em dia".
            _est = COLUNAS_CONFIG.get(nl, {}).get("tempo_min") or 0
            _decorrido = _tempos.get(card["id"], {}).get("total", 0.0)
            if _est > 0 and _decorrido > _est:
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
