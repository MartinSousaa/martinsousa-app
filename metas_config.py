"""
metas_config.py — Configurações mensais de metas persistidas no Google Sheets
Aba: "metas_config" na planilha "MartinSousa - Financeiro"
"""
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

import planilha as _plan
# Nome vindo do ambiente: producao usa o padrao, homologacao usa a copia.
PLANILHA_NOME = _plan.nome()
ABA_NOME = "metas_config"

# Ordem fixa de colunas na planilha
COLUNAS = [
    "ano", "mes",
    "meta_equipe",           # pontos meta coletiva
    "meta_maxx_pct",         # % da meta mensal (ex: 110 = 10% a mais)
    # Metas por pessoa entram adiante, derivadas da equipe cadastrada.
    "max_pen_normal",        # máx penalidades meta normal (ex: 4)
    "max_pen_maxx",          # máx penalidades meta maxx (ex: 1)
    "max_tol_normal",        # máx tolerâncias pontualidade normal (ex: 15)
    "max_tol_maxx",          # máx tolerâncias pontualidade maxx (ex: 7)
    "max_atr_normal",        # máx atrasos pontualidade normal (ex: 10)
    "max_atr_maxx",          # máx atrasos pontualidade maxx (ex: 5)
    "max_retrab_normal",     # % retrabalho máx normal (ex: 10)
    "max_retrab_maxx",       # % retrabalho máx maxx (ex: 5)
    "min_membro_pct",        # % mín cartões com membro (ex: 95)
    "exec_red_equipe",       # % de reducao do tempo medio de execucao da equipe
]

DEFAULTS = {
    "meta_equipe":         5000,
    "meta_maxx_pct":       110,

    "max_pen_normal":      4,
    "max_pen_maxx":        1,
    "max_tol_normal":      15,
    "max_tol_maxx":        7,
    "max_atr_normal":      10,
    "max_atr_maxx":        5,
    "max_retrab_normal":   10,
    "max_retrab_maxx":     5,
    "min_membro_pct":      95,
    "exec_red_equipe":     0,
    "exec_ref_equipe":     0,
    "min_contrib_normal":  80,
    "min_contrib_maxx":    100,
    "max_adv_normal":      2,
    "max_adv_maxx":        1,
}

# Rótulos legíveis para exibição na UI
LABELS = {
    "meta_equipe":         "Meta Equipe (pts)",
    "meta_maxx_pct":       "Meta MAXX (% da meta mensal)",

    "max_pen_normal":      "Máx. penalidades (Meta Normal)",
    "max_pen_maxx":        "Máx. penalidades (Meta MAXX)",
    "max_tol_normal":      "Máx. tolerâncias pontualidade (Normal)",
    "max_tol_maxx":        "Máx. tolerâncias pontualidade (MAXX)",
    "max_atr_normal":      "Máx. atrasos pontualidade (Normal)",
    "max_atr_maxx":        "Máx. atrasos pontualidade (MAXX)",
    "max_retrab_normal":   "Retrabalho máx. % (Normal)",
    "max_retrab_maxx":     "Retrabalho máx. % (MAXX)",
    "min_membro_pct":      "% mín. cartões com membro",
    "exec_red_equipe":     "Redução do tempo médio de execução — equipe (%)",
    "exec_ref_equipe":     "Tempo de referência — equipe (min)",
    "min_contrib_normal":  "% mín. da meta individual p/ entrar na Coletiva",
    "min_contrib_maxx":    "% mín. da meta individual p/ entrar na MAXX",
    "max_adv_normal":      "Máx. advertências (Meta Normal)",
    "max_adv_maxx":        "Máx. advertências (Meta MAXX)",
}


# ── Campos por pessoa ─────────────────────────────────────────────────────────
# Derivados da equipe cadastrada, e nao de uma lista fixa: contratar alguem
# passa a ser cadastro na aba "equipe", sem alteracao de codigo.
META_INDIVIDUAL_PADRAO = 1500

# Tempo medio de execucao: referencia e reducao esperada, por pessoa e por mes.
#
# A referencia NAO e digitada. Ela e a media que o Trello mediu, congelada no mes
# quando o gestor salva — congelar e o ponto: se o alvo fosse "a media atual
# menos 10%", ele perseguiria o proprio resultado e ninguem chegaria nunca.
#
# Quem ainda nao tem cartao medido (contratacao recente) entra com 2h, para ter
# uma meta desde o primeiro mes em vez de um traco.
EXEC_REF_PADRAO_MIN = 120

# Zero e o marcador de "ainda nao ancorada neste mes". Precisa ser um valor que
# nao possa vir de uma medicao real — carregar_config preenche com o padrao tudo
# que falta na planilha, entao sem um marcador nao havia como distinguir um mes
# nunca salvo de um mes salvo com 2h.
EXEC_REF_NAO_ANCORADA = 0
EXEC_RED_PADRAO_PCT = 0


def campos_metas_pessoa():
    """[(chave_meta, chave_maxx, nome)] por pessoa — a forma que a tela usa.

    campos_por_pessoa() devolve a lista achatada, boa para sincronizar colunas e
    padroes. Para desenhar a tela o que serve e a pessoa inteira numa linha: a
    meta dela ao lado da MAXX dela.
    """
    return [(f"meta_{user}", f"meta_maxx_{user}", nome)
            for user, nome in _equipe().items()]


def campos_tempo_execucao():
    """[(chave_referencia, chave_reducao, nome)] de cada pessoa da equipe."""
    return [(f"exec_ref_{user}", f"exec_red_{user}", nome)
            for user, nome in _equipe().items()]


# Advertencia nao tem de onde ser lida: nao esta no Trello nem na RHiD. E um
# lancamento do gestor, por pessoa e por mes, como qualquer outro campo daqui.
ADVERTENCIAS_PADRAO = 0


def campos_advertencia():
    """[(chave, nome)] de advertências de cada pessoa da equipe."""
    return [(f"adv_{user}", nome) for user, nome in _equipe().items()]


def _crono(rotulo, seg, detalhe=""):
    """Registra quanto custou uma ida a planilha. Nunca derruba a leitura."""
    try:
        import cronometro
        cronometro.marcar(rotulo, seg, detalhe)
    except Exception:
        pass


def _equipe():
    try:
        import placar_core as _pc
        _pc.recarregar_membros()
        return dict(_pc.MEMBROS_ATIVOS)
    except Exception:
        return {}


def campos_por_pessoa():
    """[(chave, rotulo, padrao)] para meta individual e meta MAXX de cada um."""
    campos = []
    for user, nome in _equipe().items():
        campos.append((f"meta_{user}", f"Meta Individual — {nome} (pts)",
                       META_INDIVIDUAL_PADRAO))
        campos.append((f"meta_maxx_{user}", f"Meta MAXX — {nome} (pts)", 0))
    return campos


def sincronizar_campos():
    """Garante que COLUNAS, DEFAULTS e LABELS conhecam a equipe atual."""
    campos = list(campos_por_pessoa())
    for chave_ref, chave_red, nome in campos_tempo_execucao():
        campos.append((chave_ref, f"Tempo de referência — {nome} (min)",
                       EXEC_REF_NAO_ANCORADA))
        campos.append((chave_red, f"Redução esperada — {nome} (%)",
                       EXEC_RED_PADRAO_PCT))
    for chave_adv, nome in campos_advertencia():
        campos.append((chave_adv, f"Advertências — {nome}", ADVERTENCIAS_PADRAO))
    for chave, rotulo, padrao in campos:
        if chave not in COLUNAS:
            COLUNAS.append(chave)
        DEFAULTS.setdefault(chave, padrao)
        LABELS.setdefault(chave, rotulo)

# ── Conexão ────────────────────────────────────────────────────────────────────

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
        aba = planilha.worksheet(ABA_NOME)
        cabecalho = aba.row_values(1)
        for col in COLUNAS:
            if col not in cabecalho:
                aba.add_cols(1)
                aba.update_cell(1, len(cabecalho) + 1, col)
                cabecalho.append(col)
        return aba
    except gspread.exceptions.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA_NOME, rows=500, cols=len(COLUNAS))
        aba.append_row(COLUNAS, value_input_option="RAW")
        return aba

# ── Leitura ────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=600)
def carregar_todas() -> pd.DataFrame:
    """Retorna DataFrame com todos os registros de configuração de metas."""
    try:
        aba = _aba()
        import time as _t_crono
        _t0_crono = _t_crono.perf_counter()
        registros = aba.get_all_records(value_render_option="UNFORMATTED_VALUE")
        _crono("Planilha: metas", _t_crono.perf_counter() - _t0_crono,
               f"{len(registros)} linhas")
        df = pd.DataFrame(registros)
        if not df.empty:
            df.columns = [str(c).strip().lower() for c in df.columns]
            for col in ["ano", "mes"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        return df
    except Exception:
        return pd.DataFrame()


def carregar_config(ano: int, mes: int) -> dict:
    """Retorna dict de configuração para o mês. Valores ausentes são preenchidos com defaults."""
    sincronizar_campos()
    cfg = {**DEFAULTS, "ano": int(ano), "mes": int(mes)}
    try:
        df = carregar_todas()
        if df.empty:
            return cfg
        mask = (df["ano"] == int(ano)) & (df["mes"] == int(mes))
        linha = df[mask]
        if linha.empty:
            return cfg
        row = linha.iloc[-1]
        for k in DEFAULTS:
            val = row.get(k)
            try:
                v = float(val)
                cfg[k] = int(v) if v == int(v) else v
            except Exception:
                pass
    except Exception:
        pass
    return cfg

# ── Escrita ────────────────────────────────────────────────────────────────────

def salvar_config(ano: int, mes: int, dados: dict):
    """Salva ou atualiza a configuração do mês, preservando o que não veio no form.

    Dois cuidados que faltavam e apagavam configuração:

    1. A linha era montada na ordem de COLUNAS, do código, e escrita por posição.
       Bastava a planilha ter outra ordem — ou o código ganhar uma coluna nova no
       meio da lista — para os valores irem parar nos campos errados a partir
       dali. Agora a linha é montada pelo CABEÇALHO REAL da planilha, e coluna
       nova é acrescentada no fim.

    2. Campo ausente em `dados` virava o valor padrão, apagando o que estava
       salvo. Agora a base é a configuração atual do mês: o formulário só
       sobrescreve o que ele de fato enviou.
    """
    try:
        sincronizar_campos()
        aba = _aba()

        cabecalho = [str(c).strip() for c in aba.row_values(1)]
        if not cabecalho:
            cabecalho = list(COLUNAS)
            aba.update("A1", [cabecalho])

        # Coluna que o código conhece e a planilha ainda não tem entra no fim,
        # sem deslocar nada do que já está gravado.
        faltando = [c for c in COLUNAS if c not in cabecalho]
        if faltando:
            cabecalho = cabecalho + faltando
            aba.update("A1", [cabecalho])

        registros = aba.get_all_records(value_render_option="UNFORMATTED_VALUE")
        linha_idx, atual = None, {}
        for i, r in enumerate(registros, start=2):
            try:
                if int(r.get("ano", 0)) == int(ano) and int(r.get("mes", 0)) == int(mes):
                    linha_idx, atual = i, dict(r)
                    break
            except (TypeError, ValueError):
                pass

        valores = {**DEFAULTS, **{k: v for k, v in atual.items() if v not in (None, "")},
                   **dados, "ano": int(ano), "mes": int(mes)}
        nova = [valores.get(col, "") for col in cabecalho]

        fim = _letra_coluna(len(cabecalho))
        if linha_idx:
            aba.update(f"A{linha_idx}:{fim}{linha_idx}", [nova],
                       value_input_option="RAW")
        else:
            aba.append_row(nova, value_input_option="RAW")

        carregar_todas.clear()
    except Exception as e:
        st.error(f"Erro ao salvar configuração: {e}")


def _letra_coluna(n: int) -> str:
    """1 -> A, 27 -> AA. A planilha ja passa de 26 colunas."""
    letras = ""
    while n > 0:
        n, resto = divmod(n - 1, 26)
        letras = chr(65 + resto) + letras
    return letras