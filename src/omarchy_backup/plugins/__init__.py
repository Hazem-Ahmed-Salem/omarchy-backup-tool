"""Plugin discovery and restoration modules."""

from omarchy_backup.plugins.hyprpm import restore_hyprpm_plugins
from omarchy_backup.plugins.omarchy import restore_omarchy_plugins
from omarchy_backup.plugins.prompt import PluginPromptHandler

__all__ = [
    "restore_omarchy_plugins",
    "restore_hyprpm_plugins",
    "PluginPromptHandler",
]
