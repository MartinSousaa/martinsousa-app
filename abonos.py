"""
abonos.py — Horas que não contam para ninguém, e por quê.

Queda de internet, falta de energia, prédio sem acesso: o trabalho para, mas os
indicadores não. O cartão continua acumulando tempo com a etiqueta EM ANDAMENTO,
a ociosidade sobe porque ninguém está executando nada, e o atraso chega pelo
tempo estimado da coluna. A equipe é cobrada por uma hora que não foi dela.

O abono é um trecho de tempo, com data, hora e motivo, que sai da conta.

Por que UM lugar só conserta os três indicadores
------------------------------------------------
Tanto o relógio do cartão quanto a ociosidade partem de "janelas" — os pedaços
do dia em que se espera trabalho. Descontando o abono das janelas, some junto:

  tempo do cartão   -> não corre durante o abono, então o atraso por tempo
                       estimado deixa de acontecer
  ociosidade        -> a hora parada não entra no denominador nem no buraco
  tempo de execução -> cai pelo mesmo motivo do primeiro

Descontar em cada indicador separadamente daria três contas para manter em
acordo — e é assim que duas telas passam a discordar.

Dois donos, porque são duas origens
-----------------------------------
Sem dono, o abono vale para a equipe inteira — é o caso original, o evento do
escritório. Com dono, vale só para uma pessoa: é o PEDIDO DE ABATIMENTO, onde
o colaborador conta o trabalho que fez e o sistema não viu (filmou sem a
etiqueta FILMAGEM, analisou a demanda sem abrir o cartão). Aquilo virava
ociosidade dela, e o indicador estava certo — ele mede o que o Trello viu.

O pedido nasce PENDENTE e não muda indicador nenhum enquanto ninguém decidir;
só o APROVADO desconta. O gestor pode aprovar menos do que foi pedido: quem
manda escreve o horário de memória, quem confere tem o cartão e a câmera.
Recusa não apaga a linha — sem ver a decisão e o porquê, a pessoa manda o
mesmo pedido de novo na semana seguinte.

Dois tipos, porque são dois momentos diferentes
-----------------------------------------------
  parada     lançada DEPOIS. A internet caiu das 9h às 11h e você registra ao
             fim. Um dia, com hora de início e fim.
  periodo    lançado ANTES. Emenda de feriado, férias coletivas, feriado
             regional. Uma faixa de datas, dia inteiro.

A conta é a mesma para os dois: hora que sai da janela de trabalho. O que muda
é a forma de preencher.
"""

from datetime import datetime, time, timedelta

import gspread
import streamlit as st

ABA_NOME = "abonos"
# data_fim e tipo entraram depois; user, status e o rastro da decisao entraram
# junto com o pedido da equipe. Linha antiga, sem nada disso, vale como um dia
# so, do tipo "parada", da equipe inteira e ja aprovada — que e exatamente o
# que ela era.
COLUNAS = ["data", "data_fim", "inicio", "fim", "motivo", "tipo",
           "user", "status", "criado_em", "decidido_por", "decidido_em", "obs"]

TIPO_PARADA = "parada"
TIPO_PERIODO = "periodo"
DIA_INTEIRO = (time(0, 0), time(23, 59))

# O ciclo do pedido. Lancamento do gestor nasce APROVADO — ele e a propria
# aprovacao. Pedido da equipe nasce pendente e so desconta quando alguem decide.
PENDENTE = "pendente"
APROVADO = "aprovado"
RECUSADO = "recusado"

# Abono sem dono vale para a equipe inteira: e o caso que ele foi feito para
# cobrir, a queda de energia do escritorio. Com dono, vale so para uma pessoa.
TODOS = ""


def _crono(rotulo, seg, detalhe=""):
    try:
        import cronometro
        cronometro.marcar(rotulo, seg, detalhe)
    except Exception:
        pass


@st.cache_resource
def _aba():
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        aba = planilha.worksheet(ABA_NOME)
    except Exception:
        aba = planilha.add_worksheet(title=ABA_NOME, rows=300,
                                     cols=len(COLUNAS))
        aba.append_row(COLUNAS, value_input_option="RAW")
        return aba
    _completar_cabecalho(aba)
    return aba


def _completar_cabecalho(aba):
    """Põe no cabeçalho as colunas que entraram depois que a aba nasceu.

    A aba de produção foi criada com seis colunas. Gravar `user` e `status` sem
    escrever o cabeçalho primeiro daria uma linha com valores em células que
    `get_all_records()` não sabe nomear: o pedido seria salvo e lido como abono
    da equipe inteira, já aprovado — o contrário do que ele é.

    Roda uma vez por sessão, junto com o cache da aba, e não faz nada quando o
    cabeçalho já está completo.
    """
    try:
        atual = aba.row_values(1) or []
        if len(atual) >= len(COLUNAS) and atual[:len(COLUNAS)] == COLUNAS:
            return
        faltam = [c for c in COLUNAS if c not in atual]
        if not faltam:
            return
        if aba.col_count < len(atual) + len(faltam):
            aba.add_cols(len(atual) + len(faltam) - aba.col_count)
        aba.update(
            values=[atual + faltam],
            range_name=f"A1:{gspread.utils.rowcol_to_a1(1, len(atual) + len(faltam))}",
            value_input_option="RAW")
    except Exception:
        # Cabecalho e conveniencia: sem ele o pedido nao grava direito, e
        # `salvar` ja devolve o erro para a tela. Derrubar a pagina inteira
        # aqui seria pior.
        pass


def _hhmm(texto, padrao=None):
    """'09:30' -> time(9, 30). Devolve `padrao` quando não dá para ler."""
    try:
        h, m = str(texto).strip().split(":")[:2]
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return padrao


def _data(texto):
    """Aceita '2026-09-02' e '02/09/2026'. None quando não dá para ler."""
    t = str(texto or "").strip()
    for forma in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(t, forma).date()
        except ValueError:
            continue
    return None


@st.cache_data(ttl=300)
def carregar():
    """[{'data': date, 'inicio': time, 'fim': time, 'motivo': str}].

    Vazio em qualquer falha: sem abono, os indicadores voltam a ser o que são
    hoje. Abono que não carrega não pode virar hora abonada por engano.
    """
    try:
        import time as _t
        _t0 = _t.perf_counter()
        linhas = _aba().get_all_records()
        _crono("Planilha: abonos", _t.perf_counter() - _t0, f"{len(linhas)} linhas")
    except Exception:
        return []

    fora = []
    for i, r in enumerate(linhas, start=2):   # 2: a linha 1 e o cabecalho
        d = _data(r.get("data"))
        ini = _hhmm(r.get("inicio"), DIA_INTEIRO[0])
        fim = _hhmm(r.get("fim"), DIA_INTEIRO[1])
        if not d or fim <= ini:
            continue
        fora.append({
            "linha": i,
            "data": d,
            # Sem data_fim a linha e de um dia so. E o formato antigo, e ele
            # continua valendo sem conversao nenhuma.
            "data_fim": _data(r.get("data_fim")) or d,
            "inicio": ini, "fim": fim,
            "motivo": str(r.get("motivo") or "").strip(),
            "tipo": (str(r.get("tipo") or "").strip().lower()
                     or TIPO_PARADA),
            "user": str(r.get("user") or "").strip(),
            # Linha sem status e do tempo em que so o gestor lancava: ela ja
            # valia, e continua valendo. Ler como pendente apagaria abono
            # antigo do calculo sem ninguem pedir.
            "status": (str(r.get("status") or "").strip().lower() or APROVADO),
            "criado_em": str(r.get("criado_em") or "").strip(),
            "decidido_por": str(r.get("decidido_por") or "").strip(),
            "decidido_em": str(r.get("decidido_em") or "").strip(),
            "obs": str(r.get("obs") or "").strip(),
        })
    fora.sort(key=lambda a: (a["data"], a["inicio"]), reverse=True)
    return fora


def _cabecalho(aba):
    """A ordem REAL das colunas na planilha, não a de COLUNAS.

    A aba foi ganhando colunas ao longo do tempo, e o cabeçalho de uma planilha
    antiga pode não estar na ordem em que COLUNAS está hoje. Gravar por posição
    fixa escreveria o status na coluna do motivo.
    """
    try:
        atual = [c for c in (aba.row_values(1) or []) if c]
    except Exception:
        atual = []
    return atual or list(COLUNAS)


def _agora():
    """Carimbo de data e hora em Brasília, para o rastro da decisão."""
    from datetime import timezone, timedelta
    return datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M")


def salvar(data, inicio, fim, motivo, data_fim=None, tipo=TIPO_PARADA,
           user=TODOS, status=APROVADO):
    """Acrescenta um abono. Devolve (ok, mensagem).

    O lançamento do gestor nasce aprovado — ele é a própria aprovação. O pedido
    da equipe chega com user preenchido e status pendente, e não muda nenhum
    indicador enquanto ninguém decidir.
    """
    data_fim = data_fim or data
    if fim <= inicio:
        return False, "A hora final tem que ser depois da inicial."
    if data_fim < data:
        return False, "A data final tem que ser igual ou depois da inicial."
    if not str(motivo or "").strip():
        return False, "Escreva o que você estava fazendo nesse horário."
    valores = {
        "data": data.strftime("%Y-%m-%d"),
        "data_fim": data_fim.strftime("%Y-%m-%d"),
        "inicio": inicio.strftime("%H:%M"), "fim": fim.strftime("%H:%M"),
        "motivo": str(motivo or "").strip(), "tipo": tipo,
        "user": str(user or ""), "status": status, "criado_em": _agora(),
        "decidido_por": "", "decidido_em": "", "obs": "",
    }
    try:
        aba = _aba()
        aba.append_row([valores.get(c, "") for c in _cabecalho(aba)],
                       value_input_option="RAW")
        carregar.clear()
        return True, ""
    except Exception as e:
        return False, str(e)[:200]


def _escrever(linha, valores):
    """{coluna: valor} numa linha já existente. Devolve (ok, mensagem)."""
    try:
        aba = _aba()
        ordem = _cabecalho(aba)
        for nome, valor in valores.items():
            if nome not in ordem:
                continue
            aba.update_cell(int(linha), ordem.index(nome) + 1, valor)
        carregar.clear()
        return True, ""
    except Exception as e:
        return False, str(e)[:200]


def aprovar(linha, quem, inicio=None, fim=None, obs=""):
    """Aprova o pedido daquela linha, com o horário que o gestor decidir.

    O gestor pode aprovar menos do que foi pedido — o colaborador chuta o
    horário de memória, e quem confere tem o cartão e a câmera. Passar
    inicio/fim reescreve o trecho antes de aprovar.
    """
    campos = {"status": APROVADO, "decidido_por": str(quem or ""),
              "decidido_em": _agora(), "obs": str(obs or "").strip()}
    if inicio is not None and fim is not None:
        if fim <= inicio:
            return False, "A hora final tem que ser depois da inicial."
        campos["inicio"] = inicio.strftime("%H:%M")
        campos["fim"] = fim.strftime("%H:%M")
    return _escrever(linha, campos)


def recusar(linha, quem, obs=""):
    """Recusa o pedido daquela linha. A linha fica, com o motivo da recusa.

    Apagar seria mais simples e seria pior: o colaborador precisa ver que o
    pedido foi visto e por que não passou, senão manda de novo.
    """
    return _escrever(linha, {"status": RECUSADO, "decidido_por": str(quem or ""),
                             "decidido_em": _agora(),
                             "obs": str(obs or "").strip()})


def remover(data, inicio):
    """Apaga o abono daquela data e hora. Devolve (ok, mensagem)."""
    try:
        aba = _aba()
        for i, r in enumerate(aba.get_all_records(), start=2):
            if (_data(r.get("data")) == data
                    and _hhmm(r.get("inicio")) == inicio):
                aba.delete_rows(i)
                carregar.clear()
                return True, ""
        return False, "Abono não encontrado."
    except Exception as e:
        return False, str(e)[:200]


def remover_linha(linha):
    """Apaga a linha exata. Devolve (ok, mensagem).

    Dois pedidos do mesmo dia e da mesma hora, de pessoas diferentes, são
    normais — `remover` acharia o primeiro dos dois.
    """
    try:
        _aba().delete_rows(int(linha))
        carregar.clear()
        return True, ""
    except Exception as e:
        return False, str(e)[:200]


def pendentes(lista=None):
    """Os pedidos esperando decisão, do mais antigo para o mais novo.

    Fila do gestor: quem esperou mais aparece primeiro.
    """
    fila = [a for a in (carregar() if lista is None else lista)
            if a["status"] == PENDENTE]
    fila.sort(key=lambda a: (a["data"], a["inicio"]))
    return fila


def do_usuario(username, lista=None):
    """Tudo que aquela pessoa pediu, do mais novo para o mais velho."""
    u = str(username or "").strip().lower()
    return [a for a in (carregar() if lista is None else lista)
            if a["user"].lower() == u]


def janelas_do_dia(dia, fuso, lista=None, username=None):
    """[(inicio, fim)] dos abonos que alcançam aquele dia, no fuso pedido.

    Um período de férias coletivas é uma linha só e vale para cada dia dentro
    dela — por isso a comparação é de faixa, e não de igualdade.

    Só o APROVADO desconta. Pedido pendente que já saísse da conta faria o
    indicador melhorar sozinho no instante do envio, e a aprovação do gestor
    viraria enfeite.

    Abono sem dono é do escritório e vale para todo mundo. Com dono, vale só
    para a pessoa: a Beatriz esquecer de abrir o cartão não pode abonar a
    ociosidade do Gabriel. Sem `username`, só os da equipe inteira entram —
    quem pergunta "quanto o time parou" não quer o esquecimento de ninguém.
    """
    u = str(username or "").strip().lower()
    fora = []
    for a in (carregar() if lista is None else lista):
        if a["status"] != APROVADO:
            continue
        if a["user"] and a["user"].lower() != u:
            continue
        if not (a["data"] <= dia <= a["data_fim"]):
            continue
        fora.append((datetime.combine(dia, a["inicio"], tzinfo=fuso),
                     datetime.combine(dia, a["fim"], tzinfo=fuso)))
    return fora


def descontar(janelas, abonos):
    """Tira os trechos abonados de uma lista de janelas de trabalho.

    Uma janela partida ao meio por um abono vira duas. Janela inteiramente
    dentro do abono desaparece. É a mesma conta de `_buracos`, do outro lado.
    """
    if not abonos:
        return list(janelas)
    fora = []
    for ini, fim in janelas:
        pedacos = [(ini, fim)]
        for a_ini, a_fim in abonos:
            novos = []
            for s, e in pedacos:
                if a_fim <= s or a_ini >= e:      # não se tocam
                    novos.append((s, e))
                    continue
                if a_ini > s:
                    novos.append((s, a_ini))
                if a_fim < e:
                    novos.append((a_fim, e))
            pedacos = novos
        fora.extend(pedacos)
    return fora
