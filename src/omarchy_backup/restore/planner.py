"""Restore planner generating atomic action graphs before execution."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from omarchy_backup.backup.checksum import calculate_sha256
from omarchy_backup.manifest import Manifest, ManifestEntry
from omarchy_backup.paths import AppPaths, default_paths


class ActionType(str, Enum):
    CREATE = "CREATE"
    MODIFY = "MODIFY"
    DELETE = "DELETE"
    INSTALL_PLUGIN = "INSTALL_PLUGIN"
    ENABLE_PLUGIN = "ENABLE_PLUGIN"
    DISABLE_PLUGIN = "DISABLE_PLUGIN"
    RELOAD_SERVICE = "RELOAD_SERVICE"
    RESTART_SERVICE = "RESTART_SERVICE"
    PACKAGE_INSTALL = "PACKAGE_INSTALL"
    SKIP_LOCAL = "SKIP_LOCAL"


@dataclass
class RestoreAction:
    """Individual atomic operation in the restore plan."""
    action_type: ActionType
    target: str
    details: str = ""
    source: str = ""
    manifest_entry: ManifestEntry | None = None


@dataclass
class RestorePlan:
    """Complete, pre-computed restore plan."""
    actions: list[RestoreAction] = field(default_factory=list)
    skipped_local: list[str] = field(default_factory=list)
    has_hypr_changes: bool = False
    has_omarchy_changes: bool = False
    has_plugin_changes: bool = False

    def render_text(self) -> str:
        """Render a clean, human-readable plan description."""
        lines = [
            "=" * 60,
            "RESTORE PLAN",
            "=" * 60,
            "",
            "Files:",
        ]

        file_actions = [a for a in self.actions if a.action_type in {ActionType.CREATE, ActionType.MODIFY, ActionType.DELETE}]
        if not file_actions:
            lines.append("  (No file modifications required)")
        else:
            for act in file_actions:
                lines.append(f"  {act.action_type.value:<6} {act.target}")

        plugin_actions = [a for a in self.actions if a.action_type in {ActionType.INSTALL_PLUGIN, ActionType.ENABLE_PLUGIN, ActionType.DISABLE_PLUGIN}]
        lines.append("\nPlugins:")
        if not plugin_actions:
            lines.append("  (No plugin changes required)")
        else:
            for act in plugin_actions:
                lines.append(f"  {act.action_type.value:<14} {act.target} ({act.details})")

        service_actions = [a for a in self.actions if a.action_type in {ActionType.RELOAD_SERVICE, ActionType.RESTART_SERVICE}]
        lines.append("\nServices:")
        if not service_actions:
            lines.append("  (No service restarts required)")
        else:
            for act in service_actions:
                lines.append(f"  {act.action_type.value:<15} {act.target}")

        if self.skipped_local:
            lines.append("\nLocal configuration (omitted without --include-local):")
            for item in self.skipped_local:
                lines.append(f"  NOT INCLUDED: {item}")

        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)


def plan_restore(
    manifest: Manifest,
    backup_dir: Path,
    paths: AppPaths | None = None,
    include_local: bool = False,
    exact: bool = False,
    packages: bool = False,
) -> RestorePlan:
    """Generate restore plan comparing backup manifest against the live system."""
    p = paths or default_paths
    actions: list[RestoreAction] = []
    skipped_local: list[str] = []

    has_hypr = False
    has_omarchy = False
    has_plugins = False

    # 1. Compare manifest file entries against live system
    for entry in manifest.entries:
        # Check local vs portable scope
        if entry.scope == "local" and not include_local:
            skipped_local.append(entry.destination)
            continue

        backup_file = backup_dir / entry.destination
        live_file = Path(entry.source.replace("~", str(p.home)))

        if not backup_file.exists():
            continue

        if not live_file.exists():
            actions.append(
                RestoreAction(
                    action_type=ActionType.CREATE,
                    target=str(live_file),
                    source=str(backup_file),
                    manifest_entry=entry,
                )
            )
            if "hypr/" in entry.destination:
                has_hypr = True
            elif "omarchy/" in entry.destination:
                has_omarchy = True
        else:
            # Check checksum
            try:
                live_sha = calculate_sha256(live_file)
                if live_sha.lower() != entry.sha256.lower():
                    actions.append(
                        RestoreAction(
                            action_type=ActionType.MODIFY,
                            target=str(live_file),
                            source=str(backup_file),
                            manifest_entry=entry,
                        )
                    )
                    if "hypr/" in entry.destination:
                        has_hypr = True
                    elif "omarchy/" in entry.destination:
                        has_omarchy = True
            except Exception:
                actions.append(
                    RestoreAction(
                        action_type=ActionType.MODIFY,
                        target=str(live_file),
                        source=str(backup_file),
                        manifest_entry=entry,
                    )
                )

    # 2. Check plugins
    omarchy_plugins_file = backup_dir / "plugins" / "omarchy-shell.json"
    if omarchy_plugins_file.is_file():
        try:
            with open(omarchy_plugins_file, "r", encoding="utf-8") as f:
                p_list = json.load(f)
            installed_dir = p.omarchy_config_dir / "plugins"
            existing_ids = {d.name for d in installed_dir.iterdir()} if installed_dir.is_dir() else set()

            for pl in p_list:
                pid = pl.get("id")
                repo = pl.get("repository")
                if pid and pid not in existing_ids and repo:
                    actions.append(
                        RestoreAction(
                            action_type=ActionType.INSTALL_PLUGIN,
                            target=pid,
                            details=repo,
                        )
                    )
                    has_plugins = True
        except Exception:
            pass

    # 3. Service notifications/reloads
    if has_hypr:
        actions.append(
            RestoreAction(
                action_type=ActionType.RELOAD_SERVICE,
                target="Hyprland (hyprctl reload)",
            )
        )
    if has_omarchy or has_plugins:
        actions.append(
            RestoreAction(
                action_type=ActionType.RESTART_SERVICE,
                target="Omarchy Shell (omarchy restart shell)",
            )
        )

    return RestorePlan(
        actions=actions,
        skipped_local=skipped_local,
        has_hypr_changes=has_hypr,
        has_omarchy_changes=has_omarchy,
        has_plugin_changes=has_plugins,
    )
