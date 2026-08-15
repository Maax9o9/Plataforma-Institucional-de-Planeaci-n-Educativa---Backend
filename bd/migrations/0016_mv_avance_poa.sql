-- ============================================================
-- 0016 - Vista materializada para dashboard institucional POA
-- Modulo dueno: modules/dashboards (EP-10)
-- ============================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_avance_institucional_poa AS
SELECT
    pp.area_id,
    pa.periodo_id,
    COUNT(*) AS total_avances,
    COUNT(*) FILTER (WHERE pa.estado = 'validado') AS validadas,
    COUNT(*) FILTER (WHERE pa.estado = 'enviado') AS enviadas,
    COUNT(*) FILTER (WHERE pa.estado = 'borrador') AS en_borrador,
    COUNT(*) FILTER (WHERE pa.estado = 'rechazado') AS rechazadas,
    ROUND(AVG(pa.pct_cumplimiento) FILTER (WHERE pa.estado = 'validado'), 2)
        AS pct_cumplimiento_promedio
FROM poa_avances pa
JOIN poa_actividades act ON act.id = pa.actividad_id
JOIN poa_objetivos obj ON obj.id = act.objetivo_id
JOIN poa_procesos pp ON pp.id = obj.proceso_id
GROUP BY pp.area_id, pa.periodo_id;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_avance_poa
    ON mv_avance_institucional_poa(area_id, periodo_id);
