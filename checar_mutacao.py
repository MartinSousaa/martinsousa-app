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
    (
        'o campo do formulario da equipe volta a nao ter chave por pessoa',
        "admin.py",
        [('                              key=f"eq_user_{_k}",\n',
          '')],
        None,
        ["python3", "checar_tela.py"],
    ),
    (
        'a confirmacao da remocao volta a valer para outra pessoa',
        "admin.py",
        [('                key=f"eq_rm_conf_{_k}",\n',
          '                key="eq_rm_conf",\n')],
        None,
        ["python3", "checar_tela.py"],
    ),
    (
        'a Reserva volta a ficar fora do Balanco headcount',
        "headcount.py",
        [('    _rt.conteudo(usuario_logado)\n', '    pass\n')],
        None,
        ["python3", "checar_tela.py"],
    ),
    (
        'o card do colaborador volta a ter a conta do bonus propria',
        "analise_metas.py",
        [('            meta_col_batida = _b["col"]\n',
          '            meta_col_batida = _sit_pen["bateu_col"] and _entra_col\n')],
        None,
        ["python3", "analise_metas.py"],
    ),
    (
        'as devolucoes voltam a puxar os ultimos meses quando o mes nao tem',
        "home_gestao.py",
        [('    linhas_top, sub_top = (dev_mes or []), "no mês"\n',
          '    linhas_top, sub_top = (dev_mes or dev_todas), "no mês"\n')],
        None,
        ["python3", "home_gestao.py"],
    ),
    (
        'a fatura do cartao volta a gravar as linhas sem classificar',
        "extratos_tela.py",
        [('            classificados, _conta_fat, _comp, usuario_logado)\n',
          '            lancs, _conta_fat, _comp, usuario_logado)\n')],
        None,
        ["python3", "extratos_tela.py"],
    ),
    (
        'as assinaturas voltam a ser conferidas no mes que acabou de comecar',
        "assinaturas_tela.py",
        [('    atual = mes_conferido()\n', '    atual = _meses_recentes(1)[0]\n')],
        None,
        ["python3", "assinaturas_tela.py"],
    ),
    (
        'o LPV negativo volta a ser regravado pelo Salvar',
        "financeiro.py",
        [('                "em branco."))\n            lpv = None\n',
          '                "em branco."))\n')],
        None,
        ["python3", "financeiro.py"],
    ),
    (
        'a Monique volta ao quadro CLT',
        "colaboradores.py",
        [('    {"funcionario": "Gabriel", "cargo": "Analista de Marketing",\n'
          '     "salario_base": 3000.00, "registrado": "Sim"},\n',
          '    {"funcionario": "Gabriel", "cargo": "Analista de Marketing",\n'
          '     "salario_base": 3000.00, "registrado": "Sim"},\n'
          '    {"funcionario": "Monique", "registrado": "Não",\n'
          '     "salario_base": 2400.00, "no_aporte": "Não"},\n')],
        None,
        ["python3", "colaboradores.py"],
    ),
    (
        # 05/10, na planilha do dono: lucro liquido = MARGEM C. - LPV.
        'o lucro liquido deixa de descontar o LPV',
        "home_gestao.py",
        [('    _ll_venda = (_mc_venda - _lpv) if (_mc_venda is not None and _lpv) else None\n',
          '    _ll_venda = _mc_venda if (_mc_venda is not None and _lpv) else None\n')],
        None,
        ["python3", "checar_tela.py"],
    ),
    (
        'o LPV volta a esquecer o nao operacional (PRONAMPs)',
        "lpv_mensal.py",
        [('    partes = {"custo fixo": custo_fixo, "folha da gerência": folha_gerencia,\n'
          '              "assinaturas": assinaturas, "não operacional": nao_operacional}\n',
          '    partes = {"custo fixo": custo_fixo, "folha da gerência": folha_gerencia,\n'
          '              "assinaturas": assinaturas}\n')],
        None,
        ["python3", "lpv_mensal.py"],
    ),
    (
        'o LPV em uso volta a ser o custo operacional por venda',
        "financeiro.py",
        [('            meses, _erro = _lm.lpv_do_ano(ano)\n',
          '            meses, _erro = _lm.custo_operacional_do_ano(ano)\n')],
        None,
        ["python3", "financeiro.py"],
    ),
    (
        'grade da gerencia nao salva volta a entrar como zero no LPV',
        "lpv_mensal.py",
        [('            None if cache["fs"][0].empty else\n',
          '            0.0 if cache["fs"][0].empty else\n')],
        None,
        ["python3", "lpv_mensal.py"],
    ),
    (
        'o titulo "Home" volta a empurrar os graficos para baixo',
        "home_gestao.py",
        [('    # O painel já abre com o mês e a fonte dos números, que é o que orienta.\n',
          '    # O painel já abre com o mês e a fonte dos números, que é o que orienta.\n'
          '    st.markdown("### 🏠 Home")\n')],
        None,
        ["python3", "home_gestao.py"],
    ),
    (
        'a baixa do cheque volta a ignorar a folha na descricao do Itau',
        "cheques.py",
        [('            if id(lan) in usados or _num_cheque(lan) != folha:\n',
          '            if True:\n')],
        None,
        ["python3", "cheques.py"],
    ),
    (
        'a tela de Cheques volta a so conferir no anexo do extrato',
        "cheques_tela.py",
        [('        _feitas, _duv_ch, _err_ch = _ch.conferir_com_extratos(\n'
          '            usuario_logado, linhas)\n',
          '        _feitas, _duv_ch, _err_ch = 0, [], []\n')],
        None,
        ["python3", "cheques.py"],
    ),
    (
        'cheque compensado dias depois volta a nunca dar baixa sozinho',
        "cheques.py",
        [('        if len(cand) == 1 and not mesmos:\n', '        if False:\n')],
        None,
        ["python3", "cheques.py"],
    ),
    (
        'o custo fixo do mes volta a ignorar o valor real do extrato',
        "previsto.py",
        [('    return _cr.total_custo_fixo(grade, _aj.carregar(), ano, mes, _cr.carregar())\n',
          '    return round(float(_aj.aplicar(grade, _aj.carregar(), "custo_fixo", ano, mes)), 2)\n')],
        None,
        ["python3", "custo_real.py"],
    ),
    (
        'PIX recebido volta a contar como cobranca do custo fixo',
        "custo_real.py",
        [('            if v < 0:\n                total += -v\n',
          '            if v:\n                total += abs(v)\n')],
        None,
        ["python3", "custo_real.py"],
    ),
    (
        'o anexo do extrato volta a nao conferir o custo fixo',
        "extratos_tela.py",
        [('        _, _feitas_cr, _erro_cr = _cr.conferir_meses(_meses)\n',
          '        _, _feitas_cr, _erro_cr = [], 0, ""\n')],
        None,
        ["python3", "custo_real.py"],
    ),
    (
        'abono e atestado voltam a nao contar como horas trabalhadas',
        "analise_metas.py",
        [('                  + float(p.get("min_abono", 0.0) or 0.0))\n        fora.append((f"horas trabalhadas',
          '                  + 0.0)\n        fora.append((f"horas trabalhadas')],
        None,
        ["python3", "analise_metas.py"],
    ),
    (
        'tolerancia volta a reprovar a meta antes da regra nova',
        "analise_metas.py",
        [('    fora.append(("tolerâncias (não computadas até definição)", None))\n',
          '    fora.append(("tolerâncias (não computadas até definição)", p["tol"] <= tol_lim))\n')],
        None,
        ["python3", "analise_metas.py"],
    ),
    (
        'o abono do dia de atestado volta a ficar fora das horas',
        "relogio_ponto.py",
        [('            acc["abono_total_min"] += float(reg.get("minutos_abonados") or 0)\n', '')],
        None,
        ["python3", "relogio_ponto.py"],
    ),
    (
        'a UNI. CONT. (a UC) volta a ser somada como quantidade',
        "base_vendas.py",
        [('    "unidades": ("quantidade",),\n', '    "unidades": ("uni cont",),\n')],
        None,
        ["python3", "base_vendas.py"],
    ),
    (
        'o vale-transporte por pessoa volta a sumir do Ajuste de valor',
        "ajustes.py",
        [('         ["colaboradores", "vale_transporte"])\n',
          '         ["colaboradores"])\n')],
        None,
        ["python3", "ajustes.py"],
    ),
    (
        'o log volta a gravar produto vazio na geracao pelo codigo',
        "imagem.py",
        # A ancora acompanhou a correcao de 05/10: o `produto` passou a sair
        # de `definir_produto_da_sessao`, a porta unica. O defeito medido e o
        # mesmo — a marcacao sai e o log grava produto vazio.
        [('                try:\n                    import log_imagem as _li_ger\n                    _li_ger.marcar_contexto(\n                        produto=definir_produto_da_sessao(\n                            cfg.get("nome_produto", ""),\n                            codigo=cfg.get("codigo", "")),\n                        usuario=usuario_logado)\n                except Exception:',
          '                try:\n                    pass\n                except Exception:')],
        None,
        ["python3", "imagem.py", "--autoteste"],
    ),
    (
        'o caminho Responses+tools volta a morrer no parametro recusado',
        "imagem.py",
        [('                        _qual = parametro_recusado(_e_par, list(_tools_cfg))',
          '                        _qual = ""')],
        None,
        ["python3", "imagem.py", "--autoteste"],
    ),
    (
        'o caminho images.edit volta a morrer no parametro recusado',
        "imagem.py",
        [('                        _qual_e = parametro_recusado(_e_pe, list(_args_edit))',
          '                        _qual_e = ""')],
        None,
        ["python3", "imagem.py", "--autoteste"],
    ),
    (
        'o chat volta a anunciar a acao em duas vozes',
        'chat_assistente.py',
        [('            texto_final = sem_anuncio_de_acao(resposta)',
          '            texto_final = resposta')],
        None,
        ['python3', 'chat_assistente.py', '--autoteste'],
    ),
    (
        'a referencia anexada volta a se perder no refazer',
        'chat_assistente.py',
        [('                        {"num": foto_num, "instrucao": instrucao,\n                         "referencia": referencia_do_pedido(\n                             st.session_state.get("ms_chat_hist"))})',
          '                        {"num": foto_num, "instrucao": instrucao})')],
        None,
        ['python3', 'chat_assistente.py', '--autoteste'],
    ),
    (
        'o refazer volta a mandar so as fotos, sem a referencia',
        'imagem.py',
        [('                          args=(_prompt, _fotos_desta, _r),',
          '                          args=(_prompt, _fotos_rf, _r), daemon=True).start()')],
        None,
        ['python3', 'imagem.py', '--autoteste'],
    ),
    # ── 01/10: O ROTEADOR AJUSTAR x REFAZER ──────────────────
    #
    # "mudar a quantidade de divisorias para 6" ia para o ajuste fino,
    # que e edicao cirurgica: ele nao recompoe geometria e devolve a
    # imagem INTACTA, sem erro. Quatro rodadas assim, e o Studio
    # anunciando "instrucao enviada" em todas.
    (
        "o chat volta a decidir sozinho entre ajustar e refazer",
        "chat_assistente.py",
        [('            _modo_rot, _por_rot = _img_rot.classificar_edicao(instrucao)',
          '            _modo_rot, _por_rot = "ajustar", ""')],
        None,
        ["python3", "chat_assistente.py", "--autoteste"],
    ),
    (
        "mudar a quantidade de pecas volta a ser tratado como retoque",
        "imagem.py",
        [('    (r"(?:quantidade|n[úu]mero)\\s+de\\s+\\w+|"\n     r"\\b\\d+\\s+"\n     r"(?:divis[óo]ri|nicho|comparti|al[çc]a|gaveta|prateleira|furo|"\n     r"bot[ãa]o|bot[õo]es|pe[çc]a)",\n     "muda a quantidade de peças do produto"),',
          '    (r"ZZZ_NUNCA_CASA_ZZZ",\n     "muda a quantidade de peças do produto"),')],
        None,
        ["python3", "imagem.py", "--autoteste"],
    ),
    # ── 01/10: O AJUSTE RECUSAVA TODO PEDIDO QUE MEXESSE NO PRODUTO ────
    #
    # Cinco pedidos do dono em sequencia, todos recusados: "mudar a cor
    # interior para preta", "6 divisorias". Mensagem, cinco vezes: "toda vez
    # o produto mudava junto, e produto errado e pior que peca sem
    # correcao".
    #
    # O produto mudava porque ELE PEDIU que mudasse. Tres vozes proibiam o
    # pedido ao mesmo tempo: o booleano `produto_alterado` do juiz, o
    # cabecalho "O PRODUTO NAO E PARTE DO AJUSTE — regra acima de qualquer
    # instrucao", e a `_trava_cor_produto` colada sem olhar o pedido.
    (
        "o ajuste volta a aceitar sem olhar se mudou o que ninguem pediu",
        "imagem.py",
        [('        if veredito.get("feito") and not _colateral and not _dano_produto:',
          '        if veredito.get("feito"):')],
        None,
        ["python3", "imagem.py", "--autoteste"],
    ),
    (
        "a trava de cor volta a proibir o que o pedido mandou mudar",
        "imagem.py",
        # A ancora perdeu o `cor_do_produto_atual()`: ele lia a tela de
        # dentro da thread e saiu daqui (05/10). O defeito medido e o
        # mesmo — a trava volta a valer mesmo quando o pedido fala de cor.
        [('    _trava = ("" if _pedido_fala_de_cor(instrucao) else\n'
          '              _trava_cor_produto(cor_produto))\n'
          '    if _pedido_fala_de_cor(instrucao):',
          '    _trava = _trava_cor_produto(cor_produto)\n'
          '    if False:')],
        None,
        ["python3", "imagem.py", "--autoteste"],
    ),
    (
        "a revisao de texto volta a redesenhar sem ninguem julgar o resultado",
        "imagem.py",
        [('    if relato.get("ok") and img_ok is not None and img_ok != img:',
          '    if False:')],
        None,
        ["python3", "imagem.py", "--autoteste"],
    ),
    # ── 01/10: AS QUATRO ROTAS DE EMERGENCIA DA ANALISE EXTERNA ────────
    #
    # Segunda rodada da auditoria. O ChatGPT nomeou o padrao melhor do que
    # eu: *"o risco principal agora e deixar ROTAS DE EMERGENCIA reabrirem
    # decisoes que o planejador ja deveria ter encerrado"*. Quatro delas
    # estavam vivas, e as quatro viraram entrada aqui.
    (
        "o prompt volta a dizer que um bloco a menos esta bom",
        "imagem.py",
        # A ANCORA MUDOU EM 02/10, e o verificador reprovou a entrada velha —
        # com razao: ela apontava para "o conteúdo de cada cartão já veio
        # pronto", redacao que saiu quando a REGRA DE TEXTO REAL virou
        # `INSTRUCAO_TEXTO_REAL`, compartilhada pelo cartao e pelo callout.
        # Entrada que nao se aplica mais da impressao de cobertura que nao
        # existe, e e isso que ele cobra.
        [("- NÃO INVENTE TEXTO: o que se escreve já veio pronto no bloco de TEXTO",
          "  Bloco a menos é melhor que bloco com texto inventado.\n- NÃO INVENTE TEXTO: o que se escreve já veio pronto no bloco de TEXTO")],
        None,
        ["python3", "checar_comunicacao.py"],
    ),
    (
        "o ingles volta a dizer 'no maximo N' onde o portugues diz 'exatamente N'",
        "imagem.py",
        [("        + ((f\"- EXACTLY {_max_blocos} information element(s) — \"\n"
          "            f\"never fewer, never more, never merged\\n\"\n"
          "            if _pedidos_fechados else\n"
          "            f\"- Maximum {_max_blocos} information elements if text present — never cluttered\\n\")",
          "        + ((f\"- Maximum {_max_blocos} information elements if text present — never cluttered\\n\"\n"
          "            if True else\n"
          "            f\"- Maximum {_max_blocos} information elements if text present — never cluttered\\n\")")],
        None,
        ["python3", "checar_comunicacao.py"],
    ),
    (
        "o pedido de quadrada volta a ter plano B silencioso",
        "imagem.py",
        [("                # A FORMA \"SEM PROPORCAO\" SAIU DAQUI, EM 01/10.",
          "                (\"sem proporcao\", {\"responseModalities\": [\"IMAGE\"]}),\n"
          "                # A FORMA \"SEM PROPORCAO\" SAIU DAQUI, EM 01/10.")],
        None,
        ["python3", "checar_comunicacao.py"],
    ),
    (
        "sem copy, o prompt volta a PEDIR bloco de texto que ninguem escreveu",
        "imagem.py",
        # O DEFEITO MUDOU DE FORMA EM 02/10, E A ENTRADA MUDA COM ELE.
        #
        # Ate aqui esta entrada media "o prompt volta a mandar uma FAIXA de
        # blocos". Mas fechar o NUMERO nunca foi o conserto: com `textos: []`
        # no plano, o prompt mandava desenhar N cartoes e nao dava palavra
        # nenhuma para por neles. O Gemini escreveu a DESCRICAO DO CAMPO
        # dentro do cartao — "TITULO CURTO EM CAIXA ALTA: TEXTURA UNICA E
        # PROFUNDA" — e inventou sete cotas na peca 5.
        #
        # Hoje, sem copy, a peca sai SEM TEXTO. A mutacao reintroduz o pedido.
        # A FRASE VIROU `MARCA_SEM_COPY` (imagem.py:284), porque tres
        # leitores a procuravam por texto cru e um deles ficou para tras.
        # A ancora acompanha a constante: entrada presa em texto que nao
        # existe mais nao muta nada, e "passa" sem medir.
        [('    return (MARCA_SEM_COPY + " o plano voltou sem texto para ela. "',
          '    return (f"- Esta peça tem exatamente {maximo} bloco(s) de texto. "\n'
          '            f"Não acrescente nenhum outro, e não entregue menos.")\n'
          '    return (MARCA_SEM_COPY + " o plano voltou sem texto para ela. "')],
        None,
        # O COMANDO E O AUTOTESTE DO `imagem.py`, E NAO O `checar_comunicacao`.
        #
        # A primeira versao desta entrada apontava para o `checar_comunicacao`
        # e ficou VERDE com o defeito de volta — ele monta os prompts COM
        # copy, entao o caminho "sem copy" nunca e percorrido. O verificador
        # estava certo em reprovar a entrada: guarda que nao passa pela linha
        # mutada nao e guarda.
        ["python3", "imagem.py", "--autoteste"],
    ),
    # ── 01/10: A REFERENCIA DE LAYOUT MANDAVA NA QUANTIDADE DE CARTOES ──
    #
    # ACHADO PELO CHATGPT, lendo o CODIGO_GERACAO_DE_IMAGEM.txt que o dono
    # mandou analisar. Ele escreveu: *"o codigo ainda contem 'a referencia de
    # layout manda na quantidade de blocos' e, depois, uma regra que permite
    # usar menos cartoes se nao couber; isso devolve ao Gemini uma decisao
    # que deveria estar fechada antes da chamada"*. Estava certo nas duas.
    #
    # A REGRA DE DENSIDADE tinha, em itens vizinhos, sem linha em branco:
    #
    #     - QUANDO HOUVER IMAGEM DE REFERENCIA DE LAYOUT, ELA MANDA.
    #       Reproduza a mesma quantidade de blocos (...) mesmo que sejam 5 ou
    #       6 blocos. (...) qualquer numero abaixo desta regra nao se aplica.
    #     - Esta peca tem exatamente 1 bloco(s) de texto.
    #
    # A segunda e o numero que o sistema calculou; a primeira manda ignorar
    # a segunda COM TODAS AS LETRAS. Duas autoridades sobre o mesmo numero.
    #
    # E `checar_comunicacao` nao via: ele parava no primeiro achado de cada
    # BLOCO, e os dois itens sao do mesmo bloco. A Forma 2 dentro do proprio
    # verificador — a regra procurava a REDACAO que ja tinha quebrado
    # ("exatamente N bloco") em vez do ASSUNTO.
    (
        "a referencia de layout volta a mandar na quantidade de cartoes",
        "imagem.py",
        [("- A IMAGEM DE REFERÊNCIA DE LAYOUT, QUANDO HOUVER, MANDA NO ESTILO: posição\n"
          "  dos cartões, forma, cor, tipografia, ícones e espaçamento. Ela NÃO manda na\n"
          "  QUANTIDADE de cartões nem no TAMANHO do texto — esses dois já vêm resolvidos\n"
          "  nas linhas abaixo, e nada nesta peça os altera.",
          "- QUANDO HOUVER IMAGEM DE REFERÊNCIA DE LAYOUT, ELA MANDA. Reproduza a mesma\n"
          "  quantidade de blocos, o mesmo tamanho de texto e a mesma densidade que ela\n"
          "  mostra — mesmo que sejam 5 ou 6 blocos. A referência é o padrão aprovado da\n"
          "  empresa; qualquer número abaixo desta regra não se aplica a ela.")],
        None,
        ["python3", "checar_comunicacao.py"],
    ),
    # ── 01/10: "USE MENOS CARTOES SE NAO COUBER" — A ORDEM IMPOSSIVEL ───
    #
    # Eu relatei ao dono que esta ordem tinha sido removida. NAO TINHA: eu
    # procurei por "menos blocos" e o texto diz "menos cartoes", e procurei
    # "nao couber" com grep sem dobra de acento, que nao casa "NAO COUBEREM".
    # Ela estava viva em 6 dos 9 tipos.
    #
    #     - Esta peca tem exatamente 3 bloco(s) de texto.
    #     - SE NAO COUBEREM TODOS na coluna com essa folga, use MENOS cartoes.
    #
    # A primeira fecha a decisao; a segunda a reabre. E a Regra 2 nao alcanca
    # este par, porque "use MENOS" nao tem numero — dai a REGRA 2-bis, que
    # procura a ordem que DEVOLVE ao modelo uma decisao ja tomada.
    (
        "o prompt volta a autorizar o modelo a usar menos cartoes",
        "imagem.py",
        [("- A QUANTIDADE DE CARTÕES JÁ CABE: ela foi calculada para ESTA peça, com ESTA\n"
          "  folga, antes de este texto ser escrito. Não reduza o número para fazer caber,\n"
          "  não junte dois num só, não deixe nenhum de fora. Faltando espaço, diminua a\n"
          "  ALTURA e o ESPAÇAMENTO dos cartões — nunca a quantidade, nunca comprima o\n"
          "  texto a ponto de cortar, nunca empilhe até a borda, nunca deixe um pela\n"
          "  metade.",
          "- SE NÃO COUBEREM TODOS na coluna com essa folga, use MENOS cartões e maiores —\n"
          "  nunca comprima, nunca empilhe até a borda, nunca deixe um pela metade.")],
        None,
        ["python3", "checar_comunicacao.py"],
    ),
    # ── 01/10: O PROMPT PEDIA 3 CARTOES E ENTREGAVA 1 ──────────────────
    #
    # ACHADO NO ARQUIVO DO DONO e reproduzido linha a linha contra o codigo
    # que estava em producao em 30/09.
    #
    # A peca 2 foi ao motor, na REFACAO, assim:
    #
    #     - Esta peça tem exatamente 3 bloco(s) de texto.
    #     1. PROTEÇÃO contra poeira e impactos ORGANIZAÇÃO espaço organizado
    #        e seguro MADEIRA NATURAL durável e elegante
    #
    # A geracao montou 3 blocos e declarou 3. A revisao de texto devolveu a
    # correcao como UMA STRING com os tres colados, e `trocar_texto_exato`
    # troca so o bloco TEXTO EXATO — a linha da contagem ficou da geracao.
    #
    # Resultado: tres cartoes pedidos, um entregue, numa frase corrida de 108
    # caracteres sem pontuacao para ser partida em tres. O modelo parte onde
    # consegue — sao os cartoes embaralhados e sobrepostos que o dono chamou
    # de "quadrados sobressaindo o outro".
    #
    # Trocar o texto sem trocar o numero e deixar duas vozes sobre a mesma
    # coisa: o defeito que mais custou nesta base.
    (
        "a refacao volta a trocar o texto e deixar o numero de blocos para tras",
        "imagem.py",
        # A SINCRONIZACAO VIROU `_sincronizar_contagem` (imagem.py:5141),
        # dono unico das DUAS redacoes da contagem. A mutacao desliga a
        # funcao inteira, e nao mais o trecho inline que nao existe mais.
        [('    saida = _re_quadro.sub(\n'
          '        r"(- Esta peça tem exatamente )\\d+( bloco)",\n'
          '        lambda _m: f"{_m.group(1)}{_n}{_m.group(2)}", prompt)\n',
          '    saida = prompt\n')],
        None,
        ["python3", "imagem.py", "--autoteste"],
    ),
    # ── 01/10: SEM FOTO, A PECA SAIA CALADA ────────────────────────────
    #
    # Dono: "criacao de uma foto totalmente errada comparada ao produto
    # original anexado nas imagens do produto".
    #
    # `revisar_peca` devolvia `None` quando faltava foto de referencia, e
    # `peca_em_aviso(None)` devolve "". A peca chegava a galeria com a mesma
    # cara de uma peca CONFERIDA E APROVADA: sem veredito, sem aviso.
    #
    # E "sem foto" e exatamente o caso em que o produto tem mais chance de
    # sair errado — o motor o reconstroi a partir do texto. A diferenca entre
    # "conferi e esta boa" e "nao consegui conferir" e a diferenca entre
    # publicar e nao publicar.
    #
    # A guarda ANTIGA exigia `_rel is None`: ela assinava embaixo do silencio.
    # Foi reescrita para medir a propriedade certa — nao roda a conferencia
    # (nao ha com o que comparar) mas DIZ que nao rodou.
    (
        "a peca sem foto volta a sair sem veredito e sem aviso",
        "imagem.py",
        [('    if not fotos_ref:\n'
          '        return img, {"ok": None, "rodadas": 0, "problemas": [],\n'
          '                     "erro": "sem foto do produto para comparar — o motor "\n'
          '                             "montou a peça a partir do texto"}',
          '    if not fotos_ref:\n        return img, None')],
        None,
        ["python3", "imagem.py", "--autoteste"],
    ),
    # ── 01/10: A TELA SABIA E NAO CONTAVA O QUE AQUILO SIGNIFICA ───────
    #
    # Dono: "margem nas fotos" e "criacao de uma foto totalmente errada
    # comparada ao produto original". As duas vem da MESMA causa: a conta nao
    # tem `gpt-image-*`, entao toda peca COM fotos cai no motor reserva, que
    # nao aceita `size=1024x1024` nem `input_fidelity=high`.
    #
    # A tela de diagnostico LISTAVA os modelos da conta e parava ai. Um nome
    # de modelo nao diz a ninguem que as pecas vao sair com margem. O Studio
    # tinha a informacao e nao a transformava em recado — a mesma falha que o
    # oitavo verificador existe para pegar.
    #
    # A mutacao faz a tela voltar a nao dizer nada.
    (
        "a tela volta a listar os modelos sem dizer o que isso custa",
        "imagem.py",
        [("                _cap_ok, _cap_recado = capacidade_do_motor(_disp)",
          '                _cap_ok, _cap_recado = (True, "")')],
        None,
        ["python3", "imagem.py", "--autoteste"],
    ),
    # ── 01/10: A CONFERENCIA COBRAVA "METADE DO QUADRO" DE UMA CENA ────
    #
    # Dono: "produtos pequenos comparados as dimensoes da imagem" e, antes,
    # "o produto esta GIGANTE nas maos da crianca". Sao os dois lados do
    # MESMO defeito, e este aqui estava escondido na CONFERENCIA.
    #
    # A quarta pergunta da revisao da peca era "pequeno demais, ocupando
    # menos de METADE do quadro?" — numero escrito a mao. Nas pecas de cena
    # (3, 7, 8) o produto ocupa uma fracao modesta porque e essa a escala
    # real dele: um compasso de 16 cm na mao de uma crianca nao chega perto
    # de metade do quadro. A pergunta mandava REPROVAR a peca certa, e cada
    # reprovacao aqui e uma geracao PAGA que volta com o produto inflado.
    #
    # A conferencia fabricava o defeito que o prompt acabou de parar de
    # pedir. E era a TERCEIRA voz sobre o mesmo numero, depois da faixa em
    # OCUPACAO e do bloco de protagonismo.
    (
        "a conferencia volta a cobrar fracao do quadro das pecas de cena",
        "imagem.py",
        [("    if numero_do_tipo(tipo) in TIPOS_DE_CENA:\n"
          "        return (base + \" E ele aparece na ESCALA REAL que teria nessa cena, \"",
          "    if False:\n"
          "        return (base + \" E ele aparece na ESCALA REAL que teria nessa cena, \"")],
        None,
        ["python3", "imagem.py", "--autoteste"],
    ),
    # ── 01/10: O STUDIO ACHAVA O MOTOR E NAO SABIA FALAR COM ELE ───────
    #
    # O filtro corrigido em 30/09 passou a ENCONTRAR o `dall-e-3` na conta. E
    # a chamada sem fotos mandava `quality="high"` e `response_format`, que
    # sao da familia `gpt-image-*`: o `dall-e-3` recusa os dois. O Studio
    # achava o motor, chamava e levava 400 — e a peca morria justamente no
    # caminho que existe para quando nao ha fotos do produto.
    #
    # O CONSERTO NAO FOI ESCREVER O QUE EU ACHO QUE CADA MODELO ACEITA. Foi
    # assim que o nome do modelo e o campo da proporcao viraram defeito nesta
    # base: valor escrito a mao sobre a API de outro envelhece sem avisar. A
    # chamada le o nome do parametro NA RESPOSTA DE ERRO e tira aquele.
    #
    # A mutacao faz a chamada parar de ler a recusa: o 400 volta a matar a
    # peca, e a guarda tem de ficar vermelha.
    (
        "a chamada sem fotos volta a nao se adaptar ao modelo",
        "imagem.py",
        [('                _qual = parametro_recusado(_e_gen, _args_gen)',
          '                _qual = ""')],
        None,
        ["python3", "imagem.py", "--autoteste"],
    ),
    # ── 01/10: AS DUAS CONTAS DO MESMO NUMERO ──────────────────────────
    #
    # `_processar` existe DUAS vezes: `placar.py` e `placar_core.py`. As duas
    # estao VIVAS, em telas diferentes — o Painel de Metas (que decide bonus)
    # chama a do core; o Placar e mais quatro telas chamam a do placar. Elas
    # ja discordaram em 330 PONTOS, no mesmo mes e na mesma sessao.
    #
    # Medido: hoje concordam nas 25 chaves em comum, em 18 cenarios (450
    # comparacoes). O defeito nao e "discordam agora" — e "vao discordar, e
    # nada vigia". A mutacao soma 1 ponto de um lado so.
    #
    # NOTA: a primeira versao desta guarda deu ALARME FALSO. `python3
    # placar_core.py` faz este arquivo ser `__main__`, e `import placar` cria
    # uma SEGUNDA instancia de placar_core — com outro `MEMBROS_ATIVOS`. A
    # comparacao passou a ser feita na instancia que o `placar` realmente
    # enxerga, que e a que roda no Studio.
    (
        "as duas contas do mesmo numero voltam a poder discordar",
        "placar.py",
        [('        d["pts_equipe"]+=pt\n', '        d["pts_equipe"]+=pt+1\n')],
        None,
        ["python3", "placar_core.py"],
    ),
    # ── 30/09: AS 65 REGRAS SO ERAM MEDIDAS COM O CADASTRO CHEIO ───────
    #
    # O cadastro do teste sempre teve medida, peso e material — e e no VAZIO
    # que o tipo 5 se contradizia: "INFOGRAFICO TECNICO DE MEDIDAS" junto de
    # "JAMAIS invente medidas". Com dado as duas conviviam; sem dado elas se
    # anulavam, e o modelo resolvia contradicao inventando numero.
    #
    # O MOTIVO QUE EU TINHA ESCRITO PARA NAO FAZER ISTO ERA FALSO. Estava no
    # ACHADOS_ABERTOS.md: "dobra o tempo do verificador, que ja e a parte mais
    # lenta do protocolo". Medido: `checar_prompts.py` leva 2,8 SEGUNDOS, e a
    # segunda passada nao mudou o relogio. A parte lenta e o `checar_mutacao`,
    # com vinte minutos. Escrevi um motivo sem medir e ele ficou de pe por
    # dias, segurando uma varredura que custava zero.
    #
    # A mutacao tira uma regra da lista de isencao: ela passa a ser cobrada no
    # vazio, onde a linha nao existe. Nove tipos, nove reprovacoes — e e isso
    # que prova que a segunda passada roda de verdade.
    (
        "a varredura com cadastro vazio deixa de medir",
        "checar_prompts.py",
        [('    "o material e a montagem",\n', "")],
        None,
        ["python3", "checar_prompts.py"],
    ),
    # ── 30/09: DOIS CARTOES IDENTICOS NA MESMA PECA ────────────────────
    #
    # O item "corte de texto nas pecas 4 e 5" estava ABERTO desde 28/09 com o
    # motivo "preciso do prompt real para separar 'o layout nao cabe' de 'o
    # modelo desobedeceu'". O arquivo que o dono mandou tinha o prompt real, e
    # a peca 4 respondeu sozinha:
    #
    #     1. MADEIRA TRABALHADA: / Acabamento e textura
    #     2. MADEIRA TRABALHADA: / Acabamento e textura
    #     3. MONTAGEM: / Construcao precisa
    #
    # Nao foi o modelo que desobedeceu: foi a NOSSA copy que pediu dois
    # cartoes iguais, e o teto da peca gastou uma vaga com a repeticao.
    #
    # Esta base ja conferia `faces_repetidas` e `cenas_repetidas` entre pecas;
    # bloco de texto repetido DENTRO da peca, nao. Forma 1 de novo.
    #
    # NOTA SOBRE A GUARDA: a primeira versao dela usava `find(...) < find(...)`
    # e ficava VERDE com a chamada removida, porque `find` devolve -1 quando
    # nao acha e -1 e menor que tudo. Foi esta mutacao que mostrou.
    (
        "o bloco de texto repetido volta a ser enviado ao motor",
        "imagem.py",
        [("        _textos, _repetidos = blocos_sem_repeticao(_textos)\n", "")],
        None,
        ["python3", "imagem.py", "--autoteste"],
    ),
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
            # A ANCORA E SO O CALCULO DO FIM, e isso e de proposito.
            #
            # Ela prendia a FUNCAO INTEIRA, comentarios inclusive — e na
            # passada de 05/10 ficou presa em texto que nao existia mais
            # (entrou um comentario novo dentro do `if i < 0`). Ancora que
            # nao casa nao muta nada, e a entrada "passa" sem medir: a 16a
            # entrada desta lista ja esteve verde exatamente por isso.
            #
            # Com a marca de fim fora (o segundo corte, logo abaixo), o
            # `f >= 0` nao acha nada e quem roda e o `else`. Mutar o `else`
            # para o corte antigo — ate a proxima "━━━" — e o defeito
            # original inteiro: a SECTION 2 vem doze mil caracteres adiante,
            # e tudo entre ela e a copy ia junto.
            ('        _ultima = "para preencher espaço."\n'
             "        _u = base.find(_ultima, i)\n"
             "        fim = (_u + len(_ultima)) if _u >= 0 else i + len(MARCA_TEXTO_EXATO)\n",
             '        _j = base.find("━━━", i + len(MARCA_TEXTO_EXATO) + 1)\n'
             "        fim = _j if _j > 0 else len(base)\n"),
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
        '                        img_bytes, _rel_txt, _rel_peca = revisar_tudo(\n                            img_bytes, tipo,\n                            fotos_ref=cfg["fotos_bytes"],\n                            gerar=_gerar_de_novo,\n                            prompt_base=prompt_final,\n                            pedido=cfg.get("instrucoes_extras", ""),\n                            dados_descricao=cfg.get("dados_descricao") or {},\n                            aviso=lambda t, _i=i: barra.progress(\n                                _i / len(tipos), text=t[:70]),\n                        )\n',
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
        # A ancora acompanhou a correcao de 06/10: o descoberto e o PADRAO
        # passaram pelo mesmo filtro, e quando nenhum serve a funcao devolve
        # "". O defeito medido e o mesmo: a variavel voltar a mandar.
        "    cfg = _ch_mod.ler(\"OPENAI_MODELO_IMAGEM\")\n"
        "    if cfg and cfg not in _MODELO_INVALIDO:\n        return cfg\n",
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
        # A ancora acompanhou a correcao de 05/10: a funcao deixou de
        # escrever nas chaves de widget e passa a deixar um PEDIDO, que a
        # aba aplica antes de desenhar os widgets. O defeito medido e o
        # mesmo — o chat promete marcar os tipos e nao marca nada.
        '    st.session_state["img_pedido_faltantes"] = list(faltam)\n    return True',
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
        "a recusa por mudanca nao pedida volta a tirar a opcao de insistir",
        "imagem.py",
        '        return (f"❌ Imagem {num}: a alteração não foi aplicada. Em "\n'
        '                f"{_n_tent} tentativa(s) ela veio acompanhada de mudanças "',
        '        return (f"❌ Imagem {num}: a alteração não foi aplicada. "\n'
        '                f"Mudanças vieram junto. "',
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
        "        _cena_limpa = sem_decisao_do_compilador(plano_triagem_item_cena)",
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
        # UMA LINHA SO. A ancora pegava as DUAS, e entre elas entrou o
        # bloco que grava a copy vigente (`guardar_copy_vigente`) — ela
        # deixou de casar e a entrada parou de medir. Trocar o destino da
        # atribuicao faz a correcao morrer na rodada: `gerar` recebe a
        # base velha, que e o defeito original.
        "        prompt_base = trocar_texto_exato(prompt_base, _certo_limpo)\n",
        "        _base_corrigida = trocar_texto_exato(prompt_base, _certo_limpo)\n",
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
        '            _img_rf, _rel_t_rf, _rel_p_rf = revisar_tudo(\n                _r["img"], _tp, fotos_ref=_fotos_rf, gerar=_gerar_rf,\n                prompt_base=_prompt, pedido=_ins,\n                dados_descricao=_dados_rf,\n                aviso=lambda t: _b.progress(1.0, text=t[:70]))\n',
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
        "- O produto PODE ser alterado exatamente nas características que a\n"
        "  MODIFICAÇÃO SOLICITADA mandar alterar. Essas mudanças são o objetivo.\n",
        "- Se a modificação pedida só puder ser feita alterando o produto, NÃO a faça:\n"
        "  devolva a imagem como está.\n",
        ["python3", "imagem.py", "--autoteste"],
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
        '                "input_fidelity": "high",\n',
        "",
        ["python3", "checar_comunicacao.py"],
    ),
    (
        # O caminho da OpenAI SEM fotos entregava a peca sem gravar o motor:
        # a tela mostrava "Motor —" justamente no caminho onde o produto tem
        # mais chance de sair errado, porque o modelo nao ve as fotos.
        "um caminho volta a entregar imagem sem dizer por onde ela veio",
        "imagem.py",
        # DUAS LINHAS, E A SEGUNDA CHEGOU DEPOIS.
        #
        # Esta entrada tirava so a primeira gravacao do motor. Em 01/10 a
        # chamada sem fotos ganhou uma SEGUNDA, para dizer quais parametros o
        # modelo recusou — e com ela no lugar, tirar a primeira deixava a
        # chave `motor` ainda com dono: o verificador ficava VERDE com o
        # defeito meio reintroduzido.
        #
        # Foi o proprio `checar_mutacao` que reprovou, e esse e o servico
        # dele. Mutacao que deixa de reintroduzir o defeito vira guarda que
        # assina embaixo — e so se descobre medindo.
        [('            diagnostico["motor"] = f"{_modelo} (images.generate — SEM fotos)"\n', ""),
         # O BLOCO INTEIRO, E NAO SO A LINHA DE DENTRO.
         #
         # Cortar so a gravacao deixava `if _tirados ...:` com corpo vazio, e
         # o verificador ficava vermelho por IndentationError — vermelho por
         # acidente, que nao mede guarda nenhuma. Esta base ja aprendeu isso:
         # "mutacao que nao reintroduz o defeito da alarme falso".
         ('        if _tirados and diagnostico is not None:\n            diagnostico["motor"] = (\n                f"{_modelo} (images.generate — SEM fotos, sem "\n                + ", ".join(_tirados) + ")")\n', "")],
        None,
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
        # A ANCORA ERA O TEXTO DE UM ITEM QUE EU FECHEI, e a mutacao parou de
        # encontrar alvo — o verificador reprovou por "o trecho certo aparece
        # 0 vezes", que e o servico dele. Ancora que aponta para um item
        # especifico morre quando o item e resolvido, que e justamente o que
        # se espera que aconteca. Agora ela aponta para o PRIMEIRO item
        # aberto, seja ele qual for.
        "POR QUE AINDA NÃO: a análise do dia 30/09 foi feita em cima do",
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
    # ── 05/10: A FORMA 6 PELA TERCEIRA VEZ, E A PRIMEIRA VARRIDA ────────
    #
    # `st.session_state` e ilegivel dentro de `threading.Thread`. Eu sabia,
    # apliquei ao numero da peca, e escrevi a copy vigente com o defeito.
    # A varredura por AST (`checar_alcance`, 5-penta) achou mais tres, que
    # estavam la ha semanas: os tres ajustes do chat liam `dados_descricao`
    # de dentro da thread, e e ele que alimenta as barreiras contra medida
    # inventada e claim sem lastro.
    (
        "o ajuste do chat volta a ler dados_descricao dentro da thread",
        "imagem.py",
        '                           _dd=st.session_state.get(\n'
        '                               "img_dados_descricao") or {}):\n'
        "                try:\n",
        "                           ):\n"
        '                _dd = st.session_state.get("img_dados_descricao") or {}\n'
        "                try:\n",
        ["python3", "checar_alcance.py"],
    ),
    (
        "o ajuste fino volta a ler dados_descricao dentro da thread",
        "imagem.py",
        '                          _dd=st.session_state.get(\n'
        '                              "img_dados_descricao") or {}):\n'
        "                try:\n",
        "                          ):\n"
        '                _dd = st.session_state.get("img_dados_descricao") or {}\n'
        "                try:\n",
        ["python3", "checar_alcance.py"],
    ),
    (
        "o ajuste da galeria volta a ler dados_descricao dentro da thread",
        "imagem.py",
        '                                   _dd=st.session_state.get(\n'
        '                                       "img_dados_descricao") or {}):\n'
        "                        try:\n",
        "                                   ):\n"
        '                        _dd = st.session_state.get("img_dados_descricao") or {}\n'
        "                        try:\n",
        ["python3", "checar_alcance.py"],
    ),
    # A COR TEM DE DESCER, e a mutacao corta a DESCIDA — nao o padrao.
    #
    # A primeira mutacao que escrevi devolvia `cor_do_produto_atual()` ao
    # padrao de `montar_prompt_ajuste_fino` e ficou VERDE: com a cor
    # descendo, o padrao nunca e usado. Mutacao que nao reintroduz o
    # defeito da alarme falso, e alarme falso ensina a ignorar o
    # verificador.
    (
        "a cor do cadastro para de descer ate a trava do ajuste",
        "imagem.py",
        '                                 cor_produto=(dados_descricao or {}).get("cor")\n'
        "                                 or None)",
        "                                 cor_produto=None)",
        ["python3", "imagem.py", "--autoteste"],
    ),
    # A VARREDURA NAO PODE FICAR MUDA, e medir isso deu trabalho.
    #
    # A primeira versao desta entrada mutava o `except` que engolia o erro
    # de leitura e mandava rodar `checar_mutacao --autoteste` — que nao le
    # a varredura. Ficou verde, e com razao: comando errado.
    #
    # E apontar para o `checar_alcance` tambem nao resolveria sozinho:
    # varredura muda APROVA TUDO, entao ela fica verde justamente quando
    # esta quebrada. O que torna o defeito visivel e a CONTAGEM: ela
    # imprime quantas funcoes alcancou e reprova no zero. A mutacao tira o
    # alvo da varredura, e aí a contagem cai para zero.
    (
        "a varredura de thread perde o alvo e passa a aprovar tudo",
        "checar_alcance.py",
        '                    _t = ast.unparse(_kw.value)\n',
        '                    _t = "xxx_nao_existe"\n',
        ["python3", "checar_alcance.py"],
    ),
    # ── 05/10: UM NOME, DUAS RESPOSTAS (Forma 5) ────────────────────────
    #
    # A marcacao do contexto na geracao usava `cfg["nome_produto"]`; a tela,
    # o chat e a copy vigente leem `session_state["img_nome_produto"]`, cujo
    # escritor unico e `definir_produto_da_sessao`. Concordavam por tabela —
    # a porta era chamada no FIM da geracao, e so `if galeria`. Geracao que
    # falha inteira deixava o log gravando um nome e o historico filtrando o
    # outro, e a copy corrigida numa chave que ninguem procura.
    (
        "o contexto da geracao volta a sair do cfg, e nao da porta unica",
        "imagem.py",
        '                        produto=definir_produto_da_sessao(\n'
        '                            cfg.get("nome_produto", ""),\n'
        '                            codigo=cfg.get("codigo", "")),\n',
        '                        produto=cfg.get("nome_produto", ""),\n',
        ["python3", "checar_tela.py"],
    ),
    # ── 05/10: O BOTAO "LIMPAR CHAT" ────────────────────────────────────
    #
    # "Limpar a conversa" e "jogar fora o trabalho" sao coisas diferentes, e
    # o estado do chat mistura as duas: tres das seis chaves sao COMANDOS JA
    # ACEITOS que a aba Imagem ainda vai executar. Levar a fila junto seria
    # perder geracao paga em silencio.
    (
        "limpar a conversa volta a cancelar os pedidos ja aceitos",
        "chat_assistente.py",
        '    st.session_state.pop("chat_pendente", None)\n',
        '    st.session_state.pop("chat_pendente", None)\n'
        '    st.session_state.pop("chat_refazer_imagem", None)\n'
        '    st.session_state.pop("chat_img_pendente", None)\n'
        '    st.session_state.pop("chat_refazer_todas", None)\n',
        ["python3", "chat_assistente.py"],
    ),
    (
        "limpar a conversa volta a levar a galeria junto",
        "chat_assistente.py",
        '    st.session_state["ms_chat_hist"] = []\n'
        '    st.session_state.pop("chat_pendente", None)\n',
        "    st.session_state.clear()\n"
        '    st.session_state["ms_chat_hist"] = []\n',
        ["python3", "chat_assistente.py"],
    ),
    # A FOTO PRESA. A chave do `file_uploader` carrega esta versao: sem
    # troca-la, o anexo continua pendurado num chat que acabou de ser zerado.
    (
        "limpar a conversa deixa a foto presa no campo de anexo",
        "chat_assistente.py",
        '    st.session_state["chat_anexo_versao"] = (\n'
        '        st.session_state.get("chat_anexo_versao", 0) + 1)\n',
        "    pass\n",
        ["python3", "chat_assistente.py"],
    ),
    # O BOTAO SAI INTEIRO, e nao "desligado" por um `and`: a guarda e por AST,
    # e um `if False and st.button(...)` deixa a chamada na arvore. Mutacao
    # que nao reintroduz o defeito da alarme falso.
    (
        "o botao Limpar Chat some da tela",
        "chat_assistente.py",
        '                if st.button("Limpar Chat", key="btn_limpar_chat",\n'
        '                             help="Apaga esta conversa e começa do zero. A "\n'
        '                                  "galeria, o plano e as fotos não são "\n'
        '                                  "tocados; pedidos já aceitos continuam.",\n'
        "                             use_container_width=True):\n"
        "                    limpar_conversa()\n"
        "                    st.rerun()\n",
        '                st.caption("")\n',
        ["python3", "chat_assistente.py"],
    ),
    (
        "o botao sai da fileira do anexo e vira uma linha propria",
        "chat_assistente.py",
        '        _col_anexo, _col_limpar = st.columns([2, 1], vertical_alignment="center")\n',
        "        _col_anexo = _col_limpar = st.container()\n",
        ["python3", "chat_assistente.py"],
    ),
    # ── 05/10, TESTE 2 DO DONO: 6 de 8, e a recuperacao quebrada ────────
    #
    # Duas pecas morreram no timeout do Gemini; ele pediu no chat para gerar
    # as faltantes e o comando morreu com "img_modo cannot be modified after
    # the widget with key img_modo is instantiated". A guarda antiga media a
    # funcao com o session_state limpo, onde a regra do Streamlit nao existe.
    (
        "o chat volta a escrever na chave do widget para gerar as faltantes",
        "chat_assistente.py",
        '    st.session_state["img_pedido_faltantes"] = list(faltam)\n',
        '    st.session_state["img_tipos_multi"] = list(faltam)\n'
        '    st.session_state["img_modo"] = "Selecionar"\n',
        ["python3", "checar_tela.py"],
    ),
    (
        "a aba para de aplicar o pedido de gerar as faltantes",
        "imagem.py",
        '    _faltantes_pedidas = st.session_state.pop("img_pedido_faltantes", None)\n',
        "    _faltantes_pedidas = None\n",
        ["python3", "checar_tela.py"],
    ),
    # O TETO DA PECA E O TIMEOUT DO MOTOR SAO UMA CONTA SO. Subir o timeout e
    # deixar o teto para tras so troca a mensagem de erro.
    (
        "o teto da peca volta a ser menor que o orcamento do motor",
        "imagem.py",
        "TETO_POR_PECA_S = orcamento_da_peca() + 60\n",
        "TETO_POR_PECA_S = 300\n",
        ["python3", "imagem.py", "--autoteste"],
    ),
    # O LIMITE SILENCIOSO DA LEITURA DAS REFERENCIAS DE AMBIENTACAO.
    (
        "o teto de tokens das referencias volta a ser fixo",
        "ambientacao_ref.py",
        "    return max(2000, TOKENS_DE_ABERTURA + TOKENS_POR_REFERENCIA * int(quantas or 0))\n",
        "    return 2000\n",
        ["python3", "ambientacao_ref.py"],
    ),
    (
        "o salvamento do JSON cortado aceita cenario sem conteudo",
        "ambientacao_ref.py",
        '                if isinstance(_o, dict) and _o.get("ambiente"):\n',
        "                if True:\n",
        ["python3", "ambientacao_ref.py"],
    ),
    (
        "o varredor do JSON cortado ignora aspas escapadas",
        "ambientacao_ref.py",
        '            elif c == "\\\\":\n                escapa = True\n',
        "            elif False:\n                escapa = True\n",
        ["python3", "ambientacao_ref.py"],
    ),
    # ── 06/10: O DIAGNOSTICO DO DONO DERRUBOU A PREMISSA ────────────────
    #
    # A tela dizia "esta conta nao tem «gpt-image-2»" e, logo abaixo, o
    # diagnostico listava OITO modelos — `gpt-image-2` entre eles — e o
    # `sunburst` gerando imagem em 10,3s. Tres defeitos saem daqui.
    (
        "a redescoberta volta a devolver o modelo que acabou de falhar",
        "imagem.py",
        "        if nome in _MODELO_INVALIDO:\n            continue\n",
        "        if False:\n            continue\n",
        ["python3", "imagem.py"],
    ),
    (
        "volta a banir um modelo que a conta TEM",
        "imagem.py",
        '    if _da_conta and str(nome) in _da_conta:\n',
        "    if False:\n",
        ["python3", "imagem.py"],
    ),
    # O MAIS GRAVE: "nao consegui analisar" virando "esta tudo suficiente".
    # Apontado pelo ChatGPT e confirmado no codigo em imagem.py:2098.
    (
        "a triagem que falha volta a liberar as oito pecas",
        "imagem.py",
        '                    "viavel": False,\n',
        '                    "viavel": True,\n',
        ["python3", "imagem.py"],
    ),
    # ── 06/10: O CARTÃO CONTADO DUAS VEZES NA META DE GASTOS ────────────
    #
    # A meta somava o pagamento da fatura (extrato) E cada compra da fatura
    # confirmada. E a compra pesava no mês da COMPRA: a parcela 7/10 de
    # março caía em março. Regra do dono: "a régua é o CAIXA".
    (
        "o pagamento da fatura volta a somar por cima das compras",
        "lancamentos.py",
        "        if so_saida and _eh_pagamento_de_fatura(l, fin, valor):\n            continue\n",
        "        if False:\n            continue\n",
        ["python3", "lancamentos.py"],
    ),
    (
        "a compra do cartao volta a pesar no mes da compra",
        "lancamentos.py",
        "    if t.startswith(TIPO_FATURA) and len(t) >= len(TIPO_FATURA) + 7:\n",
        "    if False:\n",
        ["python3", "lancamentos.py"],
    ),
    (
        "a fatura gravada antes da regra volta a duplicar quando anexada",
        "lancamentos.py",
        '            if antigo is not None and str(antigo.get("tipo") or "").strip() in ("", tipo):\n',
        "            if False:\n",
        ["python3", "lancamentos.py"],
    ),
    (
        "as compras do cartao deixam de ser descontadas do pago",
        "lancamentos.py",
        "        if eh_do_cartao(l) and v < 0 and _fv.consome_meta(fin):\n",
        "        if False:\n",
        ["python3", "lancamentos.py"],
    ),
    (
        "o C.O volta a perder a fatura paga e nao anexada",
        "lpv_mensal.py",
        "    if _resto > 0:\n        por_finalidade[_lan.FATURA]",
        "    if False:\n        por_finalidade[_lan.FATURA]",
        ["python3", "lpv_mensal.py"],
    ),
    (
        "a fatura gravada antes do mes do caixa volta a nao abater o pagamento",
        "lancamentos.py",
        "            or str(l.get(\"conta\") or \"\").startswith(CONTA_CARTAO))\n",
        "            or False)\n",
        ["python3", "lancamentos.py"],
    ),
    # ── 06/10: A ABA FATURAS ERA UM AVISO SEM CAMPO DE ANEXAR ───────────
    (
        "a aba Faturas volta a esconder o pago sem fatura lancada",
        "extratos_tela.py",
        '        "sem_detalhe": round(max(pago - detalhado, 0.0), 2),\n',
        '        "sem_detalhe": 0.0,\n',
        ["python3", "extratos_tela.py"],
    ),
    (
        "a tela de Faturas quebra ao desenhar o mes",
        "extratos_tela.py",
        "f\"R$ {_fmt(r['compras_total'])}\",",
        "f\"R$ {_fmt(r['compras'])}\",",
        ["python3", "checar_tela.py"],
    ),
    (
        "a aba Faturas do menu volta a ser so um aviso",
        "gestao.py",
        '    _abrir_tela("extratos_tela", usuario_logado, "pagina_faturas")\n',
        '    st.info("As faturas ainda são lidas dentro de Conta corrente.")\n',
        ["python3", "checar_tela.py"],
    ),
    # ── 06/10: A FILA PERGUNTAVA CADA PARCELA, E SALVAVA UMA POR UMA ────
    (
        "cada parcela volta a ser uma pergunta",
        "favorecidos.py",
        '    return re.sub(r"\\s*\\d{1,2}\\s*/\\s*\\d{1,2}\\s*$", "", t).strip(" ·-")\n',
        "    return t\n",
        ["python3", "extratos_tela.py"],
    ),
    (
        "juntar as parcelas volta a esconder cada lancamento",
        "extratos_tela.py",
        '        d["itens"] = list(d.get("itens") or []) + list(item.get("itens") or [])\n',
        "",
        ["python3", "extratos_tela.py"],
    ),
    (
        "salvar em massa volta a apagar a resposta do outro sentido",
        "favorecidos.py",
        '            k = (chave(l.get("favorecido")),\n                 str(l.get("tipo") or "saida").strip().lower() or "saida")\n',
        '            k = (chave(l.get("favorecido")), "saida")\n',
        ["python3", "favorecidos.py"],
    ),
    (
        "a celula vazia da fila volta a gravar 'nan' como finalidade",
        "extratos_tela.py",
        '        fin = fin.strip() if isinstance(fin, str) else ""\n',
        '        fin = str(fin or "").strip()\n',
        ["python3", "extratos_tela.py"],
    ),
    (
        "a finalidade em massa deixa de valer para os marcados",
        "extratos_tela.py",
        "        if not fin and l.get(\"marcar\") is True and massa:\n",
        "        if False:\n",
        ["python3", "extratos_tela.py"],
    ),
    (
        "nome curto do custo fixo volta a casar com qualquer descricao",
        "custo_real.py",
        '    if len(_fv.chave(item).replace(" ", "")) >= NOME_MINIMO:\n',
        "    if True:\n",
        ["python3", "custo_real.py"],
    ),
    (
        "o custo fixo volta a exigir a coluna preenchida para casar pelo nome",
        "custo_real.py",
        "    nomes = nomes_do_item(linha)\n",
        "    nomes = apelidos(linha)\n",
        ["python3", "custo_real.py"],
    ),
    (
        "o nome do item volta a alargar a coluna que o dono preencheu",
        "custo_real.py",
        "    if nomes:\n        return nomes\n",
        "",
        ["python3", "custo_real.py"],
    ),
    (
        "a fatura confirmada volta a nao atualizar o custo fixo do mes",
        "extratos_tela.py",
        "            st.success(_msg)\n            _conferir_custo_real(classificados)\n",
        "            st.success(_msg)\n",
        ["python3", "extratos_tela.py"],
    ),
    # ── 07/10: A BARRA DE PENALIDADE CHEIA COM ZERO, E A TV CORTANDO METAS ──
    (
        "a barra de penalidade volta a encher sem penalidade nenhuma",
        "placar_core.py",
        "        pct = min(q / t * 100.0, 100.0)\n",
        "        pct = 100.0\n",
        ["python3", "placar_core.py"],
    ),
    (
        "a TV volta a cortar as ultimas linhas das metas",
        "placar.py",
        "      if (ult) {{ need = Math.max(need, ult.offsetTop + ult.offsetHeight + 8); }}\n",
        "      if (ult) {{ need = 0; }}\n",
        ["python3", "placar_core.py"],
    ),
    (
        "a Analise de Metas volta a ter a propria conta da barra de penalidade",
        "analise_metas.py",
        "    pct_pen_n, txt_pen_n = _pc.barra_penalidades(pen_qtd, max_pen_n)\n",
        "    pct_pen_n, txt_pen_n = min(pen_qtd / (max_pen_n + 1) * 100, 100), \"\"\n",
        ["python3", "placar_core.py"],
    ),
    (
        "Assinaturas volta a ficar fora do Operacional",
        "gestao.py",
        '        _abrir_tela("assinaturas_tela", usuario_logado)\n',
        "        pass\n",
        ["python3", "checar_tela.py"],
    ),
    # ── 07/10: O LPV DO MÊS CORRENTE PELA PROJEÇÃO DE VENDAS ────────────
    (
        "o LPV vigente volta a ignorar a projecao do mes",
        "financeiro.py",
        "    proj = lpv_do_mes_projetado(hoje)\n",
        "    proj = None\n",
        ["python3", "financeiro.py"],
    ),
    (
        "o LPV projetado volta a nao ler a projecao digitada",
        "lpv_mensal.py",
        "    vendas = _mg.projecao_vendas(ano, mes)\n",
        "    vendas = 0.0\n",
        ["python3", "lpv_mensal.py"],
    ),
    (
        "a aba antiga da meta volta a esconder a coluna da projecao",
        "meta_gastos.py",
        "    if [c for c in COLUNAS if c not in cab]:\n",
        "    if False:\n",
        ["python3", "meta_gastos.py"],
    ),
    (
        "o Salvar da meta volta a perder a projecao",
        "meta_gastos_tela.py",
        "usuario=usuario_logado, projecao=_proj)",
        "usuario=usuario_logado)",
        ["python3", "checar_tela.py"],
    ),
    (
        "a TV volta a medir a caixa esticada e o bloco cresce a cada minuto",
        "placar.py",
        "      if (ult) {{ need = Math.max(need, ult.offsetTop + ult.offsetHeight + 8); }}\n",
        "      need = Math.max(need, bb.children[i].scrollHeight || 0);\n",
        ["python3", "placar_core.py"],
    ),
    (
        "o equilibrio volta a ser custo fixo dividido pela margem do mes",
        "home_gestao.py",
        "            \"operacional\": _eq_meta,\n",
        "            \"operacional\": comp.get(\"equilibrio_hoje\"),\n",
        ["python3", "home_gestao.py"],
    ),
    (
        "o equilibrio volta a ignorar a meta de gastos",
        "equilibrio_caixa.py",
        "    return round(meta / mb, 2)\n",
        "    return round(meta, 2)\n",
        ["python3", "equilibrio_caixa.py"],
    ),
    (
        "a Monique volta a sumir dos gestores ja gravados",
        "folha_salarial.py",
        "    df, _faltando = com_gestores_pedidos(df)\n",
        "    _faltando = []\n",
        ["python3", "checar_tela.py"],
    ),
    # ── 07/10: COLUNA CONFIGURADA OU EXCLUÍDA CONTINUAVA NO AVISO E NA TV ──
    (
        "o aviso de coluna volta a comparar a grafia exata",
        "analise_metas.py",
        "    novas = _pc.colunas_sem_config(do_board, salvas)\n",
        "    novas = [c for c in do_board if c not in _pc.COLUNAS_CONFIG and c not in salvas]\n",
        ["python3", "placar_core.py"],
    ),
    (
        "a configuracao de coluna volta a nao reconhecer outra grafia",
        "placar_core.py",
        "        if n in COLUNAS_CONFIG or n in (salvas or {}) or chave_coluna(n) in chaves:\n",
        "        if n in COLUNAS_CONFIG or n in (salvas or {}):\n",
        ["python3", "placar_core.py"],
    ),
    (
        "a TV volta a desenhar com as metas guardadas por 10 minutos",
        "placar.py",
        '    for _mod, _fn in (("metas_config", "carregar_todas"),\n',
        '    for _mod, _fn in (("metas_config_x", "carregar_todas"),\n',
        ["python3", "placar_core.py"],
    ),
    (
        "o previsto do cartao volta a ignorar as compras ja lancadas",
        "previsto.py",
        '    if prev.get("FATURA DO CARTÃO") and cartao_detalhado:\n',
        "    if False:\n",
        ["python3", "previsto.py"],
    ),
    (
        "o quadro da Home volta a combinar sem as compras do cartao",
        "home_gestao.py",
        "    combinado, total = _pv.combinar(res, prev, cartao_detalhado)\n",
        "    combinado, total = _pv.combinar(res, prev)\n",
        ["python3", "home_gestao.py"],
    ),
    (
        "o C.O volta a pôr a compra do cartao no mes da compra",
        "lpv_mensal.py",
        "        do_mes = [l for l in do_ano_todo if _lan.mes_de(l) == alvo]\n",
        '        do_mes = [l for l in do_ano_todo if str(l.get("data", "")).startswith(alvo)]\n',
        ["python3", "lpv_mensal.py"],
    ),
    (
        "a fatura volta a lancar sem o mes do vencimento",
        "extratos_tela.py",
        "        _novos, _reps, _marc, _err = _lan_fat.gravar_fatura(\n            classificados, _conta_fat, _comp, usuario_logado)\n",
        "        _novos, _reps, _marc, _err = (*_lan_fat.gravar(\n            classificados, _conta_fat, usuario_logado)[:2], 0, '')\n",
        ["python3", "extratos_tela.py"],
    ),
    # ── 06/10: AS TRES VOZES SOBRE O CENARIO, E A REFACAO QUE PERDIA A ──
    # ── REFERENCIA. Os dois achados do ChatGPT que seguiam abertos.
    (
        "a luz e os materiais da referencia voltam a concorrer com a "
        "direcao de arte",
        "ambientacao_ref.py",
        "    if tem_direcao_de_arte:\n        linhas.append(\n",
        "    if False:\n        linhas.append(\n",
        ["python3", "ambientacao_ref.py"],
    ),
    (
        "o cenario da visao volta a morrer com a passada da geracao",
        "imagem.py",
        "        if _txt:\n            with _TRAVA_CENARIO_VIGENTE:\n",
        "        if False:\n            with _TRAVA_CENARIO_VIGENTE:\n",
        ["python3", "imagem.py"],
    ),
    (
        "o refazer volta a montar a ambientacao crua, sem o cenario escolhido",
        "imagem.py",
        "        ambientacao=ambientacao_do_tipo(cfg, tipo),\n"
        "        direcao_arte=_direcao_de_arte_da_sessao(),\n",
        '        ambientacao=cfg.get("ambientacao", ""),\n'
        "        direcao_arte=_direcao_de_arte_da_sessao(),\n",
        ["python3", "imagem.py"],
    ),
    (
        "o lote novo deixa de apagar o cenario do lote anterior",
        "imagem.py",
        "    with _TRAVA_CENARIO_VIGENTE:\n"
        "        for _k in [k for k in _CENARIO_VIGENTE if k[0] == _p]:\n"
        "            _CENARIO_VIGENTE.pop(_k, None)\n",
        "    with _TRAVA_CENARIO_VIGENTE:\n        pass\n",
        ["python3", "imagem.py"],
    ),
    # ── 07/10: AS VARIACOES DO MESMO PRODUTO ───────────────────────────
    (
        "a geometria volta para a peca cuja regra manda o contrario",
        "imagem.py",
        "    if not blocos or n in (1, 4, 5, 8):\n",
        "    if not blocos or n in (1, 4, 8):\n",
        ["python3", "imagem.py"],
    ),
    (
        "o bloco de geometria para de dizer que nao vira texto na imagem",
        "imagem.py",
        '        "- ESTE BLOCO É INSTRUÇÃO DE ONDE PÔR AS COISAS, E NUNCA TEXTO A\\n"\n',
        '        "- Posicione os elementos conforme abaixo.\\n"\n',
        ["python3", "imagem.py"],
    ),
    (
        "duas triagens com variacao voltam a escolher a primeira",
        "imagem.py",
        "    if len(_com_var) > 1:\n",
        "    if False:\n",
        ["python3", "imagem.py"],
    ),
    (
        "a foto anexada na aba deixa de vencer a da triagem",
        "imagem.py",
        '    _anexadas = list(_dados.get("fotos_bytes") or [])\n',
        "    _anexadas = []\n",
        ["python3", "imagem.py"],
    ),
    (
        "o cache das fotos do Drive some, e cada peca volta a baixar de novo",
        "imagem.py",
        "        if _em_cache:\n            _fora.append(_em_cache)\n",
        "        if False:\n            _fora.append(_em_cache)\n",
        ["python3", "imagem.py"],
    ),
    (
        "o auto-confirmar da proxima variacao volta a disparar a cada rerun",
        "imagem.py",
        'if st.session_state.pop("img_var_autoconfirmar", False):\n',
        'if st.session_state.get("img_var_autoconfirmar", False):\n',
        ["python3", "imagem.py"],
    ),
    (
        "a leitura das variacoes da triagem volta a estourar com JSON ruim",
        "triagem.py",
        "        try:\n            itens = json.loads(texto)\n        except Exception:\n            return []\n",
        "        itens = json.loads(texto)\n",
        ["python3", "triagem.py"],
    ),
    (
        "o bloco de variacao volta a ser removido por indice, e embaralha",
        "triagem.py",
        '    st.session_state[_VAR_IDS] = [i for i in _ids_das_variacoes() if i != vid]\n',
        "    st.session_state[_VAR_IDS] = _ids_das_variacoes()[:-1]\n",
        ["python3", "triagem.py"],
    ),
    (
        "o produto seguinte volta a herdar as variacoes do anterior",
        "triagem.py",
        "        st.session_state.pop(_k, None)\n    _zerar_variacoes()\n",
        "        st.session_state.pop(_k, None)\n",
        ["python3", "triagem.py"],
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

    # ANTES DE MUTAR QUALQUER COISA: os comandos conseguem reprovar?
    #
    # Entrada cujo comando sai 0 sempre esta verde por acidente, e verde por
    # acidente e pior que vermelho: ele conta como guarda e nao e.
    _sem_codigo = comandos_sem_codigo_de_saida()
    if _sem_codigo:
        falhas += 1
        _tot = sum(n for _, n, _ in _sem_codigo)
        print(f"FALHA  {_tot} mutacao(oes) apontam para modulo que NUNCA "
              f"reprova — elas estao verdes por acidente:")
        for _m, _n, _por in _sem_codigo:
            print(f"         {_n:3}x  {_m} — {_por}")
        print("       Termine o auto-teste com "
              "`sys.exit(1 if falhas else 0)`.")

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


def comandos_sem_codigo_de_saida():
    """[(modulo, n)] cujos comandos NUNCA reprovam: saem 0 sempre.

    O BURACO QUE ESCONDIA 64 MUTACOES — achado em 01/10.

    Este verificador decide "a guarda viu o defeito?" pelo CODIGO DE SAIDA do
    comando. Mas o auto-teste de quase todo modulo desta base imprime
    "falhas: N" e termina sem chamar `sys.exit` — ou seja, sai 0 mesmo
    reprovando. Para ca, esses modulos nunca falham: a mutacao passa, a
    entrada fica VERDE, e ninguem mede nada.

    Eram 33 entradas apontadas para o `imagem.py` e mais 31 para outros
    cinco modulos. 64 das 122 — mais da metade.

    Apareceu por acidente: escrevi uma guarda nova, reintroduzi o defeito, e
    li "falhas: 2" na tela E "verde" no veredito, na mesma rodada.

    E o CLAUDE.md ja registrava a doenca, pelo lado espelhado: o
    `varredura_formas.py` saia com 1 SEMPRE, porque alguem somou com `and`
    uma contagem e um booleano. La o verde era impossivel; aqui o vermelho
    era. Nos dois casos, o defeito era ninguem ler o codigo de saida.

    Esta guarda fecha a classe: entrada cujo comando nao consegue reprovar
    nao e entrada, e reprova o verificador em vez de mentir para ele.
    """
    import collections
    usados = collections.Counter()
    for ent in MUTACOES:
        cmd = ent[-1]
        if len(cmd) >= 2 and cmd[0] == "python3" and cmd[1].endswith(".py"):
            usados[cmd[1]] += 1
    fora = []
    for mod, n in sorted(usados.items()):
        caminho = os.path.join(RAIZ, mod)
        if not os.path.exists(caminho):
            fora.append((mod, n, "o modulo nem existe"))
            continue
        fonte = open(caminho, encoding="utf-8").read()
        corpo = fonte.split('if __name__ == "__main__":')[-1]
        if "falhas:" not in corpo:
            continue        # nao e auto-teste com contagem; nada a exigir
        # `SystemExit` CONTA, e isto era alarme falso.
        #
        # A condicao procurava "exit(" em minusculas. `raise SystemExit(1 if
        # falhas else 0)` — que e o que o `financeiro.py` usa — tem "Exit("
        # com E maiusculo, e passava batido: a varredura acusava um modulo
        # que estava certo. Guarda que acusa o inocente ensina a ignora-la, e
        # isso ja custou caro nesta base.
        if ("sys.exit" in corpo or "exit(" in corpo
                or "SystemExit" in corpo):
            continue
        fora.append((mod, n, "imprime 'falhas:' e sai com 0 sempre"))

    # ── E A VARREDURA VALE PARA TODO MODULO, nao so para os que alguma
    #    mutacao aponta ──────────────────────────────────────────────────
    #
    # A varredura acima olha `usados` — os modulos que alguma entrada desta
    # lista manda rodar. Tres modulos do diff de 06/10 passaram por fora dela
    # exatamente por isso: `favorecidos.py`, `folha_salarial.py` e
    # `headcount.py` tem auto-teste e nenhuma mutacao aponta para eles. E a
    # Forma 1 aplicada ao proprio verificador: a regra nao e "quem esta nesta
    # lista", e sim "quem tem auto-teste".
    #
    # SAO DUAS REDES, E BASTA UMA. `conferir._reprovou` e o `_reprovou` daqui
    # reprovam por CODIGO DE SAIDA **ou** pela palavra FALHA na saida. Medido
    # em 06/10: dos 74 modulos com auto-teste, 34 nao tem codigo de saida (e
    # todos imprimem FALHA) e 7 nao imprimem FALHA (e todos tem codigo). Zero
    # ficam sem nenhuma das duas — e e isso que esta guarda trava.
    import re as _re_rede
    for _n_mod in sorted(os.listdir(RAIZ)):
        if not _n_mod.endswith(".py") or _n_mod.startswith("checar_"):
            continue
        try:
            _f_mod = open(os.path.join(RAIZ, _n_mod), encoding="utf-8").read()
        except Exception:
            continue
        if 'if __name__ == "__main__":' not in _f_mod:
            continue
        _c_mod = _f_mod.split('if __name__ == "__main__":')[-1]
        if "falhas:" not in _c_mod:
            continue
        _tem_saida = ("sys.exit" in _c_mod or "exit(" in _c_mod
                      or "SystemExit" in _c_mod)
        _tem_falha = bool(_re_rede.search(r'["\']FALHA', _c_mod))
        if not _tem_saida and not _tem_falha:
            fora.append((_n_mod, 0,
                         "auto-teste SEM REDE: nao sai com codigo != 0 nem "
                         "imprime FALHA — quem reprova nele passa batido"))
    return fora


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
