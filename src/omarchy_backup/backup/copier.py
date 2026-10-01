"""Safe, atomic copying of files and symlinks with permission and checksum preservation."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path

from omarchy_backup.backup.checksum import calculate_sha256
from omarchy_backup.manifest import ManifestEntry
from omarchy_backup.paths import AppPaths, default_paths

logger = logging.getLogger(__name__)


def copy_manifest_entry(
    entry: ManifestEntry,
    target_root: Path,
    paths: AppPaths | None = None,
) -> tuple[bool, str]:
    """Copy an entry from its source path to target_root / entry.destination.

    Returns (success, message).
    """
    p = paths or default_paths
    dest_path = target_root / entry.destination
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    source_path = Path(entry.source.replace("~", str(p.home)))

    if entry.entry_type == "symlink":
        try:
            if dest_path.is_symlink() or dest_path.exists():
                dest_path.unlink()
            target = entry.symlink_target or os.readlink(source_path)
            dest_path.symlink_to(target)
            return True, f"Symlinked {entry.destination} -> {target}"
        except OSError as exc:
            return False, f"Failed to symlink {entry.destination}: {exc}"

    if not source_path.is_file():
        return False, f"Source file does not exist: {source_path}"

    # Atomic file copy
    temp_file = None
    try:
        # Create temp file in same directory for atomic rename
        with tempfile.NamedTemporaryFile(dir=dest_path.parent, delete=False) as tmp:
            temp_file = Path(tmp.name)
            with open(source_path, "rb") as src_f:
                shutil.copyfileobj(src_f, tmp)
            tmp.flush()
            os.fsync(tmp.fileno())

        # Verify checksum before placing
        if entry.sha256:
            actual_sha = calculate_sha256(temp_file)
            if actual_sha.lower() != entry.sha256.lower():
                temp_file.unlink(missing_ok=True)
                return False, f"Checksum mismatch while copying {entry.destination}"

        # Preserve permissions
        mode_int = int(entry.mode, 8)
        os.chmod(temp_file, mode_int)

        # Atomic replace
        temp_file.replace(dest_path)
        return True, f"Copied {entry.destination}"
    except Exception as exc:
        if temp_file and temp_file.exists():
            temp_file.unlink(missing_ok=True)
        return False, f"Failed copying {entry.destination}: {exc}"
