"""alertas_trello.py — os dois avisos do instante, no Trello (dono, 23/10).

    "Ociosidade detectada e sendo contabilizada!!!"
    "Você está em duas demandas ao mesmo tempo" (a coluna Desativar não conta)

No Studio os dois já aparecem na tela "Meu desempenho" (`meu_desempenho`).
Aqui eles chegam ONDE A PESSOA ESTÁ: um comentário no Trello marcando @ela, e
o app do Trello manda a notificação no celular.

ONDE COMENTA
------------
- Duas demandas: no próprio cartão, que é onde está o problema.
- Ociosidade: a pessoa não tem cartão rodando — é essa a ociosidade —, então
  não há cartão dela onde avisar. O aviso vai num cartão fixo do quadro cujo
  nome tem "ALERTAS" (o dono cria uma vez). Sem ele, este aviso é pulado e o
  log diz por quê.

QUANDO
------
Roda junto com a rotina do fim de expediente (`fechar_expediente.py`), a cada
vez que ela roda. A ociosidade só avisa depois de `ESPERA_MIN` seguidos sem
cartão — a mesma folga que a conta da ociosidade dá entre um cartão e o
seguinte (`placar_core.GRACA_ENTRE_MIN`) — e uma vez só por episódio. As duas
demandas avisam uma vez por par de cartões por dia. Sem isso o celular da
equipe tocaria a cada 5 minutos.

Escreve no board real, então tem as travas do fechar_expediente: só produção
e `--simular` para ver sem aplicar.
"""
import json
from datetime import datetime, timedelta

ABA_ESTADO = "alertas_trello"
NOME_CARTAO = "ALERTAS"
TIMEOUT_TRELLO = (10, 30)


def espera_min():
    import placar_core as _pc
    return int(getattr(_pc, "GRACA_ENTRE_MIN", 5))


# ── A decisão (pura) ─────────────────────────────────────────────────────────
def decidir(agora, rodando, no_exp, estado, espera=5):
    """O que avisar agora. Pura.

    rodando  {username: [(nome, coluna, id)]} dos cartões EM ANDAMENTO.
    no_exp   {username: bool} — dentro do expediente batido agora.
    estado   {username: {"ocioso_desde", "avisou_ocio", "duas"}} da rodada passada.

    Devolve ([{"tipo", "usuario", "card_id"|None, "texto"}], estado_novo).
    """
    import meu_desempenho as _md
    acoes, novo = [], {}
    dia = agora.strftime("%Y-%m-%d")
    for u in sorted(set(rodando) | set(no_exp)):
        e = dict(estado.get(u) or {})
        rod = rodando.get(u) or []
        duas = _md.demandas_simultaneas(rod)
        if len(duas) >= 2:
            chave = dia + "|" + "|".join(sorted(x[2] for x in duas))
            if e.get("duas") != chave:
                acoes.append({
                    "tipo": "duas", "usuario": u, "card_id": duas[0][2],
                    "texto": (f"🟡 @{u} você está em {len(duas)} demandas ao mesmo tempo: "
                              + " · ".join(f"“{x[0][:60]}”" for x in duas)
                              + ". Ponha INTERROMPIDO numa delas antes de seguir "
                                "(cartões na coluna Desativar não contam).")})
                e["duas"] = chave
        if no_exp.get(u) and not rod:
            desde = e.get("ocioso_desde")
            if not desde:
                e["ocioso_desde"] = agora.isoformat()
            elif (not e.get("avisou_ocio")
                  and agora - datetime.fromisoformat(desde) >= timedelta(minutes=espera)):
                _min = int((agora - datetime.fromisoformat(desde)).total_seconds() // 60)
                acoes.append({
                    "tipo": "ocio", "usuario": u, "card_id": None,
                    "texto": (f"⚠️ @{u} Ociosidade detectada e sendo contabilizada!!! "
                              f"Nenhum cartão seu está EM ANDAMENTO há {_min} min.")})
                e["avisou_ocio"] = True
        else:
            # Voltou a trabalhar, ou saiu do expediente: o episódio acabou.
            e.pop("ocioso_desde", None)
            e.pop("avisou_ocio", None)
        novo[u] = e
    return acoes, novo


def cartao_de_alertas(cards):
    """O id do cartão fixo de avisos (nome com "ALERTAS"). '' sem ele. Pura."""
    for c in cards or []:
        if NOME_CARTAO in (c.get("name") or "").upper():
            return c.get("id", "")
    return ""


# ── O mundo (rede e planilha) ────────────────────────────────────────────────
def _aba():
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        return planilha.worksheet(ABA_ESTADO)
    except Exception:
        return planilha.add_worksheet(title=ABA_ESTADO, rows=2, cols=1)


def _ler_estado():
    try:
        return json.loads(_aba().acell("A1").value or "{}")
    except Exception:
        return {}


def _gravar_estado(estado):
    try:
        _aba().update_acell("A1", json.dumps(estado, ensure_ascii=False))
    except Exception:
        pass


def _comentar(card_id, texto):
    import requests
    import placar_core as _pc
    try:
        r = requests.post(f"https://api.trello.com/1/cards/{card_id}/actions/comments",
                          params={"key": _pc.TRELLO_KEY, "token": _pc.TRELLO_TOKEN,
                                  "text": texto}, timeout=TIMEOUT_TRELLO)
        return r.ok, ("" if r.ok else f"HTTP {r.status_code}")
    except Exception as e:
        return False, str(e)[:140]


def main(simular=False, agora=None, log=print):
    """Uma rodada. Devolve quantos avisos saíram. Quem chama já preparou o
    secrets e conferiu que é produção (`fechar_expediente.main`)."""
    import placar_core as _pc
    import batidas as _bat
    import meu_desempenho as _md
    agora = agora or datetime.now(_pc.FUSO)
    if not _pc.eh_dia_util(agora.date()):
        return 0
    listas, cards, membros_map, *_ = _pc._buscar_board()
    if not cards:
        log("Alertas: o board não respondeu.")
        return 0
    mapa = _bat.mapa() or {}
    rodando, no_exp = {}, {}
    for u in _pc.MEMBROS_ATIVOS:
        rodando[u] = _md.cartoes_rodando(u, listas, cards, membros_map, com_id=True)
        try:
            jan = _bat.janelas_do_dia((mapa.get(u) or {}).get(agora.date()),
                                      agora.date(), _pc.FUSO, agora=agora,
                                      fim_contrato=_pc.horario_de(u)["fim"])
        except Exception:
            jan = []
        no_exp[u] = _md.no_expediente(jan, agora)
    acoes, estado = decidir(agora, rodando, no_exp, _ler_estado(), espera_min())
    fixo = cartao_de_alertas(cards)
    feitos = 0
    for a in acoes:
        alvo = a["card_id"] or fixo
        if not alvo:
            log(f"Alertas: ociosidade de {a['usuario']} sem aviso — crie no "
                f"quadro um cartão com '{NOME_CARTAO}' no nome.")
            continue
        if simular:
            log(f"  [simulado] {a['texto']}")
            continue
        ok, det = _comentar(alvo, a["texto"])
        feitos += ok
        log(("  avisado: " if ok else "  FALHOU: ") + a["texto"][:90] + (f" · {det}" if det else ""))
    if not simular:
        _gravar_estado(estado)
    return feitos


if __name__ == "__main__":
    import placar_core as _pc_t
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    _t = lambda h, m: datetime(2026, 10, 27, h, m, tzinfo=_pc_t.FUSO)
    A, B, D = ("Caneca", "PRODUÇÃO", "c1"), ("Porta", "PRODUÇÃO", "c2"), ("Conferir", "DESATIVAR", "c3")

    _a, _e = decidir(_t(10, 0), {"bia": [A, B]}, {"bia": True}, {})
    ok("duas demandas: avisa no próprio cartão, marcando a pessoa",
       [(x["tipo"], x["card_id"]) for x in _a] == [("duas", "c1")] and "@bia" in _a[0]["texto"])
    _a2, _ = decidir(_t(10, 5), {"bia": [A, B]}, {"bia": True}, _e)
    ok("duas demandas: o mesmo par não avisa de novo no dia", _a2 == [])
    ok("duas demandas: Desativar não conta",
       decidir(_t(10, 0), {"bia": [A, D]}, {"bia": True}, {})[0] == [])

    _a, _e = decidir(_t(10, 0), {"bia": []}, {"bia": True}, {})
    ok("ociosidade: a primeira rodada sem cartão só marca o início", _a == [] and _e["bia"]["ocioso_desde"])
    _a, _e = decidir(_t(10, 3), {"bia": []}, {"bia": True}, _e)
    ok("ociosidade: antes da folga de 5 min não avisa", _a == [])
    _a, _e = decidir(_t(10, 6), {"bia": []}, {"bia": True}, _e)
    ok("ociosidade: passou a folga, avisa uma vez com a frase do dono",
       len(_a) == 1 and "Ociosidade detectada e sendo contabilizada!!!" in _a[0]["texto"]
       and _a[0]["card_id"] is None)
    _a, _e = decidir(_t(10, 20), {"bia": []}, {"bia": True}, _e)
    ok("ociosidade: o mesmo episódio não avisa de novo", _a == [])
    _a, _e = decidir(_t(10, 25), {"bia": [A]}, {"bia": True}, _e)
    ok("ociosidade: voltou a trabalhar, o episódio fecha", "ocioso_desde" not in _e["bia"])
    ok("ociosidade: fora do expediente (almoço, depois da saída) não avisa",
       decidir(_t(12, 30), {"bia": []}, {"bia": False}, {"bia": {"ocioso_desde": _t(12, 0).isoformat()}})[0] == [])
    ok("cartão fixo: acha pelo nome com ALERTAS",
       cartao_de_alertas([{"id": "x", "name": "Caneca"}, {"id": "z", "name": "⚠️ Alertas da equipe"}]) == "z")
    ok("a folga é a mesma da conta da ociosidade", espera_min() == _pc_t.GRACA_ENTRE_MIN)
    print("\nfalhas:", falhas)
    raise SystemExit(1 if falhas else 0)
