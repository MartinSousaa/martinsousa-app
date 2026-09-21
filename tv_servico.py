"""tv_servico.py — a TV num container só dela, servindo o próprio arquivo.

POR QUE ISTO EXISTE
-------------------
O `tv_worker.py` roda dentro do MESMO container do Studio. Uma volta é o Painel
de Metas inteiro, e ela caía em cima de quem estava trabalhando: a tela mostrava
"Reconectando ao servidor… os cliques não estão sendo enviados".

Três tentativas de repartir o container falharam pelo mesmo motivo:

    nice 19              -> reparte CPU, não reparte o resto
    esperar por presença -> só adia; alguém sempre está dentro
    teto de espera       -> é o próprio teto que cai em cima da pessoa
                            (quem entra a 100s do fim leva a volta na cara)

E o trabalho que derruba a sessão de quem produz **não serve a ninguém que
produz**: nenhuma tela do Studio lê o `static/tv.html`. Quem lê é o navegador da
TV de parede, e só ele. Repartir melhor era otimizar em volta do problema.

O QUE MUDA
----------
Este processo sobe como SERVIÇO SEPARADO no Railway, com container próprio. Ele
faz duas coisas e mais nada:

    1. serve o diretório static/ por HTTP, na porta que o Railway der
    2. roda o laço de regeneração, que reescreve static/tv.html

A partir daí o Studio e a TV não dividem CPU, memória nem processo. Uma volta de
31 segundos deixa de ser problema de alguém.

A CONSEQUÊNCIA QUE PRECISA SER DITA
-----------------------------------
Containers separados não dividem disco. O `static/tv.html` que este serviço
escreve NÃO aparece no serviço do Studio — e por isso **a URL da TV muda**: ela
passa a apontar para o domínio deste serviço, e não mais para
`app.martinsousa.com.br/app/static/tv.html`.

O Studio continua escrevendo o próprio `tv.html` quando alguém abre o Painel de
Metas (`placar.py:2508`), mas esse arquivo passa a não servir a ninguém. É
inofensivo e fica onde está: tirá-lo quebraria o modo `?tv=` de desenvolvimento.

O SEGREDO, QUE O PROCFILE ESCREVIA E AQUI NÃO CHEGA
---------------------------------------------------
O Procfile monta `.streamlit/secrets.toml` a partir da variável
`STREAMLIT_SECRETS` antes de subir o Streamlit. Este serviço tem start command
próprio e não passa pelo Procfile — sem repetir esse passo aqui, `placar` sobe
sem credencial do Trello e toda volta termina em "credenciais do Trello não
configuradas", com a TV congelada e o motivo escondido num log.
"""

import os
import sys
import threading
import time

_AQUI = os.path.dirname(os.path.abspath(__file__))
_STATIC = os.path.join(_AQUI, "static")


def _escrever_secrets():
    """Repete o que o Procfile faz antes de subir o Streamlit.

    Silencioso quando não há o que escrever: em desenvolvimento o arquivo já
    existe no disco, e sobrescrevê-lo com vazio apagaria as chaves locais.
    """
    bloco = os.environ.get("STREAMLIT_SECRETS") or ""
    plan = os.environ.get("PLANILHA_ID") or ""
    if not bloco and not plan:
        return "nada a escrever (STREAMLIT_SECRETS ausente)"
    try:
        destino = os.path.join(_AQUI, ".streamlit")
        os.makedirs(destino, exist_ok=True)
        with open(os.path.join(destino, "secrets.toml"), "w",
                  encoding="utf-8") as fh:
            if plan:
                fh.write('PLANILHA_ID = "%s"\n' % plan)
            fh.write(bloco)
        return "secrets.toml escrito"
    except Exception as e:
        return f"NÃO consegui escrever secrets.toml: {e}"


def _servidor_estatico(porta):
    """Serve só o diretório static/, e só leitura.

    A porta é aberta ANTES de importar `placar`. Esse import puxa streamlit,
    pandas e as bibliotecas do Google e leva segundos; o Railway derruba um
    serviço que demora a atender na porta, e o serviço morreria antes da
    primeira volta — reiniciando para morrer de novo.
    """
    import functools
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    os.makedirs(_STATIC, exist_ok=True)

    class Handler(SimpleHTTPRequestHandler):
        # Sem cache: o arquivo é reescrito a cada volta, e a TV busca de novo a
        # cada minuto. Um ETag guardado aqui repetiria o problema que o
        # `_write_tv_static` já teve que resolver do lado do Tornado.
        def end_headers(self):
            self.send_header("Cache-Control", "no-store, must-revalidate")
            super().end_headers()

        def do_GET(self):
            # A raiz responde o painel: a TV aponta para o domínio do serviço e
            # mais nada. Quem digita o endereço sem o nome do arquivo vê a TV,
            # e não uma listagem de diretório.
            if self.path in ("/", ""):
                self.path = "/tv.html"
            return super().do_GET()

        def list_directory(self, path):
            # Listagem de diretório é superfície à toa num serviço público.
            self.send_error(404, "Not Found")
            return None

        def log_message(self, formato, *args):
            pass          # o log do Railway não precisa de uma linha por GET

    Handler2 = functools.partial(Handler, directory=_STATIC)
    servidor = ThreadingHTTPServer(("0.0.0.0", porta), Handler2)
    print(f"[tv_servico] servindo {_STATIC} na porta {porta}",
          file=sys.stderr, flush=True)
    servidor.serve_forever()


def main():
    print("[tv_servico] " + _escrever_secrets(), file=sys.stderr, flush=True)

    porta = int(os.environ.get("PORT") or 8080)
    threading.Thread(target=_servidor_estatico, args=(porta,),
                     daemon=True).start()

    import logging
    logging.getLogger(
        "streamlit.runtime.scriptrunner_utils.script_run_context"
    ).setLevel(logging.ERROR)
    logging.getLogger("streamlit.runtime.caching.cache_data_api").setLevel(
        logging.ERROR)

    # Carimbo tirado ANTES do import, como no tv_worker: `import placar` puxa
    # streamlit, pandas e as bibliotecas do Google, e esse custo faz parte do
    # tempo em que a TV ainda está sem arquivo depois de um deploy.
    t0 = time.time()
    print("[tv_servico] subindo — regenera static/tv.html em laço",
          file=sys.stderr, flush=True)
    import placar
    placar._TV_INICIO_WORKER = t0
    print(f"[tv_servico] import do placar: {time.time() - t0:.1f}s",
          file=sys.stderr, flush=True)

    # CONTAINER PRÓPRIO: NÃO HÁ MAIS COM QUEM DISPUTAR.
    #
    # A espera por presença e o teto existiam para não atrapalhar o Studio, que
    # morava aqui do lado. Ele não mora mais. Manter a espera faria a TV ficar
    # até 15 minutos velha sem motivo nenhum — o arquivo de presença deste
    # container é de outro disco e nunca vai ter ninguém dentro.
    placar._TV_TETO_ESPERA_SEG = 0
    placar._loop_regenerador_tv()


if __name__ == "__main__":
    main()
