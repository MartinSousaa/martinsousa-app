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

DE ONDE VEM A LISTA
-------------------
A aba «Excluir» da planilha da Análise de Anúncios, linhas com «s» na coluna
«EXCLUIR?» — a MESMA leitura que a exclusão usou (`excluir_anuncios_ml.marcados`,
um dono da regra) e o MESMO link do Railway que as promoções usam
(`promocoes_ml.bytes_da_analise`). O Studio não guardou o resultado da
exclusão: ele vivia na memória do processo.

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


# ── Leitura (uma vez por hora) ────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def lista_de_exclusoes():
    try:
        import promocoes_ml
        dados, erro = promocoes_ml.bytes_da_analise()
        if erro:
            return [], erro
        return lista_dos_bytes(dados)
    except Exception as e:
        return [], f"a planilha da Análise não abriu: {type(e).__name__}"


# ── A tela ────────────────────────────────────────────────────────────────────
def _reler():
    lista_de_exclusoes.clear()


def pagina(usuario_logado=None):
    st.markdown("## Consulta de anúncio")
    st.caption("Antes de espelhar, digite uma palavra do anúncio e aperte Enter.")
    with st.form("cons_anuncio_form", border=False):
        c1, c2 = st.columns([5, 1])
        texto = c1.text_input("Palavra do anúncio", key="cons_anuncio_txt",
                              placeholder="ex.: globo", label_visibility="collapsed")
        c2.form_submit_button("Buscar", type="primary", use_container_width=True)

    if not normalizar(texto):
        return
    with st.spinner("Lendo a lista de exclusões..."):
        lista, erro = lista_de_exclusoes()
    estado, achados = veredito(lista, erro, texto)
    mostra = " ".join(str(texto).split())

    if estado == "sem_lista":
        st.warning(f"⚠️ **Não consegui conferir a lista de exclusões** — {erro}.  \n"
                   "Não espelhe até a lista voltar. Avise o gestor.")
        st.button("Ler a planilha de novo", key="cons_anuncio_reler", on_click=_reler)
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

    # A tela, pelo duplo do Streamlit: o caminho sem_lista não mostra ✅.
    import inspect
    src = inspect.getsource(pagina)
    ok("a tela só mostra «Liberado» no ramo liberado",
       src.index('estado == "sem_lista"') < src.index("Liberado para ser espelhado"))
    ok("busca do texto é `in`, nunca regex", "re." not in inspect.getsource(buscar)
       and "contains" not in inspect.getsource(buscar))

    print(f"\n{'OK' if not falhas else 'FALHAS: ' + str(falhas)}")
    raise SystemExit(1 if falhas else 0)
