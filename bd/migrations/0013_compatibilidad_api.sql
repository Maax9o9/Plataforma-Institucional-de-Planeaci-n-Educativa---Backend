-- ============================================================
-- 0013 - Compatibilidad con la API inicial
-- Modulo dueno: shared / identity_access / institutional_catalogs / periods
-- ============================================================

-- La API usa el rol administrativo definido en ARQUITECTURA_BACKEND.md.
ALTER TYPE rol ADD VALUE IF NOT EXISTS 'admin_sistema';

-- Se conserva el estado inicial de borrador usado por el flujo HTTP.
ALTER TYPE estado_periodo ADD VALUE IF NOT EXISTS 'borrador';
-- No se cambia el DEFAULT dentro de esta migracion: PostgreSQL no permite
-- usar un valor ENUM recien agregado hasta que termine la transaccion.
-- La API envia explicitamente el estado al crear el periodo.

-- La API identifica areas por codigo y permite jerarquia.
ALTER TABLE areas
    ADD COLUMN IF NOT EXISTS codigo VARCHAR(30),
    ADD COLUMN IF NOT EXISTS parent_id INTEGER REFERENCES areas(id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_areas_codigo
    ON areas(codigo)
    WHERE codigo IS NOT NULL;

ALTER TABLE instrumentos
    ADD COLUMN IF NOT EXISTS codigo VARCHAR(30),
    ADD COLUMN IF NOT EXISTS descripcion TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_instrumentos_codigo
    ON instrumentos(codigo)
    WHERE codigo IS NOT NULL;

ALTER TABLE tipos_indicador
    ADD COLUMN IF NOT EXISTS activo BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE bitacora
    ADD COLUMN IF NOT EXISTS evento VARCHAR(100);

-- La sesion permite revocar toda la cadena de refresh tokens ante reuso.
ALTER TABLE refresh_tokens
    ADD COLUMN IF NOT EXISTS session_id UUID;

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_session
    ON refresh_tokens(session_id)
    WHERE revocado_en IS NULL;
