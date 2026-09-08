"""Exercise the extraction boundary without installed source packages."""

import json
import os
import venv
from pathlib import Path
from typing import Any

import pytest

from schematerial.extraction.contract import ContractError, read_document, validate_document
from schematerial.extraction.runner import ExtractorEnvironment, ExtractorError, run_extractor

FAKE = Path(__file__).parents[2] / "src/schematerial/extractors/fake.py"


@pytest.fixture
def document() -> dict[str, Any]:
    return {
        "contract_version": "1.0",
        "source": {"name": "fixture", "version": "1", "module": "fixture.sample"},
        "classes": [
            {"id": "Base", "name": "Base", "bases": [], "attributes": []},
            {"id": "Sample", "name": "Sample", "bases": ["Base"], "attributes": [
                {"name": "positions", "kind": "quantity",
                 "range": {"kind": "datatype", "name": "numpy.float64"},
                 "unit": "m", "shape": ["n_atoms", 3]},
                {"name": "child", "kind": "subsection", "repeats": True,
                 "range": {"kind": "class", "name": "Base"}},
                {"name": "state", "kind": "property",
                 "range": {"kind": "enum", "name": "State"},
                 "annotations": {"property_code": "STATE", "data_type": "CONTROLLEDVOCABULARY"}},
            ]},
        ],
        "enums": [{"id": "State", "values": ["solid", "liquid"]}],
        "report": [{"path": "Optional", "status": "skipped", "reason": "fixture omission"}],
    }


@pytest.fixture(scope="module")
def environment(tmp_path_factory: pytest.TempPathFactory) -> ExtractorEnvironment:
    directory = tmp_path_factory.mktemp("extractor-env")
    venv.EnvBuilder(with_pip=False).create(directory)
    interpreter = directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return ExtractorEnvironment("fixture-only", interpreter)


def test_fake_extractor_validates_in_separate_environment(
    environment: ExtractorEnvironment, document: dict[str, Any], tmp_path: Path,
) -> None:
    # This interpreter has only stdlib: no source packages or application dependencies.
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import importlib.util\n"
        "assert all(importlib.util.find_spec(name) is None for name in "
        "('nomad', 'nomad_simulations', 'bam_masterdata', 'schematerial', 'linkml_runtime'))\n"
        + FAKE.read_text()
    )
    result = run_extractor(environment, probe, input_text=json.dumps(document))
    assert result == document
    assert result["classes"][1]["attributes"][0]["shape"] == ["n_atoms", 3]


def test_fake_extractor_itself(environment: ExtractorEnvironment, document: dict[str, Any]) -> None:
    assert run_extractor(environment, FAKE, input_text=json.dumps(document)) == document


def test_missing_environment_is_named(tmp_path: Path) -> None:
    with pytest.raises(ExtractorError, match="missing-nomad.*interpreter"):
        run_extractor(ExtractorEnvironment("missing-nomad", tmp_path / "absent/python"), FAKE)


def test_malformed_attribute_reports_path(document: dict[str, Any]) -> None:
    document["classes"][1]["attributes"][0]["shape"] = [True]
    with pytest.raises(ContractError, match=r"classes\[1\].attributes\[0\].shape\[0\]"):
        validate_document(document)


@pytest.mark.parametrize("change,match", [
    ("version", "contract_version"),
    ("reference", "range.name"),
    ("duplicate", "duplicate identifier"),
    ("base", "bases"),
    ("repeat", "requires class range and repeats"),
])
def test_invalid_contract_semantics(document: dict[str, Any], change: str, match: str) -> None:
    if change == "version":
        document["contract_version"] = "2.0"
    elif change == "reference":
        document["classes"][1]["attributes"][1]["range"]["name"] = "Missing"
    elif change == "duplicate":
        document["classes"].append(document["classes"][0])
    elif change == "base":
        document["classes"][1]["bases"] = ["Missing"]
    else:
        del document["classes"][1]["attributes"][1]["repeats"]
    with pytest.raises(ContractError, match=match):
        validate_document(document)


def upgrade(document: dict[str, Any], version: str) -> dict[str, Any]:
    """Add what a version requires, so only the field under test differs."""
    document["contract_version"] = version
    document["source"]["dependencies"] = {"pydantic": "2.13.5"}
    for row in document["classes"]:
        row["effective_attributes"] = [
            {"name": item["name"], "kind": item["kind"], "declaring_class_id": row["id"]}
            for item in row["attributes"]
        ]
    return document


def test_class_annotations_and_labelled_enum_values_need_version_1_2(
    document: dict[str, Any],
) -> None:
    upgrade(document, "1.2")
    document["classes"][1]["annotations"] = {"code": "SAMPLE", "auto_generate_codes": True}
    document["enums"][0]["values"] = [
        "solid", {"value": "liquid", "title": "Liquid", "description": "A liquid",
                  "annotations": {"official": True}},
    ]
    assert validate_document(document) is document
    # The same document at 1.1 must not pass: an older version keeps its meaning.
    document["contract_version"] = "1.1"
    with pytest.raises(ContractError, match=r"\$\.(classes|enums)"):
        validate_document(document)


@pytest.mark.parametrize("version", ["1.0", "1.1"])
def test_earlier_versions_still_forbid_the_1_2_additions(
    document: dict[str, Any], version: str,
) -> None:
    if version == "1.1":
        upgrade(document, version)
    document["classes"][0]["annotations"] = {"code": "BASE"}
    with pytest.raises(ContractError, match=r"\$\.classes\[0\]"):
        validate_document(document)


def test_an_enum_value_is_named_once_however_it_is_written(document: dict[str, Any]) -> None:
    upgrade(document, "1.2")
    document["enums"][0]["values"] = ["solid", {"value": "solid", "title": "Solid"}]
    with pytest.raises(ContractError, match=r"\$\.enums\[0\].values\[1\]: duplicate"):
        validate_document(document)


@pytest.mark.parametrize("content", ['{"a":1,"a":2}', '{"a":NaN}', '{"a":1e999}', 'not json'])
def test_invalid_json_is_rejected(content: str) -> None:
    with pytest.raises(ContractError):
        read_document(content)


def test_runner_rejects_malformed_output(environment: ExtractorEnvironment, tmp_path: Path) -> None:
    script = tmp_path / "bad.py"
    script.write_text("print('{}')")
    with pytest.raises(ContractError, match="required property"):
        run_extractor(environment, script)


def test_runner_reports_failure_and_timeout(
    environment: ExtractorEnvironment, tmp_path: Path,
) -> None:
    script = tmp_path / "fail.py"
    script.write_text("import sys; print('reader failed', file=sys.stderr); sys.exit(2)")
    with pytest.raises(ExtractorError, match="fixture-only.*exit 2.*reader failed"):
        run_extractor(environment, script)
    script.write_text("import time; time.sleep(10)")
    with pytest.raises(ExtractorError, match="fixture-only.*timed out"):
        run_extractor(environment, script, timeout=0.05)
