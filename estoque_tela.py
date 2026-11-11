"""estoque_tela.py — a tela do Estoque (Operacional › 📦 Estoque), 11/11.

O dono aprovou seis layouts, um por vez. Esta é a PARTE 1 — Entrada e
cadastro. As outras partes têm o lugar delas no seletor de cima e dizem, na
própria tela, que ainda estão sendo construídas — aba vazia calada seria
pior que aviso.

O FLUXO DA ENTRADA, COMO O DONO DESENHOU
----------------------------------------
1. A tela abre só com a barra, e o cursor já nasce nela.
2. Bipou um código CADASTRADO → abre a ficha: foto, as variações (cada uma
   com o nome que ele escreveu e o quanto está entrando) e as variações de
   quantidade. Confirmou → volta para a barra.
3. Bipou um código que NÃO existe → "Cadastrar como produto novo?".
   Sim abre o cadastro com o código já preenchido; Não volta para a barra.
4. Produto sem código (óculos) → o Studio gera o código e a etiqueta.
5. Bipou de novo o MESMO código com a ficha aberta → abre "nova variação":
   é assim que se cadastram as três posições da bailarina.
"""
import html as _html

import streamlit as st

import estoque as E

MODOS = ("⬇ Entrada", "⬆ Saída", "✖ Quebra · Descarte · Devolução",
         "🧩 Kits", "📊 Painel", "📱 Contagem")
EM_CONSTRUCAO = {
    "⬆ Saída": "Parte 2",
    "✖ Quebra · Descarte · Devolução": "Parte 3",
    "🧩 Kits": "Parte 4",
    "📊 Painel": "Parte 5",
    "📱 Contagem": "Parte 6",
}

# O BIPE VAI PARA A BARRA, ESTEJA O CURSOR ONDE ESTIVER (dono, 11/11).
#
# O leitor é um teclado: ele "digita" o código no campo que tem o cursor e
# aperta Enter. Com o cursor na QUANTIDADE, o 6 que a pessoa tinha escrito
# viraria 67891234567895 — e o Enter confirmaria. A escuta abaixo reconhece o
# bipe pela VELOCIDADE (gente não digita 6 teclas a menos de 40 ms cada),
# devolve ao campo o que ele tinha antes, e entrega o código à barra.
#
# Mora NA PÁGINA (eval do pai), como a ponte do `clique.py`: a caixinha do
# componente some quando a tela troca, e a escuta iria junto. Registra UMA
# vez, e não faz nada em tela que não tem a barra.
_ESCUTA = r"""
if (!window.__msBipe) { window.__msBipe = true;
  var buf = '', t0 = 0, ult = 0, alvo = null, antes = null;
  var poe = function (el, v) {
    var proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement : HTMLInputElement;
    Object.getOwnPropertyDescriptor(proto.prototype, 'value').set.call(el, v);
    el.dispatchEvent(new Event('input', {bubbles: true}));
  };
  document.addEventListener('keydown', function (e) {
    var barra = document.querySelector('.st-key-est_bipe input');
    if (!barra) { buf = ''; return; }
    var agora = performance.now();
    if (e.key === 'Enter') {
      var bipe = buf.length >= 6 && (ult - t0) / Math.max(buf.length - 1, 1) < 40;
      if (bipe && document.activeElement !== barra) {
        e.preventDefault(); e.stopPropagation();
        if (alvo && antes !== null && 'value' in alvo) poe(alvo, antes);
        // O Enter vai DEPOIS de a barra receber o código, numa volta à
        // parte: medido no Chromium, com o Enter na mesma volta o campo
        // que perdeu o foco (a quantidade) gravava primeiro e o bipe se
        // perdia.
        var codigo = buf;
        barra.focus(); poe(barra, codigo);
        setTimeout(function () {
          if (barra.value !== codigo) poe(barra, codigo);
          barra.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter',
            keyCode: 13, which: 13, bubbles: true}));
          // E o campo perde o foco: o Streamlit grava o texto ao sair do
          // campo. Medido: com outra passada em curso (a da quantidade que
          // perdeu o foco) o Enter sintético era ignorado, e o bipe ficava
          // parado na barra. A barra volta a ter o foco na passada seguinte.
          barra.blur();
        }, 60);
      }
      buf = ''; return;
    }
    if (!e.key || e.key.length !== 1) return;
    if (agora - ult > 60) {
      buf = ''; t0 = agora; alvo = document.activeElement;
      antes = (alvo && 'value' in alvo) ? alvo.value : null;
    }
    buf += e.key; ult = agora;
  }, true);
}
"""

_FOCO = """<script>
// O cursor volta para a barra de bipe depois de cada passada — a não ser que
// a pessoa esteja digitando em outro campo (a quantidade, o nome). Roubar o
// foco de quem digita trocaria o número que ela estava escrevendo.
(function () {
  try { window.parent.eval(ESCUTA); } catch (err) {}
  const d = window.parent.document;
  setTimeout(function () {
    const i = d.querySelector('.st-key-est_bipe input');
    const a = d.activeElement;
    // Radio, caixinha e botão não são "digitar": o seletor de modo fica com
    // o foco depois do clique, e a barra precisa voltar a tê-lo.
    const texto = ['text', 'number', 'search', 'email', 'tel', 'password', ''];
    const digitando = a && a !== d.body && ((a.tagName === 'INPUT' &&
                      texto.indexOf(a.type || '') >= 0 && a !== i) ||
                      a.tagName === 'TEXTAREA' || a.isContentEditable);
    if (i && !digitando) i.focus();
  }, 120);
})();
/*NONCE*/
</script>"""


# ── peças puras de desenho ───────────────────────────────────────────────────

def _esc(t):
    return _html.escape(str(t or ""))


def foto_html(foto_id, lado=64):
    """A miniatura do Drive, ou o quadrado vazio. Pura."""
    import gdrive
    url = gdrive.url_thumbnail(foto_id, 300) if foto_id else None
    base = (f"width:{lado}px;height:{lado}px;border-radius:10px;flex:none;"
            f"background:#555;object-fit:cover")
    if url:
        return f'<img src="{_esc(url)}" style="{base}">'
    return (f'<div style="{base};display:flex;align-items:center;justify-content:center;'
            f'font-size:10px;color:#ccc">sem foto</div>')


def cabecalho_html(variacoes, saldo, codigo):
    """O topo da ficha: foto, nome, código do fornecedor, custo, registro. Pura."""
    p = variacoes[0]
    total = sum(saldo.get((v["id"], E.FISICO), 0) for v in variacoes)
    n = len(variacoes)
    var_txt = f" · {n} variações" if n > 1 or str(p.get("variacao") or "").strip() else ""
    custo = f'{E.numero(p.get("custo")):,.2f}'.replace(",", "X").replace(".", ",").replace("X", ".")
    return (f'<div style="display:flex;gap:14px;align-items:center;margin:4px 0 10px">'
            f'{foto_html(p.get("foto_id"), 88)}<div>'
            f'<div style="font-size:11px;color:#4CC38A;font-weight:800;letter-spacing:.12em">'
            f'✓ JÁ CADASTRADO · {_esc(codigo)}</div>'
            f'<div style="font-size:20px;font-weight:800">{_esc(p.get("nome"))}</div>'
            f'<div style="font-size:13px;color:#9AA3AE">{_esc(p.get("codigo_fornecedor") or "—")}'
            f' · custo R$ {custo}{var_txt} · em estoque: {total}</div>'
            f'<div style="font-size:13px;color:#9AA3AE">registrado em '
            f'{_esc(str(p.get("registrado_em") or "")[:10])} · '
            f'<span style="color:#f0c060">a idade conta daqui</span></div></div></div>')


def lote_txt(lote, por_id):
    """'14:02 · Bailarina: Braço para cima +6 · Sentada +6 · leo'. Pura."""
    partes = []
    for m in lote["linhas"]:
        p = por_id.get(str(m.get("produto_id")), {})
        partes.append(f'{E.nome_completo(p) or "produto apagado"} +{E.inteiro(m.get("qtd"))}')
    quando = str(lote.get("quando") or "")
    return f'{quando[-5:] if len(quando) >= 5 else quando} · ' + " · ".join(partes) + f' · {lote.get("quem", "")}'


def receita_txt(k, por_id):
    """'1× Braço para cima · 1× Sentada' de um código gerado. Pura."""
    return " · ".join(f'{q}× {E.nome_completo(por_id.get(pid, {})) or "?"}'
                      for pid, q in E.itens_do_codigo(k).items())


# ── estado ───────────────────────────────────────────────────────────────────

def _ao_bipar():
    """O leitor terminou o bipe (Enter). Guarda o código e limpa a barra.

    Roda como callback, ANTES de a barra ser desenhada de novo — é o único
    momento em que o Streamlit deixa trocar o valor dela.
    """
    ss = st.session_state
    cod = E.limpar_codigo(ss.get("est_bipe", ""))
    ss["est_bipe"] = ""
    if not cod:
        return
    if cod == ss.get("est_lido") and not ss.get("est_cadastrar"):
        ss["est_nova_var"] = True        # bipou de novo o mesmo: nova variação
        return
    _limpar_ficha()
    ss["est_lido"] = cod


def _limpar_ficha():
    ss = st.session_state
    for k in [k for k in ss.keys() if str(k).startswith(("est_q_", "est_n_", "est_cq_"))]:
        del ss[k]
    for k in ("est_lido", "est_cadastrar", "est_sem_codigo", "est_nova_var",
              "est_imprimir"):
        ss.pop(k, None)


def _voltar():
    _limpar_ficha()


def _avisar(msg, erro=False):
    st.session_state["est_aviso"] = (msg, erro)


def _quando():
    import placar_core as _pc
    return _pc.agora_br().strftime("%d/%m/%Y %H:%M")


# ── ações (callbacks) ────────────────────────────────────────────────────────

def _confirmar_entrada(variacoes, quem):
    ss = st.session_state
    try:
        itens = [(v, int(ss.get(f"est_q_{v['id']}", 0) or 0)) for v in variacoes]
        renomes = {}
        for v in variacoes:
            novo = str(ss.get(f"est_n_{v['id']}", v.get("variacao") or "")).strip()
            if novo and novo != str(v.get("variacao") or "").strip():
                renomes[v["id"]] = {"variacao": novo}
        linhas = E.linhas_de_entrada(itens, quem, _quando())
        if not linhas and not renomes:
            _avisar("Nada para gravar: todas as quantidades estão em zero.", True)
            return
        E.atualizar_produtos(renomes)
        E.gravar_movimentos(linhas)
        total = sum(q for _v, q in itens)
        _avisar(f"✓ Entrada gravada: {total} peça(s) de {variacoes[0].get('nome')}."
                if linhas else "✓ Nomes das variações atualizados.")
        _limpar_ficha()
    except Exception as e:
        _avisar(f"Não gravei a entrada — a planilha respondeu: {e}", True)


def _desfazer(lote, quem):
    try:
        _p, movs, _c = E.carregar()
        linhas = E.linhas_que_desfazem(lote, movs, quem, _quando())
        if not linhas:
            _avisar("Essa entrada já tinha sido desfeita.", True)
            return
        E.gravar_movimentos(linhas)
        _avisar("↶ Entrada desfeita: as peças saíram do estoque de novo.")
    except Exception as e:
        _avisar(f"Não desfiz — a planilha respondeu: {e}", True)


# ── blocos da tela ───────────────────────────────────────────────────────────

def _barra():
    c1, c2 = st.columns([4, 1.3])
    with c1:
        st.text_input("Bipe ou digite o código de barras", key="est_bipe",
                      on_change=_ao_bipar, placeholder="▌ bipe o código…",
                      label_visibility="collapsed")
    with c2:
        if st.button("➕ Produto sem código", key="est_btn_semcod", use_container_width=True,
                     help="Óculos e o que mais vier sem código: o Studio gera e imprime."):
            _limpar_ficha()
            st.session_state["est_sem_codigo"] = True
            st.session_state["est_cadastrar"] = True
    try:
        import streamlit.components.v1 as _comp
        st.session_state["_est_nonce"] = st.session_state.get("_est_nonce", 0) + 1
        import json as _json
        _comp.html(_FOCO.replace("NONCE", str(st.session_state["_est_nonce"]))
                   .replace("ESCUTA", _json.dumps(_ESCUTA)), height=0)
    except Exception:
        pass


def _ficha(variacoes, saldo, codigos, por_id, quem):
    cod = st.session_state["est_lido"]
    st.markdown(cabecalho_html(variacoes, saldo, cod), unsafe_allow_html=True)
    sem_nome = len(variacoes) == 1 and not str(variacoes[0].get("variacao") or "").strip()
    st.markdown("**Variações · o nome é você que escreve · quanto entra de cada**"
                if not sem_nome else "**Quanto está entrando**")
    for v in variacoes:
        c0, c1, c2 = st.columns([0.7, 4, 1.4])
        with c0:
            st.markdown(foto_html(v.get("foto_id"), 54), unsafe_allow_html=True)
        with c1:
            if sem_nome:
                st.markdown(f'**{_esc(v.get("nome"))}**  \nem estoque: '
                            f'{saldo.get((v["id"], E.FISICO), 0)}')
            else:
                st.text_input("Nome da variação", value=str(v.get("variacao") or ""),
                              key=f"est_n_{v['id']}", label_visibility="collapsed")
                st.caption(f"em estoque: {saldo.get((v['id'], E.FISICO), 0)}")
        with c2:
            st.number_input("entrando", min_value=0, step=1, value=0,
                            key=f"est_q_{v['id']}")
    total = sum(int(st.session_state.get(f"est_q_{v['id']}", 0) or 0) for v in variacoes)
    valor = sum(int(st.session_state.get(f"est_q_{v['id']}", 0) or 0) * E.numero(v.get("custo"))
                for v in variacoes)
    c1, c2, c3 = st.columns([3, 1.4, 1.2])
    c1.markdown(f"total entrando: **{total} peça(s) · R\\$ "
                f"{valor:,.2f}**".replace(",", "X").replace(".", ",").replace("X", "."))
    c2.button("CONFIRMAR ENTRADA", key="est_confirmar", type="primary",
              use_container_width=True, on_click=_confirmar_entrada,
              args=(variacoes, quem))
    c3.button("Voltar", key="est_voltar", use_container_width=True, on_click=_voltar)

    _nova_variacao(variacoes, quem)
    _editar_produto(variacoes, quem)
    _variacoes_de_quantidade(variacoes, codigos, por_id, quem)


def _nova_variacao(variacoes, quem):
    aberta = bool(st.session_state.get("est_nova_var"))
    with st.expander("➕ Nova variação — bipe o mesmo código de novo, escreva o nome e tire a foto",
                     expanded=aberta):
        p0 = variacoes[0]
        sem_nome = len(variacoes) == 1 and not str(p0.get("variacao") or "").strip()
        with st.form("est_form_var", clear_on_submit=True):
            nome_antigo = ""
            if sem_nome:
                nome_antigo = st.text_input(
                    "Nome da variação que JÁ existe (a primeira)",
                    help="O produto tinha uma variação só, sem nome. Para separar, as duas precisam de nome.")
            nome = st.text_input("Nome da nova variação (posição, cor…)")
            foto = st.file_uploader("Foto da variação", type=None, key="est_var_foto")
            qtd = st.number_input("Quantidade entrando agora", min_value=0, step=1, value=0)
            enviar = st.form_submit_button("Salvar variação", type="primary")
        if not enviar:
            return
        if not str(nome).strip() or (sem_nome and not str(nome_antigo).strip()):
            st.error("Escreva o nome da variação" + (" — das duas." if sem_nome else "."))
            return
        try:
            foto_id = ""
            if foto is not None:
                foto_id, erro = E.salvar_foto(foto.getvalue(), E.limpar_codigo(p0.get("ean")))
                if erro:
                    st.warning(f"A variação foi salva sem foto: {erro}")
            if sem_nome:
                E.atualizar_produtos({p0["id"]: {"variacao": str(nome_antigo).strip()}})
            novas = E.linhas_de_produto(p0.get("ean"), p0.get("codigo_fornecedor"), p0.get("nome"),
                                        E.numero(p0.get("custo")), [(nome, foto_id)], quem, _quando())
            E.gravar_produtos(novas)
            E.gravar_movimentos(E.linhas_de_entrada([(novas[0], int(qtd))], quem, _quando()))
            _avisar(f"✓ Variação «{str(nome).strip()}» criada" + (f", com {int(qtd)} peça(s)." if qtd else "."))
            st.session_state.pop("est_nova_var", None)
            st.rerun()
        except Exception as e:
            st.error(f"Não gravei a variação — a planilha respondeu: {e}")


def _editar_produto(variacoes, quem):
    with st.expander("✎ Editar produto (nome, código do fornecedor, custo, foto)"):
        p0 = variacoes[0]
        with st.form("est_form_edit"):
            nome = st.text_input("Produto", value=str(p0.get("nome") or ""))
            forn = st.text_input("Código do fornecedor", value=str(p0.get("codigo_fornecedor") or ""))
            custo = st.text_input("Preço de custo (R$)", value=f'{E.numero(p0.get("custo")):.2f}'.replace(".", ","))
            alvo = st.selectbox("Trocar a foto de", [E.nome_completo(v) for v in variacoes])
            foto = st.file_uploader("Nova foto (opcional)", type=None, key="est_edit_foto")
            enviar = st.form_submit_button("Salvar alterações")
        if not enviar:
            return
        try:
            mud = {v["id"]: {"nome": nome.strip(), "codigo_fornecedor": forn.strip(),
                             "custo": f"{E.numero(custo):.2f}"} for v in variacoes}
            if foto is not None:
                foto_id, erro = E.salvar_foto(foto.getvalue(), E.limpar_codigo(p0.get("ean")))
                if erro:
                    st.warning(f"A foto não foi trocada: {erro}")
                else:
                    v = variacoes[[E.nome_completo(x) for x in variacoes].index(alvo)]
                    mud[v["id"]]["foto_id"] = foto_id
            E.atualizar_produtos(mud)
            _avisar("✓ Produto atualizado. O custo novo vale para as próximas entradas.")
            st.rerun()
        except Exception as e:
            st.error(f"Não gravei — a planilha respondeu: {e}")


def _etiqueta(codigo, nome, sub=""):
    """A etiqueta para imprimir: o iframe imprime só ele mesmo."""
    import streamlit.components.v1 as _comp
    svg = E.svg_ean13(codigo, modulo=2, altura=56)
    _comp.html(
        f'<div style="font-family:sans-serif;background:#fff;color:#000;padding:8px;'
        f'display:inline-block;border-radius:6px"><div style="font-weight:700;font-size:13px">'
        f'{_esc(nome)}</div><div style="font-size:11px">{_esc(sub)}</div>{svg}</div>'
        f'<div><button onclick="window.print()" style="margin-top:6px;padding:6px 12px">'
        f'🖨 Imprimir etiqueta</button></div>', height=170)


def _variacoes_de_quantidade(variacoes, codigos, por_id, quem):
    ean = E.limpar_codigo(variacoes[0].get("ean"))
    meus = [k for k in codigos if E.limpar_codigo(k.get("produto_ean")) == ean
            and k.get("tipo") == "quantidade"]
    st.markdown("**Variações de quantidade · como é vendido (não mexe no estoque)**")
    if not meus:
        st.caption("Nenhuma ainda. Ex.: «Kit com 3, 1 de cada posição», «Pacote com 2».")
    for k in meus:
        c1, c2, c3 = st.columns([3, 2.4, 1])
        c1.markdown(f'**{_esc(k.get("nome"))}**  \n{_esc(receita_txt(k, por_id))}')
        c2.markdown(E.svg_ean13(k["codigo"], modulo=1, altura=34), unsafe_allow_html=True)
        if c3.button("🖨", key=f"est_pr_{k['codigo']}", help="Imprimir a etiqueta"):
            st.session_state["est_imprimir"] = k["codigo"]
        if st.session_state.get("est_imprimir") == k["codigo"]:
            _etiqueta(k["codigo"], k.get("nome"), receita_txt(k, por_id))
    with st.expander("➕ Adicionar variação de quantidade"):
        with st.form("est_form_qtd", clear_on_submit=True):
            nome = st.text_input("Nome (como aparece na venda)", placeholder="Kit com 3 (1 de cada posição)")
            st.caption("Quantas peças de cada variação saem com UM bipe deste código:")
            qts = {}
            for v in variacoes:
                qts[v["id"]] = st.number_input(E.nome_completo(v), min_value=0, step=1,
                                               value=1 if len(variacoes) == 1 else 0,
                                               key=f"est_cq_{v['id']}")
            enviar = st.form_submit_button("Salvar e gerar código", type="primary")
        if not enviar:
            return
        if not str(nome).strip() or not any(int(q) > 0 for q in qts.values()):
            st.error("Escreva o nome e ponha a quantidade de pelo menos uma variação.")
            return
        try:
            prods, _m, cods = E.carregar()
            novo = E.novo_codigo_interno(E.todos_os_codigos(prods, cods))
            E.gravar_codigo(E.linha_de_codigo(novo, "quantidade", nome, ean, qts, quem, _quando()))
            _avisar(f"✓ Código {novo} criado para «{str(nome).strip()}». Imprima pelo 🖨.")
            st.rerun()
        except Exception as e:
            st.error(f"Não gravei — a planilha respondeu: {e}")


def _pergunta(cod):
    st.markdown(
        f'<div style="padding:14px;border-radius:12px;background:#4a3a1a;margin:6px 0 10px">'
        f'<div style="color:#f0c060;font-weight:800">Este código não está cadastrado: {_esc(cod)}</div>'
        f'<div style="color:#E8EAED;font-weight:600;margin-top:4px">Cadastrar como produto novo?</div></div>',
        unsafe_allow_html=True)
    c1, c2, _ = st.columns([1.3, 1.3, 3])
    if c1.button("SIM, CADASTRAR", key="est_sim", type="primary", use_container_width=True):
        st.session_state["est_cadastrar"] = True
        st.rerun()
    c2.button("NÃO, BIPEI ERRADO", key="est_nao", use_container_width=True, on_click=_voltar)


def _cadastro(quem):
    ss = st.session_state
    sem_codigo = bool(ss.get("est_sem_codigo"))
    cod = ss.get("est_lido", "")
    titulo = ("PRODUTO SEM CÓDIGO · o Studio gera o código ao salvar" if sem_codigo
              else f"NÃO CADASTRADO · {cod}")
    st.markdown(f'<div style="font-size:11px;color:#f0c060;font-weight:800;letter-spacing:.12em">'
                f'{_esc(titulo)}</div>', unsafe_allow_html=True)
    with st.form("est_form_cad"):
        c1, c2 = st.columns([1, 2])
        with c1:
            foto = st.file_uploader("Foto do produto", type=None, key="est_cad_foto")
        with c2:
            forn = st.text_input("Código do fornecedor", placeholder="TRES-B131")
            nome = st.text_input("Produto", placeholder="Mini Yoga · conjunto")
        c3, c4 = st.columns(2)
        custo = c3.text_input("Preço de custo (R$)", placeholder="12,90")
        qtd = c4.number_input("Quantidade entrando", min_value=0, step=1, value=0)
        tem_var = st.checkbox("Tem variações com este mesmo código (posição, cor…)",
                              help="Marcado: escreva o nome desta primeira. Depois bipe o mesmo "
                                   "código de novo para cada variação.")
        var = st.text_input("Nome desta variação (se marcou acima)", placeholder="Braço para cima")
        enviar = st.form_submit_button("CADASTRAR E DAR ENTRADA", type="primary")
    st.button("Cancelar", key="est_cancelar", on_click=_voltar)
    if not enviar:
        return
    faltando = [r for r, v in (("o nome do produto", nome), ("o preço de custo", custo)) if not str(v).strip()]
    if tem_var and not str(var).strip():
        faltando.append("o nome da variação")
    if E.numero(custo, -1) < 0:
        faltando.append("um preço de custo que seja número")
    if faltando:
        st.error("Falta " + ", ".join(faltando) + ".")
        return
    try:
        prods, _m, cods = E.carregar()
        if sem_codigo:
            cod = E.novo_codigo_interno(E.todos_os_codigos(prods, cods))
        elif E.do_codigo(prods, cod):
            st.error("Este código acabou de ser cadastrado por outra pessoa. Bipe de novo.")
            return
        foto_id = ""
        if foto is not None:
            foto_id, erro = E.salvar_foto(foto.getvalue(), cod)
            if erro:
                st.warning(f"O produto foi salvo sem foto: {erro}")
        novas = E.linhas_de_produto(cod, forn, nome, E.numero(custo),
                                    [(var if tem_var else "", foto_id)], quem, _quando())
        E.gravar_produtos(novas)
        E.gravar_movimentos(E.linhas_de_entrada([(novas[0], int(qtd))], quem, _quando()))
        _limpar_ficha()
        _avisar(f"✓ «{nome.strip()}» cadastrado" + (f" com {int(qtd)} peça(s)." if qtd else "."))
        if sem_codigo:
            ss["est_etiqueta_nova"] = (cod, nome.strip())
        st.rerun()
    except Exception as e:
        st.error(f"Não gravei o cadastro — a planilha respondeu: {e}")


def _ultimas(movs, por_id, quem):
    lotes = E.ultimos_lotes(movs, E.ENTRADA, 5)
    if not lotes:
        return
    st.markdown("**Últimas entradas**")
    for lt in lotes:
        c1, c2 = st.columns([6, 1])
        txt = lote_txt(lt, por_id)
        c1.markdown(f"~~{_esc(txt)}~~ · desfeita" if lt["desfeito"] else _esc(txt))
        if not lt["desfeito"]:
            c2.button("↶ desfazer", key=f"est_desf_{lt['lote']}", on_click=_desfazer,
                      args=(lt["lote"], quem))


# ── a página ─────────────────────────────────────────────────────────────────

def pagina(usuario_logado=None):
    quem = str(usuario_logado or "").strip()
    st.markdown("### 📦 Estoque")
    modo = st.segmented_control("Modo", MODOS, default=MODOS[0], key="est_modo",
                                label_visibility="collapsed") or MODOS[0]
    if modo in EM_CONSTRUCAO:
        st.info(f"**{modo}** é a {EM_CONSTRUCAO[modo]} do Estoque: o layout está aprovado "
                f"(11/11) e ela está sendo construída. Por enquanto, só a Entrada funciona.")
        return
    _entrada(quem)


def _entrada(quem):
    ss = st.session_state
    aviso = ss.pop("est_aviso", None)
    if aviso:
        (st.error if aviso[1] else st.success)(aviso[0])
    nova = ss.pop("est_etiqueta_nova", None)
    if nova:
        st.markdown("**Código gerado — imprima a etiqueta e cole no produto:**")
        _etiqueta(nova[0], nova[1])

    try:
        prods, movs, codigos = E.carregar()
    except Exception as e:
        st.error(f"Não consegui ler o estoque na planilha: {e}")
        return
    _barra()
    por_id = {p["id"]: p for p in prods}
    saldo = E.saldos(movs)
    cod = ss.get("est_lido")

    if ss.get("est_cadastrar"):
        _cadastro(quem)
    elif cod:
        variacoes = E.do_codigo(prods, cod)
        gerado = E.codigo_gerado(codigos, cod)
        if variacoes:
            _ficha(variacoes, saldo, codigos, por_id, quem)
        elif gerado:
            st.warning(f"**{gerado.get('nome')}** é um código de VENDA ({receita_txt(gerado, por_id)}). "
                       f"Na entrada, bipe o código do produto.")
            st.button("Voltar", key="est_voltar_g", on_click=_voltar)
        else:
            _pergunta(cod)
    else:
        st.caption("Bipe um código. Já cadastrado: abre a ficha. Não cadastrado: o Studio "
                   "pergunta se é produto novo.")
    _ultimas(movs, por_id, quem)


if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    prods = E.linhas_de_produto("7891234567895", "MBLN-06", "Bailarina <resina> + base",
                                18.4, [("Braço para cima", ""), ("Sentada", "")], "leo",
                                "11/11/2026 14:02")
    ent = E.linhas_de_entrada([(prods[0], 6), (prods[1], 2)], "leo", "11/11/2026 14:03")
    por_id = {p["id"]: p for p in prods}
    cab = cabecalho_html(prods, E.saldos(ent), "7891234567895")
    ok("cabecalho_html: nome escapado, total do estoque, custo em reais",
       "&lt;resina&gt;" in cab and "em estoque: 8" in cab and "R$ 18,40" in cab
       and "2 variações" in cab)
    lt = E.ultimos_lotes(ent, E.ENTRADA)[0]
    ok("lote_txt: hora, cada variação com a quantidade, e quem",
       lote_txt(lt, por_id) == "14:03 · Bailarina <resina> + base · Braço para cima +6 · "
                               "Bailarina <resina> + base · Sentada +2 · leo")
    k = E.linha_de_codigo("2000000000015", "quantidade", "Kit com 2", "7891234567895",
                          {prods[0]["id"]: 1, prods[1]["id"]: 1}, "leo", "x")
    ok("receita_txt: as peças de um código gerado",
       receita_txt(k, por_id).startswith("1× Bailarina <resina> + base · Braço para cima"))
    ok("foto_html: sem foto vira quadrado, com foto vira miniatura do Drive",
       "sem foto" in foto_html("") and "thumbnail?id=abc" in foto_html("abc"))
    ok("o foco não rouba o campo de quem está digitando",
       "digitando" in _FOCO and "est_bipe" in _FOCO and "location" not in _FOCO)
    ok("modos: as seis partes aprovadas, e só a Entrada pronta",
       len(MODOS) == 6 and set(EM_CONSTRUCAO) == set(MODOS) - {MODOS[0]})
    print("\n" + ("TUDO OK" if not falhas else f"{falhas} FALHA(S)"))
    raise SystemExit(1 if falhas else 0)
