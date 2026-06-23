from pathlib import Path
from typing import Protocol, runtime_checkable

from schematerial.models.ontology import OntologyModel
from schematerial.models.schema import SchemaModel


@runtime_checkable
class Parser(Protocol):
    """Converts a schema source file into the internal SchemaModel IR."""

    def parse(self, source: str | Path) -> SchemaModel:
        ...


@runtime_checkable
class OntologyParser(Protocol):
    """Converts an OWL/TTL ontology into the internal OntologyModel IR."""

    def parse(self, source: str | Path) -> OntologyModel:
        ...
