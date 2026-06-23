from pydantic import BaseModel, Field


class SchemaField(BaseModel):
    name: str
    path: str
    dtype: str | None = None
    unit: str | None = None
    description: str | None = None
    required: bool = False


class Entity(BaseModel):
    name: str
    fields: list[SchemaField] = Field(default_factory=list)
    description: str | None = None


class SchemaModel(BaseModel):
    name: str
    version: str | None = None
    entities: list[Entity] = Field(default_factory=list)
    description: str | None = None
