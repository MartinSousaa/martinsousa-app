"""fatura_ml.py — a fatura do Mercado Livre, separada pelo que ELE já diz.

O RELATÓRIO RESPONDE SOZINHO O QUE SE FAZIA À MÃO
--------------------------------------------------
O relatório de faturamento traz a coluna **"Descontado da operação"**:

    Sim            -> a tarifa já foi abatida da venda. Nunca sai do bolso.
    Não            -> é isto que vira fatura.
    Não se aplica  -> par de lançamento e cancelamento, fora das duas contas.

Agosto/2026, medido nas planilhas dele (3.192 linhas):

    Sim             R$ 24.480,85   (2.409 linhas)
    Não             R$  3.420,90   (441 linhas)
    Não se aplica   R$    -97,78   (342 linhas)

Somar a planilha inteira como gasto contaria sete vezes o que saiu. Era o que
o total da TELA do ML sugeria (R$ 28.086,54): ele inclui o que foi abatido.

MAS NEM O QUE VIRA FATURA É O QUE ELE PAGA
-------------------------------------------
Quem manda no valor das SAÍDAS é o relatório de PAGAMENTO, não o de
faturamento. Em agosto o cartão Visa foi debitado em R$ 3.200,18 — R$ 220,72
a menos que a fatura. A diferença não é mistério e não precisa de palpite: o
relatório de pagamento lista o NÚMERO DA TARIFA de cada linha paga, e as sete
que faltam são todas tarifas de devolução:

    18,72 + 61,50 + 39,70 + 9,36 + 43,30 + 9,64 + 38,50 = R$ 220,72

É o que o dono descreveu: *"vem MUITA cobrança que se abate e não cobram da
gente"*. Por isso `conciliar()` não devolve um número solto de diferença: ela
devolve as LINHAS que explicam a diferença, uma a uma.

IMPOSTO E MULTA NÃO ENTRAM CALADOS
-----------------------------------
Em agosto veio R$ 69,60 sob o nome "Cobrança do diferencial de alíquota
interestadual (ICMS-DIFAL)" — e foi PAGA (está no detalhe do pagamento
000fawarhe). Lendo a guia da SEFAZ-CE anexada à cobrança:

    código de receita   1023 — ICMS ANTECIPADO   (DIFAL é 1090)
    valor principal     R$ 0,00
    MULTA               R$ 69,60
    contribuinte        COCO BAMBU FRUTOS DO MAR, Fortaleza/CE

Não era DIFAL, não era imposto da venda, e a guia estava em nome de outra
empresa. A linha no relatório também não tem Número da venda e a NF-e está
"Ainda indisponível" — não há como saber de que venda ela veio. Uma linha de
R$ 69,60 no meio de três mil não chama atenção de ninguém.

Por isso toda linha de natureza fiscal sai MARCADA, com o motivo escrito. O
Studio não decide se é devida; ele impede que passe sem alguém olhar.

E CONTESTAÇÃO NÃO PODE MORRER NA FATURA DO MÊS
-----------------------------------------------
O dono tem um caso de venda cancelada, produto devolvido e cobrança fiscal
nunca estornada — aberto até hoje. Cobrança contestada some na fatura
seguinte e ninguém cobra o ML de volta.

Por isso a marcação é PERSISTENTE, na aba `cobrancas_ml`: a linha fica EM
ABERTO até o estorno aparecer ou alguém encerrar o caso à mão. E o estorno
não é procurado por semelhança de valor: o próprio ML aponta o alvo na coluna
**"Tarifa cancelada"**, que carrega o número da tarifa original. Casar por
valor erraria — em agosto há 56 cancelamentos de "Custo por vender" com
valores que se repetem.
"""

import hashlib
import unicodedata
from datetime import datetime, timezone, timedelta

import streamlit as st

FUSO = timezone(timedelta(hours=-3))

# ── Relatório de faturamento ─────────────────────────────────────────────────
# O ML mudou o layout em 2026 e avisa na própria planilha ("Adapte sua
# conciliação"); por isso a coluna é procurada pelo NOME, nunca pela posição.
COL_DESCONTADO = "Descontado da operação"
COL_DETALHE = "Detalhe"
COL_VALOR = "Valor da tarifa"
COL_DATA = "Data da tarifa"
COL_VENDA = "Número da venda"
COL_STATUS = "Status da tarifa"
COL_NUMERO = "Número da tarifa"
COL_CANCELADA = "Tarifa cancelada"
COL_NFE = "N° NF-e"

OBRIGATORIAS = (COL_DETALHE, COL_VALOR, COL_DESCONTADO)

# ── Relatório de pagamento ───────────────────────────────────────────────────
PG_APLICADO = "Parte do pagamento aplicado a tarifas"
PG_NUMERO = "Número da tarifa"
PG_DETALHE = "Detalhe"
PG_PAGAMENTO = "Número do pagamento"
PG_DATA = "Data do pagamento"

RE_ESTORNO = "Número do estorno"
RE_TIPO = "Tipo de pagamento"
RE_MEIO = "Meio de pagamento"
RE_STATUS = "Status"
RE_TOTAL = "Valor total"
RE_DATA = "Data do pagamento/emissão de estorno"

OBRIGATORIAS_PAGAMENTO = (PG_NUMERO, PG_APLICADO)

# ── Natureza fiscal: o que NUNCA passa sem conferência ──────────────────────
# Tributo e multa não são tarifa de plataforma: têm guia, contribuinte e
# fundamento legal próprios, e podem estar errados de um jeito que nenhuma
# tarifa está. O caso de agosto provou.
FISCAIS = ("icms", "difal", "diferencial de aliquota", "antecipado",
           "imposto", "multa", "tributo", "iss", "substituicao tributaria")

# Devolução também sai marcada: é o gatilho do caso em aberto do dono — venda
# cancelada, produto de volta, cobrança fiscal nunca estornada.
DEVOLUCAO = ("devolucao", "cancelamento de venda", "reembolso")

ABA_CASOS = "cobrancas_ml"
COLUNAS_CASO = ["id", "numero", "data", "detalhe", "valor", "venda",
                "natureza", "situacao", "motivo", "estorno_numero",
                "estorno_em", "observacao", "atualizado_em", "atualizado_por"]

EM_ABERTO, ESTORNADO, ACEITA = "EM ABERTO", "ESTORNADO", "ACEITA"
SITUACOES = (EM_ABERTO, ESTORNADO, ACEITA)


def _chave(t):
    t = unicodedata.normalize("NFKD", str(t or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).lower().strip()


def _num(v):
    if v is None or v == "":
        return 0.0
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
        return 0.0


def moeda(v, markdown=False):
    """R$ 1.234,56 — vírgula decimal e ponto de milhar, como no Brasil.

    `markdown=True` escapa o cifrão. O markdown do Streamlit trata `$...$`
    como LaTeX: duas cifras no mesmo parágrafo e tudo entre elas vira fórmula
    matemática. Foi o que aconteceu com o alerta do ICMS-DIFAL, que tem dois
    valores na mesma frase — o aviso mais importante da tela saiu ilegível.
    """
    t = f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace(
        "X", ".")
    return ("R\\$ " if markdown else "R$ ") + t


def id_tarifa(v):
    """O número da tarifa como TEXTO comparável entre os dois relatórios.

    O openpyxl devolve `68069345761.0` (float) no relatório de faturamento e
    `68069345761` no de pagamento. Comparar os dois crus nunca casa — e o
    sintoma seria "nenhuma tarifa foi paga", que é falso e assustador.
    """
    t = str(v if v is not None else "").strip()
    if t.endswith(".0"):
        t = t[:-2]
    return "".join(c for c in t if c.isdigit())


def texto_data(v):
    """Data em AAAA-MM-DD. A planilha devolve datetime; a tela, texto."""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    t = str(v or "").strip()
    return t[:10]


def natureza(detalhe):
    """'fiscal' | 'devolucao' | 'tarifa' — o que esta linha é.

    'fiscal' vem primeiro: uma linha pode dizer "cancelamento da tarifa de
    devolução" e conter as duas palavras. Tributo classificado como devolução
    deixaria de ser conferido, que é o erro caro.
    """
    d = _chave(detalhe)
    if any(f in d for f in FISCAIS):
        return "fiscal"
    if any(x in d for x in DEVOLUCAO):
        return "devolucao"
    return "tarifa"


def cabecalho_valido(colunas, obrigatorias=OBRIGATORIAS):
    """(ok, faltando) — a planilha é a que este módulo sabe ler?

    Ler um layout diferente e devolver números silenciosamente errados é pior
    do que recusar. O ML já mudou o layout uma vez.
    """
    tem = {_chave(c) for c in (colunas or [])}
    faltando = [c for c in obrigatorias if _chave(c) not in tem]
    return (not faltando), faltando


def separar(linhas):
    """As linhas partidas pelo que o próprio ML diz sobre cada uma.

    `linhas` é [{coluna: valor}]. Devolve:
        na_operacao / na_fatura / nao_se_aplica   as três listas
        total_operacao / total_fatura / total_nao_se_aplica
        conferir      as fiscais e devoluções da fatura
        cancelamentos {numero_da_tarifa_original: linha_que_cancelou}
    """
    op, fat, nsa, conferir, cancelamentos = [], [], [], [], {}
    for l in (linhas or []):
        item = {_chave(k): v for k, v in (l or {}).items()}
        descontado = _chave(item.get(_chave(COL_DESCONTADO)))
        detalhe = str(item.get(_chave(COL_DETALHE), "") or "")
        reg = {"detalhe": detalhe,
               "valor": round(_num(item.get(_chave(COL_VALOR))), 2),
               "data": texto_data(item.get(_chave(COL_DATA), "")),
               "venda": id_tarifa(item.get(_chave(COL_VENDA), "")),
               "numero": id_tarifa(item.get(_chave(COL_NUMERO), "")),
               "cancela": id_tarifa(item.get(_chave(COL_CANCELADA), "")),
               "nfe": str(item.get(_chave(COL_NFE), "") or ""),
               "status": str(item.get(_chave(COL_STATUS), "") or ""),
               "natureza": natureza(detalhe)}
        if reg["cancela"]:
            cancelamentos[reg["cancela"]] = reg
        if descontado == "nao":
            fat.append(reg)
            if reg["natureza"] in ("fiscal", "devolucao") and reg["valor"] > 0:
                conferir.append(reg)
        elif descontado == "sim":
            op.append(reg)
        else:
            # "Não se aplica" NÃO é "Não": são pares lançamento/cancelamento.
            # Em ago/2026 eles NÃO se anulam — somam -R$ 97,78 —, então ficam
            # visíveis em vez de sumirem dentro de um `else` calado.
            nsa.append(reg)
    return {
        "na_operacao": op, "na_fatura": fat, "nao_se_aplica": nsa,
        "conferir": conferir, "cancelamentos": cancelamentos,
        "total_operacao": round(sum(r["valor"] for r in op), 2),
        "total_fatura": round(sum(r["valor"] for r in fat), 2),
        "total_nao_se_aplica": round(sum(r["valor"] for r in nsa), 2),
    }


# ── Os grupos com os nomes DELE ─────────────────────────────────────────────
# Vieram da aba `ADS E CROSS` do Controle MS, que ele mantém à mão:
# PUBLICIDADE, ENVIOS FULL, PÁGINA DO ML, IMPOSTOS (ICMS-DIFAL), AFILIADOS.
# Traduzir o texto do ML para o vocabulário dele não é enfeite: é o que
# permite conferir esta tela contra a planilha sem reinterpretar oito nomes.
#
# A ordem importa — o primeiro grupo que casar leva a linha. "Tarifa de
# devolução por envio externo" tem "envio" e tem "devolução"; devolução vem
# antes porque é o que ela é.
GRUPOS = (
    ("Impostos", FISCAIS),
    ("Devoluções", DEVOLUCAO),
    ("ADS", ("campanha de publicidade", "product ads", "publicidade")),
    ("Cross (envios Full)", ("coleta full", "armazenamento full",
                             "estoque antigo no full", "envios full",
                             "servico de coleta", "cross")),
    ("Flex", ("flex",)),
    ("Página da loja", ("minha pagina", "minha página", "pagina do ml")),
    ("Afiliados", ("afiliado",)),
    ("Parcelamento", ("parcelamento",)),
)

NOVO = "❓ Novo — nunca visto"

# A ordem de CASAMENTO (GRUPOS) e a de LEITURA não são a mesma. Imposto e
# devolução precisam casar primeiro porque são os nomes mais específicos; mas
# na tela ele quer o custo devido em cima — é o que ele copia para a planilha
# — e o que precisa de conferência embaixo, onde termina a leitura.
ORDEM_NA_TELA = ("ADS", "Cross (envios Full)", "Flex", "Página da loja",
                 "Afiliados", "Parcelamento", "Devoluções", "Impostos", NOVO)


def grupo_de(detalhe):
    """O nome DELE para esta cobrança, ou `NOVO` se o ML inventou um.

    Cobrança que não casa com nenhum grupo é o pedido em uma palavra: *"caso
    haja custo com imposto ou algo novo, preciso que o Studio sinalize"*.
    Somar o desconhecido calado dentro de "outros" é justamente o que deixou
    R$ 69,60 de multa passar.
    """
    d = _chave(detalhe)
    for nome, pedacos in GRUPOS:
        if any(x in d for x in pedacos):
            return nome
    return NOVO


def por_grupo(linhas):
    """{grupo: {'total', 'n', 'itens': {detalhe: total}}} na ordem de GRUPOS.

    Os grupos com zero também vêm: Flex ausente é informação — ele espera um
    custo de Flex e precisa ver que ELE NÃO ESTÁ AQUI, em vez de procurar uma
    linha que a tela simplesmente não desenhou.
    """
    fora = {nome: {"total": 0.0, "n": 0, "itens": {}}
            for nome in ORDEM_NA_TELA}
    for r in (linhas or []):
        g = fora[grupo_de(r["detalhe"])]
        g["n"] += 1
        g["total"] = round(g["total"] + r["valor"], 2)
        g["itens"][r["detalhe"]] = round(
            g["itens"].get(r["detalhe"], 0.0) + r["valor"], 2)
    return fora


def novidades(linhas):
    """[(detalhe, total)] do que não se encaixou em nenhum grupo conhecido."""
    g = por_grupo(linhas)[NOVO]
    return sorted(g["itens"].items(), key=lambda kv: -abs(kv[1]))


def por_tipo(linhas):
    """{detalhe: total}, do maior para o menor. É o resumo que a fatura mostra."""
    fora = {}
    for r in (linhas or []):
        fora[r["detalhe"]] = round(fora.get(r["detalhe"], 0.0) + r["valor"], 2)
    return dict(sorted(fora.items(), key=lambda kv: -abs(kv[1])))


def ler_pagamentos(resumo, detalhe):
    """O que SAIU do bolso — a aba "Pagamentos e estornos" e o detalhe dela.

    `resumo` traz o pagamento (Visa, R$ 3.200,18 em 04/09/2026) e os estornos
    em processamento. `detalhe` traz uma linha por tarifa paga, com o número
    da tarifa — é ele que permite dizer o que foi pago SEM adivinhar.
    """
    pagos, por_numero, total = [], {}, 0.0
    for l in (detalhe or []):
        item = {_chave(k): v for k, v in (l or {}).items()}
        numero = id_tarifa(item.get(_chave(PG_NUMERO), ""))
        if not numero:
            continue
        reg = {"numero": numero,
               "detalhe": str(item.get(_chave(PG_DETALHE), "") or ""),
               "valor": round(_num(item.get(_chave(PG_APLICADO))), 2),
               "pagamento": str(item.get(_chave(PG_PAGAMENTO), "") or ""),
               "data": texto_data(item.get(_chave(PG_DATA), ""))}
        pagos.append(reg)
        por_numero[numero] = round(por_numero.get(numero, 0.0) + reg["valor"], 2)
        total += reg["valor"]

    pagamentos, estornos = [], []
    for l in (resumo or []):
        item = {_chave(k): v for k, v in (l or {}).items()}
        reg = {"tipo": str(item.get(_chave(RE_TIPO), "") or ""),
               "meio": str(item.get(_chave(RE_MEIO), "") or ""),
               "status": str(item.get(_chave(RE_STATUS), "") or ""),
               "data": texto_data(item.get(_chave(RE_DATA), "")),
               "valor": round(_num(item.get(_chave(RE_TOTAL))), 2)}
        if _chave(reg["tipo"]).startswith("estorno"):
            estornos.append(reg)
        elif reg["valor"]:
            pagamentos.append(reg)
    return {
        "pagos": pagos, "por_numero": por_numero,
        "total_pago": round(total, 2),
        "pagamentos": pagamentos, "estornos": estornos,
        "total_estornos": round(sum(e["valor"] for e in estornos), 2),
    }


def conciliar(sep, pag):
    """Por que a fatura e o pagamento não batem — LINHA A LINHA.

    Devolve (diferenca, nao_cobradas). Diferença solta não serve para nada:
    o dono precisa saber QUAL cobrança não foi cobrada, senão ele confere
    3.192 linhas à mão. Em ago/2026 são sete tarifas de devolução, R$ 220,72.
    """
    pagas = set((pag or {}).get("por_numero", {}))
    nao_cobradas = [r for r in (sep or {}).get("na_fatura", [])
                    if r["numero"] and r["numero"] not in pagas]
    dif = round((sep or {}).get("total_fatura", 0.0)
                - (pag or {}).get("total_pago", 0.0), 2)
    return dif, nao_cobradas


def motivo_da_conferencia(reg):
    """A frase que explica por que ESTA linha precisa de olho humano."""
    if reg["natureza"] == "fiscal":
        m = ("Tributo/multa tem guia própria: confira o código da receita, o "
             "valor principal e o CONTRIBUINTE antes de aceitar. Em ago/2026 "
             "uma cobrança de R\\$ 69,60 chamada de DIFAL era multa de ICMS "
             "Antecipado em nome de outra empresa — e foi paga.")
        if not reg.get("venda"):
            m += " Esta linha não tem Número da venda: não dá para saber de " \
                 "que venda ela veio."
        return m
    return ("Venda devolvida ou cancelada: confira se a cobrança FISCAL dela "
            "também foi estornada. Já houve caso de produto de volta e "
            "tributo não devolvido, aberto até hoje.")


def alertas(sep, pag=None, so_pagas=False):
    """As frases que o dono lê. Uma por cobrança que precisa de conferência.

    Com `pag`, cada frase diz se a cobrança FOI PAGA — é a diferença entre
    "olhe isto quando puder" e "isto já saiu da sua conta".

    `so_pagas` corta o que o ML nem chegou a cobrar. Em ago/2026 isso é sete
    das oito frases, e as sete já aparecem na tabela do que não foi cobrado,
    logo acima na tela. Oito avisos de onde um importa é como se para de ler
    aviso.
    """
    pagas = set((pag or {}).get("por_numero", {}))
    fora = []
    for r in (sep or {}).get("conferir", []):
        if so_pagas and r["numero"] not in pagas:
            continue
        icone = "⚖️" if r["natureza"] == "fiscal" else "↩️"
        onde = ""
        if pag:
            onde = " · **JÁ PAGA**" if r["numero"] in pagas else " · não cobrada"
        venda = f" (venda {r['venda']})" if r["venda"] else ""
        fora.append(f"{icone} **{r['detalhe']}** — "
                    f"{moeda(r['valor'], markdown=True)}"
                    f"{venda}{onde}. {motivo_da_conferencia(r)}")
    return fora


# ── Leitura do arquivo ───────────────────────────────────────────────────────

# Quantas linhas do topo podem ser aviso do ML antes do cabeçalho de verdade.
# No relatório de faturamento ele começa na 8; no de pagamento, na 10. Procurar
# é obrigatório, não zelo: o próprio arquivo avisa "Adapte sua conciliação:
# mudamos o relatório", e uma posição fixa lê a planilha nova toda torta.
LINHAS_DE_AVISO = 30


def linhas_da_planilha(dados, obrigatorias=OBRIGATORIAS):
    """(linhas, aba, erro) — acha o cabeçalho sozinho e devolve [{coluna: valor}].

    Varre as abas do arquivo e usa a PRIMEIRA linha que contenha todas as
    colunas obrigatórias. Não achou: devolve erro dizendo o que faltou, em vez
    de somar números de uma planilha que não é esta.
    """
    import io
    import openpyxl
    try:
        wb = openpyxl.load_workbook(io.BytesIO(dados), read_only=True,
                                    data_only=True)
    except Exception as e:
        return [], "", f"Não consegui abrir o arquivo: {str(e)[:120]}"
    alvo = {_chave(c) for c in obrigatorias}
    for ws in wb.worksheets:
        cabecalho, linha_do_cabecalho = None, 0
        for i, linha in enumerate(ws.iter_rows(max_row=LINHAS_DE_AVISO,
                                               values_only=True)):
            nomes = [str(c or "") for c in linha]
            if alvo.issubset({_chave(c) for c in nomes}):
                cabecalho, linha_do_cabecalho = nomes, i + 1
                break
        if not cabecalho:
            continue
        fora = []
        for linha in ws.iter_rows(min_row=linha_do_cabecalho + 1,
                                  values_only=True):
            if not any(c is not None and c != "" for c in linha):
                continue
            fora.append(dict(zip(cabecalho, linha)))
        return fora, ws.title, ""
    faltando = ", ".join(obrigatorias)
    return [], "", ("Não achei nenhuma aba com as colunas necessárias "
                    f"({faltando}). Confira se é o relatório certo do ML.")


def ler_arquivos(arquivos):
    """Os dois relatórios de uma vez. (sep, pag, avisos).

    `arquivos` é [(nome, bytes)]. Cada arquivo é reconhecido pelo CONTEÚDO —
    quais colunas ele tem —, nunca pelo nome: o dono renomeia arquivo, e um
    `if "Faturamento" in nome` quebraria calado.
    """
    sep, pag, avisos = None, None, []
    resumo_pg, detalhe_pg = None, None
    for nome, dados in (arquivos or []):
        linhas, aba, erro = linhas_da_planilha(dados, OBRIGATORIAS)
        if linhas:
            sep = separar(linhas)
            avisos.append(f"✅ **{nome}** · faturamento, aba *{aba}*, "
                          f"{len(linhas)} linhas.")
            continue
        # O relatório de tarifas Full não acrescenta nada à conta: coleta,
        # armazenamento e estoque antigo já estão no de faturamento (em
        # ago/2026, R$ 268,78 nos dois). Ele detalha por SKU. Dizer "não
        # precisa" evita que o dono fique procurando o que deu errado.
        if linhas_da_planilha(dados, ("N\u00ba da tarifa estornada",))[0]:
            avisos.append(f"ℹ️ **{nome}** — é o detalhe Full por SKU. Os "
                          "valores dele já estão no relatório de "
                          "faturamento; não precisa subir.")
            continue
        det, aba, _ = linhas_da_planilha(dados, OBRIGATORIAS_PAGAMENTO)
        if det:
            detalhe_pg = det
            res, _, _ = linhas_da_planilha(dados, (RE_TIPO, RE_TOTAL))
            resumo_pg = res or []
            avisos.append(f"✅ **{nome}** · pagamento, aba *{aba}*, "
                          f"{len(det)} tarifas pagas.")
            continue
        avisos.append(f"⚠️ **{nome}** — {erro}")
    if detalhe_pg is not None:
        pag = ler_pagamentos(resumo_pg, detalhe_pg)
    return sep, pag, avisos


# ── Casos em aberto: a marcação que sobrevive ao mês ─────────────────────────

def identidade(reg):
    """A chave estável da cobrança, para não abrir o mesmo caso duas vezes.

    O número da tarifa manda quando existe — ele é do ML e não muda. Sem ele,
    o hash de data+detalhe+valor+venda; reimportar a mesma planilha tem que
    reencontrar o caso, não criar outro.
    """
    n = id_tarifa(reg.get("numero", ""))
    if n:
        return f"t{n}"
    crua = "|".join(str(reg.get(c, "")) for c in
                    ("data", "detalhe", "valor", "venda"))
    return "h" + hashlib.sha1(crua.encode("utf-8")).hexdigest()[:14]


def caso_de(reg, pago=None):
    """A linha de conferência virando caso gravável."""
    obs = ""
    if pago is True:
        obs = "Cobrança já paga."
    elif pago is False:
        obs = "Constava na fatura e não foi cobrada."
    return {"id": identidade(reg), "numero": reg.get("numero", ""),
            "data": reg.get("data", ""), "detalhe": reg.get("detalhe", ""),
            "valor": reg.get("valor", 0.0), "venda": reg.get("venda", ""),
            "natureza": reg.get("natureza", ""), "situacao": EM_ABERTO,
            "motivo": motivo_da_conferencia(reg), "estorno_numero": "",
            "estorno_em": "", "observacao": obs}


def casos_a_abrir(sep, pag=None):
    """As cobranças que viram caso PERSISTENTE — e só elas.

    Abrir caso para tudo o que se confere seria trocar um incômodo por outro:
    em ago/2026 sete das oito linhas a conferir são tarifas de devolução que o
    ML nem chegou a cobrar. Cobrar o dono de conferir dinheiro que não saiu é
    gastar o tempo dele à toa.

    Com `pag`, vira caso o que FOI PAGO. Sem `pag` — planilha de pagamento não
    anexada — vira caso tudo o que se confere, porque aí não dá para saber o
    que saiu, e deixar passar é o erro caro.
    """
    conferir = (sep or {}).get("conferir", [])
    if not pag:
        return [caso_de(r) for r in conferir]
    pagas = set(pag.get("por_numero", {}))
    return [caso_de(r, pago=True) for r in conferir if r["numero"] in pagas]


def fiscais_repetidas(sep, casos=None):
    """Cobranças fiscais de MESMO nome e MESMO valor em datas diferentes.

    Nasceu de um documento, não de uma suposição. Na conta Little Glass o ML
    lançou "Cobrança do diferencial de alíquota interestadual (ICMS-DIFAL)"
    de R$ 69,60 em 15/07/2026 e de novo em 30/07/2026 — duas faturas
    seguidas, mesmo rótulo, mesmo centavo. Valor fiscal que se repete igual é
    duplicidade até que se prove o contrário, e ninguém acha isso olhando
    uma fatura por vez: cada uma tem uma linha só.

    Compara o relatório com ele mesmo E com os casos já gravados, que é como
    a repetição ENTRE meses aparece.
    """
    fiscais = [r for r in (sep or {}).get("conferir", [])
               if r["natureza"] == "fiscal"]
    antigos = [c for c in (casos or [])
               if str(c.get("natureza", "")) == "fiscal"]
    fora = []
    for r in fiscais:
        iguais = [x for x in fiscais
                  if x is not r and x["detalhe"] == r["detalhe"]
                  and abs(x["valor"] - r["valor"]) < 0.01]
        iguais += [c for c in antigos
                   if str(c.get("detalhe", "")) == r["detalhe"]
                   and abs(_num(c.get("valor")) - r["valor"]) < 0.01
                   and str(c.get("numero", "")) != r["numero"]]
        if iguais:
            datas = sorted({str(x.get("data", "")) for x in iguais
                            if str(x.get("data", ""))})
            fora.append((r, datas))
    return fora


def fiscais_sem_venda(sep):
    """As cobranças fiscais que NÃO dá para ligar a nenhuma venda.

    Isto não é um detalhe: a linha de R$ 69,60 de agosto veio sem Número da
    venda e com NF-e "Ainda indisponível". Sem esse número, o Studio não
    consegue cruzar imposto com venda devolvida — que é exatamente o caso em
    aberto do dono. A falta é dita em voz alta em vez de ser contornada:
    quando ela aparecer, a conferência é no painel do ML, não aqui.
    """
    return [r for r in (sep or {}).get("conferir", [])
            if r["natureza"] == "fiscal" and not r["venda"]]


def vendas_devolvidas(sep):
    """Os números de venda com tarifa de devolução no mês.

    Servem para o dono conferir, no painel do ML, se alguma delas também foi
    tributada — o cruzamento automático não existe enquanto a linha fiscal
    vier sem venda (ver `fiscais_sem_venda`).
    """
    return sorted({r["venda"] for r in (sep or {}).get("na_fatura", [])
                   if r["natureza"] == "devolucao" and r["venda"]})


def estornos_encontrados(casos, sep):
    """[(caso, linha_de_cancelamento)] — o que o ML já devolveu.

    O casamento é pelo número da tarifa que a coluna "Tarifa cancelada"
    aponta, nunca por valor: em ago/2026 há 56 cancelamentos de "Custo por
    vender" e os valores se repetem. Casar por valor fecharia o caso errado.
    """
    cancelamentos = (sep or {}).get("cancelamentos", {})
    fora = []
    for c in (casos or []):
        if str(c.get("situacao", "")).strip().upper() != EM_ABERTO:
            continue
        alvo = cancelamentos.get(id_tarifa(c.get("numero", "")))
        if alvo:
            fora.append((c, alvo))
    return fora


def em_aberto(casos):
    return [c for c in (casos or [])
            if str(c.get("situacao", "")).strip().upper() == EM_ABERTO]


def resumo(casos):
    """{situacao: {'n': , 'total': }} para o cabeçalho da tela."""
    fora = {}
    for c in (casos or []):
        s = str(c.get("situacao", "") or EM_ABERTO).strip().upper()
        d = fora.setdefault(s, {"n": 0, "total": 0.0})
        d["n"] += 1
        d["total"] = round(d["total"] + _num(c.get("valor")), 2)
    return fora


# ── Planilha ─────────────────────────────────────────────────────────────────

def _aba():
    import gspread
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        return planilha.worksheet(ABA_CASOS)
    except gspread.WorksheetNotFound:
        nova = planilha.add_worksheet(title=ABA_CASOS, rows=2000,
                                      cols=len(COLUNAS_CASO))
        nova.append_row(COLUNAS_CASO, value_input_option="RAW")
        return nova


@st.cache_data(ttl=120)
def carregar():
    """[{...}] dos casos gravados. Lista vazia em qualquer falha."""
    try:
        registros = _aba().get_all_records()
    except Exception:
        return []
    fora = []
    for r in registros:
        if not str(r.get("id", "") or "").strip():
            continue
        fora.append({c: r.get(c, "") for c in COLUNAS_CASO})
    return fora


def abrir(casos_novos, usuario=""):
    """Grava os que ainda não existem. (novos, ja_existiam, erro).

    Nunca reescreve linha existente: reimportar a planilha do mês não pode
    apagar o "ACEITA" que alguém marcou na tela.
    """
    agora = datetime.now(FUSO).strftime("%Y-%m-%d %H:%M")
    novos = 0
    try:
        aba = _aba()
        ja = {str(r.get("id", "")).strip()
              for r in aba.get_all_records() if str(r.get("id", "")).strip()}
        linhas, vistos = [], set()
        for c in (casos_novos or []):
            cid = str(c.get("id", "")).strip()
            if not cid or cid in ja or cid in vistos:
                continue
            vistos.add(cid)
            linhas.append([c.get(k, "") for k in COLUNAS_CASO[:-2]]
                          + [agora, str(usuario or "")[:60]])
        if linhas:
            aba.append_rows(linhas, value_input_option="RAW")
        novos = len(linhas)
        repetidos = len(casos_novos or []) - novos
    except Exception as e:
        return 0, 0, str(e)[:200]
    carregar.clear()
    return novos, repetidos, ""


def atualizar(id_caso, campos, usuario=""):
    """Altera um caso gravado. (ok, mensagem)."""
    alvo = str(id_caso or "").strip()
    if not alvo:
        return False, "Sem id não dá para saber qual caso alterar."
    try:
        aba = _aba()
        registros = aba.get_all_records()
        achados = [i for i, r in enumerate(registros)
                   if str(r.get("id", "")).strip() == alvo]
        if not achados:
            return False, "Não achei este caso na aba."
        i = achados[-1]
        atual = dict(registros[i])
        atual.update({k: v for k, v in (campos or {}).items()
                      if k in COLUNAS_CASO})
        atual["atualizado_em"] = datetime.now(FUSO).strftime("%Y-%m-%d %H:%M")
        atual["atualizado_por"] = str(usuario or "")[:60]
        fim = chr(ord("A") + len(COLUNAS_CASO) - 1)
        n = i + 2
        aba.update([[atual.get(c, "") for c in COLUNAS_CASO]], f"A{n}:{fim}{n}",
                   value_input_option="RAW")
    except Exception as e:
        return False, str(e)[:200]
    carregar.clear()
    return True, "Alterado."


def encerrar(id_caso, situacao, observacao="", usuario=""):
    """Fecha o caso à mão — aceito ou estornado."""
    s = str(situacao or "").strip().upper()
    if s not in SITUACOES:
        return False, f"Situação inválida: {situacao}"
    return atualizar(id_caso, {"situacao": s, "observacao": observacao},
                     usuario)


def aplicar_estornos(pares, usuario=""):
    """Fecha como ESTORNADO os casos cujo cancelamento já apareceu."""
    fechados, erro = 0, ""
    for caso, alvo in (pares or []):
        ok, msg = atualizar(caso["id"], {
            "situacao": ESTORNADO,
            "estorno_numero": alvo.get("numero", ""),
            "estorno_em": alvo.get("data", ""),
            "observacao": f"Estorno de {moeda(abs(_num(alvo.get('valor'))))} "
                          f"identificado pelo ML."}, usuario)
        if ok:
            fechados += 1
        else:
            erro = msg
    return fechados, erro


# ── Conferência ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Aba falsa: a conferência roda sem rede, como em cheques.py.
    class _Falsa:
        def __init__(self):
            self.linhas = []

        def get_all_records(self):
            return [dict(zip(COLUNAS_CASO, l)) for l in self.linhas]

        def append_rows(self, linhas, **kw):
            self.linhas.extend(linhas)

        def update(self, values, range_name=None, **kw):
            n = int("".join(c for c in str(range_name).split(":")[0]
                            if c.isdigit())) - 2
            self.linhas[n] = list(values[0])

    _falsa = _Falsa()
    globals()["_aba"] = lambda: _falsa
    globals()["carregar"] = type("C", (), {
        "clear": staticmethod(lambda: None)})()

    falhas = []

    def ok(nome, cond):
        if not cond:
            falhas.append(nome)
        print(("  ok  " if cond else "FALHOU") + "  " + nome)

    # 1. Natureza — fiscal antes de devolução, porque a linha tem as duas.
    ok("fiscal ganha de devolução na mesma linha",
       natureza("Cancelamento da cobrança de ICMS por devolução") == "fiscal")
    ok("DIFAL de agosto é fiscal",
       natureza("Cobrança do diferencial de alíquota interestadual "
                "(ICMS-DIFAL)") == "fiscal")
    ok("tarifa de devolução é devolução",
       natureza("Tarifa de devolução por envio externo ou intermunicipal")
       == "devolucao")
    ok("ADS é tarifa comum",
       natureza("Tarifa por campanha de publicidade de Product Ads")
       == "tarifa")
    ok("sem acento e sem caixa dá no mesmo",
       natureza("COBRANCA DE IMPOSTO") == "fiscal")

    # 2. Número da tarifa: o float da planilha e o int do pagamento são o mesmo.
    ok("68069345761.0 e 68069345761 são a mesma tarifa",
       id_tarifa(68069345761.0) == id_tarifa("68069345761") == "68069345761")
    ok("vazio continua vazio", id_tarifa(None) == id_tarifa("") == "")

    # 3. Cabeçalho: layout diferente é recusado, não lido torto.
    ok("cabeçalho completo passa",
       cabecalho_valido([COL_DETALHE, COL_VALOR, COL_DESCONTADO, "outra"])[0])
    achou, faltando = cabecalho_valido([COL_DETALHE, COL_VALOR])
    ok("falta 'Descontado da operação' e ele é nomeado",
       (not achou) and faltando == [COL_DESCONTADO])

    # 4. separar() — os três baldes, com os números medidos em ago/2026.
    linhas = [
        {COL_DETALHE: "Tarifa por campanha de publicidade de Product Ads",
         COL_VALOR: 2762.80, COL_DESCONTADO: "Não", COL_NUMERO: 1.0},
        {COL_DETALHE: "Custo por vender no Mercado Livre",
         COL_VALOR: 24480.85, COL_DESCONTADO: "Sim", COL_NUMERO: 2.0},
        {COL_DETALHE: "Cancelamento do Custo por vender no Mercado Livre",
         COL_VALOR: -97.78, COL_DESCONTADO: "Não se aplica",
         COL_NUMERO: 3.0, COL_CANCELADA: 2.0},
        {COL_DETALHE: "Cobrança do diferencial de alíquota interestadual "
                      "(ICMS-DIFAL)", COL_VALOR: 69.60,
         COL_DESCONTADO: "Não", COL_NUMERO: 68080404754.0,
         COL_DATA: datetime(2026, 7, 30), COL_NFE: "Ainda indisponível"},
        {COL_DETALHE: "Tarifa de devolução", COL_VALOR: 61.50,
         COL_DESCONTADO: "Não", COL_NUMERO: 5.0,
         COL_VENDA: "2000017601814770", COL_STATUS: "Cancelado neste mes"},
    ]
    sep = separar(linhas)
    ok("fatura soma só o 'Não'", sep["total_fatura"] == round(
        2762.80 + 69.60 + 61.50, 2))
    ok("operação soma só o 'Sim'", sep["total_operacao"] == 24480.85)
    ok("'Não se aplica' fica no seu próprio balde, visível",
       sep["total_nao_se_aplica"] == -97.78 and len(sep["nao_se_aplica"]) == 1)
    ok("'Não se aplica' não entra na fatura",
       all(r["detalhe"] != "Cancelamento do Custo por vender no Mercado Livre"
           for r in sep["na_fatura"]))
    ok("conferir pegou a fiscal e a devolução, e só elas",
       len(sep["conferir"]) == 2
       and {r["natureza"] for r in sep["conferir"]} == {"fiscal", "devolucao"})
    ok("o cancelamento aponta a tarifa 2",
       sep["cancelamentos"].get("2", {}).get("numero") == "3")
    ok("a data virou texto", sep["conferir"][0]["data"] == "2026-07-30")

    # 4b. Os grupos com o vocabulário dele, e o alarme do que for novo.
    #
    # Os oito nomes abaixo são EXATAMENTE os que o ML mandou em ago/2026.
    # Se um deles deixar de casar, a tela passa a mostrar "Novo" para uma
    # cobrança de sempre — e o alarme que existe para o desconhecido vira
    # ruído que ninguém lê.
    DE_AGOSTO = {
        "Tarifa por campanha de publicidade de Product Ads": "ADS",
        "Custo do serviço de coleta Full": "Cross (envios Full)",
        "Tarifa pelo serviço de armazenamento Full": "Cross (envios Full)",
        "Tarifa por estoque antigo no Full": "Cross (envios Full)",
        "Tarifa de manutenção da Minha página": "Página da loja",
        "Cobrança do diferencial de alíquota interestadual (ICMS-DIFAL)":
            "Impostos",
        "Tarifa de devolução": "Devoluções",
        "Tarifa de devolução por envio externo ou intermunicipal":
            "Devoluções",
    }
    for _texto, _esperado in DE_AGOSTO.items():
        ok(f"'{_texto[:42]}…' → {_esperado}",
           grupo_de(_texto) == _esperado)
    ok("devolução ganha de envio na mesma linha",
       grupo_de("Tarifa de devolução por envio externo ou intermunicipal")
       == "Devoluções")
    ok("imposto ganha de tudo",
       grupo_de("Cancelamento de ICMS por devolução de publicidade")
       == "Impostos")
    ok("cobrança que o ML inventar cai em NOVO",
       grupo_de("Tarifa de assinatura Mercado Livre Mais") == NOVO)

    _grupos = por_grupo([{"detalhe": t, "valor": 10.0, "natureza": natureza(t)}
                         for t in DE_AGOSTO])
    ok("Flex aparece mesmo zerado — ausência dele é informação",
       "Flex" in _grupos and _grupos["Flex"]["total"] == 0.0)
    ok("nada de agosto caiu em NOVO", _grupos[NOVO]["n"] == 0)
    ok("ADS somou a sua linha", _grupos["ADS"]["total"] == 10.0)
    ok("custo devido em cima, conferência embaixo",
       list(_grupos)[:2] == ["ADS", "Cross (envios Full)"]
       and list(_grupos)[-3:] == ["Devoluções", "Impostos", NOVO])
    ok("todo grupo que casa tem lugar na ordem da tela",
       all(nome in ORDEM_NA_TELA for nome, _ in GRUPOS))
    ok("Cross somou as três dele", _grupos["Cross (envios Full)"]["n"] == 3)
    ok("novidades() nomeia o que é novo",
       novidades([{"detalhe": "Tarifa nova do ML", "valor": 12.0}])
       == [("Tarifa nova do ML", 12.0)])

    # 5. Pagamento — é ele que manda nas saídas.
    resumo_pg = [
        {RE_TIPO: "Pagamento voluntário", RE_MEIO: "Visa",
         RE_STATUS: "Pagamento aprovado", RE_TOTAL: 3200.18,
         RE_DATA: datetime(2026, 9, 4)},
        {RE_ESTORNO: "Em processamento", RE_TIPO: "Estorno",
         RE_STATUS: "Em processo de faturamento", RE_TOTAL: 21.47},
        {RE_ESTORNO: "Em processamento", RE_TIPO: "Estorno",
         RE_STATUS: "Em processo de faturamento", RE_TOTAL: 136.41},
    ]
    detalhe_pg = [
        {PG_NUMERO: "1", PG_APLICADO: 2762.80, PG_DETALHE: "Product Ads",
         PG_PAGAMENTO: "000fawarhe", PG_DATA: datetime(2026, 9, 4)},
        {PG_NUMERO: "68080404754", PG_APLICADO: 69.60,
         PG_DETALHE: "ICMS-DIFAL", PG_PAGAMENTO: "000fawarhe"},
    ]
    pag = ler_pagamentos(resumo_pg, detalhe_pg)
    ok("total pago é a soma do detalhe", pag["total_pago"] == 2832.40)
    ok("o pagamento do cartão foi separado do estorno",
       len(pag["pagamentos"]) == 1 and pag["pagamentos"][0]["meio"] == "Visa")
    ok("estornos em processamento somam 157,88",
       pag["total_estornos"] == 157.88 and len(pag["estornos"]) == 2)

    # 6. conciliar() — a diferença vem com NOME, não como número solto.
    dif, nao_cobradas = conciliar(sep, pag)
    ok("a diferença é a tarifa de devolução de 61,50", dif == 61.50)
    ok("e ela é nomeada, não só contada",
       len(nao_cobradas) == 1 and nao_cobradas[0]["valor"] == 61.50)

    # 7. Alertas — dizem se a cobrança JÁ SAIU da conta.
    frases = alertas(sep, pag)
    ok("uma frase por cobrança a conferir", len(frases) == 2)
    ok("só as pagas, quando o dono pediu só as pagas",
       len(alertas(sep, pag, so_pagas=True)) == 1)
    ok("a fiscal paga é marcada como JÁ PAGA",
       any("JÁ PAGA" in f and "ICMS-DIFAL" in f for f in frases))
    ok("a devolução não cobrada NÃO é marcada como paga",
       any("não cobrada" in f and "Tarifa de devolução" in f for f in frases))
    ok("a fiscal sem número de venda avisa disso",
       any("não tem Número da venda" in f for f in frases))

    # 7b. Moeda — formato do Brasil, e cifrão escapado no markdown.
    ok("R$ 1.234,50, não 1,234.50", moeda(1234.5) == "R$ 1.234,50")
    ok("negativo também", moeda(-97.78) == "R$ -97,78")
    ok("no markdown o cifrão vai escapado",
       moeda(69.6, markdown=True) == "R\\$ 69,60")
    import re as _re
    ok("NENHUM alerta leva cifrão cru — dois deles viram fórmula LaTeX e "
       "comem o aviso inteiro",
       all(not _re.search(r"(?<!\\)\$", f) for f in frases))

    # 8. Identidade — reimportar a mesma planilha reencontra o caso.
    a = sep["conferir"][0]
    ok("o número da tarifa manda na identidade",
       identidade(a) == "t68080404754")
    sem_numero = dict(a, numero="")
    ok("sem número, o hash é estável",
       identidade(sem_numero) == identidade(dict(sem_numero)))
    ok("e duas cobranças diferentes não colidem",
       identidade(sem_numero) != identidade(dict(sem_numero, valor=70.0)))

    # 9. Quem vira caso: o que SAIU da conta.
    novos_casos = casos_a_abrir(sep, pag)
    ok("a devolução não cobrada não vira caso — dinheiro que não saiu",
       len(novos_casos) == 1 and novos_casos[0]["natureza"] == "fiscal")
    ok("sem planilha de pagamento, tudo vira caso",
       len(casos_a_abrir(sep)) == 2)
    ok("a fiscal sem venda é apontada como não-cruzável",
       len(fiscais_sem_venda(sep)) == 1)
    ok("e a venda devolvida fica listada para conferir no painel do ML",
       vendas_devolvidas(sep) == ["2000017601814770"])

    # 9a. Valor fiscal repetido — o R$ 69,60 cobrado em 15/07 e de novo em
    # 30/07 na conta Little Glass. Uma fatura por vez, ninguém vê.
    _difal = "Cobrança do diferencial de alíquota interestadual (ICMS-DIFAL)"
    ok("não acusa repetição onde não há", fiscais_repetidas(sep) == [])
    _sep2 = separar([
        {COL_DETALHE: _difal, COL_VALOR: 69.60, COL_DESCONTADO: "Não",
         COL_NUMERO: 111.0, COL_DATA: datetime(2026, 7, 15)},
        {COL_DETALHE: _difal, COL_VALOR: 69.60, COL_DESCONTADO: "Não",
         COL_NUMERO: 222.0, COL_DATA: datetime(2026, 7, 30)},
    ])
    _rep = fiscais_repetidas(_sep2)
    ok("dois R$ 69,60 na mesma planilha: as duas linhas saem marcadas",
       len(_rep) == 2)
    ok("e cada uma aponta a data da outra",
       _rep[0][1] == ["2026-07-30"] and _rep[1][1] == ["2026-07-15"])
    _hist = [{"detalhe": _difal, "valor": 69.60, "natureza": "fiscal",
              "numero": "111", "data": "2026-07-15"}]
    _um = separar([{COL_DETALHE: _difal, COL_VALOR: 69.60,
                    COL_DESCONTADO: "Não", COL_NUMERO: 222.0,
                    COL_DATA: datetime(2026, 7, 30)}])
    ok("repetição ENTRE meses também é achada, contra os casos gravados",
       len(fiscais_repetidas(_um, _hist)) == 1)
    ok("a mesma tarifa reimportada não é repetição dela mesma",
       fiscais_repetidas(_um, [dict(_hist[0], numero="222")]) == [])
    ok("valor fiscal diferente não é repetição",
       fiscais_repetidas(separar([
           {COL_DETALHE: _difal, COL_VALOR: 69.60, COL_DESCONTADO: "Não",
            COL_NUMERO: 111.0},
           {COL_DETALHE: _difal, COL_VALOR: 658.90, COL_DESCONTADO: "Não",
            COL_NUMERO: 222.0}])) == [])

    # 9b. Persistência — é o coração do caso em aberto do dono.
    novos_casos = [caso_de(r, pago=r["numero"] in set(pag["por_numero"]))
                   for r in sep["conferir"]]
    n, rep, erro = abrir(novos_casos, "conferencia")
    ok("os dois casos foram gravados", (n, rep, erro) == (2, 0, ""))
    n2, rep2, _ = abrir(novos_casos, "conferencia")
    ok("reimportar a mesma planilha não duplica", (n2, rep2) == (0, 2))

    gravados = [dict(zip(COLUNAS_CASO, l)) for l in _falsa.linhas]
    ok("nascem EM ABERTO",
       all(c["situacao"] == EM_ABERTO for c in gravados))
    ok("o motivo foi escrito junto",
       all(len(c["motivo"]) > 40 for c in gravados))
    ok("o caso fiscal sabe que já foi pago",
       any(c["natureza"] == "fiscal" and c["observacao"] == "Cobrança já paga."
           for c in gravados))
    ok("em_aberto() devolve os dois", len(em_aberto(gravados)) == 2)
    ok("resumo() conta e soma", resumo(gravados)[EM_ABERTO]["n"] == 2)

    # 10. O estorno fecha o caso — pela coluna do ML, não por valor parecido.
    fiscal = [c for c in gravados if c["natureza"] == "fiscal"][0]
    sep_set = separar([
        {COL_DETALHE: "Cancelamento da cobrança do diferencial de alíquota",
         COL_VALOR: -69.60, COL_DESCONTADO: "Não se aplica",
         COL_NUMERO: 99999.0, COL_CANCELADA: 68080404754.0,
         COL_DATA: datetime(2026, 9, 18)},
        {COL_DETALHE: "Custo por vender no Mercado Livre", COL_VALOR: -69.60,
         COL_DESCONTADO: "Não se aplica", COL_NUMERO: 88888.0},
    ])
    pares = estornos_encontrados(gravados, sep_set)
    ok("o estorno foi achado pelo número, não pelo valor igual",
       len(pares) == 1 and pares[0][1]["numero"] == "99999")
    fechados, erro = aplicar_estornos(pares, "conferencia")
    ok("e fechou o caso", fechados == 1 and not erro)

    gravados = [dict(zip(COLUNAS_CASO, l)) for l in _falsa.linhas]
    fiscal = [c for c in gravados if c["natureza"] == "fiscal"][0]
    ok("o caso fiscal está ESTORNADO", fiscal["situacao"] == ESTORNADO)
    ok("com a data e o número do estorno",
       fiscal["estorno_em"] == "2026-09-18"
       and fiscal["estorno_numero"] == "99999")
    ok("e a devolução continua EM ABERTO — ninguém a estornou",
       len(em_aberto(gravados)) == 1)
    ok("estorno já aplicado não é reaplicado",
       estornos_encontrados(gravados, sep_set) == [])

    # 11. Encerrar à mão.
    aberto = em_aberto(gravados)[0]
    ok("situação inválida é recusada",
       encerrar(aberto["id"], "SUMIU")[0] is False)
    ok("aceitar fecha", encerrar(aberto["id"], ACEITA, "conferido", "leo")[0])
    ok("e não sobra nada em aberto",
       em_aberto([dict(zip(COLUNAS_CASO, l)) for l in _falsa.linhas]) == [])

    print()
    if falhas:
        print("FALHOU: " + ", ".join(falhas))
        raise SystemExit(1)
    print("Tudo certo.")
