"""Offline taxonomy behavior on small inline Turtle fixtures."""
import hashlib
import json
from importlib.resources import files

import pytest

from schematerial.ontologies.pmdco import load_bundled, parse_taxonomy

TURTLE = b'''
@prefix p: <https://w3id.org/pmd/co/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
p: a owl:Ontology; owl:versionIRI p:3.1.0 .
<https://example.org/Entity> a owl:Class; rdfs:label "Entity" .
p:Material a owl:Class; rdfs:label "Werkstoff"@de, "Material"@en;
    rdfs:subClassOf <https://example.org/Entity>; skos:definition "Matter in a process"@en .
p:Specimen a owl:Class; rdfs:label "Specimen"@en; skos:altLabel "sample";
    rdfs:subClassOf p:Material, <https://example.org/Entity>,
      [a owl:Restriction; owl:onProperty p:hasPart; owl:someValuesFrom p:Material] .
p:Legacy a owl:Class; owl:deprecated true; rdfs:subClassOf p:Material .
p:CycleA a owl:Class; rdfs:subClassOf p:CycleB .
p:CycleB a owl:Class; rdfs:subClassOf p:CycleA .
p:hasPart a owl:ObjectProperty .
'''


def offline(*args, **kwargs):
    raise AssertionError("network access is forbidden")


def test_offline_taxonomy_preserves_identity_labels_and_all_named_parents(monkeypatch):
    monkeypatch.setattr("socket.socket.connect", offline)
    monkeypatch.setattr("urllib.request.urlopen", offline)
    taxonomy = parse_taxonomy(TURTLE, version="3.1.0")
    terms = {term.id: term for term in taxonomy.terms}
    assert len(terms) == 6
    assert terms["pmdco:Material"].label == "Material"
    assert "Werkstoff" in terms["pmdco:Material"].synonyms
    assert terms["pmdco:Material"].definition == "Matter in a process"
    assert terms["pmdco:Specimen"].parents == ("https://example.org/Entity", "pmdco:Material")
    assert "sample" in terms["pmdco:Specimen"].synonyms
    assert terms["pmdco:CycleA"].parents == ("pmdco:CycleB",)
    assert terms["pmdco:Legacy"].deprecated
    assert "pmdco:hasPart" not in terms
    assert not terms["https://example.org/Entity"].anchorable
    assert terms["pmdco:Material"].uri == "https://w3id.org/pmd/co/Material"
    snapshots = taxonomy.snapshots()
    assert len(snapshots) == 5
    assert snapshots[("pmdco", "pmdco:Material")].source_version == "3.1.0"
    assert snapshots[("pmdco", "pmdco:Material")].semantic_type is None
    assert parse_taxonomy(TURTLE, version="3.1.0").payload_bytes == taxonomy.payload_bytes
    assert json.loads(taxonomy.payload_bytes)["schema"] == "pmdco"


def test_wrong_version_or_unresolved_import_is_refused_offline(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", offline)
    with pytest.raises(ValueError, match="version IRI"):
        parse_taxonomy(TURTLE, version="2.0.8")
    with pytest.raises(ValueError, match="unresolved owl:imports"):
        parse_taxonomy(TURTLE + b'p: owl:imports <https://example.org/missing> .', version="3.1.0")


def test_bundle_resources_have_verified_release_and_license_bytes():
    # Packaging integrity only: real-schema behavioral tests use inline fixtures above.
    root = files("schematerial.ontologies").joinpath("assets")
    manifest = json.loads(root.joinpath("pmdco.json").read_text())
    assert manifest["version"] == "3.1.0"
    assert manifest["upstream_commit"] == "b4ce63ebf325d6596d0a1dba86e478fcafea547d"
    for name, digest in (("artifact", "sha256"), ("license_file", "license_sha256")):
        actual = hashlib.sha256(root.joinpath(manifest[name]).read_bytes()).hexdigest()
        assert actual == manifest[digest]
    assert manifest["license"] == "CC-BY-4.0"


def test_loader_validates_checksum_before_parsing(tmp_path, monkeypatch):
    root = tmp_path / "assets"
    root.mkdir()
    manifest = {"version": "3.1.0", "version_iri": "https://w3id.org/pmd/co/3.1.0",
                "namespace": "https://w3id.org/pmd/co/", "artifact": "fixture.ttl",
                "license_file": "license.txt", "sha256": "incorrect", "license_sha256": "incorrect"}
    (root / "pmdco.json").write_text(json.dumps(manifest))
    (root / "fixture.ttl").write_bytes(TURTLE)
    (root / "license.txt").write_text("Fixture license")
    monkeypatch.setattr("schematerial.ontologies.pmdco.files", lambda _: tmp_path)
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_bundled()
