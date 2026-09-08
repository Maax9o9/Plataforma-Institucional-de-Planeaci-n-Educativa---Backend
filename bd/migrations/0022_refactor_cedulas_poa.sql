-- ============================================================
-- 0022 · Cédula institucional POA y respaldo cuatrimestral
-- Módulo dueño: modules/poa_planning
-- ============================================================

CREATE TABLE poa_catalogo_objetivos (
    numero       SMALLINT PRIMARY KEY,
    clave        VARCHAR(20) NOT NULL UNIQUE,
    denominacion TEXT NOT NULL,
    activo       BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT chk_poa_objetivo_numero CHECK (numero BETWEEN 1 AND 6)
);

CREATE TABLE poa_catalogo_estrategias (
    clave           VARCHAR(20) PRIMARY KEY,
    objetivo_numero SMALLINT NOT NULL REFERENCES poa_catalogo_objetivos(numero),
    denominacion    TEXT NOT NULL,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (clave, objetivo_numero)
);

CREATE INDEX idx_poa_catalogo_estrategias_objetivo
    ON poa_catalogo_estrategias(objetivo_numero);

CREATE TABLE poa_catalogo_indicadores (
    clave           VARCHAR(30) PRIMARY KEY,
    objetivo_numero SMALLINT NOT NULL REFERENCES poa_catalogo_objetivos(numero),
    nombre          TEXT NOT NULL,
    formula         TEXT NOT NULL,
    unidad_medida   VARCHAR(100) NOT NULL,
    activo          BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_poa_catalogo_indicadores_objetivo
    ON poa_catalogo_indicadores(objetivo_numero);

CREATE TABLE poa_catalogo_actividades (
    clave             VARCHAR(30) PRIMARY KEY,
    estrategia_clave  VARCHAR(20) NOT NULL REFERENCES poa_catalogo_estrategias(clave),
    descripcion       TEXT NOT NULL,
    activo            BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_poa_catalogo_actividades_estrategia
    ON poa_catalogo_actividades(estrategia_clave);

CREATE TABLE poa_cedulas (
    id                             SERIAL PRIMARY KEY,
    ejercicio_id                   INTEGER NOT NULL REFERENCES poa_ejercicios(id),
    objetivo_numero                SMALLINT NOT NULL,
    estrategia_clave               VARCHAR(20) NOT NULL,
    area_responsable_id            INTEGER NOT NULL REFERENCES areas(id),
    alcance_efecto_socioeconomico  TEXT,
    creado_por                     INTEGER NOT NULL REFERENCES usuarios(id),
    version                        INTEGER NOT NULL DEFAULT 1,
    creado_en                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_poa_cedula_estrategia_objetivo
        FOREIGN KEY (estrategia_clave, objetivo_numero)
        REFERENCES poa_catalogo_estrategias(clave, objetivo_numero),
    UNIQUE (ejercicio_id, estrategia_clave, area_responsable_id)
);

CREATE INDEX idx_poa_cedulas_ejercicio_objetivo
    ON poa_cedulas(ejercicio_id, objetivo_numero);
CREATE INDEX idx_poa_cedulas_area
    ON poa_cedulas(area_responsable_id);

CREATE TABLE poa_cedula_indicadores (
    id                    SERIAL PRIMARY KEY,
    cedula_id             INTEGER NOT NULL REFERENCES poa_cedulas(id) ON DELETE CASCADE,
    indicador_clave       VARCHAR(30) NOT NULL REFERENCES poa_catalogo_indicadores(clave),
    meta_institucional    NUMERIC(18,4),
    linea_base_anio       SMALLINT,
    linea_base_valor      NUMERIC(18,4),
    porcentaje_actual     NUMERIC(7,4),
    meta_numero           NUMERIC(18,4),
    meta_porcentaje       NUMERIC(7,4),
    total_alcanzado       NUMERIC(18,4),
    porcentaje_alcanzado  NUMERIC(7,4),
    creado_en             TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_poa_indicador_valores_no_negativos CHECK (
        (meta_institucional IS NULL OR meta_institucional >= 0)
        AND (linea_base_valor IS NULL OR linea_base_valor >= 0)
        AND (meta_numero IS NULL OR meta_numero >= 0)
        AND (total_alcanzado IS NULL OR total_alcanzado >= 0)
    ),
    CONSTRAINT chk_poa_indicador_porcentajes CHECK (
        (porcentaje_actual IS NULL OR porcentaje_actual BETWEEN 0 AND 100)
        AND (meta_porcentaje IS NULL OR meta_porcentaje BETWEEN 0 AND 100)
        AND (porcentaje_alcanzado IS NULL OR porcentaje_alcanzado >= 0)
    ),
    UNIQUE (cedula_id, indicador_clave)
);

CREATE INDEX idx_poa_cedula_indicadores_cedula
    ON poa_cedula_indicadores(cedula_id);

CREATE TABLE poa_cedula_actividades (
    id                 SERIAL PRIMARY KEY,
    cedula_id          INTEGER NOT NULL REFERENCES poa_cedulas(id) ON DELETE CASCADE,
    actividad_clave    VARCHAR(30) NOT NULL REFERENCES poa_catalogo_actividades(clave),
    unidad_medida      VARCHAR(100) NOT NULL,
    meta_anual         NUMERIC(18,4) NOT NULL,
    area_ejecutora_id  INTEGER REFERENCES areas(id),
    observaciones      TEXT,
    creado_en          TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_poa_cedula_actividad_meta CHECK (meta_anual >= 0),
    UNIQUE (cedula_id, actividad_clave)
);

CREATE INDEX idx_poa_cedula_actividades_cedula
    ON poa_cedula_actividades(cedula_id);
CREATE INDEX idx_poa_cedula_actividades_area
    ON poa_cedula_actividades(area_ejecutora_id);

CREATE TABLE poa_cedula_seguimientos (
    id                       SERIAL PRIMARY KEY,
    cedula_actividad_id      INTEGER NOT NULL
                                 REFERENCES poa_cedula_actividades(id) ON DELETE CASCADE,
    cuatrimestre             SMALLINT NOT NULL,
    periodo_id               INTEGER NOT NULL REFERENCES periodos(id),
    capturado_por            INTEGER NOT NULL REFERENCES usuarios(id),
    programado               NUMERIC(18,4) NOT NULL,
    alcanzado                NUMERIC(18,4),
    justificacion_desviacion TEXT,
    creado_en                TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_poa_cedula_seguimiento_cuatrimestre
        CHECK (cuatrimestre IN (1, 2, 3)),
    CONSTRAINT chk_poa_cedula_seguimiento_valores
        CHECK (programado >= 0 AND (alcanzado IS NULL OR alcanzado >= 0)),
    UNIQUE (cedula_actividad_id, cuatrimestre)
);

CREATE INDEX idx_poa_cedula_seguimientos_periodo
    ON poa_cedula_seguimientos(periodo_id);

CREATE TABLE poa_cedula_emisiones (
    id            SERIAL PRIMARY KEY,
    cedula_id     INTEGER NOT NULL REFERENCES poa_cedulas(id),
    cuatrimestre  SMALLINT NOT NULL,
    periodo_id    INTEGER NOT NULL REFERENCES periodos(id),
    nombre        VARCHAR(200) NOT NULL,
    snapshot      JSONB NOT NULL,
    emitido_por   INTEGER NOT NULL REFERENCES usuarios(id),
    emitido_en    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_poa_cedula_emision_cuatrimestre
        CHECK (cuatrimestre IN (1, 2, 3)),
    UNIQUE (cedula_id, cuatrimestre)
);

CREATE INDEX idx_poa_cedula_emisiones_periodo
    ON poa_cedula_emisiones(periodo_id);
