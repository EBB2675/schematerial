"""Real materialisation, cache isolation, and reproducible keys."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from linkml_runtime.dumpers import yaml_dumper
from linkml_runtime.utils.schemaview import SchemaView

from schematerial._linkml import attributes_of, class_of
from schematerial.cache import MaterialisationCache, content_hash
from schematerial.embeddings import EmbeddingIndex
from schematerial.facets import read_facets

SOURCE = """id: https://example.org/cache
name: cache_fixture
imports:
  - linkml:types
classes:
  Parent:
    attributes:
      energy:
        range: float
  Child:
    is_a: Parent
"""


def test_warm_prepare_and_lookup_do_no_materialisation() -> None:
    cache = MaterialisationCache()
    original = SchemaView.materialize_derived_schema
    with patch.object(SchemaView, "materialize_derived_schema", autospec=True,
                      side_effect=original) as materialise:
        key = cache.prepare(SOURCE)
        assert cache.prepare(SOURCE) == key
        result = cache.get(key)
        assert attributes_of(class_of(result, "Child"))["energy"].range == "float"
        assert materialise.call_count == 1
        changed = cache.prepare(SOURCE + "\n")
        assert changed != key
        assert materialise.call_count == 2


def test_hash_is_stable_across_processes() -> None:
    outputs = []
    for seed in ("1", "2"):
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; from schematerial.cache import content_hash; "
             "print(content_hash(sys.stdin.read()))"],
            input=SOURCE, text=True, capture_output=True, check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        outputs.append(result.stdout.strip())
    assert outputs == [content_hash(SOURCE)] * 2
    assert content_hash("") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_caller_mutation_cannot_poison_cached_schema() -> None:
    cache = MaterialisationCache()
    key = cache.prepare(SOURCE)
    result = cache.get(key)
    attributes_of(class_of(result, "Child"))["energy"].range = "integer"
    assert attributes_of(class_of(cache.get(key), "Child"))["energy"].range == "float"


def test_lookup_miss_never_materialises() -> None:
    with patch.object(SchemaView, "materialize_derived_schema") as materialise:
        with pytest.raises(KeyError):
            MaterialisationCache().get(content_hash(SOURCE))
        materialise.assert_not_called()


def test_concurrent_preparations_materialise_once() -> None:
    cache = MaterialisationCache()
    original = SchemaView.materialize_derived_schema
    with patch.object(SchemaView, "materialize_derived_schema", autospec=True,
                      side_effect=original) as materialise:
        with ThreadPoolExecutor(max_workers=4) as executor:
            keys = list(executor.map(cache.prepare, [SOURCE] * 8))
        assert len(set(keys)) == 1
        assert materialise.call_count == 1


def test_failed_materialisation_is_not_cached() -> None:
    cache = MaterialisationCache()
    with patch.object(SchemaView, "materialize_derived_schema",
                      side_effect=RuntimeError("failed")):
        with pytest.raises(RuntimeError, match="failed"):
            cache.prepare(SOURCE)
    with pytest.raises(KeyError):
        cache.get(content_hash(SOURCE))
    assert cache.prepare(SOURCE) == content_hash(SOURCE)


def test_external_imports_fail_before_materialisation() -> None:
    with patch.object(SchemaView, "materialize_derived_schema") as materialise:
        with pytest.raises(ValueError, match="resolve external.*other.yaml"):
            MaterialisationCache().prepare(SOURCE.replace("linkml:types", "other.yaml"))
        materialise.assert_not_called()


def test_embeddings_do_not_change_source_or_cache_entry() -> None:
    cache = MaterialisationCache()
    key = cache.prepare(SOURCE)
    before = yaml_dumper.dumps(cache.get(key))
    embeddings = EmbeddingIndex()
    embeddings.set("smat:Parent.energy", [1.0, 2.0])
    embeddings.set("smat:Parent.energy", [3.0, 4.0])
    assert cache.prepare(SOURCE) == key
    assert yaml_dumper.dumps(cache.get(key)) == before
    assert "embedding" not in before


def test_materialisation_preserves_inherited_facets() -> None:
    source = SOURCE.replace("        range: float", """        range: float
        instantiates:
          - smat:MaterialsFacets
        annotations:
          semantic_type: quantitykind:Energy
          coordinate_frame: cartesian
          per_atom: false
          spin_channel: 0
          unit_normalized: J""")
    cache = MaterialisationCache()
    schema = cache.get(cache.prepare(source))
    inherited = attributes_of(class_of(schema, "Child"))["energy"]
    facets = read_facets(inherited)
    assert facets.semantic_type == "quantitykind:Energy"
    assert facets.coordinate_frame == "cartesian"
    assert facets.per_atom is False
    assert facets.spin_channel == 0
    assert facets.unit_normalized == "J"


def test_self_contained_schema_needs_no_imports() -> None:
    source = """id: https://example.org/standalone
name: standalone
classes:
  Empty: {}
"""
    cache = MaterialisationCache()
    assert class_of(cache.get(cache.prepare(source)), "Empty").name == "Empty"


def test_malformed_source_does_not_publish_an_entry() -> None:
    cache = MaterialisationCache()
    source = "classes: ["
    with pytest.raises(ValueError):
        cache.prepare(source)
    with pytest.raises(KeyError):
        cache.get(content_hash(source))


def test_one_line_yaml_is_content_not_a_file_name() -> None:
    source = "{id: 'https://example.org/inline', name: inline, classes: {Empty: {}}}"
    cache = MaterialisationCache()
    assert class_of(cache.get(cache.prepare(source)), "Empty").name == "Empty"
