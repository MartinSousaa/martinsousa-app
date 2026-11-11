"""checar_navegador.py — o verificador que abre um navegador de verdade (27/10).

POR QUE EXISTE
--------------
Os outros verificadores desenham a tela num Streamlit de mentira. Eles
conferiam que o ranking de Produtos tinha um link, e o link estava lá — só
que link RECARREGA a página, e isso nenhum duplo vê: a navegação acontece no
navegador. O defeito foi a produção por uma semana, com ~9 s por clique, a
sub-aba voltando para o Painel e o login sendo pedido de novo (diagnóstico
do dono pela extensão do Chrome, 27/10).

O QUE MEDE
----------
Sobe um Streamlit de verdade com o `clique.py` de verdade, abre no Chromium e
clica nos alvos. Exige: (1) nenhuma navegação de página depois da primeira,
(2) o alvo certo aberto, (3) a sub-aba preservada.

Sem Chromium ou Playwright na máquina, ele diz que PULOU, em voz alta — e
não finge verde.
"""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.abspath(__file__))
CHROMIUM = "/opt/pw-browsers/chromium"

APP = '''
import sys
sys.path.insert(0, {raiz!r})
import streamlit as st
import clique
aba = st.radio("Home", ["Painel", "Produtos", "Metas", "Fila", "Estoque"], horizontal=True, key="home_aba")
if aba == "Painel":
    # O PAINEL TEM CLIQUE PRÓPRIO, como a Home de verdade (28/10). Sem isto o
    # verificador não via o defeito: a escuta nascia na caixinha do Painel,
    # morria quando ele saía da tela, e em Produtos nenhum clique abria.
    st.markdown("<div " + clique.alvo("hg", "X") + ">Quadro X</div>", unsafe_allow_html=True)
    clique.botoes("hg", ["X"])
    # A TABELA (30/10): a regra geral de tabela do app.py de VERDADE, lida do
    # arquivo, e a tabela do Balanço headcount e a do holerite como elas são
    # desenhadas. O que se mede é o que o Chromium calcula.
    import re, headcount, holerite
    _css = re.search(r"/\* ── TABELAS.*?(?=tr:last-child)",
                     open({raiz!r} + "/app.py", encoding="utf-8").read(), re.S).group(0)
    st.markdown("<style>" + _css + "</style>", unsafe_allow_html=True)
    st.markdown(headcount._tabela_html(["Colaborador", "Cargo", "Salário"],
                                       [["Bia", "Aux", "2.006,58"]], esquerda=2),
                unsafe_allow_html=True)
    st.markdown(holerite._tab(["Data", "Valor"], [[("07/10", ""), ("− R$ 100,00", "color:#E34948;")]],
                              ["left", "right"]), unsafe_allow_html=True)
if aba == "Produtos":
    st.markdown("<div>" + "".join(
        f'<div ' + clique.alvo("pa", f"PRODUTO {{i}}") + f' style="padding:10px">Linha {{i}}</div>'
        for i in range(4)) + "</div>", unsafe_allow_html=True)
    ab = clique.botoes("pa", [f"PRODUTO {{i}}" for i in range(4)])
    if ab:
        st.session_state["aberto"] = ab
    if st.session_state.get("aberto"):
        st.write("ABERTO=" + st.session_state["aberto"])
if aba == "Metas":
    # AS COLUNAS DO TRELLO (30/10): a `_secao_colunas` de verdade. So o que vai
    # ao Trello e a planilha e trocado. Cada setinha fora de formulario refazia
    # a pagina inteira (~5 s) e a linha recolhia no meio da edicao.
    import placar_core as _pc, colunas_config as _cc, analise_metas as _am
    _pc.colunas_do_board = lambda: ["VÍDEO IA TIKTOK", "Porta 2 Relógio + Jóias (2)?"]
    _cc.carregar = lambda: {{}}
    _cc.ocultas = lambda: set()
    _grav = st.session_state.setdefault("grav", [])
    _cc.salvar = lambda *a: _grav.append(a)
    st.session_state["passadas"] = st.session_state.get("passadas", 0) + 1
    st.markdown(f"PASSADAS={{st.session_state['passadas']}} GRAVOU={{len(_grav)}}")
    _am._secao_colunas([{{"tempo_lista": {{"VÍDEO IA TIKTOK": [80, 90]}}}}])
if aba == "Fila":
    # A FILA DE NOMES SEM FINALIDADE (dono, 03/11): salvou, e os nomes
    # continuavam na tabela. So o Google e trocado; a fila de verdade sai
    # do que ficou sem gravar.
    import extratos_tela as _et
    _gr = st.session_state.setdefault("fila_gravados", set())
    class _FV:
        @staticmethod
        def salvar_varios(resp, u):
            _gr.update(f for f, _fin, _tp in resp)
            return len(resp), ""
    _et._finalidades_conhecidas = lambda fv: ["CONSUMO INTERNO", "MERCADORIA"]
    _et._fixos_cadastrados = lambda: ([], [])
    _nomes = [f"Porta 2 Relógio + Jóias {{i}}" for i in range(6)]
    _fila = [{{"favorecido": n, "sentido": "saida", "n": 1, "total": 10.0, "conta": "cartão",
              "itens": [{{"data": "2026-10-2%d" % i, "descricao": n, "valor": -10.0, "conta": "cartão"}}],
              "datas": ["2026-10-20"]}} for i, n in enumerate(_nomes) if n not in _gr]
    st.markdown(f"FILA={{len(_fila)}}")
    _et._avisos_da_fila()
    if _fila:
        _et._perguntar(_fila, _FV, "teste")
if aba == "Estoque":
    # O BIPE (dono, 11/11): o leitor e um teclado, e digita onde estiver o
    # cursor. So a planilha e o Drive sao trocados; a tela e a escuta do
    # bipe sao as de verdade. O nome tem simbolo, como o da equipe.
    import estoque as _E, estoque_tela as _ET
    _db = st.session_state.setdefault("est_db", {{"p": [], "m": [], "c": []}})
    if not _db["p"]:
        _db["p"] = (_E.linhas_de_produto("7891234567895", "MBLN-06", "Bailarina (P/M) + base", 18.4,
                                         [("Braço para cima", ""), ("Sentada", "")], "t", "11/11/2026 10:00")
                    + _E.linhas_de_produto("5901234123457", "S2017", "Embaralhador automático", 42,
                                           [("", "")], "t", "11/11/2026 10:00"))
        _db["c"] = [_E.linha_de_codigo("2000000000015", "quantidade", "Kit com 2 (1 de cada)",
                                       "7891234567895", {{_db["p"][0]["id"]: 1, _db["p"][1]["id"]: 1}},
                                       "t", "x")]
    _E.carregar = lambda: (list(_db["p"]), list(_db["m"]), list(_db["c"]))
    _E.gravar_produtos = lambda l: _db["p"].extend(l) or len(l)
    _E.gravar_movimentos = lambda l: _db["m"].extend(l) or len(l)
    _E.gravar_codigo = lambda l: _db["c"].append(l) or 1
    _E.atualizar_produtos = lambda m: [p.update(m.get(p["id"], {{}})) for p in _db["p"]] and 1
    _E.salvar_foto = lambda d, n: ("", None)
    _E.atualizar_codigos = lambda m: [k.update(m.get(k["codigo"], {{}})) for k in _db["c"]] and 1
    st.markdown("KITS=" + ";".join(k["nome"] for k in _db["c"] if k["tipo"] == "kit"))
    _s = _E.saldos(_db["m"])
    st.markdown("SALDO=" + ",".join(f'{{p["variacao"] or p["nome"]}}:{{_s.get((p["id"], "fisico"), 0)}}'
                                    + (f'/{{_s[(p["id"], "full")]}}' if (p["id"], "full") in _s else "")
                                    for p in _db["p"]))
    _ET.pagina("t")
'''


def _porta_livre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("PULADO: sem Playwright nesta máquina — o clique NÃO foi medido.")
        return 0
    if not os.path.exists(CHROMIUM):
        print(f"PULADO: sem Chromium em {CHROMIUM} — o clique NÃO foi medido.")
        return 0
    pasta = tempfile.mkdtemp(prefix="checar_nav_")
    caminho = os.path.join(pasta, "app.py")
    with open(caminho, "w", encoding="utf-8") as fh:
        fh.write(APP.format(raiz=RAIZ))
    porta = _porta_livre()
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", caminho, "--server.port", str(porta),
         "--server.headless", "true", "--browser.gatherUsageStats", "false"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=pasta)
    falhas = 0
    try:
        time.sleep(6)
        with sync_playwright() as p:
            nav = p.chromium.launch(executable_path=CHROMIUM)
            pg = nav.new_page()
            navegou = []
            pg.on("framenavigated", lambda f: navegou.append(f.url) if f == pg.main_frame else None)
            pg.goto(f"http://127.0.0.1:{porta}")
            pg.wait_for_timeout(3500)
            # O TÍTULO SOBRE O VALOR (30/10): o 3º título do Balanço no centro
            # como o valor, o da coluna de valor do holerite à direita, e a
            # cor do desconto vermelha — calculados pelo navegador.
            _al = pg.eval_on_selector_all("th", "e => e.map(x => getComputedStyle(x).textAlign)")
            ok = len(_al) >= 5 and _al[2] == "center" and _al[4] == "right"
            falhas += not ok
            print(("ok    " if ok else "FALHA ") + f"título da coluna alinhado com o valor ({_al})")
            _cor = pg.eval_on_selector_all("td span", "e => e.map(x => getComputedStyle(x).color)")
            ok = "rgb(227, 73, 72)" in _cor
            falhas += not ok
            print(("ok    " if ok else "FALHA ") + f"o desconto do holerite sai vermelho ({_cor})")
            pg.get_by_text("Produtos", exact=True).click()
            pg.wait_for_timeout(1500)
            for i in (2, 0, 3):
                pg.get_by_text(f"Linha {i}", exact=True).click()
                pg.wait_for_timeout(2000)
                aberto = " ".join(pg.locator("text=ABERTO=").all_inner_texts())
                ok = f"ABERTO=PRODUTO {i}" in aberto
                falhas += not ok
                print(("ok    " if ok else "FALHA ") + f"clicar na linha {i} abre o produto {i}  ({aberto or 'nada'})")
            ok = len(navegou) == 1
            falhas += not ok
            print(("ok    " if ok else "FALHA ") + f"nenhum clique recarregou a página ({len(navegou) - 1} recarga(s))")
            marcada = pg.locator("input[type=radio]:checked").evaluate("e => e.parentElement.innerText")
            ok = "Produtos" in marcada
            falhas += not ok
            print(("ok    " if ok else "FALHA ") + f"a sub-aba continua em Produtos ({marcada.strip()})")
            # A LINHA DA COLUNA NAO RECOLHE E NAO RECARREGA A CADA SETINHA (30/10).
            import re as _re
            pg.get_by_text("Metas", exact=True).click()
            pg.wait_for_timeout(2500)
            _placar = lambda: _re.search(r"PASSADAS=(\d+) GRAVOU=(\d+)", pg.inner_text("body")).groups()
            _antes = _placar()
            pg.locator("summary").first.click()
            pg.wait_for_timeout(800)
            for _ in range(3):
                pg.locator("[data-testid=stNumberInputStepUp]").nth(1).click()
                pg.wait_for_timeout(1200)
            _depois = _placar()
            _aberta = pg.evaluate("document.querySelector('details').open")
            ok = _depois == _antes and _aberta
            falhas += not ok
            print(("ok    " if ok else "FALHA ") + f"3 setinhas na coluna: nenhuma passada nova e a linha aberta "
                  f"(passadas {_antes[0]}→{_depois[0]}, aberta={_aberta})")
            pg.get_by_role("button", name="Salvar").first.click()
            pg.wait_for_timeout(3000)
            ok = _placar()[1] == "1"
            falhas += not ok
            print(("ok    " if ok else "FALHA ") + f"o Salvar grava uma vez (gravou={_placar()[1]})")
            # SALVOU, SAIU DA TABELA (03/11): marca duas linhas, escolhe a
            # finalidade em cima e salva. Os dois nomes somem da tabela, o
            # aviso fica ACIMA dela e nenhuma marca cai em outro nome.
            pg.get_by_text("Fila", exact=True).click()
            pg.wait_for_timeout(2500)
            _tab = pg.locator("[data-testid=stDataFrameResizable]").first
            _bx = _tab.bounding_box()
            for _r in (0, 1):
                pg.mouse.click(_bx["x"] + 37, _bx["y"] + 36 + 35 * _r + 17)
                pg.wait_for_timeout(500)
            pg.locator("[data-testid=stSelectbox]").first.click()
            pg.wait_for_timeout(500)
            pg.get_by_role("option", name="CONSUMO INTERNO").click()
            pg.wait_for_timeout(500)
            pg.get_by_role("button", name=_re.compile("Salvar")).click()
            pg.wait_for_timeout(4000)
            _fl = _re.search(r"FILA=(\d+)", pg.inner_text("body")).group(1)
            _txt_tab = _tab.inner_text() if _tab.count() else ""
            _acima = pg.evaluate("(()=>{const a=document.querySelector('[data-testid=stAlertContentSuccess]');"
                                 "const t=document.querySelector('[data-testid=stDataFrameResizable]');"
                                 "return !!(a&&t&&a.getBoundingClientRect().top<t.getBoundingClientRect().top)})()")
            ok = _fl == "4" and "Jóias 0" not in _txt_tab and "Jóias 1" not in _txt_tab and _acima
            falhas += not ok
            print(("ok    " if ok else "FALHA ") + f"salvar a fila tira os nomes da tabela e avisa acima dela "
                  f"(fila={_fl}, aviso acima={_acima})")
            # O BIPE CAI NA BARRA, ESTEJA O CURSOR ONDE ESTIVER (11/11). Com o
            # cursor na QUANTIDADE, o leitor escreveria o código dentro dela
            # (6 → 64006381333931) e o Enter confirmaria a entrada.
            pg.get_by_text("Estoque", exact=True).click()
            pg.wait_for_timeout(3000)
            _sal = lambda: _re.search(r"SALDO=([^\n]*)", pg.inner_text("body")).group(1)
            _barra_foco = pg.evaluate("document.activeElement === document.querySelector('.st-key-est_bipe input')")
            pg.keyboard.type("7891234567895", delay=8)
            pg.keyboard.press("Enter")
            pg.wait_for_timeout(2500)
            _ficha = "CONFIRMAR ENTRADA" in pg.inner_text("body")
            ok = _barra_foco and _ficha
            falhas += not ok
            print(("ok    " if ok else "FALHA ") + f"estoque: o cursor nasce na barra e o bipe abre a ficha "
                  f"(foco={_barra_foco}, ficha={_ficha})")
            _q = pg.locator("[class*=st-key-est_q_] input")
            _q.nth(0).fill("6")
            _q.nth(1).fill("2")
            pg.keyboard.press("Tab")
            pg.wait_for_timeout(1500)
            _q.nth(0).click()
            pg.wait_for_timeout(300)
            pg.keyboard.type("4006381333931", delay=8)
            pg.keyboard.press("Enter")
            pg.wait_for_timeout(3000)
            _txt = pg.inner_text("body")
            ok = "Cadastrar como produto novo?" in _txt and "4006381333931" in _txt
            falhas += not ok
            print(("ok    " if ok else "FALHA ") + "estoque: bipe com o cursor na quantidade vai para a barra "
                  f"(pergunta={'Cadastrar como produto novo?' in _txt})")
            pg.get_by_role("button", name="NÃO, BIPEI ERRADO").click()
            pg.wait_for_timeout(2000)
            pg.keyboard.type("7891234567895", delay=8)
            pg.keyboard.press("Enter")
            pg.wait_for_timeout(2500)
            _q.nth(0).fill("6")
            _q.nth(1).fill("2")
            pg.keyboard.press("Tab")
            pg.wait_for_timeout(1500)
            pg.get_by_role("button", name="CONFIRMAR ENTRADA").click()
            pg.wait_for_timeout(2500)
            _depois = _sal()
            pg.get_by_role("button", name="↶ desfazer").first.click()
            pg.wait_for_timeout(2500)
            _desf = _sal()
            ok = (_depois == "Braço para cima:6,Sentada:2,Embaralhador automático:0"
                  and _desf == "Braço para cima:0,Sentada:0,Embaralhador automático:0"
                  and len(navegou) == 1)
            falhas += not ok
            print(("ok    " if ok else "FALHA ") + f"estoque: confirmar soma, desfazer devolve, nada recarrega "
                  f"({_depois} → {_desf}, recargas={len(navegou) - 1})")
            # A SAÍDA (Parte 2, 11/11): cada bipe é 1 unidade, sem perguntar;
            # código com vários modelos abre a janela; o código do kit tira
            # os dois; o envio ao Full tira do físico e soma no Full.
            pg.get_by_text("Saída", exact=True).click()
            pg.wait_for_timeout(2500)
            for _c in ("5901234123457", "5901234123457", "7891234567895"):
                pg.keyboard.type(_c, delay=8)
                pg.keyboard.press("Enter")
                pg.wait_for_timeout(2500)
            _jan = pg.get_by_role("button", name="SAIU ESTE").count()
            pg.get_by_role("button", name="SAIU ESTE").nth(1).click()
            pg.wait_for_timeout(2500)
            pg.keyboard.type("2000000000015", delay=8)
            pg.keyboard.press("Enter")
            pg.wait_for_timeout(2500)
            pg.get_by_text("Envio para o Full").click()
            pg.wait_for_timeout(2000)
            pg.keyboard.type("5901234123457", delay=8)
            pg.keyboard.press("Enter")
            pg.wait_for_timeout(2500)
            _sai = _sal()
            ok = (_jan == 2 and _sai == "Braço para cima:-1,Sentada:-2,Embaralhador automático:-3/1"
                  and len(navegou) == 1)
            falhas += not ok
            print(("ok    " if ok else "FALHA ") + f"estoque: saída por bipe, janela de modelos, kit e Full "
                  f"(janela={_jan} modelos, {_sai}, recargas={len(navegou) - 1})")
            # QUEBRA · DEVOLUÇÃO (Parte 3, 11/11): a quebra tira do físico; a
            # devolução que voltou RUIM não mexe no estoque (a peça já tinha
            # saído na venda) e conta como perda; a observação com símbolo
            # do jeito que a equipe escreve.
            pg.get_by_text("Quebra · Descarte · Devolução", exact=True).click()
            pg.wait_for_timeout(2500)
            pg.keyboard.type("5901234123457", delay=8)
            pg.keyboard.press("Enter")
            pg.wait_for_timeout(2500)
            pg.get_by_role("button", name="CONFIRMAR").click()
            pg.wait_for_timeout(3000)
            pg.get_by_text("Devolução", exact=True).click()
            pg.wait_for_timeout(2000)
            pg.keyboard.type("7891234567895", delay=8)
            pg.keyboard.press("Enter")
            pg.wait_for_timeout(2500)
            pg.get_by_text("✖ RUIM · descarte").click()
            pg.get_by_label("Observação").fill("Porta 2 Relógio + Jóias (caixa) ?")
            pg.get_by_role("button", name="CONFIRMAR").click()
            pg.wait_for_timeout(3000)
            _bx = _sal()
            _perda = _re.search(r"perda a custo: ([^\n]*)", pg.inner_text("body"))
            ok = (_bx == "Braço para cima:-1,Sentada:-2,Embaralhador automático:-4/1"
                  and _perda and _perda.group(1) == "R$ 60,40" and len(navegou) == 1)
            falhas += not ok
            print(("ok    " if ok else "FALHA ") + f"estoque: quebra tira do físico, devolução ruim só é perda "
                  f"({_bx}, perda={_perda.group(1) if _perda else '?'}, recargas={len(navegou) - 1})")
            # KITS (Parte 4, 11/11): bipa o embaralhador duas vezes (vira 2),
            # escolhe a posição da bailarina, salva; a lista de kits aparece
            # mesmo com o kit novo vazio; e o código do kit, bipado na Saída,
            # tira 2 + 1.
            pg.get_by_text("Kits", exact=True).click()
            pg.wait_for_timeout(2500)
            for _c in ("5901234123457", "5901234123457", "7891234567895"):
                pg.keyboard.type(_c, delay=8)
                pg.keyboard.press("Enter")
                pg.wait_for_timeout(2500)
            pg.get_by_role("button", name="Sentada").click()
            pg.wait_for_timeout(2000)
            pg.get_by_label("Nome do kit").fill("Kit Embaralhador + Bailarina (P/M)")
            pg.get_by_role("button", name="SALVAR E GERAR CÓDIGO").click()
            pg.wait_for_timeout(3500)
            _ktxt = pg.inner_text("body")
            _kcod = _re.search(r"código (20\d{11})", _ktxt)
            _lista = "Kits cadastrados" in _ktxt and "KITS=Kit Embaralhador + Bailarina (P/M)" in _ktxt
            pg.get_by_text("Saída", exact=True).click()
            pg.wait_for_timeout(2500)
            pg.get_by_text("Venda", exact=True).click()
            pg.wait_for_timeout(1500)
            if _kcod:
                pg.keyboard.type(_kcod.group(1), delay=8)
                pg.keyboard.press("Enter")
                pg.wait_for_timeout(2500)
            _kv = _sal()
            ok = (_lista and _kcod is not None
                  and _kv == "Braço para cima:-1,Sentada:-3,Embaralhador automático:-6/1"
                  and len(navegou) == 1)
            falhas += not ok
            print(("ok    " if ok else "FALHA ") + f"estoque: kit montado por bipe, listado, e vendido tira a receita "
                  f"(lista={_lista}, código={_kcod.group(1) if _kcod else None}, {_kv})")
            nav.close()
    except Exception as e:
        falhas += 1
        print(f"FALHA o navegador não completou o teste: {type(e).__name__}: {str(e)[:200]}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        shutil.rmtree(pasta, ignore_errors=True)
    print(f"\nfalhas: {falhas}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
