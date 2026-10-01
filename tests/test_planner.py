"""Tests for restore plan generation and dry-run calculations."""

import tempfile
import unittest
from pathlib import Path

from omarchy_backup.backup.checksum import calculate_sha256
from omarchy_backup.manifest import Manifest, ManifestEntry
from omarchy_backup.paths import AppPaths
from omarchy_backup.restore.planner import ActionType, plan_restore


class TestRestorePlanner(unittest.TestCase):
    def test_plan_actions(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_home = Path(tmp_dir) / "home"
            fake_backup = Path(tmp_dir) / "backup"
            fake_home.mkdir()
            fake_backup.mkdir()

            paths = AppPaths(home=fake_home)

            # Create backup files
            hypr_backup = fake_backup / "hypr"
            hypr_backup.mkdir()
            bindings_backup = hypr_backup / "bindings.lua"
            bindings_backup.write_text("hl.bind('SUPER', 'Return')\n")
            sha_bindings = calculate_sha256(bindings_backup)

            monitors_backup = hypr_backup / "monitors.lua"
            monitors_backup.write_text("hl.monitor('DP-1')\n")
            sha_monitors = calculate_sha256(monitors_backup)

            manifest = Manifest(
                entries=[
                    ManifestEntry(
                        source="~/.config/hypr/bindings.lua",
                        destination="hypr/bindings.lua",
                        entry_type="file",
                        scope="portable",
                        sha256=sha_bindings,
                    ),
                    ManifestEntry(
                        source="~/.config/hypr/monitors.lua",
                        destination="hypr/monitors.lua",
                        entry_type="file",
                        scope="local",
                        sha256=sha_monitors,
                    ),
                ]
            )

            # Case 1: Live system does not have bindings.lua (CREATE) and local config is excluded by default
            plan = plan_restore(manifest, fake_backup, paths=paths, include_local=False)
            create_actions = [a for a in plan.actions if a.action_type == ActionType.CREATE]
            self.assertEqual(len(create_actions), 1)
            self.assertIn("bindings.lua", create_actions[0].target)
            self.assertIn("hypr/monitors.lua", plan.skipped_local)

            # Case 2: include_local=True includes monitors.lua
            plan_with_local = plan_restore(manifest, fake_backup, paths=paths, include_local=True)
            self.assertEqual(len(plan_with_local.skipped_local), 0)
            self.assertEqual(len([a for a in plan_with_local.actions if a.action_type == ActionType.CREATE]), 2)


if __name__ == "__main__":
    unittest.main()
