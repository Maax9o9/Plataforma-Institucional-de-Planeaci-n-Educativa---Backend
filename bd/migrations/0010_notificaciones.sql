-- ============================================================
-- 0010 · Notificaciones
-- Módulo dueño: modules/notifications  (EP-11)
-- ============================================================

CREATE TABLE notificaciones (
    id                  SERIAL PRIMARY KEY,
    usuario_id          INTEGER NOT NULL REFERENCES usuarios(id),
    tipo                tipo_notificacion NOT NULL,
    entidad             entidad_flujo,          -- opcional: a qué captura/avance se refiere
    entidad_id          INTEGER,
    mensaje             TEXT NOT NULL,
    leida               BOOLEAN NOT NULL DEFAULT FALSE,
    enviada_por_correo  BOOLEAN NOT NULL DEFAULT FALSE,
    fecha               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_notificaciones_usuario_no_leidas
    ON notificaciones(usuario_id, fecha DESC) WHERE leida = FALSE;

-- SUGERENCIA: no estaba en el diagrama original. Sin esta restricción,
-- un reintento del job de recordatorios (Celery/arq) podría duplicar
-- el recordatorio "5 días antes" del mismo elemento para el mismo
-- usuario si el job corre dos veces por un reintento de infraestructura.
CREATE UNIQUE INDEX uq_notificaciones_recordatorio_unico
    ON notificaciones(usuario_id, tipo, entidad, entidad_id)
    WHERE tipo IN ('recordatorio_5d', 'recordatorio_3d', 'recordatorio_2d', 'recordatorio_1d');
