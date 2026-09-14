"""home_gestao.py — A primeira tela da Gestão: o mês contra o que ele precisa ser.

A FORMA
-------
Seis indicadores, e todos fazem a mesma pergunta: **o realizado contra o
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
parcelas saem —, e os outros cinco vêm embaixo, em cartões menores.

OS NÚMEROS DESTA TELA SÃO DE EXEMPLO
------------------------------------
`EXEMPLO` é um dicionário de valores fictícios, marcado como tal na tela. Ele
existe para o layout ser aprovado antes de haver de onde ler os dados reais —
LPV, UC e os lucros dependem de campos que ainda são preenchidos à mão durante a
venda. Trocar a fonte é trocar o dicionário por uma leitura; a tela não muda.
"""

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
        "projecao": 241_800.00, "piso": 212_400.00, "teto": 272_300.00,
        "operacional": 131_918.00, "caixa": 183_940.00,
    },
    "cards": [
        {"rotulo": "LPV", "sub": "lucro por venda",
         "realizado": 42.10, "necessario": 48.00, "fmt": "brl",
         "maior_melhor": True},
        {"rotulo": "UC", "sub": "custo unitário",
         "realizado": 21.60, "necessario": 19.80, "fmt": "brl",
         "maior_melhor": False},
        {"rotulo": "Lucro bruto", "sub": "no mês",
         "realizado": 71_190.00, "necessario": 68_400.00, "fmt": "brl0",
         "maior_melhor": True},
        {"rotulo": "Lucro líquido", "sub": "no mês",
         "realizado": 18_460.00, "necessario": 24_900.00, "fmt": "brl0",
         "maior_melhor": True},
        {"rotulo": "Margem de lucro", "sub": "líquida sobre o faturado",
         "realizado": 12.4, "necessario": 16.0, "fmt": "pct",
         "maior_melhor": True},
    ],
}


def _fmt(valor, como):
    if como == "pct":
        return _num(valor, 1, "%")
    if como == "brl0":
        return _brl(valor, 0)
    return _brl(valor)


def _bloco_faturamento(d):
    """O faturamento contra as duas linhas de equilíbrio, em largura inteira.

    Duas linhas e não uma: os PRONAMPs saem do caixa mas não são custo de
    operar, e incluir ou não muda a resposta em R$ 52 mil. Em vez de escolher
    pelo gestor, a barra mostra as duas e diz onde a projeção caiu.
    """
    f = d["faturamento"]
    proj, op, cx = f["projecao"], f["operacional"], f["caixa"]
    if proj >= cx:
        cor, veredito = VERDE, "fecha acima das duas linhas"
    elif proj >= op:
        cor, veredito = AMARELO, "paga a operação, mas não as parcelas"
    else:
        cor, veredito = VERMELHO, "fecha abaixo do equilíbrio operacional"

    escala = max(proj, cx, f["teto"]) * 1.12 or 1
    x = lambda v: min(max(v / escala * 100, 0), 100)

    st.markdown(
        f'<div style="background:var(--ms-metric-bg);'
        f'border:1px solid var(--ms-metric-bd);border-radius:12px;'
        f'padding:16px 18px 12px;">'

        f'<div style="font-size:11px;color:var(--ms-texto-sec);'
        f'text-transform:uppercase;letter-spacing:.6px;">'
        f'Faturamento × ponto de equilíbrio</div>'

        f'<div style="display:flex;align-items:baseline;gap:12px;'
        f'flex-wrap:wrap;margin-top:6px;">'
        f'<span style="font-size:40px;font-weight:700;color:var(--ms-texto);'
        f'line-height:1;">{_brl(f["realizado"], 0)}</span>'
        f'<span style="font-size:12px;color:var(--ms-texto-sec);">'
        f'faturado até o dia {d["dia"]}</span>'
        f'<span style="margin-left:auto;font-size:12px;'
        f'color:var(--ms-texto-sec);">projeção de fechamento '
        f'<b style="color:var(--ms-texto);">{_brl(proj, 0)}</b></span></div>'

        # A trilha, com a faixa da projeção por cima da barra do realizado.
        f'<div style="height:18px;border-radius:9px;'
        f'background:var(--ms-metric-bd);margin:18px 0 6px;position:relative;">'
        f'<div style="position:absolute;left:0;top:0;height:100%;'
        f'width:{x(f["realizado"]):.1f}%;background:{cor};'
        f'border-radius:9px;"></div>'
        # A faixa piso-teto: a projeção tem erro medido, e fingir um ponto
        # exato seria inventar precisão que o método não tem.
        f'<div style="position:absolute;top:3px;height:12px;'
        f'left:{x(f["piso"]):.1f}%;width:{x(f["teto"]) - x(f["piso"]):.1f}%;'
        f'border:2px dashed var(--ms-texto-sec);border-radius:7px;'
        f'opacity:.75;"></div>'
        + _marcador(x(op), "operacional")
        + _marcador(x(cx), "caixa") +
        f'</div>'

        f'<div style="position:relative;height:15px;">'
        f'<span style="position:absolute;left:{x(op):.1f}%;'
        f'transform:translateX(-50%);font-size:9px;font-weight:700;'
        f'white-space:nowrap;color:var(--ms-texto);">▲ operacional</span>'
        f'<span style="position:absolute;left:{x(cx):.1f}%;'
        f'transform:translateX(-50%);font-size:9px;font-weight:700;'
        f'white-space:nowrap;color:var(--ms-texto);">▲ caixa</span></div>'

        f'<div style="display:flex;justify-content:space-between;gap:12px;'
        f'flex-wrap:wrap;font-size:11px;color:var(--ms-texto-sec);'
        f'margin-top:6px;">'
        f'<span>faixa da projeção {_brl(f["piso"], 0)} – {_brl(f["teto"], 0)}</span>'
        f'<span style="color:{cor};font-weight:700;">{veredito}</span>'
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
        f'{"✔" if atingiu else "▸"} {_fmt(abs(falta), c["fmt"])} {verbo}</div>'
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
        '<div style="display:grid;grid-template-columns:repeat(5,1fr);'
        'gap:10px;">' + "".join(_card(c) for c in d["cards"]) + '</div>',
        unsafe_allow_html=True)

    st.caption(
        f"Mês de referência {d['mes']:02d}/{d['ano']}, fechado no dia "
        f"{d['dia']}. A faixa tracejada no topo é o intervalo da projeção — "
        "ela tem erro medido, e fingir um ponto exato seria inventar precisão "
        "que o método não tem.")


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    ok("real sai no formato brasileiro", _brl(148320, 0) == "R$ 148.320")
    ok("porcentagem sai com uma casa", _fmt(12.4, "pct") == "12,4%")
    ok("o exemplo tem os cinco cartões", len(EXEMPLO["cards"]) == 5)
    ok("todo cartão diz para que lado é melhor",
       all("maior_melhor" in c for c in EXEMPLO["cards"]))
    ok("o custo unitário é o único em que menos é melhor",
       [c["rotulo"] for c in EXEMPLO["cards"] if not c["maior_melhor"]] == ["UC"])
    ok("a linha de caixa é sempre maior que a operacional",
       EXEMPLO["faturamento"]["caixa"] > EXEMPLO["faturamento"]["operacional"])
    ok("a projeção cai dentro da própria faixa",
       EXEMPLO["faturamento"]["piso"] <= EXEMPLO["faturamento"]["projecao"]
       <= EXEMPLO["faturamento"]["teto"])
    ok("o realizado do exemplo é menor que a projeção",
       EXEMPLO["faturamento"]["realizado"] < EXEMPLO["faturamento"]["projecao"])

    # As tres cores sao ESTADO: cada barra mostra uma so, e sempre com frase.
    ok("as três cores de estado são distintas",
       len({VERDE, AMARELO, VERMELHO}) == 3)

    print("\nfalhas:", falhas)
