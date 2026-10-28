"""promocoes_ml.py — promoções do Mercado Livre nas quatro contas, por produto.

O PEDIDO (dono, 28/10)
----------------------
Cada anúncio existe nas quatro contas com o MESMO TÍTULO. A tela acha o
produto pelo título, junta a mesma promoção das quatro contas numa caixa só,
uma linha por conta, e deixa ajustar cada linha antes de entrar em todas de
uma vez. Promoção que só existe numa conta aparece só nela. A que o ML
define sozinho (desconto fixo) aparece marcada como "só aceitar ou não".

Três abas (layout aprovado 28/10): em andamento, disponíveis, criar desconto.

DE ONDE VEM CADA REGRA
----------------------
Da documentação do ML (developers.mercadolivre.com.br, páginas
campanhas-tradicionais, ofertas-relampago, desconto-individua,
campanhas-smart-price-matching, desconto-pre-acordado-por-item,
gerenciar-ofertas, lidas em 28/10) e da amostra real da ML1 (28/10 12:26):

- a lista de anúncios de uma promoção vem em páginas de 50, e a próxima
  página se pede com `search_after`, o valor que a resposta devolve em
  `paging.searchAfter` (TTL de 5 minutos, só para frente);
- a lista NÃO traz o título: ele vem de `/items?ids=` (até 20 por vez);
- para entrar: POST `/seller-promotions/items/{item}?app_version=v2`, com
  `deal_price` nas que aceitam preço (DEAL, SELLER_CAMPAIGN, LIGHTNING com
  `stock`, PRICE_DISCOUNT com datas) e `offer_id` nas que o ML define;
- para sair: DELETE no mesmo caminho, com `promotion_type`, `promotion_id`
  e `offer_id` quando houver;
- PRICE_DISCOUNT: de 5% a 80%, no máximo 14 dias, a data vale o dia inteiro.

A ESCRITA NÃO FOI EXERCITADA EM CONTA REAL antes desta versão. A primeira
vez é com o dono olhando, num anúncio só (combinado em 28/10).
"""
import hashlib
import unicodedata
from datetime import date, timedelta

import streamlit as st

import ml_api as _ml

LIMITE = 50              # o máximo que o ML aceita por página
PAGINAS_MAX = 80         # 4.000 anúncios por promoção; passou disso, a tela DIZ
LOTE_TITULOS = 20        # o máximo do /items?ids=
SITUACOES_VIVAS = ("started", "pending", "candidate")
DESCONTO_MIN, DESCONTO_MAX, DIAS_MAX = 5.0, 80.0, 14   # PRICE_DISCOUNT

# O que a equipe pode editar em cada tipo. Tipo que não estiver aqui é
# tratado como "o ML define": mostrar um campo de % que o ML vai ignorar
# seria pior que não mostrar.
COM_PRECO = {"DEAL", "SELLER_CAMPAIGN", "LIGHTNING", "PRICE_DISCOUNT"}
COM_ESTOQUE = {"LIGHTNING", "SMART_LIGHTNING"}
NOMES = {"LIGHTNING": "Relâmpago", "DEAL": "Campanha", "SMART": "Co-participação",
         "SMART_LIGHTNING": "Relâmpago automática", "UNHEALTHY_STOCK": "Estoque Full",
         "PRICE_DISCOUNT": "Desconto do vendedor", "SELLER_CAMPAIGN": "Campanha do vendedor",
         "PRE_NEGOTIATED": "Desconto pré-acordado", "PRICE_MATCHING": "Preço competitivo",
         "MARKETPLACE_CAMPAIGN": "Campanha do ML"}


# ── Puras ─────────────────────────────────────────────────────────────────────
def normalizar(texto):
    """O título na forma em que as quatro contas concordam. Pura.

    Sem acento, sem caixa e com um espaço só: "Cavaleiro  Medieval" e
    "cavaleiro medieval" são o mesmo anúncio digitado duas vezes."""
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.casefold().split())


def editavel(tipo):
    return tipo in COM_PRECO


def nome_da_promocao(p):
    return str(p.get("name") or NOMES.get(p.get("type"), p.get("type") or "?"))


def chave_da_promocao(tipo, nome):
    """A mesma promoção nas quatro contas: tipo + nome. Pura.

    O id NÃO serve: nas promoções automáticas cada conta recebe o seu."""
    return f"{tipo}|{normalizar(nome)}"


def preco_hoje(oferta):
    """O preço sem promoção. A DEAL candidata vem com `price` 0. Pura."""
    for k in ("original_price", "price"):
        try:
            v = float(oferta.get(k) or 0)
        except (TypeError, ValueError):
            v = 0.0
        if v > 0:
            return v
    return 0.0


def preco_com(base, pct):
    return round(base * (1 - float(pct) / 100), 2)


def pct_de(base, preco):
    return round((1 - preco / base) * 100, 1) if base and preco else 0.0


def pct_sugerido(oferta):
    """O % que o ML sugere (ou impõe) para esta linha. Pura."""
    base = preco_hoje(oferta)
    for k in ("suggested_discounted_price", "price"):
        v = float(oferta.get(k) or 0)
        if 0 < v < base:
            return pct_de(base, v)
    soma = float(oferta.get("seller_percentage") or 0) + float(oferta.get("meli_percentage") or 0)
    return round(soma, 1)


def validar(oferta, pct=None, estoque=None):
    """(preço, erro) desta linha com este %. erro '' quando o ML deve aceitar.

    Confere a faixa que o PRÓPRIO ML devolveu para a linha (min e max do
    preço com desconto, e o estoque mínimo e máximo do relâmpago): o que
    sair dela não é enviado — o ML recusaria, e a recusa chegaria depois de
    o resto ter subido. Pura."""
    tipo = oferta.get("tipo")
    base = preco_hoje(oferta)
    if not editavel(tipo):
        preco = float(oferta.get("price") or 0) or None
    else:
        if pct is None or not (0 < float(pct) < 100):
            return (None, "desconto precisa ficar entre 0% e 100%")
        if not base:
            return (None, "o ML não mandou o preço deste anúncio")
        preco = preco_com(base, pct)
        mn = float(oferta.get("min_discounted_price") or 0)
        mx = float(oferta.get("max_discounted_price") or 0)
        if mn and preco < mn:
            return (preco, f"abaixo do mínimo do ML (R$ {mn:.2f}, {pct_de(base, mn):.0f}%)")
        if mx and preco > mx:
            return (preco, f"acima do máximo do ML (R$ {mx:.2f}, {pct_de(base, mx):.0f}%)")
        if tipo == "PRICE_DISCOUNT" and not (DESCONTO_MIN <= float(pct) <= DESCONTO_MAX):
            return (preco, f"o desconto do vendedor vai de {DESCONTO_MIN:.0f}% a {DESCONTO_MAX:.0f}%")
    if tipo in COM_ESTOQUE:
        faixa = oferta.get("stock") or {}
        try:
            e = int(estoque)
        except (TypeError, ValueError):
            return (preco, "falta o estoque da oferta")
        if faixa.get("min") and e < int(faixa["min"]):
            return (preco, f"estoque mínimo do ML: {faixa['min']}")
        if faixa.get("max") and e > int(faixa["max"]):
            return (preco, f"estoque máximo do ML: {faixa['max']}")
    return (preco, "")


def pedido_de_entrada(oferta, preco=None, estoque=None, inicio=None, fim=None):
    """(caminho, params, corpo) do POST que coloca a linha na promoção. Pura.

    Os campos são os da documentação de cada tipo (ver o topo do arquivo)."""
    tipo = oferta["tipo"]
    corpo = {"promotion_type": tipo}
    if tipo in ("DEAL", "SELLER_CAMPAIGN"):
        corpo.update(promotion_id=oferta["promo_id"], deal_price=preco)
    elif tipo == "LIGHTNING":
        corpo.update(deal_price=preco, stock=int(estoque))
    elif tipo == "PRICE_DISCOUNT":
        corpo.update(deal_price=preco, start_date=f"{inicio}T00:00:00",
                     finish_date=f"{fim}T00:00:00")
    else:
        corpo.update(promotion_id=oferta["promo_id"], offer_id=oferta.get("offer_id", ""))
        if tipo in COM_ESTOQUE and estoque is not None:
            corpo["stock"] = int(estoque)
    return (f"/seller-promotions/items/{oferta['item']}", {"app_version": "v2"}, corpo)


def pedido_de_saida(oferta):
    """(caminho, params) do DELETE que tira a linha da promoção. Pura."""
    p = {"promotion_type": oferta["tipo"], "app_version": "v2"}
    if oferta.get("promo_id") and oferta["tipo"] not in ("LIGHTNING", "PRICE_DISCOUNT"):
        p["promotion_id"] = oferta["promo_id"]
    if oferta.get("offer_id") and oferta["tipo"] not in COM_PRECO:
        p["offer_id"] = oferta["offer_id"]
    return (f"/seller-promotions/items/{oferta['item']}", p)


def datas_validas(inicio, fim, hoje):
    """'' se o par de datas serve ao desconto do vendedor. Pura."""
    if fim < inicio:
        return "o fim vem antes do início"
    if inicio < hoje:
        return "o início já passou"
    if (fim - inicio).days + 1 > DIAS_MAX:
        return f"o ML aceita no máximo {DIAS_MAX} dias"
    return ""


def ident(*partes):
    """Chave curta e estável para os widgets de uma linha. Pura."""
    return hashlib.md5("|".join(map(str, partes)).encode("utf-8")).hexdigest()[:10]


def agrupar(lidas):
    """Junta as quatro contas por produto. Pura.

    lidas: {conta: {"ofertas": [...], "titulos": {item: {...}}}}
    Devolve {"produtos": [...], "andamento": [...]}; cada produto tem
    "titulo", "anuncios" {conta: [item...]} e "promocoes" [caixa], e cada
    caixa tem "tipo", "nome", "editavel", "fim", "linhas" (uma por conta e
    anúncio).
    """
    produtos, andamento = {}, []
    for conta in _ml.CONTAS:
        dado = lidas.get(conta) or {}
        tit = dado.get("titulos") or {}
        for o in dado.get("ofertas") or []:
            info = tit.get(o["item"]) or {}
            titulo = info.get("title") or o["item"]
            o = dict(o, conta=conta, titulo=titulo, thumb=info.get("thumbnail", ""),
                     estoque_anuncio=info.get("available_quantity"))
            if o.get("status") in ("started", "pending"):
                andamento.append(o)
                continue
            chave = normalizar(titulo)
            pr = produtos.setdefault(chave, {"titulo": titulo, "anuncios": {},
                                             "caixas": {}, "thumb": o["thumb"]})
            lst = pr["anuncios"].setdefault(conta, [])
            if o["item"] not in lst:
                lst.append(o["item"])
            cx = pr["caixas"].setdefault(chave_da_promocao(o["tipo"], o["nome"]), {
                "tipo": o["tipo"], "nome": o["nome"], "editavel": editavel(o["tipo"]),
                "fim": o.get("fim", ""), "prazo": o.get("prazo", ""), "linhas": []})
            cx["linhas"].append(o)
    lista = []
    for chave, pr in produtos.items():
        caixas = sorted(pr["caixas"].values(),
                        key=lambda c: (-len({l["conta"] for l in c["linhas"]}), c["nome"]))
        for c in caixas:
            c["linhas"].sort(key=lambda l: (l["conta"], l["item"]))
            c["contas"] = sorted({l["conta"] for l in c["linhas"]})
        lista.append({"chave": chave, "titulo": pr["titulo"], "thumb": pr["thumb"],
                      "anuncios": pr["anuncios"], "promocoes": caixas})
    lista.sort(key=lambda p: (-len(p["anuncios"]), p["titulo"]))
    andamento.sort(key=lambda o: (o["titulo"], o["conta"]))
    return {"produtos": lista, "andamento": andamento}


# ── A leitura (rede) ──────────────────────────────────────────────────────────
def ofertas_da_promocao(conta, tok, promo, req):
    """Todas as linhas de uma promoção, página a página. (ofertas, aviso).

    O aviso não fica vazio quando a lista foi cortada ou falhou no meio: a
    tela diz quantas leu de quantas — limite calado é defeito desta base."""
    tipo = promo.get("type", "")
    base = {"promotion_type": tipo, "app_version": "v2", "limit": LIMITE}
    saida, depois, total = [], None, None
    for _ in range(PAGINAS_MAX):
        params = dict(base, **({"search_after": depois} if depois else {}))
        resp, erro = req("GET", conta, tok,
                         f"/seller-promotions/promotions/{promo['id']}/items", params)
        if erro:
            return (saida, f"{nome_da_promocao(promo)}: parou em {len(saida)} — {erro}")
        resp = resp if isinstance(resp, dict) else {}
        pag = resp.get("paging") if isinstance(resp.get("paging"), dict) else {}
        total = pag.get("total", total)
        for it in resp.get("results") or []:
            if not isinstance(it, dict) or it.get("status") not in SITUACOES_VIVAS:
                continue
            saida.append({
                **{k: it.get(k) for k in ("status", "price", "original_price",
                                          "min_discounted_price", "max_discounted_price",
                                          "suggested_discounted_price", "seller_percentage",
                                          "meli_percentage", "stock",
                                          # o reembolso da tarifa (boost): o bolso
                                          # do vendedor depende dele (28/10)
                                          "boosted_offer", "discount_meli_boost_amount",
                                          "discount_meli_boosted_percentage",
                                          "total_price_for_boosted_offer")},
                "item": it.get("id"), "tipo": tipo, "promo_id": promo.get("id", ""),
                "nome": nome_da_promocao(promo),
                "offer_id": it.get("offer_id") or it.get("ref_id") or "",
                "fim": it.get("end_date") or promo.get("finish_date", ""),
                "prazo": promo.get("deadline_date", "")})
        depois = pag.get("searchAfter") or pag.get("search_after")
        if not depois or not resp.get("results"):
            return (saida, "")
    return (saida, f"{nome_da_promocao(promo)}: cortada em {PAGINAS_MAX * LIMITE} de {total}")


def titulos(conta, tok, ids, req):
    """{item: {title, price, thumbnail, available_quantity}}, 20 por vez."""
    saida, avisos = {}, []
    ids = list(dict.fromkeys(i for i in ids if i))
    for i in range(0, len(ids), LOTE_TITULOS):
        lote = ids[i:i + LOTE_TITULOS]
        resp, erro = req("GET", conta, tok, "/items", {
            "ids": ",".join(lote),
            "attributes": "id,title,price,thumbnail,available_quantity,permalink"})
        if erro:
            avisos.append(f"títulos: {len(lote)} sem nome — {erro}")
            continue
        for r in resp if isinstance(resp, list) else []:
            b = (r or {}).get("body") or {}
            if (r or {}).get("code") == 200 and b.get("id"):
                saida[b["id"]] = b
    return saida, avisos


def ler_conta(conta, tok, uid, req=None):
    """Tudo o que a tela precisa de UMA conta. Roda em thread: não toca em
    `st.session_state` nem no token (que chega pronto)."""
    req = req or _ml.requisitar
    fora = {"ofertas": [], "titulos": {}, "avisos": [], "promocoes": 0}
    resp, erro = req("GET", conta, tok, f"/seller-promotions/users/{uid}", {"app_version": "v2"})
    if erro:
        fora["avisos"].append(erro)
        return fora
    promos = resp.get("results") if isinstance(resp, dict) else resp
    promos = [p for p in promos or [] if isinstance(p, dict) and p.get("id")
              and p.get("status") in ("started", "pending")]
    fora["promocoes"] = len(promos)
    for p in promos:
        ofs, aviso = ofertas_da_promocao(conta, tok, p, req)
        fora["ofertas"].extend(ofs)
        if aviso:
            fora["avisos"].append(aviso)
    fora["titulos"], av = titulos(conta, tok, [o["item"] for o in fora["ofertas"]], req)
    fora["avisos"].extend(av)
    return fora


def ler_todas():
    """As quatro contas em paralelo. {conta: dado}. O token de cada uma é
    buscado AQUI, na thread da tela (ele lê a planilha e pode renovar)."""
    from concurrent.futures import ThreadPoolExecutor
    prontas, lidas = {}, {}
    for c in _ml.CONTAS:
        uid = str((_ml._ler_da_planilha(c) or {}).get("user_id", "")).strip()
        tok, erro = _ml.token(c) if uid else ("", "ainda não foi autorizada")
        if erro:
            lidas[c] = {"ofertas": [], "titulos": {}, "avisos": [erro], "promocoes": 0}
        else:
            prontas[c] = (tok, uid)
    with ThreadPoolExecutor(max_workers=4) as ex:
        fut = {c: ex.submit(ler_conta, c, t, u) for c, (t, u) in prontas.items()}
        for c, f in fut.items():
            try:
                lidas[c] = f.result()
            except Exception as e:
                lidas[c] = {"ofertas": [], "titulos": {}, "promocoes": 0,
                            "avisos": [f"a leitura caiu: {type(e).__name__}"]}
    return lidas


def faixa_do_desconto(conta, item):
    """A linha PRICE_DISCOUNT do anúncio (faixa de preço do ML). (oferta, erro)."""
    resp, erro = _ml.get(conta, f"/seller-promotions/items/{item}", {"app_version": "v2"})
    if erro:
        return (None, erro)
    for p in resp if isinstance(resp, list) else []:
        if isinstance(p, dict) and p.get("type") == "PRICE_DISCOUNT":
            return ({**p, "item": item, "tipo": "PRICE_DISCOUNT", "conta": conta,
                     "promo_id": "", "nome": NOMES["PRICE_DISCOUNT"]}, "")
    return (None, "o ML não oferece desconto do vendedor para este anúncio")


# ── A tela ────────────────────────────────────────────────────────────────────
def _brl(v):
    try:
        return "R$ " + f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "—"


def _md(v):
    """O dinheiro dentro de `st.markdown`: o `$` sozinho vira fórmula (LaTeX)
    entre dois valores — "R$ 27,00 – R$ 130,94" saía em itálico matemático."""
    return _brl(v).replace("$", "\\$")


def _data(iso):
    s = str(iso or "")
    return f"{s[8:10]}/{s[5:7]}/{s[2:4]}" if len(s) >= 10 else "—"


def _executar(pedidos):
    """Roda os POST/DELETE confirmados. [(conta, item, ok, msg)]."""
    saida = []
    for conta, item, metodo, caminho, params, corpo in pedidos:
        resp, erro = _ml.escrever(conta, metodo, caminho, params, corpo)
        saida.append((conta, item, not erro, erro or "ok"))
    return saida


def _confirmar(chave, pedidos, rotulo):
    """Primeiro clique arma, o segundo grava. Devolve o resultado ou None."""
    armado = st.session_state.get("pml_armado") == chave
    if not armado:
        if st.button(rotulo, key=f"pml_b_{chave}", type="primary", disabled=not pedidos):
            st.session_state["pml_armado"] = chave
            st.rerun()
        return None
    st.warning(f"Confirma? Isto muda {len(pedidos)} anúncio(s) no Mercado Livre agora.")
    c1, c2 = st.columns(2)
    if c2.button("Cancelar", key=f"pml_n_{chave}"):
        st.session_state.pop("pml_armado", None)
        st.rerun()
    if c1.button("✅ Confirmar", key=f"pml_s_{chave}", type="primary"):
        st.session_state.pop("pml_armado", None)
        with st.spinner("Enviando ao Mercado Livre…"):
            res = _executar(pedidos)
        st.session_state["pml_resultado"] = res
        st.session_state["pml_desatualizado"] = True
        st.rerun()
    return None


def _resultado():
    res = st.session_state.pop("pml_resultado", None)
    if not res:
        return
    bons = sum(1 for r in res if r[2])
    (st.success if bons == len(res) else st.warning)(
        f"{bons} de {len(res)} entraram no Mercado Livre.")
    for conta, item, ok, msg in res:
        st.markdown(f"{'✅' if ok else '❌'} **{conta.upper()}** · {item} · {msg}")


def linhas_da_caixa(cx, pct_todas=None, editados=None, estoques=None, desmarcados=()):
    """As linhas da tabela de uma promoção e os pedidos das marcadas. Pura.

    pct_todas  o "% para todas" da caixa (None = o sugerido de cada conta)
    editados   {índice da linha: %} digitado na própria tabela — vence o geral
    estoques   {índice: estoque} do relâmpago
    Devolve (linhas, pedidos): cada linha já com o preço, o bolso e o aviso."""
    import promocoes_auto as _pa
    edit = cx["editavel"]
    linhas, pedidos = [], []
    for i, l in enumerate(cx["linhas"]):
        base = preco_hoje(l)
        if edit:
            pct = (editados or {}).get(i)
            if pct is None:
                pct = pct_todas if pct_todas is not None else pct_sugerido(l)
        else:
            pct = pct_sugerido(l)
        est = None
        if cx["tipo"] in COM_ESTOQUE:
            fx = l.get("stock") or {}
            est = (estoques or {}).get(i) or int(fx.get("min") or 1)
        preco, erro = validar(l, float(pct) if edit else None, est)
        ef = _pa.efetivo(l, preco if edit else None) if preco else None
        mn, mx = l.get("min_discounted_price"), l.get("max_discounted_price")
        marcado = i not in desmarcados
        linhas.append({"Entrar": marcado, "Conta": l["conta"].upper(), "Anúncio": l["item"],
                       "Preço hoje": _brl(base), "Desconto %": float(pct),
                       "Na promoção": _brl(preco) if preco else "—",
                       "No bolso": f"{ef:.1f}%".replace(".", ",") if ef is not None else "—",
                       "Estoque": est,
                       "Faixa do ML / aviso": ("⚠️ " + erro) if erro else
                       (f"{_brl(mn)} – {_brl(mx)}" if mn and mx else "")})
        if marcado and not erro:
            cam, par, corpo = pedido_de_entrada(l, preco, est)
            pedidos.append((l["conta"], l["item"], "POST", cam, par, corpo))
    return linhas, pedidos


def _caixa(pr, cx):
    """Uma promoção de um produto: uma tabela, uma linha por conta.

    Era uma fileira de widgets por conta (28/10): alta, com colunas vazias e o
    "aplicar em todas" solto no meio. O dono pediu melhor. Agora é UMA tabela
    editável — o % e o estoque se digitam nela —, e o "% para todas" e o
    botão ficam no cabeçalho da caixa."""
    import pandas as pd
    edit, com_est = cx["editavel"], cx["tipo"] in COM_ESTOQUE
    ck = ident(pr["chave"], cx["tipo"], cx["nome"])
    with st.container(border=True):
        h1, h2, h3 = st.columns([3.2, 1.1, 1.4], vertical_alignment="bottom")
        contas = ", ".join(c.upper() for c in cx["contas"])
        h1.markdown(f"<b style='font-size:15px'>{cx['nome']}</b> "
                    f"<span style='font-size:10px;padding:1px 6px;border-radius:8px;"
                    f"background:#EDA10033;color:#EDA100'>{cx['tipo']}</span><br>"
                    f"<span style='font-size:12px;opacity:.75'>em {contas}"
                    + (f" · termina {_data(cx['fim'])}" if cx.get("fim") else "")
                    + (f" · entrar até {_data(cx['prazo'])}" if cx.get("prazo") else "")
                    + "</span>", unsafe_allow_html=True)
        pct_todas = None
        if edit:
            pct_todas = h2.number_input("% para todas", 0.0, 99.0, value=None, step=1.0,
                                        format="%.1f", key=f"pml_all_{ck}",
                                        placeholder="sugerido")
        else:
            h2.markdown("🔒 **o ML define**")
        # As edições da tabela ficam no estado dela; a tabela é remontada com
        # elas aplicadas, para o preço e o bolso acompanharem o % digitado. O
        # "% para todas" entra na chave: mudou o geral, a tabela recomeça dele.
        kt = f"pml_t_{ck}_{pct_todas}"
        ed = (st.session_state.get(kt) or {}).get("edited_rows", {}) if hasattr(
            st.session_state, "get") else {}
        editados = {int(i): v["Desconto %"] for i, v in ed.items()
                    if isinstance(v, dict) and v.get("Desconto %") is not None}
        estoques = {int(i): int(v["Estoque"]) for i, v in ed.items()
                    if isinstance(v, dict) and v.get("Estoque") is not None}
        desm = {int(i) for i, v in ed.items()
                if isinstance(v, dict) and v.get("Entrar") is False}
        linhas, pedidos = linhas_da_caixa(cx, pct_todas, editados, estoques, desm)
        df = pd.DataFrame(linhas)
        if not com_est:
            df = df.drop(columns=["Estoque"])
        cc = st.column_config
        st.data_editor(
            df, key=kt, hide_index=True, use_container_width=True,
            disabled=[c for c in df.columns if c not in ("Entrar", "Desconto %", "Estoque")]
            + ([] if edit else ["Desconto %"]),
            column_config={
                "Entrar": cc.CheckboxColumn("", width="small"),
                "Conta": cc.TextColumn(width="small"),
                "Desconto %": cc.NumberColumn(format="%.1f%%", min_value=0.0,
                                              max_value=99.0, step=0.5),
                "Estoque": cc.NumberColumn(min_value=1, step=1, width="small"),
                "No bolso": cc.TextColumn(width="small",
                                          help="O que sai do seu bolso: o desconto menos o "
                                               "que o ML banca e devolve na tarifa."),
                "Faixa do ML / aviso": cc.TextColumn(width="large")})
        faltam = [c.upper() for c in _ml.CONTAS
                  if c in pr["anuncios"] and c not in cx["contas"]]
        if faltam:
            st.caption(f"Sem esta promoção em: {', '.join(faltam)}")
        with h3:
            _confirmar(f"in_{ck}", pedidos, f"Participar nas {len(pedidos)} marcadas")


def _aba_andamento(dados):
    and_ = dados["andamento"]
    if not and_:
        st.info("Nenhum anúncio em promoção agora.")
        return
    import pandas as pd
    st.dataframe(pd.DataFrame([{
        "Produto": o["titulo"], "Conta": o["conta"].upper(), "Promoção": o["nome"],
        "Situação": "programada" if o["status"] == "pending" else "no ar",
        "Preço cheio": _brl(preco_hoje(o)), "Na promoção": _brl(o.get("price")),
        "Desconto": f"{pct_de(preco_hoje(o), float(o.get('price') or 0)):.1f}%",
        "Termina": _data(o.get("fim"))} for o in and_]),
        use_container_width=True, hide_index=True)
    rot = {f"{o['titulo'][:60]} · {o['conta'].upper()} · {o['nome']}": o for o in and_}
    esc = st.selectbox("Tirar da promoção", ["—"] + list(rot), key="pml_sair_sel")
    if esc != "—":
        o = rot[esc]
        cam, par = pedido_de_saida(o)
        _confirmar(f"out_{ident(o['conta'], o['item'], o['tipo'], o['promo_id'])}",
                   [(o["conta"], o["item"], "DELETE", cam, par, None)], "Sair desta promoção")


def _escolher_produto(dados, chave):
    prods = dados["produtos"]
    busca = st.text_input("Buscar produto pelo título", key=f"pml_q_{chave}")
    if busca:
        prods = [p for p in prods if normalizar(busca) in p["chave"]]
    if not prods:
        st.info("Nenhum produto com promoção aberta para essa busca.")
        return None
    rot = {f"{p['titulo'][:80]} · {len(p['anuncios'])} conta(s) · "
           f"{len(p['promocoes'])} promoção(ões)": p for p in prods[:300]}
    if len(prods) > 300:
        st.caption(f"Mostrando 300 de {len(prods)} — refine a busca.")
    return rot[st.selectbox("Produto", list(rot), key=f"pml_sel_{chave}")]


def _aba_disponiveis(dados):
    pr = _escolher_produto(dados, "disp")
    if not pr:
        return
    ns = ", ".join(f"{c.upper()} {', '.join(i)}" for c, i in sorted(pr["anuncios"].items()))
    st.markdown(f"#### {pr['titulo']}")
    st.caption(f"{ns} · {len(pr['promocoes'])} promoção(ões) abertas")
    for cx in pr["promocoes"]:
        _caixa(pr, cx)


def _aba_criar(dados, hoje):
    st.caption("O desconto do vendedor (PRICE_DISCOUNT): de 5% a 80%, até 14 dias, "
               "o mesmo produto em todas as contas de uma vez — cada conta com o seu %.")
    pr = _escolher_produto(dados, "criar")
    if not pr:
        return
    c1, c2, c3 = st.columns(3)
    pct_geral = c1.number_input("Desconto %", 5.0, 80.0, 10.0, 1.0, key="pml_cr_pct")
    ini = c2.date_input("De", hoje, key="pml_cr_ini", format="DD/MM/YYYY")
    fim = c3.date_input("Até", hoje + timedelta(days=DIAS_MAX - 1), key="pml_cr_fim",
                        format="DD/MM/YYYY")
    erro_d = datas_validas(ini, fim, hoje)
    if erro_d:
        st.error(erro_d)
    chave = f"cr_{pr['chave']}"
    if st.session_state.get("pml_cr_chave") != chave:
        # A faixa do ML vem de uma leitura por anúncio: só ao escolher o
        # produto, e guardada, nunca a cada tecla.
        faixas = {}
        for conta, itens in pr["anuncios"].items():
            for it in itens:
                faixas[(conta, it)] = faixa_do_desconto(conta, it)
        st.session_state["pml_cr_faixas"] = faixas
        st.session_state["pml_cr_chave"] = chave
    faixas = st.session_state["pml_cr_faixas"]
    pedidos = []
    for (conta, it), (of, err) in sorted(faixas.items()):
        k = ident(chave, conta, it)
        c = st.columns([0.4, 0.6, 1.9, 1.1, 1.0, 1.2, 2.4])
        if err:
            c[1].markdown(f"**{conta.upper()}**")
            c[2].markdown(it)
            c[6].markdown(f":red[{err}]")
            continue
        marcado = c[0].checkbox("marcar", True, key=f"pml_crc_{k}",
                                label_visibility="collapsed")
        c[1].markdown(f"**{conta.upper()}**")
        c[2].markdown(it)
        c[3].markdown(_md(preco_hoje(of)))
        pct = c[4].number_input("%", 5.0, 80.0, float(pct_geral), 1.0, format="%.1f",
                                key=f"pml_crp_{k}_{pct_geral}",
                                label_visibility="collapsed")
        preco, erro = validar(of, pct)
        c[5].markdown(f"**{_md(preco)}**" if preco else "—")
        erro_md = erro.replace("$", "\\$")
        c[6].markdown(f":red[{erro_md}]" if erro else
                      f"{_md(of.get('min_discounted_price'))} – {_md(of.get('max_discounted_price'))}")
        if marcado and not erro and not erro_d:
            cam, par, corpo = pedido_de_entrada(of, preco, inicio=ini.isoformat(),
                                                fim=fim.isoformat())
            pedidos.append((conta, it, "POST", cam, par, corpo))
    _confirmar(chave, pedidos, f"Aplicar nas {len(pedidos)} marcadas")


def pagina(usuario_logado=None):
    import auth
    import placar_core as _pc
    if not auth.eh_dono(usuario_logado):
        st.error("Acesso restrito ao dono do Studio: esta tela muda preço no Mercado Livre.")
        return
    st.markdown("### 🏷️ Promoções — Mercado Livre")
    _resultado()
    dados = st.session_state.get("pml_dados")
    rotulo = "🔄 Ler as promoções das 4 contas" if not dados else "🔄 Ler de novo"
    if st.session_state.get("pml_desatualizado"):
        st.warning("Houve mudança no Mercado Livre depois da última leitura — leia de novo "
                   "para ver a situação atual.")
    if st.button(rotulo, key="pml_ler"):
        with st.spinner("Lendo as promoções e os anúncios das 4 contas…"):
            lidas = ler_todas()
        st.session_state["pml_dados"] = dados = {
            "lidas": {c: {"promocoes": v["promocoes"], "ofertas": len(v["ofertas"]),
                          "avisos": v["avisos"]} for c, v in lidas.items()},
            **agrupar(lidas), "quando": _pc.agora_br().strftime("%d/%m %H:%M")}
        st.session_state.pop("pml_desatualizado", None)
        st.session_state.pop("pml_cr_chave", None)
    if not dados:
        st.caption("A leitura leva alguns segundos: são todas as páginas de anúncios de "
                   "todas as promoções das quatro contas.")
        return
    resumo = " · ".join(f"{c.upper()} {v['promocoes']} promoções, {v['ofertas']} ofertas"
                        for c, v in sorted(dados["lidas"].items()))
    st.caption(f"Lido às {dados['quando']} · {resumo}")
    for c, v in sorted(dados["lidas"].items()):
        for a in v["avisos"]:
            st.warning(f"{c.upper()}: {a}")
    import promocoes_auto as _pa
    vistos = _vistos_guardados()
    fins = _pa.finalizadas(vistos)
    t1, t2, t3, t4, t5 = st.tabs([f"🟢 Em andamento ({len(dados['andamento'])})",
                                  f"📨 Disponíveis para participar ({len(dados['produtos'])} produtos)",
                                  "➕ Criar desconto %",
                                  f"🔁 Finalizadas sem recriar ({len(fins)})",
                                  "⚙️ Automático"])
    with t1:
        _aba_andamento(dados)
    with t2:
        _aba_disponiveis(dados)
    with t3:
        _aba_criar(dados, _pc.agora_br().date())
    with t4:
        _aba_finalizadas(fins)
    with t5:
        _aba_automatico(_pc.agora_br())


# ── As abas do automático (28/10) ─────────────────────────────────────────────
# A planilha é lida uma vez a cada 5 minutos, e não a cada tecla: as abas do
# `st.tabs` se desenham todas em toda passada.
@st.cache_data(ttl=300, show_spinner=False)
def _vistos_guardados():
    import promocoes_auto as _pa
    return _pa.carregar_vistos()


@st.cache_data(ttl=300, show_spinner=False)
def _regras_guardadas():
    import promocoes_auto as _pa
    return _pa.carregar_regras()


@st.cache_data(ttl=300, show_spinner=False)
def _log_guardado():
    import promocoes_auto as _pa
    return _pa.carregar_log()


@st.cache_data(ttl=300, show_spinner=False)
def _estado_guardado():
    import promocoes_auto as _pa
    return _pa.estado()


def _aba_finalizadas(fins):
    st.caption("Anúncios que estavam em promoção e saíram de todas. A lista começa no dia "
               "em que a rotina diária passou a rodar — o ML só mostra o que está ativo.")
    if not fins:
        st.info("Nenhum anúncio saiu de promoção sem voltar.")
        return
    import pandas as pd
    st.dataframe(pd.DataFrame([{
        "Produto": v.get("titulo", ""), "Conta": str(v.get("conta", "")).upper(),
        "Anúncio": v.get("item", ""), "Última promoção": v.get("promocao", ""),
        "Terminava": _data(v.get("fim")), "Saiu em": _data(v.get("saiu_em"))}
        for v in fins]), use_container_width=True, hide_index=True)
    st.caption("Desconto do vendedor se recria na aba ➕ ou sozinho, pela lista do ⚙️ "
               "Automático. Campanha do ML não se recria: ela volta quando o ML convidar.")


def _aba_automatico(agora):
    import promocoes_auto as _pa
    est = _estado_guardado()
    real = est.get("modo") == "ligado"
    st.markdown(f"**Modo: {'🟢 LIGADO — grava no Mercado Livre' if real else '🟡 SIMULAÇÃO — só registra o que faria'}**"
                f" · última rodada: {est.get('ultimo_dia') or 'nenhuma ainda'} "
                f"(uma por dia, depois das {_pa.HORA_DA_RODADA}h)")
    if st.session_state.get("pml_modo_armado"):
        st.warning("Confirma? " + ("Volta a só simular." if real else
                   "A partir da próxima rodada o Studio ENTRA e RECRIA promoções sozinho."))
        c1, c2 = st.columns(2)
        if c1.button("✅ Confirmar", key="pml_modo_sim", type="primary"):
            _pa.gravar_estado(dict(est, modo="simulacao" if real else "ligado"))
            _estado_guardado.clear()
            st.session_state.pop("pml_modo_armado", None)
            st.rerun()
        if c2.button("Cancelar", key="pml_modo_nao"):
            st.session_state.pop("pml_modo_armado", None)
            st.rerun()
    elif st.button("Voltar para simulação" if real else "Ligar o modo real", key="pml_modo"):
        st.session_state["pml_modo_armado"] = True
        st.rerun()

    st.markdown("##### A lista")
    st.caption("Uma linha por produto, pelo título (junta as 4 contas). % máximo: entra nos "
               "convites com até esse % no bolso. Recriar %: o desconto do vendedor que volta "
               "quando expira (até 14 dias). Estoque relâmpago: sem ele, o relâmpago fica de fora.")
    import pandas as pd
    linhas = _regras_guardadas() or []
    df = pd.DataFrame(linhas or [{c: "" for c in _pa.COLUNAS_REGRAS}],
                      columns=_pa.COLUNAS_REGRAS)
    ed = st.data_editor(df, num_rows="dynamic", use_container_width=True, hide_index=True,
                        key="pml_regras_ed")
    if st.button("💾 Salvar a lista", key="pml_regras_salvar"):
        _pa.gravar_regras(ed.fillna("").to_dict("records"))
        _regras_guardadas.clear()
        st.success("Lista salva. Vale a partir da próxima rodada.")

    st.markdown("##### O que a rotina fez")
    lg = _log_guardado()
    if lg:
        st.dataframe(pd.DataFrame(lg), use_container_width=True, hide_index=True)
    else:
        st.caption("Nenhuma rodada registrada ainda.")


if __name__ == "__main__":
    import json as _json
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # PELA CADEIA, com a FORMA DA AMOSTRA REAL da ML1 (28/10 12:26): a rede é
    # dublada devolvendo as respostas que o ML devolveu de verdade — lista de
    # promoções, páginas com `paging.searchAfter`, `/items?ids=` no formato
    # code/body. O mesmo produto em duas contas com o título grafado diferente.
    _cav = "Escultura E Porta Caneta Cavaleiro Medieval Em Resina Dourado-escuro"
    _rede = {
        ("ml1", "/seller-promotions/users/1"): {"results": [
            {"id": "P-MLB17909028", "type": "DEAL", "status": "started",
             "finish_date": "2026-11-12T03:00:00Z", "deadline_date": "2026-11-12T02:00:00Z",
             "name": "11.11 da Black"},
            {"id": "P-MLB17937078", "type": "SMART", "status": "started",
             "name": "Impulsione suas vendas"},
            {"id": "LGH-MLB1000", "type": "LIGHTNING", "status": "started"},
            {"id": "P-VELHA", "type": "DEAL", "status": "finished", "name": "Velha"}],
            "paging": {"total": 4}},
        ("ml2", "/seller-promotions/users/2"): {"results": [
            {"id": "P-MLB17909028", "type": "DEAL", "status": "started", "name": "11.11 da Black"}]},
    }
    _paginas = {
        ("ml1", "P-MLB17909028", None): {"results": [
            {"id": "MLB7699295012", "status": "candidate", "original_price": 134.99,
             "min_discounted_price": 27, "max_discounted_price": 130.94,
             "suggested_discounted_price": 117.44}],
            "paging": {"total": 2, "limit": 50, "searchAfter": "abc"}},
        ("ml1", "P-MLB17909028", "abc"): {"results": [
            {"id": "MLB3888083486", "status": "started", "price": 142.49,
             "original_price": 149.99}], "paging": {"total": 2, "limit": 50}},
        ("ml1", "P-MLB17937078", None): {"results": [
            {"id": "MLB7699295012", "status": "candidate", "price": 130.94,
             "original_price": 134.99, "offer_id": "CANDIDATE-MLB7699295012-77636538721",
             "meli_percentage": 0.5, "seller_percentage": 2.5, "boosted_offer": True,
             "discount_meli_boost_amount": 1.35, "total_price_for_boosted_offer": 129.59}],
            "paging": {"total": 1}},
        ("ml1", "LGH-MLB1000", None): {"results": [
            {"id": "MLB7699295012", "ref_id": "CANDIDATE-MLB7699295012-77636143971",
             "status": "candidate", "price": 130.94, "original_price": 134.99,
             "min_discounted_price": 29.99, "stock": {"min": 5, "max": 98}}],
            "paging": {"total": 1}},
        ("ml2", "P-MLB17909028", None): {"results": [
            {"id": "MLB222", "status": "candidate", "original_price": 139.99,
             "min_discounted_price": 28, "max_discounted_price": 135.79,
             "suggested_discounted_price": 121.79}], "paging": {"total": 1}},
    }
    _tit = {"MLB7699295012": _cav, "MLB3888083486": "Outro produto",
            "MLB222": "escultura e porta caneta cavaleiro medieval em resina  DOURADO-ESCURO"}
    _pedidos_vistos = []

    def _req(metodo, conta, tok, caminho, params=None, corpo=None):
        _pedidos_vistos.append((conta, caminho, dict(params or {})))
        if caminho == "/items":
            ids = params["ids"].split(",")
            return ([{"code": 200, "body": {"id": i, "title": _tit[i], "thumbnail": ""}}
                     for i in ids], "")
        if caminho.endswith("/items"):
            pid = caminho.split("/")[3]
            assert params["promotion_type"] and params["app_version"] == "v2"
            return (_paginas[(conta, pid, params.get("search_after"))], "")
        return (_rede[(conta, caminho)], "")

    _l1 = ler_conta("ml1", "T", "1", _req)
    _l2 = ler_conta("ml2", "T", "2", _req)
    ok("leitura: segue a página seguinte pelo search_after que o ML devolveu",
       any(p.get("search_after") == "abc" for _, _, p in _pedidos_vistos)
       and len(_l1["ofertas"]) == 4)
    ok("leitura: promoção encerrada não é lida", not any("P-VELHA" in c for _, c, _ in _pedidos_vistos))
    ok("leitura: o título vem do /items?ids=, não da lista da promoção",
       _l1["titulos"]["MLB7699295012"]["title"] == _cav)
    _g = agrupar({"ml1": _l1, "ml2": _l2})
    _pr = [p for p in _g["produtos"] if p["chave"] == normalizar(_cav)]
    ok("título com caixa e espaço diferentes é o MESMO produto nas duas contas",
       len(_pr) == 1 and set(_pr[0]["anuncios"]) == {"ml1", "ml2"})
    _cx = {c["tipo"]: c for c in _pr[0]["promocoes"]}
    ok("a 11.11 das duas contas vira UMA caixa com uma linha por conta, e vem primeiro",
       _pr[0]["promocoes"][0]["tipo"] == "DEAL"
       and [l["conta"] for l in _cx["DEAL"]["linhas"]] == ["ml1", "ml2"])
    ok("promoção que só existe na ML1 aparece só com a ML1",
       _cx["SMART"]["contas"] == ["ml1"] and _cx["LIGHTNING"]["contas"] == ["ml1"])
    ok("o que já está no ar vai para Em andamento, não para Disponíveis",
       [o["item"] for o in _g["andamento"]] == ["MLB3888083486"])
    ok("o reembolso da tarifa (boost) atravessa a leitura até a linha da caixa",
       _cx["SMART"]["linhas"][0].get("discount_meli_boost_amount") == 1.35
       and _cx["SMART"]["linhas"][0].get("total_price_for_boosted_offer") == 129.59)
    ok("a promoção que o ML define não é editável; a campanha e o relâmpago são",
       not _cx["SMART"]["editavel"] and _cx["DEAL"]["editavel"] and _cx["LIGHTNING"]["editavel"])
    _d1, _d2 = _cx["DEAL"]["linhas"]
    ok("o % sugerido sai do preço sugerido do ML (117,44 de 134,99 = 13%)",
       pct_sugerido(_d1) == 13.0)
    ok("cada conta com o seu %: 13% na ML1 e 15% na ML2 dão preços próprios",
       validar(_d1, 13) == (117.44, "") and validar(_d2, 15) == (118.99, ""))
    ok("% fora da faixa do ML é barrado antes de enviar, com o motivo",
       "mínimo" in validar(_d1, 90)[1] and "máximo" in validar(_d1, 1)[1])
    _lg = _cx["LIGHTNING"]["linhas"][0]
    ok("relâmpago exige estoque dentro da faixa do ML",
       "estoque mínimo" in validar(_lg, 15, 2)[1] and validar(_lg, 15, 10)[1] == "")
    ok("entrar na campanha: promotion_id + deal_price (documentação do ML)",
       pedido_de_entrada(_d1, 117.44) == (
           "/seller-promotions/items/MLB7699295012", {"app_version": "v2"},
           {"promotion_type": "DEAL", "promotion_id": "P-MLB17909028", "deal_price": 117.44}))
    ok("entrar no relâmpago: deal_price + stock",
       pedido_de_entrada(_lg, 114.75, 10)[2] == {"promotion_type": "LIGHTNING",
                                                  "deal_price": 114.75, "stock": 10})
    _sm = _cx["SMART"]["linhas"][0]
    ok("entrar na automática: o offer_id que o ML mandou, sem preço",
       pedido_de_entrada(_sm)[2] == {"promotion_type": "SMART", "promotion_id": "P-MLB17937078",
                                     "offer_id": "CANDIDATE-MLB7699295012-77636538721"})
    ok("sair: promotion_type, promotion_id e offer_id quando a promoção tem",
       pedido_de_saida(_sm)[1] == {"promotion_type": "SMART", "app_version": "v2",
                                   "promotion_id": "P-MLB17937078",
                                   "offer_id": "CANDIDATE-MLB7699295012-77636538721"}
       and pedido_de_saida(_lg)[1] == {"promotion_type": "LIGHTNING", "app_version": "v2"})
    _pd = {"tipo": "PRICE_DISCOUNT", "item": "MLB1", "original_price": 134.99,
           "min_discounted_price": 54, "max_discounted_price": 128.24, "promo_id": ""}
    ok("desconto do vendedor: 10% entra, 70% passa do mínimo do ML",
       validar(_pd, 10) == (121.49, "") and validar(_pd, 70)[1].startswith("abaixo"))
    ok("desconto do vendedor: datas no formato da documentação",
       pedido_de_entrada(_pd, 121.49, inicio="2026-10-28", fim="2026-11-10")[2]
       == {"promotion_type": "PRICE_DISCOUNT", "deal_price": 121.49,
           "start_date": "2026-10-28T00:00:00", "finish_date": "2026-11-10T00:00:00"})
    _h = date(2026, 10, 28)
    ok("datas: no máximo 14 dias, sem começar no passado",
       datas_validas(_h, _h + timedelta(days=13), _h) == ""
       and "14" in datas_validas(_h, _h + timedelta(days=14), _h)
       and datas_validas(_h - timedelta(days=1), _h, _h) != "")

    # LIMITE CALADO NÃO: a lista cortada diz que foi cortada.
    _sempre = lambda m, c, t, cam, p=None, corpo=None: (
        {"results": [{"id": "X", "status": "candidate"}],
         "paging": {"total": 99999, "searchAfter": "s"}}, "")
    _of, _av = ofertas_da_promocao("ml1", "T", {"id": "P", "type": "DEAL", "name": "Grande"}, _sempre)
    ok(f"lista maior que o teto avisa quantas leu de quantas ({_av})",
       len(_of) == PAGINAS_MAX and "99999" in _av)
    _cai = lambda m, c, t, cam, p=None, corpo=None: (None, "Mercado Livre respondeu 500: x")
    ok("falha no meio da leitura vira aviso, não some",
       "500" in ofertas_da_promocao("ml1", "T", {"id": "P", "type": "DEAL"}, _cai)[1])

    # A THREAD NÃO TOCA NO session_state (a Forma 6 desta base): a leitura em
    # paralelo roda numa thread de verdade e tem de devolver o mesmo dado.
    import threading as _th
    _box = {}
    _t = _th.Thread(target=lambda: _box.update(r=ler_conta("ml2", "T", "2", _req)))
    _t.start()
    _t.join()
    ok("ler_conta numa Thread de verdade devolve as ofertas",
       len(_box["r"]["ofertas"]) == 1 and _box["r"]["titulos"])
    import ast as _ast_p
    import inspect as _insp_p
    # Por AST, e não por texto: a docstring que proíbe não pode se acusar.
    _nos_t = [n for f in (ler_conta, ofertas_da_promocao, titulos)
              for n in _ast_p.walk(_ast_p.parse(_insp_p.getsource(f)))]
    ok("o que roda na thread não lê session_state nem busca token",
       not any(isinstance(n, _ast_p.Attribute) and n.attr == "session_state" for n in _nos_t)
       and not any(isinstance(n, _ast_p.Call) and (getattr(n.func, "attr", "") == "token"
                                                   or getattr(n.func, "id", "") == "token")
                   for n in _nos_t))
    ok("toda escrita passa pela confirmação (_executar só é chamado por _confirmar)",
       sum(1 for n in _ast_p.walk(_ast_p.parse(open(__file__, encoding="utf-8").read()))
           if isinstance(n, _ast_p.Call) and getattr(n.func, "id", "") == "_executar") == 1
       and "_executar(" in _insp_p.getsource(_confirmar))
    # A TABELA DA CAIXA (28/10): o % digitado numa linha vence o "% para
    # todas", que vence o sugerido; linha desmarcada não vira pedido.
    _cx_t = _cx["DEAL"]
    _lin, _ped = linhas_da_caixa(_cx_t)
    ok("tabela: sem nada digitado, cada conta com o sugerido dela",
       [r["Desconto %"] for r in _lin] == [13.0, 13.0] and len(_ped) == 2)
    _lin, _ped = linhas_da_caixa(_cx_t, pct_todas=10.0, editados={1: 15.0}, desmarcados={0})
    ok("tabela: o % da linha vence o geral, e a desmarcada fica de fora dos pedidos",
       [r["Desconto %"] for r in _lin] == [10.0, 15.0]
       and [p[0] for p in _ped] == ["ml2"] and _ped[0][5]["deal_price"] == 118.99)
    _lin, _ped = linhas_da_caixa(_cx_t, pct_todas=95.0)
    ok("tabela: % fora da faixa do ML vira aviso na linha e não vira pedido",
       all(r["Faixa do ML / aviso"].startswith("⚠️") for r in _lin) and not _ped)
    ok("preco_hoje: a DEAL candidata vem com price 0, e vale o original_price",
       preco_hoje({"price": 0, "original_price": 98.65}) == 98.65
       and preco_hoje({"price": 34.44}) == 34.44 and preco_hoje({}) == 0.0)
    # ler_todas: o token é buscado FORA da thread, e conta sem autorização vira
    # aviso em vez de derrubar as outras.
    _g_lt = (_ml.token, _ml._ler_da_planilha, globals()["ler_conta"])
    _quem_pediu_token = []
    try:
        _ml._ler_da_planilha = lambda c: {"user_id": "" if c == "ml4" else "9"}
        _ml.token = lambda c: (_quem_pediu_token.append(_th.current_thread().name), ("T", ""))[1]
        globals()["ler_conta"] = lambda c, t, u, req=None: {"ofertas": [1], "titulos": {},
                                                            "avisos": [], "promocoes": 1}
        _lt = ler_todas()
    finally:
        _ml.token, _ml._ler_da_planilha, globals()["ler_conta"] = _g_lt
    ok("ler_todas: lê as autorizadas, a sem autorização vira aviso, token na thread da tela",
       sorted(_lt) == list(_ml.CONTAS) and _lt["ml4"]["avisos"]
       and _lt["ml1"]["ofertas"] == [1]
       and set(_quem_pediu_token) == {_th.main_thread().name})

    print("\nfalhas:", falhas)
    raise SystemExit(1 if falhas else 0)
