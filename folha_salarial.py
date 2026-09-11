"""folha_salarial.py — A folha inteira: gestores e colaboradores, lado a lado.

POR QUE ELA SAIU DA GRADE GENÉRICA
----------------------------------
Custo fixo é um valor por item. Folha não: cada pessoa tem várias verbas que se
somam, e um desconto que pode entrar por alguns meses e sair. Enfiar isso na
grade de «item, valor» obrigaria a lançar a mesma pessoa em cinco linhas — e aí
ninguém mais sabe quanto custa uma pessoa, que é justamente a pergunta.

DUAS TABELAS, PORQUE SÃO DUAS CONDIÇÕES
---------------------------------------
    Gestores       pró-labore, bônus, vales — e um desconto com prazo
    Colaboradores  salário, encargos CLT, provisões, refeição, multa do FGTS

Isto começou como uma tabela só com uma coluna de grupo, e estava errado: as
duas não compartilham campo nenhum além do nome. Gestor não tem FGTS nem
admissão; colaborador não tem pró-labore nem vale-combustível. Numa tabela só,
cada linha ficaria com metade das colunas vazia e as duas contas conviveriam
sem se encontrar.

A soma da folha é uma só, no fim da tela: as duas tabelas alimentam o mesmo
total, e é isso que impede que virem dois números.

O DESCONTO TEM PRAZO
--------------------
Desconto sem prazo é desconto para sempre, e não foi isso que se combinou com
ninguém. Ele vale de `desconto_desde` por `desconto_meses`, e some sozinho
depois disso — sem precisar de alguém lembrar de apagar a linha, que é o tipo
de lembrete que ninguém cumpre.

    total bruto    = salário + pró-labore + bônus + VA + VR + VC
    total líquido  = total bruto − desconto (nos meses em que ele vigora)
    provisão 13º   = 1/12 sobre a parte SALARIAL (salário + pró-labore)

O 13º fica fora do total líquido e aparece em coluna própria: ele não sai do
caixa no mês, fica guardado para sair em dezembro. Somado ao total, inflaria o
custo do mês e esconderia o caixa — que é o erro que a tela de colaboradores
também evita.

A provisão incide só sobre salário e pró-labore, e não sobre bônus e vales:
vale-alimentação e vale-refeição não têm natureza salarial. Se a contabilidade
disser que algum deles entra na base aqui, a lista `BASE_DECIMO` é onde mudar.

REAJUSTE NÃO SE DIGITA AQUI
---------------------------
Trocar o valor de uma verba reescreve o passado: janeiro passaria a valer o
salário de maio. Reajuste entra em «Ajuste de valor», com o mês em que passou a
valer, e ele substitui o TOTAL BRUTO da pessoa daquele mês em diante.
"""

from datetime import date, datetime, timezone, timedelta

import pandas as pd
import streamlit as st

ABA_NOME = "folha_salarial"

VERBAS = ["salario", "pro_labore", "bonus", "vale_alimentacao",
          "vale_refeicao", "vale_combustivel"]

COLUNAS = (["pessoa"] + VERBAS +
           ["vigente_desde", "desconto", "desconto_desde", "desconto_meses",
            "desconto_descricao", "dia_debito", "forma_pagamento",
            "atualizado_em", "atualizado_por"])

FORMAS = ["PIX", "Boleto", "Cartão", "Transferência"]

# 1/12 por mês trabalhado. Mesma taxa usada na tela de colaboradores — as duas
# provisionam o mesmo direito, e duas taxas diferentes para a mesma conta
# passariam a discordar na primeira vez que uma fosse ajustada.
TAXA_DECIMO = 0.083

# Sobre o que o 13º é provisionado. Bônus e vales ficam de fora: não têm
# natureza salarial.
BASE_DECIMO = ["salario", "pro_labore"]

# Quem já se sabe que está na folha. É sugestão de partida, não cadastro: só
# vira linha na planilha depois de salvar. A lista de quem trabalha aqui mora na
# aba `equipe`, e não neste arquivo — nome escrito no código já escondeu dois
# colaboradores do painel.
SUGESTOES = ["Leonardo", "Renan"]

ROTULOS = {
    "salario": "Salário", "pro_labore": "Pró-labore", "bonus": "Bônus",
    "vale_alimentacao": "Vale alimentação", "vale_refeicao": "Vale refeição",
    "vale_combustivel": "Vale combustível",
}

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


# ── Contas ───────────────────────────────────────────────────────────────────

def total_bruto(linha):
    """A soma das verbas da pessoa."""
    return round(sum(_num(linha.get(v)) for v in VERBAS), 2)


def base_salarial(linha):
    """A parte das verbas que tem natureza salarial — a base do 13º."""
    return round(sum(_num(linha.get(v)) for v in BASE_DECIMO), 2)


def provisao_decimo(linha, taxa=None):
    """1/12 de 13º do mês, sobre a base salarial."""
    t = TAXA_DECIMO if taxa is None else max(_num(taxa), 0.0)
    return round(base_salarial(linha) * t, 2)


def desconto_no_mes(linha, ano, mes):
    """O desconto que incide naquele mês. Zero fora da janela combinada.

    Sem mês de início não há janela: o desconto passa a valer em todo mês, que
    é o contrário de ter prazo. Nesse caso ele fica fora da conta e a tela
    avisa — melhor não descontar do que descontar para sempre por engano.
    """
    valor = _num(linha.get("desconto"))
    if valor <= 0:
        return 0.0
    aj = _aj()
    inicio = aj.mes_de(linha.get("desconto_desde"))
    if not inicio:
        return 0.0
    meses = int(_num(linha.get("desconto_meses"), 0))
    alvo = (int(ano), int(mes))
    if alvo < inicio:
        return 0.0
    if meses <= 0:
        return valor            # prazo em branco: segue até alguém encerrar
    decorridos = (alvo[0] * 12 + alvo[1]) - (inicio[0] * 12 + inicio[1])
    return valor if decorridos < meses else 0.0


def custo_no_mes(linha, ano, mes, ajustes_da_pessoa=None):
    """Quanto esta pessoa custou naquele mês, já com reajuste e desconto.

    O reajuste substitui o TOTAL BRUTO: é assim que um aumento chega, e
    espalhar o novo valor pelas seis verbas exigiria adivinhar qual delas
    subiu.
    """
    aj = _aj()
    bruto = aj.valor_no_mes(total_bruto(linha), linha.get("vigente_desde"),
                            ajustes_da_pessoa, ano, mes)
    if bruto <= 0:
        return 0.0
    return round(max(bruto - desconto_no_mes(linha, ano, mes), 0.0), 2)


def total_da_folha(df, ano, mes, ajustes_df=None):
    """A folha inteira naquele mês."""
    d = pd.DataFrame(df)
    if d.empty:
        return 0.0
    mapa = _aj().por_item(ajustes_df) if ajustes_df is not None else {}
    total = 0.0
    for _, r in d.iterrows():
        pessoa = str(r.get("pessoa", "") or "").strip()
        if not pessoa:
            continue
        total += custo_no_mes(r, ano, mes, mapa.get((ABA_NOME, pessoa)))
    return round(total, 2)


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
    """Linhas prontas para a planilha. Descarta linha sem nome de pessoa."""
    aj = _aj()
    agora = datetime.now(FUSO).strftime("%Y-%m-%d %H:%M")
    saida = []
    for _, r in pd.DataFrame(df).iterrows():
        pessoa = str(r.get("pessoa", "") or "").strip()
        if not pessoa:
            continue
        linha = {
            "pessoa": pessoa,
            "vigente_desde": aj.texto_mes(aj.mes_de(r.get("vigente_desde"))),
            "desconto": round(_num(r.get("desconto")), 2),
            "desconto_desde": aj.texto_mes(aj.mes_de(r.get("desconto_desde"))),
            "desconto_meses": max(int(_num(r.get("desconto_meses"), 0)), 0),
            "desconto_descricao": str(r.get("desconto_descricao", "") or "").strip()[:200],
            "dia_debito": min(max(int(_num(r.get("dia_debito"), 0)), 0), 31),
            "forma_pagamento": (str(r.get("forma_pagamento", "") or "").strip()
                                if str(r.get("forma_pagamento", "") or "").strip() in FORMAS
                                else ""),
            "atualizado_em": agora,
            "atualizado_por": str(usuario or "")[:60],
        }
        for v in VERBAS:
            linha[v] = round(_num(r.get(v)), 2)
        saida.append(linha)
    return saida


def salvar(df, usuario=""):
    linhas = _normalizar(df, usuario)
    try:
        aba = _aba()
        cabecalho = aba.row_values(1) or list(COLUNAS)
        corpo = [[l.get(str(c).strip().lower(), "") for c in cabecalho]
                 for l in linhas]
        aba.clear()
        aba.update("A1", [cabecalho] + corpo, value_input_option="RAW")
    except Exception as e:
        return False, type(e).__name__
    carregar.clear()
    return True, f"{len(linhas)} pessoas gravadas"


def _brl(v):
    return "R$ " + f"{float(v):,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")


# ── Tela ─────────────────────────────────────────────────────────────────────

def pagina(usuario_logado=None):
    """A folha inteira: as duas tabelas e um total só."""
    import colaboradores as _co

    st.markdown("#### 👥 Folha salarial")
    st.caption(
        "Duas tabelas porque são duas condições. Reajuste **não** se digita "
        "aqui — entra em «Ajuste de valor», com o mês em que passou a valer."
    )

    taxas = _co.painel_taxas(_co.carregar_taxas())

    # O mês é escolhido UMA vez, no topo, e vale para as duas tabelas. Um
    # seletor por tabela deixaria comparar março dos gestores com setembro dos
    # colaboradores e somar os dois no total.
    hoje = datetime.now(FUSO).date()
    c1, c2 = st.columns(2)
    ano = c1.number_input("Ano", min_value=2020, max_value=2100,
                          value=hoje.year, step=1, key="folha_ano")
    mes = c2.number_input("Mês", min_value=1, max_value=12,
                          value=hoje.month, step=1, key="folha_mes")

    st.markdown("##### 🧑‍💼 Gestores")
    st.caption("Pró-labore, bônus e vales. O **novo total** já tira o "
               "desconto, e o desconto só incide nos meses do prazo "
               "combinado.")
    df = carregar()
    if df.empty:
        df = pd.DataFrame(
            [{**{v: 0.0 for v in VERBAS}, "pessoa": p,
              "vigente_desde": "", "desconto": 0.0, "desconto_desde": "",
              "desconto_meses": 0, "desconto_descricao": "", "dia_debito": 30,
              "forma_pagamento": "Transferência", "atualizado_em": "",
              "atualizado_por": ""} for p in SUGESTOES],
            columns=COLUNAS)
        st.info("Aba ainda vazia. Estas pessoas são sugestão de partida — nada "
                "foi gravado até você salvar.")

    visiveis = (["pessoa"] + VERBAS +
                ["vigente_desde", "desconto", "desconto_desde",
                 "desconto_meses", "desconto_descricao", "dia_debito",
                 "forma_pagamento"])
    dinheiro = lambda rot: st.column_config.NumberColumn(
        rot, min_value=0.0, step=0.01, format="%.2f", width="small")

    editado = st.data_editor(
        df[visiveis],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="ed_folha_salarial",
        column_config={
            "pessoa": st.column_config.TextColumn(
                "Pessoa", required=True, width="medium"),
            **{v: dinheiro(ROTULOS[v]) for v in VERBAS},
            "vigente_desde": st.column_config.TextColumn(
                "Está desde", width="small",
                help="AAAA-MM. Antes deste mês a pessoa não entra no custo."),
            "desconto": st.column_config.NumberColumn(
                "Desconto (R$)", min_value=0.0, step=0.01, format="%.2f",
                width="small"),
            "desconto_desde": st.column_config.TextColumn(
                "Desconto desde", width="small", help="AAAA-MM."),
            "desconto_meses": st.column_config.NumberColumn(
                "Prazo (meses)", min_value=0, max_value=120, step=1,
                format="%d", width="small",
                help="Por quantos meses o desconto incide. 0 = até alguém "
                     "encerrar."),
            "desconto_descricao": st.column_config.TextColumn(
                "Motivo do desconto", width="large"),
            "dia_debito": st.column_config.NumberColumn(
                "Dia", min_value=0, max_value=31, step=1, format="%d",
                width="small"),
            "forma_pagamento": st.column_config.SelectboxColumn(
                "Forma de pagamento", options=FORMAS, width="medium"),
        },
    )

    if st.button("💾 Salvar gestores", type="primary", key="btn_salvar_folha"):
        ok, msg = salvar(editado, usuario_logado)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(f"Não consegui gravar: {msg}")

    _tot_gestores = _conferencia(editado, ano, mes)

    st.markdown("---")
    st.markdown("##### 👔 Colaboradores (CLT)")
    st.caption(
        "Salário, encargos e provisões. Quem **não** é registrado não soma "
        "FGTS, INSS, férias, 13º nem multa — só o salário, a refeição e o "
        "vale-transporte."
    )
    _ed_colab = _co.bloco(usuario_logado, taxas)
    _tot_colab = _co.conferencia(_ed_colab, taxas, ano, mes)

    st.markdown("---")
    g = st.columns(3)
    g[0].metric("Gestores", _brl(_tot_gestores))
    g[1].metric("Colaboradores", _brl(_tot_colab))
    g[2].metric(f"Folha em {int(mes):02d}/{int(ano)}",
                _brl(_tot_gestores + _tot_colab))


def _conferencia(editado, ano, mes):
    """Total, desconto e novo total de cada gestor, no mês escolhido.

    Fica fora da grade de propósito: o `data_editor` só redesenha uma coluna
    calculada no rerun seguinte, e um total que mostra o número anterior ao que
    acabou de ser digitado é pior que nenhum total.
    """
    d = pd.DataFrame(editado)
    if d.empty:
        return 0.0
    aj = _aj()
    ajustes_df = aj.carregar()
    mapa = aj.por_item(ajustes_df)

    linhas, sem_prazo, decimo_total = [], [], 0.0
    for _, r in d.iterrows():
        pessoa = str(r.get("pessoa", "") or "").strip()
        if not pessoa:
            continue
        bruto_hoje = total_bruto(r)
        bruto_mes = aj.valor_no_mes(bruto_hoje, r.get("vigente_desde"),
                                    mapa.get((ABA_NOME, pessoa)), ano, mes)
        desc = desconto_no_mes(r, ano, mes)
        if _num(r.get("desconto")) > 0 and not aj.mes_de(r.get("desconto_desde")):
            sem_prazo.append(pessoa)
        # Zero antes de a pessoa entrar: provisionar 13º de quem ainda nao
        # trabalhou guardaria dinheiro para um direito que nao nasceu.
        decimo = provisao_decimo(r) if bruto_mes > 0 else 0.0
        decimo_total += decimo
        linhas.append({
            "Pessoa": pessoa,
            "Total": _brl(bruto_mes),
            "Desconto": _brl(desc),
            "Novo total": _brl(max(bruto_mes - desc, 0.0)),
            "1/12 de 13º": _brl(decimo),
            "Motivo": r.get("desconto_descricao") or "",
        })
    if not linhas:
        return 0.0

    st.dataframe(pd.DataFrame(linhas), use_container_width=True,
                 hide_index=True)

    if sem_prazo:
        st.warning(
            "Desconto sem mês de início fica **fora** da conta: "
            + ", ".join(sorted(set(sem_prazo)))
            + ". Sem o mês, ele valeria em todos os meses, inclusive nos "
              "anteriores — e não foi isso que se combinou.")

    _total = total_da_folha(d, ano, mes, ajustes_df)
    cols = st.columns(2)
    cols[0].metric(f"Gestores em {int(mes):02d}/{int(ano)}", _brl(_total))
    cols[1].metric("1/12 de 13º provisionado", _brl(round(decimo_total, 2)),
                   help="Fica guardado, não sai do caixa neste mês. Incide "
                        "sobre salário e pró-labore — bônus e vales ficam de "
                        "fora por não terem natureza salarial.")
    return _total


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    leo = {"pessoa": "Leonardo", "salario": 0,
           "pro_labore": 7000, "bonus": 1000, "vale_alimentacao": 500,
           "vale_refeicao": 400, "vale_combustivel": 600,
           "vigente_desde": "2026-01"}
    ok("o total é a soma das verbas", total_bruto(leo) == 9500.0)
    ok("verba em branco não atrapalha a soma",
       total_bruto({"pro_labore": 7000}) == 7000.0)
    ok("verba com vírgula entra na soma",
       total_bruto({"salario": "2.033,00"}) == 2033.0)
    ok("pessoa sem verba nenhuma soma zero", total_bruto({}) == 0.0)

    # Desconto com prazo de 3 meses a partir de maio
    com_desc = {**leo, "desconto": 300, "desconto_desde": "2026-05",
                "desconto_meses": 3, "desconto_descricao": "adiantamento"}
    ok("antes do início, não desconta", desconto_no_mes(com_desc, 2026, 4) == 0.0)
    ok("no primeiro mês, desconta", desconto_no_mes(com_desc, 2026, 5) == 300.0)
    ok("no último mês do prazo, ainda desconta",
       desconto_no_mes(com_desc, 2026, 7) == 300.0)
    ok("passado o prazo, para sozinho",
       desconto_no_mes(com_desc, 2026, 8) == 0.0)
    ok("prazo em branco segue descontando",
       desconto_no_mes({**com_desc, "desconto_meses": 0}, 2027, 1) == 300.0)
    ok("desconto sem mês de início fica fora da conta",
       desconto_no_mes({**com_desc, "desconto_desde": ""}, 2026, 6) == 0.0)
    ok("desconto zerado não desconta",
       desconto_no_mes({**com_desc, "desconto": 0}, 2026, 5) == 0.0)

    ok("o novo total é o total menos o desconto",
       custo_no_mes(com_desc, 2026, 5) == 9200.0)
    ok("fora do prazo, o novo total volta a ser o total",
       custo_no_mes(com_desc, 2026, 8) == 9500.0)
    ok("desconto maior que o salário não vira custo negativo",
       custo_no_mes({**com_desc, "desconto": 99999}, 2026, 5) == 0.0)
    ok("antes de a pessoa entrar, ela não custa",
       custo_no_mes({**leo, "vigente_desde": "2026-06"}, 2026, 5) == 0.0)

    # Reajuste pelo Ajuste de valor: substitui o TOTAL BRUTO
    aj_leo = [{"valor_novo": 11000, "vigente_desde": "2026-07"}]
    ok("antes do reajuste vale a soma das verbas",
       custo_no_mes(leo, 2026, 6, aj_leo) == 9500.0)
    ok("do mês do reajuste em diante vale o novo total",
       custo_no_mes(leo, 2026, 7, aj_leo) == 11000.0)
    ok("reajuste e desconto convivem: desconta sobre o valor novo",
       custo_no_mes({**com_desc, "desconto_meses": 12}, 2026, 7, aj_leo)
       == 10700.0)

    renan = {"pessoa": "Renan", "pro_labore": 6500, "vale_alimentacao": 500,
             "vale_refeicao": 400, "vigente_desde": "2026-01"}
    folha = pd.DataFrame([leo, renan])
    ok("a folha soma os gestores", total_da_folha(folha, 2026, 6) == 9500 + 7400)
    ok("linha sem pessoa não entra na folha",
       total_da_folha(pd.DataFrame([{"pessoa": "  ", "salario": 9999}]),
                      2026, 6) == 0.0)
    ok("folha vazia dá zero", total_da_folha(pd.DataFrame(), 2026, 6) == 0.0)
    ok("o ajuste de uma pessoa não muda o custo das outras",
       total_da_folha(folha, 2026, 7,
                      pd.DataFrame([{"grade": ABA_NOME, "item": "Leonardo",
                                     "valor_novo": 11000,
                                     "vigente_desde": "2026-07"}]))
       == 11000 + 7400)

    linhas = _normalizar(pd.DataFrame([
        {**com_desc, "dia_debito": 45, "forma_pagamento": "Cheque",
         "desconto_desde": "05/2026", "desconto_meses": -3},
        {"pessoa": "", "salario": 9999},
        {"pessoa": "X"},
    ]), "martinsousa")
    ok("linha sem pessoa não é gravada", len(linhas) == 2)
    ok("a vigência do desconto vira AAAA-MM",
       linhas[0]["desconto_desde"] == "2026-05")
    ok("prazo negativo vira zero", linhas[0]["desconto_meses"] == 0)
    ok("dia fora do calendário é aparado", linhas[0]["dia_debito"] == 31)
    ok("forma de pagamento fora da lista fica vazia",
       linhas[0]["forma_pagamento"] == "")
    ok("toda verba é gravada, mesmo em branco",
       all(v in linhas[1] for v in VERBAS))

    ok("o 13º provisiona 1/12 do pró-labore do gestor",
       provisao_decimo(leo) == round(7000 * 0.083, 2))
    ok("bônus e vales ficam fora da base do 13º",
       base_salarial(leo) == 7000.0)
    ok("quando há salário, ele entra na base do 13º",
       provisao_decimo({"salario": 2400}) == round(2400 * 0.083, 2))
    ok("quem não tem verba salarial não provisiona 13º",
       provisao_decimo({"vale_refeicao": 400}) == 0.0)
    ok("a taxa do 13º é a mesma das duas telas",
       TAXA_DECIMO == __import__("colaboradores").TAXAS["decimo_1_12"][2])

    ok("a tabela de gestores sugere Leonardo e Renan",
       set(SUGESTOES) == {"Leonardo", "Renan"})
    ok("a folha de gestores não tem coluna de grupo",
       "grupo" not in COLUNAS)

    print("\nfalhas:", falhas)
