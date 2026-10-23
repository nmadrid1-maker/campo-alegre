"""Carga datos de demostración: 3 vacas por potrero, con eventos sanitarios, reproductivos, pesajes y movimientos
(crías, entradas, salidas y novedades).

Uso:  py seed_demo.py            (carga los datos)
      py seed_demo.py --borrar   (borra solo los datos de demostración)
Se puede ejecutar varias veces: no duplica nada.
"""
import sys

from campo_alegre import create_app
from campo_alegre.db import get_db
from campo_alegre.semilla import borrar_demo, crear_demo

app = create_app()

with app.app_context():
    db = get_db()
    if "--borrar" in sys.argv:
        print("Documentos de demostración borrados:", borrar_demo(db))
    else:
        r = crear_demo(db)
        if r is None:
            print("Los datos de demostración ya estaban cargados. Para quitarlos: py seed_demo.py --borrar")
        elif "animales" not in r:
            print("Los datos de demostración ya estaban cargados; se agregaron los del módulo de movimientos:")
            for clave, n in r.items():
                print(f"  {clave}: {n}")
        else:
            print("Datos de demostración creados:")
            for clave, n in r.items():
                print(f"  {clave}: {n}")
