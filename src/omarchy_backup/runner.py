"""Subprocess execution abstraction with timeout, safety, and testing hooks."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Represents the outcome of an executed shell command."""
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


class CommandRunner:
    """Centralized command runner with timeout and mock support."""

    def __init__(self, default_timeout: float = 15.0) -> None:
        self.default_timeout = default_timeout

    def run(
        self,
        cmd: Sequence[str | Path],
        cwd: Path | str | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
        capture_output: bool = True,
        stdin_null: bool = True,
    ) -> CommandResult:
        """Run a command with non-blocking stdin to avoid hanging on prompts."""
        str_cmd = [str(c) for c in cmd]
        effective_timeout = timeout if timeout is not None else self.default_timeout

        # Ensure PATH and non-interactive safeguards
        merged_env = os.environ.copy()
        merged_env.setdefault("SUDO_ASKPASS", "/bin/false")
        if env:
            merged_env.update(env)

        # Non-interactive stdin by default
        stdin_val = subprocess.DEVNULL if stdin_null else None

        logger.debug("Executing command: %s (cwd=%s, timeout=%s)", str_cmd, cwd, effective_timeout)

        # Check if the executable exists
        executable = str_cmd[0]
        if not shutil.which(executable) and not Path(executable).exists():
            logger.debug("Command not found: %s", executable)
            return CommandResult(
                command=str_cmd,
                returncode=127,
                stdout="",
                stderr=f"Executable not found: {executable}",
            )

        try:
            proc = subprocess.run(
                str_cmd,
                cwd=str(cwd) if cwd else None,
                env=merged_env,
                stdin=stdin_val,
                stdout=subprocess.PIPE if capture_output else None,
                stderr=subprocess.PIPE if capture_output else None,
                text=True,
                timeout=effective_timeout,
                check=False,
            )
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            return CommandResult(
                command=str_cmd,
                returncode=proc.returncode,
                stdout=stdout,
                stderr=stderr,
            )
        except subprocess.TimeoutExpired as exc:
            logger.warning("Command timed out after %s seconds: %s", effective_timeout, str_cmd)
            stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            return CommandResult(
                command=str_cmd,
                returncode=-1,
                stdout=stdout,
                stderr=f"Command timed out after {effective_timeout}s: {stderr}",
            )
        except Exception as exc:
            logger.error("Command execution error: %s: %s", str_cmd, exc)
            return CommandResult(
                command=str_cmd,
                returncode=1,
                stdout="",
                stderr=str(exc),
            )

    def capture(
        self,
        cmd: Sequence[str | Path],
        cwd: Path | str | None = None,
        timeout: float | None = None,
    ) -> str:
        """Run command and return trimmed stdout on success, empty string on failure."""
        res = self.run(cmd, cwd=cwd, timeout=timeout, capture_output=True)
        return res.stdout.strip() if res.success else ""

    def check(
        self,
        cmd: Sequence[str | Path],
        cwd: Path | str | None = None,
        timeout: float | None = None,
    ) -> bool:
        """Run command and return True if exit code is 0."""
        return self.run(cmd, cwd=cwd, timeout=timeout).success


# Default shared runner
default_runner = CommandRunner()
