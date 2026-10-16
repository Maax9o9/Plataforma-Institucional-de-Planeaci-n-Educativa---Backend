-- Actividad UPE y criterios SEAES multiples por actividad del POA.
--
-- El texto oficial del POA federal es generico: Planeacion le agrega, por
-- actividad, una explicacion concreta de que significa para el area que la
-- va a ejecutar (la llaman "actividad UPE Chiapas").
--
-- Y los criterios SEAES (migracion 0028) son siete e indicativos: una
-- actividad puede caer en varios a la vez. La columna singular
-- `criterio_seaes_id` ya no puede representar ese dato, asi que se reemplaza
-- por una tabla muchos a muchos. El orden importa aqui: primero se copian
-- los criterios que ya existian, despues se suelta la columna.

CREATE TABLE poa_cedula_actividad_criterios (
    cedula_actividad_id INTEGER NOT NULL
        REFERENCES poa_cedula_actividades(id) ON DELETE CASCADE,
    criterio_seaes_id INTEGER NOT NULL REFERENCES criterios_seaes(id),
    PRIMARY KEY (cedula_actividad_id, criterio_seaes_id)
);

INSERT INTO poa_cedula_actividad_criterios (cedula_actividad_id, criterio_seaes_id)
SELECT id, criterio_seaes_id FROM poa_cedula_actividades WHERE criterio_seaes_id IS NOT NULL;

DROP INDEX IF EXISTS idx_poa_cedula_actividades_criterio;
ALTER TABLE poa_cedula_actividades DROP COLUMN criterio_seaes_id;
ALTER TABLE poa_cedula_actividades ADD COLUMN actividad_upe TEXT;

COMMENT ON TABLE poa_cedula_actividad_criterios IS
    'Criterios SEAES que clasifican la actividad. Son indicativos: una actividad puede tener varios.';
COMMENT ON COLUMN poa_cedula_actividades.actividad_upe IS
    'Que significa la actividad en concreto para el area ejecutora ("actividad UPE Chiapas").';
