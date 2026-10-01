"""Tests for git repository management and audited staging."""

import tempfile
import unittest
from pathlib import Path

from omarchy_backup.git.commit import commit_manifest_backup
from omarchy_backup.git.repository import GitRepo
from omarchy_backup.manifest import Manifest, ManifestEntry


class TestGitRepo(unittest.TestCase):
    def test_git_init_and_audited_commit(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_path = Path(tmp_dir) / "repo"
            repo = GitRepo(repo_path)

            self.assertFalse(repo.is_git_repo())
            self.assertTrue(repo.init(branch="main"))
            self.assertTrue(repo.is_git_repo())

            # Configure git user identity for testing environment
            repo.runner.run(["git", "config", "user.name", "Test User"], cwd=repo_path)
            repo.runner.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path)

            # Create an audited file and an untracked/unrelated file
            audited_file = repo_path / "hypr" / "bindings.lua"
            audited_file.parent.mkdir(parents=True)
            audited_file.write_text("hl.bind('SUPER', 'Q')\n")

            untracked_file = repo_path / "random_secret.tmp"
            untracked_file.write_text("random secret text\n")

            manifest = Manifest(
                omarchy_version="4.0.4",
                hyprland_version="0.56.2",
                entries=[
                    ManifestEntry(
                        source="~/.config/hypr/bindings.lua",
                        destination="hypr/bindings.lua",
                        entry_type="file",
                    )
                ],
            )
            manifest.save(repo_path / "manifest.json")

            # Commit
            ok, msg = commit_manifest_backup(repo, manifest, custom_message="Initial test backup")
            self.assertTrue(ok)

            # Verify that audited_file was committed, but untracked_file was NOT staged or committed!
            status_res = repo.runner.run(["git", "status", "--porcelain"], cwd=repo_path)
            self.assertIn("?? random_secret.tmp", status_res.stdout)
            self.assertNotIn("bindings.lua", status_res.stdout)

            # Check history
            history = repo.get_history(limit=5)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["message"], "Initial test backup")


if __name__ == "__main__":
    unittest.main()
