from datetime import datetime

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def fecha(valor):
    return valor.strftime("%d/%m/%Y") if valor else "—"


def fecha_hora(valor):
    return valor.strftime("%d/%m/%Y %H:%M") if valor else "—"


def fecha_input(valor):
    """Formato que entiende <input type="date">."""
    return valor.strftime("%Y-%m-%d") if valor else ""


def edad(nacimiento):
    if not nacimiento:
        return "—"
    hoy = datetime.now()
    meses = (hoy.year - nacimiento.year) * 12 + hoy.month - nacimiento.month
    if hoy.day < nacimiento.day:
        meses -= 1
    meses = max(meses, 0)
    anios, resto = divmod(meses, 12)
    partes = []
    if anios:
        partes.append(f"{anios} {'año' if anios == 1 else 'años'}")
    if resto or not anios:
        partes.append(f"{resto} {'mes' if resto == 1 else 'meses'}")
    return ", ".join(partes)


def fecha_larga(valor=None):
    valor = valor or datetime.now()
    return f"{DIAS[valor.weekday()].capitalize()} {valor.day} de {MESES[valor.month - 1]} de {valor.year}"


def kg(valor):
    """420.0 -> '420 kg'; 420.5 -> '420,5 kg'."""
    if valor is None:
        return "—"
    return f"{valor:.1f}".rstrip("0").rstrip(".").replace(".", ",") + " kg"


def cambio_kg(valor):
    """Cambio de peso con signo: +8 kg, -1,5 kg."""
    if valor is None:
        return "—"
    return f"{valor:+.1f}".rstrip("0").rstrip(".").replace(".", ",") + " kg"


def registrar_filtros(app):
    app.jinja_env.filters["fecha"] = fecha
    app.jinja_env.filters["fecha_hora"] = fecha_hora
    app.jinja_env.filters["fecha_input"] = fecha_input
    app.jinja_env.filters["edad"] = edad
    app.jinja_env.filters["kg"] = kg
    app.jinja_env.filters["cambio_kg"] = cambio_kg
