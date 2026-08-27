"""
rascunho.py — Guarda as imagens geradas fora da sessão, para elas sobreviverem
a uma queda de conexão.

O problema
----------
A galeria só existia em `st.session_state`. Quando o WebSocket cai, o navegador
reconecta numa sessão NOVA e o session_state anterior morre junto. Numa geração
de 6 imagens que leva minutos, a chance de a conexão cair no meio é real — e
aconteceu: quatro imagens prontas evaporaram, com o custo delas na OpenAI já
pago. O colaborador voltou para o formulário vazio, sem nem saber o que houve.

O que este módulo faz
---------------------
Grava cada imagem em disco assim que ela fica pronta, junto de um manifesto
JSON. Se a sessão seguinte abrir sem galeria e existir rascunho recente, a tela
oferece recuperar.

Por que disco e não a planilha ou o Drive
-----------------------------------------
Disco local é instantâneo e não gasta cota. A falha que estamos cobrindo é a
queda do WebSocket, não a queda do servidor: o processo continua vivo e o
arquivo continua lá. Um deploy ou restart do Railway apaga tudo — e tudo bem,
porque nesse caso o navegador recarrega inteiro de qualquer forma.

O rascunho é descartável por definição: depois de salvar no Drive, ou ao começar
uma geração nova, ele é apagado.
"""
import json
import os
import shutil
import time

PASTA_BASE = os.path.join("/tmp", "ms_studio_rascunho")
VALIDADE_HORAS = 12


def _slug(texto):
    return "".join(c if c.isalnum() else "_" for c in str(texto))[:60] or "anon"


def _pasta(usuario):
    return os.path.join(PASTA_BASE, _slug(usuario))


def _ext(dados):
    if dados[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if dados[:2] == b"\xff\xd8":
        return "jpg"
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "webp"
    return "png"


def salvar(usuario, nome_produto, galeria, codigo=""):
    """Grava a galeria inteira. Nunca levanta: rascunho não pode derrubar geração."""
    if not usuario or not galeria:
        return False
    try:
        pasta = _pasta(usuario)
        shutil.rmtree(pasta, ignore_errors=True)
        os.makedirs(pasta, exist_ok=True)
        itens = []
        for i, g in enumerate(galeria):
            dados = g.get("bytes")
            if not dados:
                continue
            arq = f"{i:02d}.{_ext(dados)}"
            with open(os.path.join(pasta, arq), "wb") as fh:
                fh.write(dados)
            itens.append({"tipo": g.get("tipo", ""), "arquivo": arq,
                          "aprovado": bool(g.get("aprovado")),
                          "link": g.get("link", "")})
        with open(os.path.join(pasta, "manifesto.json"), "w", encoding="utf-8") as fh:
            json.dump({"quando": time.time(), "nome_produto": nome_produto,
                       "codigo": codigo, "itens": itens}, fh)
        return True
    except Exception:
        return False


def carregar(usuario):
    """Devolve {"nome_produto","codigo","galeria","quando","idade_min"} ou None."""
    if not usuario:
        return None
    try:
        pasta = _pasta(usuario)
        caminho = os.path.join(pasta, "manifesto.json")
        if not os.path.exists(caminho):
            return None
        with open(caminho, encoding="utf-8") as fh:
            man = json.load(fh)
        idade = time.time() - float(man.get("quando", 0))
        if idade > VALIDADE_HORAS * 3600:
            limpar(usuario)
            return None
        galeria = []
        for it in man.get("itens", []):
            caminho_img = os.path.join(pasta, it.get("arquivo", ""))
            if not os.path.exists(caminho_img):
                continue
            with open(caminho_img, "rb") as fh:
                galeria.append({"tipo": it.get("tipo", ""), "bytes": fh.read(),
                                "aprovado": it.get("aprovado", False),
                                "link": it.get("link", ""), "diag": {}})
        if not galeria:
            return None
        return {"nome_produto": man.get("nome_produto", ""),
                "codigo": man.get("codigo", ""),
                "galeria": galeria, "quando": man.get("quando", 0),
                "idade_min": int(idade // 60)}
    except Exception:
        return None


def limpar(usuario):
    try:
        shutil.rmtree(_pasta(usuario), ignore_errors=True)
    except Exception:
        pass


# ── Trabalho da sessão ───────────────────────────────────────────────────────
#
# Um F5 apagava título, descrição, palavras-chave e o histórico do chat. O login
# persiste — o trabalho não. Uma queda de internet, um deploy no Railway, um F5
# sem querer, e a pessoa refaz tudo (pagando a geração de novo).
#
# O mesmo disco que já guarda as imagens guarda o resto. Vale a mesma ressalva:
# cobre queda de conexão e recarga de página, não reinício do servidor — e nesse
# caso o navegador recarrega inteiro de qualquer jeito.

# Só o que é RESULTADO de trabalho. Chaves de widget e de controle de fluxo
# ficam de fora de propósito: restaurar estado de widget faz o Streamlit brigar,
# e restaurar um "pendente" de meio de fluxo reabriria uma confirmação que a
# pessoa já respondeu.
CHAVES_TRABALHO = (
    "desc_nome_atual", "desc_codigo_atual", "desc_texto_atual", "desc_dados_atual",
    "tt_titulos_gerados", "tt_dados_produto", "tt_palavras_usadas",
    "pc_palavras_geradas", "pc_dados_produto", "pc_tendencias",
    "img_nome_produto", "img_codigo", "img_dados_descricao",
    "ms_chat_hist",
)


def _caminho_trabalho(usuario):
    return os.path.join(_pasta(usuario), "trabalho.json")


def salvar_trabalho(usuario, estado):
    """Grava as chaves de trabalho. Devolve True se escreveu algo.

    `estado` é o st.session_state. Só grava o que é serializável em JSON: bytes
    de imagem, por exemplo, têm o caminho próprio em salvar()/carregar().
    """
    if not usuario:
        return False
    dados = {}
    for chave in CHAVES_TRABALHO:
        valor = estado.get(chave)
        if valor in (None, "", [], {}):
            continue
        try:
            json.dumps(valor)
        except (TypeError, ValueError):
            continue
        dados[chave] = valor
    try:
        pasta = _pasta(usuario)
        os.makedirs(pasta, exist_ok=True)
        if not dados:
            if os.path.exists(_caminho_trabalho(usuario)):
                os.remove(_caminho_trabalho(usuario))
            return False
        with open(_caminho_trabalho(usuario), "w", encoding="utf-8") as fh:
            json.dump({"quando": time.time(), "dados": dados}, fh)
        return True
    except Exception:
        return False


def carregar_trabalho(usuario):
    """Devolve o dict de chaves gravadas, ou {} se não houver nada válido."""
    if not usuario:
        return {}
    try:
        caminho = _caminho_trabalho(usuario)
        if not os.path.exists(caminho):
            return {}
        with open(caminho, encoding="utf-8") as fh:
            guardado = json.load(fh)
        if time.time() - float(guardado.get("quando", 0)) > VALIDADE_HORAS * 3600:
            os.remove(caminho)
            return {}
        return guardado.get("dados") or {}
    except Exception:
        return {}


def restaurar(usuario, estado):
    """Repõe o trabalho no session_state. Devolve o que foi reposto.

    Só preenche chave que está VAZIA: se a pessoa já gerou algo nesta sessão,
    o que está na tela manda sobre o que estava em disco.
    """
    reposto = []
    for chave, valor in (carregar_trabalho(usuario) or {}).items():
        if estado.get(chave) in (None, "", [], {}):
            estado[chave] = valor
            reposto.append(chave)
    return reposto
