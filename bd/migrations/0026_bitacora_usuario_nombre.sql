-- Instantanea del nombre del autor en la bitacora.
--
-- Hasta ahora la bitacora guardaba solo `usuario_id`, asi que cualquier cliente
-- tenia que resolver el nombre contra el directorio vigente. Si una cuenta se
-- renombra o se reasigna, los movimientos historicos quedaban atribuidos al
-- nombre nuevo, lo que contradice el proposito de la bitacora: saber quien hizo
-- que aunque esa persona ya no este en la institucion.
--
-- El nombre se captura al insertar y no se recalcula despues. Las entradas ya
-- existentes conservan NULL: su nombre historico no se puede reconstruir.

ALTER TABLE bitacora ADD COLUMN usuario_nombre VARCHAR(200);

COMMENT ON COLUMN bitacora.usuario_nombre IS
    'Nombre del autor al momento del movimiento. No se actualiza si el usuario cambia de nombre.';
