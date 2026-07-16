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
from sbg.manifest import resolve_manifest_path, write_manifest


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
        if path == "/api/violation-context":
            self._serve_violation_context()
            return
        if path == "/api/pattern-preview":
            self._serve_pattern_preview()
            return
        if path == "/api/pattern-save":
            self._serve_pattern_save()
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
        payload = self._read_json_payload()
        repo_root = self._resolve_repo_root(payload.get("repo_root"))
        manifest_target = self._resolve_manifest_path(payload.get("manifest_path"), repo_root=repo_root)

        engine = RuleEngine.from_manifest_path(manifest_target)
        violations = engine.scan_repository(repo_root)

        summary = {
            "total": len(violations),
            "by_rule": dict(sorted(Counter(violation.rule_id for violation in violations).items())),
        }
        response_payload = {
            "repo_root": str(repo_root),
            "manifest_path": str(manifest_target),
            "violation_count": len(violations),
            "summary": summary,
            "violations": [violation.as_dict() for violation in violations],
        }
        self._send_json(response_payload)

    def _serve_violation_context(self) -> None:
        payload = self._read_json_payload()
        repo_root = self._resolve_repo_root(payload.get("repo_root"))
        violation = payload.get("violation") or {}
        if not isinstance(violation, dict):
            self._send_json({"error": "violation payload must be an object"})
            return

        relative_path = violation.get("path")
        if not relative_path:
            self._send_json({"path": None, "line": None, "lines": []})
            return

        file_path = self._resolve_file_path(repo_root, relative_path)
        if not file_path.exists() or not file_path.is_file():
            self._send_json({"path": relative_path, "line": None, "lines": []})
            return

        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        line_number = violation.get("line")
        if line_number is not None:
            try:
                line_number = int(line_number)
            except (TypeError, ValueError):
                line_number = None

        if line_number is None or line_number < 1:
            start_index = 0
            end_index = min(len(lines), 8)
        else:
            start_index = max(0, line_number - 3)
            end_index = min(len(lines), line_number + 2)

        context_lines = [
            {"line": index + 1, "text": lines[index] if index < len(lines) else ""}
            for index in range(start_index, end_index)
        ]
        response_payload = {
            "path": relative_path,
            "line": line_number,
            "line_count": len(lines),
            "lines": context_lines,
            "violation": violation,
        }
        self._send_json(response_payload)

    def _serve_pattern_preview(self) -> None:
        payload = self._read_json_payload()
        repo_root = self._resolve_repo_root(payload.get("repo_root"))
        base_manifest_path = self._resolve_manifest_path(payload.get("manifest_path"), repo_root=repo_root)
        rule = self._build_rule_payload(payload)
        manifest = self._load_manifest(base_manifest_path)
        preview_manifest = {"rules": [*manifest.get("rules", []), rule]}
        engine = RuleEngine(preview_manifest)
        violations = engine.scan_repository(repo_root)
        pattern_violations = [violation for violation in violations if violation.rule_id == rule["id"]]
        response_payload = {
            "repo_root": str(repo_root),
            "manifest_path": str(base_manifest_path),
            "rule": rule,
            "preview_violation_count": len(pattern_violations),
            "violations": [violation.as_dict() for violation in pattern_violations],
        }
        self._send_json(response_payload)

    def _serve_pattern_save(self) -> None:
        payload = self._read_json_payload()
        repo_root = self._resolve_repo_root(payload.get("repo_root"))
        base_manifest_path = self._resolve_manifest_path(payload.get("manifest_path"), repo_root=repo_root)
        target_manifest_path = (
            payload.get("output_manifest_path")
            or payload.get("target_manifest_path")
            or payload.get("manifest_path")
        )
        target_manifest_path = self._resolve_manifest_path(target_manifest_path, repo_root=repo_root)
        rule = self._build_rule_payload(payload)
        manifest = self._load_manifest(base_manifest_path)
        rules = list(manifest.get("rules", []))
        if not any(existing.get("id") == rule["id"] for existing in rules):
            rules.append(rule)
        else:
            rules = [existing if existing.get("id") != rule["id"] else rule for existing in rules]
        manifest["rules"] = rules
        manifest_path = write_manifest(target_manifest_path, manifest, repo_root=repo_root)
        preview_manifest = {"rules": rules}
        engine = RuleEngine(preview_manifest)
        violations = engine.scan_repository(repo_root)
        pattern_violations = [violation for violation in violations if violation.rule_id == rule["id"]]
        response_payload = {
            "repo_root": str(repo_root),
            "manifest_path": str(manifest_path),
            "rule": rule,
            "saved_rule_count": len(rules),
            "preview_violation_count": len(pattern_violations),
            "violations": [violation.as_dict() for violation in pattern_violations],
            "manifest": manifest,
        }
        self._send_json(response_payload)

    def _build_rule_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        pattern_name = str(payload.get("pattern_name") or "").strip()
        if not pattern_name:
            raise ValueError("pattern_name is required")
        pattern_text = str(payload.get("pattern_text") or "").strip()
        if not pattern_text:
            raise ValueError("pattern_text is required")
        rule_kind = str(payload.get("rule_kind") or "placeholder-comments")
        pattern_type = str(payload.get("pattern_type") or payload.get("match_mode") or "plain_text")
        rule: dict[str, Any] = {
            "id": pattern_name,
            "type": rule_kind,
            "enabled": True,
            "pattern": pattern_text,
            "match_mode": pattern_type,
        }
        if rule_kind == "marker-spam":
            rule["threshold"] = 1
        if rule_kind == "long-lines":
            rule["max_length"] = int(payload.get("max_length") or 120)
        if rule_kind in {"placeholder-comments", "marker-spam"}:
            rule["patterns"] = [pattern_text]
        return rule

    def _load_manifest(self, path: Path) -> dict[str, Any]:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {"rules": []}

    def _resolve_repo_root(self, repo_root: str | Path | None) -> Path:
        if repo_root:
            resolved_repo = Path(repo_root).expanduser()
            if not resolved_repo.is_absolute():
                resolved_repo = (Path.cwd() / resolved_repo).resolve()
            return resolved_repo.resolve()
        return resolve_default_repo_root()

    def _resolve_manifest_path(self, manifest_path: str | Path | None, repo_root: str | Path | None = None) -> Path:
        if manifest_path:
            return resolve_manifest_path(manifest_path, repo_root=repo_root)
        return resolve_manifest_path(None, repo_root=repo_root)

    def _resolve_file_path(self, repo_root: Path, relative_path: str | Path) -> Path:
        candidate = Path(relative_path).expanduser()
        if not candidate.is_absolute():
            candidate = (repo_root / candidate).resolve()
        return candidate.resolve()

    def _read_json_payload(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            self._send_json({"error": f"invalid JSON: {exc.msg}"})
            raise ValueError("invalid JSON") from exc
        if not isinstance(payload, dict):
            self._send_json({"error": "request body must be a JSON object"})
            raise ValueError("request body must be a JSON object")
        return payload

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
