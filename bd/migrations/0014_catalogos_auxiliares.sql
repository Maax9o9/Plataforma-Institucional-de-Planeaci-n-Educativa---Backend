-- ============================================================
-- 0014 - Estado de tipos de indicador
-- Modulo dueno: institutional_catalogs (EP-00 / EP-01)
-- ============================================================

ALTER TABLE tipos_indicador
    ADD COLUMN IF NOT EXISTS activo BOOLEAN NOT NULL DEFAULT TRUE;
