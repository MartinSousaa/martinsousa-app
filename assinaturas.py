"""assinaturas.py — o que se paga todo mês sem ninguém decidir de novo.

POR QUE ELAS GANHARAM MÓDULO PRÓPRIO
------------------------------------
Assinatura não é custo fixo comum e não é gasto variável. Ela tem três
particularidades que, juntas, não cabem em nenhuma das duas grades que já
existem:

    1. cobra sozinha, no cartão, sem ninguém aprovar nada;
    2. muda de valor sem avisar — dólar, reajuste, plano que virou outro;
    3. some sem avisar — cancelada, cartão recusado, conta suspensa.

As três são invisíveis na fatura consolidada: uma linha "MERCADO PAGO
R$ 16.598" não conta que o Canva subiu de 90 para 120. O dono disse o que quer
disso com todas as letras: *"preciso que o sistema monitore os extratos para
caso identifique um custo de assinatura que não bata ou não esteja na planilha
que te passei para me alertar para eu analisar"*.

ELAS SÃO FIXAS, E ISSO DECIDE ONDE ENTRAM NA CONTA
--------------------------------------------------
O Trello custa o mesmo vendendo 100 ou 3.000 pedidos. Então a assinatura é
NUMERADOR do ponto de equilíbrio, junto com aluguel e luz — e precisa sair dos
baldes SERVIÇO do PIX e do cartão que compõem o custo operacional por venda,
senão o mesmo Trello conta duas vezes: uma como fixo, outra diluído em cada
venda. `favorecidos_das_assinaturas()` existe exatamente para essa subtração.

ANUAL NÃO É UM MÊS DE R$ 2.500
-------------------------------
O Envato foi pago de uma vez: US$ 468 em 24/04/2026. Lançar o valor cheio em
abril faria abril parecer um mês ruim e os outros onze, bons — e o ponto de
equilíbrio de abril subiria R$ 8 mil sem que nada tivesse mudado no negócio.
O custo mensal rateia por doze; o CAIXA continua saindo de uma vez, e isso é
assunto da provisão, não do equilíbrio.

O QUE ESTE MÓDULO NÃO DECIDE
----------------------------
Ele não cancela nada e não conserta valor. Ele compara o cadastro com o que
chegou e devolve as diferenças para o dono olhar. A conferência é dele — o
Studio só garante que nada passe despercebido.
"""

import re
import unicodedata
from datetime import timezone, timedelta

FUSO = timezone(timedelta(hours=-3))

COLUNAS = ["item", "valor_mensal", "periodicidade", "favorecido",
           "forma_pagamento", "vigente_desde", "observacao",
           "atualizado_em", "atualizado_por"]

ABA = "assinaturas"

MENSAL, ANUAL = "Mensal", "Anual"
PERIODICIDADES = (MENSAL, ANUAL)

# Quanto o valor pode variar sem virar alerta.
#
# Dois limites, e não um. Uma assinatura em dólar oscila alguns por cento todo
# mês só pelo câmbio: alertar nisso ensinaria o dono a ignorar o alerta, que é
# a única forma de um alerta deixar de funcionar. Já R$ 5,90 da Apple variando
# 10% é ruído de centavo, e não merece nem o percentual.
TOLERANCIA_PCT = 0.10
TOLERANCIA_REAIS = 3.00

# Quantas vezes uma cobrança precisa se repetir para o Studio suspeitar de que
# ela é uma assinatura que ninguém cadastrou. Três meses seguidos: duas seriam
# uma compra parcelada em 2x, e quatro demorariam um trimestre para avisar.
MESES_PARA_SUSPEITAR = 3

# As finalidades onde uma assinatura pode se esconder. MERCADORIA não entra:
# fornecedor que recebe todo mês é fornecedor, não assinatura.
FINALIDADES_DE_ASSINATURA = ("SERVIÇO", "SERVIÇOS", "OUTROS", "SITE MS")

# O que o dono consolidou olhando as faturas, em 18/09/2026 (cartão "Maperar as
# assinaturas mensais"). Entra como SUGESTÃO da tela vazia e não é gravado
# sozinho: dado que ninguém digitou é dado em que ninguém confia.
#
# Bling e Contabilidade NÃO estão aqui de propósito — eles já são itens do
# Custo fixo (`custo_fixo.py`), e repeti-los criaria a segunda resposta para a
# mesma pergunta.
SUGESTOES = [
    ("Trello", 68.13, MENSAL, "TRELLO"),
    ("ChatGPT", 217.00, MENSAL, "OPENAI"),
    ("Tray", 118.00, MENSAL, "TRAY"),
    ("Claude", 500.00, MENSAL, "CLAUDE"),
    ("Canva PRO", 90.00, MENSAL, "CANVA"),
    ("Microsoft", 167.00, MENSAL, "MICROSOFT"),
    ("ControlID", 102.00, MENSAL, "CONTROLID"),
    ("Hostgator", 50.59, MENSAL, "HOSTGATOR"),
    ("Railway", 80.00, MENSAL, "RAILWAY"),
    ("Anthropic (API)", 70.00, MENSAL, "ANTHROPIC"),
    ("KlingAI", 51.13, MENSAL, "KLING"),
    ("API Gemini", 500.00, MENSAL, "GOOGLE"),
    ("Serasa", 120.00, MENSAL, "SERASA"),
    ("Apple", 5.90, MENSAL, "APPLE"),
    ("Envato", 2527.20, ANUAL, "ENVATO"),
]


def _num(v, padrao=0.0):
    """Número a partir do que a planilha devolver. '1.234,56' inclusive."""
    if v is None or v == "":
        return padrao
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace("R$", "").replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return padrao


def _chave(texto):
    """Texto comparável: sem acento, sem pontuação, maiúsculo.

    O extrato escreve "MERCADO PAGO *CANVA", a fatura escreve "Canva.com" e o
    cadastro diz "Canva PRO". Comparar como vem não casa nenhum dos três.
    """
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]+", " ", t.upper()).strip()


def custo_mensal(linha):
    """Quanto esta assinatura pesa em UM mês. Anual entra rateada por 12."""
    v = _num(linha.get("valor_mensal"))
    if str(linha.get("periodicidade", "")).strip().lower().startswith("anu"):
        return round(v / 12.0, 2)
    return round(v, 2)


def total_mensal(linhas):
    """O que todas juntas pesam no mês — o número que vai ao equilíbrio."""
    return round(sum(custo_mensal(l) for l in (linhas or [])), 2)


def favorecidos_das_assinaturas(linhas):
    """As chaves de busca, para o custo operacional NÃO contá-las de novo.

    Devolve as chaves já normalizadas: quem subtrai compara com `_chave` do
    lançamento, e não com o texto cru que cada banco escreve do seu jeito.
    """
    fora = set()
    for l in (linhas or []):
        for campo in ("favorecido", "item"):
            k = _chave(l.get(campo))
            if k:
                fora.add(k)
    return fora


def _casa(lancamento, linha):
    """Este lançamento é esta assinatura?

    Casa pelo FAVORECIDO cadastrado dentro da descrição ou do favorecido do
    lançamento — e não pelo valor. Casar por valor seria circular: a pergunta
    que se está fazendo é justamente se o valor mudou.
    """
    alvo = _chave(linha.get("favorecido")) or _chave(linha.get("item"))
    if not alvo:
        return False
    texto = _chave(lancamento.get("descricao")) + " " + \
        _chave(lancamento.get("favorecido"))
    # PALAVRA INTEIRA, e nao pedaco de palavra.
    #
    # `"CANVA" in texto` casava com "CANVAS ARTESANAL LTDA" — um fornecedor de
    # tecido viraria a assinatura do Canva, e a divergencia de valor apareceria
    # todo mes sem que nada estivesse errado. Nome curto de servico e prefixo
    # de muita coisa: KLING, APPLE, TRAY.
    return re.search(r"(?<![A-Z0-9])" + re.escape(alvo) + r"(?![A-Z0-9])",
                     texto) is not None


def _valor_de_saida(lancamento):
    """O valor da saída, sempre positivo. Entrada devolve 0.

    O extrato grava saída como negativo; a fatura do cartão, como positivo.
    Comparar sem normalizar faria a mesma assinatura bater num lugar e falhar
    no outro.
    """
    v = _num(lancamento.get("valor"))
    tipo = str(lancamento.get("tipo", "")).strip().lower()
    if tipo.startswith("entrada"):
        return 0.0
    return abs(v)


def _fora_da_tolerancia(cobrado, cadastrado):
    """A diferença merece alerta? (bool, diferença)"""
    dif = round(cobrado - cadastrado, 2)
    if abs(dif) <= TOLERANCIA_REAIS:
        return False, dif
    if cadastrado > 0 and abs(dif) / cadastrado <= TOLERANCIA_PCT:
        return False, dif
    return True, dif


def conferir(cadastro, lancamentos_do_mes):
    """O que não bate entre o cadastro e o que chegou no mês.

    Devolve {"divergentes", "sumidas", "nao_cadastradas"}. Três listas e não
    uma: cada uma pede uma ação diferente do dono — conferir o valor, conferir
    se cancelou, decidir se cadastra.

    A assinatura ANUAL não entra em "sumidas": ela cobra uma vez por ano, e
    acusá-la de sumida em onze meses de doze seria ensinar a ignorar o aviso.
    """
    cad = [l for l in (cadastro or []) if str(l.get("item", "")).strip()]
    lancs = list(lancamentos_do_mes or [])

    divergentes, sumidas, usados = [], [], set()
    for linha in cad:
        achados = [(i, l) for i, l in enumerate(lancs) if _casa(l, linha)]
        if not achados:
            if not str(linha.get("periodicidade", "")).lower().startswith("anu"):
                sumidas.append({"item": linha.get("item", ""),
                                "esperado": custo_mensal(linha)})
            continue
        # Soma os lançamentos da mesma assinatura: a OpenAI cobra três
        # assinaturas em três linhas, e comparar uma linha com o total
        # cadastrado acusaria divergência todo mês.
        cobrado = round(sum(_valor_de_saida(l) for _, l in achados), 2)
        for i, _ in achados:
            usados.add(i)
        esperado = custo_mensal(linha)
        alerta, dif = _fora_da_tolerancia(cobrado, esperado)
        if alerta:
            divergentes.append({"item": linha.get("item", ""),
                                "esperado": esperado, "cobrado": cobrado,
                                "diferenca": dif,
                                "linhas": len(achados)})

    # O que sobrou e parece assinatura: cobrança recorrente que ninguém
    # cadastrou. Aqui só se marca o candidato do mês; quem decide que ele se
    # repete é `recorrentes_nao_cadastradas`, que olha vários meses.
    nao_cadastradas = []
    for i, l in enumerate(lancs):
        if i in usados:
            continue
        if _chave(l.get("finalidade")) not in \
                {_chave(f) for f in FINALIDADES_DE_ASSINATURA}:
            continue
        v = _valor_de_saida(l)
        if v <= 0:
            continue
        nao_cadastradas.append({"favorecido": l.get("favorecido")
                                or l.get("descricao", ""),
                                "valor": round(v, 2),
                                "data": l.get("data", "")})
    return {"divergentes": divergentes, "sumidas": sumidas,
            "nao_cadastradas": nao_cadastradas}


def recorrentes_nao_cadastradas(cadastro, por_mes, minimo=MESES_PARA_SUSPEITAR):
    """Cobranças que se repetem mês a mês e não estão no cadastro.

    `por_mes` é {(ano, mês): [lançamentos]}. Uma compra avulsa aparece uma vez
    e não vira alerta; o que aparece em três meses diferentes com o mesmo
    favorecido é assinatura até prova em contrário.

    Devolve [{"favorecido", "meses", "media", "valores"}], do mais caro para o
    mais barato — a ordem em que vale a pena olhar.
    """
    vistos = {}
    for chave_mes in sorted(por_mes or {}):
        achados = conferir(cadastro, por_mes[chave_mes])["nao_cadastradas"]
        # Um favorecido que cobra duas vezes no MESMO mês conta como um mês só:
        # senão duas cobranças em janeiro já bateriam o mínimo de três.
        por_favorecido = {}
        for a in achados:
            k = _chave(a["favorecido"])
            if not k:
                continue
            por_favorecido[k] = por_favorecido.get(k, 0.0) + a["valor"]
        for k, v in por_favorecido.items():
            d = vistos.setdefault(k, {"favorecido": k, "meses": 0,
                                      "valores": []})
            d["meses"] += 1
            d["valores"].append(round(v, 2))
    fora = [d for d in vistos.values() if d["meses"] >= int(minimo)]
    for d in fora:
        d["media"] = round(sum(d["valores"]) / len(d["valores"]), 2)
    return sorted(fora, key=lambda d: -d["media"])


def alertas(cadastro, por_mes, ano, mes):
    """As frases prontas para o dono — no Studio e, depois, no WhatsApp.

    Uma função só monta o texto porque a mesma frase vai para dois lugares. Em
    dois lugares, elas passariam a discordar: a questão é só quando.
    """
    do_mes = conferir(cadastro, (por_mes or {}).get((ano, mes), []))
    fora = []
    for d in do_mes["divergentes"]:
        sinal = "subiu" if d["diferenca"] > 0 else "caiu"
        fora.append(f"💸 {d['item']} {sinal} R$ {abs(d['diferenca']):.2f} — "
                    f"cadastrado R$ {d['esperado']:.2f}, cobrado "
                    f"R$ {d['cobrado']:.2f}.")
    for d in do_mes["sumidas"]:
        fora.append(f"❓ {d['item']} não apareceu neste mês — cancelada, ou o "
                    f"cartão recusou? Esperado R$ {d['esperado']:.2f}.")
    for d in recorrentes_nao_cadastradas(cadastro, por_mes):
        fora.append(f"🆕 {d['favorecido']} cobra há {d['meses']} meses "
                    f"(média R$ {d['media']:.2f}) e não está no cadastro.")
    return fora


# ── Conferência ──────────────────────────────────────────────────────────────
# `python3 assinaturas.py`. Os casos moram aqui porque este repositório não tem
# suíte: teste que não viaja junto do código é teste que ninguém roda.
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    CAD = [{"item": i, "valor_mensal": v, "periodicidade": p, "favorecido": f}
           for i, v, p, f in SUGESTOES]

    def lanc(desc, valor, fin="SERVIÇO", data="2026-09-10", fav=""):
        return {"descricao": desc, "favorecido": fav, "valor": valor,
                "tipo": "saida", "finalidade": fin, "data": data}

    # ── o custo mensal ───────────────────────────────────────────────────
    ok("mensal entra pelo valor cheio",
       custo_mensal({"valor_mensal": 68.13, "periodicidade": MENSAL}) == 68.13)
    ok("anual entra rateado por doze",
       custo_mensal({"valor_mensal": 2527.20, "periodicidade": ANUAL}) == 210.60)
    # 14 mensais somam 2.139,75; o Envato rateado soma 210,60.
    ok("o total do cadastro do dono bate com a conta da mão",
       abs(total_mensal(CAD) - 2350.35) < 0.01)

    # ── casar texto que cada banco escreve do seu jeito ──────────────────
    ok("casa com prefixo de adquirente",
       _casa(lanc("MERCADO PAGO *CANVA", -90.0), CAD[4]))
    ok("casa ignorando acento e pontuacao",
       _casa(lanc("Canva.com Assinatura", -90.0), CAD[4]))
    ok("nao casa com quem so parece",
       not _casa(lanc("CANVAS ARTESANAL LTDA", -90.0), CAD[4]))
    ok("nem com o nome colado em outro",
       not _casa(lanc("TRAYCON INDUSTRIA", -118.0), CAD[2]))
    ok("mas casa quando e palavra inteira no meio da frase",
       _casa(lanc("PAG *TRAY TECNOLOGIA", -118.0), CAD[2]))

    # ── divergencia de valor ─────────────────────────────────────────────
    r = conferir(CAD, [lanc("CANVA PRO", -120.0)])
    ok("valor acima do cadastrado vira divergencia",
       len(r["divergentes"]) == 1 and r["divergentes"][0]["diferenca"] == 30.0)
    r = conferir(CAD, [lanc("CANVA PRO", -92.0)])
    ok("variacao pequena nao vira alerta", not r["divergentes"])
    # Ruido de centavo no valor pequeno: 10% de R$ 5,90 sao 59 centavos.
    r = conferir(CAD, [lanc("APPLE COM BILL", -6.90)])
    ok("R$ 1 na Apple nao vira alerta", not r["divergentes"])
    r = conferir(CAD, [lanc("APPLE COM BILL", -59.00)])
    ok("mas dez vezes o valor vira", len(r["divergentes"]) == 1)

    # ── a fatura do cartao grava saida como positivo ─────────────────────
    l = lanc("TRELLO.COM", 68.13)
    ok("saida positiva da fatura e lida igual", _valor_de_saida(l) == 68.13)
    ok("entrada nao conta", _valor_de_saida({"valor": 500.0,
                                             "tipo": "entrada"}) == 0.0)

    # ── tres cobrancas da mesma assinatura somam ─────────────────────────
    r = conferir(CAD, [lanc("OPENAI CHATGPT", -72.33),
                       lanc("OPENAI CHATGPT", -72.33),
                       lanc("OPENAI CHATGPT", -72.34)])
    ok("as tres assinaturas do ChatGPT somam e nao divergem",
       not r["divergentes"])

    # ── sumidas ──────────────────────────────────────────────────────────
    r = conferir(CAD, [lanc("TRELLO.COM", -68.13)])
    ok("quem nao apareceu entra em sumidas",
       any(d["item"] == "Canva PRO" for d in r["sumidas"]))
    ok("a anual NAO entra em sumidas",
       not any(d["item"] == "Envato" for d in r["sumidas"]))

    # ── nao cadastradas: so o que se repete ──────────────────────────────
    POR_MES = {
        (2026, 7): [lanc("FIGMA INC", -180.0, data="2026-07-09"),
                    lanc("COMPRA AVULSA XPTO", -900.0, data="2026-07-11")],
        (2026, 8): [lanc("FIGMA INC", -180.0, data="2026-08-09")],
        (2026, 9): [lanc("FIGMA INC", -190.0, data="2026-09-09")],
    }
    rec = recorrentes_nao_cadastradas(CAD, POR_MES)
    ok("tres meses seguidos viram suspeita",
       len(rec) == 1 and rec[0]["meses"] == 3)
    ok("e a media sai dos tres valores", abs(rec[0]["media"] - 183.33) < 0.01)
    ok("compra avulsa de um mes so nao vira suspeita",
       not any("XPTO" in d["favorecido"] for d in rec))

    # Duas cobrancas no MESMO mes nao sao tres meses.
    DOIS = {(2026, 7): [lanc("FIGMA INC", -180.0), lanc("FIGMA INC", -180.0),
                        lanc("FIGMA INC", -180.0)]}
    ok("tres cobrancas num mes so nao bastam",
       not recorrentes_nao_cadastradas(CAD, DOIS))

    # Mercadoria recorrente e fornecedor, nao assinatura.
    FORN = {(2026, m): [lanc("FORNECEDOR ABC", -9000.0, fin="MERCADORIA")]
            for m in (7, 8, 9)}
    ok("fornecedor de mercadoria nao vira assinatura",
       not recorrentes_nao_cadastradas(CAD, FORN))

    # ── a subtracao que evita contar duas vezes ──────────────────────────
    fora = favorecidos_das_assinaturas(CAD)
    ok("as chaves saem normalizadas", "TRELLO" in fora and "CANVA" in fora)
    ok("o item tambem vira chave", "CANVA PRO" in fora)

    # ── as frases do alerta ──────────────────────────────────────────────
    A = {(2026, 9): [lanc("CANVA PRO", -120.0)]}
    frases = alertas(CAD, A, 2026, 9)
    ok("a divergencia vira frase", any("Canva" in f and "subiu" in f
                                       for f in frases))
    ok("a sumida tambem", any("não apareceu" in f for f in frases))
    ok("cadastro vazio nao quebra", conferir([], [lanc("X", -1.0)]) is not None)
    ok("mes vazio nao quebra", conferir(CAD, []) is not None)

    print("\nfalhas:", falhas)
    raise SystemExit(falhas)
