import os
import threading
import webbrowser

from campo_alegre import create_app

app = create_app()

URL = "http://127.0.0.1:5000"

if __name__ == "__main__":
    # El recargador de Flask lanza este archivo dos veces; solo la primera (el proceso
    # padre, sin WERKZEUG_RUN_MAIN) abre el navegador, así no se abre otra pestaña al guardar cambios.
    # Para no abrirlo automáticamente: NO_ABRIR_NAVEGADOR=1 en el .env o en el entorno.
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true" and not os.environ.get("NO_ABRIR_NAVEGADOR"):
        threading.Timer(1.5, lambda: webbrowser.open(URL)).start()
    # debug=True recarga el servidor al guardar cambios. Solo para desarrollo.
    # Con CAMPO_ALEGRE_PRODUCCION=1 (lo pone Iniciar Campo Alegre.bat) arranca sin modo desarrollo.
    app.run(host="127.0.0.1", port=5000, debug=not os.environ.get("CAMPO_ALEGRE_PRODUCCION"))
