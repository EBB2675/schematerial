"""Validate extraction documents without importing a source package."""

import json
import math
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator

_SCHEMA = json.loads(files(__package__).joinpath("contract.schema.json").read_text())
_VALIDATOR = Draft202012Validator(_SCHEMA)


class ContractError(ValueError):
    """Invalid extraction output, with JSON paths identifying the problem."""


def enum_value(value: str | dict[str, Any]) -> str:
    """The value an enum entry names, whether or not it carries metadata."""
    return value if isinstance(value, str) else value["value"]


def validate_document(document: Any) -> dict[str, Any]:
    errors = sorted(_VALIDATOR.iter_errors(document), key=lambda error: str(error.json_path))
    if errors:
        raise ContractError("\n".join(f"{error.json_path}: {error.message}" for error in errors))

    def unique(values: list[str], path: str) -> None:
        seen: set[str] = set()
        for index, value in enumerate(values):
            if value in seen:
                raise ContractError(f"{path}[{index}]: duplicate identifier {value!r}")
            seen.add(value)

    classes = document["classes"]
    enums = document["enums"]
    unique([item["id"] for item in classes], "$.classes")
    unique([item["id"] for item in enums], "$.enums")
    # A value may be spelled plainly or carry metadata; both name the same value.
    for index, item in enumerate(enums):
        unique([enum_value(value) for value in item["values"]], f"$.enums[{index}].values")
    class_ids = {item["id"] for item in classes}
    enum_ids = {item["id"] for item in enums}
    declarations = {
        (cls["id"], attribute["name"]): attribute["kind"]
        for cls in classes for attribute in cls["attributes"]
    }
    for index, cls in enumerate(classes):
        path = f"$.classes[{index}]"
        unique(cls["bases"], f"{path}.bases")
        unique([item["name"] for item in cls["attributes"]], f"{path}.attributes")
        effective = cls.get("effective_attributes", [])
        unique([item["name"] for item in effective], f"{path}.effective_attributes")
        for ref_index, reference in enumerate(effective):
            key = (reference["declaring_class_id"], reference["name"])
            if declarations.get(key) != reference["kind"]:
                raise ContractError(
                    f"{path}.effective_attributes[{ref_index}]: "
                    f"no matching local {reference['kind']} declaration {key!r}"
                )
        for base_index, base in enumerate(cls["bases"]):
            if base not in class_ids:
                raise ContractError(f"{path}.bases[{base_index}]: unknown class {base!r}")
        for attr_index, attribute in enumerate(cls["attributes"]):
            range_ = attribute["range"]
            allowed = {"class": class_ids, "enum": enum_ids}.get(range_["kind"])
            if allowed is not None and range_["name"] not in allowed:
                raise ContractError(
                    f"{path}.attributes[{attr_index}].range.name: "
                    f"unknown {range_['kind']} {range_['name']!r}"
                )
            if attribute["kind"] == "subsection" and (
                range_["kind"] != "class" or "repeats" not in attribute
            ):
                raise ContractError(
                    f"{path}.attributes[{attr_index}]: subsection requires class range and repeats"
                )
    return document


def read_document(content: str) -> dict[str, Any]:
    """Read strict JSON: duplicate keys and non-finite numbers are errors."""
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in items:
            if key in result:
                raise ContractError(f"$: duplicate JSON key {key!r}")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise ContractError(f"$: invalid JSON number {value}")

    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ContractError(f"$: non-finite JSON number {value}")
        return number

    try:
        document = json.loads(
            content, object_pairs_hook=pairs, parse_constant=invalid_constant,
            parse_float=finite_float,
        )
    except json.JSONDecodeError as error:
        raise ContractError(
            f"$: invalid JSON at line {error.lineno}, column {error.colno}"
        ) from error
    return validate_document(document)
