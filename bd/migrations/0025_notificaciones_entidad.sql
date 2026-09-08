-- Las notificaciones también apuntan a periodos; no son sólo vínculos de evidencia.
-- Conservar todas las referencias históricas al ampliar el tipo.
ALTER TABLE notificaciones
    ALTER COLUMN entidad TYPE VARCHAR(60) USING entidad::text;
