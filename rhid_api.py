"""
rhid_api.py — Cliente da API RHiD (ControlID) para MS Studio

Endpoints utilizados:
  POST /login            → obtém accessToken (JWT)
  GET  /person           → lista colaboradores
  GET  /person/{id}      → detalhes de um colaborador
  GET  /apuracao_ponto   → apuração de ponto por período e pessoa

Autenticação: Bearer Token no header Authorization.
Token armazenado em st.session_state; renovado automaticamente ao expirar.
"""

import streamlit as st
import requests
from datetime import datetime, timedelta
from typing import Optional

BASE_URL = "https://rhid.com.br/v2/api.svc"
TOKEN_TTL_MIN = 50  # JWT RHiD expira ~60 min; renova aos 50 min


# ── Configuração ────────────────────────────────────────────────────────────────

def _cfg() -> dict:
    """Lê credenciais de st.secrets['rhid'] com fallback para defaults vazios."""
    try:
        s = st.secrets["rhid"]
        return {
            "email":    s.get("email",    ""),
            "password": s.get("password", ""),
            "domain":   s.get("domain",   ""),
        }
    except Exception:
        return {"email": "", "password": "", "domain": ""}


# ── Gestão de token ─────────────────────────────────────────────────────────────

def _token_valido() -> bool:
    exp = st.session_state.get("rhid_token_exp")
    return bool(exp and datetime.now() < exp)


def get_token() -> Optional[str]:
    """Retorna token válido (do cache ou faz novo login)."""
    if _token_valido():
        return st.session_state["rhid_token"]

    cfg = _cfg()
    if not cfg["email"]:
        return None

    try:
        resp = requests.post(
            f"{BASE_URL}/login",
            json={
                "email":    cfg["email"],
                "password": cfg["password"],
                "domain":   cfg["domain"],
                "system":   "rhid",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        # accessToken pode estar direto ou dentro de listCustomer[0]
        token = data.get("accessToken", "")
        if not token:
            customers = data.get("listCustomer") or []
            if customers:
                token = customers[0].get("accessToken", "")

        if token:
            st.session_state["rhid_token"]     = token
            st.session_state["rhid_token_exp"] = datetime.now() + timedelta(minutes=TOKEN_TTL_MIN)
            return token

        # Login sem token — erro retornado pela API
        st.session_state["rhid_login_error"] = data.get("error", "Login retornou sem token")
        return None

    except requests.exceptions.RequestException as e:
        st.session_state["rhid_login_error"] = str(e)
        st.session_state.pop("rhid_token", None)
        st.session_state.pop("rhid_token_exp", None)
        return None


def _headers() -> dict:
    token = get_token()
    if not token:
        raise ValueError("Token RHiD indisponível — verifique credenciais em st.secrets['rhid']")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def invalidar_token():
    """Força novo login na próxima chamada."""
    st.session_state.pop("rhid_token", None)
    st.session_state.pop("rhid_token_exp", None)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def get_persons() -> list[dict]:
    """
    Retorna lista de colaboradores cadastrados na RHiD.
    Tenta múltiplas variações de endpoint/parâmetros.
    Cache de 5 minutos.
    """
    endpoints = [
        # (url_suffix, params)
        ("/person",    {"start": 0, "length": 500}),
        ("/person",    {}),
        ("/persons",   {"start": 0, "length": 500}),
        ("/employee",  {"start": 0, "length": 500}),
        ("/collaborator", {}),
    ]
    last_err = "Nenhuma tentativa realizada"
    for suffix, params in endpoints:
        try:
            resp = requests.get(
                f"{BASE_URL}{suffix}",
                headers=_headers(),
                params=params,
                timeout=15,
            )
            if resp.status_code == 500:
                last_err = f"500 em {suffix}"
                continue
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                for key in ("records", "data", "persons", "colaboradores", "items", "content"):
                    if key in data and isinstance(data[key], list) and data[key]:
                        return data[key]
                vals = list(data.values())
                flat = []
                for v in vals:
                    if isinstance(v, list):
                        flat.extend(v)
                    elif isinstance(v, dict):
                        flat.append(v)
                if flat:
                    return flat
            elif isinstance(data, list) and data:
                return data
            last_err = f"Sem dados em {suffix} (status {resp.status_code})"
        except Exception as e:
            last_err = str(e)
    return []


def get_apuracao(data_ini: str, data_final: str, id_person: int) -> Optional[dict]:
    """
    Retorna apuração de ponto de um colaborador num período.

    Parâmetros:
      data_ini, data_final: 'yyyy-MM-dd'  (intervalo máx. 90 dias)
      id_person: id numérico da pessoa na RHiD

    Retorno: dict com os dados (estrutura depende da versão da API),
             ou None em caso de erro.
    """
    try:
        resp = requests.get(
            f"{BASE_URL}/apuracao_ponto",
            headers=_headers(),
            params={
                "dataIni":   data_ini,
                "dataFinal": data_final,
                "idPerson":  id_person,
            },
            timeout=20,
        )
        resp.raise_for_status()
        try:
            data = resp.json()
            # Se a API retornar uma string JSON (ex.: "null", "[]", ou texto puro)
            if isinstance(data, dict):
                return data
            if isinstance(data, list):
                return {"records": data, "_status": resp.status_code}
            # A RHiD pode retornar a lista serializada como string JSON dupla
            if isinstance(data, str):
                import json as _json
                try:
                    inner = _json.loads(data)
                    if isinstance(inner, list):
                        return {"records": inner, "_status": resp.status_code}
                    if isinstance(inner, dict):
                        return inner
                except (ValueError, TypeError):
                    pass
            # Outro tipo primitivo — preserva raw para debug
            return {"_raw": str(data), "_status": resp.status_code}
        except ValueError:
            # Resposta não é JSON (ex.: string pura ou CSV)
            return {"_raw": resp.text, "_status": resp.status_code}
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 401:
            invalidar_token()
        return None
    except Exception:
        return None


def get_person(id_person: int) -> Optional[dict]:
    """Retorna dados completos de um colaborador pelo ID."""
    try:
        resp = requests.get(
            f"{BASE_URL}/person/{id_person}",
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


# ── Utilitários de parse ────────────────────────────────────────────────────────

def parse_horario(valor: Optional[str]) -> Optional[datetime]:
    """
    Tenta parsear um horário retornado pela API no formato HH:MM, HH:MM:SS
    ou ISO 8601 completo.
    """
    if not valor:
        return None
    formatos = ["%H:%M:%S", "%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]
    for fmt in formatos:
        try:
            return datetime.strptime(valor.strip(), fmt)
        except ValueError:
            pass
    return None


def minutos_entre(t1: Optional[datetime], t2: Optional[datetime]) -> float:
    """Diferença em minutos (t2 - t1). Retorna 0 se inválido."""
    if not t1 or not t2:
        return 0.0
    return max((t2 - t1).total_seconds() / 60, 0.0)


def fmt_horas(minutos: float) -> str:
    """Formata minutos em 'Xh Ymin'."""
    if minutos <= 0:
        return "—"
    h  = int(minutos // 60)
    m  = int(minutos % 60)
    if h > 0 and m > 0:
        return f"{h}h {m:02d}min"
    elif h > 0:
        return f"{h}h"
    return f"{m}min"


def fmt_banco(minutos: float) -> str:
    """Formata saldo do banco de horas com sinal: '+2h15min' ou '-30min'. Retorna '0' se zerado."""
    if minutos == 0:
        return "0"
    sinal = "+" if minutos > 0 else "-"
    return f"{sinal}{fmt_horas(abs(minutos))}"


# ── Batidas diárias (fonte oficial de pontualidade) ───────────────────────────
# A equipe registra ponto SOMENTE no relógio físico — nunca pelo Studio. Então a
# pontualidade tem que sair daqui, não da planilha.
#
# O nome dos campos varia entre versões da RHiD, e não dá para descobrir sem ver
# a resposta real. Por isso a normalização tenta todas as variações conhecidas e
# devolve, junto, as chaves cruas do primeiro registro: se nenhuma bater, o
# diagnóstico mostra o que veio em vez de devolver zero em silêncio.

_CAMPOS_LISTA_BATIDAS = (
    "batidas", "marcacoes", "marcacoesDia", "pontos", "horarios",
    "apontamentos", "registrosPonto", "punches", "clockings",
)
_CAMPOS_DATA = ("dateTimeStr", "date", "data", "dia", "dataStr", "dataRegistro")
_CAMPOS_HORA = ("hora", "horario", "time", "dateTime", "marcacao", "batida",
                "valor", "value", "horaMarcacao")
_SEQUENCIAS_ENTRADA_SAIDA = (
    # A apuração da RHiD traz as quatro marcações em "colunaMix" — é o que a
    # tela mostra como Ent.1 / Saí.1 / Ent.2 / Saí.2.
    ("colunaMix1", "colunaMix2", "colunaMix3", "colunaMix4"),
    ("mix1", "mix2", "mix3", "mix4"),
    ("entrada1", "saida1", "entrada2", "saida2"),
    ("entrada", "saidaAlmoco", "voltaAlmoco", "saida"),
    ("entrada", "saida_almoco", "volta_almoco", "saida"),
    ("e1", "s1", "e2", "s2"),
)


def _extrair_hhmm(valor) -> Optional[str]:
    """Extrai 'HH:MM' de string, timestamp ou dict aninhado. None se não der."""
    if valor is None:
        return None
    if isinstance(valor, dict):
        for c in _CAMPOS_HORA:
            if c in valor:
                achou = _extrair_hhmm(valor[c])
                if achou:
                    return achou
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    # "2026-08-25T08:59:00" / "2026-08-25 08:59" → pega a parte da hora
    if "T" in texto or " " in texto:
        texto = texto.replace("T", " ").split(" ")[-1]
    # "085900" → "08:59"
    if texto.isdigit() and len(texto) in (4, 6):
        return f"{texto[:2]}:{texto[2:4]}"
    partes = texto.split(":")
    if len(partes) >= 2 and partes[0].isdigit() and partes[1][:2].isdigit():
        h, m = int(partes[0]), int(partes[1][:2])
        if 0 <= h <= 23 and 0 <= m <= 59:
            return f"{h:02d}:{m:02d}"
    return None


def _extrair_data(reg: dict):
    """date do registro diário, ou None."""
    from datetime import datetime as _dt
    for c in _CAMPOS_DATA:
        v = reg.get(c)
        if not v:
            continue
        t = str(v)
        try:
            if len(t) == 8 and t.isdigit():        # "20260825"
                return _dt.strptime(t, "%Y%m%d").date()
            if "/" in t[:10]:                       # "25/08/2026"
                return _dt.strptime(t[:10], "%d/%m/%Y").date()
            return _dt.fromisoformat(t[:10]).date()
        except (ValueError, TypeError):
            continue
    return None


def _extrair_marcacoes(reg: dict):
    """As quatro marcações do dia: (entrada, saída almoço, volta almoço, saída).

    A tela da RHiD chama de Ent.1 / Saí.1 / Ent.2 / Saí.2. Os campos nomeados vêm
    ANTES de qualquer lista de batidas: a RHiD também devolve as marcações
    excluídas do cálculo (coluna "Exclusões"), e uma lista crua misturaria as
    duas coisas. Dia de "Folga" ou "Justif" não tem horário e volta tudo None.
    """
    for sequencia in _SEQUENCIAS_ENTRADA_SAIDA:
        valores = [_extrair_hhmm(reg.get(c)) for c in sequencia]
        if any(valores):
            return tuple(valores)

    # Sem campos nomeados: usa a lista de batidas na ordem do relógio.
    horas = _extrair_batidas(reg)
    horas = horas + [None] * 4
    return tuple(horas[:4])


def _extrair_batidas(reg: dict) -> list[str]:
    """Horários de marcação do dia, em ordem, como 'HH:MM'."""
    for campo in _CAMPOS_LISTA_BATIDAS:
        bruto = reg.get(campo)
        if isinstance(bruto, list) and bruto:
            horas = [h for h in (_extrair_hhmm(b) for b in bruto) if h]
            if horas:
                return sorted(horas)
        if isinstance(bruto, str) and bruto.strip():
            # "08:59, 12:01, 13:00, 18:02" ou "08:59 12:01 13:00 18:02"
            pedacos = bruto.replace(";", ",").replace(" ", ",").split(",")
            horas = [h for h in (_extrair_hhmm(p) for p in pedacos) if h]
            if horas:
                return sorted(horas)

    return []


def get_registros_diarios(data_ini: str, data_final: str, id_person: int):
    """Registros diários de ponto de uma pessoa, normalizados.

    Devolve (lista, diagnostico). Cada item:
      {"data": date, "batidas": ["08:59", ...],
       "entrada"/"saida_almoco"/"volta_almoco"/"saida": "HH:MM"|None,
       "minutos_atraso": float|None, "minutos_trabalhados": float, "faltou": bool}

    O diagnóstico diz o que aconteceu quando a lista vem vazia — nunca devolve
    silêncio: {"erro": str|None, "registros_brutos": int, "com_batidas": int,
    "chaves_exemplo": [str]}.
    """
    diag = {"erro": None, "registros_brutos": 0, "com_batidas": 0,
            "chaves_exemplo": [], "campos_com_hora": [], "data_amostra": ""}

    apuracao = get_apuracao(data_ini, data_final, id_person)
    if not apuracao:
        diag["erro"] = "A RHiD não respondeu à apuração de ponto."
        return [], diag
    if apuracao.get("_raw"):
        diag["erro"] = f"Resposta não reconhecida da RHiD: {str(apuracao['_raw'])[:120]}"
        return [], diag

    brutos = apuracao.get("registros", apuracao.get("records", apuracao.get("data", [])))
    if not isinstance(brutos, list):
        brutos = [apuracao] if isinstance(apuracao, dict) else []
    diag["registros_brutos"] = len(brutos)
    if brutos and isinstance(brutos[0], dict):
        diag["chaves_exemplo"] = sorted(brutos[0].keys())
        # Em vez de despejar o JSON inteiro (que fica cortado na tela e não cabe
        # numa captura), procura sozinho os campos que CONTÊM horário. É o que
        # falta saber: o nome do campo não diz nada se o formato for outro.
        _amostra = None
        _melhor = -1
        for _r in brutos:
            if not isinstance(_r, dict):
                continue
            _n = sum(1 for v in _r.values() if _extrair_hhmm(v))
            if _n > _melhor:
                _melhor, _amostra = _n, _r
            if _n >= 4:
                break
        if _amostra is not None:
            diag["campos_com_hora"] = [
                f"{k} = {v!r} → {_extrair_hhmm(v)}"
                for k, v in sorted(_amostra.items())
                if _extrair_hhmm(v)
            ][:20]
            diag["data_amostra"] = str(_amostra.get("dateTimeStr")
                                       or _amostra.get("date") or "?")[:20]

    saida = []
    for reg in brutos:
        if not isinstance(reg, dict):
            continue
        marcacoes = _extrair_marcacoes(reg)
        batidas = [m for m in marcacoes if m]
        if batidas:
            diag["com_batidas"] += 1
        atraso = reg.get("minutosAtraso", reg.get("atraso", reg.get("lateMinutes")))
        try:
            atraso = float(atraso) if atraso is not None else None
        except (TypeError, ValueError):
            atraso = None
        try:
            trabalhados = float(reg.get("totalHorasTrabalhadas",
                                        reg.get("horasTrabalhadas",
                                        reg.get("workedMinutes", 0))) or 0)
        except (TypeError, ValueError):
            trabalhados = 0.0
        saida.append({
            "data": _extrair_data(reg),
            "batidas": batidas,
            "entrada":      marcacoes[0],
            "saida_almoco": marcacoes[1],
            "volta_almoco": marcacoes[2],
            "saida":        marcacoes[3],
            "minutos_atraso": atraso,
            "minutos_trabalhados": trabalhados,
            "faltou": bool(int(reg.get("faltasDiasInteiro", reg.get("ausente", 0)) or 0)),
        })

    if saida and diag["com_batidas"] == 0:
        diag["erro"] = ("A RHiD devolveu os dias, mas nenhum horário de batida foi "
                        "reconhecido nos campos conhecidos.")
    return saida, diag
