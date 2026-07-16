from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
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

    def test_check_staged_scans_only_staged_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)

            (repo_path / "tracked.txt").write_text("hello\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "initial"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            )

            staged_path = repo_path / "staged.py"
            staged_path.write_text("// placeholder content\n", encoding="utf-8")
            subprocess.run(["git", "add", "staged.py"], cwd=repo_path, check=True)

            unstaged_path = repo_path / "unstaged.py"
            unstaged_path.write_text("// placeholder content\n", encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["check", str(repo_path), "--staged"])

            self.assertEqual(exit_code, 1)
            output = stdout.getvalue()
            self.assertIn("staged.py", output)
            self.assertNotIn("unstaged.py", output)

    def test_install_hooks_creates_executable_pre_commit_hook(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True, text=True)

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["install-hooks", str(repo_path)])

            self.assertEqual(exit_code, 0)
            hook_path = repo_path / ".git" / "hooks" / "pre-commit"
            self.assertTrue(hook_path.exists())
            self.assertTrue(os.access(hook_path, os.X_OK))
            contents = hook_path.read_text(encoding="utf-8")
            self.assertIn("sbg.cli check --staged", contents)
            self.assertIn(sys.executable, contents)

    def test_install_hooks_can_use_custom_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True, text=True)
            manifest_path = repo_path / "custom_manifest.json"
            manifest_path.write_text(
                '{"rules": [{"id": "empty-files", "type": "empty-files", "enabled": true}]}',
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    ["install-hooks", str(repo_path), "--manifest", str(manifest_path)]
                )

            self.assertEqual(exit_code, 0)
            hook_path = repo_path / ".git" / "hooks" / "pre-commit"
            contents = hook_path.read_text(encoding="utf-8")
            self.assertIn("--manifest", contents)
            self.assertIn(str(manifest_path), contents)

    def test_check_prefers_repo_local_manifest_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            # A repo-local manifest that only enables empty-files.
            (repo_path / "sbg_manifest.json").write_text(
                '{"rules": [{"id": "empty-files", "type": "empty-files", "enabled": true}]}',
                encoding="utf-8",
            )
            (repo_path / "blank.txt").write_text("", encoding="utf-8")
            # A scaffold marker that the bundled default would flag, but this repo's manifest ignores.
            (repo_path / "marked.py").write_text("# placeholder\n", encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["check", str(repo_path), "--json"])

            self.assertEqual(exit_code, 1)
            payload = json.loads(stdout.getvalue())
            rule_ids = {entry["rule_id"] for entry in payload}
            self.assertEqual(rule_ids, {"empty-files"})

    def test_report_groups_by_rule_with_suggestions(self) -> None:
        fixture_repo = ROOT / "tests" / "fixtures" / "fixture_repo"
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = main(["report", str(fixture_repo)])

        self.assertEqual(exit_code, 1)
        output = stdout.getvalue()
        self.assertIn("Hygiene report", output)
        self.assertIn("placeholder-comments", output)
        self.assertIn("Suggestion:", output)
        self.assertIn("Remove placeholder comments", output)

    def test_validate_accepts_bundled_manifest(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["validate", str(ROOT)])
        self.assertEqual(exit_code, 0)
        self.assertIn("is valid", stdout.getvalue())

    def test_validate_rejects_malformed_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            (repo_path / "sbg_manifest.json").write_text(
                '{"rules": [{"id": "broken"}]}', encoding="utf-8"
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["validate", str(repo_path)])
            self.assertEqual(exit_code, 1)
            self.assertIn("problem", stdout.getvalue())


    def test_init_scaffolds_manifest_and_docs_that_pass_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["init", str(repo_path)])
            self.assertEqual(exit_code, 0)

            manifest_path = repo_path / "sbg_manifest.json"
            docs_path = repo_path / "docs" / "hygiene-rules.md"
            self.assertTrue(manifest_path.exists())
            self.assertTrue(docs_path.exists())

            # The scaffolded manifest must validate and the scaffolded repo must be clean.
            validate_out = io.StringIO()
            with contextlib.redirect_stdout(validate_out):
                validate_code = main(["validate", str(repo_path)])
            self.assertEqual(validate_code, 0)

            check_out = io.StringIO()
            with contextlib.redirect_stdout(check_out):
                check_code = main(["check", str(repo_path)])
            self.assertEqual(check_code, 0)

    def test_init_refuses_to_overwrite_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            (repo_path / "sbg_manifest.json").write_text('{"rules": []}', encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main(["init", str(repo_path)])
            self.assertEqual(exit_code, 1)
            self.assertIn("Refusing to overwrite", stderr.getvalue())


    def test_check_warning_severity_does_not_block_unless_strict(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            (repo_path / "sbg_manifest.json").write_text(
                '{"rules": [{"id": "empty-files", "type": "empty-files", "enabled": true, "severity": "warning"}]}',
                encoding="utf-8",
            )
            (repo_path / "blank.txt").write_text("", encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["check", str(repo_path)])
            self.assertEqual(exit_code, 0)
            self.assertIn("(warning)", stdout.getvalue())
            self.assertIn("warning(s)", stdout.getvalue())

            strict_out = io.StringIO()
            with contextlib.redirect_stdout(strict_out):
                strict_code = main(["check", str(repo_path), "--strict"])
            self.assertEqual(strict_code, 1)


if __name__ == "__main__":
    unittest.main()
