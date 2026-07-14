import streamlit as st


def verificar_login():
    """Tela de login usando os usuarios definidos nas Secrets do Streamlit
    (bloco [usuarios], no formato usuario = "senha"). Bloqueia o app inteiro
    ate logar. Retorna o nome do usuario logado assim que autenticado."""
    if "usuario_logado" in st.session_state:
        return st.session_state["usuario_logado"]

    usuarios = dict(st.secrets.get("usuarios", {}))

    st.title("MartinSousa App")
    st.subheader("Login")

    if not usuarios:
        st.warning("Nenhum usuário configurado ainda nas Secrets do Streamlit (bloco [usuarios]).")
        st.stop()

    with st.form("login_form"):
        login = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        entrar = st.form_submit_button("Entrar", type="primary", use_container_width=True)

    if entrar:
        if usuarios.get(login) == senha:
            st.session_state["usuario_logado"] = login
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos.")

    st.stop()
