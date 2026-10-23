"""Pruebas de Potreros y ubicación de los animales (RF-07)."""
import unittest

from base import CLAVE_EMPLEADO, BaseTest
from campo_alegre.db import get_db
from campo_alegre.semilla import (
    POTREROS_FINCA,
    asignar_potreros_ejemplo,
    crear_animales_ejemplo,
    crear_potreros,
)


class PotrerosBase(BaseTest):
    def setUp(self):
        super().setUp()
        with self.app.app_context():
            crear_animales_ejemplo(get_db())
        self.entrar()

    def crear(self, nombre, obs=""):
        return self.post("/potreros/nuevo", {"nombre": nombre, "observaciones": obs})

    def potrero(self, nombre):
        with self.app.app_context():
            return get_db().potreros.find_one({"nombre_lower": nombre.lower()})

    def pid(self, nombre):
        return str(self.potrero(nombre)["_id"])

    def animal(self, ident):
        with self.app.app_context():
            return get_db().animales.find_one({"identificacion": ident})

    def traslados(self, ident=None):
        with self.app.app_context():
            return list(get_db().traslados.find({"animal": ident} if ident else {}))

    def editar_animal(self, ident, **cambios):
        a = self.animal(ident)
        datos = {"nombre": a["nombre"], "sexo": a["sexo"], "categoria": a["categoria"],
                 "fecha_nacimiento": a["fecha_nacimiento"].strftime("%Y-%m-%d"),
                 "fecha_ingreso": a["fecha_ingreso"].strftime("%Y-%m-%d"),
                 "procedencia": a.get("procedencia") or "", "estado": a["estado"],
                 "potrero": a.get("potrero") or "", "observaciones": ""}
        datos.update(cambios)
        return self.post(f"/ganado/{ident}/editar", datos)


class PruebasCrud(PotrerosBase):
    def test_crear(self):
        r = self.crear("  El   Roto  ", "cerca del río")
        self.assertEqual(r.status_code, 302)
        p = self.potrero("el roto")
        self.assertEqual((p["nombre"], p["activo"], p["observaciones"]), ("El Roto", True, "cerca del río"))

    def test_validaciones(self):
        self.crear("Palera")
        casos = [("", "Escriba el nombre"), ("x" * 41, "hasta 40"), ("palera", "Ya existe"), ("PALERA", "Ya existe")]
        for nombre, texto in casos:
            r = self.crear(nombre)
            self.assertEqual(r.status_code, 200, nombre)
            self.assertIn(texto, r.get_data(as_text=True))
        self.assertIn("hasta 200", self.crear("Otro", "x" * 201).get_data(as_text=True))

    def test_editar_y_no_chocar_con_otro(self):
        self.crear("Palera")
        self.crear("Perillo")
        self.assertIn("Ya existe", self.post(f"/potreros/{self.pid('Perillo')}/editar", {"nombre": "palera"}).get_data(as_text=True))
        # guardar con su mismo nombre (otra capitalización) sí se permite
        r = self.post(f"/potreros/{self.pid('Perillo')}/editar", {"nombre": "PERILLO", "observaciones": "x"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.potrero("perillo")["nombre"], "PERILLO")

    def test_renombrar_actualiza_animales_e_historial(self):
        self.crear("Palera")
        self.editar_animal("125", potrero="Palera")
        self.post(f"/potreros/{self.pid('Palera')}/editar", {"nombre": "Palera Alta"})
        self.assertEqual(self.animal("125")["potrero"], "Palera Alta")
        self.assertEqual(self.traslados("125")[0]["hacia"], "Palera Alta")

    def test_inexistente(self):
        self.assertEqual(self.client.get("/potreros/zzz/editar").status_code, 302)
        self.assertEqual(self.post("/potreros/zzz/eliminar").status_code, 302)
        self.assertEqual(self.post("/potreros/zzz/estado").status_code, 302)

    def test_desactivar_y_activar(self):
        self.crear("Palera")
        self.post(f"/potreros/{self.pid('Palera')}/estado")
        self.assertFalse(self.potrero("palera")["activo"])
        self.post(f"/potreros/{self.pid('Palera')}/estado")
        self.assertTrue(self.potrero("palera")["activo"])

    def test_no_se_desactiva_con_animales_activos(self):
        self.crear("Palera")
        self.editar_animal("125", potrero="Palera")
        r = self.post(f"/potreros/{self.pid('Palera')}/estado")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(self.potrero("palera")["activo"])
        self.assertIn("No se puede desactivar", self.client.get("/potreros/").get_data(as_text=True))

    def test_animal_vendido_no_impide_desactivar_pero_si_eliminar(self):
        self.crear("Palera")
        self.editar_animal("125", potrero="Palera")
        self.editar_animal("125", potrero="Palera", estado="Vendido")
        self.post(f"/potreros/{self.pid('Palera')}/estado")
        self.assertFalse(self.potrero("palera")["activo"])
        self.post(f"/potreros/{self.pid('Palera')}/eliminar")
        self.assertIsNotNone(self.potrero("palera"))

    def test_eliminar_sin_uso(self):
        self.crear("Palera")
        self.post(f"/potreros/{self.pid('Palera')}/eliminar")
        self.assertIsNone(self.potrero("palera"))

    def test_no_se_elimina_con_historial(self):
        self.crear("Palera")
        self.editar_animal("125", potrero="Palera")
        self.editar_animal("125", potrero="")  # ya no está allí, pero queda el historial
        self.post(f"/potreros/{self.pid('Palera')}/eliminar")
        self.assertIsNotNone(self.potrero("palera"))

    def test_lista_muestra_conteo(self):
        self.crear("Palera")
        self.editar_animal("125", potrero="Palera")
        self.editar_animal("221", potrero="Palera")
        h = self.client.get("/potreros/").get_data(as_text=True)
        self.assertIn("2 animales activos ubicados", h)
        self.assertIn("potrero=Palera", h)


class PruebasAnimales(PotrerosBase):
    def setUp(self):
        super().setUp()
        self.crear("Palera")
        self.crear("La Vega")

    def test_potrero_en_alta_registra_traslado_inicial(self):
        r = self.post("/ganado/nuevo", self.animal_valido(potrero="Palera"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.animal("301")["potrero"], "Palera")
        t = self.traslados("301")
        self.assertEqual((len(t), t[0]["desde"], t[0]["hacia"]), (1, None, "Palera"))

    def test_sin_potrero(self):
        self.post("/ganado/nuevo", self.animal_valido())
        self.assertIsNone(self.animal("301")["potrero"])
        self.assertEqual(self.traslados("301"), [])

    def test_potrero_inexistente_o_inactivo(self):
        r = self.post("/ganado/nuevo", self.animal_valido(potrero="Inventado"))
        self.assertIn("Seleccione un potrero", r.get_data(as_text=True))
        self.post(f"/potreros/{self.pid('La Vega')}/estado")
        r = self.post("/ganado/nuevo", self.animal_valido(potrero="La Vega"))
        self.assertIn("Seleccione un potrero", r.get_data(as_text=True))
        self.assertEqual(self.contar({"identificacion": "301"}), 0)

    def test_cambio_de_potrero_registra_traslado(self):
        self.editar_animal("125", potrero="Palera")
        self.editar_animal("125", potrero="La Vega")
        t = sorted(self.traslados("125"), key=lambda x: x["creado_en"])
        self.assertEqual([(x["desde"], x["hacia"]) for x in t], [(None, "Palera"), ("Palera", "La Vega")])

    def test_editar_sin_cambiar_potrero_no_registra_nada(self):
        self.editar_animal("125", potrero="Palera")
        self.editar_animal("125", potrero="Palera", nombre="Luna Nueva")
        self.assertEqual(len(self.traslados("125")), 1)

    def test_quitar_potrero_registra_traslado_a_ninguno(self):
        self.editar_animal("125", potrero="Palera")
        self.editar_animal("125", potrero="")
        self.assertIsNone(self.animal("125")["potrero"])
        self.assertEqual(len(self.traslados("125")), 2)
        self.assertIn("Palera → sin potrero", self.client.get("/ganado/125").get_data(as_text=True))

    def test_animal_en_potrero_desactivado_se_puede_seguir_editando(self):
        self.editar_animal("125", potrero="Palera", estado="Fallecido")
        self.post(f"/potreros/{self.pid('Palera')}/estado")  # se desactiva (el animal ya no está activo)
        r = self.editar_animal("125", potrero="Palera", estado="Fallecido", nombre="Luna II")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.animal("125")["nombre"], "Luna II")

    def test_ficha_y_lista_muestran_potrero(self):
        self.editar_animal("125", potrero="Palera")
        self.assertIn("Palera", self.client.get("/ganado/125").get_data(as_text=True))
        h = self.client.get("/ganado/").get_data(as_text=True)
        self.assertIn("<th>Potrero</th>", h)

    def test_filtro_de_lista_por_potrero_y_con_paginacion(self):
        self.editar_animal("125", potrero="Palera")
        self.editar_animal("221", potrero="Palera")
        self.editar_animal("248", potrero="La Vega")
        h = self.client.get("/ganado/?potrero=Palera").get_data(as_text=True)
        self.assertIn("de 2 animales", h)
        self.assertIn("de 1 animales", self.client.get("/ganado/?potrero=La+Vega").get_data(as_text=True))
        self.assertIn("de 8 animales", self.client.get("/ganado/").get_data(as_text=True))

    def test_eliminar_animal_borra_su_historial_de_traslados(self):
        self.post("/ganado/nuevo", self.animal_valido(potrero="Palera"))
        self.post("/ganado/301/eliminar")
        self.assertEqual(self.contar({"identificacion": "301"}), 0)
        self.assertEqual(self.traslados("301"), [])

    def test_informe_inventario_por_potrero(self):
        self.editar_animal("125", potrero="Palera")
        self.editar_animal("221", potrero="Palera")
        h = self.client.get("/informes/inventario?potrero=Palera").get_data(as_text=True)
        self.assertIn("Potrero Palera</span><strong>2", h)
        r = self.client.get("/informes/inventario?formato=csv&potrero=Palera")
        filas = r.get_data(as_text=True).splitlines()
        self.assertEqual(len(filas) - 1, 2)
        self.assertIn("Potrero", filas[0])
        h = self.client.get("/informes/inventario").get_data(as_text=True)
        self.assertIn("Potrero Sin potrero</span><strong>6", h)


class PruebasPermisosYSemilla(PotrerosBase):
    def test_empleado_consulta_pero_no_modifica(self):
        self.crear("Palera")
        self.post("/logout")
        self.entrar("empleado", CLAVE_EMPLEADO)
        html = self.client.get("/potreros/").get_data(as_text=True)
        self.assertIn("Palera", html)
        for texto in ("Nuevo potrero", "Eliminar", "Desactivar", "<th>Acciones</th>"):
            self.assertNotIn(texto, html)
        self.assertEqual(self.client.get("/potreros/nuevo").status_code, 302)
        self.crear("Hackeado")
        self.post(f"/potreros/{self.pid('Palera')}/eliminar")
        self.post(f"/potreros/{self.pid('Palera')}/estado")
        self.assertIsNone(self.potrero("hackeado"))
        self.assertTrue(self.potrero("palera")["activo"])

    def test_sin_sesion_y_sin_csrf(self):
        self.assertEqual(self.client.post("/potreros/nuevo", data={"nombre": "X"}).status_code, 400)
        self.post("/logout")
        self.assertEqual(self.client.get("/potreros/").status_code, 302)

    def test_semilla_carga_los_potreros_reales_sin_duplicar(self):
        with self.app.app_context():
            db = get_db()
            self.assertEqual(crear_potreros(db), len(POTREROS_FINCA))
            self.assertEqual(crear_potreros(db), 0)
            self.assertEqual(db.potreros.count_documents({}), 27)
            self.assertEqual(len({p.lower() for p in POTREROS_FINCA}), 27)
            self.assertGreater(asignar_potreros_ejemplo(db), 0)
            self.assertEqual(asignar_potreros_ejemplo(db), 0)
            self.assertEqual(db.animales.find_one({"identificacion": "125"})["potrero"], "Palera")
        self.assertIn("Llano Chulo", self.client.get("/potreros/").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
