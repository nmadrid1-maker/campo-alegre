"""Pruebas de los datos de demostración (3 vacas por potrero)."""
import unittest
from datetime import datetime, timedelta

from base import BaseTest
from campo_alegre.db import get_db
from campo_alegre.reproductivo import partos_probables, resumen
from campo_alegre.sanitario import contar_proximas_dosis
from campo_alegre.semilla import (
    VACAS_POR_POTRERO,
    asignar_potreros_ejemplo,
    borrar_demo,
    crear_animales_ejemplo,
    crear_demo,
    crear_potreros,
)


class DemoBase(BaseTest):
    def setUp(self):
        super().setUp()
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.db = get_db()
        self.addCleanup(self.ctx.pop)
        self.resumen = crear_demo(self.db)

    def demo(self, coleccion):
        return list(getattr(self.db, coleccion).find({"demo": True}))

    def vacas(self):
        """Las 81 vacas de demostración (las crías y los animales que salieron tienen otros números)."""
        return [a for a in self.demo("animales") if a["identificacion"] < "700"]


class PruebasContenido(DemoBase):
    def test_tres_vacas_por_cada_potrero(self):
        self.assertEqual(self.db.potreros.count_documents({}), 27)
        for p in self.db.potreros.find({}):
            n = len([a for a in self.vacas() if a["potrero"] == p["nombre"]])
            self.assertEqual(n, VACAS_POR_POTRERO, p["nombre"])
        self.assertEqual(self.resumen["animales"], 81)

    def test_todos_los_campos_de_los_animales_estan_llenos(self):
        for a in self.vacas():
            for campo in ("identificacion", "nombre", "sexo", "categoria", "estado", "fecha_nacimiento",
                          "fecha_ingreso", "procedencia", "potrero", "observaciones"):
                self.assertTrue(a.get(campo), (a["identificacion"], campo))
            self.assertEqual((a["sexo"], a["categoria"], a["estado"]), ("Hembra", "Vaca", "Activa"))
            self.assertLessEqual(a["fecha_nacimiento"], a["fecha_ingreso"])
            self.assertLessEqual(a["fecha_ingreso"], datetime.now())

    def test_identificaciones_y_nombres_unicos(self):
        animales = self.demo("animales")
        self.assertEqual(len({a["identificacion"] for a in animales}), len(animales))
        vacas = self.vacas()
        self.assertEqual(len({a["nombre"] for a in vacas}), 81)

    def test_eventos_cumplen_las_reglas_del_sistema(self):
        nacimientos = {a["identificacion"]: a["fecha_nacimiento"] for a in self.demo("animales")}
        ahora = datetime.now()
        for coleccion, campo in (("eventos_sanitarios", "fecha_aplicacion"), ("eventos_reproductivos", "fecha"),
                                 ("pesajes", "fecha"), ("traslados", "fecha")):
            docs = self.demo(coleccion)
            self.assertGreater(len(docs), 81, coleccion)
            for d in docs:
                self.assertIn(d["animal"], nacimientos)
                self.assertGreaterEqual(d[campo], nacimientos[d["animal"]], (coleccion, d["animal"]))
                self.assertLessEqual(d[campo], ahora, (coleccion, d["animal"]))
                self.assertEqual(d["registrado_por"], "admin")

    def test_sanitarios_con_proxima_dosis_posterior_y_observaciones(self):
        for e in self.demo("eventos_sanitarios"):
            self.assertTrue(e["observaciones"])
            if e["proxima_dosis"]:
                self.assertGreater(e["proxima_dosis"], e["fecha_aplicacion"])

    def test_reproductivos_completos_por_tipo(self):
        tipos = set()
        for e in self.demo("eventos_reproductivos"):
            tipos.add(e["tipo"])
            self.assertTrue(e["observaciones"])
            if e["tipo"] == "Servicio":
                self.assertTrue(e["metodo"] and e["reproductor"])
                self.assertEqual(e["parto_probable"], e["fecha"] + timedelta(days=283))
            elif e["tipo"] == "Diagnóstico de preñez":
                self.assertIn(e["resultado"], ("Preñada", "Vacía"))
            elif e["tipo"] == "Parto":
                self.assertIn(e["cria_estado"], ("Viva", "Muerta"))
                self.assertIn(e["cria_sexo"], ("Hembra", "Macho"))
        self.assertEqual(tipos, {"Servicio", "Diagnóstico de preñez", "Parto", "Aborto"})

    def test_pesajes_validos_y_sin_repetir_fecha(self):
        vistos = set()
        for p in self.demo("pesajes"):
            self.assertTrue(10 <= p["peso_kg"] <= 1500)
            self.assertTrue(p["observaciones"])
            clave = (p["animal"], p["fecha"])
            self.assertNotIn(clave, vistos)
            vistos.add(clave)

    def test_el_ultimo_traslado_coincide_con_el_potrero_actual(self):
        for a in self.demo("animales"):
            t = sorted(self.db.traslados.find({"animal": a["identificacion"]}), key=lambda x: x["fecha"])
            self.assertEqual(t[-1]["hacia"], a["potrero"], a["identificacion"])
            self.assertIsNone(t[0]["desde"])
            for previo, siguiente in zip(t, t[1:]):
                self.assertEqual(previo["hacia"], siguiente["desde"])

    def test_el_inicio_tiene_avisos_con_datos(self):
        self.assertGreater(contar_proximas_dosis(), 0)
        self.assertGreater(len(partos_probables()), 0)
        recientes, partos = resumen()
        self.assertGreater(recientes, 0)
        self.assertEqual(partos, len(partos_probables()))


class PruebasUsoEnLaAplicacion(DemoBase):
    def test_pantallas_con_datos_responden(self):
        self.entrar()
        for ruta in ("/inicio", "/ganado/", "/ganado/?potrero=Palera", "/ganado/401", "/potreros/", "/sanitario/",
                     "/reproductivo/", "/productivo/", "/informes/inventario", "/informes/sanitario",
                     "/informes/reproductivo", "/informes/productivo"):
            self.assertEqual(self.client.get(ruta).status_code, 200, ruta)
        self.assertIn("de 3 animales", self.client.get("/ganado/?potrero=Palera").get_data(as_text=True))

    def test_se_puede_editar_un_animal_demo_sin_errores(self):
        self.entrar()
        a = self.db.animales.find_one({"identificacion": "405"})
        datos = {"nombre": a["nombre"], "sexo": a["sexo"], "categoria": a["categoria"],
                 "fecha_nacimiento": a["fecha_nacimiento"].strftime("%Y-%m-%d"),
                 "fecha_ingreso": a["fecha_ingreso"].strftime("%Y-%m-%d"), "procedencia": a["procedencia"],
                 "potrero": a["potrero"], "estado": "Activa", "observaciones": a["observaciones"]}
        self.assertEqual(self.post("/ganado/405/editar", datos).status_code, 302)


class PruebasMovimientosDemo(DemoBase):
    def test_hay_de_los_cuatro_tipos_y_motivos(self):
        movs = self.demo("movimientos")
        self.assertEqual({m["tipo"] for m in movs}, {"Nacimiento", "Entrada", "Salida", "Novedad"})
        self.assertEqual({m["motivo"] for m in movs if m["tipo"] == "Salida"}, {"Venta", "Muerte", "Traslado", "Otro"})
        self.assertGreaterEqual(self.resumen["crias"], 3)
        self.assertEqual(self.resumen["salidas"], 6)
        self.assertEqual(self.resumen["novedades"], 15)

    def test_nacimientos_enlazan_con_la_madre(self):
        animales = {a["identificacion"]: a for a in self.demo("animales")}
        for m in [m for m in self.demo("movimientos") if m["tipo"] == "Nacimiento"]:
            cria, madre = animales[m["animal"]], animales[m["madre"]]
            self.assertEqual(cria["madre"], m["madre"])
            self.assertEqual(cria["sexo"] == "Hembra", cria["categoria"] == "Ternera")
            self.assertEqual(madre["sexo"], "Hembra")
            self.assertEqual(m["fecha"], cria["fecha_nacimiento"])
            self.assertGreater(cria["fecha_nacimiento"], madre["fecha_nacimiento"])

    def test_salidas_dejan_el_estado_correcto_y_fechas_validas(self):
        animales = {a["identificacion"]: a for a in self.demo("animales")}
        esperado = {"Venta": "Vendido", "Muerte": "Fallecido", "Traslado": "Trasladado", "Otro": "Retirado"}
        ahora = datetime.now()
        for m in [m for m in self.demo("movimientos") if m["tipo"] == "Salida"]:
            a = animales[m["animal"]]
            self.assertEqual(a["estado"], esperado[m["motivo"]])
            self.assertTrue(m["detalle"])
            self.assertTrue(a["fecha_ingreso"] <= m["fecha"] <= ahora)
        for m in self.demo("movimientos"):
            a = animales[m["animal"]]
            self.assertGreaterEqual(m["fecha"], a["fecha_nacimiento"])
            self.assertLessEqual(m["fecha"], ahora)
            self.assertEqual(m["registrado_por"], "admin")

    def test_entradas_son_de_compras_y_donaciones(self):
        animales = {a["identificacion"]: a for a in self.demo("animales")}
        entradas = [m for m in self.demo("movimientos") if m["tipo"] == "Entrada"]
        self.assertTrue(entradas)
        for m in entradas:
            self.assertIn(animales[m["animal"]]["procedencia"], ("Compra", "Donación"))
            self.assertEqual(m["fecha"], animales[m["animal"]]["fecha_ingreso"])

    def test_pantallas_de_movimientos_responden(self):
        self.entrar()
        for ruta in ("/movimientos/", "/movimientos/?tipo=Salida", "/informes/movimientos", "/informes/movimientos?formato=csv",
                     "/ganado/?estado=Vendido", "/ganado/701"):
            self.assertEqual(self.client.get(ruta).status_code, 200, ruta)
        self.assertIn("Madre", self.client.get("/ganado/701").get_data(as_text=True))


class PruebasIdempotenciaYBorrado(BaseTest):
    def test_no_duplica_y_borra_solo_lo_demo(self):
        with self.app.app_context():
            db = get_db()
            crear_animales_ejemplo(db)
            crear_potreros(db)
            asignar_potreros_ejemplo(db)
            r = crear_demo(db)
            self.assertIsNotNone(r)
            extra = r["crias"] + r["salidas"]
            antes = db.animales.count_documents({})
            self.assertIsNone(crear_demo(db))
            self.assertEqual(db.animales.count_documents({}), antes)
            self.assertEqual(antes, 8 + 81 + extra)
            self.assertGreater(borrar_demo(db), 0)
            self.assertEqual(db.animales.count_documents({}), 8)
            for c in ("eventos_sanitarios", "eventos_reproductivos", "pesajes", "traslados", "movimientos"):
                self.assertEqual(getattr(db, c).count_documents({"demo": True}), 0, c)
            self.assertEqual(db.potreros.count_documents({}), 27)
            self.assertEqual(db.animales.find_one({"identificacion": "125"})["potrero"], "Palera")
            self.assertGreater(db.traslados.count_documents({}), 0)  # los traslados de los ejemplos siguen

    def test_completa_una_demo_antigua_sin_movimientos(self):
        with self.app.app_context():
            db = get_db()
            crear_demo(db)
            db.movimientos.delete_many({"demo": True})
            db.animales.delete_many({"demo": True, "identificacion": {"$gte": "700"}})
            r = crear_demo(db)
            self.assertGreater(r["movimientos"], 0)
            self.assertNotIn("animales", r)
            self.assertIsNone(crear_demo(db))

    def test_funciona_sin_potreros_previos(self):
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.potreros.count_documents({}), 0)
            self.assertEqual(crear_demo(db)["animales"], 81)
            self.assertEqual(db.potreros.count_documents({}), 27)


if __name__ == "__main__":
    unittest.main()
