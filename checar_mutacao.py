"""checar_mutacao.py — o sétimo verificador: as guardas vêem o defeito?

POR QUE ELE EXISTE
------------------
Dono, 28/09, depois da terceira rodada de conferência seguida:

    "Tem certeza? Você falou isso da primeira vez, mandei revisar e pegou
     novos dois erros quando tinha acabado de revisar!"

Ele está certo, e a medição dá razão a ele. Em três rodadas do protocolo, os
seis verificadores acharam ZERO defeitos novos; o passo 5 — feito à mão —
achou quatro. Os seis rodam igual sempre; os passos 4 (mutação) e 5 (mapa de
risco) dependiam de eu lembrar, e à mão eu não faço igual duas vezes.

Este arquivo tira o passo 4 da mão. Cada entrada de `MUTACOES` é um defeito
REAL que já aconteceu nesta base: o arquivo, o trecho certo, o trecho errado,
e quem deveria reprovar. Ele reintroduz o defeito, roda o verificador, e
exige VERMELHO. Guarda que fica verde com o defeito de volta nunca foi
guarda — e três desta base nasceram assim.

REGRA DE OURO DAQUI: o arquivo é sempre restaurado, inclusive quando algo
explode no meio. Um verificador que deixa o repositório mutado é pior do que
não ter verificador nenhum.
"""
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))

# (nome, arquivo, trecho CERTO, trecho ERRADO, comando que tem de reprovar)
#
# O trecho certo tem de aparecer UMA vez. Se aparecer zero, o código mudou e
# esta entrada virou letra morta — e isso também é reprovado, porque mutação
# que não se aplica dá a impressão de cobertura que não existe.
MUTACOES = [
    # A MUTACAO TEM DE REINTRODUZIR O DEFEITO DE VERDADE.
    #
    # A primeira versao desta entrada so tirava a marca de fim do bloco — e o
    # verificador ficou verde, com razao: `trocar_texto_exato` tem um segundo
    # ancora ("para preencher espaco."), e o corte continuava certo. Eu li
    # aquele verde como "guarda fraca" e quase reescrevi uma guarda que
    # estava certa.
    #
    # Mutacao que nao reintroduz o defeito da alarme falso, e alarme falso
    # ensina a ignorar o verificador. Aqui volta o corte ORIGINAL, o que
    # apagava as seis regras da peca em 28/09.
    (
        "a troca da copy volta a apagar as regras da peca",
        "imagem.py",
        # DOIS CORTES: o corte antigo volta E a marca de fim sai. So o
        # primeiro nao basta — com a marca no lugar, o codigo antigo acha o
        # fim certo por tabela, e o verificador fica verde com razao.
        [
            ('    base = str(prompt or "")\n    i = base.find(MARCA_TEXTO_EXATO)\n    novo = bloco_texto_exato(textos)\n    if i < 0:\n        return base + novo\n    f = base.find(MARCA_FIM_TEXTO_EXATO, i)\n    if f >= 0:\n        fim = f + len(MARCA_FIM_TEXTO_EXATO)\n    else:\n        # PROMPT ANTIGO, sem a marca de fim: o bloco termina na última linha\n        # que `bloco_texto_exato` escreve. Cortar até a próxima "━━━" é o que\n        # levava as regras junto, e não se faz mais.\n        _ultima = "para preencher espaço."\n        _u = base.find(_ultima, i)\n        fim = (_u + len(_ultima)) if _u >= 0 else i + len(MARCA_TEXTO_EXATO)\n    return (base[:i].rstrip("\\n") + "\\n" + novo.lstrip("\\n")\n            + "\\n" + base[fim:].lstrip("\\n")).rstrip() + "\\n"',
             '    base = str(prompt or "")\n'
             "    i = base.find(MARCA_TEXTO_EXATO)\n"
             "    if i >= 0:\n"
             '        j = base.find("\u2501\u2501\u2501", i + len(MARCA_TEXTO_EXATO) + 1)\n'
             '        base = (base[:i].rstrip("\\n") + ("\\n\\n" + base[j:] if j > 0 else "")).rstrip()\n'
             "    return base + bloco_texto_exato(textos)"),
            ('        + MARCA_FIM_TEXTO_EXATO + "\\n"\n', ""),
        ],
        None,
        ["python3", "checar_prompts.py"],
    ),
    # A CHAMADA SAI INTEIRA, e nao "desligada" por um `or`.
    #
    # A guarda desta linha e por AST: um `(x, None, None) or revisar_tudo(...)`
    # deixa a chamada na arvore, e a guarda continua vendo — certissimo da
    # parte dela. Tirar a chamada e a unica mutacao honesta.
    (
        "a conferencia da peca sai do laco de geracao",
        "imagem.py",
        '                        img_bytes, _rel_txt, _rel_peca = revisar_tudo(\n                            img_bytes, tipo,\n                            fotos_ref=cfg["fotos_bytes"],\n                            gerar=_gerar_de_novo,\n                            prompt_base=prompt_final,\n                            pedido=cfg.get("instrucoes_extras", ""),\n                            aviso=lambda t, _i=i: barra.progress(\n                                _i / len(tipos), text=t[:70]),\n                        )\n',
        "                        _rel_txt = _rel_peca = None\n",
        ["python3", "checar_tela.py"],
    ),
    (
        "as fotos do produto param de chegar a conferencia",
        "imagem.py",
        '                            fotos_ref=cfg["fotos_bytes"],',
        "                            fotos_ref=[],",
        ["python3", "checar_tela.py"],
    ),
    (
        "a porta unica vira oca",
        "imagem.py",
        "    img, rel_peca = revisar_peca(img, tipo, fotos_ref=fotos_ref, gerar=gerar,\n"
        "                                 prompt_base=prompt_base, aviso=aviso)",
        "    rel_peca = None",
        ["python3", "checar_tela.py"],
    ),
    (
        "a cena do plano volta a mandar tamanho",
        "imagem.py",
        "        _cena = sem_medida_de_quadro(plano_triagem_item_cena)",
        '        _cena = str(plano_triagem_item_cena or "").strip()',
        ["python3", "checar_prompts.py"],
    ),
    (
        "volta a voz que manda encher a borda",
        "imagem.py",
        '          "- A FOLGA DA BORDA MANDA: pelo menos 6% em cada lado, e nenhum\\n"',
        '          "- Faixa vazia em volta da peça é área desperdiçada.\\n"\n'
        '          "- A FOLGA DA BORDA MANDA: pelo menos 6% em cada lado, e nenhum\\n"',
        ["python3", "checar_prompts.py"],
    ),
    (
        "a copy volta a ser cortada por linha",
        "imagem.py",
        "            if linhas and not _INICIO_DE_BLOCO.match(t):",
        "            if False:",
        ["python3", "imagem.py"],
    ),
    (
        "a refacao pior volta a substituir a boa",
        "imagem.py",
        "        if melhor_n is None or len(problemas) <= melhor_n:",
        "        if True:",
        ["python3", "imagem.py"],
    ),
    (
        "a base corrigida nao acompanha a segunda revisao",
        "imagem.py",
        "        prompt_base = trocar_texto_exato(prompt_base, certo)\n"
        "        nova_img, erro_g = gerar(prompt_base)",
        "        nova_img, erro_g = gerar(trocar_texto_exato(prompt_base, certo))",
        ["python3", "imagem.py"],
    ),
    (
        "o del das chaves de triagem volta a jogar o dado fora",
        "imagem.py",
        "                    guardar_plano_gerado()\n",
        "",
        ["python3", "checar_tela.py"],
    ),
    (
        "o refazer do chat volta a entregar sem conferir",
        "imagem.py",
        '            _img_rf, _rel_t_rf, _rel_p_rf = revisar_tudo(\n                _r["img"], _tp, fotos_ref=_fotos_rf, gerar=_gerar_rf,\n                prompt_base=_prompt, pedido=_ins,\n                aviso=lambda t: _b.progress(1.0, text=t[:70]))\n',
        '            _img_rf, _rel_t_rf, _rel_p_rf = _r["img"], None, None\n',
        ["python3", "checar_tela.py"],
    ),
    (
        "as fotos anexadas voltam a ser gravadas a cada tecla",
        "imagem.py",
        '            if st.session_state.get("img_fotos_no_disco") != _assin_ft:',
        "            if True:",
        ["python3", "checar_tela.py"],
    ),
]


def _roda(cmd):
    """(codigo, saida). Sem shell, e com o cwd na raiz do projeto."""
    p = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True,
                       timeout=600)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _reprovou(codigo, saida):
    """O verificador disse NAO? Codigo != 0, ou FALHA na saida.

    Os dois criterios porque os verificadores desta base nao concordam: uns
    saem com codigo, outros so imprimem FALHA e saem com zero. Exigir so um
    deixaria metade das mutacoes passando batido.
    """
    return codigo != 0 or "FALHA" in saida


def main():
    falhas = 0
    for nome, arquivo, certo, errado, cmd in MUTACOES:
        caminho = os.path.join(RAIZ, arquivo)
        with open(caminho, encoding="utf-8") as fh:
            original = fh.read()

        # UM DEFEITO PODE PRECISAR DE DOIS CORTES.
        #
        # O corte da copy so volta a apagar as regras se a marca de fim do
        # bloco TAMBEM sair — com ela no lugar, o codigo antigo acerta por
        # tabela. Mutacao pela metade deixa o verificador verde e me faz
        # acreditar que a guarda e fraca, quando ela esta certa.
        pares = certo if isinstance(certo, list) else [(certo, errado)]
        mutado, quebrou = original, ""
        for _c, _e in pares:
            n = mutado.count(_c)
            if n != 1:
                quebrou = (f"o trecho certo aparece {n} vez(es): "
                           f"{_c.strip()[:60]!r}")
                break
            mutado = mutado.replace(_c, _e)
        if quebrou:
            print(f"FALHA  '{nome}': {quebrou} em {arquivo} — a mutacao nao "
                  "se aplica mais, e esta entrada esta dando impressao de "
                  "cobertura que nao existe")
            falhas += 1
            continue

        try:
            with open(caminho, "w", encoding="utf-8") as fh:
                fh.write(mutado)
            codigo, saida = _roda(cmd)
        finally:
            # SEMPRE. Inclusive se o verificador estourar no meio.
            with open(caminho, "w", encoding="utf-8") as fh:
                fh.write(original)

        if _reprovou(codigo, saida):
            print(f"ok    com o defeito de volta, {' '.join(cmd)} reprova "
                  f"— {nome}")
        else:
            print(f"FALHA  '{nome}': reintroduzi o defeito e "
                  f"{' '.join(cmd)} continuou VERDE. A guarda dele nunca viu "
                  "o defeito, entao ela nao e guarda")
            falhas += 1

    if not falhas:
        print(f"\nok    {len(MUTACOES)} defeitos reais reintroduzidos, "
              "todos reprovados")
    print(f"\nfalhas: {falhas}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
