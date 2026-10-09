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

import rotulos as _rot

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
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        _f = float(v)
        # `nan` E float: sem esta linha ele atravessa o isinstance
        # inteiro e vai parar na planilha, que recusa gravar — "Out of
        # range float values are not JSON compliant: nan". Foi assim
        # que a importacao de 604 cheques morreu depois de ler tudo.
        if _f != _f or _f in (float('inf'), float('-inf')):
            return padrao
        return _f
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


def linhas_do_aporte(ano, mes, colaboradores_df=None, taxas=None,
                     ajustes_df=None):
    """Só as pessoas cobertas pelo aporte, com o custo de cada uma no mês."""
    import colaboradores as _co
    df = _co.carregar() if colaboradores_df is None else colaboradores_df
    return [l for l in _co.folha_clt(df, ano, mes, taxas, ajustes_df)
            if l.get("no_aporte", True)]


def custo_do_mes(ano, mes, params=None, colaboradores_df=None, taxas=None,
                 ajustes_df=None):
    """O que o aporte paga naquele mês: o time coberto mais a contabilidade."""
    time = sum(l["total"] for l in linhas_do_aporte(ano, mes, colaboradores_df,
                                                    taxas, ajustes_df))
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

def registrar_saldo(movimentos, ano, mes, valor, observacao=""):
    """Põe (ou substitui) a leitura de saldo daquele mês.

    Substitui em vez de acrescentar: duas leituras do mesmo mês são correção de
    digitação, não dois saldos. Empilhá-las deixaria a conta dependendo de qual
    linha veio por último na planilha.
    """
    aj = _aj()
    alvo = aj.texto_mes((int(ano), int(mes)))
    d = pd.DataFrame(movimentos)
    if not d.empty:
        d = d[~((d.get("tipo", "").astype(str).str.strip() == "Saldo")
                & (d.get("data", "").astype(str).str.strip() == alvo))]
    nova = pd.DataFrame([{"tipo": "Saldo", "data": alvo,
                          "valor": round(_num(valor), 2),
                          "observacao": str(observacao or "").strip()}])
    return pd.concat([d, nova], ignore_index=True)


def _painel_contabilidade(params):
    with st.expander("🧾 Contabilidade — o acréscimo pelo quadro de funcionários",
                     expanded=True):
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


def _registrar_saldo_de_hoje(params, hoje, usuario_logado=None):
    """O saldo do mês em dois campos e um botão, sem editar a grade.

    Todo fim de mês ele abre o extrato e informa quanto sobrou. Fazer isso
    pela grade exige criar linha, escolher o tipo e digitar o mês — quatro
    passos para um número. Aqui é um.
    """
    aj = _aj()
    with st.expander("💰 Informar o saldo de hoje", expanded=True):
        st.caption(
            "Abra o extrato do investimento e informe quanto há na conta. "
            "Informar de novo no mesmo mês **substitui** a leitura anterior — "
            "dois saldos do mesmo mês seriam correção de digitação, não dois "
            "saldos.")
        c1, c2, c3, c4 = st.columns([1, 1, 2, 1])
        ano = c1.number_input("Ano", min_value=2020, max_value=2100,
                              value=hoje.year, step=1, key="hc_saldo_ano")
        mes = c2.number_input("Mês", min_value=1, max_value=12,
                              value=hoje.month, step=1, key="hc_saldo_mes")
        valor = c3.number_input("Saldo na conta (R$)", min_value=0.0,
                                step=0.01, format="%.2f", key="hc_saldo_valor")
        c4.markdown("&nbsp;", unsafe_allow_html=True)

        atual = carregar()
        _ja = [r for _, r in pd.DataFrame(atual).iterrows()
               if str(r.get("tipo", "")).strip() == "Saldo"
               and str(r.get("data", "")).strip() == aj.texto_mes((int(ano), int(mes)))]
        if _ja:
            st.caption(f"Já há um saldo de {int(mes):02d}/{int(ano)}: "
                       f"**{_brl(_num(_ja[0].get('valor')))}**. Registrar "
                       "de novo troca esse valor.")

        if c4.button("Registrar", key="btn_hc_saldo", type="primary"):
            if _num(valor) <= 0:
                st.error("Informe o saldo.")
            else:
                ok, msg = salvar(registrar_saldo(atual, ano, mes, valor),
                                 usuario_logado)
                if ok:
                    st.success(f"Saldo de {int(mes):02d}/{int(ano)} "
                               f"registrado: {_brl(_num(valor))}.")
                    st.rerun()
                else:
                    st.error(f"Não consegui gravar: {msg}")


# ── O mês do Balanço: salários e bônus ───────────────────────────────────────
#
# Pedido do dono em 05/10, com layout aprovado: o custo do time CLT no mês,
# cada imposto que ele paga, cada obrigação que reserva, e o bônus das metas
# em bloco SEPARADO — pago até o 5º dia útil do mês seguinte, com o que é
# tributo dele e o que é tributo do colaborador.

def quinto_dia_util(ano, mes):
    """O 5º dia útil do mês SEGUINTE a (ano, mes) — quando o bônus é pago.

    Sábado conta, como a CLT conta para o pagamento de salário; domingo e
    feriado não. Ponto facultativo (Carnaval) não é feriado e conta.
    """
    import calendar
    import placar_core as _pc
    a, m = (int(ano) + 1, 1) if int(mes) == 12 else (int(ano), int(mes) + 1)
    fer = {d for d, (_n, orig) in _pc.feriados_do_ano(a).items()
           if orig != "ponto facultativo"}
    n = 0
    for dia in range(1, calendar.monthrange(a, m)[1] + 1):
        d = date(a, m, dia)
        if d.weekday() == 6 or d in fer:
            continue
        n += 1
        if n == 5:
            return d
    return None


def salarios_do_mes(linhas_clt, taxas=None):
    """(linhas, totais) do bloco de salários, com cada imposto à parte.

    `linhas_clt` é `colaboradores.folha_clt` do mês — quem ainda não tinha
    entrado já não está nela, e o mês de admissão já vem proporcional. A multa
    do FGTS entra como obrigação a reservar (4% do salário de quem é
    registrado), que é como o layout aprovado mostra.
    """
    import colaboradores as _co
    t = {**_co.taxas_padrao(), **(taxas or {})}
    tx_multa = max(_num(t.get("multa_fgts")), 0.0)
    linhas = []
    for l in linhas_clt or []:
        multa = round(l["base"] * tx_multa, 2) if l.get("registrado") else 0.0
        linhas.append({
            "funcionario": l["funcionario"], "cargo": l.get("cargo", ""),
            "salario": l["base"], "fgts": l.get("p_fgts", 0.0),
            "inss_das": l.get("p_inss", 0.0),
            "ferias": l.get("p_ferias_1_12", 0.0),
            "terco": l.get("p_terco_ferias", 0.0),
            "decimo": l.get("p_decimo_1_12", 0.0), "multa": multa,
            "vt": l.get("p_vt", 0.0), "refeicao": l.get("refeicao", 0.0),
            # O custo de caixa do Studio (`total`) mais a multa reservada. O
            # INSS/CPP fica fora: ele já é pago dentro do DAS.
            "custo": round(l["total"] + multa, 2),
            "no_aporte": l.get("no_aporte", True),
        })
    soma = lambda c: round(sum(x[c] for x in linhas), 2)
    tot = {c: soma(c) for c in ("salario", "fgts", "inss_das", "ferias",
                                "terco", "decimo", "multa", "vt", "refeicao",
                                "custo")}
    tot["obrigacoes"] = round(tot["ferias"] + tot["terco"] + tot["decimo"]
                              + tot["multa"], 2)
    tot["impostos_pagos"] = round(tot["fgts"] + tot["inss_das"], 2)
    tot["da_reserva"] = round(sum(x["custo"] for x in linhas
                                  if x["no_aporte"]), 2)
    return linhas, tot


def _chave_nome(t):
    import unicodedata
    t = unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore")
    partes = t.decode().strip().lower().split()
    return partes[0] if partes else ""


def atingiu(ap):
    """O que a pessoa atingiu, em uma linha — e o critério que reprovou. Pura.

    Dono, 07/10: "precisa informar o que cada colaborador atingiu". O Gabriel
    aparecia com 18% (só o time) sem dizer por que a parte individual zerou.
    """
    ap = ap or {}
    time = ("Coletiva MAXX" if ap.get("maxx") else
            "Coletiva" if ap.get("col") else "Coletiva não")
    if ap.get("ind_maxx"):
        ind = "Individual MAXX"
    elif ap.get("ind"):
        falha = ap.get("reprovou_x") or []
        ind = "Individual" + (f" (MAXX não: {falha[0]})" if falha else "")
    else:
        falha = ap.get("reprovou_n") or []
        ind = "Individual não" + (f": {', '.join(falha)}" if falha else "")
    return f"{time} · {ind}"


def bonus_por_pessoa(linhas_clt, apurado, nomes, taxas=None, faixas=None):
    """(linhas, totais, sem_linha) do bônus das metas, com os tributos.

    `apurado` é `analise_metas.apuracao_bonus` — a mesma conta que o card do
    colaborador mostra. `nomes` é {username: nome} (`MEMBROS_ATIVOS`). A
    pessoa da meta é achada na grade de colaboradores pelo primeiro nome.

    O bônus incide sobre o SALÁRIO BASE de contrato (no mês de admissão, o
    cheio, não o proporcional). Paga os tributos de lei como salário, que é a
    regra dada pelo dono em 05/10:
      do dono    FGTS, reflexo em férias + 1/3 e em 13º, multa do FGTS
                 (o INSS/CPP vai dentro do DAS: aparece, não soma)
      do colab.  INSS e IRRF, pela `tabela_tributos` — sem ela, None.
    """
    import colaboradores as _co
    import tabela_tributos as _tt
    t = {**_co.taxas_padrao(), **(taxas or {})}
    fx = faixas or {"inss": [], "irrf": [], "isento_ate": 0.0}
    por_nome = {_chave_nome(l["funcionario"]): l for l in linhas_clt or []}
    linhas, sem_linha = [], []
    for u, ap in (apurado or {}).items():
        nome = (nomes or {}).get(u, u)
        l = por_nome.get(_chave_nome(nome))
        if l is None:
            if ap.get("pct_time") or ap.get("pct_seu"):
                sem_linha.append(nome)
            continue
        prop = l.get("proporcional") or 1.0
        base = round(l["base"] / prop, 2) if prop > 0 else l["base"]
        b_time = round(base * ap.get("pct_time", 0.0) / 100.0, 2)
        b_ind = round(base * ap.get("pct_seu", 0.0) / 100.0, 2)
        bruto = round(b_time + b_ind, 2)
        reg = bool(l.get("registrado"))
        tx = lambda k: max(_num(t.get(k)), 0.0) if reg else 0.0
        fgts = round(bruto * tx("fgts"), 2)
        ref_f = round(bruto * (tx("ferias_1_12") + tx("terco_ferias")), 2)
        ref_d = round(bruto * tx("decimo_1_12"), 2)
        multa = round(bruto * tx("multa_fgts"), 2)
        das = round(bruto * tx("inss"), 2)
        i_emp, ir = (_tt.do_bonus(base, bruto, fx) if (reg and bruto > 0)
                     else ((0.0, 0.0) if bruto <= 0 or not reg else (None, None)))
        liq = (round(bruto - i_emp - ir, 2)
               if (i_emp is not None and ir is not None) else None)
        linhas.append({
            "funcionario": l["funcionario"], "user": u,
            "pct_time": ap.get("pct_time", 0.0), "pct_seu": ap.get("pct_seu", 0.0),
            "bonus_time": b_time, "bonus_ind": b_ind, "bruto": bruto,
            "inss_emp": i_emp, "irrf": ir, "liquido": liq,
            "fgts": fgts, "ref_ferias": ref_f, "ref_decimo": ref_d,
            "multa": multa, "inss_das": das,
            "custo": round(bruto + fgts + ref_f + ref_d + multa, 2),
            "no_aporte": l.get("no_aporte", True),
            "atingiu": atingiu(ap),
        })
    soma = lambda c: round(sum(x[c] for x in linhas), 2)
    tot = {c: soma(c) for c in ("bonus_time", "bonus_ind", "bruto", "fgts",
                                "ref_ferias", "ref_decimo", "multa",
                                "inss_das", "custo")}
    _ok_tab = all(x["inss_emp"] is not None and x["irrf"] is not None
                  for x in linhas)
    tot["inss_emp"] = (round(sum(x["inss_emp"] for x in linhas), 2)
                       if _ok_tab else None)
    tot["irrf"] = round(sum(x["irrf"] for x in linhas), 2) if _ok_tab else None
    tot["tributos_meus"] = round(tot["fgts"] + tot["ref_ferias"]
                                 + tot["ref_decimo"] + tot["multa"], 2)
    _ret = [x for x in linhas if x["bruto"] > 0]
    tot["tributos_deles"] = (
        round(sum(x["inss_emp"] + x["irrf"] for x in _ret), 2)
        if all(x["inss_emp"] is not None and x["irrf"] is not None
               for x in _ret) else None)
    tot["liquido"] = (round(tot["bruto"] - tot["tributos_deles"], 2)
                      if tot["tributos_deles"] is not None else None)
    tot["da_reserva"] = round(sum(x["custo"] for x in linhas
                                  if x["no_aporte"]), 2)
    return linhas, tot, sem_linha


@st.cache_data(ttl=300, show_spinner=False)
def _apurado_do_mes(ano, mes):
    """(apurado, nomes, situacao, erro) das metas de (ano, mes).

    Cacheado: é a leitura do Trello e do relógio de ponto, e esta tela roda a
    cada clique. O board já tem cache próprio; aqui se guarda a apuração.
    """
    try:
        import analise_metas as _am
        import placar_core as _pc
        board = _pc._buscar_board()
        if not board or not board[0]:
            return {}, {}, {}, "o Trello não respondeu"
        dados = _am._analisar_meses(*board, [(int(ano), int(mes))],
                                    _pc._processar)
        nomes = dict(_pc.MEMBROS_ATIVOS)
        ap = _am.apuracao_bonus(dados, list(nomes))
        sit = next(iter(ap.values()), {}).get("sit_pen", {}) if ap else {}
        enxuto = {u: {**{k: v for k, v in a.items()
                         if k in ("col", "maxx", "ind", "ind_maxx",
                                  "pct_time", "pct_seu")},
                      # o critério que reprovou, para a tela dizer POR QUE
                      # a parte individual não pagou (dono, 07/10: Gabriel)
                      "reprovou_n": [r for r, ok in (a.get("crit_n") or [])
                                     if ok is False],
                      "reprovou_x": [r for r, ok in (a.get("crit_x") or [])
                                     if ok is False]}
                  for u, a in ap.items()}
        return (enxuto, nomes,
                {"bateu_col": bool(sit.get("bateu_col")),
                 "bateu_maxx": bool(sit.get("bateu_maxx"))}, "")
    except Exception as e:
        return {}, {}, {}, f"{type(e).__name__}: {str(e)[:120]}"


def _meses_para_escolher(hoje):
    """Os últimos 12 meses, do atual para trás. O atual é o padrão."""
    a, m, fora = hoje.year, hoje.month, []
    for _ in range(12):
        fora.append((a, m))
        a, m = (a - 1, 12) if m == 1 else (a, m - 1)
    return fora


_MESES_PT = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
             "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


def _rot_mes(am):
    return f"{_MESES_PT[am[1] - 1]}/{am[0]}"


def _v(x, casas=2):
    """Número da tabela: '—' quando a conta não existe (tabela não cadastrada)."""
    if x is None:
        return "—"
    return f"{float(x):,.{casas}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def _tabela_html(cab, linhas, total=None, grupo=(), esquerda=1):
    """Tabela sem quebra de linha (o markdown do Streamlit fecharia o HTML)."""
    th = "".join(
        f'<th style="text-align:{"left" if i < esquerda else "center"};padding:6px 8px;'
        f'border-bottom:1px solid var(--ms-borda);color:'
        f'{"#7FB8F0" if c in grupo else "var(--ms-texto-sec)"};font-weight:600;">'
        f'{c}</th>' for i, c in enumerate(cab))
    def tr(cel, forte=False):
        return "<tr>" + "".join(
            f'<td style="text-align:{"left" if i < esquerda else "center"};padding:6px 8px;'
            f'{"font-weight:800;" if forte or i == len(cel) - 1 else ""}'
            f'border-bottom:1px solid rgba(128,128,128,.25);">{c}</td>'
            for i, c in enumerate(cel)) + "</tr>"
    corpo = "".join(tr(c) for c in linhas) + (tr(total, True) if total else "")
    return ('<div style="overflow-x:auto;"><table style="width:100%;'
            'border-collapse:collapse;font-size:13px;color:var(--ms-texto);">'
            f'<tr>{th}</tr>{corpo}</table></div>')


def _cartao(rotulo, valor, sub, cor=None):
    c = cor or "var(--ms-texto)"
    borda = cor or "var(--ms-borda)"
    return (f'<div style="background:var(--ms-metric-bg);border:1px solid {borda};'
            f'border-radius:10px;padding:12px 14px;">'
            f'<div style="font-size:12px;color:var(--ms-texto-sec);font-weight:600;">{rotulo}</div>'
            f'<div style="font-size:22px;font-weight:800;color:{c};margin:3px 0;">{valor}</div>'
            f'<div style="font-size:11px;color:var(--ms-texto-sec);">{sub}</div></div>')


def _grade(cartoes, n):
    return (f'<div style="display:grid;grid-template-columns:repeat({n},minmax(0,1fr));'
            f'gap:10px;margin:6px 0 12px;">' + "".join(cartoes) + '</div>')


def _cadastro_tabela(usuario_logado):
    """A tabela do INSS e do IRRF do empregado — uma vez por ano."""
    import tabela_tributos as _tt
    df, erro = _tt.carregar()
    with st.expander("🧾 Tabela do INSS e do IRRF do empregado"
                     + ("" if not df.empty else " — não cadastrada"),
                     expanded=False):
        if erro:
            st.warning(f"Não consegui ler a tabela ({erro}). Nada foi apagado; "
                       "tente de novo antes de salvar.")
            return
        st.caption(
            "Uma linha por faixa, da tabela oficial do ano. **INSS**: até "
            "quanto vale a faixa e a alíquota (7,5 = 7,5%). **IRRF**: até "
            "quanto, alíquota e dedução; a última faixa fica com o “até” "
            "vazio. **IRRF_ISENTO_ATE**: quem ganha até este valor não paga "
            "IR (preencha só o “até”).")
        base = df if not df.empty else pd.DataFrame(
            [{"tributo": "INSS", "ate": 0.0, "aliquota": 0.0, "deducao": 0.0}])
        with st.form("form_tab_trib"):
            ed = st.data_editor(
                base[["tributo", "ate", "aliquota", "deducao"]],
                num_rows="dynamic", use_container_width=True, hide_index=True,
                key="ed_tab_trib",
                column_config={
                    "tributo": st.column_config.SelectboxColumn(
                        "Tributo", options=_tt.TRIBUTOS, required=True),
                    "ate": st.column_config.NumberColumn("Até (R$)", format="R$ %.2f"),
                    "aliquota": st.column_config.NumberColumn("Alíquota (%)",
                                                              format="%.2f"),
                    "deducao": st.column_config.NumberColumn("Dedução (R$)",
                                                             format="R$ %.2f"),
                })
            if st.form_submit_button("💾 Salvar tabela", type="primary"):
                okk, msg = _tt.salvar(ed, usuario_logado)
                (st.success if okk else st.error)(msg)
                if okk:
                    st.rerun()


def pagina(usuario_logado=None):
    import auth
    import colaboradores as _co
    import tabela_tributos as _tt
    aj = _aj()
    hoje = datetime.now(FUSO).date()

    st.markdown("### 🧮 Balanço headcount")

    # SEMPRE ABRE NO MÊS ATUAL. O seletor é para olhar trás; quem entrou
    # depois não aparece nos meses anteriores (`folha_clt` corta antes da
    # admissão), e o histórico não fica poluído.
    _meses = _meses_para_escolher(hoje)
    am = st.selectbox("Mês", _meses, index=0, format_func=_rot_mes,
                      key="hc_mes_ref")
    ano, mes = am

    taxas = _co.carregar_taxas()
    ajustes = aj.carregar()
    _df_co = _co.carregar()
    if _df_co.empty:
        st.warning("A grade de **Colaboradores** está vazia — o quadro que "
                   "aparece lá é sugestão e só conta depois de **Salvar "
                   "colaboradores** (Custos fixos › Folha salarial).")
    clt = _co.folha_clt(_df_co, ano, mes, taxas, ajustes)
    sal, ts = salarios_do_mes(clt, taxas)

    apurado, nomes, sit, erro_b = _apurado_do_mes(ano, mes)
    _tab, _erro_tab = _tt.carregar()
    fx = _tt.faixas(_tab)
    bon, tb, sem_linha = bonus_por_pessoa(clt, apurado, nomes, taxas, fx)
    pg = quinto_dia_util(ano, mes)
    pg_txt = pg.strftime("%d/%m/%Y") if pg else "—"
    _corrente = (ano, mes) == (hoje.year, hoje.month)

    st.markdown(_grade([
        _cartao("Salários do mês", _brl(ts["salario"]),
                f"{len(sal)} colaborador(es) CLT"),
        _cartao("Impostos e obrigações dos salários",
                _brl(round(ts["custo"] - ts["salario"], 2)),
                "FGTS, VT, férias, 1/3, 13º, multa"),
        _cartao(f"Bônus a pagar · até {pg_txt[:5]}", _brl(tb["bruto"]),
                "previsão pelo placar de hoje" if _corrente else
                "bruto, metas do mês", "#7FB8F0"),
        _cartao("Tributos sobre o bônus (meus)", _brl(tb["tributos_meus"]),
                "FGTS + reflexos + multa", "#7FB8F0"),
        _cartao("Sai da Reserva", _brl(ts["da_reserva"] + tb["da_reserva"]),
                f"salários {_brl(ts['da_reserva'])} + bônus "
                f"{_brl(tb['da_reserva'])}", "#E0A13A"),
    ], 5), unsafe_allow_html=True)

    # ── SALÁRIOS ─────────────────────────────────────────────────────────
    st.markdown(f"#### 💼 Salários · {_rot_mes(am)}")
    if not sal:
        st.info("Nenhum colaborador com salário neste mês.")
    else:
        _ref = ts["refeicao"] > 0
        cab = (["Colaborador", "Cargo", "Salário", "FGTS", "INSS/CPP", "Férias",
                "1/3", "13º", "Multa FGTS", "VT"] + (["Refeição"] if _ref else [])
               + ["Custo"])
        lin = [[x["funcionario"], x["cargo"]] + [_v(x[c]) for c in
               ("salario", "fgts", "inss_das", "ferias", "terco", "decimo",
                "multa", "vt")] + ([_v(x["refeicao"])] if _ref else [])
               + [_v(x["custo"])] for x in sal]
        tot = (["Total", ""] + [_v(ts[c]) for c in
               ("salario", "fgts", "inss_das", "ferias", "terco", "decimo",
                "multa", "vt")] + ([_v(ts["refeicao"])] if _ref else [])
               + [_v(ts["custo"])])
        st.markdown(_tabela_html(cab, lin, tot, grupo=("FGTS", "INSS/CPP"),
                                 esquerda=2),
                    unsafe_allow_html=True)
        _fora = [x["funcionario"] for x in sal if not x["no_aporte"]]
        if _fora:
            st.caption("Fora do aporte (não sai da Reserva): **"
                       + ", ".join(_fora) + "**.")

    # ── BÔNUS ────────────────────────────────────────────────────────────
    # Dono, 07/10: "deixe somente Bonus Setembro/2026" — sem o "pagar até"
    # e sem as explicações no meio da tela.
    st.markdown(f"#### 🎯 Bônus {_rot_mes(am)}")
    if erro_b:
        st.warning(f"Não consegui apurar as metas: {erro_b}. O bônus fica "
                   "fora até a leitura voltar.")
    if bon:
        cab = ["Colaborador", "Atingiu", "Bônus time", "Bônus indiv.", "Bônus bruto",
               "INSS deles", "IRRF deles", "Líquido a depositar", "FGTS 8%",
               "Reflexo férias+1/3", "Reflexo 13º", "Multa FGTS",
               "INSS/CPP (DAS)", "Custo p/ mim"]
        lin = [[x["funcionario"], x.get("atingiu", "")] + [_v(x[c]) for c in
               ("bonus_time", "bonus_ind", "bruto", "inss_emp", "irrf",
                "liquido", "fgts", "ref_ferias", "ref_decimo", "multa",
                "inss_das", "custo")] for x in bon]
        tot = ["Total", ""] + [_v(tb.get(c)) for c in
               ("bonus_time", "bonus_ind", "bruto")] + [
               _v(tb["inss_emp"]), _v(tb["irrf"]), _v(tb["liquido"])] + [_v(tb[c]) for c in
               ("fgts", "ref_ferias", "ref_decimo", "multa", "inss_das",
                "custo")]
        st.markdown(_tabela_html(cab, lin, tot,
                                 grupo=("FGTS 8%", "Reflexo férias+1/3",
                                        "Reflexo 13º", "Multa FGTS",
                                        "INSS/CPP (DAS)"), esquerda=2),
                    unsafe_allow_html=True)
    st.markdown(_grade([
        _cartao("Bônus bruto", _brl(tb["bruto"]), "o que cada um ganhou"),
        _cartao("Tributos deles (retidos)",
                _brl(tb["tributos_deles"]) if tb["tributos_deles"] is not None
                else "—", "INSS do empregado + IRRF · você desconta e recolhe"),
        _cartao("Tributos meus", _brl(tb["tributos_meus"]),
                f"FGTS {_brl(tb['fgts'])} + reflexos "
                f"{_brl(tb['ref_ferias'] + tb['ref_decimo'])} + multa "
                f"{_brl(tb['multa'])}"),
        _cartao("Custo total do bônus", _brl(tb["custo"]), "sai da Reserva",
                "#E0A13A"),
    ], 4), unsafe_allow_html=True)
    if sem_linha:
        st.warning("Bateu meta e não está na grade de colaboradores (o bônus "
                   "dela não entrou na conta): **" + ", ".join(sem_linha)
                   + "**.")
    _cadastro_tabela(usuario_logado)

    # ── RESERVA ──────────────────────────────────────────────────────────
    # A Reserva mora aqui desde 05/10 (pedido do dono), e "Aportes e
    # saldos" mora dentro dela.
    st.markdown("---")
    if not auth.eh_dono(usuario_logado):
        st.info("A Reserva é exclusiva do dono.")
        return
    import reserva_tela as _rt
    _rt.conteudo(usuario_logado)

    st.markdown("#### Aportes e saldos")
    params = _painel_contabilidade(carregar_params())
    _registrar_saldo_de_hoje(params, hoje, usuario_logado)
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

    # Editor e botao no MESMO formulario. Com o botao solto, o clique que sai
    # da celula ainda em edicao fecha a celula E dispara o rerun: o rerun come
    # o clique, o botao nao roda, e a tela nao diz nada. Foi assim que a meta
    # de gastos de setembro nao foi gravada em 17/09.
    with st.form("form_headcount"):
        editado = st.data_editor(
            df[["tipo", "data", "valor", "observacao"]],
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key="ed_headcount",
            column_config={**_rot.config(["tipo", "data", "quantidade", "observacao"], st), 
                "tipo": st.column_config.SelectboxColumn(
                    "Tipo", options=TIPOS, required=True, width="small"),
                "data": st.column_config.TextColumn(
                    "Mês", width="small", help="AAAA-MM."),
                "valor": st.column_config.NumberColumn(
                    "Valor (R$)", min_value=0.0, step=0.01, format="R$ %.2f"),
                "observacao": st.column_config.TextColumn("Observação", width="large"),
            },
        )
        enviou = st.form_submit_button("💾 Salvar movimentos",
                                       type="primary")

    if enviou:
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
        st.info("Sem nenhum **Aporte** lançado não há balanço: é do primeiro "
                "aporte que sai a conta de quanto já foi consumido e de "
                "quanto rendeu.")
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

    # Registrar o saldo do mes: substitui, nao empilha
    _m = pd.DataFrame([{"tipo": "Aporte", "data": "2026-06", "valor": 120000},
                       {"tipo": "Saldo", "data": "2026-09", "valor": 110000}])
    _r1 = registrar_saldo(_m, 2026, 10, 99000)
    ok("saldo de um mes novo e acrescentado", len(_r1) == 3)
    ok("e o resumo passa a usar o mais recente",
       resumo(_r1, p, quadro, tx, hoje=date(2026, 10, 15))["saldo"] == 99000.0)
    _r2 = registrar_saldo(_m, 2026, 9, 108000)
    ok("saldo do mesmo mes SUBSTITUI em vez de empilhar", len(_r2) == 2)
    ok("e vale o valor novo",
       resumo(_r2, p, quadro, tx, hoje=date(2026, 9, 15))["saldo"] == 108000.0)
    ok("o aporte nao e tocado ao registrar saldo",
       resumo(_r2, p, quadro, tx, hoje=date(2026, 9, 15))["aportado"] == 120000.0)
    ok("registrar saldo numa tabela vazia cria a primeira linha",
       len(registrar_saldo(pd.DataFrame(), 2026, 9, 1000)) == 1)

    # So quem esta no aporte entra na conta
    _lin = linhas_do_aporte(2026, 9, quadro, tx)
    ok("a lista do aporte traz so quem esta coberto",
       [l["funcionario"] for l in _lin] == ["Beatriz"])
    ok("a Monique fica de fora por nao estar no aporte",
       "Monique" not in {l["funcionario"] for l in _lin})

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


    # ── O BALANÇO DO MÊS (layout aprovado em 05/10) ──────────────────────
    # A ENTRADA VEM DO SISTEMA: o quadro é o de `colaboradores.SUGESTOES`
    # passado por `folha_clt` de verdade, e a apuração é a de
    # `analise_metas.apuracao_bonus` — não números escritos aqui.
    import colaboradores as _co_t
    _pad = {"cargo": _co_t.CARGO_PADRAO, "registrado": "Sim",
            "salario_base": _co_t.SALARIO_PADRAO, "admissao": "2026-01",
            "dias_uteis": 22, "no_aporte": "Sim"}
    _q = pd.DataFrame([{**_pad, **p} for p in _co_t.SUGESTOES])
    _clt = _co_t.folha_clt(_q, 2026, 10)
    _sal, _ts = salarios_do_mes(_clt)
    _gab = [x for x in _sal if x["funcionario"] == "Gabriel"][0]
    ok("FGTS do Gabriel = 8% de 3.000", _gab["fgts"] == 240.0)
    ok("férias, 1/3 e 13º à parte", (_gab["ferias"], _gab["terco"],
                                     _gab["decimo"]) == (249.0, 84.0, 249.0))
    ok("multa do FGTS reservada = 4%", _gab["multa"] == 120.0)
    ok("custo = caixa do Studio + multa (sem o INSS do DAS)",
       _gab["custo"] == round(3000 + 240 + 233.33 + 249 + 84 + 249 + 120, 2))
    ok("os salários do mês somam o quadro sem a Monique",
       _ts["salario"] == round(3000 + 4 * 2006.58, 2)
       and "Monique" not in {x["funcionario"] for x in _sal})
    ok("obrigações = férias + 1/3 + 13º + multa",
       _ts["obrigacoes"] == round(_ts["ferias"] + _ts["terco"] + _ts["decimo"]
                                  + _ts["multa"], 2))
    ok("quem entra depois não aparece no mês anterior",
       not salarios_do_mes(_co_t.folha_clt(pd.DataFrame([{**_pad,
           "funcionario": "Novo", "admissao": "2026-11-03"}]), 2026, 10))[0])

    import analise_metas as _am_t
    import placar_core as _pc_t
    _cfg = {"meta_gab": 1000, "meta_bea": 1000, "meta_lui": 1000}
    _dados = [{"cfg": _cfg, "pts_membro": {"gab": 1000, "bea": 900,
                                           "lui": 500},
               "saldo": 10000.0, "meta_eq": 10000.0,
               "meta_maxx": 12000.0, "pen_qtd": 0}]
    _nomes = {"gab": "Gabriel Borges", "bea": "Beatriz", "lui": "Luiz",
              "xxx": "Fulano"}
    _ap = _am_t.apuracao_bonus(_dados, ["gab", "bea", "lui"])
    _bon, _tb, _sem = bonus_por_pessoa(_clt, _ap, _nomes)
    _bg = [x for x in _bon if x["funcionario"] == "Gabriel"][0]
    ok("o bônus sai da apuração única: 12% do time + 8% individual",
       _bg["bonus_time"] == 360.0 and _bg["bonus_ind"] == 240.0)
    ok("abaixo de 80% da própria meta: nada do time",
       [x for x in _bon if x["funcionario"] == "Luiz"][0]["bruto"] == 0.0)
    ok("o nome da meta acha a pessoa pelo primeiro nome",
       _bg["user"] == "gab")
    ok("tributos meus sobre o bônus: FGTS, reflexos e multa",
       (_bg["fgts"], _bg["ref_ferias"], _bg["ref_decimo"], _bg["multa"])
       == (48.0, 66.6, 49.8, 24.0))
    ok("custo do bônus = bruto + tributos meus (o DAS não soma)",
       _bg["custo"] == 788.4 and _bg["inss_das"] == 22.88)
    ok("sem tabela, o desconto do colaborador fica em aberto",
       _bg["inss_emp"] is None and _tb["tributos_deles"] is None
       and _tb["liquido"] is None)
    import tabela_tributos as _tt_t
    _fx = _tt_t.faixas(pd.DataFrame([
        {"tributo": "INSS", "ate": 10000, "aliquota": 10},
        {"tributo": "IRRF", "ate": "", "aliquota": 0, "deducao": 0}]))
    _bg2 = [x for x in bonus_por_pessoa(_clt, _ap, _nomes, None, _fx)[0]
            if x["funcionario"] == "Gabriel"][0]
    ok("com tabela, o líquido é o bruto menos o desconto deles",
       _bg2["inss_emp"] == 60.0 and _bg2["liquido"] == 540.0)
    ok("bônus de quem não está na grade é avisado, não some",
       bonus_por_pessoa(_clt, {"xxx": {"pct_time": 12.0, "pct_seu": 0.0}},
                        _nomes)[2] == ["Fulano"])
    ok("o bônus de outubro é pago até 07/11 (sábado conta, Finados não)",
       quinto_dia_util(2026, 10) == date(2026, 11, 7))
    ok("e o de dezembro, em janeiro do ano seguinte",
       quinto_dia_util(2026, 12).year == 2027)
    ok("o mês do Balanço abre no atual",
       _meses_para_escolher(date(2026, 10, 5))[0] == (2026, 10))
    import inspect as _insp_t
    _pg = _insp_t.getsource(pagina)
    ok("a Reserva mora dentro do Balanço, e os aportes dentro dela",
       _pg.index("_rt.conteudo(") < _pg.index("Aportes e saldos")
       < _pg.index("form_headcount"))
    ok("o bônus da tela vem da apuração única",
       "_apurado_do_mes(" in _pg
       and "apuracao_bonus(" in _insp_t.getsource(_apurado_do_mes))
    ok("nenhum bloco da tela tem quebra de linha",
       "\n" not in _tabela_html(["a", "b"], [["1", "2"]], ["t", "3"])
       and "\n" not in _grade([_cartao("x", "1", "s")], 1))
    # ── 07/10: o que cada um atingiu, e a tela sem explicações no meio ──
    ok("atingiu diz o time e o critério individual que reprovou (Gabriel)",
       atingiu({"maxx": True, "ind": False, "reprovou_n": ["horas trabalhadas"]})
       == "Coletiva MAXX · Individual não: horas trabalhadas")
    ok("atingiu com as duas MAXX",
       atingiu({"maxx": True, "ind": True, "ind_maxx": True})
       == "Coletiva MAXX · Individual MAXX")
    ok("atingiu sem nada", atingiu({}) == "Coletiva não · Individual não")
    _l_g = [{"funcionario": "Gabriel", "base": 3000.0, "registrado": True}]
    _b_g = bonus_por_pessoa(_l_g, {"gabriel": {"maxx": True, "pct_time": 18,
                                              "pct_seu": 0, "reprovou_n":
                                              ["tempo médio"]}},
                            {"gabriel": "Gabriel"})[0]
    ok("a linha do bônus leva o que a pessoa atingiu",
       _b_g[0]["atingiu"] == "Coletiva MAXX · Individual não: tempo médio"
       and _b_g[0]["bonus_time"] == 540.0)
    import inspect as _insp_h
    _src_pg = _insp_h.getsource(pagina)
    ok("a tela não tem mais os textos explicativos nem o 'pagar até' no título",
       "Impostos que eu pago" not in _src_pg and "Coletiva mensal: **" not in _src_pg
       and "tabela do ano**, que" not in _src_pg
       and 'f"#### 🎯 Bônus {_rot_mes(am)}"' in _src_pg
       and '"Atingiu"' in _src_pg)
    ok("os números das tabelas ficam centralizados",
       '"left" if i < esquerda else "center"' in _insp_h.getsource(_tabela_html))

    print("\nfalhas:", falhas)

    # O CODIGO DE SAIDA. Sem ele, quem le `returncode` ve este modulo como
    # aprovado SEMPRE — e o `conferir.py` e o `checar_mutacao.py` leem
    # exatamente isso. Auto-teste sem codigo de saida nao e rede: e decoracao.
    __import__("sys").exit(1 if falhas else 0)
