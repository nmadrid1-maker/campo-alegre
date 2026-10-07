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
| Control sanitario | Pendiente |
| Control reproductivo | Pendiente |
| Control productivo | Pendiente |
| Informes | Pendiente |
| Gestión de usuarios | Pendiente |

Los módulos pendientes muestran una pantalla "en construcción" para que el menú ya funcione completo.

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
   Verás las colecciones `usuarios`, `animales` y `actividad`.

## Pruebas automáticas

```
pip install -r requirements-dev.txt
py -m unittest discover -s tests -v
```

Las pruebas usan una base de datos simulada en memoria (`mongomock`), así que no tocan tus datos reales.
Cubren inicio de sesión, protección contra CSRF, permisos por rol, validaciones del formulario de animales,
búsqueda, paginación, edición y eliminación.

## Bootstrap sin internet

Por defecto Bootstrap 5.3.3 se carga desde un CDN, por lo que la primera vez necesitas internet.
Para que funcione sin conexión (como en la finca), sigue las instrucciones de `campo_alegre/static/vendor/LEEME.txt`.

## Estructura

```
campo_alegre/
  __init__.py     crea la aplicación (create_app)
  config.py       configuración desde .env
  db.py           conexión a MongoDB, índices únicos y registro de actividad
  security.py     roles, protección CSRF, decoradores y menú
  auth.py         inicio y cierre de sesión
  inicio.py       panel de inicio y secciones pendientes
  ganado.py       módulo de gestión del hato
  semilla.py      usuarios y animales de ejemplo
  templates/      pantallas (Jinja)
  static/         estilos, imágenes y Bootstrap local opcional
tests/            pruebas automáticas
run.py            arranque en desarrollo
seed.py           carga de datos iniciales
```

## Modelo de datos (MongoDB)

**usuarios:** `usuario` (único), `nombre`, `rol`, `password_hash`, `activo`, `creado_en`.

**animales:** `identificacion` (único), `nombre`, `sexo`, `categoria`, `estado`, `fecha_nacimiento`,
`fecha_ingreso`, `procedencia`, `observaciones`, `creado_en`, `actualizado_en`.

**actividad:** `fecha`, `usuario`, `texto` (alimenta "Actividades recientes").

## Reglas de negocio ya implementadas

- La identificación del animal es única y no se puede cambiar después de creada.
- La categoría debe corresponder al sexo (Vaca, Novilla y Ternera son hembras; Toro, Novillo y Ternero son machos).
- Las fechas de nacimiento e ingreso no pueden ser futuras, y el ingreso no puede ser anterior al nacimiento.
- El Administrador tiene acceso total; el Empleado solo ve el inicio y los controles de campo.
- Las contraseñas se guardan con hash, nunca en texto plano.

## Flujo de trabajo

Lean Software Development con tablero Kanban. Un commit por cambio con sentido, y cada módulo se prueba antes de integrarse.
