from pydantic import BaseModel


class AnnotationEntry(BaseModel):
    field: str
    pmdco_concept: str | None = None
    emmo_concept: str | None = None
    qudt_unit: str | None = None
    match_type: str | None = None
    confidence: float | None = None


class AnnotationMap(BaseModel):
    schema_name: str
    entries: list[AnnotationEntry] = []
