"""Pre-restore snapshot creation and management for emergency rollback."""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omarchy_backup.backup.checksum import calculate_sha256, get_file_mode_str
from omarchy_backup.manifest import Manifest, ManifestEntry
from omarchy_backup.paths import AppPaths, default_paths

logger = logging.getLogger(__name__)


def create_pre_restore_snapshot(
    manifest: Manifest,
    paths: AppPaths | None = None,
    tag: str = "pre-restore",
) -> Path:
    """Create an emergency snapshot of currently live files before restoring.

    Snapshots are stored under ~/.local/state/omarchy-backup/snapshots/
    """
    p = paths or default_paths
    snapshots_dir = p.snapshots_dir
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    snapshot_dir = snapshots_dir / f"{tag}-{timestamp}"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    files_dir = snapshot_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    snapshotted_entries: list[dict[str, Any]] = []

    for entry in manifest.entries:
        source_path = Path(entry.source.replace("~", str(p.home)))
        if not source_path.exists() and not source_path.is_symlink():
            continue

        dest_in_snapshot = files_dir / entry.destination
        dest_in_snapshot.parent.mkdir(parents=True, exist_ok=True)

        if source_path.is_symlink():
            target = os.readlink(source_path)
            dest_in_snapshot.symlink_to(target)
            snapshotted_entries.append({
                "source": entry.source,
                "relative_path": entry.destination,
                "type": "symlink",
                "target": str(target),
            })
        elif source_path.is_file():
            shutil.copy2(source_path, dest_in_snapshot)
            sha = calculate_sha256(source_path)
            mode = get_file_mode_str(source_path)
            snapshotted_entries.append({
                "source": entry.source,
                "relative_path": entry.destination,
                "type": "file",
                "sha256": sha,
                "mode": mode,
            })

    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tag": tag,
        "entry_count": len(snapshotted_entries),
        "entries": snapshotted_entries,
    }

    with open(snapshot_dir / "snapshot-manifest.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    logger.info("Created pre-restore snapshot: %s (%d files)", snapshot_dir, len(snapshotted_entries))
    return snapshot_dir


def list_snapshots(paths: AppPaths | None = None) -> list[Path]:
    """Return all snapshot directories sorted newest first."""
    p = paths or default_paths
    snapshots_dir = p.snapshots_dir
    if not snapshots_dir.is_dir():
        return []

    snaps = [d for d in snapshots_dir.iterdir() if d.is_dir() and (d / "snapshot-manifest.json").exists()]
    return sorted(snaps, reverse=True)


def get_latest_snapshot(paths: AppPaths | None = None) -> Path | None:
    """Return the most recently created snapshot directory."""
    snaps = list_snapshots(paths)
    return snaps[0] if snaps else None
