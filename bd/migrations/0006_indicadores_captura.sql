-- ============================================================
-- 0006 · Captura de avances de indicadores
-- Módulo dueño: modules/indicators_capture  (EP-02)
-- Nota: los campos pct_avance / semaforo son escritos por
-- modules/indicators_scoring (EP-04) a través del puerto
-- ICaptureRepository.actualizar_evaluacion(), NO por acceso
-- directo a esta tabla desde otro módulo. Ver INTEGRACION_BD.md.
-- ============================================================

CREATE TABLE capturas (
    id                  SERIAL PRIMARY KEY,
    indicador_id        INTEGER NOT NULL REFERENCES indicadores(id),
    periodo_id          INTEGER NOT NULL REFERENCES periodos(id),
    capturista_id       INTEGER NOT NULL REFERENCES usuarios(id),
    resultado           NUMERIC(18,4),                 -- obligatorio para enviar (HU-02.01)
    datos_fuente        TEXT,
    actividad_realizada TEXT,
    observaciones       TEXT,
    estado              estado_captura NOT NULL DEFAULT 'borrador',
    pct_avance          NUMERIC(6,2),   -- HU-04.03: calculado y congelado al validar
    semaforo            semaforo,       -- según umbrales vigentes al validar
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (indicador_id, periodo_id)
);

CREATE INDEX idx_capturas_periodo ON capturas(periodo_id);
CREATE INDEX idx_capturas_capturista_estado ON capturas(capturista_id, estado);
CREATE INDEX idx_capturas_indicador ON capturas(indicador_id);

-- SUGERENCIA: útil para el "Reporte de Indicadores sin Captura" (HU-05.08)
-- y para el panel personal del capturista (HU-02.02): consulta directa
-- de "qué le falta a quién" sin tener que escanear toda la tabla.
CREATE INDEX idx_capturas_estado ON capturas(estado) WHERE estado IN ('borrador', 'enviado');
