from campo_alegre import create_app

app = create_app()

if __name__ == "__main__":
    # debug=True recarga el servidor al guardar cambios. Solo para desarrollo.
    app.run(host="127.0.0.1", port=5000, debug=True)
