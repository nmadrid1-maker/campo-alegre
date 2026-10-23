import os
import secrets
from functools import wraps

from flask import abort, flash, redirect, request, session, url_for

from .db import get_db

ADMIN = "Administrador"
EMPLEADO = "Empleado"

# Menú lateral. "roles" indica quién lo ve.
MENU = [
    {"endpoint": "inicio.inicio", "icono": "home", "etiqueta": "Inicio", "roles": (ADMIN, EMPLEADO)},
    {"endpoint": "ganado.lista", "icono": "cow", "etiqueta": "Ganado", "roles": (ADMIN, EMPLEADO), "blueprint": "ganado"},
    {"endpoint": "potreros.lista", "icono": "leaf", "etiqueta": "Potreros", "roles": (ADMIN, EMPLEADO), "blueprint": "potreros"},
    {"endpoint": "movimientos.lista", "icono": "swap", "etiqueta": "Movimientos", "roles": (ADMIN, EMPLEADO), "blueprint": "movimientos"},
    {"endpoint": "sanitario.lista", "icono": "shield",
     "etiqueta": "Control sanitario", "roles": (ADMIN, EMPLEADO), "blueprint": "sanitario"},
    {"endpoint": "reproductivo.lista", "icono": "heart",
     "etiqueta": "Control reproductivo", "roles": (ADMIN, EMPLEADO), "blueprint": "reproductivo"},
    {"endpoint": "productivo.lista", "icono": "bars",
     "etiqueta": "Control productivo", "roles": (ADMIN, EMPLEADO), "blueprint": "productivo"},
    {"endpoint": "informes.indice", "icono": "doc", "etiqueta": "Informes", "roles": (ADMIN, EMPLEADO), "blueprint": "informes"},
    {"endpoint": "respaldos.lista", "icono": "save", "etiqueta": "Respaldos", "roles": (ADMIN,), "blueprint": "respaldos"},
    {"endpoint": "usuarios.lista", "icono": "users", "etiqueta": "Usuarios", "roles": (ADMIN,), "blueprint": "usuarios"},
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
        # Se revisa en la base en cada petición: si el usuario fue desactivado,
        # eliminado o cambió de rol, la sesión abierta se actualiza o se cierra.
        actual = get_db().usuarios.find_one({"usuario": session["user"]["usuario"]})
        if not actual or not actual.get("activo"):
            session.clear()
            flash("Tu sesión se cerró porque el usuario ya no está activo.", "warning")
            return redirect(url_for("auth.login"))
        if actual["rol"] != session["user"]["rol"] or actual["nombre"] != session["user"]["nombre"]:
            session["user"] = {
                "usuario": actual["usuario"],
                "nombre": actual["nombre"],
                "rol": actual["rol"],
            }
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
                    destino = item["endpoint"]
                    if usuario["rol"] == EMPLEADO and item.get("endpoint_empleado"):
                        destino = item["endpoint_empleado"]
                    activo = request.endpoint == destino or (
                        item.get("blueprint") and request.blueprint == item["blueprint"]
                    )
                    menu.append({**item, "endpoint": destino, "activo": bool(activo)})
        return {"usuario": usuario, "menu": menu, "es_admin": bool(usuario and usuario["rol"] == ADMIN)}
