"""Datos iniciales: usuarios y algunos animales de ejemplo."""
from datetime import datetime

from werkzeug.security import generate_password_hash

from .security import ADMIN, EMPLEADO


def crear_usuarios(db, clave_admin, clave_empleado):
    usuarios = [
        {"usuario": "admin", "nombre": "Administrador", "rol": ADMIN, "clave": clave_admin},
        {"usuario": "empleado", "nombre": "Empleado", "rol": EMPLEADO, "clave": clave_empleado},
    ]
    creados = []
    for u in usuarios:
        if db.usuarios.find_one({"usuario": u["usuario"]}):
            continue
        db.usuarios.insert_one(
            {
                "usuario": u["usuario"],
                "nombre": u["nombre"],
                "rol": u["rol"],
                "password_hash": generate_password_hash(u["clave"]),
                "activo": True,
                "creado_en": datetime.now(),
            }
        )
        creados.append(u["usuario"])
    return creados


def _f(texto):
    return datetime.strptime(texto, "%d/%m/%Y")


EJEMPLOS = [
    ("125", "Luna", "Hembra", "Vaca", "Activa", "12/04/2023", "15/04/2023", "Finca Campo Alegre"),
    ("178", "Trueno", "Macho", "Toro", "Activa", "03/08/2021", "10/09/2021", "Compra"),
    ("204", "Estrella", "Hembra", "Novilla", "Activa", "21/01/2024", "21/01/2024", "Finca Campo Alegre"),
    ("221", "Manchas", "Hembra", "Vaca", "Activa", "09/06/2022", "02/07/2022", "Compra"),
    ("236", "Relámpago", "Macho", "Novillo", "Vendido", "14/02/2023", "14/02/2023", "Finca Campo Alegre"),
    ("248", "Nube", "Hembra", "Vaca", "Activa", "30/11/2021", "05/12/2021", "Compra"),
    ("251", "Canela", "Hembra", "Ternera", "Activa", "10/03/2026", "10/03/2026", "Finca Campo Alegre"),
    ("254", "Capitán", "Macho", "Ternero", "Activa", "22/04/2026", "22/04/2026", "Finca Campo Alegre"),
]


def crear_animales_ejemplo(db):
    n = 0
    for ident, nombre, sexo, cat, estado, nac, ing, proc in EJEMPLOS:
        if db.animales.find_one({"identificacion": ident}):
            continue
        ahora = datetime.now()
        db.animales.insert_one(
            {
                "identificacion": ident,
                "nombre": nombre,
                "sexo": sexo,
                "categoria": cat,
                "estado": estado,
                "fecha_nacimiento": _f(nac),
                "fecha_ingreso": _f(ing),
                "procedencia": proc,
                "observaciones": None,
                "creado_en": ahora,
                "actualizado_en": ahora,
            }
        )
        n += 1
    return n
