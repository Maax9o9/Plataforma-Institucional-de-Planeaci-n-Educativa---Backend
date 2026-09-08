# Backend de la Plataforma Institucional de Planeacion Educativa

Backend inicial basado en Python 3.12, FastAPI, Clean Architecture y Vertical Slice.

## Estado actual

La Fase 0 ya tiene una implementacion ejecutable con fallback sin base de datos:

- `core`: configuracion, JWT, Argon2, RBAC, errores, middleware y OpenAPI.
- `core.app_factory`, `core.container` y `core.event_handlers`: composición de dependencias y eventos; `main.py` solo expone el entrypoint ASGI.
- `api/router_registry.py`: registro único y ordenado de routers HTTP.
- `shared`: entidades base, objetos de valor, paginacion y bus de eventos.
- `identity_access`: login, rotación de refresh, logout, invitaciones, alta por comando
  y cambio privado de contraseña administrativa con revocación persistente de sesiones.
- `institutional_catalogs`: areas e instrumentos con repositorio SQLAlchemy o memoria.
- `periods`: apertura, cierre y reapertura de periodos con repositorio SQLAlchemy o memoria.
- `audit`: bitacora inmutable consumiendo eventos sin acoplarse a los emisores.
- `indicators_catalog`: indicadores, clasificacion PIDE, linea base, metas y periodicidad.
- `evidence_management`: evidencias reutilizables y versiones append-only.
- `indicators_capture`: borradores, envio, panel personal y bloqueo por periodo.
- `indicators_validation`: validacion, rechazo e historial de estados.
- `indicators_scoring`: umbrales, porcentaje de avance, semaforo y tendencia.
- `indicators_reports`: reportes JSON, Excel y PDF con registro de generacion.
- `poa_planning`: ejercicios y cédulas POA divididas en estrategia, indicadores,
  total alcanzado y calendarización de actividades, con catálogos del formato 2026.
- `poa_reports`: reportes de las cédulas actuales por periodo, cédula, área y estatus.
- `dashboards`: vistas ejecutiva, de Planeacion y del area con aislamiento por rol.
- `notifications`: avisos internos/correo y recordatorios automaticos idempotentes.

Con `DATABASE_URL` configurada se usan adaptadores SQLAlchemy async sobre PostgreSQL. Sin esa variable se usan repositorios en memoria para desarrollo y pruebas; no deben usarse como persistencia de un ambiente compartido.

El alcance funcional actual maneja indicadores PIDE y el flujo POA. Algunas tablas auxiliares del DDL original se conservan para compatibilidad de migraciones, pero no tienen endpoints ni lógica activa en la API.

El POA anterior fue retirado: sólo están activos ejercicios, catálogos, cédulas,
seguimientos y emisiones del modelo actual. Reportes, dashboards, historial y
recordatorios consultan ese mismo modelo. Consulta [los cambios para frontend y despliegue](docs/POA_UNICO_Y_CAMBIO_CONTRASENA.md).

## Ejecucion local

Desde la carpeta `backend`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

El workspace incluye `.vscode/settings.json`: selecciona automaticamente `backend/.venv` y oculta visualmente `.venv` y caches del explorador. Los paquetes usan namespace packages de Python y no requieren archivos `__init__.py`.

La documentacion queda disponible en:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Health check: `http://127.0.0.1:8000/health`

## PostgreSQL y migraciones

Con Docker Desktop iniciado, desde `backend`:

```powershell
Copy-Item .env.example .env
docker compose up -d postgres
.\.venv\Scripts\Activate.ps1
alembic upgrade head
uvicorn app.main:app --reload
```

Cuando `DATABASE_URL` existe, `app.main` selecciona los repositorios SQLAlchemy. Cuando esta vacia, conserva los repositorios en memoria para desarrollo y pruebas. El health check devuelve `database=connected` o `database=in_memory`.

Las migraciones SQL son la fuente de verdad en `bd/migrations/`; los archivos de `alembic/versions/` solo las orquestan y no deben reemplazarse por `--autogenerate`.

Para restaurar los datos reproducibles de integración (solo desarrollo o staging), define
una contraseña por canal privado y ejecuta el comando idempotente:

```powershell
$env:SEED_TEST_PASSWORD = "una-clave-temporal-de-12-o-mas-caracteres"
python -m app.scripts.seed_integration
Remove-Item Env:SEED_TEST_PASSWORD
```

El comando crea las cinco cuentas por rol, catálogos, periodos, seis indicadores, metas,
capturas en distintos estados, evidencias y auditoría. No imprime ni almacena la contraseña
en el repositorio. La matriz de permisos está en `docs/RBAC.md`.

## Correo y notificaciones

El proveedor predeterminado es `console`: registra los correos simulados y no requiere credenciales. Para una cuenta de prueba SMTP, configura en `.env` `EMAIL_PROVIDER=smtp`, `EMAIL_SENDER`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER` y `SMTP_PASSWORD`. No guardes la contraseña en el repositorio; usa una contraseña de aplicación o un servidor local como Mailpit.

Para crear un administrador en la base de datos, ejecuta `python -m app.scripts.create_admin --correo admin@tu-institucion.mx --nombre "Administrador"`. Solicita la contraseña oculta y su confirmación; no se guarda en `.env` ni se pasa como argumento. Con Docker de producción: `docker compose -f docker-compose.prod.yml exec api python -m app.scripts.create_admin --correo admin@tu-institucion.mx --nombre "Administrador"`. Primero aplica las migraciones (`alembic upgrade head`). `BOOTSTRAP_ADMIN_EMAIL` y `BOOTSTRAP_ADMIN_PASSWORD` ya no crean cuentas al iniciar y pueden eliminarse del `.env`; los usuarios existentes se conservan. `DATABASE_URL` sigue siendo necesaria para la conexión. Consulta [la verificación de flujo y roles](docs/VERIFICACION_POA_Y_ADMIN.md).

Los usuarios administrativos no necesitan capturar una contrasena en `POST /api/v1/usuarios`: reciben un enlace de un solo uso en su correo y establecen la contrasena mediante `POST /api/v1/auth/password-setup`. El token expira y no se almacena en texto plano.

Los recordatorios de vencimiento se procesan automaticamente para los dias 5, 3, 2 y 1
anteriores al cierre. `REMINDER_CHECK_INTERVAL_SECONDS` controla la frecuencia de revision;
la clave idempotente evita duplicados aunque la aplicacion se reinicie. El endpoint
`POST /api/v1/notificaciones/recordatorios/generar` se conserva para ejecucion manual por
Planeacion o administracion.

## Pruebas

```powershell
pytest
```

## Contrato para integracion frontend

- El prefijo estable es `/api/v1` y los campos HTTP usan `snake_case`.
- El refresh token se entrega exclusivamente en la cookie `planeacion_refresh`, marcada
  `HttpOnly` y `SameSite`; nunca se expone a JavaScript ni aparece en el JSON. Se rota en
  cada llamada a `POST /auth/refresh`, se elimina en logout y su reutilizacion invalida la
  sesion completa. El access token se devuelve en JSON y debe mantenerse solo en memoria.
- El frontend debe enviar `credentials: "include"` en login, refresh y logout. Para un
  frontend en otro origen, `CORS_ORIGINS` debe enumerar ese origen: el comodin
  `CORS_ALLOW_ALL=true` no es compatible con cookies credenciales en navegadores.
- `GET /usuarios`, `GET /indicadores`, `GET /capturas` y `GET /bitacora` usan respuestas
  paginadas con `items`, `total`, `offset` y `limit`.
- `/auditoria` se conserva temporalmente como alias paginado y deprecado; `/bitacora` es el
  contrato canónico.
- Los errores incluyen `code`, `message`, `details` y `request_id`; la respuesta también
  expone el mismo identificador mediante `X-Request-ID`.
- Los intentos fallidos de login se limitan con `LOGIN_MAX_ATTEMPTS` y
  `LOGIN_RATE_LIMIT_WINDOW_SECONDS`; un bloqueo temporal devuelve `429` y `Retry-After`.
- Kubernetes, Docker o el monitor externo pueden usar `/health/live` para liveness y
  `/health/ready` para readiness de API y PostgreSQL.
- `POST /api/v1/archivos` acepta PDF, JPG y PNG, valida la firma real, calcula SHA-256 y
  genera el nombre en servidor. El máximo predeterminado es 10 MiB y puede configurarse con
  `UPLOAD_MAX_BYTES`; los archivos se almacenan fuera de directorios públicos. Solo un
  usuario autorizado sobre la captura o avance vinculado puede descargarlos mediante
  `GET /api/v1/archivos/{nombre_generado}`.
- Los campos oficiales de un área incluyen `codigo`, `nombre`, `area_padre_id`, `tipo`,
  `color` y `activo`. La migración `0018_integracion_frontend` agrega los campos nuevos.
- Los orígenes CORS de staging y producción deben declararse explícitamente en
  `CORS_ORIGINS`; `CORS_ALLOW_ALL` no está permitido en ninguno de esos ambientes.

Los cambios de contrato de la versión `0.2.0` se detallan en
`docs/CONTRATO_FRONTEND_0.2.md`.

El flujo refactorizado de cédulas y sus endpoints se documenta en
`docs/CONTRATO_CEDULAS_POA.md`.

Las cuentas y contraseñas de prueba no se incluyen en el repositorio. Deben provisionarse
en el ambiente correspondiente y compartirse por un canal privado.

## Despliegue en VPS

El workflow conserva los nombres `EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY` y
`EC2_DEPLOY_PATH` por compatibilidad con los Repository Secrets existentes, aunque el
servidor sea una VPS. La configuracion funcional permanece exclusivamente en
`/opt/planeacion-api/.env`; GitHub Actions no la reemplaza.

Antes de desplegar, el `.env` de la VPS debe incluir al menos:

```dotenv
ENVIRONMENT=production
SECRET_KEY=<valor-aleatorio-de-32-o-mas-caracteres>
DATABASE_URL=postgresql+asyncpg://planeacion:<password>@postgres:5432/planeacion
POSTGRES_PASSWORD=<el-mismo-password-de-DATABASE_URL>
CORS_ORIGINS=["https://testeo.tech"]
CORS_ALLOW_ALL=false
REFRESH_COOKIE_SECURE=true
REFRESH_COOKIE_SAMESITE=lax
FRONTEND_URL=https://testeo.tech
```

Si aun no existe frontend, usa temporalmente el origen HTTPS publico del backend, como en
el ejemplo. CORS solo controla navegadores y no sustituye la autenticacion; cuando exista
el frontend, reemplazalo o agrega su origen HTTPS exacto. No habilites `CORS_ALLOW_ALL` en
produccion. `POSTGRES_PASSWORD` es obligatorio para Compose y debe coincidir con la
contraseña incluida en `DATABASE_URL`.

`SameSite=lax` funciona cuando frontend y API pertenecen al mismo sitio, por ejemplo
`app.testeo.tech` y `api.testeo.tech`. Si el frontend vive en un sitio distinto, configura
`REFRESH_COOKIE_SAMESITE=none` y conserva obligatoriamente
`REFRESH_COOKIE_SECURE=true`, ademas del origen HTTPS explicito en `CORS_ORIGINS`.

El despliegue valida Compose, construye la imagen, ejecuta `alembic upgrade head`, levanta
los servicios y solo termina correctamente cuando `/health` responde con
`database=connected`. Los archivos se conservan en el volumen `planeacion_uploads` y la
base de datos en `planeacion_postgres_data`.

## Proxima etapa

La siguiente etapa es completar las vertical slices de indicadores, POA, evidencias, validaciones, notificaciones y reportes sobre los mismos puertos y migraciones.
