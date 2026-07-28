"""
placar.py — Painel de Meta · MS Studio v3
Layout compacto premium — tudo em uma tela
"""
import streamlit as st
import requests
from datetime import datetime
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

@st.cache_data(ttl=120)
def _buscar_board():
    if not TRELLO_KEY: return None,None,None,None,None,None
    base = "https://api.trello.com/1"
    auth = {"key":TRELLO_KEY,"token":TRELLO_TOKEN}
    r_l = requests.get(f"{base}/boards/{BOARD_ID}/lists", params={**auth,"fields":"id,name"})
    listas = {l["id"]:l["name"] for l in r_l.json()} if r_l.ok else {}
    r_c = requests.get(f"{base}/boards/{BOARD_ID}/cards", params={
        **auth,"fields":"id,name,idList,idMembers,labels,dueComplete,customFieldItems",
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

def _processar(listas, cards, membros_map, id_p, id_t, id_interr, filtro_mes=None):
    d = {
        "pts_equipe":0.0, "pen_total":0.0,
        "pts_membro":{u:0.0 for u in MEMBROS_ATIVOS},
        "pen_membro":{u:0.0 for u in MEMBROS_ATIVOS},
        "abertos":0, "urgentes":0, "atrasados":0,
        "em_andamento":0, "falta_conf":0, "falta_info":0,
        "sem_membro":0, "falta_pts":0,
        "pts_pendentes":0.0, "pen_cards":[],
        "andamento_lista":[], "tempo_lista":{},
        "desativar":0, "reativar":0,
        "pend_lista":{},
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
            tl = max(tempo-interr,0)
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

# ── CSS INJETADO ───────────────────────────────────────────────────────────────
CSS = """
<style>
.pm-card {
    background: var(--ms-metric-bg);
    border: 1px solid var(--ms-metric-bd);
    border-radius: 12px;
    padding: 14px 16px;
    height: 100%;
    min-height: 80px;
    display: flex;
    flex-direction: column;
    justify-content: center;
}
.pm-label {
    font-size: 10px;
    color: var(--ms-texto-sec);
    text-transform: uppercase;
    letter-spacing: .7px;
    margin-bottom: 4px;
}
.pm-value {
    font-size: 28px;
    font-weight: 700;
    line-height: 1.1;
}
.pm-sub {
    font-size: 10px;
    color: var(--ms-texto-sec);
    margin-top: 3px;
}
.pm-status-card {
    background: var(--ms-metric-bg);
    border: 1px solid var(--ms-metric-bd);
    border-radius: 10px;
    padding: 12px 10px;
    text-align: center;
    height: 90px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
}
.pm-status-num {
    font-size: 30px;
    font-weight: 700;
    line-height: 1;
    margin: 4px 0;
}
.pm-status-label {
    font-size: 9px;
    color: var(--ms-texto-sec);
    text-transform: uppercase;
    letter-spacing: .5px;
}
.pm-badge {
    font-size: 9px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 4px;
    margin-top: 4px;
    display: inline-block;
}
.pm-andamento-card {
    background: var(--ms-metric-bg);
    border: 1px solid var(--ms-metric-bd);
    border-radius: 8px;
    padding: 8px 12px;
    margin-bottom: 5px;
}
.pm-barra-label {
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    color: #aaa;
    margin-bottom: 3px;
}
.pm-barra-track {
    background: var(--ms-metric-bd);
    border-radius: 4px;
    height: 6px;
    overflow: hidden;
    margin-bottom: 2px;
}
</style>
"""

def _velocimetro(pct, meta_eq, saldo_eq, faltam, pct_maxx=130):
    pct_clip = min(max(pct,0), pct_maxx+5)
    # Ponteiro
    ang = math.radians(-180 + min(pct_clip/100,1)*180)
    cx,cy,r = 120,115,95
    px = cx+r*math.cos(ang)
    py = cy+r*math.sin(ang)

    # Comprimento total do arco = pi*r
    perim = math.pi*r  # ~298.45

    # Arco verde: 0 até 100%
    dash_verde = min(pct_clip/100,1)*perim

    # Arco azul: 100% até maxx%
    inicio_maxx = 1.0*perim  # começa onde verde termina (100%)
    fim_maxx    = min(pct_maxx/100,1)*perim
    dash_azul   = max(fim_maxx - inicio_maxx, 0)

    # Posição do ponteiro % — logo abaixo do centro
    pct_show = min(pct, 999)

    return f"""
<div style="text-align:center;">
<svg viewBox="0 0 240 148" width="100%" style="max-width:280px;display:block;margin:0 auto;overflow:visible;">
  <!-- Arco fundo cinza -->
  <path d="M20,115 A100,100 0 0 1 220,115" fill="none" stroke="#2a2a2a" stroke-width="16" stroke-linecap="round"/>
  <!-- Arco azul (zona Meta Maxx: 100%→maxx%) -->
  <path d="M20,115 A100,100 0 0 1 220,115" fill="none" stroke="#2a78d6" stroke-width="16" stroke-linecap="round"
        stroke-dasharray="{fim_maxx:.1f} {perim:.1f}"
        stroke-dashoffset="0"/>
  <!-- Arco verde (zona meta: 0→100%) -->
  <path d="M20,115 A100,100 0 0 1 220,115" fill="none" stroke="#1baf7a" stroke-width="16" stroke-linecap="round"
        stroke-dasharray="{dash_verde:.1f} {perim:.1f}"/>
  <!-- Ticks laterais -->
  <text x="13" y="132" text-anchor="middle" font-size="9" fill="var(--ms-texto-sec)">0</text>
  <text x="227" y="132" text-anchor="middle" font-size="9" fill="var(--ms-texto-sec)">META</text>
  <!-- Ponteiro -->
  <line x1="{cx}" y1="{cy}" x2="{px:.1f}" y2="{py:.1f}" stroke="var(--ms-texto)" stroke-width="2.5" stroke-linecap="round"/>
  <circle cx="{cx}" cy="{cy}" r="6" fill="var(--ms-texto)"/>
  <circle cx="{cx}" cy="{cy}" r="2.5" fill="var(--ms-metric-bg)"/>
  <!-- % abaixo do ponteiro, sutil -->
  <text x="{cx}" y="{cy+22}" text-anchor="middle" font-size="20" font-weight="700" fill="var(--ms-texto)">{pct_show:.0f}%</text>
</svg>
<div style="font-size:10px;color:#555;text-transform:uppercase;letter-spacing:.5px;margin-top:2px;">Meta da Equipe</div>
</div>"""

def _card_html(label, valor, sub=None, cor="var(--ms-texto)", badge=None, badge_cor=None):
    sub_h = f'<div class="pm-sub">{sub}</div>' if sub else ""
    badge_h = f'<span class="pm-badge" style="background:{badge_cor}20;color:{badge_cor};">{badge}</span>' if badge else ""
    return f"""<div class="pm-card">
  <div class="pm-label">{label}</div>
  <div class="pm-value" style="color:{cor};">{valor}</div>
  {sub_h}{badge_h}
</div>"""

def _status_card(label, valor, badge, cor_num, cor_badge_bg, cor_badge_txt):
    return f"""<div class="pm-status-card">
  <div class="pm-status-label">{label}</div>
  <div class="pm-status-num" style="color:{cor_num};">{valor}</div>
  <span class="pm-badge" style="background:{cor_badge_bg};color:{cor_badge_txt};">{badge}</span>
</div>"""

def pagina_placar(usuario_logado):
    eh_master = usuario_logado in MASTERS
    eh_membro = usuario_logado in MEMBROS_ATIVOS

    if not TRELLO_KEY:
        st.error("Credenciais do Trello não configuradas.")
        return

    st.markdown(CSS, unsafe_allow_html=True)
    agora = datetime.now()

    # Cabeçalho compacto
    col_tit, col_mes, col_att = st.columns([3,2,1])
    with col_tit:
        st.markdown("### 🏆 Painel de Meta")
    with col_mes:
        meses = [(agora.year, agora.month)]
        m,a = agora.month, agora.year
        for _ in range(5):
            m-=1
            if m==0: m=12; a-=1
            meses.append((a,m))
        labels = [f"{MESES_PT[mm]} {aa}" for aa,mm in meses]
        sel = st.selectbox("Mês", labels, index=0, key="placar_mes", label_visibility="collapsed")
        filtro_mes = meses[labels.index(sel)]
    with col_att:
        if st.button("🔄", use_container_width=True, help="Atualizar dados"):
            _buscar_board.clear(); st.rerun()

    # Metas
    k_eq  = f"meta_eq_{filtro_mes[0]}_{filtro_mes[1]}"
    k_ind = f"meta_ind_{filtro_mes[0]}_{filtro_mes[1]}"
    k_mx  = f"meta_maxx_{filtro_mes[0]}_{filtro_mes[1]}"

    if k_eq not in st.session_state: st.session_state[k_eq] = 5000
    if k_ind not in st.session_state: st.session_state[k_ind] = 1500
    if k_mx not in st.session_state: st.session_state[k_mx] = 130

    with st.expander(f"⚙️ Configurar Metas — {sel}", expanded=False):
        if eh_master:
            c1,c2,c3 = st.columns(3)
            st.session_state[k_eq]  = c1.number_input("Meta equipe (pts)", min_value=0, value=st.session_state[k_eq], step=100)
            st.session_state[k_ind] = c2.number_input("Meta individual (pts)", min_value=0, value=st.session_state[k_ind], step=100)
            st.session_state[k_mx]  = c3.number_input("Meta Maxx (%)", min_value=100, max_value=300, value=st.session_state[k_mx], step=5)
        else:
            st.info("Metas configuradas pelo gestor.")

    meta_eq   = st.session_state[k_eq]
    meta_ind  = st.session_state[k_ind]
    maxx_pct  = st.session_state[k_mx]
    meta_maxx_pts = meta_eq * maxx_pct / 100

    # Dados
    with st.spinner(""):
        dados_api = _buscar_board()
    if not dados_api or not dados_api[0]:
        st.error("Não foi possível conectar ao Trello.")
        return

    listas, cards, membros_map, id_p, id_t, id_interr = dados_api
    d = _processar(listas, cards, membros_map, id_p, id_t, id_interr, filtro_mes)

    saldo_eq = d["pts_equipe"] - d["pen_total"]
    pct_eq   = (saldo_eq/meta_eq*100) if meta_eq>0 else 0
    faltam   = max(meta_eq-saldo_eq,0)
    faltam_maxx = max(meta_maxx_pts-saldo_eq,0)
    cor_pts  = "#1baf7a" if pct_eq>=100 else ("#eda100" if pct_eq>=50 else "#e34948")

    # ══ BLOCO 1: VELOCÍMETRO + CARDS META ══
    col_vel, col_meta = st.columns([2,3])

    with col_vel:
        st.markdown(_velocimetro(pct_eq, meta_eq, saldo_eq, faltam, maxx_pct), unsafe_allow_html=True)

    with col_meta:
        r1 = st.columns(3)
        r2 = st.columns(3)
        r1[0].markdown(_card_html("Meta", f"{meta_eq:,.0f}", "pts/mês"), unsafe_allow_html=True)
        r1[1].markdown(_card_html("Pontuação Atual", f"{saldo_eq:,.0f}", f"{pct_eq:.0f}% da meta", cor=cor_pts), unsafe_allow_html=True)
        r1[2].markdown(_card_html("Faltam para Meta", f"{faltam:,.0f}", "pts restantes", cor="#eda100" if faltam>0 else "#1baf7a"), unsafe_allow_html=True)
        r2[0].markdown(_card_html("Pts em Aberto", f"{d['pts_pendentes']:,.0f}", "cartões pendentes", cor="#eda100"), unsafe_allow_html=True)
        r2[1].markdown(_card_html("Meta Maxx", f"{meta_maxx_pts:,.0f}", f"{maxx_pct}% da meta", cor="#2a78d6"), unsafe_allow_html=True)
        r2[2].markdown(_card_html("Faltam p/ Maxx", f"{faltam_maxx:,.0f}", "pts para bônus", cor="#2a78d6" if faltam_maxx>0 else "#1baf7a"), unsafe_allow_html=True)

    # ══ BLOCO 2: STATUS DOS CARTÕES ══
    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

    pend_total = sum(d["pend_lista"].values())
    status_items = [
        ("Cartões Pendentes", pend_total,            "Pendente",      "var(--ms-texto)", "#eda10030", "#eda100"),
        ("Pts Pendentes",     f"{d['pts_pendentes']:.0f}", "Aberto", "#eda100", "#eda10020", "#eda100"),
        ("Em Andamento",      d["em_andamento"],     "Ativo",         "var(--ms-texto)", "#1baf7a20", "#1baf7a"),
        ("Atrasados",         d["atrasados"],        "Atenção",       "#e34948", "#e3494820", "#e34948"),
        ("Desativar",         d["desativar"],        "Prioritário",   "var(--ms-texto)", "#2a78d620", "#2a78d6"),
        ("Reativar",          d["reativar"],         "Normal",        "var(--ms-texto)", "#33333350", "#888"),
        ("Urgentes",          d["urgentes"],         "Crítico",       "#e34948", "#e3494830", "#e34948"),
        ("Falta Info",        d["falta_info"],       "Pendente",      "#eda100", "#eda10020", "#eda100"),
        ("Falta Pontuação",   d["falta_pts"],        "Revisar",       "#eda100", "#eda10020", "#eda100"),
        ("Penalidades",       f"-{d['pen_total']:.0f}", "Ocorrências","#e34948", "#e3494820", "#e34948"),
        ("Sem Membro",        d["sem_membro"],       "Revisar",       "#eda100", "#eda10020", "#eda100"),
    ]

    cols_st = st.columns(11)
    for i, (lbl, val, badge, cor_n, bg_b, txt_b) in enumerate(status_items):
        with cols_st[i]:
            st.markdown(_status_card(lbl, val, badge, cor_n, bg_b, txt_b), unsafe_allow_html=True)

    # ══ BLOCO 3: EM ANDAMENTO + DESEMPENHO ══
    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
    col_and, col_colab = st.columns([3,2])

    with col_and:
        st.markdown('<div class="pm-label" style="margin-bottom:6px;">▶️ EM ANDAMENTO AGORA</div>', unsafe_allow_html=True)
        if d["andamento_lista"]:
            for c in d["andamento_lista"][:6]:
                ms = ", ".join(MEMBROS_ATIVOS.get(u,u) for u in c["membros"]) or "—"
                st.markdown(f"""<div class="pm-andamento-card">
                  <div style="font-size:12px;font-weight:600;color:var(--ms-texto);">{c['card'][:55]}</div>
                  <div style="font-size:10px;color:var(--ms-texto-sec);margin-top:2px;">{c['lista'][:35]} · <span style="color:#1baf7a;">{ms}</span></div>
                </div>""", unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:var(--ms-texto-sec);font-size:12px;padding:8px 0;">Nenhum cartão em andamento.</div>', unsafe_allow_html=True)

    with col_colab:
        st.markdown('<div class="pm-label" style="margin-bottom:6px;">👥 DESEMPENHO POR COLABORADOR</div>', unsafe_allow_html=True)
        for username, nome in MEMBROS_ATIVOS.items():
            pts = d["pts_membro"].get(username,0)
            pen = d["pen_membro"].get(username,0)
            saldo_i = pts-pen
            pct_i = min((saldo_i/meta_ind*100),100) if meta_ind>0 else 0
            cor_i = "#1baf7a" if pct_i>=100 else ("#eda100" if pct_i>=50 else "#e34948")
            pen_txt = f'<div style="font-size:9px;color:#e34948;margin-top:2px;">⚠ -{pen:.0f} pts penalidades</div>' if pen > 0 else ""
            html_barra = (
                '<div style="margin-bottom:10px;">' +
                '<div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px;">' +
                f'<span style="color:var(--ms-texto);font-weight:600;">{nome}</span>' +
                f'<span style="color:{cor_i};">{saldo_i:.0f} / {meta_ind:.0f} pts · {pct_i:.0f}%</span>' +
                '</div>' +
                '<div style="background:var(--ms-metric-bd);border-radius:4px;height:8px;overflow:hidden;">' +
                f'<div style="background:{cor_i};width:{pct_i:.1f}%;height:100%;border-radius:4px;"></div>' +
                '</div>' +
                pen_txt +
                '</div>'
            )
            st.markdown(html_barra, unsafe_allow_html=True)

    # ══ BLOCO 4: TEMPO MÉDIO POR COLUNA ══
    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
    st.markdown('<div class="pm-label" style="margin-bottom:6px;">⏱️ TEMPO MÉDIO POR COLUNA</div>', unsafe_allow_html=True)

    listas_tempo = [nl for nl in set(listas.values())
                    if nl not in LISTAS_PENALIDADE
                    and nl != "TABELA DE PONTUAÇÃO"
                    and nl not in LISTAS_SEM_PONTUACAO]
    listas_tempo.sort()

    if listas_tempo:
        cols_t = st.columns(min(len(listas_tempo),6))
        for i, nl in enumerate(listas_tempo[:12]):
            tempos = d["tempo_lista"].get(nl,[])
            if tempos:
                media = sum(tempos)/len(tempos)
                val = f"{media:.0f} min"
                sub = f"{len(tempos)} demandas"
                cor = "var(--ms-texto)"
            else:
                val = "— min"
                sub = "sem dados"
                cor = "var(--ms-texto-sec)"
            with cols_t[i%6]:
                st.markdown(f"""<div style="background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);border-radius:8px;
                    padding:8px 10px;margin-bottom:6px;">
                  <div style="font-size:9px;color:var(--ms-texto-sec);text-transform:uppercase;letter-spacing:.4px;margin-bottom:2px;">{nl[:22]}</div>
                  <div style="font-size:16px;font-weight:700;color:{cor};">{val}</div>
                  <div style="font-size:9px;color:var(--ms-texto-sec);">{sub}</div>
                </div>""", unsafe_allow_html=True)

    st.markdown(f'<div style="font-size:9px;color:#333;text-align:right;margin-top:8px;">{sel} · {agora.strftime("%d/%m/%Y %H:%M")} · atualiza a cada 2 min</div>', unsafe_allow_html=True)
