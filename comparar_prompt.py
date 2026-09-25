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

    print("\nfalhas:", falhas)
