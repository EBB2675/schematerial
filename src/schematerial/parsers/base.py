from pathlib import Path
from typing import Protocol, runtime_checkable

from linkml_runtime.linkml_model.meta import SchemaDefinition

from schematerial.semantics.ontology import OntologyModel


@runtime_checkable
class Parser(Protocol):
    """Converts a schema source file into the canonical LinkML SchemaDefinition."""

    def parse(self, source: str | Path) -> SchemaDefinition: ...


@runtime_checkable
class OntologyParser(Protocol):
    """Converts an OWL/TTL ontology into the internal OntologyModel IR."""

    def parse(self, source: str | Path) -> OntologyModel: ...
