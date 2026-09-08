"""Prepared schema browsing, with optional local manual mapping review.

Schema reads serve prepared bytes. Review routes persist SSSOM rows without
materialising schemas or entering the cache.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from schematerial.mappings.store import MappingStore
from schematerial.ontologies.pmdco import SCHEMA_KEY, PmdcoTaxonomy
from schematerial.web.human_review import install_review
from schematerial.web.preview import SchemaPreview, serialise

__all__ = ["create_app", "default_client_root"]

JSON = "application/json"

_NO_CLIENT = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>schematerial schema preview</title>
<style>body{font:14px/1.6 system-ui,sans-serif;margin:3rem auto;max-width:44rem;padding:0 1rem}
code{background:#f2f2f2;padding:.1rem .3rem;border-radius:3px}</style></head><body>
<h1>The server is running; the client has not been built</h1>
<p>The API is already answering. Build the interface once, then reload:</p>
<pre><code>cd web
npm install
npm run build</code></pre>
<p>For development with hot reloading, run <code>npm run dev</code> in
<code>web/</code> and open the address it prints; it proxies API calls to this
server.</p>
<p>The API itself is browsable now: <a href="/api/schemas">/api/schemas</a>.</p>
</body></html>
"""


def default_client_root() -> Path:
    """Where a source checkout puts the built interface."""
    return Path(__file__).resolve().parents[3] / "web" / "dist"


def _payload(body: bytes, status: int = 200) -> Response:
    return Response(content=body, status_code=status, media_type=JSON)


def _error(message: str, status: int) -> Response:
    return _payload(serialise({"error": message}), status)


def create_app(
    previews: Sequence[SchemaPreview], *, client_root: Path | None = None,
    mapping_path: Path | None = None, taxonomy: PmdcoTaxonomy | None = None
) -> FastAPI:
    """Build the application over schemas that are already fully prepared."""
    registry = {preview.name: preview for preview in previews}
    catalogue = serialise({"schemas": [preview.summary for preview in previews]})
    health = serialise(
        {
            "status": "ok",
            "schemas": [
                {"name": preview.name, "status": preview.status} for preview in previews
            ],
        }
    )

    app = FastAPI(title="schematerial schema preview", docs_url="/api/docs", redoc_url=None)

    @app.get("/api/health")
    def read_health() -> Response:
        return _payload(health)

    @app.get("/api/schemas")
    def read_schemas() -> Response:
        return _payload(catalogue)

    @app.get("/api/schemas/{name}")
    def read_schema(name: str) -> Response:
        preview = registry.get(name)
        if preview is None:
            return _error(f"unknown schema {name!r}", 404)
        return _payload(preview.summary_bytes)

    @app.get("/api/schemas/{name}/elements")
    def read_elements(name: str, request: Request) -> Response:
        preview = registry.get(name)
        if preview is None:
            return _error(f"unknown schema {name!r}", 404)
        headers = {"vary": "accept-encoding"}
        if "gzip" in request.headers.get("accept-encoding", ""):
            # Compressed during ingestion, not now.
            return Response(
                content=preview.index_gzip,
                media_type=JSON,
                headers={**headers, "content-encoding": "gzip"},
            )
        return Response(content=preview.index_bytes, media_type=JSON, headers=headers)

    # The class boxes and the edges between them, positioned at ingestion. A
    # request neither lays the graph out nor re-serialises it.
    @app.get("/api/schemas/{name}/graph")
    def read_graph(name: str, request: Request) -> Response:
        preview = registry.get(name)
        if preview is None:
            return _error(f"unknown schema {name!r}", 404)
        headers = {"vary": "accept-encoding"}
        if "gzip" in request.headers.get("accept-encoding", ""):
            return Response(
                content=preview.graph_gzip,
                media_type=JSON,
                headers={**headers, "content-encoding": "gzip"},
            )
        return Response(content=preview.graph_bytes, media_type=JSON, headers=headers)

    # The identifier is a CURIE with a colon, dots and percent escapes, so it
    # travels as a query parameter rather than through a second encoding round.
    @app.get("/api/schemas/{name}/element")
    def read_element(name: str, id: str) -> Response:
        preview = registry.get(name)
        if preview is None:
            return _error(f"unknown schema {name!r}", 404)
        body = preview.detail_bytes.get(id)
        if body is None:
            return _error(f"unknown element {id!r} in schema {name!r}", 404)
        return _payload(body)

    @app.get("/api/pmdco")
    def read_pmdco() -> Response:
        if taxonomy is None:
            return _error("PMDco is not loaded", 404)
        return _payload(taxonomy.payload_bytes)

    if taxonomy is not None and SCHEMA_KEY in registry:
        raise ValueError("Schema name pmdco is reserved for the ontology taxonomy")
    if mapping_path is not None:
        install_review(app, previews, MappingStore(mapping_path),
                       extra_snapshots={} if taxonomy is None else taxonomy.snapshots())

    root = default_client_root() if client_root is None else client_root
    if (root / "index.html").is_file():
        app.mount("/", StaticFiles(directory=root, html=True), name="client")
    else:

        @app.get("/", response_class=HTMLResponse)
        def read_placeholder() -> HTMLResponse:
            return HTMLResponse(_NO_CLIENT)

    return app
