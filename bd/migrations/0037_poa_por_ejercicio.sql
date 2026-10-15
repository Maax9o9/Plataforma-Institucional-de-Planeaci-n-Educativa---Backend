-- El catalogo del POA deja de ser uno solo y pasa a tener un dueno: su POA.
--
-- Hasta ahora la clave `1.1` era llave primaria global, asi que solo podia
-- existir una estrategia 1.1 en toda la base, y editar su texto reescribia lo
-- que mostraban las cedulas de todos los anos. A partir de aqui cada POA tiene
-- su catalogo y lo que se edita en uno no toca al otro.

CREATE TABLE poa_catalogos (
    id             SERIAL PRIMARY KEY,
    nombre         VARCHAR(120) NOT NULL UNIQUE,
    anio           SMALLINT NOT NULL,
    -- De donde salio: "subido del archivo X", "copiado del POA 2026",
    -- "capturado a mano". Es lo que deja saber que se esta mirando.
    origen         TEXT,
    creado_por     INTEGER REFERENCES usuarios(id),
    creado_en      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Se mueve cuando cambia el CONTENIDO del catalogo, no solo la cabecera.
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_poa_catalogo_anio CHECK (anio BETWEEN 2000 AND 2200)
);

-- El nombre identifica al POA ante quien lo elige; el ano no, porque de un
-- mismo ano puede haber mas de uno (el que se entrego y el que se esta
-- rearmando).
COMMENT ON COLUMN poa_catalogos.nombre IS
    'Como se nombra el POA al elegirlo. Unico; el ano no lo es.';

-- El POA que recoge todo lo que ya existia. El archivo que siembra el catalogo
-- actual se llama literalmente "Catalogos POA 2026".
INSERT INTO poa_catalogos (nombre, anio, origen)
VALUES ('POA 2026', 2026, 'Catálogo inicial del sistema');

-- 1. Las cuatro tablas del catalogo ganan su dueno.
ALTER TABLE poa_catalogo_objetivos   ADD COLUMN catalogo_id INTEGER;
ALTER TABLE poa_catalogo_estrategias ADD COLUMN catalogo_id INTEGER;
ALTER TABLE poa_catalogo_indicadores ADD COLUMN catalogo_id INTEGER;
ALTER TABLE poa_catalogo_actividades ADD COLUMN catalogo_id INTEGER;

UPDATE poa_catalogo_objetivos   SET catalogo_id = (SELECT id FROM poa_catalogos WHERE nombre = 'POA 2026');
UPDATE poa_catalogo_estrategias SET catalogo_id = (SELECT id FROM poa_catalogos WHERE nombre = 'POA 2026');
UPDATE poa_catalogo_indicadores SET catalogo_id = (SELECT id FROM poa_catalogos WHERE nombre = 'POA 2026');
UPDATE poa_catalogo_actividades SET catalogo_id = (SELECT id FROM poa_catalogos WHERE nombre = 'POA 2026');

ALTER TABLE poa_catalogo_objetivos   ALTER COLUMN catalogo_id SET NOT NULL;
ALTER TABLE poa_catalogo_estrategias ALTER COLUMN catalogo_id SET NOT NULL;
ALTER TABLE poa_catalogo_indicadores ALTER COLUMN catalogo_id SET NOT NULL;
ALTER TABLE poa_catalogo_actividades ALTER COLUMN catalogo_id SET NOT NULL;

-- 2. El ejercicio y las tres tablas de cedula que apuntan al catalogo.
ALTER TABLE poa_ejercicios           ADD COLUMN catalogo_id INTEGER;
ALTER TABLE poa_cedulas              ADD COLUMN catalogo_id INTEGER;
ALTER TABLE poa_cedula_indicadores   ADD COLUMN catalogo_id INTEGER;
ALTER TABLE poa_cedula_actividades   ADD COLUMN catalogo_id INTEGER;

UPDATE poa_ejercicios         SET catalogo_id = (SELECT id FROM poa_catalogos WHERE nombre = 'POA 2026');
UPDATE poa_cedulas            SET catalogo_id = (SELECT id FROM poa_catalogos WHERE nombre = 'POA 2026');
UPDATE poa_cedula_indicadores SET catalogo_id = (SELECT id FROM poa_catalogos WHERE nombre = 'POA 2026');
UPDATE poa_cedula_actividades SET catalogo_id = (SELECT id FROM poa_catalogos WHERE nombre = 'POA 2026');

ALTER TABLE poa_ejercicios         ALTER COLUMN catalogo_id SET NOT NULL;
ALTER TABLE poa_cedulas            ALTER COLUMN catalogo_id SET NOT NULL;
ALTER TABLE poa_cedula_indicadores ALTER COLUMN catalogo_id SET NOT NULL;
ALTER TABLE poa_cedula_actividades ALTER COLUMN catalogo_id SET NOT NULL;

ALTER TABLE poa_ejercicios
    ADD CONSTRAINT fk_poa_ejercicio_catalogo
    FOREIGN KEY (catalogo_id) REFERENCES poa_catalogos(id);

-- 3. Rehacer las llaves del catalogo: la clave pasa a ser unica DENTRO del POA.
--    Se sueltan primero las foraneas que apuntan a ellas.
ALTER TABLE poa_cedulas              DROP CONSTRAINT IF EXISTS fk_poa_cedula_estrategia_objetivo;
ALTER TABLE poa_cedula_indicadores   DROP CONSTRAINT IF EXISTS poa_cedula_indicadores_indicador_clave_fkey;
ALTER TABLE poa_cedula_actividades   DROP CONSTRAINT IF EXISTS poa_cedula_actividades_actividad_clave_fkey;
ALTER TABLE poa_catalogo_estrategias DROP CONSTRAINT IF EXISTS poa_catalogo_estrategias_objetivo_numero_fkey;
ALTER TABLE poa_catalogo_indicadores DROP CONSTRAINT IF EXISTS poa_catalogo_indicadores_objetivo_numero_fkey;
ALTER TABLE poa_catalogo_actividades DROP CONSTRAINT IF EXISTS poa_catalogo_actividades_estrategia_clave_fkey;
ALTER TABLE poa_catalogo_estrategias DROP CONSTRAINT IF EXISTS poa_catalogo_estrategias_clave_objetivo_numero_key;

-- La clave del objetivo tambien deja de valer en todo el sistema. Mientras esa
-- unica exista, dos POA no pueden tener un objetivo con la misma clave, y
-- copiar un POA entero -lo que viene despues de esta entrega- es exactamente
-- eso.
ALTER TABLE poa_catalogo_objetivos   DROP CONSTRAINT IF EXISTS poa_catalogo_objetivos_clave_key;

ALTER TABLE poa_catalogo_objetivos   DROP CONSTRAINT poa_catalogo_objetivos_pkey;
ALTER TABLE poa_catalogo_estrategias DROP CONSTRAINT poa_catalogo_estrategias_pkey;
ALTER TABLE poa_catalogo_indicadores DROP CONSTRAINT poa_catalogo_indicadores_pkey;
ALTER TABLE poa_catalogo_actividades DROP CONSTRAINT poa_catalogo_actividades_pkey;

ALTER TABLE poa_catalogo_objetivos   ADD PRIMARY KEY (catalogo_id, numero);
ALTER TABLE poa_catalogo_estrategias ADD PRIMARY KEY (catalogo_id, clave);
ALTER TABLE poa_catalogo_indicadores ADD PRIMARY KEY (catalogo_id, clave);
ALTER TABLE poa_catalogo_actividades ADD PRIMARY KEY (catalogo_id, clave);

ALTER TABLE poa_catalogo_objetivos
    ADD CONSTRAINT uq_poa_catalogo_objetivo_clave UNIQUE (catalogo_id, clave);

-- La unica que respalda la foranea de tres columnas de la cedula (bloque 4).
CREATE UNIQUE INDEX uq_poa_catalogo_estrategia_objetivo
    ON poa_catalogo_estrategias (catalogo_id, clave, objetivo_numero);

ALTER TABLE poa_catalogo_objetivos
    ADD CONSTRAINT fk_poa_catalogo_objetivo_catalogo
    FOREIGN KEY (catalogo_id) REFERENCES poa_catalogos(id) ON DELETE CASCADE;

-- Dentro del catalogo, cada hijo referencia a su padre llevando el POA consigo.
ALTER TABLE poa_catalogo_estrategias
    ADD CONSTRAINT fk_poa_catalogo_estrategia_objetivo
    FOREIGN KEY (catalogo_id, objetivo_numero)
    REFERENCES poa_catalogo_objetivos(catalogo_id, numero) ON DELETE CASCADE;

ALTER TABLE poa_catalogo_indicadores
    ADD CONSTRAINT fk_poa_catalogo_indicador_objetivo
    FOREIGN KEY (catalogo_id, objetivo_numero)
    REFERENCES poa_catalogo_objetivos(catalogo_id, numero) ON DELETE CASCADE;

ALTER TABLE poa_catalogo_actividades
    ADD CONSTRAINT fk_poa_catalogo_actividad_estrategia
    FOREIGN KEY (catalogo_id, estrategia_clave)
    REFERENCES poa_catalogo_estrategias(catalogo_id, clave) ON DELETE CASCADE;

-- 4. Que la cedula no pueda apuntar al catalogo de otro ano. Es declarativo a
--    proposito: un disparador habria que recordar mantenerlo.
CREATE UNIQUE INDEX uq_poa_ejercicio_catalogo ON poa_ejercicios (id, catalogo_id);

ALTER TABLE poa_cedulas
    ADD CONSTRAINT fk_poa_cedula_ejercicio_catalogo
    FOREIGN KEY (ejercicio_id, catalogo_id)
    REFERENCES poa_ejercicios (id, catalogo_id);

-- Lleva las tres columnas y no dos: ademas de atar la estrategia a su POA,
-- conserva lo que ya garantizaba `fk_poa_cedula_estrategia_objetivo`, que el
-- `objetivo_numero` de la cedula sea el del objetivo de su estrategia. Con dos
-- columnas esa garantia se habria aflojado sin que nada lo avisara.
ALTER TABLE poa_cedulas
    ADD CONSTRAINT fk_poa_cedula_estrategia
    FOREIGN KEY (catalogo_id, estrategia_clave, objetivo_numero)
    REFERENCES poa_catalogo_estrategias (catalogo_id, clave, objetivo_numero);

CREATE UNIQUE INDEX uq_poa_cedula_catalogo ON poa_cedulas (id, catalogo_id);

-- Las dos foraneas hacia la cedula van ON DELETE CASCADE porque la que ya
-- existia por `cedula_id` tambien lo esta. Si una cascada y la otra no, borrar
-- una cedula depende de cual de las dos revise Postgres primero -el orden de
-- los disparadores RI, que va por nombre y lleva el OID dentro-, y el
-- endpoint que borra cedulas quedaria fallando segun la base.
ALTER TABLE poa_cedula_indicadores
    ADD CONSTRAINT fk_poa_cedula_indicador_cedula_catalogo
    FOREIGN KEY (cedula_id, catalogo_id) REFERENCES poa_cedulas (id, catalogo_id) ON DELETE CASCADE;
ALTER TABLE poa_cedula_indicadores
    ADD CONSTRAINT fk_poa_cedula_indicador_catalogo
    FOREIGN KEY (catalogo_id, indicador_clave)
    REFERENCES poa_catalogo_indicadores (catalogo_id, clave);

ALTER TABLE poa_cedula_actividades
    ADD CONSTRAINT fk_poa_cedula_actividad_cedula_catalogo
    FOREIGN KEY (cedula_id, catalogo_id) REFERENCES poa_cedulas (id, catalogo_id) ON DELETE CASCADE;
ALTER TABLE poa_cedula_actividades
    ADD CONSTRAINT fk_poa_cedula_actividad_catalogo
    FOREIGN KEY (catalogo_id, actividad_clave)
    REFERENCES poa_catalogo_actividades (catalogo_id, clave);

CREATE INDEX idx_poa_catalogo_estrategias_catalogo ON poa_catalogo_estrategias (catalogo_id);
CREATE INDEX idx_poa_catalogo_indicadores_catalogo ON poa_catalogo_indicadores (catalogo_id);
CREATE INDEX idx_poa_catalogo_actividades_catalogo ON poa_catalogo_actividades (catalogo_id);
