"""historico.py — a sub-aba Histórico da Home: mês a mês, a meta contra o que foi.

Dono, 13/10: "preciso enxergar o histórico dos meses anteriores, o que era meta
vs o que realmente foi gasto e faturado (...) não precisa ser tão elaborado,
mas com as informações precisas". Layout aprovado no mesmo dia.

UMA CONTA SÓ. `meses` é a mesma conta da tabela "Equilíbrio real — meses
fechados" da Meta de gastos (`meta_gastos_tela._equilibrio_real`, que passa a
usá-la): `equilibrio_caixa.equilibrio_real` sobre a linha de cada mês. Duas
telas montando a mesma pergunta por conta própria passariam a discordar — a
Forma 5 do CLAUDE.md.

Só meses FECHADOS: o mês corrente se compara depois de fechar (dono, 09/10).
"""
import streamlit as st

import rotulos as _rot

MESES = ("Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro")


def situacao(r, tem_meta):
    """O veredito do mês, em texto. A mesma frase nas duas telas."""
    if r["motivo"]:
        return r["motivo"]
    txt = ("⚠️ gasto real menos da metade da meta — extratos completos?"
           if r["suspeito"] else
           ("✅ cobriu" if (r["resultado"] or 0) >= 0 else "❌ faltou"))
    if r["origem_gasto"] == "informado":
        txt += " · gasto informado à mão"
    if not tem_meta:
        txt += " · sem meta no mês"
    return txt


def meses(linhas, mapa, ano, hoje):
    """Os meses fechados do ano com meta ou gasto, em ordem. Pura.

    `linhas` = `meta_gastos.ano_inteiro(ano)` (uma por mês, janeiro primeiro);
    `mapa` = `base_vendas.somas_por_mes()`. Cada item traz o que
    `equilibrio_caixa.equilibrio_real` devolve, mais o mês, o faturamento
    bruto e a frase da situação.
    """
    import equilibrio_caixa as _ec
    fechados = set(_ec.meses_fechados(ano, hoje))
    fora = []
    for i, l in enumerate(linhas or [], start=1):
        if i not in fechados:
            continue
        if not (l.get("meta") or l.get("origem") != "sem dado"):
            continue
        r = _ec.equilibrio_real(l.get("meta"), l.get("realizado"),
                                l.get("origem"), mapa, ano, i)
        somas = (mapa or {}).get((int(ano), i)) or {}
        fora.append({**r, "mes": i, "rotulo": f"{MESES[i - 1]}/{ano}",
                     "tem_meta": bool(l.get("meta")),
                     "fat_bruto": (float(somas.get("faturamento") or 0.0)
                                   if somas.get("linhas") else None),
                     "situacao": situacao(r, bool(l.get("meta")))})
    return fora


def _barra(rotulo, valor, alvo, cor, nota):
    """Barra de valor contra alvo, com a marca no alvo."""
    if not valor or not alvo:
        return ""
    pct = valor / alvo * 100
    larg = min(pct, 100.0)
    marca = min(alvo / max(valor, alvo) * 100, 100.0)
    return (
        '<div style="display:flex;flex-direction:column;gap:6px;">'
        '<div style="display:flex;justify-content:space-between;font-size:12px;'
        'color:#9AA3AE;"><span>' + rotulo + '</span><b style="color:#E8EAED;">'
        f'{_rot.brl(valor, 0)} de {_rot.brl(alvo, 0)} · {pct:.0f}%</b></div>'
        '<div style="height:10px;border-radius:999px;background:#2c2c2c;'
        'position:relative;">'
        f'<div style="height:100%;width:{larg:.1f}%;border-radius:999px;'
        f'background:{cor};"></div>'
        f'<div style="position:absolute;top:-4px;bottom:-4px;left:{marca:.1f}%;'
        'width:3px;margin-left:-1.5px;background:#E8EAED;border-radius:2px;">'
        '</div></div>'
        f'<div style="font-size:11px;color:#9AA3AE;">{nota}</div></div>')


def html_resumo(m, lpv=None):
    """O cartão de um mês: resultado, as duas barras e os números de apoio."""
    ok = (m["resultado"] or 0) >= 0
    cor = "#4CC38A" if ok else "#E5534B"
    if m["resultado"] is None:
        topo = (f'<div style="font-size:15px;font-weight:700;color:#E0A13A;">'
                f'{m["situacao"]}</div>')
    else:
        sinal = "+" if ok else "−"
        topo = (f'<div style="font-size:34px;font-weight:800;color:{cor};">'
                f'{sinal}{_rot.brl(abs(m["resultado"]), 0)}</div>'
                '<div style="font-size:12px;color:#9AA3AE;">faturado líquido '
                + ("acima" if ok else "abaixo") + ' do equilíbrio real</div>')
    gasto = m.get("gasto_real") or 0.0
    meta = m.get("meta") or 0.0
    dif = gasto - meta if meta else None
    nota_g = ("" if dif is None else
              f"gastou {_rot.brl(abs(dif), 0)} a "
              + ("menos" if dif <= 0 else "mais") + " que a meta")

    def tile(rot, val):
        return ('<div style="background:#2c2c2c;border-radius:10px;padding:9px 12px;">'
                f'<div style="font-size:11px;color:#9AA3AE;">{rot}</div>'
                f'<div style="font-size:16px;font-weight:700;">{val}</div></div>')
    mb = m.get("mb_mes")
    return (
        '<div style="background:#333333;border:1px solid #4a4a4a;border-radius:14px;'
        'padding:18px 22px;display:flex;flex-direction:column;gap:14px;color:#E8EAED;">'
        f'<div style="font-size:12px;font-weight:600;letter-spacing:.08em;'
        f'text-transform:uppercase;color:#9AA3AE;">Resumo · {m["rotulo"]}</div>'
        + topo
        + '<div style="display:grid;grid-template-columns:repeat(auto-fit,'
          'minmax(260px,1fr));gap:16px;">'
        + _barra("Gasto real × meta de gastos", gasto, meta, "#E0A13A", nota_g)
        + _barra("Faturado × equilíbrio real", m.get("faturado") or 0.0,
                 m.get("real") or 0.0, cor,
                 "a marca é o equilíbrio real")
        + '</div>'
        + '<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;">'
        + tile("Faturamento bruto", _rot.brl(m["fat_bruto"], 0)
               if m.get("fat_bruto") else "—")
        + tile("Lucro bruto do mês", f"{mb:.1f}%".replace(".", ",") if mb else "—")
        + tile("LPV do mês", _rot.brl(lpv) if lpv else "—")
        + '</div></div>')


def tabela(lista):
    """As linhas da tabela, do mês mais recente ao mais antigo. Pura."""
    return [{
        "mês": m["rotulo"],
        "meta de gastos": m["meta"] or None,
        "gasto real": m["gasto_real"] or None,
        "gasto × meta": m["gasto_vs_meta"],
        "faturado (líquido)": m["faturado"],
        "lucro bruto": (f"{m['mb_mes']:.1f}%".replace(".", ",")
                        if m.get("mb_mes") else "—"),
        "equilíbrio da meta": m["planejado"],
        "equilíbrio real": m["real"],
        "resultado": m["resultado"],
        "situação": m["situacao"],
    } for m in reversed(lista)]


def pagina(usuario_logado=None):
    from datetime import datetime
    import base_vendas as _bv
    import lpv_mensal as _lm
    import meta_gastos as _mg
    import placar_core as _pc

    hoje = datetime.now(_pc.FUSO).date()
    anos = [hoje.year, hoje.year - 1]
    ano = st.selectbox("Ano", anos, key="hist_ano")
    mapa, erro = _bv.somas_por_mes()
    if erro:
        st.warning(f"Não consegui ler a BASE DE VENDAS: {erro}")
    lista = meses(_mg.ano_inteiro(ano), mapa or {}, ano, hoje)
    if not lista:
        st.info(f"Nenhum mês fechado de {ano} com meta ou gasto lançado.")
        return
    linhas = tabela(lista)
    _din = ["meta de gastos", "gasto real", "gasto × meta", "faturado (líquido)",
            "equilíbrio da meta", "equilíbrio real", "resultado"]
    st.dataframe(linhas, use_container_width=True, hide_index=True,
                 column_config=_rot.config(list(linhas[0]), st,
                                           tipos={c: "brl" for c in _din}))
    por_rotulo = {m["rotulo"]: m for m in lista}
    escolha = st.selectbox("Mês", [l["mês"] for l in linhas], key="hist_mes")
    m = por_rotulo[escolha]
    try:
        _lpvs, _ = _lm.lpv_do_ano(ano)
        lpv = (_lpvs.get(m["mes"]) or {}).get("lpv")
    except Exception:
        lpv = None
    st.markdown(html_resumo(m, lpv), unsafe_allow_html=True)


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from datetime import date, datetime as _dt
    import base_vendas as _bv_t
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # A ENTRADA VEM DO SISTEMA: as vendas saem de `base_vendas.somar` com os
    # nomes de coluna da BASE DE VENDAS, e as linhas da meta têm a forma de
    # `meta_gastos.ano_inteiro` (meta, realizado, origem).
    # Os nomes da planilha do dono (os mesmos do auto-teste de base_vendas).
    COLS = ["Data", "MÊS/ANO", "FAT TOTAL", "FAT - DEV", "L.B", "VENDAS"]

    def _venda(m, fat, liq, lb):
        return {"Data": _dt(2026, m, 10), "MÊS/ANO": f"m{m}", "FAT TOTAL": fat,
                "FAT - DEV": liq, "L.B": lb, "VENDAS": 100}
    _base = [_venda(m, 240000, 228000, 168000) for m in (5, 6, 7, 8, 9)]
    _mapa = {(2026, m): _bv_t.somar(_base, COLS, 2026, m) for m in range(1, 11)}
    _linhas = [{"meta": 0.0, "realizado": 0.0, "origem": "sem dado"}
               for _ in range(12)]
    _linhas[8] = {"meta": 150000.0, "realizado": 142380.0, "origem": "extrato"}
    _linhas[7] = {"meta": 0.0, "realizado": 158930.0, "origem": "extrato"}
    _linhas[9] = {"meta": 150000.0, "realizado": 50000.0, "origem": "extrato"}
    _l = meses(_linhas, _mapa, 2026, date(2026, 10, 13))
    ok("só os meses fechados com meta ou gasto, em ordem",
       [m["rotulo"] for m in _l] == ["Agosto/2026", "Setembro/2026"])
    _set = _l[1]
    _mb_set = _set["mb_mes"]
    ok("o equilíbrio real é o gasto ÷ o lucro bruto do próprio mês",
       _mb_set and abs(_set["real"] - round(142380.0 / (_mb_set / 100), 2)) < 0.01)
    ok("e o resultado é o faturado líquido menos ele",
       _set["resultado"] == round(_set["faturado"] - _set["real"], 2))
    ok("mês sem meta diz isso", "sem meta" in _l[0]["situacao"]
       and _l[0]["planejado"] is None)
    ok("o faturamento bruto vem da BASE DE VENDAS", _set["fat_bruto"] == 240000.0)
    _t = tabela(_l)
    ok("a tabela abre no mês mais recente",
       _t[0]["mês"] == "Setembro/2026" and _t[1]["mês"] == "Agosto/2026")
    _h = html_resumo(_set, 21.96)
    ok("o resumo do mês traz resultado, as duas barras e o LPV",
       "Resumo · Setembro/2026" in _h and "Gasto real × meta de gastos" in _h
       and "Faturado × equilíbrio real" in _h and "R$ 21,96" in _h)
    _sem_base = meses(_linhas, {}, 2026, date(2026, 10, 13))
    ok("sem a BASE DE VENDAS o mês aparece com o motivo, sem resultado",
       _sem_base and _sem_base[1]["resultado"] is None
       and "BASE DE VENDAS" in html_resumo(_sem_base[1]))
    print(f"\nfalhas: {falhas}")
    sys.exit(1 if falhas else 0)
