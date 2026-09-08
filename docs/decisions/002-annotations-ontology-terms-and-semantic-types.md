# 002. Annotations, ontology terms, and semantic types

This record explains how the prototype's annotation and ontology records fit
into the canonical LinkML schema and the planned mapping workflow.

## Annotation records

`AnnotationEntry` and `AnnotationMap` were removed. Their responsibilities
belong to two separate representations:

- Source-stated semantic types are facet annotations on LinkML elements,
  governed by the materials metamodel extension through `instantiates`.
  Units belong to the element's unit metadata.
- Correspondences between an element and an ontology term belong in the
  planned SSSOM mapping store, with justification and provenance.

Keeping another annotation record would duplicate those responsibilities.

## Ontology terms

`OntologyTerm` remains an application record in `semantics/ontology.py`.
Its URI, label, ontology, match type and confidence describe a grounding
proposal. A proposal is not a fact; acceptance requires a human action.
The planned grounding workflow will produce these proposals.

The canonical schema carries an explicit or human-approved `semantic_type`
CURIE. It does not carry grounding confidence or embeddings. Keeping volatile
application data separate prevents rescoring from invalidating the
[materialisation cache](../materialisation-cache.md).

`models/` contains generated output, so handwritten application records live
outside it.

## Semantic aliases

`semantic_type` has an open `uriorcurie` range. Aliases are conveniences rather
than an exhaustive list of permitted values. Ten prototype names have aliases:

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

Six prototype names have no alias:

- `lattice_parameter` conflated lengths, angles and vectors; one alias would
  obscure those differences.
- `k_point` needs a vocabulary term and version chosen explicitly through the
  grounding workflow.
- `identifier`, `label` and `flag` described roles or datatypes rather than
  physical quantity kinds.
- `unknown` represented absence. An unstated semantic type remains absent.

The parser does not infer these aliases from names or descriptions. Explicit
valid CURIEs are preserved even when they are not in the alias table. Future
matching must work when semantic types are absent.
