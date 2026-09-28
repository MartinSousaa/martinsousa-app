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

import sys
import types


class ChaveRepetida(Exception):
    """O mesmo `key=` duas vezes — é o erro que o Streamlit dá em produção."""


class _Falso:
    """Um Streamlit de mentira. Tudo devolve algo; nada vai para a rede."""

    def __init__(self, chaves=None):
        # As chaves são compartilhadas entre o módulo e as colunas/containers:
        # o Streamlit de verdade também as vê como um espaço só.
        self._chaves = {} if chaves is None else chaves
        self.session_state = _Estado()
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
    """`st.session_state`: dicionário que também responde por atributo."""

    def __getattr__(self, k):
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v

    def get(self, k, padrao=None):
        return dict.get(self, k, padrao)


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
                   "L3": "CONFERENCIA VÍDEO (10)"}
        _cf = lambda v: [{"idCustomField": "idp", "value": {"number": str(v)}}]
        _cards = [
            # SOMA: concluido, em lista que pontua, com o campo PONTOS.
            {"id": "c1", "name": "Desativar carimbos", "idList": "L1",
             "idMembers": [], "labels": [], "idLabels": [], "due": None,
             "dueComplete": True, "customFieldItems": _cf(50),
             "dateLastActivity": "2020-01-01T00:00:00.000Z"},
            {"id": "c2", "name": "Conferência vídeo", "idList": "L3",
             "idMembers": [], "labels": [], "idLabels": [], "due": None,
             "dueComplete": True, "customFieldItems": _cf(10),
             "dateLastActivity": "2020-01-01T00:00:00.000Z"},
            # NAO SOMA: TRIAGEM esta em LISTAS_SEM_PONTUACAO.
            {"id": "c3", "name": "Na triagem", "idList": "L2",
             "idMembers": [], "labels": [], "idLabels": [], "due": None,
             "dueComplete": True, "customFieldItems": _cf(100),
             "dateLastActivity": "2020-01-01T00:00:00.000Z"},
            # NAO SOMA: o "concluido" nao esta marcado. `placar.py:621`.
            {"id": "c4", "name": "Aberto ainda", "idList": "L1",
             "idMembers": [], "labels": [], "idLabels": [], "due": None,
             "dueComplete": False, "customFieldItems": _cf(80),
             "dateLastActivity": "2020-01-01T00:00:00.000Z"},
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
              sorted(c["id"] for c in _d["cards_pts"]) == ["c1", "c2"],
              str(sorted(c["id"] for c in _d["cards_pts"])))
        conta("cada cartao traz id, nome, lista e pontos",
              all({"id", "card", "lista", "pts", "membros"} <= set(c)
                  for c in _d["cards_pts"]), "")
        # QUEM MAIS LE: ferramentas_chat.py:243 monta o saldo com estas duas
        # chaves. Acrescentar cards_pts nao pode ter mexido nelas.
        conta("ferramentas_chat continua achando pts_equipe e pen_total",
              _d.get("pts_equipe") == 60 and _d.get("pen_total") == 0,
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
    ("descricao", "pagina_descricao"),
    ("gestao", "pagina_home"),
    ("gestao", "pagina_financeiro"),
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
            getattr(_m, funcao)("martinsousa")
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
    import inspect as _insp_t
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
    _telas_restantes(conta)
    _home(falhas, conta)
    _extratos(conta)
    _gargalos(conta)
    _historico(conta)
    _faturas(conta)
    _queda_de_pontos(conta)
    _mapa_de_pontos(conta)
    _processar_cards_pts(conta)
    _chat(conta)
    _retrato_no_painel(conta)
    _historico_de_prompts(conta)
    _contexto_do_log(conta)
    _txt_consolidado(conta)
    print(f"\n{'ok    a tela monta' if not falhas else 'FALHA'} "
          f"· {len(falhas)} tela(s) quebrada(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
