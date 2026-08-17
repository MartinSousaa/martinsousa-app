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
            st.session_state["rhid_login_data"] = data  # guarda resposta completa para debug
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
    Cache de 5 minutos.
    """
    try:
        resp = requests.get(
            f"{BASE_URL}/person",
            headers=_headers(),
            params={"start": 0, "length": 500},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            return data.get("records", data.get("data", []))
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
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
            return resp.json()
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
    """Formata saldo do banco de horas com sinal: '+2h15min' ou '-30min'."""
    sinal = "+" if minutos >= 0 else "-"
    return f"{sinal}{fmt_horas(abs(minutos))}"
