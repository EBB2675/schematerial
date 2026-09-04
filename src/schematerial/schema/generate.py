"""Regenerate `models/` from the LinkML schema. The `schema` command.

`models/` is generated output. Nothing in it is hand-written and nothing in it
should be edited: change `schematerial_core.yaml` and run this.

Decision 9 pins the LinkML toolchain and records the pins in the header of every
generated file, which is what `_header` writes. The pins are read from the
installed environment rather than hard-coded, so a header can never disagree
with what actually produced the file.

Generating twice produces byte-identical output. gen-pydantic stamps no
timestamp, and this script adds none.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import sys
from pathlib import Path

from linkml.generators.pydanticgen import PydanticGenerator

SCHEMA_DIR = Path(__file__).parent
CORE_SCHEMA = SCHEMA_DIR / "schematerial_core.yaml"
MODELS_DIR = SCHEMA_DIR.parent / "models"
GENERATED = MODELS_DIR / "core.py"
PACKAGE_INIT = MODELS_DIR / "__init__.py"

# Decision 9 calls the metamodel `linkml-model`; its Python distribution is
# `linkml-runtime`. Query the distribution name importlib.metadata knows.
PINNED_DISTRIBUTIONS = ("linkml", "linkml-runtime", "linkml-map", "sssom")

BANNER = "DO NOT EDIT. Generated from schematerial_core.yaml by `uv run schematerial-schema`."


def _pins() -> list[str]:
    lines = []
    for distribution in PINNED_DISTRIBUTIONS:
        try:
            version = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:  # pragma: no cover
            version = "not installed"
        lines.append(f"#   {distribution}=={version}")
    return lines


def _header() -> str:
    return "\n".join(
        [
            f"# {BANNER}",
            "#",
            "# Pinned versions this file was generated against (decision 9):",
            *_pins(),
            "",
            "",
        ]
    )


_INIT_BODY = '''"""The generated view over the LinkML schema.

Nothing here is hand-written. Change `schema/schematerial_core.yaml` and run
`uv run schematerial-schema`.
"""

from linkml_runtime.linkml_model.meta import (
    ClassDefinition as Entity,
    SchemaDefinition as SchemaModel,
    SlotDefinition as SchemaField,
)

from schematerial.models.core import CoordinateFrame, MaterialsFacets

__all__ = [
    "CoordinateFrame",
    "Entity",
    "MaterialsFacets",
    "SchemaField",
    "SchemaModel",
]
'''


def render(schema: Path = CORE_SCHEMA) -> str:
    """Return the generated Pydantic view without changing the filesystem."""
    return _header() + PydanticGenerator(str(schema)).serialize()


def render_package_init() -> str:
    """Return the generated package exports without changing the filesystem.

    Card 2's ``SchemaModel``, ``Entity`` and ``SchemaField`` survive as names
    for LinkML's generated metamodel classes. They are aliases, not a second
    hand-written representation of a LinkML schema.
    """
    return _header() + _INIT_BODY


def generate(
    schema: Path = CORE_SCHEMA,
    target: Path = GENERATED,
    package_init: Path | None = None,
) -> str:
    """Generate the model package and return the main file's content.

    A custom target keeps all writes next to that target unless the caller
    explicitly supplies ``package_init``. Tests can therefore generate into a
    temporary directory without touching the working tree.
    """
    content = render(schema)
    package_init = target.parent / "__init__.py" if package_init is None else package_init
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    package_init.write_text(render_package_init(), encoding="utf-8")
    return content


def stale_generated_files() -> list[Path]:
    """Return stale generated paths without modifying either one."""
    expected = {
        GENERATED: render(),
        PACKAGE_INIT: render_package_init(),
    }
    return [
        path
        for path, content in expected.items()
        if not path.exists() or path.read_text(encoding="utf-8") != content
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the generated file is not what regenerating would produce",
    )
    args = parser.parse_args()

    if args.check:
        stale = stale_generated_files()
        if stale:
            joined = ", ".join(str(path) for path in stale)
            print(
                f"Generated files are stale: {joined}. Run `uv run schematerial-schema`.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        print("Generated model package is up to date.")
        return

    generate()
    print(f"Wrote {GENERATED}")


if __name__ == "__main__":
    main()
