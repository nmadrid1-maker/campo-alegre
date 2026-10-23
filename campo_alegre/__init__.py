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

    if not app.config.get("TESTING"):
        # Los errores quedan también en errores.log (útil cuando el sistema corre sin ventana).
        import logging
        import os
        from logging.handlers import RotatingFileHandler

        manejador = RotatingFileHandler(
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "errores.log"),
            maxBytes=500_000, backupCount=2, encoding="utf-8",
        )
        manejador.setLevel(logging.WARNING)
        manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logging.getLogger().addHandler(manejador)
        app.logger.addHandler(manejador)

    init_db(app)
    init_security(app)
    registrar_filtros(app)

    from . import auth, ganado, movimientos, respaldos, potreros, informes, inicio, productivo, reproductivo, sanitario, usuarios

    app.register_blueprint(auth.bp)
    app.register_blueprint(inicio.bp)
    app.register_blueprint(ganado.bp)
    app.register_blueprint(potreros.bp)
    app.register_blueprint(movimientos.bp)
    app.register_blueprint(sanitario.bp)
    app.register_blueprint(reproductivo.bp)
    app.register_blueprint(productivo.bp)
    app.register_blueprint(usuarios.bp)
    app.register_blueprint(informes.bp)
    app.register_blueprint(respaldos.bp)
    respaldos.init_respaldos(app)

    @app.errorhandler(404)
    def no_encontrado(_error):
        return render_template("error.html", codigo=404, mensaje="No encontramos esa página."), 404

    @app.errorhandler(400)
    def solicitud_invalida(error):
        return render_template("error.html", codigo=400, mensaje=error.description), 400

    @app.errorhandler(500)
    def error_interno(_error):
        return render_template(
            "error.html", codigo=500,
            mensaje="Ocurrió un error en el sistema. Si se repite, avise al administrador (el detalle quedó en el archivo errores.log).",
        ), 500

    return app
