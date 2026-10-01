"""Discovery of Omarchy user configuration files."""

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

# Files that represent local hardware state
LOCAL_SCOPE_NAMES = {"display-settings.json"}


def discover_omarchy_files(
    paths: AppPaths | None = None,
    custom_exclusions: list[str] | None = None,
) -> list[ManifestEntry]:
    """Discover user configuration files in ~/.config/omarchy.

    Note: Omarchy plugins are discovered separately by discovery.plugins.
    """
    p = paths or default_paths
    omarchy_dir = p.omarchy_config_dir

    if not omarchy_dir.is_dir():
        logger.debug("Omarchy config directory not found: %s", omarchy_dir)
        return []

    entries: list[ManifestEntry] = []

    for item in sorted(omarchy_dir.rglob("*")):
        if item.is_dir():
            continue

        rel_to_omarchy = item.relative_to(omarchy_dir)
        rel_str = str(rel_to_omarchy)
        rel_parts = rel_to_omarchy.parts

        # NEVER copy the raw plugins/ directory inside omarchy config;
        # plugin metadata is recorded in plugins/omarchy-shell.json instead!
        if rel_parts and rel_parts[0] == "plugins":
            continue

        # Check exclusion rules
        is_ex, reason = should_exclude_path(item, custom_exclusions)
        if is_ex:
            logger.debug("Excluding omarchy file %s: %s", item, reason)
            continue

        # Skip binary media files (wallpapers, videos, archives)
        if item.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mkv", ".tar", ".gz", ".zip"}:
            logger.debug("Skipping binary media file in omarchy: %s", item)
            continue

        # Symlinks
        if item.is_symlink():
            target = os.readlink(item)
            scope = "local" if item.name in LOCAL_SCOPE_NAMES else "portable"
            entries.append(
                ManifestEntry(
                    source=f"~/.config/omarchy/{rel_str}",
                    destination=f"omarchy/{rel_str}",
                    entry_type="symlink",
                    scope=scope,
                    symlink_target=str(target),
                    mode="0777",
                )
            )
            continue

        # Secret scan
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
                    source=f"~/.config/omarchy/{rel_str}",
                    destination=f"omarchy/{rel_str}",
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
