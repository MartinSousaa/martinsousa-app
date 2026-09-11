"""gestao.py — O ambiente de Gestão: onde o dinheiro é planejado, não medido.

POR QUE UM AMBIENTE NOVO E NÃO MAIS UMA ABA
-------------------------------------------
Os três ambientes respondem a perguntas diferentes, e misturá-los foi o que fez
a tela de Gestão antiga virar um depósito:

    Operação     o que fazer agora — triagem, título, imagem, vídeo
    Indicadores  o que já aconteceu — metas, ponto, faturamento realizado
    Gestão       o que vai acontecer — custo fixo, meta de gastos, equilíbrio

`Indicadores` olha para trás e é alimentado por Trello, RHiD e Bling. `Gestão`
olha para frente e é alimentado pelo gestor, à mão. São fontes diferentes,
públicos diferentes e cadências diferentes: um muda a cada minuto, o outro a
cada mês.

ESTADO ATUAL
------------
As duas telas estão em branco de propósito. O ambiente foi criado primeiro para
a navegação, a URL e a permissão ficarem prontas e testadas antes de existir
qualquer número — e não o contrário, que é como se acaba com um formulário
pendurado numa tela que ninguém consegue abrir.
"""

import streamlit as st


def _em_branco(titulo, descricao, itens):
    """Tela ainda sem conteúdo, dizendo o que virá.

    Página vazia de verdade parece erro, e quem abre acha que quebrou. Esta diz
    o que vai morar aqui — enquanto não mora.
    """
    st.markdown(f"### {titulo}")
    st.caption(descricao)
    st.info("Ainda em construção — nada aqui é definitivo.")
    if itens:
        st.markdown("\n".join(f"- {i}" for i in itens))


def pagina_home(usuario_logado=None):
    """A primeira tela de Gestão: os indicadores que resumem o mês."""
    _em_branco(
        "🏠 Home",
        "O resumo do mês: onde o faturamento está contra o que ele precisa ser.",
        [
            "Faturamento × ponto de equilíbrio",
            "LPV · realizado contra o necessário",
            "UC · realizado contra o necessário",
            "Lucro bruto · realizado contra o necessário",
            "Lucro líquido · realizado contra o necessário",
            "Margem de lucro · realizada contra a necessária",
        ],
    )


def _custo_fixo(usuario_logado=None):
    """O custo que existe com ou sem venda — a base de tudo o que vem depois."""
    _em_branco(
        "🧱 Custo fixo",
        "O que sai todo mês independente de vender. É o numerador da linha de "
        "equilíbrio: faturamento de equilíbrio = custo fixo ÷ margem de "
        "contribuição.",
        [
            "Item a item, com valor, dia de pagamento e forma de pagamento",
            "Separação entre operacional e não operacional (parcelas de empréstimo)",
            "Aporte: valor, custo mensal que ele cobre e por quantos meses",
            "Total do mês e quanto ele representa do faturamento",
        ],
    )


# As telas de Financeiro, na ordem em que aparecem. Dicionário no topo do
# módulo, e não montado dentro da função: é a lista que cresce a cada bloco
# novo, e ela precisa estar num lugar só.
SUBTELAS = {
    "🧱 Custo fixo": _custo_fixo,
}


def pagina_financeiro(usuario_logado=None, navegar=None):
    """O dinheiro planejado: custo fixo, aporte, meta de gastos.

    `navegar` é o mesmo seletor de abas do app (`app._navegar`), passado de
    fora em vez de reescrito aqui. Aquela função carrega correções que
    custaram caro — clique na aba já aberta, botão voltar do navegador, tela
    antiga desenhada embaixo da nova — e uma segunda cópia começaria igual e
    terminaria discordando. Sem ele (import solto, teste), desenha a primeira.
    """
    st.markdown("### 💼 Financeiro")
    if navegar is None:
        next(iter(SUBTELAS.values()))(usuario_logado)
        return
    navegar({rot: (lambda f=fn: f(usuario_logado)) for rot, fn in SUBTELAS.items()},
            "sub_fin")
