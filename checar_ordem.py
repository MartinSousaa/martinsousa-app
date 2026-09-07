"""Nome usado ANTES de existir, dentro de uma funcao.

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


def checar(arq):
    fora = []
    arv = ast.parse(open(arq, encoding="utf-8").read(), arq)
    for fn in ast.walk(arv):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
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
            for nome in ligados(st):
                onde.setdefault(nome, (i, st.lineno))
        for i, st in enumerate(fn.body):
            for n in lidos(st):
                pos = onde.get(n.id)
                if (pos and i < pos[0] and n.id not in param
                        and n.id not in dir(builtins)):
                    fora.append((n.lineno, n.id, pos[1], fn.name))
    return sorted(set(fora))


total = 0
for arq in sys.argv[1:]:
    for ln, nome, prim, fn in checar(arq):
        print(f"  {arq}:{ln}  '{nome}' usado aqui, so existe a partir da "
              f"linha {prim}   ({fn})")
        total += 1
print(f"\n{total} ocorrencia(s)")
