from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from sbg.manifest import resolve_concepts_path, resolve_manifest_path

BUNDLED_DATA = ROOT / "src" / "sbg" / "data"


class PackagingDriftTests(unittest.TestCase):
    """The bundled package data must stay byte-identical to the canonical sources.

    These copies exist so that a non-editable ``pip install`` still ships the
    default manifest, concepts, and rule guide. This test is the enforced guard
    that keeps the shipped copies from drifting away from the repository source.
    """

    def test_bundled_manifest_matches_repo_manifest(self) -> None:
        source = (ROOT / "sbg_manifest.json").read_text(encoding="utf-8")
        bundled = (BUNDLED_DATA / "default_manifest.json").read_text(encoding="utf-8")
        self.assertEqual(source, bundled)

    def test_bundled_concepts_match_repo_concepts(self) -> None:
        source = (ROOT / "sbg_concepts.json").read_text(encoding="utf-8")
        bundled = (BUNDLED_DATA / "concepts.json").read_text(encoding="utf-8")
        self.assertEqual(source, bundled)

    def test_bundled_docs_match_repo_docs(self) -> None:
        source = (ROOT / "docs" / "hygiene-rules.md").read_text(encoding="utf-8")
        bundled = (BUNDLED_DATA / "hygiene-rules.md").read_text(encoding="utf-8")
        self.assertEqual(source, bundled)

    def test_default_resolution_prefers_checkout_but_bundled_exists(self) -> None:
        # In the checkout, the default resolves to the repo-root files.
        self.assertEqual(resolve_manifest_path(None), (ROOT / "sbg_manifest.json").resolve())
        self.assertEqual(resolve_concepts_path(None), (ROOT / "sbg_concepts.json").resolve())
        # And the bundled fallbacks must exist for installed (non-editable) use.
        self.assertTrue((BUNDLED_DATA / "default_manifest.json").is_file())
        self.assertTrue((BUNDLED_DATA / "concepts.json").is_file())


if __name__ == "__main__":
    unittest.main()
