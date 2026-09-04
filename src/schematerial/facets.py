"""Reading, writing and validating the decision 4 facets on a LinkML element.

Decision 4: `semantic_type`, `coordinate_frame`, `per_atom`, `spin_channel` and
`unit_normalized` live in `annotations`, governed by a metamodel extension class
referenced through `instantiates`. That is the only mechanism LinkML offers --
assigning a non-metamodel slot to a schema element is an error, and there is no
way to add slots to `SlotDefinition`.

`instantiates` is what makes the annotations legible. Without it a reader sees
five loose tags and cannot tell them from anybody else's five loose tags.

A facet with no value is absent. Writing None writes nothing, and reading an
absent facet gives None -- never a default, never a guess.
"""

from __future__ import annotations

from collections.abc import Iterator

from linkml_runtime.linkml_model.meta import ClassDefinition, Element, SchemaDefinition

from schematerial._linkml import (
    annotations_of,
    attributes_of,
    classes_of,
    instantiates_of,
    set_annotation,
    slots_of,
)
from schematerial.models.core import CoordinateFrame, MaterialsFacets

__all__ = [
    "FACET_TAGS",
    "MATERIALS_FACETS_CURIE",
    "FacetError",
    "facet_problems",
    "read_facets",
    "validate_schema_facets",
    "write_facets",
]

MATERIALS_FACETS_CURIE = "smat:MaterialsFacets"
"""What an element's `instantiates` points at when it carries facets."""

FACET_TAGS: tuple[str, ...] = tuple(MaterialsFacets.model_fields)

_TRUE = frozenset({"true", "yes", "1"})
_FALSE = frozenset({"false", "no", "0"})


class FacetError(ValueError):
    """A facet value that is not one. Always names the element it came from."""


def _annotation_value(element: Element, tag: str) -> object | None:
    annotation = annotations_of(element).get(tag)
    if annotation is None:
        return None
    return getattr(annotation, "value", annotation)


def _as_bool(raw: object) -> bool | None:
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return None


def _as_int(raw: object) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    try:
        return int(str(raw).strip())
    except ValueError:
        return None


def write_facets(element: Element, facets: MaterialsFacets) -> None:
    """Write the facets that have a value, and point `instantiates` at the class.

    A facet set to None writes no annotation, per decision 4. An element given
    no facets at all is left untouched, `instantiates` included -- pointing at
    the extension class while carrying nothing would be a lie.
    """
    written = False
    for tag in FACET_TAGS:
        value = getattr(facets, tag)
        if value is None:
            continue
        set_annotation(element, tag, str(getattr(value, "value", value)))
        written = True

    if not written:
        return
    instantiates = instantiates_of(element)
    if MATERIALS_FACETS_CURIE not in instantiates:
        instantiates.append(MATERIALS_FACETS_CURIE)


def read_facets(element: Element) -> MaterialsFacets:
    """Read the facets off an element. Absent facets come back as None.

    Values are coerced back out of annotation strings. A value that will not
    coerce is left for `facet_problems` to report rather than being silently
    dropped or repaired here.
    """
    raw_frame = _annotation_value(element, "coordinate_frame")
    frame: CoordinateFrame | None = None
    if raw_frame is not None:
        try:
            frame = CoordinateFrame(str(raw_frame))
        except ValueError:
            frame = None

    per_atom = _annotation_value(element, "per_atom")
    spin_channel = _annotation_value(element, "spin_channel")
    semantic_type = _annotation_value(element, "semantic_type")
    unit_normalized = _annotation_value(element, "unit_normalized")

    return MaterialsFacets(
        semantic_type=None if semantic_type is None else str(semantic_type),
        coordinate_frame=frame,
        per_atom=None if per_atom is None else _as_bool(per_atom),
        spin_channel=None if spin_channel is None else _as_int(spin_channel),
        unit_normalized=None if unit_normalized is None else str(unit_normalized),
    )


def facet_problems(element: Element, element_name: str) -> list[str]:
    """Every bad facet value on one element, each message naming the element."""
    problems: list[str] = []

    def bad(tag: str, raw: object, expected: str) -> None:
        problems.append(f"{element_name}: facet {tag!r} is {raw!r}, expected {expected}.")

    instantiates = instantiates_of(element)
    present = [tag for tag in annotations_of(element) if tag in FACET_TAGS]
    if present and MATERIALS_FACETS_CURIE not in instantiates:
        problems.append(
            f"{element_name}: carries facets {sorted(present)} but does not instantiate "
            f"{MATERIALS_FACETS_CURIE}. Decision 4 is what makes the annotations legible; "
            f"without it they are five loose tags."
        )

    if MATERIALS_FACETS_CURIE in instantiates and not present:
        problems.append(
            f"{element_name}: instantiates {MATERIALS_FACETS_CURIE} but carries no facet. "
            f"A facet with no value is absent, and so is the reference to the class."
        )

    raw = _annotation_value(element, "semantic_type")
    if raw is not None:
        text = str(raw)
        if not text.strip():
            bad("semantic_type", raw, "a non-empty CURIE or URI")
        elif ":" not in text:
            bad(
                "semantic_type",
                raw,
                "a CURIE or URI into QUDT, EMMO or PMDco, such as 'quantitykind:Energy'",
            )

    raw = _annotation_value(element, "coordinate_frame")
    if raw is not None:
        allowed = ", ".join(member.value for member in CoordinateFrame)
        try:
            CoordinateFrame(str(raw))
        except ValueError:
            bad("coordinate_frame", raw, f"one of {allowed}")

    raw = _annotation_value(element, "per_atom")
    if raw is not None and _as_bool(raw) is None:
        bad("per_atom", raw, "a boolean")

    raw = _annotation_value(element, "spin_channel")
    if raw is not None and _as_int(raw) is None:
        bad("spin_channel", raw, "an integer")

    raw = _annotation_value(element, "unit_normalized")
    if raw is not None and not str(raw).strip():
        bad("unit_normalized", raw, "a non-empty UCUM code")

    return problems


def _elements(schema: SchemaDefinition) -> Iterator[tuple[str, Element]]:
    for class_name, class_definition in classes_of(schema).items():
        yield str(class_name), class_definition
        yield from _attributes(str(class_name), class_definition)
    for slot_name, slot in slots_of(schema).items():
        yield str(slot_name), slot


def _attributes(
    class_name: str, class_definition: ClassDefinition
) -> Iterator[tuple[str, Element]]:
    for attribute_name, attribute in attributes_of(class_definition).items():
        yield f"{class_name}.{attribute_name}", attribute


def validate_schema_facets(schema: SchemaDefinition) -> None:
    """Raise if any element in the schema carries a bad facet value.

    The message names every offending element, not just the first, because a
    generated schema is fixed by its adapter and one round trip through the
    adapter per bad value is a waste of a run.
    """
    problems: list[str] = []
    for name, element in _elements(schema):
        problems.extend(facet_problems(element, name))
    if problems:
        raise FacetError(
            f"{schema.name}: {len(problems)} bad facet value(s).\n" + "\n".join(problems)
        )
