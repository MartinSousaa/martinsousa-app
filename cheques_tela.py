"""cheques_tela.py — a carteira de cheques no Studio.

Três perguntas, nesta ordem, porque é a ordem da decisão:

    quanto ainda vai sair?      em aberto
    o que já devia ter saído?   pendente — venceu e não baixou
    quanto sai neste mês?       a vencer no mês

EM ABERTO e PENDENTE não são campos: são conta, feita na hora, contra a data de
hoje. Escritas à mão na planilha elas erram no dia seguinte — o cheque de 25/09
vira pendente sozinho em 26/09, e ninguém reabre a planilha para mover a
célula.
"""

from datetime import datetime

import streamlit as st


def _brl(v):
    return "R$ " + f"{float(v or 0):,.2f}".replace(",", "X").replace(
        ".", ",").replace("X", ".")


def pagina(usuario_logado=None):
    import pandas as pd
    import cheques as _ch
    import placar_core as _pc
    import rotulos as _rot

    st.markdown("#### 🧾 Cheques")
    st.caption(
        "O cheque emitido, que o extrato só conhece no dia em que compensa. "
        "Aqui ele existe desde que foi dado — e é assim que entra no "
        "comprometido do mês, na Home."
    )

    hoje = datetime.now(_pc.FUSO).date()
    linhas = _ch.carregar()

    # ── importar ─────────────────────────────────────────────────────────
    # Fora e ACIMA de qualquer editor: botão embaixo de grade é o clique que
    # se perde quando a célula ainda está aberta.
    ci, cb = st.columns([3, 1])
    ci.caption(
        "A primeira carga vem da aba **CHEQUES** do seu Controle MS. Depois "
        "disso o cadastro vive aqui: importar de novo não duplica (o número da "
        "folha é a identidade) nem desfaz baixa dada nesta tela."
    )
    if cb.button("📥 Importar do Controle MS", use_container_width=True,
                 key="ch_importar"):
        brutos, erro = _ch.do_controle_ms()
        if erro:
            st.error(f"Não consegui ler: {erro}")
        else:
            novas, repetidas, erro_g = _ch.gravar(brutos, usuario_logado)
            if erro_g:
                st.error(f"Li {len(brutos)} da planilha e não gravei: {erro_g}")
            else:
                st.success(
                    f"{novas} cheque(s) novo(s) gravado(s)"
                    + (f" · {repetidas} já estavam aqui" if repetidas else "")
                )
                linhas = _ch.carregar()

    if not linhas:
        st.info("Nenhum cheque cadastrado ainda. Importe do Controle MS ou "
                "cadastre um abaixo.")

    # ── os três números ──────────────────────────────────────────────────
    aberto = _ch.em_aberto(linhas)
    atrasado = _ch.pendente(linhas, hoje)
    no_mes = _ch.a_vencer(linhas, hoje.year, hoje.month)
    c1, c2, c3 = st.columns(3)
    c1.metric("Em aberto", _brl(aberto), help="tudo que ainda não baixou")
    c2.metric("Pendente", _brl(atrasado),
              delta=f"{len(_ch.vencidos_sem_baixa(linhas, hoje))} cheque(s)",
              delta_color="inverse",
              help="venceu e não baixou. Ou a baixa não foi dada, ou o cheque "
                   "não foi apresentado — nos dois casos é trabalho parado.")
    c3.metric(f"Vence em {hoje.month:02d}/{hoje.year}", _brl(no_mes))

    # As linhas cuja conta não fecha. A planilha é mantida à mão desde 2023, e
    # uma linha fora da soma é erro de digitação lá — o Studio mostra, e não
    # corrige: trocar o número dele pelo meu sem pedir seria inventar dado.
    _tortas = _ch.nao_fecham(linhas)
    if _tortas:
        with st.expander(f"🧮 {len(_tortas)} linha(s) em que valor ≠ envio + "
                         "estoque"):
            st.caption("Vieram assim da planilha. Confira lá — aqui nada foi "
                       "alterado.")
            st.dataframe(
                pd.DataFrame([{
                    "folha": l.get("folha", ""),
                    "vencimento": _ch.data_br(l.get("vencimento")),
                    "valor": _ch._num(l.get("valor")),
                    "envio": _ch._num(l.get("envio")),
                    "estoque": _ch._num(l.get("estoque")),
                    "diferença": _ch.divergencia_da_soma(l),
                } for l in _tortas[:50]]),
                use_container_width=True, hide_index=True,
                column_config=_rot.config(
                    ["folha", "vencimento", "valor", "envio", "estoque",
                     "diferença"], st,
                    tipos={c: "brl" for c in ("valor", "envio", "estoque",
                                              "diferença")}))

    atrasados = _ch.vencidos_sem_baixa(linhas, hoje)
    if atrasados:
        with st.expander(f"⚠️ {len(atrasados)} venceram e não baixaram"):
            st.dataframe(
                pd.DataFrame([{"folha": l.get("folha", ""),
                               "vencimento": _ch.data_br(l.get("vencimento")),
                               "valor": _ch._num(l.get("valor")),
                               "favorecido": l.get("favorecido", "")}
                              for l in atrasados]),
                use_container_width=True, hide_index=True,
                column_config=_rot.config(
                    ["folha", "vencimento", "valor", "favorecido"], st,
                    tipos={"valor": "brl"}))

    # ── cadastrar ────────────────────────────────────────────────────────
    #
    # O resultado do cadastro anterior aparece AQUI, e não lá embaixo: limpar
    # os campos exige recarregar a tela, e o que foi escrito antes do recarregar
    # some junto. Guardar a mensagem e mostrá-la na passada seguinte é o preço
    # de um formulário que não guarda o cheque de ontem.
    _recado = st.session_state.pop("ch_recado", None)
    if _recado:
        st.success(_recado["texto"])
        if _recado.get("tabela"):
            st.dataframe(pd.DataFrame(_recado["tabela"]),
                         use_container_width=True, hide_index=True,
                         column_config=_rot.config(
                             ["folha", "vencimento", "valor", "envio",
                              "estoque"], st,
                             tipos={x: "brl" for x in ("valor", "envio",
                                                       "estoque")}))

    with st.expander("➕ Cadastrar cheque(s) de uma compra", expanded=True):
        # QUANTOS CHEQUES — fora do formulário, de propósito.
        #
        # O número de linhas do formulário depende dele, e dentro de `st.form`
        # o Streamlit só entrega o valor no envio: escolher "3" não desenharia
        # as três linhas até alguém enviar. Aqui ele é um seletor solto, que é
        # seguro — o problema do botão solto era o clique perdido ao lado de
        # uma grade em edição, e não existe grade aqui.
        # A GERAÇÃO DO FORMULÁRIO.
        #
        # Limpar campo por campo significa apagar chave do `session_state` de
        # widget já desenhado — o Streamlit recusa, e o contorno (apagar e
        # recarregar) é frágil: esquece uma chave e o cheque seguinte nasce com
        # o vencimento do anterior, que é justamente o erro a evitar.
        #
        # Aqui o formulário inteiro ganha um número no fim de cada chave. Ao
        # gravar, o número sobe: para o Streamlit são OUTROS widgets, e widget
        # novo nasce no padrão. Nada é apagado, nada fora deste formulário é
        # tocado, e não há chave para esquecer.
        _g = st.session_state.get("ch_geracao", 0)
        if _g:
            # As chaves das gerações passadas não servem mais a widget nenhum —
            # o formulário que as usava não existe. Apagá-las é seguro (não há
            # widget desenhado com elas) e evita que a sessão engorde a cada
            # cadastro. Só as deste formulário, e só as velhas.
            _velhas = [k for k in list(st.session_state.keys())
                       if str(k).startswith(("ch_qtd_", "ch_favorecido_",
                                             "ch_tipo_", "ch_compra_",
                                             "ch_valor_cada_",
                                             "ch_envio_total_",
                                             "ch_situacao_", "ch_obs_",
                                             "ch_folha_", "ch_venc_"))
                       and not str(k).endswith(f"_{_g}")
                       and f"_{_g}_" not in str(k)]
            for _k in _velhas:
                st.session_state.pop(_k, None)

        n = st.number_input(
            "Quantos cheques nesta compra?", min_value=1, max_value=12,
            value=1, step=1, key=f"ch_qtd_{_g}",
            help="Uma compra fechada em vários cheques. Compra, favorecido, "
                 "valor total e envio são os mesmos; folha e vencimento são "
                 "de cada um.")

        with st.form(f"ch_novo_{_g}"):
            st.markdown("**A compra** — vale para todos os cheques")
            f1, f2, f3 = st.columns(3)
            # Nasce preenchido com o favorecido dos cheques, e editável: o
            # dia em que houver cheque para outro nome, basta apagar.
            favorecido = f1.text_input(
                "Favorecido", value=_ch.FAVORECIDO_PADRAO_CHEQUE,
                key=f"ch_favorecido_{_g}",
                help="Cheque vai para a LEXTACK por padrão. Apague e escreva "
                     "outro se for o caso.")
            tipo = f2.selectbox("Tipo", _ch.TIPOS, key=f"ch_tipo_{_g}")
            compra = f3.date_input("Data da compra", value=hoje,
                                   format="DD/MM/YYYY", key=f"ch_compra_{_g}")
            g1, g2, g3 = st.columns(3)
            # O VALOR É O DE UM CHEQUE, e não o da compra.
            #
            # O talão sai com dois de R$ 1.495,84, e não com um de R$ 2.991,68.
            # Pedir o total obrigaria a somar de cabeça antes de digitar —
            # conta que ninguém precisa fazer, e que erra em silêncio quando são
            # cinco cheques.
            valor_cada = g1.number_input(
                "Valor de CADA cheque (R$)", min_value=0.0, step=100.0,
                format="%.2f", key=f"ch_valor_cada_{_g}",
                help="Todos os cheques da compra saem com este valor. A compra "
                     "é a soma, e quem soma é o Studio.")
            envio_total = g2.number_input(
                "ENVIO total da compra (R$)", min_value=0.0, step=50.0,
                format="%.2f", key=f"ch_envio_total_{_g}",
                help="Um número só da compra inteira, repartido entre os "
                     "cheques. É a parte que a plataforma devolve com data "
                     "marcada.")
            situacao = g3.selectbox("Situação", _ch.SITUACOES, key=f"ch_situacao_{_g}")

            # ESTOQUE não é campo: é valor − envio, e o dono só quer digitar
            # o envio. O Studio calcula e guarda; nada mais depende dele.
            st.caption("**Estoque = valor − envio**, calculado ao cadastrar.")

            st.markdown(f"**Os {int(n)} cheque(s)** — folha e vencimento de cada")
            folhas, vencs = [], []
            for _i in range(int(n)):
                c1, c2 = st.columns([1, 2])
                folhas.append(c1.text_input(
                    f"Folha do {_i + 1}º", key=f"ch_folha_{_g}_{_i}"))
                vencs.append(c2.date_input(
                    f"Vencimento do {_i + 1}º", value=hoje,
                    format="DD/MM/YYYY", key=f"ch_venc_{_g}_{_i}"))

            obs = st.text_input("Observação (vale para todos)",
                                key=f"ch_obs_{_g}")
            criar = st.form_submit_button("💾 Cadastrar", type="primary",
                                          use_container_width=True)

        if criar:
            # FOLHA REPETIDA NÃO ENTRA, E O STUDIO DIZ QUAL.
            #
            # O número do talão é único: é ele que o banco debita. Dois
            # registros com a mesma folha contam o mesmo dinheiro duas vezes no
            # comprometido do mês, e a baixa dada num deixa o outro em aberto
            # para sempre.
            #
            # `gravar` já descartava a repetida — a folha é a identidade —, mas
            # EM SILÊNCIO, devolvendo só uma contagem. Quem cadastrava quatro
            # cheques e errava um número via "cadastrados" e ia embora, sem
            # saber qual ficou de fora. Recusar sem dizer o número é quase tão
            # ruim quanto aceitar.
            _repetidas_no_lote = _ch.folhas_repetidas_na_lista(folhas)
            _ja_na_carteira = _ch.folhas_ja_cadastradas(folhas, linhas=linhas)

            if not valor_cada:
                st.error("Cheque sem valor não entra — seriam linhas que "
                         "ocupam lugar e não contam nada.")
            elif _repetidas_no_lote:
                st.error(
                    "Você repetiu a folha "
                    + ", ".join(f"**{f}**" for f in _repetidas_no_lote)
                    + " dentro deste mesmo cadastro. Cada cheque tem o seu "
                      "número — confira o talão antes de cadastrar.")
            elif _ja_na_carteira:
                _linhas_erro = []
                for _f, _l in _ja_na_carteira.items():
                    _linhas_erro.append(
                        f"- Folha **{_f}** já está cadastrada: "
                        f"{_ch.data_br(_l.get('vencimento')) or 'sem vencimento'}"
                        f", {_brl(_ch._num(_l.get('valor')))}"
                        + (f", {_l.get('favorecido')}" if _l.get("favorecido")
                           else "")
                        + f" — {_ch.situacao_de(_l.get('situacao'))}")
                st.error(_rot.tela(
                    "Não cadastrei: já existe cheque com esse número.\n\n"
                    + "\n".join(_linhas_erro)
                    + "\n\nSe o número estiver errado aqui, corrija. Se o "
                      "errado for o que já está na carteira, corrija a folha "
                      "lá embaixo — ela abre para edição."))
            else:
                # ENVIO MAIOR QUE A COMPRA NÃO É ERRO — E BLOQUEAVA.
                #
                # Parte da compra sai no PIX ou no cartão e o resto em cheque.
                # O cheque pode cobrir só uma fatia, e o ENVIO da compra
                # inteira passar da soma dos cheques. Isto era um `st.error`
                # com `elif`: o caso real do dono não entrava no Studio de
                # jeito nenhum.
                #
                # Os dados dele já provavam que o caso existe — há cheque
                # importado da planilha com estoque −629,91, gravado e válido.
                # Bloquear o que a própria fonte já contém é o Studio
                # discordando do dono sobre o negócio dele.
                #
                # Vira aviso: o Studio diz o que notou, e cadastra.
                if envio_total > valor_cada * int(n):
                    st.info(
                        _rot.tela(
                            f"O envio ({_brl(envio_total)}) passa da soma dos "
                            f"cheques ({_brl(valor_cada * int(n))}). Cadastrei "
                            f"assim mesmo — é o caso de parte da compra ter "
                            f"saído no PIX ou no cartão. O estoque fica "
                            f"negativo, e é essa a leitura: este cheque cobre "
                            f"menos envio do que a compra tem."))
                cheques_do_lote = _ch.lote(
                    {"favorecido": _ch.favorecido_do_tipo(tipo, favorecido),
                     "tipo": tipo, "compra": compra,
                     "situacao": situacao, "observacao": obs},
                    folhas, vencs, valor_cada, envio_total)
                novas, repetidas, erro = _ch.gravar(cheques_do_lote,
                                                    usuario_logado)
                if erro:
                    st.error(f"Não consegui gravar: {erro}")
                elif not novas:
                    st.warning("Todos já estavam cadastrados — nada mudou.")
                else:
                    _v = cheques_do_lote[0]["valor"]
                    _e = cheques_do_lote[0]["envio"]
                    _soma = round(sum(c["valor"] for c in cheques_do_lote), 2)
                    # O recado viaja para a próxima passada da tela, porque a
                    # próxima passada é a que limpa os campos.
                    st.session_state["ch_recado"] = {
                        "texto": (
                            f"{novas} cheque(s) cadastrado(s)"
                            + (f" · {repetidas} já existia(m)" if repetidas
                               else "")
                            + f"\n\nCada um: {_brl(_v)} · envio {_brl(_e)} · "
                            f"estoque {_brl(round(_v - _e, 2))}"
                            + f"\n\nCompra: {_brl(_soma)} = {novas} × "
                            f"{_brl(_v)}"),
                        "tabela": [{
                            "folha": c["folha"],
                            "vencimento": _ch.data_br(c["vencimento"]),
                            "valor": c["valor"], "envio": c["envio"],
                            "estoque": round(c["valor"] - c["envio"], 2),
                        } for c in cheques_do_lote],
                    }
                    # O FORMULÁRIO LIMPA AQUI, e em uma linha.
                    #
                    # A geração sobe, todas as chaves mudam, e para o Streamlit
                    # o formulário seguinte é outro — nasce no padrão. Sem
                    # apagar chave nenhuma, sem tocar em nada fora daqui, e sem
                    # chave para esquecer.
                    #
                    # Isso importa porque o erro que ele evita não é digitar
                    # errado: é ESQUECER de mudar. Um vencimento que ficou do
                    # cheque passado entra certo na tela e errado no mês.
                    st.session_state["ch_geracao"] = _g + 1
                    st.rerun()

    if not linhas:
        return

    # ── a carteira ───────────────────────────────────────────────────────
    st.markdown("##### A carteira")
    sit = sorted({_ch.situacao_de(l.get("situacao")) for l in linhas})
    s1, s2 = st.columns([2, 1])
    filtro = s1.multiselect("Situação", sit, default=["EM ABERTO"]
                            if "EM ABERTO" in sit else sit, key="ch_filtro")
    so_ano = s2.number_input("Ano do vencimento", 2020, 2100, hoje.year, 1,
                             key="ch_ano")
    vis = [l for l in linhas
           if _ch.situacao_de(l.get("situacao")) in (filtro or sit)
           and _ch.texto_data(l.get("vencimento")).startswith(str(so_ano))]
    if not vis:
        st.caption("Nenhum cheque com esses filtros.")
        return

    # NA SEQUÊNCIA DO TALÃO, e não por vencimento: é a ordem em que os
    # cheques saem e em que o dono confere.
    vis.sort(key=_ch.ordem_da_folha)
    df = pd.DataFrame([{
        "id": l.get("id"),
        "folha": str(l.get("folha", "") or ""),
        # A DATA DA COMPRA. Ela era gravada desde sempre (`cheques.COLUNAS`) e
        # preenchida no cadastro (`ch_compra_`), mas não aparecia em lugar
        # nenhum depois — o dono cadastrava e nunca mais via. Dado que se
        # escreve e não se lê é dado que ninguém confere.
        # Na tela, DD/MM/AAAA — o formato em que o dono digita. O gravado
        # continua AAAA-MM-DD (`_ch.texto_data`), que é o que ordena e o que a
        # identidade usa; o que muda é só o que se lê.
        "compra": _ch.data_br(l.get("compra")),
        "vencimento": _ch.data_br(l.get("vencimento")),
        "valor": _ch._num(l.get("valor")),
        "envio": _ch._num(l.get("envio")),
        "estoque": _ch._num(l.get("estoque")),
        "favorecido": str(l.get("favorecido", "") or ""),
        "situação": _ch.situacao_de(l.get("situacao")),
        "apagar": False,
    } for l in vis])

    with st.form("ch_grade"):
        editado = st.data_editor(
            df, use_container_width=True, hide_index=True, key="ch_ed",
            column_config={
                **_rot.config(
                    ["folha", "compra", "vencimento", "valor", "envio",
                     "estoque", "favorecido", "situação", "apagar"], st,
                    tipos={"valor": "brl", "envio": "brl", "estoque": "brl"}),
                "id": None,
                # A FOLHA ABRE. Ela estava travada porque é a identidade do
                # cheque — mas travar o campo não protege a identidade, só
                # impede de consertar. O dono cadastrou um lote sem o número
                # do talão em mãos e ficou sem caminho nenhum para incluí-lo:
                # editar era impossível, e apagar perderia a linha.
                #
                # O `id` da linha não muda ao salvar (`_ch.atualizar` escreve
                # campos, não reescreve o id), então preencher a folha aqui
                # corrige o cadastro sem mexer em quem a linha é.
                "folha": st.column_config.TextColumn(
                    _rot.rotular("folha"), width="small",
                    help="O número do talão. Dá para preencher depois, se ele "
                         "não estava em mãos na hora do cadastro."),
                # Vencimento, valor e envio ABREM para edição: cheque
                # cadastrado com a data errada tem de ser corrigido aqui, e não
                # apagado e digitado de novo — apagar perde a baixa e o
                # histórico da linha.
                # Compra e vencimento ABREM juntos, e pela mesma razão: data
                # errada se corrige aqui, não se apaga a linha e digita de novo.
                "compra": st.column_config.TextColumn(
                    "Compra", width="small",
                    help="Data da compra. AAAA-MM-DD ou DD/MM/AAAA."),
                "vencimento": st.column_config.TextColumn(
                    "Vencimento", width="small",
                    help="AAAA-MM-DD ou DD/MM/AAAA. O Studio entende os dois."),
                "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f",
                                                       min_value=0.0),
                "envio": st.column_config.NumberColumn("Envio", format="R$ %.2f",
                                                       min_value=0.0),
                # O estoque continua travado: ele é conta, não campo.
                # Leitura: ele é conta, e muda sozinho quando o valor ou o
                # envio mudam.
                "estoque": st.column_config.NumberColumn(
                    "Estoque", format="R$ %.2f", disabled=True,
                    help="valor − envio, recalculado ao salvar"),
                "favorecido": st.column_config.TextColumn("Favorecido",
                                                          width="medium"),
                "situação": st.column_config.SelectboxColumn(
                    "Situação", options=list(_ch.SITUACOES), width="small",
                    help="Dar baixa aqui tira o cheque do comprometido do mês. "
                         "O extrato faz isso sozinho quando o débito aparece."),
                "apagar": st.column_config.CheckboxColumn(
                    "🗑️", help="Marque e salve para remover a linha."),
            })
        gravar = st.form_submit_button("💾 Salvar alterações", type="primary",
                                       use_container_width=True)

    if gravar:
        antes = {l["id"]: l for l in vis}
        mudou, erros = 0, []
        apagar = [r["id"] for _, r in editado.iterrows() if r["apagar"]]
        for _, r in editado.iterrows():
            if r["apagar"]:
                continue
            a = antes.get(r["id"], {})
            campos = {}
            if _ch.situacao_de(a.get("situacao")) != r["situação"]:
                campos["situacao"] = r["situação"]
            if str(a.get("favorecido", "") or "") != str(r["favorecido"] or ""):
                campos["favorecido"] = str(r["favorecido"] or "")

            _folha_nova = _ch.texto_folha(r["folha"])[:20]
            if _folha_nova != _ch.texto_folha(a.get("folha")):
                # A MESMA REGRA DO CADASTRO, aqui também. Abrir a folha para
                # edição sem esta conferência seria abrir a porta que o
                # cadastro acabou de fechar.
                _colide = _ch.folhas_ja_cadastradas(
                    [_folha_nova], ignorando_id=r["id"], linhas=linhas)
                if _colide:
                    erros.append(
                        f"Folha {_folha_nova} já é de outro cheque — o da "
                        f"linha com vencimento "
                        f"{_ch.data_br(_colide[_folha_nova].get('vencimento'))}"
                        f". Nada foi alterado nesta linha.")
                    continue
                campos["folha"] = _folha_nova

            # Data digitada que o Studio não entende NÃO vira data vazia: a
            # linha é recusada com o número da folha, e o resto da grade salva
            # normalmente. Gravar "" aqui tiraria o cheque do mês sem aviso.
            # A compra passa pela MESMA peneira do vencimento. Escrever a
            # recusa só para um dos dois campos de data seria consertar metade:
            # data que o Studio não entende viraria data VAZIA na planilha, sem
            # ninguém avisado.
            _compra_nova = _ch.texto_data(r["compra"])
            if str(r["compra"] or "").strip() and not _compra_nova:
                erros.append(
                    f"Cheque {a.get('folha') or '(sem folha)'}: não entendi a "
                    f"data da compra «{r['compra']}» — use 02/10/2026 ou "
                    f"2026-10-02.")
                continue
            if _compra_nova != _ch.texto_data(a.get("compra")):
                campos["compra"] = _compra_nova

            _venc_novo = _ch.texto_data(r["vencimento"])
            if str(r["vencimento"] or "").strip() and not _venc_novo:
                erros.append(
                    f"Cheque {a.get('folha') or '(sem folha)'}: não entendi a "
                    f"data «{r['vencimento']}» — use 02/10/2026 ou 2026-10-02.")
                continue
            if _venc_novo and _venc_novo != _ch.texto_data(a.get("vencimento")):
                campos["vencimento"] = _venc_novo

            _v_novo = round(float(r["valor"] or 0), 2)
            _e_novo = round(float(r["envio"] or 0), 2)
            _mudou_dinheiro = (_v_novo != round(_ch._num(a.get("valor")), 2)
                               or _e_novo != round(_ch._num(a.get("envio")), 2))
            if _mudou_dinheiro:
                campos["valor"] = _v_novo
                campos["envio"] = _e_novo
                # O estoque acompanha, sempre: ele é valor − envio, e deixá-lo
                # com o número antigo faria a linha parar de fechar.
                campos["estoque"] = round(_v_novo - _e_novo, 2)

            if not campos:
                continue
            ok, msg = _ch.atualizar(r["id"], campos, usuario_logado)
            mudou += ok
            if not ok:
                erros.append(msg)
        n_apagados, erro_ap = (_ch.apagar(apagar) if apagar else (0, ""))
        if erros or erro_ap:
            st.error(" · ".join(erros + ([erro_ap] if erro_ap else [])))
        if mudou or n_apagados:
            st.success(f"{mudou} alterado(s)"
                       + (f" · {n_apagados} apagado(s)" if n_apagados else ""))
            _atual = _ch.carregar()
            st.caption(
                f"Agora: em aberto {_brl(_ch.em_aberto(_atual))} · pendente "
                f"{_brl(_ch.pendente(_atual, hoje))}")
        elif not erros and not erro_ap:
            st.info("Nada mudou.")
