"""NOMAD extraction JSON to verified canonical LinkML; no source-package imports."""

import json
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from importlib.metadata import version
from pathlib import Path
from typing import Any

from linkml_runtime.dumpers import json_dumper, yaml_dumper
from linkml_runtime.linkml_model.meta import (
    ArrayExpression,
    ClassDefinition,
    DimensionExpression,
    EnumDefinition,
    Prefix,
    SchemaDefinition,
    SlotDefinition,
    UnitOfMeasure,
)

from schematerial._linkml import (
    add_attribute,
    add_class,
    annotations_of,
    attributes_of,
    class_of,
    instantiates_of,
    set_annotation,
)
from schematerial.cache import MaterialisationCache
from schematerial.extraction.contract import read_document, validate_document
from schematerial.facets import FACET_TAGS, validate_schema_facets, write_facets
from schematerial.identity import Source, element_id, snapshot_index
from schematerial.loading import LoadedSchema
from schematerial.models.core import MaterialsFacets
from schematerial.parsers.source import SchemaImportError

# Each row is tested. None means retained as an explicitly unsupported source type.
TYPE_RANGES: dict[tuple[str, str], str | None] = {
    ("python", "str"): "string",
    ("python", "bool"): "boolean",
    ("python", "int"): "integer",
    ("python", "float"): "float",
    ("python", "complex"): None,
    ("numpy", "int32"): "integer",
    ("numpy", "int64"): "integer",
    ("numpy", "float64"): "double",
    ("numpy", "complex128"): None,
    ("custom", "nomad.metainfo.data_type.Datetime"): "datetime",
    ("custom", "nomad.metainfo.data_type.URL"): "uri",
    ("custom", "nomad.metainfo.data_type.JSON"): None,
}

# Exact spelling table: no dimensional inference or source-package unit registry.
UNIT_CODES = {
    "meter": "m", "meter ** 2": "m2", "meter ** 3": "m3", "1 / meter": "/m",
    "joule": "J", "1 / joule": "/J", "second": "s", "meter / second": "m/s",
    "kilogram": "kg", "kelvin": "K", "newton": "N", "electron_volt": "eV",
    "mole / liter": "mol/L",
}


class NomadImportError(SchemaImportError):
    """A NOMAD document that cannot be presented as a faithful schema.

    The shared base is what lets a consumer report a refused import without
    knowing which source it came from.
    """


@dataclass(frozen=True)
class NomadImport:
    """Local canonical schema plus the verified, cached loading view and diagnostics."""

    schema: SchemaDefinition
    loaded: LoadedSchema
    cache_key: str
    report: tuple[dict[str, str], ...]

    def to_yaml(self) -> str:
        """Portable canonical YAML with the pinned toolchain in its header."""
        return _canonical_yaml(self.schema)


def _canonical_yaml(schema: SchemaDefinition) -> str:
    pins = json.loads(str(annotations_of(schema)["toolchain_versions"].value))
    header = "# Generated NOMAD canonical schema\n"
    return header + "".join(f"# {name}=={pin}\n" for name, pin in pins.items()) + (
        yaml_dumper.dumps(schema))


def _type_range(raw: str) -> str | None:
    try:
        data = json.loads(raw)
    except ValueError:
        # Also support raw Python/numpy names emitted for actual type objects.
        module, _, name = raw.rpartition(".")
        data = {"type_kind": "python" if module == "builtins" else module, "type_data": name}
    if not isinstance(data, dict):
        return None
    kind, name = data.get("type_kind"), data.get("type_data")
    if not isinstance(kind, str) or not isinstance(name, str):
        return None
    return TYPE_RANGES.get((kind, name))


def _attribute(
    owner: str, raw: dict[str, Any], report: list[dict[str, str]],
) -> SlotDefinition:
    path = f"{owner}.{raw['name']}"

    def partial(reason: str) -> None:
        report.append({"path": path, "status": "partial", "reason": reason})

    range_ = raw["range"]
    target = _type_range(range_["name"]) if range_["kind"] == "datatype" else range_["name"]
    attribute = SlotDefinition(
        name=raw["name"], description=raw.get("description"), range=target,
        slot_uri=element_id(Source.NOMAD_SIMULATION, (owner, raw["name"])),
    )
    set_annotation(attribute, "source_declaring_class", owner)
    set_annotation(attribute, "source_kind", raw["kind"])
    set_annotation(attribute, "source_range", json.dumps(range_, sort_keys=True))
    if range_["kind"] == "datatype":
        set_annotation(attribute, "source_type", range_["name"])
        if target is None:
            partial(f"unmapped source type: {range_['name']}")
        else:
            try:
                data = json.loads(range_["name"])
            except ValueError:
                data = {}
            if isinstance(data, dict) and set(data) - {"type_kind", "type_data"}:
                partial("source type constraints/flags retained verbatim; not enforced by LinkML")
    if "unit" in raw:
        unit = raw["unit"]
        code = UNIT_CODES.get(unit, unit if unit in UNIT_CODES.values() else None)
        set_annotation(attribute, "source_unit", unit)
        if code is None:
            partial(f"unmapped source unit: {unit}")
        else:
            attribute.unit = UnitOfMeasure(ucum_code=code)
    if raw["kind"] == "subsection":
        attribute.multivalued = raw["repeats"]
    if "shape" in raw:
        shape = raw["shape"]
        set_annotation(attribute, "source_shape", json.dumps(shape))
        instantiates_of(attribute).append("smat:NomadShape")
        if shape:
            attribute.array = ArrayExpression(exact_number_dimensions=len(shape))
            if all(type(dim) is int for dim in shape):
                attribute.array.dimensions = [
                    DimensionExpression(alias=f"axis_{index}", exact_cardinality=dim)
                    for index, dim in enumerate(shape)
                ]
            else:
                partial("symbolic shape retained verbatim; only dimension count is represented")
    annotations = raw.get("annotations", {})
    write_facets(attribute, MaterialsFacets.model_validate(
        {tag: value for tag, value in annotations.items() if tag in FACET_TAGS}
    ))
    # Retain other source facts under one namespace, without overwriting adapter provenance.
    if annotations:
        set_annotation(attribute, "source_annotations", json.dumps(annotations, sort_keys=True))
    return attribute


def _signature(attribute: SlotDefinition) -> dict[str, Any]:
    value = json.loads(json_dumper.dumps(attribute))
    tags = ("source_kind", "source_range", "source_type", "source_unit", "source_shape",
            "source_declaring_class", "source_annotations", *FACET_TAGS)
    annotations = value.get("annotations", {})
    return {
        "range": value.get("range"), "unit": value.get("unit"), "array": value.get("array"),
        "description": value.get("description"),
        "multivalued": bool(value.get("multivalued")),
        **{tag: annotations.get(tag) for tag in tags},
    }


class NomadAdapter:
    """Only JSON enters this boundary. Inheritance is delegated to pinned SchemaView."""

    def __init__(self, cache: MaterialisationCache | None = None) -> None:
        self.cache = cache if cache is not None else MaterialisationCache()

    def read(self, source: str | Path) -> NomadImport:
        return self.convert(read_document(Path(source).read_text(encoding="utf-8")))

    def convert(self, document: dict[str, Any]) -> NomadImport:
        document = validate_document(document)
        report = [dict(item) for item in document["report"]]
        if document["contract_version"] != "1.1":
            raise NomadImportError(
                "NOMAD import requires contract 1.1; re-extract with evidence", report)
        source = document["source"]
        if source["name"] != "nomad-simulations" or not source["dependencies"].get("nomad-lab"):
            raise NomadImportError("NOMAD import requires nomad-simulations and nomad-lab versions",
                                   report)
        # A lost source definition cannot be hidden by comparing two incomplete projections.
        omissions = [row for row in report if row["status"] == "skipped" and not (
            row["path"].endswith(".__bases__.MSection") and
            row["reason"] == "metainfo framework class excluded from source model"
        )]
        if omissions:
            raise NomadImportError("Incomplete NOMAD extraction:\n" + "\n".join(
                f"{row['path']}: {row['reason']}" for row in omissions), report)
        records = {row["id"]: row for row in sorted(document["classes"], key=lambda r: r["id"])}
        try:
            graph = {name: row["bases"] for name, row in records.items()}
            tuple(TopologicalSorter(graph).static_order())
        except CycleError as error:
            raise NomadImportError(f"Unsupported inheritance cycle: {error}", report) from error
        pins = {name: version(name) for name in ("linkml", "linkml-runtime", "linkml-map", "sssom")}
        schema = SchemaDefinition(
            id=f"https://w3id.org/schematerial/nomad/{source['module']}",
            name=source["module"], title=f"NOMAD {source['module']}", version=source["version"],
            imports=["linkml:types"], prefixes=[
                Prefix(prefix_prefix="linkml", prefix_reference="https://w3id.org/linkml/"),
                Prefix(prefix_prefix="smat", prefix_reference="https://w3id.org/schematerial/core/"),
            ],
        )
        set_annotation(schema, "toolchain_versions", json.dumps(pins, sort_keys=True))
        set_annotation(schema, "source_dependencies",
                       json.dumps(source["dependencies"], sort_keys=True))
        schema.enums = {row["id"]: EnumDefinition(name=row["id"], permissible_values=row["values"])
                        for row in sorted(document["enums"], key=lambda r: r["id"])}
        for name, row in records.items():
            cls = ClassDefinition(name=name, title=row["name"], description=row.get("description"),
                                  class_uri=element_id(Source.NOMAD_SIMULATION, (name,)),
                                  is_a=row["bases"][0] if row["bases"] else None,
                                  mixins=row["bases"][1:])
            set_annotation(cls, "source_bases", json.dumps(row["bases"]))
            set_annotation(cls, "source_effective_attributes", json.dumps(
                sorted(row["effective_attributes"], key=lambda r: r["name"]), sort_keys=True))
            for raw in sorted(row["attributes"], key=lambda a: a["name"]):
                add_attribute(cls, _attribute(name, raw, report))
            add_class(schema, cls)
        validate_schema_facets(schema)

        def verify(materialized: SchemaDefinition) -> None:
            problems = []
            for name, row in records.items():
                actual = attributes_of(class_of(materialized, name))
                expected = {
                    ref["name"]: attributes_of(
                        class_of(schema, ref["declaring_class_id"]))[ref["name"]]
                    for ref in row["effective_attributes"]
                }
                for attr_name in sorted(actual.keys() | expected.keys()):
                    observed = _signature(actual[attr_name]) if attr_name in actual else None
                    wanted = _signature(expected[attr_name]) if attr_name in expected else None
                    if observed != wanted:
                        problems.append({"path": f"{name}.{attr_name}", "status": "skipped",
                                         "reason": (f"inheritance mismatch: NOMAD={wanted}; "
                                                    f"LinkML={observed}")})
            if problems:
                raise NomadImportError("Unsupported NOMAD inheritance:\n" + "\n".join(
                    f"{row['path']}: {row['reason']}" for row in problems), report + problems)

        key = self.cache.prepare(_canonical_yaml(schema), validate=verify)
        materialized = self.cache.get(key)
        loaded = LoadedSchema(materialized, snapshot_index(materialized, Source.NOMAD_SIMULATION))
        return NomadImport(schema, loaded, key, tuple(report))
