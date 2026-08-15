-- ============================================================
-- 0001 · Extensiones y tipos ENUM
-- Módulo dueño: shared (no pertenece a ninguna épica específica,
-- es infraestructura usada por todos los módulos)
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid() para jti, tokens, etc.

CREATE TYPE rol AS ENUM (
    'planeacion',        -- Dirección de Planeación / admin_sistema (EP-00)
    'responsable_area',
    'rectoria',
    'consulta'
);

CREATE TYPE periodicidad AS ENUM (
    'mensual', 'trimestral', 'cuatrimestral', 'anual'
);

CREATE TYPE tipo_periodo AS ENUM (
    'indicadores', 'poa'
);

CREATE TYPE estado_periodo AS ENUM (
    'abierto', 'cerrado'
);

CREATE TYPE estado_captura AS ENUM (
    'borrador', 'enviado', 'validado', 'rechazado'
);

CREATE TYPE semaforo AS ENUM (
    'verde', 'amarillo', 'rojo'
);

CREATE TYPE tipo_evidencia AS ENUM (
    'archivo', 'enlace'
);

CREATE TYPE entidad_flujo AS ENUM (
    'captura',      -- captura de indicador (Módulo 1)
    'poa_avance'    -- avance cuatrimestral (Módulo 2)
);

-- SUGERENCIA (no estaba en el diagrama original): tipar las notificaciones
-- en vez de dejar 'tipo' como varchar libre, para poder filtrar/paginar
-- de forma confiable y evitar strings mal escritos en el código de negocio.
CREATE TYPE tipo_notificacion AS ENUM (
    'apertura_periodo',
    'validacion',
    'rechazo',
    'recordatorio_5d',
    'recordatorio_3d',
    'recordatorio_2d',
    'recordatorio_1d'
);
