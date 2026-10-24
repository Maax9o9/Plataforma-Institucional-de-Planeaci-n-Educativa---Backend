"""El árbol de un instrumento: sus nodos y las reglas que no dependen de dónde se guarden.

El capítulo VII del PIDE tiene cinco niveles -eje, objetivo general, objetivo
específico, línea estratégica y acción-, y un nodo sabe de quién cuelga por su
`parent_id`. La clave de un nodo («E1.L2.A3») la fija el documento fuente y no
dice nada de sus ancestros: la jerarquía se consulta, nunca se deriva de ella.

Hay dos adaptadores, memoria y PostgreSQL. La base impone un `CHECK` sobre el
nivel, una `UNIQUE` sobre la clave entre hermanos y una foránea compuesta sobre
el padre; la memoria no tiene esquema. Lo que no necesita saber dónde se guarda
vive aquí, y los dos adaptadores lo llaman: así la regla es una y los mensajes
también. Lo que sí necesita el almacén -¿ya existe esa clave entre los
hermanos?- lo resuelve cada adaptador a su manera, y la prueba exige que
respondan lo mismo.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from app.shared.domain.exceptions import ConflictError, InvalidStateError, ValidationError

#: `clave` es `VARCHAR(50)` en la base.
KEY_MAX_LENGTH = 50


class NodeKind(StrEnum):
    """Los cinco niveles, de arriba a abajo.

    El valor es la cadena que admite el `CHECK` de la migración 0038: el
    adaptador SQL la escribe tal cual. El nivel es un dato del nodo y no una
    posición en el árbol.
    """

    EJE = "eje"
    OBJETIVO_GENERAL = "objetivo_general"
    OBJETIVO_ESPECIFICO = "objetivo_especifico"
    LINEA_ESTRATEGICA = "linea_estrategica"
    ACCION = "accion"


_DEPTH_BY_DECLARATION_ORDER = {kind: posicion for posicion, kind in enumerate(NodeKind)}
_KINDS_FROM_TOP_TO_BOTTOM = " → ".join(kind.value for kind in NodeKind)


@dataclass(kw_only=True)
class StrategicNode:
    """Un nodo del árbol de una versión de un instrumento.

    `id` es 0 mientras el nodo no se haya guardado; `add` lo asigna. `order` es
    la posición entre hermanos: la clave no ordena.
    """

    id: int = 0
    version_id: int
    parent_id: int | None
    kind: NodeKind
    key: str
    name: str
    order: int
    is_active: bool = True
    indicator_formula: str | None = None

    def validate(self) -> None:
        """Normaliza `kind`: acepta la cadena de un JSON y la deja como `NodeKind`,
        para que los dos adaptadores devuelvan el mismo tipo. No se llama al
        construir sino al guardar: leer una fila ya escrita no debe fallar por
        una regla que la base nunca impuso.
        """
        try:
            self.kind = NodeKind(self.kind)
        except ValueError:
            raise ValidationError(
                f"El nivel «{self.kind}» no es uno de los cinco del instrumento: "
                + ", ".join(kind.value for kind in NodeKind)
                + "."
            ) from None
        if not self.key.strip():
            raise ValidationError("La clave del nodo es obligatoria.")
        if len(self.key) > KEY_MAX_LENGTH:
            raise ValidationError(
                f"La clave del nodo no puede superar {KEY_MAX_LENGTH} caracteres."
            )
        if not self.name.strip():
            raise ValidationError("La denominación del nodo es obligatoria.")


def in_traversal_order(nodes: Iterable[StrategicNode]) -> list[StrategicNode]:
    """Los nodos de una versión en orden de recorrido: cada padre, y enseguida
    cada hijo con toda su descendencia antes del siguiente hermano.

    Los hermanos van por `order` y, si empatan, por `id` -el orden en que se
    cargaron-: ni la clave ni el nombre ordenan.

    Sólo se llega a un nodo bajando desde una raíz, así que el recorrido no
    puede girar. Lo que no se alcanza no se omite: se levanta
    `InvalidStateError`. Un nodo existe y no aparece es lo peor que le puede
    pasar a un sistema que tiene que acreditar cifras ante una revisión
    externa, y con la foránea del padre puesta la única forma de no alcanzar un
    nodo es que alguien haya escrito un ciclo por fuera -lo que, además,
    esconde a todo lo que cuelga de él aunque no sea parte del ciclo-.
    """
    children: defaultdict[int | None, list[StrategicNode]] = defaultdict(list)
    recibidos: list[StrategicNode] = []
    for node in nodes:
        recibidos.append(node)
        children[node.parent_id].append(node)
    for siblings in children.values():
        siblings.sort(key=lambda node: (node.order, node.id))

    ordered: list[StrategicNode] = []
    pending = list(reversed(children[None]))
    while pending:
        node = pending.pop()
        ordered.append(node)
        pending.extend(reversed(children[node.id]))

    if len(ordered) != len(recibidos):
        alcanzados = {node.id for node in ordered}
        perdidos = sorted(node.id for node in recibidos if node.id not in alcanzados)
        raise InvalidStateError(
            f"El árbol tiene un ciclo: {len(perdidos)} nodos no se alcanzan bajando "
            f"desde ninguna raíz y quedarían fuera del listado sin decirlo "
            f"(ids {', '.join(str(perdido) for perdido in perdidos)})."
        )
    return ordered


def ensure_parent_fits(node: StrategicNode, upward: list[StrategicNode]) -> None:
    """El padre existe y es de la misma versión que el nodo.

    `upward` es lo que el almacén encontró subiendo desde `node.parent_id`: el
    padre y luego sus ancestros, del más cercano al más lejano; vacía si el padre
    no existe. Es lo que en PostgreSQL impone la foránea compuesta
    `(padre_id, version_id)`: un nodo no cuelga de un padre de otra versión.
    """
    if node.parent_id is None:
        return
    if not upward:
        raise ValidationError("El padre del nodo no existe.")
    if upward[0].version_id != node.version_id:
        raise ValidationError("El padre del nodo es de otra versión.")


def ensure_no_cycle(node: StrategicNode, upward: list[StrategicNode]) -> None:
    """Mover `node` bajo su nuevo padre no lo vuelve ancestro de sí mismo.

    Se sube desde el nuevo padre, con lo que ya está guardado: si por el camino
    aparece el propio nodo, el nuevo padre es él mismo o un descendiente suyo.
    La base no lo impide -una foránea compuesta acepta un ciclo-, así que se
    detecta antes de escribir.
    """
    if any(ancestor.id == node.id for ancestor in upward):
        raise ValidationError("Un nodo no puede colgar de sí mismo ni de uno de sus descendientes.")


def ensure_kind_fits_under(node: StrategicNode, parent: StrategicNode | None) -> None:
    if parent is None:
        return
    if _DEPTH_BY_DECLARATION_ORDER[node.kind] > _DEPTH_BY_DECLARATION_ORDER[parent.kind]:
        return
    raise ValidationError(
        f"Un nodo de nivel «{node.kind.value}» no puede colgar de uno de nivel "
        f"«{parent.kind.value}»: el hijo va más abajo que su padre en "
        f"{_KINDS_FROM_TOP_TO_BOTTOM}."
    )


def ensure_children_stay_deeper(node: StrategicNode, children: Iterable[StrategicNode]) -> None:
    que_dejarian_de_ir_mas_abajo = [
        child
        for child in children
        if _DEPTH_BY_DECLARATION_ORDER[child.kind] <= _DEPTH_BY_DECLARATION_ORDER[node.kind]
    ]
    if not que_dejarian_de_ir_mas_abajo:
        return
    raise ValidationError(
        f"«{node.key}» no puede pasar al nivel «{node.kind.value}»: "
        f"{len(que_dejarian_de_ir_mas_abajo)} de los nodos que cuelgan de él dejarían "
        "de ir más abajo que su padre. Cambie primero el nivel de esos nodos."
    )


def ensure_parent_is_active(node: StrategicNode, parent: StrategicNode | None) -> None:
    if parent is None or parent.is_active:
        return
    raise ValidationError(
        f"«{node.key}» quedaría colgando de «{parent.key}», que está retirado: "
        "lo retirado no se puede elegir al formular. Reactive primero el padre."
    )


def ensure_nothing_active_hangs(node: StrategicNode, children: Iterable[StrategicNode]) -> None:
    activos = [child for child in children if child.is_active]
    if not activos:
        return
    raise ValidationError(
        f"«{node.key}» no se puede retirar: {len(activos)} nodos activos cuelgan de él "
        "y quedarían ofreciéndose bajo algo retirado. Retire primero lo que cuelga."
    )


def repeated_key_error(node: StrategicNode) -> ConflictError:
    entre_quienes = (
        "bajo ese padre" if node.parent_id is not None else "entre las raíces de la versión"
    )
    return ConflictError(f"Ya existe un nodo con la clave «{node.key}» {entre_quienes}.")
