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
        # SÓ A CÉLULA QUE FALTA. A primeira versão reescrevia `A1:I1` com
        # COLUNAS inteiro — e isso RENOMEIA as oito colunas que já existem.
        # Se um dia a aba tiver sido editada à mão, ou se a ordem de COLUNAS
        # mudar, o registro antigo passa a ser lido sob outro nome, em
        # silêncio. Escrever só o que falta não tem esse alcance.
        import gspread.utils as _gu
        faltando = COLUNAS[len(cab):]
        for i, nome in enumerate(faltando):
            celula = _gu.rowcol_to_a1(1, len(cab) + 1 + i)
            aba.update(celula, [[nome]], value_input_option="RAW")
    except Exception:
        pass


def ler(limite=200):
    """Últimos registros, mais recentes primeiro. Lista vazia se falhar."""
    try:
        linhas = _aba().get_all_records()
    except Exception:
        return []
    return list(reversed(linhas))[:limite]


# ── Conferência ──────────────────────────────────────────────────────────────
# `python3 log_imagem.py`. Só o cabeçalho — o resto é planilha.
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    class _AbaFalsa:
        def __init__(self, cab):
            self.cab, self.escritas = list(cab), []

        def row_values(self, n):
            return self.cab

        def update(self, faixa, vals, **kw):
            self.escritas.append((faixa, vals[0][0]))

    def _rodar(cab):
        globals()["_cabecalho_conferido"] = False
        a = _AbaFalsa(cab)
        _garantir_coluna_prompt(a)
        return a

    # A ABA ANTIGA TEM 8 COLUNAS; a nona precisa existir para o prompt ser
    # LIDO de volta. Registro que não se consegue ler não é registro.
    _a = _rodar(COLUNAS[:-1])
    ok("a coluna que falta e escrita", _a.escritas == [("I1", "prompt")])
    # E SÓ ELA. Reescrever A1:I1 renomearia as oito que já existem — se a aba
    # tiver sido editada à mão, o registro antigo passa a ser lido sob outro
    # nome, em silêncio.
    ok("e nenhuma das que ja existem e tocada",
       all(f != "A1" for f, _ in _a.escritas))
    ok("aba completa nao e tocada", _rodar(COLUNAS).escritas == [])
    ok("aba curta ganha todas as que faltam",
       len(_rodar(COLUNAS[:2]).escritas) == len(COLUNAS) - 2)

    # UMA VEZ POR PROCESSO: oito imagens nao podem virar oito leituras a mais
    # do Drive no meio da geracao.
    _a2 = _AbaFalsa(COLUNAS[:-1])
    globals()["_cabecalho_conferido"] = False
    _garantir_coluna_prompt(_a2)
    _garantir_coluna_prompt(_a2)
    _garantir_coluna_prompt(_a2)
    ok("tres chamadas, uma escrita so", len(_a2.escritas) == 1)

    ok("a coluna do prompt e a ultima", COLUNAS[-1] == "prompt")

    print("\nfalhas:", falhas)
