"""operacional_gestao.py — Desempenho por conta: quem puxa e quem não puxa.

ONDE ISTO MORA
--------------
Fora da Home. O bloco nasceu lá embaixo dos seis indicadores e o gestor tirou:
"não é tão importante para estar na aba de resumo". A Home responde uma
pergunta só — o mês está onde precisa estar? —, e nove linhas de canal são
outra conversa. O layout ficou guardado aqui inteiro, esperando a aba dele.

Para usar numa aba nova, é uma linha:

    import operacional_gestao as og
    og.pagina(usuario_logado)            # com os números de exemplo
    og.pagina(usuario_logado, dados=d)   # com `d["operacional"]` de verdade

A FORMA
-------
Barra ordenada, e não pizza: a pergunta é quem puxa e quem não puxa, que se
responde comparando comprimento. Numa pizza de nove fatias, as quatro últimas
somam 3% e viram lasca sem rótulo. A trilha vai até a maior participação e não
até 100%, senão dois terços dela seriam espaço morto.

AS DUAS PARTICIPAÇÕES
---------------------
Um canal pode ser 31% do dinheiro e 28% das vendas, e a diferença entre os dois
números é o ticket médio dele. Mostrar só a do faturamento esconderia justo o
canal que vende muito e fatura pouco — o que dá trabalho na expedição sem pagar
a conta. Por isso as duas barras dividem a mesma escala: o desencontro entre
elas é a informação, não um detalhe de desenho.

NADA AQUI É IDENTIFICADO POR COR
--------------------------------
O par azul/roxo que eu tinha escolhido para LG e MS reprovou no validador de
paleta: ΔE 10,2 entre os dois, abaixo do piso de 15 — indistinguíveis até para
quem enxerga todas as cores, e 2,5 para quem tem protanopia. Em vez de caçar
outro par, a distinção saiu da cor: a sigla vai ESCRITA no selo, e a forma
separa os dois (cheio × vazado, borda sólida × tracejada). Cor aqui ainda
brigaria com o verde/amarelo/vermelho de estado do resto da Gestão, que querem
dizer "bateu" e "não bateu" — e aqui nada é bom nem ruim, são duas empresas.

DE ONDE VÊM OS NÚMEROS
----------------------
`EXEMPLO` é fictício e a tela avisa. Quando a fonte real chegar, ela é o
`por_loja` que o `bling_api.somar_pedidos` já devolve, com os nomes que o
`bling_api.canais_de_venda` já lê — nenhuma das duas peças falta.
"""

import streamlit as st

# O dinheiro e a porcentagem se escrevem num lugar só. Duplicar `_brl` aqui
# seria a mesma pergunta com duas respostas no código — elas discordam um dia,
# e a questão é só quando.
import home_gestao as _hg

VERDE = _hg.VERDE
_brl = _hg._brl
_num = _hg._num


EXEMPLO = {
    #     # Os quatro canais da LG sao os numeros REAIS lidos do Bling em 14/09/2026
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


def bloco(d):
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
    """A aba inteira. Enquanto não existir fonte real, avisa na tela."""
    d = dados or EXEMPLO
    st.markdown("### 🏬 Operacional")
    st.caption("Desempenho de cada canal de venda: quanto fatura, quanto "
               "vende, e o que representa no total das duas empresas.")
    if dados is None:
        st.warning("**Números de exemplo.** Os quatro canais da Little Glass "
                   "são leitura real do Bling em 14/09/2026; os cinco da MS "
                   "são fictícios, fechando no bruto e nos pedidos que a "
                   "mesma leitura mostrou.")
    bloco(d)


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

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


    # O CNPJ nao e distinguido por cor nenhuma: o selo traz a sigla escrita e
    # a forma (cheio x vazado). Se um dia alguem puser hue aqui, este caso
    # lembra por que o par anterior foi reprovado.
    ok("o selo do CNPJ não depende de cor para se distinguir",
       "LG" in _selo_cnpj("LG") and "MS" in _selo_cnpj("MS")
       and _selo_cnpj("LG") != _selo_cnpj("MS")
       and VERDE not in (_selo_cnpj("LG") + _selo_cnpj("MS")))

    print("\nfalhas:", falhas)
