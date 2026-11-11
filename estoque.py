"""estoque.py — o estoque da mercadoria: cadastro, variações e movimentos (11/11).

O dono desenhou em seis partes, aprovadas uma a uma. Este arquivo é o
NÚCLEO das seis: o que fica gravado e a conta do saldo. A tela mora em
`estoque_tela.py`.

AS TRÊS ABAS DA PLANILHA
------------------------
`estoque_produtos`   uma linha por VARIAÇÃO. A bailarina MBLN-06 tem o
                     mesmo código de barras nas três posições: são três
                     linhas com o mesmo `ean` e `variacao` diferente.
`estoque_movimentos` TUDO o que mexe no estoque é uma linha nova, nunca uma
                     conta reescrita: entrada, saída, quebra, desfazer. O
                     saldo é a SOMA das linhas — assim o histórico explica o
                     número, e duas pessoas gravando ao mesmo tempo não
                     apagam uma à outra.
`estoque_codigos`    os códigos que o Studio GERA: variação de quantidade
                     ("kit com 3, 1 de cada posição") e kit de produtos
                     diferentes. Eles NÃO entram no estoque — são a receita
                     do que sai quando o código é bipado. Dono, 11/11: "se eu
                     der entrada nos produtos e depois dar entrada em kit, vai
                     duplicar".

O CÓDIGO DE BARRAS É TEXTO, NUNCA NÚMERO
----------------------------------------
`get_all_records` do gspread converte "0789…" em 789… e o zero da frente
some — o bipe nunca mais acharia o produto. Tudo aqui lê por
`get_all_values`, que devolve texto, e grava com RAW.
"""
import json
import secrets

ABA_PRODUTOS = "estoque_produtos"
COL_PRODUTOS = ["id", "ean", "codigo_fornecedor", "nome", "variacao", "custo",
                "foto_id", "registrado_em", "registrado_por", "ativo"]

ABA_MOV = "estoque_movimentos"
COL_MOV = ["id", "lote", "quando", "tipo", "local", "produto_id", "qtd",
           "custo_unit", "quem", "obs", "desfaz", "pedido", "foto_id"]

ABA_CONTAGENS = "estoque_contagens"
COL_CONTAGENS = ["id", "aberta_em", "aberta_por", "fechada_em", "fechada_por"]
ABA_CONTADOS = "estoque_contados"
COL_CONTADOS = ["contagem", "produto_id", "qtd", "onde", "quem", "quando"]
AJUSTE_CONTAGEM = "contagem"

ABA_COMPRAS = "estoque_compras"
COL_COMPRAS = ["produto_id", "marcado_em", "quem"]

ABA_CODIGOS = "estoque_codigos"
COL_CODIGOS = ["codigo", "tipo", "nome", "produto_ean", "itens", "foto_id",
               "criado_em", "criado_por"]

FISICO, FULL = "fisico", "full"
# UM FULL POR CONTA (dono, 11/11): "o estoque no full deve ser separado do
# físico, pois acontece de acabar o físico e ainda termos ele no full" — e
# cada conta tem o seu Full. Os nomes são os do Bling (`bling_api.py:19-20`).
# `FULL` sozinho fica só para ler linha antiga, gravada antes da separação.
FULLS = {"full_ml1": "Full ML1", "full_ml2": "Full ML2", "full_ml3": "Full ML3",
         "full_ml4": "Full ML4", "full_shopee1": "Full Shopee 1", "full_shopee2": "Full Shopee 2"}
NOME_LOCAL = {FISICO: "físico", FULL: "Full (sem conta)", **FULLS}


def eh_full(local):
    """O local é um Full (de qualquer conta)? Pura."""
    return str(local or "").startswith(FULL)


def no_full(saldo, pid):
    """O total do produto em TODOS os Full. Pura."""
    return sum(q for (p, loc), q in saldo.items() if p == pid and eh_full(loc))
ENTRADA, DESFEITO = "entrada", "desfeito"
VENDA, ENVIO_FULL = "venda", "envio_full"
QUEBRA, DESCARTE, DOACAO, DEVOLUCAO = "quebra", "descarte", "doacao", "devolucao"
PERDAS = (QUEBRA, DESCARTE, DOACAO)

# Prefixo 2 é a faixa que o GS1 reserva para uso INTERNO: nenhum produto do
# mercado tem código começando por 20. O código que o Studio gera nunca
# colide com o de um fornecedor.
PREFIXO_INTERNO = "20"


# ── texto da planilha ────────────────────────────────────────────────────────

def limpar_codigo(txt):
    """O código como o leitor manda: sem espaço nem quebra de linha. Pura.

    O leitor termina o bipe com Enter, e quem digita à mão põe espaço no meio
    ("7 891 234…"). Os zeros da frente FICAM: o código é texto.
    """
    return "".join(str(txt or "").split())


def numero(txt, padrao=0.0):
    """'18,40', 'R$ 1.234,50', '18.4' → float. Pura."""
    s = str(txt or "").replace("R$", "").strip()
    if not s:
        return padrao
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return padrao


def inteiro(txt, padrao=0):
    try:
        return int(round(numero(txt, padrao)))
    except (TypeError, ValueError):
        return padrao


def linhas_para_dicts(valores, colunas):
    """`get_all_values` → [dict], pelo cabeçalho DA ABA. Pura.

    Lê pelo cabeçalho que está na planilha, e não pela ordem de `colunas`:
    alguém que mova uma coluna à mão não troca o custo pelo nome.
    """
    if not valores:
        return []
    cab = [str(c).strip() for c in valores[0]]
    fora = []
    for linha in valores[1:]:
        if not any(str(v).strip() for v in linha):
            continue
        d = {c: "" for c in colunas}
        for i, c in enumerate(cab):
            if c and i < len(linha):
                d[c] = str(linha[i])
        fora.append(d)
    return fora


# ── código de barras (EAN-13) ────────────────────────────────────────────────

_L = ["0001101", "0011001", "0010011", "0111101", "0100011",
      "0110001", "0101111", "0111011", "0110111", "0001011"]
_R = ["".join("1" if b == "0" else "0" for b in c) for c in _L]
_G = [c[::-1] for c in _R]
_PARIDADE = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG",
             "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"]


def digito_ean13(doze):
    """O 13º dígito (verificador) de 12 dígitos. Pura."""
    s = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(doze))
    return str((10 - s % 10) % 10)


def ean13_valido(cod):
    cod = limpar_codigo(cod)
    return len(cod) == 13 and cod.isdigit() and digito_ean13(cod[:12]) == cod[12]


def modulos_ean13(cod):
    """A sequência de barras (1) e espaços (0) do EAN-13. Pura."""
    if not ean13_valido(cod):
        raise ValueError(f"EAN-13 inválido: {cod!r}")
    par = _PARIDADE[int(cod[0])]
    esq = "".join((_L if p == "L" else _G)[int(d)] for p, d in zip(par, cod[1:7]))
    dir_ = "".join(_R[int(d)] for d in cod[7:13])
    return "101" + esq + "01010" + dir_ + "101"


def svg_ean13(cod, modulo=2, altura=60, texto=True):
    """O código desenhado em SVG, com a margem branca que o leitor exige. Pura.

    A margem (11 módulos de cada lado) não é enfeite: sem ela o leitor não
    acha onde o código começa — e o dono vai bipar NA TELA (Parte 2).
    """
    mods = modulos_ean13(cod)
    quieta = 11
    larg = (len(mods) + 2 * quieta) * modulo
    alt_txt = 16 if texto else 0
    rects = []
    i = 0
    while i < len(mods):
        if mods[i] == "1":
            j = i
            while j < len(mods) and mods[j] == "1":
                j += 1
            rects.append(f'<rect x="{(quieta + i) * modulo}" y="4" '
                         f'width="{(j - i) * modulo}" height="{altura}"/>')
            i = j
        else:
            i += 1
    legenda = (f'<text x="{larg / 2}" y="{altura + 4 + alt_txt - 2}" '
               f'font-family="monospace" font-size="14" text-anchor="middle">'
               f'{cod}</text>') if texto else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{larg}" '
            f'height="{altura + 8 + alt_txt}" viewBox="0 0 {larg} {altura + 8 + alt_txt}">'
            f'<rect width="100%" height="100%" fill="#fff"/>'
            f'<g fill="#000">{"".join(rects)}</g>{legenda}</svg>')


def novo_codigo_interno(existentes):
    """O próximo código 20…, que não colide com nenhum já usado. Pura.

    `existentes` são TODOS os códigos conhecidos (produto e gerado): um
    produto de fornecedor que por acaso comece com 20 também é evitado.
    """
    usados = {limpar_codigo(c) for c in existentes}
    maior = 0
    for c in usados:
        if c.startswith(PREFIXO_INTERNO) and len(c) == 13 and c.isdigit():
            maior = max(maior, int(c[2:12]))
    n = maior + 1
    while True:
        doze = PREFIXO_INTERNO + f"{n:010d}"
        cod = doze + digito_ean13(doze)
        if cod not in usados:
            return cod
        n += 1


# ── produtos, saldo e lotes (puras) ──────────────────────────────────────────

def ativos(produtos):
    return [p for p in produtos if str(p.get("ativo", "1")).strip() not in ("0", "nao", "não")]


def do_codigo(produtos, codigo):
    """As variações cadastradas com este código de barras. Pura."""
    c = limpar_codigo(codigo)
    if not c:
        return []
    return [p for p in ativos(produtos) if limpar_codigo(p.get("ean")) == c]


def codigo_gerado(codigos, codigo):
    """O código de quantidade/kit com este número, ou None. Pura."""
    c = limpar_codigo(codigo)
    for k in codigos:
        if limpar_codigo(k.get("codigo")) == c:
            return k
    return None


def itens_do_codigo(k):
    """{produto_id: qtd} da receita de um código gerado. Pura."""
    try:
        d = json.loads(k.get("itens") or "{}")
    except (TypeError, ValueError):
        return {}
    return {str(pid): inteiro(q) for pid, q in d.items() if inteiro(q) > 0}


def nome_completo(p):
    v = str(p.get("variacao") or "").strip()
    return f'{p.get("nome", "")} · {v}' if v else str(p.get("nome", ""))


def saldos(movs):
    """{(produto_id, local): quantidade}. A soma das linhas, e mais nada. Pura."""
    s = {}
    for m in movs:
        ch = (str(m.get("produto_id")), str(m.get("local") or FISICO))
        s[ch] = s.get(ch, 0) + inteiro(m.get("qtd"))
    return s


def lotes_desfeitos(movs):
    return {str(m.get("desfaz")) for m in movs if str(m.get("desfaz") or "").strip()}


def ultimos_lotes(movs, tipo, n=5):
    """Os últimos `n` lotes de um tipo, do mais novo ao mais velho. Pura.

    Um lote é um CONFIRMAR: as três posições da bailarina entram juntas e se
    desfazem juntas. Devolve [{lote, quando, quem, linhas, desfeito}].
    """
    desf = lotes_desfeitos(movs)
    tipos = (tipo,) if isinstance(tipo, str) else tuple(tipo)
    por = {}
    ordem = []
    for m in movs:
        if m.get("tipo") not in tipos:
            continue
        lt = str(m.get("lote"))
        if lt not in por:
            por[lt] = {"lote": lt, "quando": m.get("quando", ""),
                       "quem": m.get("quem", ""), "linhas": [], "desfeito": lt in desf}
            ordem.append(lt)
        por[lt]["linhas"].append(m)
    return [por[lt] for lt in reversed(ordem)][:n]


def _id(prefixo):
    return prefixo + secrets.token_hex(5)


def linhas_de_produto(ean, codigo_fornecedor, nome, custo, variacoes, quem, quando):
    """As linhas de `estoque_produtos` de um cadastro novo. Pura.

    `variacoes` = [(nome_da_variacao, foto_id)]; produto sem variação passa
    [("", foto_id)]. Devolve as linhas, cada uma com o seu `id`.
    """
    return [{"id": _id("P"), "ean": limpar_codigo(ean),
             "codigo_fornecedor": str(codigo_fornecedor or "").strip(),
             "nome": str(nome or "").strip(), "variacao": str(v or "").strip(),
             "custo": f"{float(custo or 0):.2f}", "foto_id": foto or "",
             "registrado_em": quando, "registrado_por": quem, "ativo": "1"}
            for v, foto in variacoes]


def linhas_de_entrada(itens, quem, quando, tipo=ENTRADA, local=FISICO, obs=""):
    """As linhas de movimento de um CONFIRMAR. `itens` = [(produto, qtd)]. Pura.

    Quantidade zero não grava linha: a posição que não entrou não aparece no
    histórico como se tivesse entrado.
    """
    lote = _id("L")
    sinal = -1 if tipo not in (ENTRADA,) else 1
    return [{"id": _id("M"), "lote": lote, "quando": quando, "tipo": tipo,
             "local": local, "produto_id": p["id"], "qtd": str(sinal * int(q)),
             "custo_unit": f'{numero(p.get("custo")):.2f}', "quem": quem,
             "obs": obs, "desfaz": ""}
            for p, q in itens if int(q or 0) > 0]


def linhas_de_saida(itens, destino, quem, quando, obs="", full=""):
    """As linhas de um bipe na SAÍDA. `itens` = [(produto, qtd)]. Pura.

    VENDA tira do físico. ENVIO PARA O FULL tira do físico e SOMA no Full
    da conta escolhida — duas linhas no mesmo lote, e o desfazer devolve as
    duas (Parte 2, 11/11).
    """
    if destino not in (VENDA, ENVIO_FULL):
        raise ValueError(f"destino de saída desconhecido: {destino!r}")
    if destino == ENVIO_FULL and full not in FULLS:
        raise ValueError(f"envio ao Full sem dizer qual: {full!r}")
    lote = _id("L")
    fora = []
    for p, q in itens:
        q = int(q or 0)
        if q <= 0:
            continue
        base = {"lote": lote, "quando": quando, "tipo": destino, "produto_id": p["id"],
                "custo_unit": f'{numero(p.get("custo")):.2f}', "quem": quem, "obs": obs,
                "desfaz": ""}
        fora.append({**base, "id": _id("M"), "local": FISICO, "qtd": str(-q)})
        if destino == ENVIO_FULL:
            fora.append({**base, "id": _id("M"), "local": full, "qtd": str(q)})
    return fora


def linhas_de_baixa(p, q, motivo, quem, quando, local=FISICO, volta=False,
                    obs="", pedido="", foto_id=""):
    """As linhas de uma quebra, descarte, doação ou devolução. Pura.

    QUEBRA, DESCARTE, DOAÇÃO: tiram do estoque (físico ou Full) e são PERDA.
    DEVOLUÇÃO que voltou BOA: soma no físico, e não é perda.
    DEVOLUÇÃO que voltou RUIM: a peça JÁ tinha saído na venda — tirar de
    novo deixaria o estoque uma peça abaixo do que existe. Ela entra e sai no
    mesmo lote (saldo não muda), e a linha de saída é a perda.
    """
    q = int(q or 0)
    if q <= 0:
        return []
    if motivo not in PERDAS + (DEVOLUCAO,):
        raise ValueError(f"motivo desconhecido: {motivo!r}")
    lote = _id("L")
    base = {"lote": lote, "quando": quando, "produto_id": p["id"],
            "custo_unit": f'{numero(p.get("custo")):.2f}', "quem": quem, "obs": obs,
            "desfaz": "", "pedido": pedido, "foto_id": foto_id}
    if motivo in PERDAS:
        return [{**base, "id": _id("M"), "tipo": motivo, "local": local, "qtd": str(-q)}]
    linhas = [{**base, "id": _id("M"), "tipo": DEVOLUCAO, "local": FISICO, "qtd": str(q)}]
    if not volta:
        linhas.append({**base, "id": _id("M"), "tipo": DESCARTE, "local": FISICO,
                       "qtd": str(-q), "obs": ("devolução que voltou ruim. " + obs).strip()})
    return linhas


def baixas_do_mes(movs, ano, mes):
    """As quebras, descartes, doações e devoluções do mês, sem as desfeitas. Pura.

    Devolve {"por_motivo": {motivo: valor a custo}, "voltaram": peças,
    "perda": total, "lotes": [lote mais novo primeiro]}.
    """
    chave = f"/{mes:02d}/{ano:04d}"
    desf = lotes_desfeitos(movs)
    tipos = PERDAS + (DEVOLUCAO,)
    por_motivo = {m: 0.0 for m in PERDAS}
    voltaram = 0
    lotes = {}
    for m in movs:
        if m.get("tipo") not in tipos or str(m.get("lote")) in desf:
            continue
        if chave not in str(m.get("quando") or "")[:10]:
            continue
        lotes.setdefault(str(m["lote"]), []).append(m)
    for linhas in lotes.values():
        perda = [m for m in linhas if m.get("tipo") in PERDAS]
        for m in perda:
            por_motivo[m["tipo"]] += -inteiro(m["qtd"]) * numero(m.get("custo_unit"))
        if not perda:
            voltaram += sum(inteiro(m["qtd"]) for m in linhas)
    # Mais nova em cima. No MESMO minuto, desempata pela ordem de gravação:
    # o `sorted` estável deixava a mais velha primeiro, e o "desfazer" da
    # linha de cima desfazia outra baixa (medido no navegador, 11/11).
    ordem = [ls for _i, ls in sorted(enumerate(lotes.values()),
                                     key=lambda t: (_ordem_quando(t[1][0].get("quando")), t[0]),
                                     reverse=True)]
    return {"por_motivo": por_motivo, "voltaram": voltaram,
            "perda": sum(por_motivo.values()), "lotes": ordem}


# ── PAINEL (Parte 5) ─────────────────────────────────────────────────────────

ATENCAO_DIAS, CRITICO_DIAS = 91, 152      # 3 e 5 meses (dono, 11/11)


def data_de(q):
    """'11/11/2026 14:02' → date, ou None. Pura."""
    import datetime as _dt
    try:
        return _dt.datetime.strptime(str(q or "")[:10], "%d/%m/%Y").date()
    except ValueError:
        return None


def faixa_de_idade(dias):
    """'ok', 'atencao' (3 a 5 meses) ou 'critico' (mais de 5). Pura."""
    if dias is None or dias < ATENCAO_DIAS:
        return "ok"
    return "atencao" if dias < CRITICO_DIAS else "critico"


def painel(produtos, movs, hoje):
    """Tudo o que o Painel mostra, numa passada só pelos movimentos. Pura.

    A IDADE conta do REGISTRO no Studio (dono, 11/11: "a partir do registro
    no sistema que ele irá começar a contar a vida útil"). Só entra na conta
    de parado o que ainda TEM peça: produto zerado não está parado.
    """
    saldo = saldos(movs)
    ult_saida = {}
    for m in movs:
        if m.get("tipo") in (VENDA, ENVIO_FULL) + PERDAS and inteiro(m.get("qtd")) < 0:
            d = data_de(m.get("quando"))
            pid = str(m.get("produto_id"))
            if d and (pid not in ult_saida or d > ult_saida[pid]):
                ult_saida[pid] = d
    linhas = []
    for p in ativos(produtos):
        fis = saldo.get((p["id"], FISICO), 0)
        full = no_full(saldo, p["id"])
        custo = numero(p.get("custo"))
        reg = data_de(p.get("registrado_em"))
        dias = (hoje - reg).days if reg else None
        linhas.append({"produto": p, "fisico": fis, "full": full, "custo": custo,
                       "por_full": {loc: saldo.get((p["id"], loc), 0) for loc in FULLS
                                    if saldo.get((p["id"], loc), 0)},
                       "valor": max(fis, 0) * custo + max(full, 0) * custo,
                       "dias": dias, "faixa": faixa_de_idade(dias),
                       "ultima_saida": ult_saida.get(p["id"])})
    com_peca = [l for l in linhas if l["fisico"] > 0 or l["full"] > 0]
    faixas = {f: sum(l["valor"] for l in com_peca if l["faixa"] == f) for f in ("ok", "atencao", "critico")}
    parados = sorted([l for l in com_peca if l["faixa"] != "ok"],
                     key=lambda l: (-(l["dias"] or 0), -l["valor"]))
    total = sum(l["valor"] for l in linhas)
    return {
        "linhas": linhas, "faixas": faixas, "parados": parados, "valor": total,
        "valor_fisico": sum(max(l["fisico"], 0) * l["custo"] for l in linhas),
        "valor_full": sum(max(l["full"], 0) * l["custo"] for l in linhas),
        "pecas_fisico": sum(max(l["fisico"], 0) for l in linhas),
        "pecas_full": sum(max(l["full"], 0) for l in linhas),
        "produtos": len(com_peca),
        "valor_parado": faixas["atencao"] + faixas["critico"],
    }


def lista_de_compra(produtos, movs, codigos, marcados):
    """A lista do Renan. Pura.

    Entra sozinho: (1) o que VENDEU e ficou com o físico em zero ou abaixo —
    a venda aconteceu sem peça; (2) o item que trava um kit. Sai sozinho
    quando o saldo volta a ficar positivo. `marcados` = {produto_id: data}
    de quem clicou "comprado": a marca vale enquanto ele seguir na lista.
    Devolve [{produto, motivo, comprado}].
    """
    saldo = saldos(movs)
    por_id = {p["id"]: p for p in ativos(produtos)}
    vendeu = {}
    for m in movs:
        if m.get("tipo") in (VENDA, ENVIO_FULL) and m.get("local") == FISICO and inteiro(m.get("qtd")) < 0:
            vendeu[str(m.get("produto_id"))] = vendeu.get(str(m.get("produto_id")), 0) + 1
    fora = {}
    for pid, n in vendeu.items():
        s = saldo.get((pid, FISICO), 0)
        if pid in por_id and s <= 0:
            fora[pid] = ("vendeu sem estoque" if s < 0 else "zerou na venda") + (
                f" · faltam {-s}" if s < 0 else "")
    for k in codigos:
        if k.get("tipo") != "kit":
            continue
        n, faltam = da_para_montar(itens_do_codigo(k), saldo)
        for pid in faltam:
            if pid in por_id and pid not in fora:
                fora[pid] = f'trava o kit «{k.get("nome")}»'
    return [{"produto": por_id[pid], "motivo": mot, "comprado": pid in marcados}
            for pid, mot in fora.items()]


# ── CONTAGEM (Parte 6) ───────────────────────────────────────────────────────

def contagem_aberta(contagens):
    """A contagem em andamento (sem `fechada_em`), ou None. Pura."""
    abertas = [c for c in contagens if not str(c.get("fechada_em") or "").strip()]
    return abertas[-1] if abertas else None


def contado_por_produto(contados, contagem_id):
    """{produto_id: total contado} — o mesmo produto em dois lugares SOMA. Pura."""
    t = {}
    for c in contados:
        if str(c.get("contagem")) == str(contagem_id):
            t[str(c["produto_id"])] = t.get(str(c["produto_id"]), 0) + inteiro(c.get("qtd"))
    return t


def quem_contou(contados, contagem_id):
    """{(quem, onde): peças} desta contagem, para 'quem está contando agora'. Pura."""
    t = {}
    for c in contados:
        if str(c.get("contagem")) == str(contagem_id):
            ch = (c.get("quem", ""), c.get("onde", ""))
            t[ch] = t.get(ch, 0) + inteiro(c.get("qtd"))
    return t


def fechamento(produtos, movs, contados, contagem_id):
    """O que a contagem achou contra o que o Studio diz. Pura.

    Só os CONTADOS entram no ajuste. Produto do Studio que ninguém contou
    aparece como "não contado" e NUNCA vira zero sozinho: esquecer uma
    prateleira não pode apagar o estoque dela.
    Devolve {"linhas": [{produto, sistema, contado, dif}], "nao_contados": [...],
    "bateu": n, "diferenca": n, "valor": R$ da diferença a custo}.
    """
    saldo = saldos(movs)
    cont = contado_por_produto(contados, contagem_id)
    linhas, nao = [], []
    for p in ativos(produtos):
        sis = saldo.get((p["id"], FISICO), 0)
        if p["id"] in cont:
            linhas.append({"produto": p, "sistema": sis, "contado": cont[p["id"]],
                           "dif": cont[p["id"]] - sis})
        elif sis:
            nao.append({"produto": p, "sistema": sis})
    dif = [l for l in linhas if l["dif"]]
    return {"linhas": sorted(linhas, key=lambda l: -abs(l["dif"])), "nao_contados": nao,
            "bateu": len(linhas) - len(dif), "diferenca": len(dif),
            "valor": sum(l["dif"] * numero(l["produto"].get("custo")) for l in dif)}


def linhas_de_ajuste(fech, quem, quando, contagem_id):
    """Os movimentos que põem o físico no que foi CONTADO. Pura."""
    lote = _id("L")
    return [{"id": _id("M"), "lote": lote, "quando": quando, "tipo": AJUSTE_CONTAGEM,
             "local": FISICO, "produto_id": l["produto"]["id"], "qtd": str(l["dif"]),
             "custo_unit": f'{numero(l["produto"].get("custo")):.2f}', "quem": quem,
             "obs": f"contagem {contagem_id}", "desfaz": ""}
            for l in fech["linhas"] if l["dif"]]


def marcados_de(linhas):
    """{produto_id: marcado_em} da aba de compras. Pura."""
    return {str(l.get("produto_id")): l.get("marcado_em") for l in linhas if l.get("produto_id")}


def _ordem_quando(q):
    """'11/11/2026 14:02' → '2026-11-11 14:02', para ordenar. Pura."""
    q = str(q or "")
    try:
        return f"{q[6:10]}-{q[3:5]}-{q[0:2]} {q[11:16]}"
    except Exception:
        return q


def da_para_montar(itens, saldo):
    """Quantos kits o estoque FÍSICO monta: o item mais curto manda. Pura.

    `itens` = {produto_id: qtd no kit}. Devolve (quantos, [ids que faltam]).
    """
    if not itens:
        return 0, []
    por_item = {pid: max(saldo.get((pid, FISICO), 0), 0) // q for pid, q in itens.items() if q > 0}
    n = min(por_item.values()) if por_item else 0
    return n, [pid for pid, k in por_item.items() if k == n and n == 0]


def custo_da_receita(itens, por_id):
    """O custo de um kit: a soma dos itens, a preço de custo. Pura."""
    return sum(numero(por_id.get(pid, {}).get("custo")) * q for pid, q in itens.items())


def itens_do_bipe(produtos, codigos, codigo):
    """O que UM bipe na saída tira do estoque. Pura.

    Devolve (itens, variacoes):
      · código gerado (quantidade ou kit) → a receita inteira, e [];
      · código de UM produto só          → [(produto, 1)], e [];
      · código com vários modelos         → [], e os modelos (a tela pergunta);
      · código desconhecido               → [], [].
    Dono, 11/11: "se for 2 unidades na saída, ela vai bipar os 2" — cada bipe
    é uma unidade, sem perguntar quantidade.
    """
    k = codigo_gerado(codigos, codigo)
    if k:
        por_id = {p["id"]: p for p in produtos}
        return [(por_id[pid], q) for pid, q in itens_do_codigo(k).items() if pid in por_id], []
    var = do_codigo(produtos, codigo)
    if len(var) == 1:
        return [(var[0], 1)], []
    return [], var


def codigos_da_janela(variacoes, codigos):
    """Os códigos de quantidade/kit do mesmo produto, para a janela. Pura."""
    if not variacoes:
        return []
    ean = limpar_codigo(variacoes[0].get("ean"))
    return [k for k in codigos if limpar_codigo(k.get("produto_ean")) == ean]


def linhas_que_desfazem(lote, movs, quem, quando):
    """O lote ao contrário: cada linha volta com o sinal trocado. Pura.

    Desfazer NÃO apaga: grava o contrário, e o histórico mostra os dois.
    Lote já desfeito devolve [] — clicar duas vezes não devolve em dobro.
    """
    lote = str(lote)
    if lote in lotes_desfeitos(movs):
        return []
    novo = _id("L")
    return [{"id": _id("M"), "lote": novo, "quando": quando, "tipo": DESFEITO,
             "local": m.get("local") or FISICO, "produto_id": m.get("produto_id"),
             "qtd": str(-inteiro(m.get("qtd"))), "custo_unit": m.get("custo_unit", ""),
             "quem": quem, "obs": f'desfaz {m.get("tipo")}', "desfaz": lote}
            for m in movs if str(m.get("lote")) == lote and m.get("tipo") != DESFEITO]


def linha_de_codigo(codigo, tipo, nome, produto_ean, itens, quem, quando, foto_id=""):
    """Uma linha de `estoque_codigos`. `itens` = {produto_id: qtd}. Pura."""
    return {"codigo": codigo, "tipo": tipo, "nome": str(nome or "").strip(),
            "produto_ean": limpar_codigo(produto_ean),
            "itens": json.dumps({k: int(v) for k, v in itens.items() if int(v) > 0},
                                ensure_ascii=False),
            "foto_id": foto_id, "criado_em": quando, "criado_por": quem}


def todos_os_codigos(produtos, codigos):
    return [p.get("ean") for p in produtos] + [k.get("codigo") for k in codigos]


# ── planilha (efeito) ────────────────────────────────────────────────────────

def _aba(nome, colunas):
    import sheets as _sh
    pl = _sh.planilha()
    try:
        return pl.worksheet(nome)
    except Exception:
        a = pl.add_worksheet(title=nome, rows=500, cols=len(colunas))
        a.append_row(colunas, value_input_option="RAW")
        return a


def _ler(nome, colunas):
    return linhas_para_dicts(_aba(nome, colunas).get_all_values(), colunas)


def _carregar_sem_cache():
    return (_ler(ABA_PRODUTOS, COL_PRODUTOS), _ler(ABA_MOV, COL_MOV),
            _ler(ABA_CODIGOS, COL_CODIGOS))


def _compras_sem_cache():
    return _ler(ABA_COMPRAS, COL_COMPRAS)


def _contagem_sem_cache():
    return _ler(ABA_CONTAGENS, COL_CONTAGENS), _ler(ABA_CONTADOS, COL_CONTADOS)


try:
    import streamlit as _st
    carregar = _st.cache_data(ttl=120, show_spinner=False)(_carregar_sem_cache)
    compras = _st.cache_data(ttl=120, show_spinner=False)(_compras_sem_cache)
    # 20 s, e não 2 min: com várias pessoas contando, o fechamento precisa
    # ver o que o celular do outro acabou de gravar.
    contagem = _st.cache_data(ttl=20, show_spinner=False)(_contagem_sem_cache)
except Exception:          # fora do Streamlit (auto-teste)
    carregar = _carregar_sem_cache
    compras = _compras_sem_cache
    contagem = _contagem_sem_cache


def _limpar_cache():
    for f in (carregar, compras, contagem):
        try:
            f.clear()
        except Exception:
            pass


def cabecalho_completo(cab_da_aba, colunas):
    """O cabeçalho da aba com as colunas que faltam no FIM. Pura.

    A aba nasceu com as colunas daquele dia; a Parte 3 trouxe `pedido` e
    `foto_id`. Escrever pela ordem de `colunas` numa aba de cabeçalho velho
    poria o pedido embaixo de outra coluna — então a coluna nova entra no
    fim do cabeçalho, e a linha se escreve pelo cabeçalho DA ABA.
    """
    cab = [str(c).strip() for c in cab_da_aba if str(c).strip()]
    return cab + [c for c in colunas if c not in cab]


def _anexar(nome, colunas, linhas):
    if not linhas:
        return 0
    a = _aba(nome, colunas)
    atual = a.row_values(1)
    cab = cabecalho_completo(atual, colunas)
    if cab != [str(c).strip() for c in atual]:
        if a.col_count < len(cab):
            a.add_cols(len(cab) - a.col_count)
        a.update(values=[cab], range_name="A1", value_input_option="RAW")
    a.append_rows([[str(l.get(c, "")) for c in cab] for l in linhas],
                  value_input_option="RAW")
    _limpar_cache()
    return len(linhas)


def gravar_produtos(linhas):
    return _anexar(ABA_PRODUTOS, COL_PRODUTOS, linhas)


def gravar_movimentos(linhas):
    return _anexar(ABA_MOV, COL_MOV, linhas)


def abrir_contagem(quem, quando):
    cid = _id("C")
    _anexar(ABA_CONTAGENS, COL_CONTAGENS, [{"id": cid, "aberta_em": quando, "aberta_por": quem}])
    return cid


def fechar_contagem(contagem_id, quem, quando):
    return _atualizar(ABA_CONTAGENS, COL_CONTAGENS, "id",
                      {contagem_id: {"fechada_em": quando, "fechada_por": quem}})


def gravar_contado(contagem_id, produto_id, qtd, onde, quem, quando):
    return _anexar(ABA_CONTADOS, COL_CONTADOS, [{"contagem": contagem_id, "produto_id": produto_id,
                                                 "qtd": str(int(qtd)), "onde": onde, "quem": quem,
                                                 "quando": quando}])


def marcar_comprado(produto_id, quem, quando):
    return _anexar(ABA_COMPRAS, COL_COMPRAS,
                   [{"produto_id": produto_id, "marcado_em": quando, "quem": quem}])


def gravar_codigo(linha):
    return _anexar(ABA_CODIGOS, COL_CODIGOS, [linha])


def atualizar_produtos(mudancas):
    """`mudancas` = {produto_id: {coluna: valor}}. Reescreve só as células."""
    return _atualizar(ABA_PRODUTOS, COL_PRODUTOS, "id", mudancas)


def atualizar_codigos(mudancas):
    """`mudancas` = {codigo: {coluna: valor}} — renomear um kit (Parte 4)."""
    return _atualizar(ABA_CODIGOS, COL_CODIGOS, "codigo", mudancas)


def _atualizar(nome, colunas, chave, mudancas):
    """Reescreve só as células mudadas, achando a linha pela `chave`.

    Lê a aba na hora (e não do cache): outra pessoa pode ter cadastrado
    alguma coisa desde a última leitura, e a linha certa é a de AGORA.
    """
    if not mudancas:
        return 0
    a = _aba(nome, colunas)
    valores = a.get_all_values()
    cab = [str(c).strip() for c in valores[0]] if valores else colunas
    i_id = cab.index(chave)
    celulas = []
    import gspread.utils as _gu
    for n, linha in enumerate(valores[1:], start=2):
        pid = linha[i_id] if i_id < len(linha) else ""
        for col, val in mudancas.get(pid, {}).items():
            if col in cab:
                celulas.append({"range": _gu.rowcol_to_a1(n, cab.index(col) + 1),
                                "values": [[str(val)]]})
    if celulas:
        a.batch_update(celulas, value_input_option="RAW")
    _limpar_cache()
    return len(celulas)


def salvar_foto(dados, nome):
    """A foto no Drive, já convertida e reduzida. Devolve (file_id, erro).

    Qualquer formato entra (HEIC do iPhone inclusive) — `imagem.normalizar_imagem`
    é a porta única do Studio para isso. Depois, reduz para 800 px: a foto
    aparece pequena na tela, e uma de 10 MB atrasaria cada bipe.
    """
    import io
    import gdrive
    import imagem
    try:
        b, _mime, _ext = imagem.normalizar_imagem(dados)
        from PIL import Image
        im = Image.open(io.BytesIO(b))
        im.thumbnail((800, 800))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="JPEG", quality=85)
        b = buf.getvalue()
    except Exception as e:
        return "", f"não consegui abrir a foto ({e})"
    info, erro = gdrive.upload(b, f"estoque_{nome}.jpg", gdrive.pasta_estoque_id(),
                               mimetype="image/jpeg")
    if erro:
        return "", erro
    return info["id"], None


if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # Código de barras: os zeros da frente ficam, o espaço sai.
    ok("limpar_codigo: tira espaço, mantém o zero da frente",
       limpar_codigo(" 0789 1234\n") == "07891234")
    ok("numero: formato brasileiro e com R$",
       numero("R$ 1.234,50") == 1234.5 and numero("18,40") == 18.4 and numero("18.4") == 18.4
       and numero("") == 0.0)

    # EAN-13: o dígito verificador confere com códigos REAIS de mercado (os
    # dois primeiros são de livros com ISBN impresso; o terceiro é o
    # exemplo da norma GS1).
    ok("digito_ean13: confere com códigos reais",
       ean13_valido("9788535902778") and ean13_valido("9780306406157")
       and ean13_valido("4006381333931") and not ean13_valido("4006381333932"))
    m = modulos_ean13("4006381333931")
    ok("modulos_ean13: 95 módulos, guardas nas pontas e no meio",
       len(m) == 95 and m.startswith("101") and m.endswith("101") and m[45:50] == "01010")
    # Cada dígito tem 2 barras e 2 espaços, e 7 módulos: a regra que todo
    # leitor usa para se achar. Se a tabela tivesse um dígito errado, um
    # deles sairia com 1 ou 3 barras.
    def _barras(c):
        return sum(1 for i, b in enumerate(c) if b == "1" and (i == 0 or c[i - 1] == "0"))
    ok("modulos_ean13: todo dígito tem 2 barras em 7 módulos",
       all(_barras(c) == 2 and len(c) == 7 for c in _L + _G + _R))
    ok("svg_ean13: com margem e com o número embaixo",
       svg_ean13("4006381333931").startswith("<svg") and ">4006381333931<" in svg_ean13("4006381333931"))
    try:
        svg_ean13("123")
        ok("svg_ean13: recusa código inválido", False)
    except ValueError:
        ok("svg_ean13: recusa código inválido", True)

    c1 = novo_codigo_interno([])
    c2 = novo_codigo_interno([c1, "7891234567895"])
    ok("novo_codigo_interno: prefixo 20, válido, e o seguinte não repete",
       c1.startswith("20") and ean13_valido(c1) and ean13_valido(c2) and c2 != c1
       and int(c2[2:12]) == int(c1[2:12]) + 1)

    # A planilha lida como TEXTO: o zero da frente sobrevive, e a coluna
    # movida à mão não troca um campo pelo outro.
    vals = [["nome", "id", "ean", "custo"], ["Bailarina", "P1", "0789000000017", "18.40"],
            ["", "", "", ""]]
    d = linhas_para_dicts(vals, COL_PRODUTOS)
    ok("linhas_para_dicts: lê pelo cabeçalho da aba, mantém o zero, pula linha vazia",
       len(d) == 1 and d[0]["ean"] == "0789000000017" and d[0]["nome"] == "Bailarina"
       and d[0]["variacao"] == "")

    # A LEITURA DE VERDADE (`_ler`), com uma aba que se comporta como o
    # gspread: `get_all_records` converte o código em número e o zero some.
    class _AbaFalsa:
        def get_all_values(self):
            return [["id", "ean"], ["P1", "0789000000011"]]

        def get_all_records(self):
            return [{"id": "P1", "ean": 789000000011}]
    _real_aba = globals()["_aba"]
    globals()["_aba"] = lambda nome, colunas: _AbaFalsa()
    try:
        _lido = _ler(ABA_PRODUTOS, COL_PRODUTOS)
    except Exception:
        _lido = []
    finally:
        globals()["_aba"] = _real_aba
    ok("_ler: o código chega da planilha com o zero da frente",
       len(_lido) == 1 and _lido[0]["ean"] == "0789000000011")

    # A GRAVAÇÃO DE VERDADE, numa aba falsa que guarda o que recebeu: as
    # colunas na ordem do cabeçalho, RAW (o código não vira número), e a
    # célula certa na edição — a linha 3 é a do segundo produto.
    class _AbaGrava:
        def __init__(self, valores):
            self.valores, self.anexado, self.celulas, self.modo = valores, [], [], None

        def get_all_values(self):
            return self.valores

        def row_values(self, n):
            return list(self.valores[n - 1]) if len(self.valores) >= n else []

        col_count = 11

        def add_cols(self, n):
            self.col_count += n

        def update(self, values=None, range_name=None, value_input_option=None):
            valores = values
            self.cabecalho_novo = valores[0]
            self.valores[0] = list(valores[0])

        def append_rows(self, linhas, value_input_option=None):
            self.anexado += linhas
            self.modo = value_input_option

        def batch_update(self, celulas, value_input_option=None):
            self.celulas += celulas
            self.modo = value_input_option
    _ab = _AbaGrava([COL_PRODUTOS, ["P1"] + [""] * 9, ["P2"] + [""] * 9])
    globals()["_aba"] = lambda nome, colunas: _ab
    try:
        _n1 = gravar_produtos([{"id": "P3", "ean": "0789000000011", "nome": "Óculos"}])
        _n2 = gravar_movimentos([])
        _n3 = atualizar_produtos({"P2": {"variacao": "Sentada"}, "PX": {"nome": "x"}})
        _n4 = gravar_codigo({"codigo": "2000000000015"})
    finally:
        globals()["_aba"] = _real_aba
    ok("gravar_produtos: na ordem das colunas, como texto (RAW)",
       _n1 == 1 and _ab.anexado[0][:2] == ["P3", "0789000000011"] and _ab.anexado[0][3] == "Óculos")
    ok("gravar_movimentos: lista vazia não toca a planilha", _n2 == 0)
    _abc = _AbaGrava([list(COL_COMPRAS)])
    globals()["_aba"] = lambda nome, colunas: _abc
    try:
        marcar_comprado("P9", "renan", "11/11/2026 16:00")
    finally:
        globals()["_aba"] = _real_aba
    _abg = _AbaGrava([list(COL_CONTAGENS)])
    _abd = _AbaGrava([list(COL_CONTADOS)])
    globals()["_aba"] = lambda nome, colunas: _abg if nome == ABA_CONTAGENS else _abd
    try:
        _cid = abrir_contagem("leo", "11/11/2026 08:00")
        _abg.valores.append(_abg.anexado[0])
        _fz = fechar_contagem(_cid, "leo", "11/11/2026 18:00")
        gravar_contado(_cid, "P1", 3.0, "Prateleira B", "my", "11/11/2026 09:00")
    finally:
        globals()["_aba"] = _real_aba
    ok("abrir_contagem / fechar_contagem / gravar_contado: grava, acha a linha (D2, E2) e a quantidade inteira",
       _cid.startswith("C") and _fz == 2
       and [c["range"] for c in _abg.celulas] == ["D2", "E2"]
       and _abd.anexado == [[_cid, "P1", "3", "Prateleira B", "my", "11/11/2026 09:00"]])
    ok("marcar_comprado: grava produto, quando e quem, e marcados_de lê de volta",
       _abc.anexado == [["P9", "11/11/2026 16:00", "renan"]]
       and marcados_de([dict(zip(COL_COMPRAS, _abc.anexado[0]))]) == {"P9": "11/11/2026 16:00"})
    ok("atualizar_produtos: só a célula da variação do P2 (E3), e id desconhecido não grava",
       _n3 == 1 and _ab.celulas == [{"range": "E3", "values": [["Sentada"]]}] and _ab.modo == "RAW")
    _abk = _AbaGrava([COL_CODIGOS, ["2000000000015", "kit", "Kit velho"] + [""] * 5])
    globals()["_aba"] = lambda nome, colunas: _abk
    try:
        _nk = atualizar_codigos({"2000000000015": {"nome": "Kit Embaralhador + 2 baralhos"}})
    finally:
        globals()["_aba"] = _real_aba
    ok("atualizar_codigos: acha o kit pelo código e troca só o nome (C2)",
       _nk == 1 and _abk.celulas == [{"range": "C2", "values": [["Kit Embaralhador + 2 baralhos"]]}])
    ok("gravar_codigo: uma linha", _n4 == 1 and "2000000000015" in _ab.anexado[-1])
    # A ABA VELHA: o cabeçalho de 11/11 manhã, sem `pedido` e `foto_id`. A
    # linha nova se escreve pelo cabeçalho DA ABA, e as colunas entram no fim.
    # E com duas colunas trocadas à mão (lote antes de id): escrever pela
    # ordem do código poria o id embaixo de «lote».
    _velho = ["lote", "id", "quando", "tipo", "local", "produto_id", "qtd",
              "custo_unit", "quem", "obs", "desfaz"]
    _abm = _AbaGrava([list(_velho)])
    globals()["_aba"] = lambda nome, colunas: _abm
    try:
        gravar_movimentos([{"id": "M1", "tipo": "quebra", "qtd": "-1", "pedido": "ML 9", "foto_id": "F"}])
    finally:
        globals()["_aba"] = _real_aba
    ok("_anexar: aba de cabeçalho velho ganha as colunas no fim, e a linha cai embaixo delas",
       _abm.valores[0] == _velho + ["pedido", "foto_id"] and _abm.col_count == 13
       and _abm.anexado[0][1] == "M1" and _abm.anexado[0][0] == "" and _abm.anexado[0][6] == "-1"
       and _abm.anexado[0][11:] == ["ML 9", "F"])
    ok("todos_os_codigos: os de produto e os gerados, para o gerador não repetir",
       todos_os_codigos([{"ean": "A"}], [{"codigo": "B"}]) == ["A", "B"])

    # A FOTO: qualquer formato entra pela porta única (`normalizar_imagem`),
    # sai JPEG de no máximo 800 px e vai para a pasta do ESTOQUE.
    import io as _io_t
    import sys as _sys_t
    import types as _types_t
    from PIL import Image as _Im
    _png = _io_t.BytesIO()
    _Im.new("RGB", (2400, 1200), (200, 30, 30)).save(_png, format="PNG")
    _enviado = {}
    _f_img = _types_t.ModuleType("imagem")
    _f_img.normalizar_imagem = lambda b: (_enviado.setdefault("normalizou", True) and b, "image/png", "png")
    _f_gd = _types_t.ModuleType("gdrive")
    _f_gd.pasta_estoque_id = lambda: "PASTA_ESTOQUE"
    _f_gd.upload = lambda b, nome, pasta, mimetype=None: (
        _enviado.update(b=b, nome=nome, pasta=pasta) or ({"id": "F1"}, None))
    _reais = {k: _sys_t.modules.get(k) for k in ("imagem", "gdrive")}
    _sys_t.modules.update(imagem=_f_img, gdrive=_f_gd)
    try:
        _fid, _err = salvar_foto(_png.getvalue(), "0789")
    finally:
        for k, v in _reais.items():
            if v is None:
                _sys_t.modules.pop(k, None)
            else:
                _sys_t.modules[k] = v
    _sai = _Im.open(_io_t.BytesIO(_enviado.get("b", b"")))
    ok("salvar_foto: passa pelo conversor, sai JPEG de até 800 px, na pasta do estoque",
       _fid == "F1" and _err is None and _enviado.get("normalizou") and _sai.format == "JPEG"
       and max(_sai.size) == 800 and _enviado["pasta"] == "PASTA_ESTOQUE")

    # O caminho inteiro de um cadastro com três posições, uma entrada e o
    # desfazer — com o NOME REAL que a equipe digita (passo 13).
    prods = linhas_de_produto("7899999000061", "MBLN-06", "Bailarina  de resina (P/M) + base",
                              "18,40".replace(",", "."), [("Braço para cima", "f1"),
                                                          ("Perna estendida", ""), ("Sentada", "")],
                              "leo", "11/11/2026 14:02")
    ok("linhas_de_produto: uma linha por variação, mesmo código, ids diferentes",
       len(prods) == 3 and len({p["id"] for p in prods}) == 3
       and all(p["ean"] == "7899999000061" for p in prods) and prods[0]["custo"] == "18.40")
    ok("do_codigo: o bipe acha as três posições, com espaço no meio do bipe",
       len(do_codigo(prods, "7899 9990 00061")) == 3 and do_codigo(prods, "") == [])
    ent = linhas_de_entrada([(prods[0], 6), (prods[1], 0), (prods[2], 6)], "leo", "11/11/2026 14:03")
    ok("linhas_de_entrada: quantidade zero não grava, o lote é um só",
       len(ent) == 2 and len({e["lote"] for e in ent}) == 1 and ent[0]["qtd"] == "6")
    s = saldos(ent)
    ok("saldos: soma por produto e por local",
       s[(prods[0]["id"], FISICO)] == 6 and (prods[1]["id"], FISICO) not in s)
    des = linhas_que_desfazem(ent[0]["lote"], ent, "leo", "11/11/2026 14:05")
    s2 = saldos(ent + des)
    ok("linhas_que_desfazem: devolve tudo, e não apaga a entrada",
       len(des) == 2 and s2[(prods[0]["id"], FISICO)] == 0 and s2[(prods[2]["id"], FISICO)] == 0)
    ok("linhas_que_desfazem: desfazer duas vezes não devolve em dobro",
       linhas_que_desfazem(ent[0]["lote"], ent + des, "leo", "x") == [])
    ok("lotes_desfeitos: o lote da entrada, e só ele",
       lotes_desfeitos(ent + des) == {ent[0]["lote"]} and lotes_desfeitos(ent) == set())
    lt = ultimos_lotes(ent + des, ENTRADA)
    ok("ultimos_lotes: o lote desfeito aparece marcado",
       len(lt) == 1 and lt[0]["desfeito"] and len(lt[0]["linhas"]) == 2)

    k = linha_de_codigo(c1, "quantidade", "Kit com 3 (1 de cada)", "7899999000061",
                        {p["id"]: 1 for p in prods}, "leo", "x")
    ok("codigo gerado: a receita volta igual, e não é produto",
       itens_do_codigo(k) == {p["id"]: 1 for p in prods}
       and codigo_gerado([k], c1) is k and do_codigo(prods, c1) == [])
    ok("nome_completo: nome · variação",
       nome_completo(prods[0]) == "Bailarina  de resina (P/M) + base · Braço para cima")

    # SAÍDA (Parte 2): cada bipe é uma unidade; o código com vários modelos
    # pergunta; o código gerado tira a receita; o Full soma do outro lado.
    _k3 = linha_de_codigo("2000000000022", "quantidade", "Kit com 3", "7899999000061",
                          {p["id"]: 1 for p in prods}, "leo", "x")
    _it, _var = itens_do_bipe(prods, [_k3], "2000000000022")
    ok("itens_do_bipe: código gerado tira 1 de cada posição, sem perguntar",
       sorted(q for _p, q in _it) == [1, 1, 1] and _var == [])
    _it, _var = itens_do_bipe(prods, [_k3], "7899999000061")
    ok("itens_do_bipe: código com 3 modelos não tira nada e devolve os modelos",
       _it == [] and len(_var) == 3)
    _um = linhas_de_produto("4006381333931", "", "Embaralhador", 42, [("", "")], "leo", "x")
    _it, _var = itens_do_bipe(_um, [], "4006381333931")
    ok("itens_do_bipe: código de um produto só tira 1", _it == [(_um[0], 1)] and _var == [])
    ok("itens_do_bipe: desconhecido não tira nada", itens_do_bipe(_um, [], "123") == ([], []))
    _v = linhas_de_saida([(_um[0], 2)], VENDA, "leo", "x")
    _f = linhas_de_saida([(_um[0], 1)], ENVIO_FULL, "leo", "x", full="full_ml1")
    _s = saldos(linhas_de_entrada([(_um[0], 10)], "leo", "x") + _v + _f)
    ok("linhas_de_saida: venda tira do físico; Full tira do físico e soma no Full",
       _s[(_um[0]["id"], FISICO)] == 7 and _s[(_um[0]["id"], "full_ml1")] == 1
       and len(_f) == 2 and len({l["lote"] for l in _f}) == 1)
    _d = linhas_que_desfazem(_f[0]["lote"], _f, "leo", "y")
    _s2 = saldos(_f + _d)
    ok("desfazer o envio ao Full devolve os dois lados",
       _s2[(_um[0]["id"], FISICO)] == 0 and _s2[(_um[0]["id"], "full_ml1")] == 0)
    try:
        linhas_de_saida([(_um[0], 1)], ENVIO_FULL, "leo", "x")
        ok("linhas_de_saida: envio ao Full sem dizer qual é recusado", False)
    except ValueError:
        ok("linhas_de_saida: envio ao Full sem dizer qual é recusado", True)
    _s4 = saldos(linhas_de_saida([(_um[0], 2)], ENVIO_FULL, "l", "x", full="full_ml1")
                 + linhas_de_saida([(_um[0], 3)], ENVIO_FULL, "l", "x", full="full_shopee2")
                 + linhas_de_entrada([(_um[0], 4)], "l", "x", local="full_ml4"))
    ok("no_full: soma os Full de todas as contas, e cada um fica separado do físico",
       no_full(_s4, _um[0]["id"]) == 9 and _s4[(_um[0]["id"], FISICO)] == -5
       and _s4[(_um[0]["id"], "full_shopee2")] == 3 and eh_full("full_shopee1") and not eh_full(FISICO))
    ok("codigos_da_janela: os códigos gerados do mesmo produto",
       codigos_da_janela(prods, [_k3]) == [_k3] and codigos_da_janela(_um, [_k3]) == [])

    # QUEBRA · DESCARTE · DOAÇÃO · DEVOLUÇÃO (Parte 3).
    _e = linhas_de_entrada([(_um[0], 10)], "leo", "05/11/2026 09:00")
    _qb = linhas_de_baixa(_um[0], 1, QUEBRA, "leo", "11/11/2026 14:00", obs="caiu")
    _dv_bom = linhas_de_baixa(_um[0], 2, DEVOLUCAO, "my", "11/11/2026 15:00", volta=True, pedido="ML 1")
    _dv_ruim = linhas_de_baixa(_um[0], 1, DEVOLUCAO, "my", "10/11/2026 15:00", volta=False)
    _doa_full = linhas_de_baixa(_um[0], 1, DOACAO, "leo", "09/11/2026 10:00", local="full_ml2")
    _s3 = saldos(_e + _qb + _dv_bom + _dv_ruim + _doa_full)
    ok("linhas_de_baixa: quebra tira, devolução boa soma, devolução ruim não mexe, doação do Full",
       _s3[(_um[0]["id"], FISICO)] == 10 - 1 + 2 and _s3[(_um[0]["id"], "full_ml2")] == -1)
    _bm = baixas_do_mes(_e + _qb + _dv_bom + _dv_ruim + _doa_full
                        + linhas_de_baixa(_um[0], 5, QUEBRA, "leo", "30/10/2026 10:00"), 2026, 11)
    ok("baixas_do_mes: perda a custo por motivo, só do mês, devolução boa conta peças",
       _bm["por_motivo"] == {QUEBRA: 42.0, DESCARTE: 42.0, DOACAO: 42.0} and _bm["voltaram"] == 2
       and _bm["perda"] == 126.0 and len(_bm["lotes"]) == 4
       and _bm["lotes"][0][0]["quando"] == "11/11/2026 15:00")
    _mesmo_min = [linhas_de_baixa(_um[0], 1, QUEBRA, "leo", "11/11/2026 14:00", obs=str(i))
                  for i in range(3)]
    ok("baixas_do_mes: no mesmo minuto, a gravada por último fica em cima",
       [ls[0]["obs"] for ls in baixas_do_mes(sum(_mesmo_min, []), 2026, 11)["lotes"]] == ["2", "1", "0"])
    _dz = linhas_que_desfazem(_qb[0]["lote"], _qb, "leo", "x")
    ok("baixas_do_mes: a quebra desfeita sai da perda",
       baixas_do_mes(_qb + _dz, 2026, 11)["perda"] == 0)
    # KITS (Parte 4): o item mais curto manda, e o que zerou é o que falta.
    _sk = {("A", FISICO): 11, ("B", FISICO): 30, ("C", FISICO): 1}
    ok("da_para_montar: o item mais curto manda (2 de C por kit, só 1 em estoque → 0, falta C)",
       da_para_montar({"A": 1, "B": 2}, _sk) == (11, []) and da_para_montar({"A": 1, "C": 2}, _sk) == (0, ["C"])
       and da_para_montar({}, _sk) == (0, []) and da_para_montar({"Z": 1}, _sk) == (0, ["Z"]))
    ok("custo_da_receita: soma a custo",
       custo_da_receita({"A": 1, "B": 2}, {"A": {"custo": "42.00"}, "B": {"custo": "4,90"}}) == 51.8)
    # PAINEL (Parte 5): idade do registro, faixas, Full separado, e a lista
    # do Renan entrando e saindo sozinha.
    import datetime as _dtp
    _hoje = _dtp.date(2026, 11, 11)
    _pp = (linhas_de_produto("1", "", "Óculos aviador", 15, [("", "")], "l", "01/05/2026 10:00")
           + linhas_de_produto("2", "", "Glass Chess", 60, [("", "")], "l", "20/07/2026 10:00")
           + linhas_de_produto("3", "", "Leão", 10, [("", "")], "l", "05/11/2026 10:00")
           + linhas_de_produto("4", "", "Mini Yoga", 12.9, [("", "")], "l", "05/11/2026 10:00"))
    _mm = (linhas_de_entrada([(_pp[0], 40), (_pp[1], 9), (_pp[2], 3), (_pp[3], 1)], "l", "05/11/2026 10:00")
           + linhas_de_saida([(_pp[2], 1)], ENVIO_FULL, "l", "06/11/2026 10:00", full="full_shopee1")
           + linhas_de_saida([(_pp[3], 2)], VENDA, "l", "10/11/2026 10:00"))
    _pn = painel(_pp, _mm, _hoje)
    ok("painel: valor físico e Full a custo; o Mini Yoga negativo não entra no valor",
       _pn["valor_fisico"] == 40 * 15 + 9 * 60 + 2 * 10 and _pn["valor_full"] == 10
       and _pn["pecas_full"] == 1 and _pn["produtos"] == 3
       and [l["por_full"] for l in _pn["linhas"] if l["produto"]["nome"] == "Leão"] == [{"full_shopee1": 1}])
    ok("painel: 6 meses é crítico, 4 meses é atenção, e o recém-chegado não está parado",
       _pn["faixas"] == {"ok": 30.0, "atencao": 540.0, "critico": 600.0}
       and [l["produto"]["nome"] for l in _pn["parados"]] == ["Óculos aviador", "Glass Chess"]
       and _pn["valor_parado"] == 1140.0)
    ok("painel: última saída por produto",
       {l["produto"]["nome"]: l["ultima_saida"] for l in _pn["linhas"]}["Mini Yoga"] == _dtp.date(2026, 11, 10))
    _kp = linha_de_codigo("2000000000039", "kit", "Kit Pôquer", "", {_pp[1]["id"]: 10}, "l", "x")
    _lc = lista_de_compra(_pp, _mm, [_kp], {})
    ok("lista_de_compra: vendeu sem estoque (faltam 1) e o item que trava o kit",
       {(l["produto"]["nome"], l["motivo"]) for l in _lc}
       == {("Mini Yoga", "vendeu sem estoque · faltam 1"), ("Glass Chess", "trava o kit «Kit Pôquer»")})
    _mm2 = _mm + linhas_de_entrada([(_pp[3], 5)], "l", "11/11/2026 09:00")
    _lc2 = lista_de_compra(_pp, _mm2, [], marcados_de([{"produto_id": _pp[3]["id"], "marcado_em": "x"}]))
    ok("lista_de_compra: a entrada tira o produto da lista sozinha", _lc2 == [])
    ok("lista_de_compra: a marca de comprado aparece enquanto está na lista",
       lista_de_compra(_pp, _mm, [], {_pp[3]["id"]: "x"})[0]["comprado"])
    ok("faixa_de_idade: as bordas de 3 e 5 meses",
       [faixa_de_idade(d) for d in (None, 90, 91, 151, 152)] == ["ok", "ok", "atencao", "atencao", "critico"])
    # CONTAGEM (Parte 6): duas pessoas, o mesmo produto em dois lugares soma;
    # o que ninguém contou não zera; o ajuste põe o físico no contado.
    _cc = [{"id": "C1", "fechada_em": "x"}, {"id": "C2", "fechada_em": ""}]
    ok("contagem_aberta: a sem data de fechamento", contagem_aberta(_cc)["id"] == "C2"
       and contagem_aberta(_cc[:1]) is None)
    _ct = [{"contagem": "C2", "produto_id": _pp[0]["id"], "qtd": "30", "onde": "A", "quem": "leo"},
           {"contagem": "C2", "produto_id": _pp[0]["id"], "qtd": "6", "onde": "B", "quem": "my"},
           {"contagem": "C2", "produto_id": _pp[1]["id"], "qtd": "9", "onde": "B", "quem": "my"},
           {"contagem": "C1", "produto_id": _pp[1]["id"], "qtd": "99", "onde": "B", "quem": "my"}]
    ok("contado_por_produto: soma os dois lugares, e só desta contagem",
       contado_por_produto(_ct, "C2") == {_pp[0]["id"]: 36, _pp[1]["id"]: 9})
    ok("quem_contou: por pessoa e lugar", quem_contou(_ct, "C2")[("my", "B")] == 15)
    _fc = fechamento(_pp, _mm, _ct, "C2")
    ok("fechamento: óculos 40 → 36 é diferença; Glass Chess bateu; os outros não foram contados",
       _fc["bateu"] == 1 and _fc["diferenca"] == 1 and _fc["valor"] == -60.0
       and {l["produto"]["nome"] for l in _fc["nao_contados"]} == {"Leão", "Mini Yoga"})
    _aj = linhas_de_ajuste(_fc, "leo", "11/11/2026 18:00", "C2")
    _sa = saldos(_mm + _aj)
    ok("linhas_de_ajuste: o físico vira o contado, e o não contado fica como estava",
       len(_aj) == 1 and _sa[(_pp[0]["id"], FISICO)] == 36 and _sa[(_pp[2]["id"], FISICO)] == 2
       and _sa[(_pp[3]["id"], FISICO)] == -1)
    ok("FULLS e NOME_LOCAL: as seis contas do Bling, todas Full, e o nome de cada local",
       list(FULLS) == ["full_ml1", "full_ml2", "full_ml3", "full_ml4", "full_shopee1", "full_shopee2"]
       and all(eh_full(k) for k in FULLS) and NOME_LOCAL[FISICO] == "físico"
       and NOME_LOCAL["full_shopee2"] == "Full Shopee 2" and NOME_LOCAL[FULL] == "Full (sem conta)")
    ok("ativos: o produto desativado sai, o sem coluna fica",
       [p["id"] for p in ativos([{"id": "a", "ativo": "1"}, {"id": "b", "ativo": "0"}, {"id": "c"}])] == ["a", "c"])
    ok("PERDAS: quebra, descarte e doação — devolução NÃO é perda por si",
       PERDAS == (QUEBRA, DESCARTE, DOACAO) and DEVOLUCAO not in PERDAS)
    ok("cabecalho_completo: coluna nova entra no fim, a ordem velha fica",
       cabecalho_completo(["id", "lote", "x"], ["id", "pedido", "lote"]) == ["id", "lote", "x", "pedido"])
    try:
        linhas_de_baixa(_um[0], 1, "roubo", "leo", "x")
        ok("linhas_de_baixa: motivo desconhecido é recusado", False)
    except ValueError:
        ok("linhas_de_baixa: motivo desconhecido é recusado", True)

    print("\n" + ("TUDO OK" if not falhas else f"{falhas} FALHA(S)"))
    raise SystemExit(1 if falhas else 0)
