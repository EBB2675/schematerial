"""Which adapter reads a document, decided by the source package it names.

`source.name` in an extraction document is the source distribution that was
read. It selects the adapter; nothing downstream branches on it again.
"""

from __future__ import annotations

from collections.abc import Callable

from schematerial.cache import MaterialisationCache
from schematerial.parsers.bam_json import BamAdapter
from schematerial.parsers.nomad_json import NomadAdapter
from schematerial.parsers.source import SchemaImportError, SourceAdapter

__all__ = ["ADAPTERS", "UnknownSourceError", "adapter_for"]

ADAPTERS: dict[str, Callable[[MaterialisationCache], SourceAdapter]] = {
    "bam-masterdata": BamAdapter,
    "nomad-simulations": NomadAdapter,
}
"""Source distribution name to the adapter that reads its extraction output.

A new source registers here and needs no change anywhere downstream.
"""


class UnknownSourceError(SchemaImportError):
    """A document from a source package no adapter reads.

    A `SchemaImportError`, so a caller that already reports refused imports
    reports this one the same way instead of crashing on an unfamiliar source.
    """


def adapter_for(name: str, cache: MaterialisationCache) -> SourceAdapter:
    build = ADAPTERS.get(name)
    if build is None:
        known = ", ".join(sorted(ADAPTERS)) or "none"
        raise UnknownSourceError(
            f"no adapter reads source package {name!r}. Known sources: {known}."
        )
    return build(cache)
