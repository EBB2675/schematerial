"""The side index embeddings live in. Decision 10, Card 2's migration."""

import pytest

from schematerial.embeddings import EmbeddingIndex
from schematerial.identity import ElementIdError, UnknownPrefixError


def test_vectors_are_keyed_by_element_id() -> None:
    index = EmbeddingIndex()
    index.set("nomadsim:Run.calculation.energy.total.value", [0.1, 0.2, 0.3])
    assert index.get("nomadsim:Run.calculation.energy.total.value") == (0.1, 0.2, 0.3)
    assert "nomadsim:Run.calculation.energy.total.value" in index
    assert len(index) == 1


def test_an_absent_element_has_no_vector() -> None:
    assert EmbeddingIndex().get("nomadsim:Run.energy") is None


def test_a_malformed_key_cannot_enter_the_index() -> None:
    index = EmbeddingIndex()
    with pytest.raises(ElementIdError):
        index.set("Run.energy", [0.1])
    with pytest.raises(UnknownPrefixError):
        index.set("nomad:Run.energy", [0.1])


def test_the_index_can_be_built_from_a_mapping() -> None:
    index = EmbeddingIndex({"bammd:ExperimentalStep": [1.0, 2.0]})
    assert index.get("bammd:ExperimentalStep") == (1.0, 2.0)
    assert list(index) == ["bammd:ExperimentalStep"]


def test_the_index_is_the_only_place_a_vector_lives() -> None:
    """The element it describes serialises without it."""
    from linkml_runtime.dumpers import yaml_dumper
    from linkml_runtime.linkml_model.meta import SlotDefinition

    element = SlotDefinition(name="energy", range="float")
    index = EmbeddingIndex({"nomadsim:Run.energy": [0.1, 0.2]})
    assert "0.1" not in yaml_dumper.dumps(element)
    assert index.get("nomadsim:Run.energy") is not None
