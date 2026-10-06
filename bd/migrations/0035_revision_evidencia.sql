-- Dictamen de Planeacion sobre cada evidencia.
--
-- El informe cuatrimestral ya se valida o se devuelve entero. Esto es mas
-- fino: Planeacion puede decir, archivo por archivo, si la evidencia sostiene
-- lo que el area reporto. Sirve para que el area sepa cual repone sin tener
-- que adivinar a partir de un comentario general.
--
-- No bloquea nada a proposito. El dictamen del informe sigue siendo uno solo
-- -validar o devolver con motivo-, y meter un segundo candado sobre las piezas
-- dejaria al area trabada sin saber cual de los dos la detiene. La marca
-- informa el dictamen; no lo sustituye ni lo condiciona.

CREATE TYPE estado_revision_evidencia AS ENUM ('pendiente', 'aprobada', 'rechazada');

ALTER TABLE evidencias
    ADD COLUMN estado_revision estado_revision_evidencia NOT NULL DEFAULT 'pendiente',
    ADD COLUMN revisado_por INTEGER REFERENCES usuarios(id),
    ADD COLUMN revisado_en TIMESTAMPTZ,
    ADD COLUMN comentario_revision TEXT;

-- Rechazar sin motivo deja al area adivinando que corregir, que es justo lo
-- que esta marca viene a evitar. Aprobar no necesita explicacion.
ALTER TABLE evidencias ADD CONSTRAINT chk_evidencia_rechazo_con_motivo
    CHECK (
        estado_revision <> 'rechazada'
        OR (comentario_revision IS NOT NULL AND btrim(comentario_revision) <> '')
    );

-- Quien dictamina y cuando van juntos: una evidencia revisada sin autor o sin
-- fecha no se puede auditar.
ALTER TABLE evidencias ADD CONSTRAINT chk_evidencia_revision_completa
    CHECK (
        estado_revision = 'pendiente'
        OR (revisado_por IS NOT NULL AND revisado_en IS NOT NULL)
    );

COMMENT ON COLUMN evidencias.estado_revision IS
    'Dictamen de Planeacion sobre la evidencia. Informa el dictamen del informe; no lo bloquea.';
COMMENT ON COLUMN evidencias.comentario_revision IS
    'Por que no sirve. Obligatorio al rechazar: el area lo lee para saber que reponer.';
