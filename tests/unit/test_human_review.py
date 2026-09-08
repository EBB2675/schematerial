"""Card 12: real HTTP boundary and persistence, using inline extraction schemas."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from schematerial.mappings.store import MappingRow, MappingStore
from schematerial.ontologies.pmdco import parse_taxonomy
from schematerial.parsers.bam_json import BamAdapter
from schematerial.parsers.nomad_json import NomadAdapter
from schematerial.web.app import create_app
from schematerial.web.preview import build_preview


@pytest.fixture
def previews():
    def document(source, module, kind, dtype, version, dependencies, contract, annotations):
        attribute = {"name": "value", "kind": kind,
                     "range": {"kind": "datatype", "name": dtype},
                     "annotations": annotations, "shape": []}
        return {"contract_version": contract, "source": {"name": source, "module": module,
                "version": version, "dependencies": dependencies}, "report": [], "enums": [],
                "classes": [{"id": "Sample", "name": "Sample", "bases": [],
                             **({"annotations": {"entity_kind": "ObjectTypeDef"}}
                                if kind == "property" else {}),
                             "attributes": [attribute], "effective_attributes": [
                                 {"name": "value", "kind": kind, "declaring_class_id": "Sample"}]}]}
    nomad = document("nomad-simulations", "nomad", "quantity", "builtins.float", "1",
                     {"nomad-lab": "1.4.0"}, "1.1", {})
    bam = document("bam-masterdata", "bam", "property", "REAL", "2",
                   {"pydantic": "2.13.5"}, "1.2", {"property_code": "VALUE", "data_type": "REAL"})
    return [build_preview(NomadAdapter().convert(nomad)), build_preview(BamAdapter().convert(bam))]


def client(previews, path, *, taxonomy=None, **kwargs):
    return TestClient(create_app(previews, mapping_path=path, client_root=Path("/nonexistent"),
                                 taxonomy=taxonomy),
                      base_url="http://localhost", client=("127.0.0.1", 12345), **kwargs)


def headers(live):
    session = live.get("/api/review-session")
    assert session.status_code == 200
    assert "HttpOnly" in session.headers["set-cookie"]
    return {"Origin": "http://localhost", "X-Review-Token": session.json()["token"]}


def form(**changes):
    return {"subject_schema": "nomad", "subject_id": "nomadsim:Sample.value",
            "object_schema": "bam", "object_id": "bammd:Sample.value",
            "predicate_id": "skos:narrowMatch", "author_id": "orcid:0000-0001-2345-6789",
            "comment": "Reviewed the two definitions and their scopes.", "confidence": 1, **changes}


@pytest.mark.parametrize("reverse,predicate", [(False, "narrow"), (True, "broad")])
def test_manual_create_and_restart(previews, tmp_path, reverse, predicate, monkeypatch):
    path = tmp_path / "crosswalk.tsv"
    live = client(previews, path)
    payload = form(predicate_id=f"skos:{predicate}Match")
    if reverse:
        payload.update(subject_schema="bam", subject_id="bammd:Sample.value",
                       object_schema="nomad", object_id="nomadsim:Sample.value")
    # Neither request may touch materialisation or matcher code.
    def forbidden(*args, **kwargs):
        raise AssertionError("materialisation entered during a request")
    monkeypatch.setattr("schematerial.cache.MaterialisationCache.get", forbidden)
    response = live.post("/api/human/mappings", json=payload, headers=headers(live))
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved["review_status"] == "accepted"
    for key in ("subject_id", "object_id", "predicate_id", "author_id", "comment"):
        assert saved[key] == payload[key]
    assert saved["subject_snapshot"]["parent"] == "Sample"
    assert saved["subject_snapshot"]["source_version"] == ("2" if reverse else "1")
    assert saved["mapping_justification"] == "semapv:ManualMappingCuration"
    reopened = client(previews, path)
    assert reopened.get("/api/mappings").json()["rows"] == [saved]
    assert live.post("/api/human/mappings", json=payload, headers=headers(live)).status_code == 409
    assert len(MappingStore(path).rows()) == 1


@pytest.mark.parametrize("attack", ["no-session", "no-origin", "foreign-origin", "wrong-token",
                                  "foreign-site", "wrong-cookie", "forged-snapshot", "status"])
def test_human_boundary_rejects_forged_writes(previews, tmp_path, attack):
    path = tmp_path / "rows.tsv"
    live = client(previews, path)
    auth = headers(live)
    payload = form()
    if attack == "no-session":
        live.cookies.clear()
    elif attack == "no-origin":
        auth.pop("Origin")
    elif attack == "foreign-origin":
        auth["Origin"] = "https://attacker.example"
    elif attack == "wrong-token":
        auth["X-Review-Token"] = "forged"
    elif attack == "foreign-site":
        auth["Sec-Fetch-Site"] = "cross-site"
    elif attack == "wrong-cookie":
        live.cookies.clear()
        live.cookies.set("schematerial_review", "other.1")
    elif attack == "forged-snapshot":
        payload["subject_snapshot"] = {"name": "fake"}
    else:
        payload["review_status"] = "accepted"
    response = live.post("/api/human/mappings", json=payload, headers=auth)
    assert response.status_code in (403, 422), response.text
    assert MappingStore(path).rows() == []


def test_remote_access_and_sessions_from_other_server_are_refused(previews, tmp_path):
    app = create_app(previews, mapping_path=tmp_path / "rows.tsv")
    remote = TestClient(app, base_url="http://localhost", client=("192.0.2.1", 12345))
    assert remote.get("/api/review-session").status_code == 403
    poisoned_host = TestClient(app, base_url="http://attacker.example", client=("127.0.0.1", 1))
    assert poisoned_host.get("/api/review-session").status_code == 403
    first = client(previews, tmp_path / "rows.tsv")
    auth = headers(first)
    second = client(previews, tmp_path / "rows.tsv")
    second.cookies.update(first.cookies)
    assert second.post("/api/human/mappings", json=form(), headers=auth).status_code == 403


@pytest.mark.parametrize("action,status", [("accept", "accepted"), ("reject", "rejected")])
def test_explicit_suggestion_review_persists(previews, tmp_path, action, status):
    path = tmp_path / "rows.tsv"
    store = MappingStore(path)
    suggested = store.suggest(MappingRow.model_validate({
        **{k: v for k, v in form().items() if not k.endswith("_schema")},
        "subject_snapshot": previews[0].details["nomadsim:Sample.value"]["mapping_snapshot"],
        "object_snapshot": previews[1].details["bammd:Sample.value"]["mapping_snapshot"],
        "mapping_justification": "semapv:LexicalMatching",
    }))
    live = client(previews, path)
    payload = {"record_id": suggested.record_id, "action": action,
               "author_id": "https://example.org/reviewer", "comment": "Human review reasoning."}
    assert live.post("/api/human/review", json=payload).status_code == 403
    assert store.rows() == [suggested]
    response = live.post("/api/human/review", json=payload, headers=headers(live))
    assert response.status_code == 200, response.text
    reviewed = MappingStore(path).rows()[0]
    assert reviewed.record_id == suggested.record_id
    assert reviewed.review_status == status
    assert reviewed.author_id == payload["author_id"]
    assert payload["comment"] in reviewed.comment
    assert suggested.mapping_justification in reviewed.comment
    assert reviewed.subject_snapshot == suggested.subject_snapshot
    assert store.suggest(suggested) == reviewed
    assert live.post("/api/human/review", json=payload, headers=headers(live)).status_code == 409


@pytest.mark.parametrize("change", [{"author_id": ""}, {"comment": " "},
                                   {"subject_id": "nomadsim:Missing"}, {"confidence": 2},
                                   {"subject_schema": []}])
def test_invalid_form_never_writes(previews, tmp_path, change):
    path = tmp_path / "rows.tsv"
    live = client(previews, path)
    assert live.post("/api/human/mappings", json=form(**change),
                     headers=headers(live)).status_code == 422
    assert not path.exists()


def test_expired_session_and_disk_failure_leave_store_unchanged(previews, tmp_path, monkeypatch):
    path = tmp_path / "rows.tsv"
    live = client(previews, path)
    auth = headers(live)
    import time
    now = time.time()
    with monkeypatch.context() as patch:
        patch.setattr("schematerial.web.human_review.time.time", lambda: now + 13 * 60 * 60)
        assert live.post("/api/human/mappings", json=form(), headers=auth).status_code == 403
    assert not path.exists()

    def fail(*args, **kwargs):
        raise OSError("disk is unavailable")
    monkeypatch.setattr("schematerial.mappings.store.os.replace", fail)
    response = live.post("/api/human/mappings", json=form(), headers=headers(live))
    assert response.status_code == 503
    assert "unsaved" in response.json()["detail"]
    assert not path.exists()


PMDCO_TURTLE = b'''
@prefix p: <https://w3id.org/pmd/co/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
p: a owl:Ontology; owl:versionIRI p:3.1.0 .
p:Material a owl:Class; rdfs:label "Material";
    rdfs:subClassOf <https://example.org/Entity> .
<https://example.org/Entity> a owl:Class; rdfs:label "Entity" .
'''


def test_direct_mapping_and_both_pmdco_anchors_coexist_offline(previews, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("external service or materialisation entered")
    monkeypatch.setattr("socket.socket.connect", forbidden)
    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr("schematerial.cache.MaterialisationCache.get", forbidden)
    taxonomy = parse_taxonomy(PMDCO_TURTLE, version="3.1.0")
    path = tmp_path / "complete-crosswalk.tsv"
    live = client(previews, path, taxonomy=taxonomy)
    assert live.get("/api/pmdco").content == taxonomy.payload_bytes
    drafts = [form(), form(object_schema="pmdco", object_id="pmdco:Material"),
              form(subject_schema="bam", subject_id="bammd:Sample.value",
                   object_schema="pmdco", object_id="pmdco:Material")]
    created = []
    for draft in drafts:
        response = live.post("/api/human/mappings", json=draft, headers=headers(live))
        assert response.status_code == 201, response.text
        created.append(response.json())
    reopened = client(previews, path, taxonomy=taxonomy)
    assert reopened.get("/api/mappings").json()["rows"] == created
    assert len({row["record_id"] for row in created}) == 3
    assert all(row["review_status"] == "accepted" for row in created)
    for row in created[1:]:
        assert row["object_snapshot"]["name"] == "Material"
        assert row["object_snapshot"]["source_version"] == "3.1.0"
    exported = MappingStore(path).rows()[1].cells()
    assert exported["object_source"] == "https://w3id.org/pmd/co/"
    assert exported["object_source_version"] == "3.1.0"
    assert exported["object_label"] == "Material"
    # The browser cannot relabel a contextual ancestor as a PMDco term.
    for target in ("pmdco:Missing", "https://example.org/Entity"):
        response = live.post("/api/human/mappings", headers=headers(live),
                             json=form(object_schema="pmdco", object_id=target))
        assert response.status_code == 422
    assert len(MappingStore(path).rows()) == 3


def test_pmdco_anchors_use_the_same_human_authorization(previews, tmp_path):
    taxonomy = parse_taxonomy(PMDCO_TURTLE, version="3.1.0")
    path = tmp_path / "rows.tsv"
    live = client(previews, path, taxonomy=taxonomy)
    response = live.post("/api/human/mappings",
                         json=form(object_schema="pmdco", object_id="pmdco:Material"))
    assert response.status_code == 403
    assert not path.exists()
