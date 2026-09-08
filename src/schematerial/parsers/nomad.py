from pathlib import Path

from linkml_runtime.linkml_model.meta import SchemaDefinition

from schematerial.parsers._yaml_base import parse_yaml_schema
from schematerial.parsers.nomad_json import NomadAdapter


class NomadParser:
    """Read extraction JSON; retain the original prototype YAML reader explicitly."""

    def __init__(self) -> None:
        self.adapter = NomadAdapter()

    def parse(self, source: str | Path) -> SchemaDefinition:
        if Path(source).suffix.lower() == ".json":
            return self.adapter.read(source).loaded.schema
        return parse_yaml_schema(source, format="nomad")
