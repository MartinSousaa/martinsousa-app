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
    """ID da planilha, quando houver. Sem ele, abre por nome como antes.

    Como configurar
    ---------------
    O segredo chega pela variavel de ambiente PLANILHA_ID, que o Procfile
    escreve no secrets.toml ANTES do bloco STREAMLIT_SECRETS. A ordem nao e
    detalhe: em TOML, chave solta escrita depois de um cabecalho [secao]
    pertence aquela secao. Acrescentada no fim do bloco de segredos, esta linha
    viraria trello.PLANILHA_ID -- sem erro nenhum, so o Drive sendo varrido de
    novo a cada container novo, que e exatamente o custo que ela existe para
    evitar. Variavel nao definida nao escreve linha alguma.

    O valor e o trecho entre /d/ e /edit da URL da planilha.
    """
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


# Motivo de a planilha ter sido aberta pelo nome, quando havia um ID. Lido pela
# tela para avisar; vazio quando nao houve problema.
ID_RECUSADO = {"motivo": ""}


@st.cache_resource
def planilha():
    """A planilha deste ambiente, aberta uma vez por processo.

    O ID so e aceito se o titulo bater com o nome esperado do ambiente.

    Sem essa conferencia, o ID de producao colado por engano no ambiente de
    teste faria o teste ESCREVER na planilha de verdade — com a faixa amarela
    de "nada aqui afeta o Studio de verdade" no topo da tela, dizendo o
    contrario. O nome e escolhido por ambiente em planilha.py; o ID nao passa
    por ali, entao ele tem que se justificar contra o nome.

    O titulo nao custa requisicao: gspread ja busca o metadata da planilha ao
    construir o objeto, tanto por ID quanto por nome.
    """
    gc = cliente()
    chave = _id_configurado()
    esperado = _plan.nome()
    ID_RECUSADO["motivo"] = ""
    if chave:
        try:
            pl = gc.open_by_key(chave)
            titulo = str(getattr(pl, "title", "") or "").strip()
            if titulo == esperado:
                return pl
            ID_RECUSADO["motivo"] = (
                f'PLANILHA_ID aponta para "{titulo}", mas este ambiente é '
                f'"{esperado}". Abri pelo nome e ignorei o ID.')
        except Exception as e:
            ID_RECUSADO["motivo"] = (
                f"PLANILHA_ID configurado, mas não consegui abrir por ele "
                f"({str(e)[:120]}). Abri pelo nome.")
    return gc.open(esperado)
