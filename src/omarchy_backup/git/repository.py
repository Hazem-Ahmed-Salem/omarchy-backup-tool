"""Git repository wrapper ensuring safe, audited staging and operations."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from omarchy_backup.runner import CommandRunner, default_runner

logger = logging.getLogger(__name__)


class GitRepo:
    """Manages git actions exclusively inside the backup repository directory."""

    def __init__(self, repo_dir: Path | str, runner: CommandRunner | None = None) -> None:
        self.repo_dir = Path(repo_dir).resolve()
        self.runner = runner or default_runner

    def is_git_repo(self) -> bool:
        """Check if repository directory has an initialized .git folder."""
        return (self.repo_dir / ".git").is_dir()

    def init(self, branch: str = "main") -> bool:
        """Initialize a new git repository if not already initialized."""
        if self.is_git_repo():
            return True

        self.repo_dir.mkdir(parents=True, exist_ok=True)
        res = self.runner.run(["git", "init", "-b", branch], cwd=self.repo_dir)
        if not res.success:
            # Fallback for older git that doesn't support -b
            res = self.runner.run(["git", "init"], cwd=self.repo_dir)
            if res.success:
                self.runner.run(["git", "checkout", "-B", branch], cwd=self.repo_dir)
        return res.success

    def stage_files(self, relative_files: list[str]) -> tuple[bool, list[str]]:
        """Stage ONLY the explicitly listed files. NEVER use 'git add .'!

        Returns (success, staged_files).
        """
        if not self.is_git_repo():
            return False, []

        staged: list[str] = []
        # Stage in batches to avoid command line limits
        batch_size = 50
        for i in range(0, len(relative_files), batch_size):
            batch = relative_files[i : i + batch_size]
            existing_batch = [f for f in batch if (self.repo_dir / f).exists()]
            if not existing_batch:
                continue
            cmd = ["git", "add", "-f", "--"] + existing_batch
            res = self.runner.run(cmd, cwd=self.repo_dir)
            if res.success:
                staged.extend(existing_batch)
            else:
                logger.warning("Git stage failed for batch: %s", res.stderr)
                return False, staged

        return True, staged

    def has_uncommitted_changes(self) -> bool:
        """Check if there are staged or unstaged modifications in git."""
        if not self.is_git_repo():
            return False
        res = self.runner.run(["git", "status", "--porcelain"], cwd=self.repo_dir)
        return bool(res.stdout.strip())

    def get_diff(self, staged: bool = False) -> str:
        """Return git diff output."""
        if not self.is_git_repo():
            return ""
        cmd = ["git", "diff", "--cached"] if staged else ["git", "diff"]
        res = self.runner.run(cmd, cwd=self.repo_dir)
        return res.stdout

    def get_history(self, limit: int = 15) -> list[dict[str, str]]:
        """Return recent commit log."""
        if not self.is_git_repo():
            return []
        format_str = "%H%x00%an%x00%ad%x00%s"
        res = self.runner.run(
            ["git", "log", f"-n{limit}", f"--format={format_str}", "--date=short"],
            cwd=self.repo_dir,
        )
        if not res.success:
            return []

        commits: list[dict[str, str]] = []
        for line in res.stdout.splitlines():
            parts = line.split("\x00")
            if len(parts) >= 4:
                commits.append({
                    "hash": parts[0],
                    "short_hash": parts[0][:8],
                    "author": parts[1],
                    "date": parts[2],
                    "message": parts[3],
                })
        return commits
