-- Persistencia de revocacion de access tokens entre reinicios y despliegues.
CREATE TABLE access_tokens_revocados (
    jti UUID PRIMARY KEY,
    expira_en TIMESTAMPTZ NOT NULL,
    revocado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_access_tokens_revocados_expira
    ON access_tokens_revocados (expira_en);
