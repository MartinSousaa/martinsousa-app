"""
placar.py — Módulo de Placar e Metas · MS Studio
Lê dados em tempo real da API do Trello e exibe o painel de desempenho da equipe.
"""

import streamlit as st
import requests
from datetime import datetime, date
import math

# ── CONFIGURAÇÕES ─────────────────────────────────────────────────────────────

TRELLO_KEY   = st.secrets.get("trello", {}).get("api_key", "")
TRELLO_TOKEN = st.secrets.get("trello", {}).get("token", "")
BOARD_ID     = st.secrets.get("trello", {}).get("board_id", "")

# Membros que pontuam (mapeamento username → nome de exibição)
MEMBROS_ATIVOS = {
    "myrelladesouza": "Myrella",
    "beatriz51":      "Beatriz",
    "gabriel_borges": "Gabriel",
}

# Usuários master (veem tudo)
MASTERS = {"martinsousa", "renan"}

# Listas que NÃO pontuam diretamente
LISTAS_SEM_PONTUACAO = {
    "TABELA DE PONTUAÇÃO",
    "TRIAGEM",
    "CORREÇÃO DE FOTOS: 0 PONTOS",
    "RENAN",
    "GUSTAVO",
    "MYRELLA",
    "URGENTES!!!!",
    "Vídeos pendentes",
    "CRIAR ANÚNCIO",
    "CRIAR ANÚNCIO DO ZERO",
}

# Listas que só pontuam quando o card chega em outra lista
LISTAS_DEPENDENTES = {
    # lista_origem : lista_destino_que_pontua
    "CRIATIVO DO ZERO: (FINALIZAR NO INTEGRAÇÃO!!!)": "INTEGRAÇÃO NOVOS ANÚNCIOS (100)",
    "CRIATIVO VÍDEO (80)":                             "CONFERENCIA VÍDEO",
    "INTEGRAÇÃO VÍDEO (10)":                           "CONFERENCIA VÍDEO",
}

# Listas de penalidade
LISTAS_PENALIDADE = {"PENALIDADES"}

# Etiquetas conhecidas
LABEL_EM_ANDAMENTO    = "EM ANDAMENTO"
LABEL_PENDENTE        = "PENDENTE"
LABEL_ATRASADO        = "ATRASADO"
LABEL_URGENTE         = "URGENTE"
LABEL_FALTA_CONF      = "FALTA CONFERÊNCIA"
LABEL_FALTA_INFO      = "FALTA INFORMAÇÃO"

# ── CACHE / API ───────────────────────────────────────────────────────────────

@st.cache_data(ttl=120)   # atualiza a cada 2 minutos
def _buscar_board():
    """Busca todos os cards e listas do board via API Trello."""
    if not TRELLO_KEY or not TRELLO_TOKEN or not BOARD_ID:
        return None, None, None

    base = "https://api.trello.com/1"
    auth = {"key": TRELLO_KEY, "token": TRELLO_TOKEN}

    # Listas
    r_listas = requests.get(f"{base}/boards/{BOARD_ID}/lists", params={**auth, "fields": "id,name"})
    listas = {l["id"]: l["name"] for l in r_listas.json()} if r_listas.ok else {}

    # Cards (com campos personalizados, membros, etiquetas)
    r_cards = requests.get(
        f"{base}/boards/{BOARD_ID}/cards",
        params={
            **auth,
            "fields": "id,name,idList,idMembers,labels,dueComplete,due,customFieldItems",
            "customFieldItems": "true",
        }
    )
    cards = r_cards.json() if r_cards.ok else []

    # Membros do board
    r_membros = requests.get(f"{base}/boards/{BOARD_ID}/members", params={**auth, "fields": "id,username,fullName"})
    membros_map = {m["id"]: m["username"] for m in r_membros.json()} if r_membros.ok else {}

    # Campos personalizados do board (para identificar IDs)
    r_campos = requests.get(f"{base}/boards/{BOARD_ID}/customFields", params=auth)
    campos = r_campos.json() if r_campos.ok else []

    # Identifica o ID do campo PONTOS e INTERROMPIDO
    id_campo_pontos       = None
    id_campo_interrompido = None
    for c in campos:
        nome = c.get("name", "").upper()
        if nome == "PONTOS":
            id_campo_pontos = c["id"]
        elif "INTERROMPIDO" in nome:
            id_campo_interrompido = c["id"]

    return listas, cards, membros_map, id_campo_pontos, id_campo_interrompido


def _pontos_do_card(card, id_campo_pontos):
    """Extrai o valor do campo PONTOS do card."""
    if not id_campo_pontos:
        return None
    for cf in card.get("customFieldItems", []):
        if cf.get("idCustomField") == id_campo_pontos:
            val = cf.get("value", {})
            n = val.get("number")
            if n is not None:
                try:
                    return float(n)
                except Exception:
                    pass
    return None


def _nome_lista(id_lista, listas):
    return listas.get(id_lista, "")


def _labels_do_card(card):
    """Retorna set com nomes de etiquetas do card (uppercase)."""
    return {lb.get("name", "").upper() for lb in card.get("labels", [])}


def _usernames_do_card(card, membros_map):
    return [membros_map.get(mid, mid) for mid in card.get("idMembers", [])]


# ── PROCESSAMENTO ─────────────────────────────────────────────────────────────

def _processar_dados(listas, cards, membros_map, id_campo_pontos, id_campo_interrompido, mes_filtro=None):
    """
    Processa os cards e retorna estrutura de dados para o painel.
    mes_filtro: (ano, mes) tuple ou None para todos.
    """
    resultado = {
        "pontuacao_por_membro":   {u: 0.0 for u in MEMBROS_ATIVOS},
        "pontuacao_equipe":        0.0,
        "penalidades_por_membro": {u: 0.0 for u in MEMBROS_ATIVOS},
        "penalidade_total":        0.0,
        "cards_abertos":           0,
        "cards_urgentes":          0,
        "cards_atrasados":         0,
        "cards_em_andamento":      0,
        "cards_falta_conf":        0,
        "cards_falta_info":        0,
        "cards_sem_membro":        0,
        "pontos_pendentes":        0.0,
        "cards_por_lista_pendente": {},
        "penalidades_cards":       [],
        "cards_em_andamento_lista": [],
    }

    for card in cards:
        nome_lista = _nome_lista(card["idList"], listas)

        # Ignora listas de controle/tabela
        if nome_lista == "TABELA DE PONTUAÇÃO":
            continue

        labels     = _labels_do_card(card)
        usernames  = _usernames_do_card(card, membros_map)
        concluido  = card.get("dueComplete", False)
        pontos     = _pontos_do_card(card, id_campo_pontos)

        # ── PENALIDADES ─────────────────────────────────────────────────────
        if nome_lista in LISTAS_PENALIDADE:
            if pontos is not None:
                val = abs(pontos)
                resultado["penalidade_total"] += val
                resultado["penalidades_cards"].append({
                    "card": card["name"],
                    "valor": val,
                    "membros": usernames,
                })
                for u in usernames:
                    if u in resultado["penalidades_por_membro"]:
                        resultado["penalidades_por_membro"][u] += val
            continue

        # ── CARDS EM ANDAMENTO ───────────────────────────────────────────────
        if LABEL_EM_ANDAMENTO in labels:
            resultado["cards_em_andamento"] += 1
            resultado["cards_em_andamento_lista"].append({
                "card": card["name"],
                "lista": nome_lista,
                "membros": usernames,
            })

        # ── CONTADORES DE STATUS ─────────────────────────────────────────────
        if not concluido:
            resultado["cards_abertos"] += 1
            if LABEL_URGENTE in labels or "URGENTES" in nome_lista.upper():
                resultado["cards_urgentes"] += 1
            if LABEL_ATRASADO in labels:
                resultado["cards_atrasados"] += 1
            if LABEL_FALTA_CONF in labels:
                resultado["cards_falta_conf"] += 1
            if LABEL_FALTA_INFO in labels:
                resultado["cards_falta_info"] += 1
            if not usernames:
                resultado["cards_sem_membro"] += 1

            # Pontos pendentes (cards com PENDENTE e pontuação definida)
            if LABEL_PENDENTE in labels and pontos:
                resultado["pontos_pendentes"] += pontos
                lista_key = nome_lista or "Sem lista"
                resultado["cards_por_lista_pendente"][lista_key] = (
                    resultado["cards_por_lista_pendente"].get(lista_key, 0) + 1
                )

        # ── PONTUAÇÃO ────────────────────────────────────────────────────────
        if not concluido:
            continue
        if pontos is None:
            continue
        if nome_lista in LISTAS_SEM_PONTUACAO:
            continue

        # Meta da equipe: sempre soma integral
        resultado["pontuacao_equipe"] += pontos

        # Meta individual: divide entre membros ativos no card
        membros_ativos_no_card = [u for u in usernames if u in MEMBROS_ATIVOS]
        if membros_ativos_no_card:
            pts_cada = pontos / len(membros_ativos_no_card)
            for u in membros_ativos_no_card:
                resultado["pontuacao_por_membro"][u] += pts_cada

    return resultado


# ── COMPONENTES VISUAIS ───────────────────────────────────────────────────────

def _card_metrica(label, valor, sub=None, cor_valor="var(--ms-texto)", icone=""):
    sub_html = f'<div style="font-size:11px;color:var(--ms-texto-sec);margin-top:2px;">{sub}</div>' if sub else ""
    return f"""
    <div style="
        background:var(--ms-metric-bg);
        border:1px solid var(--ms-metric-bd);
        border-radius:10px;
        padding:16px 18px;
        min-height:80px;
        display:flex;flex-direction:column;justify-content:center;
    ">
        <div style="font-size:11px;color:var(--ms-texto-sec);letter-spacing:.6px;text-transform:uppercase;margin-bottom:4px;">{icone} {label}</div>
        <div style="font-size:28px;font-weight:700;color:{cor_valor};line-height:1.1;">{valor}</div>
        {sub_html}
    </div>
    """


def _velocimetro(pct, label="Meta", meta_pts=0, atual_pts=0):
    """Renderiza velocímetro SVG de meia-lua."""
    pct_clip  = min(max(pct, 0), 100)
    angulo    = -180 + (pct_clip / 100) * 180  # -180° a 0°
    rad       = math.radians(angulo)
    cx, cy, r = 110, 110, 80

    # Ponteiro
    px = cx + r * math.cos(rad)
    py = cy + r * math.sin(rad)

    # Cor do arco conforme progresso
    if pct_clip >= 80:   cor = "#27AE60"
    elif pct_clip >= 50: cor = "#F39C12"
    else:                cor = "#C0392B"

    return f"""
    <div style="text-align:center;">
        <svg viewBox="0 0 220 130" width="100%" style="max-width:260px;">
            <!-- Arco fundo -->
            <path d="M 30 110 A 80 80 0 0 1 190 110" fill="none" stroke="var(--ms-metric-bd)" stroke-width="18" stroke-linecap="round"/>
            <!-- Arco progresso -->
            <path d="M 30 110 A 80 80 0 0 1 190 110" fill="none" stroke="{cor}" stroke-width="18"
                  stroke-linecap="round"
                  stroke-dasharray="{pct_clip * 2.513} 251.3"
                  transform="rotate(0, 110, 110)"/>
            <!-- Ponteiro -->
            <line x1="{cx}" y1="{cy}" x2="{px:.1f}" y2="{py:.1f}"
                  stroke="var(--ms-texto)" stroke-width="2.5" stroke-linecap="round"/>
            <circle cx="{cx}" cy="{cy}" r="5" fill="var(--ms-texto)"/>
            <!-- Percentual -->
            <text x="110" y="100" text-anchor="middle" font-size="22" font-weight="700" fill="var(--ms-texto)">{pct_clip:.0f}%</text>
            <text x="110" y="120" text-anchor="middle" font-size="11" fill="var(--ms-texto-sec)">{atual_pts:.0f} / {meta_pts} pts</text>
        </svg>
        <div style="font-size:12px;color:var(--ms-texto-sec);letter-spacing:.5px;text-transform:uppercase;margin-top:-4px;">{label}</div>
    </div>
    """


def _barra_membro(nome, pts, meta, penalidade):
    saldo  = pts - penalidade
    pct    = min((saldo / meta * 100), 100) if meta > 0 else 0
    cor    = "#27AE60" if pct >= 80 else ("#F39C12" if pct >= 50 else "#C0392B")
    return f"""
    <div style="margin-bottom:14px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
            <span style="font-size:13px;font-weight:600;color:var(--ms-texto);">{nome}</span>
            <span style="font-size:12px;color:var(--ms-texto-sec);">{saldo:.0f} / {meta:.0f} pts</span>
        </div>
        <div style="background:var(--ms-metric-bd);border-radius:6px;height:10px;overflow:hidden;">
            <div style="background:{cor};width:{pct:.1f}%;height:100%;border-radius:6px;transition:width .4s;"></div>
        </div>
        {"" if penalidade == 0 else f'<div style="font-size:10px;color:#C0392B;margin-top:2px;">⚠ -{penalidade:.0f} pts em penalidades</div>'}
    </div>
    """


# ── PÁGINA PRINCIPAL ──────────────────────────────────────────────────────────

def pagina_placar(usuario_logado):
    eh_master = usuario_logado in MASTERS
    eh_membro = usuario_logado in MEMBROS_ATIVOS

    st.markdown("## 🏆 Placar & Metas")

    # ── VERIFICAÇÃO DE CREDENCIAIS ────────────────────────────────────────────
    if not TRELLO_KEY or not TRELLO_TOKEN or not BOARD_ID:
        st.error("Credenciais do Trello não configuradas. Adicione `[trello]` no secrets.toml.")
        st.code("""
[trello]
api_key  = "SUA_API_KEY"
token    = "SEU_TOKEN"
board_id = "ID_DO_BOARD"
        """)
        return

    # ── CABEÇALHO E FILTROS ───────────────────────────────────────────────────
    col_titulo, col_att = st.columns([5, 1])
    with col_att:
        if st.button("🔄 Atualizar", use_container_width=True):
            _buscar_board.clear()
            st.rerun()

    # ── BUSCA DE DADOS ────────────────────────────────────────────────────────
    with st.spinner("Buscando dados do Trello..."):
        dados_api = _buscar_board()

    if dados_api is None or dados_api[0] is None:
        st.error("Não foi possível conectar ao Trello. Verifique as credenciais.")
        return

    listas, cards, membros_map, id_campo_pontos, id_campo_interrompido = dados_api

    # ── META (configurável pelo master) ───────────────────────────────────────
    st.markdown("---")
    with st.expander("⚙️ Configurar Metas", expanded=False):
        if eh_master:
            col_m1, col_m2 = st.columns(2)
            meta_equipe = col_m1.number_input("Meta da equipe (pts/mês)", min_value=0, value=st.session_state.get("meta_equipe", 5000), step=100, key="meta_equipe")
            meta_ind    = col_m2.number_input("Meta individual (pts/mês)", min_value=0, value=st.session_state.get("meta_individual", 1500), step=100, key="meta_individual")
        else:
            meta_equipe = st.session_state.get("meta_equipe", 5000)
            meta_ind    = st.session_state.get("meta_individual", 1500)
            st.info("Metas configuradas pelo gestor.")

    meta_equipe = st.session_state.get("meta_equipe", 5000)
    meta_ind    = st.session_state.get("meta_individual", 1500)

    # ── PROCESSAMENTO ─────────────────────────────────────────────────────────
    dados = _processar_dados(listas, cards, membros_map, id_campo_pontos, id_campo_interrompido)

    pts_equipe   = dados["pontuacao_equipe"]
    pen_total    = dados["penalidade_total"]
    saldo_equipe = pts_equipe - pen_total
    pct_equipe   = (saldo_equipe / meta_equipe * 100) if meta_equipe > 0 else 0

    # ════════════════════════════════════════════════════════════════════════════
    # BLOCO 1 — VELOCÍMETRO + MÉTRICAS PRINCIPAIS
    # ════════════════════════════════════════════════════════════════════════════
    col_vel, col_metricas = st.columns([2, 3])

    with col_vel:
        st.markdown(
            _velocimetro(pct_equipe, "META DA EQUIPE", meta_pts=meta_equipe, atual_pts=saldo_equipe),
            unsafe_allow_html=True
        )

    with col_metricas:
        r1c1, r1c2, r1c3 = st.columns(3)
        r1c1.markdown(_card_metrica("Pontuação Atual", f"{saldo_equipe:.0f}", f"Meta: {meta_equipe}", cor_valor="#27AE60" if pct_equipe >= 80 else "#F39C12"), unsafe_allow_html=True)
        r1c2.markdown(_card_metrica("Cartões em Aberto", dados["cards_abertos"], icone="📋"), unsafe_allow_html=True)
        r1c3.markdown(_card_metrica("Penalidades", f"-{pen_total:.0f} pts", f"{len(dados['penalidades_cards'])} ocorrências", cor_valor="#C0392B" if pen_total > 0 else "var(--ms-texto)", icone="⚠️"), unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════════════
    # BLOCO 2 — STATUS DOS CARTÕES
    # ════════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("#### 📊 Status dos Cartões")

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.markdown(_card_metrica("Urgentes",        dados["cards_urgentes"],     icone="🚨", cor_valor="#C0392B" if dados["cards_urgentes"] > 0 else "var(--ms-texto)"), unsafe_allow_html=True)
    c2.markdown(_card_metrica("Atrasados",       dados["cards_atrasados"],    icone="⏰", cor_valor="#C0392B" if dados["cards_atrasados"] > 0 else "var(--ms-texto)"), unsafe_allow_html=True)
    c3.markdown(_card_metrica("Em Andamento",    dados["cards_em_andamento"], icone="▶️"), unsafe_allow_html=True)
    c4.markdown(_card_metrica("Falta Conferir",  dados["cards_falta_conf"],   icone="🔍"), unsafe_allow_html=True)
    c5.markdown(_card_metrica("Falta Info",      dados["cards_falta_info"],   icone="❓"), unsafe_allow_html=True)
    c6.markdown(_card_metrica("Sem Membro",      dados["cards_sem_membro"],   icone="👤", cor_valor="#F39C12" if dados["cards_sem_membro"] > 0 else "var(--ms-texto)"), unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════════════
    # BLOCO 3 — PONTUAÇÃO POR COLABORADOR
    # ════════════════════════════════════════════════════════════════════════════
    st.markdown("---")

    if eh_master:
        st.markdown("#### 👥 Desempenho por Colaborador")
        barras_html = ""
        for username, nome_exib in MEMBROS_ATIVOS.items():
            pts  = dados["pontuacao_por_membro"].get(username, 0)
            pen  = dados["penalidades_por_membro"].get(username, 0)
            barras_html += _barra_membro(nome_exib, pts, meta_ind, pen)
        st.markdown(f'<div style="padding:8px 0;">{barras_html}</div>', unsafe_allow_html=True)

    elif eh_membro:
        st.markdown(f"#### Seu Desempenho")
        pts  = dados["pontuacao_por_membro"].get(usuario_logado, 0)
        pen  = dados["penalidades_por_membro"].get(usuario_logado, 0)
        saldo_ind = pts - pen
        pct_ind   = (saldo_ind / meta_ind * 100) if meta_ind > 0 else 0
        col_vind, col_mind = st.columns([2, 3])
        with col_vind:
            st.markdown(_velocimetro(pct_ind, "SUA META", meta_pts=meta_ind, atual_pts=saldo_ind), unsafe_allow_html=True)
        with col_mind:
            nome_exib = MEMBROS_ATIVOS.get(usuario_logado, usuario_logado)
            st.markdown(_barra_membro(nome_exib, pts, meta_ind, pen), unsafe_allow_html=True)
            if pen > 0:
                st.warning(f"Você tem {pen:.0f} pts em penalidades este mês.")

    # ════════════════════════════════════════════════════════════════════════════
    # BLOCO 4 — CARTÕES PENDENTES POR COLUNA
    # ════════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    col_pend, col_pts_pend = st.columns(2)

    with col_pend:
        st.markdown("#### 🟠 Pendentes por Coluna")
        if dados["cards_por_lista_pendente"]:
            for lista, qtd in sorted(dados["cards_por_lista_pendente"].items(), key=lambda x: -x[1]):
                pct_barra = min(qtd / max(dados["cards_por_lista_pendente"].values()) * 100, 100)
                st.markdown(f"""
                <div style="margin-bottom:10px;">
                    <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--ms-texto);margin-bottom:3px;">
                        <span>{lista[:40]}</span><span style="font-weight:700;">{qtd}</span>
                    </div>
                    <div style="background:var(--ms-metric-bd);border-radius:4px;height:6px;">
                        <div style="background:#F39C12;width:{pct_barra:.0f}%;height:100%;border-radius:4px;"></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:var(--ms-texto-sec);font-size:13px;">Nenhum cartão pendente 🎉</div>', unsafe_allow_html=True)

    with col_pts_pend:
        st.markdown("#### 💰 Pontos em Aberto")
        st.markdown(_card_metrica(
            "Pts nos cartões Pendentes",
            f"{dados['pontos_pendentes']:.0f}",
            "Pontuação que ainda não foi conquistada",
            icone="🟠"
        ), unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown("#### ▶️ Em Andamento Agora")
        if dados["cards_em_andamento_lista"]:
            for c in dados["cards_em_andamento_lista"][:5]:
                membros_str = ", ".join(MEMBROS_ATIVOS.get(u, u) for u in c["membros"]) or "—"
                st.markdown(f"""
                <div style="
                    background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);
                    border-radius:8px;padding:10px 14px;margin-bottom:6px;
                ">
                    <div style="font-size:12px;font-weight:600;color:var(--ms-texto);">{c['card'][:50]}</div>
                    <div style="font-size:10px;color:var(--ms-texto-sec);margin-top:2px;">{c['lista']} · {membros_str}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:var(--ms-texto-sec);font-size:13px;">Nenhum cartão em andamento.</div>', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════════════
    # BLOCO 5 — PENALIDADES (só master)
    # ════════════════════════════════════════════════════════════════════════════
    if eh_master and dados["penalidades_cards"]:
        st.markdown("---")
        st.markdown("#### ⚠️ Registro de Penalidades")
        for p in dados["penalidades_cards"]:
            membros_str = ", ".join(MEMBROS_ATIVOS.get(u, u) for u in p["membros"]) or "Sem membro"
            st.markdown(f"""
            <div style="
                background:var(--ms-metric-bg);border:1px solid #C0392B;
                border-radius:8px;padding:10px 14px;margin-bottom:6px;
            ">
                <div style="display:flex;justify-content:space-between;">
                    <span style="font-size:12px;font-weight:600;color:var(--ms-texto);">{p['card'][:60]}</span>
                    <span style="font-size:13px;font-weight:700;color:#C0392B;">-{p['valor']:.0f} pts</span>
                </div>
                <div style="font-size:10px;color:var(--ms-texto-sec);margin-top:2px;">{membros_str}</div>
            </div>
            """, unsafe_allow_html=True)

    # ── RODAPÉ ────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.caption(f"Dados atualizados a cada 2 minutos · Última consulta: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
