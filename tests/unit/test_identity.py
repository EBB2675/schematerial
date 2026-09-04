"""Card 1: element identity and snapshot. Decisions 1 and 2."""

import json
import subprocess
import sys
import textwrap

import pytest
from linkml_runtime.linkml_model.meta import ClassDefinition, SchemaDefinition, SlotDefinition

from schematerial._linkml import add_attribute, add_class
from schematerial.facets import write_facets
from schematerial.identity import (
    PREFIXES,
    ElementIdError,
    ElementSnapshot,
    QualifiedNameError,
    Source,
    UnknownPrefixError,
    capture_snapshot,
    element_id,
    join_qualified_name,
    parse_element_id,
    snapshot_index,
)
from schematerial.models import MaterialsFacets
from schematerial.semantics import semantic_types


def _attribute(
    name: str,
    *,
    range: str | None = None,
    unit: str | None = None,
    semantic_type: str | None = None,
) -> SlotDefinition:
    from linkml_runtime.linkml_model.meta import UnitOfMeasure

    attribute = SlotDefinition(name=name, range=range)
    if unit is not None:
        attribute.unit = UnitOfMeasure(ucum_code=unit)
    write_facets(attribute, MaterialsFacets(semantic_type=semantic_type))
    return attribute


def _inline(*classes: ClassDefinition, version: str | None = "1.0") -> SchemaDefinition:
    schema = SchemaDefinition(id="https://example.org/inline", name="inline", version=version)
    for definition in classes:
        add_class(schema, definition)
    return schema


def _schema() -> SchemaDefinition:
    """A small inline schema. Nesting is a slot whose range is a class."""
    run = ClassDefinition(name="Run", tree_root=True)
    add_attribute(run, SlotDefinition(name="calculation", range="Calculation"))
    add_attribute(run, SlotDefinition(name="system", range="System"))

    calculation = ClassDefinition(name="Calculation")
    add_attribute(
        calculation,
        _attribute("energy", range="float", unit="J", semantic_type=semantic_types.ENERGY),
    )
    add_attribute(calculation, _attribute("positions", range="float"))

    system = ClassDefinition(name="System")
    add_attribute(
        system,
        _attribute(
            "positions", range="float", unit="m", semantic_type=semantic_types.ATOMIC_POSITION
        ),
    )

    return _inline(run, calculation, system)


# --- the prefix map, decision 1 ----------------------------------------------


def test_prefix_map_is_exactly_decision_1() -> None:
    assert set(PREFIXES) == {
        "nomadsim",
        "nomadmeas",
        "emmet",
        "optimade",
        "bammd",
        "pmdco",
        "smat",
    }
    assert set(PREFIXES) == {source.value for source in Source}


def test_unknown_prefix_is_rejected_and_names_the_known_ones() -> None:
    with pytest.raises(UnknownPrefixError) as excinfo:
        element_id("nomad", ["Run"])
    assert "nomad" in str(excinfo.value)
    assert "nomadsim" in str(excinfo.value)


# --- "identity round-trips for a class, a nested attribute, and a name
#      containing a dot" ------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "segments", "expected"),
    [
        pytest.param(Source.EMMET, ["TaskDocument"], "emmet:TaskDocument", id="class"),
        pytest.param(
            Source.NOMAD_SIMULATION,
            ["Run", "calculation", "energy", "total", "value"],
            "nomadsim:Run.calculation.energy.total.value",
            id="nested-attribute",
        ),
        pytest.param(
            Source.OPTIMADE,
            ["Structure", "chemical_formula.reduced"],
            "optimade:Structure.chemical_formula%2Ereduced",
            id="name-containing-a-dot",
        ),
        pytest.param(
            Source.BAM_MASTERDATA,
            ["ExperimentalStep", "100%25"],
            "bammd:ExperimentalStep.100%2525",
            id="name-containing-a-percent",
        ),
    ],
)
def test_identity_round_trips(source: Source, segments: list[str], expected: str) -> None:
    identifier = element_id(source, segments)
    assert identifier == expected

    parsed = parse_element_id(identifier)
    assert parsed.source == source.value
    assert parsed.segments == tuple(segments)
    assert parsed.name == segments[-1]
    assert element_id(parsed.source, parsed.qualified_name) == identifier
    assert element_id(parsed.source, parsed.segments) == identifier


def test_a_dotted_name_does_not_look_like_a_deeper_path() -> None:
    """The escape is what makes the reverse parser exact."""
    escaped = element_id("optimade", ["Structure", "chemical_formula.reduced"])
    nested = element_id("optimade", ["Structure", "chemical_formula", "reduced"])
    assert escaped != nested
    assert parse_element_id(escaped).segments == ("Structure", "chemical_formula.reduced")
    assert parse_element_id(nested).segments == ("Structure", "chemical_formula", "reduced")


def test_parsed_id_reports_its_parent() -> None:
    assert parse_element_id("nomadsim:Run.system.atoms").parent == "Run.system"
    assert parse_element_id("nomadsim:Run").parent is None
    assert parse_element_id("optimade:S.a%2Eb.c").parent == "S.a%2Eb"


# --- "two elements with the same leaf name under different parents get
#      different ids" ---------------------------------------------------------


def test_same_leaf_name_under_different_parents_differs() -> None:
    system = element_id("nomadsim", ["Run", "system", "atoms", "positions"])
    calculation = element_id("nomadsim", ["Run", "calculation", "positions"])
    assert system != calculation
    assert parse_element_id(system).name == parse_element_id(calculation).name


def test_same_qualified_name_under_different_sources_differs() -> None:
    assert element_id("nomadsim", ["Run", "energy"]) != element_id("emmet", ["Run", "energy"])


# --- "a qualified name containing an index is rejected with a message,
#      per decision 1" --------------------------------------------------------


@pytest.mark.parametrize(
    ("qualified_name", "offending"),
    [
        ("run[0].calculation[-1].energy.total.value", "run[0]"),
        ("run[0].system[-1].atoms.n_atoms", "run[0]"),
        ("calcs_reversed[0].output.energy", "calcs_reversed[0]"),
        ("calcs_reversed[0].output.structure.sites[].xyz", "calcs_reversed[0]"),
    ],
)
def test_an_index_is_rejected_with_a_message(qualified_name: str, offending: str) -> None:
    with pytest.raises(QualifiedNameError) as excinfo:
        element_id("nomadsim", qualified_name)
    message = str(excinfo.value)
    assert offending in message, "the message must name the offending segment"
    assert "schema path" in message and "instance path" in message
    assert "decision 1" in message


def test_an_index_is_rejected_from_segments_too() -> None:
    with pytest.raises(QualifiedNameError):
        element_id("emmet", ["TaskDocument", "calcs_reversed[0]", "energy"])


def test_an_empty_segment_is_rejected() -> None:
    with pytest.raises(QualifiedNameError):
        element_id("nomadsim", "Run..energy")
    with pytest.raises(QualifiedNameError):
        element_id("nomadsim", "")


def test_whitespace_in_a_segment_is_rejected() -> None:
    with pytest.raises(QualifiedNameError) as excinfo:
        element_id("bammd", ["ExperimentalStep", "sample name"])
    assert "sample name" in str(excinfo.value)


def test_a_stray_percent_is_rejected_rather_than_repaired() -> None:
    with pytest.raises(QualifiedNameError) as excinfo:
        element_id("bammd", "Step.50%off")
    assert "position" in str(excinfo.value)
    # Lower case is not the canonical escape, so it is not silently accepted.
    with pytest.raises(QualifiedNameError):
        element_id("optimade", "Structure.a%2eb")


def test_a_string_without_a_prefix_is_not_an_element_id() -> None:
    with pytest.raises(ElementIdError):
        parse_element_id("Run.calculation.energy")
    with pytest.raises(UnknownPrefixError):
        parse_element_id("nomad:Run.calculation.energy")


# --- "a snapshot survives serialisation and reload unchanged" ----------------


def test_snapshot_survives_serialisation_and_reload() -> None:
    snapshot = capture_snapshot(
        name="value",
        parent="Run.calculation.energy.total",
        range="float",
        unit="J",
        semantic_type="qudt:Energy",
        source_version="1.0",
    )
    reloaded = ElementSnapshot.model_validate_json(snapshot.model_dump_json())
    assert reloaded == snapshot
    assert ElementSnapshot.model_validate(snapshot.model_dump()) == snapshot
    assert json.loads(snapshot.model_dump_json()) == {
        "name": "value",
        "parent": "Run.calculation.energy.total",
        "range": "float",
        "unit": "J",
        "semantic_type": "qudt:Energy",
        "source_version": "1.0",
    }


def test_a_sparse_snapshot_survives_serialisation_and_reload() -> None:
    snapshot = capture_snapshot(name="TaskDocument")
    assert ElementSnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot
    assert snapshot.parent is None
    assert snapshot.semantic_type is None


def test_a_snapshot_rejects_unknown_fields() -> None:
    """Decision 2 fixes what a snapshot holds; decision 10 keeps it small."""
    with pytest.raises(ValueError):
        ElementSnapshot.model_validate({"name": "value", "embedding": [0.1, 0.2]})


# --- snapshot capture --------------------------------------------------------


def test_snapshot_index_captures_every_element() -> None:
    index = snapshot_index(_schema(), Source.NOMAD_SIMULATION)

    assert set(index) == {
        "nomadsim:Run",
        "nomadsim:Run.calculation",
        "nomadsim:Run.calculation.energy",
        "nomadsim:Run.calculation.positions",
        "nomadsim:Run.system",
        "nomadsim:Run.system.positions",
    }

    energy = index["nomadsim:Run.calculation.energy"]
    assert energy.name == "energy"
    assert energy.parent == "Run.calculation"
    assert energy.range == "float"
    assert energy.unit == "J"
    assert energy.semantic_type == "quantitykind:Energy"
    assert energy.source_version == "1.0"

    assert index["nomadsim:Run"].parent is None


def test_an_unstated_semantic_type_is_absent_not_unknown() -> None:
    """Decision 4: a facet with no value is absent, not guessed."""
    index = snapshot_index(_schema(), Source.NOMAD_SIMULATION)
    assert index["nomadsim:Run.calculation.positions"].semantic_type is None


def test_snapshot_index_rejects_the_prototype_instance_paths() -> None:
    """The fixture schemas still key on instance paths; Card 11 resolves them."""
    root = ClassDefinition(name="root", tree_root=True)
    add_attribute(root, SlotDefinition(name="run[0]", range="float"))
    with pytest.raises(QualifiedNameError) as excinfo:
        snapshot_index(_inline(root), Source.NOMAD_SIMULATION)
    assert "run[0]" in str(excinfo.value)


def test_one_class_reached_by_two_paths_gets_two_ids() -> None:
    """A class is a type, an element is a place. The same class reached down two
    different paths is two elements, and decision 1 gives them two ids."""
    run = ClassDefinition(name="Run", tree_root=True)
    add_attribute(run, SlotDefinition(name="initial", range="System"))
    add_attribute(run, SlotDefinition(name="final", range="System"))
    system = ClassDefinition(name="System")
    add_attribute(system, SlotDefinition(name="positions", range="float"))

    index = snapshot_index(_inline(run, system), Source.NOMAD_SIMULATION)
    assert "nomadsim:Run.initial.positions" in index
    assert "nomadsim:Run.final.positions" in index


def test_a_self_referential_schema_terminates() -> None:
    """A section that contains itself is legal and must not walk forever."""
    run = ClassDefinition(name="Run", tree_root=True)
    add_attribute(run, SlotDefinition(name="child", range="Run"))
    index = snapshot_index(_inline(run), Source.NOMAD_SIMULATION)
    assert set(index) == {"nomadsim:Run", "nomadsim:Run.child"}


# --- "ids are stable across two runs on identical input" ---------------------

_STABILITY_SCRIPT = textwrap.dedent(
    """
    import json

    from linkml_runtime.linkml_model.meta import (
        ClassDefinition,
        SchemaDefinition,
        SlotDefinition,
    )

    from schematerial.identity import Source, snapshot_index

    run = ClassDefinition(name="Run", tree_root=True)
    for name, range_ in [
        ("energy", "float"),
        ("positions", "float"),
        ("chemical_formula%2Ereduced", "string"),
    ]:
        run.attributes[name] = SlotDefinition(name=name, range=range_)
    schema = SchemaDefinition(id="https://example.org/i", name="inline", version="1.0")
    schema.classes["Run"] = run

    index = snapshot_index(schema, Source.NOMAD_SIMULATION)
    print(json.dumps({k: v.model_dump() for k, v in index.items()}, sort_keys=True))
    """
)


def _run_in_subprocess(hash_seed: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", _STABILITY_SCRIPT],
        capture_output=True,
        text=True,
        check=True,
        env={"PYTHONHASHSEED": hash_seed, "PATH": ""},
    )
    return result.stdout


def test_ids_are_stable_across_two_runs_on_identical_input() -> None:
    first = _run_in_subprocess("0")
    second = _run_in_subprocess("1")
    assert first == second
    assert "nomadsim:Run.energy" in json.loads(first)


def test_ids_are_stable_within_a_process() -> None:
    assert snapshot_index(_schema(), Source.NOMAD_SIMULATION) == snapshot_index(
        _schema(), Source.NOMAD_SIMULATION
    )


def test_a_qualified_name_round_trips_through_join_and_id() -> None:
    segments = ["Run", "a.b", "c%d"]
    qualified = join_qualified_name(segments)
    assert parse_element_id(element_id("smat", qualified)).segments == tuple(segments)
