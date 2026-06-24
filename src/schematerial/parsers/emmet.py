from pathlib import Path

from schematerial.models.schema import SchemaModel
from schematerial.parsers._yaml_base import parse_yaml_schema


class EmmetParser:
    """Parses Emmet (Materials Project) schema fixtures into SchemaModel."""

    def parse(self, source: str | Path) -> SchemaModel:
        return parse_yaml_schema(source, format="emmet")
