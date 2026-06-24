from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from schematerial.models.ontology import OntologyTerm


class SemanticType(StrEnum):
    ENERGY = "energy"
    LENGTH = "length"
    FORCE = "force"
    STRESS = "stress"
    CHARGE = "charge"
    SPIN = "spin"
    TEMPERATURE = "temperature"
    PRESSURE = "pressure"
    BANDGAP = "band_gap"
    KPOINT = "k_point"
    ATOMIC_POSITION = "atomic_position"
    LATTICE_PARAMETER = "lattice_parameter"
    IDENTIFIER = "identifier"
    LABEL = "label"
    FLAG = "flag"
    UNKNOWN = "unknown"


class CoordinateFrame(StrEnum):
    CARTESIAN = "cartesian"
    FRACTIONAL = "fractional"
    RECIPROCAL = "reciprocal"
    NONE = "none"


class SchemaField(BaseModel):
    path: str
    label: str
    description: str | None = None
    datatype: str = "unknown"
    shape: list[int | None] | None = None
    unit: str | None = None
    unit_normalized: str | None = None
    cardinality: Literal["one", "many", "optional"] = "one"
    semantic_type: SemanticType = SemanticType.UNKNOWN
    coordinate_frame: CoordinateFrame = CoordinateFrame.NONE
    per_atom: bool = False
    per_unit_cell: bool = False
    spin_channel: int | None = None
    ontology_terms: list[OntologyTerm] = Field(default_factory=list)
    embedding: list[float] | None = None
    examples: list[Any] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    source_path_raw: str | None = None


class Entity(BaseModel):
    name: str
    description: str | None = None
    fields: list[SchemaField] = Field(default_factory=list)
    parent: str | None = None


class SchemaModel(BaseModel):
    name: str
    version: str | None = None
    format: str = "unknown"
    source_file: str | None = None
    entities: list[Entity] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
