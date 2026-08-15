-- ============================================================
-- 0003 · Catálogos institucionales transversales
-- Módulo dueño: modules/institutional_catalogs  (EP-00 · F0.2)
-- ============================================================

CREATE TABLE areas (
    id      SERIAL PRIMARY KEY,
    nombre  VARCHAR(200) NOT NULL UNIQUE,
    activo  BOOLEAN NOT NULL DEFAULT TRUE       -- HU-00.04: se desactiva, nunca se elimina
);

-- Ahora sí se puede cerrar la referencia usuarios -> areas (0002 la dejó suelta)
ALTER TABLE usuarios
    ADD CONSTRAINT fk_usuarios_area FOREIGN KEY (area_id) REFERENCES areas(id);

CREATE TABLE instrumentos (
    id      SERIAL PRIMARY KEY,
    nombre  VARCHAR(100) NOT NULL UNIQUE,       -- PIDE, SEAES, COCODI, Institucional
    activo  BOOLEAN NOT NULL DEFAULT TRUE        -- HU-00.05: no se elimina si tiene indicadores asociados
);

CREATE TABLE criterios_seaes (
    id      SERIAL PRIMARY KEY,
    clave   VARCHAR(50)  NOT NULL UNIQUE,
    nombre  VARCHAR(300) NOT NULL,
    activo  BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE tipos_indicador (
    id      SERIAL PRIMARY KEY,
    nombre  VARCHAR(100) NOT NULL UNIQUE
);

-- HU-04.01: umbrales globales de semaforización. Fila única (id = 1).
CREATE TABLE config_sistema (
    id                      SMALLINT PRIMARY KEY DEFAULT 1,
    umbral_verde_min        SMALLINT NOT NULL DEFAULT 90,
    umbral_amarillo_min     SMALLINT NOT NULL DEFAULT 40,
    actualizado_en          TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_por         INTEGER REFERENCES usuarios(id),
    CONSTRAINT chk_fila_unica CHECK (id = 1),
    CONSTRAINT chk_umbrales_orden CHECK (umbral_amarillo_min < umbral_verde_min)
);

INSERT INTO config_sistema (id) VALUES (1);
