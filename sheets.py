"""
sheets.py — uma conexão só com a planilha, para o Studio inteiro.

Por que este módulo existe
--------------------------
Nove módulos montavam a própria conexão, cada um com o mesmo bloco copiado:
credencial, `gspread.authorize()` e `cliente.open(PLANILHA_NOME)`. Numa máquina
já aquecida isso passava despercebido, porque cada um deles é `cache_resource` e
roda uma vez por processo. Num container recém-subido — depois de todo deploy —
é a primeira coisa que acontece, e o custo aparece inteiro na tela de login.

Duas idas à rede por módulo, nove vezes:

  authorize()            troca a chave do service account por um token OAuth
  open(PLANILHA_NOME)    NÃO abre a planilha: procura por nome no Drive inteiro
                         (files.list paginado, pageSize=1000, incluindo drives
                         compartilhados) e só então monta o objeto

A busca por nome é a parte cara. `open_by_key()` não faz requisição nenhuma —
monta a planilha direto do ID. Com o secret PLANILHA_ID configurado, o Studio
deixa de varrer o Drive; sem ele, continua abrindo por nome como antes.

Timeout
-------
O gspread aceita timeout e vem com `None`, que em `requests` significa esperar
para sempre. Uma conexão pendurada com o Google travava a tela de login sem
erro nenhum — o mesmo tipo de falha que já tinha derrubado a TV pelo lado do
Trello. Aqui ele é explícito.
"""

import streamlit as st

import planilha as _plan

# Conectar, ler. Generoso na leitura porque get_all_records de uma aba grande
# demora mesmo; curto na conexão porque conexão que não estabelece em 10s não
# vai estabelecer.
TIMEOUT = (10, 45)

ESCOPOS = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _id_configurado():
    """ID da planilha, quando houver. Sem ele, abre por nome como antes."""
    try:
        return str(st.secrets.get("PLANILHA_ID", "") or "").strip()
    except Exception:
        return ""


@st.cache_resource
def cliente():
    """Cliente gspread compartilhado — uma troca de token por processo."""
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=ESCOPOS)
    gc = gspread.authorize(creds)
    try:
        gc.set_timeout(TIMEOUT)
    except Exception:
        pass   # versão de gspread sem set_timeout: segue sem timeout, como antes
    return gc


@st.cache_resource
def planilha():
    """A planilha deste ambiente, aberta uma vez por processo."""
    gc = cliente()
    chave = _id_configurado()
    if chave:
        return gc.open_by_key(chave)
    return gc.open(_plan.nome())
