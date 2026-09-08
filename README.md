![schematerial logo](logo.png)

Schematerial translates between heterogeneous materials-science data models by generating semantic crosswalks, executable mappings, and human-in-the-loop alignment reports. 

AI agents assist with schema inspection, ontology grounding, ambiguity detection, and evidence-based mapping suggestions.

## Local development

**Prerequisites:** [uv](https://docs.astral.sh/uv/) and Python >=3.12. The
interface additionally needs [Node.js](https://nodejs.org/) 22 or newer.

```sh
uv sync                  # install deps + editable package into .venv
uv run pytest            # run tests
uv run ruff check .      # lint
uv run pyright           # type check
```

## Browse two schemas side by side

Build the interface once, then serve the extraction documents with it:

```sh
cd web && npm install && npm run build && cd ..
uv run schematerial-web \
  runs/extraction/nomad-simulations-0.6.0-general-v1.1.json \
  runs/extraction/bam-masterdata-0.13.1-object_types-v1.2.json
```

The page opens with one schema on each side, searchable together and read-only.
Either side reads as a list of elements or as a graph of its classes.
See [schema aligner](docs/schema-preview.md) for what it shows, how the two
sides are synchronised, the API it reads, and how to run its own checks.

## Architecture

- [Source extraction contract](docs/extraction-contract.md)
- [NOMAD extraction](docs/nomad-extraction.md)
- [NOMAD JSON adapter](docs/nomad-adapter.md)
- [BAM masterdata extraction](docs/bam-extraction.md)
- [BAM masterdata JSON adapter](docs/bam-adapter.md)
- [Schema aligner](docs/schema-preview.md)

- [Materialisation cache](docs/materialisation-cache.md)
- [Annotations, ontology terms, and semantic types](docs/decisions/002-annotations-ontology-terms-and-semantic-types.md)
- [Web layer decisions](docs/decisions/004-web-layer.md)
- [Structural graph view decisions](docs/decisions/006-structural-graph-view.md)
- [BAM masterdata conversion decisions](docs/decisions/005-bam-masterdata-linkml-conversion.md)
