"""Security package initialization."""

from omarchy_backup.security.exclusions import is_excluded_path, should_exclude_path
from omarchy_backup.security.secrets import SecretScanResult, scan_file_for_secrets, scan_text_for_secrets

__all__ = [
    "is_excluded_path",
    "should_exclude_path",
    "SecretScanResult",
    "scan_file_for_secrets",
    "scan_text_for_secrets",
]
