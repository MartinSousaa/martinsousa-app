"""fatura_inter.py — a fatura do cartão do Inter, que vem num CSV torto.

O FORMATO, CONFERIDO NO ARQUIVO DE OUTUBRO/2026
-----------------------------------------------
O Inter exporta a fatura com a linha inteira entre aspas e cada campo com
aspas dobradas dentro dela, terminando em aspas-e-ponto-e-vírgula — e o que vem DEPOIS do
ponto e vírgula é anotação de quem editou o arquivo:

    <linha>  <aspas>16/09/2026<aspas> , <aspas>•••• 1924<aspas> ,
    <aspas>ZUL 1 cartao 2DKM8I<aspas> , <aspas>TRANSPORTE<aspas> ,
    <aspas>Compra à vista<aspas> , <aspas>-R$ 6,95<aspas>  </linha> ; Estacionamento

Um leitor de CSV comum devolve uma coluna só, com o texto cru. Por isso os
campos saem por expressão regular: os grupos entre aspas dobradas, na ordem.

O QUE A FATURA TEM E O EXTRATO NÃO
----------------------------------
- **Parcela.** "Parcela 7/10" diz que a compra foi em março e ainda tem três
  meses para vencer. É o que permite ligar a parcela à compra original — e
  saber que o gasto do mês não é uma compra nova.
- **Categoria do banco.** TRANSPORTE, SERVICOS, COMPRAS. Serve de pista, mas
  não de resposta: "MERCADOLIVRE 4PRODUTOS" vem como OUTROS, e o que aquilo
  foi só o dono sabe.
- **Pagamento da fatura anterior**, positivo, no meio dos lançamentos. Não é
  compra e não pode entrar como gasto: a fatura já foi contada quando o débito
  saiu da conta.
"""

import re

# Os grupos entre aspas dobradas, na ordem em que o Inter escreve.
_CAMPO = re.compile(r'""(.*?)""')

# Linhas que não são compra.
_CABECALHO = ("CARTÃO PRINCIPAL", "VENCIMENTO", "TOTAL", "DESCRICAO")

# O pagamento da fatura anterior aparece como lançamento positivo.
_PAGAMENTO = ("PAGTO DEBITO AUTOMATICO", "PAGAMENTO DE FATURA", "PAGTO FATURA")


def _num(v):
    """'-R$ 6,95' -> -6.95. None quando não dá para ler."""
    t = str(v or "").replace("R$", "").replace("\xa0", " ").strip()
    if not t:
        return None
    neg = t.startswith("-")
    t = t.lstrip("-+").replace(".", "").replace(",", ".").strip()
    try:
        n = float(t)
    except ValueError:
        return None
    return -n if neg else n


def _data(v):
    from datetime import datetime
    t = str(v or "").strip()[:10]
    for f in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(t, f).date()
        except ValueError:
            continue
    return None


def parcela(texto):
    """'Parcela 7/10' -> (7, 10). (0, 0) para compra à vista."""
    m = re.search(r"(\d+)\s*/\s*(\d+)", str(texto or ""))
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2)))


def final_cartao(texto):
    """Os últimos 4 dígitos do cartão, que é como o dono o reconhece."""
    numeros = re.findall(r"\d{4,}", str(texto or ""))
    return numeros[-1][-4:] if numeros else ""


def ler(dados):
    """(lançamentos, cabeçalho, erro).

    Cada lançamento: {"data", "descricao", "cartao", "categoria",
    "parcela_n", "parcela_de", "valor", "finalidade", "pagamento"}.
    `finalidade` só vem preenchida quando o arquivo traz anotação depois do
    `;` — é o dono classificando à mão, e ela manda.
    """
    if isinstance(dados, bytes):
        for cod in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                texto = dados.decode(cod)
                break
            except UnicodeDecodeError:
                continue
        else:
            return [], {}, "Não consegui ler o arquivo em nenhuma codificação."
    else:
        texto = str(dados)

    cabecalho, fora = {}, []
    for linha in texto.splitlines():
        if not linha.strip():
            continue
        crua, _, anotacao = linha.partition('";')
        campos = _CAMPO.findall(crua)
        if not campos:
            continue
        primeiro = campos[0].strip().upper()
        # Cabeçalho: "Cartão Principal", "Vencimento", "Total".
        rotulo = crua.split(",", 1)[0].strip().strip('"').upper()
        if rotulo in _CABECALHO or primeiro in _CABECALHO:
            if rotulo and campos[0].strip():
                cabecalho[rotulo.lower()] = campos[0].strip()
            continue

        data = _data(campos[0]) if campos else None
        if data is None or len(campos) < 6:
            continue
        valor = _num(campos[-1])
        if valor is None:
            continue
        desc = campos[2].strip()
        n, de = parcela(campos[4] if len(campos) > 4 else "")
        eh_pgto = any(p in desc.upper() for p in _PAGAMENTO)
        fora.append({
            "data": data,
            "descricao": " ".join(desc.split()),
            "cartao": final_cartao(campos[1]),
            "categoria": campos[3].strip(),
            "parcela_n": n,
            "parcela_de": de,
            "valor": valor,
            "finalidade": anotacao.strip().upper(),
            "pagamento": eh_pgto,
        })
    return fora, cabecalho, ""


def compras(lancamentos):
    """Só as compras: fora o pagamento da fatura anterior."""
    return [l for l in (lancamentos or []) if not l["pagamento"]]


def por_estabelecimento(lancamentos):
    """{estabelecimento: {"n","total"}} — a lista que o dono classifica.

    O nome vem cheio de lixo de maquininha: "ZUL 1 cartao 2DKM8I", "ZUL 1
    cartao 2DH0BI    SAO PAULO     BRA". São o MESMO estabelecimento, e sem
    agrupar o dono classificaria doze vezes o mesmo estacionamento.
    """
    fora = {}
    for l in compras(lancamentos):
        nome = estabelecimento(l["descricao"])
        d = fora.setdefault(nome, {"n": 0, "total": 0.0})
        d["n"] += 1
        d["total"] += abs(l["valor"])
    return dict(sorted(fora.items(), key=lambda x: -x[1]["total"]))


# Palavras que não identificam a loja: cidade, país e sobra de maquininha.
_LIXO = {"SAO", "PAULO", "BRA", "SC", "RIO", "DE", "JANEI", "CURITIBA",
         "CAJAMAR", "BLUMENAU", "OSASCO", "MARILIA", "BERNARD", "SO",
         "CARTAO", "1"}


def estabelecimento(descricao):
    """O nome da loja, sem cidade nem código da transação.

    "ZUL 1 cartao 2DKM8I" e "ZUL 1 cartao 2DH0BI SAO PAULO BRA" viram ZUL.
    Duas palavras bastam: com uma, "MERCADO RASTREAMENTO" e "MERCADO
    FENIXOFFICE" virariam a mesma coisa.
    """
    palavras = []
    for p in str(descricao or "").upper().split():
        p = re.sub(r"[^A-Z0-9]", "", p)
        if not p or p in _LIXO:
            continue
        # Código de transação: mistura letra e número, ou é número puro.
        if re.search(r"\d", p) and re.search(r"[A-Z]", p):
            continue
        if p.isdigit():
            continue
        palavras.append(p)
        if len(palavras) == 2:
            break
    return " ".join(palavras) or str(descricao or "").strip()[:24]


# ── Conferência ──────────────────────────────────────────────────────────────
# Forma real do arquivo de outubro/2026, com valores mantidos porque é deles
# que sai a conta do teste.
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    ok("valor negativo com R$ e virgula", _num("-R$ 6,95") == -6.95)
    ok("valor positivo", _num("R$ 1.503,80") == 1503.80)
    ok("milhar e virgula juntos", _num("-R$ 1.234,56") == -1234.56)
    ok("campo vazio nao vira zero", _num("") is None and _num(None) is None)

    ok("parcela e lida", parcela("Parcela 7/10") == (7, 10))
    ok("compra a vista nao tem parcela",
       parcela("Compra à vista") == (0, 0) and parcela("") == (0, 0))
    ok("o final do cartao sai do numero mascarado",
       final_cartao("•••• •••• •••• 0005497380087931924") == "1924")

    # O agrupamento e o que economiza o trabalho do dono: doze ZUL, uma
    # classificacao.
    ok("o codigo da maquininha sai do nome",
       estabelecimento("ZUL 1 cartao 2DKM8I") == "ZUL")
    ok("cidade e pais saem do nome",
       estabelecimento("ZUL 1 cartao 2DH0BI    SAO PAULO     BRA") == "ZUL")
    ok("duas lojas que comecam igual continuam separadas",
       estabelecimento("MERCADO RASTREAMENTOA  SO BERNARD    BRA")
       != estabelecimento("MERCADO FENIXOFFICE    OSASCO        BRA"))
    ok("numero colado na palavra e sobra de maquininha, e sai",
       estabelecimento("MERCADOLIVRE 4PRODUTOS CAJAMAR BRA") == "MERCADOLIVRE")
    ok("nome com duas palavras uteis fica com as duas",
       estabelecimento("Vindi   TrayEcommerce  Marilia       BRA")
       == "VINDI TRAYECOMMERCE")

    LINHAS = (
        '"Descricao,""Data"",""Cartao"",""Lançamento"",""Categoria"",""Tipo"",""Valor""";\n'
        '"Cartão Principal,""•••• •••• •••• 2645"","""","""","""","""",""""";\n'
        '"Vencimento,""01/10"","""","""","""","""",""""";\n'
        '",""16/09/2026"",""•••• 1924"",""ZUL 1 cartao 2DKM8I"",""TRANSPORTE"",""Compra à vista"",""-R$ 6,95""";Estacionamento\n'
        '",""13/09/2026"",""•••• 1924"",""Vindi   TrayEcommerce  Marilia BRA"",""SERVICOS"",""Compra à vista"",""-R$ 8,52""";Serviço\n'
        '",""01/09/2026"",""•••• 8095"",""PAGTO DEBITO AUTOMATICO"",""OUTROS"",""Compra à vista"",""R$ 1.503,80""";\n'
        '",""17/03/2026"",""•••• 1924"",""MERCADOLIVRE 4PRODUTOS CAJAMAR BRA"",""OUTROS"",""Parcela 7/10"",""-R$ 73,99""";Outros\n'
        '"Total,"""","""","""","""","""",""R$ 324,66""";\n'
    )
    _l, _cab, _e = ler(LINHAS.encode("utf-8"))
    ok("le os quatro lancamentos, e nao o cabecalho", len(_l) == 4)
    ok("o vencimento e lido", _cab.get("vencimento") == "01/10")
    ok("a anotacao do dono vira finalidade",
       _l[0]["finalidade"] == "ESTACIONAMENTO" and _l[1]["finalidade"] == "SERVIÇO")
    ok("linha sem anotacao fica sem finalidade", _l[2]["finalidade"] == "")
    ok("a parcela viaja junto",
       (_l[3]["parcela_n"], _l[3]["parcela_de"]) == (7, 10))
    ok("a vista tem parcela zero", _l[0]["parcela_n"] == 0)

    # O pagamento da fatura anterior nao e compra: contado como gasto, ele
    # somaria de novo a fatura que ja saiu da conta corrente.
    ok("o pagamento da fatura e marcado", _l[2]["pagamento"] is True)
    ok("e fica fora das compras", len(compras(_l)) == 3)

    _est = por_estabelecimento(_l)
    ok("o agrupamento por estabelecimento soma certo",
       abs(_est["MERCADOLIVRE"]["total"] - 73.99) < 0.01)
    ok("o pagamento nao entra no agrupamento",
       not any("PAGTO" in k for k in _est))

    print("\nfalhas:", falhas)
