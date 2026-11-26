"""consulta_anuncio.py — antes de espelhar, a equipe pergunta se o anúncio saiu.

O PEDIDO (dono, 26/11)
----------------------
Uma quantidade de anúncios foi excluída nas plataformas pelo Studio
(`excluir_anuncios_ml.py`). A equipe espelha anúncio que existe numa
plataforma e falta em outra — e sem consulta refaria os excluídos. A aba
«🔎 Consulta de anúncio», na barra da Operação, recebe uma palavra («Globo»,
Enter) e responde uma de duas coisas:

  ⛔ fez parte da exclusão em massa — não replicar em nenhuma plataforma;
  ✅ não está na lista de exclusões — liberado para espelhar.

DE ONDE VEM A LISTA (dono, 26/11)
---------------------------------
O GESTOR sobe a planilha da Análise de Anúncios na própria aba. O Studio lê a
aba «Excluir», linhas com «s» em «EXCLUIR?» — a MESMA leitura da exclusão
(`excluir_anuncios_ml.marcados`, um dono da regra) —, mostra a prévia (quantos,
quantos entram e saem em relação à lista atual) e só grava quando ele
confirma. A lista fica na aba «exclusoes_anuncios» da planilha do Studio: o
disco do container some a cada deploy, a planilha não.

Não é o link do Railway: o link apontava para a cópia SEM a coluna «EXCLUIR?»
(26/11), e o dono quer ver a base antes de ela valer.

A REGRA QUE NÃO PODE QUEBRAR
----------------------------
O ✅ só aparece com a lista LIDA e não vazia. Planilha que não abre, aba que
não existe, coluna que falta ou lista com zero marcas dão ⛔ amarelo de
«não consegui conferir» — nunca «liberado». Liberar por falta de dado é o
erro que refaz o anúncio que a exclusão tirou.

A busca é TEXTO, nunca padrão (Forma 12): sem acento, sem maiúscula, espaço
duplo vira um; todas as palavras digitadas têm de estar no título, em
qualquer ordem.
"""
import unicodedata

import streamlit as st

import excluir_anuncios_ml as _exc


# ── Puras ─────────────────────────────────────────────────────────────────────
def normalizar(texto):
    """minúsculo, sem acento, espaços colapsados."""
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.lower().split())


def buscar(lista, texto):
    """Os itens da lista cujo título tem TODAS as palavras digitadas.
    Comparação de texto puro (`in`), nunca expressão regular."""
    palavras = normalizar(texto).split()
    if not palavras:
        return []
    return [i for i in lista
            if all(p in normalizar(i.get("titulo")) for p in palavras)]


def lista_dos_bytes(dados):
    """(lista, erro) — os bytes do .xlsx pela leitura da própria exclusão.
    Lista vazia é erro: zero marcas não prova que nada saiu."""
    itens, avisos = _exc.ler_planilha(dados)
    if not itens:
        motivo = "; ".join(avisos[:2]) or "nenhuma linha marcada com «s»"
        return [], f"a lista de exclusões não veio: {motivo}"
    return itens, ""


def veredito(lista, erro, texto):
    """("bloqueado" | "liberado" | "sem_lista" | "vazio", achados)."""
    if not normalizar(texto):
        return "vazio", []
    if erro or not lista:
        return "sem_lista", []
    achados = buscar(lista, texto)
    return ("bloqueado" if achados else "liberado"), achados


# ── A lista gravada ───────────────────────────────────────────────────────────
ABA_NOME = "exclusoes_anuncios"
COLUNAS = ["conta", "codigo", "titulo", "enviado_em", "enviado_por"]


def linhas_para_gravar(lista, quando, quem):
    """A lista -> as linhas da aba, cabeçalho primeiro. Pura."""
    return [COLUNAS] + [[i["conta"], i["item"], i["titulo"], quando, quem] for i in lista]


def lista_das_linhas(linhas):
    """As linhas da aba -> (lista, enviado_em, enviado_por). Pura. Colunas
    pelo nome."""
    linhas = list(linhas or [])
    if not linhas:
        return [], "", ""
    cab = [str(c).strip().lower() for c in linhas[0]]
    if any(c not in cab for c in COLUNAS[:3]):
        return [], "", ""
    ix = {c: cab.index(c) for c in COLUNAS if c in cab}
    lista, quando, quem = [], "", ""
    for r in linhas[1:]:
        r = list(r) + [""] * (len(cab) - len(r))
        cod = str(r[ix["codigo"]]).strip()
        if not cod:
            continue
        lista.append({"conta": str(r[ix["conta"]]).strip(), "item": cod,
                      "titulo": str(r[ix["titulo"]])})
        if not quando and "enviado_em" in ix:
            quando = str(r[ix["enviado_em"]])
            quem = str(r[ix["enviado_por"]]) if "enviado_por" in ix else ""
    return lista, quando, quem


def diferenca(atual, nova):
    """(entram, saem) — os códigos, contando conta + código."""
    a = {(i["conta"], i["item"]) for i in atual}
    n = {(i["conta"], i["item"]) for i in nova}
    return len(n - a), len(a - n)


def _aba(criar=False):
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        return planilha.worksheet(ABA_NOME)
    except Exception:
        if not criar:
            return None
        return planilha.add_worksheet(title=ABA_NOME, rows=10, cols=len(COLUNAS))


def gravar(lista, quem, aba=None, agora=None):
    """Substitui a lista inteira, numa chamada só. (ok, erro)."""
    if not lista:
        return False, "a planilha não trouxe nenhum anúncio marcado — nada gravado"
    from datetime import datetime
    import placar_core as _pc
    quando = (agora or datetime.now(_pc.FUSO)).strftime("%d/%m/%Y %H:%M")
    linhas = linhas_para_gravar(lista, quando, quem)
    try:
        aba = aba or _aba(criar=True)
        aba.resize(rows=len(linhas), cols=len(COLUNAS))
        aba.update(values=linhas, range_name="A1", value_input_option="RAW")
    except Exception as e:
        return False, f"não consegui gravar na planilha do Studio: {type(e).__name__}"
    lista_de_exclusoes.clear()
    return True, ""


@st.cache_data(ttl=3600, show_spinner=False)
def lista_de_exclusoes():
    """(lista, erro, enviado_em, enviado_por) — da aba do Studio."""
    try:
        aba = _aba()
        if aba is None:
            return [], "a lista ainda não foi enviada pelo gestor", "", ""
        lista, quando, quem = lista_das_linhas(aba.get_all_values())
        if not lista:
            return [], "a lista gravada está vazia", "", ""
        return lista, "", quando, quem
    except Exception as e:
        return [], f"a planilha do Studio não abriu: {type(e).__name__}", "", ""


# ── A tela ────────────────────────────────────────────────────────────────────
def _reler():
    lista_de_exclusoes.clear()


def _ao_subir():
    arq = st.session_state.get("cons_anuncio_arq")
    st.session_state.pop("cons_anuncio_nova", None)
    st.session_state.pop("cons_anuncio_msg", None)
    if arq is None:
        return
    try:
        st.session_state["cons_anuncio_nova"] = lista_dos_bytes(arq.getvalue())
    except Exception as e:
        st.session_state["cons_anuncio_nova"] = ([], f"não consegui abrir a planilha: {type(e).__name__}")


def _ao_gravar(quem):
    lista, _erro = st.session_state.get("cons_anuncio_nova") or ([], "")
    ok, erro = gravar(lista, quem)
    st.session_state["cons_anuncio_msg"] = (
        f"✅ Lista gravada: {len(lista)} anúncios." if ok else f"⚠️ {erro}")
    if ok:
        st.session_state.pop("cons_anuncio_nova", None)


def _painel_do_gestor(usuario_logado, lista, quando, quem):
    rotulo = (f"📤 Lista de exclusões — {len(lista)} anúncios, enviada em {quando} por {quem}"
              if lista else "📤 Lista de exclusões — ainda não enviada")
    with st.expander(rotulo, expanded=not lista):
        st.caption("Suba a planilha da Análise de Anúncios. Valem as linhas da aba "
                   "«Excluir» com «s» na coluna «EXCLUIR?». Nada muda antes de você confirmar.")
        st.file_uploader("Planilha (.xlsx)", type=["xlsx"], key="cons_anuncio_arq",
                         on_change=_ao_subir, label_visibility="collapsed")
        msg = st.session_state.get("cons_anuncio_msg")
        if msg:
            (st.success if msg.startswith("✅") else st.warning)(msg)
        nova = st.session_state.get("cons_anuncio_nova")
        if not nova:
            return
        nl, erro = nova
        if erro:
            st.warning(f"⚠️ {erro}. Nada foi gravado.")
            return
        entram, saem = diferenca(lista, nl)
        por_conta = {}
        for i in nl:
            por_conta[i["conta"].upper()] = por_conta.get(i["conta"].upper(), 0) + 1
        st.markdown(f"**Prévia: {len(nl)} anúncios marcados** · "
                    + " · ".join(f"{c}: {n}" for c, n in sorted(por_conta.items())))
        if lista:
            st.markdown(f"Em relação à lista atual: **{entram} entram**, **{saem} saem**.")
        st.dataframe([{"Título": i["titulo"], "Conta": i["conta"].upper(), "Código": i["item"]}
                      for i in nl], hide_index=True, use_container_width=True, height=240)
        st.button(f"Gravar estes {len(nl)} como a lista de exclusões", type="primary",
                  key="cons_anuncio_gravar", on_click=_ao_gravar, args=(usuario_logado,))


def pagina(usuario_logado=None):
    st.markdown("## Consulta de anúncio")
    st.caption("Antes de espelhar, digite uma palavra do anúncio e aperte Enter.")
    lista, erro, quando, quem = lista_de_exclusoes()
    try:
        import auth as _auth
        gestor = _auth.eh_gestor(usuario_logado)
    except Exception:
        gestor = False
    if gestor:
        _painel_do_gestor(usuario_logado, lista, quando, quem)

    with st.form("cons_anuncio_form", border=False):
        c1, c2 = st.columns([5, 1])
        texto = c1.text_input("Palavra do anúncio", key="cons_anuncio_txt",
                              placeholder="ex.: globo", label_visibility="collapsed")
        c2.form_submit_button("Buscar", type="primary", use_container_width=True)

    if not normalizar(texto):
        return
    estado, achados = veredito(lista, erro, texto)
    mostra = " ".join(str(texto).split())

    if estado == "sem_lista":
        st.warning(f"⚠️ **Não consegui conferir a lista de exclusões** — {erro}.  \n"
                   "Não espelhe até a lista voltar. Avise o gestor.")
        st.button("Ler a lista de novo", key="cons_anuncio_reler", on_click=_reler)
        return
    if estado == "liberado":
        st.success(f"✅ **Nenhum anúncio com “{mostra}” está na lista de exclusões**  \n"
                   "Liberado para ser espelhado.")
        st.caption(f"Conferido contra {len(lista)} anúncios excluídos.")
        return
    n = len(achados)
    st.error(f"⛔ **{n} anúncio{'s' if n != 1 else ''} com “{mostra}” "
             f"{'fizeram' if n != 1 else 'fez'} parte da exclusão em massa**  \n"
             "Não devem ser replicados em nenhuma plataforma.")
    st.dataframe(
        [{"Título do anúncio excluído": a["titulo"], "Conta": a["conta"].upper(),
          "Código": a["item"]} for a in achados],
        hide_index=True, use_container_width=True)


if __name__ == "__main__":
    import io
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # A ENTRADA VEM DA FORMA REAL (Forma 7): o cabeçalho da aba «Excluir»
    # de 19/11, as grafias do Renan, e os piores nomes reais (Forma 12).
    import openpyxl
    CAB = ("EXCLUIR?", "Conta", "Código", "Título", "Preço", "Situação", "Motivo")
    LIN = [
        ("s", "ML2", "MLB1001", "Globo De Neve Musical  Bailarina"),
        ("S", "ML1", "MLB1002", "Globo Terrestre Decorativo 20cm"),
        (" s ", "ML4", "MLB1003", "Luminária GLOBO Vidro Retrô"),
        ("s", "ML3", "MLB1004", "Porta 2 Relógio + Jóias"),
        ("s", "ML3", "MLB1005", "Álbum Pequeno (Cor Azul) + Fotos?"),
        (None, "ML1", "MLB2001", "Globo De Cristal Que Fica"),
        ("n", "ML1", "MLB2002", "Caneca Medieval"),
    ]
    wb = openpyxl.Workbook()
    wb.active.title = "Resumo"
    ws = wb.create_sheet("Excluir")
    ws.append(CAB)
    for x, c, i, t in LIN:
        ws.append([x, c, i, t, 10.0, "RUIM", "sem venda"])
    buf = io.BytesIO()
    wb.save(buf)

    # PELA CADEIA: bytes -> excluir_anuncios_ml.ler_planilha -> lista -> veredito
    lista, erro = lista_dos_bytes(buf.getvalue())
    ok("lê só os «s», pela leitura da própria exclusão", not erro and len(lista) == 5)
    est, ach = veredito(lista, erro, "globo")
    ok("«globo» acha os 3 excluídos (maiúscula, espaço duplo) e não o que ficou",
       est == "bloqueado" and sorted(a["item"] for a in ach) == ["MLB1001", "MLB1002", "MLB1003"])
    ok("sem acento acha com acento: «luminaria» acha «Luminária»",
       [a["item"] for a in veredito(lista, "", "luminaria")[1]] == ["MLB1003"])
    ok("o nome real da Myrella acha a si mesmo (+ não vira padrão)",
       [a["item"] for a in veredito(lista, "", "Porta 2 Relógio + Jóias")[1]] == ["MLB1004"])
    ok("( ) ? * não quebram a busca",
       veredito(lista, "", "(Cor Azul) + Fotos?")[0] == "bloqueado"
       and veredito(lista, "", "*")[0] == "liberado")
    ok("palavras em qualquer ordem: «bailarina globo»",
       veredito(lista, "", "bailarina  globo")[0] == "bloqueado")
    ok("o que não está na lista sai liberado: «caneca medieval» (marcada «n»)",
       veredito(lista, "", "caneca medieval") == ("liberado", []))
    ok("busca vazia não responde nada", veredito(lista, "", "   ")[0] == "vazio")

    # A REGRA QUE NÃO PODE QUEBRAR: sem lista, nunca «liberado».
    ok("planilha que não abriu -> sem_lista, nunca liberado",
       veredito([], "a planilha da Análise não abriu: x", "caneca")[0] == "sem_lista")
    wb2 = openpyxl.Workbook()
    b2 = io.BytesIO()
    wb2.save(b2)
    l2, e2 = lista_dos_bytes(b2.getvalue())
    ok("sem a aba «Excluir» -> erro dito, e a consulta não libera",
       not l2 and "não tem a aba" in e2 and veredito(l2, e2, "caneca")[0] == "sem_lista")
    wb3 = openpyxl.Workbook()
    ws3 = wb3.active
    ws3.title = "Excluir"
    ws3.append(("Conta", "Código", "Título"))       # a cópia sem «EXCLUIR?»
    ws3.append(("ML1", "MLB9", "Globo"))
    b3 = io.BytesIO()
    wb3.save(b3)
    l3, e3 = lista_dos_bytes(b3.getvalue())
    ok("aba sem a coluna «EXCLUIR?» -> erro, não liberado",
       not l3 and "excluir?" in e3 and veredito(l3, e3, "globo")[0] == "sem_lista")
    wb4 = openpyxl.Workbook()
    wb4.active.title = "Excluir"
    wb4.active.append(CAB)
    wb4.active.append(("n", "ML1", "MLB1", "Globo"))
    b4 = io.BytesIO()
    wb4.save(b4)
    l4, e4 = lista_dos_bytes(b4.getvalue())
    ok("zero marcas é erro, não lista vazia que libera tudo",
       not l4 and e4 and veredito(l4, e4, "globo")[0] == "sem_lista")

    # A LISTA GRAVADA, PELA CADEIA: bytes reais -> lista -> gravar numa aba
    # dupla -> ler de volta -> veredito. A aba guarda o que recebeu.
    class _Aba:
        def __init__(self):
            self.v, self.tam = [], None
        def resize(self, rows, cols):
            self.tam = (rows, cols)
        def update(self, values, range_name, value_input_option):
            assert range_name == "A1"
            self.v = [list(map(str, r)) for r in values]
        def get_all_values(self):
            return self.v
    from datetime import datetime as _dt
    _a = _Aba()
    _g = gravar(lista, "martinsousa", aba=_a, agora=_dt(2026, 11, 26, 14, 5))
    ok("gravar: uma chamada, tamanho exato da lista", _g == (True, "") and _a.tam == (6, 5)
       and _a.v[0] == COLUNAS)
    _l, _q, _p = lista_das_linhas(_a.v)
    ok("ler de volta devolve os mesmos 5, com quando e quem",
       [(i["conta"], i["item"], i["titulo"]) for i in _l]
       == [(i["conta"], i["item"], i["titulo"]) for i in lista]
       and _q == "26/11/2026 14:05" and _p == "martinsousa")
    ok("a lista lida da aba responde igual: «globo» -> 3, nome da Myrella -> 1",
       len(veredito(_l, "", "globo")[1]) == 3
       and veredito(_l, "", "Porta 2 Relógio + Jóias")[0] == "bloqueado")
    _a2 = _Aba()
    ok("gravar lista vazia: recusa e não toca a aba",
       gravar([], "x", aba=_a2)[0] is False and _a2.v == [] and _a2.tam is None)
    class _AbaQuebra(_Aba):
        def update(self, *a, **k):
            raise RuntimeError("quota")
    ok("planilha recusou: o erro é dito, não engolido",
       gravar(lista, "x", aba=_AbaQuebra())[1].startswith("não consegui gravar"))
    ok("diferenca: conta + código", diferenca(lista[:3], lista[1:]) == (2, 1))
    ok("aba sem as colunas -> lista vazia (e a consulta não libera)",
       lista_das_linhas([["a", "b"], ["1", "2"]])[0] == []
       and veredito([], "a lista gravada está vazia", "x")[0] == "sem_lista")
    # lista_de_exclusoes, com a aba que ainda não existe e com a gravada
    _g_aba = globals()["_aba"]
    try:
        globals()["_aba"] = lambda criar=False: None
        lista_de_exclusoes.clear()
        _r = lista_de_exclusoes()
        ok("sem aba ainda: erro dito, nunca liberado",
           _r[0] == [] and "ainda não foi enviada" in _r[1] and veredito(_r[0], _r[1], "x")[0] == "sem_lista")
        globals()["_aba"] = lambda criar=False: _a
        lista_de_exclusoes.clear()
        _r = lista_de_exclusoes()
        ok("com a aba gravada: lê os 5", len(_r[0]) == 5 and _r[1] == "" and _r[3] == "martinsousa")
    finally:
        globals()["_aba"] = _g_aba
        lista_de_exclusoes.clear()

    # A tela, pelo duplo do Streamlit: o caminho sem_lista não mostra ✅.
    import inspect
    src = inspect.getsource(pagina)
    ok("a tela só mostra «Liberado» no ramo liberado",
       src.index('estado == "sem_lista"') < src.index("Liberado para ser espelhado"))
    ok("busca do texto é `in`, nunca regex", "re." not in inspect.getsource(buscar)
       and "contains" not in inspect.getsource(buscar))

    print(f"\n{'OK' if not falhas else 'FALHAS: ' + str(falhas)}")
    raise SystemExit(1 if falhas else 0)
