"""
dok_app.py — ponto de entrada do DOK como aplicativo de desktop.

Roda o Flask numa thread em segundo plano e abre uma janela nativa do
sistema operacional (sem barra de navegador) apontando pra ele —
usando pywebview. É isso que vira o .exe (Windows) ou o binário
(Linux/Pi) depois de empacotado com o PyInstaller.
"""
import socket
import threading
import time

import webview

from app import app, load_config


def _wait_port(host, port, timeout=10):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _run_flask(host, port):
    app.run(host=host, port=port, debug=False, use_reloader=False)


def main():
    cfg = load_config()
    host = "127.0.0.1"  # janela nativa não precisa expor na rede
    port = cfg["server"]["port"]
    app_cfg = cfg.get("app", {})

    flask_thread = threading.Thread(target=_run_flask, args=(host, port), daemon=True)
    flask_thread.start()

    if not _wait_port(host, port):
        raise RuntimeError("O servidor interno do DOK não subiu a tempo.")

    webview.create_window(
        title="DOK",
        url=f"http://{host}:{port}/",
        width=app_cfg.get("width", 480),
        height=app_cfg.get("height", 320),
        fullscreen=app_cfg.get("fullscreen", False),
        resizable=app_cfg.get("resizable", True),
    )
    webview.start()


if __name__ == "__main__":
    main()
