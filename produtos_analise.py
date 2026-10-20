"""produtos_analise.py — Gestão › Produtos: o analista de produtos do dono.

O QUE ELE RESPONDE (dono, 20/10)
--------------------------------
"Me mostrar basicamente o que está dando certo e o que está dando errado."
Vocês sabem pelos pacotes o que SAI; esta página mostra o que RENDE:

* quem paga o custo fixo e deixa lucro (UC), no ano, semestre, trimestre e mês;
* a posição de cada produto nos quatro recortes, lado a lado (busca por código);
* o que puxa a UC média para baixo e para cima;
* o que precisa de atenção imediata no mês, o que está lucrando forte e os
  produtos NOVOS que já nasceram bem;
* o panorama completo de um produto: plataforma, período, para onde vai o preço.

DE ONDE VEM CADA NÚMERO
-----------------------
Uma linha da BASE DE VENDAS 2026 por venda. Margem, custo, comissão, frete, NF,
devolução e C.O. vêm da planilha (são digitados/calculados lá). O LPV de cada
venda é o do MÊS DELA — `lpv_mensal.lpv_do_ano`, a mesma conta do Financeiro;
mês que o Studio não consegue calcular cai na coluna LPV da própria planilha,
e a tela diz quais meses vieram de onde.

    UC por venda = margem de contribuição ÷ LPV consumido   (razão das SOMAS)
    UC total     = soma da UC de cada venda — quanto custo fixo o produto pagou
    Lucro        = margem − LPV de cada venda

O QUE ELE AINDA NÃO FAZ (dito em voz alta)
------------------------------------------
* O produto é o TÍTULO normalizado. O mesmo produto anunciado com títulos
  diferentes ainda aparece separado — o SKU não serve para juntar, porque o
  SKU é o custo e produtos diferentes dividem o mesmo (MS-3800: bengala,
  xadrez, furador). Juntar por IA + confirmação do dono é a próxima etapa, e o
  código do produto (P…) passa a ser do produto juntado.
* Nicho, C.O. previsto do mês e gravação na DIN FINANÇAS: etapas seguintes.
"""

import collections
import hashlib
import statistics
import unicodedata
from datetime import date

import streamlit as st

# ── Regras do dono (20/10). Um lugar só: a tela, os alertas e o teste leem daqui.
UC_CRITICA = 0.7          # "atenção imediata"
UC_DESTAQUE = 2.0         # "lucrando forte"
PEDIDOS_RELEVANTES = 10   # no mês, para entrar nos alertas
UC_RUIM = 0.8             # "dando errado" e o 4º número do topo
PEDIDOS_ERRADO = 20       # no período, para entrar em "dando errado"
PONTUAL_X = 4             # pedido com 4× a quantidade normal = venda pontual
DIAS_NOVO = 60            # primeira venda há até 60 dias = produto novo
BAIXA_SAIDA = 3           # vendeu 3 vezes ou menos no período
MIN_VENDAS_CONTA = 3      # produto com menos vendas não entra nas contagens
RECORRENTE_FRACAO = 0.85  # "dando certo": vendeu em 85% dos meses desde o início
RECORRENTE_PEDIDOS = 5    # … e 5+ pedidos por mês

FAIXAS = (("abaixo de 0,8", "não paga o custo fixo", 0.0, 0.8, "VERMELHO"),
          ("0,8 a 1,0", "no limite", 0.8, 1.0, "AMBAR"),
          ("1,0 a 1,5", "paga", 1.0, 1.5, "#8FCB9B"),
          ("1,5 a 2,0", "bom", 1.5, 2.0, "#5DBB85"),
          ("2,0 ou mais", "excelente", 2.0, 1e9, "VERDE"))

PERIODOS = ("Ano", "Semestre", "Trimestre", "Mês")
MES_CURTO = ("jan", "fev", "mar", "abr", "mai", "jun",
             "jul", "ago", "set", "out", "nov", "dez")

# As colunas da BASE DE VENDAS que esta página lê, pela chave sem acento de
# `base_vendas._chave` — a mesma tolerância a "Margem C. " digitado à mão.
CAMPOS = {"data": "data", "mes/ano": "mes_ano", "plataforma": "plataforma",
          "sku": "sku", "produto": "produto", "quantidade": "q",
          "fat total": "fat", "custo total": "ct", "comissao": "com",
          "frete": "fr", "nf": "nf", "custo op": "co", "devolucao": "dev",
          "margem c": "mc", "custo flex": "cflex", "lpv": "lpv_planilha",
          "custo unitario": "custo_un"}


# ── LEITURA ─────────────────────────────────────────────────────────────────

def norm_titulo(t):
    """O título como chave: espaços colapsados e caixa alta."""
    return " ".join(str(t or "").split()).upper()


def codigo(produto):
    """Código curto e FIXO do produto (P + 5 hex do título normalizado).

    Fixo porque sai do próprio nome, e não da posição numa lista que muda a
    cada venda nova: o código que o dono anota hoje acha o mesmo produto
    amanhã.
    """
    h = hashlib.sha1(norm_titulo(produto).encode("utf-8")).hexdigest()
    return "P" + h[:5].upper()


def _mapa(colunas):
    import base_vendas as _bv
    fora = {}
    for c in colunas:
        k = CAMPOS.get(_bv._chave(c))
        if k and k not in fora:
            fora[k] = c
    return fora


def linhas_da_base(registros, colunas, lpv_mes, ano):
    """[venda] do ANO, com o LPV do mês de cada uma. Pura.

    `registros`: as linhas como `controle_ms.ler(...).to_dict("records")`.
    `lpv_mes`: {mes: lpv} do Studio; mês fora dele usa a coluna LPV da linha.
    Venda sem faturamento ou sem margem fica de fora (não é venda medível).
    """
    import base_vendas as _bv
    import home_gestao as _hg
    m = _mapa(colunas)
    col_data, col_ma = m.get("data"), m.get("mes_ano")
    fora = []
    for r in (registros or []):
        a, mes = _bv._mes_da_linha(r, col_data, col_ma)
        if a != ano:
            continue
        g = lambda k: r.get(m[k]) if k in m else None
        fat = _bv._num(g("fat"))
        if fat <= 0 or not m.get("mc") or g("mc") in (None, ""):
            continue
        lpv = lpv_mes.get(mes)
        fonte = "studio"
        if not lpv:
            lpv, fonte = _bv._num(g("lpv_planilha")), "planilha"
        d = g("data")
        fora.append({
            "mes": mes, "dia": d.date() if hasattr(d, "date") else None,
            "produto": norm_titulo(g("produto")), "sku": str(g("sku") or "").strip(),
            "plataforma": _hg.plataforma_do_canal(g("plataforma")),
            "q": _bv._num(g("q"), 1.0) or 1.0, "fat": fat, "mc": _bv._num(g("mc")),
            "ct": _bv._num(g("ct")), "com": _bv._num(g("com")),
            "fr": _bv._num(g("fr")) + _bv._num(g("cflex")), "nf": _bv._num(g("nf")),
            "co": _bv._num(g("co")), "dev": _bv._num(g("dev")),
            "custo_un": _bv._num(g("custo_un")),
            "lpv": lpv if lpv and lpv > 0 else None, "fonte_lpv": fonte})
    return fora


def lpv_por_mes(ano, hoje):
    """{mes: lpv} do Studio, e o mês corrente pela projeção de vendas."""
    import lpv_mensal as _lm
    fora = {}
    try:
        meses, _ = _lm.lpv_do_ano(ano)
        fora = {m: r["lpv"] for m, r in (meses or {}).items() if r.get("lpv")}
        if ano == hoje.year and hoje.month not in fora:
            p = _lm.lpv_projetado(ano, hoje.month)
            if p and p.get("lpv"):
                fora[hoje.month] = p["lpv"]
    except Exception:
        pass
    return fora


@st.cache_data(ttl=600, show_spinner=False)
def dados(ano, hoje):
    """(linhas, erro). Uma leitura da BASE por 10 min — a mesma de `base_vendas`."""
    try:
        import controle_ms as _cms
        import base_vendas as _bv
        df, erro = _cms.ler(_bv.ABA)
        if erro:
            return [], erro
        if df is None or df.empty:
            return [], f"A aba «{_bv.ABA}» veio vazia."
        return linhas_da_base(df.to_dict("records"), list(df.columns),
                              lpv_por_mes(ano, hoje), ano), ""
    except Exception as e:
        return [], f"Não consegui ler a BASE DE VENDAS: {type(e).__name__}: {str(e)[:160]}"


# ── CONTAS (puras) ──────────────────────────────────────────────────────────

def medianas_de_quantidade(linhas):
    q = collections.defaultdict(list)
    for x in linhas:
        q[x["produto"]].append(x["q"])
    return {k: statistics.median(v) for k, v in q.items()}


def eh_pontual(x, med):
    """Pedido com 4× ou mais a quantidade normal do produto (e 4+ peças).

    É o kit de 30 maletas: não é venda recorrente e não pode decidir ranking.
    Sai da conta e aparece à parte.
    """
    return x["q"] >= max(PONTUAL_X * med.get(x["produto"], 1.0), PONTUAL_X)


def primeiras_vendas(linhas):
    fora = {}
    for x in linhas:
        d = x["dia"] or date(2000, x["mes"], 1)
        if x["produto"] not in fora or d < fora[x["produto"]]:
            fora[x["produto"]] = d
    return fora


def agregar(linhas, meses, plataforma=None, med=None):
    """{produto: números} das vendas desses meses (e plataforma). Pura.

    Venda sem LPV conta no faturamento, mas não na UC — UC sem LPV é número
    inventado.
    """
    med = med if med is not None else medianas_de_quantidade(linhas)
    P = {}
    for x in linhas:
        if x["mes"] not in meses or (plataforma and x["plataforma"] != plataforma):
            continue
        p = P.get(x["produto"])
        if p is None:
            p = P[x["produto"]] = {
                "v": 0, "fat": 0.0, "mc": 0.0, "lpv": 0.0, "co": 0.0, "ct": 0.0,
                "com": 0.0, "fr": 0.0, "nf": 0.0, "dev": 0.0, "q": 0.0,
                "uc_pontual": 0.0, "mes": collections.Counter(),
                "plat": collections.Counter(), "sku": collections.Counter(),
                "custo_un": []}
        if not x["lpv"]:
            continue
        if eh_pontual(x, med):
            p["uc_pontual"] += x["mc"] / x["lpv"]
            continue
        p["v"] += 1
        for k in ("fat", "mc", "lpv", "co", "ct", "com", "fr", "nf", "dev", "q"):
            p[k] += x[k]
        p["mes"][x["mes"]] += 1
        p["plat"][x["plataforma"]] += 1
        p["sku"][x["sku"]] += 1
        if x["custo_un"]:
            p["custo_un"].append(x["custo_un"])
    for k in [k for k, p in P.items() if p["v"] == 0]:
        del P[k]
    for p in P.values():
        p["ucv"] = p["mc"] / p["lpv"] if p["lpv"] else 0.0
        p["uct"] = p["ucv"] * p["v"]
        p["lucro"] = p["mc"] - p["lpv"]
    return P


def ranking(P):
    """[(produto, números)] pela UC total — quem mais pagou custo fixo."""
    return sorted(P.items(), key=lambda kv: (-kv[1]["uct"], kv[0]))


def uc_media(P):
    mc = sum(p["mc"] for p in P.values())
    lpv = sum(p["lpv"] for p in P.values())
    return mc / lpv if lpv else 0.0


def impacto_na_media(P):
    """{produto: quanto a UC média MUDA por causa dele}. + puxa para cima."""
    MC = sum(p["mc"] for p in P.values())
    L = sum(p["lpv"] for p in P.values())
    if not L:
        return {}
    media = MC / L
    fora = {}
    for k, p in P.items():
        resto = L - p["lpv"]
        fora[k] = media - ((MC - p["mc"]) / resto) if resto > 0 else 0.0
    return fora


def faixa_de(uc):
    for i, f in enumerate(FAIXAS):
        if f[2] <= uc < f[3]:
            return i
    return 0


def balanco(P):
    """Por faixa de UC: produtos (com 3+ vendas), vendas, lucro e a lista."""
    fora = [{"produtos": [], "vendas": 0, "lucro": 0.0} for _ in FAIXAS]
    for k, p in P.items():
        f = fora[faixa_de(p["ucv"])]
        f["vendas"] += p["v"]
        f["lucro"] += p["lucro"]
        if p["v"] >= MIN_VENDAS_CONTA:
            f["produtos"].append(k)
    return fora


def volatilidade(p, ate_mes):
    """'Estável' | 'Oscila' | 'Picos' — pelo coeficiente de variação mensal,
    contado desde o primeiro mês em que o produto vendeu."""
    if not p["mes"]:
        return "Picos"
    ini = min(p["mes"])
    serie = [p["mes"].get(m, 0) for m in range(ini, ate_mes + 1)]
    mu = statistics.mean(serie)
    if not mu or len(serie) < 2:
        return "Picos" if len(serie) < 2 else "Estável"
    cv = statistics.pstdev(serie) / mu
    return "Estável" if cv < 0.35 else "Oscila" if cv < 0.75 else "Picos"


def tendencia(p, ate_mes):
    """Variação dos pedidos: 3 últimos meses contra os 3 anteriores. None = novo."""
    a = sum(p["mes"].get(m, 0) for m in range(ate_mes - 2, ate_mes + 1))
    b = sum(p["mes"].get(m, 0) for m in range(ate_mes - 5, ate_mes - 2))
    return (a - b) / b if b else None


def dando_certo(P, ate_mes):
    fora = []
    for k, p in ranking(P):
        ini = min(p["mes"])
        disp = ate_mes - ini + 1
        # 3 meses no mínimo: com 1 mês, "vende todo mês" é verdade de graça —
        # é produto novo, e esse tem quadro próprio (novos com potencial).
        if (p["ucv"] >= 1.0 and disp >= 3
                and len(p["mes"]) / disp >= RECORRENTE_FRACAO
                and p["v"] / disp >= RECORRENTE_PEDIDOS):
            fora.append((k, p))
    return fora


def dando_errado(P):
    """UC abaixo de 0,8 e volume — do que mais perde dinheiro para o que menos."""
    return sorted([(k, p) for k, p in P.items()
                   if p["ucv"] < UC_RUIM and p["v"] >= PEDIDOS_ERRADO],
                  key=lambda kv: kv[1]["lucro"])


def alertas(linhas, mes, plataforma=None, med=None):
    """(críticos, destaques, uc_media_do_mês, % das vendas abaixo de 0,7)."""
    P = agregar(linhas, {mes}, plataforma, med)
    v = sum(p["v"] for p in P.values())
    crit = sorted([(k, p) for k, p in P.items()
                   if p["v"] >= PEDIDOS_RELEVANTES and p["ucv"] < UC_CRITICA],
                  key=lambda kv: kv[1]["lucro"])
    dest = sorted([(k, p) for k, p in P.items()
                   if p["v"] >= PEDIDOS_RELEVANTES and p["ucv"] >= UC_DESTAQUE],
                  key=lambda kv: -kv[1]["lucro"])
    abaixo = sum(p["v"] for p in P.values() if p["ucv"] < UC_CRITICA)
    return crit, dest, uc_media(P), (abaixo / v if v else 0.0)


def novos_com_potencial(linhas, mes, hoje, plataforma=None, med=None, prim=None):
    """Produtos com primeira venda há até 60 dias que já estão no top 20 do mês
    com UC ≥ 1,0. A primeira venda é a do TÍTULO até os títulos serem juntados."""
    prim = prim if prim is not None else primeiras_vendas(linhas)
    rk = ranking(agregar(linhas, {mes}, plataforma, med))
    fora = []
    for i, (k, p) in enumerate(rk[:20], 1):
        d = prim.get(k)
        if d and (hoje - d).days <= DIAS_NOVO and p["ucv"] >= 1.0:
            fora.append((k, p, i, d))
    return fora


def concentracao(P, n=5):
    pos = sorted((p["lucro"] for p in P.values() if p["lucro"] > 0), reverse=True)
    return sum(pos[:n]) / sum(pos) if pos else 0.0


def skus_repetidos(linhas):
    nomes = collections.defaultdict(set)
    for x in linhas:
        if x["sku"]:
            nomes[x["sku"]].add(x["produto"])
    return {s: n for s, n in nomes.items() if len(n) > 1}


def meses_do_recorte(periodo, escolha):
    """{meses} do período. `escolha`: semestre 1-2, trimestre 1-4, mês 1-12."""
    if periodo == "Ano":
        return set(range(1, 13))
    if periodo == "Semestre":
        return set(range(1, 7)) if escolha == 1 else set(range(7, 13))
    if periodo == "Trimestre":
        return set(range(3 * escolha - 2, 3 * escolha + 1))
    return {escolha}


def panorama(linhas, produto, ate_mes, med=None):
    """Tudo de um produto: totais, por período, por plataforma e por mês."""
    med = med if med is not None else medianas_de_quantidade(linhas)
    so = [x for x in linhas if x["produto"] == produto]
    tot = agregar(so, set(range(1, 13)), None, med).get(produto)
    if not tot:
        return None
    sem = 1 if ate_mes <= 6 else 2
    tri = (ate_mes - 1) // 3 + 1
    rec = (("Mês", MES_CURTO[ate_mes - 1], {ate_mes}),
           ("Trimestre", f"{tri}º tri", meses_do_recorte("Trimestre", tri)),
           ("Semestre", f"{sem}º sem", meses_do_recorte("Semestre", sem)),
           ("Ano", "ano", set(range(1, 13))))
    periodos = []
    for nome, sub, ms in rec:
        rk = [k for k, _ in ranking(agregar(linhas, ms, None, med))]
        p = agregar(so, ms, None, med).get(produto)
        periodos.append((nome, sub, p, (rk.index(produto) + 1) if produto in rk else None))
    plats = {}
    for pl in ("Mercado Livre", "Shopee", "Shein", "TikTok Shop"):
        plats[pl] = agregar(so, set(range(1, 13)), pl, med).get(produto)
    por_mes = {m: agregar(so, {m}, None, med).get(produto) for m in range(1, ate_mes + 1)}
    return {"total": tot, "periodos": periodos, "plataformas": plats,
            "por_mes": por_mes, "titulos": 1}


# ── TELA ────────────────────────────────────────────────────────────────────

def _num(v, c=0):
    return f"{v:,.{c}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def _brl(v, c=0):
    return ("−" if v < 0 else "") + "R$ " + _num(abs(v), c)


def _cor(nome):
    import home_gestao as _hg
    return {"VERDE": _hg.VERDE, "AMBAR": _hg.AMBAR, "VERMELHO": _hg.VERMELHO}.get(nome, nome)


def _cor_uc(u):
    import home_gestao as _hg
    return _hg.VERDE if u >= 1 else _hg.AMBAR if u >= UC_RUIM else _hg.VERMELHO


def _chip_uc(u):
    c = _cor_uc(u)
    return (f'<span style="display:inline-block;min-width:40px;text-align:center;'
            f'border:1px solid {c}66;background:{c}18;color:{c};border-radius:8px;'
            f'padding:1px 6px;font-weight:700;font-size:12px">{_num(u, 2)}</span>')


def _barrinhas(p, ate_mes):
    from home_gestao import TILE
    mx = max(p["mes"].values()) if p["mes"] else 1
    r = "".join(
        f'<rect x="{i * 8}" y="{24 - (2 + 22 * p["mes"].get(m, 0) / mx if p["mes"].get(m) else 2):.1f}" '
        f'width="6" height="{(2 + 22 * p["mes"].get(m, 0) / mx if p["mes"].get(m) else 2):.1f}" rx="1.5" '
        f'fill="{"#BF9A45" if p["mes"].get(m) else "#4a4a4a"}"/>'
        for i, m in enumerate(range(1, ate_mes + 1)))
    return f'<svg width="{8 * ate_mes}" height="24" style="background:{TILE}00">{r}</svg>'


def _css():
    from home_gestao import CARTAO, BORDA, TILE, TEXTO, SEC
    return (f'<style>.pa-card{{background:{CARTAO};border:1px solid {BORDA};border-radius:16px;'
            f'padding:14px 16px;margin-bottom:10px;color:{TEXTO}}}'
            f'.pa-t{{font-size:16px;font-weight:700}}.pa-s{{font-size:12px;color:{SEC};margin-top:2px}}'
            f'.pa-k{{background:linear-gradient(160deg,{CARTAO},{TILE});border:1px solid {BORDA};'
            f'border-radius:14px;padding:12px 16px;color:{TEXTO}}}'
            f'.pa-kt{{font-size:11px;color:{SEC};letter-spacing:.08em;text-transform:uppercase}}'
            f'.pa-kv{{font-size:23px;font-weight:700;margin-top:4px}}.pa-kd{{font-size:12px;color:{SEC}}}'
            f'.pa-l{{display:flex;justify-content:space-between;gap:10px;font-size:12.5px;'
            f'padding:5px 0;border-top:1px solid #ffffff14}}.pa-l b{{color:{SEC};font-weight:600;white-space:nowrap}}'
            f'.pa-n{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}</style>')


def _caixa(cor, titulo, frase, sub, itens):
    from home_gestao import CARTAO
    lis = "".join(f'<div class="pa-l"><span class="pa-n">{a}</span><b>{b}</b></div>' for a, b in itens)
    return (f'<div class="pa-card" style="border-color:{cor}88;background:linear-gradient(135deg,{cor}22,{CARTAO})">'
            f'<div style="font-size:11px;font-weight:800;letter-spacing:.14em;color:{cor}">{titulo}</div>'
            f'<div style="font-size:15px;margin-top:6px">{frase}</div>'
            f'<div class="pa-s" style="margin-bottom:6px">{sub}</div>{lis}</div>')


def _tabela(itens, ate_mes, hoje=None, prim=None):
    """DataFrame de uma lista de produtos, com o código para achar e abrir."""
    import pandas as pd
    linhas = []
    for k, p in itens:
        d = (prim or {}).get(k)
        linhas.append({
            "Código": codigo(k), "Produto": k.title(),
            "Pedidos": p["v"], "Faturamento": round(p["fat"], 2),
            "Margem": round(p["mc"], 2), "Lucro": round(p["lucro"], 2),
            "UC/venda": round(p["ucv"], 2), "UC total": round(p["uct"], 1),
            "Mês a mês": volatilidade(p, ate_mes),
            "Desde": d.strftime("%d/%m") if d else ""})
    return pd.DataFrame(linhas)


def _lista(titulo, itens, linhas, ate_mes, prim, med, chave):
    """Abre a lista; escolher uma linha abre o panorama do produto ali mesmo."""
    @st.dialog(titulo, width="large")
    def _d():
        df = _tabela(itens, ate_mes, prim=prim)
        if df.empty:
            st.info("Nenhum produto nesta lista.")
            return
        sel = st.dataframe(df, hide_index=True, use_container_width=True,
                           on_select="rerun", selection_mode="single-row",
                           key=f"pa_lista_{chave}",
                           column_config={c: st.column_config.NumberColumn(c, format="R$ %.2f")
                                          for c in ("Faturamento", "Margem", "Lucro")})
        st.download_button("Baixar planilha", df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                           file_name=f"produtos_{chave}.csv", key=f"pa_dl_{chave}")
        linhas_sel = getattr(getattr(sel, "selection", None), "rows", None)
        if not isinstance(linhas_sel, (list, tuple)):
            linhas_sel = []
        if linhas_sel:
            k = itens[linhas_sel[0]][0]
            _mostrar_panorama(linhas, k, ate_mes, med, prim)
        else:
            st.caption("Clique numa linha para abrir o panorama do produto.")
    _d()


def _mostrar_panorama(linhas, produto, ate_mes, med, prim):
    import home_gestao as _hg
    pan = panorama(linhas, produto, ate_mes, med)
    if not pan:
        st.info("Sem vendas medíveis deste produto no ano.")
        return
    t = pan["total"]
    d = (prim or {}).get(produto)
    custo = statistics.median(t["custo_un"]) if t["custo_un"] else 0.0
    st.markdown(f"#### {produto.title()}")
    st.caption(f"Código {codigo(produto)} · SKU {t['sku'].most_common(1)[0][0]} · "
               f"custo unitário {_brl(custo, 2)} · vende desde "
               f"{d.strftime('%d/%m/%Y') if d else '—'} · {volatilidade(t, ate_mes).lower()}")
    c = st.columns(6)
    for col, (nm, val, sub) in zip(c, (
            ("Pedidos", _num(t["v"]), f"{_num(t['v'] / max(len(t['mes']), 1), 1)} por mês com venda"),
            ("Faturamento", _brl(t["fat"]), f"preço médio {_brl(t['fat'] / t['v'], 2)}"),
            ("Margem", _brl(t["mc"]), f"{t['mc'] / t['fat'] * 100:.0f}% do faturamento"),
            ("C.O. absorvido", _brl(t["co"]), "custo operacional"),
            ("Lucro", _brl(t["lucro"]), f"pagou {_brl(t['lpv'])} de custo fixo"),
            ("UC por venda", _num(t["ucv"], 2), f"UC total {_num(t['uct'])}"))):
        col.metric(nm, val, help=sub)
    import pandas as pd
    st.markdown("**Por período · e a posição no ranking de UC**")
    st.dataframe(pd.DataFrame([{
        "Período": f"{nm} ({sub})", "Posição": f"{pos}º" if pos else "—",
        "Pedidos": p["v"] if p else 0, "Faturamento": round(p["fat"], 2) if p else 0,
        "Margem": round(p["mc"], 2) if p else 0, "C.O.": round(p["co"], 2) if p else 0,
        "Custo fixo (LPV)": round(p["lpv"], 2) if p else 0,
        "Lucro": round(p["lucro"], 2) if p else 0,
        "UC/venda": round(p["ucv"], 2) if p else None}
        for nm, sub, p, pos in pan["periodos"]]), hide_index=True, use_container_width=True)
    st.markdown("**Por plataforma · ano**")
    st.dataframe(pd.DataFrame([{
        "Plataforma": pl, "Pedidos": p["v"] if p else 0,
        "% das vendas": f"{p['v'] / t['v'] * 100:.0f}%" if p else "—",
        "Preço médio": round(p["fat"] / p["v"], 2) if p else None,
        "Faturamento": round(p["fat"], 2) if p else 0,
        "Comissão %": f"{p['com'] / p['fat'] * 100:.0f}%" if p else "—",
        "Margem": round(p["mc"], 2) if p else 0, "Lucro": round(p["lucro"], 2) if p else 0,
        "UC/venda": round(p["ucv"], 2) if p else None}
        for pl, p in pan["plataformas"].items()]), hide_index=True, use_container_width=True)
    n = t["v"]
    preco = t["fat"] / n
    partes = [("Custo do produto", t["ct"] / n), ("Comissão", t["com"] / n),
              ("Frete", t["fr"] / n), ("NF", t["nf"] / n), ("Devolução", t["dev"] / n),
              ("Custo operacional", t["co"] / n), ("Margem de contribuição", t["mc"] / n)]
    mcv, lpvv = t["mc"] / n, t["lpv"] / n
    st.markdown(f"**Para onde vai o preço médio de {_brl(preco, 2)}**")
    st.dataframe(pd.DataFrame([{"Parte": a, "Por venda": round(b, 2),
                                "% do preço": f"{b / preco * 100:.0f}%"} for a, b in partes if abs(b) > 0.005]
                              + [{"Parte": "Custo fixo que cada venda paga (LPV)", "Por venda": round(lpvv, 2), "% do preço": ""},
                                 {"Parte": "Sobra por venda" if mcv >= lpvv else "Falta por venda",
                                  "Por venda": round(abs(mcv - lpvv), 2), "% do preço": ""}]),
                 hide_index=True, use_container_width=True)
    if mcv < lpvv:
        var = (t["com"] + t["nf"] + t["co"]) / t["fat"]
        if var < 1:
            st.caption(f"Preço estimado para UC 1,0: **{_brl(preco + (lpvv - mcv) / (1 - var), 2)}** "
                       f"(comissão, NF e C.O. sobem junto com o preço).")
    meses = [m for m in range(1, ate_mes + 1)]
    st.markdown("**Pedidos por mês, por plataforma**")
    st.bar_chart(pd.DataFrame(
        {pl: [agregar([x for x in linhas if x["produto"] == produto], {m}, pl, med).get(produto, {}).get("v", 0)
              for m in meses] for pl, p in pan["plataformas"].items() if p},
        index=[MES_CURTO[m - 1] for m in meses]),
        color=[_hg.COR_PLATAFORMA[pl] for pl, p in pan["plataformas"].items() if p])


def _coluna_html(nome, sub, rk, n_vis, alvo):
    """Uma das quatro colunas do ranking; `alvo` acende o produto buscado."""
    from home_gestao import TILE, TEXTO, SEC, CARTAO, BORDA, VERDE, VERMELHO
    linhas = []
    top = rk[:20]
    for i, (k, p) in enumerate(top, 1):
        hl = alvo and k == alvo
        corte = "border-bottom:1px dashed #BF9A45aa;" if i == n_vis else ""
        med = {1: "#D4B26A", 2: "#C0C6CE", 3: "#B98A5E"}.get(i, "#5a5a5a")
        linhas.append(
            f'<div style="display:flex;gap:8px;align-items:center;padding:6px 6px;margin:3px 0;'
            f'border-radius:9px;background:{"#3a3324" if hl else TILE};'
            f'{"outline:1.5px solid #BF9A45;" if hl else ""}{corte}">'
            f'<span style="width:22px;height:22px;border-radius:50%;border:1.5px solid {med};'
            f'color:{med if i <= 3 else SEC};font-size:11px;font-weight:700;display:inline-flex;'
            f'align-items:center;justify-content:center;flex:none">{i}</span>'
            f'<span style="flex:1;min-width:0"><span class="pa-n" style="display:block;font-size:12.5px;'
            f'font-weight:600">{k.title()}</span><span style="font-size:11px;color:{SEC}">UC '
            f'<b style="color:{_cor_uc(p["ucv"])}">{_num(p["ucv"], 2)}</b> · lucro '
            f'<b style="color:{VERDE if p["lucro"] >= 0 else VERMELHO}">{_brl(p["lucro"])}</b></span></span>'
            f'<span style="font-family:monospace;font-size:10px;color:{"#BF9A45" if hl else "#7b7f86"}">'
            f'{codigo(k)}</span></div>')
    fixo = ""
    if alvo:
        nomes = [k for k, _ in rk]
        if alvo not in nomes:
            fixo = f'<div style="font-size:11.5px;color:{SEC};text-align:center;padding:8px">não vendeu neste período</div>'
        elif nomes.index(alvo) >= 20:
            p = rk[nomes.index(alvo)][1]
            fixo = (f'<div style="padding:6px;border-radius:9px;border:1.5px dashed #BF9A45;'
                    f'background:#3a3324;font-size:12px;margin-top:4px"><b style="color:#BF9A45">'
                    f'{nomes.index(alvo) + 1}º</b> · {alvo.title()[:34]}… · UC {_num(p["ucv"], 2)}</div>')
    altura = 50 * n_vis + 8
    return (f'<div class="pa-card" style="padding:12px"><div style="display:flex;justify-content:space-between">'
            f'<div><div class="pa-t">{nome}</div><div class="pa-s">{sub}</div></div>'
            f'<div style="font-size:10px;font-weight:700;color:#BF9A45;letter-spacing:.1em">TOP {n_vis} · ATÉ 20 ↓</div></div>'
            f'<div style="max-height:{altura}px;overflow-y:auto;margin-top:6px">{"".join(linhas)}</div>{fixo}</div>')


def pagina(usuario_logado=None):
    import auth
    import home_gestao as _hg
    import lancamentos as _lan
    from datetime import datetime
    if not auth.eh_dono(usuario_logado):
        st.warning("Esta página é só do dono.")
        return
    hoje = datetime.now(_lan.FUSO).date()
    ano = hoje.year
    with st.spinner("Lendo a BASE DE VENDAS…"):
        linhas, erro = dados(ano, hoje)
    if erro:
        st.error(erro)
        return
    if not linhas:
        st.info("Nenhuma venda medível na BASE DE VENDAS deste ano.")
        return
    ate_mes = max(x["mes"] for x in linhas)
    med = medianas_de_quantidade(linhas)
    prim = primeiras_vendas(linhas)
    st.markdown(_css(), unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:11px;letter-spacing:.18em;color:#BF9A45;font-weight:700">'
                f'GESTÃO · PRODUTOS</div>', unsafe_allow_html=True)
    st.markdown("### Análise de produtos")
    c1, c2 = st.columns([3, 2])
    with c1:
        periodo = st.segmented_control("Período", ("Ano", "1º sem", "2º sem", "Trimestre", "Mês"),
                                       default="Ano", key="pa_periodo") or "Ano"
    with c2:
        plat = st.segmented_control("Plataforma", ("Todas", "Mercado Livre", "Shopee", "Shein", "TikTok Shop"),
                                    default="Todas", key="pa_plat") or "Todas"
    plat = None if plat == "Todas" else plat
    mes_ref = ate_mes
    tri_ref = (ate_mes - 1) // 3 + 1
    if periodo == "Trimestre":
        tri_ref = st.selectbox("Trimestre", [1, 2, 3, 4], index=tri_ref - 1,
                               format_func=lambda t: f"{t}º trimestre", key="pa_tri")
    if periodo == "Mês":
        mes_ref = st.selectbox("Mês", list(range(1, ate_mes + 1)), index=ate_mes - 1,
                               format_func=lambda m: MES_CURTO[m - 1], key="pa_mes")
    meses = {"Ano": meses_do_recorte("Ano", 0), "1º sem": meses_do_recorte("Semestre", 1),
             "2º sem": meses_do_recorte("Semestre", 2),
             "Trimestre": meses_do_recorte("Trimestre", tri_ref),
             "Mês": meses_do_recorte("Mês", mes_ref)}[periodo]
    P = agregar(linhas, meses, plat, med)
    fontes = sorted({x["mes"] for x in linhas if x["fonte_lpv"] == "planilha"})
    st.caption(f"Dados da BASE DE VENDAS até {MES_CURTO[ate_mes - 1]} · LPV de cada venda é o do mês dela"
               + (f" · meses com LPV da planilha (o Studio não conseguiu calcular): "
                  + ", ".join(MES_CURTO[m - 1] for m in fontes) if fontes else ""))

    # ALERTAS DO MÊS
    crit, dest, ucm_mes, pct07 = alertas(linhas, mes_ref, plat, med)
    novos = novos_com_potencial(linhas, mes_ref, hoje, plat, med, prim)
    a1, a2, a3 = st.columns(3)
    nm_mes = MES_CURTO[mes_ref - 1]
    with a1:
        st.markdown(_caixa(_hg.VERMELHO, f"● ATENÇÃO IMEDIATA · {nm_mes.upper()}",
                           f"<b>{len(crit)} produtos</b> com UC abaixo de {_num(UC_CRITICA, 1)} e "
                           f"{PEDIDOS_RELEVANTES}+ pedidos — <b style='color:{_hg.VERMELHO}'>"
                           f"{_brl(sum(p['lucro'] for _, p in crit))}</b>",
                           f"UC média do mês {_num(ucm_mes, 2)} · {pct07 * 100:.0f}% das vendas abaixo de {_num(UC_CRITICA, 1)}",
                           [(k.title(), f"{p['v']} ped. · UC {_num(p['ucv'], 2)} · {_brl(p['lucro'])}") for k, p in crit[:3]]),
                    unsafe_allow_html=True)
        if crit and st.button(f"Ver os {len(crit)} ›", key="pa_v_crit"):
            _lista(f"Atenção imediata · {nm_mes}", crit, linhas, ate_mes, prim, med, "crit")
    with a2:
        st.markdown(_caixa(_hg.VERDE, f"● LUCRANDO FORTE · {nm_mes.upper()}",
                           f"<b>{len(dest)} produtos</b> com UC {_num(UC_DESTAQUE, 1)}+ e {PEDIDOS_RELEVANTES}+ pedidos — "
                           f"<b style='color:{_hg.VERDE}'>{_brl(sum(p['lucro'] for _, p in dest))}</b>",
                           "É o que vale reforçar: estoque, anúncio e exposição",
                           [(k.title(), f"{p['v']} ped. · UC {_num(p['ucv'], 2)} · {_brl(p['lucro'])}") for k, p in dest[:3]]),
                    unsafe_allow_html=True)
        if dest and st.button(f"Ver os {len(dest)} ›", key="pa_v_dest"):
            _lista(f"Lucrando forte · {nm_mes}", dest, linhas, ate_mes, prim, med, "dest")
    with a3:
        st.markdown(_caixa(_hg.AZUL, f"⚡ NOVOS COM POTENCIAL · {nm_mes.upper()}",
                           f"<b>{len(novos)} produtos</b> com primeira venda há até {DIAS_NOVO} dias, "
                           f"já no top 20 do mês com UC ≥ 1,0",
                           "Primeira venda do título — até os títulos do mesmo produto serem juntados",
                           [(k.title(), f"{i}º · desde {d.strftime('%d/%m')} · UC {_num(p['ucv'], 2)}") for k, p, i, d in novos[:3]]),
                    unsafe_allow_html=True)
        if novos and st.button(f"Ver os {len(novos)} ›", key="pa_v_novos"):
            _lista(f"Novos com potencial · {nm_mes}", [(k, p) for k, p, _, _ in novos],
                   linhas, ate_mes, prim, med, "novos")
    rep = skus_repetidos(linhas)
    if rep:
        st.caption(f"⚠ {len(rep)} SKUs aparecem em mais de um título — boa parte é o mesmo produto "
                   f"anunciado com outro nome; o resto é produto diferente com o mesmo custo (o SKU é o custo).")

    # OS NÚMEROS DO TOPO
    ucm = uc_media(P)
    tv = sum(p["v"] for p in P.values()) or 1
    bal = balanco(P)
    paga = sum(b["vendas"] for b, f in zip(bal, FAIXAS) if f[2] >= 1.0)
    ruim = bal[0]["vendas"]
    k = st.columns(5)
    for col, (t, v, d, cor) in zip(k, (
            ("UC média do período", _num(ucm, 2), "margem total ÷ LPV consumido", _cor_uc(ucm)),
            ("Lucro depois do custo fixo", _brl(sum(p["lucro"] for p in P.values())), "margem − LPV de cada venda", _hg.TEXTO),
            ("Vendas que pagam o custo fixo", f"{paga / tv * 100:.0f}%", "UC ≥ 1,0", _hg.VERDE),
            (f"Vendas abaixo de {_num(UC_RUIM, 1)}", f"{ruim / tv * 100:.0f}%", f"{len(bal[0]['produtos'])} produtos", _hg.VERMELHO),
            ("Concentração do lucro", f"{concentracao(P) * 100:.0f}%", "do lucro vem de 5 produtos", _hg.TEXTO))):
        col.markdown(f'<div class="pa-k"><div class="pa-kt">{t}</div><div class="pa-kv" style="color:{cor}">{v}</div>'
                     f'<div class="pa-kd">{d}</div></div>', unsafe_allow_html=True)

    # BALANÇO DA UC
    st.markdown(f'<div class="pa-card" style="margin-top:10px"><div class="pa-t">Balanço da UC</div>'
                f'<div class="pa-s">Como as vendas se dividem por faixa de UC — clique para ver a lista</div>'
                f'<div style="display:flex;height:14px;border-radius:6px;overflow:hidden;gap:2px;margin-top:10px">'
                + "".join(f'<span style="display:block;width:{b["vendas"] / tv * 100:.1f}%;background:{_cor(f[4])}"></span>'
                          for b, f in zip(bal, FAIXAS)) + '</div></div>', unsafe_allow_html=True)
    cols = st.columns(len(FAIXAS))
    for i, (col, b, f) in enumerate(zip(cols, bal, FAIXAS)):
        with col:
            st.markdown(f'<div class="pa-k" style="border-top:3px solid {_cor(f[4])}"><div style="font-weight:700">UC {f[0]}</div>'
                        f'<div class="pa-kd">{f[1]}</div><div class="pa-kv">{len(b["produtos"])} '
                        f'<span style="font-size:12px;color:{_hg.SEC};font-weight:500">produtos</span></div>'
                        f'<div class="pa-kd">{_num(b["vendas"])} vendas · {b["vendas"] / tv * 100:.0f}%</div>'
                        f'<div class="pa-kd" style="color:{_hg.VERDE if b["lucro"] >= 0 else _hg.VERMELHO}">lucro {_brl(b["lucro"])}</div></div>',
                        unsafe_allow_html=True)
            if b["produtos"] and st.button("Ver lista ›", key=f"pa_faixa_{i}"):
                _lista(f"UC {f[0]}", sorted([(n, P[n]) for n in b["produtos"]], key=lambda kv: kv[1]["lucro"]),
                       linhas, ate_mes, prim, med, f"faixa{i}")
    imp = impacto_na_media(P)
    elig = [(n, P[n]) for n in P if P[n]["v"] >= MIN_VENDAS_CONTA]
    cima = sorted(elig, key=lambda kv: -imp.get(kv[0], 0))[:5]
    baixo = sorted(elig, key=lambda kv: imp.get(kv[0], 0))[:5]
    m1, m2 = st.columns(2)
    for col, nome, lst, cor, sinal in ((m1, "▲ Puxam a média para cima", cima, _hg.VERDE, "soma"),
                                       (m2, "▼ Puxam a média para baixo", baixo, _hg.VERMELHO, "tira")):
        col.markdown(f'<div class="pa-card"><div style="font-size:12px;font-weight:800;letter-spacing:.08em;color:{cor}">{nome}</div>'
                     f'<div class="pa-s">UC média hoje: <b>{_num(ucm, 2)}</b> · "{sinal} 0,016" = quanto a média muda por causa dele</div>'
                     + "".join(f'<div class="pa-l"><span class="pa-n">{n.title()} <span style="color:{_hg.SEC}">· {p["v"]} ped. · UC {_num(p["ucv"], 2)} · {_brl(p["lucro"])}</span></span>'
                               f'<b style="color:{cor}">{sinal} {_num(abs(imp.get(n, 0)), 3)}</b></div>' for n, p in lst)
                     + '</div>', unsafe_allow_html=True)

    # DANDO CERTO · DANDO ERRADO
    certo, errado = dando_certo(P, ate_mes), dando_errado(P)
    d1, d2 = st.columns(2)
    for col, nome, sub, lst, cor, ch in (
            (d1, "✓ Dando certo", f"Vende quase todo mês, {RECORRENTE_PEDIDOS}+ pedidos/mês e UC ≥ 1,0", certo, _hg.VERDE, "certo"),
            (d2, "✕ Dando errado", f"UC abaixo de {_num(UC_RUIM, 1)} e {PEDIDOS_ERRADO}+ pedidos · do que mais perde", errado, _hg.VERMELHO, "errado")):
        with col:
            st.markdown(f'<div class="pa-card"><div class="pa-t" style="color:{cor}">{nome}</div><div class="pa-s">{sub}</div>'
                        + "".join(f'<div class="pa-l" style="align-items:center"><span class="pa-n">{n.title()}'
                                  f'<br><span style="color:{_hg.SEC};font-size:11px">{p["v"]} pedidos · {volatilidade(p, ate_mes).lower()}</span></span>'
                                  f'{_barrinhas(p, ate_mes)}<b style="color:{_hg.VERDE if p["lucro"] >= 0 else _hg.VERMELHO}">{_brl(p["lucro"])}</b>{_chip_uc(p["ucv"])}</div>'
                                  for n, p in lst[:5])
                        + '</div>', unsafe_allow_html=True)
            if lst and st.button(f"Ver todos ({len(lst)}) ›", key=f"pa_v_{ch}"):
                _lista(nome, lst[:200], linhas, ate_mes, prim, med, ch)

    # RANKING NOS QUATRO PERÍODOS
    st.markdown('<div class="pa-card"><div class="pa-t">Ranking nos quatro períodos</div>'
                '<div class="pa-s">Por UC total · cada produto tem um código · busque para achá-lo nas quatro colunas</div></div>',
                unsafe_allow_html=True)
    todos = sorted(P.keys() | {x["produto"] for x in linhas})
    por_codigo = {codigo(n): n for n in todos}
    busca = st.text_input("Buscar produto ou código", key="pa_busca", placeholder="P1A2B3 ou parte do nome",
                          label_visibility="collapsed")
    alvo = None
    b = norm_titulo(busca)
    if b:
        alvo = por_codigo.get(b) or next((n for n in todos if b in n), None)
        if not alvo:
            st.caption("Nenhum produto com esse código ou nome.")
    sem = 1 if mes_ref <= 6 else 2
    quatro = (("Ano", f"{ano}", meses_do_recorte("Ano", 0), 10),
              ("Semestre", f"{sem}º semestre", meses_do_recorte("Semestre", sem), 5),
              ("Trimestre", f"{tri_ref}º trimestre", meses_do_recorte("Trimestre", tri_ref), 5),
              ("Mês", MES_CURTO[mes_ref - 1], {mes_ref}, 5))
    for col, (nome, sub, ms, nv) in zip(st.columns(4), quatro):
        col.markdown(_coluna_html(nome, sub, ranking(agregar(linhas, ms, plat, med)), nv, alvo),
                     unsafe_allow_html=True)
    escolha = st.selectbox("Abrir o panorama de um produto", [""] + [n for n, _ in ranking(P)[:300]],
                           format_func=lambda n: "" if not n else f"{codigo(n)} · {n.title()}", key="pa_pan")
    if alvo and st.button(f"Abrir o panorama de {codigo(alvo)}", key="pa_pan_busca"):
        escolha = alvo
    if escolha:
        @st.dialog("Panorama do produto", width="large")
        def _pan():
            _mostrar_panorama(linhas, escolha, ate_mes, med, prim)
        _pan()

    # BAIXÍSSIMA SAÍDA
    baixa = sorted([(n, p) for n, p in P.items() if p["v"] <= BAIXA_SAIDA], key=lambda kv: kv[1]["lucro"])
    st.markdown(f'<div class="pa-card"><div class="pa-t">Baixíssima saída</div><div class="pa-s">Venderam {BAIXA_SAIDA} vezes ou menos no período</div>'
                f'<div style="font-size:14px;margin-top:6px"><b style="font-size:22px">{len(baixa)}</b> produtos · '
                f'{sum(p["v"] for _, p in baixa)} vendas ({sum(p["v"] for _, p in baixa) / tv * 100:.1f}% das vendas)</div></div>',
                unsafe_allow_html=True)
    if baixa and st.button("Ver lista ›", key="pa_v_baixa"):
        _lista("Baixíssima saída", baixa, linhas, ate_mes, prim, med, "baixa")


if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    import datetime as _dt
    # A ENTRADA VEM DO SISTEMA: o cabeçalho é o da BASE DE VENDAS 2026 real
    # (cópia de 15/10), e as linhas passam por `linhas_da_base`, a mesma porta
    # da tela — não um dicionário escrito no formato que eu acho que ele tem.
    CAB = ['MÊS', 'MÊS/ANO', 'Data', 'Situação', 'Plataforma', 'Pedido', 'SKU', 'Produto',
           'Quantidade', 'Preço unitário', 'Total dos Produtos', 'Desconto', 'Custo Unitário',
           'Taxa de Comissão', 'Custo de Frete', 'Reembolso Flex', 'Custo Flex', 'FAT TOTAL',
           'CUSTO TOTAL', 'COMISSÃO', 'FRETE', 'NF', 'CUSTO OP.', 'DEVOLUÇÃO', 'MARGEM C.',
           'VENDAS', 'LPV', 'UNI. CONT.', 'MARGEM %']

    def _linha(mes, dia, produto, plat, mc, q=1, fat=60.0, sku="MS-2260", lpv_pl=18.0):
        return {"Data": _dt.datetime(2026, mes, dia), "MÊS/ANO": f"{MES_CURTO[mes - 1]}2026",
                "Plataforma": plat, "SKU": sku, "Produto": produto + "  ", "Quantidade": q,
                "FAT TOTAL": fat, "CUSTO TOTAL": 22.6, "COMISSÃO": 17.5, "FRETE": 0,
                "NF": 5.4, "CUSTO OP.": 4.3, "DEVOLUÇÃO": 0, "MARGEM C.": mc,
                "Custo Flex": 0, "LPV": lpv_pl, "Custo Unitário": 22.6}

    regs = []
    for m in range(1, 10):
        for d in range(1, 13):                                  # 12/mês, UC baixa
            regs.append(_linha(m, d, "Kit Com 3 Estátuas", "Shopee1", 10.0))
        for d in range(1, 8):                                   # 7/mês, UC alta
            regs.append(_linha(m, d, "Cinzeiro Telescópico", "MercadoLivre1", 45.0, fat=200.0, sku="MS-8936"))
    for d in range(1, 13):                                      # novo em setembro, 12 pedidos
        regs.append(_linha(9, d + 5, "Globo Preto Base Meta", "Shopee2", 40.0, fat=120.0, sku="MS-5832"))
    regs.append(_linha(2, 9, "Kit Com 3 Estátuas", "Shopee1", 300.0, q=30))   # o kit de 30
    regs.append(_linha(5, 1, "Produto Raro", "Shein1", 5.0, sku="MS-2260"))
    regs.append({"Data": _dt.datetime(2025, 12, 1), "Produto": "De Outro Ano", "FAT TOTAL": 10,
                 "MARGEM C.": 1})
    lpv_mes = {m: 18.0 for m in range(1, 9)}                   # setembro sem LPV do Studio
    L = linhas_da_base(regs, CAB, lpv_mes, 2026)
    ok("lê a BASE pela porta da tela; outro ano fica de fora",
       len(L) == len(regs) - 1 and all(x["fat"] > 0 for x in L))
    ok("título normalizado e plataforma canônica",
       L[0]["produto"] == "KIT COM 3 ESTÁTUAS" and L[0]["plataforma"] == "Shopee"
       and L[12]["plataforma"] == "Mercado Livre")
    ok("mês sem LPV do Studio usa a coluna LPV da planilha, e diz que usou",
       all(x["fonte_lpv"] == "planilha" and x["lpv"] == 18.0 for x in L if x["mes"] == 9)
       and all(x["fonte_lpv"] == "studio" for x in L if x["mes"] < 9))
    med = medianas_de_quantidade(L)
    kit30 = [x for x in L if x["q"] == 30][0]
    ok("o kit de 30 é venda pontual; a venda normal não", eh_pontual(kit30, med)
       and not eh_pontual(L[0], med))
    A = agregar(L, set(range(1, 13)), None, med)
    kit = A["KIT COM 3 ESTÁTUAS"]
    ok("a venda pontual sai da conta e aparece à parte",
       kit["v"] == 108 and abs(kit["uc_pontual"] - 300 / 18) < 1e-6)
    ok("UC por venda é razão das somas", abs(kit["ucv"] - 10 / 18) < 1e-9
       and abs(A["CINZEIRO TELESCÓPICO"]["ucv"] - 45 / 18) < 1e-9)
    rk = ranking(A)
    ok("ranking pela UC total (quem mais pagou custo fixo)",
       rk[0][0] == "CINZEIRO TELESCÓPICO" and rk[0][1]["uct"] > rk[1][1]["uct"])
    imp = impacto_na_media(A)
    ok("o kit puxa a média para baixo, o cinzeiro para cima",
       imp["KIT COM 3 ESTÁTUAS"] < 0 < imp["CINZEIRO TELESCÓPICO"])
    bal = balanco(A)
    ok("balanço: kit abaixo de 0,8; produto com 1 venda não entra na contagem",
       "KIT COM 3 ESTÁTUAS" in bal[0]["produtos"] and "PRODUTO RARO" not in sum((b["produtos"] for b in bal), []))
    ok("dando errado = UC < 0,8 com volume; dando certo = recorrente com UC ≥ 1",
       [k for k, _ in dando_errado(A)] == ["KIT COM 3 ESTÁTUAS"]
       and [k for k, _ in dando_certo(A, 9)] == ["CINZEIRO TELESCÓPICO"])
    crit, dest, ucm9, pct = alertas(L, 9, None, med)
    ok("alerta de setembro: kit crítico, globo novo lucrando forte",
       [k for k, _ in crit] == ["KIT COM 3 ESTÁTUAS"]
       and "GLOBO PRETO BASE META" in [k for k, _ in dest])
    prim = primeiras_vendas(L)
    nv = novos_com_potencial(L, 9, date(2026, 10, 20), None, med, prim)
    ok("novo com potencial: o globo (primeira venda em setembro), não o cinzeiro",
       [k for k, *_ in nv] == ["GLOBO PRETO BASE META"])
    ok("o mesmo título dá sempre o mesmo código, com ou sem espaço sobrando",
       codigo("Kit Com 3 Estátuas") == codigo(" KIT  COM 3 ESTÁTUAS ") and codigo("x").startswith("P")
       and len(codigo("x")) == 6)
    ok("volatilidade: 12 por mês é estável; tendência sem histórico é None",
       volatilidade(kit, 9) == "Estável" and tendencia(A["GLOBO PRETO BASE META"], 9) is None)
    ok("SKU repetido: MS-2260 está em dois títulos", "MS-2260" in skus_repetidos(L))
    ok("recortes: 2º semestre e 3º trimestre",
       meses_do_recorte("Semestre", 2) == set(range(7, 13)) and meses_do_recorte("Trimestre", 3) == {7, 8, 9})
    pan = panorama(L, "CINZEIRO TELESCÓPICO", 9, med)
    ok("panorama: posição 1º no ano e só Mercado Livre",
       pan["periodos"][3][3] == 1 and pan["plataformas"]["Mercado Livre"]["v"] == 63
       and pan["plataformas"]["Shopee"] is None)
    ok("concentração entre 0 e 1", 0 < concentracao(A) <= 1)

    raise SystemExit(1 if falhas else 0)
