"""produtos_grupos.py — o mesmo produto com títulos diferentes, e o nicho dele.

POR QUE
-------
Na BASE DE VENDAS cada anúncio tem um título, e o mesmo produto aparece com
cinco, dez, dezesseis títulos ("Carimbo para chá de bebê…", "Kit carimbo festa
chá revelação…"). Contado por título, o produto se espalha pelo ranking, e o
anúncio novo de um produto velho parece produto novo — o dono chamou isso de
"tiro no pé" (20/10).

O SKU NÃO SERVE PARA JUNTAR: o SKU é o custo (MS-3800 = R$ 38,00), e produtos
diferentes dividem o mesmo custo — bengala, xadrez, furador e estátua de leão
são todos MS-3800. O custo só serve para separar: títulos de custo diferente
nunca são o mesmo produto.

COMO
----
1. Os títulos são separados por CUSTO UNITÁRIO.
2. Dentro de cada custo, a IA lê os títulos e diz quais são o mesmo produto,
   dá um nome curto ao produto e escolhe o NICHO de uma lista fixa.
3. O resultado vai para a aba `produtos_grupos` da planilha do Studio — a IA
   roda UMA vez por título, no clique do dono, nunca no desenho da tela.
4. O dono corrige o que vier errado na própria tela; a correção vale para
   sempre (origem "manual", e a IA não passa por cima).
"""

import json
import re
from datetime import datetime

import streamlit as st

ABA_NOME = "produtos_grupos"
COLUNAS = ["titulo", "produto", "nicho", "origem", "atualizado"]
MODELO = "claude-haiku-4-5"
POR_CHAMADA = 60

# Os nichos do dono, tirados dos mais vendidos (20/10). A IA escolhe só daqui:
# nome solto vira cinquenta grafias e a fatia por nicho não soma.
NICHOS = ("Decoração", "Tabacaria", "Artesanato e Scrapbook",
          "Festa e Chá Revelação", "Relógios e Organização",
          "Saúde e Mobilidade", "Jogos", "Vinho e Bar", "Moda e Acessórios",
          "Outros")


def norm(t):
    return " ".join(str(t or "").split()).upper()


def grupos_por_custo(linhas):
    """{custo: [títulos]} — o custo separa, a IA junta dentro dele. Pura."""
    g = {}
    for x in linhas:
        c = round(float(x.get("custo_un") or 0.0), 2)
        t = x["produto"]
        g.setdefault(c, set()).add(t)
    return {c: sorted(ts) for c, ts in g.items()}


def prompt(titulos):
    lista = "\n".join(f"{i}. {t}" for i, t in enumerate(titulos))
    return (
        "Estes são títulos de anúncios de uma loja de marketplace, todos com o "
        "MESMO custo de compra. Agrupe os que são O MESMO PRODUTO físico (títulos "
        "diferentes para a mesma coisa). Quantidades diferentes no título (kit 2 x "
        "kit 3, 100 x 500 unidades) são produtos DIFERENTES. Para cada grupo dê "
        "um nome curto do produto e o nicho, escolhido EXATAMENTE desta lista: "
        + ", ".join(NICHOS) + ".\n\n"
        "Responda só com JSON, sem texto em volta, no formato:\n"
        '[{"itens": [0, 3], "produto": "nome curto", "nicho": "Decoração"}]\n'
        "Todo índice tem de aparecer em exatamente um grupo.\n\n" + lista)


def ler_resposta(texto, titulos):
    """{título: (produto, nicho)} da resposta da IA. Pura.

    Índice que a IA esqueceu vira grupo próprio (o título é o produto) com
    nicho "Outros": nunca some título, e nunca entra nicho fora da lista.
    """
    m = re.search(r"\[.*\]", texto or "", re.S)
    try:
        grupos = json.loads(m.group(0)) if m else []
    except (ValueError, TypeError):
        grupos = []
    fora = {}
    for g in grupos if isinstance(grupos, list) else []:
        if not isinstance(g, dict):
            continue
        nome = norm(g.get("produto")) or None
        nicho = g.get("nicho") if g.get("nicho") in NICHOS else "Outros"
        for i in g.get("itens") or []:
            if isinstance(i, int) and 0 <= i < len(titulos) and titulos[i] not in fora:
                fora[titulos[i]] = (nome or titulos[i], nicho)
    for t in titulos:
        fora.setdefault(t, (t, "Outros"))
    return fora


def classificar(titulos, chamar=None):
    """(mapa, erro) de um lote. `chamar(prompt) -> texto` é trocável no teste."""
    if chamar is None:
        chamar = _chamar_ia
    texto, erro = chamar(prompt(titulos))
    if erro:
        return {}, erro
    return ler_resposta(texto, titulos), ""


def _chamar_ia(texto):
    import chaves
    chave, aviso = chaves.exigir("ANTHROPIC_API_KEY", "juntar os títulos do mesmo produto")
    if not chave:
        return "", aviso
    try:
        import anthropic
        r = anthropic.Anthropic(api_key=chave).messages.create(
            model=MODELO, max_tokens=8000,
            messages=[{"role": "user", "content": texto}])
        import uso_ia as _uso
        _uso.registrar("Produtos (agrupar títulos)", "Anthropic", MODELO, r)
        return "".join(getattr(b, "text", "") for b in r.content), ""
    except Exception as e:
        return "", f"A IA não respondeu: {type(e).__name__}: {str(e)[:160]}"


def lotes_pendentes(linhas, ja):
    """[[títulos]] ainda sem grupo, separados por custo e em lotes de 60."""
    fora = []
    for _c, ts in sorted(grupos_por_custo(linhas).items()):
        falta = [t for t in ts if t not in ja]
        for i in range(0, len(falta), POR_CHAMADA):
            fora.append(falta[i:i + POR_CHAMADA])
    return fora


# Automático (dono, 20/10: "faça que seja automático!"): quando a página abre
# com título novo, a IA junta sozinha. No máximo AUTO_LOTES chamadas por
# abertura, para a tela não esperar a IA por minutos; o resto entra na
# próxima. Uma vez por título: o que já está na aba nunca volta para a IA.
AUTO_LOTES = 5


def juntar_pendentes(mapa, pendentes, classificar_=None, salvar_=None, limite=AUTO_LOTES):
    """(mapa_novo, juntados, erro). Classifica até `limite` lotes e salva.

    Erro da IA para no lote em que aconteceu, salva o que já foi feito e
    devolve o erro — a tela avisa e não tenta de novo na mesma sessão.
    """
    classificar_ = classificar_ or classificar
    salvar_ = salvar_ or salvar
    novo, feitos, erro = dict(mapa), 0, ""
    for lote in pendentes[:limite]:
        m, erro = classificar_(lote)
        if erro:
            break
        novo = mesclar(novo, m, "ia")
        feitos += len(lote)
    if feitos:
        salvar_(novo)
    return novo, feitos, erro


# ── SEGUNDA PASSADA: UM NICHO POR PRODUTO (dono, 20/10) ─────────────────────
# A primeira passada escolhe o nicho DENTRO de cada custo, e o mesmo tipo de
# produto em custos diferentes caía em nichos diferentes ("Alicate furador"
# em Artesanato num custo e em Outros noutro). Esta passada olha os NOMES DE
# PRODUTO todos juntos, sem o custo, e dá um nicho só a cada um. O título que
# passou por ela vira origem PADRONIZADO; título novo entra como "ia" e é
# padronizado na abertura seguinte. Correção manual nunca é tocada.
PADRONIZADO = "ia-nicho"
NICHO_POR_CHAMADA = 150


def nichos_pendentes(mapa):
    """Nomes de produto com algum título ainda não padronizado. Pura."""
    return sorted({g["produto"] for g in mapa.values() if g.get("origem") == "ia"})


def prompt_nichos(nomes):
    lista = "\n".join(f"{i}. {n}" for i, n in enumerate(nomes))
    return (
        "Estes são produtos de uma loja de marketplace. Dê a cada um o nicho, "
        "escolhido EXATAMENTE desta lista: " + ", ".join(NICHOS) + ". "
        "Produtos do mesmo tipo ficam SEMPRE no mesmo nicho, qualquer que seja o "
        "nome. Use Outros só quando nenhum nicho da lista servir.\n\n"
        "Responda só com JSON, sem texto em volta, no formato:\n"
        '{"0": "Decoração", "1": "Jogos"}\n'
        "Todo índice tem de aparecer.\n\n" + lista)


def ler_nichos(texto, nomes):
    """{nome: nicho} da resposta. Pura. Nicho fora da lista vira Outros;
    nome que a IA esqueceu fica de fora (segue como estava, e volta depois)."""
    m = re.search(r"\{.*\}", texto or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except (ValueError, TypeError):
        d = {}
    fora = {}
    for k, v in (d.items() if isinstance(d, dict) else []):
        try:
            i = int(k)
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(nomes):
            fora[nomes[i]] = v if v in NICHOS else "Outros"
    return fora


def padronizar(mapa, nicho_de):
    """O mapa com o nicho de cada produto aplicado a todos os títulos "ia"
    dele, que passam a PADRONIZADO. Manual não muda. Pura."""
    fora = {}
    for t, g in mapa.items():
        if g.get("origem") == "ia" and g["produto"] in nicho_de:
            g = dict(g, nicho=nicho_de[g["produto"]], origem=PADRONIZADO)
        fora[t] = g
    return fora


def padronizar_pendentes(mapa, chamar=None, salvar_=None, limite=AUTO_LOTES):
    """(mapa_novo, produtos_padronizados, erro). Até `limite` chamadas."""
    chamar = chamar or _chamar_ia
    salvar_ = salvar_ or salvar
    # Produto com algum título corrigido à mão: o nicho do dono vale para os
    # outros títulos dele, sem perguntar à IA.
    do_dono = {g["produto"]: g["nicho"] for g in mapa.values() if g.get("origem") == "manual"}
    novo = padronizar(mapa, do_dono)
    antes = set(nichos_pendentes(mapa))
    feitos, erro = sum(1 for p in do_dono if p in antes), ""
    nomes = nichos_pendentes(novo)
    for i in range(0, min(len(nomes), limite * NICHO_POR_CHAMADA), NICHO_POR_CHAMADA):
        lote = nomes[i:i + NICHO_POR_CHAMADA]
        texto, erro = chamar(prompt_nichos(lote))
        if erro:
            break
        nicho_de = ler_nichos(texto, lote)
        novo = padronizar(novo, nicho_de)
        feitos += len(nicho_de)
    if feitos:
        salvar_(novo)
    return novo, feitos, erro


def aplicar(linhas, mapa):
    """As vendas com `produto` = o produto juntado e `nicho`. Pura.

    O título original fica em `titulo`, para o panorama dizer quais títulos
    entraram no produto.
    """
    fora = []
    for x in linhas:
        g = mapa.get(x["produto"])
        y = dict(x)
        y["titulo"] = x["produto"]
        if g:
            y["produto"], y["nicho"] = g["produto"], g["nicho"]
        else:
            y["nicho"] = ""
        fora.append(y)
    return fora


# ── planilha ────────────────────────────────────────────────────────────────

@st.cache_resource
def _aba():
    import gspread
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        return planilha.worksheet(ABA_NOME)
    except gspread.exceptions.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA_NOME, rows=3000, cols=len(COLUNAS))
        aba.append_row(COLUNAS, value_input_option="RAW")
        return aba


@st.cache_data(ttl=600, show_spinner=False)
def carregar():
    """({título: {produto, nicho, origem}}, erro)."""
    try:
        regs = _aba().get_all_records()
    except Exception as e:
        return {}, f"Não consegui ler a aba {ABA_NOME}: {type(e).__name__}"
    fora = {}
    for r in regs:
        t = norm(r.get("titulo"))
        if t:
            fora[t] = {"produto": norm(r.get("produto")) or t,
                       "nicho": r.get("nicho") or "Outros",
                       "origem": r.get("origem") or "ia"}
    return fora, ""


def mesclar(atual, novos, origem):
    """O mapa novo por cima do atual — menos onde o dono corrigiu à mão."""
    fora = dict(atual)
    for t, (prod, nicho) in novos.items():
        if fora.get(t, {}).get("origem") == "manual" and origem != "manual":
            continue
        fora[t] = {"produto": prod, "nicho": nicho, "origem": origem}
    return fora


def salvar(mapa):
    """Regrava a aba inteira numa chamada só (são até alguns milhares de linhas)."""
    import placar_core as _pc
    agora = datetime.now(_pc.FUSO).strftime("%Y-%m-%d %H:%M")
    linhas = [COLUNAS] + [[t, g["produto"], g["nicho"], g["origem"], agora]
                          for t, g in sorted(mapa.items())]
    aba = _aba()
    aba.clear()
    aba.update(linhas, "A1", value_input_option="RAW")
    carregar.clear()


if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # A ENTRADA VEM DO SISTEMA: as vendas no formato de
    # `produtos_analise.linhas_da_base` (produto = título normalizado,
    # custo_un da coluna Custo Unitário).
    L = [{"produto": "KIT COM 3 ESTÁTUAS ENFEITE", "custo_un": 22.6},
         {"produto": "MINIATURA ESTÁTUA YOGA RESINA 3 PEÇAS", "custo_un": 22.6},
         {"produto": "BENGALA DE METAL 3 APOIOS", "custo_un": 38.0},
         {"produto": "JOGO DE XADREZ MAGNÉTICO", "custo_un": 38.0},
         {"produto": "KIT COM 3 ESTÁTUAS ENFEITE", "custo_un": 22.6}]
    g = grupos_por_custo(L)
    ok("o custo separa: bengala e xadrez (mesmo custo) ficam no mesmo lote, estátuas noutro",
       g[38.0] == ["BENGALA DE METAL 3 APOIOS", "JOGO DE XADREZ MAGNÉTICO"] and len(g[22.6]) == 2)
    resp = ('Claro: [{"itens": [0, 1], "produto": "Kit 3 estátuas yoga", "nicho": "Decoração"}]')
    m = ler_resposta(resp, g[22.6])
    ok("a IA junta as duas estátuas num produto só, com o nicho da lista",
       m["KIT COM 3 ESTÁTUAS ENFEITE"] == ("KIT 3 ESTÁTUAS YOGA", "Decoração")
       and m["MINIATURA ESTÁTUA YOGA RESINA 3 PEÇAS"][0] == "KIT 3 ESTÁTUAS YOGA")
    m2 = ler_resposta('[{"itens": [0], "produto": "Bengala", "nicho": "Inventado"}]', g[38.0])
    ok("nicho fora da lista vira Outros; título esquecido pela IA vira produto próprio",
       m2["BENGALA DE METAL 3 APOIOS"] == ("BENGALA", "Outros")
       and m2["JOGO DE XADREZ MAGNÉTICO"] == ("JOGO DE XADREZ MAGNÉTICO", "Outros"))
    ok("resposta quebrada não derruba: cada título vira o próprio produto",
       ler_resposta("não sei", ["A", "B"]) == {"A": ("A", "Outros"), "B": ("B", "Outros")})
    mapa, erro = classificar(g[22.6], chamar=lambda p: (resp, ""))
    ok("classificar usa o prompt com os títulos e a lista de nichos",
       not erro and len(mapa) == 2 and "Tabacaria" in prompt(["X"]) and "0. X" in prompt(["X"]))
    ok("erro da IA volta como erro, sem mapa", classificar(["A"], chamar=lambda p: ("", "sem chave")) == ({}, "sem chave"))
    atual = {"MINIATURA ESTÁTUA YOGA RESINA 3 PEÇAS": {"produto": "ESTÁTUA AVULSA", "nicho": "Decoração", "origem": "manual"}}
    mx = mesclar(atual, mapa, "ia")
    ok("a correção manual do dono não é sobrescrita pela IA",
       mx["MINIATURA ESTÁTUA YOGA RESINA 3 PEÇAS"]["produto"] == "ESTÁTUA AVULSA"
       and mx["KIT COM 3 ESTÁTUAS ENFEITE"]["origem"] == "ia")
    ok("lotes só com o que falta, por custo",
       lotes_pendentes(L, mx) == [["BENGALA DE METAL 3 APOIOS", "JOGO DE XADREZ MAGNÉTICO"]])
    ap = aplicar(L, mx)
    ok("aplicar troca o título pelo produto e guarda o título original",
       ap[0]["produto"] == "KIT 3 ESTÁTUAS YOGA" and ap[0]["titulo"] == "KIT COM 3 ESTÁTUAS ENFEITE"
       and ap[0]["nicho"] == "Decoração" and ap[2]["produto"] == "BENGALA DE METAL 3 APOIOS" and ap[2]["nicho"] == "")

    _salvo = []
    _n, _f, _e = juntar_pendentes({}, [["A"], ["B"], ["C"]], classificar_=lambda l: ({l[0]: (l[0], "Outros")}, ""),
                                  salvar_=_salvo.append, limite=2)
    ok("automático: junta até o limite de lotes por abertura e salva uma vez",
       _f == 2 and set(_n) == {"A", "B"} and len(_salvo) == 1 and not _e)
    _salvo.clear()
    _n, _f, _e = juntar_pendentes({}, [["A"], ["B"]], classificar_=lambda l: ({}, "sem chave"),
                                  salvar_=_salvo.append)
    ok("automático: erro da IA para, não salva nada vazio e devolve o erro",
       _f == 0 and _salvo == [] and _e == "sem chave")
    _cham = []
    juntar_pendentes({}, [[str(i)] for i in range(9)], classificar_=lambda l: (_cham.append(l), ({}, ""))[1],
                     salvar_=lambda m: None)
    ok("por padrão, no máximo AUTO_LOTES chamadas por abertura (a tela não espera minutos)",
       AUTO_LOTES == 5 and len(_cham) == AUTO_LOTES)
    ok("a lista de nichos é a do dono, com Outros para o que não cabe",
       "Decoração" in NICHOS and "Tabacaria" in NICHOS and NICHOS[-1] == "Outros")
    ok("lotes de até POR_CHAMADA títulos (a resposta da IA cabe no limite)",
       POR_CHAMADA == 60 and all(len(l) <= POR_CHAMADA for l in
                                 lotes_pendentes([{"produto": f"T{i}", "custo_un": 1} for i in range(130)], {})))
    ok("norm colapsa espaços e põe em caixa alta", norm("  kit  com 3 ") == "KIT COM 3")

    # SEGUNDA PASSADA (20/10). O mapa na forma que `carregar` devolve:
    # {título: {produto, nicho, origem}}. O alicate furador em dois custos,
    # com dois nichos, que é o caso que o dono viu.
    _mp = {"ALICATE FURADOR COURO 6 FUROS": {"produto": "ALICATE FURADOR", "nicho": "Artesanato e Scrapbook", "origem": "ia"},
           "ALICATE VAZADOR PARA CINTO": {"produto": "ALICATE FURADOR", "nicho": "Outros", "origem": "ia"},
           "XADREZ MAGNÉTICO": {"produto": "XADREZ", "nicho": "Outros", "origem": "manual"},
           "BENGALA 3 APOIOS": {"produto": "BENGALA", "nicho": "Saúde e Mobilidade", "origem": PADRONIZADO}}
    ok("pendentes: só produto com título 'ia' — manual e já padronizado ficam fora",
       nichos_pendentes(_mp) == ["ALICATE FURADOR"])
    ok("o prompt da passada lista os nomes e os nichos, sem o custo",
       "0. ALICATE FURADOR" in prompt_nichos(["ALICATE FURADOR"]) and "Tabacaria" in prompt_nichos(["X"]))
    ok("ler_nichos: fora da lista vira Outros; índice inválido e resposta quebrada não derrubam",
       ler_nichos('ok {"0": "Inventado", "7": "Jogos", "x": "Jogos"}', ["A"]) == {"A": "Outros"}
       and ler_nichos("não sei", ["A"]) == {})
    _salvo = []
    _np, _nf, _ne = padronizar_pendentes(
        _mp, chamar=lambda p: ('{"0": "Artesanato e Scrapbook"}', ""), salvar_=_salvo.append)
    ok("padronizar: os dois títulos do alicate ficam no MESMO nicho e viram padronizado",
       {_np[t]["nicho"] for t in ("ALICATE FURADOR COURO 6 FUROS", "ALICATE VAZADOR PARA CINTO")}
       == {"Artesanato e Scrapbook"}
       and {_np[t]["origem"] for t in ("ALICATE FURADOR COURO 6 FUROS", "ALICATE VAZADOR PARA CINTO")}
       == {PADRONIZADO} and _nf == 1 and len(_salvo) == 1 and not _ne)
    ok("padronizar: a correção manual do dono não muda",
       _np["XADREZ MAGNÉTICO"] == _mp["XADREZ MAGNÉTICO"])
    ok("depois de padronizar, nada fica pendente (não chama a IA de novo)", nichos_pendentes(_np) == [])
    _salvo.clear()
    _np2, _nf2, _ne2 = padronizar_pendentes(_mp, chamar=lambda p: ("", "sem chave"), salvar_=_salvo.append)
    ok("padronizar: erro da IA não salva nada e devolve o erro", _salvo == [] and _ne2 == "sem chave" and _np2 == _mp)
    _ch = []
    padronizar_pendentes({f"T{i}": {"produto": f"P{i}", "nicho": "Outros", "origem": "ia"} for i in range(1000)},
                         chamar=lambda p: (_ch.append(p), ("{}", ""))[1], salvar_=lambda m: None, limite=2)
    ok("padronizar: no máximo `limite` chamadas por abertura", len(_ch) == 2)
    _mp3 = {"XADREZ DE MADEIRA": {"produto": "XADREZ", "nicho": "Decoração", "origem": "ia"},
            "XADREZ MAGNÉTICO": {"produto": "XADREZ", "nicho": "Jogos", "origem": "manual"}}
    _ch.clear()
    _np3, _nf3, _ = padronizar_pendentes(_mp3, chamar=lambda p: (_ch.append(p), ("{}", ""))[1], salvar_=lambda m: None)
    ok("padronizar: produto com título corrigido à mão herda o nicho do dono, sem chamar a IA",
       _np3["XADREZ DE MADEIRA"]["nicho"] == "Jogos" and _ch == [] and _nf3 == 1)
    # PELA CADEIA: a mesma aba de `mesclar`, depois `aplicar` nas vendas.
    _ap = aplicar([{"produto": "ALICATE VAZADOR PARA CINTO", "custo_un": 9.0}], _np)
    ok("pela cadeia: a venda do título do outro custo sai no nicho padronizado",
       _ap[0]["nicho"] == "Artesanato e Scrapbook" and _ap[0]["produto"] == "ALICATE FURADOR")

    raise SystemExit(1 if falhas else 0)
