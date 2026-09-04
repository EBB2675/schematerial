"""The models that survive Card 2, and the shape they survive in."""

import pytest
from pydantic import ValidationError

from schematerial.models.schema import CoordinateFrame, Entity, SchemaField, SchemaModel
from schematerial.semantics import semantic_types
from schematerial.semantics.ontology import OntologyConcept, OntologyModel, OntologyTerm

# --- semantic type: an open uriorcurie, not an enum (decision 4) -------------


def test_semantic_type_is_absent_by_default() -> None:
    """A facet with no value is absent, not guessed, and not 'unknown'."""
    f = SchemaField(path="Run.energy", label="energy")
    assert f.semantic_type is None


def test_an_unrecognised_semantic_type_is_preserved_verbatim() -> None:
    """The value space is the vocabularies, not a local enum."""
    exotic = "emmo:EMMO_6074aa9d_7c3b_4011_b45a_4e7cde6f5f39"
    f = SchemaField(path="Run.k_point", label="k_point", semantic_type=exotic)
    assert f.semantic_type == exotic
    assert SchemaField.model_validate_json(f.model_dump_json()).semantic_type == exotic
    assert semantic_types.resolve_alias(exotic) == exotic


def test_an_unrecognised_semantic_type_survives_snapshot_capture() -> None:
    from schematerial.identity import Source, snapshot_index

    exotic = "pmdco:SomeTermNobodyHasHeardOf"
    model = SchemaModel(
        name="m",
        entities=[
            Entity(
                name="Run",
                fields=[SchemaField(path="Run.x", label="x", semantic_type=exotic)],
            )
        ],
    )
    index = snapshot_index(model, Source.NOMAD_SIMULATION)
    assert index["nomadsim:Run.x"].semantic_type == exotic


def test_the_prototype_unknown_is_not_a_semantic_type() -> None:
    from schematerial.identity import Source, snapshot_index

    model = SchemaModel(
        name="m",
        entities=[
            Entity(
                name="Run",
                fields=[SchemaField(path="Run.x", label="x", semantic_type="unknown")],
            )
        ],
    )
    assert snapshot_index(model, Source.NOMAD_SIMULATION)["nomadsim:Run.x"].semantic_type is None


# --- the alias table ---------------------------------------------------------


def test_aliases_are_curies_into_the_decision_4_vocabularies() -> None:
    allowed = ("quantitykind:", "unit:", "emmo:", "pmdco:")
    for alias, curie in semantic_types.SEMANTIC_TYPE_ALIASES.items():
        assert curie.startswith(allowed), f"{alias} -> {curie} is not a QUDT/EMMO/PMDco CURIE"
        assert ":" in curie and not curie.endswith(":")


def test_the_six_unresolved_prototype_values_have_no_alias() -> None:
    """Dropped deliberately; see decision record 002."""
    for dropped in ("lattice_parameter", "k_point", "identifier", "label", "flag", "unknown"):
        assert dropped not in semantic_types.SEMANTIC_TYPE_ALIASES


def test_resolve_alias_expands_a_known_alias_and_passes_anything_else_through() -> None:
    assert semantic_types.resolve_alias("energy") == "quantitykind:Energy"
    assert semantic_types.resolve_alias("quantitykind:Energy") == "quantitykind:Energy"
    assert semantic_types.resolve_alias("whatever:Thing") == "whatever:Thing"
    assert semantic_types.resolve_alias(None) is None


def test_the_alias_table_is_not_mutable() -> None:
    with pytest.raises(TypeError):
        semantic_types.SEMANTIC_TYPE_ALIASES["energy"] = "nope"  # type: ignore[index]


# --- no vector data in the core IR (decision 10) -----------------------------


def test_a_schema_field_has_no_embedding_field() -> None:
    assert "embedding" not in SchemaField.model_fields
    with pytest.raises(ValidationError):
        SchemaField(path="Run.x", label="x", embedding=[0.1, 0.2])  # type: ignore[call-arg]


def test_serialising_an_element_produces_no_vector_data() -> None:
    f = SchemaField(path="Run.energy", label="energy", unit="J", examples=[1.0, 2.0])
    dumped = f.model_dump()
    vector_like = {
        key: value
        for key, value in dumped.items()
        if key != "examples"
        and isinstance(value, list)
        and value
        and all(isinstance(item, float) for item in value)
    }
    assert vector_like == {}


def test_a_schema_field_carries_no_ontology_terms() -> None:
    """A grounding proposal is Card 14's output, never a field on an element."""
    assert "ontology_terms" not in SchemaField.model_fields


# --- what survives -----------------------------------------------------------


def test_schema_field_defaults() -> None:
    f = SchemaField(path="Run.energy", label="energy")
    assert f.datatype == "unknown"
    assert f.shape is None
    assert f.cardinality == "one"
    assert f.coordinate_frame == CoordinateFrame.NONE
    assert f.per_atom is False
    assert f.spin_channel is None


def test_schema_model_round_trips() -> None:
    model = SchemaModel(
        name="NOMAD",
        version="1.0",
        format="nomad",
        entities=[
            Entity(
                name="Run",
                parent="Base",
                fields=[
                    SchemaField(
                        path="Run.calculation.energy.total.value",
                        label="energy_total",
                        datatype="float",
                        unit="J",
                        semantic_type=semantic_types.ENERGY,
                    )
                ],
            )
        ],
    )
    assert SchemaModel.model_validate_json(model.model_dump_json()) == model


def test_ontology_records_survive_as_app_records() -> None:
    term = OntologyTerm(
        uri="https://w3id.org/emmo#EMMO_xyz",
        label="Energy",
        ontology="EMMO",
        match_type="exact",
        confidence=0.9,
    )
    assert term.confidence == 0.9
    model = OntologyModel(name="EMMO", concepts=[OntologyConcept(uri=term.uri, label="Energy")])
    assert model.concepts[0].uri == term.uri


def test_ontology_records_are_not_importable_from_models() -> None:
    """models/ becomes generated output in Card 3; app records live elsewhere."""
    import importlib

    import schematerial.models as models

    assert not hasattr(models, "OntologyTerm")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("schematerial.models.ontology")


# --- the deleted models are gone (Card 2's deletion list) --------------------


@pytest.mark.parametrize(
    "module",
    [
        "schematerial.models.transform",
        "schematerial.models.crosswalk",
        "schematerial.models.alignment",
        "schematerial.models.annotation",
    ],
)
def test_the_deleted_modules_are_gone(module: str) -> None:
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module)


# The names themselves are asserted absent in tests/test_invariants.py, which
# greps the tree. Naming them here would put them back in it.
