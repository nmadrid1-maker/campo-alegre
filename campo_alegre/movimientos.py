"""Movimientos del hato: nacimientos, entradas, salidas y novedades."""
import math
import re
from datetime import datetime

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from .db import get_db, registrar_actividad
from .security import ADMIN, EMPLEADO, login_required, rol_required
from .utils import hoy, parse_fecha, validar_fecha_evento
from .utils import paginas as numeros_de_pagina

bp = Blueprint("movimientos", __name__, url_prefix="/movimientos")

POR_PAGINA = 10
TIPOS = ("Nacimiento", "Entrada", "Salida", "Novedad")
# motivo de salida -> estado en que queda el animal
MOTIVOS_SALIDA = {"Venta": "Vendido", "Muerte": "Fallecido", "Traslado": "Trasladado", "Otro": "Retirado"}
PROCEDENCIAS_ENTRADA = ("Compra", "Donación")


def _col():
    return get_db().movimientos


def registrar_movimiento(tipo, animal, fecha, usuario, **extra):
    doc = {"tipo": tipo, "animal": animal, "fecha": fecha, "registrado_por": usuario, "creado_en": datetime.now()}
    doc.update({k: x for k, x in extra.items() if x})
    _col().insert_one(doc)


def registrar_alta(animal, usuario):
    """Al registrar un animal: Nacimiento si tiene madre, Entrada si fue comprado o donado."""
    if animal.get("madre"):
        registrar_movimiento("Nacimiento", animal["identificacion"], animal["fecha_nacimiento"], usuario,
                             madre=animal["madre"])
    elif animal.get("procedencia") in PROCEDENCIAS_ENTRADA:
        registrar_movimiento("Entrada", animal["identificacion"], animal["fecha_ingreso"], usuario,
                             detalle=animal["procedencia"])


def detalle(m):
    if m["tipo"] == "Nacimiento":
        return f"Madre {m['madre']}" if m.get("madre") else (m.get("detalle") or "Madre sin registrar")
    if m["tipo"] == "Salida":
        return m.get("motivo", "") + (f" · {m['detalle']}" if m.get("detalle") else "")
    return m.get("detalle") or ""


def resumen():
    """Cantidad de movimientos de los últimos 30 días (para el inicio)."""
    from datetime import timedelta
    return _col().count_documents({"fecha": {"$gte": hoy() - timedelta(days=30)}})


@bp.route("/")
@login_required
@rol_required(ADMIN, EMPLEADO)
def lista():
    q = request.args.get("q", "").strip()
    tipo = request.args.get("tipo", "").strip()
    desde = parse_fecha(request.args.get("desde", ""))
    hasta = parse_fecha(request.args.get("hasta", ""))
    pagina = max(1, request.args.get("page", 1, type=int))

    filtro = {}
    if q:
        filtro["animal"] = {"$regex": re.escape(q), "$options": "i"}
    if tipo in TIPOS:
        filtro["tipo"] = tipo
    rango = {}
    if desde:
        rango["$gte"] = desde
    if hasta:
        rango["$lte"] = hasta
    if rango:
        filtro["fecha"] = rango

    total = _col().count_documents(filtro)
    paginas = max(1, math.ceil(total / POR_PAGINA))
    pagina = min(pagina, paginas)
    inicio = (pagina - 1) * POR_PAGINA
    filas = list(_col().find(filtro).sort([("fecha", -1), ("creado_en", -1)]).skip(inicio).limit(POR_PAGINA))
    nombres = {a["identificacion"]: a.get("nombre")
               for a in get_db().animales.find({"identificacion": {"$in": [m["animal"] for m in filas]}})}
    return render_template(
        "movimientos/lista.html", filas=filas, nombres=nombres, q=q, tipo=tipo if tipo in TIPOS else "",
        desde=request.args.get("desde", "") if desde else "", hasta=request.args.get("hasta", "") if hasta else "",
        tipos=TIPOS, pagina=pagina, paginas=paginas, numeros=numeros_de_pagina(pagina, paginas),
        total=total, inicio=inicio, detalle=detalle,
    )


def _animal(identificacion):
    return get_db().animales.find_one({"identificacion": identificacion})


def _form(plantilla, v, errores):
    return render_template(plantilla, v=v, errores=errores, motivos=list(MOTIVOS_SALIDA))


@bp.route("/salida", methods=["GET", "POST"])
@login_required
@rol_required(ADMIN)
def salida():
    if request.method == "POST":
        v = {c: request.form.get(c, "").strip() for c in ("animal", "fecha", "motivo", "detalle")}
        errores = {}
        animal = _animal(v["animal"]) if v["animal"] else None
        if not v["animal"]:
            errores["animal"] = "Escriba la identificación del animal."
        elif not animal:
            errores["animal"] = f"No existe un animal con la identificación {v['animal']}."
        elif animal["estado"] != "Activa":
            errores["animal"] = f"El animal {v['animal']} ya figura como {animal['estado']}."
        fecha, mensaje = validar_fecha_evento(v["fecha"], animal, "de la salida")
        if mensaje:
            errores["fecha"] = mensaje
        elif animal and animal.get("fecha_ingreso") and fecha < animal["fecha_ingreso"]:
            errores["fecha"] = "La salida no puede ser anterior al ingreso del animal."
        if v["motivo"] not in MOTIVOS_SALIDA:
            errores["motivo"] = "Seleccione el motivo de la salida."
        if len(v["detalle"]) > 500:
            errores["detalle"] = "El detalle admite hasta 500 caracteres."
        if not errores:
            usuario = session["user"]["usuario"]
            get_db().animales.update_one(
                {"identificacion": v["animal"]},
                {"$set": {"estado": MOTIVOS_SALIDA[v["motivo"]], "actualizado_en": datetime.now()}},
            )
            registrar_movimiento("Salida", v["animal"], fecha, usuario, motivo=v["motivo"], detalle=v["detalle"])
            registrar_actividad(f"Salida del animal {v['animal']}: {v['motivo']}", usuario)
            flash(f"Salida registrada: el animal {v['animal']} queda como {MOTIVOS_SALIDA[v['motivo']]}.", "success")
            return redirect(url_for("movimientos.lista"))
        flash("Revisa los campos marcados.", "danger")
        return _form("movimientos/salida.html", v, errores)
    v = {"animal": request.args.get("animal", "").strip(), "fecha": hoy().strftime("%Y-%m-%d"),
         "motivo": "", "detalle": ""}
    return _form("movimientos/salida.html", v, {})


@bp.route("/novedad", methods=["GET", "POST"])
@login_required
@rol_required(ADMIN)
def novedad():
    if request.method == "POST":
        v = {c: request.form.get(c, "").strip() for c in ("animal", "fecha", "detalle")}
        errores = {}
        animal = _animal(v["animal"]) if v["animal"] else None
        if not v["animal"]:
            errores["animal"] = "Escriba la identificación del animal."
        elif not animal:
            errores["animal"] = f"No existe un animal con la identificación {v['animal']}."
        fecha, mensaje = validar_fecha_evento(v["fecha"], animal, "de la novedad")
        if mensaje:
            errores["fecha"] = mensaje
        if not v["detalle"]:
            errores["detalle"] = "Describa la novedad."
        elif len(v["detalle"]) > 500:
            errores["detalle"] = "La novedad admite hasta 500 caracteres."
        if not errores:
            usuario = session["user"]["usuario"]
            registrar_movimiento("Novedad", v["animal"], fecha, usuario, detalle=v["detalle"])
            registrar_actividad(f"Novedad registrada al animal {v['animal']}", usuario)
            flash("Novedad guardada.", "success")
            return redirect(url_for("movimientos.lista"))
        flash("Revisa los campos marcados.", "danger")
        return _form("movimientos/novedad.html", v, errores)
    v = {"animal": request.args.get("animal", "").strip(), "fecha": hoy().strftime("%Y-%m-%d"), "detalle": ""}
    return _form("movimientos/novedad.html", v, {})


@bp.route("/<movimiento_id>/eliminar", methods=["POST"])
@login_required
@rol_required(ADMIN)
def eliminar(movimiento_id):
    try:
        oid = ObjectId(movimiento_id)
    except (InvalidId, TypeError):
        flash("Ese movimiento no existe.", "warning")
        return redirect(url_for("movimientos.lista"))
    m = _col().find_one({"_id": oid})
    if not m:
        flash("Ese movimiento ya no existe.", "warning")
    elif m["tipo"] in ("Nacimiento", "Entrada"):
        flash("Los nacimientos y entradas se generan al registrar el animal; no se eliminan aquí.", "warning")
    else:
        _col().delete_one({"_id": oid})
        if m["tipo"] == "Salida":  # se corrige el error: el animal vuelve a estar activo
            get_db().animales.update_one({"identificacion": m["animal"]}, {"$set": {"estado": "Activa"}})
        registrar_actividad(f"Se eliminó un movimiento: {m['tipo']} (animal {m['animal']})", session["user"]["usuario"])
        flash("Movimiento eliminado." + (" El animal volvió a estado Activa." if m["tipo"] == "Salida" else ""), "success")
    return redirect(url_for("movimientos.lista"))
