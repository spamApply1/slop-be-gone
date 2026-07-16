from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from sbg.script_maps import build_script_map


class ScriptMapTests(unittest.TestCase):
    def test_build_script_map_returns_nodes_and_edges(self) -> None:
        payload = build_script_map(ROOT)
        self.assertIn("nodes", payload)
        self.assertIn("edges", payload)
        self.assertTrue(payload["nodes"])
        self.assertGreaterEqual(payload["summary"]["edge_count"], 1)


if __name__ == "__main__":
    unittest.main()
