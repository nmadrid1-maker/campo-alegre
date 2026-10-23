import unittest

from base import CLAVE_EMPLEADO, BaseTest
from campo_alegre.db import get_db


class PruebasMovimientos(BaseTest):
    def setUp(self):
        super().setUp()
        self.entrar()

    def movs(self, **f):
        with self.app.app_context():
            return list(get_db().movimientos.find(f))

    def estado(self, ident):
        with self.app.app_context():
            return get_db().animales.find_one({"identificacion": ident})["estado"]

    def salida(self, **c):
        d = {"animal": "301", "fecha": "2026-01-10", "motivo": "Venta", "detalle": "A Juan"}
        d.update(c)
        return self.post("/movimientos/salida", d)

    def test_compra_genera_entrada_y_finca_sin_madre_no(self):
        self.post("/ganado/nuevo", self.animal_valido(procedencia="Compra"))
        self.post("/ganado/nuevo", self.animal_valido(identificacion="302", procedencia="Finca Campo Alegre"))
        m = self.movs()
        self.assertEqual([(x["tipo"], x["animal"]) for x in m], [("Entrada", "301")])

    def test_nacimiento_con_madre(self):
        self.post("/ganado/nuevo", self.animal_valido())
        self.post("/ganado/nuevo", self.animal_valido(identificacion="302", madre="301", categoria="Ternera",
                                                      fecha_nacimiento="2025-03-01", fecha_ingreso="2025-03-01",
                                                      procedencia="Finca Campo Alegre"))
        n = self.movs(tipo="Nacimiento")
        self.assertEqual(len(n), 1)
        self.assertEqual(n[0]["madre"], "301")
        html = self.client.get("/ganado/301").get_data(as_text=True)
        self.assertIn('href="/ganado/302"', html)
        self.assertIn("Madre 301", self.client.get("/movimientos/").get_data(as_text=True))

    def test_madre_invalida(self):
        self.post("/ganado/nuevo", self.animal_valido(identificacion="400", sexo="Macho", categoria="Toro"))
        for madre in ("999", "400", "302"):
            self.post("/ganado/nuevo", self.animal_valido(identificacion="302", madre=madre, fecha_nacimiento="2024-01-01", fecha_ingreso="2024-01-01"))
        self.post("/ganado/nuevo", self.animal_valido())
        self.post("/ganado/nuevo", self.animal_valido(identificacion="303", madre="301", fecha_nacimiento="2022-05-10"))
        with self.app.app_context():
            self.assertEqual(get_db().animales.count_documents({"identificacion": {"$in": ["302", "303"]}}), 0)

    def test_salida_cambia_estado_y_bloquea_eventos(self):
        self.post("/ganado/nuevo", self.animal_valido())
        self.salida()
        self.assertEqual(self.estado("301"), "Vendido")
        self.assertEqual(self.movs(tipo="Salida")[0]["motivo"], "Venta")
        self.salida(motivo="Muerte")  # ya no está activo
        self.assertEqual(len(self.movs(tipo="Salida")), 1)
        self.post("/reproductivo/nuevo", {"animal": "301", "tipo": "Aborto", "fecha": "2026-01-11"})
        with self.app.app_context():
            self.assertEqual(get_db().eventos_reproductivos.count_documents({}), 0)

    def test_estados_por_motivo(self):
        for i, (motivo, estado) in enumerate([("Muerte", "Fallecido"), ("Traslado", "Trasladado"), ("Otro", "Retirado")]):
            ident = f"4{i}"
            self.post("/ganado/nuevo", self.animal_valido(identificacion=ident))
            self.salida(animal=ident, motivo=motivo)
            self.assertEqual(self.estado(ident), estado)

    def test_validaciones_de_salida(self):
        self.post("/ganado/nuevo", self.animal_valido())
        self.salida(motivo="")
        self.salida(motivo="Regalo")
        self.salida(fecha="2999-01-01")
        self.salida(fecha="2022-01-01")  # antes del ingreso
        self.salida(animal="999")
        self.salida(animal="")
        self.salida(detalle="x" * 501)
        self.assertEqual(self.movs(tipo="Salida"), [])
        self.assertEqual(self.estado("301"), "Activa")

    def test_novedad_y_eliminar(self):
        self.post("/ganado/nuevo", self.animal_valido())
        self.post("/movimientos/novedad", {"animal": "301", "fecha": "2026-01-05", "detalle": ""})
        self.post("/movimientos/novedad", {"animal": "301", "fecha": "2026-01-05", "detalle": "Cojera leve"})
        self.assertIn("Cojera leve", self.client.get("/ganado/301").get_data(as_text=True))
        mid = str(self.movs(tipo="Novedad")[0]["_id"])
        self.post(f"/movimientos/{mid}/eliminar")
        self.assertEqual(self.movs(tipo="Novedad"), [])

    def test_eliminar_salida_reactiva_y_altas_no_se_borran(self):
        self.post("/ganado/nuevo", self.animal_valido(procedencia="Compra"))
        self.salida()
        sid = str(self.movs(tipo="Salida")[0]["_id"])
        eid = str(self.movs(tipo="Entrada")[0]["_id"])
        self.post(f"/movimientos/{eid}/eliminar")
        self.assertEqual(len(self.movs(tipo="Entrada")), 1)
        self.post(f"/movimientos/{sid}/eliminar")
        self.assertEqual(self.estado("301"), "Activa")

    def test_no_se_elimina_animal_con_salida_pero_si_con_solo_alta(self):
        self.post("/ganado/nuevo", self.animal_valido(procedencia="Compra"))
        self.salida()
        self.post("/ganado/301/eliminar")
        self.assertEqual(self.estado("301"), "Vendido")
        self.post("/ganado/nuevo", self.animal_valido(identificacion="302", procedencia="Donación"))
        self.post("/ganado/302/eliminar")
        self.assertEqual(self.movs(animal="302"), [])

    def test_filtros_de_la_lista(self):
        self.post("/ganado/nuevo", self.animal_valido(procedencia="Compra"))
        self.salida()
        self.post("/movimientos/novedad", {"animal": "301", "fecha": "2026-01-05", "detalle": "Nota"})
        h = self.client.get("/movimientos/?tipo=Salida").get_data(as_text=True)
        self.assertIn("Venta", h)
        self.assertNotIn("Nota", h)
        h = self.client.get("/movimientos/?desde=2026-01-08&hasta=2026-01-31").get_data(as_text=True)
        self.assertIn("Venta", h)
        self.assertNotIn("Nota", h)
        self.assertIn("coincide", self.client.get("/movimientos/?q=zzz").get_data(as_text=True))

    def test_empleado_solo_consulta(self):
        self.post("/ganado/nuevo", self.animal_valido())
        self.salida()
        self.post("/logout")
        self.entrar("empleado", CLAVE_EMPLEADO)
        h = self.client.get("/movimientos/").get_data(as_text=True)
        self.assertIn("Venta", h)
        for t in ("Registrar salida", "Novedad</a>", "Eliminar"):
            self.assertNotIn(t, h)
        for ruta in ("/movimientos/salida", "/movimientos/novedad"):
            self.assertEqual(self.client.get(ruta).status_code, 302)
        self.post("/movimientos/novedad", {"animal": "301", "fecha": "2026-01-05", "detalle": "X"})
        self.assertEqual(len(self.movs(tipo="Novedad")), 0)
        mid = str(self.movs(tipo="Salida")[0]["_id"])
        self.post(f"/movimientos/{mid}/eliminar")
        self.assertEqual(len(self.movs(tipo="Salida")), 1)
        self.assertEqual(self.estado("301"), "Vendido")


if __name__ == "__main__":
    unittest.main()
