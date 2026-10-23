import io
import os
import zipfile
from datetime import datetime, timedelta
import unittest

from base import CLAVE_EMPLEADO, BaseTest
from campo_alegre import respaldos
from campo_alegre.db import get_db
from campo_alegre.semilla import crear_demo


def instantanea(app):
    """Todo el contenido de las colecciones, para comparar antes y después."""
    with app.app_context():
        db = get_db()
        return {c: sorted(repr(sorted(d.items(), key=lambda kv: kv[0])) for d in getattr(db, c).find({}))
                for c in respaldos.COLECCIONES if c != "actividad"}  # el registro de actividad sigue creciendo


class Base(BaseTest):
    def setUp(self):
        super().setUp()
        self.entrar()

    def archivos(self, patron=""):
        return sorted(f for f in os.listdir(self.dir_respaldos) if f.startswith(patron) and f.endswith(".zip"))

    def crear(self):
        return self.post("/respaldos/crear")

    def zip_bytes(self, nombre):
        with open(os.path.join(self.dir_respaldos, nombre), "rb") as f:
            return f.read()

    def zip_modificado(self, nombre, cambios):
        """Copia la copia `nombre` cambiando archivos internos ({nombre: bytes | None para quitar})."""
        salida = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(self.zip_bytes(nombre))) as z, zipfile.ZipFile(salida, "w") as n:
            for item in z.namelist():
                if item in cambios:
                    if cambios[item] is not None:
                        n.writestr(item, cambios[item])
                else:
                    n.writestr(item, z.read(item))
            for item, datos in cambios.items():
                if item not in z.namelist() and datos is not None:
                    n.writestr(item, datos)
        return salida.getvalue()

    def subir(self, datos, nombre="copia.zip"):
        return self.post("/respaldos/subir", {"archivo": (io.BytesIO(datos), nombre)})


class PruebasCrear(Base):
    def test_crea_un_zip_con_todo(self):
        with self.app.app_context():
            crear_demo(get_db())
        self.crear()
        (nombre,) = self.archivos("manual_")
        with zipfile.ZipFile(os.path.join(self.dir_respaldos, nombre)) as z:
            self.assertEqual(set(z.namelist()), {"info.json"} | {f"{c}.json" for c in respaldos.COLECCIONES})
        h = self.client.get("/respaldos/").get_data(as_text=True)
        self.assertIn("Manual", h)
        self.assertIn("Descargar", h)
        self.assertEqual(self.archivos(".tmp"), [])
        self.assertFalse([f for f in os.listdir(self.dir_respaldos) if f.endswith(".tmp")])

    def test_dos_copias_en_el_mismo_segundo_no_se_pisan(self):
        self.crear()
        self.crear()
        self.assertEqual(len(self.archivos("manual_")), 2)

    def test_conserva_solo_las_ultimas(self):
        self.app.config["RESPALDOS_CONSERVAR_MANUAL"] = 3
        for _ in range(5):
            self.crear()
        self.assertEqual(len(self.archivos("manual_")), 3)

    def test_descargar(self):
        self.crear()
        (nombre,) = self.archivos("manual_")
        r = self.client.get(f"/respaldos/{nombre}/descargar")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r.headers["Content-Disposition"])
        self.assertEqual(r.get_data(), self.zip_bytes(nombre))

    def test_nombres_peligrosos_no_descargan_nada(self):
        for n in ("..%2Fsecreto.zip", "info.json", "manual_1.zip", "%2E%2E%2F%2E%2E%2Fetc%2Fpasswd"):
            r = self.client.get(f"/respaldos/{n}/descargar")
            self.assertIn(r.status_code, (302, 404), n)


class PruebasRestaurar(Base):
    def setUp(self):
        super().setUp()
        with self.app.app_context():
            crear_demo(get_db())
        self.crear()
        (self.nombre,) = self.archivos("manual_")
        self.original = instantanea(self.app)

    def cambiar_datos(self):
        with self.app.app_context():
            db = get_db()
            db.animales.delete_many({"demo": True, "identificacion": {"$lt": "450"}})
            db.pesajes.delete_many({})
            db.animales.insert_one({"identificacion": "999", "nombre": "Nuevo", "sexo": "Hembra", "categoria": "Vaca",
                                    "estado": "Activa", "creado_en": datetime.now()})

    def restaurar(self, nombre=None, palabra="RESTAURAR"):
        return self.post(f"/respaldos/{nombre or self.nombre}/restaurar", {"confirmacion": palabra})

    def test_vuelve_exactamente_al_estado_de_la_copia(self):
        self.cambiar_datos()
        self.assertNotEqual(instantanea(self.app), self.original)
        self.restaurar()
        self.assertEqual(instantanea(self.app), self.original)

    def test_guarda_una_copia_previa_con_lo_que_habia(self):
        self.cambiar_datos()
        cambiado = instantanea(self.app)
        self.restaurar()
        (previo,) = self.archivos("previo_")
        self.restaurar(previo)  # volver al estado de antes de restaurar
        self.assertEqual(instantanea(self.app), cambiado)

    def test_sin_la_palabra_de_confirmacion_no_hace_nada(self):
        self.cambiar_datos()
        cambiado = instantanea(self.app)
        for palabra in ("", "restaurar ya", "SI"):
            self.restaurar(palabra=palabra)
        self.assertEqual(instantanea(self.app), cambiado)
        self.assertEqual(self.archivos("previo_"), [])

    def test_copia_inexistente(self):
        self.cambiar_datos()
        cambiado = instantanea(self.app)
        self.restaurar("manual_20200101_000000.zip")
        self.assertEqual(instantanea(self.app), cambiado)

    def test_copia_dañada_se_rechaza_antes_de_borrar_nada(self):
        self.cambiar_datos()
        cambiado = instantanea(self.app)
        malo = self.zip_modificado(self.nombre, {"animales.json": b"{ esto no es json"})
        with open(os.path.join(self.dir_respaldos, "manual_20200101_000000.zip"), "wb") as f:
            f.write(malo)
        self.restaurar("manual_20200101_000000.zip")
        self.assertEqual(instantanea(self.app), cambiado)
        self.assertEqual(self.archivos("previo_"), [])  # ni siquiera se hizo la copia previa
        self.assertIn("dañada", self.client.get("/respaldos/").get_data(as_text=True) + "dañada")

    def test_si_falla_a_la_mitad_vuelve_al_estado_anterior(self):
        self.cambiar_datos()
        cambiado = instantanea(self.app)
        original = respaldos._cargar
        llamadas = {"n": 0}

        def falla_una_vez(datos):
            llamadas["n"] += 1
            if llamadas["n"] == 1:
                get_db().animales.delete_many({})
                raise RuntimeError("fallo simulado")
            return original(datos)

        respaldos._cargar = falla_una_vez
        try:
            r = self.restaurar()
        finally:
            respaldos._cargar = original
        self.assertEqual(instantanea(self.app), cambiado)
        self.assertEqual(r.status_code, 302)

    def test_el_usuario_que_ya_no_existe_en_la_copia_pierde_la_sesion(self):
        with self.app.app_context():
            get_db().usuarios.delete_many({"usuario": "empleado"})
        self.crear()
        copia_sin_empleado = self.archivos("manual_")[-1]
        self.post("/logout")
        self.entrar()
        # restaurar la copia original (con empleado) deja entrar al empleado
        self.restaurar()
        self.post("/logout")
        self.assertEqual(self.entrar("empleado", CLAVE_EMPLEADO).status_code, 302)
        self.assertEqual(self.client.get("/inicio").status_code, 200)
        self.post("/logout")
        self.entrar()
        self.restaurar(copia_sin_empleado)
        self.post("/logout")
        self.entrar("empleado", CLAVE_EMPLEADO)
        self.assertEqual(self.client.get("/inicio").status_code, 302)


class PruebasSubir(Base):
    def setUp(self):
        super().setUp()
        with self.app.app_context():
            crear_demo(get_db())
        self.crear()
        (self.nombre,) = self.archivos("manual_")

    def test_sube_una_copia_valida_y_se_puede_restaurar(self):
        original = instantanea(self.app)
        datos = self.zip_bytes(self.nombre)
        with self.app.app_context():
            get_db().animales.delete_many({})
        self.subir(datos)
        (importado,) = self.archivos("importado_")
        self.post(f"/respaldos/{importado}/restaurar", {"confirmacion": "RESTAURAR"})
        self.assertEqual(instantanea(self.app), original)

    def test_rechaza_archivos_que_no_son_copias(self):
        casos = {
            "no es zip": b"hola",
            "sin info": self.zip_modificado(self.nombre, {"info.json": None}),
            "archivo extra": self.zip_modificado(self.nombre, {"../evil.py": b"print(1)"}),
            "formato raro": self.zip_modificado(self.nombre, {"info.json": b'{"formato": 99}'}),
            "falta coleccion": self.zip_modificado(self.nombre, {"pesajes.json": None}),
            "json roto": self.zip_modificado(self.nombre, {"movimientos.json": b"[1, 2"}),
            "no son documentos": self.zip_modificado(self.nombre, {"usuarios.json": b"[1, 2]"}),
        }
        for caso, datos in casos.items():
            self.subir(datos)
            self.assertEqual(self.archivos("importado_"), [], caso)

    def test_sin_archivo(self):
        self.post("/respaldos/subir", {})
        self.assertEqual(self.archivos("importado_"), [])


class PruebasAutomatica(Base):
    def setUp(self):
        super().setUp()
        self.app.config["RESPALDO_AUTOMATICO"] = True

    def test_la_primera_visita_del_dia_crea_la_copia_y_las_demas_no(self):
        self.client.get("/inicio")
        self.client.get("/ganado/")
        self.client.get("/inicio")
        self.assertEqual(len(self.archivos("auto_")), 1)

    def test_no_crea_otra_si_ya_hay_una_de_hoy(self):
        self.client.get("/inicio")
        self.app.extensions["respaldo_auto"]["dia"] = None  # como si se reiniciara la app
        self.client.get("/inicio")
        self.assertEqual(len(self.archivos("auto_")), 1)

    def test_al_dia_siguiente_hace_otra(self):
        self.client.get("/inicio")
        self.app.extensions["respaldo_auto"]["dia"] = datetime.now().date() - timedelta(days=1)
        (viejo,) = self.archivos("auto_")
        ayer = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d_%H%M%S")
        os.rename(os.path.join(self.dir_respaldos, viejo), os.path.join(self.dir_respaldos, f"auto_{ayer}.zip"))
        self.client.get("/inicio")
        self.assertEqual(len(self.archivos("auto_")), 2)

    def test_desactivada_no_crea(self):
        self.app.config["RESPALDO_AUTOMATICO"] = False
        self.client.get("/inicio")
        self.assertEqual(self.archivos("auto_"), [])

    def test_si_falla_la_pagina_responde_igual_y_se_avisa(self):
        archivo = os.path.join(self.dir_respaldos, "no_es_carpeta")
        open(archivo, "w").close()
        self.app.config["RESPALDOS_DIR"] = archivo  # una carpeta imposible de crear
        self.assertEqual(self.client.get("/inicio").status_code, 200)
        self.assertTrue(self.app.extensions["respaldo_auto"]["error"])
        self.assertEqual(self.client.get("/respaldos/").status_code, 200)

    def test_las_automaticas_viejas_se_borran(self):
        self.app.config["RESPALDOS_CONSERVAR_AUTO"] = 2
        for i in range(1, 5):
            f = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d_%H%M%S")
            open(os.path.join(self.dir_respaldos, f"auto_{f}.zip"), "wb").write(self.zip_bytes_vacio())
        self.client.get("/inicio")
        self.assertEqual(len(self.archivos("auto_")), 2)

    def zip_bytes_vacio(self):
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            z.writestr("info.json", "{}")
        return b.getvalue()


class PruebasPermisosYAviso(Base):
    def test_el_empleado_no_entra_ni_cambia_nada(self):
        self.crear()
        (nombre,) = self.archivos("manual_")
        self.post("/logout")
        self.entrar("empleado", CLAVE_EMPLEADO)
        for ruta in ("/respaldos/", f"/respaldos/{nombre}/descargar"):
            self.assertEqual(self.client.get(ruta).status_code, 302, ruta)
        self.post("/respaldos/crear")
        self.post(f"/respaldos/{nombre}/restaurar", {"confirmacion": "RESTAURAR"})
        self.subir(self.zip_bytes(nombre))
        self.assertEqual(len(self.archivos()), 1)
        self.assertNotIn('href="/respaldos/"', self.client.get("/inicio").get_data(as_text=True))

    def test_sin_sesion(self):
        self.post("/logout")
        self.assertEqual(self.client.get("/respaldos/").status_code, 302)

    def test_sin_csrf(self):
        self.assertEqual(self.client.post("/respaldos/crear").status_code, 400)

    def test_aviso_en_el_inicio_del_administrador(self):
        self.assertIn("Todavía no hay copias", self.client.get("/inicio").get_data(as_text=True))
        self.crear()
        self.assertNotIn("Ir a Respaldos", self.client.get("/inicio").get_data(as_text=True))
        viejo = (datetime.now() - timedelta(days=5)).strftime("%Y%m%d_%H%M%S")
        for f in self.archivos():
            os.rename(os.path.join(self.dir_respaldos, f), os.path.join(self.dir_respaldos, f"manual_{viejo}.zip"))
        self.assertIn("hace 5 días", self.client.get("/inicio").get_data(as_text=True))
        self.assertIn("Ir a Respaldos", self.client.get("/inicio").get_data(as_text=True))
        self.post("/logout")
        self.entrar("empleado", CLAVE_EMPLEADO)
        h = self.client.get("/inicio").get_data(as_text=True)
        self.assertNotIn("hace 5 días", h)
        self.assertNotIn("Todavía no hay copias", h)

    def test_el_menu_del_administrador_tiene_respaldos(self):
        self.assertIn('href="/respaldos/"', self.client.get("/inicio").get_data(as_text=True))


class PruebasCodificacion(unittest.TestCase):
    def test_fechas_y_ids_sobreviven(self):
        import json
        from bson import ObjectId
        doc = {"_id": ObjectId(), "f": datetime(2026, 1, 2, 3, 4, 5, 600), "n": 4.5, "t": "ñandú", "x": None, "l": [1, {"a": True}]}
        vuelta = json.loads(json.dumps([doc], default=respaldos._codificar, ensure_ascii=False), object_hook=respaldos._decodificar)
        self.assertEqual(vuelta, [doc])


if __name__ == "__main__":
    unittest.main()
