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
            "pts_lista": dict(d["pts_lista"]),
            "qtd_lista": dict(d["qtd_lista"]),
            "pts_membro": dict(d["pts_membro"]),
            "pen_membro": dict(d["pen_membro"]),
            "qtd_membro": dict(d.get("qtd_membro", {})),
            "pen_cards": d["pen_cards"],
            "pct_retrab": pct_retrab,   # None se sem dados
            "total_concl": total_concl,
            "pct_com_membro": pct_com_membro_m,
        })
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
        pct_retrab_n = min(pct_retrab / max_retrab_n * 100, 100) if max_retrab_n > 0 else 0
        pct_retrab_x = min(pct_retrab / max_retrab_x * 100, 100) if max_retrab_x > 0 else 0
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
        b += _barra_painel("Sem atraso em prioritários P8-P10", pct_prioritarios,
                            "Nenhum cartão prioritário atrasado" if atrasados == 0 else f"{atrasados} atrasado(s)", "#1BAF7A")
        b += _barra_painel(f"Retrabalho abaixo de {max_retrab_n}%", pct_retrab_n, desc_retrab, "#E34948")
        b += _barra_painel(f"Menos de {max_pen_n+1} penalidades", pct_pen_n,
                            f"{pen_qtd} ocorrência(s) / máx {max_pen_n}", "#E34948")
        b += _barra_painel("Cartões com membro atribuído", pct_com_membro,
                            "Em andamento e concluídos no período", "#1BAF7A")
        st.markdown(f'<div style="background:var(--ms-metric-bg);border:1px solid #1BAF7A22;border-radius:8px;padding:12px 14px;">{b}</div>', unsafe_allow_html=True)

    with col_x:
        b = f'<div style="font-size:10px;font-weight:600;color:#FFD700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px;">⭐ Meta Maxx Coletiva</div>'
        b += _barra_painel(f"Pontuação +{maxx_pct-100}% acima da meta", pct_maxx,
                            f"{saldo:,.0f} / {meta_maxx:,.0f} pts (c/ penalidades -{pen_total:.0f})", "#FFD700")
        b += _barra_painel("Zero prioritários em atraso", pct_prioritarios,
                            "Nenhum cartão prioritário atrasado" if atrasados == 0 else f"{atrasados} atrasado(s)", "#FFD700")
        b += _barra_painel(f"Retrabalho abaixo de {max_retrab_x}%", pct_retrab_x, desc_retrab_x, "#E34948")
        b += _barra_painel(f"Menos de {max_pen_x+1} penalidades", pct_pen_x,
                            f"{pen_qtd} ocorrência(s) / máx {max_pen_x}", "#E34948")
        b += _barra_painel("Cartões com membro atribuído", pct_com_membro,
                            "Em andamento e concluídos no período", "#FFD700")
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
    c = cor or ("#1BAF7A" if pct >= 80 else ("#EDA100" if pct >= 50 else "#E34948"))
    return (f'<div style="{_card_css}">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">'
            f'<div style="{_titulo_css}margin:0;">{titulo}</div>'
            f'<div style="font-size:16px;font-weight:700;color:{c};">{pct:.0f}%</div></div>'
            f'<div style="{_barra_bg}">'
            f'<div style="background:{c};width:{min(pct,100):.1f}%;height:100%;border-radius:4px;"></div></div>'
            f'<div style="font-size:9px;color:var(--ms-texto-sec);margin-top:3px;">{descricao}</div></div>')


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

    def _card(username, nome):
        pts  = pts_total.get(username, 0)
        meta = meta_total.get(username, len(dados) * 1500)
        pct_pts = min(pts / meta * 100, 100) if meta > 0 else 0
        cor_pts = "#1BAF7A" if pct_pts >= 100 else ("#EDA100" if pct_pts >= 50 else "#E34948")

        st.markdown(f"##### {nome}")
        st.markdown(_meta_ind_item(
            "📈 Pontuação Individual", pct_pts,
            f"{pts:,.0f} / {meta:,.0f} pts · "
            f"{'✅ Meta atingida!' if pct_pts >= 100 else f'Faltam {meta - pts:,.0f} pts'}",
            cor=cor_pts
        ), unsafe_allow_html=True)
        st.markdown(_meta_ind_item(
            "⏱️ Ociosidade abaixo de 10%", 100,
            "Aguardando integração do relógio de ponto", aguardando=True
        ), unsafe_allow_html=True)
        st.markdown(_meta_ind_item(
            "⚡ Tempo médio de execução abaixo do estimado", 100,
            "Aguardando dados suficientes de execução", aguardando=True
        ), unsafe_allow_html=True)
        st.markdown(_meta_ind_item(
            f"🕐 Tolerâncias de pontualidade ({max_tol}/mês)", 100,
            "0 tolerâncias usadas — Aguardando integração do ponto", cor="#1BAF7A"
        ), unsafe_allow_html=True)
        st.markdown(_meta_ind_item(
            f"⏰ Atrasos de pontualidade ({max_atr}/mês)", 100,
            "0 atrasos registrados — Aguardando integração do ponto", cor="#1BAF7A"
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
            bonus_col      = salario * 0.12 * (pct_eq   / 100)
            bonus_ind      = salario * 0.08 * (pct_i    / 100)
            bonus_maxx_col = salario * 0.05 * (pct_maxx / 100)
            bonus_maxx_ind = salario * 0.05 * (pct_i / 100) * (pct_maxx / 100)
            total = salario + bonus_col + bonus_ind + bonus_maxx_col + bonus_maxx_ind
            cor_total = "#FFD700" if pct_maxx > 0 else "#1BAF7A"
            st.markdown(
                f'<div style="background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);'
                f'border-radius:8px;padding:10px 12px;margin-top:6px;">'
                f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr 1fr 1fr;gap:6px;">'
                f'<div><div style="font-size:7px;color:var(--ms-texto-sec);text-transform:uppercase;">Salário Base</div>'
                f'<div style="font-size:13px;font-weight:700;color:var(--ms-texto);">R$ {salario:,.2f}</div></div>'
                f'<div><div style="font-size:7px;color:var(--ms-texto-sec);text-transform:uppercase;">Bônus Coletivo</div>'
                f'<div style="font-size:13px;font-weight:700;color:#1BAF7A;">+R$ {bonus_col:,.2f}</div>'
                f'<div style="font-size:7px;color:var(--ms-texto-sec);">{pct_eq:.0f}% de 12%</div></div>'
                f'<div><div style="font-size:7px;color:var(--ms-texto-sec);text-transform:uppercase;">Bônus Individual</div>'
                f'<div style="font-size:13px;font-weight:700;color:#1BAF7A;">+R$ {bonus_ind:,.2f}</div>'
                f'<div style="font-size:7px;color:var(--ms-texto-sec);">{pct_i:.0f}% de 8%</div></div>'
                f'<div><div style="font-size:7px;color:var(--ms-texto-sec);text-transform:uppercase;">Maxx Coletivo</div>'
                f'<div style="font-size:13px;font-weight:700;color:#FFD700;">+R$ {bonus_maxx_col:,.2f}</div>'
                f'<div style="font-size:7px;color:var(--ms-texto-sec);">{pct_maxx:.0f}% de 5%</div></div>'
                f'<div><div style="font-size:7px;color:var(--ms-texto-sec);text-transform:uppercase;">Maxx Individual</div>'
                f'<div style="font-size:13px;font-weight:700;color:#FFD700;">+R$ {bonus_maxx_ind:,.2f}</div>'
                f'<div style="font-size:7px;color:var(--ms-texto-sec);">{pct_maxx:.0f}% de 5%</div></div>'
                f'<div><div style="font-size:7px;color:var(--ms-texto-sec);text-transform:uppercase;">Total a Receber</div>'
                f'<div style="font-size:16px;font-weight:700;color:{cor_total};">R$ {total:,.2f}</div></div>'
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


# ── Seção: tempo individual por colaborador (placeholder) ──────────────────────

def _secao_tempos_individual(dados):
    """Tempo médio de execução por colaborador — será populado em tempo real."""
    _CC = _pc.COLUNAS_CONFIG
    membros = _pc.MEMBROS_ATIVOS

    # Agrupa tempo por membro (se houver dados no futuro, virão de campos customizados por membro)
    # Por ora, exibe placeholder estruturado — os números aparecerão conforme forem registrados
    st.caption("Campos atualizados em tempo real conforme as demandas são concluídas.")

    cols = st.columns(len(membros))
    for i, (u, nome) in enumerate(membros.items()):
        with cols[i]:
            st.markdown(
                f'<div style="font-size:12px;font-weight:600;color:var(--ms-texto);'
                f'margin-bottom:8px;">{nome}</div>',
                unsafe_allow_html=True
            )
            # Card de média geral
            st.markdown(
                f'<div style="background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);'
                f'border-radius:8px;padding:10px 12px;margin-bottom:8px;text-align:center;">'
                f'<div style="font-size:9px;color:var(--ms-texto-sec);text-transform:uppercase;">Média Geral</div>'
                f'<div style="font-size:20px;font-weight:700;color:var(--ms-texto-sec);">—</div>'
                f'<div style="font-size:8px;color:var(--ms-texto-sec);font-style:italic;">Aguardando dados</div>'
                f'</div>',
                unsafe_allow_html=True
            )
            # Barras por coluna (zeradas — será preenchido em tempo real)
            colunas_ord = sorted(_CC.keys(), key=lambda x: -_CC[x]["prioridade"])
            html = ""
            for nl in colunas_ord[:8]:
                nl_c = nl[:30] + "…" if len(nl) > 30 else nl
                html += (
                    f'<div style="margin-bottom:4px;">'
                    f'<div style="display:flex;justify-content:space-between;font-size:9px;margin-bottom:1px;">'
                    f'<span style="color:var(--ms-texto-sec);">{nl_c}</span>'
                    f'<span style="color:var(--ms-texto-sec);">—</span></div>'
                    f'<div style="background:var(--ms-metric-bd);border-radius:3px;height:4px;">'
                    f'<div style="background:var(--ms-metric-bd);width:0%;height:100%;border-radius:3px;"></div>'
                    f'</div></div>'
                )
            st.markdown(html, unsafe_allow_html=True)


# ── Aba Desempenho — helpers matplotlib ──────────────────────────────────────

def _mpl_bg():
    """Retorna dicionário com cores do tema escuro para matplotlib."""
    return {
        "bg": "#1a1a1a", "ax": "#1e1e1e", "text": "#cccccc",
        "grid": "#2e2e2e", "orange": "#EDA100", "blue": "#4A90D9",
        "green": "#1BAF7A", "red": "#E34948", "gray": "#555555",
        "cores_mb": ["#4A90D9", "#E34948", "#1BAF7A"],
    }


def _chart_pontuacao_meta(dados):
    """
    Gráfico combinado: barras agrupadas (meta vs realizado) + linha de delta.
    Destaque do mês com melhor % acima da meta.
    """
    import matplotlib.pyplot as plt
    import numpy as np

    C = _mpl_bg()
    labels  = [r["label"] for r in dados]
    metas   = [r["meta_eq"] for r in dados]
    saldos  = [r["saldo"]   for r in dados]
    deltas  = [r["saldo"] - r["meta_eq"] for r in dados]
    pcts    = [r["pct_mensal"] for r in dados]
    n       = len(dados)

    x     = np.arange(n)
    w     = 0.35
    cores = [C["green"] if s >= m else C["red"] for s, m in zip(saldos, metas)]

    fig, ax1 = plt.subplots(figsize=(6, 3.2))
    fig.patch.set_facecolor(C["bg"])
    ax1.set_facecolor(C["ax"])

    ax1.bar(x - w / 2, metas,  w, color=C["blue"], alpha=0.50, label="Meta",      zorder=2)
    ax1.bar(x + w / 2, saldos, w, color=cores,      alpha=0.90, label="Realizado", zorder=2)

    # Linha delta (eixo secundário)
    ax2 = ax1.twinx()
    ax2.plot(x, deltas, color="#FF6B6B", linewidth=1.8, marker="o", markersize=4,
             zorder=3, label="Delta")
    ax2.axhline(0, color="#555", linewidth=0.7, linestyle="--")
    ax2.set_facecolor("none")
    ax2.tick_params(axis="y", colors="#FF6B6B", labelsize=6)
    ax2.spines["right"].set_color("#FF6B6B")
    ax2.spines["top"].set_visible(False)
    ax2.spines["bottom"].set_visible(False)
    ax2.spines["left"].set_visible(False)

    # Destaque mês com maior %
    if n > 0:
        bi = max(range(n), key=lambda i: pcts[i])
        max_y = max(max(metas), max(saldos)) if metas else 1
        ax1.annotate(
            f"{pcts[bi]:.1f}%\n{labels[bi]}",
            xy=(bi, max(metas[bi], saldos[bi])),
            xytext=(bi, max_y * 1.12),
            ha="center", fontsize=7, color=C["orange"], fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=C["orange"], lw=0.8),
            bbox=dict(boxstyle="round,pad=0.3", facecolor=C["bg"],
                      edgecolor=C["orange"], linewidth=0.8),
        )

    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=40, ha="right", fontsize=7, color=C["text"])
    ax1.tick_params(axis="y", colors=C["text"], labelsize=7)
    ax1.set_ylabel("Pontos", color=C["text"], fontsize=7)
    ax2.set_ylabel("Delta (pts)", color="#FF6B6B", fontsize=6)
    for sp in ["top", "right"]:
        ax1.spines[sp].set_visible(False)
    for sp in ["bottom", "left"]:
        ax1.spines[sp].set_color(C["grid"])
    ax1.grid(axis="y", color=C["grid"], linewidth=0.5, zorder=1)

    lines1, lbl1 = ax1.get_legend_handles_labels()
    lines2, lbl2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, lbl1 + lbl2,
               fontsize=6, facecolor=C["bg"], edgecolor=C["grid"],
               labelcolor=C["text"], loc="upper left")

    # Média do período no canto
    avg_pct = sum(pcts) / len(pcts) if pcts else 0
    fig.text(0.99, 0.97, f"Média período: {avg_pct:.1f}%",
             ha="right", va="top", fontsize=7, color=C["orange"])

    fig.tight_layout(rect=[0, 0, 1, 0.93])
    return fig


def _chart_indices_meta(dados):
    """
    4 velocímetros semicirculares: alcance MAXX, pontualidade, qualidade, conformidade.
    """
    import matplotlib.pyplot as plt
    import numpy as np

    C  = _mpl_bg()
    n  = len(dados)
    tc = sum(r["total_concl"] for r in dados)

    pct_maxx   = sum(min(r["pct_maxx"], 100) for r in dados) / n
    pct_atras  = sum(r["atrasados"] for r in dados) / max(tc, 1) * 100
    retrab_l   = [r["pct_retrab"] for r in dados if r["pct_retrab"] is not None]
    pct_retrab = sum(retrab_l) / len(retrab_l) if retrab_l else 0
    pct_pen    = sum(r["pen_qtd"] for r in dados) / max(tc, 1) * 100

    # (valor_exibido, cor, titulo, subtítulo)
    indices = [
        (min(pct_maxx, 100),       C["blue"],   "Alcance MAXX",   f"{pct_maxx:.0f}% da meta MAXX"),
        (max(0, 100 - pct_atras),  "#2C6BAF",   "Pontualidade",   f"{pct_atras:.1f}% atrasados"),
        (max(0, 100 - pct_retrab), C["red"],     "Qualidade",      f"{pct_retrab:.1f}% retrabalho"),
        (max(0, 100 - pct_pen),    C["orange"],  "Conformidade",   f"{pct_pen:.1f}% c/ penalidade"),
    ]

    fig, axes = plt.subplots(1, 4, figsize=(8, 2.6))
    fig.patch.set_facecolor(C["bg"])

    for ax, (pct, cor, titulo, sub) in zip(axes, indices):
        ax.set_facecolor(C["bg"])
        pct_c = max(1.0, min(99.0, pct))

        # Arco cinza de fundo (semicírculo completo: π→0)
        theta_bg = np.linspace(math.pi, 0, 200)
        ax.plot(np.cos(theta_bg), np.sin(theta_bg),
                color="#2e2e2e", linewidth=11, solid_capstyle="round")

        # Arco colorido (preenchimento proporcional ao pct)
        theta_end  = math.pi - (pct_c / 100.0 * math.pi)
        theta_fill = np.linspace(math.pi, theta_end, max(2, int(pct_c * 2)))
        ax.plot(np.cos(theta_fill), np.sin(theta_fill),
                color=cor, linewidth=11, solid_capstyle="round")

        # Textos
        ax.text(0,  0.10, f"{pct_c:.0f}%", ha="center", va="center",
                fontsize=13, fontweight="bold", color=cor)
        ax.text(0, -0.35, titulo, ha="center", va="center",
                fontsize=6.5, fontweight="700", color=C["text"])
        ax.text(0, -0.65, sub, ha="center", va="center",
                fontsize=5.5, color="#888888")

        ax.set_xlim(-1.4, 1.4)
        ax.set_ylim(-0.9, 1.3)
        ax.axis("off")

    fig.tight_layout(pad=0.3)
    return fig


def _chart_tempo_execucao(dados):
    """
    Donut chart: top 5 colunas por tempo médio de execução.
    Mostra % que o top 5 representa do tempo total.
    """
    import matplotlib.pyplot as plt
    import numpy as np

    C = _mpl_bg()
    CORES5 = [C["blue"], "#2C6BAF", C["red"], C["orange"], C["green"]]

    # Agregar tempo por coluna
    tempo_agg = {}
    for r in dados:
        for nl, tempos in r["tempo_lista"].items():
            tempo_agg.setdefault(nl, []).extend(tempos)

    if not tempo_agg:
        fig, ax = plt.subplots(figsize=(5.5, 3.5))
        fig.patch.set_facecolor(C["bg"]); ax.set_facecolor(C["bg"])
        ax.text(0.5, 0.5, "Sem dados de tempo no período", ha="center", va="center",
                color="#888", fontsize=8); ax.axis("off")
        return fig

    medias    = {nl: sum(t) / len(t) for nl, t in tempo_agg.items()}
    total_t   = sum(medias.values())
    top5      = sorted(medias.items(), key=lambda x: -x[1])[:5]
    top5_soma = sum(v for _, v in top5)
    pct_top5  = top5_soma / total_t * 100 if total_t > 0 else 0

    fig = plt.figure(figsize=(6, 3.5))
    fig.patch.set_facecolor(C["bg"])

    # Donut (eixo esquerdo)
    ax_d = fig.add_axes([0.02, 0.08, 0.48, 0.88])
    ax_d.set_facecolor(C["bg"])
    vals5  = [v for _, v in top5]
    outros = max(0, total_t - top5_soma)
    pie_vals  = vals5 + ([outros] if outros > 0 else [])
    pie_cores = CORES5[:len(top5)] + (["#2a2a2a"] if outros > 0 else [])

    ax_d.pie(pie_vals, colors=pie_cores, startangle=90,
             wedgeprops=dict(width=0.48, edgecolor=C["bg"], linewidth=2),
             counterclock=False)

    # Centro do donut
    ax_d.text(0,  0.12, f"{pct_top5:.0f}%", ha="center", va="center",
              fontsize=15, fontweight="bold", color=C["orange"])
    ax_d.text(0, -0.18, "do total", ha="center", va="center",
              fontsize=7, color="#888")

    # Legenda (eixo direito)
    ax_l = fig.add_axes([0.52, 0.02, 0.46, 0.96])
    ax_l.set_facecolor(C["bg"]); ax_l.axis("off")

    for i, (nl, v) in enumerate(top5):
        y    = 0.90 - i * 0.18
        pct  = v / total_t * 100
        mins = int(v)
        h, m = divmod(mins, 60)
        t_str = f"{h}h{m:02d}" if h else f"{m}min"

        # Bolinha numerada
        circ = plt.Circle((0.07, y), 0.055, color=CORES5[i],
                           transform=ax_l.transAxes, zorder=5, clip_on=False)
        ax_l.add_patch(circ)
        ax_l.text(0.07, y, f"{i+1:02d}", ha="center", va="center",
                  fontsize=6, fontweight="bold", color="white",
                  transform=ax_l.transAxes, zorder=6)

        # Nome + dados
        nl_s = (nl[:24] + "…") if len(nl) > 24 else nl
        ax_l.text(0.16, y + 0.04, nl_s, ha="left", va="center",
                  fontsize=6.5, color=C["text"], transform=ax_l.transAxes)
        ax_l.text(0.16, y - 0.06, f"{pct:.1f}%  ·  ~{t_str} avg",
                  ha="left", va="center", fontsize=5.5,
                  color="#888", transform=ax_l.transAxes)

    return fig


def _chart_pontuacoes(dados):
    """
    4 mini gráficos horizontais lado a lado:
    pts/colaborador · cartões/colaborador · top 4 cols por qtd · top 4 cols por pts.
    """
    import matplotlib.pyplot as plt
    import numpy as np

    C  = _mpl_bg()
    MB = _pc.MEMBROS_ATIVOS  # {username: nome_display}

    # Agregar por membro
    pts_mb = {}; qtd_mb = {}
    for r in dados:
        for u, p in r["pts_membro"].items():
            pts_mb[u] = pts_mb.get(u, 0) + p
        for u, q in r.get("qtd_membro", {}).items():
            qtd_mb[u] = qtd_mb.get(u, 0) + q

    # Agregar por coluna
    pts_col = {}; qtd_col = {}
    for r in dados:
        for nl, p in r["pts_lista"].items():
            pts_col[nl] = pts_col.get(nl, 0) + p
        for nl, q in r["qtd_lista"].items():
            qtd_col[nl] = qtd_col.get(nl, 0) + q

    top4_qtd = sorted(qtd_col.items(), key=lambda x: -x[1])[:4]
    top4_pts = sorted(pts_col.items(), key=lambda x: -x[1])[:4]

    fig, axes = plt.subplots(1, 4, figsize=(10, 3.2))
    fig.patch.set_facecolor(C["bg"])

    def _estilizar(ax, titulo):
        ax.set_facecolor(C["ax"])
        ax.tick_params(colors=C["text"], labelsize=6)
        for sp in ax.spines.values():
            sp.set_color(C["grid"])
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis="x", color=C["grid"], linewidth=0.4, zorder=0)
        ax.set_title(titulo, fontsize=7, color=C["text"], pad=5, fontweight="600")

    def _rotulo_barra_h(ax, bars, vals, fmt="{:.0f}"):
        if not vals: return
        mx = max(v for v in vals if v is not None) or 1
        for bar, val in zip(bars, vals):
            ax.text(bar.get_width() + mx * 0.03,
                    bar.get_y() + bar.get_height() / 2,
                    fmt.format(val), va="center", ha="left",
                    fontsize=6, color=C["text"])

    # --- A: Pontos por colaborador ---
    ax = axes[0]
    mb_nomes = [MB.get(u, u) for u in MB if pts_mb.get(u, 0) > 0]
    mb_pts_v = [pts_mb.get(u, 0) for u in MB if pts_mb.get(u, 0) > 0]
    if mb_nomes:
        bars = ax.barh(mb_nomes, mb_pts_v,
                       color=C["cores_mb"][:len(mb_nomes)], alpha=0.90, zorder=2)
        _rotulo_barra_h(ax, bars, mb_pts_v, "{:,.0f}")
    else:
        ax.text(0.5, 0.5, "Sem dados", ha="center", va="center",
                color="#888", fontsize=7, transform=ax.transAxes)
    ax.set_xlabel("Pontos", fontsize=6, color="#888")
    _estilizar(ax, "Pts/Colaborador")

    # --- B: Cartões por colaborador ---
    ax = axes[1]
    if qtd_mb:
        mb_nomes_q = [MB.get(u, u) for u in MB if qtd_mb.get(u, 0) > 0]
        mb_qtd_v   = [qtd_mb.get(u, 0) for u in MB if qtd_mb.get(u, 0) > 0]
        bars = ax.barh(mb_nomes_q, mb_qtd_v,
                       color=C["cores_mb"][:len(mb_nomes_q)], alpha=0.90, zorder=2)
        _rotulo_barra_h(ax, bars, mb_qtd_v, "{:.0f}")
    else:
        ax.text(0.5, 0.5, "Aguardando\ndados Trello", ha="center", va="center",
                color="#888", fontsize=6.5, transform=ax.transAxes)
    ax.set_xlabel("Cartões", fontsize=6, color="#888")
    _estilizar(ax, "Cartões/Colaborador")

    # --- C: Top 4 colunas por quantidade ---
    ax = axes[2]
    if top4_qtd:
        nls_q = [(nl[:15] + "…") if len(nl) > 15 else nl for nl, _ in top4_qtd]
        vs_q  = [v for _, v in top4_qtd]
        cores_q = [C["orange"]] + [C["blue"]] * (len(vs_q) - 1)
        bars = ax.barh(nls_q, vs_q, color=cores_q, alpha=0.90, zorder=2)
        _rotulo_barra_h(ax, bars, vs_q, "{:.0f}")
    ax.set_xlabel("Qtd", fontsize=6, color="#888")
    _estilizar(ax, "Top 4 Cols · Cartões")

    # --- D: Top 4 colunas por pontos ---
    ax = axes[3]
    if top4_pts:
        nls_p = [(nl[:15] + "…") if len(nl) > 15 else nl for nl, _ in top4_pts]
        vs_p  = [v for _, v in top4_pts]
        cores_p = [C["orange"]] + [C["blue"]] * (len(vs_p) - 1)
        bars = ax.barh(nls_p, vs_p, color=cores_p, alpha=0.90, zorder=2)
        _rotulo_barra_h(ax, bars, vs_p, "{:,.0f}")
    ax.set_xlabel("Pts", fontsize=6, color="#888")
    _estilizar(ax, "Top 4 Cols · Pontos")

    fig.tight_layout(pad=0.8, w_pad=1.2)
    return fig


# ── Desempenho Individual — helpers ───────────────────────────────────────────

def _ind_extrair_meses(dados, username):
    """Dados mensais filtrados por colaborador."""
    resultado = []
    for r in dados:
        mk = f"meta_{username}"
        meta_ind = r["cfg"].get(mk, r["cfg"].get("meta_equipe", 0))
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


def _chart_ind_pts(meses, C):
    """Barras: meta individual vs realizado + linha de delta."""
    import matplotlib.pyplot as plt
    import numpy as np

    n = len(meses)
    if n == 0:
        return None

    labels = [m["label"] for m in meses]
    metas  = [m["meta"]  for m in meses]
    pts    = [m["pts"]   for m in meses]
    deltas = [m["delta"] for m in meses]
    pcts   = [m["pct"]   for m in meses]

    x = np.arange(n)
    w = 0.35
    cores = [C["green"] if p >= me else C["red"] for p, me in zip(pts, metas)]

    fig, ax1 = plt.subplots(figsize=(6, 3.2))
    fig.patch.set_facecolor(C["bg"])
    ax1.set_facecolor(C["ax"])

    ax1.bar(x - w / 2, metas, w, color=C["blue"], alpha=0.50, label="Meta", zorder=2)
    ax1.bar(x + w / 2, pts,   w, color=cores,     alpha=0.90, label="Realizado", zorder=2)

    ax2 = ax1.twinx()
    ax2.plot(x, deltas, color="#FF6B6B", lw=1.8, marker="o", ms=4, zorder=3, label="Delta")
    ax2.axhline(0, color="#555", lw=0.7, ls="--")
    ax2.set_facecolor("none")
    ax2.tick_params(axis="y", colors="#FF6B6B", labelsize=6)
    ax2.spines["right"].set_color("#FF6B6B")
    ax2.spines["top"].set_visible(False)
    ax2.spines["bottom"].set_visible(False)
    ax2.spines["left"].set_visible(False)

    if n > 0:
        bi = max(range(n), key=lambda i: pcts[i])
        max_y = max(max(metas or [1]), max(pts or [1]))
        sinal = "+" if pcts[bi] >= 100 else ""
        ax1.annotate(
            f"{sinal}{pcts[bi]:.1f}%\n{labels[bi]}",
            xy=(bi, max(metas[bi], pts[bi])),
            xytext=(bi, max_y * 1.12),
            ha="center", fontsize=7, color=C["orange"], fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=C["orange"], lw=0.8),
            bbox=dict(boxstyle="round,pad=0.3", facecolor=C["bg"],
                      edgecolor=C["orange"], lw=0.8),
        )

    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=40, ha="right", fontsize=7, color=C["text"])
    ax1.tick_params(axis="y", colors=C["text"], labelsize=7)
    ax1.set_ylabel("Pontos", color=C["text"], fontsize=7)
    ax2.set_ylabel("Delta (pts)", color="#FF6B6B", fontsize=6)
    for sp in ["top", "right"]:
        ax1.spines[sp].set_visible(False)
    for sp in ["bottom", "left"]:
        ax1.spines[sp].set_color(C["grid"])
    ax1.grid(axis="y", color=C["grid"], lw=0.5, zorder=1)

    l1, n1 = ax1.get_legend_handles_labels()
    l2, n2 = ax2.get_legend_handles_labels()
    ax1.legend(l1 + l2, n1 + n2, fontsize=6, facecolor=C["bg"],
               edgecolor=C["grid"], labelcolor=C["text"], loc="upper left")

    avg_pct = sum(pcts) / len(pcts) if pcts else 0
    fig.text(0.99, 0.97, f"Média: {avg_pct:.1f}%", ha="right", va="top",
             fontsize=7, color=C["orange"])
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    return fig


def _chart_ind_indices(meses, C):
    """5 velocímetros individuais."""
    import matplotlib.pyplot as plt
    import numpy as np

    n = len(meses)

    # 1. Pontuação batida
    batidos   = sum(1 for m in meses if m["pct"] >= 100)
    pct_bat   = (batidos / n * 100) if n > 0 else 0

    # 2. Ociosidade — aguardando relógio de ponto
    pct_ocio  = 0

    # 3. Diminuição tempo médio (equipe como proxy)
    def _med_global(tl):
        vals = [sum(t) / len(t) for t in tl.values() if t]
        return sum(vals) / len(vals) if vals else None

    if n >= 2:
        t0 = _med_global(meses[0]["tempo_lista"])
        tf = _med_global(meses[-1]["tempo_lista"])
        if t0 and tf and t0 > 0:
            melhora = (t0 - tf) / t0 * 100
            pct_tempo = max(0, min(100, 50 + melhora))
        else:
            pct_tempo = 0
    else:
        pct_tempo = 0

    # 4. Tolerâncias — aguardando ponto
    pct_tol   = 100

    # 5. Atraso (equipe como proxy)
    tc        = sum(m["total_concl"] for m in meses)
    ta        = sum(m["atrasados"]   for m in meses)
    pct_pont  = max(0, 100 - (ta / max(tc, 1) * 100))

    indices = [
        (min(pct_bat,  100), C["blue"],   "Pontuação\nBatida",     f"{batidos}/{n} meses"),
        (pct_ocio,           "#2C6BAF",   "Ociosidade",            "Aguardando ponto"),
        (pct_tempo,          C["green"],  "Redução\nTempo Médio",  "1º vs último mês"),
        (pct_tol,            C["orange"], "Tolerâncias",           "Aguardando ponto"),
        (min(pct_pont, 100), C["red"],    "Pontualidade\nTarefa",  f"{ta} atras./{max(tc,1)} concl."),
    ]

    fig, axes = plt.subplots(1, 5, figsize=(10, 2.6))
    fig.patch.set_facecolor(C["bg"])

    for ax, (pct, cor, titulo, sub) in zip(axes, indices):
        ax.set_facecolor(C["bg"])
        pct_c = max(1.0, min(99.0, pct))

        theta_bg = np.linspace(math.pi, 0, 200)
        ax.plot(np.cos(theta_bg), np.sin(theta_bg),
                color="#2e2e2e", lw=10, solid_capstyle="round")

        theta_end  = math.pi - (pct_c / 100.0 * math.pi)
        theta_fill = np.linspace(math.pi, theta_end, max(2, int(pct_c * 2)))
        ax.plot(np.cos(theta_fill), np.sin(theta_fill),
                color=cor, lw=10, solid_capstyle="round")

        ax.text(0,  0.10, f"{pct_c:.0f}%", ha="center", va="center",
                fontsize=11, fontweight="bold", color=cor)
        ax.text(0, -0.35, titulo, ha="center", va="center",
                fontsize=6, fontweight="700", color=C["text"])
        ax.text(0, -0.70, sub, ha="center", va="center",
                fontsize=5, color="#888888")

        ax.set_xlim(-1.4, 1.4)
        ax.set_ylim(-0.95, 1.3)
        ax.axis("off")

    fig.tight_layout(pad=0.3)
    return fig


def _chart_ind_participacao(dados, username, C):
    """Donut: participação nas top 5 colunas + % de contribuição no total da equipe."""
    import matplotlib.pyplot as plt

    CORES5 = [C["blue"], "#2C6BAF", C["red"], C["orange"], C["green"]]

    pts_col_team = {}
    pts_total_team = 0
    pts_mb_total   = 0

    for r in dados:
        for nl, p in r["pts_lista"].items():
            pts_col_team[nl] = pts_col_team.get(nl, 0) + p
        pts_total_team += sum(r["pts_lista"].values())
        pts_mb_total   += r["pts_membro"].get(username, 0)

    pct_contrib = (pts_mb_total / max(pts_total_team, 1)) * 100
    top5        = sorted(pts_col_team.items(), key=lambda x: -x[1])[:5]
    top5_soma   = sum(v for _, v in top5)
    total_t     = sum(pts_col_team.values())

    if not top5:
        fig, ax = plt.subplots(figsize=(5.5, 3.5))
        fig.patch.set_facecolor(C["bg"]); ax.set_facecolor(C["bg"])
        ax.text(0.5, 0.5, "Sem dados de pontuação", ha="center", va="center",
                color="#888", fontsize=8); ax.axis("off")
        return fig

    fig = plt.figure(figsize=(6, 3.5))
    fig.patch.set_facecolor(C["bg"])

    ax_d = fig.add_axes([0.02, 0.08, 0.48, 0.88])
    ax_d.set_facecolor(C["bg"])
    vals5  = [v for _, v in top5]
    outros = max(0, total_t - top5_soma)
    pie_vals  = vals5 + ([outros] if outros > 0 else [])
    pie_cores = CORES5[:len(top5)] + (["#2a2a2a"] if outros > 0 else [])

    ax_d.pie(pie_vals, colors=pie_cores, startangle=90,
             wedgeprops=dict(width=0.48, edgecolor=C["bg"], lw=2), counterclock=False)

    ax_d.text(0,  0.15, f"{pct_contrib:.0f}%", ha="center", va="center",
              fontsize=14, fontweight="bold", color=C["orange"])
    ax_d.text(0, -0.18, "do total\nda equipe", ha="center", va="center",
              fontsize=6.5, color="#888")

    ax_l = fig.add_axes([0.52, 0.02, 0.46, 0.96])
    ax_l.set_facecolor(C["bg"]); ax_l.axis("off")

    for i, (nl, v) in enumerate(top5):
        y   = 0.90 - i * 0.18
        pct = v / total_t * 100
        circ = plt.Circle((0.07, y), 0.055, color=CORES5[i],
                           transform=ax_l.transAxes, zorder=5, clip_on=False)
        ax_l.add_patch(circ)
        ax_l.text(0.07, y, f"{i+1:02d}", ha="center", va="center",
                  fontsize=6, fontweight="bold", color="white",
                  transform=ax_l.transAxes, zorder=6)
        nl_s = (nl[:22] + "…") if len(nl) > 22 else nl
        ax_l.text(0.16, y + 0.04, nl_s, ha="left", va="center",
                  fontsize=6.5, color=C["text"], transform=ax_l.transAxes)
        ax_l.text(0.16, y - 0.06, f"{pct:.1f}%  ·  {v:,.0f} pts",
                  ha="left", va="center", fontsize=5.5, color="#888",
                  transform=ax_l.transAxes)

    return fig


def _chart_ind_destaques(meses, dados, username, C):
    """
    Top 4 meses por pontuação individual (mini barras + número grande)
    + Top 4 colunas por pontuação (barras horizontais).
    """
    import matplotlib.pyplot as plt
    import numpy as np

    n = len(meses)
    CORES4 = [C["orange"], C["blue"], C["green"], C["red"]]

    # Top 4 meses
    top4_m = sorted(meses, key=lambda m: -m["pts"])[:4]

    # Top 4 colunas (equipe)
    pts_col = {}
    for r in dados:
        for nl, p in r["pts_lista"].items():
            pts_col[nl] = pts_col.get(nl, 0) + p
    top4_c = sorted(pts_col.items(), key=lambda x: -x[1])[:4]

    fig = plt.figure(figsize=(10, 4.2))
    fig.patch.set_facecolor(C["bg"])

    # ── Linha de cima: mini barras + número ──────────────────────────────────
    for i in range(4):
        ax_bar = fig.add_subplot(2, 4, i + 1)
        ax_bar.set_facecolor("#1a1a1a")

        if i < len(top4_m):
            m = top4_m[i]
            all_pts = [md["pts"] for md in meses]
            this_lbl = m["label"]
            bar_colors = [CORES4[i] if md["label"] == this_lbl else "#333"
                          for md in meses]
            ax_bar.bar(range(n), all_pts, color=bar_colors, width=0.8, zorder=2)
            if m["meta"] > 0:
                ax_bar.axhline(m["meta"], color="#555", lw=0.8, ls="--")
            # Rótulo do mês destacado
            ax_bar.set_title(m["label"], fontsize=7, color=CORES4[i],
                             fontweight="700", pad=3)
        else:
            ax_bar.text(0.5, 0.5, "—", ha="center", va="center",
                        color="#444", fontsize=14, transform=ax_bar.transAxes)

        for sp in ax_bar.spines.values():
            sp.set_color("#2e2e2e")
        ax_bar.spines["top"].set_visible(False)
        ax_bar.spines["right"].set_visible(False)
        ax_bar.tick_params(labelbottom=False, labelleft=False,
                           colors="#555", length=2)
        ax_bar.grid(axis="y", color="#2e2e2e", lw=0.4, zorder=1)

    # ── Linha de baixo: número grande + descrição ──────────────────────────
    for i in range(4):
        ax_txt = fig.add_subplot(2, 4, i + 5)
        ax_txt.set_facecolor(C["bg"]); ax_txt.axis("off")

        if i < len(top4_m):
            m    = top4_m[i]
            cor  = CORES4[i]
            sinal = "+" if m["delta"] >= 0 else ""
            pct   = m["pct"]
            ax_txt.text(0.5, 0.82, f"{m['pts']:,.0f}", ha="center", va="top",
                        fontsize=15, fontweight="bold", color=cor,
                        transform=ax_txt.transAxes)
            ax_txt.text(0.5, 0.40, "pts alcançados", ha="center", va="center",
                        fontsize=6.5, fontweight="600", color=C["text"],
                        transform=ax_txt.transAxes)
            ax_txt.text(0.5, 0.08,
                        f"{pct:.0f}% da meta · {sinal}{m['delta']:,.0f} pts",
                        ha="center", va="center", fontsize=5.5, color="#888",
                        transform=ax_txt.transAxes)

    # ── Divider + Top 4 Colunas ──────────────────────────────────────────────
    # Adiciona texto de rodapé com top 4 colunas
    if top4_c:
        cols_txt = "  ·  ".join(
            f"#{i+1} {(nl[:18]+'…') if len(nl)>18 else nl} ({v:,.0f}pts)"
            for i, (nl, v) in enumerate(top4_c)
        )
        fig.text(0.5, 0.01,
                 f"🏆 Top 4 colunas da equipe: {cols_txt}",
                 ha="center", va="bottom", fontsize=6,
                 color="#888", style="italic")

    fig.suptitle("🏆 Melhores Meses — Pontuação Individual",
                 fontsize=8.5, color=C["text"], fontweight="600", y=0.99)
    fig.tight_layout(rect=[0, 0.06, 1, 0.97], h_pad=0.1, w_pad=0.5)
    return fig


def _chart_resumo_colabs(dados):
    """
    Painel comparativo de todos os colaboradores.
    Gráfico sugerido: grade de barras horizontais por métrica —
    cada mini-gráfico mostra todos os membros em uma dimensão diferente,
    facilitando a comparação rápida sem sobrecarregar a tela.
    """
    import matplotlib.pyplot as plt
    import numpy as np

    C  = _mpl_bg()
    MB = _pc.MEMBROS_ATIVOS
    users = list(MB.keys())
    nomes = [MB[u] for u in users]
    n     = len(users)
    CORES = [C["blue"], C["red"], C["green"], C["orange"]][:n]

    # ── Métricas disponíveis ──────────────────────────────────────────────────
    pts_mb = {u: sum(r["pts_membro"].get(u, 0) for r in dados) for u in users}
    meta_mb = {}
    for u in users:
        mk = f"meta_{u}"
        meta_mb[u] = sum(r["cfg"].get(mk, r["cfg"].get("meta_equipe", 0)) for r in dados)

    total_pts   = sum(pts_mb.values()) or 1
    pct_contrib = {u: pts_mb[u] / total_pts * 100 for u in users}
    pct_meta    = {u: pts_mb[u] / max(meta_mb[u], 1) * 100 for u in users}

    # Média execução global (equipe — individual não disponível ainda)
    tempo_flat = []
    for r in dados:
        for ts in r["tempo_lista"].values():
            tempo_flat.extend(ts)
    med_global = sum(tempo_flat) / len(tempo_flat) if tempo_flat else 0
    exec_mb    = {u: med_global for u in users}   # mesmo valor até ter por membro

    # Atraso (equipe como proxy — individual aguardando)
    tc_total   = sum(r["total_concl"] for r in dados)
    ta_total   = sum(r["atrasados"]   for r in dados)
    atr_pct    = ta_total / max(tc_total, 1) * 100
    atraso_mb  = {u: atr_pct for u in users}

    # Placeholder — aguardando relógio de ponto
    ocio_mb    = {u: 0 for u in users}
    tol_mb     = {u: 0 for u in users}

    # ── Layout: 2 linhas × 4 colunas ─────────────────────────────────────────
    fig, axes = plt.subplots(2, 4, figsize=(13, 5.0))
    fig.patch.set_facecolor(C["bg"])

    def _mini(ax, titulo, vals_dict, fmt="{:.0f}", unidade="", aguardando=False,
               cor_fn=None, limite_ref=None):
        """Mini gráfico horizontal de barras para uma métrica."""
        ax.set_facecolor(C["ax"])
        ax.tick_params(colors=C["text"], labelsize=6.5)
        for sp in ax.spines.values():
            sp.set_color(C["grid"])
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis="x", color=C["grid"], lw=0.4, zorder=0)
        ax.set_title(titulo, fontsize=7, color=C["text"], fontweight="600", pad=4)

        if aguardando:
            ax.text(0.5, 0.5, "Aguardando\nrelógio de ponto",
                    ha="center", va="center", fontsize=6.5,
                    color="#666", style="italic", transform=ax.transAxes)
            ax.set_yticks([])
            return

        # Ordena por valor decrescente
        sorted_items = sorted(vals_dict.items(), key=lambda x: -x[1])
        s_users = [u for u, _ in sorted_items]
        s_vals  = [v for _, v in sorted_items]
        s_nomes = [MB.get(u, u) for u in s_users]
        s_cores = [CORES[users.index(u)] if u in users else C["gray"] for u in s_users]

        if cor_fn:
            s_cores = [cor_fn(v) for v in s_vals]

        bars = ax.barh(s_nomes, s_vals, color=s_cores, alpha=0.9,
                       height=0.55, zorder=2)

        if limite_ref is not None:
            ax.axvline(limite_ref, color="#555", lw=0.8, ls="--")

        mx = max(s_vals) if s_vals else 1
        for bar, val in zip(bars, s_vals):
            label = fmt.format(val) + unidade
            ax.text(bar.get_width() + mx * 0.03,
                    bar.get_y() + bar.get_height() / 2,
                    label, va="center", ha="left", fontsize=6.5, color=C["text"])

        ax.set_xlim(0, max(mx * 1.35, 1))

    def _cor_meta(v):
        return C["green"] if v >= 100 else (C["orange"] if v >= 75 else C["red"])

    def _cor_atraso(v):
        return C["green"] if v < 5 else (C["orange"] if v < 15 else C["red"])

    # Linha 1
    _mini(axes[0][0], "🏆 Ranking — Pontuação",
          pts_mb, fmt="{:,.0f}", unidade=" pts")

    _mini(axes[0][1], "🎯 % de Contribuição",
          pct_contrib, fmt="{:.1f}", unidade="%")

    _mini(axes[0][2], "📈 % da Meta Individual",
          pct_meta, fmt="{:.0f}", unidade="%",
          cor_fn=_cor_meta, limite_ref=100)

    _mini(axes[0][3], "⏱️ Média de Execução",
          exec_mb, fmt="{:.0f}", unidade=" min",
          cor_fn=lambda v: C["green"] if v <= 60 else (C["orange"] if v <= 120 else C["red"]))

    # Linha 2
    _mini(axes[1][0], "💤 Ociosidade",
          ocio_mb, aguardando=True)

    _mini(axes[1][1], "🕐 Tolerâncias Utilizadas",
          tol_mb, aguardando=True)

    _mini(axes[1][2], "⏰ Índice de Atraso",
          atraso_mb, fmt="{:.1f}", unidade="%",
          cor_fn=_cor_atraso,
          limite_ref=10)

    # Célula extra: ociosidade detalhada (placeholder)
    ax_oci = axes[1][3]
    ax_oci.set_facecolor(C["ax"])
    ax_oci.set_title("💤 Ociosidade — Detalhamento", fontsize=7,
                     color=C["text"], fontweight="600", pad=4)
    ax_oci.axis("off")
    linhas_oci = [
        ("% médio/dia",    "—"),
        ("Total no mês",   "—  h"),
        ("Média diária",   "—  min/dia"),
        ("% representa",   "—"),
    ]
    for j, (lbl, val) in enumerate(linhas_oci):
        y = 0.78 - j * 0.20
        ax_oci.text(0.05, y, lbl, ha="left", va="center",
                    fontsize=6.5, color=C["text"], transform=ax_oci.transAxes)
        ax_oci.text(0.95, y, val, ha="right", va="center",
                    fontsize=6.5, color="#666", transform=ax_oci.transAxes,
                    style="italic")
    ax_oci.text(0.5, 0.02, "Aguardando relógio de ponto",
                ha="center", va="bottom", fontsize=5.5,
                color="#555", transform=ax_oci.transAxes, style="italic")
    ax_oci.patch.set_visible(True)
    ax_oci.spines["bottom"].set_color(C["grid"])

    fig.suptitle("📋 Resumo Comparativo — Todos os Colaboradores",
                 fontsize=9, color=C["text"], fontweight="700", y=1.01)
    fig.tight_layout(pad=0.8, h_pad=1.2, w_pad=0.8)
    return fig


def _desempenho_individual(dados, username, nome):
    """Renderiza os 4 gráficos de desempenho para um colaborador."""
    import matplotlib.pyplot as plt

    C    = _mpl_bg()
    meses = _ind_extrair_meses(dados, username)

    row1a, row1b = st.columns(2)

    with row1a:
        st.markdown(f"#### 📊 Pontuação — {nome}")
        st.caption("Meta individual vs. realizado · linha de delta · destaque do melhor mês.")
        fig = _chart_ind_pts(meses, C)
        if fig:
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
        else:
            st.caption("Sem dados suficientes.")

    with row1b:
        st.markdown("#### 🎯 Índices Individuais")
        st.caption("Pontuação batida · ociosidade · tempo médio · tolerâncias · pontualidade de tarefa.")
        fig = _chart_ind_indices(meses, C)
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)

    st.markdown("---")
    row2a, row2b = st.columns(2)

    with row2a:
        st.markdown("#### 🍩 Participação nas Colunas")
        st.caption(
            "Top 5 colunas mais pontuadas pela equipe · % central = contribuição individual "
            "no total de pontos do período."
        )
        fig = _chart_ind_participacao(dados, username, C)
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)

    with row2b:
        st.markdown("#### 🏆 Destaques do Período")
        st.caption("4 melhores meses individuais com pontos alcançados, % da meta e delta · top 4 colunas da equipe no rodapé.")
        fig = _chart_ind_destaques(meses, dados, username, C)
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)


def _aba_desempenho(dados):
    """Aba Desempenho — 4 gráficos anuais de performance coletiva."""
    import matplotlib.pyplot as plt

    if not dados:
        st.caption("Sem dados para exibir no período selecionado.")
        return

    row1_col1, row1_col2 = st.columns(2)

    with row1_col1:
        st.markdown("#### 📊 Pontuação Meta Coletiva")
        st.caption("Meta de pontuação vs. realizado mês a mês · linha de delta · destaque do melhor mês.")
        fig = _chart_pontuacao_meta(dados)
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)

    with row1_col2:
        st.markdown("#### 🎯 Índices Meta Coletiva")
        st.caption("Quatro indicadores percentuais de desempenho coletivo no período selecionado.")
        fig = _chart_indices_meta(dados)
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)

    st.markdown("---")

    row2_col1, row2_col2 = st.columns(2)

    with row2_col1:
        st.markdown("#### ⏱️ Tempo de Execução")
        st.caption("Top 5 colunas com maior tempo médio de execução e a representatividade de cada uma no total do período.")
        fig = _chart_tempo_execucao(dados)
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)

    with row2_col2:
        st.markdown("#### 🟠 Pontuações")
        st.caption("Pontos e cartões por colaborador · top 4 colunas mais ativas por quantidade e por pontuação.")
        fig = _chart_pontuacoes(dados)
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)


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
    if usuario_logado.lower() != "martinsousa":
        st.warning("🔒 Acesso restrito ao gestor.")
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

    # ── TABS DE ANÁLISE ────────────────────────────────────────────────────
    tab_col, tab_ind, tab_des, tab_cfg = st.tabs([
        "📋 Coletivo", "🎯 Individual", "📈 Desempenho", "⚙️ Configuração de Metas"
    ])

    with tab_col:
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

    with tab_ind:
        _eh_master_am = usuario_logado.lower() in {m.lower() for m in _pc.MASTERS}
        # Mapeia login do app → username do Trello (para membros que fazem login)
        _LOGIN_MAP = {"Myrella": "myrelladesouza", "Beatriz": "beatriz51",
                      "Gabriel": "gabriel_borges", "MartinSousa": "martinsousa"}
        _username_logado = _LOGIN_MAP.get(usuario_logado, usuario_logado)
        _secao_meta_individual(
            dados, _pc.MEMBROS_ATIVOS,
            usuario_logado=_username_logado,
            eh_master=_eh_master_am
        )
        st.markdown("---")
        _secao_tempos_individual(dados)

        # ── Resumo comparativo (todos os colaboradores) ───────────────────
        st.markdown("---")
        st.markdown("#### 📋 Resumo Comparativo dos Colaboradores")
        st.caption(
            "Grade de barras horizontais por métrica — cada painel compara todos "
            "os colaboradores em uma dimensão. Métricas que dependem do relógio de "
            "ponto serão preenchidas automaticamente após a integração."
        )
        import matplotlib.pyplot as plt
        _fig_res = _chart_resumo_colabs(dados)
        st.pyplot(_fig_res, use_container_width=True)
        plt.close(_fig_res)

        # ── Desempenho Individual com filtro ──────────────────────────────
        st.markdown("---")
        st.markdown("#### 📈 Desempenho Individual")

        # Selector visível para masters; colaboradores veem apenas o próprio
        _mb_opcoes   = list(_pc.MEMBROS_ATIVOS.keys())
        _mb_nomes    = [_pc.MEMBROS_ATIVOS[u] for u in _mb_opcoes]

        if _eh_master_am:
            _mb_nome_sel = st.selectbox(
                "👤 Selecionar colaborador:", _mb_nomes, key="am_ind_graf_sel"
            )
            _mb_u_sel = _mb_opcoes[_mb_nomes.index(_mb_nome_sel)]
        else:
            _mb_u_sel    = _username_logado
            _mb_nome_sel = _pc.MEMBROS_ATIVOS.get(_mb_u_sel, _mb_u_sel)
            st.info(f"Exibindo seus dados: **{_mb_nome_sel}**")

        if _mb_u_sel:
            _desempenho_individual(dados, _mb_u_sel, _mb_nome_sel)

    with tab_des:
        _aba_desempenho(dados)

    with tab_cfg:
        _secao_configuracao()
