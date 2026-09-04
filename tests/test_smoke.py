import json
from pathlib import Path

import pytest
import yaml

FIXTURES_DIR = Path(__file__).parent / "fixtures"

YAML_FIXTURES = [
    "nomad_schema.yaml",
    "optimade_schema.yaml",
    "emmet_schema.yaml",
    "cif_schema.yaml",
    "nomad_optimade_gt.yaml",
    "nomad_emmet_gt.yaml",
]

JSON_FIXTURES = [
    "nomad_entry.json",
    "optimade_entry.json",
    "emmet_entry.json",
    "cif_entry.json",
]


def test_import() -> None:
    import schematerial

    assert isinstance(schematerial.__version__, str)


def test_cli_main_exists() -> None:
    from schematerial.cli import main

    assert callable(main)


@pytest.mark.parametrize("name", YAML_FIXTURES)
def test_yaml_fixture_loads(name: str) -> None:
    path = FIXTURES_DIR / name
    assert path.exists(), f"Missing fixture file: {name}"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data is not None, f"{name} parsed as empty"


@pytest.mark.parametrize("name", JSON_FIXTURES)
def test_json_fixture_loads(name: str) -> None:
    path = FIXTURES_DIR / name
    assert path.exists(), f"Missing fixture file: {name}"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{name} did not parse to a dict"


def test_models_instantiate() -> None:
    from schematerial.models import CoordinateFrame, MaterialsFacets
    from schematerial.semantics import semantic_types

    facets = MaterialsFacets(
        semantic_type=semantic_types.ENERGY,
        coordinate_frame=CoordinateFrame.cartesian,
    )
    assert facets.semantic_type == "quantitykind:Energy"
    assert facets.per_atom is None
