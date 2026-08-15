-- ============================================================
-- 0012 - Reportes generados y dashboard institucional
-- Modulos duenos: indicators_reports / poa_reports / dashboards
-- ============================================================

CREATE TABLE reportes_generados (
    id              BIGSERIAL PRIMARY KEY,
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),
    tipo            VARCHAR(100) NOT NULL,
    parametros      JSONB,
    formato         VARCHAR(20) NOT NULL,
    ruta_o_url      VARCHAR(500),
    generado_en     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_reportes_generados_usuario_fecha
    ON reportes_generados(usuario_id, generado_en DESC);

CREATE MATERIALIZED VIEW mv_avance_institucional_indicadores AS
SELECT
    areas.id AS area_id,
    areas.nombre AS area_nombre,
    periodos.id AS periodo_id,
    periodos.anio,
    COUNT(capturas.id) AS capturas_total,
    COUNT(capturas.id) FILTER (WHERE capturas.estado = 'validado') AS capturas_validadas,
    COALESCE(
        AVG(capturas.pct_avance) FILTER (WHERE capturas.estado = 'validado'),
        0
    )::NUMERIC(6, 2) AS pct_avance_promedio
FROM areas
CROSS JOIN periodos
LEFT JOIN indicadores
    ON indicadores.area_id = areas.id
LEFT JOIN capturas
    ON capturas.indicador_id = indicadores.id
   AND capturas.periodo_id = periodos.id
GROUP BY areas.id, areas.nombre, periodos.id, periodos.anio;

CREATE UNIQUE INDEX uq_mv_avance_institucional_indicadores
    ON mv_avance_institucional_indicadores(area_id, periodo_id);
