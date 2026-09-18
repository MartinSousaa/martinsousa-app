"""saude.py — o processo está de pé desde quando, e com quanta memória.

POR QUE ISTO EXISTE
-------------------
O Studio começou a mostrar "Reconectando ao servidor… os cliques não estão
sendo enviados", o chat passou a perder o histórico e as imagens geradas não
chegavam à tela. Três sintomas, e nenhum deles diz QUAL é a causa:

    rerun demais            -> a tela repinta, mas o histórico fica
    script preso            -> os cliques não chegam, e o histórico fica
    PROCESSO REINICIADO     -> o histórico some, porque ele vive na memória

O terceiro é o único que apaga `session_state`. "O chat perde histórico" é,
portanto, a assinatura de um reinício — e reinício num container é quase
sempre memória estourada.

Sem medir, a diferença entre os três é opinião. Com o tempo de vida do
processo na tela, ela é um número: se o "de pé há" volta para segundos toda
vez que a tela reconecta, o processo está morrendo e voltando.

NADA AQUI DEPENDE DE BIBLIOTECA NOVA. `/proc` é do Linux, que é onde o
container roda, e a ausência dele não derruba nada — devolve vazio.
"""

import os
import time

_NASCIMENTO = time.time()

# Quantas vezes o script rodou neste processo. Não é por sessão: é o total, e
# serve para separar "muitos reruns" de "poucos reruns num processo novo".
_PASSADAS = {"n": 0}


def contar_passada():
    _PASSADAS["n"] += 1
    return _PASSADAS["n"]


def de_pe_ha():
    """Segundos desde que ESTE processo começou."""
    return max(0.0, time.time() - _NASCIMENTO)


def texto_tempo(seg):
    seg = int(seg or 0)
    if seg < 60:
        return f"{seg}s"
    if seg < 3600:
        return f"{seg // 60}min {seg % 60}s"
    return f"{seg // 3600}h {(seg % 3600) // 60}min"


def memoria_mb():
    """(usada_mb, limite_mb). 0.0 quando não dá para saber.

    `VmRSS` é o que o processo ocupa de verdade. O limite vem do cgroup — é o
    número que o Railway usa para matar o container, e sem ele "300 MB" não
    diz se está perto ou longe.
    """
    usada = 0.0
    try:
        with open("/proc/self/status", encoding="utf-8") as f:
            for linha in f:
                if linha.startswith("VmRSS:"):
                    usada = float(linha.split()[1]) / 1024.0
                    break
    except Exception:
        pass
    limite = 0.0
    for caminho in ("/sys/fs/cgroup/memory.max",
                    "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            with open(caminho, encoding="utf-8") as f:
                bruto = f.read().strip()
            if bruto and bruto != "max":
                v = float(bruto) / (1024 * 1024)
                # Sem limite, o cgroup devolve um número absurdo.
                if 0 < v < 1024 * 1024:
                    limite = v
                break
        except Exception:
            continue
    return round(usada, 1), round(limite, 1)


def peso_da_sessao(estado):
    """Quantos MB de imagem esta sessão está segurando, e onde.

    A galeria, as fotos originais e o balde de recuperação guardam BYTES de
    imagem em `session_state` — e `session_state` é memória do processo, por
    sessão aberta. Três colaboradores com oito peças de 1,5 MB são 36 MB que
    ninguém vê na tela.
    """
    fora = {}
    try:
        for chave, valor in dict(estado or {}).items():
            n = _bytes_de(valor)
            if n > 0:
                fora[chave] = round(n / (1024 * 1024), 2)
    except Exception:
        return {}, 0.0
    fora = dict(sorted(fora.items(), key=lambda x: -x[1])[:8])
    return fora, round(sum(fora.values()), 2)


def _bytes_de(v, fundo=0):
    """Soma os bytes de imagem dentro de listas e dicionários, sem cavar fundo
    demais: `session_state` tem estruturas grandes, e varrer tudo custaria
    justamente o que se está tentando medir."""
    if fundo > 3:
        return 0
    if isinstance(v, (bytes, bytearray)):
        return len(v)
    if isinstance(v, (list, tuple)):
        return sum(_bytes_de(x, fundo + 1) for x in v[:60])
    if isinstance(v, dict):
        return sum(_bytes_de(x, fundo + 1) for x in list(v.values())[:60])
    return 0


def resumo(estado=None):
    """Tudo junto, para a tela mostrar numa linha."""
    usada, limite = memoria_mb()
    por_chave, total = peso_da_sessao(estado)
    return {
        "de_pe_ha_seg": round(de_pe_ha(), 1),
        "de_pe_ha": texto_tempo(de_pe_ha()),
        "passadas": _PASSADAS["n"],
        "memoria_mb": usada,
        "limite_mb": limite,
        "pct_memoria": round(usada / limite * 100, 1) if limite else 0.0,
        "imagens_na_sessao_mb": total,
        "por_chave": por_chave,
        "pid": os.getpid(),
    }


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    ok("o processo nasce com tempo de vida perto de zero", de_pe_ha() < 5)
    ok("a contagem de passadas sobe", contar_passada() == 1 and contar_passada() == 2)
    ok("segundos viram texto curto", texto_tempo(45) == "45s")
    ok("minutos tambem", texto_tempo(125) == "2min 5s")
    ok("e horas", texto_tempo(7300) == "2h 1min")

    _est = {"img_galeria": [{"bytes": b"x" * (1024 * 1024)},
                            {"bytes": b"y" * (512 * 1024)}],
            "img_fotos_originais": [b"z" * (256 * 1024)],
            "nome": "texto nao conta"}
    _por, _tot = peso_da_sessao(_est)
    ok("a galeria e medida em MB", _por["img_galeria"] == 1.5)
    ok("as fotos originais tambem", _por["img_fotos_originais"] == 0.25)
    ok("texto nao entra na conta", "nome" not in _por)
    ok("e o total soma as duas", _tot == 1.75)
    ok("estado vazio nao derruba", peso_da_sessao(None) == ({}, 0.0)
       and peso_da_sessao({}) == ({}, 0.0))

    _r = resumo(_est)
    ok("o resumo traz o pid e o tempo de vida",
       _r["pid"] > 0 and "de_pe_ha" in _r)
    ok("memoria sem /proc nao derruba, devolve zero",
       isinstance(_r["memoria_mb"], float))

    print("\nfalhas:", falhas)
