"""Base común de las pruebas: crea una aplicación con base MongoDB simulada (mongomock)."""
import shutil
import tempfile
import unittest

from campo_alegre import create_app
from campo_alegre.db import get_db
from campo_alegre.semilla import crear_usuarios

CLAVE_ADMIN = "clave-admin-de-prueba"
CLAVE_EMPLEADO = "clave-empleado-de-prueba"


class BaseTest(unittest.TestCase):
    def setUp(self):
        self.dir_respaldos = tempfile.mkdtemp(prefix="respaldos_prueba_")
        self.addCleanup(shutil.rmtree, self.dir_respaldos, True)
        self.app = create_app({"USE_MOCK_DB": True, "TESTING": True, "SECRET_KEY": "prueba",
                               "RESPALDOS_DIR": self.dir_respaldos, "RESPALDO_AUTOMATICO": False})
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
