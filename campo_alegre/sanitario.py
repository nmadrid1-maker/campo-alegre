import math
import re
from datetime import datetime, timedelta

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from .db import get_db, registrar_actividad
from .security import ADMIN, EMPLEADO, login_required, rol_required
from .utils import animales_activos, hoy, parse_fecha, validar_animal, validar_fecha_evento
from .utils import paginas as numeros_de_pagina

bp = Blueprint("sanitario", __name__, url_prefix="/sanitario")

POR_PAGINA = 10
TIPOS = ("Vacunación", "Desparasitación", "Tratamiento", "Otro")
DIAS_AVISO = 30  # ventana de "próximas dosis"

CAMPOS = ("animal", "tipo", "producto", "fecha_aplicacion", "proxima_dosis", "observaciones")


def _eventos():
    return get_db().eventos_sanitarios


def contar_proximas_dosis():
    """Eventos cuya próxima dosis cae entre hoy y los próximos 30 días."""
    desde = hoy()
    return _eventos().count_documents(
        {"proxima_dosis": {"$gte": desde, "$lte": desde + timedelta(days=DIAS_AVISO)}}
    )


def validar(formulario):
    """Devuelve (valores, errores). Los valores sirven para volver a pintar el formulario."""
    v = {campo: formulario.get(campo, "").strip() for campo in CAMPOS}
    errores = {}

    animal, mensaje = validar_animal(v["animal"])
    if mensaje:
        errores["animal"] = mensaje

    if v["tipo"] not in TIPOS:
        errores["tipo"] = "Seleccione el tipo de evento."

    if not v["producto"]:
        errores["producto"] = "Escriba el nombre del producto."
    elif len(v["producto"]) > 80:
        errores["producto"] = "El nombre del producto admite hasta 80 caracteres."

    aplicacion, mensaje = validar_fecha_evento(v["fecha_aplicacion"], animal, "de aplicación")
    if mensaje:
        errores["fecha_aplicacion"] = mensaje

    if v["proxima_dosis"]:
        proxima = parse_fecha(v["proxima_dosis"])
        if not proxima:
            errores["proxima_dosis"] = "La fecha de la próxima dosis no es válida."
        elif aplicacion and proxima <= aplicacion:
            errores["proxima_dosis"] = "La próxima dosis debe ser posterior a la fecha de aplicación."

    if len(v["observaciones"]) > 500:
        errores["observaciones"] = "Las observaciones admiten hasta 500 caracteres."

    return v, errores


def _form(valores, errores):
    return render_template(
        "sanitario/form.html",
        v=valores,
        errores=errores,
        tipos=TIPOS,
        animales=animales_activos(),
    )


@bp.route("/")
@login_required
@rol_required(ADMIN, EMPLEADO)
def lista():
    q = request.args.get("q", "").strip()
    tipo = request.args.get("tipo", "").strip()
    animal = request.args.get("animal", "").strip()
    pagina = max(1, request.args.get("page", 1, type=int))

    filtro = {}
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        filtro["$or"] = [{"animal": rx}, {"producto": rx}]
    if tipo in TIPOS:
        filtro["tipo"] = tipo
    if animal:
        filtro["animal"] = animal

    total = _eventos().count_documents(filtro)
    paginas = max(1, math.ceil(total / POR_PAGINA))
    pagina = min(pagina, paginas)
    inicio = (pagina - 1) * POR_PAGINA
    filas = list(
        _eventos()
        .find(filtro)
        .sort([("fecha_aplicacion", -1), ("creado_en", -1)])
        .skip(inicio)
        .limit(POR_PAGINA)
    )

    desde = hoy()
    hasta = desde + timedelta(days=DIAS_AVISO)
    rango = {"proxima_dosis": {"$gte": desde, "$lte": hasta}}
    proximas = list(_eventos().find(rango).sort("proxima_dosis", 1).limit(5))
    total_proximas = _eventos().count_documents(rango)

    ids = {e["animal"] for e in filas} | {e["animal"] for e in proximas}
    nombres = {
        a["identificacion"]: a.get("nombre")
        for a in get_db().animales.find({"identificacion": {"$in": list(ids)}})
    }

    return render_template(
        "sanitario/lista.html",
        filas=filas,
        nombres=nombres,
        proximas=proximas,
        total_proximas=total_proximas,
        hoy=desde,
        aviso=hasta,
        q=q,
        tipo=tipo if tipo in TIPOS else "",
        animal=animal,
        tipos=TIPOS,
        pagina=pagina,
        paginas=paginas,
        numeros=numeros_de_pagina(pagina, paginas),
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
            ahora = datetime.now()
            _eventos().insert_one(
                {
                    "animal": v["animal"],
                    "tipo": v["tipo"],
                    "producto": v["producto"],
                    "fecha_aplicacion": parse_fecha(v["fecha_aplicacion"]),
                    "proxima_dosis": parse_fecha(v["proxima_dosis"]) if v["proxima_dosis"] else None,
                    "observaciones": v["observaciones"] or None,
                    "registrado_por": session["user"]["usuario"],
                    "creado_en": ahora,
                }
            )
            registrar_actividad(
                f"Se registró un evento sanitario: {v['tipo']} · {v['producto']} (animal {v['animal']})",
                session["user"]["usuario"],
            )
            flash("Evento sanitario guardado.", "success")
            return redirect(url_for("sanitario.lista"))
        flash("Revisa los campos marcados.", "danger")
        return _form(v, errores)

    valores = {campo: "" for campo in CAMPOS}
    valores["tipo"] = "Vacunación"
    valores["fecha_aplicacion"] = hoy().strftime("%Y-%m-%d")
    valores["animal"] = request.args.get("animal", "").strip()
    return _form(valores, {})


@bp.route("/<evento_id>/eliminar", methods=["POST"])
@login_required
@rol_required(ADMIN)
def eliminar(evento_id):
    try:
        oid = ObjectId(evento_id)
    except (InvalidId, TypeError):
        flash("Ese evento no existe.", "warning")
        return redirect(url_for("sanitario.lista"))

    evento = _eventos().find_one({"_id": oid})
    if not evento:
        flash("Ese evento ya no existe.", "warning")
        return redirect(url_for("sanitario.lista"))

    _eventos().delete_one({"_id": oid})
    registrar_actividad(
        f"Se eliminó un evento sanitario: {evento['tipo']} · {evento['producto']} (animal {evento['animal']})",
        session["user"]["usuario"],
    )
    flash("Evento eliminado.", "success")
    return redirect(url_for("sanitario.lista"))
