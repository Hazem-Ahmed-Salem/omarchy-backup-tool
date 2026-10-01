"""Tests for manifest creation, serialization, and retrieval."""

import tempfile
import unittest
from pathlib import Path

from omarchy_backup.manifest import Manifest, ManifestEntry


class TestManifest(unittest.TestCase):
    def test_manifest_roundtrip(self):
        entry = ManifestEntry(
            source="~/.config/hypr/bindings.lua",
            destination="hypr/bindings.lua",
            entry_type="file",
            scope="portable",
            sha256="abcdef1234567890",
            size=1024,
            mode="0644",
        )
        manifest = Manifest(
            omarchy_version="4.0.4",
            hyprland_version="0.56.2",
            entries=[entry],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            manifest_path = Path(tmp_dir) / "manifest.json"
            manifest.save(manifest_path)

            loaded = Manifest.load(manifest_path)
            self.assertEqual(loaded.format_version, 1)
            self.assertEqual(loaded.omarchy_version, "4.0.4")
            self.assertEqual(loaded.hyprland_version, "0.56.2")
            self.assertEqual(len(loaded.entries), 1)

            loaded_entry = loaded.get_entry_by_dest("hypr/bindings.lua")
            self.assertIsNotNone(loaded_entry)
            self.assertEqual(loaded_entry.sha256, "abcdef1234567890")
            self.assertEqual(loaded_entry.scope, "portable")


if __name__ == "__main__":
    unittest.main()
