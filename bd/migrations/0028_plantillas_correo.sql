CREATE TABLE plantillas_correo (
    tipo varchar(60) PRIMARY KEY,
    contenido jsonb NOT NULL,
    version integer NOT NULL,
    actualizado_por integer NOT NULL,
    actualizado_en timestamptz NOT NULL
);
