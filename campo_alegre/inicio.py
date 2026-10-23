from flask import Blueprint, redirect, render_template, session, url_for

from .db import get_db
from .filtros import fecha_larga
from .productivo import pesajes_del_mes
from .respaldos import aviso_para_inicio
from .reproductivo import resumen as resumen_reproductivo
from .sanitario import contar_proximas_dosis
from .security import ADMIN, login_required

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
    eventos_repro, partos = resumen_reproductivo()
    return render_template(
        "inicio.html",
        total=total,
        activos=activos,
        actividades=actividades,
        proximas_vacunas=contar_proximas_dosis(),
        eventos_repro=eventos_repro,
        partos_probables=partos,
        pesajes_mes=pesajes_del_mes(),
        hoy=fecha_larga(),
        es_admin=session["user"]["rol"] == ADMIN,
        aviso_respaldo=aviso_para_inicio() if session["user"]["rol"] == ADMIN else None,
    )
