"""Everything the read-only preview serves, prepared once at ingestion.

Materialisation happens here, behind the cache, while the process is starting.
The index rows, the per-element detail records and their serialised bytes are
built in the same pass. A request path performs a dictionary lookup and writes
bytes; it never materialises, never copies a cached schema and never serialises.

Three kinds of identifier appear below and are deliberately kept apart:

- ``class_id`` and ``declaration_id`` name where something is **declared**. An
  inherited attribute keeps its declaring class in ``declaration_id``.
- an element ``id`` names an effective attribute **as seen on one class**. This
  is what the browser lists, filters and selects.
- ``snapshot_paths`` name contextual positions reached by descending from a root
  through subsection ranges. One declaration corresponds to many paths, so their
  total is not an element count.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from linkml_runtime.linkml_model.meta import (
    ArrayExpression,
    ClassDefinition,
    DimensionExpression,
    Element,
    SchemaDefinition,
    SlotDefinition,
    UnitOfMeasure,
)

from schematerial._linkml import (
    annotations_of,
    attributes_of,
    classes_of,
    enums_of,
    instantiates_of,
)
from schematerial.cache import MaterialisationCache
from schematerial.extraction.contract import read_document
from schematerial.facets import read_facets
from schematerial.identity import (
    ElementSnapshot,
    capture_snapshot,
    element_id,
    parse_element_id,
)
from schematerial.parsers.registry import adapter_for
from schematerial.parsers.source import SchemaImport, SchemaImportError
from schematerial.web.graph import build_graph, empty_graph

__all__ = ["SchemaPreview", "build_preview", "ingest", "unsupported_preview"]

Report = Sequence[Mapping[str, str]]


def serialise(value: Any) -> bytes:
    """Deterministic JSON bytes: identical input gives an identical payload."""
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _compress(payload: bytes) -> bytes:
    # mtime=0: the compressed bytes depend on the payload alone, never the clock.
    return gzip.compress(payload, compresslevel=6, mtime=0)


@dataclass(frozen=True)
class SchemaPreview:
    """One ingested schema, with every response it can produce already built."""

    name: str
    status: str
    summary: dict[str, Any]
    index: tuple[dict[str, Any], ...]
    details: Mapping[str, dict[str, Any]]
    graph: dict[str, Any]
    summary_bytes: bytes
    index_bytes: bytes
    index_gzip: bytes
    detail_bytes: Mapping[str, bytes]
    graph_bytes: bytes
    graph_gzip: bytes


def _prepare(
    name: str,
    status: str,
    summary: dict[str, Any],
    index: Sequence[dict[str, Any]],
    details: Mapping[str, dict[str, Any]],
    graph: dict[str, Any],
) -> SchemaPreview:
    index_bytes = serialise({"schema": name, "elements": list(index)})
    graph_bytes = serialise(graph)
    return SchemaPreview(
        name=name,
        status=status,
        summary=summary,
        index=tuple(index),
        details=dict(details),
        graph=graph,
        summary_bytes=serialise(summary),
        index_bytes=index_bytes,
        index_gzip=_compress(index_bytes),
        detail_bytes={key: serialise(value) for key, value in details.items()},
        graph_bytes=graph_bytes,
        graph_gzip=_compress(graph_bytes),
    )


def _annotation(element: Element, tag: str) -> str | None:
    entry = annotations_of(element).get(tag)
    return None if entry is None else str(entry.value)


def _json_annotation(element: Element, tag: str) -> Any | None:
    raw = _annotation(element, tag)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _display_name(key: str, definition: ClassDefinition | None) -> str:
    """The source's short class name, falling back to its full definition id."""
    if definition is None or definition.title is None:
        return key.rpartition(".")[2] or key
    return str(definition.title)


def _class_reference(
    prefix: str, key: str, classes: Mapping[str, ClassDefinition]
) -> dict[str, Any]:
    return {
        "id": element_id(prefix, (key,)),
        "key": key,
        "name": _display_name(key, classes.get(key)),
        "known": key in classes,
    }


def _source_prefix(imported: SchemaImport) -> str:
    """The source prefix this adapter wrote, read back off its own output.

    Taking it from the import rather than naming a source here is what keeps the
    preview usable by a second adapter. Declarations and snapshot keys must
    agree: if they did not, joining paths to elements would silently miss.
    """
    prefixes = {
        parse_element_id(str(definition.class_uri)).source
        for definition in classes_of(imported.loaded.schema).values()
        if definition.class_uri is not None
    }
    prefixes |= {parse_element_id(key).source for key in imported.loaded.snapshots}
    if len(prefixes) != 1:
        found = ", ".join(sorted(prefixes)) or "none"
        raise SchemaImportError(
            f"an import must use exactly one source prefix; found: {found}. "
            f"Class identifiers and snapshot paths have to come from one source.",
            [dict(entry) for entry in imported.report],
        )
    return prefixes.pop()


def _paths_by_element(
    prefix: str, schema: SchemaDefinition, snapshots: Mapping[str, ElementSnapshot]
) -> dict[str, list[str]]:
    """Group contextual snapshot paths under the element each one lands on.

    A path is resolved by walking it: the first segment names a class, every
    later segment names an attribute of the class reached so far. This uses the
    authoritative snapshot index rather than repeating its traversal.
    """
    classes = classes_of(schema)
    grouped: dict[str, list[str]] = {}
    for key in snapshots:
        segments = parse_element_id(key).segments
        owner = segments[0]
        if owner not in classes:
            continue
        landing: str | None = element_id(prefix, (owner,))
        for position, segment in enumerate(segments[1:], start=1):
            attribute = attributes_of(classes[owner]).get(segment)
            if attribute is None:
                landing = None
                break
            landing = element_id(prefix, (owner, segment))
            if position < len(segments) - 1:
                target = None if attribute.range is None else str(attribute.range)
                if target is None or target not in classes:
                    landing = None
                    break
                owner = target
        if landing is not None:
            grouped.setdefault(landing, []).append(key)
    return {key: sorted(value) for key, value in grouped.items()}


def _attach_diagnostics(
    report: Report, local_attributes: Mapping[str, Sequence[str]]
) -> tuple[dict[str, list[dict[str, str]]], dict[str, list[dict[str, str]]], list[dict[str, str]]]:
    """Split the conversion report by the class or declared attribute it names.

    Diagnostic paths are written at the declaration site, so an inherited
    attribute's diagnostics are found under its declaring class.
    """
    by_class: dict[str, list[dict[str, str]]] = {}
    by_attribute: dict[str, list[dict[str, str]]] = {}
    unattached: list[dict[str, str]] = []
    # Longest first, so a class key that is a prefix of another cannot win.
    keys = sorted(local_attributes, key=len, reverse=True)
    for entry in report:
        row = dict(entry)
        path = row.get("path", "")
        for key in keys:
            if path == key:
                by_class.setdefault(key, []).append(row)
                break
            if path.startswith(f"{key}."):
                rest = path[len(key) + 1 :]
                if rest in local_attributes[key]:
                    by_attribute.setdefault(f"{key}.{rest}", []).append(row)
                else:
                    by_class.setdefault(key, []).append(row)
                break
        else:
            unattached.append(row)
    return by_class, by_attribute, unattached


def _range(
    prefix: str,
    attribute: SlotDefinition,
    classes: Mapping[str, ClassDefinition],
    enums: Mapping[str, Any],
) -> dict[str, Any] | None:
    if attribute.range is None:
        return None
    name = str(attribute.range)
    if name in classes:
        return {"name": name, "kind": "class", "target": _class_reference(prefix, name, classes)}
    if name in enums:
        values = [str(value) for value in (enums[name].permissible_values or {})]
        return {"name": name, "kind": "enum", "values": sorted(values)}
    return {"name": name, "kind": "type"}


def _array(attribute: SlotDefinition) -> dict[str, Any] | None:
    # The metamodel declares these slots as wide unions; after construction they
    # hold the real classes, so narrow once here rather than at every read.
    array = attribute.array
    if not isinstance(array, ArrayExpression):
        return None
    dimensions = [
        {
            "alias": None if dimension.alias is None else str(dimension.alias),
            "exact_cardinality": dimension.exact_cardinality,
        }
        for dimension in (array.dimensions or [])
        if isinstance(dimension, DimensionExpression)
    ]
    return {
        "exact_number_dimensions": array.exact_number_dimensions,
        "dimensions": dimensions,
    }


def _unit(attribute: SlotDefinition) -> dict[str, Any] | None:
    source_unit = _annotation(attribute, "source_unit")
    unit = attribute.unit
    code = unit.ucum_code if isinstance(unit, UnitOfMeasure) else None
    if source_unit is None and code is None:
        return None
    return {"ucum_code": None if code is None else str(code), "source": source_unit}


def _counts(
    local: SchemaDefinition, materialised: SchemaDefinition, snapshot_paths: int
) -> dict[str, int]:
    classes = classes_of(materialised)
    effective = sum(len(attributes_of(definition)) for definition in classes.values())
    inherited = sum(
        1
        for key, definition in classes.items()
        for attribute in attributes_of(definition).values()
        if _annotation(attribute, "source_declaring_class") not in (None, key)
    )
    return {
        "classes": len(classes),
        "local_attributes": sum(
            len(attributes_of(definition)) for definition in classes_of(local).values()
        ),
        "effective_attributes": effective,
        "inherited_attributes": inherited,
        "enums": len(enums_of(materialised)),
        # What the browser lists: one row per class and per effective attribute.
        "browsable_elements": len(classes) + effective,
        # Contextual positions, not elements. Deliberately reported separately.
        "snapshot_paths": snapshot_paths,
    }


def _ancestors(key: str, bases: Mapping[str, Sequence[str]]) -> list[str]:
    """Every transitive source parent, following all bases rather than the first."""
    seen: set[str] = set()
    queue = list(bases.get(key, ()))
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        queue.extend(bases.get(current, ()))
    return sorted(seen)


def _qualified(name: str, version: str | None) -> str:
    """Two extractions of one module are two schemas, told apart by version.

    This is the address a pane is served under, not an identity: the elements
    inside keep their own ids. Naming the version is what lets two versions of
    one module be browsed side by side.
    """
    return name if not version else f"{name}@{version}"


def build_preview(imported: SchemaImport, *, package: str | None = None) -> SchemaPreview:
    """Turn one converted document into every response the preview can serve.

    Nothing here names a source package: the element identifiers come from the
    prefix the adapter wrote, and everything else is read off the canonical
    schema, its materialisation and its diagnostics.
    """
    prefix = _source_prefix(imported)
    local = imported.schema
    materialised = imported.loaded.schema
    snapshots = imported.loaded.snapshots
    classes = classes_of(materialised)
    enums = enums_of(materialised)
    version = None if materialised.version is None else str(materialised.version)

    local_names = {
        key: sorted(attributes_of(definition))
        for key, definition in classes_of(local).items()
    }
    by_class, by_attribute, unattached = _attach_diagnostics(imported.report, local_names)
    paths = _paths_by_element(prefix, materialised, snapshots)
    bases = {
        key: [str(base) for base in (_json_annotation(definition, "source_bases") or [])]
        for key, definition in classes.items()
    }

    index: list[dict[str, Any]] = []
    details: dict[str, dict[str, Any]] = {}
    schema_name = _qualified(str(materialised.name), version)
    # (owner, attribute, target) for locally declared attributes ranging on a
    # class. Collected where each one is declared, so the graph draws structure
    # at the class that wrote it rather than on every subclass inheriting it.
    containment: list[tuple[str, str, str]] = []
    graph_names: dict[str, str] = {}
    graph_attributes: dict[str, int] = {}
    graph_diagnostics: dict[str, int] = {}

    for key in sorted(classes, key=lambda item: (_display_name(item, classes[item]), item)):
        definition = classes[key]
        identifier = element_id(prefix, (key,))
        class_reference = _class_reference(prefix, key, classes)
        class_diagnostics = by_class.get(key, [])
        references = {
            str(entry["name"]): entry
            for entry in (_json_annotation(definition, "source_effective_attributes") or [])
        }
        attributes = attributes_of(definition)

        rows: list[dict[str, Any]] = []
        for name in sorted(attributes):
            attribute = attributes[name]
            declaring = _annotation(attribute, "source_declaring_class") or key
            inherited = declaring != key
            attribute_id = element_id(prefix, (key, name))
            diagnostics = [
                {**row, "inherited": inherited}
                for row in by_attribute.get(f"{declaring}.{name}", [])
            ]
            unit = _unit(attribute)
            range_ = _range(prefix, attribute, classes, enums)
            if not inherited and range_ is not None and range_["kind"] == "class":
                containment.append((key, name, range_["name"]))
            rows.append(
                {
                    "id": attribute_id,
                    "kind": "attribute",
                    "name": name,
                    "class_id": identifier,
                    "class_name": class_reference["name"],
                    "range": None if range_ is None else range_["name"],
                    "unit": None if unit is None else unit["ucum_code"],
                    "inherited": inherited,
                    "multivalued": bool(attribute.multivalued),
                    "diagnostics": len(diagnostics),
                    "snapshot_paths": len(paths.get(attribute_id, ())),
                }
            )
            representative = paths.get(attribute_id, ())
            snapshot = snapshots.get(representative[0]) if representative else None
            details[attribute_id] = {
                "id": attribute_id,
                "kind": "attribute",
                "schema": schema_name,
                "name": name,
                "class": class_reference,
                "declared_in": _class_reference(prefix, declaring, classes),
                "inherited": inherited,
                "declaration_id": None
                if attribute.slot_uri is None
                else str(attribute.slot_uri),
                "source_reference": references.get(name),
                "description": attribute.description,
                "range": range_,
                "unit": unit,
                "multivalued": attribute.multivalued,
                "array": _array(attribute),
                "facets": read_facets(attribute).model_dump(exclude_none=True),
                "instantiates": [str(item) for item in instantiates_of(attribute)],
                "source": {
                    "kind": _annotation(attribute, "source_kind"),
                    "type": _annotation(attribute, "source_type"),
                    "range": _json_annotation(attribute, "source_range"),
                    "shape": _json_annotation(attribute, "source_shape"),
                    "annotations": _json_annotation(attribute, "source_annotations"),
                },
                "mapping_snapshot": capture_snapshot(
                    name=name, parent=parse_element_id(attribute_id).parent,
                    range=None if range_ is None else range_["name"],
                    unit=None if unit is None else unit["ucum_code"],
                    semantic_type=read_facets(attribute).semantic_type,
                    source_version=version,
                ).model_dump(),
                "snapshot": None if snapshot is None else snapshot.model_dump(),
                "snapshot_paths": list(representative),
                "diagnostics": diagnostics,
            }

        parents = [
            {**_class_reference(prefix, base, classes),
             "role": "is_a" if position == 0 else "mixin", "position": position}
            for position, base in enumerate(bases.get(key, ()))
        ]
        class_paths = paths.get(identifier, ())
        class_snapshot = snapshots.get(class_paths[0]) if class_paths else None
        graph_names[key] = class_reference["name"]
        graph_attributes[key] = len(attributes)
        graph_diagnostics[key] = len(class_diagnostics)
        index.append(
            {
                "id": identifier,
                "kind": "class",
                "name": class_reference["name"],
                "class_id": identifier,
                "class_name": class_reference["name"],
                "range": None,
                "unit": None,
                "inherited": False,
                "multivalued": False,
                "diagnostics": len(class_diagnostics),
                "snapshot_paths": len(class_paths),
            }
        )
        index.extend(rows)
        details[identifier] = {
            "id": identifier,
            "kind": "class",
            "schema": schema_name,
            "key": key,
            "name": class_reference["name"],
            "description": definition.description,
            "parents": parents,
            "ancestors": [
                _class_reference(prefix, base, classes) for base in _ancestors(key, bases)
            ],
            "counts": {
                "local_attributes": len(local_names.get(key, ())),
                "effective_attributes": len(attributes),
                "inherited_attributes": sum(1 for row in rows if row["inherited"]),
                "snapshot_paths": len(class_paths),
            },
            "attributes": rows,
            "mapping_snapshot": capture_snapshot(
                name=class_reference["name"], source_version=version,
                semantic_type=read_facets(definition).semantic_type,
            ).model_dump(),
            "snapshot": None if class_snapshot is None else class_snapshot.model_dump(),
            "snapshot_paths": list(class_paths),
            "diagnostics": class_diagnostics,
            "source_version": version,
        }

    graph = build_graph(
        schema_name,
        prefix,
        list(classes),
        graph_names,
        bases,
        containment,
        graph_attributes,
        graph_diagnostics,
    )

    statuses: dict[str, int] = {}
    for entry in imported.report:
        statuses[entry["status"]] = statuses.get(entry["status"], 0) + 1
    summary = {
        "name": schema_name,
        "title": None if materialised.title is None else str(materialised.title),
        "status": "ok",
        "error": None,
        "schema_id": str(materialised.id),
        "source": {
            "package": package,
            "version": version,
            "dependencies": _json_annotation(local, "source_dependencies"),
        },
        "toolchain": _json_annotation(local, "toolchain_versions"),
        "cache_key": imported.cache_key,
        "counts": _counts(local, materialised, len(snapshots)),
        "diagnostics": {"total": len(imported.report), **statuses},
        "schema_diagnostics": unattached,
    }
    return _prepare(schema_name, "ok", summary, index, details, graph)


def unsupported_preview(
    name: str, error: str, *, report: Report = (), package: str | None = None,
    version: str | None = None,
) -> SchemaPreview:
    """A refused document, listed with its diagnostics rather than hidden.

    An import the adapter will not vouch for must not be shown as an apparently
    complete pane, and must not silently disappear either.
    """
    name = _qualified(name, version)
    statuses: dict[str, int] = {}
    for entry in report:
        statuses[entry["status"]] = statuses.get(entry["status"], 0) + 1
    summary = {
        "name": name,
        "title": None,
        "status": "unsupported",
        "error": error,
        "schema_id": None,
        "source": {"package": package, "version": version, "dependencies": None},
        "toolchain": None,
        "cache_key": None,
        "counts": {
            "classes": 0,
            "local_attributes": 0,
            "effective_attributes": 0,
            "inherited_attributes": 0,
            "enums": 0,
            "browsable_elements": 0,
            "snapshot_paths": 0,
        },
        "diagnostics": {"total": len(report), **statuses},
        "schema_diagnostics": [dict(entry) for entry in report],
    }
    return _prepare(name, "unsupported", summary, [], {}, empty_graph(name))


def ingest(
    paths: Sequence[str | Path], *, cache: MaterialisationCache | None = None
) -> tuple[SchemaPreview, ...]:
    """Convert every extraction document once, at startup.

    Each document names the source package it was read from, and that selects
    the adapter. A document no adapter reads, or one an adapter refuses, becomes
    an unsupported entry carrying its error and diagnostics; neither stops the
    other schemas from loading. Documents from different sources may be ingested
    together, and share one materialisation cache.
    """
    entries = cache if cache is not None else MaterialisationCache()
    previews: list[SchemaPreview] = []
    for path in paths:
        location = Path(path)
        fallback = location.name.split(".")[0]
        try:
            document = read_document(location.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            previews.append(unsupported_preview(fallback, str(error)))
            continue
        source = document.get("source", {})
        name = str(source.get("module") or fallback)
        try:
            imported = adapter_for(str(source.get("name", "")), entries).convert(document)
            previews.append(build_preview(imported, package=source.get("name")))
        except SchemaImportError as error:
            previews.append(
                unsupported_preview(
                    name, str(error), report=error.report,
                    package=source.get("name"), version=source.get("version"),
                )
            )
    return tuple(previews)
