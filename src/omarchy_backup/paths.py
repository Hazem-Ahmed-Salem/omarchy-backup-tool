"""Path resolution and environment paths for omarchy-backup."""

from __future__ import annotations

import os
from pathlib import Path


class AppPaths:
    """Manages paths used by omarchy-backup with test override support."""

    def __init__(self, home: Path | None = None, backup_dir: Path | None = None) -> None:
        self._home = (home or Path.home()).resolve()
        self._custom_backup_dir = backup_dir.resolve() if backup_dir else None

    @property
    def home(self) -> Path:
        return self._home

    @property
    def config_dir(self) -> Path:
        """User ~/.config directory."""
        xdg_config = os.getenv("XDG_CONFIG_HOME")
        if xdg_config and not self._is_custom_home:
            return Path(xdg_config).resolve()
        return self._home / ".config"

    @property
    def state_dir(self) -> Path:
        """Application state directory (~/.local/state/omarchy-backup)."""
        xdg_state = os.getenv("XDG_STATE_HOME")
        base = Path(xdg_state).resolve() if (xdg_state and not self._is_custom_home) else (self._home / ".local" / "state")
        return base / "omarchy-backup"

    @property
    def app_config_file(self) -> Path:
        """Tool config file (~/.config/omarchy-backup/config.json)."""
        return self.config_dir / "omarchy-backup" / "config.json"

    @property
    def logs_dir(self) -> Path:
        return self.state_dir / "logs"

    @property
    def snapshots_dir(self) -> Path:
        return self.state_dir / "snapshots"

    @property
    def restore_state_file(self) -> Path:
        return self.state_dir / ".restore-state.json"

    @property
    def hypr_config_dir(self) -> Path:
        return self.config_dir / "hypr"

    @property
    def omarchy_config_dir(self) -> Path:
        return self.config_dir / "omarchy"

    @property
    def local_bin_dir(self) -> Path:
        return self._home / ".local" / "bin"

    @property
    def default_backup_dir(self) -> Path:
        if self._custom_backup_dir:
            return self._custom_backup_dir
        return self._home / "omarchy-config-backup"

    @property
    def _is_custom_home(self) -> bool:
        return self._home != Path.home().resolve()


# Default singleton instance
default_paths = AppPaths()
