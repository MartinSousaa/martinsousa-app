import streamlit as st
import hashlib
from datetime import datetime
import auth


def _hash(senha):
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


def _criar_usuario(login, senha, eh_admin):
    aba = auth._aba_usuarios()
    aba.append_row(
        [login, _hash(senha), "Sim", "Sim" if eh_admin else "Não",
         datetime.now().strftime("%d/%m/%Y %H:%M")],
        value_input_option="RAW",
    )


def _atualizar_campo(login, campo, valor):
    """Atualiza uma célula específica na linha do usuário."""
    aba = auth._aba_usuarios()
    cabecalho = aba.row_values(1)
    if campo not in cabecalho:
        return
    col_idx = cabecalho.index(campo) + 1  # 1-based
    registros = aba.get_all_records(value_render_option="UNFORMATTED_VALUE")
    for i, reg in enumerate(registros):
        if str(reg.get("login", "")) == login:
            aba.update_cell(i + 2, col_idx, valor)  # +2: linha 1 é cabeçalho
            return


def pagina_admin(usuario_logado):
    # eh_gestor, nao is_admin: a coluna `admin` da planilha e editavel daqui
    # dentro. Se ela desse entrada, quem entrasse uma vez poderia se promover.
    if not auth.eh_gestor(usuario_logado):
        st.error("Acesso restrito a administradores.")
        return

    # ── CONFIRMAÇÃO DE SENHA (segunda camada de segurança) ────────────────────
    chave = f"admin_confirmado_{usuario_logado}"
    if not st.session_state.get(chave):
        st.markdown("### 🔒 Confirmação necessária")
        st.caption("Digite sua senha para acessar a área administrativa.")
        with st.form("form_confirm_admin"):
            senha_confirm = st.text_input("Sua senha", type="password")
            ok_btn = st.form_submit_button("Confirmar", type="primary")
        if ok_btn:
            autenticado, _ = auth._verificar_credencial(usuario_logado, senha_confirm)
            if autenticado:
                st.session_state[chave] = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
        return

    st.subheader("Administrativo — Gestão de Usuários")

    # ── USUÁRIOS DAS SECRETS (somente leitura) ────────────────────────────────
    usuarios_secrets = dict(st.secrets.get("usuarios", {}))
    if usuarios_secrets:
        st.markdown("##### Usuários fixos (Secrets do Streamlit)")
        st.caption("Esses usuários só podem ser alterados no painel do Railway. "
                   "Estar aqui dá acesso ao Studio — **não** dá perfil de gestor.")
        import pandas as pd
        # O perfil e LIDO, nao presumido.
        #
        # Esta tabela dizia "Admin" para todo mundo das Secrets, e a legenda
        # afirmava "Todos tem perfil Admin". Era verdade ate a separacao entre
        # cadastro e perfil; depois dela, virou a tela mentindo sobre quem pode
        # o que — justamente na tela onde se confere isso.
        df_sec = pd.DataFrame([
            {"login": u,
             "perfil": "Gestor" if auth.eh_gestor(u) else "Colaborador",
             "origem": "Secrets", "ativo": "Sim"}
            for u in usuarios_secrets
        ])
        st.dataframe(df_sec, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── USUÁRIOS DO SHEETS ────────────────────────────────────────────────────
    st.markdown("##### Usuários gerenciados pelo app")

    df = auth._carregar_usuarios_sheets()
    tem_usuarios_sheets = not df.empty and "login" in df.columns and len(df) > 0

    if tem_usuarios_sheets:
        colunas_ver = [c for c in ["login", "ativo", "admin", "criado_em"] if c in df.columns]
        st.dataframe(df[colunas_ver], use_container_width=True, hide_index=True)

        st.markdown("##### Gerenciar usuário existente")
        logins_sheets = df["login"].astype(str).tolist()
        usuario_sel = st.selectbox("Selecionar usuário", logins_sheets, key="admin_sel_usuario")

        row_sel = df[df["login"].astype(str) == usuario_sel].iloc[0] if tem_usuarios_sheets else None
        ativo_atual = str(row_sel.get("ativo", "Sim")).lower() in ("sim", "true", "1", "yes", "ativo") if row_sel is not None else True
        admin_atual = str(row_sel.get("admin", "Não")).lower() in ("sim", "true", "1", "yes") if row_sel is not None else False

        col_a, col_b, col_c = st.columns(3)

        # Ativar / Desativar
        if ativo_atual:
            if col_a.button("🔴 Desativar acesso", use_container_width=True, key="btn_desativar"):
                _atualizar_campo(usuario_sel, "ativo", "Não")
                auth._carregar_usuarios_sheets.clear()
                st.success(f"Usuário '{usuario_sel}' desativado.")
                st.rerun()
        else:
            if col_a.button("🟢 Reativar acesso", use_container_width=True, key="btn_reativar"):
                _atualizar_campo(usuario_sel, "ativo", "Sim")
                auth._carregar_usuarios_sheets.clear()
                st.success(f"Usuário '{usuario_sel}' reativado.")
                st.rerun()

        # Promover / Rebaixar admin
        if admin_atual:
            if col_b.button("👤 Remover Admin", use_container_width=True, key="btn_rm_admin"):
                _atualizar_campo(usuario_sel, "admin", "Não")
                auth._carregar_usuarios_sheets.clear()
                # is_admin fica fixado por sessão — invalida para refletir a mudança
                st.session_state.pop(f"_perfil_admin__{usuario_sel}", None)
                st.success(f"'{usuario_sel}' não é mais admin.")
                st.rerun()
        else:
            if col_b.button("⭐ Tornar Admin", use_container_width=True, key="btn_mk_admin"):
                _atualizar_campo(usuario_sel, "admin", "Sim")
                auth._carregar_usuarios_sheets.clear()
                # is_admin fica fixado por sessão — invalida para refletir a mudança
                st.session_state.pop(f"_perfil_admin__{usuario_sel}", None)
                st.success(f"'{usuario_sel}' agora é admin.")
                st.rerun()

        # Reset de senha
        with col_c.popover("🔑 Resetar senha", use_container_width=True):
            nova_senha_reset = st.text_input("Nova senha", type="password", key="reset_senha_input")
            confirmar_reset = st.text_input("Confirmar", type="password", key="reset_senha_conf")
            if st.button("Confirmar reset", key="btn_confirmar_reset"):
                if not nova_senha_reset:
                    st.warning("Digite a nova senha.")
                elif nova_senha_reset != confirmar_reset:
                    st.error("As senhas não conferem.")
                else:
                    _atualizar_campo(usuario_sel, "senha_hash", _hash(nova_senha_reset))
                    auth._carregar_usuarios_sheets.clear()
                    st.success(f"Senha de '{usuario_sel}' redefinida.")
                    st.rerun()
    else:
        st.info("Nenhum usuário cadastrado pelo app ainda. Crie o primeiro abaixo.")

    st.markdown("---")

    # ── CRIAR NOVO USUÁRIO ────────────────────────────────────────────────────
    st.markdown("##### Criar novo usuário")

    with st.form("form_novo_usuario", clear_on_submit=True):
        col1, col2 = st.columns(2)
        novo_login = col1.text_input("Login", placeholder="ex: colaborador1")
        nova_senha = col2.text_input("Senha", type="password")
        col3, col4 = st.columns(2)
        confirmar_senha = col3.text_input("Confirmar senha", type="password")
        eh_admin = col4.checkbox("Perfil administrador")
        criar = st.form_submit_button("✅ Criar usuário", type="primary", use_container_width=True)

    if criar:
        erros = []
        if not novo_login:
            erros.append("Informe o login.")
        if not nova_senha:
            erros.append("Informe a senha.")
        elif nova_senha != confirmar_senha:
            erros.append("As senhas não conferem.")
        if novo_login in dict(st.secrets.get("usuarios", {})):
            erros.append(f"O login '{novo_login}' já existe nas Secrets do sistema.")
        if tem_usuarios_sheets and novo_login in df["login"].astype(str).tolist():
            erros.append(f"Já existe um usuário com o login '{novo_login}'.")

        if erros:
            for e in erros:
                st.error(e)
        else:
            _criar_usuario(novo_login, nova_senha, eh_admin)
            auth._carregar_usuarios_sheets.clear()
            perfil = "Admin" if eh_admin else "Colaborador"
            st.success(f"Usuário **{novo_login}** criado com perfil {perfil}!")
            st.rerun()

    # ── DIAGNÓSTICO DO GOOGLE DRIVE ──────────────────────────────────────────
    st.markdown("---")
    # ── Explorador da API da RHiD ─────────────────────────────────────────────
    # A pontualidade depende das marcações do dia, e a apuração não as devolve —
    # traz totais e o horário contratual. Este painel pergunta à própria API
    # quais caminhos existem, em vez de eu ficar adivinhando nomes de campo.
    with st.expander("🔎 Explorar a API da RHiD (achar as marcações de ponto)"):
        st.caption(
            "A apuração devolve totais, não as batidas. Isto testa os caminhos "
            "conhecidos e mostra o que cada um responde — a saída me diz qual usar."
        )
        if st.button("Testar caminhos da RHiD", key="rhid_explorar"):
            import rhid_api as _ra
            from datetime import date as _d, timedelta as _td
            _fim = _d.today()
            _ini = _fim - _td(days=7)

            with st.spinner("Consultando a RHiD..."):
                _pessoas = _ra.get_persons()
                if not _pessoas:
                    st.error("Não consegui listar colaboradores na RHiD.")
                else:
                    _p = _pessoas[0]
                    _idp = (_p.get("id") or _p.get("idPerson")
                            or _p.get("personId") or _p.get("codigo"))
                    _nome = (_p.get("name") or _p.get("nome") or "?")
                    st.caption(f"Testando com **{_nome}** (id {_idp}), "
                               f"{_ini.strftime('%d/%m')} a {_fim.strftime('%d/%m')}")
                    _res = _ra.explorar_endpoints(_ini.isoformat(), _fim.isoformat(), int(_idp))

            _uteis = [r for r in _res if r.get("campos_com_hora")]
            if _uteis:
                st.success(f"{len(_uteis)} caminho(s) devolveram horários:")
                for r in _uteis:
                    st.markdown(f"**{r['endpoint']}** — status {r['status']} · "
                                f"{r['registros']} registro(s)")
                    st.code("\n".join(r["campos_com_hora"]))
            else:
                st.warning("Nenhum caminho devolveu horário. Resumo do que respondeu:")

            _linhas = [
                f"{r['endpoint']:26} status={r['status']} "
                f"tipo={r['tipo'] or '—'} registros={r['registros']}"
                + (f"  campos: {r['amostra'][:160]}" if r.get("amostra") else "")
                for r in _res
            ]
            st.code("\n".join(_linhas))
            st.caption("Copie este bloco e me mande — com ele eu fecho a pontualidade.")

    st.markdown("---")
    st.markdown("#### 🔧 Diagnóstico do Google Drive")
    st.caption(
        "Verifica se o sistema consegue gravar arquivos no Drive. "
        "Use quando aparecer erro ao salvar fotos de triagem ou imagens geradas."
    )

    if st.button("Testar conexão com o Drive", use_container_width=True):
        import gdrive
        with st.spinner("Testando gravação no Drive..."):
            rel = gdrive.diagnostico()

        rotulo_modo = {
            "oauth": "OAuth (refresh token) — usa a cota de uma conta Google real",
            "impersonation": f"Impersonation — agindo como {rel['impersonando']}",
            "service_account": "Conta de serviço pura — SEM cota de armazenamento",
        }.get(rel["modo"], rel["modo"])

        col_a, col_b = st.columns(2)
        col_a.markdown(f"**Modo de credencial**  \n{rotulo_modo}")
        col_b.markdown(
            f"**Pasta de destino**  \n"
            f"{rel['pasta_nome'] or '(não encontrada)'}  \n"
            f"{'✅ Unidade Compartilhada' if rel['shared_drive'] else '⚠️ Meu Drive (pasta pessoal)'}"
        )
        st.caption(f"Conta de serviço: `{rel['conta']}`")

        if rel["escrita_ok"]:
            st.success("✅ Gravação no Drive funcionando — upload de teste concluído e removido.")
            if not rel["publico_ok"]:
                st.warning(
                    "⚠️ O arquivo foi salvo, mas não pôde ser tornado público. "
                    "Os thumbnails do seletor de variante não vão aparecer. "
                    "Verifique se o compartilhamento externo está liberado no Workspace."
                )
        else:
            st.error(f"❌ Gravação falhou.\n\n{rel['erro']}")
            if rel["modo"] == "service_account" and not rel["shared_drive"]:
                st.info(
                    "**Como resolver** — escolha um dos caminhos:\n\n"
                    "1. **Unidade Compartilhada** (Workspace Business Standard+): crie uma "
                    "unidade compartilhada, adicione a conta de serviço acima como *Gerente de conteúdo*, "
                    "mova a pasta de imagens para dentro dela e atualize `DRIVE_PASTA_IMAGENS_ID`.\n\n"
                    "2. **Impersonation** (Workspace + Admin Console): ative a delegação em todo o domínio "
                    "para a conta de serviço com o escopo `https://www.googleapis.com/auth/drive` e "
                    "adicione a secret `GDRIVE_IMPERSONATE_USER` com seu e-mail.\n\n"
                    "3. **OAuth** (funciona até com Gmail comum): configure o bloco de secret "
                    "`[gdrive_oauth]` com `client_id`, `client_secret` e `refresh_token`."
                )

    # ── ASSISTENTE DE OAUTH DO DRIVE ─────────────────────────────────────────
    # O OAuth exige um consentimento humano no navegador — ninguém pode autorizar
    # acesso ao Drive de outra pessoa, e é exatamente isso que ele protege. O que
    # dá para automatizar é o resto: montar a URL de autorização com os parâmetros
    # certos e trocar o código pelo refresh_token. Feito à mão, é aí que se erra
    # (falta access_type=offline, falta prompt=consent, escopo errado) e o token
    # volta sem refresh — funcionando por uma hora e quebrando depois.
    st.markdown("---")
    st.markdown("#### 🔑 Assistente de configuração do OAuth do Drive")
    st.caption(
        "Gera o refresh_token que falta para o sistema gravar no Drive. "
        "Use uma vez; depois é só colar o resultado no Railway."
    )

    with st.expander("Abrir assistente", expanded=False):
        st.markdown(
            "**Antes de começar**, no `console.cloud.google.com` (projeto `martinsousa-app`):\n\n"
            "1. **APIs e serviços → Biblioteca** → ative a **Google Drive API**\n"
            "2. **Tela de permissão OAuth** → tipo **Externo** → preencha o básico → "
            "**PUBLICAR APLICATIVO** (se ficar em *Teste*, o token expira em 7 dias)\n"
            "3. **Clientes → Criar cliente** → tipo **App para computador**\n\n"
            "O tipo *App para computador* evita ter que verificar a posse do domínio "
            "no Search Console, exigência do tipo *Aplicativo da Web*. Ele usa "
            "`http://localhost` como redirecionamento, que é o valor abaixo."
        )
        _redirect = st.text_input(
            "URI de redirecionamento (cole este valor no Google Cloud Console)",
            value="http://localhost",
            key="oauth_redirect",
        )

        st.markdown("---")
        _cid = st.text_input("client_id", key="oauth_cid",
                             placeholder="...apps.googleusercontent.com")
        _csec = st.text_input("client_secret", key="oauth_csec", type="password")

        if _cid and _csec:
            from urllib.parse import urlencode as _urlencode
            _params = _urlencode({
                "client_id": _cid.strip(),
                "redirect_uri": _redirect.strip(),
                "response_type": "code",
                "scope": "https://www.googleapis.com/auth/drive",
                # Sem estes dois o Google devolve só um token de 1 hora, sem
                # refresh_token — o erro mais comum neste fluxo.
                "access_type": "offline",
                "prompt": "consent",
            })
            _url_auth = f"https://accounts.google.com/o/oauth2/v2/auth?{_params}"
            # target="_blank": na mesma aba, o Google substituiria esta pagina e
            # os campos preenchidos se perderiam no meio do processo.
            st.markdown(
                f'**Passo 1 —** <a href="{_url_auth}" target="_blank">'
                f'Clique aqui para autorizar no Google (abre em nova aba)</a>',
                unsafe_allow_html=True,
            )
            st.caption(
                "Entre com a conta dona do Drive → em \"o Google não verificou este "
                "app\" clique em Avançado → Acessar → Permitir. A página seguinte vai "
                "falhar (\"localhost recusou a conexão\") — isso é o esperado. O que "
                "importa está na barra de endereço: copie o trecho entre `code=` e `&scope`."
            )
            st.markdown("**Passo 2 —** cole aqui o valor do `code` que apareceu na URL:")
            _codigo = st.text_input("code", key="oauth_code")

            # Sem `disabled=`: a condicao dependia de o Streamlit ter confirmado o
            # campo de texto, e em producao o botao ficava apagado com o codigo
            # ja colado — sem o colaborador ter como saber por que. Agora o botao
            # esta sempre ativo e a validacao acontece ao clicar.
            if st.button("Gerar refresh_token", type="primary",
                         use_container_width=True):
                if not _codigo.strip():
                    st.warning("Cole o `code` no campo acima antes de gerar.")
                    st.stop()
                import requests as _rq
                with st.spinner("Trocando o código pelo token..."):
                    try:
                        _r = _rq.post(
                            "https://oauth2.googleapis.com/token",
                            data={
                                "code": _codigo.strip(),
                                "client_id": _cid.strip(),
                                "client_secret": _csec.strip(),
                                "redirect_uri": _redirect.strip(),
                                "grant_type": "authorization_code",
                            },
                            timeout=30,
                        )
                        _dados = _r.json()
                    except Exception as _e_tok:
                        _dados = {"error": "falha_rede", "error_description": str(_e_tok)}

                _refresh = _dados.get("refresh_token", "")
                if _refresh:
                    st.success("✅ Token gerado. Copie o bloco abaixo.")
                    st.markdown(
                        "**Passo 3 —** no **Railway → Variables**, cole isto nas secrets "
                        "e aguarde o redeploy:"
                    )
                    st.code(
                        '[gdrive_oauth]\n'
                        f'client_id = "{_cid.strip()}"\n'
                        f'client_secret = "{_csec.strip()}"\n'
                        f'refresh_token = "{_refresh}"',
                        language="toml",
                    )
                    st.info(
                        "Depois do redeploy, volte aqui e rode **Testar conexão com o "
                        "Drive**. O modo deve aparecer como *OAuth* e a gravação em verde."
                    )
                    st.warning(
                        "Esse refresh_token dá acesso de escrita ao seu Drive. Cole no "
                        "Railway e não deixe cópia em documento, e-mail ou conversa."
                    )
                elif _dados.get("error"):
                    _desc = _dados.get("error_description", "")
                    st.error(f"❌ {_dados['error']}: {_desc}")
                    if _dados["error"] == "invalid_grant":
                        st.info(
                            "O código só vale uma vez e expira em minutos. Refaça o "
                            "Passo 1 e cole um código novo."
                        )
                    elif _dados["error"] == "redirect_uri_mismatch":
                        st.info(
                            "A URI de redirecionamento aqui e a cadastrada no Google "
                            "Cloud Console precisam ser idênticas — inclusive a barra "
                            "no final."
                        )
                else:
                    st.error(
                        "O Google respondeu sem refresh_token. Isso acontece quando a "
                        "conta já autorizou este app antes. Remova o acesso em "
                        "myaccount.google.com/permissions e refaça o Passo 1."
                    )
