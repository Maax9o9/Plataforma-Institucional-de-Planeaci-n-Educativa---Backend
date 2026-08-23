-- Contratos administrativos y control de concurrencia para integracion frontend.
ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS ultimo_acceso TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

ALTER TABLE areas
    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

ALTER TABLE instrumentos
    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

ALTER TABLE criterios_seaes
    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

ALTER TABLE tipos_indicador
    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

ALTER TABLE periodos
    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

ALTER TABLE capturas
    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS idx_capturas_actualizado_id
    ON capturas (actualizado_en DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_indicadores_actualizado_id
    ON indicadores (actualizado_en DESC, id DESC);
