"""uso_ia.py — quem usou qual IA, em qual ferramenta, e quanto (dono, 27/10).

POR QUE EXISTE
--------------
O Google cobrava R$ 500 a R$ 1.000 por mês no cartão pessoal do dono, e
ninguém sabia dizer de onde vinha: o Studio não registrava uso nenhum. A tela
"Custos do Studio" (`custos_studio.py`) precisa de duas coisas, e esta é a
segunda: o PAGO vem do extrato; a DIVISÃO do pago entre ferramentas e pessoas
vem daqui.

O QUE NÃO ESTÁ AQUI, DE PROPÓSITO
---------------------------------
A geração de imagem e vídeo (OpenAI e Gemini, em `imagem.py`, `video.py`,
`ambientacao_ref.py`) não registra: o dono proibiu mexer nesses arquivos
(27/10). O custo delas aparece inteiro, pelo extrato, sem divisão por pessoa.

NUNCA DERRUBA
-------------
Registro é coadjuvante: se a planilha não responder, a resposta da IA chega do
mesmo jeito e a linha se perde. Por isso tudo aqui engole a própria exceção.
"""
from datetime import datetime

import streamlit as st

ABA = "uso_ia"
COLUNAS = ["quando", "usuario", "ferramenta", "servico", "modelo",
           "entrada", "saida", "unidades"]


def tokens_de(resp):
    """(entrada, saída) da resposta do SDK da Anthropic. (0, 0) sem dado. Pura."""
    u = getattr(resp, "usage", None)
    if u is None and isinstance(resp, dict):
        u = resp.get("usage")
    if u is None:
        return 0, 0

    def _g(nome):
        v = u.get(nome) if isinstance(u, dict) else getattr(u, nome, 0)
        try:
            return int(v or 0)
        except (TypeError, ValueError):
            return 0
    # O cache de prompt cobra à parte, mas cobra: a leitura e a escrita no
    # cache somam na entrada, senão o chat (que usa cache) pareceria de graça.
    entrada = (_g("input_tokens") + _g("cache_creation_input_tokens")
               + _g("cache_read_input_tokens"))
    return entrada, _g("output_tokens")


def linha(ferramenta, servico, modelo, resp=None, unidades=0, usuario="",
          agora=None):
    """A linha que vai à planilha, na ordem de COLUNAS. Pura."""
    import placar_core as _pc
    agora = agora or datetime.now(_pc.FUSO)
    ent, sai = tokens_de(resp) if resp is not None else (0, 0)
    return [agora.strftime("%Y-%m-%d %H:%M:%S"), str(usuario or ""),
            str(ferramenta), str(servico), str(modelo or ""),
            ent, sai, int(unidades or 0)]


def _usuario():
    # Estas ferramentas rodam na thread da tela (nenhuma abre Thread), onde o
    # session_state existe. Fora dela volta "" — e a linha fica sem dono,
    # em vez de a chamada quebrar.
    try:
        return str(st.session_state.get("usuario_logado", "") or "")
    except Exception:
        return ""


@st.cache_resource
def _aba():
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        return planilha.worksheet(ABA)
    except Exception:
        aba = planilha.add_worksheet(title=ABA, rows=5000, cols=len(COLUNAS))
        aba.append_row(COLUNAS, value_input_option="RAW")
        return aba


def registrar(ferramenta, servico, modelo, resp=None, unidades=0):
    """Grava uma chamada. Nunca levanta."""
    try:
        _aba().append_row(linha(ferramenta, servico, modelo, resp, unidades,
                                _usuario()), value_input_option="RAW")
    except Exception:
        pass


@st.cache_data(ttl=300, show_spinner=False)
def carregar():
    """Todas as linhas registradas, como dicionários. [] em qualquer falha."""
    try:
        return _aba().get_all_records()
    except Exception:
        return []


if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    class _U:   # a forma do `usage` do SDK da Anthropic
        input_tokens, output_tokens = 1200, 300
        cache_creation_input_tokens, cache_read_input_tokens = 0, 5000

    class _R:
        usage = _U()
    ok("tokens: cache lido e escrito entram na entrada", tokens_de(_R()) == (6200, 300))
    ok("tokens: resposta sem usage não derruba", tokens_de(object()) == (0, 0))
    ok("tokens: aceita o dicionário cru da API",
       tokens_de({"usage": {"input_tokens": 10, "output_tokens": 2}}) == (10, 2))
    import placar_core as _pc_t
    _l = linha("Descrição", "Anthropic", "claude-sonnet-4-6", _R(), usuario="beatriz",
               agora=datetime(2026, 10, 27, 10, 5, tzinfo=_pc_t.FUSO))
    ok("linha: na ordem das colunas, com o dono da chamada",
       _l == ["2026-10-27 10:05:00", "beatriz", "Descrição", "Anthropic",
              "claude-sonnet-4-6", 6200, 300, 0] and len(_l) == len(COLUNAS))
    ok("linha: pesquisa sem tokens conta uma unidade",
       linha("Pesquisa", "SerpAPI", "", unidades=1)[-3:] == [0, 0, 1])

    # NUNCA DERRUBA: planilha fora do ar e a chamada segue.
    _orig = globals()["_aba"]
    globals()["_aba"] = lambda: (_ for _ in ()).throw(RuntimeError("fora do ar"))
    try:
        registrar("Título", "Anthropic", "x", _R())
        ok("registrar: planilha fora do ar não derruba quem chamou", True)
    except Exception:
        ok("registrar: planilha fora do ar não derruba quem chamou", False)
    finally:
        globals()["_aba"] = _orig
    # TODA CHAMADA REGISTRA, em todo irmão (Forma 1): uma ferramenta nova que
    # chama a Anthropic sem registrar sumiria da tela de custos em silêncio.
    # Por AST, contando chamadas e registros em cada arquivo. Os de imagem
    # ficam fora: o dono proibiu mexer neles (27/10).
    import ast as _ast_u
    for _arq in ("tit_ml.py", "palavras_chave.py", "descricao.py",
                 "produtos_grupos.py", "chat_assistente.py"):
        _arv = _ast_u.parse(open(_arq, encoding="utf-8").read())
        _cria = sum(1 for n in _ast_u.walk(_arv) if isinstance(n, _ast_u.Call)
                    and getattr(n.func, "attr", "") == "create"
                    and getattr(getattr(n.func, "value", None), "attr", "") == "messages")
        _reg = sum(1 for n in _ast_u.walk(_arv) if isinstance(n, _ast_u.Call)
                   and getattr(n.func, "attr", "") == "registrar")
        ok(f"{_arq}: cada chamada à Anthropic registra o uso ({_cria} e {_reg})",
           _cria > 0 and _reg >= _cria)
    print("\nfalhas:", falhas)
    raise SystemExit(1 if falhas else 0)
