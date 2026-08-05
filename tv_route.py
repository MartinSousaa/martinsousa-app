"""
Registra a rota /app/tv no servidor Tornado interno do Streamlit,
servindo o painel TV com Content-Type: text/html correto.
"""
import os
import threading
import time

import tornado.web

TV_TOKEN = "msstudio2025tv"
_registered = False


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
            self.finish("Painel TV ainda não gerado. Abra o Placar primeiro.")
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
    Injeta a rota GET /app/tv no servidor Tornado do Streamlit.
    Executa em background thread para não bloquear o startup do app.
    """
    global _registered
    if _registered:
        return

    def _do_register():
        global _registered
        for attempt in range(90):          # tenta por até 90 s
            try:
                from streamlit.web.server.server import Server  # noqa: PLC0415
                server = Server.get_current()
                if server is not None and hasattr(server, "_app"):
                    server._app.add_handlers(
                        r".*",
                        [(r"/app/tv", TVPageHandler)],
                    )
                    _registered = True
                    print("[TV Route] Rota /app/tv registrada com sucesso ✓")
                    return
            except Exception:
                pass
            time.sleep(1)
        print("[TV Route] ⚠ Não foi possível registrar a rota após 90 tentativas")

    t = threading.Thread(target=_do_register, daemon=True, name="tv-route-registrar")
    t.start()