from pydantic import BaseModel


class TransformOp(BaseModel):
    op: str = ""


class UnitConversionOp(TransformOp):
    op: str = "unit_conversion"
    from_unit: str
    to_unit: str
    factor: float | None = None


class PerAtomRescaleOp(TransformOp):
    op: str = "per_atom_rescale"
    direction: str


class SplitOp(TransformOp):
    op: str = "split"
    source_field: str
    target_fields: list[str]


class MergeOp(TransformOp):
    op: str = "merge"
    source_fields: list[str]
    target_field: str


class ArrayIndexOp(TransformOp):
    op: str = "array_index"
    index: int


class EnumRemapOp(TransformOp):
    op: str = "enum_remap"
    mapping: dict[str, str]


class ConditionalOp(TransformOp):
    op: str = "conditional"
    condition: str
