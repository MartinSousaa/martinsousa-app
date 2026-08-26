"""Registro dos comandos que o Assistente IA executa sobre imagens.

Por que este módulo existe
--------------------------
Quando uma geração sai errada, a primeira pergunta é "o que foi pedido?". Até
agora a resposta vivia só na sessão do colaborador: ele encerrava o expediente,
a conversa sumia e não sobrava nada para investigar. Foi exatamente o que
aconteceu no episódio do Gladiador — sete imagens refeitas fora do padrão e
nenhum rastro do que causou.

Cada comando vira uma linha numa aba da planilha. Uma linha por comando, com
quem pediu, em qual imagem e o que pediu.

Falhar aqui nunca pode derrubar a geração: se a planilha não responder, o
registro se perde mas o trabalho continua.
"""

import streamlit as st
from datetime import datetime

import planilha as _plan
# Nome vindo do ambiente: producao usa o padrao, homologacao usa a copia.
PLANILHA_NOME = _plan.nome()
ABA_LOG = "log_imagem"
COLUNAS = ["quando", "usuario", "produto", "acao", "imagem", "tipo", "instrucao", "resultado"]


@st.cache_resource
def _aba():
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"],
    )
    planilha = gspread.authorize(creds).open(PLANILHA_NOME)
    try:
        return planilha.worksheet(ABA_LOG)
    except Exception:
        aba = planilha.add_worksheet(title=ABA_LOG, rows=5000, cols=len(COLUNAS))
        aba.append_row(COLUNAS, value_input_option="RAW")
        return aba


def registrar(acao, instrucao="", imagem=None, tipo="", resultado=""):
    """Grava uma linha de registro. Nunca levanta exceção."""
    try:
        _aba().append_row(
            [
                datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                str(st.session_state.get("usuario", "?")),
                str(st.session_state.get("img_nome_produto", "")
                    or st.session_state.get("nome_produto", "")),
                str(acao),
                "" if imagem is None else str(imagem),
                str(tipo)[:60],
                str(instrucao)[:500],
                str(resultado)[:300],
            ],
            value_input_option="RAW",
        )
    except Exception:
        # Registro é apoio, não requisito: uma planilha fora do ar não pode
        # impedir o colaborador de gerar imagem.
        pass


def ler(limite=200):
    """Últimos registros, mais recentes primeiro. Lista vazia se falhar."""
    try:
        linhas = _aba().get_all_records()
    except Exception:
        return []
    return list(reversed(linhas))[:limite]
