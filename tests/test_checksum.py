"""Tests for checksum calculation and verification."""

import tempfile
import unittest
from pathlib import Path

from omarchy_backup.backup.checksum import (
    calculate_bytes_sha256,
    calculate_sha256,
    get_file_mode_str,
    verify_file_sha256,
)


class TestChecksum(unittest.TestCase):
    def test_bytes_and_file_checksum(self):
        content = b"hello omarchy backup\n"
        expected_sha = calculate_bytes_sha256(content)

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            actual_sha = calculate_sha256(tmp_path)
            self.assertEqual(actual_sha, expected_sha)
            self.assertTrue(verify_file_sha256(tmp_path, expected_sha))
            self.assertFalse(verify_file_sha256(tmp_path, "invalid_sha"))
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_file_mode_str(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            tmp_path.chmod(0o644)
            self.assertEqual(get_file_mode_str(tmp_path), "0644")
            tmp_path.chmod(0o755)
            self.assertEqual(get_file_mode_str(tmp_path), "0755")
        finally:
            tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
