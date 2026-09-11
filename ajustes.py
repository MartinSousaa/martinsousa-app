"""ajustes.py — Quando cada valor mudou, para o custo de cada mês ficar certo.

O PROBLEMA QUE ELE RESOLVE
--------------------------
Um salário reajustado em maio não pode reescrever janeiro. Sem histórico, o
custo fixo tem um valor só — o de hoje — e ele é aplicado para trás, inventando
um custo que não existiu. Todo indicador que olhe para o passado (margem do mês,
ponto de equilíbrio de abril, quanto o custo pesou no faturamento) sai errado, e
sai errado de um jeito que parece certo.

COMO O VALOR DE UM MÊS É DECIDIDO
---------------------------------
Cada item da grade tem um valor INICIAL e o mês em que passou a existir. Cada
ajuste diz: a partir de tal mês, este item passa a valer tanto.

    valor em M  =  o último ajuste com vigência ≤ M
                   ou, se não houver nenhum, o valor inicial
                   ou zero, se M for anterior ao mês em que o item passou a existir

Por isso a coluna da grade se chama **Valor inicial** e não "Valor mensal":
quem manda no valor de hoje é o último ajuste. A tela mostra o valor vigente
calculado ao lado, para a diferença ficar visível em vez de virar uma dúvida.

POR QUE MÊS E NÃO DIA
---------------------
O custo fixo é mensal. Um reajuste no dia 10 não cobra dez trinta avos do valor
velho e vinte do novo — a conta do mês é uma só. Guardar o dia daria uma
precisão que a conta não usa, e convidaria a uma proporcionalização que ninguém
pediu.
"""

from datetime import date, datetime, timezone, timedelta

import pandas as pd
import streamlit as st

ABA_NOME = "ajustes"

COLUNAS = ["grade", "item", "valor_novo", "vigente_desde", "observacao",
           "atualizado_em", "atualizado_por"]

# As grades que um ajuste pode alcançar, com o campo que ele muda em cada uma.
# O rótulo é o que aparece na tela; a chave é o que vai para a planilha.
GRADES_ALVO = {
    "custo_fixo": "Custo fixo",
    "folha_salarial": "Folha salarial",
    "nao_operacional": "Não operacional",
}

FUSO = timezone(timedelta(hours=-3))


# ── Contas ───────────────────────────────────────────────────────────────────

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


def mes_de(v):
    """(ano, mes) de '2026-05', '05/2026', '2026-05-13' ou uma data. None se não der.

    Aceita as quatro formas porque as quatro aparecem: o que ele digita, o que
    a planilha devolve e o que o Streamlit entrega num campo de data.
    """
    if isinstance(v, (datetime, date)):
        return (v.year, v.month)
    t = str(v or "").strip()
    if not t:
        return None
    for f in ("%Y-%m", "%m/%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            d = datetime.strptime(t[:len("0000-00-00")] if f.count("-") == 2
                                  or f.count("/") == 2 else t[:7], f)
            return (d.year, d.month)
        except ValueError:
            continue
    return None


def texto_mes(am):
    return f"{am[0]:04d}-{am[1]:02d}" if am else ""


def valor_no_mes(valor_inicial, desde_inicial, ajustes_do_item, ano, mes):
    """Quanto este item valia em (ano, mes).

    `ajustes_do_item` é uma lista de dicts com `valor_novo` e `vigente_desde`.
    Ajuste sem mês legível é ignorado: aplicá-lo "desde sempre" reescreveria o
    passado inteiro, que é exatamente o erro que esta função existe para evitar.
    """
    alvo = (int(ano), int(mes))
    inicio = mes_de(desde_inicial)
    if inicio and alvo < inicio:
        return 0.0
    valor = _num(valor_inicial)
    melhor = None
    for a in (ajustes_do_item or []):
        m = mes_de(a.get("vigente_desde"))
        if not m or m > alvo:
            continue
        # Empate no mesmo mês: vale o último da lista, que é o mais recente na
        # planilha. Dois ajustes no mesmo mês é correção de digitação, e a
        # correção é a de baixo.
        if melhor is None or m >= melhor:
            melhor, valor = m, _num(a.get("valor_novo"))
    return valor


def por_item(df):
    """{(grade, item): [ajustes]} — os ajustes agrupados, prontos para a conta."""
    fora = {}
    d = pd.DataFrame(df)
    if d.empty:
        return fora
    for _, r in d.iterrows():
        item = str(r.get("item", "") or "").strip()
        if not item:
            continue
        chave = (str(r.get("grade", "") or "").strip(), item)
        fora.setdefault(chave, []).append({
            "valor_novo": r.get("valor_novo"),
            "vigente_desde": r.get("vigente_desde"),
        })
    return fora


def aplicar(linhas_grade, ajustes_df, grade, ano, mes,
            campo_valor="valor_mensal", campo_desde="vigente_desde",
            campo_item="item"):
    """Soma da grade naquele mês, já com os ajustes aplicados."""
    mapa = por_item(ajustes_df)
    d = pd.DataFrame(linhas_grade)
    if d.empty:
        return 0.0
    total = 0.0
    for _, r in d.iterrows():
        item = str(r.get(campo_item, "") or "").strip()
        if not item:
            continue
        total += valor_no_mes(r.get(campo_valor), r.get(campo_desde),
                              mapa.get((grade, item)), ano, mes)
    return float(total)


# ── Planilha ─────────────────────────────────────────────────────────────────

def _aba():
    import gspread
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        aba = planilha.worksheet(ABA_NOME)
    except gspread.exceptions.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA_NOME, rows=500,
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
    """Linhas prontas para a planilha, em ordem de vigência.

    Descarta ajuste sem item ou sem mês de vigência. Ajuste sem vigência não é
    ajuste: ou ele vale desde sempre e reescreve o passado, ou não vale nunca —
    e nenhuma das duas é o que quem digitou quis dizer.
    """
    agora = datetime.now(FUSO).strftime("%Y-%m-%d %H:%M")
    saida = []
    for _, r in pd.DataFrame(df).iterrows():
        item = str(r.get("item", "") or "").strip()
        m = mes_de(r.get("vigente_desde"))
        if not item or not m:
            continue
        grade = str(r.get("grade", "") or "").strip()
        saida.append({
            "grade": grade if grade in GRADES_ALVO else "custo_fixo",
            "item": item,
            "valor_novo": round(_num(r.get("valor_novo")), 2),
            "vigente_desde": texto_mes(m),
            "observacao": str(r.get("observacao", "") or "").strip()[:200],
            "atualizado_em": agora,
            "atualizado_por": str(usuario or "")[:60],
        })
    saida.sort(key=lambda l: (l["grade"], l["item"], l["vigente_desde"]))
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
    return True, f"{len(linhas)} ajustes gravados"


def _brl(v):
    return "R$ " + f"{float(v):,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")


# ── Tela ─────────────────────────────────────────────────────────────────────

def _itens_cadastrados():
    """Os itens que existem nas grades, para a lista não ser digitada à mão.

    Item digitado à mão erra um acento e o ajuste passa a valer para um item
    que não existe — silenciosamente, porque ninguém confere o que não
    apareceu.
    """
    fora = []
    try:
        import custo_fixo as _cf
        for grade, cfg in _cf.GRADES.items():
            d = _cf.carregar(cfg["aba"])
            for it in d.get("item", []):
                if str(it).strip():
                    fora.append(f"{GRADES_ALVO[grade]} › {str(it).strip()}")
    except Exception:
        pass
    try:
        import nao_operacional as _no
        for it in _no.carregar().get("programa", []):
            if str(it).strip():
                fora.append(f"{GRADES_ALVO['nao_operacional']} › {str(it).strip()}")
    except Exception:
        pass
    return sorted(set(fora))


def pagina(usuario_logado=None):
    st.markdown("#### 📈 Ajuste de valor")
    st.caption(
        "Quando um valor mudou. Um salário reajustado em maio **não** reescreve "
        "janeiro: o ajuste vale do mês informado em diante, e os meses "
        "anteriores continuam com o valor que tinham."
    )

    df = carregar()
    if df.empty:
        df = pd.DataFrame(columns=COLUNAS)
        st.info("Nenhum ajuste registrado. Enquanto não houver, cada item vale "
                "o valor inicial da grade em todos os meses.")

    opcoes = _itens_cadastrados()
    if not opcoes:
        st.warning("Nenhum item cadastrado ainda nas grades. Preencha o Custo "
                   "fixo, a Folha salarial ou o Não operacional primeiro — o "
                   "ajuste escolhe o item de lá, e não da digitação.")
        return

    # Na tela, grade e item andam juntos num rótulo só: escolher dois campos
    # separados deixa escolher combinação que não existe.
    visao = df.copy()
    visao["alvo"] = [
        f"{GRADES_ALVO.get(str(g).strip(), 'Custo fixo')} › {str(i).strip()}"
        for g, i in zip(visao.get("grade", []), visao.get("item", []))
    ] if not visao.empty else []

    editado = st.data_editor(
        visao[["alvo", "valor_novo", "vigente_desde", "observacao"]]
        if not visao.empty else
        pd.DataFrame(columns=["alvo", "valor_novo", "vigente_desde", "observacao"]),
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="ed_ajustes",
        column_config={
            "alvo": st.column_config.SelectboxColumn(
                "O que muda", options=opcoes, required=True, width="large",
                help="A lista vem do que já está cadastrado nas grades."),
            "valor_novo": st.column_config.NumberColumn(
                "Novo valor (R$)", min_value=0.0, step=0.01, format="%.2f"),
            "vigente_desde": st.column_config.TextColumn(
                "Vigente desde", width="small",
                help="AAAA-MM. O mês em que o novo valor passou a valer."),
            "observacao": st.column_config.TextColumn(
                "Motivo", width="large",
                help="Dissídio, promoção, renegociação… ajuda a lembrar em "
                     "dezembro por que mudou em maio."),
        },
    )

    if st.button("💾 Salvar", type="primary", key="btn_salvar_ajustes"):
        ok, msg = salvar(_desmontar(editado), usuario_logado)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(f"Não consegui gravar: {msg}")


def _desmontar(editado):
    """Desfaz o rótulo «Grade › Item» nas duas colunas que vão para a planilha."""
    rotulo_para_chave = {v: k for k, v in GRADES_ALVO.items()}
    fora = []
    for _, r in pd.DataFrame(editado).iterrows():
        alvo = str(r.get("alvo", "") or "")
        if "›" not in alvo:
            continue
        rotulo, item = [p.strip() for p in alvo.split("›", 1)]
        fora.append({
            "grade": rotulo_para_chave.get(rotulo, "custo_fixo"),
            "item": item,
            "valor_novo": r.get("valor_novo"),
            "vigente_desde": r.get("vigente_desde"),
            "observacao": r.get("observacao"),
        })
    return pd.DataFrame(fora, columns=["grade", "item", "valor_novo",
                                       "vigente_desde", "observacao"])


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    ok("2026-05 é lido", mes_de("2026-05") == (2026, 5))
    ok("05/2026 é lido", mes_de("05/2026") == (2026, 5))
    ok("2026-05-13 vira o mês", mes_de("2026-05-13") == (2026, 5))
    ok("13/05/2026 vira o mês", mes_de("13/05/2026") == (2026, 5))
    ok("uma data do Streamlit vira o mês", mes_de(date(2026, 5, 13)) == (2026, 5))
    ok("vazio não é mês", mes_de("") is None)
    ok("texto qualquer não é mês", mes_de("maio") is None)

    # O caso do enunciado: salário de 2.033 reajustado para 2.400 em maio/2026
    aj = [{"valor_novo": 2400, "vigente_desde": "2026-05"}]
    ok("janeiro continua com o valor antigo",
       valor_no_mes(2033, "2026-01", aj, 2026, 1) == 2033.0)
    ok("abril ainda é o valor antigo",
       valor_no_mes(2033, "2026-01", aj, 2026, 4) == 2033.0)
    ok("maio já é o novo", valor_no_mes(2033, "2026-01", aj, 2026, 5) == 2400.0)
    ok("dezembro segue no novo",
       valor_no_mes(2033, "2026-01", aj, 2026, 12) == 2400.0)

    dois = [{"valor_novo": 2400, "vigente_desde": "2026-05"},
            {"valor_novo": 2600, "vigente_desde": "2026-09"}]
    ok("com dois ajustes, junho pega o de maio",
       valor_no_mes(2033, "2026-01", dois, 2026, 6) == 2400.0)
    ok("com dois ajustes, outubro pega o de setembro",
       valor_no_mes(2033, "2026-01", dois, 2026, 10) == 2600.0)
    ok("a ordem em que foram digitados não muda o resultado",
       valor_no_mes(2033, "2026-01", list(reversed(dois)), 2026, 10) == 2600.0)

    ok("antes de o item existir, ele vale zero",
       valor_no_mes(2033, "2026-03", aj, 2026, 2) == 0.0)
    ok("no mês em que passou a existir, já vale",
       valor_no_mes(2033, "2026-03", aj, 2026, 3) == 2033.0)
    ok("sem mês de início, vale em qualquer mês",
       valor_no_mes(2033, "", aj, 2020, 1) == 2033.0)
    ok("sem ajuste nenhum, vale o inicial",
       valor_no_mes(2033, "2026-01", [], 2026, 12) == 2033.0)
    ok("ajuste sem vigência é ignorado em vez de reescrever o passado",
       valor_no_mes(2033, "2026-01", [{"valor_novo": 9999,
                                       "vigente_desde": ""}], 2026, 12) == 2033.0)
    ok("dois ajustes no mesmo mês: vale o último digitado",
       valor_no_mes(100, "2026-01",
                    [{"valor_novo": 200, "vigente_desde": "2026-05"},
                     {"valor_novo": 300, "vigente_desde": "2026-05"}],
                    2026, 6) == 300.0)

    # Soma da grade inteira
    grade = pd.DataFrame([
        {"item": "Luz", "valor_mensal": 450, "vigente_desde": "2026-01"},
        {"item": "Salário Beatriz", "valor_mensal": 2033, "vigente_desde": "2026-01"},
        {"item": "Sala Bolhas", "valor_mensal": 350, "vigente_desde": "2026-07"},
    ])
    ajs = pd.DataFrame([
        {"grade": "custo_fixo", "item": "Salário Beatriz",
         "valor_novo": 2400, "vigente_desde": "2026-05"},
    ])
    ok("em janeiro a sala ainda não existe e o salário é o antigo",
       aplicar(grade, ajs, "custo_fixo", 2026, 1) == 450 + 2033)
    ok("em junho o salário já subiu e a sala ainda não existe",
       aplicar(grade, ajs, "custo_fixo", 2026, 6) == 450 + 2400)
    ok("em julho entra a sala", aplicar(grade, ajs, "custo_fixo", 2026, 7)
       == 450 + 2400 + 350)
    ok("ajuste de outra grade não vaza para esta",
       aplicar(grade, pd.DataFrame([{"grade": "folha_salarial",
                                     "item": "Salário Beatriz",
                                     "valor_novo": 9999,
                                     "vigente_desde": "2026-01"}]),
               "custo_fixo", 2026, 6) == 450 + 2033 + 0)
    ok("grade vazia dá zero", aplicar(pd.DataFrame(), ajs, "custo_fixo", 2026, 6) == 0.0)

    linhas = _normalizar(pd.DataFrame([
        {"grade": "custo_fixo", "item": "Luz", "valor_novo": "1.234,56",
         "vigente_desde": "05/2026", "observacao": "bandeira vermelha"},
        {"grade": "custo_fixo", "item": "", "valor_novo": 10,
         "vigente_desde": "2026-05"},
        {"grade": "custo_fixo", "item": "Água", "valor_novo": 10,
         "vigente_desde": ""},
        {"grade": "inventada", "item": "X", "valor_novo": 10,
         "vigente_desde": "2026-05"},
    ]), "martinsousa")
    ok("ajuste sem item não é gravado e ajuste sem vigência também não",
       len(linhas) == 2)
    # Por item, e não por posição: `_normalizar` ordena a saída, e um teste
    # preso ao índice quebra quando a ordenação muda sem nada mais mudar.
    porn = {l["item"]: l for l in linhas}
    ok("valor com vírgula chega certo", porn["Luz"]["valor_novo"] == 1234.56)
    ok("a vigência é gravada sempre como AAAA-MM",
       porn["Luz"]["vigente_desde"] == "2026-05")
    ok("grade inventada cai no custo fixo", porn["X"]["grade"] == "custo_fixo")
    ok("a saída sai ordenada por grade, item e vigência",
       linhas == sorted(linhas, key=lambda l: (l["grade"], l["item"],
                                               l["vigente_desde"])))

    d = _desmontar(pd.DataFrame([{"alvo": "Folha salarial › Salário Beatriz",
                                  "valor_novo": 2400,
                                  "vigente_desde": "2026-05",
                                  "observacao": ""},
                                 {"alvo": "", "valor_novo": 1}]))
    ok("o rótulo da tela vira grade e item", len(d) == 1
       and d.iloc[0]["grade"] == "folha_salarial"
       and d.iloc[0]["item"] == "Salário Beatriz")

    print("\nfalhas:", falhas)
