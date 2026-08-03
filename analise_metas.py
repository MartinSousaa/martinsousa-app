"""
analise_metas.py — Página de Análise de Metas (exclusiva MartinSousa)
Permite visualizar desempenho histórico e configurar metas por mês.

NOTA: importa placar_core (sem UI) em vez de placar (com UI) para evitar
circular import e conflito de chaves de widgets do Streamlit.
"""
import streamlit as st
import pandas as pd
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
            "pen_cards": d["pen_cards"],
            "pct_retrab": pct_retrab,   # None se sem dados
            "total_concl": total_concl,
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
        b += f'<div style="border-top:1px solid var(--ms-divisor);margin:8px 0 8px 0;padding-top:8px;font-size:10px;font-weight:600;color:#1BAF7A;text-transform:uppercase;letter-spacing:.5px;">🎯 Meta Individual</div>'
        b += _barra_painel_dash("Pontuação Individual", "Veja a aba Individual")
        b += _barra_painel_dash("Ociosidade abaixo de 10%", "Aguardando relógio de ponto")
        b += _barra_painel_dash("Tempo médio abaixo do estimado", "Aguardando histórico de execução")
        b += _barra_painel_dash(f"Pontualidade: máx {int(cfg.get('max_tol_normal',15))} tolerâncias", "Aguardando integração do ponto")
        b += _barra_painel_dash(f"Pontualidade: máx {int(cfg.get('max_atr_normal',10))} atrasos", "Aguardando integração do ponto")
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
        b += f'<div style="height:32px;"></div>'
        b += f'<div style="border-top:1px solid var(--ms-divisor);margin:8px 0 8px 0;padding-top:8px;font-size:10px;font-weight:600;color:#FFD700;text-transform:uppercase;letter-spacing:.5px;">⭐ Meta Maxx Individual</div>'
        b += _barra_painel_dash("Pontuação Individual", "Veja a aba Individual")
        b += _barra_painel_dash("Ociosidade abaixo de 5%", "Aguardando relógio de ponto")
        b += _barra_painel_dash("Tempo médio abaixo do estimado", "Aguardando histórico de execução")
        b += _barra_painel_dash(f"Pontualidade: máx {int(cfg.get('max_tol_maxx',7))} tolerâncias", "Aguardando integração do ponto")
        b += _barra_painel_dash(f"Pontualidade: máx {int(cfg.get('max_atr_maxx',5))} atrasos", "Aguardando integração do ponto")
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
    """Tempo médio por coluna com barras horizontais estilo Pendentes."""
    _CC = _pc.COLUNAS_CONFIG

    tempo_agg = {}
    for r in dados:
        for nl, tempos in r["tempo_lista"].items():
            tempo_agg.setdefault(nl, []).extend(tempos)

    if not tempo_agg:
        st.caption("Nenhum dado de tempo de execução para o período.")
        return

    def _fmt(m):
        if m < 60: return f"{m:.0f}min"
        h = int(m // 60); mm = int(m % 60)
        return f"{h}h{mm:02d}" if mm else f"{h}h"

    medias = {nl: sum(t) / len(t) for nl, t in tempo_agg.items()}
    max_med = max(medias.values()) if medias else 1

    html = ""
    for nl, media in sorted(medias.items(), key=lambda x: -x[1]):
        estimado = _CC.get(nl, {}).get("tempo_min", None)
        cor = "#1BAF7A" if (estimado and media <= estimado) else "#EDA100"
        sub = (f"Estimado: ~{estimado}min · {len(tempo_agg[nl])} concluído(s)"
               if estimado else f"{len(tempo_agg[nl])} concluído(s)")
        pct = media / max_med * 100
        html += _barra_std(nl, _fmt(media), pct, cor=cor, sub=sub)

    st.markdown(html, unsafe_allow_html=True)


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
    """Pontuação e quantidade de cartões concluídos por coluna."""
    pts_agg = {}
    qtd_agg = {}
    for r in dados:
        for nl, pts in r["pts_lista"].items():
            pts_agg[nl] = pts_agg.get(nl, 0.0) + pts
        for nl, qtd in r["qtd_lista"].items():
            qtd_agg[nl] = qtd_agg.get(nl, 0) + qtd

    if not pts_agg:
        st.caption("Nenhum dado de pontuação por coluna no período.")
        return

    total_pts = sum(pts_agg.values())
    max_pts = max(pts_agg.values()) if pts_agg else 1

    col1, col2 = st.columns([3, 1])
    with col1:
        html = ""
        for nl, pts in sorted(pts_agg.items(), key=lambda x: -x[1]):
            qtd = qtd_agg.get(nl, 0)
            pct = pts / max_pts * 100
            sub = f"{qtd} cartão(ões) concluído(s)"
            html += _barra_std(nl, f"{pts:,.0f} pts", pct, cor="#EDA100", sub=sub)
        st.markdown(html, unsafe_allow_html=True)
    with col2:
        st.markdown(
            f'<div style="background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);'
            f'border-radius:8px;padding:12px 14px;text-align:center;">'
            f'<div style="font-size:9px;color:var(--ms-texto-sec);text-transform:uppercase;margin-bottom:4px;">'
            f'Total do Período</div>'
            f'<div style="font-size:28px;font-weight:700;color:#EDA100;">{total_pts:,.0f}</div>'
            f'<div style="font-size:10px;color:var(--ms-texto-sec);">pontos</div>'
            f'</div>',
            unsafe_allow_html=True
        )


# ── Seção: em andamento na virada do mês ──────────────────────────────────────

def _secao_em_andamento_virada(dados):
    """Destaca cartões que estavam em andamento na virada do mês."""
    andamento = []
    for r in dados:
        for card in r.get("andamento_lista", []):
            andamento.append({**card, "mes_label": r["label"]})

    if not andamento:
        st.caption("Nenhum cartão estava em andamento na virada do mês.")
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
        f'letter-spacing:.5px;margin-bottom:8px;">⏳ {len(andamento)} demanda(s) em andamento na virada do mês</div>'
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
    tab_col, tab_ind, tab_cfg = st.tabs([
        "📋 Coletivo", "🎯 Individual", "⚙️ Configuração de Metas"
    ])

    with tab_col:
        _secao_metas_card(dados)

        st.markdown("---")
        _secao_coletiva(dados)

        st.markdown("---")
        st.markdown("#### ⏱️ Tempo Médio de Execução por Coluna")
        _secao_tempos(dados)

        st.markdown("---")
        st.markdown("#### 🟠 Pontuação por Coluna")
        _secao_pontuacao_coluna(dados)

        st.markdown("---")
        st.markdown("#### 📋 Demandas Pendentes por Coluna")
        _secao_pendentes(dados)

        _andamento_total = sum(len(r.get("andamento_lista", [])) for r in dados)
        if _andamento_total > 0:
            st.markdown("---")
            st.markdown("#### ⏳ Em Andamento na Virada do Mês")
            _secao_em_andamento_virada(dados)

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

    with tab_cfg:
        _secao_configuracao()
