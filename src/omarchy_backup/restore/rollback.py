"""Rollback engine restoring configuration from emergency snapshots."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path

from omarchy_backup.backup.snapshot import get_latest_snapshot
from omarchy_backup.paths import AppPaths, default_paths

logger = logging.getLogger(__name__)


def rollback_snapshot(
    snapshot_dir: Path,
    paths: AppPaths | None = None,
) -> tuple[bool, list[str]]:
    """Restore files from a snapshot back to live configuration atomically."""
    p = paths or default_paths
    manifest_file = snapshot_dir / "snapshot-manifest.json"
    files_dir = snapshot_dir / "files"

    if not manifest_file.is_file() or not files_dir.is_dir():
        return False, [f"Invalid snapshot directory structure: {snapshot_dir}"]

    with open(manifest_file, "r", encoding="utf-8") as f:
        meta = json.load(f)

    restored: list[str] = []
    entries = meta.get("entries", [])

    for item in entries:
        source_str = item.get("source", "")
        rel_path = item.get("relative_path", "")
        entry_type = item.get("type", "file")

        if not source_str or not rel_path:
            continue

        target_file = Path(source_str.replace("~", str(p.home)))
        target_file.parent.mkdir(parents=True, exist_ok=True)
        backup_item = files_dir / rel_path

        if entry_type == "symlink":
            sym_target = item.get("target", "")
            if target_file.is_symlink() or target_file.exists():
                target_file.unlink()
            target_file.symlink_to(sym_target)
            restored.append(str(target_file))
        elif backup_item.is_file():
            # Atomic file restore
            temp_file = None
            try:
                with tempfile.NamedTemporaryFile(dir=target_file.parent, delete=False) as tmp:
                    temp_file = Path(tmp.name)
                    with open(backup_item, "rb") as src_f:
                        shutil.copyfileobj(src_f, tmp)
                    tmp.flush()
                    os.fsync(tmp.fileno())

                mode = item.get("mode")
                if mode:
                    os.chmod(temp_file, int(mode, 8))

                temp_file.replace(target_file)
                restored.append(str(target_file))
            except Exception as exc:
                if temp_file and temp_file.exists():
                    temp_file.unlink(missing_ok=True)
                logger.error("Failed to restore %s during rollback: %s", target_file, exc)

    return True, restored


def rollback_latest_snapshot(paths: AppPaths | None = None) -> tuple[bool, str, list[str]]:
    """Find and rollback the latest emergency snapshot.

    Returns (success, snapshot_name, restored_files).
    """
    p = paths or default_paths
    latest = get_latest_snapshot(p)
    if not latest:
        return False, "", ["No emergency snapshots found to rollback."]

    ok, restored = rollback_snapshot(latest, paths=p)
    return ok, latest.name, restored
