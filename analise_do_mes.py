"""analise_do_mes.py — a contagem ATUAL do quadro, no terminal.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
Dono, 29/09: *"eu não quero que vá pelo meu print, precisa rodar uma análise
ATUAL dos cartões concluídos NESSE MÊS DE SETEMBRO. Quero o resumo geral e por
colaborador"*.

Até aqui a única forma de eu responder isso era pedir a ele que abrisse o
Studio, tirasse um print e me mandasse — empurrando para o dono o trabalho que
o sistema tem de fazer, e ainda por cima medindo o que a TELA mostra em vez do
que o QUADRO tem.

Aqui a conta sai da mesma função que o Painel usa (`placar._processar`), com o
mesmo `_num`, as mesmas listas e o mesmo filtro de mês. Uma pergunta, uma
resposta: se este script e o Painel discordarem, é defeito, e não configuração.

COMO RODAR
----------
    python3 analise_do_mes.py            # mês corrente, em Brasília
    python3 analise_do_mes.py 2026-08    # outro mês
    python3 analise_do_mes.py --autoteste

A credencial vem de `st.secrets` ou das variáveis de ambiente
`TRELLO_API_KEY`, `TRELLO_TOKEN` e `TRELLO_BOARD_ID` (`placar_core._cred`).
Nenhum valor mora no repositório.
"""
import sys


def _fmt(n):
    return f"{n:,.2f}".replace(",", "·").replace(".", ",").replace("·", ".")


def analisar(filtro_mes):
    """(dados_do_processar, contagem_crua, por_coluna) para o mês pedido."""
    import checar_tela  # substitui o Streamlit por um duplo; sem tela, sem erro
    checar_tela.instalar()
    import placar as pl
    import placar_core as pc
    import conferencia_pontos as cf

    if not pc.TRELLO_KEY or not pc.TRELLO_TOKEN or not pc.BOARD_ID:
        raise RuntimeError(
            "sem credencial do Trello: defina TRELLO_API_KEY, TRELLO_TOKEN e "
            "TRELLO_BOARD_ID no ambiente (ou em .streamlit/secrets.toml)")

    listas, cards, membros_map, id_p, id_t, id_i = pc._buscar_board()
    pc.recarregar_membros()
    pl.MEMBROS_ATIVOS = pc.MEMBROS_ATIVOS

    d = pl._processar(listas, cards, membros_map, id_p, id_t, id_i,
                      filtro_mes=filtro_mes)
    crua = cf.contagem_crua(cards, listas, membros_map, id_p,
                            pl.MEMBROS_ATIVOS, pl.LISTAS_SEM_PONTUACAO, pl._num)

    # POR COLUNA — a MESMA função que a tela usa (`conferencia_pontos`).
    # Uma cópia aqui seria a segunda resposta para a mesma pergunta, e nesta
    # base `_processar` duplicado já discordou em 330 pontos.
    return d, crua, cf.por_coluna(d.get("cards_pts"))


def relatorio(filtro_mes):
    import placar as pl
    import placar_core as pc
    d, crua, por_coluna = analisar(filtro_mes)

    soma_ind = sum(d["pts_membro"].values())
    linhas = [
        f"═══ {pc.MESES_PT[filtro_mes[1]].upper()} DE {filtro_mes[0]} "
        f"— cartões CONCLUÍDOS no mês ═══", "",
        f"  Pontuação coletiva .......... {_fmt(d['pts_equipe']):>12}",
        f"  Penalidades ................. {_fmt(-d['pen_total']):>12}"
        f"   ({len(d['pen_cards'])} ocorrência(s))",
        f"  SALDO ....................... "
        f"{_fmt(d['pts_equipe'] - d['pen_total']):>12}",
        f"  Cartões que somam ........... {len(d.get('cards_pts') or []):>12}",
        "",
        f"  Soma dos individuais ........ {_fmt(soma_ind):>12}",
        f"  Sem dono (no time e em pessoa nenhuma) "
        f"{_fmt(d['pts_equipe'] - soma_ind):>6}",
        "", "  POR COLABORADOR", ""]
    for u, nome in sorted(pl.MEMBROS_ATIVOS.items(),
                          key=lambda x: -d["pts_membro"].get(x[0], 0.0)):
        linhas.append(
            f"   {nome:<22} {_fmt(d['pts_membro'].get(u, 0.0)):>10} pts"
            f"   penalidades {_fmt(d['pen_membro'].get(u, 0.0)):>8}")
    linhas += ["", "  POR COLUNA (onde os pontos do mês estão)", ""]
    for nl, e in sorted(por_coluna.items(), key=lambda x: -x[1]["pts"]):
        linhas.append(f"   {nl:<38} {_fmt(e['pts']):>10} pts"
                      f"   {e['qtd']:>4} cartão(ões)")
    linhas += ["",
               f"  Trello, TODOS os meses ...... {_fmt(crua['total']):>12}",
               f"  Cartões no quadro ........... {crua['qtd']['cards']:>12}"]
    return "\n".join(linhas)


if __name__ == "__main__":
    if "--autoteste" in sys.argv:
        falhas = 0

        def ok(nome, cond):
            global falhas
            falhas += not cond
            print(("ok    " if cond else "FALHA ") + nome)

        # A ENTRADA VEM DA CADEIA REAL: sem credencial, a exigência é que o
        # script DIGA isso, e não devolva zero parecendo resposta. Zero calado
        # é a pior saída possível — vira número em relatório.
        import checar_tela as _ct
        _ct.instalar()
        import placar_core as _pc
        _k, _t, _b = _pc.TRELLO_KEY, _pc.TRELLO_TOKEN, _pc.BOARD_ID
        _pc.TRELLO_KEY = _pc.TRELLO_TOKEN = _pc.BOARD_ID = ""
        try:
            analisar((2026, 9))
            ok("sem credencial, o script RECUSA em vez de devolver zero", False)
        except RuntimeError as e:
            ok("sem credencial, o script RECUSA em vez de devolver zero",
               "credencial" in str(e))
        except Exception as e:
            ok(f"sem credencial, recusa com RuntimeError (veio {type(e).__name__})",
               False)
        finally:
            _pc.TRELLO_KEY, _pc.TRELLO_TOKEN, _pc.BOARD_ID = _k, _t, _b

        # A CONTA É A DO PAINEL, e isso é estrutural: se este script tivesse
        # `_processar` próprio, ele passaria a discordar da tela — e a
        # pergunta "quanto deu setembro?" teria duas respostas. Já aconteceu
        # nesta base, com 330 pontos de diferença.
        import ast, inspect
        _arv = ast.parse(inspect.getsource(analisar))
        _chama = {(getattr(n.func, "attr", "") or getattr(n.func, "id", ""))
                  for n in ast.walk(_arv) if isinstance(n, ast.Call)}
        ok("a conta sai de `placar._processar`, e não de uma cópia",
           "_processar" in _chama)
        ok("a leitura da pontuação é o `_num` da tela",
           "_num" in inspect.getsource(analisar))
        _fonte = open(__file__, encoding="utf-8").read().split(
            'if __name__ ==')[0]
        ok("e este arquivo não define um _processar próprio",
           "def _processar" not in _fonte)

        # TRIAGEM PAGA. O relatório por coluna existe justamente para
        # responder "quanto tem na TRIAGEM" — se ela não pagasse, a coluna
        # nunca apareceria na lista e a pergunta ficaria sem resposta.
        ok("TRIAGEM paga pontos, então aparece no relatório por coluna",
           "TRIAGEM" not in _pc.LISTAS_SEM_PONTUACAO)

        # O POR-COLUNA É O DA TELA, e isso é estrutural.
        ok("o por-coluna vem de `conferencia_pontos`, e não de uma cópia",
           "cf.por_coluna" in inspect.getsource(analisar)
           and "por_coluna = {}" not in _fonte)

        print("\nfalhas:", falhas)
        sys.exit(1 if falhas else 0)

    import placar_core as _pc0
    if len(sys.argv) > 1:
        _a, _m = sys.argv[1].split("-")[:2]
        _mes = (int(_a), int(_m))
    else:
        _h = _pc0.agora_br()
        _mes = (_h.year, _h.month)
    print(relatorio(_mes))
