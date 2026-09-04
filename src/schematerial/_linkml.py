"""Typed accessors over the LinkML metamodel dataclasses.

LinkML declares its collection slots as wide unions -- `classes` is a dict *or*
a list of dicts *or* a list of ClassDefinitions -- because `__post_init__`
accepts all of those and normalises them. After construction the normalised
form is always a dict keyed by name, but the declared type still says otherwise,
so every read of one is a type error.

These functions do the narrowing once, here, with the reason written down, so
that the code reading a schema does not carry a cast on every line.
"""

from __future__ import annotations

from typing import cast

from linkml_runtime.linkml_model.annotations import Annotation
from linkml_runtime.linkml_model.meta import (
    ClassDefinition,
    Element,
    SchemaDefinition,
    SlotDefinition,
)

__all__ = [
    "add_attribute",
    "add_class",
    "annotations_of",
    "attributes_of",
    "class_of",
    "classes_of",
    "instantiates_of",
    "set_annotation",
    "slots_of",
]


def _container(value: object) -> object:
    """The live container, never a substitute.

    `or {}` would hand back a fresh dict whenever the real one is empty, and a
    write through it would be silently lost. An empty container is still the
    container.
    """
    return {} if value is None else value


def classes_of(schema: SchemaDefinition) -> dict[str, ClassDefinition]:
    return cast("dict[str, ClassDefinition]", _container(schema.classes))


def slots_of(schema: SchemaDefinition) -> dict[str, SlotDefinition]:
    return cast("dict[str, SlotDefinition]", _container(schema.slots))


def attributes_of(class_definition: ClassDefinition) -> dict[str, SlotDefinition]:
    return cast("dict[str, SlotDefinition]", _container(class_definition.attributes))


def annotations_of(element: Element) -> dict[str, Annotation]:
    return cast("dict[str, Annotation]", _container(getattr(element, "annotations", None)))


def instantiates_of(element: Element) -> list[str]:
    """`instantiates` is declared as a scalar-or-list; after construction it is
    a list. Mutating the returned list mutates the element, which is what
    `write_facets` relies on."""
    value = getattr(element, "instantiates", None)
    if value is None:
        return []
    return cast("list[str]", value)


def class_of(schema: SchemaDefinition, name: str) -> ClassDefinition:
    """Return one normalised class, raising the usual ``KeyError`` if absent."""
    return classes_of(schema)[name]


def set_annotation(element: Element, tag: str, value: str) -> None:
    """Write one annotation. The same narrowing as `annotations_of`, for writes."""
    annotations_of(element)[tag] = Annotation(tag=tag, value=value)


def add_class(schema: SchemaDefinition, class_definition: ClassDefinition) -> None:
    classes_of(schema)[str(class_definition.name)] = class_definition


def add_attribute(class_definition: ClassDefinition, attribute: SlotDefinition) -> None:
    attributes_of(class_definition)[str(attribute.name)] = attribute
