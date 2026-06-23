from pydantic import BaseModel


class TransformOp(BaseModel):
    ...


class UnitConversionOp(TransformOp):
    from_unit: str
    to_unit: str


class PerAtomRescaleOp(TransformOp):
    direction: str


class SplitOp(TransformOp):
    source_field: str
    target_fields: list[str]


class MergeOp(TransformOp):
    source_fields: list[str]
    target_field: str


class ArrayIndexOp(TransformOp):
    index: int


class EnumRemapOp(TransformOp):
    mapping: dict[str, str]


class ConditionalOp(TransformOp):
    condition: str
