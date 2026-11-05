"""visao_financeira.py — o mês financeiro de bater o olho (layout A, dono, 05/11).

O PEDIDO
--------
"Eu preciso ver o balanço de saídas e entradas, se o que foi faturado cobriu
as saídas, se o mês foi verde ou vermelho, quanto gastamos a mais (...)
preciso bater o olho e ter as informações claras." E as regras dele:

    1. A régua é o DINHEIRO QUE ENTROU NA CONTA (extratos), e não o faturado.
    2. Mercadoria é prioridade DEPOIS dos compromissos previstos (custo fixo,
       assinaturas, cheques, folha...); o que sobra fica para consumo interno
       e outros. Impostos NÃO entram nos previstos (05/11): vão para "outros".
    3. Lucro bruto e líquido do mês pela planilha; linha sem preenchimento
       entra como "aguardando informação".

NADA AQUI É UMA SEGUNDA RESPOSTA
--------------------------------
    saídas por finalidade   `visao_geral.resumo` — a mesma tabela de baixo
    entradas                `lancamentos` com `favorecidos.eh_faturamento`
                            e `consome_meta` (transferência, aplicação,
                            empréstimo e reembolso ficam fora)
    previsto                `previsto.do_mes` (custo fixo, folha, não
                            operacional), `custo_real.total_assinaturas`, e os
                            cheques que VENCEM no mês (`cheques.do_mes`)
    mercadoria              `meta_gastos.FLEXIVEIS`
    lucro bruto             coluna L.B (`visao_faturamento.resumo_mensal`)
    lucro líquido           MC − LPV × vendas — a conta da Home
                            (`home_gestao.py`, "_ll_venda = (_mc_venda - _lpv)")

ENTRADA SÓ EXISTE ONDE HÁ EXTRATO
---------------------------------
A planilha (SAIDAS PIX-BOLETO, CARTÕES) só tem SAÍDAS. Mês em que um banco veio
da planilha não tem as entradas daquele banco, e a tela diz isso — senão o mês
sairia vermelho por falta de dado, e não por falta de dinheiro.
"""
import streamlit as st

# Os compromissos: o que o mês já deve antes de comprar mercadoria (dono,
# 03/11 e 05/11). Impostos ficaram de fora por decisão dele.
COMPROMISSOS = ("CUSTO FIXO", "ASSINATURAS", "FOLHA", "NÃO OPERACIONAL",
                "CHEQUES")
ROTULO = {"CUSTO FIXO": "Custo fixo", "ASSINATURAS": "Assinaturas",
          "FOLHA": "Folha", "NÃO OPERACIONAL": "Não operacional",
          "CHEQUES": "Cheques", "MERCADORIA": "Mercadoria"}


def grupo(fin):
    """'compromissos', 'mercadoria' ou 'outros'. Pura."""
    import meta_gastos as _mg
    import visao_geral as _vg
    f = _vg.finalidade(fin)
    if f in COMPROMISSOS:
        return "compromissos"
    if f in _mg.FLEXIVEIS:
        return "mercadoria"
    return "outros"


def entradas(lancs):
    """(entrou, sem_classificacao, por_finalidade) dos lançamentos. Pura.

    Entrou = venda que caiu na conta. Transferência entre contas, aplicação,
    empréstimo, reembolso e rateio não são venda. Entrada sem finalidade não
    soma: ela aparece à parte, para ser classificada.
    """
    import favorecidos as _fv
    entrou, sem, por = 0.0, 0.0, {}
    for l in lancs or []:
        v = float(l.get("valor") or 0.0)
        if v <= 0:
            continue
        fin = str(l.get("finalidade") or "").strip().upper()
        if not fin:
            sem += v
            continue
        if not (_fv.eh_faturamento(fin) and _fv.consome_meta(fin)):
            continue
        entrou += v
        por[fin] = por.get(fin, 0.0) + v
    return round(entrou, 2), round(sem, 2), {k: round(v, 2) for k, v in por.items()}


def por_grupo(saidas):
    """{grupo: total} e {grupo: {finalidade: valor}} das saídas do mês. Pura."""
    tot = {"compromissos": 0.0, "mercadoria": 0.0, "outros": 0.0}
    det = {"compromissos": {}, "mercadoria": {}, "outros": {}}
    for fin, v in (saidas or {}).items():
        g = grupo(fin)
        tot[g] += float(v or 0.0)
        det[g][fin] = det[g].get(fin, 0.0) + float(v or 0.0)
    return {k: round(v, 2) for k, v in tot.items()}, det


def cascata(entrou, tot):
    """Os quatro passos, na ordem da prioridade. Pura.

    [(rótulo, gasto, restou)] — o primeiro é o que entrou. `restou` negativo
    é a etapa que gastou mais do que tinha: é ali que a margem foi puxada.
    """
    passos = [("Entraram na conta", entrou, entrou)]
    resto = entrou
    for rot, g in (("Pagamos os compromissos", "compromissos"),
                   ("Compramos mercadoria", "mercadoria"),
                   ("Gastamos com consumo e outros", "outros")):
        resto = round(resto - tot[g], 2)
        passos.append((rot, tot[g], resto))
    return passos


def desvios(previsto, saidas, tot, entrou):
    """[(nome, previsto, realizado, situacao, nota)], o maior estouro primeiro.

    Compromissos contra o previsto de cada um; mercadoria contra o que restou
    depois dos compromissos; consumo e outros contra o que restou depois da
    mercadoria. `situacao`: 'acima', 'dentro' ou 'falta' (previsto sem nada
    pago — falta lançar?). Pura.
    """
    import visao_geral as _vg
    real = {}
    for fin, v in (saidas or {}).items():
        f = _vg.finalidade(fin)
        real[f] = real.get(f, 0.0) + float(v or 0.0)
    fora = []
    for f in COMPROMISSOS:
        p = round(float((previsto or {}).get(f) or 0.0), 2)
        r = round(real.get(f, 0.0), 2)
        if not p and not r:
            continue
        if p and r < p * 0.5:
            sit = "falta"
        elif r > p + 0.5:
            sit = "acima"
        else:
            sit = "dentro"
        fora.append((ROTULO.get(f, f.title()), p, r, sit, ""))
    disp = round((entrou or 0.0) - tot["compromissos"], 2)
    sobra = round(disp - tot["mercadoria"], 2)
    for nome, p, r in (("Mercadoria", disp, tot["mercadoria"]),
                       ("Consumo interno e outros", sobra, tot["outros"])):
        if entrou is None:
            break
        nota = "do que restou" if nome == "Mercadoria" else "da sobra"
        if p < 0:
            p, nota = 0.0, "não restou nada"
        fora.append((nome, p, r, "acima" if r > p + 0.5 else "dentro", nota))
    ordem = {"acima": 0, "falta": 1, "dentro": 2}
    return sorted(fora, key=lambda x: (ordem[x[3]], -(x[2] - x[1])))


def lucro(r_mes, lpv):
    """(bruto, líquido, aguardando) do mês na BASE DE VENDAS. Pura.

    Líquido = margem de contribuição − LPV × vendas, a conta da Home. Sem
    LPV, o líquido é None. `aguardando` conta as linhas sem custo ou sem
    SKU — o número existe, mas ainda pode mudar.
    """
    if not r_mes or not r_mes.get("linhas"):
        return None, None, 0
    bruto = round(r_mes["lb"], 2)
    liq = (round(r_mes.get("mc", 0.0) - float(lpv) * r_mes["vendas"], 2)
           if lpv else None)
    return bruto, liq, int(r_mes.get("sem_custo", 0)) + int(r_mes.get("sem_sku", 0))


def previsto_do_mes(ano, mes):
    """({compromisso: previsto}, erros). Cheque previsto é o que VENCE no mês,
    baixado ou não — o que já baixou também era compromisso."""
    import previsto as _pv
    prev, erros = _pv.do_mes(int(ano), int(mes))
    fora = {f: float(prev.get(f) or 0.0)
            for f in ("CUSTO FIXO", "FOLHA", "NÃO OPERACIONAL")}
    try:
        import assinaturas as _as
        import custo_real as _cr
        fora["ASSINATURAS"] = float(_cr.total_assinaturas(
            _as.carregar() or [], int(ano), int(mes), _cr.carregar()) or 0.0)
    except Exception as e:
        erros = list(erros) + [f"assinaturas: {type(e).__name__}"]
    try:
        import cheques as _ch
        fora["CHEQUES"] = round(sum(
            _ch._num(l.get("valor")) for l in _ch.do_mes(_ch.carregar(), ano, mes)
            if _ch.eh_tipo(l, "CHEQUE")), 2)
    except Exception as e:
        erros = list(erros) + [f"cheques: {type(e).__name__}"]
    return fora, list(erros)


@st.cache_data(ttl=120, show_spinner=False)
def dados_do_mes(ano, mes):
    """Entradas do mês e do anterior, previsto e lucro. Cache de 120 s, o mesmo
    de `lancamentos.carregar`: o radio do mês redesenha a página."""
    import lancamentos as _lan
    import visao_faturamento as _vf
    alvo = f"{int(ano):04d}-{int(mes):02d}"
    a_ano, a_mes = (int(ano) - 1, 12) if int(mes) == 1 else (int(ano), int(mes) - 1)
    alvo_ant = f"{a_ano:04d}-{a_mes:02d}"
    todos = _lan.carregar()
    do_mes = _lan.aplicar_cadastro([l for l in todos if _lan.mes_de(l) == alvo])
    do_ant = _lan.aplicar_cadastro([l for l in todos if _lan.mes_de(l) == alvo_ant])
    contas = sorted({str(l.get("conta") or "") for l in do_mes
                     if not str(l.get("conta") or "").startswith(_lan.CONTA_CARTAO)})
    prev, erros = previsto_do_mes(ano, mes)
    plan, av = _vf.ler_planilha()
    base = plan.get("base") or []
    meses = _vf.resumo_mensal(base, int(ano), _vf.lpv_atual(base))
    return {"entradas": entradas(do_mes), "entradas_ant": entradas(do_ant),
            "contas": contas, "previsto": prev, "erros": erros + list(av),
            "base_mes": meses.get(int(mes)), "tem_ant": bool(do_ant)}


# ── Tela ─────────────────────────────────────────────────────────────────────

def _dinheiro(v):
    if v is None:
        return "—"
    return ("− " if v < 0 else "") + "R$ " + f"{abs(v):,.0f}".replace(",", ".")


def _chip(txt, bom, cor=None):
    import visao_faturamento as _vf
    c = cor or (_vf.BOM if bom else _vf.RUIM)
    bg = "#4a3a1a" if cor else ("#1f4a36" if bom else "#4a2321")
    return (f'<span style="display:inline-block;padding:2px 8px;border-radius:999px;'
            f'font-size:11px;font-weight:700;background:{bg};color:{c}">{txt}</span>')


def _variacao(atual, antes, gasto=False):
    if not antes or atual is None:
        return ""
    pc = (atual / antes - 1) * 100
    bom = (pc <= 0) if gasto else (pc >= 0)
    seta = "▲" if pc >= 0 else "▼"
    return (_chip(f"{seta} {abs(pc):.1f}%".replace(".", ","), bom)
            + ' <span style="color:#6b737c">vs mês anterior</span>')


def html_painel(mes_txt, ano, entrou, saiu, saiu_ant, d, saidas, lpv, parcial):
    """O layout A aprovado (05/11): placar, para onde foi o dinheiro e onde o
    gasto fugiu do previsto."""
    import visao_faturamento as _vf
    V, SEC, MUTED, BORDA = _vf.VIDRO, _vf.SEC, _vf.MUTED, _vf.BORDA
    BOM, RUIM, AMB = _vf.BOM, _vf.RUIM, "#f0c060"
    tot, _det = por_grupo(saidas)
    # Extrato lido sem nenhuma venda entrando também não dá régua: dividir
    # por zero, e um "vermelho" que é falta de dado, e não de dinheiro.
    sem_ext = entrou is None or entrou <= 0
    msg_sem = ("sem extrato de entrada" if entrou is None
               else "nenhuma entrada de venda lida")
    res = None if sem_ext else round(entrou - saiu, 2)
    bruto, liq, aguard = lucro(d.get("base_mes"), lpv)

    def kp(a, b, c, cor="#E8EAED"):
        return (f'<div style="{V};padding:14px"><div style="font-size:11px;color:{SEC};'
                f'letter-spacing:.12em">{a}</div><div style="font-size:24px;font-weight:800;'
                f'color:{cor}">{b}</div><div style="font-size:11px;margin-top:2px">{c}</div></div>')
    ent_sub = (_chip(f"⏳ {msg_sem}", True, AMB) if sem_ext else
               (_chip("⚠️ parcial: há banco vindo da planilha", True, AMB) if parcial
                else _variacao(entrou, d["entradas_ant"][0] if d.get("tem_ant") else None)))
    if d["entradas"][1]:
        ent_sub += (f'<div style="color:{AMB};margin-top:3px">+ {_dinheiro(d["entradas"][1])} '
                    f'de entrada sem classificação</div>')
    if aguard:
        liq_sub = _chip(f"⏳ {aguard} linha(s) aguardando informação", True, AMB)
    elif liq is None:
        liq_sub = f'<span style="color:{SEC}">falta o LPV do mês</span>'
    else:
        liq_sub = f'<span style="color:{SEC}">margem − LPV × vendas</span>'
    kpis = ('<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px">'
            + kp("ENTROU NA CONTA", _dinheiro(entrou), ent_sub)
            + kp("SAIU DA CONTA", _dinheiro(saiu), _variacao(saiu, saiu_ant, gasto=True))
            + kp("LUCRO BRUTO", _dinheiro(bruto),
                 (_chip(f"⏳ {aguard} linha(s) aguardando informação", True, AMB)
                  if aguard else f'<span style="color:{SEC}">L.B da BASE DE VENDAS</span>'),
                 AMB if aguard else "#E8EAED")
            + kp("LUCRO LÍQUIDO", _dinheiro(liq), liq_sub, AMB if aguard else "#E8EAED")
            + '</div>')
    # A rosca: quanto das saídas o que entrou cobriu.
    if sem_ext or not saiu:
        rosca = (f'<div style="font-size:40px">⏳</div><div style="font-size:12px;color:{SEC};'
                 f'text-align:center">{msg_sem}<br>neste mês</div>')
    else:
        pct = entrou / saiu * 100
        svg = _vf._svg_donut(pct).replace("DA META", "COBERTO")
        if pct < 100:
            svg = svg.replace(_vf.VERDE_A, "#f08a84").replace("#1f8f5c", "#9c3a35")
        rosca = (svg + f'<div style="font-size:12px;color:{SEC};margin-bottom:4px">'
                 'do que saiu, o que entrou cobriu</div>'
                 + f'<div style="font-size:12px;color:{SEC}">'
                 + (f'sobraram <b style="color:{BOM}">{_dinheiro(res)}</b>' if res >= 0
                    else f'faltaram <b style="color:{RUIM}">{_dinheiro(-res)}</b>') + '</div>')
    # Para onde foi o dinheiro.
    if sem_ext:
        onde = (f'<div style="color:{SEC};font-size:14px">{msg_sem.capitalize()} neste mês: '
                f'o Studio sabe o que saiu ({_dinheiro(saiu)}), mas não o que entrou.</div>')
    else:
        base_ = max(entrou, saiu, 1.0)
        partes = [("Compromissos", tot["compromissos"], "#8f9aa8"),
                  ("Mercadoria", tot["mercadoria"], _vf.AZUL_A),
                  ("Consumo e outros", tot["outros"], AMB)]
        if res > 0:
            partes.append(("Sobrou", res, BOM))
        barra = "".join(
            f'<div style="width:{v / base_ * 100:.2f}%;background:{c};display:flex;flex-direction:column;'
            f'justify-content:center;align-items:center;color:#1b1b1b;font-weight:800;font-size:12px;'
            f'line-height:1.15;overflow:hidden;white-space:nowrap">'
            + (f'<span>{n}</span>' if v / base_ >= 0.09 else "")
            + f'<span style="font-size:15px">R$ {v / entrou * 100:.0f}</span></div>'
            for n, v, c in partes if v > 0)
        legenda = " &nbsp; ".join(
            f'<span style="color:{c}">■</span> {n}' for n, v, c in partes if v > 0)
        lin = ""
        for i, (txt, v, depois) in enumerate(cascata(entrou, tot)):
            cor = ("#E8EAED", "#8f9aa8", _vf.AZUL_A, AMB)[i]
            num = (f'<div style="width:28px;height:28px;border-radius:50%;background:{cor};color:#1b1b1b;'
                   f'font-weight:900;display:flex;align-items:center;justify-content:center">{i + 1}</div>')
            if i == 0:
                resto = ""
            elif depois < 0:
                resto = (f'<span style="color:{RUIM}">→ faltaram <b>{_dinheiro(-depois)}</b></span>')
            else:
                palavra = "sobraram" if i == 3 else "restaram"
                resto = (f'<span style="color:{SEC}">→ {palavra}</span> '
                         f'<b style="color:{BOM if i == 3 else "#E8EAED"}">{_dinheiro(depois)}</b>')
            fundo = "background:#4a2321;" if (i and depois < 0) else ""
            lin += (f'<div style="display:grid;grid-template-columns:38px 1fr 150px 230px;align-items:center;'
                    f'gap:10px;padding:8px 6px;border-bottom:1px solid {BORDA};font-size:14px;{fundo}">'
                    f'{num}<span>{txt}</span><b style="text-align:right;color:{cor}">'
                    f'{"" if i == 0 else "− "}{_dinheiro(v)}</b><span style="text-align:right">{resto}</span></div>')
        cab_ = ('De cada <b>R$ 100</b> que entraram na conta:' if res >= 0 else
                f'Para cada <b>R$ 100</b> que entraram, saíram <b style="color:{RUIM}">'
                f'R$ {saiu / entrou * 100:.0f}</b>:')
        onde = (f'<div style="font-size:14px;margin-bottom:8px">{cab_}</div>'
                f'<div style="display:flex;height:60px;border-radius:10px;overflow:hidden;gap:2px;'
                f'background:#222">{barra}</div>'
                f'<div style="font-size:11px;color:{SEC};margin-top:4px">{legenda}</div>'
                f'<div style="margin-top:10px">{lin}</div>'
                f'<div style="margin-top:8px;font-size:12px;color:{SEC}">Primeiro os compromissos '
                f'(custo fixo, assinaturas, folha, não operacional e cheques), depois a mercadoria, e o '
                f'que sobra paga consumo e outros — impostos inclusive. Etapa que gastou mais do que '
                f'tinha fica <b style="color:{RUIM}">vermelha</b>.</div>')
    # Onde o gasto fugiu do previsto.
    lins = ""
    for nome, p, r, sit, nota in desvios(d.get("previsto"), saidas, tot, entrou):
        dif = r - p
        if sit == "falta":
            c = _chip("FALTA LANÇAR?", True, AMB)
        elif sit == "acima":
            c = _chip(f"▲ {_dinheiro(dif)}", False)
        else:
            c = _chip(f"▼ {_dinheiro(-dif)}" if dif < 0 else "no previsto", True)
        lins += (f'<div style="display:grid;grid-template-columns:1.6fr 1fr 1fr 1.2fr;gap:8px;padding:8px 0;'
                 f'border-bottom:1px solid {BORDA};font-size:13px;align-items:center"><b>{nome}</b>'
                 f'<span style="color:{SEC}">{_dinheiro(p)} <span style="font-size:10px">{nota}</span></span>'
                 f'<span>{_dinheiro(r)}</span><span>{c}</span></div>')
    tab = (f'<div style="display:grid;grid-template-columns:1.6fr 1fr 1fr 1.2fr;gap:8px;font-size:11px;'
           f'color:{MUTED};letter-spacing:.1em"><span>FINALIDADE</span><span>PREVISTO</span>'
           f'<span>REALIZADO</span><span>DESVIO</span></div>' + lins)
    tit = lambda t: (f'<div style="font-size:11px;font-weight:800;letter-spacing:.14em;color:{SEC};'
                     f'margin-bottom:10px">{t}</div>')
    if sem_ext:
        topo = f'<div style="font-size:20px;font-weight:800;color:{AMB}">⏳ {msg_sem}</div>'
    else:
        topo = (f'<div style="font-size:22px;font-weight:800;color:{BOM if res >= 0 else RUIM}">'
                f'{"+ " if res >= 0 else ""}{_dinheiro(res)} {"🟢" if res >= 0 else "🔴"}</div>')
    return (f'<div style="background:radial-gradient(1200px 400px at 20% 0%,#454545 0%,{_vf.FUNDO} 60%);'
            f'border-radius:18px;padding:22px;border:1px solid {BORDA}">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:16px">'
            f'<div><div style="font-size:22px;font-weight:300;letter-spacing:.42em">MARTINSOUSA</div>'
            f'<div style="font-size:12px;color:{SEC};letter-spacing:.14em;margin-top:2px">'
            f'FINANCEIRO · {mes_txt} {ano}</div></div>'
            f'<div style="text-align:right;font-size:12px;color:{SEC}">Resultado do mês{topo}</div></div>'
            f'<div style="display:grid;grid-template-columns:230px 1fr;gap:12px;margin-bottom:12px">'
            f'<div style="{V};padding:10px;display:flex;flex-direction:column;align-items:center;'
            f'justify-content:center">{rosca}</div>'
            f'<div>{kpis}<div style="{V};padding:16px;margin-top:12px">{tit("PARA ONDE FOI O DINHEIRO")}'
            f'{onde}</div></div></div>'
            f'<div style="{V};padding:16px">{tit("ONDE O GASTO FUGIU DO PREVISTO · MAIOR DESVIO PRIMEIRO")}'
            f'{tab}</div></div>')


def mostrar(ano, mes, mes_txt, valores, fontes, lpv):
    """Desenha o painel do mês. `valores`/`fontes` são os de `visao_geral.resumo`."""
    try:
        d = dados_do_mes(int(ano), int(mes))
    except Exception as e:
        st.warning(f"Painel do mês sem dados: {type(e).__name__}: {str(e)[:120]}")
        return
    saidas = valores.get(int(mes)) or {}
    saiu = round(sum(saidas.values()), 2)
    ant = valores.get(int(mes) - 1) if int(mes) > 1 else None
    saiu_ant = round(sum(ant.values()), 2) if ant else None
    tem_extrato = bool(d["contas"])
    entrou = d["entradas"][0] if tem_extrato else None
    parcial = "P" in (fontes.get(int(mes)) or set())
    st.markdown(html_painel(mes_txt, ano, entrou, saiu, saiu_ant, d, saidas,
                            lpv.get(int(mes)), parcial), unsafe_allow_html=True)
    if tem_extrato:
        st.caption("Entradas lidas dos extratos de: " + " · ".join(d["contas"]))
    for e in d["erros"]:
        st.caption(f"⚠️ {e}")


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import inspect as _insp
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # A ENTRADA VEM DO SISTEMA: linhas na forma de `lancamentos.carregar`,
    # com as finalidades que `favorecidos` grava.
    _l = [{"valor": 1000.0, "finalidade": "MERCADO LIVRE"},
          {"valor": 500.0, "finalidade": "SHOPEE"},
          {"valor": 9000.0, "finalidade": "TRANSFERENCIA ENTRE CONTAS"},
          {"valor": 300.0, "finalidade": "APLICACAO"},
          {"valor": 200.0, "finalidade": "REEMBOLSO"},
          {"valor": 50000.0, "finalidade": "EMPRESTIMO PRONAMP"},
          {"valor": 70.0, "finalidade": ""},
          {"valor": -400.0, "finalidade": "MERCADORIA"}]
    _e = entradas(_l)
    ok("entrou é só venda: transferência, aplicação, reembolso e empréstimo ficam fora",
       _e[0] == 1500.0)
    ok("entrada sem finalidade aparece à parte, e não soma", _e[1] == 70.0)

    # OS GRUPOS DA PRIORIDADE, com as grafias que `visao_geral.resumo` produz.
    ok("compromissos: custo fixo, assinaturas, folha, não operacional e cheques",
       all(grupo(f) == "compromissos" for f in
           ("CUSTO FIXO", "ASSINATURAS", "FOLHA", "NÃO OPERACIONAL",
            "NAO OPERACIONAL", "CHEQUES")))
    ok("impostos NÃO são compromisso (dono, 05/11): vão para outros",
       grupo("IMPOSTOS") == "outros" and grupo("IMPOSTO") == "outros"
       and grupo("DAS") == "outros")
    ok("mercadoria é a de meta_gastos.FLEXIVEIS", grupo("MERCADORIA") == "mercadoria")

    # A CASCATA FECHA: os gastos somam o que saiu e o último passo é o resultado.
    _s = {"CUSTO FIXO": 7000.0, "CHEQUES": 60000.0, "FOLHA": 25000.0,
          "MERCADORIA": 139000.0, "IMPOSTOS": 800.0, "CONSUMO INTERNO": 6000.0}
    _t, _ = por_grupo(_s)
    _c = cascata(250000.0, _t)
    ok("a cascata fecha: o último resto é entrou − saiu",
       _c[-1][2] == round(250000.0 - sum(_s.values()), 2))
    ok("e os três gastos somam o que saiu",
       round(sum(p[1] for p in _c[1:]), 2) == round(sum(_s.values()), 2))
    _c2 = cascata(80000.0, _t)
    ok("etapa que gasta mais do que tinha fica negativa (a tela pinta de vermelho)",
       _c2[2][2] < 0)

    # O DESVIO: cheque acima do previsto, custo fixo sem débito, maior primeiro.
    _dv = desvios({"CUSTO FIXO": 7000.0, "CHEQUES": 55000.0, "FOLHA": 25000.0,
                   "ASSINATURAS": 2000.0},
                  {"CUSTO FIXO": 1400.0, "CHEQUES": 60753.0, "FOLHA": 25000.0,
                   "MERCADORIA": 139000.0}, por_grupo(
                      {"CUSTO FIXO": 1400.0, "CHEQUES": 60753.0, "FOLHA": 25000.0,
                       "MERCADORIA": 139000.0})[0], 268400.0)
    _nomes = [x[0] for x in _dv]
    ok("o maior estouro vem primeiro", _nomes[0] == "Cheques" and _dv[0][3] == "acima")
    ok("previsto sem débito vira 'falta lançar?'",
       dict((x[0], x[3]) for x in _dv)["Custo fixo"] == "falta")
    ok("assinatura prevista e não paga também aparece",
       dict((x[0], x[3]) for x in _dv)["Assinaturas"] == "falta")
    ok("mercadoria contra o que restou dos compromissos",
       dict((x[0], x[1]) for x in _dv)["Mercadoria"]
       == round(268400.0 - 1400.0 - 60753.0 - 25000.0, 2))

    # O LUCRO PELA CADEIA: linhas da BASE DE VENDAS por
    # `visao_faturamento.resumo_mensal` de verdade, com as colunas de lá.
    import visao_faturamento as _vf
    from datetime import datetime as _dt
    _base = [{"Data": _dt(2026, 10, 3), "FAT TOTAL": 100.0, "FAT - DEV": 100.0,
              "DEVOLUÇÃO": 0, "L.B": 60.0, "MARGEM C.": 40.0, "VENDAS": 1,
              "SKU": "MS-1", "Custo Unitário": 10.0, "LPV": 20.0, "UNI. CONT.": 2.0},
             {"Data": _dt(2026, 10, 4), "FAT TOTAL": 200.0, "FAT - DEV": 200.0,
              "DEVOLUÇÃO": 0, "L.B": 90.0, "MARGEM C.": 70.0, "VENDAS": 1,
              "SKU": "Porta 2 Relógio + Jóias", "Custo Unitário": None,
              "LPV": 20.0, "UNI. CONT.": 3.5}]
    _rm = _vf.resumo_mensal(_base, 2026, 20.0).get(10)
    _lb, _ll, _ag = lucro(_rm, 20.0)
    ok("lucro bruto é a soma da L.B", _lb == 150.0)
    ok("lucro líquido é margem − LPV × vendas (a conta da Home)",
       _ll == round(110.0 - 20.0 * _rm["vendas"], 2))
    ok("linha sem custo conta como 'aguardando informação'", _ag == 1)
    ok("sem LPV, o líquido não vira número", lucro(_rm, None)[1] is None)
    ok("mês sem venda na base não inventa lucro", lucro(None, 20.0) == (None, None, 0))

    # A TELA DESENHA: verde, vermelho e sem extrato.
    _d = {"entradas": (268400.0, 70.0, {}), "entradas_ant": (250000.0, 0.0, {}),
          "tem_ant": True, "previsto": {"CHEQUES": 55000.0}, "base_mes": _rm,
          "contas": ["inter-1"]}
    _h = html_painel("OUT", 2026, 268400.0, sum(_s.values()), 200000.0, _d, _s, 20.0, False)
    ok("mês verde mostra o que sobrou", "🟢" in _h and "sobraram" in _h)
    _h2 = html_painel("OUT", 2026, 80000.0, sum(_s.values()), None, _d, _s, 20.0, False)
    ok("mês vermelho mostra o que faltou", "🔴" in _h2 and "faltaram" in _h2)
    _h3 = html_painel("JUL", 2026, None, sum(_s.values()), None, _d, _s, 20.0, False)
    ok("mês sem extrato de entrada diz isso, e não pinta de vermelho",
       "sem extrato de entrada" in _h3 and "🔴" not in _h3)
    _h4 = html_painel("OUT", 2026, 0.0, sum(_s.values()), None, _d, _s, 20.0, False)
    ok("extrato sem nenhuma venda entrando não divide por zero nem pinta de vermelho",
       "nenhuma entrada de venda lida" in _h4 and "🔴" not in _h4)
    ok("banco vindo da planilha avisa que a entrada é parcial",
       "parcial" in html_painel("OUT", 2026, 1.0, 2.0, None, _d, _s, 20.0, True))
    ok("linha da planilha sem custo aparece como aguardando informação",
       "aguardando informação" in _h)
    ok("o HTML não tem linha só de espaço (o markdown do Streamlit fecharia o bloco)",
       all(l.strip() for l in _h.split("\n")))

    # O PREVISTO DO CHEQUE É O QUE VENCE, BAIXADO OU NÃO.
    ok("cheque previsto soma todos os que vencem no mês, e não só os em aberto",
       "_ch.do_mes(" in _insp.getsource(previsto_do_mes)
       and "a_vencer" not in _insp.getsource(previsto_do_mes))

    print(f"\nfalhas: {falhas}")
    raise SystemExit(1 if falhas else 0)
