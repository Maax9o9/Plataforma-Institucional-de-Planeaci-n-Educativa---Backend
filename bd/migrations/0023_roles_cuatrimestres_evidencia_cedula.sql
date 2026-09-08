-- Roles institucionales, calendario propio y evidencia de seguimientos POA.

ALTER TYPE rol ADD VALUE IF NOT EXISTS 'planeacion_admin';
ALTER TYPE rol ADD VALUE IF NOT EXISTS 'capturista_poa';
ALTER TYPE rol ADD VALUE IF NOT EXISTS 'revisor_poa';
ALTER TYPE entidad_flujo ADD VALUE IF NOT EXISTS 'poa_cedula_seguimiento';

CREATE TABLE poa_cedula_cuatrimestres (
    id             SERIAL PRIMARY KEY,
    cedula_id      INTEGER NOT NULL REFERENCES poa_cedulas(id) ON DELETE CASCADE,
    cuatrimestre   SMALLINT NOT NULL,
    periodo_id     INTEGER NOT NULL REFERENCES periodos(id),
    fecha_inicio   DATE NOT NULL,
    fecha_fin      DATE NOT NULL,
    CONSTRAINT chk_poa_cedula_cuatrimestre_numero CHECK (cuatrimestre IN (1, 2, 3)),
    CONSTRAINT chk_poa_cedula_cuatrimestre_fechas CHECK (fecha_fin > fecha_inicio),
    UNIQUE (cedula_id, cuatrimestre),
    UNIQUE (periodo_id)
);

CREATE INDEX idx_poa_cedula_cuatrimestres_cedula
    ON poa_cedula_cuatrimestres(cedula_id);

ALTER TABLE poa_cedula_seguimientos ADD COLUMN progreso TEXT;
ALTER TABLE poa_cedula_seguimientos ADD COLUMN alcance TEXT;

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
    ELSIF NEW.entidad::text = 'poa_cedula_seguimiento' THEN
        IF NOT EXISTS (SELECT 1 FROM poa_cedula_seguimientos WHERE id = NEW.entidad_id) THEN
            RAISE EXCEPTION 'entidad_id % no existe en poa_cedula_seguimientos', NEW.entidad_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
