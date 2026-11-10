"""saidas_mes.py — tudo o que saiu no mês, num lugar só (dono, 10/11).

O PEDIDO
--------
"Eu preciso ver isso em um só lugar de forma clara e objetiva" — e, em cada
finalidade, "quando eu clicar, eu preciso ver todos os comprovantes que o
sistema computou", com "pelo menos o consolidado gasto por dia".

UMA RESPOSTA SÓ
---------------
Os itens são os da Visão Geral (`visao_geral.dados_do_ano`): o mesmo total do
"Resumo por finalidade" e do painel do mês. Nada é somado de novo de outra
fonte. Os grupos são os do painel (`visao_financeira.grupo`).

O que cada linha é:
    S  lançamento do Studio (extrato, fatura do cartão ou do ML, cheque)
    P  linha da planilha Controle MS, onde o Studio ainda não tem o banco
    C  cadastro do Studio (custo fixo, folha…) em mês fechado sem débito lido

A compra no cartão aparece com a DATA DA COMPRA (dono, 10/11) e conta no mês
em que a fatura é paga — a régua da meta é o caixa (17/09).
"""
import html as _h

GRUPOS = (("compromissos", "COMPROMISSOS", "#8f9aa8"),
          ("mercadoria", "MERCADORIA", "#7db4ec"),
          ("outros", "CONSUMO E OUTROS", "#f0c060"))
SEM = "SEM CLASSIFICAÇÃO"
ETIQUETA = {"P": " (planilha)", "C": " (previsto)"}


def do_mes(itens, mes):
    """As saídas do mês 'AAAA-MM', na forma de `visao_geral.dados_do_ano`. Pura."""
    return [i for i in (itens or []) if i.get("mes") == mes and float(i.get("valor") or 0)]


def montar(linhas):
    """[(grupo, rótulo, cor, total, [(finalidade, total, [linha])])], do maior
    para o menor dentro de cada grupo, e o total do mês. Pura."""
    import visao_financeira as _vfin
    por = {}
    for l in linhas or []:
        fin = l.get("finalidade") or SEM
        por.setdefault(_vfin.grupo(fin), {}).setdefault(fin, []).append(l)
    fora = []
    for g, rot, cor in GRUPOS:
        fins = [(f, round(sum(float(x["valor"]) for x in ls), 2),
                 sorted(ls, key=lambda x: (str(x.get("data") or ""), -float(x["valor"]))))
                for f, ls in (por.get(g) or {}).items()]
        fins.sort(key=lambda t: -t[1])
        fora.append((g, rot, cor, round(sum(t[1] for t in fins), 2), fins))
    return fora, round(sum(t[3] for t in fora), 2)


def por_dia(linhas):
    """[(data 'AAAA-MM-DD' ou "", n, total)] em ordem de data. Pura."""
    d = {}
    for l in linhas or []:
        k = str(l.get("data") or "")[:10]
        n, t = d.get(k, (0, 0.0))
        d[k] = (n + 1, t + float(l["valor"]))
    return [(k, n, round(t, 2)) for k, (n, t) in sorted(d.items())]


def _r(v):
    return "R$ " + f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(p):
    return f"{p:.1f}%".replace(".", ",")


def _dia(iso):
    t = str(iso or "")
    if len(t) >= 10 and t[4] == "-":
        return f"{t[8:10]}/{t[5:7]}"
    if len(t) == 5 and t[2] == "-":          # fatura em PDF: "MM-DD"
        return f"{t[3:5]}/{t[:2]}"
    return "sem data"


def _quem(l):
    meio = str(l.get("modalidade") or "").title()
    q = _h.escape(str(l.get("quem") or "—"))
    return (f"{meio} · {q}" if meio else q) + ETIQUETA.get(l.get("fonte"), "")


def html(mes_txt, ano, linhas):
    """O quadro inteiro. Uma linha só de HTML (markdown do Streamlit). Pura."""
    import visao_faturamento as _vf
    V, SEC, MUT, BOR, AMB = _vf.VIDRO, _vf.SEC, _vf.MUTED, _vf.BORDA, "#f0c060"
    grupos, tot = montar(linhas)
    if not tot:
        return (f'<div style="{V};padding:16px;margin-top:12px;color:{SEC}">Nenhuma saída lida em '
                f'{mes_txt} {ano}.</div>')
    cols = "grid-template-columns:1fr 160px 80px"
    corpo = ""
    for _g, rot, cor, st, fins in grupos:
        if not fins:
            continue
        corpo += (f'<div style="display:grid;{cols};gap:10px;padding:12px 6px 6px;border-top:2px solid {BOR};'
                  f'align-items:baseline"><span style="font-size:12px;font-weight:800;letter-spacing:.14em;'
                  f'color:{cor}">■ {rot}</span><b style="text-align:right;font-size:16px">{_r(st)}</b>'
                  f'<span style="text-align:right;color:{SEC};font-size:12px">{_pct(st / tot * 100)}</span></div>')
        for fin, v, ls in fins:
            dias = por_dia(ls)
            t_dia = "".join(
                f'<div style="display:grid;grid-template-columns:80px 1fr 160px;gap:10px;padding:2px 0;'
                f'font-size:12.5px"><span>{_dia(d)}</span><span style="color:{SEC}">{n} lançamento(s)</span>'
                f'<span style="text-align:right">{_r(t)}</span></div>' for d, n, t in dias)
            t_lin = "".join(
                f'<div style="display:grid;grid-template-columns:70px 1fr 170px 150px;gap:10px;padding:3px 0;'
                f'font-size:12.5px;color:#c9ced4"><span style="color:{SEC}">{_dia(l.get("data"))}</span>'
                f'<span>{_quem(l)}</span><span style="color:{MUT}">{_h.escape(str(l.get("conta") or ""))[:30]}'
                f'</span><span style="text-align:right">{_r(l["valor"])}</span></div>' for l in ls)
            barra = (f'<div style="height:6px;border-radius:3px;background:{cor};opacity:.8;margin-top:4px;'
                     f'width:{min(v / tot * 220, 100):.1f}%"></div>')
            alerta = f"color:{AMB};font-weight:700;" if fin == SEM else ""
            corpo += (f'<details style="border-top:1px solid {BOR}"><summary style="cursor:pointer;display:grid;'
                      f'{cols};gap:10px;padding:8px 6px;font-size:14px"><span style="{alerta}">'
                      f'{_h.escape(fin.capitalize())} <span style="font-size:11px;color:{MUT}">· {len(ls)} '
                      f'lançamento(s)</span>{barra}</span><span style="text-align:right">{_r(v)}</span>'
                      f'<span style="text-align:right;color:{SEC};font-size:12px">{_pct(v / tot * 100)}</span>'
                      f'</summary><div style="padding:6px 6px 10px 26px">'
                      f'<div style="font-size:11px;font-weight:800;letter-spacing:.1em;color:{SEC};margin:4px 0">'
                      f'POR DIA</div>{t_dia}'
                      f'<div style="font-size:11px;font-weight:800;letter-spacing:.1em;color:{SEC};margin:10px 0 4px">'
                      f'TODOS OS LANÇAMENTOS</div>{t_lin}</div></details>')
    sem = sum(v for _g, _r_, _c, _s, fins in grupos for f, v, _l in fins if f == SEM)
    aviso = (f'<div style="margin-top:10px;padding:10px 12px;border-radius:10px;background:rgba(240,192,96,.08);'
             f'font-size:13px"><b style="color:{AMB}">⚠️ Sem finalidade: {_r(sem)}</b> <span style="color:{SEC}">'
             f'— está no total e ainda precisa ser classificado (Extratos › fila).</span></div>' if sem else "")
    return (f'<div style="background:radial-gradient(1200px 400px at 20% 0%,#454545 0%,{_vf.FUNDO} 60%);'
            f'border-radius:18px;padding:22px;border:1px solid {BOR};margin-top:12px;color:#E8EAED">'
            f'<div style="font-size:12px;font-weight:800;letter-spacing:.14em;color:{SEC}">TUDO O QUE SAIU · '
            f'{mes_txt} {ano}</div><div style="font-size:34px;font-weight:800;margin-top:4px">{_r(tot)}</div>'
            f'<div style="font-size:13px;color:{SEC}">em {len(linhas)} lançamento(s) · transferência entre contas, '
            f'aplicação e empréstimo recebido ficam fora</div>'
            f'<div style="{V};padding:10px 16px 16px;margin-top:16px"><div style="display:grid;{cols};gap:10px;'
            f'padding:4px 6px;font-size:11px;color:{MUT};letter-spacing:.1em"><span>GRUPO › FINALIDADE (clique '
            f'para ver por dia e cada lançamento)</span><span style="text-align:right">VALOR</span>'
            f'<span style="text-align:right">% DO MÊS</span></div>{corpo}'
            f'<div style="display:grid;{cols};gap:10px;padding:12px 6px 0;border-top:2px solid #E8EAED;'
            f'font-size:16px;font-weight:800"><span>TOTAL DO MÊS</span><span style="text-align:right">{_r(tot)}'
            f'</span><span style="text-align:right">100%</span></div></div>{aviso}'
            f'<div style="font-size:12px;color:{SEC};margin-top:10px">Mesma conta do Resumo por finalidade e do '
            f'painel acima. (planilha) = banco ainda sem extrato no Studio; (previsto) = cadastro, sem débito lido. '
            f'A compra no cartão aparece na data da compra e conta no mês em que a fatura é paga.</div></div>')


def mostrar(itens, ano, mes, mes_txt):
    """Desenha o quadro do mês. `itens` = os de `visao_geral.dados_do_ano`."""
    import streamlit as st
    st.markdown(html(mes_txt, ano, do_mes(itens, f"{int(ano):04d}-{int(mes):02d}")),
                unsafe_allow_html=True)


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import inspect as _insp
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # A ENTRADA VEM DO SISTEMA: lançamentos na forma de `lancamentos.carregar`
    # passados por `resumo_mensal.itens_pagos` e `visao_geral.itens_do_studio`
    # de verdade; uma linha da planilha por `visao_geral.juntar`.
    import resumo_mensal as _rm
    import visao_geral as _vg
    _l = [{"data": "2026-10-03", "valor": -22400.0, "descricao": "SISPAG FORNECEDORES",
           "favorecido": "APEXIMP COMERCIO", "finalidade": "MERCADORIA", "conta": "itau-0099275-0",
           "tipo": ""},
          {"data": "2026-10-03", "valor": -8850.0, "descricao": "PIX ENVIADO",
           "favorecido": "Porta 2 Relógio + Jóias <b>", "finalidade": "MERCADORIA",
           "conta": "inter-167513915", "tipo": ""},
          {"data": "2026-10-06", "valor": -8900.0, "descricao": "BOLETO PAGO",
           "favorecido": "LOOK CHINA", "finalidade": "MERCADORIA", "conta": "itau-0099275-0", "tipo": ""},
          {"data": "2026-10-30", "valor": -1350.0, "descricao": "PIX ENVIADO",
           "favorecido": "VLAMOR GARCIA IMOBILIARIA", "finalidade": "CUSTO FIXO",
           "conta": "itau-0099275-0", "tipo": ""},
          {"data": "2026-10-12", "valor": -310.0, "descricao": "CLAUDE.AI USAGE",
           "favorecido": "CLAUDE.AI USAGE", "finalidade": "", "conta": "cartão · f.pdf",
           "tipo": "fatura 2026-10"},
          {"data": "2026-10-15", "valor": 5000.0, "descricao": "PIX RECEBIDO", "favorecido": "SHEIN",
           "finalidade": "SHEIN", "conta": "itau-0099275-0", "tipo": ""},
          {"data": "2026-10-20", "valor": -90000.0, "descricao": "TRANSF", "favorecido": "MS",
           "finalidade": "TRANSFERENCIA ENTRE CONTAS", "conta": "itau-0099275-0", "tipo": ""}]
    _it = _vg.itens_do_studio({"2026-10": _rm.itens_pagos(_l, set(), com_origem=True)})
    _it = _vg.juntar(2026, _it, [{"Data": "2026-10-09", "Operação": "PIX ENVIADO",
                                  "DESTINATÁRIO": "ER EMBALAGENS", "FINALIDADE": "EMBALAGEM",
                                  "Valor": -2100.0, "Banco": "INTER LG"}], [], [], [])
    _m = do_mes(_it, "2026-10")
    _g, _tot = montar(_m)
    _vals, _ = _vg.resumo(_it, 2026)
    ok("o total do mês é o mesmo do Resumo por finalidade (uma resposta só)",
       _tot == round(sum(_vals[10].values()), 2))
    ok("entrada e transferência entre contas ficam fora",
       all(i["finalidade"] not in ("SHEIN", "TRANSFERENCIA ENTRE CONTAS") for i in _m))
    _merc = dict((f, (v, ls)) for _a, _b, _c, _d, fins in _g for f, v, ls in fins)["MERCADORIA"]
    ok("mercadoria: TODOS os lançamentos, e a soma das linhas é o total da finalidade",
       len(_merc[1]) == 3 and round(sum(x["valor"] for x in _merc[1]), 2) == _merc[0] == 40150.0)
    ok("consolidado por dia: 03/10 com 2 lançamentos, 06/10 com 1",
       por_dia(_merc[1]) == [("2026-10-03", 2, 31250.0), ("2026-10-06", 1, 8900.0)])
    ok("os grupos são os do painel: custo fixo é compromisso, embalagem é outros",
       [g[0] for g in _g] == ["compromissos", "mercadoria", "outros"]
       and any(f == "CUSTO FIXO" for f, _v, _l2 in _g[0][4])
       and any(f == "EMBALAGEM" for f, _v, _l2 in _g[2][4]))
    _h1 = html("OUT", 2026, _m)
    ok("cada lançamento aparece com data, quem e valor, e o da planilha marcado",
       "03/10" in _h1 and "APEXIMP COMERCIO" in _h1 and "R$ 22.400,00" in _h1
       and "ER EMBALAGENS (planilha)" in _h1)
    ok("a tela lista TODOS os lançamentos da finalidade, e não só os primeiros",
       all(t in _h1 for t in ("APEXIMP COMERCIO", "Porta 2 Relógio", "LOOK CHINA")))
    ok("o pior nome real passa escapado", "Porta 2 Relógio + Jóias &lt;b&gt;" in _h1 and "<b>\"" not in _h1)
    ok("sem finalidade vira linha e aviso", "Sem finalidade" in _h1 and "Sem classificação" in _h1)
    import re as _re
    ok("percentual com vírgula (o da barra é CSS e fica com ponto)",
       _pct(12.34) == "12,3%" and not _re.search(r">\d+\.\d%<", _h1))
    ok("o HTML não tem linha só de espaço e nada navega (Regra 12)",
       all(x.strip() for x in _h1.split("\n")) and "<a " not in _h1 and "href" not in _h1)
    ok("mês sem saída diz isso", "Nenhuma saída lida" in html("NOV", 2026, []))
    ok("data da fatura em PDF ('MM-DD') vira dd/mm", _dia("10-12") == "12/10")
    import visao_financeira as _vfin_t
    ok("todo COMPROMISSOS do painel cai no grupo compromissos aqui",
       all(montar([{"finalidade": f, "valor": 1.0}])[0][0][4] for f in _vfin_t.COMPROMISSOS))
    ok("os grupos vêm de visao_financeira.grupo (uma regra só)",
       "_vfin.grupo(" in _insp.getsource(montar))
    print(f"\nfalhas: {falhas}")
    raise SystemExit(1 if falhas else 0)
