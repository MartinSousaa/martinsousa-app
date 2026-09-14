"""home_gestao.py — A primeira tela da Gestão: o mês contra o que ele precisa ser.

A FORMA
-------
Sete indicadores, e todos fazem a mesma pergunta: **o realizado contra o
necessário**. Isso não é gráfico de série — é medida única contra alvo. A forma
certa é a barra com marcador, que é exatamente o que o Painel de Metas já usa
para ociosidade e pontuação. Quem abre esta tela já sabe ler essa barra.

Nada aqui é gráfico de linha, pizza ou barra empilhada: não há série temporal
nem composição para mostrar. Uma pizza de seis fatias responderia pior a única
pergunta que a tela tem.

COR NUNCA SOZINHA
-----------------
As três cores são estado, não identidade: verde acima do necessário, amarelo a
menos de 8% dele, vermelho abaixo. Toda barra carrega o veredito **escrito** ao
lado — quem não distingue as cores lê a frase. O vermelho do Studio tem 2,79:1
de contraste no fundo escuro, abaixo dos 3:1: é por isso que o texto nunca
depende dele, e o selo do ritmo é preenchido com tinta escura por cima.

O PONTO DE EQUILÍBRIO VEM PRIMEIRO
----------------------------------
Foi decisão do gestor: "meta de faturamento é secundário, o principal é
alcançarmos o ponto de equilíbrio". Por isso o faturamento ocupa a tela inteira
no topo, com as DUAS linhas — Operacional (a operação se paga) e Não
operacional (a operação se paga E as parcelas do PRONAMP saem) —, a meta do
mês e o ritmo do dia; os outros seis vêm embaixo, em cartões menores.

UMA PROJEÇÃO SÓ
---------------
Tudo que a tela chama de projeção sai do mesmo lugar: o ritmo médio dos dias
já corridos, esticado até o fim do mês. Duas projeções discordando na mesma
tela não informam — escolhem pelo gestor, e escondem qual método escolheu.

OS NÚMEROS DESTA TELA SÃO DE EXEMPLO
------------------------------------
`EXEMPLO` é um dicionário de valores fictícios, marcado como tal na tela. Ele
existe para o layout ser aprovado antes de haver de onde ler os dados reais —
LPV, UC e os lucros dependem de campos que ainda são preenchidos à mão durante a
venda. Trocar a fonte é trocar o dicionário por uma leitura; a tela não muda.
"""

import calendar

import streamlit as st

# Estado, não identidade. As três nunca aparecem lado a lado disputando
# significado: cada barra mostra uma só, e sempre com a frase ao lado.
VERDE = "#1BAF7A"
AMARELO = "#EDA100"
VERMELHO = "#E34948"


def _brl(v, casas=2):
    return "R$ " + f"{float(v):,.{casas}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def _num(v, casas=2, sufixo=""):
    return f"{float(v):,.{casas}f}".replace(",", "§").replace(".", ",").replace("§", ".") + sufixo


# ── Dados de exemplo ─────────────────────────────────────────────────────────
# Setembro de 2026, dia 14. Números fictícios, coerentes entre si: a projeção
# sai da curva medida em três anos (financeiro_historico) e as duas linhas de
# equilíbrio saem da margem medida em 17.793 vendas (financeiro_equilibrio).
EXEMPLO = {
    "dia": 14, "mes": 9, "ano": 2026,
    "faturamento": {
        "realizado": 148_320.00,
        "meta": 240_000.00,
        "operacional": 131_918.00, "nao_operacional": 183_940.00,
    },
    # Três por linha: bruto em cima, líquido embaixo, e cada valor em R$ ao
    # lado da sua própria margem em %. O mesmo fato lido nas duas unidades —
    # por isso o R$ aqui é a margem vezes o faturado, e a conferência trava
    # os dois juntos: se um dia discordarem, a tela mente em dois cartões
    # vizinhos.
    "cards": [
        {"rotulo": "Lucro bruto", "sub": "no mês",
         "realizado": 102_340.80, "necessario": 94_924.80, "fmt": "brl0",
         "maior_melhor": True, "acumula": True},
        {"rotulo": "Margem bruta", "sub": "sobre o faturado",
         "realizado": 69.0, "necessario": 64.0, "fmt": "pct",
         "maior_melhor": True, "acumula": False},
        {"rotulo": "LPV", "sub": "lucro por venda",
         "realizado": 19.86, "necessario": 17.50, "fmt": "brl",
         "maior_melhor": True, "acumula": False},
        {"rotulo": "Lucro líquido", "sub": "no mês",
         "realizado": 41_974.56, "necessario": 35_596.80, "fmt": "brl0",
         "maior_melhor": True, "acumula": True},
        {"rotulo": "Margem líquida", "sub": "sobre o faturado",
         "realizado": 28.3, "necessario": 24.0, "fmt": "pct",
         "maior_melhor": True, "acumula": False},
        {"rotulo": "UC", "sub": "unidade de contribuição, média por venda",
         "realizado": 1.8, "necessario": 1.5, "fmt": "razao",
         "maior_melhor": True, "acumula": False},
    ],
    # OPERACIONAL — desempenho por canal.
    #
    # Os quatro canais da LG sao os numeros REAIS lidos do Bling em 14/09/2026
    # (Administrativo › Bling). Os cinco da MS sao inventados, fechando no
    # bruto e nos pedidos que a mesma leitura mostrou: R$ 58.454 e 533.
    #
    # So entram faturamento e vendas. As duas participacoes (%) e o ticket
    # medio sao CALCULADOS — guardar porcentagem escrita ao lado do valor que
    # a origina e combinar os dois para discordarem um dia.
    "operacional": [
        {"canal": "ML 1",     "cnpj": "LG", "faturamento": 37_262.20, "vendas": 284},
        {"canal": "ML 2",     "cnpj": "MS", "faturamento": 31_200.00, "vendas": 268},
        {"canal": "SHOPEE 2", "cnpj": "LG", "faturamento": 16_274.24, "vendas": 133},
        {"canal": "ML 4",     "cnpj": "MS", "faturamento": 12_480.50, "vendas": 121},
        {"canal": "SHOPEE 1", "cnpj": "MS", "faturamento": 11_903.20, "vendas": 118},
        {"canal": "ML 3",     "cnpj": "LG", "faturamento":  8_095.64, "vendas":  68},
        {"canal": "SHEIN 2",  "cnpj": "MS", "faturamento":  2_210.30, "vendas":  21},
        {"canal": "TIKTOK 2", "cnpj": "MS", "faturamento":    660.00, "vendas":   5},
        {"canal": "SHEIN 1º", "cnpj": "LG", "faturamento":    534.92, "vendas":   8},
    ],
}


def participacao(linhas):
    """Cada canal com as duas participações e o ticket médio. Função pura.

    Devolve (canais, por_cnpj, total) já ordenados por faturamento.

    As DUAS participações e não uma: um canal pode ser 31% do dinheiro e 28%
    das vendas, e a diferença entre os dois números é o ticket médio dele.
    Mostrar só a do faturamento esconderia justamente o canal que vende muito
    e fatura pouco — que é o que dá trabalho na expedição sem pagar a conta.
    """
    linhas = list(linhas or [])
    t_fat = sum(float(l.get("faturamento") or 0) for l in linhas)
    t_ven = sum(int(l.get("vendas") or 0) for l in linhas)
    canais = []
    por_cnpj = {}
    for l in sorted(linhas, key=lambda x: -float(x.get("faturamento") or 0)):
        fat, ven = float(l.get("faturamento") or 0), int(l.get("vendas") or 0)
        canais.append({
            "canal": l.get("canal", "?"),
            "cnpj": l.get("cnpj", ""),
            "faturamento": fat,
            "vendas": ven,
            "pct_fat": (fat / t_fat * 100) if t_fat else 0.0,
            "pct_ven": (ven / t_ven * 100) if t_ven else 0.0,
            # Canal sem venda nenhuma nao pode derrubar a tela por divisao
            # por zero: ticket sem venda e zero, nao erro.
            "ticket": (fat / ven) if ven else 0.0,
        })
        acc = por_cnpj.setdefault(l.get("cnpj", ""), {"faturamento": 0.0,
                                                      "vendas": 0})
        acc["faturamento"] += fat
        acc["vendas"] += ven
    for acc in por_cnpj.values():
        acc["pct_fat"] = (acc["faturamento"] / t_fat * 100) if t_fat else 0.0
        acc["pct_ven"] = (acc["vendas"] / t_ven * 100) if t_ven else 0.0
        acc["ticket"] = (acc["faturamento"] / acc["vendas"]) if acc["vendas"] else 0.0
    return (canais, por_cnpj, {"faturamento": t_fat, "vendas": t_ven,
                               "ticket": (t_fat / t_ven) if t_ven else 0.0})


def _fmt(valor, como):
    if como == "razao":
        # Unidade de contribuicao e quantas unidades saem por venda: le-se
        # "1,8 para 1", nao um valor em real.
        return _num(valor, 1) + "/1"
    if como == "pct":
        return _num(valor, 1, "%")
    if como == "brl0":
        return _brl(valor, 0)
    return _brl(valor)


def ritmo(d):
    """Meta gradual e ritmo médio: o mês repartido pelos dias que já passaram.

    Devolve (alvo_ate_hoje, por_dia, projecao, dia, dias).

    A meta se reparte em partes iguais pelos dias CORRIDOS — é o dia do
    calendário que faz o cheque vencer, não o dia útil. A curva de venda não é
    reta (o mês tem picos), mas fingir uma curva sem ter a medida seria pior
    que a reta honesta: quando `financeiro_historico` entregar a curva medida,
    troca-se esta função e a tela não muda.

    A projeção é o ritmo médio vezes os dias do mês — UM método só, porque
    duas projeções discordando na mesma tela não informam, escolhem por você.
    """
    f = d["faturamento"]
    dias = int(d.get("dias_mes") or calendar.monthrange(d["ano"], d["mes"])[1])
    dia = min(max(int(d["dia"]), 1), dias)
    alvo = f.get("meta", 0.0) * dia / dias
    por_dia = f["realizado"] / dia
    return alvo, por_dia, por_dia * dias, dia, dias


def projetar(valor, dia, dias, acumula):
    """Onde este indicador fecha o mês se o ritmo de hoje se mantiver.

    Quem ACUMULA (lucro em R$) se estica pelos dias que faltam. Quem já é
    média (margem, LPV, UC) fecha onde está: esticar uma razão pelo tempo
    daria um número sem significado.
    """
    return valor / dia * dias if acumula else valor


def _bloco_faturamento(d):
    """O faturamento contra o equilíbrio, a meta do mês e a meta do dia.

    Duas linhas de equilíbrio e não uma: os PRONAMPs saem do caixa mas não são
    custo de operar, e incluir ou não muda a resposta em R$ 52 mil. Em vez de
    escolher pelo gestor, a barra mostra as duas — Operacional e Não
    operacional — e diz onde a projeção caiu.

    Duas trilhas empilhadas na MESMA escala: em cima o realizado, embaixo o
    ritmo — o pedaço da meta que os dias já consumiram. Comparar comprimento
    de barra é mais barato para o olho que comparar dois números escritos.
    """
    f = d["faturamento"]
    op, cx = f["operacional"], f["nao_operacional"]
    meta, real = f.get("meta", 0.0), f["realizado"]
    alvo_hoje, por_dia, proj, dia, dias = ritmo(d)

    if proj >= cx:
        cor_proj, veredito = VERDE, "fecha acima das duas linhas"
    elif proj >= op:
        cor_proj, veredito = AMARELO, "paga o operacional, não o resto"
    else:
        cor_proj, veredito = VERMELHO, "fecha abaixo do operacional"

    if real >= alvo_hoje:
        cor, seta, frase = VERDE, "▲", "acima do ritmo"
    elif real >= alvo_hoje * 0.92:
        cor, seta, frase = AMARELO, "▲", "quase no ritmo"
    else:
        cor, seta, frase = VERMELHO, "▼", "abaixo do ritmo"
    dif = abs(real - alvo_hoje)

    # O selo e preenchido com a cor de estado e escreve em tinta escura: o
    # vermelho do Studio tem 2,79:1 sobre o fundo escuro, e texto colorido
    # nele ficaria abaixo do minimo. Preenchido, a leitura passa dos 5:1.
    selo = (f'<span style="background:{cor};color:#161616;font-size:12.5px;'
            f'font-weight:800;padding:4px 10px;border-radius:999px;'
            f'white-space:nowrap;">{seta} {_brl(dif, 0)} {frase}</span>')

    # A regua para na META, nao na projecao: esticar ate uma projecao que
    # supera a meta em 32% abria um vazio de um terco da barra depois do
    # marcador da meta, e vazio nao e informacao. A projecao fica escrita.
    escala = max(meta, cx, real) * 1.06 or 1
    x = lambda v: min(max(v / escala * 100, 0), 100)
    rot = ('font-size:10px;color:var(--ms-texto-sec);text-align:right;'
           'white-space:nowrap;')

    st.markdown(
        f'<div style="background:var(--ms-metric-bg);'
        f'border:1px solid var(--ms-metric-bd);border-radius:12px;'
        f'padding:16px 18px 12px;">'

        f'<div style="font-size:11px;color:var(--ms-texto-sec);'
        f'letter-spacing:.3px;">'
        f'Faturamento × ponto de equilíbrio × meta</div>'

        f'<div style="display:flex;align-items:center;gap:12px;'
        f'flex-wrap:wrap;margin-top:6px;">'
        f'<span style="font-size:40px;font-weight:700;color:var(--ms-texto);'
        f'line-height:1;">{_brl(real, 0)}</span>'
        f'<span style="font-size:12px;color:var(--ms-texto-sec);">'
        f'faturado até o dia {dia} de {dias}</span>'
        + selo +
        f'<span style="margin-left:auto;text-align:right;line-height:1.2;">'
        f'<span style="display:block;font-size:11px;'
        f'color:var(--ms-texto-sec);">Se mantiver o ritmo, fecha em</span>'
        f'<span style="font-size:24px;font-weight:700;color:{cor_proj};">'
        f'{_brl(proj, 0)}</span></span>'
        f'</div>'

        # Duas trilhas na mesma escala, com rótulo à esquerda: o que a coluna
        # da direita mede é sempre o mesmo eixo de R$ faturado no mês.
        f'<div style="display:grid;grid-template-columns:96px 1fr;'
        f'gap:6px 10px;align-items:center;margin-top:16px;">'

        f'<div style="{rot}font-weight:700;color:var(--ms-texto);">Realizado</div>'
        f'<div style="height:18px;border-radius:9px;'
        f'background:var(--ms-metric-bd);position:relative;">'
        f'<div style="position:absolute;left:0;top:0;height:100%;'
        f'width:{x(real):.1f}%;background:{cor};border-radius:9px;"></div>'
        + _marcador(x(op))
        + _marcador(x(cx))
        + _marcador(x(meta)) +
        f'</div>'

        f'<div style="{rot}">Ritmo do dia {dia}</div>'
        f'<div style="height:10px;border-radius:5px;'
        f'background:var(--ms-metric-bd);position:relative;">'
        f'<div style="position:absolute;left:0;top:0;height:100%;'
        f'width:{x(alvo_hoje):.1f}%;background:var(--ms-texto-sec);'
        f'border-radius:5px;opacity:.85;"></div></div>'

        f'<div></div>'
        f'<div style="position:relative;height:15px;">'
        + _rotulo(x(op), "▲ Operacional")
        + _rotulo(x(cx), "▲ Não operacional")
        + _rotulo(x(meta), "▲ Meta") +
        f'</div></div>'

        f'<div style="display:flex;justify-content:space-between;gap:12px;'
        f'flex-wrap:wrap;font-size:11px;color:var(--ms-texto-sec);'
        f'margin-top:8px;">'
        f'<span>Meta do mês <b style="color:var(--ms-texto);">{_brl(meta, 0)}</b>'
        f' · até o dia {dia} deveria ter <b style="color:var(--ms-texto);">'
        f'{_brl(alvo_hoje, 0)}</b></span>'
        f'<span>Ritmo médio <b style="color:var(--ms-texto);">'
        f'{_brl(por_dia, 0)}/dia</b> em {dia} dias</span></div>'

        f'<div style="display:flex;justify-content:space-between;gap:12px;'
        f'flex-wrap:wrap;font-size:11px;color:var(--ms-texto-sec);'
        f'margin-top:4px;">'
        f'<span>Projeção = ritmo médio × {dias} dias</span>'
        f'<span>Projeção: <b style="color:{cor_proj};">{veredito}</b></span>'
        f'<span>Operacional {_brl(op, 0)} · Não operacional {_brl(cx, 0)}</span>'
        f'</div></div>',
        unsafe_allow_html=True)


def _rotulo(pos, texto):
    return (f'<span style="position:absolute;left:{pos:.1f}%;'
            f'transform:translateX(-50%);font-size:9px;font-weight:700;'
            f'white-space:nowrap;color:var(--ms-texto);">{texto}</span>')


def _marcador(pos):
    return (f'<div style="position:absolute;top:-6px;bottom:-6px;'
            f'left:{pos:.1f}%;width:3px;margin-left:-1.5px;border-radius:2px;'
            f'background:var(--ms-texto);"></div>')


def atingiu(c):
    """Bateu o necessário? A direção é do cartão, não da tela."""
    r, n = float(c["realizado"]), float(c["necessario"])
    return r >= n if c["maior_melhor"] else r <= n


def _card(c, dia=1, dias=1):
    """Um indicador: realizado contra necessário, e onde ele fecha o mês.

    `maior_melhor` existe porque nem todos apontam para o mesmo lado: em LPV,
    nos lucros e na unidade de contribuição, mais é melhor; num custo, menos.
    Sem isso, a mesma cor diria coisas opostas em cartões vizinhos.
    """
    r, n = float(c["realizado"]), float(c["necessario"])
    bateu = atingiu(c)
    perto = abs(r - n) / (abs(n) or 1) <= 0.08
    cor = VERDE if bateu else (AMARELO if perto else VERMELHO)
    falta = (n - r) if c["maior_melhor"] else (r - n)
    verbo = "acima do necessário" if bateu else (
        "abaixo do necessário" if c["maior_melhor"] else "acima do necessário")
    # Diferenca entre duas porcentagens e ponto percentual, nao porcentagem:
    # "1,9%" ao lado de "48,0%" faz o olho ler 1,9% DE 48, que e outro numero.
    dif = (_num(abs(falta), 1, " p.p.") if c["fmt"] == "pct"
           else _num(abs(falta), 1) if c["fmt"] == "razao"
           else _fmt(abs(falta), c["fmt"]))
    fecha = projetar(r, dia, dias, c.get("acumula", False))
    nota = ("soma o mês inteiro no ritmo de hoje" if c.get("acumula")
            else "já é média: fecha onde está")
    escala = max(r, n) * 1.25 or 1
    return (
        f'<div style="background:var(--ms-metric-bg);'
        f'border:1px solid var(--ms-metric-bd);border-radius:10px;'
        f'padding:12px 14px;height:100%;">'
        f'<div style="font-size:11.5px;font-weight:700;'
        f'color:var(--ms-texto);letter-spacing:.2px;">{c["rotulo"]}</div>'
        f'<div style="font-size:9px;color:var(--ms-texto-sec);'
        f'margin-bottom:6px;">{c["sub"]}</div>'
        f'<div style="font-size:26px;font-weight:700;color:var(--ms-texto);'
        f'line-height:1.1;">{_fmt(r, c["fmt"])}</div>'
        f'<div style="height:10px;border-radius:5px;'
        f'background:var(--ms-metric-bd);margin:10px 0 4px;position:relative;">'
        f'<div style="position:absolute;left:0;top:0;height:100%;'
        f'width:{min(r / escala * 100, 100):.1f}%;background:{cor};'
        f'border-radius:5px;"></div>'
        f'<div style="position:absolute;top:-4px;bottom:-4px;'
        f'left:{min(n / escala * 100, 100):.1f}%;width:3px;margin-left:-1.5px;'
        f'border-radius:2px;background:var(--ms-texto);"></div></div>'
        f'<div style="font-size:9.5px;color:var(--ms-texto-sec);">'
        f'Necessário <b style="color:var(--ms-texto);">'
        f'{_fmt(n, c["fmt"])}</b></div>'
        f'<div style="font-size:10.5px;font-weight:700;color:{cor};'
        f'margin-top:4px;">{"✔" if bateu else "▸"} {dif} {verbo}</div>'
        f'<div style="margin-top:7px;padding-top:6px;'
        f'border-top:1px solid var(--ms-metric-bd);font-size:9.5px;'
        f'color:var(--ms-texto-sec);">No ritmo, fecha em '
        f'<b style="color:var(--ms-texto);">{_fmt(fecha, c["fmt"])}</b>'
        f'<br><span style="opacity:.75;">{nota}</span></div>'
        f'</div>')


# Os dois CNPJs. NAO sao distinguidos por cor — o par azul/roxo que eu tinha
# escolhido reprovou no validador: DeltaE 10,2 entre os dois, abaixo do piso de
# 15, ou seja, indistinguiveis ate para quem enxerga todas as cores (e 2,5 para
# quem tem protanopia). Em vez de procurar outro par, a distincao saiu da cor:
# a sigla esta ESCRITA no selo, e a forma (cheio x vazado) separa os dois sem
# depender de enxergar hue nenhum. Cor aqui tambem brigaria com o verde/
# amarelo/vermelho de estado, que nesta tela querem dizer "bateu" e "nao bateu".
CNPJS = {"LG": "Little Glass", "MS": "MS"}


def _selo_cnpj(sigla):
    base = ('display:inline-block;min-width:26px;text-align:center;'
            'font-size:9px;font-weight:800;padding:2px 5px;border-radius:4px;')
    if sigla == "LG":
        return (f'<span style="{base}background:var(--ms-texto-sec);'
                f'color:#161616;">{sigla}</span>')
    return (f'<span style="{base}background:transparent;'
            f'border:1px solid var(--ms-texto-sec);'
            f'color:var(--ms-texto);">{sigla}</span>')


def _barra_dupla(pct_fat, pct_ven, escala=100.0):
    """Duas barras finas na MESMA escala: dinheiro em cima, vendas embaixo.

    O desencontro entre elas É o ticket médio — barra de cima mais curta que a
    de baixo quer dizer canal que dá trabalho na expedição sem pagar a conta.

    A escala é a maior participação da tabela, não 100%: com nove canais, o
    maior fica em 31% e o resto da trilha seria espaço morto. Como as duas
    barras dividem a mesma escala, a comparação entre elas não muda — e o
    número em % vai escrito na linha de qualquer jeito.
    """
    larg = lambda v: min(v / (escala or 1) * 100, 100)
    return (
        f'<div style="display:flex;flex-direction:column;gap:3px;">'
        f'<div style="height:9px;border-radius:5px;'
        f'background:var(--ms-metric-bd);position:relative;">'
        f'<div style="position:absolute;left:0;top:0;height:100%;'
        f'width:{larg(pct_fat):.1f}%;background:{VERDE};'
        f'border-radius:5px;"></div></div>'
        f'<div style="height:9px;border-radius:5px;'
        f'background:var(--ms-metric-bd);position:relative;">'
        f'<div style="position:absolute;left:0;top:0;height:100%;'
        f'width:{larg(pct_ven):.1f}%;background:var(--ms-texto-sec);'
        f'border-radius:5px;opacity:.9;"></div></div></div>')


def _bloco_operacional(d):
    """Desempenho por canal: quanto cada um fatura, vende, e o que representa.

    Nove canais em barra ordenada, e não em pizza: a pergunta é "quem puxa e
    quem não puxa", que se responde comparando comprimento. Numa pizza de nove
    fatias, as quatro últimas somam 3% e viram lasca sem rótulo.

    Nenhuma cor identifica canal. O nome já está escrito na linha — pintar
    nove hues obrigaria o olho a consultar legenda para ler uma tabela que ele
    já lê de cima para baixo.
    """
    canais, por_cnpj, total = participacao(d.get("operacional"))
    if not canais:
        return

    st.markdown('<div style="height:14px;"></div>', unsafe_allow_html=True)

    # A trilha vai ate a maior participacao da tabela, com 5% de folga.
    escala = max([c["pct_fat"] for c in canais]
                 + [c["pct_ven"] for c in canais]) * 1.05 or 100.0

    cab = ('font-size:9.5px;color:var(--ms-texto-sec);'
           'text-transform:none;letter-spacing:.2px;')
    grade = ('display:grid;grid-template-columns:96px 34px minmax(160px,1fr) '
             '112px 74px 88px;'
             'gap:8px 10px;align-items:center;')

    # Os dois CNPJs primeiro: e a comparacao que o gestor faz antes de descer
    # para o canal.
    cartoes = ""
    for sigla in ("LG", "MS"):
        acc = por_cnpj.get(sigla)
        if not acc:
            continue
        nome = CNPJS.get(sigla, sigla)
        # Borda cheia x tracejada: a mesma distincao do selo, pelo mesmo
        # motivo — forma sobrevive a qualquer daltonismo e a impressao P&B.
        risco = "solid" if sigla == "LG" else "dashed"
        cartoes += (
            f'<div style="flex:1;min-width:230px;background:var(--ms-metric-bg);'
            f'border:1px solid var(--ms-metric-bd);'
            f'border-left:3px {risco} var(--ms-texto-sec);'
            f'border-radius:10px;padding:10px 14px;">'
            f'<div style="display:flex;align-items:center;gap:6px;">'
            + _selo_cnpj(sigla) +
            f'<span style="font-size:11.5px;font-weight:700;'
            f'color:var(--ms-texto);">{nome}</span></div>'
            f'<div style="display:flex;align-items:baseline;gap:10px;'
            f'flex-wrap:wrap;margin-top:2px;">'
            f'<span style="font-size:22px;font-weight:700;'
            f'color:var(--ms-texto);">{_brl(acc["faturamento"], 0)}</span>'
            f'<span style="font-size:11px;color:var(--ms-texto-sec);">'
            f'{_num(acc["pct_fat"], 1, "%")} do faturado</span></div>'
            f'<div style="font-size:10.5px;color:var(--ms-texto-sec);'
            f'margin-top:3px;">{acc["vendas"]} vendas · '
            f'{_num(acc["pct_ven"], 1, "%")} do total · ticket '
            f'<b style="color:var(--ms-texto);">{_brl(acc["ticket"])}</b>'
            f'</div></div>')

    linhas = ""
    for c in canais:
        linhas += (
            f'<div style="{cab}color:var(--ms-texto);font-weight:600;'
            f'font-size:11px;">{c["canal"]}</div>'
            f'<div>{_selo_cnpj(c["cnpj"])}</div>'
            + _barra_dupla(c["pct_fat"], c["pct_ven"], escala) +
            f'<div style="text-align:right;font-size:11px;'
            f'color:var(--ms-texto);">{_brl(c["faturamento"], 0)}'
            f'<span style="color:var(--ms-texto-sec);"> · '
            f'{_num(c["pct_fat"], 1, "%")}</span></div>'
            f'<div style="text-align:right;font-size:11px;'
            f'color:var(--ms-texto);">{c["vendas"]}'
            f'<span style="color:var(--ms-texto-sec);"> · '
            f'{_num(c["pct_ven"], 1, "%")}</span></div>'
            f'<div style="text-align:right;font-size:11px;'
            f'color:var(--ms-texto-sec);">{_brl(c["ticket"])}</div>')

    st.markdown(
        f'<div style="background:var(--ms-metric-bg);'
        f'border:1px solid var(--ms-metric-bd);border-radius:12px;'
        f'padding:16px 18px 14px;">'

        f'<div style="font-size:11px;color:var(--ms-texto-sec);'
        f'letter-spacing:.3px;">Operacional</div>'
        f'<div style="font-size:16px;font-weight:700;color:var(--ms-texto);'
        f'margin:2px 0 2px;">Desempenho por conta</div>'
        f'<div style="font-size:11px;color:var(--ms-texto-sec);">'
        f'Participação de cada canal no faturamento e nas vendas. '
        f'{len(canais)} canais · {_brl(total["faturamento"], 0)} · '
        f'{total["vendas"]} vendas · ticket médio '
        f'{_brl(total["ticket"])}</div>'

        f'<div style="display:flex;gap:10px;flex-wrap:wrap;'
        f'margin:12px 0 16px;">{cartoes}</div>'

        # Legenda: sao duas barras por linha, entao a identidade delas nunca
        # fica so na cor.
        f'<div style="display:flex;gap:16px;flex-wrap:wrap;font-size:10px;'
        f'color:var(--ms-texto-sec);margin-bottom:8px;">'
        f'<span><span style="display:inline-block;width:18px;height:7px;'
        f'border-radius:4px;background:{VERDE};vertical-align:middle;">'
        f'</span> % do faturamento</span>'
        f'<span><span style="display:inline-block;width:18px;height:7px;'
        f'border-radius:4px;background:var(--ms-texto-sec);'
        f'vertical-align:middle;"></span> % das vendas</span></div>'

        f'<div style="{grade}">'
        f'<div style="{cab}">Canal</div><div style="{cab}">CNPJ</div>'
        f'<div style="{cab}">Participação</div>'
        f'<div style="{cab}text-align:right;">Faturamento</div>'
        f'<div style="{cab}text-align:right;">Vendas</div>'
        f'<div style="{cab}text-align:right;">Ticket médio</div>'
        + linhas +
        f'</div></div>',
        unsafe_allow_html=True)


def pagina(usuario_logado=None, dados=None):
    d = dados or EXEMPLO
    st.markdown("### 🏠 Home")
    st.caption("O resumo do mês: onde o faturamento está contra o que ele "
               "precisa ser. **O ponto de equilíbrio vem primeiro** — meta de "
               "faturamento é consequência dele.")

    if dados is None:
        st.warning("**Números de exemplo**, para aprovar o layout. Nenhum "
                   "deles vem da operação ainda.")

    _, _, _, dia, dias = ritmo(d)
    _bloco_faturamento(d)

    st.markdown('<div style="height:10px;"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="display:grid;grid-template-columns:repeat(3,1fr);'
        'gap:10px;">'
        + "".join(_card(c, dia, dias) for c in d["cards"])
        + '</div>',
        unsafe_allow_html=True)

    _bloco_operacional(d)

    st.caption(
        f"Mês de referência {d['mes']:02d}/{d['ano']}, fechado no dia "
        f"{dia} de {dias}. O **ritmo** reparte a meta em partes iguais pelos "
        "dias corridos do mês, e a **projeção** é o ritmo médio vezes os "
        "dias do mês — um método só, porque duas projeções discordando na "
        "mesma tela não informam, escolhem por você.")


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    ok("real sai no formato brasileiro", _brl(148320, 0) == "R$ 148.320")
    ok("porcentagem sai com uma casa", _fmt(12.4, "pct") == "12,4%")
    ok("a unidade de contribuição sai como razão", _fmt(1.8, "razao") == "1,8/1")
    ok("o exemplo tem os seis cartões", len(EXEMPLO["cards"]) == 6)
    ok("todo cartão diz para que lado é melhor e se acumula",
       all("maior_melhor" in c and "acumula" in c for c in EXEMPLO["cards"]))
    ok("todo rótulo começa com maiúscula",
       all(c["rotulo"][0].isupper() for c in EXEMPLO["cards"]))
    ok("no exemplo ilustrado, todo cartão bate o necessário",
       all(atingiu(c) for c in EXEMPLO["cards"]))
    ok("o não operacional é sempre maior que o operacional",
       EXEMPLO["faturamento"]["nao_operacional"]
       > EXEMPLO["faturamento"]["operacional"])
    ok("a meta do mês fica acima do não operacional",
       EXEMPLO["faturamento"]["meta"]
       > EXEMPLO["faturamento"]["nao_operacional"])

    # As margens em % e os lucros em R$ sao o MESMO fato em duas unidades: se
    # um dia discordarem, a tela mente em dois cartoes vizinhos.
    _c = {c["rotulo"]: c for c in EXEMPLO["cards"]}
    _fat = EXEMPLO["faturamento"]["realizado"]
    for _lucro, _margem in (("Lucro bruto", "Margem bruta"),
                            ("Lucro líquido", "Margem líquida")):
        for _campo in ("realizado", "necessario"):
            _esperado = _c[_lucro][_campo] / _fat * 100
            ok(f"{_margem} bate com {_lucro} ({_campo})",
               abs(_esperado - _c[_margem][_campo]) < 0.06)

    # Ritmo: meta repartida pelos dias CORRIDOS, e a projecao saindo do
    # proprio ritmo — nunca de um numero escrito a mao em outro lugar.
    _alvo, _dia_a_dia, _proj, _dia, _dias = ritmo(EXEMPLO)
    ok("setembro tem 30 dias", _dias == 30)
    ok("o ritmo do dia 14 é 14/30 da meta", abs(_alvo - 240_000 * 14 / 30) < 0.01)
    ok("o ritmo médio é o faturado dividido pelos dias corridos",
       abs(_dia_a_dia - 148_320 / 14) < 0.01)
    ok("a projeção é o ritmo médio vezes os dias do mês",
       abs(_proj - _dia_a_dia * 30) < 0.01)
    ok("no último dia do mês, ritmo e projeção encontram o realizado",
       abs(ritmo(dict(EXEMPLO, dia=30))[0] - 240_000) < 0.01
       and abs(ritmo(dict(EXEMPLO, dia=30))[2] - 148_320) < 0.01)
    ok("um dia além do fim do mês não estica a projeção",
       abs(ritmo(dict(EXEMPLO, dia=44))[2] - 148_320) < 0.01)

    # O que ACUMULA se estica; o que ja e media fecha onde esta. Esticar uma
    # razao pelo tempo daria um numero sem significado.
    ok("o lucro em R$ se estica pelos dias que faltam",
       abs(projetar(102_340.80, 14, 30, True) - 102_340.80 / 14 * 30) < 0.01)
    ok("a margem em % fecha onde está",
       projetar(69.0, 14, 30, False) == 69.0)
    ok("só os lucros em R$ acumulam",
       [c["rotulo"] for c in EXEMPLO["cards"] if c["acumula"]]
       == ["Lucro bruto", "Lucro líquido"])

    # ── Operacional: as duas participacoes ─────────────────────────────────
    _canais, _cnpj, _tot = participacao(EXEMPLO["operacional"])
    ok("os nove canais entram", len(_canais) == 9)
    ok("sai ordenado do maior faturamento para o menor",
       [c["faturamento"] for c in _canais]
       == sorted((c["faturamento"] for c in _canais), reverse=True))
    ok("as participações de faturamento somam 100%",
       abs(sum(c["pct_fat"] for c in _canais) - 100.0) < 0.001)
    ok("as participações de vendas somam 100%",
       abs(sum(c["pct_ven"] for c in _canais) - 100.0) < 0.001)
    ok("o ticket médio é faturamento dividido por vendas",
       all(abs(c["ticket"] - c["faturamento"] / c["vendas"]) < 0.001
           for c in _canais))
    ok("os dois CNPJs somam o total",
       abs(sum(v["faturamento"] for v in _cnpj.values())
           - _tot["faturamento"]) < 0.001
       and sum(v["vendas"] for v in _cnpj.values()) == _tot["vendas"])

    # Os quatro canais da LG sao leitura real do Bling em 14/09/2026: se o
    # exemplo deixar de bater com ela, o numero virou invencao sem aviso.
    ok("a LG do exemplo bate com o Bling: R$ 62.167 em 493 vendas",
       abs(_cnpj["LG"]["faturamento"] - 62_166.99) < 0.01
       and _cnpj["LG"]["vendas"] == 493)
    ok("a MS do exemplo fecha nos números que a mesma leitura mostrou",
       abs(_cnpj["MS"]["faturamento"] - 58_454.00) < 0.01
       and _cnpj["MS"]["vendas"] == 533)
    ok("todo canal declara o CNPJ", all(c["cnpj"] in CNPJS for c in _canais))

    ok("canal sem venda não derruba por divisão por zero",
       participacao([{"canal": "X", "cnpj": "LG",
                      "faturamento": 0.0, "vendas": 0}])[0][0]["ticket"] == 0.0)
    ok("lista vazia não derruba", participacao([])[0] == [])
    ok("lista None não derruba", participacao(None)[2]["vendas"] == 0)

    # As tres cores sao ESTADO: cada barra mostra uma so, e sempre com frase.
    ok("as três cores de estado são distintas",
       len({VERDE, AMARELO, VERMELHO}) == 3)
    # O CNPJ nao e distinguido por cor nenhuma: o selo traz a sigla escrita e
    # a forma (cheio x vazado). Se um dia alguem puser hue aqui, este caso
    # lembra por que o par anterior foi reprovado.
    ok("o selo do CNPJ não depende de cor para se distinguir",
       "LG" in _selo_cnpj("LG") and "MS" in _selo_cnpj("MS")
       and _selo_cnpj("LG") != _selo_cnpj("MS")
       and not any(h in (_selo_cnpj("LG") + _selo_cnpj("MS"))
                   for h in (VERDE, AMARELO, VERMELHO)))

    print("\nfalhas:", falhas)
