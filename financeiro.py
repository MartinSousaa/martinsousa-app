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


def parse_inteiro_br(texto):
    """Converte texto de QUANTIDADE (sem casas decimais -- ex: numero de
    vendas) em int. Aqui ponto e virgula so podem ser separador de milhar
    (2.088 = dois mil e oitenta e oito), nunca decimal."""
    if texto is None:
        return None
    texto = str(texto).strip().replace(" ", "").replace(".", "").replace(",", "")
    if not texto:
        return None
    try:
        return int(texto)
    except ValueError:
        return None


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
    registros = aba.get_all_records()
    df = pd.DataFrame(registros)
    if df.empty:
        df = pd.DataFrame(columns=COLUNAS)
        return df
    # Normaliza nomes de coluna (maiuscula/minuscula e espacos nao importam)
    df.columns = [str(c).strip().lower() for c in df.columns]
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
    ignorado nos calculos, nunca inventa numero).
    OBS: a coluna 'lucro_bruto' guarda a MARGEM BRUTA em % (ex: 78.03),
    informada diretamente pelo usuario -- nao e mais um valor em R$.

    Formula (conforme definido pelo usuario):
    Ponto de Equilibrio = Custos totais / Margem Bruta
    LPV = Ponto de Equilibrio / Numero de vendas
    """
    custos = row.get("custos_totais")
    fat = row.get("faturamento")
    vendas = row.get("vendas")
    margem_bruta_pct = row.get("lucro_bruto")

    valores = [custos, fat, vendas, margem_bruta_pct]
    if any(v is None or (isinstance(v, float) and pd.isna(v)) or v == 0 for v in valores):
        return None

    margem_bruta = margem_bruta_pct / 100
    ponto_equilibrio = custos / margem_bruta if margem_bruta else None
    lpv = ponto_equilibrio / vendas if ponto_equilibrio else None

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
    """Aliquota do ano informado; se nao tiver (ou for um valor absurdo,
    fora de 0-100), usa a mais recente disponivel que seja valida."""
    ano = ano or date.today().year

    def valida(v):
        return pd.notna(v) and v and 0 < v <= 100

    linha = df[df["ano"] == ano]
    if not linha.empty and valida(linha.iloc[0].get("aliquota")):
        return float(linha.iloc[0]["aliquota"]), linha.iloc[0].get("regime_tributario")

    com_aliquota = df[df["aliquota"].apply(valida)] if "aliquota" in df.columns else pd.DataFrame()
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

    if not df.empty and "ano" not in df.columns:
        st.error(
            "A planilha está conectada, mas o cabeçalho da aba 'financeiro' não está "
            "com os nomes de coluna esperados. Confirme que a linha 1 tem, cada um numa "
            "célula separada (A1, B1, C1...): ano, mes, custos_totais, faturamento, "
            "vendas, lucro_bruto, regime_tributario, aliquota.\n\n"
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
    regime = col1.text_input("Regime tributário", value=regime_atual or "")
    txt_aliquota = col2.text_input("Alíquota (%)",
                                    value=(f"{aliquota_atual:.2f}".replace(".", ",") if aliquota_atual else ""),
                                    placeholder="ex: 10")
    aliquota = parse_numero_br(txt_aliquota) or 0.0
    if aliquota > 100 or aliquota < 0:
        st.error(f"Alíquota de {aliquota:.1f}% não faz sentido (tem que estar entre 0 e 100). Confira o valor digitado -- não vai salvar assim.")
        aliquota_invalida = True
    else:
        aliquota_invalida = False

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
            txt_custos = c1.text_input("Custos totais (R$)",
                                        value=(f"{v_custos:.2f}".replace(".", ",") if pd.notna(v_custos) else ""),
                                        key=f"custos_{ano}_{i}", placeholder="ex: 45.737,34")
            txt_fat = c2.text_input("Faturamento (R$)",
                                     value=(f"{v_fat:.2f}".replace(".", ",") if pd.notna(v_fat) else ""),
                                     key=f"fat_{ano}_{i}", placeholder="ex: 219.124,82")
            txt_vendas = c3.text_input("Vendas (qtd)",
                                        value=(f"{v_vendas:.0f}" if pd.notna(v_vendas) else ""),
                                        key=f"vendas_{ano}_{i}", placeholder="ex: 1954")
            txt_margem = c4.text_input("Margem Bruta (%)",
                                        value=(f"{v_lucro:.2f}".replace(".", ",") if pd.notna(v_lucro) else ""),
                                        key=f"lucro_{ano}_{i}", placeholder="ex: 78,03")

            custos = parse_numero_br(txt_custos)
            fat    = parse_numero_br(txt_fat)
            vendas = parse_inteiro_br(txt_vendas)
            margem = parse_numero_br(txt_margem)

            if custos is None and txt_custos:
                st.error("Custos totais: valor não reconhecido.")
            if fat is None and txt_fat:
                st.error("Faturamento: valor não reconhecido.")
            if vendas is None and txt_vendas:
                st.error("Vendas: valor não reconhecido.")
            if margem is None and txt_margem:
                st.error("Margem Bruta: valor não reconhecido.")

            calc = calcular_mes({"custos_totais": custos, "faturamento": fat,
                                  "vendas": vendas, "lucro_bruto": margem})
            if calc:
                st.caption(
                    f"Ponto de equilíbrio: R${calc['ponto_equilibrio']:.2f} · "
                    f"LPV: R${calc['lpv']:.2f}"
                )
            else:
                st.caption("Mês incompleto — preencha os 4 campos pra esse mês entrar nos cálculos.")

        dados_meses.append({
            "custos_totais": custos,
            "faturamento": fat,
            "vendas": vendas,
            "lucro_bruto": margem,
        })

    if st.button(f"Salvar dados de {ano}", type="primary", use_container_width=True, disabled=aliquota_invalida):
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
