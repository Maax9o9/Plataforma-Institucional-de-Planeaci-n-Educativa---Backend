-- Contrato institucional requerido por la integracion frontend (EP-00).
ALTER TABLE areas
    ADD COLUMN IF NOT EXISTS tipo VARCHAR(30) NOT NULL DEFAULT 'administrativa',
    ADD COLUMN IF NOT EXISTS color VARCHAR(7);

ALTER TABLE areas
    DROP CONSTRAINT IF EXISTS chk_areas_tipo,
    DROP CONSTRAINT IF EXISTS chk_areas_color;

ALTER TABLE areas
    ADD CONSTRAINT chk_areas_tipo
        CHECK (tipo IN ('administrativa', 'programa_educativo')),
    ADD CONSTRAINT chk_areas_color
        CHECK (color IS NULL OR color ~ '^#[0-9A-Fa-f]{6}$');
