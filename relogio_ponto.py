"""
relogio_ponto.py — Módulo de Relógio de Ponto para MS Studio

Responsabilidades:
  1. Armazenar registros de ponto no Google Sheets (aba "ponto")
  2. UI Streamlit para registro de: entrada, saída almoço, volta almoço, fim expediente, ausência
  3. Calcular: horas disponíveis, ociosidade e tolerâncias utilizadas por colaborador/dia
  4. Prover dados exportáveis para analise_metas.py
  5. [MASTER ONLY] Relatório RHiD: atrasos, desempenho, banco de horas e ociosidade via API
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date, time, timedelta
from typing import Optional

import placar_core as _pc
import rhid_api as _rhid

# ── Constantes ─────────────────────────────────────────────────────────────────
MEMBROS = _pc.MEMBROS_ATIVOS          # {"username": "Nome", ...}
MASTERS = _pc.MASTERS                 # {"martinsousa", "renan"}

# Horário padrão de expediente (usado para cálculo de tolerância)
ENTRADA_ESPERADA  = time(8,  0)
SAIDA_ALMOCO      = time(12, 0)
VOLTA_ALMOCO      = time(13, 0)
FIM_EXPEDIENTE    = time(17, 0)
TOLERANCIA_MINUTOS = 10               # atraso ≤ 10 min não é tolerância registrada

TIPOS_PONTO = {
    "entrada":        "🟢 Entrada",
    "saida_almoco":   "🍽️ Saída Almoço",
    "volta_almoco":   "↩️ Volta Almoço",
    "fim_expediente": "🔴 Fim de Expediente",
    "ausencia":       "⛔ Ausência",
}

# ── Google Sheets ──────────────────────────────────────────────────────────────

PLANILHA_NOME = "MartinSousa - Financeiro"
ABA_PONTO     = "ponto"
COLUNAS_PONTO = ["data", "username", "tipo", "horario", "observacao", "criado_em", "criado_por"]


def _cliente_gs():
    creds_dict = dict(st.secrets["gcp_service_account"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)


def _aba_ponto():
    """Retorna a aba 'ponto' da planilha, criando-a se necessário."""
    cliente = _cliente_gs()
    planilha = cliente.open(PLANILHA_NOME)
    try:
        aba = planilha.worksheet(ABA_PONTO)
        # Garante que todas as colunas existem no cabeçalho
        cabecalho = aba.row_values(1)
        for col in COLUNAS_PONTO:
            if col not in cabecalho:
                aba.add_cols(1)
                col_idx = len(cabecalho) + 1
                aba.update_cell(1, col_idx, col)
                cabecalho.append(col)
        return aba
    except gspread.exceptions.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA_PONTO, rows=5000, cols=len(COLUNAS_PONTO))
        aba.append_row(COLUNAS_PONTO, value_input_option="RAW")
        return aba


@st.cache_data(ttl=30)
def _carregar_ponto_todos() -> list[dict]:
    """Carrega todos os registros de ponto do Google Sheets (cache de 30 s)."""
    aba = _aba_ponto()
    registros = aba.get_all_records(value_render_option="UNFORMATTED_VALUE")
    resultado = []
    for r in registros:
        resultado.append({
            "data":       str(r.get("data",       "")).strip(),
            "username":   str(r.get("username",   "")).strip(),
            "tipo":       str(r.get("tipo",        "")).strip(),
            "horario":    str(r.get("horario",    "")).strip() or None,
            "observacao": str(r.get("observacao", "")).strip() or None,
            "criado_em":  str(r.get("criado_em",  "")).strip(),
            "criado_por": str(r.get("criado_por", "")).strip(),
        })
    return resultado


def _get_registros(data_str: str, username: Optional[str] = None) -> list[dict]:
    """Retorna registros de ponto de uma data (YYYY-MM-DD), opcionalmente filtrado por usuário."""
    todos = _carregar_ponto_todos()
    regs  = [r for r in todos if r["data"] == data_str]
    if username:
        regs = [r for r in regs if r["username"] == username]
    regs.sort(key=lambda r: (r["username"], r["horario"] or "99:99"))
    return regs


def _get_registros_periodo(ano: int, mes: int) -> list[dict]:
    """Retorna todos os registros de ponto de um mês (ano, mes)."""
    prefixo = f"{ano:04d}-{mes:02d}"
    todos   = _carregar_ponto_todos()
    regs    = [r for r in todos if r["data"].startswith(prefixo)]
    regs.sort(key=lambda r: (r["data"], r["username"], r["horario"] or "99:99"))
    return regs


def _salvar_registro(data_str, username, tipo, horario_str, observacao, criado_por):
    """Upsert: atualiza linha existente ou adiciona nova linha no Google Sheets."""
    try:
        aba       = _aba_ponto()
        criado_em = datetime.now().strftime("%d/%m/%Y %H:%M")
        nova_linha = [
            data_str, username, tipo,
            horario_str or "", observacao or "",
            criado_em, criado_por,
        ]
        all_vals = aba.get_all_values()          # inclui cabeçalho na posição 0
        for i, row in enumerate(all_vals[1:], start=2):   # 1-based, pula cabeçalho
            if (len(row) >= 3
                    and row[0] == data_str
                    and row[1] == username
                    and row[2] == tipo):
                aba.update(f"A{i}:G{i}", [nova_linha], value_input_option="RAW")
                _carregar_ponto_todos.clear()
                return
        aba.append_row(nova_linha, value_input_option="RAW")
        _carregar_ponto_todos.clear()
    except Exception:
        pass


def _deletar_registro(data_str, username, tipo):
    """Remove uma linha do Google Sheets que corresponde a (data, username, tipo)."""
    try:
        aba      = _aba_ponto()
        all_vals = aba.get_all_values()
        for i, row in enumerate(all_vals[1:], start=2):
            if (len(row) >= 3
                    and row[0] == data_str
                    and row[1] == username
                    and row[2] == tipo):
                aba.delete_rows(i)
                _carregar_ponto_todos.clear()
                return
    except Exception:
        pass


# ── Cálculo de indicadores ─────────────────────────────────────────────────────

def _parse_horario(h: Optional[str]) -> Optional[time]:
    if not h:
        return None
    try:
        parts = h.split(":")
        return time(int(parts[0]), int(parts[1]))
    except Exception:
        return None


def _diff_min(t1: Optional[time], t2: Optional[time]) -> float:
    """Diferença em minutos (t2 - t1). Retorna 0 se inválido."""
    if not t1 or not t2:
        return 0.0
    dt1 = datetime.combine(date.today(), t1)
    dt2 = datetime.combine(date.today(), t2)
    return max((dt2 - dt1).total_seconds() / 60, 0)


def calcular_indicadores_dia(regs: list[dict]) -> dict:
    """
    Recebe lista de registros de um dia para um único colaborador.
    Retorna dict com:
      - ausente (bool)
      - entrada, saida_almoco, volta_almoco, fim_expediente (time|None)
      - horas_disponiveis (float, minutos)
      - duracao_almoco (float, minutos)
      - tolerancia_min (float — minutos de atraso acima da tolerância base)
      - saiu_cedo_min (float — minutos antes do fim esperado)
    """
    r = {
        "ausente":          False,
        "entrada":          None,
        "saida_almoco":     None,
        "volta_almoco":     None,
        "fim_expediente":   None,
        "horas_disponiveis": 0.0,
        "duracao_almoco":   0.0,
        "tolerancia_min":   0.0,
        "saiu_cedo_min":    0.0,
    }
    tipos = {reg["tipo"]: reg for reg in regs}

    if "ausencia" in tipos:
        r["ausente"] = True
        return r

    r["entrada"]        = _parse_horario(tipos.get("entrada",        {}).get("horario"))
    r["saida_almoco"]   = _parse_horario(tipos.get("saida_almoco",   {}).get("horario"))
    r["volta_almoco"]   = _parse_horario(tipos.get("volta_almoco",   {}).get("horario"))
    r["fim_expediente"] = _parse_horario(tipos.get("fim_expediente", {}).get("horario"))

    # Duração almoço
    r["duracao_almoco"] = _diff_min(r["saida_almoco"], r["volta_almoco"])

    # Horas disponíveis = (fim - entrada) - almoço
    total_periodo = _diff_min(r["entrada"], r["fim_expediente"])
    r["horas_disponiveis"] = max(total_periodo - r["duracao_almoco"], 0)

    # Tolerância de entrada (atraso acima do limite de tolerância)
    if r["entrada"]:
        entrada_min = _diff_min(ENTRADA_ESPERADA, r["entrada"])   # > 0 se atrasado
        r["tolerancia_min"] = max(entrada_min - TOLERANCIA_MINUTOS, 0)

    # Saiu cedo (antes do fim esperado)
    if r["fim_expediente"]:
        r["saiu_cedo_min"] = max(_diff_min(r["fim_expediente"], FIM_EXPEDIENTE), 0)

    return r


def calcular_resumo_mes(ano: int, mes: int) -> dict:
    """
    Retorna dict {username: resumo_mensal} com:
      - dias_trabalhados, dias_ausentes, total_horas_disp (min),
        total_tolerancia_min, total_saiu_cedo_min
      - detalhes: [{data, ...indicadores_dia}]
    """
    regs = _get_registros_periodo(ano, mes)

    # Agrupa por data → username → lista de registros
    from collections import defaultdict
    por_data_user: dict = defaultdict(lambda: defaultdict(list))
    for reg in regs:
        por_data_user[reg["data"]][reg["username"]].append(reg)

    # Inicializa resumo para todos os membros
    resumo = {
        u: {
            "dias_trabalhados":    0,
            "dias_ausentes":       0,
            "total_horas_disp":    0.0,  # em minutos
            "total_tolerancia_min": 0.0,
            "total_saiu_cedo_min":  0.0,
            "detalhes":            [],
        }
        for u in MEMBROS
    }

    for data_str, users in sorted(por_data_user.items()):
        for username, rlist in users.items():
            if username not in resumo:
                continue
            ind = calcular_indicadores_dia(rlist)
            if ind["ausente"]:
                resumo[username]["dias_ausentes"] += 1
            else:
                resumo[username]["dias_trabalhados"]    += 1
                resumo[username]["total_horas_disp"]    += ind["horas_disponiveis"]
                resumo[username]["total_tolerancia_min"] += ind["tolerancia_min"]
                resumo[username]["total_saiu_cedo_min"]  += ind["saiu_cedo_min"]
            resumo[username]["detalhes"].append({"data": data_str, **ind})

    return resumo


def get_ausencias_hoje(data_str: Optional[str] = None) -> list[str]:
    """Retorna lista de usernames ausentes hoje (ou na data informada)."""
    d = data_str or date.today().isoformat()
    regs = _get_registros(d)
    ausentes = [r["username"] for r in regs if r["tipo"] == "ausencia"]
    # Presentes são quem registrou qualquer ponto que não seja ausência
    presentes = {r["username"] for r in regs if r["tipo"] != "ausencia"}
    # Quem não registrou nada não sabemos — retornamos só quem explicitamente marcou ausência
    return ausentes


def get_disponiveis_agora(data_str: Optional[str] = None) -> dict:
    """
    Retorna dict {username: status} onde status é:
      'disponivel' | 'almoco' | 'encerrado' | 'ausente' | 'nao_registrado'
    """
    d = data_str or date.today().isoformat()
    regs = _get_registros(d)
    agora = datetime.now().time()

    resultado = {u: "nao_registrado" for u in MEMBROS}

    por_user: dict = {}
    for reg in regs:
        por_user.setdefault(reg["username"], []).append(reg)

    for u, rlist in por_user.items():
        if u not in resultado:
            continue
        tipos = {r["tipo"]: r for r in rlist}
        if "ausencia" in tipos:
            resultado[u] = "ausente"
        elif "fim_expediente" in tipos:
            fim = _parse_horario(tipos["fim_expediente"]["horario"])
            resultado[u] = "encerrado" if (fim and agora >= fim) else "disponivel"
        elif "volta_almoco" in tipos:
            resultado[u] = "disponivel"
        elif "saida_almoco" in tipos:
            resultado[u] = "almoco"
        elif "entrada" in tipos:
            resultado[u] = "disponivel"

    return resultado


# ── Interface Streamlit ────────────────────────────────────────────────────────

def _cor_status(status: str) -> str:
    return {
        "disponivel":    "#1BAF7A",
        "almoco":        "#EDA100",
        "encerrado":     "#888888",
        "ausente":       "#E34948",
        "nao_registrado":"#555555",
    }.get(status, "#555555")


def _label_status(status: str) -> str:
    return {
        "disponivel":    "✅ Disponível",
        "almoco":        "🍽️ Almoço",
        "encerrado":     "🏠 Encerrado",
        "ausente":       "⛔ Ausente",
        "nao_registrado":"❓ Não registrado",
    }.get(status, status)


def _fmt_min(m: float) -> str:
    if m <= 0:
        return "0 min"
    h = int(m // 60); mm = int(m % 60)
    if h > 0 and mm > 0:
        return f"{h}h{mm:02d}"
    elif h > 0:
        return f"{h}h"
    return f"{mm}min"


def _secao_status_hoje():
    """Painel de status atual de todos os colaboradores."""
    hoje = date.today().isoformat()
    status_map = get_disponiveis_agora(hoje)
    regs = _get_registros(hoje)

    # Calcula indicadores por usuário
    por_user: dict = {}
    for reg in regs:
        por_user.setdefault(reg["username"], []).append(reg)

    cards = []
    for username, nome in MEMBROS.items():
        status = status_map.get(username, "nao_registrado")
        cor = _cor_status(status)
        label_s = _label_status(status)

        rlist = por_user.get(username, [])
        ind = calcular_indicadores_dia(rlist) if rlist else None

        # Horários registrados
        tipos = {r["tipo"]: r.get("horario", "") for r in rlist}
        linha_h = "  ·  ".join(
            f"{TIPOS_PONTO[t].split(' ', 1)[0]} {h}"
            for t, h in tipos.items()
            if h
        ) or "Nenhum registro hoje"

        horas_str = _fmt_min(ind["horas_disponiveis"]) if ind and not ind["ausente"] else "—"

        cards.append(
            f'<div style="background:var(--ms-metric-bg);border:1px solid var(--ms-divisor);'
            f'border-radius:8px;padding:12px 14px;border-left:3px solid {cor};">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">'
            f'<span style="font-size:13px;font-weight:700;color:var(--ms-texto);">{nome}</span>'
            f'<span style="font-size:11px;font-weight:600;color:{cor};">{label_s}</span></div>'
            f'<div style="font-size:10px;color:var(--ms-texto-sec);">{linha_h}</div>'
            f'<div style="font-size:9px;color:var(--ms-texto-sec);margin-top:4px;">Disponível hoje: <b style="color:var(--ms-texto);">{horas_str}</b></div>'
            f'</div>'
        )

    st.markdown(
        f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:8px;">'
        + "".join(cards) + '</div>',
        unsafe_allow_html=True
    )

    # Alerta de ausência / sobrecarga
    ausentes = [MEMBROS[u] for u, s in status_map.items() if s == "ausente"]
    if ausentes:
        total = len(MEMBROS)
        presentes = total - len(ausentes)
        st.warning(
            f"⚠️ **{', '.join(ausentes)}** {'está' if len(ausentes)==1 else 'estão'} ausente{'s' if len(ausentes)>1 else ''} hoje. "
            f"A demanda será distribuída entre {presentes} colaborador{'es' if presentes>1 else ''}. "
            f"Fique atento à carga de trabalho."
        )


def _secao_registro(usuario_logado: str, eh_master: bool):
    """Formulário de registro de ponto."""
    hoje = date.today()

    col_data, col_user = st.columns([1, 2])
    data_sel = col_data.date_input("📅 Data", value=hoje, max_value=hoje, key="pt_data")
    data_str = data_sel.isoformat()

    if eh_master:
        usernames = list(MEMBROS.keys())
        nomes_disp = [MEMBROS[u] for u in usernames]
        nome_sel = col_user.selectbox("👤 Colaborador", nomes_disp, key="pt_user")
        username_sel = usernames[nomes_disp.index(nome_sel)]
    else:
        # Mapeia login do app para username Trello
        _LOGIN_MAP = {"Myrella": "myrelladesouza", "Beatriz": "beatriz51",
                      "Gabriel": "gabriel_borges", "MartinSousa": "martinsousa"}
        username_sel = _LOGIN_MAP.get(usuario_logado, usuario_logado.lower())
        nome_sel = MEMBROS.get(username_sel, usuario_logado)
        col_user.info(f"Registrando para: **{nome_sel}**")

    # Registros já existentes nesse dia/pessoa
    regs_existentes = {r["tipo"]: r for r in _get_registros(data_str, username_sel)}
    ind_existente   = calcular_indicadores_dia(list(regs_existentes.values())) if regs_existentes else None

    st.markdown("##### Registrar horário")

    tipo_opts = list(TIPOS_PONTO.keys())
    tipo_labels = [TIPOS_PONTO[t] for t in tipo_opts]

    with st.form("form_ponto", clear_on_submit=True):
        col_tipo, col_hora, col_obs = st.columns([2, 1, 3])
        tipo_label = col_tipo.selectbox("Tipo", tipo_labels, key="pt_tipo")
        tipo_sel = tipo_opts[tipo_labels.index(tipo_label)]

        horario_default = {
            "entrada":        ENTRADA_ESPERADA,
            "saida_almoco":   SAIDA_ALMOCO,
            "volta_almoco":   VOLTA_ALMOCO,
            "fim_expediente": FIM_EXPEDIENTE,
            "ausencia":       None,
        }[tipo_sel]

        if tipo_sel != "ausencia":
            hora_val = col_hora.time_input(
                "Horário", value=horario_default or time(8, 0), key="pt_hora"
            )
            hora_str = hora_val.strftime("%H:%M")
        else:
            hora_str = None
            col_hora.markdown(" ")

        obs = col_obs.text_input("Observação (opcional)", key="pt_obs", placeholder="ex.: problema de transporte")

        salvar = st.form_submit_button("💾 Registrar ponto", use_container_width=True)
        if salvar:
            _salvar_registro(data_str, username_sel, tipo_sel, hora_str, obs, usuario_logado)
            st.success(f"✅ {TIPOS_PONTO[tipo_sel]} registrado para **{nome_sel}** em {data_str}" +
                       (f" às {hora_str}" if hora_str else "") + ".")
            st.rerun()

    # Exibe registros do dia selecionado
    if regs_existentes:
        st.markdown(f"**Registros em {data_str} — {nome_sel}:**")
        for tipo, reg in regs_existentes.items():
            h = reg.get("horario", "—") or "—"
            obs_txt = f"  ·  _{reg['observacao']}_" if reg.get("observacao") else ""
            col_r, col_del = st.columns([5, 1])
            col_r.markdown(f"{TIPOS_PONTO[tipo]}  **{h}**{obs_txt}")
            if eh_master and col_del.button("🗑️", key=f"del_{tipo}_{data_str}_{username_sel}", help="Remover"):
                _deletar_registro(data_str, username_sel, tipo)
                st.rerun()

        if ind_existente and not ind_existente["ausente"]:
            disp = ind_existente["horas_disponiveis"]
            tol  = ind_existente["tolerancia_min"]
            alm  = ind_existente["duracao_almoco"]
            st.markdown(
                f'<div style="background:var(--ms-metric-bg);border-radius:6px;padding:8px 14px;'
                f'margin-top:6px;font-size:11px;display:flex;gap:24px;">'
                f'<span>⏱️ Disponível: <b>{_fmt_min(disp)}</b></span>'
                f'<span>🍽️ Almoço: <b>{_fmt_min(alm)}</b></span>'
                f'<span>⏰ Tolerância usada: <b>{_fmt_min(tol)}</b></span>'
                f'</div>',
                unsafe_allow_html=True
            )


def _secao_historico_mensal(eh_master: bool, usuario_logado: str):
    """Resumo mensal de ponto por colaborador."""
    agora = datetime.now()
    col_a, col_m, _ = st.columns([1, 2, 3])
    ano_sel = col_a.selectbox("Ano", list(range(agora.year, agora.year - 3, -1)), key="pt_h_ano")
    mes_opts = [_pc.MESES_PT[m] for m in range(1, 13)]
    mes_sel  = col_m.selectbox("Mês", mes_opts, index=agora.month - 1, key="pt_h_mes")
    mes_num  = mes_opts.index(mes_sel) + 1

    resumo = calcular_resumo_mes(ano_sel, mes_num)

    if not any(r["dias_trabalhados"] + r["dias_ausentes"] > 0 for r in resumo.values()):
        st.caption(f"Nenhum registro de ponto em {mes_sel} {ano_sel}.")
        return

    # Mostra apenas o colaborador logado (se não for master)
    _LOGIN_MAP = {"Myrella": "myrelladesouza", "Beatriz": "beatriz51",
                  "Gabriel": "gabriel_borges", "MartinSousa": "martinsousa"}
    u_logado = _LOGIN_MAP.get(usuario_logado, usuario_logado.lower())

    for username, nome in MEMBROS.items():
        if not eh_master and username != u_logado:
            continue
        r = resumo[username]
        if r["dias_trabalhados"] + r["dias_ausentes"] == 0:
            continue

        with st.expander(f"📋 {nome} — {r['dias_trabalhados']} dias trabalhados, {r['dias_ausentes']} ausências", expanded=False):
            total_h = _fmt_min(r["total_horas_disp"])
            media_h = _fmt_min(r["total_horas_disp"] / max(r["dias_trabalhados"], 1))
            tol_t   = _fmt_min(r["total_tolerancia_min"])

            st.markdown(
                f'<div style="display:flex;gap:20px;margin-bottom:10px;flex-wrap:wrap;">'
                f'<span style="font-size:12px;">⏱️ Total disponível: <b>{total_h}</b></span>'
                f'<span style="font-size:12px;">📊 Média/dia: <b>{media_h}</b></span>'
                f'<span style="font-size:12px;">⏰ Tolerâncias: <b>{tol_t}</b></span>'
                f'</div>',
                unsafe_allow_html=True
            )

            if r["detalhes"]:
                linhas = []
                for det in r["detalhes"]:
                    data_fmt = det["data"][8:] + "/" + det["data"][5:7]  # DD/MM
                    if det["ausente"]:
                        linhas.append(f"| {data_fmt} | ⛔ Ausente | — | — | — | — |")
                    else:
                        ent  = det["entrada"].strftime("%H:%M")  if det["entrada"]        else "—"
                        alm  = det["saida_almoco"].strftime("%H:%M") if det["saida_almoco"] else "—"
                        vlt  = det["volta_almoco"].strftime("%H:%M") if det["volta_almoco"] else "—"
                        fim  = det["fim_expediente"].strftime("%H:%M") if det["fim_expediente"] else "—"
                        disp = _fmt_min(det["horas_disponiveis"])
                        linhas.append(f"| {data_fmt} | {ent} | {alm} | {vlt} | {fim} | {disp} |")

                md = "| Data | Entrada | S. Almoço | V. Almoço | Saída | Disponível |\n"
                md += "|---|---|---|---|---|---|\n"
                md += "\n".join(linhas)
                st.markdown(md)


# ── Dados para analise_metas.py ────────────────────────────────────────────────

def get_ociosidade_mes(ano: int, mes: int, tempo_cards_por_user: dict) -> dict:
    """
    Calcula ociosidade por colaborador no mês.

    tempo_cards_por_user: {username: minutos_em_cards}
      — vem de analise_metas._processar()["tempo_lista"] filtrado por membro.
      Se não disponível, passa dict vazio.

    Retorna {username: {"horas_disp_min": float, "tempo_cards_min": float,
                        "ociosidade_min": float, "pct_ocioso": float}}
    """
    resumo = calcular_resumo_mes(ano, mes)
    resultado = {}
    for u in MEMBROS:
        hd   = resumo[u]["total_horas_disp"]          # minutos disponíveis
        tc   = tempo_cards_por_user.get(u, 0)         # minutos em cards (Trello)
        ocio = max(hd - tc, 0)
        pct  = (ocio / hd * 100) if hd > 0 else 0
        resultado[u] = {
            "horas_disp_min": hd,
            "tempo_cards_min": tc,
            "ociosidade_min": ocio,
            "pct_ocioso": pct,
            "dias_trabalhados": resumo[u]["dias_trabalhados"],
            "dias_ausentes": resumo[u]["dias_ausentes"],
            "total_tolerancia_min": resumo[u]["total_tolerancia_min"],
        }
    return resultado


# ── Relatório RHiD (só para masters) ──────────────────────────────────────────

# Mapeamento nome RHiD → username Trello (ajuste conforme nomes cadastrados na RHiD)
_RHID_TRELLO_MAP = {
    "myrella":      "myrelladesouza",
    "beatriz":      "beatriz51",
    "gabriel":      "gabriel_borges",
    "martinsousa":  "martinsousa",
    "martin":       "martinsousa",
}

# Horas esperadas por dia (em minutos)
_JORNADA_MINUTOS = 8 * 60  # 480 min = 8h


def _rhid_nome_para_trello(nome: str) -> Optional[str]:
    """Tenta mapear nome da RHiD para username Trello."""
    chave = nome.lower().split()[0]  # primeiro nome
    return _RHID_TRELLO_MAP.get(chave)


def _cor_atraso(min_atraso: float) -> str:
    if min_atraso <= 0:
        return "#1BAF7A"   # verde — no horário
    if min_atraso <= 15:
        return "#EDA100"   # amarelo — tolerável
    return "#E34948"       # vermelho — atraso relevante


def _cor_banco(saldo_min: float) -> str:
    if saldo_min >= 0:
        return "#1BAF7A"
    if saldo_min >= -60:
        return "#EDA100"
    return "#E34948"


def _secao_relatorio_rhid():
    """
    Relatório de ponto via RHiD API — exclusivo para masters.
    Mostra: atrasos, desempenho, banco de horas e ociosidade por colaborador.
    """
    # ── Seletor de período ────────────────────────────────────────────────────
    hoje = date.today()
    col_ini, col_fim, col_btn = st.columns([1, 1, 1])
    data_ini = col_ini.date_input(
        "De", value=hoje.replace(day=1), max_value=hoje, key="rhid_ini"
    )
    data_fim = col_fim.date_input(
        "Até", value=hoje, min_value=data_ini, max_value=hoje, key="rhid_fim"
    )

    # Limite da API: máximo 90 dias
    if (data_fim - data_ini).days > 90:
        st.error("⚠️ O intervalo máximo permitido pela API RHiD é 90 dias.")
        return

    atualizar = col_btn.button("🔄 Atualizar", use_container_width=True, key="rhid_atualizar")

    # Limpa caches ao atualizar (ou na primeira carga, se persons ainda não estiver em cache válido)
    if atualizar:
        _rhid.get_persons.clear()
        _rhid.invalidar_token()

    str_ini = data_ini.isoformat()
    str_fim = data_fim.isoformat()

    # ── Carrega colaboradores ─────────────────────────────────────────────────
    with st.spinner("Conectando à RHiD…"):
        token = _rhid.get_token()

    if not token:
        erro = st.session_state.get("rhid_login_error", "Erro desconhecido")
        st.error(f"❌ Não foi possível autenticar na RHiD: **{erro}**")
        st.caption("Verifique se `[rhid]` está configurado nos secrets do Railway.")
        if st.button("🔁 Tentar novamente", key="rhid_retry"):
            _rhid.invalidar_token()
            _rhid.get_persons.clear()
            st.rerun()
        return

    persons = _rhid.get_persons()
    if not persons:
        st.warning("Nenhum colaborador encontrado na RHiD.")
        if st.button("🔁 Recarregar colaboradores", key="rhid_reload_persons"):
            _rhid.get_persons.clear()
            st.rerun()
        # Debug: mostra resposta bruta da API
        debug_info = st.session_state.get("rhid_persons_debug")
        if debug_info:
            with st.expander("🔧 Debug — resposta bruta da API /person", expanded=True):
                st.json(debug_info)
        else:
            st.caption("ℹ️ Clique em Atualizar para carregar debug da API.")
        return

    # Filtra apenas colaboradores ativos
    persons_ativos = [p for p in persons if str(p.get("status", "1")) != "0"]

    st.caption(
        f"✅ Conectado à RHiD · {len(persons_ativos)} colaborador(es) · "
        f"Período: {data_ini.strftime('%d/%m')} a {data_fim.strftime('%d/%m/%Y')}"
    )

    # ── Busca apuração para cada colaborador ──────────────────────────────────
    dias_uteis = max(sum(
        1 for d in range((data_fim - data_ini).days + 1)
        if (data_ini + timedelta(days=d)).weekday() < 5
    ), 1)

    resultados = []

    prog = st.progress(0, text="Buscando dados de ponto…")
    for i, p in enumerate(persons_ativos):
        prog.progress((i + 1) / len(persons_ativos), text=f"Buscando: {p.get('name', '?')}")
        apuracao = _rhid.get_apuracao(str_ini, str_fim, int(p["id"]))

        # Extrai campos da apuração (estrutura pode variar entre versões da API)
        if apuracao and not apuracao.get("_raw"):
            # Campos comuns em APIs de ponto RHiD/ControlID
            horas_trab_min  = float(apuracao.get("horasTrabalhadas", apuracao.get("workedMinutes", 0)) or 0)
            banco_min       = float(apuracao.get("bancoHoras",        apuracao.get("bankMinutes",   0)) or 0)
            total_atrasos   = float(apuracao.get("totalAtrasos",      apuracao.get("lateMinutes",    0)) or 0)
            dias_presentes  = int(  apuracao.get("diasPresentes",     apuracao.get("workedDays",     0)) or 0)
            dias_ausentes   = int(  apuracao.get("diasAusentes",      apuracao.get("absentDays",     0)) or 0)

            # Se a API retornar tudo zero mas com dados brutos, tenta interpretar
            if horas_trab_min == 0 and isinstance(apuracao, dict):
                # Pode ser uma lista de registros diários
                registros = apuracao.get("registros", apuracao.get("records", apuracao.get("data", [])))
                if isinstance(registros, list) and registros:
                    for reg in registros:
                        horas_trab_min += float(reg.get("horasTrabalhadas", reg.get("workedMinutes", 0)) or 0)
                        banco_min      += float(reg.get("bancoHoras", reg.get("bankBalance", 0)) or 0)
                        total_atrasos  += float(reg.get("atraso", reg.get("lateMinutes", 0)) or 0)
                    dias_presentes = len([r for r in registros if not r.get("ausente", False)])
                    dias_ausentes  = len([r for r in registros if r.get("ausente", False)])
        else:
            horas_trab_min = 0
            banco_min      = 0
            total_atrasos  = 0
            dias_presentes = 0
            dias_ausentes  = 0
            apuracao       = apuracao or {}

        # Desempenho = horas trabalhadas / horas esperadas no período
        horas_esperadas = dias_uteis * _JORNADA_MINUTOS
        desempenho_pct  = (horas_trab_min / horas_esperadas * 100) if horas_esperadas > 0 else 0

        # Mapeamento para Trello
        trello_user = _rhid_nome_para_trello(p.get("name", ""))

        resultados.append({
            "id":            p["id"],
            "nome":          p.get("name", "—"),
            "trello_user":   trello_user,
            "horas_min":     horas_trab_min,
            "banco_min":     banco_min,
            "atraso_min":    total_atrasos,
            "dias_pres":     dias_presentes,
            "dias_aus":      dias_ausentes,
            "desempenho":    desempenho_pct,
            "apuracao_raw":  apuracao,
        })

    prog.empty()

    if not resultados:
        st.info("Nenhum dado de apuração retornado pela API.")
        return

    # ── Painel de cards por colaborador ──────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 👥 Resumo por Colaborador")

    for r in sorted(resultados, key=lambda x: x["nome"]):
        nome         = r["nome"]
        horas_str    = _rhid.fmt_horas(r["horas_min"])
        banco_str    = _rhid.fmt_banco(r["banco_min"])
        atraso_str   = _rhid.fmt_horas(r["atraso_min"]) if r["atraso_min"] > 0 else "Nenhum"
        desemp_str   = f"{r['desempenho']:.0f}%"
        cor_atraso   = _cor_atraso(r["atraso_min"])
        cor_banco    = _cor_banco(r["banco_min"])
        cor_desemp   = "#1BAF7A" if r["desempenho"] >= 90 else ("#EDA100" if r["desempenho"] >= 70 else "#E34948")

        with st.expander(f"**{nome}** — {horas_str} trabalhadas · {desemp_str} desempenho", expanded=False):
            cols = st.columns(4)
            cols[0].metric("⏱️ Horas trab.", horas_str)
            cols[1].metric(
                "🏦 Banco de horas",
                banco_str,
                delta=None,
                help="Saldo positivo = banco a favor · negativo = débito"
            )
            cols[2].metric(
                "⏰ Atrasos",
                atraso_str,
                delta=None,
                help="Total de minutos de atraso no período"
            )
            cols[3].metric(
                "📊 Desempenho",
                desemp_str,
                help=f"Horas trabalhadas / horas esperadas ({dias_uteis} dias úteis × 8h)"
            )

            # Dias
            st.markdown(
                f'<div style="display:flex;gap:20px;font-size:11px;color:var(--ms-texto-sec);margin-top:4px;">'
                f'<span>✅ Dias presentes: <b style="color:var(--ms-texto);">{r["dias_pres"]}</b></span>'
                f'<span>⛔ Ausências: <b style="color:{"#E34948" if r["dias_aus"]>0 else "var(--ms-texto)"};">{r["dias_aus"]}</b></span>'
                f'</div>',
                unsafe_allow_html=True
            )

            # Ociosidade via Trello (se mapeado)
            if r["trello_user"] and r["horas_min"] > 0:
                st.markdown("---")
                st.caption("🔗 Cruzamento com Trello")
                _calcular_ociosidade_trello(r["trello_user"], r["nome"], str_ini, str_fim, r["horas_min"])

            # Debug: resposta bruta da API (para ajuste do parse)
            with st.expander("🔧 Dados brutos da API (debug)", expanded=False):
                st.json(r["apuracao_raw"])


def _calcular_ociosidade_trello(trello_user: str, nome: str, data_ini: str, data_fim: str, horas_min: float):
    """
    Estima ociosidade cruzando horas trabalhadas (RHiD) com atividade Trello.
    Usa a função de análise de metas existente para buscar tempo em cards.
    """
    try:
        import placar_core as _pc
        import requests as _req

        key   = _pc.TRELLO_KEY
        token = _pc.TRELLO_TOKEN
        board = _pc.BOARD_ID

        # Busca membros do board para encontrar idMember do usuário
        resp = _req.get(
            f"https://api.trello.com/1/boards/{board}/members",
            params={"key": key, "token": token},
            timeout=10,
        )
        membros = resp.json() if resp.ok else []
        id_member = next(
            (m["id"] for m in membros if m.get("username", "").lower() == trello_user.lower()),
            None
        )

        if not id_member:
            st.caption(f"⚠️ Usuário Trello '{trello_user}' não encontrado no board.")
            return

        # Busca ações do membro no período
        ini_dt = datetime.fromisoformat(data_ini)
        fim_dt = datetime.fromisoformat(data_fim) + timedelta(days=1)

        resp2 = _req.get(
            f"https://api.trello.com/1/members/{id_member}/actions",
            params={
                "key": key, "token": token,
                "filter": "updateCard,createCard,commentCard,moveCardToBoard",
                "since": ini_dt.strftime("%Y-%m-%dT00:00:00.000Z"),
                "before": fim_dt.strftime("%Y-%m-%dT00:00:00.000Z"),
                "limit": 1000,
            },
            timeout=15,
        )
        acoes = resp2.json() if resp2.ok else []

        # Conta dias com atividade e estima tempo ativo (1 ação = ~5min de trabalho ativo)
        dias_com_atividade = len({a["date"][:10] for a in acoes})
        acoes_total        = len(acoes)
        tempo_ativo_est    = min(acoes_total * 5, horas_min)  # cap nas horas trabalhadas
        ociosidade_est     = max(horas_min - tempo_ativo_est, 0)
        pct_ocioso         = (ociosidade_est / horas_min * 100) if horas_min > 0 else 0

        cor_ocio = "#1BAF7A" if pct_ocioso < 20 else ("#EDA100" if pct_ocioso < 40 else "#E34948")

        cols = st.columns(3)
        cols[0].metric("📋 Ações no Trello", f"{acoes_total}")
        cols[1].metric("📅 Dias com atividade", f"{dias_com_atividade}")
        cols[2].metric(
            "😴 Ociosidade estimada",
            _rhid.fmt_horas(ociosidade_est),
            delta=f"{pct_ocioso:.0f}% do tempo",
            delta_color="inverse",
            help="Estimativa: tempo trabalhado (RHiD) menos tempo com atividade no Trello"
        )

        if pct_ocioso > 30:
            st.warning(
                f"⚠️ **{nome}** ficou ~{pct_ocioso:.0f}% do tempo sem atividade registrada no Trello "
                f"durante o período trabalhado."
            )

    except Exception as e:
        st.caption(f"Não foi possível calcular ociosidade Trello: {e}")


# ── Página principal ────────────────────────────────────────────────────────────

def pagina_ponto(usuario_logado: str):
    """Página completa do Relógio de Ponto."""
    eh_master = usuario_logado.lower() in {m.lower() for m in MASTERS}

    st.markdown("### 🕐 Relógio de Ponto")
    st.caption(
        "Registre entradas, saídas e ausências. A IA utiliza esses dados para calcular "
        "ociosidade por colaborador e alertar sobre sobrecarga em caso de ausência."
    )

    if eh_master:
        tab_relatorio, tab_hoje, tab_registro, tab_historico = st.tabs(
            ["📊 Relatório RHiD", "📡 Status Hoje", "✏️ Registrar", "📋 Histórico Mensal"]
        )
    else:
        tab_hoje, tab_registro, tab_historico = st.tabs(
            ["📡 Status Hoje", "✏️ Registrar", "📋 Histórico Mensal"]
        )

    if eh_master:
        with tab_relatorio:
            st.markdown("#### 📊 Relatório de Ponto — RHiD")
            st.caption(
                "Dados obtidos diretamente do sistema RHiD. "
                "Ociosidade calculada cruzando horas registradas com atividade no Trello."
            )
            _secao_relatorio_rhid()

    with tab_hoje:
        st.markdown("#### Status atual da equipe")
        st.caption(f"Atualizado em {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        _secao_status_hoje()

    with tab_registro:
        st.markdown("#### Registrar horário de ponto")
        _secao_registro(usuario_logado, eh_master)

    with tab_historico:
        st.markdown("#### Histórico mensal de ponto")
        _secao_historico_mensal(eh_master, usuario_logado)
