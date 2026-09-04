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


def _nao_bate_ponto():
    """Usernames de quem nao usa o relogio. Vazio em qualquer falha.

    Sem isto, as duas telas de ponto tratavam quem nao bate ponto igual a quem
    faltou: 0% de desempenho no Resumo por Colaborador e "Nao registrado" em
    vermelho no Status Hoje. Quem bate o olho le "essa pessoa rendeu zero", e o
    numero vira conversa de avaliacao — sobre uma medicao que nunca existiu.
    """
    try:
        import equipe_config as _ec_bp
        return _ec_bp.nao_batem()
    except Exception:
        return set()
MASTERS = _pc.MASTERS                 # {"martinsousa", "renan"}

# ── Horários de expediente ────────────────────────────────────────────────────
# Definidos em placar_core: o cálculo de tempo de cartão também precisa deles
# para cortar o que caiu fora do expediente, e duas cópias divergiriam.
HORARIO_PADRAO = _pc.HORARIO_PADRAO
HORARIOS       = _pc.HORARIOS
ALMOCO_MINUTOS = _pc.ALMOCO_MINUTOS
TOLERANCIA_ENTRADA_MIN = _pc.TOLERANCIA_ENTRADA_MIN
FOLGA_ENTRADA_MIN      = _pc.FOLGA_ENTRADA_MIN
FOLGA_ALMOCO_MIN       = _pc.FOLGA_ALMOCO_MIN

ENTRADA_ESPERADA = HORARIO_PADRAO["entrada"]
FIM_EXPEDIENTE   = HORARIO_PADRAO["fim"]
SAIDA_ALMOCO     = _pc.ALMOCO[0]
VOLTA_ALMOCO     = _pc.ALMOCO[1]

TOLERANCIA_MINUTOS = 10   # legado: folga do cálculo antigo

horario_de = _pc.horario_de


def limite_tolerancia(username: Optional[str]) -> time:
    """Até que horas a entrada ainda conta como tolerância, e não como atraso."""
    ent = horario_de(username)["entrada"]
    return (datetime.combine(date.min, ent)
            + timedelta(minutes=TOLERANCIA_ENTRADA_MIN)).time()


TIPOS_PONTO = {
    "entrada":        "🟢 Entrada",
    "saida_almoco":   "🍽️ Saída Almoço",
    "volta_almoco":   "↩️ Volta Almoço",
    "fim_expediente": "🔴 Fim de Expediente",
    "ausencia":       "⛔ Ausência",
}

# ── Google Sheets ──────────────────────────────────────────────────────────────

import planilha as _plan
# Nome vindo do ambiente: producao usa o padrao, homologacao usa a copia.
PLANILHA_NOME = _plan.nome()
ABA_PONTO     = "ponto"
COLUNAS_PONTO = ["data", "username", "tipo", "horario", "observacao", "criado_em", "criado_por"]


# Reutiliza a conexao entre reruns. Sem isso cada chamada refazia
# from_service_account_info + gspread.authorize + open() + worksheet() —
# quatro idas a rede antes de ler o primeiro dado, por modulo, a cada rerun.
def _cliente_gs():
    """Cliente gspread compartilhado (ver sheets.py).

    Era um bloco proprio de credencial + authorize, identico em nove
    modulos: nove trocas de token por processo, todas no cold start.
    """
    import sheets as _sh
    return _sh.cliente()


@st.cache_resource
def _aba_ponto():
    """Retorna a aba 'ponto' da planilha, criando-a se necessário."""
    # A planilha e aberta uma vez por processo em sheets.py. Aqui cada
    # modulo abria a sua, e abrir por nome custa uma varredura do Drive.
    import sheets as _sh
    planilha = _sh.planilha()
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


@st.cache_data(ttl=90)
def _carregar_ponto_todos() -> list[dict]:
    """Carrega todos os registros de ponto do Google Sheets (cache de 90 s;
    invalidado na hora por _salvar_registro e _deletar_registro)."""
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
    """Upsert: atualiza linha existente ou adiciona nova linha no Google Sheets.

    Retorna (ok: bool, erro: str). Ponto é dado de folha de pagamento — uma
    falha aqui NAO pode passar despercebida, entao o resultado volta para o
    chamador em vez de ser engolido.
    """
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
                return True, ""
        aba.append_row(nova_linha, value_input_option="RAW")
        _carregar_ponto_todos.clear()
        return True, ""
    except Exception as e:
        return False, str(e)


def _deletar_registro(data_str, username, tipo):
    """Remove uma linha do Sheets que corresponde a (data, username, tipo).

    Retorna (ok: bool, erro: str).
    """
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
                return True, ""
        return False, "Registro não encontrado na planilha."
    except Exception as e:
        return False, str(e)


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


def calcular_indicadores_dia(regs: list[dict], username: Optional[str] = None) -> dict:
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
        # Pontualidade (contagem, não minutos)
        "tolerancia_entrada":  False,
        "tolerancia_almoco":   False,
        "atraso_entrada":      False,
        "atraso_almoco":       False,
        "min_atraso_entrada":  0.0,
        "min_atraso_almoco":   0.0,
        "qtd_tolerancias":     0,
        "qtd_atrasos":         0,
    }
    # Cada colaborador pode ter horário próprio; sem username, usa o padrão.
    if username is None and regs:
        username = regs[0].get("username")
    _h = horario_de(username)
    entrada_esperada = _h["entrada"]
    fim_esperado     = _h["fim"]
    limite_tol       = limite_tolerancia(username)

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

    # ── Pontualidade ──────────────────────────────────────────────────────────
    # Entrada em tres faixas: os 5 primeiros minutos nao registram nada, os 5
    # seguintes consomem tolerancia, e depois disso e atraso. Para quem entra
    # 09:00: nada ate 09:05, tolerancia ate 09:10, atraso a partir dai.
    if r["entrada"]:
        atraso_ent = _diff_min(entrada_esperada, r["entrada"])   # > 0 se atrasado
        if r["entrada"] > limite_tol:
            r["atraso_entrada"]     = True
            r["min_atraso_entrada"] = atraso_ent
        elif atraso_ent > FOLGA_ENTRADA_MIN:
            r["tolerancia_entrada"] = True
            r["min_atraso_entrada"] = atraso_ent
            r["tolerancia_min"]     = atraso_ent

    # Almoço: conta pela duração, não pelo relógio de parede. Duas faixas apenas
    # — 5 minutos livres e, passando disso, atraso. Tolerância só na entrada.
    _excedeu = 0.0
    if r["saida_almoco"] and r["volta_almoco"]:
        _excedeu = _diff_min(r["saida_almoco"], r["volta_almoco"]) - ALMOCO_MINUTOS
    elif r["volta_almoco"] and r["volta_almoco"] > VOLTA_ALMOCO:
        # Sem a saída registrada, só resta comparar com o horário de referência.
        _excedeu = _diff_min(VOLTA_ALMOCO, r["volta_almoco"])
    if _excedeu > FOLGA_ALMOCO_MIN:
        r["atraso_almoco"]     = True
        r["min_atraso_almoco"] = _excedeu

    # Entrada e volta do almoço são ocorrências separadas: atrasar nas duas no
    # mesmo dia conta dois atrasos. O mesmo vale para as tolerâncias.
    r["qtd_atrasos"]     = int(r["atraso_entrada"]) + int(r["atraso_almoco"])
    r["qtd_tolerancias"] = (int(r["tolerancia_entrada"])
                            + int(r["tolerancia_almoco"]))

    # Saiu cedo (antes do fim esperado)
    if r["fim_expediente"]:
        r["saiu_cedo_min"] = max(_diff_min(r["fim_expediente"], fim_esperado), 0)

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
            "qtd_tolerancias":     0,
            "qtd_atrasos":         0,
            "atrasos_entrada":     0,
            "atrasos_almoco":      0,
            "detalhes":            [],
        }
        for u in MEMBROS
    }

    for data_str, users in sorted(por_data_user.items()):
        for username, rlist in users.items():
            if username not in resumo:
                continue
            ind = calcular_indicadores_dia(rlist, username)
            if ind["ausente"]:
                resumo[username]["dias_ausentes"] += 1
            else:
                resumo[username]["dias_trabalhados"]    += 1
                resumo[username]["total_horas_disp"]    += ind["horas_disponiveis"]
                resumo[username]["total_tolerancia_min"] += ind["tolerancia_min"]
                resumo[username]["total_saiu_cedo_min"]  += ind["saiu_cedo_min"]
                resumo[username]["qtd_tolerancias"] += ind["qtd_tolerancias"]
                resumo[username]["qtd_atrasos"]     += ind["qtd_atrasos"]
                resumo[username]["atrasos_entrada"] += int(ind["atraso_entrada"])
                resumo[username]["atrasos_almoco"]  += int(ind["atraso_almoco"])
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
        # Cinza, nao vermelho: nao bater ponto nao e ausencia.
        "sem_relogio":   "#6B7280",
    }.get(status, "#555555")


def _label_status(status: str) -> str:
    return {
        "disponivel":    "✅ Disponível",
        "almoco":        "🍽️ Almoço",
        "encerrado":     "🏠 Encerrado",
        "ausente":       "⛔ Ausente",
        "nao_registrado":"❓ Não registrado",
        "sem_relogio":   "🕒 Não bate ponto",
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

    _fora_do_relogio = _nao_bate_ponto()

    cards = []
    for username, nome in MEMBROS.items():
        status = status_map.get(username, "nao_registrado")
        if username in _fora_do_relogio and status == "nao_registrado":
            status = "sem_relogio"
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
        # Quem nao bate ponto sai da lista: lancamento manual aqui vira dado de
        # folha, e nao pode existir batida para quem nao tem relogio. Para
        # incluir alguem, marque "Bate ponto" no cadastro da equipe.
        _fora = _nao_bate_ponto()
        usernames = [u for u in MEMBROS if u not in _fora]
        if not usernames:
            st.warning("Nenhum colaborador marcado como 'bate ponto' no cadastro "
                       "da equipe. Marque em Análise de Metas → Configuração de "
                       "Metas → Equipe.")
            return
        nomes_disp = [MEMBROS[u] for u in usernames]
        nome_sel = col_user.selectbox("👤 Colaborador", nomes_disp, key="pt_user")
        username_sel = usernames[nomes_disp.index(nome_sel)]
        _sem_relogio = [MEMBROS[u] for u in MEMBROS if u in _fora]
        if _sem_relogio:
            col_user.caption("Fora da lista (não batem ponto): "
                             + ", ".join(_sem_relogio))
    else:
        # Mapeia login do app para username Trello
        _LOGIN_MAP = {"Myrella": "myrelladesouza", "Beatriz": "beatriz51",
                      "Gabriel": "gabriel_borges", "MartinSousa": "martinsousa"}
        username_sel = _LOGIN_MAP.get(usuario_logado, usuario_logado.lower())
        nome_sel = MEMBROS.get(username_sel, usuario_logado)
        col_user.info(f"Registrando para: **{nome_sel}**")

    # Registros já existentes nesse dia/pessoa
    regs_existentes = {r["tipo"]: r for r in _get_registros(data_str, username_sel)}
    ind_existente   = (calcular_indicadores_dia(list(regs_existentes.values()), username_sel)
                       if regs_existentes else None)

    st.markdown("##### Registrar horário")

    tipo_opts = list(TIPOS_PONTO.keys())
    tipo_labels = [TIPOS_PONTO[t] for t in tipo_opts]

    with st.form("form_ponto", clear_on_submit=True):
        col_tipo, col_hora, col_obs = st.columns([2, 1, 3])
        tipo_label = col_tipo.selectbox("Tipo", tipo_labels, key="pt_tipo")
        tipo_sel = tipo_opts[tipo_labels.index(tipo_label)]

        _h_sel = horario_de(username_sel)
        horario_default = {
            "entrada":        _h_sel["entrada"],
            "saida_almoco":   SAIDA_ALMOCO,
            "volta_almoco":   VOLTA_ALMOCO,
            "fim_expediente": _h_sel["fim"],
            "ausencia":       None,
        }[tipo_sel]

        if tipo_sel != "ausencia":
            hora_val = col_hora.time_input(
                "Horário", value=horario_default or _h_sel["entrada"], key="pt_hora"
            )
            hora_str = hora_val.strftime("%H:%M")
        else:
            hora_str = None
            col_hora.markdown(" ")

        obs = col_obs.text_input("Observação (opcional)", key="pt_obs", placeholder="ex.: problema de transporte")

        salvar = st.form_submit_button("💾 Registrar ponto", use_container_width=True)
        if salvar:
            _ok, _err = _salvar_registro(
                data_str, username_sel, tipo_sel, hora_str, obs, usuario_logado
            )
            if _ok:
                st.success(f"✅ {TIPOS_PONTO[tipo_sel]} registrado para **{nome_sel}** em {data_str}" +
                           (f" às {hora_str}" if hora_str else "") + ".")
                st.rerun()
            else:
                # Nunca confirmar um ponto que não foi gravado.
                st.error(
                    f"❌ NÃO foi possível registrar o ponto de **{nome_sel}**. "
                    f"O registro não está salvo — tente de novo ou avise o administrador.\n\n{_err}"
                )

    # Exibe registros do dia selecionado
    if regs_existentes:
        st.markdown(f"**Registros em {data_str} — {nome_sel}:**")
        for tipo, reg in regs_existentes.items():
            h = reg.get("horario", "—") or "—"
            obs_txt = f"  ·  _{reg['observacao']}_" if reg.get("observacao") else ""
            col_r, col_del = st.columns([5, 1])
            col_r.markdown(f"{TIPOS_PONTO[tipo]}  **{h}**{obs_txt}")
            if eh_master and col_del.button("🗑️", key=f"del_{tipo}_{data_str}_{username_sel}", help="Remover"):
                _ok_del, _err_del = _deletar_registro(data_str, username_sel, tipo)
                if _ok_del:
                    st.rerun()
                else:
                    st.error(f"❌ Não foi possível remover o registro.\n\n{_err_del}")

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

    st.caption("Lançamentos manuais (aba *Registrar*)"
               + (" — as batidas do relógio estão em *Relatório RHiD*."
                  if eh_master else "."))

    resumo = calcular_resumo_mes(ano_sel, mes_num)

    if not any(r["dias_trabalhados"] + r["dias_ausentes"] > 0 for r in resumo.values()):
        # Dizer de QUAL fonte o vazio fala.
        #
        # Esta tela le os lancamentos MANUAIS da planilha; o Relatorio RHiD, ao
        # lado, le o relogio. "Nenhum registro de ponto em Agosto" aparecia com
        # 437 horas registradas na aba vizinha, no mesmo mes — quem abrisse
        # concluiria que ninguem bateu ponto.
        st.info(
            f"Nenhum **lançamento manual** em {mes_sel} {ano_sel}. "
            "Esta tela mostra só o que foi registrado à mão na aba *Registrar*"
            + (" — as batidas do relógio ficam em **📊 Relatório RHiD**, na mesma tela."
               if eh_master else ".")
        )
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

def _dt_soma(t, minutos):
    """Horario mais N minutos, sem sair do tipo time."""
    from datetime import datetime as _d, timedelta as _td
    return (_d.combine(_d.today().date(), t) + _td(minutes=minutos)).time()


def _janelas_do_dia(data, entrada, saida_almoco, volta_almoco, saida):
    """[(ini, fim)] do expediente efetivo, em hora local com data.

    Duas janelas quando o almoco esta registrado, uma so quando nao esta. Sem
    a saida do dia, usa o fim contratual — melhor que descartar o dia inteiro.
    """
    from datetime import datetime as _dt
    def _dt_local(t):
        return _dt.combine(data, t, tzinfo=_pc.FUSO) if t else None
    ini = _dt_local(entrada)
    fim = _dt_local(saida)
    if not ini:
        return []
    if not fim or fim <= ini:
        return []
    sa, va = _dt_local(saida_almoco), _dt_local(volta_almoco)
    if sa and va and ini < sa < va < fim:
        return [(ini, sa), (va, fim)]
    # Foi embora durante o almoco ou logo na volta dele: so vale a manha. Sem
    # este corte a hora do almoco entrava como expediente e, sem cartao aberto,
    # virava ociosidade — justamente no dia em que a pessoa teve um imprevisto.
    if sa and ini < sa and fim <= (va or sa):
        return [(ini, min(sa, fim))]
    return [(ini, fim)]


# De onde vieram as tolerancias do ultimo dia classificado.
TOLERANCIA_DETALHE = {"entrada": 0, "almoco": 0}


def _classificar_batidas(username, entrada, saida_almoco=None, volta_almoco=None):
    """Aplica a regra da casa a um dia.

    Devolve (tolerancias, atraso_entrada, atraso_almoco, minutos_almoco).

    Entrada em tres faixas: os 5 primeiros minutos de atraso nao registram nada,
    os 5 seguintes consomem tolerancia, e passou disso e atraso.

    Volta do almoco em duas: 5 minutos livres sobre a duracao do almoco e, acima
    disso, atraso. Nao ha tolerancia aqui — ela existe so na entrada.

    Guarda em TOLERANCIA_DETALHE de onde vieram as tolerâncias do dia. Sem essa
    separação a tela mostrava "13 tolerâncias" para quem só chegou atrasado
    sete vezes, e não havia como descobrir que as outras seis eram do almoço.
    """
    tol = atr_ent = atr_alm = 0
    TOLERANCIA_DETALHE["entrada"] = TOLERANCIA_DETALHE["almoco"] = 0
    minutos_almoco = 0.0

    if entrada:
        h = horario_de(username)
        if entrada > limite_tolerancia(username):
            atr_ent = 1
        elif _diff_min(h["entrada"], entrada) > FOLGA_ENTRADA_MIN:
            tol = 1
            TOLERANCIA_DETALHE["entrada"] = 1

    excedeu = 0.0
    if saida_almoco and volta_almoco:
        minutos_almoco = _diff_min(saida_almoco, volta_almoco)
        excedeu = minutos_almoco - ALMOCO_MINUTOS
    elif volta_almoco and volta_almoco > VOLTA_ALMOCO:
        # Sem a saída registrada, só resta comparar com o horário de referência.
        excedeu = _diff_min(VOLTA_ALMOCO, volta_almoco)
    if excedeu > FOLGA_ALMOCO_MIN:
        atr_alm = 1

    return tol, atr_ent, atr_alm, minutos_almoco


@st.cache_data(ttl=300)   # 5 min — o painel precisa acompanhar o dia
def _pontualidade_rhid(ano: int, mes: int):
    """Pontualidade a partir do relógio de ponto físico (RHiD).

    A equipe bate ponto SOMENTE no relógio — nunca pelo Studio. Esta é a fonte
    real; a planilha só entra como reserva.

    Devolve ({username: resumo}, diagnostico). O diagnóstico nunca fica vazio:
    quando não há dado, ele diz por quê.
    """
    diag = {"fonte": "RHiD", "erro": None, "pessoas": 0, "mapeadas": 0,
            "dias_com_batida": 0, "chaves_exemplo": [],
            "campos_com_hora": [], "data_amostra": "",
            "todos_os_campos": []}

    persons = _rhid.get_persons()
    if not persons:
        diag["erro"] = ("Não consegui listar os colaboradores na RHiD "
                        "(login ou endpoint de pessoas).")
        return {}, diag
    diag["pessoas"] = len(persons)

    ini = date(ano, mes, 1)
    prox = date(ano + (1 if mes == 12 else 0), 1 if mes == 12 else mes + 1, 1)
    fim = min(prox - timedelta(days=1), date.today())
    if fim < ini:
        diag["erro"] = "Mês ainda não começou."
        return {}, diag

    resultado = {}
    for p in persons:
        nome_p = (p.get("name") or p.get("nome") or p.get("nomeCompleto")
                  or p.get("fullName") or p.get("personName") or "")
        id_p = p.get("id") or p.get("idPerson") or p.get("personId") or p.get("codigo")
        u = _rhid_nome_para_trello(nome_p) if nome_p else None
        if not u or u not in MEMBROS or not id_p:
            continue
        diag["mapeadas"] += 1

        regs, d = _rhid.get_registros_diarios(ini.isoformat(), fim.isoformat(), int(id_p))
        if d.get("erro") and not diag["erro"]:
            diag["erro"] = d["erro"]
        if d.get("chaves_exemplo") and not diag["chaves_exemplo"]:
            diag["chaves_exemplo"] = d["chaves_exemplo"]
        if d.get("campos_com_hora") and not diag.get("campos_com_hora"):
            diag["campos_com_hora"] = d["campos_com_hora"]
            diag["data_amostra"] = d.get("data_amostra", "")
        if d.get("todos_os_campos") and not diag.get("todos_os_campos"):
            diag["todos_os_campos"] = d["todos_os_campos"]
        # De qual campo as batidas sairam. Se a RHiD trocar o nome da lista, a
        # tela diz qual campo foi usado em vez de voltar a zero em silencio.
        if not diag.get("campo_batidas"):
            diag["campo_batidas"] = _rhid.ULTIMA_ORIGEM_BATIDAS.get("campo", "")

        acc = {"tolerancias": 0, "tol_entrada": 0, "tol_almoco": 0,
               "atrasos": 0, "atrasos_entrada": 0,
               "atrasos_almoco": 0, "dias_trabalhados": 0, "ocorrencias": [],
               "minutos_trabalhados": 0.0,
               # Expediente EFETIVO de cada dia, do relogio de ponto. E sobre
               # estas janelas que a ociosidade e medida — sem elas so da para
               # subtrair totais, e a folga de 10 e a de 5 minutos precisam
               # saber QUANDO cada buraco aconteceu.
               "janelas": [],
               # Saldo do banco no fim do mes e quanto os atrasos pesaram nele.
               # O desconto quem faz e a RHiD; aqui so se le, para nao existirem
               # duas contas da mesma coisa dando numeros diferentes.
               "banco_min": 0.0, "minutos_atraso": 0.0}
        # Saldo do banco: o ULTIMO dia que trouxer o valor, porque o campo da
        # RHiD ja e acumulado — somar os dias contaria tudo de novo.
        for reg in reversed(regs):
            if reg.get("saldo_banco"):
                acc["banco_min"] = float(reg["saldo_banco"])
                break

        for reg in regs:
            if reg["faltou"] or not reg["batidas"]:
                continue
            diag["dias_com_batida"] += 1
            acc["dias_trabalhados"] += 1
            acc["minutos_trabalhados"] += reg["minutos_trabalhados"]
            entrada = _parse_horario(reg.get("entrada"))
            saida_a = _parse_horario(reg.get("saida_almoco"))
            volta   = _parse_horario(reg.get("volta_almoco"))
            if not entrada and not volta:
                continue
            tol, atr_ent, atr_alm, min_almoco = _classificar_batidas(
                u, entrada, saida_a, volta)
            acc["tolerancias"]     += tol
            acc["tol_entrada"]     += TOLERANCIA_DETALHE["entrada"]
            acc["tol_almoco"]      += TOLERANCIA_DETALHE["almoco"]
            acc["atrasos_entrada"] += atr_ent
            acc["atrasos_almoco"]  += atr_alm
            acc["atrasos"]         += atr_ent + atr_alm

            saida_d = _parse_horario(reg.get("saida"))
            if reg["data"]:
                acc["janelas"].append(
                    (reg["data"], _janelas_do_dia(reg["data"], entrada, saida_a,
                                                  volta, saida_d)))

            # Cada ocorrencia guarda o dia, a hora batida, QUAL evento a gerou e
            # quantos minutos passaram do horario. E o que a equipe precisa para
            # conferir um numero contra o proprio ponto.
            data_txt = reg["data"].strftime("%d/%m") if reg["data"] else "—"
            _esperado = horario_de(u)["entrada"]
            if tol and entrada:
                acc["ocorrencias"].append({
                    "data": data_txt, "tipo": "tolerancia",
                    "evento": "Entrada", "horario": entrada.strftime("%H:%M"),
                    "esperado": _esperado.strftime("%H:%M"),
                    "minutos": _diff_min(_esperado, entrada)})
            if atr_ent and entrada:
                acc["ocorrencias"].append({
                    "data": data_txt, "tipo": "atraso_entrada",
                    "evento": "Entrada", "horario": entrada.strftime("%H:%M"),
                    "esperado": _esperado.strftime("%H:%M"),
                    "minutos": _diff_min(_esperado, entrada)})
            if atr_alm:
                _prev = (_dt_soma(saida_a, ALMOCO_MINUTOS) if saida_a
                         else VOLTA_ALMOCO)
                acc["ocorrencias"].append({
                    "data": data_txt, "tipo": "atraso_almoco",
                    "evento": "Volta do almoço",
                    "horario": volta.strftime("%H:%M") if volta else "—",
                    "esperado": _prev.strftime("%H:%M"),
                    "minutos": max(min_almoco - ALMOCO_MINUTOS, 0),
                })
        # Minutos de atraso do mes: ja estavam em cada ocorrencia, so nunca
        # tinham sido somados. E o numero que diz o TAMANHO do atraso — chegar
        # 6 min tarde e chegar 40 min tarde contavam igual ate aqui.
        acc["minutos_atraso"] = sum(
            float(o.get("minutos", 0) or 0) for o in acc["ocorrencias"]
            if o.get("tipo", "").startswith("atraso"))
        resultado[u] = acc

    if diag["mapeadas"] == 0 and not diag["erro"]:
        diag["erro"] = ("Nenhum colaborador da RHiD casou com os nomes do Trello "
                        "(confira _RHID_TRELLO_MAP).")
    return resultado, diag


def limpar_cache_ponto():
    """Descarta o cache de ponto para a próxima leitura vir do zero."""
    for f in (_pontualidade_rhid, _carregar_ponto_todos):
        try:
            f.clear()
        except Exception:
            pass


def get_pontualidade_mes(ano: int, mes: int, com_diagnostico: bool = False):
    """Contagem de tolerâncias e atrasos do mês, por colaborador.

    Regra da casa: entrada até 09h05 não registra nada, de 09h05 a 09h10 é
    tolerância e depois disso é atraso. Na volta do almoço são 5 minutos livres
    e, passando disso, atraso — sem tolerância; volta
    do almoço atrasada é atraso mesmo que por um minuto. Entrada e volta são
    ocorrências separadas.

    Retorna {username: {"tolerancias": int, "atrasos": int, "atrasos_entrada": int,
                        "atrasos_almoco": int, "dias_trabalhados": int,
                        "ocorrencias": [ {data, tipo, horario, minutos} ]}}
    """
    try:
        via_rhid, diag = _pontualidade_rhid(ano, mes)
    except Exception as e:
        via_rhid, diag = {}, {"fonte": "RHiD", "erro": str(e)[:200],
                              "pessoas": 0, "mapeadas": 0,
                              "dias_com_batida": 0, "chaves_exemplo": [],
                              "campos_com_hora": [], "data_amostra": "",
            "todos_os_campos": []}
    if any(v["dias_trabalhados"] > 0 for v in via_rhid.values()):
        completo = {u: via_rhid.get(u, {
            "tolerancias": 0, "atrasos": 0, "atrasos_entrada": 0,
            "atrasos_almoco": 0, "dias_trabalhados": 0, "ocorrencias": [],
            "minutos_trabalhados": 0.0, "banco_min": 0.0, "minutos_atraso": 0.0,
        }) for u in MEMBROS}
        return (completo, diag) if com_diagnostico else completo

    # Reserva: registros feitos dentro do Studio. Hoje ninguém usa, mas se
    # alguém usar, o dado não se perde.
    resumo = calcular_resumo_mes(ano, mes)
    diag["fonte"] = "planilha (RHiD sem dado)"
    resultado = {}
    for u in MEMBROS:
        ocorrencias = []
        for det in resumo[u]["detalhes"]:
            if det.get("tolerancia_entrada"):
                ocorrencias.append({
                    "data": det["data"], "tipo": "tolerancia",
                    "horario": det["entrada"].strftime("%H:%M") if det["entrada"] else "—",
                    "minutos": det["min_atraso_entrada"],
                })
            if det.get("atraso_entrada"):
                ocorrencias.append({
                    "data": det["data"], "tipo": "atraso_entrada",
                    "horario": det["entrada"].strftime("%H:%M") if det["entrada"] else "—",
                    "minutos": det["min_atraso_entrada"],
                })
            if det.get("atraso_almoco"):
                ocorrencias.append({
                    "data": det["data"], "tipo": "atraso_almoco",
                    "horario": det["volta_almoco"].strftime("%H:%M") if det["volta_almoco"] else "—",
                    "minutos": det["min_atraso_almoco"],
                })
        resultado[u] = {
            "tolerancias":      resumo[u]["qtd_tolerancias"],
            "atrasos":          resumo[u]["qtd_atrasos"],
            "atrasos_entrada":  resumo[u]["atrasos_entrada"],
            "atrasos_almoco":   resumo[u]["atrasos_almoco"],
            "dias_trabalhados": resumo[u]["dias_trabalhados"],
            "ocorrencias":      ocorrencias,
        }
    return (resultado, diag) if com_diagnostico else resultado


def get_ociosidade_mes(ano: int, mes: int, tempo_cards_por_user: dict,
                       intervalos_por_user: dict = None) -> dict:
    """
    Calcula ociosidade por colaborador no mês.

    intervalos_por_user: {username: [(ini, fim)]} — trechos com cartão
      EM ANDAMENTO daquela pessoa, em hora local. Quando vem, a ociosidade é
      medida DIA A DIA sobre a linha do tempo: cada buraco entre o expediente e
      os cartões vira ocioso, descontada a folga de 10 minutos no começo do dia
      e de 5 minutos entre um cartão e o seguinte.

    tempo_cards_por_user: {username: minutos_em_cards} — reserva para quando
      não há linha do tempo (o mês inteiro cai numa subtração de totais, sem as
      folgas). É como funcionava antes.

    Retorna {username: {"horas_disp_min": float, "tempo_cards_min": float,
                        "ociosidade_min": float, "pct_ocioso": float}}
    """
    resumo = calcular_resumo_mes(ano, mes)

    # Horas disponíveis vêm do relógio físico quando ele responde — é lá que a
    # equipe bate ponto. A planilha só entra se a RHiD não trouxer nada.
    try:
        via_rhid, _ = _pontualidade_rhid(ano, mes)
    except Exception:
        via_rhid = {}

    intervalos_por_user = intervalos_por_user or {}
    resultado = {}
    for u in MEMBROS:
        hd = (via_rhid.get(u, {}).get("minutos_trabalhados", 0.0)
              or resumo[u]["total_horas_disp"])       # minutos disponíveis
        tc   = tempo_cards_por_user.get(u, 0)         # minutos em cards (Trello)

        _janelas_mes = (via_rhid.get(u, {}) or {}).get("janelas") or []
        if _janelas_mes and u in intervalos_por_user:
            ativos = intervalos_por_user.get(u) or []
            ocio, hd_reais = 0.0, 0.0
            for _data, _jans in _janelas_mes:
                if not _jans:
                    continue
                # Hora abonada sai dos dois lados: do buraco e do denominador.
                # Sem isto, uma manha sem internet aparecia como ociosidade da
                # pessoa -- ela estava no lugar, sem ter como trabalhar.
                # `u` entra na conta: alem da parada do escritorio, sai
                # daqui o abatimento que o gestor aprovou para essa pessoa --
                # o trabalho que ela fez sem cartao aberto ou sem etiqueta.
                _ab = _pc.abonos_do_dia(_data, username=u)
                if _ab:
                    import abonos as _abm
                    _jans = _abm.descontar(_jans, _ab)
                    if not _jans:
                        continue
                _o, _ = _pc.ociosidade_do_dia(_jans, ativos)
                _bruto_dia = sum((f - i).total_seconds() / 60 for i, f in _jans)
                # A hora pessoal do dia sai dos DOIS lados: do tempo ocioso e do
                # tempo cobrado. Das 8h no relogio, 7h sao de atividade.
                ocio += max(_o - _pc.PAUSA_PESSOAL_MIN, 0.0)
                hd_reais += max(_bruto_dia - _pc.PAUSA_PESSOAL_MIN, 0.0)
            if hd_reais > 0:
                hd = hd_reais
        else:
            # Sem linha do tempo: subtracao de totais, como era antes — mas ja
            # descontando a hora pessoal de cada dia trabalhado.
            _dias = (via_rhid.get(u, {}).get("dias_trabalhados")
                     or resumo[u]["dias_trabalhados"] or 0)
            hd = max(hd - _pc.PAUSA_PESSOAL_MIN * _dias, 0)
            ocio = max(hd - tc, 0)
        pct  = (ocio / hd * 100) if hd > 0 else 0
        resultado[u] = {
            "horas_disp_min": hd,
            "tempo_cards_min": tc,
            "ociosidade_min": ocio,
            "pct_ocioso": pct,
            "dias_trabalhados": (via_rhid.get(u, {}).get("dias_trabalhados")
                                 or resumo[u]["dias_trabalhados"]),
            "dias_ausentes": resumo[u]["dias_ausentes"],
            "total_tolerancia_min": resumo[u]["total_tolerancia_min"],
            "qtd_tolerancias": (via_rhid.get(u, {}).get("tolerancias")
                                or resumo[u]["qtd_tolerancias"]),
            "qtd_atrasos":     (via_rhid.get(u, {}).get("atrasos")
                                or resumo[u]["qtd_atrasos"]),
            # Saldo do banco e o peso dos atrasos em minutos, para a meta poder
            # mostrar os dois lado a lado. Quem desconta o atraso do banco e a
            # RHiD; o Studio le o saldo dela e nao refaz a conta.
            "banco_min":       float(via_rhid.get(u, {}).get("banco_min", 0.0) or 0.0),
            "minutos_atraso":  float(via_rhid.get(u, {}).get("minutos_atraso", 0.0) or 0.0),
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
    """Nome da RHiD -> username do Trello.

    A equipe cadastrada na planilha manda; o mapa do codigo fica de reserva.
    Sem isso, cada contratacao exigia alterar codigo para o ponto da pessoa ser
    reconhecido.
    """
    if not nome:
        return None
    chave = nome.lower().split()[0]
    return _pc.MAPA_RHID.get(chave) or _RHID_TRELLO_MAP.get(chave)


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
        return

    # Filtra apenas colaboradores ativos
    persons_ativos = [p for p in persons if str(p.get("status", "1")) != "0"]

    st.caption(
        f"✅ Conectado à RHiD · {len(persons_ativos)} colaborador(es) · "
        f"Período: {data_ini.strftime('%d/%m')} a {data_fim.strftime('%d/%m/%Y')}"
    )

    # Esta tela lista quem existe na RHiD; a aba "Status Hoje" lista a equipe
    # cadastrada no Studio. Sao fontes diferentes, e quando divergem a diferenca
    # aparecia como colaborador sumido, sem explicacao nenhuma. Agora a
    # divergencia e dita em voz alta.
    _users_na_rhid = set()
    for _p in persons_ativos:
        _n = (_p.get("name") or _p.get("nome") or _p.get("nomeCompleto")
              or _p.get("fullName") or _p.get("personName") or "")
        _u = _rhid_nome_para_trello(_n) if _n else None
        if _u:
            _users_na_rhid.add(_u)
    _fora_relogio = _nao_bate_ponto()
    # Quem esta marcado como "nao bate ponto" nao e uma divergencia a resolver:
    # e o esperado. Continua listado, mas como informacao, nao como alerta.
    _faltando = [nome for user, nome in MEMBROS.items()
                 if user not in _users_na_rhid and user not in _fora_relogio]
    _por_escolha = [nome for user, nome in MEMBROS.items() if user in _fora_relogio]
    if _faltando:
        st.warning(
            "⚠️ Sem relógio na RHiD: **" + "**, **".join(_faltando) + "**. "
            "Estes aparecem na aba *Status Hoje* (equipe do Studio) mas não aqui. "
            "Ou o cadastro na RHiD está inativo, ou o primeiro nome está escrito "
            "diferente dos dois lados. Se for gente que **não bate ponto**, "
            "desmarque a caixa **Bate ponto no relógio** em *Análise de Metas → Configuração de Metas → Equipe* e este aviso some."
        )
    if _por_escolha:
        st.caption("🕒 Não batem ponto (fora do cálculo de horas e desempenho): "
                   + ", ".join(_por_escolha))

    # ── Busca apuração para cada colaborador ──────────────────────────────────
    dias_uteis = max(sum(
        1 for d in range((data_fim - data_ini).days + 1)
        if (data_ini + timedelta(days=d)).weekday() < 5
    ), 1)

    resultados = []

    prog = st.progress(0, text="Buscando dados de ponto…")
    for i, p in enumerate(persons_ativos):
        # Campos de nome e ID podem variar entre versões da API RHiD
        nome_p = (p.get("name") or p.get("nome") or p.get("nomeCompleto")
                  or p.get("fullName") or p.get("personName") or str(p.get("id", "?")))
        id_p   = p.get("id") or p.get("idPerson") or p.get("personId") or p.get("codigo") or 0
        prog.progress((i + 1) / len(persons_ativos), text=f"Buscando: {nome_p}")
        apuracao = _rhid.get_apuracao(str_ini, str_fim, int(id_p))

        # Extrai campos da apuração (estrutura pode variar entre versões da API)
        if apuracao and not apuracao.get("_raw"):
            # Campos comuns em APIs de ponto RHiD/ControlID
            horas_trab_min  = float(apuracao.get("horasTrabalhadas", apuracao.get("workedMinutes", 0)) or 0)
            banco_min       = float(apuracao.get("bancoHoras",        apuracao.get("bankMinutes",   0)) or 0)
            total_atrasos   = float(apuracao.get("totalAtrasos",      apuracao.get("lateMinutes",    0)) or 0)
            dias_presentes  = int(  apuracao.get("diasPresentes",     apuracao.get("workedDays",     0)) or 0)
            dias_ausentes   = int(  apuracao.get("diasAusentes",      apuracao.get("absentDays",     0)) or 0)

            # Se a API retornar tudo zero mas com dados brutos, tenta interpretar
            registros_diarios = []
            if horas_trab_min == 0 and isinstance(apuracao, dict):
                # Pode ser uma lista de registros diários (RHiD retorna um por dia)
                registros = apuracao.get("registros", apuracao.get("records", apuracao.get("data", [])))
                if isinstance(registros, list) and registros:
                    for reg in registros:
                        # totalHorasTrabalhadas = minutos trabalhados no dia (campo nativo RHiD)
                        _apurado = float(
                            reg.get("totalHorasTrabalhadas",
                            reg.get("horasTrabalhadas",
                            reg.get("workedMinutes", 0))) or 0
                        )
                        # Dia ainda nao fechado pela RHiD: vale a batida.
                        horas_trab_min += _apurado or _rhid.minutos_das_marcacoes(
                            _rhid.marcacoes_do_registro(reg))
                        total_atrasos  += float(
                            reg.get("minutosAtraso",
                            reg.get("atraso",
                            reg.get("lateMinutes", 0))) or 0
                        )
                    # Banco de horas: usa saldoBancoFinalDia do ÚLTIMO registro
                    # (valor acumulado oficial da RHiD, não a soma diária)
                    for reg in reversed(registros):
                        saldo_final = reg.get("saldoBancoFinalDia")
                        if saldo_final is not None:
                            banco_min = float(saldo_final or 0)
                            break
                    # Dias presentes: registros onde houve trabalho (totalHorasTrabalhadas > 0)
                    # Presenca e ausencia olham a batida, nao so a apuracao:
                    # dia em aberto tem batida e zero apurado, e contava como
                    # ausencia.
                    def _bateu(r):
                        return any(_rhid.marcacoes_do_registro(r))

                    dias_presentes = len([
                        r for r in registros
                        if float(r.get("totalHorasTrabalhadas", r.get("horasTrabalhadas", 0)) or 0) > 0
                        or _bateu(r)
                    ])
                    dias_ausentes = len([
                        r for r in registros
                        if int(r.get("faltasDiasInteiro", r.get("ausente", 0)) or 0) > 0
                        and not _bateu(r)
                    ])
                    # Guarda resumo diário para tabela de conferência
                    import datetime as _dt
                    for reg in registros:
                        data_str = reg.get("dateTimeStr") or reg.get("date", "")
                        try:
                            if len(str(data_str)) == 8:  # "20260801"
                                d = _dt.datetime.strptime(str(data_str), "%Y%m%d").date()
                            else:
                                d = _dt.datetime.fromisoformat(str(data_str)[:10]).date()
                        except Exception:
                            d = None
                        trabalhado = float(reg.get("totalHorasTrabalhadas", 0) or 0)
                        saldo_dia  = float(reg.get("saldoBancoCredDeb", 0) or 0)
                        saldo_acum = float(reg.get("saldoBancoFinalDia", 0) or 0)
                        is_holiday = bool(reg.get("isHoliday") or reg.get("holiday"))
                        is_falta   = int(reg.get("faltasDiasInteiro", 0) or 0) > 0

                        # As batidas do relógio, independentes da apuração.
                        #
                        # A RHiD só preenche totalHorasTrabalhadas quando FECHA o
                        # dia. No dia corrente ela devolve zero para todo mundo, e
                        # a tela mostrava o dia em branco com "Falta" — lido como
                        # "ninguém trabalhou hoje", que é o oposto da verdade.
                        # Também acontece em dia de batida incompleta: quem sai
                        # mais cedo sem bater o almoço aparecia como ausente.
                        #
                        # As batidas chegam assim que o relógio registra, então
                        # elas viram a fonte quando a apuração ainda não fechou.
                        marc = _rhid.marcacoes_do_registro(reg)
                        batidas_txt = " · ".join(m for m in marc if m)
                        trab_batidas = _rhid.minutos_das_marcacoes(marc)
                        em_aberto = False
                        if trabalhado <= 0 and trab_batidas > 0:
                            trabalhado = trab_batidas
                            em_aberto = True
                            is_falta = False
                        elif trabalhado <= 0 and batidas_txt:
                            # Bateu, mas não dá para fechar par nenhum: ainda está
                            # no expediente. Não é falta.
                            em_aberto = True
                            is_falta = False

                        # só inclui dias úteis ou com alguma informação relevante
                        if d and (trabalhado > 0 or is_falta or saldo_dia != 0
                                  or batidas_txt):
                            registros_diarios.append({
                                "data":       d,
                                "trab_min":   trabalhado,
                                "saldo_dia":  saldo_dia,
                                "saldo_acum": saldo_acum,
                                "falta":      is_falta,
                                "holiday":    is_holiday,
                                "batidas":    batidas_txt,
                                "em_aberto":  em_aberto,
                            })
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
        trello_user = _rhid_nome_para_trello(nome_p)

        resultados.append({
            "id":            id_p,
            "nome":          nome_p or "—",
            "trello_user":   trello_user,
            "horas_min":     horas_trab_min,
            "banco_min":     banco_min,
            "atraso_min":    total_atrasos,
            "dias_pres":     dias_presentes,
            "dias_aus":      dias_ausentes,
            "desempenho":    desempenho_pct,
            "registros":     registros_diarios,
        })

    prog.empty()

    if not resultados:
        st.info("Nenhum dado de apuração retornado pela API.")
        return

    # Quem existe na RHiD mas voltou sem nada no periodo. Antes aparecia so como
    # travessao no lugar das horas, e nao dava para saber se era falta, cadastro
    # sem relogio vinculado ou periodo errado.
    _sem_dado = [r["nome"] for r in resultados
                 if r["horas_min"] <= 0 and not r["registros"]
                 and (r.get("trello_user") or "") not in _fora_relogio]
    if _sem_dado:
        st.info(
            "ℹ️ Sem nenhum registro no período: **" + "**, **".join(_sem_dado) +
            "**. Não é o mesmo que falta — a RHiD não devolveu batida nem "
            "apuração para estes. Confira se o cadastro tem relógio vinculado e "
            "se o período escolhido é o certo."
        )

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

        # Quem nao bate ponto nao tem desempenho a mostrar: "0%" seria lido como
        # rendimento zero numa conversa de avaliacao.
        _sem_relogio = (r.get("trello_user") or "") in _nao_bate_ponto()
        _titulo_exp = (f"**{nome}** — 🕒 não bate ponto (sem medição de horas)"
                       if _sem_relogio
                       else f"**{nome}** — {horas_str} trabalhadas · {desemp_str} desempenho")
        with st.expander(_titulo_exp, expanded=False):
            if _sem_relogio:
                st.info("Este colaborador não usa o relógio de ponto. Horas, "
                        "desempenho e atrasos não se aplicam — o trabalho dele "
                        "aparece no Painel de Metas, pelos cartões do Trello.")
                continue
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

            # Tabela diária para conferência do banco de horas
            if r["registros"]:
                import pandas as _pd
                st.markdown("---")
                st.caption("📅 Detalhamento diário (banco de horas)")
                df_dias = _pd.DataFrame(r["registros"])
                df_dias["Data"]     = df_dias["data"].apply(lambda d: d.strftime("%d/%m/%Y (%a)") if d else "—")
                df_dias["Trabalhado"] = df_dias["trab_min"].apply(
                    lambda m: _rhid.fmt_horas(m) if m > 0 else "—"
                )
                df_dias["Saldo dia"]  = df_dias["saldo_dia"].apply(
                    lambda m: _rhid.fmt_banco(m) if m != 0 else "—"
                )
                df_dias["Banco acum."] = df_dias["saldo_acum"].apply(_rhid.fmt_banco)
                # A coluna das batidas e o que permite conferir o dia sem abrir a
                # RHiD: e o unico dado que existe antes de a apuracao fechar.
                df_dias["Batidas"] = df_dias.get("batidas", "").fillna("") if "batidas" in df_dias else ""

                def _obs(row):
                    if row["holiday"]:
                        return "🎉 Feriado"
                    if row["falta"]:
                        return "🔴 Falta"
                    if row.get("em_aberto"):
                        return "⏳ Dia em aberto (RHiD ainda não fechou)"
                    return ""

                df_dias["Obs."] = df_dias.apply(_obs, axis=1
                )
                st.dataframe(
                    df_dias[["Data", "Batidas", "Trabalhado", "Saldo dia",
                             "Banco acum.", "Obs."]],
                    hide_index=True,
                    use_container_width=True,
                )

            # Ociosidade via Trello (se mapeado)
            if r["trello_user"] and r["horas_min"] > 0:
                st.markdown("---")
                st.caption("🔗 Cruzamento com Trello")
                _calcular_ociosidade_trello(r["trello_user"], r["nome"], str_ini, str_fim, r["horas_min"])



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

        # Ociosidade NAO sai daqui.
        #
        # Havia aqui uma "ociosidade estimada" que multiplicava o numero de acoes
        # no Trello por 5 minutos e chamava o resto de ocioso. Nao mede nada: uma
        # pessoa que passa duas horas num cartao gera uma acao, e virava 1h55 de
        # ociosidade. Dava numeros como 79% ocioso ao lado de 96% de desempenho,
        # dois numeros que nao podem ser verdade ao mesmo tempo.
        #
        # A ociosidade de verdade e medida por linha do tempo (entrada, cartoes
        # em andamento, folgas de 10 e 5 min, 1h pessoal por dia) em
        # get_ociosidade_mes, e aparece em Analise de Metas. Um numero so, num
        # lugar so.
        dias_com_atividade = len({a["date"][:10] for a in acoes})
        acoes_total        = len(acoes)

        cols = st.columns(2)
        cols[0].metric("📋 Ações no Trello", f"{acoes_total}")
        cols[1].metric("📅 Dias com atividade", f"{dias_com_atividade}")
        st.caption("Atividade no Trello no período. A **ociosidade** medida por "
                   "linha do tempo fica em *Análise de Metas* — aqui seria um "
                   "chute com outro nome.")

    except Exception as e:
        st.caption(f"Não foi possível calcular ociosidade Trello: {e}")


# ── Página principal ────────────────────────────────────────────────────────────

def _esc_ab(texto):
    """Texto do colaborador dentro de HTML. Ele escreve o motivo à mão."""
    return (str(texto or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _cartao_pedido(a, _ab):
    """Um pedido desenhado para a fila do gestor: quem, quando, quanto, o quê."""
    dur = ((a["fim"].hour * 60 + a["fim"].minute)
           - (a["inicio"].hour * 60 + a["inicio"].minute))
    if a["status"] == _ab.APROVADO:
        cor, selo = "#1BAF7A", "✅ aprovado"
    elif a["status"] == _ab.RECUSADO:
        cor, selo = "#E34948", "🚫 recusado"
    else:
        cor, selo = "#EDA100", "⏳ aguardando você"
    nome = MEMBROS.get(a["user"], a["user"] or "equipe inteira")

    rodape = ""
    if a["status"] != _ab.PENDENTE:
        _obs = f' — "{_esc_ab(a["obs"])}"' if a["obs"] else ""
        _por = f' por {_esc_ab(a["decidido_por"])}' if a["decidido_por"] else ""
        rodape = (f'<div style="font-size:11.5px;color:{cor};margin-top:3px;">'
                  f'{selo} como {a["inicio"]:%H:%M} → {a["fim"]:%H:%M}'
                  f'{_por}{_obs}</div>')

    return (
        f'<div style="border-left:3px solid {cor};background:var(--ms-metric-bg);'
        f'border-radius:0 6px 6px 0;padding:9px 12px;">'
        f'<div style="font-size:12.5px;color:var(--ms-texto-sec);">'
        f'<span style="font-weight:700;color:var(--ms-texto);">'
        f'{_esc_ab(nome)}</span> · {a["data"]:%d/%m} · {a["inicio"]:%H:%M} → '
        f'{a["fim"]:%H:%M}<span style="color:var(--ms-texto);font-weight:700;">'
        f' · {_fmt_min(dur)}</span>'
        f'<span style="color:{cor};"> · {selo}</span></div>'
        f'<div style="font-size:13px;margin-top:3px;">'
        f'{_esc_ab(a["motivo"]) or "sem motivo"}</div>'
        f'{rodape}</div>')


def _secao_abatimentos(usuario_logado: str):
    """A fila de pedidos de abatimento de ociosidade, para decidir.

    O colaborador manda o horário de memória; quem confere tem o cartão e a
    câmera. Por isso o gestor pode aprovar MENOS do que foi pedido — 1h20 onde
    ela pediu 1h40 — em vez de só aceitar ou negar por inteiro.

    Recusa não apaga a linha: sem ver a decisão e o porquê, a pessoa manda o
    mesmo pedido de novo na semana seguinte.
    """
    st.caption(
        "Cada pedido traz **quem**, **quando**, **quanto tempo** e o **motivo**. "
        "Você pode ajustar o horário antes de aprovar — ou recusar escrevendo o "
        "porquê. O colaborador vê a decisão e o texto. Aprovado, o tempo sai da "
        "ociosidade, do tempo de execução e do atraso daquela pessoa."
    )
    try:
        import abonos as _ab
        _lista = _ab.carregar()
    except Exception as _e:
        st.warning(f"Não consegui ler os pedidos: {str(_e)[:150]}")
        return

    fila = [a for a in _ab.pendentes(_lista) if a["user"]]
    st.markdown(f"##### ⏳ Aguardando você ({len(fila)})")
    if not fila:
        st.caption("Nenhum pedido na fila.")
    for a in fila:
        k = f'ab_dec_{a["linha"]}'
        st.markdown(_cartao_pedido(a, _ab), unsafe_allow_html=True)
        c1, c2, c3, c4, c5 = st.columns([.9, .9, 2.4, 1, 1])
        _i = c1.time_input("Das", value=a["inicio"], key=f"{k}_i", step=300)
        _f = c2.time_input("Até", value=a["fim"], key=f"{k}_f", step=300)
        _o = c3.text_input("Observação (o colaborador vê)", key=f"{k}_o",
                           placeholder="opcional na aprovação, "
                                       "obrigatória na recusa")
        c4.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        c5.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        if c4.button("✅ Aprovar", key=f"{k}_ok", use_container_width=True):
            ok, msg = _ab.aprovar(a["linha"], usuario_logado, _i, _f, _o)
            st.rerun() if ok else st.error(msg)
        if c5.button("🚫 Recusar", key=f"{k}_no", use_container_width=True):
            if not (_o or "").strip():
                st.error("Escreva o porquê — é o que a pessoa vai ler.")
            else:
                ok, msg = _ab.recusar(a["linha"], usuario_logado, _o)
                st.rerun() if ok else st.error(msg)
        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

    decididos = [a for a in _lista
                 if a["user"] and a["status"] != _ab.PENDENTE]
    st.markdown(f"##### ✅ Já decididos ({len(decididos)})")
    if not decididos:
        st.caption("Nada decidido ainda.")
        return
    for a in decididos[:25]:
        c1, c2 = st.columns([9, 1])
        c1.markdown(_cartao_pedido(a, _ab), unsafe_allow_html=True)
        # Apagar existe para o engano — aprovou o pedido errado, recusou sem
        # ler. Reabrir a decisao mudaria indicador de mes fechado sem rastro.
        if c2.button("🗑️", key=f'ab_del_{a["linha"]}',
                     use_container_width=True, help="Apagar o pedido"):
            ok, msg = _ab.remover_linha(a["linha"])
            st.rerun() if ok else st.error(msg)
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)


def pagina_ponto(usuario_logado: str):
    """Página completa do Relógio de Ponto."""
    eh_master = usuario_logado.lower() in {m.lower() for m in MASTERS}

    st.markdown("### 🕐 Relógio de Ponto")
    st.caption(
        "Registre entradas, saídas e ausências. A IA utiliza esses dados para calcular "
        "ociosidade por colaborador e alertar sobre sobrecarga em caso de ausência."
    )

    if eh_master:
        (tab_relatorio, tab_abat, tab_hoje, tab_registro,
         tab_historico) = st.tabs(
            ["📊 Relatório RHiD", "🙋 Abatimentos", "📡 Status Hoje",
             "✏️ Registrar", "📋 Histórico Mensal"]
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

        with tab_abat:
            st.markdown("#### 📥 Pedidos de abatimento")
            _secao_abatimentos(usuario_logado)

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
