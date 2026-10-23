"""
fim_expediente.py — Que cartões deveriam ter parado quando o dia acabou.

O problema
----------
A pessoa vai embora e o cartão fica com EM ANDAMENTO. O relógio do Studio não
para: ele volta a andar sozinho às 9h do dia seguinte, e ela aparece
trabalhando sem ter tocado no cartão.

A etiqueta que resolve já existe e já é entendida como interrupção
(placar_core.LABEL_FIM_EXPEDIENTE). Este módulo decide em quais cartões pô-la.

A regra (dono, 23/10)
---------------------
**Às 18h30 de Brasília, TODO cartão EM ANDAMENTO recebe FIM DE EXPEDIENTE.**
Em sábado, domingo e feriado, a qualquer hora. Não olha o ponto, não olha quem
está no cartão.

POR QUE A REGRA ANTERIOR FOI EMBORA
-----------------------------------
Antes, cada cartão esperava TODOS os membros "encerrarem" o dia: saída batida
na RHiD, ou uma hora depois do fim do expediente de cada um, nunca antes das
19h. Em outubro a Linha do tempo mostrou cartões correndo até meia-noite em
dia útil e o fim de semana inteiro (print do dono, 23/10). A regra tinha portas
por onde o cartão escapava para sempre, todas silenciosas:

  · membro que a RHiD não reconhece  -> nunca "encerrava", o cartão não fechava;
  · cartão sem ninguém anexado        -> não fechava em dia nenhum;
  · RHiD fora do ar                   -> a rotina abortava e não fechava nada;
  · sexta à noite que escapou          -> o fim de semana era pulado inteiro.

Uma regra que depende de três sistemas responderem certo falha quando
qualquer um deles falha. A hora fixa só depende do relógio.

O custo, dito em voz alta: quem estiver trabalhando depois das 18h30 tem o
cartão interrompido e precisa tirar a etiqueta para seguir. O expediente do
time termina às 18h; o dono escolheu o corte sabendo disso.

Este módulo só DECIDE. Quem escreve no Trello é `fechar_expediente.py`.
"""

from datetime import datetime

# O corte, em horário de Brasília. `agora` chega sempre local: quem chama
# converte com placar_core.FUSO (o container roda em UTC).
CORTE_HORA, CORTE_MIN = 18, 30


def corte_txt():
    return f"{CORTE_HORA}h{CORTE_MIN:02d}"


def passou_do_corte(agora, dia_util=True):
    """True quando todo cartão aberto já deve parar."""
    if not dia_util:
        return True
    return (agora.hour, agora.minute) >= (CORTE_HORA, CORTE_MIN)


def _motivo(agora, dia_util):
    if not dia_util:
        return "dia sem expediente (fim de semana ou feriado)"
    return f"{corte_txt()}, fim do expediente"


def decidir(agora, cartoes, dia_util=True):
    """Quais cartões devem receber FIM DE EXPEDIENTE agora.

    agora     datetime local (Brasília).
    cartoes   [{"id", "nome", "membros": [username]}] com EM ANDAMENTO agora.
    dia_util  False em sábado, domingo e feriado.

    Devolve [{"id", "nome", "quem", "motivo"}]: antes do corte, nenhum; depois,
    todos — com membro ou sem.
    """
    if not passou_do_corte(agora, dia_util):
        return []
    motivo = _motivo(agora, dia_util)
    return [{"id": c.get("id"), "nome": c.get("nome", ""),
             "quem": ", ".join(c.get("membros") or []) or "—",
             "motivo": motivo}
            for c in (cartoes or [])]


def diagnosticar(agora, cartoes, dia_util=True):
    """Por que cada cartão aberto NÃO foi fechado. Função pura.

    Com a hora fixa só existe uma porta: ainda não deu a hora. Depois do corte
    nenhum cartão fica de fora — quem estiver aberto é para `decidir`, e se ele
    continua aberto é porque a rotina não rodou.
    """
    if passou_do_corte(agora, dia_util):
        return []
    return [{"id": c.get("id"), "nome": c.get("nome", ""),
             "quem": ", ".join(c.get("membros") or []) or "—",
             "porque": "antes_do_corte",
             "detalhe": f"São {agora:%H:%M}; a rotina fecha todos às {corte_txt()}."}
            for c in (cartoes or [])]


# ── Conferência ───────────────────────────────────────────────────────────────
# `python3 fim_expediente.py` roda os casos abaixo.

if __name__ == "__main__":
    falhas = 0

    def _ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    def _em(h, m=0, dia=1):
        return datetime(2026, 10, dia, h, m)

    UM = [{"id": "c1", "nome": "excluindo notas bling", "membros": ["myrelladesouza"]}]
    DOIS = [{"id": "c2", "nome": "dupla", "membros": ["myrelladesouza", "beatriz51"]}]
    ORFAO = [{"id": "c3", "nome": "órfão", "membros": []}]
    # Quem a RHiD nao conhecia prendia o cartao para sempre: o caso que fez a
    # regra mudar. Agora o nome da pessoa nao entra na decisao.
    DESCONHECIDO = [{"id": "c4", "nome": "x", "membros": ["brumielly"]}]

    _ok("o corte é 18h30, escrito assim na tela", corte_txt() == "18h30")
    _ok("passou_do_corte: 18:30 sim, 18:29 não, sábado sempre",
        passou_do_corte(_em(18, 30)) and not passou_do_corte(_em(18, 29))
        and passou_do_corte(_em(6, 0), dia_util=False))
    _ok("18:29 ainda não fecha", decidir(_em(18, 29), UM) == [])
    _ok("18:30 em ponto fecha", len(decidir(_em(18, 30), UM)) == 1)
    _ok("23:00 fecha", len(decidir(_em(23, 0), UM)) == 1)
    _ok("cartão de dupla fecha às 18:30, sem esperar ninguém",
        len(decidir(_em(18, 30), DOIS)) == 1)
    _ok("cartão sem membro também fecha", len(decidir(_em(18, 30), ORFAO)) == 1)
    _ok("membro que a RHiD não conhece não segura o cartão",
        len(decidir(_em(18, 30), DESCONHECIDO)) == 1)
    _ok("fim de semana fecha a qualquer hora, inclusive de manhã",
        len(decidir(_em(9, 0, dia=3), UM, dia_util=False)) == 1)
    _ok("manhã de dia útil não fecha", decidir(_em(9, 0), UM) == [])
    _ok("o motivo diz a hora do corte",
        "18h30" in decidir(_em(18, 30), UM)[0]["motivo"])
    _ok("o motivo do fim de semana diz que não há expediente",
        "sem expediente" in decidir(_em(9, 0), UM, dia_util=False)[0]["motivo"])
    _ok("lista vazia e None não derrubam",
        decidir(_em(19, 0), []) == [] and decidir(_em(19, 0), None) == [])
    _ok("antes do corte o diagnóstico diz a hora",
        [d["porque"] for d in diagnosticar(_em(15, 0), UM)] == ["antes_do_corte"])
    _ok("depois do corte ninguém fica preso no diagnóstico",
        diagnosticar(_em(18, 30), UM + ORFAO + DESCONHECIDO) == [])

    print("\nfalhas:", falhas)
    raise SystemExit(1 if falhas else 0)
