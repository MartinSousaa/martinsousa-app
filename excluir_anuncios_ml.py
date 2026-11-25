"""excluir_anuncios_ml.py — excluir no Mercado Livre os anúncios marcados na planilha.

O PEDIDO (dono, 19/11)
----------------------
O Renan preencheu a aba «Excluir» da Análise de Anúncios: coluna «EXCLUIR?»
com "s" ou "S" no que sai (ele trocou de maiúscula para minúscula na linha
413 — é a mesma marca). Em branco, fica. "Pode excluir com base nos 's' da
lista, independente se maiúsculo ou minúsculo."

O CAMINHO
---------
1. Subir a planilha. O Studio lê a aba «Excluir» (Conta, Código, Título).
2. Conferir: lê cada anúncio na conta dele (`/items?ids=`, 20 por vez) e
   separa o que já está finalizado, o que não é daquela conta e o que vai
   sair. Nada muda no ML neste passo.
3. Excluir: o dono clica, confirma, e o Studio finaliza (`status: closed`)
   e depois apaga (`deleted: true`) cada anúncio. Começa por um teste com
   5, para ver a resposta real antes dos 1.600.

A ROTA DA API NÃO FOI LIDA NA DOCUMENTAÇÃO: o site do ML recusou a leitura
automática (403, 19/11). Ela é a de sempre do `/items` — PUT com o campo
que muda —, e por isso o teste com 5 vem antes de tudo: a resposta do ML
aparece na tela, anúncio por anúncio.

A exclusão roda numa thread por conta (1.600 PUTs não cabem numa passada
da tela). A thread não lê `st.session_state`: recebe o token pronto e
escreve o andamento em `_ANDAMENTO`, global do módulo. Se o Studio
reiniciar no meio, nada se perde: «Conferir» de novo mostra o que já foi
finalizado e só sobra o resto.
"""
import threading

import streamlit as st

import ml_api as _ml

ABA = "Excluir"
LOTE = _ml.LOTE_ANUNCIOS   # o máximo do /items?ids= — um número só, o do leitor
TESTE = 5                 # o primeiro clique exclui só estes
VIVOS = ("active", "paused", "under_review", "inactive")

_TRAVA = threading.Lock()
_ANDAMENTO = {}           # conta -> {"total", "feitos", "resultados", "rodando"}


# ── Puras ─────────────────────────────────────────────────────────────────────
def _cab(txt):
    return " ".join(str(txt or "").strip().lower().split())


def marcado(valor):
    """A marca do Renan: "s" ou "S", com ou sem espaço. Qualquer outra coisa
    (branco, "n", "não", "?") NÃO exclui — na dúvida o anúncio fica."""
    return str(valor if valor is not None else "").strip().lower() == "s"


def marcados(linhas):
    """[{conta, item, titulo, linha}], [avisos] — da aba «Excluir».

    `linhas` são as tuplas da planilha, a primeira é o cabeçalho. As colunas
    se acham pelo NOME, não pela posição: a planilha é refeita a cada análise.
    """
    linhas = list(linhas)
    if not linhas:
        return [], ["a aba está vazia"]
    cab = [_cab(c) for c in linhas[0]]
    faltam = [n for n in ("excluir?", "conta", "código") if n not in cab]
    if faltam:
        return [], ["faltam as colunas: " + ", ".join(faltam)]
    i_x, i_c, i_i = cab.index("excluir?"), cab.index("conta"), cab.index("código")
    i_t = cab.index("título") if "título" in cab else None
    saida, avisos, vistos = [], [], set()
    for n, r in enumerate(linhas[1:], 2):
        r = list(r) + [None] * (len(cab) - len(r))
        if not marcado(r[i_x]):
            continue
        conta = str(r[i_c] or "").strip().lower()
        item = str(r[i_i] or "").strip().upper()
        if conta not in _ml.CONTAS:
            avisos.append(f"linha {n}: conta «{r[i_c]}» não é ML1 a ML4 — fica")
            continue
        if not (item.startswith("MLB") and item[3:].isdigit()):
            avisos.append(f"linha {n}: código «{r[i_i]}» não é um anúncio MLB — fica")
            continue
        if (conta, item) in vistos:
            continue
        vistos.add((conta, item))
        saida.append({"conta": conta, "item": item, "linha": n,
                      "titulo": str(r[i_t] or "") if i_t is not None else ""})
    return saida, avisos


def ler_planilha(dados):
    """Os bytes do .xlsx -> marcados(). Pelo `planilha_xlsx.abrir`, que lê
    até a última linha de verdade (Forma 10)."""
    import planilha_xlsx
    wb = planilha_xlsx.abrir(dados)
    try:
        nomes = {_cab(n): n for n in wb.sheetnames}
        if _cab(ABA) not in nomes:
            return [], [f"a planilha não tem a aba «{ABA}»"]
        return marcados(wb[nomes[_cab(ABA)]].iter_rows(values_only=True))
    finally:
        wb.close()


def conferir_conta(conta, tok, uid, itens, req):
    """Lê na conta cada anúncio marcado. Não muda nada.

    {"excluir": [...], "ja": [...], "erros": [(item, motivo)]}. Anúncio de
    outro vendedor vai para erros: a planilha diz ML2 e o código é da ML1 —
    excluir pela conta errada é o ML recusar, ou pior.
    """
    fora = {"excluir": [], "ja": [], "erros": []}
    por_id = {i["item"]: i for i in itens}
    # O MESMO LEITOR DAS PROMOÇÕES (25/11): o ML recusa o lote para alguns
    # anúncios, e eles vêm um por um — `ml_api.ler_anuncios`.
    lidos, falhas = _ml.ler_anuncios(conta, tok, list(por_id), "id,status,seller_id", req)
    for i in por_id:
        if i not in lidos:
            f = falhas.get(i, "")
            fora["erros"].append((i, f"não consegui ler: {f}" if f and f != "o ML não achou este anúncio"
                                  else "o ML não achou este anúncio"))
            continue
        b = lidos[i]
        if uid and str(b.get("seller_id")) != str(uid):
            fora["erros"].append((i, f"não é da {conta.upper()}"))
        elif b.get("status") == "closed":
            fora["ja"].append(por_id[i])
        elif b.get("status") in VIVOS:
            fora["excluir"].append(por_id[i])
        else:
            fora["erros"].append((i, f"situação «{b.get('status')}»"))
    return fora


def excluir_um(conta, tok, item, req):
    """Finaliza e depois apaga. (ok, mensagem). Só apaga o que finalizou."""
    _r, erro = req("PUT", conta, tok, f"/items/{item}", None, {"status": "closed"})
    if erro:
        return (False, f"não finalizou: {erro}")
    _r, erro = req("PUT", conta, tok, f"/items/{item}", None, {"deleted": "true"})
    if erro:
        return (True, f"finalizado, mas não apagou da lista: {erro}")
    return (True, "excluído")


def _trabalhar(conta, tok, itens, req):
    """A thread de UMA conta. Tudo chega por argumento (Forma 6)."""
    for it in itens:
        try:
            ok, msg = excluir_um(conta, tok, it["item"], req)
        except Exception as e:          # a thread não pode morrer calada
            ok, msg = False, f"caiu: {type(e).__name__}"
        with _TRAVA:
            a = _ANDAMENTO[conta]
            a["feitos"] += 1
            a["resultados"].append((it["item"], it["titulo"], ok, msg))
    with _TRAVA:
        _ANDAMENTO[conta]["rodando"] = False


def disparar(por_conta, tokens, req=None):
    """Uma thread por conta. `tokens` já buscados na thread da tela."""
    req = req or _ml.requisitar
    threads = []
    for conta, itens in por_conta.items():
        if not itens or conta not in tokens:
            continue
        with _TRAVA:
            if (_ANDAMENTO.get(conta) or {}).get("rodando"):
                continue            # dois cliques não disparam duas vezes
            _ANDAMENTO[conta] = {"total": len(itens), "feitos": 0,
                                 "resultados": [], "rodando": True}
        t = threading.Thread(target=_trabalhar, args=(conta, tokens[conta], itens, req),
                             daemon=True)
        t.start()
        threads.append(t)
    return threads


def andamento():
    with _TRAVA:
        return {c: {**a, "resultados": list(a["resultados"])} for c, a in _ANDAMENTO.items()}


# ── A tela ────────────────────────────────────────────────────────────────────
def _uid(conta):
    return str((_ml._ler_da_planilha(conta) or {}).get("user_id", "")).strip()


def _ao_subir():
    arq = st.session_state.get("eam_arq")
    for k in ("eam_itens", "eam_avisos", "eam_conf", "eam_armado"):
        st.session_state.pop(k, None)
    if arq is None:
        return
    try:
        itens, avisos = ler_planilha(arq.getvalue())
    except Exception as e:
        itens, avisos = [], [f"não consegui abrir a planilha: {type(e).__name__}"]
    st.session_state["eam_itens"], st.session_state["eam_avisos"] = itens, avisos


def _ao_conferir():
    itens = st.session_state.get("eam_itens") or []
    conf = {}
    for c in _ml.CONTAS:
        dela = [i for i in itens if i["conta"] == c]
        if not dela:
            continue
        tok, erro = _ml.token(c)
        if erro:
            conf[c] = {"excluir": [], "ja": [], "erros": [(i["item"], erro) for i in dela]}
            continue
        conf[c] = conferir_conta(c, tok, _uid(c), dela, _ml.requisitar)
    st.session_state["eam_conf"] = conf
    st.session_state.pop("eam_armado", None)


def _armar(qual):
    st.session_state["eam_armado"] = qual


def _desarmar():
    st.session_state.pop("eam_armado", None)


def _ao_excluir(qual):
    conf = st.session_state.get("eam_conf") or {}
    por_conta = {c: v["excluir"] for c, v in conf.items()}
    if qual == "teste":
        sobra, corte = TESTE, {}
        for c, its in por_conta.items():
            corte[c], sobra = its[:sobra], sobra - len(its[:sobra])
        por_conta = corte
    tokens = {}
    for c, its in por_conta.items():
        if its:
            tok, erro = _ml.token(c)
            if not erro:
                tokens[c] = tok
    disparar(por_conta, tokens)
    st.session_state.pop("eam_armado", None)
    st.session_state.pop("eam_conf", None)   # o que mudou se confere de novo


@st.fragment(run_every="3s")
def _andamento_ao_vivo():
    a = andamento()
    if not a:
        return
    for c in sorted(a):
        v = a[c]
        bons = sum(1 for r in v["resultados"] if r[2])
        st.progress(v["feitos"] / max(v["total"], 1),
                    text=f"{c.upper()}: {v['feitos']} de {v['total']} · {bons} excluídos"
                         + (" · rodando" if v["rodando"] else " · terminou"))
    ruins = [(c, r) for c in sorted(a) for r in a[c]["resultados"]
             if not r[2] or r[3] != "excluído"]
    if ruins:
        with st.expander(f"⚠️ {len(ruins)} com problema", expanded=len(ruins) <= 10):
            for c, (item, tit, _ok, msg) in ruins[:300]:
                st.markdown(f"**{c.upper()}** · {item} · {tit[:60]} — {msg}")
    feitos = [r for c in sorted(a) for r in a[c]["resultados"] if r[3] == "excluído"]
    if feitos and len(feitos) <= TESTE:
        for item, tit, _ok, _m in feitos:
            st.caption(f"✅ {item} · {tit[:70]}")


def pagina(usuario_logado=None):
    import auth
    if not auth.eh_dono(usuario_logado):
        st.error("Acesso restrito ao dono do Studio: esta tela exclui anúncios no Mercado Livre.")
        return
    st.markdown("### 🗑️ Excluir anúncios — Mercado Livre")
    st.caption("Sobe a Análise de Anúncios. Sai só o que tem «s» na coluna EXCLUIR? da aba "
               "Excluir (maiúsculo ou minúsculo); o resto fica.")
    _andamento_ao_vivo()
    st.file_uploader("Planilha (.xlsx)", type=["xlsx"], key="eam_arq", on_change=_ao_subir)
    itens = st.session_state.get("eam_itens")
    for a in st.session_state.get("eam_avisos") or []:
        st.warning(a)
    if not itens:
        if itens is not None:
            st.info("Nenhum anúncio marcado com «s».")
        return
    cont = {c: sum(1 for i in itens if i["conta"] == c) for c in _ml.CONTAS}
    st.markdown(f"**{len(itens)} marcados** · " +
                " · ".join(f"{c.upper()} {n}" for c, n in cont.items() if n))
    conf = st.session_state.get("eam_conf")
    st.button("🔎 Conferir no Mercado Livre (não muda nada)", key="eam_conferir",
              on_click=_ao_conferir)
    if not conf:
        return
    n_exc = sum(len(v["excluir"]) for v in conf.values())
    n_ja = sum(len(v["ja"]) for v in conf.values())
    erros = [(c, e) for c, v in conf.items() for e in v["erros"]]
    st.markdown(f"**Vão sair: {n_exc}** · já finalizados: {n_ja} · com problema: {len(erros)}")
    if erros:
        with st.expander(f"⚠️ {len(erros)} que o Studio NÃO vai mexer"):
            for c, (item, motivo) in erros[:300]:
                st.markdown(f"**{c.upper()}** · {item} — {motivo}")
    if not n_exc:
        return
    armado = st.session_state.get("eam_armado")
    if armado:
        n = min(TESTE, n_exc) if armado == "teste" else n_exc
        st.warning(f"Confirma? Isto finaliza e apaga **{n}** anúncio(s) no Mercado Livre "
                   "agora. Não tem volta.")
        c1, c2 = st.columns(2)
        c1.button("✅ Confirmar", key="eam_sim", type="primary",
                  on_click=_ao_excluir, args=(armado,))
        c2.button("Cancelar", key="eam_nao", on_click=_desarmar)
        return
    c1, c2 = st.columns(2)
    c1.button(f"🧪 Excluir {min(TESTE, n_exc)} primeiro (teste)", key="eam_teste",
              on_click=_armar, args=("teste",))
    c2.button(f"🗑️ Excluir os {n_exc}", key="eam_todos", type="primary",
              on_click=_armar, args=("todos",))


# ── Auto-teste ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import io
    import time
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # A ENTRADA VEM DA FORMA REAL (Forma 7): o cabeçalho copiado da aba
    # «Excluir» que o dono mandou em 19/11, as duas grafias do Renan, e o
    # pior título real (vírgula, acento, símbolo).
    CAB = ('EXCLUIR?', 'Conta', 'Código', 'Título', 'Preço', 'Situação', 'Motivo',
           'Visitas (ML)', 'Vendas (ML)', 'Unid. (ML)', 'Conversão', '1ª venda (base)',
           'Última venda (base)', 'Unid. no ano (base)', 'Unid. últimos 3 meses',
           'Faturamento no ano (base)', 'Outros números ruins',
           'Anúncio parecido vendendo melhor')
    LIN = [
        ("S", "ML3", "MLB111", "03 Fitas Banana Dupla Face 2,4cm X 5m Adesivo"),
        ("s", "ML1", "MLB222", "Álbum Pequeno Para Scrapbook (Cor Azul) + Fotos?"),
        (" s ", "ML2", "MLB333", "Cinzeiro"),
        (None, "ML4", "MLB444", "fica: em branco"),
        ("n", "ML4", "MLB555", "fica: n"),
        ("sim", "ML4", "MLB556", "fica: sim não é a marca do Renan"),
        ("s", "ML9", "MLB666", "conta errada"),
        ("s", "ML4", "123", "código errado"),
        ("S", "ML3", "MLB111", "repetido"),
        ("s", "ML4", "mlb777", "minúsculo no código"),
    ]
    import openpyxl
    wb = openpyxl.Workbook()
    wb.active.title = "Resumo"
    ws = wb.create_sheet("Excluir")
    ws.append(CAB)
    for x, c, i, t in LIN:
        ws.append([x, c, i, t, 64.99, "RUIM", "nenhuma venda em 2026"] + [0] * 11)
    buf = io.BytesIO()
    wb.save(buf)

    # PELA CADEIA: bytes -> planilha_xlsx.abrir -> marcados
    itens, avisos = ler_planilha(buf.getvalue())
    ids = [(i["conta"], i["item"]) for i in itens]
    ok("só sai o «s», maiúsculo, minúsculo ou com espaço",
       ids == [("ml3", "MLB111"), ("ml1", "MLB222"), ("ml2", "MLB333"), ("ml4", "MLB777")])
    ok("branco, «n» e «sim» ficam", not any(i in ("MLB444", "MLB555", "MLB556") for _c, i in ids))
    ok("conta e código inválidos viram aviso, não exclusão",
       len(avisos) == 2 and "ML9" in avisos[0] and "123" in avisos[1])
    ok("o título com símbolo chega inteiro",
       itens[1]["titulo"] == "Álbum Pequeno Para Scrapbook (Cor Azul) + Fotos?")
    ok("a linha da planilha vai junto", itens[0]["linha"] == 2)
    wb2 = openpyxl.Workbook()
    b2 = io.BytesIO()
    wb2.save(b2)
    ok("sem a aba Excluir, diz", ler_planilha(b2.getvalue())[1][0].startswith("a planilha não tem"))
    ok("colunas pelo nome: falta Código, diz",
       "código" in marcados([("EXCLUIR?", "Conta", "Titulo")])[1][0])

    # Conferir: o ML dublado no formato code/body do /items?ids=
    chamadas = []

    def rede(metodo, conta, tok, caminho, params=None, corpo=None):
        chamadas.append((metodo, conta, caminho, params, corpo))
        if metodo == "GET" and caminho != "/items":
            return {"message": "not found"}, ""     # o um por um: o ML não acha
        if metodo == "GET":
            base = {"MLB1": "active", "MLB2": "closed", "MLB3": "paused", "MLB5": "active"}
            out = []
            for i in params["ids"].split(","):
                if i in base:
                    out.append({"code": 200, "body": {"id": i, "status": base[i],
                                "seller_id": 99 if i == "MLB5" else 7}})
                else:
                    out.append({"code": 404, "body": {"message": "not found"}})
            return out, ""
        if corpo == {"status": "closed"} and caminho.endswith("MLB9"):
            return None, "Mercado Livre respondeu 400: x"
        return {}, ""

    its = [{"conta": "ml1", "item": f"MLB{n}", "titulo": f"t{n}", "linha": n} for n in (1, 2, 3, 4, 5)]
    cf = conferir_conta("ml1", "T", "7", its, rede)
    ok("ativo e pausado saem", [i["item"] for i in cf["excluir"]] == ["MLB1", "MLB3"])
    ok("já finalizado não se mexe", [i["item"] for i in cf["ja"]] == ["MLB2"])
    ok("o que o ML não acha e o de outro vendedor ficam de fora",
       dict(cf["erros"]) == {"MLB4": "o ML não achou este anúncio", "MLB5": "não é da ML1"})
    ok("conferir só lê", all(c[0] == "GET" for c in chamadas))
    chamadas.clear()
    conferir_conta("ml1", "T", "7", [{"conta": "ml1", "item": f"MLB{n}", "titulo": "", "linha": n}
                                     for n in range(45)], rede)
    _lotes = [c for c in chamadas if c[2] == "/items"]
    ok("lê 20 por vez; o que o lote não trouxe vem um por um",
       len(_lotes) == 3 and all(len(c[3]["ids"].split(",")) <= LOTE for c in _lotes)
       and sorted(c[2] for c in chamadas if c[2] != "/items")
       == sorted(f"/items/MLB{n}" for n in range(45) if n not in (1, 2, 3, 5)))

    # Excluir: finaliza ANTES de apagar, e não apaga o que não finalizou
    chamadas.clear()
    ok("excluído", excluir_um("ml1", "T", "MLB1", rede) == (True, "excluído"))
    ok("finaliza e depois apaga", [c[4] for c in chamadas] == [{"status": "closed"},
                                                                 {"deleted": "true"}])
    chamadas.clear()
    r = excluir_um("ml1", "T", "MLB9", rede)
    ok("não finalizou: não tenta apagar", not r[0] and len(chamadas) == 1)

    # A thread de verdade, e o que ela GRAVOU (Forma 6): sem session_state
    chamadas.clear()
    _ANDAMENTO.clear()
    th = disparar({"ml1": cf["excluir"], "ml2": []}, {"ml1": "T"}, req=rede)
    for t in th:
        t.join(5)
    a = andamento()
    ok("a thread terminou e contou tudo", a["ml1"]["feitos"] == 2 and not a["ml1"]["rodando"])
    ok("o resultado gravado tem item, título e mensagem",
       a["ml1"]["resultados"][0] == ("MLB1", "t1", True, "excluído"))
    ok("conta sem item não dispara", "ml2" not in a)
    _ANDAMENTO["ml1"]["rodando"] = True
    ok("dois cliques não disparam duas vezes",
       disparar({"ml1": cf["excluir"]}, {"ml1": "T"}, req=rede) == [])
    _ANDAMENTO.clear()

    # A tela: nenhum botão chama rede fora de on_click (custo por passada)
    import inspect
    fonte = inspect.getsource(pagina)
    ok("a tela não chama a API ao se desenhar",
       "_ml.token(" not in fonte and "requisitar" not in fonte and "conferir_conta(" not in fonte)
    ok("o primeiro clique é um teste de 5", "TESTE" in inspect.getsource(_ao_excluir)
       and TESTE == 5)
    ok("a thread não lê session_state",
       "session_state" not in inspect.getsource(_trabalhar)
       and "session_state" not in inspect.getsource(excluir_um))

    print(f"\n{'OK' if not falhas else 'FALHAS: ' + str(falhas)}")
    raise SystemExit(1 if falhas else 0)
