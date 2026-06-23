from pydantic import BaseModel


class Field(BaseModel):
    name: str
    path: str
    dtype: str | None = None
    unit: str | None = None
    description: str | None = None
    required: bool = False


class Entity(BaseModel):
    name: str
    fields: list[Field] = []
    description: str | None = None


class SchemaModel(BaseModel):
    name: str
    version: str | None = None
    entities: list[Entity] = []
    description: str | None = None
