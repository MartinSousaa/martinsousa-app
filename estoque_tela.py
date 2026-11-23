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
         "🧩 Kits", "📊 Estoque cadastrado", "📱 Contagem", "📈 Painel")
EM_CONSTRUCAO = {}

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
        barra.focus(); poe(barra, codigo);  // rola de propósito: a ficha do bipe abre logo abaixo da barra
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
    // preventScroll (dono, 13/11): o foco voltava e o navegador rolava a
    // tela até a barra — digitar a quantidade lá embaixo e clicar fora
    // jogava a pessoa para o topo. O leitor digita na barra do mesmo jeito.
    if (i && !digitando) i.focus({preventScroll: true});
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
    sku = E.normalizar_sku(p.get("sku"))
    sku_txt = (f' · SKU {_esc(sku)}' if sku else ' · <span style="color:#f0c060">sem SKU</span>')
    if E.normalizar_sku(p.get("sku_atacado")):
        sku_txt += (f' · atacado {_esc(E.normalizar_sku(p.get("sku_atacado")))} '
                    f'{_rs(E.custo_de(p, E.ATACADO))}')
    forn_txt = f' · {_esc(p.get("fornecedor"))}' if str(p.get("fornecedor") or "").strip() else ""
    return (f'<div style="display:flex;gap:14px;align-items:center;margin:4px 0 10px">'
            f'{foto_html(E.foto_principal(p), 88)}<div>'
            f'<div style="font-size:11px;color:#4CC38A;font-weight:800;letter-spacing:.12em">'
            f'✓ JÁ CADASTRADO · {_esc(codigo)}</div>'
            f'<div style="font-size:20px;font-weight:800">{_esc(p.get("nome"))}</div>'
            f'<div style="font-size:13px;color:#9AA3AE">{_esc(p.get("codigo_fornecedor") or "—")}'
            f'{forn_txt} · custo R$ {custo}{sku_txt}{var_txt} · em estoque: {total}</div>'
            f'<div style="font-size:13px;color:#9AA3AE">registrado em '
            f'{_esc(str(p.get("registrado_em") or "")[:10])} · '
            f'<span style="color:#f0c060">a idade conta daqui</span></div></div></div>')


def estoque_txt(saldo, pid):
    """'em estoque: físico 4 · Full ML1 2 · Full Shopee 1 1'. Pura."""
    partes = [f"físico {saldo.get((pid, E.FISICO), 0)}"]
    partes += [f"{nome} {saldo[(pid, loc)]}" for loc, nome in E.FULLS.items() if saldo.get((pid, loc))]
    return "em estoque: " + " · ".join(partes)


def receita_txt(k, por_id):
    """'1× Braço para cima · 1× Sentada' de um código gerado. Pura."""
    return " · ".join(f'{q}× {E.nome_completo(por_id.get(pid, {})) or "?"}'
                      for pid, q in E.itens_do_codigo(k).items())


# ── estado ───────────────────────────────────────────────────────────────────

def _ao_bipar():
    """O leitor terminou o bipe (Enter). Guarda o código e limpa a barra.

    Roda como callback, ANTES de a barra ser desenhada de novo — é o único
    momento em que o Streamlit deixa trocar o valor dela.

    A BARRA TAMBÉM PROCURA (dono, 12/11: "em todas as opções de estoque seja
    possível procurar o produto por qualquer informação"). Código cadastrado
    age como bipe, igual antes. Qualquer outra coisa — nome, SKU, código do
    fornecedor, pedaço do código de barras — vira busca, e o produto achado
    é ESCOLHIDO com um clique (`_escolheu`), que age como o bipe dele.
    """
    ss = st.session_state
    bruto = " ".join(str(ss.get("est_bipe", "")).split())
    ss["est_bipe"] = ""
    ss.pop("est_procura", None)
    cod = E.limpar_codigo(bruto)
    if not cod:
        return
    try:
        prods, _m, codigos = E.carregar()
    except Exception:
        prods, codigos = None, []
    if prods is not None and not eh_codigo_cadastrado(prods, codigos, cod) and procurar(bruto):
        # A tela vai junto: o resultado vale só onde foi procurado.
        ss["est_procura"] = {"texto": bruto, "modo": ss.get("est_modo"),
                             "eans": [p.get("ean") for p in buscar_produtos(prods, bruto)]}
        return
    _despachar(cod)


def procurar(bruto):
    """Este texto é BUSCA (e não um código novo para cadastrar)? Pura.

    Código de barras de verdade é só número e tem 8 dígitos ou mais: esse,
    desconhecido, continua oferecendo o cadastro. Letra, espaço, hífen ou
    número curto é busca.
    """
    c = E.limpar_codigo(bruto)
    return bool(c) and not (c.isdigit() and len(c) >= 8)


def eh_codigo_cadastrado(prods, codigos, cod):
    """O código é de um produto ou de um código gerado (kit, quantidade)? Pura."""
    return bool(E.do_codigo(prods, cod) or E.codigo_gerado(codigos, cod))


def _escolheu(ean):
    """Clique num produto achado pela busca da barra: age como o bipe dele."""
    st.session_state.pop("est_procura", None)
    _despachar(E.limpar_codigo(ean))


def _despachar(cod):
    """O que o bipe faz, em cada tela."""
    ss = st.session_state
    # Qualquer bipe, em qualquer modo, encerra a pergunta do kit: ela vale só
    # para a unidade que acabou de sair.
    ss.pop("est_kit_pergunta", None)
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
    if ss.get("est_modo") == "📱 Contagem":
        _bipe_na_contagem(cod)
        return
    if cod == ss.get("est_lido") and not ss.get("est_cadastrar"):
        ss["est_nova_var"] = True        # bipou de novo o mesmo: nova variação
        return
    _limpar_ficha()
    ss["est_lido"] = cod


def _limpar_ficha():
    ss = st.session_state
    for k in [k for k in ss.keys() if str(k).startswith(("est_q_", "est_n_", "est_cq_", "est_cad_s",
                                                         "est_cad_c", "est_ed_", "est_cad_forn",
                                                         "est_cad_n", "est_cad_q", "est_cad_t",
                                                         "est_cad_v", "est_cad_m"))]:
        del ss[k]
    for k in ("est_lido", "est_cadastrar", "est_sem_codigo", "est_nova_var",
              "est_imprimir"):
        ss.pop(k, None)


def _voltar():
    _limpar_ficha()
    _voltar_ao_modo()


# CÓDIGO DESCONHECIDO EM QUALQUER TELA (dono, 11/11, pelo iPhone): a Contagem
# dizia "não está cadastrado" e parava — o cadastro só existia na Entrada. Agora
# toda tela que bipa oferece cadastrar ali mesmo, e volta para onde estava.
def _ir_cadastrar(cod):
    ss = st.session_state
    volta = ss.get("est_modo")
    _limpar_ficha()
    if volta and volta != MODOS[0]:
        ss["est_volta_modo"] = volta
    ss["est_modo"] = MODOS[0]
    ss["est_lido"] = cod
    ss["est_cadastrar"] = True


def _voltar_ao_modo():
    """Depois do cadastro (ou do cancelar), volta para a tela de onde veio.

    O seletor de modo já foi desenhado quando o cadastro grava: trocar o valor
    dele agora o Streamlit recusa. Fica pendente e é aplicado no começo da
    próxima passada, antes de o seletor existir.
    """
    ss = st.session_state
    volta = ss.pop("est_volta_modo", None)
    if volta:
        ss["est_modo_pendente"] = volta


def _mostrar_procura():
    """Os produtos achados pelo texto digitado na barra. Clique = bipe."""
    ss = st.session_state
    pr = ss.get("est_procura")
    if not pr or pr.get("modo") != ss.get("est_modo"):
        return
    try:
        prods = E.carregar()[0]
    except Exception:
        return
    por_ean = {E.limpar_codigo(p.get("ean")): p for p in E.ativos(prods)}
    achados = [por_ean[E.limpar_codigo(e)] for e in pr["eans"] if E.limpar_codigo(e) in por_ean]
    if not achados:
        st.warning(f"Nada encontrado com «{pr['texto']}» — procure por nome, SKU, código do "
                   "fornecedor ou código de barras.")
        return
    st.caption(f"Achados com «{pr['texto']}» — clique no produto (age como o bipe dele):")
    for p in achados:
        rot = " · ".join(x for x in (str(p.get("nome") or ""), str(p.get("codigo_fornecedor") or ""),
                                      E.normalizar_sku(p.get("sku")), E.limpar_codigo(p.get("ean"))) if x)
        st.button(rot, key=f"est_pr_{E.limpar_codigo(p.get('ean'))}", on_click=_escolheu,
                  args=(p.get("ean"),), use_container_width=True)


def _mostrar_desconhecido():
    ss = st.session_state
    _mostrar_procura()
    cod = ss.pop("est_desconhecido", None)
    if not cod:
        return
    st.error(f"Código {cod} não está cadastrado.")
    st.button("➕ Cadastrar este código", key="est_cad_desc", type="primary",
              on_click=_ir_cadastrar, args=(cod,))


def _avisar(msg, erro=False):
    st.session_state["est_aviso"] = (msg, erro)


def foto_da_tela(foto, nome):
    """(foto_id, aviso) de um campo de foto. O aviso NÃO vai para st.warning:
    toda gravação aqui termina em st.rerun(), que apagava o aviso — sobrava
    só o «✓ salvo», e a foto que o Drive recusou parecia salva (17/11). Quem
    chama junta o aviso à mensagem de `_avisar`, que sobrevive ao rerun."""
    if foto is None:
        return "", ""
    fid, erro = E.salvar_foto(foto.getvalue(), nome)
    if not erro:
        return fid or "", ""
    return fid or "", ("⚠ FOTO: " + erro) if fid else ("⚠ A FOTO NÃO FOI SALVA: " + erro)


def _com_foto(msg, aviso_foto):
    """Junta o aviso da foto à mensagem e põe a mensagem em vermelho. Pura."""
    return (msg + " · " + aviso_foto, True) if aviso_foto else (msg, False)


def _quando():
    import placar_core as _pc
    return _pc.agora_br().strftime("%d/%m/%Y %H:%M")


# ── ações (callbacks) ────────────────────────────────────────────────────────

def _local_da_entrada():
    nome = st.session_state.get("est_onde_entra") or "Físico"
    return next((k for k, v in E.FULLS.items() if v == nome), E.FISICO)


def _origem_da_entrada():
    return E.ATACADO if st.session_state.get("est_origem_entra") == "Atacado" else E.VAREJO


def renomeacoes(variacoes, digitados):
    """{id: {"variacao": nome}} só das variações cujo nome a pessoa MUDOU. Pura.

    O campo MOSTRA o nome capitalizado (dono, 13/11). Comparar o que está no
    campo com o gravado cru renomeava a variação na planilha a cada
    CONFIRMAR, sem ninguém ter mexido no nome (o @ pegou: «Braço para cima»
    virou «Braço para Cima»). Renomear é o texto diferente do que a tela
    mostrou."""
    out = {}
    for v in variacoes:
        mostrado = E.capitalizar(str(v.get("variacao") or "").strip())
        novo = str(digitados.get(v["id"]) if digitados.get(v["id"]) is not None else mostrado).strip()
        if novo and novo != mostrado:
            out[v["id"]] = {"variacao": novo}
    return out


def _confirmar_entrada(variacoes, quem):
    ss = st.session_state
    try:
        itens = [(v, int(ss.get(f"est_q_{v['id']}", 0) or 0)) for v in variacoes]
        renomes = renomeacoes(variacoes, {v["id"]: ss.get(f"est_n_{v['id']}") for v in variacoes})
        local = _local_da_entrada()
        origem = _origem_da_entrada()
        linhas = E.linhas_de_entrada(itens, quem, _quando(), local=local, origem=origem)
        if not linhas and not renomes:
            _avisar("Nada para gravar: todas as quantidades estão em zero.", True)
            return
        E.atualizar_produtos(renomes)
        E.gravar_movimentos(linhas)
        total = sum(q for _v, q in itens)
        _avisar(f"✓ Entrada gravada no {E.NOME_LOCAL[local]}: {total} peça(s) de {variacoes[0].get('nome')}"
                f" · {origem}."
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
    # A CÂMERA EM TODA TELA QUE BIPA (dono, 11/11: "está acrescentando o
    # scanner pelo celular na aba de entrada?"). Ela morava só na Contagem —
    # a Forma 1 desta base. Mora aqui, junto da barra, e a chave é uma só:
    # ligada numa tela, continua ligada ao trocar de tela.
    if st.toggle("📷 Usar a câmera do celular", key="est_cam"):
        import streamlit.components.v1 as _comp
        _comp.html(_CAMERA, height=330)
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


def _rot_col(txt):
    """O rótulo de uma coluna da lista de variações. Pura."""
    return f'<div style="font-size:12px;color:#9AA3AE;font-weight:700">{_esc(txt)}</div>'


def _abrir_nova_variacao():
    st.session_state["est_nova_var"] = True


def _ficha(variacoes, saldo, codigos, por_id, quem, movs=None):
    """A ficha do produto JÁ cadastrado (dono, 13/11): abre como o bipe da
    vez da saída — o quadro grande à esquerda, as últimas entradas à direita."""
    cod = st.session_state["est_lido"]
    principal, lateral = st.columns([1.15, 1])
    with lateral:
        with st.container(border=True):
            _ultimas(movs or [], por_id, quem)
    with principal:
        _ficha_principal(variacoes, saldo, codigos, por_id, quem, cod)


def _ficha_principal(variacoes, saldo, codigos, por_id, quem, cod):
    st.markdown(ficha_entrada_html(variacoes, saldo, cod), unsafe_allow_html=True)
    # LOGO ABAIXO DO QUADRO (dono, 16/11): «não tem botão para editar o SKU,
    # incluir SKU de varejo… foto e tudo mais». Tinha — no fim da página,
    # depois do CONFIRMAR, fora da tela. Edição que ninguém acha não existe.
    _editar_produto(variacoes, quem)
    sem_nome = len(variacoes) == 1 and not str(variacoes[0].get("variacao") or "").strip()
    # ALINHADO (dono, 13/11): os rótulos ficam numa linha de cabeçalho só, e
    # cada linha tem um campo de UMA altura por coluna — com o rótulo
    # «entrando» em cima do número, ele descia e não batia com o nome.
    larg = [0.7, 3, 1.3, 1.4]
    # Respiro (dono, 13/11): o cabeçalho colava no quadro verde.
    st.markdown('<div style="height:14px"></div>', unsafe_allow_html=True)
    cab = st.columns(larg)
    cab[1].markdown(_rot_col("Variação" if not sem_nome else "Produto"), unsafe_allow_html=True)
    cab[2].markdown(_rot_col("Em estoque"), unsafe_allow_html=True)
    cab[3].markdown(_rot_col("Entrando"), unsafe_allow_html=True)
    for v in variacoes:
        c0, c1, c2, c3 = st.columns(larg, vertical_alignment="center")
        c0.markdown(foto_html(v.get("foto_id"), 54), unsafe_allow_html=True)
        if sem_nome:
            c1.markdown(f'**{_esc(E.capitalizar(v.get("nome")))}**')
        else:
            c1.text_input("Nome da variação", value=E.capitalizar(str(v.get("variacao") or "")),
                          key=f"est_n_{v['id']}", label_visibility="collapsed")
        c2.markdown(_esc(estoque_txt(saldo, v["id"]).replace("em estoque: ", "")))
        c3.number_input("entrando", min_value=0, step=1, value=None,
                        key=f"est_q_{v['id']}", label_visibility="collapsed")
    # Logo abaixo da última variação (dono, 13/11), e o quadro dela abre ali
    # — com respiro: o botão encostava na foto da última linha.
    st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
    st.button("➕ Nova variação", key="est_nova_var_b", on_click=_abrir_nova_variacao)
    _nova_variacao(variacoes, quem)
    st.segmented_control("Onde está entrando", ["Físico"] + list(E.FULLS.values()), default="Físico",
                         key="est_onde_entra",
                         help="Produto que JÁ está no Full e não dá para bipar: escolha o Full e digite a quantidade.")
    st.segmented_control("Esta compra é", ["Varejo", "Atacado"], default="Varejo", key="est_origem_entra",
                         help="Cada uma tem o seu SKU e o seu custo. Na saída, o varejo sai primeiro.")
    total = sum(int(st.session_state.get(f"est_q_{v['id']}", 0) or 0) for v in variacoes)
    valor = sum(int(st.session_state.get(f"est_q_{v['id']}", 0) or 0) * E.custo_de(v, _origem_da_entrada())
                for v in variacoes)
    st.markdown(f"total entrando: **{total} peça(s) · R\\$ "
                f"{valor:,.2f}**".replace(",", "X").replace(".", ",").replace("X", "."))
    c2, c3 = st.columns([2, 1])
    c2.button("CONFIRMAR ENTRADA", key="est_confirmar", type="primary",
              use_container_width=True, on_click=_confirmar_entrada,
              args=(variacoes, quem))
    c3.button("Voltar", key="est_voltar", use_container_width=True, on_click=_voltar)

    _variacoes_de_quantidade(variacoes, codigos, por_id, quem)


def blocos_de_variacao(blocos):
    """([(nome, qtd, foto)], erro) dos quadros de variação nova. Pura.

    Quadro todo vazio é ignorado (o «➕» a mais que ninguém preencheu).
    Quadro com quantidade ou foto e sem nome é erro: a peça não tem para
    onde ir. Nome repetido entre os quadros também.
    """
    fora, vistos = [], set()
    for n, (nome, qtd, foto) in enumerate(blocos, start=1):
        nome = " ".join(str(nome or "").split())
        qtd = int(qtd or 0)
        if not nome:
            if qtd or foto is not None:
                return [], f"Variação {n}: falta o nome."
            continue
        if nome.lower() in vistos:
            return [], f"A variação «{nome}» está escrita duas vezes."
        vistos.add(nome.lower())
        fora.append((nome, qtd, foto))
    if not fora:
        return [], "Escreva o nome da variação."
    return fora, ""


def _ch_var(campo, i):
    """A chave do quadro `i`. A rodada (`est_var_k`) muda ao salvar: os
    quadros nascem vazios, inclusive o da foto, que não se apaga à mão."""
    return f"est_var_{campo}_{st.session_state.get('est_var_k', 0)}_{i}"


def _mais_um_quadro_de_variacao():
    st.session_state["est_var_n"] = int(st.session_state.get("est_var_n") or 1) + 1


def pai_sem_nome(variacoes):
    """A linha SEM nome de um produto que tem variações com nome — o
    «produto em si», que não é peça de verdade. None se não há. Pura."""
    sem = [v for v in variacoes if not str(v.get("variacao") or "").strip()]
    com = [v for v in variacoes if str(v.get("variacao") or "").strip()]
    return sem[0] if len(sem) == 1 and (com or len(variacoes) == 1) else None


def _zerar_pai(pai, quem):
    """Zera o produto sem nome e o tira da lista: o estoque passa a ser o das
    variações. Devolve o aviso. Efeito: grava. Produto que entra num kit não
    é tocado — o kit tiraria peça de uma linha que sumiu."""
    _p, movs, codigos = E.carregar()
    if E.kits_com(codigos, pai["id"]):
        return (f"«{E.nome_completo(pai)}» entra num kit: o estoque dele NÃO foi zerado — "
                "troque o kit para as variações primeiro.")
    zera = E.linhas_de_zerar(pai, movs, quem, _quando(), "zerado: o estoque passou para as variações")
    if zera:
        E.gravar_movimentos(zera)
    E.atualizar_produtos({pai["id"]: {"ativo": "0"}})
    n = -sum(int(m["qtd"]) for m in zera)
    return f"o produto sem variação foi zerado ({n} peça(s)) — o estoque agora é o das variações"


def _zerar_pai_agora(pai, quem):
    try:
        _avisar("✓ " + _zerar_pai(pai, quem))
    except Exception as e:
        _avisar(f"Não zerei — a planilha respondeu: {e}", erro=True)


def _fechar_nova_variacao():
    ss = st.session_state
    ss.pop("est_nova_var", None)
    ss["est_var_n"] = 1
    ss["est_var_k"] = int(ss.get("est_var_k") or 0) + 1


def _nova_variacao(variacoes, quem, sufixo_ed="", botoes=True):
    # Abre pelo botão «➕ Nova variação» ou bipando o mesmo código de novo.
    ss = st.session_state
    if not ss.get("est_nova_var"):
        return
    with st.container(border=True):
        st.markdown("**➕ Nova variação** — escreva o nome e tire a foto")
        # VÁRIAS DE UMA VEZ (dono, 17/11: «cadastrei a primeira, tem que ter
        # um botão Nova Variação para já cadastrar a próxima sem ter que
        # salvar e abrir novamente»). Sem `st.form`: o «➕» acrescenta um
        # quadro sem perder o que foi digitado nos outros. Um campo de nome
        # só: «a primeira já é a variação» — o produto que existe fica igual.
        n = int(ss.get("est_var_n") or 1)
        for i in range(n):
            c1, c2, c3 = st.columns([2, 1, 2], vertical_alignment="bottom")
            c1.text_input("Nome da variação (posição, cor…)" if i == 0 else f"Variação {i + 1}",
                          key=_ch_var("nome", i))
            c2.number_input("Quantidade entrando", min_value=0, step=1, value=None, key=_ch_var("qtd", i))
            c3.file_uploader("Foto", type=None, key=_ch_var("foto", i))
        st.button("➕ Mais uma variação", key="est_var_mais", on_click=_mais_um_quadro_de_variacao)
        if not botoes:            # dentro do quadro do produto: o «Salvar tudo» grava
            return
        a, b = st.columns(2)
        a.button("Salvar variação" if n == 1 else f"Salvar as {n} variações", key="est_var_salvar",
                 type="primary", use_container_width=True,
                 on_click=_salvar_produto, args=(variacoes, quem, sufixo_ed))
        # Clicou errado (dono, 17/11): sair sem salvar.
        b.button("Cancelar", key="est_var_cancelar", use_container_width=True,
                 on_click=_fechar_nova_variacao)


def _fechar_ed_entrada():
    """Fecha o «✎ editar» da entrada (Cancelar, ou depois de salvar)."""
    st.session_state["est_ent_ed"] = None


def _pf_ed(variacoes, sufixo):
    """O prefixo das chaves do «✎ Editar» deste produto nesta tela."""
    return f"est_ed_{E.limpar_codigo(variacoes[0].get('ean'))}{sufixo}_"


def _iniciais_ed(p0):
    """O que os campos do «✎ Editar» mostram ao abrir, como texto. Pura."""
    return {"sku": str(p0.get("sku") or ""),
            # Só atacado (dono, 16/11): o custo base É o do atacado; mostrado
            # como «Custo varejo», parecia cadastrado sozinho.
            "custo": ("" if E.so_atacado(p0) else f'{E.numero(p0.get("custo")):.2f}'.replace(".", ",")),
            "sku_at": str(p0.get("sku_atacado") or ""),
            "custo_at": (f'{E.numero(p0.get("custo_atacado")):.2f}'.replace(".", ",")
                         if str(p0.get("custo_atacado") or "").strip() else ""),
            "nome": str(p0.get("nome") or ""), "fornecedor": str(p0.get("fornecedor") or ""),
            "forn": str(p0.get("codigo_fornecedor") or "")}


def edicao_mudou(iniciais, digitados, tem_foto):
    """O «✎ Editar» tem alguma coisa para gravar? Pura. Sem mudança, o
    «Salvar» das variações não regrava o produto (nem cobra SKU dele)."""
    return tem_foto or any(str(digitados.get(k) or "").strip() != str(v or "").strip()
                           for k, v in iniciais.items())


def _ch_foto_ed(pf):
    return f"{pf}foto_{st.session_state.get(pf + 'k', 0)}"


def _editar_produto(variacoes, quem, sufixo="", aberto=False, fechar=False, saldo=None, entrada=None):
    """O cadastro inteiro do produto. `sufixo` separa as chaves: o mesmo
    produto pode estar aberto na ficha E no «✎ editar» das últimas entradas
    na mesma tela (dono, 17/11) — chave repetida derruba a tela.

    SEM `st.form` (dono, 17/11: «coloquei a foto do produto e das variações
    e cliquei em salvar, só salvou o da variação»). Dentro de um form o que
    se digita só existe depois do botão DELE; agora os campos ficam na
    sessão e os dois «Salvar» (este e o das variações) gravam tudo."""
    ss = st.session_state
    # NO ESTOQUE CADASTRADO, UM QUADRO SÓ (dono, 17/11: «tem que estar tudo
    # em um quadrado só para alterar tudo que preciso e salvar uma vez só no
    # final»): produto, foto de capa, cada variação (nome e foto) e as
    # variações novas — um «Salvar tudo».
    painel = saldo is not None
    # A QUANTIDADE DA ENTRADA DENTRO DO QUADRO (dono, 18/11: «abre o campo de
    # estoque em cima… eu desço para o campo das informações e não acho o
    # estoque»): no «✎ editar» da Entrada, quantidade e produto num quadro só,
    # com um «Salvar» só.
    caixa = (st.container(border=True) if painel or entrada else
             st.expander("✎ Editar produto — SKU varejo e atacado, custo, nome, fornecedor, foto",
                         expanded=aberto))
    with caixa:
        p0 = variacoes[0]
        pf = _pf_ed(variacoes, sufixo)
        ss[pf + "painel"] = painel
        if entrada:
            _quantidades_da_entrada(entrada)
        if painel:
            st.markdown("**✎ Produto** — altere o que precisar e salve tudo de uma vez no fim")
            # O CÓDIGO À VISTA (dono, 17/11: «cadastrei sem código, o sistema
            # gerou um, preciso vê-lo… preciso gerar um kit com ele»).
            _cod = E.limpar_codigo(p0.get("ean"))
            c_a, c_b = st.columns([3, 1], vertical_alignment="center")
            c_a.markdown(f"Código de barras **{_esc(_cod)}**"
                         + (" · gerado pelo Studio" if eh_codigo_do_studio(_cod) else ""))
            if c_b.toggle("🖨 Etiqueta", key=f"{pf}etq"):
                _etiqueta(_cod, E.capitalizar(p0.get("nome")))
        ini = _iniciais_ed(p0)
        # A chave leva o código: dois produtos abertos em seguida não dividem
        # o que foi digitado em um.
        for k in ("nome", "fornecedor", "forn"):
            ss.setdefault(pf + k, ini[k])
        ss[pf + "ini"] = ini
        # A mesma linha do cadastro, 30% · 40% · 30% (dono, 23/11).
        e1, e2, e3 = st.columns([3, 4, 3])
        e1.text_input("Código do fornecedor", key=pf + "forn")
        e2.text_input("Produto", key=pf + "nome")
        e3.text_input("Fornecedor", key=pf + "fornecedor", placeholder="nome do fornecedor")
        # SKU e custo embaixo da linha do produto, como no cadastro.
        _campos_sku(pf, {k: ini[k] for k in ("sku", "custo", "sku_at", "custo_at")})
        if painel:
            st.file_uploader("Foto do produto (a que aparece na lista)", type=None, key=_ch_foto_ed(pf))
            _variacoes_do_painel(variacoes, saldo, quem, pf)
        else:
            # A chave muda com o número de variações: a lista ganha opção nova.
            st.selectbox("Trocar a foto de", [E.nome_completo(v) for v in variacoes],
                         key=f"{pf}alvo_{len(variacoes)}")
            st.file_uploader("Nova foto (opcional)", type=None, key=_ch_foto_ed(pf))
        a, b = st.columns(2)
        a.button("💾 Salvar tudo" if painel else "Salvar alterações", key=f"{pf}salvar", type="primary",
                 use_container_width=True,
                 on_click=_salvar_produto, args=(variacoes, quem, sufixo, fechar, entrada))
        # Cancelar (dono, 17/11): os campos voltam ao que está gravado.
        b.button("Cancelar", key=f"{pf}cancelar", use_container_width=True,
                 on_click=_cancelar_edicao, args=(pf, fechar))


def _ch_qe(lote, i):
    return f"est_ent_q_{lote}_{i}"


def _quantidades_da_entrada(entrada):
    """As quantidades desta entrada, no topo do quadro do produto."""
    lote, linhas = entrada
    st.markdown("**✎ Quantidade que entrou** — 0 tira a linha da entrada")
    for i, m, p in linhas:
        onde = E.NOME_LOCAL.get(m.get("local"), "físico") if m.get("local") != E.FISICO else "físico"
        a, b = st.columns([3, 1.2], vertical_alignment="center")
        a.markdown(f'{_esc(E.nome_completo(p) or "produto apagado")} · {_esc(onde)} · '
                   f'{_esc(E.origem_de(m))}')
        b.number_input("quantidade certa", min_value=0, step=1, value=E.inteiro(m.get("qtd")),
                       key=_ch_qe(lote, i), label_visibility="collapsed")
    st.markdown("**✎ Produto**")


def quantidades_mudadas(linhas, digitados):
    """{índice: nova} só das linhas cuja quantidade digitada mudou. Pura.
    Campo que não está na tela não entra: ausente NÃO é zero (zero tira a
    linha da entrada)."""
    return {i: int(digitados[i]) for i, m, _p in linhas
            if digitados.get(i) is not None and int(digitados[i]) != E.inteiro(m.get("qtd"))}


def _cancelar_edicao(pf, fechar=False):
    """Desfaz o digitado no «✎ Editar»: as chaves saem e renascem do gravado."""
    ss = st.session_state
    rodada = int(ss.get(pf + "k") or 0) + 1        # lida ANTES: ela também sai abaixo
    for k in [k for k in ss.keys() if str(k).startswith(pf)]:
        del ss[k]
    ss[pf + "k"] = rodada
    if fechar:
        _fechar_ed_entrada()
    _fechar_nova_variacao()
    ss.pop("est_pn_excluir", None)


def edicoes_de_variacao(variacoes, nomes, fotos):
    """({id: {"variacao": novo}}, [(v, foto)], erro) do que mudou NAS
    variações que já existem. `nomes`/`fotos` = {id: digitado}. Pura."""
    mud, com_foto = {}, []
    for v in variacoes:
        if v["id"] in nomes:
            novo = " ".join(str(nomes[v["id"]] or "").split())
            velho = str(v.get("variacao") or "").strip()
            if novo != velho:
                if velho and not novo:
                    return {}, [], f"o nome da variação «{E.nome_completo(v)}» ficou vazio."
                mud[v["id"]] = {"variacao": novo}
        if fotos.get(v["id"]) is not None:
            com_foto.append((v, fotos[v["id"]]))
    novos = [" ".join(str(nomes.get(v["id"], v.get("variacao")) or "").split()).lower() for v in variacoes]
    novos = [n for n in novos if n]
    if len(novos) != len(set(novos)):
        return {}, [], "duas variações ficaram com o mesmo nome."
    return mud, com_foto, ""


def _ch_vq(pf, pid):
    return f"{pf}vq_{pid}"


def ajustes_de_quantidade(variacoes, digitados, saldo):
    """[(variação, diferença)] do físico digitado contra o que existe. Pura."""
    fora = []
    for v in variacoes:
        if v["id"] not in digitados or digitados[v["id"]] is None:
            continue
        dif = int(digitados[v["id"]]) - int(saldo.get((v["id"], E.FISICO), 0))
        if dif:
            fora.append((v, dif))
    return fora


def _ch_vn(pf, pid):
    return f"{pf}vn_{pid}"


def _ch_vf(pf, pid):
    return f"{pf}vf_{pid}_{st.session_state.get(pf + 'k', 0)}"


def _edicao_pendente(variacoes, sufixo):
    """(mud, avisos, foto, erro) do «✎ Editar» como está na tela agora.
    mud = None quando nada mudou. Efeito: lê a planilha de SKU se mudou."""
    ss = st.session_state
    pf = _pf_ed(variacoes, sufixo)
    ini = ss.get(pf + "ini")
    if not ini:                       # o editar deste produto não está na tela
        return None, [], None, ""
    dig = {k: ss.get(pf + k, "") for k in ini}
    foto = ss.get(_ch_foto_ed(pf))
    if not edicao_mudou(ini, dig, foto is not None):
        return None, [], None, ""
    custos, erro_c, avisos_c = _custos_do_formulario(dig["sku"], dig["custo"], dig["sku_at"], dig["custo_at"])
    if erro_c:
        return None, [], None, erro_c
    nome = " ".join(str(dig["nome"]).split())
    if not nome:
        return None, [], None, "Falta o nome do produto."
    mud = {v["id"]: {"nome": nome, "codigo_fornecedor": str(dig["forn"]).strip(),
                     "fornecedor": " ".join(str(dig["fornecedor"]).split()), **custos}
           for v in variacoes}
    return mud, avisos_c, foto, ""


def _salvar_produto(variacoes, quem, sufixo="", fechar=False, entrada=None):
    """UM «Salvar» para tudo do produto (dono, 17/11): o que mudou no «✎
    Editar» E as variações novas que estiverem escritas. Callback."""
    ss = st.session_state
    p0 = variacoes[0]
    mud, avisos, foto, erro = _edicao_pendente(variacoes, sufixo)
    if erro:
        _avisar(f"Nada foi gravado — {erro}", erro=True)
        return
    pf = _pf_ed(variacoes, sufixo)
    painel = bool(ss.get(pf + "painel"))
    var_mud, var_fotos = {}, []
    if painel:
        var_mud, var_fotos, erro_e = edicoes_de_variacao(
            variacoes, {v["id"]: ss[_ch_vn(pf, v["id"])] for v in variacoes if _ch_vn(pf, v["id"]) in ss},
            {v["id"]: ss.get(_ch_vf(pf, v["id"])) for v in variacoes})
        if erro_e:
            _avisar(f"Nada foi gravado — {erro_e}", erro=True)
            return
    ajustes, movs_ag = [], []
    if painel:
        _pp, movs_ag, _cc = E.carregar()
        ajustes = ajustes_de_quantidade(
            variacoes, {v["id"]: ss.get(_ch_vq(pf, v["id"])) for v in variacoes if _ch_vq(pf, v["id"]) in ss},
            E.saldos(movs_ag))
    blocos = []
    if ss.get("est_nova_var"):
        lidos = [(ss.get(_ch_var("nome", i)), ss.get(_ch_var("qtd", i)), ss.get(_ch_var("foto", i)))
                 for i in range(int(ss.get("est_var_n") or 1))]
        if any(str(n or "").strip() or q or f is not None for n, q, f in lidos):
            blocos, erro_v = blocos_de_variacao(lidos)
            if erro_v:
                _avisar(f"Nada foi gravado — {erro_v}", erro=True)
                return
    if blocos:
        # A planilha de AGORA, não a da tela: o segundo clique precisa ver
        # o que o primeiro acabou de gravar.
        ja = nomes_ja_cadastrados(E.carregar_agora()[0], p0.get("ean"))
        rep = [n for n, _q, _f in blocos if n.lower() in ja]
        if rep:
            _avisar("Nada foi gravado — " + ", ".join(f"«{n}»" for n in rep)
                    + (" já está cadastrada" if len(rep) == 1 else " já estão cadastradas")
                    + " neste produto. Se acabou de salvar, ela já entrou: confira a lista.", erro=True)
            return
    qtd_ent = {}
    if entrada:
        qtd_ent = quantidades_mudadas(entrada[1], {i: ss.get(_ch_qe(entrada[0], i)) for i, _m, _p in entrada[1]})
    if mud is None and not blocos and not var_mud and not var_fotos and not ajustes and not qtd_ent:
        _avisar("Nada para gravar: nenhum campo mudou.", erro=True)
        return
    try:
        partes, avisos_f = [], []
        tudo = {}
        if qtd_ent:
            _pc, movs_c, _cc = E.carregar()
            lin_c, novo_c = linhas_da_correcao(entrada[0], movs_c, qtd_ent, quem, _quando())
            if not lin_c:
                _avisar("Nada foi gravado — essa entrada já tinha sido excluída.", erro=True)
                return
            E.gravar_movimentos(lin_c)
            tot = sum(E.inteiro(m["qtd"]) for m in lin_c if str(m.get("lote")) == str(novo_c))
            partes.append(f"✎ Entrada corrigida: agora {tot} peça(s)." if novo_c else
                          "↶ Entrada excluída: todas as quantidades ficaram zero.")
        if mud is not None:
            foto_id, af = foto_da_tela(foto, E.limpar_codigo(p0.get("ean")))
            if af:
                avisos_f.append(af)
            if foto_id and painel:
                # A foto de CAPA vai em todas as variações: a lista mostra
                # a primeira, e a primeira pode ser excluída.
                for m in mud.values():
                    m["foto_produto"] = foto_id
            elif foto_id:
                alvo = ss.get(f"{pf}alvo_{len(variacoes)}")
                nomes = [E.nome_completo(x) for x in variacoes]
                v = variacoes[nomes.index(alvo) if alvo in nomes else 0]
                mud[v["id"]]["foto_id"] = foto_id
            tudo = {k: dict(v) for k, v in mud.items()}
            partes.append("✓ Produto atualizado. O custo novo vale para as próximas entradas."
                          + "".join(f" · {a}" for a in avisos))
        for vid, m in var_mud.items():
            tudo.setdefault(vid, {}).update(m)
        for v, fv in var_fotos:
            foto_id, af = foto_da_tela(fv, E.limpar_codigo(p0.get("ean")))
            if af:
                avisos_f.append(f"{E.nome_completo(v)}: {af}")
            if foto_id:
                tudo.setdefault(v["id"], {})["foto_id"] = foto_id
        if var_mud or var_fotos:
            partes.append(f"✓ {len(set(var_mud) | {v['id'] for v, _f in var_fotos})} variação(ões) atualizada(s).")
        if ajustes:
            E.gravar_movimentos(E.linhas_de_ajuste(
                {"linhas": [{"produto": v, "dif": d} for v, d in ajustes]}, quem, _quando(),
                "ajuste no Estoque cadastrado", movs=movs_ag))
            partes.append("✓ Quantidade corrigida: " + ", ".join(
                f"{E.nome_completo(v)} {'+' if d > 0 else ''}{d}" for v, d in ajustes) + ".")
            # Os campos de quantidade renascem do saldo novo.
            for v, _d in ajustes:
                ss.pop(_ch_vq(pf, v["id"]), None)
        if tudo:
            E.atualizar_produtos(tudo)
            # Os campos voltam ao que foi gravado; as fotos nascem vazias.
            ss[pf + "k"] = int(ss.get(pf + "k") or 0) + 1
        if blocos:
            # A variação nova nasce com o produto JÁ editado (nome, custo…).
            base = {**p0, **(mud or {}).get(p0["id"], {})}
            linhas, ent = [], []
            for nome, qtd, fv in blocos:
                foto_id, af = foto_da_tela(fv, E.limpar_codigo(p0.get("ean")))
                if af:
                    avisos_f.append(f"{nome}: {af}")
                nv = E.linhas_de_produto(base.get("ean"), base.get("codigo_fornecedor"), base.get("nome"),
                                         E.numero(base.get("custo")), [(nome, foto_id)], quem, _quando(),
                                         sku=base.get("sku", ""), sku_atacado=base.get("sku_atacado", ""),
                                         custo_atacado=base.get("custo_atacado", ""),
                                         fornecedor=base.get("fornecedor", ""))
                if base.get("foto_produto"):
                    nv[0]["foto_produto"] = base["foto_produto"]
                linhas += nv
                ent += E.linhas_de_entrada([(nv[0], qtd)], quem, _quando(), origem=_origem_da_entrada())
            E.gravar_produtos(linhas)
            if ent:
                E.gravar_movimentos(ent)
            pai = pai_sem_nome(variacoes)
            if pai is not None:
                avisos_z = _zerar_pai(pai, quem)
            else:
                avisos_z = ""
            pecas = sum(q for _n, q, _f in blocos)
            nomes = ", ".join(f"«{n}»" for n, _q, _f in blocos)
            plural = len(blocos) > 1
            partes.append(f"✓ {'Variações' if plural else 'Variação'} {nomes} {'criadas' if plural else 'criada'}"
                          + (f", com {pecas} peça(s)." if pecas else ".")
                          + (f" · {avisos_z}" if avisos_z else ""))
            _fechar_nova_variacao()
        _avisar(*_com_foto(" ".join(partes), " · ".join(avisos_f)))
        # Salvou: o «✎ editar» da entrada recolhe (dono, 17/11).
        if fechar:
            _fechar_ed_entrada()
    except Exception as e:
        _avisar(f"Não gravei — a planilha respondeu: {e}", erro=True)


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


def resolver_custo(sku, digitado, tabela, erro_planilha=""):
    """O custo que o cadastro grava, a partir do SKU e do que foi digitado. Pura.

    Devolve (custo ou None, erro, info). Dono, 12/11: o SKU acha o custo na
    aba PREÇO DE CUSTO. Achou: vale o da planilha ("mesmo SKU quer dizer
    mesmo preço de custo"). SKU de PACOTE não entra: o custo dele é do pacote
    inteiro. Não achou, ou sem SKU: vale o digitado, e o produto vai para a
    lista «Produtos sem SKU» só quando não tem SKU nenhum (17/11).
    """
    c = E.consulta_sku(tabela or {}, sku)
    sem_planilha = (f" (não consegui ler o Controle MS: {erro_planilha})" if erro_planilha else "")
    if c["achou"] and c["aviso"]:
        return None, c["aviso"], ""
    if c["achou"]:
        dig = E.numero(digitado, -1)
        nota = (f" — o digitado ({_rs(dig)}) foi trocado pelo da planilha" if dig >= 0 and
                str(digitado).strip() and abs(dig - c["custo"]) > 0.004 else "")
        return c["custo"], "", f"custo da planilha pelo SKU: {_rs(c['custo'])}{nota}"
    if not str(digitado or "").strip():
        motivo = ("o SKU não está na planilha" if E.normalizar_sku(sku) else "o produto está sem SKU")
        return None, f"Falta o preço de custo — {motivo}{sem_planilha}.", ""
    dig = E.numero(digitado, -1)
    if dig < 0:
        return None, "O preço de custo precisa ser um número.", ""
    info = ("sem SKU — o produto entra na lista «Produtos sem SKU»" if not E.normalizar_sku(sku)
            else c["aviso"] + sem_planilha)
    return dig, "", info


def _tabela_sku():
    """(tabela, erro) da planilha, pelo cache de 10 min. Nunca levanta."""
    try:
        return E.tabela_de_sku_da_planilha()
    except Exception as e:
        return None, str(e)[:140]


def situacao_sku(sku, tabela, erro_planilha=""):
    """O que a tela diz ENQUANTO o SKU é digitado (dono, 12/11). Pura.

    (tipo, mensagem, custo em texto ou None). tipo: "" (vazio), "ok",
    "erro" (pacote ou não encontrado) ou "aviso" (planilha ilegível).
    O custo achado volta escrito como a equipe digita ("35,00"), para
    preencher o campo de custo sozinho.
    """
    n = E.normalizar_sku(sku)
    if not n:
        return "", "", None
    if tabela is None:
        return ("aviso", f"Não consegui ler o Controle MS agora ({erro_planilha or 'sem resposta'}). "
                         "Digite o custo à mão.", None)
    c = E.consulta_sku(tabela, n)
    if c["achou"] and c["aviso"]:
        return "erro", c["aviso"], None
    if c["achou"]:
        prod = str((tabela.get(n) or {}).get("produto") or "").strip()
        txt = f'{c["custo"]:.2f}'.replace(".", ",")
        return ("ok", f"✓ {n} achado na planilha" + (f" ({prod})" if prod else "")
                + f" · custo R$ {txt}", txt)
    return ("aviso", f"SKU {n} ainda não está na aba {E.ABA_SKU} do Controle MS — digite o custo "
                     "e salve: vale o digitado.", None)


RELER_SKU_SEG = 30


def precisa_reler_sku(sku, tabela, relidos, agora):
    """O SKU digitado não está na cópia guardada: vale ler a planilha de
    novo? Pura. Uma vez por SKU a cada RELER_SKU_SEG — são ~24 MB, e o
    mesmo SKU errado não pode baixar a planilha a cada Enter."""
    n = E.normalizar_sku(sku)
    if not n or tabela is None or n in tabela:
        return False
    return agora - float((relidos or {}).get(n, 0)) >= RELER_SKU_SEG


def _ao_mudar_sku(chave_sku, chave_custo):
    """Digitou o SKU: achou na planilha, o custo se preenche sozinho. NÃO
    achou: lê a planilha de novo na hora, uma vez — o SKU acabou de ser
    cadastrado lá e a cópia guardada tem até 10 min (dono, 18/11)."""
    import time as _t_sku
    ss = st.session_state
    tab, err = _tabela_sku()
    relidos = ss.setdefault("est_sku_relidos", {})
    agora = _t_sku.time()
    if precisa_reler_sku(ss.get(chave_sku, ""), tab, relidos, agora):
        relidos[E.normalizar_sku(ss.get(chave_sku, ""))] = agora
        try:
            tab, err = E.tabela_de_sku_agora()
        except Exception as e:
            tab, err = None, str(e)[:140]
    _t, _m, custo = situacao_sku(ss.get(chave_sku, ""), tab, err)
    if custo is not None:
        ss[chave_custo] = custo


def _campos_sku(prefixo, inicial=None, qtds=False):
    """SKU varejo, custo varejo, SKU atacado e custo atacado, NUMA LINHA e
    FORA de `st.form`: dentro de um form nada acontece até salvar, e a busca
    na planilha tem de responder na hora. O mesmo bloco no cadastro e na
    edição — a mesma capacidade nos dois irmãos. (sku, custo, sku_at, custo_at)."""
    ss = st.session_state
    for k, v in (inicial or {}).items():
        ss.setdefault(prefixo + k, v)
    campos = (("SKU (varejo)", "sku", "Custo varejo (R$)", "custo"),
              ("SKU atacado", "sku_at", "Custo atacado (R$)", "custo_at"))
    # Duas colunas iguais, uma linha para cada compra: simétrico ao resto do
    # quadro (dono, 12/11).
    # Três colunas iguais (dono, 23/11): SKU · custo · quantidade da mesma
    # compra na mesma linha. `qtds` só no cadastro sem variações.
    qtd = {"sku": ("Qtd varejo", "est_cad_qv", "Peças desta entrada que vieram da compra de VAREJO."),
           "sku_at": ("Qtd atacado", "est_cad_qa", "Peças desta entrada que vieram da compra de ATACADO.")}
    for rot, k, rot_c, kc in campos:
        c1, c2, c3 = st.columns(3)
        if qtds:
            rq, kq, hq = qtd[k]
            c3.number_input(rq, min_value=0, step=1, value=None, key=kq, help=hq)
        c1.text_input(rot, key=prefixo + k, placeholder="MS-3500" if k == "sku" else "MS-2800",
                      on_change=_ao_mudar_sku, args=(prefixo + k, prefixo + kc),
                      help="Digite e aperte Enter: o Studio busca o custo na aba "
                           "PREÇO DE CUSTO do Controle MS.")
        c2.text_input(rot_c, key=prefixo + kc, placeholder="se não estiver na planilha")
    vals = []
    for rot, k, rot_c, kc in campos:
        sku = ss.get(prefixo + k, "")
        if E.normalizar_sku(sku):
            tab, err = _tabela_sku()
            tipo, msg, _c = situacao_sku(sku, tab, err)
            {"ok": st.success, "erro": st.error, "aviso": st.warning}.get(tipo, st.caption)(msg)
        vals += [sku, ss.get(prefixo + kc, "")]
    return tuple(vals)


def _ch(base, i):
    """A chave do campo da variação `i`. A primeira usa a chave de sempre."""
    return base if i == 0 else f"{base}_{i}"


def _mais_variacao():
    ss = st.session_state
    ss["est_cad_nvar"] = int(ss.get("est_cad_nvar") or 1) + 1


def _linhas_de_variacao():
    """Uma linha por variação no cadastro: nome, qtd varejo, qtd atacado."""
    ss = st.session_state
    n = int(ss.get("est_cad_nvar") or 1)
    for i in range(n):
        a, b, c = st.columns([2, 1, 1])
        a.text_input(f"Variação {i + 1}", key=_ch("est_cad_var", i),
                     placeholder="Braço para cima (fica com a foto)" if i == 0 else "Sentada",
                     label_visibility="visible" if i == 0 else "collapsed")
        b.number_input("Qtd varejo", min_value=0, step=1, value=None, key=_ch("est_cad_qv", i),
                       label_visibility="visible" if i == 0 else "collapsed")
        c.number_input("Qtd atacado", min_value=0, step=1, value=None, key=_ch("est_cad_qa", i),
                       label_visibility="visible" if i == 0 else "collapsed")
    st.button("➕ Adicionar outra variação", key="est_cad_mais_var", on_click=_mais_variacao)


def variacoes_do_cadastro(lidas, tem_var):
    """[(nome, qtd_varejo, qtd_atacado)] limpas, ou (None, erro). Pura.

    Linha de variação toda vazia é ignorada (clicou «adicionar» a mais);
    quantidade sem nome é erro — a peça não pode entrar sem dizer qual é.
    Nome repetido também: duas linhas iguais no cadastro viram dois produtos
    que ninguém distingue na saída."""
    out = []
    for nome, qv, qa in lidas:
        nome = " ".join(str(nome or "").split())
        qv, qa = int(qv or 0), int(qa or 0)
        if tem_var and not nome:
            if qv or qa:
                return None, "Tem quantidade numa variação sem nome."
            continue
        out.append((nome if tem_var else "", qv, qa))
    if tem_var and not out:
        return None, "Falta o nome da variação."
    nomes = [n.casefold() for n, _a, _b in out]
    if len(set(nomes)) != len(nomes):
        return None, "Duas variações com o mesmo nome."
    return out, None


def entrada_das_variacoes(novas, var_ok, quem, quando):
    """A entrada de TODAS as variações do cadastro num lote só: um «excluir»
    desfaz o cadastro inteiro. Pura."""
    lin = []
    for p, (_n, qv, qa) in zip(novas, var_ok):
        lin += linhas_da_entrada_nova(p, qv, qa, quem, quando)
    for l in lin:
        l["lote"] = lin[0]["lote"]
    return lin


def linhas_da_entrada_nova(p, q_varejo, q_atacado, quem, quando):
    """A entrada do cadastro, com as peças de varejo e as de atacado no MESMO
    lote: um «desfazer» desfaz as duas. Pura."""
    lin = (E.linhas_de_entrada([(p, int(q_varejo or 0))], quem, quando, origem=E.VAREJO)
           + E.linhas_de_entrada([(p, int(q_atacado or 0))], quem, quando, origem=E.ATACADO))
    for l in lin:
        l["lote"] = lin[0]["lote"]
    return lin


def _custos_do_formulario(sku, custo, sku_at, custo_at):
    """(mudanças, erro, avisos) do SKU de varejo e do de atacado. Efeito: lê a planilha.

    Basta UM dos dois (dono, 12/11: "eu não tenho esse produto na compra por
    varejo, somente atacado"). Só atacado: o custo do produto passa a ser o
    do atacado, e o SKU de varejo fica vazio.
    """
    tem_v = bool(E.normalizar_sku(sku) or str(custo or "").strip())
    tem_a = bool(E.normalizar_sku(sku_at) or str(custo_at or "").strip())
    if not tem_v and not tem_a:
        return None, "Falta o SKU ou o custo — de varejo ou de atacado.", []
    tab, err = _tabela_sku()
    avisos, cv, ca = [], None, ""
    if tem_v:
        cv, e1, i1 = resolver_custo(sku, custo, tab, err)
        if e1:
            return None, "Varejo: " + e1, []
        if i1:
            avisos.append(i1)
    if tem_a:
        ca, e2, i2 = resolver_custo(sku_at, custo_at, tab, err)
        if e2:
            return None, "Atacado: " + e2, []
        if i2:
            avisos.append("Atacado: " + i2)
    return ({"sku": E.normalizar_sku(sku), "custo": f"{(cv if cv is not None else ca):.2f}",
             "sku_atacado": E.normalizar_sku(sku_at),
             "custo_atacado": f"{ca:.2f}" if ca != "" else ""}, "", avisos)


def _pergunta(cod):
    st.markdown(
        f'<div style="padding:14px;border-radius:12px;background:#4a3a1a;margin:6px 0 10px">'
        f'<div style="color:#f0c060;font-weight:800">Este código não está cadastrado: {_esc(cod)}</div>'
        f'<div style="color:#E8EAED;font-weight:600;margin-top:4px">Cadastrar como produto novo?</div></div>',
        unsafe_allow_html=True)
    c1, c2, _ = st.columns([1.3, 1.3, 3])
    # Callback (varredura de 13/11): o `if botão: … st.rerun()` desenhava a
    # tela duas vezes por clique.
    c1.button("SIM, CADASTRAR", key="est_sim", type="primary", use_container_width=True,
              on_click=lambda: st.session_state.update(est_cadastrar=True))
    c2.button("NÃO, BIPEI ERRADO", key="est_nao", use_container_width=True, on_click=_voltar)


# O upload sem a caixa de arrastar (dono, 23/11): o seletor é da chave do
# campo (`st-key-…`), então só o campo citado muda.
CSS_UPLOAD_COMPACTO = (
    "<style>.st-key-{chave} [data-testid='stFileUploaderDropzone']{padding:6px 10px;}"
    ".st-key-{chave} [data-testid='stFileUploaderDropzoneInstructions']{display:none;}"
    "</style>")


def quadro_da_foto(b64=""):
    """O quadrado grande da foto, como o quadro da rosca na Visão Financeira. Pura."""
    dentro = (f'<img src="data:image/jpeg;base64,{b64}" style="width:100%;height:100%;'
              f'object-fit:contain">' if b64 else
              '<div style="text-align:center;color:#9AA3AE;font-size:13px">📷<br>sem foto ainda</div>')
    # Altura fixa (dono, 13/11): o quadrado em 1:1 descia muito abaixo do
    # último campo da esquerda («Tem variações com este código»). Com o upload
    # numa linha só (23/11), 272 px leva o fundo do quadro até o fundo desse
    # campo — medido no navegador; a foto se encaixa sem cortar.
    return ('<div style="height:272px;width:100%;border-radius:18px;border:1px solid #3a3f45;'
            'background:#2c2c2c;display:flex;align-items:center;justify-content:center;'
            f'overflow:hidden;margin-top:6px">{dentro}</div>')


def _miniatura(arq):
    """A foto anexada reduzida a 600 px, UMA vez por arquivo: a tela redesenha
    a cada tecla, e mandar a foto inteira ao navegador a cada passada pesaria
    megabytes por tecla."""
    if arq is None:
        return ""
    ss = st.session_state
    chave = f"{getattr(arq, 'file_id', '')}|{getattr(arq, 'size', '')}"
    guardada = ss.get("est_cad_mini")
    if guardada and guardada[0] == chave:
        return guardada[1]
    try:
        import base64
        import io
        from PIL import Image
        dados = arq.getvalue()
        try:
            im = Image.open(io.BytesIO(dados)).convert("RGB")
        except Exception:
            # HEIC do iPhone e afins: o conversor que o Studio já tem.
            import imagem as _img
            im = Image.open(io.BytesIO(_img.normalizar_imagem(dados)[0])).convert("RGB")
        im.thumbnail((600, 600))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=80)
        b64 = base64.b64encode(out.getvalue()).decode()
    except Exception:
        b64 = ""
    ss["est_cad_mini"] = (chave, b64)
    return b64


def _cadastro(quem):
    ss = st.session_state
    sem_codigo = bool(ss.get("est_sem_codigo"))
    cod = ss.get("est_lido", "")
    titulo = ("PRODUTO SEM CÓDIGO · o Studio gera o código ao salvar" if sem_codigo
              else f"NÃO CADASTRADO · {cod}")
    st.markdown(f'<div style="font-size:11px;color:#f0c060;font-weight:800;letter-spacing:.12em">'
                f'{_esc(titulo)}</div>', unsafe_allow_html=True)
    # UM QUADRO SÓ, sem `st.form` (dono, 12/11): o SKU busca o custo na
    # hora, e isso não acontece dentro de um form.
    # Upload em uma linha só (dono, 23/11): só o botão, sem a caixa de
    # arrastar — o espaço vai para o quadro da foto. FORA do quadro: dentro
    # da coluna o <style> ocupa uma linha e a foto descia em relação aos campos.
    st.markdown(CSS_UPLOAD_COMPACTO.replace("{chave}", "est_cad_foto"), unsafe_allow_html=True)
    with st.container(border=True):
        esq, dir_ = st.columns([2, 1])
        with esq:
            # 30% · 40% · 30% (dono, 23/11).
            c1, c2, c3 = st.columns([3, 4, 3])
            forn = c1.text_input("Código do fornecedor", placeholder="TRES-B131", key="est_cad_forn")
            nome = c2.text_input("Produto", placeholder="Mini Yoga · conjunto", key="est_cad_nome")
            fornecedor = c3.text_input("Fornecedor", placeholder="nome do fornecedor", key="est_cad_fornecedor")
            # Com variações (dono, 13/11), cada uma tem a sua quantidade: a
            # coluna de quantidade fica vazia e as linhas das variações entram.
            sku, custo, sku_at, custo_at = _campos_sku("est_cad_", qtds=not ss.get("est_cad_tv"))
            tem_var = st.checkbox("Tem variações com este código", key="est_cad_tv",
                                  help="Marcado: uma linha por variação, cada uma com a sua "
                                       "quantidade. A foto ao lado fica com a primeira.")
            if tem_var:
                _linhas_de_variacao()
        with dir_:
            foto = st.file_uploader("Foto do produto", type=None, key="est_cad_foto")
            st.markdown(quadro_da_foto(_miniatura(foto)), unsafe_allow_html=True)
        enviar = st.button("CADASTRAR E DAR ENTRADA", type="primary", key="est_cad_ok")
    st.button("Cancelar", key="est_cancelar", on_click=_voltar)
    if not enviar:
        return
    if not str(nome).strip():
        st.error("Falta o nome do produto.")
        return
    lidas = [(ss.get(_ch("est_cad_var", i), ""), ss.get(_ch("est_cad_qv", i), 0),
              ss.get(_ch("est_cad_qa", i), 0))
             for i in range(int(ss.get("est_cad_nvar") or 1) if tem_var else 1)]
    if not tem_var:
        lidas = [("", lidas[0][1], lidas[0][2])]
    var_ok, erro_v = variacoes_do_cadastro(lidas, tem_var)
    if erro_v:
        st.error(erro_v)
        return
    custos, erro_c, avisos_c = _custos_do_formulario(sku, custo, sku_at, custo_at)
    if erro_c:
        st.error(erro_c)
        return
    try:
        prods, _m, cods = E.carregar()
        if sem_codigo:
            cod = E.novo_codigo_interno(E.todos_os_codigos(prods, cods))
        elif E.do_codigo(prods, cod):
            st.error("Este código acabou de ser cadastrado por outra pessoa. Bipe de novo.")
            return
        foto_id, af = foto_da_tela(foto, cod)
        novas = E.linhas_de_produto(cod, forn, nome, E.numero(custos["custo"]),
                                    [(v, foto_id if i == 0 else "") for i, (v, _a, _b) in enumerate(var_ok)],
                                    quem, _quando(),
                                    sku=custos["sku"], sku_atacado=custos["sku_atacado"],
                                    custo_atacado=custos["custo_atacado"],
                                    fornecedor=fornecedor)
        E.gravar_produtos(novas)
        entrada = entrada_das_variacoes(novas, var_ok, quem, _quando())
        if entrada:
            E.gravar_movimentos(entrada)
        _limpar_ficha()
        q_var = sum(x[1] for x in var_ok)
        q_at = sum(x[2] for x in var_ok)
        _pecas = " e ".join(f"{int(q)} de {o}" for q, o in ((q_var, E.VAREJO), (q_at, E.ATACADO)) if q)
        _nv = f" · {len(var_ok)} variações" if len(var_ok) > 1 else ""
        _avisar(*_com_foto(f"✓ «{nome.strip()}» cadastrado{_nv}" + (f" com {_pecas}." if _pecas else ".")
                           + "".join(f" · {a}" for a in avisos_c), af))
        if sem_codigo:
            ss["est_etiqueta_nova"] = (cod, nome.strip())
        _voltar_ao_modo()
        st.rerun()
    except Exception as e:
        st.error(f"Não gravei o cadastro — a planilha respondeu: {e}")


PASSO_ENTRADAS = 5


def resumo_da_entrada(lt, por_id):
    """O que a lista de entradas mostra de um CONFIRMAR. Pura.

    Mesmo desenho da saída (dono, 13/11), com uma diferença: a entrada é de
    TODO MUNDO, então quem deu a entrada vai na linha de baixo."""
    lin = lt["linhas"]
    pids = list(dict.fromkeys(str(m.get("produto_id")) for m in lin))
    p = por_id.get(pids[0], {}) if pids else {}
    varias = len(pids) > 1
    nome = (" · ".join(f'{E.nome_completo(por_id.get(str(m.get("produto_id")), {})) or "produto apagado"}'
                       f' +{E.inteiro(m.get("qtd"))}' for m in lin) if varias
            else (E.nome_completo(p) or "produto apagado"))
    return {"nome": nome, "p": p, "q": sum(E.inteiro(m.get("qtd")) for m in lin),
            "ean": "" if varias else E.limpar_codigo(p.get("ean")),
            "sku": "" if varias else E.normalizar_sku(p.get("sku")),
            "quem": str(lt.get("quem") or ""), "hora": str(lt.get("quando") or "")[-5:],
            "desfeito": lt["desfeito"]}


def linha_entrada_html(r):
    """Uma linha das últimas entradas — a de `linha_bipada_html`, em verde. Pura."""
    nome = f"<s>{_esc(r['nome'])}</s>" if r["desfeito"] else _esc(r["nome"])
    sub = " · ".join(x for x in (r["hora"], r["ean"], f"SKU {r['sku']}" if r["sku"] else "",
                                 r["quem"], "excluída" if r["desfeito"] else "") if x)
    return (f'<div style="display:flex;align-items:center;gap:12px;padding:8px 0;'
            f'opacity:{0.45 if r["desfeito"] else 1}">{foto_html(r["p"].get("foto_id"), 56)}'
            f'<div style="flex:1"><div style="font-size:16px;font-weight:800">{nome}</div>'
            f'<div style="font-size:12px;color:#9AA3AE;margin-top:2px">{_esc(sub)}</div></div>'
            f'<div style="font-size:20px;font-weight:800;color:#7fd18b">+{r["q"]}</div></div>')


def linhas_da_correcao(lote, movs, novas, quem, quando):
    """Corrige as quantidades de uma ENTRADA (dono, 13/11). Pura.

    `novas` = {índice da linha no lote: quantidade nova}. Grava o lote ao
    contrário (o desfazer de sempre) e um lote novo com as quantidades
    certas — cada linha mantém produto, local, origem e custo da original:
    corrigir o número não pode trocar a peça de Full nem de compra.
    Quantidade 0 tira a linha. Lote já desfeito devolve [].
    Devolve (linhas, lote_novo)."""
    lote = str(lote)
    orig = [m for m in movs if str(m.get("lote")) == lote and m.get("tipo") != E.DESFEITO]
    volta = E.linhas_que_desfazem(lote, movs, quem, quando)
    if not volta:
        return [], None
    novo = E._id("L")
    certas = []
    for i, m in enumerate(orig):
        q = int(novas.get(i, E.inteiro(m.get("qtd"))) or 0)
        if q > 0:
            certas.append({**m, "id": E._id("M"), "lote": novo, "qtd": str(q), "quem": quem,
                           "obs": f"corrige {lote}"})
    return volta + certas, (novo if certas else None)


def _alternar_ed_entrada(lote):
    ss = st.session_state
    ss["est_ent_ed"] = None if ss.get("est_ent_ed") == lote else lote


def _salvar_correcao(lote, quem, n):
    ss = st.session_state
    try:
        _p, movs, _c = E.carregar()
        novas = {i: ss[_ch_qe(lote, i)] for i in range(n) if ss.get(_ch_qe(lote, i)) is not None}
        linhas, novo = linhas_da_correcao(lote, movs, novas, quem, _quando())
        if not linhas:
            _avisar("Essa entrada já tinha sido excluída.", True)
            return
        E.gravar_movimentos(linhas)
        ss["est_ent_ed"] = None
        tot = sum(E.inteiro(m["qtd"]) for m in linhas if str(m.get("lote")) == str(novo))
        _avisar(f"✎ Entrada corrigida: agora {tot} peça(s)." if novo else
                "↶ Entrada excluída: todas as quantidades ficaram zero.")
    except Exception as e:
        _avisar(f"Não corrigi — a planilha respondeu: {e}", True)


def _edicao_da_entrada(lt, por_id, quem):
    """A entrada aberta: cada produto dela num quadro com a QUANTIDADE e o
    cadastro juntos (dono, 18/11). Linha de produto apagado (sem código)
    fica num quadro só de quantidade."""
    linhas = [m for m in lt["linhas"] if m.get("tipo") != E.DESFEITO]
    todos = list(por_id.values())
    por_ean, soltas = {}, []
    for i, m in enumerate(linhas):
        p = por_id.get(str(m.get("produto_id")), {})
        e = E.limpar_codigo(p.get("ean"))
        vs = E.do_codigo(todos, e) if e else []
        if vs:
            por_ean.setdefault(e, (vs, []))[1].append((i, m, p))
        else:
            soltas.append((i, m, p))
    for e, (vs, lin) in por_ean.items():
        _editar_produto(vs, quem, sufixo=f"_lt{lt['lote']}", aberto=True, fechar=True,
                        entrada=(lt["lote"], lin))
    if soltas:
        with st.container(border=True):
            for i, m, p in soltas:
                a, b = st.columns([3, 1.2], vertical_alignment="center")
                a.markdown(f'{_esc(E.nome_completo(p) or "produto apagado")} · {_esc(E.origem_de(m))}')
                b.number_input("quantidade certa", min_value=0, step=1, value=E.inteiro(m.get("qtd")),
                               key=_ch_qe(lt["lote"], i), label_visibility="collapsed")
            # Cancelar (dono, 17/11): abriu o produto errado, fecha sem gravar.
            s1, s2, _s3 = st.columns([1.3, 1, 2])
            s1.button("Salvar quantidade", key=f"est_ent_sv_{lt['lote']}", type="primary",
                      on_click=_salvar_correcao, args=(lt["lote"], quem, len(linhas)))
            s2.button("Cancelar", key=f"est_ent_cx_{lt['lote']}", on_click=_fechar_ed_entrada)


def _mais_entradas():
    ss = st.session_state
    ss["est_ent_n"] = int(ss.get("est_ent_n") or PASSO_ENTRADAS) + PASSO_ENTRADAS


def entradas_visiveis(movs, n):
    """As últimas `n` entradas que valem — sem as excluídas/corrigidas. Pura."""
    return [lt for lt in E.ultimos_lotes(movs, E.ENTRADA, len(movs) + 1) if not lt["desfeito"]][:n]


def _ultimas(movs, por_id, quem):
    n = int(st.session_state.get("est_ent_n") or PASSO_ENTRADAS)
    # Um a mais do que mostra: é assim que se sabe se a seta tem o que abrir.
    # SEM OS RISCADOS (dono, 17/11): entrada excluída ou corrigida não
    # aparece — o «✎ editar» grava um lote novo e desfaz o velho, e o velho
    # riscado na lista parecia entrada a mais.
    lotes = entradas_visiveis(movs, n + 1)
    if not lotes:
        return
    st.markdown(f'<div style="font-size:12px;letter-spacing:.14em;font-weight:800;color:#9AA3AE">'
                f'ÚLTIMAS {min(n, len(lotes))} ENTRADAS</div>', unsafe_allow_html=True)
    for lt in lotes[:n]:
        # 4:2.2 e não 6:1: ao lado da ficha a coluna é estreita, e o
        # «✖ excluir» quebrava em duas linhas (visto no navegador, 13/11).
        c1, c2 = st.columns([4, 2.2], vertical_alignment="center")
        c1.markdown(linha_entrada_html(resumo_da_entrada(lt, por_id)), unsafe_allow_html=True)
        if not lt["desfeito"]:
            # ✎ editar (dono, 13/11): «eram 2 e entraram 3» se corrige sem
            # excluir e bipar tudo de novo. Os dois botões lado a lado,
            # como na saída.
            b1, b2 = c2.columns(2)
            b1.button("✎ editar", key=f"est_ent_ed_{lt['lote']}", on_click=_alternar_ed_entrada,
                      args=(lt["lote"],), use_container_width=True)
            b2.button("✖ excluir", key=f"est_desf_{lt['lote']}", on_click=_desfazer,
                      args=(lt["lote"], quem), use_container_width=True)
            if st.session_state.get("est_ent_ed") == lt["lote"]:
                _edicao_da_entrada(lt, por_id, quem)
    if len(lotes) > n:
        st.button("▾ mostrar mais 5", key="est_ent_mais", on_click=_mais_entradas)


# ── SAÍDA (Parte 2) ──────────────────────────────────────────────────────────

def _baixar(itens, destino, quem, rotulo, full=None):
    """Grava a saída de um bipe e deixa o aviso com o que saiu. Levanta erro."""
    prods, movs, _c = E.carregar()
    if destino == E.ENVIO_FULL and full is None:
        full = _full_escolhido()
        if not full:
            _avisar("Escolha PARA QUAL Full está indo, antes de bipar.", True)
            return None
    linhas = E.linhas_de_saida(itens, destino, quem, _quando(), obs=rotulo, full=full or "", movs=movs)
    if not linhas:
        return None
    E.gravar_movimentos(linhas)
    lote = linhas[0]["lote"]
    st.session_state.setdefault("est_sessao", []).append(lote)
    saldo = E.saldos(movs + linhas)
    zerados = [E.nome_completo(p) for p, _q in itens if saldo.get((p["id"], E.FISICO), 0) <= 0]
    para = f" → {E.NOME_LOCAL.get(full, 'Full')}" if destino == E.ENVIO_FULL else ""
    msg = f"✓ Saiu{para}: {rotulo}"
    if zerados:
        msg += " · ⚠️ estoque físico ZEROU: " + ", ".join(zerados)
    _avisar(msg, False)
    return lote


def _destino():
    return DESTINOS.get(st.session_state.get("est_dest") or "🛒 Venda", E.VENDA)


def _full_escolhido():
    """O Full escolhido na Saída, pelo nome na tela → a chave. Ou ''."""
    nome = st.session_state.get("est_full_dest") or ""
    return next((k for k, v in E.FULLS.items() if v == nome), "")


def _bipe_na_saida(cod):
    """Um bipe na Saída. Callback: roda antes de a tela ser desenhada."""
    ss = st.session_state
    quem = ss.get("est_quem", "")
    # O PRÓXIMO BIPE FECHA A PERGUNTA DO KIT: não clicou, a unidade fica.
    ss.pop("est_kit_pergunta", None)
    try:
        prods, movs, codigos = E.carregar()
        itens, variacoes = E.itens_do_bipe(prods, codigos, cod)
        if variacoes:
            ss["est_janela"] = cod           # vários modelos: a tela pergunta qual
            return
        if not itens:
            ss["est_desconhecido"] = cod
            return
        k = E.codigo_gerado(codigos, cod)
        rotulo = (k.get("nome") if k else E.nome_completo(itens[0][0]))
        corr = ss.pop("est_corrigir", None)
        if corr:
            desf = E.linhas_que_desfazem(corr, movs, quem, _quando())
            E.gravar_movimentos(desf)
        lote = _baixar(itens, _destino(), quem, rotulo + (" (no lugar do bipe errado)" if corr else ""))
        ss.pop("est_janela", None)
        if lote and not k:
            _perguntar_kit(lote, itens[0][0]["id"], codigos)
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
        ss.pop("est_kit_pergunta", None)
        lote = _baixar([(p, 1)], _destino(), quem, E.nome_completo(p))
        ss.pop("est_janela", None)
        if lote:
            _perguntar_kit(lote, pid, _c)
    except Exception as e:
        _avisar(f"Não gravei a saída — a planilha respondeu: {e}", True)


def _perguntar_kit(lote, pid, codigos):
    ks = E.kits_com(codigos, pid)
    if ks:
        st.session_state["est_kit_pergunta"] = {"lote": lote, "codigos": [k["codigo"] for k in ks]}


def _era_kit(codigo, quem):
    """Clique em "É o Kit X?": a unidade volta e o kit inteiro sai no lugar."""
    ss = st.session_state
    perg = ss.pop("est_kit_pergunta", None)
    if not perg:
        return
    try:
        prods, movs, codigos = E.carregar()
        k = E.codigo_gerado(codigos, codigo)
        itens, _v = E.itens_do_bipe(prods, codigos, codigo)
        if not k or not itens:
            _avisar("Esse kit não existe mais — a unidade ficou como saiu.", True)
            return
        E.gravar_movimentos(E.linhas_que_desfazem(perg["lote"], movs, quem, _quando()))
        _baixar(itens, _destino(), quem, f'{k.get("nome")} (no lugar da unidade)')
    except Exception as e:
        _avisar(f"Não troquei pelo kit — a planilha respondeu: {e}", True)


def _pergunta_kit(codigos, por_id, quem, movs):
    perg = st.session_state.get("est_kit_pergunta")
    if not perg or perg["lote"] in E.lotes_desfeitos(movs):
        return
    ks = [k for k in codigos if k.get("codigo") in perg["codigos"]]
    if not ks:
        return
    with st.container(border=True):
        st.markdown("**Saiu 1 unidade. Era um kit?** — se não for, é só bipar o próximo.")
        for k in ks:
            c1, c2 = st.columns([3, 1.6])
            c1.markdown(f'**{_esc(k.get("nome"))}**  \n{_esc(receita_txt(k, por_id))}')
            c2.button(f"É o {k.get('nome')}?", key=f"est_ek_{k['codigo']}", type="primary",
                      use_container_width=True, on_click=_era_kit, args=(k["codigo"], quem))


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
        full = next((m.get("local") for m in movs if str(m.get("lote")) == lote
                     and E.eh_full(m.get("local"))), None)
        E.gravar_movimentos(E.linhas_que_desfazem(lote, movs, quem, _quando()))
        if n > 0:
            itens = [(por_id[m["produto_id"]], -E.inteiro(m["qtd"]) * n) for m in linhas
                     if m["produto_id"] in por_id]
            _baixar(itens, destino, quem, f"{n}× " + ", ".join(E.nome_completo(p) for p, _q in itens),
                    full=full)
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


# ── O LAYOUT DA SAÍDA (dono, 12/11, aprovado no mockup) ──────────────────────
# Quadro roxo à esquerda: o bipe da vez, grande — foto, nome, código de
# barras, fornecedor, SKU, quanto saiu, quanto fica e o custo considerado,
# com «editar» e «excluir». À direita, os 5 anteriores. A saída manual vai
# embaixo de tudo.

def resumo_do_lote(lt, por_id, saldo):
    """O que a tela mostra de um bipe. Pura.

    {nome, p (o produto da foto), ean, forn, sku, q, origens, custo, fica,
     destino, hora, desfeito, kit}
    """
    fis = [m for m in lt["linhas"] if m.get("local") == E.FISICO]
    pids = list(dict.fromkeys(m.get("produto_id") for m in fis))
    p = por_id.get(pids[0], {}) if pids else {}
    q = sum(-E.inteiro(m["qtd"]) for m in fis)
    valor = sum(-E.inteiro(m["qtd"]) * E.numero(m.get("custo_unit")) for m in fis)
    full = next((m.get("local") for m in lt["linhas"] if E.eh_full(m.get("local"))), "")
    kit = len(pids) > 1
    return {"nome": rotulo_do_lote(fis, por_id), "p": p,
            "ean": "" if kit else E.limpar_codigo(p.get("ean")),
            "forn": "" if kit else str(p.get("codigo_fornecedor") or ""),
            "sku": "" if kit else E.normalizar_sku(p.get("sku")),
            "q": q, "origens": sorted({E.origem_de(m) for m in fis}),
            "custo": (valor / q) if q and not kit else valor,
            "fica": None if kit else saldo.get((p.get("id"), E.FISICO), 0),
            "destino": (E.NOME_LOCAL.get(full, "Full") if full else "Venda"),
            "hora": str(lt.get("quando") or "")[-5:], "desfeito": lt["desfeito"], "kit": kit}


def _barras_html(ean):
    try:
        return E.svg_ean13(ean, modulo=2, altura=44) if len(ean) == 13 and ean.isdigit() else ""
    except Exception:
        return ""


def quadro_grande_html(titulo, cor, nome, linhas, rotulo_custo, custo, foto_id, ean):
    """O quadro grande do produto bipado — o da saída (roxo) e o da entrada
    (verde, dono 13/11). Um desenho só para os dois: com duas cópias, uma
    muda e a outra fica para trás. Pura. Sem linha em branco: o HTML passa
    pelo markdown do Streamlit."""
    cinza = "#9AA3AE"
    import gdrive
    url = gdrive.url_thumbnail(foto_id, 600) if foto_id else None
    # Python 3.11: sem barra invertida dentro da f-string — pré-calculado.
    barras = _barras_html(ean).replace("<svg ", "<svg style='max-width:100%;height:auto' ", 1)
    # A foto ocupa 38% do quadro, sempre quadrada: lado fixo em pixel
    # espremia o texto em coluna estreita (visto no navegador, 12/11).
    foto = (f'<img src="{_esc(url)}" style="width:100%;aspect-ratio:1/1;object-fit:cover;'
            f'border-radius:16px">' if url else
            '<div style="width:100%;aspect-ratio:1/1;border-radius:16px;background:#444;display:flex;'
            'align-items:center;justify-content:center;color:#9AA3AE;font-size:13px">sem foto</div>')
    return (f'<div style="border:2px solid {cor};border-radius:20px;padding:20px;background:#2f2f2f;'
            'color:#E8EAED">'
            f'<div style="font-size:12px;letter-spacing:.14em;font-weight:800;color:{cor};'
            f'margin-bottom:12px">{titulo}</div>'
            '<div style="display:flex;flex-wrap:wrap;gap:20px;align-items:flex-start">'
            f'<div style="flex:0 0 38%;min-width:150px">{foto}</div>'
            f'<div style="flex:1;min-width:200px;overflow-wrap:anywhere"><div style="font-size:26px;'
            f'font-weight:800;line-height:1.15">{_esc(nome)}</div>'
            + "".join(f'<div style="font-size:15px;color:{cinza};margin-top:7px">{x}</div>' for x in linhas)
            + f'<div style="margin-top:12px;font-size:21px;font-weight:800;color:#4cc38a">'
              f'{rotulo_custo}: {_rs(custo)}</div>'
            + (f'<div style="margin-top:10px;max-width:100%;overflow:hidden">{barras}</div>'
               if barras else "")
            + '</div></div></div>')


def bipe_atual_html(r):
    """O quadro roxo do bipe da vez. Pura."""
    chip = "".join(f'<span style="display:inline-block;padding:3px 10px;border-radius:999px;'
                   f'background:#1f3a5a;color:#7cb8ff;font-size:12px;font-weight:700;'
                   f'margin-left:6px">{_esc(o)}</span>' for o in r["origens"])
    lin = []
    if r["ean"]:
        lin.append(f'Código de barras <b style="color:#E8EAED">{_esc(r["ean"])}</b>')
    if r["forn"] or r["sku"]:
        lin.append(" · ".join(x for x in (
            f'Cód. fornecedor <b style="color:#E8EAED">{_esc(r["forn"])}</b>' if r["forn"] else "",
            f'SKU <b style="color:#E8EAED">{_esc(r["sku"])}</b>' if r["sku"] else
            '<span style="color:#f0c060">sem SKU</span>') if x) + chip)
    lin.append(f'Saiu <b style="color:#E8EAED">{r["q"]}</b>'
               + (f' · fica no físico <b style="color:#E8EAED">{r["fica"]}</b>' if r["fica"] is not None else ""))
    return quadro_grande_html(f'✓ SAIU AGORA · {_esc(r["hora"])} · {_esc(r["destino"]).upper()}',
                              "#a78bfa", r["nome"], lin,
                              "custo do kit" if r["kit"] else "custo considerado",
                              r["custo"], r["p"].get("foto_id"), r["ean"])


def ficha_entrada_html(variacoes, saldo, codigo):
    """O quadro verde do produto bipado na ENTRADA (dono, 13/11): o mesmo
    desenho do bipe da vez da saída. Pura."""
    p = variacoes[0]
    b = lambda x: f'<b style="color:#E8EAED">{_esc(x)}</b>'
    ean = E.limpar_codigo(codigo)
    lin = [f'Código de barras {b(ean)}']
    sku = E.normalizar_sku(p.get("sku"))
    forn = str(p.get("codigo_fornecedor") or "").strip()
    nome_forn = str(p.get("fornecedor") or "").strip()
    lin.append(" · ".join(x for x in (
        f'Fornecedor {b(nome_forn)}' if nome_forn else "",
        f'Cód. fornecedor {b(forn)}' if forn else "",
        f'SKU {b(sku)}' if sku else ("só atacado" if E.so_atacado(p) else
                                     '<span style="color:#f0c060">sem SKU</span>')) if x))
    sku_at = E.normalizar_sku(p.get("sku_atacado"))
    if sku_at:
        lin.append(f'Atacado {b(sku_at)} · {_rs(E.custo_de(p, E.ATACADO))}')
    total = sum(saldo.get((v["id"], E.FISICO), 0) for v in variacoes)
    n = len(variacoes)
    var_txt = f' · {n} variações' if n > 1 or str(p.get("variacao") or "").strip() else ""
    lin.append(f'Em estoque no físico <b style="color:#E8EAED">{total}</b>{var_txt}')
    lin.append(f'Registrado em {_esc(str(p.get("registrado_em") or "")[:10])} · '
               '<span style="color:#f0c060">a idade conta daqui</span>')
    return quadro_grande_html(f'✓ JÁ CADASTRADO · {_esc(ean)}', "#4cc38a", E.capitalizar(p.get("nome")), lin,
                              "custo atacado" if E.so_atacado(p) else "custo varejo",
                              E.custo_de(p, E.VAREJO), E.foto_principal(p), ean)


def linha_bipada_html(r):
    """Uma linha da lista dos 5 anteriores. Pura."""
    nome = f"<s>{_esc(r['nome'])}</s>" if r["desfeito"] else _esc(r["nome"])
    sub = " · ".join(x for x in (r["hora"], r["ean"], f"SKU {r['sku']}" if r["sku"] else "",
                                 "kit" if r["kit"] else "", "excluído" if r["desfeito"] else "") if x)
    return (f'<div style="display:flex;align-items:center;gap:12px;padding:8px 0;'
            f'opacity:{0.45 if r["desfeito"] else 1}">{foto_html(r["p"].get("foto_id"), 56)}'
            f'<div style="flex:1"><div style="font-size:16px;font-weight:800">{nome}</div>'
            f'<div style="font-size:12px;color:#9AA3AE;margin-top:2px">{_esc(sub)}</div></div>'
            f'<div style="font-size:20px;font-weight:800;color:#f08a84">−{r["q"]}</div></div>')


def _alternar_edicao(lote):
    ss = st.session_state
    ss["est_sai_ed"] = None if ss.get("est_sai_ed") == lote else lote


def _edicao_do_bipe(lote, quem):
    """Os controles do «editar»: trocar pelo código certo, ou mudar a quantidade."""
    st.button("🔁 Trocar pelo código certo", key=f"est_tr_{lote}", on_click=_corrigir,
              args=(lote,), use_container_width=True)
    c1, c2 = st.columns([1, 1.3])
    c1.number_input("vezes", min_value=0, step=1, value=1, key=f"est_mq_{lote}",
                    help="Quantas vezes este bipe saiu. 0 = exclui.")
    c2.button("Salvar quantidade", key=f"est_sq_{lote}", on_click=_mudar_qtd,
              args=(lote, quem), use_container_width=True)


def _botoes_do_bipe(lote, quem, chave):
    """✎ editar e ✖ excluir, lado a lado."""
    b1, b2 = st.columns(2)
    b1.button("✎ editar", key=f"est_ed_b_{chave}_{lote}", on_click=_alternar_edicao,
              args=(lote,), use_container_width=True)
    b2.button("✖ excluir", key=f"est_desf_s_{chave}_{lote}", on_click=_desfazer,
              args=(lote, quem), use_container_width=True)
    ss = st.session_state
    if ss.get("est_sai_ed") == lote or ss.get("est_corrigir") == lote:
        _edicao_do_bipe(lote, quem)


def _lotes_de_quem(movs, quem, n=6):
    # SÓ OS BIPES DE QUEM ESTÁ NA TELA: com duas pessoas empacotando, uma
    # não deve corrigir o bipe da outra sem perceber.
    return E.ultimos_lotes([m for m in movs if m.get("quem") == quem or m.get("tipo") == E.DESFEITO],
                           (E.VENDA, E.ENVIO_FULL), n)


def _bipe_atual(lotes, por_id, saldo, quem):
    vivo = next((lt for lt in lotes if not lt["desfeito"]), None)
    if not vivo:
        st.caption("Bipe o produto: ele sai na hora e aparece aqui, grande.")
        return None
    st.markdown(bipe_atual_html(resumo_do_lote(vivo, por_id, saldo)), unsafe_allow_html=True)
    _botoes_do_bipe(vivo["lote"], quem, "a")
    return vivo["lote"]


def _lateral_saida(lotes, atual, movs, por_id, saldo, quem):
    st.markdown('<div style="font-size:12px;letter-spacing:.14em;font-weight:800;color:#9AA3AE">'
                'ÚLTIMOS 5 BIPADOS</div>', unsafe_allow_html=True)
    resto = [lt for lt in lotes if lt["lote"] != atual][:5]
    if not resto:
        st.caption("Nada saiu antes deste.")
    for lt in resto:
        r = resumo_do_lote(lt, por_id, saldo)
        st.markdown(linha_bipada_html(r), unsafe_allow_html=True)
        if not lt["desfeito"]:
            _botoes_do_bipe(lt["lote"], quem, "l")
    sess = set(st.session_state.get("est_sessao", []))
    desf = E.lotes_desfeitos(movs)
    das = [m for m in movs if str(m.get("lote")) in sess and str(m.get("lote")) not in desf
           and m.get("local") == E.FISICO]
    pecas = sum(-E.inteiro(m["qtd"]) for m in das)
    custo = sum(-E.inteiro(m["qtd"]) * E.numero(m.get("custo_unit")) for m in das)
    st.markdown(f"**{pecas}** peça(s) nesta sessão · **R\\$ {custo:,.0f}** a custo"
                .replace(",", "."))


def rotulo_manual(p, q, obs=""):
    """O texto que fica no movimento da saída manual. Pura.

    "manual" fica escrito para o histórico separar o que foi bipado do que
    foi lançado depois, e a observação (pedido, data real) vai junto."""
    obs = " ".join(str(obs or "").split())
    return f"{int(q)}× {E.nome_completo(p)} · saída manual" + (f" · {obs}" if obs else "")


def _saiu_manual(pid, quem):
    """Botão «Dar saída» da busca manual: sai a quantidade digitada daquele modelo."""
    ss = st.session_state
    try:
        q = int(ss.get(f"est_sm_q_{pid}", 1) or 0)
        if q <= 0:
            _avisar("Digite quantas peças saíram (1 ou mais).", True)
            return
        prods, _m, _c = E.carregar()
        p = next((x for x in prods if x["id"] == pid), None)
        if p is None:
            _avisar("Esse produto não está mais no cadastro.", True)
            return
        ss.pop("est_kit_pergunta", None)
        if _baixar([(p, q)], _destino(), quem, rotulo_manual(p, q, ss.get("est_sm_obs"))):
            ss["est_busca_sai"] = ""
    except Exception as e:
        _avisar(f"Não gravei a saída — a planilha respondeu: {e}", True)


def _saida_manual(prods, saldo, quem):
    """Saída sem bipe (dono, 12/11): o produto que saiu antes de ter cadastro,
    ou que não dá para bipar, é lançado depois pelo nome. Usa o mesmo destino
    escolhido acima (Venda ou Full) e o mesmo `_baixar` do bipe — e, como no
    bipe, sem estoque ele fica negativo em vez de travar."""
    with st.expander("✍️ Saída manual — produto sem bipe, buscar pelo nome"):
        txt = st.text_input("Nome ou código", key="est_busca_sai", placeholder="Embaralhador, MBLN-06…")
        st.text_input("Observação (pedido, data em que saiu de verdade)", key="est_sm_obs",
                      placeholder="ML · 2000012345678 · saiu em 10/11")
        achados = buscar_produtos(prods, txt)
        if txt and not achados:
            st.caption("Nenhum produto com esse nome. Cadastre primeiro: bipe ou digite o código "
                       "de barras na barra acima, e volte aqui.")
        for p0 in achados:
            for v in E.do_codigo(prods, p0.get("ean")) or [p0]:
                c1, c2, c3 = st.columns([3, 1, 1.2])
                c1.markdown(f"{_esc(E.nome_completo(v))} · em estoque: "
                            f"{saldo.get((v['id'], E.FISICO), 0)}")
                c2.number_input("qtd", min_value=1, step=1, value=1, key=f"est_sm_q_{v['id']}",
                                label_visibility="collapsed")
                c3.button("Dar saída", key=f"est_sm_b_{v['id']}", on_click=_saiu_manual,
                          args=(v["id"], quem), use_container_width=True)
        st.caption("Sai na hora em que você clica. A data real vai na observação.")


# ── PRODUTOS SEM EAN (dono, 12/11, layout aprovado) ─────────────────────────
# O produto que veio sem código de barras de fábrica ganhou um código do
# Studio (20…). Sem etiqueta na peça, a colaboradora acha o produto pelo nome
# e escaneia o código NA TELA — e a saída acontece como um bipe.

VISTAS_SAIDA = ("📦 Bipe da vez", "🏷️ Produtos sem EAN", "✍️ Saída manual")
MAX_SEM_EAN = 30


def eh_codigo_do_studio(ean):
    """O código foi gerado pelo Studio (sem EAN de fábrica)? Pura."""
    c = E.limpar_codigo(ean)
    return c.startswith(E.PREFIXO_INTERNO) and len(c) == 13 and c.isdigit()


def lista_sem_ean(prods, saldo, busca="", todos=False):
    """Um produto por código, em ordem alfabética, filtrado pela palavra como
    TEXTO (nome, variação, SKU, código do fornecedor ou código). Pura.

    [{p, ean, nome, modelos, sku, custo, estoque}]
    """
    b = " ".join(str(busca or "").lower().split())
    por = {}
    for p in E.ativos(prods):
        ean = E.limpar_codigo(p.get("ean"))
        if not ean or (not todos and not eh_codigo_do_studio(ean)):
            continue
        d = por.setdefault(ean, {"p": p, "ean": ean, "nome": str(p.get("nome") or ""), "modelos": 0,
                                 "sku": E.normalizar_sku(p.get("sku")), "custo": E.numero(p.get("custo")),
                                 "estoque": 0, "alvo": ""})
        d["modelos"] += 1
        d["estoque"] += saldo.get((p["id"], E.FISICO), 0)
        d["alvo"] += " " + " ".join(str(x or "").lower() for x in (
            p.get("nome"), p.get("variacao"), p.get("sku"), p.get("sku_atacado"),
            p.get("codigo_fornecedor"), ean))
    fora = [d for d in por.values() if not b or b in " ".join(d["alvo"].split())]
    return sorted(fora, key=lambda d: E._sem_acento(d["nome"]))


def _destacar(nome, busca):
    """O nome escapado, com a palavra buscada destacada. Pura."""
    b = " ".join(str(busca or "").split())
    i = nome.lower().find(b.lower()) if b else -1
    if i < 0:
        return _esc(nome)
    return (_esc(nome[:i]) + '<mark style="background:#f0c06055;color:inherit;border-radius:4px">'
            + _esc(nome[i:i + len(b)]) + "</mark>" + _esc(nome[i + len(b):]))


def linha_sem_ean_html(d, busca=""):
    """Uma linha: foto, nome, SKU, custo, estoque e o código GRANDE à direita. Pura."""
    try:
        barras = E.svg_ean13(d["ean"], modulo=3, altura=70).replace(
            "<svg ", "<svg style='max-width:100%;height:auto' ", 1)
    except Exception:
        barras = f'<div style="color:#000;font-size:22px;font-family:monospace">{_esc(d["ean"])}</div>'
    cor_q = "#f08a84" if d["estoque"] < 0 else "#E8EAED"
    sub = f'{d["modelos"]} modelos' if d["modelos"] > 1 else ""
    return ('<div style="display:grid;grid-template-columns:72px 1.6fr .8fr .7fr .5fr 300px;gap:14px;'
            'align-items:center;padding:10px 0;border-bottom:1px solid #3a3f45;color:#E8EAED">'
            f'{foto_html(d["p"].get("foto_id"), 72)}'
            f'<div><div style="font-size:18px;font-weight:800">{_destacar(d["nome"], busca)}</div>'
            f'<div style="font-size:12px;color:#9AA3AE">{_esc(sub)}</div></div>'
            f'<div style="font-weight:700">{_esc(d["sku"]) or "<span style=color:#f0c060>sem SKU</span>"}</div>'
            f'<div style="font-weight:700">{_rs(d["custo"])}</div>'
            f'<div style="font-size:22px;font-weight:800;color:{cor_q}">{d["estoque"]}</div>'
            f'<div style="background:#fff;border-radius:10px;padding:8px;text-align:center">{barras}</div>'
            '</div>')


def _sem_ean(prods, saldo):
    st.markdown('<div style="font-size:13px;letter-spacing:.14em;font-weight:800;color:#f0c060">'
                '🏷️ PRODUTOS SEM EAN · ESCANEIE O CÓDIGO NA TELA</div>', unsafe_allow_html=True)
    c1, c2 = st.columns([4, 1.2])
    busca = c1.text_input("Buscar", key="est_sem_ean_busca", label_visibility="collapsed",
                          placeholder="🔎 uma palavra do nome, SKU ou código do fornecedor")
    todos = c2.toggle("Mostrar também os com EAN de fábrica", key="est_sem_ean_todos")
    lista = lista_sem_ean(prods, saldo, busca, todos)
    total = len(lista_sem_ean(prods, saldo, "", todos))
    st.caption(f"Ordem alfabética · {len(lista)} de {total} produto(s)"
               + (f" · mostrando os {MAX_SEM_EAN} primeiros — digite mais para afunilar"
                  if len(lista) > MAX_SEM_EAN else ""))
    if not lista:
        st.info("Nenhum produto sem EAN com essa palavra." if busca else
                "Nenhum produto sem EAN cadastrado. Quem não tem código entra pelo botão "
                "«Produto sem código» na Entrada, e o Studio gera um.")
        return
    st.markdown("".join(linha_sem_ean_html(d, busca) for d in lista[:MAX_SEM_EAN]),
                unsafe_allow_html=True)
    st.caption("O leitor lê o código direto da tela: a saída acontece como um bipe e aparece "
               "em «📦 Bipe da vez», com editar e excluir.")


MODOS_BUSCA_SAIDA = ("Código", "Nome")


def _busca_por_nome_saida(prods, saldo):
    """«Buscar produto por: Código ou nome» logo abaixo da barra (dono, 17/11):
    o produto TEM código, mas a etiqueta não está na caixa. Escolher o produto
    é o mesmo que bipar o código dele — `_bipe_na_saida`, com a janela de
    modelos, o kit e o «Bipe da vez» com editar e excluir."""
    modo = st.segmented_control("Buscar produto por", MODOS_BUSCA_SAIDA, default="Código",
                                key="est_sai_modo") or "Código"
    if modo != "Nome":
        return
    txt = st.text_input("Nome do produto", key="est_sai_nome", label_visibility="collapsed",
                        placeholder="🔎 nome, SKU ou código do fornecedor do produto sem etiqueta")
    achados = [p for p in buscar_produtos(prods, txt) if E.limpar_codigo(p.get("ean"))]
    if len(" ".join(str(txt or "").split())) >= 2 and not achados:
        st.caption("Nenhum produto com esse nome.")
    for p in achados:
        ean = E.limpar_codigo(p.get("ean"))
        mods = E.do_codigo(prods, ean) or [p]
        est = sum(saldo.get((v["id"], E.FISICO), 0) for v in mods)
        c0, c1, c2 = st.columns([0.6, 3.4, 1.3], vertical_alignment="center")
        c0.markdown(foto_html(p.get("foto_id"), 44), unsafe_allow_html=True)
        c1.markdown(f"**{_esc(E.capitalizar(p.get('nome')))}** · {_esc(ean)} · em estoque {est}"
                    + (f" · {len(mods)} modelos" if len(mods) > 1 else ""))
        c2.button("Dar saída", key=f"est_sai_nm_{ean}", on_click=_bipe_na_saida, args=(ean,),
                  use_container_width=True)


def _saida(quem):
    ss = st.session_state
    st.segmented_control("Saída para", list(DESTINOS), default="🛒 Venda", key="est_dest")
    if _destino() == E.ENVIO_FULL:
        st.segmented_control("Para qual Full?", list(E.FULLS.values()), key="est_full_dest")
        if not _full_escolhido():
            st.warning("Escolha para qual Full está indo — cada conta tem o seu estoque.")
    aviso = ss.pop("est_aviso", None)
    if aviso:
        (st.error if aviso[1] else st.success)(aviso[0])
    _mostrar_desconhecido()
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
    lotes = _lotes_de_quem(movs, quem)
    _busca_por_nome_saida(prods, saldo)
    vista = st.segmented_control("Ver", VISTAS_SAIDA, default=VISTAS_SAIDA[0], key="est_sai_vista",
                                 label_visibility="collapsed") or VISTAS_SAIDA[0]
    # A janela de modelos e a pergunta do kit valem em qualquer vista: o
    # código escaneado na tela dos sem EAN também pode ter vários modelos.
    jan = ss.get("est_janela")
    variacoes = E.do_codigo(prods, jan) if jan else []
    if vista == VISTAS_SAIDA[1]:
        if variacoes:
            _janela(variacoes, saldo, codigos, por_id, quem)
        _sem_ean(prods, saldo)
        return
    if vista == VISTAS_SAIDA[2]:
        # A janela de modelos também aqui: «Dar saída» pela busca por nome
        # vale em qualquer vista.
        if variacoes:
            _janela(variacoes, saldo, codigos, por_id, quem)
        _saida_manual(prods, saldo, quem)
        return
    principal, lateral = st.columns([1.15, 1])
    atual = None
    with principal:
        if variacoes:
            _janela(variacoes, saldo, codigos, por_id, quem)
        elif ss.get("est_kit_pergunta") and ss.get("est_kit_pergunta", {}).get("lote") not in E.lotes_desfeitos(movs):
            _pergunta_kit(codigos, por_id, quem, movs)
        atual = _bipe_atual(lotes, por_id, saldo, quem)
    with lateral:
        with st.container(border=True):
            _lateral_saida(lotes, atual, movs, por_id, saldo, quem)
    st.caption("Cada bipe é 1 unidade e sai na hora. Código com mais de um modelo abre a "
               "janela para escolher. Código de kit ou de quantidade tira todos os itens dele.")
    _saida_manual(prods, saldo, quem)


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
        if E.eh_full(m0.get("local")):
            mot += f' ({E.NOME_LOCAL.get(m0.get("local"), "Full")})'
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
    foto_id, af = foto_da_tela(foto, f"baixa_{E.limpar_codigo(p.get('ean'))}")
    _p, movs, _c = E.carregar()
    linhas = E.linhas_de_baixa(p, q, motivo, quem, _quando(), local=local, volta=volta,
                               obs=obs, pedido=pedido, foto_id=foto_id, movs=movs)
    E.gravar_movimentos(linhas)
    return linhas, af


def _baixas(quem):
    ss = st.session_state
    rot = st.segmented_control("Motivo", list(MOTIVOS), default="💔 Quebra", key="est_motivo")
    motivo = MOTIVOS.get(rot or "💔 Quebra", E.QUEBRA)
    aviso = ss.pop("est_aviso", None)
    if aviso:
        (st.error if aviso[1] else st.success)(aviso[0])
    _mostrar_desconhecido()
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
            ss.pop("est_bx_cod", None)
            ss["est_desconhecido"] = cod
            _mostrar_desconhecido()
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
    fis, full = saldo.get((p["id"], E.FISICO), 0), E.no_full(saldo, p["id"])
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
            lr = st.selectbox("Saiu de qual estoque?", ["físico"] + list(E.FULLS.values()))
            local = next((k for k, v in E.FULLS.items() if v == lr), E.FISICO)
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
        _lb, af = _gravar_baixa(p, motivo, quem, int(q), volta, local, obs.strip(), pedido.strip(), foto)
        oque = ("voltou ao estoque" if motivo == E.DEVOLUCAO and volta else
                f"perda de {_rs(int(q) * E.numero(p.get('custo')))}")
        _avisar(*_com_foto(f"✓ {NOME_MOTIVO[motivo]}: {int(q)}× {E.nome_completo(p)} — {oque}.", af))
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
        ss["est_desconhecido"] = cod
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
    # O código de barras vai à DIREITA do nome, no mesmo cartão (dono, 23/11):
    # embaixo ele dobrava a altura de cada kit.
    barras = E.svg_ean13(k.get("codigo"), modulo=1, altura=30) if k.get("codigo") else ""
    return (f'<div style="display:flex;gap:10px;align-items:center">{foto_html(k.get("foto_id"), 52)}'
            f'<div style="min-width:0;flex:1"><b>{_esc(k.get("nome"))}</b>'
            f'<div style="font-size:12px;color:#9AA3AE">{_esc(lista)}</div>'
            f'<div style="font-size:12px;color:{cor}">dá para montar: {n}{_esc(falta_txt)} · custo '
            f'{_rs(E.custo_da_receita(itens, por_id))}</div></div>'
            f'<div style="flex-shrink:0;line-height:0">{barras}</div></div>')


KITS_NA_TELA = 3


def kits_a_mostrar(kits, todos=False, abertos=()):
    """Os kits da lista: os últimos KITS_NA_TELA criados, o mais novo em cima. Pura.

    A ordem da aba é a ordem de criação (cada kit novo é uma linha nova no
    fim). O kit que está sendo editado ou impresso fica, mesmo sendo antigo —
    senão o editor some no meio do trabalho.
    """
    novos = list(reversed(kits))
    if todos:
        return novos
    topo = novos[:KITS_NA_TELA]
    return topo + [k for k in novos[KITS_NA_TELA:] if k.get("codigo") in abertos]


def _kits(quem):
    ss = st.session_state
    aviso = ss.pop("est_aviso", None)
    if aviso:
        (st.error if aviso[1] else st.success)(aviso[0])
    _mostrar_desconhecido()
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
        _kits_cadastrados(codigos, por_id, saldo, prods)


def _criar_kit(prods, codigos, por_id, saldo, nova, quem):
    # Função própria, e não bloco dentro do `with`: o `return` do kit vazio
    # saía da tela INTEIRA e a lista de kits cadastrados sumia (navegador, 11/11).
    ss = st.session_state
    st.markdown("**Criar kit · 1) bipe os itens  2) nome e foto  3) gerar código**")
    if nova:
        st.markdown("**Kit criado — imprima a etiqueta:**")
        _etiqueta(nova[0], nova[1])
        # Errou o nome? Abre o editor do kit que acabou de nascer — ele é o
        # primeiro da lista ao lado (dono, 23/11).
        st.button("✎ editar este kit", key="est_kit_novo_ed", on_click=_abrir_ed_kit, args=(nova[0],))
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
                foto_id, af = foto_da_tela(foto, f"kit_{novo}")
                E.gravar_codigo(E.linha_de_codigo(novo, "kit", nome, "", dict(kit), quem,
                                                  _quando(), foto_id=foto_id))
                ss["est_etiqueta_nova"] = (novo, str(nome).strip())
                _avisar(*_com_foto(f"✓ Kit «{str(nome).strip()}» criado com o código {novo}.", af))
                _limpar_kit()
                st.rerun()
            except Exception as e:
                st.error(f"Não gravei o kit — a planilha respondeu: {e}")


def _kits_cadastrados(codigos, por_id, saldo, prods=()):
    ss = st.session_state
    st.markdown("**Kits cadastrados**")
    kits = [k for k in codigos if k.get("tipo") == "kit"]
    if not kits:
        st.caption("Nenhum kit ainda.")
    todos = len(kits) > KITS_NA_TELA and st.toggle(
        f"Ver todos os {len(kits)} kits", key="est_kits_todos")
    abertos = (ss.get("est_kit_ed"), ss.get("est_imprimir"))
    for k in kits_a_mostrar(kits, todos, abertos):
        with st.container(border=True):
            st.markdown(kit_card_html(k, por_id, saldo), unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            if c1.button("🖨 imprimir", key=f"est_kp_{k['codigo']}", use_container_width=True):
                ss["est_imprimir"] = k["codigo"]
            c2.button("✎ editar", key=f"est_ke_ab_{k['codigo']}", use_container_width=True,
                      on_click=_abrir_ed_kit, args=(k["codigo"],))
            if ss.get("est_kit_ed") == k["codigo"]:
                _editar_kit(k, por_id, prods)
            if ss.get("est_imprimir") == k["codigo"]:
                _etiqueta(k["codigo"], k.get("nome"), " · ".join(
                    E.nome_completo(por_id.get(pid, {})) for pid in E.itens_do_codigo(k)))


def _abrir_ed_kit(codigo):
    st.session_state["est_kit_ed"] = codigo


def _fechar_ed_kit():
    ss = st.session_state
    ss.pop("est_kit_ed", None)
    ss["est_kit_ek"] = int(ss.get("est_kit_ek") or 0) + 1      # campos e foto nascem limpos


def _ch_kit(campo, codigo, extra=""):
    return f"est_ked_{campo}_{st.session_state.get('est_kit_ek', 0)}_{codigo}{extra}"


def receita_editada(atual, digitados, novo_pid="", novo_q=0):
    """({produto_id: qtd}, erro) da receita depois do ✎ editar do kit. Pura.

    Quantidade 0 tira o item; o item novo soma ao que já existir dele."""
    fora = {}
    for pid in atual:
        q = int(digitados.get(pid, atual[pid]) or 0)
        if q > 0:
            fora[pid] = q
    if novo_pid and int(novo_q or 0) > 0:
        fora[novo_pid] = fora.get(novo_pid, 0) + int(novo_q)
    if not fora:
        return {}, "o kit ficou sem item nenhum."
    return fora, ""


def _salvar_kit(codigo, atual, opcoes):
    """Callback: nome, foto e itens do kit, de uma vez."""
    import json as _json
    ss = st.session_state
    nome = " ".join(str(ss.get(_ch_kit("nome", codigo)) or "").split())
    if not nome:
        _avisar("Nada foi gravado — falta o nome do kit.", True)
        return
    rec, erro = receita_editada(atual, {pid: ss.get(_ch_kit("q", codigo, f"_{pid}")) for pid in atual},
                                opcoes.get(ss.get(_ch_kit("novo", codigo)) or "", ""),
                                ss.get(_ch_kit("novo_q", codigo)) or 0)
    if erro:
        _avisar(f"Nada foi gravado — {erro}", True)
        return
    try:
        mud = {"nome": nome, "itens": _json.dumps(rec, ensure_ascii=False)}
        foto_id, af = foto_da_tela(ss.get(_ch_kit("foto", codigo)), f"kit_{codigo}")
        if foto_id:
            mud["foto_id"] = foto_id
        E.atualizar_codigos({codigo: mud})
        _avisar(*_com_foto("✓ Kit atualizado.", af))
        _fechar_ed_kit()
    except Exception as e:
        _avisar(f"Não gravei — a planilha respondeu: {e}", True)


def _editar_kit(k, por_id, prods):
    """O ✎ editar do kit INTEIRO (dono, 17/11: «e para editar a foto do kit?
    Eu tenho que falar absolutamente tudo?»): nome, foto e itens — quanto de
    cada, tirar (0) e pôr um novo — com um Salvar e um Cancelar."""
    ss = st.session_state
    cod = k["codigo"]
    atual = E.itens_do_codigo(k)
    with st.container(border=True):
        ss.setdefault(_ch_kit("nome", cod), str(k.get("nome") or ""))
        st.text_input("Nome do kit", key=_ch_kit("nome", cod))
        st.file_uploader("Foto do kit", type=None, key=_ch_kit("foto", cod))
        st.markdown("**Itens** — 0 tira do kit")
        for pid, q in atual.items():
            a, b = st.columns([3, 1], vertical_alignment="center")
            a.markdown(_esc(E.nome_completo(por_id.get(pid, {})) or "?"))
            ss.setdefault(_ch_kit("q", cod, f"_{pid}"), int(q))
            b.number_input("Qtd", min_value=0, step=1, key=_ch_kit("q", cod, f"_{pid}"),
                           label_visibility="collapsed")
        opcoes = {E.nome_completo(p): p["id"] for p in sorted(
            E.ativos(prods), key=lambda p: E._sem_acento(E.nome_completo(p))) if p["id"] not in atual}
        a, b = st.columns([3, 1], vertical_alignment="bottom")
        a.selectbox("Pôr mais um item", [""] + list(opcoes), key=_ch_kit("novo", cod),
                    format_func=lambda x: x or "— escolha um produto —")
        b.number_input("Qtd", min_value=0, step=1, value=1, key=_ch_kit("novo_q", cod))
        c1, c2 = st.columns(2)
        c1.button("Salvar kit", key=f"est_ked_ok_{cod}", type="primary", use_container_width=True,
                  on_click=_salvar_kit, args=(cod, atual, opcoes))
        c2.button("Cancelar", key=f"est_ked_cx_{cod}", use_container_width=True, on_click=_fechar_ed_kit)


# ── PAINEL (Parte 5) ─────────────────────────────────────────────────────────

def _r0(v):
    return f"R$ {v:,.0f}".replace(",", ".")


def _por_conta_txt(pn):
    """' · ML1 3 · Shopee 1 2': as peças de cada Full, somadas. Pura."""
    t = {}
    for l in pn["linhas"]:
        for loc, q in l.get("por_full", {}).items():
            t[loc] = t.get(loc, 0) + max(q, 0)
    return "".join(f' · {E.FULLS[loc].replace("Full ", "")} {q}' for loc, q in t.items() if q)


def topo_painel_html(pn):
    """Os quatro quadros do topo. Pura."""
    pct = (pn["valor_parado"] / pn["valor"] * 100) if pn["valor"] else 0
    q = [("VALOR EM ESTOQUE", _r0(pn["valor"]), f'a custo · {pn["pecas_fisico"] + pn["pecas_full"]} peças · '
          f'{pn["produtos"]} produtos', "#E8EAED"),
         ("ESTOQUE FÍSICO", _r0(pn["valor_fisico"]), f'{pn["pecas_fisico"]} peças', "#E8EAED"),
         ("ESTOQUE FULL", _r0(pn["valor_full"]), f'{pn["pecas_full"]} peças' + _por_conta_txt(pn),
          "#7db4ec"),
         ("PARADO HÁ MAIS DE 3 MESES", _r0(pn["valor_parado"]), f'{len(pn["parados"])} produtos · '
          f'{pct:.1f}% do valor'.replace(".", ","), "#f0c060")]
    return ('<div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:8px 0">'
            + "".join(f'<div style="padding:12px;border-radius:12px;background:#2c2c2c">'
                      f'<div style="font-size:11px;color:#9AA3AE;letter-spacing:.1em">{t}</div>'
                      f'<div style="font-size:22px;font-weight:800;color:{c}">{v}</div>'
                      f'<div style="font-size:12px;color:#9AA3AE">{d}</div></div>' for t, v, d, c in q)
            + "</div>")


def faixas_html(pn):
    """As três faixas de idade, com barra proporcional ao valor. Pura."""
    tot = sum(pn["faixas"].values()) or 1
    rot = [("ok", "até 3 meses", "#4CC38A"), ("atencao", "3 a 5 meses · atenção", "#f0c060"),
           ("critico", "mais de 5 meses · crítico", "#E5534B")]
    return "".join(
        f'<div style="margin-top:8px"><div style="display:flex;justify-content:space-between;font-size:13px">'
        f'<span>{r}</span><b style="color:{c}">{_r0(pn["faixas"][f])}</b></div>'
        f'<div style="height:8px;border-radius:4px;background:#222;margin-top:4px">'
        f'<div style="width:{pn["faixas"][f] / tot * 100:.0f}%;height:8px;border-radius:4px;background:{c}">'
        f'</div></div></div>' for f, r, c in rot)


def _meses_txt(dias):
    if dias is None:
        return "—"
    m = dias // 30
    return f"{m} mês" if m == 1 else (f"{m} meses" if m else f"{dias} dias")


def _marcar(pid, quem):
    try:
        E.marcar_comprado(pid, quem, _quando())
        _avisar("✓ Marcado como comprado.")
    except Exception as e:
        _avisar(f"Não gravei — a planilha respondeu: {e}", True)


def sem_sku_html(lista):
    """A lista «Produtos sem SKU», para pôr o SKU depois (dono, 12/11). Pura."""
    if not lista:
        return ""
    itens = "".join(f'<div style="font-size:13px;margin-top:4px"><b>{_esc(E.nome_completo(p))}</b> '
                    f'<span style="color:#9AA3AE">· {_esc(p.get("codigo_fornecedor") or p.get("ean"))}'
                    f' · {_esc(m)}</span></div>' for p, m in lista)
    return (f'<div style="padding:12px 14px;border-radius:12px;background:#4a3a1a;margin:8px 0">'
            f'<div style="color:#f0c060;font-weight:800">⚠️ PRODUTOS SEM SKU · {len(lista)}</div>'
            f'<div style="color:#E8EAED;font-size:12px">sem o SKU, o custo não vem do Controle MS. '
            f'Bipe o produto na Entrada → ✎ Editar produto.</div>{itens}</div>')


def _alerta_sem_sku(prods):
    tab, erro = _tabela_sku()
    lista = E.sem_sku(prods, tab)
    if lista:
        st.markdown(sem_sku_html(lista), unsafe_allow_html=True)
    if erro:
        st.caption(f"Não consegui ler a aba {E.ABA_SKU} do Controle MS ({erro}): a lista acima só "
                   "mostra quem está SEM SKU, e não confere se o SKU existe na planilha.")


def agrupar_por_produto(linhas):
    """UMA linha por produto, as variações dentro dela (dono, 17/11: «não é
    para cada variação duplicar a linha… vai poluir demais»). Pura.

    Junta pelo código de barras (sem código, cada linha é dela mesma). Soma
    peças e valor; a idade é a da variação mais antiga, a última saída é a
    mais recente. `produto` é a primeira variação (foto, código, SKU), e
    `variacoes` traz os ids de todas — o histórico e a ficha usam as todas.
    """
    grupos, ordem = {}, []
    for l in linhas:
        p = l["produto"]
        chave = E.limpar_codigo(p.get("ean")) or p["id"]
        if chave not in grupos:
            grupos[chave] = []
            ordem.append(chave)
        grupos[chave].append(l)
    fora = []
    for ch in ordem:
        ls = grupos[ch]
        if len(ls) == 1:
            fora.append({**ls[0], "variacoes": [ls[0]["produto"]["id"]], "n_var": 1})
            continue
        p0 = ls[0]["produto"]
        por_full = {}
        for l in ls:
            for k, q in l.get("por_full", {}).items():
                por_full[k] = por_full.get(k, 0) + q
        dias = [l["dias"] for l in ls if l.get("dias") is not None]
        saidas = [l["ultima_saida"] for l in ls if l.get("ultima_saida")]
        custos = sorted({round(float(l.get("custo") or 0), 2) for l in ls})
        fora.append({
            "produto": p0, "variacoes": [l["produto"]["id"] for l in ls], "n_var": len(ls),
            "fisico": sum(l.get("fisico", 0) for l in ls), "full": sum(l.get("full", 0) for l in ls),
            "varejo": sum(l.get("varejo", 0) for l in ls), "atacado": sum(l.get("atacado", 0) for l in ls),
            "por_full": por_full, "custo": custos[0], "custo_max": custos[-1],
            "valor": sum(l.get("valor", 0) for l in ls),
            "dias": max(dias) if dias else None,
            "ultima_saida": max(saidas) if saidas else None})
    return fora


def nome_da_linha(g):
    """«Jogo de Dardo 46cm · 2 variações», ou o nome com a variação quando é uma só. Pura."""
    if g.get("n_var", 1) > 1:
        return f'{E.capitalizar(g["produto"].get("nome"))} · {g["n_var"]} variações'
    return E.nome_completo(g["produto"])


def tabela_produtos(linhas, busca=""):
    """As linhas da tabela, filtradas pela busca como TEXTO (passo 13). Pura.

    Busca por nome, variação, código do fornecedor ou código de barras. O
    "+" de "Porta 2 Relógio + Jóias" é letra, não padrão.
    """
    b = " ".join(str(busca or "").lower().split())
    fora = []
    for l in linhas:
        p = l["produto"]
        alvo = " ".join(str(x or "").lower() for x in (p.get("nome"), p.get("variacao"),
                                                       p.get("codigo_fornecedor"), p.get("ean"),
                                                       p.get("sku"), p.get("sku_atacado"),
                                                       p.get("fornecedor")))
        if b and b not in " ".join(alvo.split()) and E.limpar_codigo(b) != E.limpar_codigo(p.get("ean")):
            continue
        fora.append(l)
    # ORDEM ALFABÉTICA (dono, 17/11), sem acento e sem maiúscula: «Álbum»
    # junto de «album», antes de «Caixa». Era pelo valor. A busca vale para
    # cada variação, e o agrupamento vem depois: «preto» acha o produto.
    return sorted(agrupar_por_produto(fora), key=lambda l: E._sem_acento(nome_da_linha(l)))


def assinatura_da_lista(linhas):
    """Muda quando QUALQUER coisa que a tabela mostra muda. Pura.

    O Streamlit desmarca a tabela quando o DADO muda, não só quando muda a
    lista: a variação nova troca «Embaralhador» por «Embaralhador · 2
    variações» na mesma linha, e o produto fechava (17/11)."""
    import hashlib
    txt = "|".join(repr((l["produto"]["id"], nome_da_linha(l), l.get("fisico"), l.get("full"),
                         l.get("varejo"), l.get("atacado"), l.get("valor"), l.get("custo"),
                         l.get("custo_max"), sorted(l.get("por_full", {}).items()),
                         l.get("ultima_saida"), l.get("dias"),
                         *(l["produto"].get(k) for k in ("foto_id", "sku", "codigo_fornecedor",
                                                         "ean", "fornecedor"))))
                   for l in linhas)
    return hashlib.md5(txt.encode()).hexdigest()[:10]


def produto_escolhido(linhas, sel, guardado, desmarcou, ean_guardado=""):
    """O id do produto aberto no Estoque cadastrado. Pura.

    Linha marcada: ela. `desmarcou` (a MESMA tabela tinha marcação e agora
    não tem): fechou. Tabela desmarcada por ter nascido de novo (variação
    nova, excluída, busca): fica aberto o produto guardado, se ainda está
    na lista. Tratar «sem marcação» como «desmarcou» fechava o produto no
    clique seguinte — o «+ Nova variação» que não abria (17/11).
    """
    ids = [l["produto"]["id"] for l in linhas]
    if sel and sel[0] < len(ids):
        return ids[sel[0]]
    if desmarcou or not guardado:
        return None
    if guardado in ids:
        return guardado
    # A variação aberta foi excluída: fica aberta outra do mesmo produto.
    return next((l["produto"]["id"] for l in linhas
                 if ean_guardado and E.limpar_codigo(l["produto"].get("ean")) == ean_guardado), None)


def opcoes_fornecedor_em_massa(prods):
    """{rótulo: [ids das variações]} — UM produto por código, em ordem
    alfabética, com o fornecedor que já tem. Pura."""
    por = {}
    for p in E.ativos(prods):
        ch = E.limpar_codigo(p.get("ean")) or p["id"]
        por.setdefault(ch, []).append(p)
    fora = {}
    for vs in sorted(por.values(), key=lambda vs: E._sem_acento(E.capitalizar(vs[0].get("nome")))):
        f = str(vs[0].get("fornecedor") or "").strip()
        cod = vs[0].get("codigo_fornecedor") or vs[0].get("ean") or ""
        rot = f'{E.capitalizar(vs[0].get("nome"))} · {cod}' + (f" — {f}" if f else " — sem fornecedor")
        while rot in fora:                   # dois produtos com o mesmo nome e código
            rot += " "
        fora[rot] = [v["id"] for v in vs]
    return fora


def mudancas_fornecedor(opcoes, escolhidos, fornecedor):
    """({id: {"fornecedor": nome}}, erro) do preenchimento em massa. Pura."""
    nome = " ".join(str(fornecedor or "").split())
    if not escolhidos:
        return {}, "Escolha ao menos um produto."
    if not nome:
        return {}, "Escreva o fornecedor."
    return {pid: {"fornecedor": nome} for r in escolhidos for pid in opcoes.get(r, [])}, ""


def opcoes_das_marcadas(marcadas):
    """{nome da linha: ids de todas as variações} das linhas marcadas. Pura."""
    fora = {}
    for l in marcadas:
        rot = nome_da_linha(l)
        while rot in fora:
            rot += " "
        fora[rot] = list(l.get("variacoes") or [l["produto"]["id"]])
    return fora


def _salvar_fornecedor_em_massa(opcoes):
    ss = st.session_state
    k = int(ss.get("est_fm_k") or 0)
    mud, erro = mudancas_fornecedor(opcoes, list(opcoes), ss.get(f"est_fm_nome_{k}"))
    if erro:
        _avisar(f"Nada foi gravado — {erro}", erro=True)
        return
    try:
        E.atualizar_produtos(mud)
        nome = next(iter(mud.values()))["fornecedor"]
        _avisar(f"✓ Fornecedor «{nome}» gravado em {len(opcoes)} produto(s).")
        ss["est_fm_k"] = k + 1                      # o campo nasce limpo
    except Exception as e:
        _avisar(f"Não gravei — a planilha respondeu: {e}", erro=True)


def _fornecedor_em_massa(marcadas):
    """Fornecedor de vários produtos de uma vez (dono, 17/11): os MARCADOS
    nas caixinhas da lista (a do cabeçalho marca todos)."""
    k = int(st.session_state.get("est_fm_k") or 0)
    if len(marcadas) < 2:
        st.caption("🏷 Para preencher o fornecedor de vários de uma vez, marque as caixinhas "
                   "na lista (a do cabeçalho marca todos).")
        return
    opcoes = opcoes_das_marcadas(marcadas)
    with st.container(border=True):
        st.markdown(f"**🏷 Fornecedor dos {len(marcadas)} produtos marcados**")
        st.text_input("Fornecedor", key=f"est_fm_nome_{k}", placeholder="nome do fornecedor")
        st.button(f"Salvar fornecedor nos {len(marcadas)} marcados", key=f"est_fm_ok_{k}", type="primary",
                  on_click=_salvar_fornecedor_em_massa, args=(opcoes,))


def variacao_pode_excluir(v, saldo, codigos=()):
    """(pode, aviso). Pura. Dono, 17/11: «preciso poder excluir a quantidade
    sem ter que dar baixa» — variação COM peça sai, e as peças saem junto
    como ajuste de contagem (o aviso diz quantas). Só a que entra num kit
    não sai: o kit tiraria peça de uma linha que sumiu."""
    if E.kits_com(codigos, v.get("id")):
        return False, "entra num kit — troque o kit antes de excluir"
    q = sum(n for (pid, _loc), n in saldo.items() if pid == v.get("id"))
    if q:
        return True, f"as {q} peça(s) dela saem do estoque como ajuste de contagem, sem baixa"
    return True, ""


def nomes_ja_cadastrados(prods, ean):
    """Os nomes de variação (minúsculos) já ATIVOS neste código. Pura.
    Salvar duas vezes — clique duplo, ou de novo depois de um erro da
    planilha no meio — duplicava todas as variações (dono, 17/11)."""
    ean = E.limpar_codigo(ean)
    return {" ".join(str(p.get("variacao") or "").split()).lower() for p in prods
            if E.limpar_codigo(p.get("ean")) == ean and str(p.get("ativo", "1")).strip() != "0"}


def _pedir_exclusao(pid):
    st.session_state["est_pn_excluir"] = pid


def _cancelar_exclusao():
    st.session_state.pop("est_pn_excluir", None)


def _excluir_variacao(pid, nome, quem=""):
    """Zera as peças (ajuste de contagem) e desativa (ativo=0): some do
    estoque e das buscas; o histórico fica. Lê a planilha na hora: o saldo
    da tela pode ter 2 minutos."""
    try:
        prods, movs, codigos = E.carregar_agora()
        p = next((x for x in prods if x.get("id") == pid), None)
        if p is None:
            _avisar(f"Não achei «{nome}» na planilha — nada foi excluído.", erro=True)
            return
        pode, motivo = variacao_pode_excluir(p, E.saldos(movs), codigos)
        if not pode:
            _avisar(f"«{nome}» {motivo}. Nada foi excluído.", erro=True)
            return
        zera = E.linhas_de_zerar(p, movs, quem, _quando(), "variação excluída no Estoque cadastrado")
        if zera:
            E.gravar_movimentos(zera)
        E.atualizar_produtos({pid: {"ativo": "0"}})
        n = -sum(int(m["qtd"]) for m in zera)
        _avisar(f"✓ Variação «{nome}» excluída" + (f" — {n} peça(s) saíram do estoque." if n else "."))
    except Exception as e:
        _avisar(f"Não excluí — a planilha respondeu: {e}", erro=True)
    st.session_state.pop("est_pn_excluir", None)


def _variacoes_do_painel(variacoes, saldo, quem, pf):
    """As variações DENTRO do quadro do produto (dono, 17/11): nome e foto
    de cada uma editáveis ali mesmo, ✕ para excluir (com confirmação) e ➕
    Nova variação — tudo gravado pelo «Salvar tudo» do quadro."""
    ss = st.session_state
    st.markdown("**Variações**")
    for v in variacoes:
        c0, c1, c2, c3, c4 = st.columns([0.6, 2.4, 1.1, 2.4, 0.5], vertical_alignment="center")
        c0.markdown(foto_html(v.get("foto_id"), 44), unsafe_allow_html=True)
        ss.setdefault(_ch_vn(pf, v["id"]), str(v.get("variacao") or ""))
        c1.text_input("Nome da variação", key=_ch_vn(pf, v["id"]), label_visibility="collapsed",
                      placeholder="nome da variação")
        # A QUANTIDADE (dono, 17/11: «se eu coloquei errado e precisar
        # editar?»): o físico de cada variação; mudou, o «Salvar tudo» grava
        # a diferença como ajuste — o mesmo caminho da Contagem.
        ss.setdefault(_ch_vq(pf, v["id"]), int(saldo.get((v["id"], E.FISICO), 0)))
        _full = sum(q for (pid, loc), q in saldo.items() if pid == v["id"] and E.eh_full(loc))
        c2.number_input("Físico", step=1, key=_ch_vq(pf, v["id"]), label_visibility="collapsed",
                        help="Peças no físico. Mude para corrigir: grava um ajuste."
                             + (f" No Full: {_full}." if _full else ""))
        c3.file_uploader("Foto da variação", type=None, key=_ch_vf(pf, v["id"]),
                         label_visibility="collapsed")
        # A última não tem ✕: excluir a única variação é excluir o produto.
        if len(variacoes) > 1:
            c4.button("✕", key=f"est_pn_x_{v['id']}", help="Excluir esta variação",
                      on_click=_pedir_exclusao, args=(v["id"],))
    # O QUE JÁ FOI CADASTRADO ANTES (17/11): produto sem nome COM estoque ao
    # lado das variações — as peças contam duas vezes. Um clique arruma.
    pai = pai_sem_nome(variacoes) if len(variacoes) > 1 else None
    if pai is not None:
        q_pai = sum(n for (pid, _l), n in saldo.items() if pid == pai["id"])
        st.warning(f"«{E.nome_completo(pai)}» (sem variação) ainda tem {q_pai} peça(s) somando com as "
                   "variações. Com variações, o estoque é só o delas.")
        st.button(f"Zerar «{E.nome_completo(pai)}» e tirar da lista", key="est_pn_zerar_pai",
                  on_click=_zerar_pai_agora, args=(pai, quem))
    alvo = next((v for v in variacoes if v["id"] == ss.get("est_pn_excluir")), None)
    if alvo is not None:
        nome = E.nome_completo(alvo)
        pode, motivo = variacao_pode_excluir(alvo, saldo, E.carregar()[2])
        if not pode:
            st.warning(f"«{nome}» {motivo}.")
            st.button("Ok", key="est_pn_x_ok", on_click=_cancelar_exclusao)
        else:
            st.warning(f"Excluir a variação «{nome}»? Ela some do estoque; o histórico fica."
                       + (f" {motivo[0].upper()}{motivo[1:]}." if motivo else ""))
            a, b = st.columns(2)
            a.button("Sim, excluir", key="est_pn_x_sim", type="primary", use_container_width=True,
                     on_click=_excluir_variacao, args=(alvo["id"], nome, quem))
            b.button("Cancelar", key="est_pn_x_nao", use_container_width=True, on_click=_cancelar_exclusao)
    st.button("➕ Nova variação", key="est_pn_nova_var", on_click=_abrir_nova_variacao)
    _nova_variacao(variacoes, quem, sufixo_ed="_pn", botoes=False)


def _painel_resumo(quem):
    """A aba «📈 Painel» (dono, 17/11): os quadros de valor, o tempo parado e
    a lista do Renan saíram do Estoque cadastrado — «o painel ainda vamos
    desenvolver o que quero ver», então ficam aqui por enquanto."""
    import placar_core as _pc
    ss = st.session_state
    aviso = ss.pop("est_aviso", None)
    if aviso:
        (st.error if aviso[1] else st.success)(aviso[0])
    try:
        prods, movs, codigos = E.carregar()
        marcados = E.marcados_de(E.compras())
    except Exception as e:
        st.error(f"Não consegui ler o estoque na planilha: {e}")
        return
    pn = E.painel(prods, movs, _pc.agora_br().date())
    st.markdown(topo_painel_html(pn), unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Tempo parado · conta desde o registro**")
        st.markdown(faixas_html(pn), unsafe_allow_html=True)
        for l in pn["parados"][:5]:
            p = l["produto"]
            cor = "#E5534B" if l["faixa"] == "critico" else "#f0c060"
            st.markdown(f'<div style="display:flex;gap:8px;align-items:center;font-size:13px;margin-top:6px">'
                        f'{foto_html(p.get("foto_id"), 30)}<b style="flex:1">{_esc(E.nome_completo(p))}</b>'
                        f'<span style="color:{cor};font-weight:800">{_meses_txt(l["dias"])}</span>'
                        f'<span>{max(l["fisico"], 0) + max(l["full"], 0)} un</span>'
                        f'<b>{_r0(l["valor"])}</b></div>', unsafe_allow_html=True)
        if len(pn["parados"]) > 5:
            st.caption(f'+ {len(pn["parados"]) - 5} — estão todos na tabela abaixo, pela coluna "No estoque há".')
    with c2:
        st.markdown("**Lista de compra do Renan**")
        lista = E.lista_de_compra(prods, movs, codigos, marcados)
        if not lista:
            st.caption("Nada faltando.")
        for i in lista:
            p = i["produto"]
            a, b = st.columns([3, 1.2])
            a.markdown(f'**{_esc(E.nome_completo(p))}**  \n:red[{_esc(i["motivo"])}]')
            if i["comprado"]:
                b.markdown(":green[✓ comprado]")
            else:
                b.button("marcar comprado", key=f"est_cmp_{p['id']}", on_click=_marcar,
                         args=(p["id"], quem), use_container_width=True)
        st.caption("Entra sozinho quando vende sem estoque ou um kit trava. Sai sozinho quando a "
                   "mercadoria dá entrada.")


def _painel(quem):
    import gdrive
    import pandas as pd
    import placar_core as _pc
    ss = st.session_state
    aviso = ss.pop("est_aviso", None)
    if aviso:
        (st.error if aviso[1] else st.success)(aviso[0])
    _mostrar_desconhecido()
    try:
        prods, movs, codigos = E.carregar()
    except Exception as e:
        st.error(f"Não consegui ler o estoque na planilha: {e}")
        return
    pn = E.painel(prods, movs, _pc.agora_br().date())
    _alerta_sem_sku(prods)
    st.markdown("**Todos os produtos**")
    busca = st.text_input("Buscar", key="est_busca", placeholder="🔎 nome, código ou bipe",
                          label_visibility="collapsed")
    linhas = tabela_produtos(pn["linhas"], busca)
    df = pd.DataFrame([{
        "foto": (gdrive.url_thumbnail(E.foto_principal(l["produto"]), 120)
                 if E.foto_principal(l["produto"]) else ""),
        "Produto": nome_da_linha(l),
        "Código": l["produto"].get("codigo_fornecedor") or "—",
        "Código de barras": E.limpar_codigo(l["produto"].get("ean")) or "—",
        "Fornecedor": l["produto"].get("fornecedor") or "—",
        "SKU": E.normalizar_sku(l["produto"].get("sku")) or "—",
        "Físico": l["fisico"], "Full": l["full"],
        "Varejo · atacado": f'{l.get("varejo", 0)} · {l.get("atacado", 0)}',
        "Full por conta": " · ".join(f'{E.FULLS[k].replace("Full ", "")} {q}'
                                     for k, q in l.get("por_full", {}).items()) or "—",
        "Custo": (_rs(l["custo"]) if l.get("custo_max", l["custo"]) == l["custo"]
                  else f'{_rs(l["custo"])} a {_rs(l["custo_max"])}'), "Valor": _r0(l["valor"]),
        "No estoque há": _meses_txt(l["dias"]),
        "Última saída": l["ultima_saida"].strftime("%d/%m") if l["ultima_saida"] else "—",
    } for l in linhas])
    if df.empty:
        st.caption("Nenhum produto" + (" com essa busca." if busca else " cadastrado ainda."))
        return
    # O PRODUTO ESCOLHIDO NÃO SOME (dono, 17/11: «clico em + nova variação
    # e não abre»). Salvar uma variação põe uma linha nova na lista, e o
    # Streamlit desmarca a tabela — o produto, o botão e as variações sumiam.
    # Lista nova = tabela nova (a chave leva a assinatura) e o produto
    # escolhido vem do que foi guardado; lista igual, vale o clique.
    sig = assinatura_da_lista(linhas)
    ev = st.dataframe(df, hide_index=True, use_container_width=True, on_select="rerun",
                      selection_mode="multi-row", key=f"est_tab_{sig}",
                      column_config={"foto": st.column_config.ImageColumn("", width="small")})
    st.caption(f"{len(linhas)} produto(s)" + (f" com «{busca.strip()}»" if busca.strip() else ""))
    # VÁRIAS MARCADAS (dono, 17/11: «selecionar os produtos nas caixinhas, na
    # lista, para colocar o fornecedor em massa»): uma marcada abre o
    # produto; duas ou mais (ou a caixinha de todos) abrem o fornecedor.
    marcadas = [linhas[i] for i in (getattr(getattr(ev, "selection", None), "rows", []) or [])
                if i < len(linhas)]
    _fornecedor_em_massa(marcadas)
    sel = [linhas.index(marcadas[0])] if len(marcadas) == 1 else []
    if len(marcadas) > 1:
        ss["est_pn_sig"], ss["est_pn_pid"], ss["est_pn_sel"] = sig, None, True
        return
    desmarcou = ss.get("est_pn_sig") == sig and bool(ss.get("est_pn_sel")) and not sel
    pid = produto_escolhido(linhas, sel, ss.get("est_pn_pid"), desmarcou, ss.get("est_pn_ean", ""))
    p = next((l["produto"] for l in linhas if l["produto"]["id"] == pid), None)
    ss["est_pn_sig"], ss["est_pn_pid"], ss["est_pn_sel"] = sig, pid, bool(sel)
    ss["est_pn_ean"] = E.limpar_codigo(p.get("ean")) if p else ""
    if p:
        # ✎ EDITAR NO ESTOQUE CADASTRADO (dono, 17/11: «cadê o botão de
        # editar? preciso pôr foto»). O mesmo editor da Entrada, com todos
        # os campos; sufixo próprio nas chaves.
        _vs_pn = E.do_codigo(prods, p.get("ean")) or [p]
        _editar_produto(_vs_pn, quem, sufixo="_pn", saldo=E.saldos(movs))
        # Uma linha por produto: o histórico é o de TODAS as variações dele.
        _ids_pn = {v["id"]: v for v in _vs_pn}
        _multi = len(_vs_pn) > 1
        st.markdown(f"**Histórico · {_esc(E.capitalizar(p.get('nome')) if _multi else E.nome_completo(p))}**")
        hist = [m for m in movs if m.get("produto_id") in _ids_pn][-30:]
        st.dataframe(pd.DataFrame([{**({"Variação": E.capitalizar(str(_ids_pn[m["produto_id"]].get("variacao")
                                                                    or "—"))} if _multi else {}),
                                    "Quando": m.get("quando"), "O quê": m.get("tipo"),
                                    "Onde": E.NOME_LOCAL.get(m.get("local"), m.get("local")),
                                    "Qtd": E.inteiro(m.get("qtd")), "Quem": m.get("quem"),
                                    "Obs": m.get("obs")} for m in reversed(hist)]),
                     hide_index=True, use_container_width=True)
    else:
        st.caption("Clique numa linha para ✎ editar o produto (foto, SKU, custo, nome…) "
                   "e ver o histórico de entradas e saídas.")


# ── CONTAGEM (Parte 6) ───────────────────────────────────────────────────────

# A CÂMERA DO CELULAR. O Safari do iPhone não lê código de barras sozinho
# (não tem BarcodeDetector): a leitura vem da biblioteca html5-qrcode, que
# traz o decodificador dela. O código lido é entregue à MESMA barra do
# leitor USB — um caminho só para o bipe, venha de onde vier.
_CAMERA = """<div id="leitor" style="width:100%;max-width:420px;margin:auto"></div>
<div id="msg" style="font:13px sans-serif;color:#9AA3AE;text-align:center;margin-top:4px"></div>
<script src="https://cdn.jsdelivr.net/npm/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
<script>
(function () {
  var W = window.parent, ultimo = '', visto = 0;
  function entrega(cod) {
    // A MESMA ETIQUETA PARADA NA FRENTE não conta de novo: a câmera lê dez
    // vezes por segundo. Só volta a contar depois que ela SAIU da imagem
    // (mais de 1,2 s sem ser vista) — para contar duas iguais, tira e põe.
    var agora = Date.now();
    var parada = (cod === ultimo && agora - visto < 1200);
    visto = agora; ultimo = cod;
    if (parada) return;
    var b = W.document.querySelector('.st-key-est_bipe input');
    if (!b) return;
    Object.getOwnPropertyDescriptor(W.HTMLInputElement.prototype, 'value').set.call(b, cod);
    b.dispatchEvent(new Event('input', {bubbles: true}));
    b.focus();  // rola de propósito: o código lido abre a ficha logo abaixo da barra
    setTimeout(function () { b.blur(); }, 60);
    if (navigator.vibrate) navigator.vibrate(80);
    document.getElementById('msg').textContent = 'lido: ' + cod;
  }
  try {
    var F = Html5QrcodeSupportedFormats;
    var h = new Html5Qrcode('leitor', {formatsToSupport: [F.EAN_13, F.EAN_8, F.UPC_A, F.UPC_E, F.CODE_128]});
    h.start({facingMode: 'environment'}, {fps: 10, qrbox: {width: 260, height: 110}}, entrega,
            function () {}).catch(function (e) {
      document.getElementById('msg').textContent = 'Câmera não abriu: ' + e + ' — permita a câmera no navegador.';
    });
  } catch (e) {
    document.getElementById('msg').textContent = 'Leitor da câmera não carregou: ' + e;
  }
})();
</script>"""


def _bipe_na_contagem(cod):
    """Cada bipe do mesmo produto soma 1; bipou outro, o anterior é gravado."""
    ss = st.session_state
    try:
        prods, _m, codigos = E.carregar()
    except Exception as e:
        _avisar(f"Não consegui ler o estoque: {e}", True)
        return
    var = E.do_codigo(prods, cod)
    if not var:
        if E.codigo_gerado(codigos, cod):
            _avisar("Esse é um código de kit/quantidade: na contagem, bipe cada PRODUTO.", True)
        else:
            ss["est_desconhecido"] = cod
        return
    if len(var) > 1:
        ss["est_ct_escolha"] = cod
        return
    _contar(var[0]["id"])


def _contar(pid):
    ss = st.session_state
    ss.pop("est_ct_escolha", None)
    atual = ss.get("est_ct")
    if atual and atual["pid"] == pid:
        ss["est_ct_q"] = int(ss.get("est_ct_q", 0) or 0) + 1
        return
    if atual:
        _gravar_contado()
    ss["est_ct"] = {"pid": pid}
    ss["est_ct_q"] = 1


def _gravar_contado():
    """Grava o produto que estava sendo contado. Callback."""
    ss = st.session_state
    atual = ss.get("est_ct")
    q = int(ss.get("est_ct_q", 0) or 0)
    cid = ss.get("est_ct_id")
    if not atual or not cid:
        return
    try:
        if q > 0:
            E.gravar_contado(cid, atual["pid"], q, str(ss.get("est_ct_onde") or "").strip(),
                             ss.get("est_quem", ""), _quando())
        ss.pop("est_ct", None)
        ss.pop("est_ct_q", None)
    except Exception as e:
        _avisar(f"Não gravei a contagem — a planilha respondeu: {e}", True)


def _abrir_contagem(quem):
    try:
        E.abrir_contagem(quem, _quando())
        _avisar("✓ Contagem aberta. Cada pessoa escolhe onde vai contar e começa a bipar.")
    except Exception as e:
        _avisar(f"Não abri — a planilha respondeu: {e}", True)


def _ajustar(cid, quem):
    try:
        prods, movs, _c = E.carregar()
        _cs, contados = E.contagem()
        fech = E.fechamento(prods, movs, contados, cid)
        E.gravar_movimentos(E.linhas_de_ajuste(fech, quem, _quando(), cid, movs=movs))
        E.fechar_contagem(cid, quem, _quando())
        _avisar(f"✓ Contagem fechada: {fech['diferenca']} produto(s) ajustado(s), "
                f"{fech['bateu']} bateram.")
    except Exception as e:
        _avisar(f"Não fechei — a planilha respondeu: {e}", True)


def _contagem(quem):
    import auth
    ss = st.session_state
    aviso = ss.pop("est_aviso", None)
    if aviso:
        (st.error if aviso[1] else st.success)(aviso[0])
    _mostrar_desconhecido()
    try:
        prods, movs, _c = E.carregar()
        contagens, contados = E.contagem()
    except Exception as e:
        st.error(f"Não consegui ler o estoque na planilha: {e}")
        return
    gestor = auth.eh_gestor(quem)
    aberta = E.contagem_aberta(contagens)
    if not aberta:
        st.info("Nenhuma contagem aberta.")
        if gestor:
            st.button("ABRIR CONTAGEM", type="primary", key="est_ct_abrir",
                      on_click=_abrir_contagem, args=(quem,))
        else:
            st.caption("Quem abre a contagem é o gestor.")
        return
    cid = aberta["id"]
    ss["est_ct_id"] = cid
    por_id = {p["id"]: p for p in prods}
    st.caption(f'Contagem de {str(aberta.get("aberta_em"))[:10]} · aberta por {aberta.get("aberta_por")}')
    abas = ["Contar"] + (["Fechar (gestor)"] if gestor else [])
    aba = st.segmented_control("Contagem", abas, default="Contar", key="est_ct_aba",
                               label_visibility="collapsed") or "Contar"
    if aba == "Contar":
        _tela_contar(por_id, contados, cid, prods)
    else:
        _tela_fechar(prods, movs, contados, cid, quem)


def _tela_contar(por_id, contados, cid, prods):
    ss = st.session_state
    st.text_input("Onde você vai contar", key="est_ct_onde", placeholder="Prateleira B")
    _barra(saida=True)
    esc = ss.get("est_ct_escolha")
    var = E.do_codigo(prods, esc) if esc else []
    if var:
        st.warning("Este código tem mais de um modelo. Qual você está contando?")
        for v in var:
            st.button(str(v.get("variacao") or E.nome_completo(v)), key=f"est_cte_{v['id']}",
                      on_click=_contar, args=(v["id"],), use_container_width=True)
    atual = ss.get("est_ct")
    if atual and atual["pid"] in por_id:
        p = por_id[atual["pid"]]
        st.markdown(f'<div style="display:flex;gap:10px;align-items:center;padding:10px;border-radius:12px;'
                    f'background:#1f3a2c;margin:8px 0">{foto_html(p.get("foto_id"), 56)}<div>'
                    f'<b>{_esc(E.nome_completo(p))}</b><div style="font-size:12px;color:#9AA3AE">'
                    f'{_esc(p.get("codigo_fornecedor") or p.get("ean"))} · bipe lido ✓</div></div></div>',
                    unsafe_allow_html=True)
        st.number_input("Quantidade (cada bipe soma 1 · ou digite o da caixa)", min_value=0, step=1,
                        key="est_ct_q")
        st.button("CONFIRMAR E PRÓXIMO", type="primary", key="est_ct_ok", on_click=_gravar_contado,
                  use_container_width=True)
    elif not var:
        st.caption("Bipe o produto. Cada bipe do mesmo produto soma 1; bipou outro, o anterior é gravado.")
    st.markdown("**Quem está contando agora**")
    qc = E.quem_contou(contados, cid)
    if not qc:
        st.caption("Ninguém contou nada ainda.")
    for (q, onde), n in sorted(qc.items(), key=lambda kv: -kv[1]):
        st.markdown(f"{_esc(q)} · {_esc(onde or 'sem lugar')} · **{n} peças**")


def _tela_fechar(prods, movs, contados, cid, quem):
    import pandas as pd
    fech = E.fechamento(prods, movs, contados, cid)
    c1, c2, c3 = st.columns(3)
    c1.markdown(f'<div style="padding:10px;border-radius:10px;background:#2c2c2c"><div style="font-size:11px;'
                f'color:#9AA3AE">BATEU</div><b style="color:#4CC38A;font-size:20px">{fech["bateu"]}</b></div>',
                unsafe_allow_html=True)
    c2.markdown(f'<div style="padding:10px;border-radius:10px;background:#2c2c2c"><div style="font-size:11px;'
                f'color:#9AA3AE">DIFERENÇA</div><b style="color:#E5534B;font-size:20px">{fech["diferenca"]}</b>'
                f'</div>', unsafe_allow_html=True)
    c3.markdown(f'<div style="padding:10px;border-radius:10px;background:#2c2c2c"><div style="font-size:11px;'
                f'color:#9AA3AE">VALOR</div><b style="color:{"#E5534B" if fech["valor"] < 0 else "#4CC38A"};'
                f'font-size:20px">{_rs(fech["valor"])}</b></div>', unsafe_allow_html=True)
    if fech["linhas"]:
        st.dataframe(pd.DataFrame([{"Produto": E.nome_completo(l["produto"]), "Sistema": l["sistema"],
                                    "Contado": l["contado"],
                                    "Diferença": ("ok" if not l["dif"] else f'{l["dif"]:+d}')}
                                   for l in fech["linhas"]]), hide_index=True, use_container_width=True)
    if fech["nao_contados"]:
        st.warning(f'{len(fech["nao_contados"])} produto(s) com estoque no Studio que ninguém contou: '
                   f'ficam como estão, nunca viram zero sozinhos.')
        with st.expander("Ver os não contados"):
            st.markdown("  \n".join(f'{_esc(E.nome_completo(n["produto"]))} · Studio: {n["sistema"]}'
                                     for n in fech["nao_contados"]))
    st.button("AJUSTAR O ESTOQUE PELA CONTAGEM E FECHAR", type="primary", key="est_ct_fechar",
              on_click=_ajustar, args=(cid, quem), use_container_width=True)
    st.caption("O ajuste fica no histórico de cada produto como «contagem», com quem fechou.")


# ── a página ─────────────────────────────────────────────────────────────────

def pagina(usuario_logado=None):
    quem = str(usuario_logado or "").strip()
    st.session_state["est_quem"] = quem      # os callbacks do bipe gravam o nome
    st.markdown("### 📦 Estoque")
    if st.session_state.get("est_modo_pendente"):
        st.session_state["est_modo"] = st.session_state.pop("est_modo_pendente")
    # O valor inicial vem do session_state, e NÃO de `default=` (13/11): o
    # `_ir_cadastrar` escreve `est_modo`, e widget com default E valor escrito
    # pelo código põe um aviso amarelo na tela uma passada só — os campos do
    # cadastro mudam de posição, o Streamlit os recria e o clique em
    # «CADASTRAR E DAR ENTRADA» vindo da Contagem se perdia.
    st.session_state.setdefault("est_modo", MODOS[0])
    modo = st.segmented_control("Modo", MODOS, key="est_modo",
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
    if modo == MODOS[4]:  # «Estoque cadastrado», antes «Painel» (dono, 17/11)
        _painel(quem)
        return
    if modo == "📱 Contagem":
        _contagem(quem)
        return
    if modo == MODOS[6]:
        _painel_resumo(quem)
        return
    _entrada(quem)


def _entrada(quem):
    ss = st.session_state
    aviso = ss.pop("est_aviso", None)
    if aviso:
        (st.error if aviso[1] else st.success)(aviso[0])
    _mostrar_desconhecido()
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
    ficha_aberta = False

    if ss.get("est_cadastrar"):
        _cadastro(quem)
    elif cod:
        variacoes = E.do_codigo(prods, cod)
        gerado = E.codigo_gerado(codigos, cod)
        if variacoes:
            _ficha(variacoes, saldo, codigos, por_id, quem, movs)
            ficha_aberta = True
        elif gerado:
            st.warning(f"**{gerado.get('nome')}** é um código de VENDA ({receita_txt(gerado, por_id)}). "
                       f"Na entrada, bipe o código do produto.")
            st.button("Voltar", key="est_voltar_g", on_click=_voltar)
        else:
            _pergunta(cod)
    else:
        st.caption("Bipe um código. Já cadastrado: abre a ficha. Não cadastrado: o Studio "
                   "pergunta se é produto novo.")
        _busca_sem_bipe(prods)
    if not ficha_aberta:      # com a ficha aberta, a lista está ao lado dela
        _ultimas(movs, por_id, quem)


def _abrir_ficha(ean):
    _limpar_ficha()
    st.session_state["est_lido"] = ean


def buscar_produtos(prods, texto, limite=8):
    """Um produto por código de barras, achado pelo nome, variação, código do
    fornecedor, código de barras ou SKU (varejo e atacado), como TEXTO (o "+" e o "(" da equipe são letra). Pura."""
    # Sem acento (dono, 17/11): a equipe digita «relogio» para «Relógio».
    b = " ".join(E._sem_acento(str(texto or "")).lower().split())
    if len(b) < 2:
        return []
    vistos, fora = set(), []
    for p in E.ativos(prods):
        alvo = " ".join(E._sem_acento(" ".join(str(x or "") for x in (
            p.get("nome"), p.get("variacao"), p.get("codigo_fornecedor"), p.get("ean"),
            p.get("sku"), p.get("sku_atacado"), p.get("fornecedor")))).lower().split())
        ean = E.limpar_codigo(p.get("ean"))
        if b in alvo and ean not in vistos:
            vistos.add(ean)
            fora.append(p)
    return fora[:limite]


def _busca_sem_bipe(prods):
    """Produto que não dá para bipar — o que já está no Full (dono, 11/11)."""
    with st.expander("🔎 Produto que não dá para bipar (já está no Full) — buscar pelo nome"):
        txt = st.text_input("Nome ou código", key="est_busca_ent", placeholder="Embaralhador, MBLN-06…")
        achados = buscar_produtos(prods, txt)
        if txt and not achados:
            st.caption("Nenhum produto com esse nome. Cadastre primeiro: bipe ou digite o código "
                       "de barras na barra acima.")
        for p in achados:
            st.button(f'{p.get("nome")} · {p.get("codigo_fornecedor") or p.get("ean")}',
                      key=f"est_be_{p['id']}", on_click=_abrir_ficha, args=(p.get("ean"),),
                      use_container_width=True)
        st.caption("Abre a ficha: em «Onde está entrando», escolha o Full e digite a quantidade.")


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
    _tb = {"MS-3500": {"custo": 35.0, "qtd": 1, "produto": "Caneca (P) + tampa"},
           "MS-9000": {"custo": 90.0, "qtd": 3, "produto": "Pacote"}}
    ok("situacao_sku: achou — diz o produto e devolve o custo como a equipe digita",
       situacao_sku("  ms-3500 ", _tb) == ("ok", "✓ MS-3500 achado na planilha (Caneca (P) + tampa) · custo R$ 35,00", "35,00"))
    ok("situacao_sku: não achou — avisa (não é erro: vale o digitado, 17/11) e não inventa custo",
       situacao_sku("MS-1", _tb)[0] == "aviso" and "ainda não está" in situacao_sku("MS-1", _tb)[1]
       and situacao_sku("MS-1", _tb)[2] is None)
    ok("situacao_sku: pacote é recusado sem custo", situacao_sku("ms-9000", _tb)[0] == "erro"
       and "pacote" in situacao_sku("ms-9000", _tb)[1] and situacao_sku("ms-9000", _tb)[2] is None)
    ok("situacao_sku: planilha ilegível manda digitar, vazio fica calado",
       situacao_sku("MS-3500", None, "403")[0] == "aviso" and situacao_sku("  ", _tb) == ("", "", None))
    _en = linhas_da_entrada_nova(prods[0], 2, 3, "leo", "x")
    ok("linhas_da_entrada_nova: varejo e atacado no mesmo lote, cada um com a sua origem",
       sorted((l["origem"], l["qtd"]) for l in _en) == [(E.ATACADO, "3"), (E.VAREJO, "2")]
       and len({l["lote"] for l in _en}) == 1)
    ok("linhas_da_entrada_nova: quantidade zero não grava linha",
       [l["origem"] for l in linhas_da_entrada_nova(prods[0], 0, 4, "l", "x")] == [E.ATACADO]
       and linhas_da_entrada_nova(prods[0], 0, 0, "l", "x") == [])
    _g_tab = _tabela_sku
    _tabela_sku = lambda: ({"MS-2768": {"custo": 27.68, "qtd": 1, "produto": "JOGO DE DARDO"}}, "")
    _so_at = _custos_do_formulario("", "", "MS-2768", "")
    ok("_custos_do_formulario: só atacado salva, e o custo do produto é o do atacado (dono, 12/11)",
       _so_at[1] == "" and _so_at[0]["custo"] == "27.68" and _so_at[0]["sku"] == ""
       and _so_at[0]["sku_atacado"] == "MS-2768")
    ok("_custos_do_formulario: sem nenhum dos dois, diz o que falta",
       "varejo ou de atacado" in _custos_do_formulario("", "", "", "")[1])
    _tabela_sku = _g_tab
    ok("quadro_da_foto: altura fixa (não desce além do último campo), com a foto ou o aviso",
       "height:272px" in quadro_da_foto("") and "aspect-ratio" not in quadro_da_foto("")
       and "sem foto" in quadro_da_foto("")
       and "data:image/jpeg;base64,QUJD" in quadro_da_foto("QUJD"))
    _sv = E.linhas_de_saida([(prods[1], 2)], E.VENDA, "leo", "12/11/2026 15:47", movs=ent)
    _lt = E.ultimos_lotes(ent + _sv, E.VENDA)[0]
    _r = resumo_do_lote(_lt, por_id, E.saldos(ent + _sv))
    ok("resumo_do_lote: nome, código, quanto saiu, quanto fica e o custo por peça (cadeia real)",
       _r["nome"] == E.nome_completo(prods[1]) and _r["ean"] == "7891234567895" and _r["q"] == 2
       and _r["fica"] == 0 and abs(_r["custo"] - 18.4) < 0.01 and _r["hora"] == "15:47")
    _hb = bipe_atual_html(_r)
    ok("bipe_atual_html: quadro roxo com nome escapado, custo considerado e sem linha em branco",
       "#a78bfa" in _hb and "&lt;resina&gt;" in _hb and "custo considerado: R$ 18,40" in _hb
       and "\n" not in _hb)
    ok("linha_bipada_html: excluído sai riscado", "<s>" in linha_bipada_html(dict(_r, desfeito=True)))
    ok("procurar: código de barras de 8+ dígitos não é busca (oferece cadastro)",
       not procurar("7891234567895") and not procurar(" 7891 2345 ") and not procurar(""))
    ok("procurar: nome, SKU, código do fornecedor e número curto são busca",
       procurar("caneca (p) + tampa") and procurar("MS-3500") and procurar("MBLN-06") and procurar("4567"))
    _cods = [E.linha_de_codigo("2000000000015", "quantidade", "Kit", prods[0]["ean"], {prods[0]["id"]: 2}, "l", "x")]
    ok("eh_codigo_cadastrado: produto e código gerado contam, o resto não",
       eh_codigo_cadastrado(prods, _cods, "7891234567895") and eh_codigo_cadastrado(prods, _cods, "2000000000015")
       and not eh_codigo_cadastrado(prods, _cods, "MS-3500"))
    _ps = [dict(prods[0], sku="MS-3500", sku_atacado="MS-2800")]
    ok("buscar_produtos: acha pelo SKU de varejo e pelo de atacado, sem diferença de caixa",
       buscar_produtos(_ps, "ms-3500") == _ps and buscar_produtos(_ps, "MS-2800") == _ps)
    _int = E.linhas_de_produto(E.novo_codigo_interno([]), "", "ESTÁTUA LIVRO + base", 18.9,
                               [("", "")], "l", "x", sku="MS-1890")
    _int2 = E.linhas_de_produto("2000000000022", "", "Abajur (P)", 5, [("A", ""), ("B", "")], "l", "x")
    _todos_p = prods + _int + _int2
    _ls = lista_sem_ean(_todos_p, E.saldos(ent))
    ok("lista_sem_ean: só os de código do Studio, em ordem alfabética, um por código",
       [d["nome"] for d in _ls] == ["Abajur (P)", "ESTÁTUA LIVRO + base"] and _ls[0]["modelos"] == 2)
    ok("lista_sem_ean: a palavra filtra como TEXTO (+, parênteses, acento) e pelo SKU",
       [d["nome"] for d in lista_sem_ean(_todos_p, {}, "livro + base")] == ["ESTÁTUA LIVRO + base"]
       and [d["nome"] for d in lista_sem_ean(_todos_p, {}, "ms-1890")] == ["ESTÁTUA LIVRO + base"]
       and [d["nome"] for d in lista_sem_ean(_todos_p, {}, "(p)")] == ["Abajur (P)"])
    ok("lista_sem_ean: com «todos», o de EAN de fábrica entra",
       any(d["ean"] == "7891234567895" for d in lista_sem_ean(_todos_p, {}, "", True)))
    _hl = linha_sem_ean_html(_ls[1], "livro")
    ok("linha_sem_ean_html: código desenhado, palavra destacada, sem linha em branco",
       "<svg" in _hl and "<mark" in _hl and "\n" not in _hl and "R$ 18,90" in _hl)
    ok("rotulo_manual: quantidade, nome, a marca de manual e a observação limpa",
       rotulo_manual(prods[1], 3, "  ML  123 ") == "3× Bailarina <resina> + Base · Sentada · saída manual · ML 123"
       and rotulo_manual(prods[1], 1).endswith("saída manual"))
    cab = cabecalho_html(prods, E.saldos(ent), "7891234567895")
    ok("cabecalho_html: nome escapado, total do estoque, custo em reais",
       "&lt;resina&gt;" in cab and "em estoque: 8" in cab and "R$ 18,40" in cab
       and "2 variações" in cab)
    lt = E.ultimos_lotes(ent, E.ENTRADA)[0]
    # CADASTRO COM VARIAÇÕES (dono, 13/11): várias de uma vez, num lote só.
    _vo, _ve = variacoes_do_cadastro([("Braço  para cima ", "2", 1), ("", 0, 0), ("Sentada (P/M) + base", 3, 0)], True)
    ok("variacoes_do_cadastro: limpa o nome, ignora a linha vazia, mantém a ordem",
       _ve is None and _vo == [("Braço para cima", 2, 1), ("Sentada (P/M) + base", 3, 0)])
    ok("variacoes_do_cadastro: quantidade sem nome, nome repetido e nenhuma variação são recusados",
       variacoes_do_cadastro([("", 1, 0)], True)[0] is None
       and "mesmo nome" in variacoes_do_cadastro([("Azul", 1, 0), ("azul", 0, 1)], True)[1]
       and variacoes_do_cadastro([("", 0, 0)], True)[0] is None)
    ok("variacoes_do_cadastro: sem variação, uma linha sem nome com as quantidades",
       variacoes_do_cadastro([("", 4, 0)], False) == ([("", 4, 0)], None))
    _nv = E.linhas_de_produto("7891234567895", "PR-2", "Porta 2 Relógio + Jóias", 10,
                              [(v, "F1" if i == 0 else "") for i, (v, _a, _b) in enumerate(_vo)], "myrella", "x")
    _ev = entrada_das_variacoes(_nv, _vo, "myrella", "2026-11-13 16:00")
    _lt_ev = E.ultimos_lotes(_ev, E.ENTRADA)
    ok("entrada_das_variacoes: as duas variações num lote só, com as quantidades de cada origem",
       len(_lt_ev) == 1 and sorted((m["produto_id"], m["qtd"], m.get("origem")) for m in _ev)
       == sorted([(_nv[0]["id"], "2", E.VAREJO), (_nv[0]["id"], "1", E.ATACADO), (_nv[1]["id"], "3", E.VAREJO)]))
    _fe = ficha_entrada_html(_nv, E.saldos(_ev), "7891234567895")
    ok("ficha_entrada_html: quadro verde, nome escapado, estoque somado das variações, sem linha em branco",
       "#4cc38a" in _fe and "JÁ CADASTRADO" in _fe and "Relógio + Jóias" in _fe
       and "físico <b style=\"color:#E8EAED\">6</b> · 2 variações" in _fe and "\n" not in _fe
       and "PR-2" in _fe)
    ok("renomeacoes: o nome como a tela mostra NÃO renomeia; texto mudado renomeia; vazio não apaga",
       renomeacoes(prods, {prods[0]["id"]: "Braço para Cima", prods[1]["id"]: None}) == {}
       and renomeacoes(prods, {prods[0]["id"]: "Braço erguido"}) == {prods[0]["id"]: {"variacao": "Braço erguido"}}
       and renomeacoes(prods, {prods[0]["id"]: "  "}) == {})
    # ✎ EDITAR A ENTRADA (dono, 13/11): «eram 2 e entraram 3». Lote real,
    # com varejo e atacado e um Full, como a tela grava.
    _lc = (E.linhas_de_entrada([(prods[0], 1), (prods[1], 2)], "MartinSousa", "13/11/2026 16:19")
           + E.linhas_de_entrada([(prods[1], 4)], "MartinSousa", "13/11/2026 16:19",
                                 local="full_shp2", origem=E.ATACADO))
    for _l in _lc:
        _l["lote"] = _lc[0]["lote"]
    _cor, _novo = linhas_da_correcao(_lc[0]["lote"], _lc, {1: 1}, "leo", "13/11/2026 16:30")
    _sc = E.saldos(_lc + _cor)
    ok("linhas_da_correcao: só a linha corrigida muda; Full, origem e custo das outras ficam",
       _sc.get((prods[0]["id"], E.FISICO)) == 1 and _sc.get((prods[1]["id"], E.FISICO)) == 1
       and _sc.get((prods[1]["id"], "full_shp2")) == 4 and _novo
       and [m.get("origem") for m in _cor if m["lote"] == _novo] == [E.VAREJO, E.VAREJO, E.ATACADO]
       and all(m["custo_unit"] == o["custo_unit"] for m, o in zip([m for m in _cor if m["lote"] == _novo], _lc)))
    ok("linhas_da_correcao: o lote antigo fica desfeito e o novo aparece nas últimas entradas",
       _lc[0]["lote"] in E.lotes_desfeitos(_lc + _cor)
       and E.ultimos_lotes(_lc + _cor, E.ENTRADA)[0]["lote"] == _novo)
    _cz, _nz = linhas_da_correcao(_lc[0]["lote"], _lc, {0: 0, 1: 0, 2: 0}, "leo", "x")
    ok("linhas_da_correcao: tudo zero vira exclusão; corrigir duas vezes o mesmo lote não dobra",
       _nz is None and all(v == 0 for v in E.saldos(_lc + _cz).values())
       and linhas_da_correcao(_lc[0]["lote"], _lc + _cor, {1: 5}, "leo", "x") == ([], None))
    _re = resumo_da_entrada(lt, por_id)
    ok("resumo_da_entrada: cada variação com a quantidade, o total, a hora e quem (lote real)",
       _re["nome"] == "Bailarina <resina> + Base · Braço para Cima +6 · "
                      "Bailarina <resina> + Base · Sentada +2"
       and _re["q"] == 8 and _re["hora"] == "14:03" and _re["quem"] == "leo" and _re["ean"] == "")
    _le = linha_entrada_html(_re)
    ok("linha_entrada_html: nome escapado, +N em verde, quem na linha de baixo, sem linha em branco",
       "&lt;resina&gt;" in _le and "+8</div>" in _le and "#7fd18b" in _le and "leo" in _le
       and "\n" not in _le)
    _lt1 = E.ultimos_lotes(E.linhas_de_entrada([(prods[0], 3)], "myrella", "2026-11-13 15:54"),
                           E.ENTRADA)[0]
    _r1 = resumo_da_entrada(_lt1, por_id)
    ok("resumo_da_entrada: um modelo só mostra o nome, o EAN e o +N do lote",
       _r1["q"] == 3 and _r1["ean"] == "7891234567895" and "+" not in _r1["nome"].split("Base")[-1])
    ok("linha_entrada_html: entrada excluída fica riscada e marcada",
       "<s>" in linha_entrada_html({**_r1, "desfeito": True})
       and "excluída" in linha_entrada_html({**_r1, "desfeito": True}))
    k = E.linha_de_codigo("2000000000015", "quantidade", "Kit com 2", "7891234567895",
                          {prods[0]["id"]: 1, prods[1]["id"]: 1}, "leo", "x")
    ok("receita_txt: as peças de um código gerado",
       receita_txt(k, por_id).startswith("1× Bailarina <resina> + Base · Braço para Cima"))
    ok("foto_html: sem foto vira quadrado, com foto vira miniatura do Drive",
       "sem foto" in foto_html("") and "thumbnail?id=abc" in foto_html("abc"))
    ok("o foco não rouba o campo de quem está digitando",
       "digitando" in _FOCO and "est_bipe" in _FOCO and "location" not in _FOCO)
    import inspect as _insp
    ok("câmera em TODA tela que bipa: a barra tem a câmera, e as cinco telas usam a barra",
       "_CAMERA" in _insp.getsource(_barra)
       and all("_barra(" in _insp.getsource(f) for f in (_entrada, _saida, _baixas, _kits, _tela_contar)))
    ok("modos: as seis partes aprovadas e prontas", len(MODOS) == 7 and EM_CONSTRUCAO == {})
    # O PAINEL À PARTE (dono, 17/11): quadros, tempo parado e lista do Renan
    # saem do Estoque cadastrado e vão para a última aba.
    _src_pr = _insp.getsource(_painel_resumo)
    _src_pc = _insp.getsource(_painel)
    ok("Painel: aba última; quadros, tempo parado e lista do Renan nela e NÃO no Estoque cadastrado",
       MODOS[-1] == "📈 Painel" and "_painel_resumo(quem)" in _insp.getsource(pagina)
       and all(t in _src_pr for t in ("topo_painel_html(pn)", "faixas_html(pn)", "E.lista_de_compra("))
       and not any(t in _src_pc for t in ("topo_painel_html(", "faixas_html(", "E.lista_de_compra(")))
    ok("câmera: entrega o código à MESMA barra do leitor, e não repete a etiqueta parada",
       ".st-key-est_bipe input" in _CAMERA and "agora - visto < 1200" in _CAMERA and "location" not in _CAMERA
       and "html5-qrcode@2.3.8" in _CAMERA)
    ok("destinos da saída: venda e envio ao Full",
       set(DESTINOS.values()) == {E.VENDA, E.ENVIO_FULL})
    _kit = E.linhas_de_saida([(prods[0], 1), (prods[1], 1)], E.VENDA, "leo", "x", obs="Kit com 2")
    ok("rotulo_do_lote: kit pelo nome do kit; produto pelo nome dele",
       rotulo_do_lote(_kit, por_id) == "Kit com 2"
       and rotulo_do_lote(_kit[:1], por_id) == "Bailarina <resina> + Base · Braço para Cima")
    _bx = E.linhas_de_baixa(prods[1], 1, E.DEVOLUCAO, "my", "11/11/2026 15:00", volta=False,
                            obs="arranhado")
    ok("linha_baixa_txt: devolução ruim é descarte, com valor e obs",
       linha_baixa_txt(_bx, por_id) == "11/11 · Bailarina <resina> + Base · Sentada · Devolução → "
                                       "descarte · arranhado · −1 · R$ 18,40 · my")
    _bx2 = E.linhas_de_baixa(prods[0], 2, E.DEVOLUCAO, "my", "11/11/2026 15:00", volta=True)
    _bx3 = E.linhas_de_baixa(prods[0], 1, E.QUEBRA, "leo", "11/11/2026 15:00", local="full_ml1")
    ok("linha_baixa_txt: devolução boa soma sem valor; quebra do Full diz Full",
       " · Devolução → voltou ao estoque · +2 · — · my" in linha_baixa_txt(_bx2, por_id)
       and "Quebra (Full ML1) · −1 · R$ 18,40" in linha_baixa_txt(_bx3, por_id))
    _sx = E.saldos(ent + E.linhas_de_entrada([(prods[0], 3)], "l", "x", local="full_shopee1"))
    ok("estoque_txt: físico e cada Full com peça, pelo nome da conta",
       estoque_txt(_sx, prods[0]["id"]) == "em estoque: físico 6 · Full Shopee 1 3"
       and estoque_txt(_sx, "nada") == "em estoque: físico 0")
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
    ok("kit_card_html: o código de barras vai no cartão, à direita do nome (dono, 23/11)",
       "<svg" in _kc and _kc.index("Kit &lt;A&gt;") < _kc.index("<svg")
       and "2000000000022" in _kc and "\n" not in _kc)
    _ks = [E.linha_de_codigo(f"20000000000{i:02d}", "kit", f"K{i}", "", {prods[0]["id"]: 1}, "leo", "x")
           for i in range(1, 7)]
    _nm = lambda ls: [k["nome"] for k in ls]
    ok("kits_a_mostrar: os 3 últimos criados, o mais novo em cima; todos; o aberto antigo fica",
       _nm(kits_a_mostrar(_ks)) == ["K6", "K5", "K4"]
       and len(kits_a_mostrar(_ks, todos=True)) == 6
       and _nm(kits_a_mostrar(_ks, abertos=("2000000000001", None))) == ["K6", "K5", "K4", "K1"]
       and _nm(kits_a_mostrar(_ks[:2])) == ["K2", "K1"])
    import datetime as _dtt
    _pnl = E.painel(prods, ent, _dtt.date(2026, 11, 11))
    _tp = topo_painel_html(_pnl)
    ok("topo_painel_html: os quatro quadros, valor a custo",
       _tp.count("border-radius:12px") == 4 and "R$ 147" in _tp and "ESTOQUE FULL" in _tp)
    ok("faixas_html: três faixas", faixas_html(_pnl).count("height:8px;border-radius:4px;background:#222") == 3)
    _real = E.linhas_de_produto("9", "PRJ-2", "Porta 2 Relógio + Jóias", 31.5, [("", "")], "l", "x")
    _linhas = [{"produto": p, "valor": 1.0} for p in prods + _real]
    ok("tabela_produtos: busca o nome REAL com + como texto, e por código bipado",
       [l["produto"]["nome"] for l in tabela_produtos(_linhas, "relógio + jóias")] == ["Porta 2 Relógio + Jóias"]
       and len(tabela_produtos(_linhas, "7891 234567895")) == 1 and len(tabela_produtos(_linhas, "")) == 2
       and tabela_produtos(_linhas, "(P/M) ?") == [])
    _bp = (E.linhas_de_produto("5901234123457", "S2017", "Embaralhador automático", 42, [("", "")], "l", "x")
           + E.linhas_de_produto("9", "PRJ-2", "Porta 2 Relógio + Jóias", 31.5, [("", "")], "l", "x"))
    ok("buscar_produtos: nome real com + como texto, um por código, e as 3 posições viram 1",
       [p["nome"] for p in buscar_produtos(prods + _bp, "relógio + jóias")] == ["Porta 2 Relógio + Jóias"]
       and len(buscar_produtos(prods + _bp, "bailarina")) == 1 and buscar_produtos(prods, "b") == []
       and [p["nome"] for p in buscar_produtos(_bp, "s2017")] == ["Embaralhador automático"])
    _pnf = {"linhas": [{"por_full": {"full_ml1": 3}}, {"por_full": {"full_ml1": 1, "full_shopee1": 2}}]}
    ok("_por_conta_txt: soma cada Full entre os produtos", _por_conta_txt(_pnf) == " · ML1 4 · Shopee 1 2")
    ok("janela_html: nome escapado e o aviso de vários modelos",
       "&lt;resina&gt;" in janela_html(prods, {}) and "MAIS DE UM MODELO" in janela_html(prods, {}))
    # SKU (dono, 12/11). A tabela vem de `E.tabela_de_sku`, a mesma função
    # que lê a planilha — e não de um dicionário escrito à mão (passo 6).
    _tb = E.tabela_de_sku(["DATA", "SKU", "PRODUTO", "QUANTIDADE", "CUSTO"],
                          [{"SKU": "MS-3500", "PRODUTO": "Porta 2 Relógio + Jóias", "QUANTIDADE": 1, "CUSTO": 35.0},
                           {"SKU": "MS-9000", "PRODUTO": "Kit (3)", "QUANTIDADE": 3, "CUSTO": 90.0}])
    _r1 = resolver_custo(" ms-3500", "", _tb)
    ok("resolver_custo: SKU achado traz o custo da planilha", _r1[0] == 35.0 and not _r1[1] and "35,00" in _r1[2])
    _r2 = resolver_custo("MS-3500", "30", _tb)
    ok("resolver_custo: o da planilha vence o digitado, e diz", _r2[0] == 35.0 and "trocado" in _r2[2])
    _r3 = resolver_custo("MS-9000", "30", _tb)
    ok("resolver_custo: SKU de pacote é recusado", _r3[0] is None and "pacote de 3" in _r3[1])
    _r4 = resolver_custo("MS-0001", "", _tb)
    ok("resolver_custo: SKU desconhecido sem custo digitado pede o custo", _r4[0] is None and "não está na planilha" in _r4[1])
    _r5 = resolver_custo("", "12,90", _tb)
    ok("resolver_custo: sem SKU, vale o digitado e avisa da lista", _r5[0] == 12.9 and "Produtos sem SKU" in _r5[2])
    _r6 = resolver_custo("MS-3500", "", None, "sem permissão")
    ok("resolver_custo: planilha ilegível diz por quê", _r6[0] is None and "sem permissão" in _r6[1])
    ok("resolver_custo: custo que não é número é recusado", resolver_custo("", "abc", _tb)[0] is None)
    _sh = sem_sku_html([({"nome": "Porta <2> + Jóias", "ean": "9"}, "sem SKU")])
    ok("sem_sku_html: conta, escapa o nome e diz onde pôr o SKU",
       "PRODUTOS SEM SKU · 1" in _sh and "&lt;2&gt;" in _sh and "Editar produto" in _sh and sem_sku_html([]) == "")
    _cs = cabecalho_html([{**prods[0], "sku": "ms-3500", "sku_atacado": "MS-2800", "custo_atacado": "28"}], {}, "1")
    ok("cabecalho_html: mostra o SKU, o do atacado e o custo dele; sem SKU avisa",
       "SKU MS-3500" in _cs and "atacado MS-2800 R$ 28,00" in _cs and "sem SKU" in cabecalho_html(prods, {}, "1"))
    ok("tabela_produtos: busca pelo SKU também",
       len(tabela_produtos([{"produto": {**prods[0], "sku": "MS-3500"}, "valor": 1}], "ms-3500")) == 1)

    # SÓ ATACADO (dono, 16/11): «cadastrou valor de varejo sozinho, copiou o
    # de atacado». Cadeia real: o cadastro grava pelo _custos_do_formulario,
    # e o quadro e o «sem SKU» leem o produto que ele gravou.
    _orig_tab = _tabela_sku
    try:
        _tabela_sku = lambda: ({}, "")
        _mud, _err, _av = _custos_do_formulario("", "", "MS-3949", "39,49")
    finally:
        _tabela_sku = _orig_tab
    _pat = {**prods[0], **(_mud or {})}
    _fe_at = ficha_entrada_html([_pat], {}, "7908045146994")
    ok("só atacado: o cadastro grava o custo base = atacado e sem SKU de varejo (a regra de 12/11 fica)",
       not _err and _mud["sku"] == "" and _mud["custo"] == "39.49" and _mud["custo_atacado"] == "39.49")
    ok("só atacado: o quadro diz «custo atacado» e «só atacado», nunca «custo varejo»/«sem SKU»",
       "custo atacado" in _fe_at and "só atacado" in _fe_at and "custo varejo" not in _fe_at
       and "sem SKU" not in _fe_at)
    ok("só atacado: fica fora da lista «Produtos sem SKU»; sem SKU nenhum continua entrando",
       E.sem_sku([_pat], None) == [] and len(E.sem_sku([{**_pat, "sku_atacado": ""}], None)) == 1)
    ok("só atacado: com custo de varejo digitado diferente, volta a ser «custo varejo»",
       "custo varejo" in ficha_entrada_html([{**_pat, "custo": "45"}], {}, "1"))

    # ✎ EDITAR DA ENTRADA ABRE O CADASTRO INTEIRO (dono, 17/11). Por AST: a
    # edição da entrada chama _editar_produto aberto e com sufixo; e as
    # chaves do editor levam o sufixo (ficha + entrada na mesma tela).
    _src_ee = _insp.getsource(_edicao_da_entrada)
    _src_ep = _insp.getsource(_editar_produto)
    ok("editar entrada: abre o cadastro inteiro (_editar_produto), já aberto e recolhe ao salvar",
       "_editar_produto(vs, quem, sufixo=" in _src_ee and "aberto=True" in _src_ee
       and "fechar=True" in _src_ee and "args=(variacoes, quem, sufixo, fechar, entrada)" in _src_ep
       and "if fechar:\n            _fechar_ed_entrada()" in _insp.getsource(_salvar_produto))
    # Cancelar: o botão existe e FECHA de verdade (o callback, rodado).
    _ss_cx = {"est_ent_ed": "L1"}
    _orig_ss = st.session_state
    try:
        st.session_state = _ss_cx
        _fechar_ed_entrada()
    finally:
        st.session_state = _orig_ss
    ok("editar entrada: «Cancelar» chama _fechar_ed_entrada, e ela fecha",
       'on_click=_fechar_ed_entrada' in _src_ee and _ss_cx["est_ent_ed"] is None
       and "if fechar:\n        _fechar_ed_entrada()" in _insp.getsource(_cancelar_edicao))
    # SKU RECÉM-CADASTRADO NA PLANILHA (dono, 18/11). Pela cadeia: a cópia
    # guardada não tem o SKU, a planilha de agora tem — o callback relê UMA
    # vez e preenche o custo; o mesmo SKU de novo em 30 s não baixa de novo.
    ok("precisa_reler_sku: só quando falta, uma vez a cada 30 s, nome real normalizado",
       precisa_reler_sku(" ms-1430 ", {"MS-2800": {}}, {}, 1000.0)
       and not precisa_reler_sku("MS-1430", {"MS-1430": {}}, {}, 1000.0)
       and not precisa_reler_sku("MS-1430", {}, {"MS-1430": 990.0}, 1000.0)
       and precisa_reler_sku("MS-1430", {}, {"MS-1430": 960.0}, 1000.0)
       and not precisa_reler_sku("MS-1430", None, {}, 1000.0) and not precisa_reler_sku("  ", {}, {}, 1.0))
    _velha_sku = E.tabela_de_sku(["SKU", "PRODUTO", "QUANTIDADE", "CUSTO"],
                                 [{"SKU": "MS-2800", "PRODUTO": "X", "QUANTIDADE": 1, "CUSTO": 10}])
    _nova_sku = E.tabela_de_sku(["SKU", "PRODUTO", "QUANTIDADE", "CUSTO"],
                                [{"SKU": "MS-2800", "PRODUTO": "X", "QUANTIDADE": 1, "CUSTO": 10},
                                 {"SKU": "MS-1430", "PRODUTO": "BANCO INFANTIL UNITÁRIO", "QUANTIDADE": 1,
                                  "CUSTO": 14.3}])
    _releu = []
    _orig_sk = (E.tabela_de_sku_da_planilha, E.tabela_de_sku_agora, st.session_state)
    try:
        E.tabela_de_sku_da_planilha = lambda: (_velha_sku, "")
        E.tabela_de_sku_agora = lambda: _releu.append(1) or (_nova_sku, "")
        st.session_state = {"k_sku": "ms-1430", "k_custo": ""}
        _ao_mudar_sku("k_sku", "k_custo")
        _custo_1 = st.session_state["k_custo"]
        st.session_state["k_custo"] = ""
        E.tabela_de_sku_agora = lambda: _releu.append(1) or (_velha_sku, "")
        _ao_mudar_sku("k_sku", "k_custo")
    finally:
        E.tabela_de_sku_da_planilha, E.tabela_de_sku_agora, st.session_state = _orig_sk
    ok("SKU que não está na cópia guardada: relê a planilha uma vez e preenche o custo (14,30)",
       _custo_1 == "14,30" and len(_releu) == 1)
    # QUANTIDADE DENTRO DO QUADRO (dono, 18/11). Pela CADEIA: a entrada de
    # verdade (linhas_de_entrada), o quadro passa a entrada, e o «Salvar»
    # do produto grava a correção — mesmo sem nada do produto mudar.
    _pq = E.linhas_de_produto("7908045165056", "PR-2", "Porta 2 Relógio + Jóias", 10,
                              [("Rosa", ""), ("Azul", "")], "l", "x")
    _eq = E.linhas_de_entrada([(_pq[0], 6), (_pq[1], 18)], "l", "x")
    _lote_q = _eq[0]["lote"]
    _lin_q = [(i, m, _pq[i]) for i, m in enumerate(_eq)]
    ok("quantidades_mudadas: só a que mudou; campo ausente NÃO vira zero",
       quantidades_mudadas(_lin_q, {0: 6, 1: 24}) == {1: 24}
       and quantidades_mudadas(_lin_q, {1: None}) == {} and quantidades_mudadas(_lin_q, {0: 0}) == {0: 0})
    _db_q = {"m": list(_eq)}
    _av_q, _orig_q = [], (E.carregar, E.gravar_movimentos, _avisar, st.session_state)
    try:
        E.carregar = lambda: (list(_pq), list(_db_q["m"]), [])
        E.gravar_movimentos = lambda l: _db_q["m"].extend(l)
        globals()["_avisar"] = lambda msg, erro=False: _av_q.append((msg, erro))
        _pf_q = _pf_ed(_pq, f"_lt{_lote_q}")
        st.session_state = {**{_pf_q + k: v for k, v in _iniciais_ed(_pq[0]).items()},
                            _ch_qe(_lote_q, 1): 24, "est_ent_ed": _lote_q}
        _salvar_produto(_pq, "leo", f"_lt{_lote_q}", True, (_lote_q, _lin_q))
        _ss_q = st.session_state
    finally:
        E.carregar, E.gravar_movimentos = _orig_q[:2]
        globals()["_avisar"] = _orig_q[2]
        st.session_state = _orig_q[3]
    _sq = E.saldos(_db_q["m"])
    ok("editar entrada: o «Salvar» do quadro grava a quantidade (Rosa 6, Azul 18→24) e fecha",
       _sq.get((_pq[0]["id"], E.FISICO)) == 6 and _sq.get((_pq[1]["id"], E.FISICO)) == 24
       and _av_q and not _av_q[0][1] and "agora 30 peça(s)" in _av_q[0][0] and _ss_q.get("est_ent_ed") is None)
    ok("editar entrada: a quantidade mora DENTRO do quadro do produto (antes era um quadro em cima)",
       "        if entrada:\n            _quantidades_da_entrada(entrada)\n" in _src_ep
       and "entrada=(lt[\"lote\"], lin)" in _insp.getsource(_edicao_da_entrada)
       and "on_click=_salvar_correcao" in _insp.getsource(_edicao_da_entrada).split("if soltas:")[1])
    ok("editar produto: toda chave com o prefixo do produto E do sufixo — sem chave repetida com a ficha",
       "pf = _pf_ed(variacoes, sufixo)" in _src_ep and "{sufixo}_" in _insp.getsource(_pf_ed)
       and "st.form(" not in __import__("ast").unparse(__import__("ast").parse(_src_ep.lstrip()))
       and all("key=pf" in ln or "key=f'{pf}" in ln or "key=_ch_foto_ed(pf)" in ln or "key=f\"{pf}" in ln
               for ln in _src_ep.splitlines() if "key=" in ln))

    # ORDEM ALFABÉTICA do Estoque cadastrado (dono, 17/11), com nome da
    # planilha (acento, maiúscula) e valor invertido de propósito.
    _alf = [{"produto": {**prods[0], "id": f"A{v}", "ean": f"78900000{v:05d}", "nome": n, "variacao": ""},
             "valor": v}
            for n, v in (("Caixa para 12 Relógios", 900), ("álbum Pequeno", 10), ("Álbum Grande", 5),
                         ("Globo Azul 14cm", 50))]
    ok("estoque cadastrado: ordem alfabética, sem olhar acento, maiúscula ou valor",
       [l["produto"]["nome"] for l in tabela_produtos(_alf, "")]
       == ["Álbum Grande", "álbum Pequeno", "Caixa para 12 Relógios", "Globo Azul 14cm"])

    # SEM OS RISCADOS (dono, 17/11). Cadeia real: uma entrada corrigida pelo
    # ✎ editar (linhas_da_correcao) e outra excluída (linhas_que_desfazem).
    _mv_e = E.linhas_de_entrada([(prods[0], 2)], "my", "16/11/2026 10:00")
    _lt_a = str(_mv_e[0]["lote"])
    _corr, _novo = linhas_da_correcao(_lt_a, _mv_e, {0: 3}, "my", "16/11/2026 10:05")
    _mv_e = _mv_e + _corr
    _vis = entradas_visiveis(_mv_e, 5)
    ok("últimas entradas: a corrigida some, só a nova aparece (sem riscado)",
       [lt["lote"] for lt in _vis] == [str(_novo)] and not any(lt["desfeito"] for lt in _vis))
    _mv_x = _mv_e + E.linhas_que_desfazem(str(_novo), _mv_e, "my", "16/11/2026 10:06")
    ok("últimas entradas: a excluída também some", entradas_visiveis(_mv_x, 5) == [])

    # ✎ EDITAR NO ESTOQUE CADASTRADO (dono, 17/11): a linha escolhida abre o
    # MESMO _editar_produto, com sufixo próprio.
    ok("estoque cadastrado: a linha escolhida abre o ✎ Editar produto (com sufixo)",
       '_vs_pn = E.do_codigo(prods, p.get("ean")) or [p]' in _insp.getsource(_painel)
       and '_editar_produto(_vs_pn, quem, sufixo="_pn", saldo=E.saldos(movs))' in _insp.getsource(_painel))

    # BUSCAR POR NOME NA SAÍDA (dono, 17/11). Por AST: o seletor vem logo
    # depois da barra e antes do «Ver»; o botão chama o MESMO _bipe_na_saida.
    import ast as _ast_sn
    _ch_sn = sorted((n.lineno, _ast_sn.unparse(n.func)) for n in
                    _ast_sn.walk(_ast_sn.parse(_insp.getsource(_saida).lstrip()))
                    if isinstance(n, _ast_sn.Call))
    _ln = lambda f: [l for l, x in _ch_sn if x == f]
    ok("saída: «Buscar produto por» logo depois da barra e antes do «Ver»",
       _ln("_busca_por_nome_saida") and _ln("_barra")[0] < _ln("_busca_por_nome_saida")[0]
       < _ln("st.segmented_control")[-1])
    _src_sn = _insp.getsource(_busca_por_nome_saida)
    ok("saída por nome: o botão dá saída pelo MESMO caminho do bipe",
       "on_click=_bipe_na_saida" in _src_sn and "args=(ean,)" in _src_sn
       and MODOS_BUSCA_SAIDA == ("Código", "Nome"))
    # O pior nome real, digitado como a equipe digita: sem acento, minúscula.
    _pj = [{**prods[0], "id": "PJ", "ean": "7908045165056", "nome": "Porta 2 Relógio + Jóias"}]
    ok("buscar_produtos: «relogio + joias» acha «Porta 2 Relógio + Jóias» (símbolo e acento)",
       [p["id"] for p in buscar_produtos(_pj, "relogio + joias")] == ["PJ"]
       and [p["id"] for p in buscar_produtos(_pj, "RELÓGIO  +")] == ["PJ"]
       and buscar_produtos(_pj, "ouro") == [])

    # ✎ EDITAR À VISTA (dono, 16/11): a edição existia no fim da página e o
    # dono disse que não tinha. Por AST, no bloco: o «✎ Editar produto» é
    # chamado ANTES da lista de variações e do CONFIRMAR — não só «existe».
    import ast as _ast_ed
    _arv_ed = _ast_ed.parse(_insp.getsource(_ficha_principal).lstrip())
    _ch_ed = sorted((n.lineno, _ast_ed.unparse(n.func)) for n in _ast_ed.walk(_arv_ed)
                    if isinstance(n, _ast_ed.Call))
    _l_ed = [ln for ln, f in _ch_ed if f == "_editar_produto"]
    _l_tela = [ln for ln, f in _ch_ed if f in ("st.columns", "st.button", "c2.button")]
    ok("ficha: ✎ Editar produto aparece logo abaixo do quadro, antes das variações e do CONFIRMAR",
       len(_l_ed) == 1 and _l_tela and _l_ed[0] < min(_l_tela))

    # VARIAÇÃO NO ESTOQUE CADASTRADO (dono, 17/11): ➕ e ✕ ao lado do editar.
    _vx = E.linhas_de_produto("7908045165056", "PR-2", "Porta 2 Relógio + Jóias", 10,
                              [("Preto", ""), ("Branco (P)", "")], "l", "x")
    _sx = E.saldos(E.linhas_de_entrada([(_vx[0], 3)], "l", "x")
                   + E.linhas_de_entrada([(_vx[1], 2)], "l", "x", local=list(E.FULLS)[0]))
    # Dono, 17/11: «preciso poder excluir a quantidade sem ter que dar baixa».
    _kx = [{"codigo": "K1", "tipo": "kit", "itens": E.json.dumps({_vx[1]["id"]: 1})}]
    ok("variação: com peça (físico OU Full) EXCLUI e o aviso diz quantas saem; em kit não exclui",
       variacao_pode_excluir(_vx[0], _sx) == (True, "as 3 peça(s) dela saem do estoque como ajuste de contagem, sem baixa")
       and variacao_pode_excluir(_vx[1], _sx)[0] and "2 peça" in variacao_pode_excluir(_vx[1], _sx)[1]
       and not variacao_pode_excluir(_vx[1], _sx, _kx)[0]
       and variacao_pode_excluir(_vx[1], E.saldos([])) == (True, ""))
    # PELA CADEIA: o ✕ de verdade, com a planilha de mentira — zera as peças
    # (todas as origens e locais) e desativa.
    _db_x = {"p": [dict(x) for x in _vx], "m": E.linhas_de_entrada([(_vx[0], 3)], "l", "x")
             + E.linhas_de_entrada([(_vx[0], 2)], "l", "x", local=list(E.FULLS)[0]), "c": []}
    _gm, _ap, _av = [], {}, []
    _orig_x = (E.carregar_agora, E.gravar_movimentos, E.atualizar_produtos, _avisar)
    try:
        E.carregar_agora = lambda: (_db_x["p"], _db_x["m"], _db_x["c"])
        E.gravar_movimentos = lambda l: _gm.extend(l)
        E.atualizar_produtos = lambda d: _ap.update(d)
        globals()["_avisar"] = lambda msg, erro=False: _av.append((msg, erro))
        _excluir_variacao(_vx[0]["id"], "Preto", "leo")
        _sobra = E.saldos(_db_x["m"] + _gm)
    finally:
        E.carregar_agora, E.gravar_movimentos, E.atualizar_produtos = _orig_x[:3]
        globals()["_avisar"] = _orig_x[3]
    ok("✕ com peça: grava ajuste que ZERA físico e Full, desativa, e diz quantas saíram",
       not any(q for (pid, _l), q in _sobra.items() if pid == _vx[0]["id"])
       and all(m["tipo"] == E.AJUSTE_CONTAGEM for m in _gm) and len(_gm) == 2
       and _ap == {_vx[0]["id"]: {"ativo": "0"}} and _av and "5 peça(s)" in _av[0][0] and not _av[0][1])
    # SALVAR DUAS VEZES (dono, 17/11: «duplicou as variações sozinho»). O
    # segundo clique lê a planilha de AGORA e não grava de novo.
    ok("nomes já cadastrados: só os ATIVOS deste código, com espaço e maiúscula normalizados",
       nomes_ja_cadastrados(_vx + [{**_vx[0], "variacao": "Rosa", "ativo": "0"},
                                   {**_vx[0], "ean": "1", "variacao": "Azul"}], " 7908045165056")
       == {"preto", "branco (p)"})
    _db_s = {"p": [dict(x) for x in _vx], "m": [], "c": []}
    _gp, _av2 = [], []
    _orig_s = (E.carregar_agora, E.gravar_produtos, E.gravar_movimentos, _avisar, st.session_state)
    try:
        E.carregar_agora = lambda: (_db_s["p"], _db_s["m"], _db_s["c"])
        def _grava(l):
            _gp.extend(l)
            _db_s["p"] += l
        E.gravar_produtos = _grava
        E.gravar_movimentos = lambda l: _db_s["m"].extend(l)
        globals()["_avisar"] = lambda msg, erro=False: _av2.append((msg, erro))
        for _clique in range(2):
            st.session_state = {"est_nova_var": True, "est_var_n": 2, "est_var_k": 0,
                                "est_var_nome_0_0": "Porta 2  Relógio + Jóias (G)", "est_var_qtd_0_0": 4,
                                "est_var_nome_0_1": "Azul", "est_var_qtd_0_1": 1}
            _salvar_produto(_vx, "leo", "_pn")
        st.session_state = {"est_nova_var": True, "est_var_n": 1, "est_var_k": 0,
                            "est_var_nome_0_0": "PRETO", "est_var_qtd_0_0": 2}
        _salvar_produto(_vx, "leo", "_pn")
    finally:
        E.carregar_agora, E.gravar_produtos, E.gravar_movimentos, _ = _orig_s[:4]
        globals()["_avisar"] = _orig_s[3]
        st.session_state = _orig_s[4]
    ok("salvar 2× seguidas: as variações novas entram UMA vez; nome que já existe não grava nada",
       len(_gp) == 2 and sorted(x["variacao"] for x in _gp) == ["Azul", "Porta 2 Relógio + Jóias (G)"]
       and not _av2[0][1] and _av2[1][1] and "já estão cadastradas" in _av2[1][0]
       and _av2[2][1] and "«PRETO» já está cadastrada" in _av2[2][0]
       and sum(int(m["qtd"]) for m in _db_s["m"]) == 5)
    _src_pn = _insp.getsource(_painel)
    _src_vp = _insp.getsource(_variacoes_do_painel)
    ok("Estoque cadastrado: a linha escolhida mostra ✕ e ➕ Nova variação",
       "_variacoes_do_painel(variacoes, saldo, quem, pf)" in _insp.getsource(_editar_produto)
       and '_nova_variacao(variacoes, quem, sufixo_ed="_pn", botoes=False)' in _src_vp
       and "on_click=_excluir_variacao" in _src_vp and '"ativo": "0"' in _insp.getsource(_excluir_variacao))

    # FORNECEDOR (dono, 17/11): o NOME de quem vende, ao lado do código dele.
    # Pela CADEIA: o mesmo `linhas_de_produto` que o cadastro chama, com o
    # pior nome (símbolo, acento, espaço duplo) e depois a tela que lê.
    _fz = E.linhas_de_produto("7908045165056", "TRES-B131", "Porta 2 Relógio + Jóias", 31.5,
                              [("", "")], "leo", "x", fornecedor="  Três  Irmãos (SP) + Cia ")
    ok("fornecedor: gravado pelo cadastro, com espaço limpo, numa coluna da aba",
       "fornecedor" in E.COL_PRODUTOS and _fz[0]["fornecedor"] == "Três Irmãos (SP) + Cia")
    _ffe = ficha_entrada_html(_fz, {}, "7908045165056")
    ok("fornecedor: a ficha da entrada mostra o NOME e o código separado",
       "Fornecedor <b" in _ffe and "Três Irmãos (SP) + Cia" in _ffe and "Cód. fornecedor" in _ffe
       and "TRES-B131" in _ffe)
    ok("fornecedor: a busca acha pelo nome dele, sem acento e com símbolo",
       [p["id"] for p in buscar_produtos(_fz, "tres irmaos (sp) +")] == [_fz[0]["id"]]
       and len(tabela_produtos([{"produto": _fz[0]}], "irmãos (sp) + cia")) == 1)
    _sc, _se, _sv = (_insp.getsource(x) for x in (_cadastro, _editar_produto, _salvar_produto))
    _se += _insp.getsource(_edicao_pendente)
    ok("fornecedor: cadastro, edição e nova variação levam o campo até a gravação",
       '"Fornecedor"' in _sc and "fornecedor=fornecedor" in _sc
       and '"Fornecedor"' in _se and '"fornecedor": " ".join(str(dig["fornecedor"]).split())' in _se
       and 'fornecedor=base.get("fornecedor"' in _sv)

    # A FOTO QUE «NÃO SALVOU» (dono, 17/11). O aviso do Drive ia para
    # st.warning e o st.rerun() logo depois o apagava: sobrava «✓ salvo».
    class _Up:
        def getvalue(self):
            return b"x"
    _real_sf = E.salvar_foto
    try:
        E.salvar_foto = lambda d, n: ("", "o Drive recusou (cota)")
        _f1 = foto_da_tela(_Up(), "1")
        E.salvar_foto = lambda d, n: ("F1", "a foto foi gravada, mas o Drive não deixou ela pública")
        _f2 = foto_da_tela(_Up(), "1")
        E.salvar_foto = lambda d, n: ("F1", None)
        _f3 = foto_da_tela(_Up(), "1")
    finally:
        E.salvar_foto = _real_sf
    ok("foto: recusada, gravada sem ser pública, e boa — cada uma diz o que houve",
       _f1 == ("", "⚠ A FOTO NÃO FOI SALVA: o Drive recusou (cota)") and _f2[0] == "F1"
       and _f2[1].startswith("⚠ FOTO:") and _f3 == ("F1", "") and foto_da_tela(None, "1") == ("", ""))
    ok("foto: o aviso entra na mensagem que sobrevive ao rerun, em vermelho",
       _com_foto("✓ Produto atualizado.", _f1[1]) == ("✓ Produto atualizado. · " + _f1[1], True)
       and _com_foto("✓ ok", "") == ("✓ ok", False))
    # Todo campo de foto do estoque passa por foto_da_tela, e quem chama põe
    # o aviso em _com_foto — os cinco irmãos, não só a edição (Forma 1).
    import ast as _ast_ft
    _arv_ft = _ast_ft.parse(open(__file__, encoding="utf-8").read())
    _fun_ft = {n.name: _ast_ft.unparse(n) for n in _arv_ft.body if isinstance(n, _ast_ft.FunctionDef)}
    _sf = [k for k, v in _fun_ft.items() if "E.salvar_foto(" in v]
    _usa = [k for k, v in _fun_ft.items() if "foto_da_tela(" in v and k != "foto_da_tela"]
    _sem = [k for k in _usa if "_com_foto(" not in _fun_ft[k]
            and not (k == "_gravar_baixa" and "_com_foto(" in _fun_ft["_ficha_baixa"]
                                                        and "_gravar_baixa(" in _fun_ft["_ficha_baixa"])]
    _warn = [k for k in _usa if "st.warning(" in _fun_ft[k] and "foto" in _fun_ft[k].split("st.warning(")[1][:60]]
    # O aviso não pode ser trocado no caminho: todo `af` nasce do Drive.
    _af_ruim = [n.name for n in _arv_ft.body if isinstance(n, _ast_ft.FunctionDef)
                for x in _ast_ft.walk(n) if isinstance(x, (_ast_ft.Assign, _ast_ft.AugAssign))
                and "af" in _ast_ft.unparse(x.targets[0] if isinstance(x, _ast_ft.Assign) else x.target)
                .replace(" ", "").split(",")
                and not (isinstance(x.value, _ast_ft.Call)
                         and _ast_ft.unparse(x.value.func) in ("foto_da_tela", "_gravar_baixa"))]
    ok(f"foto: só foto_da_tela chama o Drive, e os {len(_usa)} campos avisam pela mensagem "
       f"({_sem}, {_warn}, {_af_ruim})",
       _sf == ["foto_da_tela"] and len(_usa) == 5 and not _sem and not _warn and not _af_ruim)

    # O PRODUTO ESCOLHIDO NÃO SOME (dono, 17/11). Pela cadeia: as linhas
    # vêm de tabela_produtos, como na tela, antes e depois da variação nova.
    _pe = E.linhas_de_produto("5901234123457", "S2017", "Embaralhador automático", 42, [("", "")], "l", "x")
    _pb = E.linhas_de_produto("7891234567895", "MBLN-06", "Álbum + base", 18, [("", "")], "l", "x")
    _ln = lambda ps: tabela_produtos([{"produto": q, "valor": 0} for q in ps])
    _antes = _ln(_pe + _pb)
    # Agora a variação nova não muda a lista (uma linha por produto); quem
    # muda é um produto novo — e a ✕ de uma variação que abre a linha.
    _nova = E.linhas_de_produto("7890000000017", "CX", "Caixa nova", 42, [("", "")], "l", "x")
    _depois = _ln(_pe + _pb + _nova)
    _i = [l["produto"]["id"] for l in _antes].index(_pe[0]["id"])
    _esc1 = produto_escolhido(_antes, [_i], None, False)
    _esc2 = produto_escolhido(_depois, [], _esc1, False, "5901234123457")
    ok("produto escolhido: lista mudou (variação nova) e ele continua aberto, mesmo com a tabela desmarcada",
       _esc1 == _pe[0]["id"] and assinatura_da_lista(_antes) != assinatura_da_lista(_depois)
       and _esc2 == _pe[0]["id"])
    ok("produto escolhido: e continua no CLIQUE SEGUINTE (o + Nova variação que não abria)",
       produto_escolhido(_depois, [], _esc2, False, "5901234123457") == _pe[0]["id"])
    _ir = E.linhas_de_produto("5901234123457", "S2017", "Embaralhador automático", 42, [("Preto", "")], "l", "x")
    ok("produto escolhido: desmarcou fecha; a excluída deixa aberta a irmã",
       produto_escolhido(_antes, [], _esc1, True) is None
       and produto_escolhido(_ln(_pb + _ir), [], _esc1, False, "5901234123457") == _ir[0]["id"])
    _comvar = _ln(_pe + _pb + E.linhas_de_produto("5901234123457", "S2017", "Embaralhador automático", 42,
                                                  [("Preto", "")], "l", "x"))
    _foto = _ln([{**_pe[0], "foto_id": "F1"}] + _pb)
    ok("produto escolhido: variação nova ou foto nova na MESMA linha também trocam a tabela",
       [l["produto"]["id"] for l in _comvar] == [l["produto"]["id"] for l in _antes]
       and len({assinatura_da_lista(x) for x in (_antes, _comvar, _foto)}) == 3)
    _src_pn2 = _insp.getsource(_painel)
    ok("produto escolhido: a tabela troca de chave quando a lista muda",
       'key=f"est_tab_{sig}"' in _src_pn2 and "produto_escolhido(" in _src_pn2
       and 'desmarcou = ss.get("est_pn_sig") == sig and bool(ss.get("est_pn_sel")) and not sel' in _src_pn2)
    _src_nv = _insp.getsource(_nova_variacao)
    ok("nova variação: um campo de nome só, e Cancelar",
       "JÁ existe" not in _src_nv and "nome_antigo" not in _src_nv
       and "on_click=_fechar_nova_variacao" in _src_nv)

    # UMA LINHA POR PRODUTO (dono, 17/11). Pela cadeia: E.painel monta as
    # linhas por variação, como na tela, e tabela_produtos agrupa.
    import datetime as _dt_g
    _gv = E.linhas_de_produto("7908045165056", "APBL17018", "Jogo de Dardo Magnético 46cm", 75.68,
                              [("Creme", ""), ("Branco (P)", "")], "l", "10/11/2026 10:00")
    _gs = E.linhas_de_produto("7891234567895", "AP3012", "Álbum + base", 38.4, [("", "")], "l", "15/11/2026 10:00")
    _gm = (E.linhas_de_entrada([(_gv[0], 4), (_gv[1], 2), (_gs[0], 1)], "l", "15/11/2026 11:00")
           + E.linhas_de_entrada([(_gv[1], 3)], "l", "15/11/2026 11:00", origem=E.ATACADO))
    _gp = E.painel(_gv + _gs, _gm, _dt_g.date(2026, 11, 17))
    _gt = tabela_produtos(_gp["linhas"])
    _gd = next(g for g in _gt if g["n_var"] == 2)
    ok("lista: uma linha por produto, as variações somadas dentro dela",
       len(_gt) == 2 and [nome_da_linha(g) for g in _gt]
       == ["Álbum + Base", "Jogo de Dardo Magnético 46cm · 2 variações"]
       and _gd["fisico"] == 9 and _gd["varejo"] == 6 and _gd["atacado"] == 3
       and abs(_gd["valor"] - sum(l["valor"] for l in _gp["linhas"] if l["produto"]["ean"] == "7908045165056")) < 0.01
       and set(_gd["variacoes"]) == {_gv[0]["id"], _gv[1]["id"]} and _gd["dias"] == 7)
    _gb = tabela_produtos(_gp["linhas"], "branco (p)")
    ok("lista: a busca pelo nome da VARIAÇÃO acha o produto (uma linha só)",
       len(_gb) == 1 and _gb[0]["produto"]["ean"] == "7908045165056")
    _src_hist = _insp.getsource(_painel)
    ok("lista: o histórico do produto aberto é o de todas as variações",
       'm.get("produto_id") in _ids_pn' in _src_hist and '"Produto": nome_da_linha(l)' in _src_hist)

    # VÁRIAS VARIAÇÕES DE UMA VEZ (dono, 17/11), com o pior nome real.
    _bv, _be = blocos_de_variacao([("  Porta 2 Relógio + Jóias (P) ", 2, None), ("", None, None),
                                   ("Verde", 0, "foto")])
    ok("variações: os quadros preenchidos entram, o vazio é ignorado",
       _be == "" and _bv == [("Porta 2 Relógio + Jóias (P)", 2, None), ("Verde", 0, "foto")])
    ok("variações: sem nome com peça, nome repetido e nada escrito são recusados",
       blocos_de_variacao([("", 3, None)])[1] == "Variação 1: falta o nome."
       and "duas vezes" in blocos_de_variacao([("Verde", 0, None), ("verde", 1, None)])[1]
       and blocos_de_variacao([("", None, None)])[1] == "Escreva o nome da variação.")
    import ast as _ast_nv
    _src_nv2 = _ast_nv.unparse(_ast_nv.parse(_insp.getsource(_nova_variacao)))   # sem comentário
    ok("variações: «➕ Mais uma variação» no quadro, sem st.form, salvar por callback",
       "on_click=_mais_um_quadro_de_variacao" in _src_nv2 and "st.form" not in _src_nv2
       and "on_click=_salvar_produto" in _src_nv2 and "st.rerun" not in _src_nv2)

    # UM SALVAR PARA TUDO (dono, 17/11: «coloquei a foto do produto e das
    # variações, só salvou o da variação»).
    _ini = _iniciais_ed({**prods[0], "sku": "MS-3500", "fornecedor": "Três Irmãos"})
    ok("salvar tudo: sem mudança o produto não é regravado; nome, SKU ou foto mudados são",
       not edicao_mudou(_ini, dict(_ini), False)
       and not edicao_mudou(_ini, {**_ini, "nome": " " + _ini["nome"] + " "}, False)
       and edicao_mudou(_ini, {**_ini, "nome": "Outro"}, False)
       and edicao_mudou(_ini, {**_ini, "sku": "MS-9"}, False) and edicao_mudou(_ini, dict(_ini), True))
    ok("salvar tudo: o «Salvar» do editar e o das variações são o MESMO, e ele lê os dois quadros",
       "on_click=_salvar_produto" in _insp.getsource(_editar_produto)
       and "on_click=_salvar_produto" in _insp.getsource(_nova_variacao)
       and "_edicao_pendente(variacoes, sufixo)" in _insp.getsource(_salvar_produto)
       and "blocos_de_variacao(lidos)" in _insp.getsource(_salvar_produto))

    # COM VARIAÇÃO, O ESTOQUE É SÓ O DELAS (dono, 17/11): o caso da tela —
    # «Jogo de Dardo 34cm» com 10, Marrom 9 e Verde 1 somavam 20.
    _jd = E.linhas_de_produto("7908045100001", "AP3017", "Jogo de Dardo Magnético 34cm", 46.32,
                              [("", "")], "l", "x", custo_atacado="46.32")
    _jv = E.linhas_de_produto("7908045100001", "AP3017", "Jogo de Dardo Magnético 34cm", 46.32,
                              [("Marrom", ""), ("Verde", "")], "l", "x")
    _jm = (E.linhas_de_entrada([(_jd[0], 7)], "l", "x") + E.linhas_de_entrada([(_jd[0], 3)], "l", "x", origem=E.ATACADO)
           + E.linhas_de_entrada([(_jd[0], 2)], "l", "x", local=list(E.FULLS)[0])
           + E.linhas_de_entrada([(_jv[0], 9), (_jv[1], 1)], "l", "x"))
    _jz = E.linhas_de_zerar(_jd[0], _jm, "l", "x", "zerado")
    _js = E.saldos(_jm + _jz)
    ok("zerar: o produto sem nome vai a zero no físico E no Full, origem a origem; as variações ficam",
       sum(q for (pid, _l), q in _js.items() if pid == _jd[0]["id"]) == 0
       and _js.get((_jv[0]["id"], E.FISICO)) == 9 and _js.get((_jv[1]["id"], E.FISICO)) == 1
       and len(_jz) == 3 and all(m["obs"] == "zerado" for m in _jz))
    ok("zerar: o produto sem nome só é «pai» quando é UM, e ao lado de variações com nome",
       pai_sem_nome(_jd + _jv) == _jd[0] and pai_sem_nome(_jd) == _jd[0] and pai_sem_nome(_jv) is None
       and pai_sem_nome(_jd + [{**_jd[0], "id": "X"}] + _jv) is None)
    ok("zerar: salvar variação nova zera o pai, e o Estoque cadastrado oferece o clique para o antigo",
       "_zerar_pai(pai, quem)" in _insp.getsource(_salvar_produto)
       and "on_click=_zerar_pai_agora" in _insp.getsource(_variacoes_do_painel)
       and 'E.atualizar_produtos({pai["id"]: {"ativo": "0"}})' in _insp.getsource(_zerar_pai)
       and "E.kits_com(codigos, pai[\"id\"])" in _insp.getsource(_zerar_pai))

    # ✎ DA VARIAÇÃO e CANCELAR (dono, 17/11).
    _orig_ss2 = st.session_state
    try:
        st.session_state = {"est_ed_1_pn_nome": "x", "est_ed_1_pn_k": 3, "est_ed_1_pn_foto_3": "F", "outra": 1}
        _cancelar_edicao("est_ed_1_pn_")
        _cx = dict(st.session_state)
    finally:
        st.session_state = _orig_ss2
    ok("cancelar edição: o digitado sai e a foto nasce vazia (rodada nova)",
       _cx == {"outra": 1, "est_ed_1_pn_k": 4, "est_var_n": 1, "est_var_k": 1})
    _src_vp2 = _insp.getsource(_variacoes_do_painel)
    ok("variação: no MESMO quadro, cada uma com nome, quantidade e foto; um Salvar tudo e Cancelar",
       "key=_ch_vn(pf, v[\"id\"])" in _src_vp2 and "key=_ch_vq(pf, v[\"id\"])" in _src_vp2
       and "key=_ch_vf(pf, v[\"id\"])" in _src_vp2
       and "on_click=_salvar_produto" in _insp.getsource(_editar_produto)
       and "on_click=_cancelar_edicao" in _insp.getsource(_editar_produto))
    # As edições das variações e a quantidade, pela cadeia (linhas_de_produto
    # → linhas_de_entrada → saldos → linhas_de_ajuste).
    _qv = E.linhas_de_produto("7908045100001", "AP3017", "Jogo", 46, [("Marrom", ""), ("Verde", "")], "l", "x")
    _qm = E.linhas_de_entrada([(_qv[0], 9), (_qv[1], 1)], "l", "x")
    _qs = E.saldos(_qm)
    _qa = ajustes_de_quantidade(_qv, {_qv[0]["id"]: 8, _qv[1]["id"]: 1}, _qs)
    _qz = E.linhas_de_ajuste({"linhas": [{"produto": v, "dif": d} for v, d in _qa]}, "l", "x", "aj", movs=_qm)
    ok("quantidade: o digitado vira ajuste da diferença, e o saldo fica no digitado",
       [(v["id"], d) for v, d in _qa] == [(_qv[0]["id"], -1)]
       and E.saldos(_qm + _qz).get((_qv[0]["id"], E.FISICO)) == 8)
    _em, _ef, _ee = edicoes_de_variacao(_qv, {_qv[0]["id"]: " Amarelo  e Verde ", _qv[1]["id"]: "Verde"},
                                        {_qv[1]["id"]: "F"})
    ok("variações: nome mudado e foto entram; vazio e repetido são recusados",
       _em == {_qv[0]["id"]: {"variacao": "Amarelo e Verde"}} and [v["id"] for v, _f in _ef] == [_qv[1]["id"]]
       and _ee == "" and edicoes_de_variacao(_qv, {_qv[0]["id"]: ""}, {})[2] != ""
       and edicoes_de_variacao(_qv, {_qv[0]["id"]: "verde"}, {})[2] != "")

    # FORNECEDOR EM MASSA (dono, 17/11): um rótulo por produto, e o nome
    # vai para TODAS as variações dele. Pela cadeia: linhas_de_produto.
    _fm = (E.linhas_de_produto("7908045100001", "AP3017", "Jogo de Dardo 34cm", 46, [("Marrom", ""), ("Verde", "")],
                               "l", "x")
           + E.linhas_de_produto("7891234567895", "PR-2", "Porta 2 Relógio + Jóias", 10, [("", "")], "l", "x",
                                 fornecedor="Três Irmãos"))
    _fo = opcoes_fornecedor_em_massa(_fm)
    _fr = list(_fo)
    _fmud, _ferr = mudancas_fornecedor(_fo, [_fr[0]], "  Wang  (SP) + Cia ")
    ok("fornecedor em massa: um por produto, e grava em todas as variações dele",
       len(_fo) == 2 and _fr[0].startswith("Jogo de Dardo 34cm") and "sem fornecedor" in _fr[0]
       and "Três Irmãos" in _fr[1] and _ferr == ""
       and _fmud == {_fm[0]["id"]: {"fornecedor": "Wang (SP) + Cia"}, _fm[1]["id"]: {"fornecedor": "Wang (SP) + Cia"}})
    ok("fornecedor em massa: sem produto ou sem nome não grava",
       mudancas_fornecedor(_fo, [], "X")[1] != "" and mudancas_fornecedor(_fo, _fr, "  ")[1] != "")
    _gm2 = tabela_produtos([{"produto": q, "valor": 0} for q in _fm])
    _om = opcoes_das_marcadas(_gm2)
    ok("fornecedor em massa: as linhas MARCADAS levam todas as variações de cada produto",
       len(_om) == 2 and sorted(sum(_om.values(), [])) == sorted(q["id"] for q in _fm)
       and len(mudancas_fornecedor(_om, list(_om), "Wang")[0]) == 3)
    ok("fornecedor em massa: caixinhas na lista (várias), e salva por callback",
       'selection_mode="multi-row"' in _insp.getsource(_painel)
       and "_fornecedor_em_massa(marcadas)" in _insp.getsource(_painel)
       and "on_click=_salvar_fornecedor_em_massa" in _insp.getsource(_fornecedor_em_massa))

    ok("foto de capa: a lista e a ficha mostram a do produto; sem ela, a da variação",
       E.foto_principal({"foto_id": "V", "foto_produto": "P"}) == "P" and E.foto_principal({"foto_id": "V"}) == "V"
       and "FCAPA" in ficha_entrada_html([{**prods[0], "foto_id": "V", "foto_produto": "FCAPA"}], {}, "1")
       and 'E.foto_principal(l["produto"])' in _insp.getsource(_painel))

    _srcc = _insp.getsource(_painel) + _insp.getsource(_editar_produto)
    ok("código de barras: coluna própria na lista e à vista no quadro, com etiqueta (17/11)",
       '"Código de barras": E.limpar_codigo(l["produto"].get("ean"))' in _srcc
       and "Código de barras **" in _srcc and "_etiqueta(_cod" in _srcc)

    # ✎ EDITAR O KIT INTEIRO (dono, 17/11): nome, foto e itens.
    ok("kit: quantidade muda, 0 tira, item novo soma; kit vazio é recusado",
       receita_editada({"A": 2, "B": 1}, {"A": 3, "B": 0}, "C", 4) == ({"A": 3, "C": 4}, "")
       and receita_editada({"A": 2}, {"A": 2}, "A", 1) == ({"A": 3}, "")
       and receita_editada({"A": 2}, {"A": 0})[1] != "")
    _sk = _insp.getsource(_editar_kit)
    ok("kit: o ✎ editar tem nome, FOTO, itens, Salvar e Cancelar",
       '"Foto do kit"' in _sk and "on_click=_salvar_kit" in _sk and "on_click=_fechar_ed_kit" in _sk
       and '"Pôr mais um item"' in _sk and "_editar_kit(k, por_id, prods)" in _insp.getsource(_kits_cadastrados))
    ok("kit: o recém-criado tem ✎ editar ao lado da etiqueta, e abre o editor dele (dono, 23/11)",
       "on_click=_abrir_ed_kit, args=(nova[0],)" in _insp.getsource(_criar_kit))

    print("\n" + ("TUDO OK" if not falhas else f"{falhas} FALHA(S)"))
    raise SystemExit(1 if falhas else 0)
