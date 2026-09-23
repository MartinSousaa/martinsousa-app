"""devolucoes.py — a devolução deixa de morar na planilha e passa a morar aqui.

O QUE ELA PRECISA RESPONDER
---------------------------
    quanto do que vendi voltou?    % sobre o faturado, do mês e do ano
    por que voltou?                top 5 motivos, mês e período
    a culpa foi nossa?             o FRETE responde — regra do dono
    o que ainda está aberto?       fica visível até alguém marcar resolvido

UMA VENDA COM DOIS PRODUTOS É UMA DEVOLUÇÃO SÓ
-----------------------------------------------
Palavra do dono: *"se a venda contiver mais de um produto, às vezes o cliente
devolve somente 1, ou os dois, isso deve gerar uma única devolução, mas
contendo os dois produtos com valores entre eles somados"*.

Por isso o cadastro marca ITENS, e Produto, SKU, Quantidade e Valor são a soma
do que foi marcado — nunca uma linha por produto.

O NOME MENTIU; O VALOR NUNCA
-----------------------------
No histórico ele não sabia dizer o que tinha voltado: *"às vezes colocou o
nome de só um produto ou com outro nome"*. Sabe sim — o valor entrega.
Das 7 devoluções de pedido com mais de um item, 6 fecham com UMA combinação:

    "2 XADREZ"    R$ 119,98  -> os dois enfeites de xadrez
    "URSINHOS"    R$  66,34  -> só os ursos; as bailarinas ficaram
    "MEIÃO"       R$  39,98  -> os dois meiões
    "MÁQUINA A4"  R$ 956,36  -> DUAS combinações fecham: este fica marcado

`combinacao_que_fecha` é isso. Quando mais de uma soma dá o mesmo valor, ela
NÃO escolhe: devolve ambíguo e a linha entra para conferência. Chutar aqui
seria inventar o que voltou para o estoque.

O FRETE É QUEM DIZ DE QUEM FOI A CULPA
---------------------------------------
Regra dele, não dedução minha: *"devoluções sem valor de frete quer dizer que
o motivo dessa devolução não foi culpa nossa. Quando tiver valor, o motivo foi
culpa nossa (outro produto, outra cor, produto com defeito, quebrado...)"*.

No ano: arrependimento é 65,5% do valor devolvido e custa R$ 12,96 de frete —
não é falha nossa. PRODUTO DANIFICADO são 26 casos e R$ 625,15 de frete,
metade de todo o frete de devolução. Isso é embalagem, não cliente.

RECORRIDO NÃO ZERA NADA SOZINHO
--------------------------------
*"Se no campo Situação estiver preenchido com Recorrido quer dizer que
recorremos à plataforma e ela nos reembolsou, zerando o que foi cobrado, não
deve alterar automaticamente, deixe para removermos os valores manualmente,
às vezes reembolsam parcialmente"*. Então o Studio não mexe em valor nenhum
por causa da situação. Quem apaga é ele.

NF DE DEVOLUÇÃO É IMPOSTO, NÃO BUROCRACIA
------------------------------------------
Sem cancelar a NF de venda ou emitir a de devolução, paga-se imposto sobre
produto que voltou. Por isso a falta dela é avisada, e não só deixada em
branco.
"""

import hashlib
import itertools
import unicodedata
from datetime import date, datetime, timezone, timedelta

import streamlit as st

FUSO = timezone(timedelta(hours=-3))

ABA = "devolucoes"

COLUNAS = ["id", "data_venda", "data_solic", "pedido", "sku", "produto",
           "quantidade", "valor", "conta", "envios", "usuario", "nome",
           "motivo", "frete", "conferencia", "situacao", "nf_devolucao",
           "status", "resolvido", "atualizado_em", "atualizado_por"]

# Os seis que não podem faltar. O resto pode: "nem sempre temos todas as
# informações", e travar o cadastro por um campo vazio empurra a pessoa de
# volta para a planilha, que é o lugar de onde estamos tirando o trabalho.
OBRIGATORIOS = ("data_solic", "envios", "produto", "motivo", "conferencia",
                "situacao")

ROTULOS = {"data_solic": "Data da solicitação", "envios": "Envios",
           "produto": "Produto", "motivo": "Motivo",
           "conferencia": "Data de conferência", "situacao": "Situação"}

# Como ele escreve na planilha, e nada além disso.
ENVIOS = ("ENVIOS", "EXPRESS", "FLEX", "ANJUN", "FULL", "J&T")

MOTIVOS = ("SE ARREPENDEU DA COMPRA", "FALHA NA ENTREGA", "PRODUTO DANIFICADO",
           "PRODUTO ERRADO", "DEFEITO", "PRODUTO QUEBRADO", "PRODUTO DIFERENTE",
           "TAMANHO ERRADO", "FALTA ITENS")

SITUACOES = ("OK", "RECORRENDO", "RECORRIDO", "RETORNOU PARA O FULL",
             "REEMBOLSO")

# Situação que mantém a devolução em aberto por natureza. RECORRENDO é a que
# ele usa hoje na linha que fica esperando resposta da plataforma.
ABERTAS = ("RECORRENDO",)

# Plataforma na BASE DE VENDAS -> conta como ele a chama.
CONTAS = {"mercadolivre1": "ML1", "mercadolivre2": "ML2",
          "mercadolivre3": "ML3", "mercadolivre4": "ML4",
          "shopee1": "SHOP01", "shopee2": "SHOP02",
          "shein1": "SHEIN01", "shein2": "SHEIN02"}

# Acima disto, testar todas as combinações de itens custa mais do que vale.
# Um pedido de 14 itens dá 16.383 somas; nenhum pedido desta base passa de 4.
MAX_ITENS_COMBINACAO = 14


def _chave(t):
    t = unicodedata.normalize("NFKD", str(t or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).lower().strip()


def num(v, padrao=0.0):
    if v is None or v == "":
        return padrao
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace("R$", "").replace(" ", "")
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return padrao


def texto_data(v):
    """Data em AAAA-MM-DD — o formato que ordena sozinho e não vira 03/04."""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    t = str(v or "").strip()
    if not t:
        return ""
    if len(t) >= 10 and t[4] == "-":
        return t[:10]
    # dd/mm/aaaa, que é como a planilha dele às vezes devolve
    p = t.replace("-", "/").split("/")
    if len(p) == 3 and len(p[0]) <= 2:
        return f"{p[2][:4]}-{int(p[1]):02d}-{int(p[0]):02d}"
    return t[:10]


def data_br(v):
    t = texto_data(v)
    return f"{t[8:10]}/{t[5:7]}/{t[:4]}" if len(t) == 10 else (t or "—")


def mes_de(v):
    """AAAA-MM de uma data. É por ele que a tela separa os meses."""
    return texto_data(v)[:7]


def conta_da_plataforma(plataforma):
    """'MercadoLivre2' -> 'ML2'. Desconhecida volta como veio, em maiúsculas.

    Devolver o texto cru em vez de vazio é de propósito: o TikTok existe nas
    devoluções e não existe na BASE DE VENDAS. Engolir isso faria a conta
    aparecer em branco sem ninguém saber por quê.
    """
    k = _chave(plataforma).replace(" ", "")
    return CONTAS.get(k, str(plataforma or "").strip().upper())


# ── O valor diz o que voltou ────────────────────────────────────────────────

def combinacao_que_fecha(valores, alvo, tolerancia=0.01):
    """(indices, ambiguo) — quais itens somam exatamente o valor devolvido.

    `indices` é a única combinação que fecha, ou [] se nenhuma fecha.
    `ambiguo` é True quando mais de uma fecha — e aí o Studio NÃO escolhe.

    Nasceu do histórico: o nome do produto foi escrito resumido ("MEIÃO" para
    dois meiões), mas o valor sempre foi a soma certa. Reconstruir pelo valor
    acerta 6 dos 7 casos; o sétimo tem duas somas iguais e fica para alguém
    olhar.
    """
    vals = [num(v) for v in (valores or [])]
    a = num(alvo)
    if not vals or len(vals) > MAX_ITENS_COMBINACAO:
        return [], False
    fecham = []
    for k in range(1, len(vals) + 1):
        for c in itertools.combinations(range(len(vals)), k):
            if abs(sum(vals[i] for i in c) - a) <= tolerancia:
                fecham.append(list(c))
                if len(fecham) > 1:
                    return fecham[0], True
    return (fecham[0] if fecham else []), False


def juntar(itens, marcados=None):
    """Os itens marcados viram UMA devolução. {produto, sku, quantidade, valor}.

    `itens` é [{produto, sku, quantidade, valor, data, plataforma}].
    `marcados` são os índices; None marca todos.

    É a regra do dono em código: uma devolução só, com os valores somados.
    """
    itens = list(itens or [])
    idx = list(range(len(itens))) if marcados is None else list(marcados)
    esc = [itens[i] for i in idx if 0 <= i < len(itens)]
    if not esc:
        return {"produto": "", "sku": "", "quantidade": 0, "valor": 0.0,
                "data_venda": "", "conta": ""}
    return {
        "produto": " + ".join(str(i.get("produto", "")).strip()
                              for i in esc if str(i.get("produto", "")).strip()),
        "sku": " + ".join(str(i.get("sku", "")).strip()
                          for i in esc if str(i.get("sku", "")).strip()),
        "quantidade": int(sum(num(i.get("quantidade"), 1) for i in esc)),
        "valor": round(sum(num(i.get("valor")) for i in esc), 2),
        "data_venda": texto_data(esc[0].get("data")),
        "conta": conta_da_plataforma(esc[0].get("plataforma")),
    }


# ── Regras do cadastro ──────────────────────────────────────────────────────

def faltando(reg):
    """Os obrigatórios em branco, com o nome que aparece na tela.

    Só estes seis. Qualquer outro campo vazio passa — travar por um campo que
    "nem sempre temos" devolve a pessoa para a planilha.
    """
    fora = []
    for c in OBRIGATORIOS:
        if not str((reg or {}).get(c, "") or "").strip():
            fora.append(ROTULOS[c])
    return fora


def culpa_nossa(reg):
    """O frete responde. Regra do dono, não dedução minha.

    Sem frete: o motivo não foi culpa nossa (arrependimento, falha da
    transportadora). Com frete: foi (produto errado, cor errada, defeito).
    """
    return num((reg or {}).get("frete")) > 0


def esta_aberta(reg):
    """Em aberto até alguém marcar resolvido. A situação não fecha sozinha.

    Uma linha entra em aberto por ser RECORRENDO ou por alguém ter escrito
    algo no Status — os dois são "isto ainda me deve resposta". E sai só pelo
    ✅, nunca pela virada do mês.
    """
    r = reg or {}
    if str(r.get("resolvido", "")).strip().upper() in ("TRUE", "SIM", "1", "X"):
        return False
    if str(r.get("situacao", "")).strip().upper() in ABERTAS:
        return True
    return bool(str(r.get("status", "") or "").strip())


def identidade(reg):
    """A chave estável da devolução. Reimportar não pode duplicar linha."""
    crua = "|".join(str((reg or {}).get(c, "")) for c in
                    ("data_solic", "pedido", "produto", "valor"))
    return "d" + hashlib.sha1(crua.encode("utf-8")).hexdigest()[:14]


def normalizar(reg):
    """A linha pronta para gravar: datas em AAAA-MM-DD, números como número."""
    r = dict(reg or {})
    for c in ("data_venda", "data_solic", "conferencia"):
        r[c] = texto_data(r.get(c))
    r["valor"] = round(num(r.get("valor")), 2)
    r["frete"] = round(num(r.get("frete")), 2)
    r["quantidade"] = int(num(r.get("quantidade"), 0))
    for c in ("pedido", "sku", "produto", "conta", "envios", "usuario",
              "nome", "motivo", "situacao", "nf_devolucao", "status"):
        r[c] = str(r.get(c, "") or "").strip()
    r["resolvido"] = "TRUE" if str(r.get("resolvido", "")).strip().upper() in (
        "TRUE", "SIM", "1", "X") else ""
    r["id"] = str(r.get("id", "") or "").strip() or identidade(r)
    return {c: r.get(c, "") for c in COLUNAS}


# ── O que a tela mostra ─────────────────────────────────────────────────────

def do_mes(linhas, mes):
    """As devoluções de um mês (AAAA-MM), pela DATA DA SOLICITAÇÃO."""
    return [l for l in (linhas or []) if mes_de(l.get("data_solic")) == mes]


def meses(linhas):
    """Os meses com devolução, do mais novo para o mais velho."""
    return sorted({mes_de(l.get("data_solic")) for l in (linhas or [])
                   if mes_de(l.get("data_solic"))}, reverse=True)


def resumo(linhas):
    """{n, valor, frete, ticket_medio, culpa_nossa, sem_nf}.

    O tícket médio é (valor + frete) ÷ quantidade de devoluções — a conta que
    ele já fazia na planilha, agora do MÊS e não do ano inteiro.
    """
    ls = list(linhas or [])
    valor = round(sum(num(l.get("valor")) for l in ls), 2)
    frete = round(sum(num(l.get("frete")) for l in ls), 2)
    return {
        "n": len(ls), "valor": valor, "frete": frete,
        "ticket_medio": round((valor + frete) / len(ls), 2) if ls else 0.0,
        "culpa_nossa": sum(1 for l in ls if culpa_nossa(l)),
        "sem_nf": [l for l in ls
                   if not str(l.get("nf_devolucao", "") or "").strip()],
    }


def top_motivos(linhas, quantos=5):
    """[(motivo, n, valor, pct_do_valor)] do maior valor para o menor."""
    ls = list(linhas or [])
    por = {}
    for l in ls:
        m = str(l.get("motivo", "") or "").strip() or "(em branco)"
        d = por.setdefault(m, {"n": 0, "valor": 0.0})
        d["n"] += 1
        d["valor"] = round(d["valor"] + num(l.get("valor")), 2)
    total = sum(d["valor"] for d in por.values()) or 1.0
    ordenado = sorted(por.items(), key=lambda kv: -kv[1]["valor"])
    return [(m, d["n"], d["valor"], round(100.0 * d["valor"] / total, 1))
            for m, d in ordenado[:quantos]]


def pct_do_faturado(devolvido, faturado):
    """devolvido ÷ faturado, em %. None quando não há faturamento.

    SEM somar as devoluções de volta ao denominador. Na BASE DE VENDAS a
    coluna FAT TOTAL **já inclui** a venda devolvida — pedido 260803B7RPDJ0H
    tem FAT TOTAL R$ 29,99 e DEVOLUÇÃO R$ 29,99. Somar de novo contaria a
    mesma venda duas vezes e rebaixaria o percentual, que é justamente o
    número que ele quer vigiar.
    """
    f = num(faturado)
    return round(100.0 * num(devolvido) / f, 2) if f else None


def por_mes_da_venda(linhas):
    """{AAAA-MM: valor} agrupado pela DATA DA VENDA, não pela solicitação.

    A pergunta é "do que vendi neste mês, quanto voltou?" — e a resposta
    pertence ao mês da VENDA. Uma devolução pedida em setembro de uma venda de
    agosto é devolução de agosto. É por isso que a data da venda vem
    preenchida automaticamente.
    """
    fora = {}
    for l in (linhas or []):
        m = mes_de(l.get("data_venda"))
        if m:
            fora[m] = round(fora.get(m, 0.0) + num(l.get("valor")), 2)
    return fora


def em_aberto(linhas):
    return [l for l in (linhas or []) if esta_aberta(l)]


# ── Planilha ────────────────────────────────────────────────────────────────

def _aba():
    import gspread
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        return planilha.worksheet(ABA)
    except gspread.WorksheetNotFound:
        nova = planilha.add_worksheet(title=ABA, rows=4000, cols=len(COLUNAS))
        nova.append_row(COLUNAS, value_input_option="RAW")
        return nova


@st.cache_data(ttl=120)
def carregar():
    """[{...}] da aba. Lista vazia em qualquer falha."""
    try:
        registros = _aba().get_all_records()
    except Exception:
        return []
    return [{c: r.get(c, "") for c in COLUNAS} for r in registros
            if str(r.get("id", "") or "").strip()]


def gravar(novas, usuario=""):
    """Acrescenta o que ainda não existe. (novas, repetidas, erro)."""
    agora = datetime.now(FUSO).strftime("%Y-%m-%d %H:%M")
    try:
        aba = _aba()
        ja = {str(r.get("id", "")).strip()
              for r in aba.get_all_records() if str(r.get("id", "")).strip()}
        linhas, vistos, repetidas = [], set(), 0
        for l in (novas or []):
            r = normalizar(l)
            if r["id"] in ja or r["id"] in vistos:
                repetidas += 1
                continue
            vistos.add(r["id"])
            linhas.append([r.get(c, "") for c in COLUNAS[:-2]]
                          + [agora, str(usuario or "")[:60]])
        if linhas:
            aba.append_rows(linhas, value_input_option="RAW")
    except Exception as e:
        return 0, 0, str(e)[:200]
    carregar.clear()
    return len(linhas), repetidas, ""


def atualizar(id_dev, campos, usuario=""):
    """Altera uma devolução gravada. (ok, mensagem).

    TUDO o que foi preenchido à mão é editável — pedido do dono. Inclusive o
    valor: quando a plataforma reembolsa (RECORRIDO), é ELE quem apaga, porque
    às vezes o reembolso é parcial e nenhuma regra automática acerta isso.
    """
    alvo = str(id_dev or "").strip()
    if not alvo:
        return False, "Sem id não dá para saber qual devolução alterar."
    try:
        aba = _aba()
        registros = aba.get_all_records()
        achados = [i for i, r in enumerate(registros)
                   if str(r.get("id", "")).strip() == alvo]
        if not achados:
            return False, "Não achei esta devolução na aba."
        i = achados[-1]
        atual = dict(registros[i])
        atual.update({k: v for k, v in (campos or {}).items() if k in COLUNAS})
        atual["id"] = alvo          # a identidade não muda quando se corrige
        atual["atualizado_em"] = datetime.now(FUSO).strftime("%Y-%m-%d %H:%M")
        atual["atualizado_por"] = str(usuario or "")[:60]
        fim = chr(ord("A") + len(COLUNAS) - 1)
        n = i + 2
        aba.update([[atual.get(c, "") for c in COLUNAS]], f"A{n}:{fim}{n}",
                   value_input_option="RAW")
    except Exception as e:
        return False, str(e)[:200]
    carregar.clear()
    return True, "Alterado."


def apagar(ids):
    """Remove linhas pelo id. (quantas, erro)."""
    alvos = {str(i).strip() for i in (ids or []) if str(i).strip()}
    if not alvos:
        return 0, ""
    try:
        aba = _aba()
        registros = aba.get_all_records()
        linhas = [i + 2 for i, r in enumerate(registros)
                  if str(r.get("id", "")).strip() in alvos]
        for n in sorted(linhas, reverse=True):
            aba.delete_rows(n)
    except Exception as e:
        return 0, str(e)[:200]
    carregar.clear()
    return len(linhas), ""


# ── Conferência ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    class _Falsa:
        def __init__(self):
            self.linhas = []

        def get_all_records(self):
            return [dict(zip(COLUNAS, l)) for l in self.linhas]

        def append_rows(self, ls, **k):
            self.linhas.extend(ls)

        def update(self, v, range_name=None, **k):
            n = int("".join(c for c in str(range_name).split(":")[0]
                            if c.isdigit())) - 2
            self.linhas[n] = list(v[0])

        def delete_rows(self, n, **k):
            self.linhas.pop(n - 2)

    _falsa = _Falsa()
    globals()["_aba"] = lambda: _falsa
    globals()["carregar"] = type("C", (), {
        "clear": staticmethod(lambda: None)})()

    falhas = []

    def ok(nome, cond):
        if not cond:
            falhas.append(nome)
        print(("  ok  " if cond else "FALHOU") + "  " + nome)

    # 1. Datas — a planilha devolve datetime, o formulário devolve date, e o
    #    dono digita dd/mm/aaaa. Os três precisam virar a mesma coisa.
    ok("datetime vira AAAA-MM-DD",
       texto_data(datetime(2026, 8, 14)) == "2026-08-14")
    ok("date também", texto_data(date(2026, 8, 14)) == "2026-08-14")
    ok("dd/mm/aaaa também", texto_data("14/08/2026") == "2026-08-14")
    ok("dia 3 não vira 03/04", texto_data("3/4/2026") == "2026-04-03")
    ok("e volta em BR para ler", data_br("2026-08-14") == "14/08/2026")
    ok("vazio não inventa data", texto_data("") == "" and data_br("") == "—")
    ok("o mês sai da data", mes_de(datetime(2026, 8, 14)) == "2026-08")

    # 2. A conta, traduzida da plataforma.
    ok("MercadoLivre2 é ML2", conta_da_plataforma("MercadoLivre2") == "ML2")
    ok("Shopee1 é SHOP01", conta_da_plataforma("Shopee1") == "SHOP01")
    ok("Shein2 é SHEIN02", conta_da_plataforma("Shein2") == "SHEIN02")
    # O TikTok existe nas devoluções e NÃO existe na BASE DE VENDAS. Voltar
    # vazio esconderia a conta; voltar o nome deixa o buraco visível.
    ok("plataforma desconhecida volta visível, não vazia",
       conta_da_plataforma("TikTok1") == "TIKTOK1")

    # 3. O valor diz o que voltou — os casos REAIS do histórico dele.
    ok("'URSINHOS' R$ 66,34: voltaram só os ursos",
       combinacao_que_fecha([66.34, 78.99], 66.34) == ([0], False))
    ok("'MEIÃO' R$ 39,98: voltaram os dois meiões",
       combinacao_que_fecha([19.99, 19.99], 39.98) == ([0, 1], False))
    ok("'2 XADREZ' R$ 119,98: os dois",
       combinacao_que_fecha([59.99, 59.99], 119.98) == ([0, 1], False))
    # O sétimo caso: dois itens de mesmo valor, e o devolvido é o de um deles.
    # Duas somas fecham, e escolher seria inventar o que voltou ao estoque.
    _idx, _amb = combinacao_que_fecha([956.36, 956.36], 956.36)
    ok("duas combinações que fecham = ambíguo, e o Studio não escolhe", _amb)
    ok("valor que não fecha com nada devolve vazio",
       combinacao_que_fecha([10.0, 20.0], 77.0) == ([], False))
    ok("pedido sem item não quebra", combinacao_que_fecha([], 10.0) == ([], False))
    ok("centavo de diferença ainda fecha",
       combinacao_que_fecha([66.34], 66.345)[0] == [0])

    # 4. Juntar — uma devolução só, valores somados. A regra do dono.
    ITENS = [{"produto": "Dupla De Ursos", "sku": "MS-2160", "quantidade": 1,
              "valor": 66.34, "data": datetime(2026, 3, 11),
              "plataforma": "MercadoLivre1"},
             {"produto": "Kit 3 Mini Bailarinas", "sku": "MS-3114",
              "quantidade": 1, "valor": 78.99, "data": datetime(2026, 3, 11),
              "plataforma": "MercadoLivre1"}]
    j = juntar(ITENS)
    ok("os dois marcados somam o valor", j["valor"] == 145.33)
    ok("e a quantidade", j["quantidade"] == 2)
    ok("o produto leva os dois nomes",
       j["produto"] == "Dupla De Ursos + Kit 3 Mini Bailarinas")
    ok("o SKU também", j["sku"] == "MS-2160 + MS-3114")
    ok("a data da venda e a conta vêm junto",
       j["data_venda"] == "2026-03-11" and j["conta"] == "ML1")
    j1 = juntar(ITENS, [0])
    ok("desmarcar um refaz tudo",
       j1["valor"] == 66.34 and j1["quantidade"] == 1
       and j1["sku"] == "MS-2160" and j1["produto"] == "Dupla De Ursos")
    ok("nenhum marcado não inventa devolução",
       juntar(ITENS, [])["valor"] == 0.0)

    # 5. Obrigatórios — seis, e só seis.
    CHEIA = {"data_solic": "2026-08-14", "envios": "ENVIOS",
             "produto": "ÓCULOS", "motivo": "FALHA NA ENTREGA",
             "conferencia": "2026-08-20", "situacao": "OK"}
    ok("com os seis, nada falta", faltando(CHEIA) == [])
    ok("sem NF, sem usuário, sem nome e sem frete ainda passa",
       faltando(dict(CHEIA, nf_devolucao="", usuario="", nome="",
                     frete="")) == [])
    ok("faltando a conferência, ela é nomeada na tela",
       faltando(dict(CHEIA, conferencia="")) == ["Data de conferência"])
    ok("faltando três, os três aparecem",
       len(faltando(dict(CHEIA, envios="", motivo="", situacao=""))) == 3)
    ok("todo obrigatório tem rótulo", all(c in ROTULOS for c in OBRIGATORIOS))

    # 6. O frete diz de quem foi a culpa. Regra dele.
    ok("sem frete, não foi culpa nossa", not culpa_nossa(dict(CHEIA, frete=0)))
    ok("com frete, foi", culpa_nossa(dict(CHEIA, frete=16.39)))
    ok("frete em branco não é culpa", not culpa_nossa(dict(CHEIA, frete="")))

    # 7. Em aberto — sai pelo ✅, nunca pela virada do mês.
    ok("RECORRENDO fica em aberto",
       esta_aberta(dict(CHEIA, situacao="RECORRENDO")))
    ok("OK com observação no Status também fica",
       esta_aberta(dict(CHEIA, status="Recorrer semana que vem")))
    ok("OK limpo não fica", not esta_aberta(CHEIA))
    ok("marcado como resolvido sai, mesmo RECORRENDO",
       not esta_aberta(dict(CHEIA, situacao="RECORRENDO", resolvido="TRUE")))
    # RECORRIDO é reembolso JÁ recebido: o caso acabou. Mas o valor não se
    # zera sozinho — quem apaga é ele, porque o reembolso às vezes é parcial.
    ok("RECORRIDO não é caso em aberto",
       not esta_aberta(dict(CHEIA, situacao="RECORRIDO")))
    ok("e o Studio não mexe no valor por causa da situação",
       normalizar(dict(CHEIA, situacao="RECORRIDO",
                       valor=199.99))["valor"] == 199.99)

    # 8. Identidade — reimportar o histórico não pode duplicar.
    a = dict(CHEIA, pedido="2000011", valor=37.99)
    ok("a mesma devolução dá a mesma chave",
       identidade(a) == identidade(dict(a)))
    ok("outro valor é outra devolução",
       identidade(a) != identidade(dict(a, valor=38.0)))
    ok("outro pedido também",
       identidade(a) != identidade(dict(a, pedido="2000012")))

    # 9. Os números da tela.
    MES = [dict(CHEIA, data_solic="2026-08-02", data_venda="2026-07-20",
                valor=29.99, frete=0, motivo="SE ARREPENDEU DA COMPRA",
                nf_devolucao="25601"),
           dict(CHEIA, data_solic="2026-08-05", data_venda="2026-08-01",
                valor=39.99, frete=16.39, motivo="PRODUTO ERRADO",
                nf_devolucao="25602"),
           dict(CHEIA, data_solic="2026-08-14", data_venda="2026-08-03",
                valor=59.99, frete=0, motivo="SE ARREPENDEU DA COMPRA",
                nf_devolucao=""),
           dict(CHEIA, data_solic="2026-07-30", data_venda="2026-07-10",
                valor=99.00, frete=0, motivo="FALHA NA ENTREGA")]
    ago = do_mes(MES, "2026-08")
    ok("o mês separa pela data da SOLICITAÇÃO", len(ago) == 3)
    ok("e os meses vêm do mais novo para o mais velho",
       meses(MES) == ["2026-08", "2026-07"])
    r = resumo(ago)
    ok("soma o valor do mês", r["valor"] == 129.97)
    ok("soma o frete", r["frete"] == 16.39)
    ok("tícket médio é (valor + frete) ÷ devoluções",
       r["ticket_medio"] == round((129.97 + 16.39) / 3, 2))
    ok("culpa nossa é 1 de 3", r["culpa_nossa"] == 1)
    ok("e a sem NF é apontada — é imposto pago à toa",
       len(r["sem_nf"]) == 1 and r["sem_nf"][0]["valor"] == 59.99)

    t = top_motivos(ago)
    ok("o maior motivo em VALOR vem primeiro",
       t[0][0] == "SE ARREPENDEU DA COMPRA" and t[0][1] == 2
       and t[0][2] == 89.98)
    ok("e o percentual é sobre o valor, não sobre a contagem",
       abs(t[0][3] - 69.2) < 0.2)
    ok("top 5 corta em 5",
       len(top_motivos([dict(CHEIA, motivo=f"M{i}", valor=i)
                        for i in range(1, 9)])) == 5)

    # 10. A porcentagem sobre o faturado — a conta que ele pediu.
    #
    # SEM somar as devoluções de volta: na BASE DE VENDAS o FAT TOTAL já
    # contém a venda devolvida. Somar de novo rebaixaria o percentual, que é
    # exatamente o número que ele quer vigiar.
    ok("4.429,10 sobre 269.159,94 é 1,65%",
       pct_do_faturado(4429.10, 269159.94) == 1.65)
    ok("o ano: 46.989,61 sobre 1.852.806,88 é 2,54%",
       pct_do_faturado(46989.61, 1852806.88) == 2.54)
    ok("sem faturamento não inventa percentual",
       pct_do_faturado(100.0, 0) is None)

    pv = por_mes_da_venda(MES)
    ok("a devolução pertence ao mês da VENDA, não ao do pedido",
       pv["2026-07"] == round(29.99 + 99.00, 2) and pv["2026-08"] == 99.98)

    # 11. Gravar, editar, apagar.
    n, rep, erro = gravar(MES, "leo")
    ok("gravou as quatro", (n, rep, erro) == (4, 0, ""))
    ok("reimportar não duplica", gravar(MES, "leo")[:2] == (0, 4))
    gravadas = [dict(zip(COLUNAS, l)) for l in _falsa.linhas]
    ok("toda linha nasceu com id", all(g["id"] for g in gravadas))
    ok("e as datas gravadas ordenam sozinhas",
       all(len(g["data_solic"]) == 10 and g["data_solic"][4] == "-"
           for g in gravadas))

    alvo = gravadas[1]["id"]
    ok("dá para corrigir o valor à mão — RECORRIDO parcial",
       atualizar(alvo, {"valor": 20.0, "situacao": "RECORRIDO"}, "leo")[0])
    gravadas = [dict(zip(COLUNAS, l)) for l in _falsa.linhas]
    depois = [g for g in gravadas if g["id"] == alvo][0]
    ok("o valor mudou", num(depois["valor"]) == 20.0)
    ok("e a identidade NÃO mudou junto — senão viraria outra devolução",
       depois["id"] == alvo)
    ok("id que não existe não é alterado em silêncio",
       atualizar("dnaoexiste", {"valor": 1})[0] is False)

    q, erro = apagar([alvo])
    ok("apagou uma", (q, erro) == (1, ""))
    ok("e sobraram três", len(_falsa.linhas) == 3)

    print()
    if falhas:
        print("FALHOU: " + ", ".join(falhas))
        raise SystemExit(1)
    print("Tudo certo.")
