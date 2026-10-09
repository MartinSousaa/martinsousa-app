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

import rotulos as _rot


def pagina(usuario_logado=None):
    import favorecidos as _fv
    import lancamentos as _lan
    import pandas as pd

    st.markdown("#### 🏷️ Finalidades")

    cad = _fv.carregar() or {}
    _opcoes = _finalidades(cad)

    # ── A fila: nomes que já apareceram e ninguém classificou ────────────
    #
    # A MESMA TABELA da fila do anexo (`extratos_tela._perguntar`): todos os
    # nomes, nenhuma finalidade pré-escolhida, marcar várias e salvar de uma
    # vez, e cada compra listada embaixo. Era uma linha por vez, só 20, e com
    # ADS já selecionado — um Salvar distraído gravava ADS (dono, 07/10).
    import extratos_tela as _et
    st.markdown("##### ⏳ Sem classificação")
    fila = _et.fila_dos_gravados(_lan.carregar(), cad)
    if not fila:
        st.success("Nada na fila — todo nome que já apareceu tem resposta.")
    else:
        _et._perguntar(fila, _fv, usuario_logado)

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

    # Editor e botao no MESMO formulario. Com o botao solto, o clique que sai
    # da celula ainda em edicao fecha a celula E dispara o rerun: o rerun come
    # o clique, o botao nao roda, e a tela nao diz nada. Foi assim que a meta
    # de gastos de setembro nao foi gravada em 17/09.
    with st.form("form_finalidades"):
        editado = st.data_editor(
            df, use_container_width=True, hide_index=True, key="fin_ed",
            num_rows="dynamic",
            column_config={**_rot.config(["favorecido", "finalidade", "sentido", "observação", "n", "total"], st), 
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
        enviou = st.form_submit_button("💾 Salvar cadastro", type="primary",
                                       use_container_width=True)

    if enviou:
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
    """A lista vem de `favorecidos.FINALIDADES_BASE` — dono único.

    Ela estava escrita aqui E em `extratos_tela.py`, e as duas cópias já
    discordavam em quatro nomes.
    """
    import favorecidos as _fv
    return _fv.finalidades_conhecidas(cad)
