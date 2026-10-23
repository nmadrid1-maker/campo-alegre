import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "clave-solo-para-desarrollo")
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB = os.environ.get("MONGO_DB", "campo_alegre")

    # Solo las pruebas automáticas ponen esto en True (base simulada en memoria).
    USE_MOCK_DB = False

    # Copias de seguridad
    RESPALDOS_DIR = os.environ.get("RESPALDOS_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "respaldos"))
    RESPALDO_AUTOMATICO = True
    RESPALDOS_CONSERVAR_AUTO = 14      # copias automáticas que se guardan (una por día)
    RESPALDOS_CONSERVAR_MANUAL = 30
    MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # tamaño máximo de un archivo subido

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
