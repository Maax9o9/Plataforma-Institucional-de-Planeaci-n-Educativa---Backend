-- ============================================================
-- 0015 - Idempotencia de notificaciones
-- Modulo dueno: modules/notifications (EP-11)
-- ============================================================

ALTER TABLE notificaciones
    ADD COLUMN IF NOT EXISTS origen_evento_id UUID;

CREATE UNIQUE INDEX IF NOT EXISTS uq_notificaciones_evento_idempotente
    ON notificaciones(usuario_id, tipo, origen_evento_id)
    WHERE origen_evento_id IS NOT NULL;
