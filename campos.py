"""campos.py — as tabelas editáveis viram campos, uma linha por bloco.

Pedido do dono, 09/10 ("Pode aplicar os dois do layout", sobre a prévia em que
escolheu "É para aplicar em TODAS as bases"): clicar na célula do
`st.data_editor` abre uma caixinha flutuante por cima da tabela — é o editor do
Streamlit, e não dá para desligar. A saída é não usar a grade: cada linha vira
um bloco com um campo por coluna, e digita-se direto no campo.

UM LUGAR SÓ, COMO O DINHEIRO
----------------------------
`instalar(st)` troca o `st.data_editor` por `editor`, uma vez, no `app.py` — o
mesmo caminho de `rotulos.instalar_moeda`. As telas continuam chamando
`st.data_editor(df, column_config=..., num_rows=..., key=...)` e recebem o
MESMO DataFrame de volta: mesmas colunas, mesma ordem, mesmo índice nas linhas
que já existiam. O código que grava não muda em tela nenhuma. Base nova que
usar `st.data_editor` já nasce em campos, sem ninguém lembrar.

O QUE A GRADE FAZIA E O BLOCO TEM DE FAZER IGUAL
------------------------------------------------
- Linha nova (`num_rows="dynamic"`): botão "+ Adicionar item". Linha nova toda
  em branco não volta — a grade também não devolvia linha que ninguém tocou.
- Apagar linha: a caixa "Remover" tira a linha do que volta; só vale ao
  salvar, como na grade.
- Coluna `None` no column_config: não aparece, e volta como estava.
- Coluna travada (`disabled`): aparece como texto, sem campo.
- Campo que ninguém mexeu volta com o valor ORIGINAL, no tipo original — o
  `None` não vira `""`, nem o `5` vira `5.0`.

DINHEIRO CONTINUA R$ 58.490,56
------------------------------
O `st.number_input` só sabe "58490.56". A coluna de dinheiro (`format` com R$,
ou "localized", que é como `rotulos` entrega a coluna de dinheiro ao editor)
vira campo de texto mostrando "58.490,56", e o que se digita é lido de volta
por `numero_br`. O que não se entende como número não é gravado: o campo
avisa e o valor anterior fica.

LISTA GRANDE É PAGINADA
-----------------------
O extrato do mês e a fila de finalidades passam de cem linhas. Cem blocos de
quatro campos são quatrocentos widgets a CADA tecla (Regra 8). Mostra-se
`POR_PAGINA` linhas por vez; o que foi editado numa página fica guardado em
`st.session_state` e volta junto quando se salva de outra.
"""
import hashlib
import math

POR_PAGINA = 20
CAMPOS_POR_LINHA = 4
_ESTADO = "_campos"


# ── Leitura do column_config ─────────────────────────────────────────────────
def _vazio(v):
    """None, NaN e "" — a célula vazia do Google chega como ""."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return True
    try:
        return isinstance(v, float) and math.isnan(v)
    except TypeError:
        return False
    return False


def _cfg_de(column_config, coluna):
    """(visível, rótulo, tipo, type_config, cfg) de uma coluna."""
    cc = column_config or {}
    if coluna in cc and cc[coluna] is None:
        return False, coluna, "oculta", {}, {}
    v = cc.get(coluna)
    if isinstance(v, str):
        return True, v, "text", {}, {"label": v}
    if isinstance(v, dict):
        tc = v.get("type_config") or {}
        return (True, v.get("label") or coluna, tc.get("type") or "text",
                tc, v)
    return True, coluna, "texto_livre", {}, {}


def eh_dinheiro(tipo, type_config):
    fmt = str((type_config or {}).get("format") or "")
    return tipo == "number" and ("R$" in fmt or fmt == "localized")


def eh_inteiro(type_config, valores):
    """A coluna numérica é de inteiros? `%d` decide; sem formato, o passo e
    os valores decidem."""
    fmt = str((type_config or {}).get("format") or "")
    if "%d" in fmt or "%i" in fmt:
        return True
    if fmt:
        return False
    passo = (type_config or {}).get("step")
    if passo is not None and float(passo) != int(float(passo)):
        return False
    vals = [v for v in valores if not _vazio(v)]
    return bool(vals) and passo is not None and all(
        isinstance(v, (int,)) and not isinstance(v, bool) for v in vals)


def _tipo_pelo_dado(cfg, serie):
    """Coluna sem tipo declarado (só rótulo, ou nada) toma o tipo do dado —
    senão um número sem config viraria texto e voltaria como string."""
    import pandas as pd
    visivel, rotulo, tipo, tc, c = cfg
    if tipo not in ("text", "texto_livre") or tc:
        return cfg
    if pd.api.types.is_bool_dtype(serie):
        return visivel, rotulo, "checkbox", {}, c
    if pd.api.types.is_numeric_dtype(serie):
        return visivel, rotulo, "number", {}, c
    return visivel, rotulo, "text", {}, c


def _calculada(coluna, cfg, travadas):
    """Coluna numérica travada é conta da tela (realizado, saldo, "preenche
    junto"): fica fora da identidade da linha. Senão o realizado que se
    atualiza no meio da digitação trocaria a chave do campo, e a meta
    digitada sumiria ao salvar — o defeito de 17/09 por outro caminho."""
    visivel, rotulo, tipo, tc, c = cfg
    return (tipo == "number"
            and (coluna in travadas or bool(c.get("disabled"))))


# ── Dinheiro: "58.490,56" ⇄ 58490.56 ─────────────────────────────────────────
def mostrar_br(v):
    """58490.56 → "58.490,56"; vazio → ""."""
    if _vazio(v):
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    txt = f"{abs(f):,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")
    return ("-" if f < 0 else "") + txt


def numero_br(txt):
    """O que se digita num campo de dinheiro → float, None (vazio) ou levanta
    ValueError. Aceita "58.490,56", "58490,56", "58490.56", "R$ 1.500",
    "1.500" (milhar) e "-12,5"."""
    s = str(txt or "").strip().replace("R$", "").replace(" ", "")
    if not s:
        return None
    neg = s.startswith("-")
    s = s.lstrip("-+")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1 or (s.count(".") == 1
                              and len(s.split(".")[1]) == 3):
        # "1.500" e "1.500.000": ponto de milhar, o jeito de quem digita aqui.
        s = s.replace(".", "")
    if not s or any(ch not in "0123456789." for ch in s) or s.count(".") > 1:
        raise ValueError(txt)
    v = float(s)
    return -v if neg else v


# ── Identidade das linhas ────────────────────────────────────────────────────
def ids_das_linhas(df):
    """Uma identidade por linha, tirada do CONTEÚDO, e não da posição.

    Pela posição, trocar de mês com a mesma chave mostraria na linha 3 o que
    se digitou na linha 3 do mês anterior. Duas linhas idênticas recebem o
    número da ocorrência, para não repetirem a chave do widget.
    """
    vistos = {}
    fora = []
    for linha in df.itertuples(index=False, name=None):
        h = hashlib.sha1(repr(linha).encode("utf-8", "replace")).hexdigest()[:10]
        n = vistos.get(h, 0)
        vistos[h] = n + 1
        fora.append(f"{h}{n}")
    return fora


# ── O editor ─────────────────────────────────────────────────────────────────
def _botao(st, rotulo, chave, **kw):
    """`st.button` fora do formulário, `form_submit_button` dentro.

    O Streamlit recusa os dois do lado errado, antes de desenhar — então
    tenta-se o que a detecção indica e, se ela errar, o outro.
    """
    try:
        from streamlit.elements.lib.form_utils import is_in_form
        em_form = is_in_form(st._main)
    except Exception:
        em_form = False
    ordem = ("form", "solto") if em_form else ("solto", "form")
    erro = None
    for modo in ordem:
        try:
            if modo == "form":
                return st.form_submit_button(rotulo, **kw)
            return st.button(rotulo, key=chave, **kw)
        except Exception as e:  # StreamlitAPIException: lado errado do form
            if "form" not in str(e).lower():
                raise
            erro = e
    raise erro


def _texto_lido(v, tipo, tc):
    if _vazio(v):
        return ""
    if tipo == "checkbox":
        return "✔" if bool(v) else ""
    if eh_dinheiro(tipo, tc):
        return "R$ " + mostrar_br(v)
    return str(v)


def _campo(col, rotulo, tipo, tc, cfg, inicial, chave, valores_coluna):
    """Desenha um campo e devolve o valor digitado (ou o original, se o campo
    não mudou)."""
    ajuda = cfg.get("help")
    if tipo == "checkbox":
        # "FALSE" é texto, e bool("FALSE") é True.
        mostrado = (str(inicial).strip().upper() in ("TRUE", "1", "SIM", "X",
                                                      "✔", "1.0")
                    if isinstance(inicial, str) else
                    (bool(inicial) if not _vazio(inicial) else False))
        v = col.checkbox(rotulo, value=mostrado, key=chave, help=ajuda)
        return inicial if v == mostrado else v
    if tipo == "selectbox":
        opcoes = list(tc.get("options") or [])
        if not _vazio(inicial) and inicial not in opcoes:
            opcoes = [inicial] + opcoes
        idx = opcoes.index(inicial) if (not _vazio(inicial)
                                        and inicial in opcoes) else None
        v = col.selectbox(rotulo, opcoes, index=idx, key=chave, help=ajuda,
                          placeholder="Escolha")
        mostrado = inicial if idx is not None else None
        return inicial if v == mostrado else v
    if eh_dinheiro(tipo, tc):
        mostrado = mostrar_br(inicial)
        rot = rotulo if "R$" in rotulo else f"{rotulo} (R$)"
        txt = col.text_input(rot, value=mostrado, key=chave, help=ajuda,
                             placeholder="0,00")
        if txt == mostrado:
            return inicial
        try:
            v = numero_br(txt)
        except ValueError:
            col.caption(f"⚠️ «{txt}» não é um valor — ficou {mostrado or 'vazio'}")
            return inicial
        mn, mx = tc.get("min_value"), tc.get("max_value")
        if v is not None and ((mn is not None and v < mn)
                              or (mx is not None and v > mx)):
            col.caption(f"⚠️ fora do limite — ficou {mostrado or 'vazio'}")
            return inicial
        return v
    if tipo == "number":
        inteiro = eh_inteiro(tc, valores_coluna)
        conv = int if inteiro else float
        try:
            mostrado = (None if _vazio(inicial)
                        else conv(float(str(inicial).replace(",", "."))))
        except (TypeError, ValueError):
            # Texto gravado numa coluna de número: campo de texto, para o
            # dado não sumir nem derrubar a tela.
            mostrado_t = str(inicial)
            v = col.text_input(rotulo, value=mostrado_t, key=chave, help=ajuda)
            return inicial if v == mostrado_t else v
        mn, mx, passo = tc.get("min_value"), tc.get("max_value"), tc.get("step")
        mn = None if mn is None else conv(mn)
        mx = None if mx is None else conv(mx)
        # Valor gravado fora do limite NÃO é cortado em silêncio: o limite
        # abre até ele. Cortar mudaria o dado de quem só foi salvar outra linha.
        if mostrado is not None and mn is not None and mostrado < mn:
            mn = mostrado
        if mostrado is not None and mx is not None and mostrado > mx:
            mx = mostrado
        passo = conv(passo) if passo is not None else (1 if inteiro else 0.01)
        fmt = str(tc.get("format") or "")
        fmt = fmt if fmt.startswith("%") else ("%d" if inteiro else None)
        v = col.number_input(rotulo, min_value=mn, max_value=mx,
                             value=mostrado, step=passo, format=fmt,
                             key=chave, help=ajuda)
        return inicial if v == mostrado else v
    mostrado = "" if _vazio(inicial) else str(inicial)
    v = col.text_input(rotulo, value=mostrado, key=chave, help=ajuda,
                       max_chars=tc.get("max_chars"))
    return inicial if v == mostrado else v


def editor(st, data, column_config=None, num_rows="fixed", disabled=False,
           key=None, column_order=None, _original=None, **kw):
    """Mesmo contrato do `st.data_editor`, desenhado em campos."""
    import pandas as pd
    if not isinstance(data, pd.DataFrame) or key is None:
        # Sem DataFrame ou sem chave não há como guardar a edição entre
        # passadas: fica a grade, que é o comportamento de antes.
        if _original is not None:
            return _original(data, column_config=column_config,
                             num_rows=num_rows, disabled=disabled, key=key,
                             column_order=column_order, **kw)
        return data
    colunas = list(data.columns)
    travadas = (set(colunas) if disabled is True
                else set(disabled or []))
    cfgs = {c: _tipo_pelo_dado(_cfg_de(column_config, c), data[c])
            for c in colunas}
    vis = [c for c in (column_order or colunas)
           if c in cfgs and cfgs[c][0]]
    dinamico = num_rows == "dynamic" and disabled is not True

    ids = ids_das_linhas(data[[c for c in colunas
                               if not _calculada(c, cfgs[c], travadas)]])
    assinatura = hashlib.sha1("|".join(ids).encode()).hexdigest()[:12]
    todos = st.session_state.setdefault(_ESTADO, {})
    est = todos.get(key)
    if not est or est.get("assinatura") != assinatura:
        # O dado mudou (salvou, trocou de mês): o que estava guardado era do
        # dado anterior. Fica só a página.
        est = {"assinatura": assinatura, "valores": {}, "novos": 0,
               "pagina": (est or {}).get("pagina", 0)}
        todos[key] = est
    valores = est["valores"]

    registros = data.to_dict("records")
    linhas = [(rid, i, reg) for rid, i, reg in zip(ids, data.index, registros)]
    novos = [(f"novo{n}", None, {c: (cfgs[c][4] or {}).get("default")
                                 for c in colunas})
             for n in range(est["novos"])]
    todas = linhas + novos
    paginas = max(1, math.ceil(len(todas) / POR_PAGINA))
    pagina = min(max(int(est.get("pagina") or 0), 0), paginas - 1)
    est["pagina"] = pagina

    pref = f"cp_{key}"
    mudou_pagina = None
    if paginas > 1:
        c_info, c_ant, c_prox = st.columns([4, 1, 1])
        ini = pagina * POR_PAGINA
        c_info.caption(f"Linhas {ini + 1}–{min(ini + POR_PAGINA, len(todas))} "
                       f"de {len(todas)} · página {pagina + 1} de {paginas}")
        with c_ant:
            if _botao(st, "◀ Anterior", f"{pref}_ant", disabled=pagina == 0,
                      use_container_width=True):
                mudou_pagina = pagina - 1
        with c_prox:
            if _botao(st, "Próxima ▶", f"{pref}_prox",
                      disabled=pagina >= paginas - 1,
                      use_container_width=True):
                mudou_pagina = pagina + 1

    colunas_de = {c: [r.get(c) for r in registros] for c in colunas}
    for rid, _i, reg in todas[pagina * POR_PAGINA:(pagina + 1) * POR_PAGINA]:
        guardado = valores.setdefault(rid, {})
        campos = list(vis) + (["__remover"] if dinamico else [])
        with st.container(border=True):
            for ini in range(0, len(campos), CAMPOS_POR_LINHA):
                grupo = campos[ini:ini + CAMPOS_POR_LINHA]
                cols = st.columns(CAMPOS_POR_LINHA)
                for col, c in zip(cols, grupo):
                    chave = f"{pref}_{rid}_{colunas.index(c) if c in colunas else 'rm'}"
                    if c == "__remover":
                        guardado["__remover"] = col.checkbox(
                            "🗑️ Remover", value=bool(guardado.get("__remover")),
                            key=chave)
                        continue
                    _v, rotulo, tipo, tc, cfg = cfgs[c]
                    original = reg.get(c)
                    inicial = guardado.get(c, original)
                    if c in travadas or cfg.get("disabled"):
                        col.caption(rotulo)
                        col.markdown(_texto_lido(original, tipo, tc) or "—")
                        continue
                    guardado[c] = _campo(col, rotulo, tipo, tc, cfg,
                                         inicial, chave, colunas_de[c])

    if dinamico:
        if _botao(st, "+ Adicionar item", f"{pref}_novo"):
            est["novos"] += 1
            st.rerun()
    if mudou_pagina is not None:
        est["pagina"] = mudou_pagina
        st.rerun()

    return montar(data, linhas, novos, valores, cfgs)


def montar(data, linhas, novos, valores, cfgs):
    """O DataFrame que a grade devolveria. Pura.

    Linha existente: os valores originais com o que foi digitado por cima, no
    índice dela; removida, não volta. Linha nova: só volta se alguém
    preencheu algum campo, e com os obrigatórios preenchidos.
    """
    import pandas as pd
    colunas = list(data.columns)
    recs, idx = [], []
    for rid, i, reg in linhas:
        g = valores.get(rid) or {}
        if g.get("__remover"):
            continue
        recs.append({c: g.get(c, reg.get(c)) for c in colunas})
        idx.append(i)
    prox = (max([int(i) for i in data.index if pd.api.types.is_integer(i)],
                default=-1) + 1)
    for rid, _i, reg in novos:
        g = valores.get(rid) or {}
        if g.get("__remover"):
            continue
        rec = {c: g.get(c, reg.get(c)) for c in colunas}
        preenchidos = [c for c in colunas
                       if not _vazio(rec[c]) and rec[c] != "" and rec[c] is not False]
        if not preenchidos:
            continue
        if any(cfgs[c][4].get("required") and (_vazio(rec[c]) or rec[c] == "")
               for c in colunas):
            continue
        recs.append(rec)
        idx.append(prox)
        prox += 1
    # Sem forçar o tipo de volta: 650,50 digitado numa coluna que só tinha
    # inteiros viraria 650. A grade também deixava a coluna virar float.
    return pd.DataFrame(recs, columns=colunas, index=idx)


def instalar(st):
    """`st.data_editor` passa a desenhar em campos. Idempotente.

    Chamado no `app.py` ANTES de `rotulos.instalar_moeda`: o embrulho do
    dinheiro fica por fora e o editor de campos recebe a coluna de dinheiro
    como "localized" — que `eh_dinheiro` reconhece.
    """
    atual = getattr(st, "data_editor", None)
    f = atual
    while f is not None:
        if getattr(f, "_ms_campos", False):
            return
        f = getattr(f, "__wrapped__", None)
    if atual is None:
        return

    def _editor(*a, **k):
        if a:
            k.setdefault("data", a[0])
        return editor(st, k.pop("data", None), _original=atual, **k)

    _editor._ms_campos = True
    _editor.__wrapped__ = atual
    st.data_editor = _editor


# ── Conferência ──────────────────────────────────────────────────────────────
# Pelo Streamlit DE VERDADE (`AppTest`), e não por um duplo: o que se mede
# aqui é justamente o que o duplo não sabe — botão dentro e fora de
# formulário, estado do widget entre passadas, chave repetida.
def _app_teste():
    import streamlit as st
    import pandas as pd
    import campos
    import rotulos
    # A ordem do app.py, duas vezes: a segunda passada do script não pode
    # embrulhar o embrulho.
    campos.instalar(st)
    rotulos.instalar_moeda(st)
    campos.instalar(st)
    rotulos.instalar_moeda(st)
    cfg = {"item": st.column_config.TextColumn("Item", required=True),
           "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f",
                                                  min_value=0.0),
           "dia": st.column_config.NumberColumn("Dia", min_value=0,
                                                max_value=31, step=1,
                                                format="%d"),
           "forma": st.column_config.SelectboxColumn(
               "Forma", options=["PIX", "BOLETO"]),
           "realizado": st.column_config.NumberColumn(
               "Realizado", format="R$ %.2f", disabled=True),
           "id": None}
    base = st.session_state.get("base") or [
        {"item": "Aluguel", "valor": 3000.0, "dia": 5, "forma": "PIX",
         "realizado": 10.0, "id": "a"},
        {"item": "Energia", "valor": 650.0, "dia": 12, "forma": "BOLETO",
         "realizado": 20.0, "id": "b"}]
    df = pd.DataFrame(base)
    if st.session_state.get("realizado_mudou"):
        df["realizado"] = df["realizado"] + 1
    with st.form("f1"):
        ed = st.data_editor(df, num_rows="dynamic", hide_index=True,
                            key="ed1", column_config=cfg)
        st.session_state["salvou"] = st.form_submit_button("💾 Salvar")
    st.session_state["ret"] = ed.to_dict("records")
    st.session_state["idx"] = [int(i) for i in ed.index]
    # Segundo formulário na mesma página, com os mesmos botões: o
    # `form_submit_button` não tem `key`, e o rótulo repetido não pode
    # derrubar a tela.
    with st.form("f2"):
        st.data_editor(df, num_rows="dynamic", key="ed2", column_config=cfg)
        st.form_submit_button("Salvar 2")
    # Lista longa DENTRO de formulário: o botão de página é o envio do
    # formulário, e o que se digitou na página 1 só chega ao script nele.
    with st.form("f3"):
        ed5 = st.data_editor(pd.DataFrame([{"nome": f"M{i}"}
                                           for i in range(40)]), key="ed5")
        st.form_submit_button("Salvar 3")
    st.session_state["ret5"] = ed5.to_dict("records")
    # Fora de formulário, lista longa e com linhas idênticas.
    # "qtd" não tem column_config: o tipo vem do dado. QUARENTA linhas, duas
    # páginas cheias: o `AppTest` guarda os elementos da passada interrompida
    # pelo `st.rerun()`, e uma página 2 mais curta deixaria widgets velhos na
    # árvore dele (o navegador os apaga ao fim da passada).
    longa = pd.DataFrame([{"nome": "X", "valor": 1.0, "qtd": 1}] * 3
                         + [{"nome": f"L{i}", "valor": float(i), "qtd": i}
                            for i in range(37)])
    ed3 = st.data_editor(longa, key="ed3", disabled=["valor"])
    st.session_state["ret3"] = ed3.to_dict("records")
    # Células como o Google devolve: "" no número, texto no número, e
    # "FALSE" (texto) na caixa de marcar.
    crua = pd.DataFrame([{"n": "", "ok": "FALSE"}, {"n": "7", "ok": "TRUE"},
                         {"n": "abc", "ok": ""}])
    ed4 = st.data_editor(crua, key="ed4", column_config={
        "n": st.column_config.NumberColumn("N", min_value=0, step=1,
                                           format="%d"),
        "ok": st.column_config.CheckboxColumn("OK")})
    st.session_state["ret4"] = ed4.to_dict("records")


if __name__ == "__main__":
    import pandas as _pd_t
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    ok("dinheiro digitado como o dono escreve",
       numero_br("58.490,56") == 58490.56 and numero_br("R$ 1.500") == 1500.0
       and numero_br("58490.56") == 58490.56 and numero_br("-12,5") == -12.5
       and numero_br("") is None and numero_br("199,9") == 199.9)
    try:
        numero_br("12a")
        ok("texto que não é número é recusado", False)
    except ValueError:
        ok("texto que não é número é recusado", True)
    ok("dinheiro mostrado como o dono escreve",
       mostrar_br(58490.56) == "58.490,56" and mostrar_br(None) == ""
       and mostrar_br(float("nan")) == "" and mostrar_br(-3) == "-3,00")
    _d = _pd_t.DataFrame([{"a": 1}, {"a": 1}, {"a": 2}])
    _ids = ids_das_linhas(_d)
    ok("linhas idênticas não repetem a identidade", len(set(_ids)) == 3)
    ok("a identidade vem do conteúdo, não da posição",
       ids_das_linhas(_pd_t.DataFrame([{"a": 2}]))[0] == _ids[2])

    import types as _ty_t
    import rotulos as _rot_t
    _fake = _ty_t.SimpleNamespace(data_editor=lambda *a, **k: "grade",
                                  dataframe=lambda *a, **k: None)
    instalar(_fake)
    _rot_t.instalar_moeda(_fake)
    _uma = _fake.data_editor
    for _ in range(3):   # cada passada do script chama os dois de novo
        instalar(_fake)
        _rot_t.instalar_moeda(_fake)
    ok("instalar a cada passada não embrulha o embrulho",
       _fake.data_editor is _uma)
    ok("sem DataFrame ou sem chave, fica a grade de antes",
       _fake.data_editor([1, 2], key="k") == "grade"
       and _fake.data_editor(_pd_t.DataFrame([{"a": 1}])) == "grade")

    # Linha nova em branco, numa grade SEM coluna obrigatória: só a regra
    # do "ninguém preencheu" a segura.
    _dn = _pd_t.DataFrame([{"a": "x", "b": 1.0}])
    _cf = {c: _cfg_de({}, c) for c in _dn.columns}
    _lin = [("r0", 0, {"a": "x", "b": 1.0})]
    _nov = [("novo0", None, {"a": None, "b": None})]
    ok("linha nova que ninguém preencheu não volta",
       len(montar(_dn, _lin, _nov, {"novo0": {"a": "", "b": None}}, _cf)) == 1
       and len(montar(_dn, _lin, _nov, {"novo0": {"a": "y"}}, _cf)) == 2)

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(_app_teste, default_timeout=30).run()
    ok("a tela monta no Streamlit de verdade, com dois formulários e uma "
       "lista solta", not at.exception)
    _st = at.session_state
    ok("nada mexido: volta o mesmo DataFrame, nos mesmos tipos",
       _st["ret"] == [
           {"item": "Aluguel", "valor": 3000.0, "dia": 5, "forma": "PIX",
            "realizado": 10.0, "id": "a"},
           {"item": "Energia", "valor": 650.0, "dia": 12, "forma": "BOLETO",
            "realizado": 20.0, "id": "b"}]
       and isinstance(_st["ret"][0]["dia"], int))
    _txt = {t.key: t for t in at.text_input}
    ok("dinheiro aparece 3.000,00, e não 3000.0",
       any(t.value == "3.000,00" for t in at.text_input))
    ok("coluna oculta não aparece, coluna travada não vira campo",
       not any(t.value == "a" for t in at.text_input)
       and not any(n.label == "Realizado" for n in at.number_input))

    def _clicar(rotulo, n=0):
        [b for b in at.button if b.label == rotulo][n].click()
        at.run()

    def _campo_txt(valor):
        return [t for t in at.text_input if t.value == valor][0]

    _campo_txt("3.000,00").set_value("3.250,50")
    [n for n in at.number_input if n.value == 12][0].set_value(15)
    [s for s in at.selectbox if s.value == "BOLETO"][0].select("PIX")
    _clicar("💾 Salvar")
    ok("o que se digita volta no DataFrame, no índice de antes",
       not at.exception and _st["salvou"]
       and _st["ret"][0]["valor"] == 3250.5 and _st["ret"][1]["dia"] == 15
       and _st["ret"][1]["forma"] == "PIX" and _st["idx"] == [0, 1])

    _campo_txt("650,00").set_value("abc")
    _clicar("💾 Salvar")
    ok("valor que não é número não é gravado: fica o anterior, e avisa",
       _st["ret"][1]["valor"] == 650.0
       and any("não é um valor" in c.value for c in at.caption))
    _campo_txt("abc").set_value("650,00")

    _clicar("+ Adicionar item")
    _vazios = [t for t in at.text_input if t.value == ""]
    ok("+ Adicionar item abre uma linha, e linha em branco não volta",
       not at.exception and len(_vazios) >= 2 and len(_st["ret"]) == 2)
    _vazios[1].set_value("199,9")   # valor sem o item obrigatório
    _clicar("💾 Salvar")
    ok("linha nova sem o campo obrigatório não volta", len(_st["ret"]) == 2)
    [t for t in at.text_input if t.value == ""][0].set_value("Internet")
    _clicar("💾 Salvar")
    ok("linha nova preenchida volta no fim, com índice novo",
       len(_st["ret"]) == 3 and _st["ret"][2]["item"] == "Internet"
       and _st["ret"][2]["valor"] == 199.9 and _st["idx"] == [0, 1, 2])

    [c for c in at.checkbox if c.label == "🗑️ Remover"][0].check()
    _clicar("💾 Salvar")
    ok("Remover tira a linha do que volta",
       [r["item"] for r in _st["ret"]] == ["Energia", "Internet"]
       and _st["idx"] == [1, 2])

    # O dado mudou (salvou e a planilha voltou outra): o guardado era do
    # dado anterior e não pode reaparecer.
    at.session_state["base"] = [
        {"item": "Aluguel", "valor": 3100.0, "dia": 5, "forma": "PIX",
         "realizado": 10.0, "id": "a"}]
    at.run()
    ok("dado novo: o que estava guardado do anterior some",
       not at.exception and _st["ret"] == [
           {"item": "Aluguel", "valor": 3100.0, "dia": 5, "forma": "PIX",
            "realizado": 10.0, "id": "a"}])

    # A conta da tela (realizado) muda entre a digitação e o salvar.
    _campo_txt("3.100,00").set_value("4.000,00")
    at.session_state["realizado_mudou"] = True
    _clicar("💾 Salvar")
    ok("o realizado que muda no meio não apaga o que foi digitado",
       not at.exception and _st["ret"][0]["valor"] == 4000.0
       and _st["ret"][0]["realizado"] == 11.0)

    ok("célula vazia, texto no número e \"FALSE\" não derrubam a tela, e "
       "voltam como estavam",
       _st["ret4"] == [{"n": "", "ok": "FALSE"}, {"n": "7", "ok": "TRUE"},
                       {"n": "abc", "ok": ""}]
       and [c.value for c in at.checkbox if c.label == "OK"] == [False, True,
                                                                 False])

    _campo_txt("M1").set_value("M1 editado")
    _clicar("Próxima ▶", 0)
    ok("no formulário, a edição da página 1 sobrevive ao botão de página",
       not at.exception and _st["ret5"][1]["nome"] == "M1 editado"
       and any(t.value == "M20" for t in at.text_input))

    # Lista longa, fora de formulário: paginada, e a edição de uma página
    # sobrevive à troca de página.
    ok("lista longa mostra uma página por vez",
       any("página 1 de 2" in c.value for c in at.caption)
       and len(_st["ret3"]) == 40)
    _campo_txt("L0").set_value("L0 editado")
    at.run()
    _clicar("Próxima ▶", -1)
    ok("a edição da página 1 volta junto quando se está na página 2",
       not at.exception and any("página 2 de 2" in c.value for c in at.caption)
       and _st["ret3"][3]["nome"] == "L0 editado"
       and [r["nome"] for r in _st["ret3"][:3]] == ["X", "X", "X"])
    _clicar("◀ Anterior", -1)
    ok("de volta à página 1, o campo mostra o que foi digitado",
       not at.exception and any(t.value == "L0 editado" for t in at.text_input)
       and _st["ret3"][3]["nome"] == "L0 editado")
    ok("coluna numérica sem column_config vira campo de número, não texto",
       any(n.label == "qtd" for n in at.number_input)
       and not any(t.label == "qtd" for t in at.text_input)
       and isinstance(_st["ret3"][0]["qtd"], int))

    print(f"\nfalhas: {falhas}")
    raise SystemExit(1 if falhas else 0)
