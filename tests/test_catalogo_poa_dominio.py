"""El POA como entidad: lo que no puede valer cualquier cosa."""

import pytest

from app.modules.poa_planning.domain.cedula_entities import PoaCatalogo
from app.shared.domain.exceptions import ValidationError


def test_el_nombre_es_obligatorio():
    # Sin nombre no hay forma de distinguir un POA de otro en el selector, que
    # es lo único que Planeación ve.
    with pytest.raises(ValidationError):
        PoaCatalogo.create(name="   ", year=2027, origin=None, created_by=1)


def test_el_anio_tiene_que_ser_plausible():
    with pytest.raises(ValidationError):
        PoaCatalogo.create(name="POA 1999", year=1999, origin=None, created_by=1)


def test_nace_con_su_origen_y_sus_fechas():
    poa = PoaCatalogo.create(name="POA 2027", year=2027, origin="capturado a mano", created_by=7)
    assert poa.name == "POA 2027"
    assert poa.origin == "capturado a mano"
    assert poa.created_by == 7
    assert poa.created_at == poa.updated_at
