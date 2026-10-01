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


def _le_para_reescrever(raiz=None):
    """{chave: [linhas]} — leituras que só alimentam a escrita da MESMA chave.

    POR QUE ISTO EXISTE (30/09)
    --------------------------
    `diagnostico["enquadramento"]` é a frase que explica a MARGEM que o dono
    vê na peça: "o motor devolveu 1536x1024 em vez de quadrada — as faixas
    laterais foram preenchidas pelo Studio".

    Esta regra dava VERDE para ela, e a frase nunca chegou à tela. O motivo:

        diagnostico["enquadramento"] = (
            diagnostico.get("enquadramento", "")      <-- contado como LEITOR
            + " · repeti uma vez e voltou torta de novo")

    Ler o próprio campo para concatenar nele NÃO é entregar a ninguém. É a
    mesma leitura, do mesmo lado do balcão — e foi assim que o campo mais
    procurado desta base passou semanas escondido com o verificador verde.
    """
    achados = {}
    for arq in sorted(os.listdir(raiz or RAIZ)):
        if not arq.endswith(".py") or _eh_verificador(arq):
            continue
        arv = _arvore(os.path.join(raiz or RAIZ, arq))
        if arv is None:
            continue
        for n in ast.walk(arv):
            # alvo: d["chave"] = <expressao que contem d.get("chave")>
            if not isinstance(n, ast.Assign) or len(n.targets) != 1:
                continue
            alvo = n.targets[0]
            if not (isinstance(alvo, ast.Subscript)
                    and isinstance(alvo.value, ast.Name)
                    and alvo.value.id in DICTS_DIAG
                    and isinstance(alvo.slice, ast.Constant)
                    and isinstance(alvo.slice.value, str)):
                continue
            chave = alvo.slice.value
            for c in ast.walk(n.value):
                if (isinstance(c, ast.Call)
                        and isinstance(c.func, ast.Attribute)
                        and c.func.attr == "get"
                        and isinstance(c.func.value, ast.Name)
                        and c.func.value.id in DICTS_DIAG
                        and c.args and isinstance(c.args[0], ast.Constant)
                        and c.args[0].value == chave):
                    achados.setdefault(chave, []).append(f"{arq}:{c.lineno}")
    return achados


def mudas(raiz=None):
    """[(chave, [onde grava])] — gravadas e que não chegam a ninguém."""
    grava, le = gravadas_e_lidas(raiz)
    na_tela = chaves_na_tela(raiz)
    so_para_reescrever = _le_para_reescrever(raiz)
    fora = []
    for chave, onde in sorted(grava.items()):
        if chave in MUDAS_POR_ESCOLHA:
            continue
        # LER PARA REESCREVER A PROPRIA CHAVE NAO E LEITOR.
        descartar = set(onde) | set(so_para_reescrever.get(chave, []))
        leitores = [x for x in le.get(chave, []) if x not in descartar]
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
    # O ASSUNTO, E NAO A FRASE QUE JA QUEBROU — e a Forma 2 dentro do
    # proprio verificador.
    #
    # A primeira versao perguntava so por "exatamente N bloco", que e como a
    # voz do SISTEMA escreve. A segunda voz, na REGRA DE DENSIDADE, escrevia
    # "reproduza a mesma quantidade de blocos (...) mesmo que sejam 5 ou 6
    # blocos" — mesmo assunto, outra redacao, e o verificador via UMA voz so.
    # Foi o ChatGPT, lendo o codigo exportado em 01/10, que achou o que este
    # verificador existia para achar. Agora ele pergunta pelo ASSUNTO:
    # "quantidade/numero de blocos|cartoes", em qualquer redacao.
    "quantidade de blocos de texto":
        r"exatamente \d+ bloco|maximum \d+ information|"
        r"(?:quantidade|n[uú]mero) de (?:blocos|cart[õo]es)|"
        r"\d+ ou \d+ (?:blocos|cart[õo]es)",
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


_ABRE_ITEM = _re_voz.compile(r"^\s*(?:[-•*]\s|\d+[.)]\s)")


_SO_NUMERO = _re_voz.compile(r"\d+|metade|dois ter[cç]os", _re_voz.I)


def _assinatura(trecho):
    """O conjunto de medidas da linha — é por ele que duas vozes discordam."""
    return frozenset(m.group(0).lower() for m in _SO_NUMERO.finditer(trecho))


def _itens_do_bloco(bloco):
    """O bloco partido em ITENS. Marcador abre; linha sem marcador continua.

    Bloco sem marcador nenhum devolve o bloco inteiro como um item só — era
    esse o comportamento antigo, e ele continua valendo onde não há lista.
    """
    fora, atual = [], []
    for linha in (bloco or "").split("\n"):
        if _ABRE_ITEM.match(linha) and atual:
            fora.append("\n".join(atual))
            atual = []
        atual.append(linha)
    if atual:
        fora.append("\n".join(atual))
    return fora


_INICIO_DO_INGLES = "SECTION 2"


def metades_do_prompt(prompt):
    """O prompt partido em [brief PT, metade EN]. Uma só, quando não há EN.

    POR QUE PARTIR, E NÃO COMPARAR NÚMERO

    Quando esta regra passou a ler o prompt INTEIRO (01/10), ela começou a
    acusar o par português/inglês da MESMA medida — "ocupa de 50% a 65%" e
    "Product occupancy 50–65%". Uma decisão, duas redações, por desenho do
    prompt: alarme falso, que é o que este arquivo existe para não dar.

    A primeira correção foi exigir que os números DISCORDASSEM. Estava
    errada, e o `checar_mutacao` provou na mesma rodada: a entrada "a folga
    da borda volta a ter duas vozes com numero" reintroduz uma SEGUNDA voz
    em português com o MESMO 6% — duplicação genuína, Forma 5 esperando
    acontecer — e a guarda ficou verde.

    O que separa os dois casos não é o número: é a METADE. Duas vozes na
    mesma língua são duplicação; a mesma voz nas duas línguas é tradução.
    Divergência de número ENTRE as línguas continua sendo da Regra 5.
    """
    i = (prompt or "").find(_INICIO_DO_INGLES)
    if i < 0:
        return [prompt or ""]
    return [prompt[:i], prompt[i:]]


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

    UMA VOZ É UM ITEM, E NÃO UM BLOCO — e esta correção custou um defeito que
    ficou de pé em produção por dias.

    A primeira versão parava no primeiro achado de cada BLOCO (`break`), para
    não contar uma regra quebrada em duas linhas como duas vozes. Só que a
    REGRA DE DENSIDADE tem DOIS itens contíguos, sem linha em branco entre
    eles, e eles discordavam:

        - QUANDO HOUVER IMAGEM DE REFERÊNCIA DE LAYOUT, ELA MANDA. Reproduza
          a mesma quantidade de blocos (...) mesmo que sejam 5 ou 6 blocos.
        - Esta peça tem exatamente 1 bloco(s) de texto.

    Duas ordens contrárias sobre a mesma coisa, no mesmo bloco, uma delas
    mandando ignorar a outra com todas as letras — e o verificador via UMA
    voz só, porque o `break` o fazia sair no primeiro item.

    Agora o recorte é o ITEM: linha que começa com marcador (`- `, `• `,
    `1. `) abre uma voz; linha sem marcador continua a voz anterior. A
    proteção original fica de pé (regra em duas linhas = uma voz) e dois
    itens vizinhos deixam de se esconder um atrás do outro.
    """
    fora = {}
    for metade in metades_do_prompt(prompt):
      for assunto, padrao in ASSUNTOS_DO_PROMPT.items():
        vozes = []
        for bloco in blocos_do_prompt(metade):
            for item in _itens_do_bloco(bloco):
                linhas = item.splitlines()
                achou = False
                for i, linha in enumerate(linhas):
                    if not _re_voz.search(padrao, linha, _re_voz.I):
                        continue
                    trecho = linha + " " + (linhas[i + 1] if i + 1 < len(linhas)
                                            else "")
                    if _TRAZ_NUMERO.search(trecho):
                        vozes.append((_assinatura(trecho),
                                      linhas[0].strip()[:78]))
                        achou = True
                        break      # uma voz por ITEM, não uma por linha
                if achou:
                    continue
        if len(vozes) > 1:
            fora.setdefault(assunto, []).extend(l for _, l in vozes)
    return fora


# ── REGRA 2-bis: ORDEM QUE DEVOLVE AO MODELO UMA DECISÃO JÁ FECHADA ───────
#
# A Regra 2 só enxerga duas vozes quando as DUAS trazem número. Existe um
# segundo jeito de criar duas autoridades, e ele passa por baixo dela: uma
# frase SEM número que autoriza o modelo a mudar o número da outra.
#
# O caso, vivo em produção até 01/10 e em 6 dos 9 tipos:
#
#     - Esta peça tem exatamente 3 bloco(s) de texto.
#     - SE NÃO COUBEREM TODOS na coluna com essa folga, use MENOS cartões.
#
# A primeira fecha; a segunda reabre. "use MENOS" não tem dígito, então a
# Regra 2 não via nada — e eu cheguei a relatar ao dono que esta ordem
# impossível tinha sido removida. Não tinha: a minha varredura procurou
# "menos blocos" e o texto diz "menos cartões".
#
# QUEM ACHOU ISTO FOI O CHATGPT, lendo o código exportado. Ele descreveu o
# padrão certo: "qualquer coisa que o Python possa calcular não deve virar
# escolha do modelo". A guarda abaixo é esse padrão virado medida.
#
# ELA É ESTREITA DE PROPÓSITO. Guarda larga aqui reprovaria meio prompt e
# viraria ruído — e ruído ensina a ignorar o verificador. Só entra frase que
# ENTREGA AO MODELO uma decisão que o sistema já tomou antes da chamada.
REABREM_DECISAO = (
    (r"use\s+menos|escreva\s+menos|menos\s+(?:cart[õo]es|blocos)",
     "autoriza o modelo a mudar a QUANTIDADE, que o sistema já fechou"),
    (r"se\s+n[ãa]o\s+couber(?:em)?|caso\s+n[ãa]o\s+couber(?:em)?|"
     r"conforme\s+couber",
     "entrega ao modelo a decisão de 'o que cortar', que é do sistema"),
    (r"de\s+\d+\s+a\s+\d+\s+(?:cart[õo]es|blocos)|at[ée]\s+\d+\s+cart[õo]es",
     "manda uma FAIXA onde já existe um número fechado"),
    (r"bloco a menos|um bloco a menos",
     "autoriza o modelo a entregar um bloco a menos do que o sistema pediu"),
    (r"maximum\s+\d+\s+information",
     "diz 'no máximo N' onde o português já disse 'exatamente N' — "
     "'máximo' permite menos, e é a metade inglesa que fica mais perto do fim"),
)
_REABREM = tuple((_re_voz.compile(p, _re_voz.I), motivo)
                 for p, motivo in REABREM_DECISAO)


def ordens_que_reabrem(prompt):
    """[(linha, motivo)] das ordens que devolvem ao modelo decisão fechada."""
    fora = []
    for linha in (prompt or "").splitlines():
        for rx, motivo in _REABREM:
            if rx.search(linha):
                fora.append((linha.strip()[:88], motivo))
                break
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


# ── REGRA 5: A MESMA REGRA NAS DUAS LÍNGUAS ────────────────────────────────
#
# Dono, 29/09: *"localizar inconsistências (...) comandos em diferentes
# linguagens"*.
#
# O prompt diz cada regra DUAS vezes: o brief em português (SECTION 1, que o
# próprio texto chama de "the contract") e as seções em inglês que o repetem
# para o renderizador. 13% do prompt é inglês repetindo o português.
#
# Isso é de propósito e funciona — mas cada NÚMERO passa a existir em dois
# lugares. Mudar a ocupação de 50-65% para 40-55% no português e esquecer o
# inglês manda duas ordens contrárias ao motor, e o inglês está MAIS PERTO do
# fim do prompt, que é onde o modelo presta mais atenção.
#
# É a Forma 5 desta base atravessando a barreira do idioma: um nome, duas
# respostas.
PARES_PT_EN = {
    "ocupação do quadro": (r"ocupa de (\d+)% a (\d+)%",
                           r"[Oo]ccupancy (\d+)[–-](\d+)%"),
    "folga da borda": (r"pelo menos (\d+)% (?:em cada lado|da borda)",
                       r"at least (\d+)% on every side"),
    "nº de blocos de texto": (r"exatamente (\d+) bloco",
                              r"[Mm]aximum (\d+) information"),
}


def pares_divergentes(prompt):
    """{assunto: (valores PT, valores EN)} quando as duas línguas discordam."""
    fora = {}
    for assunto, (pt, en) in PARES_PT_EN.items():
        mpt = _re_voz.search(pt, prompt or "")
        men = _re_voz.search(en, prompt or "")
        # SÓ UMA DAS DUAS NÃO É DIVERGÊNCIA: nem toda regra é dobrada, e
        # exigir o par de todas reprovaria o prompt inteiro. O defeito é o
        # par EXISTIR e os números não baterem.
        if mpt and men and mpt.groups() != men.groups():
            fora[assunto] = (mpt.groups(), men.groups())
    return fora



# ── REGRA 6: O PEDIDO TEM DUAS METADES, E SÓ UMA ERA CONFERIDA ───────────
#
# Dono, 30/09: "o Gemini devolve o que o sistema pede, ué".
#
# Ele está certo, e é por isso que o trabalho todo é no PEDIDO. Só que o
# pedido tem duas metades:
#
#   o TEXTO         — 65 regras em `checar_prompts`, mais a ida e volta dos
#                     campos do cadastro e o prompt do ajuste fino
#   os PARÂMETROS   — `size=1024x1024`, `input_fidelity=high`, `aspectRatio
#                     1:1`. NENHUM verificador olhava para eles.
#
# E os parâmetros são a metade que produziu os quatro defeitos relatados no
# mesmo dia: sem `size` a imagem volta retangular e o Studio preenche — é a
# MARGEM, e o produto encolhe dentro dela; sem `input_fidelity` o produto é
# REDESENHADO. Alguém tira uma dessas linhas amanhã e os oito verificadores
# seguem verdes.
#
# A segunda metade desta regra: TODO CAMINHO QUE ENTREGA UMA IMAGEM DIZ POR
# ONDE ELA VEIO. Achado aqui: o caminho da OpenAI sem fotos
# (`client.images.generate`) devolvia a peça e não gravava diagnóstico
# nenhum — a tela mostrava "Motor —", e quem olha não tinha como saber que
# aquela peça saiu por um caminho que nem recebeu as fotos do produto.

# (funcao, o que a chamada TEM de mandar, por que)
# `devolve_imagem` separa quem entrega BYTES de quem entrega a resposta HTTP
# crua. `_chamar_gemini_geracao_texto` devolve `(resp, erro)`: quem extrai a
# imagem e grava o diagnostico e o CHAMADOR, antes de chamar. A primeira
# versao desta regra acusou essa funcao — alarme falso meu, e verificador que
# da alarme falso ensina a ignora-lo.
PARAMETROS_DO_MOTOR = [
    ("imagem.py", "_chamar_openai_geracao", "image_generation",
     ("size", "input_fidelity"), True,
     "sem `size` a imagem volta retangular e o Studio preenche (margem); "
     "sem `input_fidelity` o produto e redesenhado"),
    ("imagem.py", "_chamar_gemini_geracao_texto", "responseFormat",
     ("aspectRatio",), False,
     "sem pedir a proporcao o Gemini escolhe o formato e costuma devolver "
     "retangular — e ai a margem volta"),
]


# ── REGRA 6: O PEDIDO DE QUADRADA NAO TEM PLANO B SILENCIOSO ──────────────
#
# O Studio tenta varias formas de pedir a imagem quadrada, porque a
# documentacao do Google descreve mais de um nome de campo. Isso esta certo.
#
# O que estava errado era a ULTIMA da fila: uma forma SEM proporcao nenhuma.
# Recusadas as outras, ela passava, o Gemini escolhia o formato, devolvia
# retangular, e o enquadramento preenchia as sobras com faixa lisa — a
# MARGEM que o dono reclama desde 30/09. O sistema sabia que tinha falhado
# (gravava `proporcao_recusada`) e entregava a peca torta assim mesmo.
#
# A analise externa de 01/10 colocou a regra na frase certa: *"recusou ->
# erro explicito, nao autorizacao para gerar uma imagem que o
# pos-processamento tera de remendar com faixa"*.
#
# Esta guarda reprova qualquer entrada de `_formas` cujo corpo nao peca
# proporcao. Ela nao limita QUANTAS formas existem — nome de campo pode
# mudar, e tentar varios e o certo. Ela exige que todas pecam o quadrado.
FORMAS_DE_PROPORCAO = ("imagem.py", "_chamar_gemini_geracao_texto", "_formas")


def formas_sem_proporcao(raiz=None):
    """[nome] das formas de pedido que NAO pedem proporcao. Vazio = ok."""
    arq, func, var = FORMAS_DE_PROPORCAO
    arv = _arvore(os.path.join(raiz or RAIZ, arq))
    if arv is None:
        return ["não consegui ler " + arq]
    fn = next((n for n in ast.walk(arv)
               if isinstance(n, ast.FunctionDef) and n.name == func), None)
    if fn is None:
        return [f"a função {func} nem existe mais"]
    lista = None
    for n in ast.walk(fn):
        if (isinstance(n, ast.Assign) and isinstance(n.value, ast.List)
                and any(isinstance(a, ast.Name) and a.id == var
                        for a in n.targets)):
            lista = n.value
            break
    if lista is None:
        return [f"a lista {var} nem existe mais em {func}"]
    fora = []
    for item in lista.elts:
        texto = ast.unparse(item)
        if "aspectRatio" not in texto and "aspect_ratio" not in texto:
            nome = (item.elts[0].value
                    if isinstance(item, ast.Tuple) and item.elts
                    and isinstance(item.elts[0], ast.Constant)
                    else ast.unparse(item)[:40])
            fora.append(str(nome))
    return fora


def parametros_do_motor(raiz=None):
    """[(funcao, faltando, motivo)] — parametro que o motor precisa e nao vai."""
    fora = []
    for arq, func, marca, exigidos, _img, motivo in PARAMETROS_DO_MOTOR:
        arv = _arvore(os.path.join(raiz or RAIZ, arq))
        if arv is None:
            continue
        fn = next((n for n in ast.walk(arv)
                   if isinstance(n, ast.FunctionDef) and n.name == func), None)
        if fn is None:
            fora.append((f"{arq}:{func}", list(exigidos),
                         "a funcao nem existe mais"))
            continue
        # o dicionario/chamada que carrega a marca daquele caminho
        achou = set()
        for n in ast.walk(fn):
            texto = ast.unparse(n) if isinstance(n, (ast.Dict, ast.Call)) else ""
            if marca not in texto:
                continue
            for p in exigidos:
                if f"'{p}'" in texto or f'"{p}"' in texto or f"{p}=" in texto:
                    achou.add(p)
        faltando = [p for p in exigidos if p not in achou]
        if faltando:
            fora.append((f"{arq}:{func}", faltando, motivo))
    return fora


def _grava_motor(no):
    """`diagnostico["motor"] = ...`, direto ou dentro de `if diagnostico:`."""
    if isinstance(no, ast.Assign):
        for alvo in no.targets:
            if (isinstance(alvo, ast.Subscript)
                    and isinstance(alvo.value, ast.Name)
                    and alvo.value.id in DICTS_DIAG
                    and isinstance(alvo.slice, ast.Constant)
                    and alvo.slice.value == "motor"):
                return True
        return False
    # o embrulho `if diagnostico is not None:` conta; um `if` sobre OUTRA
    # coisa, nao — ele pode gravar so num dos ramos.
    # `ast.walk(no)` INCLUI o proprio `no`: recursao infinita. Olha o corpo.
    if isinstance(no, ast.If) and any(
            d in ast.unparse(no.test) for d in DICTS_DIAG):
        for dentro in no.body + no.orelse:
            for x in ast.walk(dentro):
                if isinstance(x, ast.Assign) and _grava_motor(x):
                    return True
    return False


def _entrega_imagem(no):
    """`return <imagem>, None` — a saida de SUCESSO de um motor."""
    return (isinstance(no, ast.Return) and isinstance(no.value, ast.Tuple)
            and len(no.value.elts) == 2
            and not (isinstance(no.value.elts[0], ast.Constant)
                     and no.value.elts[0].value is None)
            and isinstance(no.value.elts[1], ast.Constant)
            and no.value.elts[1].value is None)


def entregas_mudas(raiz=None):
    """[(arquivo:linha, funcao)] — entrega imagem sem dizer por onde ela veio.

    Sobe pelos blocos que contem o `return` e procura, ANTES dele, a
    gravacao de `diagnostico["motor"]`. Olhar so a funcao inteira nao serve:
    um caminho grava e o irmao dele nao, e foi exatamente o que aconteceu.
    """
    fora = []
    for arq, func, _marca, _ex, devolve_imagem, _mot in PARAMETROS_DO_MOTOR:
        if not devolve_imagem:
            continue
        arv = _arvore(os.path.join(raiz or RAIZ, arq))
        if arv is None:
            continue
        fn = next((n for n in ast.walk(arv)
                   if isinstance(n, ast.FunctionDef) and n.name == func), None)
        if fn is None:
            continue
        pai = {}
        for n in ast.walk(fn):
            for f, valor in ast.iter_fields(n):
                if isinstance(valor, list):
                    for item in valor:
                        if isinstance(item, ast.AST):
                            pai[item] = (n, valor)
        for n in ast.walk(fn):
            if not _entrega_imagem(n):
                continue
            # sobe: em cada bloco, olha os irmaos ANTERIORES
            atual, disse = n, False
            while atual in pai and not disse:
                _p, irmaos = pai[atual]
                for irmao in irmaos[:irmaos.index(atual)]:
                    # SO CONTA O QUE DOMINA ESTE `return`.
                    #
                    # A primeira versao fazia `ast.unparse(irmao)` do bloco
                    # inteiro e procurava o texto dentro. Um `if
                    # imagens_bytes:` vizinho, que grava o motor no ramo
                    # DELE, fazia o caminho SEM fotos passar como se
                    # tivesse gravado. Foi assim que a entrega muda da
                    # OpenAI escapou desta regra.
                    if _grava_motor(irmao):
                        disse = True
                        break
                atual = _p
            if not disse:
                fora.append((f"{arq}:{n.lineno}", func))
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

    # ── 6-bis. O PEDIDO DE QUADRADA SEM PLANO B SILENCIOSO ────────────
    _fsp = formas_sem_proporcao()
    if _fsp:
        falhas += 1
        print(f"FALHA  {len(_fsp)} forma(s) de pedido ao Gemini que NÃO pedem "
              "proporção:")
        for _f in _fsp:
            print(f"         · «{_f}»")
        print("       Recusado o quadrado, o certo é ERRO EXPLÍCITO. Gerar "
              "sem pedir devolve retangular, o enquadramento preenche as "
              "sobras, e a pessoa recebe a peça COM MARGEM.")

    # ── 6. OS PARAMETROS DO PEDIDO, E QUEM ENTREGA SEM SE IDENTIFICAR ──
    _pm = parametros_do_motor()
    if _pm:
        falhas += 1
        for onde, faltando, motivo in _pm:
            print(f"FALHA  {onde} nao manda {', '.join(faltando)} ao motor "
                  f"— {motivo}")
    _em = entregas_mudas()
    if _em:
        falhas += 1
        for onde, func in _em:
            print(f"FALHA  {onde} entrega uma imagem sem gravar "
                  f"`diagnostico['motor']` — a tela mostra 'Motor —' e "
                  f"ninguem sabe por onde a peca saiu ({func})")

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
        _reabrem = {}
        for _tipo in _img.TIPOS_PADRAO:
            # O PROMPT INTEIRO, E NAO SO O BRIEF EM PORTUGUES.
            #
            # Ate 01/10 esta regra lia so `montar_prompt_imagem` — a SECAO 1.
            # A metade em ingles e colada depois, por `gerar_imagem_ia`, e e
            # ela que carrega "Maximum N information elements". O verificador
            # dizia verde sobre um texto que nao lia: a Forma 3.
            _base = _img.montar_prompt_imagem(_tipo, "", _dados, "Produto",
                                              plano_triagem=_plano,
                                              direcao_arte=_dir)
            _p = _img.prompt_que_sera_enviado(
                _base, [b"foto"], tipo=_tipo) or _base
            for _a, _vs in vozes_numericas(_p).items():
                _achados.setdefault(_a, set()).update(_vs)
            for _l, _mot in ordens_que_reabrem(_p):
                _reabrem.setdefault(_l, _mot)
        if _reabrem:
            falhas += 1
            print(f"FALHA  {len(_reabrem)} ordem(ns) que devolvem ao modelo "
                  "uma decisão que o sistema já tomou:")
            for _l, _mot in sorted(_reabrem.items()):
                print(f"         · {_l}")
                print(f"           {_mot}")
            print("       O que o Python pode calcular não vira escolha do "
                  "modelo. Feche a decisão antes da chamada.")
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

    # REGRA 5 — as duas línguas do prompt dizem o mesmo número?
    try:
        _pares = {}
        for _tipo in _img.TIPOS_PADRAO:
            _base = _img.montar_prompt_imagem(
                _tipo, "", _dados, "Produto", plano_triagem=_plano,
                direcao_arte=_dir)
            _cheio = _img.prompt_que_sera_enviado(
                _base, [b"foto"], tipo=_tipo) or _base
            for _a, _v in pares_divergentes(_cheio).items():
                _pares.setdefault(f"{_a} · {_tipo[:16]}", _v)
        if _pares:
            falhas += 1
            print(f"FALHA  {len(_pares)} regra(s) com números diferentes em "
                  "português e inglês, no mesmo prompt:")
            for _a, (_pt, _en) in _pares.items():
                print(f"         {_a}:  PT={_pt}  EN={_en}")
            print("       O inglês fica mais perto do fim do prompt, que é "
                  "onde o modelo presta mais atenção.")
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

        # ── REGRA 5, com o defeito que ela existe para pegar ────────────
        _pt_en_ok = ("- O produto ocupa de 50% a 65% da dimensao util\n"
                     "COMPOSITION: Product occupancy 50–65% of frame.\n")
        ok("as duas línguas com o mesmo número passam",
           not pares_divergentes(_pt_en_ok))
        _pt_en_mau = ("- O produto ocupa de 40% a 55% da dimensao util\n"
                      "COMPOSITION: Product occupancy 50–65% of frame.\n")
        _dv = pares_divergentes(_pt_en_mau)
        ok("português e inglês discordando é acusado", bool(_dv))
        ok("e o aviso mostra OS DOIS valores",
           _dv.get("ocupação do quadro") == (("40", "55"), ("50", "65")))
        ok("só o português, sem o par em inglês, NÃO é divergência",
           not pares_divergentes("- O produto ocupa de 40% a 55% da dimensao"))
        ok("e só o inglês também não",
           not pares_divergentes("COMPOSITION: Product occupancy 50–65%"))

        # ── REGRA 4, com o comando órfão que ela pegou ──────────────────
        import tempfile as _tf2
        with _tf2.TemporaryDirectory() as _t2:
            open(os.path.join(_t2, "chat_assistente.py"), "w",
                 encoding="utf-8").write(
                'st.session_state["chat_orfa"] = 1\n'
                'st.session_state["chat_lida"] = 2\n')
            open(os.path.join(_t2, "imagem.py"), "w", encoding="utf-8").write(
                'x = st.session_state.pop("chat_lida", [])\n')
            open(os.path.join(_t2, "ferramentas_chat.py"), "w",
                 encoding="utf-8").write("")
            _of = dict(filas_orfas(_t2))
            ok("fila escrita e nunca consumida é acusada", "chat_orfa" in _of)
            ok("e a fila com consumidor NÃO é", "chat_lida" not in _of)

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
