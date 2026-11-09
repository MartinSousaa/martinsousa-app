"""ads_diagnostico.py — o que o Studio enxerga de ADS, sem perguntar ao dono.

O PEDIDO (dono, 05/11)
----------------------
"Preciso saber o que falta ou precisa para mapear o ADS" — e, na resposta a
uma lista de perguntas: "Não é mais fácil trazer o que o sistema consegue
acessar ao invés de eu ficar respondendo?". Era. As credenciais (planilha,
tokens do ML) moram no Railway; só o Studio em produção as tem. Então é ele
quem diz o que vê.

TRÊS FONTES, E NENHUMA CONTA NOVA
---------------------------------
    o ADS que saiu da conta    lançamentos com finalidade ADS (extratos e
                               faturas), estorno abatendo — `lancamentos`
    a publicidade do ML        aba ADS E CROSS, grupo PUBLICIDADE —
                               `visao_geral.mercado_livre`, a mesma leitura
                               da Visão Geral
    as contas do ML            aba `ml_tokens` — quais autorizaram o
                               "Sistema MS" e com que escopo. Token NUNCA
                               aparece na tela: só se existe.
"""
import streamlit as st


def ads_dos_lancamentos(lancs):
    """{"por_nome", "por_conta", "por_mes", "total", "linhas"}. Pura.

    Só finalidade ADS. Saída soma; estorno (entrada ADS) abate, no mês em que
    cai — a regra da meta de gastos.
    """
    import lancamentos as _lan
    por_nome, por_conta, por_mes = {}, {}, {}
    total, n = 0.0, 0
    for l in lancs or []:
        if str(l.get("finalidade") or "").strip().upper() != "ADS":
            continue
        v = -float(l.get("valor") or 0.0)
        nome = (str(l.get("favorecido") or "").strip()
                or str(l.get("descricao") or "").strip()[:40] or "(sem nome)")
        conta = str(l.get("conta") or "").strip() or "(sem conta)"
        mes = _lan.mes_de(l)
        por_nome[nome] = por_nome.get(nome, 0.0) + v
        por_conta[conta] = por_conta.get(conta, 0.0) + v
        por_mes[mes] = por_mes.get(mes, 0.0) + v
        total += v
        n += 1
    r = lambda d: {k: round(v, 2) for k, v in d.items()}
    return {"por_nome": r(por_nome), "por_conta": r(por_conta),
            "por_mes": r(por_mes), "total": round(total, 2), "linhas": n}


def vence_txt(v):
    """O `expira_em` da aba `ml_tokens` legível em Brasília. Pura.

    Quem grava é `ml_api._guardar` via `bling_api.vencimento`: um EPOCH, que a
    planilha devolve como número ou texto ("1793925014.63"). O print de 06/11
    mostrou o número cru — o teste antigo usava uma data que eu escrevi.
    """
    from datetime import datetime as _dt
    import placar_core as _pc
    try:
        return _dt.fromtimestamp(float(v), _pc.FUSO).strftime("%d/%m %H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return str(v or "")


def contas_ml(regs):
    """[(conta, situação, apelido, user_id, permite ADS, vence)] das 4. Pura.

    Nunca devolve token: só se ele existe. Do escopo, só a pergunta que
    importa aqui — a autorização inclui publicidade (`mktp:ads`)?
    """
    import ml_api as _ml
    fora = []
    for c in _ml.CONTAS:
        r = (regs or {}).get(c) or {}
        tem = bool(str(r.get("refresh_token") or "").strip())
        fora.append((c.upper(), "autorizada" if tem else "não autorizada",
                     str(r.get("apelido") or ""), str(r.get("user_id") or ""),
                     "sim" if "mktp:ads" in str(r.get("escopo") or "") else "não",
                     vence_txt(r.get("expira_em"))))
    return fora


@st.cache_data(ttl=120, show_spinner=False)
def _dados(ano):
    """(ads, publicidade_ml, contas, avisos). Cache de 120 s: a tela de
    ADS-Cross redesenha a cada anexo."""
    import lancamentos as _lan
    import ml_api as _ml
    import visao_geral as _vg
    avisos = []
    try:
        lancs = _lan.aplicar_cadastro(
            [l for l in _lan.carregar() if _lan.mes_de(l).startswith(f"{int(ano)}-")])
        ads = ads_dos_lancamentos(lancs)
    except Exception as e:
        ads = ads_dos_lancamentos([])
        avisos.append(f"lançamentos: {type(e).__name__}")
    plan, av = _vg.da_planilha()
    avisos += av
    pub = {m: g.get("PUBLICIDADE", 0.0)
           for m, g in _vg.mercado_livre(plan.get("ADS E CROSS"), ano).items()}
    try:
        contas = contas_ml(_ml._todas())
    except Exception as e:
        contas = contas_ml({})
        avisos.append(f"contas do ML: {type(e).__name__}")
    return ads, pub, contas, avisos


def _esc(t):
    import html as _h
    return _h.escape(str(t))


def _dinheiro(v):
    return ("− " if v < 0 else "") + "R$ " + f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def html(ads, pub, contas, ano, api=None):
    """As fontes lado a lado. `api` = `ml_ads.buscar(...)`, quando o botão
    já foi apertado; sem ele a coluna da API não aparece. Pura."""
    import ml_ads as _mla
    from headcount import _tabela_html
    MES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set",
           "out", "nov", "dez")
    nomes = sorted(ads["por_nome"].items(), key=lambda x: -x[1])
    t1 = (_tabela_html(["Quem recebeu (como o extrato escreve)", "Total no ano"],
                       [[n, _dinheiro(v)] for n, v in nomes], esquerda=1)
          if nomes else "<p>Nenhum lançamento com finalidade ADS no ano.</p>")
    api_mes, parcial = _mla.por_mes(api) if api is not None else ({}, set())
    meses = sorted(set(ads["por_mes"]) | {f"{int(ano)}-{m:02d}" for m in pub}
                   | {f"{int(ano)}-{m:02d}" for m in api_mes})
    cab = ["Mês", "ADS pago (extratos e faturas)", "Publicidade ML (planilha ADS E CROSS)"]
    if api is not None:
        cab.append("Publicidade ML (direto do ML)")

    guardado = set().union(*[set(d.get("guardado") or ()) for d in (api or {}).values()]) \
        if api else set()
    fora_j = sorted(set().union(*[set(d.get("fora_janela") or ()) for d in (api or {}).values()])) \
        if api else []

    def _api(m):
        k = int(m[5:7])
        if k not in api_mes:
            return "fora dos 90 dias do ML" if k in fora_j else "—"
        return (_dinheiro(api_mes[k]) + (" (parcial)" if k in parcial else "")
                + (" (guardado)" if k in guardado else ""))
    t2 = _tabela_html(
        cab,
        [[f"{MES[int(m[5:7]) - 1]}/{m[:4]}",
          _dinheiro(ads["por_mes"].get(m, 0.0)),
          _dinheiro(pub.get(int(m[5:7]), 0.0))] + ([_api(m)] if api is not None else [])
         for m in meses if m[:4] == str(ano)],
        esquerda=1) if meses else ""
    t3 = _tabela_html(["Conta", "Situação", "Apelido no ML", "user_id",
                       "Autorizou publicidade", "Token vence"],
                      [list(c) for c in contas], esquerda=1)
    t4 = ""
    if api is not None:
        t4 = ("<p><b>4 · O que o ML respondeu</b> — conta a conta; aviso é o que o ML "
              "disse, sem tradução.</p>" + _tabela_html(
                  ["Conta", "Anunciante", "Total no ano", "Caminho que respondeu", "Avisos"],
                  [[c.upper(), d.get("anunciante") or "—",
                    _dinheiro(sum(d.get("por_mes", {}).values())),
                    d.get("caminho") or "—",
                    " · ".join(_esc(a) for a in d.get("avisos", [])) or "—"]
                   for c, d in api.items()], esquerda=1))
    contas_txt = " · ".join(f"{k}: {_dinheiro(v)}" for k, v in
                            sorted(ads["por_conta"].items(), key=lambda x: -x[1]))
    return (f"<p><b>1 · ADS que saiu da conta em {ano}:</b> {_dinheiro(ads['total'])} "
            f"em {ads['linhas']} lançamento(s).</p>"
            + (f"<p style='font-size:12px'>Por onde saiu: {contas_txt}</p>" if contas_txt else "")
            + t1
            + f"<p><b>2 · Mês a mês</b> — a publicidade do ML é paga pelo saldo do Mercado "
              f"Pago e não passa no extrato: vem da planilha ou, pelo botão acima, direto "
              f"do ML.</p>"
            + ("<p style='font-size:12px'>O ML só devolve os <b>últimos 90 dias</b>. Cada mês "
               "fechado que ele responde fica guardado no Studio (aba ml_ads_mes): o histórico "
               "se forma daqui para a frente. Antes da janela, vale a planilha.</p>"
               if api is not None else "") + t2
            + "<p><b>3 · Contas do Mercado Livre no Studio</b> — autorizada é a que tem token "
              "gravado; o vencimento se renova sozinho a cada 6 h.</p>" + t3 + t4)


def mostrar(ano):
    """O bloco na tela ADS-Cross. Só leitura."""
    with st.expander("🔎 Diagnóstico de ADS — o que o Studio enxerga hoje", expanded=False):
        ads, pub, contas, avisos = _dados(int(ano))
        api = None
        if st.button("Buscar a publicidade direto no Mercado Livre", key="adsd_buscar_ml"):
            st.session_state["adsd_api_ligada"] = True
        if st.session_state.get("adsd_api_ligada"):
            import ml_ads as _mla
            import placar_core as _pc
            hoje = _pc.agora_br()
            # Só depois do botão: até 48 idas ao ML. Depois, cache de 1 h.
            api = _mla.buscar(int(ano), hoje.month if hoje.year == int(ano) else 12,
                              hoje.day if hoje.year == int(ano) else 31)
            # GUARDA o mês fechado: o ML esquece depois de 90 dias. A leitura
            # do que já está guardado tem cache; só escreve o que é novo.
            try:
                ja = _mla.guardados(int(ano))
                novas = _mla.a_guardar(api, int(ano),
                                       hoje.month if hoje.year == int(ano) else 13, ja)
                if novas:
                    _mla.guardar(novas, hoje.strftime("%d/%m/%Y %H:%M"))
                    ja = _mla.guardados(int(ano))
                api = _mla.com_guardados(api, ja)
            except Exception as e:
                st.caption(f"⚠️ Não guardei a publicidade lida: {type(e).__name__}: {str(e)[:100]}")
        st.markdown(html(ads, pub, contas, int(ano), api), unsafe_allow_html=True)
        for a in avisos:
            st.caption(f"⚠️ Não li: {a}")


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # Linhas na forma de `lancamentos.carregar` — data, valor negativo na
    # saída, conta como o Studio grava (inter-…, cartão · …).
    _l = [{"data": "2026-10-03", "valor": -500.0, "finalidade": "ADS",
           "favorecido": "SHOPEE ADS", "conta": "inter-116183837"},
          {"data": "2026-10-10", "valor": -300.0, "finalidade": "ads",
           "favorecido": "", "descricao": "FACEBK *ADS (2) + Jóias?",
           "conta": "cartão · Fatura.pdf"},
          {"data": "2026-10-20", "valor": 100.0, "finalidade": "ADS",
           "favorecido": "SHOPEE ADS", "conta": "inter-116183837"},
          {"data": "2026-09-01", "valor": -50.0, "finalidade": "MERCADORIA",
           "favorecido": "X", "conta": "inter-1"}]
    _a = ads_dos_lancamentos(_l)
    ok("só finalidade ADS, e o estorno abate", _a["total"] == 700.0 and _a["linhas"] == 3)
    ok("sem favorecido, o nome sai da descrição (inclusive com + ( ) ?)",
       _a["por_nome"].get("FACEBK *ADS (2) + Jóias?") == 300.0)
    ok("por mês pela data do lançamento", _a["por_mes"] == {"2026-10": 700.0})
    ok("por conta, para ver por onde saiu", _a["por_conta"]["inter-116183837"] == 400.0)

    # As contas do ML na forma da aba `ml_tokens` (`ml_api.COLUNAS`).
    _regs = {"ml1": {"conta": "ml1", "access_token": "SEGREDO-A", "refresh_token": "SEGREDO-R",
                     "escopo": "offline_access read urn:ml:mktp:ads:/read-write", "user_id": 123,
                     "apelido": "LOJA1",
                     # como a aba devolve: epoch em TEXTO (ml_api._guardar, RAW)
                     "expira_em": "1793925014.6316743"}}
    _c = contas_ml(_regs)
    ok("as quatro contas aparecem, autorizadas ou não",
       [x[0] for x in _c] == ["ML1", "ML2", "ML3", "ML4"]
       and _c[0][1] == "autorizada" and _c[1][1] == "não autorizada")
    _h = html(_a, {10: 1234.5}, _c, 2026)
    ok("o token NUNCA vai para a tela", "SEGREDO" not in _h)
    ok("a publicidade do ML da planilha aparece no mês dela", "1.234,50" in _h)
    ok("o vencimento sai em Brasília, não o número cru",
       "05/11 21:30" in _h and "1793925014" not in _h)
    ok("diz se a autorização inclui publicidade", _c[0][4] == "sim" and _c[1][4] == "não")
    ok("sem o botão, a coluna da API não aparece", "(direto do ML)" not in _h)
    _api = {"ml1": {"anunciante": "777", "caminho": "/advertising/x", "por_mes": {10: 300.0, 11: 50.0},
                    "avisos": []},
            "ml2": {"anunciante": "888", "caminho": "/advertising/x", "por_mes": {10: 20.0},
                    "avisos": ["mês 11: Mercado Livre respondeu 500: <erro> & cia"]}}
    _h2 = html(_a, {10: 1234.5}, _c, 2026, _api)
    ok("com o botão, a publicidade do ML entra no mês, somando as contas",
       "(direto do ML)" in _h2 and "320,00" in _h2)
    ok("mês em que uma conta falhou aparece como parcial", "50,00 (parcial)" in _h2)
    ok("o aviso do ML vai escapado (não quebra o HTML)",
       "&lt;erro&gt; &amp; cia" in _h2 and "<erro>" not in _h2)
    ok("o HTML com a API não tem linha só de espaço", all(x.strip() for x in _h2.split("\n")))
    # 09/11: a janela de 90 dias do ML e o mês guardado, pela cadeia
    # (`ml_ads.com_guardados` de verdade).
    import ml_ads as _mla_t
    _api3 = _mla_t.com_guardados(
        {"ml1": {"anunciante": "777", "caminho": "/x", "por_mes": {10: 300.0},
                 "avisos": [], "fora_janela": [6, 7], "cortados": set()}},
        {"ml1": {6: 4500.0}})
    _a3 = dict(_a, por_mes={"2026-06": 1.0, "2026-07": 1.0, "2026-10": 1.0})
    _h3 = html(_a3, {}, _c, 2026, _api3)
    ok("mês guardado aparece marcado; o que saiu da janela e não foi guardado diz isso",
       "4.500,00 (guardado)" in _h3 and "fora dos 90 dias do ML" in _h3
       and "últimos 90 dias" in _h3)
    ok("o HTML não tem linha só de espaço",
       all(x.strip() for x in _h.split("\n")))
    ok("ano sem ADS diz isso, e não desenha tabela vazia",
       "Nenhum lançamento" in html(ads_dos_lancamentos([]), {}, _c, 2026))

    import inspect as _insp
    import fatura_ml_tela as _fmt
    ok("o diagnóstico está na tela ADS-Cross, antes de qualquer retorno",
       _insp.getsource(_fmt.pagina).index("_adsd.mostrar(")
       < _insp.getsource(_fmt.pagina).index("return"))
    print(f"\nfalhas: {falhas}")
    raise SystemExit(1 if falhas else 0)
