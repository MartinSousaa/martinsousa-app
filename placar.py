"""
placar.py — Painel de Meta · MS Studio v5
Layout: cards resumo | vel. meta | vel. maxx | cards resumo maxx
+ Fila com urgentes em vermelho
+ Meta individual detalhada
+ Modo TV
"""
import os
import struct as _struct
import base64 as _base64
import streamlit as st
import requests
import json as _json
from datetime import datetime, timezone
import math
import placar_core as _pc_core

# Conexao, leitura. requests SEM timeout espera para sempre: uma chamada
# pendurada travava a thread que regenera a TV — ela nao morre, nao levanta
# excecao e nao volta, entao o painel congelava sem uma linha de erro.
_HTTP_TIMEOUT = (10, 30)

class _RespFalha:
    """Resposta que nao chegou, com a forma de uma resposta do requests.

    Todo call-site aqui ja trata `r.ok` falso — e o caminho que termina em
    "Nao foi possivel conectar ao Trello", que a tela sabe mostrar. Deixar o
    timeout virar excecao trocaria a espera infinita por um traceback vermelho
    na cara do usuario; assim ele vira a falha que o codigo ja esperava.
    """
    ok = False
    status_code = None

    def __init__(self, erro=""):
        self.erro = erro

    def json(self):
        return []


def _req_get(url, **kw):
    """GET no Trello que nunca pendura e nunca levanta."""
    kw.setdefault("timeout", _HTTP_TIMEOUT)
    try:
        return requests.get(url, **kw)
    except Exception as e:
        try:
            import sys as _sys
            print(f"[Trello] {type(e).__name__}: {e}", file=_sys.stderr)
        except Exception:
            pass
        return _RespFalha(f"{type(e).__name__}: {e}")


# ── Beep de alerta — gerado como arquivo WAV físico em static/beep.wav ────────
# Data URIs de ~79KB falham silenciosamente no browser da LG TV.
# Servir como arquivo HTTP normal é compatível com todos os browsers.
def _gerar_beep_wav_bytes() -> bytes:
    """Gera bytes de um WAV com 4 bipes (660→880→1100→1100 Hz)."""
    sr = 22050
    beeps = [
        (660,  0.25, 0.40, 0.00),
        (880,  0.25, 0.40, 0.35),
        (1100, 0.40, 0.45, 0.70),
        (1100, 0.40, 0.45, 1.20),
    ]
    total_n = int(sr * 1.85)
    samples = [0.0] * total_n
    for freq, dur, vol, delay in beeps:
        s0 = int(delay * sr)
        s1 = int((delay + dur) * sr)
        for i in range(s0, min(s1, total_n)):
            t = (i - s0) / sr
            fade = max(0.0, min(t / 0.02, 1.0, (dur - t) / 0.05))
            samples[i] += math.sin(2 * math.pi * freq * t) * vol * fade
    pcm = b"".join(
        _struct.pack('<h', int(max(-1.0, min(1.0, s)) * 32767))
        for s in samples
    )
    hdr = _struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF', 36 + len(pcm), b'WAVE',
        b'fmt ', 16, 1, 1, sr, sr * 2, 2, 16,
        b'data', len(pcm),
    )
    return hdr + pcm

def _write_beep_wav() -> None:
    """Escreve static/beep.wav (gerado uma vez; regenera se sumir após redeploy)."""
    try:
        _static_dir = os.path.join(os.path.dirname(__file__), "static")
        os.makedirs(_static_dir, exist_ok=True)
        _path = os.path.join(_static_dir, "beep.wav")
        if not os.path.exists(_path):
            with open(_path, "wb") as _f:
                _f.write(_gerar_beep_wav_bytes())
    except Exception:
        pass

try:
    TRELLO_KEY   = st.secrets["trello"]["api_key"]
    TRELLO_TOKEN = st.secrets["trello"]["token"]
    BOARD_ID     = st.secrets["trello"]["board_id"]
except Exception:
    TRELLO_KEY = TRELLO_TOKEN = BOARD_ID = ""

try:
    _TV_TOKEN = str(st.secrets.get("tv", {}).get("token", ""))
except Exception:
    _TV_TOKEN = ""

# ── helper: persiste o HTML do painel TV em static/tv.html ──────────────────
def _meta_sessao(chave, padrao):
    """Lê uma meta do session_state, caindo na configuração quando não há sessão.

    A thread que regenera o painel da TV roda fora de qualquer sessão Streamlit,
    e nesse contexto `st.session_state[...]` levanta KeyError. Todo o resto da
    pagina_placar funciona: as chamadas de UI viram no-op e st.secrets lê do
    secrets.toml normalmente. Este acessor é o único ponto que precisava ceder.
    """
    try:
        return st.session_state[chave]
    except Exception:
        return int(padrao)


def _semear_meta(chave, valor):
    """Grava o valor inicial no session_state; no-op fora de uma sessão."""
    try:
        if chave not in st.session_state:
            st.session_state[chave] = int(valor)
    except Exception:
        pass


def _write_tv_static(html: str) -> bool:
    """Grava o HTML completo do painel TV no diretório static/ do Streamlit.

    O `except: pass` continua — a TV nunca pode derrubar o app —, mas agora a
    falha deixa rastro. Antes, disco cheio ou sistema de arquivos somente
    leitura sumia sem uma linha em lugar nenhum, e o diagnostico da TV seguia
    dizendo que estava tudo certo.
    """
    try:
        _static_dir = os.path.join(os.path.dirname(__file__), "static")
        os.makedirs(_static_dir, exist_ok=True)
        _path = os.path.join(_static_dir, "tv.html")
        with open(_path, "w", encoding="utf-8") as _f:
            _f.write(html)
        # O Tornado calcula o ETag de um arquivo estatico UMA vez e guarda o
        # hash num dicionario de classe que nunca expira. Como a TV revalida com
        # If-None-Match, ela recebia 304 para sempre: o arquivo era reescrito a
        # cada minuto e o navegador continuava com a primeira versao servida
        # depois do deploy. Recarregar nao adiantava — o 304 responde igual.
        # Apagar a entrada devolve o ETag correto na proxima requisicao.
        try:
            from tornado.web import StaticFileHandler as _SFH
            # A chave e o caminho absoluto que o proprio Tornado montou. Se por
            # qualquer diferenca de normalizacao ela nao for esta, reset() limpa
            # tudo — sao dois arquivos no static/, o custo e um md5 de cada um.
            if _SFH._static_hashes.pop(os.path.abspath(_path), None) is None:
                _SFH.reset()
        except Exception:
            pass
        ok = True
    except Exception as e:
        try:
            TV_STATUS["motivo"] = f"falha ao gravar o arquivo: {type(e).__name__}: {e}"[:200]
        except Exception:
            pass
        ok = False
    _write_beep_wav()  # garante que beep.wav existe ao lado de tv.html
    return ok

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

# Prioridade e tempo estimado de cada coluna vivem em placar_core. Aqui existia
# uma copia literal do dicionario, e ela ficou para tras: sem CONFERENCIA DE
# CHAMADOS (20) — inclusive sem as 36h de espera de terceiro dela — e sem
# CORRECOES/RETRABALHOS: 0 PONTOS, e ainda com o nome antigo da INTEGRACAO
# VIDEO. As duas telas liam listas diferentes da mesma coisa.
#
# Agora e a mesma referencia, e _cfg_colunas() ainda deixa a planilha mandar,
# como manda na Analise de Metas: o que o gestor configura na tela passa a valer
# tambem no Painel de Metas e na TV, que antes ignoravam a planilha aqui.
COLUNAS_CONFIG = _pc_core.COLUNAS_CONFIG


def _cfg_colunas():
    """Configuracao efetiva por coluna: valores de origem + planilha por cima.

    Devolve um dicionario so com o que esta realmente configurado — coluna
    ausente continua ausente, e nao um padrao inventado. Quem chama depende
    disso para distinguir "estimativa configurada" de "sem estimativa".

    Montado uma vez por chamada de proposito: cfg_coluna() por cartao colocaria
    uma consulta de cache dentro do laco do board inteiro.
    """
    base = dict(_pc_core.COLUNAS_CONFIG)
    try:
        import colunas_config as _cc_p
        base.update(_cc_p.carregar() or {})
    except Exception:
        pass
    return base
COLUNAS_SKIP = {
    "TABELA DE PONTUAÇÃO","TRIAGEM","PENALIDADES",
    "RENAN","GUSTAVO","MYRELLA","Vídeos pendentes",
    "CRIAR ANÚNCIO","CRIAR ANÚNCIO DO ZERO",
}
CAPACIDADE_MIN = 390

# ── Etiquetas e limiares para o campo Atenção ─────────────────────────────────
LABEL_FILMAGEM          = "FILMAGEM"
LABEL_INTERROMPIDO_MS   = "INTERROMPIDO MS"
LABEL_EM_ANDAMENTO_STR  = "EM ANDAMENTO"
LABEL_PENDENTE_STR      = "PENDENTE"
FATOR_VENCIMENTO        = 1.5   # alerta quando decorrido >= 1.5× tempo_médio
MIN_PENDENTE_COM_MEMBRO = 5     # minutos antes de alertar (pendente + membro)

# ── API ────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def _buscar_board():
    if not TRELLO_KEY: return None,None,None,None,None,None
    base = "https://api.trello.com/1"
    auth = {"key":TRELLO_KEY,"token":TRELLO_TOKEN}
    r_l = _req_get(f"{base}/boards/{BOARD_ID}/lists",params={**auth,"fields":"id,name"}, timeout=_HTTP_TIMEOUT)
    listas = {l["id"]:l["name"] for l in r_l.json()} if r_l.ok else {}
    r_c = _req_get(f"{base}/boards/{BOARD_ID}/cards",params={
        # idLabels: estado atual das etiquetas, ancora da reconstrucao da linha
        # do tempo em placar_core.
        # `due` entra aqui porque o criterio de prazo depende dele. Sem o campo,
        # _data_entrega devolvia None para todo cartao e a metade do teste de
        # atraso que olha a data de entrega simplesmente nunca disparava.
        **auth,"fields":"id,name,idList,idMembers,labels,idLabels,due,dueComplete,customFieldItems,dateLastActivity",
        "customFieldItems":"true"}, timeout=_HTTP_TIMEOUT)
    cards = r_c.json() if r_c.ok else []
    r_m = _req_get(f"{base}/boards/{BOARD_ID}/members",params={**auth,"fields":"id,username"}, timeout=_HTTP_TIMEOUT)
    membros_map = {m["id"]:m["username"] for m in r_m.json()} if r_m.ok else {}
    r_cf = _req_get(f"{base}/boards/{BOARD_ID}/customFields",params=auth, timeout=_HTTP_TIMEOUT)
    campos = r_cf.json() if r_cf.ok else []
    id_p = next((c["id"] for c in campos if c.get("name","").upper()=="PONTOS"),None)
    id_t = next((c["id"] for c in campos if "TEMPO ACUMULADO" in c.get("name","").upper()),None)
    id_i = next((c["id"] for c in campos if "INTERROMPIDO" in c.get("name","").upper()),None)
    return listas,cards,membros_map,id_p,id_t,id_i

@st.cache_data(ttl=60)
def _buscar_acoes_card(card_id: str):
    """Busca histórico de adição/remoção de etiquetas e membros de um cartão."""
    if not TRELLO_KEY:
        return []
    base = "https://api.trello.com/1"
    auth = {"key": TRELLO_KEY, "token": TRELLO_TOKEN}
    r = _req_get(
        f"{base}/cards/{card_id}/actions",
        params={**auth,
                "filter": "addLabelToCard,removeLabelFromCard,addMemberToCard",
                "limit": 200},
     timeout=_HTTP_TIMEOUT)
    return r.json() if r.ok else []


def _calcular_tempo_execucao_min(card_id: str):
    """Minutos de execução do cartão — regra única, em placar_core.

    O relógio corre com EM ANDAMENTO ou FILMAGEM e para enquanto houver
    INTERROMPIDO ou INTERROMPIDO MS. Só conta o que caiu dentro do expediente.
    """
    import placar_core as _pc_tempo
    return _pc_tempo.tempo_execucao_min(card_id)


def _num(card,id_c):
    if not id_c: return None
    for cf in card.get("customFieldItems",[]):
        if cf.get("idCustomField")==id_c:
            n=cf.get("value",{}).get("number")
            if n is not None:
                try: return float(n)
                except: pass
    return None

def _labels(card): return {lb.get("name","").upper().strip() for lb in card.get("labels",[])}


def _ordem_pausa():
    """Etiquetas de pausa, da mais especifica para a mais generica.

    A ordem so decide qual mostrar quando o cartao tem mais de uma —
    "FIM DE EXPEDIENTE" diz mais que "INTERROMPIDO".
    """
    import placar_core as _pc_o
    return [_pc_o.LABEL_FIM_EXPEDIENTE, "FIM DO EXPEDIENTE",
            _pc_o.LABEL_INTERROMPIDO_MS, _pc_o.LABEL_INTERROMPIDO]


def _parado(lb):
    """Se o cartao esta com o relogio parado por etiqueta.

    Inclui FIM DE EXPEDIENTE: cartao guardado para amanha nao pode aparecer no
    painel como alguem trabalhando nele agora.
    """
    import placar_core as _pc_lb
    return bool(lb & _pc_lb.LABELS_INTERRUPCAO)
def _users(card,mm): return [mm.get(mid,mid) for mid in card.get("idMembers",[])]

def _data_card(card):
    d=card.get("dateLastActivity","")
    if d:
        try: return datetime.fromisoformat(d.replace("Z","+00:00"))
        except: pass
    return datetime.now(timezone.utc)

def _mes_card(card):
    """OBSOLETA — não use. Mantida só para não quebrar chamador esquecido.

    Usava a última atividade como mês de conclusão, o que fazia um cartão de
    julho pontuar em agosto ao receber um comentário. O mês de conclusão de
    verdade vem de placar_core._mes_card(card, conclusoes, janela), que lê a
    ação que virou dueComplete. Duas contas para a mesma pergunta foi o que fez
    o Painel e a Análise discordarem em 330 pontos.
    """
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

# ── FILA ───────────────────────────────────────────────────────────────────────
def _calcular_fila(listas,cards,membros_map):
    import placar_core as _pc_ent
    _entradas_tv = _pc_ent.entradas_se_preciso(listas)
    pendentes=[]
    for card in cards:
        nl=listas.get(card["idList"],"")
        if nl in COLUNAS_SKIP: continue
        if card.get("dueComplete",False): continue
        lb=_labels(card)
        if "EM ANDAMENTO" in lb: continue
        import placar_core as _pc_fila
        # Espera de terceiro (ex.: 36h de retorno da plataforma) nao ocupa a
        # fila: o cartao aparece quando o prazo esta vencendo.
        if _pc_fila.aguardando_terceiro(card, nl, _entradas_tv): continue
        cfg=_pc_fila.cfg_coluna(nl)
        us=_users(card,membros_map)
        pendentes.append({
            "card_id":card["id"],
            "nome":card["name"],"lista":nl,
            "prioridade":cfg["prioridade"],"tempo_min":cfg["tempo_min"],
            "data":_data_card(card),
            "membros":", ".join(MEMBROS_ATIVOS.get(u,u) for u in us) or "—",
            "is_urgente": cfg["prioridade"]>=10 or "URGENTE" in nl.upper(),
        })
    pendentes.sort(key=lambda x:(-x["prioridade"],x["data"]))
    # Limita CRIATIVO VÍDEO a no máximo 2 itens na fila
    _cv_count = 0
    _filtrado = []
    for p in pendentes:
        if "CRIATIVO V" in p["lista"].upper():
            if _cv_count >= 2:
                continue
            _cv_count += 1
        _filtrado.append(p)
    pendentes = _filtrado
    # A previsao supunha UMA pessoa fazendo tudo em serie. Com tres
    # colaboradores, a fila anda em paralelo e o numero saia ~3x maior do que a
    # espera real.
    _equipe = max(len(MEMBROS_ATIVOS), 1)
    acum = 0
    for i, p in enumerate(pendentes):
        p["posicao"] = i + 1
        acum += p["tempo_min"]
        p["eta_serie_min"] = acum          # se uma pessoa so fizesse tudo
        p["eta_min"] = acum / _equipe      # com a equipe trabalhando junto
        p["entrega"] = _data_entrega_card(p["card_id"], cards)
        p["estoura_prazo"] = _estoura_prazo(p["entrega"], p["eta_min"])
    return pendentes


def _data_entrega_card(card_id, cards):
    for c in cards:
        if c.get("id") == card_id:
            import placar_core as _pc_dt
            return _pc_dt._data_entrega(c)
    return None


def _estoura_prazo(entrega, eta_min):
    """Se a fila nao alcanca o prazo: previsao de inicio + execucao passa da entrega."""
    if not entrega:
        return False
    from datetime import timedelta as _td
    return datetime.now(timezone.utc) + _td(minutes=eta_min) > entrega

def _fmt_tempo(m):
    if m<60: return f"{int(m)}min"
    h=int(m//60); mm=int(m%60)
    return f"{h}h{mm:02d}" if mm>0 else f"{h}h"

# ── PROCESSAMENTO ──────────────────────────────────────────────────────────────
def _processar(listas,cards,membros_map,id_p,id_t,id_i,filtro_mes=None):
    """
    filtro_mes=(year,month) filtra APENAS:
      - pontuação de cartões concluídos  (pts_equipe / pts_membro)
      - penalidades
    Cartões abertos/pendentes são exibidos SEMPRE, independente do mês.
    """
    import placar_core as _pc_tv
    from datetime import timedelta as _td_tv
    _tempos_tv = _pc_tv.tempos_do_board(cards, membros_map, _pc_tv._desde_curto(45))
    _cfg_col = _cfg_colunas()
    # Espera de terceiro: busca so acontece se alguma coluna tiver espera
    # configurada, entao na maioria dos boards isto e um dicionario vazio.
    try:
        _entradas_atr = _pc_tv.entradas_se_preciso(listas)
    except Exception:
        _entradas_atr = {}

    # Mês de conclusão: a MESMA fonte que a Análise de Metas usa.
    #
    # Esta tela decidia o mês do cartão pela última atividade dele. Comentar ou
    # editar em agosto um cartão concluído em julho trazia os pontos para agosto
    # — e o Painel mostrava 5.972 pts onde a Análise mostrava 5.642, 330 pontos
    # de diferença no mesmo mês e na mesma sessão. A Análise já usava a ação que
    # de fato virou dueComplete, que é o que "concluído no mês" significa.
    _desde_concl = _pc_tv._desde_padrao()
    _conclusoes_tv = _pc_tv.datas_de_conclusao(
        _pc_tv.acoes_movimento(_desde_concl, max_paginas=5))
    try:
        _janela_tv = datetime.fromisoformat(_desde_concl.replace("Z", "+00:00"))
    except Exception:
        _janela_tv = None
    d={
        "pts_equipe":0.0,"pen_total":0.0,
        "pts_membro":{u:0.0 for u in MEMBROS_ATIVOS},
        "pen_membro":{u:0.0 for u in MEMBROS_ATIVOS},
        "abertos":0,"urgentes":0,"atrasados":0,"atrasados_pri":0,
        "atrasados_pri_lista":[],"em_andamento":0,
        "falta_conf":0,"falta_info":0,"sem_membro":0,"sem_membro_lista":[],"falta_pts":0,
        "pts_pendentes":0.0,"pen_cards":[],"andamento_lista":[],"pausados_lista":[],
        "tempo_lista":{},"desativar":0,"reativar":0,"pend_lista":{},
        "correcao_concl":0,"total_concl":0,
        "concluido_sem_membro":[],
    }
    for card in cards:
        nl=listas.get(card["idList"],"")
        if nl=="TABELA DE PONTUAÇÃO": continue
        lb=_labels(card); us=_users(card,membros_map)
        ok=card.get("dueComplete",False)
        pt=_num(card,id_p); tempo=_num(card,id_t); interr=_num(card,id_i) or 0

        # ── PENALIDADES: contam no mês em que foram CRIADAS (data de criação) ────
        if nl in LISTAS_PENALIDADE:
            if filtro_mes:
                mc=_mes_card_criacao(card)  # data de criação — não vaza penalidades antigas
                if mc and mc!=filtro_mes: continue
            if pt:
                v=abs(pt); d["pen_total"]+=v
                d["pen_cards"].append({"card":card["name"],"valor":v,"membros":us})
                for u in us:
                    if u in d["pen_membro"]: d["pen_membro"][u]+=v
            continue

        # ── EM ANDAMENTO: sempre visível, sem filtro de mês ────────────────────
        # Cartao com INTERROMPIDO, INTERROMPIDO MS ou FIM DE EXPEDIENTE nao esta
        # em execucao agora, mesmo com EM ANDAMENTO ainda colada nele. O contador
        # nao olhava para isso e mostrava quatro em andamento havendo um.
        _pausa = next((x for x in _ordem_pausa() if x in lb), "")
        if "EM ANDAMENTO" in lb and not _pausa:
            d["em_andamento"]+=1
            d["andamento_lista"].append({"card":card["name"],"lista":nl,"membros":us})
        elif _pausa:
            # Comecado e parado. Aparece na mesma secao, apagado, para a equipe
            # ver o que ha para retomar — inclusive quando a etiqueta de pausa
            # SUBSTITUIU a EM ANDAMENTO, que e como a equipe usa no fim do dia.
            d["pausados_lista"].append({"card":card["name"],"lista":nl,
                                        "membros":us,"motivo":_pausa})

        # ── CARTÕES ABERTOS/PENDENTES: nunca filtrados por mês ─────────────────
        if not ok:
            d["abertos"]+=1
            if "URGENTE" in lb or "URGENTES" in nl.upper(): d["urgentes"]+=1
            # A etiqueta ATRASADO saiu do board: atraso vem do tempo medido.
            # Usa o mapa do board inteiro — consultar cartao a cartao seria uma
            # requisicao por cartao aberto a cada atualizacao do painel.
            #
            # O criterio e o mesmo da Analise de Metas, e nao mais uma copia
            # antiga dele. A daqui so olhava tempo de execucao: cartao que
            # ninguem tocou tem tempo zero e nunca ficava atrasado, mesmo aberto
            # ha semanas, e cartao parado esperando a plataforma responder era
            # contado como atraso da equipe. As duas telas mostravam numeros
            # diferentes para a mesma pergunta.
            if _pc_tv._card_atrasado(card, nl, _tempos_tv, _entradas_atr):
                d["atrasados"]+=1
                # Ver placar_core: a meta e sobre prioridade 8 a 10, nao sobre
                # o board inteiro.
                if int((_cfg_col.get(nl) or {}).get("prioridade", 5) or 5) >= 8:
                    d["atrasados_pri"]+=1
                    d["atrasados_pri_lista"].append({"nome":card["name"],"lista":nl})
            if "FALTA CONFERÊNCIA" in lb: d["falta_conf"]+=1
            if "FALTA INFORMAÇÃO" in lb: d["falta_info"]+=1
            if not us:
                if not filtro_mes or _mes_card_criacao(card) == filtro_mes:
                    d["sem_membro"] += 1  # data de criação — conta no mês em que o cartão foi aberto
                    d["sem_membro_lista"].append({"nome": card["name"], "lista": nl})
            if pt is None: d["falta_pts"]+=1
            if "PENDENTE" in lb:
                d["pend_lista"][nl]=d["pend_lista"].get(nl,0)+1
                if pt: d["pts_pendentes"]+=pt
            if "DESATIVAR" in nl.upper(): d["desativar"]+=1
            if "REATIVAR" in nl.upper(): d["reativar"]+=1
            continue  # cartão aberto não pontua — próximo card

        # ── A partir daqui: cartão concluído (ok=True) ─────────────────────────
        # Aplica filtro de mês somente para concluídos
        if filtro_mes:
            # Sem "if mc and": mês indeterminado deixa o cartão FORA do mês, em
            # vez de contar em qualquer mês que estiver aberto na tela.
            if _pc_tv._mes_card(card, _conclusoes_tv, _janela_tv) != filtro_mes:
                continue

        if tempo and tempo>0:
            d["tempo_lista"].setdefault(nl,[]).append(max(tempo-interr,0))

        # Retrabalho: conta cartões concluídos e de correção de fotos
        d["total_concl"]+=1
        if nl=="CORREÇÃO DE FOTOS: 0 PONTOS": d["correcao_concl"]+=1

        # Alerta: concluído sem membro atribuído
        if not us: d["concluido_sem_membro"].append({"card":card["name"],"lista":nl})

        # ── PONTUAÇÃO: somente concluídos no mês selecionado ───────────────────
        if pt is None: continue
        if nl in LISTAS_SEM_PONTUACAO: continue
        d["pts_equipe"]+=pt
        ma=[u for u in us if u in MEMBROS_ATIVOS]
        if ma:
            cada=pt/len(ma)
            for u in ma: d["pts_membro"][u]+=cada
    return d

# ── CSS ────────────────────────────────────────────────────────────────────────
CSS="""
<style>
.pm-card{background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);border-radius:8px;padding:8px 12px;display:flex;flex-direction:column;justify-content:center;min-height:48px;}
.pm-label{font-size:8px;color:var(--ms-texto-sec);text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px;}
.pm-value{font-size:16px;font-weight:700;line-height:1.1;}
.pm-sub{font-size:8px;color:var(--ms-texto-sec);margin-top:1px;}
.pm-sc{background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);border-radius:10px;padding:8px 6px;text-align:center;min-height:80px;display:flex;flex-direction:column;justify-content:center;align-items:center;}
.pm-badge{font-size:8px;font-weight:600;padding:2px 6px;border-radius:3px;margin-top:3px;display:inline-block;}
.fila-card{border-left:4px solid;border-radius:0 8px 8px 0;padding:9px 12px;margin-bottom:5px;display:flex;align-items:center;gap:10px;background:var(--ms-metric-bg);}
.fila-card-urgente{border-left:4px solid #E34948!important;background:rgba(227,73,72,0.07)!important;}
.fila-pos{font-size:20px;font-weight:700;min-width:28px;text-align:center;}
.fila-info{flex:1;}
.fila-nome{font-size:12px;font-weight:600;color:var(--ms-texto);}
.fila-meta{font-size:9px;color:var(--ms-texto-sec);}
.fila-eta{font-size:11px;font-weight:600;min-width:50px;text-align:right;}
.meta-ind-card{background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);border-radius:10px;padding:14px 16px;margin-bottom:8px;}
.meta-ind-titulo{font-size:12px;font-weight:600;color:var(--ms-texto);margin-bottom:6px;}
.meta-ind-barra-bg{background:var(--ms-metric-bd);border-radius:4px;height:8px;overflow:hidden;margin-bottom:3px;}
.vel-label{font-size:9px;color:var(--ms-texto-sec);text-transform:uppercase;letter-spacing:.6px;text-align:center;margin-top:4px;}
</style>
"""

# ── VELOCÍMETROS ───────────────────────────────────────────────────────────────
def _vel_meta(pct, meta_eq, saldo_eq, faltam):
    pct_clip=min(max(pct,0),110)
    ang=math.radians(-180+min(pct_clip/100,1)*180)
    cx,cy,r=130,125,105
    px=cx+r*math.cos(ang); py=cy+r*math.sin(ang)
    cor="#1BAF7A"
    perim=math.pi*r; dash=min(pct_clip/100,1)*perim
    return f"""
<div style="text-align:center;">
<svg viewBox="0 0 260 150" width="75%" style="display:block;margin:0 auto;overflow:visible;">
  <path d="M20,120 A110,110 0 0 1 240,120" fill="none" stroke="var(--ms-metric-bd)" stroke-width="18" stroke-linecap="round"/>
  <path d="M20,120 A110,110 0 0 1 240,120" fill="none" stroke="{cor}" stroke-width="18" stroke-linecap="round" stroke-dasharray="{dash:.1f} {perim:.1f}"/>
  <line x1="{cx}" y1="{cy}" x2="{px:.1f}" y2="{py:.1f}" stroke="var(--ms-texto)" stroke-width="3" stroke-linecap="round"/>
  <circle cx="{cx}" cy="{cy}" r="7" fill="var(--ms-texto)"/>
  <circle cx="{cx}" cy="{cy}" r="3" fill="var(--ms-metric-bg)"/>
  <text x="13" y="142" text-anchor="middle" font-size="9" fill="var(--ms-texto-sec)">0</text>
  <text x="247" y="142" text-anchor="middle" font-size="9" fill="var(--ms-texto-sec)">META</text>
</svg>
<div style="font-size:36px;font-weight:700;color:{cor};margin-top:2px;line-height:1;">{"%.1f%%" % min(pct,999) if pct < 10 else "%.0f%%" % min(pct,999)}</div>
<div class="vel-label">🏆 Meta Mensal</div>
</div>"""

def _vel_maxx(pct_maxx, meta_maxx_pts, saldo_eq):
    """Velocímetro dourado para Meta Maxx."""
    pct_clip=min(max(pct_maxx,0),115)
    ang=math.radians(-180+min(pct_clip/100,1)*180)
    cx,cy,r=130,125,105
    px=cx+r*math.cos(ang); py=cy+r*math.sin(ang)
    perim=math.pi*r; dash=min(pct_clip/100,1)*perim
    atingiu=saldo_eq>=meta_maxx_pts
    # Gradiente dourado brilhante
    return f"""
<div style="text-align:center;">
<svg viewBox="0 0 260 150" width="75%" style="display:block;margin:0 auto;overflow:visible;">
  <defs>
    <linearGradient id="goldGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" style="stop-color:#B8860B;stop-opacity:1"/>
      <stop offset="30%" style="stop-color:#FFD700;stop-opacity:1"/>
      <stop offset="60%" style="stop-color:#FFF8DC;stop-opacity:1"/>
      <stop offset="80%" style="stop-color:#FFD700;stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#B8860B;stop-opacity:1"/>
    </linearGradient>
    <!-- filterUnits e o detalhe que faz o ponteiro existir. No padrao
         (objectBoundingBox) a regiao do filtro e uma porcentagem da caixa do
         elemento — e o ponteiro fica EXATAMENTE horizontal quando a Maxx bate
         100%, entao a caixa dele tem altura zero, a regiao do filtro tem altura
         zero e o navegador nao desenha nada. O ponteiro sumia justo quando a
         meta era atingida. Em userSpaceOnUse a regiao e fixa no espaco do SVG e
         nao depende mais da forma do que esta sendo filtrado. -->
    <filter id="glow" filterUnits="userSpaceOnUse" x="0" y="0" width="260" height="150">
      <feGaussianBlur stdDeviation="2.5" result="coloredBlur"/>
      <feMerge><feMergeNode in="coloredBlur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <path d="M20,120 A110,110 0 0 1 240,120" fill="none" stroke="var(--ms-metric-bd)" stroke-width="18" stroke-linecap="round"/>
  <path d="M20,120 A110,110 0 0 1 240,120" fill="none" stroke="url(#goldGrad)" stroke-width="18" stroke-linecap="round"
        stroke-dasharray="{dash:.1f} {perim:.1f}" filter="url(#glow)"/>
  <line x1="{cx}" y1="{cy}" x2="{px:.1f}" y2="{py:.1f}" stroke="#FFD700" stroke-width="3" stroke-linecap="round" filter="url(#glow)"/>
  <circle cx="{cx}" cy="{cy}" r="7" fill="#FFD700" filter="url(#glow)"/>
  <circle cx="{cx}" cy="{cy}" r="3" fill="var(--ms-metric-bg)"/>
  <text x="13" y="142" text-anchor="middle" font-size="9" fill="#B8860B">0</text>
  <text x="247" y="142" text-anchor="middle" font-size="9" fill="#B8860B">MAXX</text>
</svg>
<div style="font-size:36px;font-weight:700;color:#FFD700;margin-top:2px;line-height:1;filter:drop-shadow(0 0 8px #FFD700);">{"%.1f%%" % min(pct_maxx,999) if pct_maxx < 10 else "%.0f%%" % min(pct_maxx,999)}</div>
<div class="vel-label" style="color:#FFD700;">{"⭐ META MAXX ATINGIDA!" if atingiu else "⭐ Meta Maxx"}</div>
</div>"""

def _card(label,valor,sub=None,cor="var(--ms-texto)",icone=""):
    s=f'<div class="pm-sub">{sub}</div>' if sub else ""
    return f'<div class="pm-card"><div class="pm-label">{icone} {label}</div><div class="pm-value" style="color:{cor};">{valor}</div>{s}</div>'

def _sc(label,valor,badge,cn,bb,bt):
    return f"""<div class="pm-sc">
  <div style="font-size:8px;color:var(--ms-texto-sec);text-transform:uppercase;letter-spacing:.4px;">{label}</div>
  <div style="font-size:24px;font-weight:700;color:{cn};line-height:1.1;margin:2px 0;">{valor}</div>
  <span class="pm-badge" style="background:{bb};color:{bt};">{badge}</span>
</div>"""

def _barra(nome,pts,meta,pen):
    saldo=pts-pen; pct=min(saldo/meta*100,100) if meta>0 else 0
    cor="#1BAF7A" if pct>=100 else ("#8BC34A" if pct>=75 else ("#4A90D9" if pct>=0 else "#4A90D9"))
    pen_h=f'<div style="font-size:9px;color:#E34948;margin-top:2px;">⚠ -{pen:.0f} pts penalidades</div>' if pen>0 else ""
    return (f'<div style="margin-bottom:10px;">'
            f'<div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px;">'
            f'<span style="color:var(--ms-texto);font-weight:600;">{nome}</span>'
            f'<span style="color:{cor};">{saldo:,.0f} / {meta:,.0f} · {pct:.0f}%</span></div>'
            f'<div style="background:var(--ms-metric-bd);border-radius:4px;height:8px;overflow:hidden;">'
            f'<div style="background:{cor};width:{pct:.1f}%;height:100%;border-radius:4px;"></div></div>'
            f'{pen_h}</div>')

def _fila_html(item):
    p=item["prioridade"]; urg=item.get("is_urgente",False) or p>=10
    cor="#E34948" if p>=10 else ("#EDA100" if p>=8 else ("#1BAF7A" if p>=6 else "#888"))
    extra_class="fila-card-urgente" if urg else ""
    urg_badge='<span style="font-size:8px;font-weight:700;color:#E34948;background:rgba(227,73,72,0.15);padding:1px 5px;border-radius:3px;margin-left:6px;">🚨 URGENTE</span>' if urg else ""
    nome=item["nome"][:50]+"..." if len(item["nome"])>50 else item["nome"]
    lista=item["lista"][:32]+"..." if len(item["lista"])>32 else item["lista"]
    return f"""<div class="fila-card {extra_class}" style="border-left-color:{cor};">
  <div class="fila-pos" style="color:{cor};">{item['posicao']}°</div>
  <div class="fila-info">
    <div class="fila-nome">{nome}{urg_badge}</div>
    <div class="fila-meta">{lista} · {item['membros']} · P{p}</div>
  </div>
  <div class="fila-eta" style="color:{cor};">~{_fmt_tempo(item['eta_min'])}</div>
</div>"""

# ── TV MODE HELPERS ────────────────────────────────────────────────────────────
def _g_pt(pct, r, cx=90, cy=92):
    """Ponto no arco do gauge SVG para um dado percentual (0-100)."""
    a = math.radians(180 - max(0.0, min(float(pct), 100.0)) / 100 * 180)
    return round(cx + r * math.cos(a), 1), round(cy - r * math.sin(a), 1)

def _alertas_tv_list(listas, cards, membros_map):
    """
    Alertas para o campo Atenção — 7 condições:
    1. Prioridade 8-10 com etiqueta PENDENTE (sem INTERROMPIDO MS)
    2. EM ANDAMENTO / Filmagem / Concluído sem membro atribuído
    3. PENDENTE + membro atribuído + >5 min sem virar EM ANDAMENTO
    4. Tempo de execução (relógio pausado por INTERROMPIDO / INTERROMPIDO MS) >= 1.5× tempo médio
    5. Concluído (dueComplete) com etiqueta PENDENTE ainda presente
    6. Mesmo cartão com EM ANDAMENTO + FILMAGEM simultaneamente
    7. Membro tem ≥1 cartão EM ANDAMENTO e ainda tem outros cartões só com FILMAGEM
    """
    import placar_core as _pc_al
    from datetime import timedelta as _td_al
    # Uma chamada para o board inteiro. Antes era um GET por cartao em execucao,
    # a cada atualizacao do painel.
    _acoes_al = _pc_al._buscar_acoes_board(_pc_al._desde_curto(45), max_paginas=5)
    agora   = datetime.now(timezone.utc)
    alertas = []

    # Pré-computa dados relevantes por membro para condição 7
    # membro → {"andamento": [card_name,...], "filmagem": [card_name,...]}
    membro_estado = {}

    for card in cards:
        nl = listas.get(card["idList"], "")
        if nl in COLUNAS_SKIP:
            continue
        lb = _labels(card)
        us = _users(card, membros_map)
        _pausado     = _parado(lb)
        is_andamento = LABEL_EM_ANDAMENTO_STR in lb and not _pausado
        is_filmagem  = LABEL_FILMAGEM         in lb and not _pausado
        for u in us:
            if u not in membro_estado:
                membro_estado[u] = {"andamento": [], "filmagem_puro": []}
            if is_andamento:
                membro_estado[u]["andamento"].append(card["name"])
            # filmagem "puro" = FILMAGEM mas NÃO EM ANDAMENTO (evita dupla contagem)
            if is_filmagem and not is_andamento:
                membro_estado[u]["filmagem_puro"].append(card["name"])

    for card in cards:
        nl = listas.get(card["idList"], "")
        if nl in COLUNAS_SKIP:
            continue

        lb          = _labels(card)
        us          = _users(card, membros_map)
        cfg         = _pc_al.cfg_coluna(nl)
        prio        = cfg.get("prioridade", 0)
        tempo_medio = cfg.get("tempo_min", 0)
        concluido   = card.get("dueComplete", False)

        is_pendente     = LABEL_PENDENTE_STR      in lb
        is_interrompido = _parado(lb)
        is_andamento    = LABEL_EM_ANDAMENTO_STR  in lb and not is_interrompido
        is_filmagem     = LABEL_FILMAGEM          in lb and not is_interrompido

        # ── 1. P8-10 com etiqueta PENDENTE ─────────────────────────────────────
        if prio >= 8 and is_pendente and not is_interrompido:
            alertas.append({
                "tipo": "urgente", "lab": "🔴 Alta Prioridade",
                "pos": f"P{prio}", "nome": card["name"], "col": nl,
                "detalhe": f"Prioridade {prio} aguardando execução",
                "_s": (0, -prio, _data_card(card).timestamp()),
            })

        # ── 2. Em andamento / Filmagem / Concluído sem membro ──────────────────
        if (is_andamento or is_filmagem or concluido) and not us:
            status = ("Filmagem" if is_filmagem
                      else "Em andamento" if is_andamento
                      else "Concluído")
            alertas.append({
                "tipo": "atencao", "lab": "🟡 Sem Membro",
                "pos": "—", "nome": card["name"], "col": nl,
                "detalhe": f"{status} · sem membro atribuído",
                "_s": (1, -prio, _data_card(card).timestamp()),
            })

        # ── 3. PENDENTE + membro + >5 min sem virar EM ANDAMENTO ───────────────
        if is_pendente and us and not is_interrompido and not is_andamento:
            ultima  = _data_card(card)
            min_dec = (agora - ultima).total_seconds() / 60
            if min_dec >= MIN_PENDENTE_COM_MEMBRO:
                nomes_mb = ", ".join(MEMBROS_ATIVOS.get(u, u) for u in us)
                alertas.append({
                    "tipo": "atencao", "lab": "🟡 Pend. c/ Membro",
                    "pos": f"{int(min_dec)}min",
                    "nome": card["name"], "col": nl,
                    "detalhe": f"Pendente há {int(min_dec)}min — {nomes_mb}",
                    "_s": (2, -min_dec, _data_card(card).timestamp()),
                })

        # ── 4. Tempo de execução >= 1.5× tempo médio ───────────────────────────
        if (is_andamento or is_filmagem) and tempo_medio > 0 and not is_interrompido:
            try:
                tempo_exec, _ = _pc_al.tempo_execucao_min(card["id"], _acoes_al)
                if tempo_exec >= tempo_medio * FATOR_VENCIMENTO:
                    pct_uso = tempo_exec / tempo_medio * 100
                    alertas.append({
                        "tipo": "atencao", "lab": "⏰ Tempo Crítico",
                        "pos": f"{int(pct_uso)}%",
                        "nome": card["name"], "col": nl,
                        "detalhe": (
                            f"{_fmt_tempo(int(tempo_exec))} decorrido "
                            f"(prev. {_fmt_tempo(tempo_medio)})"
                        ),
                        "_s": (3, -(tempo_exec / tempo_medio),
                               _data_card(card).timestamp()),
                    })
            except Exception:
                pass

        # ── 5. Concluído (dueComplete) com etiqueta PENDENTE ainda presente ────
        if concluido and is_pendente:
            alertas.append({
                "tipo": "atencao", "lab": "🟡 Concl. c/ Pendente",
                "pos": "—", "nome": card["name"], "col": nl,
                "detalhe": "Marcado como concluído mas etiqueta Pendente não removida",
                "_s": (4, -prio, _data_card(card).timestamp()),
            })

        # ── 6. Mesmo cartão com EM ANDAMENTO + FILMAGEM simultaneamente ─────────
        if is_andamento and is_filmagem:
            nomes_mb = ", ".join(MEMBROS_ATIVOS.get(u, u) for u in us) if us else "sem membro"
            alertas.append({
                "tipo": "atencao", "lab": "🟡 And.+Film. no mesmo",
                "pos": "—", "nome": card["name"], "col": nl,
                "detalhe": f"Em Andamento sem remover Filmagem — {nomes_mb}",
                "_s": (5, -prio, _data_card(card).timestamp()),
            })

    # ── 7. Membro tem EM ANDAMENTO e ainda tem outros cartões só com FILMAGEM ──
    alertas_mb_vistos = set()  # evita duplicar por membro
    for membro, estado in membro_estado.items():
        if estado["andamento"] and estado["filmagem_puro"]:
            if membro in alertas_mb_vistos:
                continue
            alertas_mb_vistos.add(membro)
            nome_mb  = MEMBROS_ATIVOS.get(membro, membro)
            n_film   = len(estado["filmagem_puro"])
            alertas.append({
                "tipo": "atencao", "lab": "🟡 Filmagem pendente",
                "pos": f"{n_film} cartão(ões)",
                "nome": f"{nome_mb} — filmagens não encerradas",
                "col": "—",
                "detalhe": (
                    f"{nome_mb} está Em Andamento mas ainda tem "
                    f"{n_film} cartão(ões) com Filmagem: "
                    f"{', '.join(estado['filmagem_puro'][:3])}"
                    + (" ..." if n_film > 3 else "")
                ),
                "_s": (6, -n_film, 0.0),
            })

    alertas.sort(key=lambda x: x["_s"])
    # Coluna que existe no Trello e nao esta configurada: o trabalho dela ficava
    # fora do painel inteiro, sem nenhum aviso.
    _desconhecidas = sorted(_pc_al.COLUNAS_DESCONHECIDAS)
    for _col in _desconhecidas[:3]:
        _qtd = sum(1 for c in cards
                   if listas.get(c["idList"], "") == _col and not c.get("dueComplete"))
        alertas.append({
            "tipo": "atencao", "lab": "⚙️ Coluna sem config",
            "pos": f"{_qtd}", "nome": _col, "col": _col,
            "detalhe": f"{_qtd} cartao(oes) usando prioridade e tempo padrao",
            "_s": (1, 0, 0),
        })

    return alertas

def _tv_full_html(
    pct_eq, pct_maxx,
    saldo_eq, meta_eq, faltam, pts_pendentes,
    meta_maxx_pts, faltam_maxx, maxx_pct, pen_total, n_pen,
    d, fila, alertas, pend_lista,
    pct_pri_ok, pct_retrab_n, pct_pen_n, pct_retrab_x, pct_pen_x,
    pct_com_membro, desc_retrab, max_retrab_n, max_pen_n, max_retrab_x, max_pen_x,
    n_urgentes, n_sem_mb, agora_str,
    meta_ind_map=None,
    ritmo_tv_html="",
    sem_membro_lista=None, sem_membro_desc="",
    # Carimbo de quando este HTML foi gerado. O JS da TV compara com o relogio
    # do navegador e mostra a faixa vermelha se os dados envelhecerem — uma TV
    # congelada precisa se anunciar, senao mostra numeros plausiveis e velhos.
    gerado_epoch=0,
):
    def fp(v): return f"{'%.1f'%v if v<10 else '%.0f'%v}%"

    # Gauge META MENSAL
    ax_m, ay_m = _g_pt(pct_eq, 78)
    nx_m, ny_m = _g_pt(pct_eq, 72)
    fill_m = (f'<path d="M 12 92 A 78 78 0 0 1 {ax_m} {ay_m}" fill="none" '
              f'stroke="#1BAF7A" stroke-width="11" stroke-linecap="butt"/>'
              if pct_eq >= 0.5 else "")

    # Gauge META MAXX
    ax_x, ay_x = _g_pt(pct_maxx, 78)
    nx_x, ny_x = _g_pt(pct_maxx, 72)
    fill_x = (f'<path d="M 12 92 A 78 78 0 0 1 {ax_x} {ay_x}" fill="none" '
              f'stroke="#FFD700" stroke-width="11" stroke-linecap="butt"/>'
              if pct_maxx >= 0.5 else "")

    # Pendentes por coluna
    pend_html = ""
    if pend_lista:
        max_q = max(pend_lista.values()) or 1
        for nl, qtd in sorted(pend_lista.items(), key=lambda x: -x[1]):
            pct_b = qtd / max_q * 100
            is_red = "URGENTE" in nl.upper()
            fc = "#E34948" if is_red else "#EDA100"
            nc = "red" if is_red else ""
            nl_s = (nl[:28]+"…") if len(nl)>28 else nl
            pend_html += (f'<div class="pend-item">'
                          f'<div class="pend-header"><span>{nl_s}</span>'
                          f'<span class="pend-num {nc}">{qtd}</span></div>'
                          f'<div class="pend-track"><div class="pend-fill" '
                          f'style="width:{pct_b:.0f}%;background:{fc};"></div></div></div>')

    # Desempenho por colaborador (abaixo de pendentes por coluna)
    desempenho_html = ""
    _pts_mb = d.get("pts_membro", {})
    _pen_mb = d.get("pen_membro", {})
    _meta_per = meta_ind_map or {}
    _meta_base = meta_eq / max(len(MEMBROS_ATIVOS), 1)
    for _u, _nm in MEMBROS_ATIVOS.items():
        _pts = _pts_mb.get(_u, 0.0)
        _pen = _pen_mb.get(_u, 0.0)
        _meta_u = _meta_per.get(_u, _meta_base)
        _pct = min(_pts / _meta_u * 100, 100) if _meta_u > 0 else 0
        _pen_str = f" <span style='color:#E34948;font-size:9px;'>-{_pen:.0f}p</span>" if _pen > 0 else ""
        _pts_fmt  = f"{_pts:,.0f}".replace(",", ".")
        _meta_fmt = f"{_meta_u:,.0f}".replace(",", ".")
        desempenho_html += (
            f'<div class="pend-item">'
            f'<div class="pend-header"><span>{_nm}</span>'
            f'<span class="pend-num" style="color:#1BAF7A;">{_pts_fmt}/{_meta_fmt}{_pen_str}</span></div>'
            f'<div class="pend-track"><div class="pend-fill" style="width:{_pct:.0f}%;background:#1BAF7A;"></div></div>'
            f'</div>'
        )

    # Em andamento
    and_html = ""
    for c in (d.get("andamento_lista") or []):
        ms = ", ".join(MEMBROS_ATIVOS.get(u,u) for u in c.get("membros",[])) or "—"
        nome = (c["card"][:42]+"…") if len(c["card"])>42 else c["card"]
        ls   = (c["lista"][:28]+"…") if len(c["lista"])>28 else c["lista"]
        and_html += (f'<div class="card-base">'
                     f'<div class="card-and-nome">{nome}</div>'
                     f'<div class="card-and-sub">{ls} · <span>{ms}</span></div></div>')
    # Parados com EM ANDAMENTO ainda no cartao: aparecem aqui, apagados e com o
    # motivo, para a equipe ver o que ha para retomar. Nao entram no contador.
    for c in (d.get("pausados_lista") or []):
        ms = ", ".join(MEMBROS_ATIVOS.get(u,u) for u in c.get("membros",[])) or "—"
        nome = (c["card"][:42]+"…") if len(c["card"])>42 else c["card"]
        ls   = (c["lista"][:28]+"…") if len(c["lista"])>28 else c["lista"]
        and_html += (f'<div class="card-base" style="opacity:.62;'
                     f'border-left:3px solid #EDA100;">'
                     f'<div class="card-and-nome">⏸ {nome}</div>'
                     f'<div class="card-and-sub">{ls} · <span>{ms}</span>'
                     f' · <span style="color:#EDA100;">{c["motivo"]}</span></div></div>')
    if not and_html:
        and_html = '<div style="font-size:10px;color:#555;padding:8px;">Nenhum em andamento</div>'

    # Próximas 5 da fila — visual idêntico aos cards de alerta
    ORDS = ["1°","2°","3°","4°","5°"]
    fila_html = ""
    for i, item in enumerate(fila[:5]):
        p = item["prioridade"]
        cor = "#E34948" if p>=10 else ("#EDA100" if p>=8 else ("#1BAF7A" if p>=6 else "#888"))
        tipo_cls = "urgente" if (item.get("is_urgente") or p>=8) else "atencao"
        nome = (item["nome"][:42]+"…") if len(item["nome"])>42 else item["nome"]
        ls   = (item["lista"][:24]+"…") if len(item["lista"])>24 else item["lista"]
        eta  = _fmt_tempo(item["eta_min"])
        fila_html += (f'<div class="alerta-item {tipo_cls}">'
                      f'<div class="alerta-item-prioridade">'
                      f'<span style="color:{cor};">{ORDS[i]} — P{p}</span>'
                      f'<span style="color:#888;font-weight:400;">~{eta}</span>'
                      f'</div>'
                      f'<div class="alerta-item-nome">{nome}</div>'
                      f'<div class="alerta-item-col">{ls}</div>'
                      f'</div>')
    if not fila_html:
        fila_html = '<div style="font-size:10px;color:#555;padding:8px;">Fila vazia 🎉</div>'

    # Alertas JS
    n_alerta_urg = sum(1 for a in alertas if a.get("tipo") == "urgente")
    n_alerta_atc = sum(1 for a in alertas if a.get("tipo") == "atencao")
    tem_alertas      = len(alertas) > 0
    alerta_cls       = "com-alerta" if tem_alertas else "sem-alerta"
    alerta_titulo_txt = "⚠️ ATENÇÃO" if tem_alertas else "✅ TUDO OK"
    alerta_titulo_cor = "#E34948" if tem_alertas else "#555"
    alerta_sub_html   = (f"{n_alerta_urg} prioritários · {n_alerta_atc} atenção"
                         if tem_alertas else "Nenhum alerta no momento")
    alertas_js = "[\n"
    for a in alertas:
        ne = a["nome"].replace('"','\\"').replace("'","\\'")
        ce = a["col"].replace('"','\\"')
        de = a.get("detalhe","").replace('"','\\"').replace("'","\\'")
        alertas_js += (f'  {{tipo:"{a["tipo"]}",prioridade:"{a["lab"]}",pos:"{a["pos"]}",'
                       f'nome:"{ne}",col:"{ce}",detalhe:"{de}"}},\n')
    alertas_js += "]"

    pend_total = sum(pend_lista.values()) if pend_lista else 0
    atrasados  = d.get("atrasados_pri", 0)
    desc_pri   = ("Nenhum cartão prioritário (P8-P10) atrasado" if atrasados == 0
                  else f"{atrasados} prioritário(s) atrasado(s)")

    # Coletiva: threshold bars (verde ↔ vermelho), progresso sempre verde
    _cor_tv_eq       = "#1BAF7A"  # progresso — sempre verde
    _cor_tv_pri      = "#1BAF7A" if pct_pri_ok      >= 100 else "#E34948"
    _cor_tv_retrab_n = "#1BAF7A" if pct_retrab_n    >= 100 else "#E34948"
    _cor_tv_cmb      = "#1BAF7A" if pct_com_membro  >= 99.5 else "#E34948"
    # MAXX: threshold bars (amarelo ↔ vermelho), progresso sempre amarelo
    _cor_tv_maxx     = "#FFD700"  # progresso — sempre amarelo
    _cor_tv_prix     = "#FFD700" if pct_pri_ok      >= 100 else "#E34948"
    _cor_tv_retrab_x = "#FFD700" if pct_retrab_x    >= 100 else "#E34948"
    _cor_tv_cmbx     = "#FFD700" if pct_com_membro  >= 99.5 else "#E34948"
    # Mesma legenda do painel: quem monta a descrição é quem calcula o
    # percentual. Antes a TV recebia a lista de cartões ABERTOS sem membro,
    # enquanto a barra media os em andamento e concluídos — 100% com faltantes
    # listados embaixo.
    _tv_sem_mb_desc = sem_membro_desc or "Em andamento e concluídos"
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<!-- Sem <meta refresh>: recarregar a pagina apaga a liberacao de audio do
     navegador e a TV volta a ficar muda. A atualizacao e feita por JS, trocando
     so o conteudo. -->
<title>MS Studio — TV</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
html,body{{width:100%;height:100%;overflow:hidden;background:#1a1a1a;color:#e0e0e0;font-family:Arial,Helvetica,sans-serif;}}
.tv-root{{position:absolute;top:0;left:0;width:100%;height:100%;overflow:hidden;}}
#tv-carimbo{{position:absolute;top:2px;right:8px;font-size:8px;color:#6a6a6a;letter-spacing:.3px;z-index:99;}}
#tv-carimbo.velho{{color:#E34948;font-weight:700;}}
.bloco-metas{{position:absolute;left:10px;right:10px;top:5px;height:212px;display:-webkit-box;display:-webkit-flex;display:flex;gap:6px;overflow:hidden;}}
.bloco-metas>div{{-webkit-flex:1;flex:1;overflow:hidden;}}
.mini-cards{{display:-webkit-box;display:-webkit-flex;display:flex;-webkit-flex-wrap:wrap;flex-wrap:wrap;gap:3px;height:100%;}}
.mini-card{{-webkit-flex:1 1 45%;flex:1 1 45%;background:#252525;border-radius:5px;padding:3px 6px;border:1px solid #444;text-align:center;overflow:hidden;}}
.mini-card.verde{{border-color:#1BAF7A;background:#0d2e1f;}}
.mini-card.amarelo{{border-color:#EDA100;background:#2a1e05;}}
.mini-card.ouro{{border-color:#FFD700;background:#2a2000;}}
.mini-card.red{{border-color:#E34948;background:#2a1500;}}
.mc-label{{font-size:6px;text-transform:uppercase;letter-spacing:.4px;display:block;}}
.mc-label.verde{{color:#1BAF7A;}}.mc-label.amarelo{{color:#EDA100;}}.mc-label.ouro{{color:#FFD700;}}.mc-label.red{{color:#E34948;}}
.mc-val{{font-size:13px;font-weight:700;display:block;line-height:1.1;}}
.mc-val.verde{{color:#e0f5ec;}}.mc-val.amarelo{{color:#fae8b0;}}.mc-val.ouro{{color:#fff5cc;}}.mc-val.red{{color:#fae8b0;}}
.mc-sub{{font-size:6px;display:block;}}
.mc-sub.verde{{color:#1BAF7A;}}.mc-sub.amarelo{{color:#EDA100;}}.mc-sub.ouro{{color:#FFD700;}}.mc-sub.red{{color:#E34948;}}
.bloco-titulo{{font-size:7px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px;}}
.bloco-titulo.verde{{color:#1BAF7A;}}.bloco-titulo.ouro{{color:#FFD700;}}
.gauge-col{{display:-webkit-box;display:-webkit-flex;display:flex;-webkit-box-orient:vertical;-webkit-flex-direction:column;flex-direction:column;-webkit-box-align:center;-webkit-align-items:center;align-items:center;-webkit-box-pack:center;-webkit-justify-content:center;justify-content:center;gap:4px;height:100%;}}
.gauge-svg{{height:90px;width:auto;}}
.gauge-info{{text-align:center;}}
.gauge-pct{{font-size:30px;font-weight:700;line-height:1;}}
.gauge-pct.verde{{color:#1BAF7A;}}.gauge-pct.ouro{{color:#FFD700;}}
.gauge-label{{font-size:10px;color:#aaa;margin-top:3px;}}
#som-btn{{position:fixed;bottom:14px;right:14px;background:#1a1a1aee;border:1px solid #444;border-radius:8px;padding:8px 14px;color:#aaa;font-size:13px;cursor:pointer;z-index:9999;-webkit-user-select:none;user-select:none;}}
#som-btn.ativo{{color:#1BAF7A;border-color:#1BAF7A;}}
.tip-maxx{{-webkit-animation:glow-tip 2.4s ease-in-out infinite;animation:glow-tip 2.4s ease-in-out infinite;}}
@-webkit-keyframes glow-tip{{0%,100%{{-webkit-filter:drop-shadow(0 0 4px #FFD700);}}50%{{-webkit-filter:drop-shadow(0 0 10px #FFD700);}}}}
@keyframes glow-tip{{0%,100%{{filter:drop-shadow(0 0 4px #FFD700);}}50%{{filter:drop-shadow(0 0 10px #FFD700);}}}}
.bloco-status{{position:absolute;left:10px;right:10px;top:220px;height:72px;display:-webkit-box;display:-webkit-flex;display:flex;gap:4px;overflow:hidden;-webkit-flex-wrap:nowrap;flex-wrap:nowrap;}}
.pill{{-webkit-flex:1;flex:1;background:#252525;border-radius:6px;padding:6px 4px;text-align:center;border:1px solid #444;overflow:hidden;display:-webkit-box;display:-webkit-flex;display:flex;-webkit-flex-direction:column;flex-direction:column;-webkit-box-pack:center;-webkit-justify-content:center;justify-content:center;}}
.pill-val{{font-size:20px;font-weight:700;display:block;line-height:1.1;}}
.pill-label{{font-size:9px;color:#aaa;text-transform:uppercase;letter-spacing:.3px;display:block;margin-bottom:2px;}}
.pill-badge{{font-size:8px;display:block;padding:1px 0;margin-top:2px;}}
.pill.urgente{{background:#E3494820;border-color:#E34948;}}.pill.urgente .pill-val{{color:#E34948;}}
.pill.atencao{{background:#EDA10020;border-color:#EDA100;}}.pill.atencao .pill-val{{color:#EDA100;}}
.pill.ok{{background:#1BAF7A20;border-color:#1BAF7A;}}.pill.ok .pill-val{{color:#1BAF7A;}}
.bloco-barras{{position:absolute;left:10px;right:10px;top:296px;height:255px;display:-webkit-box;display:-webkit-flex;display:flex;gap:6px;overflow:hidden;}}
.barra-box{{-webkit-flex:1;flex:1;background:#252525;border-radius:6px;padding:5px 10px;overflow:hidden;}}
.barra-box.verde-border{{border:1px solid #1BAF7A33;}}.barra-box.ouro-border{{border:1px solid #FFD70033;}}
.barra-item{{margin-bottom:3px;}}
.barra-header{{display:-webkit-box;display:-webkit-flex;display:flex;-webkit-box-pack:justify;-webkit-justify-content:space-between;justify-content:space-between;font-size:8px;margin-bottom:1px;}}
.barra-track{{background:#3a3a3a;border-radius:2px;height:4px;overflow:hidden;}}
.barra-fill{{height:100%;border-radius:2px;}}
.barra-desc{{font-size:6px;color:#777;margin-top:1px;}}
.bloco-bottom{{position:absolute;left:10px;right:10px;top:555px;height:521px;display:-webkit-box;display:-webkit-flex;display:flex;gap:6px;overflow:hidden;}}
.sub-bloco-pend{{width:13%;height:100%;overflow:hidden;padding-right:4px;}}
.sub-bloco-and{{width:21%;height:100%;overflow:hidden;}}
.sub-bloco-fila{{width:29%;height:100%;overflow:hidden;}}
.sub-bloco-alerta{{width:36%;height:100%;overflow:hidden;}}
.sub-titulo{{font-size:12px;font-weight:700;margin-bottom:4px;padding-bottom:3px;border-bottom:1px solid #2e2e2e;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.cards-col{{overflow:hidden;}}
.card-base{{background:#252525;border:1px solid #3a3a3a;border-radius:6px;padding:8px 12px;overflow:hidden;margin-bottom:4px;}}
.card-and-nome{{font-size:13px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
.card-and-sub{{font-size:10px;color:#888;margin-top:2px;}}.card-and-sub span{{color:#1BAF7A;}}
.fila-inner{{display:-webkit-box;display:-webkit-flex;display:flex;gap:6px;-webkit-box-align:center;-webkit-align-items:center;align-items:center;}}
.fila-num{{font-size:16px;font-weight:700;min-width:24px;}}
.fila-info{{-webkit-flex:1;flex:1;overflow:hidden;}}
.fila-nome{{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.fila-sub{{font-size:10px;color:#888;}}
.fila-tempo{{font-size:10px;color:#888;white-space:nowrap;}}
.badge-urg{{background:#E3494830;color:#E34948;border:1px solid #E34948;border-radius:3px;font-size:9px;padding:0 3px;}}
.pend-item{{margin-bottom:6px;}}
.pend-header{{display:-webkit-box;display:-webkit-flex;display:flex;-webkit-box-pack:justify;-webkit-justify-content:space-between;justify-content:space-between;font-size:11px;margin-bottom:2px;}}
.pend-header .pend-num{{font-weight:700;color:#EDA100;}}.pend-header .pend-num.red{{color:#E34948;}}
.pend-track{{background:#3a3a3a;border-radius:2px;height:6px;overflow:hidden;}}
.pend-fill{{height:100%;border-radius:2px;background:#EDA100;}}
.alerta-col{{overflow:hidden;}}
.alerta-header{{border-radius:6px;padding:5px 10px;text-align:center;margin-bottom:4px;}}
.alerta-header.com-alerta{{background:#E3494812;border:2px solid #E34948;-webkit-animation:pulso 2s ease-in-out infinite;animation:pulso 2s ease-in-out infinite;}}
.alerta-header.sem-alerta{{background:#1a1a1a;border:1px solid #333;}}
.alerta-header.com-alerta.tocando{{-webkit-animation:pulso-forte 0.35s ease-in-out infinite!important;animation:pulso-forte 0.35s ease-in-out infinite!important;}}
@-webkit-keyframes pulso{{0%,100%{{background:#E3494812;border-color:#E34948;}}50%{{background:#E3494840;border-color:#FF6B6B;}}}}
@keyframes pulso{{0%,100%{{background:#E3494812;border-color:#E34948;}}50%{{background:#E3494840;border-color:#FF6B6B;}}}}
@-webkit-keyframes pulso-forte{{0%,100%{{background:#E3494820;border-color:#E34948;}}50%{{background:#E3494880;border-color:#FF5555;}}}}
@keyframes pulso-forte{{0%,100%{{background:#E3494820;border-color:#E34948;}}50%{{background:#E3494880;border-color:#FF5555;}}}}
.alerta-titulo{{font-size:14px;font-weight:900;letter-spacing:2px;color:#E34948;}}
.alerta-sub{{font-size:10px;color:#aaa;}}
.alerta-lista{{overflow:hidden;}}
.alerta-item{{border-radius:5px;padding:6px 12px;margin-bottom:4px;overflow:hidden;}}
.alerta-item.urgente{{background:#E3494818;border-left:3px solid #E34948;}}
.alerta-item.atencao{{background:#EDA10015;border-left:3px solid #EDA100;}}
.alerta-item-prioridade{{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;display:-webkit-box;display:-webkit-flex;display:flex;-webkit-box-pack:justify;-webkit-justify-content:space-between;justify-content:space-between;}}
.alerta-item.urgente .alerta-item-prioridade{{color:#E34948;}}.alerta-item.atencao .alerta-item-prioridade{{color:#EDA100;}}
.alerta-item-nome{{font-size:13px;font-weight:600;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.alerta-item-col{{font-size:10px;color:#aaa;}}
</style>
</head>
<body>
<div class="tv-root">

  <!-- Carimbo de geracao: sem ele nao da para olhar a TV e saber se o dado e
       de agora ou de ontem. O painel ja ficou congelado sem ninguem perceber.
       O script no rodape pinta de vermelho quando passa de 5 minutos. -->
  <div id="tv-carimbo" data-gerado="{agora_str}">atualizado {agora_str}</div>

  <div class="bloco-metas" id="tv-bm">
    <div>
      <div class="bloco-titulo verde">🏆 Meta Mensal</div>
      <div class="mini-cards">
        <div class="mini-card verde"><span class="mc-label verde">Meta</span><span class="mc-val verde">{meta_eq:,.0f}</span><span class="mc-sub verde">pts/mês</span></div>
        <div class="mini-card amarelo"><span class="mc-label amarelo">Atual</span><span class="mc-val amarelo">{saldo_eq:,.0f}</span><span class="mc-sub amarelo">{fp(pct_eq)} da meta</span></div>
        <div class="mini-card amarelo"><span class="mc-label amarelo">Faltam</span><span class="mc-val amarelo">{faltam:,.0f}</span><span class="mc-sub amarelo">pts</span></div>
        <div class="mini-card amarelo"><span class="mc-label amarelo">Em Aberto</span><span class="mc-val amarelo">{pts_pendentes:,.0f}</span><span class="mc-sub amarelo">pendentes</span></div>
      </div>
    </div>
    <div class="gauge-col">
      <svg class="gauge-svg" viewBox="0 0 180 100" xmlns="http://www.w3.org/2000/svg">
        <path d="M 12 92 A 78 78 0 0 1 168 92" fill="none" stroke="#2e2e2e" stroke-width="11" stroke-linecap="butt"/>
        {fill_m}
        <line x1="12" y1="92" x2="18" y2="92" stroke="#666" stroke-width="1.5"/>
        <line x1="90" y1="14" x2="90" y2="21" stroke="#444" stroke-width="1.5"/>
        <line x1="168" y1="92" x2="162" y2="92" stroke="#444" stroke-width="1.5"/>
        <text x="8" y="89" text-anchor="end" fill="#555" font-size="7" font-family="Arial">0</text>
        <text x="172" y="89" text-anchor="start" fill="#555" font-size="7" font-family="Arial">100%</text>
        <line x1="90" y1="92" x2="{nx_m}" y2="{ny_m}" stroke="#1BAF7A" stroke-width="2.5" stroke-linecap="round"/>
        <circle cx="90" cy="92" r="5" fill="#222" stroke="#1BAF7A" stroke-width="1.5"/>
        <circle cx="{nx_m}" cy="{ny_m}" r="3.5" fill="#1BAF7A"/>
      </svg>
      <div class="gauge-info">
        <div class="gauge-pct verde">{fp(pct_eq)}</div>
        <div class="gauge-label">🏆 META MENSAL</div>
      </div>
      {ritmo_tv_html}
    </div>
    <div class="gauge-col">
      <svg class="gauge-svg" viewBox="0 0 180 100" xmlns="http://www.w3.org/2000/svg">
        <path d="M 12 92 A 78 78 0 0 1 168 92" fill="none" stroke="#2e2e2e" stroke-width="11" stroke-linecap="butt"/>
        {fill_x}
        <line x1="12" y1="92" x2="18" y2="92" stroke="#666" stroke-width="1.5"/>
        <line x1="90" y1="14" x2="90" y2="21" stroke="#444" stroke-width="1.5"/>
        <line x1="168" y1="92" x2="162" y2="92" stroke="#444" stroke-width="1.5"/>
        <text x="8" y="89" text-anchor="end" fill="#555" font-size="7" font-family="Arial">0</text>
        <text x="172" y="89" text-anchor="start" fill="#555" font-size="7" font-family="Arial">100%</text>
        <!-- Sem a classe de brilho: aqui o glow e um filter CSS, que tambem
             tem a regiao presa a caixa do elemento, e a caixa de uma linha
             horizontal tem altura zero. O pulso dourado fica no tip-maxx, que e
             um circulo e nunca degenera. -->
        <line x1="90" y1="92" x2="{nx_x}" y2="{ny_x}" stroke="#FFD700" stroke-width="2.5" stroke-linecap="round"/>
        <circle cx="90" cy="92" r="5" fill="#222" stroke="#FFD700" stroke-width="1.5"/>
        <circle class="tip-maxx" cx="{nx_x}" cy="{ny_x}" r="3.5" fill="#FFD700"/>
      </svg>
      <div class="gauge-info">
        <div class="gauge-pct ouro">{fp(pct_maxx)}</div>
        <div class="gauge-label">⭐ META MAXX</div>
      </div>
    </div>
    <div>
      <div class="bloco-titulo ouro">⭐ Meta Maxx</div>
      <div class="mini-cards">
        <div class="mini-card ouro"><span class="mc-label ouro">Maxx</span><span class="mc-val ouro">{meta_maxx_pts:,.0f}</span><span class="mc-sub ouro">+{maxx_pct-100}% meta</span></div>
        <div class="mini-card amarelo"><span class="mc-label amarelo">Saldo c/ pen.</span><span class="mc-val amarelo">{saldo_eq:,.0f}</span><span class="mc-sub amarelo">{fp(pct_maxx)} Maxx</span></div>
        <div class="mini-card amarelo"><span class="mc-label amarelo">Faltam</span><span class="mc-val amarelo">{faltam_maxx:,.0f}</span><span class="mc-sub amarelo">p/ bônus</span></div>
        <div class="mini-card red"><span class="mc-label red">Penalidades</span><span class="mc-val red">-{pen_total:,.0f}</span><span class="mc-sub red">{n_pen} ocorrência(s)</span></div>
      </div>
    </div>
  </div>

  <div class="bloco-status" id="tv-bs">
    <div class="pill atencao"><span class="pill-label">Cartões Pend.</span><span class="pill-val">{pend_total}</span><span class="pill-badge" style="background:#EDA10030;color:#EDA100;">Pendente</span></div>
    <div class="pill atencao"><span class="pill-label">Pts Pendentes</span><span class="pill-val">{pts_pendentes:,.0f}</span><span class="pill-badge" style="background:#EDA10030;color:#EDA100;">Aberto</span></div>
    <div class="pill ok"><span class="pill-label">Em Andamento</span><span class="pill-val">{d.get("em_andamento",0)}</span><span class="pill-badge" style="background:#1BAF7A30;color:#1BAF7A;">Ativo</span></div>
    <div class="pill urgente"><span class="pill-label">Atrasados</span><span class="pill-val">{d.get("atrasados",0)}</span><span class="pill-badge" style="background:#E3494830;color:#E34948;">Atenção</span></div>
    <div class="pill urgente"><span class="pill-label">Desativar</span><span class="pill-val">{d.get("desativar",0)}</span><span class="pill-badge" style="background:#E3494830;color:#E34948;">Prioritário</span></div>
    <div class="pill urgente"><span class="pill-label">Reativar</span><span class="pill-val">{d.get("reativar",0)}</span><span class="pill-badge" style="background:#E3494830;color:#E34948;">Normal</span></div>
    <div class="pill urgente"><span class="pill-label">Urgentes</span><span class="pill-val">{n_urgentes}</span><span class="pill-badge" style="background:#E3494830;color:#E34948;">Crítico</span></div>
    <div class="pill atencao"><span class="pill-label">Falta Info</span><span class="pill-val">{d.get("falta_info",0)}</span><span class="pill-badge" style="background:#EDA10020;color:#EDA100;">Pendente</span></div>
    <div class="pill atencao"><span class="pill-label">Falta Pontuação</span><span class="pill-val">{d.get("falta_pts",0)}</span><span class="pill-badge" style="background:#EDA10020;color:#EDA100;">Revisar</span></div>
    <div class="pill urgente"><span class="pill-label">Penalidades</span><span class="pill-val">-{pen_total:,.0f}</span><span class="pill-badge" style="background:#E3494820;color:#E34948;">Ocorrências</span></div>
    <div class="pill atencao"><span class="pill-label">Sem Membro</span><span class="pill-val">{n_sem_mb}</span><span class="pill-badge" style="background:#EDA10020;color:#EDA100;">Revisar</span></div>
  </div>

  <div class="bloco-barras" id="tv-bb">
    <div class="barra-box verde-border">
      <div class="bloco-titulo verde" style="margin-bottom:5px;">📋 Meta Coletiva</div>
      <div class="barra-item"><div class="barra-header"><span>Pontuação do mês</span><span style="color:{_cor_tv_eq};font-weight:700;">{fp(pct_eq)}</span></div><div class="barra-track"><div class="barra-fill" style="width:{min(pct_eq,100):.1f}%;background:{_cor_tv_eq};"></div></div><div class="barra-desc">{saldo_eq:,.0f} / {meta_eq:,} pts (inclui -{pen_total:.0f} penalidades)</div></div>
      <div class="barra-item"><div class="barra-header"><span>Sem atraso em prioritários P8-P10</span><span style="color:{_cor_tv_pri};font-weight:700;">{pct_pri_ok:.0f}%</span></div><div class="barra-track"><div class="barra-fill" style="width:{min(pct_pri_ok,100):.1f}%;background:{_cor_tv_pri};"></div></div><div class="barra-desc">{desc_pri}</div></div>
      <div class="barra-item"><div class="barra-header"><span>Retrabalho abaixo de {max_retrab_n}%</span><span style="color:{_cor_tv_retrab_n};font-weight:700;">{pct_retrab_n:.0f}%</span></div><div class="barra-track"><div class="barra-fill" style="width:{min(pct_retrab_n,100):.1f}%;background:{_cor_tv_retrab_n};"></div></div><div class="barra-desc">{desc_retrab}</div></div>
      <div class="barra-item"><div class="barra-header"><span>Menos de {max_pen_n+1} penalidades</span><span style="color:#E34948;font-weight:700;">{pct_pen_n:.0f}%</span></div><div class="barra-track"><div class="barra-fill" style="width:{min(pct_pen_n,100):.1f}%;background:#E34948;"></div></div><div class="barra-desc">{n_pen} ocorrência(s) / máx {max_pen_n}</div></div>
      <div class="barra-item"><div class="barra-header"><span>Cartões com membro atribuído</span><span style="color:{_cor_tv_cmb};font-weight:700;">{pct_com_membro:.0f}%</span></div><div class="barra-track"><div class="barra-fill" style="width:{min(pct_com_membro,100):.1f}%;background:{_cor_tv_cmb};"></div></div><div class="barra-desc">{_tv_sem_mb_desc}</div></div>
    </div>
    <div class="barra-box ouro-border">
      <div class="bloco-titulo ouro" style="margin-bottom:5px;">⭐ Meta Maxx Coletiva</div>
      <div class="barra-item"><div class="barra-header"><span>Pontuação +{maxx_pct-100}% acima da meta</span><span style="color:{_cor_tv_maxx};font-weight:700;">{fp(pct_maxx)}</span></div><div class="barra-track"><div class="barra-fill" style="width:{min(pct_maxx,100):.1f}%;background:{_cor_tv_maxx};"></div></div><div class="barra-desc">{saldo_eq:,.0f} / {meta_maxx_pts:,.0f} pts (c/ penalidades -{pen_total:.0f})</div></div>
      <div class="barra-item"><div class="barra-header"><span>Zero prioritários em atraso</span><span style="color:{_cor_tv_prix};font-weight:700;">{pct_pri_ok:.0f}%</span></div><div class="barra-track"><div class="barra-fill" style="width:{min(pct_pri_ok,100):.1f}%;background:{_cor_tv_prix};"></div></div><div class="barra-desc">{desc_pri}</div></div>
      <div class="barra-item"><div class="barra-header"><span>Retrabalho abaixo de {max_retrab_x}%</span><span style="color:{_cor_tv_retrab_x};font-weight:700;">{pct_retrab_x:.0f}%</span></div><div class="barra-track"><div class="barra-fill" style="width:{min(pct_retrab_x,100):.1f}%;background:{_cor_tv_retrab_x};"></div></div><div class="barra-desc">{desc_retrab}</div></div>
      <div class="barra-item"><div class="barra-header"><span>Menos de {max_pen_x+1} penalidades</span><span style="color:#E34948;font-weight:700;">{pct_pen_x:.0f}%</span></div><div class="barra-track"><div class="barra-fill" style="width:{min(pct_pen_x,100):.1f}%;background:#E34948;"></div></div><div class="barra-desc">{n_pen} ocorrência(s) / máx {max_pen_x}</div></div>
      <div class="barra-item"><div class="barra-header"><span>Cartões com membro atribuído</span><span style="color:{_cor_tv_cmbx};font-weight:700;">{pct_com_membro:.0f}%</span></div><div class="barra-track"><div class="barra-fill" style="width:{min(pct_com_membro,100):.1f}%;background:{_cor_tv_cmbx};"></div></div><div class="barra-desc">{_tv_sem_mb_desc}</div></div>
    </div>
  </div>

  <div class="bloco-bottom" id="tv-bbt">
    <div class="sub-bloco-pend">
      <div class="sub-titulo" style="color:#EDA100;">🟠 Pendentes por Coluna</div>
      {pend_html}
    </div>
    <div class="sub-bloco-and">
      <div class="sub-titulo">▶️ Em Andamento</div>
      <div class="cards-col">{and_html}</div>
    </div>
    <div class="sub-bloco-fila">
      <div class="sub-titulo">📋 Próximas na Fila</div>
      <div class="cards-col">{fila_html}</div>
    </div>
    <div class="sub-bloco-alerta">
      <div class="sub-titulo" style="color:#E34948;">🔔 Alertas</div>
      <div class="alerta-col">
        <div class="alerta-header {alerta_cls}" id="alerta-header">
          <div class="alerta-titulo" style="color:{alerta_titulo_cor};">{alerta_titulo_txt}</div>
          <div class="alerta-sub">{alerta_sub_html}</div>
        </div>
        <div class="alerta-lista" id="alerta-lista"></div>
      </div>
    </div>
  </div>
</div>

<audio id="beep-audio" src="/app/static/beep.wav" preload="auto"></audio>
<div id="som-btn" onclick="ativarSom();">🔊 Ativar Som</div>

<script>
// ── Layout: calcula alturas reais em px a partir de window.innerHeight ──────
function _aplicarLayout() {{
  var H = window.innerHeight || 1080;
  var GAP = 3, PAD = 5;
  var avail = H - PAD * 2 - GAP * 3;
  var hM  = Math.round(avail * 0.20);
  var hS  = Math.round(avail * 0.09);
  var hB  = Math.round(avail * 0.22);
  var hBt = avail - hM - hS - hB;
  var y = PAD;
  function fix(id, top, h) {{
    var e = document.getElementById(id);
    if (e) {{ e.style.top = top + 'px'; e.style.height = h + 'px'; }}
  }}
  fix('tv-bm',  y, hM);  y += hM  + GAP;
  fix('tv-bs',  y, hS);  y += hS  + GAP;
  fix('tv-bb',  y, hB);  y += hB  + GAP;
  fix('tv-bbt', y, hBt);
}}
_aplicarLayout();
// ── Alertas: máx 4 visíveis; rotação automática quando há mais de 4 ──────────
var ALERTAS = {alertas_js};
var _alertaOffset = 0;
function _renderAlertas() {{
  var lista = document.getElementById("alerta-lista");
  if (!lista) return;
  lista.innerHTML = "";
  var total = ALERTAS.length;
  if (!total) return;
  var visiveis = total > 3 ? 3 : total;
  for (var i = 0; i < visiveis; i++) {{
    var idx = (i + _alertaOffset) % total;
    var a = ALERTAS[idx];
    var div = document.createElement("div");
    div.className = "alerta-item " + a.tipo;
    div.innerHTML =
      '<div class="alerta-item-prioridade">' +
        '<span>' + a.prioridade + ' — ' + a.pos + '</span>' +
        '<span style="color:#555;font-weight:400;">' + (idx+1) + '/' + total + '</span>' +
      '</div>' +
      '<div class="alerta-item-nome">' + a.nome + '</div>' +
      '<div class="alerta-item-col">' + a.col + '</div>' +
      '<div class="alerta-item-col" style="color:#666;font-style:italic;">' + a.detalhe + '</div>';
    lista.appendChild(div);
  }}
}}
_renderAlertas();
if (ALERTAS.length > 3) {{
  setInterval(function() {{
    _alertaOffset = (_alertaOffset + 1) % ALERTAS.length;
    _renderAlertas();
  }}, 12000);
}}
// ── Áudio via Web Audio API (sem arquivo externo, compatível com WebOS) ────────
var _audioCtx = null;
var _audioAtivo = false;
function _ensureCtx() {{
  if (!_audioCtx) {{
    try {{
      _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }} catch(e) {{ _audioCtx = null; }}
  }}
  return _audioCtx;
}}
function _marcarBtnAtivo() {{
  var btn = document.getElementById('som-btn');
  if (btn) {{ btn.className = 'ativo'; btn.innerHTML = '🔊 Som Ativo'; }}
}}
function _marcarBtnErro() {{
  var btn = document.getElementById('som-btn');
  if (btn) {{ btn.style.color = '#E34948'; btn.innerHTML = '🔇 Sem suporte'; }}
}}
function _beepOsc(freq, dur) {{
  var ctx = _ensureCtx();
  if (!ctx) return;
  function _doBeep() {{
    try {{
      var osc = ctx.createOscillator();
      var gain = ctx.createGain();
      osc.connect(gain); gain.connect(ctx.destination);
      osc.frequency.value = freq || 880;
      gain.gain.setValueAtTime(0.35, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + (dur || 0.4));
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + (dur || 0.4));
    }} catch(e) {{}}
  }}
  try {{
    if (ctx.state === 'suspended') {{
      ctx.resume().then(_doBeep).catch(function() {{}});
    }} else {{
      _doBeep();
    }}
  }} catch(e) {{ _doBeep(); }}
}}
// O navegador da TV (WebOS) nao implementa Web Audio API — o ctx.resume()
// era rejeitado e o botao virava "Sem suporte". Mas ele toca <audio> sem
// problema, e o beep.wav ja estava na pagina, so nao era usado.
var _beepEl = null;
function _ensureBeepEl() {{
  if (!_beepEl) _beepEl = document.getElementById('beep-audio');
  return _beepEl;
}}
function _tocarWav() {{
  var el = _ensureBeepEl();
  if (!el) return Promise.reject('sem elemento de audio');
  try {{
    el.currentTime = 0;
    var p = el.play();
    return (p && p.then) ? p : Promise.resolve();
  }} catch(e) {{ return Promise.reject(e); }}
}}
function _playAudio() {{
  if (!_audioAtivo) return;
  _tocarWav().catch(function() {{
    // Reserva: navegadores sem <audio> utilizavel, mas com Web Audio.
    _beepOsc(880, 0.35);
    setTimeout(function() {{ _beepOsc(660, 0.25); }}, 450);
  }});
}}
function _confirmarAtivo() {{
  _audioAtivo = true;
  _marcarBtnAtivo();
  try {{ localStorage.setItem('ms_tv_audio', '1'); }} catch(e) {{}}
}}
function ativarSom() {{
  var btn = document.getElementById('som-btn');
  if (btn) {{ btn.innerHTML = '⏳ Ativando...'; }}
  _tocarWav().then(_confirmarAtivo).catch(function() {{
    // So agora tenta Web Audio — e so marca "Sem suporte" se os dois falharem.
    var ctx = _ensureCtx();
    if (!ctx) {{ _marcarBtnErro(); return; }}
    try {{
      ctx.resume().then(function() {{
        _beepOsc(880, 0.15);
        _confirmarAtivo();
      }}).catch(function() {{ _marcarBtnErro(); }});
    }} catch(e) {{ _marcarBtnErro(); }}
  }});
}}
// A pagina recarrega sozinha e o navegador volta a bloquear o audio. Antes o
// codigo remarcava o botao como "Som Ativo" so porque havia registro de um
// clique antigo — a TV ficava muda anunciando que estava tocando. Agora ele
// confere de verdade: toca mudo e so se declara ativo se o navegador deixar.
try {{
  if (localStorage.getItem('ms_tv_audio') === '1') {{
    var _el = _ensureBeepEl();
    var _vol = _el ? _el.volume : 1;
    if (_el) _el.volume = 0;
    _tocarWav().then(function() {{
      if (_el) {{ _el.pause(); _el.currentTime = 0; _el.volume = _vol; }}
      _audioAtivo = true; _marcarBtnAtivo();
    }}).catch(function() {{
      if (_el) _el.volume = _vol;
      var b = document.getElementById('som-btn');
      if (b) {{ b.className = ''; b.innerHTML = '🔇 Toque para ativar'; }}
    }});
  }}
}} catch(e) {{}}
// checkAndPlay: só dispara quando há alertas (ALERTAS não vazio)
function checkAndPlay() {{
  if (!ALERTAS.length) return;
  var h = document.getElementById("alerta-header");
  if (!h) return;
  h.classList.add("tocando");
  _playAudio();
  setTimeout(_playAudio, 3500);
  setTimeout(_playAudio, 7000);
  setTimeout(function() {{ h.classList.remove("tocando"); }}, 11000);
}}
// Carimbo: fica vermelho se o painel passou de 5 min sem ser regenerado.
// Assim um congelamento vira algo visivel na tela, nao uma surpresa silenciosa.
(function() {{
  // O elemento e reprocurado a cada volta de proposito: a atualizacao sem
  // recarregar troca o innerHTML de .tv-root, e a referencia guardada aqui
  // ficava apontando para o carimbo antigo, ja fora da pagina — o aviso era
  // escrito num no invisivel. Relendo o data-gerado a cada checagem, o
  // carimbo passa a refletir o arquivo que esta na tela agora.
  function checar() {{
    var el = document.getElementById('tv-carimbo');
    if (!el) return;
    var g = el.getAttribute('data-gerado') || '';
    var m = g.match(/(\\d{{2}})\\/(\\d{{2}})\\/(\\d{{4}}) (\\d{{2}}):(\\d{{2}})/);
    if (!m) return;
    var gerado = new Date(+m[3], +m[2] - 1, +m[1], +m[4], +m[5]);
    var min = (Date.now() - gerado.getTime()) / 60000;
    if (min > 5) {{
      el.className = 'velho';
      el.textContent = 'DESATUALIZADO — ultima atualizacao ' + g;
    }}
  }}
  checar();
  setInterval(checar, 30000);
}})();
// ── Atualizacao sem recarregar a pagina ──────────────────────────────────────
// Recarregar a pagina inteira apagava a liberacao de audio do navegador: quem
// clicasse em "Ativar Som" na TV perdia o som em menos de um minuto e nunca
// mais ouvia alerta. Agora so o conteudo e trocado; a pagina, o <audio> e a
// liberacao continuam vivos.
//
// Se qualquer coisa falhar na troca, cai no recarregamento de antes — pior caso
// e voltar ao comportamento atual, nunca uma TV congelada.
function _atualizarPainel() {{
  // Cada volta usa uma URL nova. Sem isso o navegador revalida com
  // If-None-Match e o servidor estatico responde 304 com o ETag velho — o
  // conteudo novo nunca chega, por mais que o arquivo mude no disco.
  var _u = new URL(location.href);
  _u.searchParams.set('ts', Date.now());   // 'v' nao: o Tornado da 10 anos de cache
  fetch(_u.toString(), {{cache: 'no-store'}})
    .then(function(r) {{ if (!r.ok) throw new Error(r.status); return r.text(); }})
    .then(function(html) {{
      var sv = html.match(/var SCRIPT_VER = "([^"]+)";/);
      if (sv && sv[1] !== SCRIPT_VER) {{
        try {{
          if (sessionStorage.getItem('tv_ver') !== sv[1]) {{
            sessionStorage.setItem('tv_ver', sv[1]);
            location.reload();
            return;
          }}
        }} catch (e) {{ location.reload(); return; }}
      }}
      var doc = new DOMParser().parseFromString(html, 'text/html');
      var novo = doc.querySelector('.tv-root');
      var atual = document.querySelector('.tv-root');
      if (!novo || !atual) throw new Error('sem .tv-root');
      atual.innerHTML = novo.innerHTML;

      // Os alertas vivem numa variavel do script, nao no HTML trocado.
      var m = html.match(/var ALERTAS = (\[[\s\S]*?\]);/);
      if (m) {{
        try {{ ALERTAS = JSON.parse(m[1]); _alertaOffset = 0; }} catch(e) {{}}
      }}

      // O carimbo de frescor tambem vive numa variavel do script, e o script
      // do HTML buscado nunca e executado — so o miolo da pagina e trocado.
      // Sem reler GERADO_EM aqui, ele ficava parado na hora em que a TV foi
      // ligada, e a faixa "DADOS DESATUALIZADOS" acendia sozinha 6 min depois
      // mesmo com o painel se atualizando certinho a cada minuto. Agora a
      // faixa so acende quando o servidor de fato parou de reescrever.
      var gm = html.match(/var GERADO_EM = (\d+);/);
      if (gm) {{ GERADO_EM = parseInt(gm[1], 10) || GERADO_EM; }}
      _checarFrescor();
      _aplicarLayout();
      _renderAlertas();
      _autoEscala();
      checkAndPlay();
      setTimeout(_atualizarPainel, 60000);
    }})
    .catch(function() {{ location.reload(); }});
}}
setTimeout(_atualizarPainel, 60000);
setTimeout(checkAndPlay, 4000);

// A TV avisa quando ela mesma congela.
//
// O arquivo servido a TV so muda quando o servidor o reescreve. Se a
// regeneracao parar, a TV segue mostrando numeros plausiveis e velhos — e
// ninguem percebe, que e o pior jeito de falhar. GERADO_EM e carimbado no
// HTML a cada regeneracao; se ficar velho, a faixa aparece.
var GERADO_EM = {gerado_epoch};
// Versao do proprio script. A atualizacao sem recarregar troca so o miolo da
// pagina, entao o script que roda na TV e o do dia em que ela foi ligada:
// qualquer correcao daqui de dentro so chegava se alguem fosse ate a TV e
// recarregasse na mao. Quando a versao servida muda, a pagina se recarrega uma
// unica vez — o sessionStorage e o que impede virar laco se algum cache
// intermediario insistir na versao velha.
var SCRIPT_VER = "{_TV_SCRIPT_VER}";
function _checarFrescor() {{
  try {{
    var idadeMin = (Date.now() / 1000 - GERADO_EM) / 60;
    var faixa = document.getElementById('tv-congelada');
    if (!faixa) {{
      faixa = document.createElement('div');
      faixa.id = 'tv-congelada';
      faixa.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:99999;'
        + 'background:#E34948;color:#fff;font-weight:800;text-align:center;'
        + 'padding:10px;font-size:22px;display:none;';
      document.body.appendChild(faixa);
    }}
    if (idadeMin > 6) {{
      faixa.textContent = 'DADOS DESATUALIZADOS — parados ha '
        + Math.round(idadeMin) + ' min. Avise o gestor.';
      faixa.style.display = 'block';
    }} else {{
      faixa.style.display = 'none';
    }}
  }} catch (e) {{}}
}}
_checarFrescor();
setInterval(_checarFrescor, 60000);
setInterval(checkAndPlay, 5 * 60 * 1000);
// Auto-scale se conteúdo não couber na tela
function _autoEscala() {{
  try {{
    var root = document.querySelector('.tv-root');
    root.style.transform = ''; root.style.webkitTransform = ''; root.style.width = '';
    var sh = root.scrollHeight;
    var vh = window.innerHeight || document.documentElement.clientHeight;
    if (sh > vh) {{
      var scale = vh / sh;
      root.style.webkitTransform = 'scale(' + scale + ')';
      root.style.transform = 'scale(' + scale + ')';
      root.style.webkitTransformOrigin = 'top left';
      root.style.transformOrigin = 'top left';
      root.style.width = Math.round(100 / scale) + '%';
    }}
  }} catch(e) {{}}
}}
_autoEscala();
</script>
</body>
</html>"""

# Muda quando o codigo da TV muda, e so entao. Nao serve hash do HTML pronto: o
# carimbo de geracao entra nele, o valor mudaria a cada minuto e a TV entraria
# num laco de recarregamento.
try:
    import hashlib as _hl_tv, inspect as _insp_tv
    _TV_SCRIPT_VER = _hl_tv.md5(
        _insp_tv.getsource(_tv_full_html).encode("utf-8")).hexdigest()[:8]
except Exception:
    _TV_SCRIPT_VER = "estatico"


def _meta_ind_item(titulo, pct, descricao, cor=None, aguardando=False):
    if aguardando:
        return f"""<div class="meta-ind-card">
  <div class="meta-ind-titulo">{titulo}</div>
  <div style="font-size:10px;color:var(--ms-texto-sec);font-style:italic;">⏳ Aguardando integração do relógio de ponto</div>
</div>"""
    c=cor or ("#1BAF7A" if pct>=80 else ("#EDA100" if pct>=50 else "#4A90D9"))
    return f"""<div class="meta-ind-card">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
    <div class="meta-ind-titulo" style="margin:0;">{titulo}</div>
    <div style="font-size:16px;font-weight:700;color:{c};">{pct:.0f}%</div>
  </div>
  <div class="meta-ind-barra-bg">
    <div style="background:{c};width:{min(pct,100):.1f}%;height:100%;border-radius:4px;"></div>
  </div>
  <div style="font-size:9px;color:var(--ms-texto-sec);margin-top:3px;">{descricao}</div>
</div>"""

# ── PÁGINA ─────────────────────────────────────────────────────────────────────
def pagina_placar(usuario_logado, headless=False):
    """Renderiza o Painel de Metas.

    headless=True: chamado pela thread que mantém o painel da TV vivo. Nesse
    modo não há sessão Streamlit — as chamadas de UI viram no-op e a função
    serve apenas para recalcular e reescrever o static/tv.html.
    """
    eh_master=usuario_logado.lower() in {m.lower() for m in MASTERS}
    eh_membro=usuario_logado in MEMBROS_ATIVOS
    if not TRELLO_KEY:
        # Sair daqui nao levanta excecao, entao a thread da TV contabilizava a
        # volta como sucesso e o arquivo nunca era reescrito. O motivo fica
        # registrado para o diagnostico nao mentir.
        if headless:
            TV_STATUS["motivo"] = "credenciais do Trello não configuradas"
        st.error("Credenciais do Trello não configuradas."); return

    st.markdown(CSS,unsafe_allow_html=True)
    agora=datetime.now()
    params=st.query_params
    modo_tv = headless or (bool(_TV_TOKEN) and params.get("tv","") == _TV_TOKEN)

    # ── Cabeçalho / controles ────────────────────────────────────────────────
    if modo_tv:
        # TV: sem seletor de mês, sem botão, mês atual fixo
        filtro_mes = (agora.year, agora.month)
        sel        = f"{MESES_PT[agora.month]} {agora.year}"
        st.markdown(
            f'<div style="font-size:10px;color:var(--ms-texto-sec);'
            f'text-align:right;padding:2px 8px 6px;">'
            f'📺 {sel} · atualiza a cada 60s · {agora.strftime("%d/%m/%Y %H:%M")}</div>',
            unsafe_allow_html=True
        )
    else:
        col_tit,col_mes,col_att=st.columns([3,2,1])
        with col_tit: st.markdown("### 🏆 Painel de Meta")
        with col_mes:
            meses=[(agora.year,agora.month)]
            m,a=agora.month,agora.year
            for _ in range(5):
                m-=1
                if m==0: m=12; a-=1
                meses.append((a,m))
            labels=[f"{MESES_PT[mm]} {aa}" for aa,mm in meses]
            sel=st.selectbox("Mês",labels,index=0,key="placar_mes",label_visibility="collapsed")
            filtro_mes=meses[labels.index(sel)]
        with col_att:
            if st.button("🔄",use_container_width=True,help="Atualizar"):
                _buscar_board.clear(); st.rerun()
        st.caption(f"Exibindo: {sel} · {agora.strftime('%d/%m/%Y %H:%M')} · use 🔄 para atualizar")

    # ── Carrega configuração persistida (ou usa defaults) ──────────────────────
    try:
        import metas_config as _mc
        cfg_mes = _mc.carregar_config(filtro_mes[0], filtro_mes[1])
    except Exception:
        cfg_mes = {
            "meta_equipe": 5000, "meta_maxx_pct": 110,
            "meta_myrelladesouza": 1500, "meta_beatriz51": 1500,
            "meta_gabriel_borges": 1500,
            "max_pen_normal": 4, "max_pen_maxx": 1,
            "max_tol_normal": 15, "max_tol_maxx": 7,
            "max_atr_normal": 10, "max_atr_maxx": 5,
        }

    # Chaves de sessão por mês (para sobrescritas rápidas no expander)
    k_eq  = f"meta_eq_{filtro_mes[0]}_{filtro_mes[1]}"
    k_mx  = f"meta_maxx_{filtro_mes[0]}_{filtro_mes[1]}"
    k_myr = f"meta_myr_{filtro_mes[0]}_{filtro_mes[1]}"
    k_bea = f"meta_bea_{filtro_mes[0]}_{filtro_mes[1]}"
    k_gab = f"meta_gab_{filtro_mes[0]}_{filtro_mes[1]}"

    _semear_meta(k_eq,  cfg_mes["meta_equipe"])
    _semear_meta(k_mx,  cfg_mes["meta_maxx_pct"])
    _semear_meta(k_myr, cfg_mes["meta_myrelladesouza"])
    _semear_meta(k_bea, cfg_mes["meta_beatriz51"])
    _semear_meta(k_gab, cfg_mes["meta_gabriel_borges"])

    # Configuração de metas foi movida para a aba "📊 Análise de Metas"
    # _meta_sessao cai na configuração quando não há sessão (thread da TV).
    meta_eq   = _meta_sessao(k_eq, cfg_mes["meta_equipe"])
    maxx_pct  = _meta_sessao(k_mx, cfg_mes["meta_maxx_pct"])
    meta_maxx_pts = meta_eq * maxx_pct / 100
    # Meta individual por colaborador
    meta_ind_map = {
        "myrelladesouza": _meta_sessao(k_myr, cfg_mes["meta_myrelladesouza"]),
        "beatriz51":      _meta_sessao(k_bea, cfg_mes["meta_beatriz51"]),
        "gabriel_borges": _meta_sessao(k_gab, cfg_mes["meta_gabriel_borges"]),
    }
    # Compatibilidade: meta_ind = média para barras genéricas
    meta_ind = sum(meta_ind_map.values()) // max(len(meta_ind_map), 1)

    with st.spinner(""):
        dados=_buscar_board()
    if not dados or not dados[0]:
        if headless:
            TV_STATUS["motivo"] = "o Trello não respondeu nesta volta"
        st.error("Não foi possível conectar ao Trello."); return

    listas,cards,membros_map,id_p,id_t,id_i=dados
    d=_processar(listas,cards,membros_map,id_p,id_t,id_i,filtro_mes)
    fila=_calcular_fila(listas,cards,membros_map)

    # ── ALERTA: cartões em andamento ou concluídos sem membro ─────────────────
    _and_sem_mb = [
        {"card": c["card"], "lista": c["lista"], "tipo": "em andamento"}
        for c in d["andamento_lista"] if not c["membros"]
    ]
    _concl_sem_mb = [
        {**c, "tipo": "concluído"} for c in d.get("concluido_sem_membro", [])
    ]
    _alertas_sem_mb = _and_sem_mb + _concl_sem_mb

    if _alertas_sem_mb:
        _itens = "".join(
            f'<div style="display:flex;align-items:center;gap:8px;padding:4px 0;'
            f'border-bottom:1px solid #E3494830;">'
            f'<span style="font-size:10px;font-weight:600;color:#E34948;min-width:80px;">'
            f'{"⏳ em andamento" if a["tipo"]=="em andamento" else "✅ concluído"}</span>'
            f'<span style="font-size:10px;color:var(--ms-texto);flex:1;">{a["card"][:55]}</span>'
            f'<span style="font-size:9px;color:var(--ms-texto-sec);">{a["lista"][:30]}</span>'
            f'</div>'
            for a in _alertas_sem_mb
        )
        st.markdown(
            f'<div style="background:#E3494815;border:2px solid #E34948;border-radius:8px;'
            f'padding:10px 14px;margin-bottom:12px;">'
            f'<div style="font-size:11px;font-weight:700;color:#E34948;margin-bottom:8px;">'
            f'🚨 {len(_alertas_sem_mb)} cartão(ões) sem membro atribuído — '
            f'atribua o responsável antes de continuar!</div>'
            f'{_itens}</div>',
            unsafe_allow_html=True
        )

    saldo_eq=d["pts_equipe"]-d["pen_total"]
    pct_eq=(saldo_eq/meta_eq*100) if meta_eq>0 else 0
    pct_maxx=(saldo_eq/meta_maxx_pts*100) if meta_maxx_pts>0 else 0
    faltam=max(meta_eq-saldo_eq,0)
    faltam_maxx=max(meta_maxx_pts-saldo_eq,0)
    cor_pts="#1BAF7A" if pct_eq>=100 else ("#EDA100" if pct_eq>=50 else "#4A90D9")

    # ══ BLOCO 1 — cards meta | vel meta | vel maxx | cards maxx ══
    col_cm, col_vm, col_vx, col_cx = st.columns([1.8, 2.0, 2.0, 1.8])

    with col_cm:
        faltam_cor="#EDA100" if faltam>0 else "#1BAF7A"
        faltam_maxx_cor="#FFD700" if faltam_maxx==0 else "#EDA100"
        atual_maxx_cor="#FFD700" if pct_maxx>=100 else "#EDA100"
        st.markdown(f"""<div style="font-size:9px;font-weight:600;color:#1BAF7A;text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px;">🏆 Meta Mensal</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;">
  <div style="background:#0d2e1f;border:1px solid #1BAF7A;border-radius:6px;padding:6px 8px;">
    <div style="font-size:7px;color:#1BAF7A;text-transform:uppercase;">Meta</div>
    <div style="font-size:13px;font-weight:700;color:#e0f5ec;">{meta_eq:,}</div>
    <div style="font-size:7px;color:#1BAF7A;">pts/mês</div>
  </div>
  <div style="background:#2a1e05;border:1px solid #EDA100;border-radius:6px;padding:6px 8px;">
    <div style="font-size:7px;color:#EDA100;text-transform:uppercase;">Atual</div>
    <div style="font-size:13px;font-weight:700;color:#fae8b0;">{saldo_eq:,.0f}</div>
    <div style="font-size:7px;color:#EDA100;">{"%.1f" % pct_eq if pct_eq < 10 else "%.0f" % pct_eq}% meta</div>
  </div>
  <div style="background:#2a1e05;border:1px solid #EDA100;border-radius:6px;padding:6px 8px;">
    <div style="font-size:7px;color:#EDA100;text-transform:uppercase;">Faltam</div>
    <div style="font-size:13px;font-weight:700;color:#fae8b0;">{faltam:,.0f}</div>
    <div style="font-size:7px;color:#EDA100;">pts</div>
  </div>
  <div style="background:#2a1e05;border:1px solid #EDA100;border-radius:6px;padding:6px 8px;">
    <div style="font-size:7px;color:#EDA100;text-transform:uppercase;">Em Aberto</div>
    <div style="font-size:13px;font-weight:700;color:#fae8b0;">{d["pts_pendentes"]:,.0f}</div>
    <div style="font-size:7px;color:#EDA100;">pendentes</div>
  </div>
</div>""", unsafe_allow_html=True)
        # ── Ritmo de desempenho por dias úteis ──
        import calendar as _cal
        _hoje = datetime.now().date()
        if filtro_mes[0] == _hoje.year and filtro_mes[1] == _hoje.month:
            _feriados_br = {(1,1),(4,21),(5,1),(9,7),(10,12),(11,2),(11,15),(12,25)}
            _, _n_dias = _cal.monthrange(filtro_mes[0], filtro_mes[1])
            _total_uteis = sum(
                1 for _d in range(1, _n_dias+1)
                if datetime(filtro_mes[0], filtro_mes[1], _d).weekday() < 5
                and (filtro_mes[1], _d) not in _feriados_br
            )
            _uteis_dec = sum(
                1 for _d in range(1, _hoje.day+1)
                if datetime(filtro_mes[0], filtro_mes[1], _d).weekday() < 5
                and (filtro_mes[1], _d) not in _feriados_br
            )
            if _total_uteis > 0 and _uteis_dec > 0:
                _meta_diaria = meta_eq / _total_uteis
                _pts_esp = _meta_diaria * _uteis_dec
                _diff_pct = (saldo_eq - _pts_esp) / _pts_esp * 100 if _pts_esp > 0 else 0
                _proj = saldo_eq / _uteis_dec * _total_uteis
                if _diff_pct > 10:
                    _r_icon, _r_cor = "📈", "#1BAF7A"
                    _r_txt = f"Desempenho {_diff_pct:.0f}% acima do estimado para o período"
                    _r_extra = f"+{saldo_eq-_pts_esp:.0f} pts a mais que o esperado ({_pts_esp:.0f} pts em {_uteis_dec} dias úteis)"
                elif _diff_pct < -10:
                    _r_icon, _r_cor = "📉", "#E34948"
                    _r_txt = f"Desempenho {abs(_diff_pct):.0f}% abaixo do estimado para o período"
                    _r_extra = f"{saldo_eq-_pts_esp:.0f} pts abaixo do esperado ({_pts_esp:.0f} pts em {_uteis_dec} dias úteis)"
                else:
                    _r_icon, _r_cor = "📊", "#EDA100"
                    _r_txt = "Desempenho dentro do ritmo esperado para o período"
                    _r_extra = f"Realizados {saldo_eq:.0f} pts · esperado {_pts_esp:.0f} pts em {_uteis_dec} dias úteis"
                _ritmo_html = f"""<div style="background:#1a1a1a;border:1px solid {_r_cor}44;border-radius:6px;padding:8px 10px;margin-top:8px;">
  <div style="font-size:11px;font-weight:700;color:{_r_cor};margin-bottom:3px;">{_r_icon} {_r_txt}</div>
  <div style="font-size:9px;color:#ccc;line-height:1.5;">{_r_extra}<br>Nesse ritmo: projeção de <strong style="color:{_r_cor};">{_proj:.0f} pts</strong> ao final do mês</div>
</div>"""
            else:
                _ritmo_html = ""
        else:
            _ritmo_html = ""
        if _ritmo_html:
            st.markdown(_ritmo_html, unsafe_allow_html=True)

    with col_vm:
        st.markdown(_vel_meta(pct_eq, meta_eq, saldo_eq, faltam), unsafe_allow_html=True)

    with col_vx:
        st.markdown(_vel_maxx(pct_maxx, meta_maxx_pts, saldo_eq), unsafe_allow_html=True)

    with col_cx:
        cor_pen_maxx_card="#E34948" if d["pen_total"]>0 else "#FFD700"
        st.markdown(f"""<div style="font-size:9px;font-weight:600;color:#FFD700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px;">⭐ Meta Maxx</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;">
  <div style="background:#2a2000;border:1px solid #FFD700;border-radius:6px;padding:6px 8px;">
    <div style="font-size:7px;color:#FFD700;text-transform:uppercase;">Maxx</div>
    <div style="font-size:13px;font-weight:700;color:#fff5cc;">{meta_maxx_pts:,.0f}</div>
    <div style="font-size:7px;color:#FFD700;">+{maxx_pct-100}% da meta</div>
  </div>
  <div style="background:#2a1e05;border:1px solid #EDA100;border-radius:6px;padding:6px 8px;">
    <div style="font-size:7px;color:#EDA100;text-transform:uppercase;">Saldo (c/ pen.)</div>
    <div style="font-size:13px;font-weight:700;color:#fae8b0;">{saldo_eq:,.0f}</div>
    <div style="font-size:7px;color:#EDA100;">{"%.1f" % pct_maxx if pct_maxx < 10 else "%.0f" % pct_maxx}% Maxx</div>
  </div>
  <div style="background:#2a1e05;border:1px solid #EDA100;border-radius:6px;padding:6px 8px;">
    <div style="font-size:7px;color:#EDA100;text-transform:uppercase;">Faltam</div>
    <div style="font-size:13px;font-weight:700;color:#fae8b0;">{faltam_maxx:,.0f}</div>
    <div style="font-size:7px;color:#EDA100;">p/ bônus</div>
  </div>
  <div style="background:#2a1500;border:1px solid {cor_pen_maxx_card};border-radius:6px;padding:6px 8px;">
    <div style="font-size:7px;color:{cor_pen_maxx_card};text-transform:uppercase;">Penalidades</div>
    <div style="font-size:13px;font-weight:700;color:#fae8b0;">-{d["pen_total"]:,.0f}</div>
    <div style="font-size:7px;color:{cor_pen_maxx_card};">{len(d["pen_cards"])} ocorrências</div>
  </div>
</div>""", unsafe_allow_html=True)

    # ══ BLOCO 2 — STATUS ══
    st.markdown('<hr style="border:none;border-top:1px solid var(--ms-divisor);margin:10px 0 8px 0;"/>',unsafe_allow_html=True)
    status_items=[
        ("Cartões Pendentes",sum(d["pend_lista"].values()),"Pendente","var(--ms-texto)","#EDA10030","#EDA100"),
        ("Pts Pendentes",f"{d['pts_pendentes']:.0f}","Aberto","#EDA100","#EDA10020","#EDA100"),
        ("Em Andamento",d["em_andamento"],"Ativo","var(--ms-texto)","#1BAF7A20","#1BAF7A"),
        ("Atrasados",d["atrasados"],"Atenção","var(--ms-texto)","#E3494820","#E34948"),
        ("Desativar",d["desativar"],"Prioritário","var(--ms-texto)","#E3494820","#E34948"),
        ("Reativar",d["reativar"],"Normal","var(--ms-texto)","#33333340","#888"),
        ("Urgentes",d["urgentes"],"Crítico","#E34948","#E3494830","#E34948"),
        ("Falta Info",d["falta_info"],"Pendente","#EDA100","#EDA10020","#EDA100"),
        ("Falta Pontuação",d["falta_pts"],"Revisar","#EDA100","#EDA10020","#EDA100"),
        ("Penalidades",f"-{d['pen_total']:.0f}","Ocorrências","#E34948","#E3494820","#E34948"),
        ("Sem Membro",d["sem_membro"],"Revisar","#EDA100","#EDA10020","#EDA100"),
    ]
    cols_st=st.columns(11)
    for i,(lbl,val,badge,cn,bb,bt) in enumerate(status_items):
        with cols_st[i]: st.markdown(_sc(lbl,val,badge,cn,bb,bt),unsafe_allow_html=True)

    # ══ BLOCO METAS — ponta a ponta ══
    st.markdown('<hr style="border:none;border-top:1px solid var(--ms-divisor);margin:10px 0 8px 0;"/>',unsafe_allow_html=True)
    col_meta_n, col_meta_x = st.columns(2)

    # Cálculos para as barras
    # Percentual e legenda saem do mesmo numero. Antes a legenda era o texto
    # fixo "Nenhum cartao prioritario atrasado", entao a barra podia marcar 0%
    # jurando que nao havia atraso nenhum.
    _atr_pri = d.get("atrasados_pri", 0)
    pct_prioritarios_ok = 100 if _atr_pri == 0 else max(0, 100 - _atr_pri * 20)
    if _atr_pri == 0:
        _desc_pri = "Nenhum cartão prioritário (P8-P10) atrasado"
    else:
        _nomes_pri = ", ".join(f'"{c["nome"][:30]}"'
                               for c in d.get("atrasados_pri_lista", [])[:3])
        _desc_pri = f"{_atr_pri} prioritário(s) atrasado(s)" + (f": {_nomes_pri}" if _nomes_pri else "")
    total_cards_ativos = max(d["em_andamento"] + sum(d["pend_lista"].values()), 1)
    # Meta: Em Andamento e Concluídos com membro — apenas de 01/07/2026 em diante
    from datetime import timezone as _tz
    _corte = datetime(2026, 7, 1, tzinfo=_tz.utc)
    _elegivel = [
        card for card in cards
        if _data_card(card) >= _corte
        and ("EM ANDAMENTO" in _labels(card) or card.get("dueComplete", False))
    ]
    # A legenda sai da MESMA lista que o percentual.
    #
    # A barra marcava 100% e logo abaixo listava cartões sem membro, com o
    # contador do topo dizendo SEM MEMBRO: 16. Os dois números estavam certos e
    # falavam de coisas diferentes: o percentual olha os cartões em andamento e
    # concluídos desde 01/07; a legenda vinha de sem_membro_lista, que é
    # preenchida com cartões ABERTOS. Uma barra cheia com uma lista de faltantes
    # embaixo só pode ser lida como erro.
    _sem_mb_cards = [card for card in _elegivel if not _users(card, membros_map)]
    _sem_mb_novo = len(_sem_mb_cards)
    _total_novo = max(len(_elegivel), 1)
    pct_com_membro = max(0, min(100, 100 - (_sem_mb_novo / _total_novo * 100)))
    _sem_mb_desc_meta = (
        f"Em andamento e concluídos desde 01/07 — todos os {len(_elegivel)} com membro"
        if not _sem_mb_cards else
        f"{_sem_mb_novo} de {len(_elegivel)} sem membro: "
        + ", ".join(f'"{c["name"][:30]}"' for c in _sem_mb_cards[:3])
    )



    def _barra_meta(nome, pct, desc, cor_barra):
        pct_c = min(max(pct,0),100)
        # % sempre na cor da barra
        return f"""<div style="margin-bottom:8px;">
  <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px;">
    <span style="color:var(--ms-texto);">{nome}</span>
    <span style="color:{cor_barra};font-weight:700;">{pct_c:.0f}%</span>
  </div>
  <div style="background:var(--ms-metric-bd);border-radius:3px;height:5px;overflow:hidden;">
    <div style="background:{cor_barra};width:{pct_c:.1f}%;height:100%;border-radius:3px;"></div>
  </div>
  <div style="font-size:8px;color:{cor_barra};margin-top:2px;opacity:.8;">{desc}</div>
</div>"""

    def _barra_aguardando(nome, desc, cor_barra):
        return f"""<div style="margin-bottom:8px;">
  <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px;">
    <span style="color:var(--ms-texto);">{nome}</span>
    <span style="color:#555;font-weight:700;">—</span>
  </div>
  <div style="background:var(--ms-metric-bd);border-radius:3px;height:5px;overflow:hidden;">
    <div style="background:{cor_barra};width:100%;height:100%;border-radius:3px;opacity:.2;"></div>
  </div>
  <div style="font-size:8px;color:var(--ms-texto-sec);margin-top:2px;">{desc}</div>
</div>"""

    # Cálculos penalidades com limites da configuração persistida
    qtd_pen       = len(d["pen_cards"])
    max_pen_n     = int(cfg_mes.get("max_pen_normal", 4))
    max_pen_x     = int(cfg_mes.get("max_pen_maxx", 1))
    max_tol_n     = int(cfg_mes.get("max_tol_normal", 15))
    max_tol_x     = int(cfg_mes.get("max_tol_maxx", 7))
    max_atr_n     = int(cfg_mes.get("max_atr_normal", 10))
    max_atr_x     = int(cfg_mes.get("max_atr_maxx", 5))
    max_retrab_n  = int(cfg_mes.get("max_retrab_normal", 10))
    max_retrab_x  = int(cfg_mes.get("max_retrab_maxx", 5))

    # Penalidades: acumulam de 0% (sem pen.) até 100% (no limite) — barra VERMELHA
    pct_pen_normal = min(qtd_pen / (max_pen_n + 1) * 100, 100) if max_pen_n >= 0 else 0
    pct_pen_maxx   = min(qtd_pen / (max_pen_x + 1) * 100, 100) if max_pen_x >= 0 else 0

    # Retrabalho: calcula do processamento do mês (via _processar já aplicou filtro_mes)
    _total_concl  = d.get("total_concl", 0)
    _corr_concl   = d.get("correcao_concl", 0)
    pct_retrab    = (_corr_concl / _total_concl * 100) if _total_concl > 0 else 0
    _desc_retrab  = (f"{pct_retrab:.1f}% retrabalho · {_corr_concl} correção(ões) / {_total_concl} concluídos"
                     if _total_concl > 0 else "Nenhum cartão concluído no período")
    # Barra: 100% = sem retrabalho (meta batida), decresce conforme aumenta — VERDE quando 100%, VERMELHO quando abaixo
    pct_retrab_barra_n = max(0.0, (1.0 - pct_retrab / max_retrab_n) * 100) if max_retrab_n > 0 else 100.0
    pct_retrab_barra_x = max(0.0, (1.0 - pct_retrab / max_retrab_x) * 100) if max_retrab_x > 0 else 100.0

    # ══ MODO TV — gera HTML estático e encerra (sem WebSocket) ══
    # Todas as variáveis necessárias já estão calculadas aqui.
    _alertas_tv = _alertas_tv_list(listas, cards, membros_map)
    # ── Ritmo de desempenho para TV ──
    import calendar as _cal_tv
    _hoje_tv = datetime.now().date()
    _ritmo_tv_html = ""
    if filtro_mes[0] == _hoje_tv.year and filtro_mes[1] == _hoje_tv.month:
        _feriados_br_tv = {(1,1),(4,21),(5,1),(9,7),(10,12),(11,2),(11,15),(12,25)}
        _, _n_dias_tv = _cal_tv.monthrange(filtro_mes[0], filtro_mes[1])
        _total_uteis_tv = sum(
            1 for _d in range(1, _n_dias_tv+1)
            if datetime(filtro_mes[0], filtro_mes[1], _d).weekday() < 5
            and (filtro_mes[1], _d) not in _feriados_br_tv
        )
        _uteis_dec_tv = sum(
            1 for _d in range(1, _hoje_tv.day+1)
            if datetime(filtro_mes[0], filtro_mes[1], _d).weekday() < 5
            and (filtro_mes[1], _d) not in _feriados_br_tv
        )
        if _total_uteis_tv > 0 and _uteis_dec_tv > 0:
            _pts_esp_tv = meta_eq / _total_uteis_tv * _uteis_dec_tv
            _diff_pct_tv = (saldo_eq - _pts_esp_tv) / _pts_esp_tv * 100 if _pts_esp_tv > 0 else 0
            _proj_tv = saldo_eq / _uteis_dec_tv * _total_uteis_tv
            if _diff_pct_tv > 10:
                _r_icon_tv, _r_cor_tv = "📈", "#1BAF7A"
                _r_txt_tv = f"{_diff_pct_tv:.0f}% acima do ritmo"
                _r_extra_tv = f"+{saldo_eq-_pts_esp_tv:.0f} pts · projeção: {_proj_tv:.0f} pts"
            elif _diff_pct_tv < -10:
                _r_icon_tv, _r_cor_tv = "📉", "#E34948"
                _r_txt_tv = f"{abs(_diff_pct_tv):.0f}% abaixo do ritmo"
                _r_extra_tv = f"{saldo_eq-_pts_esp_tv:.0f} pts · projeção: {_proj_tv:.0f} pts"
            else:
                _r_icon_tv, _r_cor_tv = "📊", "#EDA100"
                _r_txt_tv = "Dentro do ritmo esperado"
                _r_extra_tv = f"Esperado {_pts_esp_tv:.0f} pts · projeção: {_proj_tv:.0f} pts"
            _ritmo_tv_html = (f'<div style="margin-top:4px;padding:3px 6px;background:{_r_cor_tv}18;'
                              f'border:1px solid {_r_cor_tv}44;border-radius:4px;font-size:9px;">'
                              f'<span style="color:{_r_cor_tv};font-weight:700;">{_r_icon_tv} {_r_txt_tv}</span>'
                              f'<span style="color:#aaa;margin-left:6px;">{_r_extra_tv}</span></div>')
    _html_tv = _tv_full_html(
        pct_eq=pct_eq, pct_maxx=pct_maxx,
        saldo_eq=saldo_eq, meta_eq=meta_eq, faltam=faltam,
        pts_pendentes=d["pts_pendentes"],
        meta_maxx_pts=meta_maxx_pts, faltam_maxx=faltam_maxx,
        maxx_pct=maxx_pct, pen_total=d["pen_total"], n_pen=len(d["pen_cards"]),
        d=d, fila=fila, alertas=_alertas_tv, pend_lista=d["pend_lista"],
        pct_pri_ok=pct_prioritarios_ok,
        pct_retrab_n=pct_retrab_barra_n, pct_pen_n=pct_pen_normal,
        pct_retrab_x=pct_retrab_barra_x, pct_pen_x=pct_pen_maxx,
        pct_com_membro=pct_com_membro, desc_retrab=_desc_retrab,
        max_retrab_n=max_retrab_n, max_pen_n=max_pen_n,
        max_retrab_x=max_retrab_x, max_pen_x=max_pen_x,
        n_urgentes=d.get("urgentes", 0), n_sem_mb=d.get("sem_membro", 0),
        agora_str=agora.strftime("%d/%m/%Y %H:%M"),
        gerado_epoch=int(agora.timestamp()),
        meta_ind_map=meta_ind_map,
        ritmo_tv_html=_ritmo_tv_html,
        sem_membro_lista=d.get("sem_membro_lista", []),
        sem_membro_desc=_sem_mb_desc_meta,
    )
    if _write_tv_static(_html_tv) and headless:
        TV_STATUS["motivo"] = ""   # chegou ate aqui e gravou: a volta valeu

    # Estado da regeneracao, para quem abre o painel. Uma TV congelada nao se
    # anuncia; esta linha anuncia por ela.
    if not modo_tv:
        try:
            _tipo_tv, _msg_tv = tv_diagnostico()
            getattr(st, _tipo_tv if _tipo_tv != "caption" else "caption")(_msg_tv)
        except Exception:
            pass

    if modo_tv:
        st.info(
            "📺 **Painel TV atualizado!** "
            "Acesse na TV: `https://app.martinsousa.com.br/app/static/tv.html` "
            "— HTML puro, sem WebSocket, auto-atualiza a cada 60s."
        )
        return

    with col_meta_n:
        b = ""
        b += f'<div style="font-size:10px;font-weight:600;color:#1BAF7A;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px;">📋 Meta Coletiva</div>'
        _cor_eq   = "#1BAF7A"  # progresso — sempre verde
        _cor_pri  = "#1BAF7A" if pct_prioritarios_ok  >= 100 else "#E34948"
        _cor_rtn  = "#1BAF7A" if pct_retrab_barra_n   >= 100 else "#E34948"
        _cor_cmb  = "#1BAF7A" if pct_com_membro       >= 99.5 else "#E34948"
        _sem_mb_desc_n = _sem_mb_desc_meta
        b += _barra_meta("Pontuação do mês", pct_eq, f"{saldo_eq:,.0f} / {meta_eq:,} pts (inclui -{d['pen_total']:.0f} penalidades)", _cor_eq)
        b += _barra_meta("Sem atraso em prioritários P8-P10", pct_prioritarios_ok, _desc_pri, _cor_pri)
        b += _barra_meta(f"Retrabalho abaixo de {max_retrab_n}%", pct_retrab_barra_n, _desc_retrab, _cor_rtn)
        b += _barra_meta(f"Menos de {max_pen_n+1} penalidades", pct_pen_normal, f"{qtd_pen} ocorrência(s) / máx {max_pen_n}", "#E34948")
        b += _barra_meta("Cartões com membro atribuído", pct_com_membro, _sem_mb_desc_n, _cor_cmb)
        st.markdown(f'<div style="background:var(--ms-metric-bg);border:1px solid #1BAF7A22;border-radius:8px;padding:12px 14px;">{b}</div>', unsafe_allow_html=True)

    with col_meta_x:
        b = ""
        b += f'<div style="font-size:10px;font-weight:600;color:#FFD700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px;">⭐ Meta Maxx Coletiva</div>'
        _cor_mx   = "#FFD700"  # progresso — sempre amarelo
        _cor_prix = "#FFD700" if pct_prioritarios_ok  >= 100 else "#E34948"
        _cor_rtnx = "#FFD700" if pct_retrab_barra_x   >= 100 else "#E34948"
        _cor_cmbx = "#FFD700" if pct_com_membro       >= 99.5 else "#E34948"
        _sem_mb_desc_x = _sem_mb_desc_meta
        b += _barra_meta(f"Pontuação +{maxx_pct-100}% acima da meta", pct_maxx, f"{saldo_eq:,.0f} / {meta_maxx_pts:,.0f} pts (c/ penalidades -{ d['pen_total']:.0f})", _cor_mx)
        b += _barra_meta("Zero prioritários em atraso", pct_prioritarios_ok, _desc_pri, _cor_prix)
        b += _barra_meta(f"Retrabalho abaixo de {max_retrab_x}%", pct_retrab_barra_x, _desc_retrab, _cor_rtnx)
        b += _barra_meta(f"Menos de {max_pen_x+1} penalidades", pct_pen_maxx, f"{qtd_pen} ocorrência(s) / máx {max_pen_x}", "#E34948")
        b += _barra_meta("Cartões com membro atribuído", pct_com_membro, _sem_mb_desc_x, _cor_cmbx)
        st.markdown(f'<div style="background:var(--ms-metric-bg);border:1px solid #FFD70022;border-radius:8px;padding:12px 14px;">{b}</div>', unsafe_allow_html=True)

    # ══ BLOCO 3 — EM ANDAMENTO | FILA | DESEMPENHO ══
    st.markdown('<hr style="border:none;border-top:1px solid var(--ms-divisor);margin:10px 0 8px 0;"/>',unsafe_allow_html=True)
    col_and,col_fila,col_colab=st.columns([3,3,3])

    with col_and:
        st.markdown("**▶️ Em Andamento Agora**")
        if d["andamento_lista"]:
            for c in d["andamento_lista"]:
                ms=", ".join(MEMBROS_ATIVOS.get(u,u) for u in c["membros"]) or "—"
                st.markdown(f"""<div style="background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);border-radius:8px;padding:8px 12px;margin-bottom:5px;">
                  <div style="font-size:12px;font-weight:600;color:var(--ms-texto);">{c['card'][:48]}</div>
                  <div style="font-size:10px;color:var(--ms-texto-sec);margin-top:1px;">{c['lista'][:35]} · <span style="color:#1BAF7A;">{ms}</span></div>
                </div>""",unsafe_allow_html=True)
        else:
            st.caption("Nenhum cartão em andamento.")

    with col_fila:
        st.markdown("**📋 Próximas Demandas na Fila**")
        if fila:
            for item in fila[:4]:
                st.markdown(_fila_html(item),unsafe_allow_html=True)
        else:
            st.caption("Fila vazia 🎉")

    with col_colab:
        st.markdown("**👥 Desempenho por Colaborador**")
        barras=""
        for u,nome in MEMBROS_ATIVOS.items():
            pts=d["pts_membro"].get(u,0); pen=d["pen_membro"].get(u,0)
            barras+=_barra(nome,pts,meta_ind_map.get(u,1500),pen)
        st.markdown(f'<div style="padding:4px 0">{barras}</div>',unsafe_allow_html=True)

    # ══ BLOCO 4 — PENDENTES + TEMPO MÉDIO (oculto na TV para caber na tela) ══
    if not modo_tv:
        st.markdown('<hr style="border:none;border-top:1px solid var(--ms-divisor);margin:10px 0 8px 0;"/>',unsafe_allow_html=True)
        col_pend,col_tempo=st.columns([1,1])

        with col_pend:
            st.markdown("**🟠 Pendentes por Coluna**")
            if d["pend_lista"]:
                max_q=max(d["pend_lista"].values())
                for nl,qtd in sorted(d["pend_lista"].items(),key=lambda x:-x[1]):
                    pct_b=qtd/max_q*100
                    st.markdown(f"""<div style="margin-bottom:6px;">
                      <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--ms-texto);margin-bottom:2px;">
                        <span>{nl[:38]}</span><span style="font-weight:700;">{qtd}</span></div>
                      <div style="background:var(--ms-metric-bd);border-radius:3px;height:5px;">
                        <div style="background:#EDA100;width:{pct_b:.0f}%;height:100%;border-radius:3px;"></div>
                      </div></div>""",unsafe_allow_html=True)
            else:
                st.caption("Nenhum cartão pendente 🎉")

        with col_tempo:
            st.markdown("**⏱️ Tempo Médio por Coluna**")
            listas_t=[nl for nl in set(listas.values())
                      if nl not in LISTAS_PENALIDADE and nl!="TABELA DE PONTUAÇÃO"
                      and nl not in LISTAS_SEM_PONTUACAO]
            listas_ord=sorted(listas_t)
            cols_t=st.columns(3)
            for i,nl in enumerate(listas_ord[:18]):
                tempos=d["tempo_lista"].get(nl,[])
                cfg=_cfg_colunas().get(nl)
                if tempos:
                    media=sum(tempos)/len(tempos)
                    val=f"{media:.0f}min"; sub=f"{len(tempos)} reais"; cor="var(--ms-texto)"
                elif cfg:
                    val=f"~{cfg['tempo_min']}min"; sub="estimativa"; cor="var(--ms-texto-sec)"
                else:
                    val="—"; sub="sem dados"; cor="var(--ms-texto-sec)"
                nl_curto=nl[:20]+"…" if len(nl)>20 else nl
                with cols_t[i%3]:
                    st.markdown(f"""<div style="background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);border-radius:6px;padding:6px 8px;margin-bottom:4px;display:flex;align-items:center;justify-content:space-between;gap:4px;">
                      <div style="flex:1;min-width:0;">
                        <div style="font-size:8px;color:var(--ms-texto-sec);text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{nl_curto}</div>
                        <div style="font-size:7px;color:var(--ms-texto-sec);margin-top:1px;">{sub}</div>
                      </div>
                      <div style="font-size:14px;font-weight:700;color:{cor};white-space:nowrap;text-align:right;">{val}</div>
                    </div>""",unsafe_allow_html=True)

    # ══ BLOCO 5 — PENALIDADES (coletivas, apenas master, oculto na TV) ══
    if not modo_tv and eh_master and d["pen_cards"]:
        st.markdown('<hr style="border:none;border-top:1px solid var(--ms-divisor);margin:10px 0 8px 0;"/>',unsafe_allow_html=True)
        st.markdown("**⚠️ Penalidades Registradas**")
        for p in d["pen_cards"]:
            ms=", ".join(MEMBROS_ATIVOS.get(u,u) for u in p["membros"]) or "Sem membro"
            st.markdown(f"""<div style="background:var(--ms-metric-bg);border:1px solid #E34948;border-radius:8px;padding:10px 14px;margin-bottom:5px;">
              <div style="display:flex;justify-content:space-between;">
                <span style="font-size:12px;font-weight:600;color:var(--ms-texto);">{p['card'][:55]}</span>
                <span style="font-size:13px;font-weight:700;color:#E34948;">-{p['valor']:.0f} pts</span>
              </div>
              <div style="font-size:10px;color:var(--ms-texto-sec);margin-top:2px;">{ms}</div>
            </div>""",unsafe_allow_html=True)

    # ══ BLOCO FINAL — rodapé normal ══
    if False:  # modo_tv já fez return acima
        pass
    else:
        # Rodapé normal com dica de TV
        if _TV_TOKEN:
            st.markdown('<hr style="border:none;border-top:1px solid var(--ms-divisor);margin:10px 0 4px 0;"/>',unsafe_allow_html=True)
            st.caption(f"📺 Para TV: adicione **?tv={_TV_TOKEN}** no final da URL · {agora.strftime('%d/%m/%Y %H:%M')}")
        else:
            st.markdown('<hr style="border:none;border-top:1px solid var(--ms-divisor);margin:10px 0 4px 0;"/>',unsafe_allow_html=True)
            st.caption(f"📺 Configure **[tv] token** no Secrets para ativar modo TV · {agora.strftime('%d/%m/%Y %H:%M')}")


# ── REGENERADOR DO PAINEL DA TV ───────────────────────────────────────────────
# Antes, o static/tv.html só era reescrito quando alguém renderizava o Placar
# dentro do app. Como o Streamlit executa o corpo de todas as abas, isso
# acontecia por acidente enquanto havia gente trabalhando — e parava fora do
# expediente, deixando a TV congelada sem aviso. Pior: o arquivo nem sobrevive
# a um restart do container, então após cada deploy a TV ficava sem nada até
# alguém abrir o Placar.
#
# Esta thread torna o painel independente de pessoas: ela recalcula e reescreve
# o arquivo em intervalo fixo, 24h por dia.

_TV_INTERVALO_SEG = 60

# Estado da regeneração, para a falha parar de ser invisível.
#
# A thread engolia qualquer exceção com `except: pass`. A intenção estava certa
# — ela não pode morrer, a TV depende dela — mas o efeito era que uma falha
# deixava a TV congelada mostrando a tela de horas atrás, sem nada em lugar
# nenhum dizendo isso. Quem olhasse a TV via números plausíveis e velhos, que é
# pior do que ver uma tela quebrada.
#
# Agora a volta registra o que aconteceu, e o Painel de Metas mostra.
# `ultimo_ok` era carimbado quando pagina_placar nao levantava excecao — e ela
# tem duas saidas antecipadas que nao levantam nada (sem credencial do Trello, e
# Trello sem responder), alem de uma gravacao de arquivo que engolia o proprio
# erro. Dava para a TV ficar congelada com o diagnostico jurando "regenerada ha
# 0 min". Agora o sucesso e o ARQUIVO ter sido reescrito, e `motivo` guarda por
# que a volta nao chegou la.
TV_STATUS = {
    "voltas": 0, "erros": 0,
    "ultimo_ok": None,       # epoch da última regeneração que de fato gravou
    "ultimo_erro": None,     # epoch da última falha
    "erro": "",              # a mensagem, resumida
    "motivo": "",            # por que a volta terminou sem gravar
}


def _loop_regenerador_tv():
    import time as _t_tv
    import logging as _log_tv
    import traceback as _tb_tv
    # A thread roda fora de qualquer sessão Streamlit. As chamadas de UI viram
    # no-op, mas cada uma emite "missing ScriptRunContext" — sem isso os logs
    # do Railway ficariam ilegíveis.
    _log_tv.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context"
                      ).setLevel(_log_tv.ERROR)
    while True:
        TV_STATUS["voltas"] += 1
        try:
            TV_STATUS["motivo"] = "a volta terminou sem chegar na gravação"
            pagina_placar("martinsousa", headless=True)
            if TV_STATUS["motivo"]:
                # Voltou inteira, mas sem gravar. Nao e excecao, e tambem nao e
                # sucesso: contar como sucesso era o que escondia o problema.
                TV_STATUS["erros"] += 1
                TV_STATUS["ultimo_erro"] = _t_tv.time()
                TV_STATUS["erro"] = TV_STATUS["motivo"]
            else:
                TV_STATUS["ultimo_ok"] = _t_tv.time()
                TV_STATUS["erro"] = ""
        except Exception as e:
            # Continua sem morrer — mas agora deixa rastro, na estrutura e no
            # log do Railway.
            TV_STATUS["erros"] += 1
            TV_STATUS["ultimo_erro"] = _t_tv.time()
            TV_STATUS["erro"] = f"{type(e).__name__}: {e}"[:200]
            try:
                print("[TV regen] FALHOU:", _tb_tv.format_exc()[-1200:],
                      file=__import__("sys").stderr)
            except Exception:
                pass
        _t_tv.sleep(_TV_INTERVALO_SEG)


def tv_diagnostico():
    """Uma linha dizendo se a TV está sendo regenerada, e há quanto tempo.

    A verdade aqui é a data do ARQUIVO, não o que a thread acha que fez: é o
    arquivo que a TV lê. A contagem de voltas e o último erro entram como
    explicação de por que ele está velho, quando está.
    """
    import time as _t_d
    import os as _os_d
    agora = _t_d.time()
    ok, erro = TV_STATUS["ultimo_ok"], TV_STATUS["erro"]
    caminho = _os_d.path.join(_os_d.path.dirname(__file__), "static", "tv.html")
    try:
        idade_arq = agora - _os_d.path.getmtime(caminho)
    except Exception:
        idade_arq = None

    porque = f" Motivo: {erro}" if erro else ""

    if idade_arq is None:
        return ("error", "O arquivo da TV não existe. Ela está sem nada para "
                         "mostrar desde o último deploy." + porque)

    if idade_arq > 300:
        if TV_STATUS["voltas"] == 0:
            return ("error", f"O arquivo da TV tem {idade_arq/60:.0f} min e a "
                             f"thread de regeneração nunca rodou — ela não subiu.")
        return ("error", f"A TV está congelada: o arquivo tem {idade_arq/60:.0f} min "
                         f"({TV_STATUS['erros']} falha(s) em {TV_STATUS['voltas']} "
                         f"voltas).{porque}")

    # Arquivo fresco. Se a thread mesmo assim vem falhando, quem esta salvando a
    # TV e alguem com o Painel aberto — e no fim do expediente ela congela.
    if erro:
        return ("warning", f"O arquivo da TV está atualizado ({idade_arq/60:.0f} min), "
                           f"mas a regeneração automática está falhando "
                           f"({TV_STATUS['erros']} de {TV_STATUS['voltas']} voltas). "
                           f"Fora do expediente a TV vai congelar.{porque}")

    visto = f"{(agora - ok)/60:.0f} min" if ok else "—"
    return ("caption", f"📺 TV: arquivo com {idade_arq/60:.0f} min · última "
                       f"regeneração há {visto} · {TV_STATUS['voltas']} voltas · "
                       f"{TV_STATUS['erros']} falha(s)")


@st.cache_resource
def iniciar_regenerador_tv():
    """Sobe a thread uma única vez por processo (garantido pelo cache_resource)."""
    import threading as _th_tv
    t = _th_tv.Thread(target=_loop_regenerador_tv, name="tv-regen", daemon=True)
    t.start()
    return t
