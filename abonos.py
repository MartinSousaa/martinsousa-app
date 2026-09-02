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

O abono vale para a equipe inteira: os eventos que ele existe para cobrir são
do escritório, não de uma pessoa.

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

import streamlit as st

ABA_NOME = "abonos"
# data_fim e tipo entraram depois. Linha antiga, sem eles, vale como um dia so
# do tipo "parada" — que e exatamente o que ela era.
COLUNAS = ["data", "data_fim", "inicio", "fim", "motivo", "tipo"]

TIPO_PARADA = "parada"
TIPO_PERIODO = "periodo"
DIA_INTEIRO = (time(0, 0), time(23, 59))


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
        return planilha.worksheet(ABA_NOME)
    except Exception:
        aba = planilha.add_worksheet(title=ABA_NOME, rows=300,
                                     cols=len(COLUNAS))
        aba.append_row(COLUNAS, value_input_option="RAW")
        return aba


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
    for r in linhas:
        d = _data(r.get("data"))
        ini = _hhmm(r.get("inicio"), DIA_INTEIRO[0])
        fim = _hhmm(r.get("fim"), DIA_INTEIRO[1])
        if not d or fim <= ini:
            continue
        fora.append({
            "data": d,
            # Sem data_fim a linha e de um dia so. E o formato antigo, e ele
            # continua valendo sem conversao nenhuma.
            "data_fim": _data(r.get("data_fim")) or d,
            "inicio": ini, "fim": fim,
            "motivo": str(r.get("motivo") or "").strip(),
            "tipo": (str(r.get("tipo") or "").strip().lower()
                     or TIPO_PARADA),
        })
    fora.sort(key=lambda a: (a["data"], a["inicio"]), reverse=True)
    return fora


def salvar(data, inicio, fim, motivo, data_fim=None, tipo=TIPO_PARADA):
    """Acrescenta um abono. Devolve (ok, mensagem)."""
    data_fim = data_fim or data
    if fim <= inicio:
        return False, "A hora final tem que ser depois da inicial."
    if data_fim < data:
        return False, "A data final tem que ser igual ou depois da inicial."
    try:
        _aba().append_row(
            [data.strftime("%Y-%m-%d"), data_fim.strftime("%Y-%m-%d"),
             inicio.strftime("%H:%M"), fim.strftime("%H:%M"),
             str(motivo or "").strip(), tipo],
            value_input_option="RAW")
        carregar.clear()
        return True, ""
    except Exception as e:
        return False, str(e)[:200]


def remover(data, inicio):
    """Apaga o abono daquela data e hora. Devolve (ok, mensagem)."""
    try:
        aba = _aba()
        alvo_d, alvo_h = data.strftime("%Y-%m-%d"), inicio.strftime("%H:%M")
        for i, r in enumerate(aba.get_all_records(), start=2):
            if (_data(r.get("data")) == data
                    and _hhmm(r.get("inicio")) == inicio):
                aba.delete_rows(i)
                carregar.clear()
                return True, ""
        return False, "Abono não encontrado."
    except Exception as e:
        return False, str(e)[:200]


def janelas_do_dia(dia, fuso, lista=None):
    """[(inicio, fim)] dos abonos que alcançam aquele dia, no fuso pedido.

    Um período de férias coletivas é uma linha só e vale para cada dia dentro
    dela — por isso a comparação é de faixa, e não de igualdade.
    """
    return [(datetime.combine(dia, a["inicio"], tzinfo=fuso),
             datetime.combine(dia, a["fim"], tzinfo=fuso))
            for a in (carregar() if lista is None else lista)
            if a["data"] <= dia <= a["data_fim"]]


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
