"""batidas.py — a janela de trabalho sai do relógio de ponto, não do contrato.

O QUE ESTE MÓDULO RESOLVE
-------------------------
O relógio do cartão só corre dentro das janelas de expediente, e até aqui essas
janelas eram o horário CONTRATUAL: 09:00–13:30 e 14:30–18:00 para todo mundo
(`placar_core.py:447`). Na prática ninguém almoça no horário do contrato — sai
13h05, volta 14h20 — e a diferença ia inteira para a conta da pessoa: o cartão
continuava contando enquanto ela almoçava, e parava enquanto ela trabalhava.

Aqui a janela vira o que o relógio registrou: entrada → saída para o almoço,
volta do almoço → saída. O tempo entre a saída e a volta simplesmente não
existe para o cartão, para o atraso nem para a ociosidade — os três partem das
mesmas janelas, então um conserto só arruma os três.

AS TRÊS DECISÕES, E POR QUE CADA UMA
------------------------------------
1. **Quem não bate ponto continua no contrato.** Gestor não tem batida; sem
   janela nenhuma o cartão dele pararia de contar para sempre.

2. **Quem entrou e ainda não saiu conta ATÉ AGORA.** A pessoa está trabalhando
   neste minuto. Fechar a janela no fim do expediente contratual daria tempo
   que ela ainda não trabalhou; fechar na última batida daria zero.
   Em dia PASSADO sem batida de saída, a janela fecha no fim do contrato — dia
   velho com janela aberta acumularia a madrugada inteira.

3. **RHiD fora do ar volta para o contrato.** Número aproximado é melhor que
   tela vazia. Uma falha de rede não pode zerar a produção do time — e zerar
   é o que aconteceria se "sem batida" virasse "sem janela".

O CUSTO, QUE É O QUE QUASE QUEBROU ISTO
---------------------------------------
`_janelas_uteis` roda POR CARTÃO E POR MEMBRO, varrendo até 60 dias por
chamada. Consultar a RHiD lá dentro daria dezenas de milhares de chamadas por
rodada — foi exatamente o que já aconteceu com os abonos, e a saída foi a
mesma: ler tudo UMA vez e servir de um mapa em memória (`placar_core.py:1276`).

Por isso `mapa()` guarda o resultado por TTL e a leitura da RHida acontece uma
vez por rodada, não uma por cartão.
"""

from datetime import datetime, timedelta

# Cinco minutos: o mesmo fôlego do cache de mês do Bling. Batida nova aparece
# na próxima leitura, e ninguém fica olhando o relógio esperando o painel.
TTL_SEG = 300

# Quantos dias para trás a leitura cobre. O intervalo do cartão pode ir a 60
# dias (MAX_DIAS_INTERVALO), mas puxar 60 dias de ponto de todo mundo a cada
# rodada é caro e quase nunca usado: cartão parado há dois meses é caso raro, e
# nesses dias o contrato responde. 31 cobre o mês corrente inteiro.
DIAS_PARA_TRAS = 31

_CACHE = {"ts": 0.0, "chave": None, "dados": {}}


def _hm(texto):
    """'08:59' -> (8, 59). None quando não dá para ler."""
    t = str(texto or "").strip()
    if not t or ":" not in t:
        return None
    try:
        h, m = t.split(":")[:2]
        h, m = int(h), int(m)
    except (TypeError, ValueError):
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return (h, m)


def janelas_do_dia(marc, dia, fuso, agora=None, fim_contrato=None):
    """As janelas reais daquele dia. [] quando não há batida nenhuma.

    `marc` é o registro normalizado da RHiD: entrada, saida_almoco,
    volta_almoco, saida — qualquer um deles pode faltar.

    Devolve [] (e não uma janela vazia) quando não há batida: quem chama
    precisa distinguir "não trabalhou" de "não sei", e cai no contrato.
    """
    if not marc:
        return []
    pontos = {k: _hm(marc.get(k)) for k in
              ("entrada", "saida_almoco", "volta_almoco", "saida")}
    if not pontos["entrada"]:
        # Sem entrada não há jornada. Uma saída solta é registro torto, e
        # inventar a entrada daria tempo que ninguém trabalhou.
        return []

    def _dt(hm):
        return datetime(dia.year, dia.month, dia.day, hm[0], hm[1], tzinfo=fuso)

    # O fecho de uma janela aberta: hoje é agora (a pessoa está trabalhando);
    # em dia passado é o fim do contrato, senão a madrugada entraria na conta.
    eh_hoje = agora is not None and agora.date() == dia
    if eh_hoje:
        limite = agora
    elif fim_contrato:
        limite = _dt((fim_contrato.hour, fim_contrato.minute))
    else:
        limite = _dt((23, 59))

    ent = _dt(pontos["entrada"])
    saiu = _dt(pontos["saida_almoco"]) if pontos["saida_almoco"] else None
    voltou = _dt(pontos["volta_almoco"]) if pontos["volta_almoco"] else None
    fim = _dt(pontos["saida"]) if pontos["saida"] else None

    janelas = []
    if saiu:
        # Manhã: entrada até a saída para o almoço.
        if saiu > ent:
            janelas.append((ent, saiu))
        if voltou:
            # Tarde: volta do almoço até a saída (ou até o limite, se ainda
            # não saiu). É AQUI que o almoço real fica de fora — o buraco
            # entre `saiu` e `voltou` não vira janela nenhuma.
            fecho = fim if (fim and fim > voltou) else limite
            if fecho > voltou:
                janelas.append((voltou, fecho))
        # Saiu para o almoço e ainda não voltou: a tarde não começou. Nada a
        # acrescentar — e é exatamente o caso do time que foi almoçar agora.
    else:
        # Dia direto, sem intervalo registrado.
        fecho = fim if (fim and fim > ent) else limite
        if fecho > ent:
            janelas.append((ent, fecho))
    return janelas


def _persons_por_username():
    """{username_trello: id_person}. Vazio em qualquer falha."""
    try:
        import rhid_api as _rhid
        import placar_core as _pc
    except Exception:
        return {}
    try:
        persons = _rhid.get_persons()
    except Exception:
        return {}
    fora = {}
    for p in (persons or []):
        nome = (p.get("name") or p.get("nome") or p.get("nomeCompleto")
                or p.get("fullName") or p.get("personName") or "")
        idp = (p.get("id") or p.get("idPerson") or p.get("personId")
               or p.get("codigo"))
        if not nome or not idp:
            continue
        chave = nome.lower().split()[0]
        user = _pc.MAPA_RHID.get(chave)
        if user:
            fora[user] = int(idp)
    return fora


def mapa(hoje=None, forcar=False):
    """{username: {date: marcacoes}} do mês corrente. {} em qualquer falha.

    Uma leitura por rodada, não uma por cartão. Falha nunca sobe: sem mapa,
    quem chama volta para o horário contratual.
    """
    import time as _t
    from datetime import date as _date
    hoje = hoje or _date.today()
    chave = hoje.isoformat()
    agora_ts = _t.time()
    if (not forcar and _CACHE["chave"] == chave
            and (agora_ts - _CACHE["ts"]) < TTL_SEG):
        return _CACHE["dados"]

    dados = {}
    try:
        import rhid_api as _rhid
        ini = (hoje - timedelta(days=DIAS_PARA_TRAS)).isoformat()
        fim = hoje.isoformat()
        for user, idp in _persons_por_username().items():
            regs, _d = _rhid.get_registros_diarios(ini, fim, idp)
            por_dia = {}
            for r in (regs or []):
                d = r.get("data")
                if d:
                    por_dia[d] = r
            if por_dia:
                dados[user] = por_dia
    except Exception:
        dados = {}

    _CACHE.update({"ts": agora_ts, "chave": chave, "dados": dados})
    return dados


def limpar():
    """Esquece o que foi lido. Para a tela que acabou de corrigir uma batida."""
    _CACHE.update({"ts": 0.0, "chave": None, "dados": {}})


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from datetime import date, time, timezone
    FUSO = timezone(timedelta(hours=-3))
    DIA = date(2026, 9, 15)
    FIM_CONTRATO = time(18, 0)
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    def hm(j):
        return [(f"{a:%H:%M}", f"{b:%H:%M}") for a, b in j]

    ok("hora ilegível não derruba", _hm("banana") is None and _hm("") is None)
    ok("hora fora do relógio é recusada",
       _hm("25:00") is None and _hm("08:70") is None)
    ok("hora boa é lida", _hm("08:59") == (8, 59))

    DIA_CHEIO = {"entrada": "08:57", "saida_almoco": "13:05",
                 "volta_almoco": "14:22", "saida": "18:03"}
    ok("dia completo vira duas janelas, e o almoço REAL fica de fora",
       hm(janelas_do_dia(DIA_CHEIO, DIA, FUSO, fim_contrato=FIM_CONTRATO))
       == [("08:57", "13:05"), ("14:22", "18:03")])

    # O caso do dia: foram almoçar e o cartão ficou EM ANDAMENTO.
    ALMOCANDO = {"entrada": "08:57", "saida_almoco": "13:05",
                 "volta_almoco": None, "saida": None}
    _agora = datetime(2026, 9, 15, 13, 40, tzinfo=FUSO)
    ok("quem saiu para almoçar e não voltou para de contar na saída",
       hm(janelas_do_dia(ALMOCANDO, DIA, FUSO, agora=_agora,
                         fim_contrato=FIM_CONTRATO)) == [("08:57", "13:05")])

    TRABALHANDO = {"entrada": "08:57", "saida_almoco": "13:05",
                   "volta_almoco": "14:22", "saida": None}
    _agora2 = datetime(2026, 9, 15, 16, 10, tzinfo=FUSO)
    ok("quem voltou e ainda não saiu conta até AGORA",
       hm(janelas_do_dia(TRABALHANDO, DIA, FUSO, agora=_agora2,
                         fim_contrato=FIM_CONTRATO))
       == [("08:57", "13:05"), ("14:22", "16:10")])

    ok("dia PASSADO sem batida de saída fecha no fim do contrato, "
       "não na madrugada",
       hm(janelas_do_dia(TRABALHANDO, DIA, FUSO, agora=None,
                         fim_contrato=FIM_CONTRATO))
       == [("08:57", "13:05"), ("14:22", "18:00")])

    SEM_INTERVALO = {"entrada": "09:02", "saida_almoco": None,
                     "volta_almoco": None, "saida": "17:40"}
    ok("dia direto, sem intervalo registrado, vira uma janela só",
       hm(janelas_do_dia(SEM_INTERVALO, DIA, FUSO, fim_contrato=FIM_CONTRATO))
       == [("09:02", "17:40")])

    # Vazio e nao janela vazia: quem chama precisa distinguir "nao trabalhou"
    # de "nao sei", e so assim ele cai no contrato.
    ok("sem batida nenhuma devolve vazio", janelas_do_dia({}, DIA, FUSO) == [])
    ok("registro None devolve vazio", janelas_do_dia(None, DIA, FUSO) == [])
    ok("saída solta, sem entrada, devolve vazio",
       janelas_do_dia({"saida": "18:00"}, DIA, FUSO) == [])
    ok("batida ilegível cai no mesmo caminho do vazio",
       janelas_do_dia({"entrada": "--:--"}, DIA, FUSO) == [])
    ok("saída ANTES da entrada não vira janela negativa",
       janelas_do_dia({"entrada": "18:00", "saida": "08:00"}, DIA, FUSO,
                      fim_contrato=FIM_CONTRATO) == [])

    # O tempo do almoco nunca entra: e o que o gestor pediu.
    _j = janelas_do_dia(DIA_CHEIO, DIA, FUSO, fim_contrato=FIM_CONTRATO)
    _min = sum((b - a).total_seconds() / 60 for a, b in _j)
    # 08:57->13:05 = 248 min; 14:22->18:03 = 221 min. O buraco de 1h17 entre
    # 13:05 e 14:22 nao aparece em lugar nenhum — que e o ponto de tudo isto.
    ok("o intervalo real de 1h17 sai da conta (7h49 de janela)",
       abs(_min - 469) < 0.5)

    ok("limpar() zera o cache", (limpar() or True) and _CACHE["chave"] is None)

    print("\nfalhas:", falhas)
