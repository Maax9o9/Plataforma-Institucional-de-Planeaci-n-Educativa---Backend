-- El instrumento deja de ser un nombre y pasa a tener su arbol.
--
-- `instrumentos` guarda un instrumento como una fila -nombre, codigo,
-- descripcion, version y una bandera-, sin nada que diga que ejes, objetivos o
-- acciones lo componen. En una base recien migrada esa tabla esta VACIA: el
-- PIDE no esta sembrado y lo carga la tarea 4. El POA institucional cuelga de
-- esos niveles, asi que el arbol tiene que vivir en la base y no en un
-- documento que alguien lee.
--
-- Dos tablas y una columna.
--   instrumento_versiones  cada edicion de un instrumento. El arbol cuelga de
--                          una version y no del instrumento, para que cargar la
--                          siguiente no toque lo que la anterior dejo dicho.
--   nodos_estrategicos     el arbol de una version, con su padre explicito.
--   indicadores.nodo_id    a que nodo responde un indicador. Es opcional: los
--                          que ya existen no lo traen y siguen siendo validos.
--
-- El capitulo VII del PIDE tiene cinco niveles -eje, objetivo general,
-- objetivo especifico, linea estrategica y accion- y sus claves llegan a cinco
-- segmentos (1.1.1.1.1). Por eso el padre es una columna y el nivel es un dato:
-- el ancestro de un nodo se consulta, nunca se deriva partiendo su clave. La
-- clave la fija el documento fuente y no se usa para ordenar, ni exige formato
-- numerico (E1.L2.A3 es una clave valida). El orden entre hermanos es `orden`.
--
-- No hay borrado, se desactiva. Todas las foraneas son ON DELETE RESTRICT: una
-- fila que ya se usa se conserva, porque lo que cuelga de ella -un nodo, un
-- indicador, mas adelante las actividades de un area- dejaria de saber a que
-- respondia.

CREATE TABLE instrumento_versiones (
    id             SERIAL PRIMARY KEY,
    instrumento_id INTEGER NOT NULL,
    etiqueta       VARCHAR(120) NOT NULL,
    vigente_desde  DATE NOT NULL,
    -- NULL mientras la version esta en borrador.
    publicada_en   TIMESTAMPTZ,
    CONSTRAINT fk_instrumento_version_instrumento
        FOREIGN KEY (instrumento_id) REFERENCES instrumentos(id) ON DELETE RESTRICT,
    -- La etiqueta es lo que distingue una version de otra ante quien la elige.
    -- Tambien es lo que permite cargar el instrumento mas de una vez sin
    -- duplicar su cabecera.
    CONSTRAINT uq_instrumento_version_etiqueta UNIQUE (instrumento_id, etiqueta)
);

CREATE TABLE nodos_estrategicos (
    id           SERIAL PRIMARY KEY,
    version_id   INTEGER NOT NULL,
    -- NULL solo en la raiz del arbol.
    padre_id     INTEGER,
    tipo         VARCHAR(30) NOT NULL,
    clave        VARCHAR(50) NOT NULL,
    denominacion TEXT NOT NULL,
    orden        INTEGER NOT NULL,
    activo       BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_nodo_estrategico_version
        FOREIGN KEY (version_id) REFERENCES instrumento_versiones(id) ON DELETE RESTRICT,

    -- Existe solo para que la foranea del padre pueda llevar la version.
    CONSTRAINT uq_nodo_estrategico_id_version UNIQUE (id, version_id),

    -- El padre es de la misma version que el hijo. Con una foranea de solo
    -- `padre_id`, una accion de la version 2 podria colgar de una linea de la
    -- version 1, y el arbol de cada version dejaria de ser suyo. Con `padre_id`
    -- NULL la foranea no se evalua, asi que la raiz entra sin padre.
    CONSTRAINT fk_nodo_estrategico_padre
        FOREIGN KEY (padre_id, version_id)
        REFERENCES nodos_estrategicos(id, version_id) ON DELETE RESTRICT,

    -- Dos hermanos no repiten clave. NULLS NOT DISTINCT (PostgreSQL 15 o mas)
    -- es lo que cubre a los ejes: no tienen padre, y en una UNIQUE comun dos
    -- NULL no se consideran iguales, asi que el eje 1 podria cargarse dos veces
    -- en la misma version.
    CONSTRAINT uq_nodo_estrategico_hermano_clave
        UNIQUE NULLS NOT DISTINCT (version_id, padre_id, clave),

    -- Son los cinco niveles que el capitulo VII usa de verdad. Si aparece otro,
    -- el CHECK se amplia con una migracion.
    CONSTRAINT chk_nodo_estrategico_tipo CHECK (
        tipo IN (
            'eje',
            'objetivo_general',
            'objetivo_especifico',
            'linea_estrategica',
            'accion'
        )
    )
);

COMMENT ON COLUMN instrumento_versiones.vigente_desde IS
    'Desde cuando rige esta version del instrumento.';
COMMENT ON COLUMN instrumento_versiones.publicada_en IS
    'Cuando se publico. NULL mientras esta en borrador.';

COMMENT ON COLUMN nodos_estrategicos.padre_id IS
    'De quien cuelga. Es la unica fuente de la jerarquia: el ancestro se consulta, no se deriva de la clave.';
COMMENT ON COLUMN nodos_estrategicos.tipo IS
    'El nivel del nodo. Es un dato y no una posicion en el arbol.';
COMMENT ON COLUMN nodos_estrategicos.clave IS
    'La fija el documento fuente. Admite digitos, puntos y letras; no se usa para ordenar.';
COMMENT ON COLUMN nodos_estrategicos.orden IS
    'Posicion entre sus hermanos. La clave no ordena.';
COMMENT ON COLUMN nodos_estrategicos.activo IS
    'Si se puede elegir al formular. Retirarlo no afecta a lo que ya cuelga de el.';

-- El indicador responde a un nodo del arbol. Opcional: los que ya existen no
-- cuelgan de ninguno.
ALTER TABLE indicadores ADD COLUMN nodo_id INTEGER;
ALTER TABLE indicadores
    ADD CONSTRAINT fk_indicador_nodo
    FOREIGN KEY (nodo_id) REFERENCES nodos_estrategicos(id) ON DELETE RESTRICT;

COMMENT ON COLUMN indicadores.nodo_id IS
    'Nodo del arbol de un instrumento al que responde este indicador. NULL si no responde a ninguno.';
