# POA: últimos cambios de integración, errores y despliegue

Actualizado: 8 de septiembre de 2026.

Este documento complementa la [guía completa del frontend](INTEGRACION_FRONTEND_POA.md).
Las rutas usan la misma URL base y autenticación que el resto de la API. No son rutas
del POA anterior ni requieren nuevos secretos de GitHub.

## 1. Cambios que debe incorporar el frontend

### Encabezado y firmas

En `POST /poa/cedulas` y `PATCH /poa/cedulas/{form_id}` se admiten
`tipo_estrategia` y `firmantes`. Ejemplo de PATCH:

```json
{
  "tipo_estrategia": "Eficiencia",
  "firmantes": [
    {"nombre": "Nombre de quien elabora", "cargo": "Cargo de quien elabora"},
    {"nombre": "Nombre de quien autoriza", "cargo": "Cargo de quien autoriza"}
  ]
}
```

Obtener los tipos mediante `GET /poa/catalogos/tipos-estrategia`:
`Eficiencia`, `Eficacia`, `Pertinencia`, `Vinculación`, `Equidad de Género`.
No confundir el tipo con la denominación o clave de la estrategia.

La lista de firmantes puede estar vacía durante el borrador o contener exactamente
dos elementos; uno solo se rechaza. Nombre y cargo no admiten cadenas vacías ni sólo
espacios. Para emitir se exige tipo de estrategia y ambos firmantes.
Son datos para representar los espacios de firma, no firmas digitales ni un flujo
de aprobación. Las emisiones nuevas conservan esos datos en su snapshot; las
históricas no se reescriben.

Los cuerpos del POA rechazan propiedades desconocidas con `422`, incluso en objetos
anidados. Construir DTO de escritura explícitos: no reenviar todo el objeto recibido
por GET, pues contiene campos de sólo lectura. Las cadenas de entrada se recortan
en sus extremos. Los PATCH de estructura generalmente no usan `null` para borrar.

### Total alcanzado de cada indicador

`PATCH /poa/cedulas/indicadores/{form_indicator_id}/total-alcanzado`:

```json
{
  "periodo_id": 33,
  "total_alcanzado": "120",
  "porcentaje_alcanzado": "80"
}
```

El ID del ejemplo se sustituye por el periodo de C3 de esa cédula. Ambos valores
son explícitos: el backend no deduce el porcentaje dividiendo entre la meta.
Cero es un valor capturado, no un pendiente. Consultar en la guía los límites
numéricos de cada campo.

La operación exige permiso de Planeación, periodo propio y abierto, y fecha actual
dentro de C3, incluidos sus días inicial y final. La fecha institucional usa
`America/Mexico_City`. La excepción administrativa para editar estructura después
de C1 no elimina esta restricción del total. C1 y C2 no exponen el total anual en
sus nuevas emisiones aunque posteriormente se capture en C3.

### Emisión y recordatorios

`POST /poa/cedulas/{form_id}/emisiones` continúa recibiendo el cuatrimestre y su
`periodo_id`, según la guía completa. Después de validar acceso y periodo, ahora
informa **todos los pendientes de contenido** en una respuesta. No crea una emisión
parcial. Se revisan tipo, firmantes, al menos un indicador y una actividad,
seguimientos con alcanzado/progreso/alcance y evidencia de tipo archivo; en C3,
también los dos valores del total de cada indicador.

Los avisos de asignación y recordatorios no requieren un endpoint nuevo en el
frontend. Usar `GET /notificaciones` y marcar leídas con
`POST /notificaciones/{id}/leer`. El scheduler revisa pendientes cada seis horas
por defecto; no es un envío exactamente a medianoche.

- Asignación: usuarios activos habilitados del área ejecutora.
- Captura: ventana de inicio y última semana del cuatrimestre, sólo pendientes.
- Total: misma lógica, únicamente C3 y destinatarios de Planeación.
- Se deduplica por destinatario, elemento, periodo y ventana.
- Un aviso no abre el periodo ni concede permisos. El borrador requiere apertura.
- `entidad_id` apunta a la actividad/indicador de la cédula, no al catálogo.
- `EMAIL_PROVIDER=console` simula correo; se necesita SMTP para entrega real.

## 2. Contrato de errores

Los errores controlados conservan este sobre:

```json
{
  "code": "INVALID_STATE",
  "message": "El periodo debe estar abierto.",
  "details": {
    "reason": "POA_PERIOD_NOT_OPEN",
    "field": "periodo_id",
    "periodo_id": 33,
    "estado": "cerrado"
  },
  "request_id": "identificador-de-la-peticion"
}
```

`message` es para la persona; no implementar lógica comparando ese texto.
Usar estado HTTP, `code` y, cuando exista, `details.reason`. El ejemplo ilustra la
estructura: los mensajes concretos pueden variar. `details` puede ser arreglo,
objeto o `null`; `reason` no aparece en todos los errores.

### Validación de la petición: detalles como arreglo

HTTP `422`, `code=REQUEST_VALIDATION_ERROR`:

```json
{
  "code": "REQUEST_VALIDATION_ERROR",
  "message": "La solicitud contiene datos invalidos.",
  "details": [
    {
      "loc": ["body", "porcentaje_alcanzado"],
      "field": "porcentaje_alcanzado",
      "msg": "Este campo es obligatorio.",
      "type": "missing"
    }
  ],
  "request_id": "identificador-de-la-peticion"
}
```

`field` facilita asociar el error al formulario. Por ejemplo,
`firmantes.1.nombre` corresponde al segundo firmante: estos índices comienzan en
cero. Se mantienen `loc`, `msg` y `type` para compatibilidad. No se devuelve el
cuerpo original, los valores de entrada ni contraseñas en estos detalles.

### Cédula incompleta: detalles con errores por fila

HTTP `422`, `code=BUSINESS_VALIDATION_ERROR`:

```json
{
  "code": "BUSINESS_VALIDATION_ERROR",
  "message": "La cédula está incompleta. Revise los campos indicados antes de emitir.",
  "details": {
    "reason": "POA_FORM_INCOMPLETE",
    "cedula_id": 12,
    "cuatrimestre": 3,
    "errors": [
      {"field": "firmantes", "message": "Indique los nombres y cargos de los dos firmantes."},
      {
        "field": "evidencias",
        "message": "Vincule al menos una evidencia de tipo archivo.",
        "actividad_id": 71,
        "seguimiento_id": 94,
        "cuatrimestre": 3
      },
      {
        "field": "total_alcanzado",
        "message": "Capture total alcanzado del indicador.",
        "indicador_id": 42,
        "cuatrimestre": 3
      }
    ],
    "actividad_ids": [71],
    "indicador_ids": [42]
  },
  "request_id": "identificador-de-la-peticion"
}
```

Los IDs de negocio son identificadores persistidos, **no posiciones del arreglo**.
Ubicar la fila por `actividad_id` o `indicador_id`, y después resaltar `field`.
Si falta todo el seguimiento se señala `field=seguimiento`; primero debe crearse
antes de vincular evidencias. Se permite guardar avances incompletos; esta lista
es la validación de emisión, no una transacción de guardado masivo.

### Motivos específicos del POA

| `details.reason` | Qué debe hacer la interfaz |
| --- | --- |
| `POA_FORM_INCOMPLETE` | Mostrar `errors` completos, agrupados por sección y fila. |
| `POA_STRUCTURE_LOCKED` | Informar que terminó C1; usar `fecha_fin`, `fecha_actual` y `zona_horaria`. No bloquear por ello la justificación ni confundirlo con cierre de periodo. |
| `POA_TOTAL_OUTSIDE_WINDOW` | Deshabilitar total fuera de C3; mostrar `fecha_inicio`, `fecha_fin` y fecha institucional. |
| `POA_PERIOD_MISMATCH` | Reconsultar los cuatrimestres de la cédula y usar `periodo_esperado_id`. |
| `POA_PERIOD_NOT_OPEN` | Mostrar `estado`; la persona autorizada debe abrir el periodo si procede. |
| `POA_PLANNING_REQUIRED` | La operación requiere Planeación; no mostrar un reintento como solución. |
| `POA_ACTIVITY_NOT_ASSIGNED` | El área de la cuenta no tiene asignada esa actividad. |
| `POA_FORM_DUPLICATE` | En edición, la combinación ejercicio/estrategia/área ya existe; HTTP 409. |
| `POA_INVALID_QUARTERS` | Debe existir exactamente C1, C2 y C3. |
| `POA_QUARTER_YEAR_MISMATCH` | Corregir año de fechas; se devuelve `anio_esperado` y `cuatrimestre`. |
| `POA_QUARTER_INVALID_RANGE` | La fecha final debe ser posterior a la inicial. |
| `POA_QUARTERS_OVERLAP` | Corregir solapamiento; usar `cuatrimestre` y `fin_anterior`. |

En estos errores de calendario, `cuatrimestre` es el número 1, 2 o 3, no un índice.
Las validaciones HTTP pueden actuar antes que las reglas de negocio; por ejemplo,
una lista con sólo dos cuatrimestres devuelve `REQUEST_VALIDATION_ERROR`.
Los controles de acceso de la ruta también pueden devolver `FORBIDDEN` sin motivo
específico. Otros duplicados conservan `CONFLICT` sin `reason`: manejar el caso genérico.

### Tratamiento por estado HTTP

| HTTP | Códigos habituales | Comportamiento |
| --- | --- | --- |
| 400 | `HTTP_ERROR` u otro controlado | Mostrar mensaje y conservar captura. |
| 401 | `AUTHENTICATION_REQUIRED` | Renovar sesión una sola vez si corresponde; si falla, login. |
| 403 | `FORBIDDEN` | Informar falta de permiso, sin bucle de renovación de sesión. |
| 404 | `RESOURCE_NOT_FOUND`, `HTTP_ERROR` | Reconsultar selección; recurso inexistente o ruta no disponible. |
| 409 | `CONFLICT`, `CAPTURE_IMMUTABLE` | Reconsultar antes de editar otra vez; no sobrescribir automáticamente. |
| 413 | `FILE_TOO_LARGE` | Solicitar archivo menor; usar `details.max_bytes` cuando exista. |
| 415 | `FILE_TYPE_NOT_ALLOWED` | Solicitar un formato permitido. |
| 422 | `REQUEST_VALIDATION_ERROR`, `BUSINESS_VALIDATION_ERROR`, `INVALID_STATE` | Mostrar mensaje y errores junto al campo o fila. |
| 429 | `RATE_LIMIT_EXCEEDED` | Respetar `Retry-After` y evitar nuevos intentos inmediatos. |
| 500 | `INTERNAL_SERVER_ERROR` | Conservar datos y ofrecer `request_id` para soporte. |
| 503 | `SERVICE_UNAVAILABLE` o `HTTP_ERROR` | Servicio temporalmente no disponible; conservar captura. |

Los fallos de conexión/interfaz de base de datos envueltos por SQLAlchemy y el
agotamiento de su pool se traducen a `503 SERVICE_UNAVAILABLE`, con
`Retry-After: 5` y `details.retry_after=5`. Otros fallos inesperados conservan `500`
con mensaje seguro; no se exponen consultas SQL ni trazas al cliente.

`X-Request-ID` y `Retry-After` quedan expuestos por CORS. Puede haber respuestas
sin JSON generadas por Nginx o una desconexión sin respuesta HTTP. Mostrar un
mensaje propio en esos casos, no HTML ni el texto crudo del proxy.

## 3. Normalización sugerida en TypeScript

```ts
type FieldIssue = {
  field?: string;
  message: string;
  actividad_id?: number;
  indicador_id?: number;
  seguimiento_id?: number;
  cuatrimestre?: number;
};

export function normalizeApiError(body: any, response: Response) {
  const details = body?.details;
  let issues: FieldIssue[] = [];
  if (Array.isArray(details)) {
    issues = details.map((item: any) => ({
      field: item?.field,
      message: item?.msg || "Revise este campo.",
    }));
  } else if (Array.isArray(details?.errors)) {
    issues = details.errors;
  } else if (details?.field) {
    issues = [{ ...details, message: body?.message || "Revise este campo." }];
  }
  return {
    status: response.status,
    code: body?.code || "HTTP_ERROR",
    reason: details?.reason,
    message: body?.message || "No se pudo completar la operación. Conserve sus datos.",
    requestId: body?.request_id || response.headers.get("X-Request-ID"),
    retryAfter: response.headers.get("Retry-After"),
    issues,
  };
}

// Después de fetch, usando la autenticación habitual del proyecto:
// const body = await response.json().catch(() => null);
// if (!response.ok) throw normalizeApiError(body, response);
// Una respuesta 204 no contiene JSON y se trata como éxito sin cuerpo.
```

Renderizar mensajes como texto, no HTML. Conservar el formulario si falla el
guardado y cerrarlo sólo después del éxito. No registrar tokens, contraseñas ni
cuerpos sensibles junto con `requestId`.

No reintentar escrituras automáticamente después de un timeout, 500 o 503: el
servidor pudo guardar antes de perderse la respuesta. Primero reconsultar el recurso,
seguimiento, vínculo de evidencia o emisión y después ofrecer un nuevo intento.
`Retry-After` indica espera, **no garantiza idempotencia**. La recuperación de sesión
debe evitar múltiples refresh simultáneos y bucles infinitos.

## 4. Migración y comandos para la VPS

La revisión pendiente es **`0026_cedula_recordatorios`**, posterior a `0025`.
Agrega datos de la cédula y soporte de recordatorios/correo, y amplía la precisión
del porcentaje alcanzado. Estos últimos ajustes de errores no necesitan una `0027`.
`alembic upgrade head` aplica todas las revisiones faltantes en orden y no repite
las ya registradas. No ejecutar también el SQL manual ni usar `alembic stamp`
para saltarse la migración.

El workflow actual ya construye la API y ejecuta `alembic upgrade head` antes de
levantarla. Si despliegas el commit nuevo mediante Actions, no necesitas repetirlo
manualmente. Mantén los cuatro secretos `EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY` y
`EC2_DEPLOY_PATH`; sus nombres también sirven con Hostinger.

### Antes de desplegar

Conserva el `.env` de la VPS y respalda la base. Este comando de Ubuntu guarda un
dump protegido en el servidor, usando los nombres actuales del Compose:

```bash
cd /opt/planeacion-api
umask 077
mkdir -p /opt/planeacion-backups
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U planeacion -d planeacion -Fc \
  > "/opt/planeacion-backups/planeacion-$(date +%Y%m%d-%H%M%S).dump"
```

Verifica que el comando termine correctamente. Ese respaldo contiene datos
sensibles y no respalda los archivos del volumen de uploads; conserva también un
respaldo de éstos según tu procedimiento operativo.

### Despliegue manual, con el código nuevo ya actualizado en la VPS

Ejecutar en orden y detenerse si cualquier comando falla:

```bash
cd /opt/planeacion-api
docker compose -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.prod.yml build api
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml up -d --remove-orphans --wait --wait-timeout 120
docker compose -f docker-compose.prod.yml exec -T api alembic current
curl -fsS https://testeo.tech/health/ready
```

La revisión esperada es `0026_cedula_recordatorios (head)`. Si hay un fallo:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail 100 api postgres nginx
```

No publiques logs sin revisar datos sensibles. No usar `down -v`, borrar volúmenes
ni reinicializar PostgreSQL como solución a una migración fallida.

No se modificó tu `.env` en esta revisión ni se requieren variables nuevas para los
errores. El Compose de producción sí exige que ya exista `POSTGRES_PASSWORD`,
coincidente con la contraseña real de la base y la de `DATABASE_URL`. Cambiar esa
variable no cambia la contraseña de una base ya inicializada. Si la validación de
Compose informa que falta, corrígela con el valor real antes de continuar.

Las políticas `unless-stopped` reinician contenedores al terminar su proceso, pero
un estado `unhealthy` por sí solo no los reinicia. No sustituyen respaldos ni
resuelven falta de disco/memoria. Las comprobaciones de salud detectan disponibilidad.

## 5. Verificación realizada

- 58 pruebas aprobadas, incluyendo repositorios en memoria y PostgreSQL.
- Migraciones desde base temporal vacía hasta `0026_cedula_recordatorios` aprobadas.
- Ruff sin errores.
- Pruebas de errores por campo/fila, ventana de C3, conflicto de edición sin
  modificar el registro original, 503/500 seguros y correlación de peticiones.
- No se ejecutó el despliegue en tu VPS ni se alteró su `.env`.

La guía completa sigue siendo la referencia para roles, endpoints de evidencias,
periodos, notificaciones, reportes y limitaciones funcionales pendientes de definición.
