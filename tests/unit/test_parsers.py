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
    _parse_dtype,
    parse_yaml_schema,
)
from schematerial.parsers.base import Parser
from schematerial.parsers.nomad import NomadParser

INLINE_SCHEMA = """# NOMAD Metainfo: DFT calculation results, SI units throughout
# https://nomad-lab.eu/prod/v1/staging/docs/reference/archive.html

name: "NOMAD Metainfo"
version: "1.0"
description: Prototype DFT fields with indexed source paths.

fields:
  - name: energy_total
    path: run[0].calculation[-1].energy.total.value
    dtype: float
    unit: J
    description: Total electronic energy (DFT SCF converged).

  - name: energy_total_per_atom
    path: run[0].calculation[-1].energy.total.value_per_atom
    dtype: float
    unit: J
    description: Total energy divided by number of atoms.

  - name: n_atoms
    path: run[0].system[-1].atoms.n_atoms
    dtype: int
    unit: null
    description: Number of atoms in the simulation cell.

  - name: chemical_composition_reduced
    path: run[0].system[-1].chemical_composition_reduced
    dtype: str
    unit: null
    description: Reduced chemical formula in Hill order (e.g. "GaAs").

  - name: lattice_vectors
    path: run[0].system[-1].atoms.lattice_vectors
    dtype: float[3][3]
    unit: m
    description: Bravais lattice vectors as a 3×3 matrix.

  - name: atom_positions
    path: run[0].system[-1].atoms.positions
    dtype: float[N][3]
    unit: m
    description: Cartesian positions of each atom.

  - name: atom_labels
    path: run[0].system[-1].atoms.labels
    dtype: str[N]
    unit: null
    description: Element symbol for each atom site.

  - name: periodicity
    path: run[0].system[-1].atoms.periodic
    dtype: bool[3]
    unit: null
    description: Periodicity along each lattice direction.

  - name: band_gap
    path: run[0].calculation[-1].band_gap[0].value
    dtype: float
    unit: J
    description: Electronic band gap. Zero for metals.

  - name: energy_free
    path: run[0].calculation[-1].energy.free.value
    dtype: float
    unit: J
    description: Free energy F = E - TS. Distinct from total energy at finite temperature.
"""


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


# --- Protocol conformance ---


def test_parsers_satisfy_protocol() -> None:
    assert isinstance(NomadParser(), Parser)


# --- NOMAD parser ---


@pytest.fixture
def nomad_path(tmp_path: Path) -> Path:
    path = tmp_path / "nomad_schema.yaml"
    path.write_text(INLINE_SCHEMA)
    return path


@pytest.fixture
def nomad_schema(nomad_path: Path) -> SchemaDefinition:
    return NomadParser().parse(nomad_path)


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
    assert f.semantic_type is None
    assert f.per_atom is None
    assert f.shape is None
    assert f.multivalued is False


def test_nomad_energy_total_per_atom(nomad_schema: SchemaDefinition) -> None:
    f = _get(nomad_schema, "energy_total_per_atom")
    assert f.per_atom is None
    assert f.semantic_type is None


def test_nomad_band_gap(nomad_schema: SchemaDefinition) -> None:
    assert _get(nomad_schema, "band_gap").semantic_type is None


def test_nomad_lattice_vectors(nomad_schema: SchemaDefinition) -> None:
    f = _get(nomad_schema, "lattice_vectors")
    assert f.semantic_type is None
    assert f.shape == [3, 3]
    assert f.multivalued is True


def test_nomad_atom_positions(nomad_schema: SchemaDefinition) -> None:
    f = _get(nomad_schema, "atom_positions")
    assert f.semantic_type is None
    assert f.coordinate_frame is None
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


def test_parser_accepts_str_path(nomad_path: Path) -> None:
    schema = NomadParser().parse(str(nomad_path))
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


def test_explicit_facets_survive_loading(tmp_path: Path) -> None:
    from schematerial.loading import load_schema

    path = tmp_path / "explicit.yaml"
    path.write_text('''name: explicit
version: "2"
fields:
  - name: energy
    path: A.energy
    dtype: float
    facets:
      semantic_type: unfamiliar:Energy
      coordinate_frame: fractional
      per_atom: false
      spin_channel: 0
      unit_normalized: J
''')
    loaded = load_schema(NomadParser(), path, "nomadsim")
    facets = read_facets(attributes_of(class_of(loaded.schema, "Root"))["energy"])
    assert facets.semantic_type == "unfamiliar:Energy"
    assert facets.coordinate_frame == CoordinateFrame.fractional
    assert facets.per_atom is False
    assert facets.spin_channel == 0
    assert facets.unit_normalized == "J"
    assert loaded.snapshots["nomadsim:Root.energy"].semantic_type == "unfamiliar:Energy"
    assert loaded.snapshots["nomadsim:Root.energy"].source_version == "2"


def test_duplicate_fields_report_both_source_paths(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.yaml"
    path.write_text('''name: duplicate
fields:
  - {name: energy, path: A.energy, dtype: float}
  - {name: energy, path: B.energy, dtype: int}
''')
    with pytest.raises(ValueError, match="A.energy.*B.energy"):
        NomadParser().parse(path)
