"""custos_studio.py — quanto o Studio custa, por serviço, ferramenta e pessoa.

Dono, 27/10: o Google cobrava a API do Gemini no cartão pessoal dele, R$ 500 a
R$ 1.000 por mês, e ninguém sabia de onde vinha. Layout aprovado no mesmo dia
(opção B: área do total + composição do mês).

DE ONDE VEM CADA NÚMERO
-----------------------
- PAGO: o que saiu no extrato e nos cartões para cada serviço, casado pelo
  nome (`REGRAS`, com a mesma comparação das assinaturas, `assinaturas._casa`).
  É o único número que bate com a fatura — então é o total da tela.
- DIVISÃO entre ferramentas e pessoas: o pago da Anthropic repartido pelo uso
  que `uso_ia` registra. Sem tabela de preço inventada: o total sempre fecha
  com o que saiu.
- IMAGEM E VÍDEO (OpenAI e Gemini): sem divisão. Esses arquivos não registram
  uso (dono, 27/10: "não mexa em imagens"), então o pago aparece inteiro.

AS REGRAS SÃO PALPITE CONFERÍVEL
--------------------------------
O nome com que cada serviço aparece no extrato não foi visto num extrato real.
Por isso a tela mostra, em cada serviço, as linhas que casaram: nome errado
aparece na hora, em vez de virar número errado em silêncio.
"""
import streamlit as st

# serviço -> (palavras que casam, palavras que tiram)
REGRAS = {
    "OpenAI": (("OPENAI",), ("CHATGPT",)),
    "Gemini": (("GOOGLE CLOUD", "GEMINI", "GOOGLE AI STUDIO"), ()),
    "Anthropic": (("ANTHROPIC",), ("CLAUDE AI", "CLAUDE MAX", "CLAUDE PRO")),
    "Railway": (("RAILWAY",), ()),
    "SerpAPI": (("SERPAPI",), ()),
}
# Ordem e cores do gráfico aprovado (paleta validada para o fundo escuro).
CORES = {"OpenAI": "#3987e5", "Gemini": "#d95926", "Anthropic": "#199e70",
         "Railway": "#c98500", "SerpAPI": "#d55181"}
IMAGEM = ("OpenAI", "Gemini")
# Saída custa 5× a entrada nos modelos Sonnet: é o peso do rateio por tokens.
PESO_SAIDA = 5


# ── Contas puras ─────────────────────────────────────────────────────────────
def servico_do_lancamento(lanc):
    """O serviço deste lançamento, ou ''. Saída só; entrada não é custo. Pura."""
    import assinaturas as _as
    if _as._valor_de_saida(lanc) <= 0:
        return ""
    for serv, (sim, nao) in REGRAS.items():
        if any(_as._casa(lanc, {"favorecido": n}) for n in nao):
            continue
        if any(_as._casa(lanc, {"favorecido": s}) for s in sim):
            return serv
    return ""


def pago_por_servico(lancs):
    """({serviço: R$}, {serviço: [lançamentos]}) de uma lista de um mês. Pura."""
    import assinaturas as _as
    tot, linhas = {}, {}
    for l in lancs or []:
        s = servico_do_lancamento(l)
        if s:
            tot[s] = round(tot.get(s, 0.0) + _as._valor_de_saida(l), 2)
            linhas.setdefault(s, []).append(l)
    return tot, linhas


def rateio(uso, pago_anthropic, ano, mes):
    """O pago da Anthropic dividido pelo uso registrado no mês. Pura.

    Devolve ({ferramenta: R$}, {usuario: R$}). Sem uso registrado, o pago fica
    numa linha só ("sem registro"), em vez de sumir.
    """
    alvo = f"{ano:04d}-{mes:02d}"
    pesos_f, pesos_u = {}, {}
    for r in uso or []:
        if str(r.get("servico")) != "Anthropic" or not str(r.get("quando", "")).startswith(alvo):
            continue
        try:
            p = float(r.get("entrada") or 0) + PESO_SAIDA * float(r.get("saida") or 0)
        except (TypeError, ValueError):
            continue
        f = str(r.get("ferramenta") or "—")
        u = str(r.get("usuario") or "—")
        pesos_f[f] = pesos_f.get(f, 0.0) + p
        pesos_u[u] = pesos_u.get(u, 0.0) + p
    total = sum(pesos_f.values())
    if not total:
        return ({"sem registro de uso": pago_anthropic} if pago_anthropic else {}), {}
    return ({f: round(pago_anthropic * p / total, 2) for f, p in pesos_f.items()},
            {u: round(pago_anthropic * p / total, 2) for u, p in pesos_u.items()})


def usos_no_mes(uso, ano, mes):
    """{(ferramenta, serviço): chamadas} no mês. Pura."""
    alvo = f"{ano:04d}-{mes:02d}"
    fora = {}
    for r in uso or []:
        if str(r.get("quando", "")).startswith(alvo):
            k = (str(r.get("ferramenta") or "—"), str(r.get("servico") or "—"))
            fora[k] = fora.get(k, 0) + 1
    return fora


def meses_ate(ano, mes, n):
    fora, a, m = [], ano, mes
    for _ in range(n):
        fora.append((a, m))
        m -= 1
        if m == 0:
            a, m = a - 1, 12
    return list(reversed(fora))


def _brl(v, casas=0):
    from rotulos import brl
    return brl(v, casas)


MESES = ["", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set",
         "out", "nov", "dez"]


def svg_historico(serie):
    """O gráfico da opção B: área do total, mês a mês. `serie` = [(rótulo, R$)]. Pura."""
    if not serie:
        return ""
    W, H, ml, mr, mt, mb = 660, 250, 74, 40, 34, 34
    vmax = max(v for _, v in serie) or 1.0
    passo = 10 ** max(len(str(int(vmax))) - 1, 1)
    vmax = (int(vmax / passo) + 1) * passo
    ph, n = H - mt - mb, len(serie)
    slot = (W - ml - mr) / max(n - 1, 1)
    X = lambda i: ml + slot * i
    Y = lambda v: mt + ph - v / vmax * ph
    pts = [(X(i), Y(v)) for i, (_, v) in enumerate(serie)]

    def curva(p):
        d = f"M{p[0][0]:.1f},{p[0][1]:.1f}"
        for i in range(1, len(p)):
            (x0, y0), (x1, y1) = p[i - 1], p[i]
            cx = (x0 + x1) / 2
            d += f" C{cx:.1f},{y0:.1f} {cx:.1f},{y1:.1f} {x1:.1f},{y1:.1f}"
        return d
    o = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
         f'aria-label="Custo total do Studio por mês">'
         '<defs><linearGradient id="csA" x1="0" y1="0" x2="0" y2="1">'
         '<stop offset="0" stop-color="#3987e5" stop-opacity=".45"/>'
         '<stop offset="1" stop-color="#3987e5" stop-opacity="0"/></linearGradient></defs>']
    for k in range(0, 5):
        v = vmax * k / 4
        yy = Y(v)
        o.append(f'<line x1="{ml}" x2="{W - mr}" y1="{yy:.1f}" y2="{yy:.1f}" '
                 f'stroke="#45474a" stroke-dasharray="{"0" if k == 0 else "2 5"}"/>')
        o.append(f'<text x="{ml - 10}" y="{yy + 4:.1f}" text-anchor="end" '
                 f'font-size="11" fill="#9aa0a6">{_brl(v)}</text>')
    if len(pts) > 1:
        o.append(f'<path d="{curva(pts)} L{pts[-1][0]:.1f},{Y(0):.1f} '
                 f'L{pts[0][0]:.1f},{Y(0):.1f} Z" fill="url(#csA)"/>')
        o.append(f'<path d="{curva(pts)}" fill="none" stroke="#3987e5" stroke-width="2.5"/>')
    for i, ((x, yv), (rot, v)) in enumerate(zip(pts, serie)):
        ult = i == n - 1
        o.append(f'<circle cx="{x:.1f}" cy="{yv:.1f}" r="{6 if ult else 4}" fill="#3987e5" '
                 f'stroke="#333436" stroke-width="2"><title>{rot}: {_brl(v, 2)}</title></circle>')
        o.append(f'<text x="{x:.1f}" y="{yv - 12:.1f}" text-anchor="middle" font-size="12" '
                 f'font-weight="700" fill="#e8eaed">{_brl(v)}</text>')
        o.append(f'<text x="{x:.1f}" y="{H - 10}" text-anchor="middle" font-size="12" '
                 f'fill="{"#e8eaed" if ult else "#9aa0a6"}">{rot}</text>')
    o.append('</svg>')
    return "".join(o)


def html_composicao(pago):
    """A barra 100% do mês, com a legenda de valor e %. Pura."""
    tot = sum(pago.values())
    if not tot:
        return ""
    ordem = [s for s in REGRAS if pago.get(s)]
    barra = "".join(f'<div style="flex:{pago[s]};background:{CORES[s]}" '
                    f'title="{s}: {_brl(pago[s], 2)}"></div>' for s in ordem)
    leg = "".join(
        f'<span style="white-space:nowrap"><span style="display:inline-block;width:9px;'
        f'height:9px;border-radius:50%;background:{CORES[s]};margin-right:6px"></span>'
        f'<b>{s}</b> {_brl(pago[s])} · {pago[s] / tot * 100:.0f}%</span>' for s in ordem)
    return ('<div style="display:flex;height:14px;border-radius:7px;overflow:hidden;'
            f'gap:2px;margin:14px 0 8px">{barra}</div>'
            f'<div style="display:flex;gap:14px;flex-wrap:wrap;font-size:13px">{leg}</div>')


# ── A tela ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _lancamentos_por_mes(meses):
    # O MÊS DO CAIXA, e não o da compra: a compra no cartão pesa no mês da
    # fatura (`lancamentos.mes_de`). É a mesma regra do resto do Studio.
    import lancamentos as _lan
    todos = _lan.carregar()
    return {m: [l for l in todos if _lan.mes_de(l) == f"{m[0]:04d}-{m[1]:02d}"]
            for m in meses}


def pagina(usuario_logado=None):
    import auth
    import placar_core as _pc
    import uso_ia as _uso
    if not auth.eh_dono(usuario_logado):
        st.error("Acesso restrito ao dono do Studio.")
        return
    st.markdown("### 💸 Custos do Studio")
    agora = _pc.agora_br()
    meses = tuple(meses_ate(agora.year, agora.month, 6))
    try:
        por_mes = _lancamentos_por_mes(meses)
    except Exception as e:
        st.error(f"Não consegui ler os extratos: {str(e)[:160]}")
        return
    pagos = {m: pago_por_servico(por_mes.get(m))[0] for m in meses}
    atual, anterior = meses[-1], meses[-2]
    pago_atual, linhas_atual = pago_por_servico(por_mes.get(atual))
    t_atual, t_ant = sum(pago_atual.values()), sum(pagos[anterior].values())
    st.caption(f"{MESES[atual[1]]}/{atual[0]} até hoje · pago de verdade, pelo "
               "extrato e pelos cartões já importados")

    c1, c2, c3 = st.columns(3)
    c1.metric("Pago no mês", _brl(t_atual, 2))
    c2.metric(f"Mês passado ({MESES[anterior[1]]})", _brl(t_ant, 2))
    _img = sum(pago_atual.get(s, 0) for s in IMAGEM)
    c3.metric("Imagem e vídeo no mês", _brl(_img, 2),
              f"{_img / t_atual * 100:.0f}% do total" if t_atual else None,
              delta_color="off")

    # O sinal que explica o cartão do dono: a reserva custando mais que o
    # motor principal quer dizer que a OpenAI está falhando e tudo cai nela.
    if pago_atual.get("Gemini", 0) > pago_atual.get("OpenAI", 0) > 0 or \
            (pago_atual.get("Gemini", 0) and not pago_atual.get("OpenAI")):
        st.error("**O Gemini, que é só a reserva das imagens, custou mais que a "
                 "OpenAI, que é o motor principal.** Quando a OpenAI falha (sem "
                 "crédito, chave recusada), toda imagem cai no Gemini. Confira o "
                 "saldo e a recarga automática da OpenAI.")

    col_g, col_t = st.columns([1.25, 1])
    with col_g:
        st.markdown("**Custo total · últimos 6 meses**")
        serie = [(MESES[m[1]], sum(pagos[m].values())) for m in meses]
        st.markdown(svg_historico(serie) + html_composicao(pago_atual),
                    unsafe_allow_html=True)
    with col_t:
        st.markdown("**Por ferramenta** · " + MESES[atual[1]])
        try:
            uso = _uso.carregar()
        except Exception:
            uso = []
        por_f, por_u = rateio(uso, pago_atual.get("Anthropic", 0.0), *atual)
        chamadas = usos_no_mes(uso, *atual)
        linhas = [{"ferramenta": f, "serviço": "Anthropic",
                   "usos": sum(n for (ff, s), n in chamadas.items() if ff == f and s == "Anthropic"),
                   "custo": _brl(v, 2)} for f, v in sorted(por_f.items(), key=lambda x: -x[1])]
        if _img:
            linhas.insert(0, {"ferramenta": "Imagem e vídeo", "serviço": "OpenAI + Gemini",
                              "usos": None, "custo": _brl(_img, 2)})
        for s in ("Railway", "SerpAPI"):
            if pago_atual.get(s):
                linhas.append({"ferramenta": {"Railway": "Hospedagem",
                                              "SerpAPI": "Pesquisa de concorrentes"}[s],
                               "serviço": s,
                               "usos": chamadas.get(("Pesquisa de concorrentes", s)),
                               "custo": _brl(pago_atual[s], 2)})
        if linhas:
            import pandas as _pd
            st.dataframe(_pd.DataFrame(linhas), use_container_width=True, hide_index=True)
        else:
            st.caption("Nenhum pagamento destes serviços no mês ainda.")
        if por_u:
            st.markdown("**Por pessoa** · só textos e chat (Anthropic)")
            import pandas as _pd
            st.dataframe(_pd.DataFrame(
                [{"quem": u, "custo": _brl(v, 2)} for u, v in sorted(por_u.items(), key=lambda x: -x[1])]),
                use_container_width=True, hide_index=True)
        st.caption("Imagem e vídeo não têm divisão por pessoa: aqueles arquivos "
                   "não registram uso. O uso dos textos e do chat conta a partir "
                   "de 27/10.")

    with st.expander("🔎 Que linhas do extrato entraram em cada serviço"):
        if not linhas_atual:
            st.caption("Nenhuma linha casou neste mês.")
        for s, ls in linhas_atual.items():
            st.markdown(f"**{s}** · {_brl(pago_atual[s], 2)}")
            for l in ls:
                st.caption(f"{l.get('data', '')} · {l.get('favorecido') or l.get('descricao', '')}"
                           f" · {_brl(abs(float(l.get('valor') or 0)), 2)}")
        st.caption("Palavras que casam: " + "; ".join(
            f"{s}: {', '.join(r[0])}" + (f" (menos {', '.join(r[1])})" if r[1] else "")
            for s, r in REGRAS.items()) + ". Nome errado aqui? Me avise com o print.")


if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # Lançamentos na forma que `lancamentos.carregar` grava (saída negativa
    # no extrato, positiva na fatura do cartão).
    _l = [{"data": "2026-09-28", "descricao": "GOOGLE *CLOUD 1A2B", "valor": 120.0, "tipo": "fatura 2026-10"},
          {"data": "2026-10-05", "descricao": "OPENAI *CHATGPT SUBSCR", "valor": 217.0, "tipo": "fatura 2026-10"},
          {"data": "2026-10-06", "descricao": "OPENAI", "valor": -262.5, "tipo": ""},
          {"data": "2026-10-07", "descricao": "CLAUDE.AI SUBSCRIPTION", "valor": 500.0, "tipo": "fatura 2026-10"},
          {"data": "2026-10-08", "descricao": "ANTHROPIC", "valor": 248.0, "tipo": "fatura 2026-10"},
          {"data": "2026-10-09", "descricao": "RAILWAY", "valor": 139.0, "tipo": "fatura 2026-10"},
          {"data": "2026-10-10", "descricao": "GOOGLE ADS", "valor": 999.0, "tipo": "fatura 2026-10"},
          {"data": "2026-10-11", "descricao": "OPENAI ESTORNO", "valor": 50.0, "tipo": "entrada"}]
    # A forma e o mês vêm de `lancamentos` (valor float; compra no cartão
    # carrega o mês da fatura em `tipo`). A compra de 28/09 pesa em outubro.
    import lancamentos as _lan_t
    ok("mês do caixa: a compra de setembro na fatura de outubro entra em outubro",
       all(_lan_t.mes_de(x) == "2026-10" for x in _l))
    _p, _ls = pago_por_servico(_l)
    ok("pago: ChatGPT e Claude (assinaturas pessoais) ficam de fora",
       _p.get("OpenAI") == 262.5 and _p.get("Anthropic") == 248.0)
    ok("pago: Google Ads não vira Gemini", _p.get("Gemini") == 120.0)
    ok("pago: entrada não é custo", sum(_p.values()) == 262.5 + 248 + 120 + 139)
    ok("pago: cada serviço guarda as linhas que casaram", len(_ls["Gemini"]) == 1)

    _uso = [{"quando": "2026-10-05 10:00:00", "usuario": "beatriz", "ferramenta": "Descrição",
             "servico": "Anthropic", "entrada": 1000, "saida": 200},
            {"quando": "2026-10-06 10:00:00", "usuario": "luiz", "ferramenta": "Título",
             "servico": "Anthropic", "entrada": 1000, "saida": 0},
            {"quando": "2026-09-30 10:00:00", "usuario": "luiz", "ferramenta": "Título",
             "servico": "Anthropic", "entrada": 99999, "saida": 0},
            {"quando": "2026-10-06 11:00:00", "usuario": "luiz", "ferramenta": "Pesquisa de concorrentes",
             "servico": "SerpAPI", "unidades": 1}]
    _f, _u = rateio(_uso, 300.0, 2026, 10)
    ok("rateio: o total fecha com o pago, e outro mês não entra",
       abs(sum(_f.values()) - 300) < 0.05 and _f["Descrição"] == 200.0 and _f["Título"] == 100.0)
    ok("rateio: por pessoa, a mesma conta", _u == {"beatriz": 200.0, "luiz": 100.0})
    ok("rateio: sem uso registrado o pago não some",
       rateio([], 248.0, 2026, 10) == ({"sem registro de uso": 248.0}, {}))
    ok("usos: conta chamadas por ferramenta e serviço no mês",
       usos_no_mes(_uso, 2026, 10)[("Pesquisa de concorrentes", "SerpAPI")] == 1)
    ok("meses: seis, terminando no atual, virando o ano",
       meses_ate(2027, 2, 6) == [(2026, 9), (2026, 10), (2026, 11), (2026, 12), (2027, 1), (2027, 2)])
    _svg = svg_historico([("set", 1640.0), ("out", 1284.0)])
    ok("gráfico: valores no formato do Studio e o mês atual destacado",
       "R$ 1.640" in _svg and "R$ 1.284" in _svg and _svg.startswith("<svg"))
    ok("composição: % de cada serviço, na ordem do gráfico",
       "OpenAI</b> R$ 262 · 51%" in html_composicao({"OpenAI": 262.0, "Anthropic": 248.0}))
    print("\nfalhas:", falhas)
    raise SystemExit(1 if falhas else 0)
