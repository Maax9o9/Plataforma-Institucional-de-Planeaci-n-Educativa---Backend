-- Criterio SEAES por actividad del POA.
--
-- SEAES no es un programa paralelo: es una clasificacion que se aplica a cada
-- actividad del POA, y la asigna el area responsable cuando recibe su actividad,
-- leyendo su descripcion.
--
-- El vinculo que existia (indicador_criterios_seaes, migracion 0005) une el
-- criterio con el indicador del catalogo PIDE, que es el eje equivocado. El eje
-- correcto vivia en el modelo retirado (poa_avance_criterios_seaes, 0008) y no
-- se recreo cuando la 0022 rehizo el POA en cedulas.
--
-- Nullable a proposito: la asignacion es una tarea del area y su ausencia es
-- justo lo que mide la cobertura SEAES del semaforo.

ALTER TABLE poa_cedula_actividades
    ADD COLUMN criterio_seaes_id INTEGER REFERENCES criterios_seaes(id);

CREATE INDEX idx_poa_cedula_actividades_criterio
    ON poa_cedula_actividades(criterio_seaes_id);

COMMENT ON COLUMN poa_cedula_actividades.criterio_seaes_id IS
    'Criterio SEAES que clasifica la actividad. Lo asigna el area ejecutora al recibirla.';
