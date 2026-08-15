-- ============================================================
-- 0002 · Identidad, roles y seguridad
-- Módulo dueño: modules/identity_access  (EP-00 · F0.1)
-- ============================================================

CREATE TABLE usuarios (
    id                  SERIAL PRIMARY KEY,
    nombre              VARCHAR(200)  NOT NULL,
    correo              VARCHAR(200)  NOT NULL UNIQUE,     -- correo institucional
    hash_password       VARCHAR(255)  NOT NULL,            -- Argon2
    area_id             INTEGER,                           -- FK a areas, se agrega en 0003 (evita ciclo)
    activo              BOOLEAN       NOT NULL DEFAULT TRUE, -- HU-00.02
    notificar_correo    BOOLEAN       NOT NULL DEFAULT TRUE, -- HU-11.03
    creado_en           TIMESTAMPTZ   NOT NULL DEFAULT now(),
    actualizado_en       TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE TABLE usuario_roles (
    usuario_id  INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    rol         rol     NOT NULL,
    PRIMARY KEY (usuario_id, rol)
);

-- ------------------------------------------------------------
-- SUGERENCIA · faltaba en el diagrama original:
-- persistir refresh tokens para poder revocarlos, auditarlos y
-- soportar múltiples sesiones/dispositivos por usuario, alineado
-- con la sección de seguridad de la arquitectura (rotación +
-- revocación de JWT). Redis maneja el "hot path" de blacklist por
-- jti; esta tabla es la fuente de verdad persistente.
-- ------------------------------------------------------------
CREATE TABLE refresh_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    jti             UUID    NOT NULL UNIQUE,       -- debe coincidir con el jti del JWT emitido
    hash_token      VARCHAR(255) NOT NULL,          -- nunca se guarda el token en claro
    user_agent      VARCHAR(300),
    ip_origen       INET,
    emitido_en      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expira_en       TIMESTAMPTZ NOT NULL,
    revocado_en     TIMESTAMPTZ,                    -- NULL = vigente
    reemplazado_por UUID REFERENCES refresh_tokens(id), -- traza la cadena de rotación
    CONSTRAINT chk_revocado_coherente CHECK (
        revocado_en IS NULL OR revocado_en >= emitido_en
    )
);

CREATE INDEX idx_refresh_tokens_usuario ON refresh_tokens(usuario_id) WHERE revocado_en IS NULL;

-- ------------------------------------------------------------
-- SUGERENCIA · faltaba en el diagrama original:
-- bitácora de accesos (login exitoso/fallido), separada de la
-- bitácora de negocio (tabla `bitacora` en 0011). Es información
-- de seguridad (detección de fuerza bruta, accesos sospechosos),
-- no de trazabilidad funcional, y conviene poder purgarla/rotarla
-- con una política distinta a la bitácora de negocio (que es
-- inmutable e indefinida por RN-04).
-- ------------------------------------------------------------
CREATE TABLE bitacora_accesos (
    id              BIGSERIAL PRIMARY KEY,
    usuario_id      INTEGER REFERENCES usuarios(id),   -- NULL si el correo ni siquiera existe
    correo_intentado VARCHAR(200) NOT NULL,
    exitoso         BOOLEAN NOT NULL,
    motivo_fallo    VARCHAR(100),                       -- 'credenciales_invalidas', 'usuario_inactivo', etc.
    ip_origen       INET,
    user_agent      VARCHAR(300),
    fecha           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_bitacora_accesos_usuario_fecha ON bitacora_accesos(usuario_id, fecha DESC);
