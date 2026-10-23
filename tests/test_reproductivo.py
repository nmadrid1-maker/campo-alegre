"""Pruebas del módulo de Control reproductivo (RF-04)."""
import unittest
from datetime import datetime, timedelta

from base import CLAVE_EMPLEADO, BaseTest
from campo_alegre.db import get_db
from campo_alegre.semilla import crear_animales_ejemplo, crear_reproductivos_ejemplo


def fecha(dias):
    return (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")


class ReproBase(BaseTest):
    def setUp(self):
        super().setUp()
        with self.app.app_context():
            crear_animales_ejemplo(get_db())

    def servicio(self, **c):
        datos = {"animal": "125", "tipo": "Servicio", "fecha": fecha(-2), "metodo": "Monta",
                 "reproductor": "Toro 178", "observaciones": ""}
        datos.update(c)
        return datos

    def eventos(self, filtro=None):
        with self.app.app_context():
            return list(get_db().eventos_reproductivos.find(filtro or {}))

    def insertar(self, animal, tipo, dias, **extra):
        f = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=dias)
        doc = {"animal": animal, "tipo": tipo, "fecha": f, "metodo": None, "reproductor": None,
               "parto_probable": None, "resultado": None, "cria_sexo": None, "cria_estado": None,
               "observaciones": None, "registrado_por": "admin", "creado_en": datetime.now()}
        if tipo == "Servicio":
            doc["parto_probable"] = f + timedelta(days=283)
        doc.update(extra)
        with self.app.app_context():
            get_db().eventos_reproductivos.insert_one(doc)

    def partos_en_inicio(self):
        import re
        html = self.client.get("/inicio").get_data(as_text=True)
        return int(re.search(r"Partos probables: (\d+)", html).group(1))


class PruebasRegistro(ReproBase):
    def test_servicio_calcula_parto_probable(self):
        self.entrar()
        r = self.post("/reproductivo/nuevo", self.servicio(fecha="2026-01-01"))
        self.assertEqual(r.status_code, 302)
        e = self.eventos()[0]
        self.assertEqual(e["metodo"], "Monta")
        self.assertEqual(e["parto_probable"], datetime(2026, 1, 1) + timedelta(days=283))

    def test_diagnostico_parto_y_aborto(self):
        self.entrar()
        self.post("/reproductivo/nuevo", {"animal": "125", "tipo": "Diagnóstico de preñez", "fecha": fecha(-3), "resultado": "Preñada"})
        self.post("/reproductivo/nuevo", {"animal": "221", "tipo": "Parto", "fecha": fecha(-1), "cria_estado": "Viva", "cria_sexo": "Macho"})
        self.post("/reproductivo/nuevo", {"animal": "248", "tipo": "Aborto", "fecha": fecha(-1)})
        self.assertEqual(len(self.eventos()), 3)
        parto = self.eventos({"tipo": "Parto"})[0]
        self.assertEqual((parto["cria_estado"], parto["cria_sexo"]), ("Viva", "Macho"))
        self.assertIsNone(parto["parto_probable"])

    def test_campos_de_otro_tipo_no_se_guardan(self):
        self.entrar()
        self.post("/reproductivo/nuevo", {"animal": "125", "tipo": "Aborto", "fecha": fecha(-1),
                                          "metodo": "Monta", "resultado": "Preñada", "cria_estado": "Viva"})
        e = self.eventos()[0]
        self.assertIsNone(e["metodo"])
        self.assertIsNone(e["resultado"])
        self.assertIsNone(e["cria_estado"])

    def test_solo_hembras(self):
        self.entrar()
        r = self.post("/reproductivo/nuevo", self.servicio(animal="178"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("es macho", r.get_data(as_text=True))
        self.assertEqual(len(self.eventos()), 0)

    def test_animal_inexistente_y_no_activo(self):
        self.entrar()
        self.assertIn("No existe un animal", self.post("/reproductivo/nuevo", self.servicio(animal="999")).get_data(as_text=True))
        with self.app.app_context():
            get_db().animales.update_one({"identificacion": "125"}, {"$set": {"estado": "Vendido"}})
        self.assertIn("figura como Vendido", self.post("/reproductivo/nuevo", self.servicio()).get_data(as_text=True))
        self.assertEqual(len(self.eventos()), 0)

    def test_validaciones_por_tipo(self):
        self.entrar()
        casos = [
            (self.servicio(metodo=""), "Seleccione el método"),
            (self.servicio(reproductor="x" * 61), "hasta 60"),
            ({"animal": "125", "tipo": "Diagnóstico de preñez", "fecha": fecha(-1)}, "resultado del diagnóstico"),
            ({"animal": "125", "tipo": "Parto", "fecha": fecha(-1)}, "viva o muerta"),
            ({"animal": "125", "tipo": "Parto", "fecha": fecha(-1), "cria_estado": "Viva", "cria_sexo": "X"}, "sexo de la cría"),
            (self.servicio(tipo="Otro"), "Seleccione el tipo"),
            (self.servicio(observaciones="x" * 501), "hasta 500"),
        ]
        for datos, texto in casos:
            r = self.post("/reproductivo/nuevo", datos)
            self.assertEqual(r.status_code, 200, texto)
            self.assertIn(texto, r.get_data(as_text=True))
        self.assertEqual(len(self.eventos()), 0)

    def test_fechas_invalidas(self):
        self.entrar()
        self.assertIn("no puede ser futura", self.post("/reproductivo/nuevo", self.servicio(fecha=fecha(3))).get_data(as_text=True))
        self.assertIn("anterior al nacimiento", self.post("/reproductivo/nuevo", self.servicio(fecha="2020-01-01")).get_data(as_text=True))
        self.assertIn("Indique la fecha", self.post("/reproductivo/nuevo", self.servicio(fecha="")).get_data(as_text=True))
        self.assertEqual(len(self.eventos()), 0)


class PruebasPartosProbables(ReproBase):
    def test_servicio_con_parto_en_la_ventana_cuenta(self):
        self.entrar()
        self.insertar("221", "Servicio", -255)  # parto probable en 28 días
        self.assertEqual(self.partos_en_inicio(), 1)

    def test_fuera_de_la_ventana_no_cuenta(self):
        self.entrar()
        self.insertar("125", "Servicio", -100)   # +183 días
        self.insertar("221", "Servicio", -290)   # ya pasó
        self.assertEqual(self.partos_en_inicio(), 0)

    def test_se_cierra_con_parto_aborto_nuevo_servicio_o_vacia(self):
        self.entrar()
        for tipo, extra in (("Parto", {}), ("Aborto", {}), ("Servicio", {}),
                            ("Diagnóstico de preñez", {"resultado": "Vacía"})):
            with self.app.app_context():
                get_db().eventos_reproductivos.delete_many({})
            self.insertar("221", "Servicio", -255)
            self.insertar("221", tipo, -10, **extra)
            self.assertEqual(self.partos_en_inicio(), 0, tipo)

    def test_diagnostico_prenada_no_cierra(self):
        self.entrar()
        self.insertar("221", "Servicio", -255)
        self.insertar("221", "Diagnóstico de preñez", -200, resultado="Preñada")
        self.assertEqual(self.partos_en_inicio(), 1)

    def test_lista_muestra_panel(self):
        self.entrar()
        self.insertar("221", "Servicio", -255)
        html = self.client.get("/reproductivo/").get_data(as_text=True)
        self.assertIn("Partos probables (30 días): 1", html)

    def test_kpi_eventos_ultimos_30_dias(self):
        self.entrar()
        self.insertar("125", "Aborto", -5)
        self.insertar("125", "Aborto", -60)
        import re
        html = self.client.get("/inicio").get_data(as_text=True)
        self.assertEqual(re.search(r'\(30 días\)</span><span class="n">(\d+)</span>', html).group(1), "1")


class PruebasPermisosYLista(ReproBase):
    def test_empleado_ve_la_lista_pero_no_registra_ni_elimina(self):
        self.entrar()
        self.post("/reproductivo/nuevo", self.servicio())
        oid = str(self.eventos()[0]["_id"])
        self.post("/logout")
        self.entrar("empleado", CLAVE_EMPLEADO)
        html = self.client.get("/reproductivo/").get_data(as_text=True)
        self.assertIn("Servicio", html)
        for texto in ("Registrar evento", "Eliminar", "<th>Acciones</th>"):
            self.assertNotIn(texto, html)
        self.assertEqual(self.client.get("/reproductivo/nuevo").status_code, 302)
        self.post("/reproductivo/nuevo", self.servicio(animal="221"))
        self.post(f"/reproductivo/{oid}/eliminar")
        self.assertEqual(len(self.eventos()), 1)

    def test_sin_sesion_redirige(self):
        self.assertEqual(self.client.get("/reproductivo/nuevo").status_code, 302)

    def test_post_sin_csrf_rechazado(self):
        self.entrar()
        r = self.client.post("/reproductivo/nuevo", data=self.servicio())
        self.assertEqual(r.status_code, 400)

    def test_eliminar(self):
        self.entrar()
        self.post("/reproductivo/nuevo", self.servicio())
        oid = str(self.eventos()[0]["_id"])
        r = self.post(f"/reproductivo/{oid}/eliminar")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(len(self.eventos()), 0)
        self.assertEqual(self.post("/reproductivo/zzz/eliminar").status_code, 302)

    def test_filtros_y_paginacion(self):
        self.entrar()
        for i in range(12):
            self.insertar("125", "Aborto", -i - 1)
        self.insertar("221", "Parto", -1, cria_estado="Viva")
        html = self.client.get("/reproductivo/").get_data(as_text=True)
        self.assertIn("de 13 eventos", html)
        self.assertIn("Mostrando 11 a 13", self.client.get("/reproductivo/?page=2").get_data(as_text=True))
        self.assertIn("de 1 eventos", self.client.get("/reproductivo/?tipo=Parto").get_data(as_text=True))
        self.assertIn("de 1 eventos", self.client.get("/reproductivo/?q=221").get_data(as_text=True))
        self.assertIn("de 12 eventos", self.client.get("/reproductivo/?animal=125").get_data(as_text=True))

    def test_ficha_hembra_y_macho(self):
        self.entrar()
        self.insertar("125", "Parto", -3, cria_estado="Viva", cria_sexo="Hembra")
        self.assertIn("Cría Hembra viva", self.client.get("/ganado/125").get_data(as_text=True))
        self.assertIn("solo se registran a hembras", self.client.get("/ganado/178").get_data(as_text=True))

    def test_animal_con_eventos_no_se_elimina(self):
        self.entrar()
        self.insertar("125", "Aborto", -3)
        self.post("/ganado/125/eliminar")
        with self.app.app_context():
            self.assertEqual(get_db().animales.count_documents({"identificacion": "125"}), 1)

    def test_semilla_no_duplica(self):
        with self.app.app_context():
            n = crear_reproductivos_ejemplo(get_db())
            self.assertGreater(n, 0)
            self.assertEqual(crear_reproductivos_ejemplo(get_db()), 0)


if __name__ == "__main__":
    unittest.main()
