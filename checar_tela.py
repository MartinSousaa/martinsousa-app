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
        # E QUEM ESTAVA ABERTO NA HORA. Sem isto, "o campo existe" e "o campo
        # esta no cabecalho" sao a mesma resposta — e foi assim que uma guarda
        # minha ficou verde com o defeito de volta.
        for _c in _PILHA_DE_CONTAINERS:
            try:
                _c.dentro.add(k)
            except Exception:
                pass

    def __getattr__(self, nome):
        def _qualquer(*a, **kw):
            self._registra(nome, kw)
            # O WIDGET COM `key` DEVOLVE O QUE ESTA NO ESTADO, como no
            # Streamlit de verdade: la, `st.text_input(key="x")` devolve
            # `session_state["x"]` quando ele ja existe, e o `value=` so vale
            # na primeira vez.
            #
            # O duplo devolvia "" sempre. Resultado: nenhuma guarda conseguia
            # montar a tela COM produto preenchido — e e justamente esse o
            # estado em que o botao de gerar aparece. A guarda do botao
            # reprovava uma tela que funciona, que e o alarme falso que esta
            # base ja pagou tres vezes.
            _k = kw.get("key")
            if _k is not None and nome in _LEEM_O_ESTADO:
                try:
                    if _k in self.session_state:
                        return self.session_state[_k]
                except Exception:
                    pass
            return _retorno_de(nome, a, kw)
        return _qualquer

    # ── os que precisam devolver coisa específica ────────────────────────
    def columns(self, spec, **kw):
        n = spec if isinstance(spec, int) else len(spec)
        return [_Falso(self._chaves) for _ in range(n)]

    def tabs(self, rotulos, **kw):
        return [_Falso(self._chaves) for _ in rotulos]

    def container(self, *a, **kw):
        # A CHAVE DO CONTAINER TAMBEM ENTRA NO REGISTRO. O Streamlit de
        # verdade recusa duas chaves iguais em qualquer elemento, container
        # incluido (`streamlit/elements/layouts.py`), e e por essa chave que
        # o CSS do Studio acha o botao de limpar o chat. Sem registrar,
        # container repetido passava — e a guarda que procura um bloco
        # desenhado pela chave dele nao tinha onde olhar.
        self._registra("container", kw)
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


# Os conteineres abertos por `with`, do mais antigo ao mais recente. O topo e
# o container ativo — e e nele que a chave desenhada agora e anotada.
_PILHA_DE_CONTAINERS = []


class _Contexto:
    """`st.container()` e `st.expander()`: servem de `with` E de objeto.

    O CONTAINER DO STREAMLIT TEM OS MESMOS METODOS DA TELA. `c = st.container()`
    devolve um DeltaGenerator, e `c.file_uploader(...)` desenha o campo DENTRO
    dele — e que e exatamente como a aba Imagem poe os tres campos de upload no
    cabecalho sem mover o codigo deles de lugar.

    O duplo so sabia ser `with`, e acusou o inocente:

        AttributeError: '_Contexto' object has no attribute 'file_uploader'

    numa tela que funciona. E a terceira vez que isto acontece aqui — o
    `linha_do_mes` mais pobre que a realidade, o `with c1:` que faltava, as
    datas que voltavam `_Falso` — e a licao e sempre a mesma: duplo mais pobre
    que a realidade ensina a ignorar o verificador.

    Delegar para o `_Falso` de dentro tambem mantem o REGISTRO DE CHAVES: um
    widget desenhado por `c.file_uploader(key=...)` entra na mesma conta, e
    chave repetida continua explodindo.
    """

    def __init__(self, valor):
        self.valor = valor
        # As chaves desenhadas ATRAVES deste container (`c.file_uploader(...)`).
        self.dentro = set()

    def __enter__(self):
        # O `with` TAMBEM DIZ ONDE. No Streamlit de verdade, `with c:` troca o
        # container ativo e tudo que for desenhado ali dentro vai para ele —
        # e e assim que a galeria e desenhada no lugar reservado.
        #
        # O duplo so anotava `c.metodo(...)`. Com isso, uma guarda de POSICAO
        # funcionava para os campos de upload (que usam a chamada) e falhava
        # para a galeria (que usa o `with`) — medindo a tecnica, e nao o lugar.
        _PILHA_DE_CONTAINERS.append(self)
        return self.valor

    def __exit__(self, *a):
        if _PILHA_DE_CONTAINERS and _PILHA_DE_CONTAINERS[-1] is self:
            _PILHA_DE_CONTAINERS.pop()
        return False

    def __getattr__(self, nome):
        _dentro = object.__getattribute__(self, "valor")
        _meus = object.__getattribute__(self, "dentro")

        def _anotando(*a, **kw):
            # QUEM DESENHOU ONDE. Sem isto o duplo so sabe dizer que a chave
            # existe — e "o campo existe" nao e a mesma pergunta que "o campo
            # esta no cabecalho". Foi assim que uma guarda minha ficou verde
            # com o defeito de volta: tirar o campo do cabecalho e desenha-lo
            # no fim da pagina registra a MESMA chave.
            if kw.get("key") is not None:
                _meus.add(kw["key"])
            return getattr(_dentro, nome)(*a, **kw)

        return _anotando if callable(getattr(_dentro, nome, None)) else getattr(
            _dentro, nome)


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


# Os widgets cujo valor o Streamlit de verdade le do `session_state` quando a
# chave ja existe. Botao e upload ficam de fora: clique nao se guarda no
# estado, e arquivo nao e serializavel.
_LEEM_O_ESTADO = ("text_input", "text_area", "selectbox", "radio",
                  "multiselect", "number_input", "slider", "checkbox",
                  "toggle", "date_input", "time_input", "segmented_control")


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


def _aba_faturas(conta):
    """A aba Faturas (06/10): anexar e ver o cartão do mês, com e sem compras.

    Só a leitura da planilha é trocada: `do_mes` recebe a lista e roda de
    verdade (mês do vencimento, cadastro de fora)."""
    import extratos_tela as et
    import lancamentos as _lan
    _base = [
        {"id": "p", "conta": "inter", "data": "2026-10-01", "valor": -80.94,
         "finalidade": "FATURA DO CARTÃO", "descricao": "DEB AUT FATURA",
         "tipo": "", "favorecido": "", "fixada": ""},
        {"id": "a", "conta": _lan.CONTA_CARTAO + "out.csv",
         "data": "2026-03-17", "valor": -73.99, "finalidade": "MERCADORIA",
         "descricao": "ML · Parcela 7/10", "tipo": "fatura 2026-10",
         "favorecido": "ML", "fixada": ""},
    ]
    _g = _lan.do_mes
    for nome, lista in (("Faturas: mês com compras lançadas", _base),
                        ("Faturas: mês só com o pagamento", _base[:1]),
                        ("Faturas: mês vazio", [])):
        _lan.do_mes = lambda a, m, lista_=None, _l=lista: _g(a, m, _l)
        _falso = instalar()
        et.st = _falso
        try:
            et.pagina_faturas("leo")
            conta(nome, True, "")
        except (_Rerun, _Parou):
            conta(nome, True, "")
        except Exception as e:
            conta(nome, False, f"{type(e).__name__}: {e}")
        finally:
            _lan.do_mes = _g

    # E A ABA DO MENU ABRE ESTA TELA, e não o aviso antigo sem campo.
    import gestao as _ge
    _abertas = []
    _gp = et.pagina_faturas
    et.pagina_faturas = lambda u=None: _abertas.append(u)
    try:
        _ge._faturas("leo")
    except Exception:
        pass
    finally:
        et.pagina_faturas = _gp
    conta("a aba Faturas do menu abre a tela de anexar", _abertas == ["leo"],
          "o menu continua mostrando o aviso sem campo de anexar")


def _assinaturas_no_operacional(conta):
    """07/10: Assinaturas mora embaixo do Custo fixo, no pontinho Operacional,
    e deixou de ser pontinho próprio — uma tela, não duas."""
    import gestao as _ge
    _abertas = []
    _g_abrir, _g_pag = _ge._abrir_tela, None
    import custo_fixo as _cf_t
    import auth as _au_t
    _g_pag, _g_dono = _cf_t.pagina, _au_t.eh_dono
    _ge._abrir_tela = lambda m, u=None, f="pagina": _abertas.append(m)
    _cf_t.pagina = lambda u=None, grade=None: _abertas.append("custo_fixo")
    _au_t.eh_dono = lambda u: True
    _g_st = _ge.st
    _ge.st = instalar()
    try:
        _ge._operacional("leo")
    except Exception as e:
        conta("Operacional abre Custo fixo e Assinaturas", False,
              f"{type(e).__name__}: {e}")
    finally:
        _ge._abrir_tela, _cf_t.pagina, _au_t.eh_dono = _g_abrir, _g_pag, _g_dono
        _ge.st = _g_st
    conta("Operacional abre o Custo fixo e, embaixo, as Assinaturas",
          _abertas == ["custo_fixo", "assinaturas_tela"], str(_abertas))
    conta("e Assinaturas não é mais pontinho à parte",
          not any("Assinaturas" in k for k in _ge._PONTINHOS_CUSTO_FIXO), "")
    # 07/10: a legenda do Custo fixo dizia que ele entra no equilíbrio; o
    # equilíbrio passou a ser meta de gastos ÷ lucro bruto. Ele entra no LPV.
    import inspect as _insp_cf
    _src_cf = _insp_cf.getsource(_ge._custo_fixo)
    # 09/10: o título ficou sem legenda ("não quero que os títulos tenham
    # explicações"). A guarda do texto errado continua: nada de "linha de".
    conta("o Custo fixo não volta a dizer que entra no equilíbrio",
          "linha de" not in _src_cf, "")
    conta("e o título do Custo fixo não tem explicação embaixo",
          "st.caption(" not in _src_cf, "")


def _projecao_na_meta(conta):
    """07/10: a projeção de vendas se digita na MESMA tabela da meta de
    gastos, e o Salvar a grava junto (dono: "na mesma tabela o valor da meta
    de gastos e a projeção de vendas para aquele mês")."""
    import inspect as _insp_pj
    import meta_gastos_tela as _mgt
    _src = _insp_pj.getsource(_mgt.pagina)
    conta("a tabela da meta tem a coluna de projeção de vendas",
          '"projeção de vendas": int(' in _src
          and "PROJEÇÃO DE VENDAS — digite aqui" in _src, "")
    conta("e o Salvar grava a projeção junto com a meta",
          "projecao=_proj" in _src and "lpv_projetado.clear()" in _src, "")


def _monique_nos_gestores(conta):
    """07/10: a tela de Folha salarial passa a aba gravada por
    `com_gestores_pedidos` — sem isso a Monique, pedida em 05/10, nunca
    aparecia, porque a aba já tinha Leonardo e Renan."""
    import inspect as _insp_mo
    import folha_salarial as _fs_mo
    _src = _insp_mo.getsource(_fs_mo.pagina)
    conta("a Folha salarial acrescenta os gestores pedidos à aba já gravada",
          "com_gestores_pedidos(df)" in _src
          and _src.index("com_gestores_pedidos(df)") < _src.index("st.data_editor"), "")


def _alerta_de_coluna_na_tv(conta):
    """07/10: o alerta "Coluna sem config" da TV é perguntado sobre as listas
    de AGORA — coluna configurada ou excluída não fica mais nele."""
    import placar as _pl_c
    import placar_core as _pc_c
    import colunas_config as _cc_c
    _g = _cc_c.carregar
    _cc_c.carregar = lambda: {"CORREÇÕES/RETRABALHOS: -30 PONTOS":
                              {"prioridade": 5, "tempo_min": 60}}
    try:
        # `_alertas_tv_list` inteira vai ao Trello; o alerta de coluna é a
        # pergunta a `colunas_sem_config` sobre as listas recebidas.
        import inspect as _insp_c
        _src_al = _insp_c.getsource(_pl_c._alertas_tv_list)
        _listas = {"l1": "CORREÇÕES/RETRABALHOS:  -30 PONTOS",
                   "l2": "COLUNA NOVA XYZ"}
        _cols = _pc_c.colunas_sem_config(sorted(set(_listas.values())))
        conta("TV: coluna configurada sai do alerta, coluna nova entra",
              _cols == ["COLUNA NOVA XYZ"]
              and "colunas_sem_config(sorted(set(listas.values())))" in _src_al,
              str(_cols))
        # 07/10: cada volta da TV esquece as metas guardadas (outro processo)
        import metas_config as _mc_r
        _lim = []
        _g_r = _mc_r.carregar_todas

        class _Limpa:
            def clear(self):
                _lim.append(1)
        _mc_r.carregar_todas = _Limpa()
        try:
            _pl_c._tv_reler_config()
        finally:
            _mc_r.carregar_todas = _g_r
        conta("a TV esquece as metas guardadas antes de cada volta", _lim == [1],
              str(_lim))
        # e a medição de um cartão só continua de pé, pelas ações dadas
        _min, _quem = _pc_c.tempo_execucao_min("c1", {"c1": []})
        conta("tempo_execucao_min sem ações devolve zero", _min == 0.0, str(_min))
    except Exception as e:
        conta("TV: alerta de coluna", False, f"{type(e).__name__}: {e}")
    finally:
        _cc_c.carregar = _g


def _finalidades_em_massa(conta):
    """07/10: a lista de Finalidades usa a tabela em massa — sem ADS
    pré-selecionado, todos os nomes, cada compra embaixo."""
    import finalidades_tela as _ft
    import extratos_tela as _et_f
    import favorecidos as _fv_f
    import lancamentos as _lan_f
    _g = (_fv_f.carregar, _lan_f.carregar, _et_f._fixos_cadastrados)
    _fv_f.carregar = lambda *a, **k: {}
    _lan_f.carregar = lambda: [
        {"id": "1", "data": "2026-09-10", "descricao": "HERING 04/06",
         "valor": -81.69, "conta": "cartão · a.csv", "favorecido": "",
         "finalidade": "", "fixada": "", "tipo": ""}]
    _et_f._fixos_cadastrados = lambda: ([], [])
    _falso = instalar()
    _ft.st = _falso
    _et_f.st = _falso
    try:
        _ft.pagina("leo")
        conta("Finalidades: a fila desenha como tabela em massa", True, "")
    except (_Rerun, _Parou):
        conta("Finalidades: a fila desenha como tabela em massa", True, "")
    except Exception as e:
        conta("Finalidades: a fila desenha como tabela em massa", False,
              f"{type(e).__name__}: {e}")
    finally:
        _fv_f.carregar, _lan_f.carregar, _et_f._fixos_cadastrados = _g
    # E A TABELA QUE CHEGA AO EDITOR (07/10): uma compra por linha, com o
    # valor dela, e nenhuma coluna de soma — "somadas em uma só eu não vou
    # conseguir identificar".
    _vistos_ed = []
    _g2 = (_fv_f.carregar, _lan_f.carregar, _et_f._fixos_cadastrados)
    _fv_f.carregar = lambda *a, **k: {}
    _lan_f.carregar = lambda: [
        {"id": "1", "data": "2026-09-10", "descricao": "HERING 04/06",
         "valor": -81.69, "conta": "cartão · a.csv", "favorecido": "",
         "finalidade": "", "fixada": "", "tipo": ""},
        {"id": "2", "data": "2026-10-10", "descricao": "HERING 05/06",
         "valor": -81.69, "conta": "cartão · b.csv", "favorecido": "",
         "finalidade": "", "fixada": "", "tipo": ""}]
    _et_f._fixos_cadastrados = lambda: ([], [])
    _falso2 = instalar()
    _falso2.data_editor = lambda *a, **k: _vistos_ed.append(a[0]) or a[0]
    _ft.st = _falso2
    _et_f.st = _falso2
    try:
        _ft.pagina("leo")
    except Exception:
        pass
    finally:
        _fv_f.carregar, _lan_f.carregar, _et_f._fixos_cadastrados = _g2
    _df_ed = _vistos_ed[0] if _vistos_ed else None
    _ok_ed = (_df_ed is not None and "total" not in _df_ed.columns
              and list(_df_ed["valor"]) == [81.69]
              and list(_df_ed["preenche junto"]) == [1])
    conta("Finalidades: a linha mostra a parcela, e não a soma das compras",
          _ok_ed, f"colunas: {list(_df_ed.columns) if _df_ed is not None else None}")
    import inspect as _insp_ft
    _src = _insp_ft.getsource(_ft.pagina)
    conta("e não tem mais o selectbox de ADS linha a linha",
          "_et._perguntar(fila" in _src and "fila[:20]" not in _src, "")


def _resumo_mensal(conta):
    """07/10: a aba Resumo Mensal desenha com e sem lançamentos.

    Só a planilha é trocada: `itens_pagos`, `montar` e `itens_provisionados`
    rodam de verdade sobre a forma que `lancamentos.do_mes` devolve."""
    import resumo_mensal as _rm
    import lancamentos as _lan_r
    import assinaturas as _as_r
    import previsto as _pv_r
    import custo_real as _cr_r
    import custo_fixo as _cf_r
    import ajustes as _aj_r
    import pandas as _pd_r
    _lista = [
        {"id": "1", "conta": "itau", "data": "2026-10-05", "valor": -3000.0,
         "finalidade": "CUSTO FIXO", "descricao": "PIX ALUGUEL",
         "favorecido": "IMOB", "tipo": "", "fixada": ""},
        {"id": "2", "conta": _lan_r.CONTA_CARTAO + "inter", "data": "2026-10-06",
         "valor": -550.0, "finalidade": "CUSTO FIXO",
         "descricao": "CLAUDE.AI", "favorecido": "", "tipo": "fatura 2026-10",
         "fixada": ""},
    ]
    _g = (_lan_r.do_mes, _as_r.carregar, _pv_r.do_mes, _cr_r.carregar,
          _cf_r.carregar, _aj_r.carregar)
    _as_r.carregar = lambda: [{"item": "Claude", "valor_mensal": 550.0,
                               "periodicidade": "Mensal", "favorecido": ""}]
    _pv_r.do_mes = lambda a, m: ({"CUSTO FIXO": 3500.0, "FOLHA": 9000.0}, [])
    _cr_r.carregar = lambda: {}
    _cf_r.carregar = lambda aba: _pd_r.DataFrame(
        [{"item": "Aluguel", "valor_mensal": 3000.0, "vigente_desde": "2026-01",
          "dia_debito": 5, "forma_pagamento": "PIX", "favorecido": "IMOB"}])
    _aj_r.carregar = lambda: _pd_r.DataFrame()
    try:
        for nome, lista in (("Resumo Mensal: mês com lançamentos", _lista),
                            ("Resumo Mensal: mês vazio", [])):
            _lan_r.do_mes = lambda a, m, lista_=None, _l=lista: _g[0](a, m, _l)
            _falso = instalar()
            _rm.st = _falso
            try:
                _rm.pagina("leo")
                conta(nome, True, "")
            except (_Rerun, _Parou):
                conta(nome, True, "")
            except Exception as e:
                conta(nome, False, f"{type(e).__name__}: {e}")
        # 20/10: CADA QUADRO ABRE O SEU — saídas e provisionado daquele
        # quadro. O clique em «Custo fixo» abre a janela com o Aluguel.
        _lan_r.do_mes = lambda a, m, lista_=None, _l=_lista: _g[0](a, m, _l)
        _falso = instalar()
        _tabs_q, _botoes_q = [], []
        _falso.selectbox = lambda rot, opcoes, index=0, **k: list(opcoes)[index]
        _falso.dialog = lambda *a, **k: (lambda fn: fn)
        _falso.dataframe = lambda d, *a, **k: _tabs_q.append(d)
        _falso.columns = lambda spec, **k: [_falso] * (spec if isinstance(spec, int) else len(spec))
        _falso.button = lambda rot, *a, **k: (_botoes_q.append(k.get("key")),
                                              k.get("key") == "rm_q_Custo fixo")[1]
        _rm.st = _falso
        try:
            _rm.pagina("leo")
            _itens = [list(d["item"]) for d in _tabs_q if hasattr(d, "columns") and "item" in d.columns
                      and "situação" in d.columns and "valor" in d.columns]
            conta("Resumo Mensal: cada quadro tem o seu botão, e Custo fixo abre saídas e provisionado dele",
                  len([b for b in _botoes_q if str(b).startswith("rm_q_")]) == len(_rm.QUADROS)
                  and ["Aluguel"] in _itens, f"botões {len(_botoes_q)} · provisionado {_itens}")
        except (_Rerun, _Parou):
            conta("Resumo Mensal: quadro aberto", True, "")
        except Exception as e:
            conta("Resumo Mensal: quadro aberto", False, f"{type(e).__name__}: {e}")
    finally:
        (_lan_r.do_mes, _as_r.carregar, _pv_r.do_mes, _cr_r.carregar,
         _cf_r.carregar, _aj_r.carregar) = _g
    import gestao as _ge_r
    _abas = list(_ge_r.SUBTELAS)
    conta("Resumo Mensal vem antes de Custos fixos no Financeiro",
          _abas[:2] == ["📊 Resumo Mensal", "🧱 Custos fixos"],
          f"ordem das abas: {_abas[:3]}")


def _salvar_metas(conta):
    """07/10: a meta de 11.000 / +25% nunca chegou à TV. A gravação recusada
    mostrava erro, a tela mostrava "salva com sucesso" e o st.rerun() apagava
    os dois. Aqui o formulário roda de verdade com o Salvar clicado; só a
    planilha (salvar e reler) é trocada."""
    global _retorno_de
    # O `@st.fragment` do Painel de Metas roda no IMPORT e o duplo não é
    # chamável: o import se faz com o Streamlit de verdade (nada desenha nem
    # vai à rede no import), e o duplo volta logo depois.
    if "analise_metas" not in sys.modules:
        import importlib as _il_s
        _dbl_s = sys.modules.pop("streamlit", None)
        try:
            _il_s.import_module("streamlit")
            import analise_metas  # noqa: F401
        finally:
            if _dbl_s is not None:
                sys.modules["streamlit"] = _dbl_s
    import analise_metas as _am_s
    import metas_config as _mc_s
    _g = (_mc_s.salvar_config, _mc_s.conferir_gravado, _mc_s.carregar_config,
          _retorno_de)
    _cfg9 = {**_mc_s.DEFAULTS, "meta_equipe": 9000, "ano": 2026, "mes": 10}
    _mc_s.carregar_config = lambda a, m: dict(_cfg9)

    def rodar(salvar, conferir, clicou=True, digitado=None):
        visto = []
        _falso = instalar()
        _am_s.st = _falso
        _falso.form_submit_button = lambda *a, **k: clicou
        _falso.error = lambda *a, **k: visto.append("error")
        _falso.success = lambda *a, **k: visto.append("success")
        _falso.warning = lambda *a, **k: visto.append(
            "nao_salvo" if "Não salvo" in str(a[0] if a else "") else "warning")

        def _rr(*a, **k):
            visto.append("rerun")
            raise _Rerun()
        _falso.rerun = _rr
        _mc_s.salvar_config = salvar
        _mc_s.conferir_gravado = conferir
        if digitado is not None:
            # O que a pessoa digitou e o formulário guardou depois de um
            # Salvar que falhou: o campo devolve isso, e não o gravado.
            def _ret(nome, a, kw, _orig=_g[3]):
                if nome == "number_input" and "cfg_meta_equipe" in str(kw.get("key")):
                    return digitado
                return _orig(nome, a, kw)
            globals()["_retorno_de"] = _ret
        try:
            _am_s._secao_configuracao([], None)
        except (_Rerun, _Parou):
            pass
        finally:
            globals()["_retorno_de"] = _g[3]
        return visto, _falso

    try:
        v, _ = rodar(lambda a, m, d: (False, "APIError: [429]"), lambda *a: [])
        conta("Metas: gravação recusada mostra NÃO SALVOU e não apaga",
              "error" in v and "success" not in v and "rerun" not in v,
              f"visto: {v}")
        v, _ = rodar(lambda a, m, d: (True, ""),
                     lambda a, m, d: [("meta_equipe", 11000, 9000)])
        conta("Metas: gravou diferente do que está na tela, e a tela diz",
              "error" in v and "rerun" not in v, f"visto: {v}")
        v, f = rodar(lambda a, m, d: (True, ""), lambda a, m, d: [])
        conta("Metas: só diz salvo depois de reler, e o aviso sobrevive ao rerun",
              v == ["rerun"] and any(str(k).startswith("_cfg_salva_")
                                     for k in f.session_state), f"visto: {v}")
        v, _ = rodar(lambda a, m, d: (True, ""), lambda a, m, d: [],
                     clicou=False, digitado=11000)
        conta("Metas: campo diferente do gravado avisa «Não salvo»",
              "nao_salvo" in v, f"visto: {v}")
        v, _ = rodar(lambda a, m, d: (True, ""), lambda a, m, d: [],
                     clicou=False)
        conta("Metas: campo igual ao gravado não avisa nada",
              "nao_salvo" not in v, f"visto: {v}")
    finally:
        (_mc_s.salvar_config, _mc_s.conferir_gravado, _mc_s.carregar_config,
         _retorno_de) = _g


def _devolucoes_da_planilha(conta):
    """09/10: as devoluções vêm da planilha; o Studio só acompanha.

    Só a leitura é trocada: `do_controle_ms` devolve linhas na forma dele
    (`normalizar`), e `juntar_fontes` roda de verdade."""
    import devolucoes as _dv_d
    import devolucoes_tela as _dvt_d
    _p = _dv_d.normalizar({"data_solic": "2026-09-10", "pedido": "111",
                           "produto": "Caneca", "valor": 50.0,
                           "situacao": "RECORRENDO"})
    _so = _dv_d.normalizar({"data_solic": "2026-08-01", "pedido": "9",
                            "produto": "Só no Studio", "valor": 10.0})
    _g = (_dv_d.do_controle_ms, _dv_d._do_studio, _dv_d.carregar_tudo)
    _dv_d.do_controle_ms = lambda limite=None: ([_p], [])
    _dv_d._do_studio = lambda: [_so]
    _dv_d.carregar_tudo = lambda: (lambda l, s: (l, s, []))(
        *_dv_d.juntar_fontes(*([_p], [_so])))
    _vistos = []
    _falso = instalar()
    _falso.data_editor = lambda *a, **k: _vistos.append("editor") or (a[0] if a else None)
    _falso.form = lambda *a, **k: _vistos.append("form") or _falso
    _dvt_d.st = _falso
    try:
        _dvt_d.pagina("leo")
        conta("Devoluções: a tela monta com a planilha como fonte", True, "")
    except (_Rerun, _Parou):
        conta("Devoluções: a tela monta com a planilha como fonte", True, "")
    except Exception as e:
        conta("Devoluções: a tela monta com a planilha como fonte", False,
              f"{type(e).__name__}: {e}")
    finally:
        _dv_d.do_controle_ms, _dv_d._do_studio, _dv_d.carregar_tudo = _g
    conta("Devoluções: sem cadastro nem edição no Studio — a planilha edita",
          "editor" not in _vistos and "form" not in _vistos
          and not hasattr(_dvt_d, "_nova") and not hasattr(_dvt_d, "_importar"),
          f"visto: {_vistos}")


def _equilibrio_real_na_meta(conta):
    """09/10: o equilíbrio real aparece só para os meses fechados.

    `linhas` na forma de `meta_gastos.ano_inteiro`; o mapa na forma de
    `base_vendas.somas_por_mes`. Só a leitura da planilha é trocada."""
    import meta_gastos_tela as _mgt_e
    import base_vendas as _bv_e
    from datetime import date as _d_e

    def _mes(fat, lb):
        d = {k: 0.0 for k in _bv_e.COLUNAS}
        d.update({"faturamento": fat, "fat_liquido": fat, "lucro_bruto": lb,
                  "linhas": 5})
        return d
    _mapa = {(2026, m): _mes(200000, 60000) for m in range(6, 11)}
    _linhas = [{"mes": f"2026-{m:02d}", "rotulo": f"mes{m} 2026",
                "meta": 60000.0 if m in (9, 10) else 0.0,
                "realizado": 66000.0, "origem": "extrato"}
               for m in range(1, 13)]
    _g = _bv_e.somas_por_mes
    _bv_e.somas_por_mes = lambda: (_mapa, "")
    _tabelas = []
    _falso = instalar()
    _falso.dataframe = lambda d, *a, **k: _tabelas.append(d)
    _mgt_e.st = _falso
    try:
        _mgt_e._equilibrio_real(2026, _d_e(2026, 10, 9), _linhas)
        _df = _tabelas[-1] if _tabelas else None
        _meses = list(_df["mês"]) if _df is not None else []
        # 10/10: mês SEM META também entra — o equilíbrio real não depende
        # dela. Esta guarda exigia o contrário (só Mes9, o único com meta) e
        # travou o defeito: o bloco sumia para quem não digitou meta.
        conta("Meta de gastos: equilíbrio real em TODO mês fechado com gasto",
              _meses == [f"{_n}/2026" for _n in ("Janeiro", "Fevereiro", "Março",
                                                "Abril", "Maio", "Junho",
                                                "Julho", "Agosto",
                                                "Setembro")], f"meses: {_meses}")
        _r = dict(zip(_meses, list(_df["resultado"]))) if _df is not None else {}
        conta("e o resultado é faturado líquido − gasto ÷ lucro bruto do mês",
              _r.get("Setembro/2026") == 200000 - 220000.0
              and _r.get("Agosto/2026") == 200000 - 220000.0, str(_r))
        _sit = dict(zip(_meses, list(_df["situação"]))) if _df is not None else {}
        _plan = (dict(zip(_meses, list(_df["equilíbrio planejado"])))
                 if _df is not None else {})
        conta("mês sem meta diz que não tem meta, e fica sem planejado",
              "sem meta" in str(_sit.get("Agosto/2026"))
              and "sem meta" not in str(_sit.get("Setembro/2026"))
              and _plan.get("Agosto/2026") != _plan.get("Agosto/2026")  # NaN
              and _plan.get("Setembro/2026") > 0, str(_sit))
    except Exception as e:
        conta("Meta de gastos: equilíbrio real só nos meses fechados", False,
              f"{type(e).__name__}: {e}")
    finally:
        _bv_e.somas_por_mes = _g


def _acompanhamento_do_mes(conta):
    """09/10: o mês em andamento ganha o projetado × real, embaixo da meta.

    Só a margem (BASE DE VENDAS) e o faturado (Bling) são trocados."""
    import meta_gastos_tela as _mgt_a
    import base_vendas as _bv_a
    import home_gestao as _hg_a
    from datetime import date as _d_a
    _g = (_bv_a.media_recente, _hg_a._faturamento_bling)
    _bv_a.media_recente = lambda a, m, quantos=3: ({"margem_bruta": 30.0}, "")
    _hg_a._faturamento_bling = lambda a, m: (90000.0, [])
    _vistos = {"grafico": None, "frase": ""}
    _falso = instalar()
    _falso.bar_chart = lambda d, *a, **k: _vistos.update(grafico=d)
    _falso.success = lambda t, *a, **k: _vistos.update(frase=str(t))
    _falso.warning = lambda t, *a, **k: _vistos.update(frase=str(t))
    _mgt_a.st = _falso
    _hoje = _d_a.today()
    try:
        _mgt_a._acompanhar_mes(_hoje.year, _hoje, 60000.0, 75000.0)
        _df = _vistos["grafico"]
        conta("Meta de gastos: o mês em andamento desenha projetado × real",
              _df is not None and list(_df.index) == ["Gastos do mês",
                                                      "Equilíbrio do mês",
                                                      "Faturamento até hoje"]
              and list(_df.columns) == ["Projetado", "Real"]
              and list(_df.loc["Equilíbrio do mês"]) == [200000.0, 250000.0],
              str(_df))
        conta("e diz onde o mês fecha no ritmo de hoje",
              "No ritmo de hoje o mês fecha em" in _vistos["frase"]
              and "250.000,00" in _vistos["frase"], _vistos["frase"][:120])
        _vistos["grafico"] = None
        _mgt_a._acompanhar_mes(_hoje.year - 1, _hoje, 60000.0, 75000.0)
        conta("e ano que não é o corrente não ganha acompanhamento",
              _vistos["grafico"] is None, "")
        # A página passa o COMPROMETIDO (já saiu + provisionado), e não só o
        # que já saiu: "tem que considerar tudo que já está provisionado".
        import inspect as _insp_a
        conta("e a página entrega o comprometido, com o provisionado dentro",
              '_acompanhar_mes(ano, hoje, atual["meta"], _comp)'
              in _insp_a.getsource(_mgt_a.pagina), "")
    except Exception as e:
        conta("Meta de gastos: o mês em andamento desenha projetado × real",
              False, f"{type(e).__name__}: {e}")
    finally:
        _bv_a.media_recente, _hg_a._faturamento_bling = _g


def _inter_pela_api(conta):
    """09/10: o extrato do Inter pela API — mostra antes de gravar.

    Só a rede é trocada: `buscar` devolve linhas na forma de `ler`, e o que
    já está gravado vem na forma de `lancamentos.carregar`."""
    import extratos_tela as _et_i
    import extrato_inter_api as _api_i
    import lancamentos as _lan_i
    from datetime import date as _d_i
    _da_api = [{"data": _d_i(2026, 10, 8), "descricao": "Pix enviado: X",
                "favorecido": "X", "valor": -100.0, "sentido": "saida"},
               {"data": _d_i(2026, 10, 9), "descricao": "Pix enviado: Y",
                "favorecido": "Y", "valor": -40.0, "sentido": "saida"}]
    _g = (_api_i.configuradas, _api_i.buscar, _lan_i.carregar, _lan_i.gravar)
    _gravou, _tabelas = [], []
    _api_i.configuradas = lambda ambiente=None: [("LG", "INTER", "inter-1")]
    _api_i.buscar = lambda pref, a, b: (list(_da_api), "")
    _lan_i.carregar = lambda: [{"conta": "inter-1", "data": "2026-10-08",
                                "valor": -100.0, "descricao": "do CSV"}]
    _lan_i.gravar = lambda *a, **k: _gravou.append(a) or (1, 0, "")
    _falso = instalar()
    _falso.button = lambda rot, *a, **k: k.get("key") == "api_inter_buscar"
    _falso.dataframe = lambda d, *a, **k: _tabelas.append(d)
    _et_i.st = _falso
    try:
        _et_i._buscar_inter("leo")
        conta("Inter pela API: mostra só o que ainda não está gravado",
              len(_tabelas) == 1 and [r["valor"] for r in _tabelas[0]] == [-40.0],
              str(_tabelas))
        conta("e não grava nada sem o clique em Gravar", _gravou == [],
              str(_gravou))
    except Exception as e:
        conta("Inter pela API: mostra só o que ainda não está gravado", False,
              f"{type(e).__name__}: {e}")
    finally:
        (_api_i.configuradas, _api_i.buscar, _lan_i.carregar,
         _lan_i.gravar) = _g


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
                 or _falso_f.session_state.get("img_pedido_de_pecas"))
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
    _falso_g.session_state["img_pedido_de_pecas"] = {"tipos": list(_duas_g),
                                                     "descricao": ""}
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
          "img_pedido_de_pecas" not in _falso_g.session_state,
          "o pedido ficou guardado: a cada passada a tela volta para o modo "
          "Selecionar, e o colaborador não consegue sair dele")

    # ── UMA PECA SO, QUE E O PEDIDO DO DIA A DIA (23/10) ────────────────
    #
    # Dono: *"Ele nao ira gerar as 8 imagens de uma vez, somente conforme eles
    # forem pedindo"*. Com um tipo, a aba abre em "1 imagem especifica" — e a
    # descricao tem de cair na chave DAQUELE tipo (`img_instr_<tipo>`), que e
    # de onde a tela a le. Numa chave propria o campo mostraria o preset
    # enquanto o motor recebia outra coisa.
    #
    # E TUDO ISSO E ESCRITA EM CHAVE DE WIDGET: so e legal aqui, no topo da
    # pagina, antes de o widget nascer. E por isso que a guarda desenha a
    # tela em vez de chamar a funcao.
    _falso_u = instalar()
    for _nm_u, _mod_u in list(_sys_f.modules.items()):
        if getattr(_mod_u, "st", None) is not None and not _nm_u.startswith(
                ("streamlit", "checar_")):
            try:
                _mod_u.st = _falso_u
            except Exception:
                pass
    _um_u = _img_f.TIPOS_PADRAO[2]
    _falso_u.session_state["img_pedido_de_pecas"] = {
        "tipos": [_um_u], "descricao": "varal com 6 prendedores, bem clara"}
    _erro_u = ""
    try:
        _img_f.pagina_imagem("myrelladesouza")
    except (_Rerun, _Parou):
        pass
    except Exception as e:
        _erro_u = f"{type(e).__name__}: {str(e)[:160]}"
    conta("pedir UMA peca pelo chat nao derruba a aba",
          _erro_u == "", _erro_u)
    conta("e a aba abre no modo de UMA imagem, no tipo pedido",
          _falso_u.session_state.get("img_modo") == "1 imagem específica"
          and _falso_u.session_state.get("img_tipo_unico") == _um_u,
          f"abriu em {_falso_u.session_state.get('img_modo')!r} com "
          f"{_falso_u.session_state.get('img_tipo_unico')!r}")
    conta("e a descricao cai na chave daquele tipo, que e a que a tela le",
          _falso_u.session_state.get(f"img_instr_{_um_u}")
          == "varal com 6 prendedores, bem clara",
          "a descricao foi para outro lugar: o campo da tela mostraria o "
          "preset enquanto o motor recebia outra coisa")
    conta("e o pedido de uma peca tambem e consumido",
          "img_pedido_de_pecas" not in _falso_u.session_state,
          "o pedido ficou: a cada passada a tela volta para o tipo pedido")

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


def _novo_produto(conta):
    """O botao "Novo produto" zera a aba — e NAO descarta geracao paga calado.

    Pedido do dono, 23/10: *"Então coloque um botão como 'Novo Produto'"*, e
    *"Zera tudo sim"*. O "Limpar Chat" que ja existia nao servia: ele preserva
    galeria, fotos e nome do produto de proposito (`chat_assistente.py:1362`).

    POR QUE ESTA GUARDA DESENHA A TELA E NAO SO CHAMA A FUNCAO
    ---------------------------------------------------------
    Tres dos defeitos possiveis aqui nao aparecem chamando a funcao sozinha:

    1. O campo de upload NAO esvazia por `session_state` — a lista de arquivos
       mora no navegador. So mudar a CHAVE do widget solta o que esta
       pendurado, e isso so se mede desenhando a tela duas vezes e comparando
       as chaves registradas.
    2. `contexto_produto.semear` repoe o nome do produto em todo campo vazio.
       Sem `esquecer()`, o campo volta preenchido na passada seguinte ao
       clique e o botao parece nao funcionar.
    3. O disco. `app.py:1532` chama `rascunho.restaurar` em toda sessao.

    E a quarta assercao e a que protege o trabalho: com a galeria fora do
    Drive, o clique PERGUNTA em vez de zerar.
    """
    import importlib
    import shutil as _sh_np
    import sys as _sys_np
    import tempfile as _tmp_np

    import rascunho as _rasc_np

    _base = _tmp_np.mkdtemp()
    _pasta_real = _rasc_np._pasta
    _rasc_np._pasta = lambda u, _b=_base: os.path.join(_b, str(u))
    _sh, _guardado = _sem_planilha()
    _button_real = getattr(_Falso, "button", None)

    def _troca_st(falso):
        for _nm, _mod in list(_sys_np.modules.items()):
            if getattr(_mod, "st", None) is not None and not _nm.startswith(
                    ("streamlit", "checar_")):
                try:
                    _mod.st = falso
                except Exception:
                    pass

    try:
        _falso = instalar()
        _m = importlib.import_module("imagem")
        _troca_st(_falso)
        try:
            _m.pagina_imagem("martinsousa")
        except (_Rerun, _Parou):
            pass
        except Exception as e:
            conta("a aba Imagem monta com o botao Novo produto", False,
                  f"{type(e).__name__}: {str(e)[:160]}")
            return
        conta("a aba Imagem desenha o botao Novo produto",
              "btn_novo_produto" in _falso._chaves,
              "o botao nao foi desenhado — nao ha como comecar outro produto")

        # ── O ESTADO DE QUEM ESTAVA NO MEIO DE UM PRODUTO ───────────────
        _PNG = b"\x89PNG\r\n\x1a\n" + b"w" * 2000
        _rasc_np.salvar_fotos("martinsousa", [_PNG], ["frente.png"])
        _rasc_np.salvar("martinsousa", "Urso Prata",
                        [{"tipo": "1 — capa", "bytes": _PNG}], "MS-URSO-1")
        _rasc_np.salvar_trabalho("martinsousa",
                                 {"img_nome_produto": "Urso Prata",
                                  "img_codigo": "MS-URSO-1"})
        _f2 = instalar()
        _troca_st(_f2)
        _f2.session_state.update({
            "img_nome_produto_input": "Urso Prata",
            "img_codigo_input": "MS-URSO-1",
            "img_galeria": [{"tipo": "1 — capa", "bytes": _PNG}],
            "img_triagem_config": {"nome_produto": "Urso Prata"},
            "ctx_produto_nome": "Urso Prata",
            "ctx_produto_codigo": "MS-URSO-1",
            "ms_chat_hist": [{"role": "user", "content": "gera a capa"}],
            "chat_refazer_imagem": {"num": 3},
            "img_upload_versao": 2,
        })
        _saiu = _m.limpar_tudo_do_produto("martinsousa")

        _sobrou = [k for k in dict(_f2.session_state)
                   if str(k).startswith("img_") and k != "img_upload_versao"]
        conta("zerar o produto nao deixa nenhuma chave `img_` para tras",
              _sobrou == [], f"sobrou: {_sobrou[:6]}")
        conta("e leva o produto COMPARTILHADO entre as abas",
              not dict(_f2.session_state).get("ctx_produto_nome")
              and not dict(_f2.session_state).get("ctx_produto_codigo"),
              "`ctx_produto_nome` ficou — `semear` repoe o nome no campo na "
              "passada seguinte, e o botao parece nao funcionar")
        conta("e a conversa", not dict(_f2.session_state).get("ms_chat_hist"),
              "a conversa do produto anterior ficou na tela")
        conta("e o comando de refazer JA ACEITO do produto anterior",
              "chat_refazer_imagem" not in dict(_f2.session_state),
              "um 'refazer a imagem 3' do produto velho executaria contra o "
              "produto que acabou de entrar")
        conta("e a chave do upload muda, que e o que esvazia o campo",
              _m.versao_dos_uploads() == 3,
              f"a versao ficou em {_m.versao_dos_uploads()} — o campo continua "
              "com as fotos do produto anterior penduradas")
        conta("e o DISCO vai junto: galeria, fotos e trabalho",
              _rasc_np.resumo("martinsousa") is None
              and _rasc_np.carregar_fotos("martinsousa") == []
              and _rasc_np.carregar_trabalho("martinsousa") == {},
              "o produto velho volta no primeiro F5, porque `app.py` chama "
              "`restaurar` em toda sessao")
        conta("e a funcao DIZ o que apagou, em vez de zerar calada",
              "img_galeria" in _saiu and "rascunho" in _saiu,
              f"devolveu {_saiu[:6]}")

        # ── O CLIQUE COM GERACAO FORA DO DRIVE: PERGUNTA, NAO APAGA ─────
        #
        # Esta e a assercao que protege dinheiro. `img_galeria_salva` guarda o
        # TAMANHO salvo, e nao um booleano: salvar 2 de 3 nao e ter salvo.
        def _clica_no_novo_produto(self, *a, **kw):
            self._registra("button", kw)
            return kw.get("key") == "btn_novo_produto"

        _Falso.button = _clica_no_novo_produto
        _f3 = instalar()
        _troca_st(_f3)
        _f3.session_state.update({
            "img_galeria": [{"tipo": "1 — capa", "bytes": _PNG},
                            {"tipo": "2 — detalhe", "bytes": _PNG}],
            "img_galeria_salva": 1,          # uma das duas no Drive
            "img_nome_produto_input": "Urso Prata",
        })
        try:
            _m.pagina_imagem("martinsousa")
        except (_Rerun, _Parou):
            pass
        except Exception:
            pass
        _est3 = dict(_f3.session_state)
        conta("com imagem fora do Drive, o clique PERGUNTA antes de descartar",
              _est3.get("img_novo_produto_confirmar") == 2
              and len(_est3.get("img_galeria") or []) == 2,
              "o botao descartou geracao paga sem perguntar")

        # E com tudo salvo ele zera de uma vez: confirmacao que aparece sempre
        # e confirmacao que ninguem le.
        _f4 = instalar()
        _troca_st(_f4)
        _f4.session_state.update({
            "img_galeria": [{"tipo": "1 — capa", "bytes": _PNG}],
            "img_galeria_salva": 1,
            "img_nome_produto_input": "Urso Prata",
        })
        try:
            _m.pagina_imagem("martinsousa")
        except (_Rerun, _Parou):
            pass
        except Exception:
            pass
        _est4 = dict(_f4.session_state)
        conta("com tudo no Drive, o clique zera sem perguntar",
              not _est4.get("img_galeria")
              and not _est4.get("img_novo_produto_confirmar"),
              "pediu confirmacao sem ter o que perder")
    finally:
        if _button_real is None:
            try:
                del _Falso.button
            except AttributeError:
                pass
        else:
            _Falso.button = _button_real
        _rasc_np._pasta = _pasta_real
        _sh.planilha, _sh.cliente = _guardado
        _sh_np.rmtree(_base, ignore_errors=True)


def _fotos_que_o_chat_nao_via(conta):
    """O refazer pelo chat acha as fotos anexadas — sem geracao nenhuma antes.

    O DEFEITO, EM PRODUCAO, 27/10. O dono anexou tres fotos do produto, pediu
    no chat para refazer a peca 5, e recebeu:

        "Preciso das fotos do produto para refazer do zero. O Studio nao tem
         nenhuma nesta sessao"

    com as tres fotos na tela. A causa: o campo de upload NUNCA escrevia
    `img_fotos_originais` — ela so era preenchida DEPOIS de uma geracao rodar
    neste processo. A aba sabia das fotos; o chat nao. Uma pergunta, duas
    respostas.

    POR QUE ESTA GUARDA DESENHA A TELA
    ----------------------------------
    `fotos_do_produto` tem guarda propria em `imagem.py`, e ela mede as tres
    fontes. Mas o defeito nao estava na porta: estava em NINGUEM GRAVAR o que
    o campo entregou. Isso so aparece desenhando a pagina com fotos no campo
    e perguntando, depois, se o refazer as acha.

    E ela mede A RECUSA, que e o que o dono leu — nao "a funcao devolveu
    alguma coisa". Guarda que confere so que nao explodiu nao ve texto errado.
    """
    import importlib
    import shutil as _sh_fq
    import sys as _sys_fq
    import tempfile as _tmp_fq

    import rascunho as _rasc_fq

    _base = _tmp_fq.mkdtemp()
    _pasta_real = _rasc_fq._pasta
    _rasc_fq._pasta = lambda u, _b=_base: os.path.join(_b, str(u))
    _sh, _guardado = _sem_planilha()
    _revisar_real = None
    _m = None
    try:
        _falso = instalar()
        _m = importlib.import_module("imagem")
        _revisar_real = _m.revisar_anexos
        for _nm, _mod in list(_sys_fq.modules.items()):
            if getattr(_mod, "st", None) is not None and not _nm.startswith(
                    ("streamlit", "checar_")):
                try:
                    _mod.st = _falso
                except Exception:
                    pass

        _PNG = b"\x89PNG\r\n\x1a\n" + b"p" * 2000
        # O CAMPO DE UPLOAD COM TRES FOTOS, como na tela do dono. O duplo nao
        # carrega arquivo; quem devolve os bytes e `revisar_anexos`, que e a
        # porta por onde todo anexo desta aba passa.
        _m.revisar_anexos = lambda up: ([_PNG, _PNG, _PNG],
                                        ["a.png", "b.png", "c.png"], [], [])
        _falso.session_state["img_nome_produto_input"] = "Garrafa Térmica"
        try:
            _m.pagina_imagem("myrelladesouza")
        except (_Rerun, _Parou):
            pass
        except Exception as e:
            conta("a aba monta com as fotos anexadas", False,
                  f"{type(e).__name__}: {str(e)[:160]}")
            return

        # NENHUMA GERACAO RODOU. Era exatamente este o estado que recusava.
        conta("as fotos anexadas viram as fotos da sessao, sem gerar nada",
              len(_m.fotos_do_produto("myrelladesouza")) == 3,
              "o campo entregou tres fotos e o Studio continua sem nenhuma — "
              "e o refazer pelo chat recusa com as fotos na tela")

        # ── E AGORA O CAMINHO INTEIRO: o pedido do chat, desenhado ──────
        #
        # A assercao mede A RECUSA, que e o texto que o dono leu.
        _falso2 = instalar()
        for _nm, _mod in list(_sys_fq.modules.items()):
            if getattr(_mod, "st", None) is not None and not _nm.startswith(
                    ("streamlit", "checar_")):
                try:
                    _mod.st = _falso2
                except Exception:
                    pass
        _m.revisar_anexos = lambda up: ([_PNG, _PNG, _PNG],
                                        ["a.png", "b.png", "c.png"], [], [])
        _rasc_fq.salvar_fotos("myrelladesouza", [_PNG, _PNG, _PNG],
                              ["a.png", "b.png", "c.png"])
        _falso2.session_state.update({
            "img_nome_produto_input": "Garrafa Térmica",
            "img_galeria": [{"tipo": t, "bytes": _PNG}
                            for t in _m.TIPOS_PADRAO[:5]],
            "chat_refazer_imagem": [{"num": 5, "instrucao": "troca a tampa",
                                     "referencia": []}],
        })
        try:
            _m.pagina_imagem("myrelladesouza")
        except (_Rerun, _Parou):
            pass
        except Exception:
            pass
        _falas = [str(f.get("content", "")) for f in
                  (_falso2.session_state.get("ms_chat_hist") or [])]
        conta("e o refazer pelo chat NAO recusa por falta de foto",
              not any("não tem nenhuma nesta sessão" in f for f in _falas),
              "a recusa de 27/10 voltou: o dono anexa as fotos, pede no chat, "
              "e o Studio diz que nao tem foto nenhuma")
    finally:
        if _m is not None and _revisar_real is not None:
            _m.revisar_anexos = _revisar_real
        _rasc_fq._pasta = _pasta_real
        _sh.planilha, _sh.cliente = _guardado
        _sh_fq.rmtree(_base, ignore_errors=True)


def _chat_no_centro(conta):
    """O chat e desenhado no CENTRO da aba Imagem, e so num lugar por passada.

    Dono, 23/10: *"quero que o chat seja central"*, depois de *"O pessoal ainda
    esta com muita dificuldade no Studio, principalmente na criacao das
    imagens"*. A largura explica a dificuldade: a barra lateral tem 284px e o
    centro desta aba tem 1.228px.

    POR QUE A GUARDA DESENHA AS DUAS COISAS
    ---------------------------------------
    O risco nao e o chat nao aparecer — e ele aparecer DUAS vezes. As chaves
    dos widgets dele sao fixas, e a segunda chamada na mesma passada derruba a
    tela com `StreamlitDuplicateElementKey`, que e o erro que ja tirou a tela
    de Extratos do ar. O duplo desta conferencia guarda toda chave e explode
    na repetida, entao desenhar a pagina E o chat na sequencia mede exatamente
    isso.

    E mede tambem o que ninguem lembraria: `_SLOT_DO_CHAT` e global de MODULO,
    e modulo sobrevive entre passadas. Sem o `esquecer` no comeco de cada
    passada, o lugar reservado com a aba Imagem aberta continuaria valendo com
    o colaborador em outra aba.
    """
    import importlib
    import sys as _sys_cc

    _sh, _guardado = _sem_planilha()
    try:
        _falso = instalar()
        _m = importlib.import_module("imagem")
        _ca = importlib.import_module("chat_assistente")
        for _nm, _mod in list(_sys_cc.modules.items()):
            if getattr(_mod, "st", None) is not None and not _nm.startswith(
                    ("streamlit", "checar_")):
                try:
                    _mod.st = _falso
                except Exception:
                    pass

        _m.esquecer_slot_do_chat()
        conta("o lugar do chat comeca vazio em toda passada",
              _m.slot_do_chat() is None,
              "o conteiner da passada anterior continuou valendo")

        # COM PRODUTO PREENCHIDO, que e o estado em que o colaborador
        # trabalha. Com a tela em branco o botao de gerar nao aparece — e
        # nao deve: botao que promete o que nao pode fazer e pior que
        # botao nenhum.
        _falso.session_state["img_nome_produto_input"] = "Prendedor de Roupa"

        _erro = ""
        try:
            _m.pagina_imagem("myrelladesouza")
        except (_Rerun, _Parou):
            pass
        except Exception as e:
            _erro = f"{type(e).__name__}: {str(e)[:160]}"
        conta("a aba Imagem monta com o resumo e o lugar do chat",
              _erro == "", _erro)
        conta("e ela RESERVA o lugar do chat no centro",
              _m.slot_do_chat() is not None,
              "o lugar nao foi reservado: o chat cairia para a barra lateral "
              "de 284px, que e o defeito que isto corrige")

        # O RESUMO DA ESQUERDA FOI DESENHADO, e nao so calculado. A guarda
        # procura o rotulo da secao que o dono pediu.
        conta("e o resumo da esquerda e desenhado",
              "img_resumo_esquerda" in _falso._chaves,
              "a coluna da esquerda saiu vazia")

        # E AGORA O CHAT, dentro do lugar reservado, na MESMA passada. Se
        # alguma chave dele repetir com uma da pagina, o duplo explode aqui.
        _erro_ch = ""
        try:
            with _m.slot_do_chat():
                _ca.renderizar_chat("myrelladesouza")
        except (_Rerun, _Parou):
            pass
        except Exception as e:
            _erro_ch = f"{type(e).__name__}: {str(e)[:200]}"
        conta("o chat desenha dentro do lugar reservado, sem chave repetida",
              _erro_ch == "",
              f"{_erro_ch} — e o erro que tira a tela do ar quando o mesmo "
              "widget e desenhado duas vezes na mesma passada")

        # ── O QUE O DONO COBROU DEPOIS DE VER A TELA (23/10) ────────────
        #
        # O print dele mostrava: os tres uploads la embaixo, o formulario
        # inteiro na frente, o diagnostico abrindo a pagina e um buraco cinza
        # de 800px no lugar da conversa. Cada linha abaixo mede UMA dessas.
        #
        # Elas procuram a CHAVE do widget, nunca o texto do rotulo: travar a
        # frase e a Forma 2, e tres guardas desta base ja nasceram assim.
        # ONDE, e nao SE. A primeira versao desta guarda conferia que as tres
        # chaves existiam — e elas existem nos dois casos, porque o campo
        # desenhado no fim da pagina registra a mesma chave. Ela ficou verde
        # com o defeito de volta, e o `checar_mutacao` cobrou.
        _no_cabecalho = set()
        for _slot in (_m.slot_das_fotos(), _m.slot_da_ambientacao(),
                      _m.slot_do_layout()):
            _no_cabecalho |= getattr(_slot, "dentro", set())
        _v = _m.versao_dos_uploads()
        conta("os tres campos de imagem sao desenhados NO CABECALHO",
              all(k in _no_cabecalho for k in
                  (f"img_fotos_upload_{_v}", f"img_refs_amb_upload_{_v}",
                   f"img_refs_layout_upload_{_v}")),
              f"no cabecalho foram desenhados {sorted(_no_cabecalho)} — algum "
              "campo voltou para o fim da pagina, dentro do Modo manual")
        conta("o botao de gerar aparece ao lado da conversa",
              "btn_gerar_na_conversa" in _falso._chaves,
              "o botao que gasta a geracao ficou so no fim da pagina, dentro "
              "do Modo manual recolhido — o colaborador pede no chat e nao "
              "tem onde clicar")
        # A GALERIA LOGO ABAIXO DA CONVERSA (dono, 27/10). ONDE, e nao SE:
        # a galeria desenhada no fim da pagina registra as mesmas chaves.
        _falso.session_state["img_galeria"] = [
            {"tipo": _m.TIPOS_PADRAO[0], "bytes": b"\x89PNG\r\n\x1a\nz"}]
        _f_gal = instalar()
        for _nm_g, _mod_g in list(_sys_cc.modules.items()):
            if getattr(_mod_g, "st", None) is not None and not _nm_g.startswith(
                    ("streamlit", "checar_")):
                try:
                    _mod_g.st = _f_gal
                except Exception:
                    pass
        _f_gal.session_state.update({
            "img_nome_produto_input": "Prendedor de Roupa",
            "img_galeria": [{"tipo": _m.TIPOS_PADRAO[0],
                             "bytes": b"\x89PNG\r\n\x1a\nz"}]})
        try:
            _m.pagina_imagem("myrelladesouza")
        except (_Rerun, _Parou):
            pass
        except Exception:
            pass
        conta("a galeria e desenhada logo abaixo da conversa",
              "img_diag_sel" in getattr(_m.slot_da_galeria(), "dentro", set()),
              "a galeria voltou para o fim da pagina: quem pede a peca no "
              "chat tem de rolar a tela inteira para ver o que saiu")

        conta("e o ☰ devolve a barra lateral",
              "btn_lateral_imagem" in _falso._chaves,
              "a lateral some e nao ha como traze-la de volta: o Sair mora "
              "la dentro")

        # O FORMULARIO CONTINUA EXISTINDO, so que recolhido. Esta e a
        # assercao que impede a "limpeza" de virar remocao: e ele que gera.
        import inspect as _insp_mm
        _fonte_mm = _insp_mm.getsource(_m.pagina_imagem)
        conta("e o formulario continua na pagina, dentro do Modo manual",
              "⚙️ Modo manual" in _fonte_mm
              and "img_fotos_upload_{versao_dos_uploads()}" in _fonte_mm,
              "o formulario que GERA foi removido junto com a arrumacao: "
              "sem ele a conversa pede e nada acontece")

        # ── E O `app.py`, QUE VERIFICADOR NENHUM EXECUTA ────────────────
        #
        # Esta conferencia desenha PAGINAS (`pagina_imagem`, `pagina_home`);
        # o `app.py` e o script de entrada do Streamlit e nao tem funcao para
        # chamar. Entao a decisao de ONDE o chat aparece — a linha que o dono
        # pediu em 23/10 — nao era lida por ninguem.
        #
        # Por AST, e nao por texto: `getsource` do modulo inteiro casaria com
        # a mencao destes nomes nos comentarios, e tirar a chamada de verdade
        # nao reprovaria nada. E a licao do `.normalizar_imagem(` logo acima.
        import ast as _ast_ap
        # A RAIZ SAI DO PROPRIO ARQUIVO. Caminho absoluto escrito a mao
        # quebra no container do Railway, que nao monta o repositorio no
        # mesmo lugar — e e a mesma nota que o `exportar_codigo_de_imagem`
        # carrega.
        _raiz_ap = os.path.dirname(os.path.abspath(__file__))
        _fonte_ap = open(os.path.join(_raiz_ap, "app.py"), encoding="utf-8").read()
        _arv_ap = _ast_ap.parse(_fonte_ap)
        _chamadas_ap = {
            (getattr(_n.func, "attr", "") or getattr(_n.func, "id", ""))
            for _n in _ast_ap.walk(_arv_ap) if isinstance(_n, _ast_ap.Call)}
        conta("o app.py LE o lugar reservado para o chat",
              "slot_do_chat" in _chamadas_ap,
              "o chat voltou a ser desenhado so na barra lateral de 284px, "
              "que e o defeito que o dono pediu para corrigir")
        conta("e ele ZERA esse lugar no comeco de cada passada",
              "esquecer_slot_do_chat" in _chamadas_ap,
              "sem zerar, o conteiner da passada anterior continua valendo e "
              "o chat e escrito num lugar que nao esta mais na tela")
        # A QUEDA PARA A LATERAL CONTINUA EXISTINDO. Chat que desaparece sem
        # explicacao e pior que chat estreito.
        conta("e a barra lateral continua sendo a queda, nao o unico lugar",
              _fonte_ap.count("chat_assistente.renderizar_chat") == 2,
              "o chat tem de ser desenhado no centro OU na lateral — se so "
              "um dos dois existe, ou ele some nas outras abas ou nunca vai "
              "para o centro")
        # O ESTILO DO BOTAO VALE NOS DOIS LUGARES. Seletor preso a
        # `stSidebar` estilizaria o mesmo "Limpar Chat" num lugar e no outro
        # nao — a Forma 1 desta base, em CSS.
        conta("e o estilo do Limpar Chat nao esta preso a barra lateral",
              'stSidebar"] .st-key-ms_limpar_chat' not in _fonte_ap
              and ".st-key-ms_limpar_chat" in _fonte_ap,
              "o mesmo botao ficaria com duas caras, dependendo de onde o "
              "chat foi desenhado")
    finally:
        _sh.planilha, _sh.cliente = _guardado


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
              # 19/10: os textos da Home começam com maiúscula ("Falta o LPV")
              p4["lucro_liquido"] is None and "falta o lpv" in _h.lower(), "")
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


def _co_proporcional_na_viabilidade(conta):
    """10/10: o C.O da Viabilidade e do Preço Mínimo é % do preço.

    O dono, 07/10: "C.O. por venda proporcional ao ticket". Eram R$ 8,13
    fixos por venda nas duas abas. O `app.py` é o script do Streamlit e não
    se importa: as funções saem dele pela AST e rodam DE VERDADE, com as
    tabelas de `params_oficiais` e o `lpv_mensal` reais.
    """
    import ast as _ast_co
    import types as _ty_co
    import params_oficiais as _po_co
    import lpv_mensal as _lm_co
    import placar_core as _pc_co
    _src = open("app.py", encoding="utf-8").read()
    _arv = _ast_co.parse(_src)
    _quero = {"calcular_comissao_ml", "calcular_frete_ml", "calcular_resultado",
              "calcular_comissao_shopee", "calcular_resultado_shopee",
              "calcular_frete_shein", "calcular_resultado_shein",
              "resolver_preco_para_uc", "resolver_preco_para_uc_fn",
              "_ate_o_alvo",
              "_co_pct_medido"}
    _nos = [n for n in _arv.body if (isinstance(n, _ast_co.FunctionDef)
                                     and n.name in _quero)
            or (isinstance(n, _ast_co.Assign) and any(
                getattr(t, "id", "") == "_MESES_CURTOS" for t in n.targets))]
    _ns = {k: getattr(_po_co, k) for k in dir(_po_co) if k.isupper()}
    _ns.update(lpv_mensal=_lm_co, _pc_login=_pc_co)
    exec(compile(_ast_co.Module(body=_nos, type_ignores=[]), "app.py", "exec"),
         _ns)
    _cat = sorted(_po_co.ML_COMISSAO_POR_CATEGORIA)[0]
    _r100 = _ns["calcular_resultado"](100.0, 30.0, 0.5, _cat, "Premium", 0.08,
                                      0.07, 20.0)
    _r400 = _ns["calcular_resultado"](400.0, 30.0, 0.5, _cat, "Premium", 0.08,
                                      0.07, 20.0)
    conta("Viabilidade: o C.O é % do preço, e não valor fixo",
          abs(_r100["custo_operacional"] - 7.0) < 1e-9
          and abs(_r400["custo_operacional"] - 28.0) < 1e-9, "")
    _sp = _ns["calcular_resultado_shopee"](200.0, 30.0, 0.08, 0.05, 20.0)
    _sh = _ns["calcular_resultado_shein"](200.0, 30.0, 0.5, 0.08, 0.05, 20.0)
    conta("Shopee e Shein também cobram o C.O pelo preço",
          abs(_sp["custo_operacional"] - 10.0) < 1e-9
          and abs(_sh["custo_operacional"] - 10.0) < 1e-9, "")
    # A bisseção experimenta preços: o C.O tem de acompanhar cada um. No preço
    # achado, o UC é o alvo E o C.O é a taxa sobre ESSE preço.
    _p = _ns["resolver_preco_para_uc"](1.0, 30.0, 0.5, _cat, "Premium", 0.08,
                                       0.07, 20.0)
    _rp = _ns["calcular_resultado"](_p, 30.0, 0.5, _cat, "Premium", 0.08,
                                    0.07, 20.0)
    conta("o preço para UC 1,0 já paga o C.O desse preço",
          _rp["uc"] >= 1.0
          and _ns["calcular_resultado"](round(_p - 0.01, 2), 30.0, 0.5, _cat,
                                        "Premium", 0.08, 0.07, 20.0)["uc"] < 1.0
          and abs(_rp["custo_operacional"] - _p * 0.07) < 1e-6,
          f"preço {_p}, UC {_rp['uc']}")
    _calc_sp = lambda pr: _ns["calcular_resultado_shopee"](pr, 30.0, 0.08,
                                                           0.07, 20.0)
    _p_sp = _ns["resolver_preco_para_uc_fn"](1.0, _calc_sp, 20.0)
    _r_sp = _calc_sp(_p_sp)
    # Na troca de faixa da Shopee (R$ 79,99 → R$ 80,00) o UC salta de 0,90
    # para 1,18: o preço certo é o primeiro centavo que alcança o alvo.
    conta("Shopee e Shein: o preço para UC 1,0 é o primeiro centavo no alvo",
          _r_sp["uc"] >= 1.0 and _calc_sp(round(_p_sp - 0.01, 2))["uc"] < 1.0
          and abs(_r_sp["custo_operacional"] - _p_sp * 0.07) < 1e-6,
          f"preço {_p_sp}, UC {_r_sp['uc']}")
    _g = _lm_co.taxa_co_recente
    try:
        _lm_co.taxa_co_recente = lambda hoje: (
            0.0712, [(2026, 9), (2026, 8), (2026, 7)], "")
        _pct, _ajuda = _ns["_co_pct_medido"]()
        _lm_co.taxa_co_recente = lambda hoje: (None, [], "")
        _pct0, _ajuda0 = _ns["_co_pct_medido"]()
    finally:
        _lm_co.taxa_co_recente = _g
    conta("o campo abre com o C.O medido, e diz de que meses",
          _pct == 7.12 and "jul/2026, ago/2026, set/2026" in _ajuda, "")
    conta("sem mês medido, o campo abre vazio e pede o número",
          _pct0 is None and "Digite" in _ajuda0, "")
    _fixo = [n.lineno for n in _ast_co.walk(_arv)
             if isinstance(n, _ast_co.Constant) and n.value == 8.13]
    conta("nenhuma aba guarda os R$ 8,13 fixos", not _fixo,
          f"app.py:{_fixo}")
    _campos_co = [n for n in _ast_co.walk(_arv)
                  if isinstance(n, _ast_co.Call)
                  and getattr(n.func, "attr", "") == "number_input"
                  and n.args and isinstance(n.args[0], _ast_co.Constant)
                  and str(n.args[0].value).startswith("Custo operacional")]
    conta("as duas abas pedem o C.O em % e abrem com o medido",
          len(_campos_co) == 2 and all(
              "% do preço" in n.args[0].value
              and any(k.arg == "value" and getattr(k.value, "id", "")
                      .startswith("_co_pct") for k in n.keywords)
              for n in _campos_co), f"{len(_campos_co)} campo(s)")


def _boletos_na_tela(conta):
    """13/10: a aba Boletos lê a linha colada, mostra para conferir e lista
    os em aberto. Só a planilha é trocada: a leitura (`boleto_pdf`) e o
    cadastro (`cheques.normalizar`) rodam de verdade."""
    import boletos_tela as _bt
    import boleto_pdf as _bp
    import cheques as _ch
    from datetime import date as _d_bt

    def _campo(n):
        return n + str(_bp._mod10(n))
    _ld = (_campo("341911234") + _campo("5678901234") + _campo("5678901234")
           + "7" + "1019" + "0000150000")
    _aberto = _ch.normalizar({"tipo": "BOLETO", "favorecido": "VIDROS SA",
                              "vencimento": _d_bt.today().isoformat(),
                              "valor": 800.0, "situacao": "EM ABERTO",
                              "observacao": "LD:" + "4" * 47})
    _g = (_ch.carregar, _ch.conferir_com_extratos)
    _ch.carregar = lambda: [_aberto]
    _ch.conferir_com_extratos = lambda *a, **k: (0, [], [])
    _vistos = {}
    _falso = instalar()
    _falso.text_input = (lambda rotulo, *a, **k:
                         _ld if str(k.get("key", "")).startswith("bol_ld") else "")
    def _editor(d, *a, **k):
        _vistos["ed"] = d
        return d

    def _tabela(d, *a, **k):
        _vistos["lista"] = d
    _falso.data_editor = _editor
    _falso.dataframe = _tabela
    _bt.st = _falso
    _bt._ler_pdf = lambda dados, hoje: (None, "sem PDF no teste")
    try:
        _bt.pagina("leo")
        _ed = _vistos.get("ed")
        conta("Boletos: a linha colada vira valor e vencimento para conferir",
              _ed is not None and list(_ed["valor"]) == [1500.0]
              and bool(_ed["linha"].iloc[0]), "")
        conta("Boletos: os em aberto aparecem na lista",
              bool(_vistos.get("lista"))
              and _vistos["lista"][0]["beneficiário"] == "VIDROS SA", "")
    except (_Rerun, _Parou):
        conta("Boletos: a tela monta", True, "")
    except Exception as e:
        conta("Boletos: a tela monta", False, f"{type(e).__name__}: {e}")
    finally:
        _ch.carregar, _ch.conferir_com_extratos = _g


def _lembretes_na_home(conta):
    """15/10: os lembretes de pagamento no topo da Home, com ✓ Feito.

    Duas partes: a Home chama os lembretes ANTES de ler o Bling (indicador
    fora do ar não esconde o que vence), e o quadro desenha um botão por
    cartão, sem chave repetida. Só a planilha é trocada: o boleto passa por
    `cheques.normalizar` e o contrato por `nao_operacional._normalizar`."""
    import home_gestao as _hg_l
    import lembretes as _lem
    import cheques as _ch_l
    import nao_operacional as _no_l
    import pandas as _pd_l
    from datetime import date as _d_l
    _chamou = []
    _g_m, _g_dr = _lem.mostrar, _hg_l.dados_reais
    _falso = instalar()
    _hg_l.st = _falso
    try:
        _lem.mostrar = lambda st_, u, h: _chamou.append((u, h))
        _hg_l.dados_reais = lambda *a, **k: (None, ["Bling fora do ar"])
        _hg_l.pagina("leo")
        conta("Home: os lembretes aparecem mesmo com o Bling fora do ar",
              len(_chamou) == 1 and _chamou[0][0] == "leo", str(_chamou))
    except (_Rerun, _Parou):
        conta("Home: os lembretes aparecem mesmo com o Bling fora do ar",
              len(_chamou) == 1, "")
    except Exception as e:
        conta("Home: os lembretes aparecem mesmo com o Bling fora do ar",
              False, f"{type(e).__name__}: {e}")
    finally:
        _lem.mostrar, _hg_l.dados_reais = _g_m, _g_dr

    _bol = _ch_l.normalizar({"tipo": "BOLETO", "favorecido": "VIDROS SA",
                             "vencimento": "2026-10-17", "valor": 800.0,
                             "situacao": "EM ABERTO"})
    _contr = _no_l._normalizar([{
        "programa": "PRONAMP 1", "conta_aporte": "Itaú 99275-0",
        "data_contratacao": "2025-01-10", "carencia_meses": 6,
        "prazo_meses": 36, "aporte": 100000, "dia_debito": 18}])
    _g = (_lem.carregar_feitos, _ch_l.carregar, _no_l.carregar)
    _botoes, _textos = [], []
    _falso = instalar()

    def _botao(rot, *a, **k):
        _falso._registra("button", k)
        _botoes.append(k.get("key"))
        return False
    _falso.button = _botao
    _falso.markdown = lambda t, *a, **k: _textos.append(str(t))
    try:
        _lem.carregar_feitos = lambda: (frozenset(), "")
        _ch_l.carregar = lambda: [_bol]
        _no_l.carregar = lambda: _pd_l.DataFrame(_contr)
        # O que venceu até 15/10 já foi marcado Feito: o atrasado sem Feito
        # "continua" na tela (dono, 16/10), e aqui o assunto é o futuro.
        _passados = frozenset(x["chave"] for x in _lem.das_regras(_d_l(2026, 10, 1), _d_l(2026, 10, 15)))
        _lem.carregar_feitos = lambda: (_passados, "")
        # 16/10, o dono: aparece no dia útil anterior ao vencimento. Na
        # quinta 15/10 o próximo dia útil é 16/10: o boleto de 17/10 (sáb)
        # e o PRONAMP de 18/10 (dom) ainda não; na sexta, os dois entram.
        _lem.mostrar(_falso, "leo", _d_l(2026, 10, 15))
        conta("Lembretes: quinta sem vencimento até sexta não desenha o quadro",
              not _botoes and not _textos, str(_textos)[:120])
        _lem.mostrar(_falso, "leo", _d_l(2026, 10, 16))
        _junto = " ".join(_textos)
        conta("Lembretes: sexta 16/10 traz o boleto de sábado e o PRONAMP de domingo, um ✓ Feito cada",
              len(_botoes) == 2 and len(set(_botoes)) == 2
              and all(str(b).startswith("lem_") for b in _botoes)
              and "Boleto · VIDROS SA" in _junto and "PRONAMP 1" in _junto, str(_botoes))
        conta("Lembretes: a TM de 20/10 ainda não aparece, e nada de valor",
              "TM Logística" not in _junto and "Depois" not in _junto
              and "R$" not in _junto, "")
    except (_Rerun, _Parou):
        conta("Lembretes: a tela monta", True, "")
    except Exception as e:
        conta("Lembretes: a tela monta", False, f"{type(e).__name__}: {e}")
    finally:
        _lem.carregar_feitos, _ch_l.carregar, _no_l.carregar = _g


def _visao_geral(conta):
    """15/10: a aba Visão Geral desenha inteira — resumo por finalidade, o
    detalhe por modalidade e o mês corrente. Só a planilha e a rede são
    trocadas: os lançamentos passam por `resumo_mensal.itens_pagos` e a
    planilha por `controle_ms.ler`, de verdade."""
    import io as _io_v
    import openpyxl as _ox_v
    import pandas as _pd_v
    import auth as _au_v
    import controle_ms as _cms_v
    import lancamentos as _lan_v
    import assinaturas as _as_v
    import custo_fixo as _cf_v
    import ajustes as _aj_v
    import custo_real as _cr_v
    import nao_operacional as _no_v
    import folha_salarial as _fs_v
    import lpv_mensal as _lm_v
    import previsto as _pv_v
    import visao_geral as _vg
    _wb = _ox_v.Workbook()
    _ws = _wb.active
    _ws.title = "SAIDAS PIX-BOLETO 2026"
    _ws.append([None, "Data", "Operação", "DESTINATÁRIO", "FINALIDADE", "Valor", "Banco"])
    _ws.append([None, "2026-07-06", "PIX ENVIADO", "Z", "EMBALAGEM", -50.0, "INTER LG"])
    for _n, _c in (("CARTÕES", ["MÊS/ANO", "FINALIDADE", "Valor"]),
                   ("SIMPLES - FLEX", ["MÊS/ANO", "VALOR", "FINALIDADE"]),
                   ("ADS E CROSS", ["MÊS/ANO", "DESCRIÇÃO", "COBRANÇA"])):
        _wb.create_sheet(_n).append(_c)
    _wb["ADS E CROSS"].append(["jul2026", "PUBLICIDADE", 3119.76])
    _b = _io_v.BytesIO()
    _wb.save(_b)
    _lancs = [{"data": "2026-07-10", "valor": -300.0, "conta": "itau-0099275-0",
               "descricao": "BOLETO PAGO", "favorecido": "ENEL",
               "finalidade": "CUSTO FIXO", "tipo": ""}]
    _g = (_cms_v._bytes_do_arquivo, _lan_v.carregar, _as_v.carregar,
          _cf_v.carregar, _aj_v.carregar, _cr_v.carregar, _no_v.carregar,
          _fs_v.carregar, _lm_v.lpv_do_ano, _lm_v.custo_operacional_do_ano,
          _pv_v.do_mes, _au_v.eh_dono)
    _textos = []
    _falso = instalar()
    _falso.markdown = lambda t, *a, **k: _textos.append(str(t))
    _falso.selectbox = lambda rot, opcoes, *a, **k: list(opcoes)[0]
    _falso.radio = lambda rot, opcoes, *a, **k: list(opcoes)[k.get("index", 0) or 0]
    _vg.st = _falso
    try:
        _cms_v._bytes_do_arquivo = lambda: (_b.getvalue(), "")
        _vg.da_planilha.clear()
        _vg.dados_do_ano.clear()
        _lan_v.carregar = lambda: list(_lancs)
        _as_v.carregar = lambda: []
        _cf_v.carregar = lambda aba: _pd_v.DataFrame(columns=_cf_v.COLUNAS)
        _aj_v.carregar = lambda: _pd_v.DataFrame(columns=_aj_v.COLUNAS)
        _cr_v.carregar = lambda: {}
        _no_v.carregar = lambda: _pd_v.DataFrame(columns=_no_v.COLUNAS)
        _fs_v.carregar = lambda: _pd_v.DataFrame()
        _lm_v.lpv_do_ano = lambda ano: ({7: {"lpv": 16.90}}, "")
        _lm_v.custo_operacional_do_ano = lambda ano: ({7: {"co": 14623.49, "motivo": ""}}, "")
        _pv_v.do_mes = lambda a, m: ({}, [])
        _au_v.eh_dono = lambda u: True
        _vg.pagina("leo")
        _j = " ".join(_textos)
        conta("Visão Geral: resumo, detalhe e mês corrente desenham",
              "RESUMO POR FINALIDADE" in _j and "DETALHE POR MODALIDADE" in _j
              and "ESTE MÊS" in _j, "")
        conta("Visão Geral: planilha (P) e Studio (S) no mesmo resumo",
              "EMBALAGEM" in _j and "CUSTO FIXO" in _j and "R$ 16,90" in _j, "")
    except (_Rerun, _Parou):
        conta("Visão Geral: a tela monta", True, "")
    except Exception as e:
        conta("Visão Geral: a tela monta", False, f"{type(e).__name__}: {e}")
    finally:
        (_cms_v._bytes_do_arquivo, _lan_v.carregar, _as_v.carregar,
         _cf_v.carregar, _aj_v.carregar, _cr_v.carregar, _no_v.carregar,
         _fs_v.carregar, _lm_v.lpv_do_ano, _lm_v.custo_operacional_do_ano,
         _pv_v.do_mes, _au_v.eh_dono) = _g
        _vg.da_planilha.clear()
        _vg.dados_do_ano.clear()


def _visao_faturamento(conta):
    """15/10: Visão Geral › Faturamento desenha inteira, com a conferência
    Bling × planilha aberta. Só a planilha e o Bling são trocados: as linhas
    têm as colunas da BASE DE VENDAS do dono e os pedidos passam por
    `bling_api.pedido_resumido`."""
    import datetime as _dt_f
    import auth as _au_f
    import bling_api as _bl_f
    import visao_geral as _vg_f
    import visao_faturamento as _vf
    base = [{"MÊS/ANO": "set2026", "Data": _dt_f.datetime(2026, 9, 10), "Plataforma": "MercadoLivre1",
             "Pedido": "2000015134692443", "SKU": "MS-1", "Produto": "Argola", "Custo Unitário": 10.0,
             "FAT TOTAL": 100.0, "DEVOLUÇÃO": 0, "MARGEM C.": 41.26, "VENDAS": 1, "LPV": 20.63,
             "UNI. CONT.": 2.0, "FAT - DEV": 100.0, "L.B": 70.0},
            {"MÊS/ANO": "out2026", "Data": _dt_f.datetime(2026, 10, 5), "Plataforma": "Shopee1",
             "Pedido": "2610050AAA", "SKU": None, "Produto": "Mini", "Custo Unitário": None,
             "FAT TOTAL": 50.0, "DEVOLUÇÃO": 0, "MARGEM C.": 10.0, "VENDAS": None, "LPV": None,
             "UNI. CONT.": None, "FAT - DEV": 50.0, "L.B": 20.0}]
    plan = {"base": base, "consolidado": [{"FAT": m, "2025": 1000.0, "2025_2": 10} for m in _vf.MESES],
            "dinamica": [(2, 11, "META 2026"), (2, 12, 2700000)]
                        + [(8 + q, 16, f"{q}º Trimestre") for q in (1, 2, 3, 4)]
                        + [(8 + q, 18, 600000.0) for q in (1, 2, 3, 4)]
                        + [(16 + q, 16, f"{q}º Trimestre") for q in (1, 2, 3, 4)]
                        + [(16 + q, 18, 7000.0) for q in (1, 2, 3, 4)]}
    bling = [_bl_f.pedido_resumido({"numero": 1, "numeroLoja": "2000015134692443", "data": "2026-09-10",
                                    "total": 100.0, "loja": {"id": 1}, "situacao": {"id": 6}}),
             _bl_f.pedido_resumido({"numero": 2, "numeroLoja": "2609200SOBLING", "data": "2026-09-20",
                                    "total": 49.99, "loja": {"id": 1}, "situacao": {"id": 6}})]
    _g = (_vf.ler_planilha, _vf.bling_do_mes_corrente, _vf.pedidos_do_bling, _au_f.eh_dono)
    _textos, _tabelas, _baixar = [], [], []
    _falso = instalar()
    _falso.markdown = lambda t, *a, **k: _textos.append(str(t))
    _falso.selectbox = lambda rot, opcoes, *a, **k: list(opcoes)[0]
    _falso.radio = (lambda rot, opcoes, *a, **k:
                    "Faturamento" if k.get("key") == "vg_aba" else list(opcoes)[k.get("index", 0) or 0])
    _falso.dataframe = lambda d, *a, **k: _tabelas.append(d)
    _falso.download_button = lambda rot, dados, *a, **k: (_falso._registra("download_button", k), _baixar.append(k.get("file_name")))
    _falso.session_state["vf_conf_feito"] = (2026, 9)
    _vg_f.st = _falso
    _vf.st = _falso
    try:
        _vf.ler_planilha = lambda: (plan, [])
        _vf.bling_do_mes_corrente = lambda hoje: (5000.0, [])
        _vf.pedidos_do_bling = lambda a, m: (bling, [])
        _au_f.eh_dono = lambda u: True
        _vg_f.pagina("leo")
        _j = " ".join(_textos)
        conta("Faturamento: meta, trimestres, UC, mês a mês e resumo para o time desenham",
              all(t in _j for t in ("META 2026 E O ANO ACUMULADO", "RESULTADOS TRIMESTRAIS",
                                    "UC · RESULTADOS MENSAIS", "MÊS A MÊS", "RESUMO PARA O TIME")), "")
        conta("Faturamento: o mês corrente aparece marcado como Bling", "BLING" in _j, "")
        conta("Faturamento: a conferência lista o pedido que está só no Bling",
              any("2609200SOBLING" in str(getattr(t, "to_string", lambda: t)()) for t in _tabelas), "")
        conta("Faturamento: Excel das listas e resumo para baixar",
              "conferencia_bling_2026_09.xlsx" in _baixar and "resumo_time_2026.html" in _baixar, str(_baixar))
    except (_Rerun, _Parou):
        conta("Faturamento: a tela monta", True, "")
    except Exception as e:
        conta("Faturamento: a tela monta", False, f"{type(e).__name__}: {e}")
    finally:
        _vf.ler_planilha, _vf.bling_do_mes_corrente, _vf.pedidos_do_bling, _au_f.eh_dono = _g


def _historico_na_home(conta):
    """13/10: a sub-aba Histórico abre pela Home e mostra os meses fechados.

    Só a planilha é trocada: a meta na forma de `meta_gastos.ano_inteiro`,
    as vendas pela própria `base_vendas.somar`. O mês corrente não entra."""
    import gestao as _ge_h
    import historico as _hi
    import meta_gastos as _mg_h
    import base_vendas as _bv_h
    import lpv_mensal as _lm_h
    from datetime import date as _d_h, datetime as _dt_h
    _hoje = _d_h.today()
    _ant = (_hoje.year, _hoje.month - 1) if _hoje.month > 1 else None
    COLS = ["Data", "MÊS/ANO", "FAT TOTAL", "FAT - DEV", "L.B", "VENDAS"]
    _base = ([{"Data": _dt_h(_ant[0], _ant[1], 5), "MÊS/ANO": "x",
               "FAT TOTAL": 240000, "FAT - DEV": 228000, "L.B": 170000,
               "VENDAS": 100}] if _ant else [])
    _mapa = ({(_ant[0], _ant[1]): _bv_h.somar(_base, COLS, *_ant)}
             if _ant else {})
    _linhas = [{"meta": 0.0, "realizado": 0.0, "origem": "sem dado"}
               for _ in range(12)]
    if _ant:
        _linhas[_ant[1] - 1] = {"meta": 150000.0, "realizado": 140000.0,
                                "origem": "extrato"}
    _linhas[_hoje.month - 1] = {"meta": 150000.0, "realizado": 9000.0,
                                "origem": "extrato"}
    _g = (_mg_h.ano_inteiro, _bv_h.somas_por_mes, _lm_h.lpv_do_ano)
    _mg_h.ano_inteiro = lambda ano: _linhas
    _bv_h.somas_por_mes = lambda: (_mapa, "")
    _lm_h.lpv_do_ano = lambda ano: ({}, "")
    _vistos = {"tabela": None, "html": ""}
    _falso = instalar()
    _falso.radio = lambda *a, **k: _ge_h.ABA_HISTORICO
    _falso.selectbox = lambda rot, opcoes, *a, **k: list(opcoes)[0]

    def _tab(d, *a, **k):
        _vistos["tabela"] = d

    def _md(t, *a, **k):
        if "Resumo ·" in str(t):
            _vistos["html"] = str(t)
    _falso.dataframe = _tab
    _falso.markdown = _md
    _ge_h.st = _falso
    _hi.st = _falso
    try:
        _ge_h.pagina_home("leo")
        _t = _vistos["tabela"]
        _esperado = ([f"{_hi.MESES[_ant[1] - 1]}/{_ant[0]}"] if _ant else [])
        conta("Home › Histórico: os meses fechados, sem o mês corrente",
              _t is not None and [r["mês"] for r in _t] == _esperado,
              str([r["mês"] for r in (_t or [])]))
        conta("Home › Histórico: o resumo do mês abre embaixo",
              "Resumo · " in _vistos["html"]
              and "Faturado × equilíbrio real" in _vistos["html"], "")
    except (_Rerun, _Parou):
        conta("Home › Histórico: a tela monta", True, "")
    except Exception as e:
        conta("Home › Histórico: a tela monta", False,
              f"{type(e).__name__}: {e}")
    finally:
        _mg_h.ano_inteiro, _bv_h.somas_por_mes, _lm_h.lpv_do_ano = _g


def _visao_geral_na_home(conta):
    """19/10: a Visão Geral saiu da barra de Gestão e virou a aba do meio da
    Home — Painel | Visão Geral | Histórico —, só para o dono."""
    import gestao as _ge_v
    import visao_geral as _vg_v
    import auth as _au_v
    _dono = sorted(_au_v.ADMINS_PADRAO)[0]
    _chamou, _opcoes = [], []
    _g = _vg_v.pagina
    _falso = instalar()

    def _radio(rot, opcoes, *a, **k):
        _opcoes.append(tuple(opcoes))
        return _ge_v.ABA_VISAO if _ge_v.ABA_VISAO in opcoes else opcoes[0]
    _falso.radio = _radio
    _ge_v.st = _falso
    try:
        _vg_v.pagina = lambda u=None: _chamou.append(u)
        _ge_v.pagina_home(_dono)
        conta("Home: a ordem é Painel | Visão Geral | Produtos | Histórico, e a Visão Geral abre a dela",
              _opcoes[0] == ("📊 Painel", "🧭 Visão Geral", "📈 Produtos", "🗓️ Histórico")
              and _chamou == [_dono], str(_opcoes))
        import produtos_analise as _pa_v
        _g_pa, _abriu = _pa_v.pagina, []
        _falso.radio = lambda rot, opcoes, *a, **k: _ge_v.ABA_PRODUTOS
        try:
            _pa_v.pagina = lambda u=None: _abriu.append(u)
            _ge_v.pagina_home(_dono)
        finally:
            _pa_v.pagina = _g_pa
            _falso.radio = _radio
        conta("Home: a aba Produtos abre a análise de produtos (dono, 20/10)", _abriu == [_dono], str(_abriu))
        _opcoes.clear()
        try:
            _ge_v.pagina_home("colaborador_qualquer")
        except Exception:
            pass
        conta("Home: quem não é dono não vê a Visão Geral nem Produtos",
              bool(_opcoes) and "🧭 Visão Geral" not in _opcoes[0]
              and _ge_v.abas_da_home("colaborador_qualquer")
              == tuple(a for a in _ge_v.HOME_ABAS if a not in (_ge_v.ABA_VISAO, _ge_v.ABA_PRODUTOS))
              and "📈 Produtos" not in _opcoes[-1],
              str(_opcoes))
    except (_Rerun, _Parou):
        conta("Home › Visão Geral: a tela monta", True, "")
    except Exception as e:
        conta("Home › Visão Geral: a tela monta", False, f"{type(e).__name__}: {e}")
    finally:
        _vg_v.pagina = _g


def _tiktok_na_viabilidade(conta):
    """19/10: a TikTok Shop na Viabilidade e na Calculadora de Preço Mínimo.

    O dado vem do DEMONSTRATIVO FINANCEIRO REAL da loja (income_20261019),
    pedido a pedido — e não de taxa escrita de cabeça: globo R$ 109,99 com
    afiliado 9,5% → repasse 80,34; almofada R$ 34,99 → 25,39; suporte
    R$ 309,99 com afiliado 13,17 → 253,62. As funções saem do `app.py` pela
    AST e rodam com as tabelas reais de `params_oficiais`."""
    import ast as _ast_t
    import params_oficiais as _po_t
    import lpv_mensal as _lm_t
    _arv = _ast_t.parse(open("app.py", encoding="utf-8").read())
    _quero = {"calcular_comissao_tiktok", "calcular_resultado_tiktok",
              "resolver_preco_para_uc_fn", "_ate_o_alvo"}
    _nos = [n for n in _arv.body if isinstance(n, _ast_t.FunctionDef) and n.name in _quero]
    conta("TikTok: as funções de cálculo existem no app.py",
          {n.name for n in _nos} == _quero, str({n.name for n in _nos}))
    if {n.name for n in _nos} != _quero:
        return
    _ns = {k: getattr(_po_t, k) for k in dir(_po_t) if k.isupper()}
    _ns.update(lpv_mensal=_lm_t)
    exec(compile(_ast_t.Module(body=_nos, type_ignores=[]), "app.py", "exec"), _ns)
    _calc = _ns["calcular_resultado_tiktok"]
    # repasse = preço − (comissão + taxa por item + SFP + afiliado); com NF, C.O
    # e custo em zero, o "lucro bruto" é o que a TikTok liquida.
    _rep = lambda p, af: round(_calc(p, 0.0, 0.0, 0.0, 20.0, af)["lucro_bruto"], 2)
    conta("TikTok bate com o demonstrativo real: globo, almofada e suporte",
          _rep(109.99, 0.095) == 80.34 and _rep(34.99, 0.0) == 25.39
          and _rep(309.99, 13.17 / 309.99) == 253.62 and _rep(109.99, 0.0) == 90.79,
          f"{_rep(109.99, 0.095)} {_rep(34.99, 0.0)} {_rep(309.99, 13.17 / 309.99)}")
    conta("TikTok: o SFP para em R$ 50 por item e o frete é zero",
          round(_calc(1000.0, 0, 0, 0, 20.0)["comissao"], 2) == round(60 + 6 + 50, 2)
          and _calc(1000.0, 0, 0, 0, 20.0)["frete"] == 0.0, "")
    _c = lambda pr: _calc(pr, 30.0, 0.08, 0.07, 20.0, 0.0)
    _p = _ns["resolver_preco_para_uc_fn"](1.0, _c, 20.0)
    conta("TikTok: o preço para UC 1,0 é o primeiro centavo no alvo (troca de faixa em R$ 50)",
          _c(_p)["uc"] >= 1.0 and _c(round(_p - 0.01, 2))["uc"] < 1.0, f"preço {_p}")
    _src = open("app.py", encoding="utf-8").read()
    _viab = _src[_src.index("def _render_viabilidade_tab"):_src.index("def _navegar")]
    _calc_min = _src[_src.index("def _render_analise_venda_tab"):_src.index("def _render_viabilidade_tab")]
    conta("TikTok na tela: preço, % de afiliado, coluna do resultado e registro",
          'key="preco_tk"' in _viab and 'key="viab_tk_afiliado"' in _viab
          and '"tk": ("ms-plat-tk", "TikTok Shop")' in _viab
          and '("TikTok", res_tk, preco_tk or 0)' in _viab
          and "calcular_resultado_tiktok(" in _calc_min and "TikTok Shop" in _calc_min, "")


def _din_financas_previa(conta):
    """19/10: a prévia do que o Studio gravaria na DIN FINANÇAS (só leitura).

    O desenho da aba é o do .xlsx real (cópia de 15/10, lida no XML): título
    "LPV MENSAL" em X52 e "CUSTOS OP. MENSAL" em X68, meses "jan".."dez" na
    coluna X, valor em Y. Os meses do Studio saem de `lpv_mensal.lpv` e
    `lpv_mensal.calcular` — as funções que `lpv_do_ano` e
    `custo_operacional_do_ano` chamam. Só a REDE é trocada."""
    import financeiro as _fi_d
    import excel_ms as _xm_d
    import controle_ms as _cms_d
    import lpv_mensal as _lm_d
    from datetime import date as _d_d
    _grade = [["" for _ in range(32)] for _ in range(140)]
    _form = [["" for _ in range(32)] for _ in range(140)]
    _grade[49][23] = "LPV (FIXO E N OPER.)"
    _grade[51][23], _grade[67][23] = "LPV MENSAL", "CUSTOS OP. MENSAL"
    for _i, _n in enumerate(("jan", "fev", "mar", "abr", "mai", "jun", "jul",
                             "ago", "set", "out", "nov", "dez")):
        _grade[52 + _i][23] = _grade[68 + _i][23] = _n
        _grade[52 + _i][24] = _grade[68 + _i][24] = "0,00"
        _form[52 + _i][24] = f"=IFERROR($C$8/VLOOKUP(X{53 + _i},DINAMICA!$B$60:$C$72,2,0),0)"
    _meses = {9: _lm_d.lpv(5000.0, 1000.0, 300.0, 200.0, 300),
              10: _lm_d.lpv(5000.0, 1000.0, 300.0, 200.0, 100)}
    _co = {9: _lm_d.calcular([{"valor": -9000.0, "finalidade": "PAGINA DO ML"}],
                             {"vendas": 300})}
    _hoje = _d_d(2026, 10, 19)
    _rede, _tabelas, _avisos = [], [], []
    _g = (_xm_d.configurado, _xm_d.item_do_link, _xm_d.ler_grade,
          _cms_d.link_configurado, _fi_d.st)

    _gravados, _desab = [], []
    _g_prev, _g_grav = _lm_d.co_previsto_agora, _xm_d.gravar
    _lm_d.co_previsto_agora = lambda h: (_lm_d.co_do_mes_corrente(0.065, 100000.0, 19, 31, 3000.0), "")
    _xm_d.gravar = lambda l, itens: (_gravados.append([i["celula"] for i in itens]), (len(itens), ""))[1]

    def _rodar(clicar, link, confirma=False):
        _falso = instalar()
        if clicar is True:
            clicar = {"din_testar_2026"}
        _falso.button = lambda rot, *a, **k: (k.get("key") == "din_gravar_2026" and _desab.append(k.get("disabled")),
                                              bool(clicar) and k.get("key") in clicar)[1]
        _falso.checkbox = lambda rot, *a, **k: confirma
        _falso.dataframe = lambda d, *a, **k: _tabelas.append(d)
        _falso.warning = lambda t, *a, **k: _avisos.append(str(t))
        _fi_d.st = _falso
        _cms_d.link_configurado = lambda: link
        _fi_d._secao_din_financas(2026, _meses, _co, _hoje)
    try:
        _xm_d.configurado = lambda: ""
        _xm_d.item_do_link = lambda l: (_rede.append("item") or
                                        ({"nome": "Controle MS.xlsx", "alterado": "2026-10-19T19:00:00Z",
                                          "drive": "d", "item": "i"}, ""))
        _xm_d.ler_grade = lambda l, *a, **k: (_rede.append("grade") or
                                              ({"texto": _grade, "formulas": _form, "endereco": "A1:AF140"}, ""))
        _emp = "https://martinsousacombr-my.sharepoint.com/:x:/g/personal/x/y?e=1"
        _rodar(False, _emp)
        conta("DIN FINANÇAS: sem clique, nenhuma chamada à Microsoft (a tela roda a cada tecla)",
              _rede == [] and _tabelas == [], str(_rede))
        _rodar(True, _emp)
        _df = _tabelas[-1] if _tabelas else None
        _cel = list(_df["Célula"]) if _df is not None else []
        conta("DIN FINANÇAS: a prévia mostra set em Y61 (LPV) e Y77 (C.O.), e outubro só no C.O. previsto (Y78)",
              _cel == ["Y61", "Y77", "Y78"] and "previsto" in str(_df["Mês"].iloc[2]), str(_cel))
        conta("DIN FINANÇAS: sem a confirmação marcada, o botão de gravar fica desligado e nada é gravado",
              _desab and _desab[-1] is True and _gravados == [], str(_desab))
        _rodar({"din_testar_2026", "din_gravar_2026"}, _emp, confirma=True)
        conta("DIN FINANÇAS: com a confirmação, grava exatamente as células da prévia",
              _gravados == [["Y61", "Y77", "Y78"]], str(_gravados))
        conta("DIN FINANÇAS: avisa que Y61 hoje é fórmula",
              _df is not None and str(_df["Hoje é fórmula"].iloc[0]).startswith("sim")
              and not str(_df["Hoje é fórmula"].iloc[1]), "")
        _rede.clear()
        _tabelas.clear()
        _rodar(True, "https://onedrive.live.com/?id=x")
        conta("DIN FINANÇAS: link do OneDrive pessoal avisa e não chama a rede",
              _rede == [] and any("EMPRESA" in a for a in _avisos), str(_avisos[-1:]))
    except (_Rerun, _Parou):
        conta("DIN FINANÇAS: a prévia monta", True, "")
    except Exception as e:
        conta("DIN FINANÇAS: a prévia monta", False, f"{type(e).__name__}: {e}")
    finally:
        (_xm_d.configurado, _xm_d.item_do_link, _xm_d.ler_grade,
         _cms_d.link_configurado, _fi_d.st) = _g
        _lm_d.co_previsto_agora, _xm_d.gravar = _g_prev, _g_grav


def _produtos_analise(conta):
    """20/10: Gestão › Produtos, o analista de produtos (layout aprovado).

    As linhas passam por `produtos_analise.linhas_da_base` com o CABEÇALHO REAL
    da BASE DE VENDAS 2026 — a porta da tela, e não um dicionário no formato
    que eu acho que ele tem. Só a leitura da planilha é trocada. A tela monta
    inteira, com uma faixa de UC aberta e o panorama de um produto."""
    import datetime as _dt_p
    import produtos_analise as _pa
    import auth as _au_p
    _dono = sorted(_au_p.ADMINS_PADRAO)[0]
    cab = ['MÊS', 'MÊS/ANO', 'Data', 'Plataforma', 'Pedido', 'SKU', 'Produto', 'Quantidade',
           'Custo Unitário', 'Custo Flex', 'FAT TOTAL', 'CUSTO TOTAL', 'COMISSÃO', 'FRETE',
           'NF', 'CUSTO OP.', 'DEVOLUÇÃO', 'MARGEM C.', 'VENDAS', 'LPV', 'UNI. CONT.']
    regs = []
    for m in range(1, 10):
        for d in range(1, 13):
            regs.append({"Data": _dt_p.datetime(2026, m, d), "Plataforma": "Shopee1", "SKU": "MS-2260",
                         "Produto": "KIT COM 3 ESTÁTUAS", "Quantidade": 1, "FAT TOTAL": 60.0,
                         "CUSTO TOTAL": 22.6, "COMISSÃO": 17.5, "FRETE": 0, "NF": 5.4, "CUSTO OP.": 4.3,
                         "DEVOLUÇÃO": 0, "MARGEM C.": 10.0, "LPV": 18.0, "Custo Unitário": 22.6})
        for d in range(1, 8):
            regs.append({"Data": _dt_p.datetime(2026, m, d), "Plataforma": "MercadoLivre1", "SKU": "MS-8936",
                         "Produto": "CINZEIRO TELESCÓPICO", "Quantidade": 1, "FAT TOTAL": 200.0,
                         "CUSTO TOTAL": 89.4, "COMISSÃO": 30.0, "FRETE": 20, "NF": 18, "CUSTO OP.": 9,
                         "DEVOLUÇÃO": 0, "MARGEM C.": 45.0, "LPV": 18.0, "Custo Unitário": 89.36})
    linhas = _pa.linhas_da_base(regs, cab, {m: 18.0 for m in range(1, 10)}, 2026)
    import produtos_grupos as _pg_t
    _g = (_pa.dados, _pa.st, _pg_t.carregar, _pg_t.classificar, _pg_t.salvar)
    _botoes, _salvos, _md = [], [], []
    _mapa = {}
    _pg_t.carregar = lambda: (_mapa, "")
    _pg_t.salvar = lambda m: _salvos.append(m)
    _pg_t.classificar = lambda lote, chamar=None: (
        {t: ("KIT 3 ESTÁTUAS" if "ESTÁTUAS" in t else t, "Decoração" if "ESTÁTUAS" in t else "Tabacaria")
         for t in lote}, "")

    def _rodar(usuario, dados, clicar=(), panorama=""):
        f = instalar()
        f.segmented_control = lambda rot, opcoes, default=None, **k: (f._registra("segmented_control", k), default)[1]
        f.dialog = lambda *a, **k: (lambda fn: fn)
        f.markdown = lambda t, *a, **k: _md.append(str(t))
        # As colunas devolvem o próprio duplo: o `col.markdown` das quatro
        # colunas do ranking cai no mesmo lugar que o resto da página.
        f.columns = lambda spec, **k: [f] * (spec if isinstance(spec, int) else len(spec))
        f.button = lambda rot, *a, **k: (f._registra("button", k), _botoes.append(k.get("key")),
                                         k.get("key") in clicar)[2]
        f.selectbox = lambda rot, opcoes, *a, **k: (f._registra("selectbox", k),
                                                    panorama if k.get("key") == "pa_pan" else
                                                    list(opcoes)[k.get("index", 0) or 0])[1]
        _pa.st = f
        _pa.dados = lambda ano, hoje: (dados, "")
        _pa.pagina(usuario)
    try:
        _rodar(_dono, linhas)
        conta("Produtos: a página monta inteira (alertas, balanço, ranking nos 4 períodos)",
              "pa_faixa_0" in _botoes and "pa_v_errado" in _botoes, str(_botoes[:8]))
        import re as _re_p
        _cols = [t for t in _md if "ATÉ 20 ↓" in t]
        _alt = {_re_p.search(r"max-height:(\d+)px", t).group(1) for t in _cols}
        conta("Produtos: as 4 colunas do ranking abrem simétricas — top 10 e a mesma altura em todas (dono, 20/10)",
              len(_cols) == 4 and all("TOP 10 · ATÉ 20" in t for t in _cols) and len(_alt) == 1,
              f"{len(_cols)} colunas, alturas {_alt}")
        _rodar(_dono, linhas, clicar={"pa_faixa_0"}, panorama="CINZEIRO TELESCÓPICO")
        conta("Produtos: abrir uma faixa de UC e o panorama de um produto não quebra", True, "")
        conta("Produtos: título novo é juntado SOZINHO pela IA ao abrir a página (sem IA de verdade)",
              _salvos and _salvos[0]["KIT COM 3 ESTÁTUAS"]["nicho"] == "Decoração"
              and _salvos[0]["CINZEIRO TELESCÓPICO"]["origem"] == "ia", str(_salvos[:1])[:200])
        _ok_auto = list(_salvos)
        _salvos.clear()
        _g_cl = _pg_t.classificar
        _pg_t.classificar = lambda lote, chamar=None: ({}, "ANTHROPIC_API_KEY não configurada")
        _botoes.clear()
        _rodar(_dono, linhas)
        _pg_t.classificar = _g_cl
        conta("Produtos: com a IA fora, nada é salvo e o botão manual continua lá",
              _salvos == [] and "pa_ia_juntar" in _botoes, str(_botoes[-3:]))
        _salvos.extend(_ok_auto)
        _mapa.update(_salvos[-1])
        _botoes.clear()
        _rodar(_dono, linhas)
        conta("Produtos: com os títulos juntados, a fatia por nicho aparece e o botão da IA some",
              "pa_ia_juntar" not in _botoes, str(_botoes))
        _botoes.clear()
        _rodar(_dono, [])
        _rodar("colaborador_qualquer", linhas)
        conta("Produtos: sem vendas, e para quem não é dono, avisa e não monta nada",
              _botoes == [], str(_botoes))
    except (_Rerun, _Parou):
        conta("Produtos: a tela monta", True, "")
    except Exception as e:
        import traceback
        conta("Produtos: a tela monta", False, f"{type(e).__name__}: {e} {traceback.format_exc()[-400:]}")
    finally:
        _pa.dados, _pa.st, _pg_t.carregar, _pg_t.classificar, _pg_t.salvar = _g


def _gargalos_volume(conta):
    """20/10: a Análise de Gargalos foi para o Operacional e passou a dizer
    QUANTOS processos houve — zero retrabalho com zero processo não é verde.
    As linhas têm a forma que `log_imagem.registrar` grava ("gerar_tudo" com
    "N imagem(ns) a gerar"). Só a leitura do log é trocada."""
    import gestao as _ge_g
    import gargalos_tela as _gt_g
    import log_imagem as _li_g
    import auth as _au_g
    conta("Gargalos: saiu do Financeiro e está no Operacional",
          "🔎 Análise de Gargalos" not in _ge_g.SUBTELAS
          and "🔎 Análise de Gargalos" in _ge_g.SUBTELAS_OPERACIONAL, "")
    _dono = sorted(_au_g.ADMINS_PADRAO)[0]
    _g = (_li_g.ler, _gt_g.st)
    _metricas, _avisos = {}, []
    try:
        for caso, linhas in (("com processo", [{"quando": "", "usuario": "leo", "produto": "Caneca",
                                                "acao": "gerar_tudo", "imagem": "", "tipo": "",
                                                "instrucao": "", "resultado": "8 imagem(ns) a gerar"}]),
                             ("sem processo", [{"quando": "", "usuario": "leo", "produto": "Caneca",
                                                "acao": "layout_descartado", "imagem": "", "tipo": "",
                                                "instrucao": "", "resultado": "x"}])):
            f = instalar()
            f.columns = lambda spec, **k: [f] * (spec if isinstance(spec, int) else len(spec))
            f.selectbox = lambda rot, opcoes, *a, **k: list(opcoes)[k.get("index", 0) or 0]
            f.metric = lambda rot, valor, *a, **k: _metricas.__setitem__((caso, rot), valor)
            f.warning = lambda t, *a, **k: _avisos.append((caso, str(t)))
            _gt_g.st = f
            _li_g.ler = lambda n=200, _l=linhas: _l
            _gt_g.pagina(_dono)
        conta("Gargalos: mostra os processos gerados e as imagens pedidas",
              _metricas.get(("com processo", "Processos gerados")) == 1
              and _metricas.get(("com processo", "Imagens pedidas")) == 8, str(_metricas)[:200])
        conta("Gargalos: sem processo no período, avisa que zero retrabalho não quer dizer nada",
              any(c == "sem processo" and "Nenhum processo" in t for c, t in _avisos)
              and not any(c == "com processo" and "Nenhum processo" in t for c, t in _avisos),
              str(_avisos)[:200])
    except (_Rerun, _Parou):
        conta("Gargalos: a tela monta", True, "")
    except Exception as e:
        conta("Gargalos: a tela monta", False, f"{type(e).__name__}: {e}")
    finally:
        _li_g.ler, _gt_g.st = _g


def _faturamento_top5(conta):
    """20/10: Faturamento — o MÊS A MÊS centralizado e o quadro do
    marketplace partido: plataformas à esquerda, os 5 mais vendidos à
    direita. O top 5 sai da CADEIA real (`linhas_da_base` → `aplicar` →
    `top_vendidos`), com as linhas na forma da BASE DE VENDAS; só a leitura
    da planilha é trocada."""
    import inspect
    from datetime import datetime
    import visao_faturamento as _vf
    import produtos_analise as _pa
    import produtos_grupos as _pg
    cols = ["MÊS/ANO", "Data", "Plataforma", "Pedido", "SKU", "Produto", "Custo Unitário",
            "FAT TOTAL", "DEVOLUÇÃO", "MARGEM C.", "VENDAS", "LPV", "UNI. CONT."]
    regs = [dict(zip(cols, ("set2026", datetime(2026, 9, 10), "MercadoLivre1", f"P{i}", "MS-1",
                            nome, 10.0, 100.0, 0, 41.26, 1, 20.63, 2.0)))
            for i, nome in enumerate(["Argola Dourada"] * 3 + ["Mini Caneca"] * 2 + ["Chaveiro"])]
    brutas = _pa.linhas_da_base(regs, cols, {9: 20.63}, 2026)
    _g = (_pa.dados, _pg.carregar)
    try:
        _pa.dados = lambda ano, hoje: (brutas, "")
        _pg.carregar = lambda: ({}, "")
        top = _vf.top_do_ano(2026, datetime(2026, 10, 20).date())
        html = _vf._top_produtos(top)
        conta("Faturamento: o top 5 sai da BASE pela cadeia real, do mais vendido ao menos",
              [t[0] for t in top][:2] == ["ARGOLA DOURADA", "MINI CANECA"] and "TOP 5 MAIS VENDIDOS" in html
              and "UC " in html, str(top))
        _pa.dados = lambda ano, hoje: ([], "Não consegui ler a BASE DE VENDAS")
        conta("Faturamento: sem a BASE o top 5 avisa, não quebra",
              "indisponível" in _vf._top_produtos(_vf.top_do_ano(2026, datetime(2026, 10, 20).date())), "")
        fonte = inspect.getsource(_vf.pagina)
        conta("Faturamento: o quadro do marketplace desenha o top 5 ao lado das plataformas",
              "_top_produtos(top_do_ano(" in fonte and "_plataformas(" in fonte, "")
        tab = inspect.getsource(_vf._tabela)
        conta("Faturamento: os números do MÊS A MÊS centralizados",
              tab.count("text-align:center") >= 2 and "text-align:right;padding:6px" not in tab, "")
    except Exception as e:
        conta("Faturamento: top 5", False, f"{type(e).__name__}: {e}")
    finally:
        _pa.dados, _pg.carregar = _g


def _produtos_nichos_padronizados(conta):
    """20/10: a segunda passada da IA dá UM nicho a cada produto ao abrir a
    página. O mapa vem na forma de `produtos_grupos.carregar` depois da
    primeira passada (origem "ia", nichos divergentes); as vendas pela
    `linhas_da_base`. Só a planilha e a chamada à IA são trocadas."""
    import datetime as _dt_n
    import produtos_analise as _pa
    import produtos_grupos as _pg_n
    import auth as _au_n
    _dono = sorted(_au_n.ADMINS_PADRAO)[0]
    cab = ['Data', 'Plataforma', 'SKU', 'Produto', 'Quantidade', 'Custo Unitário', 'FAT TOTAL',
           'DEVOLUÇÃO', 'MARGEM C.', 'LPV']
    regs = [{"Data": _dt_n.datetime(2026, m, 3), "Plataforma": "Shopee1", "SKU": "MS-900",
             "Produto": t, "Quantidade": 1, "Custo Unitário": c, "FAT TOTAL": 40.0, "DEVOLUÇÃO": 0,
             "MARGEM C.": 12.0, "LPV": 6.0}
            for m in range(1, 10) for t, c in (("ALICATE FURADOR COURO", 9.0), ("ALICATE VAZADOR CINTO", 12.0))]
    linhas = _pa.linhas_da_base(regs, cab, {m: 6.0 for m in range(1, 10)}, 2026)
    mapa = {"ALICATE FURADOR COURO": {"produto": "ALICATE FURADOR", "nicho": "Artesanato e Scrapbook", "origem": "ia"},
            "ALICATE VAZADOR CINTO": {"produto": "ALICATE FURADOR", "nicho": "Outros", "origem": "ia"}}
    _g = (_pa.dados, _pa.st, _pg_n.carregar, _pg_n.salvar, _pg_n._chamar_ia)
    _salvos, _avisos, _prompts = [], [], []
    try:
        f = instalar()
        f.segmented_control = lambda rot, opcoes, default=None, **k: (f._registra("segmented_control", k), default)[1]
        f.dialog = lambda *a, **k: (lambda fn: fn)
        f.columns = lambda spec, **k: [f] * (spec if isinstance(spec, int) else len(spec))
        f.warning = lambda t, *a, **k: _avisos.append(str(t))
        _pa.st = f
        _pa.dados = lambda ano, hoje: (linhas, "")
        _pg_n.carregar = lambda: (dict(mapa), "")
        _pg_n.salvar = _salvos.append
        _pg_n._chamar_ia = lambda p: (_prompts.append(p), ('{"0": "Artesanato e Scrapbook"}', ""))[1]
        _pa.pagina(_dono)
        _n = {g["nicho"] for g in (_salvos[-1] if _salvos else {}).values()}
        conta("Produtos: a 2ª passada dá um nicho só ao alicate dos dois custos e grava (dono, 20/10)",
              _n == {"Artesanato e Scrapbook"} and len(_prompts) == 1 and "ALICATE FURADOR" in _prompts[0],
              str(_salvos[-1:])[:200])
        _salvos.clear()
        f2 = instalar()
        f2.segmented_control = lambda rot, opcoes, default=None, **k: (f2._registra("segmented_control", k), default)[1]
        f2.dialog = f.dialog
        f2.columns = lambda spec, **k: [f2] * (spec if isinstance(spec, int) else len(spec))
        f2.warning = lambda t, *a, **k: _avisos.append(str(t))
        _pa.st = f2
        _pg_n._chamar_ia = lambda p: ("", "ANTHROPIC_API_KEY não configurada")
        _pa.pagina(_dono)
        conta("Produtos: com a IA fora, a 2ª passada avisa, não grava e a página monta",
              _salvos == [] and any("não padronizou" in a for a in _avisos), str(_avisos[-2:]))
    except (_Rerun, _Parou):
        conta("Produtos: nichos padronizados — a tela monta", True, "")
    except Exception as e:
        conta("Produtos: nichos padronizados — a tela monta", False, f"{type(e).__name__}: {e}")
    finally:
        _pa.dados, _pa.st, _pg_n.carregar, _pg_n.salvar, _pg_n._chamar_ia = _g


def _mercado_livre_no_admin(conta):
    """20/10: Administrativo › Mercado Livre — as quatro contas, cada uma com
    o seu botão, e a autorizada mostrando a conta do ML a que está ligada.
    Só a planilha e as credenciais são trocadas (`ml_api._todas`,
    `ml_api.credenciais`); o registro tem as colunas de `ml_api.COLUNAS`."""
    import admin as _adm_ml
    import ml_api as _ml_t
    _g = (_adm_ml.st, _ml_t.credenciais, _ml_t._todas, _ml_t.convites, _ml_t._gravar_na_planilha)
    _md, _bot, _leituras, _av, _grav = [], [], [], [], []
    try:
        f = instalar()
        f.markdown = lambda t, *a, **k: _md.append(str(t))
        f.success = lambda t, *a, **k: _md.append(str(t))
        f.warning = lambda t, *a, **k: _av.append(str(t))
        f.button = lambda rot, *a, **k: (f._registra("button", k), _bot.append(k.get("key")),
                                         k.get("key") in ("ml_teste_ler", "ml_autorizar_ml2"))[2]
        f.radio = lambda rot, opcoes, *a, **k: (f._registra("radio", k), list(opcoes)[0])[1]
        _adm_ml.st = f
        _ml_t.credenciais = lambda: ("1", "2")
        _ml_t._gravar_na_planilha = lambda c, d: (_grav.append((c, d)), True)[1]
        _reg = {c: "" for c in _ml_t.COLUNAS}
        _reg.update({"conta": "ml1", "refresh_token": "R", "access_token": "A",
                     "expira_em": 9e12, "user_id": "999", "apelido": "LOJA1"})
        _ml_t._todas = lambda: (_leituras.append(1), {"ml1": _reg})[1]
        _ml_t.convites = lambda c: ([{"type": "DEAL"}, {"type": "DEAL"}, {"type": "PRICE_DISCOUNT"}], "")
        _adm_ml._secao_mercado_livre()
        _j = " ".join(_md)
        conta("Mercado Livre: as quatro contas com botão, e a ML1 mostra a conta a que está ligada",
              all(f"ml_autorizar_{c}" in _bot for c in _ml_t.CONTAS) and "LOJA1" in _j
              and "não autorizada" in _j, str(_bot))
        _link = [t for t in _md if "Abrir a autorização do Mercado Livre — ML2" in t]
        conta("Mercado Livre: o botão da ML2 grava o state dela ANTES e devolve o link com ele",
              _grav and _grav[0][0] == "ml2" and _grav[0][1]["state_pendente"].startswith("ml2.")
              and _link and _grav[0][1]["state_pendente"] in _link[0]
              and _ml_t.url_de_autorizacao.__name__ == "url_de_autorizacao", str(_grav)[:200])
        conta("Mercado Livre: `estados` resume as quatro com uma leitura e sem o token",
              (lambda e: sorted(e) == list(_ml_t.CONTAS) and "access_token" not in e["ml1"])(_ml_t.estados()), "")
        _leituras.pop()
        conta("Mercado Livre: a tela lê a planilha UMA vez por passada (não uma por conta)",
              len(_leituras) == 1, f"{len(_leituras)} leituras")
        conta("Mercado Livre: conferir a leitura conta as promoções da conta autorizada",
              "3 promoção(ões)" in _j, _j[-200:])
        f2 = instalar()
        f2.warning = lambda t, *a, **k: _av.append(str(t))
        _adm_ml.st = f2
        _ml_t.credenciais = lambda: ("", "")
        _adm_ml._secao_mercado_livre()
        conta("Mercado Livre: sem as variáveis no Railway, a tela diz quais faltam",
              any("ML_CLIENT_ID" in a for a in _av), str(_av))
        _app = open("app.py", encoding="utf-8").read()
        _i_cb, _i_login = _app.find("_ml_cb.processar_callback(st.query_params)"), _app.find("usuario_logado = auth.verificar_login()")
        conta("Mercado Livre: a volta da autorização é tratada ANTES do login (o code vence em minutos)",
              0 < _i_cb < _i_login, f"callback em {_i_cb}, login em {_i_login}")
    except (_Rerun, _Parou):
        conta("Mercado Livre: a seção monta", True, "")
    except Exception as e:
        conta("Mercado Livre: a seção monta", False, f"{type(e).__name__}: {e}")
    finally:
        _adm_ml.st, _ml_t.credenciais, _ml_t._todas, _ml_t.convites, _ml_t._gravar_na_planilha = _g


def _ranking_abre_panorama(conta):
    """20/10: clicar numa linha do ranking abre o panorama aprovado. O
    clique chega como `?pa_abrir=<código>` (conferido num Streamlit de
    verdade: mesma aba, login e seção mantidos). As vendas pela
    `linhas_da_base`; só a planilha é trocada."""
    import datetime as _dt_r
    import produtos_analise as _pa
    import produtos_grupos as _pg_r
    import auth as _au_r
    _dono = sorted(_au_r.ADMINS_PADRAO)[0]
    cab = ['Data', 'Plataforma', 'SKU', 'Produto', 'Quantidade', 'Custo Unitário', 'FAT TOTAL',
           'DEVOLUÇÃO', 'MARGEM C.', 'LPV']
    regs = [{"Data": _dt_r.datetime(2026, m, d), "Plataforma": "MercadoLivre1", "SKU": "MS-8936",
             "Produto": "CINZEIRO TELESCÓPICO", "Quantidade": 1, "Custo Unitário": 89.36, "FAT TOTAL": 200.0,
             "DEVOLUÇÃO": 0, "MARGEM C.": 45.0, "LPV": 18.0} for m in range(1, 10) for d in range(1, 6)]
    linhas = _pa.linhas_da_base(regs, cab, {m: 18.0 for m in range(1, 10)}, 2026)
    _g = (_pa.dados, _pa.st, _pg_r.carregar)
    _md, _dlg = [], []
    try:
        f = instalar()
        f.segmented_control = lambda rot, opcoes, default=None, **k: (f._registra("segmented_control", k), default)[1]
        f.dialog = lambda titulo, *a, **k: (_dlg.append(titulo), (lambda fn: fn))[1]
        f.columns = lambda spec, **k: [f] * (spec if isinstance(spec, int) else len(spec))
        f.markdown = lambda t, *a, **k: _md.append(str(t))
        _cod = _pa.codigo("CINZEIRO TELESCÓPICO")
        # 27/10: a linha deixou de ser link (link recarrega a página). O
        # clique é o botão escondido daquela linha — o fake o aperta.
        import clique as _clq_r
        _bt_alvo = "bt_" + _clq_r.ident("pa", "CINZEIRO TELESCÓPICO")
        f.button = lambda rot, *a, **k: (f._registra("button", k), k.get("key") == _bt_alvo)[1]
        f.query_params = {"_s": "tok", "secao": "gestao"}
        _pa.st = f
        _g_clq = _clq_r._ponte
        _clq_r._ponte = lambda: None
        _pa.dados = lambda ano, hoje: (linhas, "")
        _pg_r.carregar = lambda: ({"CINZEIRO TELESCÓPICO": {"produto": "CINZEIRO TELESCÓPICO", "nicho": "Tabacaria",
                                                              "origem": "manual"}}, "")
        _pa.pagina(_dono)
        _j = " ".join(_md)
        conta("Produtos: cada linha do ranking é alvo de clique, sem link e sem token no HTML (27/10)",
              _clq_r.alvo("pa", "CINZEIRO TELESCÓPICO") in _j and "href=" not in _j
              and "_s=tok" not in _j, "")
        conta("Produtos: Por nicho com o nome das colunas e o R$ dos alertas dito lucro (dono, 20/10)",
              all(x in _j for x in (">Fatia do lucro<", ">Faturamento<", ">Lucro<")) and "— lucro <b" in _j, "")
        conta("Produtos: o clique na linha abre o panorama do produto, sem recarregar a página",
              "Panorama do produto" in _dlg and "PANORAMA DO PRODUTO" in _j, str(_dlg))
    except (_Rerun, _Parou):
        conta("Produtos: ranking clicável — a tela monta", True, "")
    except Exception as e:
        conta("Produtos: ranking clicável — a tela monta", False, f"{type(e).__name__}: {e}")
    finally:
        _pa.dados, _pa.st, _pg_r.carregar = _g
        try:
            _clq_r._ponte = _g_clq
        except NameError:
            pass


def _celular(conta):
    """21/10: no celular a barra lateral deixava uma faixa por cima do
    conteúdo e não havia botão para abrir nem fechar (print do dono).
    Conferido num Streamlit de verdade com tela de iPhone: recolhida some
    inteira, » abre, « fecha. Aqui a guarda lê o CSS do `app.py`."""
    import re as _re_c
    _css = open("app.py", encoding="utf-8").read()
    _css = _css[_css.index("<style>"):_css.index("</style>")]
    _i = _css.index("@media screen and (max-width: 768px)")
    _cel = _css[_i:]
    _fora = _css[:_css.index("@media screen and (min-width: 769px)")]
    conta("Celular: a largura fixa de 360px da barra lateral vale só no computador",
          not _re_c.search(r'section\[data-testid="stSidebar"\]\s*\{[^}]*width:\s*360px', _fora), "")
    conta("Celular: recolhida, a barra some inteira, e os botões de abrir e fechar aparecem",
          'section[data-testid="stSidebar"][aria-expanded="false"]' in _cel
          and "translateX(-110%)" in _cel
          and _re_c.search(r'header\[data-testid="stHeader"\]\s*\{\s*display:\s*block', _cel)
          and '[data-testid="stSidebarCollapseButton"] { display: flex !important; }' in _cel, "")
    conta("Celular: os painéis da Home empilham em uma coluna",
          "grid-template-areas: 'fat' 'ind' 'gas' 'dev'" in _cel, "")


def _rastreio_etiquetas(conta):
    """21/10: Registros › Rastrear etiquetas — quem tirou o INTERROMPIDO.
    O Trello é trocado por dados na forma da API: cartão com idLabels, ações
    updateCard com data.old.idLabels e idMemberCreator."""
    import admin as _adm_r
    import placar_core as _pc_r
    _g = (_adm_r.st, _pc_r._buscar_board, _pc_r._buscar_acoes_board, _pc_r.mapa_labels, dict(_pc_r.ALINHAMENTO_OLD))
    _tab, _info = [], []
    try:
        f = instalar()
        f.text_input = lambda rot, *a, **k: (f._registra("text_input", k), "matriokas")[1]
        f.button = lambda rot, *a, **k: (f._registra("button", k), k.get("key") == "rast_ok")[1]
        f.dataframe = lambda d, *a, **k: _tab.append(d)
        f.info = lambda t, *a, **k: _info.append(str(t))
        _adm_r.st = f
        card = {"id": "c1", "name": "BONECAS MATRIOKAS", "idLabels": ["EA"], "idMembers": ["m1"]}
        up = lambda q, ids, a: {"type": "updateCard", "date": q, "idMemberCreator": a,
                                "data": {"card": {"id": "c1", "idLabels": ids}, "old": {"idLabels": ids}}}
        _pc_r._buscar_board = lambda: ({}, [card], {"m1": "luizhenriqueramos", "m2": "beatriz51"}, None, None, None)
        _pc_r._buscar_acoes_board = lambda *a, **k: {"c1": [up("2026-10-21T15:00:00.000Z", ["EA", "INT"], "m1"),
                                                         up("2026-10-21T16:00:00.000Z", ["EA"], "m2")]}
        _pc_r.mapa_labels = lambda forcar=False: {"EA": "EM ANDAMENTO", "INT": "INTERROMPIDO"}
        _adm_r._secao_rastreio_etiquetas()
        _linhas = _tab[0].to_dict("records") if _tab else []
        conta("Rastreio: o cartão buscado mostra quem tirou o INTERROMPIDO e quando (dono, 21/10)",
              any(x["etiqueta"] == "INTERROMPIDO" and x["o que"] == "tirou" and x["quem"] == "beatriz51"
                  for x in _linhas), str(_linhas)[:200])
        _pc_r._buscar_board = lambda: ({}, [], {}, None, None, None)
        f2 = instalar()
        f2.text_input = lambda rot, *a, **k: (f2._registra("text_input", k), "matriokas")[1]
        f2.button = lambda rot, *a, **k: (f2._registra("button", k), k.get("key") == "rast_ok")[1]
        f2.info = lambda t, *a, **k: _info.append(str(t))
        _adm_r.st = f2
        _adm_r._secao_rastreio_etiquetas()
        conta("Rastreio: nome que não existe avisa, não quebra", any("Nenhum cartão" in t for t in _info), "")
    except (_Rerun, _Parou):
        conta("Rastreio: a seção monta", True, "")
    except Exception as e:
        conta("Rastreio: a seção monta", False, f"{type(e).__name__}: {e}")
    finally:
        _adm_r.st, _pc_r._buscar_board, _pc_r._buscar_acoes_board, _pc_r.mapa_labels = _g[:4]
        _pc_r.ALINHAMENTO_OLD.clear(); _pc_r.ALINHAMENTO_OLD.update(_g[4])


def _lembrete_pago_no_extrato(conta):
    """23/10: o lembrete que o extrato já mostra pago sai do quadro, e o
    quadro diz numa linha o que tirou. Segunda 19/10: vencem o DAS, os demais
    impostos e a TM do dia 20. Só a planilha é trocada: os lançamentos têm a
    forma de `lancamentos.do_mes`."""
    import lembretes as _lem2
    import lancamentos as _lan2
    import cheques as _ch2
    import nao_operacional as _no2
    import pandas as _pd2
    from datetime import date as _d2
    _g = (_lem2.carregar_feitos, _ch2.carregar, _no2.carregar, _lan2.do_mes)
    _txt, _bot = [], []
    try:
        f = instalar()
        f.markdown = lambda t, *a, **k: _txt.append(str(t))
        f.caption = lambda t, *a, **k: _txt.append(str(t))
        f.button = lambda rot, *a, **k: (f._registra("button", k), _bot.append(k.get("key")), False)[2]
        _lem2.carregar_feitos = lambda: (frozenset(), "")
        _ch2.carregar = lambda: []
        _no2.carregar = lambda: _pd2.DataFrame()
        _lan2.do_mes = lambda a, m, lista=None: ([{"data": "2026-10-19", "valor": -1520.33,
                                                  "favorecido": "RECEITA FEDERAL", "descricao": "",
                                                  "finalidade": "IMPOSTO"}] if (a, m) == (2026, 10) else [])
        _lem2.mostrar(f, "leo", _d2(2026, 10, 19))
        _j = " ".join(_txt)
        conta("Lembretes: o DAS já pago no extrato sai do quadro; demais impostos e TM ficam (dono, 23/10)",
              not any(str(b).startswith("lem_das_20|") for b in _bot)
              and any(str(b).startswith("lem_impostos_20|") for b in _bot)
              and any(str(b).startswith("lem_tm_20|") for b in _bot), str(_bot))
        conta("Lembretes: o quadro diz o que tirou e por quê",
              "Já pagos, retirados pelo extrato" in _j and "DAS" in _j and "visto no extrato 19/10" in _j, _j[-200:])
    except (_Rerun, _Parou):
        conta("Lembretes: pago no extrato — a tela monta", True, "")
    except Exception as e:
        conta("Lembretes: pago no extrato — a tela monta", False, f"{type(e).__name__}: {e}")
    finally:
        _lem2.carregar_feitos, _ch2.carregar, _no2.carregar, _lan2.do_mes = _g



def _amostra_ml_no_admin(conta):
    """24/10: Registros › Mercado Livre › "Baixar amostra" — a resposta inteira
    do ML vai num arquivo, sem token, e a leitura só roda no clique. Só a rede
    (`ml_api.get`), a planilha e as credenciais são trocadas."""
    import admin as _adm_am
    import ml_api as _ml_am
    _g = (_adm_am.st, _ml_am.credenciais, _ml_am._todas, _ml_am.get,
          _ml_am._ler_da_planilha)
    _bot, _baixou, _rede = [], [], []
    try:
        f = instalar()
        f.button = lambda rot, *a, **k: (f._registra("button", k), _bot.append(k.get("key")),
                                         k.get("key") == "ml_amostra_gerar")[2]
        f.radio = lambda rot, opcoes, *a, **k: (f._registra("radio", k), list(opcoes)[0])[1]
        f.text_input = lambda rot, *a, **k: (f._registra("text_input", k), "#2894660789")[1]
        f.download_button = lambda rot, data, *a, **k: (f._registra("download_button", k),
                                                        _baixou.append((k.get("file_name"), data)))
        _adm_am.st = f
        _ml_am.credenciais = lambda: ("1", "2")
        _reg = {c: "" for c in _ml_am.COLUNAS}
        _reg.update({"conta": "ml1", "refresh_token": "R", "access_token": "A",
                     "expira_em": 9e12, "user_id": "233026091", "apelido": "MARTINSOUSA_1"})
        _ml_am._todas = lambda: {"ml1": _reg}
        _ml_am._ler_da_planilha = lambda c: _reg

        def _get(c, caminho, params=None):
            _rede.append(caminho)
            if caminho.startswith("/seller-promotions/users/"):
                return ({"results": [{"id": "P1", "status": "started", "type": "SMART"}]}, "")
            return ({"id": "x", "access_token": "NAO-PODE-SAIR"}, "")
        _ml_am.get = _get
        _adm_am._secao_mercado_livre()
        _nome, _txt = (_baixou or [("", "")])[0]
        conta("Amostra ML: o clique baixa a resposta inteira num .json da conta, sem token",
              _nome.startswith("amostra_ml1_") and _nome.endswith(".json")
              and '"promocoes_da_conta"' in _txt and "NAO-PODE-SAIR" not in _txt, _nome)
        conta("Amostra ML: o # digitado vira o anúncio lido (MLB…)",
              "/items/MLB2894660789" in _rede, str(_rede))
        _n_antes = len(_rede)
        f2 = instalar()
        f2.radio = lambda rot, opcoes, *a, **k: (f2._registra("radio", k), list(opcoes)[0])[1]
        f2.button = lambda rot, *a, **k: (f2._registra("button", k), False)[1]
        f2.text_input = lambda rot, *a, **k: (f2._registra("text_input", k), "")[1]
        f2.download_button = lambda *a, **k: f2._registra("download_button", k)
        _adm_am.st = f2
        _adm_am._secao_mercado_livre()
        conta("Amostra ML: sem clique, nenhuma chamada ao ML no desenho da tela",
              len(_rede) == _n_antes, f"{len(_rede) - _n_antes} chamadas")
    except Exception as e:
        conta("Amostra ML: a tela monta", False, f"{type(e).__name__}: {e}")
    finally:
        (_adm_am.st, _ml_am.credenciais, _ml_am._todas, _ml_am.get,
         _ml_am._ler_da_planilha) = _g


def _meu_desempenho(conta):
    """24/10: a primeira tela do colaborador. Só a rede é trocada: o board
    (Trello), o mapa de batidas (RHiD) e a apuração do mês, que aqui sai da
    MESMA `apuracao_bonus` da Análise de Metas, com dado do formato real."""
    import meu_desempenho as _md
    import analise_metas as _am_md
    import batidas as _bat_md
    import placar_core as _pc_md
    from datetime import datetime as _dt_md
    _g = (_md.st, _md.resumo_do_mes, _pc_md._buscar_board, _bat_md.mapa,
          _pc_md.username_do_login, dict(_pc_md.MEMBROS_ATIVOS))
    _txt = []
    try:
        f = instalar()
        for _k in ("markdown", "error", "warning", "success", "caption", "info"):
            setattr(f, _k, (lambda k: lambda t, *a, **kw: _txt.append(f"{k}:{t}"))(_k))
        _md.st = f
        _pc_md.MEMBROS_ATIVOS.clear()
        _pc_md.MEMBROS_ATIVOS.update({"beatriz51": "Beatriz Souza", "luiz": "Luiz"})
        _pc_md.username_do_login = lambda u: "beatriz51"
        _dados = [{"filtro_mes": (2026, 10), "pts_membro": {"beatriz51": 600.0, "luiz": 900.0},
                   "cfg": {"meta_beatriz51": 1000, "meta_luiz": 1000}, "saldo": 1500.0,
                   "meta_eq": 5000.0, "meta_maxx": 6000.0, "pen_qtd": 0}]
        _bon = _am_md.apuracao_bonus(_dados, ["beatriz51", "luiz"], pont={}, ocio={},
                                     tem_ponto=False, medias_exec={})
        _pont = {"beatriz51": {"pend": [{"data": "2026-10-09", "tipo": "sem_batida",
                                         "batidas": []}]}}
        _res = {"beatriz51": _md.resumo_da_pessoa(
            "beatriz51", _dados, _bon, _pont, _dt_md(2026, 10, 26, 10, tzinfo=_pc_md.FUSO))}
        _md.resumo_do_mes = lambda a, m: _res
        _li = {"L1": "PRODUÇÃO", "L2": "DESATIVAR ANÚNCIOS"}
        _cards = [{"name": "Caneca", "idList": "L1", "idMembers": ["m1"],
                   "labels": [{"name": "EM ANDAMENTO"}]},
                  {"name": "Porta-relógios", "idList": "L1", "idMembers": ["m1"],
                   "labels": [{"name": "EM ANDAMENTO"}]}]
        _pc_md._buscar_board = lambda: (_li, _cards, {"m1": "beatriz51"}, None, None, None)
        _md.pagina("Beatriz")
        _j = " ".join(_txt)
        conta("Meu desempenho: a tela monta com saudação, meta e meta coletiva",
              "Olá, Beatriz" in _j and "600" in _j and "1.500" in _j, _j[:200])
        conta("Meu desempenho: a pontuação reprovada aparece no que puxa a meta",
              "Pontuação (600 de 1.000 pts)" in _j and "Fora da meta coletiva" in _j, _j[-300:])
        conta("Meu desempenho: o dia sem batida pede abono",
              "09/10" in _j and "abono" in _j, "")
        conta("Meu desempenho: duas demandas fora do Desativar geram o aviso",
              "2 demandas ao mesmo tempo" in _j, "")
        # Sem cartão rodando e dentro do expediente batido: ociosidade agora.
        _txt.clear()
        _cards[:] = []
        _agora = _pc_md.agora_br()
        _bat_md.mapa = lambda *a, **k: {"beatriz51": {_agora.date(): {
            "entrada": (_agora.replace(second=0, microsecond=0)
                        - __import__("datetime").timedelta(minutes=30)).strftime("%H:%M")}}}
        f2 = instalar()
        for _k in ("markdown", "error", "warning", "success", "caption", "info"):
            setattr(f2, _k, (lambda k: lambda t, *a, **kw: _txt.append(f"{k}:{t}"))(_k))
        _md.st = f2
        _md.pagina("Beatriz")
        _j2 = " ".join(_txt)
        conta("Meu desempenho: no expediente e sem cartão rodando, a ociosidade avisa",
              "Ociosidade detectada e sendo contabilizada" in _j2
              or _agora.hour < 1, _j2[:200])
    except Exception as e:
        conta("Meu desempenho: a tela monta", False, f"{type(e).__name__}: {e}")
    finally:
        (_md.st, _md.resumo_do_mes, _pc_md._buscar_board, _bat_md.mapa,
         _pc_md.username_do_login, _m) = _g
        _pc_md.MEMBROS_ATIVOS.clear()
        _pc_md.MEMBROS_ATIVOS.update(_m)


def _custos_do_studio(conta):
    """27/10: Financeiro › Custos do Studio. Só a planilha é trocada: os
    lançamentos (na forma de `lancamentos.carregar`) e o registro de uso."""
    import custos_studio as _cs
    import lancamentos as _lan_cs
    import uso_ia as _uso_cs
    import auth as _auth_cs
    import placar_core as _pc_cs
    _g = (_cs.st, _lan_cs.carregar, _uso_cs.carregar, _auth_cs.eh_dono)
    _txt = []
    try:
        f = instalar()
        for _k in ("markdown", "error", "warning", "caption", "info"):
            setattr(f, _k, (lambda k: lambda t, *a, **kw: _txt.append(f"{k}:{t}"))(_k))
        _cs.st = f
        _auth_cs.eh_dono = lambda u: True
        _hj = _pc_cs.agora_br()
        _fat = f"fatura {_hj.year:04d}-{_hj.month:02d}"
        _dia = f"{_hj.year:04d}-{_hj.month:02d}-01"
        _lan_cs.carregar = lambda: [
            {"id": "1", "data": _dia, "descricao": "GOOGLE CLOUD", "valor": 480.0, "tipo": _fat},
            {"id": "2", "data": _dia, "descricao": "OPENAI", "valor": 120.0, "tipo": _fat},
            {"id": "3", "data": _dia, "descricao": "ANTHROPIC", "valor": 200.0, "tipo": _fat}]
        _uso_cs.carregar = lambda: [
            {"quando": f"{_dia} 10:00:00", "usuario": "beatriz", "ferramenta": "Descrição",
             "servico": "Anthropic", "entrada": 1000, "saida": 0, "unidades": 0}]
        _cs._lancamentos_por_mes.clear()
        _cs.pagina("MartinSousa")
        _j = " ".join(_txt)
        conta("Custos do Studio: a tela monta com o gráfico e a composição do mês",
              "<svg" in _j and "Gemini</b> R$ 480" in _j, _j[:200])
        conta("Custos do Studio: Gemini acima da OpenAI acende o alerta da reserva",
              "só a reserva das imagens" in _j, "")
    except Exception as e:
        conta("Custos do Studio: a tela monta", False, f"{type(e).__name__}: {e}")
    finally:
        _cs.st, _lan_cs.carregar, _uso_cs.carregar, _auth_cs.eh_dono = _g
        try:
            _cs._lancamentos_por_mes.clear()
        except Exception:
            pass

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
    _novo_produto(conta)
    _chat_no_centro(conta)
    _fotos_que_o_chat_nao_via(conta)
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
    _aba_faturas(conta)
    _assinaturas_no_operacional(conta)
    _projecao_na_meta(conta)
    _monique_nos_gestores(conta)
    _alerta_de_coluna_na_tv(conta)
    _finalidades_em_massa(conta)
    _resumo_mensal(conta)
    _salvar_metas(conta)
    _devolucoes_da_planilha(conta)
    _equilibrio_real_na_meta(conta)
    _acompanhamento_do_mes(conta)
    _inter_pela_api(conta)
    _co_proporcional_na_viabilidade(conta)
    _boletos_na_tela(conta)
    _historico_na_home(conta)
    _lembretes_na_home(conta)
    _visao_geral(conta)
    _visao_faturamento(conta)
    _visao_geral_na_home(conta)
    _tiktok_na_viabilidade(conta)
    _din_financas_previa(conta)
    _produtos_analise(conta)
    _gargalos_volume(conta)
    _faturamento_top5(conta)
    _produtos_nichos_padronizados(conta)
    _mercado_livre_no_admin(conta)
    _amostra_ml_no_admin(conta)
    _meu_desempenho(conta)
    _custos_do_studio(conta)
    _ranking_abre_panorama(conta)
    _celular(conta)
    _rastreio_etiquetas(conta)
    _lembrete_pago_no_extrato(conta)
    print(f"\n{'ok    a tela monta' if not falhas else 'FALHA'} "
          f"· {len(falhas)} tela(s) quebrada(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
