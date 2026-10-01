"""Exclusion patterns and rules to protect secrets and avoid noise."""

from __future__ import annotations

import fnmatch
from pathlib import Path

# Built-in exclusion patterns for file and directory names
DEFAULT_EXCLUSION_PATTERNS: list[str] = [
    # Secret files & keys
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.pkcs12",
    "id_rsa*",
    "id_ed25519*",
    "id_ecdsa*",
    "id_dsa*",
    "*.keystore",
    # Environment and credentials
    ".env",
    ".env.*",
    "*credential*",
    "*token*",
    "*secret*",
    "*password*",
    ".netrc",
    ".git-credentials",
    # Backup files and editor artifacts
    "*.bak",
    "*.bak.*",
    "*~",
    "*.swp",
    "*.swo",
    "*.tmp",
    "#*#",
    # Git & caches
    ".git",
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".venv",
]

# Sensitive directories that must never be scanned or backed up
PROTECTED_DIRECTORY_NAMES: set[str] = {
    ".git",
    ".ssh",
    ".gnupg",
    ".pki",
    ".password-store",
    ".mozilla",
    ".google-chrome",
    ".chromium",
    ".brave",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    ".venv",
}


def should_exclude_path(
    path: Path | str,
    custom_patterns: list[str] | None = None,
) -> tuple[bool, str]:
    """Check if a path should be excluded based on name or pattern.

    Returns (is_excluded, reason).
    """
    p = Path(path)
    name = p.name
    name_lower = name.lower()

    # Check protected directories in any parent part
    for part in p.parts:
        if part in PROTECTED_DIRECTORY_NAMES:
            return True, f"Path contains protected directory '{part}'"

    # Check explicit default patterns
    for pattern in DEFAULT_EXCLUSION_PATTERNS:
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(name_lower, pattern.lower()):
            return True, f"Matches exclusion pattern '{pattern}'"

    # Check custom patterns
    if custom_patterns:
        for pattern in custom_patterns:
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(str(p), pattern):
                return True, f"Matches custom exclusion pattern '{pattern}'"

    return False, ""


def is_excluded_path(path: Path | str, custom_patterns: list[str] | None = None) -> bool:
    """Convenience boolean check for exclusion."""
    excluded, _ = should_exclude_path(path, custom_patterns)
    return excluded
