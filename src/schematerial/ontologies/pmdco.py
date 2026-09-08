"""Offline PMDco taxonomy. Parse Turtle bytes once; never follow ontology imports."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from schematerial.identity import ElementSnapshot, capture_snapshot, parse_element_id

NAMESPACE = "https://w3id.org/pmd/co/"
VERSION = "3.1.0"
SCHEMA_KEY = "pmdco"
DEFINITION = URIRef("http://purl.obolibrary.org/obo/IAO_0000115")
SYNONYMS = (
    SKOS.altLabel,
    URIRef("http://www.geneontology.org/formats/oboInOwl#hasExactSynonym"),
)


@dataclass(frozen=True)
class TaxonomyTerm:
    id: str
    uri: str
    label: str
    definition: str | None
    synonyms: tuple[str, ...]
    parents: tuple[str, ...]
    anchorable: bool
    deprecated: bool

    def payload(self) -> dict[str, Any]:
        return {"id": self.id, "uri": self.uri, "label": self.label,
                "definition": self.definition, "synonyms": list(self.synonyms),
                "parents": list(self.parents), "anchorable": self.anchorable,
                "deprecated": self.deprecated}


@dataclass(frozen=True)
class PmdcoTaxonomy:
    version: str
    version_iri: str
    terms: tuple[TaxonomyTerm, ...]
    metadata: dict[str, Any]
    payload_bytes: bytes

    def snapshots(self) -> dict[tuple[str, str], ElementSnapshot]:
        # is_a parents are taxonomy relationships, not schema containment paths.
        return {(SCHEMA_KEY, term.id): capture_snapshot(name=term.label,
                source_version=self.version) for term in self.terms if term.anchorable}


def _texts(graph: Graph, subject: URIRef, predicates: tuple[URIRef, ...]) -> list[str]:
    values = {value for predicate in predicates for value in graph.objects(subject, predicate)
              if isinstance(value, Literal)}
    ordered = sorted(values, key=lambda value: (
        0 if value.language and value.language.lower().startswith("en") else
        1 if value.language is None else 2, str(value).casefold(), str(value)))
    return list(dict.fromkeys(str(value) for value in ordered))


def parse_taxonomy(
    data: bytes, *, version: str, metadata: dict[str, Any] | None = None,
) -> PmdcoTaxonomy:
    """Read local Turtle, including named parents and explicitly declared classes.

    Imported named ancestors stay as URI-identified context. Anonymous OWL
    restrictions are not terms. All named parents survive, including cycles;
    clients must traverse with a visited set rather than assuming a tree.
    """
    graph = Graph().parse(data=data.decode("utf-8"), format="turtle", publicID=NAMESPACE)
    ontology = URIRef(NAMESPACE)
    version_iri = f"{NAMESPACE}{version}"
    if set(graph.objects(ontology, OWL.versionIRI)) != {URIRef(version_iri)}:
        raise ValueError(f"PMDco must declare exactly version IRI {version_iri}")
    if any(graph.triples((None, OWL.imports, None))):
        raise ValueError("Offline PMDco must contain its imports; unresolved owl:imports found")
    declared = {subject for subject in graph.subjects(RDF.type, OWL.Class)
                if isinstance(subject, URIRef)}
    parents: dict[URIRef, set[URIRef]] = {}
    for subject, parent in graph.subject_objects(RDFS.subClassOf):
        if isinstance(subject, URIRef) and isinstance(parent, URIRef):
            parents.setdefault(subject, set()).add(parent)
    nodes = declared | set(parents) | {p for values in parents.values() for p in values}

    def identifier(uri: URIRef) -> str:
        value = str(uri)
        if value.startswith(NAMESPACE):
            value = "pmdco:" + value[len(NAMESPACE):]
            parse_element_id(value)  # Never silently change a term's URI on export.
        return value

    terms = []
    for uri in nodes:
        labels = _texts(graph, uri, (RDFS.label, SKOS.prefLabel))
        definitions = _texts(graph, uri, (SKOS.definition, DEFINITION, RDFS.comment))
        fallback = str(uri).rsplit("/", 1)[-1].rsplit("#", 1)[-1]
        deprecated = any(str(value).lower() in {"true", "1"}
                         for value in graph.objects(uri, OWL.deprecated))
        terms.append(TaxonomyTerm(
            id=identifier(uri), uri=str(uri), label=labels[0] if labels else fallback,
            definition=definitions[0] if definitions else None,
            synonyms=tuple(dict.fromkeys(labels[1:] + _texts(graph, uri, SYNONYMS))),
            parents=tuple(sorted(identifier(p) for p in parents.get(uri, ()))),
            anchorable=uri in declared and str(uri).startswith(NAMESPACE), deprecated=deprecated,
        ))
    terms.sort(key=lambda term: (term.label.casefold(), term.id))
    if not any(term.anchorable for term in terms):
        raise ValueError("PMDco contains no declared PMDco classes")
    info = {**(metadata or {}), "version": version, "version_iri": version_iri,
            "schema": SCHEMA_KEY, "term_count": len(terms),
            "anchor_count": sum(term.anchorable for term in terms)}
    payload = json.dumps({**info, "terms": [term.payload() for term in terms]},
                         sort_keys=True, separators=(",", ":")).encode()
    return PmdcoTaxonomy(version, version_iri, tuple(terms), info, payload)


def load_bundled() -> PmdcoTaxonomy:
    """Load and verify the bundled release and license from package resources."""
    root = files("schematerial.ontologies").joinpath("assets")
    manifest = json.loads(root.joinpath("pmdco.json").read_text())
    if (manifest["version"] != VERSION or manifest["version_iri"] != NAMESPACE + VERSION
            or manifest["namespace"] != NAMESPACE):
        raise ValueError("Bundled PMDco manifest does not match the pinned version")
    data = root.joinpath(manifest["artifact"]).read_bytes()
    license_data = root.joinpath(manifest["license_file"]).read_bytes()
    for value, expected in ((data, manifest["sha256"]),
                            (license_data, manifest["license_sha256"])):
        if hashlib.sha256(value).hexdigest() != expected:
            raise ValueError("Bundled PMDco checksum mismatch")
    return parse_taxonomy(data, version=VERSION, metadata={
        key: manifest[key] for key in ("sha256", "release_url", "license", "license_url",
                                     "attribution", "upstream_commit")
    })
