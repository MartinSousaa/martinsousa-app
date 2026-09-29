"""varredura_formas.py — as seis Formas, contra o repositório INTEIRO.

POR QUE ELE EXISTE
------------------
Dono, 28/09: *"se já estava no protocolo, eu mandei o `@` e mesmo assim o erro
passou, de que adianta o protocolo?"*

Ele estava certo, e o furo tem nome: **o protocolo é portão do que entra, não
varredura do que já está lá.** Os seis verificadores olham o diff; um defeito
já mergeado é invisível para eles. O `log_imagem.py:59` gravava produto vazio
desde o PR #173, e o `@` rodou sobre um diff com zero linha de código.

Este arquivo é o outro lado: cada Forma vira uma PERGUNTA EXECUTÁVEL feita ao
repositório inteiro, e ele lista o que já existe.

ELE É RELATÓRIO, NÃO PORTÃO
---------------------------
Sai com 0 sempre. Achado antigo é trabalho a fazer, não commit bloqueado — e
transformá-lo em portão faria a próxima correção urgente esbarrar em dívida de
três semanas atrás. Quem decide a ordem é o dono.

O QUE ELE NÃO FAZ
-----------------
A Forma 4 (otimizar em volta da raiz) não está aqui. Ela é julgamento — "esta
resposta mudou o processo quando faltava capacidade?" — e não existe pergunta
sintática que a responda. Fingir que existe seria pior: daria a impressão de
cobertura onde não há. Ela continua sendo pergunta de leitura humana.
"""

import ast
import os
import re
import sys

IGNORAR = {"varredura_formas.py"}


def _fontes():
    for nome in sorted(os.listdir(".")):
        if nome.endswith(".py") and nome not in IGNORAR:
            try:
                with open(nome, encoding="utf-8") as fh:
                    yield nome, fh.read()
            except OSError:
                continue


def _arvore(fonte):
    try:
        return ast.parse(fonte)
    except SyntaxError:
        return None


# ── FORMA 5 — o mesmo cálculo em dois lugares ────────────────────────────────
def forma5_arquivos_gemeos(minimo=4):
    """PARES de arquivos que compartilham muitos nomes de topo.

    A pergunta certa não é "existe nome repetido?". `_brl`, `_num` e `salvar`
    moram em quinze módulos cada um, e isso é convenção: cada um formata o SEU
    real e salva a SUA aba. Listar os quinze afoga o achado real.

    Um nome compartilhado é coincidência. DOZE nomes compartilhados entre dois
    arquivos quer dizer que um é cópia do outro — e é aí que duas respostas
    para a mesma pergunta passam a divergir. `placar.py` e `placar_core.py` já
    deram 330 pontos de diferença no mesmo mês e na mesma sessão.
    """
    # O ESQUELETO CRUD DESTE REPOSITORIO. Todo modulo que fala com uma aba
    # tem estes nomes, e ter os mesmos cinco nao significa nada: cada um
    # formata o SEU real e salva a SUA aba. Contando-os, quarenta pares
    # apareciam com 4-7 "nomes em comum" e afogavam os dois que importam.
    ESQUELETO = {"_aba", "_num", "_brl", "_crono", "_cliente", "_normalizar",
                 "_aj", "_abrir", "_chave", "carregar", "salvar", "pagina",
                 "remover", "atualizar", "apagar", "gravar", "main", "ok"}
    topo = {}
    for nome, fonte in _fontes():
        arv = _arvore(fonte)
        if arv is None:
            continue
        topo[nome] = {n.name for n in arv.body
                      if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    fora = []
    arquivos = sorted(topo)
    for i_ in range(len(arquivos)):
        for j_ in range(i_ + 1, len(arquivos)):
            a_, b_ = arquivos[i_], arquivos[j_]
            comuns = (topo[a_] & topo[b_]) - ESQUELETO
            if len(comuns) >= minimo:
                fora.append(f"{a_} ↔ {b_}: {len(comuns)} nomes em comum "
                            f"({', '.join(sorted(comuns)[:6])}"
                            f"{'…' if len(comuns) > 6 else ''})")
    return sorted(fora, key=lambda x: -int(x.split(": ")[1].split()[0]))


# ── FORMA 6 — restrição de ambiente aplicada a UM leitor ─────────────────────
def forma6_datetime_sem_fuso():
    """`datetime.now()` sem fuso, em arquivo que também usa FUSO.

    O container do Railway roda em UTC. Comparar `datetime.now()` com horário
    local dá diferença de três horas — e o arquivo que já importa FUSO mostra
    que alguém ali sabia disso, e alguma linha ficou para trás.
    """
    # TODO ARQUIVO, e nao so os que ja usam FUSO.
    #
    # A primeira versao exigia `FUSO` no arquivo — ou seja, so achava onde
    # alguem JA SABIA do problema. `atividades.py` e `triagem.py` gravam
    # `data_hora` com `datetime.now()` e nunca ouviram falar de fuso: o
    # Historico mostrava a hora tres horas adiantada, e a varredura passava
    # reto. E a Forma 1 dentro da propria varredura — escopar no lugar onde
    # o sintoma ja tinha sido notado.
    # A MESMA LISTA DE ISENTOS DO PORTAO, lida de la.
    #
    # `checar_alcance.CONSISTENTES_UTC` diz onde o `datetime.now()` cru esta
    # CERTO — auth e rhid_api comparam expiracao contra token gravado, os dois
    # em UTC. Repetir a lista aqui seria a Forma 5: duas listas discordando, e
    # a varredura mostrando como "achado" o que o portao ja aprovou.
    # CONSISTENTES_UTC: a lista de isentos, lida do portao. Ela tem guarda
    # propria la (`_conferir_isentos`), que reprova isento sem motivo escrito,
    # isento de arquivo que nao existe mais, e a isencao larga de
    # `placar_core.py` — a que escondeu `ritmo_do_mes`.
    try:
        from checar_alcance import CONSISTENTES_UTC as _ISENTOS
    except Exception:
        _ISENTOS = {}
    fora = []
    for nome, fonte in _fontes():
        if nome in _ISENTOS:
            continue
        # E fora do bloco de conferencia: a guarda que procura
        # `datetime.now()` contem o texto `datetime.now()`.
        fonte = fonte.split('if __name__ == "__main__":')[0]
        for i, linha in enumerate(fonte.splitlines(), 1):
            # Fora o comentário `#` e o texto entre crases: `datetime.now()`
            # dentro de uma docstring explicando o problema NÃO é o problema.
            corpo = re.sub(r"`[^`]*`", "", linha.split("#", 1)[0])
            if re.search(r"datetime\.now\(\s*\)", corpo) and "FUSO" not in corpo:
                fora.append(f"{nome}:{i}  {linha.strip()[:70]}")
    return fora


def forma6_sessao_em_thread():
    """`st.session_state` dentro de função que é alvo de `threading.Thread`.

    Foi este o defeito de 28/09: a thread não lê o session_state, e o campo
    é gravado VAZIO — sem erro nenhum.
    """
    fora = []
    for nome, fonte in _fontes():
        arv = _arvore(fonte)
        if arv is None or "Thread(" not in fonte:
            continue
        # Os nomes passados como `target=` — são eles que rodam na thread.
        alvos = set()
        for no in ast.walk(arv):
            if not isinstance(no, ast.Call):
                continue
            if (getattr(no.func, "attr", "") or getattr(no.func, "id", "")) != "Thread":
                continue
            for kw in no.keywords:
                if kw.arg == "target":
                    alvos.add(getattr(kw.value, "id", "")
                              or getattr(kw.value, "attr", ""))
        for no in ast.walk(arv):
            if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if no.name not in alvos:
                continue
            # SÓ O CORPO. `session_state` num VALOR PADRÃO de parâmetro é
            # avaliado na hora em que a função é DEFINIDA — na thread
            # principal, onde a leitura funciona. É o idioma correto para
            # levar estado para dentro da thread, e acusá-lo seria alarme
            # falso em cima de código certo (`imagem.py:7687` faz assim).
            corpo = ast.Module(body=list(no.body), type_ignores=[])
            try:
                trecho = ast.unparse(corpo)
            except Exception:
                trecho = ast.get_source_segment(fonte, no) or ""
            if "session_state" in trecho:
                fora.append(f"{nome}:{no.lineno}  {no.name} (alvo de Thread)")
    return fora


# ── FORMA 2 — a guarda que se encontra a si mesma ────────────────────────────
def forma2_guarda_que_se_encontra():
    """Guarda cuja asserção POSITIVA só bate no próprio texto do teste.

    A PERGUNTA MUDOU, E POR MEDICAO. A primeira versao listava todo
    `open(__file__)` — quatorze ocorrencias — como se o padrao fosse o
    defeito. Nao e: ler o arquivo e legitimo quando o literal procurado vive
    no codigo de producao. Mutei as quatorze e TODAS reprovaram o defeito.
    Listar codigo certo e alarme falso, e alarme falso ensina a ignorar.

    O defeito de verdade e mais estreito: uma assercao `"x" in fonte` onde
    `"x"` NAO existe na producao e so aparece no proprio bloco de
    conferencia. Ai ela passa verde para sempre, medindo a si mesma.

    `not in` fica de fora: afirmar que um texto NAO existe e justamente o
    caso em que ele so pode estar no teste.
    """
    fora = []
    for nome, fonte in _fontes():
        corpo, _, teste = fonte.partition('if __name__ == "__main__":')
        if not teste:
            continue
        for m in re.finditer(
                r'"([^"\n]{8,80})"\s+in\s+(_?[a-z_]*(?:fonte|src|corpo|arquivo)'
                r'[a-z_]*)', teste):
            lit, var = m.group(1), m.group(2)
            # So quando a variavel e o ARQUIVO inteiro: `inspect.getsource` de
            # um bloco nao alcanca o teste, entao nao ha como se encontrar.
            if f"{var} = open(__file__" not in teste and f"{var}=open(__file__" not in teste:
                continue
            if corpo.count(lit) == 0:
                linha = teste[:m.start()].count("\n") + corpo.count("\n") + 1
                fora.append(f"{nome}:{linha}  \"{lit[:50]}\" só existe no "
                            f"teste — a guarda mede a si mesma")
    return fora


# ── FORMA 3 — código sem verificador que o leia ──────────────────────────────
def forma3_tela_sem_guarda():
    """Função `pagina_*` que nenhum verificador desenha.

    `checar_tela.py` existe porque os outros não desenham nada. Uma tela fora
    dele sobe sem rede — e foi assim que a Home caiu em produção.
    """
    try:
        with open("checar_tela.py", encoding="utf-8") as fh:
            varredura = fh.read()
    except OSError:
        return ["checar_tela.py não existe"]
    fora = []
    for nome, fonte in _fontes():
        arv = _arvore(fonte)
        if arv is None:
            continue
        for no in arv.body:
            if not isinstance(no, ast.FunctionDef):
                continue
            if not no.name.startswith("pagina"):
                continue
            if no.name not in varredura:
                fora.append(f"{nome}:{no.lineno}  {no.name}")
    return fora


# ── FORMA 1 — capacidade que existe num irmão e falta no outro ───────────────
def forma1_retorno_engolido():
    """`except Exception: pass` em função que GRAVA algo.

    Não é erro por si — registro não pode derrubar geração. É o lugar onde a
    falha fica silenciosa, e silêncio foi o que escondeu o produto vazio por
    dias. Cada um destes precisa de guarda de CONTEÚDO, não de execução.
    """
    fora = []
    for nome, fonte in _fontes():
        arv = _arvore(fonte)
        if arv is None:
            continue
        for no in ast.walk(arv):
            if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            trecho = ast.get_source_segment(fonte, no) or ""
            if not re.search(r"append_row|update_cell|\.upload|insert_row", trecho):
                continue
            if not re.search(r"except Exception:\s*\n\s*(#[^\n]*\n\s*)*pass",
                             trecho):
                continue
            # SILENCIOSA NAO E O DEFEITO — e SILENCIOSA E SEM GUARDA.
            #
            # `registrar` engole a excecao de proposito: registro nao pode
            # derrubar geracao. O que falta, quando falta, e alguem CONFERIR
            # O QUE FOI ESCRITO. Tres das cinco que esta varredura listava ja
            # tinham essa guarda no proprio auto-teste, e lista-las era
            # alarme falso.
            #
            # Conta como coberta: a funcao AVISA a tela ou devolve
            # True/False, ou o auto-teste do modulo grava com uma aba falsa e
            # olha a linha.
            avisa = ("st.warning" in trecho or "st.error" in trecho
                     or "return True" in trecho or "return False" in trecho)
            _, _, teste = fonte.partition('if __name__ == "__main__":')
            tem_guarda = bool(teste) and any(
                x in teste for x in ("append_row", "_AbaFalsa", "linhas_falsas",
                                     "_AbaFalsaLog"))
            if not (avisa or tem_guarda):
                fora.append(f"{nome}:{no.lineno}  {no.name} — nem avisa, nem "
                            f"devolve resultado, nem tem guarda de conteudo")
    return fora


def _autoteste():
    """A varredura se confere, e por casos plantados — nao por inspecao.

    `forma2_guarda_que_se_encontra` nasceu de uma pergunta REESCRITA: a
    primeira listava todo `open(__file__)` e a medicao mostrou que o padrao
    nao e o defeito. Uma pergunta reescrita precisa provar que continua
    enxergando o que importa, senao ela so ficou silenciosa.

    O passo 3 do protocolo pergunta "qual verificador leu a linha que eu
    mudei?". Para esta linha, a resposta era "nenhum": eu tinha plantado um
    defeito a mao e apagado depois. Isso nao e repetivel — e o que nao e
    repetivel nao e guarda.
    """
    import tempfile
    falhas = 0

    def ok(nome, cond):
        nonlocal falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    _COM = ('def f():\n    return 1\n\n'
            'if __name__ == "__main__":\n'
            '    _fonte = open(__file__, encoding="utf-8").read()\n'
            '    ok("x", "FRASE QUE NAO EXISTE NA PRODUCAO" in _fonte)\n')
    _SEM = ('def f():\n    return "FRASE QUE EXISTE NA PRODUCAO"\n\n'
            'if __name__ == "__main__":\n'
            '    _fonte = open(__file__, encoding="utf-8").read()\n'
            '    ok("x", "FRASE QUE EXISTE NA PRODUCAO" in _fonte)\n')
    # `not in` e legitimo: afirmar ausencia so pode ter o literal no teste.
    _NEG = ('def f():\n    return 1\n\n'
            'if __name__ == "__main__":\n'
            '    _fonte = open(__file__, encoding="utf-8").read()\n'
            '    ok("x", "ORDEM QUE NAO PODE VOLTAR" not in _fonte)\n')

    import os as _os
    with tempfile.TemporaryDirectory() as _d:
        _antes = _os.getcwd()
        try:
            _os.chdir(_d)
            for _nome, _txt, _espera in (("com.py", _COM, True),
                                         ("sem.py", _SEM, False),
                                         ("neg.py", _NEG, False)):
                open(_nome, "w", encoding="utf-8").write(_txt)
            _achados = forma2_guarda_que_se_encontra()
        finally:
            _os.chdir(_antes)

    _texto = " ".join(_achados)
    ok("acha a guarda que so bate em si mesma", "com.py" in _texto)
    ok("e nao acusa a que bate na producao", "sem.py" not in _texto)
    ok("nem a assercao NEGATIVA, que e legitima", "neg.py" not in _texto)
    print("\nfalhas:", falhas)
    return falhas



# ══════════════════════════════════════════════════════════════════════════
# AS CINCO VARREDURAS DE 29/09 — pedido do dono
# ══════════════════════════════════════════════════════════════════════════
#
# "Você precisa aplicar o refino em toda codificação do sistema 5 vezes
#  seguidas, nas 5 você encontrará erros."
#
# Ele estava certo sobre o padrão: em três rodadas do protocolo, os seis
# verificadores acharam zero e o passo 5 — feito à mão — achou quatro. Então
# as cinco varreduras viram CÓDIGO. À mão eu não faço igual duas vezes; um
# script faz.
#
# Cada uma imprime CANDIDATOS, não culpados: a triagem é leitura, e está
# escrita no commit de 29/09. Verificador que dá alarme falso ensina a ser
# ignorado, e por isso cada filtro abaixo foi apertado até os falsos sumirem.


def _sem_autoteste(src):
    return src.partition('if __name__ == "__main__":')[0]


def varredura_chamadas_irmas(raiz="."):
    """A mesma função chamada em N lugares, e UM não passa o que os outros passam.

    É a forma exata dos defeitos de 28/09: `fotos_ref` faltando numa chamada,
    `plano_triagem` noutra, `prompt_base` desatualizado numa terceira.

    Só funções DESTE repositório: `sorted(...)` sem `key` deu 995 achados e
    zero sinal.
    """
    import collections
    defs, chamadas = set(), collections.defaultdict(list)
    arqs = [a for a in sorted(os.listdir(raiz))
            if a.endswith(".py") and not a.startswith(("checar_", "varredura"))]
    for arq in arqs:
        try:
            arv = ast.parse(open(os.path.join(raiz, arq), encoding="utf-8").read())
        except SyntaxError:
            continue
        for n in ast.walk(arv):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs.add(n.name)
    for arq in arqs:
        try:
            arv = ast.parse(_sem_autoteste(open(os.path.join(raiz, arq), encoding="utf-8").read()))
        except SyntaxError:
            continue
        for n in ast.walk(arv):
            if isinstance(n, ast.Call):
                nome = getattr(n.func, "attr", "") or getattr(n.func, "id", "")
                if nome in defs and not nome.startswith("_"):
                    chamadas[nome].append(
                        (arq, n.lineno,
                         frozenset(k.arg for k in n.keywords if k.arg)))
    fora = []
    for nome, sites in sorted(chamadas.items()):
        if len(sites) < 3:
            continue
        todas = set().union(*(s[2] for s in sites))
        for arq, ln, kws in sites:
            faltam = todas - kws
            passam = sum(1 for s in sites if faltam <= s[2])
            if faltam and passam >= len(sites) - 1 and passam >= 2:
                fora.append(f"{arq}:{ln} {nome}() sem {sorted(faltam)} "
                            f"— {passam}/{len(sites)} passam")
    return fora


def varredura_gravacao_muda(raiz="."):
    """`except: pass` em cima de uma GRAVAÇÃO, sem uma linha dizendo por quê.

    Gravação que falha calada é o defeito mais caro desta base: o log gravou
    produto vazio por semanas e ninguém soube.

    O comentário pode estar acima do `except`, na linha do `pass` ou logo
    abaixo — a primeira versão olhava só acima e acusou dois inocentes.
    """
    GRAVA = ("append_row", "update", "upload", "salvar", "gravar", "registrar",
             "write", "insert", "batch_update", "add_worksheet")
    fora = []
    for arq in sorted(os.listdir(raiz)):
        if not arq.endswith(".py") or arq.startswith(("checar_", "varredura")):
            continue
        src = open(os.path.join(raiz, arq), encoding="utf-8").read()
        linhas = src.split("\n")
        try:
            arv = ast.parse(_sem_autoteste(src))
        except SyntaxError:
            continue
        for n in ast.walk(arv):
            if not isinstance(n, ast.Try):
                continue
            for h in n.handlers:
                if not all(isinstance(c, ast.Pass) for c in h.body):
                    continue
                grava = sorted({(getattr(c.func, "attr", "")
                                 or getattr(c.func, "id", ""))
                                for c in ast.walk(ast.Module(body=n.body,
                                                             type_ignores=[]))
                                if isinstance(c, ast.Call)} & set(GRAVA))
                if not grava:
                    continue
                i = h.lineno - 1
                perto = "\n".join(linhas[max(0, i - 6):i + 4])
                if "#" not in perto:
                    fora.append(f"{arq}:{h.lineno} engole falha de {grava} "
                                "sem uma linha dizendo por quê")
    return fora


def varredura_constante_homonima(raiz="."):
    """Mesmo NOME de constante em arquivos diferentes, com valores diferentes.

    Alias (`X = _outro.X`) é o padrão CERTO e não entra: ele tem uma fonte
    só. O que entra é a cópia literal — duas respostas para a mesma pergunta,
    e elas passam a discordar; a questão é só quando.
    """
    import collections
    defs = collections.defaultdict(dict)
    for arq in sorted(os.listdir(raiz)):
        if not arq.endswith(".py") or arq.startswith(("checar_", "varredura")):
            continue
        try:
            arv = ast.parse(_sem_autoteste(open(os.path.join(raiz, arq), encoding="utf-8").read()))
        except SyntaxError:
            continue
        for n in arv.body:
            if (isinstance(n, ast.Assign) and len(n.targets) == 1
                    and isinstance(n.targets[0], ast.Name)
                    and n.targets[0].id.isupper()
                    and len(n.targets[0].id) > 3):
                defs[n.targets[0].id][arq] = ast.unparse(n.value)
    fora = []
    for nome, porarq in sorted(defs.items()):
        # `ABA_NOME`, `COLUNAS` e afins são de cada módulo por desenho.
        if len(porarq) < 2 or nome in ("ABA_NOME", "COLUNAS", "ABA_PARAMS"):
            continue
        literais = {a: v for a, v in porarq.items() if not v.startswith("_")}
        if len(literais) >= 2 and len(set(literais.values())) > 1:
            fora.append(f"{nome} escrita literalmente em "
                        f"{', '.join(sorted(literais))} com valores diferentes")
    return fora


def varredura_sem_rede(raiz="."):
    """Função pública que nenhuma guarda cita — sobe sem rede.

    Responde mecanicamente o passo 3 do protocolo ("qual verificador leu a
    linha que eu mudei?") para o repositório inteiro. Foi ela que achou as
    cinco contas de dinheiro do `app.py` sem guarda nenhuma.
    """
    import collections
    guardas = ""
    for a in sorted(os.listdir(raiz)):
        if a.endswith(".py") and a.startswith(("checar_", "varredura")):
            guardas += open(os.path.join(raiz, a), encoding="utf-8").read()
    sem = collections.defaultdict(list)
    for arq in sorted(os.listdir(raiz)):
        if not arq.endswith(".py") or arq.startswith(("checar_", "varredura")):
            continue
        src = open(os.path.join(raiz, arq), encoding="utf-8").read()
        cabeca, _, teste = src.partition('if __name__ == "__main__":')
        try:
            arv = ast.parse(cabeca)
        except SyntaxError:
            continue
        for n in arv.body:
            if (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and not n.name.startswith("_")
                    and n.name not in teste and n.name not in guardas):
                sem[arq].append(n.name)
    return [f"{a}: {len(f)} função(ões) sem guarda — {', '.join(f[:4])}"
            f"{'…' if len(f) > 4 else ''}"
            for a, f in sorted(sem.items(), key=lambda x: -len(x[1]))[:10]]


def varredura_duplo_pobre(raiz="."):
    """Duplo de teste sem uma chave que a função lê SEM default.

    A leitura com `.get()` não entra: chave ausente ali é o comportamento que
    o teste quer exercitar. Só a leitura por colchete, que estoura.

    LIMITE DESTA VARREDURA, dito em voz alta: ela pega pobreza de CHAVE. O
    caso de 29/09 — a direção de arte de mentira sem porcentagem nenhuma —
    era pobreza de VALOR, e nenhuma pergunta sintática responde essa. Para
    essa, o que serve é o prompt real que o dono baixa e manda.
    """
    import collections
    fora = []
    for arq in sorted(os.listdir(raiz)):
        if not arq.endswith(".py"):
            continue
        src = open(os.path.join(raiz, arq), encoding="utf-8").read()
        if 'if __name__ == "__main__":' not in src:
            continue
        cabeca, _, teste = src.partition('if __name__ == "__main__":')
        try:
            arv_c = ast.parse(cabeca)
            arv_t = ast.parse("if 1:\n" + teste)
        except SyntaxError:
            continue
        sub = collections.defaultdict(lambda: collections.defaultdict(set))
        funcs = {}
        for n in ast.walk(arv_c):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            funcs[n.name] = [a.arg for a in n.args.args]
            protegidas = {c.args[0].value
                          for c in ast.walk(n)
                          if isinstance(c, ast.Call)
                          and getattr(c.func, "attr", "") == "get"
                          and c.args and isinstance(c.args[0], ast.Constant)
                          and isinstance(c.args[0].value, str)}
            for c in ast.walk(n):
                if (isinstance(c, ast.Subscript)
                        and isinstance(c.value, ast.Name)
                        and c.value.id in set(funcs[n.name])
                        and isinstance(c.slice, ast.Constant)
                        and isinstance(c.slice.value, str)
                        and c.slice.value not in protegidas):
                    sub[n.name][c.value.id].add(c.slice.value)

        def _ver(nome, param, d, ln):
            dadas = {k.value for k in d.keys
                     if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            faltam = sub[nome].get(param, set()) - dadas
            if faltam and dadas:
                fora.append(f"{arq}:{ln} {nome}({param}=...) sem "
                            f"{sorted(faltam)} — a função lê sem default")

        for c in ast.walk(arv_t):
            if not isinstance(c, ast.Call):
                continue
            nome = getattr(c.func, "attr", "") or getattr(c.func, "id", "")
            if nome not in funcs:
                continue
            for i, a in enumerate(c.args):
                if isinstance(a, ast.Dict) and i < len(funcs[nome]):
                    _ver(nome, funcs[nome][i], a, c.lineno)
            for kw in c.keywords:
                if isinstance(kw.value, ast.Dict) and kw.arg:
                    _ver(nome, kw.arg, kw.value, c.lineno)
    return fora


def _autoteste_das_cinco():
    """As cinco varreduras novas veem o defeito? Por casos PLANTADOS.

    POR QUE ISTO EXISTE
    -------------------
    Protocolo de 29/09, passo 5: as cinco varreduras novas nao tinham guarda
    nenhuma. Se uma delas quebrasse e devolvesse lista vazia, ela imprimiria
    "(nada)" — que e exatamente o que ela imprime quando o repositorio esta
    limpo. Verificador mudo e indistinguivel de verificador satisfeito, e a
    diferenca entre os dois e todo o valor dele.

    E a minha primeira conferencia disto foi FALSA: perguntei se o nome da
    funcao aparecia entre `_autoteste` e `main`, e aparecia — porque elas
    foram escritas nesse intervalo. Aparecer no arquivo nao e ser exercitada.
    A pergunta certa e por AST: `_autoteste` CHAMA a funcao?

    Cada caso abaixo planta o defeito num diretorio temporario, e nao no
    repositorio: varredura que suja o repositorio para se testar e pior que
    varredura nenhuma.
    """
    import shutil
    import tempfile

    falhas = []

    def ok(nome, cond):
        if not cond:
            falhas.append(nome)
        print(("ok    " if cond else "FALHA ") + nome)

    base = tempfile.mkdtemp()
    try:
        # A — a terceira chamada esquece o `fotos_ref` que as outras passam.
        with open(os.path.join(base, "alvo.py"), "w", encoding="utf-8") as fh:
            fh.write(
                "def conferir(img, fotos_ref=None, tipo=''):\n    return 1\n\n"
                "def a():\n    return conferir(1, fotos_ref=[2], tipo='x')\n\n"
                "def b():\n    return conferir(1, fotos_ref=[3], tipo='y')\n\n"
                "def c():\n    return conferir(1, tipo='z')\n")
        ok("A vê a chamada irmã que esqueceu um argumento",
           any("conferir" in x for x in varredura_chamadas_irmas(base)))

        # B — gravação engolida, sem uma linha dizendo por quê.
        with open(os.path.join(base, "muda.py"), "w", encoding="utf-8") as fh:
            fh.write("def grava(aba):\n    try:\n        aba.append_row([1])\n"
                     "    except Exception:\n        pass\n")
        ok("B vê a gravação que falha calada",
           any("muda.py" in x for x in varredura_gravacao_muda(base)))

        # B-bis — a MESMA gravação, com o motivo escrito, NÃO pode aparecer.
        # Alarme falso ensina a ignorar o verificador.
        with open(os.path.join(base, "muda.py"), "w", encoding="utf-8") as fh:
            fh.write("def grava(aba):\n    try:\n        aba.append_row([1])\n"
                     "    except Exception:\n"
                     "        pass  # registro nao pode derrubar a tela\n")
        ok("e NÃO acusa a que tem o motivo escrito",
           not any("muda.py" in x for x in varredura_gravacao_muda(base)))

        # C — a mesma constante, escrita literalmente em dois arquivos.
        for nome, val in (("um.py", "10"), ("dois.py", "20")):
            with open(os.path.join(base, nome), "w", encoding="utf-8") as fh:
                fh.write(f"LIMITE_DIAS = {val}\n")
        ok("C vê a constante homônima com valores diferentes",
           any("LIMITE_DIAS" in x for x in varredura_constante_homonima(base)))

        # C-bis — o ALIAS é o padrão certo e não pode ser acusado.
        with open(os.path.join(base, "dois.py"), "w", encoding="utf-8") as fh:
            fh.write("import um as _um\nLIMITE_DIAS = _um.LIMITE_DIAS\n")
        ok("e NÃO acusa o alias, que é o padrão certo",
           not any("LIMITE_DIAS" in x for x in varredura_constante_homonima(base)))

        # D — função pública sem nenhuma guarda que a cite.
        with open(os.path.join(base, "nu.py"), "w", encoding="utf-8") as fh:
            fh.write("def calcular_frete(x):\n    return x * 2\n\n"
                     'if __name__ == "__main__":\n    print(1)\n')
        ok("D vê a função pública que nenhuma guarda cita",
           any("nu.py" in x for x in varredura_sem_rede(base)))

        # E — duplo sem a chave que a função lê SEM default.
        with open(os.path.join(base, "pobre.py"), "w", encoding="utf-8") as fh:
            fh.write("def montar(cfg):\n    return cfg['peso']\n\n"
                     'if __name__ == "__main__":\n'
                     "    montar({'nome': 'x'})\n")
        ok("E vê o duplo sem a chave lida sem default",
           any("pobre.py" in x for x in varredura_duplo_pobre(base)))

        # E-bis — com `.get()`, a ausência é o comportamento testado.
        with open(os.path.join(base, "pobre.py"), "w", encoding="utf-8") as fh:
            fh.write("def montar(cfg):\n"
                     "    if cfg.get('peso'):\n        return cfg['peso']\n"
                     "    return 0\n\n"
                     'if __name__ == "__main__":\n'
                     "    montar({'nome': 'x'})\n")
        ok("e NÃO acusa a leitura protegida por `.get()`",
           not any("pobre.py" in x for x in varredura_duplo_pobre(base)))
    finally:
        shutil.rmtree(base, ignore_errors=True)

    # DEVOLVE A CONTAGEM, como `_autoteste`. Uma pergunta, uma resposta.
    #
    # Esta funcao devolvia BOOLEANO ("passou?") e a irma devolvia CONTAGEM
    # ("quantas falharam?"). Duas convencoes para a mesma pergunta, e quem
    # somou as duas inverteu o sentido: com zero falhas, o `and` dava falso e
    # a varredura reprovava SEMPRE. Ninguem viu porque ninguem rodava o
    # codigo de saida — ate `conferir.py` existir.
    print(f"\nfalhas das cinco varreduras: {len(falhas)}")
    return len(falhas)


def main():
    if "--autoteste" in sys.argv:
        # As DUAS contam falhas, e o codigo de saida e a soma. Nao ha `and`
        # de coisas com sentidos opostos aqui.
        return 1 if (_autoteste() + _autoteste_das_cinco()) else 0
    blocos = [
        ("FORMA 1 — gravação com falha silenciosa (precisa de guarda de CONTEÚDO)",
         forma1_retorno_engolido()),
        ("FORMA 2 — guarda cuja asserção só bate em si mesma",
         forma2_guarda_que_se_encontra()),
        ("FORMA 3 — tela que nenhum verificador desenha",
         forma3_tela_sem_guarda()),
        ("FORMA 5 — arquivos gêmeos (um é cópia do outro)",
         forma5_arquivos_gemeos()),
        ("FORMA 6a — datetime.now() sem fuso (fora os isentos do portão)",
         forma6_datetime_sem_fuso()),
        ("FORMA 6b — session_state dentro de alvo de Thread",
         forma6_sessao_em_thread()),
        ("VARREDURA A — chamadas irmãs que divergem (Forma 1)",
         varredura_chamadas_irmas()),
        ("VARREDURA B — gravação que falha calada",
         varredura_gravacao_muda()),
        ("VARREDURA C — constante homônima com valores diferentes (Forma 5)",
         varredura_constante_homonima()),
        ("VARREDURA D — função pública que nenhuma guarda cita",
         varredura_sem_rede()),
        ("VARREDURA E — duplo de teste sem chave lida sem default (Forma 7)",
         varredura_duplo_pobre()),
    ]
    total = 0
    for titulo, achados in blocos:
        print(f"\n{titulo}")
        if not achados:
            print("  (nada)")
            continue
        total += len(achados)
        for a in achados:
            print(f"  {a}")
    print(f"\n{'=' * 70}")
    print(f"{total} achado(s) no repositório inteiro.")
    print("Isto é RELATÓRIO, não portão: achado antigo é trabalho a fazer,")
    print("e quem decide a ordem é o dono. A Forma 4 (otimizar em volta da")
    print("raiz) não está aqui — ela é julgamento, e não existe pergunta")
    print("sintática que a responda.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
