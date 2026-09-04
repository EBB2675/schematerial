# DO NOT EDIT. Generated from schematerial_core.yaml by `uv run schematerial-schema`.
#
# Pinned versions this file was generated against (decision 9):
#   linkml==1.11.1
#   linkml-runtime==1.11.1
#   linkml-map==0.5.2
#   sssom==0.4.21

"""The generated view over the LinkML schema.

Nothing here is hand-written. Change `schema/schematerial_core.yaml` and run
`uv run schematerial-schema`.
"""

from linkml_runtime.linkml_model.meta import (
    ClassDefinition as Entity,
    SchemaDefinition as SchemaModel,
    SlotDefinition as SchemaField,
)

from schematerial.models.core import CoordinateFrame, MaterialsFacets

__all__ = [
    "CoordinateFrame",
    "Entity",
    "MaterialsFacets",
    "SchemaField",
    "SchemaModel",
]
