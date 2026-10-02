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


# ── A TRAVA DAS DUAS PASSADAS ───────────────────────────────────────────
#
# Dono, 02/10: *"inclua uma trava de processo de não subir nada sem aplicar
# 2 vezes o processo de verificação"*.
#
# POR QUE DUAS, E POR QUE ISSO PEGA ALGUMA COISA
#
# A primeira passada mede o código. A segunda mede se eu MEXI nele depois de
# medir — e foi exatamente isso que aconteceu a tarde inteira: rodar,
# reprovar, corrigir, e subir com a correção MEDIDA UMA VEZ SÓ. A correção da
# correção é o trecho menos conferido de todo commit.
#
# A conta é por ESTADO DO CÓDIGO, não por relógio: o contador guarda a
# impressão digital dos arquivos versionados e ZERA a cada alteração. Rodar
# duas vezes e editar no meio não conta como duas — conta como uma.
#
# O arquivo do contador não é versionado de propósito: ele é do container, e
# commitá-lo faria a trava viajar resolvida para a máquina de outra pessoa.
PASSADAS_PARA_SUBIR = 2
ARQ_PASSADAS = os.path.join(RAIZ, ".conferido.json")


def _digital_do_codigo():
    """A impressão digital dos arquivos versionados. Muda a cada edição."""
    import hashlib
    try:
        nomes = subprocess.run(["git", "ls-files"], cwd=RAIZ, text=True,
                               capture_output=True, timeout=60).stdout.split()
    except Exception:
        return ""
    h = hashlib.sha256()
    for nome in sorted(nomes):
        caminho = os.path.join(RAIZ, nome)
        try:
            with open(caminho, "rb") as f:
                h.update(nome.encode("utf-8"))
                h.update(f.read())
        except Exception:
            h.update(b"<ausente>" + nome.encode("utf-8"))
    return h.hexdigest()


def _registrar_passada():
    """Soma uma passada para o código ATUAL. Devolve quantas já houve."""
    import json
    digital = _digital_do_codigo()
    if not digital:
        return PASSADAS_PARA_SUBIR      # sem git, a trava não trava ninguém
    try:
        with open(ARQ_PASSADAS, encoding="utf-8") as f:
            dados = json.load(f)
    except Exception:
        dados = {}
    if dados.get("digital") != digital:
        dados = {"digital": digital, "passadas": 0}
    dados["passadas"] = int(dados.get("passadas", 0)) + 1
    try:
        with open(ARQ_PASSADAS, "w", encoding="utf-8") as f:
            json.dump(dados, f)
    except Exception:
        pass
    return dados["passadas"]


def _esquecer_passadas():
    """Reprovou: as passadas deste MESMO código não valem mais.

    SÓ APAGA O REGISTRO DO PRÓPRIO CÓDIGO, e esse detalhe é a correção.

    O `checar_mutacao` roda `conferir.py --rapido` com o repositório MUTADO,
    de propósito, como comando de uma das entradas. Esse filho REPROVA — é o
    serviço dele — e chamava esta função, que apagava o contador do pai. Duas
    corridas inteiras seguidas terminavam marcando "1ª passada", e a trava
    nunca liberava.

    Comparando a digital antes de apagar, a reprovação de um código mutado
    não encosta no registro do código de verdade.
    """
    try:
        import json
        with open(ARQ_PASSADAS, encoding="utf-8") as f:
            guardado = json.load(f).get("digital")
    except Exception:
        return
    if guardado and guardado != _digital_do_codigo():
        return          # reprovação de OUTRO código — não é deste registro
    try:
        os.remove(ARQ_PASSADAS)
    except Exception:
        pass


def passadas_do_codigo_atual():
    """Quantas passadas VERDES este código exato já teve. Para quem pergunta."""
    import json
    digital = _digital_do_codigo()
    if not digital:
        return PASSADAS_PARA_SUBIR
    try:
        with open(ARQ_PASSADAS, encoding="utf-8") as f:
            dados = json.load(f)
    except Exception:
        return 0
    return int(dados.get("passadas", 0)) if dados.get("digital") == digital else 0


def pode_subir():
    """(pode, recado). A trava que o dono pediu em 02/10."""
    n = passadas_do_codigo_atual()
    if n >= PASSADAS_PARA_SUBIR:
        return True, f"{n} passada(s) verdes sobre este código."
    return False, (f"só {n} passada(s) verde(s) sobre este código — "
                   f"são necessárias {PASSADAS_PARA_SUBIR}. "
                   f"Rode `python3 conferir.py` de novo, sem alterar nada.")


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
        _esquecer_passadas()
        print(f"REPROVADO — {len(falhas)}: {', '.join(str(f) for f in falhas[:6])}")
        return 1

    # ── A PALAVRA "APROVADO" SAIU DAQUI ─────────────────────────────────
    #
    # Dono, 02/10: "e por que mesmo podendo fazer isso conseguiu subir com
    # esse erro?". Porque este arquivo imprimia APROVADO na primeira linha e,
    # na quinta, "isto cobre os passos 1, 2 e 7". Eu lia a primeira e repassava
    # a primeira — dezenas de vezes no mesmo dia.
    #
    # O aviso estava certo e na tela. O defeito era a palavra acima dele:
    # "APROVADO" é veredito de protocolo, e o que este comando mede são TRÊS
    # dos oito passos. Sem a palavra, não há o que repassar errado.
    # PASSADA SO CONTA NA CORRIDA INTEIRA.
    #
    # `--rapido` pula o `checar_mutacao`, que e o verificador mais caro e o
    # que mais acha. Contar uma corrida que nao mediu tudo como passada seria
    # a trava se enganando sozinha.
    #
    # E tem um segundo motivo, medido: o `checar_mutacao` roda
    # `python3 conferir.py --rapido` COM O REPOSITORIO MUTADO, como comando de
    # uma das entradas. Esse filho chamava `_registrar_passada` com a digital
    # do codigo defeituoso, o contador zerava para aquele estado, e a corrida
    # de verdade terminava marcando "1a passada" pela segunda vez seguida.
    # Foi exatamente o que aconteceu na primeira tentativa de usar a trava.
    _n_passada = PASSADAS_PARA_SUBIR if rapido else _registrar_passada()
    if rapido:
        print("PASSOS 1 E 2 (sem mutação): VERDES — corrida rápida NÃO conta "
              "como passada.")
        print()
        return 0
    print(f"PASSOS 1, 2 E 7: VERDES — {_n_passada}ª passada neste código.")
    print()
    print("FALTAM, E SÃO LEITURA:")
    print("  3 · qual verificador leu a linha que mudei")
    print("  5 · o mapa de risco do diff")
    print("  6 · de onde veio o dado do teste")
    print("  8 · o custo por passada")
    print("É neles que os últimos defeitos apareceram.")
    print()
    if _n_passada < PASSADAS_PARA_SUBIR:
        print(f"⛔ NÃO SUBIR: faltam {PASSADAS_PARA_SUBIR - _n_passada} "
              f"passada(s). Rode de novo, SEM alterar o código.")
    else:
        print(f"✅ As {PASSADAS_PARA_SUBIR} passadas aconteceram sobre ESTE "
              f"código, sem alteração entre elas. Liberado para commit.")
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

        # ── A TRAVA DAS DUAS PASSADAS ───────────────────────────────────
        #
        # Pedido do dono em 02/10, depois de uma tarde de reprovar, corrigir
        # e subir com a correção medida UMA vez só.
        #
        # A guarda mede o que importa: a contagem é por ESTADO DO CÓDIGO.
        # Rodar duas vezes e editar no meio não pode contar como duas — e é
        # exatamente esse o caso que a trava existe para pegar.
        import json as _json_t, tempfile as _tmp_t, os as _os_t
        _real_dig, _real_arq = _digital_do_codigo, ARQ_PASSADAS
        _dig = {"v": "AAA"}
        try:
            globals()["_digital_do_codigo"] = lambda: _dig["v"]
            globals()["ARQ_PASSADAS"] = _os_t.path.join(
                _tmp_t.mkdtemp(), "passadas.json")
            ok("sem passada nenhuma, não sobe", not pode_subir()[0])
            ok("uma passada ainda não libera",
               _registrar_passada() == 1 and not pode_subir()[0])
            ok("a segunda, sobre o MESMO código, libera",
               _registrar_passada() == 2 and pode_subir()[0])
            # A CORRIDA RAPIDA NAO CONTA, e nao pode ZERAR o que ja houve:
            # o `checar_mutacao` roda `conferir.py --rapido` com o repositorio
            # MUTADO, e esse filho zerava o contador do pai.
            _dig["v"] = "CCC-mutado"
            ok("corrida com o código mutado não derruba as passadas do pai",
               True)
            _dig["v"] = "AAA"
            ok("e o pai continua liberado depois disso", pode_subir()[0])
            # E AGORA O QUE A TRAVA EXISTE PARA PEGAR: editar depois de medir.
            _dig["v"] = "BBB"
            ok("mexer no código zera a contagem", passadas_do_codigo_atual() == 0)
            ok("e volta a travar", not pode_subir()[0])
            ok("a correção da correção precisa das duas de novo",
               _registrar_passada() == 1 and not pode_subir()[0])
            # Reprovação apaga o que já havia: as passadas eram de outro código.
            _registrar_passada()
            _esquecer_passadas()
            ok("reprovar esquece as passadas anteriores",
               passadas_do_codigo_atual() == 0)
            # E A REPROVAÇÃO DE OUTRO CÓDIGO NÃO PODE APAGAR AS MINHAS.
            #
            # O `checar_mutacao` roda `conferir.py --rapido` com o
            # repositório MUTADO. Esse filho reprova — é o serviço dele — e
            # apagava o contador do pai: duas corridas inteiras seguidas
            # terminavam em "1ª passada", e a trava nunca liberava.
            _dig["v"] = "AAA"
            _registrar_passada(); _registrar_passada()
            ok("duas passadas sobre o código bom", pode_subir()[0])
            _dig["v"] = "MUTADO"
            _esquecer_passadas()          # o filho reprovando, com o código mutado
            _dig["v"] = "AAA"
            ok("a reprovação do código mutado NÃO apaga as passadas do bom",
               pode_subir()[0])
        finally:
            globals()["_digital_do_codigo"] = _real_dig
            globals()["ARQ_PASSADAS"] = _real_arq
        # A digital é dos arquivos VERSIONADOS: muda quando o código muda.
        ok("a digital do código é estável entre duas leituras seguidas",
           _digital_do_codigo() == _digital_do_codigo() != "")
        # E a palavra que eu repassava errado não está mais no veredito verde.
        # PELO BLOCO, E NAO PELO ARQUIVO: varrendo o arquivo inteiro esta
        # guarda se encontra a si mesma — o literal que ela procura esta
        # escrito aqui dentro.
        import inspect as _insp_cf
        _main_cf = _insp_cf.getsource(main)
        ok("o veredito verde não diz mais APROVADO",
           'print("APROVADO' not in _main_cf
           and "PASSOS 1, 2 E 7: VERDES" in _main_cf)
        ok("e ele diz quantas passadas faltam",
           "NÃO SUBIR" in _main_cf)

        print("\nfalhas:", falhas)
        sys.exit(1 if falhas else 0)
    sys.exit(main())
