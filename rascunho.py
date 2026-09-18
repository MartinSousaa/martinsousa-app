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
Disco é instantâneo e não gasta cota. A planilha viraria lixeira de rascunho, e
o Drive cobra segundos a cada salvamento — num fluxo que salva a cada passo.

Qual disco, e o que cada um cobre
---------------------------------
Sem `RASCUNHO_DIR`, o disco é o /tmp do container: cobre queda de WebSocket e F5
(o processo segue vivo, o arquivo segue lá) mas NÃO cobre deploy — o Railway
destrói o container e leva o rascunho junto. Foi assim que imagem já gerada e
paga evaporou no meio da tarde porque alguém subiu uma correção.

Com um VOLUME do Railway montado e `RASCUNHO_DIR` apontando para ele, o rascunho
atravessa deploy e restart. A variável é opcional de propósito: sem ela nada
muda, e um volume mal configurado cai de volta para /tmp em vez de derrubar a
tela — rascunho é conveniência, nunca pode ser o motivo de o Studio não abrir.

O rascunho é descartável por definição: depois de salvar no Drive, ou ao começar
uma geração nova, ele é apagado.
"""
import json
import os
import shutil
import time

# ONDE O RASCUNHO MORA, E POR QUE ISSO IMPORTA
#
# Ate aqui era sempre /tmp — disco do container. Cobria queda de WebSocket e F5
# (o processo continua vivo, o arquivo continua la), mas NAO cobria deploy: o
# Railway destroi o container, e o rascunho ia junto. Imagem gerada e paga
# evaporava no meio da tarde porque alguem subiu uma correcao.
#
# Com um VOLUME do Railway montado e a variavel RASCUNHO_DIR apontando para ele,
# o rascunho passa a sobreviver a deploy e a restart. Sem a variavel, tudo
# continua exatamente como antes — nenhum ambiente quebra por nao ter o volume.
#
# A pasta e criada e testada na primeira leitura: volume configurado errado
# (caminho que nao existe, sem permissao de escrita) cai de volta para /tmp em
# vez de derrubar a tela. Rascunho e conveniencia; ele nunca pode ser o motivo
# de o Studio nao abrir.
_PADRAO = os.path.join("/tmp", "ms_studio_rascunho")


def _base_configurada():
    """A pasta do secret/variavel, se der para escrever nela. Senao, /tmp."""
    alvo = ""
    try:
        import streamlit as _st
        alvo = str(_st.secrets.get("RASCUNHO_DIR", "") or "").strip()
    except Exception:
        alvo = ""
    if not alvo:
        alvo = str(os.environ.get("RASCUNHO_DIR", "") or "").strip()
    if not alvo:
        return _PADRAO
    caminho = os.path.join(alvo, "ms_studio_rascunho")
    try:
        os.makedirs(caminho, exist_ok=True)
        teste = os.path.join(caminho, ".escrita")
        with open(teste, "w") as f:
            f.write("ok")
        os.remove(teste)
        return caminho
    except Exception:
        return _PADRAO


PASTA_BASE = _base_configurada()
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


MANIFESTO = "manifesto.json"
TRABALHO = "trabalho.json"
ANTERIOR = "anterior"


def _so_a_galeria(pasta):
    """Apaga os arquivos da galeria e o manifesto. NADA além disso.

    `rmtree` na pasta inteira era o bug: levava junto o `trabalho.json`, que
    guarda título, descrição, palavras-chave e o chat. Gerar imagem de novo
    apagava o texto que a pessoa tinha escrito, sem nada na tela dizendo por
    quê — e os dois não têm relação nenhuma.
    """
    if not os.path.isdir(pasta):
        return
    for nome in os.listdir(pasta):
        if nome in (TRABALHO, ANTERIOR):
            continue
        alvo = os.path.join(pasta, nome)
        try:
            if os.path.isfile(alvo):
                os.remove(alvo)
        except Exception:
            pass


def arquivar(usuario):
    """Empurra a galeria atual para `anterior/` em vez de jogá-la fora.

    Uma geração nova começa apagando a antiga — e era ali que o colaborador
    ficava sem rede: se a tela recarregasse antes de a primeira imagem nova
    ficar pronta, a sessão vinha vazia E o disco vinha vazio. As imagens
    antigas, já pagas, sumiam por causa de um pedido de correção.

    Guardadas em `anterior/`, elas continuam recuperáveis até a geração nova
    fechar. Só então `salvar()` descarta a cópia.
    """
    if not usuario:
        return False
    pasta = _pasta(usuario)
    if not os.path.exists(os.path.join(pasta, MANIFESTO)):
        return False
    antigo = os.path.join(pasta, ANTERIOR)
    try:
        shutil.rmtree(antigo, ignore_errors=True)
        os.makedirs(antigo, exist_ok=True)
        for nome in os.listdir(pasta):
            if nome in (TRABALHO, ANTERIOR):
                continue
            alvo = os.path.join(pasta, nome)
            if os.path.isfile(alvo):
                shutil.move(alvo, os.path.join(antigo, nome))
        return True
    except Exception:
        return False


def salvar(usuario, nome_produto, galeria, codigo=""):
    """Grava a galeria inteira. Nunca levanta: rascunho não pode derrubar geração."""
    if not usuario or not galeria:
        return False
    try:
        pasta = _pasta(usuario)
        os.makedirs(pasta, exist_ok=True)
        # Só a galeria: o trabalho.json fica. Antes era `rmtree` na pasta
        # inteira, e salvar imagem apagava o texto da pessoa.
        _so_a_galeria(pasta)
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
        with open(os.path.join(pasta, MANIFESTO), "w", encoding="utf-8") as fh:
            json.dump({"quando": time.time(), "nome_produto": nome_produto,
                       "codigo": codigo, "itens": itens}, fh)
        # A geração nova fechou: a cópia de segurança já não serve para nada.
        shutil.rmtree(os.path.join(pasta, ANTERIOR), ignore_errors=True)
        return True
    except Exception:
        return False


def _ler_manifesto(pasta, com_bytes=True):
    """{...} da galeria daquela pasta, ou None. Não decide nada — só lê.

    `com_bytes=False` lê SÓ o manifesto e confere quais arquivos existem, sem
    abrir um único byte de imagem.

    POR QUE ESSA OPÇÃO EXISTE
    -------------------------
    O aviso "🛟 Encontrei N imagens que não chegaram à tela" chama esta função
    a cada passada do Streamlit — ou seja, a cada tecla digitada, cada clique,
    cada troca de campo, enquanto a galeria estiver vazia. E ela lia do disco
    TODOS os bytes de TODAS as imagens: oito peças de 1,5 MB são 12 MB lidos,
    alocados e jogados fora, muitas vezes por minuto, para exibir um número e
    um nome.

    Era isso que deixava o Ajuste Fino impossível de usar: a tela travando, o
    "Reconectando ao servidor… os cliques não estão sendo enviados", e o
    processo comendo memória até reiniciar — e reiniciar é o que apaga o
    histórico do chat, porque ele vive na memória.

    Os bytes só são lidos quando alguém clica em "Recuperar". Antes disso,
    ninguém precisa deles.
    """
    caminho = os.path.join(pasta, MANIFESTO)
    if not os.path.exists(caminho):
        return None
    try:
        with open(caminho, encoding="utf-8") as fh:
            man = json.load(fh)
    except Exception:
        return None
    idade = time.time() - float(man.get("quando", 0))
    if idade > VALIDADE_HORAS * 3600:
        return None
    galeria = []
    for it in man.get("itens", []):
        caminho_img = os.path.join(pasta, it.get("arquivo", ""))
        if not os.path.exists(caminho_img):
            continue
        if not com_bytes:
            # Só a ficha: quantas são e o que são. Sem tocar no conteúdo.
            galeria.append({"tipo": it.get("tipo", ""),
                            "aprovado": it.get("aprovado", False),
                            "link": it.get("link", "")})
            continue
        try:
            with open(caminho_img, "rb") as fh:
                galeria.append({"tipo": it.get("tipo", ""), "bytes": fh.read(),
                                "aprovado": it.get("aprovado", False),
                                "link": it.get("link", ""), "diag": {}})
        except Exception:
            continue
    if not galeria:
        return None
    return {"nome_produto": man.get("nome_produto", ""),
            "codigo": man.get("codigo", ""),
            "galeria": galeria, "quando": man.get("quando", 0),
            "idade_min": int(idade // 60)}


def carregar(usuario, com_bytes=True):
    """A galeria guardada, ou None. Cai em `anterior/` quando a atual sumiu.

    É a queda que o colaborador viveu: pediu correção, a tela recarregou antes
    de a geração nova terminar, e não havia nem sessão nem disco. Agora a
    geração interrompida devolve o que existia antes dela.

    `com_bytes=False` é para quem só quer saber SE há algo e quanto — o aviso
    na tela. Ler as imagens para contar quantas são custa a tela inteira.
    """
    if not usuario:
        return None
    try:
        pasta = _pasta(usuario)
        atual = _ler_manifesto(pasta, com_bytes=com_bytes)
        if atual:
            return atual
        anterior = _ler_manifesto(os.path.join(pasta, ANTERIOR),
                                  com_bytes=com_bytes)
        if anterior:
            anterior["de_geracao_interrompida"] = True
            return anterior
        return None
    except Exception:
        return None


def resumo(usuario):
    """Só a ficha do rascunho: quantas imagens, de que produto, de quando.

    É o que o aviso na tela precisa — e ele é desenhado a cada passada do
    Streamlit. Nenhum byte de imagem é lido aqui.
    """
    return carregar(usuario, com_bytes=False)


def limpar(usuario):
    """Apaga a galeria — e SÓ ela. O trabalho de texto e chat continua.

    Título, descrição, palavras-chave e chat não têm relação com gerar imagem
    de novo; apagá-los junto era efeito colateral do `rmtree` na pasta inteira.
    """
    if not usuario:
        return
    pasta = _pasta(usuario)
    try:
        _so_a_galeria(pasta)
        shutil.rmtree(os.path.join(pasta, ANTERIOR), ignore_errors=True)
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
    # O produto em que a pessoa esta trabalhando, e as palavras-chave dele.
    "ctx_produto_nome", "ctx_produto_codigo", "ctx_produto_palavras",
    "ctx_produto_dados",
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


# ── Conferência ──────────────────────────────────────────────────────────────
# `python3 rascunho.py` roda os casos abaixo.
if __name__ == "__main__":
    import shutil as _sh_t
    import tempfile as _tmp_t

    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    _base = _tmp_t.mkdtemp()
    globals()["_pasta"] = lambda u, _b=_base: os.path.join(_b, u)

    _p = _pasta("bia")
    os.makedirs(_p, exist_ok=True)
    _IMG = b"P" * (300 * 1024)          # 300 KB por peça, como as de verdade
    for _i in range(3):
        with open(os.path.join(_p, f"img{_i}.png"), "wb") as _fh:
            _fh.write(_IMG)
    with open(os.path.join(_p, MANIFESTO), "w", encoding="utf-8") as _fh:
        json.dump({"nome_produto": "Urso Prata", "codigo": "MS-URSO-1",
                   "quando": time.time(),
                   "itens": [{"tipo": f"{i} — peça", "arquivo": f"img{i}.png"}
                             for i in range(3)]}, _fh)

    _r = resumo("bia")
    ok("o resumo acha as tres imagens", _r and len(_r["galeria"]) == 3)
    ok("e traz o nome do produto", _r["nome_produto"] == "Urso Prata")
    # O CUSTO QUE TRAVAVA A TELA: o aviso é desenhado a cada tecla digitada.
    # Lendo os bytes, eram 900 KB do disco por passada — com oito peças, 12 MB.
    ok("e NAO le um unico byte de imagem",
       all("bytes" not in it for it in _r["galeria"]))

    _c = carregar("bia")
    ok("carregar continua trazendo os bytes, para o botao Recuperar",
       _c and all(len(it["bytes"]) == len(_IMG) for it in _c["galeria"]))

    # Rascunho velho não é rascunho: o aviso some sozinho depois da validade.
    with open(os.path.join(_p, MANIFESTO), encoding="utf-8") as _fh:
        _man = json.load(_fh)
    _man["quando"] = time.time() - (VALIDADE_HORAS + 1) * 3600
    with open(os.path.join(_p, MANIFESTO), "w", encoding="utf-8") as _fh:
        json.dump(_man, _fh)
    ok("rascunho vencido nao aparece", resumo("bia") is None)

    ok("usuario sem rascunho nao derruba", resumo("ninguem") is None)
    ok("usuario vazio tambem", resumo("") is None and carregar("") is None)

    _sh_t.rmtree(_base, ignore_errors=True)
    print("\nfalhas:", falhas)
