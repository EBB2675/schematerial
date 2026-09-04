from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CoordinateFrame(StrEnum):
    CARTESIAN = "cartesian"
    FRACTIONAL = "fractional"
    RECIPROCAL = "reciprocal"
    NONE = "none"


class SchemaField(BaseModel):
    # Decision 10 keeps vectors and other volatile data out of the core IR,
    # because the Card 4 cache keys on a content hash over it. Forbidding
    # extras is what stops one being reattached by accident.
    model_config = ConfigDict(extra="forbid")

    path: str
    label: str
    description: str | None = None
    datatype: str = "unknown"
    shape: list[int | None] | None = None
    unit: str | None = None
    unit_normalized: str | None = None
    cardinality: Literal["one", "many", "optional"] = "one"

    semantic_type: str | None = None
    """A CURIE into QUDT, EMMO or PMDco (decision 4). Open: any CURIE is valid
    and is carried verbatim. Absent when the source does not state one --
    decision 4's 'a facet with no value is absent, not guessed'. Convenience
    aliases over real CURIEs live in `schematerial.semantics.semantic_types`."""

    coordinate_frame: CoordinateFrame = CoordinateFrame.NONE
    per_atom: bool = False
    per_unit_cell: bool = False
    spin_channel: int | None = None
    examples: list[Any] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    source_path_raw: str | None = None


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    fields: list[SchemaField] = Field(default_factory=list)
    parent: str | None = None


class SchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str | None = None
    format: str = "unknown"
    source_file: str | None = None
    entities: list[Entity] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
