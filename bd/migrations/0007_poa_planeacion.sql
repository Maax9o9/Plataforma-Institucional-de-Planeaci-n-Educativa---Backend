-- ============================================================
-- 0007 · Estructura del POA
-- Módulo dueño: modules/poa_planning  (EP-06)
-- ============================================================

CREATE TABLE poa_ejercicios (
    id      SERIAL PRIMARY KEY,
    anio    SMALLINT NOT NULL UNIQUE
);

CREATE TABLE poa_procesos (
    id           SERIAL PRIMARY KEY,
    ejercicio_id INTEGER NOT NULL REFERENCES poa_ejercicios(id),
    nombre       VARCHAR(300) NOT NULL,
    area_id      INTEGER NOT NULL REFERENCES areas(id)
);

CREATE INDEX idx_poa_procesos_ejercicio ON poa_procesos(ejercicio_id);
CREATE INDEX idx_poa_procesos_area ON poa_procesos(area_id);

CREATE TABLE poa_objetivos (
    id              SERIAL PRIMARY KEY,
    proceso_id      INTEGER NOT NULL REFERENCES poa_procesos(id) ON DELETE CASCADE,
    indicador_poa   VARCHAR(300),      -- texto libre del formato institucional
    objetivo        TEXT NOT NULL
);

CREATE INDEX idx_poa_objetivos_proceso ON poa_objetivos(proceso_id);

CREATE TABLE poa_actividades (
    id              SERIAL PRIMARY KEY,
    objetivo_id     INTEGER NOT NULL REFERENCES poa_objetivos(id) ON DELETE CASCADE,
    descripcion     TEXT NOT NULL,
    unidad_medida   VARCHAR(100) NOT NULL,
    meta_anual      NUMERIC(18,4) NOT NULL,   -- HU-06.03: inmutable con cuatrimestre validado
    observaciones   TEXT,
    responsable_id  INTEGER NOT NULL REFERENCES usuarios(id),

    CONSTRAINT chk_meta_anual_positiva CHECK (meta_anual >= 0)
);

CREATE INDEX idx_poa_actividades_objetivo ON poa_actividades(objetivo_id);
CREATE INDEX idx_poa_actividades_responsable ON poa_actividades(responsable_id);
