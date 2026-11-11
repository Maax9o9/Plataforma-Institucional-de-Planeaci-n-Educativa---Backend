-- ============================================================
-- 0043 · El comunicado es un registro propio y la notificacion es su entrega
-- Modulo dueno: modules/notifications
-- ============================================================
--
-- Hasta la 0042 un aviso era titulo y mensaje repartidos como una fila por
-- persona en `notificaciones`, y nada mas. Un comunicado institucional casi
-- nunca es solo texto: lleva el oficio, el formato que hay que llenar y la
-- fecha en que deja de aplicar. Sin eso la Direccion de Planeacion termina
-- escribiendo «les mando el formato por correo», que es el trabajo que esta
-- plataforma viene a quitar.
--
-- EL PROBLEMA DE FONDO NO ERAN LOS ADJUNTOS, ERA LA AGRUPACION. El reparto
-- calcula `origen_evento_id` por persona
-- (`uuid5(NAMESPACE_URL, f"{clave_del_evento}:{persona}")` en
-- `app/modules/notifications/application/area_notices.py`), asi que dos filas
-- del mismo comunicado no comparten ningun valor por el que agruparlas
-- despues: ni el evento, ni el titulo -que se puede repetir-, ni la fecha
-- -que difiere por fila-. La pregunta que la Direccion de Planeacion hace en
-- cuanto manda un comunicado, «¿quien lo leyo?», no tenia respuesta posible.
-- De ahi la forma de esta migracion: el comunicado pasa a ser una fila de
-- `avisos`, y cada notificacion que nace de el apunta a esa fila. Los adjuntos
-- y la vigencia cuelgan de ella porque son del comunicado y no de la entrega.
--
-- `origen_evento_id` NO SE TOCA NI SE REESCRIBE. Sigue siendo la idempotencia
-- de la entrega persona por persona -`uq_notificaciones_evento_idempotente`-,
-- que es un trabajo distinto del de agrupar: `aviso_id` dice de que comunicado
-- es la fila, y `origen_evento_id` impide que la misma persona reciba dos veces
-- el mismo reparto. Las dos columnas conviven y ninguna sustituye a la otra.

CREATE TABLE avisos (
    id            SERIAL PRIMARY KEY,
    titulo        VARCHAR(200) NOT NULL,
    mensaje       TEXT NOT NULL,
    destino_ruta  VARCHAR(200),
    vigente_hasta DATE,
    creado_por    INTEGER NOT NULL,
    creado_en     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT fk_aviso_creado_por
        FOREIGN KEY (creado_por) REFERENCES usuarios(id) ON DELETE RESTRICT,
    -- Un titulo o un mensaje de espacios pasa el NOT NULL y llega a la campana
    -- como un aviso en blanco. La aplicacion ya los recorta antes de guardar
    -- (`recortado_sin_invisibles`); esto es la red por debajo, para lo que
    -- entre por otra puerta.
    CONSTRAINT chk_aviso_titulo_con_texto CHECK (btrim(titulo) <> ''),
    CONSTRAINT chk_aviso_mensaje_con_texto CHECK (btrim(mensaje) <> ''),
    -- EL DESTINO ES UNA PANTALLA DEL SISTEMA, NO UN SITIO DE FUERA. Quien
    -- redacta escribe el destino y el frontend lo convierte en el enlace que
    -- la persona pulsa dentro del aviso: admitir `https://…` ahi convertiria
    -- un comunicado institucional en un enlace a cualquier parte con el sello
    -- de la Direccion de Planeacion. Una ruta absoluta del sistema empieza por
    -- una sola barra; `//sitio.example.com` se lee como ruta y el navegador la
    -- resuelve como sitio externo, asi que se rechaza aparte.
    CONSTRAINT chk_aviso_destino_del_sistema
        CHECK (destino_ruta IS NULL OR (destino_ruta LIKE '/%' AND destino_ruta NOT LIKE '//%'))
);

COMMENT ON COLUMN avisos.destino_ruta IS
    'Pantalla del sistema a la que se refiere el comunicado, como ruta absoluta del frontend; nulo significa que el comunicado no lleva a ninguna pantalla (chk_aviso_destino_del_sistema impide un sitio de fuera).';
COMMENT ON COLUMN avisos.vigente_hasta IS
    'Ultimo dia en que el comunicado cuenta como pendiente; nulo significa que no vence. Vencido se sigue consultando y no se borra: lo unico que cambia es que deja de aparecer entre lo pendiente.';
COMMENT ON COLUMN avisos.creado_por IS
    'Quien redacto el comunicado. No admite nulo: esta tabla nace con esta migracion y no hay ninguna fila anterior de la que no conste quien la escribio.';

-- LOS ADJUNTOS SON FILAS Y NO COLUMNAS DEL AVISO, porque un comunicado lleva
-- el oficio y el formato, no uno de los dos. La forma es la de
-- `evidencia_versiones` -`ruta_o_url`, `mime_type`, `tamanio_bytes`- a
-- proposito: es el mismo archivo cargado por `POST /archivos` y descrito de la
-- misma manera, y asi una consulta que ya sepa leer una version de evidencia
-- sabe leer un adjunto.
--
-- `ruta_o_url` se llama asi, y no `ruta`, por el mismo motivo que alla: deja
-- sitio a un enlace externo sin otra migracion. Hoy el contrato solo escribe
-- la ruta de un archivo ya cargado, que es lo unico que el sistema puede
-- comprobar.
CREATE TABLE aviso_adjuntos (
    id            SERIAL PRIMARY KEY,
    aviso_id      INTEGER NOT NULL,
    nombre        VARCHAR(300) NOT NULL,
    ruta_o_url    VARCHAR(500) NOT NULL,
    mime_type     VARCHAR(100) NOT NULL,
    tamanio_bytes BIGINT NOT NULL,

    CONSTRAINT fk_aviso_adjunto_aviso
        FOREIGN KEY (aviso_id) REFERENCES avisos(id) ON DELETE CASCADE,
    CONSTRAINT uq_aviso_adjunto_ruta UNIQUE (aviso_id, ruta_o_url),
    CONSTRAINT chk_aviso_adjunto_nombre_con_texto CHECK (btrim(nombre) <> ''),
    -- `POST /archivos` rechaza lo que no reconoce por su firma, asi que un
    -- archivo admitido nunca mide cero bytes: un cero aqui es un adjunto que
    -- se guardo sin su archivo.
    CONSTRAINT chk_aviso_adjunto_tamanio CHECK (tamanio_bytes > 0)
);

CREATE INDEX idx_aviso_adjuntos_aviso ON aviso_adjuntos(aviso_id);

COMMENT ON COLUMN aviso_adjuntos.nombre IS
    'Como se llama el documento para quien lo lee. Lo captura quien redacta: POST /archivos descarta el nombre original del archivo y devuelve solo su ruta.';
COMMENT ON COLUMN aviso_adjuntos.ruta_o_url IS
    'Ruta del archivo ya cargado por POST /archivos, relativa al directorio de cargas. El nombre deja sitio a un enlace externo, que el contrato de hoy no escribe.';
COMMENT ON CONSTRAINT uq_aviso_adjunto_ruta ON aviso_adjuntos IS
    'El mismo archivo dos veces en un comunicado es un descuido de captura, no un adjunto mas; el mismo archivo en dos comunicados distintos si es legitimo.';

-- LA ENTREGA. `aviso_id` ADMITE NULO Y EL NULO SIGNIFICA UNA SOLA COSA: esta
-- notificacion no nacio de un comunicado. Es el caso de todo lo que ya existe
-- en la tabla y de todo lo que el sistema genera por su cuenta -los cuatro
-- recordatorios de vencimiento, las validaciones, los rechazos, la apertura
-- del POA del area y la asignacion de una actividad-. No se rellena con nada
-- derivado: un comunicado inventado a partir de un recordatorio se leeria
-- igual que uno que la Direccion de Planeacion redacto, y las cifras de
-- lectura dejarian de significar lo que dicen.
--
-- ON DELETE RESTRICT y no CASCADE: las entregas son el rastro de quien leyo
-- que, y borrar un comunicado no puede borrar ese rastro en silencio. Si
-- alguna vez hace falta retirar un comunicado, se retira sin borrarlo.
ALTER TABLE notificaciones ADD COLUMN aviso_id INTEGER;

ALTER TABLE notificaciones ADD CONSTRAINT fk_notificacion_aviso
    FOREIGN KEY (aviso_id) REFERENCES avisos(id) ON DELETE RESTRICT;

-- El indice es parcial porque la consulta que lo necesita -las cifras de
-- lectura de un comunicado- nunca busca por nulo, y los nulos son hoy la
-- totalidad de la tabla y seguiran siendo la mayoria.
CREATE INDEX idx_notificaciones_aviso ON notificaciones(aviso_id)
    WHERE aviso_id IS NOT NULL;

COMMENT ON COLUMN notificaciones.aviso_id IS
    'El comunicado del que nacio esta entrega; nulo significa una sola cosa: la notificacion no nacio de un comunicado -un recordatorio, una validacion, un rechazo, la apertura del POA de un area- y no se deriva ninguno.';
