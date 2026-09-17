"""finalidades_tela.py — o que cada nome do extrato significa, editável.

O cadastro em si mora em `favorecidos.py`. Esta tela é só a mão do dono nele:
a fila do que ainda não tem resposta em cima — é o trabalho a fazer —, e o que
já está classificado embaixo, para consulta e correção.

Mudar aqui vale para o PASSADO inteiro: a finalidade não é copiada para dentro
do lançamento, ela é lida do cadastro. Corrigir "APEXIMP" de OUTROS para
MERCADORIA arruma os oito meses de uma vez, e é por isso que o cadastro é o
lugar certo — no lançamento, a correção valeria para uma linha só.
"""

import streamlit as st


def pagina(usuario_logado=None):
    import favorecidos as _fv
    import lancamentos as _lan
    import pandas as pd

    st.markdown("#### 🏷️ Finalidades")
    st.caption(
        "Cada nome que aparece no extrato, e o que ele significa. Alterar aqui "
        "vale para o histórico todo — a finalidade é lida do cadastro, não "
        "copiada para dentro do lançamento."
    )

    cad = _fv.carregar() or {}
    _opcoes = _finalidades(cad)

    # ── A fila: nomes que já apareceram e ninguém classificou ────────────
    todos = _lan.carregar()
    _, fila = _fv.classificar(todos, cad)
    st.markdown("##### ⏳ Sem classificação")
    if not fila:
        st.success("Nada na fila — todo nome que já apareceu tem resposta.")
    else:
        st.caption(f"{len(fila)} nome(s), do que mais pesou para o menor.")
        for i, item in enumerate(fila[:20]):
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.markdown(f"**{item['favorecido'][:40]}**  \n"
                        f"{item['n']}x · R$ {item['total']:,.2f}")
            _f = c2.selectbox("Finalidade", _opcoes, key=f"fin_q_{i}",
                              label_visibility="collapsed")
            if c3.button("Salvar", key=f"fin_s_{i}", use_container_width=True):
                _ok, _m = _fv.salvar(item["favorecido"], _f, "saida", "",
                                     usuario_logado)
                (st.success if _ok else st.error)(_m)

    # ── O cadastro, editável ─────────────────────────────────────────────
    st.markdown("---")
    st.markdown("##### 📖 Já classificados")
    if not cad:
        st.info("Cadastro vazio.")
        return
    linhas = sorted(cad.values(), key=lambda v: v["favorecido"].upper())
    _busca = st.text_input("Buscar nome", key="fin_busca",
                           placeholder="ex: apeximp")
    if _busca.strip():
        _b = _busca.strip().upper()
        linhas = [l for l in linhas if _b in l["favorecido"].upper()]

    df = pd.DataFrame([{
        "favorecido": l["favorecido"],
        "sentido": l.get("tipo") or "saida",
        "finalidade": l["finalidade"],
        "observação": l.get("observacao", ""),
    } for l in linhas])

    editado = st.data_editor(
        df, use_container_width=True, hide_index=True, key="fin_ed",
        num_rows="dynamic",
        column_config={
            "favorecido": st.column_config.TextColumn("Favorecido",
                                                      required=True),
            "sentido": st.column_config.SelectboxColumn(
                "Sentido", options=["saida", "entrada"], width="small",
                help="O mesmo nome pode significar coisas diferentes: recebido "
                     "da Little Glass é repasse do Mercado Livre; enviado para "
                     "ela é transferência entre contas."),
            "finalidade": st.column_config.SelectboxColumn(
                "Finalidade", options=_opcoes, required=True),
            "observação": st.column_config.TextColumn(width="medium"),
        },
    )

    if st.button("💾 Salvar cadastro", type="primary",
                 use_container_width=True, key="fin_salvar"):
        _antes = {(l["favorecido"], l.get("tipo") or "saida"):
                  (l["finalidade"], l.get("observacao", "")) for l in linhas}
        _n = 0
        for _, r in editado.iterrows():
            nome = str(r["favorecido"]).strip()
            if not nome or not str(r["finalidade"]).strip():
                continue
            chave = (nome, str(r["sentido"]))
            if _antes.get(chave) == (str(r["finalidade"]),
                                     str(r["observação"] or "")):
                continue
            _ok, _m = _fv.salvar(nome, str(r["finalidade"]), str(r["sentido"]),
                                 str(r["observação"] or ""), usuario_logado)
            if not _ok:
                st.error(_m)
                return
            _n += 1
        st.success(f"{_n} linha(s) salva(s).") if _n else st.info("Nada mudou.")


def _finalidades(cad):
    base = ["MERCADORIA", "EMBALAGEM", "CUSTO FIXO", "NÃO OPERACIONAL",
            "IMPOSTO", "SERVIÇO", "ESTACIONAMENTO", "CONSUMO INTERNO", "TRANSFERENCIA ENTRE CONTAS",
            "EMPRESTIMO PRONAMP", "REEMBOLSO PRONAMP", "RATEIO CUSTO FIXO",
            "MERCADO LIVRE", "SHOPEE", "SHEIN", "AMAZON", "SITE", "APLICACAO", "OUTROS"]
    usadas = {v["finalidade"] for v in (cad or {}).values()
              if v.get("finalidade")}
    return sorted(set(base) | usadas)
