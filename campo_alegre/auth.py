from flask import Blueprint, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from .db import get_db
from .security import login_required

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("inicio.inicio"))

    error = None
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip().lower()
        clave = request.form.get("clave", "")
        encontrado = get_db().usuarios.find_one({"usuario": usuario, "activo": True})
        if encontrado and check_password_hash(encontrado["password_hash"], clave):
            session.clear()
            session["user"] = {
                "usuario": encontrado["usuario"],
                "nombre": encontrado["nombre"],
                "rol": encontrado["rol"],
            }
            return redirect(url_for("inicio.inicio"))
        # Mismo mensaje si falla el usuario o la clave, para no dar pistas.
        error = "Usuario o contraseña incorrectos."

    return render_template("login.html", error=error)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
