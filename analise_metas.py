"""
analise_metas.py — Página de Análise de Metas (exclusiva MartinSousa)
Permite visualizar desempenho histórico e configurar metas por mês.

NOTA: importa placar_core (sem UI) em vez de placar (com UI) para evitar
circular import e conflito de chaves de widgets do Streamlit.
"""
import streamlit as st
import pandas as pd
import math
from datetime import datetime

import metas_config as mc
import placar_core as _pc
try:
    import relogio_ponto as _rp
    _PONTO_DISPONIVEL = True
except ImportError:
    _rp = None
    _PONTO_DISPONIVEL = False

# MESES_PT importado do placar_core
MESES_PT = _pc.MESES_PT

# ── Helpers ────────────────────────────────────────────────────────────────────

def _ultimos_meses(ano, mes, n):
    """Retorna lista de (ano,mes) dos últimos n meses, do mais antigo ao atual."""
    resultado = []
    a, m = ano, mes
    for _ in range(n):
        resultado.append((a, m))
        m -= 1
        if m == 0:
            m = 12; a -= 1
    return list(reversed(resultado))


def _label_mes(ano, mes):
    return f"{MESES_PT[mes][:3]}/{str(ano)[2:]}"


def _cor_pct(pct):
    if pct >= 100: return "#1BAF7A"
    if pct >= 75:  return "#8BC34A"
    if pct >= 50:  return "#EDA100"
    return "#E34948"


def _barra_h(pct, cor=None):
    c = cor or _cor_pct(pct)
    p = min(pct, 100)
    return (f'<div style="background:var(--ms-metric-bd);border-radius:3px;height:6px;overflow:hidden;margin-top:2px;">'
            f'<div style="background:{c};width:{p:.1f}%;height:100%;border-radius:3px;"></div></div>')


def _barra_std(label, valor_display, pct_barra, cor="#EDA100", sub=None):
    """Barra horizontal estilo Pendentes (laranja). pct_barra é 0-100."""
    pct = min(max(pct_barra, 0), 100)
    label_c = label[:50] + "…" if len(label) > 50 else label
    sub_html = (f'<div style="font-size:9px;color:var(--ms-texto-sec);margin-top:1px;">{sub}</div>'
                if sub else "")
    return (
        f'<div style="margin-bottom:6px;">'
        f'<div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:2px;">'
        f'<span style="color:var(--ms-texto);">{label_c}</span>'
        f'<span style="font-weight:700;color:{cor};">{valor_display}</span></div>'
        f'<div style="background:var(--ms-metric-bd);border-radius:3px;height:5px;">'
        f'<div style="background:{cor};width:{pct:.0f}%;height:100%;border-radius:3px;"></div>'
        f'</div>{sub_html}</div>'
    )


def _celula(valor, cor="var(--ms-texto)", bold=False):
    b = "font-weight:700;" if bold else ""
    return f'<td style="padding:5px 10px;color:{cor};{b}text-align:right;">{valor}</td>'


def _thead(colunas):
    ths = "".join(
        f'<th style="padding:5px 10px;font-size:9px;color:var(--ms-texto-sec);'
        f'text-transform:uppercase;letter-spacing:.5px;text-align:{"left" if i==0 else "right"};'
        f'white-space:nowrap;">{c}</th>'
        for i, c in enumerate(colunas)
    )
    return f'<thead><tr style="border-bottom:1px solid var(--ms-divisor);">{ths}</tr></thead>'


def _tabela(cabecalhos, linhas_html):
    return (
        f'<div style="overflow-x:auto;">'
        f'<table style="width:100%;border-collapse:collapse;font-size:11px;">'
        f'{_thead(cabecalhos)}<tbody>{"".join(linhas_html)}</tbody></table></div>'
    )


# ── Construção dos dados de análise ───────────────────────────────────────────

def _analisar_meses(listas, cards, membros_map, id_p, id_t, id_i, meses_lista, processar_fn):
    """
    Para cada mês retorna um dict com dados processados + config de meta.
    processar_fn = placar._processar (passado como parâmetro para evitar import circular)
    """
    resultado = []
    for (ano, mes) in meses_lista:
        d = processar_fn(listas, cards, membros_map, id_p, id_t, id_i, filtro_mes=(ano, mes))
        cfg = mc.carregar_config(ano, mes)
        meta_eq  = cfg["meta_equipe"]
        maxx_pct = cfg["meta_maxx_pct"]
        meta_maxx = meta_eq * maxx_pct / 100
        saldo = d["pts_equipe"] - d["pen_total"]
        pct_mensal = (saldo / meta_eq * 100) if meta_eq > 0 else 0
        pct_maxx   = (saldo / meta_maxx * 100) if meta_maxx > 0 else 0
        qtd_pen    = len(d["pen_cards"])
        total_concl = d.get("total_concl", 0)
        corr_concl  = d.get("correcao_concl", 0)
        pct_retrab  = (corr_concl / total_concl * 100) if total_concl > 0 else None
        # Cartões com membro: em andamento + concluídos
        _and_sem_mb  = sum(1 for c in d["andamento_lista"] if not c["membros"])
        _concl_sem_mb = len(d.get("concluido_sem_membro", []))
        _total_ativos = d["em_andamento"] + total_concl
        _ativos_sem_mb = _and_sem_mb + _concl_sem_mb
        pct_com_membro_m = max(0.0, min(100.0, 100 - (_ativos_sem_mb / max(_total_ativos, 1) * 100)))
        resultado.append({
            "ano": ano, "mes": mes,
            "label": _label_mes(ano, mes),
            "cfg": cfg,
            "meta_eq": meta_eq,
            "meta_maxx": meta_maxx,
            "pts_equipe": d["pts_equipe"],
            "pen_total": d["pen_total"],
            "pen_qtd": qtd_pen,
            "saldo": saldo,
            "pct_mensal": pct_mensal,
            "pct_maxx": pct_maxx,
            "pts_pendentes": d["pts_pendentes"],
            "abertos": d["abertos"],
            "urgentes": d["urgentes"],
            "atrasados": d["atrasados"],
            "em_andamento": d["em_andamento"],
            "andamento_lista": d["andamento_lista"],
            "pend_lista": d["pend_lista"],
            "tempo_lista": d["tempo_lista"],
            "tempo_membro_lista": d.get("tempo_membro_lista", {}),
            "pts_lista": dict(d["pts_lista"]),
            "qtd_lista": dict(d["qtd_lista"]),
            "pts_membro": dict(d["pts_membro"]),
            "pen_membro": dict(d["pen_membro"]),
            "qtd_membro": dict(d.get("qtd_membro", {})),
            "pen_cards": d["pen_cards"],
            "pct_retrab": pct_retrab,   # None se sem dados
            "total_concl": total_concl,
            "pct_com_membro": pct_com_membro_m,
            "filtro_mes": (ano, mes),   # usado por relogio_ponto para calcular ociosidade
        })
    return resultado


def _extend_dados_ano(dados):
    """Preenche com entradas zeradas para todos os meses de Jan até o mês atual do ano corrente.
    Garante que o gráfico anual sempre mostre Jan–mês_atual mesmo quando o período selecionado
    é apenas 'Dentro do mês' ou outro intervalo curto."""
    agora = datetime.now()
    ano_atual, mes_atual = agora.year, agora.month
    existentes = {(r["ano"], r["mes"]) for r in dados}
    resultado = list(dados)
    for m in range(1, mes_atual + 1):
        if (ano_atual, m) not in existentes:
            cfg = mc.carregar_config(ano_atual, m)
            meta_eq  = cfg["meta_equipe"]
            maxx_pct = cfg.get("meta_maxx_pct", 120)
            resultado.append({
                "ano": ano_atual, "mes": m,
                "label": _label_mes(ano_atual, m),
                "cfg": cfg,
                "meta_eq": meta_eq,
                "meta_maxx": meta_eq * maxx_pct / 100,
                "pts_equipe": 0.0, "pen_total": 0.0, "pen_qtd": 0,
                "saldo": 0.0, "pct_mensal": 0.0, "pct_maxx": 0.0,
                "pts_pendentes": 0.0, "abertos": 0, "urgentes": 0,
                "atrasados": 0, "em_andamento": 0,
                "andamento_lista": [], "pend_lista": {},
                "tempo_lista": {}, "tempo_membro_lista": {},
                "pts_lista": {}, "qtd_lista": {},
                "pts_membro": {}, "pen_membro": {}, "qtd_membro": {},
                "pen_cards": [], "pct_retrab": None, "total_concl": 0,
                "pct_com_membro": 0.0,
            })
    resultado.sort(key=lambda r: (r["ano"], r["mes"]))
    return resultado


# ── Seção: painel Meta Coletiva | Meta MAXX lado a lado ──────────────────────

def _barra_painel(nome, pct, desc, cor):
    """Barra de meta no estilo do Painel de Metas."""
    pct_c = min(max(pct, 0), 100)
    return (
        f'<div style="margin-bottom:8px;">'
        f'<div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px;">'
        f'<span style="color:var(--ms-texto);">{nome}</span>'
        f'<span style="color:{cor};font-weight:700;">{pct_c:.0f}%</span></div>'
        f'<div style="background:var(--ms-metric-bd);border-radius:3px;height:5px;overflow:hidden;">'
        f'<div style="background:{cor};width:{pct_c:.1f}%;height:100%;border-radius:3px;"></div></div>'
        f'<div style="font-size:8px;color:var(--ms-texto-sec);margin-top:2px;">{desc}</div></div>'
    )

def _barra_painel_dash(nome, desc):
    """Barra de meta aguardando dados (exibe —)."""
    return (
        f'<div style="margin-bottom:8px;">'
        f'<div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px;">'
        f'<span style="color:var(--ms-texto);">{nome}</span>'
        f'<span style="color:var(--ms-texto-sec);font-weight:700;">—</span></div>'
        f'<div style="background:var(--ms-metric-bd);border-radius:3px;height:5px;overflow:hidden;">'
        f'<div style="background:var(--ms-metric-bd);width:100%;height:100%;border-radius:3px;opacity:.2;"></div></div>'
        f'<div style="font-size:8px;color:var(--ms-texto-sec);margin-top:2px;">{desc}</div></div>'
    )


def _secao_metas_card(dados):
    """Painel Meta Coletiva | Meta MAXX lado a lado, estilo Painel de Metas."""
    if not dados:
        return
    r = dados[-1]  # mês mais recente do período
    cfg = r["cfg"]
    pct_eq   = r["pct_mensal"]
    pct_maxx = r["pct_maxx"]
    saldo    = r["saldo"]
    meta_eq  = r["meta_eq"]
    meta_maxx = r["meta_maxx"]
    pen_total = r["pen_total"]
    atrasados = r["atrasados"]
    pen_qtd   = r["pen_qtd"]
    maxx_pct  = cfg.get("meta_maxx_pct", 110)

    max_pen_n = int(cfg.get("max_pen_normal", 4))
    max_pen_x = int(cfg.get("max_pen_maxx", 1))
    max_retrab_n = int(cfg.get("max_retrab_normal", 10))
    max_retrab_x = int(cfg.get("max_retrab_maxx", 5))

    pct_prioritarios = 100 if atrasados == 0 else max(0, 100 - atrasados * 20)
    pct_com_membro   = r.get("pct_com_membro", 100.0)

    # Penalidades: acumulam de 0% a 100% (vermelho)
    pct_pen_n = min(pen_qtd / (max_pen_n + 1) * 100, 100) if max_pen_n >= 0 else 0
    pct_pen_x = min(pen_qtd / (max_pen_x + 1) * 100, 100) if max_pen_x >= 0 else 0

    # Retrabalho
    pct_retrab = r.get("pct_retrab")
    if pct_retrab is not None:
        pct_retrab_n = max(0.0, (1.0 - pct_retrab / max_retrab_n) * 100) if max_retrab_n > 0 else 100.0
        pct_retrab_x = max(0.0, (1.0 - pct_retrab / max_retrab_x) * 100) if max_retrab_x > 0 else 100.0
        desc_retrab = f"{pct_retrab:.1f}% atual · máx {max_retrab_n}%"
        desc_retrab_x = f"{pct_retrab:.1f}% atual · máx {max_retrab_x}%"
    else:
        pct_retrab_n = pct_retrab_x = 0
        desc_retrab = desc_retrab_x = "Sem dados de conclusão no período"

    st.markdown(f'<div style="font-size:9px;color:var(--ms-texto-sec);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;">Referência: {r["label"]}</div>', unsafe_allow_html=True)

    col_n, col_x = st.columns(2)
    with col_n:
        b = f'<div style="font-size:10px;font-weight:600;color:#1BAF7A;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px;">📋 Meta Coletiva</div>'
        b += _barra_painel("Pontuação do mês", pct_eq,
                            f"{saldo:,.0f} / {meta_eq:,.0f} pts (inclui -{pen_total:.0f} penalidades)", "#1BAF7A")
        _cor_pri_a = "#1BAF7A" if pct_prioritarios >= 100 else "#E34948"
        b += _barra_painel("Sem atraso em prioritários P8-P10", pct_prioritarios,
                            "Nenhum cartão prioritário atrasado" if atrasados == 0 else f"{atrasados} atrasado(s)", _cor_pri_a)
        _cor_rtn_a = "#1BAF7A" if pct_retrab_n >= 100 else "#E34948"
        b += _barra_painel(f"Retrabalho abaixo de {max_retrab_n}%", pct_retrab_n, desc_retrab, _cor_rtn_a)
        b += _barra_painel(f"Menos de {max_pen_n+1} penalidades", pct_pen_n,
                            f"{pen_qtd} ocorrência(s) / máx {max_pen_n}", "#E34948")
        _cor_cmb_a = "#1BAF7A" if pct_com_membro >= 100 else "#E34948"
        b += _barra_painel("Cartões com membro atribuído", pct_com_membro,
                            "Em andamento e concluídos no período", _cor_cmb_a)
        st.markdown(f'<div style="background:var(--ms-metric-bg);border:1px solid #1BAF7A22;border-radius:8px;padding:12px 14px;">{b}</div>', unsafe_allow_html=True)

    with col_x:
        b = f'<div style="font-size:10px;font-weight:600;color:#FFD700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px;">⭐ Meta Maxx Coletiva</div>'
        b += _barra_painel(f"Pontuação +{maxx_pct-100}% acima da meta", pct_maxx,
                            f"{saldo:,.0f} / {meta_maxx:,.0f} pts (c/ penalidades -{pen_total:.0f})", "#FFD700")
        _cor_prix_a = "#FFD700" if pct_prioritarios >= 100 else "#E34948"
        b += _barra_painel("Zero prioritários em atraso", pct_prioritarios,
                            "Nenhum cartão prioritário atrasado" if atrasados == 0 else f"{atrasados} atrasado(s)", _cor_prix_a)
        _cor_rtx_a = "#FFD700" if pct_retrab_x >= 100 else "#E34948"
        b += _barra_painel(f"Retrabalho abaixo de {max_retrab_x}%", pct_retrab_x, desc_retrab_x, _cor_rtx_a)
        b += _barra_painel(f"Menos de {max_pen_x+1} penalidades", pct_pen_x,
                            f"{pen_qtd} ocorrência(s) / máx {max_pen_x}", "#E34948")
        _cor_cmbx_a = "#FFD700" if pct_com_membro >= 100 else "#E34948"
        b += _barra_painel("Cartões com membro atribuído", pct_com_membro,
                            "Em andamento e concluídos no período", _cor_cmbx_a)
        st.markdown(f'<div style="background:var(--ms-metric-bg);border:1px solid #FFD70022;border-radius:8px;padding:12px 14px;">{b}</div>', unsafe_allow_html=True)


# ── Seção: tabela coletiva ─────────────────────────────────────────────────────

def _secao_coletiva(dados):
    """Tabela com meses em colunas, métricas coletivas em linhas."""
    if not dados: return

    labels = [r["label"] for r in dados]
    cab = ["Métrica"] + labels + (["Total", "Média/mês"] if len(dados) > 1 else [])

    def _ln(nome_label, vals_fn, fmt=lambda v: f"{v:,.0f}", cor_fn=None, total=None):
        tds = ""
        td_nome = f'<td style="padding:5px 10px;font-size:10px;color:var(--ms-texto);white-space:nowrap;">{nome_label}</td>'
        valores = [vals_fn(r) for r in dados]
        for i, v in enumerate(valores):
            cor = cor_fn(dados[i]) if cor_fn else "var(--ms-texto)"
            tds += _celula(fmt(v), cor)
        if len(dados) > 1:
            if total == "sum":
                t = sum(valores)
                tds += _celula(fmt(t), bold=True) + _celula(fmt(t / len(dados)))
            elif total == "avg":
                t = sum(valores) / len(valores)
                tds += _celula(fmt(t)) + _celula(fmt(t))
            else:
                tds += _celula("—") + _celula("—")
        return f'<tr style="border-bottom:1px solid var(--ms-divisor)30;">{td_nome}{tds}</tr>'

    linhas = []

    linhas.append(
        f'<tr style="background:var(--ms-metric-bg);border-bottom:1px solid var(--ms-divisor);">'
        f'<td colspan="{len(cab)}" style="padding:6px 10px;font-size:9px;font-weight:700;'
        f'color:#1BAF7A;text-transform:uppercase;letter-spacing:.5px;">🏆 Pontuação Coletiva</td></tr>'
    )
    linhas.append(_ln("Meta Mensal (pts)", lambda r: r["meta_eq"], total="avg"))
    linhas.append(_ln("Meta MAXX (pts)",   lambda r: r["meta_maxx"], total="avg"))
    linhas.append(_ln("Pontos Brutos",  lambda r: r["pts_equipe"], total="sum"))
    linhas.append(_ln("Penalidades (pts)", lambda r: -r["pen_total"],
                      cor_fn=lambda r: "#E34948" if r["pen_total"] > 0 else "#1BAF7A", total="sum"))
    linhas.append(_ln("Saldo Final",    lambda r: r["saldo"],
                      cor_fn=lambda r: _cor_pct(r["pct_mensal"]), total="sum", fmt=lambda v: f"{v:,.0f}"))
    linhas.append(_ln("% Meta Mensal",  lambda r: r["pct_mensal"],
                      fmt=lambda v: f"{v:.0f}%",
                      cor_fn=lambda r: _cor_pct(r["pct_mensal"]), total="avg"))
    linhas.append(_ln("% Meta MAXX",    lambda r: r["pct_maxx"],
                      fmt=lambda v: f"{v:.0f}%",
                      cor_fn=lambda r: _cor_pct(r["pct_maxx"]), total="avg"))

    linhas.append(
        f'<tr style="background:var(--ms-metric-bg);border-bottom:1px solid var(--ms-divisor);">'
        f'<td colspan="{len(cab)}" style="padding:6px 10px;font-size:9px;font-weight:700;'
        f'color:#EDA100;text-transform:uppercase;letter-spacing:.5px;">📋 Demandas</td></tr>'
    )
    linhas.append(_ln("Pts Pendentes",  lambda r: r["pts_pendentes"], total="avg",
                      cor_fn=lambda r: "#EDA100" if r["pts_pendentes"] > 0 else "var(--ms-texto)"))
    linhas.append(_ln("Cartões Abertos", lambda r: r["abertos"], total="avg"))
    linhas.append(_ln("Atrasados",      lambda r: r["atrasados"], total="avg",
                      cor_fn=lambda r: "#E34948" if r["atrasados"] > 0 else "var(--ms-texto)"))
    linhas.append(_ln("Urgentes",       lambda r: r["urgentes"], total="avg",
                      cor_fn=lambda r: "#E34948" if r["urgentes"] > 0 else "var(--ms-texto)"))

    linhas.append(
        f'<tr style="background:var(--ms-metric-bg);border-bottom:1px solid var(--ms-divisor);">'
        f'<td colspan="{len(cab)}" style="padding:6px 10px;font-size:9px;font-weight:700;'
        f'color:#E34948;text-transform:uppercase;letter-spacing:.5px;">⚠️ Penalidades</td></tr>'
    )
    linhas.append(_ln("Qtd Penalidades", lambda r: r["pen_qtd"], total="sum",
                      cor_fn=lambda r: "#E34948" if r["pen_qtd"] > 0 else "var(--ms-texto)"))

    st.markdown(_tabela(cab, linhas), unsafe_allow_html=True)


# ── Helper: card de item de meta individual ────────────────────────────────────

def _meta_ind_item(titulo, pct, descricao, cor=None, aguardando=False):
    """Card de item de meta individual (inline styles, sem depender do CSS do placar)."""
    _card_css = (
        'background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);'
        'border-radius:10px;padding:14px 16px;margin-bottom:8px;'
    )
    _titulo_css = 'font-size:12px;font-weight:600;color:var(--ms-texto);margin-bottom:6px;'
    _barra_bg   = 'background:var(--ms-metric-bd);border-radius:4px;height:8px;overflow:hidden;margin-bottom:3px;'
    if aguardando:
        return (f'<div style="{_card_css}">'
                f'<div style="{_titulo_css}">{titulo}</div>'
                f'<div style="font-size:10px;color:var(--ms-texto-sec);font-style:italic;">'
                f'⏳ Aguardando integração do relógio de ponto</div></div>')
    c = cor or ("#1BAF7A" if pct >= 80 else ("#EDA100" if pct >= 50 else "#4A90D9"))
    return (f'<div style="{_card_css}">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">'
            f'<div style="{_titulo_css}margin:0;">{titulo}</div>'
            f'<div style="font-size:16px;font-weight:700;color:{c};">{pct:.0f}%</div></div>'
            f'<div style="{_barra_bg}">'
            f'<div style="background:{c};width:{min(pct,100):.1f}%;height:100%;border-radius:4px;"></div></div>'
            f'<div style="font-size:9px;color:var(--ms-texto-sec);margin-top:3px;">{descricao}</div></div>')


# ── Diagnóstico: por que um indicador está vazio ──────────────────────────────

def _diagnostico_metas_individuais(tem_ponto, sem_exec, diags_pont, erro_pont, dados):
    """Mostra em números por que um indicador não preencheu.

    Sem isso, uma falha de API vira "aguardando integração" na tela — igual a
    "ainda não há dado". Quem olha não tem como saber se o problema é a
    ferramenta ou o processo.
    """
    faltando = []
    if not tem_ponto:
        faltando.append("pontualidade e ociosidade")
    if sem_exec:
        faltando.append("tempo de execução")

    # Aberto por padrao: fechado, ele parece um detalhe opcional — e e justamente
    # onde esta a causa de a tela estar vazia.
    with st.expander(f"🔎 Por que {' e '.join(faltando)} não preencheu", expanded=True):
        if not tem_ponto:
            st.markdown("**Relógio de ponto**")
            if erro_pont:
                st.error(f"Erro ao consultar: {erro_pont}")
            for ym, d in diags_pont:
                if not d:
                    continue
                st.markdown(
                    f"- {ym[1]:02d}/{ym[0]} · fonte **{d.get('fonte','?')}** · "
                    f"{d.get('pessoas',0)} pessoa(s) na RHiD · "
                    f"{d.get('mapeadas',0)} casaram com o Trello · "
                    f"{d.get('dias_com_batida',0)} dia(s) com batida"
                )
                if d.get("erro"):
                    st.warning(d["erro"])
                if d.get("exemplo_dia"):
                    st.caption("Um dia devolvido pela RHiD (é isto que preciso ver):")
                    st.code(d["exemplo_dia"], language="json")
                elif d.get("chaves_exemplo"):
                    st.caption("Campos devolvidos pela RHiD: " + ", ".join(d["chaves_exemplo"]))

        if sem_exec:
            st.markdown("**Tempo de execução (etiquetas do Trello)**")
            d = getattr(_pc, "ULTIMO_DIAGNOSTICO_ACOES", {})
            st.markdown(
                f"- HTTP **{d.get('http','—')}** · {d.get('paginas',0)} página(s) · "
                f"{d.get('acoes',0)} ação(ões) de etiqueta · "
                f"{d.get('cartoes',0)} cartão(ões) com histórico"
            )
            if d.get("erro"):
                st.warning(d["erro"])
            _concl = sum(r.get("total_concl", 0) for r in dados)
            st.caption(f"{_concl} cartão(ões) concluído(s) no período analisado.")


# ── Seção: meta individual por colaborador ────────────────────────────────────

def _secao_meta_individual(dados, membros_ativos, usuario_logado=None, eh_master=False):
    """Exibe cards de meta individual — pontuação real + campos aguardando integração.
    Penalidades ficam apenas na visão coletiva."""
    if not dados:
        return

    # Usa o mês mais recente para pct_eq/pct_maxx (salário) e para os limites de pontualidade
    r_atual = dados[-1]
    pct_eq   = r_atual["pct_mensal"]
    pct_maxx = r_atual["pct_maxx"]
    cfg      = r_atual["cfg"]
    max_tol  = int(cfg.get("max_tol_normal", 15))
    max_atr  = int(cfg.get("max_atr_normal", 10))

    # Agrega pontos do período completo (sem penalidades — penalidades são coletivas)
    pts_total  = {u: sum(r["pts_membro"].get(u, 0) for r in dados) for u in membros_ativos}
    meta_total = {u: sum(r["cfg"].get(f"meta_{u}", 1500) for r in dados) for u in membros_ativos}

    # Monitoramento em tempo real: os dados têm cache curto (30s a 5min) para não
    # bater na API a cada clique; este botão descarta tudo e relê na hora.
    _c_at, _c_leg = st.columns([1, 5])
    if _c_at.button("🔄 Atualizar agora", key="am_ind_refresh"):
        try:
            _pc._buscar_board_clear()
            _pc._acoes_cache.clear()
        except Exception:
            pass
        try:
            _rp.limpar_cache_ponto()
        except Exception:
            pass
        st.cache_data.clear()
        st.rerun()
    _c_leg.caption("Ponto vindo do relógio físico (RHiD) · tempo vindo das etiquetas do Trello")

    # ── Relógio de ponto: pontualidade e ociosidade reais ─────────────────────
    # Uma passada por mês do período; se a planilha de ponto não responder, os
    # cards voltam a dizer "aguardando" em vez de mostrar zero como se fosse dado.
    _pont = {u: {"tol": 0, "atr": 0, "atr_ent": 0, "atr_alm": 0, "dias": 0} for u in membros_ativos}
    _ocio = {u: {"disp": 0.0, "cards": 0.0} for u in membros_ativos}
    _tem_ponto = False
    _diags_pont = []
    _erro_pont = None
    try:
        for r in dados:
            ym = r.get("filtro_mes")
            if not ym:
                continue
            tc_mes = {
                u: sum(t for ts in por_col.values() for t in ts)
                for u, por_col in (r.get("tempo_membro_lista") or {}).items()
            }
            p_mes, _diag_pont = _rp.get_pontualidade_mes(*ym, com_diagnostico=True)
            _diags_pont.append((ym, _diag_pont))
            o_mes = _rp.get_ociosidade_mes(ym[0], ym[1], tc_mes)
            for u in membros_ativos:
                p = p_mes.get(u)
                if p:
                    _pont[u]["tol"]     += p["tolerancias"]
                    _pont[u]["atr"]     += p["atrasos"]
                    _pont[u]["atr_ent"] += p["atrasos_entrada"]
                    _pont[u]["atr_alm"] += p["atrasos_almoco"]
                    _pont[u]["dias"]    += p["dias_trabalhados"]
                o = o_mes.get(u)
                if o:
                    _ocio[u]["disp"]  += o["horas_disp_min"]
                    _ocio[u]["cards"] += o["tempo_cards_min"]
        _tem_ponto = any(v["dias"] > 0 for v in _pont.values())
    except Exception as e:
        _tem_ponto = False
        _erro_pont = str(e)[:200]

    # Tempo de execução medido pelas etiquetas: % de cartões dentro do estimado
    _CC_ = _pc.COLUNAS_CONFIG
    _exec = {u: {"dentro": 0, "total": 0} for u in membros_ativos}
    for r in dados:
        for u, por_col in (r.get("tempo_membro_lista") or {}).items():
            if u not in _exec:
                continue
            for nl, tempos in por_col.items():
                est = _CC_.get(nl, {}).get("tempo_min") or 0
                if est <= 0:
                    continue
                for t in tempos:
                    _exec[u]["total"] += 1
                    if t <= est:
                        _exec[u]["dentro"] += 1

    _sem_exec = not any(v["total"] for v in _exec.values())
    if eh_master and (not _tem_ponto or _sem_exec):
        _diagnostico_metas_individuais(_tem_ponto, _sem_exec, _diags_pont,
                                       _erro_pont, dados)

    def _card(username, nome):
        pts  = pts_total.get(username, 0)
        meta = meta_total.get(username, len(dados) * 1500)
        pct_pts = min(pts / meta * 100, 100) if meta > 0 else 0
        cor_pts = "#1BAF7A"  # progresso — sempre verde (cresce até 100%)

        st.markdown(f"##### {nome}")
        st.markdown(_meta_ind_item(
            "📈 Pontuação Individual", pct_pts,
            f"{pts:,.0f} / {meta:,.0f} pts · "
            f"{'✅ Meta atingida!' if pct_pts >= 100 else f'Faltam {meta - pts:,.0f} pts'}",
            cor=cor_pts
        ), unsafe_allow_html=True)
        # ── Ociosidade ────────────────────────────────────────────────────────
        o = _ocio.get(username, {"disp": 0.0, "cards": 0.0})
        if _tem_ponto and o["disp"] > 0:
            pct_ocio = max(o["disp"] - o["cards"], 0) / o["disp"] * 100
            # A barra mostra o quanto da meta (≤10%) está cumprido.
            pct_barra = 100 if pct_ocio <= 10 else max(0, 100 - (pct_ocio - 10) * 4)
            cor_ocio = "#1BAF7A" if pct_ocio <= 10 else ("#EDA100" if pct_ocio <= 20 else "#E34948")
            st.markdown(_meta_ind_item(
                "⏱️ Ociosidade abaixo de 10%", pct_barra,
                f"{pct_ocio:.1f}% ocioso · {o['cards']/60:.1f}h em cartões de "
                f"{o['disp']/60:.1f}h disponíveis",
                cor=cor_ocio
            ), unsafe_allow_html=True)
        else:
            st.markdown(_meta_ind_item(
                "⏱️ Ociosidade abaixo de 10%", 100,
                "", aguardando=True
            ), unsafe_allow_html=True)

        # ── Tempo de execução vs. estimado ────────────────────────────────────
        e = _exec.get(username, {"dentro": 0, "total": 0})
        if e["total"] > 0:
            pct_exec = e["dentro"] / e["total"] * 100
            cor_exec = "#1BAF7A" if pct_exec >= 80 else ("#EDA100" if pct_exec >= 50 else "#E34948")
            st.markdown(_meta_ind_item(
                "⚡ Tempo médio de execução abaixo do estimado", pct_exec,
                f"{e['dentro']} de {e['total']} cartões dentro do tempo estimado "
                f"· medido pela etiqueta EM ANDAMENTO",
                cor=cor_exec
            ), unsafe_allow_html=True)
        else:
            st.markdown(_meta_ind_item(
                "⚡ Tempo médio de execução abaixo do estimado", 100,
                "Nenhum cartão concluído com tempo medido no período", aguardando=True
            ), unsafe_allow_html=True)

        # ── Pontualidade ──────────────────────────────────────────────────────
        # Regra: entrada até 09h05 é tolerância; depois disso, atraso. Voltar
        # atrasado do almoço é atraso mesmo que por um minuto.
        p = _pont.get(username, {"tol": 0, "atr": 0, "atr_ent": 0, "atr_alm": 0})
        if _tem_ponto:
            tol = p["tol"]
            pct_tol = min(tol / max_tol * 100, 100) if max_tol else 0
            if tol > max_tol:
                cor_tol, extra_tol = "#E34948", f"limite estourado em {tol - max_tol}"
            elif tol >= max_tol * 0.7:
                cor_tol, extra_tol = "#EDA100", f"restam {max_tol - tol}"
            else:
                cor_tol, extra_tol = "#1BAF7A", f"restam {max_tol - tol}"
            st.markdown(_meta_ind_item(
                f"🕐 Tolerâncias de pontualidade ({max_tol}/mês)", pct_tol,
                f"{tol} de {max_tol} usadas · {extra_tol} · entrada entre "
                f"09h01 e 09h05",
                cor=cor_tol
            ), unsafe_allow_html=True)

            atr = p["atr"]
            pct_atr = min(atr / max_atr * 100, 100) if max_atr else 0
            if atr > max_atr:
                cor_atr, extra_atr = "#E34948", f"limite estourado em {atr - max_atr}"
            elif atr >= max_atr * 0.7:
                cor_atr, extra_atr = "#EDA100", f"restam {max_atr - atr}"
            else:
                cor_atr, extra_atr = "#1BAF7A", f"restam {max_atr - atr}"
            detalhe = f"{p['atr_ent']} na entrada · {p['atr_alm']} na volta do almoço"
            st.markdown(_meta_ind_item(
                f"⏰ Atrasos de pontualidade ({max_atr}/mês)", pct_atr,
                f"{atr} de {max_atr} · {extra_atr} · {detalhe}",
                cor=cor_atr
            ), unsafe_allow_html=True)
        else:
            st.markdown(_meta_ind_item(
                f"🕐 Tolerâncias de pontualidade ({max_tol}/mês)", 100, "", aguardando=True
            ), unsafe_allow_html=True)
            st.markdown(_meta_ind_item(
                f"⏰ Atrasos de pontualidade ({max_atr}/mês)", 100, "", aguardando=True
            ), unsafe_allow_html=True)

        # Calculadora de ganhos
        pct_i = min(pts / meta * 100, 100) if meta > 0 else 0
        st.markdown('<div style="margin-top:4px;"></div>', unsafe_allow_html=True)
        salario = st.number_input(
            "💰 Informe seu salário base para calcular seus ganhos mensais até o momento:",
            min_value=0.0, value=0.0, step=100.0, format="%.2f",
            key=f"am_salario_{username}", label_visibility="visible"
        )
        if salario > 0:
            # Bônus só entra quando a meta correspondente foi BATIDA (≥100%)
            meta_col_batida  = pct_eq   >= 100
            meta_ind_batida  = pct_i    >= 100
            meta_maxx_batida = pct_maxx >= 100

            bonus_col      = salario * 0.12 if meta_col_batida  else 0.0
            bonus_ind      = salario * 0.08 if meta_ind_batida  else 0.0
            bonus_maxx_col = salario * 0.05 if meta_maxx_batida else 0.0
            bonus_maxx_ind = salario * 0.05 if (meta_ind_batida and meta_maxx_batida) else 0.0
            total = salario + bonus_col + bonus_ind + bonus_maxx_col + bonus_maxx_ind

            alguma_meta_batida = meta_col_batida or meta_ind_batida or meta_maxx_batida
            cor_total = "#FFD700" if meta_maxx_batida else "#1BAF7A"

            def _bonus_val(valor, batida, cor):
                if batida:
                    return f'<div style="font-size:13px;font-weight:700;color:{cor};">+R$ {valor:,.2f}</div>'
                return '<div style="font-size:13px;font-weight:700;color:var(--ms-texto-sec);">—</div>'

            def _bonus_sub(batida, label):
                if batida:
                    return f'<div style="font-size:7px;color:var(--ms-texto-sec);">{label}</div>'
                return '<div style="font-size:7px;color:#e57373;">Meta não batida</div>'

            if alguma_meta_batida:
                st.markdown(
                    f'<div style="background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);'
                    f'border-radius:8px;padding:10px 12px;margin-top:6px;">'
                    f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr 1fr 1fr;gap:6px;">'
                    f'<div><div style="font-size:7px;color:var(--ms-texto-sec);text-transform:uppercase;">Salário Base</div>'
                    f'<div style="font-size:13px;font-weight:700;color:var(--ms-texto);">R$ {salario:,.2f}</div></div>'
                    f'<div><div style="font-size:7px;color:var(--ms-texto-sec);text-transform:uppercase;">Bônus Coletivo</div>'
                    f'{_bonus_val(bonus_col, meta_col_batida, "#1BAF7A")}'
                    f'{_bonus_sub(meta_col_batida, f"{pct_eq:.0f}% de 12%")}</div>'
                    f'<div><div style="font-size:7px;color:var(--ms-texto-sec);text-transform:uppercase;">Bônus Individual</div>'
                    f'{_bonus_val(bonus_ind, meta_ind_batida, "#1BAF7A")}'
                    f'{_bonus_sub(meta_ind_batida, f"{pct_i:.0f}% de 8%")}</div>'
                    f'<div><div style="font-size:7px;color:var(--ms-texto-sec);text-transform:uppercase;">Maxx Coletivo</div>'
                    f'{_bonus_val(bonus_maxx_col, meta_maxx_batida, "#FFD700")}'
                    f'{_bonus_sub(meta_maxx_batida, f"{pct_maxx:.0f}% de 5%")}</div>'
                    f'<div><div style="font-size:7px;color:var(--ms-texto-sec);text-transform:uppercase;">Maxx Individual</div>'
                    f'{_bonus_val(bonus_maxx_ind, meta_ind_batida and meta_maxx_batida, "#FFD700")}'
                    f'{_bonus_sub(meta_ind_batida and meta_maxx_batida, f"{pct_maxx:.0f}% de 5%")}</div>'
                    f'<div><div style="font-size:7px;color:var(--ms-texto-sec);text-transform:uppercase;">Total a Receber</div>'
                    f'<div style="font-size:16px;font-weight:700;color:{cor_total};">R$ {total:,.2f}</div></div>'
                    f'</div></div>',
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f'<div style="background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);'
                    f'border-radius:8px;padding:10px 14px;margin-top:6px;display:flex;align-items:center;gap:10px;">'
                    f'<div style="font-size:18px;">⏳</div>'
                    f'<div>'
                    f'<div style="font-size:12px;font-weight:700;color:var(--ms-texto);">Nenhuma meta atingida ainda</div>'
                    f'<div style="font-size:11px;color:var(--ms-texto-sec);">Os bônus serão calculados assim que as metas forem batidas.</div>'
                    f'</div></div>',
                    unsafe_allow_html=True
                )

    # Exibe master vê todos; membro vê só o próprio
    if eh_master:
        cols_mi = st.columns(len(membros_ativos))
        for i, (u, nome) in enumerate(membros_ativos.items()):
            with cols_mi[i]:
                _card(u, nome)
    elif usuario_logado in membros_ativos:
        _card(usuario_logado, membros_ativos[usuario_logado])
    else:
        st.caption("Meta individual disponível apenas para colaboradores e gestores.")


# ── Seção: tempo médio por coluna ─────────────────────────────────────────────

def _secao_tempos(dados):
    """Tempo médio por coluna — sempre exibe todas as colunas configuradas.
    Com dados reais: mostra média real + delta vs estimativa (min e %).
    Sem dados reais ainda: exibe a estimativa de referência em cinza."""
    _CC = _pc.COLUNAS_CONFIG

    def _fmt(m):
        if m < 60: return f"{m:.0f}min"
        h = int(m // 60); mm = int(m % 60)
        return f"{h}h{mm:02d}" if mm else f"{h}h"

    # Agrega tempo real por coluna (todos os meses do período)
    tempo_agg = {}
    for r in dados:
        for nl, tempos in r["tempo_lista"].items():
            tempo_agg.setdefault(nl, []).extend(tempos)

    # Calcula médias reais
    medias_reais = {nl: sum(t) / len(t) for nl, t in tempo_agg.items()}

    # Referência máxima para escala das barras (considera real OU estimado)
    valores_ref = []
    for nl, cfg in _CC.items():
        real = medias_reais.get(nl)
        est  = cfg.get("tempo_min", 0)
        valores_ref.append(real if real is not None else est)
    max_ref = max(valores_ref) if valores_ref else 1

    html = ""
    # Ordena por prioridade desc (mesma lógica do COLUNAS_CONFIG)
    for nl, cfg in sorted(_CC.items(), key=lambda x: -x[1]["prioridade"]):
        estimado = cfg.get("tempo_min")
        real     = medias_reais.get(nl)
        n_concl  = len(tempo_agg.get(nl, []))

        if real is not None:
            # — Tem dados reais —
            pct_barra = real / max_ref * 100
            valor_str = _fmt(real)
            if estimado and estimado > 0:
                delta_min = real - estimado
                delta_pct = (delta_min / estimado) * 100
                if delta_min <= 0:
                    sinal = f'↑ {abs(delta_min):.0f}min mais rápido ({abs(delta_pct):.0f}% ↓)'
                    delta_cor = "#1BAF7A"
                    cor_barra = "#1BAF7A"
                else:
                    sinal = f'↓ {delta_min:.0f}min mais lento (+{delta_pct:.0f}%)'
                    delta_cor = "#E34948"
                    cor_barra = "#E34948"
                sub = (f"Estimado: ~{estimado}min · {n_concl} concluído(s) · "
                       f'<span style="color:{delta_cor};font-weight:600;">{sinal}</span>')
            else:
                cor_barra = "#EDA100"
                sub = f"{n_concl} concluído(s) · sem estimativa de referência"
            html += _barra_std(nl, valor_str, pct_barra, cor=cor_barra, sub=sub)
        else:
            # — Só estimativa (nenhum dado real ainda) —
            pct_barra = (estimado / max_ref * 100) if estimado else 0
            valor_str = f"~{estimado}min" if estimado else "—"
            sub = "Referência — sem dados reais no período"
            html += _barra_std(nl, valor_str, pct_barra, cor="#555555", sub=sub)

    if html:
        st.markdown(
            f'<div style="margin-bottom:4px;display:flex;gap:16px;font-size:9px;color:var(--ms-texto-sec);">'
            f'<span>🟢 mais rápido que o estimado</span>'
            f'<span>🔴 mais lento que o estimado</span>'
            f'<span style="color:#555;">⬜ apenas estimativa (sem dados reais)</span>'
            f'</div>',
            unsafe_allow_html=True
        )
        st.markdown(html, unsafe_allow_html=True)
    else:
        st.caption("Nenhuma coluna configurada.")


# ── Seção: pendentes por coluna ────────────────────────────────────────────────

def _secao_pendentes(dados):
    """Pendentes por coluna (agregado do período)."""
    pend_agg = {}
    for r in dados:
        for nl, qtd in r["pend_lista"].items():
            pend_agg[nl] = pend_agg.get(nl, 0) + qtd

    if not pend_agg:
        st.caption("Nenhum cartão pendente no período.")
        return

    max_q = max(pend_agg.values())
    for nl, qtd in sorted(pend_agg.items(), key=lambda x: -x[1]):
        pct_b = qtd / max_q * 100
        nl_c = nl[:45] + "…" if len(nl) > 45 else nl
        st.markdown(
            f'<div style="margin-bottom:5px;">'
            f'<div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:2px;">'
            f'<span style="color:var(--ms-texto);">{nl_c}</span>'
            f'<span style="font-weight:700;color:#EDA100;">{qtd}</span></div>'
            f'<div style="background:var(--ms-metric-bd);border-radius:3px;height:5px;">'
            f'<div style="background:#EDA100;width:{pct_b:.0f}%;height:100%;border-radius:3px;"></div>'
            f'</div></div>', unsafe_allow_html=True
        )


# ── Seção: pontuação por coluna ───────────────────────────────────────────────

def _secao_pontuacao_coluna(dados):
    """Pontuação por coluna — exibe TODAS as colunas configuradas, zeradas se sem dados."""
    _CC = _pc.COLUNAS_CONFIG
    pts_agg = {}
    qtd_agg = {}
    for r in dados:
        for nl, pts in r["pts_lista"].items():
            pts_agg[nl] = pts_agg.get(nl, 0.0) + pts
        for nl, qtd in r["qtd_lista"].items():
            qtd_agg[nl] = qtd_agg.get(nl, 0) + qtd

    total_pts = sum(pts_agg.values()) if pts_agg else 0
    max_pts = max(pts_agg.values()) if pts_agg else 1

    st.markdown(
        f'<div style="font-size:9px;color:var(--ms-texto-sec);margin-bottom:6px;">'
        f'Total do período: <span style="font-weight:700;color:#EDA100;">{total_pts:,.0f} pts</span></div>',
        unsafe_allow_html=True
    )

    html = ""
    # Ordenação: com pontos primeiro (desc), depois zeradas (por prioridade desc)
    def _sort_key(nl):
        return (-pts_agg.get(nl, 0), -_CC.get(nl, {}).get("prioridade", 0))

    for nl in sorted(_CC.keys(), key=_sort_key):
        pts = pts_agg.get(nl, 0.0)
        qtd = qtd_agg.get(nl, 0)
        pct = pts / max_pts * 100 if max_pts > 0 and pts > 0 else 0
        if pts > 0:
            sub = f"{qtd} cartão(ões) concluído(s)"
            cor = "#EDA100"
        else:
            sub = "sem pontuação no período"
            cor = "#444444"
        html += _barra_std(nl, f"{pts:,.0f} pts", pct, cor=cor, sub=sub)

    if html:
        st.markdown(html, unsafe_allow_html=True)
    else:
        st.caption("Nenhuma coluna configurada.")


# ── Seção: em andamento na virada do mês ──────────────────────────────────────

def _secao_em_andamento_virada(dados):
    """Destaca cartões que estavam em andamento na virada do mês."""
    andamento = []
    for r in dados:
        for card in r.get("andamento_lista", []):
            andamento.append({**card, "mes_label": r["label"]})

    if not andamento:
        st.caption("Nenhum cartão em andamento no período.")
        return

    html = ""
    for item in andamento:
        us = item.get("membros", [])
        membros_str = ", ".join(_pc.MEMBROS_ATIVOS.get(u, u) for u in us) if isinstance(us, list) else str(us)
        membros_str = membros_str or "—"
        nome_card = str(item.get("card", ""))[:60]
        lista_card = str(item.get("lista", ""))
        mes_label = item.get("mes_label", "")
        html += (
            f'<div style="background:#EDA10015;border:1px solid #EDA10050;'
            f'border-radius:6px;padding:7px 12px;margin-bottom:5px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
            f'<div>'
            f'<div style="font-size:11px;font-weight:600;color:var(--ms-texto);">{nome_card}</div>'
            f'<div style="font-size:9px;color:var(--ms-texto-sec);">{lista_card} · {membros_str} · {mes_label}</div>'
            f'</div>'
            f'<div style="font-size:9px;font-weight:700;color:#EDA100;white-space:nowrap;margin-left:8px;">⏳ Em Andamento</div>'
            f'</div></div>'
        )

    st.markdown(
        f'<div style="background:#EDA10010;border:1px solid #EDA10040;border-radius:8px;'
        f'padding:10px 12px;margin-bottom:8px;">'
        f'<div style="font-size:9px;font-weight:700;color:#EDA100;text-transform:uppercase;'
        f'letter-spacing:.5px;margin-bottom:8px;">⏳ {len(andamento)} demanda(s) em andamento no período</div>'
        f'{html}</div>',
        unsafe_allow_html=True
    )


# ── Seção: tempo individual por colaborador ───────────────────────────────────

def _secao_tempos_individual(dados):
    """Tempo médio de execução por colaborador, medido pelas etiquetas do Trello.

    O tempo vem do campo TEMPO ACUMULADO quando alguém o preencheu; quando não,
    é medido automaticamente: o relógio começa quando o cartão recebe a etiqueta
    "EM ANDAMENTO" e para quando ela sai (descontando "INTERROMPIDO MS").
    """
    _CC = _pc.COLUNAS_CONFIG
    membros = _pc.MEMBROS_ATIVOS

    def _fmt(m):
        if m < 60: return f"{m:.0f}min"
        h = int(m // 60); mm = int(m % 60)
        return f"{h}h{mm:02d}" if mm else f"{h}h"

    # Agrega por membro → coluna (todos os meses do período)
    agg = {}
    for r in dados:
        for u, por_col in (r.get("tempo_membro_lista") or {}).items():
            for nl, tempos in por_col.items():
                agg.setdefault(u, {}).setdefault(nl, []).extend(tempos)

    st.caption(
        "Medido pela etiqueta: o tempo começa a contar quando o cartão recebe "
        "**EM ANDAMENTO** e para quando a etiqueta sai. Pausas com **INTERROMPIDO MS** "
        "são descontadas. Ninguém precisa preencher nada."
    )

    # Escala comum entre os colaboradores, para as barras serem comparáveis
    todos = [t for por_col in agg.values() for ts in por_col.values() for t in ts]
    max_ref = max(todos) if todos else 1

    cols = st.columns(len(membros))
    for i, (u, nome) in enumerate(membros.items()):
        por_col = agg.get(u, {})
        tempos_u = [t for ts in por_col.values() for t in ts]
        media_u = (sum(tempos_u) / len(tempos_u)) if tempos_u else None

        with cols[i]:
            st.markdown(
                f'<div style="font-size:12px;font-weight:600;color:var(--ms-texto);'
                f'margin-bottom:8px;">{nome}</div>',
                unsafe_allow_html=True
            )
            if media_u is None:
                valor, sub, cor = "—", "Sem cartões concluídos no período", "var(--ms-texto-sec)"
            else:
                valor = _fmt(media_u)
                n = len(tempos_u)
                sub = f"{n} cartão concluído" if n == 1 else f"{n} cartões concluídos"
                cor = "var(--ms-texto)"
            st.markdown(
                f'<div style="background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);'
                f'border-radius:8px;padding:10px 12px;margin-bottom:8px;text-align:center;">'
                f'<div style="font-size:9px;color:var(--ms-texto-sec);text-transform:uppercase;">Média Geral</div>'
                f'<div style="font-size:20px;font-weight:700;color:{cor};">{valor}</div>'
                f'<div style="font-size:8px;color:var(--ms-texto-sec);font-style:italic;">{sub}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

            # Só as colunas em que a pessoa realmente trabalhou; as demais só
            # encheriam a tela de traços.
            colunas_ord = sorted(
                por_col.keys(),
                key=lambda x: -_CC.get(x, {}).get("prioridade", 0)
            )[:8]
            if not colunas_ord:
                st.markdown(
                    '<div style="font-size:9px;color:var(--ms-texto-sec);font-style:italic;'
                    'text-align:center;">Nenhuma coluna com tempo medido</div>',
                    unsafe_allow_html=True
                )
                continue

            html = ""
            for nl in colunas_ord:
                tempos = por_col[nl]
                media = sum(tempos) / len(tempos)
                estimado = _CC.get(nl, {}).get("tempo_min")
                if estimado and estimado > 0:
                    cor_barra = "#1BAF7A" if media <= estimado else "#E34948"
                else:
                    cor_barra = "#4A90D9"
                pct = min(100, media / max_ref * 100) if max_ref else 0
                nl_c = nl[:30] + "…" if len(nl) > 30 else nl
                html += (
                    f'<div style="margin-bottom:4px;">'
                    f'<div style="display:flex;justify-content:space-between;font-size:9px;margin-bottom:1px;">'
                    f'<span style="color:var(--ms-texto-sec);">{nl_c}</span>'
                    f'<span style="color:{cor_barra};font-weight:600;">{_fmt(media)}</span></div>'
                    f'<div style="background:var(--ms-metric-bd);border-radius:3px;height:4px;">'
                    f'<div style="background:{cor_barra};width:{pct:.0f}%;height:100%;border-radius:3px;"></div>'
                    f'</div></div>'
                )
            st.markdown(html, unsafe_allow_html=True)


# ── Aba Desempenho — Gráficos HTML/SVG ───────────────────────────────────────

_CORES = ["#4A90D9", "#1BAF7A", "#EDA100", "#7B68EE"]


def _gauge_svg(pct, cor, titulo, sub="", legend=""):
    """Velocímetro semicircular SVG inline com traço colorido abaixo.
    legend: texto explicativo opcional abaixo da barra colorida."""
    p = max(0.1, min(99.9, float(pct)))
    cx, cy, r = 50, 52, 40
    def _pt(a): return cx + r * math.cos(a), cy - r * math.sin(a)
    sx, sy = _pt(math.pi); ex, ey = _pt(0)
    af = math.pi * (1 - p / 100); fx, fy = _pt(af)
    lg = 0  # semicírculo sempre < 180° → large-arc nunca necessário
    vh = 94 if legend else 82   # viewBox mais alto quando há legenda
    legend_el = (
        f'<text x="50" y="89" text-anchor="middle" font-size="5" '
        f'fill="var(--ms-texto-sec,#777)" font-style="italic">{legend}</text>'
    ) if legend else ""
    return (
        f'<div style="text-align:center;">'
        f'<svg viewBox="0 0 100 {vh}" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:130px;">'
        f'<path d="M{sx:.2f},{sy:.2f} A{r},{r} 0 0,1 {ex:.2f},{ey:.2f}" fill="none" '
        f'stroke="var(--ms-metric-bd,#2e2e2e)" stroke-width="9" stroke-linecap="round"/>'
        f'<path d="M{sx:.2f},{sy:.2f} A{r},{r} 0 {lg},1 {fx:.2f},{fy:.2f}" fill="none" '
        f'stroke="{cor}" stroke-width="9" stroke-linecap="round"/>'
        f'<text x="50" y="42" text-anchor="middle" font-size="14" font-weight="700" fill="{cor}">{p:.0f}%</text>'
        f'<text x="50" y="59" text-anchor="middle" font-size="6.5" font-weight="600" '
        f'fill="var(--ms-texto,#ccc)">{titulo}</text>'
        f'<text x="50" y="69" text-anchor="middle" font-size="5.5" '
        f'fill="var(--ms-texto-sec,#888)">{sub}</text>'
        f'<rect x="14" y="75" width="72" height="3" rx="1.5" fill="{cor}"/>'
        f'{legend_el}'
        f'</svg></div>'
    )


def _pizza_svg(segmentos, box_pct, box_label, box_cor="#4A90D9"):
    """Pizza chart SVG (pizza CHEIA) com % dentro das fatias + legenda numerada + box destaque.
    segmentos = [(cor, val, nome)]  — val absoluto, % calculado internamente."""
    # Cores suaves (mesmas mas com opacidade 0.85 via SVG)
    cx, cy, r = 140, 140, 125
    total = sum(s[1] for s in segmentos) or 1
    slices, labels_svg = [], []
    ang = -math.pi / 2
    for i, (cor, val, nome) in enumerate(segmentos):
        if val <= 0:
            continue
        frac = val / total
        ae = ang + 2 * math.pi * frac
        x1 = cx + r * math.cos(ang);  y1 = cy + r * math.sin(ang)
        x2 = cx + r * math.cos(ae);   y2 = cy + r * math.sin(ae)
        lg = 1 if frac > 0.5 else 0
        slices.append(
            f'<path d="M{cx},{cy} L{x1:.2f},{y1:.2f} A{r},{r} 0 {lg},1 {x2:.2f},{y2:.2f} Z" '
            f'fill="{cor}" fill-opacity="0.82" stroke="none"/>'
        )
        if frac >= 0.06:
            mid = (ang + ae) / 2
            lx = cx + r * 0.62 * math.cos(mid)
            ly = cy + r * 0.62 * math.sin(mid)
            labels_svg.append(
                f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" dominant-baseline="middle" '
                f'font-size="16" font-weight="700" fill="white">{frac*100:.0f}%</text>'
            )
        ang = ae
    svg = (
        f'<svg viewBox="0 0 280 280" xmlns="http://www.w3.org/2000/svg" style="width:200px;flex-shrink:0;">'
        + "".join(slices) + "".join(labels_svg) + '</svg>'
    )
    # Legenda numerada (bolinhas 01-05)
    leg_html = ""
    for i, (cor, val, nome) in enumerate(segmentos):
        leg_html += (
            f'<div style="display:flex;align-items:center;gap:7px;margin-bottom:6px;">'
            f'<div style="width:22px;height:22px;border-radius:50%;background:{cor};opacity:0.85;flex-shrink:0;'
            f'display:flex;align-items:center;justify-content:center;font-size:8px;font-weight:700;color:#fff;">{i+1:02d}</div>'
            f'<div style="font-size:10px;color:var(--ms-texto,#ccc);line-height:1.3;">'
            f'{nome}</div></div>'
        )
    # Box menor (metade do tamanho original)
    box_html = (
        f'<div style="margin-top:8px;background:{box_cor};border-radius:6px;padding:6px 10px;'
        f'display:flex;align-items:center;gap:8px;opacity:0.9;">'
        f'<div style="font-size:18px;font-weight:800;color:#fff;white-space:nowrap;">{box_pct}</div>'
        f'<div style="font-size:9px;color:rgba(255,255,255,0.92);line-height:1.4;">{box_label}</div>'
        f'</div>'
    )
    return (
        f'<div style="display:flex;align-items:flex-start;gap:14px;padding:8px 0;">'
        + svg
        + f'<div style="flex:1;padding-top:4px;">{leg_html}{box_html}</div>'
        + '</div>'
    )


def _grafico_barras_svg(labels, vals1, vals2=None, label1="Meta", label2="Realizado",
                         line_vals=None, cor1="#4A90D9", cor2_fn=None,
                         melhor_idx=None, melhor_txt=None):
    """SVG bar chart (1 ou 2 barras/mês) + linha de delta opcional. Retorna HTML."""
    n = len(labels)
    if n == 0:
        return '<div style="padding:20px;text-align:center;color:var(--ms-texto-sec);">Sem dados</div>'
    W, H = 560, 195
    ml, mr, mt, mb_m = 54, 38, 28, 46
    cw = W - ml - mr; ch = H - mt - mb_m
    all_v = list(vals1) + (list(vals2) if vals2 else [])
    max_v = max(all_v + [1])
    def bary(v): return mt + ch - max(0, v / max_v * ch)
    def barh(v): return max(1, v / max_v * ch)
    col_w = cw / n
    bw = col_w * 0.30 if vals2 is not None else col_w * 0.55
    parts = []
    # Grid / eixo Y
    for i in range(5):
        yg = mt + i * ch / 4
        vg = max_v * (4 - i) / 4
        parts += [
            f'<line x1="{ml}" y1="{yg:.0f}" x2="{W-mr}" y2="{yg:.0f}" stroke="var(--ms-divisor,#2a2a2a)" stroke-width="0.5"/>',
            f'<text x="{ml-4}" y="{yg+3:.0f}" text-anchor="end" font-size="7.5" fill="var(--ms-texto-sec,#888)">{vg:,.0f}</text>',
        ]
    line_pts = []
    for i in range(n):
        cx_c = ml + (i + 0.5) * col_w
        v1 = vals1[i]
        x1 = cx_c - bw - 1 if vals2 is not None else cx_c - bw / 2
        parts.append(f'<rect x="{x1:.1f}" y="{bary(v1):.1f}" width="{bw:.1f}" height="{barh(v1):.1f}" fill="{cor1}" opacity="0.55" rx="2"/>')
        if vals2 is not None:
            v2 = vals2[i]; c2 = cor2_fn(i) if cor2_fn else "#1BAF7A"
            parts.append(f'<rect x="{cx_c+1:.1f}" y="{bary(v2):.1f}" width="{bw:.1f}" height="{barh(v2):.1f}" fill="{c2}" opacity="0.9" rx="2"/>')
        if line_vals is not None:
            max_d = max(abs(v) for v in line_vals) or 1
            ly = mt + ch / 2 - (line_vals[i] / max_d * (ch / 2))
            line_pts.append((cx_c, ly))
        ry = H - mb_m + 10
        parts.append(
            f'<text x="{cx_c:.1f}" y="{ry}" text-anchor="end" font-size="7.5" fill="var(--ms-texto-sec,#888)" '
            f'transform="rotate(-35,{cx_c:.1f},{ry})">{labels[i]}</text>'
        )
    # Linha de delta
    if line_pts and line_vals is not None:
        max_d = max(abs(v) for v in line_vals) or 1
        y0 = mt + ch / 2
        parts.append(f'<line x1="{ml}" y1="{y0:.0f}" x2="{W-mr}" y2="{y0:.0f}" stroke="#555" stroke-width="0.7" stroke-dasharray="3,3"/>')
        for step, lbl_d in [(-1, f"{-max_d:+,.0f}"), (0, "0"), (1, f"+{max_d:,.0f}")]:
            yd = y0 - step * ch / 2
            parts.append(f'<text x="{W-mr+3}" y="{yd+3:.0f}" font-size="6.5" fill="#FF6B6B">{lbl_d}</text>')
        pts_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in line_pts)
        parts.append(f'<polyline points="{pts_str}" fill="none" stroke="#FF6B6B" stroke-width="1.8"/>')
        parts += [f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#FF6B6B"/>' for x, y in line_pts]
    # Callout melhor mês
    if melhor_idx is not None and melhor_txt and 0 <= melhor_idx < n:
        cx_c = ml + (melhor_idx + 0.5) * col_w
        v_pk = max(vals1[melhor_idx], (vals2[melhor_idx] if vals2 else 0))
        ytop = bary(v_pk) - 6; ytxt = max(mt + 2, ytop - 20)
        tw = min(len(melhor_txt) * 4.8 + 8, 110)
        parts += [
            f'<line x1="{cx_c:.1f}" y1="{ytop:.1f}" x2="{cx_c:.1f}" y2="{ytxt+12:.1f}" stroke="#EDA100" stroke-width="0.8"/>',
            f'<rect x="{cx_c-tw/2:.1f}" y="{ytxt:.1f}" width="{tw:.1f}" height="13" rx="3" fill="var(--ms-metric-bg,#1a1a1a)" stroke="#EDA100" stroke-width="0.8"/>',
            f'<text x="{cx_c:.1f}" y="{ytxt+9:.1f}" text-anchor="middle" font-size="6.5" fill="#EDA100" font-weight="700">{melhor_txt}</text>',
        ]
    # Legenda
    lx = ml
    parts += [
        f'<rect x="{lx}" y="8" width="9" height="9" fill="{cor1}" opacity="0.55" rx="1"/>',
        f'<text x="{lx+11}" y="15.5" font-size="7" fill="var(--ms-texto-sec,#888)">{label1}</text>',
    ]
    if vals2 is not None:
        parts += [
            f'<rect x="{lx+62}" y="8" width="9" height="9" fill="#1BAF7A" rx="1"/>',
            f'<text x="{lx+73}" y="15.5" font-size="7" fill="var(--ms-texto-sec,#888)">{label2}</text>',
        ]
    if line_vals is not None:
        lx3 = lx + 130
        parts += [
            f'<line x1="{lx3}" y1="12.5" x2="{lx3+14}" y2="12.5" stroke="#FF6B6B" stroke-width="1.5"/>',
            f'<circle cx="{lx3+7}" cy="12.5" r="2.5" fill="#FF6B6B"/>',
            f'<text x="{lx3+18}" y="15.5" font-size="7" fill="var(--ms-texto-sec,#888)">Delta</text>',
        ]
    return (
        f'<div style="width:100%;overflow:hidden;padding:4px 0;">'
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;">'
        + "".join(parts) + f'</svg></div>'
    )


def _chart_pontuacao_meta(dados):
    """HTML/SVG: barras meta vs realizado + linha de delta."""
    labels = [r["label"] for r in dados]
    metas  = [r["meta_eq"] for r in dados]
    saldos = [r["saldo"]   for r in dados]
    deltas = [s - m for s, m in zip(saldos, metas)]
    pcts   = [r["pct_mensal"] for r in dados]
    bi = max(range(len(pcts)), key=lambda i: pcts[i]) if pcts else None
    sinal = "+" if bi is not None and pcts[bi] >= 100 else ""
    melhor_txt = f"{sinal}{pcts[bi]:.1f}% · {labels[bi]}" if bi is not None else None
    avg_pct = sum(pcts) / len(pcts) if pcts else 0
    html = _grafico_barras_svg(
        labels, metas, saldos, label1="Meta", label2="Realizado",
        line_vals=deltas, cor1="#4A90D9",
        cor2_fn=lambda i: "#1BAF7A",
        melhor_idx=bi, melhor_txt=melhor_txt,
    )
    return html + f'<div style="text-align:right;font-size:9px;color:#EDA100;padding:0 4px 4px;">Média período: {avg_pct:.1f}%</div>'


def _chart_indices_meta(dados):
    """HTML/SVG: 4 velocímetros semicirculares."""
    n  = len(dados)
    tc = sum(r["total_concl"] for r in dados)
    pct_maxx   = sum(min(r["pct_maxx"], 100) for r in dados) / n if n > 0 else 0
    pct_atras  = sum(r["atrasados"] for r in dados) / max(tc, 1) * 100
    retrab_l   = [r["pct_retrab"] for r in dados if r["pct_retrab"] is not None]
    pct_retrab = sum(retrab_l) / len(retrab_l) if retrab_l else 0
    # Quando não há cartões concluídos, a divisão por 1 distorce a conformidade
    # (ex: 2 penalidades / 0 concluídos = 200% → vermelho indevido).
    # Só calcula a taxa quando há ao menos 1 cartão concluído.
    pen_qtd_total = sum(r["pen_qtd"] for r in dados)
    pct_pen    = (pen_qtd_total / tc * 100) if tc > 0 else 0
    pct_no_prazo = max(0, 100 - pct_atras)

    # Cores dinâmicas
    cor_qualidade   = "#1BAF7A" if pct_retrab <= 10 else "#E34948"
    cor_conformidade = "#1BAF7A" if pct_pen <= 10 else "#E34948"

    # (pct, cor, titulo, sub, legend)
    indices = [
        (min(pct_maxx, 100),
         "#FFD700",
         "Alcance MAXX",
         f"{pct_maxx:.0f}% da meta MAXX",
         ""),
        (pct_no_prazo,
         "#1BAF7A",
         "Pontualidade",
         f"{pct_atras:.1f}% dos cartões atrasaram",
         "Cartões concluídos dentro do prazo"),
        (max(0, 100 - pct_retrab),
         cor_qualidade,
         "Qualidade",
         f"{pct_retrab:.1f}% de retrabalho no período",
         ""),
        (max(0, 100 - pct_pen),
         cor_conformidade,
         "Conformidade",
         f"{max(0,100-pct_pen):.0f}% s/ penalidade · {pct_pen:.1f}% c/ pen.",
         ""),
    ]
    gauges = "".join(_gauge_svg(pct, cor, titulo, sub, legend) for pct, cor, titulo, sub, legend in indices)
    return (
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px 2px;padding:8px 0;">'
        f'{gauges}</div>'
    )


def _chart_tempo_execucao(dados):
    """HTML/SVG: pizza top 5 colunas por tempo médio de execução.
    Usa dados reais (TEMPO ACUMULADO) quando disponíveis;
    caso contrário usa tempo_min configurado em COLUNAS_CONFIG como estimativa."""
    CORES5 = ["#4A90D9", "#2C6BAF", "#1BAF7A", "#EDA100", "#7B68EE"]
    tempo_agg = {}; qtd_agg = {}
    for r in dados:
        for nl, tempos in r["tempo_lista"].items():
            tempo_agg.setdefault(nl, []).extend(tempos)
        for nl, q in r.get("qtd_lista", {}).items():
            qtd_agg[nl] = qtd_agg.get(nl, 0) + q

    estimado = False
    if not tempo_agg:
        # Fallback: usa tempo_min configurado para colunas com cartões concluídos
        for nl, cfg in _pc.COLUNAS_CONFIG.items():
            q = qtd_agg.get(nl, 0)
            if q > 0:
                tempo_agg[nl] = [cfg["tempo_min"]] * q
        estimado = True

    if not tempo_agg:
        return '<div style="padding:24px;text-align:center;color:var(--ms-texto-sec);font-size:11px;">Sem dados de tempo no período</div>'

    medias = {nl: sum(t) / len(t) for nl, t in tempo_agg.items()}
    top5   = sorted(medias.items(), key=lambda x: -x[1])[:5]
    top5_qtd   = sum(qtd_agg.get(nl, 0) for nl, _ in top5)
    total_qtd  = sum(qtd_agg.values()) or 1
    pct_demandas = top5_qtd / total_qtd * 100
    segs = []
    for i, (nl, v) in enumerate(top5):
        mins = int(v); h, m = divmod(mins, 60)
        t_str = f"{h}h{m:02d}" if h else f"{m}min"
        label = f"{nl[:20]}{'…' if len(nl)>20 else ''} · ~{t_str}"
        segs.append((CORES5[i], v, label))
    box_label = "das demandas totais\nestão nessas 5 colunas"
    if estimado:
        box_label += "\n(tempo estimado configurado)"
    return _pizza_svg(
        segs,
        box_pct=f"{pct_demandas:.0f}%",
        box_label=box_label,
        box_cor="#4A90D9",
    )


def _chart_pontuacoes(dados):
    """HTML: 4 mini gráficos de barras (pts/membro, cartões/membro, top4 cols qtd, top4 cols pts)."""
    MB = _pc.MEMBROS_ATIVOS
    CORES_MB = ["#4A90D9", "#1BAF7A", "#EDA100", "#7B68EE"]
    pts_mb = {}; qtd_mb = {}
    for r in dados:
        for u, p in r["pts_membro"].items(): pts_mb[u] = pts_mb.get(u, 0) + p
        for u, q in r.get("qtd_membro", {}).items(): qtd_mb[u] = qtd_mb.get(u, 0) + q
    pts_col = {}; qtd_col = {}
    for r in dados:
        for nl, p in r["pts_lista"].items(): pts_col[nl] = pts_col.get(nl, 0) + p
        for nl, q in r["qtd_lista"].items(): qtd_col[nl] = qtd_col.get(nl, 0) + q
    top4_qtd = sorted(qtd_col.items(), key=lambda x: -x[1])[:4]
    top4_pts = sorted(pts_col.items(), key=lambda x: -x[1])[:4]

    def _titulo(t):
        return f'<div style="font-size:9px;font-weight:700;color:var(--ms-texto-sec);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px;">{t}</div>'

    def _card(html):
        return f'<div style="background:var(--ms-metric-bg);border-radius:8px;padding:12px 14px;border:1px solid var(--ms-divisor);">{html}</div>'

    # A: pts/membro
    max_p = max(pts_mb.values(), default=1)
    a = _titulo("Pts / Colaborador")
    for i, u in enumerate([u for u in MB if pts_mb.get(u, 0) > 0]):
        a += _barra_std(MB[u], f"{pts_mb[u]:,.0f} pts", pts_mb[u] / max_p * 100, CORES_MB[i % 4])

    # B: cartões/membro
    b = _titulo("Cartões / Colaborador")
    if qtd_mb:
        max_q = max(qtd_mb.values(), default=1)
        for i, u in enumerate([u for u in MB if qtd_mb.get(u, 0) > 0]):
            b += _barra_std(MB[u], f"{qtd_mb[u]:.0f} cartões", qtd_mb[u] / max_q * 100, CORES_MB[i % 4])
    else:
        b += '<div style="font-size:10px;color:var(--ms-texto-sec);font-style:italic;padding:6px 0;">Aguardando dados Trello</div>'

    # C: top4 qtd
    c = _titulo("Top 4 Colunas · Cartões")
    if top4_qtd:
        max_q2 = top4_qtd[0][1]
        for i, (nl, v) in enumerate(top4_qtd):
            c += _barra_std(nl[:22] + ("…" if len(nl) > 22 else ""), f"{v:.0f}", v / max_q2 * 100, "#EDA100" if i == 0 else "#4A90D9")

    # D: top4 pts
    d = _titulo("Top 4 Colunas · Pontos")
    if top4_pts:
        max_p2 = top4_pts[0][1]
        for i, (nl, v) in enumerate(top4_pts):
            d += _barra_std(nl[:22] + ("…" if len(nl) > 22 else ""), f"{v:,.0f} pts", v / max_p2 * 100, "#EDA100" if i == 0 else "#4A90D9")

    return f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">' + _card(a) + _card(b) + _card(c) + _card(d) + '</div>'


# ── Desempenho Individual — helpers ───────────────────────────────────────────

def _ind_extrair_meses(dados, username):
    """Dados mensais filtrados por colaborador."""
    resultado = []
    for r in dados:
        mk = f"meta_{username}"
        meta_ind = r["cfg"].get(mk, 0)
        pts = r["pts_membro"].get(username, 0)
        resultado.append({
            "label":       r["label"],
            "meta":        meta_ind,
            "pts":         pts,
            "pen":         r["pen_membro"].get(username, 0),
            "delta":       pts - meta_ind,
            "pct":         (pts / meta_ind * 100) if meta_ind > 0 else 0,
            "total_concl": r["total_concl"],
            "atrasados":   r["atrasados"],
            "tempo_lista": r["tempo_lista"],
            "pts_lista":   r["pts_lista"],
        })
    return resultado


def _chart_ind_pts(meses, C=None):
    """HTML/SVG: meta vs realizado individual + linha de delta."""
    if not meses:
        return '<div style="padding:20px;text-align:center;color:var(--ms-texto-sec);">Sem dados</div>'
    labels = [m["label"] for m in meses]
    metas  = [m["meta"]  for m in meses]
    pts    = [m["pts"]   for m in meses]
    deltas = [m["delta"] for m in meses]
    pcts   = [m["pct"]   for m in meses]
    bi = max(range(len(pcts)), key=lambda i: pcts[i]) if pcts else None
    sinal = "+" if bi is not None and pcts[bi] >= 100 else ""
    melhor_txt = f"{sinal}{pcts[bi]:.1f}% · {labels[bi]}" if bi is not None else None
    avg_pct = sum(pcts) / len(pcts) if pcts else 0
    html = _grafico_barras_svg(
        labels, metas, pts, label1="Meta", label2="Realizado",
        line_vals=deltas, cor1="#4A90D9",
        cor2_fn=lambda i: "#1BAF7A",
        melhor_idx=bi, melhor_txt=melhor_txt,
    )
    return html + f'<div style="text-align:right;font-size:9px;color:#EDA100;padding:0 4px 4px;">Média: {avg_pct:.1f}%</div>'


def _chart_ind_indices(meses, C=None):
    """HTML/SVG: 5 velocímetros individuais com cores dinâmicas."""
    n = len(meses)
    batidos = sum(1 for m in meses if m["pct"] >= 100)
    pct_bat = (batidos / n * 100) if n > 0 else 0

    def _med_global(tl):
        vals = [sum(t) / len(t) for t in tl.values() if t]
        return sum(vals) / len(vals) if vals else None

    if n >= 2:
        t0 = _med_global(meses[0]["tempo_lista"])
        tf = _med_global(meses[-1]["tempo_lista"])
        pct_tempo = max(0, min(100, 50 + (t0 - tf) / t0 * 100)) if t0 and tf and t0 > 0 else 0
    else:
        pct_tempo = 0

    tc = sum(m["total_concl"] for m in meses)
    ta = sum(m["atrasados"]   for m in meses)
    pct_pont = max(0, 100 - (ta / max(tc, 1) * 100))

    # Ociosidade: 0 = aguardando; verde se <= 10, vermelho se > 10
    pct_ocio = 0
    cor_ocio = "#1BAF7A" if pct_ocio <= 10 else "#E34948"
    sub_ocio = f"{pct_ocio:.0f}% ociosidade" if pct_ocio > 0 else "Aguardando ponto"

    # Tolerâncias: 100 = aguardando (considera OK = verde)
    pct_tol = 100
    cor_tol = "#1BAF7A"  # aguardando = verde por padrão
    sub_tol = "Aguardando ponto"

    # Tempo médio: azul base, verde se há melhoria
    cor_tempo = "#1BAF7A" if pct_tempo > 50 else "#4A90D9"

    # Pontualidade: verde se >= 80%, vermelho se < 80%
    cor_pont = "#1BAF7A" if pct_pont >= 80 else "#E34948"

    indices = [
        (min(pct_bat, 100),  "#4A90D9",  "Pontuação Batida",   f"{batidos}/{n} meses"),
        (min(pct_ocio, 100), cor_ocio,   "Ociosidade",          sub_ocio),
        (pct_tempo,          cor_tempo,  "Redução Tempo Médio", "1º vs último mês"),
        (min(pct_tol, 100),  cor_tol,    "Tolerâncias",         sub_tol),
        (min(pct_pont, 100), cor_pont,   "Pontualidade Tarefa", f"{ta}/{max(tc,1)} concl."),
    ]
    gauges = "".join(_gauge_svg(pct, cor, titulo, sub) for pct, cor, titulo, sub in indices)
    return f'<div style="display:flex;justify-content:space-around;gap:4px;padding:8px 0;">{gauges}</div>'


def _chart_ind_participacao(dados, username, C=None):
    """HTML/SVG: pizza participação nas top 5 colunas + % contribuição individual.
    Fatias = % de pontos de cada coluna no total da equipe. Box = % do colaborador no total geral."""
    CORES5 = ["#4A90D9", "#2C6BAF", "#1BAF7A", "#EDA100", "#7B68EE"]
    pts_col_team = {}; pts_total_team = 0; pts_mb_total = 0
    for r in dados:
        for nl, p in r["pts_lista"].items(): pts_col_team[nl] = pts_col_team.get(nl, 0) + p
        pts_total_team += sum(r["pts_lista"].values())
        pts_mb_total   += r["pts_membro"].get(username, 0)
    if not pts_col_team:
        return '<div style="padding:20px;text-align:center;color:var(--ms-texto-sec);">Sem dados de pontuação</div>'
    pct_contrib = (pts_mb_total / max(pts_total_team, 1)) * 100
    top5 = sorted(pts_col_team.items(), key=lambda x: -x[1])[:5]
    segs = []
    for i, (nl, v) in enumerate(top5):
        label = f"{nl[:20]}{'…' if len(nl)>20 else ''} · {v:,.0f} pts"
        segs.append((CORES5[i], v, label))
    return _pizza_svg(
        segs,
        box_pct=f"{pct_contrib:.0f}%",
        box_label="contribuição individual\nno total de pontos da equipe",
        box_cor="#4A90D9",
    )


def _chart_ind_destaques(meses, dados, username, C=None):
    """HTML: top 4 meses individuais + top 4 colunas da equipe."""
    CORES4 = ["#EDA100", "#4A90D9", "#1BAF7A", "#7B68EE"]
    top4_m = sorted(meses, key=lambda m: -m["pts"])[:4]
    pts_col = {}
    for r in dados:
        for nl, p in r["pts_lista"].items(): pts_col[nl] = pts_col.get(nl, 0) + p
    top4_c = sorted(pts_col.items(), key=lambda x: -x[1])[:4]

    cards = []
    for i in range(4):
        if i < len(top4_m):
            m = top4_m[i]; cor = CORES4[i]
            sinal = "+" if m["delta"] >= 0 else ""
            cards.append(
                f'<div style="background:var(--ms-metric-bg);border-radius:8px;padding:12px 10px;'
                f'border:1px solid var(--ms-divisor);text-align:center;">'
                f'<div style="font-size:10px;font-weight:700;color:{cor};margin-bottom:4px;">🏆 {m["label"]}</div>'
                f'<div style="font-size:22px;font-weight:700;color:{cor};">{m["pts"]:,.0f}</div>'
                f'<div style="font-size:9px;color:var(--ms-texto);margin-top:2px;">pts alcançados</div>'
                f'<div style="font-size:8px;color:var(--ms-texto-sec);margin-top:4px;">{m["pct"]:.0f}% da meta · {sinal}{m["delta"]:,.0f} pts</div>'
                f'</div>'
            )
        else:
            cards.append(
                f'<div style="background:var(--ms-metric-bg);border-radius:8px;padding:12px 10px;'
                f'border:1px solid var(--ms-divisor);text-align:center;">'
                f'<div style="font-size:10px;font-weight:700;color:var(--ms-divisor);margin-bottom:4px;">— sem dado —</div>'
                f'<div style="font-size:22px;font-weight:700;color:var(--ms-texto-sec);">0</div>'
                f'<div style="font-size:9px;color:var(--ms-texto-sec);margin-top:2px;">pts alcançados</div>'
                f'<div style="font-size:8px;color:var(--ms-texto-sec);margin-top:4px;">0% da meta · 0 pts</div>'
                f'</div>'
            )
    rodape = ""
    if top4_c:
        cols_txt = "  ·  ".join(
            f"#{i+1} {(nl[:16]+'…') if len(nl)>16 else nl} ({v:,.0f}pts)"
            for i, (nl, v) in enumerate(top4_c)
        )
        rodape = f'<div style="font-size:9px;color:var(--ms-texto-sec);text-align:center;margin-top:8px;font-style:italic;">🏆 Top 4 colunas da equipe: {cols_txt}</div>'
    return (
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;">'
        + "".join(cards) + f'</div>{rodape}'
    )


def _chart_resumo_colabs(dados):
    """HTML: 2×4 grade comparativa de todos os colaboradores."""
    MB    = _pc.MEMBROS_ATIVOS
    users = list(MB.keys())
    CORES = ["#4A90D9", "#1BAF7A", "#EDA100", "#7B68EE"][:len(users)]

    pts_mb  = {u: sum(r["pts_membro"].get(u, 0) for r in dados) for u in users}
    meta_mb = {u: sum(r["cfg"].get(f"meta_{u}", r["cfg"].get("meta_equipe", 0)) for r in dados) for u in users}
    total_pts   = sum(pts_mb.values()) or 1
    pct_contrib = {u: pts_mb[u] / total_pts * 100 for u in users}
    pct_meta    = {u: pts_mb[u] / max(meta_mb[u], 1) * 100 for u in users}

    tempo_flat = [t for r in dados for ts in r["tempo_lista"].values() for t in ts]
    med_global = sum(tempo_flat) / len(tempo_flat) if tempo_flat else 0
    exec_mb    = {u: med_global for u in users}

    tc_total  = sum(r["total_concl"] for r in dados)
    ta_total  = sum(r["atrasados"]   for r in dados)
    atraso_mb = {u: ta_total / max(tc_total, 1) * 100 for u in users}

    # ── Dados do relógio de ponto (ociosidade + tolerâncias) ──────────────────
    # Tenta calcular para o período coberto em `dados`
    # `dados` é lista de dicts com chave "filtro_mes" = (ano, mes)
    try:
        _meses_ponto = [r.get("filtro_mes") for r in dados if r.get("filtro_mes")]
        _tem_ponto = False
        _ocio_mb   = {u: 0.0 for u in users}
        _tol_mb    = {u: 0.0 for u in users}
        _pct_ocio  = {u: 0.0 for u in users}
        _dias_trab = {u: 0   for u in users}
        _dias_aus  = {u: 0   for u in users}

        for ym in _meses_ponto:
            if not ym:
                continue
            _ano, _mes = ym
            # Tempo em cards por membro (minutos). Agora vem medido por membro
            # pelas etiquetas do cartão — antes era o total do mês dividido em
            # partes iguais, o que dava ociosidade errada para todo mundo.
            _tc_user = {}
            for r in dados:
                if r.get("filtro_mes") != ym:
                    continue
                for u, por_col in (r.get("tempo_membro_lista") or {}).items():
                    _tc_user[u] = _tc_user.get(u, 0) + sum(
                        t for ts in por_col.values() for t in ts
                    )
            _res = _rp.get_ociosidade_mes(_ano, _mes, _tc_user)
            for u in users:
                _ocio_mb[u]  += _res[u]["ociosidade_min"]
                _tol_mb[u]   += _res[u].get("qtd_tolerancias", 0)
                _dias_trab[u] += _res[u]["dias_trabalhados"]
                _dias_aus[u]  += _res[u]["dias_ausentes"]
            # Verifica se há dados reais de ponto
            if any(_res[u]["dias_trabalhados"] > 0 for u in users):
                _tem_ponto = True

        if _tem_ponto:
            max_disp = max((sum(r.get("horas_disp_min", 0) for r in [
                _rp.calcular_resumo_mes(_m[0], _m[1])[u] for _m in _meses_ponto if _m
            ]) for u in users), default=1) or 1
            _hd = {}
            for u in users:
                _hd_u = 0.0
                for ym in _meses_ponto:
                    if ym:
                        _hd_u += _rp.calcular_resumo_mes(ym[0], ym[1])[u]["total_horas_disp"]
                _hd[u] = _hd_u
            _pct_ocio = {u: (_ocio_mb[u] / max(_hd.get(u, 1), 1) * 100) for u in users}
    except Exception:
        _tem_ponto = False
        _ocio_mb   = {u: 0.0 for u in users}
        _tol_mb    = {u: 0.0 for u in users}
        _pct_ocio  = {u: 0.0 for u in users}
        _dias_trab = {u: 0   for u in users}
        _dias_aus  = {u: 0   for u in users}

    def _cor_meta(v):   return "#1BAF7A" if v >= 100 else ("#EDA100" if v >= 75 else "#4A90D9")
    def _cor_atraso(v): return "#1BAF7A" if v < 5   else ("#EDA100" if v < 15  else "#E34948")
    def _cor_ocio(v):   return "#1BAF7A" if v < 10  else ("#EDA100" if v < 25  else "#E34948")
    # Agora é contagem de tolerâncias, não minutos: verde até 60% do limite
    # mensal, amarelo até o limite, vermelho quando estoura.
    _lim_tol = int(dados[-1]["cfg"].get("max_tol_normal", 15)) if dados else 15
    def _cor_tol(v):
        return ("#1BAF7A" if v <= _lim_tol * 0.6
                else ("#EDA100" if v <= _lim_tol else "#E34948"))

    def _titulo(t):
        return f'<div style="font-size:9px;font-weight:700;color:var(--ms-texto-sec);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px;">{t}</div>'

    def _mini(titulo, vals_dict, fmt="{:.0f}", unidade="", cor_fn=None, aguardando=False):
        t = _titulo(titulo)
        if aguardando:
            return t + '<div style="font-size:9px;color:var(--ms-texto-sec);font-style:italic;padding:6px 0;">Registre o ponto na aba 🕐 Ponto</div>'
        sorted_items = sorted(vals_dict.items(), key=lambda x: -x[1])
        max_v = max((v for _, v in sorted_items), default=1) or 1
        rows = ""
        for idx, (u, v) in enumerate(sorted_items):
            cor = CORES[users.index(u)] if u in users else "#555"
            if cor_fn: cor = cor_fn(v)
            rows += _barra_std(MB.get(u, u), fmt.format(v) + unidade, v / max_v * 100, cor)
        return t + rows

    def _card(html):
        return f'<div style="background:var(--ms-metric-bg);border-radius:8px;padding:12px 14px;border:1px solid var(--ms-divisor);">{html}</div>'

    # Detalhe de ociosidade e ausências
    if _tem_ponto:
        _detalhe_ocio = _titulo("💤 Ociosidade — Detalhe")
        for u in users:
            nome_u = MB.get(u, u)
            ocio_h = _rp._fmt_min(_ocio_mb[u])
            aus    = _dias_aus[u]
            trab   = _dias_trab[u]
            cor_o  = _cor_ocio(_pct_ocio.get(u, 0))
            _detalhe_ocio += (
                f'<div style="margin-bottom:4px;font-size:10px;">'
                f'<span style="color:var(--ms-texto);">{nome_u}</span>'
                f' <span style="color:{cor_o};font-weight:700;">{ocio_h} ocioso</span>'
                f' <span style="color:var(--ms-texto-sec);">· {trab}d trabalhados'
                + (f' · <b style="color:#E34948;">{aus} ausência{"s" if aus>1 else ""}</b>' if aus else '') +
                f'</span></div>'
            )
    else:
        _detalhe_ocio = (
            _titulo("💤 Ociosidade — Detalhe") +
            '<div style="font-size:9px;color:var(--ms-texto-sec);font-style:italic;padding:6px 0;">'
            'Registre o ponto na aba 🕐 Ponto</div>'
        )

    cells = [
        _mini("🏆 Ranking — Pontuação",     pts_mb,     fmt="{:,.0f}", unidade=" pts"),
        _mini("🎯 % de Contribuição",        pct_contrib, fmt="{:.1f}", unidade="%"),
        _mini("📈 % da Meta Individual",      pct_meta,   fmt="{:.0f}", unidade="%", cor_fn=_cor_meta),
        _mini("⏱️ Média de Execução",         exec_mb,    fmt="{:.0f}", unidade=" min",
              cor_fn=lambda v: "#1BAF7A" if v <= 60 else ("#EDA100" if v <= 120 else "#E34948")),
        _mini("💤 Ociosidade",               _pct_ocio,  fmt="{:.1f}", unidade="%",
              cor_fn=_cor_ocio, aguardando=not _tem_ponto),
        _mini("🕐 Tolerâncias Utilizadas",    _tol_mb,    fmt="{:.0f}", unidade="",
              cor_fn=_cor_tol,  aguardando=not _tem_ponto),
        _mini("⏰ Índice de Atraso",          atraso_mb,  fmt="{:.1f}", unidade="%", cor_fn=_cor_atraso),
        _detalhe_ocio,
    ]
    return (
        f'<div style="margin-bottom:8px;font-size:11px;font-weight:700;color:var(--ms-texto);">📋 Resumo Comparativo — Todos os Colaboradores</div>'
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;">'
        + "".join(_card(c) for c in cells) + '</div>'
    )


def _desempenho_individual(dados, username, nome):
    """Renderiza os 4 gráficos HTML/SVG de desempenho para um colaborador."""
    meses = _ind_extrair_meses(dados, username)
    # Remove meses sem meta individual configurada (meta == 0)
    meses = [m for m in meses if m["meta"] > 0]

    row1a, row1b = st.columns(2)
    with row1a:
        st.markdown(f"#### 📊 Pontuação — {nome}")
        st.caption("Meta individual vs. realizado · linha de delta · destaque do melhor mês.")
        st.markdown(_chart_ind_pts(meses), unsafe_allow_html=True)

    with row1b:
        st.markdown("#### 🎯 Índices Individuais")
        st.caption("Pontuação batida · ociosidade · tempo médio · tolerâncias · pontualidade.")
        st.markdown(_chart_ind_indices(meses), unsafe_allow_html=True)

    st.markdown("---")
    row2a, row2b = st.columns(2)

    with row2a:
        st.markdown("#### 🍕 Participação nas Colunas")
        st.caption("Top 5 colunas mais pontuadas pela equipe · % central = contribuição individual no total.")
        st.markdown(_chart_ind_participacao(dados, username), unsafe_allow_html=True)

    with row2b:
        st.markdown("#### 🏆 Destaques do Período")
        st.caption("4 melhores meses individuais · top 4 colunas da equipe.")
        st.markdown(_chart_ind_destaques(meses, dados, username), unsafe_allow_html=True)


def _aba_desempenho(dados, dados_ano_full=None):
    """Aba Desempenho — 4 gráficos anuais de performance coletiva."""
    if not dados:
        st.caption("Sem dados para exibir no período selecionado.")
        return

    # Gráfico coletivo: exibe a partir do primeiro mês com atividade real
    dados_ano = dados_ano_full if dados_ano_full else _extend_dados_ano(dados)
    primeiro = next(
        (i for i, r in enumerate(dados_ano)
         if r.get("saldo", 0) > 0 or r.get("total_concl", 0) > 0 or r.get("pts_equipe", 0) > 0),
        0
    )
    dados_ano = dados_ano[primeiro:]

    row1_col1, row1_col2 = st.columns(2)

    with row1_col1:
        st.markdown("#### 📊 Pontuação Meta Coletiva")
        st.caption("Meta de pontuação vs. realizado · a partir do primeiro mês com atividade registrada.")
        st.markdown(_chart_pontuacao_meta(dados_ano), unsafe_allow_html=True)

    with row1_col2:
        st.markdown("#### 🎯 Índices Meta Coletiva")
        st.caption("Quatro indicadores percentuais de desempenho coletivo no período selecionado.")
        st.markdown(_chart_indices_meta(dados), unsafe_allow_html=True)

    st.markdown("---")

    row2_col1, row2_col2 = st.columns(2)

    with row2_col1:
        st.markdown("#### ⏱️ Tempo de Execução")
        st.caption("Top 5 colunas com maior tempo médio de execução · visão anual.")
        st.markdown(_chart_tempo_execucao(dados_ano if dados_ano else dados), unsafe_allow_html=True)

    with row2_col2:
        st.markdown("#### 🟠 Pontuações")
        st.caption("Pontos e cartões por colaborador · top 4 colunas mais ativas por quantidade e por pontuação.")
        st.markdown(_chart_pontuacoes(dados), unsafe_allow_html=True)


# ── Seção: configuração de metas ──────────────────────────────────────────────

def _secao_configuracao():
    st.markdown("#### ⚙️ Configurar Metas por Mês")
    st.caption("Configure as metas de qualquer mês, inclusive meses futuros. As configurações são salvas automaticamente no banco de dados.")

    agora = datetime.now()
    col_a, col_m = st.columns([1, 2])

    anos_disp = list(range(agora.year + 1, agora.year - 2, -1))
    ano_cfg = col_a.selectbox("Ano", anos_disp, index=1, key="am_cfg_ano")
    mes_cfg = col_m.selectbox(
        "Mês",
        [MESES_PT[m] for m in range(1, 13)],
        index=agora.month - 1,
        key="am_cfg_mes"
    )
    mes_cfg_num = list(range(1, 13))[[MESES_PT[m] for m in range(1, 13)].index(mes_cfg)]

    cfg_atual = mc.carregar_config(ano_cfg, mes_cfg_num)

    st.markdown(f"**Configurando: {mes_cfg} {ano_cfg}**")

    with st.form(key=f"form_cfg_{ano_cfg}_{mes_cfg_num}"):
        st.markdown("##### 🏆 Meta Coletiva")
        c1, c2 = st.columns(2)
        nova_cfg = {}
        nova_cfg["meta_equipe"] = c1.number_input(
            mc.LABELS["meta_equipe"], min_value=0, value=int(cfg_atual["meta_equipe"]), step=100
        )
        nova_cfg["meta_maxx_pct"] = c2.number_input(
            mc.LABELS["meta_maxx_pct"] + f" (atual: {cfg_atual['meta_maxx_pct']}% = {cfg_atual['meta_equipe'] * cfg_atual['meta_maxx_pct'] / 100:,.0f} pts)",
            min_value=100, max_value=300, value=int(cfg_atual["meta_maxx_pct"]), step=5
        )

        st.markdown("##### 🎯 Meta Individual por Colaborador")
        c1, c2, c3 = st.columns(3)
        nova_cfg["meta_myrelladesouza"] = c1.number_input(
            "Myrella (pts)", min_value=0, value=int(cfg_atual["meta_myrelladesouza"]), step=100
        )
        nova_cfg["meta_beatriz51"] = c2.number_input(
            "Beatriz (pts)", min_value=0, value=int(cfg_atual["meta_beatriz51"]), step=100
        )
        nova_cfg["meta_gabriel_borges"] = c3.number_input(
            "Gabriel (pts)", min_value=0, value=int(cfg_atual["meta_gabriel_borges"]), step=100
        )

        st.markdown("##### ⚠️ Limites de Penalidade")
        c1, c2 = st.columns(2)
        nova_cfg["max_pen_normal"] = c1.number_input(
            mc.LABELS["max_pen_normal"], min_value=0, value=int(cfg_atual["max_pen_normal"]), step=1
        )
        nova_cfg["max_pen_maxx"] = c2.number_input(
            mc.LABELS["max_pen_maxx"], min_value=0, value=int(cfg_atual["max_pen_maxx"]), step=1
        )

        st.markdown("##### 🕐 Pontualidade")
        c1, c2, c3, c4 = st.columns(4)
        nova_cfg["max_tol_normal"] = c1.number_input(
            "Tolerâncias (Normal)", min_value=0, value=int(cfg_atual["max_tol_normal"]), step=1
        )
        nova_cfg["max_tol_maxx"] = c2.number_input(
            "Tolerâncias (MAXX)", min_value=0, value=int(cfg_atual["max_tol_maxx"]), step=1
        )
        nova_cfg["max_atr_normal"] = c3.number_input(
            "Atrasos (Normal)", min_value=0, value=int(cfg_atual["max_atr_normal"]), step=1
        )
        nova_cfg["max_atr_maxx"] = c4.number_input(
            "Atrasos (MAXX)", min_value=0, value=int(cfg_atual["max_atr_maxx"]), step=1
        )

        st.markdown("##### 🔧 Outros Critérios")
        c1, c2, c3 = st.columns(3)
        nova_cfg["max_retrab_normal"] = c1.number_input(
            "Retrabalho máx % (Normal)", min_value=0, max_value=100,
            value=int(cfg_atual["max_retrab_normal"]), step=1
        )
        nova_cfg["max_retrab_maxx"] = c2.number_input(
            "Retrabalho máx % (MAXX)", min_value=0, max_value=100,
            value=int(cfg_atual["max_retrab_maxx"]), step=1
        )
        nova_cfg["min_membro_pct"] = c3.number_input(
            "% mín. cartões com membro", min_value=0, max_value=100,
            value=int(cfg_atual["min_membro_pct"]), step=1
        )

        submitted = st.form_submit_button("💾 Salvar configuração", use_container_width=True)
        if submitted:
            mc.salvar_config(ano_cfg, mes_cfg_num, nova_cfg)
            st.success(f"✅ Configuração de {mes_cfg} {ano_cfg} salva com sucesso!")
            st.rerun()


# ── Página principal ───────────────────────────────────────────────────────────

def pagina_analise_metas(usuario_logado):
    # ── Controle de acesso ─────────────────────────────────────────────────
    _LOGIN_MAP_GERAL = {
        "Myrella": "myrelladesouza", "Beatriz": "beatriz51",
        "Gabriel": "gabriel_borges", "MartinSousa": "martinsousa",
    }
    _username_atual = _LOGIN_MAP_GERAL.get(usuario_logado, usuario_logado.lower())
    _eh_master      = _username_atual in {m.lower() for m in _pc.MASTERS}
    _eh_membro      = _username_atual in _pc.MEMBROS_ATIVOS or _eh_master
    if not _eh_membro:
        st.warning("🔒 Acesso restrito à equipe.")
        return

    agora = datetime.now()
    st.markdown("### 📊 Análise de Metas")

    # ── SELETOR DE PERÍODO ─────────────────────────────────────────────────
    opcoes_periodo = [
        "Dentro do mês", "Mensal", "Último trimestre",
        "Último semestre", "Último Ano", "Personalizado"
    ]
    periodo = st.radio(
        "Período", opcoes_periodo, horizontal=True, key="am_periodo",
        label_visibility="collapsed"
    )

    # Determina a lista de meses a analisar
    meses_lista = []
    label_periodo = ""

    if periodo == "Dentro do mês":
        meses_lista = [(agora.year, agora.month)]
        label_periodo = f"{MESES_PT[agora.month]} {agora.year}"

    elif periodo == "Mensal":
        col_a, col_m, _ = st.columns([1, 2, 3])
        anos = list(range(agora.year + 1, agora.year - 3, -1))
        ano_sel = col_a.selectbox("Ano", anos, index=1, key="am_ano_sel")
        mes_opts = [MESES_PT[m] for m in range(1, 13)]
        mes_sel = col_m.selectbox("Mês", mes_opts, index=agora.month - 1, key="am_mes_sel")
        mes_num = mes_opts.index(mes_sel) + 1
        meses_lista = [(ano_sel, mes_num)]
        label_periodo = f"{mes_sel} {ano_sel}"

    elif periodo == "Último trimestre":
        meses_lista = _ultimos_meses(agora.year, agora.month, 3)
        label_periodo = "Último Trimestre (3 meses)"

    elif periodo == "Último semestre":
        meses_lista = _ultimos_meses(agora.year, agora.month, 6)
        label_periodo = "Último Semestre (6 meses)"

    elif periodo == "Último Ano":
        meses_lista = _ultimos_meses(agora.year, agora.month, 12)
        label_periodo = "Último Ano (12 meses)"

    else:  # Personalizado
        col_a1, col_m1, col_a2, col_m2, _ = st.columns([1, 2, 1, 2, 2])
        anos = list(range(agora.year + 1, agora.year - 3, -1))
        mes_opts = [MESES_PT[m] for m in range(1, 13)]
        ano_ini = col_a1.selectbox("Ano início", anos, index=1, key="am_ano_ini")
        mes_ini_s = col_m1.selectbox("Mês início", mes_opts, index=0, key="am_mes_ini")
        ano_fim = col_a2.selectbox("Ano fim", anos, index=1, key="am_ano_fim")
        mes_fim_s = col_m2.selectbox("Mês fim", mes_opts, index=agora.month - 1, key="am_mes_fim")
        mes_ini_n = mes_opts.index(mes_ini_s) + 1
        mes_fim_n = mes_opts.index(mes_fim_s) + 1
        a, m = ano_ini, mes_ini_n
        while (a, m) <= (ano_fim, mes_fim_n):
            meses_lista.append((a, m))
            m += 1
            if m > 12: m = 1; a += 1
        label_periodo = f"{mes_ini_s} {ano_ini} → {mes_fim_s} {ano_fim}"

    if not meses_lista:
        st.warning("Período inválido."); return

    # ── CARREGA DADOS ──────────────────────────────────────────────────────
    with st.spinner("Carregando dados do Trello e configurações..."):
        dados_board = _pc._buscar_board()

    if not dados_board or not dados_board[0]:
        st.error("Não foi possível conectar ao Trello."); return

    listas, cards, membros_map, id_p, id_t, id_i = dados_board

    with st.spinner(f"Processando {len(meses_lista)} mês(es)..."):
        dados = _analisar_meses(
            listas, cards, membros_map, id_p, id_t, id_i,
            meses_lista, _pc._processar
        )

    # A visão anual (Jan → mês atual) só é usada pela aba Desempenho, e custa uma
    # passada por mês. Calcular sempre fazia quem abre a tela em "Dentro do mês"
    # esperar por oito análises que ninguém ia ver.
    def _carregar_ano_full():
        _meses_ano = [(agora.year, m) for m in range(1, agora.month + 1)]
        with st.spinner("Preparando visão anual..."):
            return _analisar_meses(
                listas, cards, membros_map, id_p, id_t, id_i,
                _meses_ano, _pc._processar
            )

    # ── CABEÇALHO DO PERÍODO ───────────────────────────────────────────────
    total_saldo = sum(r["saldo"] for r in dados)
    media_saldo = total_saldo / len(dados)
    media_pct   = sum(r["pct_mensal"] for r in dados) / len(dados)

    st.markdown(
        f'<div style="background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);'
        f'border-radius:8px;padding:10px 16px;margin:8px 0 12px 0;'
        f'display:flex;align-items:center;gap:20px;">'
        f'<div><div style="font-size:9px;color:var(--ms-texto-sec);text-transform:uppercase;">Período</div>'
        f'<div style="font-size:14px;font-weight:700;color:var(--ms-texto);">{label_periodo}</div></div>'
        f'<div style="border-left:1px solid var(--ms-divisor);height:36px;"></div>'
        f'<div><div style="font-size:9px;color:var(--ms-texto-sec);text-transform:uppercase;">Total de Pontos</div>'
        f'<div style="font-size:22px;font-weight:700;color:{_cor_pct(media_pct)}">{total_saldo:,.0f} pts</div></div>'
        f'<div><div style="font-size:9px;color:var(--ms-texto-sec);text-transform:uppercase;">Média Mensal</div>'
        f'<div style="font-size:22px;font-weight:700;color:{_cor_pct(media_pct)}">{media_saldo:,.0f} pts</div></div>'
        f'<div><div style="font-size:9px;color:var(--ms-texto-sec);text-transform:uppercase;">% Média da Meta</div>'
        f'<div style="font-size:22px;font-weight:700;color:{_cor_pct(media_pct)}">{media_pct:.0f}%</div></div>'
        f'</div>',
        unsafe_allow_html=True
    )

    # ── SEÇÕES DE ANÁLISE ──────────────────────────────────────────────────
    # Não é st.tabs: ele executa o corpo de TODAS as abas em todo rerun — o
    # servidor nem fica sabendo qual está aberta. Aqui isso significava rodar
    # Coletivo, Individual (com as chamadas à RHiD), Desempenho (com a visão
    # anual e os gráficos) e Configuração de uma vez só, a cada clique.
    _ABAS = ["📋 Coletivo", "🎯 Individual", "📈 Desempenho", "⚙️ Configuração de Metas"]
    _chave_aba = "_am_aba"
    if _chave_aba not in st.session_state:
        _da_url = str(st.query_params.get("aba_am", "")).strip()
        st.session_state[_chave_aba] = _da_url if _da_url in _ABAS else _ABAS[0]

    _aba_sel = st.segmented_control(
        "Seção", _ABAS,
        default=st.session_state[_chave_aba],
        key="am_aba_sel", label_visibility="collapsed",
    ) or st.session_state[_chave_aba]

    if _aba_sel != st.session_state[_chave_aba]:
        st.session_state[_chave_aba] = _aba_sel
        st.query_params["aba_am"] = _aba_sel
        st.rerun()

    if _aba_sel == _ABAS[0]:
        _secao_metas_card(dados)

        st.markdown("---")
        col_t, col_p = st.columns(2)
        with col_t:
            st.markdown("#### ⏱️ Tempo Médio de Execução por Coluna")
            _secao_tempos(dados)
        with col_p:
            st.markdown("#### 🟠 Pontuação por Coluna")
            _secao_pontuacao_coluna(dados)

        st.markdown("---")
        col_pend, col_and = st.columns(2)
        with col_pend:
            st.markdown("#### 📋 Demandas Pendentes por Coluna")
            _secao_pendentes(dados)
        with col_and:
            st.markdown("#### ⏳ Em Andamento")
            _andamento_total = sum(len(r.get("andamento_lista", [])) for r in dados)
            if _andamento_total > 0:
                _secao_em_andamento_virada(dados)
            else:
                st.caption("Nenhum cartão em andamento no período.")

    elif _aba_sel == _ABAS[1]:
        # Reutiliza _eh_master/_username_atual calculados no início da página
        _username_logado = _username_atual
        _secao_meta_individual(
            dados, _pc.MEMBROS_ATIVOS,
            usuario_logado=_username_logado,
            eh_master=_eh_master
        )

        # Tempos individuais e resumo comparativo — apenas para masters
        if _eh_master:
            st.markdown("---")
            _secao_tempos_individual(dados)
            st.markdown("---")
            st.markdown("#### 📋 Resumo Comparativo dos Colaboradores")
            st.caption(
                "Grade de barras horizontais por métrica — cada painel compara todos "
                "os colaboradores em uma dimensão. Métricas que dependem do relógio de "
                "ponto serão preenchidas automaticamente após a integração."
            )
            st.markdown(_chart_resumo_colabs(dados), unsafe_allow_html=True)


    elif _aba_sel == _ABAS[2]:
        _aba_desempenho(dados, _carregar_ano_full())

        st.markdown("---")
        st.markdown("#### 📈 Desempenho Individual")

        # Masters podem selecionar qualquer colaborador; membros veem apenas o próprio
        _mb_opcoes_des = list(_pc.MEMBROS_ATIVOS.keys())
        _mb_nomes_des  = [_pc.MEMBROS_ATIVOS[u] for u in _mb_opcoes_des]
        if _eh_master:
            _mb_nome_des = st.selectbox("👤 Selecionar colaborador:", _mb_nomes_des, key="des_ind_sel")
            _mb_u_des = _mb_opcoes_des[_mb_nomes_des.index(_mb_nome_des)]
        else:
            _mb_u_des    = _username_atual
            _mb_nome_des = _pc.MEMBROS_ATIVOS.get(_mb_u_des, _mb_u_des)
            st.caption(f"Exibindo seus dados: **{_mb_nome_des}**")

        if _mb_u_des:
            # Usa o período selecionado (dados) — não o ano completo —
            # para evitar mostrar meses sem meta individual configurada.
            _desempenho_individual(dados, _mb_u_des, _mb_nome_des)

    elif _aba_sel == _ABAS[3]:
        if _eh_master:
            _secao_configuracao()
        else:
            st.warning("🔒 Configuração de metas restrita ao gestor.")
