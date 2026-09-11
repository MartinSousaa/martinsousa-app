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


# As três faces do custo fixo. Elas viviam como abas irmãs do Financeiro, e
# estava errado: folha e empréstimo SÃO custo fixo, não vizinhos dele. Como
# irmãs, cada uma parecia uma conta separada, e ninguém somava as três para ver
# o custo do mês — que é a única pergunta que importa aqui.
# Os imports moram dentro das funções: cada módulo abre a planilha, e carregar
# isso na importação faria o Studio inteiro esperar pelo Google para desenhar
# qualquer tela.
def _operacional(usuario_logado=None):
    """Água, luz, aluguel, contabilidade — o custo fixo que não é gente."""
    import custo_fixo as _cf
    _cf.pagina(usuario_logado, grade="custo_fixo")


def _folha_salarial(usuario_logado=None):
    """Gestores e colaboradores, em duas tabelas e um total só."""
    import folha_salarial as _fs
    _fs.pagina(usuario_logado)


def _nao_operacional(usuario_logado=None):
    """Os empréstimos: sai do caixa, mas não é custo de operar."""
    import nao_operacional as _no
    _no.pagina(usuario_logado)


FACES_DO_CUSTO = {
    "🏢 Operacional": _operacional,
    "👥 Folha salarial": _folha_salarial,
    "🏦 Não operacional": _nao_operacional,
}


def _custo_fixo(usuario_logado=None):
    """Custo fixo, com as três faces atrás de um seletor.

    Rádio e não sub-aba: são três recortes da MESMA coisa, e o rádio diz isso
    — é o mesmo gesto de «Análise coletiva / Análise individual» em Indicadores.
    A escolha vai para a URL para sobreviver ao deploy, igual às abas.
    """
    st.markdown("### 🧱 Custo fixo")
    st.caption("O que sai todo mês independente de vender — nas três formas em "
               "que ele aparece. É a soma das três que entra na linha de "
               "equilíbrio.")

    rotulos = list(FACES_DO_CUSTO)
    chave = "cf_face"
    if chave not in st.session_state:
        da_url = str(st.query_params.get(chave, "")).strip()
        st.session_state[chave] = da_url if da_url in rotulos else rotulos[0]
    escolhido = st.radio("O que você quer ver", rotulos, horizontal=True,
                         key=chave)
    if str(st.query_params.get(chave, "")) != escolhido:
        st.query_params[chave] = escolhido

    st.markdown("---")
    FACES_DO_CUSTO[escolhido](usuario_logado)


def _ajuste_de_valor(usuario_logado=None):
    """Quando cada valor mudou — o que faz o custo de cada mês ficar certo."""
    import ajustes as _aj
    _aj.pagina(usuario_logado)


# As telas de Financeiro, na ordem em que aparecem. Dicionário no topo do
# módulo, e não montado dentro da função: é a lista que cresce a cada bloco
# novo, e ela precisa estar num lugar só.
SUBTELAS = {
    "🧱 Custo fixo": _custo_fixo,
    "📈 Ajuste de valor": _ajuste_de_valor,
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
