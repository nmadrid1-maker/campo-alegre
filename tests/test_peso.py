import unittest
from datetime import datetime

from base import CLAVE_EMPLEADO, BaseTest
from campo_alegre.db import get_db


class PruebasTipoYRangoDePeso(BaseTest):
    def setUp(self):
        super().setUp()
        self.entrar()
        for ident in ("301", "302", "303"):
            self.post("/ganado/nuevo", self.animal_valido(identificacion=ident))

    def peso(self, animal, kg, fecha="2026-01-10", **extra):
        d = {"animal": animal, "fecha": fecha, "peso_kg": str(kg)}
        d.update(extra)
        return self.post("/productivo/nuevo", d)

    def guardados(self):
        with self.app.app_context():
            return list(get_db().pesajes.find({}).sort("fecha", 1))

    def test_por_defecto_es_medido_y_se_guarda_estimado(self):
        self.peso("301", 400)
        self.peso("302", 420, tipo_peso="Estimado")
        self.assertEqual([p["tipo_peso"] for p in self.guardados()], ["Medido", "Estimado"])

    def test_tipo_invalido_se_rechaza(self):
        self.peso("301", 400, tipo_peso="Adivinado")
        self.assertEqual(self.guardados(), [])

    def test_lista_y_ficha_muestran_el_tipo(self):
        self.peso("301", 400, tipo_peso="Estimado")
        self.assertIn("Estimado", self.client.get("/productivo/").get_data(as_text=True))
        f = self.client.get("/ganado/301").get_data(as_text=True)
        self.assertIn("estimado", f)
        self.assertIn("est.", self.client.get("/ganado/").get_data(as_text=True))

    def test_pesaje_antiguo_sin_tipo_cuenta_como_medido(self):
        with self.app.app_context():
            get_db().pesajes.insert_one({"animal": "301", "fecha": datetime(2026, 1, 1), "peso_kg": 380.0})
        h = self.client.get("/productivo/").get_data(as_text=True)
        self.assertIn("Medido", h)
        self.assertNotIn("est.", self.client.get("/ganado/").get_data(as_text=True))

    def test_gdp_aproximado_si_alguno_es_estimado(self):
        self.peso("301", 400, fecha="2026-01-01")
        self.peso("301", 410, fecha="2026-01-11", tipo_peso="Estimado")
        self.assertIn("≈ 1000 g/día", self.client.get("/ganado/301").get_data(as_text=True))
        self.peso("303", 400, fecha="2026-01-01", tipo_peso="Estimado")  # solo el anterior es estimado
        self.peso("303", 410, fecha="2026-01-11")
        self.assertIn("≈ 1000 g/día", self.client.get("/ganado/303").get_data(as_text=True))
        self.peso("302", 400, fecha="2026-01-01")
        self.peso("302", 410, fecha="2026-01-11")
        self.assertNotIn("≈ 1000", self.client.get("/ganado/302").get_data(as_text=True))

    def test_filtro_por_rango_usa_el_ultimo_peso(self):
        self.peso("301", 300, fecha="2026-01-01")
        self.peso("301", 420, fecha="2026-02-01")   # último peso: 420
        self.peso("302", 380, fecha="2026-01-05")
        # 303 no tiene peso
        def ids(url):
            h = self.client.get(url).get_data(as_text=True)
            return [i for i in ("301", "302", "303") if f'href="/ganado/{i}"' in h]
        self.assertEqual(ids("/ganado/?peso_min=400&peso_max=500"), ["301"])
        self.assertEqual(ids("/ganado/?peso_min=350"), ["301", "302"])
        self.assertEqual(ids("/ganado/?peso_max=390"), ["302"])
        self.assertEqual(ids("/ganado/?peso_min=420&peso_max=420"), ["301"])
        self.assertEqual(ids("/ganado/?peso_min=abc"), ["301", "302", "303"])
        self.assertEqual(ids("/ganado/?peso_min=400,5"), ["301"])
        self.assertEqual(ids("/ganado/?peso_min=900"), [])

    def test_informe_inventario_con_rango_y_columnas(self):
        self.peso("301", 420, tipo_peso="Estimado")
        self.peso("302", 300)
        h = self.client.get("/informes/inventario?peso_min=400").get_data(as_text=True)
        self.assertIn("<td>301</td>", h)
        self.assertNotIn("<td>302</td>", h)
        self.assertIn("Estimado", h)
        csv = self.client.get("/informes/inventario?formato=csv&peso_max=350").get_data(as_text=True)
        self.assertIn("302", csv)
        self.assertNotIn("301;", csv)
        self.assertIn("Tipo de peso", csv)
        self.assertIn("Tipo de peso", self.client.get("/informes/productivo?formato=csv").get_data(as_text=True))

    def test_empleado_puede_filtrar_por_peso(self):
        self.peso("301", 420)
        self.post("/logout")
        self.entrar("empleado", CLAVE_EMPLEADO)
        self.assertIn('href="/ganado/301"', self.client.get("/ganado/?peso_min=400").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()


class PruebasPesoAlRegistrar(BaseTest):
    def setUp(self):
        super().setUp()
        self.entrar()

    def pesajes(self):
        with self.app.app_context():
            return list(get_db().pesajes.find({}))

    def test_formulario_muestra_peso_y_tipo(self):
        h = self.client.get("/ganado/nuevo").get_data(as_text=True)
        self.assertIn('name="peso_kg"', h)
        self.assertIn('value="Estimado"', h)

    def test_guarda_el_primer_pesaje(self):
        self.post("/ganado/nuevo", self.animal_valido(peso_kg="415,5", tipo_peso="Estimado"))
        p = self.pesajes()
        self.assertEqual((p[0]["animal"], p[0]["peso_kg"], p[0]["tipo_peso"]), ("301", 415.5, "Estimado"))
        self.assertIn("estimado", self.client.get("/ganado/301").get_data(as_text=True))

    def test_sin_peso_no_crea_pesaje_y_peso_invalido_no_crea_animal(self):
        self.post("/ganado/nuevo", self.animal_valido())
        self.assertEqual(self.pesajes(), [])
        for peso, tipo in (("5", "Medido"), ("abc", "Medido"), ("420", "Adivinado"), ("2000", "Medido")):
            self.post("/ganado/nuevo", self.animal_valido(identificacion="302", peso_kg=peso, tipo_peso=tipo))
        with self.app.app_context():
            self.assertEqual(get_db().animales.count_documents({"identificacion": "302"}), 0)
        self.assertEqual(self.pesajes(), [])

    def test_editar_no_muestra_ni_crea_pesaje(self):
        self.post("/ganado/nuevo", self.animal_valido())
        self.assertNotIn('name="peso_kg"', self.client.get("/ganado/301/editar").get_data(as_text=True))
        self.post("/ganado/301/editar", self.animal_valido(peso_kg="400", tipo_peso="Medido"))
        self.assertEqual(self.pesajes(), [])
