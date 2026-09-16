# Integración de plantillas de correo

## Alcance

Los correos existentes usan el diseño institucional de la referencia proporcionada:
fondo azul, acentos turquesa, dragón y pie con logotipo de UPChiapas. Se adapta el
contenido al tipo de aviso y se saluda al destinatario por su nombre registrado.

El backend proporciona administración y vista previa. **La pantalla del frontend
debe integrarse usando estos endpoints**; no se ha creado una interfaz en otro repositorio.
Editar un texto cambia los futuros envíos de ese tipo para todos los destinatarios,
incluidos reintentos pendientes. No modifica correos ya enviados ni las notificaciones
internas. No es un editor HTML libre ni una plataforma de campañas.

## Archivos y arquitectura

```text
app/modules/email_templates/
  domain/                  # Contenido, validaciones y puertos
  application/             # Consulta, edición, restauración y composición
  infrastructure/
    models.py              # Persistencia de personalizaciones
    repository.py          # Adaptador de desarrollo en memoria
    sql_repository.py      # Adaptador PostgreSQL con control de versión
    rendering.py           # Renderizado seguro de HTML y texto plano
    templates/
      base.html            # Diseño compartido
      messages/*.json      # Un archivo de texto por cada tipo de correo
      assets/
        logo-horizontal.png
        logo-vertical.png
        dragon.png
  api/router.py
```

El logo horizontal se utiliza en el pie; el vertical queda disponible como recurso
institucional. Las imágenes originales no fueron alteradas. Se incluyen en el paquete
Python y en Docker; no dependen de archivos de Downloads ni de URLs públicas.

Los casos de uso de invitación y notificación dependen del puerto `EmailComposer`.
SMTP sigue siendo un adaptador separado. Los textos predeterminados viven en archivos;
las personalizaciones y sus versiones se guardan en `plantillas_correo`. Restaurar
vuelve a usar los archivos sin perder el contador de versión. Sin `DATABASE_URL`,
el modo de desarrollo en memoria no conserva cambios al reiniciar.

## Tipos de correo

| `tipo` | Uso |
| --- | --- |
| `invitacion` | Invitación para establecer contraseña. |
| `poa_actividad_asignada` | Asignación o reasignación de actividad al área ejecutora. |
| `poa_captura_inicio` | Inicio de captura cuatrimestral con pendientes. |
| `poa_captura_7d` | Última semana de captura con pendientes. |
| `poa_total_inicio` | Total y porcentaje alcanzado pendientes en C3. |
| `poa_total_7d` | Recordatorio de totales pendientes al cierre de C3. |
| `apertura_periodo` | Apertura de periodo en los flujos que emiten ese aviso. |
| `validacion` | Actualización de estado o validación de captura. |
| `rechazo` | Solicitud de correcciones. |
| `recordatorio_5d`, `recordatorio_3d`, `recordatorio_2d`, `recordatorio_1d` | Recordatorios existentes de periodos no POA. |
| `notificacion_general` | Diseño de respaldo para tipos de notificación aún no catalogados. |

Esto no agrega nuevos disparadores, no cambia ventanas de captura ni destinatarios,
y conserva preferencias de correo y deduplicación. Todos los correos generados por
el flujo actual de invitaciones/notificaciones pasan por la composición común.

## Permisos y autenticación

Base: `/api/v1/correos/plantillas` (o el prefijo configurado de la API).
Todas las operaciones requieren Bearer y rol `admin_sistema` o `planeacion_admin`.
Planeación sin rol administrativo, capturistas, revisores y consulta no pueden
editar ni previsualizar estos textos institucionales.

Los cambios/restauraciones se registran en bitácora con actor, tipo, campos afectados
y versión. La bitácora no copia cuerpos de correo ni tokens.

## Consultar

```http
GET /api/v1/correos/plantillas
GET /api/v1/correos/plantillas/poa_captura_7d
Authorization: Bearer ACCESS_TOKEN
```

La lista devuelve un arreglo; la consulta individual tiene esta forma:

```json
{
  "tipo": "poa_captura_7d",
  "etiqueta": "Recordatorio POA",
  "contenido": {
    "asunto": "Tu captura POA sigue pendiente",
    "titulo": "El cierre se acerca",
    "cuerpo": "Texto efectivo para este tipo de correo.",
    "texto_boton": "Completar mi captura"
  },
  "predeterminado": {
    "asunto": "Tu captura POA sigue pendiente",
    "titulo": "El cierre se acerca",
    "cuerpo": "Texto original incluido en el backend.",
    "texto_boton": "Completar mi captura"
  },
  "personalizada": false,
  "version": 0,
  "actualizado_por": null,
  "actualizado_en": null,
  "variables": ["nombre"]
}
```

Los cuerpos del ejemplo están abreviados. Usar siempre los textos y la `version`
que devuelva el servidor, no valores duplicados en el código del frontend.

## Editar texto predeterminado

```http
PATCH /api/v1/correos/plantillas/poa_captura_7d
Content-Type: application/json
Authorization: Bearer ACCESS_TOKEN
```

```json
{
  "version": 0,
  "contenido": {
    "asunto": "{{nombre}}, recuerda completar tu POA",
    "titulo": "Tu participación es importante",
    "cuerpo": "Te invitamos a revisar los pendientes de tu área.\n\nGracias por integrar las evidencias correspondientes.",
    "texto_boton": "Consultar la plataforma"
  }
}
```

Respuesta `200`: plantilla con versión incrementada y contenido efectivo.
Se pueden omitir los campos que no cambian. Enviar `null`, campos vacíos o un objeto
sin cambios se rechaza; restaurar es una operación separada.

| Campo editable | Máximo | Regla |
| --- | --- | --- |
| `asunto` | 180 caracteres | Una línea. |
| `titulo` | 160 caracteres | Una línea. |
| `cuerpo` | 6000 caracteres | Texto plano; línea vacía separa párrafos. |
| `texto_boton` | 60 caracteres | Una línea; no permite cambiar la URL. |

`{{nombre}}` se sustituye por el nombre de la persona al enviar. Es la única variable
editable; no se evalúan expresiones. El saludo con nombre se conserva aunque no
incluyas la variable en el texto. El HTML introducido se muestra como texto escapado,
no se ejecuta ni se interpreta como diseño. No enviar HTML de un editor enriquecido.

La fecha, cédula/actividad, aviso de pendientes, vigencia del enlace y URL se insertan
desde el backend en una sección separada que el editor no puede borrar o reemplazar.
El destino de notificaciones es `FRONTEND_URL`, no un deep link inventado; la pantalla
de destino debe permitir consultar las notificaciones y navegar al recurso.
La invitación usa `/establecer-contrasena?token=...` y conserva el token de un solo uso.

## Previsualizar sin guardar ni enviar

```http
POST /api/v1/correos/plantillas/invitacion/vista-previa
Content-Type: application/json
Authorization: Bearer ACCESS_TOKEN
```

```json
{
  "nombre_destinatario": "María López",
  "contenido": {
    "titulo": "Bienvenida a nuestra plataforma",
    "cuerpo": "Hola {{nombre}}, configura tu cuenta para comenzar."
  }
}
```

`contenido` es opcional y sólo afecta esa vista previa; sin él se usa la plantilla
efectiva. La respuesta incluye `asunto`, `html`, `texto` y `es_vista_previa: true`.
No envía correo, guarda cambios ni genera tokens reales. Los datos operativos son
ficticios y el botón apunta a `https://example.invalid/vista-previa`.

El HTML de vista previa contiene las imágenes como datos embebidos exclusivamente
para visualización en navegador. En SMTP se usan adjuntos relacionados CID.

Mostrar la vista en un iframe aislado, no inyectarla con `innerHTML` dentro de la
aplicación. Ejemplo React:

```tsx
<iframe
  title="Vista previa del correo"
  sandbox=""
  referrerPolicy="no-referrer"
  srcDoc={preview.html}
  style={{ width: mobile ? 375 : "100%", maxWidth: "100%", height: 900, border: 0 }}
/>
```

No añadir `allow-scripts`, `allow-same-origin` ni permiso de navegación superior.
Si el frontend tiene una CSP estricta, permitir las imágenes `data:` y estilos
inline dentro de su política de vista previa; no desactivar la CSP globalmente.

## Restaurar

```http
POST /api/v1/correos/plantillas/poa_captura_7d/restaurar
Content-Type: application/json
Authorization: Bearer ACCESS_TOKEN
```

```json
{"version": 1}
```

Confirmar con la persona antes de restaurar. Usar la versión actual del servidor.
La respuesta devuelve `personalizada=false` y una nueva versión; el contador no
vuelve a cero, para detectar ediciones concurrentes anteriores a la restauración.

## Errores para el frontend

Se conserva el sobre `code`, `message`, `details`, `request_id` de la API.

- `401`: sesión no válida.
- `403`: rol no autorizado.
- `404`: tipo de plantilla inexistente, también en vista previa.
- `409 CONFLICT`, `details.reason=EMAIL_TEMPLATE_VERSION_CONFLICT`: otro administrador
  editó la plantilla. Conservar el borrador local, reconsultar y ofrecer comparación;
  no actualizar la versión y reenviar automáticamente.
- `422 REQUEST_VALIDATION_ERROR`: forma, longitud o propiedades no admitidas.
- `422 BUSINESS_VALIDATION_ERROR`: texto vacío, variable desconocida o salto de línea
  en asunto/título/botón. Usar `details.field` para identificar el campo dentro de
  `contenido`; la validación HTTP puede usar `contenido.cuerpo` como ruta.
- `500/503` o desconexión: conservar edición; consultar el estado antes de repetir
  el guardado, pues la respuesta pudo perderse después de persistir.

Flujo recomendado: listar → seleccionar → editar localmente → previsualizar →
guardar con la versión consultada → reemplazar el formulario con la respuesta.

## Compatibilidad visual y entrega

- Diseño fluido de hasta 600 px, tablas de presentación, estilos principales inline,
  tipografía de sistema, botones amplios, altura variable y reglas para móvil.
- Logos con texto alternativo y fondo azul sólido como respaldo si se ignoran
  gradientes, imágenes de fondo o decoraciones. La información no depende del dragón.
- Correo MIME `multipart/alternative`: texto plano y HTML; imágenes CID relacionadas
  al HTML, no URLs locales ni imágenes base64 dentro del HTML enviado.
- Algunos clientes pueden ocultar imágenes, eliminar fondos, omitir bordes redondeados
  o aplicar sus propios colores. No se garantiza una representación idéntica en todos.
- La comprobación automatizada usa Edge/Chromium a 320, 375, 600 y 1024 px; no sustituye
  probar envíos reales en Gmail, Outlook y Apple Mail con la cuenta SMTP final.
- `EMAIL_PROVIDER=console` continúa simulando; no se cambió el proveedor, el `.env`
  ni se enviaron correos reales durante las pruebas.

Vistas de prueba locales, sin base ni envío:

```bash
python -m scripts.preview_email_templates --output var/email-previews
```

Abrir los HTML de esa carpeta. Los datos son ficticios y los archivos se excluyen
de Git. El script `scripts/check_email_layout.cjs` permite repetir las comprobaciones
visuales si el entorno de desarrollo dispone de Playwright y Edge.

## Migración y despliegue en la VPS

Nueva revisión: **`0028_plantillas_correo`**. Unifica los heads existentes
`0026_cedula_recordatorios` y `0027_revision_seguimiento_poa`, sin alterar las
migraciones anteriores. Al actualizar, Alembic ejecuta las ramas faltantes antes
de crear `plantillas_correo`. No usar `stamp` ni ejecutar el SQL manual además de Alembic.

Después de respaldar la base y actualizar el código en la VPS:

```bash
cd /opt/planeacion-api
docker compose -f docker-compose.prod.yml build api
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec -T api alembic current
```

Detenerse si algún comando falla. El resultado esperado es
`0028_plantillas_correo (head)`. El workflow de Actions ya ejecuta la migración;
no hace falta repetirla manualmente si el despliegue nuevo termina correctamente.

No se requieren nuevas variables de entorno ni secretos. `FRONTEND_URL` debe apuntar
al frontend real para que los botones e invitaciones lleven al lugar correcto.
Los textos en archivos JSON se cargan al iniciar: modificarlos en el repositorio
requiere desplegar/reiniciar. Las personalizaciones por API se consultan desde la
base al componer cada envío y no necesitan reiniciar contenedores.

## Resultado de la verificación local

- 96 pruebas aprobadas; 17 pruebas dependientes de PostgreSQL omitidas porque Docker
  estaba apagado. La ejecución real de la migración y las pruebas SQL siguen pendientes.
- Ruff y verificación de espacios de Git sin errores.
- 56 comprobaciones de presentación (14 plantillas por cuatro anchos), sin
  desplazamiento horizontal ni logos rotos; inspección visual de móvil y escritorio.
- Generación SQL de la cadena completa de Alembic correcta y un único head `0028`.
  La generación offline no demuestra la ejecución en una base real.
- Distribución wheel construida y verificada: incluye base HTML, 14 JSON y tres PNG.
- Envío MIME comprobado con SMTP simulado: texto, HTML y dos imágenes CID.
  No se enviaron mensajes reales ni se comprobó una bandeja de Gmail/Outlook.
