"""Pruebas del módulo de Informes (RF-06)."""
import csv
import io
import unittest
from datetime import datetime, timedelta

from base import CLAVE_EMPLEADO, BaseTest
from campo_alegre.db import get_db
from campo_alegre.semilla import (
    crear_animales_ejemplo,
    crear_eventos_ejemplo,
    crear_pesajes_ejemplo,
    crear_reproductivos_ejemplo,
)


def fecha(dias):
    return (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")


class InformesBase(BaseTest):
    def setUp(self):
        super().setUp()
        with self.app.app_context():
            db = get_db()
            crear_animales_ejemplo(db)
            crear_eventos_ejemplo(db)
            crear_reproductivos_ejemplo(db)
            crear_pesajes_ejemplo(db)
        self.entrar()

    def html(self, url):
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200, url)
        return r.get_data(as_text=True)

    def filas_csv(self, url):
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r.content_type)
        texto = r.get_data(as_text=True)
        self.assertTrue(texto.startswith("﻿"))
        return list(csv.reader(io.StringIO(texto.lstrip("﻿")), delimiter=";")), r


class PruebasInventario(InformesBase):
    def test_todos_los_animales(self):
        filas, r = self.filas_csv("/informes/inventario?formato=csv")
        self.assertEqual(filas[0][0], "Identificación")
        self.assertEqual(len(filas) - 1, 8)
        self.assertIn("attachment", r.headers["Content-Disposition"])
        self.assertIn(".csv", r.headers["Content-Disposition"])

    def test_filtros_combinados(self):
        filas, _ = self.filas_csv("/informes/inventario?formato=csv&sexo=Hembra&categoria=Vaca&estado=Activa")
        self.assertEqual(sorted(f[0] for f in filas[1:]), ["125", "221", "248"])
        filas, _ = self.filas_csv("/informes/inventario?formato=csv&estado=Vendido")
        self.assertEqual([f[0] for f in filas[1:]], ["236"])

    def test_filtro_invalido_se_ignora(self):
        filas, _ = self.filas_csv("/informes/inventario?formato=csv&estado=Inventado")
        self.assertEqual(len(filas) - 1, 8)

    def test_resumen_por_categoria(self):
        h = self.html("/informes/inventario")
        self.assertIn("Categoría Vaca", h)
        self.assertIn("Estado Vendido", h)


class PruebasSanitarioReproductivoProductivo(InformesBase):
    def test_sanitario_filtros(self):
        filas, _ = self.filas_csv("/informes/sanitario?formato=csv")
        self.assertEqual(len(filas) - 1, 5)
        filas, _ = self.filas_csv("/informes/sanitario?formato=csv&animal=125")
        self.assertEqual(len(filas) - 1, 2)
        filas, _ = self.filas_csv("/informes/sanitario?formato=csv&tipo=Tratamiento")
        self.assertEqual(len(filas) - 1, 1)
        filas, _ = self.filas_csv(f"/informes/sanitario?formato=csv&desde={fecha(-30)}&hasta={fecha(0)}")
        self.assertEqual(len(filas) - 1, 2)  # desparasitación (-20) y tratamiento (-9)

    def test_rango_inclusivo(self):
        filas, _ = self.filas_csv(f"/informes/sanitario?formato=csv&desde={fecha(-9)}&hasta={fecha(-9)}")
        self.assertEqual(len(filas) - 1, 1)

    def test_reproductivo_filtros(self):
        filas, _ = self.filas_csv("/informes/reproductivo?formato=csv")
        self.assertEqual(len(filas) - 1, 6)
        filas, _ = self.filas_csv("/informes/reproductivo?formato=csv&tipo=Servicio")
        self.assertEqual(len(filas) - 1, 3)
        filas, _ = self.filas_csv("/informes/reproductivo?formato=csv&tipo=Parto")
        self.assertIn("Cría Hembra viva", filas[1][4])

    def test_productivo_resumen(self):
        h = self.html("/informes/productivo")
        self.assertIn("Peso promedio", h)
        filas, _ = self.filas_csv("/informes/productivo?formato=csv&animal=125")
        self.assertEqual(len(filas) - 1, 3)
        self.assertEqual(filas[1][3], "462")           # el más reciente primero
        h = self.html("/informes/productivo?animal=125")
        self.assertIn("Peso máximo (kg)</span><strong>462", h)
        self.assertIn("Peso mínimo (kg)</span><strong>430", h)

    def test_sin_datos(self):
        h = self.html("/informes/productivo?animal=999")
        self.assertIn("No hay datos", h)
        self.assertNotIn("Peso promedio", h)


class PruebasFechasYSeguridad(InformesBase):
    def test_fecha_invalida_avisa_y_no_filtra(self):
        h = self.html("/informes/sanitario?desde=2026-13-45")
        self.assertIn("no es válida", h)
        self.assertIn("5 filas", h)

    def test_desde_posterior_a_hasta(self):
        h = self.html(f"/informes/sanitario?desde={fecha(0)}&hasta={fecha(-10)}")
        self.assertIn("no puede ser posterior", h)
        self.assertIn("5 filas", h)

    def test_informe_inexistente(self):
        self.assertEqual(self.client.get("/informes/nada").status_code, 404)

    def test_empleado_puede_consultar_y_exportar(self):
        self.post("/logout")
        self.entrar("empleado", CLAVE_EMPLEADO)
        for url in ("/informes/", "/informes/inventario", "/informes/sanitario?tipo=Tratamiento"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        r = self.client.get("/informes/inventario?formato=csv")
        self.assertIn("text/csv", r.content_type)

    def test_sin_sesion(self):
        self.post("/logout")
        self.assertEqual(self.client.get("/informes/inventario?formato=csv").status_code, 302)

    def test_csv_neutraliza_formulas(self):
        with self.app.app_context():
            get_db().animales.update_one({"identificacion": "125"}, {"$set": {"nombre": "=1+1"}})
        filas, _ = self.filas_csv("/informes/inventario?formato=csv&categoria=Vaca&sexo=Hembra&estado=Activa")
        nombres = [f[1] for f in filas[1:]]
        self.assertIn("'=1+1", nombres)
        self.assertNotIn("=1+1", nombres)

    def test_exportar_deja_actividad(self):
        self.client.get("/informes/inventario?formato=csv")
        with self.app.app_context():
            textos = [a["texto"] for a in get_db().actividad.find()]
        self.assertTrue(any("Se exportó el informe" in t for t in textos))

    def test_indice_y_menu(self):
        h = self.html("/informes/")
        for titulo in ("Inventario de ganado", "Control sanitario", "Eventos reproductivos", "Control productivo"):
            self.assertIn(titulo, h)

    def test_pantalla_limita_filas_pero_csv_no(self):
        with self.app.app_context():
            get_db().pesajes.delete_many({})
            base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            for i in range(520):
                get_db().pesajes.insert_one(
                    {"animal": "125", "fecha": base - timedelta(days=i + 1), "peso_kg": 300.0,
                     "observaciones": None, "registrado_por": "admin", "creado_en": base}
                )
        h = self.html("/informes/productivo")
        self.assertIn("520 filas", h)
        self.assertIn("primeras 500", h)
        self.assertEqual(h.count("<tr>"), 501)  # encabezado + 500 filas
        filas, _ = self.filas_csv("/informes/productivo?formato=csv")
        self.assertEqual(len(filas) - 1, 520)


if __name__ == "__main__":
    unittest.main()
