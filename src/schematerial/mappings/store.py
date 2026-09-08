"""Persistent SSSOM/TSV correspondence rows, independent of loaded schemas.

Public automated writes can only suggest or reject. Human acceptance is supplied
by the web review boundary. All transactions preserve existing rows.
"""
from __future__ import annotations

import csv
import fcntl
import io
import os
import tempfile
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Literal
from uuid import uuid4

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from schematerial.identity import ElementSnapshot, parse_element_id

CURIE_MAP = {
    **{p: f"https://w3id.org/schematerial/{p}/" for p in ("nomadsim", "nomadmeas", "bammd")},
    "smat": "https://w3id.org/schematerial/core/",
    "pmdco": "https://w3id.org/pmd/co/",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "semapv": "https://w3id.org/semapv/vocab/",
    "orcid": "https://orcid.org/",
}
Predicate = Literal[
    "skos:exactMatch", "skos:closeMatch", "skos:relatedMatch",
    "skos:narrowMatch", "skos:broadMatch",
]
ReviewStatus = Literal["suggested", "accepted", "rejected"]
EXTENSIONS = [
    {"slot_name": name, "property": f"smat:{name}",
     "type_hint": "http://www.w3.org/2001/XMLSchema#string"}
    for name in ("review_status", "subject_snapshot", "object_snapshot", "supersedes")
]


def reference(value: str) -> str:
    if not value or ":" not in value or any(c.isspace() for c in value):
        raise ValueError("expected a URI or declared CURIE")
    prefix = value.split(":", 1)[0]
    if prefix not in CURIE_MAP and prefix not in {"https", "http", "urn"}:
        raise ValueError(f"undeclared CURIE prefix: {prefix}")
    if not value.split(":", 1)[1]:
        raise ValueError("empty URI reference")
    return value


class MappingRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    record_id: str = Field(default_factory=lambda: f"urn:uuid:{uuid4()}")
    supersedes: str = ""
    subject_id: str
    object_id: str
    predicate_id: Predicate
    mapping_justification: str
    author_id: str
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    review_status: ReviewStatus = "suggested"
    subject_snapshot: ElementSnapshot
    object_snapshot: ElementSnapshot
    mapping_date: date = Field(default_factory=date.today)
    comment: str = Field(min_length=1)

    @field_validator("supersedes")
    @classmethod
    def predecessor(cls, value: str) -> str:
        return cls.record_uri(value) if value else value

    @field_validator("record_id")
    @classmethod
    def record_uri(cls, value: str) -> str:
        reference(value)
        if not value.startswith(("urn:", "http://", "https://")):
            raise ValueError("record_id must be an absolute URI")
        return value

    @field_validator("author_id", "mapping_justification")
    @classmethod
    def refs(cls, value: str) -> str:
        return reference(value)

    @field_validator("subject_id", "object_id")
    @classmethod
    def elements(cls, value: str) -> str:
        parse_element_id(value)
        return value

    @field_validator("comment")
    @classmethod
    def explanation(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("justification text is required")
        return value

    def cells(self) -> dict[str, str]:
        result = {k: str(v) for k, v in self.model_dump(mode="json").items()}
        for side in ("subject", "object"):
            snapshot = getattr(self, f"{side}_snapshot")
            result[f"{side}_snapshot"] = snapshot.model_dump_json()
            result[f"{side}_label"] = snapshot.name
            prefix = parse_element_id(getattr(self, f"{side}_id")).source
            result[f"{side}_source"] = CURIE_MAP[prefix]
            result[f"{side}_source_version"] = snapshot.source_version or ""
        return result


def encode(rows: list[MappingRow], metadata: dict) -> str:
    # Preserve unrelated declarations when updating an existing file.
    known = {definition["slot_name"] for definition in EXTENSIONS}
    extras = [definition for definition in metadata.get("extension_definitions", [])
              if definition["slot_name"] not in known]
    metadata = {**metadata, "curie_map": {**metadata.get("curie_map", {}), **CURIE_MAP},
                "extension_definitions": [*EXTENSIONS, *extras]}
    stream = io.StringIO(newline="")
    for line in yaml.safe_dump(metadata, sort_keys=True).splitlines():
        stream.write(f"# {line}\n")
    fields = list(MappingRow.model_fields) + [
        f"{side}_{suffix}" for side in ("subject", "object")
        for suffix in ("label", "source", "source_version")
    ]
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(row.cells() for row in rows)
    return stream.getvalue()


def decode(text: str) -> tuple[list[MappingRow], dict]:
    lines = text.splitlines(keepends=True)
    boundary = next((i for i, line in enumerate(lines) if not line.startswith("#")), len(lines))
    metadata = yaml.safe_load("".join(line[2:] for line in lines[:boundary]))
    if (not isinstance(metadata, dict) or not metadata.get("mapping_set_id")
            or not metadata.get("license")):
        raise ValueError("SSSOM mapping_set_id and license metadata are required")
    namespaces = metadata.get("curie_map")
    definitions = metadata.get("extension_definitions")
    if not isinstance(namespaces, dict):
        raise ValueError("SSSOM curie_map is required")
    if not isinstance(definitions, list):
        raise ValueError("missing or incompatible SSSOM extension definitions")
    declared = {}
    for definition in definitions:
        if not isinstance(definition, dict) or "slot_name" not in definition:
            raise ValueError("invalid SSSOM extension definition")
        name = definition["slot_name"]
        if name in declared:
            raise ValueError("duplicate SSSOM extension definition")
        declared[name] = definition
    rows = []
    seen = set()
    reader = csv.DictReader(io.StringIO("".join(lines[boundary:])), delimiter="\t")
    if not (set(MappingRow.model_fields) - {"supersedes"}).issubset(reader.fieldnames or []):
        raise ValueError("SSSOM header is missing required mapping columns")
    for definition in EXTENSIONS:
        if definition["slot_name"] in (reader.fieldnames or []):
            if declared.get(definition["slot_name"]) != definition:
                raise ValueError("missing or incompatible SSSOM extension definitions")
            if namespaces.get("smat") != CURIE_MAP["smat"]:
                raise ValueError("SSSOM namespace expansions disagree with element identities")
    for cells in reader:
        # Derived label/source columns are deliberately ignored: snapshots win.
        values = {key: cells[key] for key in MappingRow.model_fields if key in cells}
        for side in ("subject", "object"):
            key = f"{side}_snapshot"
            values[key] = ElementSnapshot.model_validate_json(values[key])
        row = MappingRow.model_validate(values)
        for key in ("subject_id", "object_id", "predicate_id", "author_id",
                    "mapping_justification"):
            prefix = getattr(row, key).split(":", 1)[0]
            if prefix in CURIE_MAP and namespaces.get(prefix) != CURIE_MAP[prefix]:
                raise ValueError("SSSOM namespace expansions disagree with element identities")
        if row.record_id in seen:
            raise ValueError(f"duplicate record_id: {row.record_id}")
        seen.add(row.record_id)
        rows.append(row)
    replaced = set()
    by_id = {row.record_id: row for row in rows}
    for row in rows:
        if not row.supersedes:
            continue
        if row.supersedes not in by_id or row.supersedes in replaced:
            raise ValueError("missing or multiply superseded record")
        replaced.add(row.supersedes)
        visited = {row.record_id}
        ancestor = row
        while ancestor.supersedes:
            if ancestor.supersedes in visited:
                raise ValueError("supersession cycle")
            visited.add(ancestor.supersedes)
            if ancestor.supersedes not in by_id:
                raise ValueError("missing superseded record")
            ancestor = by_id[ancestor.supersedes]
    return rows, metadata


def current_rows(rows: list[MappingRow]) -> list[MappingRow]:
    replaced = {row.supersedes for row in rows if row.supersedes}
    return [row for row in rows if row.record_id not in replaced]


class MappingStore:
    """Atomic, process-locked TSV transactions. No delete or replace-all API."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def rows(self) -> list[MappingRow]:
        return decode(self.path.read_text())[0] if self.path.exists() else []

    def _transaction(self, change: Callable[[list[MappingRow]], MappingRow]) -> MappingRow:
        with self.path.with_suffix(self.path.suffix + ".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            rows, metadata = decode(self.path.read_text()) if self.path.exists() else ([], {
                "mapping_set_id": f"urn:uuid:{uuid4()}",
                "license": "https://w3id.org/sssom/license/unspecified",
            })
            before = {row.record_id for row in rows}
            result = change(rows)
            if not before.issubset({row.record_id for row in rows}):
                raise ValueError("mapping rows cannot be deleted")
            payload = encode(rows, metadata)
            decode(payload)  # Validate before replacing the durable file.
            descriptor, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=".sssom-")
            try:
                with os.fdopen(descriptor, "w") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return result

    def suggest(self, row: MappingRow) -> MappingRow:
        if row.review_status != "suggested" or row.supersedes:
            raise ValueError("automated writes may only suggest")

        def add(rows: list[MappingRow]) -> MappingRow:
            for existing in reversed(rows):
                if (existing.subject_id, existing.predicate_id, existing.object_id) == (
                    row.subject_id, row.predicate_id, row.object_id
                ):
                    return existing  # Includes durable rejection suppression.
            rows.append(row)
            return row
        return self._transaction(add)

    def reject(self, record_id: str) -> MappingRow:
        def change(rows: list[MappingRow]) -> MappingRow:
            for i, row in enumerate(rows):
                if row.record_id == record_id:
                    if row.review_status != "suggested" or row not in current_rows(rows):
                        raise ValueError("only current suggested rows can be rejected")
                    result = MappingRow.model_validate(
                        {**row.model_dump(), "review_status": "rejected"}
                    )
                    rows[i] = result
                    return result
            raise ValueError(f"unknown record_id: {record_id}")
        return self._transaction(change)
