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
    if not auth.is_admin(usuario_logado):
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
        st.caption("Esses usuários só podem ser alterados no painel do Streamlit Cloud. Todos têm perfil Admin.")
        import pandas as pd
        df_sec = pd.DataFrame([
            {"login": u, "perfil": "Admin", "origem": "Secrets", "ativo": "Sim"}
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
                st.success(f"'{usuario_sel}' não é mais admin.")
                st.rerun()
        else:
            if col_b.button("⭐ Tornar Admin", use_container_width=True, key="btn_mk_admin"):
                _atualizar_campo(usuario_sel, "admin", "Sim")
                auth._carregar_usuarios_sheets.clear()
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
