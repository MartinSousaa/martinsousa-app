"""
analise_metas.py — Página de Análise de Metas (exclusiva MartinSousa)
Permite visualizar desempenho histórico e configurar metas por mês.

NOTA: importa placar_core (sem UI) em vez de placar (com UI) para evitar
circular import e conflito de chaves de widgets do Streamlit.
"""
import streamlit as st
import pandas as pd
import math
import calendar
from datetime import datetime, time

import metas_config as mc
import placar_core as _pc
import explicacao_metas as _expl
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
        # Cartões com membro: concluídos no mês + o que está em andamento, e
        # em andamento só conta no mês corrente — cartão aberto em agosto e
        # tocado em setembro é assunto de setembro, não piora agosto de novo.
        (pct_com_membro_m, _ativos_sem_mb_l,
         _total_ativos, _desc_com_membro) = _pc.pct_com_membro(d, (ano, mes))
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
            "atrasados_pri": d.get("atrasados_pri", 0),
            "atrasados_pri_lista": d.get("atrasados_pri_lista", []),
            "em_andamento": d["em_andamento"],
            "andamento_lista": d["andamento_lista"],
            "pend_lista": d["pend_lista"],
            "tempo_lista": d["tempo_lista"],
            "tempo_membro_lista": d.get("tempo_membro_lista", {}),
            # Estas duas sao calculadas por _processar e eram descartadas aqui.
            # Este dicionario e montado chave a chave, entao o que nao e listado
            # simplesmente nao existe do lado de fora — e nada avisa.
            #
            # entregas_membro sustenta a curva de execucao e os cartoes por
            # coluna: sem ela as duas telas diziam "nenhuma entrega" para quem
            # tinha 226 cartoes concluidos.
            #
            # intervalos_membro e a linha do tempo que a ociosidade usa para
            # aplicar as folgas de 10 e 5 minutos. Sem ela, _ponto_por_membro
            # caia no calculo grosseiro por subtracao de totais — funcionava, e
            # dava outro numero.
            #
            # atividade_dia responde a pergunta que a entrega nao responde: num
            # dia sem nenhum cartao concluido, a pessoa encostou no trabalho?
            "entregas_membro": d.get("entregas_membro", {}),
            "intervalos_membro": d.get("intervalos_membro", {}),
            "atividade_dia": d.get("atividade_dia", {}),
            "execucoes_dia": d.get("execucoes_dia", {}),
            "pts_lista": dict(d["pts_lista"]),
            "qtd_lista": dict(d["qtd_lista"]),
            "pts_membro": dict(d["pts_membro"]),
            "pen_membro": dict(d["pen_membro"]),
            "qtd_membro": dict(d.get("qtd_membro", {})),
            "pen_cards": d["pen_cards"],
            "pct_retrab": pct_retrab,   # None se sem dados
            "total_concl": total_concl,
            "pct_com_membro": pct_com_membro_m,
            "desc_com_membro": _desc_com_membro,
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
                "desc_com_membro": "Sem dados no período",
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


def _ref_execucao_equipe(dados, cfg):
    """Tempo de referência da equipe: o digitado no mês, ou o estimado.

    A referência era só calculada — os tempos estimados por coluna ponderados
    pelo volume — e não havia onde digitar o tempo médio geral do mês nem
    corrigi-lo. Agora há o campo `exec_ref_equipe`, e zero continua significando
    "usar o calculado", do mesmo jeito que a referência de cada pessoa.

    Devolve (referencia_min, n_cartoes, digitada).
    """
    ref, n_est = _tempo_estimado_esperado(dados)
    try:
        digitada = float((cfg or {}).get("exec_ref_equipe", 0) or 0)
    except (TypeError, ValueError):
        digitada = 0.0
    if digitada > 0:
        return digitada, n_est, True
    return ref, n_est, False


def _barra_tempo_medio(dados, cfg, cor_ok):
    """Barra do tempo médio de execução da equipe contra o alvo do mês.

    A linha fica no card mesmo sem alvo configurado. Sumir era o problema: o
    tempo médio pesa na meta coletiva, mas quem olhava o card não tinha como
    saber que esse indicador existia — nem que faltava dizer qual é o alvo.
    """
    ref, n_est, _digitada = _ref_execucao_equipe(dados, cfg)
    real = _media_execucao_geral(dados)
    meta = mc.meta_execucao(cfg, "equipe", ref or 0)
    alvo = meta["alvo"]
    if not meta["definida"] or not alvo:
        return _barra_painel_dash(
            "Tempo médio de execução",
            (f"{_fmt_hm(real)} de média real hoje · " if real is not None else "")
            + "sem alvo definido para o mês — defina em Configuração de Metas")
    rotulo = f"Tempo médio de execução até {_fmt_hm(alvo)}"
    if ref is None or real is None:
        return _barra_painel(rotulo, 0,
                             "Sem cartões com tempo medido no período", "#4A90D9")
    pct = 100 if real <= alvo else (alvo / real * 100 if real else 0)
    cor = cor_ok if real <= alvo else ("#EDA100" if real <= ref else "#E34948")
    # Alvo acima da referencia nao e "-16% abaixo": e uma folga em relacao a
    # base, e assim que ele precisa ser lido.
    _r = meta["red"]
    _rel = (f"{_r:.0f}% abaixo de" if _r >= 0.5 else
            ("no mesmo patamar de" if _r > -0.5 else f"{-_r:.0f}% acima de"))
    _base_txt = "digitadas" if _digitada else f"estimadas · {n_est} cartões"
    return _barra_painel(
        rotulo, pct,
        f"{_fmt_hm(real)} de média real · alvo {_fmt_hm(alvo)} "
        f"({_rel} {_fmt_hm(ref)} {_base_txt})",
        cor)


def _penalidades_por_atraso(dados, cfg):
    """Penalidades geradas por atraso alem do limite, somando a equipe.

    Cada pessoa que passar dos atrasos permitidos gera uma penalidade por atraso
    excedente. Conta a ocorrencia; a perda de pontos continua vindo so do
    lancamento no Trello.

    `dados` tem que trazer UM mes. O limite e mensal, entao receber um periodo
    inteiro aqui compara a soma de varios meses com o teto de um so.
    """
    limite = int((cfg or {}).get("max_atr_normal", 10))
    if limite <= 0:
        return 0
    try:
        users = list(_pc.MEMBROS_ATIVOS.keys())
        atr = (_ponto_por_membro(dados, users) or {}).get("atr_mb") or {}
    except Exception:
        return 0
    return sum(max(0, int(v) - limite) for v in atr.values())


def _metas_topicos(dados):
    """Os seis topicos da meta, ja em porcentagem, para Coletiva e MAXX.

    Fonte unica: as barras do painel e os velocimetros liam as mesmas coisas de
    lugares diferentes — o velocimetro de "Pontualidade" usava atrasados sobre o
    board inteiro enquanto a barra usava so os prioritarios P8-P10, e os dois
    apareciam na mesma tela dizendo coisas diferentes.

    Devolve (referencia, [topico, ...]), cada topico com pct/cor/descricao para
    as duas metas. `pct` pode passar de 100 na pontuacao: bater 120% da meta e
    informacao, e cortar em 100 esconderia.
    """
    if not dados:
        return None, []
    r = dados[-1]
    cfg = r["cfg"]

    max_pen_n = int(cfg.get("max_pen_normal", 4))
    max_pen_x = int(cfg.get("max_pen_maxx", 1))
    max_retrab_n = int(cfg.get("max_retrab_normal", 10))
    max_retrab_x = int(cfg.get("max_retrab_maxx", 5))
    pen_qtd = r["pen_qtd"]

    # 1. Pontuacao
    t_pts = {
        "chave": "pontuacao", "rotulo": "Pontuação do mês",
        "pct_n": r["pct_mensal"], "pct_x": r["pct_maxx"],
        "sub_n": f'{r["saldo"]:,.0f} / {r["meta_eq"]:,.0f} pts'.replace(",", "."),
        "sub_x": f'{r["saldo"]:,.0f} / {r["meta_maxx"]:,.0f} pts'.replace(",", "."),
    }

    # 2. Prioritarios atrasados — a meta e sobre P8-P10, nao sobre o board todo
    atr_pri = r.get("atrasados_pri", 0)
    pct_pri = 100 if atr_pri == 0 else max(0, 100 - atr_pri * 20)
    t_pri = {
        "chave": "prioritarios", "rotulo": "Sem atraso em prioritários",
        "pct_n": pct_pri, "pct_x": pct_pri,
        "sub_n": ("Nenhum P8-P10 atrasado" if atr_pri == 0
                  else f"{atr_pri} prioritário(s) atrasado(s)"),
    }
    t_pri["sub_x"] = t_pri["sub_n"]

    # 3. Retrabalho
    pct_retrab = r.get("pct_retrab")
    if pct_retrab is None:
        t_ret = {"chave": "retrabalho", "rotulo": "Retrabalho",
                 "pct_n": 0, "pct_x": 0,
                 "sub_n": "Sem conclusões no período",
                 "sub_x": "Sem conclusões no período"}
    else:
        # Como as penalidades: o arco sobe com o retrabalho e a cor julga. Verde
        # ate metade do limite, amarelo dai ate 90% dele, vermelho passando
        # disso — com o limite em 10%, da exatamente verde ate 5, amarelo ate 9
        # e vermelho de 10 em diante. Escrito em fracao do limite, a mesma regra
        # vale para a MAXX, que permite 5%.
        # Verde ate metade do limite, amarelo dai ate o limite, vermelho acima
        # dele. Em fracao do limite a mesma regra serve a MAXX, que permite 5%.
        #
        # Verde e nao azul: zero retrabalho e o melhor resultado possivel, e
        # nesta tela verde e o que quer dizer "esta bom". Azul aqui destoava dos
        # outros cinco mostradores, onde ele e a cor do neutro.
        def _ret(limite):
            if limite <= 0:
                return 0.0, "#1BAF7A"
            pct = min(pct_retrab / limite * 100, 100)
            cor = ("#1BAF7A" if pct_retrab <= limite * 0.5
                   else "#EDA100" if pct_retrab <= limite else "#E34948")
            return pct, cor

        _rn, _crn = _ret(max_retrab_n)
        _rx, _crx = _ret(max_retrab_x)
        # O numero no centro e o retrabalho de verdade, nao a fracao do limite:
        # 7% de retrabalho e a informacao, "70% do teto" e a leitura do arco.
        _v_ret = f"{pct_retrab:.1f}%".replace(".0%", "%")
        t_ret = {
            "chave": "retrabalho", "rotulo": "Retrabalho",
            "pct_n": _rn, "pct_x": _rx, "cor_n": _crn, "cor_x": _crx,
            "valor_n": _v_ret, "valor_x": _v_ret,
            "sub_n": f"máx {max_retrab_n}%", "sub_x": f"máx {max_retrab_x}%",
        }

    # 4. Penalidades — este enche com as penalidades, ao contrario dos outros
    # cinco. Quem separa o bom do ruim aqui e a cor, nao a altura: verde ate
    # metade do limite, amarelo da metade ate o limite, vermelho quando estoura.
    # Por isso ele nao precisa andar no mesmo sentido dos demais, e assim
    # continua igual a barra do painel de metas, que sempre enche desse jeito.
    def _pen(qtd, limite):
        pct = min(qtd / limite * 100, 100) if limite > 0 else (0 if qtd == 0 else 100)
        if limite > 0 and qtd > limite:
            cor = "#E34948"          # estourou
        elif pct >= 50:
            cor = "#EDA100"          # a meio caminho de estourar
        else:
            cor = "#1BAF7A"
        return pct, cor

    # Atraso alem do permitido vira penalidade, somando as da coluna
    # PENALIDADES do Trello. Conta a OCORRENCIA, nao desconta ponto: tirar
    # pontuacao e decisao de outra ordem, e o lancamento no Trello continua
    # sendo o unico caminho para isso.
    # SO o mes de referencia. Passar `dados` inteiro somava os atrasos de todos
    # os meses do filtro coletivo e comparava esse total com um limite MENSAL:
    # com quatro meses na tela, quem tivesse dois atrasos por mes aparecia
    # estourando o limite sozinho. Os outros cinco topicos sempre olharam so
    # dados[-1]; este tinha que olhar tambem.
    _pen_atr = _penalidades_por_atraso([r], cfg)
    pen_qtd += _pen_atr
    _origem_pen = f" · {_pen_atr} por atraso" if _pen_atr else ""

    _pn, _cn = _pen(pen_qtd, max_pen_n)
    _px, _cx = _pen(pen_qtd, max_pen_x)
    t_pen = {
        "chave": "penalidades", "rotulo": "Penalidades",
        "pct_n": _pn, "pct_x": _px, "cor_n": _cn, "cor_x": _cx,
        "valor_n": f"{pen_qtd:.0f}", "valor_x": f"{pen_qtd:.0f}",
        "sub_n": f"de {max_pen_n} permitidas" + _origem_pen,
        "sub_x": f"de {max_pen_x} permitidas" + _origem_pen,
    }

    # 5. Cartoes com membro
    pcm = r.get("pct_com_membro", 100.0)
    t_mb = {"chave": "membro", "rotulo": "Cartões com membro",
            "pct_n": pcm, "pct_x": pcm,
            "sub_n": "Em andamento e concluídos",
            "sub_x": "Em andamento e concluídos"}

    # 6. Tempo medio de execucao. Mes sem reducao definida vale 100%: a meta nao
    # existia ali, e mostrar 0 acusaria a equipe por uma regra que so passou a
    # valer depois.
    ref, n_est, _ref_digitada = _ref_execucao_equipe(dados, cfg)
    real = _media_execucao_geral(dados)
    _meta_t = mc.meta_execucao(cfg, "equipe", ref or 0)
    alvo = _meta_t["alvo"]
    if not _meta_t["definida"] or not alvo:
        t_tmp = {"chave": "tempo", "rotulo": "Tempo médio de execução",
                 "pct_n": 100.0, "pct_x": 100.0,
                 "sub_n": "sem alvo definido neste mês",
                 "sub_x": "sem alvo definido neste mês"}
    elif ref is None or real is None:
        t_tmp = {"chave": "tempo", "rotulo": "Tempo médio de execução",
                 "pct_n": 100.0, "pct_x": 100.0,
                 "sub_n": "sem cartão com tempo medido",
                 "sub_x": "sem cartão com tempo medido"}
    else:
        pct = 100.0 if real <= alvo else (alvo / real * 100 if real else 0.0)
        t_tmp = {"chave": "tempo", "rotulo": f"Tempo médio até {_fmt_hm(alvo)}",
                 "pct_n": pct, "pct_x": pct,
                 "sub_n": f"{_fmt_hm(real)} real · alvo {_fmt_hm(alvo)}",
                 "sub_x": f"{_fmt_hm(real)} real · alvo {_fmt_hm(alvo)}"}

    return r, [t_pts, t_pri, t_ret, t_pen, t_mb, t_tmp]


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

    # A meta e sobre prioridade 8 a 10; "atrasados" conta o board inteiro.
    atrasados_pri = r.get("atrasados_pri", 0)
    pct_prioritarios = 100 if atrasados_pri == 0 else max(0, 100 - atrasados_pri * 20)
    if atrasados_pri == 0:
        _desc_pri = "Nenhum cartão prioritário (P8-P10) atrasado"
    else:
        _nomes = ", ".join(f'"{c["nome"][:30]}"'
                           for c in (r.get("atrasados_pri_lista") or [])[:3])
        _desc_pri = (f"{atrasados_pri} prioritário(s) atrasado(s)"
                     + (f": {_nomes}" if _nomes else ""))
    pct_com_membro   = r.get("pct_com_membro", 100.0)
    _desc_cmb = r.get("desc_com_membro") or "Em andamento e concluídos no período"

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
                            _desc_pri, _cor_pri_a)
        _cor_rtn_a = "#1BAF7A" if pct_retrab_n >= 100 else "#E34948"
        b += _barra_painel(f"Retrabalho abaixo de {max_retrab_n}%", pct_retrab_n, desc_retrab, _cor_rtn_a)
        b += _barra_painel(f"Menos de {max_pen_n+1} penalidades", pct_pen_n,
                            f"{pen_qtd} ocorrência(s) / máx {max_pen_n}", "#E34948")
        _cor_cmb_a = "#1BAF7A" if pct_com_membro >= 100 else "#E34948"
        b += _barra_painel("Cartões com membro atribuído", pct_com_membro,
                            _desc_cmb, _cor_cmb_a)
        b += _barra_tempo_medio(dados, cfg, "#1BAF7A")
        st.markdown(f'<div style="background:var(--ms-metric-bg);border:1px solid #1BAF7A22;border-radius:8px;padding:12px 14px;">{b}</div>', unsafe_allow_html=True)

    with col_x:
        b = f'<div style="font-size:10px;font-weight:600;color:#FFD700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px;">⭐ Meta Maxx Coletiva</div>'
        b += _barra_painel(f"Pontuação +{maxx_pct-100}% acima da meta", pct_maxx,
                            f"{saldo:,.0f} / {meta_maxx:,.0f} pts (c/ penalidades -{pen_total:.0f})", "#FFD700")
        _cor_prix_a = "#FFD700" if pct_prioritarios >= 100 else "#E34948"
        b += _barra_painel("Zero prioritários em atraso", pct_prioritarios,
                            _desc_pri, _cor_prix_a)
        _cor_rtx_a = "#FFD700" if pct_retrab_x >= 100 else "#E34948"
        b += _barra_painel(f"Retrabalho abaixo de {max_retrab_x}%", pct_retrab_x, desc_retrab_x, _cor_rtx_a)
        b += _barra_painel(f"Menos de {max_pen_x+1} penalidades", pct_pen_x,
                            f"{pen_qtd} ocorrência(s) / máx {max_pen_x}", "#E34948")
        _cor_cmbx_a = "#FFD700" if pct_com_membro >= 100 else "#E34948"
        b += _barra_painel("Cartões com membro atribuído", pct_com_membro,
                            _desc_cmb, _cor_cmbx_a)
        # O tempo medio ja entrava nas duas contas (`_metas_do_mes` da o mesmo
        # pct para Normal e MAXX); so nao aparecia deste lado do card.
        b += _barra_tempo_medio(dados, cfg, "#FFD700")
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

def _fmt_hm(minutos):
    """Minutos como 15h24 — a unidade em que a equipe pensa o mes."""
    m = int(round(abs(minutos)))
    return f"{m // 60}h{m % 60:02d}"


def _media_execucao_por_membro(dados):
    """Média de execução medida pelo Trello, em minutos, por username.

    Mesma fonte da tela "Tempo por Colaborador": os trechos com a etiqueta
    EM ANDAMENTO, já descontadas as pausas. Quem não tem cartão medido fica
    FORA do dicionário — ausência de medição não é média zero, e tratar as duas
    igual poria a pessoa como a mais rápida da equipe.
    """
    tempos = {}
    for r in dados:
        for u, por_col in (r.get("tempo_membro_lista") or {}).items():
            for ts in por_col.values():
                tempos.setdefault(u, []).extend(ts)
    return {u: sum(v) / len(v) for u, v in tempos.items() if v}


def _min_em_cartoes(dados, ym=None):
    """{username: minutos em cartões} — reserva da ociosidade.

    Soma o tempo de execução COM a busca de demanda. São contas diferentes de
    propósito: para a meta de tempo médio a busca fica de fora, porque não é
    execução de demanda; para a ociosidade ela entra, porque a pessoa estava
    trabalhando — contá-la como tempo parado acusaria quem passou a manhã
    procurando serviço.
    """
    por = {}
    for r in dados:
        if ym is not None and r.get("filtro_mes") != ym:
            continue
        for chave in ("tempo_membro_lista", "analise_membro_lista"):
            for u, por_col in (r.get(chave) or {}).items():
                por[u] = por.get(u, 0.0) + sum(
                    t for ts in por_col.values() for t in ts)
    return por


def _media_execucao_geral(dados):
    """Média de execução de TODAS as demandas medidas no período, em minutos.

    Cartão a cartão, não média das médias por coluna: uma coluna com dois
    cartões pesaria igual a outra com oitenta.
    """
    todos = [t for r in dados
             for ts in (r.get("tempo_lista") or {}).values()
             for t in ts]
    return (sum(todos) / len(todos)) if todos else None


def _tempo_estimado_esperado(dados):
    """Tempo médio ESPERADO por demanda, em minutos, e quantos cartões o sustentam.

    Sai dos tempos estimados que o gestor definiu por coluna, ponderados pelo
    volume real de cartões concluídos em cada uma. Média simples das colunas não
    serve: uma coluna com dois cartões pesaria igual a outra com oitenta.

    É a referência do indicador coletivo — e é dela, comparada com o tempo
    medido, que se descobre quais estimativas foram chute alto ou baixo.
    """
    soma = 0.0
    qtd = 0
    for r in dados:
        for nl, tempos in (r.get("tempo_lista") or {}).items():
            est = _pc.cfg_coluna(nl).get("tempo_min") or 0
            if est <= 0:
                continue
            soma += est * len(tempos)
            qtd += len(tempos)
    return ((soma / qtd) if qtd else None), qtd


def _esc(texto):
    """Escapa texto que veio de fora para entrar em HTML ou SVG.

    Nome de cartao e escrito no Trello por quem cria a demanda: um "&" ou um
    "<" no titulo quebrava a marcacao a partir dali, e a tela perdia o resto do
    bloco sem dizer por que.
    """
    return (str(texto or "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _meta_ind_item(titulo, pct, descricao, cor=None, aguardando=False,
                   valor_texto=None):
    """Card de item de meta individual (inline styles, sem depender do CSS do placar)."""
    _card_css = (
        'background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);'
        'border-radius:10px;padding:14px 16px;margin-bottom:8px;'
    )
    _titulo_css = 'font-size:12px;font-weight:600;color:var(--ms-texto);margin-bottom:6px;'
    _barra_bg   = 'background:var(--ms-metric-bd);border-radius:4px;height:8px;overflow:hidden;margin-bottom:3px;'
    if aguardando:
        # A frase fixa dizia "relógio de ponto" mesmo quando o motivo era outro —
        # por exemplo, nenhum cartão concluído com tempo medido no período.
        _motivo = descricao or "Aguardando integração do relógio de ponto"
        return (f'<div style="{_card_css}">'
                f'<div style="{_titulo_css}">{titulo}</div>'
                f'<div style="font-size:10px;color:var(--ms-texto-sec);font-style:italic;">'
                f'⏳ {_motivo}</div></div>')
    c = cor or ("#1BAF7A" if pct >= 80 else ("#EDA100" if pct >= 50 else "#4A90D9"))
    # valor_texto: o numero REAL do indicador, quando ele nao e "quanto da meta
    # foi cumprido". Ociosidade de 40% e de 90% davam as duas 0% de meta
    # cumprida e pareciam "sem dado" — o numero de verdade sumia.
    _valor = valor_texto if valor_texto is not None else f"{pct:.0f}%"
    return (f'<div style="{_card_css}">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">'
            f'<div style="{_titulo_css}margin:0;">{titulo}</div>'
            f'<div style="font-size:16px;font-weight:700;color:{c};">{_valor}</div></div>'
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

    # Fechado por padrao. Aberto, ele despeja a lista de campos crus da RHiD e a
    # contagem de acoes do Trello no meio da Analise de Metas — util para achar
    # a causa, mas nao e o que se vai ver na tela todo dia. O titulo ja diz que a
    # explicacao esta ali; quem precisar, abre.
    with st.expander(f"🔎 Por que {' e '.join(faltando)} não preencheu", expanded=False):
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
                if d.get("campo_batidas"):
                    st.caption(f"Batidas lidas do campo **{d['campo_batidas']}**.")
                if d.get("erro"):
                    st.warning(d["erro"])
                if d.get("campos_com_hora"):
                    st.caption(
                        f"Campos da RHiD que contêm horário (dia {d.get('data_amostra','?')}) "
                        "— é daqui que saem entrada e volta do almoço:"
                    )
                    st.code("\n".join(d["campos_com_hora"]))
                if d.get("todos_os_campos"):
                    st.caption("Todos os campos do dia, com o tipo:")
                    st.code("\n".join(d["todos_os_campos"]))
                if not d.get("campos_com_hora") and d.get("chaves_exemplo"):
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

            _dt = getattr(_pc, "ULTIMO_DIAGNOSTICO_TEMPOS", {})
            if _dt:
                st.markdown(
                    f"- {_dt.get('cards',0)} cartão(ões) no board · "
                    f"**{_dt.get('com_acoes',0)}** com histórico · "
                    f"**{_dt.get('com_trecho',0)}** com trecho de trabalho · "
                    f"**{_dt.get('com_tempo_util',0)}** com tempo dentro do expediente · "
                    f"**{_dt.get('com_membro',0)}** atribuídos a alguém"
                )
                # O histograma de tipos vem SEMPRE, inclusive (e principalmente)
                # quando nenhuma etiqueta aparece: e ele que diz se o Trello
                # devolveu addLabelToCard ou so outra coisa.
                _tp = _dt.get("tipos_vistos") or {}
                if _tp:
                    st.caption("Tipos de ação recebidos do Trello (tipo · vezes):")
                    st.code("\n".join(
                        f"{n}  ·  {q}" for n, q in
                        sorted(_tp.items(), key=lambda x: -x[1])[:10]
                    ))
                _al = _dt.get("alinhamento_old") or {}
                if _al:
                    st.caption(
                        f"Leitura do campo `old.idLabels`: **{_al.get('modo','?')}** "
                        f"(em {_al.get('iguais',0)} cartão(ões) o último registro "
                        f"bate com as etiquetas atuais, em {_al.get('diferentes',0)} não)")
                _et = _dt.get("etiquetas_vistas") or {}
                if _et:
                    st.caption("Etiquetas vistas no histórico (nome exato · vezes):")
                    st.code("\n".join(
                        f"{n}  ·  {q}" for n, q in
                        sorted(_et.items(), key=lambda x: -x[1])[:15]
                    ))
                else:
                    st.caption("Nenhuma ação de etiqueta chegou no histórico — "
                               "é por isso que o tempo de execução está zerado.")
                if d.get("plano_b"):
                    st.caption(
                        f"Busca sem filtro: {d.get('plano_b_acoes',0)} ação(ões) lidas · "
                        f"{d.get('plano_b_etiquetas',0)} de etiqueta em "
                        f"{d.get('plano_b_cartoes',0)} cartão(ões)."
                    )
                    _tb = d.get("plano_b_tipos") or {}
                    if _tb:
                        st.caption("Tipos na leitura crua do board (tipo · vezes):")
                        st.code("\n".join(
                            f"{n}  ·  {q}" for n, q in
                            sorted(_tb.items(), key=lambda x: -x[1])[:15]))
                    _am = getattr(_pc, "AMOSTRA_ACAO_ETIQUETA", {}) or {}
                    st.caption(
                        f"Etiquetas cadastradas no board (id → nome): "
                        f"**{_am.get('mapa_labels', 0)}**")
                    if _am.get("acao"):
                        import json as _json
                        st.caption("Uma ação de troca de etiqueta, exatamente "
                                   "como o Trello mandou:")
                        st.code(_json.dumps(_am["acao"], indent=2,
                                            ensure_ascii=False)[:1800])
                    if d.get("plano_b_truncado"):
                        st.warning(
                            "O histórico do período é maior do que coube na leitura — "
                            "há etiquetas antigas que não foram lidas, e o tempo "
                            "medido nos meses mais antigos fica incompleto."
                        )


# ── Seção: meta individual por colaborador ────────────────────────────────────

# Limites dos indicadores individuais. A ociosidade da MAXX e 5% (a mensal e
# 10%); o percentual de cartoes dentro do tempo estimado nao tinha alvo definido,
# entao ficam 80% no mensal e 90% na MAXX — mudar aqui muda os dois cards.
# Uma fonte so: os mesmos numeros que o painel de explicacao mostra.
OCIO_META_NORMAL = _expl.OCIO_META_NORMAL
OCIO_META_MAXX   = _expl.OCIO_META_MAXX
EXEC_META_NORMAL = _expl.EXEC_META_NORMAL
EXEC_META_MAXX   = _expl.EXEC_META_MAXX


def _titulo_grupo_meta(texto, cor):
    return (f'<div style="margin:14px 0 6px 0;padding-left:8px;'
            f'border-left:3px solid {cor};font-size:12px;font-weight:700;'
            f'letter-spacing:.5px;text-transform:uppercase;color:{cor};">'
            f'{texto}</div>')


_ROTULO_OCORRENCIA = {
    "tolerancia":     ("🕐", "Tolerância", "#8E7CC3"),
    "atraso_entrada": ("⏰", "Atraso", "#E34948"),
    "atraso_almoco":  ("⏰", "Atraso", "#E34948"),
}


def _detalhe_pontualidade(ocorrencias, username):
    """Lista dia a dia o que gerou cada tolerância e cada atraso.

    Os numeros de tolerancia e atraso nao tinham como ser conferidos: a tela
    mostrava so o total, e a pessoa precisava abrir a apuracao da RHiD para
    entender de onde veio.
    """
    if not ocorrencias:
        # O expander fica, vazio. Aparecendo so para quem teve ocorrencia, ele
        # empurrava os cards seguintes e as colunas paravam de casar.
        with st.expander("📋 Ver os dias de tolerância e atraso (0)", expanded=False):
            st.caption("Nenhuma tolerância ou atraso no período.")
        return
    linhas = ""
    for oc in sorted(ocorrencias, key=lambda x: (x.get("data", ""),
                                                 x.get("horario", ""))):
        emoji, rotulo, cor = _ROTULO_OCORRENCIA.get(
            oc.get("tipo"), ("•", "Ocorrência", "var(--ms-texto-sec)"))
        mins = oc.get("minutos") or 0
        linhas += (
            f'<tr>'
            f'<td style="padding:6px 10px;font-size:12px;white-space:nowrap;">'
            f'{oc.get("data","—")}</td>'
            f'<td style="padding:6px 10px;font-size:12px;">'
            f'{oc.get("evento","—")}</td>'
            f'<td style="padding:6px 10px;font-size:12px;'
            f'color:var(--ms-texto-sec);white-space:nowrap;">'
            f'previsto {oc.get("esperado","—")}</td>'
            f'<td style="padding:6px 10px;font-size:12px;font-weight:700;'
            f'white-space:nowrap;">{oc.get("horario","—")}</td>'
            f'<td style="padding:6px 10px;font-size:12px;color:{cor};'
            f'white-space:nowrap;">{emoji} {rotulo}</td>'
            f'<td style="padding:6px 10px;font-size:12px;'
            f'color:var(--ms-texto-sec);text-align:right;white-space:nowrap;">'
            f'{mins:.0f} min</td></tr>')

    with st.expander(f"🗓️ Ver os dias de tolerância e atraso "
                     f"({len(ocorrencias)})", expanded=False):
        st.markdown(
            '<div style="overflow-x:auto;"><table style="width:100%;'
            'border-collapse:collapse;">'
            '<thead><tr style="background:var(--ms-metric-bg);">'
            '<th style="padding:7px 10px;font-size:10px;text-align:left;'
            'text-transform:uppercase;color:var(--ms-texto-sec);">Dia</th>'
            '<th style="padding:7px 10px;font-size:10px;text-align:left;'
            'text-transform:uppercase;color:var(--ms-texto-sec);">Evento</th>'
            '<th style="padding:7px 10px;font-size:10px;text-align:left;'
            'text-transform:uppercase;color:var(--ms-texto-sec);">Horário</th>'
            '<th style="padding:7px 10px;font-size:10px;text-align:left;'
            'text-transform:uppercase;color:var(--ms-texto-sec);">Bateu</th>'
            '<th style="padding:7px 10px;font-size:10px;text-align:left;'
            'text-transform:uppercase;color:var(--ms-texto-sec);">O quê</th>'
            '<th style="padding:7px 10px;font-size:10px;text-align:right;'
            'text-transform:uppercase;color:var(--ms-texto-sec);">Passou</th>'
            '</tr></thead><tbody>' + linhas + '</tbody></table></div>',
            unsafe_allow_html=True)


# A escada disciplinar, do jeito que ela e aplicada. Fica aqui, e nao espalhada
# no texto do card, porque e ela que decide a cor E o que a pessoa le: a
# terceira advertencia no mesmo mes e a que estoura a meta.
ESCADA_ADVERTENCIA = [
    ("1ª", "#1BAF7A", "advertência verbal"),
    ("2ª", "#EDA100", "um dia advertido em casa — perde a remuneração do dia "
                      "e do domingo, conforme a lei trabalhista"),
    ("3ª", "#E34948", "repete o dia em casa e perde o domingo"),
]
ADV_NEUTRO = "#8a8a8a"   # zero advertências: sem cor de alerta nenhuma


def _elegibilidade(dados, users):
    """Quem entrou na meta do time neste período, e por quê não, quando não.

    {username: {"pts","meta","pct","advs","lim_adv_n","lim_adv_x",
                "entra_col","entra_maxx","motivos_col","motivos_maxx"}}

    Bater a meta do time é do time; ENTRAR nela é de cada um. São dois
    porteiros: o piso de contribuição sobre a PRÓPRIA meta individual (80% para
    a coletiva, 100% para a MAXX) e o teto de advertências (2 e 1).

    Uma função só, porque a mesma conta decide três coisas: o que o card de cada
    pessoa mostra, quanto a calculadora de ganhos paga e quem aparece de fora no
    relatório. Três contas separadas para a mesma pergunta é como as telas
    passam a discordar entre si.
    """
    if not dados:
        return {}
    cfg = dados[-1]["cfg"]
    n_meses = max(1, len(dados))
    min_n = int(cfg.get("min_contrib_normal", 80) or 0)
    min_x = int(cfg.get("min_contrib_maxx", 100) or 0)
    lim_n = int(cfg.get("max_adv_normal", 2) or 0) * n_meses
    lim_x = int(cfg.get("max_adv_maxx", 1) or 0) * n_meses

    fora = {}
    for u in users:
        pts = sum(r["pts_membro"].get(u, 0) for r in dados)
        meta = sum(r["cfg"].get(f"meta_{u}", 1500) for r in dados)
        advs = sum(int(r["cfg"].get(f"adv_{u}", 0) or 0) for r in dados)
        pct = (pts / meta * 100) if meta > 0 else 0.0

        mot_col, mot_mx = [], []
        if pct < min_n:
            mot_col.append(f"{pct:.0f}% da meta individual (mín. {min_n}%)")
        if advs > lim_n:
            mot_col.append(f"{advs} advertência(s) (máx. {lim_n})")
        if pct < min_x:
            mot_mx.append(f"{pct:.0f}% da meta individual (mín. {min_x}%)")
        if advs > lim_x:
            mot_mx.append(f"{advs} advertência(s) (máx. {lim_x})")

        fora[u] = {
            "pts": pts, "meta": meta, "pct": pct, "advs": advs,
            "min_n": min_n, "min_x": min_x,
            "lim_adv_n": lim_n, "lim_adv_x": lim_x,
            "entra_col": not mot_col, "entra_maxx": not mot_mx,
            "motivos_col": mot_col, "motivos_maxx": mot_mx,
        }
    return fora


def _item_advertencia(advs, limite_mes, n_meses=1):
    """Card de advertências: a escada disciplinar, com o degrau atual aceso.

    A cor não vem do limite da meta, e sim da escada: a primeira é verbal e
    ainda é verde, a segunda já custa um dia e o domingo e fica amarela, a
    terceira estoura e fica vermelha. É a mesma escada nos dois grupos — a MAXX
    não tem uma escada própria, só um teto mais baixo, que continua valendo
    para dizer de qual meta a pessoa saiu.

    Advertência é lançamento do gestor, um número por mês na configuração — não
    sai do Trello nem da RHiD. Somada no período, tanto o teto quanto a escada
    acompanham os meses: a escada é sobre o MESMO mês, e comparar três meses
    com o degrau de um só acusaria quem está dentro da regra.
    """
    n_meses = max(1, n_meses)
    rotulo = f"🚫 Advertências (máx {limite_mes}/mês)"
    limite = limite_mes * n_meses
    degraus = len(ESCADA_ADVERTENCIA) * n_meses      # a 3ª é a que estoura
    pct = min(advs / degraus * 100, 100) if degraus else 0

    # Da quarta em diante o degrau continua sendo o terceiro: a escada acaba na
    # que estoura. Sem o teto aqui, quem tomasse a quarta caia fora da lista e
    # o card ficava sem degrau aceso nenhum.
    degrau = (min(int((advs - 1) // n_meses), len(ESCADA_ADVERTENCIA) - 1)
              if advs > 0 else None)
    if degrau is None:
        cor, atual = ADV_NEUTRO, "Nenhuma advertência no mês"
    else:
        _ord, cor, _txt = ESCADA_ADVERTENCIA[degrau]
        atual = f"<b>{_ord} — {_txt}</b>"

    # A escada inteira embaixo, com o degrau de agora aceso: quem tomou a
    # primeira precisa ver ali o que a segunda custa, sem perguntar a ninguem.
    passos = []
    for _i, (_ord, _c, _txt) in enumerate(ESCADA_ADVERTENCIA):
        _aceso = degrau == _i
        _cor_p = _c if _aceso else "var(--ms-texto-sec)"
        _peso = "700" if _aceso else "400"
        passos.append(f'<span style="color:{_cor_p};font-weight:{_peso};">'
                      f'{_ord} {_txt}</span>')
    escada = ' <span style="opacity:.5;">→</span> '.join(passos)

    if limite > 0 and advs > limite:
        fecho = f"fora desta meta — {advs - limite} além do permitido"
    elif limite <= 0:
        fecho = "fora desta meta" if advs else "nenhuma advertência permitida"
    else:
        fecho = f"{limite - advs} de folga até sair desta meta"
    corpo = f"{advs} de {limite} permitidas · {fecho}"
    if n_meses > 1:
        corpo += f" · {limite_mes}/mês em {n_meses} meses"
    corpo += (f'<div style="margin-top:5px;padding-top:5px;'
              f'border-top:1px solid var(--ms-divisor);line-height:1.7;">'
              f'{atual}<div style="margin-top:3px;font-size:8.5px;">'
              f'{escada}</div></div>')
    return _meta_ind_item(rotulo, pct, corpo, cor=cor, valor_texto=f"{advs:.0f}")


def _n_br(v):
    """1500 -> "1.500". O separador brasileiro sem o .replace(",", ".") do bloco
    inteiro, que já trocou vírgula de texto por ponto no meio de frase."""
    return f"{v:,.0f}".replace(",", ".")


def _dias_uteis_periodo(dados, hoje=None):
    """(dias_úteis, já_decorridos) somando os meses do período analisado.

    Mês corrente conta até hoje; mês fechado conta inteiro. Mês que ainda não
    começou fica de fora dos dois — contar dias que não existem faria o ritmo
    exigido parecer menor do que é.
    """
    hoje = hoje or datetime.now()
    uteis = dec = 0
    for r in dados or []:
        fm = r.get("filtro_mes")
        if not fm:
            continue
        ano, mes = int(fm[0]), int(fm[1])
        if (ano, mes) > (hoje.year, hoje.month):
            continue
        ate = hoje.day if (ano, mes) == (hoje.year, hoje.month) else None
        t, d = _pc.dias_uteis_do_mes(ano, mes, ate)
        uteis += t
        dec += d
    return uteis, dec


def _ritmo_entrada(pts, exigido, uteis, decorridos):
    """Ritmo diário contra o piso de entrada na meta, ou None sem base.

    A pergunta que o piso de 80% não responde sozinho: no dia 2 do mês, ter 8%
    da meta não é estar mal — é estar adiantado. O que dá para cobrar de alguém
    hoje é o pedaço do piso que os dias já corridos pedem, e é isso que vira a
    cor: abaixo do esperado vermelho, no esperado amarelo, acima verde — a mesma
    régua do velocímetro da Meta Mensal.
    """
    if uteis <= 0 or exigido <= 0:
        return None
    decorridos = max(0, min(decorridos, uteis))
    restantes = uteis - decorridos
    esperado = exigido / uteis * decorridos
    falta = max(exigido - pts, 0.0)
    pct = ((pts - esperado) / esperado * 100) if esperado > 0 else 0.0
    if decorridos <= 0:
        estado, cor = "inicio", ADV_NEUTRO
    elif pct > 10:
        estado, cor = "acima", "#1BAF7A"
    elif pct < -10:
        estado, cor = "abaixo", "#E34948"
    else:
        estado, cor = "dentro", "#EDA100"
    return {"uteis": uteis, "decorridos": decorridos, "restantes": restantes,
            "esperado": esperado, "falta": falta, "pct": pct,
            "por_dia_alvo": exigido / uteis,
            "por_dia_real": (pts / decorridos) if decorridos else 0.0,
            "por_dia_falta": (falta / restantes) if restantes else falta,
            "cor": cor, "estado": estado}


def _item_contribuicao(pts, meta, piso, ritmo=None):
    """Card do piso de participação: entregou o bastante para entrar na meta?

    Bater a meta do time é do time; ENTRAR nela é de cada um. Quem não chega a
    essa fatia da própria meta individual não participa da meta coletiva do mês,
    ainda que o time feche. Por isso o card aparece nos dois grupos, com o piso
    de cada um — 80% na coletiva, 100% na MAXX.

    A barra é a mesma da pontuação do mês: escala com folga acima do exigido, o
    mínimo vira um risco na trilha e o que passa dele é pintado de ouro. Travada
    no exigido, entregar o dobro e entregar o mínimo davam a mesma barra cheia.
    """
    rotulo = f"🤝 Participação na meta ({piso}% da meta individual)"
    if meta <= 0 or piso <= 0:
        return _meta_ind_item(rotulo, 100,
                              "Meta individual não configurada para o mês",
                              aguardando=True)
    pct_ind = pts / meta * 100
    exigido = meta * piso / 100
    # Verde entrou; amarelo a menos de 10% de entrar; vermelho abaixo disso —
    # os mesmos cortes da pontuação do mês.
    if pct_ind >= piso:
        cor, fecho = "#1BAF7A", "✅ Participa desta meta"
    elif ritmo and ritmo["restantes"] > 0 and ritmo["estado"] in ("acima", "dentro"):
        # No dia 2 do mês ninguém tem 80% da meta, e pintar isso de vermelho
        # dizia à pessoa que ela está fora quando ela está adiantada. Com o mês
        # correndo, quem manda é o ritmo — e o texto diz que ainda não entrou.
        cor = ritmo["cor"]
        fecho = f"ainda não — no ritmo · faltam {exigido - pts:,.0f} pts"
    elif pct_ind >= piso * 0.9:
        cor, fecho = "#EDA100", f"faltam {exigido - pts:,.0f} pts para entrar"
    else:
        cor, fecho = "#E34948", f"fora desta meta — faltam {exigido - pts:,.0f} pts"
    OURO = "#FFD700"
    escala = (max(pts, exigido) * 1.12) or 1
    sobra = max(0, pts - exigido)
    _x_min = exigido / escala * 100
    # Só faz sentido enquanto o período corre: com ele fechado, "hoje" é o
    # próprio mínimo e as duas marcas cairiam uma em cima da outra.
    _x_hoje = (ritmo["esperado"] / escala * 100
               if ritmo and ritmo["restantes"] > 0 and ritmo["decorridos"] > 0
               else None)

    barra = (
        f'<div style="height:14px;border-radius:7px;background:var(--ms-metric-bd);'
        f'margin:14px 0 5px;position:relative;">'
        f'<div style="position:absolute;left:0;top:0;height:100%;'
        f'width:{min(pts, exigido)/escala*100:.1f}%;background:{cor};'
        f'border-radius:7px {"0 0" if sobra > 0 else "7px 7px"} 7px;"></div>'
        + (f'<div style="position:absolute;top:0;height:100%;left:{_x_min:.1f}%;'
           f'width:{sobra/escala*100:.1f}%;background:{OURO};'
           f'border-radius:0 7px 7px 0;"></div>' if sobra > 0 else "")
        + f'<div style="position:absolute;top:-5px;bottom:-5px;left:{_x_min:.1f}%;'
        f'width:3px;margin-left:-1.5px;border-radius:2px;'
        f'background:var(--ms-texto);"></div>'
        # A marca de "hoje": o pedaço do mínimo que os dias já corridos pedem.
        # Sem ela a barra respondia "quanto falta" e não "estou no ritmo?", que
        # é a pergunta de quem olha isso no dia 2 do mês.
        + (f'<div style="position:absolute;top:-3px;bottom:-3px;'
           f'left:{_x_hoje:.1f}%;width:2px;margin-left:-1px;border-radius:2px;'
           f'background:var(--ms-texto-sec);opacity:.85;"></div>'
           if _x_hoje is not None else "")
        + '</div>'
        f'<div style="position:relative;height:12px;margin-bottom:3px;">'
        f'<span style="position:absolute;left:{_x_min:.1f}%;transform:translateX(-50%);'
        f'font-size:8px;font-weight:700;white-space:nowrap;color:var(--ms-texto);">'
        f'▲ mínimo</span>'
        + (f'<span style="position:absolute;left:{_x_hoje:.1f}%;'
           f'transform:translateX(-50%);font-size:8px;white-space:nowrap;'
           f'color:var(--ms-texto-sec);">▲ hoje</span>'
           if _x_hoje is not None else "")
        + (f'<span style="position:absolute;right:0;font-size:8px;font-weight:700;'
           f'color:{OURO};">+{sobra:,.0f} pts acima</span>' if sobra > 0 else "")
        + '</div>'
    )
    _card_css = ('background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);'
                 'border-radius:10px;padding:14px 16px;margin-bottom:8px;')
    return (
        f'<div style="{_card_css}">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
        f'<div style="font-size:12px;font-weight:600;color:var(--ms-texto);">{rotulo}</div>'
        f'<div style="font-size:16px;font-weight:700;color:{cor};">{pct_ind:.0f}%</div>'
        f'</div>{barra}'
        f'<div style="display:flex;justify-content:space-between;gap:8px;'
        f'font-size:9px;color:var(--ms-texto-sec);">'
        f'<span>mínimo <b style="color:var(--ms-texto);">{exigido:,.0f}</b> de '
        f'{meta:,.0f} pts</span>'
        f'<span style="color:{cor};font-weight:600;">{fecho}</span></div>'
        + _rodape_ritmo(ritmo, pts) + '</div>'
    ).replace(",", ".")


def _rodape_ritmo(ritmo, pts):
    """As três linhas do ritmo diário embaixo do card de participação.

    Quanto o piso pede por dia útil, quanto a pessoa vem fazendo por dia, e o
    que sobra dividido pelos dias que ainda existem. É a conta que ela faria na
    mão para saber se dá — feita aqui, com os feriados já descontados.
    """
    if not ritmo or ritmo["decorridos"] <= 0:
        return ""
    _cor_r = ritmo["cor"]
    _dif = pts - ritmo["esperado"]
    if ritmo["estado"] == "acima":
        _diag = f"{_dif:,.0f} pts ADIANTADO"
    elif ritmo["estado"] == "dentro":
        _diag = "no ritmo esperado"
    else:
        _diag = f"{-_dif:,.0f} pts atrás do ritmo"
    if ritmo["falta"] <= 0:
        _fecho_r = "mínimo já garantido"
    elif ritmo["restantes"] > 0:
        _fecho_r = (f"faltam {ritmo['falta']:,.0f} pts em "
                    f"{ritmo['restantes']} dia(s) útil(eis) = "
                    f"<b style=\'color:var(--ms-texto);\'>"
                    f"{ritmo['por_dia_falta']:,.0f} pts/dia</b>")
    else:
        _fecho_r = f"faltaram {ritmo['falta']:,.0f} pts"
    return (
        f'<div style="margin-top:7px;padding-top:6px;border-top:1px solid '
        f'var(--ms-divisor);font-size:9px;color:var(--ms-texto-sec);'
        f'line-height:1.75;">'
        f'<div>ritmo necessário <b style="color:var(--ms-texto);">'
        f'{ritmo["por_dia_alvo"]:,.0f} pts/dia útil</b> · seu ritmo '
        f'<b style="color:{_cor_r};">{ritmo["por_dia_real"]:,.0f} pts/dia</b> '
        f'· <span style="color:{_cor_r};font-weight:600;">{_diag}</span></div>'
        f'<div>esperado até hoje <b style="color:var(--ms-texto);">'
        f'{ritmo["esperado"]:,.0f} pts</b> em {ritmo["decorridos"]} de '
        f'{ritmo["uteis"]} dias úteis · você tem '
        f'<b style="color:var(--ms-texto);">{pts:,.0f}</b></div>'
        f'<div>{_fecho_r}</div></div>'
    )


def _secao_meta_individual(dados, membros_ativos, usuario_logado=None, eh_master=False):
    """Exibe cards de meta individual — pontuação real + campos aguardando integração.
    Penalidades ficam apenas na visão coletiva."""
    if not dados:
        return

    # Usa o mês mais recente para pct_eq/pct_maxx (salário) e para os limites de pontualidade
    r_atual = dados[-1]
    pct_eq   = r_atual["pct_mensal"]
    pct_maxx = r_atual["pct_maxx"]
    # Em pontos, e nao so em percentual: a calculadora precisa dizer QUANTO
    # falta, e "faltam 8%" nao e uma quantidade de trabalho.
    _saldo_eq  = r_atual.get("saldo", 0.0)
    _meta_eq   = r_atual.get("meta_eq", 0.0)
    _meta_maxx = r_atual.get("meta_maxx", 0.0)
    cfg      = r_atual["cfg"]
    max_tol  = int(cfg.get("max_tol_normal", 15))
    max_atr  = int(cfg.get("max_atr_normal", 10))
    # A MAXX tem limites proprios, mais apertados. Estavam configurados e nunca
    # apareciam no painel individual — so os limites normais eram mostrados.
    max_tol_mx = int(cfg.get("max_tol_maxx", 7))
    max_atr_mx = int(cfg.get("max_atr_maxx", 5))
    # Entrada na meta: o piso de contribuicao e o teto de advertencias. Os dois
    # sao cobrados sobre a meta INDIVIDUAL de cada um — 80% dela para entrar na
    # coletiva, 100% para entrar na MAXX.
    _min_contrib_n = int(cfg.get("min_contrib_normal", 80) or 0)
    _min_contrib_x = int(cfg.get("min_contrib_maxx", 100) or 0)
    _max_adv_n = int(cfg.get("max_adv_normal", 2) or 0)
    _max_adv_x = int(cfg.get("max_adv_maxx", 1) or 0)

    # Tempo médio de execução: a referência e a redução são do mês mais recente
    # do período, a mesma origem dos limites de pontualidade logo acima.
    _cfg_mes = cfg
    _medias_exec = _media_execucao_por_membro(dados)

    # Agrega pontos do período completo (sem penalidades — penalidades são coletivas)
    pts_total  = {u: sum(r["pts_membro"].get(u, 0) for r in dados) for u in membros_ativos}
    meta_total = {u: sum(r["cfg"].get(f"meta_{u}", 1500) for r in dados) for u in membros_ativos}

    # Meta MAXX individual. Quando nao ha valor proprio, usa a mesma porcentagem
    # da MAXX coletiva sobre a meta individual — que era o que ja acontecia na
    # pratica, so que sem nunca aparecer na tela.
    def _maxx_do_mes(r, u):
        proprio = r["cfg"].get(f"meta_maxx_{u}") or 0
        if proprio:
            return proprio
        pct = r["cfg"].get("meta_maxx_pct", 110)
        return r["cfg"].get(f"meta_{u}", 1500) * pct / 100

    maxx_total = {u: sum(_maxx_do_mes(r, u) for r in dados) for u in membros_ativos}

    # A explicacao fica DENTRO do card de cada colaborador — e a tela individual
    # dele. O master ve todos os cards lado a lado, em colunas estreitas onde a
    # tabela nao caberia, entao para ele vai uma copia so, aqui em cima.
    if eh_master:
        _expl.render(min_contrib_n=_min_contrib_n, min_contrib_x=_min_contrib_x,
                     max_adv_n=_max_adv_n, max_adv_x=_max_adv_x)

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
    _pont = {u: {"tol": 0, "tol_ent": 0, "tol_alm": 0,
                 "atr": 0, "atr_ent": 0, "atr_alm": 0, "dias": 0,
                 "ocorr": [], "min_atr": 0.0, "banco": 0.0}
             for u in membros_ativos}
    _ocio = {u: {"disp": 0.0, "cards": 0.0, "ocio": 0.0} for u in membros_ativos}
    _tem_ponto = False
    _diags_pont = []
    _erro_pont = None
    try:
        for r in dados:
            ym = r.get("filtro_mes")
            if not ym:
                continue
            tc_mes = _min_em_cartoes([r])
            p_mes, _diag_pont = _rp.get_pontualidade_mes(*ym, com_diagnostico=True)
            _diags_pont.append((ym, _diag_pont))
            _iv_mes = {}
            for _r in dados:
                if _r.get("filtro_mes") == ym:
                    _iv_mes.update(_r.get("intervalos_membro") or {})
            o_mes = _rp.get_ociosidade_mes(ym[0], ym[1], tc_mes, _iv_mes)
            for u in membros_ativos:
                p = p_mes.get(u)
                if p:
                    _pont[u]["tol"]     += p["tolerancias"]
                    _pont[u]["tol_ent"] += p.get("tol_entrada", 0)
                    _pont[u]["tol_alm"] += p.get("tol_almoco", 0)
                    _pont[u]["atr"]     += p["atrasos"]
                    _pont[u]["atr_ent"] += p["atrasos_entrada"]
                    _pont[u]["atr_alm"] += p["atrasos_almoco"]
                    _pont[u]["dias"]    += p["dias_trabalhados"]
                    _pont[u]["ocorr"].extend(p.get("ocorrencias") or [])
                    # Minutos de atraso somam; o banco NAO — ele ja vem
                    # acumulado da RHiD, e somar os meses contaria tudo de novo.
                    _pont[u]["min_atr"] += float(p.get("minutos_atraso", 0.0) or 0.0)
                    _pont[u]["banco"] = float(p.get("banco_min", 0.0) or 0.0)
                o = o_mes.get(u)
                if o:
                    _ocio[u]["disp"]  += o["horas_disp_min"]
                    _ocio[u]["cards"] += o["tempo_cards_min"]
                    # O valor JA calculado na linha do tempo, com as folgas de
                    # 10 e 5 minutos e a hora pessoal do dia. Recalcular aqui
                    # por disp menos cards jogaria fora tudo isso.
                    _ocio[u]["ocio"]  += o["ociosidade_min"]
        _tem_ponto = any(v["dias"] > 0 for v in _pont.values())
    except Exception as e:
        _tem_ponto = False
        _erro_pont = str(e)[:200]

    # Tempo de execução medido pelas etiquetas: % de cartões dentro do estimado
    _CC_ = _pc.COLUNAS_CONFIG
    try:
        import colunas_config as _cc_ed
        _editadas = _cc_ed.carregar() or {}
    except Exception:
        _editadas = {}

    _exec = {u: {"dentro": 0, "total": 0} for u in membros_ativos}
    _colunas_sem_tempo = set()
    for r in dados:
        for u, por_col in (r.get("tempo_membro_lista") or {}).items():
            if u not in _exec:
                continue
            for nl, tempos in por_col.items():
                # Coluna que ninguem configurou fica de fora: julgar contra um
                # numero inventado seria pior que nao julgar. Ela e listada na
                # tela para o gestor definir o tempo.
                if nl not in _CC_ and nl not in _editadas:
                    if tempos:
                        _colunas_sem_tempo.add(nl)
                    continue
                # cfg_coluna junta a tabela do codigo com o que o gestor editou
                # na tela. Antes lia COLUNAS_CONFIG direto, e o valor editado em
                # Configuracao de Metas nao tinha efeito nenhum aqui.
                est = _pc.cfg_coluna(nl).get("tempo_min") or 0
                if est <= 0:
                    _colunas_sem_tempo.add(nl)
                    continue
                for t in tempos:
                    _exec[u]["total"] += 1
                    if t <= est:
                        _exec[u]["dentro"] += 1

    # TRIAGEM e as demais de COLUNAS_SKIP / LISTAS_SEM_PONTUACAO estao fora da
    # conta de proposito — nao sao esquecimento de configuracao. Avisar sobre
    # elas so ensina a ignorar o aviso, e ai o dia em que aparecer uma coluna de
    # verdade mal configurada ninguem repara. O aviso tambem manda para uma tela
    # que so o gestor abre, entao so o gestor o ve.
    _fora_de_proposito = set(_pc.COLUNAS_SKIP) | set(_pc.LISTAS_SEM_PONTUACAO)
    _sem_tempo_reais = sorted(_colunas_sem_tempo - _fora_de_proposito)
    if _sem_tempo_reais and eh_master:
        st.caption(
            "⚠️ Fora da conta de tempo de execução, por não terem tempo "
            "estimado definido em Configuração de Metas → Colunas: "
            + " · ".join(_sem_tempo_reais))

    _sem_exec = not any(v["total"] for v in _exec.values())
    if eh_master and (not _tem_ponto or _sem_exec):
        _diagnostico_metas_individuais(_tem_ponto, _sem_exec, _diags_pont,
                                       _erro_pont, dados)

    def _card(username, nome, com_explicacao=False):
        pts  = pts_total.get(username, 0)
        meta = meta_total.get(username, len(dados) * 1500)
        _chave_sal = f"am_salario_{username}"

        st.markdown(f"##### {nome}")
        if com_explicacao:
            # O campo de salario mora dentro do painel: um so, alimentando a
            # tabela de exemplos e a conta real logo abaixo.
            _expl.render(chave_salario=_chave_sal,
                         min_contrib_n=_min_contrib_n,
                         min_contrib_x=_min_contrib_x,
                         max_adv_n=_max_adv_n, max_adv_x=_max_adv_x)

        o = _ocio.get(username, {"disp": 0.0, "cards": 0.0})
        p = _pont.get(username, {"tol": 0, "tol_ent": 0, "tol_alm": 0,
                                 "atr": 0, "atr_ent": 0, "atr_alm": 0,
                                 "ocorr": [], "min_atr": 0.0, "banco": 0.0})

        def _it_pontuacao(rotulo, alvo, cor):
            # Sem meta configurada o item continua na tela, so que vazio. Sumir
            # com ele desalinha a coluna dessa pessoa em relacao as outras, e
            # comparar colaboradores lado a lado e justamente o que se faz aqui.
            if alvo <= 0:
                st.markdown(_meta_ind_item(
                    rotulo, 100, "Meta não configurada para o mês",
                    aguardando=True), unsafe_allow_html=True)
                return
            pct = min(pts / alvo * 100, 100)
            falta = alvo - pts
            st.markdown(_meta_ind_item(
                rotulo, pct,
                f"{pts:,.0f} / {alvo:,.0f} pts · "
                + ("✅ Atingida!" if falta <= 0 else f"Faltam {falta:,.0f} pts"),
                cor=cor
            ), unsafe_allow_html=True)

        def _it_ociosidade(limite):
            rotulo = f"⏱️ Ociosidade abaixo de {limite}%"
            if not (_tem_ponto and o["disp"] > 0):
                st.markdown(_meta_ind_item(rotulo, 100, "", aguardando=True),
                            unsafe_allow_html=True)
                return
            _ocio_min = o.get("ocio", 0.0)
            pct_ocio = _ocio_min / o["disp"] * 100
            # Escala proporcional em vez de queda de 4 pontos por ponto: com a
            # anterior, qualquer ociosidade acima de 35% dava barra zero, e 40%
            # ficava indistinguivel de 90%.
            barra = 100 if pct_ocio <= limite else limite / pct_ocio * 100
            cor = ("#1BAF7A" if pct_ocio <= limite
                   else "#EDA100" if pct_ocio <= limite * 2 else "#E34948")
            # O teto em HORAS, que e o numero que da para administrar: 10% de
            # 154h (22 dias de 7h cobradas) sao 15h24 no mes. Percentual sozinho
            # nao diz quanto ainda sobra.
            _teto_min = o["disp"] * limite / 100
            _resta = _teto_min - _ocio_min
            st.markdown(_meta_ind_item(
                rotulo, barra,
                f"{_fmt_hm(_ocio_min)} ocioso de {_fmt_hm(_teto_min)} permitidas"
                + (f" · restam {_fmt_hm(_resta)}" if _resta >= 0
                   else f" · {_fmt_hm(-_resta)} acima do limite")
                + f" · {o['disp']/60:.0f}h cobradas no mês",
                cor=cor, valor_texto=f"{pct_ocio:.1f}%"
            ), unsafe_allow_html=True)

        # "Tempo de execucao dentro do estimado" saiu das duas metas. Ele
        # media a mesma coisa que o card de tempo medio logo abaixo, so que
        # contra o estimado de cada coluna em vez do alvo do mes — e o alvo do
        # mes e o numero acordado com a equipe. Dois cards para uma pergunta
        # so, e o que ninguem batia era sempre o outro.

        def _it_tempo_medio():
            """Tempo médio de execução da pessoa contra o alvo do mês."""
            # Referência zero significa mês nunca ancorado. Com o alvo já
            # definido, cair nas 2h é melhor do que sumir com o indicador.
            ref = float(_cfg_mes.get(f"exec_ref_{username}", 0) or 0) or 120.0
            _mt = mc.meta_execucao(_cfg_mes, username, ref)
            alvo = _mt["alvo"]
            if not _mt["definida"] or not alvo:
                # Mesmo motivo: o card fica, dizendo que a meta nao existe neste
                # mes. Era ele que a Myrella tinha e os outros nao, e a coluna
                # dela terminava um card abaixo das demais.
                st.markdown(_meta_ind_item(
                    "⏳ Tempo médio de execução", 100,
                    "Sem alvo de tempo definido para o mês",
                    aguardando=True), unsafe_allow_html=True)
                return
            rotulo = f"⏳ Tempo médio de execução até {_fmt_hm(alvo)}"
            atual = _medias_exec.get(username)
            if atual is None:
                st.markdown(_meta_ind_item(
                    rotulo, 100,
                    "Nenhum cartão com tempo medido no período", aguardando=True
                ), unsafe_allow_html=True)
                return
            # Barra cheia ao atingir; acima do alvo, proporcional — a mesma
            # escala da ociosidade, para 5% e 80% acima nao darem a mesma barra.
            barra = 100 if atual <= alvo else (alvo / atual * 100 if atual else 0)
            cor = ("#1BAF7A" if atual <= alvo
                   else "#EDA100" if atual <= ref else "#E34948")
            if atual <= alvo:
                fecho = "✅ Atingida!"
            elif atual <= ref:
                fecho = f"faltam {_fmt_hm(atual - alvo)} para o alvo"
            else:
                fecho = f"{_fmt_hm(atual - ref)} ACIMA da referência"
            st.markdown(_meta_ind_item(
                rotulo, barra,
                f"alvo {_fmt_hm(alvo)} · referência {_fmt_hm(ref)} · {fecho}",
                cor=cor, valor_texto=_fmt_hm(atual)
            ), unsafe_allow_html=True)

        # Advertencia e lancamento do gestor, um numero por mes na configuracao.
        # Somada no periodo, ela e comparada com o limite MENSAL multiplicado
        # pelos meses do periodo — comparar tres meses de advertencias com o
        # teto de um mes so acusaria quem esta dentro da regra.
        _n_meses = max(1, len(dados))
        _advs = sum(int(r["cfg"].get(f"adv_{username}", 0) or 0) for r in dados)
        _uteis_ent, _dec_ent = _dias_uteis_periodo(dados)

        def _it_advertencia(limite_mes):
            st.markdown(_item_advertencia(_advs, limite_mes, _n_meses),
                        unsafe_allow_html=True)

        def _it_contribuicao(piso):
            # O mesmo ritmo diario da secao "Entrar na meta do time": a pergunta
            # e a mesma nos dois lugares, e responder de dois jeitos e como as
            # telas passam a discordar.
            st.markdown(_item_contribuicao(
                pts, meta, piso,
                ritmo=_ritmo_entrada(pts, meta * piso / 100,
                                     _uteis_ent, _dec_ent)),
                unsafe_allow_html=True)

        def _it_contagem(rotulo, usado, limite, detalhe=""):
            """Card de tolerância ou atraso contra UM limite — o mensal ou o da MAXX."""
            if not _tem_ponto:
                st.markdown(_meta_ind_item(rotulo, 100, "", aguardando=True),
                            unsafe_allow_html=True)
                return
            pct = min(usado / limite * 100, 100) if limite else 0
            if usado > limite:
                cor, extra = "#E34948", f"limite estourado em {usado - limite}"
            elif usado >= limite * 0.7:
                cor, extra = "#EDA100", f"restam {limite - usado}"
            else:
                cor, extra = "#1BAF7A", f"restam {limite - usado}"
            corpo = f"{usado} de {limite} · {extra}"
            if detalhe:
                corpo += f" · {detalhe}"
            st.markdown(_meta_ind_item(rotulo, pct, corpo, cor=cor),
                        unsafe_allow_html=True)

        _det_atr = f"{p['atr_ent']} na entrada · {p['atr_alm']} na volta do almoço"
        # O atraso sai do banco de horas — quem desconta e a RHiD, o Studio le o
        # saldo dela. Sem isso a tela mostrava "3 atrasos" e nada dizia o que
        # aquilo custou: chegar 6 min tarde e chegar 40 min tarde eram iguais.
        _banco = float(p.get("banco", 0.0) or 0.0)
        _min_atr = float(p.get("min_atr", 0.0) or 0.0)
        if _min_atr > 0:
            _det_atr += f" · {_fmt_hm(_min_atr)} de atraso no total"
        if _banco:
            _sinal = "+" if _banco > 0 else "−"
            _det_atr += f" · banco {_sinal}{_fmt_hm(abs(_banco))}"
        # A mesma abertura das tolerancias. Sem ela "13 tolerancias" era um
        # numero sem explicacao para quem so chegou atrasado sete vezes.
        _det_tol = f"{p['tol_ent']} na entrada · {p['tol_alm']} na volta do almoço"

        # ── META MENSAL ───────────────────────────────────────────────────────
        st.markdown(_titulo_grupo_meta("Meta mensal", "#1BAF7A"),
                    unsafe_allow_html=True)
        _it_pontuacao("📈 Pontuação", meta_total.get(username, len(dados) * 1500),
                      "#1BAF7A")
        _it_ociosidade(OCIO_META_NORMAL)
        _it_tempo_medio()
        _it_contagem(f"🕐 Tolerâncias de pontualidade ({max_tol}/mês)",
                     p["tol"], max_tol, _det_tol)
        _it_contagem(f"⏰ Atrasos de pontualidade ({max_atr}/mês)",
                     p["atr"], max_atr, _det_atr)
        _it_contribuicao(_min_contrib_n)
        _it_advertencia(_max_adv_n)

        _detalhe_pontualidade(p.get("ocorr") or [], username)

        # ── META MAXX ─────────────────────────────────────────────────────────
        # Os mesmos indicadores, com os limites proprios da MAXX. Antes a MAXX
        # aparecia so como uma observacao no rodape dos cards mensais — dava para
        # ver se estava dentro, nao o quanto faltava.
        st.markdown(_titulo_grupo_meta("Meta MAXX", "#EDA100"),
                    unsafe_allow_html=True)
        _it_pontuacao("⭐ Pontuação", maxx_total.get(username, 0), "#EDA100")
        _it_ociosidade(OCIO_META_MAXX)
        _it_contagem(f"🕐 Tolerâncias de pontualidade ({max_tol_mx}/mês)",
                     p["tol"], max_tol_mx, _det_tol)
        _it_contagem(f"⏰ Atrasos de pontualidade ({max_atr_mx}/mês)",
                     p["atr"], max_atr_mx, _det_atr)
        _it_contribuicao(_min_contrib_x)
        _it_advertencia(_max_adv_x)

        # Calculadora de ganhos
        pct_i = min(pts / meta * 100, 100) if meta > 0 else 0
        st.markdown('<div style="margin-top:4px;"></div>', unsafe_allow_html=True)
        if com_explicacao:
            salario = float(st.session_state.get(_chave_sal) or 0.0)
            if salario <= 0:
                st.caption("💰 Digite seu salário no painel acima para ver seus "
                           "ganhos deste mês.")
        else:
            # Mesma razao do botao la do painel: campo de digitacao so
            # confirma ao perder o foco, e sem um clique visivel a pessoa acha
            # que a tela ignorou o que ela escreveu.
            _cs, _cb = st.columns([3, 1])
            salario = _cs.number_input(
                "💰 Informe seu salário base para calcular seus ganhos mensais até o momento:",
                min_value=0.0, value=0.0, step=100.0, format="%.2f",
                key=_chave_sal, label_visibility="visible"
            )
            _cb.markdown("<div style='height:28px;'></div>",
                         unsafe_allow_html=True)
            _cb.button("✅ Confirmar", key=f"{_chave_sal}_ok",
                       use_container_width=True)
        if salario > 0:
            # Bônus só entra quando a meta correspondente foi BATIDA (≥100%).
            #
            # A metade do time e a metade do colaborador pagam, cada uma, o nivel
            # MAIS ALTO alcancado — a MAXX toma o lugar da mensal, nao se soma a
            # ela. Antes daqui a MAXX pagava 5% + 5% e o bonus MAXX individual
            # dependia da meta MENSAL do colaborador, nao da MAXX dele.
            meta_ind = meta_total.get(username, len(dados) * 1500)
            meta_ind_maxx = maxx_total.get(username, 0)

            # Bater a meta do time nao basta: e preciso ter entrado nela. Os
            # dois porteiros sao o piso de contribuicao (80% da propria meta
            # para a coletiva, 100% para a MAXX) e o teto de advertencias
            # (2 e 1). Sem isto a regra existiria so como texto na tela, e
            # quem contribuiu pouco continuaria recebendo pelo esforco alheio.
            #
            # Os porteiros valem sobre a METADE DO TIME. A metade individual
            # continua sendo do proprio resultado de cada um.
            # A mesma conta do relatorio de elegibilidade, e nao uma copia
            # dela: duas contas para a mesma pergunta e como a tela do
            # colaborador passa a discordar da lista do gestor.
            _el = _elegibilidade(dados, [username]).get(username, {})
            _pct_ind_real = _el.get("pct", 0.0)
            _lim_adv_n = _el.get("lim_adv_n", 0)
            _lim_adv_x = _el.get("lim_adv_x", 0)
            _entra_col = _el.get("entra_col", False)
            _entra_maxx = _el.get("entra_maxx", False)

            meta_col_batida  = pct_eq   >= 100 and _entra_col
            meta_maxx_batida = pct_maxx >= 100 and _entra_maxx
            meta_ind_batida      = meta_ind > 0 and pts >= meta_ind
            meta_ind_maxx_batida = meta_ind_maxx > 0 and pts >= meta_ind_maxx

            # Quando o time fecha e a pessoa fica de fora, dizer por que. Um
            # bonus que some sem explicacao vira conversa no corredor.
            _bloqueios = []
            if pct_eq >= 100 and not _entra_col:
                if _pct_ind_real < _min_contrib_n:
                    _bloqueios.append(
                        f"contribuiu com {_pct_ind_real:.0f}% da sua meta "
                        f"individual — o mínimo para entrar na coletiva é "
                        f"{_min_contrib_n}%")
                if _advs > _lim_adv_n:
                    _bloqueios.append(
                        f"{_advs} advertência(s) no período — o máximo para a "
                        f"coletiva é {_lim_adv_n}")
            elif pct_maxx >= 100 and not _entra_maxx:
                if _pct_ind_real < _min_contrib_x:
                    _bloqueios.append(
                        f"contribuiu com {_pct_ind_real:.0f}% da sua meta "
                        f"individual — o mínimo para entrar na MAXX é "
                        f"{_min_contrib_x}%")
                if _advs > _lim_adv_x:
                    _bloqueios.append(
                        f"{_advs} advertência(s) no período — o máximo para a "
                        f"MAXX é {_lim_adv_x}")
            if _bloqueios:
                st.markdown(
                    '<div style="background:#E3494815;border:1px solid #E34948;'
                    'border-radius:8px;padding:10px 13px;margin-bottom:8px;">'
                    '<div style="font-size:11px;font-weight:700;color:#E34948;'
                    'margin-bottom:4px;">🚫 Fora da meta do time neste período</div>'
                    '<div style="font-size:10px;color:var(--ms-texto-sec);'
                    'line-height:1.6;">' + "<br>".join("· " + b for b in _bloqueios)
                    + '</div></div>', unsafe_allow_html=True)

            pct_time, pct_seu = _expl.bonus_percentuais(
                meta_col_batida, meta_maxx_batida,
                meta_ind_batida, meta_ind_maxx_batida)

            # Cada metade vira uma linha só: a do time e a sua.
            bonus_col = salario * pct_time / 100
            bonus_ind = salario * pct_seu / 100
            total = salario + bonus_col + bonus_ind

            cor_total = "#FFD700" if (meta_maxx_batida or meta_ind_maxx_batida) else "#1BAF7A"

            def _bonus_val(valor, batida, cor):
                if batida:
                    return f'<div style="font-size:13px;font-weight:700;color:{cor};">+R$ {valor:,.2f}</div>'
                return '<div style="font-size:13px;font-weight:700;color:var(--ms-texto-sec);">—</div>'

            def _bonus_sub(batida, label):
                if batida:
                    return f'<div style="font-size:7px;color:var(--ms-texto-sec);">{label}</div>'
                return '<div style="font-size:7px;color:#e57373;">Meta não batida</div>'

            # A conta aparece SEMPRE, mesmo valendo R$ 0,00 hoje.
            #
            # Antes, sem nenhuma meta batida, o lugar dela era ocupado por um
            # "nenhuma meta atingida ainda": quem digitava o salario no dia 4
            # nao via numero nenhum, e a calculadora parecia quebrada. Ela nao
            # estava — so nao tinha o que somar. Mostrar R$ 0,00 na parcela que
            # ainda nao vale, com o quanto falta para ela valer, responde a
            # pergunta que a pessoa veio fazer: "e se o mes acabasse hoje?"
            def _parcela(rotulo, valor, pct, nivel, cor):
                if pct <= 0:
                    return (f'<div><div style="font-size:8px;color:var(--ms-texto-sec);'
                            f'text-transform:uppercase;">{rotulo}</div>'
                            f'<div style="font-size:14px;font-weight:700;'
                            f'color:var(--ms-texto-sec);">—</div>'
                            f'<div style="font-size:8px;color:#e57373;">Meta não batida</div></div>')
                return (f'<div><div style="font-size:8px;color:var(--ms-texto-sec);'
                        f'text-transform:uppercase;">{rotulo}</div>'
                        f'<div style="font-size:14px;font-weight:700;color:{cor};">'
                        f'+{_expl._reais(valor)}</div>'
                        f'<div style="font-size:8px;color:var(--ms-texto-sec);">'
                        f'{nivel} · +{pct:.0f}%</div></div>')

            _niv_time = "Meta MAXX" if meta_maxx_batida else "Meta mensal"
            _niv_seu  = "Meta MAXX" if meta_ind_maxx_batida else "Meta mensal"
            st.markdown(
                f'<div style="background:var(--ms-metric-bg);border:1px solid var(--ms-metric-bd);'
                f'border-radius:8px;padding:10px 12px;margin-top:6px;">'
                f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:8px;">'
                f'<div><div style="font-size:8px;color:var(--ms-texto-sec);text-transform:uppercase;">Salário Base</div>'
                f'<div style="font-size:14px;font-weight:700;color:var(--ms-texto);">{_expl._reais(salario)}</div></div>'
                + _parcela("🤝 Parte do time", bonus_col, pct_time, _niv_time,
                           "#FFD700" if meta_maxx_batida else "#1BAF7A")
                + _parcela("🙋 Parte sua", bonus_ind, pct_seu, _niv_seu,
                           "#FFD700" if meta_ind_maxx_batida else "#1BAF7A")
                + f'<div><div style="font-size:8px;color:var(--ms-texto-sec);text-transform:uppercase;">'
                f'Total a Receber (+{pct_time + pct_seu:.0f}%)</div>'
                f'<div style="font-size:17px;font-weight:700;color:{cor_total};">'
                f'{_expl._reais(total)}</div></div>'
                f'</div></div>',
                unsafe_allow_html=True
            )

            # O que ainda falta, em pontos, para cada parcela que hoje vale
            # zero. Sem isto a pessoa ve "R$ 0,00" e nao sabe se esta a 50 ou a
            # 5.000 pontos do bonus.
            _faltas = []
            if not meta_col_batida and _meta_eq > 0 and _saldo_eq < _meta_eq:
                _faltas.append(
                    f"🤝 faltam <b>{_n_br(_meta_eq - _saldo_eq)} pts ao time</b> "
                    f"para a Meta Coletiva (+{_expl.PCT_COLETIVO_MENSAL:.0f}%)")
            if (not meta_maxx_batida and _meta_maxx > 0
                    and _saldo_eq < _meta_maxx):
                _faltas.append(
                    f"⭐ faltam <b>{_n_br(_meta_maxx - _saldo_eq)} pts ao time</b> "
                    f"para a Meta MAXX (+{_expl.PCT_COLETIVO_MAXX:.0f}%)")
            if not meta_ind_batida and meta_ind > 0 and pts < meta_ind:
                _faltas.append(
                    f"🙋 faltam <b>{_n_br(meta_ind - pts)} pts seus</b> para a "
                    f"sua meta individual (+{_expl.PCT_INDIVIDUAL_MENSAL:.0f}%)")
            if (not meta_ind_maxx_batida and meta_ind_maxx > 0
                    and pts < meta_ind_maxx):
                _faltas.append(
                    f"⭐ faltam <b>{_n_br(meta_ind_maxx - pts)} pts seus</b> para "
                    f"a sua MAXX (+{_expl.PCT_INDIVIDUAL_MAXX:.0f}%)")
            if _faltas:
                st.markdown(
                    '<div style="font-size:10px;color:var(--ms-texto-sec);'
                    'line-height:1.7;margin-top:5px;">'
                    + "<br>".join("· " + f for f in _faltas)
                    + '</div>', unsafe_allow_html=True)

    # Exibe master vê todos; membro vê só o próprio
    if eh_master:
        cols_mi = st.columns(len(membros_ativos))
        for i, (u, nome) in enumerate(membros_ativos.items()):
            with cols_mi[i]:
                _card(u, nome)
    elif usuario_logado in membros_ativos:
        _card(usuario_logado, membros_ativos[usuario_logado], com_explicacao=True)
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


def _gauge_svg(pct, cor, titulo, sub="", legend="", valor=None, max_larg=130):
    """Velocímetro semicircular SVG inline com traço colorido abaixo.
    legend: texto explicativo opcional abaixo da barra colorida."""
    p = max(0.1, min(99.9, float(pct)))
    cx, cy, r = 50, 52, 40
    def _pt(a): return cx + r * math.cos(a), cy - r * math.sin(a)
    sx, sy = _pt(math.pi); ex, ey = _pt(0)
    af = math.pi * (1 - p / 100); fx, fy = _pt(af)
    lg = 0  # semicírculo sempre < 180° → large-arc nunca necessário
    # As pontas do arco descem ate y=56.5 (centro 52 + metade do traco de 9). O
    # titulo comecava em y=59 com o topo da letra por volta de 54,3 — 2,2px
    # dentro do arco, e num rotulo longo como "Sem atraso em prioritarios" a
    # linha passava justamente por baixo das pontas. Tudo desce 5px.
    vh = 99 if legend else 87
    legend_el = (
        f'<text x="50" y="94" text-anchor="middle" font-size="5" '
        f'fill="var(--ms-texto-sec,#777)" font-style="italic">{legend}</text>'
    ) if legend else ""
    return (
        f'<div style="text-align:center;">'
        f'<svg viewBox="0 0 100 {vh}" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:{max_larg}px;">'
        f'<path d="M{sx:.2f},{sy:.2f} A{r},{r} 0 0,1 {ex:.2f},{ey:.2f}" fill="none" '
        f'stroke="var(--ms-metric-bd,#2e2e2e)" stroke-width="9" stroke-linecap="round"/>'
        f'<path d="M{sx:.2f},{sy:.2f} A{r},{r} 0 {lg},1 {fx:.2f},{fy:.2f}" fill="none" '
        f'stroke="{cor}" stroke-width="9" stroke-linecap="round"/>'
        # `valor` no lugar da porcentagem para o que e contagem: 2 penalidades
        # sao duas, nao "50% do limite". O arco continua sendo a fracao do
        # limite — e dele que sai a nocao de quanto ainda cabe.
        f'<text x="50" y="42" text-anchor="middle" font-size="14" font-weight="700" '
        f'fill="{cor}">{valor if valor is not None else f"{p:.0f}%"}</text>'
        f'<text x="50" y="64" text-anchor="middle" font-size="6.5" font-weight="600" '
        f'fill="var(--ms-texto,#ccc)">{titulo}</text>'
        f'<text x="50" y="74" text-anchor="middle" font-size="5.5" '
        f'fill="var(--ms-texto-sec,#888)">{sub}</text>'
        f'<rect x="14" y="80" width="72" height="3" rx="1.5" fill="{cor}"/>'
        f'{legend_el}'
        f'</svg></div>'
    )


def _pizza_svg(segmentos, box_pct, box_label, box_cor="#4A90D9"):
    """Rosca com as fatias destacadas. segmentos = [(cor, valor, nome)].

    Era uma pizza cheia, fatias encostadas. Duas coisas melhoram com o furo no
    meio e a folga entre elas: a comparacao passa a ser pelo comprimento do arco,
    que se le melhor que area, e cada fatia ganha um contorno proprio — nao e
    mais a divisa de cor que separa uma da outra, o que importa quando duas cores
    vizinhas sao parecidas.

    O numero da fatia vive dentro dela e repete o da legenda, para o olho ir de
    uma a outra sem contar posicao.
    """
    cx = cy = 140
    r_ext, r_int = 128, 62

    # O vao e uma distancia, nao um angulo. Com angulo fixo o vao encolhe junto
    # com o raio: 2,2 graus davam 9,8px na borda externa e 5,1px na interna, e o
    # contorno de 7px que arredonda os cantos comia os dois — na borda interna
    # sobrava -1,9px, ou seja, as fatias se sobrepunham ali. Convertendo a
    # distancia em angulo a cada raio, os lados ficam paralelos e o filete de
    # fundo aparece inteiro, do lado de fora ao de dentro.
    VAO = 11.5          # distancia total entre duas fatias, em unidades do SVG
    TRACO = 6           # contorno que arredonda os cantos; ele alarga a fatia
    total = sum(s[1] for s in segmentos if s[1] > 0) or 1

    def _pt(raio, ang):
        return cx + raio * math.cos(ang), cy + raio * math.sin(ang)

    fatias, rotulos = [], []
    ang = -math.pi / 2
    for i, (cor, val, nome) in enumerate(segmentos):
        if val <= 0:
            continue
        frac = val / total
        a0, a1 = ang, ang + 2 * math.pi * frac
        ang = a1
        abertura = a1 - a0
        # Recuo por raio, e nunca mais que um terco da abertura: numa fatia
        # estreita o vao consumiria o arco inteiro e ela sumiria.
        def _rec(raio):
            return min((VAO / 2) / raio, abertura / 3)
        re_, ri_ = _rec(r_ext), _rec(r_int)
        e0, e1 = a0 + re_, a1 - re_
        i0, i1 = a0 + ri_, a1 - ri_
        lg = 1 if (e1 - e0) > math.pi else 0
        xe0, ye0 = _pt(r_ext, e0); xe1, ye1 = _pt(r_ext, e1)
        xi1, yi1 = _pt(r_int, i1); xi0, yi0 = _pt(r_int, i0)
        fatias.append(
            f'<path d="M{xe0:.2f},{ye0:.2f} A{r_ext},{r_ext} 0 {lg},1 {xe1:.2f},{ye1:.2f} '
            f'L{xi1:.2f},{yi1:.2f} A{r_int},{r_int} 0 {lg},0 {xi0:.2f},{yi0:.2f} Z" '
            f'fill="{cor}" stroke="{cor}" stroke-width="{TRACO}" stroke-linejoin="round"/>'
        )
        # Numero e percentual no meio do anel. Fatia curta demais nao comporta os
        # dois — fica so o numero, e o percentual e lido na legenda.
        mid = (a0 + a1) / 2
        lx, ly = _pt((r_ext + r_int) / 2, mid)
        cabe_pct = frac >= 0.05
        rotulos.append(
            f'<text x="{lx:.1f}" y="{ly - (8 if cabe_pct else 0):.1f}" text-anchor="middle" '
            f'dominant-baseline="middle" font-size="16" font-weight="700" '
            f'fill="#fff">{i+1:02d}</text>'
            + (f'<text x="{lx:.1f}" y="{ly + 12:.1f}" text-anchor="middle" '
               f'dominant-baseline="middle" font-size="14" font-weight="700" '
               f'fill="#fff" fill-opacity="0.92">{frac*100:.0f}%</text>' if cabe_pct else "")
        )

    # A rosca e o assunto do bloco, e ocupava um terco da largura enquanto a
    # legenda espalhava cinco linhas em duas colunas e deixava o pe do cartao
    # vazio. Rosca grande e legenda empilhada trocam esse espaco de lugar.
    svg = (
        f'<svg viewBox="0 0 280 280" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;max-width:400px;min-width:240px;flex:1 1 300px;">'
        + "".join(fatias) + "".join(rotulos) + '</svg>'
    )

    # Legenda em duas colunas: uma embaixo da outra deixava metade da largura do
    # cartao vazia, e cada nome ainda vinha truncado.
    itens = ""
    for i, (cor, val, nome) in enumerate(segmentos):
        pct = (val / total * 100) if total else 0
        itens += (
            f'<div style="display:flex;align-items:center;gap:10px;min-width:0;'
            f'padding:7px 0;border-bottom:1px solid var(--ms-divisor,#2f2f2f);">'
            f'<div style="width:26px;height:26px;border-radius:7px;background:{cor};flex-shrink:0;'
            f'display:flex;align-items:center;justify-content:center;font-size:9px;'
            f'font-weight:700;color:#fff;">{i+1:02d}</div>'
            f'<div style="font-size:12px;color:var(--ms-texto,#ccc);line-height:1.35;flex:1;'
            f'min-width:0;">{nome}</div>'
            f'<div style="font-size:13px;font-weight:700;color:var(--ms-texto-sec,#888);'
            f'flex-shrink:0;">{pct:.0f}%</div></div>'
        )
    # Uma coluna so: em duas, cada nome vinha truncado no meio e a lista ainda
    # deixava o pe do cartao vazio. Empilhada, o nome inteiro cabe.
    leg_html = f'<div style="display:flex;flex-direction:column;">{itens}</div>'
    # A faixa fecha o bloco da legenda: mesma largura das duas colunas, conteudo
    # centrado. Encostada a esquerda ela parecia uma barra de progresso pela
    # metade; ocupando a largura inteira, e um rodape, e o numero deixa de sugerir
    # preenchimento.
    box_html = (
        f'<div style="margin-top:12px;background:{box_cor};border-radius:6px;padding:7px 12px;'
        f'display:flex;align-items:center;justify-content:center;gap:8px;opacity:0.9;">'
        f'<div style="font-size:18px;font-weight:800;color:#fff;white-space:nowrap;">{box_pct}</div>'
        f'<div style="font-size:9px;color:rgba(255,255,255,0.92);line-height:1.4;">{box_label}</div>'
        f'</div>'
    )
    return (
        f'<div style="display:flex;align-items:center;gap:24px;padding:8px 0;'
        f'flex-wrap:wrap;">'
        + svg
        + f'<div style="flex:1 1 300px;min-width:260px;">{leg_html}{box_html}</div>'
        + '</div>'
    )


def _curva_suave(pts, y_min=None, y_max=None):
    """Caminho SVG passando por todos os pontos, com as quinas arredondadas.

    Catmull-Rom convertido para Bézier cúbica: cada ponto continua exatamente
    onde estava — a linha só deixa de virar em bico. Os pontos de controle são
    presos à área do gráfico porque a curva pode ultrapassar os extremos entre
    dois pontos distantes, e sair da moldura seria pior que o bico.
    """
    if len(pts) < 2:
        return ""
    if len(pts) == 2:
        (x0, y0), (x1, y1) = pts
        return f"M{x0:.1f},{y0:.1f} L{x1:.1f},{y1:.1f}"

    def _presa(v):
        if y_min is not None and v < y_min:
            return y_min
        if y_max is not None and v > y_max:
            return y_max
        return v

    d = [f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"]
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        c1x = p1[0] + (p2[0] - p0[0]) / 6
        c1y = _presa(p1[1] + (p2[1] - p0[1]) / 6)
        c2x = p2[0] - (p3[0] - p1[0]) / 6
        c2y = _presa(p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C{c1x:.1f},{c1y:.1f} {c2x:.1f},{c2y:.1f} {p2[0]:.1f},{p2[1]:.1f}")
    return " ".join(d)


def _grafico_barras_svg(labels, vals1, vals2=None, label1="Meta", label2="Realizado",
                         line_vals=None, cor1="#4A90D9", cor2_fn=None,
                         melhor_idx=None, melhor_txt=None,
                         cor2="#1BAF7A", cor_linha="#FF6B6B", label_linha="Delta",
                         linha_na_escala=False, fmt=None):
    """SVG bar chart (1 ou 2 barras/mês) + linha opcional. Retorna HTML.

    A linha nasceu como delta — um saldo, que precisa de eixo próprio centrado
    no zero. Com `linha_na_escala` ela passa a ser uma grandeza da MESMA escala
    das barras (o realizado contra as metas, por exemplo) e é desenhada na
    régua delas: com escala própria, uma linha acima da barra poderia significar
    um valor abaixo dela.
    """
    n = len(labels)
    if n == 0:
        return '<div style="padding:20px;text-align:center;color:var(--ms-texto-sec);">Sem dados</div>'
    fmt = fmt or (lambda v: f"{v:,.0f}")
    W, H = 560, 195
    ml, mr, mt, mb_m = 54, 38, 34, 46   # topo maior: o valor da barra mora ali
    cw = W - ml - mr; ch = H - mt - mb_m
    all_v = list(vals1) + (list(vals2) if vals2 else [])
    if linha_na_escala and line_vals is not None:
        all_v += list(line_vals)
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
            f'<text x="{ml-4}" y="{yg+3:.0f}" text-anchor="end" font-size="7.5" fill="var(--ms-texto-sec,#888)">{fmt(vg)}</text>',
        ]
    line_pts = []
    for i in range(n):
        cx_c = ml + (i + 0.5) * col_w
        v1 = vals1[i]
        x1 = cx_c - bw - 1 if vals2 is not None else cx_c - bw / 2
        parts.append(f'<rect x="{x1:.1f}" y="{bary(v1):.1f}" width="{bw:.1f}" height="{barh(v1):.1f}" fill="{cor1}" opacity="0.55" rx="2"/>')
        # O valor em cima da barra. Sem ele so dava para estimar a altura contra
        # a regua da esquerda, e a pergunta que se faz olhando este grafico —
        # quanto era a meta, quanto saiu — nao tinha resposta na tela.
        parts.append(
            f'<text x="{x1+bw/2:.1f}" y="{bary(v1)-3:.1f}" text-anchor="middle" '
            f'font-size="6.5" font-weight="700" fill="var(--ms-texto-sec,#888)">{fmt(v1)}</text>')
        if vals2 is not None:
            v2 = vals2[i]; c2 = cor2_fn(i) if cor2_fn else cor2
            parts.append(f'<rect x="{cx_c+1:.1f}" y="{bary(v2):.1f}" width="{bw:.1f}" height="{barh(v2):.1f}" fill="{c2}" opacity="0.9" rx="2"/>')
            parts.append(
                f'<text x="{cx_c+1+bw/2:.1f}" y="{bary(v2)-3:.1f}" text-anchor="middle" '
                f'font-size="6.5" font-weight="700" fill="{c2}">{fmt(v2)}</text>')
        if line_vals is not None:
            if linha_na_escala:
                ly = bary(line_vals[i])
            else:
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
        if not linha_na_escala:
            max_d = max(abs(v) for v in line_vals) or 1
            y0 = mt + ch / 2
            parts.append(f'<line x1="{ml}" y1="{y0:.0f}" x2="{W-mr}" y2="{y0:.0f}" stroke="#555" stroke-width="0.7" stroke-dasharray="3,3"/>')
            for step, lbl_d in [(-1, f"{-max_d:+,.0f}"), (0, "0"), (1, f"+{max_d:,.0f}")]:
                yd = y0 - step * ch / 2
                parts.append(f'<text x="{W-mr+3}" y="{yd+3:.0f}" font-size="6.5" fill="{cor_linha}">{lbl_d}</text>')
        else:
            # O valor de cada ponto, que e o que se veio ler aqui.
            for (px, py), pv in zip(line_pts, line_vals):
                parts.append(
                    f'<text x="{px:.1f}" y="{py - 7:.1f}" text-anchor="middle" '
                    f'font-size="6.5" font-weight="700" fill="{cor_linha}">'
                    f'{fmt(pv)}</text>')
        # Curva no lugar da poligonal: em quatro meses a linha de delta virava
        # um zigue-zague de bicos, e o bico sugere um evento que nao existe —
        # o dado e mensal, a passagem entre um mes e outro e continua.
        parts.append(
            f'<path d="{_curva_suave(line_pts, mt, mt + ch)}" fill="none" '
            f'stroke="{cor_linha}" stroke-width="1.8" stroke-linecap="round"/>')
        parts += [f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{cor_linha}"/>' for x, y in line_pts]
    # Callout melhor mês
    if melhor_idx is not None and melhor_txt and 0 <= melhor_idx < n:
        cx_c = ml + (melhor_idx + 0.5) * col_w
        v_pk = max(vals1[melhor_idx], (vals2[melhor_idx] if vals2 else 0))
        # Sobe 8px: o numero da barra agora ocupa o espaco logo acima dela.
        ytop = bary(v_pk) - 14; ytxt = max(mt + 2, ytop - 20)
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
            f'<rect x="{lx+62}" y="8" width="9" height="9" fill="{cor2}" rx="1"/>',
            f'<text x="{lx+73}" y="15.5" font-size="7" fill="var(--ms-texto-sec,#888)">{label2}</text>',
        ]
    if line_vals is not None:
        lx3 = lx + 130
        parts += [
            f'<line x1="{lx3}" y1="12.5" x2="{lx3+14}" y2="12.5" stroke="{cor_linha}" stroke-width="1.5"/>',
            f'<circle cx="{lx3+7}" cy="12.5" r="2.5" fill="{cor_linha}"/>',
            f'<text x="{lx3+18}" y="15.5" font-size="7" fill="var(--ms-texto-sec,#888)">{label_linha}</text>',
        ]
    return (
        f'<div style="width:100%;overflow:hidden;padding:4px 0;">'
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;">'
        + "".join(parts) + f'</svg></div>'
    )


def _chart_pontuacao_meta(dados):
    """HTML/SVG: as duas metas em barras, o realizado como linha sobre elas.

    Era meta contra realizado, com o delta numa linha de eixo proprio. Duas
    coisas nao davam: a MAXX — que e a outra meta cobrada — nao aparecia, e o
    delta repetia em linha o que as duas barras ja diziam, num eixo diferente
    do delas. Agora as barras sao os dois alvos e a linha e o resultado: onde
    ela passa por cima da barra azul, a coletiva foi batida; por cima da
    dourada, a MAXX.
    """
    labels = [r["label"] for r in dados]
    metas  = [r["meta_eq"] for r in dados]
    maxx   = [r.get("meta_maxx", 0) or 0 for r in dados]
    saldos = [r["saldo"]   for r in dados]
    pcts   = [r["pct_mensal"] for r in dados]
    bi = max(range(len(pcts)), key=lambda i: pcts[i]) if pcts else None
    sinal = "+" if bi is not None and pcts[bi] >= 100 else ""
    melhor_txt = f"{sinal}{pcts[bi]:.1f}% · {labels[bi]}" if bi is not None else None
    avg_pct = sum(pcts) / len(pcts) if pcts else 0
    html = _grafico_barras_svg(
        labels, metas, maxx,
        label1="Meta Coletiva", label2="Meta MAXX",
        line_vals=saldos, linha_na_escala=True,
        cor1="#4A90D9", cor2_fn=lambda i: "#1BAF7A", cor2="#1BAF7A",
        cor_linha="#FF8A2B", label_linha="Realizado",
        melhor_idx=bi, melhor_txt=melhor_txt,
    )
    return html + f'<div style="text-align:right;font-size:9px;color:#EDA100;padding:0 4px 4px;">Média período: {avg_pct:.1f}%</div>'


def _chart_indices_meta(dados):
    """Os seis topicos da meta, em velocimetros, para Coletiva e MAXX.

    Antes eram quatro mostradores que nao correspondiam aos topicos cobrados
    logo acima: "Pontualidade" media atraso no board inteiro enquanto a meta e
    sobre prioritarios P8-P10, e "Alcance MAXX" cortava em 100 justamente quando
    a equipe passava dela. Agora saem de _metas_topicos, a mesma fonte das
    barras — as duas leituras nao tem como divergir.
    """
    r, topicos = _metas_topicos(dados)
    if not topicos:
        return ('<div style="padding:20px;text-align:center;'
                'color:var(--ms-texto-sec);">Sem dados</div>')

    def _cor(pct, dourado=False):
        if pct >= 100:
            return "#FFD700" if dourado else "#1BAF7A"
        if pct >= 75:
            return "#EDA100"
        return "#E34948"

    def _bloco(titulo, cor_tit, chave_pct, chave_sub, dourado):
        gauges = ""
        for t in topicos:
            pct = float(t[chave_pct] or 0)
            # Topico com regra propria de cor manda; os demais seguem a escala
            # comum, em que mais alto e melhor.
            cor = t.get("cor_n" if chave_pct == "pct_n" else "cor_x") or _cor(pct, dourado)
            # O numero fica no subtitulo quando passa de 100: o arco satura, o
            # texto nao. So vale para os que sao porcentagem — no de contagem o
            # centro ja mostra o numero cheio.
            _val = t.get("valor_n" if chave_pct == "pct_n" else "valor_x")
            _sub = t[chave_sub]
            if pct > 100 and _val is None:
                _sub = f"{pct:.0f}% · {_sub}"
            gauges += _gauge_svg(min(pct, 100), cor, t["rotulo"], _sub,
                                 valor=_val, max_larg=150)
        # A coluna da direita terminava a 300px do fim da coluna da esquerda:
        # os mostradores estavam travados em 130px e sobrava tela embaixo. Com
        # eles maiores e com folga entre as linhas, os dois blocos ocupam a
        # altura dos graficos ao lado — e a emenda entre Coletiva e MAXX fica
        # curta de proposito, para os dois continuarem lidos como um par.
        return (
            f'<div style="font-size:10px;font-weight:600;color:{cor_tit};'
            f'text-transform:uppercase;letter-spacing:.5px;margin:0 0 4px;">{titulo}</div>'
            f'<div style="display:grid;grid-template-columns:repeat(3,1fr);'
            f'gap:20px 6px;margin-bottom:16px;justify-items:center;">{gauges}</div>')

    return (
        f'<div style="font-size:9px;color:var(--ms-texto-sec);text-transform:uppercase;'
        f'letter-spacing:.5px;margin-bottom:8px;">Referência: {r["label"]}</div>'
        + _bloco("📋 Meta Coletiva", "#1BAF7A", "pct_n", "sub_n", False)
        + _bloco("⭐ Meta MAXX", "#FFD700", "pct_x", "sub_x", True))


def _chart_tempo_medio_equipe(dados):
    """Tempo médio de execução da EQUIPE, no mesmo modelo da pontuação.

    Duas barras e uma linha: a referência do mês e o alvo do mês são as barras,
    o tempo que as demandas realmente levaram é a linha. Aqui BAIXO é melhor —
    a linha abaixo da barra verde é o alvo batido. As barras repetem as cores
    do gráfico de pontuação; o que separa os dois é a linha, laranja lá e
    amarela aqui.

    Cada mês é medido contra o SEU alvo: mudar o alvo em outubro não pode
    repintar setembro.
    """
    if not dados:
        return ('<div style="padding:20px;text-align:center;font-size:11px;'
                'color:var(--ms-texto-sec);">Sem dados no período</div>')

    # Ordem por mes: os meses sem atividade sao acrescentados no fim por
    # _extend_dados_ano, e sem ordenar o grafico saia fora de ordem.
    def _chave(r):
        try:
            return (int(r.get("ano", 0)), int(r.get("mes", 0)))
        except (TypeError, ValueError):
            return (0, 0)

    linhas = []
    for r in (sorted(dados, key=_chave) if all(r.get("mes") for r in dados)
              else dados):
        _um = [r]
        _cfg_r = r.get("cfg") or {}
        _ref_r, _n_r, _dig_r = _ref_execucao_equipe(_um, _cfg_r)
        _m_r = mc.meta_execucao(_cfg_r, "equipe", _ref_r or 0)
        _real_r = _media_execucao_geral(_um)
        if _real_r is None and not _ref_r:
            continue          # mes sem medicao e sem referencia nao diz nada
        linhas.append({"label": r.get("label", ""), "real": _real_r or 0.0,
                       "ref": _ref_r or 0.0, "alvo": _m_r["alvo"] or 0.0})

    medidos = [l for l in linhas if l["real"]]
    if not medidos:
        return ('<div style="padding:20px;text-align:center;font-size:11px;'
                'color:var(--ms-texto-sec);">Nenhum cartão com tempo medido '
                'no período</div>')

    at = medidos[-1]
    if not at["alvo"]:
        _fecho = "sem alvo definido para o mês — defina em Configuração de Metas"
        _cor_f = ADV_NEUTRO
    elif at["real"] <= at["alvo"]:
        _fecho = f"alvo batido em {_esc(at['label'])} · {_fmt_hm(at['alvo'])}"
        _cor_f = "#1BAF7A"
    else:
        _fecho = (f"{_fmt_hm(at['real'] - at['alvo'])} acima do alvo em "
                  f"{_esc(at['label'])}")
        _cor_f = "#E34948"

    html = _grafico_barras_svg(
        [l["label"] for l in linhas],
        [l["ref"] for l in linhas], [l["alvo"] for l in linhas],
        label1="Referência", label2="Alvo do mês",
        line_vals=[l["real"] for l in linhas], linha_na_escala=True,
        cor1="#4A90D9", cor2_fn=lambda i: "#1BAF7A", cor2="#1BAF7A",
        cor_linha="#FFD400", label_linha="Realizado",
        fmt=_fmt_hm,
    )
    return html + (f'<div style="text-align:right;font-size:9px;color:{_cor_f};'
                   f'padding:0 4px 4px;">{_fecho}</div>')


def _tempo_analise(dados):
    """Tempo de busca de demanda por pessoa: {username: {"min","dias","n"}}.

    Sai de `execucoes_dia`, medido pela etiqueta — a mesma fonte da linha do
    tempo. O cartão dessa coluna quase nunca é concluído (fica alternando EM
    ANDAMENTO e INTERROMPIDO), então contar pelo concluído não veria nada.
    """
    por = {}
    for r in dados:
        for u, dias in ((r.get("execucoes_dia") or {})).items():
            for dia, lista in (dias or {}).items():
                trechos = [e for e in lista if e.get("analise")]
                if not trechos:
                    continue
                p = por.setdefault(u, {"min": 0.0, "dias": set(), "n": 0})
                p["min"] += sum(e["min"] for e in trechos)
                p["n"] += len(trechos)
                p["dias"].add(dia)
    return {u: {"min": v["min"], "dias": len(v["dias"]), "n": v["n"]}
            for u, v in por.items()}


def _chart_analise_demandas(dados, membros_ativos=None):
    """Quanto tempo cada um gastou procurando demanda, e a média geral.

    Esse tempo fica FORA da pontuação e fora do tempo de execução — é trabalho,
    mas não é execução de demanda, e somado junto faria a média de quem passou a
    manhã procurando parecer alta. Fora das contas, porém, ele sumia da tela: só
    aparecia no cabeçalho da linha do tempo de uma pessoa por vez. Aqui é a
    equipe inteira, que é onde dá para ver se a busca está comendo o dia.
    """
    membros_ativos = membros_ativos or {}
    dados_p = _tempo_analise(dados)
    if not dados_p:
        return ('<div style="padding:18px;text-align:center;font-size:11px;'
                'color:var(--ms-texto-sec);">Nenhum tempo registrado na coluna '
                'ANÁLISE DE DEMANDAS no período.</div>')

    CINZA = "#7A8B99"
    linhas = sorted(dados_p.items(), key=lambda kv: -kv[1]["min"])
    tot_min = sum(v["min"] for _, v in linhas)
    tot_dias = sum(v["dias"] for _, v in linhas)
    # A media geral e por PESSOA-DIA: somar o total e dividir pelo numero de
    # pessoas diria quanto cada uma gastou no periodo inteiro, que cresce com o
    # filtro. Por dia trabalhado o numero se compara entre mes e trimestre.
    media_dia = (tot_min / tot_dias) if tot_dias else 0.0
    maxm = max(v["min"] for _, v in linhas) or 1

    corpo = ""
    for u, v in linhas:
        nome = _esc(membros_ativos.get(u, u))
        md = v["min"] / v["dias"] if v["dias"] else 0.0
        corpo += (
            f'<div style="margin-bottom:9px;">'
            f'<div style="display:flex;justify-content:space-between;gap:10px;'
            f'font-size:11px;"><span>{nome}</span>'
            f'<span style="flex:none;font-weight:700;">{_fmt_hm(v["min"])}'
            f'<span style="font-weight:400;color:var(--ms-texto-sec);"> · '
            f'{_fmt_hm(md)}/dia em {v["dias"]} dia(s)</span></span></div>'
            f'<div style="height:7px;border-radius:4px;'
            f'background:var(--ms-metric-bd);margin-top:3px;overflow:hidden;">'
            f'<div style="height:100%;border-radius:4px;'
            f'width:{v["min"] / maxm * 100:.1f}%;background:{CINZA};">'
            f'</div></div></div>')

    return (
        f'<div style="display:flex;align-items:baseline;gap:10px;'
        f'flex-wrap:wrap;margin-bottom:12px;">'
        f'<span style="font-size:30px;font-weight:700;color:{CINZA};'
        f'line-height:1;">{_fmt_hm(media_dia)}</span>'
        f'<span style="font-size:11px;color:var(--ms-texto-sec);">'
        f'média geral por dia de busca</span>'
        f'<span style="margin-left:auto;font-size:11px;'
        f'color:var(--ms-texto-sec);">total do período '
        f'<b style="color:var(--ms-texto);">{_fmt_hm(tot_min)}</b></span>'
        f'</div>{corpo}')


def _chart_criacao_equipe(dados, membros_ativos=None):
    """Quantos cartões cada um abriu e quantos pontos eles geraram.

    Fica no painel coletivo, ao lado dos velocímetros: é a pergunta de quem
    olha a equipe inteira — quem alimenta a fila de demanda e com que peso.
    Cartão aberto pelo gestor ou por automação não entra; conta só a equipe
    cadastrada, o que é decidido em `placar_core.demandas_criadas`.
    """
    membros_ativos = membros_ativos or {}
    tot = {}
    for r in dados:
        for u, v in (r.get("demandas_criadas") or {}).items():
            a = tot.setdefault(u, {"n": 0, "pts": 0.0})
            a["n"] += v["n"]
            a["pts"] += v["pts"]

    _fim = max((r.get("filtro_mes") for r in dados if r.get("filtro_mes")),
               default=None)
    _corte = _pc.CORTE_CRIACAO
    if _fim and (_fim[0], _fim[1]) < (_corte.year, _corte.month):
        return ('<div style="padding:18px;text-align:center;font-size:11px;'
                'color:var(--ms-texto-sec);">A medição de cartões criados '
                f'começa em {_corte.strftime("%d/%m/%Y")}.</div>')
    if not tot:
        return ('<div style="padding:18px;text-align:center;font-size:11px;'
                'color:var(--ms-texto-sec);">Nenhum cartão criado pela equipe '
                'no período.</div>')

    AZUL, OURO = "#4A90D9", "#FFD700"
    linhas = sorted(tot.items(), key=lambda kv: -kv[1]["n"])
    n_tot = sum(v["n"] for _, v in linhas)
    p_tot = sum(v["pts"] for _, v in linhas)
    maxn = max(v["n"] for _, v in linhas) or 1

    corpo = ""
    for u, v in linhas:
        ppc = v["pts"] / v["n"] if v["n"] else 0.0
        corpo += (
            f'<div style="margin-bottom:9px;">'
            f'<div style="display:flex;justify-content:space-between;gap:10px;'
            f'font-size:11px;"><span>{_esc(membros_ativos.get(u, u))}</span>'
            f'<span style="flex:none;font-weight:700;">{v["n"]} cartões'
            f'<span style="font-weight:400;color:var(--ms-texto-sec);"> · '
            f'{_n_br(v["pts"])} pts · {_n_br(ppc)}/cartão</span></span></div>'
            f'<div style="height:7px;border-radius:4px;'
            f'background:var(--ms-metric-bd);margin-top:3px;overflow:hidden;">'
            f'<div style="height:100%;border-radius:4px;'
            f'width:{v["n"] / maxn * 100:.1f}%;background:{AZUL};"></div>'
            f'</div></div>')

    return (
        f'<div style="display:flex;align-items:baseline;gap:10px;'
        f'flex-wrap:wrap;margin-bottom:12px;">'
        f'<span style="font-size:30px;font-weight:700;color:{AZUL};'
        f'line-height:1;">{n_tot}</span>'
        f'<span style="font-size:11px;color:var(--ms-texto-sec);">'
        f'cartões criados no período</span>'
        f'<span style="margin-left:auto;font-size:11px;'
        f'color:var(--ms-texto-sec);">geraram '
        f'<b style="color:{OURO};">{_n_br(p_tot)} pts</b></span>'
        f'</div>{corpo}')


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


def _chart_ind_pts(meses, C=None, ritmo=None):
    """HTML/SVG: meta vs realizado individual + linha de delta.

    `ritmo` vem de `_ritmo_entrada`: com ele, a barra do mês corrente deixa de
    ficar vermelha só por ainda não ter chegado à meta — no dia 2 do mês
    ninguém chegou. Vermelho passa a ser "abaixo do ritmo que a meta pede".
    """
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
    # Com UM mes nao ha serie temporal: sao dois numeros, e o grafico de barras
    # vira dois retangulos gigantes lado a lado, ocupando meia tela para dizer
    # "2.500 e 2.818". A comparacao de um valor contra uma meta se le melhor
    # como um numero grande e uma barra de progresso.
    if len(meses) == 1:
        m = meses[0]
        # Verde bateu; amarelo a menos de 10% de bater; vermelho abaixo disso.
        # O corte era em 75%, que dava amarelo para quem estava a um quarto da
        # meta — longe demais para o mesmo sinal de quem esta quase la.
        if m["pct"] >= 100:
            cor = "#1BAF7A"
        elif ritmo and ritmo["decorridos"] > 0:
            cor = "#E34948" if ritmo["estado"] == "abaixo" else "#1BAF7A"
        else:
            cor = "#EDA100" if m["pct"] >= 90 else "#E34948"
        OURO = "#FFD700"   # so o que passa da meta
        falta = m["meta"] - m["pts"]
        # A escala guarda 12% de folga acima do maior dos dois, para o risco da
        # meta nunca encostar na ponta da trilha nem sumir na borda.
        _escala = max(m["pts"], m["meta"]) * 1.12 or 1
        _sobra = max(0, m["pts"] - m["meta"])
        if m["delta"] >= 0:
            fecho = "✅ meta batida · +%s pts" % f'{m["delta"]:,.0f}'
        elif ritmo and ritmo["decorridos"] > 0:
            _atras = ritmo["esperado"] - m["pts"]
            fecho = ("faltam %s pts · %s pts atrás do ritmo"
                     % (f'{falta:,.0f}', f'{_atras:,.0f}')
                     if ritmo["estado"] == "abaixo"
                     else "faltam %s pts · no ritmo" % f'{falta:,.0f}')
        else:
            fecho = "faltam %s pts" % f'{falta:,.0f}'
        return (
            f'<div style="padding:6px 2px 2px;">'
            f'<div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;">'
            f'<span style="font-size:38px;font-weight:700;color:{cor};line-height:1;">'
            f'{m["pts"]:,.0f}</span>'
            f'<span style="font-size:12px;color:var(--ms-texto-sec);">pts em {m["label"]}</span>'
            f'<span style="margin-left:auto;font-size:20px;font-weight:700;color:{cor};">'
            f'{m["pct"]:.1f}%</span></div>'
            # A barra nao para nos 100%: ela e desenhada numa escala com folga
            # acima da meta, e a meta vira um risco na trilha. Travada em 100%,
            # bater 112% e bater 100% davam a mesma barra cheia — so o texto
            # dizia a diferenca, e era preciso le-lo para ver que superou.
            f'<div style="height:16px;border-radius:8px;background:var(--ms-metric-bd);'
            f'margin:16px 0 6px;position:relative;">'
            # Ate a meta na cor do desempenho; o excedente em ouro. Uma barra de
            # cor unica mostra que passou, mas nao QUANTO passou sem medir a
            # distancia ate o risco — o trecho dourado e essa medida, pintada.
            f'<div style="position:absolute;left:0;top:0;height:100%;'
            f'width:{min(m["pts"], m["meta"])/_escala*100:.1f}%;background:{cor};'
            f'border-radius:8px {"0 0" if _sobra > 0 else "8px 8px"} 8px;"></div>'
            + (f'<div style="position:absolute;top:0;height:100%;'
               f'left:{m["meta"]/_escala*100:.1f}%;'
               f'width:{_sobra/_escala*100:.1f}%;background:{OURO};'
               f'border-radius:0 8px 8px 0;"></div>' if _sobra > 0 else "")
            +
            # O risco ultrapassa a trilha em cima e embaixo: contido nela, ele
            # se confundia com a emenda entre a cor do desempenho e o ouro.
            # Sobrando para fora, vira uma referencia, e nao uma divisa.
            f'<div style="position:absolute;top:-6px;bottom:-6px;'
            f'left:{m["meta"]/_escala*100:.1f}%;width:3px;margin-left:-1.5px;'
            f'border-radius:2px;background:var(--ms-texto);"></div></div>'
            f'<div style="position:relative;height:13px;margin-bottom:4px;">'
            f'<span style="position:absolute;left:{m["meta"]/_escala*100:.1f}%;'
            f'transform:translateX(-50%);font-size:9px;font-weight:700;'
            f'white-space:nowrap;color:var(--ms-texto);">▲ meta</span>'
            + (f'<span style="position:absolute;right:0;font-size:9px;'
               f'font-weight:700;color:{OURO};">+{_sobra:,.0f} pts acima</span>'
               if _sobra > 0 else "") + '</div>'
            f'<div style="display:flex;justify-content:space-between;font-size:11px;'
            f'color:var(--ms-texto-sec);">'
            f'<span>meta <b style="color:var(--ms-texto);">{m["meta"]:,.0f}</b> pts</span>'
            f'<span style="color:{cor};font-weight:600;">{fecho}</span></div>'
            f'<div style="margin-top:10px;padding-top:8px;border-top:1px solid var(--ms-divisor);'
            f'font-size:10.5px;color:var(--ms-texto-sec);font-style:italic;">'
            f'O comparativo mês a mês aparece no filtro de trimestre ou semestre.</div>'
            f'</div>'
        ).replace(",", ".")

    html = _grafico_barras_svg(
        labels, metas, pts, label1="Meta", label2="Realizado",
        line_vals=deltas, cor1="#4A90D9",
        cor2_fn=lambda i: "#1BAF7A",
        melhor_idx=bi, melhor_txt=melhor_txt,
    )
    return html + f'<div style="text-align:right;font-size:9px;color:#EDA100;padding:0 4px 4px;">Média: {avg_pct:.1f}%</div>'


def _ponto_por_membro(dados, users):
    """Ociosidade, tolerâncias e atrasos de cada membro no período de `dados`.

    Vivia dentro do resumo comparativo da equipe, então os velocímetros
    individuais não tinham como chegar nesses números — e mostravam
    "Aguardando ponto" para sempre, com ociosidade fixa em 0 e tolerâncias
    fixas em 100. Agora as duas telas leem da mesma conta.

    A ida ao RHiD é cacheada em `_pontualidade_rhid` (5 min), então chamar
    isto duas vezes na mesma renderização não custa uma segunda requisição.
    """
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
        _disp_mb   = {u: 0.0 for u in users}
        _atr_mb    = {u: 0   for u in users}
        _banco_mb  = {u: 0.0 for u in users}
        _minatr_mb = {u: 0.0 for u in users}

        for ym in _meses_ponto:
            if not ym:
                continue
            _ano, _mes = ym
            # Tempo em cards por membro (minutos). Agora vem medido por membro
            # pelas etiquetas do cartão — antes era o total do mês dividido em
            # partes iguais, o que dava ociosidade errada para todo mundo.
            _tc_user = _min_em_cartoes(dados, ym)
            _iv_user = {}
            for r in dados:
                if r.get("filtro_mes") == ym:
                    _iv_user.update(r.get("intervalos_membro") or {})
            _res = _rp.get_ociosidade_mes(_ano, _mes, _tc_user, _iv_user)
            for u in users:
                _ocio_mb[u]  += _res[u]["ociosidade_min"]
                _tol_mb[u]   += _res[u].get("qtd_tolerancias", 0)
                _dias_trab[u] += _res[u]["dias_trabalhados"]
                _dias_aus[u]  += _res[u]["dias_ausentes"]
                # Minutos disponiveis e atrasos de ponto saem DAQUI, da mesma
                # fonte da ociosidade. Antes o percentual era recalculado com
                # calcular_resumo_mes(), que le a planilha — e a equipe bate
                # ponto no relogio fisico, entao vinha zero: a divisao caia num
                # piso de 1 minuto e a tela mostrava 780400% de ociosidade.
                _disp_mb[u] += _res[u].get("horas_disp_min", 0.0)
                _atr_mb[u]  += _res[u].get("qtd_atrasos", 0)
                _minatr_mb[u] += _res[u].get("minutos_atraso", 0.0)
                # O banco ja vem acumulado da RHiD: o ultimo mes do periodo e o
                # saldo atual, e somar os meses contaria tudo de novo.
                _banco_mb[u] = _res[u].get("banco_min", 0.0)
            # Verifica se há dados reais de ponto
            if any(_res[u]["dias_trabalhados"] > 0 for u in users):
                _tem_ponto = True

        if _tem_ponto:
            _pct_ocio = {u: (_ocio_mb[u] / _disp_mb[u] * 100) if _disp_mb.get(u) else 0.0
                         for u in users}
    except Exception:
        _tem_ponto = False
        _ocio_mb   = {u: 0.0 for u in users}
        _tol_mb    = {u: 0.0 for u in users}
        _pct_ocio  = {u: 0.0 for u in users}
        _dias_trab = {u: 0   for u in users}
        _dias_aus  = {u: 0   for u in users}
        _disp_mb   = {u: 0.0 for u in users}
        _atr_mb    = {u: 0   for u in users}
        _banco_mb  = {u: 0.0 for u in users}
        _minatr_mb = {u: 0.0 for u in users}
    return {"tem_ponto": _tem_ponto, "ocio_mb": _ocio_mb, "tol_mb": _tol_mb,
            "pct_ocio": _pct_ocio, "dias_trab": _dias_trab, "dias_aus": _dias_aus,
            "disp_mb": _disp_mb, "atr_mb": _atr_mb,
            "banco_mb": _banco_mb, "minatr_mb": _minatr_mb}


LIMITE_OCIOSIDADE_PCT = 10.0   # teto de ocio do expediente, em %


def _barra_ociosidade(ponto, username, rotulo="", limite=LIMITE_OCIOSIDADE_PCT):
    """Ociosidade do período contra o teto, no formato da barra de pontuação.

    Aqui MENOS é melhor: o que a barra pinta é o tempo ocioso e o risco na
    trilha é o teto — passou do risco, a barra fica vermelha. É o contrário da
    barra de pontuação logo acima, e por isso o rótulo diz o teto por extenso.
    """
    if not (ponto and ponto.get("tem_ponto") and username):
        return ('<div style="padding:6px 2px;font-size:11px;'
                'color:var(--ms-texto-sec);">Sem registro de ponto no '
                'período.</div>')
    pct = float((ponto.get("pct_ocio") or {}).get(username, 0.0))
    cor = "#1BAF7A" if pct < limite else "#E34948"
    escala = max(pct, limite) * 1.35 or 1
    _x_lim = limite / escala * 100
    _x_pct = min(pct / escala * 100, 100)
    fecho = ("✅ dentro do limite" if pct < limite
             else f"{pct - limite:.1f} pontos acima do limite")
    return (
        f'<div style="padding:6px 2px 2px;">'
        f'<div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;">'
        f'<span style="font-size:38px;font-weight:700;color:{cor};line-height:1;">'
        f'{pct:.1f}%</span>'
        f'<span style="font-size:12px;color:var(--ms-texto-sec);">'
        f'do expediente{(" em " + _esc(rotulo)) if rotulo else ""}</span>'
        f'<span style="margin-left:auto;font-size:12px;color:var(--ms-texto-sec);">'
        f'máximo <b style="color:var(--ms-texto);">{limite:.0f}%</b></span></div>'
        f'<div style="height:16px;border-radius:8px;background:var(--ms-metric-bd);'
        f'margin:14px 0 6px;position:relative;">'
        f'<div style="position:absolute;left:0;top:0;height:100%;'
        f'width:{_x_pct:.1f}%;background:{cor};border-radius:8px;"></div>'
        f'<div style="position:absolute;top:-6px;bottom:-6px;left:{_x_lim:.1f}%;'
        f'width:3px;margin-left:-1.5px;border-radius:2px;'
        f'background:var(--ms-texto);"></div></div>'
        f'<div style="position:relative;height:13px;margin-bottom:4px;">'
        f'<span style="position:absolute;left:{_x_lim:.1f}%;'
        f'transform:translateX(-50%);font-size:9px;font-weight:700;'
        f'white-space:nowrap;color:var(--ms-texto);">▲ limite</span></div>'
        f'<div style="display:flex;justify-content:space-between;font-size:11px;'
        f'color:var(--ms-texto-sec);">'
        f'<span>tempo do expediente sem nenhum cartão EM ANDAMENTO</span>'
        f'<span style="color:{cor};font-weight:600;">{fecho}</span></div></div>')


def _chart_ind_indices(meses, ponto=None, username=None, max_tol=0,
                       max_atr=0, dados=None, cfg=None, C=None):
    """Os cinco critérios da meta, para a Coletiva e para a MAXX.

    Os seis velocímetros de antes mediam desempenho em geral — "Pontuação
    Batida", "Redução Tempo Médio", "Pontualidade Tarefa" — e nenhum deles é o
    que a meta do mês cobra. Agora são os cinco critérios cobrados, cada bloco
    com o limite do seu grupo: a MAXX pede mais em todos, e é amarela.

    A pontuação NÃO fica vermelha só por ainda não ter chegado ao piso: no dia
    2 do mês ninguém chegou. Ela é medida contra o ritmo — o pedaço do piso que
    os dias já corridos pedem — e só fica vermelha quem está abaixo dele.
    """
    dados = dados or []
    cfg = cfg or {}
    meses = meses or []
    n_meses = max(1, len(dados) or len(meses))

    pts = sum(m["pts"] for m in meses)
    meta = sum(m["meta"] for m in meses)
    pct_meta = (pts / meta * 100) if meta > 0 else 0.0
    advs = sum(int((r.get("cfg") or {}).get(f"adv_{username}", 0) or 0)
               for r in dados)
    uteis, decorridos = _dias_uteis_periodo(dados)

    real_exec = (_media_execucao_por_membro(dados) or {}).get(username)
    _ref_exec = float(cfg.get(f"exec_ref_{username}", 0) or 0) or 120.0
    alvo_exec = mc.meta_execucao(cfg, username, _ref_exec)["alvo"]

    tem_ponto = bool(ponto and ponto.get("tem_ponto") and username)
    tol = float((ponto.get("tol_mb") or {}).get(username, 0.0)) if tem_ponto else None
    atr = float((ponto.get("atr_mb") or {}).get(username, 0.0)) if tem_ponto else None

    VERM, AZUL = "#E34948", "#4A90D9"

    def _g_contagem(valor, limite, titulo, unidade, cor_ok):
        """Contagem contra um teto: o número no centro, o teto embaixo."""
        if valor is None:
            return _gauge_svg(0, AZUL, titulo, "sem ponto no período",
                              legend="depende do relógio de ponto", valor="—")
        if limite <= 0:
            return _gauge_svg(0 if valor == 0 else 100,
                              cor_ok if valor == 0 else VERM, titulo,
                              "sem limite definido", legend="—",
                              valor=f"{valor:.0f}")
        folga = limite - valor
        return _gauge_svg(min(valor / limite * 100, 100),
                          cor_ok if valor <= limite else VERM, titulo,
                          f"de {limite:.0f} {unidade}",
                          legend=(f"resta(m) {folga:.0f}" if folga >= 0
                                  else f"{-folga:.0f} além do limite"),
                          valor=f"{valor:.0f}")

    def _g_tempo(cor_ok):
        if real_exec is None:
            return _gauge_svg(0, AZUL, "Tempo de execução", "sem cartão medido",
                              legend="medido pela etiqueta EM ANDAMENTO",
                              valor="—")
        if not alvo_exec:
            return _gauge_svg(0, ADV_NEUTRO, "Tempo de execução",
                              "sem alvo no mês", legend="defina em Config. de Metas",
                              valor=f"{real_exec:.0f}")
        # O arco e a fracao do alvo que cabe no tempo real: quanto mais lento,
        # menor o arco. Aqui menos e melhor, e o arco precisa andar junto.
        _dif = real_exec - alvo_exec
        return _gauge_svg(min(alvo_exec / real_exec * 100, 100) if real_exec else 100,
                          cor_ok if real_exec <= alvo_exec else VERM,
                          "Tempo de execução", f"alvo {alvo_exec:.0f} min",
                          legend=(f"{-_dif:.0f} min abaixo do alvo" if _dif <= 0
                                  else f"{_dif:.0f} min acima do alvo"),
                          valor=f"{real_exec:.0f}")

    def _g_piso(piso, cor_ok):
        """O piso de pontuação, medido contra o RITMO e não contra o total.

        Vermelho aqui não é "ainda não chegou aos 80%" — é "não vai chegar
        neste passo". Quem está adiantado no dia 2 do mês tem 5% da meta e está
        bem, e um mostrador vermelho ali não informa nada.
        """
        if meta <= 0:
            return _gauge_svg(0, AZUL, "Pontuação da meta",
                              "meta individual não configurada",
                              legend="cadastre a meta do mês", valor="—")
        exigido = meta * piso / 100
        r = _ritmo_entrada(pts, exigido, uteis, decorridos)
        if pct_meta >= piso:
            cor, recado = cor_ok, "✅ piso atingido"
        elif r and r["estado"] == "abaixo":
            cor = VERM
            recado = f"{r['esperado'] - pts:,.0f} pts atrás do ritmo".replace(",", ".")
        elif r and r["restantes"] > 0:
            cor = cor_ok
            recado = f"no ritmo · faltam {exigido - pts:,.0f} pts".replace(",", ".")
        else:
            cor = VERM
            recado = f"faltaram {exigido - pts:,.0f} pts".replace(",", ".")
        return _gauge_svg(min(pct_meta / piso * 100, 100) if piso else 0, cor,
                          f"{piso:.0f}% da meta individual",
                          f"{pts:,.0f} de {exigido:,.0f} pts".replace(",", "."),
                          legend=recado, valor=f"{pct_meta:.0f}%")

    def _fila(g):
        """Os cinco lado a lado, numa linha só."""
        return (f'<div style="display:grid;grid-template-columns:repeat(5,1fr);'
                f'gap:6px 3px;padding:4px 0 12px;">{"".join(g)}</div>')

    def _bloco(titulo, cor_ok, piso, lim_tol, lim_atr, lim_adv):
        return (
            f'<div style="font-size:10px;font-weight:600;color:{cor_ok};'
            f'text-transform:uppercase;letter-spacing:.5px;margin:0 0 2px;">'
            f'{titulo}</div>'
            + _fila([
                _g_tempo(cor_ok),
                _g_contagem(tol, lim_tol, "Tolerâncias", "permitidas", cor_ok),
                _g_contagem(atr, lim_atr, "Atrasos", "permitidos", cor_ok),
                _g_piso(piso, cor_ok),
                _g_contagem(advs, lim_adv, "Advertências", "permitidas", cor_ok),
            ]))

    _tol_x = int(cfg.get("max_tol_maxx", 7) or 0) * n_meses
    _atr_x = int(cfg.get("max_atr_maxx", 5) or 0) * n_meses
    _adv_n = int(cfg.get("max_adv_normal", 2) or 0) * n_meses
    _adv_x = int(cfg.get("max_adv_maxx", 1) or 0) * n_meses
    _piso_n = int(cfg.get("min_contrib_normal", 80) or 0)
    _piso_x = int(cfg.get("min_contrib_maxx", 100) or 0)

    return (_bloco("📋 Meta Coletiva", "#1BAF7A", _piso_n,
                   float(max_tol or 0), float(max_atr or 0), _adv_n)
            + _bloco("⭐ Meta MAXX", "#FFD700", _piso_x,
                     float(_tol_x), float(_atr_x), _adv_x))


def _entregas_do_membro(dados, username):
    """Junta as entregas da pessoa em todos os meses do periodo.

    Devolve ({dia: {"qtd","pts"}}, {coluna: {"qtd","pts"}}). Vem de
    placar_core._processar, que registra a data de conclusao e a coluna de cada
    cartao entregue.
    """
    dias, cols = {}, {}
    for r in dados:
        e = (r.get("entregas_membro") or {}).get(username) or {}
        for dia, v in (e.get("dias") or {}).items():
            d = dias.setdefault(dia, {"qtd": 0, "pts": 0.0})
            d["qtd"] += v["qtd"]; d["pts"] += v["pts"]
        for col, v in (e.get("colunas") or {}).items():
            c = cols.setdefault(col, {"qtd": 0, "pts": 0.0})
            c["qtd"] += v["qtd"]; c["pts"] += v["pts"]
    return dias, cols


def _chart_curva_execucao(dados, username, por_mes=False):
    """Barras de entregas por dia do mes — ou por mes, no trimestre/semestre.

    Dia sem entrega aparece como um tracinho no zero e nao como um buraco: e a
    sequencia completa que mostra se o ritmo e constante ou se junta tudo numa
    ponta do mes. Some com os dias vazios e a curva mente.
    """
    dias, _ = _entregas_do_membro(dados, username)
    if not dias and not por_mes:
        return ('<div style="padding:24px;text-align:center;font-size:11px;'
                'color:var(--ms-texto-sec);">Nenhuma entrega registrada no período</div>')

    if por_mes:
        agrup = {}
        for dia, v in dias.items():
            agrup.setdefault(dia[:7], 0)
            agrup[dia[:7]] += v["qtd"]
        # Todos os meses do periodo, inclusive os zerados
        rotulos, vals = [], []
        for r in dados:
            ym = r.get("filtro_mes")
            if not ym:
                continue
            chave = f"{ym[0]:04d}-{ym[1]:02d}"
            rotulos.append(r.get("label", chave))
            vals.append(agrup.get(chave, 0))
        titulo_x = "mês"
    else:
        ym = next((r.get("filtro_mes") for r in dados if r.get("filtro_mes")), None)
        if not ym:
            return ('<div style="padding:24px;text-align:center;font-size:11px;'
                    'color:var(--ms-texto-sec);">Sem mês definido</div>')
        ano, mes = ym
        ultimo = calendar.monthrange(ano, mes)[1]
        rotulos = [str(d) for d in range(1, ultimo + 1)]
        vals = [dias.get(f"{ano:04d}-{mes:02d}-{d:02d}", {}).get("qtd", 0)
                for d in range(1, ultimo + 1)]
        titulo_x = "dia"

    if not vals:
        return ('<div style="padding:24px;text-align:center;font-size:11px;'
                'color:var(--ms-texto-sec);">Sem dados no período</div>')

    W, H = 620, 170
    ml, mr, mt, mb = 30, 12, 16, 30
    iw, ih = W - ml - mr, H - mt - mb
    topo = max(vals + [1])
    media = sum(vals) / len(vals)
    bw = iw / len(vals)
    def y(v): return mt + ih - (v / topo * ih)

    partes = []
    for i in range(4):
        yg = mt + ih * i / 3
        partes.append(
            f'<line x1="{ml}" y1="{yg:.1f}" x2="{W-mr}" y2="{yg:.1f}" '
            f'stroke="var(--ms-divisor,#333)" stroke-width="0.5"/>'
            f'<text x="{ml-4}" y="{yg+3:.1f}" text-anchor="end" font-size="7.5" '
            f'fill="var(--ms-texto-sec,#888)">{topo*(3-i)/3:.0f}</text>')
    for i, v in enumerate(vals):
        x = ml + i * bw + 1
        larg = max(bw - 2, 1)
        if v > 0:
            partes.append(
                f'<rect x="{x:.1f}" y="{y(v):.1f}" width="{larg:.1f}" '
                f'height="{mt+ih-y(v):.1f}" rx="2" fill="#4A90D9">'
                f'<title>{rotulos[i]}: {v} cartão(ões)</title></rect>')
        else:
            partes.append(
                f'<rect x="{x:.1f}" y="{mt+ih-1.5:.1f}" width="{larg:.1f}" height="1.5" '
                f'fill="var(--ms-divisor,#444)"><title>{rotulos[i]}: nenhum</title></rect>')
        passo = 1 if len(vals) <= 12 else 5
        if i == 0 or (i + 1) % passo == 0:
            partes.append(
                f'<text x="{x+larg/2:.1f}" y="{H-12}" text-anchor="middle" '
                f'font-size="7.5" fill="var(--ms-texto-sec,#888)">{rotulos[i]}</text>')
    partes.append(
        f'<line x1="{ml}" y1="{y(media):.1f}" x2="{W-mr}" y2="{y(media):.1f}" '
        f'stroke="#EDA100" stroke-width="1.5" stroke-dasharray="4,3"/>'
        f'<text x="{W-mr}" y="{y(media)-4:.1f}" text-anchor="end" font-size="7.5" '
        f'font-weight="700" fill="#EDA100">média {media:.1f}/{titulo_x}</text>')
    return (f'<div style="width:100%;overflow:hidden;padding:4px 0;">'
            f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
            f'style="width:100%;">' + "".join(partes) + '</svg></div>')


def _atividade_do_membro(dados, username):
    """O dia a dia da pessoa: o que ela tocou e o que ela entregou.

    Devolve {dia: {"iniciados","concluidos","interrompidos","ativos","minutos"}}.

    São duas fontes, de propósito. O concluído vem de `entregas_membro`, apurado
    pela movimentação de coluna — a mesma origem da pontuação, para as telas não
    discordarem entre si. O resto vem de `atividade_dia`, apurado pelas
    etiquetas. Um dia sem entrega não é um dia sem trabalho, e até agora só o
    primeiro tinha como aparecer.
    """
    dias = {}

    def _reg(dia):
        return dias.setdefault(dia, {"iniciados": 0, "concluidos": 0,
                                     "interrompidos": 0, "ativos": 0,
                                     "minutos": 0.0})

    for r in dados:
        for dia, v in ((r.get("atividade_dia") or {}).get(username) or {}).items():
            reg = _reg(dia)
            reg["iniciados"] += v.get("iniciados", 0)
            reg["interrompidos"] += v.get("interrompidos", 0)
            reg["ativos"] += v.get("ativos", 0)
            reg["minutos"] += float(v.get("minutos", 0) or 0)
        e = (r.get("entregas_membro") or {}).get(username) or {}
        for dia, v in (e.get("dias") or {}).items():
            _reg(dia)["concluidos"] += v.get("qtd", 0)
    return dias


def _estados_por_dia(dados, username):
    """O estado FINAL de cada cartão em cada dia. Um cartão, um estado.

    A pergunta "quantos ficaram em andamento" só faz sentido se concluído e
    interrompido saírem da conta: um cartão entregue às 17h esteve em andamento
    o dia todo, mas no fim do dia ele está entregue, e contá-lo nas duas linhas
    fazia a mesma demanda aparecer duas vezes com estados que se excluem.

    Concluído vem de `entregas_membro` — movimentação de coluna, a mesma fonte
    da pontuação — e não da etiqueta: tirar EM ANDAMENTO não é entregar. O
    resto sai do último trecho do dia: terminou com etiqueta de interrupção, é
    interrompido; qualquer outra coisa, ainda estava em andamento.

    Devolve {dia: {"por_card": {card_id: estado}, "andamento": n,
                   "concluido": n, "interrompido": n}}.
    """
    dias = {}

    def _reg(dia):
        return dias.setdefault(dia, {"por_card": {}, "ultimo": {},
                                     "andamento": 0, "concluido": 0,
                                     "interrompido": 0})

    for r in dados:
        for dia, lista in ((r.get("execucoes_dia") or {}).get(username) or {}).items():
            reg = _reg(dia)
            for e in sorted(lista, key=lambda x: x["ini"]):
                cid = e.get("card_id") or e.get("card")
                reg["ultimo"][cid] = e.get("fim_tipo")
        e_m = (r.get("entregas_membro") or {}).get(username) or {}
        for dia, v in (e_m.get("dias") or {}).items():
            reg = _reg(dia)
            for cid in (v.get("ids") or []):
                reg["por_card"][cid] = "concluido"

    for reg in dias.values():
        for cid, fim in reg["ultimo"].items():
            if reg["por_card"].get(cid) == "concluido":
                continue
            reg["por_card"][cid] = ("interrompido" if fim == "interrompido"
                                    else "andamento")
        for est in reg["por_card"].values():
            reg[est] = reg.get(est, 0) + 1
        reg.pop("ultimo", None)
    return dias


def _execucoes_do_membro(dados, username):
    """{dia: [{"card","ini","fim","min","tipo"}]} da pessoa, no período todo."""
    dias = {}
    for r in dados:
        for dia, lista in ((r.get("execucoes_dia") or {}).get(username) or {}).items():
            dias.setdefault(dia, []).extend(lista)
    for lista in dias.values():
        lista.sort(key=lambda e: e["ini"])
    return dias


def _expediente(username):
    """(inicio, fim) do expediente da pessoa, em minutos desde a meia-noite."""
    h = _pc.horario_de(username)
    return (h["entrada"].hour * 60 + h["entrada"].minute,
            h["fim"].hour * 60 + h["fim"].minute)


def _fmt_hhmm(minutos):
    return f"{int(minutos)//60:02d}:{int(minutos)%60:02d}"


# A cor de cada estado do cartão, uma só para o gráfico inteiro: o bloco na
# linha do tempo e a contagem embaixo dele falam da mesma coisa e agora falam na
# mesma cor. `fim_tipo` vem de placar_core.intervalos_do_cartao.
COR_ANDAMENTO   = "#EDA100"   # amarelo
COR_CONCLUIDO   = "#1BAF7A"   # verde
COR_INTERROMPIDO = "#8B5CF6"  # roxo — inclui FIM DE EXPEDIENTE
# O estado final do cartao no dia (de _estados_por_dia) na cor dele.
CORES_EST_DIA = {}   # preenchido logo abaixo, depois das constantes de cor

CORES_ESTADO = {
    "encerrado":    COR_CONCLUIDO,
    "interrompido": COR_INTERROMPIDO,
    # Ainda correndo, ou cortado na virada do dia, ou o trecho fechou e o
    # trabalho seguiu: nos três o cartão continua EM ANDAMENTO.
    "aberto":       COR_ANDAMENTO,
    "virada":       COR_ANDAMENTO,
    "seguiu":       COR_ANDAMENTO,
}

CORES_EST_DIA.update({"concluido": COR_CONCLUIDO,
                      "interrompido": COR_INTERROMPIDO,
                      "andamento": COR_ANDAMENTO})

# Como o estado do dia se chama na ficha. Vem antes do estado do TRECHO: o que
# interessa a quem passa o mouse e em que pe o cartao ficou naquele dia.
ESTADO_DIA_NOME = {"concluido": "CONCLUÍDO no dia",
                   "interrompido": "INTERROMPIDO",
                   "andamento": "EM ANDAMENTO"}

ESTADO_NOME = {"encerrado": "CONCLUÍDO", "interrompido": "INTERROMPIDO",
               "aberto": "EM ANDAMENTO (aberto agora)",
               "virada": "EM ANDAMENTO (virou o dia)",
               "seguiu": "EM ANDAMENTO"}


# A ficha que aparece com o mouse em cima de um bloco.
#
# Ela e HTML sobreposto ao SVG, e nao um <g> dentro dele. Duas tentativas
# falharam na tela antes desta, e o motivo esta no proprio Streamlit: markdown
# com HTML nao passa por sanitizador -- passa por rehypeRaw e e RECONSTRUIDO
# elemento a elemento pelo React. O que nao e HTML ou SVG comum se perde no
# caminho: o <style> dentro do <svg> e o <set> do SMIL sumiram, e sem eles as
# fichas ficavam todas visiveis de uma vez, empilhadas sobre o grafico.
#
# O que sobra e o que este app ja prova funcionar: style= inline em cada
# elemento, e a folha de estilo do app.py. Por isso a regra de :hover mora la,
# e aqui cada ficha nasce com display:none INLINE. Se a regra sumir, a ficha
# fica escondida -- que e o comportamento seguro -- e o <title> do bloco ainda
# responde. O contrario, que era o caso, e a tela coberta de cartoes.
#
# HTML tambem resolve a ordem de pintura de graca: as fichas vem depois do
# <svg> no documento, entao ficam por cima dele sem precisar de z-index.
FICHA_L = 246


def _ficha_exec(e, tot, cx_pct, cy_pct, cor, esq, estado=None):
    """Resumo de uma execução, sobreposto ao gráfico: cartão, coluna e tempo.

    As coordenadas vêm em porcentagem do quadro: o SVG tem viewBox e largura
    100%, então porcentagem é a única medida que acompanha o gráfico quando a
    coluna do Streamlit muda de largura.
    """
    def _corta(t, n):
        t = _esc(t)
        return t if len(t) <= n else t[:n - 1] + "…"

    linhas = [
        f'<div style="font-size:11px;font-weight:700;color:#e8e6e1;'
        f'margin-bottom:2px;">{_corta(e["card"], 44)}</div>']
    col = _corta(e.get("lista", ""), 38)
    if col:
        linhas.append(f'<div style="font-size:9px;color:#9aa09c;">{col}</div>')
    linhas.append(
        f'<div style="font-size:10px;color:{cor};margin-top:3px;">'
        f'{e["ini"]:%H:%M} → {e["fim"]:%H:%M} · {_fmt_hm(e["min"])} de execução'
        f'</div>')
    linhas.append(
        f'<div style="font-size:9px;font-weight:700;color:{cor};margin-top:2px;">'
        f'{ESTADO_DIA_NOME.get(estado) or ESTADO_NOME.get(e.get("fim_tipo"), "EM ANDAMENTO")}'
        + (' · filmagem' if e.get("tipo") == "filmagem" else '')
        + (' · busca de demanda' if e.get("analise") else '') + '</div>')
    if tot["n"] > 1:
        linhas.append(
            f'<div style="font-size:9px;color:#EDA100;margin-top:2px;">'
            f'total do cartão no dia {_fmt_hm(tot["min"])} em {tot["n"]} trechos'
            f'</div>')
    lado = (f'right:{100 - cx_pct:.2f}%;margin-right:8px;' if esq
            else f'left:{cx_pct:.2f}%;margin-left:8px;')
    return (
        f'<div class="ltd-f" style="display:none;position:absolute;'
        f'top:{cy_pct:.2f}%;{lado}transform:translateY(-50%);'
        f'width:{FICHA_L}px;max-width:60%;background:#12140f;'
        f'border:1px solid {cor};border-radius:6px;padding:8px 10px;'
        f'pointer-events:none;z-index:5;line-height:1.35;">'
        + "".join(linhas) + '</div>')


def _chart_linha_do_tempo(dados, username):
    """Quando cada cartão foi executado, dia a dia, no relógio do expediente.

    Um gráfico só, que responde as três perguntas do dia: a que horas o trabalho
    aconteceu, quanto durou cada cartão e quantos foram iniciados, concluídos e
    interrompidos. Eram dois gráficos separados, e o de cima repetia em barra o
    que este mostra em bloco.

    O eixo do relógio corre de baixo para cima: o início do expediente embaixo,
    o fim em cima. É como se lê um dia que enche — a coluna sobe com as horas
    trabalhadas em vez de descer.

    A escala é o expediente CONTRATADO da pessoa (Myrella 08:45–17:45, os demais
    09:00–18:00, de placar_core.HORARIOS). Execução fora dele não é escondida: o
    eixo se estica para caber e a faixa de fora fica com outro fundo.
    """
    dias_exec = _execucoes_do_membro(dados, username)
    atividade = _atividade_do_membro(dados, username)
    ym = next((r.get("filtro_mes") for r in dados if r.get("filtro_mes")), None)
    if not ym:
        return ('<div style="padding:24px;text-align:center;font-size:11px;'
                'color:var(--ms-texto-sec);">Sem mês definido</div>')
    ano, mes = ym
    ultimo = calendar.monthrange(ano, mes)[1]
    pref = f"{ano:04d}-{mes:02d}-"

    exp_ini, exp_fim = _expediente(username)
    eixo_ini, eixo_fim = exp_ini, exp_fim
    total_min, n_exec = 0.0, 0
    min_analise, n_analise = 0.0, 0
    for dia, lista in dias_exec.items():
        if not dia.startswith(pref):
            continue
        for e in lista:
            m_ini = e["ini"].hour * 60 + e["ini"].minute
            m_fim = e["fim"].hour * 60 + e["fim"].minute
            if m_fim <= m_ini:            # terminou na virada do dia
                m_fim = 24 * 60
            eixo_ini = min(eixo_ini, m_ini)
            eixo_fim = max(eixo_fim, m_fim)
            # Busca de demanda entra no desenho e fica fora da conta: ela e
            # trabalho, mas nao e execucao de demanda, e somar as duas faria o
            # tempo medio de quem passou a manha procurando parecer alto.
            if e.get("analise"):
                n_analise += 1
                min_analise += e["min"]
                continue
            total_min += e["min"]
            n_exec += 1
    eixo_ini = (eixo_ini // 30) * 30
    eixo_fim = -(-eixo_fim // 30) * 30
    span = max(eixo_fim - eixo_ini, 60)

    # Os tres estados da etiqueta, com o nome que eles tem no Trello e a cor de
    # cada um. "iniciou/concluiu/parou" descrevia o evento; o que se procura
    # aqui e o ESTADO do cartao no dia. Interrompido soma FIM DE EXPEDIENTE:
    # `eventos_de_trabalho` ja trata as duas como interrupcao, porque as duas
    # param o relogio do mesmo jeito.
    # Um cartao, um estado. As tres linhas se excluem: o que fechou nao conta
    # como em andamento, o que foi interrompido nao conta como fechado.
    estados = _estados_por_dia(dados, username)
    LINHAS = [("andamento", "EM ANDAMENTO", COR_ANDAMENTO),
              ("concluido", "CONCLUÍDO", COR_CONCLUIDO),
              ("interrompido", "INTERROMPIDO", COR_INTERROMPIDO)]
    W = 980
    # Margem maior a esquerda: "EM ANDAMENTO" nao cabia nos 52px que bastavam
    # para "iniciou".
    ml, mr, mt = 78, 10, 12
    ALT_REL, ALT_EIXO, ALT_LINHA = 300, 15, 15
    H = mt + ALT_REL + ALT_EIXO + ALT_LINHA * len(LINHAS) + 8
    iw = W - ml - mr
    bw = iw / ultimo
    base = mt + ALT_REL

    def y(m):
        """Hora -> altura. Invertido: mais tarde é mais alto na tela."""
        return base - (m - eixo_ini) / span * ALT_REL

    def faixa(m1, m2, cor, rotulo=""):
        y1, y2 = y(m2), y(m1)          # m2 é mais tarde, logo mais alto
        out = (f'<rect x="{ml}" y="{y1:.1f}" width="{iw}" '
               f'height="{y2-y1:.1f}" fill="{cor}"/>')
        if rotulo:
            out += (f'<text x="{ml+3}" y="{y2-3:.1f}" font-size="7" '
                    f'fill="#EDA10099">{rotulo}</text>')
        return out

    partes, sobre = [], []
    # Fora do expediente com outro fundo, e o almoco marcado: um bloco as 13h45
    # nao quer dizer a mesma coisa que um as 10h.
    if eixo_ini < exp_ini:
        partes.append(faixa(eixo_ini, exp_ini, "#00000030"))
    if eixo_fim > exp_fim:
        partes.append(faixa(exp_fim, eixo_fim, "#00000030"))
    _alm_i = _pc.ALMOCO[0].hour * 60 + _pc.ALMOCO[0].minute
    _alm_f = _pc.ALMOCO[1].hour * 60 + _pc.ALMOCO[1].minute
    partes.append(faixa(_alm_i, _alm_f, "#EDA10014", "almoço"))

    hora = -(-eixo_ini // 60) * 60
    while hora <= eixo_fim:
        partes.append(
            f'<line x1="{ml}" y1="{y(hora):.1f}" x2="{W-mr}" y2="{y(hora):.1f}" '
            f'stroke="var(--ms-divisor,#333)" stroke-width="0.5"/>'
            f'<text x="{ml-5}" y="{y(hora)+3:.1f}" text-anchor="end" '
            f'font-size="7.5" fill="var(--ms-texto-sec,#888)">'
            f'{_fmt_hhmm(hora)}</text>')
        hora += 60

    hoje = datetime.now().date()
    medias, parados = [], []
    for d in range(1, ultimo + 1):
        data = datetime(ano, mes, d).date()
        x = ml + (d - 1) * bw
        chave = f"{pref}{d:02d}"
        lista = dias_exec.get(chave, [])
        est = estados.get(chave) or {"por_card": {}, "andamento": 0,
                                     "concluido": 0, "interrompido": 0}
        util = data.weekday() < 5 and data <= hoje
        parado = util and not lista and not est["por_card"]
        if data.weekday() >= 5:
            partes.append(f'<rect x="{x:.1f}" y="{mt}" width="{bw:.1f}" '
                          f'height="{ALT_REL}" fill="#00000022"/>')
        elif parado:
            # O dia parado nao pode ser um vazio igual ao domingo: ele e o
            # achado que esta tela existe para mostrar.
            parados.append(str(d))
            partes.append(f'<rect x="{x:.1f}" y="{mt}" width="{bw:.1f}" '
                          f'height="{ALT_REL}" fill="#E3494822"/>')

        por_card = {}
        for e in lista:
            v = por_card.setdefault(e["card"], {"min": 0.0, "n": 0})
            v["min"] += e["min"]; v["n"] += 1
        for e in lista:
            m_ini = e["ini"].hour * 60 + e["ini"].minute
            m_fim = e["fim"].hour * 60 + e["fim"].minute
            # 24:00 e para o pedaco que morre na virada do dia -- e SO para
            # ele. A regra antiga era "fim <= inicio", e ela pegava junto o
            # trecho que comeca e acaba no mesmo minuto: bastava alguem entrar
            # no cartao segundos depois de por a etiqueta para o risco de meio
            # minuto virar um bloco da altura do dia inteiro, das 16h as 24h.
            if e["fim"].date() > e["ini"].date():
                m_fim = 24 * 60
            elif m_fim <= m_ini:
                m_fim = m_ini + 1
            y_topo, y_base = y(m_fim), y(m_ini)   # fim em cima, inicio embaixo
            alt = max(y_base - y_topo, 2.2)
            y_topo = y_base - alt
            # A cor do bloco e a da ETIQUETA com que ele terminou, a mesma das
            # contagens embaixo. Antes era o tipo de trabalho (andamento,
            # filmagem), e assim o cartao entregue e o esquecido aberto ficavam
            # da mesma cor — que e justamente a diferenca que se procura aqui.
            # A cor e o estado do CARTAO naquele dia, e nao o de cada trecho.
            # Um cartao entregue as 17h41 tem tres trechos no dia, e antes so o
            # ultimo ficava verde: os anteriores saiam amarelos, e a mesma
            # demanda aparecia como em andamento e concluida ao mesmo tempo.
            cor = CORES_EST_DIA.get(
                est["por_card"].get(e.get("card_id") or e.get("card")),
                COR_ANDAMENTO)
            # Filmagem e busca de demanda continuam distintas, agora pelo
            # contorno: a cor de dentro ficou reservada para o estado.
            if e.get("analise"):
                traco, tracejado = "#7A8B99", "3,2"
            elif e.get("tipo") == "filmagem":
                traco, tracejado = "#FFFFFF", "2,2"
            else:
                traco, tracejado = None, None
            _est_card = est["por_card"].get(e.get("card_id") or e.get("card"))
            _est_nome = (ESTADO_DIA_NOME.get(_est_card)
                         or ESTADO_NOME.get(e.get("fim_tipo"), "EM ANDAMENTO"))
            bx, blarg = x + 2.5, max(bw - 5, 2)
            tot = por_card.get(e["card"], {"min": e["min"], "n": 1})
            partes.append(
                f'<rect x="{bx:.1f}" y="{y_topo:.1f}" width="{blarg:.1f}" '
                f'height="{alt:.1f}" rx="2" fill="{cor}" fill-opacity="0.85"'
                + (f' stroke="{traco}" stroke-width="1" '
                   f'stroke-dasharray="{tracejado}"' if traco else "") + '>'
                # O <title> e a rede de seguranca: se a folha de estilo do app
                # nao chegar, a ficha fica escondida e ele responde sozinho.
                f'<title>{_esc(e["card"])} · {e["ini"]:%H:%M} → '
                f'{e["fim"]:%H:%M} · {_fmt_hm(e["min"])} · '
                f'{_est_nome}</title></rect>'
                # Marcadores: verde embaixo, onde comecou; vermelho em cima,
                # onde terminou. O traco passa dos lados do bloco, senao a borda
                # de um bloco encostado no seguinte vira uma emenda so e os dois
                # viram um cartao unico e longo.
                f'<line x1="{bx-2:.1f}" y1="{y_base:.1f}" '
                f'x2="{bx+blarg+2:.1f}" y2="{y_base:.1f}" '
                f'stroke="#1BAF7A" stroke-width="1.4"/>'
                f'<line x1="{bx-2:.1f}" y1="{y_topo:.1f}" '
                f'x2="{bx+blarg+2:.1f}" y2="{y_topo:.1f}" '
                f'stroke="#E34948" stroke-width="1.4"/>')
            # Area de mouse e ficha, em porcentagem do quadro: o SVG tem viewBox
            # e largura 100%, entao porcentagem e a unica medida que acompanha o
            # grafico quando a coluna do Streamlit muda de largura. A area e
            # mais alta que o bloco -- um bloco de 20 minutos tem 6px, e cacar
            # 6px com o ponteiro faz a tela parecer que nao responde.
            cx_pct = (bx + blarg / 2) / W * 100
            cy_pct = (y_topo + alt / 2) / H * 100
            sobre.append(
                f'<div class="ltd-hit" style="position:absolute;'
                f'left:{bx / W * 100:.3f}%;top:{(y_topo - 3) / H * 100:.3f}%;'
                f'width:{blarg / W * 100:.3f}%;'
                f'height:{(alt + 6) / H * 100:.3f}%;"></div>'
                + _ficha_exec(e, tot, cx_pct, cy_pct, cor, cx_pct > 55,
                              estado=_est_card))
        _exec_dia = [e for e in lista if not e.get("analise")]
        if _exec_dia:
            medias.append(sum(e["min"] for e in _exec_dia) / len(_exec_dia))
        passo = 1 if ultimo <= 12 else 2
        if d == 1 or d % passo == 0:
            partes.append(
                f'<text x="{x+bw/2:.1f}" y="{base+11:.1f}" text-anchor="middle" '
                f'font-size="7" fill="var(--ms-texto-sec,#888)">{d}</text>')
        _exec_dia = [e for e in lista if not e.get("analise")]

    # As tres contagens embaixo do eixo. Vinham de um grafico separado que
    # repetia em barra o tempo que os blocos ja mostram; so as contagens tinham
    # informacao propria, e e delas que este rodape e feito.
    for li, (chave_c, rot, cor_c) in enumerate(LINHAS):
        yl = base + ALT_EIXO + li * ALT_LINHA
        partes.append(
            f'<text x="{ml-5}" y="{yl+8:.1f}" text-anchor="end" font-size="6.4" '
            f'font-weight="700" letter-spacing="0.2" '
            f'fill="{cor_c}">{rot}</text>')
        for d in range(1, ultimo + 1):
            v = (estados.get(f"{pref}{d:02d}") or {}).get(chave_c, 0)
            x = ml + (d - 1) * bw + 1
            larg = max(bw - 2, 1)
            if v > 0:
                partes.append(
                    f'<rect x="{x:.1f}" y="{yl:.1f}" width="{larg:.1f}" '
                    f'height="{ALT_LINHA-3:.1f}" rx="2" fill="{cor_c}" '
                    f'fill-opacity="{min(0.35 + v * 0.2, 1):.2f}"/>'
                    f'<text x="{x+larg/2:.1f}" y="{yl+9:.1f}" '
                    f'text-anchor="middle" font-size="7.5" font-weight="700" '
                    f'fill="#12140f">{v}</text>')
            else:
                partes.append(
                    f'<rect x="{x:.1f}" y="{yl:.1f}" width="{larg:.1f}" '
                    f'height="{ALT_LINHA-3:.1f}" rx="2" '
                    f'fill="var(--ms-divisor,#3a3a3a)" fill-opacity="0.45"/>')

    media_geral = total_min / n_exec if n_exec else 0
    media_dia = sum(medias) / len(medias) if medias else 0
    cab = (
        f'<div style="display:flex;gap:16px;flex-wrap:wrap;align-items:baseline;'
        f'font-size:11px;color:var(--ms-texto-sec);margin-bottom:4px;">'
        f'<span>Expediente <b style="color:var(--ms-texto);">'
        f'{_fmt_hhmm(exp_ini)}–{_fmt_hhmm(exp_fim)}</b></span>'
        f'<span><b style="color:var(--ms-texto);">{n_exec}</b> execuções</span>'
        f'<span>total <b style="color:var(--ms-texto);">{_fmt_hm(total_min)}</b></span>'
        f'<span>média por cartão <b style="color:#4A90D9;">'
        f'{_fmt_hm(media_geral)}</b></span>'
        f'<span>média diária <b style="color:#4A90D9;">{_fmt_hm(media_dia)}</b></span>'
        + (f'<span style="color:#7A8B99;">busca de demanda '
           f'<b>{_fmt_hm(min_analise)}</b> em {n_analise} trecho(s) · '
           f'fora da média</span>' if n_analise else "")
        + '</div>')
    leg = (f'<div style="font-size:9px;color:var(--ms-texto-sec);margin-top:3px;">'
           f'cor do bloco = estado do cartão no dia · '
           f'<span style="color:{COR_ANDAMENTO};font-weight:700;">■</span> '
           f'EM ANDAMENTO · '
           f'<span style="color:{COR_CONCLUIDO};font-weight:700;">■</span> '
           f'CONCLUÍDO · '
           f'<span style="color:{COR_INTERROMPIDO};font-weight:700;">■</span> '
           f'INTERROMPIDO ou FIM DE EXPEDIENTE'
           f'<br>contorno branco tracejado = filmagem · contorno cinza = busca '
           f'de demanda · fundo escuro = fora do expediente ou fim de semana · '
           f'passe o mouse num bloco para ver o cartão'
           f'<br>as três linhas embaixo contam CARTÕES, nas mesmas cores, e '
           f'cada cartão entra em uma só: a do estado em que ele fechou o dia'
           f'</div>')
    if parados:
        leg += (f'<div style="margin-top:4px;font-size:10px;color:#E34948;'
                f'font-weight:700;">🚩 {len(parados)} dia(s) útil(eis) sem '
                f'nenhum registro: {", ".join(parados)}</div>')
    if n_exec == 0:
        leg = ('<div style="font-size:10px;color:var(--ms-texto-sec);'
               'margin-top:3px;">Nenhuma execução registrada no mês.</div>') + leg
    # O quadro e position:relative para as fichas se posicionarem por ele. Elas
    # vem DEPOIS do <svg> no documento, e por isso ficam por cima dele sem
    # z-index nenhum -- HTML resolve de graca o que no SVG exigia truque.
    return (f'<div style="width:100%;padding:4px 0;">{cab}'
            f'<div style="position:relative;width:100%;">'
            f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
            f'style="width:100%;display:block;">' + "".join(partes) + '</svg>'
            + "".join(sobre) + f'</div>{leg}</div>')


def _chart_atividade_dia(dados, username, por_mes=False):
    """Dia a dia: iniciados, concluídos, interrompidos e tempo de execução.

    A curva de execução mostra o que foi ENTREGUE. Um dia sem entrega pode ser
    um dia de cartão longo ou um dia em que ninguém encostou em nada, e os dois
    apareciam iguais — zero. Aqui a barra é o tempo de execução do dia, e a
    grade embaixo dá as três contagens, para separar um caso do outro.

    Dia útil já passado, sem tempo nenhum e sem cartão nenhum tocado, sai em
    vermelho. Fim de semana e dia ainda por vir não são acusados.
    """
    dias = _atividade_do_membro(dados, username)
    # Os tres estados vem da mesma conta da linha do tempo: um cartao, um
    # estado. Duas telas contando o mesmo dia de jeitos diferentes e como elas
    # passam a discordar.
    est_dia = _estados_por_dia(dados, username)
    for _d, _e in est_dia.items():
        _r = dias.setdefault(_d, {"iniciados": 0, "concluidos": 0,
                                  "interrompidos": 0, "ativos": 0,
                                  "minutos": 0.0})
        _r["andamento"] = _e["andamento"]
        _r["concluido"] = _e["concluido"]
        _r["interrompido"] = _e["interrompido"]
    for _r in dias.values():
        _r.setdefault("andamento", 0)
        _r.setdefault("concluido", 0)
        _r.setdefault("interrompido", 0)

    if por_mes:
        agrup = {}
        for dia, v in dias.items():
            a = agrup.setdefault(dia[:7], {"iniciados": 0, "concluidos": 0,
                                           "interrompidos": 0, "ativos": 0,
                                           "andamento": 0, "concluido": 0,
                                           "interrompido": 0, "minutos": 0.0})
            for k in a:
                a[k] += v[k]
        rotulos, regs, uteis = [], [], []
        for r in dados:
            ym = r.get("filtro_mes")
            if not ym:
                continue
            chave = f"{ym[0]:04d}-{ym[1]:02d}"
            rotulos.append(r.get("label", chave))
            regs.append(agrup.get(chave, {"iniciados": 0, "concluidos": 0,
                                          "interrompidos": 0, "ativos": 0,
                                          "andamento": 0, "concluido": 0,
                                          "interrompido": 0, "minutos": 0.0}))
            uteis.append(False)   # mês inteiro vazio não se acusa como dia parado
        unidade = "mês"
    else:
        ym = next((r.get("filtro_mes") for r in dados if r.get("filtro_mes")), None)
        if not ym:
            return ('<div style="padding:24px;text-align:center;font-size:11px;'
                    'color:var(--ms-texto-sec);">Sem mês definido</div>')
        ano, mes = ym
        ultimo = calendar.monthrange(ano, mes)[1]
        hoje = datetime.now().date()
        rotulos, regs, uteis = [], [], []
        for d in range(1, ultimo + 1):
            data = datetime(ano, mes, d).date()
            rotulos.append(str(d))
            regs.append(dias.get(f"{ano:04d}-{mes:02d}-{d:02d}",
                                 {"iniciados": 0, "concluidos": 0,
                                  "interrompidos": 0, "ativos": 0,
                                  "andamento": 0, "concluido": 0,
                                  "interrompido": 0, "minutos": 0.0}))
            uteis.append(data.weekday() < 5 and data <= hoje)
        unidade = "dia"

    if not regs:
        return ('<div style="padding:24px;text-align:center;font-size:11px;'
                'color:var(--ms-texto-sec);">Sem dados no período</div>')

    mins = [r["minutos"] for r in regs]
    parados = [i for i, r in enumerate(regs)
               if uteis[i] and r["minutos"] <= 0 and r["andamento"] == 0
               and r["concluido"] == 0 and r["interrompido"] == 0]

    W = 620
    # Margem maior a esquerda: "EM ANDAMENTO" nao cabe nos 52px de "andamento".
    ml, mr, mt = 74, 12, 14
    ALT_BARRA, ALT_EIXO, ALT_LINHA = 96, 14, 15
    # O rotulo da linha traz a PALAVRA, nao so o simbolo. "▶" sozinho na margem
    # nao diz nada para quem abre a tela pela primeira vez.
    LINHAS = [("andamento", "EM ANDAMENTO", "EM ANDAMENTO", COR_ANDAMENTO),
              ("concluido", "CONCLUÍDO", "CONCLUÍDO", COR_CONCLUIDO),
              ("interrompido", "INTERROMPIDO", "INTERROMPIDO", COR_INTERROMPIDO)]
    H = mt + ALT_BARRA + ALT_EIXO + ALT_LINHA * len(LINHAS) + 6
    iw = W - ml - mr
    topo = max(mins + [60.0])
    bw = iw / len(regs)
    base = mt + ALT_BARRA

    partes = []
    for i in range(4):
        yg = mt + ALT_BARRA * i / 3
        partes.append(
            f'<line x1="{ml}" y1="{yg:.1f}" x2="{W-mr}" y2="{yg:.1f}" '
            f'stroke="var(--ms-divisor,#333)" stroke-width="0.5"/>'
            f'<text x="{ml-4}" y="{yg+3:.1f}" text-anchor="end" font-size="7" '
            f'fill="var(--ms-texto-sec,#888)">'
            f'{_fmt_hm(topo*(3-i)/3)}</text>')

    for i, reg in enumerate(regs):
        x = ml + i * bw + 1
        larg = max(bw - 2, 1)
        dica = (f'{rotulos[i]}: {_fmt_hm(reg["minutos"])} de execução · '
                f'{reg["andamento"]} em andamento · {reg["concluido"]} '
                f'concluído(s) · {reg["interrompido"]} interrompido(s)')
        if reg["minutos"] > 0:
            alt = reg["minutos"] / topo * ALT_BARRA
            partes.append(
                f'<rect x="{x:.1f}" y="{base-alt:.1f}" width="{larg:.1f}" '
                f'height="{alt:.1f}" rx="2" fill="#4A90D9">'
                f'<title>{dica}</title></rect>')
        elif i in parados:
            # O dia parado nao pode ser um vazio igual ao domingo: ele e o
            # achado que esta tela existe para mostrar.
            partes.append(
                f'<rect x="{x:.1f}" y="{mt:.1f}" width="{larg:.1f}" '
                f'height="{ALT_BARRA:.1f}" fill="#E3494822"/>'
                f'<rect x="{x:.1f}" y="{base-2:.1f}" width="{larg:.1f}" height="2" '
                f'fill="#E34948"><title>{dica} — dia útil sem registro</title></rect>')
        else:
            partes.append(
                f'<rect x="{x:.1f}" y="{base-1.5:.1f}" width="{larg:.1f}" '
                f'height="1.5" fill="var(--ms-divisor,#444)">'
                f'<title>{dica}</title></rect>')
        passo = 1 if len(regs) <= 12 else 3
        if i == 0 or (i + 1) % passo == 0:
            partes.append(
                f'<text x="{x+larg/2:.1f}" y="{base+10:.1f}" text-anchor="middle" '
                f'font-size="7" fill="var(--ms-texto-sec,#888)">{rotulos[i]}</text>')

    # A grade das tres contagens. Numero pequeno em cada dia: e a resposta
    # direta a "quantos comecou, quantos terminou, quantos parou".
    for li, (chave, rot, curto, cor) in enumerate(LINHAS):
        yl = base + ALT_EIXO + li * ALT_LINHA
        partes.append(
            f'<text x="{ml-4}" y="{yl+8:.1f}" text-anchor="end" font-size="6.4" '
            f'font-weight="700" letter-spacing="0.2" '
            f'fill="{cor}">{curto}</text>')
        for i, reg in enumerate(regs):
            v = reg[chave]
            x = ml + i * bw + 1
            larg = max(bw - 2, 1)
            if v > 0:
                partes.append(
                    f'<rect x="{x:.1f}" y="{yl:.1f}" width="{larg:.1f}" '
                    f'height="{ALT_LINHA-3:.1f}" rx="2" fill="{cor}" '
                    f'fill-opacity="{min(0.35 + v * 0.2, 1):.2f}"/>'
                    f'<text x="{x+larg/2:.1f}" y="{yl+9:.1f}" text-anchor="middle" '
                    f'font-size="7.5" font-weight="700" fill="#12140f">{v}</text>')
            else:
                partes.append(
                    f'<rect x="{x:.1f}" y="{yl:.1f}" width="{larg:.1f}" '
                    f'height="{ALT_LINHA-3:.1f}" rx="2" '
                    f'fill="var(--ms-divisor,#3a3a3a)" fill-opacity="0.45"/>')

    legenda = " · ".join(
        f'<span style="color:{c};font-weight:700;">{r}</span>'
        for _, r, _cu, c in LINHAS)
    if parados:
        _quais = ", ".join(rotulos[i] for i in parados)
        aviso = (f'<div style="margin-top:6px;font-size:10px;color:#E34948;'
                 f'font-weight:700;">🚩 {len(parados)} dia(s) útil(eis) sem nenhum '
                 f'registro: {_quais}</div>')
    else:
        aviso = ('<div style="margin-top:6px;font-size:10px;color:#1BAF7A;">'
                 'Nenhum dia útil sem registro no período.</div>')
    return (f'<div style="width:100%;overflow:hidden;padding:4px 0;">'
            f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
            f'style="width:100%;">' + "".join(partes) + '</svg>'
            f'<div style="font-size:9px;color:var(--ms-texto-sec);margin-top:2px;">'
            f'Barra: tempo de execução por {unidade} · {legenda}</div>'
            f'{aviso}</div>')


def _chart_colunas_membro(dados, username, colunas_funcao=None):
    """Cartoes que a pessoa entregou, por coluna, com pontos e pontos por cartao.

    Pontos por cartao e o numero que denuncia garimpo: quem so pega coluna cara
    aparece com media alta em poucas colunas. Coluna fora da funcao configurada
    vem marcada — quando nao ha funcao cadastrada, nada e marcado.
    """
    _, cols = _entregas_do_membro(dados, username)
    if not cols:
        return ('<div style="padding:24px;text-align:center;font-size:11px;'
                'color:var(--ms-texto-sec);">Nenhum cartão entregue no período</div>')
    ordenado = sorted(cols.items(), key=lambda kv: -kv[1]["qtd"])
    maxq = max(v["qtd"] for _, v in ordenado) or 1
    funcao = [f.upper() for f in (colunas_funcao or [])]

    html = ""
    for nome, v in ordenado:
        fora = bool(funcao) and not any(nome.upper().startswith(f) for f in funcao)
        cor = "#E34948" if fora else "#4A90D9"
        ppc = v["pts"] / v["qtd"] if v["qtd"] else 0
        rot = nome if len(nome) <= 34 else nome[:33] + "…"
        html += (
            f'<div style="margin-bottom:9px;">'
            f'<div style="display:flex;justify-content:space-between;gap:10px;font-size:11px;">'
            f'<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" '
            f'title="{nome}">{rot}'
            + (' <b style="color:#E34948;">· fora da função</b>' if fora else '') +
            f'</span>'
            f'<span style="flex:none;font-weight:700;">{v["qtd"]}'
            f'<span style="font-weight:400;color:var(--ms-texto-sec);"> · '
            f'{v["pts"]:,.0f} pts · {ppc:.0f}/cartão</span></span></div>'
            f'<div style="height:7px;border-radius:4px;background:var(--ms-metric-bd);'
            f'margin-top:3px;overflow:hidden;">'
            f'<div style="height:100%;border-radius:4px;width:{v["qtd"]/maxq*100:.1f}%;'
            f'background:{cor};"></div></div></div>'
        ).replace(",", ".")
    return html


def _chart_tempo_medio(dados, username, cfg):
    """Tempo medio do periodo contra o alvo, mais o historico mes a mes."""
    ref = float((cfg or {}).get(f"exec_ref_{username}", 0) or 0) or 120.0
    _mt = mc.meta_execucao(cfg, username, ref)
    red = _mt["red"]
    alvo = _mt["alvo"] or ref

    # Media por mes, para o historico; e a do periodo inteiro, para o numero grande
    por_mes, todos = [], []
    for r in dados:
        ts = [t for por_col in (r.get("tempo_membro_lista") or {}).get(username, {}).values()
              for t in por_col]
        todos.extend(ts)
        por_mes.append((r.get("label", ""), (sum(ts) / len(ts)) if ts else None))
    atual = (sum(todos) / len(todos)) if todos else None

    if atual is None:
        return ('<div style="padding:24px;text-align:center;font-size:11px;'
                'color:var(--ms-texto-sec);">Nenhum cartão com tempo medido no período</div>')

    cor = "#1BAF7A" if atual <= alvo else ("#EDA100" if atual <= ref else "#E34948")
    if red <= 0:
        recado = "sem alvo de tempo definido para o mês"
    elif atual <= alvo:
        recado = "✅ dentro do alvo"
    else:
        recado = f"{_fmt_hm(atual - alvo)} acima do alvo"
    # Barra de progresso da reducao. O texto dizia "1h42 acima do alvo" e nao
    # dizia o que importa: quanto do caminho ja foi andado. Aqui a trilha vai da
    # referencia (o ponto de partida do mes) ate zero, o alvo e um risco nela, e
    # o quanto ja se reduziu e a parte pintada.
    OURO = "#FFD700"
    escala = max(ref, atual) * 1.06 or 1
    _x_alvo = alvo / escala * 100
    _x_atual = min(atual, ref) / escala * 100
    _acima = max(0.0, atual - ref)          # piorou em relacao a referencia
    precisa = max(ref - alvo, 0.0)
    andou = max(ref - atual, 0.0)
    pct_prog = ((andou / precisa * 100) if precisa > 0
                else (100.0 if atual <= alvo else 0.0))
    barra = (
        f'<div style="height:14px;border-radius:7px;background:var(--ms-metric-bd);'
        f'margin:12px 0 5px;position:relative;">'
        f'<div style="position:absolute;left:0;top:0;height:100%;'
        f'width:{_x_atual:.1f}%;background:{cor};'
        f'border-radius:7px {"0 0" if _acima > 0 else "7px 7px"} 7px;"></div>'
        + (f'<div style="position:absolute;top:0;height:100%;'
           f'left:{ref / escala * 100:.1f}%;width:{_acima / escala * 100:.1f}%;'
           f'background:#E34948;border-radius:0 7px 7px 0;"></div>'
           if _acima > 0 else "")
        + f'<div style="position:absolute;top:-5px;bottom:-5px;left:{_x_alvo:.1f}%;'
        f'width:3px;margin-left:-1.5px;border-radius:2px;'
        f'background:var(--ms-texto);"></div></div>'
        f'<div style="position:relative;height:12px;margin-bottom:6px;">'
        f'<span style="position:absolute;left:{_x_alvo:.1f}%;'
        f'transform:translateX(-50%);font-size:8px;font-weight:700;'
        f'white-space:nowrap;color:var(--ms-texto);">▲ alvo {_fmt_hm(alvo)}</span>'
        f'<span style="position:absolute;right:0;font-size:8px;font-weight:700;'
        f'color:{OURO if pct_prog >= 100 else "var(--ms-texto-sec)"};">'
        f'{min(pct_prog, 100):.0f}% do caminho</span></div>'
    )
    if red <= 0:
        _detalhe = "sem alvo de tempo definido para o mês"
    elif atual <= alvo:
        _detalhe = f"✅ alvo batido · {_fmt_hm(andou)} reduzidos"
    elif atual >= ref:
        _detalhe = (f"{_fmt_hm(atual - ref)} ACIMA da referência · "
                    f"a meta pede {_fmt_hm(precisa)} a menos")
    else:
        _detalhe = (f"reduziu {_fmt_hm(andou)} de {_fmt_hm(precisa)} · "
                    f"faltam {_fmt_hm(atual - alvo)}")
    topo = (
        f'<div style="display:flex;align-items:baseline;gap:10px;">'
        f'<span style="font-size:30px;font-weight:700;color:{cor};line-height:1;">'
        f'{_fmt_hm(atual)}</span>'
        f'<span style="font-size:11px;color:var(--ms-texto-sec);">média do período</span>'
        f'<span style="margin-left:auto;font-size:11px;color:var(--ms-texto-sec);">'
        f'meta do mês <b style="color:var(--ms-texto);">{_fmt_hm(alvo)}</b>'
        f'</span></div>'
        + barra +
        f'<div style="font-size:11px;color:var(--ms-texto-sec);margin-bottom:10px;">'
        f'referência do mês {_fmt_hm(ref)}'
        + (f" · alvo {_fmt_hm(alvo)} ({red:.0f}% abaixo)" if red > 0 else "")
        + f' · <span style="color:{cor};font-weight:600;">{_detalhe}</span></div>'
    )

    # Historico so faz sentido com mais de um mes: um mes so repete o numero acima
    medidos = [(l, v) for l, v in por_mes if v]
    if len(medidos) < 2:
        return topo + ('<div style="font-size:10.5px;color:var(--ms-texto-sec);'
                       'font-style:italic;">Histórico aparece com o filtro em '
                       'trimestre ou semestre.</div>')

    W, H = 420, 132
    ml, mr, mt, mb = 34, 10, 12, 24
    iw, ih = W - ml - mr, H - mt - mb
    teto = max([v for _, v in medidos] + [alvo]) * 1.15
    bw = iw / len(medidos)
    def y(v): return mt + ih - (v / teto * ih)
    partes = []
    for i, (lab, v) in enumerate(medidos):
        x = ml + i * bw + bw * 0.2
        w = bw * 0.6
        c = "#1BAF7A" if v <= alvo else "#E34948"
        partes.append(
            f'<rect x="{x:.1f}" y="{y(v):.1f}" width="{w:.1f}" '
            f'height="{mt+ih-y(v):.1f}" rx="3" fill="{c}"><title>{lab}: {_fmt_hm(v)}</title></rect>'
            f'<text x="{x+w/2:.1f}" y="{y(v)-4:.1f}" text-anchor="middle" font-size="8" '
            f'fill="var(--ms-texto-sec,#888)">{_fmt_hm(v)}</text>'
            f'<text x="{x+w/2:.1f}" y="{H-8}" text-anchor="middle" font-size="8" '
            f'fill="var(--ms-texto-sec,#888)">{lab}</text>')
    partes.append(
        f'<line x1="{ml}" y1="{y(alvo):.1f}" x2="{W-mr}" y2="{y(alvo):.1f}" '
        f'stroke="#EDA100" stroke-width="1.5" stroke-dasharray="4,3"/>'
        f'<text x="{ml}" y="{y(alvo)-4:.1f}" font-size="8" font-weight="700" '
        f'fill="#EDA100">alvo {_fmt_hm(alvo)}</text>')
    return topo + (f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
                   f'style="width:100%;">' + "".join(partes) + '</svg>')


def _chart_demandas_criadas(dados, username):
    """As demandas que essa pessoa ABRIU: quantas, quanto valeram, onde pararam.

    Fecha o outro lado da busca de demanda. O tempo gasto procurando já
    aparecia; o que ele PRODUZIU, não — e é a diferença entre quem passou a
    manhã garimpando e voltou com oito demandas e quem voltou com uma.

    A coluna é a de agora, não a da criação: a demanda nasce na triagem e é
    movida para a coluna certa quando o gestor pontua. É a de agora que responde
    "que tipo de demanda essa pessoa gera".
    """
    tot = {"n": 0, "pts": 0.0, "colunas": {}}
    for r in dados:
        v = (r.get("demandas_criadas") or {}).get(username)
        if not v:
            continue
        tot["n"] += v["n"]
        tot["pts"] += v["pts"]
        for col, c in (v.get("colunas") or {}).items():
            a = tot["colunas"].setdefault(col, {"n": 0, "pts": 0.0})
            a["n"] += c["n"]
            a["pts"] += c["pts"]

    # Quanto custou garimpar: o tempo na coluna ANÁLISE DE DEMANDAS.
    _busca = _tempo_analise(dados).get(username) or {"min": 0.0, "dias": 0}
    _md = (_busca["min"] / _busca["dias"]) if _busca["dias"] else 0.0

    # Antes do corte o Studio nao lia a acao de criacao. Dizer "0 demandas" ali
    # seria acusar de nao ter criado nada quem so nao estava sendo medido.
    _ini_per = min((r.get("filtro_mes") for r in dados if r.get("filtro_mes")),
                   default=None)
    _fim_per = max((r.get("filtro_mes") for r in dados if r.get("filtro_mes")),
                   default=None)
    _corte = _pc.CORTE_CRIACAO
    if _fim_per and (_fim_per[0], _fim_per[1]) < (_corte.year, _corte.month):
        return ('<div style="padding:20px;text-align:center;font-size:11px;'
                'color:var(--ms-texto-sec);">A medição de demandas criadas '
                f'começa em {_corte.strftime("%d/%m/%Y")} — antes disso não há '
                'o que contar.</div>')
    _aviso = ""
    if _ini_per and (_ini_per[0], _ini_per[1]) < (_corte.year, _corte.month):
        _aviso = (f'<div style="font-size:9.5px;color:#EDA100;margin-top:8px;">'
                  f'⚠️ O período escolhido começa antes de '
                  f'{_corte.strftime("%d/%m/%Y")}, quando esta medição entrou '
                  f'no ar — os meses anteriores contam zero por falta de '
                  f'leitura, não por falta de demanda.</div>')

    AZUL, OURO, CINZA, VERDE = "#4A90D9", "#FFD700", "#7A8B99", "#1BAF7A"
    ppd = (tot["pts"] / tot["n"]) if tot["n"] else 0.0

    def _n(rotulo, valor, cor, detalhe):
        return (f'<div style="flex:1;min-width:120px;">'
                f'<div style="font-size:26px;font-weight:700;color:{cor};'
                f'line-height:1;">{valor}</div>'
                f'<div style="font-size:11px;color:var(--ms-texto-sec);'
                f'margin-top:3px;">{rotulo}</div>'
                f'<div style="font-size:9px;color:var(--ms-texto-sec);'
                f'margin-top:1px;">{detalhe}</div></div>')

    # Quanto custa ACHAR uma demanda: o tempo de garimpo dividido pelo que ele
    # trouxe. E o numero que junta os dois lados — seis horas procurando podem
    # ser bem ou mal gastas, e so este quociente diz qual das duas.
    _por_card = (_busca["min"] / tot["n"]) if tot["n"] else None

    topo = (
        f'<div style="display:flex;gap:14px;flex-wrap:wrap;margin-bottom:12px;">'
        + _n("demandas abertas", f'{tot["n"]}', AZUL,
             "criadas por ela no período")
        + _n("pontos gerados", _n_br(tot["pts"]), OURO,
             f"{_n_br(ppd)} pts por demanda" if tot["n"] else "—")
        + _n("por demanda encontrada",
             _fmt_hm(_por_card) if _por_card is not None else "—", VERDE,
             ("tempo de busca ÷ demandas abertas" if _por_card is not None
              else "sem demanda no período"))
        + _n("garimpando", _fmt_hm(_busca["min"]), CINZA,
             (f'{_fmt_hm(_md)}/dia em {_busca["dias"]} dia(s)'
              if _busca["dias"] else "sem tempo registrado"))
        + '</div>')

    if not tot["colunas"]:
        return topo + ('<div style="font-size:10.5px;color:var(--ms-texto-sec);'
                       'font-style:italic;">Nenhuma demanda aberta por ela no '
                       'período.</div>') + _aviso

    ordenado = sorted(tot["colunas"].items(), key=lambda kv: -kv[1]["n"])
    maxn = max(c["n"] for _, c in ordenado) or 1
    barras = ""
    for col, c in ordenado:
        barras += (
            f'<div style="margin-bottom:9px;">'
            f'<div style="display:flex;justify-content:space-between;gap:10px;'
            f'font-size:11px;">'
            f'<span style="overflow:hidden;text-overflow:ellipsis;'
            f'white-space:nowrap;">{_esc(col)}</span>'
            f'<span style="flex:none;font-weight:700;">{c["n"]}'
            f'<span style="font-weight:400;color:var(--ms-texto-sec);"> · '
            f'{_n_br(c["pts"])} pts</span></span></div>'
            f'<div style="height:7px;border-radius:4px;'
            f'background:var(--ms-metric-bd);margin-top:3px;overflow:hidden;">'
            f'<div style="height:100%;border-radius:4px;'
            f'width:{c["n"] / maxn * 100:.1f}%;background:{AZUL};"></div>'
            f'</div></div>')
    return (topo
            + '<div style="font-size:9px;color:var(--ms-texto-sec);'
              'text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;">'
              'onde essas demandas estão hoje</div>'
            + barras + _aviso)


def _chart_colaboracao(dados, username):
    """Quanto dos pontos da equipe saiu dos cartoes dessa pessoa, em % e em pontos."""
    linhas, pt_tot, eq_tot = [], 0.0, 0.0
    for r in dados:
        p = float((r.get("pts_membro") or {}).get(username, 0) or 0)
        e = float(r.get("pts_equipe", 0) or 0)
        q = int((r.get("qtd_membro") or {}).get(username, 0) or 0)
        pt_tot += p; eq_tot += e
        linhas.append((r.get("label", ""), p, e, q))
    if eq_tot <= 0:
        return ('<div style="padding:24px;text-align:center;font-size:11px;'
                'color:var(--ms-texto-sec);">Sem pontuação da equipe no período</div>')
    pct = pt_tot / eq_tot * 100
    q_tot = sum(l[3] for l in linhas)

    html = (
        f'<div style="display:flex;align-items:baseline;gap:10px;">'
        f'<span style="font-size:30px;font-weight:700;color:#4A90D9;line-height:1;">'
        f'{pct:.1f}%</span>'
        f'<span style="font-size:11px;color:var(--ms-texto-sec);">'
        f'dos pontos da equipe</span></div>'
        f'<div style="height:11px;border-radius:6px;background:var(--ms-metric-bd);'
        f'margin:8px 0 6px;overflow:hidden;">'
        f'<div style="height:100%;border-radius:6px;width:{min(pct,100):.1f}%;'
        f'background:#4A90D9;"></div></div>'
        f'<div style="font-size:11px;color:var(--ms-texto-sec);margin-bottom:10px;">'
        f'<b style="color:var(--ms-texto);">{pt_tot:,.0f}</b> pts dela · de '
        f'<b style="color:var(--ms-texto);">{eq_tot:,.0f}</b> pts da equipe · '
        f'{q_tot} cartões</div>'
    ).replace(",", ".")

    # A tabela mes a mes so acrescenta quando ha mais de um mes
    if len(linhas) > 1:
        corpo = ""
        for lab, p, e, q in linhas:
            pp = (p / e * 100) if e else 0
            corpo += (
                f'<tr><td style="text-align:left;padding:3px 6px;">{lab}</td>'
                f'<td style="text-align:right;padding:3px 6px;">{p:,.0f}</td>'
                f'<td style="text-align:right;padding:3px 6px;">{e:,.0f}</td>'
                f'<td style="text-align:right;padding:3px 6px;font-weight:700;">'
                f'{pp:.1f}%</td></tr>').replace(",", ".")
        html += (
            f'<table style="border-collapse:collapse;width:100%;font-size:11px;">'
            f'<thead><tr style="color:var(--ms-texto-sec);font-size:9.5px;'
            f'text-transform:uppercase;letter-spacing:.4px;">'
            f'<th style="text-align:left;padding:3px 6px;">Mês</th>'
            f'<th style="text-align:right;padding:3px 6px;">Pontos</th>'
            f'<th style="text-align:right;padding:3px 6px;">Equipe</th>'
            f'<th style="text-align:right;padding:3px 6px;">Contrib.</th>'
            f'</tr></thead><tbody>{corpo}</tbody></table>')
    return html


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

    # Antes a grade era sempre de 4 quadros, e um filtro de um mês só enchia a
    # tela com três "— sem dado — 0 pts", que parecia falha de carregamento. A
    # grade agora tem o tamanho do que existe.
    cards = []
    for i, m in enumerate(top4_m):
        cor = CORES4[i]
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
    if not cards:
        cards.append(
            '<div style="background:var(--ms-metric-bg);border-radius:8px;padding:12px 10px;'
            'border:1px solid var(--ms-divisor);text-align:center;font-size:10px;'
            'color:var(--ms-texto-sec);">Nenhum mês com meta individual configurada '
            'no período selecionado.</div>'
        )
    rodape = ""
    if top4_c:
        cols_txt = "  ·  ".join(
            f"#{i+1} {(nl[:16]+'…') if len(nl)>16 else nl} ({v:,.0f}pts)"
            for i, (nl, v) in enumerate(top4_c)
        )
        rodape = f'<div style="font-size:9px;color:var(--ms-texto-sec);text-align:center;margin-top:8px;font-style:italic;">🏆 Top 4 colunas da equipe: {cols_txt}</div>'
    return (
        f'<div style="display:grid;grid-template-columns:repeat({len(cards)},1fr);gap:8px;">'
        + "".join(cards) + f'</div>{rodape}'
    )


def _chart_resumo_colabs(dados):
    """HTML: 2×4 grade comparativa de todos os colaboradores."""
    MB    = _pc.MEMBROS_ATIVOS
    users = list(MB.keys())
    # A paleta e ciclica de proposito. Ela era cortada em len(users), e como
    # a equipe vem da planilha, o quinto colaborador cadastrado (Nicollas e
    # Luiz) caia em CORES[4] e derrubava o resumo inteiro com IndexError.
    CORES = ["#4A90D9", "#1BAF7A", "#EDA100", "#7B68EE"]

    pts_mb  = {u: sum(r["pts_membro"].get(u, 0) for r in dados) for u in users}
    meta_mb = {u: sum(r["cfg"].get(f"meta_{u}", r["cfg"].get("meta_equipe", 0)) for r in dados) for u in users}
    total_pts   = sum(pts_mb.values()) or 1
    pct_contrib = {u: pts_mb[u] / total_pts * 100 for u in users}
    pct_meta    = {u: pts_mb[u] / max(meta_mb[u], 1) * 100 for u in users}

    # Media de execucao de CADA UM. Antes era a media geral do board repetida
    # identica em todas as barras — o painel comparava todo mundo com todo mundo
    # usando o mesmo numero.
    _tempos_u = {u: [] for u in users}
    for r in dados:
        for u, por_col in (r.get("tempo_membro_lista") or {}).items():
            if u in _tempos_u:
                _tempos_u[u].extend(t for ts in por_col.values() for t in ts)
    exec_mb = {u: (sum(v) / len(v) if v else 0.0) for u, v in _tempos_u.items()}

    # Cartoes entregues depois da data combinada. E do time inteiro, nao de cada
    # um: como barra por pessoa dava a mesma altura para todos e nao comparava
    # nada. Vira uma linha de texto no detalhe.
    tc_total  = sum(r["total_concl"] for r in dados)
    ta_total  = sum(r["atrasados"]   for r in dados)
    pct_cards_atrasados = ta_total / max(tc_total, 1) * 100

    _pt = _ponto_por_membro(dados, users)
    _tem_ponto = _pt["tem_ponto"]
    _ocio_mb, _tol_mb, _pct_ocio = _pt["ocio_mb"], _pt["tol_mb"], _pt["pct_ocio"]
    _dias_trab, _dias_aus, _atr_mb = _pt["dias_trab"], _pt["dias_aus"], _pt["atr_mb"]

    def _cor_meta(v):   return "#1BAF7A" if v >= 100 else ("#EDA100" if v >= 75 else "#4A90D9")
    def _cor_atraso(v): return "#1BAF7A" if v < 5   else ("#EDA100" if v < 15  else "#E34948")
    _lim_atr = int(dados[-1]["cfg"].get("max_atr_normal", 10)) if dados else 10
    def _cor_atr_ponto(v):
        return ("#1BAF7A" if v <= _lim_atr * 0.6
                else ("#EDA100" if v <= _lim_atr else "#E34948"))
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
            cor = CORES[users.index(u) % len(CORES)] if u in users else "#555"
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
        _mini("⏰ Atrasos de Ponto",          _atr_mb,    fmt="{:.0f}", unidade="",
              cor_fn=_cor_atr_ponto, aguardando=not _tem_ponto),
        _detalhe_ocio,
    ]
    cells[-1] += (
        f'<div style="margin-top:8px;padding-top:7px;'
        f'border-top:1px solid var(--ms-divisor);font-size:10px;'
        f'color:var(--ms-texto-sec);">Cartões entregues após a data combinada: '
        f'<b style="color:var(--ms-texto);">{ta_total} de {tc_total}</b>'
        f' ({pct_cards_atrasados:.1f}%) — do time inteiro</div>')
    return (
        f'<div style="margin-bottom:8px;font-size:11px;font-weight:700;color:var(--ms-texto);">📋 Resumo Comparativo — Todos os Colaboradores</div>'
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;">'
        + "".join(_card(c) for c in cells) + '</div>'
    )


def _desempenho_individual(dados, username, nome, carregar_periodo=None,
                           dono=False):
    """Desempenho de um colaborador, com periodo proprio.

    O filtro daqui e separado do coletivo la de cima de proposito: olhar o ano da
    equipe e o trimestre de uma pessoa sao perguntas diferentes, e antes uma
    obrigava a outra.
    """
    # ── Periodo desta secao ──────────────────────────────────────────────────
    #
    # As chaves nao levam o username: trocar de colaborador mantem o periodo
    # escolhido. Comparar duas pessoas no mesmo mes e o uso normal daqui, e
    # reescolher o mes a cada troca seria trabalho a toa.
    _hoje = datetime.now()

    def _recuar(ate):
        """Os `ate` ultimos meses, do mais antigo para o mais recente."""
        fora, _a, _m = [], _hoje.year, _hoje.month
        for _ in range(ate):
            fora.append((_a, _m))
            _m -= 1
            if _m == 0:
                _a, _m = _a - 1, 12
        fora.reverse()
        return fora

    _c_per, _c_mes = st.columns([2, 1])
    _op = _c_per.radio("Período", ["Mês", "Último trimestre", "Último semestre"],
                       horizontal=True, key="des_ind_periodo",
                       label_visibility="collapsed")
    _por_mes = _op != "Mês"

    _lista = None
    if _por_mes:
        _lista = _recuar(3 if _op == "Último trimestre" else 6)
    else:
        # Um mes qualquer dos ultimos doze, e nao so o que veio do filtro
        # coletivo: a secao tem periodo proprio, e sem o seletor "Mes" queria
        # dizer "o mes que a tela de cima escolheu".
        _ult12 = list(reversed(_recuar(12)))
        _rots = [_label_mes(a, m) for a, m in _ult12]
        _esc = _c_mes.selectbox("Mês", _rots, index=0, key="des_ind_mes",
                                label_visibility="collapsed")
        _lista = [_ult12[_rots.index(_esc)]]

    if _lista and carregar_periodo:
        try:
            dados = carregar_periodo(_lista)
        except Exception as _e:
            st.warning(f"Não consegui carregar o período: {str(_e)[:120]}")
            _por_mes = False
    _rot_per = (dados[0]["label"] + " → " + dados[-1]["label"]) if len(dados) > 1 else \
               (dados[-1]["label"] if dados else "—")
    st.caption(f"Período desta seção: **{_rot_per}** · independente do filtro coletivo acima.")

    meses = _ind_extrair_meses(dados, username)
    # Remove meses sem meta individual configurada (meta == 0)
    meses = [m for m in meses if m["meta"] > 0]

    # Ociosidade e tolerâncias vêm da mesma conta do resumo da equipe. O limite
    # de tolerâncias é mensal, então o orçamento do período é o limite vezes o
    # número de meses analisados — senão um filtro de 6 meses pareceria estourar.
    try:
        _users_ind = list(_pc.MEMBROS_ATIVOS.keys())
        _ponto_ind = _ponto_por_membro(dados, _users_ind)
    except Exception:
        _ponto_ind = None
    _n_meses_ponto = len({r.get("filtro_mes") for r in dados if r.get("filtro_mes")}) or 1
    _cfg_ult = dados[-1]["cfg"] if dados else {}
    _tol_lim = int(_cfg_ult.get("max_tol_normal", 15)) * _n_meses_ponto
    _atr_lim = int(_cfg_ult.get("max_atr_normal", 10)) * _n_meses_ponto

    # A entrada na meta vem primeiro: antes de olhar grafico nenhum, a pergunta
    # e "eu recebo pela meta deste mes?".
    try:
        _secao_entrada_meta(dados, username, nome)
        st.markdown("---")
    except Exception as _e_ent:
        st.warning(f"Não consegui montar a entrada na meta: {str(_e_ent)[:150]}")

    row1a, row1b = st.columns(2)
    with row1a:
        st.markdown(f"#### 📊 Pontuação — {nome}")
        st.caption("Meta individual vs. realizado · linha de delta · destaque do melhor mês.")
        # O ritmo da propria meta individual: e ele que decide se a barra
        # fica vermelha, e nao a distancia ate os 100% no dia 2 do mes.
        _u_pts, _d_pts = _dias_uteis_periodo(dados)
        _ritmo_pts = _ritmo_entrada(sum(m["pts"] for m in meses),
                                    sum(m["meta"] for m in meses),
                                    _u_pts, _d_pts)
        st.markdown(_chart_ind_pts(meses, ritmo=_ritmo_pts),
                    unsafe_allow_html=True)
        # A ociosidade e a outra metade da mesma pergunta: quanto se entregou, e
        # quanto do expediente ficou sem cartao nenhum em andamento. Ganha
        # titulo proprio, como a pontuacao: sao dois indicadores, nao um com
        # rodape.
        st.markdown(f"#### 💤 Ociosidade — {nome}")
        st.caption("Tempo do expediente sem nenhum cartão EM ANDAMENTO no seu "
                   "nome · verde abaixo do limite, vermelho acima.")
        st.markdown(_barra_ociosidade(_ponto_ind, username, _rot_per),
                    unsafe_allow_html=True)

    with row1b:
        st.markdown("#### 🎯 Índices Individuais")
        st.caption("Os cinco critérios cobrados na meta, com o limite de cada "
                   "grupo — a MAXX pede mais em todos.")
        st.markdown(_chart_ind_indices(meses, ponto=_ponto_ind, username=username,
                                       max_tol=_tol_lim, max_atr=_atr_lim,
                                       dados=dados, cfg=_cfg_ult),
                    unsafe_allow_html=True)

    st.markdown("---")
    # Um grafico so, em largura inteira. Eram dois: a Atividade diaria repetia
    # em barra o tempo que os blocos da linha do tempo ja mostram, e so as tres
    # contagens tinham informacao propria -- elas viraram o rodape daqui.
    #
    # No trimestre e no semestre nao ha linha do tempo possivel: 90 ou 180
    # colunas de dia nao cabem. La fica o resumo mes a mes.
    if _por_mes:
        st.markdown("#### 🗓️ Atividade por mês")
        st.caption("Tempo de execução e quantos cartões foram iniciados, "
                   "concluídos e interrompidos em cada mês do período.")
        st.markdown(_chart_atividade_dia(dados, username, por_mes=True),
                    unsafe_allow_html=True)
    else:
        st.markdown("#### ⏱️ Linha do tempo do dia")
        st.caption(
            "Cada execução no relógio do expediente da pessoa — o início do "
            "expediente embaixo, o fim em cima. O traço verde é o início do "
            "cartão, o vermelho é o fim, e a distância entre eles é a duração. "
            "A **cor do bloco é o estado do cartão naquele dia** — todos os "
            "trechos do mesmo cartão têm a mesma cor: amarelo EM ANDAMENTO, verde CONCLUÍDO, roxo INTERROMPIDO ou FIM DE EXPEDIENTE. "
            "Embaixo, quantos cartões ficaram **EM ANDAMENTO**, **CONCLUÍDO** e "
            "**INTERROMPIDO** no dia — interrompido conta tanto a etiqueta "
            "INTERROMPIDO quanto FIM DE EXPEDIENTE. Dia útil já passado sem "
            "nenhum registro sai em vermelho. Passe o mouse num bloco para ver "
            "o cartão."
        )
        st.markdown(_chart_linha_do_tempo(dados, username),
                    unsafe_allow_html=True)

    st.markdown("---")
    row2a, row2b = st.columns(2)
    with row2a:
        st.markdown("#### 📅 Curva de execução")
        st.caption("Cartões entregues por dia. Dia sem entrega aparece como zero — é ele "
                   "que mostra se o ritmo é constante ou se junta numa ponta do mês."
                   if not _por_mes else
                   "Cartões entregues por mês no período selecionado.")
        st.markdown(_chart_curva_execucao(dados, username, por_mes=_por_mes),
                    unsafe_allow_html=True)

    with row2b:
        st.markdown("#### 🗂️ Cartões por coluna")
        st.caption("Onde o trabalho aconteceu. **Pontos por cartão** mostra quem só "
                   "pega coluna cara. Coluna fora da função cadastrada vem marcada.")
        try:
            import equipe_config as _ec_f
            _funcao = _ec_f.colunas_da_funcao(username)
        except Exception:
            _funcao = []
        st.markdown(_chart_colunas_membro(dados, username, _funcao),
                    unsafe_allow_html=True)

    st.markdown("---")
    row3a, row3b = st.columns(2)
    with row3a:
        st.markdown("#### ⏳ Tempo médio de execução")
        st.caption("O mês contra a referência da meta, e o histórico ao lado.")
        st.markdown(_chart_tempo_medio(dados, username, _cfg_ult), unsafe_allow_html=True)

    with row3b:
        st.markdown("#### 🔎 Demandas geradas")
        st.caption("O outro lado da busca: quantas demandas essa pessoa abriu, "
                   "quanto elas valeram e em que coluna estão hoje.")
        st.markdown(_chart_demandas_criadas(dados, username),
                    unsafe_allow_html=True)

    st.markdown("---")
    row3c, row3d = st.columns(2)
    with row3c:
        st.markdown("#### 🤝 Colaboração nas metas")
        st.caption("Quanto dos pontos da equipe saiu dos cartões que essa pessoa entregou.")
        st.markdown(_chart_colaboracao(dados, username), unsafe_allow_html=True)

    with row3d:
        st.markdown("#### 🍕 Participação nas Colunas")
        st.caption("Top 5 colunas mais pontuadas pela equipe · % central = "
                   "contribuição individual no total.")
        st.markdown(_chart_ind_participacao(dados, username), unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### 🏆 Destaques do Período")
    st.caption("4 melhores meses individuais · top 4 colunas da equipe.")
    st.markdown(_chart_ind_destaques(meses, dados, username), unsafe_allow_html=True)

    # No fim de proposito: e a resposta a um numero que a pessoa acabou de ver
    # acima. Ler "78% de ociosidade" e so depois descobrir que da para explicar
    # o que aconteceu e a ordem certa.
    _secao_pedido_abatimento(username, nome, dono)


def _linha_pedido(a, _ab, gestor=False):
    """Um pedido desenhado: quando, quanto tempo, o motivo e no que deu."""
    dur = ((a["fim"].hour * 60 + a["fim"].minute)
           - (a["inicio"].hour * 60 + a["inicio"].minute))
    if a["status"] == _ab.APROVADO:
        cor, selo = "#1BAF7A", "✅ aprovado"
    elif a["status"] == _ab.RECUSADO:
        cor, selo = "#E34948", "🚫 recusado"
    else:
        cor = "#EDA100"
        selo = "⏳ aguardando você" if gestor else "⏳ aguardando aprovação"

    quem = ""
    if gestor and a["user"]:
        _n = _pc.MEMBROS_ATIVOS.get(a["user"], a["user"])
        quem = (f'<span style="font-weight:700;color:var(--ms-texto);">'
                f'{_esc(_n)}</span> · ')

    # A decisao do gestor, quando existe: o horario aprovado (que pode ser
    # menor que o pedido) e o que ele escreveu. Sem isso o pedido "some" e a
    # pessoa manda de novo.
    rodape = ""
    if a["status"] != _ab.PENDENTE:
        _obs = f' — "{_esc(a["obs"])}"' if a["obs"] else ""
        _por = f' por {_esc(a["decidido_por"])}' if a["decidido_por"] else ""
        rodape = (f'<div style="font-size:11.5px;color:{cor};margin-top:3px;">'
                  f'{selo} como {a["inicio"]:%H:%M} → {a["fim"]:%H:%M}'
                  f'{_por}{_obs}</div>')

    return (
        f'<div style="border-left:3px solid {cor};background:var(--ms-metric-bg);'
        f'border-radius:0 6px 6px 0;padding:9px 12px;margin-bottom:8px;">'
        f'<div style="font-size:12.5px;color:var(--ms-texto-sec);">'
        f'{quem}{a["data"]:%d/%m} · {a["inicio"]:%H:%M} → {a["fim"]:%H:%M}'
        f'<span style="color:var(--ms-texto);font-weight:700;"> · '
        f'{_fmt_hm(dur)}</span>'
        f'<span style="color:{cor};"> · {selo}</span></div>'
        f'<div style="font-size:13px;margin-top:3px;">'
        f'{_esc(a["motivo"]) or "sem motivo"}</div>'
        f'{rodape}</div>')


def _secao_pedido_abatimento(username, nome, pode_pedir):
    """O colaborador conta o que fez fora do cartão; o gestor decide.

    A ociosidade sobe quando o trabalho acontece sem cartão aberto ou sem a
    etiqueta certa: filmar sem FILMAGEM, analisar demanda sem abrir o cartão da
    coluna. O indicador está certo — ele mede o que o Trello viu —, mas a
    pessoa é cobrada por uma hora que ela trabalhou.

    O pedido não desconta nada sozinho. Só o que o gestor aprova sai da conta,
    e aí sai dos três de uma vez: ociosidade, tempo de execução e atraso, que
    partem todos das mesmas janelas de expediente.
    """
    try:
        import abonos as _ab
        _lista = _ab.carregar()
    except Exception as _e:
        st.warning(f"Não consegui ler os pedidos: {str(_e)[:150]}")
        return

    st.markdown("---")
    st.markdown("#### 🙋 Pedir abatimento de ociosidade")
    st.caption(
        "Trabalhou e o sistema não viu? Aconteceu de esquecer a etiqueta "
        "**FILMAGEM**, de fazer a análise de demanda sem abrir o cartão, de "
        "executar uma tarefa sem cartão nenhum. Diga o horário e o que você "
        "fez — o gestor aprova, ajusta ou recusa. Aprovado, esse tempo sai da "
        "sua **ociosidade**, do seu **tempo de execução** e do **atraso**."
    )

    if pode_pedir:
        # Fora de st.form: o rodape precisa recalcular a duracao enquanto a
        # pessoa mexe nos horarios, e formulario so atualiza no envio.
        _hoje = datetime.now(_pc.FUSO).date()
        c1, c2, c3 = st.columns([1.3, 1, 1])
        _d = c1.date_input("Data da atividade", value=_hoje,
                           key=f"pab_d_{username}", format="DD/MM/YYYY")
        _i = c2.time_input("Começou às", value=time(9, 0),
                           key=f"pab_i_{username}", step=300)
        _f = c3.time_input("Terminou às", value=time(10, 0),
                           key=f"pab_f_{username}", step=300)
        _m = st.text_area(
            "O que você estava fazendo", key=f"pab_m_{username}", height=80,
            placeholder="Estava filmando os produtos da campanha e esqueci de "
                        "pôr a etiqueta FILMAGEM no cartão.")
        _dur = ((_f.hour * 60 + _f.minute) - (_i.hour * 60 + _i.minute))
        _b1, _b2 = st.columns([1, 4])
        if _b1.button("📨 Enviar pedido", key=f"pab_ok_{username}",
                      use_container_width=True):
            _ok, _msg = _ab.salvar(_d, _i, _f, _m, user=username,
                                   status=_ab.PENDENTE)
            if _ok:
                st.rerun()
            else:
                st.error(_msg)
        _txt = (f"**{_fmt_hm(_dur)}** · " if _dur > 0 else "")
        _b2.caption(f"{_txt}o gestor recebe, pode ajustar o horário e aprovar "
                    f"ou recusar")

    meus = _ab.do_usuario(username, _lista)
    st.markdown("##### 📋 Meus pedidos" if pode_pedir
                else f"##### 📋 Pedidos de {_esc(nome)}")
    if not meus:
        st.caption("Nenhum pedido até agora.")
        return
    st.markdown("".join(_linha_pedido(a, _ab) for a in meus[:20]),
                unsafe_allow_html=True)


def _secao_entrada_meta(dados, username, nome):
    """Os dois porteiros da meta, explicados, para uma pessoa só.

    Bater a meta é do time; ENTRAR nela é de cada um — 80% da própria meta
    individual para a coletiva, 100% para a MAXX, e o teto de advertências nos
    dois. Isso vivia numa tabela com a equipe inteira, na visão coletiva: quem
    quisesse saber da própria situação lia a dos outros junto, e a tabela dizia
    "fora" sem dizer o que falta fazer para entrar.

    Aqui é a de uma pessoa só, com o ritmo diário: o que o piso pede por dia
    útil, o que ela vem fazendo por dia e quanto sobra por dia até o fim do
    período — a mesma leitura das outras metas.
    """
    if not dados:
        return
    el = _elegibilidade(dados, [username]).get(username)
    if not el:
        return

    st.markdown(f"#### 🚪 Entrar na meta do time — {_esc(nome)}")
    st.caption(
        "Bater a meta é do time. **Entrar nela é seu**: quem não chega ao "
        "mínimo da própria meta individual não recebe pela meta do mês, ainda "
        "que o time feche. São dois porteiros, e os dois valem para a Coletiva "
        f"(**{el['min_n']}%** da sua meta, até **{el['lim_adv_n']}** "
        f"advertência(s) no período) e para a MAXX (**{el['min_x']}%**, até "
        f"**{el['lim_adv_x']}**)."
    )

    uteis, decorridos = _dias_uteis_periodo(dados)
    meta, pts = el["meta"], el["pts"]
    # Advertência não tem card próprio aqui: a seção responde "eu entro na meta
    # do time?", e a resposta é a pontuação. O teto de advertências continua
    # valendo e continua aparecendo — no texto de cima e na faixa do veredito,
    # que é onde ele muda o "sim" para "não".

    if meta <= 0:
        st.info("Meta individual ainda não configurada para o período — sem "
                "ela não há como dizer se você entra na meta do time. "
                "Peça ao gestor para preencher em **Configuração de Metas**.")
        return

    _r_col = _ritmo_entrada(pts, meta * el["min_n"] / 100, uteis, decorridos)
    _r_mx = _ritmo_entrada(pts, meta * el["min_x"] / 100, uteis, decorridos)

    _cc, _cx = st.columns(2)
    with _cc:
        st.markdown('<div style="font-size:10px;font-weight:600;color:#1BAF7A;'
                    'text-transform:uppercase;letter-spacing:.5px;'
                    'margin-bottom:6px;">📋 Entrada na Meta Coletiva</div>',
                    unsafe_allow_html=True)
        st.markdown(_item_contribuicao(pts, meta, el["min_n"], ritmo=_r_col),
                    unsafe_allow_html=True)
    with _cx:
        st.markdown('<div style="font-size:10px;font-weight:600;color:#FFD700;'
                    'text-transform:uppercase;letter-spacing:.5px;'
                    'margin-bottom:6px;">⭐ Entrada na Meta MAXX</div>',
                    unsafe_allow_html=True)
        st.markdown(_item_contribuicao(pts, meta, el["min_x"], ritmo=_r_mx),
                    unsafe_allow_html=True)

    # O veredito por extenso, porque duas barras verdes ainda deixam a pergunta
    # "entao eu recebo ou nao?" no ar.
    #
    # Com o mes correndo, "fora" so vale para quem esta fora de verdade: no dia
    # 2 ninguem tem 80% da meta, e um 🚫 vermelho ali dizia a pessoa adiantada
    # que ela perdeu a meta. Advertencia e diferente — ela ja aconteceu, e o
    # excesso e vermelho no mesmo dia em que e lancado.
    def _veredito(entra, motivos, rotulo, cor, ritmo, adv_ok):
        if entra:
            texto = f"✅ Você está <b>dentro da {rotulo}</b> — os dois critérios ok."
            fundo, borda = f"{cor}15", cor
        elif (adv_ok and ritmo and ritmo["restantes"] > 0
                and ritmo["estado"] in ("acima", "dentro", "inicio")):
            texto = (f"⏳ Você ainda <b>não entrou na {rotulo}</b>, mas está no "
                     f"ritmo: faltam <b>{_n_br(ritmo['falta'])} pts</b> em "
                     f"{ritmo['restantes']} dia(s) útil(eis) — "
                     f"{_n_br(ritmo['por_dia_falta'])} pts por dia.")
            fundo, borda = f"{ritmo['cor']}15", ritmo["cor"]
        else:
            texto = (f"🚫 Hoje você está <b>fora da {rotulo}</b>: "
                     + _esc(" · ".join(motivos)))
            fundo, borda = "#E3494815", "#E34948"
        return (f'<div style="background:{fundo};border:1px solid {borda};'
                f'border-radius:8px;padding:9px 13px;font-size:11.5px;'
                f'margin-bottom:6px;">{texto}</div>')

    st.markdown(
        _veredito(el["entra_col"], el["motivos_col"], "Meta Coletiva", "#1BAF7A",
                  _r_col, el["advs"] <= el["lim_adv_n"])
        + _veredito(el["entra_maxx"], el["motivos_maxx"], "Meta MAXX", "#FFD700",
                    _r_mx, el["advs"] <= el["lim_adv_x"]),
        unsafe_allow_html=True)
    if uteis > 0 and decorridos < uteis:
        st.caption(
            f"Período com **{uteis} dias úteis**, **{decorridos}** já "
            "corridos — feriados já descontados. Enquanto o período corre, o "
            f"que vale é o ritmo: estar abaixo dos {el['min_n']}% no começo do "
            "mês não é estar fora, é estar no começo."
        )


# ── Comparativo: todo mundo, indicador a indicador ────────────────────────────

def _comparativo_linhas(dados):
    """Uma linha por colaborador, com todos os indicadores da meta.

    Cada indicador vira duas coisas: o VALOR, que e o que a pessoa fez, e o
    ATINGIMENTO de 0 a 100, que e o quanto disso a meta considera feito. O
    valor sozinho nao compara — 2 atrasos com teto de 10 e 2 com teto de 3 sao
    situacoes diferentes; o atingimento poe os dois na mesma regua.
    """
    users = list(_pc.MEMBROS_ATIVOS.keys())
    if not dados or not users:
        return [], {}

    cfg = dados[-1].get("cfg") or {}
    n_meses = max(1, len(dados))
    eleg = _elegibilidade(dados, users)
    try:
        ponto = _ponto_por_membro(dados, users)
    except Exception:
        ponto = None
    tem_ponto = bool(ponto and ponto.get("tem_ponto"))
    medias_exec = _media_execucao_por_membro(dados) or {}
    busca = _tempo_analise(dados)
    uteis, decorridos = _dias_uteis_periodo(dados)

    lim_tol = int(cfg.get("max_tol_normal", 15) or 0) * n_meses
    lim_atr = int(cfg.get("max_atr_normal", 10) or 0) * n_meses
    lim_adv = int(cfg.get("max_adv_normal", 2) or 0) * n_meses
    ocio_max = LIMITE_OCIOSIDADE_PCT

    def _teto(usado, limite):
        """0 a 100: cheio com zero ocorrencia, zero ao encostar no limite."""
        if limite <= 0:
            return 100.0 if not usado else 0.0
        return max(0.0, (1 - usado / limite) * 100)

    linhas = []
    for u in users:
        el = eleg.get(u) or {}
        pts = el.get("pts", 0.0)
        meta = el.get("meta", 0.0)
        pct_meta = el.get("pct", 0.0)

        _ocio = (float((ponto.get("pct_ocio") or {}).get(u, 0.0))
                 if tem_ponto else None)
        _tol = float((ponto.get("tol_mb") or {}).get(u, 0.0)) if tem_ponto else None
        _atr = float((ponto.get("atr_mb") or {}).get(u, 0.0)) if tem_ponto else None
        _advs = el.get("advs", 0)

        _real_ex = medias_exec.get(u)
        # O alvo do PERIODO, e nao o do ultimo mes: num trimestre em que o alvo
        # apertou de 108 para 90, cobrar os tres meses pelos 90 seria mudar a
        # regra depois do jogo. A media dos alvos e o equivalente, para tempo,
        # de somar as metas de pontuacao.
        _alvos = []
        for r in dados:
            _c = r.get("cfg") or {}
            _rf = float(_c.get(f"exec_ref_{u}", 0) or 0) or 120.0
            _a = mc.meta_execucao(_c, u, _rf)["alvo"]
            if _a:
                _alvos.append(_a)
        _alvo_ex = (sum(_alvos) / len(_alvos)) if _alvos else None
        _ref_ex = float(cfg.get(f"exec_ref_{u}", 0) or 0) or 120.0

        _cri = {"n": 0, "pts": 0.0}
        for r in dados:
            v = (r.get("demandas_criadas") or {}).get(u)
            if v:
                _cri["n"] += v["n"]
                _cri["pts"] += v["pts"]
        _bu = busca.get(u) or {"min": 0.0, "dias": 0}
        _por_dem = (_bu["min"] / _cri["n"]) if _cri["n"] else None

        # Atingimento de cada criterio. None = sem medicao, e ele fica FORA da
        # media em vez de entrar como zero: quem nao tem ponto no periodo nao e
        # improdutivo, e sem dado.
        at = {
            "pontuacao": min(pct_meta, 100.0) if meta > 0 else None,
            "ociosidade": (max(0.0, (1 - _ocio / ocio_max) * 100)
                           if _ocio is not None and ocio_max else None),
            "execucao": (min(_alvo_ex / _real_ex * 100, 100.0)
                         if (_real_ex and _alvo_ex) else None),
            "tolerancias": _teto(_tol, lim_tol) if _tol is not None else None,
            "atrasos": _teto(_atr, lim_atr) if _atr is not None else None,
            "advertencias": _teto(_advs, lim_adv),
        }
        _validos = [v for v in at.values() if v is not None]
        score = (sum(_validos) / len(_validos)) if _validos else 0.0

        linhas.append({
            "user": u, "nome": _pc.MEMBROS_ATIVOS.get(u, u),
            "score": score, "medidos": len(_validos), "at": at,
            "pts": pts, "meta": meta, "pct_meta": pct_meta,
            "entra_col": el.get("entra_col", False),
            "entra_maxx": el.get("entra_maxx", False),
            "ocio": _ocio, "tol": _tol, "atr": _atr, "advs": _advs,
            "exec_real": _real_ex, "exec_alvo": _alvo_ex,
            "criadas": _cri["n"], "criadas_pts": _cri["pts"],
            "busca_min": _bu["min"], "por_demanda": _por_dem,
            "ritmo": _ritmo_entrada(pts, meta * el.get("min_n", 80) / 100,
                                    uteis, decorridos) if meta > 0 else None,
        })

    ctx = {"lim_tol": lim_tol, "lim_atr": lim_atr, "lim_adv": lim_adv,
           "ocio_max": ocio_max, "tem_ponto": tem_ponto,
           "uteis": uteis, "decorridos": decorridos,
           "piso": int(cfg.get("min_contrib_normal", 80) or 0)}
    return linhas, ctx


def _card_ranking(titulo, sub, cor, itens, menor_melhor=False, rodape=""):
    """Um pódio de um assunto só: nome, valor e barra, do melhor para o pior.

    A barra mede sempre a MESMA coisa — quão perto do primeiro colocado —, e
    por isso a mais comprida é sempre a do topo, inclusive nos rankings em que
    menos é melhor. Barra proporcional ao valor cru inverteria a leitura
    justamente onde ela precisa ser óbvia.

    `itens` = [(nome, valor_ordenável, texto, bateu)]. Valor None é "sem
    medição": vai para o fim da lista, com um traço, e não disputa o pódio.

    `bateu` é o que pinta a linha: True verde, False vermelho, None cinza. O
    cinza não é um terceiro resultado — é a ausência de meta contra a qual
    comparar, e ele precisa se distinguir do vermelho justamente por isso.
    """
    VERDE, VERM, CINZA = "#1BAF7A", "#E34948", "#7A8B99"

    def _cor_linha(bateu):
        return CINZA if bateu is None else (VERDE if bateu else VERM)

    com = [i for i in itens if i[1] is not None]
    sem = [i for i in itens if i[1] is None]
    com.sort(key=lambda i: (i[1] if menor_melhor else -i[1]))
    if not com:
        corpo = ('<div style="font-size:11px;color:var(--ms-texto-sec);'
                 'padding:6px 0;">Sem medição no período.</div>')
    else:
        ref = com[0][1]
        corpo = ""
        for pos, (nome, val, txt, bateu) in enumerate(com, start=1):
            _c = _cor_linha(bateu)
            if menor_melhor:
                larg = (ref / val * 100) if val else 100.0
            else:
                larg = (val / ref * 100) if ref else 0.0
            larg = min(max(larg, 3.0), 100.0)
            medalha = ("🥇" if pos == 1 else "🥈" if pos == 2 else
                       "🥉" if pos == 3 else f'<span style="font-size:9px;'
                       f'color:var(--ms-texto-sec);">{pos}º</span>')
            _peso = "700" if pos == 1 else "400"
            corpo += (
                f'<div style="margin-bottom:7px;">'
                f'<div style="display:flex;align-items:baseline;gap:7px;'
                f'font-size:11.5px;">'
                f'<span style="width:17px;flex:none;">{medalha}</span>'
                f'<span style="flex:1;min-width:0;overflow:hidden;'
                f'text-overflow:ellipsis;white-space:nowrap;font-weight:{_peso};">'
                f'{_esc(nome)}</span>'
                f'<span style="flex:none;font-weight:700;color:{_c};">{txt}</span>'
                f'</div>'
                f'<div style="height:5px;border-radius:3px;margin-top:3px;'
                f'margin-left:24px;background:var(--ms-metric-bd);'
                f'overflow:hidden;"><div style="height:100%;border-radius:3px;'
                f'width:{larg:.1f}%;background:{_c};'
                f'opacity:{1 if pos == 1 else 0.8};"></div></div></div>')
        for nome, _v, txt, _b in sem:
            corpo += (
                f'<div style="display:flex;align-items:baseline;gap:7px;'
                f'font-size:11.5px;color:var(--ms-texto-sec);margin-bottom:7px;">'
                f'<span style="width:17px;flex:none;">–</span>'
                f'<span style="flex:1;">{_esc(nome)}</span>'
                f'<span style="flex:none;">{txt}</span></div>')

    return (
        f'<div style="background:var(--ms-metric-bg);border:1px solid '
        f'var(--ms-metric-bd);border-left:3px solid {cor};border-radius:10px;'
        f'padding:12px 14px;">'
        f'<div style="font-size:12.5px;font-weight:700;color:var(--ms-texto);'
        f'margin-bottom:1px;">{titulo}</div>'
        f'<div style="font-size:9.5px;color:var(--ms-texto-sec);'
        f'margin-bottom:10px;">{sub}</div>'
        + corpo
        + (f'<div style="font-size:9px;color:var(--ms-texto-sec);margin-top:8px;'
           f'padding-top:7px;border-top:1px solid var(--ms-divisor);">{rodape}'
           f'</div>' if rodape else "")
        + '</div>')


def _tabela_comparativo(linhas, ctx, ordem="Índice geral"):
    """Uma pessoa por linha, uma meta por coluna, tudo centrado na coluna.

    O limite de cada meta mora no CABEÇALHO, e não repetido em toda célula:
    "teto de 15" embaixo do título é a mesma informação dita uma vez, e é o que
    deixa a coluna estreita o bastante para o número ficar centrado embaixo do
    próprio título.

    Cada célula segue a regra da aba: verde bateu, vermelho não bateu, cinza
    não tem meta contra a qual comparar.
    """
    VERDE, VERM, CINZA = "#1BAF7A", "#E34948", "#7A8B99"

    def _chave(l):
        if ordem == "Pontuação":        return -l["pct_meta"]
        if ordem == "Ociosidade":       return (l["ocio"] is None, l["ocio"] or 0)
        if ordem == "Tempo de execução":
            return (l["exec_real"] is None, l["exec_real"] or 0)
        if ordem == "Tolerâncias":      return (l["tol"] is None, l["tol"] or 0)
        if ordem == "Atrasos":          return (l["atr"] is None, l["atr"] or 0)
        if ordem == "Advertências":     return l["advs"]
        if ordem == "Demandas geradas": return -l["criadas"]
        if ordem == "Tempo por demanda":
            return (l["por_demanda"] is None, l["por_demanda"] or 0)
        return -l["score"]
    ordenado = sorted(linhas, key=_chave)

    _tot_pts = sum(l["pts"] for l in linhas) or 1

    # (título, limite, função que devolve (texto, bateu)) — a ordem das colunas
    COLUNAS = [
        ("🏁 Índice geral", "média dos critérios com meta",
         lambda l: (f'{l["score"]:.0f}%', None)),
        ("📈 Pontuação", "meta somada no período",
         lambda l: (f'{_n_br(l["pts"])} pts',
                    l["meta"] > 0 and l["pts"] >= l["meta"])),
        ("🎯 % da meta", f'entra no time com {ctx["piso"]}%',
         lambda l: ((f'{l["pct_meta"]:.0f}%', l["pct_meta"] >= 100)
                    if l["meta"] > 0 else ("—", None))),
        ("💤 Ociosidade", f'teto de {ctx["ocio_max"]:.0f}%',
         lambda l: ((f'{l["ocio"]:.1f}%', l["ocio"] < ctx["ocio_max"])
                    if l["ocio"] is not None else ("—", None))),
        ("⚡ Tempo exec.", "contra o alvo do mês",
         lambda l: ((f'{l["exec_real"]:.0f} min',
                     (l["exec_real"] <= l["exec_alvo"]) if l["exec_alvo"] else None)
                    if l["exec_real"] else ("—", None))),
        ("🕐 Tolerâncias", f'teto de {ctx["lim_tol"]}',
         lambda l: ((f'{l["tol"]:.0f}', l["tol"] <= ctx["lim_tol"])
                    if l["tol"] is not None else ("—", None))),
        ("⏰ Atrasos", f'teto de {ctx["lim_atr"]}',
         lambda l: ((f'{l["atr"]:.0f}', l["atr"] <= ctx["lim_atr"])
                    if l["atr"] is not None else ("—", None))),
        ("🚫 Advert.", f'teto de {ctx["lim_adv"]}',
         lambda l: (f'{l["advs"]}', l["advs"] <= ctx["lim_adv"])),
        ("🚪 Entra na meta", "coletiva · MAXX",
         lambda l: (("✅" if l["entra_col"] else "🚫") + " · "
                    + ("⭐" if l["entra_maxx"] else "—"), l["entra_col"])),
        ("🤝 Contribuição", "fatia dos pontos do time",
         lambda l: (f'{l["pts"] / _tot_pts * 100:.0f}%', None)),
        ("🗃️ Cartões criados", "sem meta",
         lambda l: (f'{l["criadas"]}', None)),
        ("💰 Pontos gerados", "sem meta",
         lambda l: (f'{_n_br(l["criadas_pts"])}', None)),
        ("🔎 Garimpando", "sem meta",
         lambda l: (_fmt_hm(l["busca_min"]) if l["busca_min"] else "—", None)),
        ("⏱️ Por demanda", "sem meta",
         lambda l: (_fmt_hm(l["por_demanda"]) if l["por_demanda"] else "—", None)),
    ]

    # Cabecalho e celula usam o MESMO alinhamento e o mesmo padding: e isso que
    # poe o titulo em cima do numero, e nao ao lado dele.
    _pad = "padding:8px 12px;"
    cab = (f'<th style="{_pad}text-align:left;font-size:9px;'
           f'text-transform:uppercase;letter-spacing:.4px;'
           f'color:var(--ms-texto-sec);white-space:nowrap;">Colaborador</th>')
    for titulo, limite, _fn in COLUNAS:
        cab += (f'<th style="{_pad}text-align:center;vertical-align:bottom;">'
                f'<div style="font-size:10px;font-weight:700;'
                f'color:var(--ms-texto);white-space:nowrap;">{titulo}</div>'
                f'<div style="font-size:8.5px;font-weight:400;'
                f'color:var(--ms-texto-sec);white-space:nowrap;">{limite}</div>'
                f'</th>')

    corpo = ""
    for i, l in enumerate(ordenado, start=1):
        _m = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}º"
        fundo = "background:var(--ms-metric-bg);" if i % 2 else ""
        celulas = ""
        for _t, _lim, fn in COLUNAS:
            txt, bateu = fn(l)
            cor = CINZA if bateu is None else (VERDE if bateu else VERM)
            celulas += (f'<td style="{_pad}text-align:center;font-size:12.5px;'
                        f'font-weight:700;color:{cor};white-space:nowrap;">'
                        f'{txt}</td>')
        corpo += (
            f'<tr style="{fundo}border-top:1px solid var(--ms-divisor);">'
            f'<td style="{_pad}text-align:left;font-size:12.5px;'
            f'font-weight:700;white-space:nowrap;">{_m} {_esc(l["nome"])}</td>'
            + celulas + '</tr>')

    return (
        f'<div style="overflow-x:auto;">'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr style="background:var(--ms-metric-bg);">{cab}</tr></thead>'
        f'<tbody>{corpo}</tbody></table></div>')


def _rankings_por_topico(linhas, ctx):
    """Um pódio por assunto, em grade. É a resposta a "quem é o melhor em quê".

    A tabela larga responde "quanto" e obriga a comparar números coluna a
    coluna; o pódio responde "quem" de relance. São os mesmos dados — o que
    muda é a pergunta que cada forma responde sem esforço.

    Só três cores, e cada uma quer dizer uma coisa só: verde bateu a meta,
    vermelho não bateu, cinza não tem meta contra a qual comparar. Antes cada
    card tinha a cor do seu assunto, e a mesma paleta que servia para decorar
    era a que deveria avisar — roxo em "tolerâncias" não dizia nada sobre estar
    dentro ou fora.

    Num período de vários meses o veredito sai do montante, e não de mês a mês:
    as metas somam com os totais, e os tetos de tolerância e atraso já vêm
    multiplicados pelos meses.
    """
    CINZA = "#7A8B99"          # sem meta: informação, não julgamento
    NEUTRO = "var(--ms-texto-sec)"

    def _itens(valor, texto, bateu=None):
        """[(nome, valor_ordenavel, texto, bateu)] de cada pessoa."""
        fora = []
        for l in linhas:
            v = valor(l)
            fora.append((l["nome"], v,
                         texto(l) if v is not None else "—",
                         bateu(l) if (bateu and v is not None) else None))
        return fora

    _tot_pts = sum(l["pts"] for l in linhas) or 1

    cards = [
        # ── com meta: verde bateu, vermelho nao ──
        _card_ranking(
            "📈 Pontuação", "quem mais pontuou no período", NEUTRO,
            _itens(lambda l: l["pts"],
                   lambda l: f'{_n_br(l["pts"])} pts',
                   lambda l: l["meta"] > 0 and l["pts"] >= l["meta"]),
            rodape="meta de cada um, somada no período"),
        _card_ranking(
            "🎯 % da meta individual", "quanto cada um bateu da PRÓPRIA meta",
            NEUTRO,
            _itens(lambda l: l["pct_meta"] if l["meta"] > 0 else None,
                   lambda l: f'{l["pct_meta"]:.0f}%',
                   lambda l: l["pct_meta"] >= 100),
            rodape=f'verde a partir de 100% · entra na meta do time com '
                   f'{ctx["piso"]}%'),
        _card_ranking(
            "💤 Ociosidade", "menos tempo parado é melhor", NEUTRO,
            _itens(lambda l: l["ocio"],
                   lambda l: f'{l["ocio"]:.1f}%',
                   lambda l: l["ocio"] < ctx["ocio_max"]),
            menor_melhor=True,
            rodape=f'teto de {ctx["ocio_max"]:.0f}% do expediente'),
        _card_ranking(
            "⚡ Tempo de execução", "média por demanda · menos é melhor", NEUTRO,
            _itens(lambda l: l["exec_real"],
                   lambda l: f'{l["exec_real"]:.0f} min',
                   lambda l: (l["exec_real"] <= l["exec_alvo"]
                              if l["exec_alvo"] else None)),
            menor_melhor=True,
            rodape="cinza = mês sem alvo definido em Configuração de Metas"),
        _card_ranking(
            "🕐 Tolerâncias", "atrasos pequenos na entrada · menos é melhor",
            NEUTRO,
            _itens(lambda l: l["tol"], lambda l: f'{l["tol"]:.0f}',
                   lambda l: l["tol"] <= ctx["lim_tol"]),
            menor_melhor=True, rodape=f'teto de {ctx["lim_tol"]} no período'),
        _card_ranking(
            "⏰ Atrasos", "atrasos que pesam na meta · menos é melhor", NEUTRO,
            _itens(lambda l: l["atr"], lambda l: f'{l["atr"]:.0f}',
                   lambda l: l["atr"] <= ctx["lim_atr"]),
            menor_melhor=True, rodape=f'teto de {ctx["lim_atr"]} no período'),
        _card_ranking(
            "🚫 Advertências", "lançadas pelo gestor · menos é melhor", NEUTRO,
            _itens(lambda l: float(l["advs"]), lambda l: f'{l["advs"]}',
                   lambda l: l["advs"] <= ctx["lim_adv"]),
            menor_melhor=True, rodape=f'teto de {ctx["lim_adv"]} no período'),

        # ── sem meta: cinza, informacao ──
        _card_ranking(
            "🤝 Contribuição na meta do time",
            "fatia dos pontos da equipe que saiu de cada um", CINZA,
            _itens(lambda l: l["pts"],
                   lambda l: f'{l["pts"] / _tot_pts * 100:.0f}%'),
            rodape="não tem meta própria — depende do tamanho da equipe"),
        _card_ranking(
            "🗃️ Cartões criados", "quem mais abriu demanda", CINZA,
            _itens(lambda l: float(l["criadas"]), lambda l: f'{l["criadas"]}'),
            rodape="sem meta definida"),
        _card_ranking(
            "💰 Pontos gerados", "quanto valeram as demandas que abriu", CINZA,
            _itens(lambda l: l["criadas_pts"],
                   lambda l: f'{_n_br(l["criadas_pts"])} pts'),
            rodape="sem meta definida"),
        _card_ranking(
            "🔎 Tempo garimpando", "quanto do período passou procurando", CINZA,
            _itens(lambda l: l["busca_min"] or None,
                   lambda l: _fmt_hm(l["busca_min"])),
            menor_melhor=True,
            rodape="sem meta — menos só é melhor se as demandas vierem junto"),
        _card_ranking(
            "⏱️ Tempo por demanda encontrada",
            "busca ÷ demandas abertas · menos é melhor", CINZA,
            _itens(lambda l: l["por_demanda"],
                   lambda l: _fmt_hm(l["por_demanda"])),
            menor_melhor=True,
            rodape="sem meta — é o que diz se o garimpo foi bem gasto"),
    ]
    # 236px: tres colunas cabem nos ~750px que o Studio deixa com a coluna do
    # chat aberta (3x236 + 2x12 = 744). A grade continua elastica — em tela
    # cheia ela vira quatro, e num monitor menor volta para duas sozinha.
    return (f'<div style="display:grid;'
            f'grid-template-columns:repeat(auto-fit,minmax(236px,1fr));'
            f'gap:12px;margin-bottom:6px;">{"".join(cards)}</div>')


def _aba_comparativo(dados):
    """Todos os colaboradores lado a lado, indicador a indicador.

    O resumo comparativo antigo mostrava tres coisas — pontuacao, contribuicao
    e tempo medio — e nao dava para ordenar por nenhuma. A pergunta que o gestor
    faz no fim do mes e outra: quem esta produzindo mais e quem esta produzindo
    menos, considerando TUDO o que a meta cobra.

    O indice geral e a media dos seis criterios, cada um normalizado de 0 a 100
    contra o proprio limite. Criterio sem medicao fica de fora da media em vez
    de entrar como zero: quem nao tem ponto no periodo nao e improdutivo, e sem
    dado — e a coluna diz quantos dos seis entraram na conta.
    """
    if not dados:
        st.caption("Sem dados para exibir no período selecionado.")
        return
    linhas, ctx = _comparativo_linhas(dados)
    if not linhas:
        st.caption("Nenhum colaborador cadastrado na equipe.")
        return

    _rot = (dados[0]["label"] + " → " + dados[-1]["label"]) if len(dados) > 1 \
        else dados[-1]["label"]
    st.markdown("#### 🏁 Comparativo de colaboradores")
    st.caption(
        f"Período **{_rot}** · num período de vários meses o veredito sai do "
        "**montante**: as metas somam com os totais, e os tetos de tolerância, "
        "atraso e advertência já vêm multiplicados pelos meses. "
        f"Na tabela completa, o **índice geral** é a média de quanto cada um "
        "está longe do próprio limite nos seis critérios: 100% é o desempenho "
        "perfeito, e a distância entre duas pessoas é o que ordena a lista. "
        "**Ele não é a nota da meta** — quem tem 4% de ociosidade num teto de "
        "10% aparece com 58% ali e está perfeitamente dentro da regra. Quem "
        "diz se o critério foi cumprido é a **cor**: verde dentro, vermelho "
        "fora. As colunas de demanda são informação e ficam fora do índice — "
        "elas medem o que a pessoa abriu, não o que a meta cobra dela."
    )

    st.markdown(
        '<div style="display:flex;gap:16px;flex-wrap:wrap;font-size:11px;'
        'color:var(--ms-texto-sec);margin:2px 0 12px;">'
        '<span><b style="color:#1BAF7A;">■</b> bateu a meta</span>'
        '<span><b style="color:#E34948;">■</b> não bateu</span>'
        '<span><b style="color:#7A8B99;">■</b> indicador sem meta — '
        'informação, não cobrança</span></div>', unsafe_allow_html=True)
    st.markdown(_rankings_por_topico(linhas, ctx), unsafe_allow_html=True)

    # A tabela fica aberta: o ranking responde "quem" e ela responde "quanto",
    # e as duas perguntas sao feitas na mesma visita. Fechada, a segunda exigia
    # um clique que ninguem lembrava de dar.
    with st.expander("📋 Tabela completa — todos os indicadores lado a lado",
                     expanded=True):
        _op = ["Índice geral", "Pontuação", "Ociosidade", "Tempo de execução",
               "Tolerâncias", "Atrasos", "Advertências", "Demandas geradas",
               "Tempo por demanda"]
        ordem = st.selectbox("Ordenar por", _op, index=0, key="am_comp_ordem")
        st.markdown(_tabela_comparativo(linhas, ctx, ordem),
                    unsafe_allow_html=True)

    # O topo e o fim da lista, por extenso: a tabela responde "quanto", e isto
    # responde "e daí" — quem merece a conversa desta semana.
    _ord = sorted(linhas, key=lambda l: -l["score"])
    _top, _fim = _ord[0], _ord[-1]
    if len(_ord) > 1 and _top["score"] > _fim["score"]:
        _piores = sorted(
            [(k, v) for k, v in _fim["at"].items() if v is not None],
            key=lambda kv: kv[1])[:2]
        _nomes = {"pontuacao": "pontuação", "ociosidade": "ociosidade",
                  "execucao": "tempo de execução", "tolerancias": "tolerâncias",
                  "atrasos": "atrasos", "advertencias": "advertências"}
        _txt = " e ".join(f"<b>{_nomes[k]}</b> ({v:.0f}%)" for k, v in _piores)
        st.markdown(
            f'<div style="margin-top:12px;display:flex;gap:12px;flex-wrap:wrap;">'
            f'<div style="flex:1;min-width:260px;background:#1BAF7A12;'
            f'border:1px solid #1BAF7A55;border-radius:9px;padding:10px 14px;'
            f'font-size:12.5px;">🥇 <b>{_esc(_top["nome"])}</b> lidera com '
            f'<b>{_top["score"]:.0f}%</b> de índice geral.</div>'
            f'<div style="flex:1;min-width:260px;background:#E3494812;'
            f'border:1px solid #E3494855;border-radius:9px;padding:10px 14px;'
            f'font-size:12.5px;">📉 <b>{_esc(_fim["nome"])}</b> fecha a lista '
            f'com <b>{_fim["score"]:.0f}%</b> — o que mais pesa é {_txt}.</div>'
            f'</div>', unsafe_allow_html=True)


def _aba_desempenho(dados, dados_ano_full=None, carregar_periodo=None):
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
        st.caption("As duas metas do mês nas barras · o realizado na linha "
                   "laranja. Linha acima da barra azul, a Coletiva foi batida; "
                   "acima da verde, a MAXX.")
        st.markdown(_chart_pontuacao_meta(dados_ano), unsafe_allow_html=True)

        # A outra metade do que a meta coletiva cobra: a pontuacao diz quanto
        # foi entregue, isto diz em quanto tempo. So aparecia por pessoa.
        st.markdown("##### ⏳ Tempo médio de execução da equipe")
        st.caption("Referência e alvo do mês nas barras · o tempo que as "
                   "demandas realmente levaram na linha amarela. Aqui **quanto "
                   "mais baixo, melhor**: linha abaixo da barra verde é o alvo "
                   "batido.")
        st.markdown(_chart_tempo_medio_equipe(dados_ano), unsafe_allow_html=True)

        # A busca de demanda fica fora de todas as contas acima — e por isso
        # sumia da tela. Aqui ela tem numero proprio, sem entrar em nenhuma.
        st.markdown("##### 🔎 Busca de demandas")
        st.caption("Coluna **ANÁLISE DE DEMANDAS** · não pontua, não entra no "
                   "tempo de execução de ninguém nem no tempo médio da equipe. "
                   "Está aqui só para você ver quanto do dia ela consome.")
        st.markdown(_chart_analise_demandas(dados, _pc.MEMBROS_ATIVOS),
                    unsafe_allow_html=True)

    with row1_col2:
        st.markdown("#### 🎯 Índices Meta Coletiva")
        st.caption("Os seis tópicos cobrados na meta, para a Coletiva e para a MAXX.")
        st.markdown(_chart_indices_meta(dados), unsafe_allow_html=True)

        # O espaco que sobrava embaixo dos velocimetros. A pergunta que cabe
        # aqui e a da equipe inteira: quem alimenta a fila de demanda.
        st.markdown("##### 🗃️ Cartões criados por colaborador")
        st.caption("Quantos cartões cada um abriu no período e quantos pontos "
                   "eles geraram · cartão aberto pelo gestor não entra.")
        st.markdown(_chart_criacao_equipe(dados, _pc.MEMBROS_ATIVOS),
                    unsafe_allow_html=True)

    # A tabela "Quem entra na remuneracao da meta do time" saiu daqui: ela
    # listava a equipe inteira num painel que todos abrem. A mesma analise —
    # com o ritmo diario e o que ainda falta — vive agora no Desempenho
    # Individual, cada um com o seu.

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

def _secao_equipe():
    """Cadastro da equipe medida — quem entra nas metas, no placar e na ociosidade."""
    import equipe_config as _ec

    st.markdown("##### 👥 Equipe medida")
    st.caption(
        "Quem está aqui entra nas metas, no placar e na ociosidade. O "
        "**username do Trello** é a chave de tudo: tem que ser o @ exato, senão o "
        "trabalho da pessoa não é reconhecido. O **nome na RHiD** liga o relógio de "
        "ponto — use o primeiro nome como está cadastrado lá."
    )

    membros, mapa_rhid = _ec.carregar()
    if membros:
        _rhid_por_user = {u: n for n, u in mapa_rhid.items()}
        st.markdown("\n".join(
            f"- **{nome}** · Trello `{user}` · RHiD `{_rhid_por_user.get(user, '—')}`"
            for user, nome in membros.items()
        ))
    else:
        st.warning(
            "Nenhum colaborador cadastrado ainda — o painel está usando a equipe "
            "de origem do código (Myrella, Beatriz, Gabriel). Cadastre todos aqui, "
            "inclusive esses três, para a lista passar a valer."
        )

    with st.form("form_equipe"):
        e1, e2, e3 = st.columns([2, 2, 2])
        _user = e1.text_input("Username do Trello", placeholder="ex: gabriel_borges")
        _nome = e2.text_input("Nome no painel", placeholder="ex: Gabriel")
        _rhid = e3.text_input("Primeiro nome na RHiD", placeholder="ex: Gabriel")
        _c_at, _c_bp = st.columns(2)
        _ativo = _c_at.checkbox("Ativo (conta nas metas)", value=True)
        _funcao_in = st.text_input(
            "Colunas da função (opcional)",
            placeholder="CRIATIVO VÍDEO; CRIATIVO FOTOS; DESATIVAR",
            help="Separe por ponto e vírgula. Compara por início do nome, então "
                 "'CRIATIVO VÍDEO' pega 'CRIATIVO VÍDEO (80)' mesmo se o número "
                 "mudar. Deixe vazio para não restringir ninguém — em branco "
                 "significa sem restrição, e nada é marcado na tela.")
        _bate = _c_bp.checkbox(
            "Bate ponto no relógio", value=True,
            help="Desmarque para quem não usa a RHiD. Sem isso a pessoa aparece "
                 "com 0% de desempenho e 'Não registrado' em vermelho, como se "
                 "tivesse faltado.")
        if st.form_submit_button("Salvar colaborador", use_container_width=True):
            if not _user.strip() or not _nome.strip():
                st.error("Username do Trello e nome são obrigatórios.")
            else:
                try:
                    _ec.salvar(_user, _nome, _rhid, _ativo, _bate, _funcao_in)
                    _pc.recarregar_membros()
                    st.success(f"{_nome} salvo.")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Não consegui salvar: {str(ex)[:200]}")


def _secao_colunas(dados):
    """Prioridade, tempo estimado e espera de cada coluna — editáveis pelo gestor.

    Mostra ao lado a média REAL medida pelas etiquetas, para a calibragem sair do
    dado e não do chute. O estimado continua sendo a meta que o gestor define: se
    ele se ajustasse sozinho à média, time devagar viraria meta devagar.
    """
    import colunas_config as _cc

    st.markdown("##### 🗂️ Colunas do Trello")
    st.caption(
        "O tempo estimado é **sua meta**, não uma média automática. A média real "
        "medida aparece ao lado para você calibrar. **Espera** é tempo de terceiro "
        "(ex.: 36h de retorno da plataforma): não conta como trabalho e segura o "
        "cartão fora da fila até o prazo estar vencendo."
    )

    # Média real por coluna, do período analisado
    reais = {}
    for r in dados:
        for nl, tempos in (r.get("tempo_lista") or {}).items():
            reais.setdefault(nl, []).extend(tempos)

    try:
        do_board = _pc.colunas_do_board()
    except Exception:
        do_board = []
    # A tela mostra a uniao de tres fontes: o board agora, os valores de origem
    # no codigo e o que o gestor salvou na planilha. Uma coluna renomeada no
    # Trello continua vindo das duas ultimas — e ficava lado a lado com a nova,
    # com configuracao e sem cartao nenhum, sem nada dizendo qual era qual.
    salvas = _cc.carregar()
    try:
        _ocultas = _cc.ocultas()
    except Exception:
        _ocultas = set()
    todas = sorted((set(do_board) | set(_pc.COLUNAS_CONFIG) | set(salvas))
                   - _ocultas)
    fora_do_board = set(todas) - set(do_board) if do_board else set()
    if not todas:
        st.info("Não consegui listar as colunas do Trello agora.")
        return

    novas = [c for c in do_board if c not in _pc.COLUNAS_CONFIG and c not in salvas]
    if novas:
        st.warning(
            "**Colunas novas no Trello, ainda sem configuração:** "
            + ", ".join(novas)
            + ". Estão rodando com prioridade 5 e 1h de tempo estimado."
        )

    for nome in todas:
        cfg = _pc.cfg_coluna(nome)
        medidos = reais.get(nome) or []
        media = (sum(medidos) / len(medidos)) if medidos else None
        rotulo = nome if len(nome) <= 44 else nome[:43] + "…"
        real_txt = (f"{media/60:.1f}h real ({len(medidos)} cartões)"
                    if media else "sem medição no período")
        orfa = nome in fora_do_board
        if orfa:
            real_txt = "⚠️ não existe mais no Trello"

        with st.expander(f"{rotulo}  ·  {real_txt}", expanded=False):
            if orfa:
                st.warning(
                    "Esta coluna não está mais no board — provavelmente foi "
                    "renomeada. A configuração dela não é usada por cartão "
                    "nenhum. Configure a coluna com o nome novo e remova esta."
                )
                # O botao existia so para coluna que estava na planilha. Coluna
                # renomeada que continua escrita no codigo nao tinha linha para
                # apagar, e por isso aparecia sem saida nenhuma — que e o caso
                # que o gestor viu na tela. Agora sao dois passos: apagar a
                # linha, se houver, e marcar a coluna como oculta, que e o que
                # tira do codigo o poder de trazer ela de volta.
                if st.button("🗑️ Remover coluna", key=f"col_x_{nome}",
                             use_container_width=True):
                    _erro = ""
                    try:
                        if nome in salvas:
                            _cc.remover(nome)
                    except Exception as ex:
                        _erro = str(ex)[:200]
                    _ok, _msg = _cc.ocultar(nome)
                    if _ok and not _erro:
                        st.rerun()
                    else:
                        st.error(f"Não consegui remover: {_erro or _msg}")
            c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
            p = c1.number_input("Prioridade", 0, 10, int(cfg.get("prioridade", 5)),
                                key=f"col_p_{nome}")
            t = c2.number_input("Tempo estimado (min)", 0, 2000,
                                int(cfg.get("tempo_min", 60)), step=10,
                                key=f"col_t_{nome}")
            e = c3.number_input("Espera de terceiro (h)", 0, 336,
                                int(cfg.get("espera_h") or 0), step=1,
                                key=f"col_e_{nome}")
            if media:
                delta = media - t
                cor = "#1BAF7A" if delta <= 0 else "#E34948"
                c4.markdown(
                    f'<div style="font-size:11px;color:var(--ms-texto-sec);margin-top:28px;">'
                    f'Real: <b style="color:{cor};">{media:.0f}min</b><br>'
                    f'{"dentro" if delta <= 0 else f"+{delta:.0f}min acima"} do estimado</div>',
                    unsafe_allow_html=True,
                )
            if st.button("Salvar", key=f"col_s_{nome}", use_container_width=True):
                try:
                    _cc.salvar(nome, p, t, e or None)
                    st.success(f"{rotulo} salva.")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Não consegui salvar: {str(ex)[:200]}")

    # Esconder e uma decisao, e toda decisao erra. Sem o caminho de volta a
    # coluna sumia da tela junto com a configuracao dela, e o conserto seria
    # editar a planilha na mao.
    if _ocultas:
        with st.expander(f"🙈 Colunas removidas da tela ({len(_ocultas)})",
                         expanded=False):
            for _nm in sorted(_ocultas):
                _r1, _r2 = st.columns([6, 1])
                _r1.markdown(
                    f'<div style="padding:6px 0;font-size:13px;'
                    f'color:var(--ms-texto-sec);">{_esc(_nm)}</div>',
                    unsafe_allow_html=True)
                if _r2.button("↩️", key=f"col_v_{_nm}",
                              use_container_width=True,
                              help="Mostrar de novo"):
                    _ok, _msg = _cc.revelar(_nm)
                    st.rerun() if _ok else st.error(_msg)


def _secao_configuracao(dados=None):
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

    # Valor gravado fora da faixa do campo era corrigido em silencio pelo widget
    # e regravado assim — parecia que o numero mudava sozinho.
    _faixas = {"meta_maxx_pct": (100, 300)}
    _fora = []
    for _campo, (_mn, _mx) in _faixas.items():
        try:
            _v = float(cfg_atual.get(_campo, 0))
        except (TypeError, ValueError):
            continue
        if _v < _mn or _v > _mx:
            _fora.append(f"**{mc.LABELS.get(_campo, _campo)}** está gravado como "
                         f"`{_v:g}`, fora da faixa permitida ({_mn}–{_mx})")
    if _fora:
        st.error(
            "⚠️ Valor gravado fora da faixa — o campo abaixo aparece ajustado, e "
            "salvar vai gravar o valor ajustado:\n\n- " + "\n- ".join(_fora)
        )

    with st.expander("🔎 Valores realmente gravados neste mês", expanded=False):
        st.caption(
            "É o que está na planilha agora. Se algo aqui estiver diferente do que "
            "você digitou, é gravação errada — não cálculo."
        )
        st.code("\n".join(
            f"{mc.LABELS.get(k, k):46} = {cfg_atual.get(k)}"
            for k in mc.DEFAULTS
        ))

    st.markdown("##### 🛑 Paradas e períodos sem expediente")
    st.caption(
        "Queda de internet, falta de energia, emenda de feriado, férias "
        "coletivas: o trabalho para e os indicadores não. O tempo lançado aqui "
        "sai da conta de **atraso**, de **ociosidade** e de **tempo de "
        "execução** ao mesmo tempo — os três partem das mesmas janelas de "
        "expediente. Vale para a equipe inteira. O que a equipe pede para si "
        "está em **Ponto › 🙋 Abatimentos**."
    )
    # Fora do st.form: formulario aceita um botao de submit so, e aqui sao tres
    # acoes proprias (lancar parada, lancar periodo, apagar). Grava em aba
    # propria, na hora, sem depender do "Salvar configuração".
    try:
        import abonos as _ab
        _lista_ab = _ab.carregar()
    except Exception as _e_ab:
        _ab, _lista_ab = None, []
        st.warning(f"Não consegui ler os abonos: {str(_e_ab)[:150]}")
    else:
        # So o que parou o escritorio inteiro. Os pedidos da equipe tem dono e
        # vivem na fila do gestor, em Ponto > Abatimentos: misturados aqui,
        # apagar "a parada da tarde" apagaria o pedido de alguem.
        _lista_ab = [_a for _a in _lista_ab if not _a["user"]]

    if _ab:
        _t_dep, _t_ant = st.tabs(["⚡ Já aconteceu", "📅 Vai acontecer"])

        with _t_dep:
            st.caption("Para o que só dá para registrar depois de resolvido — "
                       "queda de internet, falta de energia.")
            _c1, _c2, _c3, _c4, _c5 = st.columns([1.2, .9, .9, 2.4, 1])
            _d1 = _c1.date_input("Dia", value=agora.date(), key="ab_p_data",
                                 format="DD/MM/YYYY")
            _h1 = _c2.time_input("Das", value=time(9, 0), key="ab_p_ini",
                                 step=300)
            _h2 = _c3.time_input("Até", value=time(11, 0), key="ab_p_fim",
                                 step=300)
            _m1 = _c4.text_input("O que houve", key="ab_p_motivo",
                                 placeholder="Queda de internet")
            _dur1 = ((_h2.hour * 60 + _h2.minute) - (_h1.hour * 60 + _h1.minute))
            if _dur1 > 0:
                _c4.caption(f"Parada de **{_fmt_hm(_dur1)}**")
            if _c5.button("Lançar", key="ab_p_add", use_container_width=True):
                if not (_m1 or "").strip():
                    st.error("Escreva o que houve — é o que justifica a parada.")
                else:
                    _ok, _msg = _ab.salvar(_d1, _h1, _h2, _m1,
                                           tipo=_ab.TIPO_PARADA)
                    st.rerun() if _ok else st.error(_msg)

        with _t_ant:
            st.caption("Para o que dá para programar — emenda de feriado, "
                       "feriado regional, férias coletivas. Dia inteiro, do "
                       "primeiro ao último.")
            _e1, _e2, _e3, _e4 = st.columns([1.2, 1.2, 2.7, 1])
            _di = _e1.date_input("Do dia", value=agora.date(), key="ab_f_ini",
                                 format="DD/MM/YYYY")
            _df = _e2.date_input("Até o dia", value=agora.date(),
                                 key="ab_f_fim", format="DD/MM/YYYY")
            _m2 = _e3.text_input("Situação", key="ab_f_motivo",
                                 placeholder="Emenda de feriado")
            _nd = (_df - _di).days + 1
            if _nd > 0:
                _e3.caption(f"**{_nd}** dia(s) sem expediente")
            if _e4.button("Lançar", key="ab_f_add", use_container_width=True):
                if not (_m2 or "").strip():
                    st.error("Escreva a situação.")
                else:
                    _ok, _msg = _ab.salvar(_di, _ab.DIA_INTEIRO[0],
                                           _ab.DIA_INTEIRO[1], _m2,
                                           data_fim=_df,
                                           tipo=_ab.TIPO_PERIODO)
                    st.rerun() if _ok else st.error(_msg)

        if not _lista_ab:
            st.caption("Nada lançado até agora.")
        for _a in _lista_ab[:15]:
            _l1, _l2 = st.columns([6, 1])
            _per = _a["tipo"] == _ab.TIPO_PERIODO
            if _per:
                _dias = (_a["data_fim"] - _a["data"]).days + 1
                _quando = (f'{_a["data"]:%d/%m/%Y}'
                           + (f' a {_a["data_fim"]:%d/%m/%Y}' if _dias > 1 else '')
                           + f' · {_dias} dia(s) inteiro(s)')
                _cor, _ico = "#8B5CF6", "📅"
            else:
                _dur = ((_a["fim"].hour * 60 + _a["fim"].minute)
                        - (_a["inicio"].hour * 60 + _a["inicio"].minute))
                _quando = (f'{_a["data"]:%d/%m/%Y} · {_a["inicio"]:%H:%M} às '
                           f'{_a["fim"]:%H:%M} · {_fmt_hm(_dur)}')
                _cor, _ico = "#EDA100", "⚡"
            _l1.markdown(
                f'<div style="padding:6px 0;font-size:13px;">'
                f'<span style="color:{_cor};">{_ico}</span> '
                f'<b>{_esc(_a["motivo"]) or "sem motivo"}</b>'
                f'<span style="color:var(--ms-texto-sec);"> — {_quando}</span>'
                f'</div>', unsafe_allow_html=True)
            if _l2.button("🗑️", key=f'ab_x_{_a["linha"]}',
                          use_container_width=True):
                _ok, _msg = _ab.remover_linha(_a["linha"])
                st.rerun() if _ok else st.error(_msg)

    with st.form(key=f"form_cfg_{ano_cfg}_{mes_cfg_num}"):
        st.markdown("##### 🏆 Meta Coletiva")
        c1, c2 = st.columns(2)
        nova_cfg = {}
        nova_cfg["meta_equipe"] = c1.number_input(
            mc.LABELS["meta_equipe"], min_value=0, value=int(cfg_atual["meta_equipe"]), step=100
        , key=f"cfg_meta_equipe_{ano_cfg}_{mes_cfg_num}")
        nova_cfg["meta_maxx_pct"] = c2.number_input(
            mc.LABELS["meta_maxx_pct"] + f" (atual: {cfg_atual['meta_maxx_pct']}% = {cfg_atual['meta_equipe'] * cfg_atual['meta_maxx_pct'] / 100:,.0f} pts)",
            min_value=100, max_value=300,
            value=min(300, max(100, int(cfg_atual["meta_maxx_pct"]))), step=5
        , key=f"cfg_meta_maxx_pct_{ano_cfg}_{mes_cfg_num}")

        st.markdown("##### 👤 Metas por colaborador")
        st.caption(
            "A lista vem da aba **equipe** da planilha. Cadastrou alguém lá, o campo "
            "aparece aqui — sem precisar mexer no código."
        )
        # A MAXX de cada um em 0 SEGUE a porcentagem coletiva — e sempre seguiu,
        # em _maxx_do_mes. A tela e que pedia o numero de novo, e ainda repetia a
        # pergunta numa segunda secao logo abaixo, que so conhecia tres pessoas e
        # sobrescrevia o que fosse digitado aqui. Agora o valor que a porcentagem
        # produz aparece ao lado do campo: nao ha o que preencher, so o que
        # conferir — e quem quiser um numero proprio para alguem digita ali.
        _pct_maxx = int(nova_cfg.get("meta_maxx_pct", 110) or 110)
        _pessoas = mc.campos_metas_pessoa()
        if not _pessoas:
            st.warning("Nenhum colaborador cadastrado na aba **equipe** da planilha.")
        for _k_meta, _k_maxx, _nome_p in _pessoas:
            _cn, _cm, _cx, _cr = st.columns([1, 1.5, 1.5, 1.6])
            _cn.markdown(
                f'<div style="padding-top:30px;font-size:13px;font-weight:600;">'
                f'{_nome_p}</div>', unsafe_allow_html=True)
            _meta_p = _cm.number_input(
                "Meta individual (pts)", min_value=0,
                value=int(cfg_atual.get(_k_meta, mc.META_INDIVIDUAL_PADRAO) or 0),
                step=100, key=f"cfg_{_k_meta}_{ano_cfg}_{mes_cfg_num}")
            _maxx_p = _cx.number_input(
                "MAXX própria (pts)", min_value=0,
                value=int(cfg_atual.get(_k_maxx, 0) or 0), step=100,
                key=f"cfg_{_k_maxx}_{ano_cfg}_{mes_cfg_num}",
                help="Deixe em 0 para seguir a porcentagem da MAXX coletiva. "
                     "Preencha só para dar um valor diferente a essa pessoa.")
            nova_cfg[_k_meta] = int(_meta_p)
            nova_cfg[_k_maxx] = int(_maxx_p)
            if _maxx_p:
                _txt = f"MAXX própria: <b>{_maxx_p:,.0f}</b> pts"
            else:
                _txt = (f"MAXX <b>{_pct_maxx * _meta_p / 100:,.0f}</b> pts "
                        f"· {_pct_maxx}% da meta")
            _cr.markdown(
                f'<div style="padding-top:32px;font-size:11px;'
                f'color:var(--ms-texto-sec);">{_txt.replace(",", ".")}</div>',
                unsafe_allow_html=True)

        st.markdown("##### ⏳ Tempo médio de execução")
        st.caption(
            "O tempo médio abaixo é **medido pelo Trello** (etiqueta EM ANDAMENTO), "
            "não digitado. Você preenche o **alvo em minutos** — em quanto tempo "
            "cada demanda deve fechar — e a **% de redução** aparece ao lado como "
            "informação, calculada contra a referência. Ao salvar, a referência do "
            "mês fica congelada: é ela que faz a meta parar de perseguir o próprio "
            "resultado. Quem ainda não tem cartão medido entra com 2h. "
            "**Alvo igual à referência = nenhuma redução cobrada no mês.**"
        )
        # De qual periodo vem a media importa: normalmente se configura o mes que
        # vem olhando a medicao do mes corrente. Dizer qual e evita configurar
        # setembro achando que a referencia era de setembro.
        _per = (dados or [{}])[-1].get("label", "")
        if _per:
            st.caption(f"Médias medidas no período analisado acima · **{_per}**")
        # A referencia e um campo, nao um valor calculado a cada salvamento.
        #
        # Ela e o tempo de fechamento do mes: a base sobre a qual a reducao e
        # cobrada. O tempo que o Trello mede serve para MEDIR o resultado contra
        # essa base — nao para virar a base de novo toda vez que esta tela abre.
        # Quando isso acontecia, quem melhorasse via o alvo fugir junto e a meta
        # quase batida virava outra sozinha.
        #
        # O campo vem preenchido com o valor ja gravado no mes; so na primeira
        # vez cai na media medida (ou 2h para quem ainda nao tem cartao medido).
        # Salvar outra coisa qualquer nao o altera, porque o que se grava e o que
        # esta no campo. Digitar nele e a unica forma de mudar a base — e serve
        # tambem para corrigir um valor preenchido errado.
        _medias_cfg = _media_execucao_por_membro(dados or [])
        _campos_exec = mc.campos_tempo_execucao()
        if not _campos_exec:
            st.caption("Nenhum colaborador cadastrado na aba **equipe** da planilha.")
        for _k_ref, _k_red, _nome_e in _campos_exec:
            _u_e = _k_ref[len("exec_ref_"):]
            _med = _medias_cfg.get(_u_e)
            _gravada = float(cfg_atual.get(_k_ref, 0) or 0)
            _inicial = _gravada if _gravada > 0 else (
                _med if _med else mc.EXEC_REF_PADRAO_MIN)

            _cn, _cr, _cp, _ca = st.columns([1.2, 1, 1, 1.8])
            _cn.markdown(
                f'<div style="padding-top:30px;font-size:13px;font-weight:600;">'
                f'{_nome_e}</div>', unsafe_allow_html=True)
            _ref = _cr.number_input(
                "Referência (min)", min_value=1, max_value=1440,
                value=int(round(_inicial)), step=5,
                key=f"cfg_{_k_ref}_{ano_cfg}_{mes_cfg_num}",
                help="Tempo de fechamento do mês — a base da meta. Edite aqui "
                     "para corrigir ou para começar um ciclo novo.")
            # O alvo e digitado em MINUTOS. Antes era a porcentagem de corte, e
            # a conta nunca devolvia o minuto que se queria: 108 min com "17%"
            # dava 1h29, nao a 1h30 pedida. Agora o minuto e o que se grava e a
            # porcentagem sai dele — e o mes ja configurado pela % continua
            # valendo, porque `mc.meta_execucao` cai nela quando nao ha alvo.
            _alvo_ant = mc.meta_execucao(cfg_atual, _u_e, _ref)["alvo"] or _ref
            _alvo_p = _cp.number_input(
                "Alvo (min)", min_value=1, max_value=1440,
                value=min(max(int(round(_alvo_ant)), 1), 1440), step=5,
                key=f"cfg_exec_alvo_{_u_e}_{ano_cfg}_{mes_cfg_num}",
                help="Em quantos minutos essa pessoa precisa fechar uma demanda. "
                     "Igual à referência = nenhuma redução cobrada no mês.")
            _red = (1 - _alvo_p / _ref) * 100 if _ref > 0 else 0.0
            nova_cfg[_k_ref] = int(_ref)
            nova_cfg[f"exec_alvo_{_u_e}"] = int(_alvo_p)
            # A % continua gravada, agora como consequencia do alvo: e o que se
            # le na planilha e no historico do mes.
            nova_cfg[_k_red] = round(max(_red, 0.0), 1)
            # Alvo abaixo de 10 min quase sempre e engano de digitacao, e a conta
            # nao tem como saber — mas quem le "alvo 0h06" sabe na hora.
            _curto = _alvo_p < 10
            _cor_p = "#E34948" if _curto else "var(--ms-texto-sec)"
            _txt_red = (f'reduzir <b>{_red:.0f}%</b>' if _red >= 0.5
                        else ('sem redução no mês' if _red > -0.5
                              else f'<b>{-_red:.0f}% acima</b> da referência'))
            _ca.markdown(
                f'<div style="padding-top:30px;font-size:11px;color:{_cor_p};">'
                f'{_fmt_hm(_ref)} → alvo <b>{_fmt_hm(_alvo_p)}</b> · {_txt_red}'
                + (f' · média medida: {_fmt_hm(_med)}' if _med
                   else ' · sem medição no período')
                + ('<br>alvo muito curto — confira os minutos' if _curto else '')
                + '</div>', unsafe_allow_html=True)

        # ── Tempo medio GERAL da equipe ──────────────────────────────────
        # Este e o campo que entra na meta coletiva, e ele estava perdido no
        # rodape da secao, com cara de nota de rodape das linhas de cima. Agora
        # tem titulo proprio e diz, no titulo, de onde ele conta.
        _ref_eq, _n_eq = _tempo_estimado_esperado(dados or [])
        _real_eq = _media_execucao_geral(dados or [])
        st.markdown("---")
        st.markdown("###### 🏁 Tempo médio geral da equipe — entra na Meta "
                    "Coletiva e na MAXX")
        st.caption(
            "Média de **todas** as demandas concluídas, não a de cada pessoa. "
            "A referência sai dos tempos estimados que você definiu por coluna, "
            "ponderados pelo volume de cartões concluídos — digite outra para "
            "usar a sua, ou deixe 0 para manter a calculada."
        )
        # A referencia da equipe agora e um campo, como a de cada pessoa. Ela era
        # so calculada — os tempos estimados por coluna ponderados pelo volume —
        # e nao havia onde digitar o tempo medio geral do mes nem corrigi-lo.
        # Zero segue significando "usar o calculado".
        _gravada_eq = float(cfg_atual.get("exec_ref_equipe", 0) or 0)
        _inicial_eq = _gravada_eq if _gravada_eq > 0 else (_ref_eq or 0)
        _ce0, _ce1, _ce2 = st.columns([1, 1, 2])
        nova_cfg["exec_ref_equipe"] = _ce0.number_input(
            "Equipe — referência (min)", min_value=0, max_value=1440,
            value=int(round(_inicial_eq)), step=5,
            key=f"cfg_exec_ref_equipe_{ano_cfg}_{mes_cfg_num}",
            help="Tempo médio geral por demanda que serve de base ao mês. "
                 "Deixe em 0 para usar o estimado por coluna.")
        _base_eq = nova_cfg["exec_ref_equipe"] or _ref_eq or 0
        _alvo_eq_ant = mc.meta_execucao(cfg_atual, "equipe", _base_eq)["alvo"]
        nova_cfg["exec_alvo_equipe"] = _ce1.number_input(
            "Equipe — alvo (min)", min_value=0, max_value=1440,
            value=min(int(round(_alvo_eq_ant or _base_eq or 0)), 1440), step=5,
            key=f"cfg_exec_alvo_equipe_{ano_cfg}_{mes_cfg_num}",
            help="Em quantos minutos a média geral por demanda precisa fechar "
                 "no mês. Igual à referência (ou 0) = nenhuma redução cobrada.")
        _alvo_eq = nova_cfg["exec_alvo_equipe"]
        _red_eq = ((1 - _alvo_eq / _base_eq) * 100
                   if (_base_eq and _alvo_eq) else 0.0)
        nova_cfg["exec_red_equipe"] = round(max(_red_eq, 0.0), 1)
        if not _base_eq:
            _ce2.caption("Sem cartões com tempo medido no período analisado — "
                         "digite a referência da equipe ao lado.")
        else:
            _origem_eq = ("digitada" if nova_cfg["exec_ref_equipe"]
                          else f"estimada por coluna ({_n_eq} cartões)")
            _txt_red_eq = (f"reduzir **{_red_eq:.0f}%**" if _red_eq >= 0.5
                           else "sem redução cobrada no mês")
            _txt_alvo_eq = _fmt_hm(_alvo_eq) if _alvo_eq else "—"
            _ce2.caption(
                f"Referência **{_fmt_hm(_base_eq)}** por demanda ({_origem_eq}) → "
                f"alvo **{_txt_alvo_eq}** · {_txt_red_eq}"
                + (f" · real medido hoje: **{_fmt_hm(_real_eq)}**"
                   if _real_eq is not None else ""))

        st.markdown("##### ⚠️ Limites de Penalidade")
        c1, c2 = st.columns(2)
        nova_cfg["max_pen_normal"] = c1.number_input(
            mc.LABELS["max_pen_normal"], min_value=0, value=int(cfg_atual["max_pen_normal"]), step=1
        , key=f"cfg_max_pen_normal_{ano_cfg}_{mes_cfg_num}")
        nova_cfg["max_pen_maxx"] = c2.number_input(
            mc.LABELS["max_pen_maxx"], min_value=0, value=int(cfg_atual["max_pen_maxx"]), step=1
        , key=f"cfg_max_pen_maxx_{ano_cfg}_{mes_cfg_num}")

        st.markdown("##### 🕐 Pontualidade")
        c1, c2, c3, c4 = st.columns(4)
        nova_cfg["max_tol_normal"] = c1.number_input(
            "Tolerâncias (Normal)", min_value=0, value=int(cfg_atual["max_tol_normal"]), step=1
        , key=f"cfg_max_tol_normal_{ano_cfg}_{mes_cfg_num}")
        nova_cfg["max_tol_maxx"] = c2.number_input(
            "Tolerâncias (MAXX)", min_value=0, value=int(cfg_atual["max_tol_maxx"]), step=1
        , key=f"cfg_max_tol_maxx_{ano_cfg}_{mes_cfg_num}")
        nova_cfg["max_atr_normal"] = c3.number_input(
            "Atrasos (Normal)", min_value=0, value=int(cfg_atual["max_atr_normal"]), step=1
        , key=f"cfg_max_atr_normal_{ano_cfg}_{mes_cfg_num}")
        nova_cfg["max_atr_maxx"] = c4.number_input(
            "Atrasos (MAXX)", min_value=0, value=int(cfg_atual["max_atr_maxx"]), step=1
        , key=f"cfg_max_atr_maxx_{ano_cfg}_{mes_cfg_num}")

        st.markdown("##### 🚫 Advertências")
        st.caption(
            "Advertência é disciplinar: uso de celular, falta ou atraso excessivo "
            "injustificado ou sem aviso prévio. Não sai de sistema nenhum — é "
            "lançada aqui, no mês em que aconteceu. Quem passa do limite **deixa "
            "de participar** da meta correspondente."
        )
        c1, c2 = st.columns(2)
        nova_cfg["max_adv_normal"] = c1.number_input(
            mc.LABELS["max_adv_normal"], min_value=0,
            value=int(cfg_atual.get("max_adv_normal", 2) or 0), step=1,
            key=f"cfg_max_adv_normal_{ano_cfg}_{mes_cfg_num}")
        nova_cfg["max_adv_maxx"] = c2.number_input(
            mc.LABELS["max_adv_maxx"], min_value=0,
            value=int(cfg_atual.get("max_adv_maxx", 1) or 0), step=1,
            key=f"cfg_max_adv_maxx_{ano_cfg}_{mes_cfg_num}")

        _campos_adv = mc.campos_advertencia()
        if not _campos_adv:
            st.caption("Nenhum colaborador cadastrado na aba **equipe** da planilha.")
        for _k_adv, _nome_a in _campos_adv:
            _ca1, _ca2, _ca3 = st.columns([1.2, 1, 2.6])
            _ca1.markdown(
                f'<div style="padding-top:30px;font-size:13px;font-weight:600;">'
                f'{_nome_a}</div>', unsafe_allow_html=True)
            _adv = _ca2.number_input(
                "Advertências no mês", min_value=0, max_value=20,
                value=int(cfg_atual.get(_k_adv, 0) or 0), step=1,
                key=f"cfg_{_k_adv}_{ano_cfg}_{mes_cfg_num}")
            nova_cfg[_k_adv] = int(_adv)
            _lim_n = int(nova_cfg["max_adv_normal"])
            _lim_x = int(nova_cfg["max_adv_maxx"])
            if _adv == 0:
                _txt_a, _cor_a = "Nenhuma advertência no mês", "var(--ms-texto-sec)"
            elif _adv > _lim_n:
                _txt_a, _cor_a = ("Fora da Meta Coletiva e da MAXX "
                                  f"(limite {_lim_n} e {_lim_x})", "#E34948")
            elif _adv > _lim_x:
                _txt_a, _cor_a = (f"Dentro da Coletiva (máx {_lim_n}) · "
                                  f"fora da MAXX (máx {_lim_x})", "#EDA100")
            else:
                _txt_a, _cor_a = (f"Dentro das duas metas "
                                  f"(máx {_lim_n} e {_lim_x})", "#1BAF7A")
            _ca3.markdown(
                f'<div style="padding-top:32px;font-size:11px;color:{_cor_a};">'
                f'{_txt_a}</div>', unsafe_allow_html=True)

        st.markdown("##### 🤝 Contribuição mínima para entrar na meta")
        st.caption(
            "Piso de participação: quem não chegar a essa fatia da **própria meta "
            "individual** não entra na meta coletiva do mês, mesmo que o time "
            "feche. Vale igual para a MAXX, com o piso dela."
        )
        c1, c2 = st.columns(2)
        nova_cfg["min_contrib_normal"] = c1.number_input(
            mc.LABELS["min_contrib_normal"], min_value=0, max_value=200,
            value=int(cfg_atual.get("min_contrib_normal", 80) or 0), step=5,
            key=f"cfg_min_contrib_normal_{ano_cfg}_{mes_cfg_num}")
        nova_cfg["min_contrib_maxx"] = c2.number_input(
            mc.LABELS["min_contrib_maxx"], min_value=0, max_value=200,
            value=int(cfg_atual.get("min_contrib_maxx", 100) or 0), step=5,
            key=f"cfg_min_contrib_maxx_{ano_cfg}_{mes_cfg_num}")

        st.markdown("##### 🔧 Outros Critérios")
        c1, c2, c3 = st.columns(3)
        nova_cfg["max_retrab_normal"] = c1.number_input(
            "Retrabalho máx % (Normal)", min_value=0, max_value=100,
            value=int(cfg_atual["max_retrab_normal"]), step=1
        , key=f"cfg_max_retrab_normal_{ano_cfg}_{mes_cfg_num}")
        nova_cfg["max_retrab_maxx"] = c2.number_input(
            "Retrabalho máx % (MAXX)", min_value=0, max_value=100,
            value=int(cfg_atual["max_retrab_maxx"]), step=1
        , key=f"cfg_max_retrab_maxx_{ano_cfg}_{mes_cfg_num}")
        nova_cfg["min_membro_pct"] = c3.number_input(
            "% mín. cartões com membro", min_value=0, max_value=100,
            value=int(cfg_atual["min_membro_pct"]), step=1
        , key=f"cfg_min_membro_pct_{ano_cfg}_{mes_cfg_num}")

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
    # Quem enxerga o desempenho dos OUTROS é quem tem perfil de administrador —
    # não uma lista de nomes escrita no código.
    #
    # A regra do gestor é: cada um vê a meta coletiva e a SUA meta individual;
    # ninguém vê o progresso do colega. A tela já respeitava isso, mas a decisão
    # vinha de _pc.MASTERS, um conjunto fixo no código, enquanto o perfil de
    # acesso vinha de outro lugar. Duas listas para a mesma pergunta é como se
    # perde o controle de quem vê o quê. Agora é o secret ADMINS que manda, e
    # MASTERS fica de reserva se a checagem de perfil falhar.
    # eh_gestor, nao is_admin: is_admin le a coluna `admin` da planilha, que e
    # editavel de dentro do proprio Studio. Se ela valesse aqui, quem entrasse
    # uma vez no Administrativo poderia se promover e passar a ver a meta
    # individual de cada colega. A regra e clara: cada um ve a sua, e ninguem ve
    # a do outro.
    try:
        import auth as _auth_am
        _eh_master = _auth_am.eh_gestor(usuario_logado)
    except Exception:
        _eh_master = _username_atual in {m.lower() for m in _pc.MASTERS}
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
    def _carregar_periodo(meses):
        """Reprocessa uma lista de meses reusando o board ja buscado.

        Nao custa requisicao nova: _buscar_board e tempos_do_board tem cache
        proprio, e o que roda de novo e a varredura dos cartoes em memoria. E o
        que permite a secao individual ter periodo proprio, independente do
        filtro coletivo la de cima.
        """
        return _analisar_meses(listas, cards, membros_map, id_p, id_t, id_i,
                               meses, _pc._processar)

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
    # A aba de configuração some para quem não é gestor, em vez de aparecer e
    # responder com cadeado. Aba que abre e nega deixa a pessoa achando que
    # quebrou — e ainda anuncia que existe um lugar onde se mexe nas metas.
    _ABAS = ["📋 Coletivo", "🎯 Individual", "📈 Desempenho"]
    if _eh_master:
        # Comparar pessoas e conversa de gestor. A tela mostra o desempenho de
        # todos lado a lado, e quem nao gerencia nao tem o que fazer com isso.
        _ABAS = _ABAS + ["🏁 Comparativo", "⚙️ Configuração de Metas"]
    _chave_aba = "_am_aba"
    if _chave_aba not in st.session_state:
        _da_url = str(st.query_params.get("aba_am", "")).strip()
        st.session_state[_chave_aba] = _da_url if _da_url in _ABAS else _ABAS[0]

    # A lista de abas encolhe para quem não é gestor. Se a seleção guardada for a
    # aba que sumiu, ela precisa ser trocada ANTES de o widget existir — escrever
    # na chave de um widget já instanciado derruba a tela.
    if st.session_state[_chave_aba] not in _ABAS:
        st.session_state[_chave_aba] = _ABAS[0]
    if st.session_state.get("am_aba_sel") not in _ABAS:
        st.session_state["am_aba_sel"] = st.session_state[_chave_aba]

    # Sem `default=`: passar default E escrever na chave do widget faz o
    # Streamlit avisar em inglês, numa caixa amarela no meio da tela, toda vez
    # que a página carrega. Com `key=`, o valor JÁ vem do session_state — o
    # default é redundante e é ele que dispara o aviso.
    _aba_sel = st.segmented_control(
        "Seção", _ABAS,
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
        # Uma visão de cada vez, escolhida aqui em cima.
        #
        # As duas viviam empilhadas: para olhar o individual de alguém era
        # preciso rolar a coletiva inteira, e a cada troca de colaborador a
        # tela voltava para o topo e a rolagem recomeçava. Além do trabalho,
        # era tempo — o corpo das duas era montado a cada clique.
        _mb_opcoes_des = list(_pc.MEMBROS_ATIVOS.keys())
        _mb_nomes_des  = [_pc.MEMBROS_ATIVOS[u] for u in _mb_opcoes_des]
        _c_vis, _c_col = st.columns([1.2, 1.4])
        _vis = _c_vis.radio(
            "O que você quer ver", ["👥 Análise coletiva", "🎯 Análise individual"],
            horizontal=True, key="des_visao")
        _individual = _vis.endswith("individual")

        _mb_u_des, _mb_nome_des = None, ""
        if _individual:
            if _eh_master:
                # O seletor mora na mesma linha da visão: escolher a pessoa é
                # parte de escolher o que ver, não um passo depois.
                _mb_nome_des = _c_col.selectbox(
                    "👤 Colaborador", _mb_nomes_des, key="des_ind_sel")
                _mb_u_des = _mb_opcoes_des[_mb_nomes_des.index(_mb_nome_des)]
            else:
                _mb_u_des    = _username_atual
                _mb_nome_des = _pc.MEMBROS_ATIVOS.get(_mb_u_des, _mb_u_des)
                _c_col.caption(f"Exibindo seus dados: **{_mb_nome_des}**")

        st.markdown("---")
        if not _individual:
            _aba_desempenho(dados, _carregar_ano_full(),
                            carregar_periodo=_carregar_periodo)
        elif _mb_u_des:
            st.markdown(f"#### 📈 Desempenho Individual — {_esc(_mb_nome_des)}")
            # Usa o período selecionado (dados) — não o ano completo —
            # para evitar mostrar meses sem meta individual configurada.
            _desempenho_individual(dados, _mb_u_des, _mb_nome_des,
                                   carregar_periodo=_carregar_periodo,
                                   dono=(_mb_u_des == _username_atual))
        else:
            st.info("Selecione um colaborador para ver o desempenho individual.")

    elif len(_ABAS) > 3 and _aba_sel == _ABAS[3]:
        if _eh_master:
            _aba_comparativo(dados)
        else:
            st.warning("Seção disponível apenas para gestores.")

    elif len(_ABAS) > 4 and _aba_sel == _ABAS[4]:
        # Só chega aqui quem é gestor: a aba nem entra na lista dos outros, e
        # _navegar recusa rótulo fora da lista. A checagem fica assim mesmo —
        # é do lado do servidor, não some se alguém mexer na URL.
        if _eh_master:
            _secao_configuracao(dados)
            st.markdown("---")
            _secao_equipe()
            st.markdown("---")
            _secao_colunas(dados)
        else:
            st.warning("🔒 Configuração de metas restrita ao gestor.")
