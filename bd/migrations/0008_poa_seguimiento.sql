-- ============================================================
-- 0008 · Seguimiento cuatrimestral del POA
-- Módulo dueño: modules/poa_tracking  (EP-07)
-- ============================================================

CREATE TABLE poa_avances (
    id               SERIAL PRIMARY KEY,
    actividad_id     INTEGER NOT NULL REFERENCES poa_actividades(id),
    cuatrimestre     SMALLINT NOT NULL,
    periodo_id       INTEGER NOT NULL REFERENCES periodos(id),
    capturista_id    INTEGER NOT NULL REFERENCES usuarios(id),
    programado       NUMERIC(18,4),     -- requerido para enviar (RN-POA-02)
    alcanzado        NUMERIC(18,4),     -- requerido para enviar
    observaciones    TEXT,              -- requerido para enviar
    pct_cumplimiento NUMERIC(6,2),      -- HU-07.01: alcanzado / programado
    estado           estado_captura NOT NULL DEFAULT 'borrador',
    creado_en        TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_cuatrimestre_valido CHECK (cuatrimestre IN (1, 2, 3)),
    UNIQUE (actividad_id, cuatrimestre)
);

CREATE INDEX idx_poa_avances_periodo ON poa_avances(periodo_id);
CREATE INDEX idx_poa_avances_capturista_estado ON poa_avances(capturista_id, estado);
CREATE INDEX idx_poa_avances_actividad ON poa_avances(actividad_id);

CREATE TABLE poa_avance_criterios_seaes (
    poa_avance_id       INTEGER NOT NULL REFERENCES poa_avances(id) ON DELETE CASCADE,
    criterio_seaes_id   INTEGER NOT NULL REFERENCES criterios_seaes(id),
    PRIMARY KEY (poa_avance_id, criterio_seaes_id)
);
