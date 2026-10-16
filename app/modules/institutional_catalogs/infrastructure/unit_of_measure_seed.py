"""Semilla del catalogo de unidades de medida de las actividades del POA.

Los mismos 20 registros alimentan la migracion 0032 (INSERT literal, para
PostgreSQL) y el repositorio en memoria: se definen una sola vez aqui para
que ambas implementaciones no se desincronicen. Vienen del Excel
institucional (herramienta poa-import, unidades-medida.json) y mezclan a
proposito la unidad de los indicadores del PSE (siempre "Porcentaje"), la de
los indicadores complementarios y la de las actividades del POA, porque la
institucion las reutiliza entre si.
"""

from __future__ import annotations

UNIDADES_MEDIDA_SEMILLA: tuple[dict[str, str], ...] = (
    {"clave": "porcentaje", "nombre": "Porcentaje", "plural": "Porcentaje"},
    {"clave": "informe", "nombre": "Informe", "plural": "Informes"},
    {"clave": "alumno", "nombre": "Alumno", "plural": "Alumnos"},
    {"clave": "curso", "nombre": "Curso", "plural": "Cursos"},
    {"clave": "documento", "nombre": "Documento", "plural": "Documentos"},
    {"clave": "estudiante", "nombre": "Estudiante", "plural": "Estudiantes"},
    {"clave": "evento", "nombre": "Evento", "plural": "Eventos"},
    {"clave": "profesor", "nombre": "Profesor", "plural": "Profesores"},
    {"clave": "certificacion", "nombre": "Certificación", "plural": "Certificaciones"},
    {"clave": "campana", "nombre": "Campaña", "plural": "Campañas"},
    {"clave": "certificado", "nombre": "Certificado", "plural": "Certificados"},
    {"clave": "convenio", "nombre": "Convenio", "plural": "Convenios"},
    {
        "clave": "educando-alfabetizado",
        "nombre": "Educando alfabetizado",
        "plural": "Educandos alfabetizados",
    },
    {"clave": "equipo", "nombre": "Equipo", "plural": "Equipos"},
    {"clave": "espacio", "nombre": "Espacio", "plural": "Espacios"},
    {"clave": "mujer-atendida", "nombre": "Mujer atendida", "plural": "Mujeres atendidas"},
    {"clave": "mujer-becada", "nombre": "Mujer becada", "plural": "Mujeres becadas"},
    {
        "clave": "nodess-registrado",
        "nombre": "NODESS registrado",
        "plural": "NODESS registrados",
    },
    {"clave": "personal", "nombre": "Personal", "plural": "Personal"},
    {"clave": "proyecto", "nombre": "Proyecto", "plural": "Proyectos"},
)
