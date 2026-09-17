"""extrato_inter.py — o extrato do Inter, a conta de rua.

É a conta que o Renan usa na rua para comprar mercadoria e pagar o que aparece.
O formato é outro e a informação útil também: aqui quase tudo é Pix, e o que
importa não é o TIPO do lançamento — é PARA QUEM foi.

O FORMATO, CONFERIDO NO ARQUIVO DE AGOSTO/2026
----------------------------------------------
CSV separado por `;`, cinco linhas de cabeçalho antes da tabela:

    Extrato Conta Corrente
    Conta ;116183837
    Período ;01/08/2026 a 31/08/2026
    Saldo: ;1.227,26
    (vazia)
    Data Lançamento;Descrição;Valor;Saldo

E a descrição vem com o favorecido embutido:

    Pix enviado: "Cp :60701190-APEXIMP"          -> APEXIMP
    Pix enviado: "00019 202584690 PAN ZHENGZHONG" -> PAN ZHENGZHONG

O nome depois do hífen é quem recebeu. É ele que diz se aquilo foi mercadoria,
almoço da equipe ou custo fixo — e é por ele que o Studio aprende: uma vez
classificado "APEXIMP = mercadoria", as 20 linhas do mês seguinte já entram
classificadas.

NÚMERO BRASILEIRO
-----------------
Os valores vêm "-1.303,00". Lido com o separador trocado, isso vira -1303000.0
— mil vezes maior, num arquivo em que ninguém confere linha a linha.
"""

import csv
import io
import re

# A linha que abre a tabela. Antes dela é cabeçalho de conta, não lançamento.
TITULO = "data lançamento"


def _num(v):
    """'-1.303,00' -> -1303.0. None quando a célula está vazia."""
    t = str(v or "").strip().replace("R$", "").replace(" ", "")
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _data(v):
    from datetime import datetime
    t = str(v or "").strip()[:10]
    for f in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(t, f).date()
        except ValueError:
            continue
    return None


def favorecido(descricao):
    """Quem recebeu (ou de quem veio). "" quando não dá para saber.

    O Inter escreve `Pix enviado: "Cp :60701190-APEXIMP"`: o código antes do
    hífen é da instituição, e o nome vem depois. Quando não há hífen, o nome
    está solto depois de dois números — é o caso das transferências por chave.
    """
    t = str(descricao or "").strip()
    if not t:
        return ""
    dentro = re.search(r'"([^"]*)"', t)
    miolo = dentro.group(1) if dentro else t.split(":", 1)[-1]
    miolo = miolo.strip()
    if "-" in miolo:
        nome = miolo.rsplit("-", 1)[-1]
    else:
        # "00019 202584690 PAN ZHENGZHONG" — cai fora dos dois números.
        partes = [p for p in miolo.split() if not p.isdigit()]
        nome = " ".join(partes)
    return re.sub(r"\s+", " ", nome).strip()


def ler(dados):
    """(lançamentos, cabeçalho, erro). `valor` negativo é saída.

    Cada lançamento: {"data", "descricao", "favorecido", "valor", "sentido"}.
    """
    if isinstance(dados, bytes):
        # O Inter exporta em UTF-8, mas planilha salva por cima vira latin-1.
        # Testar os dois sai mais barato que descobrir pelo acento errado.
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

    cabecalho, linhas, achou = {}, [], False
    for campos in csv.reader(io.StringIO(texto), delimiter=";"):
        if not campos or not any(str(c).strip() for c in campos):
            continue
        primeiro = str(campos[0]).strip()
        if not achou:
            if primeiro.lower().startswith(TITULO):
                achou = True
            elif len(campos) > 1 and str(campos[1]).strip():
                cabecalho[primeiro.rstrip(":").strip().lower()] = str(campos[1]).strip()
            continue
        data = _data(primeiro)
        valor = _num(campos[2]) if len(campos) > 2 else None
        if data is None or valor is None:
            continue
        desc = str(campos[1]).strip() if len(campos) > 1 else ""
        linhas.append({
            "data": data,
            "descricao": desc,
            "favorecido": favorecido(desc),
            "valor": valor,
            "sentido": "saida" if valor < 0 else "entrada",
        })
    return linhas, cabecalho, ""


def por_favorecido(lancamentos, sentido="saida"):
    """{favorecido: {"n": int, "total": float}} — quem mais consumiu no mês.

    É a lista que o dono precisa ver uma vez: classificado o favorecido, todo
    lançamento dele entra classificado daí em diante.
    """
    fora = {}
    for l in (lancamentos or []):
        if sentido and l["sentido"] != sentido:
            continue
        nome = l["favorecido"] or "(sem nome)"
        d = fora.setdefault(nome, {"n": 0, "total": 0.0})
        d["n"] += 1
        d["total"] += abs(l["valor"])
    return fora


# ── Conferência ──────────────────────────────────────────────────────────────
# Forma real do arquivo de agosto/2026, com valores e nomes inventados.
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    ok("o favorecido sai de dentro das aspas",
       favorecido('Pix enviado: "Cp :60701190-APEXIMP"') == "APEXIMP")
    ok("nome com espaco vem inteiro",
       favorecido('Pix enviado: "Cp :18236120-Katia Sola de Araujo"')
       == "Katia Sola de Araujo")
    ok("nome com hifen no meio fica com a ultima parte, e nao com o codigo",
       favorecido('Pix recebido: "Cp :10573521-LITTLE GLASS COMERCIO"')
       == "LITTLE GLASS COMERCIO")
    ok("transferencia por chave, sem hifen, tambem devolve nome",
       favorecido('Pix enviado: "00019 202584690 PAN ZHENGZHONG"')
       == "PAN ZHENGZHONG")
    ok("descricao vazia nao derruba",
       favorecido("") == "" and favorecido(None) == "")

    # O numero brasileiro: lido errado, vira mil vezes maior.
    ok("valor com milhar e virgula", _num("-1.303,00") == -1303.0)
    ok("valor pequeno", _num("-15,56") == -15.56)
    ok("entrada e positiva", _num("2.181,29") == 2181.29)
    ok("celula vazia nao vira zero", _num("") is None and _num(None) is None)

    CSV = (
        "Extrato Conta Corrente \n"
        "Conta ;116183837\n"
        "Período ;01/08/2026 a 31/08/2026\n"
        "Saldo: ;1.227,26\n"
        "\n"
        "Data Lançamento;Descrição;Valor;Saldo\n"
        '03/08/2026;Pix enviado: "Cp :60701190-APEXIMP";-1.303,00;-1.402,11\n'
        '03/08/2026;Pix recebido: "Cp :90400888-MAREE";2.181,29;779,18\n'
        '04/08/2026;Pix enviado: "Cp :60701190-APEXIMP";-1.404,89;2.126,28\n'
    )
    _l, _cab, _e = ler(CSV.encode("utf-8"))
    ok("o cabecalho da conta e lido", _cab.get("conta") == "116183837")
    ok("as tres linhas viram lancamento, e o cabecalho nao", len(_l) == 3)
    ok("saida e entrada sao separadas pelo sinal",
       [x["sentido"] for x in _l] == ["saida", "entrada", "saida"])
    ok("o favorecido vem preenchido", _l[0]["favorecido"] == "APEXIMP")

    _f = por_favorecido(_l)
    ok("o acumulado por favorecido soma as duas saidas do mesmo",
       _f["APEXIMP"]["n"] == 2 and abs(_f["APEXIMP"]["total"] - 2707.89) < 0.01)
    ok("entrada nao entra no acumulado de saida", "MAREE" not in _f)

    print("\nfalhas:", falhas)
