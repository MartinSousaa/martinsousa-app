"""chaves.py — as chaves de API, lidas de um jeito só e cobradas em voz alta.

DOIS DEFEITOS, O MESMO PARA TODA CHAVE
--------------------------------------
1. `st.secrets.get("X", "")` NÃO é um `dict.get`: sem arquivo de secrets ele
   LEVANTA em vez de devolver o padrão. E, no Railway, variável de ambiente não
   vira `st.secrets` — só o bloco `STREAMLIT_SECRETS` que o Procfile escreve.
   Quem lê só um dos dois lados perde a chave que está no outro.

2. Chave ausente virava silêncio. O caso que custou caro: sem `OPENAI_API_KEY`,
   o motor primário de imagem nem era tentado — toda geração caía no reserva
   (Gemini), que tem cota própria. A cota do reserva acabou fazendo o trabalho
   dos dois, e a única mensagem na tela falava de crédito do Gemini. A pergunta
   que sobrou para o dono — "como acabaram os créditos, se ele é o reserva?" —
   era impossível de responder olhando para a tela.

   Onde não havia nem esse silêncio, havia coisa pior: `tit_ml` e
   `palavras_chave` mandavam a chave vazia para a API e o colaborador recebia
   um erro de autenticação que não diz o que fazer.

UMA REGRA, E NÃO UMA CÓPIA
--------------------------
O jeito de ler mora aqui. Cada tela diz de que chave precisa e PARA QUÊ, e a
mensagem que falta sai pronta, em português, dizendo onde resolver.
"""

import os

# Para que serve cada uma, na língua de quem vai ler o aviso.
PARA_QUE = {
    "ANTHROPIC_API_KEY": "escrever título, descrição, palavras-chave e conferir "
                         "o texto das imagens",
    "OPENAI_API_KEY": "gerar imagem no motor primário (gpt-image-2)",
    "GEMINI_API_KEY": "gerar imagem no motor reserva",
    "SERPAPI_KEY": "pesquisar concorrentes na hora de escrever a descrição",
    "TRELLO_KEY": "ler os cartões do Trello",
    "TRELLO_TOKEN": "ler os cartões do Trello",
}


def ler(nome):
    """O valor da chave, dos DOIS lugares onde ela pode estar. "" se não há.

    A ordem não importa para o resultado, mas o `try` importa: `st.secrets`
    levanta quando não existe arquivo de secrets, e essa exceção, solta dentro
    de um `try` alheio, já foi lida como "a chave não existe".
    """
    try:
        import streamlit as st
        v = st.secrets.get(nome, "")
        if v:
            return str(v).strip()
    except Exception:
        pass
    return str(os.environ.get(nome, "") or "").strip()


def tem(nome):
    return bool(ler(nome))


def aviso_de_falta(nome, o_que_para_de_funcionar=""):
    """A frase que a tela mostra quando a chave não está lá. "" quando está.

    Ela diz três coisas, e as três são necessárias: o que parou, por causa de
    quê, e onde se resolve. Faltando a última, o aviso vira reclamação.
    """
    if tem(nome):
        return ""
    para = o_que_para_de_funcionar or PARA_QUE.get(nome, "esta função")
    return (f"**`{nome}` não está configurada.** Sem ela, o Studio não "
            f"consegue {para}. Configure nas variáveis do Railway (ou no "
            f"`.streamlit/secrets.toml`, em desenvolvimento).")


def exigir(nome, o_que_para_de_funcionar=""):
    """(valor, aviso). Valor vazio vem sempre acompanhado do aviso pronto."""
    return ler(nome), aviso_de_falta(nome, o_que_para_de_funcionar)


def faltando(*nomes):
    """As que não estão configuradas, na ordem em que foram pedidas."""
    return [n for n in nomes if not tem(n)]


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    _antes = {k: os.environ.get(k) for k in ("OPENAI_API_KEY", "ZZZ_TESTE")}
    os.environ.pop("ZZZ_TESTE", None)

    # O caso real: a chave existe SÓ na variável de ambiente do Railway.
    os.environ["ZZZ_TESTE"] = "valor-do-railway"
    ok("chave que só está no ambiente é encontrada", ler("ZZZ_TESTE") == "valor-do-railway")
    ok("e tem() concorda", tem("ZZZ_TESTE") is True)
    ok("com ela, não há aviso", aviso_de_falta("ZZZ_TESTE") == "")

    os.environ.pop("ZZZ_TESTE", None)
    ok("sem ela, o valor é vazio e NÃO levanta", ler("ZZZ_TESTE") == "")
    _av = aviso_de_falta("ZZZ_TESTE")
    ok("e o aviso diz onde resolver", "Railway" in _av and "ZZZ_TESTE" in _av)

    _v, _a = exigir("OPENAI_API_KEY")
    ok("exigir devolve valor e aviso juntos", isinstance(_v, str) and isinstance(_a, str))
    ok("e um so existe quando o outro nao",
       bool(_v) != bool(_a))

    os.environ["ZZZ_TESTE"] = "x"
    ok("faltando lista so as ausentes",
       faltando("ZZZ_TESTE", "ZZZ_NAO_EXISTE") == ["ZZZ_NAO_EXISTE"])
    ok("e devolve vazio quando estao todas",
       faltando("ZZZ_TESTE") == [])

    # O aviso nomeia PARA QUE serve, e nao so o nome da variavel.
    os.environ.pop("OPENAI_API_KEY", None)
    ok("o aviso da chave de imagem fala do motor primario",
       "primário" in aviso_de_falta("OPENAI_API_KEY"))
    ok("e da para escrever um motivo proprio",
       "gerar o vídeo" in aviso_de_falta("OPENAI_API_KEY", "gerar o vídeo"))

    for _k, _val in _antes.items():
        if _val:
            os.environ[_k] = _val
        else:
            os.environ.pop(_k, None)
    os.environ.pop("ZZZ_TESTE", None)
    print("\nfalhas:", falhas)
