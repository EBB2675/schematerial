from pathlib import Path

import pytest

from schematerial.models.schema import CoordinateFrame, SchemaField, SchemaModel, SemanticType
from schematerial.parsers._yaml_base import (
    _detect_per_atom,
    _infer_semantic_type,
    _parse_dtype,
    parse_yaml_schema,
)
from schematerial.parsers.base import Parser
from schematerial.parsers.emmet import EmmetParser
from schematerial.parsers.nomad import NomadParser
from schematerial.parsers.optimade import OptimadeParser

FIXTURES = Path(__file__).parent.parent / "fixtures"


# --- helpers ---


def _fields(schema: SchemaModel) -> list[SchemaField]:
    return schema.entities[0].fields


def _get(schema: SchemaModel, label: str) -> SchemaField:
    for f in _fields(schema):
        if f.label == label:
            return f
    raise KeyError(f"{label!r} not found in schema")


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
    assert result == SemanticType.ENERGY


def test_infer_bandgap_beats_energy() -> None:
    # "band_gap" must win over "energy" even if both appear in the text
    result = _infer_semantic_type("band_gap", "calculation.band_gap.value", "Electronic band gap.")
    assert result == SemanticType.BANDGAP


def test_infer_lattice_parameter() -> None:
    result = _infer_semantic_type(
        "lattice_vectors", "system.atoms.lattice_vectors", "Bravais lattice vectors."
    )
    assert result == SemanticType.LATTICE_PARAMETER


def test_infer_atomic_position() -> None:
    result = _infer_semantic_type(
        "atom_positions", "system.atoms.positions", "Cartesian positions of each atom."
    )
    assert result == SemanticType.ATOMIC_POSITION


def test_infer_flag() -> None:
    result = _infer_semantic_type(
        "periodicity", "system.atoms.periodic", "Periodicity along each direction."
    )
    assert result == SemanticType.FLAG


def test_infer_identifier() -> None:
    result = _infer_semantic_type(
        "chemical_composition_reduced", "system.chemical_composition_reduced", None
    )
    assert result == SemanticType.IDENTIFIER


def test_infer_label() -> None:
    result = _infer_semantic_type(
        "atom_labels", "system.atoms.labels", "Element symbol for each atom site."
    )
    assert result == SemanticType.LABEL


def test_infer_cell_length_is_lattice_parameter() -> None:
    result = _infer_semantic_type("cell_length_a", "_cell_length_a", "a cell edge length.")
    assert result == SemanticType.LATTICE_PARAMETER


def test_infer_cell_angle_is_lattice_parameter() -> None:
    result = _infer_semantic_type("cell_angle_alpha", "_cell_angle_alpha", "Cell angle alpha.")
    assert result == SemanticType.LATTICE_PARAMETER


def test_infer_generic_length() -> None:
    result = _infer_semantic_type("bond_length", "structure.bond_length", "Bond length in Å.")
    assert result == SemanticType.LENGTH


# --- per_atom detection ---


def test_per_atom_from_unit() -> None:
    assert _detect_per_atom("energy", "eV/atom") is True
    assert _detect_per_atom("energy", "J/atom") is True
    assert _detect_per_atom("energy", "eV") is False


def test_per_atom_from_name() -> None:
    assert _detect_per_atom("energy_total_per_atom", "J") is True
    assert _detect_per_atom("energy_per_atom", None) is True
    assert _detect_per_atom("energy_total", None) is False


# --- Protocol conformance ---


def test_parsers_satisfy_protocol() -> None:
    assert isinstance(NomadParser(), Parser)
    assert isinstance(OptimadeParser(), Parser)
    assert isinstance(EmmetParser(), Parser)


# --- NOMAD parser ---


@pytest.fixture(scope="module")
def nomad_schema() -> SchemaModel:
    return NomadParser().parse(FIXTURES / "nomad_schema.yaml")


def test_nomad_format(nomad_schema: SchemaModel) -> None:
    assert nomad_schema.format == "nomad"
    assert nomad_schema.name == "NOMAD Metainfo"
    assert nomad_schema.version == "1.0"


def test_nomad_field_count(nomad_schema: SchemaModel) -> None:
    assert len(_fields(nomad_schema)) == 10


def test_nomad_energy_total(nomad_schema: SchemaModel) -> None:
    f = _get(nomad_schema, "energy_total")
    assert f.path == "run[0].calculation[-1].energy.total.value"
    assert f.datatype == "float"
    assert f.unit == "J"
    assert f.semantic_type == SemanticType.ENERGY
    assert f.per_atom is False
    assert f.shape is None
    assert f.cardinality == "one"


def test_nomad_energy_total_per_atom(nomad_schema: SchemaModel) -> None:
    f = _get(nomad_schema, "energy_total_per_atom")
    assert f.per_atom is True
    assert f.semantic_type == SemanticType.ENERGY


def test_nomad_band_gap(nomad_schema: SchemaModel) -> None:
    assert _get(nomad_schema, "band_gap").semantic_type == SemanticType.BANDGAP


def test_nomad_lattice_vectors(nomad_schema: SchemaModel) -> None:
    f = _get(nomad_schema, "lattice_vectors")
    assert f.semantic_type == SemanticType.LATTICE_PARAMETER
    assert f.shape == [3, 3]
    assert f.cardinality == "many"


def test_nomad_atom_positions(nomad_schema: SchemaModel) -> None:
    f = _get(nomad_schema, "atom_positions")
    assert f.semantic_type == SemanticType.ATOMIC_POSITION
    assert f.coordinate_frame == CoordinateFrame.CARTESIAN
    assert f.shape == [None, 3]


def test_nomad_atom_labels(nomad_schema: SchemaModel) -> None:
    f = _get(nomad_schema, "atom_labels")
    assert f.semantic_type == SemanticType.LABEL
    assert f.shape == [None]


def test_nomad_periodicity(nomad_schema: SchemaModel) -> None:
    f = _get(nomad_schema, "periodicity")
    assert f.semantic_type == SemanticType.FLAG
    assert f.shape == [3]


def test_nomad_n_atoms(nomad_schema: SchemaModel) -> None:
    f = _get(nomad_schema, "n_atoms")
    assert f.semantic_type == SemanticType.IDENTIFIER
    assert f.datatype == "int"
    assert f.unit is None


def test_nomad_source_file(nomad_schema: SchemaModel) -> None:
    assert nomad_schema.source_file is not None
    assert "nomad_schema.yaml" in nomad_schema.source_file


# --- OPTIMADE parser ---


@pytest.fixture(scope="module")
def optimade_schema() -> SchemaModel:
    return OptimadeParser().parse(FIXTURES / "optimade_schema.yaml")


def test_optimade_format(optimade_schema: SchemaModel) -> None:
    assert optimade_schema.format == "optimade"
    assert optimade_schema.name == "OPTIMADE"
    assert optimade_schema.version == "1.2"


def test_optimade_field_count(optimade_schema: SchemaModel) -> None:
    assert len(_fields(optimade_schema)) == 11


def test_optimade_total_energy(optimade_schema: SchemaModel) -> None:
    f = _get(optimade_schema, "total_energy")
    assert f.path == "attributes._nomad_total_energy"
    assert f.unit == "eV"
    assert f.semantic_type == SemanticType.ENERGY
    assert f.per_atom is False


def test_optimade_energy_per_atom(optimade_schema: SchemaModel) -> None:
    f = _get(optimade_schema, "energy_per_atom")
    assert f.unit == "eV/atom"
    assert f.per_atom is True
    assert f.semantic_type == SemanticType.ENERGY


def test_optimade_cartesian_site_positions(optimade_schema: SchemaModel) -> None:
    f = _get(optimade_schema, "cartesian_site_positions")
    assert f.semantic_type == SemanticType.ATOMIC_POSITION
    assert f.coordinate_frame == CoordinateFrame.CARTESIAN
    assert f.shape == [None, 3]


def test_optimade_lattice_vectors(optimade_schema: SchemaModel) -> None:
    f = _get(optimade_schema, "lattice_vectors")
    assert f.semantic_type == SemanticType.LATTICE_PARAMETER
    assert f.shape == [3, 3]
    assert f.unit == "Angstrom"


def test_optimade_dimension_types(optimade_schema: SchemaModel) -> None:
    f = _get(optimade_schema, "dimension_types")
    assert f.semantic_type == SemanticType.FLAG
    assert f.shape == [3]


def test_optimade_nperiodic_dimensions(optimade_schema: SchemaModel) -> None:
    assert _get(optimade_schema, "nperiodic_dimensions").semantic_type == SemanticType.FLAG


def test_optimade_band_gap(optimade_schema: SchemaModel) -> None:
    assert _get(optimade_schema, "band_gap").semantic_type == SemanticType.BANDGAP


def test_optimade_nsites(optimade_schema: SchemaModel) -> None:
    assert _get(optimade_schema, "nsites").semantic_type == SemanticType.IDENTIFIER


# --- Emmet parser ---


@pytest.fixture(scope="module")
def emmet_schema() -> SchemaModel:
    return EmmetParser().parse(FIXTURES / "emmet_schema.yaml")


def test_emmet_format(emmet_schema: SchemaModel) -> None:
    assert emmet_schema.format == "emmet"
    assert emmet_schema.name == "Emmet"
    assert emmet_schema.version == "0.84"


def test_emmet_field_count(emmet_schema: SchemaModel) -> None:
    assert len(_fields(emmet_schema)) == 8


def test_emmet_energy(emmet_schema: SchemaModel) -> None:
    f = _get(emmet_schema, "energy")
    assert f.path == "calcs_reversed[0].output.energy"
    assert f.unit == "eV"
    assert f.semantic_type == SemanticType.ENERGY
    assert f.per_atom is False


def test_emmet_energy_per_atom(emmet_schema: SchemaModel) -> None:
    f = _get(emmet_schema, "energy_per_atom")
    assert f.per_atom is True
    assert f.semantic_type == SemanticType.ENERGY
    assert f.unit == "eV/atom"


def test_emmet_site_positions(emmet_schema: SchemaModel) -> None:
    f = _get(emmet_schema, "site_positions")
    assert f.semantic_type == SemanticType.ATOMIC_POSITION
    assert f.coordinate_frame == CoordinateFrame.CARTESIAN
    assert f.shape == [None, 3]


def test_emmet_lattice_matrix(emmet_schema: SchemaModel) -> None:
    f = _get(emmet_schema, "lattice_matrix")
    assert f.semantic_type == SemanticType.LATTICE_PARAMETER
    assert f.shape == [3, 3]
    assert f.unit == "Angstrom"


def test_emmet_site_labels(emmet_schema: SchemaModel) -> None:
    assert _get(emmet_schema, "site_labels").semantic_type == SemanticType.LABEL


def test_emmet_band_gap(emmet_schema: SchemaModel) -> None:
    assert _get(emmet_schema, "band_gap").semantic_type == SemanticType.BANDGAP


def test_emmet_nsites(emmet_schema: SchemaModel) -> None:
    assert _get(emmet_schema, "nsites").semantic_type == SemanticType.IDENTIFIER


# --- str path input ---


def test_parser_accepts_str_path() -> None:
    schema = NomadParser().parse(str(FIXTURES / "nomad_schema.yaml"))
    assert schema.format == "nomad"


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
