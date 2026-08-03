"""
metas_config.py — Configurações mensais de metas persistidas no Google Sheets
Aba: "metas_config" na planilha "MartinSousa - Financeiro"
"""
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

PLANILHA_NOME = "MartinSousa - Financeiro"
ABA_NOME = "metas_config"

# Ordem fixa de colunas na planilha
COLUNAS = [
    "ano", "mes",
    "meta_equipe",           # pontos meta coletiva
    "meta_maxx_pct",         # % da meta mensal (ex: 110 = 10% a mais)
    "meta_myrelladesouza",   # meta individual Myrella
    "meta_beatriz51",        # meta individual Beatriz
    "meta_gabriel_borges",   # meta individual Gabriel
    "max_pen_normal",        # máx penalidades meta normal (ex: 4)
    "max_pen_maxx",          # máx penalidades meta maxx (ex: 1)
    "max_tol_normal",        # máx tolerâncias pontualidade normal (ex: 15)
    "max_tol_maxx",          # máx tolerâncias pontualidade maxx (ex: 7)
    "max_atr_normal",        # máx atrasos pontualidade normal (ex: 10)
    "max_atr_maxx",          # máx atrasos pontualidade maxx (ex: 5)
    "max_retrab_normal",     # % retrabalho máx normal (ex: 10)
    "max_retrab_maxx",       # % retrabalho máx maxx (ex: 5)
    "min_membro_pct",        # % mín cartões com membro (ex: 95)
]

DEFAULTS = {
    "meta_equipe":         5000,
    "meta_maxx_pct":       110,
    "meta_myrelladesouza": 1500,
    "meta_beatriz51":      1500,
    "meta_gabriel_borges": 1500,
    "max_pen_normal":      4,
    "max_pen_maxx":        1,
    "max_tol_normal":      15,
    "max_tol_maxx":        7,
    "max_atr_normal":      10,
    "max_atr_maxx":        5,
    "max_retrab_normal":   10,
    "max_retrab_maxx":     5,
    "min_membro_pct":      95,
}

# Rótulos legíveis para exibição na UI
LABELS = {
    "meta_equipe":         "Meta Equipe (pts)",
    "meta_maxx_pct":       "Meta MAXX (% da meta mensal)",
    "meta_myrelladesouza": "Meta Individual — Myrella (pts)",
    "meta_beatriz51":      "Meta Individual — Beatriz (pts)",
    "meta_gabriel_borges": "Meta Individual — Gabriel (pts)",
    "max_pen_normal":      "Máx. penalidades (Meta Normal)",
    "max_pen_maxx":        "Máx. penalidades (Meta MAXX)",
    "max_tol_normal":      "Máx. tolerâncias pontualidade (Normal)",
    "max_tol_maxx":        "Máx. tolerâncias pontualidade (MAXX)",
    "max_atr_normal":      "Máx. atrasos pontualidade (Normal)",
    "max_atr_maxx":        "Máx. atrasos pontualidade (MAXX)",
    "max_retrab_normal":   "Retrabalho máx. % (Normal)",
    "max_retrab_maxx":     "Retrabalho máx. % (MAXX)",
    "min_membro_pct":      "% mín. cartões com membro",
}

# ── Conexão ────────────────────────────────────────────────────────────────────

def _cliente():
    creds_dict = dict(st.secrets["gcp_service_account"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)


def _aba():
    cliente = _cliente()
    planilha = cliente.open(PLANILHA_NOME)
    try:
        aba = planilha.worksheet(ABA_NOME)
        cabecalho = aba.row_values(1)
        for col in COLUNAS:
            if col not in cabecalho:
                aba.add_cols(1)
                aba.update_cell(1, len(cabecalho) + 1, col)
                cabecalho.append(col)
        return aba
    except gspread.exceptions.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA_NOME, rows=500, cols=len(COLUNAS))
        aba.append_row(COLUNAS, value_input_option="RAW")
        return aba

# ── Leitura ────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def carregar_todas() -> pd.DataFrame:
    """Retorna DataFrame com todos os registros de configuração de metas."""
    try:
        aba = _aba()
        registros = aba.get_all_records(value_render_option="UNFORMATTED_VALUE")
        df = pd.DataFrame(registros)
        if not df.empty:
            df.columns = [str(c).strip().lower() for c in df.columns]
            for col in ["ano", "mes"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        return df
    except Exception:
        return pd.DataFrame()


def carregar_config(ano: int, mes: int) -> dict:
    """Retorna dict de configuração para o mês. Valores ausentes são preenchidos com defaults."""
    cfg = {**DEFAULTS, "ano": int(ano), "mes": int(mes)}
    try:
        df = carregar_todas()
        if df.empty:
            return cfg
        mask = (df["ano"] == int(ano)) & (df["mes"] == int(mes))
        linha = df[mask]
        if linha.empty:
            return cfg
        row = linha.iloc[-1]
        for k in DEFAULTS:
            val = row.get(k)
            try:
                v = float(val)
                cfg[k] = int(v) if v == int(v) else v
            except Exception:
                pass
    except Exception:
        pass
    return cfg

# ── Escrita ────────────────────────────────────────────────────────────────────

def salvar_config(ano: int, mes: int, dados: dict):
    """Salva ou atualiza a configuração do mês no Google Sheets."""
    try:
        aba = _aba()
        registros = aba.get_all_records(value_render_option="UNFORMATTED_VALUE")

        # Localiza linha existente (ano+mes)
        linha_idx = None
        for i, r in enumerate(registros, start=2):
            try:
                if int(r.get("ano", 0)) == int(ano) and int(r.get("mes", 0)) == int(mes):
                    linha_idx = i
                    break
            except Exception:
                pass

        nova = [int(ano), int(mes)] + [
            dados.get(col, DEFAULTS.get(col, "")) for col in COLUNAS[2:]
        ]

        if linha_idx:
            aba.update(f"A{linha_idx}", [nova])
        else:
            aba.append_row(nova, value_input_option="RAW")

        carregar_todas.clear()
    except Exception as e:
        st.error(f"Erro ao salvar configuração: {e}")