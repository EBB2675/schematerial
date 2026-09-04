# DO NOT EDIT. Generated from schematerial_core.yaml by `uv run schematerial-schema`.
#
# Pinned versions this file was generated against (decision 9):
#   linkml==1.11.1
#   linkml-runtime==1.11.1
#   linkml-map==0.5.2
#   sssom==0.4.21

from __future__ import annotations

import re
import sys
from datetime import (
    date,
    datetime,
    time
)
from decimal import Decimal
from enum import Enum
from typing import (
    Any,
    ClassVar,
    Literal,
    Optional,
    Union
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer
)


metamodel_version = "1.11.0"
version = "None"


class ConfiguredBaseModel(BaseModel):
    model_config = ConfigDict(
        serialize_by_alias = True,
        validate_by_name = True,
        validate_assignment = True,
        validate_default = True,
        extra = "forbid",
        arbitrary_types_allowed = True,
        use_enum_values = True,
        strict = False,
    )





class LinkMLMeta(RootModel):
    root: dict[str, Any] = {}
    model_config = ConfigDict(frozen=True)

    def __getattr__(self, key:str):
        return getattr(self.root, key)

    def __getitem__(self, key:str):
        return self.root[key]

    def __setitem__(self, key:str, value):
        self.root[key] = value

    def __contains__(self, key:str) -> bool:
        return key in self.root


linkml_meta = LinkMLMeta({'default_prefix': 'smat',
     'default_range': 'string',
     'description': 'The metamodel extension that makes a LinkML schema carry '
                    'materials-science facets.\n'
                    '\n'
                    'The canonical representation of a source model is a plain '
                    'LinkML SchemaDefinition: sections become classes, quantities '
                    'become class-local attributes, a unit is written as a '
                    'ucum_code, a repeat is multivalued. None of that needs '
                    'redefining here, and this schema does not redefine it.\n'
                    '\n'
                    'What LinkML has no room for is the five facets of decision 4. '
                    'Assigning a non-metamodel slot to a schema element is an '
                    'error, and there is no way to add slots to SlotDefinition, so '
                    'the facets live in `annotations` and this class is what '
                    'governs them. An element carrying facets points at it through '
                    '`instantiates`, which is how a reader knows the annotations '
                    "are these annotations and not somebody else's.\n"
                    '\n'
                    'A facet with no value is absent. Every slot below is optional '
                    'and none has a default, because a default would be a guess '
                    'and decision 4 forbids guessing.',
     'id': 'https://w3id.org/schematerial/core',
     'imports': ['linkml:types'],
     'license': 'https://spdx.org/licenses/MIT.html',
     'name': 'schematerial_core',
     'prefixes': {'emmo': {'prefix_prefix': 'emmo',
                           'prefix_reference': 'https://w3id.org/emmo#'},
                  'linkml': {'prefix_prefix': 'linkml',
                             'prefix_reference': 'https://w3id.org/linkml/'},
                  'pmdco': {'prefix_prefix': 'pmdco',
                            'prefix_reference': 'https://w3id.org/pmd/co/'},
                  'quantitykind': {'prefix_prefix': 'quantitykind',
                                   'prefix_reference': 'http://qudt.org/vocab/quantitykind/'},
                  'qudt': {'prefix_prefix': 'qudt',
                           'prefix_reference': 'http://qudt.org/schema/qudt/'},
                  'smat': {'prefix_prefix': 'smat',
                           'prefix_reference': 'https://w3id.org/schematerial/core/'}},
     'source_file': '/home/eboydas/Desktop/develop/schematerial/src/schematerial/schema/schematerial_core.yaml',
     'title': 'schematerial canonical core'} )

class CoordinateFrame(str, Enum):
    """
    The frame a vector quantity is expressed in. There is no "none" member: an element with no frame carries no coordinate_frame facet.
    """
    cartesian = "cartesian"
    """
    Cartesian coordinates, in the units of the element.
    """
    fractional = "fractional"
    """
    Fractional coordinates of the lattice vectors.
    """
    reciprocal = "reciprocal"
    """
    Coordinates in reciprocal space.
    """



class MaterialsFacets(ConfiguredBaseModel):
    """
    The facets an element may carry, as annotations. Referenced from an element through `instantiates`.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'smat:MaterialsFacets',
         'from_schema': 'https://w3id.org/schematerial/core'})

    semantic_type: Optional[str] = Field(default=None, description="""What the element measures, as a CURIE into QUDT, EMMO or PMDco. Open: the value space is those vocabularies, never a local enum. Absent unless the source states one or a human has accepted a grounding.""", json_schema_extra = { "linkml_meta": {'domain_of': ['MaterialsFacets'], 'slot_uri': 'smat:semantic_type'} })
    coordinate_frame: Optional[CoordinateFrame] = Field(default=None, description="""The frame a vector quantity is expressed in. Absent for a quantity that has no frame, rather than a \"none\" member, because absent is what \"no frame\" means.""", json_schema_extra = { "linkml_meta": {'domain_of': ['MaterialsFacets'], 'slot_uri': 'smat:coordinate_frame'} })
    per_atom: Optional[bool] = Field(default=None, description="""True when the value is already divided by the number of atoms. Absent when the source does not say, which is not the same as false.""", json_schema_extra = { "linkml_meta": {'domain_of': ['MaterialsFacets'], 'slot_uri': 'smat:per_atom'} })
    spin_channel: Optional[int] = Field(default=None, description="""Which spin channel the value belongs to, when it is resolved by one. Absent for a spin-summed quantity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['MaterialsFacets'], 'slot_uri': 'smat:spin_channel'} })
    unit_normalized: Optional[str] = Field(default=None, description="""The UCUM code the element's stated unit normalises to. The raw unit stays where the source put it; this is the normalised form, and it is absent when normalisation was not possible.""", json_schema_extra = { "linkml_meta": {'domain_of': ['MaterialsFacets'], 'slot_uri': 'smat:unit_normalized'} })


# Model rebuild
# see https://pydantic-docs.helpmanual.io/usage/models/#rebuilding-a-model
MaterialsFacets.model_rebuild()
