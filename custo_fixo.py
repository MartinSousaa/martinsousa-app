"""custo_fixo.py — O custo que existe com ou sem venda.

POR QUE ESTE NÚMERO VEM PRIMEIRO
--------------------------------
Ele é o numerador da única conta que decide se o mês fecha no azul:

    faturamento de equilíbrio  =  custo fixo  ÷  margem de contribuição

A margem já está medida em 17.793 vendas (`financeiro_equilibrio.py`). O custo
fixo, não: ele morava numa foto da aba CUSTOS FIXOS do Controle_MS, sem coluna
de mês e portanto sem histórico. Enquanto ele for uma foto, a linha de
equilíbrio é uma estimativa com data de validade.

UMA TABELA, NÃO UM FORMULÁRIO POR ITEM
--------------------------------------
São dezessete itens. Um formulário por item seria dezessete aberturas, dezessete
salvamentos e dezessete chances de esquecer um. A tela é uma grade: digita tudo,
salva uma vez.

O QUE ELE AINDA NÃO FAZ
-----------------------
Não guarda histórico por mês — é a foto do custo vigente, como a planilha. Fazer
histórico é decisão a tomar depois de o número estar certo; inverter a ordem
produziria histórico de um número ainda errado.
"""

from datetime import datetime, timezone, timedelta

import pandas as pd
import streamlit as st

ABA_NOME = "custo_fixo"

# A ordem aqui é a ordem das colunas na planilha e na tela.
COLUNAS = ["item", "modalidade", "valor_mensal", "dia_debito",
           "forma_pagamento", "atualizado_em", "atualizado_por"]

# Operacional é o custo de OPERAR; não operacional é o que sai do caixa sem ser
# custo de operar — as parcelas de PRONAMP são o caso desta base. A separação
# não é enfeite: ela muda a linha de equilíbrio em R$ 52 mil, e por isso o
# painel mostra as duas linhas em vez de escolher uma.
MODALIDADES = ["Operacional", "Não operacional"]

FORMAS = ["PIX", "Boleto", "Cartão", "Transferência"]

# Sugestão de partida quando a aba está vazia. Não é gravada sozinha: aparece na
# grade para ser preenchida e só vira linha na planilha quando ele salvar.
# Gravar por conta própria criaria dado que ninguém digitou — e dado que ninguém
# digitou é dado em que ninguém confia.
ITENS_SUGERIDOS = ["Água", "Luz", "Internet fixa", "Internet móvel",
                   "Contabilidade"]

FUSO = timezone(timedelta(hours=-3))


def _aba():
    """A aba deste ambiente, criada na primeira vez.

    Sem `cache_resource`: o objeto guarda a aba encontrada, e uma aba criada
    depois do cache ficaria invisível até o container reiniciar. A abertura da
    planilha em si já é cacheada em sheets.py, que é onde está o custo.
    """
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
    # Coluna nova no código entra no fim da planilha, nunca no meio: linha
    # gravada por posição iria para o campo errado a partir dali.
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


def _num(v, padrao=0.0):
    """Número a partir do que o usuário digitou. 1.234,56 e 1234.56 valem."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return padrao
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace("R$", "").replace(" ", "")
    if not t:
        return padrao
    if "," in t:                      # 1.234,56 -> 1234.56
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return padrao


@st.cache_data(ttl=600, show_spinner=False)
def carregar():
    """DataFrame do custo fixo. Vazio quando a aba não existe ou falha."""
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
    df["valor_mensal"] = df["valor_mensal"].map(_num)
    df["dia_debito"] = df["dia_debito"].map(lambda v: int(_num(v, 0)))
    return df[COLUNAS]


def salvar(df, usuario=""):
    """Regrava a aba inteira. Devolve (ok, mensagem).

    Regravar tudo, e não linha a linha: a tabela tem dezenas de linhas, não
    milhares, e atualização parcial é onde nascem os casos de linha apagada por
    índice deslocado. Uma escrita só também deixa a aba sempre consistente.

    A ordem das colunas sai do CABEÇALHO REAL da planilha, nunca de `COLUNAS`:
    se alguém reordenar as colunas na mão, a gravação por posição levaria cada
    valor para o campo do vizinho.
    """
    linhas = _normalizar(df, usuario)
    try:
        aba = _aba()
        cabecalho = aba.row_values(1) or list(COLUNAS)
        corpo = [[l.get(str(c).strip().lower(), "") for c in cabecalho]
                 for l in linhas]
        aba.clear()
        aba.update("A1", [cabecalho] + corpo, value_input_option="RAW")
    except Exception as e:
        # Só o tipo: a mensagem de erro do gspread carrega a URL da planilha e
        # pedaços da credencial, e isto vai para a tela.
        return False, type(e).__name__
    carregar.clear()
    return True, f"{len(linhas)} itens gravados"


def _normalizar(df, usuario=""):
    """Linhas prontas para a planilha. Descarta linha sem nome de item.

    Linha em branco é o resto de quem clicou em "+" e desistiu — gravá-la
    encheria a aba de vazios que depois entram na soma como zero e ninguém
    entende de onde vieram.
    """
    agora = datetime.now(FUSO).strftime("%Y-%m-%d %H:%M")
    saida = []
    for _, r in pd.DataFrame(df).iterrows():
        item = str(r.get("item", "") or "").strip()
        if not item:
            continue
        modalidade = str(r.get("modalidade", "") or "").strip()
        forma = str(r.get("forma_pagamento", "") or "").strip()
        dia = int(_num(r.get("dia_debito"), 0))
        saida.append({
            "item": item,
            "modalidade": modalidade if modalidade in MODALIDADES else MODALIDADES[0],
            "valor_mensal": round(_num(r.get("valor_mensal")), 2),
            "dia_debito": min(max(dia, 0), 31),
            "forma_pagamento": forma if forma in FORMAS else "",
            "atualizado_em": agora,
            "atualizado_por": str(usuario or "")[:60],
        })
    return saida


def totais(df):
    """{'operacional': x, 'nao_operacional': y, 'total': x+y}."""
    d = pd.DataFrame(df)
    if d.empty or "valor_mensal" not in d:
        return {"operacional": 0.0, "nao_operacional": 0.0, "total": 0.0}
    v = d["valor_mensal"].map(_num)
    op = str(MODALIDADES[0])
    eh_op = d.get("modalidade", pd.Series([""] * len(d))).astype(str).str.strip() == op
    a, b = float(v[eh_op].sum()), float(v[~eh_op].sum())
    return {"operacional": a, "nao_operacional": b, "total": a + b}


def _brl(v):
    return "R$ " + f"{float(v):,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")


# ── Tela ─────────────────────────────────────────────────────────────────────

def pagina(usuario_logado=None):
    st.markdown("#### 🧱 Custo fixo")
    st.caption(
        "O que sai todo mês independente de vender. É o numerador da linha de "
        "equilíbrio — **faturamento de equilíbrio = custo fixo ÷ margem de "
        "contribuição**. Digite tudo e salve uma vez."
    )

    df = carregar()
    if df.empty:
        df = pd.DataFrame([{"item": i, "modalidade": MODALIDADES[0],
                            "valor_mensal": 0.0, "dia_debito": 0,
                            "forma_pagamento": "", "atualizado_em": "",
                            "atualizado_por": ""}
                           for i in ITENS_SUGERIDOS])
        st.info("Aba ainda vazia. Estes itens são só uma sugestão de partida — "
                "nada foi gravado até você salvar.")

    editado = st.data_editor(
        df[["item", "modalidade", "valor_mensal", "dia_debito", "forma_pagamento"]],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="ed_custo_fixo",
        column_config={
            "item": st.column_config.TextColumn(
                "Item", required=True, width="medium",
                help="Água, Luz, Internet fixa, Aluguel, Salário…"),
            "modalidade": st.column_config.SelectboxColumn(
                "Modalidade", options=MODALIDADES, width="medium",
                help="Operacional é custo de operar. Não operacional sai do "
                     "caixa sem ser custo de operar — parcela de empréstimo, "
                     "por exemplo."),
            "valor_mensal": st.column_config.NumberColumn(
                "Valor mensal (R$)", min_value=0.0, step=10.0, format="%.2f",
                width="small"),
            "dia_debito": st.column_config.NumberColumn(
                "Dia do débito", min_value=0, max_value=31, step=1, format="%d",
                width="small", help="0 quando não há dia fixo."),
            "forma_pagamento": st.column_config.SelectboxColumn(
                "Forma de pagamento", options=FORMAS, width="medium",
                help="Célula em cinza claro é campo ainda não preenchido, "
                     "não um valor gravado."),
        },
    )

    t = totais(editado)
    c1, c2, c3 = st.columns(3)
    c1.metric("Operacional", _brl(t["operacional"]))
    c2.metric("Não operacional", _brl(t["nao_operacional"]))
    c3.metric("Total do mês", _brl(t["total"]))

    if st.button("💾 Salvar", type="primary"):
        ok, msg = salvar(editado, usuario_logado)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(f"Não consegui gravar: {msg}")

    _quando = [str(x) for x in df.get("atualizado_em", []) if str(x).strip()]
    if _quando:
        st.caption(f"Última gravação: {max(_quando)}")


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    ok("450 vira 450.0", _num("450") == 450.0)
    ok("1.234,56 do teclado brasileiro vira 1234.56", _num("1.234,56") == 1234.56)
    ok("R$ 2.033,00 vira 2033.0", _num("R$ 2.033,00") == 2033.0)
    ok("vazio vira zero", _num("") == 0.0)
    ok("texto ilegível vira zero", _num("abc") == 0.0)
    ok("None vira zero", _num(None) == 0.0)
    ok("número já numérico passa direto", _num(70) == 70.0)

    linhas = _normalizar(pd.DataFrame([
        {"item": "Luz", "modalidade": "Operacional", "valor_mensal": "450",
         "dia_debito": 25, "forma_pagamento": "PIX"},
        {"item": "  ", "modalidade": "Operacional", "valor_mensal": 999,
         "dia_debito": 1, "forma_pagamento": "PIX"},
        {"item": "PRONAMP 1", "modalidade": "Não operacional",
         "valor_mensal": "4.980,00", "dia_debito": 99, "forma_pagamento": "Boleto"},
        {"item": "Bling", "modalidade": "inventada", "valor_mensal": 400,
         "dia_debito": 10, "forma_pagamento": "Cheque"},
    ]), "martinsousa")
    ok("linha sem item não é gravada", len(linhas) == 3)
    ok("valor com vírgula chega certo na planilha",
       linhas[1]["valor_mensal"] == 4980.0)
    ok("dia fora do calendário é aparado", linhas[1]["dia_debito"] == 31)
    ok("modalidade inventada cai em Operacional",
       linhas[2]["modalidade"] == "Operacional")
    ok("forma de pagamento fora da lista fica vazia",
       linhas[2]["forma_pagamento"] == "")
    ok("quem salvou fica registrado", linhas[0]["atualizado_por"] == "martinsousa")

    t = totais(pd.DataFrame(linhas))
    ok("operacional soma só o operacional", t["operacional"] == 850.0)
    ok("não operacional soma só o não operacional", t["nao_operacional"] == 4980.0)
    ok("o total é a soma dos dois", t["total"] == 5830.0)
    ok("tabela vazia não derruba o total", totais(pd.DataFrame())["total"] == 0.0)

    ok("real sai no formato brasileiro", _brl(29838) == "R$ 29.838,00")
    ok("centavos aparecem", _brl(1234.5) == "R$ 1.234,50")

    print("\nfalhas:", falhas)
