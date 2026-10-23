"""Pruebas del módulo de Control sanitario (RF-03).

Ejecutar:  py -m unittest discover -s tests -v
"""
import re
import unittest
from datetime import datetime, timedelta

from base import CLAVE_EMPLEADO, BaseTest
from campo_alegre.db import get_db
from campo_alegre.semilla import crear_animales_ejemplo, crear_eventos_ejemplo


def fecha(dias):
    """Fecha de hoy +/- dias, en el formato que envía <input type="date">."""
    return (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")


class SanitarioBase(BaseTest):
    def setUp(self):
        super().setUp()
        with self.app.app_context():
            crear_animales_ejemplo(get_db())  # 125 Luna, 178 Trueno, ... y 236 Vendido

    def evento(self, **cambios):
        datos = {
            "animal": "125",
            "tipo": "Vacunación",
            "producto": "Fiebre aftosa",
            "fecha_aplicacion": fecha(-2),
            "proxima_dosis": fecha(100),
            "observaciones": "",
        }
        datos.update(cambios)
        return datos

    def contar_eventos(self, filtro=None):
        with self.app.app_context():
            return get_db().eventos_sanitarios.count_documents(filtro or {})

    def proximas_en_inicio(self):
        html = self.client.get("/inicio").get_data(as_text=True)
        return int(re.search(r'Próximas vacunas</span><span class="n">(\d+)</span>', html).group(1))


class PruebasRegistro(SanitarioBase):
    def test_admin_registra_un_evento(self):
        self.entrar()
        r = self.post("/sanitario/nuevo", self.evento())
        self.assertEqual(r.status_code, 302)
        self.assertIn("/sanitario/", r.headers["Location"])
        self.assertEqual(self.contar_eventos({"animal": "125", "tipo": "Vacunación"}), 1)
        with self.app.app_context():
            e = get_db().eventos_sanitarios.find_one({"animal": "125"})
        self.assertEqual(e["producto"], "Fiebre aftosa")
        self.assertEqual(e["registrado_por"], "admin")
        self.assertIsInstance(e["fecha_aplicacion"], datetime)

    def test_proxima_dosis_y_observaciones_son_opcionales(self):
        self.entrar()
        self.post("/sanitario/nuevo", self.evento(proxima_dosis="", observaciones=""))
        with self.app.app_context():
            e = get_db().eventos_sanitarios.find_one({"animal": "125"})
        self.assertIsNone(e["proxima_dosis"])
        self.assertIsNone(e["observaciones"])

    def test_empleado_no_puede_registrar(self):
        self.entrar("empleado", CLAVE_EMPLEADO)
        self.assertEqual(self.client.get("/sanitario/nuevo").status_code, 302)
        self.post("/sanitario/nuevo", self.evento())
        self.assertEqual(self.contar_eventos(), 0)

    def test_empleado_ve_el_listado_pero_no_elimina(self):
        self.entrar()
        self.post("/sanitario/nuevo", self.evento())
        with self.app.app_context():
            evento_id = str(get_db().eventos_sanitarios.find_one({})["_id"])
        self.post("/logout")
        self.entrar("empleado", CLAVE_EMPLEADO)
        r = self.client.get("/sanitario/")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("Fiebre aftosa", html)
        for texto in ("Registrar evento", "Eliminar", "<th>Acciones</th>"):
            self.assertNotIn(texto, html)
        self.post(f"/sanitario/{evento_id}/eliminar")
        self.assertEqual(self.contar_eventos(), 1)

    def test_sin_sesion_redirige_al_login(self):
        r = self.client.get("/sanitario/nuevo")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])
        r = self.post("/sanitario/nuevo", self.evento())
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.contar_eventos(), 0)

    def test_post_sin_token_csrf_es_rechazado(self):
        self.entrar()
        r = self.client.post("/sanitario/nuevo", data=self.evento())
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.contar_eventos(), 0)

    def test_el_formulario_viene_con_fecha_de_hoy_y_vacunacion(self):
        self.entrar()
        html = self.client.get("/sanitario/nuevo").get_data(as_text=True)
        self.assertIn(f'value="{fecha(0)}"', html)
        self.assertRegex(html, r'value="Vacunación"\s+checked')

    def test_animal_prellenado_desde_la_ficha(self):
        self.entrar()
        html = self.client.get("/sanitario/nuevo?animal=204").get_data(as_text=True)
        self.assertIn('name="animal" value="204"', html)

    def test_la_lista_de_animales_solo_trae_los_activos(self):
        self.entrar()
        html = self.client.get("/sanitario/nuevo").get_data(as_text=True)
        self.assertIn('<option value="125"', html)
        self.assertNotIn('<option value="236"', html)  # 236 figura como Vendido

    def test_actividad_reciente_en_el_inicio(self):
        self.entrar()
        self.post("/sanitario/nuevo", self.evento())
        html = self.client.get("/inicio").get_data(as_text=True)
        self.assertIn("Se registró un evento sanitario: Vacunación · Fiebre aftosa (animal 125)", html)

    def test_texto_con_html_se_escapa(self):
        self.entrar()
        self.post("/sanitario/nuevo", self.evento(producto="<script>alert(1)</script>"))
        html = self.client.get("/sanitario/").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)


class PruebasValidacion(SanitarioBase):
    def setUp(self):
        super().setUp()
        self.entrar()

    def rechaza(self, mensaje, **cambios):
        r = self.post("/sanitario/nuevo", self.evento(**cambios))
        self.assertEqual(r.status_code, 200)
        self.assertIn(mensaje, r.get_data(as_text=True))
        self.assertEqual(self.contar_eventos(), 0)
        return r

    def test_campos_obligatorios(self):
        r = self.post("/sanitario/nuevo", {})
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        for mensaje in ("Escriba la identificación del animal", "Seleccione el tipo de evento",
                        "Escriba el nombre del producto", "Indique la fecha de aplicación"):
            self.assertIn(mensaje, html)
        self.assertEqual(self.contar_eventos(), 0)

    def test_animal_inexistente(self):
        self.rechaza("No existe un animal con la identificación 9999", animal="9999")

    def test_animal_vendido_no_recibe_eventos(self):
        self.rechaza("El animal 236 figura como Vendido", animal="236")

    def test_tipo_invalido(self):
        self.rechaza("Seleccione el tipo de evento", tipo="Cirugía")

    def test_fecha_futura(self):
        self.rechaza("La fecha de aplicación no puede ser futura", fecha_aplicacion=fecha(3), proxima_dosis="")

    def test_fecha_anterior_al_nacimiento(self):
        # La vaca 125 nació el 12/04/2023
        self.rechaza("anterior al nacimiento", fecha_aplicacion="2000-01-01", proxima_dosis="")

    def test_fecha_con_formato_invalido(self):
        self.rechaza("Indique la fecha de aplicación", fecha_aplicacion="ayer")

    def test_proxima_dosis_debe_ser_posterior(self):
        self.rechaza("debe ser posterior a la fecha de aplicación", fecha_aplicacion=fecha(-2), proxima_dosis=fecha(-2))
        self.rechaza("debe ser posterior a la fecha de aplicación", fecha_aplicacion=fecha(-2), proxima_dosis=fecha(-3))

    def test_proxima_dosis_con_formato_invalido(self):
        self.rechaza("La fecha de la próxima dosis no es válida", proxima_dosis="abc")

    def test_producto_muy_largo(self):
        self.rechaza("hasta 80 caracteres", producto="x" * 81)

    def test_observaciones_muy_largas(self):
        self.rechaza("hasta 500 caracteres", observaciones="x" * 501)

    def test_el_formulario_conserva_lo_escrito_si_hay_error(self):
        r = self.post("/sanitario/nuevo", self.evento(animal="9999", producto="Brucelosis RB51"))
        html = r.get_data(as_text=True)
        self.assertIn('value="Brucelosis RB51"', html)
        self.assertIn('value="9999"', html)


class PruebasListado(SanitarioBase):
    def setUp(self):
        super().setUp()
        self.entrar()

    def test_filtros_por_tipo_busqueda_y_animal(self):
        self.post("/sanitario/nuevo", self.evento(animal="125", tipo="Vacunación", producto="Fiebre aftosa"))
        self.post("/sanitario/nuevo", self.evento(animal="125", tipo="Desparasitación", producto="Ivermectina"))
        self.post("/sanitario/nuevo", self.evento(animal="178", tipo="Vacunación", producto="Brucelosis"))

        por_tipo = self.client.get("/sanitario/", query_string={"tipo": "Vacunación"}).get_data(as_text=True)
        self.assertIn("Fiebre aftosa", por_tipo)
        self.assertIn("Brucelosis", por_tipo)
        self.assertNotIn("Ivermectina", por_tipo)

        por_texto = self.client.get("/sanitario/", query_string={"q": "ivermec"}).get_data(as_text=True)
        self.assertIn("Ivermectina", por_texto)
        self.assertNotIn("Brucelosis", por_texto)

        por_animal = self.client.get("/sanitario/", query_string={"animal": "178"}).get_data(as_text=True)
        self.assertIn("Brucelosis", por_animal)
        self.assertNotIn("Ivermectina", por_animal)
        self.assertIn("Mostrando solo los eventos del animal", por_animal)

    def test_busqueda_no_interpreta_regex(self):
        self.post("/sanitario/nuevo", self.evento())
        html = self.client.get("/sanitario/", query_string={"q": ".*"}).get_data(as_text=True)
        self.assertIn("Ningún evento coincide", html)

    def test_paginacion(self):
        for n in range(12):
            self.post("/sanitario/nuevo", self.evento(producto=f"Producto {n:02d}", proxima_dosis=""))
        self.assertIn("Mostrando 1 a 10 de 12 eventos", self.client.get("/sanitario/").get_data(as_text=True))
        self.assertIn("Mostrando 11 a 12 de 12 eventos", self.client.get("/sanitario/?page=2").get_data(as_text=True))

    def test_pagina_fuera_de_rango_no_falla(self):
        self.assertEqual(self.client.get("/sanitario/?page=999").status_code, 200)
        self.assertEqual(self.client.get("/sanitario/?page=abc").status_code, 200)
        self.assertEqual(self.client.get("/sanitario/?tipo=raro").status_code, 200)

    def test_listado_vacio_explica_que_hacer(self):
        html = self.client.get("/sanitario/").get_data(as_text=True)
        self.assertIn("Aún no hay eventos sanitarios", html)

    def test_ordena_de_lo_mas_reciente_a_lo_mas_antiguo(self):
        self.post("/sanitario/nuevo", self.evento(producto="Antiguo", fecha_aplicacion=fecha(-30), proxima_dosis=""))
        self.post("/sanitario/nuevo", self.evento(producto="Reciente", fecha_aplicacion=fecha(-1), proxima_dosis=""))
        html = self.client.get("/sanitario/").get_data(as_text=True)
        self.assertLess(html.index("Reciente"), html.index("Antiguo"))


class PruebasProximasDosis(SanitarioBase):
    def setUp(self):
        super().setUp()
        self.entrar()

    def test_el_inicio_cuenta_solo_las_dosis_de_los_proximos_30_dias(self):
        self.assertEqual(self.proximas_en_inicio(), 0)
        self.post("/sanitario/nuevo", self.evento(producto="En 10 dias", proxima_dosis=fecha(10)))
        self.post("/sanitario/nuevo", self.evento(producto="En 60 dias", proxima_dosis=fecha(60)))
        self.post("/sanitario/nuevo", self.evento(producto="Ya paso", fecha_aplicacion=fecha(-40), proxima_dosis=fecha(-5)))
        self.post("/sanitario/nuevo", self.evento(producto="Hoy mismo", proxima_dosis=fecha(0)))
        self.assertEqual(self.proximas_en_inicio(), 2)  # 10 días y hoy mismo

    def test_el_listado_muestra_el_panel_de_proximas_dosis(self):
        self.post("/sanitario/nuevo", self.evento(producto="Brucelosis", proxima_dosis=fecha(10)))
        html = self.client.get("/sanitario/").get_data(as_text=True)
        self.assertIn("Próximas dosis (30 días): 1", html)

    def test_sin_dosis_proximas_no_aparece_el_panel(self):
        self.post("/sanitario/nuevo", self.evento(proxima_dosis=fecha(100)))
        html = self.client.get("/sanitario/").get_data(as_text=True)
        self.assertNotIn("Próximas dosis (30 días)", html)


class PruebasEliminar(SanitarioBase):
    def setUp(self):
        super().setUp()
        self.entrar()
        self.post("/sanitario/nuevo", self.evento())
        with self.app.app_context():
            self.evento_id = str(get_db().eventos_sanitarios.find_one({})["_id"])

    def test_admin_elimina_un_evento(self):
        r = self.post(f"/sanitario/{self.evento_id}/eliminar")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.contar_eventos(), 0)
        html = self.client.get("/inicio").get_data(as_text=True)
        self.assertIn("Se eliminó un evento sanitario", html)

    def test_id_con_formato_invalido_no_rompe(self):
        r = self.post("/sanitario/no-es-un-id/eliminar")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.contar_eventos(), 1)

    def test_id_que_no_existe_no_rompe(self):
        r = self.post("/sanitario/" + "0" * 24 + "/eliminar")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.contar_eventos(), 1)


class PruebasIntegracionConGanado(SanitarioBase):
    def setUp(self):
        super().setUp()
        self.entrar()

    def test_la_ficha_muestra_el_historial_del_animal(self):
        self.post("/sanitario/nuevo", self.evento(producto="Fiebre aftosa"))
        html = self.client.get("/ganado/125").get_data(as_text=True)
        self.assertIn("Fiebre aftosa", html)
        self.assertIn("/sanitario/nuevo?animal=125", html)

    def test_la_ficha_de_un_animal_sin_eventos_lo_dice(self):
        html = self.client.get("/ganado/204").get_data(as_text=True)
        self.assertIn("todavía no tiene eventos sanitarios", html)

    def test_no_se_elimina_un_animal_con_eventos(self):
        self.post("/sanitario/nuevo", self.evento())
        self.post("/ganado/125/eliminar")
        self.assertEqual(self.contar({"identificacion": "125"}), 1)
        html = self.client.get("/ganado/125").get_data(as_text=True)
        self.assertIn("No se puede eliminar: el animal tiene eventos", html)

    def test_un_animal_sin_eventos_si_se_elimina(self):
        self.post("/ganado/204/eliminar")
        self.assertEqual(self.contar({"identificacion": "204"}), 0)

    def test_menu_del_admin_apunta_al_listado(self):
        html = self.client.get("/inicio").get_data(as_text=True)
        self.assertIn('href="/sanitario/"', html)


class PruebasSemilla(SanitarioBase):
    def test_eventos_de_ejemplo_se_crean_una_sola_vez(self):
        with self.app.app_context():
            self.assertEqual(crear_eventos_ejemplo(get_db()), 5)
            self.assertEqual(crear_eventos_ejemplo(get_db()), 0)

    def test_la_semilla_omite_los_eventos_de_animales_que_no_existen(self):
        with self.app.app_context():
            get_db().animales.delete_one({"identificacion": "125"})
        # sin el animal 125 se omiten sus 2 eventos y se crean los otros 3
        with self.app.app_context():
            self.assertEqual(crear_eventos_ejemplo(get_db()), 3)


if __name__ == "__main__":
    unittest.main()
