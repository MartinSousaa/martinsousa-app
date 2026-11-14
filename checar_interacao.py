"""O clique custa UMA passada, e a tela fica onde a pessoa estava?

Nasceu da varredura de 13/11, pedida pelo dono: *"Eu tenho que ficar trazendo
cada erro? Não consegue rodar uma leitura geral para pegar isso antes de
acontecer?"*. No mesmo dia ele trouxe, um a um, cinco defeitos que eram o
mesmo assunto — o que acontece entre o clique e a tela redesenhada:

| Padrão | O que a pessoa viu |
|---|---|
| `st.tabs` | aprovar abono rodava o relatório da RHiD junto; a aba voltava para a primeira |
| `if botão: … st.rerun()` | cada clique desenhava a tela DUAS vezes; a passada velha ficava na tela ("duplicou a linha") |
| widget com `default=` e a mesma chave escrita no session_state | aviso amarelo, o clique seguinte se perdia (est_modo, 13/11) |
| `focus()` sem `preventScroll` | digitar a quantidade lá embaixo e clicar fora jogava a tela para o topo |
| quantidade com `value=0` | digitar 1 virava 10 |

Os outros verificadores perguntam se a tela MONTA; nenhum perguntava quanto
um clique CUSTA. Este pergunta, por AST, sem rodar nada.

COMO ELE TRATA O QUE JÁ EXISTE: o `if botão → st.rerun()` aparece em dezenas
de lugares (21 só em imagem.py, onde não se mexe sem ordem do dono). Reprovar
tudo de uma vez ensinaria a ignorar o verificador. Então há uma BASE por
arquivo — a contagem de 13/11 — e ele reprova o que PASSAR dela. A base só
desce: corrigiu um, a base desce junto, e o número velho não volta.
"""
import ast
import glob
import os
import re
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))

# A contagem de 13/11, depois da varredura. Só desce.
BASE_RERUN = {
    "imagem.py": 21, "admin.py": 7, "promocoes_ml.py": 6, "analise_metas.py": 5,
    "fatura_ml_tela.py": 4, "headcount.py": 3, "triagem.py": 3, "boletos_tela.py": 2,
    "colaboradores.py": 2, "financeiro.py": 2, "produtos_analise.py": 2,
    "relogio_ponto.py": 3, "reserva_tela.py": 2, "assinaturas_tela.py": 1,
    "atividades.py": 1, "chat_assistente.py": 1, "descricao.py": 1, "folha_tela.py": 1,
    "meu_desempenho.py": 1, "placar.py": 1,
}
# imagem.py:11266 — fora do alcance sem ordem do dono ("não mexa em imagens").
BASE_DEFAULT_KEY = {"imagem.py": 1}

WIDGETS = {"segmented_control", "radio", "selectbox", "multiselect", "text_input",
           "number_input", "checkbox", "toggle", "date_input", "time_input", "slider",
           "select_slider", "text_area", "pills"}
QTD = re.compile(r"qtd|quantidade|entrando|unidades|pe[çc]as", re.I)
# focus() que rola DE PROPÓSITO leva a marca na mesma linha.
MARCA_ROLA = "rola de propósito"


def _arquivos(raiz):
    for f in sorted(glob.glob(os.path.join(raiz, "*.py"))):
        n = os.path.basename(f)
        if n.startswith("checar_") or n == "conferir.py":
            continue
        yield n, open(f, encoding="utf-8").read()


def analisar(nome, src):
    """{padrão: [(linha, texto)]} de UM arquivo. Pura."""
    out = {"tabs": [], "rerun": [], "default_key": [], "focus": [], "zero": []}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    escritas = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if (isinstance(t, ast.Subscript) and "session_state" in ast.unparse(t.value)
                        and isinstance(t.slice, ast.Constant)):
                    escritas.add(t.slice.value)
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            a = n.func.attr
            if a == "tabs" and ast.unparse(n.func.value) in ("st", "f", "_st"):
                out["tabs"].append((n.lineno, ast.unparse(n)[:80]))
            if a in WIDGETS:
                kw = {k.arg: k.value for k in n.keywords}
                key = kw.get("key")
                if isinstance(key, ast.Constant) and key.value in escritas:
                    for d in ("default", "value", "index"):
                        if d in kw:
                            out["default_key"].append(
                                (n.lineno, f"{a}(key={key.value!r}) com {d}= e a chave escrita no session_state"))
                if a == "number_input":
                    v = kw.get("value")
                    rot = ast.unparse(n.args[0]) if n.args else ast.unparse(kw.get("label", ast.Constant("")))
                    if isinstance(v, ast.Constant) and v.value == 0 and QTD.search(rot):
                        out["zero"].append((n.lineno, f"number_input({rot[:40]}) com value=0"))
        if isinstance(n, ast.If):
            t = ast.unparse(n.test)
            if ".button(" in t or "form_submit_button(" in t:
                corpo = "\n".join(ast.unparse(x) for x in n.body)
                if "st.rerun()" in corpo:
                    out["rerun"].append((n.lineno, t[:80]))
    for i, l in enumerate(src.splitlines(), 1):
        if re.search(r"\.focus\(\s*\)", l) and MARCA_ROLA not in l:
            out["focus"].append((i, l.strip()[:80]))
    return out


def conferir(raiz=RAIZ, base_rerun=None, base_dk=None):
    """[(arquivo, linha, padrão, texto)] do que REPROVA. Pura no disco lido."""
    base_rerun = BASE_RERUN if base_rerun is None else base_rerun
    base_dk = BASE_DEFAULT_KEY if base_dk is None else base_dk
    ruins, desceu = [], []
    for nome, src in _arquivos(raiz):
        a = analisar(nome, src)
        for p in ("tabs", "focus", "zero"):
            ruins += [(nome, l, p, t) for l, t in a[p]]
        if len(a["rerun"]) > base_rerun.get(nome, 0):
            ruins += [(nome, l, "rerun", t + f"  [{len(a['rerun'])} no arquivo, base {base_rerun.get(nome, 0)}]")
                      for l, t in a["rerun"]]
        elif len(a["rerun"]) < base_rerun.get(nome, 0):
            desceu.append(f"{nome}: {len(a['rerun'])} (base {base_rerun[nome]}) — desça a BASE_RERUN")
        if len(a["default_key"]) > base_dk.get(nome, 0):
            ruins += [(nome, l, "default_key", t) for l, t in a["default_key"]]
    return ruins, desceu


EXPLICA = {
    "tabs": "st.tabs desenha TODAS as abas a cada clique e a escolhida vive só no navegador "
            "— use segmented_control com key e desenhe só a escolhida",
    "rerun": "`if botão: … st.rerun()` = duas passadas por clique — use on_click",
    "default_key": "default=/value= com a chave escrita no session_state — aviso amarelo e clique perdido; "
                   "use session_state.setdefault e tire o default=",
    "focus": "focus() sem {preventScroll: true} rola a tela até o campo — "
             f"se for de propósito, escreva «{MARCA_ROLA}» na linha",
    "zero": "quantidade nascendo em 0: digitar 1 vira 10 — use value=None",
}


if __name__ == "__main__":
    if "--autoteste" in sys.argv:
        falhas = 0

        def ok(n, c):
            global falhas
            falhas += not c
            print(("ok    " if c else "FALHA ") + n)
        # Cada defeito de 13/11, escrito como ele estava, tem de ser visto.
        _a = analisar("x.py", 'import streamlit as st\nt1, t2 = st.tabs(["a", "b"])\n')
        ok("vê o st.tabs", len(_a["tabs"]) == 1)
        _a = analisar("x.py", 'import streamlit as st\nif c4.button("Aprovar", key="k"):\n'
                              '    ok = 1\n    st.rerun() if ok else st.error("x")\n')
        ok("vê o `if botão: … st.rerun()`, inclusive no ternário", len(_a["rerun"]) == 1)
        _a = analisar("x.py", 'import streamlit as st\nc1.button("Aprovar", on_click=f)\nst.rerun()\n')
        ok("botão com on_click e rerun solto não é o padrão", _a["rerun"] == [])
        _a = analisar("x.py", 'import streamlit as st\nst.session_state["est_modo"] = "x"\n'
                              'st.segmented_control("Modo", M, default=M[0], key="est_modo")\n')
        ok("vê o default= com a chave escrita no session_state (est_modo)", len(_a["default_key"]) == 1)
        _a = analisar("x.py", 'import streamlit as st\nst.session_state.setdefault("est_modo", "x")\n'
                              'st.segmented_control("Modo", M, key="est_modo")\n')
        ok("setdefault sem default= passa", _a["default_key"] == [])
        _a = analisar("x.py", 'J = """if (i && !digitando) i.focus();"""\n')
        ok("vê o focus() sem preventScroll", len(_a["focus"]) == 1)
        _a = analisar("x.py", 'J = """i.focus({preventScroll: true});"""\n')
        ok("focus com preventScroll passa", _a["focus"] == [])
        _a = analisar("x.py", 'import streamlit as st\nst.number_input("entrando", min_value=0, value=0, key="q")\n')
        ok("vê a quantidade nascendo em 0", len(_a["zero"]) == 1)
        _a = analisar("x.py", 'import streamlit as st\nst.number_input("Salário base", value=0)\n')
        ok("valor em dinheiro com 0 não é quantidade", _a["zero"] == [])
        # A base: o que já existia passa, o NOVO reprova.
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "a.py"), "w").write(
                'import streamlit as st\nif st.button("x"):\n    st.rerun()\n')
            ruins, _ = conferir(d, {"a.py": 1}, {})
            ok("o que está na base passa", ruins == [])
            ruins, _ = conferir(d, {}, {})
            ok("um a mais que a base reprova", len(ruins) == 1 and ruins[0][2] == "rerun")
            _r, desceu = conferir(d, {"a.py": 2}, {})
            ok("a base que ficou alta é avisada, para descer", len(desceu) == 1)
        print(f"\nfalhas: {falhas}")
        sys.exit(1 if falhas else 0)

    ruins, desceu = conferir()
    for n, l, p, t in ruins:
        print(f"FALHA {n}:{l} · {p} · {t}")
        print(f"      {EXPLICA[p]}")
    for d in desceu:
        print(f"aviso {d}")
    _t = sum(BASE_RERUN.values())
    print(f"\n{'ok' if not ruins else 'FALHA'}    {len(ruins)} clique(s) caro(s) novo(s) · "
          f"dívida conhecida: {_t} `if botão → st.rerun()` em {len(BASE_RERUN)} arquivos")
    sys.exit(1 if ruins else 0)
