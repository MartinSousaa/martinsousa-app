"""mp_tela.py — A tela «💰 A liberar (MP)», no Financeiro.

Quanto dinheiro está preso no Mercado Pago das quatro contas, e em que dia
ele cai. O cálculo mora em `mp_api`; aqui é só o desenho.

Rede só no clique do botão: a tela redesenha a cada tecla, e quatro buscas
paginadas por tecla seriam dezenas de idas ao Mercado Pago.
"""

import streamlit as st

from fatura_ml import moeda
import mp_api

ROTULO_FONTE = {"mp": "Mercado Pago (variável própria)",
                "ml": "token do Mercado Livre", "": "—"}


def situacao(v):
    """A frase da coluna Situação. Erro e incompleto nunca saem calados."""
    if v.get("erro") and not v.get("lidos"):
        return "❌ " + v["erro"]
    if v.get("erro"):
        return f"⚠️ parou em {v['lidos']} de {v['total']}: {v['erro']}"
    if v.get("incompleto"):
        return f"⚠️ INCOMPLETO: li {v['lidos']} de {v['total']} pagamentos"
    return f"ok · {v.get('lidos', 0)} pagamentos lidos"


def avisos(lidas):
    """As frases de limite. Cada contador de `classificar` chega aqui."""
    saida = []
    for c, v in lidas.items():
        n = c.upper()
        if v.get("incompleto") or (v.get("erro") and v.get("lidos")):
            saida.append(f"**{n}**: o número está INCOMPLETO — o Mercado Pago tem "
                         f"{v['total']} pagamentos na janela e o Studio leu {v['lidos']}.")
        if v.get("sem_status"):
            saida.append(f"**{n}**: {v['sem_status']} pagamento(s) vieram sem o status de "
                         "liberação; para eles só a data decide, e o retido pode sair menor.")
        if v.get("com_devolucao"):
            saida.append(f"**{n}**: {v['com_devolucao']} pagamento(s) com devolução parcial — "
                         "o valor deles sai um pouco MENOR que o real (a devolução vem bruta).")
        if v.get("sem_data"):
            saida.append(f"**{n}**: {v['sem_data']} pagamento(s) aprovados sem data de "
                         "liberação ficaram de fora.")
        if v.get("ignorados"):
            saida.append(f"**{n}**: {v['ignorados']} pagamento(s) não aprovados vieram na "
                         "busca e ficaram de fora.")
    return saida


def linhas_por_conta(lidas):
    return [{"Conta": c.upper(), "A liberar": moeda(v.get("a_liberar", 0)),
             "Pagamentos": v.get("qtd_a_liberar", 0), "Retido": moeda(v.get("retido", 0)),
             "Token": ROTULO_FONTE.get(v.get("fonte", ""), v.get("fonte", "")),
             "Situação": situacao(v)} for c, v in lidas.items()]


def proximos(lidas, hoje, dias):
    """Soma do que cai de hoje até `dias` à frente, nas quatro contas."""
    from datetime import date, timedelta
    fim = (date.fromisoformat(hoje) + timedelta(days=dias)).isoformat()
    return sum(x for v in lidas.values() for d, x in v.get("por_dia", {}).items() if d < fim)


def pagina(usuario_logado=None):
    import auth
    import placar_core as _pc
    if not auth.eh_dono(usuario_logado):
        st.error("Acesso restrito ao dono do Studio.")
        return
    st.markdown("### 💰 A liberar — Mercado Pago")
    dados = st.session_state.get("mp_dados")
    # Rótulo FIXO (13/11): o botão é desenhado antes da leitura, e o «Ler de
    # novo» só aparecia uma passada depois. O «Lido em» diz se já leu.
    if st.button("🔄 Ler o Mercado Pago das 4 contas", key="mp_ler"):
        with st.spinner("Lendo os pagamentos das quatro contas…"):
            lidas = mp_api.ler_todas()
        st.session_state["mp_dados"] = dados = {
            "lidas": lidas, "hoje": _pc.agora_br().date().isoformat(),
            "quando": _pc.agora_br().strftime("%d/%m %H:%M")}
    if not dados:
        st.caption("Lê as vendas aprovadas dos últimos e dos próximos "
                   f"{mp_api.JANELA_DIAS} dias e soma o que ainda não foi liberado.")
        return
    lidas, hoje = dados["lidas"], dados["hoje"]
    total = sum(v.get("a_liberar", 0) for v in lidas.values())
    retido = sum(v.get("retido", 0) for v in lidas.values())
    c1, c2, c3 = st.columns(3)
    c1.metric("A liberar (4 contas)", moeda(total))
    c2.metric("Nos próximos 7 dias", moeda(proximos(lidas, hoje, 7)))
    c3.metric("Retido (devolução em aberto)", moeda(retido),
              help="O Mercado Livre segura o valor enquanto a devolução aberta pelo comprador "
                   "não termina: volta para o comprador ou é liberado para nós. Pela conta do "
                   "Studio: a data de liberação já passou e o Mercado Pago ainda não liberou.")
    st.caption(f"Lido em {dados['quando']}.")
    for a in avisos(lidas):
        st.warning(a)
    st.dataframe(linhas_por_conta(lidas), hide_index=True, use_container_width=True)
    cal = mp_api.calendario(lidas, dias=30, hoje=hoje)
    if cal:
        st.markdown("**Dia a dia — próximos 30 dias**")
        st.dataframe([{"Dia": (l["dia"] if l["dia"] == "depois"
                               else f"{l['dia'][8:10]}/{l['dia'][5:7]}"),
                       **{c.upper(): moeda(l[c]) for c in lidas}, "Total": moeda(l["total"])}
                      for l in cal], hide_index=True, use_container_width=True)


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    from datetime import datetime, timedelta, timezone
    BR = timezone(timedelta(hours=-3))
    AGORA = datetime(2026, 11, 12, 13, 0, tzinfo=BR)

    # A cadeia real: ler_todas de verdade, com a busca no formato do SDK.
    def buscar(tok, params):
        if tok == "t-ml2":
            return (None, "Mercado Pago recusou o token (401)")
        res = [{"status": "approved", "money_release_date": "2026-11-14T10:00:00.000-04:00",
                "money_release_status": "pending", "transaction_amount_refunded": 0,
                "transaction_details": {"net_received_amount": 100.0}},
               {"status": "approved", "money_release_date": "2026-11-30T10:00:00.000-04:00",
                "transaction_details": {"net_received_amount": 50.0}}]
        return ({"paging": {"total": 2}, "results": res}, "")

    lidas = mp_api.ler_todas(AGORA, buscar=buscar,
                             obter_token=lambda c: ("t-" + c, "ml" if c == "ml1" else "mp", ""))
    linhas = linhas_por_conta(lidas)
    ok("uma linha por conta", [l["Conta"] for l in linhas] == ["ML1", "ML2", "ML3", "ML4"])
    ok("a linha diz qual token foi usado", linhas[0]["Token"] == "token do Mercado Livre")
    ok("a conta recusada mostra o erro", "401" in linhas[1]["Situação"])
    ok("o valor sai em reais", linhas[0]["A liberar"] == "R$ 150,00")
    ok("próximos 7 dias pega só o que cai até lá", proximos(lidas, "2026-11-12", 7) == 300.0)
    av = avisos(lidas)
    ok("quem veio sem status de liberação é avisado", any("sem o status" in a for a in av))
    ok("incompleto é avisado",
       "INCOMPLETO" in situacao({"incompleto": True, "lidos": 4000, "total": 4100}))
    ok("parou no meio diz onde parou",
       "parou em 100 de 250" in situacao({"erro": "500", "lidos": 100, "total": 250}))
    _cont = ("sem_status", "com_devolucao", "sem_data", "ignorados")
    ok("todo contador de classificar tem frase própria",
       all(len(avisos({"ml1": {k: 1}})) == 1 for k in _cont)
       and set(_cont) <= set(mp_api.classificar([], AGORA)))
    print("\nfalhas:", falhas)
    raise SystemExit(1 if falhas else 0)
