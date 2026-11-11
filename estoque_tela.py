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

# Parte 3: o motivo da baixa.
MOTIVOS = {"💔 Quebra": E.QUEBRA, "🗑 Descarte": E.DESCARTE, "🎁 Doação": E.DOACAO,
           "↩ Devolução": E.DEVOLUCAO}
NOME_MOTIVO = {E.QUEBRA: "Quebra", E.DESCARTE: "Descarte", E.DOACAO: "Doação",
               E.DEVOLUCAO: "Devolução"}

# Saída (Parte 2): para onde vai o que foi bipado.
DESTINOS = {"🛒 Venda": E.VENDA, "🚚 Envio para o Full": E.ENVIO_FULL}

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
    if ss.get("est_modo") == "⬆ Saída":
        _bipe_na_saida(cod)
        return
    if ss.get("est_modo") == MODOS[2]:
        ss["est_bx_cod"] = cod
        ss.pop("est_bx_var", None)
        return
    if ss.get("est_modo") == "🧩 Kits":
        _bipe_no_kit(cod)
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
            _avisar("Isso já tinha sido desfeito.", True)
            return
        E.gravar_movimentos(linhas)
        _avisar("↶ Desfeito: o estoque voltou ao que era antes.")
    except Exception as e:
        _avisar(f"Não desfiz — a planilha respondeu: {e}", True)


# ── blocos da tela ───────────────────────────────────────────────────────────

def _barra(saida=False):
    c1, c2 = st.columns([4, 1.3])
    with c1:
        st.text_input("Bipe ou digite o código de barras", key="est_bipe",
                      on_change=_ao_bipar,
                      placeholder=("🟢 pronto para bipar — não precisa clicar aqui" if saida
                                   else "▌ bipe o código…"),
                      label_visibility="collapsed")
    with c2:
        if not saida and st.button("➕ Produto sem código", key="est_btn_semcod", use_container_width=True,
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


# ── SAÍDA (Parte 2) ──────────────────────────────────────────────────────────

def _baixar(itens, destino, quem, rotulo):
    """Grava a saída de um bipe e deixa o aviso com o que saiu. Levanta erro."""
    prods, movs, _c = E.carregar()
    linhas = E.linhas_de_saida(itens, destino, quem, _quando(), obs=rotulo)
    if not linhas:
        return None
    E.gravar_movimentos(linhas)
    lote = linhas[0]["lote"]
    st.session_state.setdefault("est_sessao", []).append(lote)
    saldo = E.saldos(movs + linhas)
    zerados = [E.nome_completo(p) for p, _q in itens if saldo.get((p["id"], E.FISICO), 0) <= 0]
    para = " → Full" if destino == E.ENVIO_FULL else ""
    msg = f"✓ Saiu{para}: {rotulo}"
    if zerados:
        msg += " · ⚠️ estoque físico ZEROU: " + ", ".join(zerados)
    _avisar(msg, False)
    return lote


def _destino():
    return DESTINOS.get(st.session_state.get("est_dest") or "🛒 Venda", E.VENDA)


def _bipe_na_saida(cod):
    """Um bipe na Saída. Callback: roda antes de a tela ser desenhada."""
    ss = st.session_state
    quem = ss.get("est_quem", "")
    try:
        prods, movs, codigos = E.carregar()
        itens, variacoes = E.itens_do_bipe(prods, codigos, cod)
        if variacoes:
            ss["est_janela"] = cod           # vários modelos: a tela pergunta qual
            return
        if not itens:
            _avisar(f"Código {cod} não está cadastrado. Cadastre na ⬇ Entrada.", True)
            return
        k = E.codigo_gerado(codigos, cod)
        rotulo = (k.get("nome") if k else E.nome_completo(itens[0][0]))
        corr = ss.pop("est_corrigir", None)
        if corr:
            desf = E.linhas_que_desfazem(corr, movs, quem, _quando())
            E.gravar_movimentos(desf)
        _baixar(itens, _destino(), quem, rotulo + (" (no lugar do bipe errado)" if corr else ""))
        ss.pop("est_janela", None)
    except Exception as e:
        _avisar(f"Não gravei a saída — a planilha respondeu: {e}", True)


def _saiu_modelo(pid, quem):
    """Clique num modelo da janela: sai 1 dele."""
    ss = st.session_state
    try:
        prods, movs, _c = E.carregar()
        p = next(x for x in prods if x["id"] == pid)
        corr = ss.pop("est_corrigir", None)
        if corr:
            E.gravar_movimentos(E.linhas_que_desfazem(corr, movs, quem, _quando()))
        _baixar([(p, 1)], _destino(), quem, E.nome_completo(p))
        ss.pop("est_janela", None)
    except Exception as e:
        _avisar(f"Não gravei a saída — a planilha respondeu: {e}", True)


def _fechar_janela():
    st.session_state.pop("est_janela", None)


def _corrigir(lote):
    st.session_state["est_corrigir"] = lote
    _avisar("Bipe agora o código CERTO: o errado volta ao estoque e o certo sai no lugar.")


def _mudar_qtd(lote, quem):
    """Troca quantas vezes aquele bipe saiu: desfaz e grava de novo, vezes N."""
    ss = st.session_state
    try:
        n = int(ss.get(f"est_mq_{lote}", 1) or 0)
        prods, movs, _c = E.carregar()
        por_id = {p["id"]: p for p in prods}
        linhas = [m for m in movs if str(m.get("lote")) == lote and m.get("local") == E.FISICO]
        if not linhas:
            return
        destino = linhas[0].get("tipo")
        E.gravar_movimentos(E.linhas_que_desfazem(lote, movs, quem, _quando()))
        if n > 0:
            itens = [(por_id[m["produto_id"]], -E.inteiro(m["qtd"]) * n) for m in linhas
                     if m["produto_id"] in por_id]
            _baixar(itens, destino, quem, f"{n}× " + ", ".join(E.nome_completo(p) for p, _q in itens))
        else:
            _avisar("↶ Desfeito: o estoque voltou ao que era antes.")
    except Exception as e:
        _avisar(f"Não gravei — a planilha respondeu: {e}", True)


def rotulo_do_lote(linhas_fisico, por_id):
    """O nome do que saiu: o do kit quando foi kit, senão o do produto. Pura.

    O kit grava o nome dele em `obs` (`_baixar`); sem isso a lista mostrava
    «Bailarina · Braço para cima, Bailarina · Sentada» para um bipe só.
    """
    if not linhas_fisico:
        return "?"
    obs = str(linhas_fisico[0].get("obs") or "").replace(" (no lugar do bipe errado)", "").strip()
    if len(linhas_fisico) > 1 and obs:
        return obs
    return ", ".join(E.nome_completo(por_id.get(m.get("produto_id"), {})) or "?" for m in linhas_fisico)


def janela_html(variacoes, saldo):
    """O título da janela de modelos. Pura."""
    return (f'<div style="font-size:11px;font-weight:800;letter-spacing:.14em;color:#f0c060">'
            f'ESTE CÓDIGO TEM MAIS DE UM MODELO · BIPE NA TELA OU CLIQUE NO QUE ESTÁ SAINDO</div>'
            f'<div style="font-size:18px;font-weight:800;margin:4px 0 8px">'
            f'{_esc(variacoes[0].get("nome"))} <span style="color:#9AA3AE;font-size:13px">'
            f'{_esc(variacoes[0].get("codigo_fornecedor"))}</span></div>')


def _janela(variacoes, saldo, codigos, por_id, quem):
    with st.container(border=True):
        st.markdown(janela_html(variacoes, saldo), unsafe_allow_html=True)
        for v in variacoes:
            c0, c1, c2 = st.columns([0.7, 3.4, 1.6])
            c0.markdown(foto_html(v.get("foto_id"), 54), unsafe_allow_html=True)
            c1.markdown(f'**{_esc(v.get("variacao") or v.get("nome"))}**  \nsai 1 peça · em estoque: '
                        f'{saldo.get((v["id"], E.FISICO), 0)}')
            c2.button("SAIU ESTE", key=f"est_sv_{v['id']}", use_container_width=True,
                      on_click=_saiu_modelo, args=(v["id"], quem))
        for k in E.codigos_da_janela(variacoes, codigos):
            c1, c2 = st.columns([3, 2.4])
            c1.markdown(f'**{_esc(k.get("nome"))}**  \n{_esc(receita_txt(k, por_id))}')
            c2.markdown(E.svg_ean13(k["codigo"], modulo=2, altura=44), unsafe_allow_html=True)
        st.caption("Saindo 2 iguais: clique (ou bipe) 2 vezes.")
        st.button("Fechar", key="est_fecha_jan", on_click=_fechar_janela)


def _lateral_saida(movs, por_id, quem):
    st.markdown("**Últimos 5 bipados · clique para corrigir**")
    # SÓ OS BIPES DE QUEM ESTÁ NA TELA: com duas pessoas empacotando, uma
    # não deve corrigir o bipe da outra sem perceber.
    lotes = E.ultimos_lotes([m for m in movs if m.get("quem") == quem or m.get("tipo") == E.DESFEITO],
                            (E.VENDA, E.ENVIO_FULL), 5)
    if not lotes:
        st.caption("Nada saiu ainda.")
    for lt in lotes:
        fis = [m for m in lt["linhas"] if m.get("local") == E.FISICO]
        nomes = rotulo_do_lote(fis, por_id)
        q = sum(-E.inteiro(m["qtd"]) for m in fis)
        para = " → Full" if lt["linhas"][0].get("tipo") == E.ENVIO_FULL else ""
        hora = str(lt.get("quando") or "")[-5:]
        rot = f"{hora} · {nomes} −{q}{para}" + (" · desfeito" if lt["desfeito"] else "")
        if lt["desfeito"]:
            st.caption("~~" + rot + "~~")
            continue
        with st.expander(rot, expanded=st.session_state.get("est_corrigir") == lt["lote"]):
            p = por_id.get(fis[0]["produto_id"], {}) if fis else {}
            st.markdown(foto_html(p.get("foto_id"), 48), unsafe_allow_html=True)
            st.button("🔁 Trocar pelo código certo", key=f"est_tr_{lt['lote']}",
                      on_click=_corrigir, args=(lt["lote"],), use_container_width=True)
            c1, c2 = st.columns([1, 1.3])
            c1.number_input("vezes", min_value=0, step=1, value=1, key=f"est_mq_{lt['lote']}",
                            help="Quantas vezes este bipe saiu. 0 = desfaz.")
            c2.button("Salvar", key=f"est_sq_{lt['lote']}", on_click=_mudar_qtd,
                      args=(lt["lote"], quem), use_container_width=True)
            st.button("↶ desfazer", key=f"est_desf_s_{lt['lote']}", on_click=_desfazer,
                      args=(lt["lote"], quem), use_container_width=True)
    sess = set(st.session_state.get("est_sessao", []))
    desf = E.lotes_desfeitos(movs)
    das = [m for m in movs if str(m.get("lote")) in sess and str(m.get("lote")) not in desf
           and m.get("local") == E.FISICO]
    pecas = sum(-E.inteiro(m["qtd"]) for m in das)
    custo = sum(-E.inteiro(m["qtd"]) * E.numero(m.get("custo_unit")) for m in das)
    st.markdown(f"**{pecas}** peça(s) nesta sessão · **R\\$ {custo:,.0f}** a custo"
                .replace(",", "."))


def _saida(quem):
    ss = st.session_state
    st.segmented_control("Saída para", list(DESTINOS), default="🛒 Venda", key="est_dest")
    aviso = ss.pop("est_aviso", None)
    if aviso:
        (st.error if aviso[1] else st.success)(aviso[0])
    if ss.get("est_corrigir"):
        st.warning("🔁 Corrigindo um bipe: **bipe o código certo** (ou clique no modelo). ")
    try:
        prods, movs, codigos = E.carregar()
    except Exception as e:
        st.error(f"Não consegui ler o estoque na planilha: {e}")
        return
    _barra(saida=True)
    por_id = {p["id"]: p for p in prods}
    saldo = E.saldos(movs)
    principal, lateral = st.columns([2.2, 1])
    with principal:
        jan = ss.get("est_janela")
        variacoes = E.do_codigo(prods, jan) if jan else []
        if variacoes:
            _janela(variacoes, saldo, codigos, por_id, quem)
        else:
            st.caption("Cada bipe é 1 unidade e sai na hora. Código com mais de um modelo abre a "
                       "janela para escolher. Código de kit ou de quantidade tira todos os itens dele.")
    with lateral:
        _lateral_saida(movs, por_id, quem)


# ── QUEBRA · DESCARTE · DOAÇÃO · DEVOLUÇÃO (Parte 3) ────────────────────────

def _rs(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def linha_baixa_txt(linhas, por_id):
    """'11/11 · Bailarina · Sentada · Devolução → voltou ao estoque · +1 · — · my'. Pura."""
    m0 = linhas[0]
    p = por_id.get(m0.get("produto_id"), {})
    perda = [m for m in linhas if m.get("tipo") in E.PERDAS]
    if m0.get("tipo") == E.DEVOLUCAO:
        mot = "Devolução → descarte" if perda else "Devolução → voltou ao estoque"
    else:
        mot = NOME_MOTIVO.get(m0.get("tipo"), m0.get("tipo"))
        if m0.get("local") == E.FULL:
            mot += " (Full)"
    q = (-sum(E.inteiro(m["qtd"]) for m in perda) if perda
         else sum(E.inteiro(m["qtd"]) for m in linhas))
    sinal = "−" if perda else "+"
    valor = sum(-E.inteiro(m["qtd"]) * E.numero(m.get("custo_unit")) for m in perda)
    obs = str(m0.get("obs") or "").replace("devolução que voltou ruim.", "").strip()
    return (f'{str(m0.get("quando") or "")[:5]} · {E.nome_completo(p) or "?"} · {mot}'
            + (f" · {obs}" if obs else "") + f" · {sinal}{q} · "
            + (_rs(valor) if perda else "—") + f' · {m0.get("quem", "")}')


def quadros_perda_html(bm):
    """Os quatro quadros do mês, em grade 2×2 — `st.metric` cortava o valor
    em «R…» na coluna estreita (visto no navegador, 11/11). Pura."""
    q = [(rot, _rs(bm["por_motivo"][m]), "#E5534B") for rot, m in MOTIVOS.items() if m in E.PERDAS]
    q.append(("↩ Voltou ao estoque", f"{bm['voltaram']} peça(s)", "#4CC38A"))
    return ('<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:6px 0 10px">'
            + "".join(f'<div style="padding:10px;border-radius:10px;background:#2c2c2c">'
                      f'<div style="font-size:11px;color:#9AA3AE">{r}</div>'
                      f'<div style="font-size:18px;font-weight:800;color:{c}">{v}</div></div>'
                      for r, v, c in q) + "</div>")


def _gravar_baixa(p, motivo, quem, q, volta, local, obs, pedido, foto):
    foto_id = ""
    if foto is not None:
        foto_id, erro = E.salvar_foto(foto.getvalue(), f"baixa_{E.limpar_codigo(p.get('ean'))}")
        if erro:
            st.warning(f"Gravei sem a foto: {erro}")
    linhas = E.linhas_de_baixa(p, q, motivo, quem, _quando(), local=local, volta=volta,
                               obs=obs, pedido=pedido, foto_id=foto_id)
    E.gravar_movimentos(linhas)
    return linhas


def _baixas(quem):
    ss = st.session_state
    rot = st.segmented_control("Motivo", list(MOTIVOS), default="💔 Quebra", key="est_motivo")
    motivo = MOTIVOS.get(rot or "💔 Quebra", E.QUEBRA)
    aviso = ss.pop("est_aviso", None)
    if aviso:
        (st.error if aviso[1] else st.success)(aviso[0])
    try:
        prods, movs, codigos = E.carregar()
    except Exception as e:
        st.error(f"Não consegui ler o estoque na planilha: {e}")
        return
    _barra(saida=True)
    por_id = {p["id"]: p for p in prods}
    saldo = E.saldos(movs)
    esq, dir_ = st.columns([1.2, 1])
    with esq:
        cod = ss.get("est_bx_cod")
        var = E.do_codigo(prods, cod) if cod else []
        if cod and not var:
            st.error(f"Código {cod} não está cadastrado. Cadastre na ⬇ Entrada.")
        elif not var:
            st.caption("Bipe o produto. Abre a ficha com quantidade, foto do estado e observação.")
        else:
            _ficha_baixa(var, motivo, saldo, quem)
    with dir_:
        _perdas_do_mes(movs, por_id, quem)


def _ficha_baixa(var, motivo, saldo, quem):
    ss = st.session_state
    if len(var) > 1:
        nomes = [str(v.get("variacao") or "").strip() or E.nome_completo(v) for v in var]
        esc = st.radio("Qual modelo?", nomes, key="est_bx_var", horizontal=True)
        p = var[nomes.index(esc)] if esc in nomes else var[0]
    else:
        p = var[0]
    fis, full = saldo.get((p["id"], E.FISICO), 0), saldo.get((p["id"], E.FULL), 0)
    st.markdown(
        f'<div style="display:flex;gap:12px;align-items:center;margin:6px 0">'
        f'{foto_html(p.get("foto_id"), 72)}<div><div style="font-size:11px;font-weight:800;'
        f'letter-spacing:.12em;color:#f0c060">BIPADO · {NOME_MOTIVO[motivo].upper()}</div>'
        f'<div style="font-size:18px;font-weight:800">{_esc(E.nome_completo(p))}</div>'
        f'<div style="font-size:13px;color:#9AA3AE">{_esc(p.get("codigo_fornecedor") or "—")} · custo '
        f'{_rs(E.numero(p.get("custo")))} · físico {fis} · Full {full}</div></div></div>',
        unsafe_allow_html=True)
    with st.form("est_form_bx", clear_on_submit=True):
        volta, local = False, E.FISICO
        if motivo == E.DEVOLUCAO:
            r = st.radio("O produto voltou…", ["✓ BOM · volta ao estoque", "✖ RUIM · descarte"],
                         horizontal=True)
            volta = r.startswith("✓")
            st.caption("Bom: soma no físico e não é perda. Ruim: a peça já tinha saído na venda — "
                       "o estoque não muda, e ela conta como perda.")
        else:
            lr = st.radio("Saiu de qual estoque?", ["físico", "Full"], horizontal=True)
            local = E.FULL if lr == "Full" else E.FISICO
        c1, c2 = st.columns([1, 2])
        q = c1.number_input("Quantidade", min_value=1, step=1, value=1)
        pedido = c2.text_input("Plataforma / pedido (opcional)", placeholder="Mercado Livre · 2000012345678")
        c3, c4 = st.columns([1, 2])
        foto = c3.file_uploader("Foto do estado (opcional)", type=None, key="est_bx_foto")
        obs = c4.text_input("Observação", placeholder="caixa amassada, peça inteira")
        enviar = st.form_submit_button("CONFIRMAR", type="primary")
    if not enviar:
        return
    try:
        _gravar_baixa(p, motivo, quem, int(q), volta, local, obs.strip(), pedido.strip(), foto)
        oque = ("voltou ao estoque" if motivo == E.DEVOLUCAO and volta else
                f"perda de {_rs(int(q) * E.numero(p.get('custo')))}")
        _avisar(f"✓ {NOME_MOTIVO[motivo]}: {int(q)}× {E.nome_completo(p)} — {oque}.")
        ss.pop("est_bx_cod", None)
        st.rerun()
    except Exception as e:
        st.error(f"Não gravei — a planilha respondeu: {e}")


def _perdas_do_mes(movs, por_id, quem):
    import placar_core as _pc
    hoje = _pc.agora_br()
    bm = E.baixas_do_mes(movs, hoje.year, hoje.month)
    meses = ("", "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO",
             "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO")
    st.markdown(f"**{meses[hoje.month].capitalize()} · perda a custo: {_rs(bm['perda'])}**"
                .replace("$", "\\$"))
    st.markdown(quadros_perda_html(bm), unsafe_allow_html=True)
    if not bm["lotes"]:
        st.caption("Nenhuma baixa neste mês.")
    for linhas in bm["lotes"][:30]:
        lote = str(linhas[0]["lote"])
        with st.expander(linha_baixa_txt(linhas, por_id)):
            m0 = linhas[0]
            if m0.get("foto_id"):
                st.markdown(foto_html(m0["foto_id"], 120), unsafe_allow_html=True)
            if m0.get("pedido"):
                st.caption(f"Pedido: {m0['pedido']}")
            st.button("↶ desfazer esta baixa", key=f"est_desf_b_{lote}", on_click=_desfazer,
                      args=(lote, quem))


# ── KITS (Parte 4) ───────────────────────────────────────────────────────────

def _bipe_no_kit(cod):
    """Bipe montando um kit: entra o item; bipou de novo, vira 2."""
    ss = st.session_state
    try:
        prods, _m, codigos = E.carregar()
    except Exception as e:
        _avisar(f"Não consegui ler o estoque: {e}", True)
        return
    if E.codigo_gerado(codigos, cod):
        _avisar("Esse é um código de kit/quantidade. No kit, bipe o código de cada PRODUTO.", True)
        return
    var = E.do_codigo(prods, cod)
    if not var:
        _avisar(f"Código {cod} não está cadastrado. Cadastre na ⬇ Entrada.", True)
    elif len(var) == 1:
        _somar_no_kit(var[0]["id"])
    else:
        ss["est_kit_escolha"] = cod       # vários modelos: a tela pergunta qual


def _somar_no_kit(pid):
    ss = st.session_state
    kit = ss.setdefault("est_kit", {})
    kit[pid] = kit.get(pid, 0) + 1
    ss[f"est_kq_{pid}"] = kit[pid]
    ss.pop("est_kit_escolha", None)


def _tirar_do_kit(pid):
    ss = st.session_state
    ss.setdefault("est_kit", {}).pop(pid, None)
    ss.pop(f"est_kq_{pid}", None)


def _limpar_kit():
    ss = st.session_state
    for pid in list(ss.get("est_kit", {})):
        ss.pop(f"est_kq_{pid}", None)
    for k in ("est_kit", "est_kit_escolha", "est_kit_nome"):
        ss.pop(k, None)


def kit_card_html(k, por_id, saldo):
    """O kit cadastrado: foto, nome, itens e quantos dá para montar. Pura."""
    itens = E.itens_do_codigo(k)
    n, faltam = E.da_para_montar(itens, saldo)
    lista = " · ".join((f"{q}× " if q > 1 else "") + E.nome_completo(por_id.get(pid, {}))
                       for pid, q in itens.items())
    falta_txt = (" · falta " + ", ".join(E.nome_completo(por_id.get(pid, {})) for pid in faltam)
                 if faltam else "")
    cor = "#E5534B" if n == 0 else "#E8EAED"
    return (f'<div style="display:flex;gap:10px;align-items:center">{foto_html(k.get("foto_id"), 52)}'
            f'<div style="min-width:0"><b>{_esc(k.get("nome"))}</b>'
            f'<div style="font-size:12px;color:#9AA3AE">{_esc(lista)}</div>'
            f'<div style="font-size:12px;color:{cor}">dá para montar: {n}{_esc(falta_txt)} · custo '
            f'{_rs(E.custo_da_receita(itens, por_id))}</div></div></div>')


def _kits(quem):
    ss = st.session_state
    aviso = ss.pop("est_aviso", None)
    if aviso:
        (st.error if aviso[1] else st.success)(aviso[0])
    nova = ss.pop("est_etiqueta_nova", None)
    try:
        prods, movs, codigos = E.carregar()
    except Exception as e:
        st.error(f"Não consegui ler o estoque na planilha: {e}")
        return
    _barra(saida=True)
    por_id = {p["id"]: p for p in prods}
    saldo = E.saldos(movs)
    esq, dir_ = st.columns([1.2, 1])
    with esq:
        _criar_kit(prods, codigos, por_id, saldo, nova, quem)
    with dir_:
        _kits_cadastrados(codigos, por_id, saldo)


def _criar_kit(prods, codigos, por_id, saldo, nova, quem):
    # Função própria, e não bloco dentro do `with`: o `return` do kit vazio
    # saía da tela INTEIRA e a lista de kits cadastrados sumia (navegador, 11/11).
    ss = st.session_state
    st.markdown("**Criar kit · 1) bipe os itens  2) nome e foto  3) gerar código**")
    if nova:
        st.markdown("**Kit criado — imprima a etiqueta:**")
        _etiqueta(nova[0], nova[1])
    esc = ss.get("est_kit_escolha")
    var = E.do_codigo(prods, esc) if esc else []
    if var:
        st.warning("Este código tem mais de um modelo. Qual vai no kit?")
        for v in var:
            st.button(str(v.get("variacao") or E.nome_completo(v)), key=f"est_ke_{v['id']}",
                      on_click=_somar_no_kit, args=(v["id"],))
    kit = ss.get("est_kit", {})
    for pid in list(kit):
        p = por_id.get(pid)
        if not p:
            continue
        c0, c1, c2, c3 = st.columns([0.7, 3, 1.2, 0.5])
        c0.markdown(foto_html(p.get("foto_id"), 44), unsafe_allow_html=True)
        c1.markdown(f"**{_esc(E.nome_completo(p))}**  \nem estoque: {saldo.get((pid, E.FISICO), 0)}")
        kit[pid] = int(c2.number_input("no kit", min_value=1, step=1, key=f"est_kq_{pid}"))
        c3.button("✕", key=f"est_kx_{pid}", on_click=_tirar_do_kit, args=(pid,), help="Tirar do kit")
    if not kit:
        st.caption("Bipe o primeiro item do kit. Bipou o mesmo de novo: vira 2 no kit.")
        return
    nome = st.text_input("Nome do kit", key="est_kit_nome", placeholder="Kit Embaralhador + 2 baralhos")
    foto = st.file_uploader("Foto do kit (anexar)", type=None, key="est_kit_foto")
    n, _f = E.da_para_montar(kit, saldo)
    st.caption(f"custo do kit: {_rs(E.custo_da_receita(kit, por_id))} · dá para montar: {n} · "
               "o kit NÃO entra no estoque: ele é só a receita.".replace("$", "\\$"))
    c1, c2 = st.columns([1.6, 1])
    salvar = c1.button("SALVAR E GERAR CÓDIGO", type="primary", key="est_kit_salvar",
                       use_container_width=True)
    c2.button("Cancelar", key="est_kit_cancelar", on_click=_limpar_kit, use_container_width=True)
    if salvar:
        if not str(nome).strip():
            st.error("Escreva o nome do kit.")
        else:
            try:
                novo = E.novo_codigo_interno(E.todos_os_codigos(prods, codigos))
                foto_id = ""
                if foto is not None:
                    foto_id, erro = E.salvar_foto(foto.getvalue(), f"kit_{novo}")
                    if erro:
                        st.warning(f"O kit foi salvo sem foto: {erro}")
                E.gravar_codigo(E.linha_de_codigo(novo, "kit", nome, "", dict(kit), quem,
                                                  _quando(), foto_id=foto_id))
                ss["est_etiqueta_nova"] = (novo, str(nome).strip())
                _avisar(f"✓ Kit «{str(nome).strip()}» criado com o código {novo}.")
                _limpar_kit()
                st.rerun()
            except Exception as e:
                st.error(f"Não gravei o kit — a planilha respondeu: {e}")


def _kits_cadastrados(codigos, por_id, saldo):
    ss = st.session_state
    st.markdown("**Kits cadastrados**")
    kits = [k for k in codigos if k.get("tipo") == "kit"]
    if not kits:
        st.caption("Nenhum kit ainda.")
    for k in kits:
        with st.container(border=True):
            st.markdown(kit_card_html(k, por_id, saldo), unsafe_allow_html=True)
            st.markdown(E.svg_ean13(k["codigo"], modulo=1, altura=30), unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            if c1.button("🖨 imprimir", key=f"est_kp_{k['codigo']}", use_container_width=True):
                ss["est_imprimir"] = k["codigo"]
            with c2.popover("✎ editar", use_container_width=True):
                novo_nome = st.text_input("Nome", value=str(k.get("nome") or ""),
                                          key=f"est_kn_{k['codigo']}")
                if st.button("Salvar nome", key=f"est_ks_{k['codigo']}"):
                    try:
                        E.atualizar_codigos({k["codigo"]: {"nome": novo_nome.strip()}})
                        _avisar("✓ Nome do kit atualizado.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Não gravei — a planilha respondeu: {e}")
            if ss.get("est_imprimir") == k["codigo"]:
                _etiqueta(k["codigo"], k.get("nome"), " · ".join(
                    E.nome_completo(por_id.get(pid, {})) for pid in E.itens_do_codigo(k)))


# ── a página ─────────────────────────────────────────────────────────────────

def pagina(usuario_logado=None):
    quem = str(usuario_logado or "").strip()
    st.session_state["est_quem"] = quem      # os callbacks do bipe gravam o nome
    st.markdown("### 📦 Estoque")
    modo = st.segmented_control("Modo", MODOS, default=MODOS[0], key="est_modo",
                                label_visibility="collapsed") or MODOS[0]
    if modo in EM_CONSTRUCAO:
        st.info(f"**{modo}** é a {EM_CONSTRUCAO[modo]} do Estoque: o layout está aprovado "
                f"(11/11) e ela está sendo construída. Por enquanto, só a Entrada funciona.")
        return
    if modo == "⬆ Saída":
        _saida(quem)
        return
    if modo == MODOS[2]:
        _baixas(quem)
        return
    if modo == "🧩 Kits":
        _kits(quem)
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
    ok("modos: as seis partes aprovadas; Entrada, Saída, Baixas e Kits prontas",
       len(MODOS) == 6 and set(EM_CONSTRUCAO) == set(MODOS) - set(MODOS[:4]))
    ok("destinos da saída: venda e envio ao Full",
       set(DESTINOS.values()) == {E.VENDA, E.ENVIO_FULL})
    _kit = E.linhas_de_saida([(prods[0], 1), (prods[1], 1)], E.VENDA, "leo", "x", obs="Kit com 2")
    ok("rotulo_do_lote: kit pelo nome do kit; produto pelo nome dele",
       rotulo_do_lote(_kit, por_id) == "Kit com 2"
       and rotulo_do_lote(_kit[:1], por_id) == "Bailarina <resina> + base · Braço para cima")
    _bx = E.linhas_de_baixa(prods[1], 1, E.DEVOLUCAO, "my", "11/11/2026 15:00", volta=False,
                            obs="arranhado")
    ok("linha_baixa_txt: devolução ruim é descarte, com valor e obs",
       linha_baixa_txt(_bx, por_id) == "11/11 · Bailarina <resina> + base · Sentada · Devolução → "
                                       "descarte · arranhado · −1 · R$ 18,40 · my")
    _bx2 = E.linhas_de_baixa(prods[0], 2, E.DEVOLUCAO, "my", "11/11/2026 15:00", volta=True)
    _bx3 = E.linhas_de_baixa(prods[0], 1, E.QUEBRA, "leo", "11/11/2026 15:00", local=E.FULL)
    ok("linha_baixa_txt: devolução boa soma sem valor; quebra do Full diz Full",
       " · Devolução → voltou ao estoque · +2 · — · my" in linha_baixa_txt(_bx2, por_id)
       and "Quebra (Full) · −1 · R$ 18,40" in linha_baixa_txt(_bx3, por_id))
    _qh = quadros_perda_html({"por_motivo": {E.QUEBRA: 42.0, E.DESCARTE: 0.0, E.DOACAO: 9.8},
                              "voltaram": 1})
    ok("quadros_perda_html: os quatro quadros, com o valor inteiro",
       _qh.count("border-radius:10px") == 4 and "R$ 42,00" in _qh and "R$ 9,80" in _qh
       and "1 peça(s)" in _qh)
    _kk = E.linha_de_codigo("2000000000022", "kit", "Kit <A>", "", {prods[0]["id"]: 1, prods[1]["id"]: 2},
                            "leo", "x")
    _sk = {(prods[0]["id"], E.FISICO): 5, (prods[1]["id"], E.FISICO): 1}
    _kc = kit_card_html(_kk, por_id, _sk)
    ok("kit_card_html: nome escapado, 2× no item dobrado, não monta e diz o que falta, custo",
       "Kit &lt;A&gt;" in _kc and "2× Bailarina" in _kc and "dá para montar: 0 · falta" in _kc
       and "Sentada" in _kc.split("falta")[1] and "R$ 55,20" in _kc and "#E5534B" in _kc)
    ok("janela_html: nome escapado e o aviso de vários modelos",
       "&lt;resina&gt;" in janela_html(prods, {}) and "MAIS DE UM MODELO" in janela_html(prods, {}))
    print("\n" + ("TUDO OK" if not falhas else f"{falhas} FALHA(S)"))
    raise SystemExit(1 if falhas else 0)
