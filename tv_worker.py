"""Mantém o static/tv.html vivo, sem depender de ninguém abrir o Studio.

NÃO É MAIS ELE QUE RODA EM PRODUÇÃO — veja `tv_servico.py`.
----------------------------------------------------------
Este arquivo subia pelo Procfile, DENTRO do container do Studio, e era daí que
vinha o "Reconectando ao servidor… os cliques não estão sendo enviados": uma
volta é o Painel de Metas inteiro, e ela caía em cima de quem estava
trabalhando. Repartir o container falhou três vezes (nice, espera por presença,
teto de espera), e a terceira falhou porque o próprio teto é o que atropela
quem entra perto do fim dele.

Desde 21/09/2026 a regeneração é um SERVIÇO à parte no Railway
(`tv_servico.py`), que além do laço serve o `static/` por HTTP — porque
containers separados não dividem disco.

Este continua aqui para rodar o laço à mão, fora do Railway, quando se quer
regenerar a TV sem subir o servidor estático junto.


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


def _sair_da_frente():
    """Põe este processo na última prioridade da CPU.

    Ele divide o container com o Streamlit, e o Streamlit atende gente. Com a
    prioridade mais baixa, o sistema operacional só dá CPU à TV quando ninguém
    está esperando por ela — e o "Reconectando ao servidor" deixa de depender
    de o worker ter a educação de esperar.

    É cinto e suspensório junto com a espera por presença: a espera cobre o
    caso normal, o `nice` cobre a volta que acontece mesmo assim.
    """
    try:
        os.nice(19)
        print("[tv_worker] prioridade de CPU rebaixada (nice 19)",
              file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[tv_worker] nao consegui rebaixar a prioridade: {e}",
              file=sys.stderr, flush=True)


def main():
    _sair_da_frente()
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
