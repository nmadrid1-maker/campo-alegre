from flask import Flask, render_template

from .config import Config
from .db import init_db
from .filtros import registrar_filtros
from .security import init_security


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    init_db(app)
    init_security(app)
    registrar_filtros(app)

    from . import auth, ganado, inicio

    app.register_blueprint(auth.bp)
    app.register_blueprint(inicio.bp)
    app.register_blueprint(ganado.bp)

    @app.errorhandler(404)
    def no_encontrado(_error):
        return render_template("error.html", codigo=404, mensaje="No encontramos esa página."), 404

    @app.errorhandler(400)
    def solicitud_invalida(error):
        return render_template("error.html", codigo=400, mensaje=error.description), 400

    return app
