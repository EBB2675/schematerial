# Schematerial: Technical Plan (Revised)

> Build the hardest case first. A system that can align NOMAD ↔ OPTIMADE can align anything simpler.

---

## What kind of problem this actually is

Schematerial is a **semantic crosswalk compiler**. The difficulty comes from three orthogonal sources that generic schema tools ignore:

### 1. Structural heterogeneity

Materials schemas are not just renamed versions of each other — they are structurally different.

NOMAD metainfo is a deeply nested section hierarchy:

```
run → calculation → energy → total   (eV)
```

OPTIMADE is flatter and REST-API-shaped:

```
attributes.energy_above_hull   (eV/atom)
```

NeXus is an HDF5 tree accessed by path. CIF is flat key-value with crystallographic conventions. Emmet (Materials Project) is Pydantic-modelled with polymorphic types and nested validators.

Structural normalization is non-trivial. You cannot compare `a.b.c.d` against `x.y` without understanding what each path represents physically.

### 2. Scientific semantic ambiguity

Field names that look close are often not equivalent:

```
energy          ← could be total, per-atom, per-unit-cell, electronic, free energy, ...
total_energy    ← could be self-consistent or non-self-consistent
E_total         ← same quantity? depends on the DFT code
scf_energy      ← explicitly the self-consistent field result
free_energy     ← F = E - TS, not the same at finite temperature
```

This is not a naming convention problem. These are physically distinct quantities that require domain understanding to align correctly.

### 3. Scientific precision requirements

A wrong mapping in a materials database is not a user-experience bug. It is a scientific error. The system must:

- Express uncertainty honestly
- Never silently guess
- Make every alignment decision traceable and reversible
- Flag ambiguity loudly rather than hiding it

---

## Target ecosystem

Scope the first version tightly. Cover these schemas and no others until they work well.

### Priority 1 — support in Phases 1–2

| Schema | Format | Why it matters |
|---|---|---|
| NOMAD metainfo | JSON / Python classes | Largest open-access materials database. The reference. |
| OPTIMADE | REST API JSON spec | Cross-database query standard. Used by 20+ databases. |
| CIF / mCIF | Key-value text | Universal crystallography format. In every lab. |
| Emmet (Materials Project) | Pydantic JSON | 150k+ structures. Widely used in ML for materials. |

### Priority 2 — support in Phase 3+

| Schema / Ontology | Format | Why |
|---|---|---|
| NeXus | HDF5 tree | Experimental data standard for synchrotrons, neutron sources, XRD. Strong candidate for discovery pair with NOMAD experimental schemas. |
| PMDco | OWL / TTL | Platform MaterialDigital Core Ontology. Built on EMMO + BFO. Covers computational and experimental materials data. Part of the NFDI4Mat ecosystem. **Schema-to-ontology alignment mode.** |
| AFLOW | JSON | Large DFT database with its own naming conventions. |
| Custom lab schemas | YAML / CSV | The long tail. Every group has one. |

Note: NOMAD has experimental schemas (XRD, XPS, TEM, optical spectroscopy, ellipsometry) that live alongside its computational schemas. NeXus covers many of the same techniques. This overlap makes NeXus ↔ NOMAD experimental a same-domain alignment problem — not a cross-domain one.

### Canonical test pairs

Two distinct roles: **calibration pairs** (ground truth exists, used to verify Schematerial reproduces known alignments) and **discovery pairs** (no existing crosswalk, these are what the tool is actually for).

#### Calibration pairs — ground truth exists

| Pair | Why |
|---|---|
| NOMAD ↔ OPTIMADE | NOMAD is an OPTIMADE provider — the translation already exists as production adapter code in the NOMAD codebase. Use this to check whether Schematerial can reproduce a known-good alignment. Not a discovery problem. |
| CIF ↔ OPTIMADE | OPTIMADE spec includes CIF field mappings. Again, ground truth is documented. |

Use calibration pairs to tune scoring weights and verify calibration. Do not use them to claim the tool solves hard problems — the answers are already written.

#### Discovery pairs — schema-to-schema

Both sides are data schemas. Output is a data transform.

| Pair | Domain | Why it is hard |
|---|---|---|
| NOMAD ↔ Emmet | computational ↔ computational | Both describe DFT calculations. Structurally very different (NOMAD: deep section hierarchy; Emmet: flat Pydantic JSON). No existing crosswalk. |
| NOMAD ↔ AFLOW | computational ↔ computational | AFLOW has its own naming conventions and unit choices. Large database. No formal crosswalk to NOMAD. |
| NeXus ↔ NOMAD experimental | experimental ↔ experimental | Both cover the same techniques (XRD, XPS, TEM, spectroscopy) but with different community conventions. NeXus uses HDF5 application definitions; NOMAD uses its metainfo section hierarchy. Same physical measurements, structurally divergent. |

**NeXus ↔ NOMAD experimental is a stronger pair than it looks.** Scoping to one technique (XRD: `NXxrd` ↔ `XRDMeasurement`) gives a complete, verifiable alignment where most fields should have counterparts.

Start with **NOMAD ↔ Emmet** (computational) and **NeXus ↔ NOMAD experimental (XRD only)** in parallel as the two primary discovery cases.

#### Discovery pairs — schema-to-ontology

One side is a data schema; the other is an OWL ontology. Output is **semantic annotation**, not a data transform.

| Pair | Why |
|---|---|
| NOMAD Metainfo ↔ PMDco | PMDco (Platform MaterialDigital Core Ontology) is an OWL ontology built on EMMO + BFO, developed within the German NFDI4Mat / MaterialDigital initiative. It covers computational (simulation) and experimental (process, characterization) materials data. NOMAD is also developed in Germany (FHI Berlin). Grounding NOMAD fields to PMDco concepts would make NOMAD data formally FAIR-compliant within that ecosystem. No existing formal crosswalk. PMDco is already in OWL/TTL — parseable by the ontology layer Schematerial already needs. |

**Schema-to-ontology mode is architecturally different.** The output is not a `TransformGraph` — it is a semantic annotation map:

```yaml
# Example schema-to-ontology crosswalk output
field: run.calculation[-1].energy.total
pmdco_concept: https://w3id.org/pmd/co/TotalEnergy
emmo_concept:  https://emmo.info/emmo#TotalElectronicEnergy
qudt_unit:     https://qudt.org/vocab/unit/EV
match_type:    exact
confidence:    0.91
```

And optionally, a serializer that exports NOMAD data as RDF/JSON-LD using PMDco terms — the entry point for genuine FAIR-data compliance.

This is the most valuable long-term use case for research data infrastructure. PMDco grounding turns Schematerial from a crosswalk tool into a semantic layer for materials databases.

---

## Two alignment modes

Schematerial must support two fundamentally different alignment tasks. They share the parsing, profiling, and scoring layers but diverge at output.

### Mode A — schema-to-schema

Both inputs are data schemas. Output is a data transform.

```
schema A  +  schema B  →  crosswalk.yaml  +  transform.py
```

Used for: NOMAD ↔ Emmet, NeXus ↔ NOMAD experimental, NOMAD ↔ AFLOW.

### Mode B — schema-to-ontology

One input is a data schema; the other is an OWL ontology. Output is a semantic annotation map, not a transform.

```
schema  +  ontology.ttl  →  annotation.yaml  (+  optional RDF/JSON-LD serializer)
```

Used for: NOMAD Metainfo ↔ PMDco.

The annotation map says "field X is an instance of ontology concept Y." It does not say "move field X to path Z." These are different things and must not be conflated.

Both modes use the same `AlignmentPipeline`. The mode is inferred from the input type: if the right-hand input parses as an OWL ontology (TTL/RDF), run in mode B.

---

## Core architecture

```
                  ┌──────────────────────────┐
                  │  Input A (schema)          │
                  │  NOMAD / OPTIMADE / CIF /  │
                  │  Emmet / NeXus / YAML      │
                  └────────────┬───────────────┘
                               │
                  ┌──────────────────────────┐
                  │  Input B                   │
                  │  schema  OR  ontology.ttl  │
                  └────────────┬───────────────┘
                               │
                               ▼
                  ┌──────────────────────────┐
                  │  Format Parsers            │
                  │  schema adapters +         │
                  │  OWL/TTL ontology reader   │
                  └────────────┬───────────────┘
                               │
                               ▼
                  ┌──────────────────────────┐
                  │  Internal Schema IR        │
                  │  SchemaModel → Entity →    │
                  │  Field (typed, rich)        │
                  └────────────┬───────────────┘
                               │
                               ▼
                  ┌──────────────────────────┐
                  │  Semantic Profiling        │
                  │  units · ontology ·        │
                  │  embeddings · context      │
                  └────────────┬───────────────┘
                               │
                               ▼
                  ┌──────────────────────────┐
                  │  Mapping Engine            │
                  │  multi-signal scoring      │
                  │  + LLM evidence pass       │
                  └───────┬──────────┬─────────┘
                          │          │
               MODE A     │          │    MODE B
                          │          │
          ┌───────────────▼──┐  ┌────▼──────────────────┐
          │  Human Report     │  │  Human Report           │
          │  + Transform Graph│  │  + Semantic Annotation  │
          │  crosswalk.yaml   │  │  annotation.yaml        │
          └──────┬────────────┘  └────┬────────────────────┘
                 │                    │
    ┌────────────┼──────┐      ┌──────▼──────────────┐
    ▼            ▼      ▼      │  Optional RDF export  │
Python       JSONata   JQ      │  JSON-LD / Turtle     │
                               └───────────────────────┘
```

The transform graph (Mode A) and semantic annotation map (Mode B) are explained in their own sections below.

---

## Internal schema representation

Use Pydantic throughout. This gives typed models, validation, JSON serialization, and later JSON Schema export for free.

```python
from enum import Enum
from typing import Literal

class SemanticType(str, Enum):
    """Controlled vocabulary of physical quantity types."""
    ENERGY = "energy"
    LENGTH = "length"
    FORCE = "force"
    STRESS = "stress"
    CHARGE = "charge"
    SPIN = "spin"
    TEMPERATURE = "temperature"
    PRESSURE = "pressure"
    BANDGAP = "band_gap"
    KPOINT = "k_point"
    ATOMIC_POSITION = "atomic_position"
    LATTICE_PARAMETER = "lattice_parameter"
    IDENTIFIER = "identifier"
    LABEL = "label"
    FLAG = "flag"
    UNKNOWN = "unknown"

class CoordinateFrame(str, Enum):
    CARTESIAN = "cartesian"
    FRACTIONAL = "fractional"
    RECIPROCAL = "reciprocal"
    NONE = "none"

class Field(BaseModel):
    path: str                              # full dot-path in source schema
    label: str                             # human name
    description: str | None = None
    datatype: str                          # "float", "int", "str", "list[float]", ...
    shape: list[int | None] | None = None  # e.g. [None, 3] for Nx3 array
    unit: str | None = None                # raw string: "eV", "angstrom", "eV/angstrom"
    unit_normalized: str | None = None     # QUDT canonical form
    cardinality: Literal["one", "many", "optional"] = "one"
    semantic_type: SemanticType = SemanticType.UNKNOWN
    coordinate_frame: CoordinateFrame = CoordinateFrame.NONE
    per_atom: bool = False                 # energy per atom vs total?
    per_unit_cell: bool = False
    spin_channel: int | None = None
    ontology_terms: list[OntologyTerm] = []
    embedding: list[float] | None = None   # populated by semantic profiling
    examples: list[Any] = []
    constraints: dict[str, Any] = {}
    source_path_raw: str | None = None     # original path before normalization

class Entity(BaseModel):
    name: str
    description: str | None = None
    fields: list[Field] = []
    parent: str | None = None             # for nested entity hierarchies

class SchemaModel(BaseModel):
    name: str
    version: str | None = None
    format: str                           # "nomad", "optimade", "cif", "emmet", ...
    source_file: str | None = None
    entities: list[Entity] = []
    metadata: dict[str, Any] = {}

class OntologyTerm(BaseModel):
    uri: str                              # e.g. "https://emmo.info/emmo#TotalElectronicEnergy"
    label: str
    ontology: str                         # "EMMO", "MatOnto", "QUDT"
    match_type: Literal["exact", "partial", "ancestor", "inferred"]
    confidence: float
```

The additions over the original plan that matter:

- `semantic_type` — a controlled vocabulary that enables cross-schema physical quantity matching without relying on field names
- `coordinate_frame` — critical for atomic positions and k-points
- `per_atom`, `per_unit_cell` — catches a very common class of silent errors (OPTIMADE reports energy per atom; NOMAD reports total energy)
- `shape` — array structure is essential for split/merge detection
- `unit_normalized` — normalizes raw unit strings to a canonical form using QUDT before comparison

---

## Semantic profiling

This layer enriches each field before mapping begins.

### Units

Use `pint` for unit parsing and compatibility checking. Normalize all units to QUDT canonical forms for ontology grounding.

```python
# catches: eV, electron_volt, electronvolt, eV/atom — all the same
unit_registry = pint.UnitRegistry()
canonical = unit_registry.parse_expression("eV").to_base_units()
```

Unit compatibility is not binary. Define levels:

```
identical       -> same unit, no conversion needed
compatible      -> different units, same dimension (eV vs J)
per_atom_diff   -> compatible but one is normalized per atom
incompatible    -> different physical dimension
unknown         -> unit missing or unparseable
```

The `per_atom_diff` case is the most common source of silent scientific errors. Flag it loudly.

### Ontology grounding

Target these ontologies in order of priority:

| Ontology | Purpose |
|---|---|
| EMMO (European Materials Modelling Ontology) | Physical quantities, materials properties, simulation quantities |
| QUDT (Quantities, Units, Dimensions, Types) | Canonical units and quantity kinds |
| MatOnto | Materials-specific property terms |
| PROV-O | Provenance: which calculation produced which result |

Grounding strategy:

```
1. Exact label match against EMMO/MatOnto labels and synonyms
2. SPARQL query against local TTL file for broader/narrower matches
3. Fuzzy label match (rapidfuzz) against ontology labels, threshold > 0.85
4. LLM-assisted grounding as last resort, flagged as "inferred"
```

Grounding is done once during semantic profiling and stored in `field.ontology_terms`. The mapping engine reads ontology terms; it never queries the ontology directly.

Store ontology TTL files locally. Do not rely on remote SPARQL endpoints during alignment — they are unreliable and make the tool fragile.

Example grounding output:

```yaml
field: calculation.energy.total
ontology_terms:
  - uri: https://emmo.info/emmo#TotalElectronicEnergy
    label: TotalElectronicEnergy
    ontology: EMMO
    match_type: exact
    confidence: 1.0
  - uri: https://qudt.org/vocab/quantitykind/Energy
    label: Energy
    ontology: QUDT
    match_type: ancestor
    confidence: 0.85
```

### Embeddings

Do not use generic sentence-transformers for materials science vocabulary.

Use **MatBERT** (LBNL, 2021) or **MatSciBERT** — both are BERT models fine-tuned on materials science literature. They produce meaningfully better embeddings for domain terms like `scf_energy`, `Hubbard_U`, `band_gap`, `k_mesh_density`.

```
Primary:  MatBERT (bert-base-cased fine-tuned on ~2M materials papers)
Fallback: sentence-transformers/all-MiniLM-L6-v2 (if MatBERT unavailable)
```

Compute embeddings from: `f"{field.label}. {field.description}. Unit: {field.unit}. Context: {entity.name}"`

This composite prompt outperforms embedding field names alone.

Cache embeddings keyed by a hash of the input string. Re-embedding 500-field schemas on every run is expensive and pointless.

---

## Mapping engine

### Scoring signals

Each candidate pair `(source_field, target_field)` is scored across these signals:

| Signal | Method | Weight (tunable) |
|---|---|---|
| Name similarity | rapidfuzz token_sort_ratio | 0.10 |
| Description similarity | cosine(embedding_a, embedding_b) | 0.20 |
| Semantic type match | exact match on SemanticType enum | 0.15 |
| Unit compatibility | pint dimensional analysis | 0.15 |
| Ontology overlap | shared EMMO ancestor depth | 0.20 |
| Structural context | parent entity similarity | 0.10 |
| Shape compatibility | array shape match | 0.05 |
| LLM reasoning | 0-1 score from evidence pass | 0.05 |

Weights are a starting point. Calibrate them against the NOMAD ↔ OPTIMADE ground-truth pair once you have it.

The LLM score is **5% weight by design**. It is used for tiebreaking and explanation, not for driving the decision.

### Relation types

Not all mappings are one-to-one equivalences. Represent the full taxonomy:

```python
class MappingRelation(str, Enum):
    EQUIVALENT      = "equivalent"       # same physical quantity, same unit dimension
    BROADER         = "broader"          # source is more specific than target
    NARROWER        = "narrower"         # source is more general than target
    UNIT_CONVERSION = "unit_conversion"  # equivalent quantity, different unit
    PER_ATOM_RESCALE= "per_atom_rescale" # one is total, other is per-atom
    SPLIT           = "split"            # 1 source field → N target fields
    MERGE           = "merge"            # N source fields → 1 target field
    DERIVED         = "derived"          # target is computed from source (not just remapped)
    AMBIGUOUS       = "ambiguous"        # plausible but unclear; needs human review
    NO_MATCH        = "no_match"         # no credible counterpart found
```

### Confidence calibration

Raw composite scores are not probabilities. Do not label them as confidence without calibration.

After building the NOMAD ↔ OPTIMADE ground-truth crosswalk manually, use it as a calibration set:

- Apply isotonic regression to map raw composite scores to calibrated probabilities
- Report calibrated confidence with the calibration set size noted in metadata
- Flag mappings above 0.85 as `auto_accept_candidate`, below 0.40 as `likely_no_match`, between 0.40–0.85 as `needs_review`

Until you have a calibration set, report raw scores explicitly labeled as `score` not `confidence`. Do not pretend calibration you have not done.

---

## Transform model: the declarative graph

This is the most important architectural decision in this revised plan.

**Never generate Python directly from an LLM.**

Instead, define a declarative transform graph as a Pydantic model. Compile the graph to Python (or JSONata, or JQ). The graph is what you version, review, and store. The compiled output is a build artifact.

### Transform operation types

```python
class TransformOp(BaseModel):
    """Base class for all transform operations."""
    op: str

class IdentityOp(TransformOp):
    op: Literal["identity"]
    source_path: str      # JSONPath
    target_path: str      # JSONPath

class UnitConversionOp(TransformOp):
    op: Literal["unit_conversion"]
    source_path: str
    target_path: str
    from_unit: str
    to_unit: str
    factor: float         # computed at plan time: never at runtime
    offset: float = 0.0   # for affine conversions (e.g. Celsius ↔ Kelvin)

class PerAtomRescaleOp(TransformOp):
    op: Literal["per_atom_rescale"]
    source_path: str
    target_path: str
    n_atoms_path: str     # path to the atom count field in source
    direction: Literal["total_to_per_atom", "per_atom_to_total"]

class SplitOp(TransformOp):
    op: Literal["split"]
    source_path: str
    targets: list[tuple[str, str]]  # [(target_path, selector_expression), ...]

class MergeOp(TransformOp):
    op: Literal["merge"]
    sources: list[str]    # source paths
    target_path: str
    merge_expression: str # e.g. "zip(a, b, c)" — kept simple and auditable

class ArrayIndexOp(TransformOp):
    op: Literal["array_index"]
    source_path: str      # supports list indexing: "eigenvalues[0]"
    target_path: str
    index: int | str      # int for positional, str for named/spin channel

class EnumRemapOp(TransformOp):
    op: Literal["enum_remap"]
    source_path: str
    target_path: str
    mapping: dict[str, str]   # {"GGA": "GGA-PBE", "LDA": "LDA-PW"}
    fallback: str | None = None

class ConditionalOp(TransformOp):
    op: Literal["conditional"]
    condition_path: str
    condition_value: Any
    then_op: "TransformOp"
    else_op: "TransformOp | None" = None

TransformGraph = list[TransformOp]
```

### Why this matters

A `UnitConversionOp` with `factor: 1.602176634e-19` is:
- Human-reviewable
- Versionable in git
- Compilable to Python, JSONata, or JQ
- Testable in isolation
- Correctable without regenerating everything

A raw LLM-generated Python function is none of these things.

### Compilation targets

```python
def compile_to_python(graph: TransformGraph) -> str:
    """Generates a transform.py file from the declarative graph."""
    ...

def compile_to_jsonata(graph: TransformGraph) -> str:
    """Generates a JSONata expression for web/API use."""
    ...
```

The compiler lives in `src/schematerial/export/compiler.py`. It is deterministic. Given the same graph, it always produces the same output.

---

## Crosswalk versioning

Research schemas evolve. The crosswalk must be versioned.

### Schema version tracking

```yaml
metadata:
  source_model: nomad-metainfo
  source_version: "1.2.0"
  target_model: optimade
  target_version: "1.1.0"
  schematerial_version: "0.3.1"
  created_at: "2026-06-20T10:00:00Z"
  review_status: draft
  calibration_set: "nomad-optimade-gt-v1"
```

### Diff tool

```bash
schematerial diff runs/v1/crosswalk.yaml runs/v2/crosswalk.yaml
```

Output:

```
+ map_031: calculation.forces → results.forces.total  [new]
~ map_001: relation changed from ambiguous → equivalent  [updated]
- map_019: calculation.spin_moment → (removed, no match in target v1.1)  [deleted]
```

This is how you communicate schema migration impact to downstream users.

### Migration paths

When a target schema version increments, flag which accepted mappings may be affected and require re-review. Do not silently carry over mappings from one schema version to another.

---

## AI agent layer

Keep agents small, typed, and bounded. Each agent has a defined input type, output type, and failure mode.

### Agent interfaces

```python
class AgentResult(BaseModel):
    success: bool
    output: Any
    reasoning: str | None = None
    confidence: float | None = None
    flagged_for_review: bool = False

class SchemaInspectorAgent:
    """
    Input:  raw schema file (any supported format)
    Output: SchemaModel
    Role:   parse and normalize only — no mapping
    """

class OntologyGroundingAgent:
    """
    Input:  Field
    Output: list[OntologyTerm]
    Role:   assign EMMO/QUDT terms to a field
            first tries deterministic SPARQL, falls back to LLM
    """

class CandidateMappingAgent:
    """
    Input:  (Field, list[Field])  — one source field + all target fields
    Output: list[MappingCandidate] with scores
    Role:   generates candidates; does NOT accept/reject them
    """

class AmbiguityReviewerAgent:
    """
    Input:  MappingCandidate where composite score is in [0.40, 0.85]
    Output: AmbiguityReport with specific questions for human reviewer
    Role:   names what is unclear and what evidence exists on each side
            never decides — only articulates the ambiguity
    """

class TransformGeneratorAgent:
    """
    Input:  accepted MappingCandidate
    Output: TransformOp (one of the typed ops above)
    Role:   determines which op type is needed and populates it
            never generates raw Python
    """

class ReportWriterAgent:
    """
    Input:  CrosswalkResult (all mappings, scores, statuses)
    Output: report.md string
    Role:   prose generation only
    """
```

### Orchestration

A plain Python `AlignmentPipeline` class is enough for Phases 1–3. Do not introduce LangGraph until the pipeline has genuine branching logic that becomes unmaintainable as plain Python.

```python
class AlignmentPipeline:
    def run(self, source: SchemaModel, target: SchemaModel) -> AlignmentResult:
        source_profiles = self.profiler.profile(source)
        target_profiles = self.profiler.profile(target)
        candidates = self.candidate_engine.generate(source_profiles, target_profiles)
        scored = self.scorer.score(candidates)
        reviewed = self.ambiguity_reviewer.flag(scored)
        transform_graph = self.transform_generator.generate(reviewed)
        return AlignmentResult(
            crosswalk=scored,
            transform_graph=transform_graph,
        )
```

Design agent interfaces as Python protocols so they can be swapped for LangGraph nodes later without changing the pipeline structure.

---

## Known hard cases to handle explicitly

Build tests around these before claiming the system works.

### 1. Per-atom vs total energy

OPTIMADE reports `energy_above_hull` in eV/atom. NOMAD reports `calculation.energy.total` in eV.

These are not unit-conversion equivalent. They require knowing `n_atoms` at transform time. Use `PerAtomRescaleOp`.

### 2. Spin-resolved eigenvalues

One schema stores spin-up and spin-down eigenvalues in a single array indexed by spin channel. Another stores them in separate fields `eigenvalues_up` and `eigenvalues_down`.

Requires `SplitOp` + `ArrayIndexOp`. This is a structural transform, not just a rename.

### 3. Coordinate frames for atomic positions

Some schemas use fractional coordinates (relative to lattice vectors). Others use Cartesian in Angstrom. The conversion requires the lattice matrix.

This is a `DerivedOp` (computation, not just unit scaling) and must be flagged for review. Never silently apply coordinate frame transforms.

### 4. Space group representations

CIF uses Hermann-Mauguin notation (`Fm-3m`). Some schemas use the international number (225). Others use Hall notation. These are semantically equivalent but require a lookup table, not arithmetic.

Use `EnumRemapOp` with a prebuilt mapping table. Never let the LLM generate this table.

### 5. Implicit physical context

NOMAD `run.calculation[-1].energy.total` means "the energy of the last self-consistent step, which is the converged result." OPTIMADE `energy` means the same thing but the `-1` indexing is implicit.

This is an `ArrayIndexOp` plus a semantic note. Flag it explicitly in the crosswalk evidence.

---

## File formats

### `crosswalk.yaml` — the core artifact

```yaml
metadata:
  source_model: nomad-metainfo
  source_version: "1.2.0"
  target_model: optimade
  target_version: "1.1.0"
  schematerial_version: "0.3.1"
  created_at: "2026-06-20T10:00:00Z"
  review_status: draft
  score: 0.71          # mean confidence across accepted mappings
  n_accepted: 34
  n_needs_review: 12
  n_no_match: 8

mappings:
  - id: map_001
    source: run.calculation[-1].energy.total
    target: attributes.energy
    relation: unit_conversion
    score: 0.91
    datatype_compatible: true
    unit:
      source: eV
      target: eV
      compatible: true
      conversion_required: false
    context_note: >
      NOMAD uses the last calculation step implicitly;
      OPTIMADE energy refers to the converged result.
      Array indexing [-1] is baked into the transform.
    ontology_overlap:
      - EMMO:TotalElectronicEnergy
    evidence:
      - Shared EMMO term: TotalElectronicEnergy (exact match in both schemas)
      - Units identical: eV
      - MatBERT embedding cosine similarity: 0.94
    transform:
      op: array_index
      source_path: run.calculation
      index: -1
      then:
        op: identity
        source_path: energy.total
        target_path: attributes.energy
    status: needs_review
    review_note: "Verify that [-1] convention holds for all NOMAD entries."

  - id: map_002
    source: run.calculation[-1].energy.total
    target: attributes.energy_per_atom
    relation: per_atom_rescale
    score: 0.62
    evidence:
      - Same quantity but OPTIMADE normalizes by n_atoms
    transform:
      op: per_atom_rescale
      source_path: run.calculation[-1].energy.total
      target_path: attributes.energy_per_atom
      n_atoms_path: run.system[-1].atoms.n_atoms
      direction: total_to_per_atom
    status: needs_review
```

### `report.md` — for humans

```markdown
# Alignment Report: NOMAD metainfo → OPTIMADE

**Generated:** 2026-06-20  
**Status:** draft — 12 mappings require human review

---

## Summary

| Status | Count |
|---|---|
| Auto-accepted (score ≥ 0.85) | 21 |
| Needs review (0.40–0.85) | 12 |
| No match found | 8 |
| Ambiguous (flagged) | 3 |

---

## High-confidence mappings

...

## Mappings requiring review

### map_002 — energy.total → energy_per_atom

**Issue:** Source is total energy in eV. Target is per-atom energy in eV/atom.
**Required:** Confirm n_atoms path is `run.system[-1].atoms.n_atoms` for all entry types.
**Decision needed:** Accept with per-atom rescale, or reject and leave unmapped?

...

## Ambiguous mappings

...

## Unmatched source fields

...

## Unmatched target fields

...

## Required human decisions

1. [ ] map_002: confirm n_atoms path for per-atom rescale
2. [ ] map_007: spin_moment — is this the total or per-site?
...
```

### `transform.py` — compiled from the transform graph

```python
# AUTO-GENERATED by schematerial v0.3.1
# Source: nomad-metainfo v1.2.0
# Target: optimade v1.1.0
# DO NOT EDIT — edit the crosswalk.yaml transform graph and recompile
#
# schematerial compile runs/example/crosswalk.yaml --format python

from __future__ import annotations

def transform(source: dict) -> dict:
    target: dict = {}

    # map_001: run.calculation[-1].energy.total → attributes.energy
    # relation: unit_conversion (units identical, array index applied)
    _calculations = source.get("run", {}).get("calculation", [])
    if _calculations:
        _last_calc = _calculations[-1]
        _energy_total = _last_calc.get("energy", {}).get("total")
        if _energy_total is not None:
            target.setdefault("attributes", {})["energy"] = _energy_total

    # map_002: run.calculation[-1].energy.total → attributes.energy_per_atom
    # relation: per_atom_rescale (total_to_per_atom)
    _systems = source.get("run", {}).get("system", [])
    if _systems and _calculations:
        _n_atoms = _systems[-1].get("atoms", {}).get("n_atoms")
        _energy = _calculations[-1].get("energy", {}).get("total")
        if _n_atoms and _energy is not None:
            target.setdefault("attributes", {})["energy_per_atom"] = _energy / _n_atoms

    return target
```

The compiled Python is defensive by design (`.get()` throughout, no bare dict access). This is a template — the compiler generates it, not a human.

### `annotation.yaml` — schema-to-ontology output (Mode B)

The output for NOMAD ↔ PMDco alignment. No transform graph. No Python. Semantic annotations only.

```yaml
metadata:
  source_model: nomad-metainfo
  source_version: "1.2.0"
  target_ontology: PMDco
  target_ontology_version: "0.4.0"
  schematerial_version: "0.3.1"
  created_at: "2026-06-20T10:00:00Z"
  review_status: draft
  n_grounded: 41
  n_partial: 14
  n_ungrounded: 22

annotations:
  - id: ann_001
    source_field: run.calculation[-1].energy.total
    pmdco_concept: https://w3id.org/pmd/co/TotalEnergy
    emmo_concept:  https://emmo.info/emmo#TotalElectronicEnergy
    qudt_unit:     https://qudt.org/vocab/unit/EV
    match_type:    exact
    score:         0.93
    evidence:
      - PMDco:TotalEnergy label matches EMMO:TotalElectronicEnergy (shared ancestor)
      - NOMAD field description mentions "total energy of the system"
      - Units: eV → QUDT:EV (exact match)
    status: accepted

  - id: ann_002
    source_field: run.calculation[-1].forces
    pmdco_concept: https://w3id.org/pmd/co/AtomicForce
    match_type:    partial
    score:         0.74
    evidence:
      - PMDco:AtomicForce covers per-atom forces; NOMAD stores as Nx3 array
      - No direct unit annotation in NOMAD field; inferred as eV/Å from context
    status: needs_review
    review_note: "Confirm whether PMDco:AtomicForce expects per-atom or total force."
```

Optionally, the annotation map can be compiled to a **JSON-LD context** or **RDF serializer** that exports NOMAD entry data as Turtle/JSON-LD using PMDco terms — the entry point for FAIR-data compliance within the NFDI4Mat ecosystem.

```bash
# Export a NOMAD entry as RDF using the PMDco annotation map
schematerial serialize \
  examples/nomad_entry.json \
  --annotation runs/nomad_pmdco/annotation.yaml \
  --format json-ld \
  --out runs/nomad_pmdco/entry.jsonld
```

---

## CLI design

```bash
# Parse and inspect a schema
schematerial inspect examples/nomad_schema.yaml

# Align two schemas (Mode A: schema-to-schema)
schematerial align \
  examples/nomad_schema.yaml \
  examples/optimade_schema.yaml \
  --ontology ontologies/emmo.ttl \
  --out runs/nomad_optimade/

# Diff two crosswalk versions
schematerial diff runs/v1/crosswalk.yaml runs/v2/crosswalk.yaml

# Compile transform graph to executable code
schematerial compile runs/nomad_optimade/crosswalk.yaml --format python
schematerial compile runs/nomad_optimade/crosswalk.yaml --format jsonata

# Validate a compiled transform against real data
schematerial validate \
  runs/nomad_optimade/transform.py \
  --source examples/nomad_entry.json \
  --expected examples/optimade_entry.json

# Ground a schema against an ontology (standalone profiling step)
schematerial ground examples/nomad_schema.yaml --ontology ontologies/emmo.ttl

# Align a schema to an ontology (Mode B: schema-to-ontology)
schematerial annotate \
  examples/nomad_schema.yaml \
  ontologies/pmdco.ttl \
  --out runs/nomad_pmdco/

# Serialize a data entry to RDF using an annotation map
schematerial serialize \
  examples/nomad_entry.json \
  --annotation runs/nomad_pmdco/annotation.yaml \
  --format json-ld \
  --out runs/nomad_pmdco/entry.jsonld

# Human review: accept/reject individual mappings or annotations
schematerial review runs/nomad_optimade/crosswalk.yaml
schematerial review runs/nomad_pmdco/annotation.yaml
```

The `validate` command (Mode A) runs the compiled transform against a real source document and checks the output against a known-good target. The `serialize` command (Mode B) runs a NOMAD entry through the annotation map to produce RDF — the check here is whether the output is valid RDF and uses PMDco terms correctly.

---

## Repository structure

```
schematerial/
  pyproject.toml
  src/schematerial/
    __init__.py
    cli.py
    models/
      schema.py          ← SchemaModel, Entity, Field, SemanticType, ...
      crosswalk.py       ← MappingCandidate, CrosswalkResult, MappingRelation, ...
      annotation.py      ← AnnotationMap, AnnotationEntry (Mode B output model)
      transform.py       ← TransformOp hierarchy, TransformGraph (Mode A only)
    parsers/
      base.py            ← Parser ABC
      nomad.py
      optimade.py
      cif.py
      emmet.py
      yaml_schema.py
      json_schema.py
      owl_ontology.py    ← OWL/TTL → SchemaModel (for Mode B right-hand input)
    semantics/
      profiler.py        ← coordinates the semantic profiling pass
      units.py           ← pint-based unit parsing and compatibility
      ontology.py        ← SPARQL queries, EMMO/QUDT/PMDco grounding
      embeddings.py      ← MatBERT loading, embedding, caching
    mapping/
      candidates.py      ← candidate pair generation
      scoring.py         ← multi-signal composite scorer
      calibration.py     ← isotonic regression, score → probability
    agents/
      base.py
      inspector.py
      grounder.py
      mapper.py
      ambiguity.py
      transform_gen.py
      reporter.py
    pipeline.py          ← AlignmentPipeline (dispatches Mode A or B)
    export/
      compiler.py        ← TransformGraph → Python / JSONata / JQ  (Mode A)
      rdf_serializer.py  ← AnnotationMap + data entry → JSON-LD / Turtle  (Mode B)
      report.py          ← CrosswalkResult / AnnotationMap → report.md
  tests/
    unit/
      test_units.py
      test_ontology.py
      test_scoring.py
      test_compiler.py
    integration/
      test_nomad_optimade.py    ← canonical pair, ground truth assertions
      test_nomad_emmet.py
      test_cif_optimade.py
    fixtures/
      nomad_schema.yaml
      optimade_schema.yaml
      emmet_schema.yaml
      nomad_entry.json
      optimade_entry.json
      emmet_entry.json
      nomad_optimade_gt.yaml    ← calibration crosswalk (ground truth from NOMAD's OPTIMADE adapter)
      nomad_emmet_gt.yaml       ← hand-written discovery crosswalk (Mode A hard test)
      nomad_pmdco_gt.yaml       ← hand-written annotation map (Mode B hard test)
  examples/
    nomad_schema.yaml
    optimade_schema.yaml
    emmet_schema.yaml
    cif_example.cif
    nomad_entry.json
  ontologies/
    emmo.ttl                    ← checked in, pinned version
    qudt-units.ttl
    pmdco.ttl                   ← checked in, pinned version (from MaterialDigital repo)
  runs/                         ← gitignored, local outputs
```

---

## Tooling

```
uv              dependency management
pytest          testing
ruff            linting + formatting
pyright         type checking (add early, keeps models honest)
pre-commit      hooks: ruff, pyright, pytest --smoke
```

Do not add more tools than this. Complexity is the enemy of a project this early.

---

## Development phases

### Phase 0 — repo structure (do this first, before writing logic)

- `pyproject.toml` with dependencies
- Empty module stubs with correct `__init__.py` files
- `pytest` running (even with zero tests)
- `ruff` and `pyright` configured
- Fixture files: `nomad_schema.yaml`, `optimade_schema.yaml`, `emmet_schema.yaml`, and real entry JSON for each
- A `nomad_optimade_gt.yaml` derived from NOMAD's existing OPTIMADE adapter code — use this for calibration
- A hand-written `nomad_emmet_gt.yaml` — even 10 mappings — this is the discovery ground truth you actually had to think about

**Both crosswalks must exist before you write the first parser.** They are your specification. The NOMAD ↔ OPTIMADE one can be derived mechanically from the adapter source. The NOMAD ↔ Emmet one requires domain knowledge — that is the one that proves the tool is worth building.

### Phase 1 — deterministic core

Goals:
- Parse NOMAD, OPTIMADE, and Emmet schemas into `SchemaModel`
- Unit compatibility checking with pint
- Name/description similarity scoring (no embeddings yet)
- Candidate generation (brute force: all source × all target pairs)
- Composite scoring (subset of signals: name, description, unit, semantic_type)
- `crosswalk.yaml` output
- `schematerial align` CLI command

Definition of done: NOMAD ↔ OPTIMADE calibration crosswalk reproduced with `score ≥ 0.70` on all known mappings. This is the easy bar — the adapter code is the answer key.

### Phase 2 — semantic enrichment

Goals:
- EMMO/QUDT ontology grounding
- MatBERT embeddings (with cache)
- Confidence calibration using NOMAD ↔ OPTIMADE as calibration set (ground truth is reliable here because it comes from production code)
- Full scoring with all signals
- `schematerial ground` command
- CIF parser (third schema format)

Definition of done: calibrated scores on NOMAD ↔ OPTIMADE calibration set have < 0.10 mean absolute error. Then run against NOMAD ↔ Emmet and inspect results manually — this is the first real discovery test.

### Phase 3 — AI-assisted review

Goals:
- `AmbiguityReviewerAgent` — generates specific questions for borderline mappings
- `OntologyGroundingAgent` — LLM fallback for fields that SPARQL cannot ground
- `ReportWriterAgent` — generates `report.md` prose
- `schematerial review` interactive CLI

LLM integration points are clearly bounded. No agent decides a mapping. Every LLM output is labeled with `source: llm` and a confidence caveat.

### Phase 4 — transform graph + compilation

Goals:
- `TransformGeneratorAgent` produces typed `TransformOp` instances
- `compiler.py` compiles `TransformGraph` to Python and JSONata
- `schematerial compile` command
- `schematerial validate` command with real test data
- Transform-level unit tests (each `TransformOp` type has a test)

Definition of done (two bars):
1. Compiled `transform.py` from NOMAD ↔ OPTIMADE crosswalk applied to a real NOMAD entry produces a valid OPTIMADE-compliant document. (Easy — adapter code is the reference.)
2. Compiled `transform.py` from NOMAD ↔ Emmet crosswalk runs without errors on a real NOMAD entry and produces plausible Emmet output. (Hard — no reference to check against, you have to reason about it.)

### Phase 5 — Mode B: schema-to-ontology

Goals:
- OWL/TTL ontology parser (`owl_ontology.py` → `SchemaModel` where entities are classes and fields are properties)
- `AnnotationMap` output model
- `schematerial annotate` command (Mode B entry point)
- NOMAD Metainfo ↔ PMDco as the primary test pair
- PMDco TTL checked into `ontologies/pmdco.ttl`
- Hand-written `nomad_pmdco_gt.yaml` with ~20 grounded fields
- `rdf_serializer.py` — produces JSON-LD from a NOMAD entry + annotation map
- `schematerial serialize` command

Definition of done: `schematerial annotate nomad_schema.yaml ontologies/pmdco.ttl` produces an `annotation.yaml` where ≥ 80% of the hand-written ground truth annotations appear with `score ≥ 0.65`.

### Phase 6 — additional schemas + crosswalk versioning

Goals:
- NeXus parser (HDF5 application definitions → SchemaModel) — enables NeXus ↔ NOMAD experimental
- Start with a single technique: NXxrd ↔ NOMAD XRDMeasurement (scoped, verifiable)
- AFLOW parser
- Crosswalk diff tool
- Schema version tracking in crosswalk metadata
- Migration flagging

### Phase 6 — API + storage

Goals:
- FastAPI service wrapping `AlignmentPipeline`
- PostgreSQL: projects, schemas, alignments, review decisions
- S3/MinIO: schema files and generated artifacts
- Qdrant or pgvector: field embeddings

Do not start this phase until Phase 4 works end-to-end.

---

## Testing strategy

### Unit tests

Test each component in isolation:

- `test_units.py` — unit compatibility for known pairs (eV/J, Å/nm, eV/atom confusion)
- `test_ontology.py` — SPARQL grounding returns correct EMMO terms for known fields
- `test_scoring.py` — composite score for known pairs is in expected range
- `test_compiler.py` — each `TransformOp` type compiles to syntactically valid Python

### Integration tests

Two test classes with different expectations:

```python
def test_nomad_optimade_calibration_recall():
    """
    NOMAD ↔ OPTIMADE: calibration test.
    Ground truth is derived from NOMAD's OPTIMADE adapter code — this is the answer key.
    Bar is high: we must reproduce known mappings reliably.
    """
    result = pipeline.run(nomad_schema, optimade_schema)
    gt = load_ground_truth("fixtures/nomad_optimade_gt.yaml")
    for gt_mapping in gt.mappings:
        found = result.get_mapping(gt_mapping.source, gt_mapping.target)
        assert found is not None, f"Missing: {gt_mapping.source} → {gt_mapping.target}"
        assert found.score >= 0.70, f"Score too low: {found.score}"


def test_nomad_emmet_discovery_recall():
    """
    NOMAD ↔ Emmet: discovery test.
    Ground truth is hand-written — no adapter exists. Bar is lower because
    some ambiguity in the hand-written GT is expected.
    """
    result = pipeline.run(nomad_schema, emmet_schema)
    gt = load_ground_truth("fixtures/nomad_emmet_gt.yaml")
    for gt_mapping in gt.mappings:
        found = result.get_mapping(gt_mapping.source, gt_mapping.target)
        assert found is not None, f"Missing: {gt_mapping.source} → {gt_mapping.target}"
        assert found.score >= 0.55, f"Score too low: {found.score}"
```

### Regression guard

Once Phase 4 is done, add a transform correctness test per pair:

```python
def test_transform_correctness_calibration():
    """
    NOMAD → OPTIMADE compiled transform must match known output exactly.
    This is verifiable because NOMAD's OPTIMADE adapter is the reference.
    """
    source = load("fixtures/nomad_entry.json")
    expected = load("fixtures/optimade_entry.json")
    result = transform(source)
    assert_deep_approx(result, expected, rtol=1e-6)


def test_transform_correctness_discovery():
    """
    NOMAD → Emmet compiled transform must run without error and produce
    plausible output. No exact reference — check structural validity only.
    """
    source = load("fixtures/nomad_entry.json")
    result = transform(source)
    assert "energy" in result  # sanity check key quantities are present
    assert isinstance(result.get("energy"), float)
```

---

## What this is not

- Not a general-purpose ETL pipeline
- Not a chatbot
- Not a schema registry
- Not a data validator

It is a semantic crosswalk compiler for materials-science schemas. Every design decision should be evaluated against that.

---

## Revised pitch

> Schematerial is a semantic crosswalk compiler for materials-science data models. It parses heterogeneous schema formats, grounds fields in EMMO and QUDT ontologies, scores alignment candidates across name, unit, embedding, and ontology signals, produces traceable evidence-backed crosswalks, and compiles reviewed mappings to executable transform code. AI assists the process — humans own the decisions.
