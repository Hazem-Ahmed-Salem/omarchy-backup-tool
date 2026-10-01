"""System and component version discovery."""

from __future__ import annotations

import json
import logging
import os
import platform
import socket
from pathlib import Path
from typing import Any

from omarchy_backup.runner import CommandRunner, default_runner

logger = logging.getLogger(__name__)


def discover_versions(runner: CommandRunner | None = None) -> dict[str, str]:
    """Dynamically discover versions of Omarchy, Hyprland, Quickshell, etc."""
    r = runner or default_runner

    omarchy_ver = r.capture(["omarchy", "version"]) or "unknown"

    hypr_res = r.run(["hyprctl", "version"], timeout=3.0)
    hypr_ver = "unknown"
    if hypr_res.success:
        first_line = hypr_res.stdout.splitlines()[0] if hypr_res.stdout.splitlines() else ""
        if "Hyprland" in first_line:
            hypr_ver = first_line.split()[1] if len(first_line.split()) > 1 else first_line

    hyprpm_ver = "unknown"
    if Path("/var/cache/hyprpm").is_dir():
        hyprpm_res = r.run(["hyprpm", "-v"], timeout=2.0)
        hyprpm_ver = hyprpm_res.stdout.strip() if hyprpm_res.success else "unknown"

    qs_res = r.run(["quickshell", "--version"], timeout=3.0)
    qs_ver = "unknown"
    if qs_res.success:
        qs_parts = qs_res.stdout.split()
        qs_ver = qs_parts[1] if len(qs_parts) > 1 else qs_res.stdout.strip()

    return {
        "omarchy": omarchy_ver,
        "hyprland": hypr_ver,
        "linux": platform.release(),
        "hyprpm": hyprpm_ver,
        "quickshell": qs_ver,
        "python": platform.python_version(),
        "architecture": platform.machine(),
    }


def discover_system_info(runner: CommandRunner | None = None) -> dict[str, Any]:
    """Discover hardware diagnostics, displays, and platform details."""
    r = runner or default_runner

    # Displays
    monitors_data: Any = []
    mon_res = r.run(["hyprctl", "monitors", "-j"], timeout=3.0)
    if mon_res.success:
        try:
            monitors_data = json.loads(mon_res.stdout)
        except Exception:
            monitors_data = []

    # Memory info
    mem_total_mb = 0
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_total_mb = int(line.split()[1]) // 1024
                    break
    except Exception:
        pass

    # CPU model
    cpu_model = "unknown"
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if "model name" in line:
                    cpu_model = line.split(":", 1)[1].strip()
                    break
    except Exception:
        pass

    # GPU
    gpu_res = r.run(["lspci"], timeout=3.0)
    gpus: list[str] = []
    if gpu_res.success:
        for line in gpu_res.stdout.splitlines():
            if "VGA" in line or "3D" in line or "Display" in line:
                gpus.append(line.strip())

    return {
        "hostname": socket.gethostname(),
        "architecture": platform.machine(),
        "cpu": cpu_model,
        "memory_total_mb": mem_total_mb,
        "gpus": gpus,
        "displays": monitors_data,
    }
