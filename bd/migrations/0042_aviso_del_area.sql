-- ============================================================
-- 0042 · El titulo de los avisos dirigidos a un area
-- Modulo dueno: modules/notifications
-- ============================================================
--
-- Planeacion dirige dos avisos a las areas: el que genera la apertura del POA
-- institucional con sus dos fechas, y el que la propia Direccion de Planeacion
-- redacta. Los dos se reparten entre las personas del area por el riel de
-- notificaciones que ya existe, que es por usuario. La 0010 dejo
-- `notificaciones` con `mensaje` y sin titulo, y la campana del frontend
-- necesita un encabezado corto que distinga un aviso de otro en la lista.
--
-- EL TITULO ADMITE NULO Y ESO SIGNIFICA UNA SOLA COSA: la notificacion se creo
-- antes de que los avisos tuvieran titulo. No se inventa uno con las primeras
-- palabras del mensaje ni con el nombre del tipo, porque un titulo derivado se
-- leeria igual que uno capturado y nadie podria distinguirlos despues. Las
-- notificaciones que el sistema genera por su cuenta -las validaciones, los
-- rechazos y los cuatro recordatorios- siguen sin titulo a proposito.
--
-- NO SE AMPLIA `tipo_notificacion`, Y NO ES UN OLVIDO. El enum de siete
-- valores que creo la 0001 sigue existiendo, pero `notificaciones.tipo` dejo de
-- usarlo en la 0026: esa migracion lo cambio a `varchar(60)`
-- (`ALTER COLUMN tipo TYPE varchar(60) USING tipo::text`) justamente para
-- evitar modificar un enum dentro de una transaccion y para admitir tipos
-- nuevos del dominio. Desde entonces ninguna columna de la base usa el enum, y
-- en la tabla ya conviven valores que no son suyos -`poa_actividad_asignada` y
-- `poa_total_inicio`, que escribe el servicio de notificaciones-. Un
-- `ALTER TYPE tipo_notificacion ADD VALUE` aqui seria codigo muerto: no habria
-- columna que lo comprobara. Los dos tipos de esta entrega
-- -`poa_apertura_del_area` y `aviso_de_planeacion`- caben en los 60 caracteres
-- de la columna y entran sin tocar el enum.
--
-- Esta migracion no inserta ninguna fila, asi que la trampa de PostgreSQL por
-- la que un valor nuevo de un enum no se puede usar en la misma transaccion en
-- que se anade no se presenta por ningun lado.

ALTER TABLE notificaciones ADD COLUMN titulo VARCHAR(200);

COMMENT ON COLUMN notificaciones.titulo IS
    'Encabezado corto del aviso, para distinguirlo en la campana; nulo significa una sola cosa: la notificacion se creo antes de que los avisos tuvieran titulo, y no se deriva uno del mensaje.';
