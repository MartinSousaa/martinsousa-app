"""Preparação do ambiente antes de subir o Streamlit.

Roda uma vez, no Procfile, antes do `streamlit run`. Faz duas coisas:

1. BLINDA CONTRA O GOOGLE TRADUTOR
   O tradutor do Chrome substitui os nós de texto da página por elementos
   <font>. O Streamlit é feito em React, que guarda referência dos nós que
   criou — quando tenta remover um nó que o tradutor trocou, estoura:

       NotFoundError: Failed to execute 'removeChild' on 'Node'

   O Streamlit se recupera recarregando a página inteira, e o colaborador
   perde tudo o que estava preenchendo. Em 21/08/2026 foram encontrados 270
   elementos <font> injetados numa única tela do app.

   A blindagem marca a página como "não traduzir", o que faz o Chrome
   ignorá-la mesmo com tradução automática ligada no navegador do usuário.

2. APLICA O config.toml
   O Streamlit só lê configuração de `.streamlit/config.toml`. O arquivo do
   projeto está na raiz do repositório, onde é ignorado — ou seja,
   enableStaticServing e maxMessageSize nunca chegaram a valer. Aqui ele é
   copiado para o lugar certo, sem sobrescrever o secrets.toml.
"""

import os
import re
import shutil
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
DIR_STREAMLIT = os.path.join(RAIZ, ".streamlit")

META_NOTRANSLATE = '<meta name="google" content="notranslate">'


def blindar_tradutor():
    """Marca o index.html do Streamlit como não-traduzível. Idempotente."""
    try:
        import streamlit
    except ImportError:
        print("[prestart] streamlit não encontrado — pulando blindagem", file=sys.stderr)
        return False

    index = os.path.join(os.path.dirname(streamlit.__file__), "static", "index.html")
    if not os.path.exists(index):
        print(f"[prestart] index.html não encontrado em {index}", file=sys.stderr)
        return False

    try:
        with open(index, "r", encoding="utf-8") as f:
            html = f.read()

        if META_NOTRANSLATE in html:
            print("[prestart] blindagem contra tradutor já aplicada")
            return True

        # <meta> no head — sinal padrão que o Google respeita
        if "<head>" in html:
            html = html.replace("<head>", "<head>" + META_NOTRANSLATE, 1)
        else:
            print("[prestart] <head> não encontrado no index.html", file=sys.stderr)
            return False

        # translate="no" + class="notranslate" na raiz — reforço para o caso
        # de o Chrome ignorar o meta
        html = re.sub(
            r"<html(?![^>]*translate=)([^>]*)>",
            r'<html\1 translate="no" class="notranslate">',
            html,
            count=1,
        )

        with open(index, "w", encoding="utf-8") as f:
            f.write(html)

        print("[prestart] blindagem contra tradutor aplicada")
        return True
    except Exception as e:
        # Nunca impedir o app de subir por causa disso
        print(f"[prestart] falha ao blindar contra tradutor: {e}", file=sys.stderr)
        return False


def aplicar_config():
    """Copia config.toml da raiz para .streamlit/, onde o Streamlit lê."""
    origem = os.path.join(RAIZ, "config.toml")
    destino = os.path.join(DIR_STREAMLIT, "config.toml")

    if not os.path.exists(origem):
        print("[prestart] config.toml não existe na raiz — nada a copiar")
        return False

    try:
        os.makedirs(DIR_STREAMLIT, exist_ok=True)
        shutil.copyfile(origem, destino)
        print(f"[prestart] config.toml aplicado em {destino}")
        return True
    except Exception as e:
        print(f"[prestart] falha ao aplicar config.toml: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    aplicar_config()
    blindar_tradutor()
