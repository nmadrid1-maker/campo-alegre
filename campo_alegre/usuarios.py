import re
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from pymongo.errors import DuplicateKeyError
from werkzeug.security import generate_password_hash

from .db import get_db, registrar_actividad
from .security import ADMIN, EMPLEADO, login_required, rol_required

bp = Blueprint("usuarios", __name__, url_prefix="/usuarios")

ROLES = (ADMIN, EMPLEADO)
PATRON_USUARIO = re.compile(r"^[a-z0-9._-]{3,30}$")
CLAVE_MIN, CLAVE_MAX = 8, 128


def _col():
    return get_db().usuarios


def _validar_clave(clave, confirmacion):
    if len(clave) < CLAVE_MIN:
        return f"La contraseña debe tener al menos {CLAVE_MIN} caracteres."
    if len(clave) > CLAVE_MAX:
        return f"La contraseña admite hasta {CLAVE_MAX} caracteres."
    if clave != confirmacion:
        return "Las contraseñas no coinciden."
    return None


def _validar_nombre_rol(v, errores):
    if not v["nombre"]:
        errores["nombre"] = "Escriba el nombre completo."
    elif len(v["nombre"]) > 60:
        errores["nombre"] = "El nombre admite hasta 60 caracteres."
    if v["rol"] not in ROLES:
        errores["rol"] = "Seleccione el rol."


@bp.route("/")
@login_required
@rol_required(ADMIN)
def lista():
    filas = list(_col().find({}).sort("usuario", 1))
    return render_template("usuarios/lista.html", filas=filas, yo=session["user"]["usuario"])


@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@rol_required(ADMIN)
def nuevo():
    v = {"usuario": "", "nombre": "", "rol": EMPLEADO}
    errores = {}
    if request.method == "POST":
        v = {c: request.form.get(c, "").strip() for c in ("usuario", "nombre", "rol")}
        v["usuario"] = v["usuario"].lower()
        clave = request.form.get("clave", "")
        confirmacion = request.form.get("confirmacion", "")

        if not PATRON_USUARIO.match(v["usuario"]):
            errores["usuario"] = "El usuario debe tener entre 3 y 30 caracteres: letras minúsculas, números, punto, guion o guion bajo."
        elif _col().find_one({"usuario": v["usuario"]}):
            errores["usuario"] = "Ese nombre de usuario ya existe."
        _validar_nombre_rol(v, errores)
        mensaje = _validar_clave(clave, confirmacion)
        if mensaje:
            errores["clave"] = mensaje

        if not errores:
            try:
                _col().insert_one(
                    {
                        "usuario": v["usuario"],
                        "nombre": v["nombre"],
                        "rol": v["rol"],
                        "password_hash": generate_password_hash(clave),
                        "activo": True,
                        "creado_en": datetime.now(),
                    }
                )
            except DuplicateKeyError:
                errores["usuario"] = "Ese nombre de usuario ya existe."
            else:
                registrar_actividad(
                    f"Se creó el usuario {v['usuario']} ({v['rol']})", session["user"]["usuario"]
                )
                flash("Usuario creado.", "success")
                return redirect(url_for("usuarios.lista"))
        flash("Revisa los campos marcados.", "danger")
    return render_template("usuarios/form.html", v=v, errores=errores, roles=ROLES, editando=False)


def _buscar(usuario):
    encontrado = _col().find_one({"usuario": usuario})
    if not encontrado:
        flash("Ese usuario no existe.", "warning")
    return encontrado


@bp.route("/<usuario>/editar", methods=["GET", "POST"])
@login_required
@rol_required(ADMIN)
def editar(usuario):
    encontrado = _buscar(usuario)
    if not encontrado:
        return redirect(url_for("usuarios.lista"))
    es_yo = usuario == session["user"]["usuario"]
    v = {"usuario": usuario, "nombre": encontrado["nombre"], "rol": encontrado["rol"]}
    errores = {}
    if request.method == "POST":
        v["nombre"] = request.form.get("nombre", "").strip()
        v["rol"] = encontrado["rol"] if es_yo else request.form.get("rol", "").strip()
        _validar_nombre_rol(v, errores)
        if not errores:
            _col().update_one({"usuario": usuario}, {"$set": {"nombre": v["nombre"], "rol": v["rol"]}})
            registrar_actividad(
                f"Se actualizó el usuario {usuario} ({v['rol']})", session["user"]["usuario"]
            )
            flash("Usuario actualizado.", "success")
            return redirect(url_for("usuarios.lista"))
        flash("Revisa los campos marcados.", "danger")
    return render_template(
        "usuarios/form.html", v=v, errores=errores, roles=ROLES, editando=True, es_yo=es_yo
    )


@bp.route("/<usuario>/clave", methods=["GET", "POST"])
@login_required
@rol_required(ADMIN)
def clave(usuario):
    encontrado = _buscar(usuario)
    if not encontrado:
        return redirect(url_for("usuarios.lista"))
    error = None
    if request.method == "POST":
        error = _validar_clave(request.form.get("clave", ""), request.form.get("confirmacion", ""))
        if not error:
            _col().update_one(
                {"usuario": usuario},
                {"$set": {"password_hash": generate_password_hash(request.form["clave"])}},
            )
            # Nunca se registra la contraseña, solo el hecho.
            registrar_actividad(
                f"Se restableció la contraseña del usuario {usuario}", session["user"]["usuario"]
            )
            flash("Contraseña actualizada.", "success")
            return redirect(url_for("usuarios.lista"))
        flash("Revisa los campos marcados.", "danger")
    return render_template("usuarios/clave.html", usuario=encontrado, error=error)


@bp.route("/<usuario>/estado", methods=["POST"])
@login_required
@rol_required(ADMIN)
def estado(usuario):
    encontrado = _buscar(usuario)
    if not encontrado:
        return redirect(url_for("usuarios.lista"))
    if usuario == session["user"]["usuario"]:
        flash("No puedes desactivar tu propio usuario.", "warning")
        return redirect(url_for("usuarios.lista"))
    nuevo_estado = not encontrado.get("activo", True)
    _col().update_one({"usuario": usuario}, {"$set": {"activo": nuevo_estado}})
    registrar_actividad(
        f"Se {'activó' if nuevo_estado else 'desactivó'} el usuario {usuario}", session["user"]["usuario"]
    )
    flash("Usuario activado." if nuevo_estado else "Usuario desactivado.", "success")
    return redirect(url_for("usuarios.lista"))
