# POA único y cambio privado de contraseña

## Sólo queda el flujo actual

Se retiraron los módulos operativos `poa_tracking` y `poa_validation`, junto con la
estructura antigua de procesos, objetivos libres, actividades y avances. No quedan
routers ni adaptadores de ese flujo en la composición de la API.

El flujo vigente es: ejercicio → cédula → indicadores y actividades del catálogo →
seguimientos por actividad/cuatrimestre con evidencias → emisión inmutable.

Las siguientes rutas antiguas ahora devuelven `404`:

- `/api/v1/poa/procesos`
- `/api/v1/poa/objetivos`
- `/api/v1/poa/actividades` y sus subrutas antiguas
- `/api/v1/poa/avances` y sus subrutas de envío, validación y evidencias
- `/api/v1/poa/reportes/por-proceso`

Usar `/poa/cedulas/{id}/actividades`, `/poa/cedulas/{id}/indicadores` y los endpoints
descritos en `CONTRATO_CEDULAS_POA.md`. Los IDs del modelo retirado no son IDs del modelo
actual y no deben reutilizarse en las nuevas rutas.

Las migraciones históricas se conservan: no se borra información de un servidor al
desplegar. Las tablas antiguas permanecen sin uso operativo y no se copian a cédulas.
También se conservan los valores históricos de enums necesarios para leer registros
almacenados, pero los endpoints de evidencias sólo admiten `captura` o
`poa_cedula_seguimiento`. No se permite operar evidencias del POA retirado.

## Integraciones adaptadas

- Reportes `/poa/reportes/cuatrimestral`, `/anual`, `/por-cedula`, `/por-area`, `/estatus`,
  `/evidencias-faltantes` y `/ejecutivo`: consultan actividades y seguimientos actuales.
  Admiten `cedula_id`, `ejercicio_id`, `periodo_id`, `objetivo_numero`, `estrategia_clave`,
  `area_id`, `tipo` y `formato=json|xlsx|pdf`. Filtros antiguos como `proceso_id` o
  `responsable_id` se rechazan con `422`; no se ignoran devolviendo datos globales.
- `area_id` filtra el área ejecutora. Para un capturista de otra área se fuerza su propia
  área, aunque envíe un ID ajeno. Revisión y consulta de Rectoría del nuevo POA siguen
  pendientes y no se habilitaron mediante los reportes.
- Los reportes tienen `fuente=cedulas_actuales` y `datos=captura_actual`: muestran datos
  editables actuales, no una certificación de validación. Para el respaldo oficial del
  cuatrimestre se consulta `/poa/emisiones/{id}`. Un reporte anual sólo marca `completo`
  cuando las cédulas incluidas tienen las tres emisiones.
- El reporte de evidencias faltantes incluye actividades sin captura y cuatrimestres
  sin archivo. Si sólo se quiere un cuatrimestre, se debe enviar su `periodo_id`.
- Dashboards: las filas `poa` pertenecen a cédulas actuales. Se sustituyen los contadores
  de avances validados por `cedulas_poa` y `seguimientos_poa_capturados`. No se inventa
  un estado de validación que todavía no existe en el nuevo flujo.
- Historial: `/poa/cedulas/actividades/{id}/historial` consulta `poa_form_activity`.
- Aperturas y recordatorios notifican a usuarios activos con permiso sobre las áreas
  ejecutoras del periodo exacto de la cédula, además de Planeación/administradores.
- Reabrir periodos permite continuar capturando conforme a las reglas actuales; nunca
  resetea supuestos avances antiguos ni reescribe las emisiones guardadas.

## Cambiar mi contraseña de administrador

El comando de alta administrativa sigue funcionando para crear la cuenta inicial.
Después de iniciar sesión, el titular puede cambiar esa contraseña por una privada.
El cambio no es obligatorio automáticamente al primer login y puede repetirse después.

```http
POST /api/v1/auth/cambiar-contrasena
Authorization: Bearer <access_token_actual>
Content-Type: application/json
```

```json
{
  "contrasena_actual": "contraseña-con-la-que-iniciaste",
  "contrasena_nueva": "contraseña-nueva-privada",
  "confirmar_contrasena": "contraseña-nueva-privada"
}
```

Sólo `admin_sistema` y `planeacion_admin`, sobre su propia cuenta. No acepta `user_id`
ni correo de otra persona. La nueva contraseña debe tener de 8 a 128 caracteres, coincidir
con la confirmación y diferir de la actual. La API conserva sólo el hash Argon2.

Respuesta `204`, sin cuerpo. El frontend debe borrar el access token guardado y volver
al login. La cookie de refresh se elimina y todos los access/refresh tokens anteriores,
incluidos los de otros dispositivos, se rechazan. La revocación persiste en PostgreSQL
por la versión de credenciales y no depende de reiniciar o no el servidor.

Errores: `401` si falta autenticación o la contraseña actual es incorrecta; `403` por rol;
`422` por confirmación, reutilización o datos inválidos; `429` tras demasiados intentos
fallidos. La contraseña no se incluye en respuestas de validación ni en la bitácora.
Usuario, revocación y auditoría se actualizan en una transacción en PostgreSQL.

## Despliegue

Aplicar las nuevas migraciones antes de iniciar esta versión de la API:

```bash
docker compose -f docker-compose.prod.yml build api
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml up -d
```

`0024_password_version` agrega la versión de credenciales. `0025_notificaciones_entidad`
amplía las referencias de notificación a texto para aceptar periodos y conserva los
valores anteriores. No cambian contraseñas ni usuarios existentes. No se necesita agregar
variables al `.env`. El workflow existente ya ejecuta las migraciones al desplegar.

## Verificación realizada

44 pruebas aprobadas con PostgreSQL temporal migrado desde cero hasta
`0025_notificaciones_entidad`. Incluyen ausencia de rutas antiguas, múltiples filas por
cédula, reportes y exportaciones PDF/XLSX, dashboard e historial actuales, aislamiento
por área, apertura/notificaciones, contraseñas incorrectas, confirmación, revocación de
dos sesiones y reversión del cambio de contraseña ante fallo de auditoría. Ruff y
`git diff --check` sin errores. No se desplegó en la VPS ni se modificó el `.env` personal.

El código antiguo retirado puede recuperarse desde el historial Git si fuera necesario.
