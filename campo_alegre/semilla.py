"""Datos iniciales: usuarios y algunos animales de ejemplo."""
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from .security import ADMIN, EMPLEADO


def crear_usuarios(db, clave_admin, clave_empleado):
    usuarios = [
        {"usuario": "admin", "nombre": "Administrador", "rol": ADMIN, "clave": clave_admin},
        {"usuario": "empleado", "nombre": "Empleado", "rol": EMPLEADO, "clave": clave_empleado},
    ]
    creados = []
    for u in usuarios:
        if db.usuarios.find_one({"usuario": u["usuario"]}):
            continue
        db.usuarios.insert_one(
            {
                "usuario": u["usuario"],
                "nombre": u["nombre"],
                "rol": u["rol"],
                "password_hash": generate_password_hash(u["clave"]),
                "activo": True,
                "creado_en": datetime.now(),
            }
        )
        creados.append(u["usuario"])
    return creados


def _f(texto):
    return datetime.strptime(texto, "%d/%m/%Y")


EJEMPLOS = [
    ("125", "Luna", "Hembra", "Vaca", "Activa", "12/04/2023", "15/04/2023", "Finca Campo Alegre"),
    ("178", "Trueno", "Macho", "Toro", "Activa", "03/08/2021", "10/09/2021", "Compra"),
    ("204", "Estrella", "Hembra", "Novilla", "Activa", "21/01/2024", "21/01/2024", "Finca Campo Alegre"),
    ("221", "Manchas", "Hembra", "Vaca", "Activa", "09/06/2022", "02/07/2022", "Compra"),
    ("236", "Relámpago", "Macho", "Novillo", "Vendido", "14/02/2023", "14/02/2023", "Finca Campo Alegre"),
    ("248", "Nube", "Hembra", "Vaca", "Activa", "30/11/2021", "05/12/2021", "Compra"),
    ("251", "Canela", "Hembra", "Ternera", "Activa", "10/03/2026", "10/03/2026", "Finca Campo Alegre"),
    ("254", "Capitán", "Macho", "Ternero", "Activa", "22/04/2026", "22/04/2026", "Finca Campo Alegre"),
]


def crear_animales_ejemplo(db):
    n = 0
    for ident, nombre, sexo, cat, estado, nac, ing, proc in EJEMPLOS:
        if db.animales.find_one({"identificacion": ident}):
            continue
        ahora = datetime.now()
        db.animales.insert_one(
            {
                "identificacion": ident,
                "nombre": nombre,
                "sexo": sexo,
                "categoria": cat,
                "estado": estado,
                "fecha_nacimiento": _f(nac),
                "fecha_ingreso": _f(ing),
                "procedencia": proc,
                "observaciones": None,
                "creado_en": ahora,
                "actualizado_en": ahora,
            }
        )
        n += 1
    return n


def crear_eventos_ejemplo(db):
    """Algunos eventos sanitarios de ejemplo. Solo si todavía no hay ninguno."""
    if db.eventos_sanitarios.count_documents({}) or not db.animales.count_documents({}):
        return 0
    hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    dias = lambda n: hoy + timedelta(days=n)
    ejemplos = [
        ("125", "Vacunación", "Fiebre aftosa", dias(-60), dias(120), None),
        ("125", "Desparasitación", "Ivermectina", dias(-20), dias(70), "Dosis según peso"),
        ("178", "Vacunación", "Brucelosis", dias(-170), dias(12), None),
        ("204", "Vacunación", "Fiebre aftosa", dias(-150), dias(25), None),
        ("221", "Tratamiento", "Antibiótico (mastitis)", dias(-9), None, "Respondió bien al tratamiento"),
    ]
    n = 0
    for animal, tipo, producto, fecha, proxima, obs in ejemplos:
        if not db.animales.find_one({"identificacion": animal}):
            continue
        db.eventos_sanitarios.insert_one(
            {
                "animal": animal,
                "tipo": tipo,
                "producto": producto,
                "fecha_aplicacion": fecha,
                "proxima_dosis": proxima,
                "observaciones": obs,
                "registrado_por": "admin",
                "creado_en": datetime.now(),
            }
        )
        n += 1
    return n


def _hoy():
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def crear_reproductivos_ejemplo(db):
    """Eventos reproductivos de ejemplo. Solo si todavía no hay ninguno."""
    if db.eventos_reproductivos.count_documents({}) or not db.animales.count_documents({}):
        return 0
    from .reproductivo import GESTACION_DIAS

    hoy = _hoy()
    dias = lambda n: hoy + timedelta(days=n)
    # (animal, tipo, fecha, metodo, reproductor, resultado, cria_sexo, cria_estado, observaciones)
    ejemplos = [
        ("125", "Servicio", dias(-100), "Inseminación artificial", "Pajilla Brahman 0231", None, None, None, None),
        ("125", "Diagnóstico de preñez", dias(-60), None, None, "Preñada", None, None, "Palpación"),
        ("221", "Servicio", dias(-255), "Monta", "Toro 178", None, None, None, None),
        ("221", "Diagnóstico de preñez", dias(-200), None, None, "Preñada", None, None, None),
        ("248", "Parto", dias(-45), None, None, None, "Hembra", "Viva", "Parto sin complicaciones"),
        ("204", "Servicio", dias(-30), "Monta", "Toro 178", None, None, None, None),
    ]
    n = 0
    for animal, tipo, fecha, metodo, repro, resultado, sexo, estado, obs in ejemplos:
        if not db.animales.find_one({"identificacion": animal}):
            continue
        db.eventos_reproductivos.insert_one(
            {
                "animal": animal,
                "tipo": tipo,
                "fecha": fecha,
                "metodo": metodo,
                "reproductor": repro,
                "parto_probable": fecha + timedelta(days=GESTACION_DIAS) if tipo == "Servicio" else None,
                "resultado": resultado,
                "cria_sexo": sexo,
                "cria_estado": estado,
                "observaciones": obs,
                "registrado_por": "admin",
                "creado_en": datetime.now(),
            }
        )
        n += 1
    return n


def crear_pesajes_ejemplo(db):
    """Pesajes de ejemplo. Solo si todavía no hay ninguno."""
    if db.pesajes.count_documents({}) or not db.animales.count_documents({}):
        return 0
    hoy = _hoy()
    dias = lambda n: hoy + timedelta(days=n)
    ejemplos = [
        ("125", dias(-90), 430.0), ("125", dias(-45), 448.5), ("125", dias(-5), 462.0),
        ("178", dias(-60), 780.0), ("178", dias(-10), 795.0),
        ("204", dias(-75), 310.0), ("204", dias(-20), 338.5),
    ]
    n = 0
    for animal, fecha, peso in ejemplos:
        if not db.animales.find_one({"identificacion": animal}):
            continue
        db.pesajes.insert_one(
            {
                "animal": animal,
                "fecha": fecha,
                "peso_kg": peso,
                "observaciones": None,
                "registrado_por": "admin",
                "creado_en": datetime.now(),
            }
        )
        n += 1
    return n


# Potreros reales de la finca (los entregó el administrador).
POTREROS_FINCA = [
    "Palera", "Perillo", "Domingos", "Llano Chulo", "Olvido", "El Bombal", "Guinea",
    "Encanto 1", "Encanto 2", "Palera 2", "La Vega", "La Vega 2", "Piscina 1", "Piscina 2",
    "Los Moncoros", "El Plan", "Caño Picho", "El Garson", "El Naranjo", "Potrero Largo",
    "La Peña 1", "Peña 2", "El Rastrojo", "El Roto", "El Salto", "Salto 2", "El Huevo",
]


def crear_potreros(db):
    """Carga los potreros de la finca. Solo si todavía no hay ninguno."""
    if db.potreros.count_documents({}):
        return 0
    ahora = datetime.now()
    for nombre in POTREROS_FINCA:
        db.potreros.insert_one(
            {"nombre": nombre, "nombre_lower": nombre.lower(), "activo": True,
             "observaciones": None, "creado_en": ahora, "actualizado_en": ahora}
        )
    return len(POTREROS_FINCA)


def asignar_potreros_ejemplo(db):
    """Pone potrero a algunos animales de ejemplo que aún no tienen. Solo si no hay traslados."""
    if db.traslados.count_documents({}):
        return 0
    hoy = _hoy()
    ejemplos = {"125": "Palera", "178": "El Roto", "204": "La Vega", "221": "Palera",
                "248": "Piscina 1", "251": "Palera", "254": "Palera"}
    n = 0
    for ident, potrero in ejemplos.items():
        animal = db.animales.find_one({"identificacion": ident})
        if not animal or animal.get("potrero") or not db.potreros.find_one({"nombre": potrero}):
            continue
        db.animales.update_one({"identificacion": ident}, {"$set": {"potrero": potrero}})
        db.traslados.insert_one(
            {"animal": ident, "desde": None, "hacia": potrero, "fecha": hoy,
             "registrado_por": "admin", "creado_en": datetime.now()}
        )
        n += 1
    return n


# ---------------------------------------------------------------------------
# Datos de demostración: 3 vacas por potrero con información completa en todos
# los módulos. Todo lo que se crea lleva demo=True para poder borrarlo después
# (py seed_demo.py --borrar) sin tocar los datos reales.
# ---------------------------------------------------------------------------
VACAS_POR_POTRERO = 3
ID_DEMO_INICIAL = 401

NOMBRES_DEMO = [
    "Margarita", "Paloma", "Esperanza", "Canelita", "Princesa", "Lucero", "Azucena", "Pintada", "Morena", "Blanquita",
    "Clavel", "Dalia", "Rosita", "Violeta", "Mariposa", "Gaviota", "Ternura", "Estrellita", "Cielo", "Aurora",
    "Brisa", "Lola", "Chispa", "Pecosa", "Bonita", "Fortuna", "Gitana", "Jazmín", "Lupe", "Mora",
    "Negra", "Oriana", "Pinta", "Reina", "Sultana", "Tulipán", "Urraca", "Vainilla", "Zarina", "Amapola",
    "Bendición", "Camila", "Diana", "Elvira", "Fresa", "Gardenia", "Hortensia", "Isabela", "Juana", "Karina",
    "Lirio", "Magnolia", "Naranja", "Orquídea", "Perla", "Quimera", "Rubí", "Sabrina", "Trigueña", "Uva",
    "Valentina", "Yolanda", "Zafiro", "Alegría", "Barbie", "Cumbia", "Delfina", "Encanto", "Flor", "Gracia",
    "Hada", "Iris", "Joya", "Kenia", "Luna Llena", "Maravilla", "Nieve", "Olivia", "Panela", "Quesada", "Rizada",
]
OBSERVACIONES_ANIMAL = [
    "Buena condición corporal", "Mansa y fácil de manejar", "Buena productora de leche", "Cría con regularidad",
    "Pelaje bien formado", "Se vigila la pezuña derecha", "Buena madre, cuida a su cría", "Ubre en buen estado",
    "Animal tranquilo en la manga", "Buen aplomo y caminadora",
]
OBSERVACIONES_EVENTO = [
    "Sin novedad", "Respondió bien", "Aplicado en la manga", "Se registra en el control del mes",
    "Animal tranquilo durante el manejo", "Revisado por el encargado",
]


def crear_demo(db):
    """Crea VACAS_POR_POTRERO vacas por potrero, con eventos en todos los módulos. Devuelve un resumen."""
    import random

    from .ganado import PROCEDENCIAS
    from .reproductivo import GESTACION_DIAS

    if db.animales.count_documents({"demo": True}):
        # Ya estaba cargada: solo se completa con movimientos si todavía no los tiene.
        return crear_demo_movimientos(db)

    crear_potreros(db)
    rng = random.Random(2026)
    hoy = _hoy()
    ahora = datetime.now()
    dias = lambda n: hoy + timedelta(days=n)
    nombres_potreros = [p["nombre"] for p in db.potreros.find({"activo": True}).sort("nombre_lower", 1)]
    total = len(nombres_potreros) * VACAS_POR_POTRERO
    nombres = (NOMBRES_DEMO * (total // len(NOMBRES_DEMO) + 1))[:total]
    resumen = {"animales": 0, "sanitarios": 0, "reproductivos": 0, "pesajes": 0, "traslados": 0}

    def repro(animal, tipo, fecha, **extra):
        doc = {"animal": animal, "tipo": tipo, "fecha": fecha, "metodo": None, "reproductor": None,
               "parto_probable": None, "resultado": None, "cria_sexo": None, "cria_estado": None,
               "observaciones": rng.choice(OBSERVACIONES_EVENTO), "registrado_por": "admin",
               "creado_en": ahora, "demo": True}
        if tipo == "Servicio":
            doc["parto_probable"] = fecha + timedelta(days=GESTACION_DIAS)
        doc.update(extra)
        db.eventos_reproductivos.insert_one(doc)
        resumen["reproductivos"] += 1

    def servicio(animal, fecha):
        if rng.random() < 0.5:
            repro(animal, "Servicio", fecha, metodo="Monta", reproductor=rng.choice(["Toro 178 Trueno", "Toro Brahman de la finca"]))
        else:
            repro(animal, "Servicio", fecha, metodo="Inseminación artificial",
                  reproductor=rng.choice(["Pajilla Brahman 0231", "Pajilla Gyr 0457", "Pajilla Holstein 0812"]))

    def diagnostico(animal, fecha, resultado):
        repro(animal, "Diagnóstico de preñez", fecha, resultado=resultado,
              observaciones=rng.choice(["Palpación rectal", "Ecografía", "Palpación, tamaño de 2 meses"]))

    def parto(animal, fecha, estado="Viva"):
        repro(animal, "Parto", fecha, cria_sexo=rng.choice(["Hembra", "Macho"]), cria_estado=estado,
              observaciones=rng.choice(["Parto sin complicaciones", "Parto asistido", "Cría con buen peso"]))

    for i in range(total):
        ident = str(ID_DEMO_INICIAL + i)
        if db.animales.find_one({"identificacion": ident}):
            continue
        potrero = nombres_potreros[i // VACAS_POR_POTRERO]
        procedencia = rng.choice(PROCEDENCIAS)
        nacimiento = dias(-rng.randint(4 * 365, 9 * 365))
        ingreso = nacimiento + timedelta(days=rng.randint(0, 60) if procedencia == "Finca Campo Alegre" else rng.randint(200, 1000))
        db.animales.insert_one(
            {"identificacion": ident, "nombre": nombres[i], "sexo": "Hembra", "categoria": "Vaca", "estado": "Activa",
             "fecha_nacimiento": nacimiento, "fecha_ingreso": ingreso, "procedencia": procedencia,
             "potrero": potrero, "observaciones": rng.choice(OBSERVACIONES_ANIMAL),
             "creado_en": ahora, "actualizado_en": ahora, "demo": True}
        )
        resumen["animales"] += 1

        # Traslados: ubicación inicial y, en 4 de cada 10, un cambio reciente hasta el potrero actual.
        def traslado(desde, hacia, fecha):
            db.traslados.insert_one({"animal": ident, "desde": desde, "hacia": hacia, "fecha": fecha,
                                     "registrado_por": "admin", "creado_en": ahora, "demo": True})
            resumen["traslados"] += 1

        if i % 5 in (0, 1):
            anterior = rng.choice([p for p in nombres_potreros if p != potrero])
            traslado(None, anterior, ingreso)
            traslado(anterior, potrero, dias(-rng.randint(5, 120)))
        else:
            traslado(None, potrero, ingreso)

        # Control sanitario
        vacuna = dias(-rng.randint(5, 170))
        eventos = [("Vacunación", "Fiebre aftosa", vacuna, vacuna + timedelta(days=180)),
                   ("Vacunación", "Carbón sintomático", dias(-rng.randint(30, 300)), None)]
        purga = dias(-rng.randint(5, 85))
        eventos.append(("Desparasitación", "Ivermectina", purga, purga + timedelta(days=90)))
        if rng.random() < 0.25:
            eventos.append(("Tratamiento", rng.choice(["Antibiótico (mastitis)", "Antiinflamatorio (cojera)", "Cicatrizante"]),
                            dias(-rng.randint(10, 200)), None))
        if rng.random() < 0.1:
            eventos.append(("Otro", "Revisión de pezuñas", dias(-rng.randint(10, 120)), None))
        for tipo, producto, fecha, proxima in eventos:
            db.eventos_sanitarios.insert_one(
                {"animal": ident, "tipo": tipo, "producto": producto, "fecha_aplicacion": fecha, "proxima_dosis": proxima,
                 "observaciones": rng.choice(OBSERVACIONES_EVENTO), "registrado_por": "admin",
                 "creado_en": ahora, "demo": True})
            resumen["sanitarios"] += 1

        # Control reproductivo: nueve situaciones que se reparten entre las vacas
        esc = i % 9
        if esc == 0:    # parto probable dentro de los próximos 30 días
            s = dias(-rng.randint(255, 270))
            parto(ident, s - timedelta(days=rng.randint(70, 110)))
            servicio(ident, s)
            diagnostico(ident, s + timedelta(days=rng.randint(30, 45)), "Preñada")
        elif esc in (1, 2, 3):  # preñada, parto lejano
            s = dias(-rng.randint(40, 200))
            parto(ident, s - timedelta(days=rng.randint(70, 120)))
            servicio(ident, s)
            diagnostico(ident, s + timedelta(days=35), "Preñada")
        elif esc in (4, 5):     # servicio reciente, aún sin diagnóstico
            s = dias(-rng.randint(3, 28))
            parto(ident, s - timedelta(days=rng.randint(80, 150)))
            servicio(ident, s)
        elif esc == 6:          # salió vacía y se volvió a servir
            s1 = dias(-rng.randint(120, 200))
            servicio(ident, s1)
            diagnostico(ident, s1 + timedelta(days=rng.randint(32, 40)), "Vacía")
            servicio(ident, s1 + timedelta(days=rng.randint(55, 90)))
        elif esc == 7:          # parto reciente
            p = dias(-rng.randint(10, 120))
            s = p - timedelta(days=GESTACION_DIAS)
            servicio(ident, s)
            diagnostico(ident, s + timedelta(days=40), "Preñada")
            parto(ident, p, estado="Viva" if rng.random() < 0.9 else "Muerta")
        else:                   # aborto
            a = dias(-rng.randint(30, 150))
            s = a - timedelta(days=rng.randint(90, 140))
            servicio(ident, s)
            diagnostico(ident, s + timedelta(days=40), "Preñada")
            repro(ident, "Aborto", a, observaciones="Se separó del lote para vigilarla")

        # Control productivo: de 2 a 4 pesajes en el último año
        fechas = sorted(rng.sample(range(10, 360), rng.randint(2, 4)), reverse=True)
        peso = rng.uniform(400, 480)
        for ago in fechas:
            db.pesajes.insert_one(
                {"animal": ident, "fecha": dias(-ago), "peso_kg": round(peso * 2) / 2,
                 "observaciones": rng.choice(["Báscula de la manga", "Pesaje de control", "Pesaje antes de vacunar"]),
                 "registrado_por": "admin", "creado_en": ahora, "demo": True})
            resumen["pesajes"] += 1
            peso = min(peso + rng.uniform(2, 30), 600)
    resumen.update(crear_demo_movimientos(db) or {})
    return resumen


NOVEDADES_DEMO = [
    "Se observó cojera leve en la pata trasera", "Se separó del lote por vigilancia", "Presentó celo, se anotó para servicio",
    "Bajó de peso, se revisa la alimentación", "Se curó una herida pequeña", "Se cambió de lote por pasto escaso",
    "Mostró signos de mastitis, se le dio seguimiento", "Se le colocó el arete nuevo", "Se encontró con la ubre inflamada",
    "Se vio decaída por el calor, se movió a la sombra", "Sin novedad después de la revisión del veterinario",
    "Se le puso hierro para identificarla",
]
SALIDAS_DEMO = [  # (motivo, detalle, estado final)
    ("Venta", "Vendida a un comprador de Barrancabermeja", "Vendido"),
    ("Venta", "Vendido en la feria ganadera de San Vicente", "Vendido"),
    ("Venta", "Vendida a una finca vecina", "Vendido"),
    ("Muerte", "Murió por una picadura de serpiente", "Fallecido"),
    ("Traslado", "Se llevó a la finca de un familiar", "Trasladado"),
    ("Otro", "Se devolvió al dueño anterior", "Retirado"),
]
ID_DEMO_CRIAS = 701
NOMBRES_CRIAS_DEMO = {
    "Hembra": ["Lunita", "Rosita", "Chispa", "Mariposa", "Estrellita", "Azucena", "Fresita", "Dulcinea"],
    "Macho": ["Rayito", "Chocolate", "Tornado", "Camilo", "Bravo", "Pelusa", "Tigre", "Lucero Jr."],
}
NOMBRES_SALIDAS_DEMO = ["Marquesa", "Mono", "Cenicienta", "Rubia", "Colorado", "Gaviota"]
ID_DEMO_SALIDAS = 801


def crear_demo_movimientos(db):
    """Agrega crías (nacimientos), animales que salieron y novedades a los datos de demostración.

    Devuelve un resumen, o None si ya existían movimientos de demostración.
    """
    import random

    if db.movimientos.count_documents({"demo": True}):
        return None
    rng = random.Random(2027)
    hoy = _hoy()
    ahora = datetime.now()
    dias = lambda n: hoy + timedelta(days=n)
    vacas = list(db.animales.find({"demo": True, "identificacion": {"$lt": str(ID_DEMO_CRIAS)}}).sort("identificacion", 1))
    resumen = {"movimientos": 0, "crias": 0, "salidas": 0, "novedades": 0}

    def mov(tipo, animal, fecha, **extra):
        doc = {"tipo": tipo, "animal": animal, "fecha": fecha, "registrado_por": "admin", "creado_en": ahora, "demo": True}
        doc.update(extra)
        db.movimientos.insert_one(doc)
        resumen["movimientos"] += 1

    def traslado_inicial(ident, potrero, fecha):
        db.traslados.insert_one({"animal": ident, "desde": None, "hacia": potrero, "fecha": fecha,
                                 "registrado_por": "admin", "creado_en": ahora, "demo": True})

    def pesaje(ident, fecha, kg, tipo, nota):
        if db.pesajes.find_one({"animal": ident, "fecha": fecha}):
            return  # un solo pesaje por animal y fecha
        db.pesajes.insert_one({"animal": ident, "fecha": fecha, "peso_kg": kg, "tipo_peso": tipo, "observaciones": nota,
                               "registrado_por": "admin", "creado_en": ahora, "demo": True})

    # Entradas: las vacas compradas o donadas entraron a la finca en su fecha de ingreso.
    for v in vacas:
        if v.get("procedencia") in ("Compra", "Donación"):
            mov("Entrada", v["identificacion"], v["fecha_ingreso"], detalle=v["procedencia"])

    # Nacimientos: una cría por cada parto con cría viva del último año (máximo 12).
    partos = list(db.eventos_reproductivos.find(
        {"demo": True, "tipo": "Parto", "cria_estado": "Viva", "fecha": {"$gte": dias(-365)}}).sort("fecha", -1))[:12]
    por_ident = {v["identificacion"]: v for v in vacas}
    for k, pa in enumerate(partos):
        madre = por_ident.get(pa["animal"])
        if not madre:
            continue
        sexo = pa.get("cria_sexo") or rng.choice(["Hembra", "Macho"])
        ident = str(ID_DEMO_CRIAS + k)
        if db.animales.find_one({"identificacion": ident}):
            continue
        db.animales.insert_one(
            {"identificacion": ident, "nombre": rng.choice(NOMBRES_CRIAS_DEMO[sexo]), "sexo": sexo,
             "categoria": "Ternera" if sexo == "Hembra" else "Ternero", "estado": "Activa",
             "fecha_nacimiento": pa["fecha"], "fecha_ingreso": pa["fecha"], "procedencia": "Finca Campo Alegre",
             "potrero": madre["potrero"], "madre": madre["identificacion"], "marca": "Hierro Campo Alegre",
             "observaciones": "Cría con buen peso, mama bien", "creado_en": ahora, "actualizado_en": ahora, "demo": True})
        mov("Nacimiento", ident, pa["fecha"], madre=madre["identificacion"])
        traslado_inicial(ident, madre["potrero"], pa["fecha"])
        pesaje(ident, pa["fecha"], float(rng.randint(28, 42)), "Estimado", "Peso al nacer, estimado a ojo")
        resumen["crias"] += 1

    # Animales que ya salieron de la finca, con su historial antes de la salida.
    potreros = [p["nombre"] for p in db.potreros.find({"activo": True}).sort("nombre_lower", 1)]
    for k, (motivo, detalle, estado) in enumerate(SALIDAS_DEMO):
        ident = str(ID_DEMO_SALIDAS + k)
        if db.animales.find_one({"identificacion": ident}):
            continue
        sexo, categoria = (("Hembra", "Novilla"), ("Macho", "Novillo"), ("Hembra", "Vaca"))[k % 3]
        potrero = potreros[(k * 4) % len(potreros)]
        nacimiento = dias(-rng.randint(900, 2000))
        ingreso = nacimiento + timedelta(days=rng.randint(0, 40))
        salida = dias(-rng.randint(3, 150))
        db.animales.insert_one(
            {"identificacion": ident, "nombre": NOMBRES_SALIDAS_DEMO[k], "sexo": sexo, "categoria": categoria,
             "estado": estado, "fecha_nacimiento": nacimiento, "fecha_ingreso": ingreso, "procedencia": "Finca Campo Alegre",
             "potrero": potrero, "marca": "Hierro Campo Alegre", "observaciones": "Salió de la finca (ver movimientos)",
             "creado_en": ahora, "actualizado_en": ahora, "demo": True})
        traslado_inicial(ident, potrero, ingreso)
        pesaje(ident, salida - timedelta(days=rng.randint(5, 40)), float(rng.randint(380, 520)),
               rng.choice(["Medido", "Estimado"]), "Pesaje antes de la salida")
        vac = salida - timedelta(days=rng.randint(30, 120))
        db.eventos_sanitarios.insert_one(
            {"animal": ident, "tipo": "Vacunación", "producto": "Fiebre aftosa", "fecha_aplicacion": vac,
             "proxima_dosis": None, "observaciones": "Sin novedad", "registrado_por": "admin",
             "creado_en": ahora, "demo": True})
        mov("Salida", ident, salida, motivo=motivo, detalle=detalle)
        resumen["salidas"] += 1

    # Novedades sobre vacas activas, en los últimos 90 días.
    for v in rng.sample(vacas, min(15, len(vacas))):
        fecha = max(dias(-rng.randint(1, 90)), v["fecha_ingreso"])
        mov("Novedad", v["identificacion"], fecha, detalle=rng.choice(NOVEDADES_DEMO))
        resumen["novedades"] += 1
    return resumen


def borrar_demo(db):
    """Borra solo lo que creó crear_demo. Devuelve cuántos documentos quitó."""
    n = 0
    for nombre in ("animales", "eventos_sanitarios", "eventos_reproductivos", "pesajes", "traslados", "movimientos"):
        n += getattr(db, nombre).delete_many({"demo": True}).deleted_count
    return n
