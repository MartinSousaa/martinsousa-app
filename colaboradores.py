"""colaboradores.py — O que cada CLT custa por mês, e o que precisa ficar em caixa.

DUAS PERGUNTAS DIFERENTES NA MESMA TELA
---------------------------------------
    custo do mês      o que sai do caixa agora: salário, encargos, refeição
    provisão          o que NÃO sai agora mas vai sair: férias, 13º, multa

Provisão tratada como custo do mês infla o custo e esconde o caixa; provisão
esquecida produz o susto de dezembro. As duas aparecem separadas e somadas.

A MULTA DO FGTS NÃO É POR PESSOA
--------------------------------
Ela só existe se houver desligamento, e o Studio não sabe quem vai sair. Por
isso ela fica fora do custo de cada colaborador e vira uma RESERVA do quadro
inteiro, pela regra que o gestor deu:

    exposição de cada um   =  salário × taxa da multa × meses de casa
    reserva sugerida       =  a MAIOR entre
                               · metade da exposição do quadro
                               · a soma das três maiores exposições individuais

As três maiores, e não três quaisquer: desligamento não sorteia quem sai, e uma
reserva dimensionada pela média quebra justamente quando saem os mais caros.

AS TAXAS NÃO SÃO LEI DESTE ARQUIVO
----------------------------------
Elas vieram da contabilidade e mudam — por lei, por acordo, por mudança de
enquadramento. Ficam numa aba da planilha e se editam na tela. Percentual
escrito no código vira a primeira coisa que discorda da realidade, e ninguém
descobre até o custo sair errado.

DUAS COISAS A CONFERIR COM A CONTABILIDADE
------------------------------------------
Não são opinião sobre o negócio; são perguntas que mudam o número:

1. **INSS 10%** — a empresa é do Simples Nacional (a aba SIMPLES - FLEX do
   Controle_MS é de DAS/DARF). Nos anexos I, II, III e V a contribuição
   patronal já está DENTRO do DAS; só o anexo IV recolhe à parte. Se for um
   desses quatro, este 10% está sendo contado duas vezes.

2. **Vale-transporte 6%** — 6% do salário é o teto do DESCONTO no salário do
   empregado, não o custo do empregador. O custo é o que passar disso: se a
   condução custar menos de 6%, o empregador não paga nada. Como custo, o 6%
   provavelmente está com o sinal trocado.

Enquanto não houver resposta, a conta usa os números que ele informou — é o que
ele tem hoje. As duas perguntas aparecem na tela para não virarem esquecimento.
"""

from datetime import date, datetime, timezone, timedelta

import pandas as pd
import streamlit as st

ABA_NOME = "colaboradores"
ABA_PARAMS = "clt_parametros"

COLUNAS = ["funcionario", "cargo", "salario_base", "admissao", "dias_uteis",
           "atualizado_em", "atualizado_por"]

# Taxa sobre o salário base. O rótulo é o que aparece na tela; `grupo` diz se
# ela sai do caixa no mês (encargo) ou se é dinheiro guardado (provisão).
TAXAS = {
    "fgts":            ("FGTS", "encargo", 0.0800),
    "inss":            ("INSS", "encargo", 0.1000),
    "vale_transporte": ("Vale-transporte", "encargo", 0.0600),
    "ferias_1_12":     ("1/12 de férias", "provisao", 0.0830),
    "terco_ferias":    ("1/3 de férias", "provisao", 0.0280),
    "decimo_1_12":     ("1/12 de 13º", "provisao", 0.0830),
}

# Fora de TAXAS de propósito: ela não entra no custo de ninguém, vira reserva
# do quadro. Ver o cabeçalho.
TAXA_MULTA_FGTS = 0.0400

REFEICAO_DIA = 29.99
DIAS_UTEIS = 22

# Quantos desligamentos simultâneos a reserva precisa cobrir, e que fração da
# exposição total ela precisa alcançar. Os dois vieram do gestor.
DESLIGAMENTOS_COBERTOS = 3
FRACAO_DO_QUADRO = 0.50

FUSO = timezone(timedelta(hours=-3))


def _aj():
    import ajustes
    return ajustes


def _num(v, padrao=0.0):
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


# ── Contas ───────────────────────────────────────────────────────────────────

def taxas_padrao():
    """{chave: fração} com os valores de partida, prontos para serem editados."""
    d = {k: v[2] for k, v in TAXAS.items()}
    d["multa_fgts"] = TAXA_MULTA_FGTS
    d["refeicao_dia"] = REFEICAO_DIA
    return d


def custo(salario_base, taxas=None, dias_uteis=DIAS_UTEIS):
    """O que este salário custa por mês, aberto em partes.

    Devolve `base`, `encargos`, `provisoes`, `refeicao` e `total`. A multa do
    FGTS não entra: ela é reserva do quadro, não custo de uma pessoa.
    """
    t = {**taxas_padrao(), **(taxas or {})}
    base = max(_num(salario_base), 0.0)
    encargos = sum(base * max(_num(t.get(k)), 0.0)
                   for k, v in TAXAS.items() if v[1] == "encargo")
    provisoes = sum(base * max(_num(t.get(k)), 0.0)
                    for k, v in TAXAS.items() if v[1] == "provisao")
    refeicao = max(_num(t.get("refeicao_dia")), 0.0) * max(int(_num(dias_uteis, 0)), 0)
    return {
        "base": round(base, 2),
        "encargos": round(encargos, 2),
        "provisoes": round(provisoes, 2),
        "refeicao": round(refeicao, 2),
        "total": round(base + encargos + provisoes + refeicao, 2),
    }


def meses_de_casa(admissao, ano, mes):
    """Meses completos entre a admissão e o mês de referência. Zero sem data."""
    aj = _aj()
    ini = aj.mes_de(admissao)
    if not ini:
        return 0
    n = (int(ano) * 12 + int(mes)) - (ini[0] * 12 + ini[1])
    return max(n, 0)


def exposicao_multa(salario_base, admissao, ano, mes, taxa=None):
    """Quanto de multa do FGTS este colaborador já acumulou até aquele mês."""
    t = TAXA_MULTA_FGTS if taxa is None else max(_num(taxa), 0.0)
    return round(max(_num(salario_base), 0.0) * t
                 * meses_de_casa(admissao, ano, mes), 2)


def reserva_multa(df, ano, mes, taxa=None, ajustes_df=None):
    """A reserva que a multa do FGTS exige do quadro inteiro.

    Devolve as duas contas e a que vale — a maior delas, porque "pelo menos"
    é o que foi pedido, e a menor das duas não atende as duas.
    """
    aj = _aj()
    mapa = aj.por_item(ajustes_df) if ajustes_df is not None else {}
    expos = []
    for _, r in pd.DataFrame(df).iterrows():
        nome = str(r.get("funcionario", "") or "").strip()
        if not nome:
            continue
        base = aj.valor_no_mes(r.get("salario_base"), r.get("admissao"),
                               mapa.get((ABA_NOME, nome)), ano, mes)
        if base <= 0:
            continue
        expos.append(exposicao_multa(base, r.get("admissao"), ano, mes, taxa))
    total = round(sum(expos), 2)
    metade = round(total * FRACAO_DO_QUADRO, 2)
    tres = round(sum(sorted(expos, reverse=True)[:DESLIGAMENTOS_COBERTOS]), 2)
    return {
        "exposicao_total": total,
        "metade_do_quadro": metade,
        "tres_desligamentos": tres,
        "reserva": max(metade, tres),
        "criterio": ("metade do quadro" if metade >= tres
                     else f"{DESLIGAMENTOS_COBERTOS} desligamentos"),
        "pessoas": len(expos),
    }


def folha_clt(df, ano, mes, taxas=None, ajustes_df=None):
    """[{funcionario, cargo, base, encargos, provisoes, refeicao, total}] do mês."""
    aj = _aj()
    mapa = aj.por_item(ajustes_df) if ajustes_df is not None else {}
    fora = []
    for _, r in pd.DataFrame(df).iterrows():
        nome = str(r.get("funcionario", "") or "").strip()
        if not nome:
            continue
        base = aj.valor_no_mes(r.get("salario_base"), r.get("admissao"),
                               mapa.get((ABA_NOME, nome)), ano, mes)
        if base <= 0:
            # Antes da admissão (ou sem salário) a pessoa não custa. Somar zero
            # e mostrar a linha faria parecer que ela está na folha de graça.
            continue
        c = custo(base, taxas, r.get("dias_uteis", DIAS_UTEIS))
        c.update({"funcionario": nome, "cargo": str(r.get("cargo", "") or "")})
        fora.append(c)
    return fora


# ── Planilha ─────────────────────────────────────────────────────────────────

def _abrir(nome, colunas):
    import gspread
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        aba = planilha.worksheet(nome)
    except gspread.exceptions.WorksheetNotFound:
        aba = planilha.add_worksheet(title=nome, rows=200, cols=len(colunas))
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
        registros = _abrir(ABA_NOME, COLUNAS).get_all_records(
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
def carregar_taxas():
    """As taxas gravadas, completadas com os padrões para o que faltar.

    Completar, e não recusar: uma taxa nova no código não pode fazer a tela
    parar de abrir até alguém salvar de novo.
    """
    t = taxas_padrao()
    try:
        registros = _abrir(ABA_PARAMS, ["chave", "valor"]).get_all_records(
            value_render_option="UNFORMATTED_VALUE")
    except Exception:
        return t
    for r in registros:
        chave = str(r.get("chave", "") or "").strip().lower()
        if chave in t:
            t[chave] = _num(r.get("valor"), t[chave])
    return t


def salvar_taxas(taxas):
    try:
        aba = _abrir(ABA_PARAMS, ["chave", "valor"])
        corpo = [[k, round(_num(v), 6)] for k, v in sorted(taxas.items())]
        aba.clear()
        aba.update("A1", [["chave", "valor"]] + corpo,
                   value_input_option="RAW")
    except Exception as e:
        return False, type(e).__name__
    carregar_taxas.clear()
    return True, "taxas gravadas"


def _normalizar(df, usuario=""):
    aj = _aj()
    agora = datetime.now(FUSO).strftime("%Y-%m-%d %H:%M")
    saida = []
    for _, r in pd.DataFrame(df).iterrows():
        nome = str(r.get("funcionario", "") or "").strip()
        if not nome:
            continue
        dias = int(_num(r.get("dias_uteis"), DIAS_UTEIS))
        saida.append({
            "funcionario": nome,
            "cargo": str(r.get("cargo", "") or "").strip()[:80],
            "salario_base": round(_num(r.get("salario_base")), 2),
            "admissao": aj.texto_mes(aj.mes_de(r.get("admissao"))),
            # Mês nenhum tem 40 dias úteis; zero também não é mês.
            "dias_uteis": min(max(dias, 0), 31),
            "atualizado_em": agora,
            "atualizado_por": str(usuario or "")[:60],
        })
    return saida


def salvar(df, usuario=""):
    linhas = _normalizar(df, usuario)
    try:
        aba = _abrir(ABA_NOME, COLUNAS)
        cabecalho = aba.row_values(1) or list(COLUNAS)
        corpo = [[l.get(str(c).strip().lower(), "") for c in cabecalho]
                 for l in linhas]
        aba.clear()
        aba.update("A1", [cabecalho] + corpo, value_input_option="RAW")
    except Exception as e:
        return False, type(e).__name__
    carregar.clear()
    return True, f"{len(linhas)} colaboradores gravados"


def _brl(v):
    return "R$ " + f"{float(v):,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")


# ── Tela ─────────────────────────────────────────────────────────────────────

def _painel_taxas(taxas):
    """As taxas, editáveis. Fechado por padrão: mudam raramente."""
    with st.expander("⚙️ Taxas e valores — o que a contabilidade informou",
                     expanded=False):
        st.caption("Percentuais sobre o salário base. Mudam por lei, acordo ou "
                   "enquadramento — por isso ficam aqui e não no código.")
        novas = {}
        colunas = st.columns(3)
        for i, (k, (rotulo, grupo, _)) in enumerate(TAXAS.items()):
            novas[k] = colunas[i % 3].number_input(
                f"{rotulo} (%)", min_value=0.0, max_value=100.0,
                value=float(taxas.get(k, 0)) * 100, step=0.01, format="%.2f",
                key=f"tx_{k}",
                help="Encargo: sai do caixa no mês." if grupo == "encargo"
                     else "Provisão: fica guardado para sair depois.") / 100.0
        c1, c2 = st.columns(2)
        novas["multa_fgts"] = c1.number_input(
            "Multa do FGTS (%)", min_value=0.0, max_value=100.0,
            value=float(taxas.get("multa_fgts", TAXA_MULTA_FGTS)) * 100,
            step=0.01, format="%.2f", key="tx_multa",
            help="Não entra no custo de ninguém: vira reserva do quadro.") / 100.0
        novas["refeicao_dia"] = c2.number_input(
            "Refeição no local (R$/dia)", min_value=0.0, step=0.01,
            format="%.2f", value=float(taxas.get("refeicao_dia", REFEICAO_DIA)),
            key="tx_ref")

        st.warning(
            "**Duas perguntas para a contabilidade, que mudam o número:**\n\n"
            "1. **INSS 10%** — a empresa é do Simples Nacional. Nos anexos I, "
            "II, III e V a contribuição patronal já está **dentro do DAS**; só "
            "o anexo IV recolhe à parte. Se for um desses quatro, este 10% "
            "está sendo contado duas vezes.\n"
            "2. **Vale-transporte 6%** — 6% é o teto do **desconto no salário "
            "do empregado**, não o custo da empresa. O custo é o que passar "
            "disso; se a condução custar menos de 6%, a empresa não paga nada."
        )
        if st.button("💾 Salvar taxas", key="btn_salvar_taxas"):
            ok, msg = salvar_taxas(novas)
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()
        return novas


def pagina(usuario_logado=None):
    st.markdown("#### 👔 Colaboradores (CLT)")
    st.caption(
        "O que cada colaborador custa por mês, separando o que **sai do caixa "
        "agora** (salário, encargos, refeição) do que **fica guardado para "
        "sair depois** (férias, 13º). A multa do FGTS não entra no custo de "
        "ninguém — vira reserva do quadro, no fim da tela."
    )

    taxas = _painel_taxas(carregar_taxas())

    df = carregar()
    if df.empty:
        df = pd.DataFrame(columns=COLUNAS)
        st.info("Nenhum colaborador cadastrado. Use o «+» no fim da tabela.")

    editado = st.data_editor(
        df[["funcionario", "cargo", "salario_base", "admissao", "dias_uteis"]],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="ed_colaboradores",
        column_config={
            "funcionario": st.column_config.TextColumn(
                "Funcionário", required=True, width="medium"),
            "cargo": st.column_config.TextColumn("Cargo", width="medium"),
            "salario_base": st.column_config.NumberColumn(
                "Salário base (R$)", min_value=0.0, step=0.01, format="%.2f",
                help="O de quando entrou. Reajuste vai em «Ajuste de valor»."),
            "admissao": st.column_config.TextColumn(
                "Admissão", width="small",
                help="AAAA-MM. Antes dela não custa, e é dela que sai o tempo "
                     "de casa para a multa do FGTS."),
            "dias_uteis": st.column_config.NumberColumn(
                "Dias úteis", min_value=0, max_value=31, step=1, format="%d",
                width="small", help="Para a refeição no local."),
        },
    )

    if st.button("💾 Salvar", type="primary", key="btn_salvar_colab"):
        ok, msg = salvar(editado, usuario_logado)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(f"Não consegui gravar: {msg}")

    _conferencia(editado, taxas)


def _conferencia(editado, taxas):
    d = pd.DataFrame(editado)
    if d.empty:
        return
    aj = _aj()
    hoje = datetime.now(FUSO).date()

    st.markdown("##### Custo por colaborador")
    c1, c2 = st.columns(2)
    ano = c1.number_input("Ano", min_value=2020, max_value=2100,
                          value=hoje.year, step=1, key="colab_ano")
    mes = c2.number_input("Mês", min_value=1, max_value=12,
                          value=hoje.month, step=1, key="colab_mes")

    ajustes_df = aj.carregar()
    linhas = folha_clt(d, ano, mes, taxas, ajustes_df)
    if not linhas:
        st.info("Nenhum colaborador com salário neste mês.")
        return

    st.dataframe(pd.DataFrame([{
        "Funcionário": l["funcionario"],
        "Cargo": l["cargo"],
        "Salário base": _brl(l["base"]),
        "Encargos": _brl(l["encargos"]),
        "Provisões": _brl(l["provisoes"]),
        "Refeição": _brl(l["refeicao"]),
        "Custo total": _brl(l["total"]),
    } for l in linhas]), use_container_width=True, hide_index=True)

    soma = lambda c: sum(l[c] for l in linhas)
    m = st.columns(4)
    m[0].metric("Sai do caixa no mês",
                _brl(soma("base") + soma("encargos") + soma("refeicao")))
    m[1].metric("Fica provisionado", _brl(soma("provisoes")))
    m[2].metric(f"Custo do quadro em {int(mes):02d}/{int(ano)}",
                _brl(soma("total")))
    m[3].metric("Custo médio por pessoa",
                _brl(soma("total") / len(linhas)))

    st.markdown("##### Reserva da multa do FGTS")
    r = reserva_multa(d, ano, mes, taxas.get("multa_fgts"), ajustes_df)
    st.caption(
        "Ela não entra no custo de ninguém porque só existe se houver "
        "desligamento. A reserva é a **maior** entre as duas regras — a menor "
        "das duas não atenderia a outra."
    )
    k = st.columns(4)
    k[0].metric("Exposição do quadro", _brl(r["exposicao_total"]),
                help="Se todos fossem desligados hoje.")
    k[1].metric("Metade do quadro", _brl(r["metade_do_quadro"]))
    k[2].metric(f"{DESLIGAMENTOS_COBERTOS} desligamentos",
                _brl(r["tres_desligamentos"]),
                help="As três MAIORES exposições. Desligamento não sorteia "
                     "quem sai, e uma reserva pela média quebra quando saem "
                     "os mais caros.")
    k[3].metric("Reserva necessária", _brl(r["reserva"]),
                help=f"Manda o critério: {r['criterio']}.")


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    t = taxas_padrao()
    ok("as taxas de partida são as que a contabilidade passou",
       t["fgts"] == 0.08 and t["inss"] == 0.10 and t["vale_transporte"] == 0.06)
    ok("1/12 de férias e de 13º são iguais",
       t["ferias_1_12"] == t["decimo_1_12"] == 0.083)
    ok("1/3 das férias é um terço do 1/12",
       abs(t["terco_ferias"] - t["ferias_1_12"] / 3) < 0.001)
    ok("a refeição é de R$ 29,99", t["refeicao_dia"] == 29.99)

    c = custo(2000)
    ok("encargos são 24% do salário (8+10+6)", abs(c["encargos"] - 480.0) < 0.01)
    ok("provisões são 19,4% do salário (8,3+2,8+8,3)",
       abs(c["provisoes"] - 388.0) < 0.01)
    ok("refeição é 22 dias a R$ 29,99", abs(c["refeicao"] - 659.78) < 0.01)
    ok("o total soma base, encargos, provisões e refeição",
       abs(c["total"] - (2000 + 480 + 388 + 659.78)) < 0.01)
    ok("a multa do FGTS NÃO entra no custo da pessoa",
       abs(c["total"] - 3527.78) < 0.01)

    ok("menos dias úteis, menos refeição",
       custo(2000, dias_uteis=20)["refeicao"] < c["refeicao"])
    ok("zero dias úteis não dá refeição",
       custo(2000, dias_uteis=0)["refeicao"] == 0.0)
    ok("salário zero dá custo só de refeição",
       custo(0)["total"] == custo(0)["refeicao"])
    ok("salário ilegível não derruba", custo("abc")["base"] == 0.0)
    ok("taxa trocada muda a conta",
       custo(2000, {"inss": 0.0})["encargos"] == 280.0)
    ok("taxa que falta cai no padrão em vez de sumir",
       custo(2000, {"fgts": 0.08})["encargos"] == 480.0)

    ok("admitido em jan e olhando jan dá zero mês de casa",
       meses_de_casa("2026-01", 2026, 1) == 0)
    ok("admitido em jan e olhando set dá oito meses",
       meses_de_casa("2026-01", 2026, 9) == 8)
    ok("mês anterior à admissão não vira tempo negativo",
       meses_de_casa("2026-09", 2026, 1) == 0)
    ok("sem data de admissão não há tempo de casa",
       meses_de_casa("", 2026, 9) == 0)

    ok("a exposição é salário x taxa x meses de casa",
       exposicao_multa(2000, "2026-01", 2026, 9) == round(2000 * 0.04 * 8, 2))

    quadro = pd.DataFrame([
        {"funcionario": "Monique", "salario_base": 2400, "admissao": "2024-01"},
        {"funcionario": "Beatriz", "salario_base": 2033, "admissao": "2025-06"},
        {"funcionario": "Gabriel", "salario_base": 3080, "admissao": "2023-05"},
        {"funcionario": "Myrella", "salario_base": 1883, "admissao": "2026-08"},
        {"funcionario": "Luiz", "salario_base": 2200, "admissao": "2026-09"},
    ])
    r = reserva_multa(quadro, 2026, 9)
    ok("a exposição do quadro soma todo mundo",
       r["exposicao_total"] > 0 and r["pessoas"] == 5)
    ok("a metade é metade da exposição",
       abs(r["metade_do_quadro"] - r["exposicao_total"] / 2) < 0.01)
    ok("três desligamentos usam as TRÊS MAIORES exposições",
       abs(r["tres_desligamentos"]
           - sum(sorted([exposicao_multa(x["salario_base"], x["admissao"],
                                         2026, 9)
                         for _, x in quadro.iterrows()],
                        reverse=True)[:3])) < 0.01)
    ok("a reserva é a maior das duas regras",
       r["reserva"] == max(r["metade_do_quadro"], r["tres_desligamentos"]))
    ok("a tela diz qual das duas regras mandou",
       r["criterio"] in ("metade do quadro", "3 desligamentos"))
    ok("num quadro pequeno, três desligamentos é quem manda",
       reserva_multa(quadro.head(3), 2026, 9)["criterio"] == "3 desligamentos")
    ok("quadro vazio não derruba a reserva",
       reserva_multa(pd.DataFrame(), 2026, 9)["reserva"] == 0.0)
    ok("quem ainda não foi admitido não entra na exposição",
       reserva_multa(pd.DataFrame([{"funcionario": "Novo",
                                    "salario_base": 5000,
                                    "admissao": "2027-01"}]),
                     2026, 9)["exposicao_total"] == 0.0)

    linhas = folha_clt(quadro, 2026, 9)
    ok("a folha traz uma linha por colaborador com salário", len(linhas) == 5)
    ok("quem entra depois não aparece na folha do mês",
       len(folha_clt(quadro, 2026, 1)) == 3)
    ok("linha sem nome não entra",
       folha_clt(pd.DataFrame([{"funcionario": " ", "salario_base": 999}]),
                 2026, 9) == [])

    # Reajuste pelo Ajuste de valor
    aj_df = pd.DataFrame([{"grade": ABA_NOME, "item": "Monique",
                           "valor_novo": 2800, "vigente_desde": "2026-05"}])
    antes = {l["funcionario"]: l for l in folha_clt(quadro, 2026, 4, None, aj_df)}
    depois = {l["funcionario"]: l for l in folha_clt(quadro, 2026, 6, None, aj_df)}
    ok("antes do reajuste vale o salário base",
       antes["Monique"]["base"] == 2400.0)
    ok("do mês do reajuste em diante vale o novo",
       depois["Monique"]["base"] == 2800.0)
    ok("o reajuste de uma não mexe na outra",
       antes["Beatriz"]["base"] == depois["Beatriz"]["base"])

    linhas_g = _normalizar(pd.DataFrame([
        {"funcionario": "Monique", "cargo": "Analista",
         "salario_base": "2.400,00", "admissao": "01/2024", "dias_uteis": 99},
        {"funcionario": "  ", "salario_base": 1},
    ]), "martinsousa")
    ok("linha sem funcionário não é gravada", len(linhas_g) == 1)
    ok("salário com vírgula chega certo", linhas_g[0]["salario_base"] == 2400.0)
    ok("a admissão vira AAAA-MM", linhas_g[0]["admissao"] == "2024-01")
    ok("mês nenhum tem 99 dias úteis", linhas_g[0]["dias_uteis"] == 31)

    print("\nfalhas:", falhas)
