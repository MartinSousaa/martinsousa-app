"""boletos_tela.py — a aba Boletos do Financeiro (dono, 13/10).

Anexa o PDF do boleto, o Studio lê valor, vencimento e beneficiário
(`boleto_pdf`), o dono confere e grava. O boleto vira provisionado do mês do
vencimento (`previsto._boletos`) até o extrato mostrar o pagamento
(`cheques.baixas_pelo_extrato`, que aceita boleto pago adiantado).

MORA NO CADASTRO DOS CHEQUES, com tipo BOLETO: a baixa pelo extrato, a
gravação e a edição já existiam ali, e uma segunda cópia delas começaria
igual e terminaria discordando. Boleto é compra de mercadoria, quase sempre
(dono): o estoque é o valor, e ele entra na "mercadoria comprometida" da Home.
"""
from datetime import datetime

import streamlit as st

import rotulos as _rot


@st.cache_data(show_spinner=False, max_entries=50)
def _ler_pdf(dados, hoje_iso):
    """A leitura de um PDF. Em cache: sem ele, o PDF seria aberto de novo a
    cada clique na tela."""
    import boleto_pdf as _bp
    from datetime import date
    return _bp.ler_pdf(dados, date.fromisoformat(hoje_iso))


def para_gravar(leituras, hoje):
    """As leituras conferidas na forma de `cheques.gravar`. Pura.

    (linhas, recusadas): leitura sem valor ou sem vencimento não grava — ela
    entraria no provisionado com zero, ou em mês nenhum.
    """
    linhas, recusadas = [], []
    for l in leituras or []:
        venc = l.get("vencimento")
        valor = l.get("valor")
        if not venc or not valor:
            recusadas.append(l.get("beneficiário") or l.get("arquivo") or "?")
            continue
        venc_txt = venc.isoformat() if hasattr(venc, "isoformat") else str(venc)
        linhas.append({
            "tipo": "BOLETO", "favorecido": str(l.get("beneficiário") or "")[:80],
            "compra": hoje.isoformat(), "vencimento": venc_txt[:10],
            "valor": float(valor), "envio": 0.0, "situacao": "EM ABERTO",
            "observacao": f"LD:{l['linha']}" if l.get("linha") else "",
        })
    return linhas, recusadas


def pagina(usuario_logado=None):
    import pandas as pd
    import boleto_pdf as _bp
    import cheques as _ch
    import placar_core as _pc

    st.markdown("#### 🧾 Boletos")
    hoje = datetime.now(_pc.FUSO).date()

    # A BAIXA PELOS EXTRATOS JÁ GRAVADOS, como na aba Cheques: é a mesma
    # função, e ela só escreve quando há baixa a dar.
    try:
        _feitas, _duv, _err = _ch.conferir_com_extratos(usuario_logado)
        if _feitas:
            st.success(f"{_feitas} boleto(s)/cheque(s) baixado(s) pelos "
                       "extratos já lançados.")
        for _e in _err:
            st.warning(_e)
    except Exception as e:
        st.warning(f"Não consegui conferir com os extratos: {type(e).__name__}")

    # ── anexar ───────────────────────────────────────────────────────────
    _rodada = st.session_state.get("bol_rodada", 0)
    arquivos = st.file_uploader("Anexar boletos (PDF)", type=["pdf"],
                                accept_multiple_files=True,
                                key=f"bol_pdfs_{_rodada}")
    colada = st.text_input("Ou cole a linha digitável", key=f"bol_ld_{_rodada}",
                           placeholder="34191.79001 01043.510047 …")
    leituras = []
    for a in arquivos or []:
        lido, erro = _ler_pdf(a.getvalue(), hoje.isoformat())
        if erro:
            st.error(f"{a.name}: {erro}")
            continue
        leituras.append({"arquivo": a.name, **lido})
    if colada.strip():
        leituras.append({"arquivo": "linha colada",
                         **_bp.ler_texto(colada, hoje)})

    if leituras:
        ja = {str(l.get("id") or "") for l in _ch.carregar()}
        df = pd.DataFrame([{
            "gravar": True,
            "beneficiário": l.get("beneficiario") or "",
            "vencimento": l.get("vencimento"),
            "valor": l.get("valor"),
            "aviso": l.get("aviso") or "",
            "arquivo": l.get("arquivo"),
            "linha": l.get("linha") or "",
        } for l in leituras])
        # O mesmo boleto já cadastrado (mesma linha digitável) não grava de
        # novo: a identidade do cadastro é a linha (`cheques.identidade`).
        for i, l in df.iterrows():
            if l["linha"] and _ch.identidade(
                    {"tipo": "BOLETO", "observacao": f"LD:{l['linha']}"}) in ja:
                df.at[i, "gravar"] = False
                df.at[i, "aviso"] = "já cadastrado"
        editado = st.data_editor(
            df, use_container_width=True, hide_index=True, key="bol_ed",
            disabled=["aviso", "arquivo"],
            column_config={
                "gravar": st.column_config.CheckboxColumn("✔", width="small"),
                "beneficiário": st.column_config.TextColumn("Beneficiário"),
                "vencimento": st.column_config.DateColumn(
                    "Vencimento", format="DD/MM/YYYY"),
                "valor": st.column_config.NumberColumn(
                    "Valor", format="R$ %.2f", min_value=0.0),
                "aviso": st.column_config.TextColumn("Conferir"),
                "arquivo": st.column_config.TextColumn("Arquivo"),
                "linha": None,
            })
        marcados = [r for r in editado.to_dict("records") if r.get("gravar")]
        if marcados and st.button(f"💾 Gravar {len(marcados)} boleto(s)",
                                  type="primary", key="bol_gravar"):
            linhas, recusadas = para_gravar(marcados, hoje)
            n, rep, erro = _ch.gravar(linhas, usuario_logado) if linhas else (0, 0, "")
            if erro:
                st.error(f"Não consegui gravar: {erro}")
            else:
                st.success(f"{n} boleto(s) gravado(s)"
                           + (f" · {rep} já estava(m) cadastrado(s)" if rep else ""))
                st.session_state["bol_rodada"] = _rodada + 1
            for r in recusadas:
                st.warning(f"{r}: sem valor ou sem vencimento — não gravado.")

    # ── em aberto ────────────────────────────────────────────────────────
    import home_gestao as _hg
    linhas_ch = _ch.carregar()
    abertos = [c for c in linhas_ch
               if _ch.eh_tipo(c, "BOLETO") and _ch.esta_aberto(c)]
    tabela = _hg.boletos_em_aberto(linhas_ch, hoje)
    st.markdown(f"##### Em aberto · "
                f"{_rot.brl(sum(b['valor'] for b in tabela))}")
    if not tabela:
        st.info("Nenhum boleto em aberto.")
        return
    st.dataframe(tabela, use_container_width=True, hide_index=True,
                 column_config=_rot.config(
                     ["vencimento", "beneficiário", "valor", "situação"], st,
                     tipos={"valor": "brl"}))
    rotulo = {c["id"]: f"{_ch.data_br(c.get('vencimento'))} · "
                       f"{c.get('favorecido') or '—'} · "
                       f"{_rot.brl(_ch._num(c.get('valor')))}"
              for c in abertos}
    sel = st.multiselect("Selecionar", list(rotulo), format_func=rotulo.get,
                         key="bol_sel")
    c1, c2 = st.columns(2)
    if sel and c1.button("✔ Marcar como pago", key="bol_pago"):
        for i in sel:
            _ch.atualizar(i, {"situacao": "PAGO"}, usuario_logado)
        st.rerun()
    if sel and c2.button("🗑️ Apagar", key="bol_apagar"):
        _ch.apagar(sel)
        st.rerun()


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from datetime import date
    import boleto_pdf as _bp_t
    import cheques as _ch_t
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # PELA CADEIA: a leitura sai de `boleto_pdf.ler_texto` (o que a tela
    # recebe), e o que se grava passa por `cheques.normalizar`.
    def _campo(n):
        return n + str(_bp_t._mod10(n))
    _ld = (_campo("341911234") + _campo("5678901234") + _campo("5678901234")
           + "7" + "1019" + "0000150000")
    _lido = _bp_t.ler_texto("Beneficiário\nVIDROS SA\n" + _ld,
                            date(2025, 3, 1))
    _lin, _rec = para_gravar([{"beneficiário": _lido["beneficiario"],
                               "vencimento": _lido["vencimento"],
                               "valor": _lido["valor"], "linha": _lido["linha"]}],
                             date(2025, 3, 1))
    _n = _ch_t.normalizar(_lin[0])
    ok("o boleto lido vira um BOLETO em aberto, com estoque = valor",
       _n["tipo"] == "BOLETO" and _n["situacao"] == "EM ABERTO"
       and _n["valor"] == 1500.0 and _n["estoque"] == 1500.0
       and _n["vencimento"] == "2025-03-13" and _n["favorecido"] == "VIDROS SA")
    ok("a linha digitável vai junto, e é ela que identifica o boleto",
       _ch_t.linha_digitavel(_n) == _ld)
    _lin2, _rec2 = para_gravar([{"beneficiário": "X", "vencimento": None,
                                 "valor": 10.0, "linha": ""}], date(2025, 3, 1))
    ok("sem vencimento não grava, e diz qual", _lin2 == [] and _rec2 == ["X"])
    print(f"\nfalhas: {falhas}")
    sys.exit(1 if falhas else 0)
