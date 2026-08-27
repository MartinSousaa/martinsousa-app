"""
presenca.py — Quem está no Studio agora e em que tela.

Existe para o gestor não precisar perguntar no WhatsApp antes de subir uma
atualização: ele olha o painel e vê quem está dentro.

Como funciona, e o que isso implica
-----------------------------------
O Streamlit só executa o script quando o navegador fala com o servidor: clique,
troca de aba, envio de formulário. Não existe aviso de "fechei a janela". Então
o que dá para saber de verdade é *quando a pessoa mexeu pela última vez*, e é
isso que o painel mostra — "há 2 min", não um sinal verde mentiroso.

Quem está com a aba aberta lendo uma tela, sem clicar, some da lista depois de
JANELA_ONLINE_MIN. É limitação real do modelo, não bug: preferi mostrar o
horário da última ação a inventar presença que não dá para comprovar.

O registro vive na memória do processo (st.cache_resource é compartilhado por
todas as sessões do mesmo servidor). Não vai para a planilha de propósito: é
dado descartável, e uma escrita a cada clique de cada pessoa deixaria o Studio
mais lento pelo resto do dia. O efeito colateral aceito é que um deploy zera a
lista — e depois do deploy a lista se refaz sozinha no primeiro clique de cada um.
"""
import time

import streamlit as st

JANELA_ONLINE_MIN = 10


@st.cache_resource
def _registro():
    """{usuario: {"visto": epoch, "onde": str, "desde": epoch}} do processo."""
    return {}


def marcar(usuario, onde=""):
    """Registra que este usuário acabou de interagir, e em que tela.

    `onde` vazio não apaga a tela anterior: a chamada do topo do app não sabe
    ainda qual aba será desenhada, e sobrescrever com vazio faria todo mundo
    aparecer sem lugar nenhum.
    """
    if not usuario:
        return
    reg = _registro()
    agora = time.time()
    atual = reg.get(usuario) or {}
    reg[usuario] = {
        "visto": agora,
        "onde": onde or atual.get("onde", ""),
        "desde": atual.get("desde", agora),
    }


def esquecer(usuario):
    """Tira o usuário da lista — chamado quando ele clica em Sair."""
    if usuario:
        _registro().pop(usuario, None)


def online(janela_min=JANELA_ONLINE_MIN):
    """Quem interagiu dentro da janela, do mais recente para o mais antigo.

    Itera sobre uma cópia: o dicionário é compartilhado por todas as sessões, e
    outra pessoa clicando durante a leitura mudaria o tamanho no meio do laço.
    """
    limite = time.time() - janela_min * 60
    vivos = [
        {"usuario": u, **d}
        for u, d in list(_registro().items())
        if d.get("visto", 0) >= limite
    ]
    return sorted(vivos, key=lambda x: x.get("visto", 0), reverse=True)


def _ha_quanto(segundos):
    if segundos < 60:
        return "agora"
    minutos = int(segundos // 60)
    if minutos < 60:
        return f"há {minutos} min"
    return f"há {minutos // 60}h{minutos % 60:02d}"


def painel(titulo="NO STUDIO AGORA"):
    """Lista compacta para a barra lateral do gestor."""
    gente = online()
    st.markdown(
        f'<span style="font-size:10px;font-weight:700;letter-spacing:1.5px;'
        f'color:var(--ms-texto-sec);text-transform:uppercase;display:block;'
        f'margin:10px 0 4px;">{titulo} · {len(gente)}</span>',
        unsafe_allow_html=True,
    )
    if not gente:
        st.caption("Ninguém ativo nos últimos 10 minutos.")
        return

    # Tudo numa linha so nao cabe na largura da barra lateral: nome, tela e
    # "ha 4 min" se sobrepunham. Duas linhas por pessoa, com a tela em fonte
    # menor embaixo do nome, e cada texto cortado no que cabe.
    agora = time.time()
    linhas = []
    for p in gente:
        inativo = agora - p.get("visto", agora)
        cor = "#3FB950" if inativo < 120 else "#EDA100"
        onde = (p.get("onde") or "—")
        if len(onde) > 26:
            onde = onde[:25] + "…"
        # A hora ia na mesma linha do nome, empurrada para a direita. Na largura
        # da barra lateral ela saía da tela — "agora" virava "ag". Agora desce
        # junto da tela, que é onde sobra espaço.
        linhas.append(
            '<div style="padding:2px 0;line-height:1.3;">'
            '<div style="font-size:12px;white-space:nowrap;overflow:hidden;'
            'text-overflow:ellipsis;">'
            f'<span style="color:{cor};font-size:9px;">●</span> '
            f'<b style="color:var(--ms-texto);">{p["usuario"]}</b></div>'
            f'<div style="font-size:10px;color:var(--ms-texto-sec);'
            f'padding-left:13px;white-space:nowrap;overflow:hidden;'
            f'text-overflow:ellipsis;">{onde} · {_ha_quanto(inativo)}</div></div>'
        )
    # Sem st.caption: ele entra com margem própria e encavalava na linha
    # seguinte. A legenda vai no title, que aparece ao passar o mouse.
    st.markdown(
        '<div title="Verde = ativo no último minuto. Quem só está lendo, sem '
        'clicar, some da lista depois de 10 min." '
        'style="margin-bottom:8px;">' + "".join(linhas) + '</div>',
        unsafe_allow_html=True)
