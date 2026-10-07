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


# ── Dinheiro: R$ 58.490,56 em todas as tabelas ──────────────────────────────
#
# Dono, 07/10: "Formate todos os números referente a dinheiro dessa maneira"
# — R$ 58.490,56. O `format="R$ %.2f"` do Streamlit é printf: não tem
# separador de milhar e põe ponto no decimal (R$ 58490.56).
#
# A COLUNA DE DINHEIRO SE DECLARA ASSIM: `format="R$ %.2f"` (ou `rotulos.config`
# com tipo "brl"). Quem desenha é este lugar, para todas as telas de uma vez:
#
#   st.dataframe   → a coluna vira o texto "R$ 58.490,56". É só leitura, e o
#                    texto custa uma passada de string por linha. O `Styler`
#                    do pandas fazia o mesmo mantendo o número, mas desenha
#                    TODAS as células da tabela em Python: 1,5 s por passada
#                    numa tabela de 3.000 linhas, medido.
#   st.data_editor → a coluna continua NÚMERO (o código lê o que volta, e texto
#                    ali quebraria a conta) e sai "localized": 58.490,56 no
#                    navegador em português, sem o "R$" na célula.
MOEDA_PREFIXO = "R$"


def brl(v, casas=2):
    """58490.56 → "R$ 58.490,56". Vazio para o que não é número."""
    if v is None:
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)          # já veio texto: não some da tela
    if f != f:                                   # NaN
        return ""
    txt = f"{abs(f):,.{casas}f}".replace(",", "§").replace(".", ",").replace("§", ".")
    # "R$ -12,50": a mesma grafia dos `_brl` das telas, para a tabela e o
    # texto ao lado não escreverem o negativo de dois jeitos.
    return "R$ " + ("-" if f < 0 else "") + txt


def _eh_moeda(cfg):
    if not isinstance(cfg, dict):
        return False
    tc = cfg.get("type_config") or {}
    return (tc.get("type") == "number"
            and str(tc.get("format") or "").strip().startswith(MOEDA_PREFIXO))


def preparar_tabela(data, column_config, editavel):
    """(data, column_config) com o dinheiro no formato do dono. Pura.

    `editavel` = é um `st.data_editor`. Nada além das colunas de dinheiro muda,
    e o DataFrame de quem chamou não é tocado (cópia).
    """
    if not isinstance(column_config, dict):
        return data, column_config
    moeda = [c for c, v in column_config.items() if _eh_moeda(v)]
    if not moeda:
        return data, column_config
    cfg = dict(column_config)
    if editavel:
        for c in moeda:
            cfg[c] = {**cfg[c], "type_config": {**cfg[c]["type_config"],
                                                "format": "localized"}}
        return data, cfg
    try:
        import pandas as pd
    except ImportError:
        return data, column_config
    if not isinstance(data, pd.DataFrame):
        return data, column_config
    presentes = [c for c in moeda if c in data.columns]
    if not presentes:
        return data, column_config
    data = data.copy()
    for c in presentes:
        casas = 0 if "%.0f" in str(cfg[c]["type_config"].get("format")) else 2
        data[c] = data[c].map(lambda v, _k=casas: brl(v, _k))
        cfg[c] = {k: v for k, v in cfg[c].items() if k != "type_config"}
        cfg[c]["type_config"] = {"type": "text"}
    return data, cfg


def instalar_moeda(st):
    """Faz `st.dataframe` e `st.data_editor` passarem por `preparar_tabela`.

    Chamado uma vez pelo `app.py`. É idempotente: o Streamlit roda o script de
    novo a cada clique, e embrulhar o embrulho a cada passada empilharia
    funções até estourar.
    """
    for nome, editavel in (("dataframe", False), ("data_editor", True)):
        original = getattr(st, nome, None)
        if original is None or getattr(original, "_ms_moeda", False):
            continue

        def _embrulho(*a, _orig=original, _ed=editavel, **k):
            if "column_config" in k:
                dados = k["data"] if "data" in k else (a[0] if a else None)
                novo, k["column_config"] = preparar_tabela(
                    dados, k["column_config"], _ed)
                if novo is not dados:
                    if "data" in k:
                        k["data"] = novo
                    else:
                        a = (novo,) + tuple(a[1:])
            return _orig(*a, **k)

        _embrulho._ms_moeda = True
        _embrulho.__wrapped__ = original
        setattr(st, nome, _embrulho)


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

    # ── Dinheiro: R$ 58.490,56 ───────────────────────────────────────────
    ok("o formato do dono: milhar com ponto, decimal com virgula",
       brl(58490.56) == "R$ 58.490,56" and brl(-1234.5) == "R$ -1.234,50"
       and brl(0) == "R$ 0,00" and brl(None) == "" and brl(float("nan")) == ""
       and brl(1500.4, 0) == "R$ 1.500"
       and brl("a definir") == "a definir")
    import types as _ty
    import pandas as _pd_t
    import streamlit as _st_real
    # O column_config vem do Streamlit DE VERDADE: é o dicionário que a tela
    # monta, e não um que eu escrevi à mão.
    _cfg_t = {"valor": _st_real.column_config.NumberColumn("Valor", format="R$ %.2f"),
              "qtd": _st_real.column_config.NumberColumn("Qtd", format="%d"),
              "nome": "Nome"}
    _df_t = _pd_t.DataFrame({"valor": [58490.56, None], "qtd": [3, 4],
                             "nome": ["a", "b"]})
    _d2, _c2 = preparar_tabela(_df_t, _cfg_t, editavel=False)
    ok("na tabela de leitura o dinheiro vira o texto do dono",
       list(_d2["valor"]) == ["R$ 58.490,56", ""]
       and _c2["valor"]["type_config"]["type"] == "text"
       and _c2["valor"]["label"] == "Valor")
    ok("o resto da tabela, e o DataFrame de quem chamou, ficam como estavam",
       list(_d2["qtd"]) == [3, 4] and _c2["qtd"] is _cfg_t["qtd"]
       and _df_t["valor"].iloc[0] == 58490.56
       and _cfg_t["valor"]["type_config"]["format"] == "R$ %.2f")
    _d3, _c3 = preparar_tabela(_df_t, _cfg_t, editavel=True)
    ok("no editor o dinheiro continua numero, e sai localizado",
       _d3 is _df_t and _c3["valor"]["type_config"]["format"] == "localized"
       and _c3["valor"]["type_config"]["type"] == "number")
    ok("rotulos.config com tipo brl entra na mesma regra",
       _eh_moeda(config(["valor"], _st_real, {"valor": "brl"})["valor"]))

    # O caminho inteiro: instalar num modulo com a cara do `st`, chamar como as
    # telas chamam (posicional e por nome), e olhar o que CHEGOU ao original.
    _vistos = []
    _fake = _ty.SimpleNamespace(
        dataframe=lambda *a, **k: _vistos.append(("df", a, k)),
        data_editor=lambda *a, **k: _vistos.append(("ed", a, k)) or "editado")
    instalar_moeda(_fake)
    _primeiro = _fake.dataframe
    instalar_moeda(_fake)
    ok("instalar de novo nao embrulha o embrulho", _fake.dataframe is _primeiro)
    _fake.dataframe(_df_t, use_container_width=True, column_config=_cfg_t)
    _fake.dataframe(data=_df_t, column_config=_cfg_t)
    _ret = _fake.data_editor(_df_t, column_config=_cfg_t, key="x")
    ok("st.dataframe recebe o dinheiro formatado, chamado das duas maneiras",
       _vistos[0][1][0]["valor"].iloc[0] == "R$ 58.490,56"
       and _vistos[0][2]["use_container_width"] is True
       and _vistos[1][2]["data"]["valor"].iloc[0] == "R$ 58.490,56")
    ok("st.data_editor recebe numero, localizado, e devolve o que o original devolve",
       _vistos[2][1][0] is _df_t and _ret == "editado"
       and _vistos[2][2]["column_config"]["valor"]["type_config"]["format"] == "localized"
       and _vistos[2][2]["key"] == "x")
    _fake.dataframe(_df_t)
    ok("tabela sem column_config passa intacta", _vistos[3][1][0] is _df_t)
    ok("None nao vira 'None' na tela", tela(None) == "")
    ok("numero tambem passa", tela(12) == "12")

    print("\nfalhas:", falhas)
    # O conversor só vale se o app o instala — no MÓDULO, antes de qualquer
    # tela, e não dentro de função (o `app.py` tem uma função que chama uma
    # variável local de `rotulos`; ali dentro o nome seria outro).
    import ast as _ast_t
    import os as _os_t
    _raiz_t = _os_t.path.dirname(_os_t.path.abspath(__file__))
    _app_t = _ast_t.parse(open(_os_t.path.join(_raiz_t, "app.py"),
                               encoding="utf-8").read())
    ok("o app.py instala o dinheiro no nivel do modulo",
       any(isinstance(n, _ast_t.Expr) and isinstance(n.value, _ast_t.Call)
           and _ast_t.unparse(n.value) == "rotulos.instalar_moeda(st)"
           for n in _app_t.body))
    # E a coluna que se diz dinheiro no rótulo se declara dinheiro no formato
    # — senão sai de fora da regra, em silêncio (Forma 1: o irmão esquecido).
    _fora_t = []
    for _nome_t in sorted(_os_t.listdir(_raiz_t)):
        if not _nome_t.endswith(".py") or _nome_t.startswith("checar_"):
            continue
        try:
            _arv_t = _ast_t.parse(open(_os_t.path.join(_raiz_t, _nome_t),
                                       encoding="utf-8").read())
        except (SyntaxError, UnicodeDecodeError):
            continue
        for _n in _ast_t.walk(_arv_t):
            if not (isinstance(_n, _ast_t.Call)
                    and _ast_t.unparse(_n.func).endswith("column_config.NumberColumn")):
                continue
            _rot_n = (_n.args[0].value if _n.args and isinstance(_n.args[0], _ast_t.Constant)
                      else next((k.value.value for k in _n.keywords if k.arg == "label"
                                 and isinstance(k.value, _ast_t.Constant)), ""))
            _fmt_n = next((k.value.value for k in _n.keywords if k.arg == "format"
                           and isinstance(k.value, _ast_t.Constant)), "")
            if "R$" in str(_rot_n) and not str(_fmt_n).startswith(MOEDA_PREFIXO):
                _fora_t.append(f"{_nome_t}:{_n.lineno}")
    ok(f"toda coluna rotulada R$ tem format de dinheiro: {_fora_t}", not _fora_t)

    import sys as _sys_t
    _sys_t.exit(1 if falhas else 0)
