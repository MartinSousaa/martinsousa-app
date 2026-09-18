"""Nome usado ANTES de existir — ou que NAO EXISTE — dentro de uma funcao.

E a classe de erro que derrubou o Painel de Metas duas vezes seguidas. O Python
so reclama em tempo de execucao, entao passa por compileall e por qualquer
checagem de nomes desconhecidos: o nome existe, so existe tarde demais.

O escopo de uma funcao em Python e PLANO: um `x = 1` la dentro de um `for`,
de um `if` ou de um `try` liga o nome para a funcao inteira. Por isso as
ligacoes sao colhidas em qualquer profundidade da instrucao — a primeira versao
disto olhava so a forma da instrucao no topo do corpo, e chamava de erro todo
nome ligado um nivel abaixo.

Ficam de fora, porque sao escopo de dentro e nao da funcao: corpo de funcao
aninhada, de lambda e de classe, e a variavel de compreensao — o `a` de
`[a for a in fila]` nao e o `a` da funcao.
"""
import ast, sys, builtins

_COMPRE = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_FUNC = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _alvos(alvo):
    """Os nomes que um alvo de atribuicao liga, inclusive `a, (b, *c)`."""
    pilha = [alvo]
    while pilha:
        t = pilha.pop()
        if isinstance(t, ast.Name):
            yield t.id
        elif isinstance(t, (ast.Tuple, ast.List)):
            pilha.extend(t.elts)
        elif isinstance(t, ast.Starred):
            pilha.append(t.value)


def ligados(no, sombra=frozenset(), topo=True):
    """Nomes que esta instrucao liga na funcao, em qualquer profundidade."""
    if not topo and isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef,
                                    ast.ClassDef)):
        yield no.name          # o `def` liga o proprio nome; o corpo e outro escopo
        return
    if isinstance(no, ast.Lambda):
        return
    if isinstance(no, _COMPRE):
        dentro = set(sombra)
        for g in no.generators:
            dentro.update(_alvos(g.target))
        for filho in ast.iter_child_nodes(no):
            for n in ligados(filho, dentro, topo=False):
                yield n
        return

    if isinstance(no, ast.Assign):
        for t in no.targets:
            for n in _alvos(t):
                yield n
    elif isinstance(no, (ast.AnnAssign, ast.AugAssign)):
        for n in _alvos(no.target):
            yield n
    elif isinstance(no, (ast.For, ast.AsyncFor)):
        for n in _alvos(no.target):
            yield n
    elif isinstance(no, (ast.With, ast.AsyncWith)):
        for it in no.items:
            if it.optional_vars is not None:
                for n in _alvos(it.optional_vars):
                    yield n
    elif isinstance(no, ast.ExceptHandler) and no.name:
        yield no.name
    elif isinstance(no, (ast.Import, ast.ImportFrom)):
        for a in no.names:
            yield (a.asname or a.name).split(".")[0]
    elif isinstance(no, ast.NamedExpr) and isinstance(no.target, ast.Name):
        yield no.target.id
    elif isinstance(no, (ast.Global, ast.Nonlocal)):
        # Nao e local: quem declara global nunca da UnboundLocalError aqui.
        for n in no.names:
            yield n

    if isinstance(no, _FUNC) and topo:
        # A propria def de topo: o nome dela ja e colhido por quem chama.
        return
    for filho in ast.iter_child_nodes(no):
        for n in ligados(filho, sombra, topo=False):
            yield n


def lidos(no, sombra=frozenset()):
    """Nomes lidos na instrucao, sem entrar em escopo de dentro."""
    if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda,
                       ast.ClassDef)):
        return
    if isinstance(no, _COMPRE):
        dentro = set(sombra)
        for g in no.generators:
            dentro.update(_alvos(g.target))
        for filho in ast.iter_child_nodes(no):
            for n in lidos(filho, dentro):
                yield n
        return
    if isinstance(no, ast.Name) and isinstance(no.ctx, ast.Load):
        if no.id not in sombra:
            yield no
        return
    for filho in ast.iter_child_nodes(no):
        for n in lidos(filho, sombra):
            yield n


def _nomes_do_modulo(arv):
    """Tudo que existe no nivel do modulo: def, class, import e atribuicao.

    E o universo do que uma funcao pode ler sem ligar antes. O que nao esta
    aqui, nem nos parametros, nem ligado na propria funcao, NAO EXISTE — e o
    Python so descobre isso na hora em que a linha roda.
    """
    # Os nomes que todo modulo Python tem, sem ninguem escrever.
    fora = {"__file__", "__name__", "__doc__", "__package__", "__spec__",
            "__loader__", "__builtins__", "__debug__"}
    for no in arv.body:
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            fora.add(no.name)
        elif isinstance(no, (ast.Import, ast.ImportFrom)):
            for a in no.names:
                fora.add((a.asname or a.name).split(".")[0])
        elif isinstance(no, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            for alvo in (no.targets if isinstance(no, ast.Assign) else [no.target]):
                fora.update(_alvos(alvo))
        elif isinstance(no, (ast.If, ast.Try, ast.For, ast.While, ast.With)):
            # `try: import x / except: x = None` e o padrao deste repositorio.
            for filho in ast.walk(no):
                if isinstance(filho, (ast.Import, ast.ImportFrom)):
                    for a in filho.names:
                        fora.add((a.asname or a.name).split(".")[0])
                elif isinstance(filho, ast.Assign):
                    for alvo in filho.targets:
                        fora.update(_alvos(alvo))
                elif isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef,
                                        ast.ClassDef)):
                    fora.add(filho.name)
    return fora


def _defs_diretos(fn):
    """Os `def` do corpo desta funcao, sem atravessar outro `def`.

    Um `def` dentro de um `if` ou de um `for` continua sendo desta funcao; um
    `def` dentro de outro `def` ja e de outro escopo e nao e assunto daqui.
    """
    pilha = list(fn.body)
    while pilha:
        no = pilha.pop()
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield no
            continue                 # o corpo dele e escopo dele
        if isinstance(no, ast.ClassDef):
            continue
        pilha.extend(ast.iter_child_nodes(no))


def _funcoes_com_escopo(arv, do_modulo):
    """(funcao, nomes_visiveis_de_fora) para cada `def`, aninhado ou nao.

    Funcao dentro de funcao ve os nomes da de fora — e ve tambem o NOME DELA
    MESMA e o das irmas. Sem essa cadeia, a checagem acusava 479 erros que nao
    existem: todo `_dia`, `_int`, `_pts_para` deste repositorio e uma funcao
    interna, e toda leitura de variavel da funcao de cima virava "nao existe".

    Um verificador que grita onde nao ha erro e pior do que nenhum: ele treina
    quem o roda a ignorar a saida.
    """
    fila = [(fn, do_modulo) for fn in arv.body
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))]
    # Nomes dentro de classes tambem contam para os metodos.
    for no in arv.body:
        if isinstance(no, ast.ClassDef):
            dentro = do_modulo | {c.name for c in no.body
                                  if isinstance(c, (ast.FunctionDef,
                                                    ast.AsyncFunctionDef))}
            fila += [(c, dentro) for c in no.body
                     if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef))]
    while fila:
        fn, visiveis = fila.pop()
        yield fn, visiveis
        _a = fn.args
        meus = {p.arg for p in (_a.posonlyargs + _a.args + _a.kwonlyargs)}
        for extra in (_a.vararg, _a.kwarg):
            if extra is not None:
                meus.add(extra.arg)
        for st in fn.body:
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef,
                               ast.ClassDef)):
                meus.add(st.name)
            meus.update(ligados(st))
        # O que um `def` interno enxerga: o de fora inteiro, mais tudo que a
        # funcao de fora liga — inclusive depois dele, porque o corpo dele só
        # roda quando alguem o chama.
        de_dentro = visiveis | meus
        # SO OS FILHOS DIRETOS. `ast.walk` desce tambem para os netos, e o neto
        # entrava na fila com o escopo do AVO — sem os nomes do pai. Quando a
        # entrada errada era processada primeiro, toda variavel do pai virava
        # "nao existe": foi assim que `_it_pontuacao`, que le `pts` de `_card`,
        # apareceu como erro.
        for filho in _defs_diretos(fn):
            fila.append((filho, de_dentro))


def checar(arq):
    fora = []
    arv = ast.parse(open(arq, encoding="utf-8").read(), arq)
    do_modulo = _nomes_do_modulo(arv)
    vistas = set()
    for fn, visiveis in _funcoes_com_escopo(arv, do_modulo):
        if id(fn) in vistas:
            continue
        vistas.add(id(fn))
        # Parametro ja chega ligado: `texto = texto.strip()` la embaixo nao
        # torna a leitura la em cima um erro.
        _a = fn.args
        param = {p.arg for p in
                 (_a.posonlyargs + _a.args + _a.kwonlyargs)}
        for extra in (_a.vararg, _a.kwarg):
            if extra is not None:
                param.add(extra.arg)
        onde = {}
        for i, st in enumerate(fn.body):
            # O `def` interno liga o proprio nome NA FUNCAO DE FORA. `ligados`
            # nao devolve isso quando o `def` e a propria instrucao do topo, e
            # era por isso que `_dia`, `_int` e `_pts_para` — funcoes internas
            # deste repositorio — apareciam como "nao existe".
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef,
                               ast.ClassDef)):
                onde.setdefault(st.name, (i, st.lineno))
            for nome in ligados(st):
                onde.setdefault(nome, (i, st.lineno))
        for i, st in enumerate(fn.body):
            for n in lidos(st):
                if n.id in param or n.id in dir(builtins):
                    continue
                pos = onde.get(n.id)
                if pos and i < pos[0]:
                    fora.append((n.lineno, n.id, pos[1], fn.name))
                elif not pos and n.id not in visiveis:
                    # NAO EXISTE EM LUGAR NENHUM — nem parametro, nem ligado
                    # aqui, nem no modulo. O `compileall` aceita, porque a
                    # sintaxe esta certa; so quebra quando a linha roda.
                    #
                    # Este caso entrou depois de eu mesmo escrever
                    # `return padrao` dentro de um `_num(v)` que nao tem esse
                    # parametro. Passou pelos tres verificadores e so apareceria
                    # no dia em que uma celula viesse vazia.
                    fora.append((n.lineno, n.id, 0, fn.name))
    return sorted(set(fora))


def _conferencia():
    """`python3 checar_ordem.py` sem argumento roda os casos deste verificador.

    Ele passou a acusar coisa que nao e erro enquanto eu o melhorava — 479
    ocorrencias numa versao, 21 em outra — e verificador que grita onde nao ha
    erro treina quem o roda a ignorar a saida. Os dois lados ficam travados
    aqui: o que ele TEM de pegar, e o que ele NAO PODE acusar.
    """
    import tempfile, os as _os
    CASOS = [
        # (codigo, quantos erros esperados, o que e)
        ("def f():\n    print(x)\n    x = 1\n", 1, "lido antes de existir"),
        ("def f(x):\n    return x\n", 0, "parametro nao e erro"),
        ("T = 1\ndef f():\n    return T\n", 0, "nome do modulo"),
        ("import os\ndef f():\n    return os.sep\n", 0, "import"),
        ("def f():\n    return __file__\n", 0, "dunder do modulo"),
        ("def f():\n    return naoexiste\n", 1, "nao existe em lugar nenhum"),
        ("def f(a):\n    def g():\n        return a + b\n    b = 2\n"
         "    return g()\n", 0, "fechamento le da funcao de fora"),
        ("def f():\n    def p():\n        v = 1\n        def n():\n"
         "            return v\n        return n()\n    return p()\n", 0,
         "neto le do pai, e nao do avo"),
        ("def f():\n    def g():\n        return 1\n    return g()\n", 0,
         "def interno liga o proprio nome"),
        ("def f():\n    return [a for a in (1, 2)]\n", 0,
         "variavel de compreensao e de dentro"),
        ("def f():\n    try:\n        import x\n    except Exception:\n"
         "        x = None\n    return x\n", 0, "import dentro de try"),
        ("def f():\n    return len([1])\n", 0, "builtin"),
    ]
    falhas = 0
    for codigo, esperado, nome in CASOS:
        cam = _os.path.join(tempfile.gettempdir(), "_co_teste.py")
        with open(cam, "w", encoding="utf-8") as fh:
            fh.write(codigo)
        achou = len(checar(cam))
        bom = achou == esperado
        falhas += not bom
        print(("ok    " if bom else f"FALHA ({achou} != {esperado}) ") + nome)
        _os.remove(cam)
    print(f"\nfalhas: {falhas}")
    return falhas


if len(sys.argv) == 1:
    sys.exit(1 if _conferencia() else 0)

total = 0
for arq in sys.argv[1:]:
    for ln, nome, prim, fn in checar(arq):
        if prim:
            print(f"  {arq}:{ln}  '{nome}' usado aqui, so existe a partir da "
                  f"linha {prim}   ({fn})")
        else:
            print(f"  {arq}:{ln}  '{nome}' NAO EXISTE — nem parametro, nem "
                  f"variavel, nem nome do modulo   ({fn})")
        total += 1
print(f"\n{total} ocorrencia(s)")
