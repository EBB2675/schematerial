"""Read BAM masterdata definitions in their own environment; emit source facts as JSON.

Standalone stdlib script. An entity class is recognised by a local ``defs``
attribute holding a masterdata ``*TypeDef``; its properties are class attributes
holding a ``PropertyTypeAssignment`` and its vocabulary terms are class
attributes holding a ``VocabularyTerm``. Nothing here interprets openBIS types
into LinkML terms; that is the adapter's problem.

The masterdata command line is deliberately never loaded. It reads an openBIS
URL from the environment while being imported, so importing any module inside
that package fails without a configured server -- including its RDF and Excel
writers. Those writers also drop the facts this reader exists to preserve: they
flatten inherited and local properties together, name no declaring class, and
carry no openBIS data type. Definitions are read instead, out of process, from
the datamodel and metadata packages only.
"""

import argparse
import contextlib
import importlib
import importlib.metadata
import inspect
import json
import pkgutil
import sys
from enum import Enum
from types import ModuleType
from typing import Any

DATAMODEL = "bam_masterdata.datamodel"

# Definition classes, by the attribute name each collection of members uses.
DEFINITION = "defs"

# Entity-definition fields worth preserving verbatim. `code` is openBIS's own
# identity for the entity and is the reason class annotations exist at all.
ENTITY_FIELDS = (
    "code",
    "iri",
    "validation_script",
    "generated_code_prefix",
    "auto_generate_codes",
    "url_template",
    "main_dataset_pattern",
    "main_dataset_path",
)

# Property-assignment fields worth preserving verbatim, beyond the ones that
# become structural contract fields (`data_type`, `units`, `description`).
PROPERTY_FIELDS = (
    "code",
    "iri",
    "property_label",
    "section",
    "mandatory",
    "show_in_edit_views",
    "ordinal",
    "unique",
    "internal_assignment",
    "dynamic_script",
    "vocabulary_code",
    "object_code",
    "metadata",
)


def identifier(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def definition_of(cls: type) -> Any:
    """The entity definition a class declares itself, never an inherited one."""
    return vars(cls).get(DEFINITION)


def is_entity(candidate: Any) -> bool:
    """The recognition rule: a class with its own `defs` holding a `*TypeDef`."""
    if not inspect.isclass(candidate):
        return False
    definition = definition_of(candidate)
    return definition is not None and type(definition).__name__.endswith("TypeDef")


def entity_kind(cls: type) -> str:
    return type(definition_of(cls)).__name__


def scalar(value: Any) -> str | float | bool | None:
    """One annotation value, or None when the source states nothing.

    Contract annotations hold strings, numbers and booleans. A source field
    holding anything else is preserved as sorted JSON text rather than dropped.
    """
    # The openBIS data type is a str-valued enum member; its own str() spells the
    # member, not the openBIS name, so unwrap before anything else looks at it.
    if isinstance(value, Enum):
        value = value.value
    if value is None or value == "":
        return None
    if isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return str(value)
    return json.dumps(value, sort_keys=True, default=str)


def annotations_of(definition: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in fields:
        value = scalar(getattr(definition, field, None))
        if value is not None:
            result[field] = value
    return result


def members(cls: type, kind: str) -> list[tuple[str, Any]]:
    """This class's own members of one definition kind, in declaration order."""
    return [
        (name, value)
        for name, value in vars(cls).items()
        if type(value).__name__ == kind
    ]


def enum_id(cls: type) -> str:
    """A vocabulary type is both a class and an enum, so their ids differ.

    One LinkML name cannot resolve to both, and an attribute range naming the
    wrong one would silently point at the entity instead of its value space.
    """
    return f"{identifier(cls)}.terms"


def catalog_modules(package: ModuleType) -> list[ModuleType]:
    """Every module in a datamodel package, including its domain subpackages."""
    modules = [package]
    path = getattr(package, "__path__", None)
    if path is not None:
        for found in pkgutil.walk_packages(path, prefix=f"{package.__name__}."):
            with contextlib.suppress(Exception):
                modules.append(importlib.import_module(found.name))
    return modules


def build_catalog(modules: tuple[ModuleType, ...]) -> dict[tuple[str, str], list[type]]:
    """Index entity classes by (kind, openBIS code).

    A property names its vocabulary and object targets by code, not by object,
    so resolving those references needs the whole datamodel rather than the one
    module being extracted. Every class claiming a code is kept: one code held
    by two definitions is an ambiguity to report, not a race to pick a winner.
    """
    catalog: dict[tuple[str, str], list[type]] = {}
    for module in modules:
        for value in vars(module).values():
            if not is_entity(value) or value.__module__ != module.__name__:
                continue
            code = getattr(definition_of(value), "code", None)
            if isinstance(code, str) and code:
                found = catalog.setdefault((entity_kind(value), code), [])
                if value not in found:
                    found.append(value)
    return catalog


def extract(
    module: ModuleType, version: str, roots: tuple[str, ...] = (), *,
    dependencies: dict[str, str] | None = None,
    catalog: tuple[ModuleType, ...] = (),
) -> dict[str, Any]:
    classes: dict[str, dict[str, Any]] = {}
    enums: dict[str, dict[str, Any]] = {}
    report: list[dict[str, str]] = []
    pending: list[tuple[str, Any]] = []
    visited: set[str] = set()
    objects: dict[str, type] = {}
    index = build_catalog(catalog or (module,))

    def warn(path: str, reason: str, status: str = "skipped") -> None:
        report.append({"path": path, "status": status, "reason": reason})

    def enqueue(target: type) -> str:
        if not is_entity(target):
            raise ValueError("masterdata framework class excluded from source model")
        name = identifier(target)
        pending.append((name, target))
        return name

    if roots:
        for root in roots:
            pending.append((f"{module.__name__}.{root}", getattr(module, root, None)))
    else:
        for name, value in sorted(vars(module).items()):
            if is_entity(value) and value.__module__ == module.__name__:
                pending.append((f"{module.__name__}.{name}", value))

    while pending:
        path, candidate = pending.pop(0)
        if path in visited:
            continue
        visited.add(path)
        terms: list[tuple[str, Any]] = []
        properties: list[tuple[str, Any]] = []
        try:
            if not is_entity(candidate):
                raise ValueError("class has no local masterdata entity definition")
            canonical_path = identifier(candidate)
            if canonical_path != path:
                if canonical_path in visited:
                    continue
                visited.add(canonical_path)
                path = canonical_path
            definition = definition_of(candidate)
            record: dict[str, Any] = {
                "id": path, "name": candidate.__name__, "bases": [], "attributes": [],
                "effective_attributes": [],
                "annotations": {"entity_kind": entity_kind(candidate),
                                **annotations_of(definition, ENTITY_FIELDS)},
            }
            description = getattr(definition, "description", None)
            if description:
                record["description"] = str(description)
            terms = members(candidate, "VocabularyTerm")
            properties = members(candidate, "PropertyTypeAssignment")
        except Exception as error:
            warn(path, f"malformed entity: {type(error).__name__}: {error}")
            continue
        classes[path] = record
        objects[path] = candidate

        if record["annotations"]["entity_kind"] == "VocabularyTypeDef":
            record["annotations"]["vocabulary_enum"] = enum_id(candidate)
            values: list[dict[str, Any]] = []
            seen: set[str] = set()
            for name, term in terms:
                term_path = f"{path}.{name}"
                try:
                    code = getattr(term, "code", None)
                    if not isinstance(code, str) or not code:
                        raise ValueError("vocabulary term has no source code")
                    if code in seen:
                        raise ValueError("duplicate vocabulary term code")
                    seen.add(code)
                    value: dict[str, Any] = {"value": code}
                    label = scalar(getattr(term, "label", None))
                    if isinstance(label, str):
                        value["title"] = label
                    term_description = getattr(term, "description", None)
                    if term_description:
                        value["description"] = str(term_description)
                    official = getattr(term, "official", None)
                    if isinstance(official, bool):
                        value["annotations"] = {"official": official}
                    values.append(value)
                except Exception as error:
                    warn(term_path, f"unreadable term: {type(error).__name__}: {error}")
            enums[enum_id(candidate)] = {"id": enum_id(candidate), "values": values}
            if properties:
                warn(path, "vocabulary type also declares property assignments", "partial")

        for base in candidate.__bases__:
            if base is object:
                continue
            try:
                record["bases"].append(enqueue(base))
            except Exception as error:
                warn(f"{path}.__bases__.{base.__name__}", str(error))

        for name, assignment in properties:
            attribute_path = f"{path}.{name}"
            try:
                if any(item["name"] == name for item in record["attributes"]):
                    raise ValueError("duplicate class-local attribute name")
                raw = scalar(getattr(assignment, "data_type", None))
                if not isinstance(raw, str) or not raw:
                    raise ValueError("property assignment has no source data type")
                annotations = {"data_type": raw, **{
                    ("property_code" if field == "code" else field): value
                    for field, value in annotations_of(assignment, PROPERTY_FIELDS).items()
                }}
                attribute: dict[str, Any] = {
                    "name": name, "kind": "property",
                    "range": _range(raw, assignment, index, enqueue, attribute_path, warn),
                    "annotations": annotations,
                }
                description = getattr(assignment, "description", None)
                if description:
                    attribute["description"] = str(description)
                units = getattr(assignment, "units", None)
                if units:
                    attribute["unit"] = str(units)
                record["attributes"].append(attribute)
            except Exception as error:
                warn(attribute_path, f"unreadable property: {type(error).__name__}: {error}")

    # Targets can fail after discovery. Remove each dangling edge with a report.
    for record in classes.values():
        bases = []
        for base in record["bases"]:
            if base in classes:
                bases.append(base)
            else:
                warn(f"{record['id']}.__bases__.{base}", "target entity was skipped")
        record["bases"] = bases
        attributes = []
        for attribute in record["attributes"]:
            range_ = attribute["range"]
            resolved = classes if range_["kind"] == "class" else enums
            if range_["kind"] in ("class", "enum") and range_["name"] not in resolved:
                warn(f"{record['id']}.{attribute['name']}", "target entity was skipped")
            else:
                attributes.append(attribute)
        record["attributes"] = attributes

    _effective(classes, objects, warn)
    return {
        "contract_version": "1.2",
        "source": {"name": "bam-masterdata", "version": version, "module": module.__name__,
                   "dependencies": dict(sorted((dependencies or {}).items()))},
        "classes": [classes[key] for key in sorted(classes)],
        "enums": [enums[key] for key in sorted(enums)],
        "report": sorted(report, key=lambda row: (row["path"], row["reason"])),
    }


def _range(
    raw: str, assignment: Any, index: dict[tuple[str, str], list[type]],
    enqueue: Any, path: str, warn: Any,
) -> dict[str, str]:
    """The source's own statement of what a property holds.

    A controlled vocabulary and an object reference name their target by code.
    A code that resolves to no definition, or to more than one, keeps the raw
    openBIS type and is reported, rather than inventing or guessing a target the
    source does not unambiguously have.
    """
    targets = {
        "CONTROLLEDVOCABULARY": ("vocabulary_code", "VocabularyTypeDef", "enum"),
        "OBJECT": ("object_code", "ObjectTypeDef", "class"),
    }
    if raw in targets:
        field, kind, range_kind = targets[raw]
        code = getattr(assignment, field, None)
        found = index.get((kind, code), []) if isinstance(code, str) else []
        if len(found) > 1:
            warn(path, f"ambiguous {field} {code!r}: "
                       f"{', '.join(sorted(identifier(item) for item in found))}", "partial")
        elif not found:
            warn(path, f"unresolved {field} {code!r} for {raw} property", "partial")
        else:
            name = enqueue(found[0])
            return {"kind": range_kind, "name": enum_id(found[0]) if range_kind == "enum" else name}
    return {"kind": "datatype", "name": raw}


def _effective(
    classes: dict[str, dict[str, Any]], objects: dict[str, type], warn: Any,
) -> None:
    """Read effective properties from Python's own lookup order.

    Inheritance here is real Python inheritance, so the winner of a name is the
    first class in the method resolution order that declares it -- exactly what
    an attribute access returns. The package's own effective dictionary is read
    as a cross-check; a disagreement is reported rather than silently resolved.
    """
    declarations = {(record["id"], item["name"]): item["kind"]
                    for record in classes.values() for item in record["attributes"]}
    for path, record in classes.items():
        cls = objects[path]
        try:
            resolved: dict[str, tuple[str, Any]] = {}
            for ancestor in cls.__mro__:
                owner = identifier(ancestor)
                for name, value in vars(ancestor).items():
                    if type(value).__name__ == "PropertyTypeAssignment" and name not in resolved:
                        resolved[name] = (owner, value)
            for name, (owner, _) in resolved.items():
                if declarations.get((owner, name)) != "property":
                    raise ValueError(f"unresolved effective property {owner}.{name}")
            source_view = _source_effective(cls)
            if source_view is not None:
                mismatch = {
                    name for name in set(source_view) | set(resolved)
                    if name not in source_view or name not in resolved
                    or source_view[name] is not resolved[name][1]
                }
                if mismatch:
                    raise ValueError(
                        "source effective properties disagree with Python lookup: "
                        + ", ".join(sorted(mismatch))
                    )
            record["effective_attributes"] = sorted(
                ({"kind": "property", "name": name, "declaring_class_id": owner}
                 for name, (owner, _) in resolved.items()),
                key=lambda reference: reference["name"],
            )
        except Exception as error:
            record["effective_attributes"] = []
            warn(path, f"incomplete effective definitions: {type(error).__name__}: {error}")


def _source_effective(cls: type) -> dict[str, Any] | None:
    """The package's own effective property dictionary, when it can be read."""
    try:
        metadata = cls().get_property_metadata()
    except Exception:
        return None
    return metadata if isinstance(metadata, dict) else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True)
    parser.add_argument("--root", action="append", default=[])
    args = parser.parse_args()
    if args.module != DATAMODEL and not args.module.startswith(f"{DATAMODEL}."):
        parser.error(f"--module must be within {DATAMODEL}")
    try:
        # Source imports may print diagnostics; stdout must remain a JSON document.
        with contextlib.redirect_stdout(sys.stderr):
            version = importlib.metadata.version("bam-masterdata")
            module = importlib.import_module(args.module)
            document = extract(
                module, version, tuple(args.root),
                dependencies={name: importlib.metadata.version(name)
                              for name in ("pydantic", "pint")},
                catalog=tuple(catalog_modules(importlib.import_module(DATAMODEL))),
            )
        print(json.dumps(document, sort_keys=True, allow_nan=False))
    except Exception as error:
        print(f"BAM masterdata extraction failed: {type(error).__name__}: {error}",
              file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
