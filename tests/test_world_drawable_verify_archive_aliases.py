"""Source-archive identity checks using synthetic reports and placeholder files only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import world_drawable_verify as verifier
import world_names


class ArchiveAliasTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.archive = self.root / "source.bin"
        self.archive.write_bytes(b"synthetic file identity only")

    def reports(self, predicted_source, exported_source):
        name = "synthetic_drawable"
        candidate = {"archetype": format(world_names.joaat(name), "x"),
                     "key": format(world_names.hash64(name), "x"), "offsets": [16],
                     "status": "candidate", "placements": 4}
        predictions = self.root / "predictions.json"
        predictions.write_text(json.dumps({"archive": str(predicted_source), "candidates": [candidate]}),
                               encoding="utf-8", newline="\n")
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps({"src": str(exported_source), "Scan": {},
                                        "Items": [{"Name": name, "Offset": 16}]}),
                            encoding="utf-8", newline="\n")
        return predictions, manifest

    def hard_link(self):
        alias = self.root / "archive-alias.bin"
        try:
            os.link(self.archive, alias)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"hard links unavailable: {error}")
        return alias

    def assert_confirmed(self, result):
        self.assertEqual(result["identities"], {"confirmed": 1})
        self.assertEqual(result["placements"], {"confirmed": 4})
        self.assertEqual(result["rows"][0]["exact_observations"], 1)

    def test_hard_link_to_source_archive_is_accepted(self):
        predictions, manifest = self.reports(self.archive, self.hard_link())
        self.assert_confirmed(verifier.verify(predictions, [manifest]))

    def test_symlink_to_source_archive_is_accepted(self):
        alias = self.root / "archive-alias.bin"
        try:
            alias.symlink_to(self.archive)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlinks unavailable: {error}")
        predictions, manifest = self.reports(self.archive, alias)
        self.assert_confirmed(verifier.verify(predictions, [manifest]))

    def test_cli_accepts_source_archive_alias(self):
        predictions, manifest = self.reports(self.archive, self.hard_link())
        result = subprocess.run(
            [sys.executable, "-I", str(ROOT / "tools" / "world_drawable_verify.py"),
             str(predictions), str(manifest)], capture_output=True, text=True, encoding="utf-8",
            errors="replace")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assert_confirmed(json.loads(result.stdout))

    def test_distinct_archive_with_identical_bytes_is_rejected(self):
        other = self.root / "different.bin"
        other.write_bytes(self.archive.read_bytes())
        self.assertFalse(os.path.samefile(self.archive, other))
        predictions, manifest = self.reports(self.archive, other)
        with self.assertRaisesRegex(ValueError, "different source archive"):
            verifier.verify(predictions, [manifest])

    def test_offline_reports_keep_normalized_path_matching(self):
        missing = self.root / "offline.bin"
        predictions, manifest = self.reports(missing, self.root / "unused" / ".." / missing.name)
        self.assertFalse(missing.exists())
        self.assert_confirmed(verifier.verify(predictions, [manifest]))

    def test_unavailable_metadata_does_not_accept_different_paths(self):
        predictions, manifest = self.reports(self.archive, self.hard_link())
        with mock.patch.object(verifier.os.path, "samefile", side_effect=PermissionError("metadata unavailable")):
            with self.assertRaisesRegex(ValueError, "different source archive"):
                verifier.verify(predictions, [manifest])


if __name__ == "__main__":
    unittest.main()
