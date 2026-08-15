-- ============================================================
-- 0017 - Invitacion de configuracion inicial de contrasena
-- Modulo dueno: identity_access (seguridad de usuarios)
-- ============================================================

ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS requiere_configurar_contrasena BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS tokens_configuracion_contrasena (
    id UUID PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    hash_token VARCHAR(64) NOT NULL UNIQUE,
    expira_en TIMESTAMPTZ NOT NULL,
    usado_en TIMESTAMPTZ,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tokens_contrasena_usuario
    ON tokens_configuracion_contrasena(usuario_id)
    WHERE usado_en IS NULL;
