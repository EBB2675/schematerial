"""Shared parsing logic for all schematerial fixture YAML schemas.

The prototype schema fixtures use the same top-level structure:

    name: "..."
    version: "..."
    description: "..."
    fields:
      - name: ...
        path: ...
        dtype: ...      # e.g. float, float[3][3], float[N][3], str[N]
        unit: ...
        description: ...

This module converts that structure into a LinkML `SchemaDefinition`, which is
the canonical representation: fields become class-local attributes, a unit is
written as a `ucum_code`, and the materials facets go into `annotations` under
`instantiates`.

These are prototype readers over fixture files, not adapters. The extractors and
the real adapters over the extraction contract replace them.
"""

import re
from pathlib import Path
from typing import Any

import yaml
from linkml_runtime.linkml_model.meta import (
    ArrayExpression,
    ClassDefinition,
    SchemaDefinition,
    SlotDefinition,
    UnitOfMeasure,
)

from schematerial._linkml import add_attribute, add_class, set_annotation
from schematerial.facets import validate_schema_facets, write_facets
from schematerial.models.core import MaterialsFacets

CANONICAL_PREFIXES: Any = {
    "linkml": "https://w3id.org/linkml/",
    "smat": "https://w3id.org/schematerial/core/",
}

ROOT_CLASS = "Root"
"""The single top-level class a fixture's flat field list becomes."""

_RANGES = {
    "float": "float",
    "int": "integer",
    "str": "string",
    "bool": "boolean",
}


def _parse_dtype(raw: str | None) -> tuple[str, list[int | None] | None]:
    """Parse a dtype string into (base_type, shape).

    Examples:
        "float"        -> ("float", None)
        "float[3][3]"  -> ("float", [3, 3])
        "float[N][3]"  -> ("float", [None, 3])
        "str[N]"       -> ("str", [None])
    """
    if not raw:
        return "unknown", None
    # Only accept N or digits inside brackets — anything else is an unrecognised token
    m = re.fullmatch(r"(\w+)((?:\[(?:N|\d+)\])*)", raw.strip())
    if not m:
        return raw, None
    base = m.group(1)
    dims_str = m.group(2)
    if not dims_str:
        return base, None
    dims = re.findall(r"\[(N|\d+)\]", dims_str)
    shape: list[int | None] = [None if d == "N" else int(d) for d in dims]
    return base, shape


def _ncname(text: str, fallback: str) -> str:
    """A LinkML schema name must be an NCName. The readable name goes in
    `title`, which has no such constraint."""
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_")
    if not slug or not re.match(r"[A-Za-z_]", slug[0]):
        slug = f"{fallback}_{slug}" if slug else fallback
    return slug


def _linkml_range(datatype: str) -> str | None:
    """Map a fixture dtype onto a LinkML range. An unmapped type is absent, and
    reported by the caller rather than guessed at."""
    return _RANGES.get(datatype)


def _attribute(entry: dict, path: Path) -> SlotDefinition:
    name: str = entry["name"]
    field_path: str = entry["path"]
    unit: str | None = entry.get("unit")
    description: str | None = entry.get("description")

    datatype, shape = _parse_dtype(entry.get("dtype"))

    attribute = SlotDefinition(
        name=name,
        description=description,
        range=_linkml_range(datatype),
        multivalued=shape is not None,
    )
    if unit:
        attribute.unit = UnitOfMeasure(ucum_code=unit)
    if shape is not None:
        attribute.array = ArrayExpression(exact_number_dimensions=len(shape))
        set_annotation(
            attribute, "source_shape", repr([d if d is not None else "N" for d in shape])
        )
    if _linkml_range(datatype) is None:
        set_annotation(attribute, "unmapped_source_type", datatype)
    set_annotation(attribute, "source_path_raw", field_path)

    write_facets(
        attribute,
        MaterialsFacets.model_validate(entry.get("facets", {})),
    )
    return attribute


def parse_yaml_schema(source: str | Path, format: str) -> SchemaDefinition:
    """Load a schematerial fixture YAML file and return a LinkML schema."""
    path = Path(source)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(
            f"{path} is not a valid schema YAML file (expected a mapping, got {type(raw).__name__})"
        )

    raw_fields = raw.get("fields", [])
    if not isinstance(raw_fields, list):
        raise ValueError(
            f"{path}: 'fields' must be a list of mappings, got {type(raw_fields).__name__}"
        )

    root = ClassDefinition(name=ROOT_CLASS, tree_root=True)
    source_paths: dict[str, str] = {}
    for entry in raw_fields:
        if not isinstance(entry, dict):
            raise ValueError(
                f"{path}: each entry in 'fields' must be a mapping, got {type(entry).__name__}"
            )
        attribute = _attribute(entry, path)
        name = str(attribute.name)
        if name in source_paths:
            raise ValueError(
                f"{path}: duplicate field {name!r} at {source_paths[name]!r} "
                f"and {entry['path']!r}; prototype fields must have unique names"
            )
        source_paths[name] = entry["path"]
        add_attribute(root, attribute)

    schema = SchemaDefinition(
        id=f"https://w3id.org/schematerial/{format}",
        name=_ncname(raw.get("name", "") or format, format),
        title=raw.get("name", "") or None,
        version=str(raw["version"]) if raw.get("version") is not None else None,
        description=raw.get("description", ""),
        source_file=str(path),
        default_range="string",
        prefixes=CANONICAL_PREFIXES,
        imports=["linkml:types"],
    )
    add_class(schema, root)
    validate_schema_facets(schema)
    return schema
