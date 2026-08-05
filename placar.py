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
import streamlit.components.v1 as _components
import requests
import json as _json
from datetime import datetime, timezone
import math

# ── Beep de alerta embutido como WAV base64 (compatível com LG WebOS) ─────────
def _gerar_beep_b64():
    """Gera WAV com 4 bipes (660→880→1100→1100 Hz) e retorna como base64."""
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
    return _base64.b64encode(hdr + pcm).decode('ascii')

_BEEP_WAV_B64 = _gerar_beep_b64()

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
def _write_tv_static(html: str) -> None:
    """Grava o HTML completo do painel TV no diretório static/ do Streamlit."""
    try:
        _static_dir = os.path.join(os.path.dirname(__file__), "static")
        os.makedirs(_static_dir, exist_ok=True)
        _path = os.path.join(_static_dir, "tv.html")
        with open(_path, "w", encoding="utf-8") as _f:
            _f.write(html)
    except Exception as _e:
        pass  # nunca travar o app por causa da TV

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
    r_l = requests.get(f"{base}/boards/{BOARD_ID}/lists",params={**auth,"fields":"id,name"})
    listas = {l["id"]:l["name"] for l in r_l.json()} if r_l.ok else {}
    r_c = requests.get(f"{base}/boards/{BOARD_ID}/cards",params={
        **auth,"fields":"id,name,idList,idMembers,labels,dueComplete,customFieldItems,dateLastActivity",
        "customFieldItems":"true"})
    cards = r_c.json() if r_c.ok else []
    r_m = requests.get(f"{base}/boards/{BOARD_ID}/members",params={**auth,"fields":"id,username"})
    membros_map = {m["id"]:m["username"] for m in r_m.json()} if r_m.ok else {}
    r_cf = requests.get(f"{base}/boards/{BOARD_ID}/customFields",params=auth)
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
    r = requests.get(
        f"{base}/cards/{card_id}/actions",
        params={**auth,
                "filter": "addLabelToCard,removeLabelFromCard,addMemberToCard",
                "limit": 200},
    )
    return r.json() if r.ok else []


def _calcular_tempo_execucao_min(card_id: str):
    """
    Calcula tempo total de execução em minutos:
      tempo_FILMAGEM + tempo_EM_ANDAMENTO − tempo_INTERROMPIDO_MS
    Retorna: (float minutos, datetime|None primeiro addMember)
    """
    acoes = _buscar_acoes_card(card_id)
    agora = datetime.now(timezone.utc)
    acoes_sorted = sorted(acoes, key=lambda a: a.get("date", ""))

    filmagem_ini  = None; filmagem_total  = 0.0
    andamento_ini = None; andamento_total = 0.0
    interr_ini    = None; interr_total    = 0.0
    membro_em     = None

    for ac in acoes_sorted:
        try:
            dt = datetime.fromisoformat(ac["date"].replace("Z", "+00:00"))
        except Exception:
            continue
        tipo    = ac.get("type", "")
        nome_lb = ac.get("data", {}).get("label", {}).get("name", "").upper()

        if tipo == "addLabelToCard":
            if nome_lb == LABEL_FILMAGEM and filmagem_ini is None:
                filmagem_ini = dt
            elif nome_lb == LABEL_EM_ANDAMENTO_STR and andamento_ini is None:
                andamento_ini = dt
            elif nome_lb == LABEL_INTERROMPIDO_MS and interr_ini is None:
                interr_ini = dt
        elif tipo == "removeLabelFromCard":
            if nome_lb == LABEL_FILMAGEM and filmagem_ini is not None:
                filmagem_total += (dt - filmagem_ini).total_seconds() / 60
                filmagem_ini = None
            elif nome_lb == LABEL_EM_ANDAMENTO_STR and andamento_ini is not None:
                andamento_total += (dt - andamento_ini).total_seconds() / 60
                andamento_ini = None
            elif nome_lb == LABEL_INTERROMPIDO_MS and interr_ini is not None:
                interr_total += (dt - interr_ini).total_seconds() / 60
                interr_ini = None
        elif tipo == "addMemberToCard" and membro_em is None:
            membro_em = dt

    # Períodos ainda em aberto
    if filmagem_ini:
        filmagem_total  += (agora - filmagem_ini).total_seconds()  / 60
    if andamento_ini:
        andamento_total += (agora - andamento_ini).total_seconds() / 60
    if interr_ini:
        interr_total    += (agora - interr_ini).total_seconds()    / 60

    total = max(0.0, filmagem_total + andamento_total - interr_total)
    return total, membro_em


def _num(card,id_c):
    if not id_c: return None
    for cf in card.get("customFieldItems",[]):
        if cf.get("idCustomField")==id_c:
            n=cf.get("value",{}).get("number")
            if n is not None:
                try: return float(n)
                except: pass
    return None

def _labels(card): return {lb.get("name","").upper() for lb in card.get("labels",[])}
def _users(card,mm): return [mm.get(mid,mid) for mid in card.get("idMembers",[])]

def _data_card(card):
    d=card.get("dateLastActivity","")
    if d:
        try: return datetime.fromisoformat(d.replace("Z","+00:00"))
        except: pass
    return datetime.now(timezone.utc)

def _mes_card(card):
    d=card.get("dateLastActivity","")
    if d:
        try:
            dt=datetime.fromisoformat(d.replace("Z","+00:00"))
            return (dt.year,dt.month)
        except: pass
    return None

# ── FILA ───────────────────────────────────────────────────────────────────────
def _calcular_fila(listas,cards,membros_map):
    pendentes=[]
    for card in cards:
        nl=listas.get(card["idList"],"")
        if nl in COLUNAS_SKIP or nl not in COLUNAS_CONFIG: continue
        if card.get("dueComplete",False): continue
        lb=_labels(card)
        if "EM ANDAMENTO" in lb: continue
        cfg=COLUNAS_CONFIG[nl]
        us=_users(card,membros_map)
        pendentes.append({
            "nome":card["name"],"lista":nl,
            "prioridade":cfg["prioridade"],"tempo_min":cfg["tempo_min"],
            "data":_data_card(card),
            "membros":", ".join(MEMBROS_ATIVOS.get(u,u) for u in us) or "—",
            "is_urgente": cfg["prioridade"]>=10 or "URGENTE" in nl.upper(),
        })
    pendentes.sort(key=lambda x:(-x["prioridade"],x["data"]))
    acum=0
    for i,p in enumerate(pendentes):
        p["posicao"]=i+1; acum+=p["tempo_min"]; p["eta_min"]=acum
    return pendentes

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
    d={
        "pts_equipe":0.0,"pen_total":0.0,
        "pts_membro":{u:0.0 for u in MEMBROS_ATIVOS},
        "pen_membro":{u:0.0 for u in MEMBROS_ATIVOS},
        "abertos":0,"urgentes":0,"atrasados":0,"em_andamento":0,
        "falta_conf":0,"falta_info":0,"sem_membro":0,"falta_pts":0,
        "pts_pendentes":0.0,"pen_cards":[],"andamento_lista":[],
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

        # ── PENALIDADES: contam só no mês em que foram registradas ─────────────
        if nl in LISTAS_PENALIDADE:
            if filtro_mes:
                mc=_mes_card(card)
                if mc and mc!=filtro_mes: continue
            if pt:
                v=abs(pt); d["pen_total"]+=v
                d["pen_cards"].append({"card":card["name"],"valor":v,"membros":us})
                for u in us:
                    if u in d["pen_membro"]: d["pen_membro"][u]+=v
            continue

        # ── EM ANDAMENTO: sempre visível, sem filtro de mês ────────────────────
        if "EM ANDAMENTO" in lb:
            d["em_andamento"]+=1
            d["andamento_lista"].append({"card":card["name"],"lista":nl,"membros":us})

        # ── CARTÕES ABERTOS/PENDENTES: nunca filtrados por mês ─────────────────
        if not ok:
            d["abertos"]+=1
            if "URGENTE" in lb or "URGENTES" in nl.upper(): d["urgentes"]+=1
            if "ATRASADO" in lb: d["atrasados"]+=1
            if "FALTA CONFERÊNCIA" in lb: d["falta_conf"]+=1
            if "FALTA INFORMAÇÃO" in lb: d["falta_info"]+=1
            if not us: d["sem_membro"]+=1
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
            mc=_mes_card(card)
            if mc and mc!=filtro_mes: continue

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
    <filter id="glow">
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
    4. Tempo de execução (Filmagem + EM ANDAMENTO − Interrompido MS) >= 1.5× tempo médio
    5. Concluído (dueComplete) com etiqueta PENDENTE ainda presente
    6. Mesmo cartão com EM ANDAMENTO + FILMAGEM simultaneamente
    7. Membro tem ≥1 cartão EM ANDAMENTO e ainda tem outros cartões só com FILMAGEM
    """
    agora   = datetime.now(timezone.utc)
    alertas = []

    # Pré-computa dados relevantes por membro para condição 7
    # membro → {"andamento": [card_name,...], "filmagem": [card_name,...]}
    membro_estado = {}

    for card in cards:
        nl = listas.get(card["idList"], "")
        if nl in COLUNAS_SKIP or nl not in COLUNAS_CONFIG:
            continue
        lb = _labels(card)
        us = _users(card, membros_map)
        is_andamento = LABEL_EM_ANDAMENTO_STR in lb
        is_filmagem  = LABEL_FILMAGEM         in lb
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
        if nl in COLUNAS_SKIP or nl not in COLUNAS_CONFIG:
            continue

        lb          = _labels(card)
        us          = _users(card, membros_map)
        cfg         = COLUNAS_CONFIG.get(nl, {})
        prio        = cfg.get("prioridade", 0)
        tempo_medio = cfg.get("tempo_min", 0)
        concluido   = card.get("dueComplete", False)

        is_pendente     = LABEL_PENDENTE_STR      in lb
        is_andamento    = LABEL_EM_ANDAMENTO_STR  in lb
        is_filmagem     = LABEL_FILMAGEM          in lb
        is_interrompido = LABEL_INTERROMPIDO_MS   in lb

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
                tempo_exec, _ = _calcular_tempo_execucao_min(card["id"])
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
    return alertas

def _tv_full_html(
    pct_eq, pct_maxx,
    saldo_eq, meta_eq, faltam, pts_pendentes,
    meta_maxx_pts, faltam_maxx, maxx_pct, pen_total, n_pen,
    d, fila, alertas, pend_lista,
    pct_pri_ok, pct_retrab_n, pct_pen_n, pct_retrab_x, pct_pen_x,
    pct_com_membro, desc_retrab, max_retrab_n, max_pen_n, max_retrab_x, max_pen_x,
    n_urgentes, n_sem_mb, agora_str,
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

    # Em andamento
    and_html = ""
    for c in (d.get("andamento_lista") or []):
        ms = ", ".join(MEMBROS_ATIVOS.get(u,u) for u in c.get("membros",[])) or "—"
        nome = (c["card"][:42]+"…") if len(c["card"])>42 else c["card"]
        ls   = (c["lista"][:28]+"…") if len(c["lista"])>28 else c["lista"]
        and_html += (f'<div class="card-base">'
                     f'<div class="card-and-nome">{nome}</div>'
                     f'<div class="card-and-sub">{ls} · <span>{ms}</span></div></div>')
    if not and_html:
        and_html = '<div style="font-size:10px;color:#555;padding:8px;">Nenhum em andamento</div>'

    # Próximas 6 da fila
    ORDS = ["1°","2°","3°","4°","5°","6°"]
    fila_html = ""
    for i, item in enumerate(fila[:6]):
        p = item["prioridade"]
        cor = "#E34948" if p>=10 else ("#EDA100" if p>=8 else ("#1BAF7A" if p>=6 else "#888"))
        badge = '<span class="badge-urg">URGENTE</span> · ' if (item.get("is_urgente") or p>=8) else ""
        nome = (item["nome"][:44]+"…") if len(item["nome"])>44 else item["nome"]
        ls   = (item["lista"][:24]+"…") if len(item["lista"])>24 else item["lista"]
        eta  = _fmt_tempo(item["eta_min"])
        fila_html += (f'<div class="card-base"><div class="fila-inner">'
                      f'<div class="fila-num" style="color:{cor};">{ORDS[i]}</div>'
                      f'<div class="fila-info"><div class="fila-nome">{nome}</div>'
                      f'<div class="fila-sub">{ls} · {badge}P{p}</div></div>'
                      f'<div class="fila-tempo">~{eta}</div></div></div>')
    if not fila_html:
        fila_html = '<div style="font-size:10px;color:#555;padding:8px;">Fila vazia 🎉</div>'

    # Alertas JS
    n_alerta_urg = sum(1 for a in alertas if a.get("tipo") == "urgente")
    n_alerta_atc = sum(1 for a in alertas if a.get("tipo") == "atencao")
    alertas_js = "[\n"
    for a in alertas:
        ne = a["nome"].replace('"','\\"').replace("'","\\'")
        ce = a["col"].replace('"','\\"')
        de = a.get("detalhe","").replace('"','\\"').replace("'","\\'")
        alertas_js += (f'  {{tipo:"{a["tipo"]}",prioridade:"{a["lab"]}",pos:"{a["pos"]}",'
                       f'nome:"{ne}",col:"{ce}",detalhe:"{de}"}},\n')
    alertas_js += "]"

    pend_total = sum(pend_lista.values()) if pend_lista else 0
    atrasados  = d.get("atrasados", 0)
    desc_pri   = "Nenhum cartão prioritário atrasado" if atrasados == 0 else f"{atrasados} atrasado(s)"

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="60">
<title>MS Studio — TV</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
html,body{{width:100%;height:100%;overflow:hidden;background:#1a1a1a;color:#e0e0e0;font-family:Arial,Helvetica,sans-serif;}}
.tv-root{{position:absolute;top:0;left:0;width:100%;height:100%;overflow:hidden;}}
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
.needle-maxx{{-webkit-animation:glow-needle 2.4s ease-in-out infinite;animation:glow-needle 2.4s ease-in-out infinite;}}
.tip-maxx{{-webkit-animation:glow-tip 2.4s ease-in-out infinite;animation:glow-tip 2.4s ease-in-out infinite;}}
@-webkit-keyframes glow-needle{{0%,100%{{-webkit-filter:drop-shadow(0 0 3px #FFD700);}}50%{{-webkit-filter:drop-shadow(0 0 8px #FFD700);}}}}
@keyframes glow-needle{{0%,100%{{filter:drop-shadow(0 0 3px #FFD700);}}50%{{filter:drop-shadow(0 0 8px #FFD700);}}}}
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
.sub-bloco-pend{{width:22%;height:100%;overflow:hidden;}}
.sub-bloco-and{{width:15%;height:100%;overflow:hidden;}}
.sub-bloco-fila{{width:28%;height:100%;overflow:hidden;}}
.sub-bloco-alerta{{width:35%;height:100%;overflow:hidden;}}
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
.alerta-header.com-alerta.tocando{{-webkit-animation:pulso-forte 0.35s ease-in-out infinite!important;animation:pulso-forte 0.35s ease-in-out infinite!important;border-color:#FF5555!important;}}
@-webkit-keyframes pulso{{0%,100%{{-webkit-box-shadow:0 0 0 0 #E3494840;}}50%{{-webkit-box-shadow:0 0 16px 5px #E3494840;}}}}
@keyframes pulso{{0%,100%{{box-shadow:0 0 0 0 #E3494840;}}50%{{box-shadow:0 0 16px 5px #E3494840;}}}}
@-webkit-keyframes pulso-forte{{0%,100%{{-webkit-box-shadow:0 0 4px 0 #E3494880;}}50%{{-webkit-box-shadow:0 0 40px 15px #E3494899;}}}}
@keyframes pulso-forte{{0%,100%{{box-shadow:0 0 4px 0 #E3494880;}}50%{{box-shadow:0 0 40px 15px #E3494899;}}}}
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
        <line class="needle-maxx" x1="90" y1="92" x2="{nx_x}" y2="{ny_x}" stroke="#FFD700" stroke-width="2.5" stroke-linecap="round"/>
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
    <div class="pill"><span class="pill-label">Atrasados</span><span class="pill-val">{d.get("atrasados",0)}</span><span class="pill-badge" style="background:#E3494830;color:#E34948;">Atenção</span></div>
    <div class="pill"><span class="pill-label">Desativar</span><span class="pill-val">{d.get("desativar",0)}</span><span class="pill-badge" style="background:#E3494830;color:#E34948;">Prioritário</span></div>
    <div class="pill"><span class="pill-label">Reativar</span><span class="pill-val">{d.get("reativar",0)}</span><span class="pill-badge" style="background:#33333340;color:#888;">Normal</span></div>
    <div class="pill urgente"><span class="pill-label">Urgentes</span><span class="pill-val">{n_urgentes}</span><span class="pill-badge" style="background:#E3494830;color:#E34948;">Crítico</span></div>
    <div class="pill atencao"><span class="pill-label">Falta Info</span><span class="pill-val">{d.get("falta_info",0)}</span><span class="pill-badge" style="background:#EDA10020;color:#EDA100;">Pendente</span></div>
    <div class="pill atencao"><span class="pill-label">Falta Pontuação</span><span class="pill-val">{d.get("falta_pts",0)}</span><span class="pill-badge" style="background:#EDA10020;color:#EDA100;">Revisar</span></div>
    <div class="pill urgente"><span class="pill-label">Penalidades</span><span class="pill-val">-{pen_total:,.0f}</span><span class="pill-badge" style="background:#E3494820;color:#E34948;">Ocorrências</span></div>
    <div class="pill atencao"><span class="pill-label">Sem Membro</span><span class="pill-val">{n_sem_mb}</span><span class="pill-badge" style="background:#EDA10020;color:#EDA100;">Revisar</span></div>
  </div>

  <div class="bloco-barras" id="tv-bb">
    <div class="barra-box verde-border">
      <div class="bloco-titulo verde" style="margin-bottom:5px;">📋 Meta Coletiva</div>
      <div class="barra-item"><div class="barra-header"><span>Pontuação do mês</span><span style="color:#1BAF7A;font-weight:700;">{fp(pct_eq)}</span></div><div class="barra-track"><div class="barra-fill" style="width:{min(pct_eq,100):.1f}%;background:#1BAF7A;"></div></div><div class="barra-desc">{saldo_eq:,.0f} / {meta_eq:,} pts (inclui -{pen_total:.0f} penalidades)</div></div>
      <div class="barra-item"><div class="barra-header"><span>Sem atraso em prioritários P8-P10</span><span style="color:#1BAF7A;font-weight:700;">{pct_pri_ok:.0f}%</span></div><div class="barra-track"><div class="barra-fill" style="width:{min(pct_pri_ok,100):.1f}%;background:#1BAF7A;"></div></div><div class="barra-desc">{desc_pri}</div></div>
      <div class="barra-item"><div class="barra-header"><span>Retrabalho abaixo de {max_retrab_n}%</span><span style="color:#E34948;font-weight:700;">{pct_retrab_n:.0f}%</span></div><div class="barra-track"><div class="barra-fill" style="width:{min(pct_retrab_n,100):.1f}%;background:#E34948;"></div></div><div class="barra-desc">{desc_retrab}</div></div>
      <div class="barra-item"><div class="barra-header"><span>Menos de {max_pen_n+1} penalidades</span><span style="color:#E34948;font-weight:700;">{pct_pen_n:.0f}%</span></div><div class="barra-track"><div class="barra-fill" style="width:{min(pct_pen_n,100):.1f}%;background:#E34948;"></div></div><div class="barra-desc">{n_pen} ocorrência(s) / máx {max_pen_n}</div></div>
      <div class="barra-item"><div class="barra-header"><span>Cartões com membro atribuído</span><span style="color:#1BAF7A;font-weight:700;">{pct_com_membro:.0f}%</span></div><div class="barra-track"><div class="barra-fill" style="width:{min(pct_com_membro,100):.1f}%;background:#1BAF7A;"></div></div><div class="barra-desc">Em andamento e concluídos</div></div>
    </div>
    <div class="barra-box ouro-border">
      <div class="bloco-titulo ouro" style="margin-bottom:5px;">⭐ Meta Maxx Coletiva</div>
      <div class="barra-item"><div class="barra-header"><span>Pontuação +{maxx_pct-100}% acima da meta</span><span style="color:#FFD700;font-weight:700;">{fp(pct_maxx)}</span></div><div class="barra-track"><div class="barra-fill" style="width:{min(pct_maxx,100):.1f}%;background:#FFD700;"></div></div><div class="barra-desc">{saldo_eq:,.0f} / {meta_maxx_pts:,.0f} pts (c/ penalidades -{pen_total:.0f})</div></div>
      <div class="barra-item"><div class="barra-header"><span>Zero prioritários em atraso</span><span style="color:#FFD700;font-weight:700;">{pct_pri_ok:.0f}%</span></div><div class="barra-track"><div class="barra-fill" style="width:{min(pct_pri_ok,100):.1f}%;background:#FFD700;"></div></div><div class="barra-desc">{desc_pri}</div></div>
      <div class="barra-item"><div class="barra-header"><span>Retrabalho abaixo de {max_retrab_x}%</span><span style="color:#E34948;font-weight:700;">{pct_retrab_x:.0f}%</span></div><div class="barra-track"><div class="barra-fill" style="width:{min(pct_retrab_x,100):.1f}%;background:#E34948;"></div></div><div class="barra-desc">{desc_retrab}</div></div>
      <div class="barra-item"><div class="barra-header"><span>Menos de {max_pen_x+1} penalidades</span><span style="color:#E34948;font-weight:700;">{pct_pen_x:.0f}%</span></div><div class="barra-track"><div class="barra-fill" style="width:{min(pct_pen_x,100):.1f}%;background:#E34948;"></div></div><div class="barra-desc">{n_pen} ocorrência(s) / máx {max_pen_x}</div></div>
      <div class="barra-item"><div class="barra-header"><span>Cartões com membro atribuído</span><span style="color:#FFD700;font-weight:700;">{pct_com_membro:.0f}%</span></div><div class="barra-track"><div class="barra-fill" style="width:{min(pct_com_membro,100):.1f}%;background:#FFD700;"></div></div><div class="barra-desc">Em andamento e concluídos</div></div>
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
        <div class="alerta-header com-alerta" id="alerta-header">
          <div class="alerta-titulo">⚠️ ATENÇÃO</div>
          <div class="alerta-sub">{n_alerta_urg} prioritários · {n_alerta_atc} atenção</div>
        </div>
        <div class="alerta-lista" id="alerta-lista"></div>
      </div>
    </div>
  </div>
</div>

<audio id="beep-audio" src="data:audio/wav;base64,{_BEEP_WAV_B64}" preload="auto"></audio>
<div id="som-btn" onclick="ativarSom();">🔊 Ativar Som</div>

<script>
// ── Layout: calcula alturas reais em px a partir de window.innerHeight ──────
(function() {{
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
}})();
// ────────────────────────────────────────────────────────────────────────────
var ALERTAS = {alertas_js};
var MAX = 5;
var offset = 0;
function render() {{
  var lista = document.getElementById("alerta-lista");
  if (!lista) return;
  lista.innerHTML = "";
  for (var i = 0; i < MAX; i++) {{
    if (!ALERTAS.length) break;
    var a   = ALERTAS[(offset + i) % ALERTAS.length];
    var pos = (offset + i) % ALERTAS.length + 1;
    var div = document.createElement("div");
    div.className = "alerta-item " + a.tipo;
    div.innerHTML =
      '<div class="alerta-item-prioridade">' +
        '<span>' + a.prioridade + ' — ' + a.pos + '</span>' +
        '<span style="color:#555;font-weight:400;">' + pos + '/' + ALERTAS.length + '</span>' +
      '</div>' +
      '<div class="alerta-item-nome">' + a.nome + '</div>' +
      '<div class="alerta-item-col">' + a.col + '</div>' +
      '<div class="alerta-item-col" style="color:#666;font-style:italic;">' + a.detalhe + '</div>';
    lista.appendChild(div);
  }}
}}
if (ALERTAS.length) {{
  render();
  setInterval(function() {{ offset = (offset + 1) % ALERTAS.length; render(); }}, 8000);
}}
// ── Áudio via elemento <audio> HTML5 (compatível com LG WebOS) ───────────────
// Web Audio API não é suportada pela TV LG. Usamos <audio> com WAV embutido.
var _audioAtivo = false;
function _marcarBtnAtivo() {{
  var btn = document.getElementById('som-btn');
  if (btn) {{ btn.className = 'ativo'; btn.innerHTML = '🔊 Som Ativo'; }}
}}
function _marcarBtnErro() {{
  var btn = document.getElementById('som-btn');
  if (btn) {{ btn.style.color = '#E34948'; btn.innerHTML = '🔇 Sem suporte'; }}
}}
function _playAudio() {{
  var a = document.getElementById('beep-audio');
  if (!a || !_audioAtivo) return;
  try {{ a.currentTime = 0; a.play(); }} catch(e) {{}}
}}
function ativarSom() {{
  var btn = document.getElementById('som-btn');
  if (btn) {{ btn.innerHTML = '⏳ Ativando...'; }}
  try {{ localStorage.setItem('ms_tv_audio', '1'); }} catch(e) {{}}
  var a = document.getElementById('beep-audio');
  if (!a) {{ _marcarBtnErro(); return; }}
  try {{
    a.load();
    var p = a.play();
    if (p !== undefined && p.then) {{
      p.then(function() {{
        _audioAtivo = true;
        _marcarBtnAtivo();
      }}).catch(function() {{
        // play() bloqueado — tenta marcar ativo mesmo assim (WebOS pode não retornar Promise)
        _audioAtivo = true;
        _marcarBtnAtivo();
      }});
    }} else {{
      // Browser mais antigo: play() não retorna Promise
      _audioAtivo = true;
      _marcarBtnAtivo();
    }}
  }} catch(e) {{
    _marcarBtnErro();
  }}
}}
function checkAndPlay() {{
  var h = document.getElementById("alerta-header");
  if (!h) return;
  h.classList.add("tocando");
  _playAudio();
  setTimeout(_playAudio, 3500);
  setTimeout(_playAudio, 7000);
  setTimeout(function() {{ h.classList.remove("tocando"); }}, 11000);
}}
setTimeout(checkAndPlay, 4000);
setInterval(checkAndPlay, 5 * 60 * 1000);
// Auto-scale se conteúdo não couber na tela
(function() {{
  try {{
    var root = document.querySelector('.tv-root');
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
}})();
</script>
</body>
</html>"""

def _meta_ind_item(titulo, pct, descricao, cor=None, aguardando=False):
    if aguardando:
        return f"""<div class="meta-ind-card">
  <div class="meta-ind-titulo">{titulo}</div>
  <div style="font-size:10px;color:var(--ms-texto-sec);font-style:italic;">⏳ Aguardando integração do relógio de ponto</div>
</div>"""
    c=cor or ("#1BAF7A" if pct>=80 else ("#EDA100" if pct>=50 else "#E34948"))
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
def pagina_placar(usuario_logado):
    eh_master=usuario_logado.lower() in {m.lower() for m in MASTERS}
    eh_membro=usuario_logado in MEMBROS_ATIVOS
    if not TRELLO_KEY:
        st.error("Credenciais do Trello não configuradas."); return

    st.markdown(CSS,unsafe_allow_html=True)
    agora=datetime.now()
    params=st.query_params
    modo_tv = bool(_TV_TOKEN) and params.get("tv","") == _TV_TOKEN

    # ── Cabeçalho / controles ────────────────────────────────────────────────
    if modo_tv:
        # TV: sem seletor de mês, sem botão, mês atual fixo
        filtro_mes = (agora.year, agora.month)
        sel        = f"{MESES_PT[agora.month]} {agora.year}"
        @st.fragment(run_every=60)
        def _tv_ticker():
            pass
        _tv_ticker()
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
        @st.fragment(run_every=30)
        def _placar_ticker():
            pass
        _placar_ticker()
        st.caption(f"Exibindo: {sel} · atualiza automaticamente a cada 30s · {agora.strftime('%d/%m/%Y %H:%M')}")

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

    if k_eq  not in st.session_state: st.session_state[k_eq]  = int(cfg_mes["meta_equipe"])
    if k_mx  not in st.session_state: st.session_state[k_mx]  = int(cfg_mes["meta_maxx_pct"])
    if k_myr not in st.session_state: st.session_state[k_myr] = int(cfg_mes["meta_myrelladesouza"])
    if k_bea not in st.session_state: st.session_state[k_bea] = int(cfg_mes["meta_beatriz51"])
    if k_gab not in st.session_state: st.session_state[k_gab] = int(cfg_mes["meta_gabriel_borges"])

    # Configuração de metas foi movida para a aba "📊 Análise de Metas"
    meta_eq   = st.session_state[k_eq]
    maxx_pct  = st.session_state[k_mx]
    meta_maxx_pts = meta_eq * maxx_pct / 100
    # Meta individual por colaborador
    meta_ind_map = {
        "myrelladesouza": st.session_state[k_myr],
        "beatriz51":      st.session_state[k_bea],
        "gabriel_borges": st.session_state[k_gab],
    }
    # Compatibilidade: meta_ind = média para barras genéricas
    meta_ind = sum(meta_ind_map.values()) // max(len(meta_ind_map), 1)

    with st.spinner(""):
        dados=_buscar_board()
    if not dados or not dados[0]:
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
    cor_pts="#1BAF7A" if pct_eq>=100 else ("#EDA100" if pct_eq>=50 else "#E34948")

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
    pct_prioritarios_ok = 100 if d["atrasados"] == 0 else max(0, 100 - d["atrasados"]*20)
    total_cards_ativos = max(d["em_andamento"] + sum(d["pend_lista"].values()), 1)
    # Meta: Em Andamento e Concluídos com membro — apenas de 01/07/2026 em diante
    from datetime import timezone as _tz
    _corte = datetime(2026, 7, 1, tzinfo=_tz.utc)
    _elegivel = [
        card for card in cards
        if _data_card(card) >= _corte
        and ("EM ANDAMENTO" in _labels(card) or card.get("dueComplete", False))
    ]
    _sem_mb_novo = sum(1 for card in _elegivel if not _users(card, membros_map))
    _total_novo = max(len(_elegivel), 1)
    pct_com_membro = max(0, min(100, 100 - (_sem_mb_novo / _total_novo * 100)))



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
    # Barra: 0% = sem retrabalho, 100% = no limite — VERMELHO
    pct_retrab_barra_n = min(pct_retrab / max_retrab_n * 100, 100) if max_retrab_n > 0 else 0
    pct_retrab_barra_x = min(pct_retrab / max_retrab_x * 100, 100) if max_retrab_x > 0 else 0

    # ══ MODO TV — gera HTML estático e encerra (sem WebSocket) ══
    # Todas as variáveis necessárias já estão calculadas aqui.
    _alertas_tv = _alertas_tv_list(listas, cards, membros_map)
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
    )
    _write_tv_static(_html_tv)  # atualiza static/tv.html a cada refresh do app

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
        b += _barra_meta("Pontuação do mês", pct_eq, f"{saldo_eq:,.0f} / {meta_eq:,} pts (inclui -{d['pen_total']:.0f} penalidades)", "#1BAF7A")
        b += _barra_meta("Sem atraso em prioritários P8-P10", pct_prioritarios_ok, "Nenhum cartão prioritário atrasado", "#1BAF7A")
        b += _barra_meta(f"Retrabalho abaixo de {max_retrab_n}%", pct_retrab_barra_n, _desc_retrab, "#E34948")
        b += _barra_meta(f"Menos de {max_pen_n+1} penalidades", pct_pen_normal, f"{qtd_pen} ocorrência(s) / máx {max_pen_n}", "#E34948")
        b += _barra_meta("Cartões com membro atribuído", pct_com_membro, "Em andamento e concluídos", "#1BAF7A")
        st.markdown(f'<div style="background:var(--ms-metric-bg);border:1px solid #1BAF7A22;border-radius:8px;padding:12px 14px;">{b}</div>', unsafe_allow_html=True)

    with col_meta_x:
        b = ""
        b += f'<div style="font-size:10px;font-weight:600;color:#FFD700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px;">⭐ Meta Maxx Coletiva</div>'
        b += _barra_meta(f"Pontuação +{maxx_pct-100}% acima da meta", pct_maxx, f"{saldo_eq:,.0f} / {meta_maxx_pts:,.0f} pts (c/ penalidades -{ d['pen_total']:.0f})", "#FFD700")
        b += _barra_meta("Zero prioritários em atraso", pct_prioritarios_ok, "Nenhum cartão prioritário atrasado", "#FFD700")
        b += _barra_meta(f"Retrabalho abaixo de {max_retrab_x}%", pct_retrab_barra_x, _desc_retrab, "#E34948")
        b += _barra_meta(f"Menos de {max_pen_x+1} penalidades", pct_pen_maxx, f"{qtd_pen} ocorrência(s) / máx {max_pen_x}", "#E34948")
        b += _barra_meta("Cartões com membro atribuído", pct_com_membro, "Em andamento e concluídos", "#FFD700")
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
                cfg=COLUNAS_CONFIG.get(nl)
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
