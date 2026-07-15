from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from sbg.cli import main


class CLITests(unittest.TestCase):
    def test_cli_prints_violations_and_returns_nonzero(self) -> None:
        fixture_repo = ROOT / "tests" / "fixtures" / "fixture_repo"
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = main(["check", str(fixture_repo)])

        self.assertEqual(exit_code, 1)
        output = stdout.getvalue()
        self.assertIn("placeholder-comments", output)
        self.assertIn("empty/blank.txt", output)
        self.assertNotIn("No violations found.", output)

    def test_cli_can_emit_json(self) -> None:
        fixture_repo = ROOT / "tests" / "fixtures" / "fixture_repo"
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = main(["check", str(fixture_repo), "--json"])

        self.assertEqual(exit_code, 1)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload)
        rule_ids = {entry["rule_id"] for entry in payload}
        self.assertIn("placeholder-comments", rule_ids)


if __name__ == "__main__":
    unittest.main()
