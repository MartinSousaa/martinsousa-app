"""Monta CODIGO_GERACAO_DE_IMAGEM.txt a partir do codigo em producao.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
O `.gitignore` dizia, desde 01/10, que a exportacao nao e commitada porque
*"quando precisar de novo, gere de novo: a extracao le o codigo em producao e
reprova se algum nome pedido nao existir mais"*. So que a extracao NAO EXISTIA
no repositorio — ela tinha sido escrita e jogada fora. Na vez seguinte em que
o dono pediu os arquivos atualizados, tive de reescrever o extrator inteiro do
zero, lendo os cabecalhos do .txt velho para descobrir quais nomes entravam em
cada secao. Comentario que promete uma ferramenta inexistente custa a mesma
hora toda vez.

COMO ELE EXTRAI
---------------
Por AST: nome -> primeira e ultima linha do bloco, e o recorte sai do arquivo
real. Nunca por busca de texto. Nome pedido que sumiu do codigo REPROVA a
exportacao em vez de sair faltando em silencio — era esse o combinado.

USO
---
    python3 exportar_codigo_de_imagem.py              grava o .txt
    python3 exportar_codigo_de_imagem.py --autoteste  so confere, nao grava
"""
import ast, io, os, re, sys, unicodedata

# Valor de secret e uma STRING LITERAL. `api_key = _chave_anthropic()` e uma
# CHAMADA, e exporta-la e correto — a primeira versao desta guarda acusava a
# chamada e reprovava a exportacao inteira. Alarme falso ensina a ignorar o
# verificador, entao ela so pega literal. O autoteste prova os dois lados.
LITERAL_DE_SECRET = re.compile(
    r"""(?ix)
    (?: (?:api[_-]?key|apikey|token|secret|senha|password|chave)
        \s* [:=] \s* ['"][^'"]{8,}['"] )
    | (?: ['"]sk-[A-Za-z0-9_\-]{16,}['"] )
    | (?: ['"]AIza[A-Za-z0-9_\-]{20,}['"] )
    """)

# A raiz sai do PROPRIO arquivo. Caminho absoluto escrito a mao quebra no
# container do Railway, que nao monta o repositorio no mesmo lugar.
RAIZ = os.path.dirname(os.path.abspath(__file__))

SECOES = [
    ("O PROMPT DO PLANO (a IA que escreve a copy e decide a cena)", "imagem.py", [
        "divergencia_de_produto", "plano_misturado", "gerar_triagem_ia",
        "tipo_canonico", "numero_do_tipo", "plano_do_tipo",
        "blocos_sem_repeticao", "faces_repetidas", "cenas_repetidas",
        "pecas_bloqueadas_da_geracao", "plano_da_geracao",
        # A copy corrigida que sobrevive a refacao (05/10).
        "_COPY_VIGENTE", "_produto_da_copy", "guardar_copy_vigente",
        "copy_vigente", "esquecer_copy_vigente",
        # O cenario lido das referencias de ambientacao, que sobrevive a
        # passada para que o refazer use a MESMA referencia (06/10). Quem le
        # o export precisa dos tres: sem o escritor nao se ve QUANDO o
        # cenario e escolhido, e foi "nao sei quando isto roda" que fez a
        # analise de fora apontar defeito em caminho que nao existia mais.
        "_CENARIO_VIGENTE", "guardar_cenarios_da_geracao",
        "cenario_vigente", "ambientacao_do_tipo",
    ]),
    ("AS MEDIDAS DE CADA PECA (fonte unica de tamanho e densidade)", "imagem.py", [
        # A REGUA DA CENA (07/10): numero sozinho nao e escala, e as pecas
        # de cena sairam com a fita de 1,2 cm do tamanho de fita crepe.
        "LARGURA_CARTAO_CM", "_medidas_em_cm", "regua_da_cena",
        # A TRAVA DE CONTRASTE (07/10): a paleta mandava escrever texto numa
        # cor de 1,63:1, e o "sim" da peca 6 saiu invisivel.
        "_PISO_CONTRASTE_TEXTO", "_luminancia", "contraste",
        "cor_serve_para_texto",
        "OCUPACAO", "BLOCOS", "faixa_de_blocos", "blocos_em_portugues",
        "faixa_de_ocupacao", "medida_da_ocupacao",
        "ocupacao_em_portugues", "ocupacao_em_ingles",
        "TIPOS_DE_CENA", "protagonismo_do_tipo", "PALAVRAS_TITULO",
        "PALAVRAS_FRASE", "medida_do_bloco", "modo_fundo_do_tipo",
    ]),
    ("OS TEXTOS FIXOS QUE ENTRAM NO PROMPT", "imagem.py", [
        "PADRAO_VISUAL", "DIRECAO_A_DEDUZIR", "DIRECAO_JA_DECIDIDA",
        "padrao_visual", "sem_medida_de_quadro", "INSTRUCAO_PROTAGONISMO",
        "INSTRUCAO_PROTAGONISMO_AMBIENTE", "APOIO_AMBIENTE", "APOIO_USO",
        "APOIO_PRESENTE", "INSTRUCAO_PROTAGONISMO_CAPA",
        "INSTRUCAO_FIDELIDADE_ABERTURA", "INSTRUCAO_FIDELIDADE_SO_CRIACAO",
        "_FIDELIDADE_ESTRUTURAL", "INSTRUCAO_FIDELIDADE",
        "INSTRUCAO_FIDELIDADE_NUCLEO", "INSTRUCAO_COMPOSICAO",
        "INSTRUCAO_PROPORCAO", "INSTRUCAO_LAYOUT_MARKETING",
        "INSTRUCAO_PERSONALIZADO", "INSTRUCAO_AJUSTE_FINO", "PRESETS",
        "NOME_FORMATO", "_SINONIMOS_TIPO", "_EM_PORTUGUES",
        "INSTRUCAO_REFERENCIA_LAYOUT", "_trava_cor_produto",
        "bloco_texto_exato", "MARCA_TEXTO_EXATO", "MARCA_FIM_TEXTO_EXATO",
        "trocar_texto_exato", "bloco_direcao_de_arte", "preset_do_tipo",
        "ANGULOS", "_ESQUEMA_CONFERENCIA", "_ESQUEMA_TEXTO",
        # A peca sem copy, e a contagem de blocos num dono so (05/10).
        "MARCA_SEM_COPY", "_sincronizar_contagem",
        # A geometria calculada, em pixels (05/10).
        "LADO_GERADO_PX", "FOLGA_BORDA_PCT", "CORREDOR_PCT", "em_px",
        "zonas_da_peca",
        # As duas decisoes que tem dono: tamanho e posicao.
        "sem_posicao_de_layout", "sem_decisao_do_compilador",
    ]),
    ("A MONTAGEM DO PROMPT DA IMAGEM", "imagem.py", [
        "motivos_para_descartar_layout", "esquecer_descarte_de_layout",
        "limpar_descricao_de_layout", "normalizar_imagem",
        "fotos_para_o_motor", "montar_prompt_imagem",
        "prompt_que_sera_enviado", "prompt_de_cada_peca", "txt_dos_prompts",
        "montar_prompt_ajuste_fino",
    ]),
    ("O ENVIO AOS MOTORES (OpenAI e Gemini)", "imagem.py", [
        "_resposta_sem_credito", "_chamar_gemini_geracao_texto",
        "MODELO_IMAGEM_PADRAO", "MODELOS_IMAGEM_CONHECIDOS",
        "marcar_modelo_invalido", "modelo_de_imagem", "capacidade_do_motor",
        "modelos_de_imagem_da_conta", "_e_modelo_inexistente",
        "redescobrir_modelo_de_imagem", "_modelo_nao_existe",
        "parametro_recusado", "_erro_openai_terminal",
        "_chamar_openai_geracao", "gerar_imagem_ia",
        # O ORCAMENTO DE TEMPO DA PECA (06/10). Subir o timeout do Gemini sem
        # subir o teto por peca so troca a mensagem de erro.
        "GEMINI_TIMEOUT_S", "TENTATIVAS_GEMINI", "FOLGA_ENTRE_TENTATIVAS_S",
        "FOLGA_DO_PRIMARIO_S", "orcamento_da_peca", "TETO_POR_PECA_S",
    ]),
    ("A CONFERENCIA DA PECA PRONTA", "imagem.py", [
        "conferir_texto", "_PERGUNTAS_DA_PECA", "pergunta_do_tamanho",
        "perguntas_da_peca", "conferir_peca", "peca_em_aviso",
        "revisar_peca", "revisar_tudo", "revisar_texto", "relato_em_texto",
        "_relato_base",
        # As barreiras de claim e de medida inventada (05/10).
        "TERMOS_DE_PROMESSA", "promessas_sem_lastro", "copy_sem_promessa",
        "_NUMERO_COM_UNIDADE", "medidas_sem_lastro",
        "copy_sem_medida_inventada",
        # O ajuste fino, que e por onde o chat passa.
        "_ajustar_bruto", "ajustar_com_conferencia", "cor_do_produto_atual",
        "classificar_edicao", "prompt_para_regerar",
    ]),
    ("A LEITURA DAS REFERENCIAS DE AMBIENTACAO", "ambientacao_ref.py", [
        "_ESQUEMA", "descrever", "resumo",
        # O teto de tokens e o salvamento do JSON cortado (05/10).
        "TOKENS_POR_REFERENCIA", "TOKENS_DE_ABERTURA", "teto_de_tokens",
        "cenarios_inteiros",
    ]),
    ("AS PECAS DE APOIO QUE O MOTOR USA (06/10: estavam faltando no .txt)", "imagem.py", [
        # Leitura do produto e da sessao
        "_descrever_produto_via_claude", "_descricao_do_produto_cacheada",
        "_direcao_de_arte_da_sessao", "config_da_geracao",
        "limpar_trava_do_produto", "_numeros_do_cadastro",
        "_chave_tipo", "_normalizar_nome", "_sem_acento", "_palavras_uteis",
        "_acha_radicais",
        # As fotos indo para o motor
        "_detectar_mime", "_tem_transparencia", "extensao_de", "_data_url",
        "_arquivo_para_openai", "_bloco_imagem", "comprimir_para_limite",
        "_assinatura_das_fotos",
        # As chaves (NENHUM valor de secret entra: o exportador so copia
        # chamada, e a guarda de literal reprova se algum valor aparecer)
        "_chave_anthropic", "_get_openai_api_key", "_get_gemini_api_key",
        # Regras da peca que o prompt usa
        "pode_ter_texto", "regra_de_espaco", "medida_do_callout",
        "instrucao_de_layout", "ref_layout_do_tipo", "_pontuar_ref",
        # O ajuste fino e a conferencia dele
        "conferir_ajuste", "eh_rotulo_de_ajuste", "_pedido_fala_de_cor",
        "peca_em_ajuste",
    ]),
]

INTEIROS = [
    ("O ENQUADRAMENTO DEPOIS DA GERACAO", "enquadrar.py"),
    ("A REGUA GEOMETRICA DA PECA PRONTA", "medir_imagem.py"),
]


def blocos_do_arquivo(arq):
    """nome -> (primeira linha, ultima linha), para def/class/atribuicao."""
    fonte = open(os.path.join(RAIZ, arq), encoding="utf-8").read()
    arvore = ast.parse(fonte)
    mapa = {}
    for no in arvore.body:
        nomes = []
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nomes = [no.name]
        elif isinstance(no, ast.Assign):
            nomes = [a.id for a in no.targets if isinstance(a, ast.Name)]
        elif isinstance(no, ast.AnnAssign) and isinstance(no.target, ast.Name):
            nomes = [no.target.id]
        for nome in nomes:
            if nome in mapa:        # redefinicao: fica a primeira
                continue
            ini = min([no.lineno] + [d.lineno for d in
                                     getattr(no, "decorator_list", [])])
            mapa[nome] = (ini, no.end_lineno)
    return fonte.splitlines(), mapa


def sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFD", t)
                   if unicodedata.category(c) != "Mn")


def montar():
    """Devolve (texto, nomes faltando, linhas suspeitas de secret)."""
    saida = io.StringIO()
    w = saida.write
    barra = "=" * 78
    traco = "-" * 78
    w(barra + "\n")
    w("MS STUDIO — TODA A CODIFICACAO QUE MONTA E ENVIA O PROMPT DE IMAGEM\n")
    w(barra + "\n\n")
    w("Gerado automaticamente a partir do codigo em producao.\n")
    w("Cada bloco traz arquivo:linha para conferencia.\n\n")
    # ── O CARIMBO: DATA E COMMIT ────────────────────────────────────────
    #
    # Em 05/10 mandei ao dono um .txt gerado tres dias antes. O ChatGPT leu e
    # reapontou QUATRO coisas que ja estavam corrigidas — e ninguem tinha como
    # saber que o arquivo era velho olhando para ele. Com o carimbo, basta
    # comparar com o `git log` para ver se a copia envelheceu.
    import subprocess as _sp_h
    try:
        _sha = _sp_h.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ,
                         capture_output=True, text=True, timeout=20
                         ).stdout.strip() or "(sem git)"
        _assunto = _sp_h.run(["git", "log", "-1", "--format=%s"], cwd=RAIZ,
                             capture_output=True, text=True, timeout=20
                             ).stdout.strip()
    except Exception:
        _sha, _assunto = "(sem git)", ""
    # A HORA VEM COM FUSO. `datetime.now()` cru devolve UTC no container do
    # Railway: o carimbo sairia 3h adiantado e, depois das 21h, com a DATA
    # errada — num campo cuja unica funcao e dizer quando a copia foi feita.
    # `checar_alcance` pegou isto no mesmo dia em que o carimbo foi escrito.
    import placar_core as _pc_h
    w(f"Gerado em: {_pc_h.agora_br().strftime('%d/%m/%Y %H:%M')} (horario de "
      f"Brasilia)\n")
    w(f"Commit:    {_sha}  {_assunto[:70]}\n")
    w("Se o commit acima nao for o ultimo do repositorio, esta copia "
      "ENVELHECEU — gere de novo com\n`python3 "
      "exportar_codigo_de_imagem.py` antes de analisar qualquer coisa.\n\n")

    faltando = []
    cache = {}
    for titulo, arq, nomes in SECOES:
        if arq not in cache:
            cache[arq] = blocos_do_arquivo(arq)
        linhas, mapa = cache[arq]
        w("\n" + barra + "\n")
        w(sem_acento(titulo) + "\n(" + arq + ")\n")
        w(barra + "\n\n")
        for nome in nomes:
            if nome not in mapa:
                faltando.append((arq, nome))
                continue
            ini, fim = mapa[nome]
            w(traco + "\n")
            w("%s:%d  %s\n" % (arq, ini, nome))
            w(traco + "\n")
            w("\n".join(linhas[ini - 1:fim]) + "\n\n")

    for titulo, arq in INTEIROS:
        w("\n" + barra + "\n")
        w(sem_acento(titulo) + "\n(" + arq + ")\n")
        w(barra + "\n\n")
        w(open(os.path.join(RAIZ, arq), encoding="utf-8").read().rstrip() + "\n")

    texto = saida.getvalue()

    # Guarda de conteudo: nenhum valor de secret pode sair daqui.
    suspeitas = []
    for n, l in enumerate(texto.splitlines(), 1):
        if LITERAL_DE_SECRET.search(l):
            suspeitas.append((n, l.strip()[:100]))
    return texto, faltando, suspeitas


# ── O QUE O MOTOR ALCANCA, E QUE PRECISA ESTAR NA LISTA ──────────────────
#
# A LISTA ESCRITA A MAO SO REPROVAVA UM LADO. Nome pedido que sumiu do codigo
# reprova a exportacao — esse era o combinado, e funciona. Mas nome NOVO,
# criado depois de a lista ser escrita, sai faltando EM SILENCIO.
#
# Medido em 06/10: o .txt entregue ao dono nao tinha `TETO_POR_PECA_S`,
# `_COPY_VIGENTE`, nem o `dados_descricao` dos tres ajustes do chat — tres
# correcoes feitas no dia anterior. Ja tinha custado antes: em 05/10 mandei
# um .txt velho e o ChatGPT reapontou QUATRO itens que ja estavam corrigidos.
#
# Entao a guarda pergunta ao CODIGO quem o motor alcanca, por AST, a partir
# das portas de entrada — e exige que cada nome esteja na lista ou na isencao,
# com motivo escrito.
PORTAS_DO_MOTOR = ("gerar_imagem_ia", "montar_prompt_imagem",
                   "montar_prompt_ajuste_fino", "revisar_tudo",
                   "ajustar_com_conferencia", "prompt_para_regerar")

# Alcancado pelo motor e FORA do .txt de proposito, com o motivo.
FORA_DE_PROPOSITO = {
    # Infraestrutura, nao e o motor: limitador de chamada, log, contexto.
    "_GEMINI_LIMITER", "_LIMITE_GEMINI", "_hoje_br", "_sys", "_time",
    # Tela: o .txt e sobre o prompt e o envio, nao sobre o desenho.
    "pagina_imagem", "st",
    # NAO SAO FUNCOES DESTE ARQUIVO: sao metodos de objeto e nomes de modulo
    # que a varredura por nome de chamada apanha junto. `json.loads`,
    # `BytesIO.getvalue`, `chaves.ler`, `_GEMINI_LIMITER.aguardar`, `list`.
    "json", "list", "getvalue", "ler", "aguardar",
    # `create` e `cliente.messages.create`, metodo do SDK da Anthropic. Ele
    # so passou a ser apanhado em 07/10 porque o auto-teste ganhou um duplo
    # com um metodo de mesmo nome — a varredura casa por NOME de chamada, e
    # o duplo deu nome a uma chamada que nunca teve dono neste arquivo.
    "create",
    # FUNCOES ANINHADAS: ja saem DENTRO do bloco da funcao que as contem, e
    # exporta-las a parte seria o mesmo codigo duas vezes no .txt. Conferido
    # em 06/10, uma a uma (a mae de cada uma esta exportada):
    #   _tenta   -> comprimir_para_limite      _cor     -> bloco_direcao_de_arte
    #   _extrair -> _chamar_openai_geracao     _lista   -> bloco_direcao_de_arte
    #   _falha   -> gerar_imagem_ia            _chave   -> blocos_sem_repeticao
    #   _texto_do_campo -> montar_prompt_imagem
    #   _diz     -> revisar_peca
    "_tenta", "_extrair", "_falha", "_cor", "_lista", "_chave",
    "_texto_do_campo", "_diz",
}


def nomes_alcancados_pelo_motor(arq="imagem.py"):
    """Todo nome de funcao que as portas do motor alcancam, por AST."""
    fonte = open(os.path.join(RAIZ, arq), encoding="utf-8").read()
    arv = ast.parse(fonte)
    defs = {}
    for no in ast.walk(arv):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defs.setdefault(no.name, no)

    def chamadas(fn):
        return {getattr(x.func, "attr", "") or getattr(x.func, "id", "")
                for x in ast.walk(fn) if isinstance(x, ast.Call)}

    vistos, fila = set(), [p for p in PORTAS_DO_MOTOR if p in defs]
    while fila:
        c = fila.pop()
        if c in vistos:
            continue
        vistos.add(c)
        if c in defs:
            fila += [n for n in chamadas(defs[c]) if n]
    return {n for n in vistos if n in defs}


def _autoteste():
    """Confere a exportacao SEM gravar. E a guarda de conteudo, nao de sintaxe."""
    falhas = 0

    def ok(titulo, cond):
        nonlocal falhas
        print(("  ok   " if cond else "  FALHA ") + titulo)
        if not cond:
            falhas += 1

    # ── NOME QUE O MOTOR ALCANCA E NAO ESTA NA LISTA ────────────────────
    pedidos = set()
    for _t, _a, _ns in SECOES:
        pedidos.update(_ns)
    alcancados = nomes_alcancados_pelo_motor()
    de_fora = sorted(alcancados - pedidos - FORA_DE_PROPOSITO)
    ok("nenhum nome do motor ficou de fora da lista (%d de fora)"
       % len(de_fora), not de_fora)
    for _n in de_fora[:20]:
        print(f"         falta exportar (ou isentar com motivo): {_n}")

    texto, faltando, suspeitas = montar()
    ok("todo nome pedido existe no codigo (%d faltando)" % len(faltando),
       not faltando)
    ok("nenhum valor de secret no texto exportado (%d suspeita(s))"
       % len(suspeitas), not suspeitas)
    ok("o texto exportado tem corpo (>3000 linhas)",
       len(texto.splitlines()) > 3000)

    # A GUARDA DE SECRET E CONFERIDA POR MUTACAO.
    #
    # A primeira versao dela acusava `api_key = _chave_anthropic()` — uma
    # CHAMADA, nao um valor — e reprovava a exportacao inteira. Alarme falso
    # ensina a ignorar o verificador. Valor de secret e uma STRING LITERAL, e
    # e isso que ela tem de separar; estes casos provam os dois lados.
    for amostra, esperado in (
            ('api_key = "sk-proj-ABCDEFGHIJKLMNOPQRSTUV"', True),
            ('OPENAI_TOKEN = "abcdefghijklmnop"', True),
            ('X = "AIzaSyA1234567890abcdefghijklmnopqrs"', True),
            ('api_key = _chave_anthropic()', False),
            ('api_key = _get_gemini_api_key()', False),
            ('    chave = os.environ["X"]', False)):
        ok("secret: %r -> %s" % (amostra[:46], esperado),
           bool(LITERAL_DE_SECRET.search(amostra)) is esperado)

    # O arquivo inteiro dos dois modulos copiados integralmente tem de estar
    # la: foi secao inteira que ja saiu vazia por engano de recorte.
    for arq in ("enquadrar.py", "medir_imagem.py"):
        corpo = open(os.path.join(RAIZ, arq), encoding="utf-8").read()
        ok("%s foi copiado inteiro" % arq,
           corpo.rstrip() and corpo.rstrip() in texto)

    print("falhas:", falhas)
    return falhas


if __name__ == "__main__":
    if "--autoteste" in sys.argv:
        sys.exit(1 if _autoteste() else 0)
    texto, faltando, suspeitas = montar()
    print("nomes nao encontrados:", len(faltando))
    for a, n in faltando:
        print("   FALTA", a, n)
    print("linhas suspeitas de secret:", len(suspeitas))
    for n, l in suspeitas:
        print("   ?", n, l)
    if faltando or suspeitas:
        print("NAO GRAVADO")
        sys.exit(1)
    open(os.path.join(RAIZ, "CODIGO_GERACAO_DE_IMAGEM.txt"), "w",
         encoding="utf-8").write(texto)
    print("GRAVADO:", len(texto.splitlines()), "linhas,", len(texto), "caracteres")
