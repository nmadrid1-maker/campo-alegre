import os
import secrets
from functools import wraps

from flask import abort, flash, redirect, request, session, url_for

ADMIN = "Administrador"
EMPLEADO = "Empleado"

# Menú lateral. "roles" indica quién lo ve.
MENU = [
    {"endpoint": "inicio.inicio", "icono": "home", "etiqueta": "Inicio", "roles": (ADMIN, EMPLEADO)},
    {"endpoint": "ganado.lista", "icono": "cow", "etiqueta": "Ganado", "roles": (ADMIN,), "blueprint": "ganado"},
    {"endpoint": "inicio.sanitario", "icono": "shield", "etiqueta": "Control sanitario", "roles": (ADMIN, EMPLEADO)},
    {"endpoint": "inicio.reproductivo", "icono": "heart", "etiqueta": "Control reproductivo", "roles": (ADMIN, EMPLEADO)},
    {"endpoint": "inicio.productivo", "icono": "bars", "etiqueta": "Control productivo", "roles": (ADMIN, EMPLEADO)},
    {"endpoint": "inicio.informes", "icono": "doc", "etiqueta": "Informes", "roles": (ADMIN,)},
    {"endpoint": "inicio.usuarios", "icono": "users", "etiqueta": "Usuarios", "roles": (ADMIN,)},
    {"endpoint": "inicio.configuracion", "icono": "gear", "etiqueta": "Configuración", "roles": (ADMIN,)},
]


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def login_required(vista):
    @wraps(vista)
    def envuelta(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login"))
        return vista(*args, **kwargs)

    return envuelta


def rol_required(*roles):
    """Deja pasar solo a los roles indicados. Va debajo de @login_required."""

    def decorador(vista):
        @wraps(vista)
        def envuelta(*args, **kwargs):
            if session["user"]["rol"] not in roles:
                flash("Tu rol no tiene permiso para entrar a esa sección.", "warning")
                return redirect(url_for("inicio.inicio"))
            return vista(*args, **kwargs)

        return envuelta

    return decorador


def init_security(app):
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def verificar_csrf():
        if request.method == "POST":
            enviado = request.form.get("_csrf", "")
            esperado = session.get("_csrf", "")
            if not enviado or not esperado or not secrets.compare_digest(enviado, esperado):
                abort(400, "Formulario inválido o vencido. Recarga la página e inténtalo de nuevo.")

    @app.context_processor
    def contexto():
        usuario = session.get("user")
        menu = []
        if usuario:
            for item in MENU:
                if usuario["rol"] in item["roles"]:
                    activo = request.endpoint == item["endpoint"] or (
                        item.get("blueprint") and request.blueprint == item["blueprint"]
                    )
                    menu.append({**item, "activo": bool(activo)})
        base = os.path.join(app.static_folder, "vendor", "bootstrap.min.css")
        return {"usuario": usuario, "menu": menu, "bootstrap_local": os.path.exists(base)}
