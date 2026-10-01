"""Restoration of Hyprland plugins via hyprpm."""

from __future__ import annotations

import logging
from typing import Any

from omarchy_backup.runner import CommandRunner, default_runner

logger = logging.getLogger(__name__)


def restore_hyprpm_plugins(
    recorded_plugins: list[dict[str, Any]],
    runner: CommandRunner | None = None,
) -> tuple[list[str], list[str]]:
    """Restore hyprpm plugins safely using non-interactive command execution."""
    r = runner or default_runner
    actions: list[str] = []
    warnings: list[str] = []

    if not recorded_plugins:
        return actions, warnings

    # Test hyprpm readiness
    test_res = r.run(["hyprpm", "list"], timeout=4.0, stdin_null=True)
    if not test_res.success or "password for" in test_res.stderr or "password for" in test_res.stdout:
        warnings.append("hyprpm is not initialized or requires root permissions. Hyprland plugins skipped.")
        return actions, warnings

    for plugin in recorded_plugins:
        name = plugin.get("name", "")
        repo = plugin.get("repository", "")
        enabled = plugin.get("enabled", True)
        revision = plugin.get("revision", "")

        if not repo:
            continue

        add_cmd = ["hyprpm", "add", repo]
        if revision:
            add_cmd.append(revision)

        res = r.run(add_cmd, timeout=30.0, stdin_null=True)
        if res.success or "already installed" in res.stdout.lower():
            if enabled and name:
                en_res = r.run(["hyprpm", "enable", name], timeout=10.0, stdin_null=True)
                if en_res.success:
                    actions.append(f"Enabled hyprpm plugin {name}")
                else:
                    warnings.append(f"Could not enable hyprpm plugin {name}: {en_res.stderr}")
            actions.append(f"Configured hyprpm plugin from {repo}")
        else:
            warnings.append(f"hyprpm add failed for {repo}: {res.stderr or res.stdout}")

    return actions, warnings
