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
0. Nunca antes das 19h (horário de Brasília). Piso absoluto, vale para as duas
   regras abaixo.
1. Bateu a saída  -> os cartões dela em EM ANDAMENTO recebem FIM DE EXPEDIENTE.
2. Não bateu      -> uma hora depois do fim do expediente dela, mesma coisa.
                     Cobre quem foi embora e esqueceu de bater a saída.

POR QUE O PISO DAS 19h EXISTE
-----------------------------
A regra 1 valia "a qualquer hora", para cobrir quem foi embora mais cedo. Em
09/09 isso fechou o cartão de alguém que estava trabalhando:

    [09/09 15:00:42] fechado: PORTA 12 RELÓGIOS MARROM COM INTERIOR PRETO
                     · myrelladesouza · bateu a saída às 14:33

Ela não tinha ido embora — 14:33 é a volta do almoço dela, e o expediente
termina 17:45. Quem chamou aquilo de "saída" foi `rhid_api._extrair_marcacoes`
(rhid_api.py:493-494): com DUAS batidas no dia, ele assume "entrada e saída,
sem almoço". A suposição está certa para quem lê o dia depois de fechado — que
e para quem ela foi escrita, o cálculo de ociosidade — e está errada no meio da
tarde, quando duas batidas quase sempre significam "as outras ainda não
chegaram".

A mesma função responde a duas perguntas diferentes: "como foi o dia dela?" e
"ela já foi embora?". Aqui só a segunda importa, e ela não tem resposta
confiável antes do fim do expediente. O piso é o que torna a leitura segura:
às 19h, duas batidas realmente querem dizer que a pessoa saiu.

O custo, dito em voz alta: quem for embora de verdade às 15h fica com o cartão
correndo até as 19h. É o que o gestor pediu, sabendo disso — melhor do que
fechar o cartão de quem está trabalhando.

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

# Piso absoluto: nenhum cartão é fechado antes desta hora, local. Ver o cabeçalho
# — antes disso não dá para distinguir "foi embora" de "as batidas do dia ainda
# não chegaram todas", e o erro fecha o cartão de quem está trabalhando.
HORA_MINIMA = 19


def _hhmm(texto):
    """'17:45' -> minutos desde a meia-noite. None quando não dá para ler."""
    try:
        h, m = str(texto).strip().split(":")[:2]
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def decidir(agora, pessoas, cartoes, espera_min=ESPERA_SEM_BATIDA_MIN,
            hora_minima=HORA_MINIMA):
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
    # O piso vem antes de tudo: sem ele nao ha leitura confiavel de "ja foi
    # embora", e devolver lista vazia e a resposta certa, nao uma desistencia.
    if agora.hour < hora_minima:
        return []
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


def diagnosticar(agora, pessoas, cartoes, espera_min=ESPERA_SEM_BATIDA_MIN,
                hora_minima=HORA_MINIMA):
    """Por que cada cartão aberto NÃO foi fechado. Função pura.

    `decidir` responde "quais fecho agora"; esta responde "e os outros, por
    quê". São perguntas diferentes e faltava a segunda: cartão que atravessa o
    dia inteiro EM ANDAMENTO não deixa rastro nenhum — a rotina roda, diz
    "sucesso", e some com ele da lista sem dizer que existiu.

    As portas por onde um cartão escapa, todas silenciosas até aqui:
      sem_membro   ninguém anexado. Nunca fecha, e o relógio corre para sempre.
      sem_ponto    a pessoa não existe para a RHiD — username do Trello escrito
                   diferente, ou nome que o mapa da RHiD não reconhece. É o caso
                   que atravessa o dia: sem saber se ela foi embora, o cartão
                   nunca pode ser fechado, e ninguém é avisado disso.
      sem_horario  a pessoa é reconhecida, mas não tem `fim` de expediente.
      aguardando   um dos membros ainda não encerrou o dia dele.

    Devolve [{"id","nome","quem","porque","detalhe"}] ordenado por porta.
    """
    agora_min = agora.hour * 60 + agora.minute
    encerrado, sem_horario = {}, set()
    for user, info in (pessoas or {}).items():
        saida = _hhmm((info or {}).get("saida"))
        if saida is not None:
            if agora_min >= saida:
                encerrado[user] = f"bateu a saída às {info['saida']}"
            continue
        fim = _hhmm((info or {}).get("fim"))
        if fim is None:
            sem_horario.add(user)
            continue
        if agora_min >= fim + espera_min:
            encerrado[user] = (f"sem batida, {espera_min} min depois do fim "
                               f"({info['fim']})")

    fora = []
    cedo = agora.hour < hora_minima
    for c in cartoes or []:
        membros = list(c.get("membros") or [])
        base = {"id": c.get("id"), "nome": c.get("nome", ""),
                "quem": ", ".join(membros) or "—"}
        if not membros:
            fora.append({**base, "porque": "sem_membro",
                         "detalhe": "Nenhuma pessoa anexada ao cartão. Este "
                                    "nunca fecha sozinho."})
            continue
        if cedo:
            fora.append({**base, "porque": "antes_das_19h",
                         "detalhe": f"São {agora:%H:%M}; a rotina só fecha a "
                                    f"partir das {hora_minima}h."})
            continue
        faltam = [m for m in membros if m not in encerrado]
        if not faltam:
            continue                      # este fecha; quem lista é `decidir`
        # Membro que nao esta em `pessoas` nao e "ainda trabalhando": e alguem
        # sobre quem nao ha informacao nenhuma. Chamar isso de aguardando
        # escondia a causa real dos cartoes que varam o dia.
        sem_p = [m for m in faltam if m not in (pessoas or {})]
        if sem_p:
            fora.append({**base, "porque": "sem_ponto",
                         "detalhe": "A RHiD não reconhece: " + ", ".join(sem_p)
                                    + ". Confira o username do Trello e o nome "
                                      "na RHiD em Equipe medida."})
            continue
        sem_h = [m for m in faltam if m in sem_horario]
        if sem_h:
            fora.append({**base, "porque": "sem_horario",
                         "detalhe": "Sem fim de expediente na RHiD: "
                                    + ", ".join(sem_h)})
        else:
            fora.append({**base, "porque": "aguardando",
                         "detalhe": "Ainda no expediente: " + ", ".join(faltam)})
    ordem = {"sem_membro": 0, "sem_ponto": 1, "sem_horario": 2,
             "aguardando": 3, "antes_das_19h": 4}
    fora.sort(key=lambda x: (ordem.get(x["porque"], 9), x["nome"]))
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
        # ── O piso das 19h ────────────────────────────────────────────────────
        # O primeiro e o caso real de 09/09: a volta do almoco lida como saida
        # fechou o cartao de quem estava trabalhando. E o motivo de o piso
        # existir, entao e o primeiro teste do arquivo.
        ("15h, 'saída' às 14:33 que é a volta do almoço — NÃO fecha",
         _em(15, 0), {MY: {"fim": "17:45", "saida": "14:33"}}, UM, 0),
        ("saiu no horário e deixou o cartão aberto — 18h ainda não fecha",
         _em(18, 0), {MY: {"fim": "17:45", "saida": "17:45"}}, UM, 0),
        ("o mesmo cartão, às 19h",
         _em(19, 0), {MY: {"fim": "17:45", "saida": "17:45"}}, UM, 1),
        ("18:59 é antes do piso",
         _em(18, 59), {MY: {"fim": "17:45", "saida": "17:45"}}, UM, 0),
        ("foi embora às 15:20 de verdade — só fecha às 19h",
         _em(15, 30), {MY: {"fim": "17:45", "saida": "15:20"}}, UM, 0),
        ("a mesma pessoa, depois do piso",
         _em(19, 30), {MY: {"fim": "17:45", "saida": "15:20"}}, UM, 1),
        # ── O resto da regra, já com o piso valendo ───────────────────────────
        ("um minuto antes da saída registrada",
         _em(19, 44), {MY: {"fim": "19:45", "saida": "19:45"}}, UM, 0),
        ("sem batida, meia hora depois do fim — ainda espera",
         _em(19, 30), {MY: {"fim": "19:15", "saida": None}}, UM, 0),
        ("sem batida, uma hora depois do fim",
         _em(19, 16), {MY: {"fim": "18:15", "saida": None}}, UM, 1),
        ("meio do expediente, sem batida",
         _em(11, 0), {MY: {"fim": "17:45", "saida": None}}, UM, 0),
        ("cartão de dupla, só uma encerrou",
         _em(19, 0), {MY: {"fim": "17:45", "saida": "17:45"},
                      BIA: {"fim": "23:00", "saida": None}}, DOIS, 0),
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

    # ── diagnosticar: por que cada cartao aberto NAO fechou ────────────────
    #
    # `ok` acima e um bool do laco de CASOS, nao uma funcao: daqui para baixo
    # a conferencia tem a sua propria.
    def _ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    _ag = _em(20, 0)
    # bia sai 20:30 e ainda nao bateu: as 20h ela esta MESMO trabalhando. Com
    # fim 18:00 a espera de 60 min ja teria vencido e o cartao dela fecharia —
    # o caso "aguardando" nao existiria para ser conferido.
    _p = {"ana": {"fim": "18:00", "saida": "18:05"},
          "bia": {"fim": "20:30", "saida": None},
          "caio": {"fim": None, "saida": None}}

    def _porques(cartoes, agora=_ag, pessoas=_p):
        return {c["nome"]: c["porque"]
                for c in diagnosticar(agora, pessoas, cartoes)}

    _r = _porques([
        {"id": "1", "nome": "sem ninguem", "membros": []},
        {"id": "2", "nome": "so ana", "membros": ["ana"]},
        {"id": "3", "nome": "so bia", "membros": ["bia"]},
        {"id": "4", "nome": "so caio", "membros": ["caio"]},
        {"id": "5", "nome": "ana e bia", "membros": ["ana", "bia"]},
    ])
    _ok("cartao sem membro e reportado, e nao ignorado",
       _r.get("sem ninguem") == "sem_membro")
    _ok("cartao que FECHA nao aparece no diagnostico", "so ana" not in _r)
    _ok("quem ainda esta no expediente sai como aguardando",
       _r.get("so bia") == "aguardando")
    _ok("pessoa sem horario na RHiD tem porta propria",
       _r.get("so caio") == "sem_horario")
    _ok("cartao de dois so fecha quando os DOIS encerram",
       _r.get("ana e bia") == "aguardando")

    # Antes das 19h nada fecha, e o diagnostico diz isso em vez de mentir que
    # o cartao esta preso por outro motivo.
    _cedo = _porques([{"id": "9", "nome": "x", "membros": ["ana"]}],
                     agora=_em(15, 0))
    _ok("antes das 19h o motivo e a hora, nao a pessoa",
       _cedo.get("x") == "antes_das_19h")

    _ok("lista vazia nao derruba", diagnosticar(_ag, _p, []) == [])
    _ok("cartoes None nao derruba", diagnosticar(_ag, _p, None) == [])
    _ok("pessoas None nao derruba",
       diagnosticar(_ag, None, [{"id": "1", "nome": "y",
                                 "membros": ["ana"]}])[0]["porque"] == "sem_ponto")
    _ok("quem a RHiD nao conhece tem porta propria, e nao vira aguardando",
       _porques([{"id": "7", "nome": "z", "membros": ["brumielly"]}])
       .get("z") == "sem_ponto")
    _ok("um membro desconhecido ja segura o cartao inteiro",
       _porques([{"id": "8", "nome": "w",
                  "membros": ["ana", "brumielly"]}]).get("w") == "sem_ponto")
    _ok("sem_membro vem antes de aguardando na lista",
       [c["porque"] for c in diagnosticar(_ag, _p, [
           {"id": "3", "nome": "b", "membros": ["bia"]},
           {"id": "1", "nome": "a", "membros": []}])] ==
       ["sem_membro", "aguardando"])

    print("\nfalhas:", falhas)
