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
    # A planilha e aberta uma vez por processo em sheets.py. Aqui cada
    # modulo abria a sua, e abrir por nome custa uma varredura do Drive.
    import sheets as _sh
    planilha = _sh.planilha()
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


ABA_OCULTAS = "colunas_ocultas"


@st.cache_resource
def _aba_ocultas():
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        return planilha.worksheet(ABA_OCULTAS)
    except Exception:
        aba = planilha.add_worksheet(title=ABA_OCULTAS, rows=100, cols=1)
        aba.append_row(["coluna"], value_input_option="RAW")
        return aba


@st.cache_data(ttl=600)
def ocultas() -> set:
    """Colunas que o gestor mandou sumir da tela de configuração.

    `remover` só apaga uma linha da planilha. A coluna que veio renomeada no
    Trello mas continua escrita no código — em COLUNAS_CONFIG — voltava na
    leitura seguinte, e o botão de remover não tinha efeito nenhum: ela não
    estava na planilha para ser apagada. Sem um lugar que diga "essa não me
    interessa mais", a única saída seria alterar o código.

    Vazio em qualquer falha: esconder coluna por engano é pior que mostrar uma
    coluna a mais.
    """
    try:
        registros = _aba_ocultas().get_all_records()
    except Exception:
        return set()
    return {str(r.get("coluna", "")).strip()
            for r in registros if str(r.get("coluna", "")).strip()}


def ocultar(nome_coluna):
    """Some com a coluna da tela. Devolve (ok, mensagem)."""
    nome = str(nome_coluna).strip()
    if not nome:
        return False, "Coluna sem nome."
    try:
        if nome not in ocultas():
            _aba_ocultas().append_row([nome], value_input_option="RAW")
            ocultas.clear()
        return True, ""
    except Exception as e:
        return False, str(e)[:200]


def revelar(nome_coluna):
    """Traz a coluna de volta. Devolve (ok, mensagem).

    Existe porque esconder é uma decisão e toda decisão erra: a coluna some da
    tela junto com a configuração dela, e sem o caminho de volta o conserto
    seria editar a planilha na mão.
    """
    try:
        aba = _aba_ocultas()
        try:
            celula = aba.find(str(nome_coluna).strip(), in_column=1)
        except Exception:
            celula = None
        if celula:
            aba.delete_rows(celula.row)
            ocultas.clear()
        return True, ""
    except Exception as e:
        return False, str(e)[:200]


def remover(nome_coluna):
    """Apaga a linha de uma coluna que não existe mais no Trello.

    Coluna renomeada no Trello deixa a configuração antiga órfã na planilha, e a
    tela de configuração mostra a união do que está no board com o que está aqui
    — então a órfã ficava para sempre, indistinguível de uma coluna real e sem
    nenhuma medição. Sem isto, a única saída era editar a planilha na mão.
    """
    aba = _aba()
    try:
        celula = aba.find(str(nome_coluna), in_column=1)
    except Exception:
        celula = None
    if celula:
        aba.delete_rows(celula.row)
    carregar.clear()
