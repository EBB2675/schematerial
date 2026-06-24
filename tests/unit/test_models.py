import pytest

from schematerial.models.alignment import AlignmentMode, AlignmentResult
from schematerial.models.crosswalk import (
    CrosswalkMetadata,
    CrosswalkResult,
    MappingCandidate,
    MappingRelation,
    MappingStatus,
)
from schematerial.models.ontology import OntologyTerm
from schematerial.models.schema import (
    CoordinateFrame,
    Entity,
    SchemaField,
    SchemaModel,
    SemanticType,
)

# --- SemanticType ---


def test_semantic_type_is_str() -> None:
    assert SemanticType.ENERGY == "energy"
    assert SemanticType.BANDGAP == "band_gap"
    assert SemanticType.UNKNOWN == "unknown"


def test_semantic_type_all_values() -> None:
    expected = {
        "energy", "length", "force", "stress", "charge", "spin",
        "temperature", "pressure", "band_gap", "k_point", "atomic_position",
        "lattice_parameter", "identifier", "label", "flag", "unknown",
    }
    assert {v.value for v in SemanticType} == expected


# --- CoordinateFrame ---


def test_coordinate_frame_values() -> None:
    assert CoordinateFrame.CARTESIAN == "cartesian"
    assert CoordinateFrame.FRACTIONAL == "fractional"
    assert CoordinateFrame.RECIPROCAL == "reciprocal"
    assert CoordinateFrame.NONE == "none"


# --- SchemaField ---


def test_schema_field_requires_path_and_label() -> None:
    f = SchemaField(path="run.calculation.energy", label="energy_total")
    assert f.path == "run.calculation.energy"
    assert f.label == "energy_total"


def test_schema_field_defaults() -> None:
    f = SchemaField(path="x", label="x")
    assert f.datatype == "unknown"
    assert f.shape is None
    assert f.unit is None
    assert f.unit_normalized is None
    assert f.cardinality == "one"
    assert f.semantic_type == SemanticType.UNKNOWN
    assert f.coordinate_frame == CoordinateFrame.NONE
    assert f.per_atom is False
    assert f.per_unit_cell is False
    assert f.spin_channel is None
    assert f.ontology_terms == []
    assert f.embedding is None
    assert f.examples == []
    assert f.constraints == {}
    assert f.source_path_raw is None


def test_schema_field_scientific_flags() -> None:
    f = SchemaField(
        path="attributes.energy_per_atom",
        label="energy_per_atom",
        unit="eV",
        semantic_type=SemanticType.ENERGY,
        per_atom=True,
        datatype="float",
    )
    assert f.per_atom is True
    assert f.semantic_type == SemanticType.ENERGY
    assert f.unit == "eV"


def test_schema_field_with_shape() -> None:
    f = SchemaField(path="atoms.positions", label="positions", shape=[None, 3])
    assert f.shape == [None, 3]


def test_schema_field_with_ontology_term() -> None:
    term = OntologyTerm(
        uri="https://emmo.info/emmo#TotalElectronicEnergy",
        label="TotalElectronicEnergy",
        ontology="EMMO",
        match_type="exact",
        confidence=1.0,
    )
    f = SchemaField(
        path="calculation.energy.total",
        label="energy_total",
        ontology_terms=[term],
    )
    assert len(f.ontology_terms) == 1
    assert f.ontology_terms[0].uri == "https://emmo.info/emmo#TotalElectronicEnergy"


# --- Entity ---


def test_entity_defaults() -> None:
    e = Entity(name="calculation")
    assert e.fields == []
    assert e.parent is None
    assert e.description is None


def test_entity_with_parent() -> None:
    e = Entity(name="energy", parent="calculation")
    assert e.parent == "calculation"


def test_entity_with_fields() -> None:
    f = SchemaField(path="x", label="x")
    e = Entity(name="root", fields=[f])
    assert len(e.fields) == 1


# --- SchemaModel ---


def test_schema_model_format_default() -> None:
    m = SchemaModel(name="test")
    assert m.format == "unknown"
    assert m.source_file is None
    assert m.entities == []
    assert m.metadata == {}


def test_schema_model_with_format() -> None:
    m = SchemaModel(name="NOMAD Metainfo", format="nomad", version="1.0")
    assert m.format == "nomad"
    assert m.version == "1.0"


# --- MappingRelation ---


def test_mapping_relation_phase0_vocab() -> None:
    assert MappingRelation.EXACT == "exact"
    assert MappingRelation.CLOSE == "close"
    assert MappingRelation.BROADER == "broader"
    assert MappingRelation.NARROWER == "narrower"
    assert MappingRelation.NONE == "none"


def test_mapping_relation_phase1_vocab() -> None:
    assert MappingRelation.UNIT_CONVERSION == "unit_conversion"
    assert MappingRelation.PER_ATOM_RESCALE == "per_atom_rescale"
    assert MappingRelation.SPLIT == "split"
    assert MappingRelation.MERGE == "merge"
    assert MappingRelation.DERIVED == "derived"
    assert MappingRelation.AMBIGUOUS == "ambiguous"


# --- MappingStatus ---


def test_mapping_status_values() -> None:
    assert MappingStatus.AUTO_ACCEPTED == "auto_accepted"
    assert MappingStatus.NEEDS_REVIEW == "needs_review"
    assert MappingStatus.LIKELY_NO_MATCH == "likely_no_match"


# --- MappingCandidate ---


def test_mapping_candidate_minimal() -> None:
    c = MappingCandidate(
        source_field="energy_total",
        target_field="total_energy",
        relation=MappingRelation.EXACT,
    )
    assert c.id == ""
    assert c.score is None
    assert c.scores == {}
    assert c.status == MappingStatus.NEEDS_REVIEW
    assert c.evidence == []


def test_mapping_candidate_with_score_breakdown() -> None:
    c = MappingCandidate(
        id="map_001",
        source_field="energy_total",
        source_path="run[0].calculation[-1].energy.total.value",
        target_field="total_energy",
        target_path="attributes._nomad_total_energy",
        relation=MappingRelation.UNIT_CONVERSION,
        score=0.91,
        scores={"name": 0.85, "unit": 1.0, "semantic_type": 1.0},
        status=MappingStatus.AUTO_ACCEPTED,
        evidence=["Units compatible: J → eV", "SemanticType: ENERGY (exact match)"],
    )
    assert c.score == pytest.approx(0.91)
    assert c.scores["unit"] == pytest.approx(1.0)
    assert c.status == MappingStatus.AUTO_ACCEPTED
    assert len(c.evidence) == 2


def test_mapping_candidate_status_derived_from_score() -> None:
    def _make(score: float) -> MappingCandidate:
        return MappingCandidate(
            source_field="a", target_field="b", relation=MappingRelation.EXACT, score=score
        )

    assert _make(0.90).status == MappingStatus.AUTO_ACCEPTED
    assert _make(0.85).status == MappingStatus.AUTO_ACCEPTED
    assert _make(0.60).status == MappingStatus.NEEDS_REVIEW
    assert _make(0.40).status == MappingStatus.NEEDS_REVIEW
    assert _make(0.20).status == MappingStatus.LIKELY_NO_MATCH
    assert _make(0.00).status == MappingStatus.LIKELY_NO_MATCH


def test_mapping_candidate_no_score_keeps_default_status() -> None:
    c = MappingCandidate(
        source_field="a", target_field="b", relation=MappingRelation.EXACT
    )
    assert c.status == MappingStatus.NEEDS_REVIEW


# --- CrosswalkMetadata ---


def test_crosswalk_metadata_defaults() -> None:
    m = CrosswalkMetadata(source_model="nomad", target_model="optimade")
    assert m.review_status == "draft"
    assert isinstance(m.schematerial_version, str) and m.schematerial_version != ""
    assert m.n_accepted == 0
    assert m.n_needs_review == 0
    assert m.n_no_match == 0
    assert m.created_at is not None


# --- CrosswalkResult ---


def _make_result(*candidates: MappingCandidate) -> CrosswalkResult:
    meta = CrosswalkMetadata(source_model="nomad", target_model="optimade")
    return CrosswalkResult(metadata=meta, mappings=list(candidates))


def test_crosswalk_result_get_mapping_found() -> None:
    c = MappingCandidate(
        source_field="energy_total",
        target_field="total_energy",
        relation=MappingRelation.EXACT,
    )
    result = _make_result(c)
    found = result.get_mapping("energy_total", "total_energy")
    assert found is not None
    assert found.relation == MappingRelation.EXACT


def test_crosswalk_result_get_mapping_miss() -> None:
    c = MappingCandidate(
        source_field="energy_total",
        target_field="total_energy",
        relation=MappingRelation.EXACT,
    )
    result = _make_result(c)
    assert result.get_mapping("energy_total", "nsites") is None
    assert result.get_mapping("n_atoms", "total_energy") is None


def test_crosswalk_result_empty_mappings() -> None:
    result = _make_result()
    assert result.mappings == []
    assert result.get_mapping("x", "y") is None


# --- AlignmentResult ---


def test_alignment_result() -> None:
    meta = CrosswalkMetadata(source_model="nomad", target_model="optimade")
    crosswalk = CrosswalkResult(metadata=meta)
    result = AlignmentResult(
        mode=AlignmentMode.SCHEMA_TO_SCHEMA,
        crosswalk=crosswalk,
    )
    assert result.mode == AlignmentMode.SCHEMA_TO_SCHEMA


# --- OntologyTerm ---


def test_ontology_term_match_types() -> None:
    for match_type in ("exact", "partial", "ancestor", "inferred"):
        term = OntologyTerm(
            uri="https://example.org/concept",
            label="TestConcept",
            ontology="EMMO",
            match_type=match_type,  # type: ignore[arg-type]
            confidence=0.9,
        )
        assert term.match_type == match_type


def test_ontology_term_invalid_match_type() -> None:
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        OntologyTerm(
            uri="https://example.org/concept",
            label="TestConcept",
            ontology="EMMO",
            match_type="wrong",  # type: ignore[arg-type]
            confidence=0.9,
        )


# --- JSON roundtrip ---


def test_crosswalk_result_json_roundtrip() -> None:
    meta = CrosswalkMetadata(
        source_model="nomad",
        source_version="1.0",
        target_model="optimade",
        target_version="1.1",
    )
    c = MappingCandidate(
        id="map_001",
        source_field="energy_total",
        target_field="total_energy",
        relation=MappingRelation.EXACT,
        score=0.91,
        scores={"name": 0.85, "unit": 1.0},
        status=MappingStatus.AUTO_ACCEPTED,
    )
    result = CrosswalkResult(metadata=meta, mappings=[c])
    serialized = result.model_dump_json()
    restored = CrosswalkResult.model_validate_json(serialized)
    assert len(restored.mappings) == 1
    assert restored.mappings[0].id == "map_001"
    assert restored.metadata.source_model == "nomad"
