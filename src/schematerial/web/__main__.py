"""Start schema browsing and local manual crosswalk authoring.

Ingestion, materialisation and index preparation all finish before the server
starts listening, so the first request is served from prepared bytes like every
one after it.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from schematerial.ontologies.pmdco import load_bundled
from schematerial.web.app import create_app, default_client_root
from schematerial.web.preview import SchemaPreview, ingest

__all__ = ["main"]


def _describe(preview: SchemaPreview) -> str:
    if preview.status != "ok":
        return f"  {preview.name}: unsupported -- {preview.summary['error']}"
    counts = preview.summary["counts"]
    return (
        f"  {preview.name}: {counts['classes']} classes, "
        f"{counts['effective_attributes']} effective attributes "
        f"({counts['browsable_elements']} browsable elements), "
        f"{counts['snapshot_paths']} snapshot paths, "
        f"{preview.summary['diagnostics']['total']} diagnostics"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="schematerial-web",
        description="Serve extracted schemas with local manual crosswalk authoring.",
    )
    parser.add_argument(
        "documents", nargs="+", type=Path, help="extraction contract JSON documents"
    )
    parser.add_argument("--host", default="127.0.0.1", help="default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8000, help="default: 8000")
    parser.add_argument(
        "--client-root",
        type=Path,
        default=None,
        help="built interface directory; defaults to web/dist in a source checkout",
    )
    parser.add_argument("--mappings", type=Path, default=Path("runs/crosswalk.sssom.tsv"),
                        help="persistent SSSOM crosswalk (default: runs/crosswalk.sssom.tsv)")
    arguments = parser.parse_args(argv)

    taxonomy = load_bundled()
    print(f"Loaded bundled PMDco {taxonomy.version}: {len(taxonomy.terms)} taxonomy terms")
    previews = ingest(arguments.documents)
    print(f"Ingested {len(previews)} schema(s):")
    for preview in previews:
        print(_describe(preview))
    root = default_client_root() if arguments.client_root is None else arguments.client_root
    if not (root / "index.html").is_file():
        print(f"No built interface at {root}; serving the API and build instructions.")
    print(f"Listening on http://{arguments.host}:{arguments.port}")

    uvicorn.run(create_app(previews, client_root=root, mapping_path=arguments.mappings,
                          taxonomy=taxonomy),
                host=arguments.host, port=arguments.port)
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
