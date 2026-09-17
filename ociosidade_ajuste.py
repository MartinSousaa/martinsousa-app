"""ociosidade_ajuste.py — o mês em que a ociosidade medida foi perdoada.

O QUE ACONTECEU
---------------
Setembro de 2026. A ociosidade da equipe estourou a meta de 10%, o gestor
sentou com o time e fechou um acordo: o mês entra com 5% para todo mundo —
dentro da meta —, e de outubro em diante vale o número real. Quem estourar de
novo, perde.

POR QUE ISSO NÃO É "CORRIGIR O NÚMERO"
--------------------------------------
Porque não é. O número medido está certo, e continua guardado: o que houve foi
uma decisão de gestão sobre um mês específico. Reescrever a medição faria o
painel mentir, e mentira em painel é pior que número ruim — número ruim se
discute, número inventado se acredita.

Daí a forma: um REGISTRO, com mês, pessoa, percentual, motivo e quem aplicou.
A tela mostra "ajustado" e o valor real ao lado. Quem olhar o setembro de 2027
vai saber por que aquele mês tem 5% cravado.

POR QUE NÃO NO CÓDIGO
---------------------
Um `if mes == 9` resolveria hoje e cobraria depois: no acordo seguinte alguém
teria que mexer no código, e a regra que vale para uma pessoa e não para outra
viraria uma lista de nomes dentro de um arquivo — que é exatamente o que já
escondeu dois colaboradores do painel nesta base.

ONDE ELE ENTRA
--------------
Num lugar só: `relogio_ponto.get_ociosidade_mes`, que é a fonte das três telas
que mostram ociosidade. Aplicar em cada tela daria três respostas para a mesma
pergunta, e elas discordariam na primeira mudança.
"""

from datetime import datetime, timezone, timedelta

import streamlit as st

ABA_NOME = "ociosidade_ajuste"
COLUNAS = ["mes", "username", "pct", "motivo", "atualizado_em", "atualizado_por"]

FUSO = timezone(timedelta(hours=-3))


def _num(v, padrao=0.0):
    if v is None:
        return padrao
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace("%", "").replace(" ", "")
    if not t:
        return padrao
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return padrao


def mes_texto(ano, mes):
    return f"{int(ano):04d}-{int(mes):02d}"


def aplicar(resultado, ano, mes, ajustes=None):
    """A ociosidade do mês com os ajustes por cima. Função pura.

    `resultado` é o que `get_ociosidade_mes` devolve; `ajustes` é
    {"AAAA-MM": {username: pct}}. Devolve um dicionário NOVO — o original
    continua intacto, e é dele que sai o valor real mostrado ao lado.

    O percentual vira minutos sobre as horas disponíveis da pessoa: 5% de quem
    trabalhou 154h não é o mesmo tanto que 5% de quem trabalhou 40h, e cravar
    minutos iguais para todos premiaria quem faltou.
    """
    do_mes = (ajustes or {}).get(mes_texto(ano, mes)) or {}
    if not do_mes or not resultado:
        return resultado
    fora = {}
    for user, d in resultado.items():
        pct_novo = do_mes.get(user)
        if pct_novo is None or not isinstance(d, dict):
            fora[user] = d
            continue
        hd = float(d.get("horas_disp_min") or 0.0)
        novo = dict(d)
        novo["ocio_medido_min"] = float(d.get("ociosidade_min") or 0.0)
        novo["pct_medido"] = float(d.get("pct_ocioso") or 0.0)
        novo["ociosidade_min"] = hd * float(pct_novo) / 100.0
        novo["pct_ocioso"] = float(pct_novo)
        novo["ajustado"] = True
        fora[user] = novo
    return fora


@st.cache_data(ttl=300)
def carregar():
    """{"AAAA-MM": {username: pct}}. Vazio em qualquer falha.

    Falha não pode virar ajuste: sem a aba, a ociosidade é a medida — que é o
    padrão certo. O contrário perdoaria um mês por causa de um erro de rede.
    """
    try:
        aba = _aba()
        registros = aba.get_all_records()
    except Exception:
        return {}
    fora = {}
    for linha in registros:
        mes = str(linha.get("mes", "") or "").strip()
        user = str(linha.get("username", "") or "").strip()
        if not mes or not user:
            continue
        fora.setdefault(mes, {})[user] = _num(linha.get("pct"), 0.0)
    return fora


def _aba():
    import gspread
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        return planilha.worksheet(ABA_NOME)
    except gspread.WorksheetNotFound:
        nova = planilha.add_worksheet(title=ABA_NOME, rows=200,
                                      cols=len(COLUNAS))
        nova.append_row(COLUNAS, value_input_option="RAW")
        return nova


def salvar(ano, mes, usuarios, pct, motivo="", usuario_logado=""):
    """Grava o ajuste do mês para essas pessoas. (ok, mensagem).

    Regrava a pessoa que já tem linha naquele mês em vez de empilhar outra:
    duas linhas para o mesmo par (mês, pessoa) são duas respostas para a mesma
    pergunta, e a segunda leitura escolheria uma delas sem dizer qual.
    """
    alvo = mes_texto(ano, mes)
    nomes = [str(u).strip() for u in (usuarios or []) if str(u).strip()]
    if not nomes:
        return False, "Ninguém selecionado."
    agora = datetime.now(FUSO).strftime("%Y-%m-%d %H:%M")
    try:
        aba = _aba()
        atuais = aba.get_all_records()
        linhas = [l for l in atuais
                  if not (str(l.get("mes", "")).strip() == alvo
                          and str(l.get("username", "")).strip() in nomes)]
        for n in nomes:
            linhas.append({"mes": alvo, "username": n,
                           "pct": round(_num(pct), 2),
                           "motivo": str(motivo or "")[:200],
                           "atualizado_em": agora,
                           "atualizado_por": str(usuario_logado or "")[:60]})
        aba.clear()
        aba.update([COLUNAS] + [[l.get(c, "") for c in COLUNAS] for l in linhas],
                   value_input_option="RAW")
    except Exception as e:
        return False, str(e)[:200]
    carregar.clear()
    return True, f"{len(nomes)} pessoa(s) com {_num(pct):.0f}% em {alvo}."


def remover(ano, mes):
    """Apaga os ajustes de um mês inteiro. (ok, mensagem)."""
    alvo = mes_texto(ano, mes)
    try:
        aba = _aba()
        linhas = [l for l in aba.get_all_records()
                  if str(l.get("mes", "")).strip() != alvo]
        aba.clear()
        aba.update([COLUNAS] + [[l.get(c, "") for c in COLUNAS] for l in linhas],
                   value_input_option="RAW")
    except Exception as e:
        return False, str(e)[:200]
    carregar.clear()
    return True, f"Ajustes de {alvo} removidos — volta a valer o medido."


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    _med = {
        "myrella":  {"horas_disp_min": 9240.0, "ociosidade_min": 2772.0,
                     "pct_ocioso": 30.0},
        "gabriel":  {"horas_disp_min": 4000.0, "ociosidade_min": 120.0,
                     "pct_ocioso": 3.0},
    }
    _aj = {"2026-09": {"myrella": 5, "gabriel": 5}}

    _r = aplicar(_med, 2026, 9, _aj)
    ok("quem estourou cai para 5%", _r["myrella"]["pct_ocioso"] == 5.0)
    ok("5% viram minutos sobre as horas DELA, e nao um numero fixo",
       abs(_r["myrella"]["ociosidade_min"] - 9240 * 0.05) < 0.01
       and abs(_r["gabriel"]["ociosidade_min"] - 4000 * 0.05) < 0.01)
    ok("o medido continua guardado, para a tela poder mostrar os dois",
       _r["myrella"]["ocio_medido_min"] == 2772.0
       and _r["myrella"]["pct_medido"] == 30.0)
    ok("a marca de ajustado viaja junto", _r["myrella"]["ajustado"] is True)
    # Quem ja estava melhor que 5% tambem vai para 5%: foi o que o gestor
    # pediu — "reduzir a ociosidade de todos para 5%" —, e o acordo e do mes,
    # nao de cada pessoa.
    ok("quem estava abaixo tambem fica no valor do acordo",
       _r["gabriel"]["pct_ocioso"] == 5.0)

    ok("o original nao e tocado",
       _med["myrella"]["pct_ocioso"] == 30.0
       and _med["myrella"]["ociosidade_min"] == 2772.0)

    ok("outro mes nao e afetado",
       aplicar(_med, 2026, 10, _aj)["myrella"]["pct_ocioso"] == 30.0)
    ok("sem ajuste nenhum devolve o proprio resultado",
       aplicar(_med, 2026, 9, {}) is _med and aplicar(_med, 2026, 9, None) is _med)
    ok("pessoa fora da lista fica como estava",
       aplicar(_med, 2026, 9, {"2026-09": {"myrella": 5}})["gabriel"]["pct_ocioso"] == 3.0)
    ok("resultado vazio nao derruba", aplicar({}, 2026, 9, _aj) == {})
    ok("sem horas disponiveis, 5% de nada e zero",
       aplicar({"x": {"horas_disp_min": 0, "ociosidade_min": 0,
                      "pct_ocioso": 0}}, 2026, 9,
               {"2026-09": {"x": 5}})["x"]["ociosidade_min"] == 0.0)

    ok("o mes vira texto com zero a esquerda", mes_texto(2026, 9) == "2026-09")
    ok("percentual com virgula e lido", _num("5,5") == 5.5)
    ok("percentual com % e lido", _num("5%") == 5.0)
    ok("texto sem numero nao vira ajuste", _num("") == 0.0 and _num(None) == 0.0)

    print("\nfalhas:", falhas)
