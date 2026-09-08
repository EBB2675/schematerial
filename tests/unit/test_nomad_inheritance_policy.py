"""Pinned-runtime evidence, not an adapter or a NOMAD resolution implementation.

NOMAD expectations were captured by an isolated probe against the pinned runtime.
All schema definitions here are inline; no NOMAD import or environment is needed.
"""

import runpy
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from linkml_runtime.linkml_model.meta import ArrayExpression, DimensionExpression, UnitOfMeasure
from linkml_runtime.utils.schemaview import SchemaView

from schematerial._linkml import attributes_of, class_of
from schematerial.extraction.contract import validate_document

SOURCE = """id: https://example.org/inheritance
name: inheritance
imports: [linkml:types]
classes:
  TargetA: {}
  TargetB: {}
  Left:
    attributes:
      value:
        range: float
        unit: {ucum_code: m}
        array:
          exact_number_dimensions: 1
          dimensions: [{alias: axis_0, exact_cardinality: 2}]
      child: {range: TargetA, multivalued: false}
      left_only: {range: string}
  Right:
    attributes:
      value:
        range: integer
        unit: {ucum_code: s}
        array:
          exact_number_dimensions: 1
          dimensions: [{alias: axis_0, exact_cardinality: 3}]
      child: {range: TargetB, multivalued: true}
      right_only: {range: string}
  Combined:
    is_a: Left
    mixins: [Right]
"""


def test_two_base_conflict_matches_nomad_metainfo_not_python_lookup() -> None:
    class Left:
        value = "float"

    class Right:
        value = "integer"

    class Combined(Left, Right):
        pass

    assert Combined.value == "float"
    view = SchemaView(SOURCE)
    value = view.induced_slot("value", "Combined")
    # Isolated NOMAD probe: Right wins in all_quantities / all_sub_sections.
    assert value.range == "integer"
    assert isinstance(value.unit, UnitOfMeasure) and value.unit.ucum_code == "s"
    assert isinstance(value.array, ArrayExpression)
    assert value.array.exact_number_dimensions == 1
    assert value.array.dimensions
    dimension = value.array.dimensions[0]
    assert isinstance(dimension, DimensionExpression)
    assert dimension.exact_cardinality == 3
    child = view.induced_slot("child", "Combined")
    assert (child.range, child.multivalued) == ("TargetB", True)


def test_nonconflicting_members_of_both_bases_survive_materialisation() -> None:
    view = SchemaView(SOURCE)
    attrs = attributes_of(class_of(view.materialize_derived_schema(), "Combined"))
    assert set(attrs) == {"value", "child", "left_only", "right_only"}
    assert attrs["left_only"].range == attrs["right_only"].range == "string"
    assert attrs["value"].range == "integer"
    assert attrs["child"].multivalued is True


def test_local_completed_override_wins_including_false_repeats() -> None:
    # NOMAD initializes omitted unit and shape from Right before extraction.
    view = SchemaView(SOURCE + """  Override:
    is_a: Left
    mixins: [Right]
    attributes:
      value:
        range: float
        unit: {ucum_code: s}
        array:
          exact_number_dimensions: 1
          dimensions: [{alias: axis_0, exact_cardinality: 3}]
      child: {range: TargetA, multivalued: false}
""")
    value = view.induced_slot("value", "Override")
    assert value.range == "float"
    assert isinstance(value.unit, UnitOfMeasure) and value.unit.ucum_code == "s"
    assert isinstance(value.array, ArrayExpression) and value.array.dimensions
    dimension = value.array.dimensions[0]
    assert isinstance(dimension, DimensionExpression)
    assert dimension.exact_cardinality == 3
    child = view.induced_slot("child", "Override")
    assert (child.range, child.multivalued) == ("TargetA", False)


def test_diamond_repeated_base_is_not_nomad_equivalent() -> None:
    view = SchemaView(SOURCE + """  DiamondLeft:
    is_a: Left
    attributes:
      value: {range: integer, unit: {ucum_code: s}}
  DiamondRight:
    is_a: Left
  Diamond:
    is_a: DiamondLeft
    mixins: [DiamondRight]
""")
    # Captured NOMAD traversal: Left, DiamondLeft, Left, DiamondRight, Diamond.
    # NOMAD selects Left/float; SchemaView selects DiamondLeft/integer.
    assert view.induced_slot("value", "Diamond").range == "integer"


def test_three_conflicting_bases_are_not_generally_nomad_equivalent() -> None:
    view = SchemaView(SOURCE + """  Third:
    attributes:
      value: {range: string}
  ThreeBases:
    is_a: Left
    mixins: [Right, Third]
""")
    # Captured NOMAD effective value is Third/string, Python is Left/float.
    # LinkML takes the first mixin Right: this policy must not claim general fidelity.
    assert view.induced_slot("value", "ThreeBases").range == "integer"


@pytest.mark.parametrize("local_override", [False, True])
def test_extraction_keeps_bases_and_initialized_local_metadata(local_override: bool) -> None:
    module = ModuleType("fixture")
    def quantity(dtype: type, unit: str, shape: list[int]) -> SimpleNamespace:
        return SimpleNamespace(name="value", type=dtype, unit=unit, shape=shape,
                               description=None)

    def definition(quantities: list[SimpleNamespace]) -> SimpleNamespace:
        return SimpleNamespace(quantities=quantities, sub_sections=[], description=None)

    left = type("Left", (), {"__module__": "fixture", "m_def": definition([
        quantity(float, "meter", [2])])})
    right = type("Right", (), {"__module__": "fixture", "m_def": definition([
        quantity(int, "second", [3])])})
    # Input is post-initialization metainfo, as observed in the isolated override probe.
    child = type("Child", (left, right), {"__module__": "fixture", "m_def": definition(
        [quantity(float, "second", [3])] if local_override else [])})
    for cls in (left, right, child):
        definition_ = vars(cls)["m_def"]
        definition_.section_cls = cls
        for prop in definition_.quantities:
            prop.m_parent = definition_
        definition_.all_quantities = {q.name: q for q in definition_.quantities}
        definition_.all_sub_sections = {}
    if not local_override:
        vars(child)["m_def"].all_quantities = vars(right)["m_def"].all_quantities
    vars(module).update(Left=left, Right=right, Child=child)
    extract = runpy.run_path(str(Path(__file__).parents[2]
                                / "src/schematerial/extractors/nomad.py"))["extract"]
    document = validate_document(extract(module, "fixture"))
    row = next(c for c in document["classes"] if c["name"] == "Child")
    assert row["bases"] == ["fixture.Left", "fixture.Right"]
    if local_override:
        assert row["attributes"][0]["unit"] == "second"
        assert row["attributes"][0]["shape"] == [3]
    else:
        assert row["attributes"] == []
    assert row["effective_attributes"] == [{
        "name": "value", "kind": "quantity",
        "declaring_class_id": "fixture.Child" if local_override else "fixture.Right",
    }]
    assert document["report"] == []


def test_disjoint_multiple_inheritance() -> None:
    view = SchemaView("""id: https://example.org/disjoint
name: disjoint
classes:
  Left:
    attributes:
      left_only: {range: string}
  Right:
    attributes:
      right_only: {range: integer}
  Both:
    is_a: Left
    mixins: [Right]
""")
    assert {s.name: s.range for s in view.class_induced_slots("Both")} == {
        "left_only": "string", "right_only": "integer"}
