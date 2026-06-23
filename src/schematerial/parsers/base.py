from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from schematerial.models.ontology import OntologyModel
from schematerial.models.schema import SchemaModel


@runtime_checkable
class Parser(Protocol):
    """Parses a materials schema format into the internal SchemaModel IR."""

    def parse(self, source: str | Path) -> SchemaModel:
        ...


@runtime_checkable
class OntologyParser(Protocol):
    """Parses an OWL/TTL ontology into the internal OntologyModel IR (Mode B)."""

    def parse(self, source: str | Path) -> OntologyModel:
        ...
