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
    ano = int((d or {}).get("ano") or hoje.year)
    mes = int((d or {}).get("mes") or hoje.month)

    try:
        linha = _mg.linha_do_mes(ano, mes)
        lancs = _lan.do_mes(ano, mes)
    except Exception as e:
        st.caption(f"Não consegui ler os gastos: {str(e)[:140]}")
        return

    if not lancs and not linha["meta"]:
        st.info(
            "Sem meta e sem lançamentos neste mês. A meta se digita em "
            "**Financeiro › 🎯 Meta de gastos**; os lançamentos entram "
            "sozinhos quando você sobe o extrato em **Financeiro › 💳 "
            "Extratos**.")
        return

    # ── 1. o número que decide ───────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    c1.metric("Realizado", _brl(linha["realizado"]),
              help=f"origem: {linha['origem']}")
    c2.metric("Meta do mês", _brl(linha["meta"]) if linha["meta"] else "—")
    if linha["meta"]:
        c3.metric("Saldo", _brl(linha["saldo"]),
                  delta=f"{linha['pct']:.0f}% consumido",
                  delta_color="inverse")
        st.progress(min(linha["pct"] / 100, 1.0),
                    text=f"{linha['pct']:.0f}% da meta")
    else:
        c3.metric("Saldo", "—")
        st.caption("Sem meta digitada para este mês — o saldo não tem como "
                   "existir.")

    if not lancs:
        st.caption("Nenhum extrato carregado neste mês. O realizado acima é o "
                   "que você informou à mão.")
        return

    # ── 2. onde o dinheiro foi ───────────────────────────────────────────
    import pandas as pd
    res = _lan.resumo_por_finalidade(lancs)
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
            column_config={
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
            column_config={"valor": st.column_config.NumberColumn(
                format="R$ %.2f")})

    sem = res.get("SEM CLASSIFICAÇÃO", 0.0)
    if sem:
        st.warning(
            f"**{_brl(sem)} sem classificação.** Cada nome respondido uma vez "
            f"nunca mais aparece — em **Financeiro › 🏷️ Finalidades**.")

    st.caption("Fora da conta: transferência entre contas, aplicação, entrada "
               "de empréstimo e repasse de plataforma. Nenhum dos quatro é "
               "gasto.")


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

    st.caption(
        f"Mês de referência {d['mes']:02d}/{d['ano']}, fechado no dia "
        f"{dia} de {dias}. O **ritmo** reparte a meta em partes iguais pelos "
        "dias corridos do mês, e a **projeção** é o ritmo médio vezes os "
        "dias do mês — um método só, porque duas projeções discordando na "
        "mesma tela não informam, escolhem por você.")

    _bloco_gastos(usuario_logado, d)


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

    # As tres cores sao ESTADO: cada barra mostra uma so, e sempre com frase.
    ok("as três cores de estado são distintas",
       len({VERDE, AMARELO, VERMELHO}) == 3)

    print("\nfalhas:", falhas)
