# Alta administrativa y verificación del POA

## Administrador sin credenciales en `.env`

Después de desplegar esta versión y aplicar migraciones, ejecuta en la carpeta del
proyecto de tu VPS (sustituye el correo y nombre):

```bash
docker compose -f docker-compose.prod.yml exec api python -m app.scripts.create_admin --correo admin@tu-institucion.mx --nombre "Administrador"
```

Sin Docker, desde la raíz del backend y con su entorno virtual activado:

```bash
python -m alembic upgrade head
python -m app.scripts.create_admin --correo admin@tu-institucion.mx --nombre "Administrador"
```

La terminal solicita dos veces la contraseña oculta, de al menos ocho caracteres.
No uses `exec -T`, redirecciones ni una contraseña como argumento. El comando crea una
cuenta activa con rol `admin_sistema`, sin requerir invitación ni configuración inicial
de contraseña. Puede iniciar sesión inmediatamente. No modifica ni promueve una cuenta
que ya exista: un correo duplicado provoca un error controlado.

Se almacena un hash Argon2, nunca la contraseña en texto plano. El usuario, sus roles
y su registro de auditoría se guardan en una transacción; si falla, el alta se revierte.
Sólo alguien con acceso a la terminal del servidor y a la base puede ejecutar este alta.
Las demás cuentas pueden seguir invitándose mediante `POST /api/v1/usuarios`.

`BOOTSTRAP_ADMIN_EMAIL` y `BOOTSTRAP_ADMIN_PASSWORD` ya no crean usuarios al arrancar:
pueden quitarse del `.env`. No se borran cuentas existentes. La conexión `DATABASE_URL`
y la clave de firma de tokens `SECRET_KEY` siguen siendo necesarias; son distintas de
la contraseña del administrador. No se modificó el `.env` personal ni los secretos de GitHub.

## Flujo y multiplicidad

1. Un administrador o Planeación crea ejercicio, cédula y tres rangos cuatrimestrales.
2. Se agregan varios indicadores del objetivo y varias actividades de la estrategia.
   Cada fila conserva su identificador propio. Las claves duplicadas en la misma cédula
   se rechazan; no se necesita Excel para agregar estas asociaciones.
3. Planeación configura metas y áreas ejecutoras. Un capturista de otra área no puede
   modificar estructura, aunque su área sea la responsable de la cédula.
4. Se abre el periodo correspondiente. Cada área captura seguimiento en sus actividades,
   carga archivos y los vincula como evidencias al seguimiento concreto.
5. Para emitir, todas las actividades necesitan progreso, alcance, valor alcanzado y
   archivo de evidencia. En el tercer periodo todos los indicadores necesitan total.
6. La emisión guarda una instantánea completa e inmutable. Las modificaciones posteriores
   a la cédula o a los seguimientos no alteran esa instantánea.

La estructura queda bloqueada al terminar el primer cuatrimestre; los administradores
pueden corregirla por emergencia. El endpoint exclusivo de justificación de Planeación
no cambia otros campos ni reescribe emisiones. Los permisos se describen en `RBAC.md`.

## Correcciones de esta revisión

- Alta administrativa explícita en lugar de creación automática desde configuración.
- Políticas de autorización reutilizables en la capa de aplicación, consumidas por
  casos de uso y consultas; la API mantiene sus validaciones de entrada.
- Capturistas sin área ya no coinciden con actividades sin área asignada.
- Evidencias de seguimiento: el rol y área actuales gobiernan acceso, no sólo autoría.
- Planeación no administrativa no puede otorgar privilegios administrativos ni modificar
  o desactivar cuentas administrativas. También se verifica el rol resuelto por directorio.
- Consulta de existencia de evidencia en PostgreSQL admite varios archivos vinculados
  sin fallar por devolver más de una fila.

Se conserva la separación dominio/aplicación/infraestructura/API, usando puertos de
repositorio e inyección de dependencias. No se agregaron condiciones de rol a SQL ni se
duplicó el alta de usuarios: el comando reutiliza el caso de uso y el adaptador de hash.

## Alcance y pendientes explícitos

Actualización: el retiro del modelo anterior y el cambio privado de contraseña se
describen en [POA único y cambio de contraseña](POA_UNICO_Y_CAMBIO_CONTRASENA.md).

- `revisor_poa` y consulta de Rectoría para cédulas siguen pendientes de reglas de negocio;
  no se habilitaron validación ni consulta global por inferencia.
- Las rutas del POA anterior ya se retiraron. Reportes y dashboards consultan las
  nuevas cédulas; los datos antiguos no se mezclan ni se migran por inferencia.
- Abrir/cerrar periodos sigue siendo una operación explícita. La captura verifica el
  periodo abierto y las fechas configuradas, pero no lo abre/cierra automáticamente por
  reloj ni impide adelantar un tercer periodo abierto. El cierre por fecha actualmente
  corresponde a la estructura del primer cuatrimestre.
- El seguimiento conserva `programado` y `alcanzado` además de `progreso`/`alcance`.
  Si se desea que sólo Planeación defina `programado` y que el área nunca lo cambie,
  falta separar ese permiso y su contrato de captura; no se cambió silenciosamente.
- La carga de evidencia es de dos pasos; es posible guardar un seguimiento incompleto
  como borrador. La exigencia de archivo se aplica al emitir, no al primer guardado.
- La asignación de correos conocidos continúa usando el directorio institucional interno;
  las invitaciones no incluidas utilizan el área y roles enviados por administración.

## Verificación de la revisión inicial (antes del retiro)

Suite automatizada: 38 pruebas aprobadas, incluidas las de PostgreSQL sobre una base
temporal nueva migrada hasta `0023_roles_cuatrimestres`. Se comprobaron dos indicadores
y dos actividades en una cédula tanto en memoria como en PostgreSQL, duplicados,
rechazo de emisión incompleta, instantáneas, reasignación de área, permisos administrativos,
alta con hash y reversión transaccional ante fallo de auditoría. La revisión estática de
los archivos afectados pasó. Esto no sustituye pruebas de carga ni una auditoría exhaustiva
de seguridad del sistema completo. No se desplegó ni modificó la base de la VPS.
