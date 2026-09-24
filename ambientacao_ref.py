"""ambientacao_ref.py — o Studio OLHA as referências de ambientação.

O QUE O DONO PEDIU, E POR QUE O QUE EXISTIA NÃO SERVE
------------------------------------------------------
*"Não tem que ir pelo nome da imagem, tem que olhar todas e quando for gerar a
imagem do produto entender qual ambientação se enquadra melhor em cada tipo de
foto que ele tem que gerar."*

A referência de LAYOUT, que já existe, casa pelo nome do arquivo
(`imagem.py:717`): quem sobe "presentear.jpg" ganha a peça 7. Isso funciona
para layout, porque o colaborador batiza o arquivo pelo tipo de peça que ele
representa.

Para AMBIENTAÇÃO não serve. Ninguém nomeia uma foto de cenário por tipo de
peça — ela é "bar_noite.jpg", "sala_clara.png", ou o nome que a câmera deu. E
a mesma sala pode caber em três peças diferentes.

O QUE ESTE MÓDULO FAZ
---------------------
Manda TODAS as referências para o Claude Vision, de uma vez, e pede uma
descrição do CENÁRIO de cada uma — ambiente, luz, materiais, clima, paleta.
Depois, para cada tipo de peça, ele escolhe qual descrição combina.

A escolha é feita UMA VEZ por geração, e não uma por imagem: são oito peças, e
oito chamadas de visão sobre as mesmas fotos seria pagar oito vezes pela mesma
leitura.

O PRODUTO CONTINUA MANDANDO
---------------------------
A referência de ambientação entra como CENÁRIO, nunca como produto. É a mesma
distinção que já existe para o layout: copie a estrutura, não a peça. Aqui:
copie o ambiente, a luz e o clima — nunca o objeto que aparece nela.

Sem isso, subir a foto de um bar com um cinzeiro de outra marca faria o
gerador desenhar o cinzeiro da foto.
"""

import json

MODELO_VISAO = "claude-opus-5"

# O que se pergunta sobre cada foto. Curto de propósito: descrição longa vira
# roteiro, e roteiro é o que faz as oito imagens saírem iguais.
_ESQUEMA = {
    "type": "object",
    "properties": {
        "cenarios": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "indice": {"type": "integer"},
                    "ambiente": {"type": "string"},
                    "luz": {"type": "string"},
                    "materiais": {"type": "string"},
                    "clima": {"type": "string"},
                    "serve_para": {
                        "type": "array", "items": {"type": "string"}},
                },
                "required": ["indice", "ambiente", "luz", "materiais",
                             "clima", "serve_para"],
            },
        },
    },
    "required": ["cenarios"],
}


def _sem_visao(motivo):
    return {"cenarios": [], "erro": motivo}


# As assinaturas de arquivo que a visão da Anthropic aceita. Declarar o tipo
# errado não degrada a leitura: ela é RECUSADA inteira, com 400.
_ASSINATURAS = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),
)


def _mime(dados):
    """O tipo real dos bytes. JPEG quando não der para saber.

    O padrão é JPEG e não PNG de propósito: é o que sai de câmera, de celular
    e do Drive, e era o que estava sendo declarado como PNG.
    """
    b = bytes(dados or b"")[:12]
    for assinatura, tipo in _ASSINATURAS:
        if b.startswith(assinatura):
            if tipo == "image/webp" and b[8:12] != b"WEBP":
                continue
            return tipo
    return "image/jpeg"


def descrever(imagens_bytes, tipos_disponiveis, nome_produto="", api_key=None):
    """Descreve o CENÁRIO de cada referência e diz em que peça cada uma cabe.

    Devolve {"cenarios": [...]} ou {"cenarios": [], "erro": "..."} — nunca
    levanta. Falha de visão não pode impedir a geração: sem descrição, a peça
    sai com a ambientação escrita pelo colaborador, que é o comportamento de
    antes deste módulo.
    """
    if not imagens_bytes:
        return {"cenarios": []}
    try:
        import anthropic
        import base64
        import chaves as _ch
    except Exception as e:
        return _sem_visao(f"{type(e).__name__}")

    chave = api_key or _ch.ler("ANTHROPIC_API_KEY")
    if not chave:
        return _sem_visao("ANTHROPIC_API_KEY não configurada")

    conteudo = []
    # Limite de oito: acima disso a leitura fica cara e a escolha não melhora
    # — o colaborador que sobe quinze cenários está mandando o mesmo clima
    # quinze vezes.
    for i, b in enumerate(list(imagens_bytes)[:8]):
        conteudo.append({"type": "text", "text": f"Referência {i}:"})
        conteudo.append({
            "type": "image",
            # O TIPO SAI DOS BYTES, NUNCA DE UM PALPITE.
            #
            # Aqui estava "image/png" fixo. A colaboradora sobe JPEG — que é
            # o que sai de celular e do Drive —, a Anthropic conferiu os bytes
            # contra o tipo declarado e recusou a requisição inteira com
            # `messages.0.content.1.image.source`. Na tela virou "Não
            # consegui ler as referências de ambientação", e as oito peças
            # saíram sem cenário nenhum.
            "source": {"type": "base64", "media_type": _mime(b),
                       "data": base64.b64encode(b).decode("utf-8")},
        })
    conteudo.append({"type": "text", "text": (
        f"São fotos de REFERÊNCIA DE AMBIENTAÇÃO para o produto "
        f"«{nome_produto or 'um produto'}».\n\n"
        "Para CADA referência, descreva o CENÁRIO — e apenas o cenário:\n"
        "- ambiente: que lugar é (sala, bar, bancada de cozinha, varanda…)\n"
        "- luz: direção, temperatura, dureza\n"
        "- materiais: superfícies e texturas visíveis\n"
        "- clima: a sensação que a foto passa em poucas palavras\n"
        "- serve_para: entre estes tipos de peça, em quais este cenário cabe "
        f"bem — {', '.join(tipos_disponiveis)}\n\n"
        "IGNORE COMPLETAMENTE o produto que aparece na foto: ele não é o "
        "nosso e não deve ser descrito nem reproduzido. Descreva o lugar, a "
        "luz e o clima — nunca o objeto.\n\n"
        "Uma mesma referência pode servir a vários tipos, e um tipo pode não "
        "ter nenhuma. Não force correspondência.")})

    try:
        cliente = anthropic.Anthropic(api_key=chave)
        resp = cliente.messages.create(
            model=MODELO_VISAO, max_tokens=2000,
            output_config={"format": {"type": "json_schema",
                                      "schema": _ESQUEMA}},
            messages=[{"role": "user", "content": conteudo}],
        )
        bruto = "".join(getattr(b, "text", "") for b in resp.content)
        dados = json.loads(bruto)
    except Exception as e:
        return _sem_visao(f"{type(e).__name__}: {str(e)[:120]}")
    if not isinstance(dados, dict) or "cenarios" not in dados:
        return _sem_visao("resposta da visão fora do formato")
    return dados


def para_o_tipo(descricao, tipo):
    """O bloco de cenário para ESTE tipo de peça. "" quando não há.

    Quando mais de uma referência serve, vence a PRIMEIRA que o colaborador
    subiu: ordem de upload é a única preferência que ele consegue expressar
    sem digitar nada.
    """
    for c in (descricao or {}).get("cenarios", []):
        serve = [str(x).strip() for x in (c.get("serve_para") or [])]
        if any(_casa(tipo, s) for s in serve):
            return _texto(c)
    return ""


def _casa(tipo, alvo):
    """O tipo bate com o que a visão devolveu?

    Compara pelo NÚMERO quando ele existe ("3 — Benefícios…" contra "3"), e
    por trecho de texto quando não. A visão devolve o rótulo de volta com
    variações — travessão trocado, acento comido —, e exigir igualdade exata
    faria toda correspondência falhar em silêncio.
    """
    t, a = str(tipo).strip(), str(alvo).strip()
    if not t or not a:
        return False
    n_t = t.split("—")[0].strip().split(" ")[0]
    n_a = a.split("—")[0].strip().split(" ")[0]
    if n_t.isdigit() and n_a.isdigit():
        return n_t == n_a
    return a.lower()[:14] in t.lower() or t.lower()[:14] in a.lower()


def _texto(c):
    return (
        "CENÁRIO DE REFERÊNCIA (copie o AMBIENTE, nunca o produto que "
        "aparecia nela):\n"
        f"- ambiente: {c.get('ambiente', '')}\n"
        f"- luz: {c.get('luz', '')}\n"
        f"- materiais: {c.get('materiais', '')}\n"
        f"- clima: {c.get('clima', '')}\n"
        "- Reproduza este ambiente com o NOSSO produto dentro dele, na "
        "escala real dele. O objeto da foto de referência não existe nesta "
        "peça.\n")


def resumo(descricao, tipos):
    """Uma linha por tipo, para a tela dizer qual cenário foi escolhido.

    Sem isto o colaborador sobe cinco fotos e não faz ideia de qual o Studio
    usou em qual peça — e quando o resultado sai errado, não há o que ajustar
    porque não há o que ver.
    """
    fora = []
    for t in tipos:
        c = para_o_tipo(descricao, t)
        if c:
            amb = c.split("- ambiente: ", 1)[-1].split("\n")[0]
            fora.append(f"{t} → {amb}")
        else:
            fora.append(f"{t} → (sem referência; usa o tema descrito)")
    return fora


# ── Conferência ──────────────────────────────────────────────────────────────
# `python3 ambientacao_ref.py`. A chamada de visão não se testa sem gastar API;
# o que se testa — e é onde os defeitos moram — é a ESCOLHA e o que ela devolve.
if __name__ == "__main__":
    import sys
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    T3 = "3 — Benefícios no cenário de uso"
    T7 = "7 — Presenteie"
    T8 = "8 — Ambientação realista (sem texto)"

    D = {"cenarios": [
        {"indice": 0, "ambiente": "bar com mesa de sinuca ao fundo",
         "luz": "quente, lateral, âmbar", "materiais": "madeira, couro",
         "clima": "noturno e acolhedor", "serve_para": [T3, T8]},
        {"indice": 1, "ambiente": "mesa posta com papel de seda",
         "luz": "difusa e clara", "materiais": "linho, papel",
         "clima": "festivo", "serve_para": [T7]},
    ]}

    # ── a escolha ────────────────────────────────────────────────────────
    ok("a peça 3 pega o bar", "sinuca" in para_o_tipo(D, T3))
    ok("a 8 também", "sinuca" in para_o_tipo(D, T8))
    ok("a 7 pega a mesa posta", "papel de seda" in para_o_tipo(D, T7))
    ok("tipo sem referência devolve vazio",
       para_o_tipo(D, "5 — Características técnicas") == "")
    ok("descrição vazia não quebra",
       para_o_tipo({}, T3) == "" and para_o_tipo(None, T3) == "")

    # A visão devolve o rótulo com variação — travessão, acento, corte.
    D2 = {"cenarios": [{"indice": 0, "ambiente": "sala", "luz": "x",
                        "materiais": "y", "clima": "z",
                        "serve_para": ["3", "8 - Ambientacao realista"]}]}
    ok("casa pelo número quando a visão devolve só ele",
       "sala" in para_o_tipo(D2, T3))
    ok("e com travessão e acento trocados", "sala" in para_o_tipo(D2, T8))
    ok("não casa com tipo diferente", para_o_tipo(D2, T7) == "")

    # ── o que o bloco manda fazer ────────────────────────────────────────
    txt = para_o_tipo(D, T3)
    ok("o bloco manda copiar o AMBIENTE", "copie o AMBIENTE" in txt)
    ok("e diz explicitamente para ignorar o produto da foto",
       "nunca o produto" in txt and "não existe nesta peça" in txt)
    ok("e repete a escala real", "escala real" in txt)

    # ── o resumo para a tela ─────────────────────────────────────────────
    r = resumo(D, [T3, T7, "5 — Características técnicas"])
    ok("o resumo diz o cenário escolhido de cada peça", len(r) == 3)
    ok("e avisa quando não há", "sem referência" in r[2])
    ok("o texto do resumo nomeia o ambiente", "sinuca" in r[0])

    # ── falha de visão não derruba nada ──────────────────────────────────
    ok("sem imagem devolve lista vazia sem erro",
       descrever([], [T3]) == {"cenarios": []})
    _f = _sem_visao("timeout")
    ok("falha vira erro declarado, e não silêncio",
       _f["cenarios"] == [] and _f["erro"] == "timeout")
    ok("e a escolha sobre uma falha devolve vazio", para_o_tipo(_f, T3) == "")

    # O TIPO DO ARQUIVO — o que derrubou a leitura das referencias em 24/09.
    ok("PNG e reconhecido",
       _mime(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0d") == "image/png")
    ok("JPEG e reconhecido",
       _mime(b"\xff\xd8\xff\xe0\x00\x10JFIF") == "image/jpeg")
    ok("GIF e reconhecido", _mime(b"GIF89a\x00\x00") == "image/gif")
    ok("WEBP e reconhecido",
       _mime(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp")
    ok("RIFF que nao e WEBP nao passa por WEBP",
       _mime(b"RIFF\x00\x00\x00\x00WAVEfmt ") == "image/jpeg")
    ok("bytes desconhecidos caem em JPEG, nao em PNG",
       _mime(b"qualquer coisa") == "image/jpeg")
    ok("vazio nao quebra", _mime(b"") == "image/jpeg")
    # A regressao em uma linha: o tipo NAO pode voltar a ser fixo.
    _fonte_ar = open(__file__, encoding="utf-8").read().split("if __name__")[0]
    ok('nenhum "image/png" fixo no bloco de imagem',
       chr(34) + "media_type" + chr(34) + ': "image/png"' not in _fonte_ar)

    print("\nfalhas:", falhas)
    sys.exit(falhas)
