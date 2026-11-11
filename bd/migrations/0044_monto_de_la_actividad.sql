-- ============================================================
-- 0044 · La actividad del POA del area lleva su monto solicitado
-- Modulo dueno: modules/poa_institucional
-- ============================================================
--
-- El formato oficial que entrego el area trae una columna «Monto solicitado»
-- por actividad y un renglon de «Total» al pie. Hasta la 0043 el sistema no
-- guardaba ningun importe, de modo que esa columna se imprimia en $0.00 y el
-- documento salia incompleto: la parte que la Direccion de Planeacion
-- Educativa usa para pedir el presupuesto era justo la que habia que llenar a
-- mano despues de imprimirlo.
--
-- NUMERIC(16,2) Y NO LA PRECISION DE LAS METAS. Una meta admite cuatro
-- decimales porque se reparte entre doce meses y el residuo tiene que caber;
-- un importe en pesos no se reparte, se suma, y dos decimales son los centavos.
-- Guardarlo con cuatro invitaria a capturar fracciones de centavo que ningun
-- oficio puede justificar.
--
-- NULO SIGNIFICA «TODAVIA NO SE CAPTURO», Y CERO SIGNIFICA «NO PIDE DINERO».
-- Son cosas distintas y el formato las imprime igual ($0.00), pero la pantalla
-- las distingue: la actividad sin capturar queda pendiente y la de cero esta
-- terminada. Por eso la columna admite nulo y las actividades que ya existen
-- se quedan en nulo en lugar de nacer en cero.

ALTER TABLE poa_inst_actividades
    ADD COLUMN IF NOT EXISTS monto_solicitado NUMERIC(16, 2);

ALTER TABLE poa_inst_actividades
    DROP CONSTRAINT IF EXISTS ck_poa_inst_actividad_monto_no_negativo;

ALTER TABLE poa_inst_actividades
    ADD CONSTRAINT ck_poa_inst_actividad_monto_no_negativo
    CHECK (monto_solicitado IS NULL OR monto_solicitado >= 0);
