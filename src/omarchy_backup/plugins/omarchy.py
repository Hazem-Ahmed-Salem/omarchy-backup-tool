"""Restoration of Omarchy shell plugins from recorded metadata."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from omarchy_backup.paths import AppPaths, default_paths
from omarchy_backup.runner import CommandRunner, default_runner

logger = logging.getLogger(__name__)


def restore_omarchy_plugins(
    recorded_plugins: list[dict[str, Any]],
    paths: AppPaths | None = None,
    runner: CommandRunner | None = None,
    auto_confirm: bool = False,
    reproducible: bool = False,
) -> tuple[list[str], list[str]]:
    """Install missing Omarchy shell plugins and restore enabled state.

    Returns (actions_taken, warnings).
    """
    p = paths or default_paths
    r = runner or default_runner
    actions: list[str] = []
    warnings: list[str] = []

    # 1. Discover already installed plugins
    installed_ids: set[str] = set()
    plugins_dir = p.omarchy_config_dir / "plugins"
    if plugins_dir.is_dir():
        for d in plugins_dir.iterdir():
            if d.is_dir():
                installed_ids.add(d.name)

    # Also check CLI
    cli_res = r.run(["omarchy", "plugin", "list", "--json"], timeout=5.0)
    cli_map: dict[str, dict[str, Any]] = {}
    if cli_res.success:
        try:
            cli_data = json.loads(cli_res.stdout)
            for item in cli_data:
                pid = item.get("id")
                if pid:
                    installed_ids.add(pid)
                    cli_map[pid] = item
        except Exception:
            pass

    for plugin in recorded_plugins:
        pid = plugin.get("id", "")
        repo = plugin.get("repository", "")
        enabled = plugin.get("enabled", True)
        revision = plugin.get("revision", "")

        if not pid and not repo:
            continue

        # Case 1: Plugin is missing and has repository URL
        if pid not in installed_ids and repo:
            logger.info("Installing missing Omarchy plugin '%s' from %s", pid or repo, repo)
            cmd = ["omarchy", "plugin", "add", repo]
            if enabled:
                cmd.append("--enable")
            if auto_confirm:
                cmd.append("--yes")

            res = r.run(cmd, timeout=60.0)
            if res.success:
                actions.append(f"Installed plugin {pid or repo}")
                # Optional checkout of recorded revision
                if reproducible and revision and pid:
                    target_dir = plugins_dir / pid
                    if target_dir.exists():
                        r.run(["git", "-C", str(target_dir), "checkout", revision], timeout=5.0)
                        actions.append(f"Checked out revision {revision[:8]} for {pid}")
            else:
                warnings.append(f"Failed to install plugin {pid or repo}: {res.stderr or res.stdout}")

        # Case 2: Plugin is already installed, ensure enabled state matches
        elif pid in installed_ids:
            current_status = cli_map.get(pid, {}).get("enabled")
            if current_status is not None and current_status != enabled:
                sub_cmd = "enable" if enabled else "disable"
                res = r.run(["omarchy", "plugin", sub_cmd, pid], timeout=5.0)
                if res.success:
                    actions.append(f"Set plugin {pid} state to {sub_cmd}d")
                else:
                    warnings.append(f"Failed to set plugin {pid} to {sub_cmd}: {res.stderr}")

    return actions, warnings
