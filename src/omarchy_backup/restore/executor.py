"""Restore executor orchestrating atomic file restoration, plugins, and validation."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omarchy_backup.backup.checksum import calculate_sha256
from omarchy_backup.backup.snapshot import create_pre_restore_snapshot
from omarchy_backup.manifest import Manifest, ManifestEntry
from omarchy_backup.paths import AppPaths, default_paths
from omarchy_backup.plugins.hyprpm import restore_hyprpm_plugins
from omarchy_backup.plugins.omarchy import restore_omarchy_plugins
from omarchy_backup.restore.planner import ActionType, RestorePlan, plan_restore
from omarchy_backup.restore.rollback import rollback_snapshot
from omarchy_backup.restore.validator import check_compatibility, validate_live_system
from omarchy_backup.runner import CommandRunner, default_runner

logger = logging.getLogger(__name__)


@dataclass
class RestoreExecutionResult:
    """Summary of restore execution."""
    success: bool
    snapshot_path: Path | None = None
    files_applied: list[str] = field(default_factory=list)
    plugin_actions: list[str] = field(default_factory=list)
    service_actions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rolled_back: bool = False
    error: str = ""


class RestoreEngine:
    """Coordinates the transactional, safe restore pipeline."""

    def __init__(
        self,
        paths: AppPaths | None = None,
        runner: CommandRunner | None = None,
    ) -> None:
        self.paths = paths or default_paths
        self.runner = runner or default_runner

    def execute(
        self,
        backup_dir: Path,
        include_local: bool = False,
        exact: bool = False,
        auto_confirm: bool = False,
        reproducible_plugins: bool = False,
        skip_service_reload: bool = False,
    ) -> RestoreExecutionResult:
        """Run the full restore pipeline with pre-restore snapshot and rollback guard."""
        manifest_file = backup_dir / "manifest.json"
        if not manifest_file.is_file():
            return RestoreExecutionResult(
                success=False,
                error=f"Manifest not found in backup: {manifest_file}",
            )

        manifest = Manifest.load(manifest_file)
        warnings: list[str] = []

        # 1. Compatibility check
        compat_msgs = check_compatibility(backup_dir, self.runner)
        for severity, msg in compat_msgs:
            if severity == "WARNING":
                warnings.append(f"Compatibility warning: {msg}")

        # 2. Plan restore
        plan = plan_restore(
            manifest=manifest,
            backup_dir=backup_dir,
            paths=self.paths,
            include_local=include_local,
            exact=exact,
        )

        # 3. Create pre-restore snapshot
        snapshot_dir = create_pre_restore_snapshot(manifest, paths=self.paths)

        # 4. Record state file for crash recovery
        self._record_state("in_progress", snapshot_dir)

        # 5. Apply file restorations atomically
        applied_files: list[str] = []
        try:
            for action in plan.actions:
                if action.action_type in {ActionType.CREATE, ActionType.MODIFY}:
                    entry = action.manifest_entry
                    if not entry:
                        continue

                    source_backup = backup_dir / entry.destination
                    live_target = Path(entry.source.replace("~", str(self.paths.home)))
                    live_target.parent.mkdir(parents=True, exist_ok=True)

                    if entry.entry_type == "symlink":
                        if live_target.is_symlink() or live_target.exists():
                            live_target.unlink()
                        target = entry.symlink_target or os.readlink(source_backup)
                        live_target.symlink_to(target)
                        applied_files.append(str(live_target))
                    elif source_backup.is_file():
                        # Atomic file write
                        temp_file = None
                        with tempfile.NamedTemporaryFile(dir=live_target.parent, delete=False) as tmp:
                            temp_file = Path(tmp.name)
                            with open(source_backup, "rb") as src_f:
                                shutil.copyfileobj(src_f, tmp)
                            tmp.flush()
                            os.fsync(tmp.fileno())

                        # Check destination checksum
                        if entry.sha256:
                            actual_sha = calculate_sha256(temp_file)
                            if actual_sha.lower() != entry.sha256.lower():
                                temp_file.unlink(missing_ok=True)
                                raise ValueError(f"Checksum mismatch on restored file {live_target}")

                        mode_int = int(entry.mode, 8)
                        os.chmod(temp_file, mode_int)
                        temp_file.replace(live_target)
                        applied_files.append(str(live_target))

        except Exception as exc:
            logger.error("Error during file restore: %s. Initiating emergency rollback...", exc)
            rollback_snapshot(snapshot_dir, self.paths)
            self._record_state("rolled_back", snapshot_dir)
            return RestoreExecutionResult(
                success=False,
                snapshot_path=snapshot_dir,
                rolled_back=True,
                error=f"File restore failed, system rolled back: {exc}",
            )

        # 6. Restore plugins
        plugin_actions: list[str] = []
        omarchy_plugins_file = backup_dir / "plugins" / "omarchy-shell.json"
        if omarchy_plugins_file.is_file():
            try:
                with open(omarchy_plugins_file, "r", encoding="utf-8") as f:
                    rec_plugins = json.load(f)
                p_acts, p_warns = restore_omarchy_plugins(
                    recorded_plugins=rec_plugins,
                    paths=self.paths,
                    runner=self.runner,
                    auto_confirm=auto_confirm,
                    reproducible=reproducible_plugins,
                )
                plugin_actions.extend(p_acts)
                warnings.extend(p_warns)
            except Exception as exc:
                warnings.append(f"Plugin restore error: {exc}")

        # 7. Reload and validate system
        service_actions: list[str] = []
        if not skip_service_reload:
            if plan.has_hypr_changes:
                self.runner.run(["hyprctl", "reload"], timeout=5.0)
                service_actions.append("Reloaded Hyprland configuration")

                # Validate running Hyprland configuration
                valid, errors = validate_live_system(self.runner)
                if not valid:
                    logger.error("Hyprland configuration errors detected after reload: %s", errors)
                    # Trigger automatic rollback!
                    rollback_snapshot(snapshot_dir, self.paths)
                    self._record_state("rolled_back", snapshot_dir)
                    return RestoreExecutionResult(
                        success=False,
                        snapshot_path=snapshot_dir,
                        rolled_back=True,
                        warnings=errors,
                        error="Hyprland reported configuration errors. System automatically rolled back.",
                    )

            if plan.has_omarchy_changes or plan.has_plugin_changes:
                self.runner.run(["omarchy", "restart", "shell"], timeout=10.0)
                service_actions.append("Restarted Omarchy Shell")

        # 8. Mark state as completed
        self._record_state("completed", snapshot_dir)

        return RestoreExecutionResult(
            success=True,
            snapshot_path=snapshot_dir,
            files_applied=applied_files,
            plugin_actions=plugin_actions,
            service_actions=service_actions,
            warnings=warnings,
        )

    def _record_state(self, status: str, snapshot_path: Path) -> None:
        """Write restore state file for recovery detection."""
        state_file = self.paths.restore_state_file
        state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "operation": "restore",
            "status": status,
            "snapshot": str(snapshot_path),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def check_pending_recovery(self) -> dict[str, Any] | None:
        """Check if an unfinished restore operation is recorded."""
        state_file = self.paths.restore_state_file
        if not state_file.is_file():
            return None
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("status") == "in_progress":
                return data
        except Exception:
            pass
        return None

    def clear_recovery_state(self) -> None:
        """Remove recovery state file."""
        state_file = self.paths.restore_state_file
        if state_file.is_file():
            state_file.unlink(missing_ok=True)
