"""
Registra a rota /app/tv no servidor Tornado interno do Streamlit,
servindo o painel TV com Content-Type: text/html correto.

Sem threads de background — o registro é feito diretamente
na thread de execução do Streamlit (seguro).
"""
import os
import threading
import tornado.web

TV_TOKEN = "msstudio2025tv"
_registered = False
_lock = threading.Lock()


class TVPageHandler(tornado.web.RequestHandler):
    def get(self):
        token = self.get_argument("token", "")
        if token != TV_TOKEN:
            self.set_status(403)
            self.finish("Acesso negado")
            return

        static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
        tv_path = os.path.join(static_dir, "tv.html")

        try:
            with open(tv_path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            self.set_status(404)
            self.finish("Painel TV ainda nao gerado. Abra o Placar primeiro.")
            return
        except Exception as e:
            self.set_status(500)
            self.finish(f"Erro ao ler painel TV: {e}")
            return

        self.set_header("Content-Type", "text/html; charset=utf-8")
        self.set_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.set_header("Pragma", "no-cache")
        self.finish(content)


def register_tv_route():
    """
    Registra /app/tv no Tornado. Deve ser chamado da thread principal
    do Streamlit (app.py). Seguro chamar múltiplas vezes.
    """
    global _registered
    with _lock:
        if _registered:
            return
        try:
            from streamlit.web.server.server import Server  # noqa
            server = Server.get_current()
            if server is None or not hasattr(server, "_app"):
                return
            app = server._app
            new_spec = tornado.web.url(r"/app/tv", TVPageHandler)
            # Insere no início para ter prioridade sobre o catch-all do Streamlit
            for _, specs in app.handlers:
                specs.insert(0, new_spec)
                _registered = True
                print("[TV Route] /app/tv registrado com sucesso ✓")
                return
        except Exception as e:
            print(f"[TV Route] Erro ao registrar: {e}")
