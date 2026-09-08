-- Los borradores existentes conservan sus datos. Planeación completa el bloque de firmas.
ALTER TABLE poa_cedulas ADD COLUMN tipo_estrategia varchar(40);
ALTER TABLE poa_cedulas ADD COLUMN firmantes json NOT NULL DEFAULT '[]'::json;
ALTER TABLE poa_cedulas ADD CONSTRAINT ck_poa_tipo_estrategia CHECK (
    tipo_estrategia IN ('Eficiencia', 'Eficacia', 'Pertinencia', 'Vinculación', 'Equidad de Género')
);
ALTER TABLE poa_cedula_indicadores ALTER COLUMN porcentaje_alcanzado TYPE numeric(18,4);
-- Evita modificar el enum dentro de una transacción y permite nuevos eventos del dominio.
DROP INDEX uq_notificaciones_recordatorio_unico;
ALTER TABLE notificaciones ALTER COLUMN tipo TYPE varchar(60) USING tipo::text;
CREATE UNIQUE INDEX uq_notificaciones_recordatorio_unico
    ON notificaciones(usuario_id, tipo, entidad, entidad_id)
    WHERE tipo IN ('recordatorio_5d', 'recordatorio_3d', 'recordatorio_2d', 'recordatorio_1d');
ALTER TABLE notificaciones ADD COLUMN correo_reservado_hasta timestamptz;
