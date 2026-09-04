"""filtros.py — Primeiro se escolhe, depois se pesquisa.

O problema
----------
Todo campo de seleção do Streamlit recarrega a tela no instante do clique. Nos
filtros que decidem O QUE a tela carrega — mês, período, colaborador — esse
recarregamento é o caro: relê o board do Trello, o ponto da RHiD, a planilha de
metas. Trocar o mês custava dezenas de segundos, e trocar o mês E o ano custava
duas vezes isso, porque cada campo disparava a sua própria recarga.

Pior que a espera é não saber se houve espera: durante a recarga a tela fica
parada, sem sinal nenhum de que o clique foi registrado. Quem estava esperando
clicava de novo, e o segundo clique enfileirava mais uma recarga.

Como funciona
-------------
Os campos continuam sendo campos: mexer neles é imediato e barato, porque o que
a tela carrega não vem deles — vem da última escolha CONFIRMADA, guardada em
sessão. O botão de pesquisar é o que confirma.

    escolha = {"ano": ano_sel, "mes": mes_sel}        # o que está nos campos
    aplicado, pendente = filtros.pesquisar("am_mes", escolha, coluna=c3)
    ano, mes = aplicado["ano"], aplicado["mes"]       # o que a tela usa

Na primeira vez não há o que confirmar: a escolha inicial vale sem clique
nenhum, senão a tela abriria vazia esperando um botão.
"""

import streamlit as st

ROTULO = "🔍 Pesquisar"


def pesquisar(chave, escolha, rotulo=ROTULO, coluna=None, ajuda=None,
              largura=True):
    """(escolha_confirmada, tem_mudanca_pendente).

    `escolha` é qualquer valor comparável com `==` — normalmente um dict com o
    que os campos mostram agora. O que volta é o que a tela deve usar: a última
    escolha confirmada, que só muda quando alguém clica.

    `tem_mudanca_pendente` diz que os campos já mostram outra coisa e a tela
    ainda não. Quem chama usa isso para avisar — um botão que não avisa que tem
    trabalho esperando é um botão que ninguém clica.
    """
    alvo = coluna if coluna is not None else st
    guardado = st.session_state.get(chave)
    pendente = guardado is not None and guardado != escolha

    # Destaque só quando há o que aplicar. Botão sempre em destaque vira parte
    # do cenário, e aí ele deixa de chamar atenção justamente na hora em que
    # precisa chamar.
    clicou = alvo.button(
        rotulo, key=f"{chave}__pesquisar", use_container_width=largura,
        type="primary" if pendente else "secondary",
        help=ajuda or "Aplica os filtros escolhidos e recarrega os dados.")

    if clicou or guardado is None:
        st.session_state[chave] = escolha
        return escolha, False
    return guardado, pendente


def aviso_pendente(pendente, alvo=None):
    """A linha que aparece quando os campos e a tela discordam."""
    if not pendente:
        return
    (alvo or st).caption(
        f"⚠️ Você mudou os filtros — clique em **{ROTULO}** para carregar.")


def espaco(alvo, altura=28):
    """Alinha um botão com os campos ao lado, que têm rótulo em cima."""
    alvo.markdown(f"<div style='height:{altura}px;'></div>",
                  unsafe_allow_html=True)
