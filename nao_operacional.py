"""nao_operacional.py — Os empréstimos: o que sai do caixa sem ser custo de operar.

POR QUE ELE FICA SEPARADO DO CUSTO FIXO
---------------------------------------
As parcelas de PRONAMP saem do caixa todo mês, mas não são custo de OPERAR: a
operação continuaria igual se a dívida não existisse. Juntar as duas coisas num
número só dá uma linha de equilíbrio que responde a pergunta errada. Por isso o
painel mostra duas:

    equilíbrio OPERACIONAL   a operação se paga
    equilíbrio DE CAIXA      a operação se paga E as parcelas saem

Nesta base a diferença entre as duas é de R$ 52 mil de faturamento por mês.

CADA CONTRATO COMEÇOU NUM MÊS
-----------------------------
E é por isso que esta tela existe em vez de um número só. Os PRONAMPs entraram
em datas diferentes, com carências diferentes: em fevereiro de 2024 a empresa
não pagava o que paga hoje. Somar o valor de hoje para trás inventaria um custo
que não existiu, e o custo fixo histórico sairia errado em todos os meses
anteriores ao último contrato.

    primeira parcela  =  contratação + carência
    última parcela    =  primeira + prazo − 1

`total_no_mes` responde "quanto de não operacional existiu em março de 2024?"
contando só os contratos que já tinham começado e ainda não tinham acabado.

A TAXA: 0,49% + SELIC
---------------------
O PRONAMP tem spread fixo mais Selic, então a parcela muda quando a Selic muda.
A conta feita aqui é explícita e aparece na tela:

    a.m.  =  spread mensal  +  Selic mensal,  Selic mensal = (1+Selic a.a.)^(1/12) − 1
    a.a.  =  a.m. × 12   (nominal, como no contrato dele: 2,19 × 12 = 26,28)

CUIDADO — ESTA CONTA NÃO REPRODUZ AS PARCELAS DE HOJE
-----------------------------------------------------
Foi conferido contra os três contratos da aba CUSTOS FIXOS do Controle_MS, e a
taxa implícita em cada parcela é diferente: 2,07%, 1,46% e 1,87% ao mês — com
os três marcados na planilha como 21% a.a. e 0,49% a.m. Ou seja, as parcelas
foram contratadas em Selics diferentes, e a coluna de taxa da planilha guarda a
taxa de HOJE, não a da assinatura.

Por isso a tela NÃO substitui a parcela do contrato pela calculada. Mostra as
duas, lado a lado, com a diferença. Enquanto elas não baterem, quem manda é o
contrato — e a diferença na tela é o que diz que a fórmula ainda está errada.
"""

from datetime import date, datetime, timezone, timedelta

import pandas as pd
import streamlit as st

ABA_NOME = "nao_operacional"

COLUNAS = ["programa", "conta_aporte", "data_contratacao", "carencia_meses",
           "prazo_meses", "aporte", "dia_debito", "parcela", "parcelas_pagas",
           "saldo_devedor", "condicao", "spread_am", "taxa_aa", "taxa_am",
           "atualizado_em", "atualizado_por"]

# A condição contratada. O spread de cada uma entra em `SPREADS`, em fração ao
# mês — é ele que soma com a Selic. "Fixa" é o contrato que não acompanha
# índice nenhum: ali a taxa digitada manda e a Selic não entra.
CONDICOES = ["0,49% + Selic", "Fixa"]
SPREADS = {"0,49% + Selic": 0.0049, "Fixa": None}

SELIC_PADRAO = 15.00   # % ao ano. Ponto de partida; ele informa a vigente.

# Os contratos de hoje, como estão no resumo do gestor. Sugestão de partida:
# só viram linha na planilha depois de salvar.
#
# O último foi renomeado de "PRONAMP LG" para "PRONAMP LG5". Havia DOIS com o
# mesmo nome no resumo, e o nome é a chave que liga o contrato ao «Ajuste de
# valor» — dois iguais fariam um reajuste cair nos dois, ou em nenhum, sem
# nada na tela dizendo por quê. Renomear é reversível; o erro silencioso não.
SUGESTOES = [
    ("PRONAMP LG",  "Itaú LG",  "2024-02-16", 9, 48,  99934.28, 18, 3304.86, 21,  84188.44, "0,49% + Selic", 0.49),
    ("PRONAMP LG2", "Itaú LG",  "2025-02-26", 9, 48,  43403.24, 23, 1263.80,  8,  46036.36, "0,49% + Selic", 0.49),
    ("PRONAMP MS",  "Itaú MS",  "2024-06-20", 9, 48, 102421.95, 20, 3254.01, 16,  96776.02, "0,49% + Selic", 0.49),
    ("PRONAMP MS2", "Inter MS", "2025-02-26", 9, 48,  23918.87, 26,  673.36, 12,  23733.84, "0,49% + Selic", 0.49),
    ("PRONAMP LG3", "Itaú LG",  "2026-01-17", 5, 48,  21168.71, 17,  493.03,  0,  20762.68, "0,49% + Selic", 0.49),
    ("PRONAMP LG4", "Itaú LG",  "2026-01-22", 5, 48,  73681.33, 22, 1754.30,  2,  76487.76, "0,49% + Selic", 0.49),
    ("PRONAMP LG5", "Itaú LG",  "2025-08-12", 0, 48, 137042.00,  7, 4980.36, 10, 129127.83, "Fixa",          2.19),
]

FUSO = timezone(timedelta(hours=-3))


# ── Contas ───────────────────────────────────────────────────────────────────

def _num(v, padrao=0.0):
    """Número a partir do que foi digitado. 1.234,56 e 1234.56 valem."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return padrao
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace("R$", "").replace("%", "").replace(" ", "")
    if not t:
        return padrao
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return padrao


def selic_mensal(selic_aa_pct):
    """Selic ao mês, equivalente composta. 15% a.a. -> 1,1715% a.m.

    Equivalente composta e não 15/12: dividir por doze dá a taxa NOMINAL, que
    rende mais de 15% no ano quando capitaliza mês a mês. A diferença é meio
    ponto ao ano — pouco por mês, milhares num contrato de 48.
    """
    a = max(_num(selic_aa_pct), 0.0) / 100.0
    return (1.0 + a) ** (1.0 / 12.0) - 1.0


def taxas(condicao, selic_aa_pct, taxa_am_digitada=None):
    """(a.m., a.a.) do contrato. Devolve fração, não porcentagem.

    A anual é NOMINAL — doze vezes a mensal —, e não a composta. Não é escolha
    minha: o resumo do gestor traz 2,19% a.m. com 26,28% a.a., e 2,19 × 12 é
    exatamente 26,28. Compor daria 29,71%, e a tela mostraria um número que o
    contrato dele não tem. Quem compara os dois precisa ver o mesmo.
    """
    spread = SPREADS.get(str(condicao or "").strip())
    if spread is None:
        am = max(_num(taxa_am_digitada), 0.0) / 100.0
    else:
        am = spread + selic_mensal(selic_aa_pct)
    return am, am * 12


def parcela_price(saldo, taxa_am, n):
    """Parcela da Tabela Price. Taxa zero vira divisão simples."""
    n = int(_num(n, 0))
    saldo = max(_num(saldo), 0.0)
    if n <= 0 or saldo <= 0:
        return 0.0
    if taxa_am <= 0:
        return saldo / n
    return saldo * taxa_am / (1.0 - (1.0 + taxa_am) ** -n)


def saldo_apos_carencia(aporte, taxa_am, carencia_meses):
    """O que se deve quando a primeira parcela vence.

    Na carência não se paga nada, mas o juro corre: o saldo que vai ser
    amortizado é maior que o aporte. Calcular a parcela sobre o aporte puro dá
    um número menor do que o banco cobra — e um custo fixo subestimado é pior
    que nenhum, porque parece certo.
    """
    c = max(int(_num(carencia_meses, 0)), 0)
    return max(_num(aporte), 0.0) * (1.0 + max(taxa_am, 0.0)) ** c


def parcela_calculada(linha, selic_aa_pct):
    """A parcela que a condição contratada produz, para comparar com a real."""
    am, _ = taxas(linha.get("condicao"), selic_aa_pct, linha.get("taxa_am"))
    saldo = saldo_apos_carencia(linha.get("aporte"), am,
                                linha.get("carencia_meses"))
    return parcela_price(saldo, am, linha.get("prazo_meses"))


def _mes_de(v):
    """(ano, mes) de uma data em qualquer formato usado por aqui. None se não der."""
    if isinstance(v, datetime):
        return (v.year, v.month)
    if isinstance(v, date):
        return (v.year, v.month)
    t = str(v or "").strip()
    if not t:
        return None
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y"):
        try:
            d = datetime.strptime(t[:19] if " " in t else t, f)
            return (d.year, d.month)
        except ValueError:
            continue
    return None


def _somar_meses(ano_mes, n):
    ano, mes = ano_mes
    total = (ano * 12 + (mes - 1)) + int(n)
    return (total // 12, total % 12 + 1)


def vigencia(linha):
    """(primeiro, ultimo) mês em que este contrato pesa, como (ano, mes).

    Devolve (None, None) sem data de contratação: contrato sem data não tem
    como entrar no custo de um mês, e chutar a data de hoje o faria aparecer
    em todos os meses de uma vez.
    """
    inicio = _mes_de(linha.get("data_contratacao"))
    if not inicio:
        return (None, None)
    carencia = max(int(_num(linha.get("carencia_meses"), 0)), 0)
    prazo = max(int(_num(linha.get("prazo_meses"), 0)), 0)
    primeiro = _somar_meses(inicio, carencia)
    if prazo <= 0:
        return (primeiro, None)
    return (primeiro, _somar_meses(primeiro, prazo - 1))


def esta_ativo(linha, ano, mes):
    """Este contrato tem parcela vencendo em (ano, mes)?"""
    primeiro, ultimo = vigencia(linha)
    if not primeiro:
        return False
    alvo = (int(ano), int(mes))
    if alvo < primeiro:
        return False
    return ultimo is None or alvo <= ultimo


def totais(df):
    """A dívida somada: o que se deve hoje e o que ainda vai sair do caixa.

    São dois números diferentes, e confundi-los é caro:

        saldo devedor   o que se deve HOJE, se quitasse tudo agora
        total a pagar   (parcelas que faltam) × parcela — já com os juros de
                        todos os meses que ainda vão correr

    A diferença entre os dois é o juro que ainda não foi pago. Olhar só o saldo
    devedor subestima o que vai sair do caixa; olhar só o total a pagar
    superestima a dívida.
    """
    d = pd.DataFrame(df)
    vazio = {"aporte": 0.0, "saldo_devedor": 0.0, "parcela_mensal": 0.0,
             "parcelas_restantes": 0, "total_a_pagar": 0.0, "juros_futuros": 0.0,
             "contratos": 0}
    if d.empty:
        return vazio
    ap = sd = pm = tp = 0.0
    restantes = n = 0
    for _, r in d.iterrows():
        if not str(r.get("programa", "") or "").strip():
            continue
        n += 1
        ap += _num(r.get("aporte"))
        sd += _num(r.get("saldo_devedor"))
        parcela = _num(r.get("parcela"))
        prazo = max(int(_num(r.get("prazo_meses"), 0)), 0)
        pagas = max(int(_num(r.get("parcelas_pagas"), 0)), 0)
        falta = max(prazo - pagas, 0)
        pm += parcela
        restantes += falta
        tp += falta * parcela
    return {"aporte": round(ap, 2), "saldo_devedor": round(sd, 2),
            "parcela_mensal": round(pm, 2), "parcelas_restantes": restantes,
            "total_a_pagar": round(tp, 2),
            "juros_futuros": round(tp - sd, 2), "contratos": n}


def total_no_mes(df, ano, mes):
    """Quanto de não operacional existiu naquele mês.

    É esta função que faz o custo fixo histórico ficar certo: em fevereiro de
    2024 a empresa não pagava o que paga hoje, e somar o valor de hoje para
    trás inventaria custo que não existiu.
    """
    d = pd.DataFrame(df)
    if d.empty:
        return 0.0
    return float(sum(_num(r.get("parcela"))
                     for _, r in d.iterrows() if esta_ativo(r, ano, mes)))


# ── Planilha ─────────────────────────────────────────────────────────────────

def _aba():
    import gspread
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        aba = planilha.worksheet(ABA_NOME)
    except gspread.exceptions.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA_NOME, rows=200,
                                     cols=len(COLUNAS))
        aba.append_row(COLUNAS, value_input_option="RAW")
        return aba
    cabecalho = aba.row_values(1)
    if not cabecalho:
        aba.update("A1", [COLUNAS], value_input_option="RAW")
        return aba
    for col in COLUNAS:
        if col not in cabecalho:
            aba.add_cols(1)
            aba.update_cell(1, len(cabecalho) + 1, col)
            cabecalho.append(col)
    return aba


@st.cache_data(ttl=600, show_spinner=False)
def carregar():
    try:
        registros = _aba().get_all_records(value_render_option="UNFORMATTED_VALUE")
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


def _normalizar(df, usuario=""):
    """Linhas prontas para a planilha. Descarta linha sem nome de programa."""
    agora = datetime.now(FUSO).strftime("%Y-%m-%d %H:%M")
    saida = []
    for _, r in pd.DataFrame(df).iterrows():
        programa = str(r.get("programa", "") or "").strip()
        if not programa:
            continue
        cond = str(r.get("condicao", "") or "").strip()
        dt = r.get("data_contratacao")
        if isinstance(dt, (date, datetime)):
            dt = dt.strftime("%Y-%m-%d")
        prazo = max(int(_num(r.get("prazo_meses"), 0)), 0)
        pagas = max(int(_num(r.get("parcelas_pagas"), 0)), 0)
        saida.append({
            "programa": programa,
            "conta_aporte": str(r.get("conta_aporte", "") or "").strip(),
            "data_contratacao": str(dt or "").strip()[:10],
            "carencia_meses": max(int(_num(r.get("carencia_meses"), 0)), 0),
            "prazo_meses": prazo,
            "aporte": round(_num(r.get("aporte")), 2),
            "dia_debito": min(max(int(_num(r.get("dia_debito"), 0)), 0), 31),
            "parcela": round(_num(r.get("parcela")), 2),
            # Pagas nunca passa do prazo: um número maior faria o saldo
            # aparecer quitado num contrato que ainda corre.
            "parcelas_pagas": min(pagas, prazo) if prazo else pagas,
            "saldo_devedor": round(_num(r.get("saldo_devedor")), 2),
            "condicao": cond if cond in CONDICOES else CONDICOES[0],
            "spread_am": round(_num(r.get("spread_am")), 4),
            "taxa_aa": round(_num(r.get("taxa_aa")), 4),
            "taxa_am": round(_num(r.get("taxa_am")), 4),
            "atualizado_em": agora,
            "atualizado_por": str(usuario or "")[:60],
        })
    return saida


def salvar(df, usuario=""):
    """Regrava a aba inteira. Devolve (ok, mensagem)."""
    linhas = _normalizar(df, usuario)
    try:
        aba = _aba()
        cabecalho = aba.row_values(1) or list(COLUNAS)
        corpo = [[l.get(str(c).strip().lower(), "") for c in cabecalho]
                 for l in linhas]
        aba.clear()
        aba.update("A1", [cabecalho] + corpo, value_input_option="RAW")
    except Exception as e:
        # Só o tipo: a mensagem do gspread carrega a URL da planilha.
        return False, type(e).__name__
    carregar.clear()
    return True, f"{len(linhas)} contratos gravados"


def _brl(v):
    return "R$ " + f"{float(v):,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")


def _mes_texto(am):
    if not am:
        return "—"
    return f"{am[1]:02d}/{am[0]}"


# ── Tela ─────────────────────────────────────────────────────────────────────

def pagina(usuario_logado=None):
    st.markdown("#### 🏦 Não operacional")
    st.caption(
        "Empréstimos e financiamentos: sai do caixa, mas não é custo de "
        "operar. Cada contrato entrou numa data — é por isso que o custo de "
        "hoje não vale para os meses de trás."
    )

    selic = st.number_input(
        "Selic vigente (% ao ano)", min_value=0.0, max_value=100.0,
        value=float(SELIC_PADRAO), step=0.25, format="%.2f",
        help="Entra na conta dos contratos com condição «0,49% + Selic».")
    sm = selic_mensal(selic)
    st.caption(f"Selic ao mês (equivalente composta): **{sm*100:.4f}%** · "
               f"a.m. do PRONAMP = 0,49% + {sm*100:.4f}% = "
               f"**{(0.0049+sm)*100:.4f}%** · a.a. (nominal, ×12) = "
               f"**{(0.0049+sm)*12*100:.2f}%**")

    df = carregar()
    if df.empty:
        df = pd.DataFrame(
            [{"programa": pr, "conta_aporte": co, "data_contratacao": dt,
              "carencia_meses": ca, "prazo_meses": pz, "aporte": ap,
              "dia_debito": di, "parcela": pc, "parcelas_pagas": pg,
              "saldo_devedor": sd, "condicao": cond, "spread_am": 0.0,
              "taxa_aa": 0.0, "taxa_am": tam, "atualizado_em": "",
              "atualizado_por": ""}
             for pr, co, dt, ca, pz, ap, di, pc, pg, sd, cond, tam in SUGESTOES],
            columns=COLUNAS)
        st.info("Aba ainda vazia. Os contratos já vêm preenchidos como "
                "sugestão — confira e clique em **Salvar**. Nada foi gravado "
                "até você salvar.")

    visiveis = ["programa", "conta_aporte", "data_contratacao", "carencia_meses",
                "prazo_meses", "aporte", "dia_debito", "parcela",
                "parcelas_pagas", "saldo_devedor", "condicao", "taxa_am"]
    editado = st.data_editor(
        df[visiveis],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="ed_nao_operacional",
        column_config={
            "programa": st.column_config.TextColumn(
                "Programa", required=True, width="medium",
                help="PRONAMP LG, PRONAMP MS…"),
            "conta_aporte": st.column_config.TextColumn(
                "Conta", width="small", help="Itaú LG, Itaú MS…"),
            "data_contratacao": st.column_config.TextColumn(
                "Contratação", width="small",
                help="AAAA-MM-DD. É ela que diz a partir de que mês este "
                     "custo existiu."),
            "carencia_meses": st.column_config.NumberColumn(
                "Carência", min_value=0, max_value=60, step=1,
                format="%d", width="small"),
            "prazo_meses": st.column_config.NumberColumn(
                "Prazo", min_value=0, max_value=240, step=1,
                format="%d", width="small"),
            "aporte": st.column_config.NumberColumn(
                "Aporte (R$)", min_value=0.0, step=0.01, format="%.2f"),
            "dia_debito": st.column_config.NumberColumn(
                "Dia", min_value=0, max_value=31, step=1,
                format="%d", width="small"),
            "parcela": st.column_config.NumberColumn(
                "Parcela (R$)", min_value=0.0, step=0.01, format="%.2f",
                help="A do contrato. É ela que entra na conta — a calculada "
                     "fica ao lado, só para comparar."),
            "parcelas_pagas": st.column_config.NumberColumn(
                "Pagas", min_value=0, max_value=240, step=1, format="%d",
                width="small"),
            "saldo_devedor": st.column_config.NumberColumn(
                "Saldo devedor", min_value=0.0, step=0.01, format="%.2f"),
            "condicao": st.column_config.SelectboxColumn(
                "Condição", options=CONDICOES, width="medium"),
            "taxa_am": st.column_config.NumberColumn(
                "Taxa fixa (% a.m.)", min_value=0.0, max_value=100.0,
                step=0.01, format="%.2f", width="medium",
                help="Só vale na condição «Fixa». Na condição com Selic, a "
                     "taxa é calculada e este campo é ignorado."),
        },
    )

    # Nome repetido: ele é a chave que liga o contrato ao «Ajuste de valor».
    # Dois iguais fazem um reajuste cair nos dois, ou em nenhum, sem nada na
    # tela dizendo por quê.
    _nomes = [str(x).strip() for x in pd.DataFrame(editado).get("programa", [])
              if str(x).strip()]
    _repetidos = sorted({n for n in _nomes if _nomes.count(n) > 1})
    if _repetidos:
        st.error("Dois contratos com o mesmo nome: **" + ", ".join(_repetidos)
                 + "**. O nome liga o contrato ao «Ajuste de valor» — com dois "
                   "iguais, um reajuste cai nos dois ou em nenhum. Renomeie um.")

    if st.button("💾 Salvar", type="primary", key="btn_salvar_nao_op"):
        ok, msg = salvar(editado, usuario_logado)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(f"Não consegui gravar: {msg}")

    _tabela_conferencia(editado, selic)


def _tabela_conferencia(editado, selic):
    """A parcela do contrato contra a que a condição produz, e a vigência."""
    d = pd.DataFrame(editado)
    if d.empty or not str(d.get("programa", pd.Series(dtype=str)).any()):
        return

    t = totais(d)
    st.markdown("##### A dívida somada")
    st.caption(
        "**Saldo devedor** é o que se deve hoje, se quitasse tudo agora. "
        "**Total a pagar** é o que ainda vai sair do caixa até a última "
        "parcela, já com os juros que ainda vão correr. A diferença entre os "
        "dois é juro que ainda não foi pago."
    )
    g = st.columns(4)
    g[0].metric("Saldo devedor", _brl(t["saldo_devedor"]),
                help=f"{t['contratos']} contrato(s). É o número que você "
                     "informa, vindo do banco.")
    g[1].metric("Total a pagar", _brl(t["total_a_pagar"]),
                help=f"{t['parcelas_restantes']} parcela(s) restante(s) × a "
                     "parcela de cada contrato.")
    g[2].metric("Juros ainda a correr", _brl(t["juros_futuros"]),
                help="Total a pagar menos o saldo devedor.")
    g[3].metric("Parcela mensal somada", _brl(t["parcela_mensal"]),
                help="Todas as parcelas juntas, independentemente de o "
                     "contrato já ter começado.")
    st.caption(f"Tomado emprestado ao todo: **{_brl(t['aporte'])}**.")

    st.markdown("##### Conferência da taxa e da vigência")
    st.caption(
        "A parcela que entra na conta é sempre a **do contrato**. A calculada "
        "está aqui para mostrar quando a fórmula e o contrato discordam — "
        "enquanto discordarem, a fórmula é que está errada."
    )

    linhas = []
    for _, r in d.iterrows():
        if not str(r.get("programa", "") or "").strip():
            continue
        am, aa = taxas(r.get("condicao"), selic, r.get("taxa_am"))
        calc = parcela_calculada(r, selic)
        real = _num(r.get("parcela"))
        primeiro, ultimo = vigencia(r)
        linhas.append({
            "Programa": r.get("programa"),
            "a.m.": f"{am*100:.4f}%",
            "a.a.": f"{aa*100:.2f}%",
            "Parcela do contrato": _brl(real),
            "Parcela calculada": _brl(calc),
            "Diferença": _brl(calc - real),
            "1ª parcela": _mes_texto(primeiro),
            "Última": _mes_texto(ultimo),
        })
    if not linhas:
        return
    st.dataframe(pd.DataFrame(linhas), use_container_width=True,
                 hide_index=True)

    hoje = datetime.now(FUSO).date()
    c1, c2 = st.columns(2)
    with c1:
        ano = st.number_input("Ano", min_value=2020, max_value=2100,
                              value=hoje.year, step=1, key="no_ano")
    with c2:
        mes = st.number_input("Mês", min_value=1, max_value=12,
                              value=hoje.month, step=1, key="no_mes")
    st.metric(f"Não operacional em {int(mes):02d}/{int(ano)}",
              _brl(total_no_mes(d, ano, mes)),
              help="Soma só os contratos que já tinham começado e ainda não "
                   "acabaram naquele mês.")


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # ── Números do teclado brasileiro
    ok("1.234,56 vira 1234.56", _num("1.234,56") == 1234.56)
    ok("21% vira 21", _num("21%") == 21.0)
    ok("vazio vira zero", _num("") == 0.0)

    # ── Selic
    sm = selic_mensal(15)
    ok("Selic 15% a.a. dá 1,1715% a.m.", abs(sm - 0.011715) < 1e-6)
    ok("a Selic mensal composta rende exatamente 15% no ano",
       abs((1 + sm) ** 12 - 1 - 0.15) < 1e-12)
    ok("a composta é menor que a nominal 15/12", sm < 0.15 / 12)
    ok("Selic zero dá mês zero", selic_mensal(0) == 0.0)

    am, aa = taxas("0,49% + Selic", 15)
    ok("a.m. do PRONAMP é 0,49% mais a Selic do mês",
       abs(am - (0.0049 + sm)) < 1e-12)
    ok("a.a. é doze vezes o a.m., como no contrato",
       abs(aa - am * 12) < 1e-12)
    ok("com Selic 15% o PRONAMP fica perto dos 21% da planilha",
       0.19 < aa < 0.22)
    am_f, _ = taxas("Fixa", 15, taxa_am_digitada=1.5)
    ok("contrato de taxa fixa ignora a Selic", abs(am_f - 0.015) < 1e-12)

    # ── Price e carência
    ok("Price de 100k a 1% em 48 meses dá ~2.633",
       abs(parcela_price(100000, 0.01, 48) - 2633.38) < 1.0)
    ok("taxa zero vira divisão simples",
       abs(parcela_price(4800, 0, 48) - 100.0) < 1e-9)
    ok("prazo zero não divide por zero", parcela_price(1000, 0.01, 0) == 0.0)
    ok("aporte zero dá parcela zero", parcela_price(0, 0.01, 48) == 0.0)
    ok("na carência o juro corre e o saldo sobe",
       saldo_apos_carencia(100000, 0.01, 9) > 100000)
    ok("sem carência o saldo é o próprio aporte",
       saldo_apos_carencia(100000, 0.01, 0) == 100000)
    ok("a parcela sobre o saldo da carência é maior que sobre o aporte puro",
       parcela_price(saldo_apos_carencia(100000, 0.016, 9), 0.016, 48)
       > parcela_price(100000, 0.016, 48))

    # ── Vigência: o caso que motivou a tela
    lg = {"programa": "PRONAMP LG", "data_contratacao": "2024-02-16",
          "carencia_meses": 9, "prazo_meses": 48, "parcela": 3304.86}
    ms = {"programa": "PRONAMP MS", "data_contratacao": "2024-06-20",
          "carencia_meses": 9, "prazo_meses": 48, "parcela": 3254.01}
    lg2 = {"programa": "PRONAMP LG2", "data_contratacao": "2025-02-26",
           "carencia_meses": 9, "prazo_meses": 48, "parcela": 1263.80}

    ok("contratado em fev/24 com 9 de carência começa em nov/24",
       vigencia(lg)[0] == (2024, 11))
    ok("48 parcelas a partir de nov/24 terminam em out/28",
       vigencia(lg)[1] == (2028, 10))
    ok("data no formato brasileiro também é lida",
       vigencia({"data_contratacao": "16/02/2024", "carencia_meses": 9,
                 "prazo_meses": 48})[0] == (2024, 11))
    ok("contrato sem data não entra em mês nenhum",
       vigencia({"carencia_meses": 9, "prazo_meses": 48}) == (None, None))
    ok("prazo em branco deixa o fim em aberto",
       vigencia({"data_contratacao": "2024-02-16", "carencia_meses": 0,
                 "prazo_meses": 0})[1] is None)

    ok("na carência o contrato ainda não pesa",
       not esta_ativo(lg, 2024, 10))
    ok("a primeira parcela pesa", esta_ativo(lg, 2024, 11))
    ok("a última parcela ainda pesa", esta_ativo(lg, 2028, 10))
    ok("depois da última, não pesa mais", not esta_ativo(lg, 2028, 11))

    todos = pd.DataFrame([lg, ms, lg2])
    ok("em fev/24 nenhum dos três existia",
       total_no_mes(todos, 2024, 2) == 0.0)
    ok("em nov/24 só o LG tinha começado",
       abs(total_no_mes(todos, 2024, 11) - 3304.86) < 0.01)
    ok("em mar/25 o LG e o MS pesam, o LG2 ainda não",
       abs(total_no_mes(todos, 2025, 3) - (3304.86 + 3254.01)) < 0.01)
    ok("em set/26 os três pesam",
       abs(total_no_mes(todos, 2026, 9) - (3304.86 + 3254.01 + 1263.80)) < 0.01)
    ok("em nov/28 o LG já acabou",
       abs(total_no_mes(todos, 2028, 11) - (3254.01 + 1263.80)) < 0.01)
    ok("tabela vazia dá zero", total_no_mes(pd.DataFrame(), 2026, 9) == 0.0)

    # ── Gravação
    linhas = _normalizar(pd.DataFrame([
        {**lg, "conta_aporte": "Itaú LG", "aporte": "99.934,28",
         "dia_debito": 18, "parcelas_pagas": 21, "saldo_devedor": 84188.44,
         "condicao": "0,49% + Selic"},
        {"programa": "  ", "aporte": 1000},
        {"programa": "X", "prazo_meses": 48, "parcelas_pagas": 99,
         "dia_debito": 45, "condicao": "inventada"},
    ]), "martinsousa")
    ok("contrato sem programa não é gravado", len(linhas) == 2)
    ok("aporte com vírgula chega certo", linhas[0]["aporte"] == 99934.28)
    ok("pagas não passa do prazo", linhas[1]["parcelas_pagas"] == 48)
    ok("dia fora do calendário é aparado", linhas[1]["dia_debito"] == 31)
    ok("condição fora da lista cai no padrão",
       linhas[1]["condicao"] == CONDICOES[0])
    ok("a data fica no formato da planilha",
       linhas[0]["data_contratacao"] == "2024-02-16")

    # Os sete contratos do resumo do gestor
    ok("são sete contratos", len(SUGESTOES) == 7)
    ok("os aportes somam R$ 501.570,38",
       abs(sum(x[5] for x in SUGESTOES) - 501570.38) < 0.01)
    ok("as parcelas somam R$ 15.723,72",
       abs(sum(x[7] for x in SUGESTOES) - 15723.72) < 0.01)
    ok("os saldos somam R$ 477.112,93",
       abs(sum(x[9] for x in SUGESTOES) - 477112.93) < 0.01)
    ok("nenhum nome se repete",
       len({x[0] for x in SUGESTOES}) == len(SUGESTOES))
    ok("seis contratos seguem a Selic e um tem taxa fixa",
       [x[10] for x in SUGESTOES].count("Fixa") == 1)
    ok("o de taxa fixa é o de 2,19% a.m.",
       [x[11] for x in SUGESTOES if x[10] == "Fixa"] == [2.19])
    ok("toda condição sugerida existe na lista",
       {x[10] for x in SUGESTOES} <= set(CONDICOES))
    ok("todo dia de débito cabe no calendário",
       all(1 <= x[6] <= 31 for x in SUGESTOES))
    ok("nenhuma parcela paga passa do prazo",
       all(x[8] <= x[4] for x in SUGESTOES))

    _fixo = [x for x in SUGESTOES if x[10] == "Fixa"][0]
    _am, _aa = taxas(_fixo[10], 15, _fixo[11])
    ok("o contrato de taxa fixa usa 2,19% a.m.", abs(_am - 0.0219) < 1e-9)
    ok("e isso dá exatamente os 26,28% a.a. do resumo",
       abs(_aa - 0.2628) < 1e-9)

    # A divida somada
    _d = pd.DataFrame([
        {"programa": "A", "aporte": 100000, "saldo_devedor": 84000,
         "parcela": 3300, "prazo_meses": 48, "parcelas_pagas": 21},
        {"programa": "B", "aporte": 40000, "saldo_devedor": 46000,
         "parcela": 1264, "prazo_meses": 48, "parcelas_pagas": 8},
        {"programa": "  ", "aporte": 99999, "saldo_devedor": 99999},
    ])
    _t = totais(_d)
    ok("contrato sem nome não entra na dívida", _t["contratos"] == 2)
    ok("o saldo devedor soma o que foi informado",
       _t["saldo_devedor"] == 130000.0)
    ok("o aporte soma o que foi tomado", _t["aporte"] == 140000.0)
    ok("a parcela mensal soma todas", _t["parcela_mensal"] == 4564.0)
    ok("as parcelas restantes são prazo menos pagas",
       _t["parcelas_restantes"] == (48 - 21) + (48 - 8))
    ok("o total a pagar é o que ainda vai sair do caixa",
       _t["total_a_pagar"] == 27 * 3300 + 40 * 1264)
    ok("o juro futuro é o total a pagar menos o saldo devedor",
       _t["juros_futuros"] == _t["total_a_pagar"] - _t["saldo_devedor"])
    ok("contrato quitado não tem parcela restante",
       totais(pd.DataFrame([{"programa": "C", "parcela": 500,
                             "prazo_meses": 48,
                             "parcelas_pagas": 48}]))["total_a_pagar"] == 0.0)
    ok("pagas acima do prazo não vira parcela negativa",
       totais(pd.DataFrame([{"programa": "C", "parcela": 500,
                             "prazo_meses": 48,
                             "parcelas_pagas": 99}]))["parcelas_restantes"] == 0)
    ok("tabela vazia não derruba o total", totais(pd.DataFrame())["contratos"] == 0)

    _real = pd.DataFrame([{"programa": p, "aporte": a, "saldo_devedor": s_,
                           "parcela": pc, "prazo_meses": pz, "parcelas_pagas": pg}
                          for p, _, _, _, pz, a, _, pc, pg, s_, _, _ in SUGESTOES])
    ok("a dívida de hoje é os R$ 477.112,93 do resumo",
       abs(totais(_real)["saldo_devedor"] - 477112.93) < 0.01)

    ok("real sai no formato brasileiro", _brl(3304.86) == "R$ 3.304,86")
    ok("mês sem data aparece como travessão", _mes_texto(None) == "—")

    print("\nfalhas:", falhas)
