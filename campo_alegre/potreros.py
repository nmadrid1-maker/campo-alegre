import re
from datetime import datetime

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from pymongo.errors import DuplicateKeyError

from .db import get_db, registrar_actividad
from .security import ADMIN, EMPLEADO, login_required, rol_required

bp = Blueprint("potreros", __name__, url_prefix="/potreros")


def _col():
    return get_db().potreros


def nombres_activos(incluir=None):
    """Nombres de potreros que se ofrecen en los formularios (más `incluir`, si ya es el actual)."""
    nombres = [p["nombre"] for p in _col().find({"activo": True}).sort("nombre_lower", 1)]
    if incluir and incluir not in nombres:
        nombres.append(incluir)
    return nombres


def registrar_traslado(animal, desde, hacia, usuario):
    """Guarda en el historial que el animal pasó de un potrero a otro (fecha: hoy)."""
    ahora = datetime.now()
    get_db().traslados.insert_one(
        {
            "animal": animal,
            "desde": desde,
            "hacia": hacia,
            "fecha": ahora.replace(hour=0, minute=0, second=0, microsecond=0),
            "registrado_por": usuario,
            "creado_en": ahora,
        }
    )


def _limpiar(texto):
    return " ".join(texto.split())


def validar(formulario, actual=None):
    v = {"nombre": _limpiar(formulario.get("nombre", "")), "observaciones": formulario.get("observaciones", "").strip()}
    errores = {}
    if not v["nombre"]:
        errores["nombre"] = "Escriba el nombre del potrero."
    elif len(v["nombre"]) > 40:
        errores["nombre"] = "El nombre admite hasta 40 caracteres."
    else:
        existente = _col().find_one({"nombre_lower": v["nombre"].lower()})
        if existente and (not actual or existente["_id"] != actual["_id"]):
            errores["nombre"] = "Ya existe un potrero con ese nombre."
    if len(v["observaciones"]) > 200:
        errores["observaciones"] = "Las observaciones admiten hasta 200 caracteres."
    return v, errores


def _animales_en(nombre, solo_activos=True):
    filtro = {"potrero": nombre}
    if solo_activos:
        filtro["estado"] = "Activa"
    return get_db().animales.count_documents(filtro)


def _buscar(potrero_id):
    try:
        oid = ObjectId(potrero_id)
    except (InvalidId, TypeError):
        oid = None
    encontrado = _col().find_one({"_id": oid}) if oid else None
    if not encontrado:
        flash("Ese potrero no existe.", "warning")
    return encontrado


@bp.route("/")
@login_required
@rol_required(ADMIN, EMPLEADO)
def lista():
    filas = []
    for p in _col().find({}).sort("nombre_lower", 1):
        p["animales"] = _animales_en(p["nombre"])
        filas.append(p)
    return render_template("potreros/lista.html", filas=filas, total_animales=sum(p["animales"] for p in filas))


@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@rol_required(ADMIN)
def nuevo():
    v, errores = {"nombre": "", "observaciones": ""}, {}
    if request.method == "POST":
        v, errores = validar(request.form)
        if not errores:
            ahora = datetime.now()
            try:
                _col().insert_one(
                    {
                        "nombre": v["nombre"],
                        "nombre_lower": v["nombre"].lower(),
                        "activo": True,
                        "observaciones": v["observaciones"] or None,
                        "creado_en": ahora,
                        "actualizado_en": ahora,
                    }
                )
            except DuplicateKeyError:
                errores["nombre"] = "Ya existe un potrero con ese nombre."
            else:
                registrar_actividad(f"Se creó el potrero {v['nombre']}", session["user"]["usuario"])
                flash("Potrero creado.", "success")
                return redirect(url_for("potreros.lista"))
        flash("Revisa los campos marcados.", "danger")
    return render_template("potreros/form.html", v=v, errores=errores, editando=False)


@bp.route("/<potrero_id>/editar", methods=["GET", "POST"])
@login_required
@rol_required(ADMIN)
def editar(potrero_id):
    actual = _buscar(potrero_id)
    if not actual:
        return redirect(url_for("potreros.lista"))
    v = {"nombre": actual["nombre"], "observaciones": actual.get("observaciones") or ""}
    errores = {}
    if request.method == "POST":
        v, errores = validar(request.form, actual)
        if not errores:
            _col().update_one(
                {"_id": actual["_id"]},
                {"$set": {"nombre": v["nombre"], "nombre_lower": v["nombre"].lower(),
                          "observaciones": v["observaciones"] or None, "actualizado_en": datetime.now()}},
            )
            if v["nombre"] != actual["nombre"]:
                # Los animales y el historial guardan el nombre: se actualizan con el cambio.
                db = get_db()
                db.animales.update_many({"potrero": actual["nombre"]}, {"$set": {"potrero": v["nombre"]}})
                db.traslados.update_many({"desde": actual["nombre"]}, {"$set": {"desde": v["nombre"]}})
                db.traslados.update_many({"hacia": actual["nombre"]}, {"$set": {"hacia": v["nombre"]}})
            registrar_actividad(
                f"Se actualizó el potrero {actual['nombre']}" + (f" (ahora {v['nombre']})" if v["nombre"] != actual["nombre"] else ""),
                session["user"]["usuario"],
            )
            flash("Potrero actualizado.", "success")
            return redirect(url_for("potreros.lista"))
        flash("Revisa los campos marcados.", "danger")
    return render_template("potreros/form.html", v=v, errores=errores, editando=True)


@bp.route("/<potrero_id>/estado", methods=["POST"])
@login_required
@rol_required(ADMIN)
def estado(potrero_id):
    p = _buscar(potrero_id)
    if not p:
        return redirect(url_for("potreros.lista"))
    if p.get("activo"):
        en_uso = _animales_en(p["nombre"])
        if en_uso:
            flash(
                f"No se puede desactivar “{p['nombre']}”: {en_uso} {'animal está' if en_uso == 1 else 'animales están'} allí. Muévalos primero.",
                "warning",
            )
            return redirect(url_for("potreros.lista"))
    nuevo_estado = not p.get("activo")
    _col().update_one({"_id": p["_id"]}, {"$set": {"activo": nuevo_estado, "actualizado_en": datetime.now()}})
    registrar_actividad(
        f"Se {'activó' if nuevo_estado else 'desactivó'} el potrero {p['nombre']}", session["user"]["usuario"]
    )
    flash("Potrero activado." if nuevo_estado else "Potrero desactivado.", "success")
    return redirect(url_for("potreros.lista"))


@bp.route("/<potrero_id>/eliminar", methods=["POST"])
@login_required
@rol_required(ADMIN)
def eliminar(potrero_id):
    p = _buscar(potrero_id)
    if not p:
        return redirect(url_for("potreros.lista"))
    db = get_db()
    if _animales_en(p["nombre"], solo_activos=False) or db.traslados.count_documents(
        {"$or": [{"desde": p["nombre"]}, {"hacia": p["nombre"]}]}
    ):
        flash(
            f"No se puede eliminar “{p['nombre']}”: tiene animales o historial de traslados. Si ya no se usa, desactívelo.",
            "warning",
        )
        return redirect(url_for("potreros.lista"))
    _col().delete_one({"_id": p["_id"]})
    registrar_actividad(f"Se eliminó el potrero {p['nombre']}", session["user"]["usuario"])
    flash("Potrero eliminado.", "success")
    return redirect(url_for("potreros.lista"))
