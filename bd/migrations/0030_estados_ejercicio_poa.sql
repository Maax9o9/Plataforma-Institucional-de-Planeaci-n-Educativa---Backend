-- Estados y fecha limite del ejercicio POA.
--
-- El ejercicio era solo un anio: no sabia si estaba formulandose, aprobado por
-- Rectoria o cerrado, ni hasta cuando se podia editar. Sin eso no hay ciclo.
--
-- A diferencia del seguimiento cuatrimestral (migracion 0027), el ejercicio NO
-- reutiliza el enum `estado_captura` para su propio estado: un POA aprobado no
-- se queda quieto como una captura validada, entra en vigor y despues se
-- cierra. Por eso `estado_ejercicio_poa` es un vocabulario propio con
-- 'vigente' y 'cerrado' en vez de 'validado'.
--
-- El ciclo de revision si se comparte (enviar, aprobar, devolver con motivo) y
-- el historial tambien: las transiciones se siguen registrando en
-- `cambios_estado` con la entidad `poa_ejercicio`, igual que 0023 hizo con
-- `poa_cedula_seguimiento`. Como esa tabla tipa `de_estado`/`a_estado` con
-- `estado_captura`, ese enum compartido crece con 'vigente' y 'cerrado' -- son
-- valores del historial, no del estado propio del ejercicio.

CREATE TYPE estado_ejercicio_poa AS ENUM (
    'borrador', 'enviado', 'vigente', 'cerrado'
);

ALTER TYPE entidad_flujo ADD VALUE IF NOT EXISTS 'poa_ejercicio';
ALTER TYPE estado_captura ADD VALUE IF NOT EXISTS 'vigente';
ALTER TYPE estado_captura ADD VALUE IF NOT EXISTS 'cerrado';

ALTER TABLE poa_ejercicios
    ADD COLUMN estado estado_ejercicio_poa NOT NULL DEFAULT 'borrador',
    ADD COLUMN fecha_limite_formulacion DATE,
    ADD COLUMN comentario_revision TEXT,
    ADD COLUMN cerrado_en TIMESTAMPTZ;

CREATE INDEX idx_poa_ejercicios_estado ON poa_ejercicios(estado);

COMMENT ON COLUMN poa_ejercicios.fecha_limite_formulacion IS
    'Hasta cuando Planeacion puede editar la estructura. La referencia es el 20 de febrero.';
COMMENT ON COLUMN poa_ejercicios.comentario_revision IS
    'Motivo con el que Rectoria devolvio el POA. Obligatorio al devolver.';

-- El trigger de integridad de `cambios_estado` (migracion 0009, extendido en
-- 0023) valida que entidad_id exista en la tabla propietaria de esa entidad. Se
-- agrega la rama de poa_ejercicio para que siga cubriendo la FK logica.
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
    ELSIF NEW.entidad::text = 'poa_ejercicio' THEN
        IF NOT EXISTS (SELECT 1 FROM poa_ejercicios WHERE id = NEW.entidad_id) THEN
            RAISE EXCEPTION 'entidad_id % no existe en poa_ejercicios', NEW.entidad_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
