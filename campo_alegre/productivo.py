import math
import re
from datetime import datetime

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from pymongo.errors import DuplicateKeyError

from .db import get_db, registrar_actividad
from .security import ADMIN, EMPLEADO, login_required, rol_required
from .utils import animales_activos, hoy, parse_fecha, validar_animal, validar_fecha_evento
from .utils import paginas as numeros_de_pagina

bp = Blueprint("productivo", __name__, url_prefix="/productivo")

POR_PAGINA = 10
PESO_MIN, PESO_MAX = 10, 1500  # kg
TIPOS_PESO = ("Medido", "Estimado")  # Medido = báscula; Estimado = a ojo o con cinta
CAMPOS = ("animal", "fecha", "peso_kg", "tipo_peso", "observaciones")
PATRON_PESO = re.compile(r"^\d{1,4}([.,]\d)?$")


def _pesajes():
    return get_db().pesajes


def pesajes_del_mes():
    """Pesajes con fecha dentro del mes actual."""
    inicio = hoy().replace(day=1)
    return _pesajes().count_documents({"fecha": {"$gte": inicio}})


def historial(identificacion):
    """Pesajes del animal, del más reciente al más antiguo, con cambio (kg) y GDP (g/día)."""
    filas = list(_pesajes().find({"animal": identificacion}).sort("fecha", -1))
    for i, p in enumerate(filas):
        anterior = filas[i + 1] if i + 1 < len(filas) else None
        if anterior:
            dias = (p["fecha"] - anterior["fecha"]).days
            p["cambio"] = round(p["peso_kg"] - anterior["peso_kg"], 1)
            p["gdp"] = round(p["cambio"] * 1000 / dias) if dias > 0 else None
            p["gdp_estimado"] = es_estimado(p) or es_estimado(anterior)
        else:
            p["cambio"] = None
            p["gdp"] = None
            p["gdp_estimado"] = False
    return filas


def es_estimado(pesaje):
    return pesaje.get("tipo_peso") == "Estimado"  # los pesajes antiguos sin tipo cuentan como medidos


def ultimos_pesos(identificaciones=None):
    """{identificacion: pesaje más reciente}. Sin argumento, de todos los animales."""
    filtro = {} if identificaciones is None else {"animal": {"$in": list(identificaciones)}}
    ultimos = {}
    for p in _pesajes().find(filtro).sort("fecha", 1):
        ultimos[p["animal"]] = p
    return ultimos


def leer_rango_peso(args):
    """(mínimo, máximo) de los parámetros peso_min y peso_max; lo que no sea número se ignora."""
    salida = []
    for nombre in ("peso_min", "peso_max"):
        texto = args.get(nombre, "").strip().replace(",", ".")
        try:
            valor = float(texto) if texto else None
        except ValueError:
            valor = None
        salida.append(valor if valor is not None and valor == valor and 0 <= valor <= 100000 else None)
    return tuple(salida)


def animales_en_rango(minimo, maximo):
    """Identificaciones cuyo último peso está dentro del rango."""
    return [
        ident for ident, p in ultimos_pesos().items()
        if (minimo is None or p["peso_kg"] >= minimo) and (maximo is None or p["peso_kg"] <= maximo)
    ]


def validar(formulario):
    v = {campo: formulario.get(campo, "").strip() for campo in CAMPOS}
    if not v["tipo_peso"]:
        v["tipo_peso"] = "Medido"
    errores = {}
    if v["tipo_peso"] not in TIPOS_PESO:
        errores["tipo_peso"] = "Indique si el peso fue medido o estimado."

    animal, mensaje = validar_animal(v["animal"])
    if mensaje:
        errores["animal"] = mensaje

    fecha, mensaje = validar_fecha_evento(v["fecha"], animal, "del pesaje")
    if mensaje:
        errores["fecha"] = mensaje

    peso = None
    if not PATRON_PESO.match(v["peso_kg"]):
        errores["peso_kg"] = "Escriba el peso en kilogramos, con un decimal como máximo. Ej: 420 o 420,5."
    else:
        peso = float(v["peso_kg"].replace(",", "."))
        if not PESO_MIN <= peso <= PESO_MAX:
            errores["peso_kg"] = f"El peso debe estar entre {PESO_MIN} y {PESO_MAX} kg."
            peso = None

    if len(v["observaciones"]) > 500:
        errores["observaciones"] = "Las observaciones admiten hasta 500 caracteres."

    if (
        not errores
        and _pesajes().count_documents({"animal": v["animal"], "fecha": fecha}) > 0
    ):
        errores["fecha"] = f"El animal {v['animal']} ya tiene un pesaje registrado en esa fecha."

    return v, errores, peso


def _form(valores, errores):
    return render_template(
        "productivo/form.html",
        v=valores,
        errores=errores,
        animales=animales_activos(),
        peso_min=PESO_MIN,
        peso_max=PESO_MAX,
        tipos_peso=TIPOS_PESO,
    )


@bp.route("/")
@login_required
@rol_required(ADMIN, EMPLEADO)
def lista():
    q = request.args.get("q", "").strip()
    animal = request.args.get("animal", "").strip()
    pagina = max(1, request.args.get("page", 1, type=int))

    filtro = {}
    if q:
        filtro["animal"] = {"$regex": re.escape(q), "$options": "i"}
    if animal:
        filtro["animal"] = animal

    total = _pesajes().count_documents(filtro)
    paginas = max(1, math.ceil(total / POR_PAGINA))
    pagina = min(pagina, paginas)
    inicio = (pagina - 1) * POR_PAGINA
    filas = list(
        _pesajes().find(filtro).sort([("fecha", -1), ("creado_en", -1)]).skip(inicio).limit(POR_PAGINA)
    )
    ids = {p["animal"] for p in filas}
    nombres = {
        a["identificacion"]: a.get("nombre")
        for a in get_db().animales.find({"identificacion": {"$in": list(ids)}})
    }
    return render_template(
        "productivo/lista.html",
        filas=filas,
        nombres=nombres,
        q=q,
        animal=animal,
        pagina=pagina,
        paginas=paginas,
        numeros=numeros_de_pagina(pagina, paginas),
        total=total,
        inicio=inicio,
        del_mes=pesajes_del_mes(),
    )


@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@rol_required(ADMIN)
def nuevo():
    if request.method == "POST":
        v, errores, peso = validar(request.form)
        if not errores:
            try:
                _pesajes().insert_one(
                    {
                        "animal": v["animal"],
                        "fecha": parse_fecha(v["fecha"]),
                        "peso_kg": peso,
                        "tipo_peso": v["tipo_peso"],
                        "observaciones": v["observaciones"] or None,
                        "registrado_por": session["user"]["usuario"],
                        "creado_en": datetime.now(),
                    }
                )
            except DuplicateKeyError:
                errores["fecha"] = f"El animal {v['animal']} ya tiene un pesaje registrado en esa fecha."
                flash("Revisa los campos marcados.", "danger")
                return _form(v, errores)
            registrar_actividad(
                f"Se registró un pesaje: {v['animal']} · {v['peso_kg'].replace('.', ',')} kg",
                session["user"]["usuario"],
            )
            flash("Pesaje guardado.", "success")
            return redirect(url_for("productivo.lista"))
        flash("Revisa los campos marcados.", "danger")
        return _form(v, errores)

    valores = {campo: "" for campo in CAMPOS}
    valores["fecha"] = hoy().strftime("%Y-%m-%d")
    valores["tipo_peso"] = "Medido"
    valores["animal"] = request.args.get("animal", "").strip()
    return _form(valores, {})


@bp.route("/<pesaje_id>/eliminar", methods=["POST"])
@login_required
@rol_required(ADMIN)
def eliminar(pesaje_id):
    try:
        oid = ObjectId(pesaje_id)
    except (InvalidId, TypeError):
        flash("Ese pesaje no existe.", "warning")
        return redirect(url_for("productivo.lista"))

    pesaje = _pesajes().find_one({"_id": oid})
    if not pesaje:
        flash("Ese pesaje ya no existe.", "warning")
        return redirect(url_for("productivo.lista"))

    _pesajes().delete_one({"_id": oid})
    registrar_actividad(
        f"Se eliminó un pesaje: {pesaje['animal']} · {pesaje['peso_kg']} kg",
        session["user"]["usuario"],
    )
    flash("Pesaje eliminado.", "success")
    return redirect(url_for("productivo.lista"))
