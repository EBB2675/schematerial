from datetime import UTC, datetime
from enum import StrEnum
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from typing import Any, Self

from pydantic import BaseModel, Field, model_validator


def _schematerial_version() -> str:
    try:
        return _pkg_version("schematerial")
    except PackageNotFoundError:
        return "unknown"


class MappingRelation(StrEnum):
    EXACT = "exact"
    CLOSE = "close"
    BROADER = "broader"
    NARROWER = "narrower"
    UNIT_CONVERSION = "unit_conversion"
    PER_ATOM_RESCALE = "per_atom_rescale"
    SPLIT = "split"
    MERGE = "merge"
    DERIVED = "derived"
    AMBIGUOUS = "ambiguous"
    NONE = "none"


class MappingStatus(StrEnum):
    AUTO_ACCEPTED = "auto_accepted"      # score >= 0.85
    NEEDS_REVIEW = "needs_review"        # 0.40 <= score < 0.85
    LIKELY_NO_MATCH = "likely_no_match"  # score < 0.40


class MappingCandidate(BaseModel):
    id: str = ""
    source_field: str
    source_path: str | None = None
    target_field: str
    target_path: str | None = None
    relation: MappingRelation
    score: float | None = None
    scores: dict[str, float] = Field(default_factory=dict)
    status: MappingStatus = MappingStatus.NEEDS_REVIEW
    evidence: list[str] = Field(default_factory=list)
    context_note: str | None = None
    transform: dict[str, Any] | None = None
    review_note: str | None = None

    @model_validator(mode="after")
    def _derive_status_from_score(self) -> Self:
        if self.score is None:
            return self
        if self.score >= 0.85:
            self.status = MappingStatus.AUTO_ACCEPTED
        elif self.score >= 0.40:
            self.status = MappingStatus.NEEDS_REVIEW
        else:
            self.status = MappingStatus.LIKELY_NO_MATCH
        return self


class CrosswalkMetadata(BaseModel):
    source_model: str
    source_version: str | None = None
    target_model: str
    target_version: str | None = None
    schematerial_version: str = Field(default_factory=_schematerial_version)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    review_status: str = "draft"
    n_accepted: int = 0
    n_needs_review: int = 0
    n_no_match: int = 0


class CrosswalkResult(BaseModel):
    metadata: CrosswalkMetadata
    mappings: list[MappingCandidate] = Field(default_factory=list)

    def get_mapping(self, source: str, target: str) -> MappingCandidate | None:
        for m in self.mappings:
            if m.source_field == source and m.target_field == target:
                return m
        return None
