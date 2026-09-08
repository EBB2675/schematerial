"""BAM masterdata extraction JSON to verified canonical LinkML; no source-package imports."""

import json
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from importlib.metadata import version
from pathlib import Path
from typing import Any

from linkml_runtime.dumpers import json_dumper, yaml_dumper
from linkml_runtime.linkml_model.meta import (
    ClassDefinition,
    EnumDefinition,
    PermissibleValue,
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
    set_annotation,
)
from schematerial.cache import MaterialisationCache
from schematerial.extraction.contract import enum_value, read_document, validate_document
from schematerial.facets import FACET_TAGS, validate_schema_facets, write_facets
from schematerial.identity import Source, element_id, snapshot_index
from schematerial.loading import LoadedSchema
from schematerial.models.core import MaterialsFacets
from schematerial.parsers.source import SchemaImportError

# openBIS data type to LinkML range. Each row is tested. None means the type is
# retained as an explicitly unsupported source type: an unmapped type is reported
# and left without a range, never given a guessed string one.
#
# CONTROLLEDVOCABULARY and OBJECT normally arrive already resolved, as an enum or
# class range naming the target the source states. They reach this table only
# when the source's own target code resolved to nothing or to several
# definitions, which the extractor reports; there is no target to invent here.
TYPE_RANGES: dict[str, str | None] = {
    "BOOLEAN": "boolean",
    "INTEGER": "integer",
    "REAL": "double",
    "VARCHAR": "string",
    "MULTILINE_VARCHAR": "string",
    "HYPERLINK": "uri",
    "DATE": "date",
    "TIMESTAMP": "datetime",
    "XML": None,
    "SAMPLE": None,
    "CONTROLLEDVOCABULARY": None,
    "OBJECT": None,
}

# Exact spelling table over the source's pint units: no dimensional inference and
# no source-package unit registry. A spelling with no unambiguous UCUM code stays
# an annotation with a diagnostic rather than acquiring an invented one.
UNIT_CODES = {
    "degree": "deg", "s": "s", "angstrom": "Ao", "kV": "kV", "mA": "mA",
}

# Source facts kept as their own annotation rather than only inside the source
# annotation map, because a consumer reads them directly.
PROPERTY_CODE = "source_property_code"
ENTITY_CODE = "source_entity_code"


class BamImportError(SchemaImportError):
    """A BAM masterdata document that cannot be presented as a faithful schema.

    The shared base is what lets a consumer report a refused import without
    knowing which source it came from.
    """


@dataclass(frozen=True)
class BamImport:
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
    header = "# Generated BAM masterdata canonical schema\n"
    return header + "".join(f"# {name}=={pin}\n" for name, pin in pins.items()) + (
        yaml_dumper.dumps(schema))


def _permissible(value: str | dict[str, Any]) -> PermissibleValue:
    """One vocabulary term, keeping the label and description the source states."""
    if isinstance(value, str):
        return PermissibleValue(text=value)
    permissible = PermissibleValue(
        text=value["value"], title=value.get("title"), description=value.get("description"),
    )
    # JSON text, so a boolean or numeric source fact reads back as what it was.
    for tag, item in sorted(value.get("annotations", {}).items()):
        set_annotation(permissible, tag, json.dumps(item))
    return permissible


def _attribute(
    owner: str, raw: dict[str, Any], report: list[dict[str, str]],
) -> SlotDefinition:
    path = f"{owner}.{raw['name']}"

    def partial(reason: str) -> None:
        report.append({"path": path, "status": "partial", "reason": reason})

    range_ = raw["range"]
    annotations = raw.get("annotations", {})
    target = TYPE_RANGES.get(range_["name"]) if range_["kind"] == "datatype" else range_["name"]
    attribute = SlotDefinition(
        name=raw["name"], description=raw.get("description"), range=target,
        slot_uri=element_id(Source.BAM_MASTERDATA, (owner, raw["name"])),
    )
    set_annotation(attribute, "source_declaring_class", owner)
    set_annotation(attribute, "source_kind", raw["kind"])
    set_annotation(attribute, "source_range", json.dumps(range_, sort_keys=True))
    if range_["kind"] == "datatype":
        # The raw openBIS name is retained alongside the normalised LinkML range.
        set_annotation(attribute, "source_type", range_["name"])
        if target is None:
            known = range_["name"] in TYPE_RANGES
            partial(f"{'unsupported' if known else 'unmapped'} source type: {range_['name']}")
    # One global property assigned to several classes becomes one class-local
    # attribute per class, each carrying that one global code.
    code = annotations.get("property_code")
    if isinstance(code, str):
        set_annotation(attribute, PROPERTY_CODE, code)
    if "unit" in raw:
        unit = raw["unit"]
        ucum = UNIT_CODES.get(unit, unit if unit in UNIT_CODES.values() else None)
        set_annotation(attribute, "source_unit", unit)
        if ucum is None:
            partial(f"unmapped source unit: {unit}")
        else:
            attribute.unit = UnitOfMeasure(ucum_code=ucum)
    write_facets(attribute, MaterialsFacets.model_validate(
        {tag: value for tag, value in annotations.items() if tag in FACET_TAGS}
    ))
    # Retain other source facts under one namespace, without overwriting adapter provenance.
    if annotations:
        set_annotation(attribute, "source_annotations", json.dumps(annotations, sort_keys=True))
    return attribute


def _signature(attribute: SlotDefinition) -> dict[str, Any]:
    value = json.loads(json_dumper.dumps(attribute))
    tags = ("source_kind", "source_range", "source_type", "source_unit",
            "source_declaring_class", "source_annotations", PROPERTY_CODE, *FACET_TAGS)
    annotations = value.get("annotations", {})
    return {
        "range": value.get("range"), "unit": value.get("unit"),
        "description": value.get("description"),
        "multivalued": bool(value.get("multivalued")),
        **{tag: annotations.get(tag) for tag in tags},
    }


class BamAdapter:
    """Only JSON enters this boundary. Inheritance is delegated to pinned SchemaView."""

    def __init__(self, cache: MaterialisationCache | None = None) -> None:
        self.cache = cache if cache is not None else MaterialisationCache()

    def read(self, source: str | Path) -> BamImport:
        return self.convert(read_document(Path(source).read_text(encoding="utf-8")))

    def convert(self, document: dict[str, Any]) -> BamImport:
        document = validate_document(document)
        report = [dict(item) for item in document["report"]]
        if document["contract_version"] != "1.2":
            raise BamImportError(
                "BAM masterdata import requires contract 1.2; re-extract with evidence", report)
        source = document["source"]
        if source["name"] != "bam-masterdata" or not source["dependencies"].get("pydantic"):
            raise BamImportError(
                "BAM masterdata import requires bam-masterdata and pydantic versions", report)
        # A lost source definition cannot be hidden by comparing two incomplete projections.
        omissions = [row for row in report if row["status"] == "skipped" and not (
            ".__bases__." in row["path"] and
            row["reason"] == "masterdata framework class excluded from source model"
        )]
        if omissions:
            raise BamImportError("Incomplete BAM masterdata extraction:\n" + "\n".join(
                f"{row['path']}: {row['reason']}" for row in omissions), report)
        records = {row["id"]: row for row in sorted(document["classes"], key=lambda r: r["id"])}
        try:
            graph = {name: row["bases"] for name, row in records.items()}
            tuple(TopologicalSorter(graph).static_order())
        except CycleError as error:
            raise BamImportError(f"Unsupported inheritance cycle: {error}", report) from error
        pins = {name: version(name) for name in ("linkml", "linkml-runtime", "linkml-map", "sssom")}
        schema = SchemaDefinition(
            id=f"https://w3id.org/schematerial/bam/{source['module']}",
            name=source["module"], title=f"BAM masterdata {source['module']}",
            version=source["version"], imports=["linkml:types"], prefixes=[
                Prefix(prefix_prefix="linkml", prefix_reference="https://w3id.org/linkml/"),
                Prefix(prefix_prefix="smat", prefix_reference="https://w3id.org/schematerial/core/"),
            ],
        )
        set_annotation(schema, "toolchain_versions", json.dumps(pins, sort_keys=True))
        set_annotation(schema, "source_dependencies",
                       json.dumps(source["dependencies"], sort_keys=True))
        schema.enums = {
            row["id"]: EnumDefinition(
                name=row["id"],
                permissible_values=[_permissible(value) for value in sorted(
                    row["values"], key=enum_value)],
            )
            for row in sorted(document["enums"], key=lambda r: r["id"])
        }
        for name, row in records.items():
            annotations = row.get("annotations", {})
            cls = ClassDefinition(name=name, title=row["name"], description=row.get("description"),
                                  class_uri=element_id(Source.BAM_MASTERDATA, (name,)),
                                  is_a=row["bases"][0] if row["bases"] else None,
                                  mixins=row["bases"][1:])
            set_annotation(cls, "source_bases", json.dumps(row["bases"]))
            set_annotation(cls, "source_effective_attributes", json.dumps(
                sorted(row["effective_attributes"], key=lambda r: r["name"]), sort_keys=True))
            # The openBIS entity code is this definition's identity in openBIS.
            code = annotations.get("code")
            if isinstance(code, str):
                set_annotation(cls, ENTITY_CODE, code)
            if annotations:
                set_annotation(cls, "source_annotations", json.dumps(annotations, sort_keys=True))
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
                                         "reason": (f"inheritance mismatch: masterdata={wanted}; "
                                                    f"LinkML={observed}")})
            if problems:
                raise BamImportError("Unsupported BAM masterdata inheritance:\n" + "\n".join(
                    f"{row['path']}: {row['reason']}" for row in problems), report + problems)

        key = self.cache.prepare(_canonical_yaml(schema), validate=verify)
        materialized = self.cache.get(key)
        loaded = LoadedSchema(materialized, snapshot_index(materialized, Source.BAM_MASTERDATA))
        return BamImport(schema, loaded, key, tuple(report))
