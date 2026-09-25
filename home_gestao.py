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

O QUE NÃO ENTRA AQUI
--------------------
O desempenho por canal de venda viveu um tempo embaixo dos cartões e saiu por
decisão do gestor: "não é tão importante para estar na aba de resumo". Está
inteiro em `operacional_gestao.py`, esperando a aba dele. Esta tela responde
uma pergunta só — o mês está onde precisa estar? —, e o que não responde essa
pergunta cobra o preço de quem abre para decidir em dez segundos.

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
from datetime import datetime

import streamlit as st

import rotulos as _rot

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
        # A meta ILUSTRADA e a conta de verdade, com os numeros de
        # jun-ago/2026: R$ 170.000 de meta de gastos divididos pelos 65,2%
        # que sobram depois de comissao, frete, NF e devolucao. Exemplo com
        # numero redondo inventado ensinaria a conta errada a quem abre o
        # arquivo para entender a tela.
        "meta_de_gastos": 170_000.00,
        "taxa_de_entrada": 0.6524,
        "meta": round(170_000.00 / 0.6524, 2),
        "descontos": [
            {"nome": "comissão", "valor": 127_512.06, "pct": 16.4},
            {"nome": "frete", "valor": 60_045.61, "pct": 7.7},
            {"nome": "NF / imposto", "valor": 60_879.32, "pct": 7.8},
            {"nome": "devoluções", "valor": 21_471.76, "pct": 2.8},
        ],
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
}


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


# Quanto do faturamento pode virar devolução antes de virar problema. É TETO,
# não meta: o cartão fica vermelho quando PASSA disto. Em jan–ago/2026 o real
# foi 2,54% (R$ 46.989,61 de R$ 1.852.806,88).
TETO_DEVOLUCAO_PCT = 3.0


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
    import equilibrio_caixa as _ec
    f = d["faturamento"]
    dias = int(d.get("dias_mes") or calendar.monthrange(d["ano"], d["mes"])[1])
    dia = min(max(int(d["dia"]), 1), dias)
    # A FRAÇÃO INCLUI A HORA DE HOJE — pedido do dono: "22 dias fechados e
    # mais 17h do dia de hoje". Cobrar o dia inteiro assim que ele começa
    # fazia a tela dizer que a manhã estava atrasada todo santo dia; às 9h
    # do dia 1º ela já cobrava um dia de faturamento que não teve como
    # acontecer. `agora` chega de fora nos testes; na tela é o relógio.
    fracao = _ec.fracao_do_mes(d.get("agora"), dias)
    if not fracao:                       # primeiro instante do mês
        fracao = dia / dias
    alvo = f.get("meta", 0.0) * fracao
    por_dia = f["realizado"] / dia
    return alvo, por_dia, f["realizado"] / fracao, dia, dias


def projetar(valor, dia, dias, acumula):
    """Onde este indicador fecha o mês se o ritmo de hoje se mantiver.

    Quem ACUMULA (lucro em R$) se estica pelos dias que faltam. Quem já é
    média (margem, LPV, UC) fecha onde está: esticar uma razão pelo tempo
    daria um número sem significado.
    """
    return valor / dia * dias if acumula else valor


def _de_onde_vem_a_meta(f):
    """A conta da meta, escrita ao lado dela.

    Numero sem origem e numero que ninguem confere — e esta meta ja esteve
    errada por meses (R$ 34.865 num mes de R$ 270 mil) sem ninguem saber de
    onde ela saia. Agora a frase diz: meta de gastos / o que cai na conta.
    """
    gastos = f.get("meta_de_gastos") or 0.0
    taxa = f.get("taxa_de_entrada")
    if not gastos or not taxa:
        return ""
    return (f' <span style="opacity:.8;">= meta de gastos '
            f'{_brl(gastos, 0)} ÷ {taxa * 100:.1f}% que cai na conta</span>')


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

    # A META ENTRA NO VEREDITO. Ele comparava a projecao so com as duas
    # linhas de equilibrio do cadastro e dizia "fecha acima das duas linhas"
    # em verde enquanto a projecao (R$ 235.972) nao alcancava a meta
    # (R$ 260.576) — verde por cima de um mes que nao fecha.
    if meta and proj < meta and proj >= cx:
        cor_proj, veredito = AMARELO, "paga as contas, mas não bate a meta"
    elif proj >= max(cx, meta or 0):
        cor_proj, veredito = VERDE, "fecha acima da meta e das duas linhas"
    elif proj >= cx:
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
        f'Faturamento em tempo real</span>'
        + selo +
        f'<span style="margin-left:auto;text-align:right;line-height:1.2;">'
        f'<span style="display:block;font-size:11px;'
        f'color:var(--ms-texto-sec);">Se mantiver o ritmo, fecha em</span>'
        f'<span style="font-size:24px;font-weight:700;color:{cor_proj};">'
        f'{_brl(proj, 0)}</span>'
        + _projecao_contra_a_meta(proj, meta, cor_proj) +
        f'</span>'
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
        + _rotulos([(x(op), "Operacional"), (x(cx), "Não operacional"),
                    (x(meta), "Meta")]) +
        f'</div></div>'

        f'<div style="display:flex;justify-content:space-between;gap:12px;'
        f'flex-wrap:wrap;font-size:11px;color:var(--ms-texto-sec);'
        f'margin-top:8px;">'
        f'<span>Meta do mês <b style="color:var(--ms-texto);">{_brl(meta, 0)}</b>'
        f'{_de_onde_vem_a_meta(f)}'
        f' · até agora deveria ter <b style="color:var(--ms-texto);">'
        f'{_brl(alvo_hoje, 0)}</b></span>'
        f'<span>Ritmo médio <b style="color:var(--ms-texto);">'
        f'{_brl(por_dia, 0)}/dia</b> em {dia} dias</span></div>'

        f'<div style="display:flex;justify-content:space-between;gap:12px;'
        f'flex-wrap:wrap;font-size:11px;color:var(--ms-texto-sec);'
        f'margin-top:4px;">'
        f'<span>Projeção = ritmo médio × {dias} dias</span>'
        f'<span>Projeção: <b style="color:{cor_proj};">{veredito}</b></span>'
        f'<span>{_as_duas_linhas(op, cx, d)}</span>'
        f'</div></div>',
        unsafe_allow_html=True)


def _rotulo(pos, texto):
    # NO FIM DA REGUA, CENTRAR TRANSBORDA O CARTAO. "▲ Meta" mora em ~95% e
    # metade dele cai fora da borda direita; no comeco acontece o espelho.
    desloc = "0" if pos <= 6 else ("-100%" if pos >= 94 else "-50%")
    return (f'<span style="position:absolute;left:{pos:.1f}%;'
            f'transform:translateX({desloc});font-size:9px;font-weight:700;'
            f'white-space:nowrap;color:var(--ms-texto);">▲ {texto}</span>')


def _rotulos(marcas, limiar=9.0):
    """Os rótulos da régua, e nenhum por cima do outro.

    O DEFEITO QUE ELE CORRIGE
    -------------------------
    Em 25/09 a tela imprimiu "▲ Nãopoperacionall" — "▲ Operacional" e "▲ Não
    operacional" no MESMO ponto, um sobre o outro, ilegíveis. Não era acaso:
    o equilíbrio Não operacional é `equilibrio(num_hoje + segunda_linha, m)`
    (`composicao.py:273`), então ele É o Operacional sempre que o mês não tem
    parcela de PRONAMP classificada. Ou seja, todo mês sem PRONAMP na conta
    cai aqui.

    Dois rótulos no mesmo lugar não informam nenhum dos dois — viram sujeira
    em cima do único gráfico da tela. Juntos numa frase só, informam os dois
    E dizem o fato novo: as duas linhas coincidem.

    `limiar` em 9% da largura porque perto também se toca: numa barra de
    1.600px isso são 144px, e "Não operacional" a 9px ocupa uns 110px.
    """
    grupos = []
    for pos, txt in sorted(marcas, key=lambda m: m[0]):
        if grupos and pos - grupos[-1][-1][0] <= limiar:
            grupos[-1].append((pos, txt))
        else:
            grupos.append([(pos, txt)])
    return "".join(
        _rotulo(sum(p for p, _ in g) / len(g), " = ".join(t for _, t in g))
        for g in grupos)


def _projecao_contra_a_meta(proj, meta, cor):
    """Quanto falta (ou sobra) para a meta, no ritmo de agora.

    A tela dizia onde o mês fecha — R$ 233.725 — e deixava a subtração para
    quem lê: "isso é acima ou abaixo da meta, e por quanto?". O número que
    decide é a DISTÂNCIA, e ele não estava escrito em lugar nenhum.
    """
    if not meta:
        return ""
    d = proj - meta
    return (f'<span style="display:block;font-size:10.5px;font-weight:700;'
            f'color:{cor};">{"▲" if d >= 0 else "▼"} {_brl(abs(d), 0)} '
            f'{"acima" if d >= 0 else "abaixo"} da meta</span>')


def _as_duas_linhas(op, cx, d=None):
    """As duas linhas de equilíbrio — e, quando são a mesma, por quê.

    "Operacional R$ 40.834 · Não operacional R$ 40.834" lado a lado parece
    erro de leitura. Não é: sem parcela de PRONAMP classificada no mês, a
    segunda linha não tem o que somar. Dizer isso custa uma frase; não dizer
    custa a confiança no número.
    """
    segunda = float(((d or {}).get("equilibrio") or {}).get("segunda_linha") or 0.0)
    if abs(float(cx) - float(op)) < 1.0:
        motivo = ("nenhuma parcela de PRONAMP classificada neste mês"
                  if not segunda else "a segunda linha não mudou o resultado")
        return (f'Operacional e Não operacional coincidem em {_brl(op, 0)} — '
                f'{motivo}')
    return f'Operacional {_brl(op, 0)} · Não operacional {_brl(cx, 0)}'


def _marcador(pos):
    return (f'<div style="position:absolute;top:-6px;bottom:-6px;'
            f'left:{pos:.1f}%;width:3px;margin-left:-1.5px;border-radius:2px;'
            f'background:var(--ms-texto);"></div>')


def atingiu(c):
    """Bateu o necessário? A direção é do cartão, não da tela."""
    r, n = float(c["realizado"]), float(c["necessario"])
    return r >= n if c["maior_melhor"] else r <= n


def _card_sem_regua(c, dia=1, dias=1):
    """O cartão de quem ainda não tem meta: só o número, a origem e a projeção.

    `estimado` marca o que foi CALCULADO a partir do faturamento de agora e da
    margem dos meses fechados, em vez de medido. Número que parece medido e
    não é, é o que faz decisão errada — e aqui ele aparece com a palavra
    "estimado" do lado, não escondido numa legenda.
    """
    r = float(c["realizado"])
    fecha = projetar(r, dia, dias, c.get("acumula", False))
    selo = ""
    if c.get("estimado"):
        selo = ('<span style="font-size:9px;font-weight:700;'
                'color:var(--ms-texto-sec);border:1px solid '
                'var(--ms-metric-bd);border-radius:4px;padding:1px 4px;'
                'margin-left:6px;">estimado</span>')
    return (
        f'<div style="background:var(--ms-metric-bg);'
        f'border:1px solid var(--ms-metric-bd);border-radius:10px;'
        f'padding:12px 14px;height:100%;">'
        f'<div style="font-size:11.5px;font-weight:700;'
        f'color:var(--ms-texto);letter-spacing:.2px;">{c["rotulo"]}{selo}</div>'
        f'<div style="font-size:9px;color:var(--ms-texto-sec);'
        f'margin-bottom:6px;">{c["sub"]}</div>'
        f'<div style="font-size:26px;font-weight:700;color:var(--ms-texto);'
        f'line-height:1.1;">{_fmt(r, c["fmt"])}</div>'
        f'<div style="margin-top:10px;padding-top:6px;'
        f'border-top:1px solid var(--ms-metric-bd);font-size:9.5px;'
        f'color:var(--ms-texto-sec);">'
        f'{c.get("rodape") or ("No ritmo, fecha em <b style=color:var(--ms-texto);>" + _fmt(fecha, c["fmt"]) + "</b>" if c.get("acumula") else "Sem meta definida para este indicador.")}'
        f'</div></div>')


def _card(c, dia=1, dias=1):
    """Um indicador: realizado contra necessário, e onde ele fecha o mês.

    `maior_melhor` existe porque nem todos apontam para o mesmo lado: em LPV,
    nos lucros e na unidade de contribuição, mais é melhor; num custo, menos.
    Sem isso, a mesma cor diria coisas opostas em cartões vizinhos.
    """
    r = float(c["realizado"])
    # SEM RÉGUA NÃO HÁ VEREDITO.
    #
    # Quatro cartões passavam o próprio valor como "necessário" e diziam
    # "✔ R$ 0 acima do necessário" para sempre — nunca podiam ficar
    # vermelhos. Eram dados de exemplo que ficaram. Agora, cartão sem régua
    # mostra o NÚMERO e de quando ele é, sem barra e sem veredito: barra que
    # não pode apontar para baixo é enfeite que finge informar.
    if c.get("necessario") is None:
        return _card_sem_regua(c, dia, dias)
    n = float(c["necessario"])
    bateu = atingiu(c)
    perto = abs(r - n) / (abs(n) or 1) <= 0.08
    cor = VERDE if bateu else (AMARELO if perto else VERMELHO)
    falta = (n - r) if c["maior_melhor"] else (r - n)
    # QUEM TEM TETO SE LÊ AO CONTRÁRIO. A frase era sempre "acima do
    # necessário" quando batia — e num cartão de teto, bater é estar ABAIXO
    # dele. A tela dizia "✔ R$ 929 acima do necessário" para R$ 4.429 de
    # devolução contra um teto de R$ 5.359.
    if c["maior_melhor"]:
        verbo = "acima do necessário" if bateu else "abaixo do necessário"
    else:
        verbo = "abaixo do teto" if bateu else "ACIMA DO TETO"
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
        f'{"Teto" if not c["maior_melhor"] else "Necessário"} '
        f'<b style="color:var(--ms-texto);">'
        f'{_fmt(n, c["fmt"])}</b></div>'
        f'<div style="font-size:10.5px;font-weight:700;color:{cor};'
        f'margin-top:4px;">{"✔" if bateu else "▸"} {dif} {verbo}</div>'
        f'<div style="margin-top:7px;padding-top:6px;'
        f'border-top:1px solid var(--ms-metric-bd);font-size:9.5px;'
        f'color:var(--ms-texto-sec);">No ritmo, fecha em '
        f'<b style="color:var(--ms-texto);">{_fmt(fecha, c["fmt"])}</b>'
        f'<br><span style="opacity:.75;">{nota}</span></div>'
        f'</div>')


def _bloco_gastos(usuario_logado=None, d=None):
    """Os gastos do mês, abaixo dos seis indicadores. Aprovado em layout 17/09.

    Lê a meta que o gestor digitou e os lançamentos que vieram dos extratos, e
    responde a pergunta que ele faz olhando para cá: *dá para comprar?*

    Três blocos, e a ordem é a da decisão:
      1. meta, realizado e saldo — o número que decide
      2. por finalidade — onde o dinheiro foi
      3. o que falta abrir e o que falta classificar — a dívida de trabalho

    Cheque, fatura e boleto ficam separados de propósito: são COMO se pagou,
    não O QUE se comprou. Somados com "mercadoria", contariam a mesma compra
    duas vezes.
    """
    from datetime import datetime
    import placar_core as _pc
    import meta_gastos as _mg
    import lancamentos as _lan

    st.markdown("---")
    st.markdown("#### 💰 Gastos do mês")

    hoje = datetime.now(_pc.FUSO).date()
    _ano_ref = int((d or {}).get("ano") or hoje.year)
    _mes_ref = int((d or {}).get("mes") or hoje.month)

    # O mês se escolhe aqui, e não fica preso ao da Home.
    #
    # O bloco nasceu mostrando só o mês de referência, e no dia 17 de setembro
    # isso são dois lançamentos: o gasto do mês mal começou. Os números que o
    # gestor quer olhar estão no mês fechado, e obrigá-lo a mudar a Home
    # inteira para ver agosto é pedir quatro cliques para uma pergunta.
    _cm, _cy, _ = st.columns([1, 1, 3])
    mes = _cm.selectbox(
        "Mês", list(range(1, 13)), index=_mes_ref - 1, key="hg_gasto_mes",
        format_func=lambda m: ["janeiro", "fevereiro", "março", "abril",
                               "maio", "junho", "julho", "agosto", "setembro",
                               "outubro", "novembro", "dezembro"][m - 1])
    ano = _cy.number_input("Ano", 2020, 2100, _ano_ref, 1, key="hg_gasto_ano")

    try:
        linha = _mg.linha_do_mes(ano, mes)
        lancs = _lan.do_mes(ano, mes)
    except Exception as e:
        st.caption(f"Não consegui ler os gastos: {str(e)[:140]}")
        return

    # ── 1. o número que decide ───────────────────────────────────────────
    #
    # E ele é o COMPROMETIDO, não o que já bateu na conta.
    #
    # Mostrar só o extrato dizia, em 17/09, "13% da meta consumida" — e a
    # decisão que sai disso é "dá para comprar à vontade". Não dá: o aluguel,
    # a luz, a folha e as parcelas do mês já estão devidos, só não passaram
    # ainda. O Studio conhece os três, e não precisa que ninguém digite.
    import pandas as pd
    import previsto as _pv

    res = _lan.resumo_por_finalidade(lancs) if lancs else {}
    prev, _erros_prev = _pv.do_mes(ano, mes)
    combinado, total_comp = _pv.combinar(res, prev)
    a_sair = round(sum(x["falta_sair"] for x in combinado), 2)

    if not lancs and not linha["meta"] and not total_comp:
        st.info(
            "Sem meta, sem lançamentos e sem nada provisionado neste mês. A "
            "meta se digita em **Financeiro › 🎯 Meta de gastos**; os "
            "lançamentos entram sozinhos quando você sobe o extrato em "
            "**Financeiro › 💳 Extratos**.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Já saiu", _brl(linha["realizado"]),
              help=f"o que o extrato mostra · origem: {linha['origem']}")
    c2.metric("Ainda vai sair", _brl(a_sair),
              help="custo fixo, folha e não operacional do mês que ainda não "
                   "apareceram no extrato. Sai das grades do Studio, sem "
                   "ninguém digitar nada.")
    c3.metric("Comprometido", _brl(total_comp),
              help="o que já saiu mais o que falta sair. É este o número que "
                   "decide se dá para comprar.")
    if linha["meta"]:
        _saldo = round(linha["meta"] - total_comp, 2)
        _pct = total_comp / linha["meta"] * 100
        c4.metric("Sobra da meta", _brl(_saldo),
                  delta=f"{_pct:.0f}% comprometido", delta_color="inverse")
        st.progress(min(_pct / 100, 1.0),
                    text=f"{_pct:.0f}% da meta comprometida"
                         f" · já saiu {linha['pct']:.0f}%")
    else:
        c4.metric("Sobra da meta", "—")
        st.caption("Sem meta digitada para este mês — a sobra não tem como "
                   "existir. Digite em **Financeiro › 🎯 Meta de gastos**.")
    if _erros_prev:
        st.caption("⚠️ Não consegui ler: " + " · ".join(_erros_prev)
                   + ". O previsto dessas está como zero, e não como "
                     "«não existe».")

    st.markdown(f"**O mês inteiro** · {_brl(total_comp)}")
    st.dataframe(
        pd.DataFrame([{"finalidade": x["finalidade"], "já saiu": x["realizado"],
                       "ainda vai sair": x["falta_sair"],
                       "conta no mês": x["conta"]} for x in combinado]),
        use_container_width=True, hide_index=True,
        column_config={**_rot.config(["finalidade", "valor", "% do mês", "forma", "já saiu", "ainda vai sair", "conta no mês"], st), 
            "já saiu": st.column_config.NumberColumn(format="R$ %.2f"),
            "ainda vai sair": st.column_config.NumberColumn(format="R$ %.2f"),
            "conta no mês": st.column_config.NumberColumn(format="R$ %.2f"),
        })
    st.caption(
        "Custo fixo, folha e não operacional entram **provisionados** desde o "
        "dia 1º, pelas grades do Studio. Quando o débito aparece no extrato, "
        "ele confere o valor — e o que saiu a mais manda. Somar os dois "
        "contaria o mesmo aluguel duas vezes."
    )

    if not lancs:
        st.caption("Nenhum extrato carregado neste mês — acima está só o "
                   "provisionado.")
        return

    # ── 2. onde o dinheiro foi ───────────────────────────────────────────
    FORMAS = {"CHEQUES", "FATURA DO CARTÃO", "BOLETO"}
    por_fin = {k: v for k, v in res.items()
               if k not in FORMAS and k != "SEM CLASSIFICAÇÃO"}
    if por_fin:
        st.markdown(f"**Por finalidade** · {_brl(sum(por_fin.values()))}")
        st.dataframe(
            pd.DataFrame([{"finalidade": k, "valor": v,
                           "% do mês": v / sum(res.values()) * 100}
                          for k, v in por_fin.items()]),
            use_container_width=True, hide_index=True,
            column_config={**_rot.config(["finalidade", "valor", "% do mês", "forma", "já saiu", "ainda vai sair", "conta no mês"], st), 
                "valor": st.column_config.NumberColumn(format="R$ %.2f"),
                "% do mês": st.column_config.ProgressColumn(
                    format="%.1f%%", min_value=0.0,
                    max_value=max(v / sum(res.values()) * 100
                                  for v in por_fin.values())),
            })

    # ── 3. a dívida de trabalho ──────────────────────────────────────────
    formas = {k: v for k, v in res.items() if k in FORMAS}
    if formas:
        st.markdown(f"**Falta abrir** · {_brl(sum(formas.values()))}")
        st.caption(
            "Cheque, fatura e boleto são **como** você pagou, não **o que** "
            "comprou. Enquanto não forem abertos, o valor conta na meta mas "
            "não tem finalidade.")
        st.dataframe(
            pd.DataFrame([{"forma": k, "valor": v} for k, v in formas.items()]),
            use_container_width=True, hide_index=True,
            column_config={**_rot.config(["finalidade", "valor", "% do mês", "forma", "já saiu", "ainda vai sair", "conta no mês"], st), "valor": st.column_config.NumberColumn(
                format="R$ %.2f")})

    sem = res.get("SEM CLASSIFICAÇÃO", 0.0)
    if sem:
        st.warning(
            f"**{_brl(sem)} sem classificação.** Cada nome respondido uma vez "
            f"nunca mais aparece — em **Financeiro › 🏷️ Finalidades**.")

    st.caption("Fora da conta: transferência entre contas, aplicação, entrada "
               "de empréstimo e repasse de plataforma. Nenhum dos quatro é "
               "gasto.")


# ── Os números de verdade ────────────────────────────────────────────────────
#
# DUAS FONTES, CADA UMA NO QUE ELA SABE. É a ordem que o dono deu:
#
#     "ele precisa computar o faturamento em tempo real considerando as vendas
#      que caem no Bling, agora, as demais informações precisa buscar na
#      planilha conforme elas forem sendo atualizadas por nós"
#
# E a razão é dele também: "não temos os custos cadastrados no Bling para que o
# sistema obtenha esses números". O Bling sabe o que VENDEU; quanto cada peça
# custou está na BASE DE VENDAS, digitado por eles.
#
# Os dois faturamentos não vão bater — a planilha é de tempos em tempos, o
# Bling é agora. A tela diz de onde veio cada número, porque número sem origem
# é número que ninguém consegue conferir.

# A meta por quadrimestre, como a planilha dele calcula: percentual sobre o
# faturamento do ano anterior. Os valores estão na aba DINAMICA, no bloco
# "REF. ANO ANTERIOR" — foram LIDOS de lá, não arbitrados aqui.
#
# Ficam no código porque a aba é uma tabela dinâmica, e ler tabela dinâmica por
# fora do Excel devolve o cache dela, não a conta. Quando a meta mudar, muda
# aqui — e é por isso que este comentário diz de onde ela veio.
META_POR_QUADRIMESTRE = {1: 211_283.28, 2: 219_222.19, 3: 250_831.99}


def meta_do_mes(mes):
    """A meta de faturamento daquele mês. None quando não se sabe."""
    try:
        return META_POR_QUADRIMESTRE.get((int(mes) - 1) // 4 + 1)
    except (TypeError, ValueError):
        return None


def _faturamento_bling(ano, mes):
    """(realizado, avisos) — a soma dos dois CNPJs, líquida de cancelados.

    Quem soma as duas contas é `bling_api.faturamento_do_mes_total`, que já
    existe e já trata conta não configurada, erro por conta e o aviso de
    leitura incompleta. Reescrever a soma aqui seria a segunda resposta para a
    mesma pergunta — e duas respostas para a mesma pergunta passam a discordar,
    a questão é só quando.
    """
    try:
        import bling_api as _bl
        total, avisos = _bl.faturamento_do_mes_total(int(ano), int(mes))
    except Exception as e:
        return None, [f"Bling indisponível: {type(e).__name__}"]
    if not total or not total.get("por_conta"):
        return None, avisos or ["Nenhuma conta do Bling respondeu."]
    return float(total.get("liquido") or 0.0), avisos


@st.cache_data(ttl=300, show_spinner=False)
def _partes_fixas(ano, mes):
    """(custo fixo, assinaturas, gerência, headcount, avisos) do mês.

    Cacheada por cinco minutos porque são QUATRO leituras de planilha e esta é
    a tela de entrada do Studio. Sem cache, cada clique na Home pagaria as
    quatro de novo — e foi lentidão de tela que já derrubou sessão aqui.

    Cada parte falha sozinha: planilha de colaboradores fora do ar não pode
    apagar o custo fixo que já foi lido. O que faltar vira aviso, e o aviso
    aparece na tela — número incompleto sem aviso é número errado.
    """
    avisos, cf, assin, ger, head = [], 0.0, 0.0, 0.0, 0.0

    try:
        import previsto as _pv
        cf = _pv._custo_fixo(ano, mes)
    except Exception as e:
        avisos.append(f"Custo fixo não lido ({type(e).__name__}) — "
                      "o equilíbrio está por baixo.")
    try:
        import assinaturas as _as
        assin = _as.total_mensal(_as.carregar())
        if not assin:
            avisos.append("Nenhuma assinatura cadastrada — cadastre em "
                          "**Gestão › Assinaturas** para o equilíbrio ficar "
                          "completo.")
    except Exception as e:
        avisos.append(f"Assinaturas não lidas ({type(e).__name__}).")
    try:
        import ajustes as _aj
        import folha_salarial as _fs
        ger = float(_fs.total_da_folha(_fs.carregar(), ano, mes,
                                       _aj.carregar()) or 0.0)
    except Exception as e:
        avisos.append(f"Folha Gerência não lida ({type(e).__name__}).")
    try:
        import ajustes as _aj2
        import colaboradores as _co
        import custo_time as _ct
        clt = _co.folha_clt(_co.carregar(), ano, mes, _co.carregar_taxas(),
                            _aj2.carregar())
        head = _ct.headcount(clt)["total"]
    except Exception as e:
        avisos.append(f"Folha Headcount não lida ({type(e).__name__}).")

    return cf, assin, ger, head, avisos


@st.cache_data(ttl=300, show_spinner=False)
def _gastos_por_finalidade(ano, mes):
    """({finalidade: total}, aviso) do mês, dos lançamentos já classificados.

    Cacheada à parte das outras leituras porque é a mais cara das quatro: ela
    varre TODOS os lançamentos e filtra pelo mês. `lancamentos.carregar` tem
    cache de 120s, mas o filtro e a aplicação do cadastro rodavam de novo a
    cada clique na Home — e a Home é a tela de entrada do Studio.
    """
    try:
        import lancamentos as _lan
        return _lan.resumo_por_finalidade(_lan.do_mes(ano, mes)), ""
    except Exception as e:
        return {}, (f"Lançamentos do mês não lidos ({type(e).__name__}) — "
                    "o custo operacional ficou de fora da margem.")


def composicao_do_mes(ano, mes, faturamento):
    """(composição, avisos) — o ponto de equilíbrio com os números do cadastro.

    Aqui morava `linhas_de_equilibrio()` sem argumento, que usa as constantes
    chumbadas de 2026. O dono perguntou "quais custos o sistema está
    considerando... se é com base no meu preenchimento" — e não era.
    """
    import composicao as _cp
    import financeiro_equilibrio as _eq

    cf, assin, ger, head, avisos = _partes_fixas(ano, mes)
    resumo, aviso_lan = _gastos_por_finalidade(ano, mes)
    if aviso_lan:
        avisos.append(aviso_lan)

    comp = _cp.montar(resumo, faturamento, _eq.TAXAS_VARIAVEIS,
                      custo_fixo=cf, assinaturas=assin, gerencia=ger,
                      headcount=head,
                      teto_outros=_eq.TETO_OUTROS_PADRAO)
    for nome, valor in comp.get("desconhecidas", [])[:3]:
        avisos.append(
            f"A finalidade **{nome}** (R$ {valor:,.2f}) não está classificada "
            "e ficou FORA da conta. Diga se ela é custo fixo ou variável.")
    if comp.get("numerador_veio_do_extrato"):
        avisos.append(
            "O ponto de equilíbrio está sendo calculado pelo que **saiu da "
            f"conta** (R$ {comp.get('saiu_no_extrato', 0):,.2f}), e não pelos "
            "cadastros — eles somam menos que isso e estão incompletos. "
            "O número está certo; completar os cadastros deixa de depender "
            "de o mês já ter acontecido.")
    return comp, avisos


def _lpv_card(ind, de_onde):
    """O LPV — e ele é o CUSTO FIXO médio por venda, digitado em Financeiro.

    O DEFEITO QUE ELE CORRIGE
    -------------------------
    Este cartão mostrava R$ 82,24 chamando de LPV o lucro bruto ÷ nº de
    vendas. O dono corrigiu na tela: *"Eu não disse que o LPV era o meu custo
    fixo dividido pelo número de vendas?"*. Disse — e está escrito no
    repositório desde antes desta Home existir:

        `financeiro.py:261`     "Informe o LPV que você já calculou"
        `chat_assistente.py:115` "LPV = custo fixo médio por venda"
        `app.py:1533`           a Viabilidade decide com `lpv_vigente`
        `ferramentas_chat.py:210` o assistente responde o mesmo número

    O Studio inteiro concordava com a definição dele. Só esta tela discordava,
    e mostrava outro número sob o mesmo nome — do lado de fora ninguém tem
    como saber qual dos dois está lendo.

    O lucro por venda não se perde: desce para o rodapé do cartão, com o nome
    que ele tem. Dois números com nomes certos informam; um número com o nome
    do outro decide errado.
    """
    valor, origem, atraso = None, "", 0
    try:
        import financeiro as _fin
        _df = _fin.carregar_dados()
        valor, origem = _fin.lpv_vigente(_df)
        atraso = _fin.meses_de_atraso_lpv(_df)
    except Exception:
        # Financeiro fora do ar não derruba os outros cinco cartões.
        valor, origem = None, "Financeiro não respondeu"

    lucro_venda = ind.get("lucro_por_venda")
    rodape = (f'Lucro por venda{de_onde}: <b style="color:var(--ms-texto);">'
              f'{_brl(lucro_venda)}</b>' if lucro_venda else "")

    if valor is None:
        return _card_sem_regua({
            "rotulo": "LPV", "sub": "custo fixo médio por venda · Financeiro",
            "realizado": 0.0, "necessario": None, "fmt": "brl",
            "maior_melhor": False, "acumula": False,
            "rodape": ("Nenhum LPV informado — preencha em "
                       f"Gestão → Financeiro. {rodape}")})

    sub = f"custo fixo médio por venda · Financeiro · {origem}"
    if atraso:
        sub += f" · {atraso} mês(es) atrasado"
    return _card_sem_regua({
        "rotulo": "LPV", "sub": sub, "realizado": valor, "necessario": None,
        "fmt": "brl", "maior_melhor": False, "acumula": False,
        "rodape": rodape})


def dados_reais(ano, mes, dia):
    """O dicionário que `pagina` desenha, montado das fontes de verdade.

    (dados, avisos). `dados` None quando nem a planilha respondeu — aí a tela
    diz o que faltou em vez de mostrar zero, que passaria por dado.
    """
    import base_vendas as _bv
    avisos = []

    # ── TRÊS RELÓGIOS DIFERENTES NA MESMA TELA ───────────────────────────
    #
    # O dono definiu cada um, e misturá-los dá número errado em silêncio:
    #
    #   faturamento  -> Bling, AGORA. A venda cai lá na hora.
    #   lucro/margem -> MÉDIA DOS 3 ÚLTIMOS MESES LANÇADOS na planilha.
    #                   O mês corrente ainda não foi digitado — em 22/09 a
    #                   BASE DE VENDAS ia até agosto —, e mês pela metade não
    #                   descreve o negócio.
    #   gastos       -> o MÊS CORRENTE, dos extratos.
    #
    # A ARMADILHA, e é por isso que `ano`/`mes` continuam sendo os de HOJE:
    # se a Home passasse a dizer que o mês de referência é agosto (que é de
    # onde vêm as margens), o bloco de gastos herdaria agosto — ele lê
    # `d["mes"]` — e o dono olharia gasto de mês fechado achando que é o de
    # agora. O período da média vai num campo PRÓPRIO, e aparece escrito ao
    # lado dos indicadores.
    ind, erro_bv = _bv.media_recente(ano, mes, quantos=3)
    if erro_bv:
        avisos.append(f"BASE DE VENDAS: {erro_bv}")

    fat_bling, avisos_bl = _faturamento_bling(ano, mes)
    avisos.extend(f"Bling: {a}" for a in (avisos_bl or []))

    # O FATURAMENTO DA TELA É O DO BLING QUANDO ELE RESPONDE.
    # Sem ele, o da planilha — e a tela diz que é o da planilha, porque a
    # diferença entre "agora" e "até onde atualizaram" muda a leitura de tudo.
    # UMA FONTE FORA DO AR NÃO DERRUBA A TELA INTEIRA.
    #
    # A Home bebe de TRÊS fontes independentes — Bling, BASE DE VENDAS e os
    # extratos — e recusava desenhar qualquer coisa se uma falhasse. Foi o
    # que aconteceu no ambiente de testes: o Drive não entregou o Controle
    # MS e a tela virou uma caixa vermelha, escondendo o faturamento e o
    # bloco de gastos, que estavam inteiros. Perder um pedaço é perder um
    # pedaço; perder a tela é outra coisa.
    if not ind and fat_bling is None:
        return None, avisos
    if not ind:
        return {"dia": dia, "mes": mes, "ano": ano,
                "fonte_faturamento": "Bling, em tempo real",
                "sem_indicadores": True,
                "faturamento": {"realizado": fat_bling, "meta": 0.0,
                                "operacional": 0.0, "nao_operacional": 0.0},
                "cards": []}, avisos

    realizado = fat_bling if fat_bling is not None else ind["faturamento_liquido"]
    fonte_fat = "Bling, em tempo real" if fat_bling is not None         else "BASE DE VENDAS (o Bling não respondeu)"

    import financeiro_equilibrio as _eq
    comp, avisos_comp = composicao_do_mes(ano, mes, realizado)
    avisos.extend(avisos_comp)

    def _card(rotulo, sub, valor, necessario, fmt, acumula,
              maior_melhor=True, estimado=False):
        return {"rotulo": rotulo, "sub": sub, "realizado": valor,
                "necessario": necessario, "fmt": fmt,
                "maior_melhor": maior_melhor, "acumula": acumula,
                "estimado": estimado}

    # ── A META DE FATURAMENTO ────────────────────────────────────────────
    # Ela não sai dos indicadores da planilha, e sim da META DE GASTOS que o
    # dono cadastra. Por isso é montada aqui e não dentro de `composicao`:
    # são duas perguntas diferentes e elas não podem virar o mesmo número.
    import equilibrio_caixa as _ec
    import meta_gastos as _mg
    try:
        _linha_meta = _mg.linha_do_mes(ano, mes)
        _meta_gastos = _linha_meta.get("meta", 0.0)
    except Exception as e:
        _meta_gastos = 0.0
        avisos.append(f"Meta de gastos: {str(e)[:100]}")
    quadro_meta, _av_meta = _ec.montar(_meta_gastos, ind.get("somas"),
                                       realizado, dias_mes=None)
    avisos.extend(_av_meta or [])

    _mb = ind["margem_bruta"]
    _ml = ind["margem_contribuicao_pct"]

    _periodo_curto = ind.get("periodo", "") or "período lançado"
    _sub_media = f"média de {_periodo_curto}"
    # A ORIGEM VAI NO CARTAO, NAO SO NO RODAPE.
    #
    # "De onde saiu esse LPV de R$ 82,24? Que conta foi feita?" — perguntado
    # olhando para a tela. A conta esta em `base_vendas.py:188`, e o rodape
    # dizia apenas que o numero vem da BASE DE VENDAS. Qual conta, nao dizia.
    # Numero sem conta escrita e numero que ninguem confere sozinho.
    _de = f" · BASE DE VENDAS · {_periodo_curto}"
    # ── O QUE DÁ PARA SABER DO MÊS CORRENTE ──────────────────────────────
    #
    # A planilha só recebe o mês depois que ele acaba, e o dono disse que o
    # preenchimento diário "provavelmente não teremos". Então o mês corrente
    # é ESTIMADO: a margem dos meses fechados aplicada ao faturamento que o
    # Bling já sabe. Estimado sai escrito na tela — número que parece medido
    # e não é, é o que faz decisão errada.
    _lucro_estimado = round(realizado * (_mb or 0.0) / 100.0, 2)
    _sub_estimado = (f"faturado de agora × margem bruta de {_periodo_curto}"
                     if _mb else _sub_media)

    # As devoluções do mês vêm da aba `devolucoes`, preenchida no dia a dia —
    # esta é a única do bloco que é MEDIDA e não estimada. Sem a aba (ou
    # antes de alguém cadastrar), cai na média dos meses fechados.
    _dev_valor, _sub_dev = ind["devolucao"], f"média de {_periodo_curto}"
    try:
        import devolucoes as _dv
        _do_mes = _dv.do_mes(_dv.carregar(), f"{ano:04d}-{mes:02d}")
        if _do_mes:
            _dev_valor = _dv.resumo(_do_mes)["valor"]
            _sub_dev = f"medido no mês · {len(_do_mes)} devolução(ões)"
    except Exception as e:
        avisos.append(f"Devoluções: {str(e)[:100]}")

    # O TETO, e não um piso: devolver menos é melhor. 3% do faturado é a
    # régua que o dono citou; em jan–ago/2026 o real foi 2,54%.
    _dev_teto = round(realizado * TETO_DEVOLUCAO_PCT / 100.0, 2) or None
    return {
        # HOJE — e é isto que o bloco de gastos e o ritmo do faturamento usam.
        "dia": dia, "mes": mes, "ano": ano,
        "fonte_faturamento": fonte_fat,
        # O período da MÉDIA, que é outro. Ele existe para o número não ficar
        # sem origem: "margem de 70%" sem dizer de quando não dá para conferir.
        "periodo_indicadores": ind.get("periodo", ""),
        "meses_na_media": ind.get("meses", 0),
        "linhas_base_vendas": ind.get("linhas", 0),
        "faturamento": {
            "realizado": realizado,
            # A META É A META DE GASTOS DIVIDIDA PELO QUE CAI NA CONTA.
            #
            # Ditada pelo dono: "se eu coloquei como meta de gastos 170k…
            # tenho os custos fixos, cheques, os parciais dos cartões… o que
            # ainda será gasto consumirá da meta". A meta de gastos é TUDO o
            # que sai no mês, então a pergunta é de CAIXA, e o divisor é a
            # fatia do faturamento que sobrevive até o banco — 65,2% em
            # jun–ago/2026, depois de comissão, frete, NF e devolução.
            #
            # A conta anterior dividia pela margem de contribuição do
            # cadastro e devolvia R$ 34.865 num mês de R$ 270 mil faturados:
            # a tela dizia "R$ 151 mil acima do ritmo" quando o certo era
            # R$ 18 mil ABAIXO. Era essa leitura que decidia comprar.
            "meta": (quadro_meta or {}).get("meta") or 0.0,
            "taxa_de_entrada": (quadro_meta or {}).get("taxa_de_entrada"),
            "descontos": (quadro_meta or {}).get("descontos") or [],
            "meta_de_gastos": (quadro_meta or {}).get("meta_de_gastos") or 0.0,
            # O equilíbrio do cadastro continua vindo junto, agora como
            # SEGUNDA leitura e com nome próprio. Ele responde outra
            # pergunta — quanto custa operar — e some se for apagado daqui.
            "operacional": comp.get("equilibrio_hoje") or 0.0,
            "nao_operacional": comp.get("equilibrio_de_caixa") or 0.0,
        },
        "equilibrio": comp,
        "cards": [
            # ESTIMADO: a margem dos meses fechados aplicada ao faturamento
            # de AGORA. A planilha só recebe o mês corrente depois que ele
            # acaba; sem isto o cartão mostraria a média de três meses
            # atrás com cara de "hoje".
            _card("Lucro bruto", _sub_estimado, _lucro_estimado,
                  None, "brl0", False, estimado=True),
            # A régua daqui era a margem de CONTRIBUIÇÃO (29%) comparada
            # com a margem BRUTA (75%): "46 p.p. acima do necessário", com
            # duas réguas diferentes. Margem bruta não tem meta própria.
            _card("Margem bruta", "lucro bruto ÷ faturado líquido" + _de,
                  _mb or 0.0, None, "pct", False),
            _lpv_card(ind, _de),
            # O necessário é a margem REAL do mês — a medida em 17.793
            # vendas MENOS o custo operacional que ela não conhece. Comparar
            # com os 29,82% puros dizia "está acima do necessário" enquanto a
            # conta do mês não fechava.
            _card("Margem de contribuição",
                  "margem de contribuição ÷ faturado líquido" + _de, _ml or 0.0,
                  (comp.get("margem") or _eq.margem_de_contribuicao()) * 100.0,
                  "pct", False),
            # DEVOLVER MAIS É PIOR. O cartão estava marcado como "maior é
            # melhor": com uma régua de verdade, ele ficaria verde no mês em
            # que mais produto voltou.
            _card("Devoluções", _sub_dev, _dev_valor, _dev_teto, "brl0",
                  False, maior_melhor=False),
            _card("UC", "unidades ÷ nº de vendas" + _de,
                  ind["uc"] or 0.0, None, "razao", False),
        ],
    }, avisos


def pagina(usuario_logado=None, dados=None):
    st.markdown("### 🏠 Home")
    # O QUE A TELA MOSTRA, E NAO POR QUE ELA EXISTE.
    #
    # Aqui havia tres linhas explicando a filosofia do painel — "o ponto de
    # equilibrio vem primeiro, meta e consequencia dele". Isso e apresentacao,
    # e quem abre a tela ja sabe. A legenda diz o que o grafico mede.
    st.caption("Faturamento do mês contra o ponto de equilíbrio e a meta.")

    # OS NÚMEROS DE VERDADE, sem ninguém pedir.
    #
    # A tela nasceu com dados de exemplo, para aprovar o layout, e o layout foi
    # aprovado há tempo. Manter o exemplo depois disso é pior do que não ter
    # tela: o número inventado é plausível, fica bonito ao lado dos outros, e
    # alguém decide em cima dele.
    _avisos = []
    if dados is None:
        import placar_core as _pc
        _agora = datetime.now(_pc.FUSO)
        with st.spinner("Lendo o Bling e a BASE DE VENDAS…"):
            dados, _avisos = dados_reais(_agora.year, _agora.month, _agora.day)

    if dados is None:
        st.error(
            "**Não consegui montar os indicadores.** Eles vêm do Bling (o "
            "faturamento de agora) e da aba BASE DE VENDAS do Controle MS "
            "(lucro, margem e UC). Enquanto uma das duas não responde, a "
            "tela prefere não mostrar número nenhum a mostrar um número que "
            "parece certo.")
        for _a in (_avisos or []):
            st.caption(f"· {_a}")
        return

    d = dados

    if d.get("sem_indicadores"):
        st.warning(
            "**Os indicadores estão fora do ar, o resto não.** Lucro, margem, "
            "UC e a meta de faturamento vêm da aba BASE DE VENDAS do "
            "Controle MS, e ela não respondeu. O faturamento de agora e o "
            "bloco de gastos continuam valendo.")
        for _a in (_avisos or []):
            st.caption(f"· {_a}")
        st.metric("Faturado no mês", _brl(d["faturamento"]["realizado"], 0))
        st.markdown("---")
        _bloco_gastos(usuario_logado, d)
        return

    _, _, _, dia, dias = ritmo(d)
    _bloco_faturamento(d)

    st.markdown('<div style="height:10px;"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="display:grid;grid-template-columns:repeat(3,1fr);'
        'gap:10px;">'
        + "".join(_card(c, dia, dias) for c in d["cards"])
        + '</div>',
        unsafe_allow_html=True)

    # DE ONDE VEIO CADA NÚMERO. Sem isto, os dois faturamentos que não batem
    # viram uma discussão sem saída — a planilha é de tempos em tempos, o
    # Bling é agora, e os dois estão certos no que cada um mede.
    if d.get("fonte_faturamento"):
        _per = d.get("periodo_indicadores") or ""
        _n = d.get("meses_na_media") or 0
        st.caption(
            f"**Faturamento:** {d['fonte_faturamento']}.  \n"
            f"**Lucro, margem e UC:** média de "
            f"{_n} mês(es) — **{_per}** — da aba BASE DE VENDAS do Controle MS"
            + (f", {d['linhas_base_vendas']} venda(s)"
               if d.get("linhas_base_vendas") else "")
            + ". O mês corrente ainda não foi lançado lá; um mês pela metade "
              "não descreve o negócio.  \n"
            "**LPV:** o custo fixo médio por venda que você digita em "
            "Gestão → Financeiro — não sai da BASE DE VENDAS.  \n"
            f"**Gastos:** o mês corrente, dos extratos — o bloco abaixo.")
    for _a in (_avisos or []):
        st.warning(_a)

    st.caption(
        f"Mês de referência {d['mes']:02d}/{d['ano']}, fechado no dia "
        f"{dia} de {dias}. O **ritmo** reparte a meta em partes iguais pelos "
        "dias corridos do mês, e a **projeção** é o ritmo médio vezes os "
        "dias do mês — um método só, porque duas projeções discordando na "
        "mesma tela não informam, escolhem por você.")

    _bloco_gastos(usuario_logado, d)


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import inspect
    s_home = open(__file__, encoding="utf-8").read()
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
    # A meta ilustrada tem que ser COERENTE com a conta nova, senao o
    # exemplo ensina errado quem abre o arquivo para entender a tela.
    ok("no exemplo, meta = meta de gastos ÷ taxa de entrada",
       abs(EXEMPLO["faturamento"]["meta"]
           - EXEMPLO["faturamento"].get("meta_de_gastos", 0.0)
           / (EXEMPLO["faturamento"].get("taxa_de_entrada") or 1)) < 1.0)

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
    # `agora` entra de fora para o teste nao depender do relogio — sem ele a
    # fracao do mes seria a de hoje e a conferencia daria resultado diferente
    # a cada execucao, que e o teste que nao serve para nada.
    from datetime import datetime as _dt
    import equilibrio_caixa as _eq_c
    _MEIO = _dt(2026, 9, 14, 12, 0, tzinfo=_eq_c.FUSO)     # dia 14, meio-dia
    _EX = dict(EXEMPLO, agora=_MEIO)
    _alvo, _dia_a_dia, _proj, _dia, _dias = ritmo(_EX)
    ok("setembro tem 30 dias", _dias == 30)
    # 13 dias fechados + meio dia = 13,5/30, e NAO 14/30. A diferenca e meio
    # dia de meta que a tela cobrava antes de o dia acontecer.
    _f = (13 + 0.5) / 30
    _meta_ex = EXEMPLO["faturamento"]["meta"]
    ok("o ritmo do dia 14 ao meio-dia é 13,5/30 da meta",
       abs(_alvo - _meta_ex * _f) < 0.01)
    ok("e NAO é 14/30 — isso cobrava o dia inteiro logo que ele comecava",
       abs(_alvo - _meta_ex * 14 / 30) > 1_000)
    ok("o ritmo médio é o faturado dividido pelos dias corridos",
       abs(_dia_a_dia - 148_320 / 14) < 0.01)
    ok("a projeção é o realizado esticado pela fração do mês",
       abs(_proj - 148_320 / _f) < 0.01)
    _FIM = _dt(2026, 9, 30, 23, 59, 59, tzinfo=_eq_c.FUSO)
    ok("no último instante do mês, o alvo encontra a meta",
       abs(ritmo(dict(EXEMPLO, dia=30, agora=_FIM))[0] - _meta_ex) < 60)
    ok("e a projeção encontra o realizado",
       abs(ritmo(dict(EXEMPLO, dia=30, agora=_FIM))[2] - 148_320) < 60)
    ok("um dia além do fim do mês não estica a projeção",
       abs(ritmo(dict(EXEMPLO, dia=44, agora=_FIM))[2] - 148_320) < 60)

    # O que ACUMULA se estica; o que ja e media fecha onde esta. Esticar uma
    # razao pelo tempo daria um numero sem significado.
    ok("o lucro em R$ se estica pelos dias que faltam",
       abs(projetar(102_340.80, 14, 30, True) - 102_340.80 / 14 * 30) < 0.01)
    ok("a margem em % fecha onde está",
       projetar(69.0, 14, 30, False) == 69.0)
    ok("só os lucros em R$ acumulam",
       [c["rotulo"] for c in EXEMPLO["cards"] if c["acumula"]]
       == ["Lucro bruto", "Lucro líquido"])

    # As tres cores sao ESTADO: cada barra mostra uma so, e sempre com frase.
    ok("as três cores de estado são distintas",
       len({VERDE, AMARELO, VERMELHO}) == 3)

    # ── A meta por quadrimestre, como a planilha dele calcula ────────────
    ok("janeiro a abril sao o 1o quadrimestre",
       all(meta_do_mes(m) == 211_283.28 for m in (1, 2, 3, 4)))
    ok("maio a agosto, o 2o",
       all(meta_do_mes(m) == 219_222.19 for m in (5, 6, 7, 8)))
    ok("setembro a dezembro, o 3o",
       all(meta_do_mes(m) == 250_831.99 for m in (9, 10, 11, 12)))
    ok("mes que nao existe nao inventa meta", meta_do_mes(13) is None)
    ok("nem texto", meta_do_mes("setembro") is None)

    # ── OS TRES RELOGIOS NAO PODEM SE MISTURAR ───────────────────────────
    #
    # A Home usa a media dos 3 ultimos meses LANCADOS para lucro e margens,
    # mas `ano`/`mes` tem de continuar sendo os de HOJE: o bloco de gastos le
    # `d["mes"]`, e se ele herdasse o mes da media o dono olharia gasto de mes
    # fechado achando que e o de agora — numero errado em silencio, que e o
    # erro mais caro que existe nesta tela.
    import ast as _ast_home
    _fonte_home = open(__file__, encoding="utf-8").read()
    _arv_home = _ast_home.parse(_fonte_home)
    _dr = next(n for n in _ast_home.walk(_arv_home)
               if isinstance(n, _ast_home.FunctionDef) and n.name == "dados_reais")
    _chaves = set()
    for _n in _ast_home.walk(_dr):
        if isinstance(_n, _ast_home.Dict):
            for _k in _n.keys:
                if isinstance(_k, _ast_home.Constant) and isinstance(_k.value, str):
                    _chaves.add(_k.value)
    ok("a Home devolve dia/mes/ano, que sao os de HOJE",
       {"dia", "mes", "ano"} <= _chaves)
    ok("e o periodo da media vai num campo PROPRIO, separado",
       "periodo_indicadores" in _chaves and "meses_na_media" in _chaves)

    # `dados_reais` pede a MEDIA, e nao um mes so.
    _corpo = _fonte_home[_fonte_home.index("def dados_reais"):
                         _fonte_home.index("def pagina(")]
    ok("os indicadores vem da media recente", "media_recente" in _corpo)
    ok("e nao de um mes solto", "_bv.do_mes(" not in _corpo)

    # O bloco de gastos continua no mes de hoje.
    _bg = _fonte_home[_fonte_home.index("def _bloco_gastos"):]
    # ── A META E O PONTO DE EQUILIBRIO, E ELE VEM DO CADASTRO ───────────
    #
    # O defeito: `linhas_de_equilibrio()` sem argumento usa as constantes
    # chumbadas de 2026. O que o dono cadastra nao chegava a conta.
    _corpo_dr = inspect.getsource(dados_reais)
    ok("a Home nao usa mais as constantes de equilibrio",
       "linhas_de_equilibrio()" not in _corpo_dr)
    ok("ela monta a composicao do mes", "composicao_do_mes(" in _corpo_dr)
    # A META DE FATURAMENTO SAI DA META DE GASTOS, e nao mais da margem de
    # contribuicao do cadastro. A conta velha devolvia R$ 34.865 num mes de
    # R$ 270 mil faturados, e a tela dizia "R$ 151 mil acima do ritmo"
    # quando o certo era R$ 18 mil ABAIXO. Se alguem religar a meta na
    # composicao, esta linha reprova.
    ok("a meta vem da meta de gastos cadastrada",
       "meta_gastos" in _corpo_dr and "linha_do_mes(" in _corpo_dr)
    ok("dividida pelo que cai na conta", "equilibrio_caixa" in _corpo_dr)
    ok("e NAO mais pela margem de contribuicao do cadastro",
       '"meta": comp.get("equilibrio' not in _corpo_dr)
    # O equilibrio do cadastro continua vindo — como SEGUNDA leitura, nao
    # como meta. Apagar isto tiraria da tela quanto custa operar.
    ok("o equilibrio do cadastro continua na tela, com nome proprio",
       "composicao_do_mes(" in _corpo_dr and "operacional" in _corpo_dr)

    # ── CARTAO SEM REGUA NAO DA VEREDITO ────────────────────────────────
    #
    # Quatro cartoes passavam o proprio valor como "necessario" e diziam
    # "acima do necessario" para sempre. Eram dados de exemplo que ficaram.
    _corpo_cards = inspect.getsource(dados_reais)
    ok("nenhum cartao usa o proprio valor como regua",
       'ind["lucro_bruto"],\n                  ind["lucro_bruto"]' not in _corpo_cards
       and 'ind["uc"] or 0.0, ind["uc"] or 0.0' not in _corpo_cards
       and 'ind["lpv"] or 0.0,\n                  ind["lpv"] or 0.0' not in _corpo_cards)
    ok("devolver MAIS nao conta como bom",
       "maior_melhor=False" in _corpo_cards)
    ok("o lucro do mes corrente sai marcado como estimado",
       "estimado=True" in _corpo_cards)
    ok("e a regua de devolucao e um TETO sobre o faturado",
       "TETO_DEVOLUCAO_PCT" in _corpo_cards)

    _sem = {"rotulo": "LPV", "sub": "x", "realizado": 84.73,
            "necessario": None, "fmt": "brl", "maior_melhor": True,
            "acumula": False}
    _html = _card(_sem, 14, 30)
    ok("cartao sem regua nao desenha barra nem veredito",
       "necessário" not in _html.lower() and "✔" not in _html)
    ok("mas mostra o numero", "84,73" in _html)
    ok("e diz que nao ha meta", "Sem meta definida" in _html)
    ok("com 'estimado', a palavra aparece no cartao",
       "estimado" in _card(dict(_sem, estimado=True), 14, 30))

    # CARTAO DE TETO SE LE AO CONTRARIO. Devolucao de R$ 4.429 contra um teto
    # de R$ 5.359 esta ABAIXO do teto — e a tela dizia "acima do necessario".
    _teto = {"rotulo": "Devoluções", "sub": "x", "realizado": 4_429.10,
             "necessario": 5_359.00, "fmt": "brl0", "maior_melhor": False,
             "acumula": False}
    _h = _card(_teto, 23, 30)
    ok("dentro do teto, o cartao diz ABAIXO do teto",
       "abaixo do teto" in _h and "acima do necessário" not in _h)
    ok("e chama a regua de Teto, nao de Necessario",
       "Teto" in _h and "Necessário" not in _h)
    _h2 = _card(dict(_teto, realizado=9_000.0), 23, 30)
    ok("passando do teto, ele grita", "ACIMA DO TETO" in _h2)
    ok("e fica vermelho", VERMELHO in _h2)

    # UMA FONTE FORA DO AR NAO DERRUBA A TELA. No ambiente de testes o Drive
    # nao entregou o Controle MS e a Home virou uma caixa vermelha, escondendo
    # o faturamento e o bloco de gastos, que estavam inteiros.
    _dr = inspect.getsource(dados_reais)
    ok("sem BASE DE VENDAS, a tela ainda entrega o que tem",
       '"sem_indicadores": True' in _dr)
    ok("so devolve None quando as DUAS fontes falham",
       "if not ind and fat_bling is None:" in _dr)
    _pg = inspect.getsource(pagina)
    ok("e a pagina desenha os gastos mesmo sem indicadores",
       'd.get("sem_indicadores")' in _pg and "_bloco_gastos(" in _pg)

    _corpo_cp = inspect.getsource(composicao_do_mes)
    ok("a composicao le o custo fixo, as assinaturas e as duas folhas",
       "_partes_fixas(" in _corpo_cp)
    # O resumo por finalidade saiu daqui para uma funcao cacheada a parte —
    # e a mais cara das quatro leituras, e rodava a cada clique na Home.
    ok("e os gastos por finalidade do mes",
       "_gastos_por_finalidade(" in _corpo_cp)
    ok("que sao lidos uma vez e guardados",
       "cache_data" in s_home.split("def _gastos_por_finalidade")[0][-200:])
    ok("finalidade nao classificada vira aviso, e nao some",
       "desconhecidas" in _corpo_cp)

    _corpo_pf = inspect.getsource(_partes_fixas)
    ok("cada leitura de planilha falha sozinha",
       _corpo_pf.count("except Exception") >= 4)
    ok("e a que falha vira aviso", _corpo_pf.count("avisos.append") >= 4)
    ok("as quatro leituras sao cacheadas",
       "cache_data" in s_home.split("def _partes_fixas")[0][-200:])

    ok("os gastos continuam saindo do mes de referencia da Home",
       'd or {}).get("mes")' in _bg)

    # ── DOIS ROTULOS NO MESMO PONTO NAO INFORMAM NENHUM DOS DOIS ────────
    #
    # Em 25/09 a tela imprimiu "▲ Nãopoperacionall": Operacional e Não
    # operacional caem no MESMO x sempre que o mes nao tem PRONAMP
    # classificado, e um foi impresso por cima do outro.
    _r_junto = _rotulos([(14.5, "Operacional"), (14.5, "Não operacional"),
                         (94.3, "Meta")])
    ok("dois marcadores no mesmo ponto viram UM rótulo",
       _r_junto.count("<span") == 2)
    ok("e a frase mostra os dois nomes",
       "Operacional = Não operacional" in _r_junto)
    ok("o ▲ aparece uma vez por rótulo, e não por nome",
       _r_junto.count("▲") == 2)
    _r_longe = _rotulos([(10.0, "Operacional"), (40.0, "Não operacional"),
                         (90.0, "Meta")])
    ok("marcadores separados continuam separados",
       _r_longe.count("<span") == 3 and " = " not in _r_longe)
    ok("rótulo no fim da régua não transborda",
       "translateX(-100%)" in _rotulos([(97.0, "Meta")]))
    ok("nem no começo", "translateX(0)" in _rotulos([(1.0, "Meta")]))
    ok("e no meio ele continua centrado",
       "translateX(-50%)" in _rotulos([(50.0, "Meta")]))

    # E O RODAPE EXPLICA A COINCIDENCIA, em vez de repetir o numero duas
    # vezes como se fosse erro de leitura.
    _txt = _as_duas_linhas(40_834.0, 40_834.0, {"equilibrio": {"segunda_linha": 0.0}})
    ok("coincidindo, o rodapé diz que coincidem e por quê",
       "coincidem" in _txt and "PRONAMP" in _txt)
    ok("diferentes, ele mostra os dois números",
       _as_duas_linhas(131_918.0, 183_940.0).count("R$") == 2)

    # ── ONDE O MES FECHA CONTRA A META ──────────────────────────────────
    #
    # A tela dizia "fecha em R$ 233.725" e deixava a subtracao para quem le.
    _abaixo = _projecao_contra_a_meta(233_725.0, 265_542.0, VERMELHO)
    ok("abaixo da meta, a distância sai escrita",
       "31.817" in _abaixo and "abaixo da meta" in _abaixo)
    ok("e com a seta para baixo", "▼" in _abaixo and "▲" not in _abaixo)
    _acima = _projecao_contra_a_meta(280_000.0, 265_542.0, VERDE)
    ok("acima, o texto inverte", "acima da meta" in _acima and "▲" in _acima)
    ok("sem meta, não inventa comparação",
       _projecao_contra_a_meta(200_000.0, 0.0, VERDE) == "")

    # ── A TELA NAO SE APRESENTA, ELA MEDE ───────────────────────────────
    ok("a legenda não explica a filosofia do painel",
       "ponto de equilíbrio vem primeiro" not in _pg)
    # A BUSCA E NO BLOCO, NAO NO ARQUIVO INTEIRO — senao a guarda encontra o
    # proprio literal que ela procura e passa sozinha. Ja aconteceu tres
    # vezes nesta base; o CLAUDE.md registra as tres.
    _bf = inspect.getsource(_bloco_faturamento)
    ok("o cabeçalho não diz mais o dia corrido ao lado do valor",
       ("faturado at" + "é o dia") not in _bf)
    ok("ele diz que o faturamento é de agora",
       "Faturamento em tempo real" in _bf)
    ok("e o veredito da projeção está acentuado",
       ("nao bate" + " a meta") not in _bf and "não bate a meta" in _bf)

    # ── CADA CARTAO CARREGA A CONTA E A FONTE ───────────────────────────
    #
    # "De onde saiu esse LPV de R$ 82,24? Que conta foi feita?" — a resposta
    # esta em `base_vendas.py:188` e agora esta tambem no cartao.
    # (O LPV saiu desta lista: ele nao e uma razao da BASE DE VENDAS. Ver o
    # bloco proprio dele, logo abaixo.)
    ok("a margem de contribuição diz a conta dela",
       "margem de contribuição ÷ faturado líquido" in _corpo_cards)
    ok("e a margem bruta", "lucro bruto ÷ faturado líquido" in _corpo_cards)
    ok("o UC idem", "unidades ÷ nº de vendas" in _corpo_cards)
    ok("os três dizem de que aba e de que período vêm",
       _corpo_cards.count("+ _de") == 3 and "BASE DE VENDAS · " in _corpo_cards)

    # ── O LPV E O CUSTO FIXO POR VENDA, E SO ELE ────────────────────────
    #
    # A Home mostrava R$ 82,24 — lucro bruto ÷ vendas — com o nome LPV.
    # O dono: "Eu nao disse que o LPV era o meu custo fixo dividido pelo
    # numero de vendas?". Disse, e esta no repositorio desde antes desta
    # tela: financeiro.py:261, chat_assistente.py:115, app.py:1533.
    _corpo_lpv = inspect.getsource(_lpv_card)
    ok("o cartão de LPV lê o Financeiro", "lpv_vigente(" in _corpo_lpv)
    ok("e NÃO o lucro por venda da BASE DE VENDAS",
       'ind["lucro_por_venda"]' not in _corpo_cards
       and ("ind[" + '"lpv"]') not in _corpo_cards)
    ok("ele diz que é custo fixo por venda",
       "custo fixo médio por venda" in _corpo_lpv)
    ok("diz de que mês o LPV veio", "origem" in _corpo_lpv)
    ok("e avisa quando ele está atrasado",
       "meses_de_atraso_lpv(" in _corpo_lpv and "atrasado" in _corpo_lpv)
    ok("o lucro por venda não some — desce para o rodapé",
       "Lucro por venda" in _corpo_lpv)
    # O Financeiro fora do ar nao pode derrubar os outros cinco cartoes.
    ok("sem Financeiro, o cartão ainda aparece e diz o que fazer",
       "except Exception" in _corpo_lpv
       and "Gestão → Financeiro" in _corpo_lpv)
    _fake = {"lucro_por_venda": 82.24}
    import financeiro as _fin_t
    _guardado = _fin_t.lpv_vigente
    _fin_t.lpv_vigente = lambda *a, **k: (19.68, "Junho/2026")
    _fin_t.meses_de_atraso_lpv = lambda *a, **k: 3
    _fin_t.carregar_dados = lambda: None
    _h_lpv = _lpv_card(_fake, " · BASE DE VENDAS · jun-ago/2026")
    _fin_t.lpv_vigente = _guardado
    ok("o número grande do cartão é o LPV do Financeiro",
       "19,68" in _h_lpv)
    ok("e os R$ 82,24 aparecem como LUCRO por venda, no rodapé",
       "82,24" in _h_lpv and "Lucro por venda" in _h_lpv)
    ok("o atraso do LPV sai escrito", "3 mês(es) atrasado" in _h_lpv)

    # A legenda do rodape nao pode continuar dizendo que o LPV vem da
    # BASE DE VENDAS — era ela que sustentava o numero errado.
    ok("o rodapé da página não atribui mais o LPV à BASE DE VENDAS",
       ("Lucro, margem, " + "LPV e UC") not in _pg)
    ok("e diz onde o LPV mora", "Gestão → Financeiro" in _pg)

    print("\nfalhas:", falhas)
