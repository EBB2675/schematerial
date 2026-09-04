"""Invariants CI enforces. AGENTS.md: these rules are not self-enforcing.

Decision 11: no tool writes a mapping with accepted status, at any score.
Card 2: `grep` finds no `TransformOp` and no threshold constant in the tree.

Do not weaken these.
"""

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
        f"transformations become linkml-map in Card 18. Found {banned!r}:\n" + "\n".join(hits)
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


@pytest.mark.parametrize("package", ["nomad", "emmet", "bam_masterdata", "optimade"])
def test_no_source_package_is_imported(package: str) -> None:
    hits = [
        hit for hit in _grep(f"import {package}") if not hit.startswith("tests/test_invariants.py")
    ]
    assert hits == [], (
        f"decision 8: {package!r} is never a dependency of the app. Found:\n" + "\n".join(hits)
    )
