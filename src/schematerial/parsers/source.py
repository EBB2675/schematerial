"""What every source adapter produces, independent of which source it reads.

An adapter turns one validated extraction document into a canonical schema, a
verified materialisation behind the cache, the snapshots taken from it, and the
diagnostics raised while converting. Anything that consumes an import -- the
preview server today, the aligner later -- depends on this shape and on nothing
that names a particular source package.

The element identifiers an adapter writes carry its own source prefix from
decision 1. Consumers read that prefix back off the import rather than
assuming one, so a second source does not need a second consumer.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from linkml_runtime.linkml_model.meta import SchemaDefinition

from schematerial.loading import LoadedSchema

__all__ = ["SchemaImport", "SchemaImportError", "SourceAdapter"]


class SchemaImportError(ValueError):
    """Import cannot be presented as a faithful schema; diagnostics remain available.

    Raised instead of returning a partial schema: an import nobody has vouched
    for must not reach a consumer looking complete. The report survives on the
    exception so a caller can still show what was found.
    """

    def __init__(self, message: str, report: list[dict[str, str]] | None = None) -> None:
        self.report = tuple(report or ())
        super().__init__(message)


@runtime_checkable
class SchemaImport(Protocol):
    """One converted document. Read-only: an import is a result, not a workspace."""

    @property
    def schema(self) -> SchemaDefinition:
        """The local canonical schema, with declarations and native inheritance."""
        ...

    @property
    def loaded(self) -> LoadedSchema:
        """The verified materialisation and the snapshots taken from it."""
        ...

    @property
    def cache_key(self) -> str:
        """The materialisation cache key this import prepared."""
        ...

    @property
    def report(self) -> tuple[dict[str, str], ...]:
        """Conversion diagnostics, each naming the path it concerns."""
        ...

    def to_yaml(self) -> str:
        """Portable canonical YAML with the pinned toolchain in its header."""
        ...


@runtime_checkable
class SourceAdapter(Protocol):
    """Reads extraction JSON only. No adapter imports a source package."""

    def convert(self, document: dict[str, Any]) -> SchemaImport: ...
