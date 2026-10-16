-- Flujo de revision del seguimiento cuatrimestral del POA (EP-08).
--
-- Hasta ahora el seguimiento se guardaba y ya: no habia forma de que el area lo
-- enviara a revision ni de que Planeacion lo aprobara o lo devolviera. Lo unico
-- disponible era la emision, que es un respaldo inmutable y no una validacion.
--
-- Se reutiliza el enum `estado_captura` y la tabla `cambios_estado`, que desde
-- la migracion 0023 ya admite la entidad `poa_cedula_seguimiento`. Asi el POA y
-- los indicadores comparten el mismo ciclo y el mismo historial.
--
-- Los seguimientos existentes quedan en 'borrador': nunca fueron revisados.

ALTER TABLE poa_cedula_seguimientos
    ADD COLUMN estado estado_captura NOT NULL DEFAULT 'borrador';

-- Comentario del ultimo rechazo, visible para el area que debe corregir.
ALTER TABLE poa_cedula_seguimientos
    ADD COLUMN comentario_revision TEXT;

CREATE INDEX idx_poa_cedula_seguimientos_estado
    ON poa_cedula_seguimientos(estado);

COMMENT ON COLUMN poa_cedula_seguimientos.estado IS
    'Ciclo de revision: borrador -> enviado -> validado | rechazado.';
COMMENT ON COLUMN poa_cedula_seguimientos.comentario_revision IS
    'Motivo del ultimo rechazo. Obligatorio al rechazar, se conserva para que el area lo corrija.';
