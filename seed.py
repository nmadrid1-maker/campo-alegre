"""Crea los usuarios iniciales y unos animales de ejemplo.

Uso:  py seed.py            (usuarios + animales de ejemplo)
      py seed.py --solo-usuarios
Se puede ejecutar varias veces: no duplica lo que ya existe.
"""
import os
import sys

from campo_alegre import create_app
from campo_alegre.db import get_db
from campo_alegre.semilla import crear_animales_ejemplo, crear_usuarios

app = create_app()

with app.app_context():
    db = get_db()
    creados = crear_usuarios(
        db,
        os.environ.get("SEED_ADMIN_PASSWORD", "Admin2026!"),
        os.environ.get("SEED_EMPLEADO_PASSWORD", "Empleado2026!"),
    )
    print("Usuarios creados:", ", ".join(creados) if creados else "ninguno (ya existían)")
    if "--solo-usuarios" not in sys.argv:
        print("Animales de ejemplo creados:", crear_animales_ejemplo(db))
    print("Listo. Las contraseñas son las de SEED_*_PASSWORD en tu archivo .env.")
