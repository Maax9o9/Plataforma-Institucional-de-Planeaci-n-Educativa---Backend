# Contrato de cédulas POA

Este flujo representa la cédula institucional completa, desde el encabezado
`PROGRAMA OPERATIVO ANUAL` hasta su emisión cuatrimestral. Es el único flujo POA activo;
las rutas del modelo anterior de procesos, objetivos y avances fueron retiradas.

## Modelo funcional

La cédula se crea una vez por ejercicio, estrategia y área responsable. Después se
completa mediante cuatro secciones:

1. **Estrategia:** objetivo derivado automáticamente, denominación de estrategia,
   área responsable y alcance o efecto socioeconómico.
2. **Indicadores:** indicador, nombre, fórmula y unidad provenientes del catálogo del
   formato; el usuario captura metas y línea base.
3. **Total alcanzado:** total y porcentaje alcanzado por indicador. La API solo admite
   esta captura con el tercer periodo de la cédula abierto y las fechas configuradas
   para ese periodo (no necesariamente septiembre a diciembre).
4. **Calendarización y seguimiento:** actividad predefinida, unidad, meta anual, área
   ejecutora y un seguimiento para cada cuatrimestre. El seguimiento registra por
   separado `progreso`, `alcance`, valor programado, valor alcanzado y evidencias.

El área ejecutora utiliza el catálogo institucional de áreas. El capturista POA solo
puede modificar seguimientos de actividades asignadas a su propia área.

Cada cédula admite múltiples indicadores y múltiples actividades. Se agrega cada elemento
con su endpoint `POST`; repetir la misma clave dentro de la misma cédula devuelve `409`.
El indicador debe pertenecer al objetivo y la actividad a la estrategia. El detalle y
las emisiones incluyen todas las filas, no sólo la primera. Para emitir se valida cada
actividad y, en el tercer cuatrimestre, el total de cada indicador.

Al crear la cédula se deben enviar exactamente tres rangos de fechas. La API crea un
periodo POA en borrador por cada rango y devuelve su `periodo_id`; Planeación abre y
cierra estos periodos mediante los endpoints normales de periodos. Los rangos deben
pertenecer al año del ejercicio, estar ordenados y no traslaparse.

La estructura puede corregirse hasta la fecha final del primer cuatrimestre, inclusive.
Desde el día siguiente quedan bloqueados la sección de estrategia, los datos de
indicadores y la configuración de actividades. `admin_sistema` y `planeacion_admin`
pueden omitir este bloqueo únicamente como mecanismo de corrección de emergencia. Los
seguimientos de las áreas continúan sujetos al periodo cuatrimestral abierto.

## Clasificación y respaldo

Cada emisión crea una instantánea inmutable con el contenido completo de las cuatro
secciones y los textos vigentes de sus catálogos. Se usa este nombre visible:

- `Cédula Objetivo 1 - Enero-Abril 2026`
- `Cédula Objetivo 1 - Mayo-Agosto 2026`
- `Cédula Objetivo 1 - Septiembre-Diciembre 2026`

El identificador de la emisión es la identidad técnica. Por eso dos áreas pueden tener
el mismo nombre visible sin perder trazabilidad.

Para emitir, el periodo generado para el cuatrimestre debe estar abierto y conservar las
fechas declaradas al crear la cédula. La
cédula debe tener al menos un indicador y una actividad; todas las actividades deben
tener seguimiento, progreso, alcance, valor alcanzado y al menos una evidencia del
cuatrimestre. En el tercero, además, todos los indicadores deben tener total alcanzado.

## Endpoints

Todos usan el prefijo `/api/v1` y requieren autenticación.

| Método | Ruta | Propósito |
| --- | --- | --- |
| `GET` | `/poa/catalogos/objetivos` | Lista los seis objetivos del formato. |
| `GET` | `/poa/catalogos/estrategias?objetivo_numero=6` | Filtra denominaciones de estrategia. |
| `GET` | `/poa/catalogos/indicadores?objetivo_numero=6` | Devuelve nombre, fórmula y unidad predefinidos. |
| `GET` | `/poa/catalogos/actividades?estrategia_clave=6.1` | Devuelve actividades predefinidas. |
| `POST` | `/poa/cedulas` | Crea la estructura anual. |
| `GET` | `/poa/cedulas` | Lista cédulas con filtros opcionales. |
| `GET` | `/poa/cedulas/{cedula_id}` | Consulta las cuatro secciones. |
| `PATCH` | `/poa/cedulas/{cedula_id}` | Corrige estrategia, área responsable o alcance antes del cierre estructural. |
| `POST` | `/poa/cedulas/{cedula_id}/indicadores` | Asocia un indicador válido para el objetivo. |
| `PATCH` | `/poa/cedulas/indicadores/{id}` | Corrige los valores configurables del indicador. |
| `PATCH` | `/poa/cedulas/indicadores/{id}/total-alcanzado` | Captura el total en el tercer cuatrimestre. |
| `POST` | `/poa/cedulas/{cedula_id}/actividades` | Asocia una actividad válida para la estrategia. |
| `PATCH` | `/poa/cedulas/actividades/{id}` | Corrige unidad, meta, área ejecutora u observaciones. |
| `PUT` | `/poa/cedulas/actividades/{id}/seguimientos/{1-3}` | Crea o actualiza el seguimiento cuatrimestral. |
| `PATCH` | `/poa/cedulas/seguimientos/{id}/justificacion` | Permite a Planeación mejorar únicamente la justificación. |
| `POST` | `/poa/cedulas/{cedula_id}/emisiones` | Emite el respaldo inmutable. |
| `GET` | `/poa/cedulas/{cedula_id}/emisiones` | Lista los respaldos de una cédula. |
| `GET` | `/poa/emisiones/{emision_id}` | Recupera una versión histórica exacta. |
| `GET` | `/poa/ejercicios` | Lista ejercicios anuales. |
| `GET` | `/poa/cedulas/actividades/{id}/historial` | Consulta la bitácora de la actividad actual. |
| `GET` | `/poa/reportes/por-cedula?cedula_id={id}` | Reporta actividades y seguimientos del modelo actual. |
| `POST` | `/archivos` | Carga PDF/JPG/PNG y devuelve la referencia segura. |
| `POST` | `/evidencias` | Vincula archivo o enlace al seguimiento. |
| `GET` | `/evidencias?entidad=poa_cedula_seguimiento&entidad_id={id}` | Lista sus evidencias con acceso por rol/área; no exige periodo abierto para lectura. |

Los roles `planeacion`, `planeacion_admin` y `admin_sistema` administran globalmente.
`capturista_poa` consulta cédulas relacionadas con su área y solo captura seguimientos
de actividades donde su área sea ejecutora. El capturista de la Dirección de Planeación
Educativa activa también consulta y configura estructuras antes del cierre, sin facultad
para crear, emitir ni omitir ese cierre. `revisor_poa` ya puede asignarse, pero su
flujo de revisión permanece pendiente. El comportamiento especial de `consulta` para
Rectoría también permanece pendiente.

La edición exclusiva de justificación no reabre los demás campos ni modifica snapshots
de emisiones anteriores. Una emisión nueva sí toma la redacción vigente.

Para adjuntar un archivo, primero se carga en `/archivos` y después se registra en
`/evidencias` con `entidad="poa_cedula_seguimiento"` y el ID del seguimiento. Las
emisiones exigen al menos una evidencia de tipo `archivo`; los enlaces son únicamente
complementarios. El snapshot inmutable incluye sus metadatos y versiones.

## Directorio institucional

`POST /usuarios` envía a cada persona un correo individual con el enlace de un solo uso
para crear su contraseña. Para las cuentas incluidas en la matriz institucional, el
backend resuelve internamente el área/unidad exacta y los roles aunque el cliente envíe
otros valores. No se expone un directorio de correos ni se crean cuentas automáticamente.
Los correos no incluidos conservan la asignación explícita existente.

## Persistencia

La migración `0022_refactor_cedulas_poa` crea catálogos normalizados, el agregado de
cédula, sus indicadores, actividades, seguimientos y emisiones JSONB. Al iniciar la API,
los catálogos extraídos del formato POA 2026 se insertan de forma idempotente.
`0023_roles_cuatrimestres` agrega los roles, las fechas propias de cada cédula y el nuevo
tipo de vínculo de evidencia.

Los módulos del POA anterior y sus rutas no están disponibles. Sus tablas históricas
permanecen en la BD sin uso operativo; no se convierten automáticamente a cédulas ni
se destruyen en el despliegue. La migración `0025_notificaciones_entidad` permite
referenciar periodos en las notificaciones sin reutilizar el enum de evidencias antiguo.
