# -*- coding: utf-8 -*-
"""Conferência de fechar_expediente.py, com RHiD, Trello e planilha de mentira.

    python3 fechar_expediente_conferencia.py

Onze casos, e o que eles guardam são as TRAVAS: o ambiente de teste que não
pode escrever no board real, o cartão que já tem a etiqueta, o board sem a
etiqueta, a RHiD muda. Cada um deles, se quebrar, quebra em silêncio — a tarefa
roda sozinha, de madrugada, sem ninguém olhando a saída.

O `agora` é fixado em cada caso de propósito: sem isso, "ainda dentro do
expediente" só passava se a máquina que roda o teste estivesse ela própria
dentro do expediente, e o container onde isto foi escrito trabalha em UTC.
"""
import sys, types, datetime as dt, io
sys.path.insert(0, __import__('os').path.dirname(__file__) or '.')

HOJE = dt.date.today()
POSTS = []

# A tarefa monta o secrets.toml a partir do ambiente antes de qualquer coisa.
# Sem esta variavel ela aborta -- corretamente -- e os casos abaixo nem chegam a
# rodar. Um bloco minimo basta: nada aqui usa credencial de verdade.
import os
os.environ.setdefault("STREAMLIT_SECRETS", '[trello]\nkey = "conferencia"\n')

def montar(ambiente="producao", saida_my="17:45", tem_label=True,
           labels_do_cartao=None, post_ok=True, pessoas_rhid=True,
           dia_util=True, dois_cartoes=False):
    POSTS.clear()

    plan = types.ModuleType("planilha")
    plan.eh_homologacao = lambda: ambiente != "producao"
    plan.ambiente = lambda: ambiente
    sys.modules["planilha"] = plan

    rhid = types.ModuleType("rhid_api")
    rhid.get_persons = lambda: ([{"id": 7, "name": "Myrella de Souza", "status": "1"}]
                                if pessoas_rhid else [])
    rhid.get_registros_diarios = lambda a, b, c: (
        [{"data": HOJE, "saida": saida_my}], {})
    sys.modules["rhid_api"] = rhid

    rp = types.ModuleType("relogio_ponto")
    rp._rhid_nome_para_trello = lambda n: "myrelladesouza" if n else None
    sys.modules["relogio_ponto"] = rp

    pc = types.ModuleType("placar_core")
    pc.LABELS_TRABALHO = {"EM ANDAMENTO", "FILMAGEM"}
    pc.LABEL_FIM_EXPEDIENTE = "FIM DE EXPEDIENTE"
    pc.TRELLO_KEY, pc.TRELLO_TOKEN = "k", "t"
    pc.recarregar_membros = lambda: None
    pc.horario_de = lambda u: {"entrada": dt.time(8, 45), "fim": dt.time(17, 45)}
    pc.eh_dia_util = lambda d: dia_util
    pc.mapa_labels = lambda forcar=False: ({"lb1": "FIM DE EXPEDIENTE"} if tem_label else {"lb9": "OUTRA"})
    _lbs = labels_do_cartao if labels_do_cartao is not None else ["EM ANDAMENTO"]
    # O que os avisos do instante (`alertas_trello`) leem do mesmo módulo.
    pc.LABELS_INTERRUPCAO = {"INTERROMPIDO", "INTERROMPIDO MS", "FIM DE EXPEDIENTE"}
    pc.MEMBROS_ATIVOS = {"myrelladesouza": "Myrella"}
    pc.FUSO = dt.timezone(dt.timedelta(hours=-3))
    pc.GRACA_ENTRE_MIN = 5
    _cards = [{"id": "card1", "name": "excluindo notas bling", "idList": "L1",
               "idMembers": ["m1"], "labels": [{"name": l} for l in _lbs]}]
    if dois_cartoes:
        _cards.append({"id": "card2", "name": "descrição caneca", "idList": "L1",
                       "idMembers": ["m1"], "labels": [{"name": "EM ANDAMENTO"}]})
    pc._buscar_board = lambda: (
        {"L1": "PRODUÇÃO"}, _cards, {"m1": "myrelladesouza"}, None, None, None)
    sys.modules["placar_core"] = pc

    # Batidas e planilha dos avisos: sem expediente aberto e sem estado
    # guardado — o que se mede aqui são as duas demandas.
    bat = types.ModuleType("batidas")
    bat.mapa = lambda *a, **k: {}
    bat.janelas_do_dia = lambda *a, **k: []
    sys.modules["batidas"] = bat
    sh = types.ModuleType("sheets")
    def _sem_planilha():
        raise RuntimeError("sem planilha na conferência")
    sh.planilha = _sem_planilha
    sys.modules["sheets"] = sh

    req = types.ModuleType("requests")
    class R:
        ok = post_ok; status_code = 200 if post_ok else 401
    def post(url, params=None, timeout=None):
        POSTS.append((url, params))
        return R()
    req.post = post
    sys.modules["requests"] = req

    for m in ("fim_expediente", "fechar_expediente", "meu_desempenho", "alertas_trello"):
        sys.modules.pop(m, None)
    import fechar_expediente as fx
    return fx

def rodar(titulo, esperado_posts, **kw):
    simular = kw.pop("simular", False)
    agora = kw.pop("agora", dt.datetime.combine(HOJE, dt.time(18, 30)))
    fx = montar(**kw)
    buf = io.StringIO(); antes = sys.stdout; sys.stdout = buf
    try:
        cod = fx.main(simular=simular, agora=agora)
    finally:
        sys.stdout = antes
    ok = len(POSTS) == esperado_posts
    print(("ok    " if ok else "FALHA ") + titulo + f"  (posts={len(POSTS)}, saida={cod})")
    for l in buf.getvalue().strip().split("\n"):
        if l.strip(): print("        " + l.split("] ", 1)[-1])
    return ok

def _as(h, m=0):
    return dt.datetime.combine(HOJE, dt.time(h, m))

f = 0
# A regra do dono (23/10): 18h30, todo cartao EM ANDAMENTO; fim de semana e
# feriado, a qualquer hora. A RHiD nao entra: os dois ultimos casos provam que
# ela pode estar muda sem que nenhum cartao deixe de fechar.
f += not rodar("18h30 em ponto: o cartao aberto fecha", 1, agora=_as(18, 30))
f += not rodar("18h29: ainda nao", 0, agora=_as(18, 29))
f += not rodar("11h de dia util: nao fecha", 0, agora=_as(11, 0))
f += not rodar("sabado de manha: fecha", 1, agora=_as(9, 0), dia_util=False)
f += not rodar("simulacao nao escreve nada", 0, simular=True)
f += not rodar("AMBIENTE DE TESTE nao escreve no board real", 0, ambiente="homologacao")
f += not rodar("cartao que ja tem a etiqueta e pulado", 0,
               labels_do_cartao=["EM ANDAMENTO", "FIM DE EXPEDIENTE"])
f += not rodar("cartao sem etiqueta de trabalho nao e tocado", 0,
               labels_do_cartao=["PENDENTE"])
f += not rodar("board sem a etiqueta: aborta", 0, tem_label=False)
f += not rodar("RHiD sem ninguem: fecha do mesmo jeito", 1, pessoas_rhid=False)
f += not rodar("sem batida de saida: fecha do mesmo jeito", 1, saida_my=None)
f += not rodar("POST recusado pelo Trello e reportado", 1, post_ok=False)
# Os avisos do instante viajam na mesma rotina: às 11h, duas demandas abertas
# da mesma pessoa viram UM comentário no cartão — e nenhuma etiqueta.
f += not rodar("11h, duas demandas: um aviso no cartão, nenhuma etiqueta", 1,
               dois_cartoes=True, agora=_as(11, 0))
f += not (POSTS and POSTS[-1][0].endswith("/actions/comments")
          and "@myrelladesouza" in POSTS[-1][1]["text"])
print("\nfalhas:", f)
if POSTS:
    print("ultimo POST:", POSTS[-1][0])
raise SystemExit(1 if f else 0)
