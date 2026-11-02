-- ============================================================
-- 0041 · El periodo de captura del POA institucional
-- Modulo dueno: modules/poa_institucional
-- ============================================================
--
-- Planeacion abre el POA institucional de un ejercicio para las areas y fija
-- desde y hasta cuando cada una registra sus actividades. Si un area no
-- entrego, Planeacion le habilita un periodo nuevo. La 0040 dejo
-- `poa_inst_areas` sin ninguna fecha, asi que no habia donde guardar eso.
--
-- UNA FILA POR CADA PERIODO, NO COLUMNAS EN `poa_inst_areas`. La migracion
-- 0004 resolvio la reapertura de un periodo con `motivo_reapertura`,
-- `reabierto_por` y `reabierto_en` en la propia fila, de modo que solo se
-- conserva la ultima. Esta tabla diverge de ese precedente a proposito: nada
-- se sobrescribe y nada desaparece en silencio, y la pregunta "este POA se
-- reabrio dos veces, por que" se contesta leyendo filas en vez de adivinar
-- que habia en la columna anterior.
--
-- `numero` ordena la historia: 1 es el periodo con que se abrio el POA y 2 en
-- adelante son los que se habilitaron despues. El periodo vigente es el del
-- `numero` mas alto. No se usa "el mas reciente por `creado_en`" porque dos
-- filas con la misma marca de tiempo dejarian el orden en manos del motor.

CREATE TABLE poa_inst_aperturas (
    id          SERIAL PRIMARY KEY,
    poa_area_id INTEGER NOT NULL,
    numero      INTEGER NOT NULL,
    desde       DATE NOT NULL,
    hasta       DATE NOT NULL,
    motivo      TEXT,
    abierto_por INTEGER,
    creado_en   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT fk_poa_inst_apertura_poa_area
        FOREIGN KEY (poa_area_id) REFERENCES poa_inst_areas(id) ON DELETE RESTRICT,
    CONSTRAINT fk_poa_inst_apertura_abierto_por
        FOREIGN KEY (abierto_por) REFERENCES usuarios(id) ON DELETE RESTRICT,
    CONSTRAINT uq_poa_inst_apertura_poa_area_numero UNIQUE (poa_area_id, numero),
    -- El primer periodo es el 1 y los siguientes continuan de ahi: un 0 o un
    -- negativo no son un lugar en la historia.
    CONSTRAINT chk_poa_inst_apertura_numero CHECK (numero >= 1),
    -- El primer y el ultimo dia estan dentro del periodo, asi que un periodo
    -- de un solo dia es legal y `hasta = desde` tambien.
    CONSTRAINT chk_poa_inst_apertura_fechas CHECK (hasta >= desde),
    -- Habilitar un periodo nuevo exige decir por que; abrir el POA por primera
    -- vez no tiene motivo previo que explicar. La 0004 anoto que esta regla
    -- solo se podia exigir en la aplicacion: con `numero` en la fila, la base
    -- si la puede exigir.
    CONSTRAINT chk_poa_inst_apertura_motivo_de_la_reapertura
        CHECK (numero = 1 OR motivo IS NOT NULL)
);

CREATE INDEX idx_poa_inst_aperturas_poa_area ON poa_inst_aperturas(poa_area_id);

COMMENT ON COLUMN poa_inst_aperturas.numero IS
    '1 es el periodo con que se abrio el POA y 2 en adelante son los que se habilitaron despues; el vigente es el del numero mas alto.';
COMMENT ON COLUMN poa_inst_aperturas.motivo IS
    'Por que la Direccion de Planeacion habilito un periodo nuevo; obligatorio desde la segunda fila (chk_poa_inst_apertura_motivo_de_la_reapertura).';
COMMENT ON COLUMN poa_inst_aperturas.abierto_por IS
    'Quien abrio el POA o habilito el periodo; nulo significa una sola cosa: se abrio antes de que el sistema registrara quien, y es el caso de las filas que esta migracion derivo.';

-- RELLENO DE LAS FILAS QUE YA EXISTEN. Es derivable, no inventado, y no se
-- borra ninguna fila: cada POA de area que la 0040 dejo abierto recibe su
-- apertura numero 1 con
--
--   desde  = el dia en que se abrio (`creado_en`), que es el unico dia de
--            inicio que consta;
--   hasta  = el 31 de diciembre del ano del ejercicio, porque el POA de un
--            ejercicio se podia capturar durante todo su ano;
--   motivo = nulo, porque es el periodo con que se abrio el POA y no uno
--            habilitado despues;
--   abierto_por = nulo, que significa "se abrio antes de que el sistema
--            registrara quien".
--
-- El `GREATEST` cubre el POA que se abrio despues de terminar el ano de su
-- ejercicio -se puede: `poa_inst_areas` no exige que el ejercicio este en
-- curso-. Sin el, `hasta` quedaria antes de `desde` y
-- `chk_poa_inst_apertura_fechas` rechazaria la fila, que es justo la que no
-- hay que perder.
INSERT INTO poa_inst_aperturas (poa_area_id, numero, desde, hasta, motivo, abierto_por, creado_en)
SELECT
    area.id,
    1,
    area.creado_en::date,
    GREATEST(make_date(ejercicio.anio, 12, 31), area.creado_en::date),
    NULL,
    NULL,
    area.creado_en
FROM poa_inst_areas AS area
JOIN poa_ejercicios AS ejercicio ON ejercicio.id = area.ejercicio_id;
