"""Backup collector orchestrating discovery, copy, and metadata persistence."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omarchy_backup.backup.copier import copy_manifest_entry
from omarchy_backup.config import BackupConfig
from omarchy_backup.discovery.hyprland import discover_hyprland_files
from omarchy_backup.discovery.omarchy import discover_omarchy_files
from omarchy_backup.discovery.packages import discover_packages
from omarchy_backup.discovery.plugins import discover_all_plugins
from omarchy_backup.discovery.scripts import discover_custom_scripts
from omarchy_backup.discovery.system import discover_system_info, discover_versions
from omarchy_backup.manifest import Manifest, ManifestEntry
from omarchy_backup.paths import AppPaths, default_paths
from omarchy_backup.runner import CommandRunner, default_runner

logger = logging.getLogger(__name__)


@dataclass
class BackupResult:
    """Summary of backup operation."""
    success: bool
    manifest: Manifest
    backup_path: Path
    copied_files: list[str] = field(default_factory=list)
    failed_files: list[tuple[str, str]] = field(default_factory=list)
    plugin_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class BackupCollector:
    """Coordinates discovering, copying, and metadata generation for backup."""

    def __init__(
        self,
        config: BackupConfig | None = None,
        paths: AppPaths | None = None,
        runner: CommandRunner | None = None,
    ) -> None:
        self.config = config or BackupConfig()
        self.paths = paths or default_paths
        self.runner = runner or default_runner

    def collect(
        self,
        target_dir: Path | None = None,
        include_scripts: bool | None = None,
        include_packages: bool | None = None,
    ) -> BackupResult:
        """Run full backup collection into target repository."""
        backup_path = (target_dir or self.config.get_backup_path(self.paths)).resolve()
        backup_path.mkdir(parents=True, exist_ok=True)

        scripts_enabled = include_scripts if include_scripts is not None else self.config.include_scripts
        packages_enabled = include_packages if include_packages is not None else self.config.include_packages

        # 1. Discover system and versions
        versions = discover_versions(self.runner)
        sys_info = discover_system_info(self.runner)

        # 2. Discover Hyprland and Omarchy files
        hypr_entries = discover_hyprland_files(
            paths=self.paths,
            custom_exclusions=self.config.custom_exclusions,
        )
        omarchy_entries = discover_omarchy_files(
            paths=self.paths,
            custom_exclusions=self.config.custom_exclusions,
        )

        all_config_entries = hypr_entries + omarchy_entries

        # 3. Discover custom scripts
        script_entries: list[ManifestEntry] = []
        if scripts_enabled:
            script_entries = discover_custom_scripts(
                config_entries=all_config_entries,
                include_all=True,
                paths=self.paths,
                custom_exclusions=self.config.custom_exclusions,
            )

        # 4. Construct complete manifest
        manifest_entries = all_config_entries + script_entries
        manifest = Manifest(
            omarchy_version=versions.get("omarchy", ""),
            hyprland_version=versions.get("hyprland", ""),
            entries=manifest_entries,
        )

        # 5. Discover plugins
        plugins = discover_all_plugins(paths=self.paths, runner=self.runner)

        # 6. Discover packages
        package_lists = discover_packages(self.runner) if packages_enabled else None

        # 7. Copy all manifest entries into the backup directory
        copied: list[str] = []
        failed: list[tuple[str, str]] = []
        warnings: list[str] = []

        for entry in manifest.entries:
            ok, msg = copy_manifest_entry(entry, backup_path, paths=self.paths)
            if ok:
                copied.append(entry.destination)
            else:
                failed.append((entry.destination, msg))
                warnings.append(f"Failed to copy {entry.destination}: {msg}")

        # 8. Write manifest.json
        manifest.save(backup_path / "manifest.json")

        # 9. Write versions.json and system.json
        with open(backup_path / "versions.json", "w", encoding="utf-8") as f:
            json.dump(versions, f, indent=2)

        with open(backup_path / "system.json", "w", encoding="utf-8") as f:
            json.dump(sys_info, f, indent=2)

        # 10. Write plugins metadata
        plugins_dir = backup_path / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)

        omarchy_plugin_data = [p.to_dict() for p in plugins.get("omarchy-shell", [])]
        with open(plugins_dir / "omarchy-shell.json", "w", encoding="utf-8") as f:
            json.dump(omarchy_plugin_data, f, indent=2)

        hyprpm_plugin_data = [p.to_dict() for p in plugins.get("hyprpm", [])]
        with open(plugins_dir / "hyprpm.json", "w", encoding="utf-8") as f:
            json.dump(hyprpm_plugin_data, f, indent=2)

        # 11. Write packages
        if package_lists:
            packages_dir = backup_path / "packages"
            packages_dir.mkdir(parents=True, exist_ok=True)
            with open(packages_dir / "native.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(package_lists.native) + ("\n" if package_lists.native else ""))
            with open(packages_dir / "aur.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(package_lists.aur) + ("\n" if package_lists.aur else ""))
            with open(packages_dir / "explicit.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(package_lists.explicit) + ("\n" if package_lists.explicit else ""))

        # 12. Write metadata
        metadata_dir = backup_path / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)

        checksums_dict = {e.destination: e.sha256 for e in manifest.entries if e.sha256}
        with open(metadata_dir / "checksums.json", "w", encoding="utf-8") as f:
            json.dump(checksums_dict, f, indent=2)

        backup_info = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "total_files": len(copied),
            "omarchy_plugins_count": len(omarchy_plugin_data),
            "hyprpm_plugins_count": len(hyprpm_plugin_data),
        }
        with open(metadata_dir / "backup-info.json", "w", encoding="utf-8") as f:
            json.dump(backup_info, f, indent=2)

        with open(metadata_dir / "hardware.json", "w", encoding="utf-8") as f:
            json.dump(sys_info, f, indent=2)

        # 13. Write README.md
        self._write_readme(backup_path, versions, len(copied), len(omarchy_plugin_data))

        return BackupResult(
            success=len(failed) == 0,
            manifest=manifest,
            backup_path=backup_path,
            copied_files=copied,
            failed_files=failed,
            plugin_counts={
                "omarchy-shell": len(omarchy_plugin_data),
                "hyprpm": len(hyprpm_plugin_data),
            },
            warnings=warnings,
        )

    def _write_readme(
        self,
        backup_path: Path,
        versions: dict[str, str],
        file_count: int,
        plugin_count: int,
    ) -> None:
        """Generate human-readable README in the backup repository."""
        content = f"""# Omarchy & Hyprland Configuration Backup

Managed and generated by `omarchy-backup`.

## System Overview
- **Omarchy Version**: {versions.get('omarchy', 'unknown')}
- **Hyprland Version**: {versions.get('hyprland', 'unknown')}
- **Architecture**: {versions.get('architecture', 'unknown')}
- **Files Managed**: {file_count}
- **Omarchy Plugins**: {plugin_count}

## Restore Instructions
To restore this backup safely on a compatible machine:
```bash
omarchy-backup restore
```

For a dry-run check without applying any changes:
```bash
omarchy-backup restore --dry-run
```
"""
        with open(backup_path / "README.md", "w", encoding="utf-8") as f:
            f.write(content)
