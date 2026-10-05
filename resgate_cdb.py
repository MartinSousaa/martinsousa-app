"""resgate_cdb.py — o comprovante de resgate do CDB atualiza a Reserva sozinho.

O QUE ELE RESOLVE
-----------------
O dono resgata parte do CDB todo mês para pagar a folha do Headcount, e a tela
da Reserva só sabia da posição que alguém DIGITASSE. Com o resgate, o valor
aplicado muda — e se só o saldo fosse atualizado, a taxa implícita
(`reserva.taxa_implicita`, saldo ÷ aplicado) diria que o CDB rendeu negativo.

O COMPROVANTE DIZ EXATAMENTE QUANTO DO PRINCIPAL SAIU
-----------------------------------------------------
O IR incide só sobre o rendimento. Com o IR do comprovante e a alíquota da
faixa (`reserva.aliquota_ir`, pelos dias desde a aplicação):

    rendimento resgatado = IR ÷ alíquota
    principal resgatado  = bruto resgatado − rendimento resgatado

Conferido contra o resgate real de 02/10/2026: 13.406,09 bruto, 52,22 de IR a
22,5% → 13.174,00 de principal; 270.000,00 − 13.174,00 = 256.826,00 — e o
print do banco, três dias depois, dava 256.826,02 (IR 1.018,03 sobre 261.350,60).

O saldo bruto no dia do resgate é PROJETADO pela taxa da última posição: o
comprovante não traz o saldo que sobrou. Por isso a tela continua aceitando a
posição digitada do extrato, que corrige a projeção quando for colada.
"""

import re

import reserva as _rv


def _valor(texto, rotulo):
    """O número em "Rótulo: 1.234,56". None quando a linha não existe."""
    m = re.search(rotulo + r"\s*:\s*R?\$?\s*([\d.]+,\d{2})", texto,
                  flags=re.IGNORECASE)
    if not m:
        return None
    return float(m.group(1).replace(".", "").replace(",", "."))


def ler_texto(texto):
    """({data, bruto, ir, iof, liquido}, "") ou (None, motivo). Função pura."""
    t = str(texto or "")
    if "resgate" not in t.lower():
        return None, "o arquivo não parece um comprovante de resgate"
    m = re.search(r"Data do cr[ée]dito\s*:\s*(\d{2})/(\d{2})/(\d{4})", t,
                  flags=re.IGNORECASE)
    bruto = _valor(t, r"Valor bruto resgatado")
    ir = _valor(t, r"Valor do IR")
    if not m or bruto is None or ir is None:
        return None, ("não achei a data do crédito, o valor bruto resgatado "
                      "ou o IR no comprovante")
    return {
        "data": f"{m.group(3)}-{m.group(2)}-{m.group(1)}",
        "bruto": bruto,
        "ir": ir,
        "iof": _valor(t, r"Valor do IOF") or 0.0,
        "liquido": _valor(t, r"Valor l[íi]quido resgatado") or 0.0,
    }, ""


def ler_pdf(arquivo):
    """Lê o PDF do comprovante (o objeto do `file_uploader` ou bytes)."""
    try:
        import io
        import pypdf
        dados = arquivo if isinstance(arquivo, (bytes, bytearray)) \
            else arquivo.getvalue()
        leitor = pypdf.PdfReader(io.BytesIO(dados))
        texto = "\n".join((p.extract_text() or "") for p in leitor.pages)
    except Exception as e:
        return None, f"não consegui ler o PDF ({type(e).__name__})"
    return ler_texto(texto)


def posicao_apos(pos, resgate):
    """A posição da Reserva depois do resgate. (nova_posicao, detalhe).

    `pos` é a posição gravada (`reserva_tela.carregar`); `resgate`, o que
    `ler_texto` devolve. Devolve (None, motivo) quando a conta não fecha.
    """
    ini = _rv._data(pos.get("inicio"))
    dia = _rv._data(resgate.get("data"))
    if not ini or not dia or dia <= ini:
        return None, "a data do resgate não é posterior à aplicação"
    aplicado = float(pos.get("aplicado") or 0)
    bruto = float(pos.get("bruto") or 0)
    dias = (dia - ini).days
    aliq = _rv.aliquota_ir(dias)
    # O rendimento resgatado é o que pagou IR mais o que pagou IOF: o IOF
    # (resgate com menos de 30 dias) sai do rendimento ANTES do IR, então
    # IR = (rendimento − IOF) × alíquota.
    rend_resgatado = ((resgate["ir"] / aliq) if aliq else 0.0) \
        + float(resgate.get("iof") or 0.0)
    principal = resgate["bruto"] - rend_resgatado
    aplicado_novo = round(aplicado - principal, 2)
    if principal <= 0 or aplicado_novo <= 0:
        return None, "o resgate é maior que o valor aplicado gravado"

    taxa = _rv.taxa_implicita(aplicado, bruto, pos.get("inicio"),
                              pos.get("posicao_em"))
    if taxa is None:
        return None, "a posição gravada não permite calcular o rendimento"
    bruto_no_dia = aplicado * (1 + taxa) ** dias
    bruto_novo = round(bruto_no_dia - resgate["bruto"], 2)
    if bruto_novo < aplicado_novo:
        return None, ("o saldo projetado ficou abaixo do aplicado — cole a "
                      "posição do extrato à mão")
    nova = {**pos,
            "aplicado": aplicado_novo,
            "bruto": bruto_novo,
            "liquido": _rv.liquido(aplicado_novo, bruto_novo,
                                   pos.get("inicio"), resgate["data"]),
            "posicao_em": resgate["data"],
            "ultimo_resgate": chave(resgate)}
    return nova, {"principal": round(principal, 2),
                  "rendimento": round(rend_resgatado, 2),
                  "aliquota": aliq}


def chave(resgate):
    """A impressão digital do comprovante: data do crédito + bruto resgatado."""
    return f"{resgate.get('data')}|{float(resgate.get('bruto') or 0):.2f}"


def ja_aplicado(pos, resgate):
    """(True, motivo) quando este comprovante NÃO pode ser descontado.

    A primeira versão comparava a posição gravada com a posição recalculada a
    partir dela — que nunca é igual, porque o principal sai de novo. Subir o
    mesmo PDF duas vezes descontava 13.174 duas vezes (revisão de 05/10).
    Agora a posição grava a chave do último comprovante, e posição gravada na
    data do resgate ou depois dele (extrato colado à mão) já o contém.
    """
    if str(pos.get("ultimo_resgate", "")) == chave(resgate):
        return True, "este comprovante já foi aplicado na posição gravada"
    em, dia = _rv._data(pos.get("posicao_em")), _rv._data(resgate.get("data"))
    if em and dia and em >= dia:
        return True, (f"a posição gravada é de {em.strftime('%d/%m/%Y')}, "
                      "do dia do resgate ou depois — ele já está nela")
    return False, ""


if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # O TEXTO É O QUE O pypdf EXTRAI DO COMPROVANTE REAL DE 02/10/2026 (sem as
    # linhas de agência e conta). A posição é a `POSICAO_INICIAL` de verdade.
    TEXTO = """Banco Itaú - Comprovante de resgate antecipado CDB-DI
Dados do crédito:
Data do crédito: 02/10/2026
Valor do crédito efetivado em conta: 13.353,87
Valor bruto resgatado: 13.406,09
Valor do IR: 52,22
Valor do IOF: 0,00
Valor líquido resgatado: 13.353,87
       Resgate efetuado em 02/10/2026 às 10:45:27 via 30 Horas Empresa Plus"""
    r, motivo = ler_texto(TEXTO)
    ok("lê a data do crédito", r and r["data"] == "2026-10-02")
    ok("lê o bruto, o IR e o líquido",
       r and (r["bruto"], r["ir"], r["liquido"]) == (13406.09, 52.22, 13353.87))
    ok("arquivo que não é resgate é recusado com motivo",
       ler_texto("Fatura do cartão")[0] is None
       and "resgate" in ler_texto("Fatura do cartão")[1])
    ok("comprovante sem IR não inventa número",
       ler_texto("resgate\nData do crédito: 02/10/2026")[0] is None)

    pos = dict(_rv.POSICAO_INICIAL)
    nova, det = posicao_apos(pos, r)
    ok("a conta do resgate fecha", nova is not None)
    nova = nova or {"aplicado": 0.0, "bruto": 0.0, "inicio": pos["inicio"],
                    "posicao_em": ""}
    det = det if isinstance(det, dict) else {"principal": None}
    ok("principal resgatado = bruto − IR ÷ alíquota (13.174,00)",
       det["principal"] == 13174.0)
    ok("aplicado depois do resgate bate com o print do banco (256.826,02)",
       abs(nova["aplicado"] - 256826.02) < 0.05)
    ok("o saldo bruto cai pelo bruto resgatado",
       nova["bruto"] < pos["bruto"] and nova["bruto"] > nova["aplicado"])
    ok("e fica perto do print de 3 dias depois (261.350,60)",
       abs(nova["bruto"] - 261350.60) < 400)
    ok("a posição passa a ser do dia do resgate",
       nova["posicao_em"] == "2026-10-02")
    ok("a taxa implícita continua positiva depois do resgate",
       (_rv.taxa_implicita(nova["aplicado"], nova["bruto"], nova["inicio"],
                           nova["posicao_em"]) or 0) > 0)
    # A CADEIA DA TELA: depois de gravar, a posição em vigor é `nova`, e o
    # mesmo PDF chega de novo. Era aqui que ele descontava duas vezes.
    ok("o mesmo comprovante não é descontado duas vezes",
       ja_aplicado(nova, r)[0] is True)
    ok("a chave do comprovante sozinha barra o PDF repetido",
       ja_aplicado({**pos, "ultimo_resgate": chave(r)}, r)[0] is True
       and "já foi aplicado" in ja_aplicado({**pos, "ultimo_resgate": chave(r)}, r)[1])
    ok("posição colada do extrato depois do resgate já o contém",
       ja_aplicado({**pos, "posicao_em": "2026-10-05"}, r)[0] is True)
    ok("e um resgate novo, posterior à posição, passa",
       ja_aplicado(pos, r)[0] is False)
    _r_iof = {**r, "iof": 10.0}
    ok("o IOF entra no rendimento resgatado (principal menor)",
       posicao_apos(pos, _r_iof)[1]["principal"] == round(det["principal"] - 10.0, 2))
    ok("resgate maior que o aplicado é recusado",
       posicao_apos({**pos, "aplicado": 1000.0, "bruto": 1010.0}, r)[0] is None)

    # ler_pdf: o caminho do upload. Bytes que não são PDF viram motivo, e um
    # PDF sem texto de resgate também — nunca um número inventado. (O PDF
    # real do Itaú não é commitado: tem agência e conta. Passou por esta
    # mesma cadeia à mão em 05/10 e deu 256.826,00 de aplicado.)
    ok("arquivo que não é PDF devolve motivo",
       ler_pdf(b"nao sou pdf")[0] is None
       and "PDF" in ler_pdf(b"nao sou pdf")[1])
    import io as _io_t
    import pypdf as _pypdf_t
    _w = _pypdf_t.PdfWriter()
    _w.add_blank_page(width=200, height=200)
    _buf = _io_t.BytesIO()
    _w.write(_buf)
    ok("PDF sem comprovante dentro é recusado",
       ler_pdf(_buf.getvalue())[0] is None)

    print("\nfalhas:", falhas)
    raise SystemExit(1 if falhas else 0)
