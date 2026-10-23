"""Copias de seguridad de la base de datos: automáticas, manuales, descarga y restauración.

Cada copia es un archivo .zip con un .json por colección y un info.json. No usa herramientas
externas (mongodump): solo Python, así funciona sin instalar nada más.
"""
import io
import json
import logging
import os
import re
import zipfile
from datetime import date, datetime, timedelta

from bson import ObjectId
from flask import (Blueprint, current_app, flash, redirect, render_template, request,
                   send_from_directory, session, url_for)

from .db import get_db, registrar_actividad
from .security import ADMIN, login_required, rol_required

bp = Blueprint("respaldos", __name__, url_prefix="/respaldos")
log = logging.getLogger(__name__)

COLECCIONES = (
    "usuarios", "animales", "potreros", "traslados", "eventos_sanitarios",
    "eventos_reproductivos", "pesajes", "movimientos", "actividad",
)
FORMATO = 1
ORIGENES = ("auto", "manual", "previo", "importado")
NOMBRE_RE = re.compile(r"^(auto|manual|previo|importado)_(\d{8})_(\d{6})\.zip$")
MAX_DESCOMPRIMIDO = 500 * 1024 * 1024
LOTE = 500
PALABRA_CONFIRMACION = "RESTAURAR"
ETIQUETAS = {"auto": "Automática", "manual": "Manual", "previo": "Antes de restaurar", "importado": "Importada"}
REINTENTO_MINUTOS = 30


# ---------- codificación ----------
def _codificar(o):
    if isinstance(o, datetime):
        return {"$date": o.isoformat()}
    if isinstance(o, ObjectId):
        return {"$oid": str(o)}
    raise TypeError(f"No se puede guardar un valor de tipo {type(o).__name__}")


def _decodificar(d):
    if len(d) == 1:
        if "$date" in d:
            return datetime.fromisoformat(d["$date"])
        if "$oid" in d:
            return ObjectId(d["$oid"])
    return d


# ---------- carpeta y listado ----------
def carpeta():
    ruta = current_app.config["RESPALDOS_DIR"]
    os.makedirs(ruta, exist_ok=True)
    return ruta


def _fecha_de_nombre(nombre):
    m = NOMBRE_RE.match(nombre)
    return datetime.strptime(m.group(2) + m.group(3), "%Y%m%d%H%M%S")


def listar():
    """Copias disponibles, de la más reciente a la más antigua."""
    ruta = carpeta()
    filas = []
    for nombre in os.listdir(ruta):
        m = NOMBRE_RE.match(nombre)
        if not m:
            continue
        info = {}
        try:
            with zipfile.ZipFile(os.path.join(ruta, nombre)) as z:
                info = json.loads(z.read("info.json"))
        except Exception:  # archivo dañado: se muestra igual, sin conteos
            info = {"dañado": True}
        filas.append({
            "nombre": nombre, "origen": m.group(1), "etiqueta": ETIQUETAS[m.group(1)],
            "fecha": _fecha_de_nombre(nombre), "tamano": os.path.getsize(os.path.join(ruta, nombre)),
            "conteos": info.get("conteos") or {}, "usuario": info.get("usuario"), "danado": bool(info.get("dañado")),
        })
    return sorted(filas, key=lambda f: f["fecha"], reverse=True)


def ultima_copia():
    copias = listar()
    return copias[0] if copias else None


def aviso_para_inicio():
    """Texto de aviso si la última copia es vieja o no existe; None si todo está al día."""
    try:
        ultima = ultima_copia()
    except OSError:
        return "No se puede leer la carpeta de copias de seguridad. Revisa la sección Respaldos."
    if not ultima:
        return "Todavía no hay copias de seguridad. Entra a Respaldos y crea la primera."
    dias = (datetime.now().date() - ultima["fecha"].date()).days
    if dias >= 3:
        return f"La última copia de seguridad fue hace {dias} días. Revisa la sección Respaldos."
    return None


# ---------- crear ----------
def crear(origen="manual", usuario=None):
    """Guarda una copia completa y devuelve el nombre del archivo."""
    db = get_db()
    ahora = datetime.now()
    conteos, contenido = {}, {}
    for nombre in COLECCIONES:
        docs = list(getattr(db, nombre).find({}))
        conteos[nombre] = len(docs)
        contenido[nombre] = json.dumps(docs, default=_codificar, ensure_ascii=False)
    info = {"formato": FORMATO, "creado": ahora.isoformat(), "origen": origen, "usuario": usuario, "conteos": conteos}

    ruta = carpeta()
    base = f"{origen}_{ahora.strftime('%Y%m%d_%H%M%S')}"
    nombre = f"{base}.zip"
    n = 1
    while os.path.exists(os.path.join(ruta, nombre)):  # dos copias en el mismo segundo
        ahora += timedelta(seconds=1)
        nombre = f"{origen}_{ahora.strftime('%Y%m%d_%H%M%S')}.zip"
        n += 1
    temporal = os.path.join(ruta, nombre + ".tmp")
    with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("info.json", json.dumps(info, ensure_ascii=False, indent=2))
        for coleccion, texto in contenido.items():
            z.writestr(f"{coleccion}.json", texto)
    os.replace(temporal, os.path.join(ruta, nombre))  # así nunca queda una copia a medio escribir
    limpiar()
    return nombre


def limpiar():
    """Borra las copias más antiguas según los límites de la configuración."""
    limites = {
        "auto": current_app.config["RESPALDOS_CONSERVAR_AUTO"],
        "manual": current_app.config["RESPALDOS_CONSERVAR_MANUAL"],
        "previo": 10,
        "importado": 10,
    }
    ruta = carpeta()
    por_origen = {}
    for c in listar():
        por_origen.setdefault(c["origen"], []).append(c)
    for origen, copias in por_origen.items():
        for vieja in copias[limites[origen]:]:
            try:
                os.remove(os.path.join(ruta, vieja["nombre"]))
            except OSError:
                log.warning("No se pudo borrar la copia antigua %s", vieja["nombre"])


# ---------- leer y restaurar ----------
def leer(origen_archivo):
    """Valida una copia (ruta o archivo en memoria). Devuelve (info, {coleccion: [documentos]}).

    Lanza ValueError con un mensaje en español si algo no es válido. No toca la base de datos.
    """
    try:
        z = zipfile.ZipFile(origen_archivo)
    except (zipfile.BadZipFile, OSError):
        raise ValueError("El archivo no es una copia de seguridad válida (no se pudo abrir el .zip).")
    with z:
        nombres = set(z.namelist())
        permitidos = {"info.json"} | {f"{c}.json" for c in COLECCIONES}
        if "info.json" not in nombres:
            raise ValueError("El archivo no es una copia de Campo Alegre (falta info.json).")
        if nombres - permitidos:
            raise ValueError("El archivo contiene elementos que no pertenecen a una copia de Campo Alegre.")
        if sum(i.file_size for i in z.infolist()) > MAX_DESCOMPRIMIDO:
            raise ValueError("El archivo es demasiado grande para ser una copia válida.")
        try:
            info = json.loads(z.read("info.json"))
        except ValueError:
            raise ValueError("El archivo info.json de la copia está dañado.")
        if not isinstance(info, dict) or info.get("formato") != FORMATO:
            raise ValueError("La copia es de un formato que este sistema no reconoce.")
        datos = {}
        for coleccion in COLECCIONES:
            if f"{coleccion}.json" not in nombres:
                raise ValueError(f"A la copia le falta la información de “{coleccion}”.")
            try:
                docs = json.loads(z.read(f"{coleccion}.json"), object_hook=_decodificar)
            except (ValueError, KeyError, TypeError):
                raise ValueError(f"La información de “{coleccion}” en la copia está dañada.")
            if not isinstance(docs, list) or not all(isinstance(d, dict) for d in docs):
                raise ValueError(f"La información de “{coleccion}” en la copia está dañada.")
            datos[coleccion] = docs
    return info, datos


def _cargar(datos):
    db = get_db()
    for coleccion in COLECCIONES:
        col = getattr(db, coleccion)
        col.delete_many({})
        docs = datos[coleccion]
        for i in range(0, len(docs), LOTE):
            col.insert_many(docs[i:i + LOTE])


def restaurar(ruta, usuario=None):
    """Reemplaza los datos actuales por los de la copia. Antes guarda una copia 'previo'.

    Si algo falla a la mitad, intenta volver al estado anterior.
    """
    _, datos = leer(ruta)  # se valida todo antes de borrar nada
    previo = crear("previo", usuario)
    try:
        _cargar(datos)
    except Exception:
        log.exception("Falló la restauración; se vuelve al estado anterior")
        _, antes = leer(os.path.join(carpeta(), previo))
        _cargar(antes)
        raise
    return previo


# ---------- copia automática ----------
def _hay_auto_de_hoy():
    hoy = date.today().strftime("%Y%m%d")
    return any(c["origen"] == "auto" and c["fecha"].strftime("%Y%m%d") == hoy for c in listar())


def init_respaldos(app):
    @app.before_request
    def copia_automatica():
        if not app.config.get("RESPALDO_AUTOMATICO") or request.endpoint in (None, "static"):
            return
        estado = app.extensions.setdefault("respaldo_auto", {"dia": None, "proximo": None, "error": None})
        ahora = datetime.now()
        if estado["dia"] == date.today() or (estado["proximo"] and ahora < estado["proximo"]):
            return
        try:
            if not _hay_auto_de_hoy():
                crear("auto", "automático")
            estado.update(dia=date.today(), error=None, proximo=None)
        except Exception as exc:  # una copia que falla nunca debe tumbar la página
            log.exception("No se pudo hacer la copia automática")
            estado.update(error=f"{type(exc).__name__}: {exc}", proximo=ahora + timedelta(minutes=REINTENTO_MINUTOS))


# ---------- pantallas ----------
def _nombre_valido(nombre):
    return bool(NOMBRE_RE.match(nombre)) and os.path.isfile(os.path.join(carpeta(), nombre))


@bp.route("/")
@login_required
@rol_required(ADMIN)
def lista():
    estado = current_app.extensions.get("respaldo_auto", {})
    try:
        copias = listar()
    except OSError as exc:
        flash(f"No se puede leer la carpeta de copias: {exc}", "danger")
        copias = []
    return render_template(
        "respaldos/lista.html", copias=copias, carpeta=os.path.abspath(current_app.config["RESPALDOS_DIR"]),
        error_auto=estado.get("error"), automatico=current_app.config["RESPALDO_AUTOMATICO"],
        conservar_auto=current_app.config["RESPALDOS_CONSERVAR_AUTO"],
        conservar_manual=current_app.config["RESPALDOS_CONSERVAR_MANUAL"],
        palabra=PALABRA_CONFIRMACION,
    )


@bp.route("/crear", methods=["POST"])
@login_required
@rol_required(ADMIN)
def crear_ahora():
    try:
        nombre = crear("manual", session["user"]["usuario"])
    except OSError as exc:
        flash(f"No se pudo guardar la copia: {exc}", "danger")
        return redirect(url_for("respaldos.lista"))
    registrar_actividad(f"Se creó una copia de seguridad ({nombre})", session["user"]["usuario"])
    flash("Copia de seguridad creada.", "success")
    return redirect(url_for("respaldos.lista"))


@bp.route("/<nombre>/descargar")
@login_required
@rol_required(ADMIN)
def descargar(nombre):
    if not _nombre_valido(nombre):
        flash("Esa copia no existe.", "warning")
        return redirect(url_for("respaldos.lista"))
    registrar_actividad(f"Se descargó la copia de seguridad {nombre}", session["user"]["usuario"])
    return send_from_directory(os.path.abspath(carpeta()), nombre, as_attachment=True)


@bp.route("/subir", methods=["POST"])
@login_required
@rol_required(ADMIN)
def subir():
    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename:
        flash("Elija el archivo de la copia (.zip).", "warning")
        return redirect(url_for("respaldos.lista"))
    contenido = archivo.read()
    try:
        leer(io.BytesIO(contenido))
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("respaldos.lista"))
    ahora = datetime.now()
    ruta = carpeta()
    nombre = f"importado_{ahora.strftime('%Y%m%d_%H%M%S')}.zip"
    while os.path.exists(os.path.join(ruta, nombre)):
        ahora += timedelta(seconds=1)
        nombre = f"importado_{ahora.strftime('%Y%m%d_%H%M%S')}.zip"
    with open(os.path.join(ruta, nombre), "wb") as f:
        f.write(contenido)
    limpiar()
    registrar_actividad(f"Se cargó una copia de seguridad desde un archivo ({nombre})", session["user"]["usuario"])
    flash("Copia cargada. Aparece en la lista; desde ahí puedes restaurarla.", "success")
    return redirect(url_for("respaldos.lista"))


@bp.route("/<nombre>/restaurar", methods=["POST"])
@login_required
@rol_required(ADMIN)
def restaurar_copia(nombre):
    if not _nombre_valido(nombre):
        flash("Esa copia no existe.", "warning")
        return redirect(url_for("respaldos.lista"))
    if request.form.get("confirmacion", "").strip() != PALABRA_CONFIRMACION:
        flash(f"Para restaurar escriba la palabra {PALABRA_CONFIRMACION} en el recuadro. No se cambió nada.", "warning")
        return redirect(url_for("respaldos.lista"))
    usuario = session["user"]["usuario"]
    try:
        previo = restaurar(os.path.join(carpeta(), nombre), usuario)
    except ValueError as exc:
        flash(f"No se restauró nada: {exc}", "danger")
        return redirect(url_for("respaldos.lista"))
    except Exception as exc:
        flash(f"La restauración falló y se volvió al estado anterior: {exc}", "danger")
        return redirect(url_for("respaldos.lista"))
    registrar_actividad(f"Se restauró la copia de seguridad {nombre}", usuario)
    flash(
        f"Copia restaurada. Antes de hacerlo se guardó el estado anterior como {previo}. "
        "Si el usuario con el que entraste no existe en esa copia, tendrás que volver a iniciar sesión.",
        "success",
    )
    return redirect(url_for("respaldos.lista"))
