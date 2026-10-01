"""Application configuration management for omarchy-backup."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from omarchy_backup.paths import AppPaths, default_paths


@dataclass
class BackupConfig:
    """User configuration for omarchy-backup."""
    backup_dir: str = ""
    remote_url: str = ""
    branch: str = "main"
    include_local: bool = False
    include_scripts: bool = False
    include_packages: bool = True
    custom_exclusions: list[str] = field(default_factory=list)

    def get_backup_path(self, paths: AppPaths | None = None) -> Path:
        """Resolve backup repository directory."""
        p = paths or default_paths
        if self.backup_dir:
            return Path(self.backup_dir).expanduser().resolve()
        return p.default_backup_dir

    @classmethod
    def load(cls, paths: AppPaths | None = None) -> BackupConfig:
        """Load configuration from disk or return default."""
        p = paths or default_paths
        config_file = p.app_config_file
        if not config_file.exists():
            return cls()

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
            return cls(
                backup_dir=data.get("backup_dir", ""),
                remote_url=data.get("remote_url", ""),
                branch=data.get("branch", "main"),
                include_local=data.get("include_local", False),
                include_scripts=data.get("include_scripts", False),
                include_packages=data.get("include_packages", True),
                custom_exclusions=data.get("custom_exclusions", []),
            )
        except Exception:
            return cls()

    def save(self, paths: AppPaths | None = None) -> Path:
        """Save configuration to disk."""
        p = paths or default_paths
        config_file = p.app_config_file
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
        return config_file
