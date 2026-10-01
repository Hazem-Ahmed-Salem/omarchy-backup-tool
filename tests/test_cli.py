"""Tests for CLI parsing and subcommands."""

import unittest

from omarchy_backup.cli import build_parser


class TestCLIParser(unittest.TestCase):
    def test_parser_subcommands(self):
        parser = build_parser()

        # init
        args_init = parser.parse_args(["init", "--dir", "~/test-backup", "--remote", "git@github.com:user/repo.git"])
        self.assertEqual(args_init.command, "init")
        self.assertEqual(args_init.dir, "~/test-backup")
        self.assertEqual(args_init.remote, "git@github.com:user/repo.git")

        # scan
        args_scan = parser.parse_args(["scan"])
        self.assertEqual(args_scan.command, "scan")

        # backup
        args_backup = parser.parse_args(["backup", "--push", "--include-scripts", "-m", "my commit"])
        self.assertEqual(args_backup.command, "backup")
        self.assertTrue(args_backup.push)
        self.assertTrue(args_backup.include_scripts)
        self.assertEqual(args_backup.message, "my commit")

        # restore
        args_restore = parser.parse_args(["restore", "--dry-run", "--yes", "--include-local"])
        self.assertEqual(args_restore.command, "restore")
        self.assertTrue(args_restore.dry_run)
        self.assertTrue(args_restore.yes)
        self.assertTrue(args_restore.include_local)

        # rollback
        args_rb = parser.parse_args(["rollback", "--yes"])
        self.assertEqual(args_rb.command, "rollback")
        self.assertTrue(args_rb.yes)


if __name__ == "__main__":
    unittest.main()
