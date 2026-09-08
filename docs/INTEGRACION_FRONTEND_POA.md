# Integración del POA actual para frontend

Fecha de revisión: **8 de septiembre de 2026**.

Complemento de los últimos cambios, errores y comandos de migración:
[INTEGRACION_POA_PENDIENTES_Y_ERRORES.md](INTEGRACION_POA_PENDIENTES_Y_ERRORES.md).

Este documento describe el comportamiento implementado en el backend, no una propuesta.
El único POA activo es el de **cédulas**, con múltiples indicadores, múltiples actividades,
seguimientos por cuatrimestre, evidencias y emisiones históricas. Las funcionalidades
pendientes se identifican expresamente para no implementarlas por suposición en la interfaz.

## Índice

1. [Preparación y autenticación](#1-preparación-y-autenticación)
2. [Modelo e identificadores](#2-modelo-e-identificadores)
3. [Roles y permisos](#3-roles-y-permisos)
4. [Flujo de pantallas recomendado](#4-flujo-de-pantallas-recomendado)
5. [Catálogos y ejercicios](#5-catálogos-y-ejercicios)
6. [Crear, consultar y editar una cédula](#6-crear-consultar-y-editar-una-cédula)
7. [Indicadores y total alcanzado](#7-indicadores-y-total-alcanzado)
8. [Actividades y seguimiento](#8-actividades-y-seguimiento)
9. [Periodos y reglas de edición](#9-periodos-y-reglas-de-edición)
10. [Evidencias y archivos](#10-evidencias-y-archivos)
11. [Emisiones y respaldo histórico](#11-emisiones-y-respaldo-histórico)
12. [Reportes, dashboard e historial](#12-reportes-dashboard-e-historial)
13. [Cliente TypeScript de referencia](#13-cliente-typescript-de-referencia)
14. [Errores y sincronización](#14-errores-y-sincronización)
15. [Cambio privado de contraseña administrativa](#15-cambio-privado-de-contraseña-administrativa)
16. [Limitaciones y checklist de integración](#16-limitaciones-y-checklist-de-integración)

## 1. Preparación y autenticación

### Base y despliegue

- Base de negocio: `https://<host-de-la-api>/api/v1`.
- Swagger: `https://<host-de-la-api>/docs`.
- Contrato completo de la instancia desplegada: `https://<host-de-la-api>/openapi.json`.
- Las rutas de este documento son relativas a `/api/v1`, salvo indicación contraria.
- El backend desplegado debe contener las migraciones hasta `0026_cedula_recordatorios`.
  Si el servidor tiene una versión anterior, el contrato puede no coincidir.
- No se requiere importar Excel desde el frontend para empezar: los catálogos del formato
  POA ya están precargados por el backend. Se seleccionan elementos de esos catálogos.

Los IDs, fechas y textos de los ejemplos son ilustrativos. Sustituirlos por los que
devuelva la API; nunca fijarlos en el código del frontend.

### Sesión

1. `POST /auth/login` con `correo` y `contrasena`.
2. Conservar el `access_token` para enviar `Authorization: Bearer <token>`.
3. El refresh token se recibe en una **cookie HttpOnly**, no en el JSON ni accesible a JS.
4. Consultar `GET /auth/me` y usar sus `roles`, `area_id`, `area_nombre` y `activo`.
5. `POST /auth/refresh`, sin JSON, usa la cookie y devuelve un access token nuevo.
6. `POST /auth/logout` cierra la sesión. Enviar el Bearer y permitir el envío de cookies.

Login, petición:

```json
{
  "correo": "administrador@institucion.mx",
  "contrasena": "contraseña-del-usuario"
}
```

Login/refresh, respuesta `200` ilustrativa:

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 900
}
```

`expires_in` depende de la configuración. La respuesta de `/auth/me` incluye:
`id`, `correo`, `nombre`, `roles[]`, `area_id`, `area_nombre`, `activo`,
`notificar_correo`, `requiere_configurar_contrasena`, `ultimo_acceso`, `creado_en`,
`actualizado_en` y `version`. Los roles son una lista: un usuario puede tener varios.

### CORS y cookies: condición para que la sesión funcione

Para login y renovación desde un origen distinto usar `credentials: "include"` en fetch,
o `withCredentials: true` en Axios. No añadir manualmente un encabezado `Cookie` en el navegador.

El servidor debe autorizar el origen real del frontend. **`CORS_ALLOW_ALL=true` no es
compatible con este flujo de cookies entre orígenes**: en ese modo el backend desactiva
`allow_credentials`. Para integración con sesión usar `CORS_ALLOW_ALL=false` y un
`CORS_ORIGINS` explícito, por ejemplo:

```dotenv
CORS_ALLOW_ALL=false
CORS_ORIGINS=["http://localhost:5173"]
```

El origen es esquema + host + puerto, sin ruta. Para frontend y API en sitios distintos,
la cookie normalmente necesita `REFRESH_COOKIE_SAMESITE=none` y
`REFRESH_COOKIE_SECURE=true`, con HTTPS. Las políticas del navegador sobre cookies de
terceros aún pueden bloquearla; un despliegue bajo el mismo sitio evita esa dependencia.
No modificar estas variables desde el frontend: coordinarlas con quien despliega la API.

## 2. Modelo e identificadores

```text
Ejercicio anual
└── Cédula: estrategia + área responsable + tres rangos cuatrimestrales
    ├── Indicadores [0..N durante captura; mínimo 1 para emitir]
    │   └── Meta/línea base y total alcanzado del tercer cuatrimestre
    ├── Actividades [0..N durante captura; mínimo 1 para emitir]
    │   └── Seguimiento por cuatrimestre [máximo 1 por actividad y número]
    │       └── Evidencias [0..N] → versiones del archivo
    └── Emisiones [máximo 1 por cuatrimestre] → snapshot inmutable
```

La cédula es anual. **No crear otra cédula para el segundo o tercer cuatrimestre**:
se reutiliza su `cedula_id` y se generan emisiones distintas.

| Dato | Significado | Uso correcto |
| --- | --- | --- |
| `ejercicio_id` | ID de un ejercicio | No es el año `2027`. |
| `objetivo_numero` | Número de catálogo, de 1 a 6 | No es un antiguo `objetivo_id`. |
| `estrategia_clave` | Clave del catálogo, p. ej. `6.1` | Selección de estrategia. |
| `cedula_id` / `id` de cédula | Instancia anual | Consulta, edición y emisiones. |
| `indicador_clave` | Clave de catálogo, p. ej. `6.1.2` | Agregar a la cédula. |
| `id` de indicador de cédula | Fila asociada a una cédula | Editar metas y total alcanzado. |
| `actividad_clave` | Clave de catálogo, p. ej. `6.1.1` | Agregar a la cédula. |
| `id` de actividad de cédula | Fila asociada a una cédula | Editar configuración o guardar seguimiento. |
| `cedula_actividad_id` | Referencia desde un seguimiento | Vincular la fila a su actividad. |
| `cuatrimestre` / `numero` | 1, 2 o 3 | No confundir con `periodo_id`. |
| `periodo_id` | Periodo creado automáticamente para una cédula/cuatrimestre | Apertura, seguimiento, total y emisión. |
| `id` del seguimiento | Registro de captura | `entidad_id` al adjuntar evidencia. |
| `id` de evidencia | Registro con versiones | Versionar y consultar archivos. |
| `id` de emisión | Respaldo histórico | Abrir el documento histórico exacto. |

Los indicadores POA no son los indicadores PIDE de `/indicadores`. Tampoco reutilizar
IDs del POA anterior en endpoints de cédulas.

### Tipos compartidos

- Fechas de calendario: `YYYY-MM-DD`; timestamps: ISO 8601. No convertir una fecha de
  cuatrimestre a UTC si eso desplaza el día mostrado al usuario.
- Los campos decimales de los DTO de cédula se devuelven como **strings JSON**, o `null`.
  En peticiones se aceptan strings decimales como `"40.25"`; es la opción recomendada.
- Valores institucionales: no negativos, máximo 18 dígitos totales y 4 decimales.
- `porcentaje_actual` y `porcentaje_a_lograr`: de 0 a 100, máximo 2 decimales.
- `porcentaje_alcanzado` puede exceder 100. No limitarlo artificialmente en la interfaz.
- `null` significa dato no capturado; `"0"` es un resultado capturado de cero. No usar
  comprobaciones por truthiness para decidir si falta un valor.

## 3. Roles y permisos

Abreviaturas de la tabla:

- **Admin**: `admin_sistema` o `planeacion_admin`.
- **Planeación**: rol `planeacion`, sin privilegio administrativo adicional.
- **Capturista Plan.**: `capturista_poa` cuya área activa es exactamente
  `Dirección de Planeación Educativa`, comparada sin distinguir mayúsculas.
- **Capturista área**: `capturista_poa` asignado a otra área.

| Operación | Admin | Planeación | Capturista Plan. | Capturista área |
| --- | --- | --- | --- | --- |
| Crear ejercicio/cédula | Sí | Sí | No | No |
| Consultar cédulas | Todas | Todas | Todas | Si es área responsable o ejecutora de alguna actividad |
| Configurar estrategia, indicadores y actividades | Sí | Hasta cierre estructural | Hasta cierre estructural | No |
| Omitir cierre estructural por emergencia | Sí | No | No | No |
| Abrir, cerrar o reabrir periodos | Sí | Sí | No | No |
| Capturar seguimiento y adjuntar evidencia | Todas las actividades | Todas las actividades | Sólo actividades de su área ejecutora | Sólo actividades de su área ejecutora |
| Capturar total de indicadores en C3 abierto | Sí | Sí | Sí | No |
| Endpoint exclusivo de justificación | Sí | Sí | No | No |
| Emitir respaldo | Sí | Sí | No | No |
| Consultar reportes POA | Global | Global | Global | Filas de su área ejecutora |

Puntos importantes:

- `planeacion_admin` equivale administrativamente a `admin_sistema`.
- Las capacidades se suman si hay varios roles. Un usuario con `capturista_poa` y
  `planeacion_admin` no debe tratarse como capturista limitado.
- `responsable_area` es un rol de otros módulos: por sí solo **no habilita el nuevo POA**.
- `revisor_poa`, `consulta` y `rectoria`, sin otro rol habilitante, no tienen todavía
  flujo de revisión/consulta de cédulas. No mostrar botones de validar o rechazar POA.
- Los catálogos POA y la lista de áreas admiten lectura autenticada; eso no implica
  permiso para consultar una cédula o emitirla.
- Un capturista sin `area_id` no puede capturar una actividad sin área asignada.
- El detalle de una cédula autorizada contiene todas sus filas. **Poder verla completa
  no permite editar todas las actividades**. Restringir edición por `area_ejecutora_id`.
- El backend vuelve a validar los permisos en cada operación. Los controles visuales
  sólo ayudan al usuario; tratar `403` como una decisión definitiva del servidor.

## 4. Flujo de pantallas recomendado

1. **Entrada al módulo**: consultar `/auth/me`, ejercicios, áreas y catálogos.
2. **Listado anual**: elegir ejercicio y filtrar cédulas por objetivo o área responsable.
3. **Nueva cédula**: elegir estrategia, área responsable y los tres rangos de fechas.
4. **Detalle con cuatro secciones**:
   - Estrategia y área responsable.
   - Tabla de indicadores, con botón para agregar otra fila.
   - Total alcanzado por indicador, editable cuando corresponda C3.
   - Tabla de actividades y selector de cuatrimestre; cada actividad tiene su seguimiento.
5. **Evidencias por actividad/cuatrimestre**: guardar seguimiento, cargar y vincular archivos.
6. **Revisión previa a emisión**: listar campos/archivos faltantes de todas las actividades.
7. **Histórico**: consultar emisiones; renderizar el snapshot, no el detalle actual.
8. **Reportes**: mostrar datos actuales o exportarlos, diferenciándolos de una emisión.

Después de una mutación, actualizar el recurso devuelto y reconsultar el detalle de la
cédula cuando cambien sus filas. Mantener cachés separadas para detalle actual y emisiones.

## 5. Catálogos y ejercicios

### Endpoints iniciales

| Método | Ruta | Respuesta |
| --- | --- | --- |
| GET | `/catalogos/areas?activo=true` | `200`, arreglo de áreas activas. |
| GET | `/poa/ejercicios` | `200`, arreglo `{id, anio}`, ordenado por año. |
| POST | `/poa/ejercicios` | `201`, ejercicio creado. |
| GET | `/poa/catalogos/objetivos` | `200`, arreglo de objetivos. |
| GET | `/poa/catalogos/estrategias?objetivo_numero=6` | `200`, estrategias del objetivo. |
| GET | `/poa/catalogos/indicadores?objetivo_numero=6` | `200`, indicadores del objetivo. |
| GET | `/poa/catalogos/actividades?estrategia_clave=6.1` | `200`, actividades de la estrategia. |

No están paginados: reciben/devuelven arreglos, no un objeto `items`.

Crear ejercicio, cuerpo:

```json
{"anio": 2027}
```

Respuesta ilustrativa:

```json
{"id": 10, "anio": 2027}
```

El año debe estar entre 2000 y 2200. Duplicarlo produce `409`; recuperar el ejercicio
existente desde el listado, no intentar crear uno nuevo con cada cédula.

### Campos de catálogos

| Catálogo | Campos de cada elemento |
| --- | --- |
| Objetivo | `clave`, `numero`, `denominacion`, `activo` |
| Estrategia | `clave`, `objetivo_numero`, `denominacion`, `activo` |
| Indicador | `clave`, `objetivo_numero`, `nombre`, `formula`, `unidad_medida`, `activo` |
| Actividad | `clave`, `estrategia_clave`, `descripcion`, `activo` |
| Área | `id`, `codigo`, `nombre`, `area_padre_id`, `tipo`, `color`, `activo`, `version` |

Mostrar los textos que devuelve el backend y guardar la clave/ID. Deshabilitar opciones
inactivas. No enviar un nombre o una fórmula escrita a mano para sustituir el catálogo.
Los indicadores se filtran por **objetivo**, no por estrategia; las actividades, por estrategia.

## 6. Crear, consultar y editar una cédula

### Encabezado y bloque de firmas

Crear (`POST /poa/cedulas`) y actualizar (`PATCH /poa/cedulas/{id}`) admiten:

```json
{
  "tipo_estrategia": "Vinculación",
  "firmantes": [
    {"nombre": "Nombre de la persona titular", "cargo": "Rectoría"},
    {"nombre": "Nombre de la persona responsable", "cargo": "Secretaría Académica"}
  ]
}
```

El POST requiere además ejercicio, estrategia, área y cuatrimestres. Este bloque por
sí solo es válido para el PATCH. Consultar opciones en `GET /poa/catalogos/tipos-estrategia`:
`Eficiencia`, `Eficacia`, `Pertinencia`, `Vinculación`, `Equidad de Género`.

Se permite un borrador sin tipo ni firmantes. Si se proporcionan firmantes deben ser
exactamente dos (o `[]` para dejar el bloque vacío), con nombre y cargo no blancos de
hasta 200 caracteres. El PATCH reemplaza la lista completa; omitirla conserva la anterior.
Para emitir son obligatorios el tipo y los dos firmantes. Se aplica el cierre estructural
de C1 y su excepción administrativa también a estos campos.

Las cabeceras devuelven `tipo_estrategia` y `firmantes`. El detalle añade `anio`, `titulo`,
`institucion`, `formato` y `estrategia_numero`. Los nombres/cargos no son firmas electrónicas,
ni acreditan una aprobación. El frontend debe renderizar las líneas de firma del formato.

### Crear

`POST /poa/cedulas` → `201`.

```json
{
  "ejercicio_id": 10,
  "estrategia_clave": "6.1",
  "area_responsable_id": 8,
  "tipo_estrategia": null,
  "firmantes": [],
  "alcance_efecto_socioeconomico": "Comunidad universitaria",
  "cuatrimestres": [
    {"numero": 1, "fecha_inicio": "2027-01-01", "fecha_fin": "2027-04-30"},
    {"numero": 2, "fecha_inicio": "2027-05-01", "fecha_fin": "2027-08-31"},
    {"numero": 3, "fecha_inicio": "2027-09-01", "fecha_fin": "2027-12-31"}
  ]
}
```

Todos los campos son obligatorios salvo `alcance_efecto_socioeconomico`.

- Exactamente tres rangos, numerados 1, 2 y 3, sin repetir.
- Cada fecha debe pertenecer al año del ejercicio.
- `fecha_fin` debe ser posterior a `fecha_inicio`.
- El inicio de cada rango debe ser posterior al final del anterior.
- El backend permite rangos personalizados; no exige exactamente cuatro meses ni que
  cubran todos los días del año. No inventar esa validación como requisito del servidor.
- Área responsable existente y activa; estrategia existente y activa.
- La combinación ejercicio + estrategia + área responsable es única.
- No enviar `objetivo_numero`: se deriva de la estrategia.

La respuesta de creación es una cabecera, no el detalle con indicadores y actividades:

```json
{
  "id": 25,
  "ejercicio_id": 10,
  "objetivo_numero": 6,
  "estrategia_clave": "6.1",
  "area_responsable_id": 8,
  "alcance_efecto_socioeconomico": "Comunidad universitaria",
  "creado_por": 2,
  "version": 1,
  "creado_en": "2027-01-05T15:00:00Z",
  "actualizado_en": "2027-01-05T15:00:00Z",
  "cuatrimestres": [
    {"numero": 1, "fecha_inicio": "2027-01-01", "fecha_fin": "2027-04-30", "periodo_id": 101},
    {"numero": 2, "fecha_inicio": "2027-05-01", "fecha_fin": "2027-08-31", "periodo_id": 102},
    {"numero": 3, "fecha_inicio": "2027-09-01", "fecha_fin": "2027-12-31", "periodo_id": 103}
  ]
}
```

Guardar esos `periodo_id`. **No crear otros periodos para reemplazarlos**: los genéricos
con iguales fechas no se aceptan como el periodo propio de la cédula.

### Consultar

| Método | Ruta | Comportamiento |
| --- | --- | --- |
| GET | `/poa/cedulas?ejercicio_id=10&objetivo_numero=6&area_responsable_id=8` | Arreglo de cabeceras autorizadas; filtros opcionales. |
| GET | `/poa/cedulas/25` | Cabecera más `objetivo_denominacion`, `estrategia_denominacion`, `indicadores[]`, `actividades[]` y `seguimientos[]`. |

El listado no está paginado y no trae las filas. Una cédula recién creada tiene los
tres arreglos de filas vacíos en su detalle.

Los seguimientos vienen en un arreglo separado, **no anidados dentro de cada actividad**:

```ts
const seguimiento = detalle.seguimientos.find(
  s => s.cedula_actividad_id === actividad.id && s.cuatrimestre === cuatrimestre
);
```

### Editar sección de estrategia

`PATCH /poa/cedulas/25` → `200`, cabecera actualizada.

```json
{"alcance_efecto_socioeconomico": "Cobertura institucional actualizada"}
```

Admite `estrategia_clave`, `area_responsable_id` y `alcance_efecto_socioeconomico`.
Enviar al menos un campo no nulo. No admite modificar los rangos cuatrimestrales ni el
ejercicio. Cambiar estrategia se rechaza si los indicadores o actividades existentes
quedan fuera de su objetivo/estrategia; el error puede incluir sus IDs incompatibles.

La cabecera devuelve `version`, pero el PATCH de cédula **no recibe una versión esperada**.
No asumir que enviar `version` implementa control de concurrencia en este endpoint.

## 7. Indicadores y total alcanzado

### Agregar un indicador

`POST /poa/cedulas/25/indicadores` → `201`.

```json
{
  "indicador_clave": "6.1.2",
  "meta_institucional": "80",
  "linea_base_anio": 2026,
  "linea_base_valor": "60",
  "porcentaje_actual": "60.00",
  "numero_a_lograr": "100",
  "porcentaje_a_lograr": "80.00"
}
```

Sólo `indicador_clave` es obligatorio. Los demás campos son opcionales/nulos. La línea
base admite año de 2000 a 2200. El catálogo define nombre, fórmula y unidad.

Respuesta: `id`, `cedula_id`, `indicador_clave`, `nombre`, `formula`, `unidad_medida`,
los seis campos de captura del ejemplo, `total_alcanzado` y `porcentaje_alcanzado`.
Los últimos dos son `null` inicialmente.

Para un segundo indicador, repetir este POST con otra clave del mismo objetivo, por
ejemplo `6.1.3`. Repetir la misma clave en la misma cédula genera `409`.

### Editar sus datos

`PATCH /poa/cedulas/indicadores/40` → `200`, indicador actualizado.

```json
{"numero_a_lograr": "120", "porcentaje_a_lograr": "85.00"}
```

`40` es el `id` del indicador de cédula, no la clave de catálogo. Admite los seis campos
de captura del POST, no `indicador_clave`, nombre, fórmula ni total alcanzado. Omitir o
enviar `null` no borra valores existentes. No hay endpoint para eliminar esta fila.

### Total alcanzado: sección independiente

`PATCH /poa/cedulas/indicadores/40/total-alcanzado` → `200`.

```json
{"periodo_id": 103, "total_alcanzado": "126", "porcentaje_alcanzado": "42"}
```

- `periodo_id`, `total_alcanzado` y `porcentaje_alcanzado` son obligatorios.
- El periodo debe ser **el tercero de esa cédula** y estar abierto.
- La fecha institucional (`America/Mexico_City`) debe estar entre el inicio y fin de C3,
  ambos inclusive. Abrir anticipadamente el periodo no evita esta regla. Tampoco el Admin.
- Sólo Planeación: roles `planeacion`, `planeacion_admin`, `admin_sistema` o capturista
  del área activa exacta `Dirección de Planeación Educativa`. Las demás áreas reciben `403`.
- El porcentaje se ingresa según la fórmula del catálogo. Ya no se calcula dividiendo
  entre la meta; el denominador puede ser matrícula, cohortes, docentes u otra población.
- El ejemplo representa 126 de una población de 300 (=42%), no el cumplimiento de una meta.
- La fórmula textual del catálogo no es una expresión que el backend evalúe para este
  campo. No construir un motor de fórmulas suponiendo que forma parte del contrato.
- Capturar por separado el total de **cada** indicador. La emisión de C3 exige todos.

## 8. Actividades y seguimiento

### Agregar actividad

`POST /poa/cedulas/25/actividades` → `201`.

```json
{
  "actividad_clave": "6.1.1",
  "unidad_medida": "Eventos",
  "meta_anual": "100",
  "area_ejecutora_id": 12,
  "observaciones": "Programación institucional"
}
```

Obligatorios: `actividad_clave`, `unidad_medida`, `meta_anual`.
Opcionales: `area_ejecutora_id`, `observaciones`.

La actividad debe pertenecer a la estrategia de la cédula. El texto `descripcion` se
obtiene del catálogo; la unidad se captura aquí, a diferencia de la unidad del indicador.
Si se asigna un área, debe existir y estar activa. Sin área ejecutora sólo los roles
globales habilitados pueden capturar; no significa que cualquier área pueda hacerlo.

Respuesta: `id`, `cedula_id`, `actividad_clave`, `descripcion`, `unidad_medida`,
`meta_anual`, `area_ejecutora_id`, `observaciones`.

Agregar tantas filas como se requieran mediante POSTs separados. Repetir la misma clave
en una cédula produce `409`. Guardar el `id` de cada fila para sus seguimientos.

### Editar configuración

`PATCH /poa/cedulas/actividades/70` → `200`.

```json
{"meta_anual": "110", "area_ejecutora_id": 12}
```

Admite unidad, meta anual, área ejecutora y observaciones. No cambia la clave del catálogo.
Requiere al menos un campo no nulo y está sujeto al cierre estructural.
`area_ejecutora_id: null` **no desasigna** un área ya configurada.
Para vaciar observaciones puede enviarse `"observaciones": ""`.

### Crear o reemplazar seguimiento

`PUT /poa/cedulas/actividades/70/seguimientos/1` → `200`, tanto al crear como al actualizar.

```json
{
  "periodo_id": 101,
  "programado": "40",
  "alcanzado": "35",
  "justificacion_desviacion": "Se reprogramaron cinco eventos.",
  "progreso": "Se realizaron 35 eventos.",
  "alcance": "Participación de la comunidad universitaria."
}
```

Obligatorios: `periodo_id` y `programado`. Los otros campos son opcionales para permitir
un guardado incompleto. No hay propiedad `estado` en el seguimiento: no enviar
`borrador`, `enviado`, `validado` ni `rechazado`.

Respuesta ilustrativa, con meta anual de `100`:

```json
{
  "id": 90,
  "cedula_actividad_id": 70,
  "cuatrimestre": 1,
  "periodo_id": 101,
  "capturado_por": 15,
  "programado": "40",
  "programado_porcentaje": "40.00",
  "alcanzado": "35",
  "alcanzado_porcentaje": "35.00",
  "justificacion_desviacion": "Se reprogramaron cinco eventos.",
  "progreso": "Se realizaron 35 eventos.",
  "alcance": "Participación de la comunidad universitaria."
}
```

Los porcentajes se calculan sobre **la meta anual**, no como `alcanzado/programado`.
Si la meta anual es cero, esos porcentajes son `null`.

**El PUT reemplaza los campos del seguimiento.** Si se omiten `alcanzado`, `progreso`,
`alcance` o justificación en una actualización, quedan nulos; no se preservan como en
un PATCH. Enviar el estado completo de la fila y evitar que un formulario desactualizado
borre una justificación que otra persona acaba de mejorar. El último editor queda en
`capturado_por`. No hay versión esperada en este PUT.

La clave lógica es actividad + cuatrimestre. Volver a guardar actualiza ese registro;
no crea otra fila histórica. Las evidencias se relacionan con su `id`.

### Editar únicamente la justificación

`PATCH /poa/cedulas/seguimientos/90/justificacion` → `200`, seguimiento actualizado.

```json
{"justificacion_desviacion": "Redacción revisada por Planeación sobre la reprogramación."}
```

Sólo Admin y rol `planeacion`. Requiere un seguimiento ya creado y texto no vacío.
No modifica progreso, alcance, valores ni evidencias. Puede usarse después del cierre
estructural **y con el periodo cerrado**. No actualiza emisiones ya guardadas.

Este endpoint permite mejorar la redacción; el PUT del seguimiento sigue admitiendo
justificación por el área capturista mientras su periodo esté abierto.

## 9. Periodos y reglas de edición

### Consultar el estado real

`GET /periodos?tipo=poa&anio=2027` → `200`, arreglo.

Cada periodo tiene `id`, `tipo`, `periodicidad`, `anio`, `etiqueta`, `fecha_inicio`,
`fecha_limite`, `estado`, `motivo_reapertura`, `reabierto_por`, `version`.

Unir esa respuesta con los `periodo_id` guardados dentro de `detalle.cuatrimestres`.
No elegir simplemente el primer periodo abierto del año: puede pertenecer a otra cédula.
La fecha final se llama `fecha_fin` dentro de la cédula y `fecha_limite` en `/periodos`.

### Administrar periodos

| Método | Ruta | Cuerpo / respuesta |
| --- | --- | --- |
| POST | `/periodos/101/abrir?version=1` | Sin cuerpo; `200`, periodo actualizado. |
| POST | `/periodos/101/cerrar?version=2` | Sin cuerpo; `200`, periodo actualizado. |
| POST | `/periodos/101/reabrir` | Motivo y versión opcional; `200`, periodo actualizado. |

Las versiones de la URL son ilustrativas. Enviar la última versión conocida; si hay
conflicto, reconsultar. Reapertura, ejemplo:

```json
{"motivo": "Corrección autorizada por Planeación", "version": 3}
```

Estados: `borrador` → `abierto` → `cerrado`; reabrir lleva un cerrado a abierto y exige
motivo. Usar `/reabrir` para un cerrado, no asumir que `/abrir` es equivalente.

### Dos restricciones distintas

| Operación | Condición temporal implementada |
| --- | --- |
| Crear/editar estructura | Permitida hasta el fin de C1 inclusive; Admin puede omitir este bloqueo. |
| Seguimiento y escritura de evidencias | Periodo propio del cuatrimestre abierto. |
| Total alcanzado | Tercer periodo propio abierto. |
| Emitir | Periodo propio abierto y contenido completo. |
| Justificación exclusiva | No depende del estado del periodo ni del cierre estructural. |
| Leer cédula, emisiones o evidencias | Permiso de acceso; no exige periodo abierto. |

La fecha del servidor es la autoridad del cierre estructural. Ese control no bloquea
la estructura antes del inicio de C1. La apertura/cierre de periodos es explícita: la API
no los abre/cierra automáticamente por reloj. El seguimiento de actividades sigue
dependiendo del estado abierto. El **total de indicadores sí exige adicionalmente estar
dentro de las fechas de C3**, utilizando la zona horaria institucional.

El privilegio de Admin **sólo omite el cierre estructural**: no salta la exigencia de
periodo abierto, no permite total en C1/C2 ni emitir con datos incompletos. Reabrir un
periodo tampoco reabre la estructura vencida para un capturista.

## 10. Evidencias y archivos

### Secuencia obligatoria

1. Guardar el seguimiento y obtener su `id`.
2. `POST /archivos` con multipart.
3. `POST /evidencias` para vincular ese archivo al seguimiento.
4. Reconsultar las evidencias vinculadas.

La carga del archivo por sí sola **no cuenta como evidencia**. Si falla el paso 3,
mantener el resultado del paso 2 para reintentar el vínculo, sin marcarlo como completado.

### Subir archivo

`POST /archivos` → `201`. El campo multipart se llama **`archivo`**.

```ts
const formData = new FormData();
formData.append("archivo", file);
const uploaded = await apiJson<ArchivoSubido>("/archivos", {
  method: "POST",
  body: formData
});
```

No fijar `Content-Type` manualmente: el navegador agrega el boundary multipart.
Tipos admitidos: PDF, PNG y JPEG, comprobados por firma del archivo. No admite XLSX,
DOCX o ZIP como evidencias de archivo. Límite predeterminado: **10 MiB (10 485 760 bytes)**,
configurable por servidor mediante `UPLOAD_MAX_BYTES`; respetar `413` y su `max_bytes`.

Respuesta de carga, forma ilustrativa:

```json
{
  "id": "0123456789abcdef0123456789abcdef",
  "ruta": "0123456789abcdef0123456789abcdef.pdf",
  "mime_type": "application/pdf",
  "tamanio_bytes": 20480,
  "checksum_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

Reutilizar exactamente los metadatos recibidos. No calcularlos ni inventarlos como en
este ejemplo ilustrativo.

### Vincular al seguimiento

`POST /evidencias` → `201`.

```json
{
  "nombre": "Informe del primer cuatrimestre",
  "descripcion": "Respaldo del progreso y alcance reportados.",
  "fecha": "2027-04-30",
  "tipo": "archivo",
  "ruta_o_url": "0123456789abcdef0123456789abcdef.pdf",
  "mime_type": "application/pdf",
  "tamanio_bytes": 20480,
  "checksum_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "entidad": "poa_cedula_seguimiento",
  "entidad_id": 90
}
```

`entidad_id` es el seguimiento, **no** la cédula, actividad ni periodo.
La respuesta contiene `id`, `nombre`, `descripcion`, `fecha`, `tipo`, `subida_por` y
`version_actual`. Esta última contiene `numero`, `ruta_o_url`, `mime_type`,
`tamanio_bytes`, `checksum_sha256`, `fecha` y `usuario_id`.

En respuestas, un archivo suele exponerse como ruta relativa
`/api/v1/archivos/<nombre.pdf>`. En la petición de vínculo, usar la `ruta` original de
la carga. Los enlaces `tipo="enlace"` son complementarios: no sustituyen el archivo
obligatorio para emitir.

### Consultar, descargar y versionar

| Método | Ruta | Respuesta |
| --- | --- | --- |
| GET | `/evidencias?entidad=poa_cedula_seguimiento&entidad_id=90` | `200`, arreglo de evidencias con versión actual. |
| GET | `/archivos/{file_name}` | Archivo binario autorizado. |
| GET | `/evidencias/50/versiones?offset=0&limit=10&order=desc` | `200`, `{items, total, offset, limit}`. |
| PUT | `/evidencias/50/version` | `204`, nueva versión conservando las anteriores. |

Para versionar, cargar primero el nuevo archivo y enviar:

```json
{
  "ruta_o_url": "fedcba9876543210fedcba9876543210.pdf",
  "mime_type": "application/pdf",
  "tamanio_bytes": 25000,
  "checksum_sha256": "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
}
```

Para PDF o imágenes protegidas, obtener un `Blob` con el Bearer y crear una URL temporal
con `URL.createObjectURL`. Un `<a href>` o `<img src>` directo no envía el Bearer del
cliente HTTP. Revocar las URLs temporales cuando dejen de usarse.

Un archivo no vinculado devuelve `404` al intentar descargarlo. Un cambio de área o rol
puede quitar acceso incluso al usuario que lo subió. No exponer rutas físicas del servidor
ni agregar el token a la URL.

## 11. Emisiones y respaldo histórico

### Emitir

`POST /poa/cedulas/25/emisiones` → `201`.

```json
{"cuatrimestre": 1, "periodo_id": 101}
```

Antes de habilitar la confirmación, mostrar una lista de pendientes:

- Periodo correcto y abierto.
- Al menos un indicador y una actividad.
- Tipo de estrategia y dos firmantes con nombre y cargo.
- **Cada actividad** tiene seguimiento del cuatrimestre elegido.
- Cada seguimiento tiene `alcanzado` distinto de `null`, `progreso` y `alcance` no vacíos.
- Cada seguimiento tiene al menos una evidencia de tipo archivo.
- Para C3, **cada indicador** tiene `total_alcanzado` y `porcentaje_alcanzado` no nulos.

La justificación no es obligatoria para emitir según la regla actual, incluso si los
valores difieren. Se exigen los datos de los firmantes, no una firma digital ni una
aprobación del revisor. El servidor realiza la comprobación definitiva y devuelve `422`
si falta algo; algunos errores incluyen `details.actividad_ids`.

La respuesta tiene:

| Campo | Descripción |
| --- | --- |
| `id`, `cedula_id` | Identificadores de emisión y cédula. |
| `cuatrimestre`, `periodo_id` | Corte respaldado. |
| `nombre` | Nombre descriptivo generado por backend. |
| `snapshot` | Contenido histórico serializado de las cuatro secciones. |
| `emitido_por`, `emitido_en` | Autor y timestamp de emisión. |

El nombre usa etiquetas `Enero-Abril`, `Mayo-Agosto` o `Septiembre-Diciembre`, según el
número; por ejemplo `Cédula Objetivo 6 - Enero-Abril 2027`. **Las fechas personalizadas
se consultan en los rangos**, no se deducen del nombre, cuya etiqueta es fija.

Sólo hay una emisión por cédula/cuatrimestre: repetirla da `409`. Emitir C2/C3 no exige
que se hayan emitido previamente los anteriores. Emitir no cierra automáticamente
el periodo y no congela la cédula editable; el respaldo sí es inmutable.

### Consultar histórico

| Método | Ruta | Respuesta |
| --- | --- | --- |
| GET | `/poa/cedulas/25/emisiones` | `200`, arreglo de emisiones, incluyendo snapshots. |
| GET | `/poa/emisiones/60` | `200`, una emisión exacta. |

No usar `nombre` como clave única; distintas áreas pueden tener nombres iguales.
La vista histórica debe renderizar exclusivamente `snapshot`. Consultar los catálogos
o el detalle actual para reemplazar sus textos alteraría lo que se está mostrando.

### Estructura del snapshot

No tiene los mismos nombres de campo que el DTO del detalle. Algunas claves son de
dominio, en inglés. Crear un adaptador separado para la vista histórica.

| Clave superior | Contenido |
| --- | --- |
| `encabezado` | Título, año, institución, formato, número y tipo de estrategia. |
| `bloque_firmas[]` | `name` y `position` de los dos firmantes al emitir. |
| `version_formato` | Actualmente `POA-2026`; identificar la versión del formato. |
| `cuatrimestre` | Corte emitido. |
| `duracion_cuatrimestres[]` | `form_id`, `quarter`, `period_id`, `starts_on`, `ends_on` y metadatos. |
| `seccion_1_estrategia` | `cedula`, `objetivo`, `estrategia`, área y alcance. |
| `seccion_2_indicadores[]` | Filas de indicador: `indicator_key`, `target_value`, etc., más `catalogo`. |
| `seccion_3_total_alcanzado[]` | `cedula_indicador_id`, `indicador_clave`, `total_alcanzado`, `porcentaje_alcanzado`. |
| `seccion_4_calendarizacion_y_seguimiento[]` | Actividades con `activity_key`, `annual_goal`, `catalogo` y `seguimientos[]`. |

En el histórico, los seguimientos sí están anidados en sus actividades. Cada uno usa
`scheduled`, `achieved`, `progress`, `scope`, `deviation_justification`, y contiene
`evidencias[]` con `versiones[]`. Se incluyen seguimientos de cuatrimestres **menores o
iguales** al corte; no los posteriores. Las secciones de indicadores y configuración
reflejan el estado vigente en el momento de emitir.

Los decimales del snapshot también se serializan como strings. Las referencias de
archivos guardadas en versiones históricas pueden ser nombres internos (`path_or_url`);
resolverlos hacia el endpoint autorizado de archivos, no usarlos como ruta del frontend.

No existe un endpoint para reemplazar/eliminar emisiones ni para exportar la emisión
histórica como PDF ya maquetado con el formato institucional. Los reportes PDF siguientes
son reportes de captura actual, no esa impresión oficial del snapshot.

## 12. Reportes, dashboard e historial

### Reportes actuales

Todos son `GET`, devuelven `200` y admiten `formato=json|xlsx|pdf`:

| Ruta | Uso |
| --- | --- |
| `/poa/reportes/cuatrimestral` | Actividades y seguimientos; enviar `periodo_id` para un corte. |
| `/poa/reportes/anual` | Filas por cuatrimestre; agrega `filtros.completo`. |
| `/poa/reportes/por-cedula` | Enviar `cedula_id`. |
| `/poa/reportes/por-area` | Enviar `area_id`, que significa área ejecutora. |
| `/poa/reportes/estatus` | Resumen por actividad y filtro `tipo`. |
| `/poa/reportes/evidencias-faltantes` | Actividades/cuatrimestres sin archivo vinculado, incluso sin captura. |
| `/poa/reportes/ejecutivo` | Filas de captura actuales; no concede permiso especial a Rectoría. |

Filtros admitidos: `periodo_id`, `ejercicio_id`, `cedula_id`, `objetivo_numero`,
`estrategia_clave`, `area_id`, `tipo`, `formato`. Son opcionales. El nombre del endpoint
no aplica por sí solo el filtro: sin `periodo_id`, el cuatrimestral puede incluir los tres
cuatrimestres; sin `cedula_id`, `por-cedula` puede incluir varias cédulas autorizadas.

Un filtro antiguo/desconocido como `proceso_id` produce `422`. No enviar `offset` o
`limit`: los reportes no tienen paginación. Para capturistas de áreas, el servidor
fuerza el área propia aunque se envíe otra.

JSON devuelve `{tipo, filtros, filas}`. Los filtros de respuesta incluyen
`fuente: "cedulas_actuales"` y `datos: "captura_actual"`.

Las filas ordinarias incluyen identificadores de cédula/ejercicio/objetivo/estrategia,
área responsable y ejecutora, actividad y descripción, `meta_anual`, `cuatrimestre`,
`periodo_id`, `seguimiento_id`, `programado`, `alcanzado`, `progreso`, `alcance`,
`justificacion_desviacion`, `archivos_evidencia`, `estado` y `cedula_emitida`.
`estado` es `capturado` o `sin_captura`; no expresa validación.

El reporte `estatus` usa `cumplidas`, `atrasadas`, `pendientes`:

- Cumplidas: hay seguimientos seleccionados y la suma alcanzada llega a la meta anual.
- Atrasadas: en otro caso, la suma alcanzada es menor que la programada.
- Pendientes: los demás casos.

Ese cálculo no compara la fecha actual contra un vencimiento. Sin `tipo` se devuelven
todos los estatus; `tipo` sólo filtra el reporte de estatus. Allí las filas resumen incluyen
`cuatrimestres_capturados` y `cuatrimestres_emitidos` en lugar de un seguimiento individual.
El anual sólo marca `completo=true` si hay cédulas incluidas y todas tienen las tres emisiones.

Las exportaciones son binarias, no JSON. Descargar con Bearer, obtener un Blob y asignar
un nombre local como `poa-cuatrimestral.xlsx`. No depender de poder leer
`Content-Disposition` desde JS: el CORS actual no lo expone.

### Dashboard

- `GET /dashboards/planeacion`: Planeación o Admin; filtros `instrumento_id`, `area_id`, `periodo_id`.
- `GET /dashboards/mi-area`: rol `capturista_poa` o `responsable_area`; no requiere filtros.
- La respuesta contiene `rol`, `resumen`, `indicadores`, `poa`, `enlaces`.
- `poa` contiene resúmenes de actividades del modelo actual. En `resumen` se usan
  `cedulas_poa`, `actividades_poa` y `seguimientos_poa_capturados`.
- Los contadores antiguos `avances_poa_por_estado`/avances validados ya no forman parte
  del contrato. No mezclar los estados de capturas de indicadores con los de POA.
- `instrumento_id` afecta la parte de indicadores, no es un filtro de las cédulas POA.

### Historial

`GET /poa/cedulas/actividades/70/historial?offset=0&limit=10&order=desc`
devuelve `{items, total, offset, limit}`. Consulta eventos de la actividad actual,
con autorización por rol y área; no es el antiguo historial de avances validados.

## 13. Cliente TypeScript de referencia

Ejemplo mínimo para un frontend cuyo origen ya está autorizado con cookies. La gestión
de estado de sesión, renovación coordinada y UI dependen de la aplicación.

```ts
type ApiErrorBody = {
  code: string;
  message: string;
  details: unknown;
  request_id: string | null;
};

class ApiError extends Error {
  constructor(public status: number, public payload: ApiErrorBody) {
    super(payload.message);
  }
}

const API_ORIGIN = "https://api.ejemplo.mx"; // Configurar por entorno.
const API_BASE = `${API_ORIGIN}/api/v1`;
let accessToken: string | null = null; // Memoria, nunca imprimirlo en logs.

async function apiResponse(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (typeof init.body === "string") headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: "include"
  });
  if (!response.ok) {
    const payload: ApiErrorBody = await response.json().catch(() => ({
      code: "HTTP_ERROR", message: `Error HTTP ${response.status}`,
      details: null, request_id: response.headers.get("X-Request-ID")
    }));
    throw new ApiError(response.status, payload);
  }
  return response;
}

async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await apiResponse(path, init);
  return response.status === 204 ? undefined as T : response.json();
}

type Session = { access_token: string; token_type: string; expires_in: number };
async function login(correo: string, contrasena: string): Promise<void> {
  const session = await apiJson<Session>("/auth/login", {
    method: "POST", body: JSON.stringify({ correo, contrasena })
  });
  accessToken = session.access_token;
}

// Compartir esta promesa entre peticiones concurrentes evita rotar dos veces la cookie.
let refreshPromise: Promise<void> | null = null;
function refreshSession(): Promise<void> {
  if (!refreshPromise) {
    refreshPromise = apiJson<Session>("/auth/refresh", { method: "POST" })
      .then(session => { accessToken = session.access_token; })
      .catch(error => { accessToken = null; throw error; })
      .finally(() => { refreshPromise = null; });
  }
  return refreshPromise;
}

type ArchivoSubido = {
  id: string; ruta: string; mime_type: string;
  tamanio_bytes: number; checksum_sha256: string;
};
type Evidencia = { id: number; nombre: string; version_actual: unknown };

async function attachFile(
  seguimientoId: number, file: File, nombre: string, descripcion: string, fecha: string
): Promise<Evidencia> {
  const body = new FormData();
  body.append("archivo", file);
  const uploaded = await apiJson<ArchivoSubido>("/archivos", { method: "POST", body });
  // En una UI real, conservar uploaded si falla el vínculo, para poder reintentarlo.
  return apiJson<Evidencia>("/evidencias", {
    method: "POST",
    body: JSON.stringify({
      nombre, descripcion, fecha, tipo: "archivo",
      entidad: "poa_cedula_seguimiento", entidad_id: seguimientoId,
      ruta_o_url: uploaded.ruta, mime_type: uploaded.mime_type,
      tamanio_bytes: uploaded.tamanio_bytes, checksum_sha256: uploaded.checksum_sha256
    })
  });
}

async function downloadReport(cedulaId: number): Promise<void> {
  const response = await apiResponse(
    `/poa/reportes/por-cedula?cedula_id=${cedulaId}&formato=xlsx`
  );
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = `poa-cedula-${cedulaId}.xlsx`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
```

No hay reintento automático en este ejemplo. Si se incorpora un interceptor, renovar
como máximo una vez ante expiración y no interceptar recursivamente `/auth/refresh`.
Un `401` del cambio de contraseña puede significar contraseña actual incorrecta, no
token vencido. Si la renovación falla, volver al login. No repetir indiscriminadamente
POSTs tras errores de red: el servidor pudo completar la operación sin que llegara la respuesta.

Para descargar una `ruta_o_url` que ya comienza con `/api/v1/archivos/`, resolverla
contra `API_ORIGIN`, no concatenar de nuevo `/api/v1`. Enviar el Bearer sólo a la API
confiable; nunca a un enlace externo almacenado como evidencia.

## 14. Errores y sincronización

Formato habitual:

```json
{
  "code": "BUSINESS_VALIDATION_ERROR",
  "message": "Todas las actividades deben tener seguimiento del cuatrimestre.",
  "details": {"actividad_ids": [71, 72]},
  "request_id": "req_ejemplo"
}
```

| HTTP | Acción recomendada |
| --- | --- |
| 401 | Revisar sesión; renovar una vez si corresponde o volver al login. |
| 403 | No hay permiso sobre esa operación/recurso. No reintentar como otra área. |
| 404 | Recurso inexistente, archivo no vinculado o ruta antigua retirada. |
| 409 | Duplicado o conflicto de versión. Reconsultar antes de ofrecer otro intento. |
| 413 | Archivo demasiado grande; usar `details.max_bytes` si aparece. |
| 415 | Archivo/formato no admitido. |
| 422 | Petición o regla de negocio inválida: mostrar mensaje y detalles por campo/fila. |
| 429 | Respetar `Retry-After`; evitar más intentos de credenciales. |
| 500 | Mensaje seguro, conservar `request_id` para soporte; no asumir que nada se guardó. |
| 503 | Servicio temporalmente no disponible; conservar captura y respetar `Retry-After` cuando exista. |

`details` puede ser `null`, objeto o arreglo. Para validación HTTP, sus elementos
incluyen `loc`, `field`, `msg`, `type`; no vienen contraseñas ni el cuerpo original. No depender
de coincidencias de texto para implementar permisos: usar estado HTTP y `code`.
Para emisión incompleta, `details.errors` contiene todos los pendientes de contenido
con campo e IDs de actividad/indicador. Consultar los ejemplos y `details.reason` en
[el complemento de errores](INTEGRACION_POA_PENDIENTES_Y_ERRORES.md).

El detalle, periodos y evidencias no se actualizan por WebSocket. Reconsultar al recuperar
el foco, después de operaciones relevantes o mediante una estrategia de refresco elegida
por el frontend. Deshabilitar el botón mientras se guarda y confirmar antes de emitir.

La captura se guarda por recurso: no existe un POST que persista toda la cédula con todas
sus filas y archivos de una sola vez. No mostrar «todo guardado» si falló alguna petición.

## 15. Cambio privado de contraseña administrativa

Después de crear la cuenta por el comando administrativo e iniciar sesión:

`POST /auth/cambiar-contrasena` con Bearer → `204`, sin cuerpo.

```json
{
  "contrasena_actual": "contraseña-inicial-del-administrador",
  "contrasena_nueva": "nueva-contraseña-privada",
  "confirmar_contrasena": "nueva-contraseña-privada"
}
```

Sólo `admin_sistema` y `planeacion_admin`, sobre su propia cuenta. No acepta ID ni correo
de otro usuario. Nueva contraseña de 8 a 128 caracteres, diferente de la actual y con
confirmación coincidente. Es una operación disponible, **no un cambio forzado al primer login**.

Al recibir `204`, borrar el access token de la aplicación y volver al login. La cookie
se elimina y todos los access/refresh tokens anteriores dejan de funcionar, incluidos
los de otros dispositivos. No intentar renovar la sesión vieja después de este cambio.
El backend limita intentos fallidos de contraseña actual; puede devolver `429`.

La creación de contraseña por invitación es otro flujo (`/auth/password-setup`), y no
debe usarse como sustituto de este endpoint autenticado.

## 16. Limitaciones y checklist de integración

### Notificaciones del POA

- `GET /notificaciones?no_leidas=true`: notificaciones propias, sin paginación.
- `POST /notificaciones/{id}/leer`: marca una notificación propia, devuelve `204`.
- `POST /notificaciones/recordatorios/generar`: ejecución manual por Planeación/Admin;
  el scheduler también funciona dentro de la API, cada seis horas por defecto.
- `poa_actividad_asignada`: al asignar/reasignar una actividad, a usuarios activos con
  permiso de captura del área ejecutora. Cambiar observaciones sin cambiar área no avisa.
- `poa_captura_inicio` y `poa_captura_7d`: inicio y última semana de cada cuatrimestre.
  Sólo se generan para actividades sin alcanzado, progreso, alcance o evidencia archivo.
- `poa_total_inicio` y `poa_total_7d`: únicamente en C3, a Planeación, por indicadores
  sin número o porcentaje alcanzado. Cero no significa pendiente.
- No se repite el mismo aviso por usuario, elemento, periodo y ventana. Tras una caída
  se recupera la ventana vigente, sin enviar avisos de periodos ya vencidos/cerrados.
- Si el periodo sigue en borrador se informa que requiere apertura por Planeación.
  El recordatorio no abre el periodo ni concede permiso de captura.
- `entidad` será `poa_form_activity` o `poa_form_indicator`; `entidad_id` corresponde a
  la fila de la cédula, no a la clave del catálogo ni al ID de la cédula.
- Correo respeta cuenta activa y `notificar_correo`. `EMAIL_PROVIDER=console` sólo simula
  entrega en logs. Para correos reales se necesita SMTP. Los fallos se reintentan.
- `generadas` en la ejecución manual cuenta destinatarios procesados, incluyendo
  notificaciones deduplicadas; no usarlo como contador de correos nuevos enviados.

### No implementar como si ya existiera

- Importación de Excel desde el frontend o CRUD de los catálogos específicos POA.
- Eliminar cédulas, indicadores, actividades o emisiones por endpoints POA.
- Editar fechas cuatrimestrales después de crear la cédula.
- Enviar/validar/rechazar seguimientos POA, firmas o aprobación por `revisor_poa`.
- Consulta institucional de Rectoría sobre nuevas cédulas sin rol habilitante adicional.
- Un bloqueo automático de seguimiento por fecha, distinto del periodo abierto.
- Un permiso separado para que sólo Planeación edite `programado`: actualmente el área
  capturista lo puede enviar en su PUT autorizado.
- Exigir evidencia en el primer guardado: se permite captura incompleta; se exige al emitir.
- Edición en tiempo real, guardado masivo transaccional o bloqueo optimista de todos los DTO.
- Mezclar IDs o rutas del POA anterior. `/poa/procesos`, `/poa/objetivos`,
  `/poa/actividades`, `/poa/avances` y `/poa/reportes/por-proceso` fueron retirados.

Los `PATCH` de estructura generalmente ignoran valores nulos. Los campos ajenos al schema
se rechazan con `422` (`extra_forbidden`), no se ignoran. Construir los cuerpos
con listas explícitas de campos editables y reconsultar después de guardar.

### Checklist de aceptación frontend

- [ ] Login, cookie HttpOnly y refresh funcionan desde el origen real del frontend.
- [ ] Se distingue `area_id` propia, área responsable y área ejecutora.
- [ ] Se respetan los permisos combinados cuando un usuario tiene varios roles.
- [ ] Una cédula puede mostrar al menos dos indicadores y dos actividades correctamente.
- [ ] Los nombres/fórmulas/descripciones vienen de catálogo; sus IDs no se inventan.
- [ ] Los tres `periodo_id` se toman de la cédula y sus estados se consultan en `/periodos`.
- [ ] El detalle une seguimientos por actividad + cuatrimestre, sin cruzar filas.
- [ ] El PUT conserva los campos existentes que no se quieren borrar.
- [ ] Se distinguen `null`, cero y porcentajes superiores a 100.
- [ ] El área no puede editar estructura ni actividades asignadas a otra área.
- [ ] Se muestran correctamente cierre de C1 y periodo cerrado como restricciones distintas.
- [ ] La carga de archivo se considera completa sólo después de vincular la evidencia.
- [ ] Archivos protegidos y reportes se descargan con Bearer; no se filtran tokens a enlaces externos.
- [ ] Una emisión incompleta muestra las actividades pendientes; repetir una emisión maneja `409`.
- [ ] El histórico usa snapshot y no cambia al editar la cédula actual.
- [ ] El reporte corriente se distingue de una emisión histórica u oficial.
- [ ] El cambio privado de contraseña cierra la sesión y permite ingresar con la nueva.
- [ ] Los errores muestran mensajes útiles y permiten copiar `request_id` para soporte.

### Referencias del repositorio

Fuentes del contrato: `app/modules/poa_planning/api/cedula_schemas.py`, `cedula_router.py`,
`application/use_cases/manage_cedula.py`, `application/access_control.py`, módulos de
periodos/evidencias/reportes y `/openapi.json` del servidor. Documentación complementaria:

- [Contrato de cédulas](CONTRATO_CEDULAS_POA.md).
- [Permisos RBAC](RBAC.md).
- [Retiro del POA anterior y cambio de contraseña](POA_UNICO_Y_CAMBIO_CONTRASENA.md).

Este documento no modifica el comportamiento del backend ni despliega cambios en servidores.
