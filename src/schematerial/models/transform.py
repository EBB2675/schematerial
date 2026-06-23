from typing import Literal

from pydantic import BaseModel


class TransformOp(BaseModel):
    ...


class UnitConversionOp(TransformOp):
    op: Literal["unit_conversion"] = "unit_conversion"
    from_unit: str
    to_unit: str
    factor: float | None = None


class PerAtomRescaleOp(TransformOp):
    op: Literal["per_atom_rescale"] = "per_atom_rescale"
    direction: str


class SplitOp(TransformOp):
    op: Literal["split"] = "split"
    source_field: str
    target_fields: list[str]


class MergeOp(TransformOp):
    op: Literal["merge"] = "merge"
    source_fields: list[str]
    target_field: str


class ArrayIndexOp(TransformOp):
    op: Literal["array_index"] = "array_index"
    index: int


class EnumRemapOp(TransformOp):
    op: Literal["enum_remap"] = "enum_remap"
    mapping: dict[str, str]


class ConditionalOp(TransformOp):
    op: Literal["conditional"] = "conditional"
    condition: str
