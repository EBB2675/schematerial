"""Read-only schema preview server.

Ingestion happens once, at startup. A request looks a key up in a table and
writes bytes that were serialised before it arrived; it never materialises a
schema, copies one out of the cache, or re-serialises a payload.

Nothing here imports a matcher, an embedding index, an agent or a network
client. The preview is fully functional with every such capability absent.
"""

from schematerial.web.app import create_app
from schematerial.web.preview import SchemaPreview, build_preview, ingest

__all__ = ["SchemaPreview", "build_preview", "create_app", "ingest"]
