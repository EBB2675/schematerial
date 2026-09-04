"""The side index embeddings live in. Decision 10.

`embedding` used to be a field on `SchemaField`. Decision 10 bans it from the
core IR: the materialisation cache in Card 4 keys on a content hash over the
schema, and a vector on an element makes that key move whenever a model is
re-run. So vectors live here instead, keyed by element id, and an element
serialises to no vector data at all.

The index is deliberately dumb -- a mapping and nothing else. Whether it is
backed by a file, a vector database or nothing at all is a caller's problem, and
none of it belongs in the IR.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence

from schematerial.identity import parse_element_id

__all__ = ["EmbeddingIndex"]


class EmbeddingIndex:
    """Vectors keyed by element id, held apart from the elements themselves."""

    def __init__(self, vectors: Mapping[str, Sequence[float]] | None = None) -> None:
        self._vectors: dict[str, tuple[float, ...]] = {}
        for element_id, vector in (vectors or {}).items():
            self.set(element_id, vector)

    def set(self, element_id: str, vector: Sequence[float]) -> None:
        """Store a vector. The id is parsed, so a malformed key cannot enter."""
        parse_element_id(element_id)
        self._vectors[element_id] = tuple(float(value) for value in vector)

    def get(self, element_id: str) -> tuple[float, ...] | None:
        return self._vectors.get(element_id)

    def __contains__(self, element_id: object) -> bool:
        return element_id in self._vectors

    def __len__(self) -> int:
        return len(self._vectors)

    def __iter__(self) -> Iterator[str]:
        return iter(self._vectors)
