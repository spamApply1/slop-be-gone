from __future__ import annotations

import json
import sys
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


if __name__ == "__main__":
    unittest.main()
