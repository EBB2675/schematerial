from typing import Literal

from pydantic import BaseModel, Field


class OntologyTerm(BaseModel):
    """A grounding of a schema field to a specific ontology concept."""

    uri: str
    label: str
    ontology: str  # "EMMO", "MatOnto", "QUDT"
    match_type: Literal["exact", "partial", "ancestor", "inferred"]
    confidence: float


class OntologyConcept(BaseModel):
    uri: str
    label: str | None = None
    description: str | None = None
    parent_uri: str | None = None


class OntologyModel(BaseModel):
    name: str
    namespace: str | None = None
    concepts: list[OntologyConcept] = Field(default_factory=list)
