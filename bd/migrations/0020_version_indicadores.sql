-- Concurrencia optimista del catalogo maestro.
ALTER TABLE indicadores
    ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
