"""
Registra a rota /app/tv no servidor Tornado interno do Streamlit,
servindo o painel TV com Content-Type: text/html correto.

A inserção no INÍCIO da lista de specs garante que nossa rota
tem prioridade sobre o catch-all do Streamlit.
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
    Insere a rota GET /app/tv NO INÍCIO da lista de handlers do Tornado,
    garantindo prioridade sobre o catch-all do Streamlit.
    """
    global _registered
    if _registered:
        return

    def _do_register():
        global _registered
        for attempt in range(90):          # tenta por até 90 s
            try:
                from streamlit.web.server.server import Server  # noqa
                server = Server.get_current()
                if server is not None and hasattr(server, "_app"):
                    app = server._app
                    new_spec = tornado.web.url(r"/app/tv", TVPageHandler)
                    # Insere no início da lista para ter prioridade sobre o catch-all
                    inserted = False
                    for host_pattern, specs in app.handlers:
                        specs.insert(0, new_spec)
                        inserted = True
                        break
                    if not inserted:
                        # fallback: usa add_handlers normalmente
                        app.add_handlers(r".*", [(r"/app/tv", TVPageHandler)])
                    _registered = True
                    print("[TV Route] Rota /app/tv registrada com prioridade ✓")
                    return
            except Exception as e:
                print(f"[TV Route] tentativa {attempt}: {e}")
            time.sleep(1)
        print("[TV Route] ⚠ Nao foi possivel registrar a rota apos 90 tentativas")

    t = threading.Thread(target=_do_register, daemon=True, name="tv-route-registrar")
    t.start()
