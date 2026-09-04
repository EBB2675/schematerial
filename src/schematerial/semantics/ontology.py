"""Ontology records. App records, deliberately not part of the LinkML core.

`OntologyTerm` is a *grounding proposal*: a URI, a match type and a confidence.
Decision 11 makes that a suggestion rather than a fact, and Card 14 is what
produces it. A proposal with a confidence is not schema structure, so it does
not go in the core and it is no longer a field on `SchemaField`; the core
carries only an accepted `semantic_type` CURIE in annotations, per decision 4.

It lives outside `models/` because Card 3 makes `models/` generated output.
"""

from typing import Literal

from pydantic import BaseModel, Field


class OntologyTerm(BaseModel):
    """A proposed grounding of a schema element to an ontology concept.

    Never written onto an element. Card 14 emits these; acceptance is a human
    act (decision 11), and what acceptance writes is a `semantic_type` CURIE.
    """

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
