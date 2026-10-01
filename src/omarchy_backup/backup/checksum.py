"""Checksum calculation and verification routines."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path


def calculate_sha256(path: Path | str) -> str:
    """Calculate the hex SHA-256 digest of a file."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Cannot calculate checksum, file not found: {p}")

    hasher = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def calculate_bytes_sha256(data: bytes) -> str:
    """Calculate hex SHA-256 digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def verify_file_sha256(path: Path | str, expected_hash: str) -> bool:
    """Verify that a file's SHA-256 matches expected digest."""
    try:
        actual = calculate_sha256(path)
        return actual.lower() == expected_hash.lower()
    except (FileNotFoundError, OSError):
        return False


def get_file_mode_str(path: Path | str) -> str:
    """Return file permissions as octal string, e.g. '0644' or '0755'."""
    p = Path(path)
    mode = stat.S_IMODE(p.stat().st_mode)
    return oct(mode)[2:].zfill(4)
