"""checar_tela.py — o quinto verificador: ele DESENHA a tela.

POR QUE ELE EXISTE
------------------
Em 25/09 a Home caiu em produção com `TypeError: string indices must be
integers`, e os quatro verificadores passaram. Passaram porque nenhum deles
desenha nada: `compileall` lê sintaxe, `checar_ordem` lê ordem de nomes,
`checar_prompts` monta o prompt da imagem, `checar_impacto` lê quem lê o quê.

O defeito era de MONTAGEM: `_lpv_card` devolvia o cartão já renderizado (uma
string) numa lista em que todo o resto era dicionário, e `pagina` fazia
`_card(c)` em cada item. O auto-teste conferia o HTML de `_lpv_card` isolado
— exatamente o único lugar onde o tipo errado parecia certo.

No mesmo dia, a tela de Extratos caiu com `StreamlitDuplicateElementKey:
ext_fin_0`: dois arquivos, e a chave do widget recomeçava do zero em cada um.
Também não havia como pegar sem desenhar.

O QUE ELE FAZ
-------------
Troca o Streamlit por um DUPLO antes de importar qualquer coisa, injeta dados
de mentira no lugar das planilhas, e manda a página se desenhar inteira. O
duplo:

  · guarda toda chave de widget e EXPLODE na repetida — é o defeito do
    `ext_fin_0`, que só aparece quando a mesma tela desenha duas vezes;
  · deixa qualquer exceção subir — é o defeito do cartão em HTML.

O QUE ELE NÃO FAZ
-----------------
Não confere se a tela ficou BONITA, nem se o número está certo: isso é o olho
do dono e são os outros verificadores. Ele responde uma pergunta só, a que
faltava: **a tela monta sem quebrar?**
"""

import os
import sys
import types


class ChaveRepetida(Exception):
    """O mesmo `key=` duas vezes — é o erro que o Streamlit dá em produção."""


class EscritaDepoisDoWidget(Exception):
    """Escrever `session_state[k]` depois de o widget `key=k` existir.

    O Streamlit recusa isto em produção com
    `StreamlitAPIException: st.session_state.<k> cannot be modified after the
    widget with key <k> is instantiated`.

    O DUPLO NÃO SABIA DISSO, E FOI O QUE DEIXOU O DEFEITO PASSAR.

    05/10, no teste do dono: duas das oito peças falharam por timeout, ele
    pediu no chat para gerar as faltantes, e o comando morreu aqui.
    `preparar_geracao_dos_faltantes` escreve `img_modo`
    (chat_assistente.py:670), que é a chave do rádio de `imagem.py:9211`; o
    chat é desenhado em `app.py:2092`, DEPOIS da página. Quando o comando
    roda, o widget já existe.

    A guarda que deveria ter pego (chat_assistente.py, autoteste) mediu a
    função com este `session_state` — um dicionário puro, onde a regra não
    existe. Duplo mais pobre que a realidade **absolve o culpado**, que é
    pior que acusar o inocente: a Forma 7 do CLAUDE.md.
    """


class _Falso:
    """Um Streamlit de mentira. Tudo devolve algo; nada vai para a rede."""

    def __init__(self, chaves=None):
        # As chaves são compartilhadas entre o módulo e as colunas/containers:
        # o Streamlit de verdade também as vê como um espaço só.
        self._chaves = {} if chaves is None else chaves
        self.session_state = _Estado(self._chaves)
        # OS SEGREDOS EXISTEM, com valor de mentira.
        #
        # `sheets.py:74` lê `st.secrets["gcp_service_account"]` com COLCHETE:
        # ausente, ele levanta KeyError cru. Um duplo com `secrets` vazio
        # fazia a tela de Ponto "quebrar" aqui — mas em produção a chave
        # existe, e o defeito era do duplo, não do código. Duplo mais pobre
        # que a realidade acusa o inocente.
        #
        # NENHUM VALOR REAL, e nenhum vai à rede: quem fala com o Google é
        # substituído logo abaixo, no lugar certo (a fronteira de I/O).
        # `st.query_params` É DICT no Streamlit de verdade, e no duplo caía
        # no `__getattr__` virando função — `gestao.py:94` fazia `.get()` nela
        # e recebia AttributeError. Duplo mais pobre que a realidade acusa o
        # inocente: a tela estava certa.
        self.query_params = {}
        self.secrets = {
            "gcp_service_account": {"type": "service_account",
                                    "project_id": "conferencia",
                                    "private_key": "-----BEGIN-----\nx\n-----END-----\n",
                                    "client_email": "x@conferencia.local"},
            "TRELLO_KEY": "", "TRELLO_TOKEN": "", "BOARD_ID": "",
            "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "GEMINI_API_KEY": "",
        }
        self.column_config = _Qualquer()
        self.errors = types.SimpleNamespace(
            StreamlitDuplicateElementKey=ChaveRepetida)

    # COLUNA E CONTAINER SAO CONTEXTO NO STREAMLIT DE VERDADE: `with c1:` é
    # uso corrente. Sem estes dois métodos o duplo acusava o inocente —
    # "'_Falso' object does not support the context manager protocol" — numa
    # tela que funciona. É a mesma lição do `linha_do_mes`: dublê mais pobre
    # que a realidade dá alarme falso, e alarme falso ensina a ignorar.
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    # ── widgets: o que tem `key` entra no registro ───────────────────────
    def _registra(self, nome, kw):
        k = kw.get("key")
        if k is None:
            return
        if k in self._chaves:
            raise ChaveRepetida(
                f"key={k!r} usada duas vezes (em {self._chaves[k]} e agora "
                f"em {nome}) — é o erro que derruba a tela em produção")
        self._chaves[k] = nome

    def __getattr__(self, nome):
        def _qualquer(*a, **kw):
            self._registra(nome, kw)
            return _retorno_de(nome, a, kw)
        return _qualquer

    # ── os que precisam devolver coisa específica ────────────────────────
    def columns(self, spec, **kw):
        n = spec if isinstance(spec, int) else len(spec)
        return [_Falso(self._chaves) for _ in range(n)]

    def tabs(self, rotulos, **kw):
        return [_Falso(self._chaves) for _ in rotulos]

    def container(self, *a, **kw):
        return _Contexto(_Falso(self._chaves))

    def expander(self, *a, **kw):
        return _Contexto(_Falso(self._chaves))

    def spinner(self, *a, **kw):
        return _Contexto(None)

    def form(self, *a, **kw):
        return _Contexto(_Falso(self._chaves))

    def sidebar(self):
        return _Falso(self._chaves)

    def cache_data(self, *a, **kw):
        """Serve como `@st.cache_data` e como `@st.cache_data(ttl=…)`."""
        if a and callable(a[0]):
            return _sem_cache(a[0])
        return _sem_cache

    cache_resource = cache_data

    def rerun(self, *a, **kw):
        raise _Rerun()

    def stop(self, *a, **kw):
        raise _Parou()


def _sem_cache(fn):
    fn.clear = lambda *a, **k: None
    return fn


class _Rerun(Exception):
    """`st.rerun()` — não é defeito: a tela pediu para recomeçar."""


class _Parou(Exception):
    """`st.stop()` — idem."""


class _Contexto:
    def __init__(self, valor):
        self.valor = valor

    def __enter__(self):
        return self.valor

    def __exit__(self, *a):
        return False


class _Estado(dict):
    """`st.session_state`: dicionário que também responde por atributo.

    E QUE RECUSA O QUE O STREAMLIT RECUSA: escrever numa chave cujo widget já
    foi desenhado nesta passada. Ver `EscritaDepoisDoWidget`.
    """

    def __init__(self, chaves=None):
        super().__init__()
        # O MESMO registro de `_Falso._chaves`, por referência: é ele que diz
        # quais widgets já nasceram nesta passada.
        object.__setattr__(self, "_chaves_widget", chaves)

    def __getattr__(self, k):
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v

    def __setitem__(self, k, v):
        _reg = object.__getattribute__(self, "__dict__").get("_chaves_widget")
        if _reg and k in _reg and dict.get(self, k, _AUSENTE) != v:
            raise EscritaDepoisDoWidget(
                f"st.session_state[{k!r}] foi escrito DEPOIS de o widget com "
                f"key={k!r} ser desenhado (em {_reg[k]}). O Streamlit levanta "
                f"StreamlitAPIException aqui, e o comando morre antes de "
                f"fazer o que prometeu.")
        dict.__setitem__(self, k, v)

    def get(self, k, padrao=None):
        return dict.get(self, k, padrao)


# Sentinela: `None` é valor legítimo no session_state, então "ausente" precisa
# de um objeto próprio — senão reescrever None por None passaria por mudança.
_AUSENTE = object()


class _Qualquer:
    def __getattr__(self, _):
        return lambda *a, **kw: None


def _retorno_de(nome, a, kw):
    """O que cada widget devolve quando ninguém clicou em nada."""
    if nome in ("button", "checkbox", "toggle", "form_submit_button",
                "download_button", "chat_input"):
        return False
    if nome in ("selectbox", "radio"):
        opcoes = kw.get("options") or (a[1] if len(a) > 1 else [])
        return list(opcoes)[0] if list(opcoes or []) else None
    if nome in ("multiselect", "file_uploader"):
        return [] if kw.get("accept_multiple_files") else None
    if nome in ("text_input", "text_area"):
        return ""
    # DATA E HORA DEVOLVEM DATA E HORA. O duplo devolvia um `_Falso`, e
    # `datetime.combine` com ele levanta TypeError — numa tela que funciona.
    # Mesma licao do `linha_do_mes` e do `with c1:`: duble mais pobre que a
    # realidade acusa o inocente.
    if nome in ("date_input", "time_input"):
        import datetime as _dt_falso
        v = kw.get("value")
        if v is None and len(a) > 1:
            v = a[1]
        if v is not None:
            return v
        return (_dt_falso.date.today() if nome == "date_input"
                else _dt_falso.time(0, 0))
    if nome in ("number_input", "slider"):
        v = kw.get("value")
        return v if v is not None else (a[3] if len(a) > 3 else 0)
    if nome == "data_editor":
        return a[0] if a else None
    return _Falso()


def instalar():
    """Põe o duplo no lugar do Streamlit. Antes de qualquer import de tela."""
    falso = _Falso()
    sys.modules["streamlit"] = falso
    return falso


# ── Os cenários ──────────────────────────────────────────────────────────────
# Dados de mentira no lugar das planilhas: o que se confere aqui é a MONTAGEM
# da tela, não o número. Número é dos outros verificadores e do olho do dono.

_IND = {
    "faturamento": 250_000.0, "faturamento_liquido": 244_000.0,
    "devolucao": 6_000.0, "vendas": 2_302.0, "unidades": 3_000.0,
    "lucro_bruto": 181_000.0, "margem_bruta": 74.5,
    "margem_contribuicao": 49_300.0, "margem_contribuicao_pct": 20.2,
    "lucro_por_venda": 82.24, "uc": 1.3, "custo_total": 0.0, "custo_op": 0.0,
    "periodo": "jun-ago/2026", "meses": 3, "linhas": 6906,
    "somas": {"faturamento": 250_000.0},
}
_RESUMO = {"MERCADORIA": -41_773.23, "CUSTO FIXO": -22_842.00,
           "SERVIÇO": -897.04, "EMBALAGEM": -2_271.69,
           "NÃO OPERACIONAL": -15_512.93, "XPTO NOVA": -1_234.00}


def _home(falhas, conta):
    """A Home inteira, com e sem cada fonte — é onde o TypeError nasceu."""
    import home_gestao as hg
    import base_vendas as _bv
    import financeiro as _fin
    import meta_gastos as _mg

    import lancamentos as _lan
    import previsto as _pv

    # SUBSTITUI-SE A LEITURA, NUNCA A CONTA.
    #
    # A primeira versão deste verificador trocava `meta_gastos.linha_do_mes`
    # por `{"meta": 170000}` — e a tela quebrou com KeyError: 'realizado'.
    # Não era defeito da tela: era o dublê mais pobre que a realidade,
    # acusando o inocente. Um verificador que dá alarme falso é pior que
    # nenhum, porque ensina a ignorá-lo.
    #
    # Então só o que vai à planilha ou à rede é trocado. Toda função que
    # CALCULA continua rodando de verdade, e é isso que dá valor ao alarme.
    _bv.media_recente = lambda *a, **k: (dict(_IND), "")
    _fin.carregar_dados = lambda *a, **k: None
    _fin.lpv_vigente = lambda *a, **k: (19.68, "Junho/2026")
    _fin.meses_de_atraso_lpv = lambda *a, **k: 3
    _mg.carregar = lambda *a, **k: {
        _mg.texto_mes(2026, 9): {"meta": 170_000.0, "informado": 0.0}}
    _mg.realizado_dos_lancamentos = lambda *a, **k: 96_000.0
    _lan.do_mes = lambda *a, **k: [
        {"data": "2026-09-02", "descricao": "Pix", "favorecido": "APEXIMP",
         "valor": -1_791.62, "finalidade": "MERCADORIA", "conta": "itau-1"},
        {"data": "2026-09-03", "descricao": "Convenio", "favorecido": "VIVO",
         "valor": -106.43, "finalidade": "CUSTO FIXO", "conta": "itau-1"}]
    _pv.do_mes = lambda *a, **k: ({}, [])
    hg._faturamento_bling = lambda *a, **k: (190_502.0, [])
    hg._partes_fixas = lambda *a, **k: (22_842.0, 2_350.35, 22_000.0, 9_900.0, [])
    hg._gastos_por_finalidade = lambda *a, **k: (dict(_RESUMO), "")

    casos = [
        ("Home completa", {}),
        # SEM LPV: o cartão tem de aparecer mandando preencher, e não sumir.
        ("Home sem LPV no Financeiro",
         {"lpv": lambda *a, **k: (None, "nenhum LPV informado ainda")}),
        # SEM CUSTO FIXO: a régua fica sem as linhas de equilíbrio.
        ("Home sem custo fixo cadastrado",
         {"fixas": lambda *a, **k: (0.0, 0.0, 0.0, 0.0, [])}),
        # SEM BLING: o faturamento cai para a planilha.
        ("Home sem Bling", {"bling": lambda *a, **k: (None, ["fora do ar"])}),
        # SEM PLANILHA: a tela entrega o que tem, e não uma caixa vermelha.
        ("Home sem BASE DE VENDAS",
         {"bv": lambda *a, **k: (None, "Drive não respondeu")}),
    ]
    for nome, troca in casos:
        _guardado = (_bv.media_recente, _fin.lpv_vigente,
                     hg._faturamento_bling, hg._partes_fixas)
        if "bv" in troca:
            _bv.media_recente = troca["bv"]
        if "lpv" in troca:
            _fin.lpv_vigente = troca["lpv"]
        if "bling" in troca:
            hg._faturamento_bling = troca["bling"]
        if "fixas" in troca:
            hg._partes_fixas = troca["fixas"]
        try:
            _falso = instalar()
            hg.st = _falso
            d, _av = hg.dados_reais(2026, 9, 25)
            hg.pagina(usuario_logado="leo", dados=d)
            conta(nome, True, "")
        except (_Rerun, _Parou):
            conta(nome, True, "")
        except Exception as e:
            conta(nome, False, f"{type(e).__name__}: {e}")
        finally:
            (_bv.media_recente, _fin.lpv_vigente,
             hg._faturamento_bling, hg._partes_fixas) = _guardado
    return falhas


def _extratos(conta):
    """A fila de nomes novos — é onde o `ext_fin_0` nasceu."""
    import extratos_tela as et
    import favorecidos as _fv

    _fv.carregar = lambda *a, **k: {}
    f1 = [{"favorecido": "APEXIMP", "sentido": "saida", "conta": "itau-1",
           "n": 2, "total": 300.0, "exemplo": "Pix", "datas": ["2026-09-02"]}]
    f2 = [{"favorecido": "IOF", "sentido": "saida", "conta": "itau-2",
           "n": 1, "total": 10.61, "exemplo": "IOF", "datas": ["2026-09-02"]}]

    _falso = instalar()
    et.st = _falso
    try:
        et._perguntar(et.juntar_filas(f1 + f2), _fv, "leo")
        conta("Extratos: dois arquivos, uma fila", True, "")
    except Exception as e:
        conta("Extratos: dois arquivos, uma fila", False,
              f"{type(e).__name__}: {e}")

    # E O DUPLO PEGA MESMO? Perguntar duas vezes, como era antes, tem de
    # explodir — senão este verificador estaria passando por não ver nada.
    _falso = instalar()
    et.st = _falso
    try:
        et._perguntar(f1, _fv, "leo")
        et._perguntar(f1, _fv, "leo")
        conta("o duplo acusa chave repetida", False,
              "perguntou duas vezes e ninguém reclamou")
    except ChaveRepetida:
        conta("o duplo acusa chave repetida", True, "")
    except Exception as e:
        conta("o duplo acusa chave repetida", False,
              f"explodiu por outro motivo: {type(e).__name__}: {e}")


def _gargalos(conta):
    """O bloco que compara o prompt da geração com o da correção."""
    import gargalos_tela as gt

    _log = [
        {"quando": "25/09/2026 10:00:00", "produto": "Caneca", "usuario": "leo",
         "acao": "prompt_geracao", "imagem": "", "tipo": "1", "instrucao": "",
         "resultado": "enviado ao motor",
         "prompt": "O produto ocupa 85-92% do quadro.\n"
                   "Nenhuma parte do produto cortada pela borda."},
        {"quando": "25/09/2026 10:10:00", "produto": "Caneca", "usuario": "leo",
         "acao": "prompt_ajuste", "imagem": "3", "tipo": "1", "instrucao": "",
         "resultado": "enviado ao motor",
         "prompt": "MODO AJUSTE FINO\n"
                   "Nenhuma parte do produto cortada pela borda.\n"
                   "A alca da caneca fica virada para a direita."},
    ]
    for nome, linhas in (("Gargalos: com par de prompts", _log),
                         ("Gargalos: sem par nenhum", []),
                         ("Gargalos: correção órfã", _log[1:])):
        _falso = instalar()
        gt.st = _falso
        try:
            gt._prompts_lado_a_lado(linhas)
            conta(nome, True, "")
        except (_Rerun, _Parou):
            conta(nome, True, "")
        except Exception as e:
            conta(nome, False, f"{type(e).__name__}: {e}")


def _historico(conta):
    """A aba Histórico, que passou a mostrar o que foi gerado."""
    import pandas as pd
    import atividades as at

    _linhas = [
        {"data_hora": "25/09/2026 10:00", "usuario": "myrella",
         "tipo": "Descrição", "produto": "Caneca", "resumo": "1847 caracteres",
         "codigo": "MS-CAN-1", "cor": "Preto", "medidas": "10x8", "peso": "400g",
         "link_capa": "", "link_pasta": "", "material": "aço",
         "caracteristicas": "", "diferenciais": "", "uso": "", "categoria": "",
         "conteudo": "Esta caneca de 400ml em aço inox mantém a bebida…"},
        {"data_hora": "25/09/2026 09:00", "usuario": "myrella",
         "tipo": "Título", "produto": "Caneca", "resumo": "10 títulos",
         "codigo": "MS-CAN-1", "cor": "", "medidas": "", "peso": "",
         "link_capa": "", "link_pasta": "", "material": "",
         "caracteristicas": "", "diferenciais": "", "uso": "", "categoria": "",
         "conteudo": "Caneca Térmica 400ml\nCaneca Medieval Inox"},
        # A LINHA ANTIGA, de antes da coluna existir: não pode quebrar a tela.
        {"data_hora": "01/08/2026 08:00", "usuario": "leo",
         "tipo": "Triagem de Produto", "produto": "Álbum", "resumo": "Papelaria",
         "codigo": "", "cor": "", "medidas": "", "peso": "", "link_capa": "",
         "link_pasta": "", "material": "", "caracteristicas": "",
         "diferenciais": "", "uso": "", "categoria": ""},
    ]
    for nome, dados in (
            ("Histórico com conteúdo gerado", pd.DataFrame(_linhas)),
            ("Histórico sem a coluna conteudo (aba antiga)",
             pd.DataFrame(_linhas).drop(columns=["conteudo"])),
            ("Histórico vazio", pd.DataFrame())):
        _falso = instalar()
        at.st = _falso
        at.carregar_atividades = lambda d=dados: d
        try:
            at.pagina_historico()
            conta(nome, True, "")
        except (_Rerun, _Parou):
            conta(nome, True, "")
        except Exception as e:
            conta(nome, False, f"{type(e).__name__}: {e}")

    # ── O TEXTO ABERTO, E NÃO SÓ O BOTÃO ────────────────────────────────
    #
    # O duplo devolve False em todo botão, então sem isto o `st.code` do
    # conteúdo nunca era desenhado — e a guarda estaria conferindo a tela
    # com a parte nova desligada.
    _falso = instalar()
    at.st = _falso
    at.carregar_atividades = lambda: pd.DataFrame(_linhas)
    _falso.session_state["_hist_cont_Caneca__MS-CAN-1_0"] = True
    _falso.session_state["_hist_ver_prompts_Caneca__MS-CAN-1"] = True
    try:
        at.pagina_historico()
        conta("Histórico com o texto gerado ABERTO", True, "")
    except (_Rerun, _Parou):
        conta("Histórico com o texto gerado ABERTO", True, "")
    except Exception as e:
        conta("Histórico com o texto gerado ABERTO", False,
              f"{type(e).__name__}: {e}")


def _faturas(conta):
    """A tela de Extratos recebendo fatura de cartão — o caminho novo."""
    import extratos_tela as et

    class _Arq:
        def __init__(self, nome, dados):
            self.name, self._d = nome, dados

        def getvalue(self):
            return self._d

    _casos = [
        ("Fatura em PDF ilegível",
         _Arq("Fatura final 3312.pdf", b"isso nao e um pdf de verdade")),
        ("Fatura do Inter em CSV",
         _Arq("Fatura Inter.csv",
              ('"Cartao Principal","x"\n'
               '"16/09","1924","ZUL 1 cartao","TRANSPORTE",'
               '"Compra a vista","-R$ 6,95"').encode())),
    ]
    for nome, arq in _casos:
        _falso = instalar()
        et.st = _falso
        try:
            et._fatura(arq, "fatura_pdf" if arq.name.endswith(".pdf")
                       else "fatura_inter", "leo")
            conta(nome, True, "")
        except (_Rerun, _Parou):
            conta(nome, True, "")
        except Exception as e:
            conta(nome, False, f"{type(e).__name__}: {e}")


def _queda_de_pontos(conta):
    """O bloco que explica a queda de pontuação — ele lê o log do Trello."""
    import placar as _pl
    import placar_core as _pc
    from datetime import datetime as _dt, timezone as _tz

    _acoes = {"c1": [{"type": "updateCard", "date": "2026-09-26T14:00:00.000Z",
                      "data": {"card": {"id": "c1", "name": "Vídeo caneca",
                                        "closed": True},
                               "old": {"closed": False}}}],
              "c2": [{"type": "createCard", "date": "2026-09-26T09:00:00.000Z",
                      "data": {"card": {"id": "c2", "name": "Atraso"},
                               "list": {"name": "PENALIDADES"}}}]}
    _agora = _dt(2026, 9, 28, 12, 0, tzinfo=_tz.utc)

    casos = [
        ("Queda de pontos: com mudanças no período",
         lambda *a, **k: dict(_acoes),
         lambda: ([], [{"id": "c2"}], {}, "idp", "idt", "idi")),
        # NENHUMA MUDANÇA: a tela tem de dizer o que conta como mudança, e
        # não ficar em branco.
        ("Queda de pontos: período sem mudança nenhuma",
         lambda *a, **k: {},
         lambda: ([], [], {}, "idp", "idt", "idi")),
        # O TRELLO FORA DO AR não pode derrubar o Painel de Metas inteiro.
        ("Queda de pontos: Trello fora do ar",
         lambda *a, **k: (_ for _ in ()).throw(RuntimeError("timeout")),
         lambda: ([], [], {}, "idp", "idt", "idi")),
    ]
    # O PAINEL INTEIRO TAMBEM E DESENHADO — o bloco novo entrou dentro dele,
    # e trocar codigo inline por uma chamada e exatamente o tipo de mexida
    # que quebra o arquivo inteiro sem que o bloco isolado acuse nada.
    _falso = instalar()
    _pl.st = _falso
    _guardado = _pc.TRELLO_KEY
    _pc.TRELLO_KEY = ""          # sem credencial: caminho de saida antecipada
    _pl.TRELLO_KEY = ""
    try:
        _pl.pagina_placar("leo")
        conta("Painel de Metas monta sem credencial do Trello", True, "")
    except (_Rerun, _Parou):
        conta("Painel de Metas monta sem credencial do Trello", True, "")
    except Exception as e:
        conta("Painel de Metas monta sem credencial do Trello", False,
              f"{type(e).__name__}: {e}")
    finally:
        _pc.TRELLO_KEY = _guardado
        _pl.TRELLO_KEY = _guardado

    for nome, _acoes_fn, _board_fn in casos:
        _falso = instalar()
        _pl.st = _falso
        _pc._buscar_acoes_board = _acoes_fn
        _pc._buscar_board = _board_fn
        _pc._num = lambda c, i: 50
        _falso.session_state["qp_rodar"] = True
        try:
            _pl.bloco_queda_de_pontos(_agora)
            conta(nome, True, "")
        except (_Rerun, _Parou):
            conta(nome, True, "")
        except Exception as e:
            conta(nome, False, f"{type(e).__name__}: {e}")


def _conferencia_de_pontos(conta):
    """A conferencia contra o Trello cru DESENHA, e diz o que ficou de fora.

    Dono, 29/09: "o pessoal continua reclamando que a pontuacao deles no painel
    continua caindo, evidenciando inclusive com imagens".

    O bloco novo e o unico lugar onde a queda vira numero conferivel — entao
    ele nao pode so "nao explodir": tem de MOSTRAR a diferenca, o motivo de
    cada cartao que ficou de fora, e o aviso de janela truncada. Guarda que so
    confere montagem nao ve campo vazio (Forma 1 do protocolo).

    O ESTADO AQUI E O QUE O BOARD PRODUZ QUANDO A JANELA E TRUNCADA: cartoes
    concluidos, com pontuacao, e NENHUMA data de conclusao lida. Nao inventei
    o cenario — e o que `acoes_movimento` devolve quando o teto de 5.000 acoes
    e atingido antes de alcancar a conclusao do cartao.
    """
    import importlib
    import sys as _sys_cp

    _falso = instalar()
    _pl = importlib.import_module("placar")
    _pc = importlib.import_module("placar_core")
    for _nm, _mod in list(_sys_cp.modules.items()):
        if getattr(_mod, "st", None) is not None and not _nm.startswith(
                ("streamlit", "checar_")):
            try:
                _mod.st = _falso
            except Exception:
                pass

    _guardado = (_pc.acoes_movimento, _pc.tempos_do_board,
                 dict(_pc.DIAGNOSTICO_POR_FILTRO))
    _pc.acoes_movimento = lambda *a, **k: {}
    _pc.tempos_do_board = lambda *a, **k: {}
    _pc.DIAGNOSTICO_POR_FILTRO[_pc.FILTRO_MOVIMENTO] = {"truncado": True}
    _pc.MEMBROS_ATIVOS.clear()
    _pc.MEMBROS_ATIVOS.update({"ana": "Ana", "bruno": "Bruno"})
    _pl.MEMBROS_ATIVOS = _pc.MEMBROS_ATIVOS

    _listas = {"l1": "CONCLUÍDO"}
    _membros = {"m1": "ana", "m2": "bruno"}

    def _card(i, membros, pts):
        return {"id": f"x{i}", "name": f"Peça {i}", "idList": "l1",
                "idMembers": membros, "labels": [], "idLabels": [],
                "dueComplete": True,
                "dateLastActivity": "2026-09-25T10:00:00.000Z",
                "customFieldItems": [{"idCustomField": "idp",
                                      "value": {"number": str(pts)}}]}

    _cards = [_card(1, ["m1"], 120), _card(2, ["m2"], 80), _card(3, [], 40)]
    # O sistema nao contou NADA: e o estado da janela truncada.
    _d = {"pts_equipe": 0.0, "pts_membro": {"ana": 0.0, "bruno": 0.0},
          "cards_pts": []}

    _erros = []
    try:
        _pl.bloco_conferencia_de_pontos(_listas, _cards, _membros, "idp", _d,
                                        (2026, 9))
    except (_Rerun, _Parou):
        pass
    except Exception as e:
        _erros.append(f"{type(e).__name__}: {str(e)[:150]}")
    finally:
        (_pc.acoes_movimento, _pc.tempos_do_board, _antigo) = _guardado
        _pc.DIAGNOSTICO_POR_FILTRO.clear()
        _pc.DIAGNOSTICO_POR_FILTRO.update(_antigo)

    conta("a conferencia de pontos monta", not _erros,
          "; ".join(_erros))

    # ── O CONTEUDO, e nao "nao explodiu" ────────────────────────────────
    import conferencia_pontos as _cf
    _crua = _cf.contagem_crua(_cards, _listas, _membros, "idp",
                              {"ana": "Ana", "bruno": "Bruno"}, set(), _pl._num)
    conta("a conta crua soma os tres cartoes concluidos",
          _crua["total"] == 240.0,
          f"somou {_crua['total']} — deveria ser 120+80+40")
    _dif, _por = _cf.comparar(_crua, _d)
    conta("e a diferenca contra o sistema e o tamanho do buraco",
          _dif == 240.0,
          f"a diferenca deu {_dif}, e o sistema mostrou "
          f"{_d['pts_equipe']} — se ela some, a queda volta a ser invisivel")
    conta("o ponto sem dono e contado a parte",
          _crua["qtd"]["pontos_fora_do_quadro"] == 40.0,
          "o cartao concluido sem membro soma no time e em ninguem, e isso "
          "tem de aparecer: e por isso que a soma dos individuais da menos "
          "que o coletivo")
    conta("o motivo do mes indeterminado nao se confunde com 'outro mes'",
          _cf.motivo_de_fora(_cards[0], _listas, "idp", set(), None,
                             (2026, 9), _pl._num) == "mes_desconhecido",
          "sem motivo proprio, a queda por janela truncada fica indistinguivel "
          "de cartao de outro mes — e e justamente ela que some sozinha")

    # E O AVISO DE TRUNCAMENTO TEM DE ESTAR NO CODIGO DA TELA.
    #
    # `diag["truncado"]` existia desde sempre em `placar_core.py:698` e
    # NENHUMA tela lia. Calcular e nao mostrar e o mesmo que nao calcular.
    # POR AST, E NAO PELO TEXTO. A primeira versao procurava a palavra
    # "truncado" no fonte — e a mutacao que APAGOU o aviso passou verde,
    # porque a palavra continuava no comentario que explica o aviso. E a
    # guarda que se encontra a si mesma, pela enesima vez nesta base.
    #
    # A pergunta certa tem duas partes: existe um `if` que LE "truncado", e
    # dentro dele alguem ESCREVE na tela? Calcular e nao mostrar e o mesmo
    # que nao calcular.
    import ast as _ast_cp
    import inspect as _insp_cp
    _arv_cp = _ast_cp.parse(
        _ast_cp.unparse(_ast_cp.parse(
            _insp_cp.getsource(_pl.bloco_conferencia_de_pontos).lstrip())))
    _avisa = False
    for _n in _ast_cp.walk(_arv_cp):
        if not isinstance(_n, _ast_cp.If):
            continue
        _le = any(isinstance(_c, _ast_cp.Constant) and _c.value == "truncado"
                  for _c in _ast_cp.walk(_n.test))
        if not _le:
            continue
        _escreve = any(
            (getattr(_c.func, "attr", "") in ("error", "warning", "info"))
            for _c in _ast_cp.walk(_ast_cp.Module(body=_n.body,
                                                  type_ignores=[]))
            if isinstance(_c, _ast_cp.Call))
        _avisa = _avisa or _escreve
    conta("a tela LE a marca de janela truncada E avisa na tela",
          _avisa,
          "nao ha `if` lendo 'truncado' com aviso dentro: a perda de pontos "
          "volta a ser silenciosa, que e exatamente o defeito de origem")


def _mapa_de_pontos(conta):
    """O bloco que mostra de onde vem cada ponto — Painel e TV."""
    import placar as _pl
    import placar_snapshot as _ps

    _d = {"cards_pts": [{"id": "a", "card": "Álbum 30x30",
                         "lista": "CRIATIVO FOTOS (NOVAS: 10/VAR.:2)",
                         "pts": 128, "membros": ["myrelladesouza"]},
                        {"id": "b", "card": "Relógio de parede",
                         "lista": "DESATIVAR (50)", "pts": 80,
                         "membros": ["gabriel_borges", "beatriz51"]}],
          "pen_total": 100.0,
          "pen_cards": [{"card": "Atraso na entrega", "valor": 100,
                         "membros": ["nicollas1"]}]}

    # UM RETRATO SO: a aba de comparar tem de DIZER que falta dia, e nao
    # ficar em branco nem explodir no `next()`.
    _um = [{"data": "2026-09-28", "pts_equipe": 208, "pen_total": 100,
            "saldo": 108, "meta": 5000, "pct": 2.16,
            "cartoes": '{"a":128,"b":80}'}]
    _dois = _um + [{"data": "2026-09-29", "pts_equipe": 128, "pen_total": 100,
                    "saldo": 28, "meta": 5000, "pct": 0.56,
                    "cartoes": '{"a":128}'}]
    casos = [
        ("Mapa de pontos: com cartões e penalidade", _d, lambda *a, **k: _dois),
        # SEM RETRATO NENHUM: a tela explica que o historico comecou agora.
        ("Mapa de pontos: nenhum retrato ainda", _d, lambda *a, **k: []),
        ("Mapa de pontos: um retrato so, nao da para comparar", _d,
         lambda *a, **k: _um),
        # MES SEM CARTAO NENHUM somando — nao pode quebrar no sorted/sum.
        ("Mapa de pontos: nenhum cartão somando",
         {"cards_pts": [], "pen_total": 0.0, "pen_cards": []},
         lambda *a, **k: []),
        # PLANILHA FORA DO AR: `ler` ja devolve [], e a tela segue de pe.
        ("Mapa de pontos: planilha fora do ar", _d, lambda *a, **k: []),
    ]
    _ler_guardado = _ps.ler
    try:
        for nome, _dd, _ler_fn in casos:
            _falso = instalar()
            _pl.st = _falso
            _ps.ler = _ler_fn
            try:
                _pl.bloco_mapa_de_pontos(_dd, 5000)
                conta(nome, True, "")
            except (_Rerun, _Parou):
                conta(nome, True, "")
            except Exception as e:
                conta(nome, False, f"{type(e).__name__}: {e}")
    finally:
        _ps.ler = _ler_guardado

    # A VARIACAO DA TV e texto puro, e tem de sair legivel de longe.
    _ps._memoria_limpar()
    conta("Variação da TV: sem retrato anterior devolve None",
          _ps.variacao(100.0) is None, "")


def _processar_cards_pts(conta):
    """`_processar` passou a guardar cada cartao que soma. A invariante e que
    eles somem EXATAMENTE o total — e o retrato diario inteiro depende disso:
    `placar_snapshot.confere` so fecha em zero se a lista for completa.

    `ferramentas_chat.py` tambem le o retorno de `_processar` (linha 237), e
    e por isso que o quarto verificador pediu esta guarda.
    """
    import placar as _pl
    import placar_core as _pc

    # SO A REDE E TROCADA. `_processar` roda inteira: e a soma dela que
    # precisa ser conferida, nao o gspread nem o Trello.
    _g_tempos, _g_mov, _g_ent = (_pc.tempos_do_board, _pc.acoes_movimento,
                                 _pc.entradas_se_preciso)
    _pc.tempos_do_board = lambda *a, **k: {}
    _pc.acoes_movimento = lambda *a, **k: {}
    _pc.entradas_se_preciso = lambda *a, **k: {}
    try:
        _listas = {"L1": "DESATIVAR (50)", "L2": "TRIAGEM",
                   "L3": "CONFERENCIA VÍDEO (10)",
                   "L4": "TABELA DE PONTUAÇÃO"}
        _cf = lambda v: [{"idCustomField": "idp", "value": {"number": str(v)}}]
        # Meio do mes, e nao 01/01 00:00 UTC: o mes do cartao e o de
        # Brasilia (02/10), e meia-noite UTC do dia 1o ainda e dezembro aqui.
        _cards = [
            # SOMA: concluido, em lista que pontua, com o campo PONTOS.
            {"id": "c1", "name": "Desativar carimbos", "idList": "L1",
             "idMembers": [], "labels": [], "idLabels": [], "due": None,
             "dueComplete": True, "customFieldItems": _cf(50),
             "dateLastActivity": "2020-01-15T12:00:00.000Z"},
            {"id": "c2", "name": "Conferência vídeo", "idList": "L3",
             "idMembers": [], "labels": [], "idLabels": [], "due": None,
             "dueComplete": True, "customFieldItems": _cf(10),
             "dateLastActivity": "2020-01-15T12:00:00.000Z"},
            # SOMA, E ISSO MUDOU EM 29/09. A TRIAGEM pagava zero, e em
            # 28/09 a equipe moveu 18 cartoes CONCLUIDOS para la: os pontos
            # sumiram da pessoa e da coletiva, sem aviso. O dono decidiu que
            # a TRIAGEM paga. Este cartao e a prova viva da decisao.
            {"id": "c3", "name": "Na triagem", "idList": "L2",
             "idMembers": [], "labels": [], "idLabels": [], "due": None,
             "dueComplete": True, "customFieldItems": _cf(100),
             "dateLastActivity": "2020-01-15T12:00:00.000Z"},
            # NAO SOMA: a TABELA DE PONTUACAO e a legenda do quadro, nao
            # trabalho. Sem um cartao aqui, a guarda deixaria de medir
            # LISTAS_SEM_PONTUACAO e ficaria verde com a lista inteira vazia.
            {"id": "c5", "name": "Legenda de pontos", "idList": "L4",
             "idMembers": [], "labels": [], "idLabels": [], "due": None,
             "dueComplete": True, "customFieldItems": _cf(200),
             "dateLastActivity": "2020-01-15T12:00:00.000Z"},
            # NAO SOMA: o "concluido" nao esta marcado. `placar.py:621`.
            {"id": "c4", "name": "Aberto ainda", "idList": "L1",
             "idMembers": [], "labels": [], "idLabels": [], "due": None,
             "dueComplete": False, "customFieldItems": _cf(80),
             "dateLastActivity": "2020-01-15T12:00:00.000Z"},
        ]
        _falso = instalar()
        _pl.st = _falso
        _d = _pl._processar(_listas, _cards, {}, "idp", "idt", "idi",
                            filtro_mes=(2020, 1))
        _soma = sum(c["pts"] for c in _d["cards_pts"])
        conta("cards_pts soma EXATAMENTE o total da equipe",
              _soma == _d["pts_equipe"],
              f"cards_pts={_soma} · pts_equipe={_d['pts_equipe']}")
        conta("so os cartoes que somam entram na lista",
              sorted(c["id"] for c in _d["cards_pts"]) == ["c1", "c2", "c3"],
              str(sorted(c["id"] for c in _d["cards_pts"])))
        conta("a TRIAGEM paga pontos — decisao do dono em 29/09",
              any(c["id"] == "c3" for c in _d["cards_pts"]),
              "cartao concluido na TRIAGEM tem de somar")
        conta("e a TABELA DE PONTUACAO continua sem pagar",
              all(c["id"] != "c5" for c in _d["cards_pts"]),
              "a legenda do quadro nao e trabalho")
        conta("cada cartao traz id, nome, lista e pontos",
              all({"id", "card", "lista", "pts", "membros"} <= set(c)
                  for c in _d["cards_pts"]), "")
        # QUEM MAIS LE: ferramentas_chat.py:243 monta o saldo com estas duas
        # chaves. Acrescentar cards_pts nao pode ter mexido nelas.
        conta("ferramentas_chat continua achando pts_equipe e pen_total",
              _d.get("pts_equipe") == 160 and _d.get("pen_total") == 0,
              f"{_d.get('pts_equipe')} / {_d.get('pen_total')}")
    except Exception as e:
        conta("cards_pts soma EXATAMENTE o total da equipe", False,
              f"{type(e).__name__}: {e}")
    finally:
        _pc.tempos_do_board, _pc.acoes_movimento = _g_tempos, _g_mov
        _pc.entradas_se_preciso = _g_ent


def _chat(conta):
    """O chat do sidebar — ele desenha, e nenhuma guarda o desenhava.

    O campo de anexo passou a aceitar QUALQUER formato e a converter antes de
    mandar ao modelo. Era o unico campo de imagem do Studio que recusava
    HEIC: quem fotografa o produto no iPhone recebia so "arquivo nao serve".
    """
    import chat_assistente as _ca

    _falso = instalar()
    _ca.st = _falso
    try:
        _ca.renderizar_chat("myrelladesouza")
        conta("O chat do sidebar monta", True, "")
    except (_Rerun, _Parou):
        conta("O chat do sidebar monta", True, "")
    except Exception as e:
        conta("O chat do sidebar monta", False, f"{type(e).__name__}: {e}")

    # O CAMPO DE ANEXO NAO PODE VOLTAR A LISTAR EXTENSOES. Ler a chamada no
    # codigo-fonte da funcao, e nao o arquivo: guarda que varre o arquivo se
    # encontra a si mesma — ja aconteceu quatro vezes nesta base.
    # ── O COMANDO DO CHAT RODA DEPOIS DA TELA, E ERA ISSO QUE FALTAVA ────
    #
    # 05/10, teste do dono: duas das oito peças falharam por timeout; ele
    # pediu no chat para gerar as faltantes, e o comando morreu com
    # `st.session_state.img_modo cannot be modified after the widget with key
    # img_modo is instantiated`.
    #
    # A ORDEM É A CAUSA: `app.py:2092` desenha o chat DEPOIS da página, e
    # `imagem.py:9211` já criou o rádio `img_modo` (e `imagem.py:9648` o
    # multiselect `img_tipos_multi`). Quando o comando roda, os dois widgets
    # existem — e o Streamlit recusa escrever na chave deles.
    #
    # A guarda antiga (chat_assistente.py, autoteste) chamava a função com o
    # `session_state` limpo, onde nenhum widget nasceu: ela media a função
    # num mundo em que a regra não existe, e ficava verde. Aqui o duplo é o
    # MESMO da tela, com o registro de widgets já preenchido pelo desenho de
    # `pagina_imagem` — o caminho inteiro, no ambiente real.
    _falso_f = instalar()
    import importlib as _imp_f
    import sys as _sys_f
    _img_f = _imp_f.import_module("imagem")
    for _nm_f, _mod_f in list(_sys_f.modules.items()):
        if getattr(_mod_f, "st", None) is not None and not _nm_f.startswith(
                ("streamlit", "checar_")):
            try:
                _mod_f.st = _falso_f
            except Exception:
                pass
    try:
        _img_f.pagina_imagem("myrelladesouza")
    except (_Rerun, _Parou):
        pass
    except Exception:
        pass
    _desenhou_f = "img_modo" in _falso_f._chaves
    conta("a tela de Imagem desenha o rádio `img_modo`", _desenhou_f,
          "sem ele a guarda abaixo não mede nada — o registro de widgets "
          "ficou vazio e a escrita passaria por legítima")

    _erro_f = ""
    try:
        _ca.preparar_geracao_dos_faltantes(["2 — Benefícios do produto",
                                            "8 — Ambientação realista (sem texto)"])
    except Exception as _e_f:
        _erro_f = f"{type(_e_f).__name__}: {_e_f}"
    conta("gerar as faltantes pelo chat NÃO escreve em chave de widget",
          _erro_f == "",
          f"{_erro_f} — é o erro que o dono recebeu em 05/10: o chat promete "
          "gerar as duas que faltaram e morre antes de marcar nada")

    _marcou_f = (_falso_f.session_state.get("img_tipos_multi")
                 or _falso_f.session_state.get("img_pedido_faltantes"))
    conta("e o pedido das faltantes fica registrado em algum lugar",
          bool(_marcou_f),
          "o comando não deixou rastro nenhum: a aba não tem como saber "
          "quais peças refazer")

    # E O PEDIDO TEM DE CHEGAR AO MULTISELECT. "Não explodiu" não é
    # "funcionou": a primeira correção poderia guardar o pedido numa chave que
    # ninguém lê, que é exatamente o defeito que `preparar_geracao_dos_faltantes`
    # já teve uma vez (`chat_gerar_faltantes`, escrita e lida por ninguém, em
    # 29/09 — a colaboradora pediu sete peças e nenhuma foi gerada).
    #
    # Então a guarda desenha a tela DE NOVO, que é a passada seguinte em
    # produção, e confere o que o multiselect recebeu.
    _falso_g = instalar()
    for _nm_g, _mod_g in list(_sys_f.modules.items()):
        if getattr(_mod_g, "st", None) is not None and not _nm_g.startswith(
                ("streamlit", "checar_")):
            try:
                _mod_g.st = _falso_g
            except Exception:
                pass
    _duas_g = ["2 — Benefícios do produto", "8 — Ambientação realista (sem texto)"]
    _falso_g.session_state["img_pedido_faltantes"] = list(_duas_g)
    try:
        _img_f.pagina_imagem("myrelladesouza")
    except (_Rerun, _Parou):
        pass
    except Exception:
        pass
    conta("e na passada seguinte as duas peças chegam ao multiselect",
          _falso_g.session_state.get("img_tipos_multi") == _duas_g,
          f"o multiselect recebeu {_falso_g.session_state.get('img_tipos_multi')!r} "
          "— o pedido foi guardado numa chave que ninguém lê, que é o defeito "
          "de 29/09 com outro nome")
    conta("e a aba abre no modo Selecionar",
          _falso_g.session_state.get("img_modo") == "Selecionar",
          "a aba abriu noutro modo: as peças estão marcadas numa tela que o "
          "colaborador não está vendo")
    # E O PEDIDO NÃO VOLTA. Sem o `pop`, a tela prende no modo Selecionar e
    # quem tenta sair dele é jogado de volta a cada passada.
    conta("e o pedido é consumido — não prende a tela no Selecionar",
          "img_pedido_faltantes" not in _falso_g.session_state,
          "o pedido ficou guardado: a cada passada a tela volta para o modo "
          "Selecionar, e o colaborador não consegue sair dele")

    _falso = instalar()
    _ca.st = _falso
    import inspect as _insp_ch
    _corpo = _insp_ch.getsource(_ca.renderizar_chat)
    _ini = _corpo.find("Anexar imagem")
    _trecho = _corpo[_ini:_ini + 900] if _ini >= 0 else ""
    conta("o anexo do chat aceita qualquer formato",
          bool(_trecho) and "type=None" in _trecho,
          "o campo voltou a listar extensoes — HEIC de iPhone seria recusado")
    # E O CONVERSOR TEM DE ESTAR NO CAMINHO: sem ele o arquivo cru vai ao
    # modelo e volta erro generico, sem dizer qual e o problema.
    # PROCURAR A CHAMADA, NAO A PALAVRA. A primeira versao procurava
    # "normalizar_imagem" no corpo — e achava a propria mencao no comentario
    # acima da chamada. Tirar a chamada de verdade nao reprovava nada.
    conta("e converte antes de mandar ao modelo",
          ".normalizar_imagem(" in _corpo, "")


def _retrato_no_painel(conta):
    """A gravacao do retrato roda DENTRO de `pagina_placar` — na thread da
    TV, a cada volta, de minuto em minuto. E a unica linha deste diff que
    fala com a rede em todo desenho de tela.

    O cenario "sem credencial do Trello" nao a alcanca: ele sai antes. Esta
    guarda existe porque o protocolo de 28/09 pergunta, antes de subir, qual
    verificador leu a linha que mudou — e nenhum lia esta.
    """
    import inspect as _insp_r
    import placar as _pl
    import placar_snapshot as _ps

    _corpo = _insp_r.getsource(_pl.pagina_placar)
    _i = _corpo.find("placar_snapshot")
    _trecho = _corpo[max(0, _i - 400):_i + 400] if _i >= 0 else ""
    # PROTEGIDA POR try/except: uma planilha fora do ar nao pode derrubar o
    # Painel de Metas nem congelar a TV.
    conta("a gravacao do retrato esta dentro de um try",
          bool(_trecho) and "try:" in _trecho and "except Exception:" in _trecho,
          "a chamada esta desprotegida — planilha fora do ar derruba a tela")
    # E O MES VAI JUNTO: sem ele, olhar agosto no seletor gravaria agosto
    # como o retrato de hoje, e a comparacao de amanha acusaria uma queda de
    # mes inteiro que nunca houve.
    conta("e o mes que a tela mostra vai junto na chamada",
          "filtro_mes=filtro_mes" in _trecho,
          "sem filtro_mes, olhar um mes passado grava retrato mentiroso")

    # E A GRAVACAO EM SI, com a planilha quebrada, nao levanta excecao.
    class _AbaMorta:
        def get_all_records(self):
            raise RuntimeError("sem rede")

        def append_row(self, *a, **k):
            raise RuntimeError("sem rede")

    _ps._memoria_limpar()
    try:
        _r = _ps.gravar({"pts_equipe": 10.0, "pen_total": 0.0,
                         "cards_pts": [{"id": "a", "pts": 10}]},
                        5000, aba=_AbaMorta())
        conta("planilha morta devolve 'falhou' em vez de explodir",
              _r == "falhou", str(_r))
    except Exception as e:
        conta("planilha morta devolve 'falhou' em vez de explodir", False,
              f"{type(e).__name__}: {e}")
    _ps._memoria_limpar()


def _historico_de_prompts(conta):
    """O .txt do historico — e o que ele diz quando volta vazio.

    28/09: o dono baixou e recebeu "Nenhum prompt registrado ainda". Isso
    pode significar DUAS coisas muito diferentes:

      - o log esta mesmo vazio (a geracao foi antes de a coluna existir), ou
      - o log TEM linhas, mas nenhuma bateu com o nome do produto — porque
        `imagem.py` filtrava por igualdade EXATA de string.

    Dizer "nenhum prompt registrado" no segundo caso e afirmar o que nao se
    sabe, e manda quem le procurar no lugar errado.
    """
    import imagem as _img_h

    _linhas = [
        {"produto": "Caneca Medieval", "peca": "1", "prompt": "a" * 40,
         "origem": "geracao"},
        {"produto": "Caneca Medieval", "peca": "1", "prompt": "b" * 40,
         "origem": "correcao"},
    ]
    # NOME COM CAIXA E ESPACO DIFERENTES continua sendo o mesmo produto.
    for _nome, _esperado in (("Caneca Medieval", 2), ("  caneca medieval  ", 2),
                             ("CANECA MEDIEVAL", 2)):
        conta(f"o filtro do historico acha o produto com {_nome!r}",
              len(_img_h.filtrar_por_produto(_linhas, _nome)) == _esperado,
              "")
    # E PRODUTO DIFERENTE NAO ENTRA. Foi puxar material do produto errado
    # que gerou o relato da colaboradora em 28/09.
    conta("e nao traz o produto errado junto",
          _img_h.filtrar_por_produto(_linhas, "Porta Joias") == [], "")
    # SEM NOME, vem tudo — o colaborador pediu o historico, nao um filtro.
    conta("sem nome digitado, vem tudo",
          len(_img_h.filtrar_por_produto(_linhas, "")) == 2, "")

    # A MENSAGEM TEM DE SEPARAR OS DOIS CASOS.
    conta("log vazio diz que o log esta vazio",
          "não há nenhum" in _img_h.recado_do_historico([], [], "Caneca"),
          _img_h.recado_do_historico([], [], "Caneca"))
    _r = _img_h.recado_do_historico(_linhas, [], "Porta Joias")
    conta("log cheio e nome que nao bate diz OUTRA coisa",
          "Porta Joias" in _r and "não há nenhum" not in _r, _r)
    conta("e oferece baixar o histórico inteiro",
          "sem filtrar" in _r or "todos" in _r.lower(), _r)


def _contexto_do_log(conta):
    """A tela marca quem está gerando ANTES de abrir qualquer thread?

    ESTA GUARDA NASCEU DE UMA MUTACAO QUE PASSOU. Corrigido o registro para
    ler de um global de modulo, mutei a TELA — tirei o `marcar_contexto` — e
    nenhuma das guardas reprovou. O registro ficaria correto e gravando
    vazio do mesmo jeito, em silencio, porque o global nunca seria
    preenchido. Meia correcao parece correcao inteira ate alguem baixar o
    arquivo.
    """
    import inspect as _insp_c
    import imagem as _img_c
    import log_imagem as _li_c

    _corpo = _insp_c.getsource(_img_c.pagina_imagem)
    # PROCURAR A CHAMADA, nao a palavra: o comentario acima dela cita o nome,
    # e uma guarda que busca o nome se encontra no proprio comentario.
    conta("a tela marca o contexto do log",
          ".marcar_contexto(" in _corpo,
          "sem isto o global fica vazio e o log grava produto em branco")
    # E ANTES DA PRIMEIRA THREAD: marcar depois nao serve para a geracao que
    # ja partiu.
    # A CHAMADA REAL, e nao o texto. A primeira versao procurava "Thread("
    # cru e se achou no COMENTARIO logo acima — que explica justamente por
    # que a marcacao nao fica junto de cada Thread. E a quinta vez nesta
    # base que uma guarda se encontra a si mesma. `ast` so ve codigo.
    import ast as _ast_c
    _arv = _ast_c.parse(_ast_c.unparse(_ast_c.parse(_corpo.lstrip())))
    _l_ctx = _l_th = None
    for _n in _ast_c.walk(_arv):
        if not isinstance(_n, _ast_c.Call):
            continue
        _alvo = getattr(_n.func, "attr", "") or getattr(_n.func, "id", "")
        if _alvo == "marcar_contexto" and _l_ctx is None:
            _l_ctx = _n.lineno
        elif _alvo == "Thread" and _l_th is None:
            _l_th = _n.lineno
    conta("e marca ANTES de abrir a primeira thread",
          _l_ctx is not None and (_l_th is None or _l_ctx < _l_th),
          f"marcar_contexto na linha {_l_ctx}, primeira Thread na {_l_th}")

    # ── E O NOME QUE ELA MARCA E O DA PORTA UNICA ───────────────────────
    #
    # UM NOME, UMA RESPOSTA — e aqui havia duas.
    #
    # A marcacao da geracao usava `cfg.get("nome_produto")`, enquanto a tela
    # (e o chat, e a copy vigente) le `session_state["img_nome_produto"]`,
    # cujo escritor unico e `definir_produto_da_sessao`. Os dois concordavam
    # por tabela, porque a porta era chamada no FIM da geracao — mas so
    # `if galeria` (imagem.py:10722). Geracao que falha inteira deixava o
    # contexto com o nome do cfg e a sessao com o nome anterior.
    #
    # Divergindo, o log grava um nome e o historico filtra pelo outro, e a
    # copy corrigida fica guardada numa chave que ninguem procura. Nao
    # corrompe nada — simplesmente nao e achada, que e a pior forma de
    # defeito desta base: silenciosa.
    #
    # A ASERCAO E SOBRE O ARGUMENTO, por AST. Procurar o texto
    # "definir_produto_da_sessao" no corpo acha a chamada do FIM da geracao
    # e fica verde sem medir nada — ela sempre esteve la.
    _prod_de = []
    for _n in _ast_c.walk(_arv):
        if not isinstance(_n, _ast_c.Call):
            continue
        if (getattr(_n.func, "attr", "") or getattr(_n.func, "id", "")) \
                != "marcar_contexto":
            continue
        for _kw in _n.keywords:
            if _kw.arg != "produto":
                continue
            _prod_de.append(_ast_c.unparse(_kw.value))
    conta("e o nome marcado sai da porta unica do produto",
          bool(_prod_de) and all(
              "definir_produto_da_sessao" in _v
              or "img_nome_produto" in _v
              or "peca" in _v
              for _v in _prod_de),
          f"marcar_contexto recebe {_prod_de} — nome que nao vem de "
          "`definir_produto_da_sessao` e segunda resposta para a mesma "
          "pergunta: o log grava um, o historico filtra o outro, e a copy "
          "corrigida fica numa chave que ninguem procura")
    # ── A DATA DO PAINEL E A DE BRASILIA ────────────────────────────────
    #
    # `pagina_placar` monta `agora = datetime.now()` — UTC no container — e
    # esse `agora` decide DOIS numeros: a janela do "por que mudou entre dois
    # dias" e a DATA DO RETRATO DIARIO. Depois das 21h locais ja e o dia
    # seguinte em UTC: o retrato de sexta seria gravado como sabado, e a
    # comparacao que o dono pediu ("sexta 102%, hoje 98%") pegaria a linha
    # errada. O defeito nasceu no proprio commit que criou o retrato.
    import placar as _pl_h
    _corpo_pl = _insp_c.getsource(_pl_h.pagina_placar)
    _codigo_pl = "\n".join(
        l.split("#", 1)[0] for l in _corpo_pl.splitlines())
    conta("a data do Painel de Metas vem com fuso",
          "datetime.now()" not in _codigo_pl.replace(" ", ""),
          "datetime.now() cru no Painel: o retrato diario grava o dia errado "
          "depois das 21h")

    # E A FUNCAO EXISTE do outro lado: a tela chamar um nome que sumiu
    # levantaria AttributeError dentro de um `try` que engole tudo.
    conta("e `marcar_contexto` existe em log_imagem",
          callable(getattr(_li_c, "marcar_contexto", None)), "")


# As telas que NENHUM verificador desenhava ate 28/09. A varredura das seis
# Formas apontou doze; estas sao as que a assinatura permite chamar direto.
#
# `pagina_analise_metas` e `pagina_pedir_abono` ficaram de fora de proposito:
# elas leem o Trello e a planilha em cadeias fundas, e um duplo pobre demais
# acusaria o inocente — foi o que a primeira versao de checar_tela fez com
# `linha_do_mes`. Verificador que da alarme falso ensina a ser ignorado.
TELAS_SEM_GUARDA = [
    ("admin", "pagina_admin"),
    # `verificar_login` DESENHA a tela de login e nenhum verificador a
    # alcancava — o quarto cobrou em 28/09. E a primeira tela que todo
    # colaborador ve: se ela quebra, ninguem entra.
    ("auth", "verificar_login"),
    ("descricao", "pagina_descricao"),
    ("gestao", "pagina_home"),
    ("gestao", "pagina_financeiro"),
    # A aba OPERACIONAL, criada em 30/09 a pedido do dono. Ela entra aqui
    # pelo mesmo motivo das outras: `checar_impacto` reprovou o nome novo
    # com leitor em `app.py` e guarda nenhuma — e tela que ninguem desenha
    # e tela que quebra em producao sem aviso.
    ("gestao", "pagina_operacional"),
    ("financeiro", "pagina_financeiro"),
    ("palavras_chave", "pagina_palavras_chave"),
    ("relogio_ponto", "pagina_ponto"),
    ("tit_ml", "pagina_titulo"),
    ("triagem", "pagina_triagem"),
    ("video", "pagina_video"),
]


class _AbaVazia:
    """Uma aba de planilha que existe e não tem nada dentro.

    A FRONTEIRA DE I/O É AQUI, e não no `st.secrets`. A primeira tentativa foi
    dar segredos de mentira ao duplo — e o código seguiu em frente até bater
    no `google.auth` de verdade, pedindo `token_uri`. Trocar o segredo é
    mentir mais fundo; trocar a planilha é trocar exatamente o que vai à rede.
    """

    def get_all_records(self, **kw):
        return []

    def get_all_values(self, **kw):
        return []

    def row_values(self, _n):
        return []

    def col_values(self, _n):
        return []

    def append_row(self, *a, **kw):
        return None

    def update_cell(self, *a, **kw):
        return None

    def update(self, *a, **kw):
        return None

    def add_cols(self, *a, **kw):
        return None

    def delete_rows(self, *a, **kw):
        return None

    def find(self, *a, **kw):
        return None


class _PlanilhaVazia:
    def worksheet(self, _nome):
        return _AbaVazia()

    def add_worksheet(self, **kw):
        return _AbaVazia()

    def worksheets(self):
        return []


def _sem_planilha():
    """Troca o acesso ao Google Sheets por um duplo. Devolve o que restaurar."""
    import sheets as _sh
    guardado = (_sh.planilha, _sh.cliente)
    _sh.planilha = lambda *a, **k: _PlanilhaVazia()
    _sh.cliente = lambda *a, **k: None
    return _sh, guardado


def _telas_restantes(conta):
    """Desenha as telas que nenhum verificador alcancava.

    NAO CONFEREM CONTEUDO — so que a pagina MONTA. E pouco, e e exatamente o
    que faltava: a Home caiu em producao com `TypeError: string indices must
    be integers`, e os quatro verificadores de entao passaram verdes porque
    nenhum deles desenhava nada.

    Cada uma roda com o Streamlit falso e sem credencial: o caminho que o
    colaborador ve quando a planilha ou o Trello estao fora do ar.
    """
    import importlib
    import sys as _sys_t

    _sh, _guardado = _sem_planilha()
    for modulo, funcao in TELAS_SEM_GUARDA:
        nome = f"{funcao} monta ({modulo}.py)"
        _falso = instalar()
        try:
            _m = importlib.import_module(modulo)
            # O FALSO VAI PARA A CADEIA INTEIRA, e nao so para o modulo de
            # entrada. `gestao.pagina_home` desenha via `home_gestao`, e o
            # `st` dele tinha ficado apontando para o falso de um cenario
            # ANTERIOR — cujo registro de chaves ja tinha `hg_gasto_mes`.
            # Resultado: ChaveRepetida acusando codigo que esta certo.
            # Alarme falso ensina a ignorar o verificador.
            for _nm, _mod in list(_sys_t.modules.items()):
                if getattr(_mod, "st", None) is not None and not _nm.startswith(
                        ("streamlit", "checar_")):
                    try:
                        _mod.st = _falso
                    except Exception:
                        pass
            # A maioria recebe o usuario logado; `verificar_login` nao —
            # ela E quem o descobre. Chamar com a assinatura errada seria
            # alarme falso em cima de codigo certo.
            import inspect as _insp_tr
            if _insp_tr.signature(getattr(_m, funcao)).parameters:
                getattr(_m, funcao)("martinsousa")
            else:
                getattr(_m, funcao)()
            conta(nome, True, "")
        except (_Rerun, _Parou):
            conta(nome, True, "")
        except Exception as e:
            conta(nome, False, f"{type(e).__name__}: {str(e)[:160]}")
    _sh.planilha, _sh.cliente = _guardado


def _txt_consolidado(conta):
    """O .txt com os prompts de TODAS as pecas de uma vez.

    Dono, 28/09: "nao tem como ter um botao que consolida o que sera enviado
    de todas as imagens para que eu nao precise abrir e copiar um por um?".
    Eram oito expanders, oito cliques, oito colagens.

    O QUE ESTA GUARDA IMPEDE: que o arquivo saia com peca faltando, com a
    ordem trocada, ou sem dizer o que ele NAO contem — a ambientacao lida das
    referencias so entra na hora de gerar, e um arquivo que nao avisa isso
    faz quem le procurar defeito onde nao ha.
    """
    import imagem as _img_t
    # O import vem ANTES do primeiro uso, e nao la embaixo: a primeira versao
    # usava `_insp_t` neste bloco e so o importava depois — UnboundLocalError,
    # que ja derrubou producao duas vezes nesta base e e exatamente o que o
    # segundo verificador existe para achar.
    import inspect as _insp_t

    # ── A CADEIA REAL, E NAO TEXTO DE MENTIRA ───────────────────────────
    #
    # ESTA GUARDA FALTAVA, E O BOTAO QUEBROU EM PRODUCAO COM ELA VERDE.
    #
    # A primeira versao chamava `txt_dos_prompts` com pares de string que eu
    # mesmo escrevi, e com `direcao_arte="Medieval Rústico"` — uma STRING.
    # Na realidade a direcao de arte e um DICIONARIO (`imagem.py:6681`:
    # `plano.get("direcao_de_arte") or {}`), e o `.strip()` nela levantava
    # `AttributeError: 'dict' object has no attribute 'strip'`.
    #
    # Duplo mais pobre que a realidade acusa o inocente — e aqui fez pior:
    # absolveu o culpado. A guarda agora chama `prompt_de_cada_peca` de
    # verdade, com um plano e um cfg com a forma que a tela monta.
    _cfg_real = {"instrucoes_extras": "", "dados_descricao": None,
                 "nome_produto": "Caneca Medieval", "refs_layout_nomes": [],
                 "instrucao_layout": "", "ambientacao": "",
                 "fotos_bytes": [], "refs_layout_bytes": None}
    _dir_dict = {"nome": "Medieval Mineral", "descricao": "pedra e metal",
                 "paleta": {"fundo": "Cimento Claro", "painel": "Antracita"},
                 "materiais": "concreto, metal oxidado",
                 "luz": "natural e difusa", "trava_produto": "cinza em metal"}
    _plano_real = [
        {"numero": 1, "tipo": "1 — Capa do anúncio (fundo branco)",
         "cena": "produto sobre fundo branco", "textos": [], "viavel": True},
        {"numero": 4, "tipo": "4 — Close nos detalhes",
         "cena": "close na alça", "textos": ["DETALHE: acabamento"],
         "viavel": True},
    ]
    _guardadas = (_img_t._chamar_openai_geracao, _img_t._get_openai_api_key,
                  _img_t._descricao_do_produto_cacheada)
    _img_t._chamar_openai_geracao = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("o preview NAO pode chamar motor"))
    _img_t._get_openai_api_key = lambda: "sk-conferencia"
    _img_t._descricao_do_produto_cacheada = lambda *a, **k: ("d", "l")
    try:
        _reais = _img_t.prompt_de_cada_peca(
            _plano_real, _cfg_real, _img_t.TIPOS_PADRAO, _dir_dict)
        conta("prompt_de_cada_peca roda com a direcao de arte em DICIONARIO",
              len(_reais) == 2 and all(isinstance(t, str) for _r, t in _reais),
              str(type(_reais[0][1]) if _reais else None))
        _txt_real = _img_t.txt_dos_prompts(_reais, "Caneca Medieval", _dir_dict)
        conta("e o .txt sai da cadeia real sem explodir",
              "PEÇA 1" in _txt_real and "PEÇA 2" in _txt_real, "")
        conta("com a direcao de arte legivel, e nao o dicionario cru",
              "Medieval Mineral" in _txt_real and "{'nome'" not in _txt_real, "")
        # E PELA MESMA FUNCAO QUE O PROMPT USA. `bloco_direcao_de_arte` ja
        # renderiza a direcao para o brief; um segundo renderizador dentro do
        # .txt seria a Forma 5 — dois textos para a mesma direcao,
        # discordando um dia.
        conta("e renderizada por `bloco_direcao_de_arte`, a mesma do prompt",
              "bloco_direcao_de_arte(" in _insp_t.getsource(
                  _img_t.txt_dos_prompts),
              "o .txt ganhou um renderizador proprio da direcao de arte")
    except Exception as e:
        conta("prompt_de_cada_peca roda com a direcao de arte em DICIONARIO",
              False, f"{type(e).__name__}: {str(e)[:140]}")
    finally:
        (_img_t._chamar_openai_geracao, _img_t._get_openai_api_key,
         _img_t._descricao_do_produto_cacheada) = _guardadas

    _pares = [("1 — Capa do anúncio (fundo branco)", "TEXTO DA PECA UM " * 4),
              ("4 — Close nos detalhes", "TEXTO DA PECA QUATRO " * 4),
              ("5 — Características técnicas", "TEXTO DA PECA CINCO " * 4)]
    _txt = _img_t.txt_dos_prompts(_pares, "Caneca Medieval", "Medieval Rústico")

    # TODA PECA ENTRA, e nenhuma some no meio.
    conta("o txt traz as tres pecas",
          all(f"PEÇA {i} —" in _txt for i in (1, 2, 3)), "")
    conta("e o texto de cada uma", all(p[1].strip()[:20] in _txt for p in _pares), "")
    # A ORDEM E A DO PLANO: peca 1 antes da 4, e a 4 antes da 5.
    conta("na ordem do plano",
          _txt.index("PEÇA 1") < _txt.index("PEÇA 2") < _txt.index("PEÇA 3"), "")
    # O CABECALHO DIZ O QUE FALTA. Sem isso, quem le acha que o arquivo e o
    # prompt final e procura defeito no lugar errado.
    conta("o cabecalho avisa que a ambientacao entra so na geracao",
          "AMBIENTAÇÃO" in _txt and "acrescentado no fim" in _txt, "")
    conta("e nomeia o produto", "Caneca Medieval" in _txt, "")
    conta("e traz a direcao de arte uma vez so",
          _txt.count("Medieval Rústico") == 1, "")

    # BORDAS: plano vazio nao pode gerar arquivo quebrado.
    _vazio = _img_t.txt_dos_prompts([], "")
    conta("plano vazio gera arquivo legivel, e nao vazio",
          "Peças: 0" in _vazio and "(sem nome)" in _vazio, "")
    # E O ARQUIVO TEM DE SER TEXTO DE VERDADE: bytes tortos nao abrem.
    try:
        _vazio.encode("utf-8"); _txt.encode("utf-8")
        _cod = True
    except Exception:
        _cod = False
    conta("o arquivo codifica em utf-8", _cod, "")

    # A FONTE E UNICA: a tela e o txt tem de sair da MESMA funcao, senao os
    # dois discordam — e a questao e so quando (Forma 5).
    _corpo_pag = _insp_t.getsource(_img_t.pagina_imagem)
    conta("a tela monta os prompts pela funcao unica",
          "prompt_de_cada_peca(" in _corpo_pag,
          "a tela voltou a montar o prompt por conta propria")
    # E O BLOCO DO PREVIEW NAO MONTA O SEU.
    #
    # Duas versoes desta guarda nasceram erradas, e as duas por mutacao:
    #
    #   1. procurar so o nome da funcao unica: ela era encontrada no bloco do
    #      BOTAO, entao o expander podia voltar a montar o proprio sem
    #      reprovar nada;
    #   2. proibir `montar_prompt_imagem` na PAGINA INTEIRA: isso acusava o
    #      caminho da GERACAO (`imagem.py:7252`), que legitimamente monta o
    #      seu — ele acrescenta a ambientacao lida das referencias, que o
    #      preview nao tem como ter. E a diferenca que o cabecalho do .txt
    #      avisa. Alarme falso em cima de codigo certo ensina a ignorar.
    #
    # A assercao certa e sobre o BLOCO DO PREVIEW, e so ele.
    _ini_pv = _corpo_pag.find("if _ver_prompts:")
    _fim_pv = _corpo_pag.find("_desc = descarte_de_layout()")
    _bloco_pv = (_corpo_pag[_ini_pv:_fim_pv]
                 if 0 <= _ini_pv < _fim_pv else "")
    conta("o bloco do preview foi encontrado", bool(_bloco_pv),
          "a guarda ficou cega — o bloco mudou de forma")
    for _cru in ("montar_prompt_imagem(", "prompt_que_sera_enviado("):
        conta(f"e o preview nao chama {_cru[:-1]} direto",
              bool(_bloco_pv) and _cru not in _bloco_pv,
              "a montagem voltou para dentro do preview: duas fontes para o "
              "mesmo prompt discordam, e a questao e so quando")


def _peca_olhada(conta):
    """A conferencia de IMAGEM roda na geracao, e o defeito aparece na peca.

    Dono, 28/09: "por que o prompt continua gerando imagens erradas mudando o
    produto e posicionando informacoes cortadas?"

    Porque a conferencia que existia le o que esta ESCRITO. As regras de
    borda, de sobreposicao e de fidelidade estavam TODAS no prompt — 5, 6 e 7
    vezes nos 9 prompts dele — e o modelo passou por cima. Regra nos dois
    lados nao se resolve escrevendo de novo: se resolve OLHANDO o que saiu.

    Esta guarda nao chama `revisar_peca`: ela le o CODIGO de `pagina_imagem`.
    O defeito e "faltou chamar em algum lugar", e nenhum teste de unidade pega
    uma chamada que nao existe — foi assim que duas mutacoes minhas passaram
    verdes hoje de manha.
    """
    import ast as _ast_po
    import importlib
    import inspect as _insp_po

    _m = importlib.import_module("imagem")
    # AS DUAS FUNCOES, e nao so a tela.
    #
    # A primeira versao desta guarda lia so `pagina_imagem`, e a mutacao que
    # tirava a conferencia do "refazer do zero" do chat passou VERDE: aquele
    # bloco vive em `consumir_comandos_do_chat`, outra funcao. Guarda que le
    # metade do caminho mede metade do caminho — e foi o caminho de fora o
    # unico que nunca teve conferencia nenhuma.
    # CADA FUNCAO CONTADA POR SI, e nao as duas num bolo so.
    #
    # A primeira versao juntava as duas e perguntava "existe chamada?". O
    # setimo verificador mostrou o buraco: tirando a conferencia do LACO DA
    # GERACAO, a guarda continuava verde — porque a chamada do chat ainda
    # estava la. Guarda que pergunta "existe em algum lugar" nao ve a peca
    # que deixou de ser conferida.
    _arvores = {}
    for _f in (_m.pagina_imagem, _m.consumir_comandos_do_chat):
        _arvores[_f.__name__] = _ast_po.parse(
            _ast_po.unparse(_ast_po.parse(_insp_po.getsource(_f).lstrip())))
    _corpo = "\n".join(
        _ast_po.unparse(_a) for _a in _arvores.values())
    _arv = _ast_po.parse(_corpo)

    def _conta_chamadas(arvore, nome):
        return sum(1 for _n in _ast_po.walk(arvore)
                   if isinstance(_n, _ast_po.Call)
                   and (getattr(_n.func, "attr", "")
                        or getattr(_n.func, "id", "")) == nome)

    # Tres lugares geram uma peca inteira e tem de conferir: o laco e o botao
    # de refazer, em `pagina_imagem`; o refazer do chat, em
    # `consumir_comandos_do_chat`.
    _na_tela = _conta_chamadas(_arvores["pagina_imagem"], "revisar_tudo")
    _no_chat = _conta_chamadas(_arvores["consumir_comandos_do_chat"],
                               "revisar_tudo")
    conta("a TELA confere nos dois lugares que geram do zero",
          _na_tela >= 2,
          f"`pagina_imagem` chama revisar_tudo {_na_tela}x — sao dois "
          "caminhos que geram peca inteira: o laco da geracao e o botao de "
          "refazer. Um deles esta entregando sem conferir")
    conta("e o CHAT confere no dele",
          _no_chat >= 1,
          "`consumir_comandos_do_chat` nao confere: o refazer do chat volta "
          "a entregar sem ler o texto e sem olhar a peca")

    _chamadas = {}
    for _n in _ast_po.walk(_arv):
        if isinstance(_n, _ast_po.Call):
            _alvo = getattr(_n.func, "attr", "") or getattr(_n.func, "id", "")
            if _alvo in ("revisar_texto", "revisar_peca", "revisar_tudo",
                         "peca_em_aviso"):
                _chamadas.setdefault(_alvo, []).append(_n.lineno)
    _chamadas_diretas = {k: list(v) for k, v in _chamadas.items()}
    # `revisar_tudo` E as duas: ela le o texto e olha a peca, nesta ordem.
    # Contar so o nome direto reprovaria quem passou a usar a porta — alarme
    # falso em cima de codigo certo, que e o que ensina a ignorar a saida.
    for _porta in _chamadas.get("revisar_tudo", []):
        _chamadas.setdefault("revisar_texto", []).append(_porta)
        _chamadas.setdefault("revisar_peca", []).append(_porta + 1)

    # E A PORTA NAO PODE VIRAR OCA. Se `revisar_tudo` deixar de chamar uma
    # das duas, todas as asercoes acima continuam verdes e nada e conferido.
    _porta_src = _ast_po.parse(_insp_po.getsource(_m.revisar_tudo).lstrip())
    _dentro = {(getattr(_n.func, "attr", "") or getattr(_n.func, "id", ""))
               for _n in _ast_po.walk(_porta_src) if isinstance(_n, _ast_po.Call)}
    conta("a porta unica chama MESMO as duas conferencias",
          {"revisar_texto", "revisar_peca"} <= _dentro,
          f"revisar_tudo chama {sorted(_dentro)} — a porta virou oca e todo "
          "caminho que passa por ela deixa de conferir, em silencio")

    conta("a geracao OLHA a peca, e nao so le o texto dela",
          "revisar_peca" in _chamadas,
          "o laco de geracao nao chama revisar_peca — texto cortado, cartao "
          "sobre o produto e alca a mais saem para a tela do colaborador")

    # ── UMA PERGUNTA, UMA RESPOSTA (Forma 5) ────────────────────────────
    #
    # A porta `revisar_tudo` existe justamente para os tres caminhos
    # concordarem — inclusive na ORDEM, que custa dinheiro: trocar a copy e
    # uma troca de string, refazer o quadro e uma geracao paga.
    #
    # A primeira versao desta correcao deixou o LACO chamando as duas soltas e
    # os outros dois usando a porta. Duas respostas para a mesma pergunta
    # passam a discordar — a questao e so quando —, e a guarda teve de
    # aceitar os dois jeitos, o que e exatamente o que a enfraquece.
    _soltas = [l for l in (_chamadas_diretas.get("revisar_texto", [])
                           + _chamadas_diretas.get("revisar_peca", []))]
    conta("ninguem chama as duas conferencias fora da porta unica",
          not _soltas,
          f"{len(_soltas)} chamada(s) diretas a revisar_texto/revisar_peca "
          f"(linhas {_soltas}) — a ordem e as rodadas passam a depender de "
          "quem escreveu cada trecho")

    # E AS FOTOS TEM DE CHEGAR LA.
    #
    # `revisar_peca` sem fotos devolve None e nao confere nada — de
    # proposito, porque julgar fidelidade sem ter com o que comparar e o
    # alarme falso mais caro que existe. So que isso tambem e o jeito mais
    # silencioso de desligar a conferencia inteira: `fotos_ref=[]` e a
    # geracao volta a entregar sem ninguem olhar, com todas as guardas
    # verdes. Foi a mutacao D, e ela passou.
    # As DUAS portas: quem chama a conferencia direto e quem chama pela
    # `revisar_tudo`. Olhar so uma delas deixaria o outro caminho desligar a
    # conferencia em silencio — foi a mutacao D, e ela ja passou verde uma vez.
    _ch_peca = [_n for _n in _ast_po.walk(_arv)
                if isinstance(_n, _ast_po.Call)
                and (getattr(_n.func, "attr", "") or getattr(_n.func, "id", ""))
                in ("revisar_peca", "revisar_tudo")]
    _fotos_vazias = []
    for _c in _ch_peca:
        _kw = {k.arg: k.value for k in _c.keywords}
        _v = _kw.get("fotos_ref")
        if _v is None:
            _fotos_vazias.append(("sem fotos_ref", _c.lineno))
        elif isinstance(_v, (_ast_po.List, _ast_po.Tuple)) and not _v.elts:
            _fotos_vazias.append(("fotos_ref vazio", _c.lineno))
        elif isinstance(_v, _ast_po.Constant) and not _v.value:
            _fotos_vazias.append(("fotos_ref constante vazia", _c.lineno))
    conta("as fotos do produto CHEGAM a conferencia",
          _ch_peca and not _fotos_vazias,
          f"{_fotos_vazias} — sem fotos ela devolve None e nao confere nada; "
          "a geracao volta a entregar sem ninguem olhar, e verde")

    # ── E TODO CAMINHO QUE GERA DO ZERO PASSA PELAS DUAS ────────────────
    #
    # O laco nao e o unico que gera uma peca inteira. O "refazer do zero" do
    # chat e o botao de refazer da tela montam o prompt por
    # `prompt_para_regerar` e escrevem os bytes novos direto na galeria — sem
    # ler o texto e sem olhar a peca. Foi o caminho mais usado no dia da
    # caneca, e era o unico sem conferencia nenhuma. Forma 1: a correcao tem
    # de chegar em todos os irmaos, e nao so onde o sintoma apareceu.
    #
    # O AJUSTE fica de fora de propósito, e isso NAO e esquecimento: o ajuste
    # promete preservar o quadro, e o conserto de `revisar_peca` e recompor.
    # Ligar uma na outra poria as duas para brigar.
    _regera = [_n.lineno for _n in _ast_po.walk(_arv)
               if isinstance(_n, _ast_po.Call)
               and (getattr(_n.func, "attr", "") or getattr(_n.func, "id", ""))
               == "prompt_para_regerar"]
    _revisoes = sorted(_chamadas.get("revisar_peca", []))
    _sem_olho = [l for l in _regera
                 if not any(0 < r - l <= 80 for r in _revisoes)]
    conta("todo caminho que REGERA do zero tambem olha a peca",
          _regera and not _sem_olho,
          f"{len(_sem_olho)} caminho(s) montam o prompt de regeracao e "
          f"entregam sem conferir (linhas {_sem_olho} do corpo de "
          "pagina_imagem) — o refazer do chat e o botao de refazer")

    conta("e tambem le o texto dela",
          _regera and not [l for l in _regera
                           if not any(0 < r - l <= 80
                                      for r in sorted(_chamadas.get("revisar_texto", [])))],
          "regeracao sem revisao de texto: volta 'Portatile' e 'apoliando'")

    # ── E DA PARA CONFERIR SEM GASTAR GERACAO ───────────────────────────
    #
    # A conferencia decide sozinha se refaz — e refazer custa. Antes de
    # confiar nela para gastar, o dono precisa poder OLHAR o veredito dela
    # nas pecas que ele JA tem, inclusive as que ele sabe que estao erradas.
    # Uma leitura custa centavos; uma geracao, nao.
    #
    # Sem isto a unica forma de saber se o leitor enxerga o defeito seria
    # gerar um produto inteiro de teste — que e exatamente o retrabalho que
    # esta correcao existe para acabar.
    conta("da para conferir a peca que ja esta na tela, sem gerar de novo",
          any(isinstance(_n, _ast_po.Constant)
              and isinstance(_n.value, str)
              and _n.value.startswith("conf_peca_")
              for _n in _ast_po.walk(_arv)),
          "nao ha botao de conferir na galeria: para saber se a conferencia "
          "enxerga o defeito seria preciso gerar um produto inteiro de teste")

    conta("e o defeito encontrado aparece NA PECA, na tela",
          "peca_em_aviso" in _chamadas,
          "o veredito da imagem e calculado e nao e mostrado — o colaborador "
          "publica a peca sem saber que ela foi reprovada")

    # E O VEREDITO VIAJA COM A IMAGEM. Sem isso a tela tem um aviso geral
    # ("uma delas tem defeito") e obriga a procurar qual — que e o que
    # ninguem faz.
    _guarda_campo = [
        _n for _n in _ast_po.walk(_arv)
        if isinstance(_n, _ast_po.Constant) and _n.value == "peca"]
    conta("o veredito da peca e guardado junto dela na galeria",
          bool(_guarda_campo),
          "a galeria nao carrega o campo `peca`: o aviso vira alerta geral")


def _refazer_cego(conta):
    """A peca refeita pelo chat nascia sem nome, sem plano e sem layout.

    A PROVA veio do .txt do dono, 28/09 17:34: a linha 47 do prompt enviado
    ao modelo era `PRODUTO: ` — vazia. A caneca tinha nome; o prompt nao.

    POR QUE: o refazer le o nome em `img_triagem_config` (imagem.py:5600), e
    o laco da geracao APAGA essa chave ao terminar (imagem.py:7596-7597).
    Junto com ela vao o plano da peca (composicao + a COPY EXATA), a direcao
    de arte, a referencia de layout e a ambientacao — tudo o que
    `prompt_para_regerar` busca ali.

    O nome aparecia no LOG porque o log le OUTRA chave (`img_nome_produto`,
    log_imagem.py:79). Duas respostas para a mesma pergunta: e a Forma 5, e
    elas discordaram.

    O `del` faz DOIS trabalhos num campo so: sinaliza "plano ja consumido"
    (e e ele que impede o painel de reaparecer, imagem.py:6816) e joga o dado
    fora. Esta guarda trava o segundo sem tocar no primeiro.

    O ESTADO AQUI NAO E INVENTADO: e o que o bloco de imagem.py:7586-7597
    deixa na sessao, chave por chave (Forma 7).
    """
    import importlib
    import inspect as _insp_rc
    import sys as _sys_rc

    _falso = instalar()
    _m = importlib.import_module("imagem")
    for _nm, _mod in list(_sys_rc.modules.items()):
        if getattr(_mod, "st", None) is not None and not _nm.startswith(
                ("streamlit", "checar_")):
            try:
                _mod.st = _falso
            except Exception:
                pass

    _tipo = "2 — Benefícios do produto"
    _cfg = {"nome_produto": "Caneca Térmica Medieval 400Ml",
            "ambientacao": "bar medieval a luz de vela",
            "refs_layout_nomes": ["ref_beneficios.jpg"],
            "instrucao_layout": "coluna de cartoes a direita"}
    _plano = {"direcao_de_arte": {"nome": "Medieval Rustico"},
              "plano": [{"tipo": _tipo, "numero": 2,
                         # A COMPOSICAO TRAZ AS DUAS COISAS DE PROPOSITO:
                         # uma decisao de POSICAO (que tem dono — e o
                         # `zonas_da_peca`) e uma decisao de CENA (que so o
                         # plano tem). A guarda confere que a segunda
                         # sobrevive e a primeira e cortada.
                         "composicao": ("caneca a esquerda, cartoes a "
                                        "direita, vapor subindo da boca "
                                        "da caneca"),
                         "cena": "bancada de pedra",
                         "textos": ["INTERIOR INOX: sabor melhor que resina pura"],
                         "viavel": True}]}

    # ── A CHAMADA, E NAO A FUNCAO ───────────────────────────────────────
    #
    # A primeira versao desta guarda chamava `guardar_plano_gerado()` ELA
    # MESMA e depois apagava as chaves na mao. As duas mutacoes passaram
    # verdes: eu estava exercitando a funcao que acabara de escrever, e nao a
    # TELA. E a Forma 6 de novo, e foi pega pelo passo 4 do protocolo.
    #
    # O defeito e "faltou chamar em algum lugar", e nenhum teste de unidade
    # pega uma chamada que nao existe. Entao a guarda le o CODIGO de
    # `pagina_imagem`: todo `del` das chaves vivas tem de vir logo depois de
    # uma chamada a `guardar_plano_gerado` (gerou) ou `limpar_plano_gerado`
    # (cancelou). Por AST, e nao por texto: guarda que varre texto se
    # encontra no proprio comentario.
    import ast as _ast_rc
    _corpo = _insp_rc.getsource(_m.pagina_imagem)
    _arv = _ast_rc.parse(_ast_rc.unparse(_ast_rc.parse(_corpo.lstrip())))

    _dels, _guardas = [], []
    for _n in _ast_rc.walk(_arv):
        if isinstance(_n, _ast_rc.Delete):
            for _al in _n.targets:
                if (isinstance(_al, _ast_rc.Subscript)
                        and getattr(_al.slice, "value", None)
                        in ("img_triagem_plano", "img_triagem_config")):
                    _dels.append(_n.lineno)
        if isinstance(_n, _ast_rc.Call):
            _alvo = getattr(_n.func, "attr", "") or getattr(_n.func, "id", "")
            if _alvo in ("guardar_plano_gerado", "limpar_plano_gerado"):
                _guardas.append(_n.lineno)

    _orfaos = [d for d in _dels
               if not any(0 < d - g <= 8 for g in _guardas)]
    conta("todo `del` das chaves de triagem trata o dado antes",
          _dels and not _orfaos,
          f"{len(_orfaos)} `del` sem guardar/limpar logo acima (linhas "
          f"{_orfaos} do corpo de pagina_imagem) — o plano, a copy e o nome "
          "do produto vao junto, e a peca refeita nasce cega")

    # E O SINAL TEM DE CAIR. Guardar o dado sem apagar a chave viva e a meia
    # correcao: o painel de confirmacao volta por cima da galeria.
    conta("e o `del` continua existindo — o painel nao volta",
          len(_dels) >= 4,
          f"achei {len(_dels)} `del` das chaves vivas; sem eles o painel do "
          "plano reaparece depois de gerar")

    _st = _falso.session_state
    _st["img_nome_produto"] = _cfg["nome_produto"]
    _st["img_galeria"] = [{"tipo": _tipo, "bytes": b"x"}]
    _st[_m.CHAVE_CONFIG_GERADA] = dict(_cfg)
    _st[_m.CHAVE_PLANO_GERADO] = dict(_plano)

    # O QUE O CHAT LE PARA REFAZER (imagem.py:5598-5600).
    _cfg_rf = _m.config_da_geracao()
    _nome_rf = _cfg_rf.get("nome_produto", "")
    conta("o refazer do chat ainda sabe o nome do produto",
          _nome_rf == _cfg["nome_produto"],
          f"leu {_nome_rf!r} — o prompt sai com `PRODUTO: ` vazio, que foi "
          "o que o dono recebeu no .txt de 28/09")

    _p = _m.prompt_para_regerar(_tipo, "cartoes inteiros",
                                {"cor": "Cinza", "medidas": "12x14",
                                 "peso": "326"}, _nome_rf)
    conta("e o nome chega ao prompt enviado ao modelo",
          f"PRODUTO: {_cfg['nome_produto']}" in _p,
          "a linha PRODUTO do prompt esta vazia")
    conta("o PLANO da peca sobrevive a geracao",
          "PLANO DE CRIAÇÃO" in _p and "vapor subindo" in _p,
          "a peca refeita perde a composicao planejada")
    # E A POSICAO TEM UM DONO SO.
    #
    # Esta asercao exigia "caneca a esquerda" NO PROMPT, e passou verde por
    # meses — ate `sem_decisao_do_compilador` entrar. Ela media a Forma 5:
    # a triagem mandando o produto para a esquerda e `zonas_da_peca`
    # mandando a mesma coisa em porcentagem, duas vozes sobre o mesmo
    # assunto. Hoje a triagem cala e o compilador fala — mas CALAR OS DOIS
    # seria pior que os dois falarem, entao as duas linhas andam juntas.
    # O FRAGMENTO E SO O DO PLANO, E ISSO IMPORTA.
    #
    # A primeira versao desta linha exigia TAMBEM "cartoes a direita"
    # ausente — e essa frase chega ao prompt por OUTRA porta, a
    # `instrucao_layout` da referencia de layout ("coluna de cartoes a
    # direita"), que e legitima e nao e o plano. A asercao reprovaria o
    # inocente. So "caneca a esquerda" nasce da composicao e de mais nada.
    conta("e a posicao do plano foi cortada — ela tem dono",
          "caneca a esquerda" not in _p,
          "a composicao do plano voltou a mandar na posicao: duas vozes "
          "sobre o mesmo assunto, e a peca sai torta quando discordam")
    conta("e quem manda na posicao e a GEOMETRIA calculada",
          "GEOMETRIA DESTA PEÇA" in _p and "ZONA DO PRODUTO" in _p,
          "cortei a voz do plano e nao sobrou nenhuma: o modelo escolhe o "
          "lado sozinho, que e pior que duas vozes concordando")
    conta("a COPY EXATA sobrevive — e quem evita 'Portatile'",
          "INTERIOR INOX" in _p,
          "sem a copy pronta o gerador volta a redigir a frase sozinho")
    conta("a direcao de arte sobrevive",
          "Medieval Rustico" in _p, "a peca refeita muda de paleta")
    conta("a ambientacao sobrevive",
          "bar medieval a luz de vela" in _p,
          "a peca refeita perde o cenario que o colaborador pediu")
    conta("a referencia de layout sobrevive",
          "ref_beneficios.jpg" in _p or "coluna de cartoes a direita" in _p,
          "a peca refeita ignora o layout aprovado")

    # ── OS IRMAOS QUE O PASSO 5 ACHOU ───────────────────────────────────
    #
    # `prompt_para_regerar` nao e o unico que buscava em `img_triagem_config`.
    # Corrigir so ele seria a Forma 1 de novo: consertar onde o sintoma
    # apareceu, e nao onde a regra alcanca.
    import chat_assistente as _ca_rc
    _ca_rc.st = _falso

    # A PORTA QUE O CHAT USA, conferida pelo nome. `checar_impacto` reprovou
    # aqui: `plano_da_geracao` tinha leitor em outro arquivo e nenhuma guarda
    # citando ela. Exercitar por tabela nao basta — quem trocar a assinatura
    # dela amanha precisa que algum teste fale o nome.
    conta("plano_da_geracao devolve a copia quando a chave viva ja caiu",
          _m.plano_da_geracao().get("direcao_de_arte", {}).get("nome")
          == "Medieval Rustico",
          "a porta do plano voltou vazia depois da geracao")
    conta("e config_da_geracao idem",
          _m.config_da_geracao().get("nome_produto") == _cfg["nome_produto"],
          "a porta da config voltou vazia depois da geracao")

    # 1. O CONTEXTO DO ASSISTENTE. Sem o plano, ele nao sabe o que cada peca
    #    deveria ser — e tem de deduzir o arranjo olhando a imagem pronta,
    #    que foi o que custou tres rodadas na caneca.
    # A ASSERCAO E SOBRE A LINHA QUE SO O PLANO PRODUZ.
    #
    # Duas versoes anteriores desta guarda passaram verdes medindo outra
    # coisa: a primeira procurava o nome do produto (que chega ali por outro
    # caminho), a segunda o nome do TIPO (que vem da listagem da galeria,
    # logo abaixo, e existe com ou sem plano). So "Plano de triagem:"
    # (chat_assistente.py:240) nasce do plano e de mais nada.
    _ctx = _ca_rc._contexto_atual()
    conta("o assistente ainda enxerga o plano depois de gerar",
          "Plano de triagem:" in _ctx,
          "o contexto do chat perde a linha do plano assim que a geracao "
          "termina — ele passa a conversar so com a lista da galeria")

    # 2. `gerar_imagens_faltantes` respondia "nao ha produto aberto na aba
    #    Imagem" — com o produto aberto. A mentira sai do mesmo `cfg` vazio.
    _resp = _ca_rc._executar_comando(
        {"acao": "gerar_imagens_faltantes"}) or ""
    conta("completar a galeria nao diz mais que nao ha produto aberto",
          "não há produto aberto" not in str(_resp).lower(),
          f"respondeu: {str(_resp)[:120]!r}")


def _fotos_perdidas(conta):
    """As fotos anexadas somem quando o Studio reinicia — e a tela oferece de volta.

    28/09, 17:17. O dono mandou o print: tres fotos listadas no campo de
    upload, e o botao respondendo "Suba pelo menos uma foto do produto".

    Por que acontece: a lista de NOMES fica no navegador, e os BYTES ficam na
    memoria do PROCESSO do Streamlit
    (`streamlit/runtime/memory_uploaded_file_manager.py`, `file_storage` — um
    dicionario). Deploy, queda ou troca de container matam o processo; o
    navegador nao sabe e continua mostrando os nomes. O Python recebe ZERO
    arquivo, e a mensagem que ele da e uma mentira do ponto de vista de quem
    esta olhando a tela.

    Esta guarda desenha a PAGINA INTEIRA, com fotos guardadas no disco do
    rascunho e o campo de upload vazio — que e exatamente o estado depois do
    reinicio — e confere que o botao de recuperar foi OFERECIDO. Conferir que
    a funcao de disco grava e le e outra coisa, e ela vive em rascunho.py: o
    defeito aqui foi na TELA, entao e a tela que tem de ser desenhada.
    """
    import importlib
    import shutil as _sh_fp
    import sys as _sys_fp
    import tempfile as _tmp_fp

    import rascunho as _rasc_fp

    _base = _tmp_fp.mkdtemp()
    _pasta_real = _rasc_fp._pasta
    _rasc_fp._pasta = lambda u, _b=_base: os.path.join(_b, str(u))
    _sh, _guardado = _sem_planilha()
    try:
        _estado_ft = {}
        _revisar_real = None
        _PNG = b"\x89PNG\r\n\x1a\n" + b"z" * 3000
        _rasc_fp.salvar_fotos("martinsousa", [_PNG, _PNG],
                              ["frente.jpeg", "lado.jpeg"])

        _falso = instalar()
        _m = importlib.import_module("imagem")
        _revisar_real = _m.revisar_anexos
        for _nm, _mod in list(_sys_fp.modules.items()):
            if getattr(_mod, "st", None) is not None and not _nm.startswith(
                    ("streamlit", "checar_")):
                try:
                    _mod.st = _falso
                except Exception:
                    pass
        try:
            _m.pagina_imagem("martinsousa")
        except (_Rerun, _Parou):
            pass
        except Exception as e:
            conta("a tela de Imagem monta com o upload vazio", False,
                  f"{type(e).__name__}: {str(e)[:160]}")
            return
        conta("a tela de Imagem monta com o upload vazio", True, "")

        # O CONTEUDO, e nao "nao explodiu". Foi essa a Forma 1 do protocolo:
        # guarda que so confere que a tela montou nao ve campo vazio.
        conta("com fotos no disco, a tela OFERECE recuperar",
              "img_recuperar_fotos" in _falso._chaves,
              "o botao de recuperar nao foi desenhado — quem perdeu as fotos "
              "no reinicio nao tem como pega-las de volta")

        # E sem nada no disco ele NAO aparece: botao que promete o que nao
        # existe e pior do que botao nenhum.
        _rasc_fp.limpar_fotos("martinsousa")
        _falso2 = instalar()
        for _nm, _mod in list(_sys_fp.modules.items()):
            if getattr(_mod, "st", None) is not None and not _nm.startswith(
                    ("streamlit", "checar_")):
                try:
                    _mod.st = _falso2
                except Exception:
                    pass
        try:
            _m.pagina_imagem("martinsousa")
        except (_Rerun, _Parou):
            pass
        except Exception:
            pass
        conta("sem fotos no disco, o botao nao aparece",
              "img_recuperar_fotos" not in _falso2._chaves,
              "o botao apareceu sem ter o que recuperar")

        # ── E A GRAVACAO NAO PODE ACONTECER A CADA TECLA ────────────────
        #
        # O Streamlit redesenha a pagina inteira a cada tecla digitada. A
        # primeira versao desta correcao chamava `salvar_fotos` em toda
        # passada: seis fotos de 5 MB dariam 30 MB escritos no disco por
        # tecla. E o mesmo defeito que fez a Home levar 15 segundos.
        #
        # Aqui a tela e desenhada TRES vezes com as MESMAS fotos, e o disco
        # so pode ter sido escrito na primeira.
        _gravou = []
        _salvar_real = _rasc_fp.salvar_fotos
        _rasc_fp.salvar_fotos = (
            lambda u, f, n=(), campo="produto", _r=_salvar_real:
            (_gravou.append(1), _r(u, f, n, campo))[1])
        _PNG2 = b"\x89PNG\r\n\x1a\n" + b"y" * 4000
        try:
            for _ in range(3):
                _f3 = instalar()
                for _nm, _mod in list(_sys_fp.modules.items()):
                    if getattr(_mod, "st", None) is not None and not _nm.startswith(
                            ("streamlit", "checar_")):
                        try:
                            _mod.st = _f3
                        except Exception:
                            pass
                _f3.session_state.update(_estado_ft)
                _m.revisar_anexos = lambda *a, **k: (
                    [_PNG2], ["frente.jpeg"], [], [])
                try:
                    _m.pagina_imagem("martinsousa")
                except (_Rerun, _Parou):
                    pass
                _estado_ft = dict(_f3.session_state)
        finally:
            _rasc_fp.salvar_fotos = _salvar_real
            _m.revisar_anexos = _revisar_real
        conta("as fotos vao ao disco UMA vez, e nao a cada tecla",
              len(_gravou) == 1,
              f"gravou {len(_gravou)} vez(es) em 3 passadas iguais — "
              "com seis fotos de 5 MB isso e 30 MB por tecla digitada")

        # O `DeletedFile` que o Streamlit entrega no lugar do upload perdido
        # tem guarda propria em `imagem.py` (auto-teste), com a classe de
        # verdade. Aqui nao da para importa-la: o duplo ja ocupou
        # `sys.modules["streamlit"]`.
    finally:
        _rasc_fp._pasta = _pasta_real
        _sh.planilha, _sh.cliente = _guardado
        _sh_fp.rmtree(_base, ignore_errors=True)


def _fatura_confirmada(conta):
    """A fatura em PDF so grava DEPOIS de o dono confirmar na tela.

    Ate 28/09 o caminho era: ler, mostrar, o dono conferir contra a fatura
    aberta, AVISAR-ME, eu ligar o lancamento e subir um deploy. Dias, para um
    clique. E enquanto isso os lancamentos do cartao nao entravam.

    O risco que travava isso esta escrito em `extratos_tela.py:90`: a fatura
    e um DESENHO, nao uma planilha. O banco muda o layout e o leitor passa a
    devolver numero errado sem erro nenhum na tela — num sistema de dinheiro,
    a pior falha possivel.

    A saida nao e ligar sozinho: e o dono confirmar. Ele ja compara com a
    fatura aberta; o que faltava era o botao. Estas guardas fixam as tres
    coisas que tornam isso seguro:

      1. NADA e gravado sem confirmacao explicita;
      2. o botao so aparece quando ha lancamento lido e nenhum erro;
      3. gravar duas vezes nao duplica — `lancamentos.gravar` ja filtra pela
         identidade, e a tela tem de DIZER quantos foram repetidos.
    """
    import inspect as _insp_f
    import extratos_tela as _et_f
    import lancamentos as _lan_f

    _corpo = _insp_f.getsource(_et_f._fatura)

    conta("a fatura tem botao de confirmar e lancar",
          "st.button(" in _corpo and "CONFIRMO" in _corpo.upper(),
          "sem botao, o caminho continua sendo me avisar e esperar deploy")
    # GRAVAR SO DEPOIS DO CLIQUE. A chamada nao pode estar solta no corpo.
    _i_grav = _corpo.find("_lan.gravar(")
    if _i_grav < 0:
        _i_grav = _corpo.find(".gravar(")
    if _i_grav < 0:                       # 06/10: grava no mes do vencimento
        _i_grav = _corpo.find(".gravar_fatura(")
    conta("a gravacao existe no caminho da fatura", _i_grav >= 0, "")
    if _i_grav >= 0:
        _antes = _corpo[:_i_grav]
        conta("e ela vem DEPOIS de um if de botao",
              "st.button(" in _antes,
              "gravar fora do if do botao grava em todo desenho da tela")

    # A DEDUPLICACAO E O QUE TORNA O CLIQUE REPETIDO INOFENSIVO.
    _l = [{"data": "01/09/2026", "descricao": "MERCADO X", "valor": -50.0}]
    _id1 = _lan_f.com_identidade(list(_l), "cartao")[0]["id"]
    _id2 = _lan_f.com_identidade(list(_l), "cartao")[0]["id"]
    conta("o mesmo lancamento tem sempre a mesma identidade", _id1 == _id2, "")
    _outro = _lan_f.com_identidade(
        [{"data": "01/09/2026", "descricao": "MERCADO X", "valor": -51.0}],
        "cartao")[0]["id"]
    conta("e valor diferente muda a identidade", _id1 != _outro, "")
    # DUAS LINHAS IGUAIS NO MESMO ARQUIVO sao dois fatos, e nao um repetido.
    _dois = _lan_f.com_identidade(_l + list(_l), "cartao")
    conta("duas linhas identicas do mesmo arquivo nao viram uma",
          _dois[0]["id"] != _dois[1]["id"], "")

    # E A TELA TEM DE DIZER O QUE ACONTECEU, inclusive os repetidos: gravar
    # 12 de 40 sem explicar por que faz o dono achar que perdeu 28.
    conta("a tela informa quantos foram gravados e quantos repetidos",
          "repetid" in _corpo.lower(), "")


def _quebra_do_ml(conta):
    """A tela ADS-Cross DESENHA a seção que mexe em `lancamentos`?

    ACHADO EM 03/10, pelo passo 3 do protocolo. `_levar_para_o_mes` é a
    função que APAGA a linha do cartão e GRAVA as partes no lugar — é a
    única coisa deste commit que escreve dinheiro — e nenhum verificador a
    alcançava. Quebrada de propósito, `checar_tela`, `checar_alcance`,
    `checar_impacto` e `checar_comunicacao` ficaram os quatro VERDES.

    POR QUE PÔR A TELA EM `TELAS_SEM_GUARDA` NÃO BASTARIA, e esta é a parte
    que quase me escapou: `pagina()` sem arquivo subido volta no
    `_casos_em_aberto` e NUNCA chega em `_levar_para_o_mes`. A guarda ficaria
    verde com o defeito dentro — guarda que não passa pela linha medida não é
    guarda, e esta base já pagou por isso.

    Então a seção é chamada direto, com um `pag` vindo de
    `fatura_ml.ler_pagamentos` — a cadeia real, não um dicionário escrito
    aqui. Valor inventado no teste mede o meu entendimento do sistema, e é
    ele que costuma estar errado.
    """
    import fatura_ml as _fm
    import fatura_ml_tela as _fmt

    _falso = instalar()
    _fmt.st = _falso
    pag = _fm.ler_pagamentos([], [
        {_fm.PG_NUMERO: "1", _fm.PG_APLICADO: 2762.80,
         _fm.PG_DETALHE: "Tarifa por campanha de publicidade de Product Ads",
         _fm.PG_DATA: "2026-09-04"},
        {_fm.PG_NUMERO: "2", _fm.PG_APLICADO: 69.60,
         _fm.PG_DETALHE: "Cobrança de ICMS-DIFAL", _fm.PG_DATA: "2026-09-04"},
    ])
    try:
        _fmt._levar_para_o_mes(_fm, pag, "martinsousa")
        conta("a seção que reparte a fatura do ML desenha", True, "")
    except (_Rerun, _Parou):
        conta("a seção que reparte a fatura do ML desenha", True, "")
    except Exception as e:
        conta("a seção que reparte a fatura do ML desenha", False,
              f"{type(e).__name__}: {str(e)[:160]}")

    # E SEM O RELATÓRIO DE PAGAMENTO ela não lança no escuro: sem saber o que
    # SAIU do cartão, repartir o cobrado poria no mês R$ 220,72 que o ML
    # abateu e que nunca saiu do bolso.
    try:
        _fmt._levar_para_o_mes(_fm, None, "martinsousa")
        conta("e sem o relatório de pagamento ela não quebra", True, "")
    except (_Rerun, _Parou):
        conta("e sem o relatório de pagamento ela não quebra", True, "")
    except Exception as e:
        conta("e sem o relatório de pagamento ela não quebra", False,
              f"{type(e).__name__}: {str(e)[:160]}")


def _lista_de_finalidades(conta):
    """As duas telas leem a MESMA lista de finalidades, de um dono so?

    Em 02/10 a lista estava escrita em `finalidades_tela._finalidades` E em
    `extratos_tela._finalidades_conhecidas`, e as duas copias JA discordavam:
    a de Extratos nao tinha EMPRESTIMO PRONAMP, REEMBOLSO PRONAMP, RATEIO
    CUSTO FIXO nem APLICACAO. Classificar um nome numa tela oferecia opcoes
    que a outra nao oferecia — a Forma 5 do CLAUDE.md acontecida.

    A guarda nao compara as duas listas entre si: isso passaria verde no dia
    em que alguem recriasse as duas copias iguais. Ela exige que as duas
    contenham a base de `favorecidos.FINALIDADES_BASE`, que e o dono.
    """
    import favorecidos as _fv
    import finalidades_tela as _ft
    import extratos_tela as _et

    import composicao as _cp

    base = set(_fv.FINALIDADES_BASE)
    _falta_ft = sorted(base - set(_ft._finalidades({})))
    conta("a tela de Finalidades oferece a base inteira", not _falta_ft,
          "faltando: " + ", ".join(_falta_ft) if _falta_ft else "")
    _falta_et = sorted(base - set(_et._finalidades_conhecidas(_fv)))
    conta("a tela de Extratos oferece a MESMA base", not _falta_et,
          "faltando: " + ", ".join(_falta_et) if _falta_et else "")
    _sem_lado = sorted(f for f in base if _cp.lado(f) == "desconhecida")
    conta("e toda finalidade da base tem lado na conta do LPV", not _sem_lado,
          "sem lado: " + ", ".join(_sem_lado) if _sem_lado else "")


def _form_da_equipe(conta):
    """Trocar de pessoa no seletor reconstrói o formulário inteiro?

    Dono, 02/10, com o print: *"Não corrigiu essa parte para eu conseguir
    remover ou alterar colaboradores?"*. A tela mostrava `bruniellymendonca`
    no username, nome e RHiD em branco, e o aviso "Username do Trello e nome
    são obrigatórios" — com o campo preenchido na frente dele.

    A causa: os campos não tinham chave. Sem chave, o Streamlit guarda o que
    foi DIGITADO e ignora o `value=` na passada seguinte. Trocar a pessoa no
    seletor deixava o username da anterior parado enquanto o resto esvaziava
    — meia ficha na tela, e o formulário recusando salvar.

    A guarda é por AST e mede o que conserta: todo widget do formulário tem
    `key`, e a key depende da SELEÇÃO. Key fixa seria o mesmo defeito com
    outro nome — um widget só para todas as pessoas.
    """
    import ast as _ast_eq
    import inspect as _insp_eq
    try:
        import admin as _adm_eq
        fonte = _insp_eq.getsource(_adm_eq._secao_equipe)
    except Exception as e:
        conta("o formulário da equipe existe para ser medido", False,
              f"{type(e).__name__}: {str(e)[:90]}")
        return
    arv = _ast_eq.parse(fonte.lstrip())
    WIDGETS = ("text_input", "checkbox", "number_input", "selectbox")
    sem_chave, chave_fixa = [], []
    for no in _ast_eq.walk(arv):
        if not (isinstance(no, _ast_eq.Call)
                and isinstance(no.func, _ast_eq.Attribute)
                and no.func.attr in WIDGETS):
            continue
        rotulo = (no.args[0].value if no.args
                  and isinstance(no.args[0], _ast_eq.Constant) else "?")
        chave = next((k.value for k in no.keywords if k.arg == "key"), None)
        if chave is None:
            # O seletor da pessoa é o único que pode ter key própria e fixa:
            # é ele que DECIDE a seleção, não pode depender dela.
            if "Editar quem já existe" not in str(rotulo):
                sem_chave.append(str(rotulo)[:34])
            continue
        texto = _ast_eq.unparse(chave)
        if "_k" not in texto and "Editar quem já existe" not in str(rotulo):
            chave_fixa.append(f"{str(rotulo)[:28]} -> {texto[:28]}")
    conta("todo campo do formulário da equipe tem chave",
          not sem_chave, f"sem chave: {sem_chave}" if sem_chave else "")
    conta("e a chave muda com a pessoa selecionada",
          not chave_fixa, f"chave fixa: {chave_fixa}" if chave_fixa else "")
    # E a chave nasce da seleção, não de um contador qualquer.
    conta("a chave sai do item escolhido no seletor",
          "_k = " in fonte and "_sel" in fonte.split("_k = ")[1][:80],
          "" if "_k = " in fonte else "não achei a montagem da chave")


def _contribuicao_coletiva(conta):
    """Desempenho por Colaborador mostra SO a contribuicao para a coletiva.

    Dono, 02/10: a meta individual e o "bateu" sairam da tela da equipe. O
    Painel desenha com `_barra` e a TV com `_tv_full_html` — cada um tinha a
    sua conta, e a TV nem descontava a penalidade. O `_barra` e desenhado de
    verdade; o `_tv_full_html` pede trinta argumentos, e a guarda dele le o
    codigo da funcao (o bloco, nao o arquivo).
    """
    import inspect
    import placar as _pl
    _h = _pl._barra("Myrella", 3100, 33, 9000)
    conta("Painel: a barra diz pontos e % da coletiva",
          "3,067 pts" in _h and "34% da coletiva" in _h, _h[:160])
    conta("Painel: sem '/ meta individual' na barra",
          " / " not in _h, _h[:160])
    _src_tv = inspect.getsource(_pl._tv_full_html)
    conta("TV: o bloco usa a mesma conta do Painel e nao le meta individual",
          "contribuicao_coletiva" in _src_tv and "meta_ind" not in _src_tv, "")


def _excluir_usuario(conta):
    """Excluir e desativar usuario do app derrubam o link salvo.

    A reconexao pelo link (`?_s=`) so olha os tokens, e nao a aba de
    usuarios: sem revogar, quem foi desativado continuava entrando pelo
    favorito. `_remover_usuario` e `_desativar_usuario` rodam inteiros; so as
    duas abas da planilha sao trocadas.
    """
    import admin as _adm
    import auth as _au

    class _AbaUsr:
        def __init__(self):
            self.linhas = [["login", "senha_hash", "ativo", "admin", "criado_em"],
                           ["Brumielly", "h", "Não", "Sim", "14/09/2026 15:25"],
                           ["Brunielly", "h", "Não", "Sim", "15/09/2026 18:03"],
                           ["Luiz", "h", "Sim", "Sim", "26/08/2026 14:57"]]

        def row_values(self, i):
            return self.linhas[i - 1]

        def get_all_records(self, **kw):
            return [dict(zip(self.linhas[0], l)) for l in self.linhas[1:]]

        def update_cell(self, r, c, v):
            self.linhas[r - 1][c - 1] = v

        def delete_rows(self, i):
            del self.linhas[i - 1]

    class _AbaTok(_AbaUsr):
        def __init__(self):
            self.linhas = [["token", "usuario", "criado_em"],
                           ["tb", "Brumielly", "01/10/2026 10:00"],
                           ["tl", "Luiz", "01/10/2026 10:00"]]

    _u, _t = _AbaUsr(), _AbaTok()
    _g = (_au._aba_usuarios, _au._aba_tokens)
    _au._aba_usuarios, _au._aba_tokens = (lambda: _u), (lambda: _t)
    _au._TOKENS.update({"tb": "Brumielly", "tl": "Luiz"})
    try:
        _ok, _msg = _adm._remover_usuario("Brumielly", "MartinSousa")
        conta("excluir apaga so a linha escolhida",
              _ok and [l[0] for l in _u.linhas[1:]] == ["Brunielly", "Luiz"],
              _msg)
        conta("e o link salvo dela deixa de entrar",
              "tb" not in _au._TOKENS
              and [l[1] for l in _t.linhas[1:]] == ["Luiz"], "")
        conta("ninguem exclui o proprio usuario",
              _adm._remover_usuario("Luiz", "luiz")[0] is False
              and any(l[0] == "Luiz" for l in _u.linhas), "")
        _adm._desativar_usuario("Luiz")
        _luiz = next((l for l in _u.linhas if l[0] == "Luiz"), None)
        conta("desativar tambem derruba o link salvo",
              "tl" not in _au._TOKENS and _luiz is not None
              and _luiz[2] == "Não", "")
    finally:
        _au._aba_usuarios, _au._aba_tokens = _g
        _au._TOKENS.clear()


def _remocao_a_vista(conta):
    """Remover da equipe e excluir usuário: visíveis e sem campo-armadilha.

    05/10: a remoção da equipe só existia depois de escolher a pessoa no
    seletor de edição — o dono não achou. E as duas confirmações pediam o
    login digitado num campo que mostrava o próprio login como exemplo, em
    cinza: parecia preenchido, estava vazio, e o botão ficava travado. Lê o
    BLOCO de cada função, nunca o arquivo.
    """
    import inspect
    import admin as _adm
    _eq = inspect.getsource(_adm._secao_equipe)
    _rm = inspect.getsource(_adm._remover_da_equipe)
    conta("a remoção da equipe aparece antes do seletor de edição",
          "_remover_da_equipe(" in _eq
          and _eq.index("_remover_da_equipe(") < _eq.index("Editar quem já existe")
          and "Remover colaborador da equipe" in _rm, "")
    _pg = inspect.getsource(_adm.pagina_admin)
    conta("nenhuma confirmação usa o login como exemplo de campo vazio",
          "placeholder=usuario_sel" not in _pg
          and 'placeholder=_f.get("username_trello"' not in _eq, "")
    conta("as confirmações são caixas, com chave da pessoa",
          'st.checkbox(f"Confirmo a exclusão' in _pg
          and 'key=f"eq_rm_vista_conf_{_rm_user}"' in _rm, "")


def _lucro_liquido_custo_fixo(conta):
    """Lucro líquido = margem de contribuição − LPV; UC = margem ÷ LPV.

    As fórmulas da planilha do dono (Controle MS, conferida em 05/10):
    MARGEM C. (col. Y) já tira o custo OPERACIONAL; LPV (col. AA) é
    (custo fixo + não operacional) ÷ vendas; UNI. CONT. (col. AB) = Y ÷ AA.
    E o dono, 25/09: "subtraia o LPV, o que sobrar é lucro líquido".

    A CADEIA, NÃO O MEIO DELA: só as leituras são trocadas, e o lucro sai de
    `dados_reais` inteiro. O LPV chega pelo `financeiro.lpv_vigente`, que é
    quem a Home lê.
    """
    import home_gestao as hg
    import base_vendas as _bv
    import financeiro as _fin

    _guardado = (_bv.media_recente, _fin.lpv_vigente, hg._faturamento_bling,
                 hg._partes_fixas, hg._gastos_por_finalidade)
    try:
        _bv.media_recente = lambda *a, **k: (dict(_IND), "")
        _fin.lpv_vigente = lambda *a, **k: (19.68, "Setembro/2026 · calculado")
        hg._faturamento_bling = lambda *a, **k: (190_502.0, [])
        hg._partes_fixas = lambda *a, **k: (22_842.0, 2_350.35, 22_000.0,
                                            9_900.0, [])
        hg._gastos_por_finalidade = lambda *a, **k: (dict(_RESUMO), "")
        hg.st = instalar()
        p = hg.dados_reais(2026, 9, 25)[0]["painel"]
        mc = _IND["margem_contribuicao"] / _IND["vendas"]
        conta("lucro líquido por venda = MC por venda − LPV",
              abs(p["ll_venda"] - (mc - 19.68)) < 0.01,
              f'{p["ll_venda"]} != {mc - 19.68}')
        conta("o % é sobre o faturado líquido, do mesmo período",
              p["lucro_liquido_pct"] == round(
                  (mc - 19.68) * _IND["vendas"] / _IND["faturamento_liquido"]
                  * 100, 1), str(p["lucro_liquido_pct"]))
        conta("a UC é MC por venda ÷ LPV (UNI. CONT. da planilha)",
              abs(p["uc"] - mc / 19.68) < 0.001, str(p["uc"]))
        # O LPV MUDA O LUCRO E A UC JUNTOS — é o mesmo número nas duas contas.
        _fin.lpv_vigente = lambda *a, **k: (30.0, "Setembro/2026 · calculado")
        p2 = hg.dados_reais(2026, 9, 25)[0]["painel"]
        conta("um LPV maior derruba o lucro líquido e a UC juntos",
              p2["ll_venda"] < p["ll_venda"] and p2["uc"] < p["uc"], "")
        hg._partes_fixas = lambda *a, **k: (0.0, 0.0, 0.0, 0.0, [])
        p3 = hg.dados_reais(2026, 9, 25)[0]["painel"]
        conta("trocar o custo fixo do equilíbrio não mexe no lucro líquido",
              p3["ll_venda"] == p2["ll_venda"], "")
        _fin.lpv_vigente = lambda *a, **k: (None, "nenhum LPV informado ainda")
        p4 = hg.dados_reais(2026, 9, 25)[0]["painel"]
        _h = hg._html_indicadores(p4)
        conta("sem LPV o lucro líquido não vira número",
              p4["lucro_liquido"] is None and "falta o LPV" in _h, "")
    except Exception as e:
        conta("lucro líquido com LPV", False, f"{type(e).__name__}: {e}")
    finally:
        (_bv.media_recente, _fin.lpv_vigente, hg._faturamento_bling,
         hg._partes_fixas, hg._gastos_por_finalidade) = _guardado


def _balanco_headcount(conta):
    """O Balanço headcount novo (05/10) desenha inteiro, com a Reserva dentro.

    Só a leitura é trocada: a grade de colaboradores é a SUGESTÃO do código
    passada pelo `folha_clt` de verdade, e a apuração das metas sai de
    `analise_metas.apuracao_bonus` de verdade, sobre um mês montado na forma
    de `_analisar_meses` (conferida em `headcount.py`). O que se confere: a tela monta, o bônus chega ao
    quadro, e a Reserva e os aportes aparecem dentro dela.
    """
    import pandas as pd
    import ajustes as _aj
    import auth as _au
    import colaboradores as _co
    import folha_salarial as _fs
    import headcount as _hc
    import reserva_tela as _rt
    import tabela_tributos as _tt

    _guard = (_co.carregar, _aj.carregar, _hc._apurado_do_mes, _tt.carregar,
              _au.eh_dono, _rt.carregar, _fs.carregar, _hc.carregar,
              _hc.carregar_params, _co.carregar_taxas)
    try:
        _pad = {"cargo": _co.CARGO_PADRAO, "registrado": "Sim",
                "salario_base": _co.SALARIO_PADRAO, "admissao": "2026-01",
                "dias_uteis": 22, "no_aporte": "Sim"}
        _co.carregar = lambda *a, **k: pd.DataFrame(
            [{**_pad, **p} for p in _co.SUGESTOES])
        _co.carregar_taxas = lambda *a, **k: _co.taxas_padrao()
        _aj.carregar = lambda *a, **k: pd.DataFrame(columns=_aj.COLUNAS)
        # A apuração na FORMA que `analise_metas.apuracao_bonus` devolve —
        # a cadeia real dela é conferida em `python3 headcount.py`. Aqui não
        # se importa o Painel de Metas: o `@st.fragment` dele não roda no
        # duplo, e a tela do Balanço só lê o resultado.
        _ap = {"g": {"col": True, "maxx": False, "ind": True,
                     "ind_maxx": False, "pct_time": 12.0, "pct_seu": 8.0}}
        _hc._apurado_do_mes = lambda *a, **k: (
            _ap, {"g": "Gabriel"}, {"bateu_col": True, "bateu_maxx": False}, "")
        _tt.carregar = lambda *a, **k: (pd.DataFrame(columns=_tt.COLUNAS), "")
        _au.eh_dono = lambda *a, **k: True
        _rt.carregar = lambda *a, **k: (dict(_rt._rv.POSICAO_INICIAL), "inicial")
        _fs.carregar = lambda *a, **k: pd.DataFrame(columns=_fs.COLUNAS)
        _hc.carregar = lambda *a, **k: pd.DataFrame(columns=_hc.COLUNAS)
        _hc.carregar_params = lambda *a, **k: _hc.parametros_padrao()
        _falso = instalar()
        for _m in (_hc, _rt, _co, _tt, _fs, _aj):
            _m.st = _falso
        _textos = []
        _md = _falso.markdown
        def _grava(t="", *a, **k):
            _textos.append(str(t))
            return _md(t, *a, **k)
        _falso.markdown = _grava
        _hc.pagina("martinsousa")
        _tudo = " ".join(_textos)
        conta("Balanço headcount monta, com a Reserva dentro", True, "")
        conta("o bônus do Gabriel chega ao quadro (12% + 8% de 3.000)",
              "600,00" in _tudo and "360,00" in _tudo, "")
        conta("e a Reserva e os aportes vêm depois do bônus",
              _tudo.find("Bônus das metas") < _tudo.find("Reserva do Headcount")
              < _tudo.find("Aportes e saldos"), "")
    except (_Rerun, _Parou):
        conta("Balanço headcount monta, com a Reserva dentro", True, "")
    except Exception as e:
        conta("Balanço headcount monta, com a Reserva dentro", False,
              f"{type(e).__name__}: {e}")
    finally:
        (_co.carregar, _aj.carregar, _hc._apurado_do_mes, _tt.carregar,
         _au.eh_dono, _rt.carregar, _fs.carregar, _hc.carregar,
         _hc.carregar_params, _co.carregar_taxas) = _guard


def main():
    instalar()
    falhas = []

    def conta(nome, ok, detalhe):
        if not ok:
            falhas.append((nome, detalhe))
        print(("ok    " if ok else "FALHA ") + nome
              + (f"\n      {detalhe}" if detalhe else ""))

    # AS TELAS GERAIS PRIMEIRO, e isso e de proposito.
    #
    # Os cenarios especificos abaixo trocam funcoes de modulo para forcar o
    # caminho que querem (`_pc._num`, `_ps.ler`, `_pc._buscar_board`), e nem
    # todos devolvem o original. Rodando depois deles, a tela do Financeiro
    # "quebrava" — e passava sozinha. Alarme falso por ordem de execucao e
    # pior que nenhum teste: ensina a ignorar a saida.
    _form_da_equipe(conta)
    _lista_de_finalidades(conta)
    _quebra_do_ml(conta)
    _telas_restantes(conta)
    _fatura_confirmada(conta)
    _fotos_perdidas(conta)
    _refazer_cego(conta)
    _peca_olhada(conta)
    _home(falhas, conta)
    _extratos(conta)
    _gargalos(conta)
    _historico(conta)
    _faturas(conta)
    _queda_de_pontos(conta)
    _mapa_de_pontos(conta)
    _conferencia_de_pontos(conta)
    _processar_cards_pts(conta)
    _chat(conta)
    _retrato_no_painel(conta)
    _historico_de_prompts(conta)
    _contexto_do_log(conta)
    _txt_consolidado(conta)
    _contribuicao_coletiva(conta)
    _excluir_usuario(conta)
    _remocao_a_vista(conta)
    _lucro_liquido_custo_fixo(conta)
    _balanco_headcount(conta)
    print(f"\n{'ok    a tela monta' if not falhas else 'FALHA'} "
          f"· {len(falhas)} tela(s) quebrada(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
