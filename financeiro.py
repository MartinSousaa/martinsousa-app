import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import date

PLANILHA_NOME = "MartinSousa - Financeiro"
ABA_NOME = "financeiro"

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
          "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

REGIMES_TRIBUTARIOS = ["Simples Nacional", "Lucro Presumido", "Lucro Real", "MEI"]

COLUNAS = ["ano", "mes", "lpv", "regime_tributario", "aliquota"]


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

def _cliente():
    creds_dict = dict(st.secrets["gcp_service_account"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def _aba():
    cliente = _cliente()
    planilha = cliente.open(PLANILHA_NOME)
    return planilha.worksheet(ABA_NOME)


@st.cache_data(ttl=60)
def carregar_dados():
    """Le todos os dados da planilha. Cache de 60s pra nao bater na API
    do Google toda hora que a tela recarrega."""
    aba = _aba()
    registros = aba.get_all_records(value_render_option="UNFORMATTED_VALUE")
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
    st.caption("Informe o LPV que você já calculou internamente pra cada mês. Pode deixar em branco o que ainda não tem.")

    lpv_meses = []
    for i, nome_mes in enumerate(MESES, start=1):
        linha_mes = df[(df["ano"] == ano) & (df["mes"] == i)] if not df.empty else pd.DataFrame()
        v_lpv = None
        if not linha_mes.empty:
            v_lpv = linha_mes.iloc[0].get("lpv")

        txt_lpv = st.text_input(f"LPV de {nome_mes} (R$)",
                                 value=(formatar_br(v_lpv) if pd.notna(v_lpv) else ""),
                                 key=f"lpv_{ano}_{i}", placeholder="ex: 22,00")
        lpv = parse_numero_br(txt_lpv)
        if lpv is None and txt_lpv:
            st.error(f"{nome_mes}: valor não reconhecido.")
        elif lpv is not None:
            st.caption(f"Entendido como -> R${formatar_br(lpv)}")

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
        st.success(f"LPV vigente: R${formatar_br(lpv)}  \nÚltimo mês informado: {origem}")
    else:
        st.warning(f"Ainda não há LPV informado ({origem}).")
