"""
placar.py — Painel de Meta · MS Studio v4
+ Fila inteligente de próximas demandas
+ Metas individuais
+ Modo TV (via ?tv=1)
"""
import streamlit as st
import requests
from datetime import datetime, timezone, timedelta
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

# ── CONFIGURAÇÃO DA FILA ───────────────────────────────────────────────────────
COLUNAS_CONFIG = {
    "DESATIVAR (50)":                              {"prioridade":10,"tempo_min":50},
    "AJUSTE DE PREÇO (MS-20)":                    {"prioridade":9, "tempo_min":120},
    "AJUSTE DE PREÇO (EQ-70)":                    {"prioridade":9, "tempo_min":60},
    "URGENTES!!!!":                               {"prioridade":8, "tempo_min":210},
    "REATIVAR (20)":                              {"prioridade":7, "tempo_min":150},
    "CORREÇÃO DE FOTOS: 0 PONTOS":                {"prioridade":7, "tempo_min":120},
    "CRIATIVO VÍDEO (80)":                        {"prioridade":7, "tempo_min":180},
    "RETIRADA DE ETIQUETAS (30)":                 {"prioridade":7, "tempo_min":90},
    "CRIATIVO VARIAÇÃO (50)":                     {"prioridade":6, "tempo_min":120},
    "CRIATIVO DO ZERO: (FINALIZAR NO INTEGRAÇÃO!!!)": {"prioridade":6,"tempo_min":240},
    "INTEGRAÇÃO NOVOS ANÚNCIOS (100)":            {"prioridade":6, "tempo_min":60},
    "CRIATIVO FOTOS (NOVAS: 10/VAR.:2)":          {"prioridade":6, "tempo_min":180},
    "INTEGRAÇÃO VÍDEO (PONTUA NA CONFERIENCIA)":  {"prioridade":6, "tempo_min":60},
    "CONFERENCIA VÍDEO (10)":                     {"prioridade":6, "tempo_min":60},
    "TÍTULO/DESCRIÇÃO/EDIÇÃO (10)":               {"prioridade":6, "tempo_min":60},
    "ANÚNCIAR DE CATÁLOGO (10)":                  {"prioridade":6, "tempo_min":60},
    "ESPELHAMENTO DE ANÚNCIO (30)":               {"prioridade":5, "tempo_min":120},
    "CHAT (PROBLEMAS-30)":                        {"prioridade":5, "tempo_min":120},
    "DEMANDAS BLING":                             {"prioridade":5, "tempo_min":150},
    "VARIAÇÃO DE ANÚNCIO (20)":                   {"prioridade":4, "tempo_min":120},
}
COLUNAS_SKIP = {
    "TABELA DE PONTUAÇÃO","TRIAGEM","PENALIDADES",
    "RENAN","GUSTAVO","MYRELLA","Vídeos pendentes",
    "CRIAR ANÚNCIO","CRIAR ANÚNCIO DO ZERO",
}
CAPACIDADE_MIN = 390  # 6h30 por colaborador

# ── API ────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def _buscar_board():
    if not TRELLO_KEY: return None,None,None,None,None,None
    base = "https://api.trello.com/1"
    auth = {"key":TRELLO_KEY,"token":TRELLO_TOKEN}
    r_l = requests.get(f"{base}/boards/{BOARD_ID}/lists", params={**auth,"fields":"id,name"})
    listas = {l["id"]:l["name"] for l in r_l.json()} if r_l.ok else {}
    r_c = requests.get(f"{base}/boards/{BOARD_ID}/cards", params={
        **auth,
        "fields":"id,name,idList,idMembers,labels,dueComplete,customFieldItems,dateLastActivity",
        "customFieldItems":"true"})
    cards = r_c.json() if r_c.ok else []
    r_m = requests.get(f"{base}/boards/{BOARD_ID}/members", params={**auth,"fields":"id,username"})
    membros_map = {m["id"]:m["username"] for m in r_m.json()} if r_m.ok else {}
    r_cf = requests.get(f"{base}/boards/{BOARD_ID}/customFields", params=auth)
    campos = r_cf.json() if r_cf.ok else []
    id_p = next((c["id"] for c in campos if c.get("name","").upper()=="PONTOS"),None)
    id_t = next((c["id"] for c in campos if "TEMPO ACUMULADO" in c.get("name","").upper()),None)
    id_interr = next((c["id"] for c in campos if "INTERROMPIDO" in c.get("name","").upper()),None)
    return listas, cards, membros_map, id_p, id_t, id_interr

def _campo_num(card, id_campo):
    if not id_campo: return None
    for cf in card.get("customFieldItems",[]):
        if cf.get("idCustomField")==id_campo:
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
    d = card.get("dateLastActivity","")
    if d:
        try:
            dt = datetime.fromisoformat(d.replace("Z","+00:00"))
            return (dt.year, dt.month)
        except: pass
    return None

def _data_card(card):
    d = card.get("dateLastActivity","")
    if d:
        try: return datetime.fromisoformat(d.replace("Z","+00:00"))
        except: pass
    return datetime.now(timezone.utc)

# ── FILA INTELIGENTE ──────────────────────────────────────────────────────────
def _calcular_fila(listas, cards, membros_map):
    """
    Calcula a fila de próximas demandas pendentes ordenada por:
    1. Prioridade da coluna (10 > 9 > 8...)
    2. Peso ponderado (P7 aparece mais que P1)
    3. Data de criação (mais antigo primeiro dentro do mesmo nível)
    Retorna lista de dicts com prazo estimado em minutos a partir de agora.
    """
    agora = datetime.now(timezone.utc)

    # Filtra apenas cartões pendentes (não concluídos, não em andamento, com coluna configurada)
    pendentes = []
    for card in cards:
        nl = listas.get(card["idList"],"")
        if nl in COLUNAS_SKIP: continue
        if nl not in COLUNAS_CONFIG: continue
        ok = card.get("dueComplete", False)
        if ok: continue
        lb = _labels(card)
        if "EM ANDAMENTO" in lb: continue  # já em execução

        cfg = COLUNAS_CONFIG[nl]
        data = _data_card(card)
        us = _users(card, membros_map)
        membros_str = ", ".join(MEMBROS_ATIVOS.get(u,u) for u in us) or "—"

        pendentes.append({
            "id": card["id"],
            "nome": card["name"],
            "lista": nl,
            "prioridade": cfg["prioridade"],
            "tempo_min": cfg["tempo_min"],
            "data": data,
            "membros": membros_str,
            "labels": lb,
        })

    # Ordena: prioridade desc, depois data asc (mais antigo primeiro)
    pendentes.sort(key=lambda x: (-x["prioridade"], x["data"]))

    # Calcula prazo acumulado (posição na fila × tempo médio)
    # Considera capacidade de 2 colaboradores = 780 min/dia útil
    capacidade_total = CAPACIDADE_MIN * 2  # Myrella + Beatriz
    acumulado = 0
    for i, p in enumerate(pendentes):
        p["posicao"] = i + 1
        p["prazo_min"] = acumulado + p["tempo_min"]
        acumulado += p["tempo_min"]
        # Converte para data estimada de início
        dias = acumulado // capacidade_total
        mins_resto = acumulado % capacidade_total
        p["eta_min"] = p["prazo_min"]

    return pendentes

def _formatar_tempo(minutos):
    if minutos < 60:
        return f"{int(minutos)}min"
    h = int(minutos // 60)
    m = int(minutos % 60)
    return f"{h}h{m:02d}" if m > 0 else f"{h}h"

def _cor_urgencia(posicao, prioridade):
    if prioridade >= 10: return "#E34948"   # vermelho — crítico
    if prioridade >= 8:  return "#EDA100"   # âmbar — urgente
    if prioridade >= 6:  return "#1BAF7A"   # verde — normal
    return "#888888"                         # cinza — baixa

# ── PROCESSAMENTO ──────────────────────────────────────────────────────────────
def _processar(listas, cards, membros_map, id_p, id_t, id_interr, filtro_mes=None):
    d = {
        "pts_equipe":0.0,"pen_total":0.0,
        "pts_membro":{u:0.0 for u in MEMBROS_ATIVOS},
        "pen_membro":{u:0.0 for u in MEMBROS_ATIVOS},
        "abertos":0,"urgentes":0,"atrasados":0,
        "em_andamento":0,"falta_conf":0,"falta_info":0,
        "sem_membro":0,"falta_pts":0,
        "pts_pendentes":0.0,"pen_cards":[],
        "andamento_lista":[],"tempo_lista":{},
        "desativar":0,"reativar":0,"pend_lista":{},
    }
    for card in cards:
        nl = listas.get(card["idList"],"")
        if nl=="TABELA DE PONTUAÇÃO": continue
        lb = _labels(card)
        us = _users(card, membros_map)
        ok = card.get("dueComplete",False)
        pt = _campo_num(card, id_p)
        tempo = _campo_num(card, id_t)
        interr = _campo_num(card, id_interr) or 0
        if filtro_mes:
            mc = _mes_card(card)
            if mc and mc != filtro_mes: continue
        if nl in LISTAS_PENALIDADE:
            if pt:
                v=abs(pt); d["pen_total"]+=v
                d["pen_cards"].append({"card":card["name"],"valor":v,"membros":us})
                for u in us:
                    if u in d["pen_membro"]: d["pen_membro"][u]+=v
            continue
        if "EM ANDAMENTO" in lb:
            d["em_andamento"]+=1
            d["andamento_lista"].append({"card":card["name"],"lista":nl,"membros":us})
        if ok and tempo and tempo>0:
            tl=max(tempo-interr,0)
            d["tempo_lista"].setdefault(nl,[]).append(tl)
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
        if not ok or pt is None: continue
        if nl in LISTAS_SEM_PONTUACAO: continue
        d["pts_equipe"]+=pt
        ma=[u for u in us if u in MEMBROS_ATIVOS]
        if ma:
            cada=pt/len(ma)
            for u in ma: d["pts_membro"][u]+=cada
    return d

# ── CSS ────────────────────────────────────────────────────────────────────────
CSS = """
<style>
.pm-card{background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);border-radius:10px;padding:14px 16px;height:82px;display:flex;flex-direction:column;justify-content:center;}
.pm-label{font-size:10px;color:var(--ms-texto-sec);text-transform:uppercase;letter-spacing:.6px;margin-bottom:4px;}
.pm-value{font-size:26px;font-weight:700;line-height:1.1;}
.pm-sub{font-size:10px;color:var(--ms-texto-sec);margin-top:3px;}
.pm-status-card{background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);border-radius:10px;padding:10px;text-align:center;height:85px;display:flex;flex-direction:column;justify-content:center;align-items:center;}
.pm-badge{font-size:9px;font-weight:600;padding:2px 7px;border-radius:4px;margin-top:3px;display:inline-block;}
.fila-card{background:var(--ms-metric-bg);border-left:4px solid;border-radius:0 8px 8px 0;padding:10px 14px;margin-bottom:6px;display:flex;align-items:center;gap:12px;}
.fila-pos{font-size:22px;font-weight:700;min-width:32px;text-align:center;}
.fila-info{flex:1;}
.fila-nome{font-size:13px;font-weight:600;color:var(--ms-texto);margin-bottom:2px;}
.fila-meta{font-size:10px;color:var(--ms-texto-sec);}
.fila-eta{font-size:11px;font-weight:600;min-width:60px;text-align:right;}
.vel-ind{background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);border-radius:12px;padding:12px 8px;text-align:center;}
</style>
"""

# ── VELOCÍMETRO ────────────────────────────────────────────────────────────────
def _vel_equipe(pct, meta_eq, saldo_eq, faltam, maxx_pct):
    pct_clip=min(max(pct,0),110)
    ang=math.radians(-180+min(pct_clip/100,1)*180)
    cx,cy,r=130,120,95
    px=cx+r*math.cos(ang); py=cy+r*math.sin(ang)
    cor="#1BAF7A" if pct>=100 else ("#EDA100" if pct>=50 else "#E34948")
    perim=math.pi*r; dash=min(pct_clip/100,1)*perim
    maxx_m=""
    if maxx_pct:
        ang_mx=math.radians(-180+min(maxx_pct/100,1)*180)
        mx_x=cx+(r+8)*math.cos(ang_mx); mx_y=cy+(r+8)*math.sin(ang_mx)
        mx_x2=cx+(r-8)*math.cos(ang_mx); mx_y2=cy+(r-8)*math.sin(ang_mx)
        maxx_m=f'<line x1="{mx_x:.1f}" y1="{mx_y:.1f}" x2="{mx_x2:.1f}" y2="{mx_y2:.1f}" stroke="#2A78D6" stroke-width="3.5" stroke-linecap="round"/>'
    return f"""
<div style="text-align:center;">
<svg viewBox="0 0 260 160" width="100%" style="max-width:280px;display:block;margin:0 auto;overflow:visible;">
  <path d="M25,120 A105,105 0 0 1 235,120" fill="none" stroke="var(--ms-metric-bd)" stroke-width="18" stroke-linecap="round"/>
  <path d="M25,120 A105,105 0 0 1 235,120" fill="none" stroke="{cor}" stroke-width="18" stroke-linecap="round" stroke-dasharray="{dash:.1f} {perim:.1f}"/>
  {maxx_m}
  <line x1="{cx}" y1="{cy}" x2="{px:.1f}" y2="{py:.1f}" stroke="var(--ms-texto)" stroke-width="3" stroke-linecap="round"/>
  <circle cx="{cx}" cy="{cy}" r="7" fill="var(--ms-texto)"/>
  <circle cx="{cx}" cy="{cy}" r="3" fill="var(--ms-metric-bg)"/>
  <text x="19" y="140" text-anchor="middle" font-size="9" fill="var(--ms-texto-sec)">0</text>
  <text x="241" y="140" text-anchor="middle" font-size="9" fill="var(--ms-texto-sec)">META</text>
</svg>
<div style="margin-top:2px;">
  <div style="font-size:30px;font-weight:700;color:{cor};line-height:1;">{min(pct,999):.0f}%</div>
  <div style="font-size:18px;font-weight:600;color:{cor};margin-top:2px;">{saldo_eq:,.0f} pts</div>
  <div style="font-size:11px;color:var(--ms-texto-sec);margin-top:3px;">Meta: {meta_eq:,.0f} pts</div>
  <div style="font-size:12px;font-weight:600;color:{cor};margin-top:4px;">{"🎯 META ATINGIDA!" if pct>=100 else f"Faltam {faltam:,.0f} pts"}</div>
  <div style="font-size:10px;color:var(--ms-texto-sec);text-transform:uppercase;letter-spacing:.5px;margin-top:4px;">Meta da Equipe</div>
</div></div>"""

def _vel_ind(pct, meta, saldo, nome, pen=0):
    pct_clip=min(max(pct,0),110)
    ang=math.radians(-180+min(pct_clip/100,1)*180)
    cx,cy,r=80,72,60
    px=cx+r*math.cos(ang); py=cy+r*math.sin(ang)
    cor="#1BAF7A" if pct>=100 else ("#EDA100" if pct>=50 else "#E34948")
    perim=math.pi*r; dash=min(pct_clip/100,1)*perim
    faltam=max(meta-saldo,0)
    status="🎯 Meta atingida!" if pct>=100 else ("⚡ Em progresso" if pct>=50 else "💪 Bora!")
    pen_h=f'<div style="font-size:9px;color:#E34948;margin-top:2px;">⚠ -{pen:.0f} pts penalidades</div>' if pen>0 else ""
    return f"""<div class="vel-ind">
  <div style="font-size:13px;font-weight:600;color:var(--ms-texto);margin-bottom:6px;">{nome}</div>
  <svg viewBox="0 0 160 105" width="100%" style="max-width:180px;display:block;margin:0 auto;overflow:visible;">
    <path d="M18,72 A62,62 0 0 1 142,72" fill="none" stroke="var(--ms-metric-bd)" stroke-width="12" stroke-linecap="round"/>
    <path d="M18,72 A62,62 0 0 1 142,72" fill="none" stroke="{cor}" stroke-width="12" stroke-linecap="round" stroke-dasharray="{dash:.1f} {perim:.1f}"/>
    <line x1="{cx}" y1="{cy}" x2="{px:.1f}" y2="{py:.1f}" stroke="var(--ms-texto)" stroke-width="2" stroke-linecap="round"/>
    <circle cx="{cx}" cy="{cy}" r="5" fill="var(--ms-texto)"/>
    <circle cx="{cx}" cy="{cy}" r="2" fill="var(--ms-metric-bg)"/>
  </svg>
  <div style="font-size:22px;font-weight:700;color:{cor};margin-top:2px;">{min(pct,999):.0f}%</div>
  <div style="font-size:15px;font-weight:600;color:{cor};">{saldo:,.0f} pts</div>
  <div style="font-size:10px;color:var(--ms-texto-sec);">Meta: {meta:,.0f} · Faltam: {faltam:,.0f}</div>
  <div style="font-size:11px;font-weight:500;color:{cor};margin-top:3px;">{status}</div>
  {pen_h}
</div>"""

def _card(label, valor, sub=None, cor="var(--ms-texto)", icone=""):
    s=f'<div class="pm-sub">{sub}</div>' if sub else ""
    return f"""<div class="pm-card">
  <div class="pm-label">{icone} {label}</div>
  <div class="pm-value" style="color:{cor};">{valor}</div>{s}
</div>"""

def _status_card(label, valor, badge, cor_n, cor_b_bg, cor_b_txt):
    return f"""<div class="pm-status-card">
  <div style="font-size:9px;color:var(--ms-texto-sec);text-transform:uppercase;letter-spacing:.5px;">{label}</div>
  <div style="font-size:28px;font-weight:700;color:{cor_n};line-height:1.1;margin:3px 0;">{valor}</div>
  <span class="pm-badge" style="background:{cor_b_bg};color:{cor_b_txt};">{badge}</span>
</div>"""

def _barra(nome, pts, meta, pen):
    saldo=pts-pen; pct=min(saldo/meta*100,100) if meta>0 else 0
    cor="#1BAF7A" if pct>=100 else ("#EDA100" if pct>=50 else "#E34948")
    pen_h=f'<div style="font-size:9px;color:#E34948;margin-top:2px;">⚠ -{pen:.0f} pts penalidades</div>' if pen>0 else ""
    return (f'<div style="margin-bottom:12px;">'
            f'<div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px;">'
            f'<span style="color:var(--ms-texto);font-weight:600;">{nome}</span>'
            f'<span style="color:{cor};">{saldo:,.0f} / {meta:,.0f} · {pct:.0f}%</span></div>'
            f'<div style="background:var(--ms-metric-bd);border-radius:4px;height:8px;overflow:hidden;">'
            f'<div style="background:{cor};width:{pct:.1f}%;height:100%;border-radius:4px;"></div></div>'
            f'{pen_h}</div>')

# ── BLOCO FILA ─────────────────────────────────────────────────────────────────
def _render_fila(fila, n=4, titulo="📋 Próximas Demandas na Fila"):
    st.markdown(f"**{titulo}**")
    if not fila:
        st.markdown('<div style="color:var(--ms-texto-sec);font-size:12px;padding:8px 0;">Nenhuma demanda pendente na fila 🎉</div>', unsafe_allow_html=True)
        return
    for item in fila[:n]:
        cor=_cor_urgencia(item["posicao"], item["prioridade"])
        eta=_formatar_tempo(item["eta_min"])
        lista_curta=item["lista"][:30]+"..." if len(item["lista"])>30 else item["lista"]
        nome_curto=item["nome"][:45]+"..." if len(item["nome"])>45 else item["nome"]
        p_label = f"P{item['prioridade']}"
        st.markdown(f"""<div class="fila-card" style="border-left-color:{cor};">
  <div class="fila-pos" style="color:{cor};">{item['posicao']}°</div>
  <div class="fila-info">
    <div class="fila-nome">{nome_curto}</div>
    <div class="fila-meta">{lista_curta} · {item['membros']} · {p_label}</div>
  </div>
  <div class="fila-eta" style="color:{cor};">~{eta}</div>
</div>""", unsafe_allow_html=True)

def _cor_urgencia(posicao, prioridade):
    if prioridade >= 10: return "#E34948"
    if prioridade >= 8:  return "#EDA100"
    if prioridade >= 6:  return "#1BAF7A"
    return "#888888"

def _formatar_tempo(minutos):
    if minutos < 60: return f"{int(minutos)}min"
    h=int(minutos//60); m=int(minutos%60)
    return f"{h}h{m:02d}" if m>0 else f"{h}h"

# ── MODO TV ────────────────────────────────────────────────────────────────────
def _render_tv(saldo_eq, meta_eq, pct_eq, faltam, maxx_pct, meta_maxx_pts, d, fila, agora, sel):
    """Versão simplificada para TV — sem login, atualiza sozinha."""
    st.markdown("""
<style>
body { overflow: hidden; }
.tv-title { font-size: 28px; font-weight: 700; color: var(--ms-texto); margin-bottom: 4px; }
.tv-sub { font-size: 13px; color: var(--ms-texto-sec); margin-bottom: 16px; }
</style>
""", unsafe_allow_html=True)

    # Auto-refresh a cada 60s
    st.markdown("""<script>setTimeout(()=>window.location.reload(), 60000);</script>""", unsafe_allow_html=True)

    st.markdown(f'<div class="tv-title">🏆 Painel de Meta — {sel}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="tv-sub">Atualizado: {agora.strftime("%d/%m/%Y %H:%M")}</div>', unsafe_allow_html=True)

    col_vel, col_status, col_fila = st.columns([2, 3, 2])

    with col_vel:
        st.markdown(_vel_equipe(pct_eq, meta_eq, saldo_eq, faltam, maxx_pct), unsafe_allow_html=True)

    with col_status:
        st.markdown("**Status dos Cartões**")
        r1=st.columns(3)
        r2=st.columns(3)
        cor_pts="#1BAF7A" if pct_eq>=100 else ("#EDA100" if pct_eq>=50 else "#E34948")
        r1[0].markdown(_card("Pontuação",f"{saldo_eq:,.0f}",f"Meta: {meta_eq:,.0f}",cor=cor_pts,icone="🏆"),unsafe_allow_html=True)
        r1[1].markdown(_card("Em Aberto",d["abertos"],icone="📋"),unsafe_allow_html=True)
        r1[2].markdown(_card("Urgentes",d["urgentes"],icone="🚨",cor="#E34948" if d["urgentes"]>0 else "var(--ms-texto)"),unsafe_allow_html=True)
        r2[0].markdown(_card("Desativar",d["desativar"],icone="⚠️",cor="#E34948" if d["desativar"]>0 else "var(--ms-texto)"),unsafe_allow_html=True)
        r2[1].markdown(_card("Penalidades",f"-{d['pen_total']:.0f}",icone="⚡",cor="#E34948" if d["pen_total"]>0 else "var(--ms-texto)"),unsafe_allow_html=True)
        r2[2].markdown(_card("Sem Membro",d["sem_membro"],icone="👤",cor="#EDA100" if d["sem_membro"]>0 else "var(--ms-texto)"),unsafe_allow_html=True)

        # Em andamento agora
        st.markdown("<div style='margin-top:10px'></div>",unsafe_allow_html=True)
        if d["andamento_lista"]:
            for c in d["andamento_lista"][:3]:
                ms=", ".join(MEMBROS_ATIVOS.get(u,u) for u in c["membros"]) or "—"
                st.markdown(f"""<div style="background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);border-radius:8px;padding:7px 12px;margin-bottom:4px;">
                  <div style="font-size:12px;font-weight:600;color:var(--ms-texto);">▶ {c['card'][:45]}</div>
                  <div style="font-size:10px;color:var(--ms-texto-sec);">{c['lista'][:30]} · <span style="color:#1BAF7A;">{ms}</span></div>
                </div>""",unsafe_allow_html=True)

    with col_fila:
        _render_fila(fila, n=4)

# ── PÁGINA PRINCIPAL ───────────────────────────────────────────────────────────
def pagina_placar(usuario_logado):
    eh_master = usuario_logado.lower() in {m.lower() for m in MASTERS}
    eh_membro = usuario_logado in MEMBROS_ATIVOS

    if not TRELLO_KEY:
        st.error("Credenciais do Trello não configuradas.")
        return

    st.markdown(CSS, unsafe_allow_html=True)
    agora = datetime.now()

    # Detecta modo TV via query param
    params = st.query_params
    modo_tv = params.get("tv","") == "1"

    # Cabeçalho
    col_tit, col_mes, col_att = st.columns([3,2,1])
    with col_tit:
        st.markdown("### 🏆 Painel de Meta" + (" 📺" if modo_tv else ""))
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

    st.caption(f"Exibindo: {sel} · atualiza a cada 60s · {agora.strftime('%d/%m/%Y %H:%M')}")

    # Metas
    k_eq=f"meta_eq_{filtro_mes[0]}_{filtro_mes[1]}"
    k_ind=f"meta_ind_{filtro_mes[0]}_{filtro_mes[1]}"
    k_mx=f"meta_maxx_{filtro_mes[0]}_{filtro_mes[1]}"
    if k_eq not in st.session_state: st.session_state[k_eq]=5000
    if k_ind not in st.session_state: st.session_state[k_ind]=1500
    if k_mx not in st.session_state: st.session_state[k_mx]=130

    with st.expander(f"⚙️ Configurar Metas — {sel}",expanded=False):
        if eh_master:
            c1,c2,c3=st.columns(3)
            st.session_state[k_eq]=c1.number_input("Meta equipe (pts)",min_value=0,value=st.session_state[k_eq],step=100)
            st.session_state[k_ind]=c2.number_input("Meta individual (pts)",min_value=0,value=st.session_state[k_ind],step=100)
            st.session_state[k_mx]=c3.number_input("Meta Maxx (%)",min_value=100,max_value=300,value=st.session_state[k_mx],step=5)
        else:
            st.info("Metas configuradas pelo gestor.")

    meta_eq=st.session_state[k_eq]
    meta_ind=st.session_state[k_ind]
    maxx_pct=st.session_state[k_mx]
    meta_maxx_pts=meta_eq*maxx_pct/100

    # Dados
    with st.spinner(""):
        dados_api=_buscar_board()
    if not dados_api or not dados_api[0]:
        st.error("Não foi possível conectar ao Trello."); return

    listas,cards,membros_map,id_p,id_t,id_interr=dados_api
    d=_processar(listas,cards,membros_map,id_p,id_t,id_interr,filtro_mes)
    fila=_calcular_fila(listas,cards,membros_map)

    saldo_eq=d["pts_equipe"]-d["pen_total"]
    pct_eq=(saldo_eq/meta_eq*100) if meta_eq>0 else 0
    faltam=max(meta_eq-saldo_eq,0)
    faltam_maxx=max(meta_maxx_pts-saldo_eq,0)
    cor_pts="#1BAF7A" if pct_eq>=100 else ("#EDA100" if pct_eq>=50 else "#E34948")

    # ── MODO TV ──
    if modo_tv:
        _render_tv(saldo_eq,meta_eq,pct_eq,faltam,maxx_pct,meta_maxx_pts,d,fila,agora,sel)
        return

    # ══ BLOCO 1 — VELOCÍMETRO + CARDS ══
    col_vel,col_cards=st.columns([2,3])
    with col_vel:
        st.markdown(_vel_equipe(pct_eq,meta_eq,saldo_eq,faltam,maxx_pct),unsafe_allow_html=True)
    with col_cards:
        r1=st.columns(3); r2=st.columns(3)
        r1[0].markdown(_card("Meta",f"{meta_eq:,}","pts/mês"),unsafe_allow_html=True)
        r1[1].markdown(_card("Pontuação Atual",f"{saldo_eq:,.0f}",f"{pct_eq:.0f}% da meta",cor=cor_pts,icone="🏆"),unsafe_allow_html=True)
        r1[2].markdown(_card("Faltam para Meta",f"{faltam:,.0f}","pts restantes",cor="#EDA100" if faltam>0 else "#1BAF7A"),unsafe_allow_html=True)
        r2[0].markdown(_card("Pts em Aberto",f"{d['pts_pendentes']:,.0f}","cartões pendentes",cor="#EDA100",icone="🟠"),unsafe_allow_html=True)
        r2[1].markdown(_card("Meta Maxx",f"{meta_maxx_pts:,.0f}",f"{maxx_pct}% da meta",cor="#2A78D6"),unsafe_allow_html=True)
        r2[2].markdown(_card("Faltam p/ Maxx",f"{faltam_maxx:,.0f}","pts para bônus",cor="#2A78D6" if faltam_maxx>0 else "#1BAF7A"),unsafe_allow_html=True)

    # ══ BLOCO 2 — STATUS ══
    st.markdown('<hr style="border:none;border-top:1px solid var(--ms-divisor);margin:12px 0 8px 0;"/>',unsafe_allow_html=True)
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
        with cols_st[i]:
            st.markdown(_status_card(lbl,val,badge,cn,bb,bt),unsafe_allow_html=True)

    # ══ BLOCO 3 — EM ANDAMENTO + FILA + DESEMPENHO ══
    st.markdown('<hr style="border:none;border-top:1px solid var(--ms-divisor);margin:12px 0 8px 0;"/>',unsafe_allow_html=True)
    col_and, col_fila_bloco, col_colab = st.columns([3,3,3])

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

    with col_fila_bloco:
        _render_fila(fila, n=4)

    with col_colab:
        if eh_master:
            st.markdown("**👥 Desempenho por Colaborador**")
            barras=""
            for u,nome in MEMBROS_ATIVOS.items():
                pts=d["pts_membro"].get(u,0); pen=d["pen_membro"].get(u,0)
                barras+=_barra(nome,pts,meta_ind,pen)
            st.markdown(f'<div style="padding:4px 0">{barras}</div>',unsafe_allow_html=True)
        elif eh_membro:
            st.markdown("**Seu Desempenho**")
            pts=d["pts_membro"].get(usuario_logado,0); pen=d["pen_membro"].get(usuario_logado,0)
            st.markdown(_barra(MEMBROS_ATIVOS.get(usuario_logado,usuario_logado),pts,meta_ind,pen),unsafe_allow_html=True)

    # ══ BLOCO 4 — METAS INDIVIDUAIS ══
    st.markdown('<hr style="border:none;border-top:1px solid var(--ms-divisor);margin:12px 0 8px 0;"/>',unsafe_allow_html=True)
    st.markdown("**🎯 Metas Individuais**")
    if eh_master:
        cols_ind=st.columns(len(MEMBROS_ATIVOS))
        for i,(u,nome) in enumerate(MEMBROS_ATIVOS.items()):
            pts=d["pts_membro"].get(u,0); pen=d["pen_membro"].get(u,0)
            saldo_i=pts-pen; pct_i=(saldo_i/meta_ind*100) if meta_ind>0 else 0
            with cols_ind[i]:
                st.markdown(_vel_ind(pct_i,meta_ind,saldo_i,nome,pen),unsafe_allow_html=True)
    elif eh_membro:
        pts=d["pts_membro"].get(usuario_logado,0); pen=d["pen_membro"].get(usuario_logado,0)
        saldo_i=pts-pen; pct_i=(saldo_i/meta_ind*100) if meta_ind>0 else 0
        nome=MEMBROS_ATIVOS.get(usuario_logado,usuario_logado)
        col_v,col_b=st.columns([1,2])
        with col_v:
            st.markdown(_vel_ind(pct_i,meta_ind,saldo_i,nome,pen),unsafe_allow_html=True)
        with col_b:
            st.markdown(_barra(nome,pts,meta_ind,pen),unsafe_allow_html=True)

    # ══ BLOCO 5 — TEMPO MÉDIO + PENDENTES ══
    st.markdown('<hr style="border:none;border-top:1px solid var(--ms-divisor);margin:12px 0 8px 0;"/>',unsafe_allow_html=True)
    col_pend, col_tempo = st.columns(2)

    with col_pend:
        st.markdown("**🟠 Pendentes por Coluna**")
        if d["pend_lista"]:
            max_q=max(d["pend_lista"].values())
            for nl,qtd in sorted(d["pend_lista"].items(),key=lambda x:-x[1]):
                pct_b=qtd/max_q*100
                st.markdown(f"""<div style="margin-bottom:8px;">
                  <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--ms-texto);margin-bottom:3px;">
                    <span>{nl[:40]}</span><span style="font-weight:700;">{qtd}</span></div>
                  <div style="background:var(--ms-metric-bd);border-radius:4px;height:6px;">
                    <div style="background:#EDA100;width:{pct_b:.0f}%;height:100%;border-radius:4px;"></div>
                  </div></div>""",unsafe_allow_html=True)
        else:
            st.caption("Nenhum cartão pendente 🎉")

    with col_tempo:
        st.markdown("**⏱️ Tempo Médio por Coluna**")
        listas_t=[nl for nl in set(listas.values()) if nl not in LISTAS_PENALIDADE and nl!="TABELA DE PONTUAÇÃO" and nl not in LISTAS_SEM_PONTUACAO]
        cols_t=st.columns(2)
        for i,nl in enumerate(sorted(listas_t)[:12]):
            tempos=d["tempo_lista"].get(nl,[])
            if tempos:
                media=sum(tempos)/len(tempos)
                val=f"{media:.0f} min"; sub=f"{len(tempos)} demandas"; cor="var(--ms-texto)"
            else:
                val="— min"; sub="sem dados"; cor="var(--ms-texto-sec)"
            with cols_t[i%2]:
                st.markdown(f"""<div style="background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);border-radius:8px;padding:8px 10px;margin-bottom:6px;">
                  <div style="font-size:9px;color:var(--ms-texto-sec);text-transform:uppercase;margin-bottom:2px;">{nl[:24]}</div>
                  <div style="font-size:16px;font-weight:700;color:{cor};">{val}</div>
                  <div style="font-size:9px;color:var(--ms-texto-sec);">{sub}</div>
                </div>""",unsafe_allow_html=True)

    # Penalidades (master)
    if eh_master and d["pen_cards"]:
        st.markdown('<hr style="border:none;border-top:1px solid var(--ms-divisor);margin:12px 0 8px 0;"/>',unsafe_allow_html=True)
        st.markdown("**⚠️ Penalidades Registradas**")
        for p in d["pen_cards"]:
            ms=", ".join(MEMBROS_ATIVOS.get(u,u) for u in p["membros"]) or "Sem membro"
            st.markdown(f"""<div style="background:var(--ms-metric-bg);border:1px solid #E34948;border-radius:8px;padding:10px 14px;margin-bottom:6px;">
              <div style="display:flex;justify-content:space-between;">
                <span style="font-size:12px;font-weight:600;color:var(--ms-texto);">{p['card'][:55]}</span>
                <span style="font-size:13px;font-weight:700;color:#E34948;">-{p['valor']:.0f} pts</span>
              </div>
              <div style="font-size:10px;color:var(--ms-texto-sec);margin-top:2px;">{ms}</div>
            </div>""",unsafe_allow_html=True)

    # Link TV
    st.markdown('<hr style="border:none;border-top:1px solid var(--ms-divisor);margin:12px 0 4px 0;"/>',unsafe_allow_html=True)
    base_url=st.secrets.get("base_url","") if hasattr(st,"secrets") else ""
    if base_url:
        tv_url=f"{base_url}/?tv=1"
        st.markdown(f'📺 **Link para TV:** <a href="{tv_url}" target="_blank">{tv_url}</a>',unsafe_allow_html=True)
    else:
        st.caption(f"📺 Para TV: acesse a URL do site e adicione **?tv=1** no final")

    st.caption(f"Dados do Trello · {sel} · {agora.strftime('%d/%m/%Y %H:%M')}")
