"""Schema loading boundary: capture identity separately from the canonical IR."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from linkml_runtime.linkml_model.meta import SchemaDefinition

from schematerial.facets import validate_schema_facets
from schematerial.identity import ElementSnapshot, Source, snapshot_index

if TYPE_CHECKING:
    from schematerial.parsers.base import Parser


@dataclass(frozen=True)
class LoadedSchema:
    schema: SchemaDefinition
    snapshots: Mapping[str, ElementSnapshot]


def load_schema(parser: Parser, path: str | Path, source: str | Source) -> LoadedSchema:
    schema = parser.parse(path)
    validate_schema_facets(schema)
    return LoadedSchema(schema, snapshot_index(schema, source))
