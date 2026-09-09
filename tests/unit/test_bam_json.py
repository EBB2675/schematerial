"""JSON-boundary adapter tests: only small inline schemas, no source imports."""

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from linkml_runtime.linkml_model.meta import PermissibleValue, UnitOfMeasure
from linkml_runtime.utils.schemaview import SchemaView

from schematerial._linkml import annotations_of, attributes_of, class_of, enums_of, slots_of
from schematerial.cache import MaterialisationCache, content_hash
from schematerial.extraction.contract import ContractError, validate_document
from schematerial.extraction.runner import ExtractorEnvironment, ExtractorError, run_extractor
from schematerial.facets import read_facets
from schematerial.identity import element_id, parse_element_id
from schematerial.parsers.bam_json import (
    PROPERTY_CODE,
    TYPE_RANGES,
    UNIT_CODES,
    BamAdapter,
    BamImportError,
)
from schematerial.parsers.nomad_json import NomadImportError
from schematerial.parsers.registry import ADAPTERS, adapter_for

FAKE = Path(__file__).parents[2] / "src/schematerial/extractors/fake.py"


def prop(name: str = "alias", data_type: str = "VARCHAR", code: str | None = None,
         **kwargs: Any) -> dict[str, Any]:
    annotations = {"data_type": data_type, "property_code": code or name.upper(),
                   **kwargs.pop("annotations", {})}
    return {"name": name, "kind": "property", "annotations": annotations,
            "range": kwargs.pop("range", {"kind": "datatype", "name": data_type}), **kwargs}


def ref(owner: str, name: str = "alias") -> dict[str, str]:
    return {"name": name, "kind": "property", "declaring_class_id": owner}


def cls(name: str, attrs: list[dict[str, Any]], bases: list[str] | None = None,
        effective: list[dict[str, str]] | None = None, **annotations: Any) -> dict[str, Any]:
    return {"id": name, "name": name.rsplit(".", 1)[-1], "attributes": attrs,
            "bases": bases or [], "annotations": {"entity_kind": "ObjectTypeDef", **annotations},
            "effective_attributes": effective if effective is not None else
            [ref(name, a["name"]) for a in attrs]}


def document(*classes: dict[str, Any], enums: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"contract_version": "1.2", "source": {"name": "bam-masterdata", "version": "0.13.1",
            "module": "fixture", "dependencies": {"pydantic": "2.13.5"}},
            "classes": list(classes), "enums": enums or [], "report": []}


def boundary(doc: dict[str, Any]) -> dict[str, Any]:
    """Every document crosses the real out-of-process JSON boundary."""
    return run_extractor(ExtractorEnvironment("inline", Path(sys.executable)), FAKE,
                         input_text=json.dumps(doc))


def field(result: Any, owner: str = "Instrument", name: str = "alias") -> Any:
    return attributes_of(class_of(result.loaded.schema, owner))[name]


@pytest.mark.parametrize("data_type,expected", sorted(TYPE_RANGES.items()))
def test_every_openbis_data_type_row(data_type: str, expected: str | None) -> None:
    result = BamAdapter().convert(boundary(document(cls("Instrument", [prop(
        data_type=data_type)]))))
    assert field(result).range == expected
    # The raw openBIS name is stored alongside the normalised range.
    assert annotations_of(field(result))["source_type"].value == data_type
    reported = [row for row in result.report if row["path"] == "Instrument.alias"]
    assert bool(reported) == (expected is None)
    if expected is None:
        assert data_type in reported[0]["reason"] and reported[0]["status"] == "partial"


def test_an_unknown_source_type_is_reported_and_never_guessed() -> None:
    result = BamAdapter().convert(boundary(document(cls("Instrument", [prop(
        data_type="UNFAMILIAR")]))))
    assert field(result).range is None
    assert annotations_of(field(result))["source_type"].value == "UNFAMILIAR"
    assert any("unmapped source type: UNFAMILIAR" in row["reason"] for row in result.report)


@pytest.mark.parametrize("raw,code", sorted(UNIT_CODES.items()))
def test_unit_table(raw: str, code: str) -> None:
    result = BamAdapter().convert(boundary(document(cls("Instrument", [prop(
        data_type="REAL", unit=raw)]))))
    unit = field(result).unit
    assert isinstance(unit, UnitOfMeasure) and unit.ucum_code == code
    assert annotations_of(field(result))["source_unit"].value == raw


def test_a_unit_with_no_unambiguous_code_is_reported_not_invented() -> None:
    result = BamAdapter().convert(boundary(document(cls("Instrument", [prop(
        data_type="REAL", unit="rpm")]))))
    assert field(result).unit is None
    assert annotations_of(field(result))["source_unit"].value == "rpm"
    assert any("unmapped source unit: rpm" in row["reason"] for row in result.report)


def test_one_global_property_on_two_classes_becomes_two_attributes_with_one_code() -> None:
    result = BamAdapter().convert(boundary(document(
        cls("Instrument", [prop("name", code="$NAME")]),
        cls("Sample", [prop("name", code="$NAME")]),
    )))
    codes = {
        owner: str(annotations_of(field(result, owner, "name"))[PROPERTY_CODE].value)
        for owner in ("Instrument", "Sample")
    }
    assert codes == {"Instrument": "$NAME", "Sample": "$NAME"}
    # Class-local attributes with distinct identities, never one global slot.
    assert not slots_of(result.loaded.schema)
    identifiers = {str(field(result, owner, "name").slot_uri) for owner in codes}
    assert identifiers == {element_id("bammd", (owner, "name")) for owner in codes}
    assert len(identifiers) == 2


def test_vocabulary_enum_keeps_term_labels_and_descriptions() -> None:
    doc = document(
        cls("Status", [], entity_kind="VocabularyTypeDef", code="STATUS",
            vocabulary_enum="Status.terms"),
        cls("Instrument", [prop("state", "CONTROLLEDVOCABULARY",
                                range={"kind": "enum", "name": "Status.terms"})]),
        enums=[{"id": "Status.terms", "values": [
            {"value": "RETIRED", "title": "Retired", "description": "No longer in use",
             "annotations": {"official": True}},
            "ACTIVE",
        ]}],
    )
    result = BamAdapter().convert(boundary(doc))
    assert field(result, name="state").range == "Status.terms"
    values = enums_of(result.loaded.schema)["Status.terms"].permissible_values
    assert isinstance(values, dict) and sorted(values) == ["ACTIVE", "RETIRED"]
    retired = values["RETIRED"]
    assert isinstance(retired, PermissibleValue)
    assert str(retired.title) == "Retired" and str(retired.description) == "No longer in use"
    assert str(annotations_of(retired)["official"].value) == "true"
    # The vocabulary type is also a class, keeping its own openBIS entity code.
    status = class_of(result.schema, "Status")
    assert str(annotations_of(status)["source_entity_code"].value) == "STATUS"


def test_entity_metadata_and_object_reference_survive_conversion() -> None:
    result = BamAdapter().convert(boundary(document(
        cls("Person", [prop("name", code="$NAME")], code="PERSON"),
        cls("Instrument", [prop("owner", "OBJECT", range={"kind": "class", "name": "Person"})],
            code="INSTRUMENT", generated_code_prefix="INS", auto_generate_codes=True),
    )))
    instrument = class_of(result.schema, "Instrument")
    assert str(annotations_of(instrument)["source_entity_code"].value) == "INSTRUMENT"
    facts = json.loads(str(annotations_of(instrument)["source_annotations"].value))
    assert facts["generated_code_prefix"] == "INS" and facts["auto_generate_codes"] is True
    assert field(result, name="owner").range == "Person"
    # A class range is a schema path the snapshot walker descends.
    assert "bammd:Instrument.owner.name" in result.loaded.snapshots


def test_inheritance_is_real_python_inheritance_with_effective_attributes() -> None:
    result = BamAdapter().convert(boundary(document(
        cls("Instrument", [prop("name", code="$NAME")]),
        cls("Camera", [prop("resolution", "INTEGER")], ["Instrument"],
            [ref("Instrument", "name"), ref("Camera", "resolution")]),
    )))
    camera = class_of(result.schema, "Camera")
    assert camera.is_a == "Instrument" and not list(camera.mixins or [])
    assert set(attributes_of(camera)) == {"resolution"}
    # The materialised view carries the inherited property, with its declaring class.
    assert set(attributes_of(class_of(result.loaded.schema, "Camera"))) == {"name", "resolution"}
    inherited = field(result, "Camera", "name")
    assert str(annotations_of(inherited)["source_declaring_class"].value) == "Instrument"
    assert str(annotations_of(inherited)[PROPERTY_CODE].value) == "$NAME"
    assert result.loaded.snapshots["bammd:Camera.name"].source_version == "0.13.1"


@pytest.mark.parametrize("pattern", ["missing", "extra", "owner", "type", "unit"])
def test_effective_reference_mismatch_is_refused_and_named(pattern: str) -> None:
    base = cls("Instrument", [prop("name", code="$NAME")])
    other = cls("Sample", [prop("name", "INTEGER", code="$NAME")])
    bases, expected = ["Instrument"], [ref("Instrument", "name")]
    classes = [base, other]
    if pattern == "missing":
        bases = []
    elif pattern == "extra":
        expected = []
    elif pattern == "owner":
        bases, expected = ["Sample"], [ref("Instrument", "name")]
    elif pattern == "type":
        base["attributes"] = [prop("name", "INTEGER", code="$NAME")]
        expected = [ref("Sample", "name")]
        bases = ["Instrument"]
    else:
        base["attributes"] = [prop("name", "REAL", code="$NAME", unit="degree")]
        other["attributes"] = [prop("name", "REAL", code="$NAME")]
        expected = [ref("Sample", "name")]
    classes.append(cls("Camera", [], bases, expected))
    cache = MaterialisationCache()
    captured: list[str] = []
    original = cache.prepare

    def prepare(source: str, **kwargs: Any) -> str:
        captured.append(content_hash(source))
        return original(source, **kwargs)

    with patch.object(cache, "prepare", side_effect=prepare):
        with pytest.raises(BamImportError, match="Camera.name.*masterdata=.*LinkML=") as error:
            BamAdapter(cache).convert(boundary(document(*classes)))
    assert any(row["path"] == "Camera.name" for row in error.value.report)
    # A refused import publishes nothing a later caller could read as verified.
    with pytest.raises(KeyError):
        cache.get(captured[0])


def test_unresolvable_effective_reference_fails_at_the_contract() -> None:
    doc = document(cls("Instrument", [prop("name")], effective=[ref("Absent", "name")]))
    with pytest.raises(ContractError, match=r"\$\.classes\[0\].effective_attributes\[0\]"):
        validate_document(doc)


@pytest.mark.parametrize("change,match", [
    ("version", "requires contract 1.2"),
    ("dependencies", "requires bam-masterdata and pydantic"),
    ("omission", "Incomplete BAM masterdata extraction"),
    ("cycle", "inheritance cycle"),
])
def test_refused_imports_name_their_reason(change: str, match: str) -> None:
    doc = boundary(document(cls("Instrument", [prop()])))
    if change == "version":
        # A valid 1.1 document: evidence present, but none of the 1.2 additions.
        doc["contract_version"] = "1.1"
        for row in doc["classes"]:
            del row["annotations"]
    elif change == "dependencies":
        doc["source"]["dependencies"] = {}
    elif change == "omission":
        doc["report"] = [{"path": "Instrument", "status": "skipped", "reason": "malformed entity"}]
    else:
        doc["classes"][0]["bases"] = ["Instrument"]
    with pytest.raises(BamImportError, match=match):
        BamAdapter().convert(doc)


def test_the_reported_framework_base_exclusion_is_the_only_allowed_omission() -> None:
    doc = boundary(document(cls("Instrument", [prop()])))
    doc["report"] = [{"path": "Instrument.__bases__.ObjectType", "status": "skipped",
                      "reason": "masterdata framework class excluded from source model"}]
    result = BamAdapter().convert(doc)
    assert result.report[0]["path"] == "Instrument.__bases__.ObjectType"


def test_adapters_are_selected_by_source_and_refuse_each_others_documents() -> None:
    doc = boundary(document(cls("Instrument", [prop()])))
    assert ADAPTERS["bam-masterdata"] is BamAdapter
    adapter = adapter_for("bam-masterdata", MaterialisationCache())
    assert isinstance(adapter, BamAdapter)
    assert adapter.convert(doc).schema.name == "fixture"
    # A sibling adapter, not a branch: each refuses a document it did not read.
    from schematerial.parsers.nomad_json import NomadAdapter

    with pytest.raises(NomadImportError):
        NomadAdapter().convert(doc)
    # Even at the contract version it does read, the source package still decides.
    legacy = boundary(document(cls("Instrument", [prop()])))
    legacy["contract_version"] = "1.1"
    for row in legacy["classes"]:
        del row["annotations"]
    with pytest.raises(NomadImportError, match="nomad-simulations"):
        NomadAdapter().convert(legacy)


def test_identifiers_use_the_bam_prefix_throughout() -> None:
    result = BamAdapter().convert(boundary(document(
        cls("Instrument", [prop("name", code="$NAME")]))))
    sources = {parse_element_id(str(class_of(result.schema, "Instrument").class_uri)).source}
    sources |= {parse_element_id(str(field(result, name="name").slot_uri)).source}
    sources |= {parse_element_id(key).source for key in result.loaded.snapshots}
    assert sources == {"bammd"}


def test_warm_cache_does_no_materialisation_and_output_is_stable() -> None:
    adapter = BamAdapter()
    doc = boundary(document(cls("Instrument", [prop()]), cls("Sample", [prop("name")])))
    original = SchemaView.materialize_derived_schema
    with patch.object(SchemaView, "materialize_derived_schema", autospec=True,
                      side_effect=original) as materialize:
        first = adapter.convert(doc)
        doc["classes"].reverse()
        second = adapter.convert(doc)
        assert materialize.call_count == 1
    assert first.cache_key == second.cache_key == content_hash(first.to_yaml())
    assert first.loaded.snapshots == second.loaded.snapshots
    assert first.to_yaml().startswith("# Generated BAM masterdata canonical schema\n")


def test_explicit_facets_survive_and_absent_semantics_stay_absent() -> None:
    result = BamAdapter().convert(boundary(document(cls("Instrument", [
        prop(), prop("grounded", annotations={"semantic_type": "unfamiliar:Energy"}),
    ]))))
    assert read_facets(field(result)).semantic_type is None
    assert read_facets(field(result, name="grounded")).semantic_type == "unfamiliar:Energy"


def nomad_document() -> dict[str, Any]:
    """A NOMAD document, so both real adapters can be ingested side by side."""
    return {"contract_version": "1.1", "source": {
        "name": "nomad-simulations", "version": "0.6.0", "module": "nomad_fixture",
        "dependencies": {"nomad-lab": "1.4.0"}}, "enums": [], "report": [], "classes": [{
            "id": "Run", "name": "Run", "bases": [], "attributes": [
                {"name": "value", "kind": "quantity",
                 "range": {"kind": "datatype", "name": "builtins.float"}}],
            "effective_attributes": [
                {"name": "value", "kind": "quantity", "declaring_class_id": "Run"}]}]}


def test_the_converted_schema_loads_in_the_preview_alongside_nomad(tmp_path: Path) -> None:
    from schematerial.web.preview import ingest

    def write(doc: dict[str, Any], name: str) -> Path:
        path = tmp_path / name
        path.write_text(json.dumps(boundary(doc)), encoding="utf-8")
        return path

    bam = document(
        cls("Instrument", [prop("name", code="$NAME")], code="INSTRUMENT"),
        cls("Camera", [prop("resolution", "INTEGER")], ["Instrument"],
            [ref("Instrument", "name"), ref("Camera", "resolution")], code="CAMERA.INSTRUMENT"),
    )
    previews = ingest([write(bam, "bam.json"), write(nomad_document(), "nomad.json")])
    # Each pane is addressed by module and version.
    assert [preview.name for preview in previews] == ["fixture@0.13.1", "nomad_fixture@0.6.0"]
    assert all(preview.status == "ok" for preview in previews)
    masterdata, nomad = previews
    assert masterdata.summary["source"]["package"] == "bam-masterdata"
    assert masterdata.summary["counts"]["effective_attributes"] == 3
    # Each import keeps the source prefix its own adapter wrote.
    assert all(parse_element_id(row["id"]).source == "bammd" for row in masterdata.index)
    assert all(parse_element_id(row["id"]).source == "nomadsim" for row in nomad.index)
    # The inherited property is browsable on the subclass, with its declaring class.
    inherited = masterdata.details[element_id("bammd", ("Camera", "name"))]
    assert inherited["inherited"] is True
    assert inherited["declared_in"]["id"] == element_id("bammd", ("Instrument",))
    assert inherited["source"]["annotations"]["property_code"] == "$NAME"


def test_the_adapter_needs_no_source_package_and_the_runner_names_a_missing_one(
    tmp_path: Path,
) -> None:
    import importlib.util

    # The adapter reads JSON only; the source package is absent from this environment.
    assert importlib.util.find_spec("bam_masterdata") is None
    assert BamAdapter().convert(boundary(document(cls("Instrument", [prop()])))).schema.name
    extractor = Path(__file__).parents[2] / "src/schematerial/extractors/bam.py"
    with pytest.raises(ExtractorError, match="bam-masterdata-missing.*interpreter"):
        run_extractor(ExtractorEnvironment("bam-masterdata-missing", tmp_path / "absent/python"),
                      extractor, arguments=("--module", "bam_masterdata.datamodel.object_types"))
