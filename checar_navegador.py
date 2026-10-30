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
aba = st.radio("Home", ["Painel", "Produtos"], horizontal=True, key="home_aba")
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
