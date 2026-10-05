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
                # SAIDA ESTRUTURADA EXIGE ISTO EM TODO OBJETO.
                #
                # Sem `additionalProperties: false`, a API recusa a requisicao
                # inteira com 400 `output_config.format.schema`. Em producao,
                # 28/09, a mensagem na tela foi "Nao consegui ler as
                # referencias de ambientacao" — e as oito pecas sairam com o
                # tema escrito, sem olhar nenhuma das referencias que o dono
                # tinha subido.
                #
                # O esquema da conferencia de ajuste (`imagem.py`) sempre teve
                # a linha; este nasceu sem ela. Mesma regra, dois lugares, uma
                # resposta so — e foi o que faltou.
                "additionalProperties": False,
            },
        },
    },
    "required": ["cenarios"],
    "additionalProperties": False,
}


def _sem_visao(motivo):
    return {"cenarios": [], "erro": motivo}


# ── O TETO DE TOKENS SAI DA CONTA, E NAO DE UM NUMERO ESCRITO A MAO ───────
#
# Era `max_tokens=2000` fixo. Cada referencia devolve ambiente, luz,
# materiais, clima e a lista de tipos que ela serve — em portugues, que gasta
# mais token que ingles. Com oito referencias a resposta passa de 2000 e vem
# CORTADA no meio de uma string.
#
# O numero por referencia foi medido no corte real de 05/10: 4586 caracteres
# em 8 referencias, com a resposta ainda inacabada. A 3,5 caracteres por
# token isso ja e ~1300 tokens so do que chegou, e faltava fechar. 400 por
# referencia da folga de duas vezes e meia sobre o observado.
TOKENS_POR_REFERENCIA = 400
TOKENS_DE_ABERTURA = 600


def teto_de_tokens(quantas):
    """O `max_tokens` para ler `quantas` referencias. Nunca menor que o fixo
    antigo — baixar o teto seria trocar um defeito por outro."""
    return max(2000, TOKENS_DE_ABERTURA + TOKENS_POR_REFERENCIA * int(quantas or 0))


def cenarios_inteiros(bruto):
    """Os cenarios COMPLETOS de um JSON cortado no meio. [] quando nao ha.

    Funcao pura. Ela existe porque perder oito cenarios por causa do oitavo
    e desperdicio: o que chegou fechado e tao bom quanto se a resposta
    tivesse terminado ali.

    SO OBJETO FECHADO ENTRA. Meio cenario no prompt seria pior que nenhum —
    "trocar uma voz contraditoria por voz nenhuma e pior" vale aqui tambem,
    e um cenario sem `clima` sai do schema que o resto do modulo espera.
    """
    import json as _json_ci
    t = str(bruto or "")
    i = t.find("[")
    if i < 0:
        return []
    fora, nivel, ini, dentro_str, escapa = [], 0, None, False, False
    for pos in range(i, len(t)):
        c = t[pos]
        if dentro_str:
            if escapa:
                escapa = False
            elif c == "\\":
                escapa = True
            elif c == '"':
                dentro_str = False
            continue
        if c == '"':
            dentro_str = True
        elif c == "{":
            if nivel == 0:
                ini = pos
            nivel += 1
        elif c == "}":
            nivel -= 1
            if nivel == 0 and ini is not None:
                try:
                    _o = _json_ci.loads(t[ini:pos + 1])
                except Exception:
                    _o = None
                if isinstance(_o, dict) and _o.get("ambiente"):
                    fora.append(_o)
                ini = None
    return fora


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
            model=MODELO_VISAO, max_tokens=teto_de_tokens(len(conteudo) // 2),
            output_config={"format": {"type": "json_schema",
                                      "schema": _ESQUEMA}},
            messages=[{"role": "user", "content": conteudo}],
        )
        bruto = "".join(getattr(b, "text", "") for b in resp.content)
        # ── O TETO BATEU? O SISTEMA TEM DE DIZER, NAO SO FALHAR ─────────
        #
        # 05/10, producao: `JSONDecodeError: Unterminated string starting at:
        # line 1 column 4587`. O `max_tokens` era 2000 FIXO, e a descricao de
        # oito referencias nao cabe nele: a resposta vinha cortada no meio de
        # uma string, o `json.loads` estourava, e a tela dizia "nao consegui
        # ler as referencias" — uma frase que nao ensina nada e manda procurar
        # no lugar errado. As oito pecas sairam sem cenario nenhum.
        #
        # E o limite silencioso que o oitavo verificador existe para pegar. O
        # `chat_assistente` ja lia `stop_reason` desde 29/09; este leitor
        # ficou para tras — a Forma 1, corrigir onde o sintoma apareceu.
        _cortou = getattr(resp, "stop_reason", "") == "max_tokens"
        try:
            dados = json.loads(bruto)
        except json.JSONDecodeError:
            # SALVAR O QUE CHEGOU INTEIRO vale mais que perder tudo: seis
            # cenarios lidos sao seis a mais do que zero. So entra cenario
            # COMPLETO — meio objeto no prompt seria pior que nenhum.
            _salvos = cenarios_inteiros(bruto)
            if not _salvos:
                return _sem_visao(
                    "a leitura foi CORTADA no limite de tokens e nao sobrou "
                    "nenhum cenario inteiro. Suba menos referencias de "
                    "ambientacao — cada uma custa leitura."
                    if _cortou else
                    f"resposta da visao veio quebrada: {bruto[:160]}")
            return {"cenarios": _salvos,
                    "erro": (f"a leitura foi CORTADA no limite de tokens: "
                             f"aproveitei {len(_salvos)} cenario(s) inteiro(s) "
                             f"e perdi o resto. Suba menos referencias.")}
    except Exception as e:
        # 120 CARACTERES ESCONDIAM A CAUSA. A mensagem da API dizia
        # `output_config.format.schema: ` e o resto — o nome do campo que
        # faltava — caia fora do corte. Ficou na tela um erro que nao
        # ensinava nada a ninguem.
        return _sem_visao(f"{type(e).__name__}: {str(e)[:400]}")
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

    # ── O TETO DE TOKENS, E O QUE SE SALVA QUANDO ELE BATE ──────────────
    #
    # 05/10, producao, teste do dono: `JSONDecodeError: Unterminated string
    # starting at: line 1 column 4587`. O `max_tokens` era 2000 FIXO e oito
    # referencias nao cabem nele. As oito pecas sairam sem cenario nenhum, e
    # a tela disse so "nao consegui ler as referencias".
    ok("o teto cresce com o numero de referencias",
       teto_de_tokens(8) > teto_de_tokens(2))
    ok("e oito referencias cabem com folga sobre o corte medido",
       teto_de_tokens(8) >= 3400)
    ok("mas o teto nunca fica MENOR que o fixo antigo",
       teto_de_tokens(0) >= 2000 and teto_de_tokens(1) >= 2000)

    # O CORTE DE VERDADE, com o tamanho medido no erro do dono: 4586
    # caracteres e a resposta ainda inacabada. O dado NAO e inventado — e o
    # formato que `_ESQUEMA` manda o modelo devolver, cortado onde o teto
    # bateu (Forma 7: valor escrito a mao mede o meu entendimento, e e ele
    # que costuma estar errado).
    _um = ('{"ambiente":"bar medieval a luz de vela","luz":"quente e baixa",'
           '"materiais":"pedra e madeira escura","clima":"acolhedor",'
           '"serve_para":["3 - Produto em uso"]}')
    # O OBJETO FECHADO MAS VAZIO E O CASO QUE O FILTRO EXISTE PARA PEGAR.
    #
    # Um fragmento ABERTO nunca fecha chave, entao ele cai fora sozinho — e
    # uma guarda feita so com ele nao mede o filtro: a mutacao que troca a
    # condicao por `True` fica verde. O que o filtro pega e o objeto que o
    # modelo FECHOU sem conteudo, que acontece quando o corte cai bem na
    # virada de um cenario para o outro.
    _vazio = '{"serve_para":[]}'
    _cortado = ('{"cenarios": [' + ",".join([_um] * 3) + "," + _vazio
                + ',{"ambiente":"varanda ao entard')
    _salvos = cenarios_inteiros(_cortado)
    ok("de um JSON cortado, os cenarios INTEIROS sao salvos",
       len(_salvos) == 3)
    ok("e o objeto fechado sem ambiente NAO entra",
       all(c.get("ambiente") and c.get("clima") for c in _salvos))
    ok("e o que sobrou e usavel pelo resto do modulo",
       bool(para_o_tipo({"cenarios": _salvos}, "3 - Produto em uso")))
    ok("JSON inteiro continua passando inteiro",
       len(cenarios_inteiros('{"cenarios": [' + _um + "]}")) == 1)
    ok("lixo sem colchete devolve lista vazia, e nao explode",
       cenarios_inteiros("desculpe, nao consegui") == []
       and cenarios_inteiros("") == [])
    # ASPAS ESCAPADAS NAO PODEM PARTIR O OBJETO NO MEIO.
    #
    # O varredor conta chaves FORA de string. Uma aspa escapada dentro do
    # texto fecharia a string cedo, e dali em diante ele contaria chaves que
    # estao DENTRO dela.
    #
    # E O DADO PRECISA DE UMA CHAVE NO TRECHO ESCAPADO. A primeira versao
    # usava um numero PAR de aspas escapadas, entao a conta se reequilibrava
    # sozinha e a mutacao que desliga o escape ficava VERDE — guarda que
    # nunca viu o defeito nunca foi guarda. Com `{` dentro do trecho
    # escapado, desligar o escape faz o nivel subir e o objeto nunca fechar.
    _esc = ('{"ambiente":"bar O Javali","luz":"vela \\"{\\" sombra",'
            '"materiais":"pedra","clima":"quente","serve_para":["3"]}')
    ok("aspas escapadas dentro do texto nao partem o cenario",
       len(cenarios_inteiros("[" + _esc + "]")) == 1)

    # E O `stop_reason` E LIDO. Sem isso o corte vira "resposta quebrada", que
    # manda procurar no lugar errado — e e o limite silencioso que o oitavo
    # verificador existe para pegar.
    _fonte_tk = open(__file__, encoding="utf-8").read().split("if __name__")[0]
    ok("o corte por teto de tokens e RECONHECIDO, e nao vira erro generico",
       'stop_reason' in _fonte_tk and "CORTADA no limite de tokens" in _fonte_tk)

    # ── O ESQUEMA DA SAIDA ESTRUTURADA ──────────────────────────────────
    #
    # 28/09, producao: "Nao consegui ler as referencias de ambientacao
    # (BadRequestError: 400 ... output_config.format.schema)". A API recusa o
    # esquema inteiro quando um objeto nao declara `additionalProperties`.
    # As oito pecas sairam com o tema escrito, sem olhar NENHUMA das
    # referencias que o dono tinha subido.
    def _objetos(no, caminho="raiz"):
        """Todo objeto do esquema, com o caminho ate ele."""
        fora = []
        if isinstance(no, dict):
            if no.get("type") == "object":
                fora.append((caminho, no))
            for ch, v in no.items():
                fora += _objetos(v, f"{caminho}.{ch}")
        elif isinstance(no, list):
            for i, v in enumerate(no):
                fora += _objetos(v, f"{caminho}[{i}]")
        return fora

    _objs = _objetos(_ESQUEMA)
    ok("o esquema tem os dois objetos (a raiz e o cenario)", len(_objs) == 2)
    _sem = [c for c, o in _objs if o.get("additionalProperties") is not False]
    ok("todo objeto declara additionalProperties: false", not _sem)
    _sem_req = [c for c, o in _objs if not o.get("required")]
    ok("e todo objeto declara required", not _sem_req)
    # REQUIRED TEM DE LISTAR TODAS AS PROPRIEDADES, senao a API tambem recusa.
    _faltando = [(c, set(o["properties"]) - set(o.get("required") or []))
                 for c, o in _objs if o.get("properties")]
    ok("required lista todas as propriedades",
       all(not f for _c, f in _faltando))

    # O MOTIVO DO ERRO NAO PODE VOLTAR CORTADO: 120 caracteres escondiam
    # justamente o nome do campo que faltava.
    ok("o motivo do erro chega inteiro na tela",
       "[:400]" in _fonte_ar and "[:120]" not in _fonte_ar)

    print("\nfalhas:", falhas)
    sys.exit(falhas)
