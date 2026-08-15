-- ============================================================
-- 0011 - Bitacora de negocio inmutable
-- Modulo dueno: modules/audit (EP-12)
-- ============================================================

CREATE TABLE bitacora (
    id              BIGSERIAL PRIMARY KEY,
    usuario_id      INTEGER REFERENCES usuarios(id),
    accion          VARCHAR(100) NOT NULL,
    entidad         VARCHAR(100) NOT NULL,
    entidad_id      INTEGER,
    valor_anterior  JSONB,
    valor_nuevo     JSONB,
    ip_origen       INET,
    fecha           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_bitacora_entidad_fecha
    ON bitacora(entidad, entidad_id, fecha DESC);
CREATE INDEX idx_bitacora_usuario_fecha
    ON bitacora(usuario_id, fecha DESC);

CREATE OR REPLACE FUNCTION fn_bitacora_inmutable() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'La bitacora es inmutable';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_bitacora_inmutable
    BEFORE UPDATE OR DELETE ON bitacora
    FOR EACH ROW EXECUTE FUNCTION fn_bitacora_inmutable();

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_backend') THEN
        EXECUTE 'REVOKE UPDATE, DELETE ON bitacora FROM app_backend';
    END IF;
END
$$;
