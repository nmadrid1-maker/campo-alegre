import unittest
from datetime import datetime, timedelta

from base import BaseTest
from campo_alegre.db import get_db
from campo_alegre.reproductivo import estado_de, gestantes_sin_fecha, partos_probables


def fecha(dias):
    return (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")


class Base(BaseTest):
    def setUp(self):
        super().setUp()
        self.entrar()
        for ident in ("301", "302"):
            self.post("/ganado/nuevo", self.animal_valido(identificacion=ident))

    def ev(self, animal="301", tipo="Servicio", dias=-10, **extra):
        d = {"animal": animal, "tipo": tipo, "fecha": fecha(dias), "metodo": "Monta"}
        d.update(extra)
        return self.post("/reproductivo/nuevo", d)

    def diag(self, animal="301", dias=-5, resultado="Preñada", **extra):
        return self.ev(animal, "Diagnóstico de preñez", dias, resultado=resultado, **extra)

    def docs(self, **f):
        with self.app.app_context():
            return list(get_db().eventos_reproductivos.find(f).sort("creado_en", 1))

    def estado(self, ident="301"):
        with self.app.app_context():
            return estado_de(ident)


class PruebasFechaDeParto(Base):
    def test_desde_servicio_toma_la_fecha_del_servicio(self):
        self.ev(dias=-100)
        self.diag(parto_modo="Desde servicio")
        d = self.docs(tipo="Diagnóstico de preñez")[0]
        self.assertEqual(d["parto_modo"], "Desde servicio")
        self.assertEqual(d["parto_estimado"].date(), (datetime.now() + timedelta(days=-100 + 283)).date())

    def test_desde_servicio_sin_servicio_vigente_falla(self):
        self.diag(parto_modo="Desde servicio")
        self.assertEqual(self.docs(), [])
        self.ev(dias=-100)
        self.ev(tipo="Aborto", dias=-50)  # el aborto cierra el servicio
        self.diag(parto_modo="Desde servicio")
        self.assertEqual(len(self.docs(tipo="Diagnóstico de preñez")), 0)

    def test_fecha_indicada(self):
        self.diag(parto_modo="Fecha indicada", parto_estimado=fecha(120))
        self.assertEqual(self.docs()[0]["parto_estimado"].strftime("%Y-%m-%d"), fecha(120))

    def test_fecha_indicada_invalida(self):
        for valor in ("", "basura", fecha(-9), fecha(-5 + 284)):
            self.diag(parto_modo="Fecha indicada", parto_estimado=valor)
        self.assertEqual(self.docs(), [])
        self.diag(parto_modo="Fecha indicada", parto_estimado=fecha(-5 + 283))  # justo en el límite
        self.assertEqual(len(self.docs()), 1)

    def test_desconocida_y_modo_invalido(self):
        self.diag(parto_modo="Desconocida")
        d = self.docs()[0]
        self.assertEqual((d["parto_modo"], d["parto_estimado"]), ("Desconocida", None))
        self.diag(animal="302", parto_modo="Inventado")
        self.assertEqual(self.docs(animal="302"), [])

    def test_sin_modo_se_deduce(self):
        self.diag()  # sin servicio: desconocida
        self.assertEqual(self.docs()[0]["parto_modo"], "Desconocida")
        self.ev("302", dias=-100)
        self.diag("302")  # con servicio vigente: se calcula
        self.assertEqual(self.docs(animal="302", tipo="Diagnóstico de preñez")[0]["parto_modo"], "Desde servicio")

    def test_vacia_no_guarda_datos_de_parto(self):
        self.diag(resultado="Vacía", parto_modo="Fecha indicada", parto_estimado=fecha(50))
        d = self.docs()[0]
        self.assertEqual((d["parto_modo"], d["parto_estimado"]), (None, None))

    def test_detalle_en_la_lista(self):
        self.diag(parto_modo="Desconocida")
        self.diag(animal="302", parto_modo="Fecha indicada", parto_estimado=fecha(100))
        h = self.client.get("/reproductivo/").get_data(as_text=True)
        self.assertIn("fecha de parto desconocida", h)
        self.assertIn("parto estimado", h)

    def test_formulario_tiene_los_controles(self):
        h = self.client.get("/reproductivo/nuevo").get_data(as_text=True)
        for t in ("Calcular desde el último servicio", "Indicar la fecha", "Desconocida", 'name="parto_estimado"'):
            self.assertIn(t, h)


class PruebasEstado(Base):
    def test_secuencia_de_estados(self):
        self.assertEqual(self.estado()["estado"], "Sin datos")
        self.ev(dias=-100)
        self.assertEqual(self.estado()["estado"], "En servicio")
        self.diag(dias=-60, parto_modo="Desde servicio")
        e = self.estado()
        self.assertEqual(e["estado"], "Gestante")
        self.assertIsNotNone(e["parto_estimado"])
        self.ev(tipo="Parto", dias=-3, cria_estado="Viva")
        self.assertEqual(self.estado()["estado"], "Parida")
        self.ev(dias=-2)
        self.diag(dias=-1, resultado="Vacía")
        self.assertEqual(self.estado()["estado"], "Vacía")

    def test_aborto_deja_vacia(self):
        self.diag(parto_modo="Desconocida", dias=-20)
        self.ev(tipo="Aborto", dias=-5)
        self.assertEqual(self.estado()["estado"], "Vacía")

    def test_registro_antiguo_sin_modo_usa_el_servicio(self):
        with self.app.app_context():
            c = get_db().eventos_reproductivos
            base = datetime.now() - timedelta(days=100)
            c.insert_one({"animal": "301", "tipo": "Servicio", "fecha": base, "parto_probable": base + timedelta(days=283),
                          "creado_en": base})
            c.insert_one({"animal": "301", "tipo": "Diagnóstico de preñez", "resultado": "Preñada",
                          "fecha": base + timedelta(days=60), "creado_en": base + timedelta(days=60)})
        e = self.estado()
        self.assertEqual((e["estado"], e["modo"]), ("Gestante", "Desde servicio"))
        self.assertIsNotNone(e["parto_estimado"])

    def test_ficha_muestra_el_estado(self):
        self.diag(parto_modo="Desconocida")
        h = self.client.get("/ganado/301").get_data(as_text=True)
        self.assertIn("Gestante", h)
        self.assertIn("desconocida", h)
        self.post("/ganado/nuevo", self.animal_valido(identificacion="500", sexo="Macho", categoria="Toro"))
        self.assertNotIn("Estado reproductivo", self.client.get("/ganado/500").get_data(as_text=True))

    def test_filtro_en_ganado(self):
        self.diag(parto_modo="Desconocida")
        def ids(q):
            h = self.client.get("/ganado/?repro=" + q).get_data(as_text=True)
            return [i for i in ("301", "302") if f'href="/ganado/{i}"' in h]
        self.assertEqual(ids("Gestante"), ["301"])
        self.assertEqual(ids("Sin datos"), ["302"])
        self.assertEqual(ids("Parida"), [])
        self.assertEqual(ids("Inventado"), ["301", "302"])

    def test_filtro_combinado_con_peso(self):
        self.diag(parto_modo="Desconocida")
        self.diag(animal="302", parto_modo="Desconocida")
        self.post("/productivo/nuevo", {"animal": "301", "fecha": fecha(-1), "peso_kg": "400"})
        h = self.client.get("/ganado/?repro=Gestante&peso_min=350").get_data(as_text=True)
        self.assertIn('href="/ganado/301"', h)
        self.assertNotIn('href="/ganado/302"', h)


class PruebasAvisos(Base):
    def test_parto_por_diagnostico_en_la_ventana(self):
        self.diag(parto_modo="Fecha indicada", parto_estimado=fecha(10))
        with self.app.app_context():
            p = partos_probables()
        self.assertEqual([(x["animal"], x["origen"]) for x in p], [("301", "diagnóstico")])
        self.assertIn("diagnóstico del", self.client.get("/reproductivo/").get_data(as_text=True))

    def test_fuera_de_la_ventana_no_avisa(self):
        self.diag(parto_modo="Fecha indicada", parto_estimado=fecha(120))
        with self.app.app_context():
            self.assertEqual(partos_probables(), [])

    def test_la_fecha_del_diagnostico_manda_sobre_el_servicio(self):
        self.ev(dias=-275)  # el servicio diría parto en ~8 días
        self.diag(dias=-5, parto_modo="Fecha indicada", parto_estimado=fecha(100))
        with self.app.app_context():
            self.assertEqual(partos_probables(), [])
        self.diag(animal="302", dias=-300, parto_modo="Desconocida")
        self.ev("302", dias=-275, tipo="Servicio")  # servicio posterior al diagnóstico: vuelve a avisar por servicio
        with self.app.app_context():
            self.assertEqual([x["animal"] for x in partos_probables()], ["302"])

    def test_desconocida_con_servicio_no_avisa_por_servicio(self):
        self.ev(dias=-275)
        self.diag(dias=-5, parto_modo="Desconocida")
        with self.app.app_context():
            self.assertEqual(partos_probables(), [])
            self.assertEqual(gestantes_sin_fecha(), ["301"])

    def test_aviso_de_gestantes_sin_fecha_y_animales_inactivos(self):
        self.diag(parto_modo="Desconocida")
        h = self.client.get("/reproductivo/").get_data(as_text=True)
        self.assertIn("Gestantes sin fecha de parto (1)", h)
        self.post("/movimientos/salida", {"animal": "301", "fecha": fecha(-1), "motivo": "Venta"})
        with self.app.app_context():
            self.assertEqual(gestantes_sin_fecha(), [])
        self.assertNotIn("Gestantes sin fecha", self.client.get("/reproductivo/").get_data(as_text=True))

    def test_animal_vendido_no_aparece_en_partos_probables(self):
        self.diag(parto_modo="Fecha indicada", parto_estimado=fecha(10))
        self.ev("302", dias=-275)
        self.post("/movimientos/salida", {"animal": "301", "fecha": fecha(-1), "motivo": "Venta"})
        self.post("/movimientos/salida", {"animal": "302", "fecha": fecha(-1), "motivo": "Muerte"})
        with self.app.app_context():
            self.assertEqual(partos_probables(), [])

    def test_informe_reproductivo(self):
        self.diag(parto_modo="Desconocida")
        self.diag(animal="302", resultado="Vacía")
        h = self.client.get("/informes/reproductivo?estado_repro=Gestante").get_data(as_text=True)
        self.assertIn("<td>301</td>", h)
        self.assertNotIn("<td>302</td>", h)
        self.assertIn("Gestantes sin fecha de parto", h)
        csv = self.client.get("/informes/reproductivo?formato=csv").get_data(as_text=True)
        self.assertIn("fecha de parto desconocida", csv)


if __name__ == "__main__":
    unittest.main()
