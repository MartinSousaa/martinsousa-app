import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import date

import planilha as _plan
import rotulos as _rot
# Nome vindo do ambiente: producao usa o padrao, homologacao usa a copia.
PLANILHA_NOME = _plan.nome()
ABA_NOME = "financeiro"

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
          "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

REGIMES_TRIBUTARIOS = ["Simples Nacional", "Lucro Presumido", "Lucro Real", "MEI"]

COLUNAS = ["ano", "mes", "lpv", "regime_tributario", "aliquota"]


def _crono(rotulo, seg, detalhe=""):
    """Registra quanto custou uma ida a planilha. Nunca derruba a leitura."""
    try:
        import cronometro
        cronometro.marcar(rotulo, seg, detalhe)
    except Exception:
        pass


def parse_numero_br(texto):
    """Converte texto colado (com virgula ou ponto decimal, com ou sem
    separador de milhar) em float. Retorna None se vazio/invalido."""
    if texto is None:
        return None
    texto = str(texto).strip().replace("R$", "").replace(" ", "")
    if not texto:
        return None
    if "," in texto and "." in texto:
        # assume ponto = milhar, virgula = decimal (padrao BR: 1.234,56)
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def formatar_br(valor, casas=2):
    """Formata numero pro padrao brasileiro (1.234.567,89), com separador
    de milhar de verdade."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    txt = f"{valor:,.{casas}f}"
    return txt.replace(",", "X").replace(".", ",").replace("X", ".")


# ── CONEXAO COM A PLANILHA ──────────────────────────────────────────────────

# Reutiliza a conexao entre reruns. Sem isso cada chamada refazia
# from_service_account_info + gspread.authorize + open() + worksheet() —
# quatro idas a rede antes de ler o primeiro dado, por modulo, a cada rerun.
def _cliente():
    """Cliente gspread compartilhado (ver sheets.py).

    Era um bloco proprio de credencial + authorize, identico em nove
    modulos: nove trocas de token por processo, todas no cold start.
    """
    import sheets as _sh
    return _sh.cliente()

@st.cache_resource
def _aba():
    # A planilha e aberta uma vez por processo em sheets.py. Aqui cada
    # modulo abria a sua, e abrir por nome custa uma varredura do Drive.
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        return planilha.worksheet(ABA_NOME)
    except gspread.exceptions.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA_NOME, rows=500, cols=len(COLUNAS))
        aba.append_row(COLUNAS, value_input_option="RAW")
        return aba


@st.cache_data(ttl=600)
def carregar_dados():
    """Le todos os dados da planilha. Cache de 60s pra nao bater na API
    do Google toda hora que a tela recarrega."""
    aba = _aba()
    import time as _t_crono
    _t0_crono = _t_crono.perf_counter()
    registros = aba.get_all_records(value_render_option="UNFORMATTED_VALUE")
    _crono("Planilha: financeiro", _t_crono.perf_counter() - _t0_crono,
           f"{len(registros)} linhas")
    df = pd.DataFrame(registros)
    if df.empty:
        df = pd.DataFrame(columns=COLUNAS)
        return df
    df.columns = [str(c).strip().lower() for c in df.columns]
    for col in ["ano", "mes", "lpv", "aliquota"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def salvar_ano(ano, regime, aliquota, lpv_meses):
    """Grava (atualiza ou cria) as 12 linhas de um ano na planilha.
    lpv_meses: lista de 12 valores (mes 1 a 12), cada um o LPV informado
    manualmente (ou None se nao preenchido)."""
    aba = _aba()
    valores_existentes = aba.get_all_values()

    if not valores_existentes:
        aba.append_row(COLUNAS, value_input_option="RAW")
        valores_existentes = [COLUNAS]

    linhas_existentes = valores_existentes[1:] if len(valores_existentes) > 1 else []
    mapa_linha = {}
    for i, linha in enumerate(linhas_existentes):
        if len(linha) >= 2 and linha[0] and linha[1]:
            try:
                chave = (int(float(linha[0])), int(float(linha[1])))
                mapa_linha[chave] = i + 2
            except ValueError:
                pass

    for mes_num, lpv_valor in enumerate(lpv_meses, start=1):
        linha_valores = [
            ano, mes_num,
            lpv_valor if lpv_valor else "",
            regime or "",
            aliquota if aliquota else "",
        ]
        chave = (ano, mes_num)
        if chave in mapa_linha:
            num_linha = mapa_linha[chave]
            aba.update(f"A{num_linha}:E{num_linha}", [linha_valores], value_input_option="RAW")
        else:
            aba.append_row(linha_valores, value_input_option="RAW")

    carregar_dados.clear()


# ── CALCULOS ─────────────────────────────────────────────────────────────────

def lpv_vigente(df, hoje=None):
    """LPV do mes mais recente ja preenchido (olhando pra tras a partir do
    mes/ano atual). O site nao calcula mais o LPV -- so usa o que o
    usuario informou manualmente."""
    hoje = hoje or date.today()
    if df.empty or "lpv" not in df.columns:
        return None, "nenhum LPV informado ainda"

    candidatos = df.dropna(subset=["lpv"])
    candidatos = candidatos[candidatos["lpv"] > 0]
    if candidatos.empty:
        return None, "nenhum LPV informado ainda"

    # so considera meses ja fechados (ano, mes) <= (hoje.ano, hoje.mes)
    candidatos = candidatos[
        (candidatos["ano"] < hoje.year) |
        ((candidatos["ano"] == hoje.year) & (candidatos["mes"] <= hoje.month))
    ]
    if candidatos.empty:
        return None, "nenhum LPV informado ainda pra este periodo"

    linha = candidatos.sort_values(["ano", "mes"], ascending=False).iloc[0]
    origem = f"{MESES[int(linha['mes'])-1]}/{int(linha['ano'])}"
    return float(linha["lpv"]), origem


def meses_de_atraso_lpv(df, hoje=None):
    """Quantos meses fechados existem depois do último LPV informado.

    O LPV alimenta toda decisão de viabilidade. Se ninguém preenche há dois
    meses, o Studio continua aprovando e reprovando produto com custo velho — e
    não dizia nada em lugar nenhum. Zero quando está em dia ou não há LPV.
    """
    hoje = hoje or date.today()
    if df is None or df.empty or "lpv" not in df.columns:
        return 0
    validos = df.dropna(subset=["lpv"])
    validos = validos[validos["lpv"] > 0]
    validos = validos[
        (validos["ano"] < hoje.year) |
        ((validos["ano"] == hoje.year) & (validos["mes"] <= hoje.month))
    ]
    if validos.empty:
        return 0
    linha = validos.sort_values(["ano", "mes"], ascending=False).iloc[0]
    return max((hoje.year - int(linha["ano"])) * 12 + hoje.month - int(linha["mes"]), 0)


def aliquota_vigente(df, ano=None):
    """Aliquota do ano informado; se nao tiver (ou for um valor absurdo,
    fora de 0-100), usa a mais recente disponivel que seja valida."""
    ano = ano or date.today().year

    def valida(v):
        return pd.notna(v) and v and 0 < v <= 100

    linha = df[df["ano"] == ano] if not df.empty else pd.DataFrame()
    # Pega a linha mais recente do ano com alíquota válida (não necessariamente janeiro)
    if not linha.empty:
        com_aliquota_ano = linha[linha["aliquota"].apply(valida)] if "aliquota" in linha.columns else pd.DataFrame()
        if not com_aliquota_ano.empty:
            melhor = com_aliquota_ano.sort_values("mes", ascending=False).iloc[0]
            return float(melhor["aliquota"]), melhor.get("regime_tributario")

    com_aliquota = df[df["aliquota"].apply(valida)] if "aliquota" in df.columns and not df.empty else pd.DataFrame()
    if com_aliquota.empty:
        return None, None
    linha_recente = com_aliquota.sort_values("ano", ascending=False).iloc[0]
    return float(linha_recente["aliquota"]), linha_recente.get("regime_tributario")


# ── INTERFACE ──────────────────────────────────────────────────────────────────

def _lpv_gravado(df, ano, mes):
    """O LPV que está na aba `financeiro` para o mês. None quando vazio."""
    if df is None or df.empty or "lpv" not in df.columns:
        return None
    linha = df[(df["ano"] == ano) & (df["mes"] == mes)]
    if linha.empty:
        return None
    v = linha.iloc[0].get("lpv")
    return float(v) if pd.notna(v) and v else None


def _lpv_a_gravar(meses, ano, hoje):
    """{mes: lpv} que o botão grava: só mês FECHADO e com LPV calculado.

    O mês corrente fica de fora — o C.O dele ainda está crescendo, e gravar o
    parcial faria a Viabilidade decidir com um custo por venda que muda todo
    dia. Mês sem cálculo (sem extrato, sem venda) também: o botão não apaga o
    que alguém digitou à mão.
    """
    import lpv_mensal as _lm
    return {m: r["lpv"] for m, r in (meses or {}).items()
            if r.get("lpv") is not None and _lm.mes_fechado(ano, m, hoje)}


def _secao_lpv_calculado(ano, regime, aliquota, bloqueado, df,
                         usuario_logado=None):
    """O LPV que o Studio calcula (`lpv_mensal.py`), ao lado do gravado.

    {mes: resultado}. Nada é gravado sem o clique: os leitores do LPV
    (Viabilidade, Home, assistente) continuam lendo UMA fonte, a aba
    `financeiro`, e o botão é quem leva o calculado até ela.
    """
    import lpv_mensal as _lm
    import lancamentos as _lan
    from datetime import datetime as _dt_lpv

    st.subheader("LPV calculado pelo Studio")
    st.caption(_rot.tela(
        "C.O do mês = saídas por PIX, cartão, boleto e tarifa que não são "
        "mercadoria, custo fixo, assinatura, imposto ou transferência + "
        "(Flex pago − reembolso do Flex). LPV = C.O ÷ vendas do mês."))
    try:
        meses, erro = _lm.do_ano(ano)
    except Exception as e:
        st.error(f"Não consegui calcular o LPV: {str(e)[:200]}")
        return {}
    if erro:
        st.warning(_rot.tela(f"BASE DE VENDAS: {erro}"))

    hoje = _dt_lpv.now(_lan.FUSO).date()
    gravaveis = _lpv_a_gravar(meses, ano, hoje)
    linhas = []
    for m in range(1, 13):
        r = meses.get(m) or {}
        fechado = _lm.mes_fechado(ano, m, hoje)
        gravado = _lpv_gravado(df, ano, m)
        obs = r.get("motivo") or ("" if fechado else "mês em andamento")
        if r.get("sem_finalidade"):
            obs = (obs + " · " if obs else "") + (
                f"R$ {formatar_br(r['sem_finalidade'])} sem finalidade, fora da conta")
        linhas.append({
            "Mês": MESES[m - 1],
            "LPV calculado": (f"R$ {formatar_br(r['lpv'])}"
                              if r.get("lpv") is not None else "—"),
            "LPV gravado": (f"R$ {formatar_br(gravado)}"
                            if gravado is not None else "—"),
            "C.O": (f"R$ {formatar_br(r['co'])}" if r.get("lpv") is not None
                    else "—"),
            "Vendas": int(r.get("vendas") or 0),
            "Observação": obs,
        })
    st.dataframe(pd.DataFrame(linhas), hide_index=True,
                 use_container_width=True)

    with st.expander("Como cada mês foi calculado"):
        for m in range(1, 13):
            r = meses.get(m) or {}
            if r.get("lpv") is None:
                continue
            partes = " · ".join(f"{k} R$ {formatar_br(v)}"
                                for k, v in r["por_finalidade"].items())
            st.markdown(_rot.tela(
                f"**{MESES[m - 1]}** — saídas R$ {formatar_br(r['saidas'])} "
                f"({partes or 'nenhuma'}) + Flex pago R$ "
                f"{formatar_br(r['flex_pago'])} − reembolso R$ "
                f"{formatar_br(r['reembolso_flex'])} = C.O R$ "
                f"{formatar_br(r['co'])} ÷ {int(r['vendas'])} vendas"))

    if st.button(f"Gravar o LPV calculado nos meses fechados de {ano} "
                 f"({len(gravaveis)})", type="primary",
                 use_container_width=True, key=f"lpv_calc_gravar_{ano}",
                 disabled=bloqueado or not gravaveis):
        lpv_meses = [gravaveis.get(m, _lpv_gravado(df, ano, m))
                     for m in range(1, 13)]
        with st.spinner("Salvando na planilha..."):
            salvar_ano(ano, regime, aliquota, lpv_meses)
        # Os campos do mês têm `key`: sem limpar, o Streamlit mostraria o
        # valor velho digitado e ignoraria o `value=` recém-gravado.
        for m in range(1, 13):
            st.session_state.pop(f"lpv_{ano}_{m}", None)
        if usuario_logado:
            import atividades as historico
            historico.registrar_atividade(
                usuario_logado, "LPV calculado gravado", f"Ano {ano}",
                ", ".join(f"{MESES[m - 1][:3]} {v}"
                          for m, v in sorted(gravaveis.items())))
        st.success("LPV calculado gravado.")
        st.rerun()
    return meses


def pagina_financeiro(usuario_logado=None):
    st.subheader("Área Financeira")

    try:
        df = carregar_dados()
    except Exception as e:
        st.error(f"Não consegui conectar com a planilha: {e}")
        return

    if not df.empty and "ano" not in df.columns:
        st.error(
            "A planilha está conectada, mas o cabeçalho da aba 'financeiro' não está "
            "com os nomes de coluna esperados. Confirme que a linha 1 tem, cada um numa "
            "célula separada (A1, B1, C1...): ano, mes, lpv, regime_tributario, aliquota.\n\n"
            f"Colunas encontradas agora: {list(df.columns)}"
        )
        return

    ano_atual = date.today().year
    anos_disponiveis = list(range(2023, ano_atual + 2))
    ano = st.selectbox("Ano", anos_disponiveis, index=anos_disponiveis.index(ano_atual))

    linha_ano = df[df["ano"] == ano] if not df.empty else pd.DataFrame()
    regime_atual = linha_ano.iloc[0].get("regime_tributario", "") if not linha_ano.empty else ""
    aliquota_val = linha_ano.iloc[0].get("aliquota") if not linha_ano.empty else None
    aliquota_atual = float(aliquota_val) if pd.notna(aliquota_val) else 0.0

    col1, col2 = st.columns(2)
    indice_regime = REGIMES_TRIBUTARIOS.index(regime_atual) if regime_atual in REGIMES_TRIBUTARIOS else 0
    regime = col1.selectbox("Regime tributário", REGIMES_TRIBUTARIOS, index=indice_regime)
    txt_aliquota = col2.text_input("Alíquota (%)",
                                    value=(formatar_br(aliquota_atual) if aliquota_atual else ""),
                                    placeholder="ex: 10")
    aliquota = parse_numero_br(txt_aliquota) or 0.0
    if aliquota > 100 or aliquota < 0:
        st.error(f"Alíquota de {aliquota:.1f}% não faz sentido (tem que estar entre 0 e 100). Confira o valor digitado -- não vai salvar assim.")
        aliquota_invalida = True
    else:
        aliquota_invalida = False

    st.markdown("---")
    _calc = _secao_lpv_calculado(ano, regime, aliquota, aliquota_invalida,
                                 df, usuario_logado)

    st.markdown("---")
    st.caption("O LPV gravado de cada mês. O botão acima grava o calculado; aqui dá para corrigir um mês à mão.")

    lpv_meses = []
    for i, nome_mes in enumerate(MESES, start=1):
        linha_mes = df[(df["ano"] == ano) & (df["mes"] == i)] if not df.empty else pd.DataFrame()
        v_lpv = None
        if not linha_mes.empty:
            v_lpv = linha_mes.iloc[0].get("lpv")

        txt_lpv = st.text_input(f"LPV de {nome_mes} (R$)",
                                 value=(formatar_br(v_lpv) if pd.notna(v_lpv) else ""),
                                 key=f"lpv_{ano}_{i}", placeholder="ex: 22,00")
        _lpv_c = (_calc.get(i) or {}).get("lpv")
        if _lpv_c is not None:
            st.caption(_rot.tela(f"Calculado pelo Studio: R$ {formatar_br(_lpv_c)}"))
        lpv = parse_numero_br(txt_lpv)
        if lpv is None and txt_lpv:
            st.error(f"{nome_mes}: valor não reconhecido.")
        elif lpv is not None:
            st.caption(_rot.tela(f"Entendido como -> R$ {formatar_br(lpv)}"))

        lpv_meses.append(lpv)

    if st.button(f"Salvar dados de {ano}", type="primary", use_container_width=True, disabled=aliquota_invalida):
        with st.spinner("Salvando na planilha..."):
            salvar_ano(ano, regime, aliquota, lpv_meses)
        if usuario_logado:
            import atividades as historico
            historico.registrar_atividade(usuario_logado, "Atualização Financeiro", f"Ano {ano}", f"Regime {regime}, alíquota {aliquota}%")
        st.success("Salvo!")
        st.rerun()

    st.markdown("---")
    st.subheader("LPV vigente")
    lpv, origem = lpv_vigente(df)
    if lpv:
        _atraso = meses_de_atraso_lpv(df)
        if _atraso >= 1:
            st.warning(_rot.tela(
                f"⚠️ LPV em uso: R$ {formatar_br(lpv)}, de **{origem}** — "
                f"{_atraso} {'mês' if _atraso == 1 else 'meses'} atrás. "
                "Toda análise de viabilidade está saindo com custo defasado. "
                "Preencha os meses que faltam abaixo."))
        else:
            st.success(_rot.tela(
                f"LPV vigente: R$ {formatar_br(lpv)}  \n"
                f"Último mês informado: {origem}"))
    else:
        st.warning(f"Ainda não há LPV informado ({origem}).")


if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    import lpv_mensal as _lm_t
    from datetime import date as _d_t
    # O `meses` vem de `lpv_mensal.calcular`, como na tela — não à mão.
    _meses = {m: _lm_t.calcular([], None) for m in range(1, 13)}
    _meses[8] = _lm_t.calcular(
        [{"data": "2026-08-05", "valor": -100.0, "finalidade": "ADS"}],
        {"vendas": 10})
    _meses[10] = _lm_t.calcular(
        [{"data": "2026-10-01", "valor": -100.0, "finalidade": "ADS"}],
        {"vendas": 10})
    _g = _lpv_a_gravar(_meses, 2026, _d_t(2026, 10, 2))
    ok("grava o mês fechado com LPV calculado", _g == {8: 10.0})
    ok("NÃO grava o mês em andamento", 10 not in _g)
    ok("NÃO apaga mês sem cálculo (o digitado à mão fica)", 9 not in _g)

    import pandas as _pd_t
    _df = _pd_t.DataFrame([{"ano": 2026, "mes": 9, "lpv": 20.47}])
    ok("o gravado é lido da aba", _lpv_gravado(_df, 2026, 9) == 20.47)
    ok("mês vazio na aba é None", _lpv_gravado(_df, 2026, 8) is None)

    # A alíquota é gravada pelo MESMO `salvar_ano` que o botão do LPV
    # calculado chama, e é lida pela Viabilidade (`app.py`) e pelo assistente.
    # A forma do `df` é a de `carregar_dados`: colunas em minúsculas, número
    # já convertido.
    _df_aliq = _pd_t.DataFrame([
        {"ano": 2026, "mes": 1, "lpv": 18.59, "regime_tributario": "Simples",
         "aliquota": 9.0},
        {"ano": 2026, "mes": 2, "lpv": None, "regime_tributario": "Simples",
         "aliquota": 500.0}])
    ok("aliquota_vigente devolve a válida do ano",
       aliquota_vigente(_df_aliq, 2026) == (9.0, "Simples"))
    ok("e ignora alíquota absurda", aliquota_vigente(
        _df_aliq[_df_aliq["mes"] == 2], 2026) == (None, None))

    print("\nfalhas:", falhas)
    raise SystemExit(1 if falhas else 0)
