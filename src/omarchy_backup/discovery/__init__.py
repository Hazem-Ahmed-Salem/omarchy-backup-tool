"""Discovery package initialization."""

from omarchy_backup.discovery.hyprland import discover_hyprland_files
from omarchy_backup.discovery.omarchy import discover_omarchy_files
from omarchy_backup.discovery.packages import discover_packages
from omarchy_backup.discovery.plugins import DiscoveredPlugin, discover_all_plugins
from omarchy_backup.discovery.scripts import discover_custom_scripts
from omarchy_backup.discovery.system import discover_system_info, discover_versions

__all__ = [
    "discover_hyprland_files",
    "discover_omarchy_files",
    "discover_all_plugins",
    "DiscoveredPlugin",
    "discover_packages",
    "discover_custom_scripts",
    "discover_versions",
    "discover_system_info",
]
