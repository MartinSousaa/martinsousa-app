"""checar_alcance.py — o sexto verificador: a correção chegou em TODO lugar?

POR QUE ELE EXISTE
------------------
Dono, 28/09: *"só de retrabalho gerado por erros seus é infinitamente superior
a qualquer outra coisa"*. Varrendo a conversa, o retrabalho tem uma forma só,
e ela se repete:

    eu corrijo NO LUGAR ONDE O PROBLEMA APARECEU,
    e não em todos os lugares onde a mesma regra alcança.

Já aconteceu, nesta base, com nome e data:

- `additionalProperties` foi escrito em `imagem.py` e faltou em
  `ambientacao_ref.py`. A tela deu erro 400 — e a linha certa já existia no
  repositório, a três arquivos de distância.
- A paleta azul voltou TRÊS vezes; o "ZERO TEXTO" sobreviveu num preset.
  Nos dois casos procurei pelo TEXTO do sintoma, não pelo ALCANCE da regra.
- O cartão de texto tinha quatro vozes — a regra compartilhada e três presets.
- `pergunta_info` ganhou um segundo dono e as peças 7 e 8 sumiram.

OS QUATRO VERIFICADORES ANTERIORES NÃO PEGAM ISSO. Eles conferem sintaxe,
ordem de nomes, o prompt da IMAGEM, quem lê o que mudou, e se a tela monta.
Nenhum pergunta: *"esta capacidade existe em um lugar e falta no irmão dele?"*

O QUE ELE CONFERE
-----------------
1. Todo campo que recebe IMAGEM aceita todo formato. O sistema tem
   `normalizar_imagem`, que converte HEIC, AVIF, GIF, BMP e TIFF. Um campo
   que lista extensões rejeita o arquivo ANTES de o conversor existir — e o
   colaborador que fotografou no iPhone não tem como saber por quê.
2. Todo caminho que manda imagem ao motor passa pelo conversor.
3. O rótulo não mente sobre o que aceita.
4. O prompt do PLANO é varrido. Ele decide quais peças são viáveis e qual
   ângulo usar, e nenhuma varredura o lia: 60 regras verdes mediam o prompt
   da IMAGEM enquanto o defeito estava no do plano.

ELE NÃO JULGA QUALIDADE. Só pergunta se a mesma capacidade está nos irmãos.
"""

import ast
import os
import re
import sys

# Os campos de upload que recebem IMAGEM. O nome do rótulo é o que identifica:
# extrato, fatura e planilha têm razão para restringir formato — imagem não.
_PALAVRAS_DE_IMAGEM = ("imagem", "imagens", "foto", "fotos", "referência",
                       "referencia", "referências", "referencias", "quadro",
                       "anexar imagem", "print")

# Extensões de imagem. Um `type=[...]` só com estas é uma porta que o
# conversor já sabia abrir.
_EXT_IMAGEM = {"png", "jpg", "jpeg", "webp", "heic", "heif", "avif", "gif",
               "bmp", "tif", "tiff"}

# Rótulo que promete menos do que o campo aceita. Quem lê "(JPG, PNG, WebP)"
# com um HEIC na mão não tenta — e o campo teria aceitado.
_ROTULO_QUE_MENTE = re.compile(r"\((?:[A-Za-z]{3,4}\s*,\s*)+[A-Za-z]{3,4}\)")


# Este arquivo FALA de marcador de conflito para saber achá-lo — procurar o
# texto nele mesmo seria a sexta vez nesta base que uma guarda se encontra.
IGNORAR_CONFLITO = {"checar_alcance.py"}


def _arquivos(raiz="."):
    for nome in sorted(os.listdir(raiz)):
        if nome.endswith(".py") and not nome.startswith("checar_"):
            yield nome


def _texto_do_no(no):
    """O literal de um nó, quando ele é um. '' quando não dá para saber."""
    if isinstance(no, ast.Constant) and isinstance(no.value, str):
        return no.value
    if isinstance(no, ast.JoinedStr):
        return "".join(p.value for p in no.values
                       if isinstance(p, ast.Constant) and isinstance(p.value, str))
    return ""


def uploads_de_imagem(fonte, arquivo=""):
    """Todo `file_uploader` cujo rótulo fala de imagem.

    Devolve [{arquivo, linha, rotulo, tipos, restringe, rotulo_mente}].
    `tipos` é None quando o campo aceita qualquer coisa — que é o certo.
    """
    try:
        arvore = ast.parse(fonte)
    except SyntaxError:
        return []
    achados = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        alvo = getattr(no.func, "attr", "")
        if alvo != "file_uploader":
            continue
        rotulo = _texto_do_no(no.args[0]) if no.args else ""
        if not any(p in rotulo.lower() for p in _PALAVRAS_DE_IMAGEM):
            continue
        tipos = None
        for kw in no.keywords:
            if kw.arg != "type":
                continue
            if isinstance(kw.value, ast.List):
                tipos = [_texto_do_no(e).lower() for e in kw.value.elts]
        restringe = bool(tipos) and set(tipos) <= _EXT_IMAGEM
        achados.append({
            "arquivo": arquivo, "linha": no.lineno, "rotulo": rotulo,
            "tipos": tipos, "restringe": restringe,
            "rotulo_mente": bool(tipos is None
                                 and _ROTULO_QUE_MENTE.search(rotulo)),
        })
    return achados


def main():
    falhas = []

    def reprova(msg):
        falhas.append(msg)
        print("FALHA  " + msg)

    # ── 1 e 3. OS CAMPOS DE IMAGEM ──────────────────────────────────────────
    total = 0
    for nome in _arquivos():
        with open(nome, encoding="utf-8") as fh:
            achados = uploads_de_imagem(fh.read(), nome)
        for a in achados:
            total += 1
            if a["restringe"]:
                reprova(
                    f"{a['arquivo']}:{a['linha']} — o campo {a['rotulo']!r} só "
                    f"aceita {a['tipos']}, mas o sistema tem "
                    f"`normalizar_imagem`, que converte HEIC, AVIF, GIF, BMP e "
                    f"TIFF. Use type=None: quem fotografa no iPhone manda HEIC "
                    f"e este campo recusa antes de o conversor existir.")
            if a["rotulo_mente"]:
                reprova(
                    f"{a['arquivo']}:{a['linha']} — o rótulo {a['rotulo']!r} "
                    f"promete menos do que o campo aceita (ele aceita "
                    f"qualquer formato). Quem lê a lista com um HEIC na mão "
                    f"não tenta.")
    print(f"ok    {total} campo(s) de imagem varrido(s)")

    # ── 2. O CONVERSOR NO CAMINHO ───────────────────────────────────────────
    #
    # Quem recebe imagem e manda para um modelo tem de passar por
    # `normalizar_imagem`. O chat mandava os bytes crus.
    # SÓ QUEM MANDA A IMAGEM A UM MODELO. Subir a foto para o Drive aceita
    # qualquer formato — exigir o conversor ali seria alarme falso, e
    # verificador que grita à toa ensina a ser ignorado. Foi o que aconteceu
    # com a primeira versão de `checar_tela.py`, que acusou o inocente.
    _SINAIS_DE_MODELO = ("anthropic.Anthropic", "messages.create",
                         "chat.completions", "images.generate",
                         "generate_content", "_chamar_ia")
    for nome in _arquivos():
        with open(nome, encoding="utf-8") as fh:
            fonte = fh.read()
        if not uploads_de_imagem(fonte, nome):
            continue
        if not any(sinal in fonte for sinal in _SINAIS_DE_MODELO):
            continue
        if "normalizar_imagem" not in fonte:
            reprova(
                f"{nome} recebe imagem por upload, manda para um modelo e "
                f"nunca chama `normalizar_imagem`. O arquivo cru vai ao "
                f"motor, e formato que ele não aceita vira erro genérico de "
                f"geração — sem dizer ao colaborador qual é o problema.")

    # ── 5. `session_state` LIDO DE DENTRO DE UMA THREAD ────────────────────
    #
    # Forma 6 do CLAUDE.md, e a que gerou o retrabalho de 28/09.
    #
    # `st.session_state` e ILEGIVEL dentro de `threading.Thread`. Eu sabia
    # disso, apliquei ao numero da peca (`_PECA_EM_AJUSTE`) e escrevi ate uma
    # guarda com Thread de verdade para provar. E deixei `produto` e `usuario`
    # lendo do session_state NO MESMO append_row, duas linhas ao lado.
    #
    # Resultado: toda linha do log gravou produto vazio, o filtro por nome
    # nunca bateu, e o historico de prompts voltava sempre vazio — em
    # silencio, porque `registrar` engole a propria excecao de proposito.
    #
    # Esta varredura acha o padrao: funcao que grava registro e le
    # `session_state` no corpo. Ela nao adivinha a pilha de chamadas; olha
    # quem ESCREVE e quem LE, que e onde o dano mora.
    _GRAVAM_REGISTRO = ("log_imagem.py", "atividades.py")
    for nome in _arquivos():
        if nome not in _GRAVAM_REGISTRO:
            continue
        with open(nome, encoding="utf-8") as fh:
            fonte = fh.read()
        try:
            arvore = ast.parse(fonte)
        except SyntaxError:
            continue
        for no in ast.walk(arvore):
            if not isinstance(no, ast.FunctionDef):
                continue
            trecho = ast.get_source_segment(fonte, no) or ""
            if "append_row" not in trecho:
                continue
            if "session_state" in trecho:
                reprova(
                    f"{nome}:{no.lineno} — `{no.name}` grava registro E lê "
                    f"`st.session_state`. A geração roda em "
                    f"`threading.Thread` (imagem.py:7162), e de lá o "
                    f"session_state volta VAZIO: o campo é gravado em branco, "
                    f"sem erro nenhum. Leia de um global de módulo, como "
                    f"`_PECA_EM_AJUSTE` faz.")

    # ── 6. O CARIMBO QUE GENTE LÊ, E O MÊS QUE O SISTEMA CALCULA ───────────
    #
    # Forma 6a. O container roda em UTC. `datetime.now()` cru SERVE quando os
    # dois lados da conta são UTC — expiração de token contra token gravado,
    # idade de cartão do Trello contra ação do Trello. Não serve em dois
    # casos, e são estes que esta varredura reprova:
    #
    #   1. o valor é LIDO POR GENTE. O Histórico carimbava 17h em cima do que
    #      o colaborador gerou às 14h.
    #   2. o valor vira MÊS ou DIA. Às 21h do dia 30 o container já está no
    #      dia 1º: o chat respondia a pontuação do mês errado, e o retrato do
    #      placar seria gravado com a data de amanhã.
    #
    # A porta única é `placar_core.agora_br()` / `hoje_br()`.
    _CARIMBO = re.compile(r"datetime\.now\(\s*\)\s*\.(strftime|date)\b")
    _VIRA_MES = re.compile(r"datetime\.now\(\s*\)(?![^\n]*timedelta)")
    # Onde o `datetime.now()` cru continua CERTO, e por quê. Comparação de
    # UTC com UTC não tem erro de fuso: trocar um lado só é que teria.
    _CONSISTENTES = {
        "auth.py": "expiração de token contra token gravado, os dois em UTC",
        "rhid_api.py": "validade do token da RHiD contra a hora de emissão",
        "gargalos_tela.py": "idade do cartão contra a ação do Trello, ambos UTC",
        "fechar_expediente.py": "é o fallback do except; o caminho normal usa FUSO",
        "placar_core.py": "é onde `agora_br` mora",
        "varredura_formas.py": "é a varredura que PROCURA este padrão",
    }
    for nome, fonte in ((n, f) for n in _arquivos()
                        for f in [open(n, encoding="utf-8").read()]):
        if nome in _CONSISTENTES:
            continue
        # Fora do bloco de conferência: a guarda que procura `datetime.now()`
        # contém o texto `datetime.now()`. É a sexta vez nesta base.
        corpo = fonte.split('if __name__ == "__main__":')[0]
        for i, linha in enumerate(corpo.splitlines(), 1):
            codigo = re.sub(r"`[^`]*`", "", linha.split("#", 1)[0])
            if not _VIRA_MES.search(codigo):
                continue
            reprova(
                f"{nome}:{i} — `datetime.now()` sem fuso. O container roda em "
                f"UTC: se este valor é lido por gente, sai 3h adiantado; se "
                f"vira mês ou dia, erra depois das 21h. Use "
                f"`placar_core.agora_br()` ou `hoje_br()`.")

    # ── 7. MARCADOR DE CONFLITO COMMITADO ──────────────────────────────────
    #
    # 28/09: resolvi um merge nos tres arquivos `.py` que o git listou e NAO
    # olhei o `CLAUDE.md` — que tambem estava em conflito. O arquivo subiu com
    # `<<<<<<< HEAD` dentro, e nenhum dos seis verificadores leu: todos olham
    # codigo. E a Forma 1 na resolucao de conflito.
    #
    # Varre TODO arquivo de texto, e nao so `.py`: o defeito nasceu justamente
    # no que nao e codigo.
    import glob as _glob
    for _nome in sorted(_glob.glob("*.py") + _glob.glob("*.md")
                        + _glob.glob("*.txt") + _glob.glob("*.toml")):
        if _nome in IGNORAR_CONFLITO:
            continue
        try:
            with open(_nome, encoding="utf-8") as fh:
                _linhas = fh.read().splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for _i, _l in enumerate(_linhas, 1):
            if _l.startswith(("<<<<<<< ", ">>>>>>> ")):
                reprova(
                    f"{_nome}:{_i} — marcador de conflito de merge no arquivo "
                    f"commitado. Resolver os `.py` que o git listou e esquecer "
                    f"o resto e a Forma 1 na resolucao de conflito.")
                break

    # ── 4. O PROMPT DO PLANO ────────────────────────────────────────────────
    #
    # 28/09: as peças 7 e 8 sumiram e o produto saiu torto. A causa estava no
    # prompt do PLANO, que varredura nenhuma lia — `checar_prompts.py` monta o
    # prompt da IMAGEM. Sessenta regras verdes mediam outro texto.
    with open("checar_prompts.py", encoding="utf-8") as fh:
        varredura = fh.read()
    if "gerar_triagem_ia" not in varredura:
        reprova(
            "checar_prompts.py não lê o prompt do PLANO "
            "(`gerar_triagem_ia`). Ele decide quais peças são viáveis e qual "
            "ângulo usar — e foi ali que as peças 7 e 8 sumiram em 28/09, com "
            "os cinco verificadores verdes.")

    print()
    if falhas:
        print(f"FALHA  {len(falhas)} correção(ões) que não chegaram em todo "
              f"lugar.\n       A correção se aplica ao ALCANCE da regra, não "
              f"ao lugar onde o sintoma apareceu.")
        return 1
    print("ok    toda capacidade existe em todos os irmãos dela")
    return 0


if __name__ == "__main__":
    sys.exit(main())
