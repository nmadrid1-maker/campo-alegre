# Sistema de Gestión de Información Campo Alegre

Sistema web para la trazabilidad y el control administrativo del ganado bovino de la Finca Campo Alegre (San Vicente de Chucurí).
Proyecto de grado de Ingeniería de Sistemas, UDI.

**Stack:** Python + Flask, MongoDB, HTML5/CSS3/JavaScript y Bootstrap 5.

## Estado del desarrollo

| Módulo | Estado |
|---|---|
| Inicio de sesión y roles (Administrador / Empleado) | Listo |
| Panel de inicio con resumen y actividades recientes | Listo |
| Gestión del hato ganadero (listar, buscar, ver, crear, editar, eliminar) | Listo |
| Potreros y ubicación de cada animal (lista de potreros, traslados con historial) | Listo |
| Movimientos (nacimientos con madre, entradas, salidas con motivo, novedades) y marca del animal | Listo |
| Control sanitario (registrar, consultar, próximas dosis) | Listo |
| Control reproductivo (servicio, diagnóstico de preñez con fecha de parto estimada o desconocida, parto, aborto; estado gestante/vacía/parida) | Listo |
| Control productivo (pesajes medidos o estimados; filtro por rango de peso en ganado e inventario) | Listo |
| Gestión de usuarios (crear, editar, contraseña, activar/desactivar) | Listo |
| Respaldos (copia automática diaria, manual, descargar, cargar y restaurar) e inicio con doble clic | Listo |
| Informes (inventario, sanitario, reproductivo, productivo, movimientos; filtros por categoría, potrero, fechas; exportar a CSV e imprimir) | Listo |

Un módulo de Configuración (datos de la finca, parámetros) se probó y se retiró por ahora: no hacía falta para el alcance actual.

## Requerimientos de referencia (provisionales)

Estos siete requerimientos son un borrador derivado del alcance de los módulos del documento Proyecto de Grado II.
**No están validados**: se reemplazarán por los del Anexo N (ERS) y el Anexo O (matriz de requerimientos) cuando se
contrasten con la entrevista al administrador, la rejilla de observación y los registros físicos.

| Código | Módulo | Requerimiento | Estado |
|---|---|---|---|
| RF-01 | Gestión del hato | Registrar la información de cada animal | Hecho |
| RF-02 | Gestión del hato | Consultar y actualizar la información de un animal | Hecho |
| RF-03 | Control sanitario | Registrar los eventos sanitarios asociados a cada animal | Hecho |
| RF-04 | Control reproductivo | Registrar y consultar eventos reproductivos | Hecho |
| RF-05 | Control productivo | Registrar y consultar pesajes | Hecho |
| RF-06 | Informes | Generar informes a partir de la información almacenada | Hecho |
| RF-07 | Gestión de usuarios | Gestionar el acceso de los usuarios autorizados | Hecho |

Funciones que se agregaron sin estar en esa lista y que conviene confirmar con el administrador: eliminar animales,
eliminar eventos sanitarios, reproductivos y pesajes (para corregir errores de digitación), el aviso de próximas dosis y de partos probables en el inicio, y el cálculo de ganancia diaria de peso (GDP).

## Qué necesitas

- Python 3.11 o superior
- MongoDB Community Server corriendo en tu computador (el servicio "MongoDB Server")
- MongoDB Compass (opcional, para ver los datos)
- VS Code

## Puesta en marcha (Windows, terminal de VS Code)

Abre esta carpeta en VS Code (Archivo > Abrir carpeta) y abre una terminal (Terminal > Nueva terminal).
Si en tu computador el comando de Python es `python` en vez de `py`, cámbialo en todos los pasos.

1. **Crear el entorno virtual**

   ```
   py -m venv .venv
   ```

2. **Activarlo**

   ```
   .venv\Scripts\Activate.ps1
   ```

   Si PowerShell dice que la ejecución de scripts está deshabilitada, escribe esto y vuelve a activar:

   ```
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   ```

   Cuando funcione, verás `(.venv)` al comienzo de la línea de la terminal.

3. **Instalar las dependencias**

   ```
   pip install -r requirements.txt
   ```

4. **Crear tu archivo de configuración.** Copia `.env.example` y renombra la copia a `.env`.
   Cambia `SECRET_KEY` por una frase larga y aleatoria, y las contraseñas `SEED_*` por las tuyas.
   El archivo `.env` no se sube a GitHub.

5. **Crear los usuarios y unos animales de ejemplo**

   ```
   py seed.py
   ```

   Crea el usuario `admin` (Administrador) y el usuario `empleado` (Empleado). Sus contraseñas son
   las de `SEED_ADMIN_PASSWORD` y `SEED_EMPLEADO_PASSWORD` de tu `.env`. Puedes ejecutarlo más
   de una vez, no duplica nada. Si no quieres los animales de ejemplo: `py seed.py --solo-usuarios`.

6. **Arrancar el sistema**

   ```
   py run.py
   ```

   Abre http://127.0.0.1:5000 en el navegador. Para detenerlo, `Ctrl + C` en la terminal.

7. **Ver los datos en Compass.** Conéctate a `mongodb://localhost:27017` y abre la base `campo_alegre`.
   Verás las colecciones `usuarios`, `animales`, `eventos_sanitarios`, `eventos_reproductivos`, `pesajes` y `actividad`.

## Uso diario en la finca (sin VS Code)

VS Code solo se usa para programar. Quien use el sistema no necesita abrirlo:

- **`Iniciar Campo Alegre.bat`**: doble clic. Arranca el sistema y abre el navegador. Deje abierta la ventana negra mientras lo usa.
- **`Iniciar Campo Alegre (sin ventana).vbs`**: lo mismo, pero sin ventana negra. Para apagarlo: **`Detener Campo Alegre.bat`**.
- Para tener un icono en el escritorio: clic derecho sobre el `.bat` o el `.vbs` → Enviar a → Escritorio (crear acceso directo).
- Para que arranque solo al encender el computador: copie el acceso directo a la carpeta de Inicio de Windows (Windows + R, escriba `shell:startup`).

MongoDB debe estar instalado como servicio de Windows (arranca solo).

## Copias de seguridad (sección Respaldos, solo Administrador)

- **Automática:** una copia por día, la primera vez que se usa el sistema ese día. Se guardan las últimas 14.
- **Manual:** botón "Crear copia ahora" (se guardan las últimas 30).
- **Descargar** una copia para llevarla en una memoria USB o a otro equipo, y **cargar** una copia desde un archivo.
- **Restaurar:** reemplaza toda la información por la de la copia. Pide escribir RESTAURAR y antes guarda una copia del estado actual ("Antes de restaurar"). Si algo falla, vuelve al estado anterior.
- Carpeta: `respaldos/` dentro del proyecto, o la que indique `RESPALDOS_DIR` en el `.env`. Se puede apuntar a un disco externo.
- La copia automática solo se hace si el sistema estuvo en uso ese día. Una copia que queda en el mismo computador no protege si el equipo se daña: descargue una de vez en cuando.
- Las copias incluyen los usuarios (con sus contraseñas ya cifradas): guárdelas con cuidado.

## Datos de demostración

Para ver el sistema con información (3 vacas en cada uno de los 27 potreros, con datos en todos los campos y eventos sanitarios, reproductivos y pesajes):

```
py seed_demo.py            (carga los datos)
py seed_demo.py --borrar   (los borra; no toca lo que registres tú)
```

Son 81 vacas con identificación 401 a 481, más 12 crías con su madre (701 en adelante), 6 animales que ya salieron de la finca (801 a 806: ventas, muerte, traslado y otro) y 15 novedades. Si ya tenías la demostración cargada, volver a ejecutar `py seed_demo.py` solo agrega los movimientos. Todo lo que crea queda marcado como demostración, por eso `--borrar` no afecta tus datos reales. Se puede ejecutar varias veces sin duplicar.

## Si la contraseña no funciona o la olvidaste

`seed.py` guarda la contraseña en el momento en que crea el usuario. Si cambiaste el `.env` después, la que sirve es la anterior.
Para fijar una nueva sin depender del `.env`:

```
py cambiar_clave.py admin
py cambiar_clave.py empleado
```

Te la pide dos veces y no se ve mientras escribes. Revisa también que el archivo se llame exactamente `.env`
(en Windows, si ocultas las extensiones, puede quedar como `.env.txt` y no se lee).

## Pruebas automáticas

```
pip install -r requirements-dev.txt
py -m unittest discover -s tests -v
```

Las pruebas usan una base de datos simulada en memoria (`mongomock`), así que no tocan tus datos reales.
Cubren inicio de sesión, protección contra CSRF, permisos por rol, validaciones de los formularios de animales y eventos
sanitarios, reproductivos y pesajes, potreros y traslados, informes y exportación, gestión de usuarios (incluye desactivar con sesión abierta), búsqueda, filtros, paginación, edición, eliminación, partos probables y GDP.

## Funciona sin internet

Bootstrap 5.3.3 viene incluido en `campo_alegre/static/vendor/`, así que el sistema no necesita conexión (RNF de funcionamiento local).

## Estructura

```
campo_alegre/
  __init__.py     crea la aplicación (create_app)
  config.py       configuración desde .env
  db.py           conexión a MongoDB, índices únicos y registro de actividad
  security.py     roles, protección CSRF, decoradores y menú
  auth.py         inicio y cierre de sesión
  inicio.py       panel de inicio
  ganado.py       módulo de gestión del hato
  potreros.py     lista de potreros y traslados de los animales
  sanitario.py    módulo de control sanitario
  reproductivo.py módulo de control reproductivo
  productivo.py   módulo de control productivo (pesajes)
  usuarios.py     gestión de usuarios
  informes.py     informes con filtros, exportación a CSV e impresión
  utils.py        funciones compartidas (fechas, paginación)
  respaldos.py    copias de seguridad automáticas y manuales
  semilla.py      usuarios, potreros, animales de ejemplo y datos de demostración
  templates/      pantallas (Jinja)
  static/         estilos, imágenes y Bootstrap local
tests/            pruebas automáticas (una por módulo, más base.py)
run.py            arranque en desarrollo
seed.py           carga de datos iniciales
seed_demo.py      carga o borra los datos de demostración
```

## Modelo de datos (MongoDB)

**usuarios:** `usuario` (único), `nombre`, `rol`, `password_hash`, `activo`, `creado_en`.

**animales:** `identificacion` (único), `nombre`, `sexo`, `categoria`, `estado`, `fecha_nacimiento`,
`fecha_ingreso`, `procedencia`, `potrero` (nombre, opcional), `observaciones`, `creado_en`, `actualizado_en`.

**potreros:** `nombre`, `nombre_lower` (único, sin distinguir mayúsculas), `activo`, `observaciones`, `creado_en`, `actualizado_en`.

**traslados:** `animal`, `desde` (vacío si es la primera ubicación), `hacia` (vacío si queda sin potrero), `fecha`, `registrado_por`, `creado_en`.

**eventos_sanitarios:** `animal` (identificación del animal), `tipo` (Vacunación, Desparasitación, Tratamiento u Otro),
`producto`, `fecha_aplicacion`, `proxima_dosis` (opcional), `observaciones` (opcional), `registrado_por`, `creado_en`.

**eventos_reproductivos:** `animal`, `tipo` (Servicio, Diagnóstico de preñez, Parto, Aborto), `fecha`, y según el tipo:
`metodo` (Monta o Inseminación artificial) y `reproductor` (opcional) y `parto_probable` en el servicio; `resultado`
(Preñada o Vacía) en el diagnóstico; `cria_sexo` (opcional) y `cria_estado` (Viva o Muerta) en el parto; además
`observaciones`, `registrado_por`, `creado_en`. Los campos que no corresponden al tipo se guardan vacíos.

**pesajes:** `animal`, `fecha`, `peso_kg`, `observaciones`, `registrado_por`, `creado_en`. Índice único (animal, fecha).

**actividad:** `fecha`, `usuario`, `texto` (alimenta "Actividades recientes").

## Reglas de negocio ya implementadas

- La identificación del animal es única y no se puede cambiar después de creada.
- La categoría debe corresponder al sexo (Vaca, Novilla y Ternera son hembras; Toro, Novillo y Ternero son machos).
- Las fechas de nacimiento e ingreso no pueden ser futuras, y el ingreso no puede ser anterior al nacimiento.
- Un evento sanitario solo se registra a un animal que existe y está en estado Activa.
- La fecha de aplicación no puede ser futura ni anterior al nacimiento del animal.
- La próxima dosis, si se indica, debe ser posterior a la fecha de aplicación.
- "Próximas vacunas" del inicio cuenta los eventos cuya próxima dosis cae entre hoy y los siguientes 30 días.
- Un animal con eventos sanitarios no se puede eliminar; se cambia su estado a Vendido o Fallecido.
- Los eventos reproductivos solo se registran a hembras activas; cada tipo exige sus propios datos (método, resultado, estado de la cría).
- El parto probable de un servicio es la fecha del servicio + 283 días. **Supuesto a confirmar con el administrador.**
- "Partos probables" cuenta los servicios cuyo parto probable cae en los próximos 30 días y que no han sido cerrados por un parto, aborto, nuevo servicio o diagnóstico "Vacía" posterior.
- El peso se registra entre 10 y 1500 kg (un decimal, se acepta coma); un animal solo puede tener un pesaje por fecha.
- Cambio de peso y GDP (g/día) se calculan contra el pesaje anterior del mismo animal.
- Un animal con eventos sanitarios, reproductivos o pesajes no se puede eliminar.
- Usuarios: nombre de usuario único (3 a 30 caracteres, minúsculas), contraseña de 8 a 128 caracteres. Un administrador no puede desactivarse ni cambiarse el rol a sí mismo.
- Si un usuario se desactiva, cambia de rol o se elimina, su sesión abierta lo refleja en la siguiente petición.
- Los informes son solo para el Administrador. Cada uno se filtra (fechas, tipo, animal, sexo, categoría o estado según el informe), muestra un resumen y se exporta a CSV (separado por punto y coma, para que Excel en español lo abra bien) o se imprime desde el navegador.
- En pantalla se muestran hasta 500 filas; el CSV siempre trae todas. Exportar queda en las actividades recientes.
- El CSV antepone una comilla a las celdas de texto que empiezan por =, +, - o @ para que Excel no las ejecute como fórmulas.
- Los potreros los administra el Administrador (crear, editar, desactivar, eliminar). Los 27 potreros de la finca se cargan con `py seed.py`.
- Un potrero no puede repetirse (sin distinguir mayúsculas). Si se cambia su nombre, se actualiza en los animales y en el historial.
- No se puede desactivar un potrero con animales activos, ni eliminar uno que tuvo animales o traslados.
- Al registrar un animal con potrero, o al cambiárselo en "Editar", queda un traslado con la fecha de hoy. Un animal puede quedar sin potrero.
- Al eliminar un animal se borra también su historial de traslados.
- El Administrador tiene acceso total: registra, actualiza, consulta y elimina.
- El Empleado solo consulta: ve ganado, potreros, controles e informes (y puede exportarlos), pero no registra, modifica ni elimina nada, y no ve Usuarios.
- Las contraseñas se guardan con hash, nunca en texto plano.

## Flujo de trabajo

Lean Software Development con tablero Kanban. Un commit por cambio con sentido, y cada módulo se prueba antes de integrarse.

## Registros oficiales 2024-2025

`datos/registros_ganado_2024_2025.csv` es el cuaderno de movimientos (nacidos, comprados, vendidos, muertes y retiros).
`py importar_registros.py` muestra una vista previa; `--cargar` hace un respaldo y lo carga como animales individuales
(IDs `24-N-001`, `24-C-001`, `24-I-001`); `--controles` agrega potreros, vacunas, partos y pesajes de ejemplo a lo ya cargado; `--borrar` quita solo lo cargado por este script.
