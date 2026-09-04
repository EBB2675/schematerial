# 002. Annotations, ontology terms, and the sixteen semantic types

Card 2 leaves three things undecided and asks for them to be settled in
writing. This is that record. Nothing here re-opens a decision in AGENTS.md.

## AnnotationEntry and AnnotationMap: neither. Deleted.

Card 2 asks which of these the LinkML core absorbs and which stay app records.
The honest answer is neither, because the class straddles a seam three
decisions already draw.

`AnnotationEntry` held `field`, `pmdco_concept`, `emmo_concept`, `qudt_unit`,
`match_type` and `confidence`. Split it along that seam:

- `qudt_unit`, and the idea of a semantic CURIE on an element, are **facets**.
  Decision 4 already puts those in the core, in `annotations`, governed by the
  metamodel extension class. They do not need a second home.
- `field` plus a concept plus `match_type` plus `confidence` is a **mapping row
  with a justification**. That is SSSOM, which decision 6 says not to reinvent.
  Card 10 writes it.

So the class is not absorbed by the core and does not stay an app record. What
it did is already owned twice over, and keeping it would be a third spelling of
the same thing that Card 10 would then have to reconcile. Deleted.

## OntologyTerm: an app record, outside `models/`.

`OntologyTerm` is `uri`, `label`, `ontology`, `match_type`, `confidence`. That
is a **grounding proposal**, and decision 11 makes a proposal a suggestion
rather than a fact. Card 14 is what produces it.

It is not absorbed by the LinkML core, for two reasons. A confidence is not
schema structure. And decision 10 keeps volatile data out of the core IR
because the Card 4 cache keys on a content hash over it -- a re-scored
proposal would move that key without the schema having changed.

It survives as an app record, and `ontology_terms` comes off `SchemaField`.
What the core carries is a single accepted `semantic_type` CURIE, per decision
4. Acceptance is what turns a proposal into that CURIE, and acceptance is a
human act.

It moves from `models/ontology.py` to `semantics/ontology.py`, because Card 3
makes `models/` generated output that is never hand-edited, and a hand-written
app record cannot live there.

## The sixteen semantic types: ten survive as aliases, six do not.

Decision 4 makes `semantic_type` an open `uriorcurie` whose value space is
QUDT, EMMO or PMDco, and says a local enum may exist only as convenience
aliases over those CURIEs. Card 2 requires the sixteen prototype values to
survive only in that form.

An alias was written only where the term (1) resolves, (2) means exactly what
the alias name says, and (3) has a stable, readable CURIE. Each of the ten
below was checked against the live vocabulary.

| prototype value   | CURIE                                 |
| ----------------- | ------------------------------------- |
| `energy`          | `quantitykind:Energy`                 |
| `length`          | `quantitykind:Length`                 |
| `force`           | `quantitykind:Force`                  |
| `stress`          | `quantitykind:Stress`                 |
| `charge`          | `quantitykind:ElectricCharge`         |
| `spin`            | `quantitykind:Spin`                   |
| `temperature`     | `quantitykind:ThermodynamicTemperature` |
| `pressure`        | `quantitykind:Pressure`               |
| `band_gap`        | `quantitykind:GapEnergy`              |
| `atomic_position` | `quantitykind:PositionVector`         |

`quantitykind:GapEnergy` is band gap: QUDT defines it as the difference in
energy between the lowest level of the conduction band and the highest level of
the valence band.

The six that did not survive, and why:

- **`lattice_parameter`.** The prototype's ladder returned it for cell lengths,
  cell angles and lattice vectors alike. No single term covers all three.
  `quantitykind:LatticeVector` covers only the last, and asserting it for a cell
  angle would be wrong. A cell length now resolves as `quantitykind:Length`,
  which is correct and narrower than what was there before.
- **`k_point`.** EMMO 1.0.3 has exactly the right term, `WaveVector`, but its
  CURIE is `emmo:EMMO_6074aa9d_7c3b_4011_b45a_4e7cde6f5f39`, and nothing pins
  the EMMO version -- decision 9 pins `linkml`, `linkml-model`, `linkml-map` and
  `sssom`, not the ontologies. An unreadable identifier against an unpinned
  vocabulary is a liability, and grounding is Card 14's job. QUDT's
  `AngularReciprocalLatticeVector` is a near miss, not a k-point.
- **`identifier`, `label`, `flag`.** Not quantity kinds, and not semantic types
  in any of the three vocabularies. They were datatype and role hints wearing
  the wrong name.
- **`unknown`.** Decision 4: a facet with no value is absent, not guessed. It
  was the absence of a semantic type, never a value for one.

None of this is lossy in the way it looks. The value space is open, so any of
these can be expressed the moment a real term is chosen for it, and Card 14 is
where that choice gets made with a confidence and a justification attached.
Card 13's baseline is required to score with `semantic_type` absent on every
element, so nothing downstream depends on the six being present.
