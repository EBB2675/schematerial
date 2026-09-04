"""Element identity and snapshot. Decisions 1 and 2.

Every schema element gets a stable CURIE, ``<prefix>:<QualifiedName>``, where
the qualified name is the dotted path from the top-level class. The path is a
**schema** path and carries no indices: ``Run.calculation.energy.total.value``,
never ``run[0].calculation[-1].energy.total.value``. Anything an index was
expressing is a cardinality on the slot or a note on a mapping row.

A segment may itself contain a dot, so the dotted string form is escaped:
``.`` becomes ``%2E`` and ``%`` becomes ``%25``. Percent-encoding keeps the id
a legal CURIE reference and makes the reverse parser exact. Only the uppercase
forms are canonical, so one element has exactly one id.

Alongside the CURIE, an element carries an :class:`ElementSnapshot`: name,
parent, range, unit, semantic type and the source version it was seen in. It is
a record, not a hash, and it duplicates what the id encodes on purpose -- it has
to stay readable after the element it describes has been renamed or moved.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from linkml_runtime.linkml_model.meta import ClassDefinition, SchemaDefinition, SlotDefinition
from pydantic import BaseModel, ConfigDict

from schematerial._linkml import attributes_of, classes_of
from schematerial.facets import read_facets

__all__ = [
    "PREFIXES",
    "ElementIdError",
    "ElementSnapshot",
    "IdentityError",
    "ParsedElementId",
    "QualifiedNameError",
    "Source",
    "UnknownPrefixError",
    "capture_snapshot",
    "element_id",
    "join_qualified_name",
    "parse_element_id",
    "snapshot_index",
    "split_qualified_name",
]


class Source(StrEnum):
    """The prefix map of decision 1: a source, and the prefix that names it.

    URI expansions are deliberately absent. Decision 1 fixes the prefixes and
    says nothing about what they expand to, and nothing before the SSSOM store
    needs an expansion. The ``curie_map`` is Card 10's problem.
    """

    NOMAD_SIMULATION = "nomadsim"
    NOMAD_MEASUREMENT = "nomadmeas"
    BAM_MASTERDATA = "bammd"
    PMDCO = "pmdco"
    SCHEMATERIAL = "smat"


PREFIXES: Final[tuple[str, ...]] = tuple(source.value for source in Source)


class IdentityError(ValueError):
    """Base for every rejection this module makes."""


class UnknownPrefixError(IdentityError):
    """A source prefix outside the decision 1 prefix map."""


class QualifiedNameError(IdentityError):
    """A qualified name that is not a schema path."""


class ElementIdError(IdentityError):
    """A string that is not a well-formed element id."""


_SEPARATOR: Final = "."
_ESCAPED_DOT: Final = "%2E"
_ESCAPED_PERCENT: Final = "%25"

# One left-to-right pass, so unescaping is the exact inverse of escaping.
_UNESCAPE = re.compile(r"%25|%2E")
_PERCENT = re.compile(r"%")
_INDEX = re.compile(r"[\[\]]")
_WHITESPACE = re.compile(r"\s")


def _escape(segment: str) -> str:
    return segment.replace("%", _ESCAPED_PERCENT).replace(_SEPARATOR, _ESCAPED_DOT)


def _unescape(segment: str) -> str:
    return _UNESCAPE.sub(lambda m: "%" if m.group(0) == _ESCAPED_PERCENT else _SEPARATOR, segment)


def _check_prefix(source: str) -> str:
    prefix = str(source)
    if prefix not in PREFIXES:
        raise UnknownPrefixError(
            f"unknown source prefix {prefix!r}. Decision 1 fixes the prefix map: "
            f"{', '.join(PREFIXES)}."
        )
    return prefix


def _check_segment(segment: str, *, within: str) -> str:
    """Validate one unescaped path segment. Returns it unchanged."""
    if not segment:
        raise QualifiedNameError(
            f"qualified name {within!r} has an empty segment. "
            f"Every segment is the name of a class or an attribute."
        )
    if _INDEX.search(segment):
        raise QualifiedNameError(
            f"qualified name {within!r} contains an index in segment {segment!r}. "
            f"An element id is a schema path, not an instance path (decision 1): "
            f"'Run.calculation.energy.total.value', never "
            f"'run[0].calculation[-1].energy.total.value'. Whatever the index meant "
            f"is a cardinality on the slot or a note on a mapping row, never part of an id."
        )
    if _WHITESPACE.search(segment):
        raise QualifiedNameError(
            f"qualified name {within!r} has whitespace in segment {segment!r}. "
            f"A segment is a schema element name."
        )
    return segment


def join_qualified_name(segments: Sequence[str]) -> str:
    """Escape and join path segments into a canonical qualified name.

    Use this whenever the segments are known separately; it is the only way to
    express a segment that itself contains a dot.
    """
    if not segments:
        raise QualifiedNameError("a qualified name needs at least one segment, got none.")
    shown = _SEPARATOR.join(segments)
    return _SEPARATOR.join(_escape(_check_segment(segment, within=shown)) for segment in segments)


def split_qualified_name(qualified_name: str) -> tuple[str, ...]:
    """Split a canonical qualified name back into unescaped segments."""
    if not qualified_name:
        raise QualifiedNameError("a qualified name needs at least one segment, got ''.")
    for match in _PERCENT.finditer(qualified_name):
        start = match.start()
        if qualified_name[start : start + 3] not in (_ESCAPED_PERCENT, _ESCAPED_DOT):
            raise QualifiedNameError(
                f"qualified name {qualified_name!r} has a stray '%' at position {start}. "
                f"Only {_ESCAPED_DOT} (a dot inside a segment) and {_ESCAPED_PERCENT} "
                f"(a literal percent) are escapes, and only in upper case."
            )
    segments = tuple(
        _unescape(_check_segment(part, within=qualified_name))
        for part in qualified_name.split(_SEPARATOR)
    )
    return segments


def element_id(source: str | Source, qualified_name: str | Sequence[str]) -> str:
    """Build the stable CURIE for one element.

    ``qualified_name`` is either a canonical dotted string or the sequence of
    unescaped segments it is made of.
    """
    prefix = _check_prefix(source)
    if isinstance(qualified_name, str):
        # Validates, and rejects a non-canonical escape rather than repairing it.
        split_qualified_name(qualified_name)
        canonical = qualified_name
    else:
        canonical = join_qualified_name(qualified_name)
    return f"{prefix}:{canonical}"


@dataclass(frozen=True, slots=True)
class ParsedElementId:
    """The three views of an element id, as the reverse parser returns them."""

    source: str
    qualified_name: str
    segments: tuple[str, ...]

    @property
    def name(self) -> str:
        """The leaf segment: the element's own name."""
        return self.segments[-1]

    @property
    def parent(self) -> str | None:
        """The qualified name of the containing element, or None at the top."""
        if len(self.segments) == 1:
            return None
        return join_qualified_name(self.segments[:-1])


def parse_element_id(value: str) -> ParsedElementId:
    """Reverse of :func:`element_id`."""
    prefix, separator, qualified_name = value.partition(":")
    if not separator:
        raise ElementIdError(
            f"{value!r} is not an element id. An id is '<prefix>:<QualifiedName>', "
            f"for example 'nomadsim:Run.calculation.energy.total.value'."
        )
    _check_prefix(prefix)
    return ParsedElementId(
        source=prefix,
        qualified_name=qualified_name,
        segments=split_qualified_name(qualified_name),
    )


class ElementSnapshot(BaseModel):
    """What an element looked like in the source version it was seen in.

    Decision 2: a record, not a hash. It is stored next to the element id, never
    inside it, and it stays valid after the element it describes has moved or
    been renamed -- which is the whole point of keeping it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    """The leaf name: the last segment of the qualified name."""

    parent: str | None = None
    """Qualified name of the containing element. None for a top-level class."""

    range: str | None = None
    """The element's type, in whatever vocabulary the adapter wrote it."""

    unit: str | None = None
    """The unit as the source stated it."""

    semantic_type: str | None = None
    """A CURIE into QUDT, EMMO or PMDco (decision 4). Absent when unstated."""

    source_version: str | None = None
    """The version of the source package the element was seen in (decision 1:
    the id does not carry it, the snapshot does)."""


def capture_snapshot(
    *,
    name: str,
    parent: str | None = None,
    range: str | None = None,
    unit: str | None = None,
    semantic_type: str | None = None,
    source_version: str | None = None,
) -> ElementSnapshot:
    """Build a snapshot. The single capture point, so every element records the
    same six facts in the same way."""
    return ElementSnapshot(
        name=name,
        parent=parent,
        range=range,
        unit=unit,
        semantic_type=semantic_type,
        source_version=source_version,
    )


def _roots(schema: SchemaDefinition) -> list[str]:
    """The top-level classes decision 1's dotted path starts from.

    An explicit `tree_root` wins. Failing that, a class that is never the range
    of an attribute is a root: a class reached only through another class is a
    step on a path, not the start of one. If every class is reachable -- a cycle
    with no entry point -- every class is treated as a root, because refusing to
    walk would be worse than walking twice.
    """
    classes = {str(name): definition for name, definition in classes_of(schema).items()}
    declared = [name for name, definition in classes.items() if definition.tree_root]
    if declared:
        return sorted(declared)

    ranged: set[str] = set()
    for definition in classes.values():
        for attribute in attributes_of(definition).values():
            if attribute.range is not None and str(attribute.range) in classes:
                ranged.add(str(attribute.range))
    roots = sorted(name for name in classes if name not in ranged)
    return roots or sorted(classes)


def _snapshot_of(
    element: ClassDefinition | SlotDefinition,
    name: str,
    parent: str | None,
    source_version: str | None,
) -> ElementSnapshot:
    unit = getattr(element, "unit", None)
    facets = read_facets(element)
    return capture_snapshot(
        name=name,
        parent=parent,
        range=None if getattr(element, "range", None) is None else str(element.range),
        unit=None if unit is None else str(unit.ucum_code or "") or None,
        semantic_type=facets.semantic_type,
        source_version=source_version,
    )


def _walk(schema: SchemaDefinition) -> Iterator[tuple[Sequence[str], ElementSnapshot]]:
    """Every element, as the segments of its qualified name and its snapshot.

    Nesting is a slot whose range is a class (decision 3 and Card 7), so the
    walk follows those ranges. A class already on the current path is not
    followed again: a self-referential schema is legal and must not produce an
    infinite path.
    """
    classes = {str(name): definition for name, definition in classes_of(schema).items()}
    version = None if schema.version is None else str(schema.version)

    def descend(
        class_name: str, prefix: tuple[str, ...], seen: frozenset[str]
    ) -> Iterator[tuple[Sequence[str], ElementSnapshot]]:
        definition = classes[class_name]
        for attribute_name, attribute in attributes_of(definition).items():
            segments = (*prefix, str(attribute_name))
            parent = join_qualified_name(prefix) if prefix else None
            yield segments, _snapshot_of(attribute, str(attribute_name), parent, version)

            range_name = None if attribute.range is None else str(attribute.range)
            if range_name in classes and range_name not in seen:
                yield from descend(range_name, segments, seen | {range_name})

    for root in _roots(schema):
        yield (root,), _snapshot_of(classes[root], root, None, version)
        yield from descend(root, (root,), frozenset({root}))


def snapshot_index(schema: SchemaDefinition, source: str | Source) -> Mapping[str, ElementSnapshot]:
    """Capture every element of a canonical schema as an id and a snapshot.

    This is where snapshots are taken: whatever builds elements calls it once on
    the finished schema, so identity and snapshot are decided in one place
    rather than at every construction site.

    Raises :class:`QualifiedNameError` if any element name is an instance path.
    """
    prefix = _check_prefix(source)
    index: dict[str, ElementSnapshot] = {}
    for segments, snapshot in _walk(schema):
        identifier = element_id(prefix, segments)
        if identifier in index:
            raise IdentityError(
                f"{schema.name!r} produces the element id {identifier!r} twice. "
                f"An id is an identity, so two elements cannot share one."
            )
        index[identifier] = snapshot
    return index
