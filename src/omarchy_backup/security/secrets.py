"""Content scanning for accidental secrets, private keys, and API tokens."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Common regexes for credentials and secret patterns
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Private Key Block", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    ("GitHub Personal Access Token", re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}")),
    ("GitHub Fine-Grained Token", re.compile(r"github_pat_[A-Za-z0-9_]{82}")),
    ("AWS Access Key ID", re.compile(r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}")),
    ("Slack API Token", re.compile(r"xox[baprs]-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*")),
    ("OpenAI / Anthropic API Key", re.compile(r"sk-[a-zA-Z0-9_-]{20,}")),
    ("Generic Bearer Token", re.compile(r"(?i)bearer\s+[a-zA-Z0-9_.\-]{30,}")),
    ("Explicit Password Assignment", re.compile(r"""(?i)(?:password|passwd|api_key|secret_key|auth_token)\s*[:=]\s*["'][^"'\s]{6,}["']""")),
]


@dataclass
class SecretScanResult:
    """Outcome of scanning a file or text content for secrets."""
    has_secret: bool
    reason: str = ""
    preview: str = ""


def scan_text_for_secrets(text: str) -> SecretScanResult:
    """Scan string content against secret patterns."""
    for name, pattern in SECRET_PATTERNS:
        match = pattern.search(text)
        if match:
            raw_match = match.group(0)
            # Redact the actual secret for display safety
            redacted = raw_match[:4] + "..." + raw_match[-4:] if len(raw_match) > 8 else "***"
            return SecretScanResult(
                has_secret=True,
                reason=f"Detected {name}",
                preview=redacted,
            )
    return SecretScanResult(has_secret=False)


def scan_file_for_secrets(path: Path | str, max_size_bytes: int = 1_048_576) -> SecretScanResult:
    """Scan a file for secrets.

    Returns SecretScanResult. If file is binary or too large, it is handled safely.
    """
    p = Path(path)
    if not p.is_file():
        return SecretScanResult(has_secret=False)

    try:
        size = p.stat().st_size
        if size > max_size_bytes:
            # Files larger than 1MB are typically binary or media; skip content inspection
            return SecretScanResult(has_secret=False)

        # Read sample to detect binary content
        with open(p, "rb") as f:
            chunk = f.read(4096)
            if b"\x00" in chunk:
                # Binary file, don't scan as text
                return SecretScanResult(has_secret=False)

        # Read as text
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        return scan_text_for_secrets(content)
    except Exception as exc:
        logger.debug("Failed to read %s for secret scanning: %s", p, exc)
        return SecretScanResult(has_secret=False)
