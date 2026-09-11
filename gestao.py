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


def pagina_financeiro(usuario_logado=None):
    """A base do custo fixo — o número que sustenta todo o resto."""
    _em_branco(
        "💼 Financeiro",
        "A base do custo fixo mensal. É dela que sai a linha de equilíbrio.",
        [
            "Custo fixo operacional, item a item",
            "Custo não operacional (parcelas de empréstimo)",
            "Aporte e o custo mensal que ele cobre, com os meses de cobertura",
            "Meta de gastos e a divisão entre obrigatórios e não obrigatórios",
        ],
    )
