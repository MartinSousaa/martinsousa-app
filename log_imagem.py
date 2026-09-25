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
# `prompt` guarda o TEXTO QUE FOI AO MOTOR — o de geração e o de ajuste, cada
# um na sua linha. Sem ele não dá para responder a pergunta que o dono fez em
# 25/09: "o que o prompt da correção tinha que o da geração não tinha?".
#
# E a resposta interessa nos dois sentidos. Se o ajuste trouxe uma regra NOVA,
# falta essa regra na geração. Se trouxe uma regra que JÁ ESTAVA lá, o modelo
# desobedeceu — e aí escrever mais não resolve nada.
COLUNAS = ["quando", "usuario", "produto", "acao", "imagem", "tipo",
           "instrucao", "resultado", "prompt"]


@st.cache_resource
def _aba():
    # A planilha e aberta uma vez por processo em sheets.py. Aqui cada
    # modulo abria a sua, e abrir por nome custa uma varredura do Drive.
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        return planilha.worksheet(ABA_LOG)
    except Exception:
        aba = planilha.add_worksheet(title=ABA_LOG, rows=5000, cols=len(COLUNAS))
        aba.append_row(COLUNAS, value_input_option="RAW")
        return aba


def registrar(acao, instrucao="", imagem=None, tipo="", resultado="",
              prompt=""):
    """Grava uma linha de registro. Nunca levanta exceção."""
    try:
        _ab = _aba()
        _garantir_coluna_prompt(_ab)
        _ab.append_row(
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
                # A célula do Sheets aceita 50 mil caracteres; o prompt real
                # dá uns 6 mil. O corte é folga, não aperto.
                str(prompt or "")[:45000],
            ],
            value_input_option="RAW",
        )
    except Exception:
        # Registro é apoio, não requisito: uma planilha fora do ar não pode
        # impedir o colaborador de gerar imagem.
        pass


_cabecalho_conferido = False


def _garantir_coluna_prompt(aba):
    """A aba antiga tem 8 colunas; a nona precisa existir no cabeçalho.

    Sem isto, `append_row` grava o prompt na coluna I e `get_all_records`
    devolve a linha sem ele — ou reclama do cabeçalho vazio. O registro que
    não se consegue ler não é registro.

    UMA VEZ POR PROCESSO. A primeira versão lia o cabeçalho a cada linha
    gravada: oito imagens viravam oito leituras a mais do Drive, no meio da
    geração, que é o momento em que o colaborador já está esperando. O
    cabeçalho não muda sozinho durante um processo.
    """
    global _cabecalho_conferido
    if _cabecalho_conferido:
        return
    _cabecalho_conferido = True
    try:
        cab = aba.row_values(1) or []
        if len(cab) >= len(COLUNAS):
            return
        aba.update(f"A1:{chr(ord('A') + len(COLUNAS) - 1)}1", [COLUNAS],
                   value_input_option="RAW")
    except Exception:
        pass


def ler(limite=200):
    """Últimos registros, mais recentes primeiro. Lista vazia se falhar."""
    try:
        linhas = _aba().get_all_records()
    except Exception:
        return []
    return list(reversed(linhas))[:limite]
