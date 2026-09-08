"""NOMAD reflection edge cases using inline objects, never source packages."""

import runpy
from pathlib import Path
from types import ModuleType, SimpleNamespace

from schematerial.extraction.contract import validate_document

EXTRACTOR = Path(__file__).parents[2] / "src/schematerial/extractors/nomad.py"
extract = runpy.run_path(str(EXTRACTOR))["extract"]


class FixtureSection(SimpleNamespace):
    # This fixture's base is empty: these are source-provided effective dictionaries.
    @property
    def all_quantities(self) -> dict[str, SimpleNamespace]:
        for item in self.quantities:
            item.m_parent = self
        return {item.name: item for item in self.quantities}

    @property
    def all_sub_sections(self) -> dict[str, SimpleNamespace]:
        for item in self.sub_sections:
            item.m_parent = self
        return {item.name: item for item in self.sub_sections}


def fixture_module() -> ModuleType:
    module = ModuleType("fixture")
    base = type("Base", (), {"__module__": "fixture", "m_def": FixtureSection(
        quantities=[], sub_sections=[], description=None,
    )})
    child = type("Child", (base,), {"__module__": "fixture", "m_def": FixtureSection(
        quantities=[SimpleNamespace(name="positions", type=float, unit="m",
                                   shape=["n_atoms", 3], description=None)],
        sub_sections=[SimpleNamespace(name=name, sub_section=SimpleNamespace(section_cls=base),
                                      repeats=True, description=None)
                      for name in ("initial", "final")], description=None,
    )})
    vars(base)["m_def"].section_cls = base
    vars(child)["m_def"].section_cls = child
    vars(module)["Base"] = base
    vars(module)["Child"] = child
    return module


def test_local_quantities_direct_bases_and_named_subsections() -> None:
    document = validate_document(extract(fixture_module(), "fixture-version"))
    classes = {cls["name"]: cls for cls in document["classes"]}
    child = classes["Child"]
    assert child["bases"] == ["fixture.Base"]
    attributes = {attr["name"]: attr for attr in child["attributes"]}
    assert attributes["positions"]["shape"] == ["n_atoms", 3]
    assert attributes["positions"]["range"] == {"kind": "datatype", "name": "builtins.float"}
    assert attributes["positions"]["unit"] == "m"
    assert attributes["initial"]["range"] == attributes["final"]["range"]
    assert attributes["final"]["repeats"] is True
    assert document["report"] == []


def test_malformed_section_and_unresolved_root_are_reported() -> None:
    module = fixture_module()
    vars(module)["Broken"] = type("Broken", (), {"__module__": "fixture", "m_def": object()})
    document = validate_document(extract(module, "v", ("Child", "Broken", "Missing")))
    assert {row["path"] for row in document["report"]} == {"fixture.Broken", "fixture.Missing"}
    assert len(document["classes"]) == 2


def test_bad_shape_is_reported_without_losing_other_attributes() -> None:
    module = fixture_module()
    module.Child.m_def.quantities[0].shape = [True]
    document = validate_document(extract(module, "v"))
    assert any(row["path"] == "fixture.Child.positions" and "shape" in row["reason"]
               for row in document["report"])
    child = next(cls for cls in document["classes"] if cls["name"] == "Child")
    assert {attr["name"] for attr in child["attributes"]} == {"initial", "final"}


def test_unreadable_target_removes_reference_with_report() -> None:
    module = fixture_module()
    module.Base.m_def = object()
    document = validate_document(extract(module, "v", ("Child",)))
    assert len(document["classes"]) == 1
    assert document["classes"][0]["bases"] == []
    assert len(document["classes"][0]["attributes"]) == 1
    assert any(row["path"] == "fixture.Child.initial" for row in document["report"])


def test_repeated_extraction_is_identical() -> None:
    assert extract(fixture_module(), "v") == extract(fixture_module(), "v")


def test_serialized_nomad_enum_is_an_enum_range() -> None:
    module = fixture_module()
    module.Child.m_def.quantities[0].type = SimpleNamespace(
        serialize_self=lambda: {"type_kind": "enum", "type_data": ["solid", "liquid"]}
    )
    document = validate_document(extract(module, "v"))
    assert document["enums"] == [{"id": "fixture.Child.positions", "values": ["solid", "liquid"]}]
    child = next(cls for cls in document["classes"] if cls["name"] == "Child")
    assert child["attributes"][0]["range"]["kind"] == "enum"


def test_reference_range_preserves_target_without_serializing_it() -> None:
    module = fixture_module()
    module.Child.m_def.quantities[0].type = SimpleNamespace(
        target_section_def=SimpleNamespace(section_cls=module.Base),
        serialize_self=lambda required_section: required_section,
    )
    document = validate_document(extract(module, "v"))
    child = next(cls for cls in document["classes"] if cls["name"] == "Child")
    assert child["attributes"][0]["range"] == {"kind": "class", "name": "fixture.Base"}


def test_recursive_subsections_terminate_and_keep_reference() -> None:
    module = fixture_module()
    module.Child.m_def.sub_sections.append(SimpleNamespace(
        name="recursive", sub_section=module.Child, repeats=False, description=None,
    ))
    document = validate_document(extract(module, "v"))
    assert len(document["classes"]) == 2
    child = next(cls for cls in document["classes"] if cls["name"] == "Child")
    assert next(a for a in child["attributes"] if a["name"] == "recursive")["range"] == {
        "kind": "class", "name": "fixture.Child",
    }


def test_duplicate_attributes_are_reported_instead_of_invalid_output() -> None:
    module = fixture_module()
    module.Child.m_def.quantities.append(module.Child.m_def.quantities[0])
    document = validate_document(extract(module, "v"))
    assert any("duplicate" in row["reason"] for row in document["report"])


def test_alias_roots_keep_canonical_definition_ids() -> None:
    module = fixture_module()
    vars(module)["Alias"] = module.Child
    document = validate_document(extract(module, "v", ("Alias", "Child")))
    assert {cls["id"] for cls in document["classes"]} == {"fixture.Base", "fixture.Child"}
    assert document["report"] == []


def test_dependency_versions_and_effective_references_are_source_evidence() -> None:
    document = validate_document(extract(
        fixture_module(), "v", dependencies={"nomad-lab": "1.4.0"}))
    assert document["contract_version"] == "1.1"
    assert document["source"]["dependencies"] == {"nomad-lab": "1.4.0"}
    child = next(c for c in document["classes"] if c["name"] == "Child")
    assert child["effective_attributes"] == [
        {"name": "final", "kind": "subsection", "declaring_class_id": "fixture.Child"},
        {"name": "initial", "kind": "subsection", "declaring_class_id": "fixture.Child"},
        {"name": "positions", "kind": "quantity", "declaring_class_id": "fixture.Child"},
    ]


def test_extension_or_missing_effective_metadata_is_reported() -> None:
    module = fixture_module()
    module.Child.m_def.extending_sections = [object()]
    document = validate_document(extract(module, "v"))
    assert any("extending sections are unsupported" in r["reason"] for r in document["report"])
    child = next(c for c in document["classes"] if c["name"] == "Child")
    assert child["effective_attributes"] == []
    module.Child.m_def = SimpleNamespace(quantities=[], sub_sections=[], description=None)
    document = validate_document(extract(module, "v"))
    assert any("incomplete effective definitions" in r["reason"] for r in document["report"])
