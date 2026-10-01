"""Migration handler for format version 1."""

from __future__ import annotations

from typing import Any


def migrate_to_v1(data: dict[str, Any]) -> dict[str, Any]:
    """Ensure raw backup dictionary conforms to format version 1."""
    if "format_version" not in data:
        data["format_version"] = 1
    if "entries" not in data:
        data["entries"] = []
    return data
