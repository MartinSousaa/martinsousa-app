"""Mantém o static/tv.html vivo, sem depender de ninguém abrir o Studio.

O PROBLEMA QUE ISTO RESOLVE
---------------------------
A thread que regenera o painel da TV era ligada em `app.py`, e `app.py` é o
script do Streamlit: ele só roda quando um NAVEGADOR abre uma sessão. A TV, por
sua vez, é um arquivo estático — pedir `static/tv.html` não abre sessão nenhuma
e portanto nunca liga a thread.

E `static/tv.html` não está no repositório: ele nasce quando a thread o escreve
(placar._write_tv_static). Junte as duas coisas e o que sai é isto:

    deploy sobe um container novo
      -> static/tv.html NÃO EXISTE
      -> a TV pede o arquivo e recebe 404
      -> e só passa a existir quando alguém abre o Studio no navegador

Ou seja: a TV dependia de um humano abrir o Painel de Metas para voltar a
funcionar, depois de todo deploy e de todo reinício do container. O próprio
diagnóstico já dizia isso em voz alta — "quem está salvando a TV é alguém com o
Painel aberto — e no fim do expediente ela congela" — e ninguém tinha ligado o
aviso à causa.

Aqui a regeneração vira um processo próprio, subido pelo Procfile junto com o
app. Ele não precisa de sessão, de navegador nem de ninguém: começa com o
container e escreve o arquivo antes de a primeira pessoa chegar.
"""

import logging
import os
import sys
import time


def main():
    # A thread do app não pode subir junto: duas regenerações do mesmo arquivo
    # dobram as chamadas ao Trello e a memória do container sem entregar nada.
    # O Procfile marca o processo do Streamlit com TV_WORKER=1, e é assim que
    # `app.py` sabe que este aqui já está cuidando disso.
    logging.getLogger(
        "streamlit.runtime.scriptrunner_utils.script_run_context"
    ).setLevel(logging.ERROR)
    logging.getLogger("streamlit.runtime.caching.cache_data_api").setLevel(
        logging.ERROR)

    # Carimbo tirado ANTES do import: `import placar` puxa streamlit, pandas e
    # as bibliotecas do Google, e esse custo faz parte do tempo em que a TV
    # ainda esta sem arquivo depois de um deploy. Sem medi-lo separado, ele
    # entra na conta como se fosse lentidao da regeneracao.
    t0 = time.time()
    print("[tv_worker] subindo — regenera static/tv.html a cada volta",
          file=sys.stderr, flush=True)
    import placar
    placar._TV_INICIO_WORKER = t0
    print(f"[tv_worker] import do placar: {time.time() - t0:.1f}s",
          file=sys.stderr, flush=True)
    # O laço é o mesmo que a thread rodava: ele já trata exceção por volta,
    # registra o motivo em TV_STATUS e nunca sai sozinho.
    placar._loop_regenerador_tv()


if __name__ == "__main__":
    main()
