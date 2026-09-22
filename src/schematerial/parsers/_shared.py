"""Shared conversion helpers for extraction JSON adapters."""

import json
from typing import Any

from linkml_runtime.linkml_model.meta import PermissibleValue

from schematerial._linkml import set_annotation


def permissible(value: str | dict[str, Any]) -> PermissibleValue:
    """One vocabulary term, keeping the label and description the source states."""
    if isinstance(value, str):
        return PermissibleValue(text=value)
    permissible = PermissibleValue(
        text=value["value"], title=value.get("title"), description=value.get("description"),
    )
    # JSON text, so a boolean or numeric source fact reads back as what it was.
    for tag, item in sorted(value.get("annotations", {}).items()):
        set_annotation(permissible, tag, json.dumps(item))
    return permissible
