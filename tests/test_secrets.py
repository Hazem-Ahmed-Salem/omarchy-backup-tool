"""Tests for secret detection and exclusion rules."""

import tempfile
import unittest
from pathlib import Path

from omarchy_backup.security.exclusions import is_excluded_path, should_exclude_path
from omarchy_backup.security.secrets import scan_file_for_secrets, scan_text_for_secrets


class TestSecretsAndExclusions(unittest.TestCase):
    def test_exclusion_patterns(self):
        # Excluded names
        self.assertTrue(is_excluded_path("id_rsa"))
        self.assertTrue(is_excluded_path("server.key"))
        self.assertTrue(is_excluded_path("cert.pem"))
        self.assertTrue(is_excluded_path(".env"))
        self.assertTrue(is_excluded_path(".env.production"))
        self.assertTrue(is_excluded_path("config.bak"))
        self.assertTrue(is_excluded_path("input.lua.bak.12345"))
        self.assertTrue(is_excluded_path(".git"))

        # Protected directories
        self.assertTrue(is_excluded_path("/home/user/.ssh/id_rsa"))
        self.assertTrue(is_excluded_path("/home/user/.gnupg/keys"))

        # Normal allowed files
        self.assertFalse(is_excluded_path("hyprland.lua"))
        self.assertFalse(is_excluded_path("bindings.lua"))
        self.assertFalse(is_excluded_path("shell.json"))

    def test_secret_content_scanning(self):
        # Private key
        priv_key = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAA\n-----END OPENSSH PRIVATE KEY-----"
        res = scan_text_for_secrets(priv_key)
        self.assertTrue(res.has_secret)
        self.assertIn("Private Key", res.reason)

        # GitHub token
        gh_token = "export GITHUB_TOKEN='ghp_0123456789abcdefghijklmnopqrstuvwxyz01'"
        res2 = scan_text_for_secrets(gh_token)
        self.assertTrue(res2.has_secret)
        self.assertIn("GitHub", res2.reason)

        # Safe config
        safe_conf = 'hl.bind("SUPER", "Q", hl.killactive)'
        res3 = scan_text_for_secrets(safe_conf)
        self.assertFalse(res3.has_secret)

    def test_scan_file(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
            tmp.write("AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'")
            tmp_path = Path(tmp.name)

        try:
            scan = scan_file_for_secrets(tmp_path)
            self.assertTrue(scan.has_secret)
            self.assertIn("AWS Access Key", scan.reason)
        finally:
            tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
