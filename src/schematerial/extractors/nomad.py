"""Read NOMAD metainfo in its own environment; emit source facts as JSON.

Standalone stdlib script. Section target resolution follows the approach in
EBB2675/schema-studio, extractor/graph_builder.py; the output is the extraction
contract rather than a display graph. No application or LinkML imports.
"""

import argparse
import contextlib
import importlib
import importlib.metadata
import inspect
import json
import re
import sys
from collections import deque
from types import ModuleType
from typing import Any


def section_class(target: Any) -> type:
    if inspect.isclass(target):
        return target
    for name in ("section_cls", "section_class", "cls", "python_type"):
        candidate = getattr(target, name, None)
        if inspect.isclass(candidate):
            return candidate
    raise ValueError("cannot resolve section definition to a Python class")


def identifier(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def members(value: Any) -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        return sorted(value.items())
    if isinstance(value, (list, tuple)):
        return sorted(((item.name, item) for item in value), key=lambda pair: pair[0])
    raise ValueError("expected metainfo definition collection")


def raw_datatype(dtype: Any) -> str:
    if inspect.isclass(dtype):
        return identifier(dtype)
    # NOMAD DataType objects expose their serialization representation.
    serialize = getattr(dtype, "serialize_self", None)
    if callable(serialize):
        value = serialize()
        return value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    value = str(dtype)
    if not value or re.search(r" at 0x[0-9a-fA-F]+", value):
        raise ValueError(f"no stable source datatype representation for {type(dtype).__name__}")
    return value


def extract(
    module: ModuleType, version: str, roots: tuple[str, ...] = (), *,
    dependencies: dict[str, str] | None = None,
) -> dict[str, Any]:
    classes: dict[str, dict[str, Any]] = {}
    enums: dict[str, dict[str, Any]] = {}
    report: list[dict[str, str]] = []
    pending: deque[tuple[str, Any]] = deque()
    visited: set[str] = set()
    definitions: dict[str, Any] = {}

    def warn(path: str, reason: str) -> None:
        report.append({"path": path, "status": "skipped", "reason": reason})

    def enqueue(target: Any) -> str:
        cls = section_class(target)
        name = identifier(cls)
        if name.startswith("nomad.metainfo."):
            raise ValueError("metainfo framework class excluded from source model")
        pending.append((name, cls))
        return name

    if roots:
        for root in roots:
            pending.append((f"{module.__name__}.{root}", getattr(module, root, None)))
    else:
        for name, value in sorted(vars(module).items()):
            if inspect.isclass(value) and value.__module__ == module.__name__:
                pending.append((f"{module.__name__}.{name}", value))

    while pending:
        path, candidate = pending.popleft()
        if path in visited:
            continue
        visited.add(path)
        try:
            cls = section_class(candidate)
            canonical_path = identifier(cls)
            if canonical_path != path:
                if canonical_path in visited:
                    continue
                visited.add(canonical_path)
                path = canonical_path
            definition = vars(cls).get("m_def")
            if definition is None:
                raise ValueError("class has no local metainfo section definition")
            quantities = members(definition.quantities)
            subsections = members(definition.sub_sections)
            record: dict[str, Any] = {
                "id": identifier(cls), "name": cls.__name__, "bases": [], "attributes": [],
                "effective_attributes": [],
            }
            if definition.description:
                record["description"] = str(definition.description)
        except Exception as error:
            warn(path, f"malformed section: {type(error).__name__}: {error}")
            continue
        classes[record["id"]] = record
        definitions[record["id"]] = definition
        for base in cls.__bases__:
            if base is object:
                continue
            try:
                record["bases"].append(enqueue(base))
            except Exception as error:
                warn(f"{path}.__bases__.{base.__name__}", str(error))
        for kind, items in (("quantity", quantities), ("subsection", subsections)):
            for name, item in items:
                attribute_path = f"{path}.{name}"
                try:
                    if not isinstance(name, str) or not name:
                        raise ValueError("attribute name must be a nonempty string")
                    if any(attribute["name"] == name for attribute in record["attributes"]):
                        raise ValueError("duplicate class-local attribute name")
                    attribute: dict[str, Any] = {"name": name, "kind": kind}
                    if item.description:
                        attribute["description"] = str(item.description)
                    if kind == "subsection":
                        target = enqueue(item.sub_section)
                        if not isinstance(item.repeats, bool):
                            raise ValueError("subsection repeats is not boolean")
                        attribute.update(range={"kind": "class", "name": target},
                                         repeats=item.repeats)
                    else:
                        dtype = item.type
                        if dtype is None:
                            raise ValueError("quantity has no source type")
                        serialize = getattr(dtype, "serialize_self", None)
                        # Reference.serialize_self needs a section context; resolve it below.
                        reference = getattr(dtype, "target_section_def", None)
                        serialized = (
                            serialize() if callable(serialize) and reference is None else None
                        )
                        if isinstance(serialized, dict) and serialized.get("type_kind") == "enum":
                            values = serialized["type_data"]
                            if not isinstance(values, list) or not all(
                                isinstance(value, str) for value in values
                            ):
                                raise ValueError("enum contains non-string values")
                            if len(values) != len(set(values)):
                                raise ValueError("enum contains duplicate values")
                            enums[attribute_path] = {"id": attribute_path, "values": values}
                            attribute["annotations"] = {
                                "source_type": json.dumps(serialized, sort_keys=True)
                            }
                            range_ = {"kind": "enum", "name": attribute_path}
                        elif reference is not None:
                            range_ = {"kind": "class", "name": enqueue(reference)}
                        else:
                            range_ = {"kind": "datatype", "name": raw_datatype(dtype)}
                        attribute["range"] = range_
                        if item.unit is not None:
                            attribute["unit"] = str(item.unit)
                        shape = item.shape
                        if shape is not None:
                            if not isinstance(shape, list) or not all(
                                (type(dim) is int and dim >= 0) or
                                (isinstance(dim, str) and bool(dim)) for dim in shape
                            ):
                                raise ValueError(f"shape cannot be preserved as JSON: {shape!r}")
                            attribute["shape"] = list(shape)
                    record["attributes"].append(attribute)
                except Exception as error:
                    warn(attribute_path, f"unreadable {kind}: {type(error).__name__}: {error}")

    # Targets can fail after discovery. Remove each dangling edge with a report.
    for record in classes.values():
        bases = []
        for base in record["bases"]:
            if base in classes:
                bases.append(base)
            else:
                warn(f"{record['id']}.__bases__.{base}", "target section was skipped")
        record["bases"] = bases
        attributes = []
        for attribute in record["attributes"]:
            range_ = attribute["range"]
            if range_["kind"] == "class" and range_["name"] not in classes:
                warn(f"{record['id']}.{attribute['name']}", "target section was skipped")
            else:
                attributes.append(attribute)
        record["attributes"] = attributes

    # Read NOMAD's resolved dictionaries, never reconstruct inheritance from bases.
    declarations = {(record["id"], attr["name"]): attr["kind"]
                    for record in classes.values() for attr in record["attributes"]}
    for path, record in classes.items():
        definition = definitions[path]
        try:
            if getattr(definition, "extending_sections", []):
                raise ValueError("metainfo extending sections are unsupported")
            for kind, properties in (("quantity", definition.all_quantities),
                                     ("subsection", definition.all_sub_sections)):
                for name, prop in members(properties):
                    owner = identifier(section_class(prop.m_parent))
                    if declarations.get((owner, name)) != kind:
                        raise ValueError(f"unresolved effective {kind} {owner}.{name}")
                    if any(ref["name"] == name for ref in record["effective_attributes"]):
                        raise ValueError(f"cross-kind effective name collision: {name}")
                    record["effective_attributes"].append({
                        "kind": kind, "name": name, "declaring_class_id": owner,
                    })
        except Exception as error:
            record["effective_attributes"] = []
            warn(path, f"incomplete effective definitions: {type(error).__name__}: {error}")
        record["effective_attributes"].sort(key=lambda ref: ref["name"])
    return {
        "contract_version": "1.1",
        "source": {"name": "nomad-simulations", "version": version, "module": module.__name__,
                   "dependencies": dict(sorted((dependencies or {}).items()))},
        "classes": [classes[key] for key in sorted(classes)],
        "enums": [enums[key] for key in sorted(enums)],
        "report": sorted(report, key=lambda row: (row["path"], row["reason"])),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True)
    parser.add_argument("--root", action="append", default=[])
    args = parser.parse_args()
    if not args.module.startswith("nomad_simulations."):
        parser.error("--module must be within nomad_simulations")
    try:
        # Source imports may print diagnostics; stdout must remain a JSON document.
        with contextlib.redirect_stdout(sys.stderr):
            version = importlib.metadata.version("nomad-simulations")
            module = importlib.import_module(args.module)
            document = extract(module, version, tuple(args.root), dependencies={
                name: importlib.metadata.version(name) for name in ("nomad-lab", "numpy")
            })
        print(json.dumps(document, sort_keys=True, allow_nan=False))
    except Exception as error:
        print(f"NOMAD extraction failed: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
