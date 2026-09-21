"""rotulos.py — o que aparece na tela começa com maiúscula, e em português.

A REGRA, DITA PELO DONO
-----------------------
    "não pode ter nada em inglês no Studio e nem nenhum indicador iniciando em
     letra minúscula; se for 2 palavras a segunda pode estar em minúscula"

    Ano de vencimento   ·   Situação   ·   Data do pagamento

POR QUE UMA FUNÇÃO, E NÃO UM ACHE-E-SUBSTITUA
---------------------------------------------
Os cabeçalhos das tabelas do Studio não são textos de tela: são as CHAVES dos
dicionários que montam o DataFrame, e o código lê por essas chaves. Trocar
`"situacao"` por `"Situação"` no lugar errado quebra a leitura em silêncio.

Então a chave continua minúscula, do jeito que o código gosta, e o rótulo é
calculado aqui. Um lugar só: a próxima tela nasce obedecendo sem ninguém
lembrar da regra.
"""

# Palavras que NÃO se capitalizam quando caem no meio, e siglas que ficam como
# estão. Sem esta lista, "Valor Do Mês" — que ninguém escreve assim.
SIGLAS = {"ml", "cnpj", "cpf", "id", "pix", "ted", "doc", "das", "nf", "sku",
          "tv", "ia", "cmv", "vt", "vr"}


def tela(texto):
    """O texto de um `st.error`/`st.info`/`st.warning`, sem virar matemática.

    O AVISO QUE SAIU ASSIM
    ----------------------
        O envio (R2.300,00)émaiorqueacompra(R 1.814,20)

    O markdown do Streamlit lê `$…$` como fórmula de LaTeX. DOIS `R$` no mesmo
    texto fecham um par: os cifrões somem, o miolo gruda e sai em itálico. O
    número continua lá — e ilegível, que é pior do que sumir.

    POR QUE AQUI, E NÃO EM CADA CHAMADA
    -----------------------------------
    Já estava resolvido com `R\$` escrito à mão em quatro lugares
    (`app.py:1490`, `financeiro.py:276`, `:295`, `:302`) e em nenhum outro — a
    correção num caminho só, de novo.

    E escapar chamada por chamada não fecha a classe: onde o `R$` vem de um
    helper (`_brl`, `formatar_br`), o cifrão não está escrito na chamada. Uma
    varredura por AST passa por ela sem ver nada, e foi exatamente o que
    aconteceu com `cheques_tela.py` — a peneira aprovou justo a linha que
    quebrou na tela.

    `_brl` continua devolvendo `R$` puro: ela também alimenta tabela e HTML,
    onde a barra invertida apareceria escrita. Quem escapa é quem entrega ao
    `st.*`, que é este lugar.
    """
    return str(texto if texto is not None else "").replace("$", "\\$")


def rotular(chave):
    """`"data pagamento"` -> `"Data pagamento"`. Só a primeira letra sobe.

    Underscore vira espaço, porque a chave é de código e o rótulo é de gente.
    Sigla conhecida sai em maiúscula inteira. O que já começa com maiúscula,
    emoji ou símbolo passa intacto — quem escreveu assim, escreveu de propósito.
    """
    t = str(chave or "").replace("_", " ").strip()
    if not t:
        return ""
    palavras = []
    for i, p in enumerate(t.split()):
        if p.lower() in SIGLAS:
            palavras.append(p.upper())
        elif i == 0:
            # Só a PRIMEIRA letra, e sem mexer no resto: `capitalize()` baixaria
            # o resto da palavra e transformaria "MERCADORIA" em "Mercadoria".
            palavras.append(p[0].upper() + p[1:] if p[0].isalpha() else p)
        else:
            palavras.append(p)
    return " ".join(palavras)


def colunas(chaves, apelidos=None):
    """{chave: rótulo} para um cabeçalho de tabela inteiro.

    `apelidos` sobrescreve o cálculo onde o nome de tela não é o da chave —
    "envio" é frete, "estoque" é mercadoria, e nenhuma das duas se adivinha.
    """
    apelidos = apelidos or {}
    return {c: apelidos.get(c, rotular(c)) for c in (chaves or [])}


# Como cada chave deste repositório se chama na tela, quando o nome de código
# não serve. Fica aqui, e não espalhado pelas telas, pelo mesmo motivo de
# sempre: a mesma coluna aparece em quatro lugares.
APELIDOS = {
    # ENVIO e ESTOQUE ficam com o nome da planilha do dono, e não com o meu.
    #
    # Eu tinha traduzido para "Frete" e "Mercadoria" achando que era o mesmo
    # com nome melhor. Não é: a divisão não é contábil, é PREVISÃO DE CAIXA. O
    # que é envio a plataforma devolve com data marcada; o que é estoque só
    # volta quando a peça vender, e ninguém sabe quando. São dois horizontes
    # diferentes de dinheiro voltando, e é isso que os nomes dele carregam.
    "envio": "Envio",
    "estoque": "Estoque",
    "folha": "Folha",
    "situacao": "Situação",
    "observacao": "Observação",
    "descricao": "Descrição",
    "mes": "Mês",
    "data_pagamento": "Data do pagamento",
    "lancamento_id": "Lançamento",
    "recebido_em": "Recebido em",
    "quem_enviou": "Quem enviou",
    "atualizado_em": "Atualizado em",
    "atualizado_por": "Atualizado por",
    "conferido_em": "Conferido em",
    "vigente_desde": "Vigente desde",
    "dia_debito": "Dia do débito",
    "forma_pagamento": "Forma de pagamento",
    "valor_mensal": "Valor mensal",
    "salario_base": "Salário base",
    "vale_transporte": "Vale-transporte",
    "nome_produto": "Nome do produto",
}


def config(chaves, st, tipos=None, apelidos=None):
    """O `column_config` do Streamlit com os rótulos já em português.

    `tipos` traz as colunas que precisam de formato — {"valor": "brl"} ou
    {"apagar": "check"} — para a tela não ter de repetir o rótulo só porque
    quis um formato.
    """
    tipos = tipos or {}
    nomes = colunas(chaves, {**APELIDOS, **(apelidos or {})})
    fora = {}
    for c, rot in nomes.items():
        t = tipos.get(c)
        if t == "brl":
            fora[c] = st.column_config.NumberColumn(rot, format="R$ %.2f")
        elif t == "check":
            fora[c] = st.column_config.CheckboxColumn(rot)
        elif t is None:
            fora[c] = rot
        else:
            fora[c] = t
    return fora


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    ok("uma palavra sobe a primeira letra", rotular("situação") == "Situação")
    ok("duas palavras: so a primeira sobe",
       rotular("ano de vencimento") == "Ano de vencimento")
    ok("underscore vira espaco",
       rotular("data_pagamento") == "Data pagamento")
    ok("o que ja esta certo passa intacto",
       rotular("Ano de vencimento") == "Ano de vencimento")
    # `capitalize()` baixaria o resto: MERCADORIA viraria Mercadoria.
    ok("palavra toda em maiuscula nao e rebaixada",
       rotular("MERCADORIA") == "MERCADORIA")
    ok("sigla sai inteira em maiuscula", rotular("id") == "ID"
       and rotular("codigo ml") == "Codigo ML")
    ok("simbolo na frente nao atrapalha", rotular("% do mes") == "% do mes")
    ok("vazio nao derruba", rotular("") == "" and rotular(None) == "")

    _c = colunas(["folha", "vencimento", "valor", "envio", "estoque"], APELIDOS)
    ok("o cabecalho inteiro sai em portugues e com maiuscula",
       _c == {"folha": "Folha", "vencimento": "Vencimento", "valor": "Valor",
              "envio": "Envio", "estoque": "Estoque"})
    # ENVIO e ESTOQUE ficam com o nome da planilha do dono: a divisao e
    # previsao de caixa, e nao contabilidade. "Frete" e "Mercadoria" perdiam
    # isso.
    ok("apelido vence o calculo",
       colunas(["envio"], {"envio": "Custo de envio"})["envio"] == "Custo de envio")
    ok("sem apelido, vale a regra",
       colunas(["vencimento"])["vencimento"] == "Vencimento")

    # Nenhum rotulo pode sair minusculo — e a regra inteira, num teste so.
    _todos = colunas(
        ["folha", "vencimento", "valor", "envio", "estoque", "favorecido",
         "situacao", "observacao", "descricao", "finalidade", "conta", "data",
         "sentido", "tipo", "saldo", "meta", "realizado", "informado"],
        APELIDOS)
    ok("nenhum cabecalho comeca em minuscula",
       all(r[0].isupper() for r in _todos.values() if r[0].isalpha()))

    # ── O cifrao do real nao vira formula ────────────────────────────────
    ok("dois R$ no mesmo texto saem escapados",
       tela("de R$ 10,00 para R$ 20,00")
       == "de R\\$ 10,00 para R\\$ 20,00")
    ok("um R$ sozinho tambem — nao se adivinha quem faz par",
       tela("R$ 5,00") == "R\\$ 5,00")
    ok("texto sem cifrao passa intacto",
       tela("Nada mudou.") == "Nada mudou.")
    ok("None nao vira 'None' na tela", tela(None) == "")
    ok("numero tambem passa", tela(12) == "12")

    print("\nfalhas:", falhas)
