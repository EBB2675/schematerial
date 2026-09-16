"""Invariants CI enforces. These rules are not self-enforcing.

No tool writes a mapping with accepted status, at any score, and `grep` finds no
`TransformOp` and no threshold constant in the tree.

Do not weaken these.
"""

import ast
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent

# AGENTS.md quotes the banned names in order to ban them. Everything else that
# is tracked is real code and is in scope.
DOC_EXEMPT = {"AGENTS.md"}


def _tracked_files() -> list[str]:
    listing = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [path for path in listing if path not in DOC_EXEMPT]


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


# --- no code path writes accepted status -------------------------------------


@pytest.mark.parametrize("banned", ["auto_accepted", "AUTO_ACCEPTED", "MappingStatus"])
def test_no_code_path_writes_accepted_status(banned: str) -> None:
    hits = [hit for hit in _grep(banned) if not hit.startswith("tests/test_invariants.py")]
    assert hits == [], (
        f"acceptance is a human act, no tool writes it. Found {banned!r}:\n"
        + "\n".join(hits)
    )


def test_no_status_is_derived_from_a_score() -> None:
    hits = [
        hit
        for hit in _grep("_derive_status_from_score")
        if not hit.startswith("tests/test_invariants.py")
    ]
    assert hits == [], "thresholds are a caller's concern, not a field on a record."


# --- no TransformOp, no threshold constant -----------------------------------


@pytest.mark.parametrize("banned", ["TransformOp", "UnitConversionOp", "PerAtomRescaleOp"])
def test_no_transform_op_survives(banned: str) -> None:
    hits = [hit for hit in _grep(banned) if not hit.startswith("tests/test_invariants.py")]
    assert hits == [], (
        f"transformations become a linkml-map side-car. Found {banned!r}:\n" + "\n".join(hits)
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


# --- no source package in the app's import graph -----------------------------


@pytest.mark.parametrize("package", ["nomad", "bam_masterdata"])
def test_no_source_package_is_imported(package: str) -> None:
    hits = [
        hit for hit in _grep(f"import {package}") if not hit.startswith("tests/test_invariants.py")
    ]
    assert hits == [], (
        f"{package!r} is never a dependency of the app. Found:\n" + "\n".join(hits)
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
            continue  # The extractor runner keeps these outside the app import graph.
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
    # A Literal type can describe imported review states; it cannot write one.
    tree = ast.parse(code)
    declarations = {
        id(child)
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "ReviewStatus"
        and isinstance(node.value, ast.Subscript)
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "Literal"
        for child in ast.walk(node.value)
    }
    return [node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and node.value == "accepted"
            and id(node) not in declarations]


def test_app_cannot_introduce_accepted_status_literals() -> None:
    for path in (REPO / "src" / "schematerial").rglob("*.py"):
        code = path.read_text()
        if path == REPO / "src/schematerial/web/human_review.py":
            tree = ast.parse(code)
            allowed = set()
            for node in ast.walk(tree):
                if (isinstance(node, ast.FunctionDef)
                        and node.name in {"create_manual", "review_manual"}):
                    # Every accepting route must authorize before inspecting or writing data.
                    assert ast.unparse(node.body[0]) == "authorize(request)"
                    allowed.update(child.lineno for child in ast.walk(node)
                                   if isinstance(child, ast.Constant) and child.value == "accepted")
            assert set(accepted_literals(code)) == allowed
        else:
            assert accepted_literals(code) == [], str(path)


@pytest.mark.parametrize("code", [
    'row.status = "accepted"',
    'write(status="accepted")',
    'row = {"status": "accepted"}',
])
def test_acceptance_guard_catches_writes(code: str) -> None:
    assert accepted_literals(code)



# --- the read-only preview needs no matcher, model or network client ---------

# Nothing in this list exists to be turned off at runtime: the preview must not
# be able to reach a matcher, an embedding index or the network at all.
BANNED_IN_WEB = {
    "schematerial.agents",
    "schematerial.embeddings",
    "schematerial.semantics",
    "anthropic",
    "openai",
    "requests",
    "httpx",
    "httpx2",
    "aiohttp",
    "urllib.request",
}


def module_imports(code: str) -> list[str]:
    """Every module name a file imports, including the dynamic forms."""
    found: list[str] = []
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level:
            module = node.module or ""
            found.append(module)
            found.extend(f"{module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call) and node.args:
            function = node.func
            dynamic = (isinstance(function, ast.Name) and function.id == "__import__") or (
                isinstance(function, ast.Attribute) and function.attr == "import_module"
            )
            if dynamic and isinstance(node.args[0], ast.Constant):
                found.append(str(node.args[0].value))
    return found


def test_web_layer_imports_no_matcher_model_or_network_client() -> None:
    root = REPO / "src" / "schematerial"
    paths = [*(root / "web").rglob("*.py"), *(root / "ontologies").rglob("*.py")]
    for path in paths:
        for module in module_imports(path.read_text()):
            offending = [
                banned
                for banned in BANNED_IN_WEB
                if module == banned or module.startswith(f"{banned}.")
            ]
            assert offending == [], f"{path}: the preview must not import {module!r}"


@pytest.mark.parametrize("code", [
    "import httpx",
    "from schematerial.agents import matcher",
    "from schematerial.embeddings import index",
    'importlib.import_module("openai")',
])
def test_web_import_guard_catches_the_banned_forms(code: str) -> None:
    assert any(
        module == banned or module.startswith(f"{banned}.")
        for module in module_imports(code)
        for banned in BANNED_IN_WEB
    )


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


# Store methods that can record a human decision, accepted status included.
HUMAN_WRITES = {"add_reviewed", "review"}


def human_writes(code: str) -> list[str]:
    return [node.func.attr for node in ast.walk(ast.parse(code))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in HUMAN_WRITES]


def test_only_web_app_installs_human_review_and_no_tool_uses_private_transactions() -> None:
    root = REPO / "src" / "schematerial"
    for path in root.rglob("*.py"):
        code = path.read_text()
        if path != root / "web" / "app.py" and path != root / "web" / "human_review.py":
            assert "human_review" not in code, str(path)
            assert "install_review" not in code, str(path)
        if path not in {root / "web" / "human_review.py", root / "mappings" / "store.py"}:
            assert "_transaction" not in code, str(path)
            assert human_writes(code) == [], f"{path}: only the review boundary records decisions"


@pytest.mark.parametrize("code", [
    "store.add_reviewed(row)",
    'MappingStore(path).review("urn:uuid:x", review_status=status)',
])
def test_human_write_guard_catches_calls(code: str) -> None:
    assert human_writes(code)
