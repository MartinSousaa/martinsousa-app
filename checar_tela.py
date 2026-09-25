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
        self.secrets = {}
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


def main():
    instalar()
    falhas = []

    def conta(nome, ok, detalhe):
        if not ok:
            falhas.append((nome, detalhe))
        print(("ok    " if ok else "FALHA ") + nome
              + (f"\n      {detalhe}" if detalhe else ""))

    _home(falhas, conta)
    _extratos(conta)
    _gargalos(conta)
    print(f"\n{'ok    a tela monta' if not falhas else 'FALHA'} "
          f"· {len(falhas)} tela(s) quebrada(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
