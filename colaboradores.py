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

COLUNAS = ["funcionario", "cargo", "registrado", "registrado_desde",
           "salario_base", "admissao", "dias_uteis", "atualizado_em",
           "atualizado_por"]

# Taxa sobre o salário base. O rótulo é o que aparece na tela; `grupo` diz se
# ela sai do caixa no mês (encargo) ou se é dinheiro guardado (provisão).
TAXAS = {
    "fgts":            ("FGTS", "encargo", 0.0800),
    "inss":            ("INSS", "encargo", 0.1000),
    "ferias_1_12":     ("1/12 de férias", "provisao", 0.0830),
    "terco_ferias":    ("1/3 de férias", "provisao", 0.0280),
    "decimo_1_12":     ("1/12 de 13º", "provisao", 0.0830),
}

# Fora de TAXAS de propósito: ela não entra no custo de ninguém, vira reserva
# do quadro. Ver o cabeçalho.
TAXA_MULTA_FGTS = 0.0400

# O vale-transporte é VALOR, não percentual. A contabilidade tinha passado 6%,
# mas 6% é o teto do DESCONTO no salário do empregado — não o custo da empresa.
# O gestor conferiu o que de fato sai: R$ 233,33 por colaborador por mês.
VALE_TRANSPORTE_MES = 233.33

# A lei deixa descontar até 6% do salário do empregado a título de
# vale-transporte; o custo da empresa é o que passar disso. Fica DESLIGADO por
# padrão porque o valor informado é o que ele disse que paga, e ligar sozinho
# baixaria o custo dele sem que ninguém tivesse decidido isso. Ligando, a tela
# mostra o custo líquido.
DESCONTAR_VT_PADRAO = False
TETO_DESCONTO_VT = 0.06

REFEICAO_DIA = 29.99
DIAS_UTEIS = 22

# A partir de que mês a refeição no local passa a custar. Vazio = ainda não
# vigora, e é o padrão. Uma taxa que ainda não existe zerada no valor seria
# indistinguível de uma que existe e é de graça — e no dia em que o gestor
# preenchesse o valor, ela passaria a valer para o ano inteiro para trás.
REFEICAO_DESDE_PADRAO = ""

# Quem já se sabe que está na folha. Sugestão de partida, não cadastro: só vira
# linha na planilha depois de salvar. A lista de quem trabalha aqui mora na aba
# `equipe` — nome escrito no código já escondeu dois colaboradores do painel.
CARGO_PADRAO = "Auxiliar de Expedição"
SALARIO_PADRAO = 2006.58
SUGESTOES = [
    {"funcionario": "Gabriel", "cargo": "Analista de Marketing",
     "salario_base": 3000.00, "registrado": "Sim"},
    {"funcionario": "Monique", "registrado": "Não", "salario_base": 2400.00},
    {"funcionario": "Beatriz"},
    {"funcionario": "Myrella"},
    {"funcionario": "Nicollas"},
    {"funcionario": "Luiz"},
]

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
    d["refeicao_desde"] = REFEICAO_DESDE_PADRAO
    d["vale_transporte_mes"] = VALE_TRANSPORTE_MES
    d["descontar_vt"] = 1.0 if DESCONTAR_VT_PADRAO else 0.0
    return d


def refeicao_vigente(taxas, ano, mes):
    """A refeição no local já custa em (ano, mes)?

    Enquanto o mês de início não for informado, ela não vigora — mesmo com o
    valor por dia preenchido. Os R$ 29,99 já estão na tela porque o valor é
    sabido; o que ainda não aconteceu é o benefício começar.
    """
    desde = _aj().mes_de((taxas or {}).get("refeicao_desde"))
    if not desde:
        return False
    return (int(ano), int(mes)) >= desde


def vale_transporte(salario_base, taxas=None):
    """O que o vale-transporte custa à EMPRESA neste mês.

    Sem o desconto ligado, é o valor cheio — que é o que o gestor disse que
    sai. Com ele ligado, é o que passa dos 6% do salário: se a condução custar
    menos que isso, a empresa não paga nada, e o custo é zero e não negativo.
    """
    t = {**taxas_padrao(), **(taxas or {})}
    valor = max(_num(t.get("vale_transporte_mes")), 0.0)
    if not _num(t.get("descontar_vt")):
        return round(valor, 2)
    desconto = max(_num(salario_base), 0.0) * TETO_DESCONTO_VT
    return round(max(valor - desconto, 0.0), 2)


def eh_registrado(v):
    """Quem NÃO tem registro é dito em voz alta; na dúvida, é registrado.

    O padrão é o caso normal: a exceção precisa ser marcada. Se a célula vier
    vazia por descuido, errar para "registrado" cobra tributo de quem talvez
    não deva — e um custo alto demais se descobre na conferência. O contrário
    esconde encargo real e só aparece quando a guia chega.
    """
    return str(v).strip().lower() not in ("não", "nao", "n", "0", "false")


def registrado_no_mes(linha, ano, mes):
    """Esta pessoa tinha registro em (ano, mes)?

    Por que a marca sozinha não basta: ela diz o estado de HOJE. Alguém que
    trabalhou seis meses sem registro e foi registrado em maio teria, só com a
    marca, os seis meses anteriores recalculados com FGTS e INSS que ninguém
    recolheu — e todo indicador que olhe para trás mudaria de valor no dia em
    que a marca fosse ligada.

    O sistema também não tem como descobrir a data sozinho: o que ele grava é o
    momento em que a LINHA foi salva, e esse momento anda a cada nova gravação.
    Além disso o clique não é o fato — o registro pode retroagir, ou a marca
    pode ser ligada semanas depois. Por isso a data é informada.

    Marca «Não» vence tudo: sem registro hoje, não houve registro mês nenhum.
    Marca «Sim» sem data continua valendo para todos os meses, que é como a
    tela se comportava antes de esta coluna existir.
    """
    if not eh_registrado(linha.get("registrado", "Sim")):
        return False
    desde = _aj().mes_de(linha.get("registrado_desde"))
    if not desde:
        return True
    return (int(ano), int(mes)) >= desde


def custo(salario_base, taxas=None, dias_uteis=DIAS_UTEIS, registrado=True,
          com_refeicao=True):
    """O que este salário custa por mês, aberto em partes.

    Devolve `base`, `encargos`, `provisoes`, `refeicao` e `total`. A multa do
    FGTS não entra: ela é reserva do quadro, não custo de uma pessoa.

    Sem registro não há FGTS, INSS, férias nem 13º — não existe vínculo que os
    gere. Refeição no local continua: ela é do dia de trabalho, não do
    contrato. Vale-transporte também, pela mesma razão.
    """
    t = {**taxas_padrao(), **(taxas or {})}
    base = max(_num(salario_base), 0.0)
    reg = eh_registrado(registrado)
    encargos = sum(base * max(_num(t.get(k)), 0.0)
                   for k, v in TAXAS.items() if v[1] == "encargo") if reg else 0.0
    encargos += vale_transporte(base, t)
    provisoes = (sum(base * max(_num(t.get(k)), 0.0)
                     for k, v in TAXAS.items() if v[1] == "provisao")
                 if reg else 0.0)
    refeicao = (max(_num(t.get("refeicao_dia")), 0.0)
                * max(int(_num(dias_uteis, 0)), 0)) if com_refeicao else 0.0
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
        if not registrado_no_mes(r, ano, mes):
            # Sem vínculo não há FGTS, e sem FGTS não há multa de 40%. Somar a
            # exposição dela inflaria a reserva com um risco que não existe.
            continue
        base = aj.valor_no_mes(r.get("salario_base"), r.get("admissao"),
                               mapa.get((ABA_NOME, nome)), ano, mes)
        if base <= 0:
            continue
        # O FGTS conta do REGISTRO, não da entrada na empresa: o tempo
        # trabalhado sem carteira não gerou depósito, e portanto não gera
        # multa. Sem data de registro, vale a admissão — é o que se sabe.
        _base_tempo = r.get("registrado_desde") or r.get("admissao")
        expos.append(exposicao_multa(base, _base_tempo, ano, mes, taxa))
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
        reg = registrado_no_mes(r, ano, mes)
        c = custo(base, taxas, r.get("dias_uteis", DIAS_UTEIS), reg,
                  refeicao_vigente(taxas, ano, mes))
        c.update({"funcionario": nome, "cargo": str(r.get("cargo", "") or ""),
                  "registrado": reg})
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
        if chave not in t:
            continue
        # `refeicao_desde` e um MES, nao um numero: passar por `_num` viraria
        # zero e a refeicao voltaria a nunca vigorar, em silencio.
        t[chave] = (str(r.get("valor", "") or "").strip()
                    if chave == "refeicao_desde" else _num(r.get("valor"), t[chave]))
    return t


def salvar_taxas(taxas):
    try:
        aba = _abrir(ABA_PARAMS, ["chave", "valor"])
        corpo = [[k, v if k == "refeicao_desde" else round(_num(v), 6)]
                 for k, v in sorted(taxas.items())]
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
            "registrado": "Sim" if eh_registrado(r.get("registrado", "Sim")) else "Não",
            "registrado_desde": aj.texto_mes(aj.mes_de(r.get("registrado_desde"))),
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

def painel_taxas(taxas):
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

        c5, c6 = st.columns(2)
        novas["refeicao_desde"] = c5.text_input(
            "Refeição vigente desde (AAAA-MM)", key="tx_ref_desde",
            value=str(taxas.get("refeicao_desde", "") or ""),
            help="Em branco, a refeição NÃO entra na conta de mês nenhum. "
                 "Preencha o mês em que o benefício começar.")
        _rd = _aj().mes_de(novas["refeicao_desde"])
        c6.markdown("&nbsp;", unsafe_allow_html=True)
        c6.caption("✅ Em vigor desde " + _aj().texto_mes(_rd) if _rd
                   else "⏸️ Refeição ainda não vigora — não entra em mês nenhum.")

        c3, c4 = st.columns(2)
        novas["vale_transporte_mes"] = c3.number_input(
            "Vale-transporte (R$/mês por colaborador)", min_value=0.0,
            step=0.01, format="%.2f", key="tx_vt",
            value=float(taxas.get("vale_transporte_mes", VALE_TRANSPORTE_MES)),
            help="Valor, não percentual: 6% é o teto do desconto no salário do "
                 "empregado, não o custo da empresa.")
        novas["descontar_vt"] = 1.0 if c4.checkbox(
            "Abater o desconto legal de 6% do salário",
            value=bool(_num(taxas.get("descontar_vt"))), key="tx_vt_desc",
            help="A lei permite descontar até 6% do salário do empregado. "
                 "Ligue se o valor acima for o CHEIO da recarga; deixe "
                 "desligado se ele já for o que sobra para a empresa.") else 0.0

        st.warning(
            "**Uma pergunta para a contabilidade, que muda o número:**\n\n"
            "**INSS 10%** — existem dois INSS e nenhum é 10%. O **do "
            "empregado** (7,5% a 14%) é descontado do salário dele e já está "
            "dentro do salário base digitado aqui — somar de novo conta duas "
            "vezes. O **patronal** é 20% no regime normal, mas no Simples "
            "Nacional anexos I, II, III e V ele já vem **dentro do DAS**; só o "
            "anexo IV recolhe à parte. A pergunta exata: *em qual anexo do "
            "Simples estamos, e esses 10% são patronal por fora do DAS ou o "
            "desconto do empregado?*"
        )
        if st.button("💾 Salvar taxas", key="btn_salvar_taxas"):
            ok, msg = salvar_taxas(novas)
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()
        return novas


def bloco(usuario_logado=None, taxas=None):
    """A tabela dos colaboradores CLT, para ser desenhada dentro da Folha.

    Não é uma página: não tem título próprio nem painel de taxas. Os dois são
    da Folha, que desenha esta tabela junto com a dos gestores — a folha é uma
    só, e quem abre quer ver as duas na mesma tela.
    """
    taxas = taxas or carregar_taxas()

    df = carregar()
    if df.empty:
        df = pd.DataFrame(
            [{**{"cargo": CARGO_PADRAO, "registrado": "Sim",
                 "registrado_desde": "", "salario_base": SALARIO_PADRAO,
                 "admissao": "", "dias_uteis": DIAS_UTEIS,
                 "atualizado_em": "", "atualizado_por": ""}, **p}
             for p in SUGESTOES],
            columns=COLUNAS)
        st.info("Aba ainda vazia. O quadro já vem preenchido como sugestão — "
                "confira e clique em **Salvar colaboradores**. Nada foi "
                "gravado até você salvar.")

    editado = st.data_editor(
        df[["funcionario", "cargo", "registrado", "registrado_desde",
            "salario_base", "admissao", "dias_uteis"]],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="ed_colaboradores",
        column_config={
            "funcionario": st.column_config.TextColumn(
                "Funcionário", required=True, width="medium"),
            "cargo": st.column_config.TextColumn("Cargo", width="medium"),
            "registrado": st.column_config.SelectboxColumn(
                "Registrado", options=["Sim", "Não"], width="small",
                help="«Não» tira FGTS, INSS, férias, 13º e a multa. Refeição e "
                     "vale-transporte continuam: são do dia de trabalho, não "
                     "do contrato."),
            "registrado_desde": st.column_config.TextColumn(
                "Registrado desde", width="small",
                help="AAAA-MM. Antes desse mês, sem tributo. Em branco com "
                     "«Sim», vale para todos os meses."),
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

    if st.button("💾 Salvar colaboradores", type="primary",
                 key="btn_salvar_colab"):
        ok, msg = salvar(editado, usuario_logado)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(f"Não consegui gravar: {msg}")
    return editado


def conferencia(editado, taxas, ano, mes):
    """Custo de cada colaborador no mês e a reserva da multa. Devolve o total."""
    d = pd.DataFrame(editado)
    if d.empty:
        return 0.0
    aj = _aj()
    ajustes_df = aj.carregar()
    linhas = folha_clt(d, ano, mes, taxas, ajustes_df)
    if not linhas:
        st.info("Nenhum colaborador com salário neste mês.")
        return 0.0

    st.dataframe(pd.DataFrame([{
        "Funcionário": l["funcionario"],
        "Cargo": l["cargo"],
        "Registro": "Sim" if l["registrado"] else "Não",
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
    m[2].metric(f"Colaboradores em {int(mes):02d}/{int(ano)}",
                _brl(soma("total")))
    m[3].metric("Custo médio por pessoa",
                _brl(soma("total") / len(linhas)))

    _sem_reg = [l["funcionario"] for l in linhas if not l["registrado"]]
    if _sem_reg:
        st.caption(f"Em {int(mes):02d}/{int(ano)} sem registro, portanto sem "
                   "FGTS, INSS, férias, 13º nem multa: **"
                   + ", ".join(_sem_reg) + "**.")

    # Marcada como registrada e sem o mês: a conta vale para todos os meses,
    # inclusive os que ela trabalhou sem carteira. Quem olhar o custo de
    # janeiro vai ver tributo que ninguém recolheu, e nada na tela diria por quê.
    _sem_data = [str(r.get("funcionario", "")).strip()
                 for _, r in d.iterrows()
                 if str(r.get("funcionario", "") or "").strip()
                 and eh_registrado(r.get("registrado", "Sim"))
                 and not _aj().mes_de(r.get("registrado_desde"))]
    if _sem_data:
        st.warning(
            "Sem **«Registrado desde»**, o tributo é cobrado em todos os "
            "meses — inclusive nos anteriores ao registro: "
            + ", ".join(sorted(set(_sem_data)))
            + ". Preencha o mês em que a carteira foi assinada para o custo "
              "dos meses de trás ficar certo.")

    st.markdown("###### Reserva da multa do FGTS")
    r = reserva_multa(d, ano, mes, taxas.get("multa_fgts"), ajustes_df)
    st.caption(
        "Ela não entra no custo de ninguém porque só existe se houver "
        "desligamento. A reserva é a **maior** entre as duas regras — a menor "
        "das duas não atenderia a outra. Quem não tem registro fica fora."
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
    return soma("total")


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    t = taxas_padrao()
    ok("as taxas de partida são as que a contabilidade passou",
       t["fgts"] == 0.08 and t["inss"] == 0.10)
    ok("o vale-transporte é valor, não percentual",
       t["vale_transporte_mes"] == 233.33 and "vale_transporte" not in t)
    ok("o desconto de 6% vem desligado", t["descontar_vt"] == 0.0)
    ok("1/12 de férias e de 13º são iguais",
       t["ferias_1_12"] == t["decimo_1_12"] == 0.083)
    ok("1/3 das férias é um terço do 1/12",
       abs(t["terco_ferias"] - t["ferias_1_12"] / 3) < 0.001)
    ok("a refeição é de R$ 29,99", t["refeicao_dia"] == 29.99)
    ok("a refeição ainda não vigora", t["refeicao_desde"] == "")
    ok("sem mês de início, a refeição não entra em mês nenhum",
       not refeicao_vigente(t, 2026, 9) and not refeicao_vigente(t, 2030, 1))
    _rt = {**t, "refeicao_desde": "2026-10"}
    ok("antes do mês de início, não entra", not refeicao_vigente(_rt, 2026, 9))
    ok("no mês de início, entra", refeicao_vigente(_rt, 2026, 10))
    ok("depois, continua entrando", refeicao_vigente(_rt, 2027, 3))

    _q = pd.DataFrame([{"funcionario": "Beatriz", "salario_base": 2006.58,
                        "admissao": "2026-01", "dias_uteis": 22}])
    ok("hoje a refeição não soma no custo de ninguém",
       folha_clt(_q, 2026, 9, t)[0]["refeicao"] == 0.0)
    ok("quando vigorar, ela soma", folha_clt(_q, 2026, 10, _rt)[0]["refeicao"]
       == round(29.99 * 22, 2))

    ok("o quadro sugerido tem seis pessoas", len(SUGESTOES) == 6)
    ok("só o Gabriel tem cargo próprio",
       [p for p in SUGESTOES if "cargo" in p][0]["funcionario"] == "Gabriel")
    ok("o padrão do quadro é auxiliar de expedição a 2.006,58",
       CARGO_PADRAO == "Auxiliar de Expedição" and SALARIO_PADRAO == 2006.58)
    _mon = [p for p in SUGESTOES if p["funcionario"] == "Monique"][0]
    ok("a Monique vem marcada como sem registro", _mon["registrado"] == "Não")
    ok("a Monique recebe R$ 2.400", _mon["salario_base"] == 2400.00)
    ok("os quatro demais ficam no padrão do quadro",
       sum(1 for p in SUGESTOES if "salario_base" not in p) == 4)

    ok("sem o desconto ligado, o VT custa o valor cheio",
       vale_transporte(2000) == 233.33)
    ok("com o desconto ligado, sobra o que passa dos 6%",
       vale_transporte(2000, {"descontar_vt": 1}) == round(233.33 - 120.0, 2))
    ok("condução mais barata que os 6% não custa nada à empresa",
       vale_transporte(10000, {"descontar_vt": 1}) == 0.0)
    ok("o VT nunca fica negativo",
       vale_transporte(99999, {"descontar_vt": 1}) >= 0.0)

    c = custo(2000)
    ok("encargos são 18% do salário mais o VT em reais",
       abs(c["encargos"] - (2000 * 0.18 + 233.33)) < 0.01)
    ok("provisões são 19,4% do salário (8,3+2,8+8,3)",
       abs(c["provisoes"] - 388.0) < 0.01)
    ok("refeição é 22 dias a R$ 29,99", abs(c["refeicao"] - 659.78) < 0.01)
    ok("o total soma base, encargos, provisões e refeição",
       abs(c["total"] - (2000 + 593.33 + 388 + 659.78)) < 0.01)
    ok("a multa do FGTS NÃO entra no custo da pessoa",
       abs(c["total"] - 3641.11) < 0.01)
    ok("ligar o desconto do VT baixa o custo",
       custo(2000, {"descontar_vt": 1})["total"] < c["total"])

    ok("menos dias úteis, menos refeição",
       custo(2000, dias_uteis=20)["refeicao"] < c["refeicao"])
    ok("zero dias úteis não dá refeição",
       custo(2000, dias_uteis=0)["refeicao"] == 0.0)
    # Salario zero so aparece aqui, na funcao pura: `folha_clt` pula quem nao
    # tem salario no mes, entao ninguem sem salario chega a custar VT na tela.
    ok("com salário zero sobram os valores que não dependem dele",
       custo(0)["total"] == custo(0)["refeicao"] + 233.33)
    ok("salário ilegível não derruba", custo("abc")["base"] == 0.0)
    ok("taxa trocada muda a conta",
       abs(custo(2000, {"inss": 0.0})["encargos"] - (160 + 233.33)) < 0.01)
    ok("taxa que falta cai no padrão em vez de sumir",
       abs(custo(2000, {"fgts": 0.08})["encargos"] - (360 + 233.33)) < 0.01)

    # Monique nao e registrada: sobre o salario dela nao incide tributo nem
    # provisao. Refeicao e vale-transporte continuam — sao do dia de trabalho,
    # nao do contrato.
    sem_reg = custo(2000, registrado=False)
    ok("sem registro não há FGTS nem INSS",
       sem_reg["encargos"] == vale_transporte(2000))
    ok("sem registro não há provisão de férias nem 13º",
       sem_reg["provisoes"] == 0.0)
    ok("sem registro a refeição continua",
       sem_reg["refeicao"] == c["refeicao"])
    ok("sem registro o custo é salário + VT + refeição",
       abs(sem_reg["total"] - (2000 + 233.33 + 659.78)) < 0.01)
    ok("sem registro custa menos que com registro",
       sem_reg["total"] < c["total"])
    ok("«Não» em qualquer grafia marca quem não tem registro",
       not any(eh_registrado(v) for v in ("Não", "nao", "NÃO", "n", "0")))
    ok("célula vazia é tratada como registrado",
       eh_registrado("") and eh_registrado(None) and eh_registrado("Sim"))

    # Registrada em maio depois de trabalhar sem carteira desde janeiro
    virou = {"registrado": "Sim", "registrado_desde": "2026-05"}
    ok("antes do registro, não tinha registro",
       not registrado_no_mes(virou, 2026, 4))
    ok("no mês do registro, já tem", registrado_no_mes(virou, 2026, 5))
    ok("depois do registro, continua tendo",
       registrado_no_mes(virou, 2026, 12))
    ok("marcada como «Não», a data não a torna registrada",
       not registrado_no_mes({**virou, "registrado": "Não"}, 2026, 12))
    ok("«Sim» sem data vale para todos os meses, como era antes",
       registrado_no_mes({"registrado": "Sim"}, 2020, 1))

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
    ok("quem não é registrado não entra na reserva da multa",
       reserva_multa(pd.DataFrame([
           {"funcionario": "Monique", "salario_base": 2400,
            "admissao": "2024-01", "registrado": "Não"}]),
           2026, 9)["exposicao_total"] == 0.0)

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

    _mq = pd.DataFrame([{"funcionario": "Monique", "salario_base": 2400,
                         "admissao": "2026-01", "registrado": "Sim",
                         "registrado_desde": "2026-05"}])
    _abr = folha_clt(_mq, 2026, 4)[0]
    _mai = folha_clt(_mq, 2026, 5)[0]
    ok("em abril ela custa sem tributo", _abr["provisoes"] == 0.0)
    ok("em maio o tributo entra", _mai["provisoes"] > 0.0)
    ok("o salário e a refeição não mudam com o registro",
       _abr["base"] == _mai["base"] and _abr["refeicao"] == _mai["refeicao"])
    ok("registrar encarece a pessoa", _mai["total"] > _abr["total"])
    ok("a multa só passa a existir depois do registro",
       reserva_multa(_mq, 2026, 4)["exposicao_total"] == 0.0
       and reserva_multa(_mq, 2026, 9)["exposicao_total"] > 0.0)
    ok("a multa conta do REGISTRO, não da entrada na empresa",
       reserva_multa(_mq, 2026, 9)["exposicao_total"]
       == exposicao_multa(2400, "2026-05", 2026, 9))

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
    ok("o registro é gravado como Sim/Não",
       linhas_g[0]["registrado"] == "Sim"
       and _normalizar(pd.DataFrame([{"funcionario": "Monique",
                                      "registrado": "Não"}]))[0]["registrado"] == "Não")

    print("\nfalhas:", falhas)
