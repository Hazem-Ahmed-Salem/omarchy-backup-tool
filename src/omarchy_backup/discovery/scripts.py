"""Discovery of custom user scripts referenced by configurations."""

from __future__ import annotations

import logging
from pathlib import Path

from omarchy_backup.backup.checksum import calculate_sha256, get_file_mode_str
from omarchy_backup.manifest import ManifestEntry
from omarchy_backup.paths import AppPaths, default_paths
from omarchy_backup.security.exclusions import should_exclude_path
from omarchy_backup.security.secrets import scan_file_for_secrets

logger = logging.getLogger(__name__)


def is_elf_binary(path: Path) -> bool:
    """Check if file starts with ELF magic bytes."""
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
            return magic == b"\x7fELF"
    except Exception:
        return False


def find_referenced_script_names(config_entries: list[ManifestEntry], paths: AppPaths | None = None) -> set[str]:
    """Inspect discovered configs to find references to ~/.local/bin script names."""
    p = paths or default_paths
    referenced_names: set[str] = set()

    for entry in config_entries:
        if entry.entry_type != "file":
            continue
        # Resolve real path
        source_expanded = Path(entry.source.replace("~", str(p.home)))
        if not source_expanded.is_file():
            continue

        # Only inspect text configuration files
        if source_expanded.suffix.lower() not in {".lua", ".conf", ".sh", ".bash", ".json", ".toml", ".jsonc"}:
            continue
        if source_expanded.stat().st_size > 262_144:
            continue

        try:
            with open(source_expanded, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
                # Check for mention of ~/.local/bin or local scripts
                for word in content.split():
                    clean_word = word.strip("\"'()[],;")
                    if ".local/bin/" in clean_word:
                        script_name = clean_word.split(".local/bin/")[-1].split("/")[0]
                        referenced_names.add(script_name)
                    elif clean_word.startswith("~/.local/bin/"):
                        referenced_names.add(clean_word.replace("~/.local/bin/", ""))
        except Exception:
            continue

    return referenced_names


def discover_custom_scripts(
    config_entries: list[ManifestEntry] | None = None,
    include_all: bool = False,
    paths: AppPaths | None = None,
    custom_exclusions: list[str] | None = None,
) -> list[ManifestEntry]:
    """Discover custom scripts in ~/.local/bin.

    If include_all is False, only scripts referenced in configurations are discovered.
    ELF binaries and secrets are strictly excluded.
    """
    p = paths or default_paths
    local_bin = p.local_bin_dir

    if not local_bin.is_dir():
        return []

    referenced = find_referenced_script_names(config_entries or [], paths=p)
    entries: list[ManifestEntry] = []

    for item in sorted(local_bin.iterdir()):
        if item.is_dir() or item.is_symlink():
            continue

        # If not include_all, only include if referenced
        if not include_all and item.name not in referenced:
            continue

        # Filter exclusions
        is_ex, reason = should_exclude_path(item, custom_exclusions)
        if is_ex:
            logger.debug("Excluding script %s: %s", item, reason)
            continue

        # Strictly skip compiled ELF binaries (e.g. uv, custom binaries)
        if is_elf_binary(item):
            logger.debug("Skipping ELF binary script: %s", item)
            continue

        # Secret scan
        scan = scan_file_for_secrets(item)
        if scan.has_secret:
            logger.warning("Secret detected in script %s (%s). Excluded.", item, scan.reason)
            continue

        try:
            sha = calculate_sha256(item)
            size = item.stat().st_size
            mode = get_file_mode_str(item)

            entries.append(
                ManifestEntry(
                    source=f"~/.local/bin/{item.name}",
                    destination=f"local/bin/{item.name}",
                    entry_type="file",
                    scope="local",
                    sha256=sha,
                    size=size,
                    mode=mode,
                )
            )
        except OSError as exc:
            logger.warning("Error processing script %s: %s", item, exc)

    return entries
