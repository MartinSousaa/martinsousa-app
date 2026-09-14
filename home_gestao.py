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
As três cores são estado, não identidade: verde acima do necessário, amarelo na
faixa da projeção, vermelho abaixo. Toda barra carrega o veredito **escrito** ao
lado — quem não distingue as cores lê a frase. O vermelho do Studio tem 2,79:1
de contraste no fundo escuro, abaixo dos 3:1: é por isso que o texto nunca
depende dele.

O PONTO DE EQUILÍBRIO VEM PRIMEIRO
----------------------------------
Foi decisão do gestor: "meta de faturamento é secundário, o principal é
alcançarmos o ponto de equilíbrio". Por isso o faturamento ocupa a tela inteira
no topo, com as DUAS linhas — a operação se paga, e a operação se paga E as
parcelas saem —, a meta do mês e o ritmo do dia; os outros seis vêm embaixo.

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
        "projecao": 241_800.00, "piso": 212_400.00, "teto": 272_300.00,
        "operacional": 131_918.00, "caixa": 183_940.00,
    },
    # Três por linha: bruto em cima, líquido embaixo, e cada valor em R$ ao
    # lado da sua própria margem em %. O mesmo fato lido nas duas unidades.
    "cards": [
        {"rotulo": "Lucro bruto", "sub": "no mês",
         "realizado": 71_190.00, "necessario": 68_400.00, "fmt": "brl0",
         "maior_melhor": True},
        {"rotulo": "Margem bruta", "sub": "sobre o faturado",
         "realizado": 48.0, "necessario": 46.1, "fmt": "pct",
         "maior_melhor": True},
        {"rotulo": "LPV", "sub": "lucro por venda",
         "realizado": 42.10, "necessario": 48.00, "fmt": "brl",
         "maior_melhor": True},
        {"rotulo": "Lucro líquido", "sub": "no mês",
         "realizado": 18_460.00, "necessario": 24_900.00, "fmt": "brl0",
         "maior_melhor": True},
        {"rotulo": "Margem líquida", "sub": "sobre o faturado",
         "realizado": 12.4, "necessario": 16.8, "fmt": "pct",
         "maior_melhor": True},
        {"rotulo": "UC", "sub": "custo unitário",
         "realizado": 21.60, "necessario": 19.80, "fmt": "brl",
         "maior_melhor": False},
    ],
}


def _fmt(valor, como):
    if como == "pct":
        return _num(valor, 1, "%")
    if como == "brl0":
        return _brl(valor, 0)
    return _brl(valor)


def ritmo(d):
    """Meta gradual: quanto da meta o mês já deveria ter entregue até hoje.

    Reparte a meta em partes iguais pelos dias CORRIDOS do mês — é o dia do
    calendário que faz o cheque vencer, não o dia útil. A curva de venda não é
    reta (o mês tem picos), mas fingir uma curva sem ter a medida seria pior
    que a reta honesta: quando `financeiro_historico` entregar a curva medida,
    troca-se esta função e a tela não muda.
    """
    f = d["faturamento"]
    dias = int(d.get("dias_mes") or calendar.monthrange(d["ano"], d["mes"])[1])
    dia = min(max(int(d["dia"]), 0), dias)
    return f.get("meta", 0.0) * dia / (dias or 1), dia, dias


def _bloco_faturamento(d):
    """O faturamento contra o equilíbrio, a meta do mês e a meta do dia.

    Duas linhas de equilíbrio e não uma: os PRONAMPs saem do caixa mas não são
    custo de operar, e incluir ou não muda a resposta em R$ 52 mil. Em vez de
    escolher pelo gestor, a barra mostra as duas e diz onde a projeção caiu.

    Duas trilhas empilhadas na MESMA escala: em cima o realizado, embaixo o
    ritmo — o pedaço da meta que os dias já consumiram. Comparar comprimento
    de barra é mais barato para o olho que comparar dois números escritos.
    """
    f = d["faturamento"]
    proj, op, cx = f["projecao"], f["operacional"], f["caixa"]
    meta, real = f.get("meta", 0.0), f["realizado"]
    if proj >= cx:
        cor_proj, veredito = VERDE, "fecha acima das duas linhas"
    elif proj >= op:
        cor_proj, veredito = AMARELO, "paga a operação, mas não as parcelas"
    else:
        cor_proj, veredito = VERMELHO, "fecha abaixo do equilíbrio operacional"

    alvo_hoje, dia, dias = ritmo(d)
    if real >= alvo_hoje:
        cor, frase = VERDE, "acima do ritmo"
    elif real >= alvo_hoje * 0.92:
        cor, frase = AMARELO, "quase no ritmo"
    else:
        cor, frase = VERMELHO, "abaixo do ritmo"
    dif = abs(real - alvo_hoje)

    escala = max(proj, cx, meta, f["teto"]) * 1.10 or 1
    x = lambda v: min(max(v / escala * 100, 0), 100)
    rot = ('font-size:10px;color:var(--ms-texto-sec);text-align:right;'
           'white-space:nowrap;')

    st.markdown(
        f'<div style="background:var(--ms-metric-bg);'
        f'border:1px solid var(--ms-metric-bd);border-radius:12px;'
        f'padding:16px 18px 12px;">'

        f'<div style="font-size:11px;color:var(--ms-texto-sec);'
        f'text-transform:uppercase;letter-spacing:.6px;">'
        f'Faturamento × ponto de equilíbrio × meta</div>'

        f'<div style="display:flex;align-items:baseline;gap:12px;'
        f'flex-wrap:wrap;margin-top:6px;">'
        f'<span style="font-size:40px;font-weight:700;color:var(--ms-texto);'
        f'line-height:1;">{_brl(real, 0)}</span>'
        f'<span style="font-size:12px;color:var(--ms-texto-sec);">'
        f'faturado até o dia {dia} de {dias}</span>'
        f'<span style="margin-left:auto;font-size:12px;'
        f'color:var(--ms-texto-sec);">projeção de fechamento '
        f'<b style="color:var(--ms-texto);">{_brl(proj, 0)}</b></span></div>'

        # Duas trilhas na mesma escala, com rótulo à esquerda: o que a coluna
        # da direita mede é sempre o mesmo eixo de R$ faturado no mês.
        f'<div style="display:grid;grid-template-columns:96px 1fr;'
        f'gap:6px 10px;align-items:center;margin-top:16px;">'

        f'<div style="{rot}font-weight:700;color:var(--ms-texto);">realizado</div>'
        f'<div style="height:18px;border-radius:9px;'
        f'background:var(--ms-metric-bd);position:relative;">'
        f'<div style="position:absolute;left:0;top:0;height:100%;'
        f'width:{x(real):.1f}%;background:{cor};border-radius:9px;"></div>'
        # A faixa piso-teto: a projeção tem erro medido, e fingir um ponto
        # exato seria inventar precisão que o método não tem.
        f'<div style="position:absolute;top:3px;height:12px;'
        f'left:{x(f["piso"]):.1f}%;width:{x(f["teto"]) - x(f["piso"]):.1f}%;'
        f'border:2px dashed var(--ms-texto-sec);border-radius:7px;'
        f'opacity:.75;"></div>'
        + _marcador(x(op), "operacional")
        + _marcador(x(cx), "caixa")
        + _marcador(x(meta), "meta") +
        f'</div>'

        f'<div style="{rot}">ritmo do dia {dia}</div>'
        f'<div style="height:10px;border-radius:5px;'
        f'background:var(--ms-metric-bd);position:relative;">'
        f'<div style="position:absolute;left:0;top:0;height:100%;'
        f'width:{x(alvo_hoje):.1f}%;background:var(--ms-texto-sec);'
        f'border-radius:5px;opacity:.85;"></div></div>'

        f'<div></div>'
        f'<div style="position:relative;height:15px;">'
        f'<span style="position:absolute;left:{x(op):.1f}%;'
        f'transform:translateX(-50%);font-size:9px;font-weight:700;'
        f'white-space:nowrap;color:var(--ms-texto);">▲ operacional</span>'
        f'<span style="position:absolute;left:{x(cx):.1f}%;'
        f'transform:translateX(-50%);font-size:9px;font-weight:700;'
        f'white-space:nowrap;color:var(--ms-texto);">▲ caixa</span>'
        f'<span style="position:absolute;left:{x(meta):.1f}%;'
        f'transform:translateX(-50%);font-size:9px;font-weight:700;'
        f'white-space:nowrap;color:var(--ms-texto);">▲ meta</span></div>'
        f'</div>'

        f'<div style="display:flex;justify-content:space-between;gap:12px;'
        f'flex-wrap:wrap;font-size:11px;color:var(--ms-texto-sec);'
        f'margin-top:8px;">'
        f'<span>meta do mês <b style="color:var(--ms-texto);">'
        f'{_brl(meta, 0)}</b> · até o dia {dia} deveria ter '
        f'<b style="color:var(--ms-texto);">{_brl(alvo_hoje, 0)}</b></span>'
        f'<span style="color:{cor};font-weight:700;">'
        f'{_brl(dif, 0)} {frase}</span></div>'

        f'<div style="display:flex;justify-content:space-between;gap:12px;'
        f'flex-wrap:wrap;font-size:11px;color:var(--ms-texto-sec);'
        f'margin-top:4px;">'
        f'<span>faixa da projeção {_brl(f["piso"], 0)} – {_brl(f["teto"], 0)}</span>'
        f'<span>projeção: <b style="color:{cor_proj};">{veredito}</b></span>'
        f'<span>equilíbrio operacional {_brl(op, 0)} · de caixa {_brl(cx, 0)}</span>'
        f'</div></div>',
        unsafe_allow_html=True)


def _marcador(pos, _nome):
    return (f'<div style="position:absolute;top:-6px;bottom:-6px;'
            f'left:{pos:.1f}%;width:3px;margin-left:-1.5px;border-radius:2px;'
            f'background:var(--ms-texto);"></div>')


def _card(c):
    """Um indicador: realizado contra necessário, com o veredito escrito.

    `maior_melhor` existe porque nem todos apontam para o mesmo lado: em LPV e
    nos lucros, mais é melhor; em custo unitário, menos. Sem isso, a mesma cor
    diria coisas opostas em cartões vizinhos.
    """
    r, n = float(c["realizado"]), float(c["necessario"])
    atingiu = r >= n if c["maior_melhor"] else r <= n
    perto = abs(r - n) / (abs(n) or 1) <= 0.08
    cor = VERDE if atingiu else (AMARELO if perto else VERMELHO)
    falta = (n - r) if c["maior_melhor"] else (r - n)
    verbo = "acima do necessário" if atingiu else (
        "abaixo do necessário" if c["maior_melhor"] else "acima do necessário")
    # Diferenca entre duas porcentagens e ponto percentual, nao porcentagem:
    # "1,9%" ao lado de "48,0%" faz o olho ler 1,9% DE 48, que e outro numero.
    dif = (_num(abs(falta), 1, " p.p.") if c["fmt"] == "pct"
           else _fmt(abs(falta), c["fmt"]))
    escala = max(r, n) * 1.25 or 1
    return (
        f'<div style="background:var(--ms-metric-bg);'
        f'border:1px solid var(--ms-metric-bd);border-radius:10px;'
        f'padding:12px 14px;height:100%;">'
        f'<div style="font-size:10px;color:var(--ms-texto-sec);'
        f'text-transform:uppercase;letter-spacing:.5px;">{c["rotulo"]}</div>'
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
        f'necessário <b style="color:var(--ms-texto);">'
        f'{_fmt(n, c["fmt"])}</b></div>'
        f'<div style="font-size:10.5px;font-weight:700;color:{cor};'
        f'margin-top:4px;">'
        f'{"✔" if atingiu else "▸"} {dif} {verbo}</div>'
        f'</div>')


def pagina(usuario_logado=None, dados=None):
    d = dados or EXEMPLO
    st.markdown("### 🏠 Home")
    st.caption("O resumo do mês: onde o faturamento está contra o que ele "
               "precisa ser. **O ponto de equilíbrio vem primeiro** — meta de "
               "faturamento é consequência dele.")

    if dados is None:
        st.warning("**Números de exemplo**, para aprovar o layout. Nenhum "
                   "deles vem da operação ainda.")

    _bloco_faturamento(d)

    st.markdown('<div style="height:10px;"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="display:grid;grid-template-columns:repeat(3,1fr);'
        'gap:10px;">' + "".join(_card(c) for c in d["cards"]) + '</div>',
        unsafe_allow_html=True)

    st.caption(
        f"Mês de referência {d['mes']:02d}/{d['ano']}, fechado no dia "
        f"{d['dia']} de {ritmo(d)[2]}. O **ritmo** reparte a meta em partes "
        "iguais pelos dias corridos do mês. A faixa tracejada é o intervalo "
        "da projeção — ela tem erro medido, e fingir um ponto exato seria "
        "inventar precisão que o método não tem.")


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    ok("real sai no formato brasileiro", _brl(148320, 0) == "R$ 148.320")
    ok("porcentagem sai com uma casa", _fmt(12.4, "pct") == "12,4%")
    ok("o exemplo tem os seis cartões", len(EXEMPLO["cards"]) == 6)
    ok("todo cartão diz para que lado é melhor",
       all("maior_melhor" in c for c in EXEMPLO["cards"]))
    ok("o custo unitário é o único em que menos é melhor",
       [c["rotulo"] for c in EXEMPLO["cards"] if not c["maior_melhor"]] == ["UC"])
    ok("a linha de caixa é sempre maior que a operacional",
       EXEMPLO["faturamento"]["caixa"] > EXEMPLO["faturamento"]["operacional"])
    ok("a meta do mês fica acima do equilíbrio de caixa",
       EXEMPLO["faturamento"]["meta"] > EXEMPLO["faturamento"]["caixa"])
    ok("a projeção cai dentro da própria faixa",
       EXEMPLO["faturamento"]["piso"] <= EXEMPLO["faturamento"]["projecao"]
       <= EXEMPLO["faturamento"]["teto"])

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

    # O ritmo e a meta repartida pelos dias CORRIDOS: no ultimo dia do mes ele
    # tem de ser a meta inteira, senao a barra nunca fecha.
    _fim = dict(EXEMPLO, dia=30)
    ok("o ritmo do último dia é a meta inteira",
       abs(ritmo(_fim)[0] - EXEMPLO["faturamento"]["meta"]) < 0.01)
    ok("setembro tem 30 dias e o ritmo do dia 14 é 14/30 da meta",
       ritmo(EXEMPLO)[2] == 30
       and abs(ritmo(EXEMPLO)[0] - 240_000 * 14 / 30) < 0.01)
    ok("um dia além do fim do mês não passa da meta",
       abs(ritmo(dict(EXEMPLO, dia=44))[0]
           - EXEMPLO["faturamento"]["meta"]) < 0.01)
    ok("o realizado do exemplo é menor que a projeção",
       EXEMPLO["faturamento"]["realizado"] < EXEMPLO["faturamento"]["projecao"])

    # As tres cores sao ESTADO: cada barra mostra uma so, e sempre com frase.
    ok("as três cores de estado são distintas",
       len({VERDE, AMARELO, VERMELHO}) == 3)

    print("\nfalhas:", falhas)
