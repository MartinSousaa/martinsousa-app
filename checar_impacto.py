"""checar_impacto.py — quem mais lê o que este commit mudou.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
O dono, depois de a terceira correção seguida precisar de uma segunda
correção: *"como consegue programar algo que travaria outra coisa?"*

A resposta honesta é que o padrão é sempre o mesmo. Eu mudo uma coisa e não
listo quem lê ela:

    `tipo_canonico` passou a devolver o rótulo oficial — e o índice do plano
    era feito com o rótulo cru. A copy exata sumiu do prompt, em produção.

    O limite de fotos subiu de três para seis — e ninguém perguntou o que
    limita além da quantidade. Seis fotos de 10MB são timeout.

    `BLOCOS[5]` virou 4 — e a caneca tinha cinco cotas. A última sumiria.

E quando ele perguntou se eu ia seguir a regra de mapear o estrago antes, a
resposta tinha de ser não: a regra de resumir está no CLAUDE.md desde o
começo e eu escrevo longo mesmo assim. Regra escrita eu derivo.

Então isto aqui não é uma regra. É um passo que roda, e que reprova.

O QUE ELE FAZ
-------------
Olha o diff, acha os nomes de topo que mudaram (funções, constantes), e para
cada um pergunta:

    1. quem mais lê este nome?
    2. existe guarda cobrindo ele — auto-teste do módulo ou `checar_prompts.py`?

Nome mudado, com leitor em outro arquivo, e sem guarda nenhuma: reprova.

O QUE ELE NÃO FAZ
-----------------
Não entende semântica. Ele não sabe se a guarda testa a coisa certa — só que
existe uma. Isso é de propósito: uma ferramenta que tentasse julgar
qualidade erraria em silêncio, e silêncio aqui é o defeito que se quer matar.

COMO USAR
---------
    python3 checar_impacto.py                 # contra o que está em main
    python3 checar_impacto.py --contra HEAD~1
    python3 checar_impacto.py --listar        # só o mapa, sem reprovar
"""

import argparse
import os
import re
import subprocess
import sys

# Arquivos que SÃO guarda: encontrar o nome aqui já conta como coberto.
#
# ESTE ARQUIVO NÃO ESTÁ NA LISTA, E O TESTE FOI QUEM MOSTROU POR QUÊ.
#
# A primeira versão se incluía. Resultado: como o docstring aqui em cima cita
# `tipo_canonico` para explicar o defeito histórico, o próprio verificador
# dava `tipo_canonico` como coberto — e a prova que eu montei para ver se ele
# reprovava passou verde.
#
# É o mesmo defeito que ele existe para achar: uma guarda que combina com o
# que eu já tinha escrito. Quem confere não pode ser a própria cobertura.
# `checar_tela.py` entra aqui porque ele É uma guarda: desenha a tela inteira
# e reprova o que quebra. Sem ele na lista, toda função de tela que ele cobre
# aparecia como "sem guarda" — e um verificador que acusa o que já está
# coberto ensina a ignorar o verificador.
GUARDAS = ("checar_prompts.py", "checar_ordem.py", "auditar.py",
           "checar_tela.py")

# Nomes cuja mudança não precisa de guarda: são texto de tela, não regra.
IGNORAR = re.compile(r"^(_?[a-z]*(msg|titulo|label|rotulo|texto_ajuda)[a-z_]*)$")


def _git(*args):
    try:
        return subprocess.run(["git"] + list(args), capture_output=True,
                              text=True, timeout=60).stdout
    except Exception:
        return ""


def nomes_mudados(contra):
    """{arquivo: [nomes de topo tocados pelo diff]}."""
    diff = _git("diff", "-U0", contra, "--", "*.py")
    if not diff.strip():
        return {}
    por_arquivo, atual = {}, None
    for linha in diff.splitlines():
        if linha.startswith("+++ b/"):
            atual = linha[6:].strip()
            por_arquivo.setdefault(atual, set())
        elif linha.startswith("@@") and atual:
            # O git escreve o contexto da hunk depois do segundo @@ — é ali
            # que vem `def nome(` ou a linha de atribuição.
            cauda = linha.split("@@")[-1]
            m = re.search(r"\b(?:def|class)\s+(\w+)", cauda)
            if m:
                por_arquivo[atual].add(m.group(1))
        elif linha.startswith("+") and atual and not linha.startswith("+++"):
            corpo = linha[1:]
            m = re.match(r"(?:def|class)\s+(\w+)", corpo)
            if m:
                por_arquivo[atual].add(m.group(1))
            m = re.match(r"([A-Z_][A-Z0-9_]{2,})\s*=", corpo)
            if m:
                por_arquivo[atual].add(m.group(1))
    return {a: sorted(n for n in ns if n and not IGNORAR.match(n))
            for a, ns in por_arquivo.items() if ns}


def leitores(nome, dono):
    """{arquivo: quantas vezes lê}, fora do arquivo onde o nome mora.

    Só conta arquivo que IMPORTA o módulo dono. Sem isso, uma função chamada
    `main` aparecia como "lida por oito arquivos" — todos com um `main` só
    deles, nenhum falando com este. Ruído assim faz a saída virar papel de
    parede, e papel de parede não se lê.
    """
    modulo = os.path.splitext(os.path.basename(dono))[0]
    achados = {}
    for raiz, _dirs, arquivos in os.walk("."):
        if any(p in raiz for p in (".git", "__pycache__", "node_modules")):
            continue
        for arq in arquivos:
            if not arq.endswith(".py"):
                continue
            caminho = os.path.normpath(os.path.join(raiz, arq))
            try:
                texto = open(caminho, encoding="utf-8").read()
            except Exception:
                continue
            mesmo_arquivo = caminho.endswith(os.path.basename(dono))
            if not mesmo_arquivo and not re.search(
                    r"^\s*(?:import\s+" + re.escape(modulo)
                    + r"\b|from\s+" + re.escape(modulo) + r"\s+import)",
                    texto, re.M):
                continue
            n = len(re.findall(r"\b" + re.escape(nome) + r"\b", texto))
            if mesmo_arquivo:
                n -= len(re.findall(
                    r"^(?:def|class)\s+" + re.escape(nome) + r"\b", texto,
                    re.M))
                n -= len(re.findall(
                    r"^" + re.escape(nome) + r"\s*=", texto, re.M))
            if n > 0:
                achados[caminho] = n
    return achados


def tem_guarda(nome, dono):
    """O nome aparece em alguma guarda, ou no auto-teste do próprio módulo?"""
    onde = []
    for g in GUARDAS:
        if os.path.exists(g) and re.search(r"\b" + re.escape(nome) + r"\b",
                                           open(g, encoding="utf-8").read()):
            onde.append(g)
    # Auto-teste do próprio módulo: a parte depois de `if __name__`.
    try:
        texto = open(dono, encoding="utf-8").read()
        corte = texto.find('if __name__')
        if corte > 0 and re.search(r"\b" + re.escape(nome) + r"\b",
                                   texto[corte:]):
            onde.append(f"{os.path.basename(dono)} (auto-teste)")
    except Exception:
        pass
    return onde


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--contra", default="origin/main",
                    help="com o que comparar (padrão: origin/main)")
    ap.add_argument("--listar", action="store_true",
                    help="mostra o mapa e não reprova")
    args = ap.parse_args()

    mudados = nomes_mudados(args.contra)
    if not mudados:
        print(f"ok    nenhum nome de topo mudou contra {args.contra}")
        return 0

    falhas = 0
    for arquivo, nomes in sorted(mudados.items()):
        print(f"\n{arquivo}")
        for nome in nomes:
            lidos = leitores(nome, arquivo)
            fora = {a: n for a, n in lidos.items()
                    if os.path.basename(a) != os.path.basename(arquivo)
                    and os.path.basename(a) not in GUARDAS}
            guardas = tem_guarda(nome, arquivo)
            marca = "ok " if (guardas or not fora) else "SEM GUARDA"
            print(f"  {marca:11} {nome}")
            if fora:
                print("              lido por: "
                      + ", ".join(f"{os.path.basename(a)}×{n}"
                                  for a, n in sorted(fora.items())))
            if guardas:
                print("              guarda:   " + ", ".join(guardas))
            if fora and not guardas and not args.listar:
                falhas += 1

    if args.listar:
        print("\n(--listar: nada reprovado)")
        return 0
    if falhas:
        print(f"\nFALHA  {falhas} nome(s) mudado(s) com leitor em outro "
              "arquivo e sem guarda nenhuma.")
        print("       Escreva a guarda ANTES de subir — depois, ela sai "
              "parecida com o que você já fez.")
    else:
        print("\nok    todo nome mudado com leitor fora tem guarda")
    return falhas


if __name__ == "__main__":
    sys.exit(main())
