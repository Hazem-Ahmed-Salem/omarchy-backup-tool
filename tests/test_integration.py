"""Comprehensive integration test verifying backup, modification, restore, and rollback in a sandboxed HOME."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from omarchy_backup.backup.collector import BackupCollector
from omarchy_backup.backup.snapshot import get_latest_snapshot
from omarchy_backup.config import BackupConfig
from omarchy_backup.paths import AppPaths
from omarchy_backup.restore.executor import RestoreEngine
from omarchy_backup.restore.rollback import rollback_latest_snapshot
from omarchy_backup.runner import CommandResult, CommandRunner


class MockCommandRunner(CommandRunner):
    """Mock command runner to prevent running real desktop commands during tests."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[list[str]] = []

    def run(self, cmd, cwd=None, timeout=None, env=None, capture_output=True, stdin_null=True):
        cmd_list = [str(c) for c in cmd]
        self.calls.append(cmd_list)
        prog = cmd_list[0]

        if prog == "git":
            # For git, we can either run actual git commands in the temporary repo or mock
            # In our test sandbox, running real git in the temp repo is great!
            return super().run(cmd, cwd=cwd, timeout=timeout, env=env, capture_output=capture_output)

        if prog == "omarchy":
            if len(cmd_list) > 1 and cmd_list[1] == "version":
                return CommandResult(cmd_list, 0, "4.0.4-1\n", "")
            if len(cmd_list) > 2 and cmd_list[1] == "plugin" and cmd_list[2] == "list":
                return CommandResult(cmd_list, 0, "[]\n", "")
            return CommandResult(cmd_list, 0, "ok\n", "")

        if prog == "hyprctl":
            if len(cmd_list) > 1 and cmd_list[1] == "version":
                return CommandResult(cmd_list, 0, "Hyprland 0.56.2\n", "")
            if len(cmd_list) > 1 and cmd_list[1] == "configerrors":
                return CommandResult(cmd_list, 0, "", "")
            return CommandResult(cmd_list, 0, "ok\n", "")

        if prog == "pacman":
            return CommandResult(cmd_list, 0, "sample-pkg\n", "")

        return CommandResult(cmd_list, 0, "", "")


class TestIntegrationWorkflow(unittest.TestCase):
    def setUp(self):
        self.test_root = Path(tempfile.mkdtemp(prefix="omarchy-backup-test-"))
        self.fake_home = self.test_root / "home" / "testuser"
        self.fake_home.mkdir(parents=True)

        self.paths = AppPaths(home=self.fake_home)
        self.runner = MockCommandRunner()

        # Seed mock user environment
        self.hypr_dir = self.paths.hypr_config_dir
        self.hypr_dir.mkdir(parents=True)
        (self.hypr_dir / "bindings.lua").write_text('hl.bind("SUPER", "Q", hl.killactive)\n')
        (self.hypr_dir / "input.lua").write_text('hl.input({ kb_layout = "us" })\n')
        (self.hypr_dir / "monitors.lua").write_text('hl.monitor({ output = "eDP-1" })\n')

        self.omarchy_dir = self.paths.omarchy_config_dir
        self.omarchy_dir.mkdir(parents=True)
        (self.omarchy_dir / "shell.json").write_text('{"theme": "dark"}\n')

        self.backup_dir = self.fake_home / "omarchy-config-backup"
        self.config = BackupConfig(backup_dir=str(self.backup_dir), include_packages=False)

    def tearDown(self):
        shutil.rmtree(self.test_root, ignore_errors=True)

    def test_full_backup_modify_restore_rollback_cycle(self):
        # 1. RUN BACKUP
        collector = BackupCollector(config=self.config, paths=self.paths, runner=self.runner)
        backup_res = collector.collect(target_dir=self.backup_dir)
        self.assertTrue(backup_res.success)
        self.assertTrue((self.backup_dir / "manifest.json").exists())
        self.assertTrue((self.backup_dir / "hypr" / "bindings.lua").exists())
        self.assertTrue((self.backup_dir / "omarchy" / "shell.json").exists())

        # 2. MODIFY CONFIGURATION (Simulate user changes or accidental corruption)
        (self.hypr_dir / "bindings.lua").write_text('-- Corrupted or modified bindings\n')
        (self.omarchy_dir / "shell.json").write_text('{"theme": "corrupted"}\n')

        # 3. RUN RESTORE
        engine = RestoreEngine(paths=self.paths, runner=self.runner)
        restore_res = engine.execute(
            backup_dir=self.backup_dir,
            auto_confirm=True,
            skip_service_reload=True,
        )
        self.assertTrue(restore_res.success)
        self.assertFalse(restore_res.rolled_back)

        # Verify that original backed up content was restored
        self.assertIn("SUPER", (self.hypr_dir / "bindings.lua").read_text())
        self.assertIn('"theme": "dark"', (self.omarchy_dir / "shell.json").read_text())

        # Verify pre-restore snapshot was generated
        latest_snap = get_latest_snapshot(self.paths)
        self.assertIsNotNone(latest_snap)

        # 4. TEST ROLLBACK
        # The pre-restore snapshot should contain the modified/corrupted state
        ok, name, files = rollback_latest_snapshot(self.paths)
        self.assertTrue(ok)
        self.assertIn("Corrupted", (self.hypr_dir / "bindings.lua").read_text())


if __name__ == "__main__":
    unittest.main()
