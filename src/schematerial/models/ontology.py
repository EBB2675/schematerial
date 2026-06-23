from pydantic import BaseModel


class OntologyConcept(BaseModel):
    iri: str
    label: str | None = None
    description: str | None = None
    parent_iri: str | None = None


class OntologyModel(BaseModel):
    name: str
    namespace: str | None = None
    concepts: list[OntologyConcept] = []
