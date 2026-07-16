from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = Path(__file__).resolve().parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def resolve_default_repo_root() -> Path:
    configured_repo = os.environ.get("SBG_DASHBOARD_REPO_ROOT")
    if configured_repo:
        candidate = Path(configured_repo).expanduser()
        if not candidate.is_absolute():
            candidate = (Path.cwd() / candidate).resolve()
        return candidate

    current_dir = Path.cwd().resolve()
    for candidate in [current_dir, *current_dir.parents]:
        git_marker = candidate / ".git"
        if git_marker.exists():
            return candidate

    return REPO_ROOT.resolve()

from sbg.engine import RuleEngine
from sbg.manifest import resolve_manifest_path


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self._handle_request()

    def do_POST(self) -> None:  # noqa: N802
        self._handle_request()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_response(status=204, payload=None, content_type="text/plain; charset=utf-8")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _handle_request(self) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == "/api/manifest":
            self._serve_manifest(parsed.query)
            return
        if path == "/api/scan":
            self._scan_repository()
            return
        if path in {"/", "/index.html"}:
            self._serve_static_asset("index.html", "text/html; charset=utf-8")
            return
        if path == "/styles.css":
            self._serve_static_asset("styles.css", "text/css; charset=utf-8")
            return
        if path == "/app.js":
            self._serve_static_asset("app.js", "application/javascript; charset=utf-8")
            return
        self._serve_not_found()

    def _serve_manifest(self, query_string: str) -> None:
        params = parse_qs(query_string)
        manifest_path_value = params.get("manifest", [None])[0]
        if manifest_path_value:
            manifest_path = resolve_manifest_path(manifest_path_value)
        else:
            manifest_path = resolve_manifest_path(None)
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload = {
            "manifest_path": str(manifest_path),
            "manifest": manifest_data,
            "default_repo_root": str(resolve_default_repo_root()),
        }
        self._send_json(payload)

    def _scan_repository(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            payload: dict[str, Any] = {}
        else:
            body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(body)

        repo_root = payload.get("repo_root")
        manifest_path = payload.get("manifest_path") or None

        if repo_root:
            resolved_repo = Path(repo_root).expanduser()
            if not resolved_repo.is_absolute():
                resolved_repo = (Path.cwd() / resolved_repo).resolve()
        else:
            resolved_repo = resolve_default_repo_root()

        manifest_target = None
        if manifest_path:
            manifest_target = resolve_manifest_path(manifest_path)
        else:
            manifest_target = resolve_manifest_path(None)

        engine = RuleEngine.from_manifest_path(manifest_target)
        violations = engine.scan_repository(resolved_repo)

        summary = {
            "total": len(violations),
            "by_rule": dict(sorted(Counter(violation.rule_id for violation in violations).items())),
        }
        response_payload = {
            "repo_root": str(resolved_repo),
            "manifest_path": str(manifest_target),
            "violation_count": len(violations),
            "summary": summary,
            "violations": [violation.as_dict() for violation in violations],
        }
        self._send_json(response_payload)

    def _serve_static_asset(self, asset_name: str, content_type: str) -> None:
        asset_path = self._resolve_static_path(asset_name)
        if asset_path is None:
            self._serve_not_found()
            return
        self._send_response(status=200, payload=asset_path.read_bytes(), content_type=content_type)

    def _resolve_static_path(self, asset_name: str) -> Path | None:
        candidate = (WEB_ROOT / asset_name).resolve()
        if not candidate.exists() or not candidate.is_file():
            return None
        try:
            candidate.relative_to(WEB_ROOT)
        except ValueError:
            return None
        return candidate

    def _send_json(self, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._send_response(status=200, payload=body, content_type="application/json; charset=utf-8")

    def _send_response(self, status: int, payload: bytes | None, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(0 if payload is None else len(payload)))
        self.end_headers()
        if payload is not None:
            self.wfile.write(payload)

    def _serve_not_found(self) -> None:
        body = b"Not Found"
        self._send_response(status=404, payload=body, content_type="text/plain; charset=utf-8")


def create_server(host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), DashboardHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the SBG dashboard locally")
    parser.add_argument("--host", default=os.environ.get("SBG_WEB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SBG_WEB_PORT", "8000")))
    args = parser.parse_args()
    server = create_server(args.host, args.port)
    print(f"Serving SBG dashboard at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
