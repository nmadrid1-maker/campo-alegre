import math
import re
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from pymongo.errors import DuplicateKeyError

from .db import get_db, registrar_actividad
from .security import ADMIN, login_required, rol_required

bp = Blueprint("ganado", __name__, url_prefix="/ganado")

POR_PAGINA = 6
SEXOS = ("Hembra", "Macho")
CATEGORIAS = {
    "Hembra": ("Vaca", "Novilla", "Ternera"),
    "Macho": ("Toro", "Novillo", "Ternero"),
}
ESTADOS = ("Activa", "Vendido", "Fallecido")
PROCEDENCIAS = ("Finca Campo Alegre", "Compra", "Donación")
IDENTIFICACION_RE = re.compile(r"^[A-Za-z0-9-]{1,20}$")

CAMPOS = (
    "identificacion", "nombre", "sexo", "categoria", "fecha_nacimiento",
    "fecha_ingreso", "procedencia", "estado", "observaciones",
)


def _animales():
    return get_db().animales


def _parse_fecha(texto):
    try:
        return datetime.strptime(texto, "%Y-%m-%d")
    except ValueError:
        return None


def validar(formulario, editando=False):
    """Devuelve (valores, errores). Los valores se usan para volver a pintar el formulario."""
    v = {campo: formulario.get(campo, "").strip() for campo in CAMPOS}
    if not v["estado"]:
        v["estado"] = "Activa"
    errores = {}

    if not editando:
        if not v["identificacion"]:
            errores["identificacion"] = "Escriba la identificación."
        elif not IDENTIFICACION_RE.match(v["identificacion"]):
            errores["identificacion"] = "Use solo letras, números o guion, hasta 20 caracteres."

    if len(v["nombre"]) > 40:
        errores["nombre"] = "El nombre admite hasta 40 caracteres."

    if v["sexo"] not in SEXOS:
        errores["sexo"] = "Seleccione el sexo."

    todas = CATEGORIAS["Hembra"] + CATEGORIAS["Macho"]
    if v["categoria"] not in todas:
        errores["categoria"] = "Seleccione la categoría."
    elif v["sexo"] in SEXOS and v["categoria"] not in CATEGORIAS[v["sexo"]]:
        errores["categoria"] = f"La categoría {v['categoria']} no corresponde a un animal de sexo {v['sexo']}."

    hoy = datetime.now()
    nacimiento = _parse_fecha(v["fecha_nacimiento"])
    ingreso = _parse_fecha(v["fecha_ingreso"])
    if not nacimiento:
        errores["fecha_nacimiento"] = "Indique la fecha de nacimiento."
    elif nacimiento > hoy:
        errores["fecha_nacimiento"] = "La fecha de nacimiento no puede ser futura."
    if not ingreso:
        errores["fecha_ingreso"] = "Indique la fecha de ingreso."
    elif ingreso > hoy:
        errores["fecha_ingreso"] = "La fecha de ingreso no puede ser futura."
    elif nacimiento and ingreso < nacimiento:
        errores["fecha_ingreso"] = "El ingreso no puede ser anterior al nacimiento."

    if v["procedencia"] and v["procedencia"] not in PROCEDENCIAS:
        errores["procedencia"] = "Seleccione una procedencia de la lista."
    if v["estado"] not in ESTADOS:
        errores["estado"] = "Seleccione un estado de la lista."
    if len(v["observaciones"]) > 500:
        errores["observaciones"] = "Las observaciones admiten hasta 500 caracteres."

    return v, errores


def _documento(v):
    return {
        "nombre": v["nombre"] or None,
        "sexo": v["sexo"],
        "categoria": v["categoria"],
        "estado": v["estado"],
        "fecha_nacimiento": _parse_fecha(v["fecha_nacimiento"]),
        "fecha_ingreso": _parse_fecha(v["fecha_ingreso"]),
        "procedencia": v["procedencia"] or None,
        "observaciones": v["observaciones"] or None,
    }


def _valores_desde_documento(a):
    f = lambda d: d.strftime("%Y-%m-%d") if d else ""
    return {
        "identificacion": a["identificacion"],
        "nombre": a.get("nombre") or "",
        "sexo": a["sexo"],
        "categoria": a["categoria"],
        "fecha_nacimiento": f(a.get("fecha_nacimiento")),
        "fecha_ingreso": f(a.get("fecha_ingreso")),
        "procedencia": a.get("procedencia") or "",
        "estado": a["estado"],
        "observaciones": a.get("observaciones") or "",
    }


def _paginas(actual, total):
    """Números de página a mostrar; None es un hueco ('…')."""
    visibles = [n for n in range(1, total + 1) if n <= 2 or n > total - 1 or abs(n - actual) <= 1]
    salida, previo = [], 0
    for n in visibles:
        if n - previo > 1:
            salida.append(None)
        salida.append(n)
        previo = n
    return salida


def _form(titulo, valores, errores, editando):
    return render_template(
        "ganado/form.html",
        titulo=titulo,
        v=valores,
        errores=errores,
        editando=editando,
        sexos=SEXOS,
        categorias=CATEGORIAS,
        estados=ESTADOS,
        procedencias=PROCEDENCIAS,
    )


@bp.route("/")
@login_required
@rol_required(ADMIN)
def lista():
    q = request.args.get("q", "").strip()
    pagina = max(1, request.args.get("page", 1, type=int))

    filtro = {}
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        filtro = {"$or": [{"identificacion": rx}, {"nombre": rx}, {"categoria": rx}]}

    total = _animales().count_documents(filtro)
    paginas = max(1, math.ceil(total / POR_PAGINA))
    pagina = min(pagina, paginas)
    inicio = (pagina - 1) * POR_PAGINA
    filas = list(
        _animales().find(filtro).sort("creado_en", -1).skip(inicio).limit(POR_PAGINA)
    )
    return render_template(
        "ganado/lista.html",
        filas=filas,
        q=q,
        pagina=pagina,
        paginas=paginas,
        numeros=_paginas(pagina, paginas),
        total=total,
        inicio=inicio,
    )


@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@rol_required(ADMIN)
def nuevo():
    if request.method == "POST":
        v, errores = validar(request.form)
        if not errores:
            documento = _documento(v)
            ahora = datetime.now()
            documento.update(
                identificacion=v["identificacion"], creado_en=ahora, actualizado_en=ahora
            )
            try:
                _animales().insert_one(documento)
            except DuplicateKeyError:
                errores["identificacion"] = "Ya existe un animal con esa identificación."
            else:
                registrar_actividad(
                    f"Se registró un nuevo animal (ID: {v['identificacion']})", session["user"]["usuario"]
                )
                flash(f"Animal {v['identificacion']} guardado.", "success")
                return redirect(url_for("ganado.ficha", identificacion=v["identificacion"]))
        flash("Revisa los campos marcados.", "danger")
        return _form("Registrar nuevo animal", v, errores, editando=False)

    valores = {campo: "" for campo in CAMPOS}
    valores["estado"] = "Activa"
    return _form("Registrar nuevo animal", valores, {}, editando=False)


@bp.route("/<identificacion>")
@login_required
@rol_required(ADMIN)
def ficha(identificacion):
    animal = _animales().find_one({"identificacion": identificacion})
    if not animal:
        abort(404)
    return render_template("ganado/ficha.html", a=animal)


@bp.route("/<identificacion>/editar", methods=["GET", "POST"])
@login_required
@rol_required(ADMIN)
def editar(identificacion):
    animal = _animales().find_one({"identificacion": identificacion})
    if not animal:
        abort(404)

    titulo = f"Editar animal {identificacion}"
    if request.method == "POST":
        formulario = request.form.copy()
        formulario["identificacion"] = identificacion  # la identificación no se cambia
        v, errores = validar(formulario, editando=True)
        if not errores:
            cambios = _documento(v)
            cambios["actualizado_en"] = datetime.now()
            _animales().update_one({"identificacion": identificacion}, {"$set": cambios})
            registrar_actividad(
                f"Se actualizó el animal (ID: {identificacion})", session["user"]["usuario"]
            )
            flash("Cambios guardados.", "success")
            return redirect(url_for("ganado.ficha", identificacion=identificacion))
        flash("Revisa los campos marcados.", "danger")
        return _form(titulo, v, errores, editando=True)

    return _form(titulo, _valores_desde_documento(animal), {}, editando=True)


@bp.route("/<identificacion>/eliminar", methods=["POST"])
@login_required
@rol_required(ADMIN)
def eliminar(identificacion):
    resultado = _animales().delete_one({"identificacion": identificacion})
    if resultado.deleted_count:
        registrar_actividad(
            f"Se eliminó el animal (ID: {identificacion})", session["user"]["usuario"]
        )
        flash(f"Animal {identificacion} eliminado.", "success")
    else:
        flash("Ese animal ya no existe.", "warning")
    return redirect(url_for("ganado.lista"))
