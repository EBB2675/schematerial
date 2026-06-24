"""Shared parsing logic for all schematerial fixture YAML schemas.

All supported schema fixtures (NOMAD, OPTIMADE, Emmet, CIF) use the same
top-level structure:

    name: "..."
    version: "..."
    description: "..."
    fields:
      - name: ...
        path: ...
        dtype: ...      # e.g. float, float[3][3], float[N][3], str[N]
        unit: ...
        description: ...

This module converts that structure into a SchemaModel with a single 'root'
entity containing all fields, annotated with semantic types, coordinate frames,
and per-atom flags derived from the field name, path, and description.
"""

import re
from pathlib import Path

import yaml

from schematerial.models.schema import (
    CoordinateFrame,
    Entity,
    SchemaField,
    SchemaModel,
    SemanticType,
)


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


def _infer_semantic_type(name: str, path: str, description: str | None) -> SemanticType:
    """Keyword heuristic over the combined name + path + description text."""
    text = f"{name} {path} {description or ''}".lower()

    # Most specific first to avoid false positives
    if "band_gap" in text or "bandgap" in text or "band gap" in text:
        return SemanticType.BANDGAP
    if "energy" in text:
        return SemanticType.ENERGY
    if "force" in text:
        return SemanticType.FORCE
    if "stress" in text:
        return SemanticType.STRESS
    if "charge" in text:
        return SemanticType.CHARGE
    if "spin" in text or "magnetic" in text:
        return SemanticType.SPIN
    if "temperature" in text:
        return SemanticType.TEMPERATURE
    if "pressure" in text:
        return SemanticType.PRESSURE
    if "k_point" in text or "kpoint" in text or "k-point" in text:
        return SemanticType.KPOINT
    if "position" in text and ("atom" in text or "site" in text or "cartesian" in text):
        return SemanticType.ATOMIC_POSITION
    if (
        "cell_length" in text
        or "cell_angle" in text
        or ("lattice" in text and ("vector" in text or "matrix" in text or "param" in text))
    ):
        return SemanticType.LATTICE_PARAMETER
    if "length" in text:
        return SemanticType.LENGTH
    if "periodic" in text or "dimension_type" in text:
        return SemanticType.FLAG
    if (
        "formula" in text
        or "composition" in text
        or "chemical" in text
        or "n_atom" in text
        or "nsites" in text
    ):
        return SemanticType.IDENTIFIER
    if "label" in text or "species" in text:
        return SemanticType.LABEL

    return SemanticType.UNKNOWN


def _detect_per_atom(name: str, unit: str | None) -> bool:
    if unit and "/atom" in unit.lower():
        return True
    return "_per_atom" in name.lower()


def _detect_coordinate_frame(name: str, description: str | None) -> CoordinateFrame:
    text = f"{name} {description or ''}".lower()
    if "cartesian" in text:
        return CoordinateFrame.CARTESIAN
    if "fractional" in text:
        return CoordinateFrame.FRACTIONAL
    return CoordinateFrame.NONE


def parse_yaml_schema(source: str | Path, format: str) -> SchemaModel:
    """Load a schematerial fixture YAML file and return a SchemaModel."""
    path = Path(source)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(
            f"{path} is not a valid schema YAML file "
            f"(expected a mapping, got {type(raw).__name__})"
        )

    raw_fields = raw.get("fields", [])
    if not isinstance(raw_fields, list):
        raise ValueError(
            f"{path}: 'fields' must be a list of mappings, got {type(raw_fields).__name__}"
        )

    fields: list[SchemaField] = []
    for entry in raw_fields:
        if not isinstance(entry, dict):
            raise ValueError(
                f"{path}: each entry in 'fields' must be a mapping, got {type(entry).__name__}"
            )
        name: str = entry["name"]
        field_path: str = entry["path"]
        unit: str | None = entry.get("unit")
        description: str | None = entry.get("description")

        datatype, shape = _parse_dtype(entry.get("dtype"))
        cardinality = "many" if shape is not None else "one"

        fields.append(
            SchemaField(
                path=field_path,
                label=name,
                description=description,
                datatype=datatype,
                shape=shape,
                unit=unit,
                cardinality=cardinality,  # type: ignore[arg-type]
                semantic_type=_infer_semantic_type(name, field_path, description),
                coordinate_frame=_detect_coordinate_frame(name, description),
                per_atom=_detect_per_atom(name, unit),
                source_path_raw=field_path,
            )
        )

    return SchemaModel(
        name=raw.get("name", ""),
        version=str(raw["version"]) if raw.get("version") is not None else None,
        format=format,
        source_file=str(path),
        entities=[Entity(name="root", fields=fields)],
        metadata={"description": raw.get("description", "")},
    )
