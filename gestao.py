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
    import home_gestao as _hg
    _hg.pagina(usuario_logado)


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


def _balanco_headcount(usuario_logado=None):
    """Até quando o aporte cobre o time, e quanto ele rendeu."""
    import headcount as _hc
    _hc.pagina(usuario_logado)


def _ajuste_de_valor(usuario_logado=None):
    """Quando cada valor mudou — o que faz o custo de cada mês ficar certo."""
    import ajustes as _aj
    _aj.pagina(usuario_logado)


# As telas de Financeiro, na ordem em que aparecem. Dicionário no topo do
# módulo, e não montado dentro da função: é a lista que cresce a cada bloco
# novo, e ela precisa estar num lugar só.
def _meta_gastos(usuario_logado=None):
    import meta_gastos_tela as _mgt
    _mgt.pagina(usuario_logado)


def _extratos(usuario_logado=None):
    import extratos_tela as _ext
    _ext.pagina(usuario_logado)


def _finalidades(usuario_logado=None):
    import finalidades_tela as _ft
    _ft.pagina(usuario_logado)


def _cheques(usuario_logado=None):
    """O cheque emitido — que o extrato só conhece no dia em que compensa."""
    import cheques_tela as _cht
    _cht.pagina(usuario_logado)


def _devolucoes(usuario_logado=None):
    """O que voltou: quanto, por quê, de quem foi a culpa e o que está aberto."""
    import devolucoes_tela as _dvt
    _dvt.pagina(usuario_logado)


def _fatura_ml(usuario_logado=None):
    """A fatura do ML: o que foi abatido, o que virou fatura, o que foi pago."""
    import fatura_ml_tela as _fml
    _fml.pagina(usuario_logado)


def _abrir_tela(modulo, usuario_logado=None, funcao="pagina"):
    """Abre a tela de outro módulo. Import tardio, como o resto do arquivo."""
    import importlib
    getattr(importlib.import_module(modulo), funcao)(usuario_logado)


def _lpv_mensal(usuario_logado=None):
    """O LPV do mês — era a aba «Financeiro» do ambiente Indicadores.

    Dono, 30/09: "está no ambiente Indicadores, mudar o nome para LPV Mensal".
    Dois «Financeiro» em ambientes diferentes é a Forma 5 desta base: o mesmo
    rótulo para duas perguntas, e quem procura um acha o outro.
    """
    _abrir_tela("financeiro", usuario_logado, "pagina_financeiro")


def _faturas(usuario_logado=None):
    """As faturas — hoje elas moram DENTRO de Conta corrente.

    Dito em voz alta: o PDF do dono pede «Faturas» como pontinho próprio, e
    esta tela ainda não existe separada. `extratos_tela.pagina` lê o extrato
    e as faturas na mesma passada. Separar é trabalho de verdade, não de
    navegação — e inventar uma tela vazia aqui seria pior do que dizer que
    ela não existe ainda.
    """
    st.markdown("### 🧾 Faturas")
    st.info(
        "As faturas ainda são lidas **dentro de Conta corrente** — é lá que "
        "o arquivo é enviado e classificado. Esta aba está reservada para "
        "quando elas ganharem tela própria; nada foi perdido."
    )


def _com_pontinhos(opcoes, chave, usuario_logado=None):
    """Desenha os «pontinhos» (o rádio) e só a tela escolhida.

    Rádio e não sub-aba porque são recortes da MESMA pergunta — é o mesmo
    gesto que o Custo fixo já usava para as três faces dele. A escolha vai
    para a URL pelo mesmo motivo das abas: o session_state morre quando o
    Railway reinicia, e sem isso a pessoa volta para o primeiro pontinho a
    cada deploy.
    """
    rotulos = list(opcoes)
    if chave not in st.session_state:
        _da_url = str(st.query_params.get(chave, "")).strip()
        st.session_state[chave] = _da_url if _da_url in rotulos else rotulos[0]
    escolhido = st.radio("O que você quer ver", rotulos, horizontal=True,
                         key=chave)
    if str(st.query_params.get(chave, "")) != escolhido:
        st.query_params[chave] = escolhido
    st.markdown("---")
    opcoes[escolhido](usuario_logado)


# ─────────────────────────────────────────────────────────────────────────
# A ARVORE DO FINANCEIRO, COMO O DONO DESENHOU (30/09)
#
# Sao QUATRO niveis, e o dono nomeou cada um:
#
#   AMBIENTE   Gestao, Indicadores, Operacao        (os tres botoes de cima)
#   ABA        Home, Financeiro, Operacional, ...   (a fileira seguinte)
#   SUB-ABA    Custos fixos, Extratos, Cheques, ... (a terceira fileira)
#   PONTINHOS  Operacional, Folha salarial, ...     (as bolinhas dentro)
#
# O que mudou aqui: cinco telas que eram ABA ou SUB-ABA viraram PONTINHO
# dentro de "Custos fixos" — Balanco headcount, Reserva, Assinaturas, LPV
# Mensal e Ajuste de valor. Elas respondem a mesma pergunta ("o que sai todo
# mes independente de vender"), e estavam espalhadas em tres niveis
# diferentes.
#
# Devolucoes saiu do Financeiro: virou sub-aba da aba OPERACIONAL, junto de
# Quebras e Estoque. Finalidades virou pontinho dentro de Extratos.
# AS TRES FACES VEM DE `FACES_DO_CUSTO`, E NAO DE UMA COPIA DELAS.
# Copiar os rotulos aqui seria a Forma 5: alguem renomeia uma face la e os
# dois dicionarios passam a discordar.
_PONTINHOS_CUSTO_FIXO = dict(FACES_DO_CUSTO)
_PONTINHOS_CUSTO_FIXO.update({
    "🧮 Balanço headcount":  _balanco_headcount,
    "🏦 Reserva":            lambda u: _abrir_tela("reserva_tela", u),
    "🔁 Assinaturas":        lambda u: _abrir_tela("assinaturas_tela", u),
    "💰 LPV Mensal":         _lpv_mensal,
    "📈 Ajuste de valor":    _ajuste_de_valor,
})

_PONTINHOS_EXTRATOS = {
    "🏦 Conta corrente": _extratos,
    "🧾 Faturas":        _faturas,
    "🏷️ Finalidades":    _finalidades,
}

SUBTELAS = {
    "🧱 Custos fixos": lambda u: _com_pontinhos(
        _PONTINHOS_CUSTO_FIXO, "fin_cf", u),
    "💳 Extratos": lambda u: _com_pontinhos(
        _PONTINHOS_EXTRATOS, "fin_ext", u),
    "🧾 Cheques": _cheques,
    "🛒 ADS-Cross": _fatura_ml,
    "🎯 Meta de gastos": _meta_gastos,
    "🔎 Análise de Gargalos": lambda u: _abrir_tela("gargalos_tela", u),
}


# ─────────────────────────────────────────────────────────────────────────
# ABA OPERACIONAL — nova, pedida pelo dono em 30/09
#
# Devolucoes saiu do Financeiro e veio para ca. Faz sentido: ela nao e
# dinheiro PLANEJADO (que e a pergunta do Financeiro), e sim coisa que
# aconteceu com a mercadoria — a mesma familia de Quebras e Estoque.
#
# QUEBRAS E ESTOQUE AINDA NAO EXISTEM, e isso esta dito na tela em vez de
# escondido atras de uma aba vazia. O dono escreveu "precisa criar e para
# configurarmos": sao telas para desenhar com ele, nao para eu inventar.
def _quebras(usuario_logado=None):
    st.markdown("### 💔 Quebras")
    st.info(
        "**Esta tela ainda não existe.** O dono pediu para criá-la e "
        "configurá-la junto — o lugar dela na navegação já está aqui, e o "
        "conteúdo depende de duas respostas: **o que conta como quebra** "
        "(produto danificado no envio, no estoque, na produção?) e **de onde "
        "vem o dado** (planilha, Bling, lançamento à mão?)."
    )


def _estoque(usuario_logado=None):
    st.markdown("### 📦 Estoque")
    st.info(
        "**Esta tela ainda não existe.** O dono pediu para criá-la e "
        "configurá-la junto — o lugar dela na navegação já está aqui, e o "
        "conteúdo depende de duas respostas: **o que ela precisa mostrar** "
        "(saldo por SKU, giro, ruptura?) e **qual é a fonte da verdade** "
        "(Bling, planilha, contagem física?)."
    )


SUBTELAS_OPERACIONAL = {
    "🔄 Devoluções": _devolucoes,
    "💔 Quebras":    _quebras,
    "📦 Estoque":    _estoque,
}


def pagina_operacional(usuario_logado=None, navegar=None):
    """O que acontece com a mercadoria: devolução, quebra e estoque."""
    st.markdown("## 📦 Operacional")
    st.caption("O que acontece com a mercadoria depois que ela existe — "
               "devolvida, quebrada ou parada no estoque.")
    if navegar is None:
        next(iter(SUBTELAS_OPERACIONAL.values()))(usuario_logado)
        return
    navegar({rot: (lambda f=fn: f(usuario_logado))
             for rot, fn in SUBTELAS_OPERACIONAL.items()}, "aba_op")


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
