from pathlib import Path

from linkml_runtime.linkml_model.meta import SchemaDefinition

from schematerial.parsers._yaml_base import parse_yaml_schema


class OptimadeParser:
    """Parses OPTIMADE schema fixtures into a canonical LinkML schema."""

    def parse(self, source: str | Path) -> SchemaDefinition:
        return parse_yaml_schema(source, format="optimade")
