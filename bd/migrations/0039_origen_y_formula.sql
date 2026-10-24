-- De donde salio una version del instrumento, y con que se mide cada accion.
--
-- Dos huecos de la 0038 que su propio brief no vio. Van aqui y no editando la
-- 0038 porque esa ya esta comprometida: quien la haya aplicado no volveria a
-- aplicarla, y el esquema de las dos bases dejaria de ser el mismo.
--
--   instrumento_versiones.origen        de donde salio esta edicion.
--   nodos_estrategicos.formula_indicador con que se mide una accion.

-- El backlog pide conservar «vigencia, origen» de lo que se carga. La vigencia
-- ya esta en `vigente_desde`; el origen no tenia donde. Va en la version y no
-- en el nodo porque lo que tiene procedencia es la edicion del documento: el
-- PDF del que se cargo, la captura a mano, la copia de la version anterior. Es
-- lo mismo que `poa_catalogos.origen` de la 0037 y por la misma razon: lo que
-- deja saber que se esta mirando.
ALTER TABLE instrumento_versiones ADD COLUMN origen TEXT;

COMMENT ON COLUMN instrumento_versiones.origen IS
    'De donde salio esta edicion: "cargada del PDF del PIDE 2025-2030", "capturada a mano". Es lo que deja saber que se esta mirando.';

-- Cada accion del capitulo VII trae su indicador como una formula en texto
-- («Nº de estudiantes... / Nº total... x 100»). No puede vivir en
-- `indicadores`: esa tabla exige `area_id` y `responsable_id` NOT NULL
-- (0005:18-19), y la formula del PIDE es institucional, de nadie en
-- particular; el cargador tendria que inventar un area y un responsable para
-- guardarla. Y no puede ir en `denominacion`, porque entonces el nombre de la
-- accion y su medida quedan pegados en una cadena sin forma de separarlos otra
-- vez.
--
-- Nulable porque solo las acciones la traen: un eje o un objetivo no se miden
-- con una formula. Es TEXT y no se valida aqui -no es una expresion que el
-- sistema evalue, es lo que el documento dice-.
ALTER TABLE nodos_estrategicos ADD COLUMN formula_indicador TEXT;

COMMENT ON COLUMN nodos_estrategicos.formula_indicador IS
    'La formula con que el PIDE mide esta accion, tal como la imprime el documento. NULL en los niveles que no se miden.';
