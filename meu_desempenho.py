"""meu_desempenho.py — a primeira tela de quem entra no Studio (dono, 24/10).

O QUE ELA RESPONDE
------------------
"Como eu estou no mês, o que está puxando a minha meta para baixo, e o que
isso custa ao time?" — sem a pessoa ter de abrir a Análise de Metas, escolher
a aba Individual e rolar.

NENHUM NÚMERO NOVO
------------------
Tudo sai das MESMAS funções da Análise de Metas: `apuracao_bonus` (os
critérios que decidem o bônus), `_elegibilidade` (a porta da meta coletiva) e
`_pontualidade_do_periodo` (ponto, ociosidade e o ponto pendente). Uma conta
própria aqui seria a Forma 5: duas respostas para a mesma pergunta, e a tela
de entrada dizendo "bateu" enquanto a Análise diz "não bateu".

O QUE CUSTA
-----------
A apuração do mês é a mesma da Análise de Metas aberta em "Dentro do mês". Ela
roda UMA vez para o time inteiro a cada 5 minutos (`resumo_do_mes`, com
cache) — e não uma vez por pessoa, nem a cada tecla. O que é do instante
(cartão rodando agora, duas demandas) lê o board, que já tem cache próprio.
"""
from datetime import timedelta

import streamlit as st

import placar_core as _pc

# A coluna onde o segundo colaborador confere o que o primeiro desativou: ele
# está no cartão, mas a demanda já não é dele (dono, 23/10).
COLUNA_LIVRE = "DESATIVAR"


# ── A apuração (pura, testável) ──────────────────────────────────────────────
def resumo_da_pessoa(u, dados, bonus, pont, hoje):
    """O painel de uma pessoa, a partir da apuração já feita. Puro."""
    import analise_metas as _am
    import explicacao_metas as _expl
    r = dados[-1]
    b = bonus.get(u) or {}
    el = b.get("el") or {}
    sit = b.get("sit_pen") or {}
    pts = float(r.get("pts_membro", {}).get(u, 0) or 0)
    meta = float(r.get("cfg", {}).get(f"meta_{u}", 1500) or 0)
    uteis, dec = _am._dias_uteis_periodo(dados, hoje)
    proj = pts / dec * uteis if dec else 0.0
    crit = b.get("crit_n") or []
    contra = [rot for rot, ok in crit if ok is False]
    medidos_ok = [rot for rot, ok in crit if ok is True]
    # O que a metade individual pagaria com os critérios em dia: a metade do
    # time não depende só dela, e por isso fica como está hoje.
    pot_time, pot_seu = _expl.bonus_percentuais(b.get("col"), b.get("maxx"),
                                                True, False)
    return {
        "pts": pts, "meta": meta, "projecao": proj,
        "pct": (pts / meta * 100) if meta else 0.0,
        "pct_esperado": (dec / uteis * 100) if uteis else 0.0,
        "uteis": uteis, "decorridos": dec,
        "contra": contra, "em_dia": medidos_ok,
        "entra_col": bool(el.get("entra_col")),
        "motivos_col": list(el.get("motivos_col") or []),
        "time": {"saldo": float(r.get("saldo", 0) or 0),
                 "meta": float(r.get("meta_eq", 0) or 0),
                 "bateu": bool(sit.get("bateu_col"))},
        "bonus_hoje": (b.get("pct_time", 0.0), b.get("pct_seu", 0.0)),
        "bonus_em_dia": (pot_time, pot_seu),
        "pendencias": list((pont.get(u) or {}).get("pend") or []),
    }


@st.cache_data(ttl=300, show_spinner=False)
def resumo_do_mes(ano, mes):
    """{username: resumo} do mês, para o time inteiro. Uma apuração por 5 min."""
    import analise_metas as _am
    listas, cards, membros_map, id_p, id_t, id_i = _pc._buscar_board()
    if not listas:
        return {}
    dados = _am._analisar_meses(listas, cards, membros_map, id_p, id_t, id_i,
                                [(ano, mes)], _pc._processar)
    if not dados:
        return {}
    membros = list(_pc.MEMBROS_ATIVOS)
    pont, ocio, tem_ponto, _d, _e = _am._pontualidade_do_periodo(dados, membros)
    medias = _am._media_execucao_por_membro(dados) or {}
    bonus = _am.apuracao_bonus(dados, membros, pont, ocio, tem_ponto, medias)
    hoje = _pc.agora_br()
    fora = {u: resumo_da_pessoa(u, dados, bonus, pont, hoje) for u in membros}
    # O MÊS EM DINHEIRO (dono, 30/10): salário pelo ponto e metas, da MESMA
    # apuração — a aba do dono (`folha_tela`) lê daqui também.
    # O SALÁRIO É DO PERÍODO (30→29), as metas do mês: a RHiD é lida de novo
    # no intervalo da folha, uma semana antes do início (é de lá que sai o
    # banco anterior). Cache de 5 min, como o resto desta apuração.
    try:
        import folha_mes as _fm
        import relogio_ponto as _rp
        from datetime import timedelta as _td
        _ini, _fim = _fm.periodo(ano, mes)
        _ponto, _dp = _rp.get_ponto_do_periodo(_ini - _td(days=7), _fim)
        if _dp.get("erro") and not _ponto:
            raise RuntimeError(f"RHiD: {_dp['erro']}")
        for u, f in _fm.do_mes(ano, mes, dados, _ponto, bonus, hoje).items():
            if u in fora:
                fora[u]["dinheiro"] = f
                # O ponto pendente do PERÍODO da folha, que pode começar no
                # dia 30 do mês anterior — o do mês do calendário não vê.
                if f:
                    fora[u]["pendencias"] = list(f["pendencias"])
    except Exception as e:
        for u in fora:
            fora[u]["dinheiro_erro"] = str(e)[:160]
    return fora


# ── O instante (puro, testável) ──────────────────────────────────────────────
def cartoes_rodando(u, listas, cards, membros_map, com_id=False):
    """[(nome, coluna)] dos cartões EM ANDAMENTO desta pessoa agora. Puro.

    `com_id`: (nome, coluna, id) — o aviso no Trello precisa saber em que
    cartão comentar (`alertas_trello`).

    Rodando é o que o relógio conta: etiqueta de trabalho e nenhuma de
    interrupção (`placar_core._trabalhando`).
    """
    fora = []
    for c in cards or []:
        if u not in [membros_map.get(m) for m in (c.get("idMembers") or [])]:
            continue
        nomes = {(lb.get("name") or "").upper().strip()
                 for lb in (c.get("labels") or [])}
        if nomes & _pc.LABELS_TRABALHO and not (nomes & _pc.LABELS_INTERRUPCAO):
            fora.append((c.get("name", ""), listas.get(c.get("idList"), ""))
                        + ((c.get("id", ""),) if com_id else ()))
    return fora


def demandas_simultaneas(rodando):
    """Os cartões que contam para "duas demandas ao mesmo tempo". Puro.

    A coluna Desativar fica de fora: ali a pessoa confere o que o colega
    desativou, e a demanda já não é dela (dono, 23/10).
    """
    return [x for x in rodando
            if COLUNA_LIVRE not in (x[1] or "").upper()]


def no_expediente(janelas, agora):
    """A pessoa está dentro do expediente batido agora? Puro.

    Janela aberta (sem saída) termina em `agora` (`batidas.janelas_do_dia`);
    um minuto de folga cobre o relógio que andou entre as duas leituras.
    """
    return any(a <= agora <= b + timedelta(minutes=1) for a, b in janelas or [])


# ── A tela ───────────────────────────────────────────────────────────────────
def _hm(minutos):
    m = int(round(minutos or 0))
    return f"{m // 60}h{m % 60:02d}"


def _n(v):
    return f"{v:,.0f}".replace(",", ".")


def _alertas_do_instante(u):
    """Os dois avisos do agora: ociosidade correndo e duas demandas."""
    try:
        listas, cards, membros_map, *_ = _pc._buscar_board()
    except Exception:
        return
    rodando = cartoes_rodando(u, listas, cards, membros_map)
    duas = demandas_simultaneas(rodando)
    if len(duas) >= 2:
        st.warning(
            f"🟡 **Você está em {len(duas)} demandas ao mesmo tempo:** "
            + " · ".join(f"“{n[:50]}”" for n, _c in duas)
            + ". Ponha INTERROMPIDO numa delas antes de seguir — cartões na "
              "coluna Desativar não contam.")
    if rodando:
        return
    try:
        import batidas as _bat
        from datetime import datetime as _dt
        # COM fuso: as janelas de `batidas` vêm com fuso, e `agora_br()` é
        # ingênua — compará-las estoura (e o aviso sumia em silêncio).
        agora = _dt.now(_pc.FUSO)
        reg = (_bat.mapa() or {}).get(u, {}).get(agora.date())
        jan = _bat.janelas_do_dia(reg, agora.date(), _pc.FUSO, agora=agora,
                                  fim_contrato=_pc.horario_de(u)["fim"])
    except Exception:
        return
    if no_expediente(jan, agora):
        st.error("⚠️ **Ociosidade detectada e sendo contabilizada!!!** "
                 "Nenhum cartão seu está EM ANDAMENTO agora.")


def aparece_para(usuario_logado):
    """Quem ganha a aba: quem é da equipe medida, com qualquer perfil.

    Uma pergunta só para as duas barras do `app.py` (colaborador e admin): o
    Luiz tem perfil admin e ficou sem a tela porque ela morava só na outra."""
    return _pc.username_do_login(usuario_logado) in _pc.MEMBROS_ATIVOS


def prazo_do_ajuste(hoje):
    """Último dia para ajustar o ponto: o fim do período ABERTO — a véspera do
    pagamento (dia 29 quando o salário cai no 30). O período é um só, o de
    `folha_mes.periodo`: o aviso e o salário não podem discordar. Pura."""
    import folha_mes as _fm
    return _fm.periodo(*_fm.competencia(hoje))[1]


def pendencias_em_aberto(pendencias, hoje):
    """Só as pendências do período ABERTO: as de um período já fechado viraram
    desconto no holerite, e avisar delas com o prazo do mês seguinte seria
    mentir o prazo. Pura."""
    import folha_mes as _fm
    ini = _fm.periodo(*_fm.competencia(hoje))[0].isoformat()
    return [p for p in pendencias or [] if str(p.get("data", ""))[:10] >= ini]


def alerta_de_ponto(pendencias, hoje):
    """O aviso do topo do painel: None, ou {"critico", "titulo", "texto"}. Pura.

    Dono, 30/10: alertar o ajuste de ponto que falta, "mais crítico no dia 28
    e 29 por ser o último dia possível", e dizer que o que não for ajustado
    "constará como falta não remunerada ou uso do banco de horas
    automaticamente" — que é o que `folha_mes.apurar` faz com a hora que falta.
    """
    if not pendencias:
        return None
    prazo = prazo_do_ajuste(hoje)
    faltam = (prazo - hoje.date() if hasattr(hoje, "date") else prazo - hoje).days
    n = len(pendencias)
    qtd = f"{n} ajuste{'s' if n > 1 else ''} de ponto pendente{'s' if n > 1 else ''}"
    regra = (f"O que não for ajustado até {prazo:%d/%m} entra AUTOMATICAMENTE como uso do "
             "seu banco de horas e, sem banco, como falta não remunerada, descontada do "
             "salário.")
    if faltam <= 0:
        return {"critico": True, "titulo": f"🚨 HOJE É O ÚLTIMO DIA — {qtd}",
                "texto": regra}
    if faltam == 1:
        return {"critico": True, "titulo": f"🚨 AMANHÃ ({prazo:%d/%m}) É O ÚLTIMO DIA — {qtd}",
                "texto": regra}
    return {"critico": False, "titulo": f"⚠️ Você tem {qtd} · prazo {prazo:%d/%m}",
            "texto": regra}


def _alerta_de_ponto(pendencias, agora):
    a = alerta_de_ponto(pendencias, agora)
    if not a:
        return
    dias = ", ".join(f"{p['data'][8:10]}/{p['data'][5:7]}" for p in pendencias)
    corpo = f"### {a['titulo']}\n\nDias: **{dias}** — veja abaixo, em Ponto pendente.\n\n{a['texto']}"
    (st.error if a["critico"] else st.warning)(corpo)


def pagina(usuario_logado):
    u = _pc.username_do_login(usuario_logado)
    if not aparece_para(usuario_logado):
        st.info("Esta tela mostra o desempenho de quem está na equipe "
                "medida. Seu usuário não está nela.")
        return
    _alertas_do_instante(u)

    agora = _pc.agora_br()
    with st.spinner("Lendo o seu mês…"):
        try:
            res = (resumo_do_mes(agora.year, agora.month) or {}).get(u)
        except Exception as e:
            st.error(f"Não consegui montar o seu resumo: {str(e)[:160]}")
            return
    if not res:
        st.warning("Ainda não há dado do mês para mostrar.")
        return

    nome = _pc.MEMBROS_ATIVOS.get(u, u).split(" ")[0]
    st.markdown(f"## Olá, {nome} 👋")
    st.caption(f"Seu mês até agora · {res['decorridos']} de {res['uteis']} "
               "dias úteis · atualiza a cada 5 minutos")
    _pend_ab = pendencias_em_aberto(res["pendencias"], agora)
    _alerta_de_ponto(_pend_ab, agora)

    c1, c2 = st.columns([1.3, 1])
    with c1:
        st.markdown("#### 🎯 Minha meta individual")
        _falta = max(res["meta"] - res["projecao"], 0)
        st.markdown(
            f"**{_n(res['pts'])}** de {_n(res['meta'])} pts "
            f"({res['pct']:.0f}%) · deveria estar em {res['pct_esperado']:.0f}% hoje")
        st.progress(min(res["pct"] / 100, 1.0))
        st.caption(f"No ritmo atual: {_n(res['projecao'])} pts no fim do mês"
                   + (f" · faltariam {_n(_falta)}" if _falta else " · bate a meta"))
        if res["em_dia"]:
            st.markdown("✅ Em dia: " + " · ".join(res["em_dia"]))

        st.markdown("#### 👥 Meta coletiva")
        _t = res["time"]
        _pct_t = _t["saldo"] / _t["meta"] * 100 if _t["meta"] else 0
        st.markdown(f"**{_n(_t['saldo'])}** de {_n(_t['meta'])} pts ({_pct_t:.0f}%)"
                    + (" · ✅ batida" if _t["bateu"] else ""))
        st.progress(min(_pct_t / 100, 1.0))
        _bh, _be = sum(res["bonus_hoje"]), sum(res["bonus_em_dia"])
        st.markdown(f"Se o mês fechasse hoje, seu bônus: **{_bh:.0f}%**"
                    + (f" · com os seus critérios em dia: **{_be:.0f}%**"
                       if _be > _bh else ""))

    with c2:
        st.markdown("#### 🚨 O que está puxando sua meta para baixo")
        if not res["contra"] and res["entra_col"]:
            st.success("Nada: todos os critérios medidos estão em dia.")
        for rot in res["contra"]:
            st.error(f"**{rot[:1].upper() + rot[1:]}**")
        if not res["entra_col"]:
            st.error("**Fora da meta coletiva:** "
                     + "; ".join(res["motivos_col"] or ["abaixo do mínimo"])
                     + ". Mesmo que o time feche, a metade do time do bônus "
                       "não vem para você.")

        st.markdown("#### 🕘 Ponto pendente — resolva com o RH")
        _pend = _pend_ab
        if not _pend:
            st.caption("Nenhuma marcação faltando nos dias anteriores.")
        for p in _pend:
            _d = f"{p['data'][8:10]}/{p['data'][5:7]}"
            if p["tipo"] == "sem_batida":
                st.warning(f"**{_d}** · dia útil sem nenhuma batida e sem abono. "
                           "Se foi atestado ou outro motivo, envie a justificativa pelo "
                           "app da RHiD (Minhas solicitações) ou fale com o RH.")
            else:
                st.warning(f"**{_d}** · marcação faltando — batidas do dia: "
                           + ", ".join(p["batidas"]))

    _meu_mes_em_dinheiro(res)
    _meu_holerite(u, agora, res)


def _brl_md(v):
    """Real no formato brasileiro, com o $ escapado para o markdown."""
    s = f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return "R\\$ " + s


# A assinatura começa no período de outubro/2026: o que veio antes não teve
# holerite no Studio, e cobrar assinatura dele seria um aviso eterno.
INICIO_ASSINATURA = (2026, 10)


@st.cache_data(ttl=300, show_spinner=False)
def _assinaturas_guardadas(ano, mes):
    import holerite as _hl
    return _hl.assinaturas(ano, mes)


def holerite_a_assinar(hoje, assinados_ant, u):
    """(ano, mes) do holerite que a pessoa ainda precisa assinar, ou None.

    O do mês corrente quando o pagamento dele já chegou (dia 30); senão o do
    mês anterior, se ficou sem assinar. Pura."""
    import holerite as _hl
    d = hoje.date() if hasattr(hoje, "date") else hoje
    if _hl.pode_assinar(d.year, d.month, d):
        return d.year, d.month
    ant = (d.year - 1, 12) if d.month == 1 else (d.year, d.month - 1)
    if ant >= INICIO_ASSINATURA and u not in (assinados_ant or {}):
        return ant
    return None


def _meu_holerite(u, agora, res):
    """O holerite do colaborador, igual ao do dono, e o botão de assinar."""
    import holerite as _hl
    d = res.get("dinheiro")
    if not d:
        return
    nome = _pc.MEMBROS_ATIVOS.get(u, u)
    ano, mes = agora.year, agora.month
    ant = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
    try:
        ass_ant = _assinaturas_guardadas(*ant) if ant >= INICIO_ASSINATURA else {}
        ass_cur = _assinaturas_guardadas(ano, mes)
    except Exception as e:
        st.error(f"Não consegui ler as assinaturas da folha de ponto: {str(e)[:120]}")
        return
    alvo = holerite_a_assinar(agora, ass_ant, u)
    if alvo == ant:
        try:
            d_alvo = ((resumo_do_mes(*ant) or {}).get(u) or {}).get("dinheiro")
        except Exception:
            d_alvo = None
        if d_alvo:
            st.error(f"✍️ Falta assinar a folha de ponto de {ant[1]:02d}/{ant[0]}.")
            _bloco_holerite(u, nome, ant, d_alvo, None, True)
    st.markdown("---")
    _fechado = d["folha"]["fechado"]
    _bloco_holerite(u, nome, (ano, mes), d, ass_cur.get(u),
                    alvo == (ano, mes) and u not in ass_cur)
    if not _fechado:
        st.caption(f"Prévia do período aberto. A assinatura é liberada no dia "
                   f"{d['pagamento'][8:10]}/{d['pagamento'][5:7]}, depois do fechamento.")


def _bloco_holerite(u, nome, am, d, assinatura, pode):
    import holerite as _hl
    st.markdown("#### 🧾 Meu holerite")
    st.markdown(_hl.html(d, nome, assinatura), unsafe_allow_html=True)
    if not pode:
        return
    ini, fim = d["periodo"]
    if st.button(f"✍️ Conferi e assino a folha de ponto de {ini[8:10]}/{ini[5:7]} a "
                 f"{fim[8:10]}/{fim[5:7]}", type="primary", key=f"assinar_{am[0]}_{am[1]}"):
        try:
            _hl.assinar(am[0], am[1], u, nome, d)
        except Exception as e:
            st.error(f"Não consegui gravar a assinatura: {str(e)[:120]}")
            return
        _assinaturas_guardadas.clear()
        st.rerun()


def _meu_mes_em_dinheiro(res):
    """Salário pelo ponto, banco de horas e metas (dono, 30/10)."""
    import folha_mes as _fm
    import headcount as _hc
    d = res.get("dinheiro")
    st.markdown("---")
    st.markdown("#### 💰 Meu mês em dinheiro")
    if not d:
        st.caption("Seu salário ainda não está cadastrado na folha — fale com o RH."
                   if "dinheiro_erro" not in res else
                   f"Não consegui montar: {res['dinheiro_erro']}")
        return
    f = d["folha"]
    agora = _pc.agora_br()
    q = _hc.quinto_dia_util(agora.year, agora.month)
    st.caption("Pelo ponto da RHiD até ontem · horas devidas: "
               f"{_fm.h(d['devidas_min']).lstrip('+')} (8h por dia útil)")
    a, b, c = st.columns(3)
    with a.container(border=True):
        st.caption("SALÁRIO DO MÊS · PAGO DIA 30")
        st.markdown(f"### {_brl_md(f['salario_se_fechasse_hoje'])}")
        st.markdown(f"Base **{_brl_md(f['salario'])}**")
        if f["desconto"]:
            # Com a marca do domingo, o desconto pode existir sem banco
            # negativo: "0h00 no banco" seria mentira na tela dele.
            _partes = ([f"{_fm.h(-f['negativo_min'])} no banco"] if f["negativo_min"] else []) \
                + ([f"{f['semanas_falta']} domingo(s) de falta de dia inteiro"]
                   if f["semanas_falta"] else [])
            st.markdown(f":red[Se o mês fechasse hoje: − {_brl_md(f['desconto'])} "
                        f"({' e '.join(_partes)})]")
    with b.container(border=True):
        st.caption("BANCO DE HORAS")
        st.markdown(f"### {_fm.h(f['banco_final_min'])}")
        st.markdown(f"Este mês: {_fm.h(f['saldo_mes_min'])}"
                    + (f" · {_fm.h(f['usado_do_banco_min']).lstrip('+')} usadas do banco"
                       if f["usado_do_banco_min"] else ""))
        if f["banco_final_min"] < 0:
            st.error("⚠️ Banco negativo. Se o mês fechar assim, estas horas serão "
                     "descontadas do salário.")
    with c.container(border=True):
        st.caption(f"METAS · PAGAS NO 5º DIA ÚTIL ({q:%d/%m})" if q else "METAS · 5º DIA ÚTIL")
        st.markdown(f"### {_brl_md(d['metas_valor'])} · {d['pct_metas']:.0f}%")
        st.markdown("  \n".join(
            ("✅ " if bateu else "❌ ") + f"**{rot}** {pct:.0f}%"
            + (f" · {_brl_md(v)}" if pago else "")
            + (f" — {mot}" if mot else "")
            for rot, pct, v, bateu, mot, pago in d["metas"]))
    st.info(f"**Total previsto do mês: {_brl_md(f['salario_se_fechasse_hoje'] + d['metas_valor'])}** · "
            f"{_brl_md(f['salario_se_fechasse_hoje'])} no dia 30 + {_brl_md(d['metas_valor'])} "
            "no 5º dia útil")


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from datetime import datetime
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    _li = {"L1": "PRODUÇÃO", "L2": "DESATIVAR ANÚNCIOS"}
    _mm = {"m1": "beatriz51", "m2": "luiz"}

    def _card(nome, lista, labels, membros=("m1",)):
        return {"name": nome, "idList": lista, "idMembers": list(membros),
                "labels": [{"name": n} for n in labels]}
    _cards = [_card("A", "L1", ["EM ANDAMENTO"]),
              _card("B", "L1", ["EM ANDAMENTO", "INTERROMPIDO"]),
              _card("C", "L2", ["EM ANDAMENTO"]),
              _card("D", "L1", ["EM ANDAMENTO"], ("m2",))]
    _rod = cartoes_rodando("beatriz51", _li, _cards, _mm)
    ok("rodando: só o que o relógio conta, e só os da pessoa",
       [n for n, _ in _rod] == ["A", "C"])
    ok("duas demandas: a coluna Desativar não conta",
       [n for n, _ in demandas_simultaneas(_rod)] == ["A"])
    ok("com id: o cartão leva o id, para o aviso saber onde comentar",
       [x[2] for x in cartoes_rodando("beatriz51", _li,
                                       [dict(_cards[0], id="c1")], _mm, com_id=True)] == ["c1"])
    ok("duas demandas: dois cartões fora do Desativar contam",
       len(demandas_simultaneas(_rod + [("E", "PRODUÇÃO")])) == 2)
    _a = datetime(2026, 10, 26, 10, 0, tzinfo=_pc.FUSO)
    ok("expediente: dentro da janela batida, sim; no almoço, não",
       no_expediente([(_a.replace(hour=9), _a.replace(hour=12))], _a)
       and not no_expediente([(_a.replace(hour=8), _a.replace(hour=9))], _a))

    # resumo_da_pessoa pela forma REAL de `apuracao_bonus` (analise_metas):
    # crit_n é [(rotulo, True|False|None)], el traz entra_col e motivos_col.
    import analise_metas as _am_t
    _dados = [{"filtro_mes": (2026, 10), "pts_membro": {"beatriz51": 600.0},
               "cfg": {"meta_beatriz51": 1000}, "saldo": 3400.0,
               "meta_eq": 5000.0}]
    _bon = {"beatriz51": {
        "crit_n": [("pontuação (600 de 1.000 pts)", False),
                   ("ociosidade (14%, máx 10%)", False),
                   ("tempo médio", None), ("advertências (0 de 2)", True)],
        "el": {"entra_col": False, "motivos_col": ["60% da meta individual (mín. 80%)"]},
        "sit_pen": {"bateu_col": False}, "col": False, "maxx": False,
        "pct_time": 0.0, "pct_seu": 0.0}}
    _pont = {"beatriz51": {"pend": [{"data": "2026-10-09", "tipo": "sem_batida",
                                     "batidas": []}]}}
    _r = resumo_da_pessoa("beatriz51", _dados, _bon, _pont,
                          datetime(2026, 10, 26, 10, tzinfo=_pc.FUSO))
    ok("resumo: o que está contra é o que a apuração do bônus reprovou, nada mais",
       _r["contra"] == ["pontuação (600 de 1.000 pts)", "ociosidade (14%, máx 10%)"]
       and _r["em_dia"] == ["advertências (0 de 2)"])
    ok("resumo: fora da meta coletiva, com o motivo da própria elegibilidade",
       not _r["entra_col"] and "80%" in _r["motivos_col"][0])
    ok("resumo: o ponto pendente chega à tela",
       _r["pendencias"][0]["tipo"] == "sem_batida")
    ok("resumo: com os critérios em dia a metade individual paga 8%",
       _r["bonus_em_dia"] == (0.0, 8.0))
    ok("resumo: a projeção usa os dias úteis do calendário do Studio",
       _r["uteis"] == _am_t._dias_uteis_periodo(_dados, datetime(2026, 10, 26, 10, tzinfo=_pc.FUSO))[0]
       and _r["projecao"] > _r["pts"])

    # E PELA CADEIA: a apuração de verdade (`apuracao_bonus`), sem ponto, com
    # os campos que `_processar` grava no mês.
    _dc = [{"filtro_mes": (2026, 10), "pts_membro": {"beatriz51": 600.0, "luiz": 900.0},
            "cfg": {"meta_beatriz51": 1000, "meta_luiz": 1000}, "saldo": 1500.0,
            "meta_eq": 5000.0, "meta_maxx": 6000.0, "pen_qtd": 0}]
    _bc = _am_t.apuracao_bonus(_dc, ["beatriz51", "luiz"], pont={}, ocio={},
                               tem_ponto=False, medias_exec={})
    _rc = resumo_da_pessoa("beatriz51", _dc, _bc, {},
                           datetime(2026, 10, 26, 10, tzinfo=_pc.FUSO))
    ok("cadeia: a pontuação reprovada pela apuração real aparece contra, e o "
       "que não dá para medir não acusa ninguém",
       _rc["contra"] == ["pontuação (600 de 1.000 pts)"]
       and not _rc["entra_col"] and _rc["motivos_col"])

    # QUEM É DA EQUIPE TEM A ABA, EM QUALQUER BARRA (28/10): o Luiz tem
    # perfil admin e ficou sem a tela, porque ela só existia na barra dos
    # colaboradores. Os logins vêm da equipe de verdade (`MEMBROS_ATIVOS`).
    _u_eq = next(iter(_pc.MEMBROS_ATIVOS))
    ok("aparece_para: quem é da equipe ganha a aba, pelo login ou pelo nome",
       aparece_para(_u_eq) and aparece_para(_pc.MEMBROS_ATIVOS[_u_eq])
       and not aparece_para("martinsousa") and not aparece_para(""))
    import ast as _ast_nav
    _arv_app = _ast_nav.parse(open("app.py", encoding="utf-8").read())
    _f_op = next(n for n in _arv_app.body if isinstance(n, _ast_nav.FunctionDef)
                 and n.name == "_render_abas_operacao")
    ok("a barra de Operação do admin pergunta aparece_para, e põe a aba primeiro",
       any(isinstance(n, _ast_nav.Call) and getattr(n.func, "attr", "") == "aparece_para"
           for n in _ast_nav.walk(_f_op))
       and "_meu" in _ast_nav.unparse(_f_op).split("Análise de Viabilidade")[0])

    # O AVISO DO PONTO (dono, 30/10): prazo no 29, crítico no 28 e no 29.
    # As pendências na forma de `relogio_ponto.pendencia_do_dia`, de verdade.
    import relogio_ponto as _rp_t
    import folha_mes as _fm_t
    _pd = [_rp_t.pendencia_do_dia({"data": "2026-10-09", "batidas": []}, "2026-10-20", True),
           _rp_t.pendencia_do_dia({"data": "2026-10-14", "batidas": ["09:00"]}, "2026-10-20", True)]
    _dia = lambda d, m=10: datetime(2026, m, d, 10, tzinfo=_pc.FUSO)
    ok("sem pendência, sem aviso", alerta_de_ponto([], _dia(28)) is None)
    _a20 = alerta_de_ponto(_pd, _dia(20))
    ok("dia 20: aviso amarelo, 2 ajustes, prazo 29/10, e diz o que acontece depois",
       not _a20["critico"] and "2 ajustes" in _a20["titulo"] and "29/10" in _a20["titulo"]
       and "banco de horas" in _a20["texto"] and "falta não remunerada" in _a20["texto"])
    ok("dia 27 ainda é amarelo", not alerta_de_ponto(_pd, _dia(27))["critico"])
    ok("dia 28: crítico, AMANHÃ é o último dia",
       alerta_de_ponto(_pd, _dia(28))["critico"] and "AMANHÃ" in alerta_de_ponto(_pd, _dia(28))["titulo"])
    ok("dia 29: crítico, HOJE é o último dia",
       alerta_de_ponto(_pd, _dia(29))["critico"] and "HOJE" in alerta_de_ponto(_pd, _dia(29))["titulo"])
    ok("dia 30: o período virou, o prazo passa a ser 29/11",
       prazo_do_ajuste(_dia(30)).isoformat() == "2026-11-29"
       and prazo_do_ajuste(_dia(31, 12)).isoformat() == "2027-01-28")
    ok("pagamento: 30; fevereiro 28; sábado ou domingo, a sexta antes",
       _fm_t.dia_do_pagamento(2026, 10).isoformat() == "2026-10-30"
       and _fm_t.dia_do_pagamento(2027, 2).isoformat() == "2027-02-26"
       and _fm_t.dia_do_pagamento(2026, 8).isoformat() == "2026-08-28"
       and _fm_t.dia_do_pagamento(2027, 1).isoformat() == "2027-01-29")
    ok("no dia 30 as pendências do período fechado saem do aviso; as do aberto ficam",
       pendencias_em_aberto(_pd, _dia(30)) == []
       and pendencias_em_aberto(_pd, _dia(20)) == _pd
       and pendencias_em_aberto([{"data": "2026-09-30", "tipo": "sem_batida"}], _dia(5))
       == [{"data": "2026-09-30", "tipo": "sem_batida"}])
    ok("pagamento na sexta 28/08: prazo 27/08, e o 26 já é crítico",
       prazo_do_ajuste(_dia(10, 8)).isoformat() == "2026-08-27"
       and alerta_de_ponto(_pd, _dia(26, 8))["critico"]
       and not alerta_de_ponto(_pd, _dia(25, 8))["critico"])
    # QUAL HOLERITE ASSINAR (dono, 30/10: "assinem (...) sempre após o dia de
    # fechamento, no dia 30, através de um botão").
    from datetime import date as _date_t
    ok("dia 29: nada a assinar (outubro ainda aberto; setembro é antes do início)",
       holerite_a_assinar(_date_t(2026, 10, 29), {}, "bia") is None)
    ok("dia 30: assina outubro", holerite_a_assinar(_date_t(2026, 10, 30), {}, "bia") == (2026, 10))
    ok("05/11 sem ter assinado: ainda cobra outubro; assinado, nada",
       holerite_a_assinar(_date_t(2026, 11, 5), {}, "bia") == (2026, 10)
       and holerite_a_assinar(_date_t(2026, 11, 5), {"bia": {}}, "bia") is None)
    print("\nfalhas:", falhas)
    raise SystemExit(1 if falhas else 0)
