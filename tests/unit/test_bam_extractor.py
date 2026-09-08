"""BAM masterdata reflection edge cases using inline objects, never source packages."""

import runpy
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

from schematerial.extraction.contract import validate_document

EXTRACTOR = Path(__file__).parents[2] / "src/schematerial/extractors/bam.py"
_MODULE = runpy.run_path(str(EXTRACTOR))
extract = _MODULE["extract"]
is_entity = _MODULE["is_entity"]

# The openBIS data types the reader must be able to carry across unchanged. The
# list is written here rather than read from the source package, so the suite
# never needs one installed; the reader emits whatever the source states.
OPENBIS_DATA_TYPES = (
    "BOOLEAN", "CONTROLLEDVOCABULARY", "DATE", "HYPERLINK", "INTEGER",
    "MULTILINE_VARCHAR", "OBJECT", "REAL", "SAMPLE", "TIMESTAMP", "VARCHAR", "XML",
)


def definition(kind: str, code: str, **fields: Any) -> Any:
    """A stand-in for a masterdata `*TypeDef`, recognised by its class name."""
    return type(kind, (SimpleNamespace,), {})(code=code, description=f"{code} description",
                                              **fields)


def assignment(code: str, data_type: str | None = "VARCHAR", **fields: Any) -> Any:
    return type("PropertyTypeAssignment", (SimpleNamespace,), {})(
        code=code, data_type=data_type, description=f"{code} description",
        property_label=code.title(), section="General", mandatory=False, **fields)


def term(code: str, **fields: Any) -> Any:
    return type("VocabularyTerm", (SimpleNamespace,), {})(
        code=code, label=code.title(), description=f"{code} description", official=True, **fields)


def entity(name: str, defs: Any, bases: tuple[type, ...] = (), /, **members: Any) -> type:
    # Positional-only: a masterdata class really does assign a property called `name`.
    return type(name, bases, {"__module__": "fixture", "defs": defs, **members})


def fixture_module() -> ModuleType:
    module = ModuleType("fixture")
    vocabulary = entity("Status", definition("VocabularyTypeDef", "STATUS"),
                        active=term("ACTIVE"), retired=term("RETIRED"))
    instrument = entity(
        "Instrument", definition("ObjectTypeDef", "INSTRUMENT", generated_code_prefix="INS",
                                 auto_generate_codes=True),
        name=assignment("$NAME"),
        state=assignment("STATE", "CONTROLLEDVOCABULARY", vocabulary_code="STATUS"),
    )
    camera = entity("Camera", definition("ObjectTypeDef", "CAMERA.INSTRUMENT"), (instrument,),
                    name=assignment("$NAME"), resolution=assignment("RESOLUTION", "INTEGER"))
    for name, value in (("Status", vocabulary), ("Instrument", instrument), ("Camera", camera)):
        vars(module)[name] = value
    return module


def classes_of(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["name"]: row for row in document["classes"]}


def test_recognition_rule_needs_a_local_defs_holding_a_type_def() -> None:
    assert is_entity(entity("Object", definition("ObjectTypeDef", "OBJ")))
    # A framework base declares no `defs`, and an inheriting class does not own one.
    framework = type("ObjectType", (), {"__module__": "fixture"})
    assert not is_entity(framework)
    assert not is_entity(type("Child", (entity("P", definition("ObjectTypeDef", "P")),), {}))
    assert not is_entity(entity("NotADef", SimpleNamespace(code="X")))
    assert not is_entity("Instrument")


def test_entity_metadata_properties_and_python_inheritance() -> None:
    document = validate_document(extract(fixture_module(), "0.13.1"))
    assert document["contract_version"] == "1.2"
    assert document["source"]["name"] == "bam-masterdata"
    classes = classes_of(document)
    camera = classes["Camera"]
    assert camera["bases"] == ["fixture.Instrument"]
    assert camera["annotations"] == {"entity_kind": "ObjectTypeDef", "code": "CAMERA.INSTRUMENT"}
    assert classes["Instrument"]["annotations"]["generated_code_prefix"] == "INS"
    resolution = next(a for a in camera["attributes"] if a["name"] == "resolution")
    assert resolution["kind"] == "property"
    assert resolution["range"] == {"kind": "datatype", "name": "INTEGER"}
    assert resolution["annotations"]["property_code"] == "RESOLUTION"
    assert resolution["annotations"]["data_type"] == "INTEGER"
    # Real Python inheritance: the base's properties are effective, not copied.
    effective = camera["effective_attributes"]
    assert {row["name"] for row in effective} == {"name", "resolution", "state"}
    assert {row["declaring_class_id"] for row in effective} == {
        "fixture.Camera", "fixture.Instrument"}
    assert document["report"] == []


def test_one_global_property_on_two_classes_keeps_one_code() -> None:
    document = extract(fixture_module(), "v")
    classes = classes_of(document)
    codes = {
        name: next(a["annotations"]["property_code"]
                   for a in classes[name]["attributes"] if a["name"] == "name")
        for name in ("Instrument", "Camera")
    }
    assert codes == {"Instrument": "$NAME", "Camera": "$NAME"}
    # Two class-local declarations, not one shared definition.
    assert all(len([a for a in classes[name]["attributes"] if a["name"] == "name"]) == 1
               for name in ("Instrument", "Camera"))


def test_vocabulary_becomes_a_class_and_an_enum_with_term_metadata() -> None:
    document = validate_document(extract(fixture_module(), "v"))
    vocabulary = classes_of(document)["Status"]
    assert vocabulary["annotations"]["entity_kind"] == "VocabularyTypeDef"
    assert vocabulary["annotations"]["code"] == "STATUS"
    assert vocabulary["attributes"] == []
    # The class and its value space cannot share one name, or a range would be ambiguous.
    enum_name = vocabulary["annotations"]["vocabulary_enum"]
    assert enum_name == "fixture.Status.terms" != vocabulary["id"]
    values = next(row for row in document["enums"] if row["id"] == enum_name)["values"]
    assert values == [
        {"value": "ACTIVE", "title": "Active", "description": "ACTIVE description",
         "annotations": {"official": True}},
        {"value": "RETIRED", "title": "Retired", "description": "RETIRED description",
         "annotations": {"official": True}},
    ]
    instrument = classes_of(document)["Instrument"]["attributes"]
    state = next(a for a in instrument if a["name"] == "state")
    assert state["range"] == {"kind": "enum", "name": enum_name}
    assert state["annotations"]["vocabulary_code"] == "STATUS"


def test_every_openbis_data_type_survives_extraction_verbatim() -> None:
    module = ModuleType("fixture")
    vars(module)["Sample"] = entity(
        "Sample", definition("ObjectTypeDef", "SAMPLE"),
        **{name.lower(): assignment(name, name) for name in OPENBIS_DATA_TYPES},
    )
    document = validate_document(extract(module, "v"))
    attributes = {a["name"]: a for a in classes_of(document)["Sample"]["attributes"]}
    assert {a["annotations"]["data_type"] for a in attributes.values()} == set(OPENBIS_DATA_TYPES)
    # No source type is interpreted here; unresolved targets keep the raw name.
    assert all(a["range"] == {"kind": "datatype", "name": a["annotations"]["data_type"]}
               for a in attributes.values())
    assert {row["path"] for row in document["report"]} == {
        "fixture.Sample.controlledvocabulary", "fixture.Sample.object"}


def test_unresolved_and_ambiguous_target_codes_are_reported_not_guessed() -> None:
    module = fixture_module()
    twin = entity("Duplicate", definition("VocabularyTypeDef", "STATUS"), retired=term("RETIRED"))
    vars(module)["Duplicate"] = twin
    vars(module)["Missing"] = entity(
        "Missing", definition("ObjectTypeDef", "MISSING"),
        absent=assignment("ABSENT", "CONTROLLEDVOCABULARY", vocabulary_code="NOWHERE"))
    document = validate_document(extract(module, "v"))
    reasons = {row["path"]: row["reason"] for row in document["report"]}
    assert "ambiguous vocabulary_code 'STATUS'" in reasons["fixture.Instrument.state"]
    assert "fixture.Duplicate" in reasons["fixture.Instrument.state"]
    assert "unresolved vocabulary_code 'NOWHERE'" in reasons["fixture.Missing.absent"]
    assert all(row["status"] == "partial" for row in document["report"])
    attributes = {a["name"]: a for a in classes_of(document)["Instrument"]["attributes"]}
    assert attributes["state"]["range"] == {"kind": "datatype", "name": "CONTROLLEDVOCABULARY"}


def test_framework_bases_are_excluded_and_reported() -> None:
    module = ModuleType("fixture")
    framework = type("ObjectType", (), {"__module__": "fixture"})
    vars(module)["Instrument"] = entity(
        "Instrument", definition("ObjectTypeDef", "INSTRUMENT"), (framework,),
        name=assignment("$NAME"))
    document = validate_document(extract(module, "v"))
    assert classes_of(document)["Instrument"]["bases"] == []
    assert document["report"] == [{
        "path": "fixture.Instrument.__bases__.ObjectType", "status": "skipped",
        "reason": "masterdata framework class excluded from source model"}]


def test_malformed_entity_and_unreadable_property_are_reported() -> None:
    module = fixture_module()
    vars(module)["Broken"] = type("Broken", (), {"__module__": "fixture", "defs": object()})
    vars(module)["Instrument"].untyped = assignment("UNTYPED", data_type=None)
    document = validate_document(extract(module, "v", ("Instrument", "Broken", "Absent")))
    reasons = {row["path"]: row["reason"] for row in document["report"]}
    assert "malformed entity" in reasons["fixture.Broken"]
    assert "malformed entity" in reasons["fixture.Absent"]
    assert "no source data type" in reasons["fixture.Instrument.untyped"]
    assert "untyped" not in {a["name"] for a in classes_of(document)["Instrument"]["attributes"]}


def test_disagreeing_source_effective_dictionary_is_reported() -> None:
    module = fixture_module()

    class Divergent:
        def get_property_metadata(self) -> dict[str, Any]:
            return {"invented": assignment("INVENTED")}

    vars(module)["Instrument"].get_property_metadata = Divergent.get_property_metadata
    document = validate_document(extract(module, "v"))
    entry = next(row for row in document["report"] if row["path"] == "fixture.Instrument")
    assert "source effective properties disagree with Python lookup" in entry["reason"]
    assert classes_of(document)["Instrument"]["effective_attributes"] == []


def test_repeated_extraction_is_identical_and_alias_roots_keep_one_id() -> None:
    assert extract(fixture_module(), "v") == extract(fixture_module(), "v")
    module = fixture_module()
    vars(module)["Alias"] = module.Camera
    document = validate_document(extract(module, "v", ("Alias", "Camera")))
    # One id per definition, and the base and referenced vocabulary come with it.
    assert {row["id"] for row in document["classes"]} == {
        "fixture.Camera", "fixture.Instrument", "fixture.Status"}


def test_dependency_versions_are_recorded_as_source_evidence() -> None:
    document = validate_document(extract(
        fixture_module(), "0.13.1", dependencies={"pydantic": "2.13.5", "pint": "0.25.3"}))
    assert document["source"]["dependencies"] == {"pint": "0.25.3", "pydantic": "2.13.5"}
