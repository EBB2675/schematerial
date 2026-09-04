import ast
from dataclasses import dataclass
from pathlib import Path

import pytest
from linkml_runtime.linkml_model.meta import SchemaDefinition, UnitOfMeasure

from schematerial._linkml import attributes_of, class_of
from schematerial.facets import read_facets
from schematerial.models import CoordinateFrame
from schematerial.parsers._yaml_base import (
    ROOT_CLASS,
    _detect_per_atom,
    _infer_semantic_type,
    _parse_dtype,
    parse_yaml_schema,
)
from schematerial.parsers.base import Parser
from schematerial.parsers.nomad import NomadParser
from schematerial.semantics import semantic_types

FIXTURES = Path(__file__).parent.parent / "fixtures"


# --- helpers ---


@dataclass(frozen=True)
class _View:
    """A canonical element, read the way a caller reads one.

    The parsers now emit a LinkML SchemaDefinition, so a "field" is a
    class-local attribute, its type is a `range`, its unit is a `ucum_code`,
    and its facets are annotations under `instantiates`. This view exists so
    the assertions below say what they mean rather than walking LinkML by hand.
    """

    name: str
    path: str | None
    range: str | None
    unit: str | None
    multivalued: bool
    shape: list[str | int] | None
    semantic_type: str | None
    coordinate_frame: CoordinateFrame | None
    per_atom: bool | None


def _annotation(attribute: object, tag: str) -> str | None:
    annotations = getattr(attribute, "annotations", None) or {}
    found = annotations.get(tag)
    return None if found is None else str(getattr(found, "value", found))


def _fields(schema: SchemaDefinition) -> list[_View]:
    return [_get(schema, name) for name in attributes_of(class_of(schema, ROOT_CLASS))]


def _get(schema: SchemaDefinition, label: str) -> _View:
    attributes = attributes_of(class_of(schema, ROOT_CLASS))
    if label not in attributes:
        raise KeyError(f"{label!r} not found in schema")
    attribute = attributes[label]
    facets = read_facets(attribute)
    raw_shape = _annotation(attribute, "source_shape")
    unit = attribute.unit
    unit_code = unit.ucum_code if isinstance(unit, UnitOfMeasure) else None
    return _View(
        name=str(attribute.name),
        path=_annotation(attribute, "source_path_raw"),
        range=None if attribute.range is None else str(attribute.range),
        unit=None if unit_code is None else str(unit_code),
        multivalued=bool(attribute.multivalued),
        shape=None if raw_shape is None else ast.literal_eval(raw_shape),
        semantic_type=facets.semantic_type,
        coordinate_frame=facets.coordinate_frame,
        per_atom=facets.per_atom,
    )


# --- dtype parsing ---


def test_parse_dtype_scalar() -> None:
    assert _parse_dtype("float") == ("float", None)
    assert _parse_dtype("int") == ("int", None)
    assert _parse_dtype("str") == ("str", None)
    assert _parse_dtype("bool") == ("bool", None)


def test_parse_dtype_fixed_shape() -> None:
    assert _parse_dtype("float[3][3]") == ("float", [3, 3])
    assert _parse_dtype("int[3]") == ("int", [3])
    assert _parse_dtype("bool[3]") == ("bool", [3])


def test_parse_dtype_variable_shape() -> None:
    assert _parse_dtype("float[N][3]") == ("float", [None, 3])
    assert _parse_dtype("str[N]") == ("str", [None])


def test_parse_dtype_none() -> None:
    assert _parse_dtype(None) == ("unknown", None)


def test_parse_dtype_unrecognised_token_does_not_crash() -> None:
    # [M] is not N or digits — fullmatch fails, returns raw string with no shape
    result = _parse_dtype("float[M]")
    assert result == ("float[M]", None)


# --- semantic type inference ---


def test_infer_energy() -> None:
    result = _infer_semantic_type("energy_total", "run.calculation.energy.total", None)
    assert result == semantic_types.ENERGY


def test_infer_bandgap_beats_energy() -> None:
    # "band_gap" must win over "energy" even if both appear in the text
    result = _infer_semantic_type("band_gap", "calculation.band_gap.value", "Electronic band gap.")
    assert result == semantic_types.BAND_GAP


def test_infer_lattice_vectors_have_no_semantic_type() -> None:
    """`lattice_parameter` covered cell lengths, cell angles and lattice
    vectors; no single term covers all three. See decision record 002."""
    result = _infer_semantic_type(
        "lattice_vectors", "system.atoms.lattice_vectors", "Bravais lattice vectors."
    )
    assert result is None


def test_infer_atomic_position() -> None:
    result = _infer_semantic_type(
        "atom_positions", "system.atoms.positions", "Cartesian positions of each atom."
    )
    assert result == semantic_types.ATOMIC_POSITION


def test_infer_flag() -> None:
    result = _infer_semantic_type(
        "periodicity", "system.atoms.periodic", "Periodicity along each direction."
    )
    assert result is None


def test_infer_identifier() -> None:
    result = _infer_semantic_type(
        "chemical_composition_reduced", "system.chemical_composition_reduced", None
    )
    assert result is None


def test_infer_label() -> None:
    result = _infer_semantic_type(
        "atom_labels", "system.atoms.labels", "Element symbol for each atom site."
    )
    assert result is None


def test_infer_cell_length_is_a_length() -> None:
    """The prototype called this `lattice_parameter`, which has no term. A cell
    edge length is a length, and that one does resolve."""
    result = _infer_semantic_type("cell_length_a", "_cell_length_a", "a cell edge length.")
    assert result == semantic_types.LENGTH


def test_infer_cell_angle_has_no_semantic_type() -> None:
    result = _infer_semantic_type("cell_angle_alpha", "_cell_angle_alpha", "Cell angle alpha.")
    assert result is None


def test_infer_generic_length() -> None:
    result = _infer_semantic_type("bond_length", "structure.bond_length", "Bond length in Å.")
    assert result == semantic_types.LENGTH


# --- per_atom detection ---


def test_per_atom_from_unit() -> None:
    assert _detect_per_atom("energy", "eV/atom") is True
    assert _detect_per_atom("energy", "J/atom") is True
    assert _detect_per_atom("energy", "eV") is None


def test_per_atom_from_name() -> None:
    assert _detect_per_atom("energy_total_per_atom", "J") is True
    assert _detect_per_atom("energy_per_atom", None) is True
    assert _detect_per_atom("energy_total", None) is None


# --- Protocol conformance ---


def test_parsers_satisfy_protocol() -> None:
    assert isinstance(NomadParser(), Parser)


# --- NOMAD parser ---


@pytest.fixture(scope="module")
def nomad_schema() -> SchemaDefinition:
    return NomadParser().parse(FIXTURES / "nomad_schema.yaml")


def test_nomad_format(nomad_schema: SchemaDefinition) -> None:
    assert nomad_schema.id.endswith("/nomad")
    assert nomad_schema.title == "NOMAD Metainfo"
    assert nomad_schema.version == "1.0"


def test_nomad_field_count(nomad_schema: SchemaDefinition) -> None:
    assert len(_fields(nomad_schema)) == 10


def test_nomad_energy_total(nomad_schema: SchemaDefinition) -> None:
    f = _get(nomad_schema, "energy_total")
    assert f.path == "run[0].calculation[-1].energy.total.value"
    assert f.range == "float"
    assert f.unit == "J"
    assert f.semantic_type == semantic_types.ENERGY
    assert f.per_atom is None
    assert f.shape is None
    assert f.multivalued is False


def test_nomad_energy_total_per_atom(nomad_schema: SchemaDefinition) -> None:
    f = _get(nomad_schema, "energy_total_per_atom")
    assert f.per_atom is True
    assert f.semantic_type == semantic_types.ENERGY


def test_nomad_band_gap(nomad_schema: SchemaDefinition) -> None:
    assert _get(nomad_schema, "band_gap").semantic_type == semantic_types.BAND_GAP


def test_nomad_lattice_vectors(nomad_schema: SchemaDefinition) -> None:
    f = _get(nomad_schema, "lattice_vectors")
    assert f.semantic_type is None
    assert f.shape == [3, 3]
    assert f.multivalued is True


def test_nomad_atom_positions(nomad_schema: SchemaDefinition) -> None:
    f = _get(nomad_schema, "atom_positions")
    assert f.semantic_type == semantic_types.ATOMIC_POSITION
    assert f.coordinate_frame == CoordinateFrame.cartesian
    assert f.shape == ["N", 3]


def test_nomad_atom_labels(nomad_schema: SchemaDefinition) -> None:
    f = _get(nomad_schema, "atom_labels")
    assert f.semantic_type is None
    assert f.shape == ["N"]


def test_nomad_periodicity(nomad_schema: SchemaDefinition) -> None:
    f = _get(nomad_schema, "periodicity")
    assert f.semantic_type is None
    assert f.shape == [3]


def test_nomad_n_atoms(nomad_schema: SchemaDefinition) -> None:
    f = _get(nomad_schema, "n_atoms")
    assert f.semantic_type is None
    assert f.range == "integer"
    assert f.unit is None


def test_nomad_source_file(nomad_schema: SchemaDefinition) -> None:
    assert nomad_schema.source_file is not None
    assert "nomad_schema.yaml" in nomad_schema.source_file


# --- str path input ---


def test_parser_accepts_str_path() -> None:
    schema = NomadParser().parse(str(FIXTURES / "nomad_schema.yaml"))
    assert schema.id.endswith("/nomad")


# --- YAML validation ---


def test_parse_yaml_schema_rejects_list(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("- item1\n- item2\n")
    with pytest.raises(ValueError, match="expected a mapping"):
        parse_yaml_schema(bad, format="nomad")


def test_parse_yaml_schema_rejects_empty(tmp_path: Path) -> None:
    empty = tmp_path / "empty.yaml"
    empty.write_text("")
    with pytest.raises(ValueError, match="expected a mapping"):
        parse_yaml_schema(empty, format="nomad")
