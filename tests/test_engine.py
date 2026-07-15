from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from sbg.engine import RuleEngine
from sbg.manifest import load_manifest


class RuleEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture_repo = ROOT / "tests" / "fixtures" / "fixture_repo"

    def test_fixture_repo_reports_expected_violations(self) -> None:
        engine = RuleEngine(load_manifest(ROOT / "sbg_manifest.json"))
        violations = engine.scan_repository(self.fixture_repo)

        violation_ids = {violation.rule_id for violation in violations}
        self.assertIn("placeholder-comments", violation_ids)
        self.assertIn("marker-spam", violation_ids)
        self.assertIn("empty-files", violation_ids)
        self.assertIn("long-lines", violation_ids)

        empty_file = [violation for violation in violations if violation.path == "empty/blank.txt"]
        self.assertTrue(empty_file)

    def test_file_size_rule_honors_manifest_threshold(self) -> None:
        manifest = {
            "rules": [
                {
                    "id": "file-size",
                    "type": "file-size",
                    "enabled": True,
                    "max_bytes": 256,
                }
            ]
        }
        engine = RuleEngine(manifest)
        violations = engine.scan_repository(self.fixture_repo)

        file_size_violations = [violation for violation in violations if violation.rule_id == "file-size"]
        self.assertTrue(file_size_violations)
        self.assertIn("other/oversized.txt", {violation.path for violation in file_size_violations})


if __name__ == "__main__":
    unittest.main()
