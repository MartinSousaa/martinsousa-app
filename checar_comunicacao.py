"""checar_comunicacao.py — o oitavo verificador: o sistema conta o que sabe?

POR QUE ESTE ARQUIVO EXISTE
---------------------------
Dono, 29/09, depois de um dia inteiro de defeitos: *"precisaria pegar a
codificação, linguagem de comunicação do sistema com o Gemini, prompt, esses
códigos mencionados VS o que as ferramentas utilizam para criação das imagens.
Fazer um fluxograma de criação e resposta para pegar essas inconsistências de
comunicação"*.

Ele estava certo, e o recorte dele é melhor que o meu. Os sete verificadores
perguntam todos **"isto está certo?"**. Nenhum perguntava **"o que este
caminho não consegue fazer, e ele avisa quando não consegue?"**.

Os sete defeitos daquele dia são UM PADRÃO SÓ — limite silencioso:

  teto de 5 páginas por fatia .......... comia pontos sem avisar
  `diag["truncado"]` ................... escrito, e nenhuma tela lia
  fila mostrando 4 de 17 ............... parecia que o cartão não entrou
  2 tentativas fixas de ajuste ......... e sem opção de insistir
  Gemini sem `input_fidelity` .......... peça saía errada sem dizer o motivo
  variável vencendo o descoberto ....... falhava igual, para sempre
  chat com anexo sem ação .............. respondia sobre a peça errada

Não são sete bugs diferentes: é a mesma falha de projeto sete vezes. O
sistema SABE e não CONTA.

O QUE ELE PERGUNTA
------------------
1. Todo dado gravado num dicionário de diagnóstico tem leitor fora dos
   verificadores? Dado que ninguém lê é dado que não existe para quem
   trabalha.

2. Toda chave gravada em `diagnostico` chega à TELA que mostra diagnóstico?
   Ter leitor em código não basta: o defeito de origem é a pessoa na frente
   do Studio não saber.

O QUE ELE NÃO PERGUNTA, E ESTÁ DITO AQUI
----------------------------------------
Ele não julga se o dado é ÚTIL. Um campo pode ser mudo com razão — e por
isso existe `MUDAS_POR_ESCOLHA`, com motivo escrito por chave. Lista muda
seria a Forma 5: alguém acrescenta a terceira e ninguém soma.

A PRIMEIRA VERSÃO DESTE ARQUIVO DEU ALARME FALSO. Ela procurava
`.get("motor")` com aspas DUPLAS, e a tela usa simples: o verificador
anunciou que o motor não chegava à tela quando ele está no expander que o
dono tem no print. Por isso a leitura é por AST, nunca por texto —
verificador que dá alarme falso ensina a ignorá-lo.
"""
import ast
import os
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))

# Os nomes que o código usa para dicionário de diagnóstico/relato.
DICTS_DIAG = ("diagnostico", "diag", "_diag", "relato", "_relato")

# A função que DESENHA o diagnóstico na tela do colaborador.
TELA_DO_DIAGNOSTICO = ("imagem.py", "pagina_imagem")

MUDAS_POR_ESCOLHA = {
    "prompt": "é o prompt inteiro; a tela mostra `prompt_final`, que é o que "
              "de fato foi enviado — mostrar os dois lado a lado confunde",
    "registros_brutos": "diagnóstico de ponto do RHiD, lido pelo log do "
                        "servidor e não pela tela de quem bate ponto",
}


def _eh_verificador(arq):
    return arq.startswith("checar_") or arq in ("conferir.py",
                                                "varredura_formas.py")


def _arvore(arq):
    try:
        return ast.parse(open(os.path.join(RAIZ, arq), encoding="utf-8").read())
    except Exception:
        return None


def gravadas_e_lidas(raiz=None):
    """({chave: [onde grava]}, {chave: [onde lê]}) fora dos verificadores."""
    base = raiz or RAIZ
    grava, le = {}, {}
    for arq in sorted(os.listdir(base)):
        if not arq.endswith(".py") or _eh_verificador(arq):
            continue
        try:
            arv = ast.parse(open(os.path.join(base, arq),
                                 encoding="utf-8").read())
        except Exception:
            continue
        for n in ast.walk(arv):
            if isinstance(n, ast.Assign):
                for alvo in n.targets:
                    if (isinstance(alvo, ast.Subscript)
                            and isinstance(alvo.slice, ast.Constant)
                            and isinstance(alvo.slice.value, str)
                            and isinstance(alvo.value, ast.Name)
                            and alvo.value.id in DICTS_DIAG):
                        grava.setdefault(alvo.slice.value, []).append(
                            f"{arq}:{n.lineno}")
            # LEITURA em qualquer forma — e por AST, nunca por texto: a
            # primeira versão procurou aspas duplas e a tela usa simples.
            if (isinstance(n, ast.Call)
                    and getattr(n.func, "attr", "") in ("get", "pop",
                                                        "setdefault")
                    and n.args and isinstance(n.args[0], ast.Constant)
                    and isinstance(n.args[0].value, str)):
                le.setdefault(n.args[0].value, []).append(f"{arq}:{n.lineno}")
            if (isinstance(n, ast.Subscript)
                    and isinstance(n.slice, ast.Constant)
                    and isinstance(n.slice.value, str)
                    and isinstance(n.ctx, ast.Load)):
                le.setdefault(n.slice.value, []).append(f"{arq}:{n.lineno}")
    return grava, le


def chaves_na_tela(raiz=None):
    """As chaves de diagnóstico que a tela do colaborador de fato mostra."""
    base = raiz or RAIZ
    arq, funcao = TELA_DO_DIAGNOSTICO
    try:
        arv = ast.parse(open(os.path.join(base, arq), encoding="utf-8").read())
    except Exception:
        return set()
    alvo = next((n for n in ast.walk(arv)
                 if isinstance(n, ast.FunctionDef) and n.name == funcao), None)
    if alvo is None:
        return set()
    fora = set()
    for n in ast.walk(alvo):
        if (isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "get"
                and n.args and isinstance(n.args[0], ast.Constant)
                and isinstance(n.args[0].value, str)):
            fora.add(n.args[0].value)
        if (isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant)
                and isinstance(n.slice.value, str)):
            fora.add(n.slice.value)
    return fora


def mudas(raiz=None):
    """[(chave, [onde grava])] — gravadas e que não chegam a ninguém."""
    grava, le = gravadas_e_lidas(raiz)
    na_tela = chaves_na_tela(raiz)
    fora = []
    for chave, onde in sorted(grava.items()):
        if chave in MUDAS_POR_ESCOLHA:
            continue
        leitores = [x for x in le.get(chave, []) if x not in onde]
        if not leitores and chave not in na_tela:
            fora.append((chave, onde))
    return fora


def isencoes_orfas(raiz=None):
    """Isenção escrita para chave que não é mais gravada — lixo que engana.

    Isenção órfã diz "este campo é mudo de propósito" sobre um campo que já
    não existe, e a próxima pessoa a ler acredita.
    """
    grava, _ = gravadas_e_lidas(raiz)
    return sorted(k for k in MUDAS_POR_ESCOLHA if k not in grava)


# ── REGRA 2: DUAS VOZES COM NÚMERO SOBRE O MESMO ASSUNTO ───────────────────
#
# O prompt do Tigre, peça 7, tinha no mesmo texto:
#
#   "O produto ocupa de 30% a 45% da dimensao util do quadro."
#   "mostre o pêndulo desobstruído, ocupando MAIS DA METADE DO QUADRO"
#
# Duas ordens contrárias sobre a mesma coisa. O gerador obedeceu à última.
#
# REDUNDÂNCIA NÃO É O DEFEITO. Duas vozes dizendo "não deforme o produto" é
# reforço inofensivo. O que faz duas vozes DISCORDAREM é o NÚMERO: só ele
# pode sair diferente. Por isso a pergunta é estreita de propósito — guarda
# larga aqui reprovaria o prompt inteiro e viraria ruído.
import re as _re_voz

ASSUNTOS_DO_PROMPT = {
    "tamanho do produto no quadro":
        r"ocupa de \d+%|ocupa NO MINIMO|occupancy \d|quanto ele ocupa|"
        r"ocupando (?:mais|menos) da",
    "folga da borda":
        r"folga da borda|pelo menos \d+%|edge clearance|cruza ou toca",
    "quantidade de blocos de texto":
        r"exatamente \d+ bloco|maximum \d+ information",
}

# O que faz duas vozes discordarem: número, fração, contagem.
_TRAZ_NUMERO = _re_voz.compile(
    r"\d+\s?%|\bde \d+% a \d+%|metade|dois ter[cç]os|exatamente \d+|"
    r"maximum \d+|\b\d+ bloco|pelo menos \d+%", _re_voz.I)


def blocos_do_prompt(texto):
    """O prompt partido em blocos. Linha em branco separa; cabeçalho começa.

    Por BLOCO e não por linha: uma regra quebrada em duas linhas é UMA voz, e
    contar linhas daria alarme falso na primeira medição que eu fiz.
    """
    fora, atual = [], []
    for linha in (texto or "").split("\n"):
        if not linha.strip():
            if atual:
                fora.append("\n".join(atual))
                atual = []
            continue
        if _re_voz.match(r"^(━━━|[A-ZÀ-Ú][A-ZÀ-Ú \-/(),]{10,}:?$)",
                         linha.strip()):
            if atual:
                fora.append("\n".join(atual))
                atual = []
        atual.append(linha)
    if atual:
        fora.append("\n".join(atual))
    return fora


def vozes_numericas(prompt):
    """{assunto: [a linha de cada voz COM número]} quando há mais de uma.

    O NÚMERO TEM DE ESTAR NA LINHA DO ASSUNTO, e não em qualquer lugar do
    bloco. A primeira versão perguntava pelo bloco inteiro e acusou a REGRA
    DE DENSIDADE de falar da folga da borda porque ela contém "NUNCA metade
    de um lado" (posição) e "nunca deixe um pela metade" (corte) — duas
    frases que não têm nada a ver com folga.

    Isso é o alarme falso que este arquivo existe para não dar. A regra vale
    para o verificador também: guarda larga vira ruído, e ruído ensina a
    ignorar.

    A linha SEGUINTE conta junto: uma regra quebrada em duas linhas é uma voz
    só, e o número costuma cair na segunda ("A FOLGA DA BORDA MANDA:\n
    pelo menos 6% em cada lado").
    """
    fora = {}
    for assunto, padrao in ASSUNTOS_DO_PROMPT.items():
        vozes = []
        for bloco in blocos_do_prompt(prompt):
            linhas = bloco.splitlines()
            for i, linha in enumerate(linhas):
                if not _re_voz.search(padrao, linha, _re_voz.I):
                    continue
                trecho = linha + " " + (linhas[i + 1] if i + 1 < len(linhas)
                                        else "")
                if _TRAZ_NUMERO.search(trecho):
                    vozes.append(linha.strip()[:78])
                    break          # uma voz por bloco, não uma por linha
        if len(vozes) > 1:
            fora[assunto] = vozes
    return fora


# ── REGRA 3: A MESMA REGRA ESCRITA DE DOIS JEITOS ──────────────────────────
#
# Achado ao construir este arquivo, em 29/09: a folga da borda é escrita de
# DUAS formas diferentes no mesmo sistema —
#
#   tipos 2, 3, 5, 6, 7 ....  "pelo menos 6% em cada lado"
#   tipos 1, 4, 8 ..........  "a pelo menos 6% da borda"
#
# Hoje as duas dizem 6% e concordam. São duas redações da mesma regra, em
# lugares diferentes do código: no dia em que a folga mudar, alguém altera
# uma e a outra fica para trás — e metade das peças passa a obedecer a um
# número e metade a outro, sem que nada reprove.
#
# É a Forma 5 desta base esperando acontecer: um nome, duas respostas.
#
# Não dá para exigir uma redação só (os dois contextos são diferentes: no
# tipo 4 a folga convive com "o produto preenche o quadro"). Dá para exigir
# que a MEDIDA seja a mesma em todas as peças — e é isso que se mede aqui.
_MEDIDA_DE_FOLGA = _re_voz.compile(r"(\d{1,2})\s?%\s*(?:em cada lado|da borda|"
                                   r"acima da base|abaixo do topo)", _re_voz.I)


def folgas_divergentes(prompts_por_tipo):
    """{medida: [tipos]} quando as peças não concordam sobre a folga."""
    por_medida = {}
    for tipo, prompt in (prompts_por_tipo or {}).items():
        for m in set(_MEDIDA_DE_FOLGA.findall(prompt or "")):
            por_medida.setdefault(m, []).append(tipo)
    return por_medida if len(por_medida) > 1 else {}


# ── REGRA 4: COMANDO QUE O CHAT MANDA E NINGUÉM EXECUTA ────────────────────
#
# Dono, 29/09: *"localizar inconsistências e comandos sem conexão (...)
# informações e comandos ignorados ou que se perdem"*.
#
# O chat e a aba Imagem conversam por uma fila no `session_state`: o chat
# escreve `chat_algo`, a aba lê e executa. Quando a fila é escrita e ninguém
# lê, o chat RESPONDE QUE VAI FAZER e nada acontece — e o colaborador fica
# esperando uma coisa que nunca foi enfileirada para ninguém.
#
# Foi o caso de `chat_gerar_faltantes`: o chat dizia "🖼️ Vou gerar as 7
# imagens que faltam, abra a aba Imagem para acompanhar", escrevia a chave, e
# NENHUMA linha do sistema a lia. Está na transcrição de 29/09 que o dono
# mandou: a colaboradora pediu, ele prometeu sete peças, e nunca gerou uma.
#
# Mentira que o sistema conta por engano é pior que recusa: a pessoa espera.
_CHAVE_DE_FILA = _re_voz.compile(r'session_state\[?\.?\(?["\'](chat_\w+)["\']')
_LEITURA_DE_FILA = _re_voz.compile(r'\.(?:get|pop)\(\s*["\'](chat_\w+)["\']')
ARQS_DO_CHAT = ("chat_assistente.py", "imagem.py", "ferramentas_chat.py")


def filas_do_chat(raiz=None):
    """({fila: [onde escreve]}, {fila: [onde lê]}) entre o chat e as abas."""
    base = raiz or RAIZ
    escritas, lidas = {}, {}
    for arq in ARQS_DO_CHAT:
        try:
            src = open(os.path.join(base, arq), encoding="utf-8").read()
        except Exception:
            continue
        for m in _CHAVE_DE_FILA.finditer(src):
            linha = src[:m.start()].count("\n") + 1
            trecho = src[max(0, m.start() - 40):m.end() + 30]
            onde = (escritas if _re_voz.search(r"\]\s*=|setdefault|\.pop", trecho)
                    else lidas)
            onde.setdefault(m.group(1), []).append(f"{arq}:{linha}")
        for m in _LEITURA_DE_FILA.finditer(src):
            lidas.setdefault(m.group(1), []).append(
                f"{arq}:{src[:m.start()].count(chr(10)) + 1}")
    return escritas, lidas


def filas_orfas(raiz=None):
    """[(fila, [onde escreve])] — escritas e que ninguém consome."""
    escritas, lidas = filas_do_chat(raiz)
    fora = []
    for fila, onde in sorted(escritas.items()):
        leitores = [x for x in lidas.get(fila, []) if x not in onde]
        if not leitores:
            fora.append((fila, onde))
    return fora


def main():
    falhas = 0
    orfas = isencoes_orfas()
    if orfas:
        falhas += 1
        print(f"FALHA  isenção sem chave correspondente: {', '.join(orfas)}")
        print("       a isenção afirma que o campo é mudo de propósito, e ele "
              "não é mais gravado — quem ler acredita.")

    fora = mudas()
    if fora:
        falhas += 1
        print(f"FALHA  {len(fora)} dado(s) que o sistema grava e NÃO conta a "
              "ninguém:")
        for chave, onde in fora:
            print(f"         «{chave}» gravado em {', '.join(onde[:2])}")
        print("       Mostre na tela de diagnóstico, ou declare em "
              "MUDAS_POR_ESCOLHA com o motivo escrito.")

    # REGRA 2 — no prompt REAL dos nove tipos, e não num texto de exemplo.
    try:
        import checar_tela as _ct
        _ct.instalar()
        import imagem as _img
        _dados = {"medidas": "10x21x5", "peso": "299", "material": "Resina",
                  "cor": "Dourado com Strass"}
        _dir = {"nome": "Dourado", "posicionamento": "premium",
                "atmosfera": "Luxo", "paleta": {"fundo": "Branco (#FFF)"},
                "trava_produto": "Resina dourada"}
        _plano = {"composicao": "Produto centralizado",
                  "cena": "Bancada de mármore", "direcao_de_arte": _dir,
                  "textos": [{"titulo": "DURA?", "descricao": "Resiste"}]}
        _achados = {}
        for _tipo in _img.TIPOS_PADRAO:
            _p = _img.montar_prompt_imagem(_tipo, "", _dados, "Produto",
                                           plano_triagem=_plano,
                                           direcao_arte=_dir)
            for _a, _vs in vozes_numericas(_p).items():
                _achados.setdefault(_a, set()).update(_vs)
        if _achados:
            falhas += 1
            print(f"FALHA  {len(_achados)} assunto(s) com DUAS vozes numéricas "
                  "no mesmo prompt:")
            for _a, _vs in _achados.items():
                print(f"         {_a}:")
                for _v in sorted(_vs):
                    print(f"           · {_v}")
            print("       Um assunto, um dono. Duas vozes com número "
                  "discordam — a questão é só quando.")
    except Exception as _e:
        falhas += 1
        print(f"FALHA  não consegui montar o prompt real para medir: "
              f"{type(_e).__name__}: {str(_e)[:90]}")

    # REGRA 3 — todas as peças concordam sobre QUANTO é a folga?
    try:
        _prompts = {}
        for _tipo in _img.TIPOS_PADRAO:
            _prompts[_tipo] = _img.montar_prompt_imagem(
                _tipo, "", _dados, "Produto", plano_triagem=_plano,
                direcao_arte=_dir)
        _div = folgas_divergentes(_prompts)
        if _div:
            falhas += 1
            print("FALHA  as peças não concordam sobre a folga da borda:")
            for _m, _tps in sorted(_div.items()):
                print(f"         {_m}% em: {', '.join(t[:22] for t in _tps)}")
            print("       Mesma regra com medidas diferentes: metade das peças "
                  "obedece a um número e metade a outro.")
    except Exception:
        pass

    # REGRA 4 — o chat manda e alguém executa?
    _orfas = filas_orfas()
    if _orfas:
        falhas += 1
        print(f"FALHA  {len(_orfas)} comando(s) do chat que ninguém executa:")
        for _f, _onde in _orfas:
            print(f"         «{_f}» escrito em {', '.join(_onde[:2])}")
        print("       O chat responde que vai fazer e nada acontece — a "
              "pessoa fica esperando.")

    if not falhas:
        print("ok    todo diagnóstico chega a alguém, e cada assunto tem um dono")
    return falhas


if __name__ == "__main__":
    if "--autoteste" in sys.argv:
        _f = 0

        def ok(nome, cond):
            global _f
            _f += not cond
            print(("ok    " if cond else "FALHA ") + nome)

        import tempfile

        # A ENTRADA VEM DE ARQUIVOS DE VERDADE, num diretório temporário.
        # Medir só o repositório faria a guarda dizer "verde" sem nunca ter
        # visto o defeito — e guarda que nunca viu o defeito não é guarda.
        with tempfile.TemporaryDirectory() as _t:
            def _escrever(nome, txt):
                open(os.path.join(_t, nome), "w", encoding="utf-8").write(txt)

            _escrever("mudo.py", 'def f(diagnostico):\n'
                                 '    diagnostico["so_grava"] = 1\n')
            _escrever("falante.py", 'def g(diagnostico, d):\n'
                                    '    diagnostico["tem_leitor"] = 2\n'
                                    '    return d.get("tem_leitor")\n')
            _grava, _le = gravadas_e_lidas(_t)
            ok("acha a chave que só é gravada", "so_grava" in _grava)
            ok("e a que tem leitor também é vista", "tem_leitor" in _grava)
            ok("o leitor é encontrado", "tem_leitor" in _le)
            _m = dict(mudas(_t))
            ok("a muda é acusada", "so_grava" in _m)
            ok("e a falante NÃO é", "tem_leitor" not in _m)

            # ASPAS SIMPLES CONTAM COMO LEITURA. Foi exatamente aqui que a
            # primeira versão deste verificador errou, e o alarme falso
            # anunciou que o motor não chegava à tela.
            _escrever("aspas.py", "def h(diagnostico, d):\n"
                                  "    diagnostico['simples'] = 3\n"
                                  "    return d.get('simples')\n")
            ok("leitura com aspas simples conta como leitura",
               "simples" not in dict(mudas(_t)))

            # VERIFICADOR NÃO É LEITOR. Guarda que lê não é tela que mostra,
            # e o defeito é o dado não chegar a quem trabalha.
            _escrever("checar_falso.py", 'def z(d):\n'
                                         '    return d.get("so_grava")\n')
            ok("leitura dentro de um verificador não salva a chave",
               "so_grava" in dict(mudas(_t)))

        # ── REGRA 2, COM O DEFEITO REAL DO TIGRE ────────────────────────
        #
        # Este é o prompt que gerou a peça 7 errada, reduzido ao que importa.
        # Se o verificador não acusar ISTO, ele é verde por acidente.
        _tigre = (
            "O PRODUTO É O DESTAQUE:\n"
            "- O produto ocupa de 30% a 45% da dimensao util do quadro.\n"
            "\n"
            "CORREÇÃO OBRIGATÓRIA:\n"
            "- mostre o pêndulo desobstruído, ocupando mais da metade do quadro\n")
        _v = vozes_numericas(_tigre)
        ok("acusa as duas vozes numéricas do prompt do Tigre",
           "tamanho do produto no quadro" in _v)
        ok("e nomeia as DUAS, não só uma",
           len(_v.get("tamanho do produto no quadro", [])) == 2)

        # UMA VOZ SÓ NÃO É DEFEITO — senão ele reprovaria todo prompt.
        _uma = ("O PRODUTO É O DESTAQUE:\n"
                "- O produto ocupa de 30% a 45% da dimensao util do quadro.\n")
        ok("prompt com uma voz só passa", not vozes_numericas(_uma))

        # REDUNDÂNCIA SEM NÚMERO TAMBÉM NÃO É DEFEITO. Duas vozes dizendo
        # "não deforme" é reforço; só o número faz duas vozes discordarem.
        _sem_num = ("O PRODUTO É O DESTAQUE:\n"
                    "- O produto ocupa de 30% a 45% da dimensao util do quadro.\n"
                    "\n"
                    "CORREÇÃO OBRIGATÓRIA:\n"
                    "- mostre o pêndulo desobstruído e sem mãos por cima\n")
        ok("voz sem número não conta como segunda voz",
           not vozes_numericas(_sem_num))

        # E O ALARME FALSO QUE ELE JÁ DEU: "NUNCA metade de um lado e metade
        # do outro" é POSIÇÃO, não folga da borda. Acusar isso reprovaria a
        # REGRA DE DENSIDADE por uma frase que não fala de folga.
        _falso = ("REGRA DE ESPAÇO DESTA PEÇA:\n"
                  "- A FOLGA DA BORDA MANDA: pelo menos 6% em cada lado\n"
                  "\n"
                  "REGRA DE DENSIDADE:\n"
                  "- NUNCA distribuídos pelos quatro cantos, NUNCA metade\n"
                  "  de um lado e metade do outro.\n")
        ok("não confunde 'metade de um lado' com folga da borda",
           "folga da borda" not in vozes_numericas(_falso))

        # ── REGRA 3, com o defeito que ela existe para pegar ────────────
        ok("folgas iguais em todas as peças não acusam nada",
           not folgas_divergentes({
               "2 — Benefícios": "callout a pelo menos 6% da borda",
               "4 — Close": "cartão a pelo menos 6% em cada lado"}))
        _d3 = folgas_divergentes({
            "2 — Benefícios": "callout a pelo menos 6% da borda",
            "4 — Close": "cartão a pelo menos 8% em cada lado"})
        ok("peças com folgas DIFERENTES são acusadas", bool(_d3))
        ok("e o aviso nomeia as duas medidas", set(_d3) == {"6", "8"})
        ok("prompt sem medida de folga não inventa divergência",
           not folgas_divergentes({"1 — Capa": "nada encosta na margem"}))

        # NO REPOSITÓRIO DE VERDADE: o `motor` tem leitor. Se esta asserção
        # cair, o verificador voltou a dar o alarme falso de origem.
        ok("no repositório, o `motor` NÃO é acusado de mudo",
           "motor" not in dict(mudas()))
        ok("e a tela do diagnóstico é encontrada",
           len(chaves_na_tela()) >= 5)
        ok("toda isenção tem motivo escrito",
           all(isinstance(v, str) and len(v) > 25
               for v in MUDAS_POR_ESCOLHA.values()))
        ok("e nenhuma isenção é órfã", not isencoes_orfas())

        print("\nfalhas:", _f)
        sys.exit(1 if _f else 0)

    sys.exit(1 if main() else 0)
