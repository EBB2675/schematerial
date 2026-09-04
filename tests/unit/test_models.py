"""The generated model, and the facets it defines. Card 3."""

import importlib

import pytest
from linkml_runtime.linkml_model.meta import ClassDefinition, SchemaDefinition, SlotDefinition
from pydantic import ValidationError

from schematerial.models import (
    CoordinateFrame,
    Entity,
    MaterialsFacets,
    SchemaField,
    SchemaModel,
)
from schematerial.semantics import semantic_types
from schematerial.semantics.ontology import OntologyConcept, OntologyModel, OntologyTerm

# --- the facets of decision 4 ------------------------------------------------


def test_card_2_core_concepts_are_linkml_metamodel_aliases() -> None:
    """The old wrappers survive without creating a second canonical model."""
    assert SchemaModel is SchemaDefinition
    assert Entity is ClassDefinition
    assert SchemaField is SlotDefinition


def test_the_model_defines_exactly_the_five_facets() -> None:
    assert set(MaterialsFacets.model_fields) == {
        "semantic_type",
        "coordinate_frame",
        "per_atom",
        "spin_channel",
        "unit_normalized",
    }


def test_every_facet_is_absent_by_default() -> None:
    """A facet with no value is absent, not guessed. No facet has a default."""
    facets = MaterialsFacets()
    for name in MaterialsFacets.model_fields:
        assert getattr(facets, name) is None, f"{name} has a default, which is a guess"


def test_coordinate_frame_has_no_none_member() -> None:
    """An element with no frame carries no facet, so 'none' is not a value."""
    assert {member.value for member in CoordinateFrame} == {
        "cartesian",
        "fractional",
        "reciprocal",
    }


# --- semantic type: an open uriorcurie, not an enum --------------------------


def test_an_unrecognised_semantic_type_is_preserved_verbatim() -> None:
    exotic = "emmo:EMMO_6074aa9d_7c3b_4011_b45a_4e7cde6f5f39"
    facets = MaterialsFacets(semantic_type=exotic)
    assert facets.semantic_type == exotic
    assert MaterialsFacets.model_validate_json(facets.model_dump_json()).semantic_type == exotic
    assert semantic_types.resolve_alias(exotic) == exotic


def test_a_bad_coordinate_frame_is_rejected_by_the_generated_model() -> None:
    with pytest.raises(ValidationError):
        MaterialsFacets(coordinate_frame="spherical")  # type: ignore[arg-type]


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


# --- no vector data in the core (decision 10) --------------------------------


def test_the_core_carries_no_vector_field() -> None:
    assert "embedding" not in MaterialsFacets.model_fields
    dumped = MaterialsFacets(semantic_type="quantitykind:Energy").model_dump()
    assert not any(isinstance(value, list) for value in dumped.values())


# --- ontology records stay app records ---------------------------------------


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


# --- the retired and deleted modules -----------------------------------------


@pytest.mark.parametrize(
    "module",
    [
        "schematerial.models.transform",
        "schematerial.models.crosswalk",
        "schematerial.models.alignment",
        "schematerial.models.annotation",
        "schematerial.models.ontology",
        "schematerial.models.schema",
    ],
)
def test_the_retired_modules_are_gone(module: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module)
