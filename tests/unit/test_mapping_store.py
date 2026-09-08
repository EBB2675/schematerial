"""Card 9: real SSSOM parsing, durable identities and automated-write constraints."""
from pathlib import Path

import pytest
from sssom.parsers import parse_sssom_table
from sssom_schema import Mapping

from schematerial.identity import ElementSnapshot
from schematerial.mappings.store import MappingRow, MappingStore, decode, encode


def row(**changes) -> MappingRow:
    return MappingRow.model_validate({
        "subject_id": "nomadsim:Run.energy", "object_id": "bammd:Sample.energy",
        "predicate_id": "skos:narrowMatch", "author_id": "orcid:0000-0001-2345-6789",
        "mapping_justification": "semapv:LexicalMatching", "confidence": 0.7,
        "comment": "Shared energy quantity; narrower source scope.",
        "subject_snapshot": ElementSnapshot(name="energy", parent="Run", source_version="1"),
        "object_snapshot": ElementSnapshot(name="energy", parent="Sample", source_version="2"),
        **changes,
    })


def test_sssom_roundtrip_and_snapshot_authority(tmp_path: Path):
    store = MappingStore(tmp_path / "mappings.sssom.tsv")
    original = store.suggest(row())
    parsed = parse_sssom_table(store.path)
    assert len(parsed.df) == 1
    assert parsed.df.iloc[0]["record_id"] == original.record_id
    assert parsed.df.iloc[0]["predicate_id"] == "skos:narrowMatch"
    assert any(d["slot_name"] == "review_status"
               for d in parsed.metadata["extension_definitions"])
    # sssom-py 0.4.21 drops extension columns; our TSV codec preserves them.
    assert store.rows() == [original]
    text = store.path.read_text().replace("\tenergy\t", "\tWRONG\t")
    rows, metadata = decode(text)
    corrected = encode(rows, metadata)
    assert "WRONG" not in corrected
    assert rows == [original]
    assert rows[0].cells()["subject_source_version"] == "1"
    assert rows[0].cells()["subject_source"] == "https://w3id.org/schematerial/nomadsim/"


@pytest.mark.parametrize("pairs", [
    [("nomadsim:A", "bammd:B"), ("nomadsim:A", "bammd:C")],
    [("nomadsim:A", "bammd:C"), ("nomadsim:B", "bammd:C")],
])
def test_splits_and_merges_have_distinct_row_ids(tmp_path: Path, pairs):
    store = MappingStore(tmp_path / "rows.tsv")
    for subject, object_ in pairs:
        store.suggest(row(subject_id=subject, object_id=object_))
    reloaded = MappingStore(store.path).rows()
    assert [(r.subject_id, r.object_id) for r in reloaded] == pairs
    assert len({r.record_id for r in reloaded}) == 2
    assert "record_id" in Mapping.__dataclass_fields__
    with pytest.raises(ValueError, match="duplicate record_id"):
        store.suggest(row(subject_id="nomadsim:Other", record_id=reloaded[0].record_id))
    assert store.rows() == reloaded


def test_rejection_is_durable_and_never_resuggested(tmp_path: Path):
    store = MappingStore(tmp_path / "rows.tsv")
    suggested = store.suggest(row())
    rejected = store.reject(suggested.record_id)
    assert rejected.review_status == "rejected"
    reopened = MappingStore(store.path)
    assert reopened.suggest(row()) == rejected
    assert reopened.rows() == [rejected]
    # Direction is significant, including after rejection.
    reopened.suggest(row(subject_id=suggested.object_id, object_id=suggested.subject_id))
    assert len(reopened.rows()) == 2


@pytest.mark.parametrize("status", ["accepted", "rejected"])
def test_automated_writer_cannot_set_review_state(tmp_path: Path, status):
    store = MappingStore(tmp_path / "rows.tsv")
    with pytest.raises(ValueError, match="only suggest"):
        store.suggest(row(review_status=status, confidence=1))
    assert store.rows() == []


@pytest.mark.parametrize("predicate", ["exact", "close", "related", "narrow", "broad"])
def test_all_directional_predicates(tmp_path: Path, predicate):
    store = MappingStore(tmp_path / "rows.tsv")
    original = row(predicate_id=f"skos:{predicate}Match")
    store.suggest(original)
    assert store.rows() == [original]


@pytest.mark.parametrize("changes", [
    {"confidence": float("nan")}, {"confidence": 1.1}, {"author_id": "someone"},
    {"record_id": "smat:local"}, {"predicate_id": "skos:wrong"}, {"comment": " "},
])
def test_invalid_rows_fail(changes):
    with pytest.raises(ValueError):
        row(**changes)


def test_concurrent_stores_preserve_all_rows(tmp_path: Path):
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "shared.tsv"

    def write(index: int):
        return MappingStore(path).suggest(row(subject_id=f"nomadsim:Element{index}"))

    with ThreadPoolExecutor(max_workers=4) as workers:
        created = list(workers.map(write, range(12)))
    assert {r.record_id for r in MappingStore(path).rows()} == {r.record_id for r in created}


def test_failed_replace_preserves_previous_file(tmp_path: Path, monkeypatch):
    store = MappingStore(tmp_path / "rows.tsv")
    original = store.suggest(row())

    def fail(*args):
        raise OSError("disk failure")

    monkeypatch.setattr("schematerial.mappings.store.os.replace", fail)
    with pytest.raises(OSError, match="disk failure"):
        store.suggest(row(subject_id="nomadsim:Other"))
    assert store.rows() == [original]
    assert list(tmp_path.glob(".sssom-*")) == []


def test_missing_header_is_not_an_empty_store(tmp_path: Path):
    store = MappingStore(tmp_path / "rows.tsv")
    store.suggest(row())
    headerless = "\n".join(line for line in store.path.read_text().splitlines()
                           if line.startswith("#"))
    with pytest.raises(ValueError, match="header"):
        decode(headerless)


@pytest.mark.parametrize("status", ["accepted", "rejected"])
def test_reject_refuses_human_decisions(tmp_path, status):
    original = row(review_status=status)
    path = tmp_path / "rows.tsv"
    path.write_text(encode([original], {"mapping_set_id": "urn:uuid:test", "license": "test"}))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="current suggested"):
        MappingStore(path).reject(original.record_id)
    assert path.read_bytes() == before


def test_metadata_evolves_without_locking_out_old_files(monkeypatch):
    from schematerial.mappings.store import CURIE_MAP, EXTENSIONS

    original = row()
    text = encode([original], {"mapping_set_id": "urn:uuid:test", "license": "test"})
    monkeypatch.setitem(CURIE_MAP, "future", "https://example.org/future/")
    monkeypatch.setattr("schematerial.mappings.store.EXTENSIONS", [
        *EXTENSIONS, {"slot_name": "future", "property": "smat:future", "type_hint": "string"}])
    assert decode(text)[0] == [original]
    # Extra unused file declarations and ordering do not change row meaning.
    import yaml
    lines = text.splitlines(keepends=True)
    boundary = next(i for i, line in enumerate(lines) if not line.startswith("#"))
    metadata = yaml.safe_load("".join(line[2:] for line in lines[:boundary]))
    metadata["curie_map"]["external"] = "https://example.org/external/"
    metadata["extension_definitions"].reverse()
    def document():
        return ("".join("# " + line + "\n" for line in yaml.safe_dump(metadata).splitlines())
                + "".join(lines[boundary:]))
    assert decode(document())[0] == [original]
    metadata["curie_map"]["nomadsim"] = "https://wrong.example/"
    with pytest.raises(ValueError, match="namespace"):
        decode(document())


def test_legacy_file_without_supersession_column_loads():
    import csv
    import io

    import yaml
    original = row()
    text = encode([original], {"mapping_set_id": "urn:uuid:test", "license": "test"})
    lines = text.splitlines(keepends=True)
    boundary = next(i for i, line in enumerate(lines) if not line.startswith("#"))
    metadata = yaml.safe_load("".join(line[2:] for line in lines[:boundary]))
    metadata["extension_definitions"] = [
        item for item in metadata["extension_definitions"] if item["slot_name"] != "supersedes"]
    reader = csv.DictReader(io.StringIO("".join(lines[boundary:])), delimiter="\t")
    fields = [key for key in (reader.fieldnames or []) if key != "supersedes"]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t")
    writer.writeheader()
    writer.writerows({key: value for key, value in cells.items() if key != "supersedes"}
                     for cells in reader)
    legacy = ("".join("# " + line + "\n" for line in yaml.safe_dump(metadata).splitlines())
              + stream.getvalue())
    assert decode(legacy)[0] == [original]


@pytest.mark.parametrize("kind", ["missing", "cycle", "fork"])
def test_invalid_supersession_history_fails(kind):
    first = row()
    second = row(supersedes=first.record_id)
    rows = [first, second]
    if kind == "missing":
        rows = [second]
    elif kind == "cycle":
        rows[0] = row(record_id=first.record_id, supersedes=second.record_id)
    else:
        rows.append(row(supersedes=first.record_id))
    with pytest.raises(ValueError, match="supersed|cycle"):
        decode(encode(rows, {"mapping_set_id": "urn:uuid:test", "license": "test"}))


def test_automated_suggestion_cannot_supersede(tmp_path):
    store = MappingStore(tmp_path / "rows.tsv")
    first = store.suggest(row())
    with pytest.raises(ValueError, match="only suggest"):
        store.suggest(row(supersedes=first.record_id))
    assert store.rows() == [first]


@pytest.mark.parametrize("change", ["missing-prefix", "changed-author-prefix",
                                   "missing-extension", "changed-extension"])
def test_used_metadata_must_remain_compatible(change):
    import yaml

    text = encode([row()], {"mapping_set_id": "urn:uuid:test", "license": "test"})
    lines = text.splitlines(keepends=True)
    boundary = next(i for i, line in enumerate(lines) if not line.startswith("#"))
    metadata = yaml.safe_load("".join(line[2:] for line in lines[:boundary]))
    if change == "missing-prefix":
        metadata["curie_map"].pop("bammd")
    elif change == "changed-author-prefix":
        metadata["curie_map"]["orcid"] = "https://wrong.example/"
    elif change == "missing-extension":
        metadata["extension_definitions"] = [
            item for item in metadata["extension_definitions"]
            if item["slot_name"] != "review_status"]
    else:
        metadata["extension_definitions"][0]["property"] = "smat:wrong"
    damaged = ("".join("# " + line + "\n" for line in yaml.safe_dump(metadata).splitlines())
               + "".join(lines[boundary:]))
    with pytest.raises(ValueError, match="namespace|extension"):
        decode(damaged)
