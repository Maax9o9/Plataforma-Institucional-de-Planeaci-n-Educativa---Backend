"""Directorio mínimo aprobado: correo, área/unidad exacta y rol del sistema."""

from __future__ import annotations

from ..domain.directory import DirectoryAssignment, InstitutionalDirectory
from ..domain.value_objects import Role


def _assignment(email: str, code: str, area: str, *roles: Role) -> DirectoryAssignment:
    return DirectoryAssignment(
        email=email,
        area_code=code,
        exact_area_name=area,
        roles=frozenset(roles),
    )


DIRECTORY_ASSIGNMENTS = (
    _assignment("rectoria@upchiapas.edu.mx", "DIR-001", "Rectoría", Role.CONSULTA),
    _assignment("brodriguez@upchiapas.edu.mx", "DIR-001", "Rectoría", Role.CAPTURISTA_POA),
    _assignment(
        "juridico@upchiapas.edu.mx",
        "DIR-002",
        "Abogacía General / Unidad de Transparencia",
        Role.CAPTURISTA_POA,
    ),
    _assignment(
        "up_comunicacion@upchiapas.edu.mx",
        "DIR-003",
        "Coordinación de Promoción y Difusión Universitaria",
        Role.CAPTURISTA_POA,
    ),
    _assignment(
        "coordinacionti@upchiapas.edu.mx",
        "DIR-004",
        "Coordinación de Tecnologías de Información",
        Role.CAPTURISTA_POA,
    ),
    _assignment(
        "igualdaddegenero@upchiapas.edu.mx",
        "DIR-005",
        "Unidad de Igualdad de Género",
        Role.CAPTURISTA_POA,
    ),
    _assignment(
        "secretariaacademica@upchiapas.edu.mx",
        "DIR-006",
        "Secretaría Académica",
        Role.CAPTURISTA_POA,
    ),
    _assignment(
        "vinculacion@upchiapas.edu.mx",
        "DIR-007",
        "Dirección de Vinculación Universitaria",
        Role.CAPTURISTA_POA,
    ),
    _assignment(
        "planeacion@upchiapas.edu.mx",
        "DIR-008",
        "Dirección de Planeación Educativa",
        Role.PLANEACION_ADMIN,
        Role.CAPTURISTA_POA,
        Role.REVISOR_POA,
    ),
    _assignment(
        "posgrado@upchiapas.edu.mx",
        "DIR-009",
        "Dirección de Innovación Educativa, Investigación y Posgrado",
        Role.CAPTURISTA_POA,
    ),
    _assignment(
        "serviciosacademicos@upchiapas.edu.mx",
        "DIR-010",
        "Dirección de Servicios Académicos",
        Role.CAPTURISTA_POA,
    ),
    _assignment(
        "flee@upchiapas.edu.mx",
        "DIR-011",
        "División de Innovación en Tecnologías Avanzadas",
        Role.CAPTURISTA_POA,
    ),
    _assignment(
        "mmorales@upchiapas.edu.mx", "DIR-012", "Ingeniería Mecatrónica", Role.CAPTURISTA_POA
    ),
    _assignment(
        "cdiaz@ids.upchiapas.edu.mx",
        "DIR-013",
        "Ingeniería en Tecnologías de la Información e Innovación Digital",
        Role.CAPTURISTA_POA,
    ),
    _assignment(
        "hrincon@upchiapas.edu.mx",
        "DIR-014",
        "Ingeniería en Manufactura Avanzada",
        Role.CAPTURISTA_POA,
    ),
    _assignment(
        "blopez@upchiapas.edu.mx",
        "DIR-015",
        "División de Salud, Alimentos y Administración",
        Role.CAPTURISTA_POA,
    ),
    _assignment(
        "ysanchez@ia.upchiapas.edu.mx", "DIR-016", "Ingeniería en Alimentos", Role.CAPTURISTA_POA
    ),
    _assignment(
        "esantoyo@upchiapas.edu.mx", "DIR-017", "Ingeniería Biomédica", Role.CAPTURISTA_POA
    ),
    _assignment(
        "gcandela@lage.upchiapas.edu.mx",
        "DIR-018",
        "Licenciatura en Administración",
        Role.CAPTURISTA_POA,
    ),
    _assignment(
        "apenagos@ip.upchiapas.edu.mx",
        "DIR-019",
        "División de Procesos Científicos, Tecnológicos y Sustentables",
        Role.CAPTURISTA_POA,
    ),
    _assignment(
        "ljimenez@upchiapas.edu.mx",
        "DIR-020",
        "Ingeniería Ambiental y Sustentabilidad",
        Role.CAPTURISTA_POA,
    ),
    _assignment(
        "icorzo@ia.upchiapas.edu.mx",
        "DIR-021",
        "Ingeniería en Energía y Desarrollo Sostenible",
        Role.CAPTURISTA_POA,
    ),
    _assignment(
        "nvasques@ip.upchiapas.edu.mx", "DIR-022", "Ingeniería Petrolera", Role.CAPTURISTA_POA
    ),
    _assignment(
        "vgonzalez@im.upchiapas.edu.mx",
        "DIR-023",
        "Ingeniería en Nanotecnología",
        Role.CAPTURISTA_POA,
    ),
    _assignment(
        "sec-admin@upchiapas.edu.mx", "DIR-024", "Secretaría Administrativa", Role.CAPTURISTA_POA
    ),
    _assignment(
        "personal@upchiapas.edu.mx",
        "DIR-025",
        "Dirección de Administración de Personal y Organización",
        Role.CAPTURISTA_POA,
    ),
    _assignment(
        "jmartinez@upchiapas.edu.mx",
        "DIR-026",
        "Dirección de Finanzas y Fideicomisos",
        Role.CAPTURISTA_POA,
    ),
    _assignment(
        "ecastellanos@upchiapas.edu.mx",
        "DIR-027",
        "Dirección de Recursos Materiales e Infraestructura",
        Role.CAPTURISTA_POA,
    ),
    _assignment(
        "hdelacruz@upchiapas.edu.mx",
        "DIR-028",
        "Dirección de Programación y Presupuesto",
        Role.CAPTURISTA_POA,
    ),
)

INSTITUTIONAL_DIRECTORY = InstitutionalDirectory(DIRECTORY_ASSIGNMENTS)
