-- ============================================================
-- 0009 · Evidencias y flujo de validación (compartidos)
-- Módulo dueño: modules/evidence_management (NUEVO, ver
-- INTEGRACION_BD.md §3) para evidencias, y
-- modules/indicators_validation + modules/poa_validation para
-- cambios_estado (cada uno filtra por su propio `entidad`).
--
-- Nota de diseño: entidad_id es una FK "lógica" (polimórfica),
-- apunta a capturas.id o poa_avances.id según el valor de
-- `entidad`. PostgreSQL no soporta FK polimórficas nativas;
-- la integridad se garantiza a nivel de aplicación (siempre se
-- escribe a través del puerto del módulo dueño) y reforzada con
-- el trigger de abajo. Ver INTEGRACION_BD.md para la alternativa
-- de "tabla por relación" si en el futuro se requiere integridad
-- referencial estricta a nivel de BD.
-- ============================================================

CREATE TABLE evidencias (
    id          SERIAL PRIMARY KEY,
    nombre      VARCHAR(300) NOT NULL,
    descripcion TEXT         NOT NULL,
    fecha       DATE         NOT NULL,
    tipo        tipo_evidencia NOT NULL,
    subida_por  INTEGER NOT NULL REFERENCES usuarios(id),
    creado_en   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE evidencia_vinculos (
    id              SERIAL PRIMARY KEY,
    evidencia_id    INTEGER NOT NULL REFERENCES evidencias(id) ON DELETE CASCADE,
    entidad         entidad_flujo NOT NULL,
    entidad_id      INTEGER NOT NULL,          -- FK lógica -> capturas.id | poa_avances.id
    vinculado_por   INTEGER NOT NULL REFERENCES usuarios(id),
    fecha           TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (evidencia_id, entidad, entidad_id)
);

CREATE INDEX idx_evidencia_vinculos_entidad ON evidencia_vinculos(entidad, entidad_id);

-- SUGERENCIA: no estaba en el diagrama original. mime_type, tamanio y
-- checksum son necesarios por seguridad (validar que un PDF sea
-- realmente un PDF y no un ejecutable renombrado, detectar duplicados
-- exactos, y permitir invalidar cache de CDN si el contenido cambia).
CREATE TABLE evidencia_versiones (
    id              SERIAL PRIMARY KEY,
    evidencia_id    INTEGER NOT NULL REFERENCES evidencias(id) ON DELETE CASCADE,
    ruta_o_url      VARCHAR(500) NOT NULL,     -- ruta en bucket S3 o URL externa
    mime_type       VARCHAR(100),               -- NULL si tipo = 'enlace'
    tamanio_bytes   BIGINT,
    checksum_sha256 VARCHAR(64),
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),
    fecha           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_evidencia_versiones_evidencia ON evidencia_versiones(evidencia_id, fecha DESC);

CREATE TABLE cambios_estado (
    id          SERIAL PRIMARY KEY,
    entidad     entidad_flujo NOT NULL,
    entidad_id  INTEGER NOT NULL,               -- FK lógica -> capturas.id | poa_avances.id
    de_estado   estado_captura,
    a_estado    estado_captura NOT NULL,
    usuario_id  INTEGER NOT NULL REFERENCES usuarios(id),
    fecha       TIMESTAMPTZ NOT NULL DEFAULT now(),
    comentario  TEXT,                            -- obligatorio en rechazos (validado en aplicación)

    CONSTRAINT chk_comentario_en_rechazo CHECK (
        a_estado <> 'rechazado' OR comentario IS NOT NULL
    )
);

CREATE INDEX idx_cambios_estado_entidad ON cambios_estado(entidad, entidad_id, fecha);

-- ------------------------------------------------------------
-- Trigger de integridad para las FKs polimórficas de esta migración.
-- Sustituye lo que en una BD sin polimorfismo sería una FK real.
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_validar_entidad_flujo() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.entidad = 'captura' THEN
        IF NOT EXISTS (SELECT 1 FROM capturas WHERE id = NEW.entidad_id) THEN
            RAISE EXCEPTION 'entidad_id % no existe en capturas', NEW.entidad_id;
        END IF;
    ELSIF NEW.entidad = 'poa_avance' THEN
        IF NOT EXISTS (SELECT 1 FROM poa_avances WHERE id = NEW.entidad_id) THEN
            RAISE EXCEPTION 'entidad_id % no existe en poa_avances', NEW.entidad_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_evidencia_vinculos_valida_entidad
    BEFORE INSERT OR UPDATE ON evidencia_vinculos
    FOR EACH ROW EXECUTE FUNCTION fn_validar_entidad_flujo();

CREATE TRIGGER trg_cambios_estado_valida_entidad
    BEFORE INSERT OR UPDATE ON cambios_estado
    FOR EACH ROW EXECUTE FUNCTION fn_validar_entidad_flujo();
