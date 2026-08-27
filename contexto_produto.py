"""
contexto_produto.py — O produto em que a pessoa está trabalhando, um só, para
todas as abas.

Dois atritos com a mesma raiz
-----------------------------
O nome do produto era digitado de novo em cinco abas — Palavras-chave, Título,
Descrição, Imagem e Vídeo. Cinco vezes o mesmo nome, e cada busca custando cerca
de dez segundos. Nada era levado de uma tela para a outra.

E o ajuste feito nas Palavras-chave não chegava ao Título: pedia-se para remover
os termos de "escritório", a lista ia de 12 para 14 termos sem eles, e a aba
Título refazia a lista do zero — com "caneca escritorio" de volta, e usado no
título. O trabalho de conversa que a pessoa acabara de fazer era descartado em
silêncio.

Os dois são o mesmo problema: não havia um lugar dizendo "é neste produto que
estamos trabalhando agora".

Como funciona
-------------
Uma aba que identifica um produto chama `definir()`. As outras leem `nome()` e
usam como valor inicial do campo de busca — inicial, não travado: quem quiser
trocar de produto apaga e digita outro, e a troca vira o novo contexto.

As palavras-chave seguem a mesma ideia. Geradas ou ajustadas numa aba, ficam
disponíveis para as outras em vez de serem refeitas.

Vive no session_state, não em disco: é o produto DESTA sessão. O que precisa
sobreviver a um F5 é gravado por rascunho.py, que já inclui estas chaves.
"""
import streamlit as st

CHAVE_NOME = "ctx_produto_nome"
CHAVE_CODIGO = "ctx_produto_codigo"
CHAVE_PALAVRAS = "ctx_produto_palavras"
CHAVE_DADOS = "ctx_produto_dados"


def _txt(v):
    return str(v or "").strip()


def definir(nome, codigo="", dados=None):
    """Marca o produto em que se está trabalhando.

    Trocar de produto limpa as palavras-chave: elas são daquele produto, e
    carregá-las para o seguinte seria pior do que não ter nenhuma.
    """
    nome = _txt(nome)
    if not nome:
        return
    if _txt(st.session_state.get(CHAVE_NOME)).lower() != nome.lower():
        st.session_state.pop(CHAVE_PALAVRAS, None)
    st.session_state[CHAVE_NOME] = nome
    if _txt(codigo):
        st.session_state[CHAVE_CODIGO] = _txt(codigo)
    if dados:
        st.session_state[CHAVE_DADOS] = dict(dados)


def nome():
    return _txt(st.session_state.get(CHAVE_NOME))


def codigo():
    return _txt(st.session_state.get(CHAVE_CODIGO))


def dados():
    return dict(st.session_state.get(CHAVE_DADOS) or {})


def definir_palavras(lista):
    """Guarda a lista de termos — a versão ajustada, se houve ajuste."""
    termos = [_txt(p.get("termo") if isinstance(p, dict) else p) for p in (lista or [])]
    termos = [t for t in termos if t]
    if termos:
        st.session_state[CHAVE_PALAVRAS] = termos


def palavras():
    return list(st.session_state.get(CHAVE_PALAVRAS) or [])


def semear(chave_widget):
    """Põe o nome do contexto num campo de busca que ainda está vazio.

    Escreve ANTES de o widget existir — depois disso o Streamlit recusa a
    escrita e derruba a tela. Por isso a função é chamada logo acima do campo,
    nunca depois.

    Só semeia o vazio: o que a pessoa digitou manda sobre o contexto.
    """
    if nome() and not _txt(st.session_state.get(chave_widget)):
        st.session_state[chave_widget] = nome()
        return True
    return False
