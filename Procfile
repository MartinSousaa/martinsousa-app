web: mkdir -p .streamlit && printf '%s' "$STREAMLIT_SECRETS" > .streamlit/secrets.toml && python prestart.py && streamlit run app.py --server.port $PORT --server.address 0.0.0.0
