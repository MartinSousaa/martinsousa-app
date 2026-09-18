"""cheques.py — o cheque emitido, que o extrato só conhece quando compensa.

O PROBLEMA
----------
O Studio só via um cheque no dia em que ele caía na conta. Um cheque dado hoje
para 60 dias não existia para o sistema até o débito aparecer — e é justamente
nesses 60 dias que a decisão "dá para comprar?" é tomada. Em setembro de 2026
eram R$ 51 mil de cheques a vencer que a tela de gastos não enxergava.

ONDE ELE JÁ ESTAVA
------------------
Na aba `CHEQUES` do Controle MS, que o dono mantém desde 2023: 654 linhas, 95
sem baixa. O Studio já lê essa planilha (`controle_ms.py`), mas só para leitura
— ela mora no OneDrive e não se escreve nela daqui.

Por isso o cadastro passa a morar AQUI, na aba `cheques` da planilha do Studio,
e o Controle MS entra uma vez, pelo botão de importar. Depois disso existe um
lugar só: cadastrar em dois seria a mesma pergunta com duas respostas, e elas
passam a discordar — a questão é só quando.

OS CAMPOS, COMO ELE OS MANTÉM
-----------------------------
    TIPO · COMPRA · VENCIMENTO · VALOR · ENVIO · ESTOQUE · FOLHA · PAGAMENTO

**VALOR = ENVIO + ESTOQUE** — a divisão do que aquele cheque pagou, frete e
mercadoria — e **FOLHA é o número do cheque**, sequencial no talão (507, 508,
509…). É ele que identifica a folha de verdade, e por isso manda na identidade
quando está preenchido.

EM ABERTO E PENDENTE NÃO SE DIGITAM
-----------------------------------
Na planilha do dono elas são duas colunas escritas à mão. Aqui são CONTA, e a
diferença entre as duas é a data de hoje:

    em aberto  -> sem baixa, venha a vencer quando vier
    pendente   -> sem baixa E o vencimento já passou

Escrever isso à mão significa que no dia seguinte já está errado: o cheque de
25/09 vira pendente sozinho em 26/09, e ninguém vai reabrir a planilha para
mover a célula.
"""

import hashlib
from datetime import date, datetime, timezone, timedelta

import streamlit as st

ABA_NOME = "cheques"
COLUNAS = ["id", "tipo", "folha", "compra", "vencimento", "valor", "envio",
           "estoque", "favorecido", "situacao", "observacao", "atualizado_em",
           "atualizado_por"]

FUSO = timezone(timedelta(hours=-3))

TIPOS = ("CHEQUE", "BOLETO")

# As situações que o dono já usa na planilha dele, e mais nada. "EM ABERTO" é o
# vazio dele, escrito por extenso: célula em branco e "ainda não baixou" eram a
# mesma coisa, e não dá para filtrar o que não tem nome.
SITUACOES = ("EM ABERTO", "DEBITADO", "PAGO", "PIX", "PERDIDO", "RASGADO")

# As que ainda vão sair do caixa. PERDIDO e RASGADO não saem — o cheque não
# existe mais. PIX, DEBITADO e PAGO já saíram, e vão aparecer no extrato.
ABERTAS = ("EM ABERTO",)


def _num(v, padrao=0.0):
    """Número, ou o padrão. `nan` NUNCA passa.

    `nan` é float, então `isinstance(v, float)` era verdadeiro e ele saía daqui
    inteiro. O Google recusa gravar: "Out of range float values are not JSON
    compliant: nan" — e a importação das 604 linhas morria depois de ler tudo,
    sem gravar nada.

    É o mesmo `nan` de célula vazia que já tinha sido peneirado do lado do
    TEXTO (`texto()`), e que eu deixei passar do lado do número. Metade do
    conserto é o conserto que volta.
    """
    if v is None:
        return padrao
    if isinstance(v, bool):
        return padrao
    if isinstance(v, (int, float)):
        f = float(v)
        # nan != nan é a única forma de detectá-lo sem importar `math`; e
        # infinito tem o mesmo destino, pelo mesmo motivo.
        if f != f or f in (float("inf"), float("-inf")):
            return padrao
        return f
    t = str(v).strip().replace("R$", "").replace(" ", "")
    if not t:
        return padrao
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return padrao


def texto(v):
    """Célula virando texto limpo. Vazio para o que não é conteúdo.

    O pandas transforma célula vazia em `nan`, e `str(nan)` é a palavra
    "nan" — texto, não vazio. Sem esta peneira, todo cheque sem número de
    folha virava `folha = "nan"`, e como a folha é a identidade, os 64 cheques
    antigos sem folha viravam UM só. Só apareceu rodando contra as 604 linhas
    de verdade: 540 ids para 604 cheques.
    """
    t = str(v).strip() if v is not None else ""
    return "" if t.lower() in ("nan", "nat", "none", "<na>") else t


def texto_folha(v):
    """O número da folha como o talão o escreve: 159, e não "159.0".

    O Excel devolve a coluna inteira como float, e "159.0" não casa com o
    "159" que alguém digita na tela — dois cheques onde há um.
    """
    t = texto(v)
    if not t:
        return ""
    try:
        f = float(t.replace(",", "."))
        if f == int(f):
            return str(int(f))
    except ValueError:
        pass
    return t


def texto_data(v):
    """Qualquer data virando "AAAA-MM-DD". "" quando não dá para ler.

    A planilha do dono devolve `datetime`; o formulário devolve `date`; a aba
    do Studio devolve texto. Três tipos para a mesma data, e comparar sem
    normalizar faz o mesmo cheque entrar duas vezes na importação.
    """
    # Ter `.year` não basta: a célula de data VAZIA do Excel chega aqui como
    # `pd.NaT`, que tem `.year` — e ele vale `nan`, um float. `f"{nan:04d}"`
    # levanta ValueError e derruba a importação inteira na primeira linha em
    # branco. Foi o que aconteceu ao importar as 654 linhas.
    a, m, d = getattr(v, "year", None), getattr(v, "month", None), \
        getattr(v, "day", None)
    if all(isinstance(x, int) for x in (a, m, d)):
        return f"{a:04d}-{m:02d}-{d:02d}"
    t = str(v or "").strip()[:10]
    # "NaT" e "nan" viram texto por este caminho, e texto não é data.
    if t.lower() in ("nat", "nan", "none", "-"):
        return ""
    if not t:
        return ""
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(t, f).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return t


def situacao_de(v):
    """O texto da planilha virando uma das situações. Vazio é EM ABERTO."""
    t = " ".join(texto(v).upper().split())
    if not t:
        return "EM ABERTO"
    return t if t in SITUACOES else t[:30]


def esta_aberto(linha):
    """Este cheque ainda vai sair do caixa?"""
    return situacao_de(linha.get("situacao")) in ABERTAS


def identidade(linha):
    """A impressão digital do cheque.

    A FOLHA quando existe: é o número do talão, e dois cheques nunca a
    repetem. Sem ela, vencimento + valor + compra — a planilha do dono tem
    linhas antigas sem folha preenchida, e recusá-las deixaria de fora justo o
    histórico que se quer importar.
    """
    folha = texto_folha(linha.get("folha"))
    if folha:
        return hashlib.sha1(("folha|" + folha).encode("utf-8")).hexdigest()[:16]
    bruto = "|".join([
        texto_data(linha.get("compra")),
        texto_data(linha.get("vencimento")),
        f"{_num(linha.get('valor')):.2f}",
        str(linha.get("tipo") or "CHEQUE").strip().upper(),
    ])
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()[:16]


def normalizar(linha, seq=0):
    """Uma linha crua virando o registro do Studio, com id.

    `seq` separa duas linhas idênticas em tudo. Elas existem: na planilha do
    dono há dois pares iguais, de 2023 e 2024, ambos já baixados. Descartar a
    segunda deixaria o histórico menor do que é, e em silêncio.
    """
    fora = {
        "folha": texto_folha(linha.get("folha"))[:20],
        "tipo": (texto(linha.get("tipo")).upper()
                 if texto(linha.get("tipo")).upper() in TIPOS else "CHEQUE"),
        "compra": texto_data(linha.get("compra")),
        "vencimento": texto_data(linha.get("vencimento")),
        "valor": round(_num(linha.get("valor")), 2),
        "envio": round(_num(linha.get("envio")), 2),
        # ESTOQUE NÃO SE DIGITA: é VALOR − ENVIO, conferido nas 604 linhas da
        # planilha do dono. Campo que se calcula e mesmo assim se pede é convite
        # a erro de digitação — e um erro aqui não aparece em lugar nenhum,
        # porque a soma do cheque continua certa.
        #
        # Quando vem preenchido (a importação do Controle MS traz), o valor
        # informado é respeitado: é o histórico dele, e reescrever passado com
        # conta minha seria inventar número.
        "estoque": round(_num(linha.get("estoque")), 2),
        "favorecido": texto(linha.get("favorecido"))[:80],
        "situacao": situacao_de(linha.get("situacao")),
        "observacao": texto(linha.get("observacao"))[:200],
    }
    if not fora["estoque"] and fora["valor"]:
        fora["estoque"] = round(fora["valor"] - fora["envio"], 2)
    fora["id"] = identidade(fora)
    if seq:
        fora["id"] = hashlib.sha1(
            f"{fora['id']}|{seq}".encode("utf-8")).hexdigest()[:16]
    return fora


def dividir_em(total, n):
    """`total` repartido em `n` partes que SOMAM o total. [] se n < 1.

    O centavo é o motivo desta função existir. R$ 3.211,61 em dois cheques dá
    1.605,805 cada: arredondar os dois para 1.605,81 cria um centavo que não
    existe, e para 1.605,80 some com um. Nenhum dos dois aparece na hora — os
    dois aparecem no fechamento do mês, quando a soma dos cheques não bate com
    a compra e ninguém sabe de onde veio a diferença.

    Aqui a sobra vai para os PRIMEIROS cheques, um centavo cada, até acabar. O
    primeiro a vencer paga o centavo a mais — e a soma fecha sempre.
    """
    n = int(n or 0)
    if n < 1:
        return []
    centavos = int(round(abs(_num(total)) * 100))
    base, sobra = divmod(centavos, n)
    return [round((base + (1 if i < sobra else 0)) / 100.0, 2)
            for i in range(n)]


def lote(comum, folhas, vencimentos, valor_total, envio_total=0.0):
    """Os N cheques de uma compra só. Lista pronta para `gravar`.

    `comum` é o que não muda entre eles — compra, favorecido, tipo, situação.
    Folha e vencimento são de cada um; valor e envio saem da divisão.

    Existe porque é assim que a compra acontece: o Renan fecha R$ 3.211,60 com
    o fornecedor e deixa dois cheques de R$ 1.605,80 para datas diferentes.
    Preencher a mesma compra duas vezes é trabalho repetido — e trabalho
    repetido é onde entra o erro de digitação que ninguém confere.
    """
    n = max(len(folhas or []), len(vencimentos or []))
    if not n:
        return []
    valores = dividir_em(valor_total, n)
    envios = dividir_em(envio_total, n)
    fora = []
    for i in range(n):
        f = (folhas or [])[i] if i < len(folhas or []) else ""
        v = (vencimentos or [])[i] if i < len(vencimentos or []) else ""
        fora.append({**(comum or {}), "folha": f, "vencimento": v,
                     "valor": valores[i], "envio": envios[i]})
    return fora


def divergencia_da_soma(linha, tolerancia=0.01):
    """Quanto VALOR − ENVIO − ESTOQUE dá de diferença. 0 quando fecha.

    Serve para a importação: a planilha do dono é mantida à mão desde 2023, e
    uma linha que não fecha é erro de digitação lá, não aqui. O Studio mostra;
    não corrige sozinho — corrigir seria trocar o número dele pelo meu sem
    ninguém pedir.
    """
    d = round(_num(linha.get("valor")) - _num(linha.get("envio"))
              - _num(linha.get("estoque")), 2)
    return 0.0 if abs(d) <= tolerancia else d


def nao_fecham(linhas):
    """As linhas cuja soma não bate, da maior diferença para a menor."""
    fora = [(divergencia_da_soma(l), l) for l in (linhas or [])]
    fora = [(d, l) for d, l in fora if d]
    return [l for _, l in sorted(fora, key=lambda x: -abs(x[0]))]


def do_mes(linhas, ano, mes):
    """Os cheques que VENCEM naquele mês, em ordem de vencimento."""
    alvo = f"{int(ano):04d}-{int(mes):02d}"
    fora = [l for l in (linhas or [])
            if texto_data(l.get("vencimento")).startswith(alvo)]
    return sorted(fora, key=lambda l: texto_data(l.get("vencimento")))


def a_vencer(linhas, ano, mes):
    """Quanto ainda vai sair em cheque naquele mês. Só o que está em aberto.

    O que já foi debitado fica de fora porque o extrato o traz — somar os dois
    contaria o mesmo cheque duas vezes, que é o erro que o `previsto` existe
    para não cometer.
    """
    return round(sum(_num(l.get("valor"))
                     for l in do_mes(linhas, ano, mes) if esta_aberto(l)), 2)


def vencidos_sem_baixa(linhas, hoje=None):
    """Em aberto com vencimento já passado — cheque que devia ter caído.

    Ou a baixa não foi dada, ou o cheque não foi apresentado. Nos dois casos é
    trabalho parado, e é a única lista desta tela que pede ação.
    """
    limite = texto_data(hoje or datetime.now(FUSO).date())
    fora = [l for l in (linhas or [])
            if esta_aberto(l) and texto_data(l.get("vencimento")) < limite
            and texto_data(l.get("vencimento"))]
    return sorted(fora, key=lambda l: texto_data(l.get("vencimento")))


def em_aberto(linhas, ano=None, mes=None):
    """Quanto ainda não baixou. Com ano/mês, só o que vence naquele mês."""
    alvo = (do_mes(linhas, ano, mes) if ano and mes else (linhas or []))
    return round(sum(_num(l.get("valor")) for l in alvo if esta_aberto(l)), 2)


def pendente(linhas, hoje=None):
    """Quanto venceu e não baixou. É a coluna PENDENTE, calculada na hora.

    Escrever isso na planilha significa errar no dia seguinte: o cheque de
    25/09 vira pendente sozinho em 26/09, e ninguém reabre a planilha para
    mover a célula.
    """
    return round(sum(_num(l.get("valor"))
                     for l in vencidos_sem_baixa(linhas, hoje)), 2)


def resumo(linhas):
    """{situacao: {"n", "total"}} — o panorama da carteira."""
    fora = {}
    for l in (linhas or []):
        s = situacao_de(l.get("situacao"))
        d = fora.setdefault(s, {"n": 0, "total": 0.0})
        d["n"] += 1
        d["total"] = round(d["total"] + _num(l.get("valor")), 2)
    return dict(sorted(fora.items(), key=lambda x: -x[1]["total"]))


# ── Planilha ─────────────────────────────────────────────────────────────────

def _aba():
    import gspread
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        return planilha.worksheet(ABA_NOME)
    except gspread.WorksheetNotFound:
        nova = planilha.add_worksheet(title=ABA_NOME, rows=2000,
                                      cols=len(COLUNAS))
        nova.append_row(COLUNAS, value_input_option="RAW")
        return nova


def _limpar_caches():
    """Esquece o que ficou velho — aqui E no comprometido do mês.

    Cheque que entra muda o comprometido da Home na hora, e não daqui a cinco
    minutos: `previsto.do_mes` tem cache próprio, e quem grava cheque é quem
    sabe que ele venceu. Sem esta linha, o dono importava 604 cheques e a Home
    continuava mostrando o número de antes, sem nada na tela explicando por quê.
    """
    carregar.clear()
    try:
        import previsto as _pv
        _pv.do_mes.clear()
    except Exception:
        pass


@st.cache_data(ttl=120)
def carregar():
    """[{...}] da aba. Lista vazia em qualquer falha."""
    try:
        registros = _aba().get_all_records()
    except Exception:
        return []
    fora = []
    for r in registros:
        if not str(r.get("id", "") or "").strip():
            continue
        fora.append({c: r.get(c, "") for c in COLUNAS})
    return fora


def gravar(novas, usuario=""):
    """Acrescenta o que ainda não existe. (novas, repetidas, erro).

    Nunca reescreve linha existente: reimportar o Controle MS não pode apagar a
    baixa que alguém deu na tela do Studio.
    """
    agora = datetime.now(FUSO).strftime("%Y-%m-%d %H:%M")
    try:
        aba = _aba()
        ja = {str(r.get("id", "")).strip()
              for r in aba.get_all_records() if str(r.get("id", "")).strip()}
        linhas, vistos, repetidas = [], set(), 0
        for l in (novas or []):
            n = normalizar(l)
            # Gêmea dentro do MESMO lote ganha sequência; gêmea do que já está
            # gravado é repetição de verdade e fica de fora.
            seq = 0
            while n["id"] in vistos and seq < 20:
                seq += 1
                n = normalizar(l, seq)
            if n["id"] in ja or n["id"] in vistos:
                repetidas += 1
                continue
            vistos.add(n["id"])
            linhas.append([n[c] if c in n else "" for c in COLUNAS[:-2]]
                          + [agora, str(usuario or "")[:60]])
        if linhas:
            aba.append_rows(linhas, value_input_option="RAW")
    except Exception as e:
        return 0, 0, str(e)[:200]
    _limpar_caches()
    return len(linhas), repetidas, ""


def atualizar(id_cheque, campos, usuario=""):
    """Altera uma linha já gravada. (ok, mensagem)."""
    alvo = str(id_cheque or "").strip()
    if not alvo:
        return False, "Sem id não dá para saber qual linha alterar."
    try:
        aba = _aba()
        registros = aba.get_all_records()
        achados = [i for i, r in enumerate(registros)
                   if str(r.get("id", "")).strip() == alvo]
        if not achados:
            return False, "Não achei este cheque na aba."
        i = achados[-1]
        atual = dict(registros[i])
        atual.update({k: v for k, v in (campos or {}).items() if k in COLUNAS})
        atual["atualizado_em"] = datetime.now(FUSO).strftime("%Y-%m-%d %H:%M")
        atual["atualizado_por"] = str(usuario or "")[:60]
        fim = chr(ord("A") + len(COLUNAS) - 1)
        n = i + 2
        aba.update([[atual.get(c, "") for c in COLUNAS]], f"A{n}:{fim}{n}",
                   value_input_option="RAW")
    except Exception as e:
        return False, str(e)[:200]
    _limpar_caches()
    return True, "Alterado."


def apagar(ids):
    """Remove linhas pelo id. (quantas, erro)."""
    alvos = {str(i).strip() for i in (ids or []) if str(i).strip()}
    if not alvos:
        return 0, ""
    try:
        aba = _aba()
        registros = aba.get_all_records()
        fora = [i for i, r in enumerate(registros)
                if str(r.get("id", "")).strip() in alvos]
        for i in reversed(fora):
            aba.delete_rows(i + 2)
    except Exception as e:
        return 0, str(e)[:200]
    _limpar_caches()
    return len(fora), ""


def do_controle_ms(limite=None):
    """Lê a aba CHEQUES do Controle MS. ([linhas], erro).

    Uma importação só: depois disso o cadastro vive no Studio. Reimportar não
    duplica (a identidade é a mesma) nem desfaz baixa dada aqui.
    """
    import controle_ms as _cms
    df, erro = _cms.ler("CHEQUES", limite=limite)
    if erro:
        return [], erro
    if df.empty:
        return [], "A aba CHEQUES do Controle MS veio vazia."
    col = {str(c).strip().upper(): c for c in df.columns}

    def pega(linha, *nomes):
        for n in nomes:
            if n in col:
                v = linha.get(col[n])
                if v is not None and str(v).strip() != "":
                    return v
        return None

    fora = []
    for _, r in df.iterrows():
        venc = texto_data(pega(r, "VENCIMENTO"))
        valor = _num(pega(r, "VALOR"))
        # Data que não virou AAAA-MM-DD é lixo, não data: o serial do Excel
        # ("45000.0") passaria como texto e viraria um vencimento que não
        # existe, dentro de um total que ninguém confere linha a linha.
        if len(venc) != 10 or venc[4] != "-" or not valor:
            continue
        fora.append({
            "tipo": pega(r, "TIPO") or "CHEQUE",
            "folha": pega(r, "FOLHA") or "",
            "compra": pega(r, "COMPRA"),
            "vencimento": venc,
            "valor": valor,
            "envio": _num(pega(r, "ENVIO")),
            "estoque": _num(pega(r, "ESTOQUE")),
            "favorecido": pega(r, "FAVORECIDO", "DESTINATÁRIO") or "",
            "situacao": situacao_de(pega(r, "PAGAMENTO", "SITUACAO")),
            "observacao": "",
        })
    return fora, ""


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    ok("datetime vira texto", texto_data(datetime(2026, 9, 25)) == "2026-09-25")
    ok("date tambem", texto_data(date(2026, 9, 25)) == "2026-09-25")
    ok("data brasileira tambem", texto_data("25/09/2026") == "2026-09-25")
    ok("texto ja pronto passa", texto_data("2026-09-25") == "2026-09-25")
    ok("vazio nao vira data", texto_data(None) == "" and texto_data("") == "")

    # A celula de data VAZIA do Excel: tem `.year`, e ele vale nan. Era este o
    # objeto que derrubava a importacao das 654 linhas na primeira em branco.
    class _NaTFalso:
        year = month = day = float("nan")

        def __str__(self):
            return "NaT"

    # O pandas devolve celula vazia como `nan`, e `str(nan)` e a palavra "nan".
    # Sem peneirar, todo cheque sem folha virava `folha = "nan"` — e como a
    # folha e a identidade, 64 cheques viravam UM. So apareceu rodando contra
    # as 604 linhas de verdade.
    _nan = float("nan")
    ok("nan nao e texto", texto(_nan) == "" and texto(None) == ""
       and texto("nan") == "")
    # O QUE DERRUBOU A IMPORTACAO DAS 604 LINHAS: `nan` E float, entao passava
    # direto por `isinstance(v, float)` e ia parar na planilha. O Google recusa:
    # "Out of range float values are not JSON compliant: nan".
    ok("nan tambem nao e numero", _num(_nan) == 0.0)
    ok("nem infinito", _num(float("inf")) == 0.0 and _num(float("-inf")) == 0.0)
    ok("e o numero de verdade continua passando",
       _num(1409.89) == 1409.89 and _num("1.409,89") == 1409.89)
    ok("celula vazia com padrao proprio devolve o padrao",
       _num(_nan, 7.0) == 7.0)
    ok("nenhum campo do cheque sai como nan",
       all(v == v for k, v in normalizar({"valor": _nan, "envio": _nan,
                                          "estoque": _nan}).items()
           if isinstance(v, float)))
    ok("dois cheques sem folha continuam sendo dois",
       normalizar({"folha": _nan, "vencimento": "2026-09-04",
                   "valor": 1409.89})["id"]
       != normalizar({"folha": _nan, "vencimento": "2026-09-12",
                      "valor": 4330.98})["id"])

    # ESTOQUE E CONTA, e nao campo: VALOR - ENVIO.
    ok("estoque sai da conta quando nao vem preenchido",
       normalizar({"valor": 1605.80, "envio": 1600.00})["estoque"] == 5.80)
    ok("cheque inteiro de mercadoria da envio zero",
       normalizar({"valor": 2500.0})["estoque"] == 2500.0)
    ok("envio maior que o valor da estoque negativo, e nao zero",
       normalizar({"valor": 875.39, "envio": 1200.00})["estoque"] == -324.61)
    ok("estoque informado e respeitado — e o historico do dono",
       normalizar({"valor": 1000.0, "envio": 100.0,
                   "estoque": 950.0})["estoque"] == 950.0)
    ok("sem valor, nao inventa estoque",
       normalizar({"envio": 100.0})["estoque"] == 0.0)

    ok("a linha que nao fecha e apontada, e nao corrigida",
       divergencia_da_soma({"valor": 1000, "envio": 100, "estoque": 950}) == -50.0)
    ok("centavo de arredondamento nao vira divergencia",
       divergencia_da_soma({"valor": 1000.0, "envio": 100.0,
                            "estoque": 899.995}) == 0.0)
    ok("e a lista vem da maior diferenca para a menor",
       [l["valor"] for l in nao_fecham([
           {"valor": 100, "envio": 0, "estoque": 90},      # -10
           {"valor": 200, "envio": 0, "estoque": 100},     # -100
           {"valor": 300, "envio": 100, "estoque": 200},   # fecha
       ])] == [200, 100])

    # ── O LOTE: uma compra, varios cheques ───────────────────────────────
    #
    # O centavo e o motivo de `dividir_em` existir: 3.211,61 em dois da
    # 1.605,805, e arredondar os dois para o mesmo lado inventa ou some com um
    # centavo — que so aparece no fechamento do mes, sem origem.
    ok("divisao exata da partes iguais",
       dividir_em(3211.60, 2) == [1605.80, 1605.80])
    ok("e a soma fecha sempre", sum(dividir_em(3211.60, 2)) == 3211.60)
    ok("o centavo que sobra vai para o primeiro",
       dividir_em(3211.61, 2) == [1605.81, 1605.80])
    ok("com tres, sobram dois centavos, um para cada um dos dois primeiros",
       dividir_em(100.02, 3) == [33.34, 33.34, 33.34]
       and sum(dividir_em(100.01, 3)) == 100.01)
    ok("um cheque so leva tudo", dividir_em(1605.80, 1) == [1605.80])
    ok("zero cheques nao divide nada", dividir_em(100, 0) == []
       and dividir_em(100, -1) == [])
    ok("total zero da zeros, e nao vazio", dividir_em(0, 2) == [0.0, 0.0])

    # O caso que o dono descreveu: compra de 3.211,60 em dois cheques, 569 e
    # 572, vencimentos diferentes, 1.400 de frete dividido entre eles.
    _l = lote({"favorecido": "LEXTACK", "compra": "2026-09-18",
               "situacao": "EM ABERTO"},
              ["569", "572"], ["2026-10-02", "2026-11-02"],
              3211.60, 1400.00)
    ok("o lote gera um cheque por folha", len(_l) == 2)
    ok("com o valor dividido igualmente",
       [c["valor"] for c in _l] == [1605.80, 1605.80])
    ok("e o frete tambem", [c["envio"] for c in _l] == [700.00, 700.00])
    ok("cada um com seu vencimento",
       [c["vencimento"] for c in _l] == ["2026-10-02", "2026-11-02"])
    ok("e o que e comum se repete em todos",
       all(c["favorecido"] == "LEXTACK" and c["compra"] == "2026-09-18"
           for c in _l))
    ok("a soma dos cheques do lote e a compra",
       round(sum(c["valor"] for c in _l), 2) == 3211.60)
    # E cada um deles, normalizado, ja traz a mercadoria calculada.
    _n = [normalizar(c) for c in _l]
    ok("e a mercadoria de cada um sai da conta",
       [c["estoque"] for c in _n] == [905.80, 905.80])
    ok("dois cheques do mesmo lote sao dois registros",
       _n[0]["id"] != _n[1]["id"])
    ok("lote sem folha nem vencimento nao inventa cheque",
       lote({}, [], [], 1000) == [])

    ok("a folha vem sem o .0 do Excel",
       normalizar({"folha": 159.0, "valor": 1})["folha"] == "159")
    ok("e folha com letra nao vira numero",
       normalizar({"folha": "A-12", "valor": 1})["folha"] == "A-12")
    ok("linha gemea com seq nao colide",
       normalizar({"vencimento": "2023-11-07", "valor": 1503.46})["id"]
       != normalizar({"vencimento": "2023-11-07", "valor": 1503.46}, 1)["id"])

    ok("celula de data vazia do Excel nao derruba",
       texto_data(_NaTFalso()) == "")
    ok("nem o texto que ela vira", texto_data("NaT") == ""
       and texto_data("nan") == "")
    ok("e ela nao entra como cheque",
       normalizar({"vencimento": _NaTFalso(), "valor": 10})["vencimento"] == "")

    # O vazio da planilha do dono E "em aberto" — sem nome, nao da para filtrar.
    ok("celula vazia e em aberto", situacao_de(None) == "EM ABERTO")
    ok("debitado passa inteiro", situacao_de(" debitado ") == "DEBITADO")

    C = [
        {"vencimento": "2026-09-04", "valor": 1409.89, "situacao": ""},
        {"vencimento": "2026-09-12", "valor": 4330.98, "situacao": ""},
        {"vencimento": "2026-09-18", "valor": 2487.08, "situacao": "DEBITADO"},
        {"vencimento": "2026-09-25", "valor": 3476.60, "situacao": ""},
        {"vencimento": "2026-10-02", "valor": 999.00, "situacao": ""},
        {"vencimento": "2026-06-18", "valor": 0.0, "situacao": "RASGADO"},
    ]
    ok("o mes traz so os que vencem nele", len(do_mes(C, 2026, 9)) == 4)
    ok("e em ordem de vencimento",
       [l["vencimento"] for l in do_mes(C, 2026, 9)]
       == ["2026-09-04", "2026-09-12", "2026-09-18", "2026-09-25"])
    # O debitado ja esta no extrato: somar os dois contaria o cheque duas vezes.
    ok("a vencer ignora o que ja foi debitado",
       a_vencer(C, 2026, 9) == round(1409.89 + 4330.98 + 3476.60, 2))
    ok("mes sem cheque nao inventa", a_vencer(C, 2026, 11) == 0.0)
    ok("rasgado nao esta aberto",
       not esta_aberto({"situacao": "RASGADO"})
       and esta_aberto({"situacao": ""}))

    _atrasados = vencidos_sem_baixa(C, date(2026, 9, 17))
    ok("vencido sem baixa e trabalho parado", len(_atrasados) == 2)
    ok("e o debitado nao entra nessa lista",
       all(x["situacao"] != "DEBITADO" for x in _atrasados))

    # A identidade tem de sobreviver aos tres tipos de data, ou a importacao
    # entra de novo com tudo.
    _a = normalizar({"compra": datetime(2026, 6, 25),
                     "vencimento": datetime(2026, 9, 25), "valor": 3476.6})
    _b = normalizar({"compra": "25/06/2026", "vencimento": "2026-09-25",
                     "valor": "3.476,60"})
    ok("o mesmo cheque em tres grafias tem um id so", _a["id"] == _b["id"])
    ok("valor diferente e outro cheque",
       normalizar({"vencimento": "2026-09-25", "valor": 10})["id"] != _a["id"])
    ok("e o normalizado ja vem com situacao", _a["situacao"] == "EM ABERTO")

    # A FOLHA e o numero do talao: identidade de verdade, quando existe.
    ok("a folha manda na identidade",
       normalizar({"folha": 515, "vencimento": "2026-09-07", "valor": 1356.01})["id"]
       == normalizar({"folha": "515", "vencimento": "2099-01-01",
                      "valor": 1.0})["id"])
    ok("sem folha, a identidade volta a ser data+valor",
       normalizar({"vencimento": "2026-09-07", "valor": 1356.01})["id"]
       != normalizar({"folha": "515", "vencimento": "2026-09-07",
                      "valor": 1356.01})["id"])

    # EM ABERTO e PENDENTE sao conta, e a diferenca entre elas e a data de hoje.
    ok("em aberto e tudo que nao baixou",
       em_aberto(C) == round(1409.89 + 4330.98 + 3476.60 + 999.0, 2))
    ok("em aberto do mes olha so o vencimento dele",
       em_aberto(C, 2026, 9) == round(1409.89 + 4330.98 + 3476.60, 2))
    ok("pendente e o que venceu e nao baixou",
       pendente(C, date(2026, 9, 17)) == round(1409.89 + 4330.98, 2))
    ok("no dia seguinte o de 18 ainda nao venceu, e o de 25 tampouco",
       pendente(C, date(2026, 9, 13)) == round(1409.89 + 4330.98, 2))
    ok("com o mes todo corrido, pendente engloba os tres",
       pendente(C, date(2026, 10, 1))
       == round(1409.89 + 4330.98 + 3476.60, 2))

    _r = resumo(C)
    ok("o resumo separa por situacao", _r["EM ABERTO"]["n"] == 4)
    ok("e soma o valor de cada uma",
       _r["EM ABERTO"]["total"] == round(1409.89 + 4330.98 + 3476.60 + 999.0, 2))

    print("\nfalhas:", falhas)
