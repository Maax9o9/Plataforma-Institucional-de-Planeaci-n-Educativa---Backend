-- ============================================================
-- 0005 · Catálogo maestro de indicadores
-- Módulo dueño: modules/indicators_catalog  (EP-01)
-- ============================================================

CREATE TABLE indicadores (
    id                          SERIAL PRIMARY KEY,
    clave                       VARCHAR(50)  NOT NULL UNIQUE,          -- HU-01.01
    nombre                      VARCHAR(300) NOT NULL,
    definicion                  TEXT,
    metodo_calculo              TEXT         NOT NULL,
    unidad_medida               VARCHAR(100) NOT NULL,
    dimension                   VARCHAR(100),
    documento_verificacion      VARCHAR(300),
    fuente_informacion          VARCHAR(300),
    observaciones_metodologicas TEXT,
    tipo_indicador_id           INTEGER REFERENCES tipos_indicador(id),
    area_id                     INTEGER NOT NULL REFERENCES areas(id),       -- área responsable
    responsable_id              INTEGER NOT NULL REFERENCES usuarios(id),    -- responsable de información
    periodicidad                periodicidad NOT NULL,                       -- HU-01.06: única activa
    umbral_verde_min            SMALLINT,     -- HU-04.02: NULL = usa umbral global
    umbral_amarillo_min         SMALLINT,
    activo                      BOOLEAN NOT NULL DEFAULT TRUE,               -- RN-05: no se elimina
    creado_en                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en              TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_umbrales_indicador CHECK (
        (umbral_verde_min IS NULL AND umbral_amarillo_min IS NULL)
        OR (umbral_amarillo_min < umbral_verde_min)
    )
);

CREATE INDEX idx_indicadores_area ON indicadores(area_id);
CREATE INDEX idx_indicadores_responsable ON indicadores(responsable_id);
CREATE INDEX idx_indicadores_activo ON indicadores(activo) WHERE activo = TRUE;

CREATE TABLE indicador_instrumentos (
    indicador_id    INTEGER NOT NULL REFERENCES indicadores(id) ON DELETE CASCADE,
    instrumento_id  INTEGER NOT NULL REFERENCES instrumentos(id),
    PRIMARY KEY (indicador_id, instrumento_id)
);

CREATE TABLE indicador_criterios_seaes (
    indicador_id        INTEGER NOT NULL REFERENCES indicadores(id) ON DELETE CASCADE,
    criterio_seaes_id   INTEGER NOT NULL REFERENCES criterios_seaes(id),
    PRIMARY KEY (indicador_id, criterio_seaes_id)
);

CREATE TABLE lineas_base (
    id           SERIAL PRIMARY KEY,
    indicador_id INTEGER NOT NULL UNIQUE REFERENCES indicadores(id) ON DELETE CASCADE, -- HU-01.04: una sola
    anio         SMALLINT NOT NULL,
    periodo      VARCHAR(50),
    valor        NUMERIC(18,4) NOT NULL,
    creado_en    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE metas (
    id           SERIAL PRIMARY KEY,
    indicador_id INTEGER NOT NULL REFERENCES indicadores(id) ON DELETE CASCADE,
    periodo_id   INTEGER NOT NULL REFERENCES periodos(id),
    valor        NUMERIC(18,4) NOT NULL,               -- HU-01.05

    CONSTRAINT chk_meta_valor_positivo CHECK (valor >= 0),
    UNIQUE (indicador_id, periodo_id)
);

CREATE INDEX idx_metas_periodo ON metas(periodo_id);
