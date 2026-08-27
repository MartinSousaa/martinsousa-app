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
    """Lista compacta para a barra lateral do gestor.

    A barra lateral é estreita e o chat divide o espaço com ela, então o painel
    é desenhado como um cartão baixo: cabeçalho com contagem, uma linha por
    pessoa, e o texto secundário menor e recuado. Tudo em HTML de uma vez — cada
    componente do Streamlit traz margem própria, e três deles empilhados já
    encavalam nesta largura.
    """
    gente = online()
    cor_titulo = "#3FB950" if gente else "var(--ms-texto-sec)"
    cabecalho = (
        '<div style="display:flex;align-items:center;gap:6px;'
        'margin-bottom:6px;">'
        f'<span style="font-size:9.5px;font-weight:700;letter-spacing:1.2px;'
        f'color:var(--ms-texto-sec);text-transform:uppercase;">{titulo}</span>'
        f'<span style="font-size:10px;font-weight:700;color:{cor_titulo};'
        f'background:#ffffff10;border-radius:8px;padding:0 6px;line-height:16px;">'
        f'{len(gente)}</span></div>'
    )

    if not gente:
        corpo = ('<div style="font-size:11px;color:var(--ms-texto-sec);">'
                 'Ninguém ativo nos últimos 10 minutos.</div>')
    else:
        agora = time.time()
        linhas = []
        for p in gente:
            inativo = agora - p.get("visto", agora)
            cor = "#3FB950" if inativo < 120 else "#EDA100"
            onde = p.get("onde") or "—"
            # Nome e tela na MESMA linha: cada pessoa ocupava duas, e a barra
            # lateral e do chat. O nome nao encolhe (flex:none) e o que sobra
            # e cortado do lado da tela, que e o texto mais longo.
            linhas.append(
                '<div style="display:flex;align-items:baseline;gap:5px;'
                'padding:2px 0;font-size:12px;min-width:0;">'
                f'<span style="width:7px;height:7px;border-radius:50%;flex:none;'
                f'background:{cor};box-shadow:0 0 6px {cor}66;'
                f'align-self:center;"></span>'
                f'<b style="color:var(--ms-texto);flex:none;">{p["usuario"]}:</b>'
                f'<span style="color:var(--ms-texto-sec);font-size:11px;'
                f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
                f'{onde} · {_ha_quanto(inativo)}</span></div>'
            )
        corpo = "".join(linhas)

    st.markdown(
        '<div title="Verde = ativo no último minuto. Quem só está lendo, sem '
        'clicar, some da lista depois de 10 min." '
        'style="background:#ffffff08;border:1px solid var(--ms-divisor);'
        'border-radius:8px;padding:8px 10px;margin:10px 0 12px;">'
        + cabecalho + corpo + '</div>',
        unsafe_allow_html=True)
