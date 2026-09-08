"""JSON-boundary adapter tests: only small inline schemas, no source imports."""

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from linkml.generators.pydanticgen import PydanticGenerator
from linkml_runtime.dumpers import yaml_dumper
from linkml_runtime.linkml_model.meta import ArrayExpression, DimensionExpression, UnitOfMeasure
from linkml_runtime.utils.schemaview import SchemaView

from schematerial._linkml import annotations_of, attributes_of, class_of
from schematerial.cache import MaterialisationCache, content_hash
from schematerial.extraction.contract import ContractError, validate_document
from schematerial.extraction.runner import ExtractorEnvironment, run_extractor
from schematerial.facets import FacetError, read_facets, validate_schema_facets
from schematerial.identity import element_id
from schematerial.parsers.nomad import NomadParser
from schematerial.parsers.nomad_json import TYPE_RANGES, UNIT_CODES, NomadAdapter, NomadImportError

FAKE = Path(__file__).parents[2] / "src/schematerial/extractors/fake.py"


def quantity(name: str = "value", dtype: str = "builtins.float", **kwargs: Any) -> dict[str, Any]:
    return {"name": name, "kind": "quantity", "range": {"kind": "datatype", "name": dtype},
            "shape": [], **kwargs}


def ref(owner: str, name: str = "value", kind: str = "quantity") -> dict[str, str]:
    return {"name": name, "kind": kind, "declaring_class_id": owner}


def cls(name: str, attrs: list[dict[str, Any]], bases: list[str] | None = None,
        effective: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {"id": name, "name": name.rsplit(".", 1)[-1], "attributes": attrs,
            "bases": bases or [], "effective_attributes": effective if effective is not None else
            [ref(name, a["name"], a["kind"]) for a in attrs]}


def document(*classes: dict[str, Any]) -> dict[str, Any]:
    return {"contract_version": "1.1", "source": {"name": "nomad-simulations", "version": "v1",
            "module": "fixture", "dependencies": {"nomad-lab": "1.4.0"}},
            "classes": list(classes), "enums": [], "report": []}


def boundary(doc: dict[str, Any]) -> dict[str, Any]:
    return run_extractor(ExtractorEnvironment("inline", Path(sys.executable)), FAKE,
                         input_text=json.dumps(doc))


def field(result: Any, owner: str = "Sample", name: str = "value") -> Any:
    return attributes_of(class_of(result.loaded.schema, owner))[name]


@pytest.mark.parametrize("kind,name,expected", [(k, n, v) for (k, n), v in TYPE_RANGES.items()])
def test_every_type_table_row(kind: str, name: str, expected: str | None) -> None:
    raw = json.dumps({"type_kind": kind, "type_data": name})
    result = NomadAdapter().convert(boundary(document(cls("Sample", [quantity(dtype=raw)]))))
    assert field(result).range == expected
    assert annotations_of(field(result))["source_type"].value == raw
    unmapped = any("unmapped source type" in row["reason"] for row in result.report)
    assert unmapped == (expected is None)


@pytest.mark.parametrize("raw,code", list(UNIT_CODES.items()))
def test_unit_table(raw: str, code: str) -> None:
    result = NomadAdapter().convert(boundary(document(cls("Sample", [quantity(unit=raw)]))))
    unit = field(result).unit
    assert isinstance(unit, UnitOfMeasure) and unit.ucum_code == code
    assert annotations_of(field(result))["source_unit"].value == raw


def test_numeric_symbolic_shapes_and_scalar() -> None:
    result = NomadAdapter().convert(boundary(document(cls("Sample", [
        quantity(), quantity("matrix", shape=[2, 3]), quantity("positions", shape=["n_atoms", 3]),
    ]))))
    assert field(result).array is None
    matrix = field(result, name="matrix").array
    assert isinstance(matrix, ArrayExpression) and matrix.dimensions
    assert all(isinstance(d, DimensionExpression) for d in matrix.dimensions)
    assert [(getattr(d, "alias"), getattr(d, "exact_cardinality")) for d in matrix.dimensions] == [
        ("axis_0", 2), ("axis_1", 3)]
    positions = field(result, name="positions")
    assert positions.array.exact_number_dimensions == 2
    assert not positions.array.dimensions
    assert json.loads(str(annotations_of(positions)["source_shape"].value)) == ["n_atoms", 3]
    assert "smat:NomadShape" in positions.instantiates
    assert any(row["path"] == "Sample.positions" and row["status"] == "partial"
               for row in result.report)


def test_inheritance_nested_subsections_and_initialized_local_override() -> None:
    child = {"name": "child", "kind": "subsection", "range": {"kind": "class", "name": "Left"},
             "repeats": True}
    result = NomadAdapter().convert(boundary(document(
        cls("Left", [quantity(unit="meter", shape=[2])]),
        cls("Right", [quantity(dtype="builtins.int", unit="second", shape=[3]), child]),
        cls("Combined", [], ["Left", "Right"], [ref("Right"), ref("Right", "child", "subsection")]),
        cls("Override", [quantity(unit="second", shape=[3]), {**child, "repeats": False}],
            ["Left", "Right"]),
    )))
    combined = class_of(result.schema, "Combined")
    assert combined.is_a == "Left" and list(combined.mixins or []) == ["Right"]
    assert not attributes_of(combined)
    assert field(result, "Combined").range == "integer"
    assert field(result, "Combined", "child").multivalued is True
    assert field(result, "Override", "child").multivalued is False
    assert "nomadsim:Combined.child.value" in result.loaded.snapshots
    assert result.loaded.snapshots["nomadsim:Combined.child.value"].parent == "Combined.child"
    assert result.loaded.snapshots["nomadsim:Combined.value"].source_version == "v1"
    assert json.loads(str(annotations_of(combined)["source_bases"].value)) == ["Left", "Right"]


@pytest.mark.parametrize("pattern", ["three", "diamond", "missing", "extra", "shape", "repeats"])
def test_inheritance_mismatch_rejects_without_cache_publication(pattern: str) -> None:
    left, right = cls("Left", [quantity()]), cls("Right", [quantity(dtype="builtins.int")])
    classes = [left, right]
    bases, expected = ["Left", "Right"], [ref("Right")]
    if pattern == "three":
        classes.append(cls("Third", [quantity(dtype="builtins.str")]))
        bases.append("Third")
        expected = [ref("Third")]
    elif pattern == "diamond":
        classes[1] = cls("Right", [], ["Left"], [ref("Left")])
        classes.append(cls("Branch", [quantity(dtype="builtins.int")], ["Left"]))
        bases, expected = ["Branch", "Right"], [ref("Left")]
    elif pattern == "missing":
        bases = []
    elif pattern == "extra":
        expected = []
    elif pattern == "shape":
        right["attributes"] = [quantity(shape=[3])]
        expected = [ref("Left")]
    else:
        for row, repeats in ((left, False), (right, True)):
            row["attributes"] = [{"name": "value", "kind": "subsection", "repeats": repeats,
                                  "range": {"kind": "class", "name": "Left"}}]
            row["effective_attributes"] = [ref(row["id"], kind="subsection")]
        expected = [ref("Left", kind="subsection")]
    classes.append(cls("Combined", [], bases, expected))
    cache = MaterialisationCache()
    captured = []
    original = cache.prepare

    def prepare(source: str, **kwargs: Any) -> str:
        captured.append(content_hash(source))
        return original(source, **kwargs)

    with patch.object(cache, "prepare", side_effect=prepare):
        with pytest.raises(NomadImportError, match="Combined.value.*NOMAD=.*LinkML=") as error:
            NomadAdapter(cache).convert(boundary(document(*classes)))
    assert any(r["path"] == "Combined.value" for r in error.value.report)
    with pytest.raises(KeyError):
        cache.get(captured[0])


def test_unmapped_type_unit_and_type_constraints_are_reported_and_retained() -> None:
    result = NomadAdapter().convert(boundary(document(cls("Sample", [
        quantity(dtype="unfamiliar.type", unit="unfamiliar unit"),
        quantity("bounded", dtype=json.dumps({"type_kind": "python", "type_data": "float",
                                               "type_bound": "[0,1]"})),
    ]))))
    assert field(result).range is None and field(result).unit is None
    assert len(result.report) == 3
    assert field(result, name="bounded").range == "float"


def test_explicit_facets_survive_and_absent_semantics_stay_absent() -> None:
    result = NomadAdapter().convert(boundary(document(cls("Sample", [
        quantity(), quantity("grounded", annotations={"semantic_type": "unfamiliar:Energy"}),
    ]))))
    assert read_facets(field(result)).semantic_type is None
    assert read_facets(field(result, name="grounded")).semantic_type == "unfamiliar:Energy"


def test_enum_references_and_same_leaf_class_names_remain_distinct() -> None:
    doc = document(cls("a.Sample", [quantity()]), cls("b.Sample", [quantity(dtype="builtins.str")]),
                   cls("Holder", [quantity(range={"kind": "enum", "name": "State"})]))
    doc["enums"] = [{"id": "State", "values": ["solid", "liquid"]}]
    result = NomadAdapter().convert(boundary(doc))
    assert field(result, "Holder").range == "State"
    for name in ("a.Sample", "b.Sample"):
        assert element_id("nomadsim", (name, "value")) in result.loaded.snapshots


def test_warm_cache_does_no_materialisation_and_ids_survive_input_reordering() -> None:
    adapter = NomadAdapter()
    doc = boundary(document(cls("Sample", [quantity()])))
    original = SchemaView.materialize_derived_schema
    with patch.object(SchemaView, "materialize_derived_schema", autospec=True,
                      side_effect=original) as materialize:
        first = adapter.convert(doc)
        second = adapter.convert(doc)
        assert materialize.call_count == 1
    assert first.cache_key == second.cache_key
    assert first.loaded.snapshots == second.loaded.snapshots


def test_unit_survives_pinned_pydantic_generator(tmp_path: Path) -> None:
    result = NomadAdapter().convert(boundary(document(cls("Sample", [quantity(unit="joule")]))))
    path = tmp_path / "schema.yaml"
    path.write_text(yaml_dumper.dumps(result.schema))
    generated = PydanticGenerator(str(path)).serialize()
    compile(generated, str(path), "exec")
    assert "ucum_code" in generated and "J" in generated
    assert field(result).unit.ucum_code == "J"


def test_json_parser_path_and_evidence_requirements(tmp_path: Path) -> None:
    path = tmp_path / "nomad.json"
    doc = boundary(document(cls("Sample", [quantity()])))
    path.write_text(json.dumps(doc))
    assert "Sample" in (NomadParser().parse(path).classes or {})
    doc["source"]["dependencies"] = {}
    with pytest.raises(NomadImportError, match="versions"):
        NomadAdapter().convert(doc)
    doc["contract_version"] = "1.0"
    del doc["source"]["dependencies"]
    for row in doc["classes"]:
        del row["effective_attributes"]
    with pytest.raises(NomadImportError, match="re-extract"):
        NomadAdapter().convert(doc)


@pytest.mark.parametrize("change", ["missing", "owner", "kind", "duplicate", "dependencies"])
def test_invalid_evidence_contract_paths(change: str) -> None:
    doc = document(cls("Sample", [quantity()]))
    row = doc["classes"][0]
    if change == "missing":
        del row["effective_attributes"]
    elif change == "dependencies":
        del doc["source"]["dependencies"]
    elif change == "duplicate":
        row["effective_attributes"] *= 2
    else:
        row["effective_attributes"][0]["declaring_class_id" if change == "owner" else "kind"] = (
            "Absent" if change == "owner" else "subsection")
    with pytest.raises(ContractError, match=r"\$\.(classes|source)"):
        validate_document(doc)


def test_incomplete_extraction_and_cycles_are_rejected() -> None:
    doc = boundary(document(cls("Sample", [quantity()])))
    doc["report"] = [{"path": "Sample", "status": "skipped", "reason": "missing evidence"}]
    with pytest.raises(NomadImportError, match="Incomplete NOMAD extraction"):
        NomadAdapter().convert(doc)
    doc["report"] = []
    doc["classes"][0]["bases"] = ["Sample"]
    with pytest.raises(NomadImportError, match="inheritance cycle"):
        NomadAdapter().convert(doc)


def test_governed_shape_validation_names_bad_element() -> None:
    result = NomadAdapter().convert(boundary(document(cls("Sample", [quantity(shape=[2])]))))
    annotations_of(field(result))["source_shape"].value = "[true]"
    with pytest.raises(FacetError, match="Sample.value.*source_shape"):
        validate_schema_facets(result.loaded.schema)


def test_disjoint_bases_and_source_order_have_stable_cached_output() -> None:
    doc = document(cls("Left", [quantity("left")]), cls("Right", [quantity("right")]),
                   cls("Both", [], ["Left", "Right"], [ref("Left", "left"), ref("Right", "right")]))
    adapter = NomadAdapter()
    first = adapter.convert(boundary(doc))
    doc["classes"].reverse()
    for row in doc["classes"]:
        row["effective_attributes"].reverse()
    second = adapter.convert(boundary(doc))
    assert first.cache_key == second.cache_key == content_hash(first.to_yaml())
    assert first.loaded.snapshots == second.loaded.snapshots
    assert set(attributes_of(class_of(second.loaded.schema, "Both"))) == {"left", "right"}
    assert "# linkml-runtime==1.11.1\n" in second.to_yaml()


def test_semantic_and_description_conflicts_are_not_hidden_by_equal_ranges() -> None:
    doc = document(
        cls("Left", [quantity(description="left", annotations={"semantic_type": "term:Left"})]),
        cls("Right", [quantity(description="right", annotations={"semantic_type": "term:Right"})]),
        cls("Both", [], ["Left", "Right"], [ref("Left")]),
    )
    with pytest.raises(NomadImportError, match="Both.value.*term:Left.*term:Right"):
        NomadAdapter().convert(boundary(doc))


def test_generic_warm_cache_cannot_bypass_source_validation() -> None:
    cache = MaterialisationCache()
    original = NomadAdapter(cache).convert(boundary(document(cls("Sample", [quantity()]))))
    # A caller using the generic cache must still run a supplied validator on a hit.
    def reject(schema: Any) -> None:
        raise ValueError("source verification failed")

    with pytest.raises(ValueError, match="source verification failed"):
        cache.prepare(original.to_yaml(), validate=reject)


def test_loading_entry_point_imports_in_a_fresh_process() -> None:
    import subprocess

    subprocess.run([sys.executable, "-c", "from schematerial.loading import load_schema"],
                   check=True, capture_output=True, text=True)
