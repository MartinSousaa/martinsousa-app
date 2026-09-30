"""conferir.py — UM comando, e ele descobre os verificadores sozinho.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
O dono, depois de a terceira conferência seguida achar defeito novo:

    "Tem certeza? Você falou isso da primeira vez, mandei revisar e pegou
     novos dois erros quando tinha acabado de revisar!"

E depois:

    "Você precisa aplicar o refino em toda codificação do sistema 5 vezes
     seguidas, nas 5 você encontrará erros."

O diagnóstico dele estava certo, e a medição confirmou: o que eu fazia à mão
eu não fazia igual duas vezes. O passo 4 (mutação) virou `checar_mutacao.py`;
as cinco varreduras viraram `varredura_formas.py`. Sobrou a peça mais boba e
mais cara: **rodar tudo**.

O protocolo listava sete comandos, um embaixo do outro, para eu digitar na
ordem certa toda vez. Esquecer um é gratuito e silencioso — e foi assim que
eu relatei "cinco verificadores verdes" depois de editar um texto que nenhum
dos cinco lia.

A PARTE QUE IMPORTA: ELE DESCOBRE, NÃO TEM LISTA
------------------------------------------------
`conferir.py` varre o disco atrás de `checar_*.py` em vez de ter uma lista
escrita. Verificador novo entra sozinho. Se tivesse lista, o defeito seria o
de sempre: alguém escreve o oitavo verificador, esquece de somar aqui, e a
conferência continua dizendo "tudo verde" medindo sete.

Uso:
    python3 conferir.py            # os verificadores + os auto-testes
    python3 conferir.py --rapido   # pula `checar_mutacao` (que roda os outros)
"""
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))

# Arquivos que NÃO são auto-teste de módulo: são verificadores (rodam sozinhos),
# serviços (não terminam) ou conferências com duplo próprio.
# CADA EXCLUSAO COM O MOTIVO ESCRITO, e nao uma lista que eu redigito a cada
# vez. Exclusao sem motivo e o jeito mais facil de um modulo sair da
# conferencia sem ninguem perceber.
NAO_SAO_AUTOTESTE = {
    "tv_servico.py": "e um servico: sobe e fica no ar, nao termina",
    "tv_worker.py": "idem — worker, nao teste",
    "fechar_expediente_conferencia.py": "tem duplo proprio e roda o job",
    "fechar_expediente.py": "o __main__ EXECUTA o fechamento, nao confere",
    "gerar_params_historico.py": "gerador de uma vez so, roda o job",
    "conferir.py": "sou eu",
}


def pede_autoteste(nome):
    """Este módulo só confere quando chamado com `--autoteste`?

    A pergunta se responde no arquivo: um `__main__` que testa
    `"--autoteste" in sys.argv` tem DOIS caminhos — o da conferência e o do
    trabalho de verdade. Rodar sem a flag executa o trabalho, e num script
    que lê o Trello isso é uma chamada de rede que estoura sem credencial.

    Descobrir em vez de listar é o motivo de este arquivo existir: com lista
    escrita à mão, alguém escreve o terceiro módulo assim, esquece de somar,
    e a conferência segue dizendo verde medindo dois.

    POR AST, E NÃO POR TEXTO. A primeira versão lia os 400 primeiros
    caracteres depois do `__main__` — e `varredura_formas.py` lê a flag lá
    dentro de `main()`, na linha 704. Guarda que procura texto num recorte
    do arquivo erra por onde o autor escolheu escrever.
    """
    import ast
    try:
        arv = ast.parse(open(os.path.join(RAIZ, nome), encoding="utf-8").read())
    except Exception:
        return False
    for n in ast.walk(arv):
        # `"--autoteste" in sys.argv`, escrito onde for.
        if (isinstance(n, ast.Compare) and len(n.ops) == 1
                and isinstance(n.ops[0], ast.In)
                and isinstance(n.left, ast.Constant)
                and n.left.value == "--autoteste"):
            return True
    return False


def _roda(cmd, limite=900):
    try:
        p = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True,
                           timeout=limite)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 1, f"TEMPO LIMITE ({limite}s)"


def _reprovou(codigo, saida):
    """Os verificadores desta base não concordam: uns saem com código, outros
    só imprimem FALHA e saem com zero. Exigir um só deixaria metade passar."""
    return codigo != 0 or "FALHA" in saida or "Traceback" in saida


def verificadores():
    """Todo `checar_*.py` do disco, em ordem. Sem lista escrita."""
    return sorted(n for n in os.listdir(RAIZ)
                  if n.startswith("checar_") and n.endswith(".py"))


def modulos_com_autoteste():
    """Todo `.py` que tem bloco de conferência própria."""
    fora = []
    for n in sorted(os.listdir(RAIZ)):
        if not n.endswith(".py") or n.startswith("checar_"):
            continue
        if n in NAO_SAO_AUTOTESTE:
            continue
        try:
            if 'if __name__ == "__main__":' in open(
                    os.path.join(RAIZ, n), encoding="utf-8").read():
                fora.append(n)
        except Exception:
            pass
    return fora


def main():
    rapido = "--rapido" in sys.argv
    falhas = []

    print("═" * 62)
    print("PASSO 1 — OS VERIFICADORES")
    print("═" * 62)
    cod, saida = _roda([sys.executable, "-m", "compileall", "-q", "."])
    print(f"  {'ok   ' if cod == 0 else 'FALHA'}  compileall (sintaxe)")
    if cod != 0:
        falhas.append("compileall")
        print(saida[-800:])

    for v in verificadores():
        if rapido and v == "checar_mutacao.py":
            print(f"  pulado  {v} (--rapido)")
            continue
        cmd = [sys.executable, v]
        if v == "checar_ordem.py":
            cmd += [n for n in sorted(os.listdir(RAIZ)) if n.endswith(".py")]
        # O SETIMO DEMORA MAIS QUE OS OUTROS, E MATA-LO E PERIGOSO.
        #
        # 30/09: com 69 mutacoes ele passou de 900s, levou SIGKILL no meio
        # e deixou `imagem.py` MUTADO no disco — SIGKILL nao roda `finally`.
        # O passo 2 entao mediu o arquivo mutado e acusou quatro falhas que
        # nao existiam. Ele ganha um teto proprio, e depois dele o socorro
        # roda de qualquer jeito: se sobrou arquivo mutado, volta aqui.
        # 84 mutacoes, e sete delas rodam `checar_prompts` (~100s cada).
        # Teto apertado aqui NAO e conferencia mais rapida: e um KILL no
        # meio, e o KILL foi o que deixou o repositorio mutado em 30/09.
        _teto = 7200 if v == "checar_mutacao.py" else 900
        cod, saida = _roda(cmd, limite=_teto)
        if v == "checar_mutacao.py":
            _c2, _s2 = _roda([sys.executable, v, "--socorro"], limite=120)
            if "nada a restaurar" not in _s2:
                print(f"  AVISO  {_s2.strip()[:100]}")
        ruim = _reprovou(cod, saida)
        ultima = [l for l in saida.strip().split("\n") if l.strip()]
        print(f"  {'FALHA' if ruim else 'ok   '}  {v:22} "
              f"{ultima[-1][:70] if ultima else ''}")
        if ruim:
            falhas.append(v)
            for l in saida.split("\n"):
                if l.startswith("FALHA") or "Traceback" in l:
                    print(f"          {l[:110]}")

    print()
    print("═" * 62)
    print("PASSO 2 — OS AUTO-TESTES DE CADA MÓDULO")
    print("═" * 62)
    mods = modulos_com_autoteste()
    ruins = []
    for m in mods:
        # A FLAG QUANDO O MÓDULO PEDE. Sem isto, `analise_do_mes.py` ia ao
        # Trello de verdade e reprovava por falta de credencial — um módulo
        # são derrubando o protocolo inteiro.
        _cmd = [sys.executable, m]
        if pede_autoteste(m):
            _cmd.append("--autoteste")
        cod, saida = _roda(_cmd, limite=300)
        if _reprovou(cod, saida):
            ruins.append(m)
            print(f"  FALHA  {m}")
            for l in saida.split("\n"):
                if l.startswith("FALHA"):
                    print(f"          {l[:110]}")
    print(f"  {len(mods)} módulo(s) com conferência própria · "
          f"{len(ruins)} com falha")
    falhas += ruins

    # A varredura das Formas roda no laço acima, como todo mundo: quem pede
    # `--autoteste` recebe a flag por descoberta, não por nome escrito aqui.

    print()
    print("═" * 62)
    print("PASSO 7 — CONFLITO DE MERGE")
    print("═" * 62)
    cod, saida = _roda(["git", "diff", "--name-only", "--diff-filter=U"])
    em_conflito = [l for l in saida.split("\n") if l.strip()]
    marcadores = []
    for n in sorted(os.listdir(RAIZ)):
        if not n.endswith((".py", ".md", ".txt", ".toml")):
            continue
        try:
            for i, l in enumerate(
                    open(os.path.join(RAIZ, n), encoding="utf-8"), 1):
                if l.startswith(("<<<<<<< ", ">>>>>>> ")) or l.rstrip() == "=======":
                    marcadores.append(f"{n}:{i}")
        except Exception:
            pass
    print(f"  {'FALHA' if em_conflito else 'ok   '}  "
          f"{len(em_conflito)} arquivo(s) em conflito")
    print(f"  {'FALHA' if marcadores else 'ok   '}  "
          f"{len(marcadores)} marcador(es) commitado(s)")
    if em_conflito:
        falhas.append("conflito")
    if marcadores:
        falhas.append(f"marcadores: {marcadores[:5]}")

    print()
    print("═" * 62)
    if falhas:
        print(f"REPROVADO — {len(falhas)}: {', '.join(str(f) for f in falhas[:6])}")
        return 1
    print("APROVADO — verificadores, auto-testes e conflito, todos verdes.")
    print()
    print("Isto cobre os passos 1, 2 e 7 do protocolo. Os passos 3 (qual")
    print("verificador leu a linha que mudei), 5 (mapa de risco), 6 (de onde")
    print("veio o dado do teste) e 8 (custo por passada) continuam sendo")
    print("leitura — e é neles que os quatro últimos defeitos apareceram.")
    return 0


if __name__ == "__main__":
    if "--autoteste" in sys.argv:
        falhas = 0

        def ok(nome, cond):
            global falhas
            falhas += not cond
            print(("ok    " if cond else "FALHA ") + nome)

        # ELE DESCOBRE, NÃO TEM LISTA. É a única coisa que esta conferência
        # precisa provar de si mesma: se um dia alguém trocar a descoberta por
        # uma lista escrita, o oitavo verificador entra no repositório e a
        # conferência continua dizendo "verde" medindo sete.
        _no_disco = {n for n in os.listdir(RAIZ)
                     if n.startswith("checar_") and n.endswith(".py")}
        ok("acha TODO checar_*.py do disco",
           set(verificadores()) == _no_disco and len(_no_disco) >= 6)
        _fonte = open(__file__, encoding="utf-8").read()
        _corpo = _fonte.split('if __name__ == "__main__":')[0]
        ok("e NÃO tem lista escrita de verificadores",
           '"checar_ordem.py"' not in _corpo
           and "'checar_ordem.py'" not in _corpo)
        ok("o auto-teste vê os módulos com conferência própria",
           len(modulos_com_autoteste()) >= 40)
        ok("e não tenta rodar o serviço da TV nem a si mesmo",
           "tv_servico.py" not in modulos_com_autoteste()
           and "conferir.py" not in modulos_com_autoteste())

        # QUEM PEDE `--autoteste` SE DESCOBRE, NÃO SE LISTA.
        #
        # `analise_do_mes.py` sem a flag vai ao Trello de verdade e estoura
        # por falta de credencial: o protocolo reprovava um módulo são. A
        # saída fácil era acrescentá-lo à exceção escrita à mão ao lado de
        # `varredura_formas.py` — e aí o defeito é o de sempre: alguém
        # escreve o terceiro, esquece de somar, e a conferência segue
        # dizendo "verde" medindo dois.
        ok("`analise_do_mes.py` é reconhecido como quem pede --autoteste",
           pede_autoteste("analise_do_mes.py"))
        ok("e `varredura_formas.py` também",
           pede_autoteste("varredura_formas.py"))
        ok("e um módulo que roda sozinho NÃO recebe a flag",
           not pede_autoteste("queda_pontos.py"))
        ok("varredura_formas deixou de ser exceção escrita à mão",
           "varredura_formas.py" not in NAO_SAO_AUTOTESTE)
        ok("e analise_do_mes nunca virou exceção",
           "analise_do_mes.py" not in NAO_SAO_AUTOTESTE)
        # Reprova por CÓDIGO ou por FALHA impressa: os verificadores desta
        # base não concordam, e exigir um só deixaria metade passar.
        ok("reprova quem sai com código != 0", _reprovou(1, ""))
        ok("e quem imprime FALHA saindo com zero", _reprovou(0, "FALHA x"))
        ok("e não reprova o verde", not _reprovou(0, "ok tudo certo"))
        print("\nfalhas:", falhas)
        sys.exit(1 if falhas else 0)
    sys.exit(main())
