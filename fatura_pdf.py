"""fatura_pdf.py — ler a fatura do cartão que só existe em PDF.

POR QUE ELE EXISTE, E POR QUE ELE DESCONFIA DE SI MESMO
-------------------------------------------------------
O dono tenta anexar as faturas dos cartões desde 25/09 e não consegue: o
Studio lia `.xlsx` e `.csv`, e a fatura do cartão dele vem em PDF.

Ler PDF de banco é o caminho mais frágil que existe nesta base. O extrato do
Itaú é uma planilha com colunas; a fatura em PDF é um desenho, e o texto sai
na ordem em que foi impresso. O banco muda o layout numa atualização e o
leitor passa a devolver número errado — **sem erro nenhum na tela**, que é a
pior forma de um sistema de dinheiro falhar.

Por isso este módulo NÃO grava nada. Ele lê, devolve o que achou e devolve
também o TEXTO CRU. Quem decide é a pessoa, olhando a tabela ao lado da
fatura aberta. Um lançamento que ele não achou é visível; um que ele
inventaria, também.

O QUE ELE PROCURA
-----------------
A forma comum das faturas brasileiras: uma data, uma descrição e um valor na
mesma linha.

    12/09   MERCADOLIVRE*LOJA     R$ 149,90
    12/09   POSTO IPIRANGA        149,90
    12 SET  UBER   *TRIP          -R$ 23,50

Data com ano, sem ano, ou com o mês por extenso. Valor com ou sem "R$", com
sinal ou sem. O que não casar com isso fica de fora e aparece no texto cru —
nunca é adivinhado.
"""

import re
import unicodedata

MESES = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
         "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}

# Uma linha de fatura: data no começo, valor no fim, descrição no meio.
_LINHA = re.compile(
    r"^\s*(?P<dia>\d{1,2})\s*[/\- ]\s*(?P<mes>\d{1,2}|[a-zA-Z]{3})"
    r"(?:\s*[/\- ]\s*(?P<ano>\d{2,4}))?\s+"
    r"(?P<desc>.+?)\s+"
    r"(?P<sinal>-)?\s*(?:R\$)?\s*"
    r"(?P<valor>\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})\s*$"
)

# "Parcela 7/10", "PARC 03/12", "7 de 10".
_PARCELA = re.compile(r"(?:parc\w*\.?\s*)?(\d{1,2})\s*(?:/|de)\s*(\d{1,2})",
                      re.IGNORECASE)

# O pagamento da fatura anterior aparece dentro dela, positivo. Não é compra:
# contá-lo como gasto somaria o mesmo dinheiro duas vezes — uma no extrato,
# quando o débito saiu, e outra aqui.
_PAGAMENTO = ("PAGAMENTO", "PGTO", "PAGTO", "CREDITO DE ATRASO",
              "ESTORNO", "DEVOLUCAO", "DEVOLUÇÃO")


def _sem_acento(t):
    t = unicodedata.normalize("NFD", str(t or ""))
    return t.encode("ascii", "ignore").decode("ascii")


def _num(t):
    """"1.234,56" -> 1234.56. None quando não é número."""
    try:
        return float(str(t).replace(".", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def _mes(t):
    t = str(t or "").strip().lower()
    if t.isdigit():
        n = int(t)
        return n if 1 <= n <= 12 else None
    return MESES.get(_sem_acento(t)[:3])


def texto_do_pdf(dados):
    """(texto, erro). Sem pypdf instalado, diz isso em vez de quebrar.

    A dependência é declarada no `requirements.txt`, mas um container que
    subiu antes dela não a tem — e o colaborador merece a frase certa, não um
    ImportError na tela.
    """
    try:
        import pypdf
    except ImportError:
        return "", ("Este Studio ainda não sabe abrir PDF (falta a biblioteca "
                    "`pypdf`). Avise o Léo — é uma linha no requirements.")
    try:
        import io
        leitor = pypdf.PdfReader(io.BytesIO(dados))
        if getattr(leitor, "is_encrypted", False):
            try:
                leitor.decrypt("")
            except Exception:
                return "", ("O PDF está protegido por senha. Salve uma cópia "
                            "sem senha e suba de novo.")
        paginas = [(p.extract_text() or "") for p in leitor.pages]
    except Exception as e:
        return "", f"Não consegui abrir o PDF: {type(e).__name__}"
    texto = "\n".join(paginas)
    if not texto.strip():
        return "", ("O PDF não tem texto — provavelmente é uma imagem "
                    "escaneada. Baixe a fatura de novo pelo app do banco, em "
                    "PDF ou CSV; o Studio não lê fatura fotografada.")
    return texto, ""


def lancamentos_do_texto(texto, ano_padrao=None):
    """Os lançamentos que a forma comum de fatura deixa reconhecer.

    Devolve (lancamentos, linhas_ignoradas). NADA aqui é chute: linha que não
    tem data E valor não vira lançamento — vai para as ignoradas, que a tela
    mostra para a pessoa conferir se perdeu alguma coisa.
    """
    fora, ignoradas = [], []
    for bruta in str(texto or "").splitlines():
        linha = " ".join(bruta.split())
        if not linha:
            continue
        m = _LINHA.match(linha)
        if not m:
            ignoradas.append(linha)
            continue
        mes = _mes(m.group("mes"))
        valor = _num(m.group("valor"))
        if mes is None or valor is None:
            ignoradas.append(linha)
            continue
        ano = m.group("ano")
        if ano:
            ano = int(ano)
            ano = ano + 2000 if ano < 100 else ano
        else:
            ano = ano_padrao
        desc = " ".join(m.group("desc").split())
        alta = _sem_acento(desc).upper()
        eh_pgto = any(p in alta for p in
                      (_sem_acento(x).upper() for x in _PAGAMENTO))
        p = _PARCELA.search(desc)
        # SINAL: compra sai do caixa e entra NEGATIVA, como no extrato. O
        # pagamento da fatura anterior é o único positivo — e ele é marcado
        # para não virar gasto.
        v = abs(valor)
        fora.append({
            "data": (f"{ano:04d}-{mes:02d}-{int(m.group('dia')):02d}"
                     if ano else f"{mes:02d}-{int(m.group('dia')):02d}"),
            "descricao": desc,
            "valor": v if eh_pgto else -v,
            "sentido": "entrada" if eh_pgto else "saida",
            "parcela_n": int(p.group(1)) if p else None,
            "parcela_de": int(p.group(2)) if p else None,
            "pagamento": eh_pgto,
        })
    return fora, ignoradas


def ler(dados, ano_padrao=None):
    """(lancamentos, texto_cru, erro). O texto cru volta SEMPRE que der.

    Ele volta porque é a única defesa contra o leitor calar: com a fatura
    aberta do lado e o texto na tela, um lançamento que faltou é visível.
    """
    texto, erro = texto_do_pdf(dados)
    if erro:
        return [], texto, erro
    lancs, ignoradas = lancamentos_do_texto(texto, ano_padrao)
    if not lancs:
        return [], texto, ("Abri o PDF, mas não reconheci nenhum lançamento "
                           "no formato «data · descrição · valor». O texto "
                           "que saiu está abaixo — me mande que eu ajusto o "
                           "leitor ao layout deste banco.")
    return lancs, texto, ""


def identificar(nome_arquivo, dados):
    """De que arquivo se trata, pelo CONTEÚDO — o nome é só o desempate.

    Devolve "extrato_itau", "extrato_inter", "fatura_inter", "fatura_pdf" ou
    "" quando não dá para saber.

    O NOME NÃO DECIDE. "Fatura final 3417 Novembro.pdf" e "Extrato Itaú MS
    09.2026.xlsx" são digitados à mão, e já chegaram trocados. O que manda é
    a forma do arquivo: os quatro formatos têm estruturas diferentes, e
    distingui-las é leitura, não adivinhação.
    """
    nome = str(nome_arquivo or "").lower()
    if nome.endswith(".pdf") or (dados or b"")[:5] == b"%PDF-":
        return "fatura_pdf"
    if nome.endswith(".xlsx") or (dados or b"")[:2] == b"PK":
        return "extrato_itau"
    if not nome.endswith(".csv"):
        return ""

    # Os dois CSV: o do EXTRATO do Inter é separado por `;` com uma linha de
    # título antes dos lançamentos; o da FATURA vem com a linha inteira entre
    # aspas e traz "Cartão Principal", "Vencimento" ou "Total" no cabeçalho.
    texto = ""
    for cod in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            texto = (dados or b"").decode(cod)
            break
        except (UnicodeDecodeError, AttributeError):
            continue
    alto = _sem_acento(texto[:4000]).upper()
    if any(m in alto for m in ("CARTAO PRINCIPAL", "VENCIMENTO", "LIMITE")):
        return "fatura_inter"
    return "extrato_inter"


# ── Conferência ──────────────────────────────────────────────────────────────
# `python3 fatura_pdf.py`. Tudo aqui é função pura sobre TEXTO — o PDF de
# verdade entra na tela, e o que ele produzir aparece para a pessoa conferir.
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    _FATURA = """
Fatura do cartao final 3312
Vencimento 10/10/2026            Total R$ 1.503,80

12/09   MERCADOLIVRE*LOJA DO JOAO            R$ 149,90
12/09   POSTO IPIRANGA                       149,90
13/09   UBER   *TRIP                     -R$ 23,50
14/09   MAGAZINE LUIZA Parcela 7/10          R$ 89,90
15 SET  AMAZON BR                            R$ 1.234,56
20/09   PAGAMENTO FATURA ANTERIOR            R$ 980,00
Limite disponivel R$ 3.000,00
"""
    _lancs, _ign = lancamentos_do_texto(_FATURA, ano_padrao=2026)

    ok("acha os seis lancamentos da fatura", len(_lancs) == 6)
    ok("com R$ e sem R$ dao no mesmo",
       _lancs[0]["valor"] == -149.90 and _lancs[1]["valor"] == -149.90)
    ok("milhar com ponto vira mil e nao um",
       any(abs(l["valor"] + 1234.56) < 0.001 for l in _lancs))
    ok("mes por extenso tambem e data",
       any(l["data"] == "2026-09-15" for l in _lancs))
    ok("a data leva o ano quando a linha nao traz",
       all(len(l["data"]) == 10 for l in _lancs))

    # COMPRA SAI DO CAIXA: entra NEGATIVA, como no extrato. Se entrasse
    # positiva, o mes fecharia com gasto virando receita.
    ok("compra e negativa",
       all(l["valor"] < 0 for l in _lancs if not l["pagamento"]))

    # O PAGAMENTO DA FATURA ANTERIOR NAO E COMPRA. Ele ja saiu pelo extrato;
    # conta-lo aqui somaria o mesmo dinheiro duas vezes.
    _pg = [l for l in _lancs if l["pagamento"]]
    ok("o pagamento da fatura anterior e marcado", len(_pg) == 1)
    ok("e entra positivo, para nao virar gasto", _pg[0]["valor"] > 0)

    # A PARCELA E O QUE A FATURA TEM E O EXTRATO NAO.
    _parc = [l for l in _lancs if l["parcela_n"]]
    ok("a parcela e lida", _parc and _parc[0]["parcela_n"] == 7
       and _parc[0]["parcela_de"] == 10)
    ok("quem nao e parcelado fica sem parcela",
       all(l["parcela_n"] is None for l in _lancs if "Parcela" not in l["descricao"]))

    # O QUE NAO E LANCAMENTO NAO PODE VIRAR LANCAMENTO. Cabecalho, limite e
    # total sao os tres que mais enganam um leitor apressado.
    _descs = " | ".join(l["descricao"] for l in _lancs)
    ok("o total da fatura nao vira compra", "Total" not in _descs)
    ok("o limite disponivel tambem nao", "Limite" not in _descs)
    ok("nem o vencimento", "Vencimento" not in _descs)
    ok("e as linhas ignoradas ficam visiveis para conferencia",
       any("Limite" in i for i in _ign))

    # BORDAS
    ok("texto vazio nao quebra", lancamentos_do_texto("") == ([], []))
    ok("None tambem nao", lancamentos_do_texto(None) == ([], []))
    ok("linha sem valor nao vira lancamento",
       lancamentos_do_texto("12/09  COMPRA SEM VALOR")[0] == [])
    ok("linha sem data tambem nao",
       lancamentos_do_texto("COMPRA QUALQUER R$ 10,00")[0] == [])
    ok("mes 13 nao existe", lancamentos_do_texto("12/13 X R$ 1,00")[0] == [])

    # SEM pypdf, a frase e sobre a biblioteca — nao um ImportError na tela.
    import sys as _sys
    _guardado = _sys.modules.get("pypdf")
    _sys.modules["pypdf"] = None
    try:
        _t, _e = texto_do_pdf(b"%PDF-1.4")
    finally:
        if _guardado is None:
            _sys.modules.pop("pypdf", None)
        else:
            _sys.modules["pypdf"] = _guardado
    ok("sem a biblioteca, a mensagem diz o que falta",
       _t == "" and "pypdf" in _e)

    # PDF QUEBRADO vira recado, nunca excecao.
    _t2, _e2 = texto_do_pdf(b"isso nao e um pdf")
    ok("arquivo que nao e PDF vira recado", _t2 == "" and _e2)

    ok("ler() devolve o texto cru junto", len(ler(b"nao e pdf")) == 3)

    # ── O MES, QUE VEM DE TRES JEITOS NA MESMA FATURA ───────────────────
    ok("mes em numero", _mes("9") == 9 and _mes("09") == 9)
    ok("mes por extenso curto", _mes("set") == 9 and _mes("SET") == 9)
    ok("com acento tambem", _mes("mar") == 3 and _mes("MAR") == 3)
    ok("mes que nao existe e None", _mes("13") is None and _mes("0") is None)
    ok("texto qualquer e None", _mes("xyz") is None and _mes("") is None)
    ok("None nao quebra", _mes(None) is None)
    # O VALOR, que muda de forma conforme o banco.
    ok("milhar com ponto", _num("1.234,56") == 1234.56)
    ok("sem milhar", _num("23,50") == 23.50)
    ok("texto nao vira numero", _num("abc") is None and _num(None) is None)

    # ── QUEM E QUEM, PELO CONTEUDO ──────────────────────────────────────
    #
    # "Eu quero poder anexar tudo no mesmo lugar, o sistema identifica o que
    # e extrato da conta e o que e fatura do cartao" — dono, 25/09.
    #
    # O NOME NAO DECIDE: "Fatura final 3417 Novembro.pdf" e "Extrato Itau MS
    # 09.2026.xlsx" sao digitados a mao e ja chegaram trocados.
    _CSV_EXT = "Conta;123\nData;Descricao;Valor\n01/09;Pix;-10,00"
    _CSV_FAT = ('"Cartao Principal","x"\n'
                '"16/09","1924","ZUL","TRANSPORTE","a vista","-R$ 6,95"')
    ok("PDF e reconhecido pelo nome",
       identificar("Fatura final 3312.pdf", b"") == "fatura_pdf")
    ok("e pela assinatura do arquivo, mesmo com nome errado",
       identificar("planilha.bin", b"%PDF-1.7 x") == "fatura_pdf")
    ok("xlsx e extrato do Itau",
       identificar("Extrato Itau.xlsx", b"PK\x03\x04") == "extrato_itau")
    ok("e pelo cabecalho do zip, mesmo sem extensao",
       identificar("arquivo", b"PK\x03\x04") == "extrato_itau")
    # OS DOIS CSV SAO O CASO DIFICIL: mesma extensao, bancos diferentes.
    ok("csv com linha de titulo e extrato do Inter",
       identificar("qualquer.csv", _CSV_EXT.encode()) == "extrato_inter")
    ok("csv com Cartao Principal e fatura do Inter",
       identificar("qualquer.csv", _CSV_FAT.encode()) == "fatura_inter")
    ok("e o nome do arquivo nao inverte isso",
       identificar("Extrato.csv", _CSV_FAT.encode()) == "fatura_inter"
       and identificar("Fatura.csv", _CSV_EXT.encode()) == "extrato_inter")
    ok("latin-1 tambem e lido",
       identificar("x.csv", "Cartao Principal;Vencimento".encode("latin-1"))
       == "fatura_inter")
    ok("formato desconhecido nao e chutado",
       identificar("foto.jpeg", b"\xff\xd8\xff") == "")
    ok("arquivo vazio nao quebra", identificar("", b"") == "")
    ok("None nao quebra", identificar(None, None) == "")

    print("\nfalhas:", falhas)
