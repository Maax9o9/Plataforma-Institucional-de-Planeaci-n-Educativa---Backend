-- El catalogo del PSE deja de ser inmutable.
--
-- Hasta aqui los objetivos, estrategias, indicadores y actividades los sembraba
-- una migracion y cambiarlos exigia editar Python y desplegar. El PSE cambia
-- -se retira una estrategia, se reescribe un indicador, el sexenio siguiente
-- trae otros objetivos- y la institucion tiene que poder reflejarlo sin pasar
-- por el equipo de desarrollo.
--
-- Lo unico que cambia en el esquema es el numero de objetivo. El CHECK lo
-- ataba a 1..6, que son los del PSE 2025-2030: con el, crear un objetivo nuevo
-- era imposible y "cambiar unos por otros" se quedaba a medias. Se relaja a
-- "mayor o igual que 1" porque el numero sigue siendo parte de la clave de las
-- estrategias y las acciones (1.4.1 = objetivo.estrategia.accion) y un cero o
-- un negativo romperian esa lectura.
--
-- Deshabilitar no borra: la columna `activo` ya existia en las cuatro tablas y
-- las cedulas apuntan al catalogo por llave foranea. Una cedula ya formulada
-- conserva su estrategia aunque se retire del catalogo -la fila sigue ahi- y
-- sigue resolviendo su denominacion. Lo que `activo` gobierna es que se pueda
-- elegir de nuevo, no lo que ya se eligio.

ALTER TABLE poa_catalogo_objetivos DROP CONSTRAINT IF EXISTS chk_poa_objetivo_numero;
ALTER TABLE poa_catalogo_objetivos ADD CONSTRAINT chk_poa_objetivo_numero CHECK (numero >= 1);

COMMENT ON COLUMN poa_catalogo_objetivos.activo IS
    'Si se puede elegir al formular. Deshabilitarlo no afecta a las cedulas que ya lo usan.';
COMMENT ON COLUMN poa_catalogo_estrategias.activo IS
    'Si se puede elegir al formular. Deshabilitarla no afecta a las cedulas que ya la usan.';
COMMENT ON COLUMN poa_catalogo_indicadores.activo IS
    'Si se puede agregar a una cedula. Deshabilitarlo no afecta a las cedulas que ya lo usan.';
COMMENT ON COLUMN poa_catalogo_actividades.activo IS
    'Si se puede agregar a una cedula. Deshabilitarla no afecta a las cedulas que ya la usan.';
