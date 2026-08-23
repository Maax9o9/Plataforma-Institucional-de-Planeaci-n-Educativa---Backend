# Nota de cambios del contrato API 0.2.0

Fecha: 23 de agosto de 2026.

## Seguridad

- Refresh token únicamente en cookie `HttpOnly`; login y refresh no lo incluyen en JSON.
- Rotación atómica por familia de sesión. La reutilización revoca los descendientes.
- Logout idempotente, sin body, y revocación de la familia asociada cuando la cookie existe.
- `Secure` es obligatorio en staging y producción; `SameSite=None` exige `Secure`.
- CORS con credenciales usa solamente orígenes explícitos en staging y producción.
- Login limita intentos fallidos por cliente y correo; al excederlos responde `429`
  (`RATE_LIMIT_EXCEEDED`) con `Retry-After`. En despliegues con varias réplicas debe
  sustituirse el almacenamiento local por uno compartido.

## Consultas

- `GET /indicadores` agrega `sort` y `order`; filtros, total, orden y paginación se ejecutan
  en PostgreSQL.
- `GET /capturas` agrega búsqueda, fechas, capturista, orden y una proyección enriquecida
  con indicador, periodo, área, capturista, meta, avance, semáforo y total de evidencias.
- Historiales de capturas, indicadores, POA y versiones de evidencia devuelven
  `{items,total,offset,limit}`; el orden predeterminado es descendente.
- `/bitacora` es canónico. `/auditoria` devuelve el mismo envelope y aparece deprecado.

## Entidades

- Evidencias incluyen `version_actual`; los archivos exponen una URL API autorizada, no la
  ruta interna.
- Usuarios incluyen notificación, área resumida, último acceso, fechas, configuración
  inicial de contraseña y `version`.
- Usuarios, catálogos, periodos, indicadores y capturas incluyen versión de concurrencia;
  una escritura obsoleta devuelve `409` con `details.version_actual`.

## Errores, archivos y reportes

- Todos los errores usan `code`, `message`, `details` y `request_id`, incluidos `422` y
  `500`; OpenAPI deja de publicar `HTTPValidationError` como contrato público.
- Los enlaces de evidencia aceptan HTTPS. Los archivos deben proceder de `/archivos`, que
  calcula MIME real, tamaño y SHA-256.
- Reportes vacíos generan XLSX y PDF válidos. OpenAPI declara JSON, XLSX y PDF.

## Operación

- `GET /health/live` comprueba que el proceso responde.
- `GET /health/ready` comprueba también PostgreSQL; `GET /health` se conserva como alias
  compatible de readiness.
- Los logs HTTP estructurados incluyen `request_id`, ruta, método, estado y duración; no
  registran headers, bodies, tokens, cookies ni contraseñas.
