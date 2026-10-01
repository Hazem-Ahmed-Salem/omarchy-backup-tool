"""Validation routines for compatibility and live system health."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from omarchy_backup.discovery.system import discover_versions
from omarchy_backup.runner import CommandRunner, default_runner

logger = logging.getLogger(__name__)


def check_compatibility(
    backup_dir: Path,
    runner: CommandRunner | None = None,
) -> list[tuple[str, str]]:
    """Compare backup versions against current live system.

    Returns list of (severity, message) where severity is INFO, WARNING, or BLOCKING.
    """
    r = runner or default_runner
    messages: list[tuple[str, str]] = []

    versions_file = backup_dir / "versions.json"
    if not versions_file.is_file():
        messages.append(("INFO", "No versions.json in backup; skipping version comparison."))
        return messages

    try:
        with open(versions_file, "r", encoding="utf-8") as f:
            backup_versions = json.load(f)
    except Exception as exc:
        messages.append(("WARNING", f"Could not parse backup versions: {exc}"))
        return messages

    current_versions = discover_versions(r)

    backup_omarchy = backup_versions.get("omarchy", "unknown")
    current_omarchy = current_versions.get("omarchy", "unknown")

    if backup_omarchy != "unknown" and current_omarchy != "unknown":
        b_major = backup_omarchy.split(".")[0]
        c_major = current_omarchy.split(".")[0]
        if b_major != c_major:
            messages.append((
                "WARNING",
                f"Backup created on Omarchy major version {b_major}.x, but current system is {c_major}.x. Migration may be required.",
            ))
        else:
            messages.append(("INFO", f"Omarchy versions match major branch ({backup_omarchy} -> {current_omarchy})."))

    backup_hypr = backup_versions.get("hyprland", "unknown")
    current_hypr = current_versions.get("hyprland", "unknown")

    if backup_hypr != "unknown" and current_hypr != "unknown":
        if backup_hypr != current_hypr:
            messages.append(("INFO", f"Hyprland version difference: {backup_hypr} (backup) vs {current_hypr} (current)."))

    return messages


def validate_live_system(runner: CommandRunner | None = None) -> tuple[bool, list[str]]:
    """Validate Hyprland configuration errors via official hyprctl commands."""
    r = runner or default_runner
    errors: list[str] = []

    # Check if Hyprland is actively running
    hypr_res = r.run(["hyprctl", "monitors"], timeout=3.0)
    if not hypr_res.success:
        logger.debug("Hyprland does not appear to be running or responsive to hyprctl.")
        return True, []

    # Query config errors
    err_res = r.run(["hyprctl", "configerrors"], timeout=5.0)
    if err_res.success and err_res.stdout.strip():
        # Configuration errors found
        raw_err = err_res.stdout.strip()
        errors.append(raw_err)
        return False, errors

    return True, []
