# Backend de la Plataforma Institucional de Planeacion Educativa

Backend inicial basado en Python 3.12, FastAPI, Clean Architecture y Vertical Slice.

## Estado actual

La Fase 0 ya tiene una implementacion ejecutable con fallback sin base de datos:

- `core`: configuracion, JWT, Argon2, RBAC, errores, middleware y OpenAPI.
- `core.app_factory`, `core.container` y `core.event_handlers`: composición de dependencias y eventos; `main.py` solo expone el entrypoint ASGI.
- `api/router_registry.py`: registro único y ordenado de routers HTTP.
- `shared`: entidades base, objetos de valor, paginacion y bus de eventos.
- `identity_access`: login, refresh rotation, logout, usuario actual y alta de usuarios.
- `institutional_catalogs`: areas e instrumentos con repositorio SQLAlchemy o memoria.
- `periods`: apertura, cierre y reapertura de periodos con repositorio SQLAlchemy o memoria.
- `audit`: bitacora inmutable consumiendo eventos sin acoplarse a los emisores.
- `indicators_catalog`: indicadores, clasificacion PIDE, linea base, metas y periodicidad.
- `evidence_management`: evidencias reutilizables y versiones append-only.
- `indicators_capture`: borradores, envio, panel personal y bloqueo por periodo.
- `indicators_validation`: validacion, rechazo e historial de estados.
- `indicators_scoring`: umbrales, porcentaje de avance, semaforo y tendencia.
- `indicators_reports`: reportes JSON, Excel y PDF con registro de generacion.
- `poa_planning`: ejercicios, procesos, objetivos y actividades del POA.
- `poa_tracking`: avances de los tres cuatrimestres, cumplimiento y acumulado.
- `poa_validation`: validacion/rechazo de avances usando `cambios_estado` compartido.
- `poa_reports`: reportes cuatrimestrales, anuales, de estatus y ejecutivo.

Con `DATABASE_URL` configurada se usan adaptadores SQLAlchemy async sobre PostgreSQL. Sin esa variable se usan repositorios en memoria para desarrollo y pruebas; no deben usarse como persistencia de un ambiente compartido.

El alcance funcional actual maneja indicadores PIDE y el flujo POA. Algunas tablas auxiliares del DDL original se conservan para compatibilidad de migraciones, pero no tienen endpoints ni lógica activa en la API.

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

## Correo y notificaciones

El proveedor predeterminado es `console`: registra los correos simulados y no requiere credenciales. Para una cuenta de prueba SMTP, configura en `.env` `EMAIL_PROVIDER=smtp`, `EMAIL_SENDER`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER` y `SMTP_PASSWORD`. No guardes la contraseña en el repositorio; usa una contraseña de aplicación o un servidor local como Mailpit.

Para disponer de un usuario inicial en desarrollo, configura `BOOTSTRAP_ADMIN_EMAIL` y `BOOTSTRAP_ADMIN_PASSWORD` en `.env` antes de iniciar.

Los usuarios administrativos no necesitan capturar una contrasena en `POST /api/v1/usuarios`: reciben un enlace de un solo uso en su correo y establecen la contrasena mediante `POST /api/v1/auth/password-setup`. El token expira y no se almacena en texto plano.

## Pruebas

```powershell
pytest
```

## Proxima etapa

La siguiente etapa es completar las vertical slices de indicadores, POA, evidencias, validaciones, notificaciones y reportes sobre los mismos puertos y migraciones.
