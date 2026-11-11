-- Criterios SEAES de una evidencia.
--
-- La actividad ya declara contra que criterios del SEAES responde (migracion
-- 0031). La evidencia es mas fina: un area entrega varios archivos por
-- cuatrimestre y no todos sirven para lo mismo -una lista de asistencia
-- sostiene un criterio y un convenio firmado sostiene otro-, asi que al
-- adjuntarla se puede decir a cual responde.
--
-- Es opcional a proposito. Obligarlo convertiria el campo en un tramite que se
-- rellena con lo primero que aparezca, y la cobertura SEAES que se mide en el
-- semaforo dejaria de significar algo. Muchos a muchos por la misma razon que
-- en la actividad: los criterios son indicativos y un documento puede servir
-- para varios.

CREATE TABLE evidencia_criterios (
    evidencia_id INTEGER NOT NULL REFERENCES evidencias(id) ON DELETE CASCADE,
    criterio_seaes_id INTEGER NOT NULL REFERENCES criterios_seaes(id),
    PRIMARY KEY (evidencia_id, criterio_seaes_id)
);

COMMENT ON TABLE evidencia_criterios IS
    'Criterios SEAES a los que responde una evidencia. Opcional e indicativo: una evidencia puede servir para varios, o para ninguno.';
