"""
placar.py — Módulo Painel de Meta · MS Studio
Capivara mascote + velocímetro premium + metas individuais
"""

import streamlit as st
import requests
from datetime import datetime
import math
import base64, os

# ── CREDENCIAIS ────────────────────────────────────────────────────────────────
try:
    TRELLO_KEY   = st.secrets["trello"]["api_key"]
    TRELLO_TOKEN = st.secrets["trello"]["token"]
    BOARD_ID     = st.secrets["trello"]["board_id"]
except Exception:
    TRELLO_KEY = TRELLO_TOKEN = BOARD_ID = ""

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

# ── LOGO BASE64 ────────────────────────────────────────────────────────────────
def _logo_b64():
    for path in [
        os.path.join(os.path.dirname(__file__), "logo_branco.png"),
        os.path.join(os.path.dirname(__file__), "logo.png"),
    ]:
        if os.path.exists(path):
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode()
    return ""

# ── API ────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=120)
def _buscar_board():
    if not TRELLO_KEY:
        return None,None,None,None,None
    base = "https://api.trello.com/1"
    auth = {"key":TRELLO_KEY,"token":TRELLO_TOKEN}
    r_l = requests.get(f"{base}/boards/{BOARD_ID}/lists", params={**auth,"fields":"id,name"})
    listas = {l["id"]:l["name"] for l in r_l.json()} if r_l.ok else {}
    r_c = requests.get(f"{base}/boards/{BOARD_ID}/cards", params={
        **auth,"fields":"id,name,idList,idMembers,labels,dueComplete,due,dateLastActivity,customFieldItems",
        "customFieldItems":"true"})
    cards = r_c.json() if r_c.ok else []
    r_m = requests.get(f"{base}/boards/{BOARD_ID}/members", params={**auth,"fields":"id,username"})
    membros_map = {m["id"]:m["username"] for m in r_m.json()} if r_m.ok else {}
    r_cf = requests.get(f"{base}/boards/{BOARD_ID}/customFields", params=auth)
    campos = r_cf.json() if r_cf.ok else []
    id_p = next((c["id"] for c in campos if c.get("name","").upper()=="PONTOS"),None)
    id_i = next((c["id"] for c in campos if "INTERROMPIDO" in c.get("name","").upper()),None)
    return listas, cards, membros_map, id_p, id_i

def _pontos(card, id_p):
    if not id_p: return None
    for cf in card.get("customFieldItems",[]):
        if cf.get("idCustomField")==id_p:
            n = cf.get("value",{}).get("number")
            if n is not None:
                try: return float(n)
                except: pass
    return None

def _labels(card):
    return {lb.get("name","").upper() for lb in card.get("labels",[])}

def _users(card, mm):
    return [mm.get(mid,mid) for mid in card.get("idMembers",[])]

def _mes_card(card):
    d = card.get("dateLastActivity") or card.get("due") or ""
    if d:
        try:
            dt = datetime.fromisoformat(d.replace("Z","+00:00"))
            return (dt.year, dt.month)
        except: pass
    return None

def _processar(listas, cards, membros_map, id_p, id_i, filtro_mes=None):
    r = {
        "pts_membro":   {u:0.0 for u in MEMBROS_ATIVOS},
        "pts_equipe":   0.0,
        "pen_membro":   {u:0.0 for u in MEMBROS_ATIVOS},
        "pen_total":    0.0,
        "abertos":      0, "urgentes":0, "atrasados":0,
        "em_andamento": 0, "falta_conf":0, "falta_info":0, "sem_membro":0,
        "pts_pendentes":0.0,
        "pend_lista":   {},
        "pen_cards":    [],
        "andamento_lista":[],
    }
    for card in cards:
        nl = listas.get(card["idList"],"")
        if nl=="TABELA DE PONTUAÇÃO": continue
        lb = _labels(card)
        us = _users(card, membros_map)
        ok = card.get("dueComplete",False)
        pt = _pontos(card, id_p)
        if filtro_mes:
            mc = _mes_card(card)
            if mc and mc!=filtro_mes: continue
        if nl in LISTAS_PENALIDADE:
            if pt is not None:
                v = abs(pt)
                r["pen_total"] += v
                r["pen_cards"].append({"card":card["name"],"valor":v,"membros":us})
                for u in us:
                    if u in r["pen_membro"]: r["pen_membro"][u] += v
            continue
        if "EM ANDAMENTO" in lb:
            r["em_andamento"] += 1
            r["andamento_lista"].append({"card":card["name"],"lista":nl,"membros":us})
        if not ok:
            r["abertos"] += 1
            if "URGENTE" in lb or "URGENTES" in nl.upper(): r["urgentes"] += 1
            if "ATRASADO" in lb: r["atrasados"] += 1
            if "FALTA CONFERÊNCIA" in lb: r["falta_conf"] += 1
            if "FALTA INFORMAÇÃO" in lb: r["falta_info"] += 1
            if not us: r["sem_membro"] += 1
            if "PENDENTE" in lb and pt:
                r["pts_pendentes"] += pt
                r["pend_lista"][nl] = r["pend_lista"].get(nl,0)+1
        if not ok or pt is None: continue
        if nl in LISTAS_SEM_PONTUACAO: continue
        r["pts_equipe"] += pt
        ma = [u for u in us if u in MEMBROS_ATIVOS]
        if ma:
            cada = pt/len(ma)
            for u in ma: r["pts_membro"][u] += cada
    return r

# ── CAPIVARA SVG ───────────────────────────────────────────────────────────────
def _capivara_svg(estado="treino", logo_b64=""):
    """
    estado: 'treino' | 'meta' | 'maxx'
    Retorna HTML com capivara animada 2D + texto motivacional
    """

    logo_img = f'<image href="data:image/png;base64,{logo_b64}" x="88" y="118" width="24" height="24" opacity="0.9"/>' if logo_b64 else '<text x="100" y="134" text-anchor="middle" font-size="7" fill="white" font-weight="bold">MS</text>'

    if estado == "maxx":
        # Elvis mode — óculos, terno branco, globo disco
        anim_corpo = "capiElvis"
        anim_css = """
@keyframes capiElvis {
  0%,100%{transform:translateY(0) rotate(0deg);}
  25%{transform:translateY(-6px) rotate(-4deg);}
  75%{transform:translateY(-6px) rotate(4deg);}
}
@keyframes globoGiro {
  from{transform:rotate(0deg);}
  to{transform:rotate(360deg);}
}
@keyframes luz1{0%,100%{opacity:0.2;}50%{opacity:1;}}
@keyframes luz2{0%,100%{opacity:1;}50%{opacity:0.2;}}
@keyframes confete{
  0%{transform:translateY(-20px) rotate(0deg);opacity:1;}
  100%{transform:translateY(200px) rotate(720deg);opacity:0;}
}"""
        frase = "🕺 META MAXX ATINGIDA! VOCÊ É INCRÍVEL! 🕺"
        cor_frase = "#FFD700"
        extras = """
<g id="globo" style="transform-origin:160px 30px;animation:globoGiro 3s linear infinite;">
  <circle cx="160" cy="30" r="18" fill="none" stroke="#aaa" stroke-width="1.5"/>
  <circle cx="160" cy="30" r="18" fill="rgba(200,200,255,0.15)"/>
  <line x1="142" y1="30" x2="178" y2="30" stroke="#ccc" stroke-width="0.5"/>
  <line x1="160" y1="12" x2="160" y2="48" stroke="#ccc" stroke-width="0.5"/>
  <ellipse cx="160" cy="30" rx="10" ry="18" fill="none" stroke="#ccc" stroke-width="0.5"/>
</g>
<circle cx="160" cy="30" r="2" fill="#FFD700" style="animation:luz1 0.4s infinite;"/>
<circle cx="150" cy="22" r="1.5" fill="#FF6B6B" style="animation:luz2 0.4s infinite;"/>
<circle cx="170" cy="22" r="1.5" fill="#4ECDC4" style="animation:luz1 0.6s infinite;"/>
<circle cx="145" cy="38" r="1.5" fill="#FFE66D" style="animation:luz2 0.5s infinite;"/>
<circle cx="175" cy="38" r="1.5" fill="#A8E6CF" style="animation:luz1 0.7s infinite;"/>
<rect x="55" y="-5" width="8" height="8" rx="2" fill="#FF6B6B" style="animation:confete 2s infinite 0s;opacity:0"/>
<rect x="75" y="-5" width="6" height="6" rx="1" fill="#FFD700" style="animation:confete 2s infinite 0.3s;opacity:0"/>
<rect x="120" y="-5" width="7" height="7" rx="2" fill="#4ECDC4" style="animation:confete 2s infinite 0.6s;opacity:0"/>
<rect x="140" y="-5" width="5" height="9" rx="1" fill="#A8E6CF" style="animation:confete 2s infinite 0.1s;opacity:0"/>
<rect x="165" y="-5" width="8" height="6" rx="2" fill="#FF6B6B" style="animation:confete 2s infinite 0.9s;opacity:0"/>
<rect x="185" y="-5" width="6" height="8" rx="1" fill="#FFE66D" style="animation:confete 2s infinite 0.4s;opacity:0"/>"""

        corpo_svg = f"""
<g style="animation:{anim_corpo} 0.5s ease-in-out infinite;transform-origin:100px 140px;">
  <!-- corpo -->
  <ellipse cx="100" cy="150" rx="42" ry="38" fill="#8B6914"/>
  <!-- terno branco-->
  <ellipse cx="100" cy="163" rx="38" ry="28" fill="#F0F0F0"/>
  <!-- camisa preta dentro -->
  <ellipse cx="100" cy="155" rx="22" ry="20" fill="#1a1a1a"/>
  {logo_img}
  <!-- lapela terno -->
  <path d="M88,148 L100,162 L112,148" fill="#F0F0F0" stroke="#ddd" stroke-width="0.5"/>
  <!-- cabeça -->
  <ellipse cx="100" cy="108" rx="32" ry="28" fill="#8B6914"/>
  <!-- focinho -->
  <ellipse cx="100" cy="120" rx="18" ry="12" fill="#A0782A"/>
  <ellipse cx="100" cy="124" rx="10" ry="5" fill="#7A5010"/>
  <!-- narinas -->
  <ellipse cx="96" cy="122" rx="3" ry="2" fill="#5A3A00"/>
  <ellipse cx="104" cy="122" rx="3" ry="2" fill="#5A3A00"/>
  <!-- olhos felizes -->
  <ellipse cx="88" cy="105" rx="6" ry="6" fill="white"/>
  <ellipse cx="88" cy="106" rx="4" ry="4" fill="#1a1a1a"/>
  <ellipse cx="86" cy="104" rx="1.5" ry="1.5" fill="white"/>
  <ellipse cx="112" cy="105" rx="6" ry="6" fill="white"/>
  <ellipse cx="112" cy="106" rx="4" ry="4" fill="#1a1a1a"/>
  <ellipse cx="110" cy="104" rx="1.5" ry="1.5" fill="white"/>
  <!-- estrelinhas nos olhos -->
  <text x="86" y="100" font-size="8" fill="#FFD700">★</text>
  <text x="109" y="100" font-size="8" fill="#FFD700">★</text>
  <!-- óculos Elvis -->
  <rect x="79" y="101" width="16" height="9" rx="4" fill="none" stroke="#FFD700" stroke-width="2"/>
  <rect x="104" y="101" width="16" height="9" rx="4" fill="none" stroke="#FFD700" stroke-width="2"/>
  <line x1="95" y1="105" x2="104" y2="105" stroke="#FFD700" stroke-width="2"/>
  <line x1="70" y1="105" x2="79" y2="105" stroke="#FFD700" stroke-width="2"/>
  <line x1="120" y1="105" x2="127" y2="105" stroke="#FFD700" stroke-width="2"/>
  <!-- lentes escuras -->
  <rect x="80" y="102" width="14" height="7" rx="3" fill="rgba(0,0,0,0.7)"/>
  <rect x="105" y="102" width="14" height="7" rx="3" fill="rgba(0,0,0,0.7)"/>
  <!-- cabelo pompadour Elvis -->
  <path d="M72,95 Q80,70 100,72 Q120,70 128,95 Q115,80 100,82 Q85,80 72,95Z" fill="#3A2A00"/>
  <path d="M100,72 Q105,60 110,65 Q108,75 100,78Z" fill="#3A2A00"/>
  <!-- sorriso -->
  <path d="M90,128 Q100,135 110,128" fill="none" stroke="#5A3A00" stroke-width="2" stroke-linecap="round"/>
  <ellipse cx="100" cy="131" rx="5" ry="2" fill="#FF6B6B"/>
  <!-- orelhas -->
  <ellipse cx="68" cy="108" rx="8" ry="10" fill="#8B6914"/>
  <ellipse cx="132" cy="108" rx="8" ry="10" fill="#8B6914"/>
  <!-- braços dançando -->
  <path d="M60,155 Q45,135 55,120" fill="none" stroke="#8B6914" stroke-width="10" stroke-linecap="round"/>
  <path d="M140,155 Q155,135 145,120" fill="none" stroke="#8B6914" stroke-width="10" stroke-linecap="round"/>
  <!-- mãos -->
  <circle cx="55" cy="120" r="7" fill="#A0782A"/>
  <circle cx="145" cy="120" r="7" fill="#A0782A"/>
  <!-- pernas -->
  <path d="M80,183 Q75,200 70,215" fill="none" stroke="#8B6914" stroke-width="12" stroke-linecap="round"/>
  <path d="M120,183 Q125,200 130,215" fill="none" stroke="#8B6914" stroke-width="12" stroke-linecap="round"/>
  <!-- pés com sapato branco -->
  <ellipse cx="68" cy="218" rx="14" ry="6" fill="white"/>
  <ellipse cx="132" cy="218" rx="14" ry="6" fill="white"/>
</g>"""

    elif estado == "meta":
        # Comemorando — pulando com fogos
        anim_css = """
@keyframes capiPula {
  0%,100%{transform:translateY(0);}
  40%{transform:translateY(-20px);}
  60%{transform:translateY(-18px);}
}
@keyframes fogo1{
  0%{transform:translateY(0) scale(1);opacity:1;}
  100%{transform:translateY(-80px) scale(0.2);opacity:0;}
}
@keyframes fogo2{
  0%{transform:translateY(0) translateX(0) scale(1);opacity:1;}
  100%{transform:translateY(-60px) translateX(30px) scale(0.2);opacity:0;}
}
@keyframes fogo3{
  0%{transform:translateY(0) translateX(0) scale(1);opacity:1;}
  100%{transform:translateY(-60px) translateX(-30px) scale(0.2);opacity:0;}
}
@keyframes brilho{0%,100%{opacity:0.3;}50%{opacity:1;}}"""
        frase = "🎉 META BATIDA! PARABÉNS TIME! 🎉"
        cor_frase = "#27AE60"
        extras = """
<circle cx="60" cy="60" r="4" fill="#FF6B6B" style="animation:fogo1 1s infinite 0s;"/>
<circle cx="60" cy="60" r="3" fill="#FFD700" style="animation:fogo1 1s infinite 0.2s;"/>
<circle cx="140" cy="50" r="4" fill="#4ECDC4" style="animation:fogo2 1.2s infinite 0.1s;"/>
<circle cx="140" cy="50" r="3" fill="#FF6B6B" style="animation:fogo3 1s infinite 0.3s;"/>
<circle cx="100" cy="40" r="5" fill="#FFD700" style="animation:fogo1 0.8s infinite 0.15s;"/>
<text x="55" y="55" font-size="16" style="animation:fogo1 1.5s infinite 0s;">🎊</text>
<text x="130" y="45" font-size="16" style="animation:fogo2 1.3s infinite 0.2s;">🎊</text>
<text x="90" y="35" font-size="16" style="animation:fogo3 1.1s infinite 0.1s;">✨</text>"""
        corpo_svg = f"""
<g style="animation:capiPula 0.6s ease-in-out infinite;transform-origin:100px 140px;">
  <!-- corpo -->
  <ellipse cx="100" cy="150" rx="42" ry="38" fill="#8B6914"/>
  <!-- camisa preta -->
  <ellipse cx="100" cy="160" rx="36" ry="26" fill="#1a1a1a"/>
  {logo_img}
  <!-- cabeça -->
  <ellipse cx="100" cy="108" rx="32" ry="28" fill="#8B6914"/>
  <!-- focinho -->
  <ellipse cx="100" cy="120" rx="18" ry="12" fill="#A0782A"/>
  <ellipse cx="100" cy="124" rx="10" ry="5" fill="#7A5010"/>
  <ellipse cx="96" cy="122" rx="3" ry="2" fill="#5A3A00"/>
  <ellipse cx="104" cy="122" rx="3" ry="2" fill="#5A3A00"/>
  <!-- olhos felizes fechados -->
  <path d="M83,104 Q88,100 93,104" fill="none" stroke="#3A2A00" stroke-width="2.5" stroke-linecap="round"/>
  <path d="M107,104 Q112,100 117,104" fill="none" stroke="#3A2A00" stroke-width="2.5" stroke-linecap="round"/>
  <!-- sorriso grande -->
  <path d="M86,128 Q100,140 114,128" fill="#FF6B6B" stroke="#5A3A00" stroke-width="1.5"/>
  <!-- orelhas -->
  <ellipse cx="68" cy="108" rx="8" ry="10" fill="#8B6914"/>
  <ellipse cx="132" cy="108" rx="8" ry="10" fill="#8B6914"/>
  <!-- braços para cima -->
  <path d="M60,148 Q40,125 50,105" fill="none" stroke="#8B6914" stroke-width="10" stroke-linecap="round"/>
  <path d="M140,148 Q160,125 150,105" fill="none" stroke="#8B6914" stroke-width="10" stroke-linecap="round"/>
  <circle cx="50" cy="105" r="7" fill="#A0782A"/>
  <circle cx="150" cy="105" r="7" fill="#A0782A"/>
  <!-- pernas pulando -->
  <path d="M82,183 Q70,200 62,218" fill="none" stroke="#8B6914" stroke-width="12" stroke-linecap="round"/>
  <path d="M118,183 Q130,200 138,218" fill="none" stroke="#8B6914" stroke-width="12" stroke-linecap="round"/>
  <!-- tênis -->
  <ellipse cx="60" cy="221" rx="12" ry="5" fill="#fff"/>
  <ellipse cx="140" cy="221" rx="12" ry="5" fill="#fff"/>
</g>"""

    else:
        # Treinando
        anim_css = """
@keyframes capiRun {
  0%,100%{transform:translateY(0);}
  50%{transform:translateY(-4px);}
}
@keyframes braco1 {
  0%,100%{transform:rotate(0deg);}
  50%{transform:rotate(30deg);}
}
@keyframes braco2 {
  0%,100%{transform:rotate(0deg);}
  50%{transform:rotate(-30deg);}
}
@keyframes halter {
  0%,100%{transform:translateY(0);}
  50%{transform:translateY(-5px);}
}
@keyframes suor {
  0%{transform:translateY(0);opacity:1;}
  100%{transform:translateY(15px);opacity:0;}
}
@keyframes pisca {
  0%,90%,100%{opacity:1;}
  95%{opacity:0;}
}
@keyframes fala {
  0%,40%,100%{opacity:0;transform:scale(0.8);}
  50%,90%{opacity:1;transform:scale(1);}
}"""

        frases = ["BORA TIME! 💪", "BORA BATER ESSA META! 🔥", "VAI QUE VAI! 🚀", "NÃO PARA NÃO! ⚡"]
        frase_anim = " / ".join(frases)
        frase = frase_anim
        cor_frase = "#F39C12"

        extras = """
<!-- halter esquerdo -->
<g style="animation:halter 0.5s ease-in-out infinite 0.1s;">
  <rect x="20" y="128" width="24" height="6" rx="3" fill="#444"/>
  <rect x="18" y="124" width="6" height="14" rx="2" fill="#666"/>
  <rect x="40" y="124" width="6" height="14" rx="2" fill="#666"/>
</g>
<!-- halter direito -->
<g style="animation:halter 0.5s ease-in-out infinite 0s;">
  <rect x="156" y="128" width="24" height="6" rx="3" fill="#444"/>
  <rect x="154" y="124" width="6" height="14" rx="2" fill="#666"/>
  <rect x="176" y="124" width="6" height="14" rx="2" fill="#666"/>
</g>
<!-- gotas de suor -->
<ellipse cx="72" cy="88" rx="2.5" ry="4" fill="#4ECDC4" style="animation:suor 1.5s infinite 0s;"/>
<ellipse cx="130" cy="85" rx="2" ry="3.5" fill="#4ECDC4" style="animation:suor 1.5s infinite 0.7s;"/>
<ellipse cx="68" cy="100" rx="2" ry="3" fill="#4ECDC4" style="animation:suor 1.5s infinite 0.3s;"/>"""

        corpo_svg = f"""
<g style="animation:capiRun 0.4s ease-in-out infinite;transform-origin:100px 150px;">
  <!-- corpo -->
  <ellipse cx="100" cy="150" rx="42" ry="38" fill="#8B6914"/>
  <!-- camisa preta -->
  <ellipse cx="100" cy="160" rx="36" ry="26" fill="#1a1a1a"/>
  {logo_img}
  <!-- listras camisa suadas -->
  <ellipse cx="100" cy="160" rx="36" ry="26" fill="rgba(255,255,255,0.03)"/>
  <!-- toalha no pescoço -->
  <path d="M70,138 Q100,132 130,138 Q128,148 100,146 Q72,148 70,138Z" fill="#E8E8E8"/>
  <path d="M75,138 Q78,155 76,168" fill="none" stroke="#E8E8E8" stroke-width="5" stroke-linecap="round"/>
  <!-- cabeça -->
  <ellipse cx="100" cy="108" rx="32" ry="28" fill="#8B6914"/>
  <!-- faixa na testa -->
  <rect x="68" y="90" width="64" height="10" rx="4" fill="white" opacity="0.95"/>
  <text x="100" y="99" text-anchor="middle" font-size="7" fill="#888" font-weight="bold">MARTINSOUSA</text>
  <!-- focinho -->
  <ellipse cx="100" cy="120" rx="18" ry="12" fill="#A0782A"/>
  <ellipse cx="100" cy="124" rx="10" ry="5" fill="#7A5010"/>
  <ellipse cx="96" cy="122" rx="3" ry="2" fill="#5A3A00"/>
  <ellipse cx="104" cy="122" rx="3" ry="2" fill="#5A3A00"/>
  <!-- olhos determinados -->
  <ellipse cx="88" cy="105" rx="6" ry="5" fill="white"/>
  <ellipse cx="89" cy="106" rx="4" ry="4" fill="#1a1a1a"/>
  <ellipse cx="87" cy="104" rx="1.5" ry="1.5" fill="white"/>
  <ellipse cx="112" cy="105" rx="6" ry="5" fill="white"/>
  <ellipse cx="113" cy="106" rx="4" ry="4" fill="#1a1a1a"/>
  <ellipse cx="111" cy="104" rx="1.5" ry="1.5" fill="white"/>
  <!-- sobrancelhas determinadas -->
  <path d="M82,99 Q88,96 93,99" fill="none" stroke="#3A2A00" stroke-width="2.5" stroke-linecap="round"/>
  <path d="M107,99 Q112,96 118,99" fill="none" stroke="#3A2A00" stroke-width="2.5" stroke-linecap="round"/>
  <!-- boca determinada -->
  <path d="M90,128 Q100,132 110,128" fill="none" stroke="#5A3A00" stroke-width="2" stroke-linecap="round"/>
  <!-- orelhas -->
  <ellipse cx="68" cy="108" rx="8" ry="10" fill="#8B6914"/>
  <ellipse cx="132" cy="108" rx="8" ry="10" fill="#8B6914"/>
  <!-- braços com halteres -->
  <g style="transform-origin:65px 148px;animation:braco1 0.4s ease-in-out infinite;">
    <path d="M65,148 Q38,138 30,130" fill="none" stroke="#8B6914" stroke-width="10" stroke-linecap="round"/>
    <circle cx="30" cy="130" r="6" fill="#A0782A"/>
  </g>
  <g style="transform-origin:135px 148px;animation:braco2 0.4s ease-in-out infinite;">
    <path d="M135,148 Q162,138 170,130" fill="none" stroke="#8B6914" stroke-width="10" stroke-linecap="round"/>
    <circle cx="170" cy="130" r="6" fill="#A0782A"/>
  </g>
  <!-- pernas correndo -->
  <path d="M82,183 Q68,205 58,220" fill="none" stroke="#8B6914" stroke-width="12" stroke-linecap="round"/>
  <path d="M118,183 Q132,200 138,215" fill="none" stroke="#8B6914" stroke-width="12" stroke-linecap="round"/>
  <!-- tênis -->
  <ellipse cx="56" cy="223" rx="13" ry="6" fill="#FF4444"/>
  <ellipse cx="56" cy="221" rx="13" ry="4" fill="white"/>
  <ellipse cx="140" cy="218" rx="13" ry="6" fill="#FF4444"/>
  <ellipse cx="140" cy="216" rx="13" ry="4" fill="white"/>
</g>"""

    balao_frase = f"""
<g style="animation:fala 3s ease-in-out infinite;" opacity="0">
  <rect x="10" y="228" width="180" height="22" rx="10" fill="rgba(0,0,0,0.7)"/>
  <text x="100" y="243" text-anchor="middle" font-size="11" font-weight="bold" fill="{cor_frase}">{frase if estado=='treino' else frase}</text>
</g>""" if estado == "treino" else f"""
<rect x="10" y="228" width="180" height="22" rx="10" fill="rgba(0,0,0,0.7)"/>
<text x="100" y="243" text-anchor="middle" font-size="10" font-weight="bold" fill="{cor_frase}">{frase}</text>"""

    return f"""
<div style="display:flex;flex-direction:column;align-items:center;padding:8px 0;">
<svg viewBox="0 0 200 255" width="200" height="255" style="overflow:visible;">
  <style>
  {anim_css}
  @keyframes fala {{
    0%,30%,100%{{opacity:0;}}
    40%,90%{{opacity:1;}}
  }}
  </style>
  {extras}
  {corpo_svg}
  {balao_frase}
</svg>
</div>"""

# ── VELOCÍMETRO ────────────────────────────────────────────────────────────────
def _velocimetro_premium(pct, meta_pts, atual_pts, faltam, pct_maxx=None):
    pct_clip = min(max(pct, 0), 110)
    # Ponteiro
    ang = math.radians(-180 + min(pct_clip/100, 1) * 180)
    cx, cy, r = 130, 125, 100
    px = cx + r * math.cos(ang)
    py = cy + r * math.sin(ang)
    # Cor do arco
    cor_arco = "#27AE60" if pct >= 100 else ("#F39C12" if pct >= 50 else "#C0392B")
    # Marca da meta maxx
    maxx_mark = ""
    if pct_maxx:
        ang_mx = math.radians(-180 + min(pct_maxx/100,1) * 180)
        mx_x = cx + (r+6) * math.cos(ang_mx)
        mx_y = cy + (r+6) * math.sin(ang_mx)
        mx_x2 = cx + (r-6) * math.cos(ang_mx)
        mx_y2 = cy + (r-6) * math.sin(ang_mx)
        maxx_mark = f'<line x1="{mx_x:.1f}" y1="{mx_y:.1f}" x2="{mx_x2:.1f}" y2="{mx_y2:.1f}" stroke="#FFD700" stroke-width="3" stroke-linecap="round"/>'

    # Dasharray para o arco (comprimento total do semicírculo = pi*r = ~314)
    perim = math.pi * r
    dash = min(pct_clip / 100, 1) * perim

    return f"""
<div style="text-align:center;">
<svg viewBox="0 0 260 175" width="100%" style="max-width:320px;display:block;margin:0 auto;overflow:visible;">
  <!-- arco fundo -->
  <path d="M30,125 A100,100 0 0 1 230,125"
        fill="none" stroke="var(--ms-metric-bd)" stroke-width="18" stroke-linecap="round"/>
  <!-- arco progresso -->
  <path d="M30,125 A100,100 0 0 1 230,125"
        fill="none" stroke="{cor_arco}" stroke-width="18" stroke-linecap="round"
        stroke-dasharray="{dash:.1f} {perim:.1f}"/>
  <!-- marca meta maxx -->
  {maxx_mark}
  <!-- ponteiro -->
  <line x1="{cx}" y1="{cy}" x2="{px:.1f}" y2="{py:.1f}"
        stroke="var(--ms-texto)" stroke-width="3" stroke-linecap="round"/>
  <circle cx="{cx}" cy="{cy}" r="7" fill="var(--ms-texto)"/>
  <circle cx="{cx}" cy="{cy}" r="3" fill="var(--ms-metric-bg)"/>
  <!-- ticks -->
  <text x="24" y="140" text-anchor="middle" font-size="9" fill="var(--ms-texto-sec)">0</text>
  <text x="236" y="140" text-anchor="middle" font-size="9" fill="var(--ms-texto-sec)">META</text>
  <!-- percentual grande -->
  <text x="{cx}" y="{cy-10}" text-anchor="middle" font-size="32" font-weight="700" fill="var(--ms-texto)">{min(pct,999):.0f}%</text>
</svg>
<!-- info abaixo do velocímetro -->
<div style="margin-top:4px;">
  <div style="font-size:22px;font-weight:700;color:{cor_arco};line-height:1;">{atual_pts:.0f} pts</div>
  <div style="font-size:11px;color:var(--ms-texto-sec);margin-top:2px;">Meta: {meta_pts:.0f} pts</div>
  <div style="font-size:12px;font-weight:600;color:{cor_arco};margin-top:4px;">
    {"🎯 META ATINGIDA!" if pct >= 100 else f"Faltam {faltam:.0f} pts"}
  </div>
  <div style="font-size:10px;color:var(--ms-texto-sec);letter-spacing:.5px;text-transform:uppercase;margin-top:4px;">META DA EQUIPE</div>
</div>
</div>"""

def _velocimetro_ind(pct, meta_pts, atual_pts, nome, pct_maxx=None):
    pct_clip = min(max(pct, 0), 110)
    ang = math.radians(-180 + min(pct_clip/100,1)*180)
    cx, cy, r = 80, 75, 62
    px = cx + r * math.cos(ang)
    py = cy + r * math.sin(ang)
    cor = "#27AE60" if pct >= 100 else ("#F39C12" if pct >= 50 else "#C0392B")
    perim = math.pi * r
    dash = min(pct_clip/100,1) * perim
    maxx_m = ""
    if pct_maxx:
        ang_mx = math.radians(-180 + min(pct_maxx/100,1)*180)
        mx_x  = cx + (r+5)*math.cos(ang_mx)
        mx_y  = cy + (r+5)*math.sin(ang_mx)
        mx_x2 = cx + (r-5)*math.cos(ang_mx)
        mx_y2 = cy + (r-5)*math.sin(ang_mx)
        maxx_m = f'<line x1="{mx_x:.1f}" y1="{mx_y:.1f}" x2="{mx_x2:.1f}" y2="{mx_y2:.1f}" stroke="#FFD700" stroke-width="2.5" stroke-linecap="round"/>'
    faltam = max(meta_pts - atual_pts, 0)
    return f"""
<div style="text-align:center;background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);
     border-radius:12px;padding:14px 10px;height:100%;">
  <div style="font-size:13px;font-weight:600;color:var(--ms-texto);margin-bottom:6px;">{nome}</div>
  <svg viewBox="0 0 160 110" width="100%" style="max-width:180px;display:block;margin:0 auto;overflow:visible;">
    <path d="M18,75 A62,62 0 0 1 142,75"
          fill="none" stroke="var(--ms-metric-bd)" stroke-width="12" stroke-linecap="round"/>
    <path d="M18,75 A62,62 0 0 1 142,75"
          fill="none" stroke="{cor}" stroke-width="12" stroke-linecap="round"
          stroke-dasharray="{dash:.1f} {perim:.1f}"/>
    {maxx_m}
    <line x1="{cx}" y1="{cy}" x2="{px:.1f}" y2="{py:.1f}"
          stroke="var(--ms-texto)" stroke-width="2" stroke-linecap="round"/>
    <circle cx="{cx}" cy="{cy}" r="5" fill="var(--ms-texto)"/>
    <circle cx="{cx}" cy="{cy}" r="2" fill="var(--ms-metric-bg)"/>
    <text x="{cx}" y="{cy-5}" text-anchor="middle" font-size="18" font-weight="700" fill="var(--ms-texto)">{min(pct,999):.0f}%</text>
  </svg>
  <div style="font-size:16px;font-weight:700;color:{cor};margin-top:2px;">{atual_pts:.0f} pts</div>
  <div style="font-size:10px;color:var(--ms-texto-sec);">Meta: {meta_pts:.0f} · Faltam: {faltam:.0f}</div>
  <div style="font-size:10px;font-weight:600;color:{"#27AE60" if pct>=100 else cor};margin-top:3px;">
    {"🎯 META ATINGIDA!" if pct >= 100 else ("⚡ Em progresso" if pct >= 50 else "💪 Bora!")}
  </div>
</div>"""

def _card(label, valor, sub=None, cor="var(--ms-texto)", icone=""):
    s = f'<div style="font-size:10px;color:var(--ms-texto-sec);margin-top:2px;">{sub}</div>' if sub else ""
    return f"""<div style="background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);
border-radius:10px;padding:14px 16px;height:82px;display:flex;flex-direction:column;justify-content:center;">
  <div style="font-size:10px;color:var(--ms-texto-sec);letter-spacing:.5px;text-transform:uppercase;margin-bottom:4px;">{icone} {label}</div>
  <div style="font-size:26px;font-weight:700;color:{cor};line-height:1.1;">{valor}</div>
  {s}
</div>"""

def _barra(nome, pts, meta, pen):
    saldo = pts - pen
    pct = min(saldo/meta*100,100) if meta>0 else 0
    cor = "#27AE60" if pct>=100 else ("#F39C12" if pct>=50 else "#C0392B")
    pen_h = f'<div style="font-size:10px;color:#C0392B;margin-top:2px;">⚠ -{pen:.0f} pts em penalidades</div>' if pen>0 else ""
    return f"""<div style="margin-bottom:14px;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
    <span style="font-size:13px;font-weight:600;color:var(--ms-texto);">{nome}</span>
    <span style="font-size:12px;color:var(--ms-texto-sec);">{saldo:.0f} / {meta:.0f} · <b style="color:{cor};">{pct:.0f}%</b></span>
  </div>
  <div style="background:var(--ms-metric-bd);border-radius:6px;height:10px;overflow:hidden;">
    <div style="background:{cor};width:{pct:.1f}%;height:100%;border-radius:6px;"></div>
  </div>
  {pen_h}
</div>"""

# ── PÁGINA ─────────────────────────────────────────────────────────────────────
def pagina_placar(usuario_logado):
    eh_master = usuario_logado in MASTERS
    eh_membro = usuario_logado in MEMBROS_ATIVOS

    if not TRELLO_KEY:
        st.error("Credenciais do Trello não configuradas.")
        st.code('[trello]\napi_key="..."\ntoken="..."\nboard_id="..."')
        return

    agora = datetime.now()
    logo_b64 = _logo_b64()
    
    # ── CABEÇALHO ──────────────────────────────────────────────────────────────
    col_tit, col_mes, col_att = st.columns([3,2,1])
    with col_tit:
        st.markdown("## 🏆 Painel de Meta")
    with col_mes:
        meses = [(agora.year, agora.month)]
        m, a = agora.month, agora.year
        for _ in range(5):
            m -= 1
            if m==0: m=12; a-=1
            meses.append((a,m))
        labels = [f"{MESES_PT[mm]} {aa}" for aa,mm in meses]
        sel = st.selectbox("Mês", labels, index=0, key="placar_mes", label_visibility="collapsed")
        filtro_mes = meses[labels.index(sel)]
    with col_att:
        if st.button("🔄 Atualizar", use_container_width=True):
            _buscar_board.clear(); st.rerun()

    st.caption(f"Exibindo: {sel} · atualizado a cada 2 min · {agora.strftime('%d/%m/%Y %H:%M')}")

    # ── METAS ──────────────────────────────────────────────────────────────────
    k_eq  = f"meta_eq_{filtro_mes[0]}_{filtro_mes[1]}"
    k_ind = f"meta_ind_{filtro_mes[0]}_{filtro_mes[1]}"
    k_mx  = f"meta_maxx_pct_{filtro_mes[0]}_{filtro_mes[1]}"

    with st.expander(f"⚙️ Configurar Metas — {sel}", expanded=False):
        if eh_master:
            c1,c2,c3 = st.columns(3)
            meta_eq  = c1.number_input("Meta equipe (pts)", min_value=0, value=st.session_state.get(k_eq,5000), step=100, key=k_eq)
            meta_ind = c2.number_input("Meta individual (pts)", min_value=0, value=st.session_state.get(k_ind,1500), step=100, key=k_ind)
            maxx_pct = c3.number_input("Meta Maxx (% da meta)", min_value=100, max_value=300, value=st.session_state.get(k_mx,130), step=5, key=k_mx)
        else:
            meta_eq  = st.session_state.get(k_eq,5000)
            meta_ind = st.session_state.get(k_ind,1500)
            maxx_pct = st.session_state.get(k_mx,130)
            st.info("Metas configuradas pelo gestor.")

    meta_eq  = st.session_state.get(k_eq,5000)
    meta_ind = st.session_state.get(k_ind,1500)
    maxx_pct = st.session_state.get(k_mx,130)
    meta_maxx_pts = meta_eq * maxx_pct / 100

    # ── DADOS ──────────────────────────────────────────────────────────────────
    with st.spinner("Buscando dados do Trello..."):
        dados_api = _buscar_board()
    if not dados_api or not dados_api[0]:
        st.error("Não foi possível conectar ao Trello.")
        return

    listas, cards, membros_map, id_p, id_i = dados_api
    d = _processar(listas, cards, membros_map, id_p, id_i, filtro_mes)

    pts_eq   = d["pts_equipe"]
    pen_tot  = d["pen_total"]
    saldo_eq = pts_eq - pen_tot
    pct_eq   = (saldo_eq / meta_eq * 100) if meta_eq > 0 else 0
    faltam   = max(meta_eq - saldo_eq, 0)
    pct_maxx_vel = maxx_pct  # posição da marca no velocímetro

    # Estado da capivara
    if saldo_eq >= meta_maxx_pts:
        estado_capi = "maxx"
    elif saldo_eq >= meta_eq:
        estado_capi = "meta"
    else:
        estado_capi = "treino"

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO 1 — CAPIVARA + VELOCÍMETRO + MÉTRICAS
    # ══════════════════════════════════════════════════════════════════════════
    col_capi, col_vel, col_metricas = st.columns([1, 2, 3])

    with col_capi:
        estado_emoji = "🏋️" if estado_capi == "treino" else ("🎉" if estado_capi == "meta" else "🕺")
        st.markdown(f"""<div style="display:flex;align-items:center;justify-content:center;height:260px;
            background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);border-radius:12px;
            font-size:80px;">{estado_emoji}</div>""", unsafe_allow_html=True)

    with col_vel:
        st.markdown(_velocimetro_premium(pct_eq, meta_eq, saldo_eq, faltam, pct_maxx_vel), unsafe_allow_html=True)
        if pct_maxx_vel:
            st.markdown(f'<div style="text-align:center;font-size:10px;color:#FFD700;margin-top:2px;">▲ Marca dourada = Meta Maxx ({maxx_pct}% · {meta_maxx_pts:.0f} pts)</div>', unsafe_allow_html=True)

    with col_metricas:
        r1 = st.columns(3)
        r2 = st.columns(3)
        cor_pts = "#27AE60" if pct_eq>=100 else ("#F39C12" if pct_eq>=50 else "#C0392B")
        r1[0].markdown(_card("Pontuação Atual", f"{saldo_eq:.0f}", f"Meta: {meta_eq} · Faltam: {faltam:.0f}", cor=cor_pts, icone="🏆"), unsafe_allow_html=True)
        r1[1].markdown(_card("Cartões em Aberto", d["abertos"], icone="📋"), unsafe_allow_html=True)
        r1[2].markdown(_card("Penalidades", f"-{pen_tot:.0f}", f"{len(d['pen_cards'])} ocorrências", cor="#C0392B" if pen_tot>0 else "var(--ms-texto)", icone="⚠️"), unsafe_allow_html=True)
        r2[0].markdown(_card("Pts em Aberto", f"{d['pts_pendentes']:.0f}", "Nos cartões pendentes", cor="#F39C12", icone="🟠"), unsafe_allow_html=True)
        r2[1].markdown(_card("Urgentes", d["urgentes"], icone="🚨", cor="#C0392B" if d["urgentes"]>0 else "var(--ms-texto)"), unsafe_allow_html=True)
        r2[2].markdown(_card("Sem Membro", d["sem_membro"], icone="👤", cor="#F39C12" if d["sem_membro"]>0 else "var(--ms-texto)"), unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO 2 — STATUS + COLABORADORES
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    col_status, col_colab = st.columns(2)

    with col_status:
        st.markdown("#### 📊 Status dos Cartões")
        s1,s2,s3,s4 = st.columns(4)
        s1.markdown(_card("Atrasados", d["atrasados"], icone="⏰", cor="#C0392B" if d["atrasados"]>0 else "var(--ms-texto)"), unsafe_allow_html=True)
        s2.markdown(_card("Em Andamento", d["em_andamento"], icone="▶️"), unsafe_allow_html=True)
        s3.markdown(_card("Falta Conferir", d["falta_conf"], icone="🔍"), unsafe_allow_html=True)
        s4.markdown(_card("Falta Info", d["falta_info"], icone="❓"), unsafe_allow_html=True)
        st.markdown("<div style='margin-top:10px'></div>", unsafe_allow_html=True)
        st.markdown("**▶️ Em Andamento Agora**")
        if d["andamento_lista"]:
            for c in d["andamento_lista"][:4]:
                ms = ", ".join(MEMBROS_ATIVOS.get(u,u) for u in c["membros"]) or "—"
                st.markdown(f"""<div style="background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);
                    border-radius:8px;padding:8px 12px;margin-bottom:5px;">
                    <div style="font-size:12px;font-weight:600;color:var(--ms-texto);">{c['card'][:48]}</div>
                    <div style="font-size:10px;color:var(--ms-texto-sec);margin-top:1px;">{c['lista'][:35]} · {ms}</div>
                </div>""", unsafe_allow_html=True)
        else:
            st.caption("Nenhum cartão em andamento.")

    with col_colab:
        if eh_master:
            st.markdown("#### 👥 Desempenho por Colaborador")
            barras = "".join(_barra(MEMBROS_ATIVOS[u], d["pts_membro"].get(u,0), meta_ind, d["pen_membro"].get(u,0)) for u in MEMBROS_ATIVOS)
            st.markdown(f'<div style="padding:4px 0">{barras}</div>', unsafe_allow_html=True)
        elif eh_membro:
            st.markdown("#### Seu Desempenho")
            pts = d["pts_membro"].get(usuario_logado,0)
            pen = d["pen_membro"].get(usuario_logado,0)
            saldo_i = pts - pen
            pct_i = (saldo_i/meta_ind*100) if meta_ind>0 else 0
            st.markdown(_barra(MEMBROS_ATIVOS.get(usuario_logado,usuario_logado), pts, meta_ind, pen), unsafe_allow_html=True)
            if pen > 0:
                st.warning(f"Você tem {pen:.0f} pts em penalidades este mês.")

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO 3 — METAS INDIVIDUAIS
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("#### 🎯 Metas Individuais")

    if eh_master:
        cols_ind = st.columns(len(MEMBROS_ATIVOS))
        for i, (username, nome) in enumerate(MEMBROS_ATIVOS.items()):
            pts  = d["pts_membro"].get(username, 0)
            pen  = d["pen_membro"].get(username, 0)
            saldo_i = pts - pen
            pct_i   = (saldo_i / meta_ind * 100) if meta_ind > 0 else 0
            with cols_ind[i]:
                st.markdown(_velocimetro_ind(pct_i, meta_ind, saldo_i, nome), unsafe_allow_html=True)
    elif eh_membro:
        pts  = d["pts_membro"].get(usuario_logado, 0)
        pen  = d["pen_membro"].get(usuario_logado, 0)
        saldo_i = pts - pen
        pct_i   = (saldo_i / meta_ind * 100) if meta_ind > 0 else 0
        nome = MEMBROS_ATIVOS.get(usuario_logado, usuario_logado)
        col_c, col_v = st.columns([1,2])
        with col_c:
            st.markdown(_velocimetro_ind(pct_i, meta_ind, saldo_i, nome), unsafe_allow_html=True)
        with col_v:
            st.markdown(_barra(nome, pts, meta_ind, pen), unsafe_allow_html=True)
            if pen > 0:
                st.warning(f"Você tem {pen:.0f} pts em penalidades este mês.")

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO 4 — PENDENTES + PENALIDADES
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    col_pend, col_pen = st.columns(2)

    with col_pend:
        st.markdown("#### 🟠 Pendentes por Coluna")
        if d["pend_lista"]:
            max_q = max(d["pend_lista"].values())
            for lista, qtd in sorted(d["pend_lista"].items(), key=lambda x:-x[1]):
                pct_b = qtd/max_q*100
                st.markdown(f"""<div style="margin-bottom:9px;">
                  <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--ms-texto);margin-bottom:3px;">
                    <span>{lista[:40]}</span><span style="font-weight:700;">{qtd}</span>
                  </div>
                  <div style="background:var(--ms-metric-bd);border-radius:4px;height:6px;">
                    <div style="background:#F39C12;width:{pct_b:.0f}%;height:100%;border-radius:4px;"></div>
                  </div></div>""", unsafe_allow_html=True)
        else:
            st.caption("Nenhum cartão pendente 🎉")

    with col_pen:
        if eh_master:
            st.markdown("#### ⚠️ Penalidades Registradas")
            if d["pen_cards"]:
                for p in d["pen_cards"]:
                    ms = ", ".join(MEMBROS_ATIVOS.get(u,u) for u in p["membros"]) or "Sem membro"
                    st.markdown(f"""<div style="background:var(--ms-metric-bg);border:1px solid #C0392B;
                        border-radius:8px;padding:10px 14px;margin-bottom:6px;">
                        <div style="display:flex;justify-content:space-between;">
                          <span style="font-size:12px;font-weight:600;color:var(--ms-texto);">{p['card'][:50]}</span>
                          <span style="font-size:13px;font-weight:700;color:#C0392B;">-{p['valor']:.0f} pts</span>
                        </div>
                        <div style="font-size:10px;color:var(--ms-texto-sec);margin-top:2px;">{ms}</div>
                    </div>""", unsafe_allow_html=True)
            else:
                st.caption("Nenhuma penalidade este mês. 🎉")
        else:
            st.markdown("#### 📊 Resumo do Mês")
            st.markdown(_card("Pts Conquistados", f"{d['pts_membro'].get(usuario_logado,0):.0f}", f"Meta: {meta_ind}", icone="🏆"), unsafe_allow_html=True)

    st.markdown("---")
    st.caption(f"Dados do Trello · {sel} · atualização automática a cada 2 min · {agora.strftime('%d/%m/%Y %H:%M')}")
