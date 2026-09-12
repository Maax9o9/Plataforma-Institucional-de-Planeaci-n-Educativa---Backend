-- Catalogo de unidades de medida de las actividades del POA.
--
-- La unidad de medida de una actividad la define la institucion, no el
-- catalogo federal (PSE): hoy se teclea libre en cada actividad, y por eso el
-- Excel institucional trae "Informe" e "Informes" como si fueran cosas
-- distintas. Este catalogo existe para ofrecer las unidades ya usadas, no
-- para obligarlas.
--
-- Las 20 unidades sembradas se extrajeron del Excel institucional
-- (herramienta poa-import, unidades-medida.json) y mezclan a proposito tres
-- fuentes distintas que la institucion reutiliza entre si:
--   - los indicadores oficiales del PSE, cuya unidad siempre es "Porcentaje";
--   - los indicadores complementarios (Alumnos, Certificaciones, Espacios...);
--   - las unidades propias de las actividades del POA (Informes, Cursos,
--     Documentos...).
-- Las tres alimentan el mismo catalogo porque en el Excel una unidad de
-- actividad (p. ej. "Curso") tambien aparece como unidad de un indicador
-- complementario: en la practica institucional no son catalogos separados.
--
-- La actividad sigue guardando su unidad como texto libre, no como llave
-- foranea a esta tabla: volverla llave rompería las cedulas que ya existen,
-- cuyas unidades se escribieron libres antes de que este catalogo existiera,
-- y no aporta nada hoy que el texto libre con sugerencias no de ya.

CREATE TABLE unidades_medida (
    id      SERIAL PRIMARY KEY,
    clave   VARCHAR(50)  NOT NULL UNIQUE,
    nombre  VARCHAR(100) NOT NULL,
    plural  VARCHAR(100) NOT NULL,
    activo  BOOLEAN NOT NULL DEFAULT TRUE,
    version INTEGER NOT NULL DEFAULT 1
);

INSERT INTO unidades_medida (clave, nombre, plural) VALUES
    ('porcentaje', 'Porcentaje', 'Porcentaje'),
    ('informe', 'Informe', 'Informes'),
    ('alumno', 'Alumno', 'Alumnos'),
    ('curso', 'Curso', 'Cursos'),
    ('documento', 'Documento', 'Documentos'),
    ('estudiante', 'Estudiante', 'Estudiantes'),
    ('evento', 'Evento', 'Eventos'),
    ('profesor', 'Profesor', 'Profesores'),
    ('certificacion', 'Certificación', 'Certificaciones'),
    ('campana', 'Campaña', 'Campañas'),
    ('certificado', 'Certificado', 'Certificados'),
    ('convenio', 'Convenio', 'Convenios'),
    ('educando-alfabetizado', 'Educando alfabetizado', 'Educandos alfabetizados'),
    ('equipo', 'Equipo', 'Equipos'),
    ('espacio', 'Espacio', 'Espacios'),
    ('mujer-atendida', 'Mujer atendida', 'Mujeres atendidas'),
    ('mujer-becada', 'Mujer becada', 'Mujeres becadas'),
    ('nodess-registrado', 'NODESS registrado', 'NODESS registrados'),
    ('personal', 'Personal', 'Personal'),
    ('proyecto', 'Proyecto', 'Proyectos');
