# Matriz RBAC canónica

La API valida el rol y, cuando aplica, la propiedad del registro o el alcance de área. La
interfaz puede ocultar acciones, pero nunca sustituye estas validaciones.

| Capacidad | admin_sistema | planeacion | responsable_area | rectoria | consulta |
|---|---:|---:|---:|---:|---:|
| Administrar usuarios y roles | Sí | Sí | No | No | No |
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
| Planeación y validación POA | Sí | Sí | Captura propia | Lectura ejecutiva | Lectura autorizada |

Las cuentas creadas por el seed usan correos institucionales descriptivos. La contraseña
proviene exclusivamente de `SEED_TEST_PASSWORD` y debe compartirse por un canal privado.
