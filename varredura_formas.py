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
def forma2_guarda_le_o_arquivo():
    """Verificador que lê o ARQUIVO inteiro em vez do bloco.

    Cinco guardas desta base já se acharam no próprio texto. `inspect.
    getsource` do bloco só vê a função; `open(__file__).read()` vê a guarda.
    """
    fora = []
    for nome, fonte in _fontes():
        if not (nome.startswith("checar_") or '__name__ == "__main__"' in fonte):
            continue
        for i, linha in enumerate(fonte.splitlines(), 1):
            if "open(__file__" in linha:
                fora.append(f"{nome}:{i}  lê o próprio arquivo — "
                            f"use inspect.getsource(bloco)")
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
            if re.search(r"except Exception:\s*\n\s*(#[^\n]*\n\s*)*pass", trecho):
                fora.append(f"{nome}:{no.lineno}  {no.name}")
    return fora


def main():
    blocos = [
        ("FORMA 1 — gravação com falha silenciosa (precisa de guarda de CONTEÚDO)",
         forma1_retorno_engolido()),
        ("FORMA 2 — guarda que lê o próprio arquivo",
         forma2_guarda_le_o_arquivo()),
        ("FORMA 3 — tela que nenhum verificador desenha",
         forma3_tela_sem_guarda()),
        ("FORMA 5 — arquivos gêmeos (um é cópia do outro)",
         forma5_arquivos_gemeos()),
        ("FORMA 6a — datetime.now() sem fuso (fora os isentos do portão)",
         forma6_datetime_sem_fuso()),
        ("FORMA 6b — session_state dentro de alvo de Thread",
         forma6_sessao_em_thread()),
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
