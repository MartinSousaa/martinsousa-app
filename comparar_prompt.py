"""comparar_prompt.py — o que o prompt da correção tinha que o da geração não.

A PERGUNTA QUE ELE RESPONDE
---------------------------
Ditada pelo dono em 25/09: *"assim conseguimos verificar o que tinha no prompt
da correção que não tinha no prompt da geração. E se o prompt de correção
contiver essas informações no prompt inicial, quer dizer que o sistema está
ignorando alguma coisa."*

São dois diagnósticos opostos, e confundi-los custa semanas:

    frase SÓ na correção   ->  FALTA no prompt de geração. Escrever resolve.
    frase NOS DOIS         ->  o modelo DESOBEDECEU. Escrever não resolve.

O segundo é o caro. Foi ele que fez esta base perder dias ajustando o texto de
um pedido enquanto o problema era outro — está no CLAUDE.md, regra 5. Uma
regra que já estava lá e não foi cumprida não pede mais texto: pede outra
coisa (ordem mais curta, contradição removida, ou a constatação de que o motor
não faz aquilo).

COMO ELE COMPARA
----------------
Por FRASE, não por palavra. Palavra solta dá ruído: "produto" aparece nos dois
e não diz nada. E não é comparação literal — a mesma regra sai escrita de dois
jeitos ("never cut by the frame edge" e "no part cut by the frame edge"), então
a frase é reduzida ao seu esqueleto antes de comparar: minúscula, sem acento,
sem pontuação, sem as palavras de ligação.

NÃO É UM JUIZ
-------------
Ele não diz se o prompt está bom. Diz onde olhar — e a leitura é do dono.
"""

import re
import unicodedata

# Palavras que aparecem em toda frase e não distinguem nada. Sem tirá-las,
# duas frases sobre assuntos diferentes parecem parentes só por serem frases.
_LIGACAO = {
    "a", "o", "as", "os", "um", "uma", "de", "do", "da", "dos", "das", "e",
    "em", "no", "na", "nos", "nas", "que", "para", "por", "com", "sem", "ao",
    "aos", "se", "ou", "the", "a", "an", "of", "in", "on", "to", "and", "or",
    "is", "are", "be", "it", "its", "as", "at", "by", "for", "with", "not",
}


def _palavras(frase):
    """As palavras que a frase usa para dizer o que diz. Conjunto."""
    t = unicodedata.normalize("NFD", str(frase or ""))
    t = t.encode("ascii", "ignore").decode("ascii").lower()
    return {p for p in re.findall(r"[a-z0-9]+", t)
            if p not in _LIGACAO and len(p) > 2}


def _esqueleto(frase):
    """A frase reduzida ao que ela diz: sem acento, sem ligação, ordenada."""
    return " ".join(sorted(_palavras(frase)))


# QUANTO DE UMA FRASE PRECISA BATER PARA SER A MESMA REGRA.
#
# Comparação literal não serve: a mesma trava já apareceu nesta base escrita
# de dois jeitos ("never cut by the frame edge" e "no part cut by the frame
# edge"), e o CLAUDE.md registra o estrago. "corte" e "cortado" são a mesma
# ordem; contá-las como regras diferentes encheria o relatório de falso "só na
# correção" — que é justamente o diagnóstico caro de errar.
#
# 0,6 porque abaixo disso frases sobre assuntos vizinhos começam a casar
# ("o produto ocupa 85% do quadro" com "o produto fica centralizado no
# quadro"), e aí o relatório erra para o outro lado.
_PARECIDO = 0.6


def _parecidas(a, b):
    """Duas frases dizem a mesma coisa? Pela fatia de palavras em comum."""
    pa, pb = _palavras(a), _palavras(b)
    if not pa or not pb:
        return False
    return len(pa & pb) / max(len(pa), len(pb)) >= _PARECIDO


def frases(texto):
    """O texto quebrado em frases — linha, ponto final e marcador de lista."""
    bruto = re.split(r"[\n\r]+|(?<=[.!?])\s+", str(texto or ""))
    fora = []
    for f in bruto:
        f = f.strip().lstrip("-•*·> ").strip()
        # TRÊS PALAVRAS QUE SIGNIFICAM ALGO, no mínimo. "MS_FUNDO: padrao" e
        # "IMAGE TYPE: 4" são marcador e rótulo, não regra — e entrariam nas
        # três listas sujando a leitura de quem só quer ver o que mudou.
        if len(f) >= 12 and len(_palavras(f)) >= 3:
            fora.append(f)
    return fora


def comparar(prompt_geracao, prompt_correcao):
    """(so_na_correcao, nos_dois, so_na_geracao). Função pura.

    `nos_dois` é o achado que importa: a regra estava escrita e a imagem saiu
    errada assim mesmo.
    """
    ger = frases(prompt_geracao)
    cor = frases(prompt_correcao)
    so_cor = [f for f in cor if not any(_parecidas(f, g) for g in ger)]
    dois = [f for f in cor if any(_parecidas(f, g) for g in ger)]
    so_ger = [g for g in ger if not any(_parecidas(g, f) for f in cor)]
    return so_cor, dois, so_ger


def veredito(prompt_geracao, prompt_correcao):
    """Uma frase dizendo qual dos dois diagnósticos é o desta correção."""
    so_cor, dois, _ = comparar(prompt_geracao, prompt_correcao)
    if dois and not so_cor:
        return ("desobedecido", "Tudo que a correção pediu JÁ ESTAVA no prompt "
                "de geração. Escrever mais não resolve — o modelo ignorou o "
                "que já estava escrito.")
    if so_cor and not dois:
        return ("faltava", "A correção trouxe regra que o prompt de geração "
                "não tinha. Aqui escrever resolve: leve essas frases para a "
                "geração.")
    if so_cor and dois:
        return ("os dois", "Parte da correção era regra nova (falta na "
                "geração) e parte já estava escrita (foi ignorada). As duas "
                "listas abaixo separam uma da outra.")
    return ("nada a dizer", "A correção não acrescentou frase nenhuma sobre a "
            "geração.")


def parear(linhas):
    """Casa cada correção com a geração que veio antes dela. Pura.

    `linhas` são as do `log_imagem`, cada uma com `quando`, `produto`, `acao`
    e `prompt`. Devolve [(geracao, correcao)], da mais recente para a mais
    antiga.

    A REGRA DO CASAMENTO, e ela é conservadora: a correção casa com a última
    geração DO MESMO PRODUTO que aconteceu antes dela. Correção sem geração
    antes — porque o registro começou no meio, ou porque a geração foi de
    outro dia que já saiu da janela — fica de fora. Parear com a geração
    errada daria o diagnóstico errado, e o diagnóstico errado aqui custa
    semanas mexendo no texto errado.
    """
    def _quando(l):
        # "25/09/2026 14:03:11" -> ordenável sem depender de datetime.
        t = str(l.get("quando") or "")
        return (t[6:10], t[3:5], t[0:2], t[11:])

    em_ordem = sorted(linhas or [], key=_quando)
    ultima_ger, pares = {}, []
    for l in em_ordem:
        acao = str(l.get("acao") or "")
        prod = str(l.get("produto") or "").strip()
        if not str(l.get("prompt") or "").strip():
            continue
        if acao == "prompt_geracao":
            ultima_ger[prod] = l
        elif acao == "prompt_ajuste" and prod in ultima_ger:
            pares.append((ultima_ger[prod], l))
    return list(reversed(pares))


def cadeias(linhas):
    """A vida inteira de cada peça: a geração e TODAS as correções dela.

    Devolve [(produto, peca, [linha_geracao, correcao1, correcao2, ...])], da
    peça mais recentemente mexida para a mais antiga.

    POR QUE A CADEIA INTEIRA, E NÃO SÓ O ÚLTIMO PAR
    -----------------------------------------------
    Ditado pelo dono em 25/09: *"quando a imagem estiver com todos os ajustes
    que o colaborador solicitou, precisamos comparar com os anteriores de
    comandos que não deram certo. Pois o prompt da imagem final correta
    precisava ter sido construído na primeira geração."*

    É outro diagnóstico, e mais fundo que o do par: a diferença entre o
    primeiro prompt e o último é a lista do que o sistema deveria ter sabido
    desde o começo. E as correções do meio, as que não deram certo, dizem
    quantas rodadas custou cada item dessa lista.

    A CHAVE É (produto, peça), e a peça vem da coluna `imagem`. Pelo rótulo
    não daria: depois de um ajuste ele vira outra coisa, e a cadeia se
    partiria no meio.
    """
    def _quando(l):
        t = str(l.get("quando") or "")
        return (t[6:10], t[3:5], t[0:2], t[11:])

    em_ordem = sorted(linhas or [], key=_quando)
    por_peca, ordem = {}, []
    for l in em_ordem:
        acao = str(l.get("acao") or "")
        if acao not in ("prompt_geracao", "prompt_ajuste"):
            continue
        if not str(l.get("prompt") or "").strip():
            continue
        chave = (str(l.get("produto") or "").strip(),
                 str(l.get("imagem") or "").strip())
        if acao == "prompt_geracao":
            # Geração nova começa uma cadeia NOVA: a peça foi refeita do
            # zero, e juntar com as correções da versão anterior misturaria
            # duas histórias diferentes.
            por_peca[chave] = [l]
        elif chave in por_peca:
            por_peca[chave].append(l)
        else:
            continue
        if chave in ordem:
            ordem.remove(chave)
        ordem.append(chave)
    return [(p, pe, por_peca[(p, pe)]) for p, pe in reversed(ordem)]


def motores(linhas):
    """Qual motor fez cada peça. {(produto, peca): [{quando, motor, enquadramento}]}.

    POR QUE ISTO EXISTE
    -------------------
    Dono, 30/09, depois de eu pedir que ELE abrisse uma tela para conferir
    qual motor a conta tinha: *"eu que tenho que confirmar? você que codificou
    o sistema..."*.

    Ele estava certo. O Studio sabe qual motor fez cada peça — grava em
    `diagnostico["motor"]` nos cinco caminhos —, e o registro que sobrevive à
    sessão dizia `resultado="enviado ao motor"`. "O motor", sem dizer qual.

    E é a pergunta mais importante sobre uma peça torta: margem e produto
    redesenhado vêm de a peça ter sido feita pelo RESERVA, que não aceita
    `size=1024x1024` nem `input_fidelity=high`. Sem o nome do motor na linha,
    o arquivo não responde isso e a pergunta cai numa pessoa.

    A CHAVE É A MESMA DE `cadeias`, (produto, peça), de propósito: é assim que
    a linha do motor encontra a peça a que pertence.
    """
    fora = {}
    for l in (linhas or []):
        if str(l.get("acao") or "") != "motor_da_peca":
            continue
        chave = (str(l.get("produto") or "").strip(),
                 str(l.get("imagem") or "").strip())
        fora.setdefault(chave, []).append({
            "quando": str(l.get("quando") or ""),
            "motor": str(l.get("resultado") or "").strip(),
            "enquadramento": str(l.get("instrucao") or "").strip(),
        })
    return fora


def linha_do_motor(registros):
    """Uma linha em português sobre o motor da peça, ou "" quando não há.

    O ÚLTIMO REGISTRO MANDA: a peça pode ter sido refeita, e quem interessa é
    o motor que fez a versão que está na mão do colaborador.
    """
    if not registros:
        return ""
    ult = registros[-1]
    motor = ult.get("motor") or "motor não registrado"
    txt = f"motor: {motor}"
    if ult.get("enquadramento"):
        txt += f"\n    enquadramento: {ult['enquadramento']}"
    return txt


def _faixa(titulo):
    return f"\n{'=' * 78}\n{titulo}\n{'=' * 78}\n"


def relatorio_txt(linhas):
    """TODO o histórico de prompts, em um texto só, pronto para copiar.

    POR QUE UM ARQUIVO, E NÃO A TELA
    --------------------------------
    O dono: *"copiar todos os prompts vai gerar muito trabalho e a
    possibilidade de erros manuais"*. Copiar oito prompts de seis mil
    caracteres da tela, um a um, é trabalho braçal com chance de faltar
    pedaço — e um prompt copiado pela metade leva a análise para o lado
    errado, que é pior do que não ter o arquivo.

    A ordem do texto é a da leitura: primeiro o veredito de cada peça, depois
    os prompts inteiros. Quem abre o arquivo vê o diagnóstico antes das seis
    mil linhas.
    """
    cads = cadeias(linhas)
    mots = motores(linhas)
    if not cads:
        # SEM PROMPT, MAS COM MOTOR, o arquivo ainda tem o que dizer — e
        # devolver "nenhum registro" com linhas na mão seria a segunda
        # mentira empilhada na primeira.
        if mots:
            corpo = ["Nenhum PROMPT registrado — mas há registro de motor:\n"]
            for (prod, peca), regs in sorted(mots.items()):
                corpo.append(f"{prod or 'sem nome'} · peça {peca or '?'}: "
                             + linha_do_motor(regs))
            return "\n".join(corpo) + "\n"
        return ("Nenhum prompt registrado ainda.\n\nO registro começa na "
                "próxima geração: cada peça grava o texto que foi ao motor, "
                "e cada correção grava o dela.\n")

    partes = [_faixa("MS STUDIO — HISTÓRICO DE PROMPTS"),
              f"{len(cads)} peça(s) com prompt registrado.\n",
              "COMO LER ESTE ARQUIVO",
              "  frase SÓ na correção -> faltava no prompt de geração;",
              "                          escrever na geração resolve.",
              "  frase NOS DOIS       -> a regra já estava escrita e a imagem",
              "                          saiu errada assim mesmo: o modelo",
              "                          ignorou, e escrever de novo não",
              "                          resolve.",
              "\nA diferença entre o PRIMEIRO prompt e o ÚLTIMO é a lista do",
              "que o sistema deveria ter sabido desde a primeira geração.\n"]

    # ── 1. O resumo, peça a peça ─────────────────────────────────────────
    partes.append(_faixa("RESUMO"))
    for produto, peca, cad in cads:
        ger, correcoes = cad[0], cad[1:]
        nome = f"{produto or 'sem nome'} · peça {peca or '?'}"
        _mot = linha_do_motor(mots.get((produto, peca)))
        _sufixo_mot = f"\n    {_mot}" if _mot else ""
        if not correcoes:
            partes.append(f"{nome}: gerada e não corrigida. "
                          f"{ger.get('quando', '')}{_sufixo_mot}")
            continue
        _n, _frase = veredito(ger.get("prompt"), correcoes[-1].get("prompt"))
        so_cor, dois, _ = comparar(ger.get("prompt"),
                                   correcoes[-1].get("prompt"))
        partes.append(
            f"{nome}: {len(correcoes)} correção(ões) · veredito da última: "
            f"{_n.upper()}\n    {_frase}\n"
            f"    só na correção: {len(so_cor)} frase(s) · "
            f"nos dois: {len(dois)} frase(s)" + _sufixo_mot)

    # ── 2. O que faltava na geração, peça a peça ────────────────────────
    partes.append(_faixa(
        "O QUE A ÚLTIMA CORREÇÃO TINHA E A GERAÇÃO NÃO TINHA"))
    for produto, peca, cad in cads:
        if len(cad) < 2:
            continue
        so_cor, dois, _ = comparar(cad[0].get("prompt"),
                                   cad[-1].get("prompt"))
        partes.append(f"\n--- {produto or 'sem nome'} · peça {peca or '?'} ---")
        partes.append("SÓ NA CORREÇÃO (faltava na geração):")
        partes.extend(f"  + {f}" for f in so_cor) if so_cor else \
            partes.append("  (nenhuma)")
        partes.append("NOS DOIS (estava escrito e não foi cumprido):")
        partes.extend(f"  = {f}" for f in dois) if dois else \
            partes.append("  (nenhuma)")

    # ── 3. Os prompts inteiros, na ordem em que aconteceram ─────────────
    partes.append(_faixa("OS PROMPTS, INTEIROS"))
    for produto, peca, cad in cads:
        partes.append(f"\n{'-' * 78}")
        partes.append(f"{produto or 'sem nome'} · peça {peca or '?'} · "
                      f"{len(cad)} prompt(s)")
        partes.append("-" * 78)
        for i, l in enumerate(cad):
            rotulo = ("GERAÇÃO" if i == 0 else f"CORREÇÃO {i}")
            partes.append(f"\n[{rotulo}] {l.get('quando', '')} · "
                          f"{l.get('usuario', '')} · tipo: {l.get('tipo', '')}")
            partes.append(str(l.get("prompt") or ""))
    return "\n".join(partes) + "\n"


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    _GER = """MS_FUNDO: padrao
O produto ocupa 85-92% do quadro.
Nenhuma parte do produto cortada pela borda.
Fundo azul-marinho da marca.
"""
    _COR = """MS_FUNDO: padrao
MODO AJUSTE FINO
Nenhuma parte do produto cortada pela borda.
A alca da caneca fica virada para a direita.
"""
    _so_cor, _dois, _so_ger = comparar(_GER, _COR)

    # O ACHADO QUE IMPORTA: a regra da borda estava nos DOIS.
    ok("a regra repetida aparece em 'nos dois'",
       any("cortada pela borda" in f for f in _dois))
    ok("e NAO em 'so na correcao'",
       not any("cortada pela borda" in f for f in _so_cor))
    ok("o pedido novo do colaborador sai como so na correcao",
       any("alca da caneca" in f for f in _so_cor))
    ok("o que a correcao nao repetiu fica em so na geracao",
       any("85-92" in f for f in _so_ger))

    # A MESMA REGRA ESCRITA DE OUTRO JEITO NAO PODE VIRAR 'REGRA NOVA'.
    # Foi esse engano que fez esta base ter a mesma trava em duas redacoes.
    # A MESMA ORDEM EM OUTRA REDACAO E A MESMA ORDEM.
    ok("ordem das palavras nao inventa regra nova",
       _parecidas("nunca corte o produto pela borda",
                  "o produto nunca cortado pela borda"))
    ok("e a traducao da mesma trava tambem casa",
       _parecidas("never cut the product by the frame edge",
                  "no part of the product cut by the frame edge"))
    ok("mas frase vizinha de outro assunto NAO casa",
       not _parecidas("o produto ocupa 85% do quadro",
                      "o fundo e azul-marinho da marca"))
    ok("acento e caixa tambem nao",
       _esqueleto("PRODUTO NÃO CORTADO") == _esqueleto("produto nao cortado"))
    ok("mas assuntos diferentes continuam diferentes",
       _esqueleto("o produto ocupa 85% do quadro")
       != _esqueleto("o fundo e azul-marinho"))

    # FRASE CURTA NAO E REGRA: titulo e numero sujariam as tres listas.
    ok("marcador nao e regra: fica fora das tres listas",
       frases("MS_FUNDO: padrao") == [] and frases("IMAGE TYPE: 4") == [])
    ok("linha vazia nao entra", frases("\n\n   \n") == [])
    ok("texto nenhum nao quebra", comparar(None, None) == ([], [], []))

    # OS TRES VEREDITOS.
    ok("tudo repetido = desobedecido",
       veredito(_GER, "Nenhuma parte do produto cortada pela borda.")[0]
       == "desobedecido")
    ok("tudo novo = faltava",
       veredito(_GER, "A etiqueta fica visivel no canto inferior.")[0]
       == "faltava")
    ok("misturado = os dois", veredito(_GER, _COR)[0] == "os dois")
    ok("correcao vazia nao acusa nada",
       veredito(_GER, "")[0] == "nada a dizer")

    # ── O CASAMENTO GERACAO -> CORRECAO ─────────────────────────────────
    _LOG = [
        {"quando": "25/09/2026 10:00:00", "produto": "Caneca",
         "acao": "prompt_geracao", "prompt": _GER},
        {"quando": "25/09/2026 10:05:00", "produto": "Album",
         "acao": "prompt_geracao", "prompt": "Outro prompt de outro produto."},
        {"quando": "25/09/2026 10:10:00", "produto": "Caneca",
         "acao": "prompt_ajuste", "prompt": _COR},
    ]
    _pares = parear(_LOG)
    ok("uma correcao casa com a geracao do MESMO produto", len(_pares) == 1)

    # ── O MOTOR DE CADA PECA CHEGA AO ARQUIVO ───────────────────────────
    #
    # ESTA GUARDA NASCEU DE UM TROPECO MEU, no mesmo dia.
    #
    # Escrevi a linha `motor_da_peca` no log para responder "qual motor fez
    # esta peca?" — e `cadeias` descarta toda acao que nao seja
    # `prompt_geracao`/`prompt_ajuste`. O dado seria gravado e NUNCA
    # mostrado: o mesmo defeito que eu estava corrigindo, um passo adiante.
    # Gravar sem ninguem ler nao e registro, e lixo com custo de escrita.
    #
    # O NOME DA ACAO VEM DO `imagem.py`, E NAO DA MINHA CABECA. Se eu
    # escrever a string a mao aqui, a guarda passa a medir o que eu ACHO que
    # o sistema grava — e foi exatamente assim que o botao dos oito prompts
    # quebrou com a guarda verde (Forma 7 do CLAUDE.md).
    import ast as _ast_mot, os as _os_mot
    _fonte_img = open(_os_mot.path.join(
        _os_mot.path.dirname(_os_mot.path.abspath(__file__)), "imagem.py"),
        encoding="utf-8").read()
    _acoes_gravadas = set()
    for _no in _ast_mot.walk(_ast_mot.parse(_fonte_img)):
        if (isinstance(_no, _ast_mot.Call)
                and getattr(_no.func, "attr", "") == "registrar"
                and _no.args
                and isinstance(_no.args[0], _ast_mot.Constant)):
            _acoes_gravadas.add(_no.args[0].value)
    ok("o imagem.py grava mesmo uma linha de motor por peca",
       "motor_da_peca" in _acoes_gravadas)

    _LOG_MOT = [
        {"quando": "30/09/2026 16:24:15", "produto": "Compasso", "imagem": "1",
         "acao": "prompt_geracao", "prompt": _GER},
        {"quando": "30/09/2026 16:24:51", "produto": "Compasso", "imagem": "1",
         "acao": "motor_da_peca", "prompt": "",
         "resultado": "Gemini 3.1 Flash Image (fallback, COM fotos)",
         "instrucao": "o motor devolveu 768x1365 e o produto nao cabe num "
                      "recorte quadrado — o Studio preencheu as faixas."},
    ]
    _txt_mot = relatorio_txt(_LOG_MOT)
    # NAO BASTA "nao explodiu": confere O QUE FOI ESCRITO.
    ok("o nome do motor aparece no arquivo",
       "Gemini 3.1 Flash Image" in _txt_mot)
    ok("e o enquadramento que gerou a margem aparece junto",
       "preencheu as faixas" in _txt_mot)
    # A LINHA DO MOTOR NAO PODE VIRAR UMA PECA FANTASMA.
    #
    # A primeira versao desta assercao contava "· peça 1" no TEXTO e exigia 1
    # — e reprovou, com razao do codigo: o nome da peca aparece no RESUMO e
    # de novo na secao dos prompts inteiros. Eu estava medindo o formato do
    # relatorio, nao a propriedade. A propriedade e que a linha de motor nao
    # abre uma cadeia propria.
    ok("a linha do motor nao vira uma peca fantasma",
       len(cadeias(_LOG_MOT)) == 1)
    # E SEM PROMPT NENHUM o arquivo ainda diz o que sabe, em vez de mentir
    # "nenhum registro" com linha na mao.
    _so_motor = relatorio_txt([_LOG_MOT[1]])
    ok("so com a linha de motor, o arquivo nao diz 'nenhum registro'",
       "Gemini 3.1 Flash Image" in _so_motor
       and "Nenhum prompt registrado ainda" not in _so_motor)
    ok("e com a do produto certo",
       _pares[0][0]["produto"] == "Caneca" and _pares[0][1]["produto"] == "Caneca")

    # CORRECAO SEM GERACAO ANTES NAO INVENTA PAR.
    ok("correcao orfa fica de fora",
       parear([{"quando": "25/09/2026 11:00:00", "produto": "Caneca",
                "acao": "prompt_ajuste", "prompt": _COR}]) == [])
    # E A GERACAO QUE VEM DEPOIS NAO SERVE: seria o diagnostico ao contrario.
    ok("geracao posterior nao casa com correcao anterior",
       parear([
           {"quando": "25/09/2026 12:00:00", "produto": "Caneca",
            "acao": "prompt_ajuste", "prompt": _COR},
           {"quando": "25/09/2026 13:00:00", "produto": "Caneca",
            "acao": "prompt_geracao", "prompt": _GER}]) == [])
    # DUAS CORRECOES SEGUIDAS casam as duas com a mesma geracao.
    ok("duas correcoes, dois pares",
       len(parear(_LOG + [{"quando": "25/09/2026 10:20:00",
                           "produto": "Caneca", "acao": "prompt_ajuste",
                           "prompt": _COR}])) == 2)
    # LINHA SEM PROMPT (as antigas, de antes da coluna existir) nao entra.
    ok("linha antiga sem prompt e ignorada",
       parear([{"quando": "24/09/2026 10:00:00", "produto": "Caneca",
                "acao": "prompt_geracao", "prompt": ""},
               {"quando": "24/09/2026 10:10:00", "produto": "Caneca",
                "acao": "prompt_ajuste", "prompt": _COR}]) == [])
    ok("registro vazio nao quebra", parear([]) == [] and parear(None) == [])
    # A ORDEM DA TELA: mais recente em cima.
    _tres = parear(_LOG + [{"quando": "25/09/2026 10:30:00",
                            "produto": "Caneca", "acao": "prompt_ajuste",
                            "prompt": "Outra correcao qualquer aqui."}])
    ok("o mais recente vem primeiro",
       _tres[0][1]["quando"] > _tres[1][1]["quando"])

    # ── A CADEIA INTEIRA DE CADA PECA ───────────────────────────────────
    #
    # "O prompt da imagem final correta precisava ter sido construido na
    # primeira geracao" — dono, 25/09. Entao a cadeia guarda a geracao E
    # todas as correcoes, na ordem em que aconteceram.
    _CAD = [
        {"quando": "25/09/2026 10:00:00", "produto": "Caneca", "imagem": "1",
         "acao": "prompt_geracao", "prompt": _GER, "usuario": "myrella"},
        {"quando": "25/09/2026 10:05:00", "produto": "Caneca", "imagem": "4",
         "acao": "prompt_geracao", "prompt": _GER, "usuario": "myrella"},
        {"quando": "25/09/2026 10:10:00", "produto": "Caneca", "imagem": "1",
         "acao": "prompt_ajuste", "prompt": _COR, "usuario": "myrella"},
        {"quando": "25/09/2026 10:20:00", "produto": "Caneca", "imagem": "1",
         "acao": "prompt_ajuste", "usuario": "myrella",
         "prompt": "MODO AJUSTE FINO\nA alca da caneca virada para a direita."},
    ]
    _cads = cadeias(_CAD)
    ok("uma cadeia por peca", len(_cads) == 2)
    _p1 = next(c for c in _cads if c[1] == "1")
    ok("a peca 1 tem a geracao e as DUAS correcoes", len(_p1[2]) == 3)
    ok("a geracao vem primeiro", _p1[2][0]["acao"] == "prompt_geracao")
    ok("e as correcoes na ordem em que aconteceram",
       _p1[2][1]["quando"] < _p1[2][2]["quando"])
    _p4 = next(c for c in _cads if c[1] == "4")
    ok("a peca 4 nao herda correcao da peca 1", len(_p4[2]) == 1)

    # GERACAO NOVA COMECA CADEIA NOVA: a peca foi refeita do zero, e juntar
    # com as correcoes da versao anterior misturaria duas historias.
    _refeita = cadeias(_CAD + [
        {"quando": "25/09/2026 11:00:00", "produto": "Caneca", "imagem": "1",
         "acao": "prompt_geracao", "prompt": _GER, "usuario": "myrella"}])
    ok("refazer a peca zera a cadeia dela",
       len(next(c for c in _refeita if c[1] == "1")[2]) == 1)

    # CORRECAO SEM GERACAO NA JANELA nao inventa cadeia.
    ok("correcao orfa nao vira cadeia",
       cadeias([{"quando": "25/09/2026 12:00:00", "produto": "X",
                 "imagem": "2", "acao": "prompt_ajuste", "prompt": _COR}]) == [])
    ok("acao que nao e prompt fica de fora",
       cadeias([{"quando": "25/09/2026 09:00:00", "produto": "Caneca",
                 "imagem": "1", "acao": "ajuste_aplicado",
                 "prompt": ""}]) == [])
    ok("registro vazio nao quebra", cadeias([]) == [] and cadeias(None) == [])

    # ── O ARQUIVO QUE SE BAIXA COM UM CLIQUE ────────────────────────────
    #
    # "Copiar todos os prompts vai gerar muito trabalho e a possibilidade de
    # erros manuais" — dono, 25/09.
    _txt = relatorio_txt(_CAD)
    ok("o relatorio traz o resumo antes dos prompts",
       _txt.index("RESUMO") < _txt.index("OS PROMPTS, INTEIROS"))
    ok("cada peca aparece no resumo",
       "peça 1" in _txt and "peça 4" in _txt)
    ok("os prompts inteiros estao la, nao um resumo deles",
       _GER.strip().splitlines()[1] in _txt
       and "A alca da caneca virada para a direita." in _txt)
    ok("a geracao e as correcoes sao rotuladas",
       "[GERAÇÃO]" in _txt and "[CORREÇÃO 1]" in _txt
       and "[CORREÇÃO 2]" in _txt)
    ok("o veredito de cada peca sai escrito",
       "veredito da última:" in _txt)
    ok("e o arquivo explica como se le",
       "COMO LER ESTE ARQUIVO" in _txt)
    ok("sem registro, o arquivo diz isso em vez de vir vazio",
       "Nenhum prompt registrado" in relatorio_txt([]))
    # UM ARQUIVO QUE NAO ABRE NAO SERVE: nada de bytes estranhos.
    ok("o texto e texto", isinstance(_txt, str) and _txt.encode("utf-8"))

    print("\nfalhas:", falhas)
    # O CODIGO DE SAIDA. Sem ele, quem le `returncode` ve este modulo como
    # aprovado SEMPRE — e o `checar_mutacao` le exatamente isso. Era assim
    # que as entradas apontadas para ca ficavam verdes por acidente.
    import sys as _sys_saida
    _sys_saida.exit(1 if falhas else 0)
