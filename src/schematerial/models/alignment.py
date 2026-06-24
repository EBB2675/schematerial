from enum import StrEnum

from pydantic import BaseModel

from schematerial.models.crosswalk import CrosswalkResult


class AlignmentMode(StrEnum):
    SCHEMA_TO_SCHEMA = "schema_to_schema"
    SCHEMA_TO_ONTOLOGY = "schema_to_ontology"


class AlignmentResult(BaseModel):
    mode: AlignmentMode
    crosswalk: CrosswalkResult
