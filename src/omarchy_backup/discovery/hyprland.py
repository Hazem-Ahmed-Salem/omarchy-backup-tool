"""Discovery of Hyprland configuration files."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from omarchy_backup.backup.checksum import calculate_sha256, get_file_mode_str
from omarchy_backup.manifest import ManifestEntry
from omarchy_backup.paths import AppPaths, default_paths
from omarchy_backup.security.exclusions import should_exclude_path
from omarchy_backup.security.secrets import scan_file_for_secrets

logger = logging.getLogger(__name__)

# Files that represent local hardware configurations
LOCAL_SCOPE_NAMES = {"monitors.lua", "monitors.conf"}


def discover_hyprland_files(
    paths: AppPaths | None = None,
    custom_exclusions: list[str] | None = None,
) -> list[ManifestEntry]:
    """Discover user configuration files in ~/.config/hypr."""
    p = paths or default_paths
    hypr_dir = p.hypr_config_dir

    if not hypr_dir.is_dir():
        logger.debug("Hyprland config directory not found: %s", hypr_dir)
        return []

    entries: list[ManifestEntry] = []

    for item in sorted(hypr_dir.rglob("*")):
        # Skip directories themselves, only track files and symlinks
        if item.is_dir():
            continue

        rel_to_hypr = item.relative_to(hypr_dir)
        rel_str = str(rel_to_hypr)

        # Check exclusion rules
        is_ex, reason = should_exclude_path(item, custom_exclusions)
        if is_ex:
            logger.debug("Excluding hypr file %s: %s", item, reason)
            continue

        # We only want config files: lua, conf, json, toml, etc.
        ext = item.suffix.lower()
        if ext not in {".lua", ".conf", ".json", ".toml", ".sh", ".bash"} and not item.name.startswith("."):
            logger.debug("Skipping non-config file in hypr: %s", item)
            continue

        # Handle symlinks
        if item.is_symlink():
            target = os.readlink(item)
            scope = "local" if item.name in LOCAL_SCOPE_NAMES else "portable"
            entries.append(
                ManifestEntry(
                    source=f"~/.config/hypr/{rel_str}",
                    destination=f"hypr/{rel_str}",
                    entry_type="symlink",
                    scope=scope,
                    symlink_target=str(target),
                    mode="0777",
                )
            )
            continue

        # Content secret scanning
        scan = scan_file_for_secrets(item)
        if scan.has_secret:
            logger.warning("Secret detected in %s (%s). Excluded from backup.", item, scan.reason)
            continue

        # Normal file
        try:
            sha = calculate_sha256(item)
            size = item.stat().st_size
            mode = get_file_mode_str(item)
            scope = "local" if item.name in LOCAL_SCOPE_NAMES else "portable"

            entries.append(
                ManifestEntry(
                    source=f"~/.config/hypr/{rel_str}",
                    destination=f"hypr/{rel_str}",
                    entry_type="file",
                    scope=scope,
                    sha256=sha,
                    size=size,
                    mode=mode,
                )
            )
        except OSError as exc:
            logger.warning("Error processing %s: %s", item, exc)

    return entries
