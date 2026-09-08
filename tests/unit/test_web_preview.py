"""Read-only preview: ingestion, prepared payloads and the request path.

Every schema here is a small document defined in this file and pushed through
the same JSON boundary a real extractor writes. No source package is imported
and no real extraction output is required.
"""

import gzip
import json
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from linkml_runtime.dumpers import yaml_dumper
from linkml_runtime.linkml_model.meta import ClassDefinition, SchemaDefinition, SlotDefinition
from linkml_runtime.utils.schemaview import SchemaView

from schematerial._linkml import add_attribute, add_class, set_annotation
from schematerial.cache import MaterialisationCache
from schematerial.extraction.runner import ExtractorEnvironment, run_extractor
from schematerial.identity import Source, element_id, snapshot_index
from schematerial.loading import LoadedSchema
from schematerial.parsers.registry import ADAPTERS
from schematerial.parsers.source import SchemaImportError
from schematerial.web.app import create_app
from schematerial.web.graph import COLUMN, MAX_COLUMNS, layer_positions
from schematerial.web.preview import SchemaPreview, build_preview, ingest

FAKE = Path(__file__).parents[2] / "src/schematerial/extractors/fake.py"
SCHEMA = "fixture"


def quantity(name: str = "value", dtype: str = "builtins.float", **kwargs: Any) -> dict[str, Any]:
    return {"name": name, "kind": "quantity", "range": {"kind": "datatype", "name": dtype},
            "shape": [], **kwargs}


def subsection(name: str, target: str, repeats: bool = False) -> dict[str, Any]:
    return {"name": name, "kind": "subsection", "range": {"kind": "class", "name": target},
            "repeats": repeats}


def ref(owner: str, name: str = "value", kind: str = "quantity") -> dict[str, str]:
    return {"name": name, "kind": kind, "declaring_class_id": owner}


def cls(name: str, attrs: list[dict[str, Any]], bases: list[str] | None = None,
        effective: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {"id": name, "name": name.rsplit(".", 1)[-1], "attributes": attrs,
            "bases": bases or [], "effective_attributes": effective if effective is not None else
            [ref(name, a["name"], a["kind"]) for a in attrs]}


def document(*classes: dict[str, Any], source_name: str = "nomad-simulations",
             module: str = SCHEMA) -> dict[str, Any]:
    return {"contract_version": "1.1", "source": {"name": source_name, "version": "0.6.0",
            "module": module, "dependencies": {"nomad-lab": "1.4.0"}},
            "classes": list(classes), "enums": [], "report": []}


def boundary(doc: dict[str, Any]) -> dict[str, Any]:
    """Round-trip the fixture through the same out-of-process JSON boundary."""
    return run_extractor(ExtractorEnvironment("inline", Path(sys.executable)), FAKE,
                         input_text=json.dumps(doc))


# `Base.value` carries a symbolic shape, so it converts partially and its
# diagnostic is reported at its declaration. `Child` inherits it through two
# bases, and `Root.child` nests `Child`, which is what makes contextual snapshot
# paths differ from class-local element counts.
FIXTURE = document(
    cls("Base", [quantity(unit="meter", shape=["n_atoms", 3])]),
    cls("Extra", [quantity("tag", "builtins.str")]),
    cls("Child", [], ["Base", "Extra"], [ref("Base"), ref("Extra", "tag")]),
    cls("Root", [subsection("child", "Child", repeats=True)]),
)


def write(tmp_path: Path, doc: dict[str, Any], name: str = "fixture.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(boundary(doc)), encoding="utf-8")
    return path


@pytest.fixture
def previews(tmp_path: Path) -> tuple[SchemaPreview, ...]:
    return ingest([write(tmp_path, FIXTURE)])


@pytest.fixture
def client(previews: tuple[SchemaPreview, ...]) -> TestClient:
    # An empty directory: the placeholder path, so no build output is required.
    return TestClient(create_app(previews, client_root=Path("/nonexistent")))


def index(client: TestClient) -> list[dict[str, Any]]:
    response = client.get(f"/api/schemas/{SCHEMA}/elements")
    assert response.status_code == 200
    return response.json()["elements"]


def detail(client: TestClient, identifier: str) -> dict[str, Any]:
    response = client.get(f"/api/schemas/{SCHEMA}/element", params={"id": identifier})
    assert response.status_code == 200, response.text
    return response.json()


# --- the page's data reaches the client through the server -------------------


def test_catalogue_reports_the_schema_name_and_source(client: TestClient) -> None:
    summaries = client.get("/api/schemas").json()["schemas"]
    assert [row["name"] for row in summaries] == [SCHEMA]
    summary = summaries[0]
    assert summary["status"] == "ok" and summary["error"] is None
    assert summary["title"] == f"NOMAD {SCHEMA}"
    assert summary["source"] == {"package": "nomad-simulations", "version": "0.6.0",
                                 "dependencies": {"nomad-lab": "1.4.0"}}
    assert summary["cache_key"] and summary["toolchain"]["linkml"]


def test_counts_name_what_they_count_and_do_not_conflate_them(client: TestClient) -> None:
    counts = client.get(f"/api/schemas/{SCHEMA}").json()["counts"]
    assert counts["classes"] == 4
    # Base.value, Extra.tag, Child.value, Child.tag, Root.child
    assert counts["effective_attributes"] == 5
    assert counts["local_attributes"] == 3
    assert counts["inherited_attributes"] == 2
    assert counts["browsable_elements"] == counts["classes"] + counts["effective_attributes"] == 9
    # Contextual positions from the roots, including Root.child.value and
    # Root.child.tag. A different number over the same schema, on purpose.
    assert counts["snapshot_paths"] == 8
    assert len({counts["effective_attributes"], counts["browsable_elements"],
                counts["snapshot_paths"]}) == 3


def test_index_lists_every_class_and_effective_attribute(client: TestClient) -> None:
    rows = index(client)
    assert len(rows) == 9
    assert sum(row["kind"] == "class" for row in rows) == 4
    child = [row for row in rows if row["class_name"] == "Child"]
    assert {row["name"] for row in child} == {"Child", "value", "tag"}
    inherited = {row["name"] for row in child if row["inherited"]}
    assert inherited == {"value", "tag"}


# --- stable identifiers ------------------------------------------------------


def test_identifiers_are_the_shared_element_ids(client: TestClient) -> None:
    rows = {row["id"] for row in index(client)}
    assert element_id("nomadsim", ("Child",)) in rows
    assert element_id("nomadsim", ("Child", "value")) in rows
    assert element_id("nomadsim", ("Base", "value")) in rows


def test_identifiers_are_identical_across_two_ingestions(tmp_path: Path) -> None:
    first = ingest([write(tmp_path, FIXTURE, "one.json")])
    second = ingest([write(tmp_path, FIXTURE, "two.json")])
    assert first[0].index_bytes == second[0].index_bytes
    assert first[0].detail_bytes == second[0].detail_bytes
    assert first[0].summary["cache_key"] == second[0].summary["cache_key"]


def test_a_declaration_identifier_is_not_a_class_scoped_identifier(client: TestClient) -> None:
    inherited = detail(client, element_id("nomadsim", ("Child", "value")))
    # Seen on Child, declared on Base: the two identifiers must not be the same.
    assert inherited["id"] == element_id("nomadsim", ("Child", "value"))
    assert inherited["declaration_id"] == element_id("nomadsim", ("Base", "value"))
    assert inherited["id"] != inherited["declaration_id"]
    # And neither is a snapshot path, which names a contextual position.
    assert inherited["snapshot_paths"] == [element_id("nomadsim", ("Root", "child", "value"))]


def test_snapshot_paths_are_contextual_not_declarations(client: TestClient) -> None:
    root = detail(client, element_id("nomadsim", ("Root",)))
    assert root["snapshot_paths"] == [element_id("nomadsim", ("Root",))]
    nested = detail(client, element_id("nomadsim", ("Child", "tag")))
    assert nested["snapshot_paths"] == [element_id("nomadsim", ("Root", "child", "tag"))]


# --- inspection: provenance, parents, diagnostics -----------------------------


def test_inherited_attribute_exposes_its_declaration_provenance(client: TestClient) -> None:
    inherited = detail(client, element_id("nomadsim", ("Child", "value")))
    assert inherited["inherited"] is True
    assert inherited["class"]["key"] == "Child"
    assert inherited["declared_in"]["key"] == "Base"
    # The source's own effective reference, alongside the adapter's answer.
    assert inherited["source_reference"] == {"kind": "quantity", "name": "value",
                                             "declaring_class_id": "Base"}
    local = detail(client, element_id("nomadsim", ("Base", "value")))
    assert local["inherited"] is False and local["declared_in"]["key"] == "Base"


def test_a_class_exposes_every_source_parent_not_only_the_backbone(client: TestClient) -> None:
    child = detail(client, element_id("nomadsim", ("Child",)))
    assert [(parent["key"], parent["role"]) for parent in child["parents"]] == [
        ("Base", "is_a"), ("Extra", "mixin")]
    assert {ancestor["key"] for ancestor in child["ancestors"]} == {"Base", "Extra"}
    assert child["counts"] == {"local_attributes": 0, "effective_attributes": 2,
                               "inherited_attributes": 2, "snapshot_paths": 0}


def test_diagnostics_reach_the_element_they_concern(client: TestClient) -> None:
    declared = detail(client, element_id("nomadsim", ("Base", "value")))
    reasons = [row["reason"] for row in declared["diagnostics"]]
    assert any("symbolic shape" in reason for reason in reasons)
    assert all(row["inherited"] is False for row in declared["diagnostics"])
    # The same diagnostic is visible where the attribute is inherited, marked as
    # having been reported at the declaration.
    inherited = detail(client, element_id("nomadsim", ("Child", "value")))
    assert [row["reason"] for row in inherited["diagnostics"]] == reasons
    assert all(row["inherited"] is True for row in inherited["diagnostics"])
    assert next(row for row in index(client)
                if row["id"] == element_id("nomadsim", ("Child", "value")))["diagnostics"] == 1


def test_conversion_facts_survive_into_the_detail(client: TestClient) -> None:
    value = detail(client, element_id("nomadsim", ("Base", "value")))
    assert value["range"] == {"name": "float", "kind": "type"}
    assert value["unit"] == {"ucum_code": "m", "source": "meter"}
    assert value["source"]["shape"] == ["n_atoms", 3]
    assert value["array"]["exact_number_dimensions"] == 2 and value["array"]["dimensions"] == []
    assert value["snapshot"]["source_version"] == "0.6.0"
    assert value["facets"] == {}
    child = detail(client, element_id("nomadsim", ("Root", "child")))
    assert child["multivalued"] is True
    assert child["range"]["kind"] == "class" and child["range"]["target"]["key"] == "Child"


# --- nothing happens in a request path ----------------------------------------


def test_requests_never_materialise_read_the_cache_or_serialise(
    previews: tuple[SchemaPreview, ...]
) -> None:
    materialise = Mock(side_effect=AssertionError("materialised in a request path"))
    read = Mock(side_effect=AssertionError("cache read in a request path"))
    prepare = Mock(side_effect=AssertionError("cache prepared in a request path"))
    identifier = element_id("nomadsim", ("Child", "value"))
    with (
        patch.object(SchemaView, "materialize_derived_schema", materialise),
        patch.object(MaterialisationCache, "get", read),
        patch.object(MaterialisationCache, "prepare", prepare),
    ):
        with TestClient(create_app(previews, client_root=Path("/nonexistent"))) as live:
            for _ in range(25):
                assert live.get("/api/schemas").status_code == 200
                assert live.get(f"/api/schemas/{SCHEMA}/elements").status_code == 200
                assert live.get(f"/api/schemas/{SCHEMA}/element",
                                params={"id": identifier}).status_code == 200
    assert materialise.call_count == read.call_count == prepare.call_count == 0


def test_responses_are_the_bytes_prepared_at_ingestion(
    previews: tuple[SchemaPreview, ...], client: TestClient
) -> None:
    preview = previews[0]
    identifier = element_id("nomadsim", ("Child", "value"))
    assert client.get(f"/api/schemas/{SCHEMA}").content == preview.summary_bytes
    assert client.get(f"/api/schemas/{SCHEMA}/elements",
                      headers={"accept-encoding": "identity"}).content == preview.index_bytes
    assert client.get(f"/api/schemas/{SCHEMA}/element",
                      params={"id": identifier}).content == preview.detail_bytes[identifier]


def test_the_index_is_compressed_at_ingestion_not_per_request(
    previews: tuple[SchemaPreview, ...], client: TestClient
) -> None:
    preview = previews[0]
    assert gzip.decompress(preview.index_gzip) == preview.index_bytes
    response = client.get(f"/api/schemas/{SCHEMA}/elements", headers={"accept-encoding": "gzip"})
    assert response.headers["vary"] == "accept-encoding"
    # httpx decodes transparently, so compare against the decoded payload.
    assert response.json() == json.loads(preview.index_bytes)


def test_ingestion_uses_the_cache_once_per_document(tmp_path: Path) -> None:
    cache = MaterialisationCache()
    documents = [write(tmp_path, FIXTURE, "a.json"), write(tmp_path, FIXTURE, "b.json")]
    with patch.object(SchemaView, "materialize_derived_schema",
                      autospec=True, side_effect=SchemaView.materialize_derived_schema) as spy:
        ingest(documents, cache=cache)
    # Identical content, so the second document reuses the first entry.
    assert spy.call_count == 1


# --- refusals stay visible ----------------------------------------------------


def test_a_refused_document_is_listed_with_its_reason(tmp_path: Path) -> None:
    # A contract 1.0 document: no dependency versions, no effective references.
    stale = document(cls("Base", [quantity()]))
    stale["contract_version"] = "1.0"
    del stale["source"]["dependencies"]
    for record in stale["classes"]:
        del record["effective_attributes"]
    previews = ingest([write(tmp_path, stale, "stale.json")])
    assert previews[0].status == "unsupported"
    client = TestClient(create_app(previews, client_root=Path("/nonexistent")))
    summary = client.get("/api/schemas").json()["schemas"][0]
    assert summary["status"] == "unsupported"
    assert "contract 1.1" in summary["error"]
    assert summary["counts"]["browsable_elements"] == 0
    assert client.get(f"/api/schemas/{SCHEMA}/elements").json()["elements"] == []


def test_a_refused_document_does_not_stop_the_others(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    previews = ingest([broken, write(tmp_path, FIXTURE)])
    assert [preview.status for preview in previews] == ["unsupported", "ok"]
    assert previews[0].summary["error"]


def test_incomplete_extraction_keeps_its_diagnostics(tmp_path: Path) -> None:
    incomplete = document(cls("Base", [quantity()]))
    incomplete["report"] = [{"path": "Base.other", "status": "skipped",
                             "reason": "unreadable attribute"}]
    previews = ingest([write(tmp_path, incomplete, "incomplete.json")])
    assert previews[0].status == "unsupported"
    assert previews[0].summary["schema_diagnostics"] == [
        {"path": "Base.other", "status": "skipped", "reason": "unreadable attribute"}]


# --- unknown things, and the page itself --------------------------------------


def test_unknown_schema_and_element_are_reported_not_guessed(client: TestClient) -> None:
    assert client.get("/api/schemas/nope").status_code == 404
    assert client.get("/api/schemas/nope/elements").status_code == 404
    response = client.get(f"/api/schemas/{SCHEMA}/element", params={"id": "nomadsim:Nope"})
    assert response.status_code == 404 and "nomadsim:Nope" in response.json()["error"]


def test_the_page_is_served_when_it_is_built(
    previews: tuple[SchemaPreview, ...], tmp_path: Path
) -> None:
    root = tmp_path / "dist"
    root.mkdir()
    (root / "index.html").write_text("<!doctype html><title>built</title>", encoding="utf-8")
    built = TestClient(create_app(previews, client_root=root))
    assert "built" in built.get("/").text


def test_an_unbuilt_page_explains_itself_and_leaves_the_api_working(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200 and "npm run build" in page.text
    assert client.get("/api/health").json()["status"] == "ok"


def test_health_reports_every_schema_and_its_status(client: TestClient) -> None:
    assert client.get("/api/health").json() == {
        "status": "ok", "schemas": [{"name": SCHEMA, "status": "ok"}]}


# --- no matcher, no model, no network ------------------------------------------


def test_serving_needs_no_network(previews: tuple[SchemaPreview, ...]) -> None:
    # Outbound connections only: an asyncio event loop legitimately makes a
    # local socketpair for its own wakeup pipe.
    forbidden = Mock(side_effect=AssertionError("the preview reached the network"))
    identifier = element_id("nomadsim", ("Child", "value"))
    with (
        patch.object(socket.socket, "connect", forbidden),
        patch.object(socket, "create_connection", forbidden),
    ):
        offline = TestClient(create_app(previews, client_root=Path("/nonexistent")))
        assert offline.get("/api/schemas").status_code == 200
        assert offline.get(f"/api/schemas/{SCHEMA}/elements").status_code == 200
        assert offline.get(f"/api/schemas/{SCHEMA}/element",
                           params={"id": identifier}).status_code == 200
    assert forbidden.call_count == 0


def test_ingestion_and_serving_need_no_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No API key, no endpoint, no feature flag: the preview is complete without them.
    for name in list(dict(__import__("os").environ)):
        if "KEY" in name or "TOKEN" in name or "OPENAI" in name or "ANTHROPIC" in name:
            monkeypatch.delenv(name, raising=False)
    previews = ingest([write(tmp_path, FIXTURE)])
    client = TestClient(create_app(previews, client_root=Path("/nonexistent")))
    assert len(client.get(f"/api/schemas/{SCHEMA}/elements").json()["elements"]) == 9


# --- the preview is not bound to one source -----------------------------------


@dataclass(frozen=True)
class FakeImport:
    """The shape every adapter returns, without naming a source package."""

    schema: SchemaDefinition
    loaded: LoadedSchema
    cache_key: str
    report: tuple[dict[str, str], ...]

    def to_yaml(self) -> str:
        return yaml_dumper.dumps(self.schema)


class OtherSourceAdapter:
    """A second adapter, standing in for one that is not NOMAD.

    It writes a different decision 1 prefix and none of NOMAD's conversion
    annotations, which is precisely what the preview must not depend on.
    """

    source = Source.BAM_MASTERDATA

    def __init__(self, cache: MaterialisationCache) -> None:
        self.cache = cache

    def convert(self, document: dict[str, Any]) -> FakeImport:
        module = document["source"]["module"]
        schema = SchemaDefinition(
            id=f"https://w3id.org/schematerial/other/{module}", name=module,
            title=f"Other {module}", version=document["source"]["version"],
            imports=["linkml:types"],
        )
        for row in document["classes"]:
            definition = ClassDefinition(
                name=row["id"], title=row["name"],
                class_uri=element_id(self.source, (row["id"],)),
                is_a=row["bases"][0] if row["bases"] else None, mixins=row["bases"][1:],
            )
            set_annotation(definition, "source_bases", json.dumps(row["bases"]))
            set_annotation(definition, "source_effective_attributes",
                           json.dumps(row["effective_attributes"], sort_keys=True))
            for raw in row["attributes"]:
                attribute = SlotDefinition(
                    name=raw["name"], range="string",
                    slot_uri=element_id(self.source, (row["id"], raw["name"])),
                )
                set_annotation(attribute, "source_declaring_class", row["id"])
                set_annotation(attribute, "source_kind", raw["kind"])
                add_attribute(definition, attribute)
            add_class(schema, definition)
        key = self.cache.prepare(yaml_dumper.dumps(schema))
        loaded = LoadedSchema(self.cache.get(key), snapshot_index(self.cache.get(key), self.source))
        return FakeImport(schema, loaded, key, tuple(dict(row) for row in document["report"]))


OTHER = document(
    cls("Sample", [quantity("code", "builtins.str")]),
    cls("Powder", [quantity("mesh", "builtins.str")], ["Sample"],
        [ref("Sample", "code"), ref("Powder", "mesh")]),
    source_name="other-masterdata", module="other",
)


@pytest.fixture
def other_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(ADAPTERS, "other-masterdata", OtherSourceAdapter)


def test_the_document_chooses_its_adapter(tmp_path: Path, other_registered: None) -> None:
    previews = ingest([write(tmp_path, OTHER, "other.json")])
    assert previews[0].status == "ok"
    assert previews[0].summary["source"]["package"] == "other-masterdata"
    assert previews[0].summary["title"] == "Other other"


def test_identifiers_use_the_prefix_the_adapter_wrote(
    tmp_path: Path, other_registered: None
) -> None:
    previews = ingest([write(tmp_path, OTHER, "other.json")])
    client = TestClient(create_app(previews, client_root=Path("/nonexistent")))
    rows = client.get("/api/schemas/other/elements").json()["elements"]
    # Every identifier, not just the class ones, carries the other source's prefix.
    assert rows and all(row["id"].startswith("bammd:") for row in rows)
    assert element_id(Source.BAM_MASTERDATA, ("Powder", "code")) in {row["id"] for row in rows}

    inherited = client.get("/api/schemas/other/element", params={
        "id": element_id(Source.BAM_MASTERDATA, ("Powder", "code"))}).json()
    assert inherited["inherited"] is True
    assert inherited["declared_in"]["id"] == element_id(Source.BAM_MASTERDATA, ("Sample",))
    assert inherited["declaration_id"] == element_id(Source.BAM_MASTERDATA, ("Sample", "code"))
    assert inherited["snapshot_paths"] == [element_id(Source.BAM_MASTERDATA, ("Powder", "code"))]
    parents = client.get("/api/schemas/other/element", params={
        "id": element_id(Source.BAM_MASTERDATA, ("Powder",))}).json()["parents"]
    assert [(parent["key"], parent["role"], parent["id"]) for parent in parents] == [
        ("Sample", "is_a", element_id(Source.BAM_MASTERDATA, ("Sample",)))]


def test_two_sources_load_together_and_keep_their_own_prefixes(
    tmp_path: Path, other_registered: None
) -> None:
    previews = ingest([write(tmp_path, FIXTURE), write(tmp_path, OTHER, "other.json")])
    assert [preview.name for preview in previews] == [SCHEMA, "other"]
    assert all(preview.status == "ok" for preview in previews)
    client = TestClient(create_app(previews, client_root=Path("/nonexistent")))
    assert client.get("/api/health").json()["schemas"] == [
        {"name": SCHEMA, "status": "ok"}, {"name": "other", "status": "ok"}]
    nomad = client.get(f"/api/schemas/{SCHEMA}/elements").json()["elements"]
    other = client.get("/api/schemas/other/elements").json()["elements"]
    assert all(row["id"].startswith("nomadsim:") for row in nomad)
    assert all(row["id"].startswith("bammd:") for row in other)


def test_a_document_from_an_unknown_source_is_reported_not_guessed(tmp_path: Path) -> None:
    unknown = document(cls("Sample", [quantity()]), source_name="mystery-package")
    previews = ingest([write(tmp_path, unknown, "mystery.json")])
    assert previews[0].status == "unsupported"
    error = previews[0].summary["error"]
    assert "mystery-package" in error and "nomad-simulations" in error
    assert previews[0].summary["counts"]["browsable_elements"] == 0


def test_an_import_mixing_prefixes_is_refused() -> None:
    # Declarations saying one source while snapshot paths say another would make
    # every path-to-element join miss silently, so it must not be served at all.
    native = ADAPTERS["nomad-simulations"](MaterialisationCache()).convert(boundary(FIXTURE))
    crossed = FakeImport(
        native.schema,
        LoadedSchema(native.loaded.schema,
                     snapshot_index(native.loaded.schema, Source.BAM_MASTERDATA)),
        native.cache_key,
        native.report,
    )
    with pytest.raises(SchemaImportError, match="exactly one source prefix"):
        build_preview(crossed)


# --- the structural graph -----------------------------------------------------


def graph_of(client: TestClient, name: str = SCHEMA) -> dict[str, Any]:
    response = client.get(f"/api/schemas/{name}/graph")
    assert response.status_code == 200, response.text
    return response.json()


# `SubHolder` inherits `Holder.part`, which is what makes a containment edge
# drawn per declaration different from one drawn per effective attribute.
NESTED = document(
    cls("Target", [quantity()]),
    cls("Holder", [subsection("part", "Target")]),
    cls("SubHolder", [], ["Holder"], [ref("Holder", "part", "subsection")]),
)


def test_graph_nodes_are_the_classes_under_their_element_identifiers(
    client: TestClient,
) -> None:
    nodes = graph_of(client)["nodes"]
    assert {node["id"] for node in nodes} == {
        element_id("nomadsim", (key,)) for key in ("Base", "Extra", "Child", "Root")
    }
    # The short source name is what a box shows; the full key stays available.
    base = next(node for node in nodes if node["key"] == "Base")
    assert base["name"] == "Base" and base["attributes"] == 1


def test_inheritance_edges_keep_the_backbone_and_the_mixin_apart(client: TestClient) -> None:
    edges = graph_of(client)["edges"]
    child = element_id("nomadsim", ("Child",))
    inheritance = {
        (edge["target"], edge["kind"]) for edge in edges if edge["source"] == child
    }
    # `Child` was declared on `Base` first and `Extra` second, so one became the
    # LinkML backbone and the other a mixin. The graph says which.
    assert inheritance == {
        (element_id("nomadsim", ("Base",)), "is_a"),
        (element_id("nomadsim", ("Extra",)), "mixin"),
    }


def test_containment_edges_are_drawn_where_the_attribute_is_declared(
    tmp_path: Path,
) -> None:
    previews = ingest([write(tmp_path, NESTED)])
    edges = [edge for edge in previews[0].graph["edges"] if edge["kind"] == "contains"]
    # One edge, at the class that declares `part` -- not a second one at the
    # subclass that merely inherits it.
    assert [(edge["source"], edge["target"], edge["label"]) for edge in edges] == [
        (element_id("nomadsim", ("Holder",)), element_id("nomadsim", ("Target",)), "part")
    ]


def test_no_edge_leaves_the_schema(client: TestClient) -> None:
    payload = graph_of(client)
    identifiers = {node["id"] for node in payload["nodes"]}
    for edge in payload["edges"]:
        assert edge["source"] in identifiers and edge["target"] in identifiers


def test_layout_puts_a_class_below_every_base_it_descends_from(client: TestClient) -> None:
    payload = graph_of(client)
    where = {node["key"]: (node["x"], node["y"]) for node in payload["nodes"]}
    assert where["Base"][1] == where["Extra"][1] == 0
    assert where["Child"][1] > where["Base"][1]
    # Two classes never share one position.
    assert len(set(where.values())) == len(where)
    assert payload["width"] > 0 and payload["height"] > 0


def test_a_cycle_in_the_source_bases_still_lays_out() -> None:
    keys = ["A", "B", "C"]
    names = {key: key for key in keys}
    positions = layer_positions(keys, names, {"A": ["B"], "B": ["A"], "C": ["A"]})
    # Terminates, places everything, and overlaps nothing. Where a cycle puts
    # its own members is arbitrary; that a descendant outside the cycle still
    # sits below it is not.
    assert set(positions) == set(keys)
    assert len(set(positions.values())) == len(keys)
    assert positions["C"][1] > positions["A"][1]


def test_an_unknown_base_gets_no_node_and_therefore_no_edge() -> None:
    positions = layer_positions(["Known"], {"Known": "Known"}, {"Known": ["Missing"]})
    assert positions == {"Known": (0, 0)}


def test_the_graph_is_identical_across_two_ingestions(tmp_path: Path) -> None:
    first = ingest([write(tmp_path, FIXTURE, "one.json")])
    second = ingest([write(tmp_path, FIXTURE, "two.json")])
    assert first[0].graph_bytes == second[0].graph_bytes


def test_the_graph_is_prepared_and_compressed_at_ingestion(
    previews: tuple[SchemaPreview, ...], client: TestClient
) -> None:
    preview = previews[0]
    assert gzip.decompress(preview.graph_gzip) == preview.graph_bytes
    plain = client.get(f"/api/schemas/{SCHEMA}/graph", headers={"accept-encoding": "identity"})
    assert plain.content == preview.graph_bytes
    compressed = client.get(f"/api/schemas/{SCHEMA}/graph", headers={"accept-encoding": "gzip"})
    assert compressed.headers["vary"] == "accept-encoding"
    assert compressed.json() == json.loads(preview.graph_bytes)


def test_a_refused_document_has_no_graph(tmp_path: Path) -> None:
    stale = document(cls("Base", [quantity()]))
    stale["contract_version"] = "1.0"
    del stale["source"]["dependencies"]
    for record in stale["classes"]:
        del record["effective_attributes"]
    previews = ingest([write(tmp_path, stale, "stale.json")])
    assert previews[0].status == "unsupported"
    assert previews[0].graph["nodes"] == [] and previews[0].graph["edges"] == []


def test_graph_requests_never_materialise_read_the_cache_or_serialise(
    previews: tuple[SchemaPreview, ...]
) -> None:
    materialise = Mock(side_effect=AssertionError("materialised in a request path"))
    read = Mock(side_effect=AssertionError("cache read in a request path"))
    with (
        patch.object(SchemaView, "materialize_derived_schema", materialise),
        patch.object(MaterialisationCache, "get", read),
    ):
        with TestClient(create_app(previews, client_root=Path("/nonexistent"))) as live:
            for _ in range(25):
                assert live.get(f"/api/schemas/{SCHEMA}/graph").status_code == 200
    assert materialise.call_count == read.call_count == 0


def test_an_unknown_schema_has_no_graph(client: TestClient) -> None:
    assert client.get("/api/schemas/nothing/graph").status_code == 404


def test_a_wide_layer_wraps_instead_of_running_off_sideways() -> None:
    # 40 classes with no base at all, which is the shape real masterdata has.
    keys = [f"C{index:02d}" for index in range(40)]
    positions = layer_positions(keys, {key: key for key in keys}, {})
    assert max(x for x, _ in positions.values()) < MAX_COLUMNS * COLUMN
    assert max(y for _, y in positions.values()) > 0
    assert len(set(positions.values())) == len(keys)


def test_a_class_stays_below_its_bases_even_when_the_layer_above_wrapped() -> None:
    keys = [f"Root{index:02d}" for index in range(MAX_COLUMNS + 5)] + ["Leaf"]
    positions = layer_positions(
        keys, {key: key for key in keys}, {"Leaf": ["Root00", f"Root{MAX_COLUMNS + 4:02d}"]}
    )
    assert positions["Leaf"][1] > max(
        y for key, (_, y) in positions.items() if key != "Leaf"
    )


def test_every_inheritance_edge_points_at_a_class_above_it(client: TestClient) -> None:
    payload = graph_of(client)
    at = {node["id"]: (node["x"], node["y"]) for node in payload["nodes"]}
    for edge in payload["edges"]:
        if edge["kind"] in ("is_a", "mixin"):
            assert at[edge["source"]][1] > at[edge["target"]][1]
