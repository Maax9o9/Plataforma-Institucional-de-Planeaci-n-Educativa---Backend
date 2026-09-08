# Revisión de cédula completa, recordatorios y recuperación Docker

Fecha: 8 de septiembre de 2026. Migración: `0026_cedula_recordatorios`.

## Comparación con el Excel

Fuente: `3. POA 2026 Universidad Politecnica de Chiapas (1) (1).xlsm`.
Se revisaron las hojas `CEDULA-Objetivo 1` a `CEDULA-Objetivo 6`, sin ejecutar macros ni
modificar el archivo. La primera cédula de Objetivo 6 comprende el encabezado de B1
hasta los nombres/cargos de B42/P42 y B43/P43. Los otros objetivos repiten el formato
con distinta cantidad de indicadores y actividades.

| Parte del formato | Resultado en el backend |
| --- | --- |
| Programa Operativo Anual + año | El detalle y las emisiones incluyen título y año del ejercicio. |
| Formato 01 e institución | Incluidos en detalle y encabezado histórico. |
| Denominación y número de estrategia | Catálogo existente; número derivado de la clave. |
| Tipo de estrategia/proceso | Añadido, con las cinco opciones de `CEDULA-Objetivo 6!FP24:FP28`. |
| Área responsable | Existente; el nombre se conserva también en nuevas emisiones. |
| Nombre, fórmula y unidad del indicador | Existentes en catálogo. Se cotejaron los 11 nombres y fórmulas. |
| Meta institucional | Existente como `meta_institucional`. El año corresponde al ejercicio. |
| Contexto actual: año, línea base y porcentaje | Existentes: `linea_base_anio`, `linea_base_valor`, `porcentaje_actual`. |
| Contexto futuro: número y porcentaje a lograr | Existentes: `numero_a_lograr`, `porcentaje_a_lograr`; año del ejercicio. |
| Número y porcentaje alcanzado | Ambos se exigen explícitamente; sólo en las fechas de C3 y por Planeación. |
| Objetivo PSE 2025-2030 | Denominación del catálogo de objetivos; conservada en el snapshot. |
| Varias actividades con unidad y meta anual | Ya soportado, sin un máximo de una fila por cédula. |
| PROG/ALC, número y porcentaje por cuatrimestre | Seguimientos existentes; porcentajes calculados respecto a meta anual. |
| Justificación de desviaciones | Existente, con PATCH exclusivo de Planeación. |
| Área ejecutora por actividad | Existente; asignación/reasignación ahora genera aviso. |
| Descripción del alcance y efecto socioeconómico | Existente como `alcance_efecto_socioeconomico`. |
| Dos espacios de firma con nombre y cargo | Añadido `firmantes`; se congela en cada nueva emisión. |

Referencias de los catálogos cotejados: Objetivo 1 FQ34:FR35; Objetivo 2 FQ49:FR51;
Objetivo 3 FQ83:FR83; Objetivo 4 FQ28:FR29; Objetivo 5 FQ29:FR29;
Objetivo 6 FQ31:FR32. El catálogo reúne 11 indicadores, 24 estrategias y 150 actividades.

El modelo admite los datos del formato completo. Eso no significa que los borradores
existentes ya tengan toda su información capturada. Tampoco se implementó un PDF que
reproduzca exactamente la maqueta de Excel: los reportes PDF existentes son tabulares.
Los logotipos y líneas de firma son presentación del frontend. No hay firma electrónica
ni se habilitó el rol de revisor/validador pendiente.

## Reglas que cambiaron

### Encabezado y firmas

- POST/PATCH de cédula admiten `tipo_estrategia` y `firmantes`.
- `GET /api/v1/poa/catalogos/tipos-estrategia` devuelve Eficiencia, Eficacia, Pertinencia,
  Vinculación y Equidad de Género.
- Un borrador puede tener el bloque vacío. Para emitir debe tener tipo y dos firmantes.
- Cada firmante lleva nombre y cargo, hasta 200 caracteres no blancos.
- No se copian automáticamente nombres personales del Excel: Planeación ingresa los vigentes.
- Estos campos respetan el cierre estructural al terminar C1 y la excepción administrativa.
- Las emisiones anteriores no se modifican. Sólo las nuevas llevan el encabezado y firmas añadidos.

### Indicadores y total alcanzado

`PATCH /api/v1/poa/cedulas/indicadores/{id}/total-alcanzado` requiere:

```json
{
  "periodo_id": 103,
  "total_alcanzado": "126",
  "porcentaje_alcanzado": "42"
}
```

Debe ser el periodo C3 propio de la cédula, estar abierto y encontrarse dentro de sus
fechas, incluyendo inicio y fin. Se utiliza `America/Mexico_City`, no la zona del
servidor. Abrir el periodo anticipadamente no habilita la captura.

Pueden capturar `planeacion`, `planeacion_admin`, `admin_sistema` y `capturista_poa`
asignado al área activa exacta `Dirección de Planeación Educativa`. Otros capturistas,
revisores y consulta no pueden. La excepción administrativa al cierre de la estructura
no omite esta regla temporal específica del total alcanzado.

Se eliminó el cálculo automático `alcanzado / meta * 100` para indicadores. Las
fórmulas institucionales usan diferentes denominadores. Por ejemplo, 126 de una
población de 300 equivale a 42%, aunque la meta fuera otra. Planeación ingresa el
porcentaje ya calculado según la fórmula. No se evalúan fórmulas textuales arbitrarias.
Los porcentajes PROG/ALC de actividades sí mantienen su cálculo sobre la meta anual.

Al trasladar datos de Excel, distinguir valor almacenado y formato: una celda de
porcentaje con valor `0.83` se muestra como `83%`; los campos de porcentaje de la API
usan `83`, no `0.83`, para ese resultado. `meta_institucional` es una cantidad cuyo
significado depende del indicador, no un porcentaje impuesto a todos los casos.

## Avisos y correos

| Evento | Destinatarios | Condición |
| --- | --- | --- |
| Asignación o cambio de área ejecutora | Cuentas activas del área con permiso de captura | Sólo si se asigna un área o cambia la anterior. |
| Inicio de C1, C2 y C3 | Capturistas del área ejecutora | Seguimiento incompleto de esa actividad/cuatrimestre. |
| Una semana antes del cierre | Los mismos | Continúa incompleto. |
| Inicio y última semana de C3 | Planeación | Indicador sin número o porcentaje total alcanzado. |

Una actividad está completa cuando tiene alcanzado (cero válido), progreso, alcance y
al menos una evidencia vinculada de tipo archivo. Un archivo sólo subido, pero no
vinculado, no completa la actividad. La justificación no se añadió como condición nueva.

La programación corre al iniciar la API y luego cada seis horas. Puede ajustarse con
`REMINDER_CHECK_INTERVAL_SECONDS` (mínimo 300 segundos), sin ser obligatorio cambiar
el `.env`. Los avisos se producen en el primer chequeo de su ventana, no necesariamente
a medianoche exacta. Si la API estuvo caída el día inicial, se recupera la ventana vigente:
inicio hasta antes de la última semana, y última semana hasta el último día inclusive.
No envía recordatorios nuevos fuera del rango ni para periodos cerrados. Si el periodo
sigue en borrador, avisa que Planeación debe abrirlo; no lo abre automáticamente.

Se deduplican por periodo, elemento, usuario y ventana. Los datos de asignación y su
notificación se guardan en una misma transacción PostgreSQL. El correo sale después
del commit. Los pendientes de correo persisten y se reintentan con reservas temporales
para evitar envíos simultáneos entre procesos. Como en cualquier entrega SMTP sin
idempotencia del proveedor, una caída después del envío y antes de confirmar en la
base puede provocar un reenvío; no se promete entrega exactamente una vez.

El correo respeta `notificar_correo` y usuario activo. Con `EMAIL_PROVIDER=console`
se escribe una simulación en logs: no llega ningún correo real. Para entrega real se
requiere SMTP configurado en el `.env` de la VPS. No se añadieron secretos a GitHub ni
se modificó el `.env` local. Las notificaciones internas se consultan en `/notificaciones`.

## Docker y recuperación

- PostgreSQL ahora tiene `restart: unless-stopped` en ambos Compose; API y Nginx ya lo
  tenían y se conserva. Una parada manual explícita de contenedor se respeta.
- Se concede 60 s a PostgreSQL para terminar y se mantiene su volumen de datos.
- Se limitan y rotan los logs para evitar crecimiento ilimitado.
- La API tiene `init`, chequeo `/health/ready` y dependencia inicial de PostgreSQL sano.
- Se conserva `pool_pre_ping=True`, que permite descartar conexiones rotas y reconectar.
- Nginx vuelve a resolver `api` usando el DNS interno Docker cuando cambia su IP.
- Se añade un chequeo interno de Nginx no publicado en un puerto de la VPS.
- El volumen de evidencias usa una ruta fija y la imagen prepara el directorio con
  permisos del usuario no root. `.env`, claves y uploads no se incorporan a la imagen.
- La base local se publica sólo en `127.0.0.1:5433`; en producción no se publica PostgreSQL.
- Los montajes de Nginx/certificados fallan claramente si no existe su ruta, en lugar
  de crear directorios vacíos. Se mantiene el dominio `testeo.tech` configurado previamente.

Las políticas reinician un proceso que termina. Un estado `unhealthy` por sí solo
no causa reinicio automático en Docker Compose; el healthcheck es diagnóstico.
Tampoco una política repara disco lleno, falta persistente de RAM o corrupción. Sin
logs de la caída original no se atribuye una causa específica. Consultar la
[documentación de reinicio de Docker](https://docs.docker.com/engine/containers/start-containers-automatically/).

## Desplegar en la VPS

Después de subir estos cambios puede ejecutarse el workflow habitual, que ya migra y
levanta Compose conservando el `.env`. Los nombres `EC2_*` permanecen iguales.
Para hacerlo manualmente, tras actualizar el código y con respaldo de la base:

```bash
cd /opt/planeacion-api
docker compose -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.prod.yml build api
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml up -d --remove-orphans --wait --wait-timeout 120
docker compose -f docker-compose.prod.yml ps
curl -fsS https://testeo.tech/health/ready
```

No es necesario ejecutar `down`, y no usar `down -v` porque elimina volúmenes.
Verificar además `sudo systemctl is-enabled docker`; si está deshabilitado, el
administrador puede habilitarlo con `sudo systemctl enable --now docker`.

Estos cambios y pruebas se hicieron localmente; no se desplegó ni se modificó la VPS.
La integración completa de endpoints y ejemplos está en
[INTEGRACION_FRONTEND_POA.md](INTEGRACION_FRONTEND_POA.md).

## Verificación realizada

- Ruff y `git diff --check` sin errores.
- 54 pruebas aprobadas, incluyendo los adaptadores en memoria y PostgreSQL.
- Migraciones desde una base vacía hasta `0026`, en PostgreSQL local y contenedor aislado.
- Fechas anterior/inicial/final/posterior a C3, roles, porcentaje explícito y cero válido.
- Destinatarios por área, captura incompleta, evidencia faltante, recordatorios deduplicados,
  recuperación de ventana temporal y reintento/reserva de correo en PostgreSQL.
- Construcción de la imagen, validación de ambos Compose y `nginx -t`.
- Arranque aislado de PostgreSQL, API y Nginx con certificado de prueba y respuesta HTTPS.
- Detención inmediata del proceso PostgreSQL aislado: contador de reinicios pasó a 1,
  dato de prueba conservado y API conectada con contador de reinicios 0.
- Recreación de la API sin reiniciar Nginx: HTTPS respondió y el archivo de prueba persistió.

No se probó entrega a un buzón SMTP real ni se diagnosticó la causa histórica de la caída
de la VPS. El entorno temporal se retiró después de las comprobaciones.
