"""Discovery of installed package lists (native, AUR, explicit)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from omarchy_backup.runner import CommandRunner, default_runner

logger = logging.getLogger(__name__)


@dataclass
class PackageLists:
    """Installed package collections."""
    native: list[str]
    aur: list[str]
    explicit: list[str]


def discover_packages(runner: CommandRunner | None = None) -> PackageLists:
    """Query pacman to record explicitly installed packages."""
    r = runner or default_runner

    native_res = r.run(["pacman", "-Qenq"], timeout=5.0)
    native_pkgs = sorted([p.strip() for p in native_res.stdout.splitlines() if p.strip()]) if native_res.success else []

    aur_res = r.run(["pacman", "-Qemq"], timeout=5.0)
    aur_pkgs = sorted([p.strip() for p in aur_res.stdout.splitlines() if p.strip()]) if aur_res.success else []

    explicit_res = r.run(["pacman", "-Qeq"], timeout=5.0)
    explicit_pkgs = sorted([p.strip() for p in explicit_res.stdout.splitlines() if p.strip()]) if explicit_res.success else []

    return PackageLists(
        native=native_pkgs,
        aur=aur_pkgs,
        explicit=explicit_pkgs,
    )
