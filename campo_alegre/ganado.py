import math
import re
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from pymongo.errors import DuplicateKeyError

from .db import get_db, registrar_actividad
from .movimientos import detalle as detalle_mov
from .movimientos import registrar_alta
from .reproductivo import ESTADOS_REPRO, estado_de, estados_reproductivos
from .potreros import nombres_activos, registrar_traslado
from .productivo import PATRON_PESO, PESO_MAX, PESO_MIN, TIPOS_PESO, animales_en_rango, es_estimado, historial, leer_rango_peso, ultimos_pesos
from .reproductivo import detalle as detalle_repro
from .security import ADMIN, EMPLEADO, login_required, rol_required
from .utils import paginas as numeros_de_pagina
from .utils import hoy, parse_fecha

bp = Blueprint("ganado", __name__, url_prefix="/ganado")

POR_PAGINA = 6
SEXOS = ("Hembra", "Macho")
CATEGORIAS = {
    "Hembra": ("Vaca", "Novilla", "Ternera"),
    "Macho": ("Toro", "Novillo", "Ternero"),
}
ESTADOS = ("Activa", "Vendido", "Fallecido", "Trasladado", "Retirado")
PROCEDENCIAS = ("Finca Campo Alegre", "Compra", "Donación")
IDENTIFICACION_RE = re.compile(r"^[A-Za-z0-9-]{1,20}$")

CAMPOS = (
    "identificacion", "nombre", "sexo", "categoria", "fecha_nacimiento",
    "fecha_ingreso", "procedencia", "potrero", "marca", "madre", "estado", "peso_kg", "tipo_peso", "observaciones",
)


def _animales():
    return get_db().animales


def validar(formulario, editando=False, potrero_actual=""):
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
    nacimiento = parse_fecha(v["fecha_nacimiento"])
    ingreso = parse_fecha(v["fecha_ingreso"])
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
    if v["potrero"] and v["potrero"] != potrero_actual and v["potrero"] not in nombres_activos():
        errores["potrero"] = "Seleccione un potrero de la lista."
    if v["estado"] not in ESTADOS:
        errores["estado"] = "Seleccione un estado de la lista."
    if v["madre"]:
        madre = _animales().find_one({"identificacion": v["madre"]})
        if v["madre"] == v["identificacion"]:
            errores["madre"] = "Un animal no puede ser su propia madre."
        elif not madre:
            errores["madre"] = f"No existe un animal con la identificación {v['madre']}."
        elif madre["sexo"] != "Hembra":
            errores["madre"] = "La madre debe ser una hembra."
        elif nacimiento and madre.get("fecha_nacimiento") and nacimiento <= madre["fecha_nacimiento"]:
            errores["madre"] = "La madre debe haber nacido antes que la cría."
    if not editando and v["peso_kg"]:
        if not PATRON_PESO.match(v["peso_kg"]):
            errores["peso_kg"] = "Escriba el peso en kilogramos, con un decimal como máximo. Ej: 420 o 420,5."
        elif not PESO_MIN <= float(v["peso_kg"].replace(",", ".")) <= PESO_MAX:
            errores["peso_kg"] = f"El peso debe estar entre {PESO_MIN} y {PESO_MAX} kg."
        if v["tipo_peso"] not in TIPOS_PESO:
            errores["tipo_peso"] = "Indique si el peso fue medido o estimado."
    if len(v["marca"]) > 40:
        errores["marca"] = "La marca admite hasta 40 caracteres."

    if len(v["observaciones"]) > 500:
        errores["observaciones"] = "Las observaciones admiten hasta 500 caracteres."

    return v, errores


def _documento(v):
    return {
        "nombre": v["nombre"] or None,
        "sexo": v["sexo"],
        "categoria": v["categoria"],
        "estado": v["estado"],
        "fecha_nacimiento": parse_fecha(v["fecha_nacimiento"]),
        "fecha_ingreso": parse_fecha(v["fecha_ingreso"]),
        "procedencia": v["procedencia"] or None,
        "potrero": v["potrero"] or None,
        "marca": v["marca"] or None,
        "madre": v["madre"] or None,
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
        "potrero": a.get("potrero") or "",
        "marca": a.get("marca") or "",
        "madre": a.get("madre") or "",
        "estado": a["estado"],
        "observaciones": a.get("observaciones") or "",
    }


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
        potreros=nombres_activos(valores.get("potrero")),
        tipos_peso=TIPOS_PESO,
        peso_min=PESO_MIN,
        peso_max=PESO_MAX,
    )


@bp.route("/")
@login_required
@rol_required(ADMIN, EMPLEADO)
def lista():
    q = request.args.get("q", "").strip()
    potrero = request.args.get("potrero", "").strip()
    pagina = max(1, request.args.get("page", 1, type=int))

    filtro = {}
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        filtro = {"$or": [{"identificacion": rx}, {"nombre": rx}, {"categoria": rx}]}
    if potrero:
        filtro["potrero"] = potrero
    peso_min, peso_max = leer_rango_peso(request.args)
    permitidos = None
    if peso_min is not None or peso_max is not None:
        permitidos = set(animales_en_rango(peso_min, peso_max))
    repro = request.args.get("repro", "").strip()
    if repro in ESTADOS_REPRO:
        con_estado = {i for i, e in estados_reproductivos().items() if e["estado"] == repro}
        if repro == "Sin datos":
            hembras = {a["identificacion"] for a in _animales().find({"sexo": "Hembra"})}
            con_estado = hembras - set(estados_reproductivos())
        permitidos = con_estado if permitidos is None else permitidos & con_estado
    else:
        repro = ""
    if permitidos is not None:
        filtro["identificacion"] = {"$in": list(permitidos)}

    total = _animales().count_documents(filtro)
    paginas = max(1, math.ceil(total / POR_PAGINA))
    pagina = min(pagina, paginas)
    inicio = (pagina - 1) * POR_PAGINA
    filas = list(
        _animales().find(filtro).sort("creado_en", -1).skip(inicio).limit(POR_PAGINA)
    )
    pesos = ultimos_pesos([a["identificacion"] for a in filas])
    return render_template(
        "ganado/lista.html",
        filas=filas,
        pesos=pesos,
        repro=repro,
        estados_repro=ESTADOS_REPRO,
        peso_min=request.args.get("peso_min", "").strip() if peso_min is not None else "",
        peso_max=request.args.get("peso_max", "").strip() if peso_max is not None else "",
        q=q,
        potrero=potrero,
        potreros=[p["nombre"] for p in get_db().potreros.find({}).sort("nombre_lower", 1)],
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
                registrar_alta(documento, session["user"]["usuario"])
                if v["peso_kg"]:
                    get_db().pesajes.insert_one({
                        "animal": v["identificacion"], "fecha": hoy(),
                        "peso_kg": float(v["peso_kg"].replace(",", ".")), "tipo_peso": v["tipo_peso"],
                        "observaciones": "Peso al registrar el animal",
                        "registrado_por": session["user"]["usuario"], "creado_en": datetime.now(),
                    })
                if v["potrero"]:
                    registrar_traslado(v["identificacion"], None, v["potrero"], session["user"]["usuario"])
                flash(f"Animal {v['identificacion']} guardado.", "success")
                return redirect(url_for("ganado.ficha", identificacion=v["identificacion"]))
        flash("Revisa los campos marcados.", "danger")
        return _form("Registrar nuevo animal", v, errores, editando=False)

    valores = {campo: "" for campo in CAMPOS}
    valores["estado"] = "Activa"
    valores["tipo_peso"] = "Medido"
    return _form("Registrar nuevo animal", valores, {}, editando=False)


def _linea_de_tiempo(animal, limite=15):
    """Historial combinado: ingreso, eventos sanitarios, reproductivos y pesajes (lo más reciente primero)."""
    ident = animal["identificacion"]
    db = get_db()
    items = []
    for e in db.eventos_sanitarios.find({"animal": ident}):
        items.append((e["fecha_aplicacion"], "Sanitario", f"{e['tipo']} · {e['producto']}"))
    for e in db.eventos_reproductivos.find({"animal": ident}):
        extra = detalle_repro(e)
        items.append((e["fecha"], "Reproductivo", e["tipo"] + (f" · {extra}" if extra else "")))
    for p in db.pesajes.find({"animal": ident}):
        items.append((p["fecha"], "Pesaje", f"{p['peso_kg']:g} kg".replace(".", ",")))
    for t in db.traslados.find({"animal": ident}):
        origen = t.get("desde")
        destino = t.get("hacia") or "sin potrero"
        items.append((t["fecha"], "Traslado", f"{origen} → {destino}" if origen else f"Ubicado en {destino}"))
    for m in db.movimientos.find({"animal": ident}):
        items.append((m["fecha"], m["tipo"], detalle_mov(m)))
    if animal.get("fecha_ingreso"):
        items.append((animal["fecha_ingreso"], "Ingreso", animal.get("procedencia") or "Ingreso a la finca"))
    items.sort(key=lambda x: x[0], reverse=True)
    return items[:limite], len(items)


@bp.route("/<identificacion>")
@login_required
@rol_required(ADMIN, EMPLEADO)
def ficha(identificacion):
    animal = _animales().find_one({"identificacion": identificacion})
    if not animal:
        abort(404)
    eventos_col = get_db().eventos_sanitarios
    eventos = list(
        eventos_col.find({"animal": identificacion})
        .sort([("fecha_aplicacion", -1), ("creado_en", -1)])
        .limit(10)
    )
    total_eventos = eventos_col.count_documents({"animal": identificacion})

    reproductivos, total_repro = [], 0
    if animal["sexo"] == "Hembra":
        repro_col = get_db().eventos_reproductivos
        reproductivos = list(
            repro_col.find({"animal": identificacion}).sort([("fecha", -1), ("creado_en", -1)]).limit(10)
        )
        total_repro = repro_col.count_documents({"animal": identificacion})

    todos_pesajes = historial(identificacion)
    pesajes = todos_pesajes[:10]
    peso_actual = todos_pesajes[0] if todos_pesajes else None

    crias = list(_animales().find({"madre": identificacion}).sort("fecha_nacimiento", -1))
    return render_template(
        "ganado/ficha.html",
        a=animal,
        crias=crias,
        estado_repro=estado_de(identificacion) if animal["sexo"] == "Hembra" else None,
        eventos=eventos,
        total_eventos=total_eventos,
        reproductivos=reproductivos,
        total_repro=total_repro,
        pesajes=pesajes,
        total_pesajes=len(todos_pesajes),
        peso_actual=peso_actual,
        linea=_linea_de_tiempo(animal),
    )


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
        v, errores = validar(formulario, editando=True, potrero_actual=animal.get("potrero") or "")
        if not errores:
            cambios = _documento(v)
            cambios["actualizado_en"] = datetime.now()
            _animales().update_one({"identificacion": identificacion}, {"$set": cambios})
            if (cambios["potrero"] or None) != (animal.get("potrero") or None):
                registrar_traslado(identificacion, animal.get("potrero"), cambios["potrero"], session["user"]["usuario"])
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
    db = get_db()
    if (
        db.eventos_sanitarios.count_documents({"animal": identificacion})
        or db.eventos_reproductivos.count_documents({"animal": identificacion})
        or db.pesajes.count_documents({"animal": identificacion})
        or db.movimientos.count_documents({"animal": identificacion, "tipo": {"$in": ["Salida", "Novedad"]}})
    ):
        flash(
            "No se puede eliminar: el animal tiene eventos sanitarios, reproductivos, pesajes, salidas o novedades registrados. "
            "Si ya no está en la finca, cambia su estado a Vendido o Fallecido en “Editar información”.",
            "warning",
        )
        return redirect(url_for("ganado.ficha", identificacion=identificacion))
    resultado = _animales().delete_one({"identificacion": identificacion})
    if resultado.deleted_count:
        db.traslados.delete_many({"animal": identificacion})
        db.movimientos.delete_many({"animal": identificacion})
        registrar_actividad(
            f"Se eliminó el animal (ID: {identificacion})", session["user"]["usuario"]
        )
        flash(f"Animal {identificacion} eliminado.", "success")
    else:
        flash("Ese animal ya no existe.", "warning")
    return redirect(url_for("ganado.lista"))
