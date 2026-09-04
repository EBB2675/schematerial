"""Reading, writing and validating the decision 4 facets."""

import pytest
from linkml_runtime.linkml_model.meta import ClassDefinition, SchemaDefinition, SlotDefinition

from schematerial._linkml import (
    add_attribute,
    add_class,
    annotations_of,
    class_of,
    instantiates_of,
    set_annotation,
)
from schematerial.facets import (
    MATERIALS_FACETS_CURIE,
    FacetError,
    facet_problems,
    read_facets,
    validate_schema_facets,
    write_facets,
)
from schematerial.models import CoordinateFrame, MaterialsFacets


def _annotated(**tags: str) -> SlotDefinition:
    attribute = SlotDefinition(name="positions", range="float")
    for tag, value in tags.items():
        set_annotation(attribute, tag, value)
    return attribute


def _schema(attribute: SlotDefinition) -> SchemaDefinition:
    root = ClassDefinition(name="System", tree_root=True)
    add_attribute(root, attribute)
    schema = SchemaDefinition(id="https://example.org/s", name="s")
    add_class(schema, root)
    return schema


# --- write and read ----------------------------------------------------------


def test_writing_a_facet_points_instantiates_at_the_class() -> None:
    attribute = SlotDefinition(name="e")
    write_facets(attribute, MaterialsFacets(per_atom=True))
    assert MATERIALS_FACETS_CURIE in instantiates_of(attribute)


def test_a_facet_with_no_value_writes_nothing() -> None:
    attribute = SlotDefinition(name="e")
    write_facets(attribute, MaterialsFacets(semantic_type="quantitykind:Energy"))
    assert set(annotations_of(attribute)) == {"semantic_type"}


def test_writing_twice_does_not_repeat_instantiates() -> None:
    attribute = SlotDefinition(name="e")
    write_facets(attribute, MaterialsFacets(per_atom=True))
    write_facets(attribute, MaterialsFacets(spin_channel=1))
    assert instantiates_of(attribute) == [MATERIALS_FACETS_CURIE]


def test_reading_an_element_with_no_facets_gives_all_absent() -> None:
    assert read_facets(SlotDefinition(name="e")) == MaterialsFacets()


def test_values_coerce_back_out_of_annotation_strings() -> None:
    attribute = _annotated(per_atom="true", spin_channel="-1", coordinate_frame="reciprocal")
    facets = read_facets(attribute)
    assert facets.per_atom is True
    assert facets.spin_channel == -1
    assert facets.coordinate_frame == CoordinateFrame.reciprocal


# --- the validator names the element and the bad value -----------------------


@pytest.mark.parametrize(
    ("tag", "value", "expected"),
    [
        ("coordinate_frame", "spherical", "cartesian, fractional, reciprocal"),
        ("per_atom", "maybe", "a boolean"),
        ("spin_channel", "up", "an integer"),
        ("semantic_type", "energy", "CURIE"),
        ("semantic_type", "   ", "non-empty"),
        ("unit_normalized", "", "non-empty"),
    ],
)
def test_the_validator_rejects_a_bad_facet_value_and_names_the_element(
    tag: str, value: str, expected: str
) -> None:
    attribute = _annotated(**{tag: value})
    instantiates_of(attribute).append(MATERIALS_FACETS_CURIE)

    problems = facet_problems(attribute, "System.positions")
    assert len(problems) == 1
    assert "System.positions" in problems[0]
    assert tag in problems[0]
    assert expected in problems[0]

    with pytest.raises(FacetError) as excinfo:
        validate_schema_facets(_schema(attribute))
    assert "System.positions" in str(excinfo.value)


def test_a_good_element_has_no_problems() -> None:
    attribute = SlotDefinition(name="positions")
    write_facets(
        attribute,
        MaterialsFacets(
            semantic_type="quantitykind:PositionVector",
            coordinate_frame=CoordinateFrame.cartesian,
            per_atom=False,
            spin_channel=0,
            unit_normalized="m",
        ),
    )
    assert facet_problems(attribute, "System.positions") == []
    validate_schema_facets(_schema(attribute))


def test_facets_without_instantiates_are_reported() -> None:
    """Decision 4's mechanism is the reference, not the tags on their own."""
    attribute = _annotated(per_atom="true")
    problems = facet_problems(attribute, "System.positions")
    assert len(problems) == 1
    assert MATERIALS_FACETS_CURIE in problems[0]


def test_instantiates_without_facets_is_reported() -> None:
    attribute = SlotDefinition(name="positions")
    instantiates_of(attribute).append(MATERIALS_FACETS_CURIE)
    problems = facet_problems(attribute, "System.positions")
    assert len(problems) == 1
    assert "carries no facet" in problems[0]


def test_the_validator_reports_every_bad_element_not_just_the_first() -> None:
    first = _annotated(per_atom="maybe")
    instantiates_of(first).append(MATERIALS_FACETS_CURIE)
    second = SlotDefinition(name="energy")
    set_annotation(second, "coordinate_frame", "spherical")
    instantiates_of(second).append(MATERIALS_FACETS_CURIE)

    schema = _schema(first)
    add_attribute(class_of(schema, "System"), second)

    with pytest.raises(FacetError) as excinfo:
        validate_schema_facets(schema)
    message = str(excinfo.value)
    assert "System.positions" in message
    assert "System.energy" in message
    assert "2 bad facet value(s)" in message


def test_a_non_facet_annotation_is_left_alone() -> None:
    """Adapters record other things in annotations; this validator owns five."""
    attribute = _annotated(source_path_raw="run[0].calculation[-1].energy")
    assert facet_problems(attribute, "System.positions") == []


def test_the_parsers_emit_facets_that_validate() -> None:
    from schematerial.parsers import EmmetParser, NomadParser, OptimadeParser

    for parser, fixture in (
        (NomadParser(), "nomad_schema.yaml"),
        (OptimadeParser(), "optimade_schema.yaml"),
        (EmmetParser(), "emmet_schema.yaml"),
    ):
        from pathlib import Path

        schema = parser.parse(Path(__file__).parent.parent / "fixtures" / fixture)
        validate_schema_facets(schema)
