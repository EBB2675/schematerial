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
the canonical representation: fields become class-local attributes (decision 3),
a unit is written as a `ucum_code`, and the facets of decision 4 go into
`annotations` under `instantiates`.

These are prototype readers over fixture files, not adapters. Cards 6 to 9
replace them with extractors and real adapters over the Card 5 contract.
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
from schematerial.facets import write_facets
from schematerial.models.core import CoordinateFrame, MaterialsFacets
from schematerial.semantics import semantic_types

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


def _infer_semantic_type(name: str, path: str, description: str | None) -> str | None:
    """Keyword heuristic over the combined name + path + description text.

    Returns a CURIE, or None where nothing resolves. This ladder is on borrowed
    time: decision 4 says inferring a semantic type is a separate, scored step,
    and Card 14 owns it. It survives here only because it is the sole producer
    today, retargeted onto real CURIEs.

    Six of the prototype's sixteen categories return None rather than a term.
    `lattice_parameter` and `k_point` have no single term that is both exact and
    stably addressable; `identifier`, `label` and `flag` are not quantity kinds
    at all, they are datatype and role hints; `unknown` is the absence of a
    semantic type, not a value for one. See decision record 002.
    """
    text = f"{name} {path} {description or ''}".lower()

    # Most specific first to avoid false positives
    if "band_gap" in text or "bandgap" in text or "band gap" in text:
        return semantic_types.BAND_GAP
    if "energy" in text:
        return semantic_types.ENERGY
    if "force" in text:
        return semantic_types.FORCE
    if "stress" in text:
        return semantic_types.STRESS
    if "charge" in text:
        return semantic_types.CHARGE
    if "spin" in text or "magnetic" in text:
        return semantic_types.SPIN
    if "temperature" in text:
        return semantic_types.TEMPERATURE
    if "pressure" in text:
        return semantic_types.PRESSURE
    if "position" in text and ("atom" in text or "site" in text or "cartesian" in text):
        return semantic_types.ATOMIC_POSITION
    if "length" in text:
        return semantic_types.LENGTH

    return None


def _detect_per_atom(name: str, unit: str | None) -> bool | None:
    """True when the source says so, absent when it does not.

    Decision 4: a facet with no value is absent. The prototype defaulted this
    to False, which asserts "not per atom" about every element that simply did
    not mention it.
    """
    if unit and "/atom" in unit.lower():
        return True
    if "_per_atom" in name.lower():
        return True
    return None


def _detect_coordinate_frame(name: str, description: str | None) -> CoordinateFrame | None:
    text = f"{name} {description or ''}".lower()
    if "cartesian" in text:
        return CoordinateFrame.cartesian
    if "fractional" in text:
        return CoordinateFrame.fractional
    return None


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
        MaterialsFacets(
            semantic_type=_infer_semantic_type(name, field_path, description),
            coordinate_frame=_detect_coordinate_frame(name, description),
            per_atom=_detect_per_atom(name, unit),
        ),
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
    for entry in raw_fields:
        if not isinstance(entry, dict):
            raise ValueError(
                f"{path}: each entry in 'fields' must be a mapping, got {type(entry).__name__}"
            )
        attribute = _attribute(entry, path)
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
    return schema
