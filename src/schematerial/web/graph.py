"""The structural graph of one schema, laid out once at ingestion.

A node is a class. An edge is either inheritance -- the first source base is the
backbone, every later one a mixin, exactly as the detail panel reports them --
or containment, where a locally declared attribute's range is another class.
Containment is drawn at the class that declares it rather than repeated on every
subclass that inherits it, so an edge always says where the structure was
written.

Every edge stays inside one schema. Both endpoints must be classes of the same
converted document; a base the conversion never produced has no node and so has
no edge, rather than a dangling one.

Layout is deterministic and happens here, at ingestion, next to everything else
the preview prepares. Positions therefore never depend on a viewport, a
selection or a hover, and identical documents produce identical coordinates.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from schematerial.identity import element_id

__all__ = ["build_graph", "empty_graph", "layer_positions"]

# Enough room for a class box and its name at the default zoom.
COLUMN = 240
ROW = 130
# A layer wider than this wraps onto further rows of its own. Real schemas are
# shallow and wide -- one masterdata module has 115 classes with no base at all
# -- and a single row of those would be a strip 27,000 pixels long that no
# amount of zooming makes readable.
MAX_COLUMNS = 12


def _depths(keys: Sequence[str], bases: Mapping[str, Sequence[str]]) -> dict[str, int]:
    """How far each class sits below a root, following every base, not the first.

    A cycle in the source bases cannot deepen a class forever: an edge that
    closes back onto a class already being resolved contributes nothing, so the
    walk terminates. Where the members of a cycle land relative to each other is
    then arbitrary but fixed; anything descending from the cycle still sits
    below all of it.
    """
    known = set(keys)
    depth: dict[str, int] = {}
    resolving: set[str] = set()

    def of(key: str) -> int:
        cached = depth.get(key)
        if cached is not None:
            return cached
        if key in resolving:
            return 0
        resolving.add(key)
        parents = [base for base in bases.get(key, ()) if base in known and base != key]
        value = 0 if not parents else 1 + max(of(base) for base in parents)
        resolving.discard(key)
        depth[key] = value
        return value

    for key in keys:
        of(key)
    return depth


def layer_positions(
    keys: Sequence[str], names: Mapping[str, str], bases: Mapping[str, Sequence[str]]
) -> dict[str, tuple[int, int]]:
    """Place every class on the layer its inheritance depth puts it on.

    Within a layer, classes are ordered by the average position of the parents
    they descend from, which pulls a child towards its bases and keeps the
    inheritance edges short; ties break on name and then on key, so the result
    is one fixed arrangement rather than one of several equally good ones. A
    layer wider than `MAX_COLUMNS` wraps onto further rows, and the layers below
    it move down by however many rows it took, so a class still sits below every
    base it descends from.
    """
    known = set(keys)
    depth = _depths(keys, bases)
    layers: dict[int, list[str]] = {}
    for key in keys:
        layers.setdefault(depth[key], []).append(key)

    order: dict[str, int] = {}
    positions: dict[str, tuple[int, int]] = {}
    top = 0
    for level in sorted(layers):
        members = layers[level]
        if level == 0:
            members = sorted(members, key=lambda key: (names.get(key, key), key))
        else:

            def barycentre(key: str) -> float:
                placed = [
                    order[base]
                    for base in bases.get(key, ())
                    if base in known and base in order
                ]
                # A class whose bases are all on this same layer has nothing to
                # be pulled towards; it sorts by name among its peers.
                return sum(placed) / len(placed) if placed else float("inf")

            members = sorted(
                members, key=lambda key: (barycentre(key), names.get(key, key), key)
            )
        for place, key in enumerate(members):
            order[key] = place
            positions[key] = (
                (place % MAX_COLUMNS) * COLUMN,
                top + (place // MAX_COLUMNS) * ROW,
            )
        top += -(-len(members) // MAX_COLUMNS) * ROW
    return positions


def build_graph(
    schema: str,
    prefix: str,
    keys: Sequence[str],
    names: Mapping[str, str],
    bases: Mapping[str, Sequence[str]],
    containment: Sequence[tuple[str, str, str]],
    attributes: Mapping[str, int],
    diagnostics: Mapping[str, int],
) -> dict[str, Any]:
    """Assemble the nodes, the edges and the extent of one schema's graph.

    `containment` carries `(owner, attribute name, target)` for locally declared
    attributes whose range is another class. `keys` are the class keys of one
    converted document, and no identifier from anywhere else can enter here.
    """
    known = set(keys)
    ordered = sorted(keys, key=lambda key: (names.get(key, key), key))
    positions = layer_positions(ordered, names, bases)

    nodes: list[dict[str, Any]] = []
    for key in ordered:
        x, y = positions[key]
        nodes.append(
            {
                "id": element_id(prefix, (key,)),
                "key": key,
                "name": names.get(key, key),
                "x": x,
                "y": y,
                "attributes": attributes.get(key, 0),
                "diagnostics": diagnostics.get(key, 0),
            }
        )

    edges: list[dict[str, Any]] = []
    for key in ordered:
        source = element_id(prefix, (key,))
        for position, base in enumerate(bases.get(key, ())):
            if base not in known or base == key:
                continue
            # First base is the backbone the conversion made `is_a`; the rest
            # became mixins. The distinction is real and is kept on the edge.
            kind = "is_a" if position == 0 else "mixin"
            edges.append(
                {
                    "id": f"{kind}:{key}->{base}",
                    "source": source,
                    "target": element_id(prefix, (base,)),
                    "kind": kind,
                    "label": None,
                }
            )
    for owner, name, target in containment:
        if owner not in known or target not in known:
            continue
        edges.append(
            {
                "id": f"contains:{owner}.{name}->{target}",
                "source": element_id(prefix, (owner,)),
                "target": element_id(prefix, (target,)),
                "kind": "contains",
                "label": name,
            }
        )
    edges.sort(key=lambda edge: edge["id"])

    return {
        "schema": schema,
        "nodes": nodes,
        "edges": edges,
        "width": max((node["x"] for node in nodes), default=0) + COLUMN,
        "height": max((node["y"] for node in nodes), default=0) + ROW,
    }


def empty_graph(schema: str) -> dict[str, Any]:
    """What a refused import has: no nodes, and no pretence of structure."""
    return {"schema": schema, "nodes": [], "edges": [], "width": 0, "height": 0}
