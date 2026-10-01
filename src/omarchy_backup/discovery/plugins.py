"""Discovery of Omarchy shell plugins and Hyprland hyprpm plugins."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from omarchy_backup.paths import AppPaths, default_paths
from omarchy_backup.runner import CommandRunner, default_runner

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredPlugin:
    """Discovered plugin with metadata and reproducible git information."""
    id: str
    name: str
    plugin_type: str  # "omarchy-shell" or "hyprpm"
    repository: str
    enabled: bool = True
    revision: str = ""
    branch: str = ""
    version: str = ""
    first_party: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveredPlugin:
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            plugin_type=data.get("plugin_type", data.get("type", "omarchy-shell")),
            repository=data.get("repository", ""),
            enabled=data.get("enabled", True),
            revision=data.get("revision", ""),
            branch=data.get("branch", ""),
            version=data.get("version", ""),
            first_party=data.get("first_party", False),
        )


def discover_omarchy_plugins(
    paths: AppPaths | None = None,
    runner: CommandRunner | None = None,
) -> list[DiscoveredPlugin]:
    """Discover user-installed Omarchy shell plugins and their git repositories."""
    p = paths or default_paths
    r = runner or default_runner
    plugins_dir = p.omarchy_config_dir / "plugins"

    # Query CLI for enabled states and firstParty indicators
    cli_status_map: dict[str, dict[str, Any]] = {}
    cli_res = r.run(["omarchy", "plugin", "list", "--json"], timeout=5.0)
    if cli_res.success:
        try:
            cli_data = json.loads(cli_res.stdout)
            if isinstance(cli_data, list):
                for item in cli_data:
                    pid = item.get("id")
                    if pid:
                        cli_status_map[pid] = item
        except json.JSONDecodeError:
            logger.debug("Could not parse 'omarchy plugin list --json' output.")

    discovered: list[DiscoveredPlugin] = []

    if not plugins_dir.is_dir():
        return discovered

    for plugin_path in sorted(plugins_dir.iterdir()):
        if not plugin_path.is_dir():
            continue

        plugin_id = plugin_path.name
        manifest_file = plugin_path / "manifest.json"

        name = plugin_id
        version = ""
        repo_url = ""

        # Read manifest if present
        if manifest_file.is_file():
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    manifest_data = json.load(f)
                name = manifest_data.get("name", plugin_id)
                version = manifest_data.get("version", "")
                repo_url = manifest_data.get("repository", "")
            except Exception as exc:
                logger.debug("Failed reading %s: %s", manifest_file, exc)

        # Inspect git repository for exact commit and remote
        git_dir = plugin_path / ".git"
        git_repo = ""
        git_rev = ""
        git_branch = ""

        if git_dir.exists():
            remote_res = r.run(["git", "-C", str(plugin_path), "remote", "get-url", "origin"], timeout=3.0)
            if remote_res.success:
                git_repo = remote_res.stdout.strip()

            rev_res = r.run(["git", "-C", str(plugin_path), "rev-parse", "HEAD"], timeout=3.0)
            if rev_res.success:
                git_rev = rev_res.stdout.strip()

            branch_res = r.run(["git", "-C", str(plugin_path), "rev-parse", "--abbrev-ref", "HEAD"], timeout=3.0)
            if branch_res.success and branch_res.stdout.strip() != "HEAD":
                git_branch = branch_res.stdout.strip()

        final_repo = git_repo or repo_url
        cli_info = cli_status_map.get(plugin_id, {})
        enabled = cli_info.get("enabled", True)
        first_party = cli_info.get("firstParty", False)

        # We only record plugins that have a repository or are user-installed
        if final_repo or not first_party:
            discovered.append(
                DiscoveredPlugin(
                    id=plugin_id,
                    name=name,
                    plugin_type="omarchy-shell",
                    repository=final_repo,
                    enabled=enabled,
                    revision=git_rev,
                    branch=git_branch,
                    version=version,
                    first_party=first_party,
                )
            )

    return discovered


def discover_hyprpm_plugins(runner: CommandRunner | None = None) -> list[DiscoveredPlugin]:
    """Discover installed Hyprland plugins via hyprpm safely without blocking."""
    if not Path("/var/cache/hyprpm").is_dir():
        logger.debug("hyprpm state store (/var/cache/hyprpm) not present; skipping hyprpm.")
        return []

    r = runner or default_runner
    res = r.run(["hyprpm", "list"], timeout=4.0, stdin_null=True)
    if not res.success or "password for" in res.stderr or "password for" in res.stdout:
        logger.debug("hyprpm list not available or requires setup: %s", res.stderr or res.stdout)
        return []

    discovered: list[DiscoveredPlugin] = []
    current_repo = ""
    lines = res.stdout.splitlines()

    for line in lines:
        line_clean = line.strip()
        # Typical hyprpm list format:
        # -> Repository: https://github.com/...
        #   Plugin: my-plugin (enabled)
        if "Repository" in line_clean:
            parts = line_clean.split(":", 1)
            if len(parts) == 2:
                current_repo = parts[1].strip()
        elif "Plugin" in line_clean and current_repo:
            parts = line_clean.split(":", 1)
            if len(parts) == 2:
                p_info = parts[1].strip()
                enabled = "enabled" in p_info.lower()
                p_name = p_info.split()[0]
                discovered.append(
                    DiscoveredPlugin(
                        id=p_name,
                        name=p_name,
                        plugin_type="hyprpm",
                        repository=current_repo,
                        enabled=enabled,
                    )
                )

    return discovered


def discover_all_plugins(
    paths: AppPaths | None = None,
    runner: CommandRunner | None = None,
) -> dict[str, list[DiscoveredPlugin]]:
    """Discover both Omarchy shell plugins and Hyprland plugins."""
    return {
        "omarchy-shell": discover_omarchy_plugins(paths=paths, runner=runner),
        "hyprpm": discover_hyprpm_plugins(runner=runner),
    }
