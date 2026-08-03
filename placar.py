"""
placar.py — Painel de Meta · MS Studio v5
Layout: cards resumo | vel. meta | vel. maxx | cards resumo maxx
+ Fila com urgentes em vermelho
+ Meta individual detalhada
+ Modo TV
"""
import streamlit as st
import streamlit.components.v1 as _components
import requests
try:
    from streamlit_autorefresh import st_autorefresh as _st_autorefresh
    _AUTOREFRESH_OK = True
except ImportError:
    _AUTOREFRESH_OK = False
from datetime import datetime, timezone
import math

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
    cor="#1BAF7A" if pct>=100 else ("#EDA100" if pct>=50 else "#E34948")
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
    modo_tv=params.get("tv","")=="1"

    # Cabeçalho
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

    # ── Auto-refresh a cada 30s (streamlit-autorefresh) ──────────────────────
    if _AUTOREFRESH_OK:
        _st_autorefresh(interval=30_000, limit=None, key="placar_autorefresh")

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

    # ══ BLOCO 4 — PENDENTES + TEMPO MÉDIO ══
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

    # ══ BLOCO 5 — PENALIDADES (coletivas, apenas master) ══
    # (Meta Individual foi movida para aba "📊 Análise de Metas" → Por Colaborador)
    if eh_master and d["pen_cards"]:
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

    # Link TV
    st.markdown('<hr style="border:none;border-top:1px solid var(--ms-divisor);margin:10px 0 4px 0;"/>',unsafe_allow_html=True)
    st.caption(f"📺 Para TV: adicione **?tv=1** no final da URL · {agora.strftime('%d/%m/%Y %H:%M')}")
