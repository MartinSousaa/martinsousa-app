"""inter_auto.py — o extrato do Inter entra sozinho, sem ninguém clicar.

Dono, 13/10: "TEM QUE SER AUTOMÁTICO SEM NINGUÉM PRECISAR CLICAR!!!". A busca
pela API existia desde 09/10, mas só no clique de "Buscar" e "Gravar"
(`extratos_tela._buscar_inter`) — e no dia em que ninguém clicou, os gastos do
Inter não estavam no sistema.

QUEM RODA
---------
Um processo próprio, subido pelo Procfile DENTRO do container do Studio: é ali
que estão as variáveis do Inter (INTER_*, INTER2_*) e o acesso à planilha. Não
depende de navegador aberto — o `app.py` só roda quando alguém abre uma sessão,
e foi exatamente isso que deixou a TV parada depois de cada deploy
(`tv_worker.py`). Roda com a prioridade de CPU mais baixa: quem atende gente é
o Streamlit.

O QUE FAZ, A CADA `INTERVALO_MIN`
---------------------------------
Para cada conta configurada (`extrato_inter_api.configuradas`): busca os
últimos `DIAS_PARA_TRAS` dias, separa o que ainda não está gravado
(`extrato_inter_api.novos`, por conta, data e valor) e grava com
`lancamentos.gravar` — o MESMO caminho do botão 💾 Gravar. Não duplica o que
o CSV ou a busca manual já gravaram, e rodar de novo não grava duas vezes.

Resposta em formato que o Studio não reconhece NÃO grava nada
(`extrato_inter_api.conferir_resposta`): sem ninguém olhando antes, gravar
errado seria pior que não gravar. O resultado de cada volta fica em
`STATUS`, e a tela de Extrato C.C mostra a última (`resumo_status`).
"""
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta

INTERVALO_MIN = 30
DIAS_PARA_TRAS = 5
USUARIO = "inter-auto"
# Um arquivo, e não variável de módulo: o Streamlit e este processo são dois
# processos no mesmo container, e é pelo disco que um conta ao outro.
STATUS = os.path.join(tempfile.gettempdir(), "ms_inter_auto.json")


def rodada(hoje, contas, buscar, carregar, gravar):
    """Uma volta da busca automática. Devolve o que aconteceu em cada conta.

    As dependências chegam de fora (`extrato_inter_api.buscar`,
    `lancamentos.carregar`, `lancamentos.gravar`) para a conferência rodar a
    cadeia sem rede.
    """
    import extrato_inter_api as _api
    inicio = hoje - timedelta(days=DIAS_PARA_TRAS)
    fora = {}
    gravados = None
    for rotulo, pref, conta in contas:
        r = {"conta": conta, "trazidos": 0, "novos": 0, "gravados": 0,
             "erro": ""}
        fora[rotulo] = r
        lancs, erro = buscar(pref, inicio, hoje)
        if erro:
            r["erro"] = erro
            continue
        r["trazidos"] = len(lancs)
        if gravados is None:
            gravados = carregar()
        nv = _api.novos(lancs, gravados, conta)
        r["novos"] = len(nv)
        if not nv:
            continue
        n, _rep, erro = gravar(nv, conta, USUARIO)
        r["gravados"] = n
        r["erro"] = erro or ""
        if n and not erro:
            # A próxima conta e a próxima volta têm de ver o que acabou de
            # entrar — o `carregar` tem cache de 120 s.
            gravados = None
            try:
                carregar.clear()
            except AttributeError:
                pass
    return fora


def salvar_status(quando, contas, erro="", caminho=None):
    try:
        with open(caminho or STATUS, "w", encoding="utf-8") as f:
            json.dump({"quando": quando.isoformat(timespec="minutes"),
                       "contas": contas, "erro": erro}, f, ensure_ascii=False)
    except OSError as e:
        print(f"[inter_auto] não consegui gravar o status: {e}",
              file=sys.stderr, flush=True)


def resumo_status(caminho=None):
    """(texto, deu_erro) da última volta, para a tela. ("", False) sem volta."""
    try:
        with open(caminho or STATUS, encoding="utf-8") as f:
            s = json.load(f)
    except (OSError, ValueError):
        return "", False
    try:
        q = datetime.fromisoformat(s["quando"])
        quando = q.strftime("%d/%m às %H:%M")
    except (KeyError, ValueError):
        quando = "?"
    if s.get("erro"):
        return f"Busca automática do Inter ({quando}): falhou — {s['erro']}", True
    partes, deu_erro = [], False
    for rot, r in (s.get("contas") or {}).items():
        if r.get("erro"):
            deu_erro = True
            partes.append(f"{rot}: falhou — {r['erro']}")
        elif r.get("gravados"):
            partes.append(f"{rot}: {r['gravados']} novo(s) gravado(s)")
        else:
            partes.append(f"{rot}: nada novo")
    return (f"Busca automática do Inter ({quando}, a cada {INTERVALO_MIN} min): "
            + " · ".join(partes or ["nenhuma conta configurada"])), deu_erro


def main():
    try:
        os.nice(19)
    except Exception:
        pass
    import logging
    logging.getLogger(
        "streamlit.runtime.scriptrunner_utils.script_run_context"
    ).setLevel(logging.ERROR)
    logging.getLogger("streamlit.runtime.caching.cache_data_api").setLevel(
        logging.ERROR)
    import extrato_inter_api as _api
    import lancamentos as _lan
    import placar_core as _pc
    print(f"[inter_auto] subindo — busca a cada {INTERVALO_MIN} min",
          file=sys.stderr, flush=True)
    while True:
        agora = datetime.now(_pc.FUSO)
        try:
            contas = _api.configuradas()
            res = rodada(agora.date(), contas, _api.buscar, _lan.carregar,
                         _lan.gravar)
            salvar_status(agora, res)
            print(f"[inter_auto] {agora:%d/%m %H:%M} "
                  + json.dumps(res, ensure_ascii=False),
                  file=sys.stderr, flush=True)
        except Exception as e:
            # Uma volta que quebra não derruba as próximas.
            salvar_status(agora, {}, f"{type(e).__name__}: {str(e)[:160]}")
            print(f"[inter_auto] volta falhou: {e}", file=sys.stderr,
                  flush=True)
        time.sleep(INTERVALO_MIN * 60)


if __name__ == "__main__" and "--autoteste" not in sys.argv:
    main()


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__" and "--autoteste" in sys.argv:
    import extrato_inter_api as _api_t
    import lancamentos as _lan_t
    from datetime import date as _date_t
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # A ENTRADA VEM DO SISTEMA: o que a API traz sai de `extrato_inter_api.ler`
    # sobre uma resposta na forma do Inter, e o gravado tem a forma de
    # `lancamentos.carregar` (data texto, valor float, conta).
    _resp = {"transacoes": [
        {"dataEntrada": "2026-10-13", "tipoOperacao": "D", "valor": "120.00",
         "titulo": "Pix enviado", "descricao": "Pix enviado: LOJA A"},
        {"dataEntrada": "2026-10-13", "tipoOperacao": "D", "valor": "50.00",
         "titulo": "Pix enviado", "descricao": "Pix enviado: LOJA B"}]}
    _da_api = _api_t.ler(_resp)
    _planilha = [{"id": "x1", "conta": "inter-116183837", "data": "2026-10-13",
                  "valor": -120.0, "descricao": "PIX LOJA A (CSV)"}]
    _gravou = []

    def _carregar():
        return list(_planilha)

    def _gravar(lancs, conta, usuario):
        _gravou.append((len(lancs), conta, usuario))
        for l in lancs:
            _planilha.append({"conta": conta,
                              "data": _lan_t._txt_data(l["data"]),
                              "valor": l["valor"], "descricao": l["descricao"]})
        return len(lancs), 0, ""

    _contas = [("LG", "INTER", "inter-116183837")]
    _hoje = _date_t(2026, 10, 13)
    _r = rodada(_hoje, _contas, lambda p, a, b: (_da_api, ""), _carregar,
                _gravar)
    ok("grava só o que não está na planilha — o do CSV não duplica",
       _r["LG"] == {"conta": "inter-116183837", "trazidos": 2, "novos": 1,
                    "gravados": 1, "erro": ""}
       and _gravou == [(1, "inter-116183837", USUARIO)])
    _r2 = rodada(_hoje, _contas, lambda p, a, b: (_da_api, ""), _carregar,
                 _gravar)
    ok("a volta seguinte não grava de novo", _r2["LG"]["gravados"] == 0
       and len(_gravou) == 1)
    _janela = []
    rodada(_hoje, _contas, lambda p, a, b: _janela.append((a, b)) or ([], ""),
           _carregar, _gravar)
    ok(f"busca os últimos {DIAS_PARA_TRAS} dias até hoje",
       _janela == [(_hoje - timedelta(days=DIAS_PARA_TRAS), _hoje)])
    _r3 = rodada(_hoje, _contas,
                 lambda p, a, b: ([], "o Inter respondeu num formato inesperado"),
                 _carregar, _gravar)
    ok("erro da busca não grava nada e fica registrado",
       _r3["LG"]["erro"] and _r3["LG"]["gravados"] == 0 and len(_gravou) == 1)

    # O status, de ponta a ponta: o que a volta salva é o que a tela lê.
    import tempfile as _tf_t
    _arq = os.path.join(_tf_t.mkdtemp(), "st.json")
    ok("sem volta nenhuma, a tela não inventa", resumo_status(_arq) == ("", False))
    salvar_status(datetime(2026, 10, 13, 14, 30), _r, caminho=_arq)
    _txt, _err = resumo_status(_arq)
    ok("a tela diz quando foi e o que gravou",
       "13/10 às 14:30" in _txt and "LG: 1 novo(s) gravado(s)" in _txt
       and not _err)
    salvar_status(datetime(2026, 10, 13, 15, 0), _r3, caminho=_arq)
    _txt3, _err3 = resumo_status(_arq)
    ok("e diz quando falhou", "LG: falhou" in _txt3 and _err3)

    # O PROCFILE SOBE O PROCESSO, e antes do Streamlit: sem esta linha, nada
    # disto roda em produção e a tela seguiria sem a última volta.
    _proc = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "Procfile"), encoding="utf-8").read()
    ok("o Procfile sobe a busca automática junto com o Studio",
       "python inter_auto.py &" in _proc
       and _proc.index("python inter_auto.py &") < _proc.index("streamlit run"))

    print(f"\nfalhas: {falhas}")
    sys.exit(1 if falhas else 0)
