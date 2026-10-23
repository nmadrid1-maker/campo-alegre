"""Pruebas del módulo de Control productivo (RF-05): pesajes."""
import re
import unittest
from datetime import datetime, timedelta

from base import CLAVE_EMPLEADO, BaseTest
from campo_alegre.db import get_db
from campo_alegre.semilla import crear_animales_ejemplo, crear_pesajes_ejemplo


def fecha(dias):
    return (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")


class ProdBase(BaseTest):
    def setUp(self):
        super().setUp()
        with self.app.app_context():
            crear_animales_ejemplo(get_db())

    def pesaje(self, **c):
        datos = {"animal": "125", "fecha": fecha(-1), "peso_kg": "420", "observaciones": ""}
        datos.update(c)
        return datos

    def pesajes(self, filtro=None):
        with self.app.app_context():
            return list(get_db().pesajes.find(filtro or {}))


class PruebasRegistro(ProdBase):
    def test_registra_pesaje(self):
        self.entrar()
        r = self.post("/productivo/nuevo", self.pesaje())
        self.assertEqual(r.status_code, 302)
        p = self.pesajes()[0]
        self.assertEqual(p["peso_kg"], 420.0)
        self.assertEqual(p["registrado_por"], "admin")

    def test_acepta_coma_decimal(self):
        self.entrar()
        self.post("/productivo/nuevo", self.pesaje(peso_kg="420,5"))
        self.assertEqual(self.pesajes()[0]["peso_kg"], 420.5)

    def test_pesos_invalidos(self):
        self.entrar()
        for peso in ("", "abc", "-5", "420,55", "9", "9,9", "1500,1", "1501", "12345", "4 20"):
            r = self.post("/productivo/nuevo", self.pesaje(peso_kg=peso))
            self.assertEqual(r.status_code, 200, peso)
            self.assertIn("peso", r.get_data(as_text=True).lower())
        self.assertEqual(len(self.pesajes()), 0)

    def test_limites_validos(self):
        self.entrar()
        self.post("/productivo/nuevo", self.pesaje(peso_kg="10", fecha=fecha(-3)))
        self.post("/productivo/nuevo", self.pesaje(peso_kg="1500", fecha=fecha(-2)))
        self.assertEqual(len(self.pesajes()), 2)

    def test_animal_y_fecha(self):
        self.entrar()
        self.assertIn("No existe un animal", self.post("/productivo/nuevo", self.pesaje(animal="999")).get_data(as_text=True))
        self.assertIn("no puede ser futura", self.post("/productivo/nuevo", self.pesaje(fecha=fecha(2))).get_data(as_text=True))
        self.assertIn("anterior al nacimiento", self.post("/productivo/nuevo", self.pesaje(fecha="2020-01-01")).get_data(as_text=True))
        self.assertIn("Indique la fecha del pesaje", self.post("/productivo/nuevo", self.pesaje(fecha="")).get_data(as_text=True))
        self.assertEqual(len(self.pesajes()), 0)

    def test_animal_macho_si_se_pesa(self):
        self.entrar()
        self.assertEqual(self.post("/productivo/nuevo", self.pesaje(animal="178", peso_kg="780")).status_code, 302)

    def test_animal_vendido_no(self):
        self.entrar()
        r = self.post("/productivo/nuevo", self.pesaje(animal="236"))
        self.assertIn("figura como Vendido", r.get_data(as_text=True))

    def test_pesaje_duplicado_mismo_dia(self):
        self.entrar()
        self.post("/productivo/nuevo", self.pesaje())
        r = self.post("/productivo/nuevo", self.pesaje(peso_kg="430"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("ya tiene un pesaje", r.get_data(as_text=True))
        self.assertEqual(len(self.pesajes()), 1)

    def test_mismo_dia_otro_animal_si(self):
        self.entrar()
        self.post("/productivo/nuevo", self.pesaje())
        self.post("/productivo/nuevo", self.pesaje(animal="221"))
        self.assertEqual(len(self.pesajes()), 2)

    def test_observaciones_largas(self):
        self.entrar()
        r = self.post("/productivo/nuevo", self.pesaje(observaciones="x" * 501))
        self.assertIn("hasta 500", r.get_data(as_text=True))


class PruebasHistorial(ProdBase):
    def registrar(self, dias, peso):
        self.post("/productivo/nuevo", self.pesaje(fecha=fecha(dias), peso_kg=peso))

    def test_cambio_y_gdp(self):
        self.entrar()
        self.registrar(-30, "400")
        self.registrar(-10, "410")   # +10 kg en 20 días = 500 g/día
        from campo_alegre.productivo import historial
        with self.app.app_context():
            h = historial("125")
        self.assertEqual([p["peso_kg"] for p in h], [410.0, 400.0])
        self.assertEqual(h[0]["cambio"], 10.0)
        self.assertEqual(h[0]["gdp"], 500)
        self.assertIsNone(h[1]["cambio"])
        self.assertIsNone(h[1]["gdp"])

    def test_cambio_negativo(self):
        self.entrar()
        self.registrar(-20, "400")
        self.registrar(-10, "395,5")
        html = self.client.get("/ganado/125").get_data(as_text=True)
        self.assertIn("-4,5 kg", html)
        self.assertIn("-450 g/día", html)

    def test_peso_actual_en_ficha(self):
        self.entrar()
        self.assertIn("se registra en Control productivo", self.client.get("/ganado/125").get_data(as_text=True))
        self.registrar(-20, "400")
        self.registrar(-2, "412,5")
        html = self.client.get("/ganado/125").get_data(as_text=True)
        self.assertIn("412,5 kg", html)

    def test_kpi_pesajes_del_mes(self):
        self.entrar()
        self.registrar(-400, "300")
        hoy_ = datetime.now()
        # un pesaje de hoy siempre cae en el mes actual
        self.post("/productivo/nuevo", self.pesaje(fecha=fecha(0)))
        html = self.client.get("/inicio").get_data(as_text=True)
        self.assertEqual(re.search(r'Pesajes registrados</span><span class="n">(\d+)</span>', html).group(1), "1")


class PruebasPermisosYLista(ProdBase):
    def test_empleado_ve_la_lista_pero_no_registra_ni_elimina(self):
        self.entrar()
        self.post("/productivo/nuevo", self.pesaje())
        oid = str(self.pesajes()[0]["_id"])
        self.post("/logout")
        self.entrar("empleado", CLAVE_EMPLEADO)
        html = self.client.get("/productivo/").get_data(as_text=True)
        self.assertIn("420 kg", html)
        for texto in ("Registrar pesaje", "Eliminar", "<th>Acciones</th>"):
            self.assertNotIn(texto, html)
        self.assertEqual(self.client.get("/productivo/nuevo").status_code, 302)
        self.post("/productivo/nuevo", self.pesaje(animal="221"))
        self.post(f"/productivo/{oid}/eliminar")
        self.assertEqual(len(self.pesajes()), 1)

    def test_eliminar(self):
        self.entrar()
        self.post("/productivo/nuevo", self.pesaje())
        oid = str(self.pesajes()[0]["_id"])
        self.post(f"/productivo/{oid}/eliminar")
        self.assertEqual(len(self.pesajes()), 0)
        self.assertEqual(self.post("/productivo/xyz/eliminar").status_code, 302)

    def test_sin_csrf(self):
        self.entrar()
        self.assertEqual(self.client.post("/productivo/nuevo", data=self.pesaje()).status_code, 400)

    def test_filtros_y_paginacion(self):
        self.entrar()
        for i in range(12):
            self.post("/productivo/nuevo", self.pesaje(fecha=fecha(-i - 1), peso_kg=str(300 + i)))
        self.post("/productivo/nuevo", self.pesaje(animal="221", peso_kg="350"))
        html = self.client.get("/productivo/").get_data(as_text=True)
        self.assertIn("de 13 pesajes", html)
        self.assertIn("Mostrando 11 a 13", self.client.get("/productivo/?page=2").get_data(as_text=True))
        self.assertIn("de 1 pesajes", self.client.get("/productivo/?q=221").get_data(as_text=True))
        self.assertIn("de 12 pesajes", self.client.get("/productivo/?animal=125").get_data(as_text=True))

    def test_animal_con_pesajes_no_se_elimina(self):
        self.entrar()
        self.post("/productivo/nuevo", self.pesaje())
        r = self.post("/ganado/125/eliminar")
        self.assertEqual(r.status_code, 302)
        with self.app.app_context():
            self.assertEqual(get_db().animales.count_documents({"identificacion": "125"}), 1)

    def test_historial_combinado_en_ficha(self):
        self.entrar()
        self.post("/productivo/nuevo", self.pesaje())
        html = self.client.get("/ganado/125").get_data(as_text=True)
        self.assertIn("<strong>Pesaje</strong>", html)
        self.assertIn("<strong>Ingreso</strong>", html)

    def test_semilla_no_duplica(self):
        with self.app.app_context():
            self.assertGreater(crear_pesajes_ejemplo(get_db()), 0)
            self.assertEqual(crear_pesajes_ejemplo(get_db()), 0)


if __name__ == "__main__":
    unittest.main()
