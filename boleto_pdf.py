"""boleto_pdf.py — o boleto em PDF virando valor, vencimento e beneficiário.

Dono, 13/10: uma aba "Boletos" para anexar os boletos de cobrança — "são de
compras de mercadoria, geralmente" — e o sistema computar nos gastos
provisionados.

VALOR E VENCIMENTO SAEM DA LINHA DIGITÁVEL, NÃO DO TEXTO
--------------------------------------------------------
O texto de um boleto muda de banco para banco; a linha digitável não. No
boleto bancário (47 dígitos, padrão Febraban) o último campo é o FATOR DE
VENCIMENTO (4 dígitos) e o VALOR em centavos (10 dígitos). Ler dali é exato —
o mesmo número que o banco usa para cobrar.

  fator de vencimento  dias desde a data-base. A contagem chegou a 9999 em
                       21/02/2025 e recomeçou em 1000 no dia 22/02/2025 (regra
                       Febraban). O mesmo fator vale nas duas voltas: fica a
                       data mais próxima de hoje.
  fator 0000           boleto sem vencimento; o texto é procurado.

O boleto de concessionária (água, luz, imposto: 48 dígitos, começa com 8) não
traz vencimento no código: o valor sai do código e o vencimento, do texto.

O BENEFICIÁRIO É O ÚNICO PALPITE. Ele sai do texto, perto da palavra
"Beneficiário", e a tela deixa corrigir antes de gravar.

DÍGITO QUE NÃO CONFERE AVISA, NÃO RECUSA. Os dígitos verificadores dos três
primeiros campos são conferidos (módulo 10). Se não batem, a linha foi lida
torta do PDF: a tela avisa para conferir, e o dono decide.
"""
import re
from datetime import date, timedelta

BASE_ANTIGA = date(1997, 10, 7)
BASE_NOVA = date(2025, 2, 22)        # fator 1000 da segunda volta

_LINHA_FORMATADA = re.compile(
    r"(\d{5})[.\s]?(\d{5})\s+(\d{5})[.\s]?(\d{6})\s+(\d{5})[.\s]?(\d{6})"
    r"\s+(\d)\s+(\d{14})")
_CONCESSIONARIA = re.compile(
    r"(8\d{10})[\s-]?(\d)\s+(\d{11})[\s-]?(\d)\s+(\d{11})[\s-]?(\d)"
    r"\s+(\d{11})[\s-]?(\d)")
_DATA = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def _mod10(numero):
    """Dígito verificador módulo 10 (pesos 2,1,2,1… da direita)."""
    soma, peso = 0, 2
    for d in reversed(numero):
        p = int(d) * peso
        soma += p // 10 + p % 10
        peso = 1 if peso == 2 else 2
    resto = soma % 10
    return 0 if resto == 0 else 10 - resto


def linha_do_texto(texto):
    """(linha digitável só com dígitos, tipo) ou ("", ""). Tipo "bancario"
    (47 dígitos) ou "concessionaria" (48)."""
    t = str(texto or "")
    m = _LINHA_FORMATADA.search(t)
    if m:
        return "".join(m.groups()), "bancario"
    m = _CONCESSIONARIA.search(t)
    if m:
        return "".join(m.groups()), "concessionaria"
    for corrido in re.findall(r"\d{47,48}", re.sub(r"[.\s-]", "", t)):
        if len(corrido) == 48 and corrido.startswith("8"):
            return corrido, "concessionaria"
        if len(corrido) >= 47:
            return corrido[:47], "bancario"
    return "", ""


def vencimento_do_fator(fator, hoje=None):
    """A data do fator de vencimento. None no fator 0000."""
    f = int(fator)
    if f == 0:
        return None
    hoje = hoje or date.today()
    candidatas = [BASE_ANTIGA + timedelta(days=f)]
    if f >= 1000:
        candidatas.append(BASE_NOVA + timedelta(days=f - 1000))
    return min(candidatas, key=lambda d: abs((d - hoje).days))


def decodificar(linha, tipo, hoje=None):
    """{"valor", "vencimento", "banco", "confere"}. Pura."""
    if tipo == "bancario" and len(linha) == 47:
        campos = (linha[0:9], linha[9], linha[10:20], linha[20],
                  linha[21:31], linha[31])
        confere = all(_mod10(campos[i]) == int(campos[i + 1])
                      for i in (0, 2, 4))
        return {"valor": int(linha[37:47]) / 100.0,
                "vencimento": vencimento_do_fator(linha[33:37], hoje),
                "banco": linha[0:3], "confere": confere}
    if tipo == "concessionaria" and len(linha) == 48:
        blocos = [linha[i * 12:i * 12 + 11] for i in range(4)]
        codigo = "".join(blocos)
        # O 3º dígito diz se o código traz o valor real (6 ou 7) ou outra
        # referência (8 ou 9) — sem valor real, não se inventa.
        valor = int(codigo[4:15]) / 100.0 if codigo[2] in "67" else None
        confere = all(_mod10(blocos[i]) == int(linha[i * 12 + 11])
                      for i in range(4)) if codigo[2] in "68" else True
        return {"valor": valor, "vencimento": None, "banco": "",
                "confere": confere}
    return {"valor": None, "vencimento": None, "banco": "", "confere": False}


def vencimento_do_texto(texto):
    """A data escrita ao lado de "Vencimento", ou None."""
    t = str(texto or "")
    i = t.lower().find("vencimento")
    if i < 0:
        return None
    m = _DATA.search(t[i:i + 120])
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def beneficiario_do_texto(texto):
    """O nome perto de "Beneficiário" (ou "Cedente"). "" se não achar."""
    linhas = [l.strip() for l in str(texto or "").splitlines()]
    for i, l in enumerate(linhas):
        baixa = l.lower()
        if not (baixa.startswith("benefici") or baixa.startswith("cedente")):
            continue
        resto = re.sub(r"^(benefici[aá]rio|cedente)\s*(final)?\s*[:\-]?\s*",
                       "", l, flags=re.I)
        candidatos = ([resto] if resto else []) + linhas[i + 1:i + 3]
        for c in candidatos:
            c = re.sub(r"(CNPJ|CPF)[^A-Za-z]*[\d./-]+", "", c, flags=re.I)
            c = re.sub(r"\b\d[\d./-]{9,}\b", "", c).strip(" -:,")
            if len(re.sub(r"[^A-Za-zÀ-ú]", "", c)) >= 3:
                return c[:80]
    return ""


def ler_texto(texto, hoje=None):
    """Tudo o que se lê de um boleto, a partir do texto. Pura.

    {"linha", "tipo", "valor", "vencimento", "beneficiario", "aviso"} — com
    "aviso" dizendo o que falta conferir, ou "" quando leu tudo.
    """
    linha, tipo = linha_do_texto(texto)
    if not linha:
        return {"linha": "", "tipo": "", "valor": None, "vencimento": None,
                "beneficiario": beneficiario_do_texto(texto),
                "aviso": "não achei a linha digitável — cole-a à mão"}
    d = decodificar(linha, tipo, hoje)
    venc = d["vencimento"] or vencimento_do_texto(texto)
    avisos = []
    if not d["confere"]:
        avisos.append("a linha digitável não confere — confira o valor e o "
                      "vencimento")
    if d["valor"] is None:
        avisos.append("o código não traz o valor — digite")
    if venc is None:
        avisos.append("sem vencimento — digite")
    return {"linha": linha, "tipo": tipo, "valor": d["valor"],
            "vencimento": venc, "beneficiario": beneficiario_do_texto(texto),
            "aviso": "; ".join(avisos)}


def ler_pdf(dados, hoje=None):
    """(leitura, erro) de um PDF de boleto. O texto sai de `fatura_pdf`."""
    import fatura_pdf as _fp
    texto, erro = _fp.texto_do_pdf(dados)
    if erro:
        return None, erro
    return ler_texto(texto, hoje), ""


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # O DÍGITO MÓDULO 10 conferido à mão contra o exemplo clássico da
    # Febraban: o campo "001900000" tem DV 9 ("00190.00009").
    ok("o módulo 10 dá os dígitos do exemplo da Febraban (campos 1 e 2)",
       _mod10("001900000") == 9 and _mod10("0123456700") == 4)

    # Uma linha digitável montada campo a campo: banco 341, moeda 9, e o
    # último campo com fator 1019 (22/02/2025 + 19 dias = 13/03/2025) e
    # valor 0000150000 (R$ 1.500,00).
    def _campo(n):
        return n + str(_mod10(n))
    _c1 = _campo("341911234")
    _c2 = _campo("5678901234")
    _c3 = _campo("5678901234")
    _linha = _c1 + _c2 + _c3 + "7" + "1019" + "0000150000"
    _fmt = (f"{_linha[0:5]}.{_linha[5:10]} {_linha[10:15]}.{_linha[15:21]} "
            f"{_linha[21:26]}.{_linha[26:32]} {_linha[32]} {_linha[33:47]}")
    _txt = ("Banco Itaú\nBeneficiário\nFORNECEDOR DE VIDROS LTDA "
            "CNPJ 12.345.678/0001-90\nVencimento 13/03/2025\n" + _fmt)
    _l = ler_texto(_txt, hoje=date(2025, 3, 1))
    ok("acha a linha digitável no texto do PDF", _l["linha"] == _linha
       and _l["tipo"] == "bancario")
    ok("valor e vencimento saem da linha, exatos",
       _l["valor"] == 1500.0 and _l["vencimento"] == date(2025, 3, 13)
       and _l["aviso"] == "")
    ok("o beneficiário sai sem o CNPJ",
       _l["beneficiario"] == "FORNECEDOR DE VIDROS LTDA")
    ok("o fator conta da data-base nova (22/02/2025 = 1000)",
       vencimento_do_fator("1000", date(2025, 3, 1)) == date(2025, 2, 22))
    ok("o mesmo fator na volta antiga, quando a data é a antiga",
       vencimento_do_fator("1000", date(2000, 7, 1)) == date(2000, 7, 3))
    ok("fator 0000 é boleto sem vencimento", vencimento_do_fator("0000") is None)
    _torta = _linha[:2] + str((int(_linha[2]) + 1) % 10) + _linha[3:]
    _lt = ler_texto(_torta, hoje=date(2025, 3, 1))
    ok("linha lida torta avisa para conferir, sem recusar",
       _lt["valor"] == 1500.0 and "não confere" in _lt["aviso"])
    _sem = ler_texto("Beneficiário: LOJA X\nsem código", hoje=date(2025, 3, 1))
    ok("sem linha digitável, pede para colar", _sem["linha"] == ""
       and "cole" in _sem["aviso"] and _sem["beneficiario"] == "LOJA X")
    # Concessionária: 4 blocos de 11 + DV; 3º dígito 6 = valor real.
    _b = ["8261000000", "0", "0", "0"]
    _cod = "826" + "1" + "00000012345" + "0" * 29
    _blocos = [_cod[i * 11:(i + 1) * 11] for i in range(4)]
    _conc = "".join(b + str(_mod10(b)) for b in _blocos)
    _lc = ler_texto(_conc + "\nVencimento: 20/10/2026", hoje=date(2026, 10, 13))
    ok("boleto de concessionária: valor do código, vencimento do texto",
       _lc["tipo"] == "concessionaria" and _lc["valor"] == 123.45
       and _lc["vencimento"] == date(2026, 10, 20) and _lc["aviso"] == "")
    # O PDF DE VERDADE: um PDF mínimo com o texto do boleto, aberto pelo
    # `pypdf` em `fatura_pdf.texto_do_pdf` — o mesmo caminho do arquivo
    # anexado na tela. Montado à mão para não depender de gerador de PDF.
    def _pdf(linhas_txt):
        conteudo = "BT /F1 10 Tf 40 800 Td 14 TL " + " ".join(
            "(" + t.replace("\\", "").replace("(", "").replace(")", "")
            + ") ' " for t in linhas_txt) + "ET"
        objs = ["<< /Type /Catalog /Pages 2 0 R >>",
                "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
                f"<< /Length {len(conteudo)} >>\nstream\n{conteudo}\nendstream",
                "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
        saida, pos = "%PDF-1.4\n", []
        for i, o in enumerate(objs, 1):
            pos.append(len(saida))
            saida += f"{i} 0 obj\n{o}\nendobj\n"
        xref = len(saida)
        saida += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(
            f"{p:010d} 00000 n \n" for p in pos)
        saida += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
                  f"startxref\n{xref}\n%%EOF")
        return saida.encode("latin-1")
    _lp, _ep = ler_pdf(_pdf(["Beneficiario", "FORNECEDOR DE VIDROS LTDA",
                             "Vencimento 13/03/2025", _fmt]),
                       hoje=date(2025, 3, 1))
    ok("o PDF anexado é lido de ponta a ponta",
       _ep == "" and _lp and _lp["valor"] == 1500.0
       and _lp["vencimento"] == date(2025, 3, 13)
       and _lp["beneficiario"] == "FORNECEDOR DE VIDROS LTDA")
    _ls, _es = ler_pdf(b"isto nao e um pdf", hoje=date(2025, 3, 1))
    ok("arquivo que não é PDF devolve o motivo, sem quebrar",
       _ls is None and _es)

    print(f"\nfalhas: {falhas}")
    sys.exit(1 if falhas else 0)
