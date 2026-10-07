from datetime import datetime

from flask import current_app
from pymongo import ASCENDING, MongoClient
from pymongo.errors import ServerSelectionTimeoutError


def init_db(app):
    """Crea el cliente de MongoDB y los índices únicos."""
    if app.config["USE_MOCK_DB"]:
        import mongomock  # solo se instala en el entorno de pruebas

        client = mongomock.MongoClient()
    else:
        client = MongoClient(app.config["MONGO_URI"], serverSelectionTimeoutMS=3000)

    app.extensions["mongo_client"] = client
    db = client[app.config["MONGO_DB"]]

    try:
        db.usuarios.create_index([("usuario", ASCENDING)], unique=True)
        db.animales.create_index([("identificacion", ASCENDING)], unique=True)
    except ServerSelectionTimeoutError as exc:
        raise RuntimeError(
            "No se pudo conectar a MongoDB en "
            + app.config["MONGO_URI"]
            + ". Revisa que el servicio MongoDB Server esté iniciado "
            "(Windows + R, services.msc) y que MONGO_URI en tu archivo .env sea correcta."
        ) from exc


def get_db():
    client = current_app.extensions["mongo_client"]
    return client[current_app.config["MONGO_DB"]]


def registrar_actividad(texto, usuario=None):
    """Guarda una línea en el registro de actividades recientes del panel."""
    get_db().actividad.insert_one(
        {"fecha": datetime.now(), "usuario": usuario, "texto": texto}
    )
