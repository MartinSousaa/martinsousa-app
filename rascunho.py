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


# ── As FOTOS ANEXADAS ────────────────────────────────────────────────────────
#
# Este módulo nasceu guardando o RESULTADO — a galeria já gerada. A ENTRADA
# ficou de fora, e ela se perde pelo mesmo motivo: os bytes do upload moram na
# memória do processo do Streamlit
# (`streamlit/runtime/memory_uploaded_file_manager.py`, `file_storage`), e a
# lista de NOMES fica no navegador. Quando o processo reinicia — deploy, queda,
# troca de container — os nomes seguem na tela e os bytes já não existem.
#
# Foi o que aconteceu em 28/09 às 17:17: três fotos listadas na tela, e o botão
# respondendo "Suba pelo menos uma foto do produto". Quem olha não tem como
# entender: as fotos ESTÃO ali.
#
# Elas moram numa SUBPASTA, e isso é de propósito: `_so_a_galeria`, `limpar` e
# `arquivar` mexem só em arquivos soltos da pasta. As fotos atravessam o ciclo
# inteiro da galeria — que é o que precisa acontecer, porque gerar de novo pede
# justamente as MESMAS fotos.
FOTOS = "fotos"
MANIFESTO_FOTOS = "fotos.json"


def _pasta_fotos(usuario, campo="produto"):
    return os.path.join(_pasta(usuario), FOTOS, _slug(campo))


def salvar_fotos(usuario, fotos, nomes=(), campo="produto"):
    """Grava as fotos anexadas. True se escreveu. Nunca levanta."""
    if not usuario or not fotos:
        return False
    try:
        pasta = _pasta_fotos(usuario, campo)
        shutil.rmtree(pasta, ignore_errors=True)
        os.makedirs(pasta, exist_ok=True)
        itens = []
        for i, dados in enumerate(fotos):
            if not dados:
                continue
            arq = f"{i:02d}.{_ext(dados)}"
            with open(os.path.join(pasta, arq), "wb") as fh:
                fh.write(dados)
            nome = nomes[i] if i < len(nomes) else ""
            itens.append({"arquivo": arq, "nome": nome})
        if not itens:
            return False
        with open(os.path.join(pasta, MANIFESTO_FOTOS), "w",
                  encoding="utf-8") as fh:
            json.dump({"quando": time.time(), "itens": itens}, fh)
        return True
    except Exception:
        return False


def carregar_fotos(usuario, campo="produto"):
    """[{"bytes":..., "nome":...}] na ordem em que foram anexadas, ou []."""
    if not usuario:
        return []
    try:
        pasta = _pasta_fotos(usuario, campo)
        caminho = os.path.join(pasta, MANIFESTO_FOTOS)
        if not os.path.exists(caminho):
            return []
        with open(caminho, encoding="utf-8") as fh:
            guardado = json.load(fh)
        if time.time() - float(guardado.get("quando", 0)) > VALIDADE_HORAS * 3600:
            shutil.rmtree(pasta, ignore_errors=True)
            return []
        saida = []
        for it in guardado.get("itens") or []:
            alvo = os.path.join(pasta, it.get("arquivo", ""))
            if not os.path.isfile(alvo):
                continue
            with open(alvo, "rb") as fh:
                saida.append({"bytes": fh.read(), "nome": it.get("nome", "")})
        return saida
    except Exception:
        return []


def resumo_fotos(usuario, campo="produto"):
    """[{"nome":...}] das fotos guardadas, SEM ler um byte de imagem.

    Existe pelo mesmo motivo que `resumo`: o aviso na tela e desenhado a cada
    passada do Streamlit, e ler 3 MB de foto do disco a cada tecla digitada
    trava a tela. O caro e o BYTE; o manifesto e um JSON de duas linhas.
    """
    if not usuario:
        return []
    try:
        pasta = _pasta_fotos(usuario, campo)
        caminho = os.path.join(pasta, MANIFESTO_FOTOS)
        if not os.path.exists(caminho):
            return []
        with open(caminho, encoding="utf-8") as fh:
            guardado = json.load(fh)
        if time.time() - float(guardado.get("quando", 0)) > VALIDADE_HORAS * 3600:
            shutil.rmtree(pasta, ignore_errors=True)
            return []
        return [{"nome": it.get("nome", "")}
                for it in (guardado.get("itens") or [])
                if os.path.isfile(os.path.join(pasta, it.get("arquivo", "")))]
    except Exception:
        return []


def limpar_fotos(usuario, campo="produto"):
    """Descarta as fotos guardadas. Devolve None sempre — é só um descarte."""
    if not usuario:
        return None
    shutil.rmtree(_pasta_fotos(usuario, campo), ignore_errors=True)
    return None


def limpar_todas_as_fotos(usuario):
    """Descarta as fotos de TODOS os campos. Devolve None sempre.

    `limpar_fotos` apaga UM campo por chamada, e é o certo para quem troca
    uma referência. Quem troca de PRODUTO tem de apagar todas — e uma lista
    de campos escrita aqui envelheceria no dia em que alguém criasse o quinto
    campo de upload da aba Imagem. Seria a Forma 1 desta base: a correção
    chegando a um irmão e não aos outros.

    A subpasta `fotos/` é a fonte, e não a lista: apagá-la cobre também o
    campo que ainda não existe.
    """
    if not usuario:
        return None
    shutil.rmtree(os.path.join(_pasta(usuario), FOTOS), ignore_errors=True)
    return None


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


def _so_o_que_cabe_em_json(valor):
    """O mesmo valor sem as partes que o JSON recusa. None se não sobrar nada.

    Feita para `ms_chat_hist`, que é uma lista de falas e ganha BYTES quando
    alguém anexa uma foto no chat. Tira a parte crua e devolve a fala; o texto
    da conversa, que é o que custa refazer, continua gravado.
    """
    if isinstance(valor, list):
        limpa = []
        for item in valor:
            if isinstance(item, dict):
                item = {k: v for k, v in item.items()
                        if not isinstance(v, (bytes, bytearray))
                        and not (isinstance(v, list) and any(
                            isinstance(x, (bytes, bytearray)) for x in v))}
            try:
                json.dumps(item)
            except (TypeError, ValueError):
                continue
            limpa.append(item)
        return limpa or None
    return None


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
            # O QUE NÃO CABE EM JSON SAI SOZINHO, e o resto FICA.
            #
            # Antes o `continue` descartava a CHAVE INTEIRA, e isso apagava a
            # conversa em silêncio: basta o colaborador anexar uma foto no
            # chat para `ms_chat_hist` ganhar bytes, e a partir daí o
            # histórico parava de ser gravado. Um F5 depois disso devolvia a
            # conversa vazia, sem nada na tela dizendo por quê — e o motivo
            # era um anexo de vinte mensagens atrás.
            #
            # Perder o ANEXO num F5 é aceitável: ele já foi usado, e os bytes
            # morrem com o processo de qualquer jeito. Perder a CONVERSA não.
            valor = _so_o_que_cabe_em_json(valor)
            if valor in (None, "", [], {}):
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


def limpar_trabalho(usuario):
    """Apaga o `trabalho.json`: texto, chat e o produto da sessão. Devolve None.

    POR QUE ELA É SEPARADA DE `limpar`, E POR QUE ELA PRECISA EXISTIR
    ----------------------------------------------------------------
    `limpar` apaga a galeria e PRESERVA o trabalho de texto, de propósito:
    pedir a geração de novo não é motivo para perder a descrição.

    Trocar de PRODUTO é outra coisa. `app.py:1532` chama `restaurar` em toda
    sessão, e ele repõe toda chave que estiver vazia — então um botão que
    zerasse só o `session_state` traria o produto velho de volta no primeiro
    F5, sem ninguém entender por quê. O disco tem de ser zerado junto com a
    tela, ou os dois passam a discordar.
    """
    if not usuario:
        return None
    try:
        caminho = _caminho_trabalho(usuario)
        if os.path.exists(caminho):
            os.remove(caminho)
    except Exception:
        pass
    return None


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

    # ── AS FOTOS ANEXADAS: a ENTRADA tambem se perde ────────────────────
    #
    # Este modulo guardava so o RESULTADO — a galeria. A ENTRADA (as fotos do
    # produto que a pessoa anexou) vivia apenas na memoria do processo do
    # Streamlit, e sumia junto com ele.
    #
    # 28/09, 17:17: a tela listava tres fotos anexadas e o botao respondia
    # "Suba pelo menos uma foto do produto". A lista de NOMES fica no
    # navegador; os BYTES ficam no processo. Reiniciou o processo, os nomes
    # continuam na tela e os bytes nao existem mais.
    _F1 = b"\x89PNG\r\n\x1a\n" + b"a" * 2000
    _F2 = b"\xff\xd8" + b"b" * 2000

    ok("sem fotos guardadas, nao ha o que recuperar", carregar_fotos("bia") == [])
    ok("salvar sem usuario nao derruba", salvar_fotos("", [_F1]) is False)
    ok("salvar lista vazia nao derruba", salvar_fotos("bia", []) is False)

    ok("as fotos sao gravadas", salvar_fotos("bia", [_F1, _F2],
                                             ["frente.png", "lado.jpg"]) is True)
    _fts = carregar_fotos("bia")
    ok("e voltam inteiras, na mesma ordem",
       [f["bytes"] for f in _fts] == [_F1, _F2])
    ok("com o nome de cada uma",
       [f["nome"] for f in _fts] == ["frente.png", "lado.jpg"])

    # O ciclo da galeria NAO pode levar as fotos junto: gerar de novo apaga a
    # galeria antiga, e quem esta gerando de novo precisa das MESMAS fotos.
    salvar("bia", "Urso Prata", [{"tipo": "1", "bytes": _IMG}])
    ok("gravar a galeria nao apaga as fotos anexadas",
       len(carregar_fotos("bia")) == 2)
    limpar("bia")
    ok("limpar a galeria tambem nao", len(carregar_fotos("bia")) == 2)
    arquivar("bia")
    ok("arquivar a galeria tambem nao", len(carregar_fotos("bia")) == 2)

    # O aviso na tela e desenhado a cada tecla digitada: ele nao pode ler os
    # bytes das fotos do disco toda vez.
    _res_ft = resumo_fotos("bia")
    ok("o resumo das fotos traz os nomes",
       [f["nome"] for f in _res_ft] == ["frente.png", "lado.jpg"])
    ok("e NAO le um unico byte de foto",
       all("bytes" not in f for f in _res_ft))

    # CADA CAMPO GUARDA O SEU. A pagina de Imagem tem quatro campos de
    # imagem; se todos escrevessem na mesma pasta, anexar uma referencia de
    # layout apagaria as fotos do produto — e o defeito voltaria pela porta
    # que eu acabei de fechar.
    salvar_fotos("bia", [_F1], ["ref.png"], campo="layout")
    ok("o campo novo nao mexe no campo do produto",
       len(carregar_fotos("bia")) == 2 and len(carregar_fotos("bia", campo="layout")) == 1)
    ok("e limpar um nao limpa o outro",
       limpar_fotos("bia", campo="layout") is None
       and carregar_fotos("bia", campo="layout") == []
       and len(carregar_fotos("bia")) == 2)

    ok("e da para descartar so as fotos", limpar_fotos("bia") is None
       and carregar_fotos("bia") == [] and resumo_fotos("bia") == [])

    # ── NOVO PRODUTO: O DISCO TEM DE ZERAR JUNTO COM A TELA ─────────────
    #
    # As duas funções abaixo existem para um botão só — "Novo Produto" — e as
    # duas cobrem o mesmo defeito por caminhos diferentes: o produto velho
    # voltando sozinho depois de a pessoa ter pedido para começar de novo.
    salvar_fotos("bia", [_F1, _F1], ["frente.png", "lado.jpg"])
    salvar_fotos("bia", [_F1], ["ref.png"], campo="layout")
    ok("as fotos dos dois campos estao no disco antes de zerar",
       len(carregar_fotos("bia")) == 2
       and len(carregar_fotos("bia", campo="layout")) == 1)
    # O CAMPO QUE AINDA NAO EXISTE entra aqui de proposito: a guarda mede a
    # VARREDURA, e nao os dois nomes que o codigo de hoje usa. Com uma lista
    # escrita, esta linha e a unica que reprovaria no dia do campo novo.
    salvar_fotos("bia", [_F1], ["amanha.png"], campo="campo_de_amanha")
    ok("limpar_todas_as_fotos leva TODOS os campos, inclusive o novo",
       limpar_todas_as_fotos("bia") is None
       and carregar_fotos("bia") == []
       and carregar_fotos("bia", campo="layout") == []
       and carregar_fotos("bia", campo="campo_de_amanha") == [])

    # E o `trabalho.json`: o nome do produto velho mora nele, e `app.py`
    # chama `restaurar` em toda sessao.
    salvar_trabalho("bia", {"img_nome_produto": "Urso Prata",
                            "img_codigo": "MS-URSO-1",
                            "ms_chat_hist": [{"role": "user", "content": "oi"}]})
    ok("o trabalho estava guardado",
       carregar_trabalho("bia").get("img_nome_produto") == "Urso Prata")
    limpar_trabalho("bia")
    ok("limpar_trabalho zera o produto, o codigo e a conversa",
       carregar_trabalho("bia") == {})
    # A GUARDA MEDE O CAMINHO INTEIRO, e nao a funcao sozinha: o que doeu nao
    # foi o arquivo ficar no disco, foi `restaurar` repor o produto velho na
    # tela. Entao a assercao parte de `restaurar`, que e quem o `app.py` chama.
    _tela = {}
    ok("e `restaurar` nao traz mais o produto velho de volta",
       restaurar("bia", _tela) == [] and _tela == {})

    # ── UM ANEXO NO CHAT NAO PODE APAGAR A CONVERSA (27/10) ─────────────
    #
    # `ms_chat_hist` ganha BYTES quando alguem anexa uma foto no chat, e
    # bytes nao cabem em JSON. O `continue` descartava a CHAVE INTEIRA: a
    # partir do primeiro anexo o historico parava de ser gravado, e um F5
    # devolvia a conversa vazia sem nada na tela dizendo por que.
    salvar_trabalho("bia", {"ms_chat_hist": [
        {"role": "user", "content": "gera a capa"},
        {"role": "user", "content": "olha essa", "img_bytes": [b"\x89PNG"]},
        {"role": "assistant", "content": "capa pronta", "peca": 1},
    ]})
    _volta = carregar_trabalho("bia").get("ms_chat_hist") or []
    ok("com um anexo no meio, a CONVERSA continua sendo gravada",
       [f["content"] for f in _volta]
       == ["gera a capa", "olha essa", "capa pronta"])
    # O ANEXO EM SI SE PERDE, e tudo bem: os bytes morrem com o processo de
    # qualquer jeito. O que nao pode se perder e o texto.
    ok("e so os bytes do anexo ficam de fora",
       all("img_bytes" not in f for f in _volta))
    # E O NUMERO DA PECA SOBREVIVE: e por ele que a imagem gerada volta a
    # aparecer na conversa depois do F5.
    ok("e o numero da peca gerada sobrevive ao F5",
       _volta[2].get("peca") == 1)

    _sh_t.rmtree(_base, ignore_errors=True)
    print("\nfalhas:", falhas)
    # O CODIGO DE SAIDA, QUE FALTAVA — e as duas mutacoes apontadas para ca
    # estavam VERDES POR ACIDENTE por causa dele.
    #
    # Sao dois leitores com respostas diferentes para a mesma pergunta "este
    # modulo reprovou?". O `conferir.py` le o TEXTO (`_reprovou` procura
    # "FALHA" na saida) e enxergava a falha; o `checar_mutacao` le o CODIGO DE
    # SAIDA, e para ele este arquivo nunca reprovava. Entao a mutacao
    # reintroduzia o defeito, o teste imprimia FALHA, e o veredito dizia
    # verde.
    #
    # E a mesma doenca que o CLAUDE.md registra duas vezes: 33 mutacoes do
    # `imagem.py` e 64 no total escondidas por esta linha ausente, e o
    # `varredura_formas.py` pelo lado espelhado, saindo 1 sempre.
    import sys as _sys_saida
    _sys_saida.exit(1 if falhas else 0)
