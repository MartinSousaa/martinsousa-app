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


# QUEM ESTÁ GERANDO, E O QUE. Globais de módulo, e não `st.session_state`.
#
# A geração inteira roda em `threading.Thread` (`imagem.py:7162`), e de dentro
# de uma thread o `session_state` volta VAZIO — sem erro, sem aviso. Este
# registro lia produto e usuário de lá, então TODA linha do log gravou produto
# em branco: o filtro por nome nunca batia, e o histórico de prompts voltava
# sempre vazio dizendo "nenhum prompt registrado".
#
# O número da peça já tinha sido movido para um global (`_PECA_EM_AJUSTE`, em
# `imagem.py`) exatamente por isso. Estes dois campos ficaram para trás, no
# mesmo `append_row`, duas linhas ao lado.
_CONTEXTO = {"produto": "", "usuario": ""}


def marcar_contexto(produto=None, usuario=None):
    """Diz quem está gerando e o que. A tela chama; a thread lê."""
    if produto is not None:
        _CONTEXTO["produto"] = str(produto or "")
    if usuario is not None:
        _CONTEXTO["usuario"] = str(usuario or "")


def _do_contexto(chave, *chaves_sessao):
    """O valor do global, caindo no session_state quando ele está vazio.

    O GLOBAL MANDA. Ele é o único que funciona dentro da thread; o
    session_state fica como rede para quem ainda não chamou `marcar_contexto`
    (uma tela antiga, um caminho que roda na thread principal).
    """
    v = str(_CONTEXTO.get(chave) or "")
    if v:
        return v
    for k in chaves_sessao:
        try:
            v = str(st.session_state.get(k, "") or "")
        except Exception:
            v = ""
        if v:
            return v
    return ""


def registrar(acao, instrucao="", imagem=None, tipo="", resultado="",
              prompt=""):
    """Grava uma linha de registro. Nunca levanta exceção."""
    try:
        _ab = _aba()
        _garantir_coluna_prompt(_ab)
        _ab.append_row(
            [
                datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                _do_contexto("usuario", "usuario") or "?",
                _do_contexto("produto", "img_nome_produto", "nome_produto"),
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

    # ── O REGISTRO VISTO DE DENTRO DE UMA THREAD ────────────────────────
    #
    # ESTA GUARDA FALTAVA, e o buraco custou o historico de prompts inteiro.
    #
    # Eu ja sabia que `st.session_state` e ilegivel dentro de
    # `threading.Thread` — apliquei ao numero da peca e escrevi ate uma
    # guarda com Thread de verdade para provar. Mas a guarda exercitava
    # `peca_em_ajuste()` SOZINHA, a funcao que eu tinha acabado de escrever.
    # `produto` e `usuario`, no mesmo append_row duas linhas ao lado,
    # continuaram lendo do session_state.
    #
    # A diferenca esta aqui: esta guarda chama `registrar` INTEIRA de dentro
    # de uma thread e olha O QUE FOI ESCRITO na linha. Guarda que so confere
    # "nao explodiu" nao ve campo vazio — e `registrar` engole a propria
    # excecao de proposito, entao ele nunca explode.
    import threading as _th_lg

    _linhas_falsas = []

    class _AbaFalsaLog:
        def row_values(self, _n):
            return list(COLUNAS)

        def append_row(self, linha, **kw):
            _linhas_falsas.append(dict(zip(COLUNAS, linha)))

    _aba_real, _cab_real = _aba, _cabecalho_conferido
    _aba = lambda: _AbaFalsaLog()          # noqa: E731 — duplo do I/O
    _cabecalho_conferido = True
    try:
        marcar_contexto(produto="Caneca Medieval", usuario="myrelladesouza")
        _t_lg = _th_lg.Thread(target=lambda: registrar(
            "prompt_geracao", imagem="4", tipo="4 — Close",
            resultado="enviado ao motor", prompt="x" * 30))
        _t_lg.start(); _t_lg.join()
        _l = _linhas_falsas[-1] if _linhas_falsas else {}
        ok("a linha e gravada de dentro da thread", bool(_l))
        # OS TRES CAMPOS, e nao so o que eu estava pensando na hora.
        ok("o PRODUTO chega na linha gravada de dentro da thread",
           _l.get("produto") == "Caneca Medieval")
        ok("o USUARIO tambem", _l.get("usuario") == "myrelladesouza")
        ok("e o prompt", len(str(_l.get("prompt") or "")) == 30)
        # SEM CONTEXTO MARCADO o campo sai vazio — e isso e esperado, nao
        # um segundo defeito: e o caso de quem ainda nao chamou.
        marcar_contexto(produto="", usuario="")
        _linhas_falsas.clear()
        _t2 = _th_lg.Thread(target=lambda: registrar("teste"))
        _t2.start(); _t2.join()
        ok("sem contexto marcado, o produto sai vazio e nao inventado",
           _linhas_falsas and _linhas_falsas[-1].get("produto") == "")
    finally:
        _aba, _cabecalho_conferido = _aba_real, _cab_real
        marcar_contexto(produto="", usuario="")

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
