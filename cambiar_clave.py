"""Cambia la contraseña de un usuario, sin depender de lo que diga el .env.

Uso:  py cambiar_clave.py admin
      py cambiar_clave.py empleado
Te pide la contraseña nueva dos veces (no se ve mientras escribes).
"""
import getpass
import sys

from werkzeug.security import generate_password_hash

from campo_alegre import create_app
from campo_alegre.db import get_db


def cambiar(db, usuario, clave):
    """Devuelve True si el usuario existía y se cambió su contraseña."""
    if not db.usuarios.find_one({"usuario": usuario}):
        return False
    db.usuarios.update_one(
        {"usuario": usuario},
        {"$set": {"password_hash": generate_password_hash(clave), "activo": True}},
    )
    return True


def main():
    if len(sys.argv) != 2:
        print("Uso: py cambiar_clave.py admin   (o: empleado)")
        return 1
    usuario = sys.argv[1].strip().lower()

    app = create_app()
    with app.app_context():
        db = get_db()
        if not db.usuarios.find_one({"usuario": usuario}):
            existentes = ", ".join(u["usuario"] for u in db.usuarios.find()) or "ninguno"
            print(f"No existe el usuario '{usuario}'. Usuarios que hay: {existentes}.")
            print("Si no hay ninguno, ejecuta primero: py seed.py")
            return 1

        clave = getpass.getpass("Contraseña nueva (mínimo 8 caracteres): ")
        if len(clave) < 8:
            print("Es muy corta. Usa al menos 8 caracteres.")
            return 1
        if clave != getpass.getpass("Repítela: "):
            print("No coinciden. No se cambió nada.")
            return 1

        cambiar(db, usuario, clave)
        print(f"Listo. La contraseña de '{usuario}' quedó cambiada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
