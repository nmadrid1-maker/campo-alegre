from urllib.parse import urlencode
import csv
import io
from datetime import datetime

from flask import Blueprint, Response, abort, flash, render_template, request, session, url_for

from .db import get_db, registrar_actividad
from .filtros import edad as texto_edad
from .ganado import CATEGORIAS, ESTADOS, SEXOS
from .movimientos import TIPOS as TIPOS_MOV
from .movimientos import detalle as detalle_mov
from .reproductivo import ESTADOS_REPRO, estados_reproductivos
from .reproductivo import TIPOS as TIPOS_REPRO
from .reproductivo import detalle as detalle_repro
from .sanitario import TIPOS as TIPOS_SANI
from .security import ADMIN, EMPLEADO, login_required, rol_required
from .productivo import animales_en_rango, es_estimado, leer_rango_peso, ultimos_pesos
from .utils import parse_fecha

bp = Blueprint("informes", __name__, url_prefix="/informes")

MAX_PANTALLA = 500  # filas que se dibujan en pantalla; el CSV siempre sale completo

INFORMES = {
    "inventario": {
        "titulo": "Inventario de ganado",
        "descripcion": "Listado de animales con su categoría, estado y procedencia.",
        "filtros": ("sexo", "categoria", "estado", "potrero", "peso_min", "peso_max"),
    },
    "sanitario": {
        "titulo": "Control sanitario",
        "descripcion": "Vacunas, desparasitaciones y tratamientos aplicados.",
        "filtros": ("desde", "hasta", "tipo", "categoria", "potrero", "animal"),
    },
    "reproductivo": {
        "titulo": "Eventos reproductivos",
        "descripcion": "Servicios, diagnósticos de preñez, partos y abortos.",
        "filtros": ("desde", "hasta", "tipo", "estado_repro", "categoria", "potrero", "animal"),
    },
    "productivo": {
        "titulo": "Control productivo",
        "descripcion": "Pesajes registrados, con peso promedio, mínimo y máximo.",
        "filtros": ("desde", "hasta", "categoria", "potrero", "animal"),
    },
    "movimientos": {
        "titulo": "Movimientos del hato",
        "descripcion": "Nacimientos, entradas, salidas (venta, muerte, traslado) y novedades.",
        "filtros": ("desde", "hasta", "tipo", "categoria", "potrero", "animal"),
    },
}


def _fecha(valor):
    return valor.strftime("%d/%m/%Y") if valor else ""


def _kg(valor):
    return f"{valor:.1f}".rstrip("0").rstrip(".").replace(".", ",") if valor is not None else ""


def _leer_filtros(nombres):
    """Devuelve (valores, errores). Los valores inválidos se descartan."""
    v = {n: request.args.get(n, "").strip() for n in nombres}
    errores = []
    fechas = {}
    for campo, etiqueta in (("desde", "Desde"), ("hasta", "Hasta")):
        if campo in v and v[campo]:
            f = parse_fecha(v[campo])
            if not f:
                errores.append(f"La fecha “{etiqueta}” no es válida.")
                v[campo] = ""
            else:
                fechas[campo] = f
    if "desde" in fechas and "hasta" in fechas and fechas["desde"] > fechas["hasta"]:
        errores.append("La fecha “Desde” no puede ser posterior a “Hasta”.")
        v["desde"] = v["hasta"] = ""
        fechas = {}
    if "sexo" in v and v["sexo"] and v["sexo"] not in SEXOS:
        v["sexo"] = ""
    if "categoria" in v and v["categoria"] and v["categoria"] not in CATEGORIAS["Hembra"] + CATEGORIAS["Macho"]:
        v["categoria"] = ""
    if "estado" in v and v["estado"] and v["estado"] not in ESTADOS:
        v["estado"] = ""
    for campo in ("peso_min", "peso_max"):
        if campo in v:
            minimo, maximo = leer_rango_peso({campo: v[campo]})
            if (minimo if campo == "peso_min" else maximo) is None:
                v[campo] = ""
    if "estado_repro" in v and v["estado_repro"] and v["estado_repro"] not in ESTADOS_REPRO:
        v["estado_repro"] = ""
    if "tipo" in v and v["tipo"] and v["tipo"] not in (TIPOS_SANI + TIPOS_REPRO + TIPOS_MOV):
        v["tipo"] = ""
    return v, fechas, errores


def _rango(campo, fechas):
    if not fechas:
        return {}
    rango = {}
    if "desde" in fechas:
        rango["$gte"] = fechas["desde"]
    if "hasta" in fechas:
        rango["$lte"] = fechas["hasta"]
    return {campo: rango}


def _nombres(identificaciones):
    return {
        a["identificacion"]: a.get("nombre") or ""
        for a in get_db().animales.find({"identificacion": {"$in": list(identificaciones)}})
    }


def _conteo(items):
    """[(texto, n)] ordenado de mayor a menor."""
    cuenta = {}
    for i in items:
        cuenta[i] = cuenta.get(i, 0) + 1
    return sorted(cuenta.items(), key=lambda x: (-x[1], x[0]))


def informe_inventario(v, fechas):
    filtro = {}
    for campo in ("sexo", "categoria", "estado", "potrero"):
        if v[campo]:
            filtro[campo] = v[campo]
    minimo, maximo = leer_rango_peso(v)
    if minimo is not None or maximo is not None:
        filtro["identificacion"] = {"$in": animales_en_rango(minimo, maximo)}
    animales = list(get_db().animales.find(filtro).sort("identificacion", 1))
    pesos = ultimos_pesos([a["identificacion"] for a in animales])
    columnas = ["Identificación", "Nombre", "Sexo", "Categoría", "Potrero", "Peso actual (kg)", "Tipo de peso", "Estado", "Nacimiento", "Edad", "Ingreso", "Procedencia"]
    filas = [
        [a["identificacion"], a.get("nombre") or "", a["sexo"], a["categoria"], a.get("potrero") or "",
         _kg(pesos[a["identificacion"]]["peso_kg"]) if a["identificacion"] in pesos else "",
         ("Estimado" if es_estimado(pesos[a["identificacion"]]) else "Medido") if a["identificacion"] in pesos else "",
         a["estado"],
         _fecha(a.get("fecha_nacimiento")), texto_edad(a.get("fecha_nacimiento")) if a.get("fecha_nacimiento") else "",
         _fecha(a.get("fecha_ingreso")), a.get("procedencia") or ""]
        for a in animales
    ]
    resumen = [("Animales", len(animales))]
    resumen += [(f"Categoría {c}", n) for c, n in _conteo([a["categoria"] for a in animales])]
    resumen += [(f"Estado {e}", n) for e, n in _conteo([a["estado"] for a in animales])]
    resumen += [(f"Potrero {p}", n) for p, n in _conteo([a.get("potrero") or "Sin potrero" for a in animales])]
    return columnas, filas, resumen


def _filtrar_animales(filtro, v, permitidos=None):
    """Limita `filtro["animal"]` por animal, categoría y potrero (y por `permitidos`, si se da)."""
    if v.get("categoria") or v.get("potrero"):
        criterio = {c: v[c] for c in ("categoria", "potrero") if v.get(c)}
        ids = {a["identificacion"] for a in get_db().animales.find(criterio)}
        permitidos = ids if permitidos is None else permitidos & ids
    if v.get("animal"):
        permitidos = {v["animal"]} if permitidos is None else permitidos & {v["animal"]}
    if permitidos is not None:
        filtro["animal"] = {"$in": list(permitidos)}


def informe_sanitario(v, fechas):
    filtro = _rango("fecha_aplicacion", fechas)
    if v["tipo"] in TIPOS_SANI:
        filtro["tipo"] = v["tipo"]
    _filtrar_animales(filtro, v)
    eventos = list(get_db().eventos_sanitarios.find(filtro).sort([("fecha_aplicacion", -1), ("creado_en", -1)]))
    nombres = _nombres({e["animal"] for e in eventos})
    columnas = ["Fecha", "Animal", "Nombre", "Tipo", "Producto", "Próxima dosis", "Observaciones", "Registró"]
    filas = [
        [_fecha(e["fecha_aplicacion"]), e["animal"], nombres.get(e["animal"], ""), e["tipo"], e["producto"],
         _fecha(e.get("proxima_dosis")), e.get("observaciones") or "", e.get("registrado_por") or ""]
        for e in eventos
    ]
    resumen = [("Eventos", len(eventos)), ("Animales distintos", len({e["animal"] for e in eventos}))]
    resumen += [(t, n) for t, n in _conteo([e["tipo"] for e in eventos])]
    return columnas, filas, resumen


def informe_reproductivo(v, fechas):
    filtro = _rango("fecha", fechas)
    if v["tipo"] in TIPOS_REPRO:
        filtro["tipo"] = v["tipo"]
    estados = estados_reproductivos()
    permitidos = {i for i, e in estados.items() if e["estado"] == v["estado_repro"]} if v["estado_repro"] else None
    _filtrar_animales(filtro, v, permitidos)
    eventos = list(get_db().eventos_reproductivos.find(filtro).sort([("fecha", -1), ("creado_en", -1)]))
    nombres = _nombres({e["animal"] for e in eventos})
    columnas = ["Fecha", "Animal", "Nombre", "Tipo", "Detalle", "Observaciones", "Registró"]
    filas = [
        [_fecha(e["fecha"]), e["animal"], nombres.get(e["animal"], ""), e["tipo"], detalle_repro(e),
         e.get("observaciones") or "", e.get("registrado_por") or ""]
        for e in eventos
    ]
    resumen = [("Eventos", len(eventos)), ("Hembras distintas", len({e["animal"] for e in eventos}))]
    resumen += [(t, n) for t, n in _conteo([e["tipo"] for e in eventos])]
    resumen += [(f"Hembras {e.lower()} (hoy)", n) for e, n in _conteo([x["estado"] for x in estados.values()])]
    sin_fecha = sum(1 for x in estados.values() if x["estado"] == "Gestante" and not x["parto_estimado"])
    if sin_fecha:
        resumen.append(("Gestantes sin fecha de parto", sin_fecha))
    return columnas, filas, resumen


def informe_productivo(v, fechas):
    filtro = _rango("fecha", fechas)
    _filtrar_animales(filtro, v)
    pesajes = list(get_db().pesajes.find(filtro).sort([("fecha", -1), ("creado_en", -1)]))
    nombres = _nombres({p["animal"] for p in pesajes})
    columnas = ["Fecha", "Animal", "Nombre", "Peso (kg)", "Tipo de peso", "Observaciones", "Registró"]
    filas = [
        [_fecha(p["fecha"]), p["animal"], nombres.get(p["animal"], ""), _kg(p["peso_kg"]),
         p.get("tipo_peso") or "Medido", p.get("observaciones") or "", p.get("registrado_por") or ""]
        for p in pesajes
    ]
    resumen = [("Pesajes", len(pesajes)), ("Animales distintos", len({p["animal"] for p in pesajes}))]
    if pesajes:
        pesos = [p["peso_kg"] for p in pesajes]
        resumen += [
            ("Peso promedio (kg)", _kg(sum(pesos) / len(pesos))),
            ("Peso mínimo (kg)", _kg(min(pesos))),
            ("Peso máximo (kg)", _kg(max(pesos))),
        ]
    return columnas, filas, resumen


def informe_movimientos(v, fechas):
    filtro = _rango("fecha", fechas)
    if v["tipo"] in TIPOS_MOV:
        filtro["tipo"] = v["tipo"]
    _filtrar_animales(filtro, v)
    movs = list(get_db().movimientos.find(filtro).sort([("fecha", -1), ("creado_en", -1)]))
    nombres = _nombres({m["animal"] for m in movs})
    columnas = ["Fecha", "Animal", "Nombre", "Tipo", "Detalle", "Registró"]
    filas = [
        [_fecha(m["fecha"]), m["animal"], nombres.get(m["animal"], ""), m["tipo"], detalle_mov(m), m.get("registrado_por") or ""]
        for m in movs
    ]
    resumen = [("Movimientos", len(movs)), ("Animales distintos", len({m["animal"] for m in movs}))]
    resumen += [(t, n) for t, n in _conteo([m["tipo"] for m in movs])]
    resumen += [(f"Salida por {x}", n) for x, n in _conteo([m.get("motivo") for m in movs if m["tipo"] == "Salida"])]
    return columnas, filas, resumen


GENERADORES = {
    "inventario": informe_inventario,
    "sanitario": informe_sanitario,
    "reproductivo": informe_reproductivo,
    "productivo": informe_productivo,
    "movimientos": informe_movimientos,
}


def _csv(columnas, filas, nombre):
    salida = io.StringIO()
    # Punto y coma y BOM: así Excel en español abre las columnas y las tildes bien.
    escritor = csv.writer(salida, delimiter=";")
    escritor.writerow(columnas)
    for fila in filas:
        # Evita que Excel interprete una celda de texto como fórmula.
        escritor.writerow(["'" + c if isinstance(c, str) and c[:1] in ("=", "+", "-", "@") else c for c in fila])
    cuerpo = "﻿" + salida.getvalue()
    return Response(
        cuerpo,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@bp.route("/")
@login_required
@rol_required(ADMIN, EMPLEADO)
def indice():
    return render_template("informes/indice.html", informes=INFORMES)


@bp.route("/<tipo>")
@login_required
@rol_required(ADMIN, EMPLEADO)
def ver(tipo):
    if tipo not in INFORMES:
        abort(404)
    meta = INFORMES[tipo]
    v, fechas, errores = _leer_filtros(meta["filtros"])
    for e in errores:
        flash(e, "warning")
    columnas, filas, resumen = GENERADORES[tipo](v, fechas)

    if request.args.get("formato") == "csv":
        marca = datetime.now().strftime("%Y%m%d")
        registrar_actividad(f"Se exportó el informe: {meta['titulo']} ({len(filas)} filas)", session["user"]["usuario"])
        return _csv(columnas, filas, f"informe_{tipo}_{marca}.csv")

    parametros = {k: x for k, x in v.items() if x}
    exportar = url_for("informes.ver", tipo=tipo) + "?" + urlencode({**parametros, "formato": "csv"})
    return render_template(
        "informes/ver.html",
        tipo=tipo,
        meta=meta,
        v=v,
        columnas=columnas,
        filas=filas[:MAX_PANTALLA],
        total=len(filas),
        recortado=len(filas) > MAX_PANTALLA,
        max_pantalla=MAX_PANTALLA,
        resumen=resumen,
        exportar=exportar,
        sexos=SEXOS,
        categorias=CATEGORIAS["Hembra"] + CATEGORIAS["Macho"],
        estados=ESTADOS,
        estados_repro=ESTADOS_REPRO,
        potreros=[p["nombre"] for p in get_db().potreros.find({}).sort("nombre_lower", 1)],
        tipos={"sanitario": TIPOS_SANI, "movimientos": TIPOS_MOV}.get(tipo, TIPOS_REPRO),
        generado=datetime.now(),
    )
