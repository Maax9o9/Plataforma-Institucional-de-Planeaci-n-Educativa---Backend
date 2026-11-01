CREATE TABLE poa_inst_areas (
    id           SERIAL PRIMARY KEY,
    ejercicio_id INTEGER NOT NULL,
    area_id      INTEGER NOT NULL,
    estado       VARCHAR(30) NOT NULL DEFAULT 'borrador',
    version      INTEGER NOT NULL DEFAULT 1,
    creado_en    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT fk_poa_inst_area_ejercicio
        FOREIGN KEY (ejercicio_id) REFERENCES poa_ejercicios(id) ON DELETE RESTRICT,
    CONSTRAINT fk_poa_inst_area_area
        FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT,
    CONSTRAINT uq_poa_inst_area_ejercicio_area UNIQUE (ejercicio_id, area_id),
    CONSTRAINT chk_poa_inst_area_estado CHECK (estado IN ('borrador', 'enviado'))
);

CREATE TABLE poa_inst_actividades (
    id                SERIAL PRIMARY KEY,
    poa_area_id       INTEGER NOT NULL,
    nodo_id           INTEGER,
    denominacion      TEXT NOT NULL,
    unidad_medida_id  INTEGER,
    metodo_evaluacion TEXT,
    meta_anual        NUMERIC(18, 4),
    version           INTEGER NOT NULL DEFAULT 1,
    activo            BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_poa_inst_actividad_poa_area
        FOREIGN KEY (poa_area_id) REFERENCES poa_inst_areas(id) ON DELETE RESTRICT,
    CONSTRAINT fk_poa_inst_actividad_nodo
        FOREIGN KEY (nodo_id) REFERENCES nodos_estrategicos(id) ON DELETE RESTRICT,
    CONSTRAINT fk_poa_inst_actividad_unidad_medida
        FOREIGN KEY (unidad_medida_id) REFERENCES unidades_medida(id) ON DELETE RESTRICT,
    CONSTRAINT chk_poa_inst_actividad_meta_anual_no_negativa CHECK (meta_anual >= 0)
);

CREATE TABLE poa_inst_programacion_mensual (
    id           SERIAL PRIMARY KEY,
    actividad_id INTEGER NOT NULL,
    mes          SMALLINT NOT NULL,
    meta         NUMERIC(18, 4) NOT NULL,
    incluido     BOOLEAN NOT NULL,

    CONSTRAINT fk_poa_inst_programacion_actividad
        FOREIGN KEY (actividad_id) REFERENCES poa_inst_actividades(id) ON DELETE RESTRICT,
    CONSTRAINT uq_poa_inst_programacion_actividad_mes UNIQUE (actividad_id, mes),
    CONSTRAINT chk_poa_inst_programacion_mes CHECK (mes BETWEEN 1 AND 12),
    CONSTRAINT chk_poa_inst_programacion_meta_no_negativa CHECK (meta >= 0),
    CONSTRAINT chk_poa_inst_programacion_no_incluido_sin_meta CHECK (incluido OR meta = 0)
);
