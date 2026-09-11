"""headcount.py — Até quando o aporte cobre o time, e quanto ele rendeu.

A PERGUNTA
----------
Foi feito um aporte para expandir e registrar o time. Todo mês o custo desse
time sai de lá. A pergunta é uma só, e ela tem prazo:

    quantos meses ainda restam antes de o dinheiro acabar?

O QUE ENTRA NA CONTA
--------------------
    custo do mês  =  colaboradores marcados «No aporte»
                     +  o acréscimo na mensalidade da contabilidade

Quem não está no aporte fica de fora — é uma coluna na tabela de
colaboradores, e não um nome escrito aqui: quem está fora hoje pode entrar
amanhã, e lista de gente dentro do código já escondeu duas pessoas do painel
nesta base.

COMO O RENDIMENTO APARECE SEM NINGUÉM DIGITAR
---------------------------------------------
O gestor informa duas coisas: o que colocou (aporte, com data) e quanto tem
hoje (saldo, com data). O resto é subtração:

    esperado sem render  =  tudo que entrou  −  o custo de cada mês decorrido
    rendimento           =  saldo informado  −  esperado sem render

Ou seja, o rendimento é o que sobrou além do que a conta previa. Não há campo
de "quanto rendeu", e é de propósito: o gestor já sabe o saldo — pedir também o
rendimento seria pedir a mesma informação duas vezes, e as duas passariam a
discordar.

POR QUE O SALDO É INFORMADO, E NÃO CALCULADO
--------------------------------------------
Porque o dinheiro está aplicado, e só o banco sabe quanto rendeu. Um saldo
projetado pelo Studio seria um palpite com cara de extrato — e é justamente o
tipo de número que se usa para decidir contratação.
"""

from datetime import date, datetime, timezone, timedelta

import pandas as pd
import streamlit as st

ABA_MOVIMENTOS = "headcount_movimentos"
ABA_PARAMS = "headcount_parametros"

COLUNAS = ["tipo", "data", "valor", "observacao", "atualizado_em",
           "atualizado_por"]

# «Aporte» é dinheiro entrando na conta de investimento. «Saldo» é uma leitura:
# quanto havia lá naquela data, já com rendimento e já com as retiradas do mês.
# As retiradas não se digitam — elas são o custo do time, que o Studio calcula.
TIPOS = ["Aporte", "Saldo"]

FUSO = timezone(timedelta(hours=-3))


def _aj():
    import ajustes
    return ajustes


def _num(v, padrao=0.0):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return padrao
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace("R$", "").replace(" ", "")
    if not t:
        return padrao
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return padrao


def _brl(v):
    return "R$ " + f"{float(v):,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")


# ── Contas ───────────────────────────────────────────────────────────────────

def parametros_padrao():
    return {"contabilidade_extra": 0.0, "contabilidade_extra_desde": ""}


def contabilidade_no_mes(params, ano, mes):
    """O acréscimo da contabilidade naquele mês. Zero antes da vigência."""
    p = {**parametros_padrao(), **(params or {})}
    valor = max(_num(p.get("contabilidade_extra")), 0.0)
    if valor <= 0:
        return 0.0
    desde = _aj().mes_de(p.get("contabilidade_extra_desde"))
    if not desde:
        # Sem mês de início o acréscimo valeria desde sempre, inclusive antes
        # de o quadro existir — e o aporte pareceria durar menos do que dura.
        return 0.0
    return valor if (int(ano), int(mes)) >= desde else 0.0


def custo_do_mes(ano, mes, params=None, colaboradores_df=None, taxas=None,
                 ajustes_df=None):
    """O que o aporte paga naquele mês: o time coberto mais a contabilidade."""
    import colaboradores as _co
    df = _co.carregar() if colaboradores_df is None else colaboradores_df
    linhas = _co.folha_clt(df, ano, mes, taxas, ajustes_df)
    time = sum(l["total"] for l in linhas if l.get("no_aporte", True))
    return round(time + contabilidade_no_mes(params, ano, mes), 2)


def _meses_entre(inicio, fim):
    """Lista de (ano, mes) de `inicio` até `fim`, ambos incluídos."""
    if not inicio or not fim or fim < inicio:
        return []
    fora, atual = [], inicio
    while atual <= fim:
        fora.append(atual)
        atual = (atual[0] + (atual[1] == 12), atual[1] % 12 + 1)
    return fora


def resumo(movimentos, params=None, colaboradores_df=None, taxas=None,
           ajustes_df=None, hoje=None):
    """O balanço inteiro: quanto entrou, quanto saiu, o que sobrou e o que rendeu.

    O rendimento sai de uma subtração, não de um campo: é o que o saldo tem
    além do que a conta previa. Pedi-lo ao gestor seria pedir duas vezes a
    mesma informação, e as duas passariam a discordar.
    """
    aj = _aj()
    d = pd.DataFrame(movimentos)
    vazio = {"aportado": 0.0, "saldo": 0.0, "saldo_em": None,
             "custo_acumulado": 0.0, "esperado": 0.0, "rendimento": 0.0,
             "rendimento_pct": 0.0, "custo_mensal": 0.0, "meses_cobertos": None,
             "primeiro_aporte": None, "meses_decorridos": 0}
    if d.empty:
        return vazio

    aportes, saldos = [], []
    for _, r in d.iterrows():
        m = aj.mes_de(r.get("data"))
        v = _num(r.get("valor"))
        if not m or v <= 0:
            continue
        (aportes if str(r.get("tipo", "")).strip() == "Aporte" else saldos).append((m, v))
    if not aportes:
        return vazio

    primeiro = min(m for m, _ in aportes)
    aportado = round(sum(v for _, v in aportes), 2)

    # A leitura mais recente do saldo. Sem nenhuma, o saldo é o que entrou —
    # ninguém disse ainda que saiu alguma coisa.
    if saldos:
        saldo_em, saldo = max(saldos, key=lambda x: x[0])
    else:
        saldo_em, saldo = primeiro, aportado

    # O custo corre do mês do primeiro aporte até o mês do saldo informado. Ir
    # além disso misturaria meses que o saldo já não cobre.
    meses = _meses_entre(primeiro, saldo_em)
    custos = [custo_do_mes(a, m, params, colaboradores_df, taxas, ajustes_df)
              for a, m in meses]
    custo_acumulado = round(sum(custos), 2)

    # Aporte feito depois do primeiro mês também entra: `aportado` é o total.
    esperado = round(aportado - custo_acumulado, 2)
    rendimento = round(saldo - esperado, 2)

    h = hoje or datetime.now(FUSO).date()
    custo_mensal = custo_do_mes(h.year, h.month, params, colaboradores_df,
                                taxas, ajustes_df)
    return {
        "aportado": aportado,
        "saldo": round(saldo, 2),
        "saldo_em": saldo_em,
        "custo_acumulado": custo_acumulado,
        "esperado": esperado,
        "rendimento": rendimento,
        "rendimento_pct": round(rendimento / aportado * 100, 2) if aportado else 0.0,
        "custo_mensal": custo_mensal,
        "meses_cobertos": (round(saldo / custo_mensal, 1)
                           if custo_mensal > 0 else None),
        "primeiro_aporte": primeiro,
        "meses_decorridos": len(meses),
    }


def fim_da_cobertura(saldo, custo_mensal, a_partir_de):
    """(ano, mes) do último mês que o saldo ainda paga. None sem custo."""
    if not a_partir_de or _num(custo_mensal) <= 0 or _num(saldo) <= 0:
        return None
    # Teto de 40 anos: saldo alto com custo baixo não vira laço infinito.
    restante, atual, limite = _num(saldo), a_partir_de, 480
    ultimo = None
    while restante >= _num(custo_mensal) and limite > 0:
        restante -= _num(custo_mensal)
        ultimo = atual
        atual = (atual[0] + (atual[1] == 12), atual[1] % 12 + 1)
        limite -= 1
    return ultimo


# ── Planilha ─────────────────────────────────────────────────────────────────

def _abrir(nome, colunas):
    import gspread
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        aba = planilha.worksheet(nome)
    except gspread.exceptions.WorksheetNotFound:
        aba = planilha.add_worksheet(title=nome, rows=300, cols=len(colunas))
        aba.append_row(colunas, value_input_option="RAW")
        return aba
    cabecalho = aba.row_values(1)
    if not cabecalho:
        aba.update("A1", [colunas], value_input_option="RAW")
        return aba
    for col in colunas:
        if col not in cabecalho:
            aba.add_cols(1)
            aba.update_cell(1, len(cabecalho) + 1, col)
            cabecalho.append(col)
    return aba


@st.cache_data(ttl=600, show_spinner=False)
def carregar():
    try:
        registros = _abrir(ABA_MOVIMENTOS, COLUNAS).get_all_records(
            value_render_option="UNFORMATTED_VALUE")
    except Exception:
        return pd.DataFrame(columns=COLUNAS)
    df = pd.DataFrame(registros)
    if df.empty:
        return pd.DataFrame(columns=COLUNAS)
    df.columns = [str(c).strip().lower() for c in df.columns]
    for col in COLUNAS:
        if col not in df.columns:
            df[col] = ""
    return df[COLUNAS]


@st.cache_data(ttl=600, show_spinner=False)
def carregar_params():
    p = parametros_padrao()
    try:
        registros = _abrir(ABA_PARAMS, ["chave", "valor"]).get_all_records(
            value_render_option="UNFORMATTED_VALUE")
    except Exception:
        return p
    for r in registros:
        chave = str(r.get("chave", "") or "").strip().lower()
        if chave not in p:
            continue
        # A vigência é um MÊS: passá-la por `_num` viraria zero, e o acréscimo
        # da contabilidade sumiria da conta em silêncio.
        p[chave] = (str(r.get("valor", "") or "").strip()
                    if chave.endswith("_desde") else _num(r.get("valor"), p[chave]))
    return p


def salvar_params(params):
    try:
        aba = _abrir(ABA_PARAMS, ["chave", "valor"])
        corpo = [[k, v if k.endswith("_desde") else round(_num(v), 2)]
                 for k, v in sorted(params.items())]
        aba.clear()
        aba.update("A1", [["chave", "valor"]] + corpo, value_input_option="RAW")
    except Exception as e:
        return False, type(e).__name__
    carregar_params.clear()
    return True, "contabilidade gravada"


def _normalizar(df, usuario=""):
    """Linhas prontas. Descarta movimento sem data ou sem valor."""
    aj = _aj()
    agora = datetime.now(FUSO).strftime("%Y-%m-%d %H:%M")
    saida = []
    for _, r in pd.DataFrame(df).iterrows():
        m = aj.mes_de(r.get("data"))
        v = _num(r.get("valor"))
        if not m or v <= 0:
            continue
        tipo = str(r.get("tipo", "") or "").strip()
        saida.append({
            "tipo": tipo if tipo in TIPOS else TIPOS[-1],
            "data": aj.texto_mes(m),
            "valor": round(v, 2),
            "observacao": str(r.get("observacao", "") or "").strip()[:200],
            "atualizado_em": agora,
            "atualizado_por": str(usuario or "")[:60],
        })
    saida.sort(key=lambda l: (l["data"], l["tipo"]))
    return saida


def salvar(df, usuario=""):
    linhas = _normalizar(df, usuario)
    try:
        aba = _abrir(ABA_MOVIMENTOS, COLUNAS)
        cabecalho = aba.row_values(1) or list(COLUNAS)
        corpo = [[l.get(str(c).strip().lower(), "") for c in cabecalho]
                 for l in linhas]
        aba.clear()
        aba.update("A1", [cabecalho] + corpo, value_input_option="RAW")
    except Exception as e:
        return False, type(e).__name__
    carregar.clear()
    return True, f"{len(linhas)} movimentos gravados"


# ── Tela ─────────────────────────────────────────────────────────────────────

def _painel_contabilidade(params):
    with st.expander("🧾 Contabilidade — o acréscimo pelo quadro de funcionários",
                     expanded=False):
        st.caption("O que a mensalidade da contabilidade subiu por causa do "
                   "time registrado. Entra no custo que o aporte cobre.")
        c1, c2 = st.columns(2)
        novos = {
            "contabilidade_extra": c1.number_input(
                "Acréscimo mensal (R$)", min_value=0.0, step=0.01,
                format="%.2f", key="hc_cont",
                value=float(params.get("contabilidade_extra", 0.0))),
            "contabilidade_extra_desde": c2.text_input(
                "Vigente desde (AAAA-MM)", key="hc_cont_desde",
                value=str(params.get("contabilidade_extra_desde", "") or ""),
                help="Em branco, o acréscimo NÃO entra em mês nenhum."),
        }
        if not _aj().mes_de(novos["contabilidade_extra_desde"]) \
                and novos["contabilidade_extra"] > 0:
            st.warning("Sem o mês de início, este acréscimo fica **fora** da "
                       "conta. Sem ele, valeria também nos meses anteriores ao "
                       "quadro existir, e o aporte pareceria durar menos.")
        if st.button("💾 Salvar contabilidade", key="btn_hc_cont"):
            ok, msg = salvar_params(novos)
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()
        return novos


def pagina(usuario_logado=None):
    st.markdown("### 🧮 Balanço headcount")
    st.caption(
        "O aporte feito para expandir e registrar o time, e por quantos meses "
        "ele ainda cobre esse custo. **O rendimento não se digita** — ele é o "
        "que o saldo tem além do que a conta previa."
    )

    params = _painel_contabilidade(carregar_params())

    st.markdown("##### Aportes e saldos")
    st.caption(
        "**Aporte** é dinheiro entrando. **Saldo** é quanto havia na conta "
        "naquele mês — o extrato, não uma estimativa. As retiradas não se "
        "digitam: elas são o custo do time, que o Studio calcula."
    )

    df = carregar()
    if df.empty:
        df = pd.DataFrame(columns=COLUNAS)
        st.info("Nenhum movimento. Comece pelo **Aporte**, com o mês em que o "
                "dinheiro entrou — é dele que sai toda a conta.")

    editado = st.data_editor(
        df[["tipo", "data", "valor", "observacao"]],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="ed_headcount",
        column_config={
            "tipo": st.column_config.SelectboxColumn(
                "Tipo", options=TIPOS, required=True, width="small"),
            "data": st.column_config.TextColumn(
                "Mês", width="small", help="AAAA-MM."),
            "valor": st.column_config.NumberColumn(
                "Valor (R$)", min_value=0.0, step=0.01, format="%.2f"),
            "observacao": st.column_config.TextColumn("Observação", width="large"),
        },
    )

    if st.button("💾 Salvar movimentos", type="primary", key="btn_hc_salvar"):
        ok, msg = salvar(editado, usuario_logado)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(f"Não consegui gravar: {msg}")

    _balanco(editado, params)


def _balanco(editado, params):
    import colaboradores as _co
    aj = _aj()
    r = resumo(editado, params, taxas=_co.carregar_taxas(),
               ajustes_df=aj.carregar())
    if not r["primeiro_aporte"]:
        return

    st.markdown("##### Onde o aporte está")
    a = st.columns(4)
    a[0].metric("Aportado", _brl(r["aportado"]),
                help=f"Primeiro aporte em {aj.texto_mes(r['primeiro_aporte'])}.")
    a[1].metric("Custo já coberto", _brl(r["custo_acumulado"]),
                help=f"{r['meses_decorridos']} mês(es) de time e contabilidade.")
    a[2].metric("Saldo informado", _brl(r["saldo"]),
                help=f"Última leitura: {aj.texto_mes(r['saldo_em'])}.")
    a[3].metric("Rendimento", _brl(r["rendimento"]),
                delta=f"{r['rendimento_pct']:.2f}% do aportado",
                help="Saldo informado menos o que a conta previa sem render.")

    if r["rendimento"] < 0:
        st.warning(
            "Rendimento negativo quer dizer que saiu mais do que o custo "
            "calculado — ou que falta um aporte no registro, ou que o aporte "
            "pagou algo que não está na conta do time. Vale conferir antes de "
            "usar o número.")

    st.markdown("##### Até quando cobre")
    b = st.columns(3)
    b[0].metric("Custo mensal de hoje", _brl(r["custo_mensal"]),
                help="Colaboradores marcados «No aporte» mais o acréscimo da "
                     "contabilidade.")
    b[1].metric("Meses cobertos",
                f"{r['meses_cobertos']:.1f}" if r["meses_cobertos"] is not None
                else "—",
                help="Saldo dividido pelo custo mensal de hoje.")
    _fim = fim_da_cobertura(r["saldo"], r["custo_mensal"],
                            aj.mes_de(aj.texto_mes(r["saldo_em"])))
    b[2].metric("Último mês coberto",
                f"{_fim[1]:02d}/{_fim[0]}" if _fim else "—",
                help="Contando do mês do saldo informado, com o custo de hoje.")

    st.caption(
        "A projeção supõe o custo de hoje repetido e **sem rendimento novo** — "
        "o que rendeu até agora já está dentro do saldo. Contratar mais gente "
        "encurta o prazo no mês seguinte, sem ninguém precisar avisar.")


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    ok("1.234,56 vira 1234.56", _num("1.234,56") == 1234.56)
    ok("real sai no formato brasileiro", _brl(120000) == "R$ 120.000,00")

    p = {"contabilidade_extra": 400.0, "contabilidade_extra_desde": "2026-06"}
    ok("antes da vigência, o acréscimo não entra",
       contabilidade_no_mes(p, 2026, 5) == 0.0)
    ok("no mês da vigência, entra", contabilidade_no_mes(p, 2026, 6) == 400.0)
    ok("sem mês de início, o acréscimo fica fora",
       contabilidade_no_mes({"contabilidade_extra": 400.0}, 2026, 9) == 0.0)
    ok("acréscimo zero é zero", contabilidade_no_mes({}, 2026, 9) == 0.0)

    ok("os meses entre junho e setembro são quatro",
       _meses_entre((2026, 6), (2026, 9)) == [(2026, 6), (2026, 7), (2026, 8),
                                              (2026, 9)])
    ok("a virada do ano é respeitada",
       _meses_entre((2026, 11), (2027, 2))
       == [(2026, 11), (2026, 12), (2027, 1), (2027, 2)])
    ok("fim antes do início não devolve mês nenhum",
       _meses_entre((2026, 9), (2026, 6)) == [])
    ok("o mesmo mês devolve ele mesmo",
       _meses_entre((2026, 9), (2026, 9)) == [(2026, 9)])

    # Quadro de duas pessoas, uma delas fora do aporte
    quadro = pd.DataFrame([
        {"funcionario": "Beatriz", "salario_base": 2006.58, "admissao": "2026-01",
         "registrado": "Sim", "no_aporte": "Sim", "dias_uteis": 22},
        {"funcionario": "Monique", "salario_base": 2400.00, "admissao": "2026-01",
         "registrado": "Não", "no_aporte": "Não", "dias_uteis": 22},
    ])
    import colaboradores as _co
    tx = _co.taxas_padrao()
    custo_b = _co.custo(2006.58, tx, 22, True, False)["total"]
    ok("quem está fora do aporte não entra no custo",
       abs(custo_do_mes(2026, 9, None, quadro, tx) - custo_b) < 0.01)
    ok("o acréscimo da contabilidade entra no custo",
       abs(custo_do_mes(2026, 9, p, quadro, tx) - (custo_b + 400)) < 0.01)

    # O caso do enunciado: aporte em junho, saldo informado em setembro
    movs = pd.DataFrame([
        {"tipo": "Aporte", "data": "2026-06", "valor": 120000},
        {"tipo": "Saldo", "data": "2026-09", "valor": 110000},
    ])
    r = resumo(movs, p, quadro, tx, hoje=date(2026, 9, 15))
    ok("o aportado é o que entrou", r["aportado"] == 120000.0)
    ok("o custo corre do primeiro aporte até o saldo", r["meses_decorridos"] == 4)
    ok("o custo acumulado são quatro meses do custo mensal",
       abs(r["custo_acumulado"] - 4 * (custo_b + 400)) < 0.01)
    ok("o esperado é o que entrou menos o que saiu",
       abs(r["esperado"] - (120000 - r["custo_acumulado"])) < 0.01)
    ok("o rendimento é o saldo além do esperado",
       abs(r["rendimento"] - (110000 - r["esperado"])) < 0.01)
    ok("meses cobertos é saldo dividido pelo custo do mês",
       abs(r["meses_cobertos"] - round(110000 / (custo_b + 400), 1)) < 0.05)

    ok("sem aporte não há balanço", resumo(pd.DataFrame())["aportado"] == 0.0)
    ok("sem saldo informado, o saldo é o que entrou",
       resumo(pd.DataFrame([{"tipo": "Aporte", "data": "2026-06",
                             "valor": 120000}]), p, quadro, tx,
              hoje=date(2026, 6, 15))["saldo"] == 120000.0)
    ok("dois aportes somam",
       resumo(pd.DataFrame([{"tipo": "Aporte", "data": "2026-06", "valor": 100000},
                            {"tipo": "Aporte", "data": "2026-08", "valor": 20000},
                            {"tipo": "Saldo", "data": "2026-08", "valor": 115000}]),
              p, quadro, tx, hoje=date(2026, 8, 15))["aportado"] == 120000.0)
    ok("vale a leitura de saldo mais recente",
       resumo(pd.DataFrame([{"tipo": "Aporte", "data": "2026-06", "valor": 120000},
                            {"tipo": "Saldo", "data": "2026-07", "valor": 118000},
                            {"tipo": "Saldo", "data": "2026-09", "valor": 110000}]),
              p, quadro, tx, hoje=date(2026, 9, 15))["saldo"] == 110000.0)

    ok("o saldo cobre seis meses de um custo de mil",
       fim_da_cobertura(6000, 1000, (2026, 9)) == (2027, 2))
    ok("saldo que não paga um mês não cobre nenhum",
       fim_da_cobertura(500, 1000, (2026, 9)) is None)
    ok("custo zero não vira laço infinito",
       fim_da_cobertura(6000, 0, (2026, 9)) is None)
    ok("saldo zero não cobre nada", fim_da_cobertura(0, 1000, (2026, 9)) is None)

    linhas = _normalizar(pd.DataFrame([
        {"tipo": "Aporte", "data": "06/2026", "valor": "120.000,00"},
        {"tipo": "Saldo", "data": "", "valor": 1000},
        {"tipo": "Saldo", "data": "2026-09", "valor": 0},
        {"tipo": "inventado", "data": "2026-09", "valor": 50},
    ]), "martinsousa")
    ok("movimento sem mês ou sem valor não é gravado", len(linhas) == 2)
    ok("o mês vira sempre AAAA-MM", linhas[0]["data"] == "2026-06")
    ok("valor com vírgula chega certo", linhas[0]["valor"] == 120000.0)
    ok("tipo inventado cai em Saldo", linhas[1]["tipo"] == "Saldo")

    print("\nfalhas:", falhas)
