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
