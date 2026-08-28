"""
cronometro.py — Onde os segundos são gastos, medido no servidor.

Por que existe
--------------
Uma medição de fora diz que a tela leva 13 segundos; não diz em quê. Toda
hipótese sobre isso — cache errando, planilha lenta, Trello lento, token
expirado — é palpite até alguém cronometrar cada chamada externa separadamente.
Este módulo faz isso e mostra o resultado dentro do Studio, para quem está
sentindo a lentidão poder ler sem depender de log de servidor.

Como usar
---------
    import cronometro
    with cronometro.medir("Trello: board"):
        ...

E, no fim da tela, `cronometro.painel()` para o gestor ver a conta.

O custo da própria medição é um time.perf_counter() por bloco. Fica ligado: uma
medição que só existe quando alguém lembra de ligar não pega o problema que
aparece uma vez por hora.
"""
import time

import streamlit as st

CHAVE = "_crono_render"
CHAVE_IDADE = "_crono_processo_inicio"

# Quando o processo subiu. Serve para cruzar a lentidao com a idade do processo:
# a degradacao medida virava a chave por volta dos 55 minutos, e sem este numero
# na tela nao da para saber se a proxima medicao esta antes ou depois da virada.
_INICIO_PROCESSO = time.time()


def idade_processo_min():
    return (time.time() - _INICIO_PROCESSO) / 60


def _lista():
    if CHAVE not in st.session_state:
        st.session_state[CHAVE] = []
    return st.session_state[CHAVE]


def zerar():
    """Começa a contagem desta passada."""
    st.session_state[CHAVE] = []


class medir:
    """Cronometra um bloco e guarda o resultado da passada atual."""

    def __init__(self, rotulo, detalhe=""):
        self.rotulo = rotulo
        self.detalhe = detalhe

    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        try:
            _lista().append({
                "rotulo": self.rotulo,
                "detalhe": self.detalhe,
                "seg": time.perf_counter() - self.t0,
            })
        except Exception:
            pass
        return False


def marcar(rotulo, seg, detalhe=""):
    """Registra uma medição já feita — para quem cronometra por dentro."""
    try:
        _lista().append({"rotulo": rotulo, "detalhe": detalhe, "seg": float(seg)})
    except Exception:
        pass


def painel(titulo="⏱️ Onde foram os segundos desta tela"):
    """Mostra a conta da passada atual. Só faz sentido para quem investiga."""
    medidas = list(_lista())
    total = sum(m["seg"] for m in medidas)
    with st.expander(f"{titulo} — {total:.1f}s em {len(medidas)} chamada(s) · "
                     f"processo com {idade_processo_min():.0f} min", expanded=False):
        if not medidas:
            st.caption("Nenhuma chamada externa nesta passada — veio tudo de cache.")
            return
        # Agrupa por rotulo: o que interessa e qual FONTE custa, nao cada
        # chamada isolada.
        por_rotulo = {}
        for m in medidas:
            d = por_rotulo.setdefault(m["rotulo"], {"n": 0, "seg": 0.0, "detalhes": []})
            d["n"] += 1
            d["seg"] += m["seg"]
            if m["detalhe"]:
                d["detalhes"].append(m["detalhe"])
        linhas = ["| Fonte | Chamadas | Tempo | % |", "|---|---:|---:|---:|"]
        for rotulo, d in sorted(por_rotulo.items(), key=lambda kv: -kv[1]["seg"]):
            pct = (d["seg"] / total * 100) if total else 0
            linhas.append(f"| {rotulo} | {d['n']} | {d['seg']:.2f}s | {pct:.0f}% |")
        st.markdown("\n".join(linhas))
        for rotulo, d in por_rotulo.items():
            if d["detalhes"]:
                st.caption(f"{rotulo}: " + " · ".join(d["detalhes"][:6]))
