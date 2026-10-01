"""Plugin restoration and management package."""

from omarchy_backup.plugins.hyprpm import restore_hyprpm_plugins
from omarchy_backup.plugins.omarchy import restore_omarchy_plugins

__all__ = [
    "restore_omarchy_plugins",
    "restore_hyprpm_plugins",
]
