"""Manifest data model and persistence for audited configuration backups."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omarchy_backup import __version__


@dataclass
class ManifestEntry:
    """Individual backed up item in the manifest."""
    source: str
    destination: str
    entry_type: str = "file"  # "file", "symlink", "directory"
    scope: str = "portable"   # "portable", "local"
    sha256: str = ""
    size: int = 0
    mode: str = "0644"
    symlink_target: str | None = None
    restore_rule: str = "default"  # "default", "no_overwrite_existing", "interactive"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ManifestEntry:
        return cls(
            source=data.get("source", ""),
            destination=data.get("destination", ""),
            entry_type=data.get("entry_type", data.get("type", "file")),
            scope=data.get("scope", "portable"),
            sha256=data.get("sha256", ""),
            size=data.get("size", 0),
            mode=data.get("mode", "0644"),
            symlink_target=data.get("symlink_target"),
            restore_rule=data.get("restore_rule", "default"),
        )


@dataclass
class Manifest:
    """Complete backup manifest with format versioning and metadata."""
    format_version: int = 1
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    application_version: str = __version__
    omarchy_version: str = ""
    hyprland_version: str = ""
    entries: list[ManifestEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "created_at": self.created_at,
            "application_version": self.application_version,
            "omarchy_version": self.omarchy_version,
            "hyprland_version": self.hyprland_version,
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        entries = [ManifestEntry.from_dict(e) for e in data.get("entries", [])]
        return cls(
            format_version=data.get("format_version", 1),
            created_at=data.get("created_at", ""),
            application_version=data.get("application_version", ""),
            omarchy_version=data.get("omarchy_version", ""),
            hyprland_version=data.get("hyprland_version", ""),
            entries=entries,
        )

    def save(self, target_path: Path | str) -> None:
        """Write manifest to json file."""
        p = Path(target_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, source_path: Path | str) -> Manifest:
        """Load manifest from json file."""
        p = Path(source_path)
        if not p.is_file():
            raise FileNotFoundError(f"Manifest not found: {p}")
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def get_entry_by_dest(self, dest: str) -> ManifestEntry | None:
        for entry in self.entries:
            if entry.destination == dest:
                return entry
        return None

    def get_entry_by_source(self, source: str) -> ManifestEntry | None:
        for entry in self.entries:
            if entry.source == source:
                return entry
        return None
