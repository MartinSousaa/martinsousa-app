"""Configuração por coluna do Trello — prioridade, tempo estimado e espera.

Por que este módulo existe
--------------------------
Prioridade e tempo estimado viviam escritos no código. Cada coluna nova ou
renomeada no Trello exigia uma alteração de código para voltar a aparecer no
painel — e, até isso acontecer, o trabalho dela sumia em silêncio.

Aqui a configuração vive numa aba da planilha e é editável pelo gestor. O código
continua com os valores de origem como reserva: se a planilha não responder, o
painel usa o que já usava, em vez de zerar tudo.

Três números por coluna:
  prioridade  — ordem na fila (maior primeiro)
  tempo_min   — quanto se espera que a execução leve, em minutos
  espera_h    — horas de espera de TERCEIRO antes de a demanda ser executável
                (ex.: 36h de retorno da plataforma). Espera não é trabalho: o
                cartão fica fora da fila até o prazo estar vencendo.
"""

import streamlit as st

import planilha as _plan
# Nome vindo do ambiente: producao usa o padrao, homologacao usa a copia.
PLANILHA_NOME = _plan.nome()
ABA_NOME = "colunas_config"
COLUNAS = ["coluna", "prioridade", "tempo_min", "espera_h"]


def _crono(rotulo, seg, detalhe=""):
    """Registra quanto custou uma ida a planilha. Nunca derruba a leitura."""
    try:
        import cronometro
        cronometro.marcar(rotulo, seg, detalhe)
    except Exception:
        pass


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
        return planilha.worksheet(ABA_NOME)
    except Exception:
        aba = planilha.add_worksheet(title=ABA_NOME, rows=200, cols=len(COLUNAS))
        aba.append_row(COLUNAS, value_input_option="RAW")
        return aba


@st.cache_data(ttl=600)
def carregar() -> dict:
    """{nome_da_coluna: {"prioridade": int, "tempo_min": int, "espera_h": int|None}}.

    Devolve vazio em qualquer falha — quem chama cai nos valores de origem.
    """
    try:
        import time as _t_crono
        _t0_crono = _t_crono.perf_counter()
        registros = _aba().get_all_records()
        _crono("Planilha: colunas", _t_crono.perf_counter() - _t0_crono,
               f"{len(registros)} linhas")
    except Exception:
        return {}

    saida = {}
    for linha in registros:
        nome = str(linha.get("coluna", "")).strip()
        if not nome:
            continue
        cfg = {}
        for campo, chave in (("prioridade", "prioridade"),
                             ("tempo_min", "tempo_min"),
                             ("espera_h", "espera_h")):
            valor = linha.get(campo)
            if valor in (None, ""):
                continue
            try:
                num = int(float(valor))
            except (TypeError, ValueError):
                continue
            if num > 0 or chave == "prioridade":
                cfg[chave] = num
        if cfg:
            saida[nome] = cfg
    return saida


def salvar(nome_coluna, prioridade, tempo_min, espera_h=None):
    """Grava (ou atualiza) a configuração de uma coluna."""
    aba = _aba()
    linha = [str(nome_coluna), int(prioridade), int(tempo_min),
             int(espera_h) if espera_h else ""]
    try:
        celula = aba.find(str(nome_coluna), in_column=1)
    except Exception:
        celula = None
    if celula:
        aba.update(f"A{celula.row}:D{celula.row}", [linha], value_input_option="RAW")
    else:
        aba.append_row(linha, value_input_option="RAW")
    carregar.clear()
