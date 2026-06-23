from __future__ import annotations

from enum import Enum


class AlignmentMode(Enum):
    SCHEMA_TO_SCHEMA = "schema_to_schema"
    SCHEMA_TO_ONTOLOGY = "schema_to_ontology"
