"""Card 3: the LinkML schema is the source of truth, models/ is generated."""

import subprocess
import sys
from pathlib import Path

import pytest
from linkml_runtime.dumpers import yaml_dumper
from linkml_runtime.linkml_model.meta import (
    ClassDefinition,
    Prefix,
    SchemaDefinition,
    SlotDefinition,
)
from linkml_runtime.utils.schemaview import SchemaView

from schematerial._linkml import add_attribute, add_class, attributes_of, instantiates_of
from schematerial.facets import read_facets, write_facets
from schematerial.models import CoordinateFrame, MaterialsFacets
from schematerial.schema import generate as generator

REPO = Path(__file__).parent.parent.parent
SRC = REPO / "src" / "schematerial"


# --- "generating twice produces byte-identical output" -----------------------


def test_generating_twice_produces_byte_identical_output(tmp_path: Path) -> None:
    first = generator.generate(target=tmp_path / "a.py")
    second = generator.generate(target=tmp_path / "b.py")
    assert first == second
    assert (tmp_path / "a.py").read_bytes() == (tmp_path / "b.py").read_bytes()


def test_the_committed_generated_file_is_what_regenerating_produces(tmp_path: Path) -> None:
    """`models/` is generated output. If this fails, someone edited it by hand."""
    regenerated = generator.generate(target=tmp_path / "core.py")
    assert generator.GENERATED.read_text(encoding="utf-8") == regenerated


def test_generation_with_a_custom_target_does_not_touch_the_package_init(
    tmp_path: Path,
) -> None:
    before = generator.PACKAGE_INIT.read_bytes()
    generator.generate(target=tmp_path / "core.py")
    assert generator.PACKAGE_INIT.read_bytes() == before
    assert (tmp_path / "__init__.py").exists()


def test_the_check_mode_passes_without_rewriting_generated_files() -> None:
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in (generator.GENERATED, generator.PACKAGE_INIT)
    }
    result = subprocess.run(
        [sys.executable, "-m", "schematerial.schema.generate", "--check"],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert result.returncode == 0, result.stderr
    after = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in (generator.GENERATED, generator.PACKAGE_INIT)
    }
    assert after == before


def test_stale_detection_covers_the_whole_generated_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generated = tmp_path / "core.py"
    package_init = tmp_path / "__init__.py"
    generated.write_text(generator.render(), encoding="utf-8")
    package_init.write_text("stale\n", encoding="utf-8")
    monkeypatch.setattr(generator, "GENERATED", generated)
    monkeypatch.setattr(generator, "PACKAGE_INIT", package_init)

    assert generator.stale_generated_files() == [package_init]
    assert package_init.read_text(encoding="utf-8") == "stale\n"


def test_the_generated_file_records_the_pins(tmp_path: Path) -> None:
    """Decision 9: pins are recorded in the header of every generated schema."""
    content = generator.generate(target=tmp_path / "core.py")
    header = content.split("\n\n", 1)[0]
    assert "DO NOT EDIT" in header
    for distribution in generator.PINNED_DISTRIBUTIONS:
        assert f"#   {distribution}==" in header


# --- "nothing in the codebase hand-writes a model class" ---------------------


def test_nothing_outside_models_defines_a_model_class() -> None:
    """The generated view is the only place a core model class is written.

    Records that are not part of the core -- ontology proposals, snapshots --
    are app records and are exempt by name; everything else in `src/` that
    subclasses BaseModel would be a hand-written mirror of the schema.
    """
    exempt = {
        SRC / "semantics" / "ontology.py",  # grounding proposals, decision record 002
        SRC / "identity.py",  # ElementSnapshot, decision 2
    }
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        if path.is_relative_to(SRC / "models") or path in exempt:
            continue
        if "(BaseModel)" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == [], f"hand-written model classes: {offenders}"


def test_the_generated_package_is_marked_as_generated() -> None:
    for path in (generator.GENERATED, generator.PACKAGE_INIT):
        assert "DO NOT EDIT" in path.read_text(encoding="utf-8").splitlines()[0]


# --- "a fixture using all five facets round-trips through SchemaView" --------


def _fixture_with_all_five_facets() -> tuple[SchemaDefinition, MaterialsFacets]:
    facets = MaterialsFacets(
        semantic_type="quantitykind:PositionVector",
        coordinate_frame=CoordinateFrame.fractional,
        per_atom=True,
        spin_channel=-1,
        unit_normalized="m",
    )
    attribute = SlotDefinition(name="positions", range="float")
    write_facets(attribute, facets)

    root = ClassDefinition(name="System", tree_root=True)
    add_attribute(root, attribute)

    schema = SchemaDefinition(
        id="https://example.org/fixture",
        name="fixture",
        default_range="string",
        prefixes={
            "linkml": Prefix("linkml", "https://w3id.org/linkml/"),
            "smat": Prefix("smat", "https://w3id.org/schematerial/core/"),
        },
        imports=["linkml:types"],
    )
    add_class(schema, root)
    return schema, facets


def test_all_five_facets_round_trip_through_schemaview(tmp_path: Path) -> None:
    schema, written = _fixture_with_all_five_facets()

    path = tmp_path / "fixture.yaml"
    path.write_text(yaml_dumper.dumps(schema), encoding="utf-8")

    view = SchemaView(str(path))
    system = view.get_class("System")
    assert system is not None
    reloaded = attributes_of(system)["positions"]

    assert read_facets(reloaded) == written
    assert "smat:MaterialsFacets" in instantiates_of(reloaded)


def test_an_element_with_no_facets_does_not_claim_to_have_any() -> None:
    attribute = SlotDefinition(name="plain", range="float")
    write_facets(attribute, MaterialsFacets())
    assert instantiates_of(attribute) == []
    assert read_facets(attribute) == MaterialsFacets()


# --- the core schema itself --------------------------------------------------


def test_the_core_schema_loads_through_schemaview() -> None:
    view = SchemaView(str(generator.CORE_SCHEMA))
    assert list(view.all_classes()) == ["MaterialsFacets"]
    assert list(view.all_enums()) == ["CoordinateFrame"]


@pytest.mark.parametrize(
    "facet",
    ["semantic_type", "coordinate_frame", "per_atom", "spin_channel", "unit_normalized"],
)
def test_every_facet_is_optional_in_the_schema(facet: str) -> None:
    view = SchemaView(str(generator.CORE_SCHEMA))
    facets = view.get_class("MaterialsFacets")
    assert facets is not None
    assert attributes_of(facets)[facet].required is False
