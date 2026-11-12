"""shopee_tela.py — A tela «🛍️ Shopee», no Operacional.

Três respostas, das duas lojas, dos últimos N dias:
  1. o NOME que a Shopee mostra para cada SKU, e se o SKU existe no estoque;
  2. o gasto de ads por dia, com a venda que a Shopee atribui a ele;
  3. as promoções e cupons em andamento.

Não soma faturamento: esse vem da BASE DE VENDAS (ver `shopee_api`).
Rede só no clique do botão. Credencial buscada na thread da tela; a thread
só faz rede.
"""

from datetime import datetime, timedelta

import streamlit as st

from fatura_ml import moeda
import shopee_api as S

DIAS_PADRAO = 30


def ler_loja(credencial, de, ate, ida=None):
    """As três leituras de uma loja. Roda em thread: não toca session_state."""
    return {"pedidos": S.pedidos(credencial, de, ate, ida),
            "ads": S.ads_diario(credencial, de, ate, ida),
            "promocoes": S.promocoes(credencial, "ongoing", ida)}


def ler_todas(dias=DIAS_PADRAO, agora=None, obter=None, ida=None):
    """{loja: {"erro": str} | {pedidos, ads, promocoes}}."""
    from concurrent.futures import ThreadPoolExecutor
    if agora is None:
        import placar_core as _pc
        agora = datetime.now(_pc.FUSO)
    obter = obter or S.credencial_da_loja
    de = agora - timedelta(days=dias)
    creds = {l: obter(l) for l in S.LOJAS}

    def _uma(l):
        cred, erro = creds[l]
        return l, ({"erro": erro} if erro else ler_loja(cred, de, agora, ida))

    with ThreadPoolExecutor(max_workers=2) as ex:
        return dict(ex.map(_uma, S.LOJAS))


def skus_do_estoque():
    """O conjunto de SKUs cadastrados no estoque, ou None se não deu para ler."""
    try:
        import estoque as E
        produtos = E.carregar()[0]
        return {E.normalizar_sku(p.get("sku")) for p in produtos if E.normalizar_sku(p.get("sku"))}
    except Exception:
        return None


def avisos_da_loja(nome, v):
    """Todo limite e todo erro da leitura vira frase."""
    if v.get("erro"):
        return [f"**{nome}**: {v['erro']}"]
    saida = []
    p = v["pedidos"]
    if p.get("erro"):
        saida.append(f"**{nome}** · pedidos: {p['erro']}")
    if p.get("incompleto"):
        saida.append(f"**{nome}** · pedidos INCOMPLETOS: a leitura parou antes do fim "
                     f"({p.get('pedidos', 0)} pedidos lidos).")
    if v["ads"].get("erro"):
        saida.append(f"**{nome}** · ads: {v['ads']['erro']}")
    for tipo in ("descontos", "cupons"):
        r = v["promocoes"][tipo]
        if r.get("erro"):
            saida.append(f"**{nome}** · {tipo}: {r['erro']}")
        elif r.get("incompleto"):
            saida.append(f"**{nome}** · {tipo} INCOMPLETOS: passou de {S.MAX_PAGINAS} páginas.")
    return saida


def linhas_ponte(ponte):
    def _est(x):
        return "—" if x is None else ("✅ sim" if x else "❌ não está no estoque")
    return [{"SKU": l["sku"] or "⚠️ SEM SKU na Shopee", "Nome na Shopee": " | ".join(l["nomes"]),
             "Vendidos": l["vendidos"], "No estoque": _est(l["no_estoque"])} for l in ponte]


def linhas_ads(dias):
    saida = []
    for d in dias:
        gasto, venda = float(d.get("expense") or 0), float(d.get("broad_gmv") or 0)
        saida.append({"Dia": str(d.get("date", ""))[:5].replace("-", "/"),
                      "Gasto": moeda(gasto), "Venda atribuída": moeda(venda),
                      "ROAS": f"{venda / gasto:.1f}" if gasto else "—",
                      "Pedidos": d.get("broad_order") or 0, "Cliques": d.get("clicks") or 0})
    return saida


def _quando(epoch):
    try:
        import placar_core as _pc
        return datetime.fromtimestamp(int(epoch), _pc.FUSO).strftime("%d/%m %H:%M")
    except Exception:
        return ""


def linhas_promocoes(promo):
    saida = [{"Tipo": "Desconto", "Nome": d.get("discount_name", ""),
              "Detalhe": d.get("source", "") or "", "Início": _quando(d.get("start_time")),
              "Fim": _quando(d.get("end_time"))} for d in promo["descontos"]["lista"]]
    for c in promo["cupons"]["lista"]:
        det = (f"{c.get('percentage')}%" if c.get("reward_type") == 2
               else moeda(c.get("discount_amount") or 0))
        saida.append({"Tipo": "Cupom", "Nome": f"{c.get('voucher_name', '')} ({c.get('voucher_code', '')})",
                      "Detalhe": f"{det} · usado {c.get('current_usage', 0)}/{c.get('usage_quantity', 0)}",
                      "Início": _quando(c.get("start_time")), "Fim": _quando(c.get("end_time"))})
    return saida


def pagina(usuario_logado=None):
    import auth
    import placar_core as _pc
    if not auth.eh_dono(usuario_logado):
        st.error("Acesso restrito ao dono do Studio.")
        return
    st.markdown("### 🛍️ Shopee — nomes, ads e promoções")
    if not S.configurado():
        st.warning(f"A Shopee ainda não está ligada: {S.FALTA_CREDENCIAL}. "
                   "Depois, autorize as duas lojas em Gestão › Registros › Shopee.")
        return
    dados = st.session_state.get("shp_dados")
    if st.button(f"🔄 Ler as duas lojas (últimos {DIAS_PADRAO} dias)" if not dados
                 else "🔄 Ler de novo", key="shp_ler"):
        with st.spinner("Lendo pedidos, ads e promoções das duas lojas…"):
            lidas = ler_todas()
            estoque = skus_do_estoque()
        st.session_state["shp_dados"] = dados = {
            "lidas": lidas, "estoque": estoque, "quando": _pc.agora_br().strftime("%d/%m %H:%M")}
    if not dados:
        st.caption("A leitura passa por todos os pedidos do período e leva alguns segundos.")
        return
    st.caption(f"Lido em {dados['quando']}.")
    if dados["estoque"] is None:
        st.warning("Não consegui ler o estoque: a coluna «No estoque» ficou sem resposta.")
    for loja, v in dados["lidas"].items():
        nome = S.NOME_DA_LOJA[loja]
        st.markdown(f"#### {nome}")
        for a in avisos_da_loja(nome, v):
            st.warning(a)
        if v.get("erro"):
            continue
        ponte = S.nomes_por_sku(v["pedidos"]["itens"], dados["estoque"])
        st.markdown("**Nome na Shopee × SKU**")
        if ponte:
            st.dataframe(linhas_ponte(ponte), hide_index=True, use_container_width=True)
        else:
            st.caption("Nenhuma venda no período.")
        dias = v["ads"]["dias"]
        gasto = sum(float(d.get("expense") or 0) for d in dias)
        venda = sum(float(d.get("broad_gmv") or 0) for d in dias)
        c1, c2, c3 = st.columns(3)
        c1.metric("Ads — gasto", moeda(gasto))
        c2.metric("Venda atribuída aos ads", moeda(venda))
        c3.metric("ROAS", f"{venda / gasto:.1f}" if gasto else "—")
        if dias:
            st.dataframe(linhas_ads(dias), hide_index=True, use_container_width=True)
        promo = linhas_promocoes(v["promocoes"])
        st.markdown(f"**Promoções em andamento: {len(promo)}**")
        if promo:
            st.dataframe(promo, hide_index=True, use_container_width=True)


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from datetime import timezone
    import threading
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    BR = timezone(timedelta(hours=-3))
    AGORA = datetime(2026, 11, 12, 13, 0, tzinfo=BR)

    def ida(metodo, caminho, params, corpo=None):
        if caminho.endswith("get_order_list"):
            return ({"error": "", "response": {"more": False, "next_cursor": "",
                                               "order_list": [{"order_sn": "A1"}]}}, "")
        if caminho.endswith("get_order_detail"):
            return ({"error": "", "response": {"order_list": [{
                "order_sn": "A1", "order_status": "COMPLETED", "create_time": 1700000000,
                "item_list": [{"item_name": "Porta 2 Relógio + Jóias", "item_sku": "pr-2",
                               "model_name": "", "model_sku": "", "model_quantity_purchased": 1}]}]}}, "")
        if caminho.endswith("daily_performance"):
            return ({"error": "", "response": [{"date": params["start_date"], "expense": 10.0,
                                                "broad_gmv": 45.0, "broad_order": 1, "clicks": 7}]}, "")
        if caminho.endswith("get_discount_list"):
            return ({"error": "", "response": {"more": False, "discount_list": [
                {"discount_name": "Black", "start_time": 1700000000, "end_time": 1700086400}]}}, "")
        return ({"error": "", "response": {"more": False, "voucher_list": [
            {"voucher_name": "DEZ", "voucher_code": "DEZOFF", "reward_type": 2, "percentage": 10,
             "usage_quantity": 100, "current_usage": 3}]}}, "")

    _thr = []

    def obter(l):
        _thr.append(threading.current_thread() is threading.main_thread())
        return ((None, "Shopee 2 (LG) ainda não foi autorizada") if l == "shp2"
                else (("1", "k", "t", "77"), ""))

    lidas = ler_todas(30, AGORA, obter, ida)
    ok("credencial buscada na thread da tela", _thr and all(_thr))
    ok("loja sem autorização volta com o erro dela", lidas["shp2"] == {"erro": "Shopee 2 (LG) ainda não foi autorizada"})
    ok("e a outra traz as três leituras", set(lidas["shp1"]) == {"pedidos", "ads", "promocoes"})
    ok("o aviso da loja sem autorização é dito",
       avisos_da_loja("Shopee 2 (LG)", lidas["shp2"]) == ["**Shopee 2 (LG)**: Shopee 2 (LG) ainda não foi autorizada"])
    ponte = S.nomes_por_sku(lidas["shp1"]["pedidos"]["itens"], {"PR-2"})
    lp = linhas_ponte(ponte)
    ok("o SKU minúsculo da Shopee casa com o do estoque",
       lp[0]["SKU"] == "PR-2" and lp[0]["No estoque"] == "✅ sim"
       and lp[0]["Nome na Shopee"] == "Porta 2 Relógio + Jóias")
    ok("SKU vazio é chamado pelo nome", linhas_ponte([{"sku": "", "nomes": ["X"], "vendidos": 1,
                                                        "no_estoque": None}])[0]["SKU"].startswith("⚠️"))
    la = linhas_ads(lidas["shp1"]["ads"]["dias"])
    ok("ads em reais, com ROAS", la[0]["Gasto"] == "R$ 10,00" and la[0]["ROAS"] == "4.5")
    lpr = linhas_promocoes(lidas["shp1"]["promocoes"])
    ok("desconto e cupom na mesma tabela",
       [l["Tipo"] for l in lpr] == ["Desconto", "Cupom"] and "10%" in lpr[1]["Detalhe"]
       and "3/100" in lpr[1]["Detalhe"])
    _v = {"pedidos": {"erro": "", "incompleto": True, "pedidos": 4},
          "ads": {"erro": "Shopee: ads.rate_limit.exceed_api"},
          "promocoes": {"descontos": {"erro": "", "incompleto": True}, "cupons": {"erro": "x"}}}
    _av = " ".join(avisos_da_loja("L", _v))
    ok("todo limite vira frase: pedidos, ads, descontos e cupons",
       "INCOMPLETOS" in _av and "rate_limit" in _av and "descontos INCOMPLETOS" in _av and "cupons: x" in _av)
    print("\nfalhas:", falhas)
    raise SystemExit(1 if falhas else 0)
