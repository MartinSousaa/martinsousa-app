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
        "    if pts_destrava:\n        alvo = saldo + float(pts_destrava)",
        "    if False:\n        alvo = saldo + float(pts_destrava)",
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
        '            + "\\n\\nO que fazer diferente agora: "\n'
        "            + sem_medida_de_quadro(instrucao))",
        '            + "\\n\\nO que fazer diferente agora: " + instrucao)',
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
                if fh.read() != original:
                    print(f"FALHA  '{nome}': NAO consegui restaurar "
                          f"{arquivo} — o repositorio esta MUTADO agora. "
                          "Rode `git checkout` neste arquivo antes de "
                          "qualquer outra coisa.")
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


if __name__ == "__main__":
    sys.exit(main())
