from enum import StrEnum

from pydantic import BaseModel


class MappingRelation(StrEnum):
    EXACT = "exact"
    CLOSE = "close"
    BROADER = "broader"
    NARROWER = "narrower"
    NONE = "none"


class MappingCandidate(BaseModel):
    source_field: str
    target_field: str
    relation: MappingRelation
    confidence: float | None = None
    notes: str | None = None
