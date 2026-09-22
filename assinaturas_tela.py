"""assinaturas_tela.py — cadastro e vigilância das cobranças recorrentes.

DUAS COISAS NA MESMA TELA, E ELAS SE ALIMENTAM
-----------------------------------------------
Em cima, a grade do que se paga todo mês. Embaixo, o que o Studio achou de
errado nos extratos e nas faturas comparando com essa grade.

Separá-las em duas telas faria o alerta apontar para um cadastro que está em
outro lugar — e alerta que obriga a procurar onde corrigir é alerta que se
ignora na segunda semana.

A GRADE COMEÇA PREENCHIDA, E NÃO GRAVADA
-----------------------------------------
As quinze assinaturas que o dono levantou olhando as faturas aparecem na tela
vazia como sugestão. Elas só viram linha na planilha quando ele salvar: dado
que ninguém digitou é dado em que ninguém confia — e ele mesmo disse que a
lista pode estar incompleta.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

import assinaturas as _as

FUSO = timezone(timedelta(hours=-3))

# Quantos meses o Studio varre atrás de cobrança recorrente não cadastrada.
# Quatro cobre o mínimo de três repetições com uma folga de um mês.
MESES_DE_VARREDURA = 4


def _brl(v):
    return ("R$ " + f"{float(v or 0):,.2f}") \
        .replace(",", "X").replace(".", ",").replace("X", ".")


def _meses_recentes(quantos):
    hoje = datetime.now(FUSO).date()
    fora, a, m = [], hoje.year, hoje.month
    for _ in range(quantos):
        fora.append((a, m))
        m -= 1
        if m == 0:
            a, m = a - 1, 12
    return fora


def _lancamentos_por_mes(quantos):
    """{(ano, mês): [lançamentos]} — o que o Studio já tem dos extratos.

    Uma leitura só, repartida por mês. Ler mês a mês faria quatro downloads da
    mesma aba numa tela que abre com um clique.
    """
    try:
        import lancamentos as _lan
        todos = _lan.aplicar_cadastro(_lan.carregar())
    except Exception as e:
        return {}, f"{type(e).__name__}: {str(e)[:120]}"
    fora = {}
    for chave in _meses_recentes(quantos):
        alvo = f"{chave[0]:04d}-{chave[1]:02d}"
        fora[chave] = [l for l in todos
                       if str(l.get("data", "")).startswith(alvo)]
    return fora, ""


def _grade(usuario_logado):
    linhas = _as.carregar()
    vazia = not linhas
    if vazia:
        linhas = _as.sugestoes_como_linhas()
        st.info(
            "A grade está vazia. Abaixo estão as **15 assinaturas que você "
            "levantou nas faturas** — confira, corrija o que mudou e salve. "
            "Nada é gravado até você clicar em salvar."
        )

    df = pd.DataFrame(linhas)[
        ["item", "valor_mensal", "periodicidade", "favorecido",
         "forma_pagamento", "observacao"]]

    editado = st.data_editor(
        df, num_rows="dynamic", use_container_width=True, hide_index=True,
        key="assin_grade",
        column_config={
            "item": st.column_config.TextColumn("Assinatura", required=True),
            "valor_mensal": st.column_config.NumberColumn(
                "Valor", format="R$ %.2f", min_value=0.0,
                help="No caso da ANUAL, o valor CHEIO do ano. O Studio "
                     "rateia por 12 sozinho."),
            "periodicidade": st.column_config.SelectboxColumn(
                "Cobrança", options=list(_as.PERIODICIDADES)),
            "favorecido": st.column_config.TextColumn(
                "Como aparece no extrato",
                help="O nome que o Studio procura na descrição da cobrança. "
                     "Ex.: CANVA casa com 'MERCADO PAGO *CANVA'."),
            "forma_pagamento": st.column_config.TextColumn("Pagamento"),
            "observacao": st.column_config.TextColumn("Observação"),
        })

    total = _as.total_mensal(editado.to_dict("records"))
    c1, c2 = st.columns([1, 2])
    c1.metric("Peso mensal", _brl(total),
              help="A anual entra rateada por 12. É este número que vai ao "
                   "numerador do ponto de equilíbrio.")
    if c2.button("💾 Salvar assinaturas", type="primary"):
        ok, msg = _as.salvar(editado.to_dict("records"), usuario_logado or "")
        (st.success if ok else st.error)(msg)
        if ok:
            st.rerun()
    return editado.to_dict("records")


def _vigilancia(cadastro):
    st.markdown("### 🔍 O que não bateu")
    st.caption(
        "O Studio compara o cadastro acima com o que chegou nos extratos e "
        "nas faturas dos últimos "
        f"{MESES_DE_VARREDURA} meses. Ele não corrige nada — aponta para "
        "você olhar."
    )
    por_mes, erro = _lancamentos_por_mes(MESES_DE_VARREDURA)
    if erro:
        st.warning(f"Não consegui ler os lançamentos: {erro}")
        return
    if not any(por_mes.values()):
        st.info("Nenhum lançamento nos últimos meses para comparar.")
        return

    atual = _meses_recentes(1)[0]
    frases = _as.alertas(cadastro, por_mes, atual[0], atual[1])
    if not frases:
        st.success("Tudo bate com o cadastro. Nenhuma cobrança fora do "
                   "esperado no mês.")
        return
    for f in frases:
        if f.startswith("💸"):
            st.warning(f)
        elif f.startswith("🆕"):
            st.info(f)
        else:
            st.error(f)


def pagina(usuario_logado=None):
    import auth
    if not auth.eh_dono(usuario_logado):
        st.error("Esta tela é exclusiva do dono.")
        return

    st.markdown("### 🔁 Assinaturas")
    st.caption(
        "O que cobra sozinho todo mês. Elas são **custo fixo** — paga-se o "
        "mesmo Trello vendendo 100 ou 3.000 —, então entram no numerador do "
        "ponto de equilíbrio, e o Studio as subtrai do custo operacional por "
        "venda para o mesmo gasto não contar duas vezes."
    )

    cadastro = _grade(usuario_logado)
    st.markdown("---")
    _vigilancia(cadastro)

    st.caption(
        "Bling e Contabilidade **não** entram aqui de propósito: já são itens "
        "do Custo fixo, e repeti-los criaria a segunda resposta para a mesma "
        "pergunta."
    )


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    _src = open(__file__, encoding="utf-8").read()
    _codigo = "\n".join(l for l in _src.split("\n")
                        if not l.lstrip().startswith("#")) \
        .split("if __name__")[0]

    ok("a tela não reimplementa a conferência",
       "TOLERANCIA" not in _codigo and "def conferir(" not in _codigo)
    ok("ela usa o módulo", "_as.alertas(" in _codigo)
    ok("a porta está trancada na própria página", "auth.eh_dono" in _codigo)

    m = _meses_recentes(4)
    ok("os meses recentes vêm do mais novo para o mais velho", len(m) == 4)
    ok("e eles retrocedem de verdade",
       all((m[i][0], m[i][1]) != (m[i + 1][0], m[i + 1][1])
           for i in range(3)))
    ok("a virada de ano anda para trás certo",
       _meses_recentes(3) == [m[0], m[1], m[2]])

    ok("as 15 sugestões viram linhas com todas as colunas",
       len(_as.sugestoes_como_linhas()) == 15
       and set(_as.sugestoes_como_linhas()[0]) == set(_as.COLUNAS))
    ok("o peso mensal das sugestões é o que ele calculou à mão",
       abs(_as.total_mensal(_as.sugestoes_como_linhas()) - 2350.35) < 0.01)

    ok("o real sai formatado", _brl(2350.35) == "R$ 2.350,35")

    print("\nfalhas:", falhas)
    raise SystemExit(falhas)
