from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib import request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from web.server import REPO_ROOT, create_server


class WebUITests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = create_server("127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _request(self, path: str, method: str = "GET", payload: dict | None = None) -> tuple[int, str]:
        url = f"http://127.0.0.1:{self.server.server_port}{path}"
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = request.Request(url, data=data, headers=headers, method=method)
        with request.urlopen(req, timeout=5) as response:
            body = response.read().decode("utf-8")
            return response.status, body

    def test_static_assets_and_manifest_endpoint(self) -> None:
        status, body = self._request("/")
        self.assertEqual(status, 200)
        self.assertIn("SBG Dashboard", body)

        status, css = self._request("/styles.css")
        self.assertEqual(status, 200)
        self.assertIn(":root", css)

        status, js = self._request("/app.js")
        self.assertEqual(status, 200)
        self.assertIn("resolveApiUrl", js)
        self.assertIn("fallbackOrigins", js)

        status, manifest_payload = self._request("/api/manifest")
        self.assertEqual(status, 200)
        payload = json.loads(manifest_payload)
        self.assertIn("manifest", payload)
        self.assertIn("rules", payload["manifest"])
        self.assertEqual(payload["default_repo_root"], str(Path.cwd().resolve()))

    def test_concepts_endpoint_returns_library(self) -> None:
        status, body = self._request("/api/concepts")
        self.assertEqual(status, 200)
        response = json.loads(body)
        self.assertIn("concepts", response)
        self.assertTrue(response["concepts"])
        self.assertIn("id", response["concepts"][0])

    def test_manifest_save_endpoint_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "custom_manifest.json"
            status, body = self._request(
                "/api/manifest-save",
                method="POST",
                payload={
                    "repo_root": str(ROOT),
                    "manifest_path": str(manifest_path),
                    "manifest": {
                        "rules": [
                            {
                                "id": "custom-commandment",
                                "type": "placeholder-comments",
                                "enabled": True,
                                "patterns": ["placeholder"],
                            }
                        ]
                    },
                },
            )
            self.assertEqual(status, 200)
            response = json.loads(body)
            self.assertEqual(response["manifest_path"], str(manifest_path))
            self.assertTrue(manifest_path.exists())
            saved_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_manifest["rules"][0]["id"], "custom-commandment")

    def test_rule_suggestion_endpoint_suggests_a_rule(self) -> None:
        status, body = self._request(
            "/api/rule-suggest",
            method="POST",
            payload={"prompt": "freeze any leftover TODO markers in code comments"},
        )
        self.assertEqual(status, 200)
        response = json.loads(body)
        self.assertIn("rule", response)
        self.assertEqual(response["rule"]["type"], "marker-spam")
        self.assertEqual(response["rule"]["pattern"], "TODO")

    def test_scan_endpoint_uses_rule_engine(self) -> None:
        fixture_repo = ROOT / "tests" / "fixtures" / "fixture_repo"
        status, body = self._request(
            "/api/scan",
            method="POST",
            payload={"repo_root": str(fixture_repo)},
        )
        self.assertEqual(status, 200)
        response = json.loads(body)
        self.assertGreater(response["violation_count"], 0)
        self.assertIn("placeholder-comments", response["summary"]["by_rule"])

    def test_violation_context_endpoint_returns_surrounding_lines(self) -> None:
        fixture_repo = ROOT / "tests" / "fixtures" / "fixture_repo"
        status, body = self._request(
            "/api/violation-context",
            method="POST",
            payload={
                "repo_root": str(fixture_repo),
                "violation": {
                    "path": "src/example.py",
                    "line": 1,
                    "rule_id": "placeholder-comments",
                    "message": "placeholder comment found",
                },
            },
        )
        self.assertEqual(status, 200)
        response = json.loads(body)
        self.assertEqual(response["path"], "src/example.py")
        self.assertEqual(response["line"], 1)
        self.assertTrue(response["lines"])
        self.assertIn("placeholder", response["lines"][0]["text"])

    def test_pattern_preview_and_save_workflow(self) -> None:
        fixture_repo = ROOT / "tests" / "fixtures" / "fixture_repo"
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "custom_manifest.json"
            status, body = self._request(
                "/api/pattern-preview",
                method="POST",
                payload={
                    "repo_root": str(fixture_repo),
                    "manifest_path": str(ROOT / "sbg_manifest.json"),
                    "pattern_name": "custom-placeholder",
                    "pattern_text": "placeholder",
                    "rule_kind": "placeholder-comments",
                    "pattern_type": "plain_text",
                },
            )
            self.assertEqual(status, 200)
            preview = json.loads(body)
            self.assertGreater(preview["preview_violation_count"], 0)
            self.assertEqual(preview["rule"]["id"], "custom-placeholder")

            status, body = self._request(
                "/api/pattern-save",
                method="POST",
                payload={
                    "repo_root": str(fixture_repo),
                    "manifest_path": str(ROOT / "sbg_manifest.json"),
                    "output_manifest_path": str(manifest_path),
                    "pattern_name": "custom-placeholder",
                    "pattern_text": "placeholder",
                    "rule_kind": "placeholder-comments",
                    "pattern_type": "plain_text",
                },
            )
            self.assertEqual(status, 200)
            saved = json.loads(body)
            self.assertEqual(saved["manifest_path"], str(manifest_path))
            self.assertTrue(manifest_path.exists())
            self.assertEqual(saved["manifest"]["rules"][-1]["id"], "custom-placeholder")


if __name__ == "__main__":
    unittest.main()
