"""
placar.py — Painel de Meta · MS Studio
"""
import streamlit as st
import requests
from datetime import datetime
import math
import base64, os

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
    id_i = next((c["id"] for c in campos if "INÍCIO PARCIAL" in c.get("name","").upper() or "INICIO" in c.get("name","").upper()),None)
    id_t = next((c["id"] for c in campos if "TEMPO ACUMULADO" in c.get("name","").upper() or "TEMPO" in c.get("name","").upper()),None)
    id_interr = next((c["id"] for c in campos if "INTERROMPIDO" in c.get("name","").upper()),None)
    return listas, cards, membros_map, id_p, id_i, id_t, id_interr

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
    d = card.get("dateLastActivity") or card.get("due") or ""
    if d:
        try:
            dt = datetime.fromisoformat(d.replace("Z","+00:00"))
            return (dt.year, dt.month)
        except: pass
    return None

def _processar(listas, cards, membros_map, id_p, id_i, id_t, id_interr, filtro_mes=None):
    r = {
        "pts_membro":    {u:0.0 for u in MEMBROS_ATIVOS},
        "pts_equipe":    0.0,
        "pen_membro":    {u:0.0 for u in MEMBROS_ATIVOS},
        "pen_total":     0.0,
        "abertos":       0, "urgentes":0, "atrasados":0,
        "em_andamento":  0, "falta_conf":0, "falta_info":0, "sem_membro":0,
        "pts_pendentes": 0.0,
        "pend_lista":    {},
        "pen_cards":     [],
        "andamento_lista":[],
        "tempo_por_lista": {},  # {nome_lista: [minutos, ...]}
    }

    for card in cards:
        nl = listas.get(card["idList"],"")
        if nl == "TABELA DE PONTUAÇÃO": continue
        lb = _labels(card)
        us = _users(card, membros_map)
        ok = card.get("dueComplete", False)
        pt = _campo_num(card, id_p)
        tempo_acum = _campo_num(card, id_t)
        interr = _campo_num(card, id_interr) or 0

        if filtro_mes:
            mc = _mes_card(card)
            if mc and mc != filtro_mes: continue

        # Penalidades
        if nl in LISTAS_PENALIDADE:
            if pt is not None:
                v = abs(pt)
                r["pen_total"] += v
                r["pen_cards"].append({"card":card["name"],"valor":v,"membros":us})
                for u in us:
                    if u in r["pen_membro"]: r["pen_membro"][u] += v
            continue

        # Em andamento
        if "EM ANDAMENTO" in lb:
            r["em_andamento"] += 1
            r["andamento_lista"].append({"card":card["name"],"lista":nl,"membros":us})

        # Tempo médio por lista (apenas concluídos com tempo registrado)
        if ok and tempo_acum and tempo_acum > 0:
            tempo_liquido = max(tempo_acum - interr, 0)
            if nl not in r["tempo_por_lista"]:
                r["tempo_por_lista"][nl] = []
            r["tempo_por_lista"][nl].append(tempo_liquido)

        # Contadores abertos
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

        # Pontuação
        if not ok or pt is None: continue
        if nl in LISTAS_SEM_PONTUACAO: continue
        r["pts_equipe"] += pt
        ma = [u for u in us if u in MEMBROS_ATIVOS]
        if ma:
            cada = pt/len(ma)
            for u in ma: r["pts_membro"][u] += cada

    return r

# ── COMPONENTES ────────────────────────────────────────────────────────────────
def _velocimetro_equipe(pct, meta_pts, atual_pts, faltam, pct_maxx=None):
    pct_clip = min(max(pct,0),110)
    ang = math.radians(-180 + min(pct_clip/100,1)*180)
    cx, cy, r = 130, 120, 95
    px = cx + r*math.cos(ang)
    py = cy + r*math.sin(ang)
    cor = "#1baf7a" if pct>=100 else ("#eda100" if pct>=50 else "#e34948")
    perim = math.pi*r
    dash = min(pct_clip/100,1)*perim

    maxx_mark = ""
    if pct_maxx:
        ang_mx = math.radians(-180 + min(pct_maxx/100,1)*180)
        mx_x  = cx+(r+8)*math.cos(ang_mx)
        mx_y  = cy+(r+8)*math.sin(ang_mx)
        mx_x2 = cx+(r-8)*math.cos(ang_mx)
        mx_y2 = cy+(r-8)*math.sin(ang_mx)
        maxx_mark = f'<line x1="{mx_x:.1f}" y1="{mx_y:.1f}" x2="{mx_x2:.1f}" y2="{mx_y2:.1f}" stroke="#FFD700" stroke-width="3.5" stroke-linecap="round"/>'

    return f"""
<div style="text-align:center;">
<svg viewBox="0 0 260 160" width="100%" style="max-width:300px;display:block;margin:0 auto;overflow:visible;">
  <path d="M25,120 A105,105 0 0 1 235,120" fill="none" stroke="#2c2c2a" stroke-width="18" stroke-linecap="round"/>
  <path d="M25,120 A105,105 0 0 1 235,120" fill="none" stroke="{cor}" stroke-width="18" stroke-linecap="round"
        stroke-dasharray="{dash:.1f} {perim:.1f}"/>
  {maxx_mark}
  <line x1="{cx}" y1="{cy}" x2="{px:.1f}" y2="{py:.1f}" stroke="#e0e0e0" stroke-width="3" stroke-linecap="round"/>
  <circle cx="{cx}" cy="{cy}" r="7" fill="#e0e0e0"/>
  <circle cx="{cx}" cy="{cy}" r="3" fill="#3c3c3c"/>
  <text x="19" y="138" text-anchor="middle" font-size="9" fill="#888">0</text>
  <text x="241" y="138" text-anchor="middle" font-size="9" fill="#888">META</text>
</svg>
<div style="margin-top:2px;">
  <div style="font-size:32px;font-weight:700;color:{cor};line-height:1;">{min(pct,999):.0f}%</div>
  <div style="font-size:20px;font-weight:600;color:{cor};margin-top:2px;">{atual_pts:.0f} pts</div>
  <div style="font-size:11px;color:var(--ms-texto-sec);margin-top:3px;">Meta: {meta_pts:.0f} pts</div>
  <div style="font-size:12px;font-weight:600;color:{cor};margin-top:4px;">
    {"🎯 META ATINGIDA!" if pct>=100 else f"Faltam {faltam:.0f} pts"}
  </div>
  {"" if not pct_maxx else f'<div style="font-size:10px;color:#FFD700;margin-top:2px;">▲ Meta Maxx: {pct_maxx:.0f}%</div>'}
  <div style="font-size:10px;color:var(--ms-texto-sec);text-transform:uppercase;letter-spacing:.5px;margin-top:4px;">Meta da Equipe</div>
</div>
</div>"""

def _velocimetro_ind(pct, meta_pts, atual_pts, nome, pen=0):
    pct_clip = min(max(pct,0),110)
    ang = math.radians(-180 + min(pct_clip/100,1)*180)
    cx,cy,r = 80,72,60
    px = cx+r*math.cos(ang)
    py = cy+r*math.sin(ang)
    cor = "#1baf7a" if pct>=100 else ("#eda100" if pct>=50 else "#e34948")
    perim = math.pi*r
    dash = min(pct_clip/100,1)*perim
    faltam = max(meta_pts-atual_pts,0)
    pen_h = f'<div style="font-size:10px;color:#e34948;margin-top:2px;">⚠ -{pen:.0f} pts penalidades</div>' if pen>0 else ""
    status = "🎯 Meta atingida!" if pct>=100 else ("⚡ Em progresso" if pct>=50 else "💪 Bora!")
    return f"""
<div style="background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);border-radius:12px;
     padding:14px 10px;text-align:center;height:100%">
  <div style="font-size:13px;font-weight:600;color:var(--ms-texto);margin-bottom:6px;">{nome}</div>
  <svg viewBox="0 0 160 105" width="100%" style="max-width:180px;display:block;margin:0 auto;overflow:visible;">
    <path d="M18,72 A62,62 0 0 1 142,72" fill="none" stroke="#2c2c2a" stroke-width="12" stroke-linecap="round"/>
    <path d="M18,72 A62,62 0 0 1 142,72" fill="none" stroke="{cor}" stroke-width="12" stroke-linecap="round"
          stroke-dasharray="{dash:.1f} {perim:.1f}"/>
    <line x1="{cx}" y1="{cy}" x2="{px:.1f}" y2="{py:.1f}" stroke="#e0e0e0" stroke-width="2" stroke-linecap="round"/>
    <circle cx="{cx}" cy="{cy}" r="5" fill="#e0e0e0"/>
    <circle cx="{cx}" cy="{cy}" r="2" fill="#3c3c3c"/>
  </svg>
  <div style="font-size:22px;font-weight:700;color:{cor};margin-top:2px;">{min(pct,999):.0f}%</div>
  <div style="font-size:15px;font-weight:600;color:{cor};">{atual_pts:.0f} pts</div>
  <div style="font-size:10px;color:var(--ms-texto-sec);">Meta: {meta_pts:.0f} · Faltam: {faltam:.0f}</div>
  <div style="font-size:11px;font-weight:500;color:{cor};margin-top:3px;">{status}</div>
  {pen_h}
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
    saldo = pts-pen
    pct = min(saldo/meta*100,100) if meta>0 else 0
    cor = "#1baf7a" if pct>=100 else ("#eda100" if pct>=50 else "#e34948")
    pen_h = f'<div style="font-size:10px;color:#e34948;margin-top:2px;">⚠ -{pen:.0f} pts em penalidades</div>' if pen>0 else ""
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
        return

    agora = datetime.now()

    # Cabeçalho
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

    # Metas
    k_eq  = f"meta_eq_{filtro_mes[0]}_{filtro_mes[1]}"
    k_ind = f"meta_ind_{filtro_mes[0]}_{filtro_mes[1]}"
    k_mx  = f"meta_maxx_{filtro_mes[0]}_{filtro_mes[1]}"

    with st.expander(f"⚙️ Configurar Metas — {sel}", expanded=False):
        if eh_master:
            c1,c2,c3 = st.columns(3)
            meta_eq  = c1.number_input("Meta equipe (pts)", min_value=0, value=st.session_state.get(k_eq,5000), step=100, key=k_eq)
            meta_ind = c2.number_input("Meta individual (pts)", min_value=0, value=st.session_state.get(k_ind,1500), step=100, key=k_ind)
            maxx_pct = c3.number_input("Meta Maxx (%)", min_value=100, max_value=300, value=st.session_state.get(k_mx,130), step=5, key=k_mx)
        else:
            meta_eq  = st.session_state.get(k_eq,5000)
            meta_ind = st.session_state.get(k_ind,1500)
            maxx_pct = st.session_state.get(k_mx,130)
            st.info("Metas configuradas pelo gestor.")

    meta_eq  = st.session_state.get(k_eq,5000)
    meta_ind = st.session_state.get(k_ind,1500)
    maxx_pct = st.session_state.get(k_mx,130)
    meta_maxx_pts = meta_eq * maxx_pct / 100

    # Dados
    with st.spinner("Buscando dados do Trello..."):
        dados_api = _buscar_board()
    if not dados_api or not dados_api[0]:
        st.error("Não foi possível conectar ao Trello.")
        return

    listas, cards, membros_map, id_p, id_i, id_t, id_interr = dados_api
    d = _processar(listas, cards, membros_map, id_p, id_i, id_t, id_interr, filtro_mes)

    pts_eq   = d["pts_equipe"]
    pen_tot  = d["pen_total"]
    saldo_eq = pts_eq - pen_tot
    pct_eq   = (saldo_eq/meta_eq*100) if meta_eq>0 else 0
    faltam   = max(meta_eq-saldo_eq, 0)

    estado_capi = "maxx" if saldo_eq>=meta_maxx_pts else ("meta" if saldo_eq>=meta_eq else "treino")
    estado_emoji = "🏋️" if estado_capi=="treino" else ("🎉" if estado_capi=="meta" else "🕺")

    # ══ BLOCO 1 — MASCOTE + VELOCÍMETRO + CARDS ══
    col_capi, col_vel, col_cards = st.columns([1,2,3])

    with col_capi:
        st.markdown(f"""<div style="display:flex;align-items:center;justify-content:center;
            height:260px;background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);
            border-radius:12px;font-size:90px;">{estado_emoji}</div>""", unsafe_allow_html=True)

    with col_vel:
        st.markdown(_velocimetro_equipe(pct_eq, meta_eq, saldo_eq, faltam, maxx_pct), unsafe_allow_html=True)

    with col_cards:
        r1 = st.columns(3)
        r2 = st.columns(3)
        cor_pts = "#1baf7a" if pct_eq>=100 else ("#eda100" if pct_eq>=50 else "#e34948")
        r1[0].markdown(_card("Pontuação Atual", f"{saldo_eq:.0f}", f"Meta: {meta_eq} · Faltam: {faltam:.0f}", cor=cor_pts, icone="🏆"), unsafe_allow_html=True)
        r1[1].markdown(_card("Cartões em Aberto", d["abertos"], icone="📋"), unsafe_allow_html=True)
        r1[2].markdown(_card("Penalidades", f"-{pen_tot:.0f}", f"{len(d['pen_cards'])} ocorrências", cor="#e34948" if pen_tot>0 else "var(--ms-texto)", icone="⚠️"), unsafe_allow_html=True)
        r2[0].markdown(_card("Pts em Aberto", f"{d['pts_pendentes']:.0f}", "Cartões pendentes", cor="#eda100", icone="🟠"), unsafe_allow_html=True)
        r2[1].markdown(_card("Urgentes", d["urgentes"], icone="🚨", cor="#e34948" if d["urgentes"]>0 else "var(--ms-texto)"), unsafe_allow_html=True)
        r2[2].markdown(_card("Sem Membro", d["sem_membro"], icone="👤", cor="#eda100" if d["sem_membro"]>0 else "var(--ms-texto)"), unsafe_allow_html=True)

    # ══ BLOCO 2 — STATUS + COLABORADORES ══
    st.markdown("---")
    col_status, col_colab = st.columns(2)

    with col_status:
        st.markdown("#### 📊 Status dos Cartões")
        s1,s2,s3,s4 = st.columns(4)
        s1.markdown(_card("Atrasados", d["atrasados"], icone="⏰", cor="#e34948" if d["atrasados"]>0 else "var(--ms-texto)"), unsafe_allow_html=True)
        s2.markdown(_card("Em Andamento", d["em_andamento"], icone="▶️"), unsafe_allow_html=True)
        s3.markdown(_card("Falta Conferir", d["falta_conf"], icone="🔍"), unsafe_allow_html=True)
        s4.markdown(_card("Falta Info", d["falta_info"], icone="❓"), unsafe_allow_html=True)

        if d["andamento_lista"]:
            st.markdown("<div style='margin-top:10px'></div>", unsafe_allow_html=True)
            st.markdown("**▶️ Em Andamento Agora**")
            for c in d["andamento_lista"][:4]:
                ms = ", ".join(MEMBROS_ATIVOS.get(u,u) for u in c["membros"]) or "—"
                st.markdown(f"""<div style="background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);
                    border-radius:8px;padding:8px 12px;margin-bottom:5px;">
                    <div style="font-size:12px;font-weight:600;color:var(--ms-texto);">{c['card'][:48]}</div>
                    <div style="font-size:10px;color:var(--ms-texto-sec);margin-top:1px;">{c['lista'][:35]} · {ms}</div>
                </div>""", unsafe_allow_html=True)

    with col_colab:
        if eh_master:
            st.markdown("#### 👥 Desempenho por Colaborador")
            if any(d["pts_membro"].get(u,0) > 0 for u in MEMBROS_ATIVOS):
                barras = "".join(_barra(MEMBROS_ATIVOS[u], d["pts_membro"].get(u,0), meta_ind, d["pen_membro"].get(u,0)) for u in MEMBROS_ATIVOS)
                st.markdown(f'<div style="padding:4px 0">{barras}</div>', unsafe_allow_html=True)
            else:
                for nome in MEMBROS_ATIVOS.values():
                    st.markdown(_barra(nome, 0, meta_ind, 0), unsafe_allow_html=True)
        elif eh_membro:
            st.markdown("#### Seu Desempenho")
            pts = d["pts_membro"].get(usuario_logado,0)
            pen = d["pen_membro"].get(usuario_logado,0)
            st.markdown(_barra(MEMBROS_ATIVOS.get(usuario_logado,usuario_logado), pts, meta_ind, pen), unsafe_allow_html=True)

    # ══ BLOCO 3 — METAS INDIVIDUAIS ══
    st.markdown("---")
    st.markdown("#### 🎯 Metas Individuais")
    if eh_master:
        cols_ind = st.columns(len(MEMBROS_ATIVOS))
        for i, (username, nome) in enumerate(MEMBROS_ATIVOS.items()):
            pts  = d["pts_membro"].get(username,0)
            pen  = d["pen_membro"].get(username,0)
            saldo_i = pts-pen
            pct_i = (saldo_i/meta_ind*100) if meta_ind>0 else 0
            with cols_ind[i]:
                st.markdown(_velocimetro_ind(pct_i, meta_ind, saldo_i, nome, pen), unsafe_allow_html=True)
    elif eh_membro:
        pts = d["pts_membro"].get(usuario_logado,0)
        pen = d["pen_membro"].get(usuario_logado,0)
        saldo_i = pts-pen
        pct_i = (saldo_i/meta_ind*100) if meta_ind>0 else 0
        nome = MEMBROS_ATIVOS.get(usuario_logado,usuario_logado)
        col_v, col_b = st.columns([1,2])
        with col_v:
            st.markdown(_velocimetro_ind(pct_i, meta_ind, saldo_i, nome, pen), unsafe_allow_html=True)
        with col_b:
            st.markdown(_barra(nome, pts, meta_ind, pen), unsafe_allow_html=True)

    # ══ BLOCO 4 — TEMPO MÉDIO POR COLUNA ══
    st.markdown("---")
    st.markdown("#### ⏱️ Tempo Médio de Execução por Coluna")

    # Todas as listas do board
    todas_listas = [nl for nl in set(listas.values())
                    if nl not in LISTAS_PENALIDADE
                    and nl != "TABELA DE PONTUAÇÃO"
                    and nl not in LISTAS_SEM_PONTUACAO]
    todas_listas.sort()

    if todas_listas:
        cols_tempo = st.columns(3)
        for i, nl in enumerate(todas_listas):
            tempos = d["tempo_por_lista"].get(nl, [])
            if tempos:
                media = sum(tempos)/len(tempos)
                valor = f"{media:.0f} min"
                sub = f"{len(tempos)} demandas concluídas"
                cor = "var(--ms-texto)"
            else:
                valor = "— min"
                sub = "Sem dados ainda"
                cor = "var(--ms-texto-sec)"
            with cols_tempo[i % 3]:
                st.markdown(_card(nl[:28], valor, sub, cor=cor, icone="⏱️"), unsafe_allow_html=True)
    else:
        st.caption("Nenhuma coluna encontrada.")

    # ══ BLOCO 5 — PENDENTES + PENALIDADES ══
    st.markdown("---")
    col_pend, col_pen = st.columns(2)

    with col_pend:
        st.markdown("#### 🟠 Pendentes por Coluna")
        if d["pend_lista"]:
            max_q = max(d["pend_lista"].values())
            for nl, qtd in sorted(d["pend_lista"].items(), key=lambda x:-x[1]):
                pct_b = qtd/max_q*100
                st.markdown(f"""<div style="margin-bottom:9px;">
                  <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--ms-texto);margin-bottom:3px;">
                    <span>{nl[:40]}</span><span style="font-weight:700;">{qtd}</span>
                  </div>
                  <div style="background:var(--ms-metric-bd);border-radius:4px;height:6px;">
                    <div style="background:#eda100;width:{pct_b:.0f}%;height:100%;border-radius:4px;"></div>
                  </div></div>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div style="background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);
                border-radius:10px;padding:20px;text-align:center;color:var(--ms-texto-sec);font-size:13px;">
                Nenhum cartão pendente 🎉</div>""", unsafe_allow_html=True)

    with col_pen:
        if eh_master:
            st.markdown("#### ⚠️ Penalidades Registradas")
            if d["pen_cards"]:
                for p in d["pen_cards"]:
                    ms = ", ".join(MEMBROS_ATIVOS.get(u,u) for u in p["membros"]) or "Sem membro"
                    st.markdown(f"""<div style="background:var(--ms-metric-bg);border:1px solid #e34948;
                        border-radius:8px;padding:10px 14px;margin-bottom:6px;">
                        <div style="display:flex;justify-content:space-between;">
                          <span style="font-size:12px;font-weight:600;color:var(--ms-texto);">{p['card'][:50]}</span>
                          <span style="font-size:13px;font-weight:700;color:#e34948;">-{p['valor']:.0f} pts</span>
                        </div>
                        <div style="font-size:10px;color:var(--ms-texto-sec);margin-top:2px;">{ms}</div>
                    </div>""", unsafe_allow_html=True)
            else:
                st.markdown("""<div style="background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);
                    border-radius:10px;padding:20px;text-align:center;color:var(--ms-texto-sec);font-size:13px;">
                    Nenhuma penalidade este mês 🎉</div>""", unsafe_allow_html=True)
        else:
            st.markdown("#### 📊 Resumo do Mês")
            pts_u = d["pts_membro"].get(usuario_logado,0)
            pen_u = d["pen_membro"].get(usuario_logado,0)
            st.markdown(_card("Pts Conquistados", f"{pts_u:.0f}", f"Meta: {meta_ind}", icone="🏆"), unsafe_allow_html=True)
            if pen_u > 0:
                st.markdown(_card("Penalidades", f"-{pen_u:.0f}", "Este mês", cor="#e34948", icone="⚠️"), unsafe_allow_html=True)

    st.markdown("---")
    st.caption(f"Dados do Trello · {sel} · atualização automática a cada 2 min · {agora.strftime('%d/%m/%Y %H:%M')}")
