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

bp = Blueprint("reproductivo", __name__, url_prefix="/reproductivo")

POR_PAGINA = 10
TIPOS = ("Servicio", "Diagnóstico de preñez", "Parto", "Aborto")
METODOS = ("Monta", "Inseminación artificial")
RESULTADOS = ("Preñada", "Vacía")
SEXOS_CRIA = ("Hembra", "Macho")
ESTADOS_CRIA = ("Viva", "Muerta")
GESTACION_DIAS = 283  # supuesto: gestación promedio bovina; confirmar con el administrador
DIAS_AVISO = 30

MODOS_PARTO = ("Desde servicio", "Fecha indicada", "Desconocida")
ESTADOS_REPRO = ("Gestante", "Vacía", "Parida", "En servicio", "Sin datos")

CAMPOS = (
    "animal", "tipo", "fecha", "metodo", "reproductor",
    "resultado", "parto_modo", "parto_estimado", "cria_sexo", "cria_estado", "observaciones",
)


def _eventos():
    return get_db().eventos_reproductivos


def _servicio_abierto(servicio):
    """True si después de ese servicio no hubo otro servicio, parto, aborto ni diagnóstico 'Vacía'."""
    posteriores = _eventos().count_documents(
        {
            "animal": servicio["animal"],
            "fecha": {"$gt": servicio["fecha"]},
            "$or": [
                {"tipo": {"$in": ["Servicio", "Parto", "Aborto"]}},
                {"tipo": "Diagnóstico de preñez", "resultado": "Vacía"},
            ],
        }
    )
    return posteriores == 0


def _recorrer(eventos):
    """Estado reproductivo a partir de los eventos de una hembra, de más antiguo a más reciente."""
    estado = {"estado": "Sin datos", "parto_estimado": None, "modo": None, "fecha": None}
    ultimo_servicio = None
    for e in eventos:
        if e["tipo"] == "Servicio":
            ultimo_servicio = e
            estado = {"estado": "En servicio", "parto_estimado": None, "modo": None, "fecha": e["fecha"]}
        elif e["tipo"] == "Diagnóstico de preñez" and e.get("resultado") == "Preñada":
            modo = e.get("parto_modo")
            estimado = e.get("parto_estimado")
            if modo is None and ultimo_servicio:  # registro anterior a la fecha de parto: se calcula del servicio
                modo, estimado = "Desde servicio", ultimo_servicio.get("parto_probable")
            estado = {"estado": "Gestante", "parto_estimado": estimado, "modo": modo or "Desconocida", "fecha": e["fecha"]}
        elif e["tipo"] == "Parto":
            estado = {"estado": "Parida", "parto_estimado": None, "modo": None, "fecha": e["fecha"]}
        else:  # aborto o diagnóstico Vacía
            estado = {"estado": "Vacía", "parto_estimado": None, "modo": None, "fecha": e["fecha"]}
    return estado


def estado_de(identificacion):
    eventos = _eventos().find({"animal": identificacion}).sort([("fecha", 1), ("creado_en", 1)])
    return _recorrer(list(eventos))


def estados_reproductivos():
    """{identificacion: estado} de las hembras que tienen eventos reproductivos."""
    por_animal = {}
    for e in _eventos().find({}).sort([("fecha", 1), ("creado_en", 1)]):
        por_animal.setdefault(e["animal"], []).append(e)
    return {ident: _recorrer(lista) for ident, lista in por_animal.items()}


def _hembras_activas():
    return {a["identificacion"] for a in get_db().animales.find({"estado": "Activa", "sexo": "Hembra"})}


def partos_probables():
    """Partos esperados en los próximos 30 días: de servicios 'abiertos' y de diagnósticos con fecha estimada."""
    desde = hoy()
    hasta = desde + timedelta(days=DIAS_AVISO)
    candidatos = _eventos().find(
        {"tipo": "Servicio", "parto_probable": {"$gte": desde, "$lte": hasta}}
    ).sort("parto_probable", 1)
    por_animal = {
        s["animal"]: {"animal": s["animal"], "fecha": s["fecha"], "parto_probable": s["parto_probable"], "origen": "servicio"}
        for s in candidatos if _servicio_abierto(s)
    }
    for ident, e in estados_reproductivos().items():
        if e["estado"] != "Gestante":
            continue
        if e["parto_estimado"] and desde <= e["parto_estimado"] <= hasta:
            por_animal[ident] = {"animal": ident, "fecha": e["fecha"], "parto_probable": e["parto_estimado"],
                                 "origen": "diagnóstico"}
        else:  # la fecha del diagnóstico manda sobre la del servicio
            por_animal.pop(ident, None)
    activas = _hembras_activas()
    return sorted((p for p in por_animal.values() if p["animal"] in activas), key=lambda p: p["parto_probable"])


def gestantes_sin_fecha():
    """Hembras activas gestantes cuya fecha de parto se registró como desconocida."""
    activas = _hembras_activas()
    return sorted(i for i, e in estados_reproductivos().items()
                  if e["estado"] == "Gestante" and not e["parto_estimado"] and i in activas)


def resumen():
    """(eventos de los últimos 30 días, cantidad de partos probables) para el inicio."""
    desde = hoy() - timedelta(days=DIAS_AVISO)
    recientes = _eventos().count_documents({"fecha": {"$gte": desde}})
    return recientes, len(partos_probables())


@bp.app_template_filter("detalle_repro")
def detalle(e):
    """Texto corto con lo propio de cada tipo de evento (para tablas e historial)."""
    if e["tipo"] == "Servicio":
        texto = e.get("metodo") or ""
        if e.get("reproductor"):
            texto += f" · {e['reproductor']}"
        if e.get("parto_probable"):
            texto += f" · parto probable {e['parto_probable'].strftime('%d/%m/%Y')}"
        return texto
    if e["tipo"] == "Diagnóstico de preñez":
        texto = e.get("resultado") or ""
        if e.get("resultado") == "Preñada" and e.get("parto_modo"):
            if e.get("parto_estimado"):
                texto += f" · parto estimado {e['parto_estimado'].strftime('%d/%m/%Y')}"
            else:
                texto += " · fecha de parto desconocida"
        return texto
    if e["tipo"] == "Parto":
        cria = e.get("cria_estado") or ""
        if e.get("cria_sexo"):
            cria = f"{e['cria_sexo']} {cria.lower()}"
        return f"Cría {cria}".strip()
    return ""


def _servicio_vigente(animal, fecha):
    """Último servicio de la hembra hasta `fecha` que no fue cerrado por parto, aborto o diagnóstico Vacía."""
    servicios = list(_eventos().find({"animal": animal, "tipo": "Servicio", "fecha": {"$lte": fecha}})
                     .sort("fecha", -1).limit(1))
    if not servicios:
        return None
    cierres = _eventos().count_documents({
        "animal": animal, "fecha": {"$gt": servicios[0]["fecha"], "$lte": fecha},
        "$or": [{"tipo": {"$in": ["Parto", "Aborto"]}}, {"tipo": "Diagnóstico de preñez", "resultado": "Vacía"}],
    })
    return None if cierres else servicios[0]


def _validar_parto(v, errores):
    """Fecha estimada de parto de un diagnóstico 'Preñada'. Deja la fecha calculada en v['_estimado']."""
    fecha = parse_fecha(v["fecha"])
    servicio = _servicio_vigente(v["animal"], fecha)
    if not v["parto_modo"]:
        v["parto_modo"] = "Desde servicio" if servicio else "Desconocida"
    v["_estimado"] = None
    if v["parto_modo"] not in MODOS_PARTO:
        errores["parto_modo"] = "Seleccione cómo se conoce la fecha estimada de parto."
    elif v["parto_modo"] == "Desde servicio":
        if not servicio:
            errores["parto_modo"] = "La hembra no tiene un servicio vigente para calcular la fecha. Indique la fecha o marque desconocida."
        else:
            v["_estimado"] = servicio["parto_probable"]
    elif v["parto_modo"] == "Fecha indicada":
        estimado = parse_fecha(v["parto_estimado"])
        if not estimado:
            errores["parto_estimado"] = "Indique la fecha estimada de parto."
        elif estimado < fecha:
            errores["parto_estimado"] = "La fecha de parto no puede ser anterior al diagnóstico."
        elif estimado > fecha + timedelta(days=GESTACION_DIAS):
            errores["parto_estimado"] = f"La fecha de parto no puede superar {GESTACION_DIAS} días desde el diagnóstico."
        else:
            v["_estimado"] = estimado


def validar(formulario):
    """Devuelve (valores, errores)."""
    v = {campo: formulario.get(campo, "").strip() for campo in CAMPOS}
    errores = {}

    animal, mensaje = validar_animal(v["animal"], solo_hembras=True)
    if mensaje:
        errores["animal"] = mensaje

    if v["tipo"] not in TIPOS:
        errores["tipo"] = "Seleccione el tipo de evento."

    _, mensaje = validar_fecha_evento(v["fecha"], animal, "del evento")
    if mensaje:
        errores["fecha"] = mensaje

    if v["tipo"] == "Servicio":
        if v["metodo"] not in METODOS:
            errores["metodo"] = "Seleccione el método (monta o inseminación artificial)."
        if len(v["reproductor"]) > 60:
            errores["reproductor"] = "El reproductor admite hasta 60 caracteres."
    elif v["tipo"] == "Diagnóstico de preñez":
        if v["resultado"] not in RESULTADOS:
            errores["resultado"] = "Seleccione el resultado del diagnóstico."
        elif v["resultado"] == "Preñada" and "fecha" not in errores and "animal" not in errores:
            _validar_parto(v, errores)
    elif v["tipo"] == "Parto":
        if v["cria_estado"] not in ESTADOS_CRIA:
            errores["cria_estado"] = "Indique si la cría nació viva o muerta."
        if v["cria_sexo"] and v["cria_sexo"] not in SEXOS_CRIA:
            errores["cria_sexo"] = "El sexo de la cría no es válido."

    if len(v["observaciones"]) > 500:
        errores["observaciones"] = "Las observaciones admiten hasta 500 caracteres."

    return v, errores


def _documento(v, usuario):
    tipo = v["tipo"]
    fecha = parse_fecha(v["fecha"])
    es_servicio = tipo == "Servicio"
    prenada = tipo == "Diagnóstico de preñez" and v["resultado"] == "Preñada"
    return {
        "animal": v["animal"],
        "tipo": tipo,
        "fecha": fecha,
        "metodo": v["metodo"] if es_servicio else None,
        "reproductor": (v["reproductor"] or None) if es_servicio else None,
        "parto_probable": fecha + timedelta(days=GESTACION_DIAS) if es_servicio else None,
        "resultado": v["resultado"] if tipo == "Diagnóstico de preñez" else None,
        "parto_modo": v["parto_modo"] if prenada else None,
        "parto_estimado": v.get("_estimado") if prenada else None,
        "cria_sexo": (v["cria_sexo"] or None) if tipo == "Parto" else None,
        "cria_estado": v["cria_estado"] if tipo == "Parto" else None,
        "observaciones": v["observaciones"] or None,
        "registrado_por": usuario,
        "creado_en": datetime.now(),
    }


def _form(valores, errores):
    return render_template(
        "reproductivo/form.html",
        v=valores,
        errores=errores,
        tipos=TIPOS,
        metodos=METODOS,
        resultados=RESULTADOS,
        sexos=SEXOS_CRIA,
        estados=ESTADOS_CRIA,
        animales=animales_activos(solo_hembras=True),
        gestacion=GESTACION_DIAS,
        modos_parto=MODOS_PARTO,
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
        filtro["$or"] = [{"animal": rx}, {"reproductor": rx}]
    if tipo in TIPOS:
        filtro["tipo"] = tipo
    if animal:
        filtro["animal"] = animal

    total = _eventos().count_documents(filtro)
    paginas = max(1, math.ceil(total / POR_PAGINA))
    pagina = min(pagina, paginas)
    inicio = (pagina - 1) * POR_PAGINA
    filas = list(
        _eventos().find(filtro).sort([("fecha", -1), ("creado_en", -1)]).skip(inicio).limit(POR_PAGINA)
    )

    probables = partos_probables()
    sin_fecha = gestantes_sin_fecha()
    ids = {e["animal"] for e in filas} | {e["animal"] for e in probables} | set(sin_fecha)
    nombres = {
        a["identificacion"]: a.get("nombre")
        for a in get_db().animales.find({"identificacion": {"$in": list(ids)}})
    }

    return render_template(
        "reproductivo/lista.html",
        filas=filas,
        nombres=nombres,
        probables=probables[:5],
        sin_fecha=sin_fecha,
        total_probables=len(probables),
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
            _eventos().insert_one(_documento(v, session["user"]["usuario"]))
            registrar_actividad(
                f"Se registró un evento reproductivo: {v['tipo']} (animal {v['animal']})",
                session["user"]["usuario"],
            )
            flash("Evento reproductivo guardado.", "success")
            return redirect(url_for("reproductivo.lista"))
        flash("Revisa los campos marcados.", "danger")
        return _form(v, errores)

    valores = {campo: "" for campo in CAMPOS}
    valores["tipo"] = "Servicio"
    valores["metodo"] = "Monta"
    valores["parto_modo"] = "Desde servicio"
    valores["fecha"] = hoy().strftime("%Y-%m-%d")
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
        return redirect(url_for("reproductivo.lista"))

    evento = _eventos().find_one({"_id": oid})
    if not evento:
        flash("Ese evento ya no existe.", "warning")
        return redirect(url_for("reproductivo.lista"))

    _eventos().delete_one({"_id": oid})
    registrar_actividad(
        f"Se eliminó un evento reproductivo: {evento['tipo']} (animal {evento['animal']})",
        session["user"]["usuario"],
    )
    flash("Evento eliminado.", "success")
    return redirect(url_for("reproductivo.lista"))
