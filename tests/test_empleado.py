"""El Empleado solo consulta: ve todo, pero no puede registrar, modificar ni eliminar nada.

Es la regla confirmada en el documento de requerimientos (RF-34).
"""
import unittest

from base import CLAVE_EMPLEADO, BaseTest
from campo_alegre.db import get_db
from campo_alegre.semilla import crear_demo

COLECCIONES = ("animales", "potreros", "traslados", "eventos_sanitarios", "eventos_reproductivos",
               "pesajes", "usuarios")


class PruebasEmpleado(BaseTest):
    def setUp(self):
        super().setUp()
        with self.app.app_context():
            crear_demo(get_db())
            db = get_db()
            self.potrero_id = str(db.potreros.find_one({"nombre": "Palera"})["_id"])
            self.sani_id = str(db.eventos_sanitarios.find_one({})["_id"])
            self.repro_id = str(db.eventos_reproductivos.find_one({})["_id"])
            self.peso_id = str(db.pesajes.find_one({})["_id"])
        self.entrar("empleado", CLAVE_EMPLEADO)

    def conteos(self):
        with self.app.app_context():
            db = get_db()
            return {c: getattr(db, c).count_documents({}) for c in COLECCIONES}

    def instantanea(self):
        with self.app.app_context():
            db = get_db()
            return {c: sorted(str(sorted((k, str(v)) for k, v in d.items())) for d in getattr(db, c).find({}))
                    for c in COLECCIONES}

    def test_puede_ver_todas_las_pantallas_de_consulta(self):
        for ruta in ("/inicio", "/ganado/", "/ganado/401", "/ganado/?potrero=Palera", "/potreros/", "/sanitario/",
                     "/reproductivo/", "/productivo/", "/informes/", "/informes/inventario",
                     "/informes/sanitario", "/informes/reproductivo", "/informes/productivo"):
            self.assertEqual(self.client.get(ruta).status_code, 200, ruta)

    def test_ninguna_pantalla_de_consulta_ofrece_controles_de_edicion(self):
        prohibidos = ("Registrar animal", "Registrar evento", "Registrar pesaje", "Nuevo potrero", "Editar",
                      "Eliminar", "Desactivar", "modal-eliminar", "/nuevo")
        for ruta in ("/inicio", "/ganado/", "/ganado/401", "/potreros/", "/sanitario/", "/reproductivo/", "/productivo/"):
            html = self.client.get(ruta).get_data(as_text=True)
            for texto in prohibidos:
                self.assertNotIn(texto, html, f"{texto!r} aparece en {ruta}")

    def test_no_puede_abrir_ningun_formulario(self):
        for ruta in ("/ganado/nuevo", "/ganado/401/editar", "/sanitario/nuevo", "/reproductivo/nuevo",
                     "/productivo/nuevo", "/potreros/nuevo", f"/potreros/{self.potrero_id}/editar",
                     "/usuarios/", "/usuarios/nuevo", "/usuarios/admin/editar", "/usuarios/admin/clave"):
            r = self.client.get(ruta)
            self.assertEqual(r.status_code, 302, ruta)
            self.assertIn("/inicio", r.headers["Location"], ruta)

    def test_ningun_envio_modifica_los_datos(self):
        antes = self.instantanea()
        a = {"nombre": "X", "sexo": "Hembra", "categoria": "Vaca", "fecha_nacimiento": "2020-01-01",
             "fecha_ingreso": "2020-02-01", "procedencia": "Compra", "estado": "Fallecido", "observaciones": ""}
        envios = [
            ("/ganado/nuevo", dict(a, identificacion="999")),
            ("/ganado/401/editar", a),
            ("/ganado/401/eliminar", {}),
            ("/sanitario/nuevo", {"animal": "401", "tipo": "Vacunación", "producto": "X", "fecha_aplicacion": "2026-01-01"}),
            (f"/sanitario/{self.sani_id}/eliminar", {}),
            ("/reproductivo/nuevo", {"animal": "401", "tipo": "Aborto", "fecha": "2026-01-01"}),
            (f"/reproductivo/{self.repro_id}/eliminar", {}),
            ("/productivo/nuevo", {"animal": "401", "fecha": "2026-01-01", "peso_kg": "400"}),
            (f"/productivo/{self.peso_id}/eliminar", {}),
            ("/potreros/nuevo", {"nombre": "Nuevo"}),
            (f"/potreros/{self.potrero_id}/editar", {"nombre": "Renombrado"}),
            (f"/potreros/{self.potrero_id}/estado", {}),
            (f"/potreros/{self.potrero_id}/eliminar", {}),
            ("/usuarios/nuevo", {"usuario": "intruso", "nombre": "I", "rol": "Administrador",
                                 "clave": "clave-segura-1", "confirmacion": "clave-segura-1"}),
            ("/usuarios/admin/clave", {"clave": "clave-segura-1", "confirmacion": "clave-segura-1"}),
            ("/usuarios/admin/estado", {}),
            ("/usuarios/empleado/editar", {"nombre": "Jefe", "rol": "Administrador"}),
        ]
        for ruta, datos in envios:
            r = self.post(ruta, datos)
            self.assertEqual(r.status_code, 302, ruta)
        self.assertEqual(self.instantanea(), antes)

    def test_sigue_sin_poder_aunque_forje_la_peticion_sin_token(self):
        antes = self.conteos()
        self.assertEqual(self.client.post("/ganado/401/eliminar").status_code, 400)
        self.assertEqual(self.conteos(), antes)

    def test_puede_exportar_informes_sin_cambiar_datos(self):
        antes = self.conteos()
        r = self.client.get("/informes/inventario?formato=csv")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r.content_type)
        self.assertEqual(self.conteos(), antes)

    def test_la_ficha_muestra_todo_el_historial(self):
        html = self.client.get("/ganado/401").get_data(as_text=True)
        for texto in ("Control sanitario", "Eventos reproductivos", "Pesajes", "Historial", "Potrero"):
            self.assertIn(texto, html)


if __name__ == "__main__":
    unittest.main()


class PruebasMarca(BaseTest):
    def test_la_marca_se_guarda_se_muestra_y_se_valida(self):
        self.entrar()
        self.post("/ganado/nuevo", self.animal_valido(marca="Hierro CA"))
        self.assertIn("Hierro CA", self.client.get("/ganado/301").get_data(as_text=True))
        self.post("/ganado/nuevo", self.animal_valido(identificacion="302", marca="x" * 41))
        with self.app.app_context():
            self.assertEqual(get_db().animales.count_documents({}), 1)
        self.post("/ganado/301/editar", self.animal_valido(marca=""))
        self.assertNotIn("Hierro CA", self.client.get("/ganado/301").get_data(as_text=True))


class PruebasSinInternet(BaseTest):
    def test_las_paginas_no_piden_nada_a_internet(self):
        import os, re
        self.entrar()
        for ruta in ("/inicio", "/ganado/", "/potreros/", "/sanitario/", "/informes/", "/usuarios/"):
            html = self.client.get(ruta).get_data(as_text=True)
            externos = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
            self.assertEqual(externos, [], ruta)
            self.assertIn("/static/vendor/bootstrap.min.css", html)
        raiz = os.path.join(os.path.dirname(__file__), "..", "campo_alegre", "static", "vendor")
        for archivo in ("bootstrap.min.css", "bootstrap.bundle.min.js"):
            self.assertGreater(os.path.getsize(os.path.join(raiz, archivo)), 50000)


class PruebasPaginaDeError(BaseTest):
    def test_un_error_interno_muestra_una_pagina_con_diseno(self):
        self.app.config["PROPAGATE_EXCEPTIONS"] = False
        self.app.config["TESTING"] = False  # en las pruebas Flask deja pasar las excepciones

        @self.app.route("/boom")
        def boom():
            raise RuntimeError("fallo de prueba")

        r = self.app.test_client().get("/boom")
        self.assertEqual(r.status_code, 500)
        h = r.get_data(as_text=True)
        self.assertIn("/static/vendor/bootstrap.min.css", h)
        self.assertIn("errores.log", h)
