"""gargalos_tela.py — a tela que responde onde o trabalho de imagem trava.

SÓ O DONO VÊ, E O MOTIVO NÃO É SIGILO
--------------------------------------
Pedido dele, com todas as letras. E a razão é boa: esta tela mede as pessoas
pelo nome. Medir gente em público muda o que a gente escreve — a partir daí o
log passa a descrever o que a equipe acha que o chefe quer ler, e o dado que
ela existe para produzir morre na origem.

A conta mora em `gargalos.py`, que é testável sem subir Streamlit. Aqui só se
desenha. Foi assim que a regra do bônus acabou presa dentro de uma tela e
teve de ser extraída depois.
"""

from datetime import datetime, timedelta, timezone

import streamlit as st

import gargalos as _g

FUSO = timezone(timedelta(hours=-3))

# Quantas linhas do log ler. O `ler()` padrão traz 200, que é pouco para um mês
# — a conversa de um único produto já passou de 40.
LINHAS = 3000

# O rótulo de cada diagnóstico, com a ação que ele pede. Diagnóstico sem ação
# é só um adjetivo, e adjetivo não conserta nada.
DIAGNOSTICOS = {
    "GERADOR": ("🔴 O gerador não entregou",
                "O pedido estava claro e a imagem não saiu. É aqui que mexer "
                "no prompt ou no motor tem retorno."),
    "COLATERAL": ("🟠 Fez, e quebrou outra coisa",
                  "O pedido foi atendido e a imagem mudou onde ninguém pediu. "
                  "É o que fabrica a rodada seguinte."),
    "ASSISTENTE": ("🟡 Disse que fez, e não fez",
                   "O Assistente respondeu como resolvido e a pessoa teve de "
                   "pedir de novo."),
    "PEDIDO": ("🔵 O pedido não dizia o suficiente",
               "A frase obriga a adivinhar. Cinco minutos de conversa com a "
               "pessoa resolvem."),
    "OK": ("✅ Saiu de primeira", "Nada a fazer."),
}

ROTULO_INTENCAO = {
    "COR": "Cor do produto",
    "TEXTO": "Texto, card ou medida",
    "CENARIO": "Cenário e ambientação",
    "ANATOMIA": "Forma do produto",
    "ENQUADRAMENTO": "Enquadramento",
    "REFERENCIA": "Seguir uma referência",
    "REMOVER": "Tirar um elemento",
    "REFAZER": "Refazer do zero",
    "OUTRO": "Não classificado",
}


def _brl(v):
    return f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",") \
        .replace("X", ".")


def _dentro_do_periodo(linha, dias):
    if not dias:
        return True
    q = _g._quando(linha.get("quando"))
    if not q:
        # Sem carimbo legível não dá para saber se é do período. Fica DENTRO:
        # esconder linha por defeito de formato apagaria justamente o registro
        # de um dia em que algo saiu do normal.
        return True
    return q >= datetime.now() - timedelta(days=int(dias))


def _cabecalho(r):
    c = st.columns(4)
    c[0].metric("Pedidos de ajuste", r["pedidos"])
    c[1].metric("Gerações gastas", r["tentativas"],
                help="Cada tentativa é uma imagem gerada e paga.")
    c[2].metric("Gastas repetindo", r["tentativas_repetindo"],
                help="Tentativas em assuntos que já tinham sido pedidos antes "
                     "na mesma imagem. É o desperdício puro.")
    c[3].metric("Refeitas do zero", r["refeitas_do_zero"])

    if r["tentativas"]:
        _pct = r["tentativas_repetindo"] / r["tentativas"] * 100
        _txt = (f"**{_pct:.0f}%** das gerações do período foram gastas "
                f"repetindo um pedido que já tinha sido feito.")
        (st.error if _pct >= 40 else st.warning if _pct >= 20
         else st.info)(_txt)


def _por_diagnostico(r):
    st.markdown("#### De quem é a trava")
    st.caption("Ordenado por gerações gastas. A ordem do diagnóstico é "
               "deliberada: falha registrada vence interpretação, e acusar a "
               "equipe é a última hipótese, nunca a primeira.")
    total = sum(r["por_diagnostico"].values()) or 1
    for chave, gastas in sorted(r["por_diagnostico"].items(),
                                key=lambda kv: -kv[1]):
        rot, ajuda = DIAGNOSTICOS.get(chave, (chave, ""))
        pct = gastas / total * 100
        st.markdown(f"**{rot}** — {gastas} geração(ões) · {pct:.0f}%")
        st.progress(min(1.0, gastas / total))
        st.caption(ajuda)


def _tabela_intencao(linhas):
    st.markdown("#### Em que assunto o trabalho se perde")
    dados = _g.por_intencao(linhas)
    if not dados:
        st.caption("Sem pedidos no período.")
        return
    st.dataframe(
        [{"Assunto": ROTULO_INTENCAO.get(d["intencao"], d["intencao"]),
          "Pedidos": d["pedidos"], "Gerações": d["tentativas"],
          "O gerador falhou": d["falhas"],
          "Quebrou outra coisa": d["colaterais"]} for d in dados],
        use_container_width=True, hide_index=True)


def _tabela_gargalos(linhas):
    st.markdown("#### Os assuntos que precisaram ser pedidos de novo")
    st.caption(f"A partir de {_g.REPETICOES_PARA_GARGALO} pedidos do mesmo "
               "assunto na mesma imagem. Dois é normal — um pedido e uma "
               "correção. Do terceiro em diante é sintoma.")
    grupos = [g for g in _g.agrupar(linhas)
              if g["pedidos"] >= _g.REPETICOES_PARA_GARGALO]
    if not grupos:
        st.success("Nenhum assunto precisou ser pedido três vezes no período.")
        return
    for g in grupos:
        rot, _ = DIAGNOSTICOS.get(g["diagnostico"], (g["diagnostico"], ""))
        with st.expander(
                f"{rot} · {g['produto'] or 'sem produto'} — imagem "
                f"{g['imagem']} · {ROTULO_INTENCAO.get(g['intencao'], g['intencao'])}"
                f" · **{g['pedidos']} pedidos**, {g['tentativas']} gerações"
                + (f", {g['minutos']:.0f} min" if g["minutos"] else "")):
            if g["usuarios"]:
                st.caption("Quem pediu: " + ", ".join(g["usuarios"]))
            st.caption("As frases, na ordem — é aqui que se vê se a pessoa "
                       "mudou o jeito de pedir ou repetiu o mesmo:")
            for i, f in enumerate(g["frases"], 1):
                st.markdown(f"{i}. _{f}_")


def _tabela_pessoas(linhas):
    st.markdown("#### Por pessoa")
    st.caption("Serve para achar treinamento, não para cobrar ninguém: quem "
               "repete muito num assunto só precisa saber como pedir aquilo, "
               "e isso se ensina em cinco minutos.")
    dados = _g.por_pessoa(linhas)
    if not dados:
        st.caption("Sem pedidos no período.")
        return
    linhas_tab = []
    for d in dados:
        pior = max(d["por_intencao"].items(), key=lambda kv: kv[1], default=("", 0))
        linhas_tab.append({
            "Pessoa": d["usuario"],
            "Pedidos": d["pedidos"],
            "Gerações": d["tentativas"],
            "Repetiu": d["repetidos"],
            "Assunto que mais custou":
                ROTULO_INTENCAO.get(pior[0], pior[0]) or "—",
        })
    st.dataframe(linhas_tab, use_container_width=True, hide_index=True)


def _reinicios():
    """O diário de reinícios, que é a outra metade do custo.

    Reinício não aparece no log de imagem — ele APAGA a sessão. Mas é ele que
    transforma uma tarde de ajustes em nada, e por isso vive na mesma tela:
    a pergunta "onde o trabalho se perde" tem duas respostas, e esta é a
    segunda.
    """
    st.markdown("#### Reinícios do Studio")
    try:
        import saude as _sd
        eventos = _sd.reinicios(20)
    except Exception as e:
        st.caption(f"Não consegui ler o diário: {type(e).__name__}")
        return
    if not eventos:
        st.success("Nenhum reinício registrado desde que o diário começou.")
        st.caption("O diário vive no disco do serviço; ele começa a contar a "
                   "partir do primeiro acesso depois de cada deploy.")
        return
    for ev in eventos:
        st.markdown(_sd.explicar(ev))


def pagina(usuario_logado=None):
    """A tela. Recusa quem não é dono na própria página, e não só na barra."""
    import auth
    if not auth.eh_dono(usuario_logado):
        # Esconder a aba sem trancar a porta troca o cadeado por uma cortina:
        # a URL continua levando até aqui.
        st.error("Esta tela é exclusiva do dono.")
        return

    st.markdown("### 🔎 Análise de Gargalos")
    st.caption(
        "Onde o trabalho de imagem trava, e de quem é a trava. Tudo aqui sai "
        "do registro que o Studio já faz a cada comando — nenhum dado novo é "
        "pedido a ninguém, e a tela fica mais útil quanto mais a equipe usa."
    )

    c1, c2 = st.columns([1, 2])
    dias = c1.selectbox("Período", [7, 15, 30, 90, 0],
                        format_func=lambda d: "Tudo" if not d else f"{d} dias",
                        index=2, key="garg_dias")

    try:
        import log_imagem
        todas = log_imagem.ler(LINHAS)
    except Exception as e:
        st.error(f"Não consegui ler o registro de imagem: {type(e).__name__}")
        return

    linhas = [l for l in todas if _dentro_do_periodo(l, dias)]
    produtos = sorted({str(l.get("produto", "")).strip()
                       for l in linhas if str(l.get("produto", "")).strip()})
    escolhido = c2.selectbox("Produto", ["Todos"] + produtos, key="garg_prod")
    if escolhido != "Todos":
        linhas = [l for l in linhas
                  if str(l.get("produto", "")).strip() == escolhido]

    if not linhas:
        st.info("Nenhum comando de imagem registrado nesse período.")
        _reinicios()
        return

    r = _g.resumo(linhas)
    _cabecalho(r)
    st.markdown("---")
    _por_diagnostico(r)
    st.markdown("---")
    _tabela_intencao(linhas)
    st.markdown("---")
    _tabela_gargalos(linhas)
    st.markdown("---")
    _tabela_pessoas(linhas)
    st.markdown("---")
    _reinicios()


# ── Conferência ──────────────────────────────────────────────────────────────
# `python3 gargalos_tela.py`. Tela não se testa sem subir Streamlit — mas o
# CONTRATO entre ela e `gargalos.py` se testa, e é dele que vêm os defeitos
# que aparecem para o dono como sigla crua na tela.
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    _src = open(__file__, encoding="utf-8").read()

    # A conta não pode morar na tela. Foi assim que a regra do bônus ficou
    # presa dentro de `analise_metas.py` e teve de ser extraída depois.
    ok("a tela não reimplementa a classificação",
       "INTENCOES = " not in _src and "def intencao(" not in _src)

    # Todo diagnóstico e todo assunto que o módulo produz precisa de rótulo:
    # sem isso o dono lê a sigla crua e não sabe o que fazer com ela.
    ok("todo diagnóstico tem rótulo e ação",
       {"GERADOR", "COLATERAL", "ASSISTENTE", "PEDIDO", "OK"}
       <= set(DIAGNOSTICOS)
       and all(len(v) == 2 and v[1] for v in DIAGNOSTICOS.values()))
    ok("todo assunto tem rótulo",
       {i for i, _ in _g.INTENCOES} | {"OUTRO"} <= set(ROTULO_INTENCAO))

    ok("a página confere o dono por conta própria", "auth.eh_dono" in _src)

    # Carimbo ilegível não pode apagar o registro de um dia fora do normal.
    ok("linha sem data continua no período",
       _dentro_do_periodo({"quando": "???"}, 30))
    ok("'Tudo' aceita qualquer linha",
       _dentro_do_periodo({"quando": "01/01/2020 10:00"}, 0))
    ok("linha velha sai do período de 7 dias",
       not _dentro_do_periodo({"quando": "01/01/2020 10:00"}, 7))

    print("\nfalhas:", falhas)
    raise SystemExit(falhas)
