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
import threading as _threading_ctx
from datetime import datetime

import planilha as _plan
import placar_core as _pc_br   # a porta unica da hora de Brasilia
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
# ── E UM GLOBAL DE PROCESSO ERA UM DONO SÓ PARA A EQUIPE INTEIRA ─────
#
# A primeira versão disto era `_CONTEXTO = {"produto": "", "usuario": ""}`:
# um dicionário de módulo. O Streamlit serve TODOS os colaboradores no MESMO
# processo, e `marcar_contexto` roda a cada desenho de página — então,
# enquanto a geração da Myrella corria (quatro minutos numa thread), qualquer
# outra pessoa que abrisse a tela Imagem sobrescrevia produto e usuário, e as
# linhas seguintes do log saíam com o nome do produto e da pessoa ERRADOS.
#
# Isso não é o mesmo defeito de antes com outra cara: é PIOR. O campo vazio a
# gente vê ("nenhum prompt registrado"); o campo errado se lê como verdade. O
# histórico do «Compasso Cortador Colorido» de 30/09 veio com quatro peças de
# OUTRO produto dentro, todas carimbadas "Myrella", e a análise que saiu dele
# apontou um defeito que não existia.
#
# POR THREAD, E NÃO POR PROCESSO. Cada sessão do Streamlit roda o script na
# própria thread, então guardar por thread já separa os colaboradores sem
# nenhum trabalho a mais. Quem abre uma thread de trabalho HERDA o contexto
# de quem a criou, por `alvo_com_contexto` — capturado no momento da criação,
# que é o único instante em que as duas threads se conhecem.
_CONTEXTO = {}          # ident da thread -> {"produto": ..., "usuario": ...}
_TETO_CONTEXTO = 256    # threads de script são reusadas; isto é só sanidade


def _meu():
    """O contexto desta thread. Cria vazio na primeira vez."""
    ident = _threading_ctx.get_ident()
    ctx = _CONTEXTO.get(ident)
    if ctx is None:
        if len(_CONTEXTO) >= _TETO_CONTEXTO:
            # Poda só o que não tem mais dono: thread morta não volta.
            vivas = {t.ident for t in _threading_ctx.enumerate()}
            for k in [k for k in _CONTEXTO if k not in vivas]:
                _CONTEXTO.pop(k, None)
        ctx = {"produto": "", "usuario": "", "peca": ""}
        _CONTEXTO[ident] = ctx
    return ctx


def marcar_contexto(produto=None, usuario=None, peca=None):
    """Diz quem está gerando, o quê, e em qual peça. A tela chama; a thread lê.

    Vale só para a thread que chamou — e é isso que separa um colaborador do
    outro dentro do mesmo processo.

    A PEÇA ENTROU AQUI DEPOIS, E O MOTIVO IMPORTA
    ---------------------------------------------
    Ela vivia num global de módulo em `imagem.py` (`_PECA_EM_AJUSTE`), com o
    custo declarado em voz alta na própria docstring: *"o global é do processo,
    não da sessão. Dois colaboradores ajustando peças diferentes no mesmo
    segundo podem trocar o número entre si"*. Era o MESMO defeito que o
    produto e o usuário tinham, no mesmo registro, três campos lado a lado —
    e eu corrigi dois e deixei o terceiro.

    Declarar o custo é melhor que escondê-lo, mas não é conserto. Com o
    contexto já sendo por thread e já sendo herdado pela thread de trabalho, a
    peça passa a viajar pelo mesmo caminho: um mecanismo, três campos, e a
    família inteira de defeito fecha em vez de fechar dois terços dela.
    """
    ctx = _meu()
    if produto is not None:
        ctx["produto"] = str(produto or "")
    if usuario is not None:
        ctx["usuario"] = str(usuario or "")
    if peca is not None:
        ctx["peca"] = str(peca or "")


def contexto_atual():
    """Cópia do contexto desta thread. Para quem vai criar outra."""
    return dict(_meu())


def alvo_com_contexto(func):
    """Embrulha o alvo de uma Thread para ela HERDAR quem a criou.

    A captura acontece AQUI, na thread que cria — o único instante em que as
    duas se conhecem. Dentro da thread nova não há como descobrir a mãe: o
    Python não guarda esse laço.

    Sem isto, a thread de geração nasce com contexto vazio e volta a gravar
    produto em branco, que é o defeito que originou este módulo.
    """
    herdado = contexto_atual()

    def _dentro(*a, **kw):
        _CONTEXTO[_threading_ctx.get_ident()] = dict(herdado)
        try:
            return func(*a, **kw)
        finally:
            _CONTEXTO.pop(_threading_ctx.get_ident(), None)

    _dentro.__name__ = getattr(func, "__name__", "alvo")
    _dentro.__doc__ = getattr(func, "__doc__", None)
    return _dentro


def _do_contexto(chave, *chaves_sessao):
    """O valor do global, caindo no session_state quando ele está vazio.

    O GLOBAL MANDA. Ele é o único que funciona dentro da thread; o
    session_state fica como rede para quem ainda não chamou `marcar_contexto`
    (uma tela antiga, um caminho que roda na thread principal).
    """
    v = str(_meu().get(chave) or "")
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
                _pc_br.agora_br().strftime("%d/%m/%Y %H:%M:%S"),
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
        _t_lg = _th_lg.Thread(target=alvo_com_contexto(lambda: registrar(
            "prompt_geracao", imagem="4", tipo="4 — Close",
            resultado="enviado ao motor", prompt="x" * 30)))
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

        # ── DOIS COLABORADORES AO MESMO TEMPO, NO MESMO PROCESSO ────────
        #
        # ESTA E A GUARDA QUE FALTAVA, e a falta dela custou um dia inteiro
        # de analise em cima de dado falso.
        #
        # O contexto era um dicionario de modulo. O Streamlit serve todo
        # mundo no MESMO processo, e `marcar_contexto` roda a cada desenho
        # de pagina — entao a segunda pessoa a abrir a tela sobrescrevia a
        # primeira, e o log da primeira passava a gravar o produto e o
        # usuario da segunda. O historico do «Compasso Cortador Colorido»
        # de 30/09 veio com quatro pecas de OUTRO produto dentro, todas
        # carimbadas com o nome de quem nao as gerou.
        #
        # A guarda anterior NAO via isso: ela marcava um contexto so e
        # conferia que ele chegava. Com um dono so, global e por-thread dao
        # a mesma resposta. O defeito so aparece com DOIS.
        _linhas_falsas.clear()
        _porta = _th_lg.Barrier(2)

        def _colaborador(produto, usuario):
            def _corpo():
                marcar_contexto(produto=produto, usuario=usuario)
                _porta.wait()          # os dois marcam ANTES de qualquer um gravar
                registrar("prompt_geracao", tipo="1 — Capa", prompt="p")
            return _corpo

        _a = _th_lg.Thread(target=_colaborador("Compasso Cortador", "myrella"))
        _b = _th_lg.Thread(target=_colaborador("Caixa de Relogio", "beatriz"))
        _a.start(); _b.start(); _a.join(); _b.join()
        _por_usuario = {l.get("usuario"): l.get("produto") for l in _linhas_falsas}
        ok("duas pessoas gerando ao mesmo tempo: duas linhas",
           len(_linhas_falsas) == 2)
        ok("cada linha guarda o produto de QUEM a gerou",
           _por_usuario.get("myrella") == "Compasso Cortador"
           and _por_usuario.get("beatriz") == "Caixa de Relogio")

        # E A THREAD DE TRABALHO HERDA DE QUEM A CRIOU — com a mae ainda
        # viva e com OUTRA thread marcando outro produto no meio.
        _linhas_falsas.clear()

        def _intruso_corpo():
            # Marca OUTRO produto e grava — no meio do caminho da mae.
            marcar_contexto(produto="Outro Produto", usuario="luiz")
            registrar("prompt_geracao", tipo="1 — Capa", prompt="p")

        def _mae():
            marcar_contexto(produto="Album Wire-O", usuario="gabriel")
            # O EMBRULHO E FEITO AQUI, na mae: e este o instante em que o
            # contexto e capturado. Criar a filha DEPOIS do intruso e de
            # proposito — com global de processo, ela herdaria "Outro
            # Produto", que e exatamente o defeito.
            _filha = _th_lg.Thread(
                target=alvo_com_contexto(lambda: registrar("prompt_geracao")))
            _intruso = _th_lg.Thread(target=_intruso_corpo)
            _intruso.start(); _intruso.join()
            _filha.start(); _filha.join()

        _m = _th_lg.Thread(target=_mae); _m.start(); _m.join()
        _da_filha = [l for l in _linhas_falsas if l.get("usuario") == "gabriel"]
        ok("a thread de trabalho herda o contexto de quem a criou",
           len(_da_filha) == 1 and _da_filha[0].get("produto") == "Album Wire-O")

        # ── `contexto_atual` E LIDO DE FORA, E POR ISSO TEM GUARDA ──────
        #
        # `imagem.peca_em_ajuste()` le a peca por ele. Se o formato mudar —
        # um campo a menos, outro nome — a leitura de la volta vazia em
        # silencio, e a linha do registro perde a chave da cadeia. O quarto
        # verificador cobrou esta guarda pelo nome.
        marcar_contexto(produto="Caneca", usuario="myrella", peca="4")
        _ctx = contexto_atual()
        ok("contexto_atual devolve os TRES campos, com os nomes de sempre",
           set(_ctx) == {"produto", "usuario", "peca"})
        ok("e com os valores de quem chamou",
           (_ctx["produto"], _ctx["usuario"], _ctx["peca"])
           == ("Caneca", "myrella", "4"))
        ok("e e uma COPIA: mexer nela nao mexe no contexto da thread",
           (_ctx.update({"peca": "9"}) or contexto_atual()["peca"]) == "4")
        marcar_contexto(produto="", usuario="", peca="")

        # ── E O DICIONARIO NAO CRESCE PARA SEMPRE ───────────────────────
        #
        # A thread de trabalho limpa a propria entrada ao terminar (o
        # `finally` de `alvo_com_contexto`). A thread de SCRIPT nao: ela
        # chama `marcar_contexto` direto, e quem a criou foi o Streamlit.
        # Entao o que segura o tamanho e a poda por ident morto.
        #
        # A PRIMEIRA VERSAO DESTA GUARDA EXIGIA VAZAMENTO ZERO e reprovou —
        # ela media uma propriedade que o desenho nao tem nem promete. Guarda
        # que cobra o que o codigo nao faz e alarme falso, e alarme falso
        # ensina a ignorar o verificador. O que importa e o TETO.
        _teto_real = _TETO_CONTEXTO
        globals()["_TETO_CONTEXTO"] = 8
        try:
            for _i in range(40):
                _t = _th_lg.Thread(
                    target=lambda: marcar_contexto(produto="x", usuario="y"))
                _t.start(); _t.join()
            ok("o contexto nao cresce sem limite: threads mortas sao podadas",
               len(_CONTEXTO) <= 8 + 1)
        finally:
            globals()["_TETO_CONTEXTO"] = _teto_real
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
