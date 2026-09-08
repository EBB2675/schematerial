"""Invariants CI enforces. AGENTS.md: these rules are not self-enforcing.

Decision 11: no tool writes a mapping with accepted status, at any score.
Card 2: `grep` finds no `TransformOp` and no threshold constant in the tree.

Do not weaken these.
"""

import ast
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent

# AGENTS.md and the decision records quote the banned names in order to ban
# them. Everything else is real code and is in scope.
DOC_EXEMPT = {"AGENTS.md"}
DOC_EXEMPT_DIRS = ("docs/decisions/",)


def _tracked_files() -> list[str]:
    listing = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [
        path for path in listing if path not in DOC_EXEMPT and not path.startswith(DOC_EXEMPT_DIRS)
    ]


def _grep(pattern: str) -> list[str]:
    """Every tracked file, other than the docs that quote the ban, matching."""
    hits: list[str] = []
    for path in _tracked_files():
        full = REPO / path
        try:
            text = full.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if pattern in line:
                hits.append(f"{path}:{number}: {line.strip()}")
    return hits


# --- decision 11: no code path writes accepted status ------------------------


@pytest.mark.parametrize("banned", ["auto_accepted", "AUTO_ACCEPTED", "MappingStatus"])
def test_no_code_path_writes_accepted_status(banned: str) -> None:
    hits = [hit for hit in _grep(banned) if not hit.startswith("tests/test_invariants.py")]
    assert hits == [], (
        f"decision 11: acceptance is a human act, no tool writes it. Found {banned!r}:\n"
        + "\n".join(hits)
    )


def test_no_status_is_derived_from_a_score() -> None:
    hits = [
        hit
        for hit in _grep("_derive_status_from_score")
        if not hit.startswith("tests/test_invariants.py")
    ]
    assert hits == [], "decision 11: thresholds are a caller's concern, not a field on a record."


# --- Card 2: no TransformOp, no threshold constant ---------------------------


@pytest.mark.parametrize("banned", ["TransformOp", "UnitConversionOp", "PerAtomRescaleOp"])
def test_no_transform_op_survives(banned: str) -> None:
    hits = [hit for hit in _grep(banned) if not hit.startswith("tests/test_invariants.py")]
    assert hits == [], (
        f"transformations become linkml-map in Card 19. Found {banned!r}:\n" + "\n".join(hits)
    )


@pytest.mark.parametrize("threshold", ["0.85", "0.40"])
def test_no_threshold_constant_survives(threshold: str) -> None:
    # Python source only. The same number appearing as a hand-written expert
    # confidence in the ground truth is a measurement, not a policy constant.
    hits = [hit for hit in _grep(threshold) if hit.endswith((".py",)) or ".py:" in hit]
    hits = [hit for hit in hits if not hit.startswith("tests/test_invariants.py")]
    assert hits == [], (
        f"the MappingStatus thresholds are deleted, not parameterised. Found {threshold!r}:\n"
        + "\n".join(hits)
    )


# --- decision 8: no source package in the app's import graph -----------------


@pytest.mark.parametrize("package", ["nomad", "bam_masterdata"])
def test_no_source_package_is_imported(package: str) -> None:
    hits = [
        hit for hit in _grep(f"import {package}") if not hit.startswith("tests/test_invariants.py")
    ]
    assert hits == [], (
        f"decision 8: {package!r} is never a dependency of the app. Found:\n" + "\n".join(hits)
    )


SOURCE_PACKAGES = {"nomad", "nomad_simulations", "nomad_measurements", "bam_masterdata"}


def source_imports(code: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(code)):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""] if not node.level else []
        elif isinstance(node, ast.Call) and node.args:
            function = node.func
            dynamic = (
                isinstance(function, ast.Name) and function.id == "__import__"
            ) or (
                isinstance(function, ast.Attribute) and function.attr == "import_module"
            )
            if dynamic and isinstance(node.args[0], ast.Constant):
                names = [str(node.args[0].value)]
        found.extend(name for name in names if name.split(".")[0] in SOURCE_PACKAGES)
    return found


def test_app_has_no_structural_source_imports() -> None:
    for path in (REPO / "src" / "schematerial").rglob("*.py"):
        if "extractors" in path.relative_to(REPO / "src" / "schematerial").parts:
            continue  # Card 5 runner must keep these outside the app import graph.
        assert source_imports(path.read_text()) == [], str(path)


@pytest.mark.parametrize("code", [
    "import nomad.metainfo as meta",
    "from nomad.metainfo import Section",
    "from bam_masterdata import datamodel",
    'importlib.import_module("nomad_simulations")',
    '__import__("nomad")',
])
def test_source_import_guard_catches_import_forms(code: str) -> None:
    assert source_imports(code)


def test_relative_adapter_import_is_allowed() -> None:
    assert source_imports("from .nomad import NomadParser") == []


def accepted_literals(code: str) -> list[int]:
    # Until Card 12 introduces a human boundary, no app module needs this value.
    # This is a structural tripwire, not a substitute for store behavior tests.
    return [node.lineno for node in ast.walk(ast.parse(code))
            if isinstance(node, ast.Constant) and node.value == "accepted"]


def test_app_cannot_introduce_accepted_status_literals() -> None:
    for path in (REPO / "src" / "schematerial").rglob("*.py"):
        assert accepted_literals(path.read_text()) == [], str(path)


@pytest.mark.parametrize("code", [
    'row.status = "accepted"',
    'write(status="accepted")',
    'row = {"status": "accepted"}',
])
def test_acceptance_guard_catches_writes(code: str) -> None:
    assert accepted_literals(code)



def test_app_cannot_import_extractor_modules() -> None:
    root = REPO / "src" / "schematerial"
    for path in root.rglob("*.py"):
        if "extractors" in path.relative_to(root).parts:
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or "", *[alias.name for alias in node.names]]
            elif isinstance(node, ast.Call) and node.args:
                if isinstance(node.args[0], ast.Constant):
                    fn = node.func
                    if ((isinstance(fn, ast.Name) and fn.id == "__import__") or
                            (isinstance(fn, ast.Attribute) and fn.attr == "import_module")):
                        modules = [str(node.args[0].value)]
            assert all("extractors" not in module.split(".") for module in modules), (
                f"{path}: extractor modules must run out of process"
            )
