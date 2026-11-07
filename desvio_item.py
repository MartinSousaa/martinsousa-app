"""desvio_item.py — o que cobrou acima do estimado, item a item (dono, 07/11).

O PEDIDO
--------
"O meu plano do Claude Code é de R$500, mas (...) eu tenho algumas cobranças
adicionais no mês por utilização (...) quero que o estúdio me informe se algum
custo fixo teve cobranças muito acima do estimado, as assinaturas e se as
demais cobranças variáveis, exceto compra de mercadoria, tenham tido gastos
excessivos." Mercadoria fica de fora: ela cresce com o faturamento.

POR QUE O PAINEL DE CIMA NÃO VIA ISSO
-------------------------------------
O "previsto" de custo fixo e assinaturas do painel (`previsto._custo_fixo`,
`visao_financeira.previsto_do_mes`) troca o cadastro pelo valor REAL do
extrato onde ele existe (`custo_real`, pedido de 25/09) — certo para saber
quanto o mês custou, e cego para o desvio: o cobrado era comparado com o
próprio cobrado. Aqui a régua é o CADASTRO, sem o real por cima.

AS RÉGUAS
---------
    custo fixo    cadastro + ajustes de valor (`ajustes.valor_no_mes`)
    assinaturas   valor da aba Assinaturas (`assinaturas.custo_mensal`);
                  anual compara a cobrança com o valor cheio, e não cobra
                  presença todo mês
    variáveis     não têm estimado: a média dos 3 meses anteriores do resumo
                  (`visao_geral.resumo`) — só dentro do ano carregado
    "acima"       a tolerância da tela de Assinaturas, uma regra só
                  (`assinaturas._fora_da_tolerancia`: 10% e R$ 3)

O cobrado de cada item é `custo_real.cobrancas_no_mes` — o mesmo casamento
que atualiza o valor real do mês. Cobrança marcada como custo fixo/assinatura
que não casa com item nenhum vai para SEM ITEM: some do item, mas não some
da tela.
"""
import streamlit as st

MESES_HIST = 4
MESES_MEDIA = 3
FIXAS = ("CUSTO FIXO", "ASSINATURAS")
MES3 = ("JAN", "FEV", "MAR", "ABR", "MAI", "JUN",
        "JUL", "AGO", "SET", "OUT", "NOV", "DEZ")


def _num(v):
    try:
        f = float(str(v).replace(",", ".")) if not isinstance(v, (int, float)) else float(v)
        return f if f == f else 0.0
    except (TypeError, ValueError):
        return 0.0


def meses_ate(ano, mes, n=MESES_HIST):
    """[(ano, mes)] dos `n` meses que terminam em (ano, mes), do mais antigo. Pura."""
    fora, a, m = [], int(ano), int(mes)
    for _ in range(n):
        fora.append((a, m))
        a, m = (a - 1, 12) if m == 1 else (a, m - 1)
    return fora[::-1]


def acima(cobrado, estimado):
    """Cobrou acima do estimado, fora da tolerância? Pura."""
    if cobrado is None:
        return False
    import assinaturas as _as
    fora, dif = _as._fora_da_tolerancia(round(cobrado, 2), round(estimado, 2))
    return fora and dif > 0


def _anual(linha):
    return str(linha.get("periodicidade", "")).strip().lower().startswith("anu")


def linha_do_item(grupo, item, estimados, cobrancas, anual=False, atual=False):
    """Um item no último dos meses. Pura.

    `estimados` e `cobrancas` têm um elemento por mês (do mais antigo);
    `cobrancas` é a lista de valores cobrados naquele mês ([] = não apareceu).
    `atual`: o último mês ainda está correndo — o que não apareceu ainda pode
    aparecer, e não vira "não apareceu".
    """
    cob = [round(sum(c), 2) if c else None for c in cobrancas]
    est, c = round(estimados[-1], 2), cob[-1]
    if c is not None and acima(c, est):
        sit = "acima"
    elif c is None and est > 0 and not anual:
        sit = "aguardando" if atual else "falta"
    else:
        sit = "dentro"
    return {"grupo": grupo, "item": item, "estimado": est, "cobrado": c,
            "hist": [x or 0.0 for x in cob], "est_hist": list(estimados),
            "partes": [round(v, 2) for v in cobrancas[-1]], "sit": sit}


def fixos(linhas_cf, linhas_as, por_item_aj, meses, lancs_por_mes, atual=False):
    """([linha_do_item], sem_item) do Custo fixo e das Assinaturas. Pura.

    `lancs_por_mes`: {(ano, mes): [lançamento]} na forma de
    `lancamentos.carregar`, já com o cadastro de finalidades aplicado.
    `sem_item`: [(nome, valor)] do ÚLTIMO mês — saída marcada como custo
    fixo/assinatura que nenhum item reconheceu, a maior primeiro.
    """
    import ajustes as _aj
    import assinaturas as _as
    import custo_real as _cr
    import visao_geral as _vg
    fora, casados = [], set()
    for grupo, linhas in (("custo_fixo", linhas_cf), ("assinaturas", linhas_as)):
        for l in (linhas or []):
            item = str(l.get("item") or "").strip()
            if not item:
                continue
            ests, cobs = [], []
            for (a, m) in meses:
                if grupo == "custo_fixo":
                    e = _aj.valor_no_mes(l.get("valor_mensal"), l.get("vigente_desde"),
                                         por_item_aj.get(("custo_fixo", item)), a, m)
                else:
                    e = _num(l.get("valor_mensal")) if _anual(l) else _as.custo_mensal(l)
                achadas = _cr.cobrancas_no_mes(l, lancs_por_mes.get((a, m)) or [])
                if (a, m) == meses[-1]:
                    casados.update(id(x) for x in achadas)
                ests.append(float(e or 0.0))
                cobs.append([-_num(x.get("valor")) for x in achadas])
            li = linha_do_item(grupo, item, ests, cobs, _anual(l), atual)
            if li["estimado"] or li["cobrado"] is not None:
                fora.append(li)
    sem = {}
    for x in lancs_por_mes.get(meses[-1]) or []:
        if id(x) in casados or _num(x.get("valor")) >= 0:
            continue
        if _vg.finalidade(x.get("finalidade")) not in FIXAS:
            continue
        nome = (str(x.get("favorecido") or "").strip()
                or str(x.get("descricao") or "").strip())[:60]
        sem[nome] = round(sem.get(nome, 0.0) - _num(x.get("valor")), 2)
    return fora, sorted(sem.items(), key=lambda kv: -kv[1])


def variaveis(valores, mes, lancs_do_mes, n=MESES_MEDIA):
    """[linha] das finalidades variáveis (sem mercadoria e sem compromissos)
    no mês `mes`, contra a média dos `n` meses anteriores do ano. Pura.

    `valores`: {mes_idx: {finalidade: valor}} de `visao_geral.resumo`. Mês
    anterior sem resumo não entra na média; sem nenhum, não há régua.
    """
    import visao_financeira as _vfin
    import visao_geral as _vg
    m = int(mes)
    antes = [k for k in range(m - n, m) if k >= 1 and k in (valores or {})]
    fins = {_vg.finalidade(f) for k in antes + [m] for f in (valores.get(k) or {})}
    fora = []
    for fin in sorted(fins):
        if _vfin.grupo(fin) != "outros":
            continue

        def v(k):
            return round(sum(float(x or 0.0) for f, x in (valores.get(k) or {}).items()
                             if _vg.finalidade(f) == fin), 2)
        if not antes:
            continue
        media = round(sum(v(k) for k in antes) / len(antes), 2)
        real = v(m)
        if not media and not real:
            continue
        maior = None
        for x in lancs_do_mes or []:
            if _vg.finalidade(x.get("finalidade")) == fin and _num(x.get("valor")) < 0:
                if maior is None or _num(x.get("valor")) < _num(maior.get("valor")):
                    maior = x
        hist_k = [k for k in range(m - MESES_HIST + 1, m + 1) if k >= 1]
        fora.append({"grupo": "variavel", "item": fin.capitalize(), "estimado": media,
                     "cobrado": real, "hist": [v(k) for k in hist_k],
                     "est_hist": [media] * len(hist_k), "partes": [],
                     "maior": maior, "sit": "acima" if acima(real, media) else "dentro"})
    return fora


def ordenar(linhas):
    """Acima primeiro (maior diferença antes), depois o que falta, depois o resto."""
    ordem = {"acima": 0, "falta": 1, "aguardando": 2, "dentro": 3}
    return sorted(linhas, key=lambda x: (ordem[x["sit"]],
                                         -((x["cobrado"] or 0.0) - x["estimado"]),
                                         x["item"]))


def excesso(linhas):
    """Quanto se cobrou acima do estimado, somando só os itens acima."""
    return round(sum((x["cobrado"] or 0.0) - x["estimado"]
                     for x in linhas if x["sit"] == "acima"), 2)


@st.cache_data(ttl=120, show_spinner=False)
def dados(ano, mes, atual):
    """Custo fixo, assinaturas e os lançamentos dos 4 meses. Cache de 120 s, o
    de `lancamentos.carregar`: o radio do mês redesenha a página."""
    import ajustes as _aj
    import assinaturas as _as
    import custo_fixo as _cf
    import lancamentos as _lan
    meses = meses_ate(ano, mes)
    alvo = {f"{a:04d}-{m:02d}": (a, m) for a, m in meses}
    por_mes = {}
    for l in _lan.aplicar_cadastro(_lan.carregar()):
        k = alvo.get(_lan.mes_de(l))
        if k:
            por_mes.setdefault(k, []).append(l)
    g = _cf.carregar("custo_fixo")
    linhas_cf = g.fillna("").to_dict("records") if not g.empty else []
    linhas_as = _as.carregar() or []
    itens, sem = fixos(linhas_cf, linhas_as, _aj.por_item(_aj.carregar()),
                       meses, por_mes, atual)
    return {"meses": meses, "itens": itens, "sem_item": sem,
            "lancs": por_mes.get(meses[-1]) or [], "tem_extrato": bool(por_mes.get(meses[-1])),
            "opcoes": ([f"Custo fixo › {str(l.get('item')).strip()}" for l in linhas_cf
                        if str(l.get("item") or "").strip()]
                       + [f"Assinatura › {str(l.get('item')).strip()}" for l in linhas_as
                          if str(l.get("item") or "").strip()])}


# ── Tela ─────────────────────────────────────────────────────────────────────

def _r(v):
    return ("− " if v < 0 else "") + "R$ " + f"{abs(v):,.0f}".replace(",", ".")


def _esc(t):
    import html as _h
    return _h.escape(str(t or ""))


def _barras(x, meses_txt):
    import visao_faturamento as _vf
    vals, ests = x["hist"], x["est_hist"]
    mx = max(vals + ests + [1.0])
    cel = ""
    for i, v in enumerate(vals):
        h = max(3, v / mx * 26)
        cor = _vf.RUIM if acima(v if v else None, ests[i]) else "#8f9aa8"
        borda = "outline:1px solid #E8EAED;" if i == len(vals) - 1 else ""
        cel += (f'<div title="{meses_txt[i]} {_r(v)}" style="width:14px;height:{h:.0f}px;'
                f'background:{cor};border-radius:2px;{borda}"></div>')
    linha = ests[-1] / mx * 26
    return (f'<div style="position:relative;display:flex;align-items:flex-end;gap:3px;height:28px">'
            f'{cel}<div style="position:absolute;left:0;right:0;bottom:{linha:.0f}px;'
            f'border-top:1px dashed #f0c060"></div></div>')


def _viu(x):
    """O que o Studio viu no item — a frase da última coluna."""
    if x["grupo"] == "variavel":
        m = x.get("maior")
        if not m:
            return ""
        d = str(m.get("data") or "")
        dt = f", {d[8:10]}/{d[5:7]}" if len(d) >= 10 and d[4] == "-" else ""
        nome = str(m.get("favorecido") or m.get("descricao") or "")[:28]
        return f"maior lançamento: {_r(-_num(m.get('valor')))} ({_esc(nome)}{dt})"
    p = x["partes"]
    if x["sit"] == "falta":
        return "previsto, sem débito no extrato — falta lançar?"
    if x["sit"] == "aguardando":
        return "ainda não cobrado neste mês"
    if len(p) > 1:
        return (f"{len(p)} cobranças no mês: "
                + " + ".join(_r(v).replace("R$ ", "") for v in p))
    return "1 cobrança no mês" if p else ""


def _linha(x, meses_txt):
    import visao_faturamento as _vf
    SEC, BORDA, RUIM, BOM = _vf.SEC, _vf.BORDA, _vf.RUIM, _vf.BOM
    est, cob = x["estimado"], x["cobrado"]
    dif = None if cob is None else round(cob - est, 2)

    def chip(t, c, bg):
        return (f'<span style="display:inline-block;padding:2px 8px;border-radius:999px;'
                f'font-size:11px;font-weight:700;background:{bg};color:{c}">{t}</span>')
    if x["sit"] == "acima":
        pc = f" · +{dif / est * 100:.0f}%" if est else " · sem estimado"
        c = chip(f"▲ {_r(dif)}{pc}", RUIM, "#4a2321")
    elif x["sit"] == "falta":
        c = chip("NÃO APARECEU", "#f0c060", "#4a3a1a")
    elif x["sit"] == "aguardando":
        c = chip("AINDA NÃO COBRADO", SEC, "#3a3a3a")
    else:
        c = chip("no estimado", BOM, "#1f4a36")
    vermelho = x["sit"] == "acima"
    fundo = "background:rgba(229,83,75,.08);" if vermelho else ""
    dif_txt = "—" if dif is None else ("+ " if dif > 0 else "") + _r(dif)
    return (f'<div style="display:grid;grid-template-columns:1.7fr 1fr 1fr 1fr 90px 1.5fr;gap:8px;'
            f'padding:8px 4px;border-top:1px solid {BORDA};font-size:13px;align-items:center;{fundo}">'
            f'<div><b style="color:#E8EAED">{_esc(x["item"])}</b><div style="margin-top:3px">{c}</div></div>'
            f'<span style="color:{SEC}">{_r(est)}</span>'
            f'<b style="color:{RUIM if vermelho else "#E8EAED"}">{"—" if cob is None else _r(cob)}</b>'
            f'<span style="color:{RUIM if vermelho else SEC}">{dif_txt}</span>'
            f'{_barras(x, meses_txt)}<span style="font-size:12px;color:{SEC}">{_viu(x)}</span></div>')


def _bloco(titulo, rotulo_est, nota, linhas, meses_txt, extra=""):
    import visao_faturamento as _vf
    V, SEC, MUTED, BORDA = _vf.VIDRO, _vf.SEC, _vf.MUTED, _vf.BORDA
    linhas = ordenar(linhas)
    fora = [x for x in linhas if x["sit"] != "dentro"]
    dentro = [x for x in linhas if x["sit"] == "dentro"]
    periodo = f"{meses_txt[0]}→{meses_txt[-1]}" if meses_txt else ""
    cab = (f'<div style="display:grid;grid-template-columns:1.7fr 1fr 1fr 1fr 90px 1.5fr;gap:8px;'
           f'font-size:11px;color:{MUTED};letter-spacing:.1em;padding-bottom:4px"><span>ITEM</span>'
           f'<span>{rotulo_est}</span><span>COBRADO</span><span>DIFERENÇA</span><span>{periodo}</span>'
           f'<span>O QUE O STUDIO VIU</span></div>')
    corpo = "".join(_linha(x, meses_txt) for x in fora)
    if not linhas:
        corpo = (f'<div style="font-size:13px;color:{SEC};padding:8px 4px;border-top:1px solid {BORDA}">'
                 f'Nada para comparar neste mês.</div>')
    elif not fora:
        corpo = (f'<div style="font-size:13px;color:{_vf.BOM};padding:8px 4px;border-top:1px solid {BORDA}">'
                 f'Tudo dentro do estimado.</div>')
    if dentro:
        corpo += (f'<details style="border-top:1px solid {BORDA};padding:8px 4px">'
                  f'<summary style="font-size:12px;color:{SEC};cursor:pointer">+ {len(dentro)} '
                  f'ite{"m" if len(dentro) == 1 else "ns"} dentro do estimado '
                  f'<span style="color:{MUTED}">(clique para ver)</span></summary>'
                  + "".join(_linha(x, meses_txt) for x in dentro) + '</details>')
    return (f'<div style="{V};padding:16px;margin-top:12px"><div style="display:flex;'
            f'justify-content:space-between;align-items:baseline;gap:12px"><div style="font-size:12px;'
            f'font-weight:800;letter-spacing:.14em;color:{SEC}">{titulo}</div><div style="font-size:11px;'
            f'color:{MUTED};text-align:right">{nota}</div></div><div style="margin-top:10px">{cab}{corpo}'
            f'{extra}</div></div>')


def _tile(nome, linhas, falta_txt=""):
    import visao_faturamento as _vf
    V, SEC, RUIM, BOM = _vf.VIDRO, _vf.SEC, _vf.RUIM, _vf.BOM
    exc = excesso(linhas)
    n = sum(1 for x in linhas if x["sit"] == "acima")
    nf = sum(1 for x in linhas if x["sit"] == "falta")
    extra = f" · {nf} não apareceu" if nf else ""
    return (f'<div style="{V};padding:14px"><div style="font-size:11px;color:{SEC};letter-spacing:.12em">'
            f'{nome}</div><div style="font-size:22px;font-weight:800;color:{RUIM if exc > 0 else BOM}">'
            f'{"+ " + _r(exc) if exc > 0 else "no estimado"}</div>'
            f'<div style="font-size:12px;color:{SEC}">cobrado acima do estimado, somando os itens</div>'
            f'<div style="font-size:12px;margin-top:4px;color:{RUIM if n else BOM}">'
            f'{n} item(ns) acima{extra}{falta_txt}</div></div>')


def html_desvios(mes_txt, ano, d, var, tem_media=True):
    """O layout aprovado em 07/11: três quadros e três blocos item a item."""
    import visao_faturamento as _vf
    SEC, MUTED, BORDA, AMB = _vf.SEC, _vf.MUTED, _vf.BORDA, "#f0c060"
    meses_txt = [MES3[m - 1] for _a, m in d["meses"]]
    cf = [x for x in d["itens"] if x["grupo"] == "custo_fixo"]
    asn = [x for x in d["itens"] if x["grupo"] == "assinaturas"]
    sem = d.get("sem_item") or []
    sem_txt = f" · {len(sem)} sem item" if sem else ""
    tiles = ('<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px">'
             + _tile("CUSTO FIXO", cf, sem_txt) + _tile("ASSINATURAS", asn)
             + _tile("VARIÁVEIS (sem mercadoria)", var) + '</div>')
    extra_sem = ""
    if sem:
        tot = round(sum(v for _n, v in sem), 2)
        extra_sem = (f'<div style="border-top:1px solid {BORDA};padding:10px 4px;font-size:13px;'
                     f'background:rgba(240,192,96,.07)"><b style="color:{AMB}">SEM ITEM · {_r(tot)}</b> '
                     f'<span style="color:{SEC}">— marcado como custo fixo/assinatura, mas o nome não bate '
                     f'com nenhum item: '
                     + " · ".join(f"{_esc(n)} ({_r(v)})" for n, v in sem[:8])
                     + (f" · e mais {len(sem) - 8}" if len(sem) > 8 else "")
                     + '. Ligue ao item logo abaixo, uma vez só.</span></div>')
    sem_ext = ("" if d.get("tem_extrato") else
               f'<div style="font-size:13px;color:{AMB};margin:8px 0">⏳ Nenhum lançamento gravado neste '
               f'mês: sem extrato, nada aparece como cobrado.</div>')
    nota_var = ("variável não tem estimado: a régua é a média dos 3 meses anteriores"
                if tem_media else "sem os meses anteriores deste ano, não há média para comparar")
    var_txt = [MES3[k - 1] for k in range(max(1, d["meses"][-1][1] - MESES_HIST + 1),
                                           d["meses"][-1][1] + 1)]
    return (f'<div style="background:radial-gradient(1200px 400px at 20% 0%,#454545 0%,{_vf.FUNDO} 60%);'
            f'border-radius:18px;padding:22px;border:1px solid {BORDA};margin-top:12px">'
            f'<div style="margin-bottom:14px"><div style="font-size:12px;font-weight:800;'
            f'letter-spacing:.14em;color:{SEC}">O QUE COBROU ACIMA DO ESTIMADO · {mes_txt} {ano}</div>'
            f'<div style="font-size:13px;color:{SEC};margin-top:4px">Mercadoria fica de fora: ela cresce '
            f'com o faturamento.</div></div>{sem_ext}{tiles}'
            + _bloco("CUSTO FIXO · item a item", "ESTIMADO",
                     "estimado = cadastro do Custo fixo, com os ajustes de valor", cf, meses_txt, extra_sem)
            + _bloco("ASSINATURAS · item a item", "ESTIMADO",
                     "estimado = valor mensal da aba Assinaturas", asn, meses_txt)
            + _bloco("VARIÁVEIS · exceto mercadoria", "MÉDIA 3 MESES", nota_var, var, var_txt)
            + f'<div style="font-size:12px;color:{SEC};margin-top:10px">Acima = mais de 10% e mais de '
              f'R$ 3 sobre o estimado (a mesma tolerância da tela de Assinaturas). Barras: um mês cada; '
              f'tracejado = o estimado; vermelho = mês que passou dele.</div></div>')


def _ligar(d, usuario_logado):
    """O "sem item" ligado ao item, uma vez: o nome entra no «Como aparece no
    extrato» pelo mesmo caminho da fila do Extratos (`gravar_apelidos`)."""
    import pandas as pd
    import extratos_tela as _ext
    sem = d.get("sem_item") or []
    if not sem or not d.get("opcoes"):
        return
    with st.expander(f"🔗 Ligar as {len(sem)} cobrança(s) sem item ao custo fixo ou assinatura"):
        df = pd.DataFrame([{"nome no extrato": n, "valor": v, "item": _ext.SEM_ITEM}
                           for n, v in sem])
        with st.form("desv_ligar_form"):
            ed = st.data_editor(
                df, hide_index=True, use_container_width=True, key="desv_ligar_ed",
                disabled=["nome no extrato", "valor"],
                column_config={"valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                               "item": st.column_config.SelectboxColumn(
                                   "Item", options=[_ext.SEM_ITEM] + d["opcoes"])})
            enviou = st.form_submit_button("💾 Ligar", type="primary")
        if not enviou:
            return
        apr = []
        for r in ed.to_dict("records"):
            esc = r.get("item")
            if isinstance(esc, str) and " › " in esc and r.get("nome no extrato"):
                origem, item = esc.split(" › ", 1)
                apr.append((origem, item, str(r["nome no extrato"])))
        if not apr:
            st.warning("Nada para ligar: escolha o item na linha.")
            return
        n, erros = _ext.gravar_apelidos(apr, usuario_logado)
        for e in erros:
            st.warning(f"Não liguei — {e}.")
        if n:
            dados.clear()
            st.success(f"✅ {n} nome(s) ligado(s). Daqui em diante entram sozinhos no item.")


def mostrar(ano, mes, mes_txt, valores, usuario_logado=None):
    """Desenha o bloco abaixo do painel do mês."""
    from datetime import datetime
    import placar_core as _pc
    hoje = datetime.now(_pc.FUSO).date()
    atual = (int(ano), int(mes)) == (hoje.year, hoje.month)
    try:
        d = dados(int(ano), int(mes), atual)
    except Exception as e:
        st.warning(f"Desvio item a item sem dados: {type(e).__name__}: {str(e)[:120]}")
        return
    m = int(mes)
    var = variaveis(valores, m, d["lancs"])
    tem_media = any(k in (valores or {}) for k in range(m - MESES_MEDIA, m) if k >= 1)
    st.markdown(html_desvios(mes_txt, ano, d, var, tem_media), unsafe_allow_html=True)
    _ligar(d, usuario_logado)


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import inspect as _insp
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    ok("os 4 meses atravessam o ano", meses_ate(2026, 2) == [(2025, 11), (2025, 12), (2026, 1), (2026, 2)])

    # A ENTRADA VEM DO SISTEMA: cadastro nas colunas de `custo_fixo.COLUNAS`
    # e `assinaturas.COLUNAS`, lançamentos na forma de `lancamentos.carregar`
    # (saída negativa), e o cobrado por `custo_real.cobrancas_no_mes` de verdade.
    import custo_fixo as _cf_t
    import assinaturas as _as_t
    _cf = [dict({c: "" for c in _cf_t.COLUNAS}, item="Energia", valor_mensal=820,
                vigente_desde="2026-01", favorecido="ENEL"),
           dict({c: "" for c in _cf_t.COLUNAS}, item="Aluguel", valor_mensal=1350,
                vigente_desde="2026-01", favorecido="IMOBILIARIA SOL")]
    _as = [dict({c: "" for c in _as_t.COLUNAS}, item="Claude Code", valor_mensal=500,
                periodicidade="Mensal", favorecido="CLAUDE"),
           dict({c: "" for c in _as_t.COLUNAS}, item="Adobe", valor_mensal=1200,
                periodicidade="Anual", favorecido="ADOBE")]

    def L(v, fav, fin, desc="", data="2026-10-05"):
        return {"valor": v, "favorecido": fav, "descricao": desc, "finalidade": fin,
                "data": data, "tipo": ""}
    _meses = meses_ate(2026, 10)
    _pm = {(2026, 7): [L(-820, "ENEL", "CUSTO FIXO"), L(-500, "CLAUDE.AI SUBSCRIPTION", "CUSTO FIXO"),
                       L(-1350, "IMOBILIARIA SOL", "CUSTO FIXO")],
           (2026, 8): [L(-830, "ENEL", "CUSTO FIXO"), L(-500, "CLAUDE.AI", "CUSTO FIXO"),
                       L(-1350, "IMOBILIARIA SOL", "CUSTO FIXO")],
           (2026, 9): [L(-810, "ENEL", "CUSTO FIXO"), L(-500, "CLAUDE.AI", "CUSTO FIXO"),
                       L(-1350, "IMOBILIARIA SOL", "CUSTO FIXO")],
           (2026, 10): [L(-610, "ENEL", "CUSTO FIXO"), L(-630, "ENEL", "CUSTO FIXO"),
                        L(-500, "CLAUDE.AI SUBSCRIPTION", "CUSTO FIXO"),
                        L(-310.0, "CLAUDE.AI USAGE", "CUSTO FIXO"),
                        L(-290.0, "CLAUDE.AI USAGE", "CUSTO FIXO"),
                        L(-330.0, "ANTHROPIC", "ASSINATURAS"),
                        L(-90.0, "Porta 2 Relógio + Jóias", "CUSTO FIXO"),
                        L(400.0, "ENEL", "CUSTO FIXO"),
                        L(-5000.0, "FORNECEDOR X", "MERCADORIA")]}
    _it, _sem = fixos(_cf, _as, {}, _meses, _pm)
    _por = {x["item"]: x for x in _it}
    ok("o Claude Code soma o plano e as cobranças de uso com o mesmo nome",
       _por["Claude Code"]["cobrado"] == 1100.0 and _por["Claude Code"]["sit"] == "acima")
    ok("e lista cada cobrança", sorted(_por["Claude Code"]["partes"]) == [290.0, 310.0, 500.0])
    ok("a régua é o CADASTRO, e não o real do extrato", _por["Claude Code"]["estimado"] == 500.0)
    ok("energia em duas cobranças passa do estimado",
       _por["Energia"]["cobrado"] == 1240.0 and _por["Energia"]["sit"] == "acima")
    ok("entrada (estorno) não soma como cobrança", 400.0 not in _por["Energia"]["partes"])
    ok("previsto sem débito vira 'não apareceu'", _por["Aluguel"]["sit"] == "falta")
    ok("no mês corrente, o que não apareceu ainda pode aparecer",
       {x["item"]: x for x in fixos(_cf, _as, {}, _meses, _pm, atual=True)[0]}["Aluguel"]["sit"]
       == "aguardando")
    ok("assinatura anual não cobra presença todo mês", _por["Adobe"]["sit"] == "dentro")
    ok("o histórico tem um valor por mês", _por["Claude Code"]["hist"] == [500.0, 500.0, 500.0, 1100.0])
    ok("cobrança de assinatura com nome sem item vai para SEM ITEM, e não some",
       dict(_sem).get("ANTHROPIC") == 330.0)
    # Passo 13: o pior nome real passa (símbolo, acento, maiúscula).
    ok("o nome com + e acento chega inteiro ao SEM ITEM",
       dict(_sem).get("Porta 2 Relógio + Jóias") == 90.0)
    ok("mercadoria não entra no SEM ITEM", "FORNECEDOR X" not in dict(_sem))
    ok("o casamento é o de custo_real (uma regra só)",
       "_cr.cobrancas_no_mes(" in _insp.getsource(fixos)
       and "_casa(" not in _insp.getsource(fixos))
    ok("a régua do custo fixo leva os ajustes de valor",
       "valor_no_mes(" in _insp.getsource(fixos))
    ok("'acima' é a tolerância das Assinaturas",
       "_fora_da_tolerancia(" in _insp.getsource(acima)
       and acima(550.0, 500.0) is False and acima(560.0, 500.0) is True
       and acima(5.0, 2.5) is False)

    # VARIÁVEIS PELA CADEIA: `valores` na forma de `visao_geral.resumo`.
    import visao_geral as _vg_t
    _itens = []
    for _m, _fin, _v in ((7, "FRETE", 5900), (8, "FRETE", 6400), (9, "FRETE", 6300), (10, "FRETE", 9850),
                         (7, "EMBALAGEM", 1000), (8, "EMBALAGEM", 1000), (9, "EMBALAGEM", 1000),
                         (10, "EMBALAGEM", 1020), (10, "MERCADORIA", 140000), (10, "CUSTO FIXO", 7000),
                         (10, "SERVIÇOS", 300), (9, "SERVIÇO", 100)):
        _itens.append({"mes": f"2026-{_m:02d}", "finalidade": _fin, "valor": _v, "fonte": "S",
                       "modalidade": "PIX"})
    _vals, _ = _vg_t.resumo(_itens, 2026)
    _var = {x["item"]: x for x in variaveis(_vals, 10, [L(-2300, "JADLOG", "FRETE", data="2026-10-14"),
                                                         L(-100, "CORREIOS", "FRETE")])}
    ok("frete contra a média dos 3 meses anteriores",
       _var["Frete"]["estimado"] == round((5900 + 6400 + 6300) / 3, 2) and _var["Frete"]["sit"] == "acima")
    ok("e mostra o maior lançamento", "JADLOG" in _viu(_var["Frete"]) and "14/10" in _viu(_var["Frete"]))
    ok("variação pequena fica dentro", _var["Embalagem"]["sit"] == "dentro")
    ok("mercadoria e compromissos ficam fora das variáveis",
       "Mercadoria" not in _var and "Custo fixo" not in _var)
    ok("SERVIÇO e SERVIÇOS são uma finalidade só (visao_geral.finalidade)",
       sum(1 for k in _var if k.upper().startswith("SERVI")) == 1)
    ok("sem meses anteriores no ano, não há régua", variaveis(_vals, 7, []) == [])

    # A TELA DESENHA.
    _d = {"meses": _meses, "itens": _it, "sem_item": _sem, "tem_extrato": True}
    _h = html_desvios("OUT", 2026, _d, list(_var.values()))
    ok("os três blocos aparecem", all(t in _h for t in ("CUSTO FIXO · item a item",
                                                        "ASSINATURAS · item a item",
                                                        "VARIÁVEIS · exceto mercadoria")))
    ok("o Claude Code aparece acima, com as cobranças", "Claude Code" in _h and "3 cobranças no mês" in _h)
    ok("o SEM ITEM aparece com o nome", "SEM ITEM" in _h and "ANTHROPIC" in _h)
    ok("o nome do extrato vai escapado ao HTML", "Porta 2 Relógio + Jóias" in _h
       and "<script>" not in html_desvios("OUT", 2026, dict(_d, sem_item=[("<script>", 1.0)]), []))
    ok("o que está dentro fica recolhido", "<details" in _h and "dentro do estimado" in _h)
    ok("sem link: nada aqui navega (Regra 12)", "<a " not in _h and "href" not in _h)
    ok("o HTML não tem linha só de espaço", all(l.strip() for l in _h.split("\n")))
    ok("mês sem extrato diz isso",
       "Nenhum lançamento gravado" in html_desvios("NOV", 2026, dict(_d, tem_extrato=False), []))

    print(f"\nfalhas: {falhas}")
    raise SystemExit(1 if falhas else 0)
