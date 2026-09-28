"""placar_snapshot.py — o retrato diário do placar.

POR QUE ELE EXISTE
------------------
28/09: *"na sexta a meta coletiva estava em 102% e agora está em 98%. Quais
cartões somaram e quais subtraíram?"*

**O Studio não tinha como responder.** Ele lê o Trello AO VIVO: sabe quanto o
quadro vale agora e nada sobre ontem. Os 102% de sexta não existiam em lugar
nenhum — nem em arquivo, nem em planilha, nem em cache. A única saída era
reconstruir a queda a partir do log do Trello, adivinhando o valor dos
cartões que já não estão lá.

Este módulo tira uma foto por dia. A partir dela a pergunta deixa de ser
investigação e vira SUBTRAÇÃO: o cartão X somava 80 na sexta e não soma hoje.

UMA LINHA POR DIA, E NÃO UMA POR CARTÃO
---------------------------------------
Uma linha por cartão por dia seriam ~200 linhas/dia — 6 mil por mês, e a aba
fica impossível de abrir. Uma linha por dia com o mapa `id:pontos` compactado
numa célula dá 365 linhas por ano, e a diferença entre dois dias sai exata do
mesmo jeito.

ELE NÃO REESCREVE O PASSADO
---------------------------
Grava no máximo uma vez por dia, e nunca por cima de um dia já gravado. Se o
retrato de hoje pudesse ser reescrito às 18h, a comparação com amanhã mediria
o fim do dia contra o começo do outro — e a queda apareceria onde não houve.
"""

import json
from datetime import datetime

ABA = "placar_diario"
COLUNAS = ["data", "pts_equipe", "pen_total", "saldo", "meta", "pct", "cartoes"]


def linha(d, meta, quando):
    """O retrato de um dia, pronto para virar linha da planilha.

    `d` é o dicionário que `_processar` devolve; `cards_pts` é a lista de
    cartões que somaram, que ele passou a guardar junto com o total.
    """
    pts = float((d or {}).get("pts_equipe") or 0.0)
    pen = float((d or {}).get("pen_total") or 0.0)
    saldo = pts - pen
    meta = float(meta or 0)
    mapa = {}
    for c in ((d or {}).get("cards_pts") or []):
        cid = c.get("id")
        if cid:
            mapa[cid] = c.get("pts")
    return {
        "data": quando.strftime("%Y-%m-%d"),
        "pts_equipe": round(pts, 2),
        "pen_total": round(pen, 2),
        "saldo": round(saldo, 2),
        "meta": round(meta, 2),
        "pct": round(saldo / meta * 100, 2) if meta > 0 else 0.0,
        # Só o mapa id→pontos. O NOME do cartão não entra: ele muda, e o que
        # identifica o cartão é o id. Os nomes de hoje vêm do quadro atual.
        "cartoes": json.dumps(mapa, separators=(",", ":")),
    }


def _mapa(linha_dia):
    """O mapa id→pontos de uma linha lida da planilha. {} quando ilegível."""
    try:
        m = json.loads((linha_dia or {}).get("cartoes") or "{}")
        return m if isinstance(m, dict) else {}
    except (ValueError, TypeError):
        return {}


def comparar(antes, depois, nomes=None):
    """O que mudou entre dois retratos. Devolve a lista de diferenças.

    `nomes` é {id: nome} do quadro de HOJE. Cartão que saiu não está mais lá,
    então o nome vem vazio — e não inventado.

    Cada item traz `delta`: o quanto aquele cartão mexeu no total. A soma dos
    deltas é EXATAMENTE a diferença entre os dois saldos, e é isso que
    transforma a investigação em subtração.
    """
    a, b = _mapa(antes), _mapa(depois)
    nomes = nomes or {}
    fora = []
    for cid in sorted(set(a) | set(b)):
        va, vb = a.get(cid), b.get(cid)
        if va == vb:
            continue
        if va is None:
            o_que, delta = "passou a somar", float(vb or 0)
        elif vb is None:
            o_que, delta = "deixou de somar", -float(va or 0)
        else:
            o_que, delta = "mudou de valor", float(vb or 0) - float(va or 0)
        fora.append({"id": cid, "cartao": nomes.get(cid, ""), "o_que": o_que,
                     "antes": va, "depois": vb, "delta": round(delta, 2)})
    # O que mais mexeu primeiro, em módulo: quem lê quer a causa no topo.
    return sorted(fora, key=lambda x: -abs(x["delta"]))


def confere(antes, depois, diffs):
    """A soma dos deltas bate com a diferença dos saldos?

    Se não bater, a explicação está INCOMPLETA — e dizer isso é melhor que
    mostrar uma lista que não fecha e deixar quem lê achar que fechou.
    """
    try:
        d_saldo = float(depois.get("pts_equipe") or 0) - float(depois.get("pen_total") or 0) \
                - float(antes.get("pts_equipe") or 0) + float(antes.get("pen_total") or 0)
    except (TypeError, ValueError):
        return None
    soma = sum(x["delta"] for x in (diffs or []))
    # A penalidade nao esta no mapa de cartoes: ela entra pelo pen_total. A
    # diferenca entre as duas contas E o efeito das penalidades no periodo.
    return round(d_saldo, 2), round(soma, 2), round(d_saldo - soma, 2)


# ── A planilha ───────────────────────────────────────────────────────────────
# Só daqui para baixo se fala com a rede. As funções acima são puras, e é por
# isso que a conferência alcança todas elas.

def _aba():
    """A aba do retrato diário, criada no primeiro uso."""
    import gspread
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        return planilha.worksheet(ABA)
    except gspread.exceptions.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA, rows=800, cols=len(COLUNAS))
        aba.append_row(COLUNAS, value_input_option="RAW")
        return aba


def ler(aba=None):
    """Os retratos já gravados, do mais antigo para o mais novo."""
    try:
        return (aba or _aba()).get_all_records()
    except Exception:
        # Ler o histórico nunca pode derrubar o Painel de Metas. Sem retrato,
        # a tela diz que não há — que é a verdade.
        return []


# O dia do último retrato deste processo. A thread da TV chama `gravar` a
# cada volta — de minuto em minuto —, e sem esta memória cada volta faria uma
# leitura da planilha: ~1.400 por dia para descobrir 1.399 vezes que o dia já
# estava gravado. `st.session_state` não serve: a thread da TV roda fora de
# qualquer sessão Streamlit e não consegue lê-lo.
_ULTIMO_DIA = {"data": "", "anterior": None}


def _memoria_limpar():
    """Esquece o último dia gravado. Existe para a conferência."""
    _ULTIMO_DIA["data"] = ""
    _ULTIMO_DIA["anterior"] = None


def variacao(saldo_hoje):
    """Quanto o saldo mudou desde o retrato anterior. None quando não há um.

    É O QUE SERVE NA TV. Uma tabela de 200 cartões não se lê de longe; a
    variação sim — "4.900 pts, −200 desde 25/09".

    Não faz leitura nenhuma: usa o retrato anterior que `gravar` guardou na
    leitura do dia. A TV redesenha de minuto em minuto, e uma consulta à
    planilha por volta seria 1.400 por dia para mostrar o mesmo número.
    """
    ant = _ULTIMO_DIA.get("anterior")
    if not ant:
        return None
    try:
        antes = float(ant.get("saldo") or 0)
    except (TypeError, ValueError):
        return None
    return {"desde": str(ant.get("data") or ""),
            "antes": antes,
            "delta": round(float(saldo_hoje or 0) - antes, 2)}


def gravar(d, meta, quando=None, aba=None, filtro_mes=None):
    """Grava o retrato de hoje. Devolve o que aconteceu, em uma palavra.

    NUNCA POR CIMA DE UM DIA JÁ GRAVADO. Se o retrato pudesse ser reescrito
    às 18h, a comparação com amanhã mediria o fim de um dia contra o começo
    do outro, e a queda apareceria onde não houve. O primeiro da manhã fica.

    `filtro_mes` é o mês que a tela está MOSTRANDO. O master pode estar
    olhando agosto no seletor, e gravar os números de agosto como o retrato
    de hoje faria a comparação de amanhã acusar uma queda de mês inteiro que
    nunca houve.
    """
    quando = quando or datetime.now()
    if filtro_mes and tuple(filtro_mes) != (quando.year, quando.month):
        return "mes_errado"
    nova = linha(d, meta, quando)
    if _ULTIMO_DIA["data"] == nova["data"]:
        return "ja_existe"
    try:
        ab = aba or _aba()
        ja_gravados = ler(ab)
        # O retrato ANTERIOR sai desta mesma leitura, de graça. É ele que a
        # TV usa para mostrar a variação sem consultar a planilha de novo.
        anteriores = [r for r in ja_gravados
                      if str(r.get("data") or "") < nova["data"]]
        _ULTIMO_DIA["anterior"] = (
            sorted(anteriores, key=lambda r: str(r.get("data")))[-1]
            if anteriores else None)
        for ja in ja_gravados:
            if str(ja.get("data") or "") == nova["data"]:
                _ULTIMO_DIA["data"] = nova["data"]
                return "ja_existe"
        ab.append_row([nova[c] for c in COLUNAS], value_input_option="RAW")
        _ULTIMO_DIA["data"] = nova["data"]
        return "gravado"
    except Exception:
        # Uma falha de planilha não pode derrubar a tela nem a thread da TV.
        # A memória NÃO é marcada: a próxima volta tenta de novo.
        return "falhou"


# ── Conferência ──────────────────────────────────────────────────────────────
# `python3 placar_snapshot.py`. Tudo acima é função pura sobre dicionários —
# a parte que fala com a planilha fica embaixo, e não é conferida aqui.
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    SEX = datetime(2026, 9, 25, 18, 0)
    # OS CARTOES SOMAM O TOTAL — como na realidade. A primeira versao deste
    # teste punha tres cartoes de 80/100/30 ao lado de um pts_equipe de 5100,
    # e `confere` reprovou com razao: a conta nao fechava. Dado de teste mais
    # pobre que o real acusa o inocente.
    _d_sex = {"pts_equipe": 5100.0, "pen_total": 0.0,
              "cards_pts": [{"id": "a", "pts": 4600}, {"id": "b", "pts": 300},
                            {"id": "c", "pts": 200}]}
    _l_sex = linha(_d_sex, 5000, SEX)
    ok("o retrato traz a data do dia", _l_sex["data"] == "2026-09-25")
    ok("e a porcentagem da meta", _l_sex["pct"] == 102.0)
    ok("o saldo desconta a penalidade",
       linha({"pts_equipe": 5100.0, "pen_total": 200.0}, 5000, SEX)["saldo"] == 4900.0)

    # ── A SUBTRACAO, que e a razao do modulo existir ─────────────────────
    _d_seg = {"pts_equipe": 4900.0, "pen_total": 0.0,
              "cards_pts": [{"id": "a", "pts": 4600}, {"id": "c", "pts": 200},
                            {"id": "d", "pts": 100}]}
    _l_seg = linha(_d_seg, 5000, datetime(2026, 9, 28, 12, 0))
    ok("e a segunda ja vem com 98", _l_seg["pct"] == 98.0)
    _dif = comparar(_l_sex, _l_seg, {"a": "Álbum", "c": "Sino", "d": "Urso"})
    ok("o cartao que sumiu aparece",
       any(x["id"] == "b" and x["o_que"] == "deixou de somar" for x in _dif))
    ok("com o delta NEGATIVO do valor que ele tinha",
       next(x for x in _dif if x["id"] == "b")["delta"] == -300.0)
    ok("o cartao novo aparece somando",
       next(x for x in _dif if x["id"] == "d")["delta"] == 100.0)
    ok("o cartao que nao mudou fica de fora",
       not any(x["id"] == "a" for x in _dif))
    # NOME DE CARTAO QUE SUMIU VEM VAZIO: ele nao esta mais no quadro, e
    # inventar o nome e tao ruim quanto inventar o valor.
    ok("cartao que saiu vem sem nome, e nao com um inventado",
       next(x for x in _dif if x["id"] == "b")["cartao"] == "")
    ok("o que mais mexeu vem primeiro", _dif[0]["id"] == "b")

    # MUDANCA DE VALOR, que nao e nem entrada nem saida.
    _dif2 = comparar(linha({"cards_pts": [{"id": "x", "pts": 100}]}, 5000, SEX),
                     linha({"cards_pts": [{"id": "x", "pts": 40}]}, 5000, SEX))
    ok("mudar de valor tem nome proprio", _dif2[0]["o_que"] == "mudou de valor")
    ok("e o delta e a diferenca", _dif2[0]["delta"] == -60.0)

    # ── A CONTA TEM DE FECHAR ───────────────────────────────────────────
    # Lista que nao fecha com a diferenca dos saldos e explicacao PARCIAL.
    # Mostra-la sem dizer isso e pior que nao mostrar: quem le acha que
    # fechou e para de procurar.
    _c = confere(_l_sex, _l_seg, _dif)
    ok("a soma dos deltas bate com a diferenca dos saldos", _c[2] == 0.0)
    ok("e a diferenca dos saldos e -200", _c[0] == -200.0)
    # COM PENALIDADE a sobra e o efeito dela, e nao um erro.
    _l_pen = linha({"pts_equipe": 5100.0, "pen_total": 300.0,
                    "cards_pts": [{"id": "a", "pts": 4600}, {"id": "b", "pts": 300},
                                  {"id": "c", "pts": 200}]}, 5000, SEX)
    _c2 = confere(_l_sex, _l_pen, comparar(_l_sex, _l_pen))
    ok("a penalidade aparece como a sobra da conta", _c2[2] == -300.0)

    # ── BORDAS ──────────────────────────────────────────────────────────
    ok("retrato de dia sem cartao nenhum nao quebra",
       linha({}, 5000, SEX)["cartoes"] == "{}")
    ok("meta zero nao divide por zero", linha({}, 0, SEX)["pct"] == 0.0)
    ok("comparar dois vazios da lista vazia", comparar({}, {}) == [])
    ok("celula ilegivel nao derruba", _mapa({"cartoes": "{nao e json"}) == {})
    ok("celula vazia nao derruba", _mapa({}) == {} and _mapa(None) == {})
    ok("cartao sem id fica de fora do mapa",
       linha({"cards_pts": [{"pts": 10}]}, 5000, SEX)["cartoes"] == "{}")
    ok("confere com linha torta devolve None",
       confere({"pts_equipe": "x"}, _l_seg, []) is None)

    # A COLUNA `cartoes` E JSON, e tem de continuar cabendo numa celula.
    ok("o mapa de 200 cartoes cabe numa celula (50k)",
       len(linha({"cards_pts": [{"id": "a" * 24, "pts": 100}] * 200},
                 5000, SEX)["cartoes"]) < 50000)

    # ── A GRAVACAO, com um duplo no lugar da planilha ───────────────────
    #
    # So a PLANILHA e trocada. `gravar` continua rodando inteira: e a regra
    # de nao reescrever o dia que precisa ser conferida, nao o gspread.
    class _AbaFalsa:
        def __init__(self, linhas=None):
            self.linhas = list(linhas or [])
            self.escritas = 0

        def get_all_records(self):
            return list(self.linhas)

        def append_row(self, linha_l, **kw):
            self.escritas += 1
            self.linhas.append(dict(zip(COLUNAS, linha_l)))

    _ab = _AbaFalsa()
    ok("o primeiro retrato do dia e gravado",
       gravar(_d_sex, 5000, SEX, aba=_ab) == "gravado" and _ab.escritas == 1)
    # A THREAD DA TV CHAMA ISTO DE MINUTO EM MINUTO. Sem esta trava seriam
    # ~1.400 escritas por dia, e a comparacao mediria o fim de um dia contra
    # o comeco do outro.
    ok("a segunda chamada no MESMO dia nao escreve nada",
       gravar(_d_sex, 5000, SEX, aba=_ab) == "ja_existe" and _ab.escritas == 1)
    ok("e nem a decima",
       all(gravar(_d_sex, 5000, SEX, aba=_ab) == "ja_existe" for _ in range(8))
       and _ab.escritas == 1)
    # O REDEPLOY DO RAILWAY ZERA A MEMORIA, e a trava da planilha e a unica
    # que sobra. Sem ela o dia seria gravado DUAS vezes — e a comparacao de
    # amanha pegaria a linha errada. Limpar a memoria aqui e exatamente o
    # que o container faz ao subir de novo.
    _memoria_limpar()
    ok("depois de um redeploy, a planilha ainda barra o dia repetido",
       gravar(_d_sex, 5000, SEX, aba=_ab) == "ja_existe" and _ab.escritas == 1)

    # O DIA SEGUINTE E OUTRO RETRATO.
    ok("o dia seguinte grava",
       gravar(_d_seg, 5000, datetime(2026, 9, 28), aba=_ab) == "gravado"
       and _ab.escritas == 2)
    # O RETRATO GRAVADO TEM DE SER COMPARAVEL depois de passar pela planilha:
    # a celula volta como TEXTO, e `comparar` precisa continuar lendo.
    _lidos = _ab.get_all_records()
    _d2 = comparar(_lidos[0], _lidos[1])
    ok("dois retratos lidos da planilha ainda se comparam", len(_d2) == 2)
    ok("e o cartao que sumiu continua com o delta certo",
       next(x for x in _d2 if x["id"] == "b")["delta"] == -300.0)

    # ── O MES ERRADO, que gravaria um retrato mentiroso ─────────────────
    #
    # O master pode estar olhando AGOSTO no seletor do painel. `_processar`
    # devolve os numeros de agosto, e grava-los como o retrato de hoje faria
    # a comparacao de amanha acusar uma queda de mes inteiro que nao houve.
    # A memoria e do PROCESSO: os testes acima ja gravaram 28/09 nela, e sem
    # limpar aqui o proximo 28/09 voltaria "ja_existe" — que e exatamente o
    # comportamento certo, e nao o que este bloco quer medir.
    _memoria_limpar()
    _ab_m = _AbaFalsa()
    ok("olhar um mes passado nao grava retrato",
       gravar(_d_sex, 5000, datetime(2026, 9, 28), aba=_ab_m,
              filtro_mes=(2026, 8)) == "mes_errado" and _ab_m.escritas == 0)
    ok("o mes atual grava normalmente",
       gravar(_d_sex, 5000, datetime(2026, 9, 28), aba=_ab_m,
              filtro_mes=(2026, 9)) == "gravado" and _ab_m.escritas == 1)
    ok("sem filtro_mes grava, que e o caso da TV",
       gravar(_d_sex, 5000, datetime(2026, 9, 29), aba=_ab_m) == "gravado")

    # ── A MEMORIA, que evita 1.400 leituras de planilha por dia ─────────
    #
    # A thread da TV chama isto a cada volta. Depois do primeiro retrato do
    # dia, as chamadas seguintes nao podem nem LER a planilha.
    class _AbaConta(_AbaFalsa):
        def __init__(self):
            super().__init__()
            self.leituras = 0

        def get_all_records(self):
            self.leituras += 1
            return super().get_all_records()

    _memoria_limpar()
    _ab_c = _AbaConta()
    gravar(_d_sex, 5000, SEX, aba=_ab_c)
    _l0 = _ab_c.leituras
    for _ in range(20):
        gravar(_d_sex, 5000, SEX, aba=_ab_c)
    ok("depois do primeiro retrato do dia, nao le mais a planilha",
       _ab_c.leituras == _l0 and _ab_c.escritas == 1)
    # E O DIA SEGUINTE VOLTA A LER: a memoria e do dia, nao do processo.
    gravar(_d_seg, 5000, datetime(2026, 9, 28), aba=_ab_c)
    ok("mas o dia seguinte volta a gravar", _ab_c.escritas == 2)
    _memoria_limpar()

    # ── A VARIACAO, que e o que serve NA TV ─────────────────────────────
    #
    # Tabela de 200 cartoes numa TV nao se le de longe. O que se le e a
    # variacao: "4.900 pts, -200 desde 25/09". E ela sai do retrato anterior,
    # que `gravar` guarda de graca na mesma leitura do dia.
    _memoria_limpar()
    _ab_v = _AbaFalsa()
    gravar(_d_sex, 5000, SEX, aba=_ab_v)
    ok("no primeiro dia nao ha com o que comparar", variacao(5100.0) is None)
    _memoria_limpar()
    gravar(_d_seg, 5000, datetime(2026, 9, 28), aba=_ab_v)
    _v = variacao(4900.0)
    ok("no dia seguinte a variacao existe", _v is not None)
    ok("e ela e a diferenca contra o retrato anterior", _v["delta"] == -200.0)
    ok("dizendo contra que dia", _v["desde"] == "2026-09-25")
    # UMA QUEDA DE ZERO NAO E "None": dia parado tem de aparecer como 0, e
    # nao como "sem dado". Sao coisas diferentes na tela.
    ok("dia sem mudanca mostra zero, e nao 'sem dado'",
       variacao(5100.0)["delta"] == 0.0)

    # PLANILHA FORA DO AR nao derruba a tela nem a thread da TV.
    class _AbaQuebrada:
        def get_all_records(self):
            raise RuntimeError("sem rede")

        def append_row(self, *a, **k):
            raise RuntimeError("sem rede")

    ok("planilha fora do ar devolve 'falhou' em vez de explodir",
       gravar(_d_sex, 5000, SEX, aba=_AbaQuebrada()) == "falhou")
    ok("e a leitura devolve lista vazia", ler(_AbaQuebrada()) == [])

    print("\nfalhas:", falhas)
