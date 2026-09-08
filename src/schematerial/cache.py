"""Process-local materialisation cache.

Prepare canonical YAML at ingestion/startup, then retain its content hash for
lookup. Lookup never parses source or materialises a schema. Returned schemas
are defensive copies: callers cannot modify a cached entry.

Only self-contained schemas and the pinned runtime's bundled linkml:types
import are supported. External imports must be resolved into the source before
preparation, so changing a dependency cannot silently reuse a stale entry.
"""

from collections.abc import Callable
from copy import deepcopy
from hashlib import sha256
from threading import Lock

from linkml_runtime.dumpers import yaml_dumper
from linkml_runtime.linkml_model.meta import SchemaDefinition
from linkml_runtime.loaders import yaml_loader
from linkml_runtime.utils.schemaview import SchemaView
from yaml import YAMLError, safe_load

from schematerial.facets import validate_schema_facets


def content_hash(source: str) -> str:
    """SHA-256 of the exact UTF-8 YAML text; whitespace changes count too."""
    return sha256(source.encode("utf-8")).hexdigest()


class MaterialisationCache:
    """Explicitly owned, in-memory cache; no persistence or automatic eviction.

    Concurrent preparations are serialized so identical input is materialised
    once. A failed preparation never publishes an entry and can be retried.
    The pinned toolchain is constant for this cache's process lifetime.
    """

    def __init__(self) -> None:
        self._entries: dict[str, SchemaDefinition] = {}
        self._lock = Lock()

    def prepare(
        self, source: str, *, validate: Callable[[SchemaDefinition], None] | None = None,
    ) -> str:
        """Materialise on a cache miss and return the source's content hash.

        An optional ingestion validator sees a defensive copy before publication,
        and also runs on hits so a generic cache entry cannot bypass validation.
        A failed cold validation publishes nothing. Validators must not call this
        cache recursively while its preparation lock is held.
        """
        key = content_hash(source)
        with self._lock:
            if key in self._entries:
                if validate is not None:
                    validate(deepcopy(self._entries[key]))
                return key
            try:
                # Parse text explicitly: LinkML guesses filenames for one-line input.
                document = safe_load(source)
                if not isinstance(document, dict):
                    raise ValueError("Schema YAML must be a mapping")
                schema = yaml_loader.load(document, target_class=SchemaDefinition)
            except YAMLError as error:
                raise ValueError(f"Invalid schema YAML: {error}") from error
            assert isinstance(schema, SchemaDefinition)
            unsupported = [str(item) for item in schema.imports or []
                           if str(item) != "linkml:types"]
            if unsupported:
                raise ValueError(
                    "Materialisation requires self-contained source; resolve external "
                    f"imports into it first: {', '.join(unsupported)}"
                )
            validate_schema_facets(schema)
            materialised = SchemaView(schema).materialize_derived_schema()
            # The pinned materialiser produces JsonObj annotation containers.
            # Reload once on the cold path to restore metamodel dictionaries.
            materialised = yaml_loader.loads(
                yaml_dumper.dumps(materialised), target_class=SchemaDefinition
            )
            assert isinstance(materialised, SchemaDefinition)
            validate_schema_facets(materialised)
            if validate is not None:
                validate(deepcopy(materialised))
            self._entries[key] = materialised
        return key

    def get(self, key: str) -> SchemaDefinition:
        """Return a defensive copy; an unprepared key raises KeyError.

        Copying is proportional to schema size. The future web layer should
        build its client index once at startup, rather than copy per request.
        """
        with self._lock:
            schema = self._entries[key]
        return deepcopy(schema)
