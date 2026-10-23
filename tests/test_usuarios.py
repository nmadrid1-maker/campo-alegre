"""Pruebas de Gestión de usuarios (RF-07)."""
import unittest

from werkzeug.security import check_password_hash

from base import CLAVE_ADMIN, CLAVE_EMPLEADO, BaseTest
from campo_alegre.db import get_db


class UsuariosBase(BaseTest):
    def usuario(self, nombre):
        with self.app.app_context():
            return get_db().usuarios.find_one({"usuario": nombre})

    def datos(self, **c):
        d = {"usuario": "maria", "nombre": "María Pérez", "rol": "Empleado",
             "clave": "clave-segura-1", "confirmacion": "clave-segura-1"}
        d.update(c)
        return d

    def actividad(self):
        with self.app.app_context():
            return [a["texto"] for a in get_db().actividad.find()]


class PruebasCrear(UsuariosBase):
    def setUp(self):
        super().setUp()
        self.entrar()

    def test_crea_usuario_que_puede_entrar(self):
        r = self.post("/usuarios/nuevo", self.datos(usuario="  María.P  ".replace("í", "i")))
        self.assertEqual(r.status_code, 302)
        u = self.usuario("maria.p")
        self.assertTrue(u["activo"])
        self.assertEqual(u["rol"], "Empleado")
        self.assertNotEqual(u["password_hash"], "clave-segura-1")
        self.assertTrue(check_password_hash(u["password_hash"], "clave-segura-1"))
        self.post("/logout")
        r = self.entrar("maria.p", "clave-segura-1")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get("/inicio").status_code, 200)

    def test_usuario_en_mayusculas_se_normaliza(self):
        self.post("/usuarios/nuevo", self.datos(usuario="PEDRO"))
        self.assertIsNotNone(self.usuario("pedro"))

    def test_usuario_duplicado(self):
        r = self.post("/usuarios/nuevo", self.datos(usuario="admin"))
        self.assertIn("ya existe", r.get_data(as_text=True))
        r = self.post("/usuarios/nuevo", self.datos(usuario="ADMIN"))
        self.assertIn("ya existe", r.get_data(as_text=True))

    def test_validaciones(self):
        casos = [
            (self.datos(usuario="ab"), "entre 3 y 30"),
            (self.datos(usuario="a" * 31), "entre 3 y 30"),
            (self.datos(usuario="con espacio"), "entre 3 y 30"),
            (self.datos(usuario="ñandú"), "entre 3 y 30"),
            (self.datos(nombre=""), "nombre completo"),
            (self.datos(nombre="x" * 61), "hasta 60"),
            (self.datos(rol="Superjefe"), "Seleccione el rol"),
            (self.datos(clave="corta1", confirmacion="corta1"), "al menos 8"),
            (self.datos(clave="a" * 129, confirmacion="a" * 129), "hasta 128"),
            (self.datos(confirmacion="otra-distinta-1"), "no coinciden"),
        ]
        for datos, texto in casos:
            r = self.post("/usuarios/nuevo", datos)
            self.assertEqual(r.status_code, 200, texto)
            self.assertIn(texto, r.get_data(as_text=True))
        self.assertIsNone(self.usuario("maria"))

    def test_actividad_no_incluye_la_clave(self):
        self.post("/usuarios/nuevo", self.datos())
        textos = " ".join(self.actividad())
        self.assertIn("Se creó el usuario maria", textos)
        self.assertNotIn("clave-segura-1", textos)


class PruebasEditar(UsuariosBase):
    def setUp(self):
        super().setUp()
        self.entrar()

    def test_editar_nombre_y_rol(self):
        self.post("/usuarios/empleado/editar", {"nombre": "Juan Campo", "rol": "Administrador"})
        u = self.usuario("empleado")
        self.assertEqual((u["nombre"], u["rol"]), ("Juan Campo", "Administrador"))

    def test_no_cambia_su_propio_rol(self):
        self.post("/usuarios/admin/editar", {"nombre": "Jefe", "rol": "Empleado"})
        u = self.usuario("admin")
        self.assertEqual(u["rol"], "Administrador")
        self.assertEqual(u["nombre"], "Jefe")

    def test_el_usuario_no_se_puede_cambiar(self):
        self.post("/usuarios/empleado/editar", {"usuario": "otro", "nombre": "X", "rol": "Empleado"})
        self.assertIsNotNone(self.usuario("empleado"))
        self.assertIsNone(self.usuario("otro"))

    def test_validaciones_y_usuario_inexistente(self):
        r = self.post("/usuarios/empleado/editar", {"nombre": "", "rol": "Empleado"})
        self.assertIn("nombre completo", r.get_data(as_text=True))
        self.assertEqual(self.client.get("/usuarios/nadie/editar").status_code, 302)

    def test_cambio_de_rol_aplica_en_la_sesion_abierta(self):
        # El empleado entra, el admin lo promueve, y su sesión ya lo refleja.
        otro = self.app.test_client()
        with otro.session_transaction() as s:
            s["_csrf"] = "t"
        otro.post("/login", data={"usuario": "empleado", "clave": CLAVE_EMPLEADO, "_csrf": "t"})
        self.assertEqual(otro.get("/usuarios/").status_code, 302)
        self.post("/usuarios/empleado/editar", {"nombre": "Empleado", "rol": "Administrador"})
        self.assertEqual(otro.get("/usuarios/").status_code, 200)


class PruebasClaveYEstado(UsuariosBase):
    def setUp(self):
        super().setUp()
        self.entrar()

    def test_restablecer_clave(self):
        r = self.post("/usuarios/empleado/clave", {"clave": "nueva-clave-99", "confirmacion": "nueva-clave-99"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(check_password_hash(self.usuario("empleado")["password_hash"], "nueva-clave-99"))
        self.assertNotIn("nueva-clave-99", " ".join(self.actividad()))
        self.post("/logout")
        self.assertEqual(self.entrar("empleado", CLAVE_EMPLEADO).status_code, 200)  # la vieja ya no sirve
        self.assertEqual(self.entrar("empleado", "nueva-clave-99").status_code, 302)

    def test_clave_invalida_no_cambia(self):
        antes = self.usuario("empleado")["password_hash"]
        for c, conf in (("corta", "corta"), ("larga-clave-1", "distinta-clave-1")):
            r = self.post("/usuarios/empleado/clave", {"clave": c, "confirmacion": conf})
            self.assertEqual(r.status_code, 200)
        self.assertEqual(self.usuario("empleado")["password_hash"], antes)

    def test_desactivar_impide_entrar_y_cierra_sesion(self):
        otro = self.app.test_client()
        with otro.session_transaction() as s:
            s["_csrf"] = "t"
        otro.post("/login", data={"usuario": "empleado", "clave": CLAVE_EMPLEADO, "_csrf": "t"})
        self.assertEqual(otro.get("/inicio").status_code, 200)

        self.post("/usuarios/empleado/estado")
        self.assertFalse(self.usuario("empleado")["activo"])
        r = otro.get("/inicio")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])
        self.assertIn("ya no está activo", otro.get("/login").get_data(as_text=True))
        # y no puede volver a entrar
        with otro.session_transaction() as s:
            s["_csrf"] = "t"
        otro.post("/login", data={"usuario": "empleado", "clave": CLAVE_EMPLEADO, "_csrf": "t"})
        self.assertEqual(otro.get("/inicio").status_code, 302)

    def test_reactivar(self):
        self.post("/usuarios/empleado/estado")
        self.post("/usuarios/empleado/estado")
        self.assertTrue(self.usuario("empleado")["activo"])

    def test_no_puede_desactivarse_a_si_mismo(self):
        self.post("/usuarios/admin/estado")
        self.assertTrue(self.usuario("admin")["activo"])

    def test_usuario_eliminado_de_la_base_pierde_la_sesion(self):
        with self.app.app_context():
            get_db().usuarios.delete_one({"usuario": "admin"})
        self.assertEqual(self.client.get("/inicio").status_code, 302)

    def test_lista_muestra_estados(self):
        self.post("/usuarios/empleado/estado")
        html = self.client.get("/usuarios/").get_data(as_text=True)
        self.assertIn("Inactivo", html)
        self.assertIn("(tú)", html)


class PruebasPermisos(UsuariosBase):
    def test_empleado_no_entra(self):
        self.entrar("empleado", CLAVE_EMPLEADO)
        for ruta in ("/usuarios/", "/usuarios/nuevo", "/usuarios/admin/editar", "/usuarios/admin/clave"):
            self.assertEqual(self.client.get(ruta).status_code, 302, ruta)
        self.post("/usuarios/nuevo", self.datos())
        self.post("/usuarios/admin/estado")
        self.post("/usuarios/admin/clave", {"clave": "hackeado-123", "confirmacion": "hackeado-123"})
        self.assertIsNone(self.usuario("maria"))
        self.assertTrue(self.usuario("admin")["activo"])
        self.assertTrue(check_password_hash(self.usuario("admin")["password_hash"], CLAVE_ADMIN))

    def test_sin_sesion(self):
        self.assertEqual(self.client.get("/usuarios/").status_code, 302)

    def test_sin_csrf(self):
        self.entrar()
        self.assertEqual(self.client.post("/usuarios/nuevo", data=self.datos()).status_code, 400)

    def test_menu_del_empleado_sin_usuarios(self):
        self.entrar("empleado", CLAVE_EMPLEADO)
        self.assertNotIn(">Usuarios<", self.client.get("/inicio").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
