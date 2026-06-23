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
    source_path: str | None = None
    target_field: str
    target_path: str | None = None
    relation: MappingRelation
    confidence: float | None = None
    transform: dict[str, object] | None = None
    notes: str | None = None
