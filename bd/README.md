# bd/ — Base de datos

Contiene el modelo de datos completo del sistema, como migraciones SQL puras
(no atadas a un ORM), para que sean legibles y revisables sin leer código de
aplicación. Aplicarlas es trabajo de Alembic, por lo que dice «Cómo
ejecutarlas».

## Orden de ejecución

Los archivos en `migrations/` están numerados y **deben ejecutarse en el orden
de la cadena de revisiones de Alembic, que no es el del nombre**: cada uno
depende de tipos y tablas creados en el anterior.

La tabla de abajo documenta el **set inicial** (0001-0017). Lo que vino después
—hasta la 0037— no se repite aquí: cada archivo lo dice en su cabecera, y una
tabla que hay que actualizar a mano en cada migración es una tabla que se queda
atrás, como ésta se quedó durante veinte. El índice que no miente es
`ls bd/migrations/`; el que manda es `alembic/versions/`.

| # | Archivo | Módulo dueño | Contenido |
|---|---|---|---|
| 0001 | `extensiones_y_enums.sql` | shared | Extensiones de Postgres y todos los `ENUM` |
| 0002 | `identidad_y_seguridad.sql` | `identity_access` | usuarios, roles, refresh tokens, auditoría de accesos |
| 0003 | `catalogos_institucionales.sql` | `institutional_catalogs` | áreas, instrumentos, criterios SEAES, config global |
| 0004 | `periodos.sql` | `periods` | periodos de captura (indicadores y POA) |
| 0005 | `indicadores_catalogo.sql` | `indicators_catalog` | indicadores, línea base, metas |
| 0006 | `indicadores_captura.sql` | `indicators_capture` | capturas de avance |
| 0007 | `poa_planeacion.sql` | `poa_planning` | ejercicios, procesos, objetivos, actividades |
| 0008 | `poa_seguimiento.sql` | `poa_tracking` | avances cuatrimestrales |
| 0009 | `evidencias_y_flujo.sql` | `evidence_management` + `*_validation` | evidencias, vínculos, historial de estados |
| 0010 | `notificaciones.sql` | `notifications` | notificaciones y recordatorios |
| 0011 | `bitacora.sql` | `audit` | bitácora inmutable |
| 0012 | `reportes_y_dashboards.sql` | `indicators_reports`, `poa_reports`, `dashboards` | log de reportes + vista materializada |
| 0013 | `compatibilidad_api.sql` | shared y módulos Fase 0 | columnas y enums requeridos por la API inicial |
| 0014 | `catalogos_auxiliares.sql` | `institutional_catalogs` | estado de tipos de indicador |
| 0015 | `notificaciones_idempotencia.sql` | `notifications` | idempotencia por evento |
| 0016 | `mv_avance_poa.sql` | `dashboards` | vista materializada institucional POA |
| 0017 | `invitacion_contrasena.sql` | `identity_access` | enlaces de configuracion inicial |

## Cómo ejecutarlas

**Vía Alembic, y sólo así:** cada archivo se envuelve en una revisión de
`alembic/versions/` con `op.execute(...)` para tener control de versión de
esquema, rollback y ejecución coordinada con el despliegue del backend.

```bash
python -m alembic upgrade head
```

Es el único camino que las pruebas ejercitan: `tests/test_instalacion_nueva.py`
migra así una base virgen, y `tests/test_migraciones_cargables.py` vigila la
trampa propia de este camino —un `:nombre` suelto dentro del SQL, que
`sqlalchemy.text()` toma por parámetro y `psql` no—.

**Lo que aquí decía y no era verdad:** un `for f in bd/migrations/*.sql` con
`psql`, ofrecido como «opción rápida (dev)». Ninguna prueba lo toca y no es
equivalente: el glob ordena por nombre y la cadena de revisiones no tiene por
qué coincidir —hay dos `0026_*`, dos `0028_*`, y dos revisiones
(`0029_unir_cabezas_migracion`, `0033_unir_plantillas_correo`) que unen cabezas
y no tienen archivo `.sql`—. Correrlo deja un esquema distinto del que tiene
producción, y sin avisar.

## Reglas al agregar una migración nueva

1. Un archivo nuevo por cambio de esquema, nunca editar uno ya aplicado en
   ambientes compartidos (staging/producción).
2. El comentario de cabecera debe indicar **qué módulo es dueño** de las
   tablas que crea (ver `INTEGRACION_BD.md` §2 para el criterio de propiedad).
3. Si el cambio agrega algo que no estaba en las historias de usuario
   originales, decir por qué explícitamente en un comentario `-- SUGERENCIA:`,
   igual que se hizo en 0002, 0009, 0010, 0011 y 0012 de este set inicial.
