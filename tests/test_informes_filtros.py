import unittest
from datetime import datetime, timedelta

from base import CLAVE_EMPLEADO, BaseTest
from campo_alegre.db import get_db


def fecha(dias):
    return (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")


class Base(BaseTest):
    def setUp(self):
        super().setUp()
        self.entrar()
        with self.app.app_context():
            for n in ("Palera", "El Roto"):
                get_db().potreros.insert_one({"nombre": n, "nombre_lower": n.lower(), "activo": True})
        self.post("/ganado/nuevo", self.animal_valido(identificacion="301", potrero="Palera"))                # Vaca, Palera
        self.post("/ganado/nuevo", self.animal_valido(identificacion="302", categoria="Novilla", potrero="El Roto"))
        self.post("/ganado/nuevo", self.animal_valido(identificacion="303", categoria="Vaca", potrero="El Roto"))
        for a in ("301", "302", "303"):
            self.post("/sanitario/nuevo", {"animal": a, "tipo": "Vacunación", "producto": "Aftosa", "fecha_aplicacion": fecha(-3)})
            self.post("/reproductivo/nuevo", {"animal": a, "tipo": "Servicio", "fecha": fecha(-3), "metodo": "Monta"})
            self.post("/productivo/nuevo", {"animal": a, "fecha": fecha(-3), "peso_kg": "400"})

    def ids(self, url, formato="html"):
        h = self.client.get(url).get_data(as_text=True)
        return [a for a in ("301", "302", "303") if (f"<td>{a}</td>" in h)]


class PruebasFiltros(Base):
    def test_categoria_y_potrero_en_cada_informe(self):
        for informe in ("sanitario", "reproductivo", "productivo"):
            self.assertEqual(self.ids(f"/informes/{informe}?categoria=Novilla"), ["302"], informe)
            self.assertEqual(self.ids(f"/informes/{informe}?potrero=El+Roto"), ["302", "303"], informe)
            self.assertEqual(self.ids(f"/informes/{informe}?potrero=El+Roto&categoria=Vaca"), ["303"], informe)
            self.assertEqual(self.ids(f"/informes/{informe}?potrero=Palera&categoria=Novilla"), [], informe)
            self.assertEqual(self.ids(f"/informes/{informe}?potrero=El+Roto&animal=301"), [], informe)
            self.assertEqual(self.ids(f"/informes/{informe}?potrero=El+Roto&animal=303"), ["303"], informe)

    def test_csv_respeta_los_filtros(self):
        csv = self.client.get("/informes/sanitario?formato=csv&potrero=Palera").get_data(as_text=True)
        self.assertIn("301", csv)
        self.assertNotIn("302", csv)

    def test_formularios_muestran_los_filtros(self):
        for informe in ("sanitario", "reproductivo", "productivo", "movimientos"):
            h = self.client.get(f"/informes/{informe}").get_data(as_text=True)
            self.assertIn('id="categoria"', h)
            self.assertIn('id="potrero"', h)
        h = self.client.get("/informes/inventario").get_data(as_text=True)
        for campo in ("sexo", "categoria", "estado", "potrero"):
            self.assertIn(f'id="{campo}"', h)

    def test_filtros_con_estado_reproductivo_se_combinan(self):
        self.post("/reproductivo/nuevo", {"animal": "301", "tipo": "Diagnóstico de preñez", "fecha": fecha(-1),
                                          "resultado": "Preñada", "parto_modo": "Desconocida"})
        self.post("/reproductivo/nuevo", {"animal": "302", "tipo": "Diagnóstico de preñez", "fecha": fecha(-1),
                                          "resultado": "Preñada", "parto_modo": "Desconocida"})
        self.assertEqual(self.ids("/informes/reproductivo?estado_repro=Gestante&potrero=Palera"), ["301"])
        self.assertEqual(self.ids("/informes/reproductivo?estado_repro=Gestante&potrero=El+Roto"), ["302"])
        self.assertEqual(self.ids("/informes/reproductivo?estado_repro=Gestante"), ["301", "302"])


class PruebasInformeMovimientos(Base):
    def setUp(self):
        super().setUp()
        self.post("/movimientos/salida", {"animal": "301", "fecha": fecha(-2), "motivo": "Venta", "detalle": "A Pedro"})
        self.post("/movimientos/novedad", {"animal": "302", "fecha": fecha(-1), "detalle": "Cojera"})
        self.post("/movimientos/salida", {"animal": "303", "fecha": fecha(-1), "motivo": "Muerte"})

    def test_aparece_en_el_indice(self):
        self.assertIn("Movimientos del hato", self.client.get("/informes/").get_data(as_text=True))

    def test_contenido_y_resumen(self):
        h = self.client.get("/informes/movimientos").get_data(as_text=True)
        for t in ("Venta", "A Pedro", "Cojera", "Salida por Venta", "Salida por Muerte", "Entrada", "Salida"):
            self.assertIn(t, h)

    def test_filtros(self):
        self.assertEqual(self.ids("/informes/movimientos?tipo=Salida"), ["301", "303"])
        self.assertEqual(self.ids("/informes/movimientos?tipo=Novedad"), ["302"])
        self.assertEqual(self.ids("/informes/movimientos?tipo=Salida&potrero=El+Roto"), ["303"])
        self.assertEqual(self.ids(f"/informes/movimientos?tipo=Salida&desde={fecha(-1)}"), ["303"])
        self.assertEqual(self.ids(f"/informes/movimientos?tipo=Salida&hasta={fecha(-2)}"), ["301"])
        self.assertEqual(self.ids("/informes/movimientos?tipo=Inventado&animal=302"), ["302"])

    def test_csv(self):
        r = self.client.get("/informes/movimientos?formato=csv&tipo=Salida")
        self.assertIn("text/csv", r.content_type)
        csv = r.get_data(as_text=True)
        self.assertIn("Fecha;Animal;Nombre;Tipo;Detalle;Registró", csv)
        self.assertIn("Venta · A Pedro", csv)
        self.assertNotIn("Cojera", csv)

    def test_empleado_puede_consultar(self):
        self.post("/logout")
        self.entrar("empleado", CLAVE_EMPLEADO)
        self.assertEqual(self.client.get("/informes/movimientos").status_code, 200)
        self.assertEqual(self.client.get("/informes/movimientos?formato=csv").status_code, 200)


if __name__ == "__main__":
    unittest.main()
