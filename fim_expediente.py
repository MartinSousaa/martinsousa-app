"""
fim_expediente.py — Que cartões deveriam ter parado quando o dia acabou.

O problema
----------
A pessoa vai embora e o cartão fica com EM ANDAMENTO. O relógio do Studio não
para: ele volta a andar sozinho às 9h do dia seguinte, e ela aparece
trabalhando sem ter tocado no cartão. Foi o que aconteceu com a Myrella — saída
registrada às 17h45 e o cartão ainda "em andamento" às 20h27.

A etiqueta que resolve já existe e já é entendida como interrupção
(placar_core.LABEL_FIM_EXPEDIENTE). Falta alguém pô-la.

A regra, decidida pelo gestor
-----------------------------
1. Bateu a saída  -> a partir daquele instante, os cartões dela em EM ANDAMENTO
                     devem receber FIM DE EXPEDIENTE. Vale a qualquer hora, o
                     que cobre quem foi embora mais cedo.
2. Não bateu      -> uma hora depois do fim do expediente dela, mesma coisa.
                     Cobre quem foi embora e esqueceu de bater a saída.

Este módulo só DECIDE. Ele não fala com o Trello, e é de propósito: escrever no
board é uma capacidade que o Studio nunca teve, e o ambiente de teste aponta
para o board real. Quem aplica é escolha de infraestrutura — um cenário do Make
ou uma tarefa agendada — e recebe daqui a lista pronta, com o motivo de cada
cartão.
"""

from datetime import datetime, timedelta

# Quanto se espera depois do fim do expediente antes de assumir que a pessoa
# foi embora sem bater. Uma hora: menos que isso pega quem ficou terminando
# algo, mais que isso deixa o relógio correndo a noite toda.
ESPERA_SEM_BATIDA_MIN = 60


def _hhmm(texto):
    """'17:45' -> minutos desde a meia-noite. None quando não dá para ler."""
    try:
        h, m = str(texto).strip().split(":")[:2]
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def decidir(agora, pessoas, cartoes, espera_min=ESPERA_SEM_BATIDA_MIN):
    """Quais cartões devem receber FIM DE EXPEDIENTE agora.

    agora    datetime local.
    pessoas  {username: {"fim": "HH:MM", "saida": "HH:MM"|None}} — o fim do
             expediente contratado e a saída batida hoje, se houve.
    cartoes  [{"id", "nome", "membros": [username]}] com EM ANDAMENTO agora.

    Devolve [{"id", "nome", "quem", "motivo"}], um por cartão. Cartão de duas
    pessoas só entra quando TODAS já encerraram: enquanto uma continua, o
    trabalho continua.
    """
    agora_min = agora.hour * 60 + agora.minute
    encerrado = {}
    for user, info in (pessoas or {}).items():
        saida = _hhmm((info or {}).get("saida"))
        if saida is not None:
            if agora_min >= saida:
                encerrado[user] = f"bateu a saída às {info['saida']}"
            continue
        fim = _hhmm((info or {}).get("fim"))
        if fim is None:
            continue
        limite = fim + espera_min
        if agora_min >= limite:
            encerrado[user] = (
                f"sem batida de saída, {espera_min} min depois do fim do "
                f"expediente ({info['fim']})")

    fora = []
    for c in cartoes or []:
        membros = [m for m in (c.get("membros") or [])]
        if not membros:
            continue
        if not all(m in encerrado for m in membros):
            continue
        fora.append({
            "id": c.get("id"),
            "nome": c.get("nome", ""),
            "quem": ", ".join(membros),
            "motivo": " · ".join(dict.fromkeys(encerrado[m] for m in membros)),
        })
    return fora


# ── Conferência ───────────────────────────────────────────────────────────────
# `python3 fim_expediente.py` roda os casos abaixo. Eles moram aqui, e não num
# arquivo de teste à parte, porque este repositório não tem suíte: teste que
# não viaja junto do código é teste que ninguém roda.
if __name__ == "__main__":
    def _em(h, m=0):
        return datetime(2026, 9, 1, h, m)

    MY, BIA = "myrelladesouza", "beatriz51"
    UM = [{"id": "c1", "nome": "excluindo notas bling", "membros": [MY]}]
    DOIS = [{"id": "c2", "nome": "Criativo em dupla", "membros": [MY, BIA]}]

    CASOS = [
        ("saiu no horário e deixou o cartão aberto",
         _em(18, 0), {MY: {"fim": "17:45", "saida": "17:45"}}, UM, 1),
        ("um minuto antes da saída registrada",
         _em(17, 44), {MY: {"fim": "17:45", "saida": "17:45"}}, UM, 0),
        ("foi embora mais cedo, bateu às 15:20",
         _em(15, 30), {MY: {"fim": "17:45", "saida": "15:20"}}, UM, 1),
        ("sem batida, meia hora depois do fim — ainda espera",
         _em(18, 30), {MY: {"fim": "17:45", "saida": None}}, UM, 0),
        ("sem batida, uma hora depois do fim",
         _em(18, 46), {MY: {"fim": "17:45", "saida": None}}, UM, 1),
        ("meio do expediente, sem batida",
         _em(11, 0), {MY: {"fim": "17:45", "saida": None}}, UM, 0),
        ("cartão de dupla, só uma encerrou",
         _em(18, 0), {MY: {"fim": "17:45", "saida": "17:45"},
                      BIA: {"fim": "18:00", "saida": None}}, DOIS, 0),
        ("cartão de dupla, as duas encerraram",
         _em(19, 5), {MY: {"fim": "17:45", "saida": "17:45"},
                      BIA: {"fim": "18:00", "saida": None}}, DOIS, 1),
        ("cartão sem membro fica de fora",
         _em(20, 0), {MY: {"fim": "17:45", "saida": "17:45"}},
         [{"id": "c3", "nome": "órfão", "membros": []}], 0),
        ("horário ilegível na configuração não derruba nada",
         _em(20, 0), {MY: {"fim": "", "saida": None}}, UM, 0),
    ]

    falhas = 0
    for nome, agora, pessoas, cartoes, esperado in CASOS:
        saida = decidir(agora, pessoas, cartoes)
        ok = len(saida) == esperado
        falhas += not ok
        print(("ok    " if ok else "FALHA ") + nome)
        for item in saida:
            print(f"         {item['nome']} ({item['quem']}) · {item['motivo']}")
    print("\nfalhas:", falhas)
