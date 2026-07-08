import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import date

PLANILHA_NOME = "MartinSousa - Financeiro"
ABA_NOME = "financeiro"

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
          "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

# Blocos sazonais fixos definidos pelo Léo (em vez de média móvel)
BLOCOS_SAZONAIS = {
    "Baixa temporada (Jan-Mar)": [1, 2, 3],
    "Normal (Abr-Set)": [4, 5, 6, 7, 8, 9],
    "Alta temporada (Out-Dez)": [10, 11, 12],
}

COLUNAS = ["ano", "mes", "custos_totais", "faturamento", "vendas",
           "lucro_bruto", "regime_tributario", "aliquota"]


# ── CONEXAO COM A PLANILHA ──────────────────────────────────────────────────

def _cliente():
    creds_dict = dict(st.secrets["gcp_service_account"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
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
    registros = aba.get_all_records()
    df = pd.DataFrame(registros)
    if df.empty:
        df = pd.DataFrame(columns=COLUNAS)
        return df
    for col in ["ano", "mes", "custos_totais", "faturamento", "vendas", "lucro_bruto", "aliquota"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def salvar_ano(ano, regime, aliquota, dados_meses):
    """Grava (atualiza ou cria) as 12 linhas de um ano na planilha.
    dados_meses: lista de 12 dicts (mes 1 a 12) com custos_totais,
    faturamento, vendas, lucro_bruto (podem ser None)."""
    aba = _aba()
    valores_existentes = aba.get_all_values()

    if not valores_existentes:
        aba.append_row(COLUNAS)
        valores_existentes = [COLUNAS]

    linhas_existentes = valores_existentes[1:] if len(valores_existentes) > 1 else []
    mapa_linha = {}
    for i, linha in enumerate(linhas_existentes):
        if len(linha) >= 2 and linha[0] and linha[1]:
            try:
                chave = (int(float(linha[0])), int(float(linha[1])))
                mapa_linha[chave] = i + 2  # +2: cabecalho ocupa a linha 1, planilha e 1-indexed
            except ValueError:
                pass

    for mes_num, dados in enumerate(dados_meses, start=1):
        linha_valores = [
            ano, mes_num,
            dados.get("custos_totais") if dados.get("custos_totais") else "",
            dados.get("faturamento") if dados.get("faturamento") else "",
            dados.get("vendas") if dados.get("vendas") else "",
            dados.get("lucro_bruto") if dados.get("lucro_bruto") else "",
            regime or "",
            aliquota if aliquota else "",
        ]
        chave = (ano, mes_num)
        if chave in mapa_linha:
            num_linha = mapa_linha[chave]
            aba.update(f"A{num_linha}:H{num_linha}", [linha_valores])
        else:
            aba.append_row(linha_valores)

    carregar_dados.clear()


# ── CALCULOS ─────────────────────────────────────────────────────────────────

def calcular_mes(row):
    """Retorna dict com margem_bruta, ponto_equilibrio e lpv pra um mes,
    ou None se faltar algum dos 4 campos necessarios (mes incompleto e
    ignorado nos calculos, nunca inventa numero)."""
    custos = row.get("custos_totais")
    fat = row.get("faturamento")
    vendas = row.get("vendas")
    lucro_bruto = row.get("lucro_bruto")

    valores = [custos, fat, vendas, lucro_bruto]
    if any(v is None or (isinstance(v, float) and pd.isna(v)) or v == 0 for v in valores):
        return None

    margem_bruta = lucro_bruto / fat
    ponto_equilibrio = custos / margem_bruta if margem_bruta else None
    lpv = custos / vendas

    return {"margem_bruta": margem_bruta, "ponto_equilibrio": ponto_equilibrio, "lpv": lpv}


def bloco_do_mes(mes):
    for nome, meses in BLOCOS_SAZONAIS.items():
        if mes in meses:
            return nome
    return None


def lpv_vigente(df, hoje=None):
    """LPV do bloco sazonal vigente: usa os meses ja fechados do bloco atual
    no ano corrente; se nenhum mes fechado tiver dado completo, cai pro
    mesmo bloco do ano anterior (bloco inteiro)."""
    hoje = hoje or date.today()
    bloco_atual = bloco_do_mes(hoje.month)
    meses_bloco = BLOCOS_SAZONAIS[bloco_atual]
    meses_fechados_ano = [m for m in meses_bloco if m < hoje.month]

    def lpvs_de(ano, meses):
        valores = []
        for m in meses:
            linha = df[(df["ano"] == ano) & (df["mes"] == m)]
            if linha.empty:
                continue
            calc = calcular_mes(linha.iloc[0].to_dict())
            if calc:
                valores.append(calc["lpv"])
        return valores

    valores = lpvs_de(hoje.year, meses_fechados_ano)
    origem = f"{bloco_atual}, {hoje.year} (meses ja fechados)"

    if not valores:
        valores = lpvs_de(hoje.year - 1, meses_bloco)
        origem = f"{bloco_atual}, {hoje.year - 1} (ano anterior, sem dado suficiente no ano atual)"

    if not valores:
        return None, "sem dados suficientes pra calcular"

    return sum(valores) / len(valores), origem


def aliquota_vigente(df, ano=None):
    """Aliquota do ano informado; se nao tiver, usa a mais recente disponivel."""
    ano = ano or date.today().year
    linha = df[df["ano"] == ano]
    if not linha.empty and pd.notna(linha.iloc[0].get("aliquota")) and linha.iloc[0].get("aliquota"):
        return float(linha.iloc[0]["aliquota"]), linha.iloc[0].get("regime_tributario")

    com_aliquota = df.dropna(subset=["aliquota"]) if "aliquota" in df.columns else pd.DataFrame()
    com_aliquota = com_aliquota[com_aliquota["aliquota"] != 0] if not com_aliquota.empty else com_aliquota
    if com_aliquota.empty:
        return None, None
    linha_recente = com_aliquota.sort_values("ano", ascending=False).iloc[0]
    return float(linha_recente["aliquota"]), linha_recente.get("regime_tributario")


# ── INTERFACE ──────────────────────────────────────────────────────────────────

def pagina_financeiro():
    st.subheader("Área Financeira")

    admin_password = st.secrets.get("ADMIN_PASSWORD", "")
    if "financeiro_autenticado" not in st.session_state:
        st.session_state.financeiro_autenticado = False

    if not st.session_state.financeiro_autenticado:
        if not admin_password:
            st.warning("Senha de administrador ainda não configurada nas Secrets do Streamlit (chave ADMIN_PASSWORD).")
            return
        senha = st.text_input("Senha de administrador", type="password")
        if st.button("Entrar"):
            if senha == admin_password:
                st.session_state.financeiro_autenticado = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
        return

    try:
        df = carregar_dados()
    except Exception as e:
        st.error(f"Não consegui conectar com a planilha: {e}")
        return

    ano_atual = date.today().year
    anos_disponiveis = list(range(2023, ano_atual + 2))
    ano = st.selectbox("Ano", anos_disponiveis, index=anos_disponiveis.index(ano_atual))

    linha_ano = df[df["ano"] == ano] if not df.empty else pd.DataFrame()
    regime_atual = linha_ano.iloc[0].get("regime_tributario", "") if not linha_ano.empty else ""
    aliquota_val = linha_ano.iloc[0].get("aliquota") if not linha_ano.empty else None
    aliquota_atual = float(aliquota_val) if pd.notna(aliquota_val) else 0.0

    col1, col2 = st.columns(2)
    regime = col1.text_input("Regime tributário", value=regime_atual or "")
    aliquota = col2.number_input("Alíquota (%)", min_value=0.0, max_value=100.0, value=aliquota_atual, step=0.1)

    st.markdown("---")
    st.caption("Preencha o que tiver de cada mês. Pode deixar em branco (0) o que ainda não tem.")

    dados_meses = []
    for i, nome_mes in enumerate(MESES, start=1):
        linha_mes = df[(df["ano"] == ano) & (df["mes"] == i)] if not df.empty else pd.DataFrame()
        v_custos = v_fat = v_vendas = v_lucro = None
        if not linha_mes.empty:
            r = linha_mes.iloc[0]
            v_custos, v_fat, v_vendas, v_lucro = (
                r.get("custos_totais"), r.get("faturamento"),
                r.get("vendas"), r.get("lucro_bruto"),
            )

        with st.expander(nome_mes):
            c1, c2, c3, c4 = st.columns(4)
            custos = c1.number_input("Custos totais (R$)", min_value=0.0,
                                      value=float(v_custos) if pd.notna(v_custos) else 0.0,
                                      step=100.0, key=f"custos_{ano}_{i}")
            fat = c2.number_input("Faturamento (R$)", min_value=0.0,
                                   value=float(v_fat) if pd.notna(v_fat) else 0.0,
                                   step=100.0, key=f"fat_{ano}_{i}")
            vendas = c3.number_input("Vendas (qtd)", min_value=0.0,
                                      value=float(v_vendas) if pd.notna(v_vendas) else 0.0,
                                      step=1.0, key=f"vendas_{ano}_{i}")
            lucro = c4.number_input("Lucro Bruto (R$)", min_value=0.0,
                                     value=float(v_lucro) if pd.notna(v_lucro) else 0.0,
                                     step=100.0, key=f"lucro_{ano}_{i}")

            calc = calcular_mes({"custos_totais": custos, "faturamento": fat,
                                  "vendas": vendas, "lucro_bruto": lucro})
            if calc:
                st.caption(
                    f"Margem bruta: {calc['margem_bruta']*100:.1f}% · "
                    f"Ponto de equilíbrio: R${calc['ponto_equilibrio']:.2f} · "
                    f"LPV: R${calc['lpv']:.2f}"
                )
            else:
                st.caption("Mês incompleto — preencha os 4 campos pra esse mês entrar nos cálculos.")

        dados_meses.append({
            "custos_totais": custos or None,
            "faturamento": fat or None,
            "vendas": vendas or None,
            "lucro_bruto": lucro or None,
        })

    if st.button(f"Salvar dados de {ano}", type="primary", use_container_width=True):
        with st.spinner("Salvando na planilha..."):
            salvar_ano(ano, regime, aliquota, dados_meses)
        st.success("Salvo!")
        st.rerun()

    st.markdown("---")
    st.subheader("LPV vigente (calculado)")
    lpv, origem = lpv_vigente(df)
    if lpv:
        st.success(f"LPV vigente: R${lpv:.2f}  \nCalculado com base em: {origem}")
    else:
        st.warning(f"Ainda não há meses completos suficientes pra calcular o LPV automático ({origem}).")
