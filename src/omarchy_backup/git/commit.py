"""Audited git commit workflow for configuration backups."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from omarchy_backup.git.repository import GitRepo
from omarchy_backup.manifest import Manifest
from omarchy_backup.security.secrets import scan_file_for_secrets

logger = logging.getLogger(__name__)

STANDARD_METADATA_FILES = [
    "manifest.json",
    "versions.json",
    "system.json",
    "README.md",
    "plugins/omarchy-shell.json",
    "plugins/hyprpm.json",
    "packages/native.txt",
    "packages/aur.txt",
    "packages/explicit.txt",
    "metadata/checksums.json",
    "metadata/backup-info.json",
    "metadata/hardware.json",
]


def commit_manifest_backup(
    repo: GitRepo,
    manifest: Manifest,
    custom_message: str | None = None,
) -> tuple[bool, str]:
    """Stage only audited manifest and metadata files, verify secrets, and commit.

    Returns (success, commit_hash_or_message).
    """
    if not repo.is_git_repo():
        repo.init()

    # Build exact audited file list
    target_files: list[str] = list(STANDARD_METADATA_FILES)
    for entry in manifest.entries:
        target_files.append(entry.destination)

    # Filter only files that exist in the repo
    existing_files: list[str] = []
    for rel_path in target_files:
        full_path = repo.repo_dir / rel_path
        if full_path.exists() or full_path.is_symlink():
            # Pre-stage secret validation
            if full_path.is_file() and not full_path.is_symlink():
                scan = scan_file_for_secrets(full_path)
                if scan.has_secret:
                    logger.warning("Secret detected in %s before git staging: %s. Omitting file!", rel_path, scan.reason)
                    continue
            existing_files.append(rel_path)

    # Perform audited staging
    ok, staged = repo.stage_files(existing_files)
    if not ok:
        return False, "Failed to stage audited files"

    # Check if there are changes to commit
    if not repo.has_uncommitted_changes():
        return True, "No changes to commit (working tree clean)"

    # Construct informative commit message
    if custom_message:
        msg = custom_message
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        omarchy_info = f"Omarchy {manifest.omarchy_version}" if manifest.omarchy_version else "Omarchy"
        hypr_info = f"Hyprland {manifest.hyprland_version}" if manifest.hyprland_version else "Hyprland"
        msg = f"backup: update configuration ({omarchy_info}, {hypr_info})\n\nRecorded at {timestamp}\nFiles backed up: {len(staged)}"

    res = repo.runner.run(["git", "commit", "-m", msg], cwd=repo.repo_dir)
    if res.success:
        hash_res = repo.runner.run(["git", "rev-parse", "HEAD"], cwd=repo.repo_dir)
        commit_hash = hash_res.stdout.strip() if hash_res.success else "committed"
        return True, commit_hash
    else:
        return False, f"Git commit failed: {res.stderr}"
