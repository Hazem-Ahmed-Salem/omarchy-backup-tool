"""Git remote management, push, and pull workflows."""

from __future__ import annotations

import logging

from omarchy_backup.git.repository import GitRepo

logger = logging.getLogger(__name__)


def get_remote_url(repo: GitRepo, remote_name: str = "origin") -> str:
    """Return the configured URL for remote_name, or empty string."""
    res = repo.runner.run(["git", "remote", "get-url", remote_name], cwd=repo.repo_dir)
    return res.stdout.strip() if res.success else ""


def configure_remote(repo: GitRepo, remote_url: str, remote_name: str = "origin") -> bool:
    """Set or update git remote URL."""
    existing = get_remote_url(repo, remote_name)
    if existing:
        res = repo.runner.run(["git", "remote", "set-url", remote_name, remote_url], cwd=repo.repo_dir)
    else:
        res = repo.runner.run(["git", "remote", "add", remote_name, remote_url], cwd=repo.repo_dir)
    return res.success


def push_backup(
    repo: GitRepo,
    branch: str = "main",
    remote_name: str = "origin",
) -> tuple[bool, str]:
    """Push local branch to remote repository."""
    if not repo.is_git_repo():
        return False, "Not a git repository"

    url = get_remote_url(repo, remote_name)
    if not url:
        return False, f"No remote named '{remote_name}' configured"

    res = repo.runner.run(["git", "push", "-u", remote_name, branch], cwd=repo.repo_dir, timeout=30.0)
    if res.success:
        return True, f"Successfully pushed to {url} ({branch})"
    return False, f"Git push failed: {res.stderr}"


def pull_backup(
    repo: GitRepo,
    branch: str = "main",
    remote_name: str = "origin",
) -> tuple[bool, str]:
    """Pull latest updates from remote repository."""
    if not repo.is_git_repo():
        return False, "Not a git repository"

    url = get_remote_url(repo, remote_name)
    if not url:
        return False, f"No remote named '{remote_name}' configured"

    res = repo.runner.run(["git", "pull", remote_name, branch], cwd=repo.repo_dir, timeout=30.0)
    if res.success:
        return True, f"Successfully pulled from {url} ({branch})"
    return False, f"Git pull failed: {res.stderr}"
