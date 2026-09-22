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


# ── O DIÁRIO DE REINÍCIOS ───────────────────────────────────────────────────
#
# POR QUE ELE PRECISOU EXISTIR
#
# A linha de saúde na tela responde a pergunta certa — mas exige que alguém
# esteja olhando na hora. O dono tentou: "não dá tempo da colaboradora subir a
# tela e tirar print, as vezes aparece a informação e some em segundos."
#
# Está certo. Pedir à pessoa que produz para virar instrumento de medição é
# trocar o trabalho dela por diagnóstico — e ainda assim perder o evento
# metade das vezes. Quem tem que registrar é o Studio.
#
# COMO SE SABE QUE REINICIOU, SEM PERGUNTAR A NINGUÉM
#
# Todo processo tem um PID e um instante de nascimento. A cada passada, o
# Studio compara o PID de agora com o último que ele mesmo anotou em disco.
# PID diferente = processo novo = o anterior morreu. Não há o que interpretar.
#
# E o arquivo guarda, do processo que morreu, a última memória medida: é ela
# que diz se a morte foi por memória ou por outra coisa. Esse número não
# existe em lugar nenhum depois que o processo morre — nem no log do Railway,
# que mostra o container e não o processo.
#
# ONDE ELE MORA
#
# No mesmo disco do rascunho, pelo mesmo motivo e com a mesma limitação: sem
# volume no Railway, ele não atravessa deploy. Atravessar o REINÍCIO já basta
# aqui — é justamente o reinício que se quer flagrar.

_DIARIO = os.path.join(
    os.environ.get("RASCUNHO_DIR") or "/tmp", "ms_studio_saude.json")
_MAX_EVENTOS = 50


def _ler_diario():
    import json
    try:
        with open(_DIARIO, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _gravar_diario(d):
    import json
    try:
        os.makedirs(os.path.dirname(_DIARIO), exist_ok=True)
        with open(_DIARIO, "w", encoding="utf-8") as fh:
            json.dump(d, fh)
        return True
    except Exception:
        # Diário é apoio, nunca requisito: disco cheio não pode impedir
        # ninguém de gerar imagem.
        return False


def anotar_passada(usuario="", tela=""):
    """Anota que este processo está vivo e, se for novo, registra o reinício.

    Chamada a cada passada do script. Devolve o evento de reinício quando ele
    ACABOU de ser detectado, e None nas outras vezes — assim a tela pode
    avisar na hora, uma única vez.
    """
    agora = time.time()
    pid = os.getpid()
    d = _ler_diario()
    anterior = d.get("processo") or {}
    evento = None

    if anterior and anterior.get("pid") != pid:
        # O processo anotado não é este: o outro morreu.
        evento = {
            "quando": agora,
            "pid_morto": anterior.get("pid"),
            "viveu_seg": round(max(0.0, (anterior.get("visto_em") or agora)
                                   - (anterior.get("nasceu_em") or agora)), 1),
            "memoria_final_mb": anterior.get("memoria_mb"),
            "limite_mb": anterior.get("limite_mb"),
            "usuario": anterior.get("usuario", ""),
            "tela": anterior.get("tela", ""),
            "imagens_mb": anterior.get("imagens_mb", 0.0),
        }
        eventos = list(d.get("eventos") or [])
        eventos.append(evento)
        d["eventos"] = eventos[-_MAX_EVENTOS:]

    usada, limite = memoria_mb()
    d["processo"] = {
        "pid": pid, "nasceu_em": _NASCIMENTO, "visto_em": agora,
        "memoria_mb": usada, "limite_mb": limite,
        "usuario": str(usuario or anterior.get("usuario", ""))[:40],
        "tela": str(tela or anterior.get("tela", ""))[:40],
        "imagens_mb": anterior.get("imagens_mb", 0.0),
    }
    _gravar_diario(d)
    return evento


def anotar_peso(mb):
    """Guarda quanta imagem esta sessão carrega, para o evento saber dizer."""
    d = _ler_diario()
    proc = d.get("processo") or {}
    proc["imagens_mb"] = round(float(mb or 0.0), 2)
    d["processo"] = proc
    return _gravar_diario(d)


def reinicios(limite=20):
    """Os reinícios registrados, do mais recente para o mais antigo."""
    return list(reversed((_ler_diario().get("eventos") or [])))[:limite]


def explicar(evento):
    """A frase que o dono lê. Ela diz a CAUSA quando o número permite.

    Memória acima de 85% do limite do container é reinício por memória, e não
    coincidência: é o container sendo morto por estourar o teto. Abaixo disso,
    a causa está fora deste processo — deploy ou o próprio Railway —, e dizer
    "foi memória" seria inventar.
    """
    if not evento:
        return ""
    from datetime import datetime, timedelta, timezone
    fuso = timezone(timedelta(hours=-3))
    hora = datetime.fromtimestamp(evento["quando"], fuso).strftime("%H:%M:%S")
    mem = evento.get("memoria_final_mb") or 0.0
    lim = evento.get("limite_mb") or 0.0
    pct = (mem / lim * 100) if lim else 0.0
    viveu = texto_tempo(evento.get("viveu_seg") or 0)
    quem = evento.get("usuario") or "alguém"
    onde = evento.get("tela") or "o Studio"
    imgs = evento.get("imagens_mb") or 0.0

    if lim and pct >= 85:
        causa = (f"**memória** — estava em {mem:.0f} MB de {lim:.0f} MB "
                 f"({pct:.0f}%)")
    elif lim:
        causa = (f"**não foi memória** — estava em {mem:.0f} MB de "
                 f"{lim:.0f} MB ({pct:.0f}%). Deploy ou o próprio Railway")
    else:
        causa = "**causa desconhecida** — não consegui ler o limite do container"

    extra = f" · {imgs:.0f} MB de imagem na sessão" if imgs else ""
    return (f"🔁 {hora} — o processo reiniciou depois de {viveu} de pé. "
            f"Causa: {causa}. Quem estava dentro: {quem}, em {onde}{extra}.")


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

    # ── o diario de reinicios ────────────────────────────────────────────
    # Disco proprio, para o teste nao mexer no diario de verdade.
    import tempfile as _tmp
    _DIARIO = os.path.join(_tmp.mkdtemp(), "saude_teste.json")
    globals()["_DIARIO"] = _DIARIO

    ok("diario vazio nao tem reinicio nenhum", reinicios() == [])
    ok("a primeira passada nao acusa reinicio",
       anotar_passada("Beatriz", "Imagem") is None)
    ok("nem a segunda, que e o mesmo processo",
       anotar_passada("Beatriz", "Imagem") is None)

    # Um processo que morre: o diario guarda outro PID.
    import json as _json
    _d = _ler_diario()
    _d["processo"]["pid"] = os.getpid() + 1          # finge outro processo
    _d["processo"]["nasceu_em"] = time.time() - 600  # que viveu 10 minutos
    _d["processo"]["memoria_mb"] = 7200.0
    _d["processo"]["limite_mb"] = 8192.0
    _d["processo"]["visto_em"] = time.time()
    _gravar_diario(_d)

    _ev = anotar_passada("Beatriz", "Imagem")
    ok("PID diferente e reinicio detectado", _ev is not None)
    ok("e o diario sabe quanto o morto viveu", 590 < _ev["viveu_seg"] < 610)
    ok("guardou a memoria final dele", _ev["memoria_final_mb"] == 7200.0)
    ok("e quem estava dentro", _ev["usuario"] == "Beatriz")

    # A frase que o dono le.
    _txt = explicar(_ev)
    ok("a frase acusa memoria quando passou de 85%", "memória" in _txt)
    ok("com o percentual escrito", "87%" in _txt or "88%" in _txt)
    ok("e diz quanto tempo o processo viveu", "10min" in _txt)

    # Memoria baixa NAO pode ser chamada de causa.
    _ev2 = dict(_ev, memoria_final_mb=500.0)
    ok("memoria baixa e dito como NAO sendo memoria",
       "não foi memória" in explicar(_ev2))
    ok("sem limite lido, a causa e declarada desconhecida",
       "desconhecida" in explicar(dict(_ev, limite_mb=0)))
    ok("evento vazio devolve texto vazio", explicar(None) == "")

    ok("o reinicio fica guardado no diario", len(reinicios()) == 1)
    ok("e a passada seguinte NAO duplica o evento",
       anotar_passada() is None and len(reinicios()) == 1)

    ok("o peso das imagens e anotado",
       anotar_peso(120.5) and _ler_diario()["processo"]["imagens_mb"] == 120.5)

    # Disco impossivel nunca pode derrubar a tela.
    globals()["_DIARIO"] = "/proc/impossivel/saude.json"
    ok("disco que nao aceita escrita nao levanta excecao",
       anotar_passada() is None and reinicios() == [])

    print("\nfalhas:", falhas)
