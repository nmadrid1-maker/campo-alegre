"""Pruebas automáticas con una base MongoDB simulada en memoria (mongomock).

Ejecutar:  py -m unittest discover -s tests -v
"""
import unittest

from campo_alegre import create_app
from campo_alegre.db import get_db
from campo_alegre.semilla import crear_animales_ejemplo, crear_usuarios

CLAVE_ADMIN = "clave-admin-de-prueba"
CLAVE_EMPLEADO = "clave-empleado-de-prueba"


class BaseTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"USE_MOCK_DB": True, "TESTING": True, "SECRET_KEY": "prueba"})
        with self.app.app_context():
            crear_usuarios(get_db(), CLAVE_ADMIN, CLAVE_EMPLEADO)
        self.client = self.app.test_client()

    def post(self, url, datos=None, token="tok"):
        """POST con el token CSRF válido en la sesión."""
        with self.client.session_transaction() as s:
            s["_csrf"] = token
        datos = dict(datos or {})
        datos["_csrf"] = token
        return self.client.post(url, data=datos)

    def entrar(self, usuario="admin", clave=CLAVE_ADMIN):
        return self.post("/login", {"usuario": usuario, "clave": clave})

    def animal_valido(self, **cambios):
        datos = {
            "identificacion": "301",
            "nombre": "Prueba",
            "sexo": "Hembra",
            "categoria": "Vaca",
            "fecha_nacimiento": "2022-05-10",
            "fecha_ingreso": "2022-06-01",
            "procedencia": "Compra",
            "estado": "Activa",
            "observaciones": "",
        }
        datos.update(cambios)
        return datos

    def contar(self, filtro=None):
        with self.app.app_context():
            return get_db().animales.count_documents(filtro or {})


class PruebasAutenticacion(BaseTest):
    def test_sin_sesion_redirige_al_login(self):
        r = self.client.get("/inicio")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])

    def test_login_correcto(self):
        r = self.entrar()
        self.assertEqual(r.status_code, 302)
        self.assertIn("/inicio", r.headers["Location"])
        self.assertEqual(self.client.get("/inicio").status_code, 200)

    def test_login_con_clave_incorrecta(self):
        r = self.entrar(clave="otra")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Usuario o contraseña incorrectos", r.get_data(as_text=True))

    def test_post_sin_token_csrf_es_rechazado(self):
        r = self.client.post("/login", data={"usuario": "admin", "clave": CLAVE_ADMIN})
        self.assertEqual(r.status_code, 400)

    def test_cerrar_sesion(self):
        self.entrar()
        self.post("/logout")
        r = self.client.get("/inicio")
        self.assertEqual(r.status_code, 302)

    def test_clave_se_guarda_con_hash(self):
        with self.app.app_context():
            u = get_db().usuarios.find_one({"usuario": "admin"})
        self.assertNotEqual(u["password_hash"], CLAVE_ADMIN)
        self.assertNotIn(CLAVE_ADMIN, u["password_hash"])


class PruebasRoles(BaseTest):
    def test_empleado_no_entra_a_ganado(self):
        self.entrar("empleado", CLAVE_EMPLEADO)
        r = self.client.get("/ganado/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/inicio", r.headers["Location"])

    def test_empleado_no_puede_crear_animales(self):
        self.entrar("empleado", CLAVE_EMPLEADO)
        self.post("/ganado/nuevo", self.animal_valido())
        self.assertEqual(self.contar(), 0)

    def test_empleado_ve_control_sanitario_pero_no_informes(self):
        self.entrar("empleado", CLAVE_EMPLEADO)
        self.assertEqual(self.client.get("/sanitario").status_code, 200)
        self.assertEqual(self.client.get("/informes").status_code, 302)

    def test_menu_del_empleado_no_muestra_ganado(self):
        self.entrar("empleado", CLAVE_EMPLEADO)
        html = self.client.get("/inicio").get_data(as_text=True)
        self.assertNotIn('href="/ganado/"', html)
        self.assertIn('href="/sanitario"', html)

    def test_admin_ve_todo(self):
        self.entrar()
        for ruta in ("/inicio", "/ganado/", "/sanitario", "/reproductivo", "/productivo",
                     "/informes", "/usuarios", "/configuracion"):
            self.assertEqual(self.client.get(ruta).status_code, 200, ruta)


class PruebasGanado(BaseTest):
    def setUp(self):
        super().setUp()
        self.entrar()

    def test_crear_animal(self):
        r = self.post("/ganado/nuevo", self.animal_valido())
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.contar({"identificacion": "301"}), 1)
        ficha = self.client.get("/ganado/301")
        self.assertEqual(ficha.status_code, 200)
        self.assertIn("Prueba", ficha.get_data(as_text=True))

    def test_identificacion_duplicada(self):
        self.post("/ganado/nuevo", self.animal_valido())
        r = self.post("/ganado/nuevo", self.animal_valido(nombre="Otra"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("Ya existe un animal con esa identificación", r.get_data(as_text=True))
        self.assertEqual(self.contar(), 1)

    def test_campos_obligatorios(self):
        r = self.post("/ganado/nuevo", {})
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        for mensaje in ("Escriba la identificación", "Seleccione el sexo",
                        "Seleccione la categoría", "Indique la fecha de nacimiento",
                        "Indique la fecha de ingreso"):
            self.assertIn(mensaje, html)
        self.assertEqual(self.contar(), 0)

    def test_categoria_debe_coincidir_con_el_sexo(self):
        r = self.post("/ganado/nuevo", self.animal_valido(sexo="Macho", categoria="Vaca"))
        self.assertIn("no corresponde a un animal de sexo Macho", r.get_data(as_text=True))
        self.assertEqual(self.contar(), 0)

    def test_fechas_invalidas(self):
        r = self.post("/ganado/nuevo", self.animal_valido(fecha_nacimiento="2999-01-01"))
        self.assertIn("no puede ser futura", r.get_data(as_text=True))
        r = self.post("/ganado/nuevo", self.animal_valido(fecha_ingreso="2020-01-01"))
        self.assertIn("anterior al nacimiento", r.get_data(as_text=True))
        self.assertEqual(self.contar(), 0)

    def test_identificacion_con_caracteres_raros(self):
        r = self.post("/ganado/nuevo", self.animal_valido(identificacion="12 5/<x>"))
        self.assertIn("solo letras, números o guion", r.get_data(as_text=True))
        self.assertEqual(self.contar(), 0)

    def test_editar_animal_y_no_cambia_la_identificacion(self):
        self.post("/ganado/nuevo", self.animal_valido())
        r = self.post("/ganado/301/editar", self.animal_valido(identificacion="999", nombre="Cambiada", estado="Vendido"))
        self.assertEqual(r.status_code, 302)
        with self.app.app_context():
            a = get_db().animales.find_one({"identificacion": "301"})
            self.assertEqual(a["nombre"], "Cambiada")
            self.assertEqual(a["estado"], "Vendido")
            self.assertIsNone(get_db().animales.find_one({"identificacion": "999"}))

    def test_eliminar_animal(self):
        self.post("/ganado/nuevo", self.animal_valido())
        r = self.post("/ganado/301/eliminar")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.contar(), 0)
        self.assertEqual(self.client.get("/ganado/301").status_code, 404)

    def test_animal_inexistente_da_404(self):
        self.assertEqual(self.client.get("/ganado/no-existe").status_code, 404)
        self.assertEqual(self.client.get("/ganado/no-existe/editar").status_code, 404)

    def test_busqueda_y_paginacion(self):
        with self.app.app_context():
            crear_animales_ejemplo(get_db())  # 8 animales, 6 por página
        pagina1 = self.client.get("/ganado/").get_data(as_text=True)
        self.assertIn("Mostrando 1 a 6 de 8 animales", pagina1)
        pagina2 = self.client.get("/ganado/?page=2").get_data(as_text=True)
        self.assertIn("Mostrando 7 a 8 de 8 animales", pagina2)
        busqueda = self.client.get("/ganado/?q=luna").get_data(as_text=True)
        self.assertIn("Luna", busqueda)
        self.assertNotIn("Trueno", busqueda)
        vacio = self.client.get("/ganado/?q=zzz").get_data(as_text=True)
        self.assertIn("Ningún animal coincide", vacio)

    def test_busqueda_no_interpreta_regex(self):
        with self.app.app_context():
            crear_animales_ejemplo(get_db())
        r = self.client.get("/ganado/?q=.*")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Ningún animal coincide", r.get_data(as_text=True))

    def test_pagina_fuera_de_rango_no_falla(self):
        self.assertEqual(self.client.get("/ganado/?page=999").status_code, 200)
        self.assertEqual(self.client.get("/ganado/?page=abc").status_code, 200)

    def test_actividad_reciente_en_el_inicio(self):
        self.post("/ganado/nuevo", self.animal_valido())
        html = self.client.get("/inicio").get_data(as_text=True)
        self.assertIn("Se registró un nuevo animal (ID: 301)", html)

    def test_texto_con_html_se_escapa(self):
        self.post("/ganado/nuevo", self.animal_valido(nombre="<script>alert(1)</script>"))
        html = self.client.get("/ganado/301").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)


if __name__ == "__main__":
    unittest.main()
