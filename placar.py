"""
placar.py — Módulo Painel de Meta · MS Studio
Lê dados em tempo real da API do Trello e exibe o painel de desempenho da equipe.
"""

import streamlit as st
import requests
from datetime import datetime
import math
import json

# ── CONFIGURAÇÕES ─────────────────────────────────────────────────────────────

try:
    TRELLO_KEY   = st.secrets["trello"]["api_key"]
    TRELLO_TOKEN = st.secrets["trello"]["token"]
    BOARD_ID     = st.secrets["trello"]["board_id"]
except Exception:
    TRELLO_KEY   = ""
    TRELLO_TOKEN = ""
    BOARD_ID     = ""

MEMBROS_ATIVOS = {
    "myrelladesouza": "Myrella",
    "beatriz51":      "Beatriz",
    "gabriel_borges": "Gabriel",
}

MASTERS = {"martinsousa", "renan"}

LISTAS_SEM_PONTUACAO = {
    "TABELA DE PONTUAÇÃO", "TRIAGEM", "CORREÇÃO DE FOTOS: 0 PONTOS",
    "RENAN", "GUSTAVO", "MYRELLA", "URGENTES!!!!", "Vídeos pendentes",
    "CRIAR ANÚNCIO", "CRIAR ANÚNCIO DO ZERO",
}

LISTAS_PENALIDADE = {"PENALIDADES"}

MESES_PT = {
    1:"Janeiro", 2:"Fevereiro", 3:"Março", 4:"Abril",
    5:"Maio", 6:"Junho", 7:"Julho", 8:"Agosto",
    9:"Setembro", 10:"Outubro", 11:"Novembro", 12:"Dezembro"
}

# ── API ────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=120)
def _buscar_board():
    if not TRELLO_KEY or not TRELLO_TOKEN or not BOARD_ID:
        return None, None, None, None, None
    base = "https://api.trello.com/1"
    auth = {"key": TRELLO_KEY, "token": TRELLO_TOKEN}
    r_listas = requests.get(f"{base}/boards/{BOARD_ID}/lists", params={**auth, "fields": "id,name"})
    listas = {l["id"]: l["name"] for l in r_listas.json()} if r_listas.ok else {}
    r_cards = requests.get(f"{base}/boards/{BOARD_ID}/cards", params={
        **auth,
        "fields": "id,name,idList,idMembers,labels,dueComplete,due,dateLastActivity,customFieldItems",
        "customFieldItems": "true",
    })
    cards = r_cards.json() if r_cards.ok else []
    r_membros = requests.get(f"{base}/boards/{BOARD_ID}/members", params={**auth, "fields": "id,username"})
    membros_map = {m["id"]: m["username"] for m in r_membros.json()} if r_membros.ok else {}
    r_campos = requests.get(f"{base}/boards/{BOARD_ID}/customFields", params=auth)
    campos = r_campos.json() if r_campos.ok else []
    id_pontos = next((c["id"] for c in campos if c.get("name","").upper() == "PONTOS"), None)
    id_interr = next((c["id"] for c in campos if "INTERROMPIDO" in c.get("name","").upper()), None)
    return listas, cards, membros_map, id_pontos, id_interr

def _pontos_do_card(card, id_campo_pontos):
    if not id_campo_pontos:
        return None
    for cf in card.get("customFieldItems", []):
        if cf.get("idCustomField") == id_campo_pontos:
            n = cf.get("value", {}).get("number")
            if n is not None:
                try: return float(n)
                except: pass
    return None

def _interrompido_do_card(card, id_campo):
    if not id_campo:
        return 0
    for cf in card.get("customFieldItems", []):
        if cf.get("idCustomField") == id_campo:
            n = cf.get("value", {}).get("number")
            if n is not None:
                try: return float(n)
                except: pass
    return 0

def _labels_do_card(card):
    return {lb.get("name", "").upper() for lb in card.get("labels", [])}

def _usernames_do_card(card, membros_map):
    return [membros_map.get(mid, mid) for mid in card.get("idMembers", [])]

def _mes_do_card(card):
    data = card.get("dateLastActivity") or card.get("due") or ""
    if data:
        try:
            dt = datetime.fromisoformat(data.replace("Z", "+00:00"))
            return (dt.year, dt.month)
        except: pass
    return None

# ── PROCESSAMENTO ──────────────────────────────────────────────────────────────

def _processar_dados(listas, cards, membros_map, id_pontos, id_interr, filtro_mes=None):
    r = {
        "pontuacao_por_membro":    {u: 0.0 for u in MEMBROS_ATIVOS},
        "pontuacao_equipe":         0.0,
        "penalidades_por_membro":  {u: 0.0 for u in MEMBROS_ATIVOS},
        "penalidade_total":         0.0,
        "cards_abertos":            0,
        "cards_urgentes":           0,
        "cards_atrasados":          0,
        "cards_em_andamento":       0,
        "cards_falta_conf":         0,
        "cards_falta_info":         0,
        "cards_sem_membro":         0,
        "pontos_pendentes":         0.0,
        "cards_por_lista_pendente": {},
        "penalidades_cards":        [],
        "cards_em_andamento_lista": [],
        "tempo_medio_por_lista":    {},
    }

    for card in cards:
        nome_lista = listas.get(card["idList"], "")
        if nome_lista == "TABELA DE PONTUAÇÃO":
            continue

        labels    = _labels_do_card(card)
        usernames = _usernames_do_card(card, membros_map)
        concluido = card.get("dueComplete", False)
        pontos    = _pontos_do_card(card, id_pontos)
        interr    = _interrompido_do_card(card, id_interr)

        # Filtro de mês
        if filtro_mes:
            mes_card = _mes_do_card(card)
            if mes_card and mes_card != filtro_mes:
                continue

        # Penalidades
        if nome_lista in LISTAS_PENALIDADE:
            if pontos is not None:
                val = abs(pontos)
                r["penalidade_total"] += val
                r["penalidades_cards"].append({
                    "card": card["name"], "valor": val, "membros": usernames
                })
                for u in usernames:
                    if u in r["penalidades_por_membro"]:
                        r["penalidades_por_membro"][u] += val
            continue

        # Em andamento
        if "EM ANDAMENTO" in labels:
            r["cards_em_andamento"] += 1
            r["cards_em_andamento_lista"].append({
                "card": card["name"], "lista": nome_lista, "membros": usernames
            })

        # Contadores status (apenas abertos)
        if not concluido:
            r["cards_abertos"] += 1
            if "URGENTE" in labels or "URGENTES" in nome_lista.upper():
                r["cards_urgentes"] += 1
            if "ATRASADO" in labels:
                r["cards_atrasados"] += 1
            if "FALTA CONFERÊNCIA" in labels:
                r["cards_falta_conf"] += 1
            if "FALTA INFORMAÇÃO" in labels:
                r["cards_falta_info"] += 1
            if not usernames:
                r["cards_sem_membro"] += 1
            if "PENDENTE" in labels and pontos:
                r["pontos_pendentes"] += pontos
                r["cards_por_lista_pendente"][nome_lista] = r["cards_por_lista_pendente"].get(nome_lista, 0) + 1

        # Pontuação (somente concluídos)
        if not concluido or pontos is None:
            continue
        if nome_lista in LISTAS_SEM_PONTUACAO:
            continue

        r["pontuacao_equipe"] += pontos
        membros_ativos_card = [u for u in usernames if u in MEMBROS_ATIVOS]
        if membros_ativos_card:
            pts_cada = pontos / len(membros_ativos_card)
            for u in membros_ativos_card:
                r["pontuacao_por_membro"][u] += pts_cada

    return r

# ── COMPONENTES HTML ───────────────────────────────────────────────────────────

def _velocimetro(pct, label, meta_pts, atual_pts, faltam_pts):
    pct_clip = min(max(pct, 0), 100)
    angulo   = math.radians(-180 + (pct_clip / 100) * 180)
    cx, cy, r = 110, 105, 78
    px = cx + r * math.cos(angulo)
    py = cy + r * math.sin(angulo)
    cor = "#27AE60" if pct_clip >= 80 else ("#F39C12" if pct_clip >= 50 else "#C0392B")
    faltam_str = f"{faltam_pts:.0f} pts para a meta"
    return f"""
<div style="text-align:center;padding:8px 0;">
  <svg viewBox="0 0 220 140" width="100%" style="max-width:240px;display:block;margin:0 auto;">
    <path d="M28 110 A82 82 0 0 1 192 110" fill="none" stroke="var(--ms-metric-bd)" stroke-width="16" stroke-linecap="round"/>
    <path d="M28 110 A82 82 0 0 1 192 110" fill="none" stroke="{cor}" stroke-width="16"
          stroke-linecap="round" stroke-dasharray="{pct_clip*2.576:.1f} 257.6"/>
    <line x1="{cx}" y1="{cy}" x2="{px:.1f}" y2="{py:.1f}"
          stroke="var(--ms-texto)" stroke-width="2.5" stroke-linecap="round"/>
    <circle cx="{cx}" cy="{cy}" r="5" fill="var(--ms-texto)"/>
    <text x="110" y="96" text-anchor="middle" font-size="22" font-weight="700" fill="var(--ms-texto)">{pct_clip:.0f}%</text>
    <text x="110" y="113" text-anchor="middle" font-size="10" fill="var(--ms-texto-sec)">{atual_pts:.0f} / {meta_pts} pts</text>
    <text x="110" y="130" text-anchor="middle" font-size="10" fill="{cor}">{faltam_str}</text>
  </svg>
  <div style="font-size:11px;color:var(--ms-texto-sec);letter-spacing:.6px;text-transform:uppercase;">{label}</div>
</div>"""

def _card_stat(label, valor, sub=None, cor="#e0e0e0", icone=""):
    sub_h = f'<div style="font-size:10px;color:var(--ms-texto-sec);margin-top:2px;">{sub}</div>' if sub else ""
    return f"""
<div style="background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);border-radius:10px;
     padding:14px 16px;height:100%;min-height:72px;">
  <div style="font-size:10px;color:var(--ms-texto-sec);letter-spacing:.5px;text-transform:uppercase;margin-bottom:4px;">{icone} {label}</div>
  <div style="font-size:26px;font-weight:700;color:{cor};line-height:1.1;">{valor}</div>
  {sub_h}
</div>"""

def _barra_membro(nome, pts, meta, pen):
    saldo = pts - pen
    pct   = min(saldo / meta * 100, 100) if meta > 0 else 0
    cor   = "#27AE60" if pct >= 80 else ("#F39C12" if pct >= 50 else "#C0392B")
    pen_h = f'<div style="font-size:10px;color:#C0392B;margin-top:2px;">⚠ -{pen:.0f} pts em penalidades</div>' if pen > 0 else ""
    return f"""
<div style="margin-bottom:14px;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
    <span style="font-size:13px;font-weight:600;color:var(--ms-texto);">{nome}</span>
    <span style="font-size:12px;color:var(--ms-texto-sec);">{saldo:.0f} / {meta:.0f} pts · <b style="color:{cor};">{pct:.0f}%</b></span>
  </div>
  <div style="background:var(--ms-metric-bd);border-radius:6px;height:10px;overflow:hidden;">
    <div style="background:{cor};width:{pct:.1f}%;height:100%;border-radius:6px;"></div>
  </div>
  {pen_h}
</div>"""

# ── PÁGINA PRINCIPAL ───────────────────────────────────────────────────────────

def pagina_placar(usuario_logado):
    eh_master = usuario_logado in MASTERS
    eh_membro = usuario_logado in MEMBROS_ATIVOS

    if not TRELLO_KEY or not TRELLO_TOKEN or not BOARD_ID:
        st.error("Credenciais do Trello não configuradas. Adicione `[trello]` no secrets.toml.")
        st.code('[trello]\napi_key  = "SUA_API_KEY"\ntoken    = "SEU_TOKEN"\nboard_id = "ID_DO_BOARD"')
        return

    # ── CABEÇALHO ─────────────────────────────────────────────────────────────
    agora = datetime.now()
    col_tit, col_mes, col_att = st.columns([3, 2, 1])
    with col_tit:
        st.markdown("## 🏆 Painel de Meta")
    with col_mes:
        meses_opcoes = [(agora.year, agora.month)]
        m, a = agora.month, agora.year
        for _ in range(5):
            m -= 1
            if m == 0: m = 12; a -= 1
            meses_opcoes.append((a, m))
        labels_meses = [f"{MESES_PT[mm]} {aa}" for aa, mm in meses_opcoes]
        sel = st.selectbox("Mês", labels_meses, index=0, key="placar_mes", label_visibility="collapsed")
        idx_sel = labels_meses.index(sel)
        filtro_mes = meses_opcoes[idx_sel]
    with col_att:
        if st.button("🔄 Atualizar", use_container_width=True):
            _buscar_board.clear()
            st.rerun()

    st.caption(f"Exibindo: {sel} · atualizado a cada 2 minutos · última consulta: {agora.strftime('%d/%m/%Y %H:%M')}")

    # ── METAS ─────────────────────────────────────────────────────────────────
    chave_meta_eq  = f"meta_equipe_{filtro_mes[0]}_{filtro_mes[1]}"
    chave_meta_ind = f"meta_ind_{filtro_mes[0]}_{filtro_mes[1]}"

    with st.expander("⚙️ Configurar Metas — " + sel, expanded=False):
        if eh_master:
            c1, c2 = st.columns(2)
            meta_equipe = c1.number_input("Meta da equipe (pts/mês)", min_value=0,
                value=st.session_state.get(chave_meta_eq, 5000), step=100, key=chave_meta_eq)
            meta_ind = c2.number_input("Meta individual (pts/mês)", min_value=0,
                value=st.session_state.get(chave_meta_ind, 1500), step=100, key=chave_meta_ind)
        else:
            meta_equipe = st.session_state.get(chave_meta_eq, 5000)
            meta_ind    = st.session_state.get(chave_meta_ind, 1500)
            st.info("Metas configuradas pelo gestor.")

    meta_equipe = st.session_state.get(chave_meta_eq, 5000)
    meta_ind    = st.session_state.get(chave_meta_ind, 1500)

    # ── BUSCA ─────────────────────────────────────────────────────────────────
    with st.spinner("Buscando dados do Trello..."):
        dados_api = _buscar_board()

    if dados_api is None or dados_api[0] is None:
        st.error("Não foi possível conectar ao Trello.")
        return

    listas, cards, membros_map, id_pontos, id_interr = dados_api
    dados = _processar_dados(listas, cards, membros_map, id_pontos, id_interr, filtro_mes=filtro_mes)

    pts_eq   = dados["pontuacao_equipe"]
    pen_tot  = dados["penalidade_total"]
    saldo_eq = pts_eq - pen_tot
    pct_eq   = (saldo_eq / meta_equipe * 100) if meta_equipe > 0 else 0
    faltam   = max(meta_equipe - saldo_eq, 0)

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO 1 — VELOCÍMETRO + MÉTRICAS PRINCIPAIS
    # ══════════════════════════════════════════════════════════════════════════
    col_vel, col_stats = st.columns([2, 3])

    with col_vel:
        st.markdown(_velocimetro(pct_eq, "META DA EQUIPE", meta_equipe, saldo_eq, faltam), unsafe_allow_html=True)

    with col_stats:
        r1, r2 = st.columns(3), st.columns(3)
        cor_pts = "#27AE60" if pct_eq >= 80 else ("#F39C12" if pct_eq >= 50 else "#C0392B")
        r1[0].markdown(_card_stat("Pontuação Atual", f"{saldo_eq:.0f}", f"Meta: {meta_equipe} · Faltam: {faltam:.0f}", cor=cor_pts, icone="🏆"), unsafe_allow_html=True)
        r1[1].markdown(_card_stat("Cartões em Aberto", dados["cards_abertos"], icone="📋"), unsafe_allow_html=True)
        r1[2].markdown(_card_stat("Penalidades", f"-{pen_tot:.0f}", f"{len(dados['penalidades_cards'])} ocorrências", cor="#C0392B" if pen_tot > 0 else "var(--ms-texto)", icone="⚠️"), unsafe_allow_html=True)
        r2[0].markdown(_card_stat("Pts em Aberto", f"{dados['pontos_pendentes']:.0f}", "Cartões pendentes", cor="#F39C12", icone="🟠"), unsafe_allow_html=True)
        r2[1].markdown(_card_stat("Urgentes", dados["cards_urgentes"], icone="🚨", cor="#C0392B" if dados["cards_urgentes"] > 0 else "var(--ms-texto)"), unsafe_allow_html=True)
        r2[2].markdown(_card_stat("Sem Membro", dados["cards_sem_membro"], icone="👤", cor="#F39C12" if dados["cards_sem_membro"] > 0 else "var(--ms-texto)"), unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO 2 — STATUS + COLABORADORES
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    col_status, col_colab = st.columns(2)

    with col_status:
        st.markdown("#### 📊 Status dos Cartões")
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(_card_stat("Atrasados", dados["cards_atrasados"], icone="⏰", cor="#C0392B" if dados["cards_atrasados"] > 0 else "var(--ms-texto)"), unsafe_allow_html=True)
        c2.markdown(_card_stat("Em Andamento", dados["cards_em_andamento"], icone="▶️"), unsafe_allow_html=True)
        c3.markdown(_card_stat("Falta Conferir", dados["cards_falta_conf"], icone="🔍"), unsafe_allow_html=True)
        c4.markdown(_card_stat("Falta Info", dados["cards_falta_info"], icone="❓"), unsafe_allow_html=True)

        st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)
        st.markdown("**▶️ Em Andamento Agora**")
        if dados["cards_em_andamento_lista"]:
            for c in dados["cards_em_andamento_lista"][:4]:
                membros_str = ", ".join(MEMBROS_ATIVOS.get(u, u) for u in c["membros"]) or "—"
                st.markdown(f"""<div style="background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);
                    border-radius:8px;padding:8px 12px;margin-bottom:5px;">
                    <div style="font-size:12px;font-weight:600;color:var(--ms-texto);">{c['card'][:48]}</div>
                    <div style="font-size:10px;color:var(--ms-texto-sec);margin-top:1px;">{c['lista'][:35]} · {membros_str}</div>
                </div>""", unsafe_allow_html=True)
        else:
            st.caption("Nenhum cartão em andamento.")

    with col_colab:
        if eh_master:
            st.markdown("#### 👥 Desempenho por Colaborador")
            barras = ""
            for username, nome_exib in MEMBROS_ATIVOS.items():
                pts = dados["pontuacao_por_membro"].get(username, 0)
                pen = dados["penalidades_por_membro"].get(username, 0)
                barras += _barra_membro(nome_exib, pts, meta_ind, pen)
            st.markdown(f'<div style="padding:4px 0">{barras}</div>', unsafe_allow_html=True)
        elif eh_membro:
            st.markdown("#### Seu Desempenho")
            pts = dados["pontuacao_por_membro"].get(usuario_logado, 0)
            pen = dados["penalidades_por_membro"].get(usuario_logado, 0)
            saldo_ind = pts - pen
            pct_ind   = (saldo_ind / meta_ind * 100) if meta_ind > 0 else 0
            faltam_ind = max(meta_ind - saldo_ind, 0)
            st.markdown(_velocimetro(pct_ind, "SUA META", meta_ind, saldo_ind, faltam_ind), unsafe_allow_html=True)
            nome_exib = MEMBROS_ATIVOS.get(usuario_logado, usuario_logado)
            st.markdown(_barra_membro(nome_exib, pts, meta_ind, pen), unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO 3 — PENDENTES POR COLUNA + PENALIDADES
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    col_pend, col_pen = st.columns(2)

    with col_pend:
        st.markdown("#### 🟠 Pendentes por Coluna")
        if dados["cards_por_lista_pendente"]:
            max_qtd = max(dados["cards_por_lista_pendente"].values())
            for lista, qtd in sorted(dados["cards_por_lista_pendente"].items(), key=lambda x: -x[1]):
                pct_b = qtd / max_qtd * 100
                st.markdown(f"""<div style="margin-bottom:9px;">
                  <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--ms-texto);margin-bottom:3px;">
                    <span>{lista[:38]}</span><span style="font-weight:700;">{qtd}</span>
                  </div>
                  <div style="background:var(--ms-metric-bd);border-radius:4px;height:6px;">
                    <div style="background:#F39C12;width:{pct_b:.0f}%;height:100%;border-radius:4px;"></div>
                  </div>
                </div>""", unsafe_allow_html=True)
        else:
            st.caption("Nenhum cartão pendente 🎉")

    with col_pen:
        if eh_master:
            st.markdown("#### ⚠️ Penalidades Registradas")
            if dados["penalidades_cards"]:
                for p in dados["penalidades_cards"]:
                    membros_str = ", ".join(MEMBROS_ATIVOS.get(u, u) for u in p["membros"]) or "Sem membro"
                    st.markdown(f"""<div style="background:var(--ms-metric-bg);border:1px solid #C0392B;
                        border-radius:8px;padding:10px 14px;margin-bottom:6px;">
                        <div style="display:flex;justify-content:space-between;">
                          <span style="font-size:12px;font-weight:600;color:var(--ms-texto);">{p['card'][:50]}</span>
                          <span style="font-size:13px;font-weight:700;color:#C0392B;">-{p['valor']:.0f} pts</span>
                        </div>
                        <div style="font-size:10px;color:var(--ms-texto-sec);margin-top:2px;">{membros_str}</div>
                    </div>""", unsafe_allow_html=True)
            else:
                st.caption("Nenhuma penalidade registrada este mês.")
        else:
            st.markdown("#### 📋 Cartões Pendentes por Coluna")
            st.caption("Vista resumida — contagem de pendências por área.")

    st.markdown("---")
    st.caption(f"Dados do Trello · {sel} · atualizado a cada 2 min · {agora.strftime('%d/%m/%Y %H:%M')}")
