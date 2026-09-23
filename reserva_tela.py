"""reserva_tela.py — a tela da Reserva do Headcount.

O QUE ELA RESPONDE, EM UMA LINHA
---------------------------------
Até quando a verba aplicada paga o time, e quanto disso é rendimento.

E A PERGUNTA MAIOR, QUE É A RAZÃO DE ELA EXISTIR
-------------------------------------------------
O dono a formulou assim: *"consigo visualizar o avanço do faturamento e se
falta muito para conquistarmos o faturamento necessário para que quando o
dinheiro do aporte terminar o aumento de faturamento supra esse custo que o
aporte vinha suprindo"*.

São dois números lado a lado — o equilíbrio de hoje, sem o Headcount, e o
equilíbrio quando a reserva acabar, com ele dentro. A distância entre eles é
quanto o faturamento ainda precisa subir, e ela encolhe sozinha conforme o
negócio cresce.

A TELA NÃO CALCULA NADA
------------------------
Toda conta mora em `reserva.py` e em `custo_time.py`, que rodam sem Streamlit
e têm teste. Aqui só se desenha e se grava. Foi cálculo dentro de tela que
deixou a regra do bônus presa por meses dentro do `analise_metas.py`.
"""

from datetime import date, datetime, timedelta, timezone

import streamlit as st

import reserva as _rv

FUSO = timezone(timedelta(hours=-3))

ABA = "reserva"
COLUNAS = ["produto", "aplicado", "inicio", "bruto", "liquido", "posicao_em",
           "remuneracao", "atualizado_em", "atualizado_por"]


def _hoje():
    return datetime.now(FUSO).date()


@st.cache_data(ttl=300, show_spinner=False)
def carregar():
    """A última posição gravada. Cai na inicial quando não há nenhuma.

    Cacheada porque esta tela relê a cada clique e a posição muda uma vez por
    semana, no máximo. Gravar limpa o cache.
    """
    try:
        import sheets as _sh
        import gspread
        planilha = _sh.planilha()
        try:
            aba = planilha.worksheet(ABA)
        except gspread.exceptions.WorksheetNotFound:
            return dict(_rv.POSICAO_INICIAL), "inicial"
        linhas = aba.get_all_records()
    except Exception:
        # Planilha fora do ar não pode esconder a reserva: a posição inicial
        # é dado real, informado pelo dono, e serve para a tela abrir.
        return dict(_rv.POSICAO_INICIAL), "inicial"
    if not linhas:
        return dict(_rv.POSICAO_INICIAL), "inicial"
    ultima = linhas[-1]
    fora = dict(_rv.POSICAO_INICIAL)
    for c in ("produto", "inicio", "posicao_em", "remuneracao"):
        if str(ultima.get(c, "")).strip():
            fora[c] = str(ultima[c]).strip()
    for c in ("aplicado", "bruto", "liquido"):
        v = _num(ultima.get(c))
        if v:
            fora[c] = v
    return fora, "planilha"


def _num(v, padrao=0.0):
    if v is None or v == "":
        return padrao
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace("R$", "").replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return padrao


def salvar(pos, usuario=""):
    """Grava uma posição nova. Devolve (ok, mensagem).

    APPEND, e não substituição: o histórico de posições é o que permite
    conferir depois se o rendimento projetado bateu com o real. Uma linha por
    consulta ao banco é barato; perder a série é irreversível.
    """
    try:
        import sheets as _sh
        import gspread
        planilha = _sh.planilha()
        try:
            aba = planilha.worksheet(ABA)
        except gspread.exceptions.WorksheetNotFound:
            aba = planilha.add_worksheet(title=ABA, rows=500,
                                         cols=len(COLUNAS))
            aba.append_row(COLUNAS, value_input_option="RAW")
        cabecalho = aba.row_values(1) or list(COLUNAS)
        agora = datetime.now(FUSO).strftime("%d/%m/%Y %H:%M:%S")
        linha = {**pos, "atualizado_em": agora, "atualizado_por": usuario}
        aba.append_row([str(linha.get(str(c).strip().lower(), ""))
                        for c in cabecalho], value_input_option="RAW")
    except Exception as e:
        # Só o tipo: a mensagem do gspread carrega a URL da planilha.
        return False, type(e).__name__
    carregar.clear()
    return True, "posição gravada"


def _brl(v, casas=2):
    return ("R$ " + f"{float(v or 0):,.{casas}f}") \
        .replace(",", "X").replace(".", ",").replace("X", ".")


def _custo_do_headcount(usuario_logado):
    """(piso, teto, detalhe) do que a reserva precisa cobrir por mês.

    Sai de `custo_time`, que lê a grade de colaboradores. Quando a planilha
    não responde, devolve (0, 0, motivo) — e a tela pede o valor à mão em vez
    de inventar um número, que é o que faria a projeção mentir.
    """
    try:
        import ajustes as _aj
        import colaboradores as _co
        import custo_time as _ct
        import folha_salarial as _fs
        hoje = _hoje()
        ajustes = _aj.carregar()
        clt = _co.folha_clt(_co.carregar(), hoje.year, hoje.month,
                            _co.carregar_taxas(), ajustes)
        gestores = _fs.total_da_folha(_fs.carregar(), hoje.year, hoje.month,
                                      ajustes)
        h = _ct.headcount(clt)
        piso, teto = _ct.faixa_do_mes(clt)          # sem a gerência: a
        # reserva cobre o Headcount, e só ele. A Folha Gerência continua
        # saindo do caixa da operação.
        return piso, teto, {
            "pessoas": h["pessoas"], "salarios": h["salarios"],
            "contabilidade": h["contabilidade"],
            "teto_bonus": _ct.teto_do_bonus(clt), "gestores": gestores,
        }
    except Exception as e:
        return 0.0, 0.0, {"erro": f"{type(e).__name__}: {str(e)[:120]}"}


def _form_posicao(pos, usuario_logado):
    with st.expander("📋 Atualizar a posição do investimento", expanded=False):
        st.caption("Cole os números do extrato do banco. O Studio tira daí a "
                   "taxa que de fato rendeu — não precisa saber o CDI.")
        with st.form("form_reserva"):
            c1, c2 = st.columns(2)
            produto = c1.text_input("Produto", pos.get("produto", ""))
            remun = c2.text_input("Remuneração", pos.get("remuneracao", ""))
            c3, c4 = st.columns(2)
            aplicado = c3.number_input("Valor aplicado (R$)", min_value=0.0,
                                       value=float(pos.get("aplicado") or 0),
                                       step=1000.0, format="%.2f")
            inicio = c4.date_input(
                "Data da aplicação",
                value=_rv._data(pos.get("inicio")) or _hoje(),
                format="DD/MM/YYYY")
            c5, c6, c7 = st.columns(3)
            bruto = c5.number_input("Saldo bruto (R$)", min_value=0.0,
                                    value=float(pos.get("bruto") or 0),
                                    step=100.0, format="%.2f")
            liquido = c6.number_input("Saldo líquido (R$)", min_value=0.0,
                                      value=float(pos.get("liquido") or 0),
                                      step=100.0, format="%.2f")
            em = c7.date_input(
                "Posição em",
                value=_rv._data(pos.get("posicao_em")) or _hoje(),
                format="DD/MM/YYYY")
            if st.form_submit_button("💾 Gravar posição", type="primary"):
                if bruto < aplicado:
                    st.warning("O saldo bruto está abaixo do aplicado. "
                               "Confere: em renda fixa com liquidez isso não "
                               "costuma acontecer.")
                ok, msg = salvar({
                    "produto": produto, "remuneracao": remun,
                    "aplicado": aplicado, "inicio": inicio.isoformat(),
                    "bruto": bruto, "liquido": liquido,
                    "posicao_em": em.isoformat(),
                }, usuario_logado or "")
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()


def _cabecalho(pos, origem):
    bruto = _num(pos.get("bruto"))
    aplicado = _num(pos.get("aplicado"))
    liquido = _num(pos.get("liquido")) or _rv.liquido(
        aplicado, bruto, pos.get("inicio"), pos.get("posicao_em"))
    rend = bruto - aplicado

    c = st.columns(4)
    c[0].metric("Aplicado", _brl(aplicado, 0))
    c[1].metric("Saldo líquido hoje", _brl(liquido, 0),
                delta=_brl(liquido - aplicado, 0))
    taxa = _rv.taxa_implicita(aplicado, bruto, pos.get("inicio"),
                              pos.get("posicao_em"))
    if taxa:
        c[2].metric("Rendimento", f"{((1 + taxa) ** 30 - 1) * 100:.2f}% a.m.",
                    help="Tirado do próprio extrato: aplicado, saldo e as "
                         "duas datas. Não depende de cotação do CDI.")
    c[3].metric("Rendeu até agora", _brl(rend, 0))

    prox = _rv.proxima_faixa(pos.get("inicio"), _hoje())
    if prox:
        d, aliq, faltam = prox
        atual = _rv.aliquota_ir(
            (_hoje() - (_rv._data(pos.get("inicio")) or _hoje())).days)
        st.caption(
            f"📉 IR hoje: **{atual * 100:.1f}%** sobre o rendimento. Cai para "
            f"**{aliq * 100:.1f}%** em **{d.strftime('%d/%m/%Y')}** "
            f"(faltam {faltam} dias).")
    if origem == "inicial":
        st.caption("ℹ️ Posição informada no cadastro inicial — atualize com o "
                   "extrato do banco para o saldo do dia.")


def _projecao(pos, saque, extras, rotulo):
    linhas = _rv.projecao(
        _num(pos.get("aplicado")), _num(pos.get("bruto")), pos.get("inicio"),
        saque, dia_do_saque=_rv.DIA_DO_SAQUE_DA_FOLHA,
        de=pos.get("posicao_em"), meses=36, extras=extras)
    cobertos = [l for l in linhas if l["cobre"]]
    if not cobertos:
        st.error(f"{rotulo}: a reserva **não cobre nem o primeiro mês**.")
        return linhas
    ult = cobertos[-1]
    st.markdown(f"**{rotulo}** — cobre **{len(cobertos)} meses**, até "
                f"**{ult['mes']:02d}/{ult['ano']}**")
    return linhas


def _tabela(linhas):
    MES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set",
           "out", "nov", "dez")
    st.dataframe(
        [{"Mês": f"{MES[l['mes'] - 1]}/{l['ano']}",
          "Saldo no início": _brl(l["saldo_inicial"], 0),
          "Rendeu": _brl(l["rendimento"], 0),
          "Precisa": _brl(l["precisava"], 0),
          "Saca (bruto)": _brl(l["sacado_bruto"], 0),
          "IR": _brl(l["ir"], 0),
          "Cai na conta": _brl(l["recebido"], 0),
          "Sobra": _brl(l["saldo_final"], 0),
          "Cobre?": "sim" if l["cobre"] else "NÃO"} for l in linhas],
        use_container_width=True, hide_index=True)


def pagina(usuario_logado=None):
    import auth
    if not auth.eh_dono(usuario_logado):
        st.error("Esta tela é exclusiva do dono.")
        return

    st.markdown("### 🏦 Reserva do Headcount")
    st.caption(
        "A verba aplicada que paga o time enquanto o faturamento não dá conta. "
        "Ela **não** sai do ponto de equilíbrio: aporte é dinheiro entrando, "
        "não custo sumindo — se a folha saísse da conta, o painel diria que a "
        "operação se paga quando quem paga é a reserva."
    )

    pos, origem = carregar()
    _cabecalho(pos, origem)
    _form_posicao(pos, usuario_logado)
    st.markdown("---")

    piso, teto, det = _custo_do_headcount(usuario_logado)
    if det.get("erro"):
        st.warning("Não consegui ler a folha do Headcount — "
                   f"{det['erro']}. Informe o valor à mão abaixo.")
        piso = st.number_input("Custo mensal do Headcount (R$)",
                               min_value=0.0, value=0.0, step=500.0,
                               format="%.2f", key="rsv_saque_manual")
        teto = piso
    else:
        st.markdown(
            f"**O que a reserva cobre por mês:** {det['pessoas']} pessoa(s) · "
            f"salários e encargos {_brl(det['salarios'], 0)} · contabilidade "
            f"do quadro {_brl(det['contabilidade'], 0)}"
        )
        st.caption(
            f"A Folha Gerência ({_brl(det['gestores'], 0)}/mês) NÃO entra "
            "aqui — ela continua saindo do caixa da operação, e por isso "
            "continua no ponto de equilíbrio.")

    if piso <= 0:
        st.info("Sem custo de Headcount informado, não há o que projetar.")
        return

    st.markdown("---")
    st.markdown("#### Até quando a reserva cobre")
    st.caption(
        "Duas linhas, porque o bônus de meta ainda não fechou. O piso é "
        "ninguém bater meta; o teto é todo mundo bater tudo (30% do salário "
        "base, que é o máximo da regra). A diferença entre os dois é o risco "
        "que existe hoje sem ninguém ver."
    )
    linhas_piso = _projecao(pos, piso, None, "🟢 Piso — ninguém bate meta")
    if teto > piso:
        _projecao(pos, teto, None, "🔴 Teto — todo mundo bate tudo")

    with st.expander("📆 Mês a mês (piso)", expanded=False):
        st.caption(
            "Repare no saque bruto subindo: sacar R\\$ X do CDB **não** põe R\\$ X "
            "na conta, porque o IR come um pedaço do rendimento resgatado. O "
            "Studio calcula ao contrário — quanto sacar para SOBRAR o que "
            "precisa."
        )
        _tabela(linhas_piso)

    st.caption(
        f"Saque da folha no dia {_rv.DIA_DO_SAQUE_DA_FOLHA} (ou no último dia "
        f"útil anterior). O bônus é saque à parte, no "
        f"{_rv.DIA_UTIL_DO_SAQUE_DO_BONUS}º dia útil do mês seguinte, depois "
        "da apuração — juntar os dois adiantaria o bônus em um mês e faria a "
        "reserva parecer mais curta do que é."
    )


# ── Conferência ──────────────────────────────────────────────────────────────
# `python3 reserva_tela.py`. A conta mora em `reserva.py` e já tem teste; aqui
# se trava o que é desta tela: a posição que o dono informou, o contrato com o
# módulo, e as bordas de leitura de planilha.
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    _src = open(__file__, encoding="utf-8").read()
    _codigo = "\n".join(l for l in _src.split("\n")
                        if not l.lstrip().startswith("#")).split("if __name__")[0]

    # ── a posição, exatamente como o extrato do Itaú diz ─────────────────
    P = _rv.POSICAO_INICIAL
    ok("o valor aplicado é o do extrato", P["aplicado"] == 270_000.00)
    ok("o saldo bruto também", P["bruto"] == 273_642.89)
    ok("e o líquido", P["liquido"] == 272_823.24)
    ok("a data da aplicação é 14/08/2026", P["inicio"] == "2026-08-14")
    # O líquido do extrato tem de bater com a conta de IR do módulo. Se não
    # bater, ou o número foi copiado errado ou a tabela de IR está errada.
    ok("o líquido calculado bate com o do banco",
       _rv.liquido(P["aplicado"], P["bruto"], P["inicio"], P["posicao_em"])
       == P["liquido"])

    # ── a tela não calcula ───────────────────────────────────────────────
    ok("a tela não tem tabela de IR própria",
       "0.225" not in _codigo and "FAIXAS_IR = " not in _codigo)
    ok("nem faz a projeção por conta própria",
       "def projecao" not in _codigo and "_rv.projecao(" in _codigo)

    # ── leitura de número como a planilha devolve ────────────────────────
    ok("valor em texto brasileiro é lido", _num("273.642,89") == 273642.89)
    ok("com R$ e espaço também", _num("R$ 270.000,00") == 270000.0)
    ok("número já numérico passa igual", _num(12.5) == 12.5)
    ok("vazio vira zero e não quebra", _num("") == 0.0 and _num(None) == 0.0)
    ok("texto impossível vira zero", _num("abc") == 0.0)

    # ── a regra que não pode se perder ───────────────────────────────────
    ok("a gerência NÃO entra no que a reserva cobre",
       "faixa_do_mes(clt)" in _codigo and "gestores" not in
       _codigo.split("return piso, teto")[0].split("h = _ct.headcount")[1])
    ok("a porta está trancada na própria página", "auth.eh_dono" in _codigo)
    ok("os dois saques são separados",
       "DIA_DO_SAQUE_DA_FOLHA" in _codigo
       and "DIA_UTIL_DO_SAQUE_DO_BONUS" in _codigo)

    # ── o formato do dinheiro ────────────────────────────────────────────
    ok("o real sai com ponto de milhar e vírgula",
       _brl(272823.24) == "R$ 272.823,24")
    ok("e sem centavos quando pedido", _brl(272823.24, 0) == "R$ 272.823")

    print("\nfalhas:", falhas)
    raise SystemExit(falhas)
