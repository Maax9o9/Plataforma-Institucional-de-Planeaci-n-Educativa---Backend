# Matriz RBAC canónica

La API valida el rol y, cuando aplica, la propiedad del registro o el alcance de área. La
interfaz puede ocultar acciones, pero nunca sustituye estas validaciones.

| Capacidad | admin_sistema | planeacion | responsable_area | rectoria | consulta |
|---|---:|---:|---:|---:|---:|
| Administrar usuarios y roles | Sí | Sólo cuentas no administrativas | No | No | No |
| Reactivar usuarios | Sí | No | No | No | No |
| Administrar catálogos, periodos e indicadores | Sí | Sí | No | No | No |
| Capturar y editar indicadores asignados | Sí por soporte | Sí por soporte | Sí, propios | No | No |
| Adjuntar/versionar evidencias | Sí | Sí | Sí, propias y editables | No | No |
| Validar o rechazar capturas | Sí | Sí | No | No | No |
| Consultar bitácora administrativa | Sí | Sí | No | No | No |
| Dashboard ejecutivo | Sí | No | No | Sí | No |
| Dashboard de planeación | Sí | Sí | No | No | No |
| Dashboard o flujo del área | Sí | Sí | Sí, área propia | No | Lectura autorizada |
| Reportes institucionales | Sí | Sí | No | Sí | Sí |
| Reportes por área | Sí | Sí | Sí, forzado a área propia | No | Sí, según endpoint |
| Cédulas POA actuales | Administración | Administración | No, requiere capturista_poa | Pendiente | Pendiente |

## Roles de la cédula POA refactorizada

| Capacidad | planeacion_admin | capturista_poa | revisor_poa | consulta (Rectoría) |
|---|---:|---:|---:|---:|
| Administración global existente | Sí, equivalente a `admin_sistema` | No | No | No |
| Crear cédula y sus tres periodos | Sí | No | No | Pendiente |
| Configurar indicadores y actividades | Sí | Sólo capturista de Dirección de Planeación Educativa activa | No | Pendiente |
| Capturar progreso y alcance | Sí | Solo actividades asignadas a su área | No | Pendiente |
| Adjuntar archivos al seguimiento | Sí | Solo actividades asignadas a su área | No | Pendiente |
| Emitir respaldo cuatrimestral | Sí | No | No | Pendiente |
| Omitir cierre estructural por emergencia | Sí | No | No | No |
| Mejorar únicamente la justificación | Sí | No | Pendiente | Pendiente |
| Revisar o validar cédula | Pendiente | No | Pendiente | Pendiente |

`planeacion_admin` hereda las capacidades de `planeacion` y `admin_sistema`. Los roles
`revisor_poa` y `consulta` se registran sin habilitar decisiones de negocio que aún no han
sido definidas.

Las políticas de cédula también se validan en los casos de uso. Tener `area_id` vacío
no permite consultar ni capturar actividades sin área ejecutora. Ser autor de un archivo
de seguimiento no conserva acceso si el usuario deja de tener el rol o área necesarios.
`planeacion` no puede otorgar `admin_sistema`/`planeacion_admin`, modificar cuentas
administrativas ni desactivarlas, incluso si el directorio resolviera esos roles al invitar.

El capturista de Planeación puede configurar las cédulas antes del cierre estructural,
pero no crear cédulas, emitirlas ni eludir el cierre. La asignación a su área institucional
se consulta mediante el puerto `AreaRepository`; el nombre exacto está centralizado en
la política POA. Un cambio de denominación institucional requiere actualizar esa política.

Los reportes y el historial POA ya utilizan cédulas actuales. `capturista_poa` sólo
obtiene filas de actividades ejecutadas por su área (salvo el capturista institucional
de Planeación). El rol de indicadores `responsable_area` no concede permisos POA.
La reapertura de un periodo no borra ni modifica emisiones históricas.

`POST /auth/cambiar-contrasena` permite a `admin_sistema` y `planeacion_admin` cambiar
exclusivamente su propia contraseña, comprobando la actual. No es un reset de terceros.

Las cuentas creadas por el seed usan correos institucionales descriptivos. La contraseña
proviene exclusivamente de `SEED_TEST_PASSWORD` y debe compartirse por un canal privado.
