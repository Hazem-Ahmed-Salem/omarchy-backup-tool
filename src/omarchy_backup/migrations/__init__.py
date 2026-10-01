"""Backup format migrations package."""

from omarchy_backup.migrations.v1 import migrate_to_v1

__all__ = ["migrate_to_v1"]
