from flask import Blueprint, redirect, render_template, session, url_for

from .db import get_db
from .filtros import fecha_larga
from .security import ADMIN, EMPLEADO, login_required, rol_required

bp = Blueprint("inicio", __name__)


@bp.route("/")
def raiz():
    return redirect(url_for("inicio.inicio"))


@bp.route("/inicio")
@login_required
def inicio():
    db = get_db()
    total = db.animales.count_documents({})
    activos = db.animales.count_documents({"estado": "Activa"})
    actividades = list(db.actividad.find().sort("fecha", -1).limit(5))
    return render_template(
        "inicio.html",
        total=total,
        activos=activos,
        actividades=actividades,
        hoy=fecha_larga(),
        es_admin=session["user"]["rol"] == ADMIN,
    )


# Secciones que aún no se construyen: muestran una pantalla "en construcción"
# con lo que va a incluir cada una.
PENDIENTES = {
    "sanitario": {
        "titulo": "Control sanitario",
        "resumen": "Vacunas, desparasitaciones y tratamientos de cada animal.",
        "incluira": ["Registrar un evento sanitario", "Historial por animal", "Próximas dosis"],
        "roles": (ADMIN, EMPLEADO),
    },
    "reproductivo": {
        "titulo": "Control reproductivo",
        "resumen": "Servicios, partos y crías de cada hembra.",
        "incluira": ["Registrar inseminación o monta", "Registrar parto y cría", "Fechas probables de parto"],
        "roles": (ADMIN, EMPLEADO),
    },
    "productivo": {
        "titulo": "Control productivo",
        "resumen": "Pesajes y producción del hato.",
        "incluira": ["Registrar pesaje", "Evolución de peso por animal"],
        "roles": (ADMIN, EMPLEADO),
    },
    "informes": {
        "titulo": "Informes",
        "resumen": "Informes del hato con filtros por fecha, categoría y estado.",
        "incluira": ["Inventario de ganado", "Control sanitario", "Eventos reproductivos", "Control productivo"],
        "roles": (ADMIN,),
    },
    "usuarios": {
        "titulo": "Usuarios",
        "resumen": "Cuentas del sistema y sus roles.",
        "incluira": ["Crear y desactivar usuarios", "Asignar rol Administrador o Empleado", "Restablecer contraseña"],
        "roles": (ADMIN,),
    },
    "configuracion": {
        "titulo": "Configuración",
        "resumen": "Parámetros generales de la finca.",
        "incluira": ["Datos de la finca", "Categorías y procedencias disponibles"],
        "roles": (ADMIN,),
    },
}


def _crear_vista(clave, datos):
    @login_required
    @rol_required(*datos["roles"])
    def vista():
        return render_template("pendiente.html", **datos)

    vista.__name__ = clave
    return vista


for _clave, _datos in PENDIENTES.items():
    bp.add_url_rule(f"/{_clave}", endpoint=_clave, view_func=_crear_vista(_clave, _datos))
