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
    ]),
    ("AS MEDIDAS DE CADA PECA (fonte unica de tamanho e densidade)", "imagem.py", [
        "OCUPACAO", "BLOCOS", "faixa_de_blocos", "blocos_em_portugues",
        "faixa_de_ocupacao", "ocupacao_em_portugues", "ocupacao_em_ingles",
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
    ]),
    ("A CONFERENCIA DA PECA PRONTA", "imagem.py", [
        "conferir_texto", "_PERGUNTAS_DA_PECA", "pergunta_do_tamanho",
        "perguntas_da_peca", "conferir_peca", "peca_em_aviso",
        "revisar_peca", "revisar_tudo", "revisar_texto", "relato_em_texto",
        "_relato_base",
    ]),
    ("A LEITURA DAS REFERENCIAS DE AMBIENTACAO", "ambientacao_ref.py", [
        "_ESQUEMA", "descrever", "resumo",
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


def _autoteste():
    """Confere a exportacao SEM gravar. E a guarda de conteudo, nao de sintaxe."""
    falhas = 0

    def ok(titulo, cond):
        nonlocal falhas
        print(("  ok   " if cond else "  FALHA ") + titulo)
        if not cond:
            falhas += 1

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
