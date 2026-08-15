-- ============================================================
-- 0004 · Periodos de captura
-- Módulo dueño: modules/periods  (EP-00 · F0.3)
-- ============================================================

CREATE TABLE periodos (
    id              SERIAL PRIMARY KEY,
    tipo            tipo_periodo    NOT NULL,
    periodicidad    periodicidad,                 -- NULL en periodos de tipo 'poa'; HU-01.06
    anio            SMALLINT        NOT NULL,
    etiqueta        VARCHAR(100)    NOT NULL,      -- 'Ene-2026', '1er cuatrimestre 2026'
    fecha_inicio    DATE            NOT NULL,
    fecha_limite    DATE            NOT NULL,      -- usada por recordatorios 5/3/2/1 días (HU-11.03)
    estado          estado_periodo  NOT NULL DEFAULT 'abierto',

    -- SUGERENCIA: motivo de reapertura obligatorio (RN-03/RN-POA-05).
    -- El diagrama original no lo tenía como columna; sin él, la regla
    -- "toda reapertura requiere motivo" solo se podría exigir en el
    -- código de aplicación y quedaría fuera de la bitácora estructurada.
    motivo_reapertura   TEXT,
    reabierto_por        INTEGER REFERENCES usuarios(id),
    reabierto_en         TIMESTAMPTZ,

    CONSTRAINT chk_periodo_fechas CHECK (fecha_limite >= fecha_inicio),
    CONSTRAINT chk_periodicidad_solo_indicadores CHECK (
        (tipo = 'indicadores' AND periodicidad IS NOT NULL) OR
        (tipo = 'poa' AND periodicidad IS NULL)
    ),
    UNIQUE (tipo, anio, etiqueta)
);

CREATE INDEX idx_periodos_tipo_estado ON periodos(tipo, estado);
CREATE INDEX idx_periodos_fecha_limite ON periodos(fecha_limite) WHERE estado = 'abierto';
