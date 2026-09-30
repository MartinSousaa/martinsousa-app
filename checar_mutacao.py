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
import time

RAIZ = os.path.dirname(os.path.abspath(__file__))

# (nome, arquivo, trecho CERTO, trecho ERRADO, comando que tem de reprovar)
#
# O trecho certo tem de aparecer UMA vez. Se aparecer zero, o código mudou e
# esta entrada virou letra morta — e isso também é reprovado, porque mutação
# que não se aplica dá a impressão de cobertura que não existe.
MUTACOES = [
    # ── 30/09: A PECA DO AJUSTE VOLTA A SER UMA CAIXA DO PROCESSO ──────
    #
    # `_PECA_EM_AJUSTE` era um global de modulo, com o custo DECLARADO na
    # propria docstring: "dois colaboradores ajustando pecas diferentes no
    # mesmo segundo podem trocar o numero entre si". Declarar e melhor que
    # esconder, mas nao e conserto — e era o MESMO defeito que `produto` e
    # `usuario` tinham, tres campos lado a lado no mesmo registro. Eu corrigi
    # dois e deixei o terceiro.
    (
        "a peca do ajuste volta a nao viajar pelo contexto por thread",
        "imagem.py",
        [("        _li_peca.marcar_contexto(peca=_valor)", "        pass")],
        None,
        ["python3", "imagem.py", "--autoteste"],
    ),
    # ── 30/09: O DETALHE DA TOLERANCIA VOLTA A VIAJAR POR UM GLOBAL ────
    #
    # `TOLERANCIA_DETALHE` era escrito por `_classificar_batidas` e lido pelo
    # laco duas linhas depois. Entre as duas, outra sessao podia classificar
    # OUTRA pessoa e sobrescrever. O que isso corrompe sao as tolerancias de
    # entrada e de almoco do Painel de Metas — numeros que entram no bonus.
    #
    # A mutacao devolve a caixa de modulo. Nota: a guarda ORIGINAL desta
    # funcao passava com o defeito de volta, porque comparava dois horarios
    # que davam tolerancia zero. Ela foi reescrita para 08:52 (tolerancia) x
    # 09:30 (atraso), medidos no proprio modulo — guarda fraca assina embaixo.
    (
        "o detalhe da tolerancia volta a morar numa caixa do processo",
        "relogio_ponto.py",
        [("    detalhe = dict(_TOLERANCIA_ZERADA)",
          "    global _TOL_CAIXA\n    _TOL_CAIXA = dict(_TOLERANCIA_ZERADA)\n"
          "    detalhe = _TOL_CAIXA"),
         ('_TOLERANCIA_ZERADA = {"entrada": 0, "almoco": 0}',
          '_TOLERANCIA_ZERADA = {"entrada": 0, "almoco": 0}\n_TOL_CAIXA = {}'),
         ('            _res_rp[rotulo] = (_t, dict(_det))',
          '            _res_rp[rotulo] = (_t, dict(_TOL_CAIXA))')],
        None,
        ["python3", "relogio_ponto.py"],
    ),
    # ── 30/09: A CAIXA DE PROCESSO SEM CLASSIFICACAO ───────────────────
    #
    # A regra nova obriga cada dicionario de modulo escrito em execucao a
    # responder "isto e de uma pessoa ou de todas?". Tirar uma declaracao e
    # o mesmo que introduzir uma caixa nova sem resposta — e e assim que a
    # familia inteira volta, num arquivo que ninguem estava olhando.
    (
        "uma caixa do processo fica sem classificacao",
        "checar_alcance.py",
        [('        "sheets.py:ID_RECUSADO": "id de planilha que o Drive recusou",\n', "")],
        None,
        ["python3", "checar_alcance.py"],
    ),
    # ── 30/09: A PECA QUE SUMIA SEM NOME ───────────────────────────────
    #
    # Dono: "nao gerou a imagem presenteando" e, depois, "investigue as fotos
    # nao geradas".
    #
    # Nao havia bug — havia um buraco. A peca bloqueada pela triagem era
    # listada com nome e motivo na tela do PLANO; no fim da geracao o Studio
    # apaga `img_triagem_plano` (ela e o sinal de "plano consumido"), o painel
    # das bloqueadas vive dentro do `if` dessa chave e some junto, e o placar
    # compara a galeria com as pecas VIAVEIS — entao dizia "8 de 8", em verde.
    #
    # A peca desaparecia no instante em que a galeria abria. Quem gerou via a
    # ausencia; a tela nunca a mencionava.
    #
    # A mutacao devolve a tela ao estado cego: a leitura sai e a lista fica
    # vazia. A guarda tem de ficar vermelha — ela confere a CHAMADA, porque a
    # funcao continuaria existindo e passando nos testes dela.
    (
        "a tela volta a esconder a peca que nem chegou a ser tentada",
        "imagem.py",
        [("    _bloqueadas_ger = pecas_bloqueadas_da_geracao()",
          "    _bloqueadas_ger = []")],
        None,
        ["python3", "imagem.py", "--autoteste"],
    ),
    # ── 30/09, A TERCEIRA VEZ DO MESMO DEFEITO ─────────────────────────
    #
    # Dono: "o produto esta GIGANTE nas maos da crianca". Eu atribui a peca 7,
    # corrigi a 7 e a 8, e deixei a 3 — cujo preset comeca com "PRODUTO NO
    # AMBIENTE DE USO REAL: deduza onde ESTE produto e de fato usado, e POR
    # QUEM". Cena com gente, igual as outras duas, e carregava "ocupa NO
    # MINIMO 45%" junto de "Nunca deixe o produto pequeno no centro de um
    # cenario amplo".
    #
    # Mesmo defeito, tres correcoes separadas: peca 8 em 29/09, peca 7 de
    # manha, peca 3 a noite. A mutacao tira a 3 do grupo de cena, que foi
    # exatamente o estado em que ela ficou entre uma correcao e outra.
    (
        "a peca do cenario de uso volta a receber porcentagem imposta",
        "imagem.py",
        [("TIPOS_DE_CENA = (3, 7, 8)", "TIPOS_DE_CENA = (7, 8)")],
        None,
        ["python3", "checar_prompts.py"],
    ),
    # ── 30/09: O NOME DO CAMPO QUE VIROU MARGEM EM TODA PECA ───────────
    #
    # Dono: "imagem 3 esta com margem na foto". E eu cheguei a responder que
    # isso "nao tinha conserto por codigo". TINHA — era o nome de um campo.
    #
    # O Studio pedia imagem quadrada ao Gemini por `responseFormat`, a API
    # respondia 400, e ele DESISTIA da proporcao. Toda peca voltava
    # retangular, o enquadramento preenchia as sobras com faixa lisa, e a
    # pessoa recebia a peca com margem. O nome documentado para o endpoint
    # generateContent e `imageConfig`.
    #
    # A mutacao devolve o nome errado na primeira tentativa. O Studio tem de
    # continuar achando o certo — mas a guarda exige mais que isso: exige que
    # o nome DOCUMENTADO seja o primeiro tentado, senao toda peca paga uma
    # chamada recusada antes de acertar.
    (
        "o pedido de imagem quadrada volta a usar o nome errado do campo",
        "imagem.py",
        [('                    "imageConfig": {"aspectRatio": "1:1", "imageSize": "1K"}}),\n'
          '                ("imageConfig sem tamanho", {\n'
          '                    "responseModalities": ["IMAGE"],\n'
          '                    "imageConfig": {"aspectRatio": "1:1"}}),',
          '                    "responseFormat": {"image": {"aspectRatio": "1:1"}}}),\n'
          '                ("imageConfig sem tamanho", {\n'
          '                    "responseModalities": ["IMAGE"],\n'
          '                    "responseFormat": {"image": {"aspectRatio": "1:1"}}}),')],
        None,
        ["python3", "imagem.py", "--autoteste"],
    ),
    # ── 30/09: A PECA NUNCA ERA COMPARADA COM AS FOTOS ─────────────────
    #
    # Dono: "por que que as imagens acabam sendo geradas diferente do que o
    # produto de fato e?".
    #
    # O prompt manda "TRAVA DE COR (regra inviolavel)" e "PROIBICAO ABSOLUTA:
    # JAMAIS substitua o produto das fotos" — e o Studio entregava sem nunca
    # comparar a peca com as fotos. Regra que ninguem confere e torcida.
    #
    # A mutacao tira a comparacao do caminho que entrega a peca. A funcao
    # continua existindo e passando nos testes dela: e por isso que a guarda
    # confere a CHAMADA, e nao a existencia.
    (
        "a peca volta a sair sem ser comparada com as fotos do produto",
        "imagem.py",
        [("        _dif_prod = _md.produto_diferente(img_bytes, imagens_referencia)\n"
          "        if _dif_prod:\n"
          "            _probs = list(_probs) + [_dif_prod]\n", "")],
        None,
        ["python3", "imagem.py", "--autoteste"],
    ),
    # ── 30/09: A REGUA NAO OLHAVA O TEXTO DA PECA ──────────────────────
    #
    # Dono, duas vezes: "os textos cortados foram corrigidos na causa raiz?".
    #
    # A resposta honesta era NAO: a regua conferia formato, faixa lisa e
    # ocupacao, e ninguem olhava se o texto tinha ficado inteiro dentro do
    # quadro. Tirar a contradicao do prompt trata a causa; sem medir o
    # resultado, e hipotese — e foi hipotese que me fez errar o dia inteiro.
    #
    # A medida so roda quando quem chama diz que a peca TEM texto. Perdido o
    # argumento, ela some em SILENCIO e a regua volta a aprovar peca com o
    # titulo decepado. Por isso a mutacao tira o argumento, e nao a funcao.
    (
        "a regua volta a nao olhar o texto da peca",
        "imagem.py",
        [(",\n                               com_texto=not _is_clean_photo)", ")")],
        None,
        ["python3", "imagem.py", "--autoteste"],
    ),
    # ── 30/09: SEIS VOZES SOBRE QUANTO UMA FRASE PODE TER ──────────────
    #
    # Dono: "as escritas estao sendo cortadas (...) aplicadas numa regiao que
    # nao da para ser escrita totalmente e ai fica a margem para fora".
    #
    # A copy e ESCRITA pelo prompt do plano e DESENHADA pelo prompt da
    # imagem. Havia seis textos dizendo o tamanho dela — dois na mesma regra
    # de densidade, a 33 linhas um do outro, tres em presets de peca e um no
    # plano — e nenhum lia o outro. Frase longa num cartao dimensionado para
    # frase curta transborda pela borda.
    #
    # Duas mutacoes, as duas pontas: a medida volta a ter duas vozes no
    # prompt da imagem, e o prompt do plano volta a ter medida propria.
    (
        "a regra de densidade volta a dizer o tamanho da frase duas vezes",
        "imagem.py",
        [("- Quanto mais longa a frase, mais letra inventada aparece nela: a medida do",
          "- Frase curta e o que sai certo. Titulo de 2 a 4 palavras, frase de 4 a 9.\n"
          "- Quanto mais longa a frase, mais letra inventada aparece nela: a medida do")],
        None,
        ["python3", "checar_prompts.py"],
    ),
    (
        "quem escreve a copy volta a ter medida propria, sem ler a fonte unica",
        "imagem.py",
        [("  {medida_do_bloco()}. Frase longa \u00e9 o que ele erra",
          "  Titulo de 2 a 4 palavras; frase de 4 a 9. Frase longa \u00e9 o que ele erra")],
        None,
        ["python3", "checar_prompts.py"],
    ),
    # ── 30/09: O MOTOR ERA GRAVADO E NUNCA MOSTRADO ────────────────────
    #
    # Dono, depois de eu pedir que ELE abrisse uma tela para conferir qual
    # motor a conta tinha: "eu que tenho que confirmar? voce que codificou o
    # sistema...".
    #
    # O Studio sabe qual motor fez cada peca e o registro dizia "enviado ao
    # motor" — sem dizer qual. E essa e a pergunta mais importante sobre uma
    # peca torta: margem e produto redesenhado vem de a peca ter sido feita
    # pelo RESERVA, que nao aceita `size=1024x1024` nem `input_fidelity`.
    #
    # A PRIMEIRA CORRECAO TROPECOU NO MESMO DEFEITO: gravei a linha e
    # `cadeias` descarta toda acao que nao e prompt — o dado ia ser escrito
    # e nunca lido. Gravar sem ninguem ler nao e registro.
    #
    # Duas mutacoes porque sao duas pontas da mesma cadeia: quem ESCREVE e
    # quem MOSTRA. Cortar so uma deixaria a outra sem rede.
    (
        "o relatorio volta a ignorar qual motor fez a peca",
        "comparar_prompt.py",
        [("    mots = motores(linhas)", "    mots = {}")],
        None,
        ["python3", "comparar_prompt.py"],
    ),
    (
        "a linha do motor deixa de ser gravada com o nome que o leitor procura",
        "imagem.py",
        [('            "motor_da_peca",', '            "motor_da_peca_renomeado",')],
        None,
        ["python3", "comparar_prompt.py"],
    ),
    # ── 30/09: A PECA 7 VOLTA A TER UMA PORCENTAGEM IMPOSTA ────────────
    #
    # Dono: "o produto esta GIGANTE nas maos da crianca".
    #
    # A peca "Presenteie" mandava, no MESMO prompt, "O produto ocupa de 30% a
    # 45% da dimensao util do quadro. Nao e sugestao: e a medida desta peca" e
    # "Never enlarge the product beyond its real scale in the hands that hold
    # it". Duas ordens sobre o mesmo assunto; ganha a que se declara
    # inegociavel. Um compasso de 16 cm a 30-45% do quadro, na mao de uma
    # crianca, E gigante.
    #
    # A mutacao devolve a faixa. O verificador tem de ficar VERMELHO em duas
    # frentes: a medida volta a aparecer numa peca de cena, e a "ESCALA REAL"
    # sai dela.
    (
        "a peca do presente volta a receber porcentagem imposta",
        "imagem.py",
        [("    7: None,", "    7: (30, 45, 'handover'),")],
        None,
        ["python3", "checar_prompts.py"],
    ),
    # ── E A OUTRA METADE DA MESMA CORRECAO: O ROTEAMENTO ───────────────
    #
    # Tirar a porcentagem de `OCUPACAO` nao basta sozinho: quem decide QUAL
    # bloco de tamanho a peca recebe e `protagonismo_do_tipo`, e era por ali
    # que a peca 7 pegava "Nunca deixe o produto pequeno no centro de um
    # cenario amplo" — a MESMA linha que ja tinha inflado a ambientacao em
    # 29/09, com o comentario que explica o defeito escrito logo acima dela.
    #
    # Duas metades, duas mutacoes. Uma entrada so deixaria a outra sem rede.
    (
        "a peca do presente volta a receber a regra das pecas de produto",
        "imagem.py",
        # A ANCORA ACOMPANHA O GRUPO. Ela era `(7, 8)` e ficou para tras
        # quando a peca 3 entrou — o verificador reprovou por "o trecho certo
        # aparece 0 vezes", que e exatamente o servico dele: mutacao que nao
        # encontra o alvo nao mede nada e ficaria verde por acidente.
        [("TIPOS_DE_CENA = (3, 7, 8)", "TIPOS_DE_CENA = (3, 8)")],
        None,
        ["python3", "checar_prompts.py"],
    ),
    # ── 30/09: O CONTEXTO DO LOG ERA UM DONO SO PARA A EQUIPE INTEIRA ──
    #
    # `log_imagem._CONTEXTO` era um dicionario de MODULO, e o Streamlit serve
    # todos os colaboradores no mesmo processo. `marcar_contexto` roda a cada
    # desenho de pagina: a segunda pessoa a abrir a tela Imagem sobrescrevia a
    # primeira, e o log da primeira passava a gravar o produto e o usuario da
    # segunda.
    #
    # O custo nao foi so o log torto. O historico do «Compasso Cortador
    # Colorido» voltou com quatro pecas de OUTRO produto dentro, carimbadas
    # com o nome de quem nao as gerou — e a analise feita em cima dele
    # apontou um defeito no PLANO que nao existia. Campo vazio a gente ve;
    # campo errado se le como verdade.
    #
    # A guarda ANTERIOR nao via isso: ela marcava UM contexto e conferia que
    # ele chegava. Com um dono so, global e por-thread dao a mesma resposta.
    # A mutacao volta `ident` para uma constante, que e exatamente o global
    # de processo de antes, e exige vermelho.
    (
        "o log volta a ter um contexto so para todos os colaboradores",
        "log_imagem.py",
        [("    ident = _threading_ctx.get_ident()\n",
          "    ident = 0\n")],
        None,
        ["python3", "log_imagem.py"],
    ),
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
        "o sinal do codigo de saida da varredura volta a ser invertido",
        "varredura_formas.py",
        "        return 1 if (_autoteste() + _autoteste_das_cinco()) else 0",
        "        return 0 if (_autoteste() and _autoteste_das_cinco()) else 1",
        ["python3", "conferir.py", "--rapido"],
    ),
    (
        "checar_impacto volta a ser cego a arquivo novo nao rastreado",
        "checar_impacto.py",
        '    novos = [n for n in _git("ls-files", "--others", "--exclude-standard",\n'
        '                             "--", "*.py").split() if n.endswith(".py")]',
        "    novos = []",
        ["python3", "checar_impacto.py", "--autoteste"],
    ),
    (
        "a conferencia volta a ler a pontuacao por conta propria",
        "conferencia_pontos.py",
        "        pt = ler_pontos(card, id_pontos)",
        "        pt = float(((card.get('customFieldItems') or [{}])[0]"
        ".get('value') or {}).get('number') or 0)",
        ["python3", "conferencia_pontos.py"],
    ),
    (
        "o mes indeterminado volta a se confundir com 'outro mes'",
        "conferencia_pontos.py",
        '        if mes_do_card is None:\n            return "mes_desconhecido"',
        '        if mes_do_card is None:\n            return "outro_mes"',
        ["python3", "conferencia_pontos.py"],
    ),
    (
        # 29/09: o cabecalho anunciou "Diferenca 12506 pts" e 11836 deles eram
        # cartoes de OUTRO MES, que a conta crua ignora de proposito. Alarme
        # falso ensina a equipe a ignorar a tela de conferir.
        "'outro mes' volta a ser contado como perda no cabecalho",
        "conferencia_pontos.py",
        '                     if d.get("motivo") not in MOTIVOS_ESPERADOS), 2)',
        "                     ), 2)",
        ["python3", "conferencia_pontos.py"],
    ),
    (
        # O mesmo alarme falso, por pessoa: a Myrella leu "Diferenca 5699" como
        # 5.699 pontos roubados dela, e eram junho, julho e agosto.
        "a tabela por pessoa volta a subtrair duas colunas de escopos diferentes",
        "placar.py",
        '          "Perdeu sem explicação": _perda_pm.get(_u, 0.0),',
        '          "Perdeu sem explicação": _v["diferenca"],',
        ["python3", "conferencia_pontos.py"],
    ),
    (
        # O aviso amarelo saia de `contagem_crua`, que ignora o mes: embaixo de
        # um painel de setembro ele anunciava o acumulado de quatro meses.
        "o aviso de ponto sem dono volta a somar todos os meses",
        "placar.py",
        '    _sem_dono = _cf.sem_dono_no_mes(d.get("cards_pts"), MEMBROS_ATIVOS)',
        '    _sem_dono = _crua["qtd"]["pontos_fora_do_quadro"]',
        ["python3", "conferencia_pontos.py"],
    ),
    (
        # 28/09: 18 cartoes CONCLUIDOS foram movidos para a TRIAGEM entre
        # 10:50 e 17:32 e os pontos sairam inteiros, sem aviso. O dono decidiu
        # em 29/09: "configure para a triagem contabilizar pontos sim".
        "a TRIAGEM volta a nao pagar pontos",
        "placar_core.py",
        'LISTAS_SEM_PONTUACAO = {\n    "TABELA DE PONTUAÇÃO","CORREÇÃO DE FOTOS: 0 PONTOS",',
        'LISTAS_SEM_PONTUACAO = {\n    "TABELA DE PONTUAÇÃO","TRIAGEM","CORREÇÃO DE FOTOS: 0 PONTOS",',
        ["python3", "placar_core.py"],
    ),
    (
        # A Forma 1 desta base: corrigir numa lista e esquecer a irma.
        "a TRIAGEM sai tambem da lista de colunas que nao sao etapa",
        "placar_core.py",
        'COLUNAS_SKIP = {\n    "TABELA DE PONTUAÇÃO","TRIAGEM","PENALIDADES",',
        'COLUNAS_SKIP = {\n    "TABELA DE PONTUAÇÃO","PENALIDADES",',
        ["python3", "placar_core.py"],
    ),
    (
        # A lista escrita a mao trazia a TRIAGEM para o mostrador de tempo.
        "o tempo medio por coluna volta a ter lista escrita a mao",
        "placar.py",
        "            listas_t=[nl for nl in set(listas.values())\n"
        "                      if not _pc_core.coluna_em(nl, COLUNAS_SKIP)]",
        "            listas_t=[nl for nl in set(listas.values())\n"
        '                      if nl not in LISTAS_PENALIDADE and nl!="TABELA DE PONTUAÇÃO"\n'
        "                      and nl not in LISTAS_SEM_PONTUACAO]",
        ["python3", "placar_core.py"],
    ),
    (
        # Se a env var viesse primeiro, uma variavel esquecida numa maquina
        # apontaria a producao para o quadro errado, calada.
        "a variavel de ambiente passa na frente do st.secrets",
        "placar_core.py",
        "    try:\n        import streamlit as st\n        v = st.secrets[\"trello\"][chave_secrets]\n"
        "        if v:\n            return str(v)\n    except Exception:\n        pass\n"
        "    for n in nomes_env:\n        v = _os_cred.environ.get(n)\n        if v:\n"
        "            return str(v)\n    return \"\"",
        "    for n in nomes_env:\n        v = _os_cred.environ.get(n)\n        if v:\n"
        "            return str(v)\n    try:\n        import streamlit as st\n"
        "        v = st.secrets[\"trello\"][chave_secrets]\n        if v:\n"
        "            return str(v)\n    except Exception:\n        pass\n    return \"\"",
        ["python3", "placar_core.py"],
    ),
    (
        # Zero calado vira numero em relatorio. A recusa e a feature.
        "a analise do mes devolve zero em vez de recusar sem credencial",
        "analise_do_mes.py",
        '        raise RuntimeError(\n            "sem credencial do Trello: defina TRELLO_API_KEY, TRELLO_TOKEN e "\n            "TRELLO_BOARD_ID no ambiente (ou em .streamlit/secrets.toml)")',
        "        pass",
        ["python3", "analise_do_mes.py", "--autoteste"],
    ),
    (
        # Myrella 2.143 -> 2.163 -> 2.133 em minutos, sem ninguem tocar no
        # quadro. As bordas das fatias vinham de now() cru e mudavam a cada
        # leitura; a acao de conclusao perto de uma borda entrava e saia, e
        # com ela o cartao inteiro.
        "as bordas das fatias voltam a se mover a cada leitura",
        "placar_core.py",
        "    fim = (agora or datetime.now(timezone.utc)).replace(\n"
        "        minute=0, second=0, microsecond=0)",
        "    fim = agora or datetime.now(timezone.utc)",
        ["python3", "placar_core.py"],
    ),
    (
        # O aviso de janela truncada lia a chave do filtro; o caminho cru
        # publica em "cru". A tela recebia {} e ficava muda — e foi isso que
        # me fez concluir que nao havia truncamento.
        "o diagnostico volta a olhar so a chave do filtro",
        "placar_core.py",
        '    for chave in ("cru", FILTRO_MOVIMENTO):',
        "    for chave in (FILTRO_MOVIMENTO,):",
        ["python3", "placar_core.py"],
    ),
    (
        "a tela volta a ler o diagnostico por chave escrita a mao",
        "placar.py",
        "        _diag = _pc_cf.diagnostico_do_movimento()",
        "        _diag = dict(_pc_cf.DIAGNOSTICO_POR_FILTRO.get(\n"
        "            _pc_cf.FILTRO_MOVIMENTO) or {})",
        ["python3", "placar_core.py"],
    ),
    (
        # 250 acoes/dia por fatia era o teto real. O board passou disso e as
        # conclusoes antigas de cada fatia comecaram a ficar de fora.
        "o teto de paginas volta a ser dividido entre as fatias",
        "placar_core.py",
        "    por_fatia = PAGINAS_POR_FATIA",
        "    por_fatia = max(2, -(-max_paginas // len(fatias)) + 1)",
        ["python3", "placar_core.py"],
    ),
    (
        "o teto por fatia volta a ser pequeno",
        "placar_core.py",
        "PAGINAS_POR_FATIA = 30",
        "PAGINAS_POR_FATIA = 5",
        ["python3", "placar_core.py"],
    ),
    (
        # Dono, 29/09: "se um cartao for concluido e depois houver
        # modificacoes nele, comentario ou descricao, ele nao pode somar a
        # pontuacao novamente".
        "comentar um cartao antigo volta a mover a pontuacao de mes",
        "placar_core.py",
        '            if ac.get("type") != "updateCard":\n                continue\n'
        '            dados = ac.get("data", {}) or {}\n'
        '            if (dados.get("old") or {}).get("dueComplete") is False and \\\n'
        '               (dados.get("card") or {}).get("dueComplete") is True:',
        '            dados = ac.get("data", {}) or {}\n            if True:',
        ["python3", "placar_core.py"],
    ),
    (
        # Dono, 29/09: "se for concluido, desmarcado e concluido de novo, o
        # sistema conta 2 vezes?" Nao — vale a ULTIMA conclusao.
        "reabrir e reconcluir volta a valer a PRIMEIRA data",
        "placar_core.py",
        "                if cid not in fim or dt > fim[cid]:",
        "                if cid not in fim:",
        ["python3", "placar_core.py"],
    ),
    (
        # Dono, 29/09: "se faltam 660 pontos para reduzirem uma das
        # penalidades para baterem a meta MAXX, nao deve aparecer como 103%".
        "a porcentagem da meta volta a ignorar o que trava ela",
        "placar_core.py",
        "        alvo = max(alvo, saldo + float(pts_destrava))",
        "        alvo = float(meta_pts or 0)",
        ["python3", "placar_core.py"],
    ),
    (
        # "Menos de 4 penalidades - 100%" com "4 ocorrencia(s) / max 3".
        "a barra de penalidade volta a dizer 100% com o teto estourado",
        "placar_core.py",
        "    return min(pct_da_meta(saldo, 0, pts_destrava), 99.9)",
        "    return 100.0",
        ["python3", "placar_core.py"],
    ),
    (
        # Dono, 29/09: "se ha pontuacao necessaria para bater a meta maxx,
        # precisa subir de 10.800 para 11.800 a meta".
        "a meta exibida volta a ser a configurada, e nao a que destrava",
        "placar_core.py",
        "        return float(base or 0) + (pen_qtd - teto) * por_pen",
        "        return m",
        ["python3", "placar_core.py"],
    ),
    (
        "a TV volta a receber a meta configurada enquanto a tela mostra a efetiva",
        "placar.py",
        "        meta_maxx_pts=meta_maxx_alvo, faltam_maxx=faltam_maxx,",
        "        meta_maxx_pts=meta_maxx_pts, faltam_maxx=faltam_maxx,",
        ["python3", "placar_core.py"],
    ),
    (
        # Dono, 29/09: "o 100% dela tem que ser quando baterem o que precisam
        # para diminuir a penalidade".
        "o termometro MAXX volta a terminar na meta configurada",
        "placar.py",
        "        st.markdown(_vel_maxx(pct_maxx, meta_maxx_alvo, saldo_eq,",
        "        st.markdown(_vel_maxx(pct_maxx, meta_maxx_pts, saldo_eq,",
        ["python3", "placar_core.py"],
    ),
    (
        "a fatia SALVAR volta e conta o trecho extra duas vezes",
        "placar.py",
        "                              _sit_pen[\"bateu_maxx\"],\n"
        "                              pts_salvar=0),",
        "                              _sit_pen[\"bateu_maxx\"],\n"
        "                              pts_salvar=_pts_salvar_maxx),",
        ["python3", "placar_core.py"],
    ),
    (
        # Dono, 29/09: "temos um monte de demanda na coluna CHAT (PROBLEMAS
        # -30) que nao estao entrando na fila". No codigo a chave era
        # "CHAT (PROBLEMAS-30)", sem o espaco: um caractere, e a config
        # inteira da coluna sumia.
        "o nome da coluna volta a ser comparado caractere a caractere",
        "placar_core.py",
        '    return _re_col.sub(r"\\s+", "", t)',
        "    return str(nome or \"\")",
        ["python3", "placar_core.py"],
    ),
    (
        "a fila volta a comparar a coluna com `in` exato",
        "placar.py",
        "        if _pc_core.coluna_em(nl, COLUNAS_SKIP): continue",
        "        if nl in COLUNAS_SKIP: continue",
        ["python3", "placar_core.py"],
    ),
    (
        # Dono, 29/09: "ja trouxe esse problema aqui umas 10 vezes e voce nao
        # resolve". A variavel do Railway apontava para um modelo que a conta
        # nao tem; o Studio redescobria um bom, usava UMA vez, e na chamada
        # seguinte lia a variavel de novo e voltava ao 404.
        "a variavel do Railway volta a mandar mesmo provada errada",
        "imagem.py",
        "    cfg = _ch_mod.ler(\"OPENAI_MODELO_IMAGEM\")\n"
        "    if cfg and cfg not in _MODELO_INVALIDO:\n        return cfg\n"
        "    return _MODELO_DESCOBERTO[\"nome\"] or MODELO_IMAGEM_PADRAO",
        "    return (_ch_mod.ler(\"OPENAI_MODELO_IMAGEM\")\n"
        "            or _MODELO_DESCOBERTO[\"nome\"]\n"
        "            or MODELO_IMAGEM_PADRAO)",
        ["python3", "imagem.py"],
    ),
    (
        # Dois endpoints, dois `if modelo nao existe`. Marcar so num deixa o
        # nome invalido voltando pelo outro — a Forma 1 desta base.
        "so um dos dois caminhos marca o modelo invalido",
        "imagem.py",
        "            # O IRMAO DA MARCACAO ACIMA. Sao dois endpoints, e corrigir so um\n"
        "            # deles e a Forma 1 desta base: o nome invalido continuaria\n"
        "            # voltando pelo caminho que ficou sem marca.\n"
        "            marcar_modelo_invalido(_modelo)\n",
        "",
        ["python3", "imagem.py"],
    ),
    (
        # Recuperar calado esconde a configuracao errada para sempre.
        "o Studio se recupera calado e some com o aviso da variavel errada",
        "imagem.py",
        '    _av_modelo = aviso_de_modelo_invalido()\n    if _av_modelo:\n'
        '        st.warning("🖼️ " + _av_modelo)',
        "    pass",
        ["python3", "imagem.py"],
    ),
    (
        # Historico do Tigre, peca 7: a regra mandava 30% a 45% e a critica da
        # peca, mais abaixo no mesmo prompt, mandava "ocupando mais da metade
        # do quadro". O gerador obedeceu a ultima.
        "a critica da peca volta a mandar tamanho no prompt",
        "imagem.py",
        "        _probs = [sem_medida_de_quadro(p) for p in problemas]\n"
        "        _probs = [p for p in _probs if p.strip()]\n",
        "        _probs = problemas\n",
        ["python3", "imagem.py"],
    ),
    (
        "a instrucao da refacao volta a mandar tamanho",
        "imagem.py",
        "        _instr = sem_medida_de_quadro(instrucao).strip()",
        "        _instr = instrucao.strip()",
        ["python3", "imagem.py"],
    ),
    (
        # "mais da metade do quadro" nao tem `%`, e a limpeza saia cedo.
        "a limpeza volta a so conhecer tamanho escrito em porcentagem",
        "imagem.py",
        '_MEDIDA_DE_QUADRO = _re_quadro.compile(\n    r"[^,;.]*?(?:\\d{1,3}\\s?%|"\n    r"(?:mais\\s+da\\s+|menos\\s+da\\s+|cerca\\s+de\\s+|quase\\s+)?"\n    r"(?:metade|dois\\s+ter[c\\u00e7]os|um\\s+ter[c\\u00e7]o|tr[e\\u00ea]s\\s+quartos|"\n    r"um\\s+quarto)\\s+(?:d[oa]\\s+)?(?:quadro|imagem|enquadramento|frame))"\n    r"[^,;.]*", _re_quadro.I)',
        '_MEDIDA_DE_QUADRO = _re_quadro.compile(\n    r"[^,;.]*?\\d{1,3}\\s?%[^,;.]*", _re_quadro.I)',
        ["python3", "imagem.py"],
    ),
    (
        # 29/09: a tela dizia "Tigre · 10x21x5 · Resina" e as oito pecas
        # sairam com "pendulo balança / 14x13x11 / Plastico". Oito pecas
        # pagas do produto errado, sem aviso.
        "a tela para de conferir se o plano e deste produto",
        "imagem.py",
        "        _div_prod = divergencia_de_produto(cfg, nome_produto, dados_descricao)\n"
        '        if _div_prod:\n            st.error("🚫 " + _div_prod)\n',
        "",
        ["python3", "imagem.py"],
    ),
    (
        "a divergencia de produto para de olhar as medidas",
        "imagem.py",
        '    for campo, rotulo in (("medidas", "medidas"), ("peso", "peso"),\n'
        '                          ("material", "material")):',
        '    for campo, rotulo in ():',
        ["python3", "imagem.py"],
    ),
    (
        # Dono, 29/09: "eles mandaram a imagem no chat para ficar claro o que
        # ele pediu". O anexo parava no chat e o motor recebia so a frase.
        "o comando de ajuste volta a nao levar a referencia do pedido",
        "chat_assistente.py",
        '                {"num": foto_num, "instrucao": instrucao,\n'
        '                 "referencia": referencia_do_pedido(\n'
        '                     st.session_state.get("ms_chat_hist"))}',
        '                {"num": foto_num, "instrucao": instrucao}',
        ["python3", "chat_assistente.py"],
    ),
    (
        # Anexo de vinte mensagens atras, sobre outra peca, viraria referencia
        # do pedido de agora — e referencia errada e pior que nenhuma.
        "o anexo antigo volta a valer como referencia do pedido novo",
        "chat_assistente.py",
        "    falas = list(historico or [])[-FALAS_QUE_O_ANEXO_ALCANCA:]",
        "    falas = list(historico or [])",
        ["python3", "chat_assistente.py"],
    ),
    (
        # A referencia nao pode substituir as fotos do produto: elas sao a
        # trava de fidelidade, e sem elas o motor perde a cor e a forma.
        "a referencia do pedido toma o lugar das fotos do produto",
        "imagem.py",
        "            _refs_cmd = _ref_pedido + list(fotos_ref_aj or [])",
        "            _refs_cmd = _ref_pedido",
        ["python3", "imagem.py"],
    ),
    (
        # O oitavo verificador: "o sistema sabe e nao conta". Cinco campos
        # eram gravados no diagnostico e nunca mostrados — entre eles o
        # `input_fidelity`, que diz se a peca preservou o produto.
        "o diagnostico volta a esconder se o produto foi preservado",
        "imagem.py",
        '                _fid = _d.get("input_fidelity")',
        "                _fid = None",
        ["python3", "checar_comunicacao.py"],
    ),
    (
        "a medicao da peca volta a ser guardada so para o sistema",
        "imagem.py",
        '                if _d.get("medida"):\n'
        '                    st.warning(\n'
        '                        "📐 **O que a medição encontrou nesta peça:** "\n'
        '                        + str(_d["medida"]))\n',
        "",
        ["python3", "checar_comunicacao.py"],
    ),
    (
        # Duas vozes com numero sobre o mesmo assunto discordam — a questao
        # e so quando. Era o defeito da peca 7 do Tigre.
        "a folga da borda volta a ter duas vozes com numero",
        "imagem.py",
        "- CADA CARTÃO INTEIRO DENTRO DO QUADRO, respeitando a folga da borda definida\n"
        "  na REGRA DE ESPAÇO DESTA PEÇA: o primeiro começa abaixo do topo e o último\n"
        "  termina acima da base",
        "- CADA CARTÃO INTEIRO DENTRO DO QUADRO: o primeiro começa pelo menos 6% abaixo\n"
        "  do topo e o último termina pelo menos 6% acima da base",
        ["python3", "checar_comunicacao.py"],
    ),
    (
        # O chat prometia "vou gerar as 7 imagens que faltam", escrevia a
        # chave e ninguem lia. A colaboradora esperou sete pecas que nunca
        # vieram.
        "o comando de gerar faltantes volta a cair no vazio",
        "chat_assistente.py",
        "        preparar_geracao_dos_faltantes(faltam)",
        '        st.session_state["chat_gerar_faltantes"] = faltam',
        ["python3", "checar_comunicacao.py"],
    ),
    (
        "preparar a aba para de marcar os tipos que faltam",
        "chat_assistente.py",
        '    st.session_state["img_tipos_multi"] = list(faltam)\n'
        '    st.session_state["img_modo"] = "Selecionar"\n    return True',
        "    return True",
        ["python3", "chat_assistente.py"],
    ),
    (
        # "Temos um monte de demanda na coluna CHAT que nao esta entrando na
        # fila." Estavam — abaixo do corte de 4, sem ninguem dizer.
        "a fila volta a cortar em 4 sem dizer quantas ficaram de fora",
        "placar.py",
        '            _corte = _pc_core.aviso_de_corte(len(fila), FILA_VISIVEL, "demanda")\n'
        '            if _corte:\n                st.caption("📋 " + _corte)\n',
        "",
        ["python3", "placar_core.py"],
    ),
    (
        "o aviso de corte some do painel da TV, e so a tela avisa",
        "placar.py",
        '        _corte_tv = _pc_core.aviso_de_corte(len(fila), FILA_VISIVEL, "demanda")',
        "        _corte_tv = None",
        ["python3", "placar_core.py"],
    ),
    (
        "o aviso de corte deixa de dizer o total",
        "placar_core.py",
        '    return (f"Mostrando {mostrados} de {total} — {total - mostrados} "\n'
        '            f"{nome}(ns) abaixo do corte, por prioridade e data.")',
        '    return "Alguns itens ficaram de fora."',
        ["python3", "placar_core.py"],
    ),
    (
        # "O chat vai conseguir em 2 ou mais tentativas?" Sao 2 fixas, e o
        # sistema encerrava sem oferecer a terceira.
        "a recusa por produto alterado volta a tirar a opcao de insistir",
        "imagem.py",
        '        return (f"❌ Imagem {num}: não consegui em {_n_tent} tentativa(s) — "',
        '        return (f"❌ Imagem {num}: não consegui — "',
        ["python3", "imagem.py"],
    ),
    (
        # Tres escritores para a mesma pergunta e a Forma 5.
        "o produto da sessao volta a ser escrito por fora da porta",
        "imagem.py",
        "                    definir_produto_da_sessao(cfg[\"nome_produto\"],\n"
        "                                              codigo=cfg.get(\"codigo\", \"\"))",
        '                    st.session_state["img_nome_produto"] = cfg["nome_produto"]',
        ["python3", "imagem.py"],
    ),
    (
        # Nome vazio trocava o produto por um rotulo generico.
        "nome vazio volta a apagar o produto da sessao",
        "imagem.py",
        "    nome = str(nome or \"\").strip()\n    if nome:\n"
        '        st.session_state["img_nome_produto"] = nome',
        '    st.session_state["img_nome_produto"] = str(nome or "").strip()',
        ["python3", "imagem.py"],
    ),
    (
        "o ponto sem dono para de ser contado a parte",
        "conferencia_pontos.py",
        '            qtd["pontos_fora_do_quadro"] += pt',
        "            pass",
        ["python3", "conferencia_pontos.py"],
    ),
    (
        "uma varredura emudece e devolve lista vazia",
        "varredura_formas.py",
        "    fora = []\n    for nome, sites in sorted(chamadas.items()):",
        "    return []\n    fora = []\n    for nome, sites in sorted(chamadas.items()):",
        ["python3", "varredura_formas.py", "--autoteste"],
    ),
    (
        "uma categoria de comissao fica com uma tarifa so",
        "params_oficiais.py",
        "    'Outros': (0.10, 0.16),\n}",
        "    'Outros': (0.10,),\n}",
        ["python3", "params_oficiais.py"],
    ),
    (
        "a isencao de fuso volta a ser por ARQUIVO, e esconde o irmao",
        "checar_alcance.py",
        '    "auth.py:_salvar_token_sheets": "grava o `criado_em` que aquela comparação lê; trocar um lado só é que criaria o erro",\n',
        "",
        ["python3", "checar_alcance.py"],
    ),
    (
        "a direcao de arte volta a poder mandar tamanho",
        "imagem.py",
        "    d = {k: (sem_medida_de_quadro(v) if isinstance(v, str) else v)\n"
        "         for k, v in d.items()}\n",
        "",
        ["python3", "checar_prompts.py"],
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
    (
        # 30/09: a mutacao saiu "falhas: 2" e depois "falhas: 0" no comando
        # seguinte. Eu tinha DUAS instancias rodando — este arquivo escreve
        # nos arquivos do repositorio, e elas se sobrescreveram. Sem a
        # trava, `main` roda junto de outra e as duas mentem o resultado.
        "duas instancias mutando ao mesmo tempo",
        "checar_mutacao.py",
        '    if not _tomei:\n        print(f"FALHA  {_motivo}")\n'
        "        return 1\n",
        '    if not _tomei and False:\n        print(f"FALHA  {_motivo}")\n'
        "        return 1\n",
        ["python3", "checar_mutacao.py", "--autoteste"],
    ),
    (
        # 30/09: o destrave TROCAVA a meta em vez de disputar com ela. No
        # fim do mes acerta (o saldo ja passou da meta) — e foi so esse
        # caso que eu testei, tirado do print do dono. No meio do mes
        # inflava: 1.000 de 10.800 com 660 de destrave davam 60,2%.
        "o destrave troca a meta em vez de ser o maior dos dois",
        "placar_core.py",
        "        alvo = max(alvo, saldo + float(pts_destrava))\n",
        "        alvo = saldo + float(pts_destrava)\n",
        ["python3", "placar_core.py", "--autoteste"],
    ),
    (
        # 30/09: quando o UNICO defeito da peca era o enquadramento, o
        # corte da medida esvaziava a lista e o sistema pagava uma geracao
        # pedindo NADA — com o risco conhecido de voltar com o produto
        # trocado. A guarda de `instrucao` vazia rodava ANTES do corte.
        "geracao paga com o pedido de correcao em branco",
        "imagem.py",
        "        if not _probs and not _instr:\n",
        "        if False:\n",
        ["python3", "imagem.py", "--autoteste"],
    ),
    (
        # 30/09: o `conferir.py` matou este verificador em 900s e SIGKILL
        # nao roda `finally` — `imagem.py` ficou MUTADO no disco, e o passo
        # 2 seguinte mediu o arquivo mutado. Sem guardar o original ANTES
        # de escrever, nao ha como desfazer o que um tiro deixou.
        "um KILL no meio deixa o repositorio mutado, sem volta",
        "checar_mutacao.py",
        "        _guardar_original(arquivo, original)\n",
        "        pass\n",
        ["python3", "checar_mutacao.py", "--autoteste"],
    ),
    (
        # 30/09, 12:58: a conferencia inteira foi RECUSADA por uma trava de
        # 12:31 cujo processo ja tinha sido morto a tiro. `os.kill(pid, 0)`
        # respondia "vivo" porque era um ZUMBI ainda nao recolhido — e a
        # mensagem mandava "esperar a outra terminar". Nao havia outra.
        "zumbi e pid reciclado voltam a segurar a trava para sempre",
        "checar_mutacao.py",
        '    if os.path.isdir("/proc/self"):\n',
        "    if False:\n",
        ["python3", "checar_mutacao.py", "--autoteste"],
    ),
    (
        # 30/09: a copia de socorro era salva como `.py` DENTRO do
        # repositorio. O `compileall` compilou, deixou um `__pycache__` la
        # dentro, e `checar_tela`, `auditar` e a pre-conferencia deste
        # arquivo reprovaram lendo o codigo duplicado. O socorro passou a
        # causar o estrago que existe para desfazer.
        "a copia de socorro volta a ter cara de codigo",
        "checar_mutacao.py",
        '    return arquivo.replace("/", "__") + ".original"\n',
        '    return arquivo.replace("/", "__")\n',
        ["python3", "checar_mutacao.py", "--autoteste"],
    ),
    (
        # 30/09: a copia usada na conferencia do `main` se chamava
        # `checar_mutacao.py` — o mesmo nome que um dos comandos da
        # pre-conferencia. Ela chamava a si mesma, e com a trava quebrada
        # (que e o que outra mutacao daqui faz DE PROPOSITO) a recursao
        # nao tinha fundo: 1.810 processos, 14 de 16 GB, e CINCO
        # verificadores sem defeito nenhum reprovando por falta de
        # memoria — morrer calado vira "FALHA" sem explicacao.
        "a copia da conferencia volta a ter o nome que ela mesma chama",
        "checar_mutacao.py",
        '        copia = os.path.join(dir_, "sob_teste.py")\n',
        '        copia = os.path.join(dir_, "checar_mutacao.py")\n',
        ["python3", "checar_mutacao.py", "--autoteste"],
    ),
    # ── AS QUATRO DO AJUSTE FINO ─────────────────────────────────────────
    #
    # Dono, 30/09: "se nao consegue nao e por recusa do GEMINI e sim por ele
    # estar fazendo algo errado (...) na comunicacao ou na analise do que
    # precisa fazer". O pedido era "trocar o texto: diametro 25 cm e peso
    # 476 g", e o mesmo prompt levava TRES proibicoes absolutas contra ele,
    # mais uma quarta mandando desistir. O modelo obedeceu.
    (
        "o prompt do ajuste volta a proibir mexer em texto",
        "imagem.py",
        "3. Preserve os textos que já existem na imagem — EXCETO o texto que a\n",
        "3. Preserve exatamente todos os textos que já existem na imagem\n"
        "   (não adicione nem remova nenhum texto)\n",
        ["python3", "checar_prompts.py"],
    ),
    (
        "o pedido do colaborador perde a prioridade declarada",
        "imagem.py",
        "A MODIFICAÇÃO SOLICITADA acima é o objetivo, e ela tem prioridade sobre TODAS\n",
        "A MODIFICAÇÃO SOLICITADA acima é o objetivo, e ela vale junto com\n",
        ["python3", "checar_prompts.py"],
    ),
    (
        # As duas clausulas so-de-criacao voltando ao ajuste: "ignore todo
        # texto visivel" e "nao escreva medida que nao veio do cadastro".
        "o ajuste volta a receber as regras que so valem na criacao",
        "imagem.py",
        "{INSTRUCAO_FIDELIDADE_NUCLEO}\n",
        "{INSTRUCAO_FIDELIDADE}\n",
        ["python3", "checar_prompts.py"],
    ),
    (
        "o prompt do ajuste volta a mandar desistir",
        "imagem.py",
        "- Se a modificação pedida for SOBRE o produto (tamanho na cena, posição,\n",
        "- Se a modificação pedida só puder ser feita alterando o produto, NÃO a faça:\n"
        "  devolva a imagem como está.\n",
        ["python3", "checar_prompts.py"],
    ),
    # ── A VARREDURA DA CADEIA STUDIO -> GEMINI (30/09) ───────────────────
    (
        # O prompt escreve "COR REAL DO PRODUTO:"; a releitura procurava
        # "Cor:" e NUNCA casava, nos nove tipos. A cor cadastrada jamais
        # chegou a analise de visao — e e ela quem descreve o produto.
        "a cor cadastrada volta a nao chegar na analise de visao",
        "imagem.py",
        '    _m_cor = _re.search(r"^COR REAL DO PRODUTO:\\s*(.+?)$", prompt_texto,\n',
        '    _m_cor = _re.search(r"Cor:\\s*(.+?)(?:\\n|$)", prompt_texto,\n',
        ["python3", "checar_prompts.py"],
    ),
    (
        # `PRODUTO:` sem ancora casava NO MEIO de outra frase. No prompt do
        # ajuste fino o nome do produto virava "JAMAIS adicione base,
        # pedestal, suporte, embalagem".
        "o nome do produto volta a ser lido do meio de outra frase",
        "imagem.py",
        '    _m = _re.search(r"^PRODUTO:\\s*(.+?)$", prompt_texto, _re.MULTILINE)\n',
        '    _m = _re.search(r"PRODUTO:\\s*(.+?)(?:\\n|$)", prompt_texto)\n',
        ["python3", "checar_prompts.py"],
    ),
    (
        # O material tem campo proprio na analise de visao e nunca era
        # extraido. A guarda so pegou isso quando passou a olhar o que a
        # analise RECEBE, e nao so se a expressao casa.
        "o material volta a nao chegar na analise de visao",
        "imagem.py",
        '    if _m_mat:\n        dados_descricao["material"] = _m_mat.group(1).strip()\n',
        "    if _m_mat:\n        pass\n",
        ["python3", "checar_prompts.py"],
    ),
    (
        # "THE BORDER MARGIN OVERRIDES the rule above" — a intencao era
        # "cartoes a 6% da borda", e o modelo lia "a margem vence o produto":
        # margem desenhada e produto encolhido.
        "a folga da borda volta a mandar sobre o produto",
        "imagem.py",
        '        + _SEM_MOLDURA_PT)',
        '        )',
        ["python3", "checar_prompts.py"],
    ),
    (
        # O aviso de que a peca foi feita pelo motor reserva morava num
        # `st.warning` DENTRO da thread: nunca apareceu para ninguem.
        "o aviso do motor reserva volta para dentro da thread",
        "imagem.py",
        "        if erro_primario and diagnostico is not None:\n",
        "        if erro_primario:\n"
        '            st.warning(f"aviso {erro_primario}")\n'
        "        if erro_primario and diagnostico is not None:\n",
        ["python3", "checar_alcance.py"],
    ),
    (
        # Tipo 5 com cadastro vazio: manda infografico de cotas E proibe
        # escrever cota, sem dizer que a medida nao existe.
        "o tipo 5 sem cadastro volta a pedir cota que ele mesmo proibe",
        "imagem.py",
        '            "SEM DADOS TÉCNICOS CADASTRADOS: este produto não tem medidas, "\n',
        '            "" "" "" "" ""  # bloco removido\n',
        ["python3", "checar_prompts.py"],
    ),
    (
        # O ponteiro do tamanho apontava para um bloco que os tipos 8 e
        # Personalizado NAO tem: o modelo encolhia o produto por precaucao.
        "o ponteiro do tamanho volta a apontar para o vazio",
        "imagem.py",
        "  peça, e é de lá que ela sai — não estime outra. Se esta peça NÃO trouxer\n"
        "  essa medida, é porque ela não tem número fixo: o produto aparece na escala\n"
        "  real da cena. Nesse caso NÃO invente uma porcentagem e NÃO encolha o\n"
        "  produto por precaução.\n",
        "  peça, e é de lá que ela sai — não estime outra.\n",
        ["python3", "checar_prompts.py"],
    ),
    (
        # Toda tentativa de ajuste pagava uma leitura de visao descartada na
        # linha seguinte — 2 por pedido, porque sao 2 tentativas.
        "o ajuste fino volta a pagar leitura de visao que ele descarta",
        "imagem.py",
        '    _eh_ajuste_fino = "MODO AJUSTE FINO" in prompt_texto[:400]\n',
        "    _eh_ajuste_fino = False\n",
        ["python3", "checar_prompts.py"],
    ),
    (
        # Dono, 30/09: "o Gemini devolve o que o sistema pede, ue". Certo —
        # e o pedido tem DUAS metades. O texto tinha 65 regras; os
        # PARAMETROS nao tinham nenhuma. Sem `input_fidelity` o produto e
        # redesenhado, e os oito verificadores seguiam verdes.
        "o motor volta a ser chamado sem input_fidelity",
        "imagem.py",
        '                        "input_fidelity": "high",\n',
        "",
        ["python3", "checar_comunicacao.py"],
    ),
    (
        # O caminho da OpenAI SEM fotos entregava a peca sem gravar o motor:
        # a tela mostrava "Motor —" justamente no caminho onde o produto tem
        # mais chance de sair errado, porque o modelo nao ve as fotos.
        "um caminho volta a entregar imagem sem dizer por onde ela veio",
        "imagem.py",
        '            diagnostico["motor"] = f"{_modelo} (images.generate — SEM fotos)"\n',
        "",
        ["python3", "checar_comunicacao.py"],
    ),
    (
        # Sem a chave da OpenAI, o prompt mandava recriar o produto A PARTIR
        # DO TEXTO — enquanto as fotos iam ao Gemini junto. O modelo nunca
        # era avisado de que elas sao a referencia.
        "o prompt volta a mandar recriar o produto de uma descricao",
        "imagem.py",
        "    _tem_fotos = bool(imagens_referencia)\n",
        "    _tem_fotos = bool(imagens_referencia) and bool(_get_openai_api_key())\n",
        ["python3", "checar_prompts.py"],
    ),
    (
        # 30/09: achei treze defeitos na cadeia, corrigi onze e deixei dois
        # — entre eles o `_tem_fotos`, causa de "produto nada a ver com o
        # original", aberto por horas enquanto eu dizia "APROVADO". Os
        # verificadores guardam o codigo; nada guardava a minha lista.
        "achado aberto volta a poder ficar sem motivo escrito",
        "ACHADOS_ABERTOS.md",
        "POR QUE AINDA NÃO: hoje só o tipo 5 é conferido com o cadastro vazio",
        "POR QUE AINDA NAO ESCRITO: ",
        ["python3", "checar_alcance.py"],
    ),
    (
        # 30/09: "Imagem 2 e imagem 5 com texto cortando". `enquadrar.janela`
        # fazia recorte CENTRAL sempre que a caixa do assunto cobria o quadro,
        # com o comentario "nao ha painel de texto para decepar". Numa peca de
        # marketing o cenario vai ate as bordas, a caixa cobre 100%, e o corte
        # come a lateral onde o texto mora.
        "o enquadramento volta a decepar o texto da peca",
        "imagem.py",
        "                lado_final=1200, tem_texto=not _is_clean_photo)\n",
        "                lado_final=1200)\n",
        ["python3", "imagem.py", "--autoteste"],
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



# ─────────────────────────────────────────────────────────────────────────
# A TRAVA: DUAS INSTANCIAS DESTE ARQUIVO SE DESTROEM
#
# Dono, 30/09: a mutacao saiu "falhas: 2" e, no comando seguinte, "falhas:
# 0". Nao-determinismo num verificador e pior que um defeito, porque ensina
# a rodar de novo ate dar verde.
#
# A causa nao era o codigo: eu rodei DUAS instancias ao mesmo tempo, uma em
# background e outra a frente. Este arquivo ESCREVE nos arquivos do
# repositorio — a instancia A muta `imagem.py`, a instancia B le `imagem.py`
# mutado como se fosse o original, e depois "restaura" o defeito da A por
# cima. As duas terminam dizendo que restauraram, e as duas estao erradas.
#
# A restauracao em `finally` ja existia e e correta; ela so nao protege de
# outra instancia. A regra de ouro do topo deste arquivo ("o repositorio
# nunca fica mutado") nao se sustenta sem exclusao.
#
# Ela RECUSA, nao espera: conferencia que roda junto de outra nao mediu
# nada, e ficar na fila esconderia isso atras de uma demora.
# ─────────────────────────────────────────────────────────────────────────
def _caminho_da_trava():
    """Onde fica a trava. O env var existe para o auto-teste poder usar a
    trava DE VERDADE num diretorio temporario, em vez de um duplo."""
    return (os.environ.get("CHECAR_MUTACAO_TRAVA")
            or os.path.join(RAIZ, ".checar_mutacao.trava"))


# ─────────────────────────────────────────────────────────────────────────
# O SOCORRO: UM KILL NAO RODA `finally`
#
# 30/09: o `conferir.py` mata cada verificador em 900s. Com 69 mutacoes
# este arquivo passou desse tempo, levou SIGKILL no meio — e SIGKILL NAO
# executa o `finally`. O `imagem.py` ficou no disco COM O DEFEITO DENTRO,
# e o passo 2 seguinte mediu o arquivo mutado e acusou quatro falhas que
# nao existiam. Se eu tivesse commitado ali, o defeito injetado subiria
# para producao.
#
# A trava resolve duas instancias; ela nao resolve uma instancia morta a
# tiro. A regra de ouro do topo deste arquivo — "o repositorio nunca fica
# mutado" — so se sustenta se a restauracao sobreviver ao processo.
#
# Entao o original vai para o DISCO antes de mutar, e a proxima execucao
# devolve o que ficou para tras, EM VOZ ALTA. Serve para SIGKILL, Ctrl-C,
# falta de memoria e queda de energia igual.
# ─────────────────────────────────────────────────────────────────────────
def _caminho_do_socorro():
    return (os.environ.get("CHECAR_MUTACAO_SOCORRO")
            or os.path.join(RAIZ, ".checar_mutacao.socorro"))


def _guardado_como(arquivo):
    """O nome da copia: caminho achatado, e SEM extensao de codigo."""
    return arquivo.replace("/", "__") + ".original"


def _de_volta_para(nome):
    """O caminho original, a partir do nome da copia."""
    return nome[:-len(".original")].replace("__", "/")


def _guardar_original(arquivo, texto):
    pasta = _caminho_do_socorro()
    os.makedirs(pasta, exist_ok=True)
    # `.original`, E NAO `.py`: a copia de socorro fica DENTRO do
    # repositorio, e com cara de codigo ela vira codigo. Em 30/09 o
    # `compileall` compilou a copia (criando `__pycache__` la dentro),
    # `checar_tela` e `auditar` leram o arquivo duplicado e reprovaram — e
    # a pre-conferencia do proprio verificador caiu junto. O socorro
    # passou a causar o estrago que ele existe para desfazer.
    with open(os.path.join(pasta, _guardado_como(arquivo)), "w",
              encoding="utf-8") as fh:
        fh.write(texto)


def _esquecer_original(arquivo):
    pasta = _caminho_do_socorro()
    try:
        os.unlink(os.path.join(pasta, _guardado_como(arquivo)))
    except OSError:
        pass
    try:
        os.rmdir(pasta)
    except OSError:
        pass


def socorrer(raiz=None, pasta=None):
    """Devolve os arquivos que uma execucao morta deixou mutados.

    Lista dos nomes restaurados — vazia quando nao havia nada. Ela nao
    pergunta se o arquivo "parece" mutado: compara com o original guardado
    e devolve o original quando diferem. Comparar e mais barato que
    reescrever, e reescrever igual ainda assim nao faria mal.
    """
    raiz = raiz or RAIZ
    pasta = pasta or _caminho_do_socorro()
    if not os.path.isdir(pasta):
        return []
    voltaram = []
    for nome in sorted(os.listdir(pasta)):
        guardado_em = os.path.join(pasta, nome)
        # SO COPIA. Qualquer outra coisa ali (um `__pycache__`, por
        # exemplo) nao e original de ninguem, e tratar como se fosse
        # deixaria a pasta viva para sempre — `os.rmdir` nao apaga pasta
        # com coisa dentro, e o socorro ficaria pendurado.
        if not nome.endswith(".original") or not os.path.isfile(guardado_em):
            continue
        alvo = os.path.join(raiz, _de_volta_para(nome))
        try:
            with open(guardado_em, encoding="utf-8") as fh:
                original = fh.read()
        except OSError:
            continue
        atual = None
        try:
            with open(alvo, encoding="utf-8") as fh:
                atual = fh.read()
        except OSError:
            pass
        if atual != original:
            with open(alvo, "w", encoding="utf-8") as fh:
                fh.write(original)
            voltaram.append(_de_volta_para(nome))
        try:
            os.unlink(guardado_em)
        except OSError:
            pass
    # A PASTA SOME INTEIRA, inclusive o `__pycache__` que o `compileall`
    # deixou la dentro enquanto a copia ainda tinha cara de codigo.
    import shutil as _sh_soc
    _sh_soc.rmtree(pasta, ignore_errors=True)
    return voltaram


def _nascimento(pid):
    """A hora em que ESTE processo nasceu. "" quando ele nao esta rodando.

    SO O PID NAO BASTA, E ISSO CUSTOU UMA CONFERENCIA EM 30/09.
    Uma execucao morta a tiro deixou a trava para tras. Na execucao
    seguinte `os.kill(pid, 0)` respondeu "vivo" — o numero ja pertencia a
    outra coisa — e a conferencia inteira foi recusada, com a mensagem
    mandando "esperar a outra terminar". Nao havia outra.

    O par (pid, nascimento) e unico: pid reciclado nasce noutra hora, e a
    trava dele deixa de bater. Zumbi conta como MORTO — um filho que ainda
    nao foi recolhido responde a sinal 0 como se estivesse vivo, e foi
    exatamente assim que a trava de 12:31 bloqueou a das 12:58.

    Fora do Linux nao ha `/proc`: devolve "" e a decisao volta a ser so
    pelo pid, que e o que se tinha antes.
    """
    try:
        with open(f"/proc/{int(pid)}/stat", encoding="utf-8") as fh:
            # o nome do programa vem entre parenteses e pode ter espaco
            campos = fh.read().rsplit(") ", 1)[1].split()
    except (OSError, ValueError, IndexError):
        return ""
    if not campos or campos[0] == "Z":
        return ""
    return campos[19] if len(campos) > 19 else ""


def _dono_vivo(pid, nascimento=""):
    """O dono da trava ainda e o mesmo processo?

    Com `/proc`, a resposta e exata. Sem ele, cai no sinal 0 — e ai
    PermissionError conta como VIVO: o processo esta la, de outro usuario.
    """
    # ONDE HA `/proc`, ELE E A AUTORIDADE — inclusive quando diz "nao esta
    # rodando". A primeira versao caia no sinal 0 sempre que `_nascimento`
    # voltava vazio, e vazio era justamente a resposta para o ZUMBI: o
    # sinal 0 dizia "vivo" e o defeito voltava inteiro.
    if os.path.isdir("/proc/self"):
        agora = _nascimento(pid)
        return bool(agora) and (not nascimento or agora == nascimento)
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, ValueError):
        return True
    return True


def tomar_a_trava(caminho=None, pid=None, vivo=_dono_vivo):
    """(True, "") se tomou a trava; (False, motivo) se outra instancia roda.

    Trava de dono MORTO e tomada, nao respeitada: um Ctrl-C no meio deixa o
    arquivo para tras, e uma trava eterna quebraria toda conferencia
    seguinte — que e exatamente o tipo de defeito silencioso que este
    arquivo existe para nao deixar passar.
    """
    caminho = caminho or _caminho_da_trava()
    pid = os.getpid() if pid is None else pid
    for _ in range(2):
        try:
            fd = os.open(caminho, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            try:
                with open(caminho, encoding="utf-8") as fh:
                    _lido = (fh.read() or "").split()
                dono = int(_lido[0]) if _lido else 0
                nasceu = _lido[1] if len(_lido) > 1 else ""
            except (OSError, ValueError, IndexError):
                dono, nasceu = 0, ""
            if dono and dono != pid and vivo(dono, nasceu):
                # A SAIDA TEM DE ESTAR NA MENSAGEM.
                #
                # Um SIGKILL no meio deixa o arquivo para tras, e se o
                # sistema reciclar aquele pid para qualquer processo sem
                # relacao nenhuma, `vivo` diz "sim" e esta conferencia
                # recusa PARA SEMPRE. "Espere a outra terminar" seria
                # conselho errado e beco sem saida: ninguem esta rodando.
                # Entao a recusa diz o caminho e a idade, e quem le decide.
                try:
                    idade = int(time.time() - os.path.getmtime(caminho))
                except OSError:
                    idade = -1
                return False, (
                    f"outra conferencia de mutacao ja esta rodando "
                    f"(processo {dono}). Este arquivo ESCREVE nos arquivos "
                    "do repositorio: duas instancias se sobrescrevem e as "
                    "duas mentem sobre o resultado. Espere a outra "
                    f"terminar. Se NINGUEM estiver rodando, a trava ficou "
                    f"de um processo morto cujo pid foi reciclado: apague "
                    f"{caminho} (feita ha {idade}s)."
                )
            try:
                os.unlink(caminho)
            except FileNotFoundError:
                pass
            continue
        with os.fdopen(fd, "w") as fh:
            fh.write(f"{pid} {_nascimento(pid)}".strip())
        return True, ""
    return False, "nao consegui tomar a trava da mutacao"


def soltar_a_trava(caminho=None, pid=None):
    """Solta a trava, e SO se ela for minha. True se soltou.

    Apagar trava alheia seria o mesmo defeito por outro caminho: eu saio, a
    outra instancia fica sem protecao, e uma terceira entra por cima dela.
    """
    caminho = caminho or _caminho_da_trava()
    pid = os.getpid() if pid is None else pid
    try:
        with open(caminho, encoding="utf-8") as fh:
            _l = (fh.read() or "").split()
            if not _l or int(_l[0]) != pid:
                return False
    except (OSError, ValueError):
        return False
    try:
        os.unlink(caminho)
    except OSError:
        return False
    return True


def main():
    falhas = 0

    # A TRAVA PRIMEIRO, ANTES DE QUALQUER LEITURA.
    #
    # Nao adianta travar so na hora de escrever: a instancia que LE o
    # arquivo ja mutado pela outra guarda o "original" errado, e restaura o
    # defeito por cima no fim.
    _tomei, _motivo = tomar_a_trava()
    if not _tomei:
        print(f"FALHA  {_motivo}")
        return 1
    try:
        # O SOCORRO ANTES DE TUDO, E EM VOZ ALTA.
        #
        # Se a execucao anterior morreu a tiro, o repositorio esta mutado
        # AGORA. Restaurar calado seria pior: quem viu a conferencia
        # quebrar precisa saber que o arquivo dele foi mexido e voltou.
        _voltaram = socorrer()
        if _voltaram:
            print("AVISO  a execucao anterior foi morta no meio e deixou "
                  f"{', '.join(_voltaram)} MUTADO(S). Devolvi ao original "
                  "antes de comecar.")
        return _conferir_as_mutacoes(falhas)
    finally:
        soltar_a_trava()


def _conferir_as_mutacoes(falhas):

    # ANTES DE MUTAR, O VERDE TEM DE SER VERDE.
    #
    # A 16a entrada — "uma varredura emudece" — passou verde por ACIDENTE: o
    # `varredura_formas.py --autoteste` estava saindo com codigo 1 SEMPRE,
    # por uma inversao de sinal, e entao "reprovou com o defeito de volta"
    # era verdade sem medir nada.
    #
    # Mutacao so mede alguma coisa se o comando passar ANTES de mutar. Sem
    # esta conferencia, toda entrada deste arquivo pode estar verde porque o
    # verificador dela ja estava vermelho.
    _comandos = {tuple(m[4]) for m in MUTACOES}
    for cmd in sorted(_comandos):
        codigo, saida = _roda(list(cmd))
        if _reprovou(codigo, saida):
            print(f"FALHA  `{' '.join(cmd)}` ja reprova SEM mutacao nenhuma "
                  "— toda entrada que depende dele esta verde por acidente")
            falhas += 1

    for nome, arquivo, certo, errado, cmd in MUTACOES:
        caminho = os.path.join(RAIZ, arquivo)
        with open(caminho, encoding="utf-8") as fh:
            original = fh.read()
        # O ORIGINAL VAI PARA O DISCO ANTES DE QUALQUER ESCRITA.
        _guardar_original(arquivo, original)

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
            # E CONFERE QUE RESTAUROU.
            #
            # Escrever de volta e uma coisa; ter voltado e outra. Disco cheio,
            # permissao, escrita parcial — e o repositorio fica mutado EM
            # SILENCIO, com o defeito de volta e todo mundo achando que rodou
            # uma conferencia. Seria o pior defeito possivel num arquivo cujo
            # trabalho e justamente nao deixar defeito passar calado.
            with open(caminho, encoding="utf-8") as fh:
                _voltou = fh.read() == original
            if _voltou:
                # So agora o socorro pode ser esquecido: o disco confirmou.
                _esquecer_original(arquivo)
            else:
                print(f"FALHA  '{nome}': NAO consegui restaurar "
                      f"{arquivo} — o repositorio esta MUTADO agora. "
                      f"O original esta guardado em {_caminho_do_socorro()} "
                      "e a proxima execucao devolve ele sozinha.")
                falhas += 1

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


def _autoteste():
    """A trava recusa a segunda instancia? E o `main` OBEDECE a recusa?

    A ultima asserção e a que importa: as tres primeiras medem a funcao
    isolada — foi assim que a guarda da thread nasceu fraca, exercitando a
    funcao que eu tinha acabado de escrever em vez do caminho inteiro.

    O `main` de verdade roda num diretorio TEMPORARIO, com uma copia deste
    arquivo. Assim, se a trava for desobedecida, ele muta arquivos que nao
    existem ali e nao encosta no repositorio — verificador que pode deixar
    o repositorio mutado e pior do que nenhum, e isso vale para o
    auto-teste dele tambem.
    """
    import shutil
    import tempfile

    # ── PROFUNDIDADE 1, E NUNCA MAIS FUNDO ────────────────────────────
    #
    # Esta conferencia COPIA este arquivo para uma pasta temporaria e roda
    # o `main` de la — e uma das mutacoes permanentes QUEBRA a trava de
    # proposito. Com a trava quebrada aquele `main` nao recusa: ele vai
    # para a pre-conferencia, que roda `--autoteste`, que copia o arquivo
    # de novo e roda outro `main`.
    #
    # 30/09: foi exatamente isso. Dezenas de processos, 14 de 16 GB de
    # memoria ocupados, e a conferencia inteira passou a reprovar
    # verificadores que passavam sozinhos — `checar_alcance`,
    # `checar_prompts`, `checar_tela`, `chat_assistente`, `lancamentos`.
    # Nenhum deles tinha defeito: eles morriam por falta de memoria, e
    # morrer calado vira "FALHA" sem uma linha de explicacao.
    #
    # Todo processo que esta conferencia abre leva a marca. Quem nasce com
    # ela nao abre mais ninguem — e diz isso, em vez de fingir que mediu.
    if os.environ.get("CHECAR_MUTACAO_NIVEL"):
        print("ok    (aninhado: nao abro processo, para nao virar bomba)")
        return 0
    _AMB_FILHO = dict(os.environ, CHECAR_MUTACAO_NIVEL="1")

    falhas = []

    def ok(msg, cond):
        # (MENSAGEM, CONDICAO) — a ordem do resto da base.
        #
        # Esta funcao ja nasceu com a ordem INVERTIDA aqui dentro, e a
        # secao nova foi escrita na ordem dos outros arquivos: a condicao
        # virou uma string nao-vazia, sempre verdadeira, e a guarda passava
        # SEMPRE. Quem pegou foi a mutacao — a guarda ficou verde com o
        # defeito de volta, que e a definicao de guarda que nao e guarda.
        #
        # Duas ordens para a mesma pergunta e a Forma 5. Agora e uma so, e
        # a troca ESTOURA em vez de mentir.
        if not isinstance(msg, str):
            raise TypeError(
                f"ok(mensagem, condicao) — veio {type(msg).__name__} na "
                "mensagem. A ordem trocada faz a guarda passar sempre.")
        if isinstance(cond, str):
            raise TypeError(
                "ok(mensagem, condicao) — veio texto na condicao. A ordem "
                "trocada faz a guarda passar sempre.")
        if not cond:
            falhas.append(msg)

    dir_ = tempfile.mkdtemp(prefix="trava_")
    dorminhoco = None
    try:
        alvo = os.path.join(dir_, "t1")

        # 1. tomo a trava; outro pid VIVO e recusado
        tomou, _ = tomar_a_trava(alvo, pid=111, vivo=lambda *_a: True)
        ok("nao consegui tomar a trava livre", tomou)
        tomou2, motivo = tomar_a_trava(alvo, pid=222, vivo=lambda *_a: True)
        ok("a trava deixou uma SEGUNDA instancia entrar", not tomou2)
        ok(f"a recusa nao diz quem e o dono: {motivo!r}", "111" in motivo)
        # E A SAIDA: trava de pid reciclado recusaria para sempre, e quem
        # le precisa saber QUAL arquivo apagar. Recusa sem saida e beco.
        ok(f"a recusa nao diz onde esta a trava: {motivo!r}",
           alvo in motivo)

        # 2. trava de dono MORTO e tomada, nao respeitada para sempre
        tomou3, _ = tomar_a_trava(alvo, pid=333, vivo=lambda *_a: False)
        ok("trava de processo morto travou a conferencia seguinte", tomou3)

        # 3. so o dono solta
        ok("um estranho apagou a trava de outro processo",
           not soltar_a_trava(alvo, pid=444))
        ok("o dono nao conseguiu soltar", soltar_a_trava(alvo, pid=333))
        ok("soltou e o arquivo ficou no disco", not os.path.exists(alvo))

        # 4. A CADEIA: o `main` de verdade recusa e NAO muta nada.
        # A COPIA TEM OUTRO NOME, E ISSO NAO E DETALHE.
        #
        # Chamada `checar_mutacao.py`, ela e o alvo de um dos comandos da
        # pre-conferencia (`python3 checar_mutacao.py --autoteste`) — entao
        # ela chama a si mesma. Com a trava quebrada, que e o que UMA DAS
        # MUTACOES PERMANENTES FAZ DE PROPOSITO, a recursao nao tem fundo.
        #
        # 30/09: 1.810 processos, 14 de 16 GB de memoria, e cinco
        # verificadores SEM DEFEITO NENHUM passaram a reprovar — eles
        # morriam por falta de memoria, e morrer calado vira "FALHA" sem
        # uma linha de explicacao. Levei tres rodadas para achar, porque o
        # sintoma aparecia longe da causa.
        #
        # Com outro nome, o comando da pre-conferencia nao encontra nada
        # nesta pasta e falha na hora. A marca de profundidade continua
        # valendo; esta aqui e a que nao depende de variavel de ambiente.
        copia = os.path.join(dir_, "sob_teste.py")
        shutil.copy(os.path.abspath(__file__), copia)
        # E A PROVA DISSO, que custa nada e nao depende de ambiente: o
        # nome da copia nao pode ser alvo de nenhum comando que o `main`
        # roda. Se voltar a ser, ela chama a si mesma.
        _alvos = {os.path.basename(_c[1]) for _, _, _, _, _c in MUTACOES
                  if len(_c) > 1}
        ok(f"a copia se chama {os.path.basename(copia)}, que e alvo de um "
           "comando da pre-conferencia — ela vai chamar a si mesma",
           os.path.basename(copia) not in _alvos)
        trava_real = os.path.join(dir_, "t2")
        dorminhoco = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(120)"],
            env=_AMB_FILHO)
        with open(trava_real, "w", encoding="utf-8") as fh:
            fh.write(str(dorminhoco.pid))

        amb = dict(_AMB_FILHO, CHECAR_MUTACAO_TRAVA=trava_real)
        try:
            p = subprocess.run([sys.executable, "sob_teste.py"],
                               cwd=dir_, capture_output=True, text=True,
                               timeout=180, env=amb)
            saida = (p.stdout or "") + (p.stderr or "")
            codigo = p.returncode
        except subprocess.TimeoutExpired:
            saida, codigo = "", 0
            falhas.append("o main IGNOROU a trava e foi rodar a suite "
                          "inteira com outra instancia viva")

        ok(f"o main nao reprovou com a trava tomada (codigo {codigo})",
           codigo == 1)
        ok(f"o main nao disse POR QUE parou: {saida[:200]!r}",
           "outra conferencia de mutacao" in saida)
        ok("o main passou da trava e comecou a conferir os verificadores",
           "SEM mutacao nenhuma" not in saida)
    finally:
        if dorminhoco is not None:
            dorminhoco.kill()
            dorminhoco.wait()
        shutil.rmtree(dir_, ignore_errors=True)

    # ── 4-bis. PID RECICLADO E ZUMBI NAO SEGURAM A TRAVA ──────────────
    #
    # 30/09, o caso real: a execucao das 12:31 foi morta a tiro e deixou a
    # trava. As 12:58 `os.kill(pid, 0)` respondeu "vivo" — o processo era
    # um ZUMBI ainda nao recolhido — e a conferencia inteira foi recusada,
    # com a mensagem mandando "esperar a outra terminar". Nao havia outra.
    #
    # Aqui um processo de verdade vira zumbi de verdade (morto, sem o pai
    # recolher), e o que se mede e a decisao da trava sobre ele.
    dir3 = tempfile.mkdtemp(prefix="zumbi_")
    z = None
    try:
        t3 = os.path.join(dir3, "t3")
        ok("o nascimento do proprio processo tem de ser legivel",
           bool(_nascimento(os.getpid())))
        ok("pid que nunca existiu nao segura a trava",
           not _dono_vivo(999999, "1"))
        ok("o MESMO processo, com o mesmo nascimento, segura",
           _dono_vivo(os.getpid(), _nascimento(os.getpid())))
        ok("pid RECICLADO (mesmo numero, outro nascimento) NAO segura",
           not _dono_vivo(os.getpid(), "1"))

        # zumbi de verdade: morre, e o pai nao chama wait()
        z = subprocess.Popen([sys.executable, "-c", "pass"], env=_AMB_FILHO)
        _t0 = time.time()
        while time.time() - _t0 < 10 and _nascimento(z.pid):
            time.sleep(0.05)
        ok("processo ZUMBI conta como morto, e nao como dono da trava",
           not _dono_vivo(z.pid))

        # e a trava dele e tomada, nao respeitada para sempre
        with open(t3, "w", encoding="utf-8") as fh:
            fh.write(f"{z.pid} 999999")
        tomou_z, _m = tomar_a_trava(t3, pid=os.getpid())
        ok("a trava de um processo morto a tiro nao bloqueia a conferencia "
           "seguinte", tomou_z)
    finally:
        if z is not None:
            z.wait()
        shutil.rmtree(dir3, ignore_errors=True)

    # ── 4-ter. O ANINHADO PARA SOZINHO ────────────────────────────────
    #
    # A marca de profundidade so vale se quem nasce com ela OBEDECER. Sem
    # esta asserção, tirar a marca nao quebra nada de imediato — e a
    # bomba de 30/09 so aparece meia hora depois, quando a memoria acaba
    # e cinco verificadores sem defeito nenhum passam a reprovar.
    try:
        _p = subprocess.run(
            [sys.executable, "checar_mutacao.py", "--autoteste"],
            cwd=RAIZ, env=_AMB_FILHO, capture_output=True, text=True,
            timeout=20)
        _sa = (_p.stdout or "") + (_p.stderr or "")
        ok(f"um --autoteste aninhado nao parou sozinho: {_sa[:120]!r}",
           _p.returncode == 0 and "aninhado" in _sa)
    except subprocess.TimeoutExpired:
        falhas.append("o --autoteste aninhado IGNOROU a marca e foi rodar "
                      "inteiro — e cada rodada dele abre mais processos")

    # ── 5. O SOCORRO: UM KILL NAO RODA `finally` ──────────────────────
    #
    # Nao e cenario inventado: aconteceu em 30/09. O `conferir.py` matou
    # este verificador em 900s e `imagem.py` ficou mutado no disco.
    #
    # Aqui um processo de verdade e MORTO A TIRO (SIGKILL) no meio de uma
    # mutacao de verdade, e o que se mede e o que sobrou no disco depois.
    dir2 = tempfile.mkdtemp(prefix="socorro_")
    vitima = None
    try:
        alvo_py = os.path.join(dir2, "vitima.py")
        original = "VALOR = 1\n"
        with open(alvo_py, "w", encoding="utf-8") as fh:
            fh.write(original)
        pasta = os.path.join(dir2, "socorro")

        # o que o laco de mutacao faz, na ordem em que ele faz
        amb2 = dict(_AMB_FILHO, CHECAR_MUTACAO_SOCORRO=pasta)
        # A VITIMA RODA O LACO DE VERDADE, e nao `_guardar_original`
        # sozinha. A primeira versao desta guarda chamava a funcao que eu
        # tinha acabado de escrever — e ficou VERDE com o laco mutado para
        # nao guardar nada. Guarda que nao exercita o caminho nao e guarda.
        #
        # O comando so dorme quando o arquivo JA esta mutado: assim a
        # pre-conferencia ("o verde tem de ser verde") passa rapido, e o
        # processo fica parado no meio do laco, com o defeito no disco.
        cmd_vitima = (
            "import time;"
            "c = open('vitima.py').read();"
            "time.sleep(60) if '999' in c else None")
        codigo_vitima = (
            "import sys\n"
            "sys.path.insert(0, %r)\n" % RAIZ +
            "import checar_mutacao as m\n"
            "m.RAIZ = %r\n" % dir2 +
            "m.MUTACOES = [('teste', 'vitima.py', %r, %r,\n"
            % (original, "VALOR = 999  # DEFEITO\n") +
            "               [sys.executable, '-c', %r])]\n" % cmd_vitima +
            "print('indo', flush=True)\n"
            "m._conferir_as_mutacoes(0)\n")
        vitima = subprocess.Popen([sys.executable, "-c", codigo_vitima],
                                  cwd=dir2, env=amb2,
                                  stdout=subprocess.PIPE, text=True)
        vitima.stdout.readline()
        _t0 = time.time()
        while time.time() - _t0 < 30:
            with open(alvo_py, encoding="utf-8") as fh:
                if fh.read() != original:
                    break
            time.sleep(0.2)
        vitima.kill()              # SIGKILL: nenhum `finally` roda
        vitima.wait()

        with open(alvo_py, encoding="utf-8") as fh:
            ok("o KILL deixa mesmo o arquivo mutado (senao o teste nao mede "
               "nada)", fh.read() != original)

        # A COPIA NAO PODE TER CARA DE CODIGO.
        #
        # 30/09: ela era salva como `.py`, dentro do repositorio. O
        # `compileall` compilou, deixou um `__pycache__` la dentro, e
        # `checar_tela`, `auditar` e a pre-conferencia do proprio
        # verificador reprovaram lendo o arquivo duplicado. O socorro
        # passou a causar o estrago que existe para desfazer.
        _dentro = os.listdir(pasta) if os.path.isdir(pasta) else []
        ok(f"a copia de socorro tem cara de codigo: {_dentro}",
           _dentro and not any(n.endswith((".py", ".md", ".txt", ".toml"))
                               for n in _dentro))
        # e lixo de terceiro nao pode segurar a pasta viva para sempre
        os.makedirs(os.path.join(pasta, "__pycache__"), exist_ok=True)

        voltaram = socorrer(raiz=dir2, pasta=pasta)
        ok("o socorro devolve o arquivo que o KILL deixou mutado",
           voltaram == ["vitima.py"])
        with open(alvo_py, encoding="utf-8") as fh:
            ok("e o conteudo e o ORIGINAL, nao um remendo",
               fh.read() == original)
        ok("e a pasta do socorro some depois de usada",
           not os.path.isdir(pasta))
        ok("socorro sem nada para fazer devolve lista vazia",
           socorrer(raiz=dir2, pasta=pasta) == [])
    finally:
        if vitima is not None and vitima.poll() is None:
            vitima.kill()
        shutil.rmtree(dir2, ignore_errors=True)

    for f in falhas:
        print(f"FALHA  {f}")
    if not falhas:
        print("ok    a trava recusa a segunda instancia, o main obedece, "
              "e o socorro devolve o que um KILL deixou mutado")
    return 1 if falhas else 0


if __name__ == "__main__":
    if "--autoteste" in sys.argv:
        sys.exit(_autoteste())
    if "--socorro" in sys.argv:
        # Chamado pelo `conferir.py` logo depois de matar este verificador
        # por tempo: o passo 2 nao pode medir um arquivo mutado.
        _v = socorrer()
        print(f"socorro: {', '.join(_v) if _v else 'nada a restaurar'}")
        sys.exit(0)
    sys.exit(main())
