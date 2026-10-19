"""excel_ms.py — o Controle MS da empresa, lido e preenchido pela Microsoft Graph.

POR QUE ELE EXISTE
------------------
Dono, 19/10: "preciso que o sistema preencha na minha planilha essas
informações que ele computa, LPV e custo operacional na DIN FINANÇAS". O
`controle_ms.py` só LÊ, por link — e um link de compartilhamento não escreve.

POR QUE A PLANILHA FOI PARA O ONEDRIVE DA EMPRESA
-------------------------------------------------
No OneDrive pessoal a Microsoft não deixa um sistema gravar célula por
célula: o único caminho seria baixar os 12 MB, mexer e subir o arquivo
inteiro de volta — apagando o que o dono digitou no meio tempo e arriscando
as tabelas dinâmicas. No OneDrive da empresa (SharePoint) a API do Excel
grava SÓ as células pedidas, com o arquivo aberto na mão de alguém.

COMO ELE ENTRA
--------------
Aplicativo "MS Studio" no Entra da martinsousa.com.br, com permissão de
APLICATIVO `Files.ReadWrite.All` e consentimento do administrador: o Studio
entra sozinho, sem botão de "conectar" e sem token para guardar. As três
chaves moram só no Railway (MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET).

O QUE ELE NÃO FAZ
-----------------
Ainda não grava. Dono, 19/10: primeiro sobe o teste de conexão e a PRÉVIA
do que seria gravado, só leitura; o botão de gravar vem depois de a prévia
bater com a planilha. Quando vier, grava só o que está no `plano`: mês
fechado e calculado — célula que o Studio não sabe preencher fica como está.
"""

import base64
import unicodedata

import streamlit as st

CHAVES = ("MS_TENANT_ID", "MS_CLIENT_ID", "MS_CLIENT_SECRET")
GRAPH = "https://graph.microsoft.com/v1.0"
TIMEOUT = (15, 90)

ABA_DIN = "DIN FINANÇAS"
# Onde os dois blocos moram. A linha NÃO é fixa: o dono já inseriu linha
# acima deles, e a cópia de 15/10 e o print de 19/10 discordam por uma. O
# bloco se acha pelo TÍTULO, e cada mês pelo rótulo ao lado do valor.
VARREDURA = "A1:AF140"
TITULO_LPV = "LPV MENSAL"
TITULO_CO = "CUSTOS OP. MENSAL"

_MES_ABREV = ("JAN", "FEV", "MAR", "ABR", "MAI", "JUN",
              "JUL", "AGO", "SET", "OUT", "NOV", "DEZ")


def configurado():
    """As três chaves existem? ("" quando sim, ou o aviso pronto.)"""
    import chaves as _ch
    faltam = [c for c in CHAVES if not _ch.tem(c)]
    if not faltam:
        return ""
    return ("Falta no Railway: " + ", ".join(f"`{c}`" for c in faltam)
            + ". Sem elas o Studio não entra no OneDrive da empresa.")


def id_do_compartilhamento(link):
    """O link de compartilhamento no formato que a Graph aceita (`u!…`).

    É a receita publicada pela Microsoft: base64 url-safe, sem `=` no fim.
    """
    t = str(link or "").strip()
    return "u!" + base64.urlsafe_b64encode(t.encode("utf-8")).decode(
        "ascii").rstrip("=")


def eh_da_empresa(link):
    return "sharepoint.com" in str(link or "").lower()


@st.cache_data(ttl=3000, show_spinner=False)
def _token(tenant, cliente, segredo):
    """(token, erro). O token vale 60 min; o cache guarda 50."""
    import requests
    try:
        r = requests.post(
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            data={"client_id": cliente, "client_secret": segredo,
                  "scope": "https://graph.microsoft.com/.default",
                  "grant_type": "client_credentials"}, timeout=TIMEOUT)
    except Exception as e:
        return "", f"A Microsoft não respondeu: {type(e).__name__}"
    if not r.ok:
        try:
            desc = r.json().get("error_description", "")[:220]
        except Exception:
            desc = r.text[:220]
        return "", f"A Microsoft recusou a entrada (HTTP {r.status_code}): {desc}"
    return r.json().get("access_token", ""), ""


def token():
    """(token, erro)."""
    falta = configurado()
    if falta:
        return "", falta
    import chaves as _ch
    return _token(*(_ch.ler(c) for c in CHAVES))


def _pedir(metodo, caminho, **kw):
    """(json|bytes, erro). Uma chamada à Graph, com o token da vez."""
    import requests
    tok, erro = token()
    if erro:
        return None, erro
    cab = {"Authorization": f"Bearer {tok}"}
    cab.update(kw.pop("headers", {}) or {})
    try:
        r = requests.request(metodo, GRAPH + caminho, headers=cab,
                             timeout=TIMEOUT, **kw)
    except Exception as e:
        return None, f"A Graph não respondeu: {type(e).__name__}"
    if not r.ok:
        try:
            msg = r.json().get("error", {}).get("message", "")[:220]
        except Exception:
            msg = r.text[:220]
        dica = ""
        if r.status_code in (401, 403):
            dica = (" — confira no Azure se `Files.ReadWrite.All` (Aplicativo) "
                    "está com o consentimento do administrador concedido.")
        return None, f"HTTP {r.status_code}: {msg}{dica}"
    if "json" in r.headers.get("Content-Type", ""):
        return r.json(), ""
    return r.content, ""


@st.cache_data(ttl=3000, show_spinner=False)
def item_do_link(link):
    """({drive, item, nome, alterado}, erro) do arquivo por trás do link."""
    j, erro = _pedir("GET", f"/shares/{id_do_compartilhamento(link)}/driveItem")
    if erro:
        return None, erro
    try:
        return {"drive": j["parentReference"]["driveId"], "item": j["id"],
                "nome": j.get("name", ""),
                "alterado": j.get("lastModifiedDateTime", "")}, ""
    except (KeyError, TypeError):
        return None, "A Graph devolveu o arquivo sem endereço."


def baixar(link):
    """(bytes, erro) do arquivo inteiro — a leitura do `controle_ms`."""
    it, erro = item_do_link(link)
    if erro:
        return None, erro
    dados, erro = _pedir("GET", f"/drives/{it['drive']}/items/{it['item']}/content")
    if erro:
        return None, erro
    if not isinstance(dados, (bytes, bytearray)) or dados[:2] != b"PK":
        return None, "A Graph não devolveu um .xlsx."
    return bytes(dados), ""


def _livro(it):
    return f"/drives/{it['drive']}/items/{it['item']}/workbook"


def _aba_url(nome):
    # Quotado à mão: "DIN FINANÇAS" tem espaço e Ç, e a Graph quer o nome
    # entre aspas simples dentro do caminho.
    from urllib.parse import quote
    return "/worksheets('" + quote(nome.replace("'", "''"), safe="") + "')"


def ler_grade(link, aba=ABA_DIN, endereco=VARREDURA):
    """({texto, formulas, inicio}, erro): o que aparece em cada célula.

    `text` e não `values`: data e mês chegam como o dono VÊ ("jan/26"), e não
    como o número de série que o Excel guarda por baixo.
    """
    it, erro = item_do_link(link)
    if erro:
        return None, erro
    j, erro = _pedir("GET", _livro(it) + _aba_url(aba)
                     + f"/range(address='{endereco}')?$select=address,text,formulas")
    if erro:
        return None, erro
    return {"texto": j.get("text") or [], "formulas": j.get("formulas") or [],
            "endereco": j.get("address", "")}, ""


# ── ONDE GRAVAR — função pura, para ser testada sem rede ────────────────────

def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore")
    return " ".join(s.decode("ascii").upper().split())


def mes_do_rotulo(texto):
    """1..12 quando a célula é um rótulo de mês ("JANEIRO", "jan/26",
    "01/2026"); None quando não é."""
    t = _norm(texto)
    if not t:
        return None
    for i, ab in enumerate(_MES_ABREV, 1):
        if t.startswith(ab):
            return i
    import re
    m = re.fullmatch(r"(\d{1,2})[/\-.](\d{2}|\d{4})", t)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(1))
    return None


def coluna_letra(i):
    """0 → A, 25 → Z, 26 → AA."""
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def localizar(texto, titulo):
    """{mes: (linha, coluna)} — índices 0-based na grade — das células de
    valor do bloco com esse título. {} quando o título não está.

    O valor de cada mês é a célula À DIREITA do rótulo do mês, nas linhas
    logo abaixo do título. Para no primeiro mês repetido ou depois de 20
    linhas: o bloco seguinte também tem JAN…DEZ.
    """
    alvo = _norm(titulo)
    for li, linha in enumerate(texto or []):
        for ci, cel in enumerate(linha):
            if _norm(cel) != alvo and not _norm(cel).startswith(alvo):
                continue
            achados = {}
            for lj in range(li + 1, min(li + 21, len(texto))):
                lin = texto[lj]
                # O rótulo fica na coluna do título ou numa vizinha.
                for cj in (ci, ci - 1, ci + 1):
                    if 0 <= cj < len(lin) - 1:
                        m = mes_do_rotulo(lin[cj])
                        if m:
                            break
                else:
                    m = None
                if not m:
                    continue
                if m in achados:
                    return achados
                achados[m] = (lj, cj + 1)
            return achados
    return {}


def valores_a_gravar(meses_lpv, meses_co, ano, hoje):
    """({mes: lpv}, {mes: co}) — só mês FECHADO, do ANO corrente, calculado.

    `meses_lpv` como `lpv_mensal.lpv_do_ano` devolve; `meses_co` como
    `lpv_mensal.custo_operacional_do_ano`. A DIN FINANÇAS não tem coluna de
    ano: gravar outro ano nela escreveria 2025 por cima de 2026.
    """
    import lpv_mensal as _lm
    if int(ano) != hoje.year:
        return {}, {}
    lpv = {m: r["lpv"] for m, r in (meses_lpv or {}).items()
           if r.get("lpv") is not None and _lm.mes_fechado(ano, m, hoje)}
    co = {m: r["co"] for m, r in (meses_co or {}).items()
          if not r.get("motivo") and r.get("co") and _lm.mes_fechado(ano, m, hoje)}
    return lpv, co


def plano(texto, formulas, inicio_linha, inicio_col, valores_lpv, valores_co):
    """[{bloco, mes, celula, atual, novo, formula}] — o que o botão grava.

    `valores_*`: {mes: número} SÓ com o que pode ser gravado (mês fechado,
    calculado). Mês fora do dicionário não entra no plano, e a célula fica
    como está. `inicio_*`: 1-based, onde a grade lida começa (A1 → 1, 1).
    """
    fora = []
    for bloco, titulo, valores in (("LPV", TITULO_LPV, valores_lpv),
                                   ("C.O.", TITULO_CO, valores_co)):
        pos = localizar(texto, titulo)
        for mes in sorted(valores or {}):
            if mes not in pos:
                continue
            li, ci = pos[mes]
            f = ""
            try:
                f = formulas[li][ci]
            except (IndexError, TypeError):
                pass
            fora.append({
                "bloco": bloco, "mes": mes,
                "celula": f"{coluna_letra(inicio_col - 1 + ci)}{inicio_linha + li}",
                "atual": texto[li][ci] if ci < len(texto[li]) else "",
                "formula": f if isinstance(f, str) and f.startswith("=") else "",
                "novo": round(float(valores[mes]), 2)})
    return fora


if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    ok("id do compartilhamento sem '=' e com u!",
       id_do_compartilhamento("https://x.sharepoint.com/:x:/g/a?e=1").startswith("u!")
       and "=" not in id_do_compartilhamento("https://x.sharepoint.com/:x:/g/a?e=1"))
    ok("sharepoint é da empresa; onedrive.live não",
       eh_da_empresa("https://martinsousacombr-my.sharepoint.com/:x:/g/p")
       and not eh_da_empresa("https://onedrive.live.com/x"))
    ok("rótulos de mês", mes_do_rotulo("JANEIRO") == 1
       and mes_do_rotulo("set/26") == 9 and mes_do_rotulo("12/2026") == 12
       and mes_do_rotulo("Março") == 3 and mes_do_rotulo("GERAL") is None
       and mes_do_rotulo("") is None)
    ok("letra de coluna", coluna_letra(0) == "A" and coluna_letra(24) == "Y"
       and coluna_letra(26) == "AA")

    # Grade no formato da DIN FINANÇAS: título, cabeçalho, 12 meses, GERAL;
    # e o segundo bloco logo abaixo, com os mesmos meses.
    def _grade(desloc=0):
        g = [["", "", ""] for _ in range(40 + desloc)]
        g[1 + desloc][1] = "LPV MENSAL"
        g[2 + desloc][1] = "MÊS"
        for m in range(12):
            g[3 + desloc + m][1] = _MES_ABREV[m] + "/26"
            g[3 + desloc + m][2] = f"R$ {m},00"
        g[15 + desloc][1] = "GERAL"
        g[18 + desloc][1] = "CUSTOS OP. MENSAL"
        for m in range(12):
            g[20 + desloc + m][1] = _MES_ABREV[m] + "/26"
        return g

    g = _grade()
    pl = localizar(g, TITULO_LPV)
    ok("LPV: 12 meses, valor à direita do rótulo",
       len(pl) == 12 and pl[1] == (3, 2) and pl[12] == (14, 2))
    pc = localizar(g, TITULO_CO)
    ok("C.O.: não confunde com os meses do bloco de cima",
       len(pc) == 12 and pc[1] == (20, 2))
    ok("título ausente → nada", localizar(g, "NÃO EXISTE") == {})

    # A linha INSERIDA acima não muda o que se grava: muda só a célula.
    g2 = _grade(1)
    f2 = [["" for _ in r] for r in g2]
    p = plano(g2, f2, 52, 24, {9: 21.96}, {9: 101.5})
    ok("plano acha a célula pelo título, com uma linha a mais",
       [(i["bloco"], i["celula"], i["novo"]) for i in p]
       == [("LPV", "Z64", 21.96), ("C.O.", "Z81", 101.5)])
    ok("mês fora do dicionário não entra no plano",
       plano(g, [["" for _ in r] for r in g], 1, 1, {}, {}) == [])

    # O DESENHO REAL da DIN FINANÇAS, lido do .xlsx de 15/10 (XML): título
    # em X52 e X68, meses "jan".."dez" em X, valor em Y, GERAL embaixo, e
    # "LPV (FIXO E N OPER.)" em X50 — que começa com "LPV" e não pode ser
    # confundido com o título do bloco.
    _real = [["" for _ in range(32)] for _ in range(140)]
    _real[49][23] = "LPV (FIXO E N OPER.)"
    _real[51][23], _real[51][24] = "LPV MENSAL", "R$ POR VENDA"
    _real[67][23], _real[67][24] = "CUSTOS OP. MENSAL", "C.O POR MÊS"
    for _i, _n in enumerate(("jan", "fev", "mar", "abr", "mai", "jun", "jul",
                             "ago", "set", "out", "nov", "dez")):
        _real[52 + _i][23] = _real[68 + _i][23] = _n
        _real[52 + _i][24] = _real[68 + _i][24] = "0"
    _real[64][23] = _real[80][23] = "GERAL"
    _f = [["" for _ in range(32)] for _ in range(140)]
    _f[60][24] = "=IFERROR($C$8/VLOOKUP(X61,DINAMICA!$B$60:$C$72,2,0),0)"
    _p = plano(_real, _f, 1, 1, {1: 18.0, 9: 21.96}, {9: 101.5, 12: 5.0})
    ok("desenho real: Y53 jan, Y61 set, Y77 set C.O., Y80 dez C.O.",
       [(i["bloco"], i["celula"]) for i in _p]
       == [("LPV", "Y53"), ("LPV", "Y61"), ("C.O.", "Y77"), ("C.O.", "Y80")])
    ok("a prévia avisa que Y61 tem fórmula (vai ser substituída)",
       _p[1]["formula"].startswith("=IFERROR") and not _p[0]["formula"])

    # A ENTRADA VEM DO SISTEMA: os dicionários saem de `lpv_mensal.lpv` e
    # `lpv_mensal.calcular`, as mesmas funções que `lpv_do_ano` e
    # `custo_operacional_do_ano` chamam — não escritos à mão.
    import lpv_mensal as _lm
    from datetime import date as _d
    _ml = {9: _lm.lpv(5000.0, 1000.0, 300.0, 200.0, 300),
           10: _lm.lpv(5000.0, 1000.0, 300.0, 200.0, 100),
           8: _lm.lpv(None, 1000.0, 300.0, 200.0, 300)}
    _l9 = [{"valor": -9000.0, "finalidade": "PAGINA DO ML"}]
    _mc = {9: _lm.calcular(_l9, {"vendas": 300}),
           8: _lm.calcular([], {"vendas": 300})}
    vl, vc = valores_a_gravar(_ml, _mc, 2026, _d(2026, 10, 19))
    ok("só mês fechado e calculado (out em andamento, ago sem custo fixo)",
       sorted(vl) == [9] and vl[9] == _ml[9]["lpv"])
    ok("C.O. só do mês sem motivo", sorted(vc) == [9] and vc[9] == _mc[9]["co"])
    ok("outro ano não grava na DIN (ela não tem coluna de ano)",
       valores_a_gravar(_ml, _mc, 2025, _d(2026, 10, 19)) == ({}, {}))
    ok("a aba é a DIN FINANÇAS do Controle MS", ABA_DIN == "DIN FINANÇAS")
    ok("toda chamada tem prazo (conexão e leitura) — a tela não trava",
       isinstance(TIMEOUT, tuple) and len(TIMEOUT) == 2 and all(TIMEOUT))
    ok("nome da aba quotado (espaço e Ç)",
       _aba_url("DIN FINANÇAS") == "/worksheets('DIN%20FINAN%C3%87AS')")

    raise SystemExit(1 if falhas else 0)
