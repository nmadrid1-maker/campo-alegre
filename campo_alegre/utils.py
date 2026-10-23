"""Funciones que usan varios módulos."""
from datetime import datetime

from .db import get_db


def parse_fecha(texto):
    """Convierte 'AAAA-MM-DD' (lo que envía <input type="date">) en datetime, o None."""
    try:
        return datetime.strptime(texto, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def hoy():
    """La fecha de hoy a las 00:00, para comparar con las fechas guardadas."""
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def paginas(actual, total):
    """Números de página a mostrar; None es un hueco ('…')."""
    visibles = [n for n in range(1, total + 1) if n <= 2 or n > total - 1 or abs(n - actual) <= 1]
    salida, previo = [], 0
    for n in visibles:
        if n - previo > 1:
            salida.append(None)
        salida.append(n)
        previo = n
    return salida


def validar_animal(identificacion, solo_hembras=False):
    """Revisa que el animal exista y esté activo. Devuelve (animal, mensaje_de_error)."""
    if not identificacion:
        return None, "Escriba la identificación del animal."
    animal = get_db().animales.find_one({"identificacion": identificacion})
    if not animal:
        return None, f"No existe un animal con la identificación {identificacion}."
    if animal["estado"] != "Activa":
        return animal, f"El animal {identificacion} figura como {animal['estado']}."
    if solo_hembras and animal["sexo"] != "Hembra":
        return animal, (
            f"El animal {identificacion} es macho; los eventos reproductivos solo se registran a hembras."
        )
    return animal, None


def validar_fecha_evento(texto, animal, nombre):
    """Fecha de un evento: obligatoria, no futura y no anterior al nacimiento del animal.

    `nombre` completa los mensajes, por ejemplo 'de aplicación' o 'del pesaje'.
    Devuelve (fecha, mensaje_de_error).
    """
    fecha = parse_fecha(texto)
    if not fecha:
        return None, f"Indique la fecha {nombre}."
    if fecha > datetime.now():
        return fecha, f"La fecha {nombre} no puede ser futura."
    nacimiento = animal.get("fecha_nacimiento") if animal else None
    if nacimiento and fecha < nacimiento:
        return fecha, f"La fecha {nombre} no puede ser anterior al nacimiento del animal."
    return fecha, None


def animales_activos(solo_hembras=False):
    """Animales para la lista desplegable de los formularios."""
    filtro = {"estado": "Activa"}
    if solo_hembras:
        filtro["sexo"] = "Hembra"
    return list(
        get_db()
        .animales.find(filtro, {"identificacion": 1, "nombre": 1, "categoria": 1})
        .sort("identificacion", 1)
    )
