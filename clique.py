"""clique.py — clique em HTML que NÃO recarrega a página (27/10).

O DEFEITO QUE ISTO TIRA
-----------------------
As linhas do ranking de Produtos e os quadrados da meta de gastos eram links
`<a href="?…" target="_self">`. Clicar um link é NAVEGAR: o navegador joga a
página fora e carrega o Studio do zero — sessão nova, ~9 s de boot, a sub-aba
volta para o Painel, às vezes pede login, e o `_s` (o token de login) ia
dentro de cada link. Diagnóstico do dono pela extensão do Chrome, 27/10.

O protocolo deixou passar: `checar_tela` usa um Streamlit de mentira e só
conferia que o link existia no HTML; navegação de página ele não vê.

COMO FUNCIONA
-------------
O HTML continua desenhado igual; o elemento clicável ganha `data-clique`.
Para cada um existe um `st.button` escondido. Um script (uma vez por página)
escuta o clique no documento e aperta o botão do mesmo id — e um botão é um
rerun do Streamlit, com a sessão inteira de pé. Conferido num Streamlit 1.46
de verdade, com navegador: nenhuma navegação de página em quatro cliques.
"""
import hashlib

_SCRIPT = """<script>
const P = window.parent;
if (!P.__msPonteClique) {
  P.__msPonteClique = true;
  P.document.addEventListener('click', function (e) {
    const t = e.target.closest('[data-clique]');
    if (!t) return;
    const b = P.document.querySelector('.st-key-clk_' + t.dataset.clique + ' button');
    if (b) { e.preventDefault(); b.click(); }
  }, true);
}
</script>"""


def ident(grupo, chave):
    """O id do alvo: só letras e números, o que vira classe CSS sem susto. Pura."""
    return grupo + hashlib.md5(str(chave).encode("utf-8")).hexdigest()[:10]


def alvo(grupo, chave):
    """O atributo que torna um elemento HTML clicável. Pura."""
    return f'data-clique="{ident(grupo, chave)}"'


def botoes(grupo, chaves):
    """Desenha os botões escondidos do grupo e a ponte. A chave clicada, ou None.

    Chamar DEPOIS do HTML que tem os alvos, uma vez por grupo e por passada.
    O `streamlit` é buscado na hora, e não no import: quem troca o módulo
    (a conferência da tela) troca para todos.
    """
    import streamlit as st
    st.markdown('<style>[class*="st-key-clk_"]{display:none !important}</style>',
                unsafe_allow_html=True)
    clicada = None
    for ch in dict.fromkeys(chaves):
        i = ident(grupo, ch)
        with st.container(key=f"clk_{i}"):
            if st.button(i, key=f"bt_{i}"):
                clicada = ch
    _ponte()
    return clicada


def _ponte():
    """O script, numa caixinha de altura zero. Separado para a conferência
    da tela (sem navegador) poder trocá-lo."""
    try:
        import streamlit.components.v1 as _comp
        _comp.html(_SCRIPT, height=0)
    except Exception:
        pass   # sem a ponte o clique não abre, mas a tela não cai


if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    ok("ident: estável, curto e só com letras e números",
       ident("pa", "CANECA TÉRMICA") == ident("pa", "CANECA TÉRMICA")
       and ident("hg", "fin:MERCADORIA").isalnum() and len(ident("hg", "x")) == 12)
    ok("ident: grupos diferentes não se confundem", ident("pa", "x") != ident("hg", "x"))
    ok("alvo: o atributo que o script procura", alvo("hg", "saldo").startswith('data-clique="hg'))
    ok("o script aperta o botão do mesmo id, e não navega",
       "st-key-clk_" in _SCRIPT and "preventDefault" in _SCRIPT and "location" not in _SCRIPT)
    # botoes: um botão escondido por chave, e devolve a que foi apertada. O
    # Streamlit é trocado por um duplo que aperta o botão de "B"; a ponte
    # (o navegador) é medida de verdade em `checar_navegador.py`.
    import contextlib
    import sys as _sys_c
    import types as _types_c
    _chaves_vistas = []
    _st_falso = _types_c.ModuleType("streamlit")
    _st_falso.markdown = lambda *a, **k: None
    _st_falso.container = lambda key=None: (_chaves_vistas.append(key), contextlib.nullcontext())[1]
    _st_falso.button = lambda rot, key=None: key == "bt_" + ident("pa", "B")
    _real_st = _sys_c.modules.get("streamlit")
    _real_ponte = globals()["_ponte"]
    _sys_c.modules["streamlit"] = _st_falso
    globals()["_ponte"] = lambda: None
    try:
        _ap = botoes("pa", ["A", "B", "A"])
    finally:
        if _real_st is not None:
            _sys_c.modules["streamlit"] = _real_st
        globals()["_ponte"] = _real_ponte
    ok("botoes: devolve a chave apertada, um botão por chave (repetida não duplica)",
       _ap == "B" and len(_chaves_vistas) == 2)

    # NENHUM LINK PARA O PRÓPRIO STUDIO, em arquivo nenhum. Um `<a href>` com
    # `target="_self"` recarrega a página — o defeito de 27/10, que passou
    # pelo protocolo porque nenhum verificador abria navegador. Por AST, só
    # nos textos que o código MONTA: docstring e comentário que contam a
    # história não são o defeito.
    import ast as _ast_c
    import glob as _glob_c
    _achados = []
    _alvo_c = "target=" + '"_self"'   # em duas partes: a guarda não se acha
    for _arq in sorted(_glob_c.glob("*.py")):
        if _arq.startswith("checar_"):
            continue
        try:
            _arv = _ast_c.parse(open(_arq, encoding="utf-8").read())
        except SyntaxError:
            continue
        _docs = {id(n.value) for n in _ast_c.walk(_arv)
                 if isinstance(n, _ast_c.Expr) and isinstance(n.value, _ast_c.Constant)}
        for n in _ast_c.walk(_arv):
            if (isinstance(n, _ast_c.Constant) and isinstance(n.value, str)
                    and id(n) not in _docs and _alvo_c in n.value):
                _achados.append(f"{_arq}:{n.lineno}")
    ok(f"nenhum link que recarrega o Studio (target=_self): {_achados or 'nenhum'}",
       not _achados)
    print("\nfalhas:", falhas)
    raise SystemExit(1 if falhas else 0)
