from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from sbg.engine import RuleEngine, validate_manifest
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

    def test_design_rules_flag_button_and_form_issues(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / "index.html").write_text(
                "<form><button>Save</button><input name=\"email\" /></form>",
                encoding="utf-8",
            )
            engine = RuleEngine(
                {
                    "rules": [
                        {"id": "button-actions", "type": "button-actions", "enabled": True},
                        {"id": "button-types", "type": "button-types", "enabled": True},
                        {"id": "form-labels", "type": "form-labels", "enabled": True},
                    ]
                }
            )
            violations = engine.scan_repository(repo_root)

            violation_ids = {violation.rule_id for violation in violations}
            self.assertIn("button-actions", violation_ids)
            self.assertIn("button-types", violation_ids)
            self.assertIn("form-labels", violation_ids)

    def test_asset_link_rule_flags_unwired_frontend_actions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / "web").mkdir(parents=True, exist_ok=True)
            (repo_root / "web" / "index.html").write_text(
                '<button type="button" data-action="save">Save</button>',
                encoding="utf-8",
            )
            (repo_root / "web" / "app.js").write_text("function noop() {}\n", encoding="utf-8")
            engine = RuleEngine({"rules": [{"id": "asset-links", "type": "asset-links", "enabled": True}]})
            violations = engine.scan_repository(repo_root)

            violation_ids = {violation.rule_id for violation in violations}
            self.assertIn("asset-links", violation_ids)
            self.assertTrue(any("save" in violation.message for violation in violations))

    def test_fully_defined_rules_flags_manifest_entries_without_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / "manifest.json").write_text(
                json.dumps(
                    {
                        "rules": [
                            {
                                "id": "placeholder-comments",
                                "type": "placeholder-comments",
                                "enabled": True,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            engine = RuleEngine(
                {"rules": [{"id": "fully-defined-rules", "type": "fully-defined-rules", "enabled": True}]}
            )
            violations = engine.scan_repository(repo_root)

            violation_ids = {violation.rule_id for violation in violations}
            self.assertIn("fully-defined-rules", violation_ids)
            self.assertTrue(any("placeholder-comments" in violation.message for violation in violations))

    def test_source_loadable_rule_flags_missing_or_unreadable_source_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / "manifest.json").write_text(
                json.dumps(
                    {
                        "rules": [
                            {
                                "id": "placeholder-comments",
                                "type": "placeholder-comments",
                                "enabled": True,
                                "description": "Freeze placeholder comments.",
                                "what": "Catch placeholders.",
                                "why": "Keep the repo honest.",
                                "source_refs": [{"path": "docs/rule.md"}],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            engine = RuleEngine({"rules": [{"id": "source-loadable", "type": "source-loadable", "enabled": True}]})
            violations = engine.scan_repository(repo_root)

            violation_ids = {violation.rule_id for violation in violations}
            self.assertIn("source-loadable", violation_ids)
            self.assertTrue(any("docs/rule.md" in violation.message for violation in violations))

    def test_dynamic_config_rule_flags_hard_coded_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            hard_coded_value = str(Path(temp_dir) / "project")
            (repo_root / "app.py").write_text(f"ROOT = '{hard_coded_value}'\n", encoding="utf-8")
            engine = RuleEngine({"rules": [{"id": "dynamic-config", "type": "dynamic-config", "enabled": True}]})
            violations = engine.scan_repository(repo_root)

            violation_ids = {violation.rule_id for violation in violations}
            self.assertIn("dynamic-config", violation_ids)
            self.assertTrue(any("absolute filesystem path" in violation.message for violation in violations))

    def test_composite_all_logic_scopes_and_unions_child_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / "src").mkdir()
            (repo_root / "src" / "clean.py").write_text("value = 1\n", encoding="utf-8")
            (repo_root / "src" / "messy.py").write_text(
                "# placeholder\n" + ("z" * 200) + "\n", encoding="utf-8"
            )
            # Outside the match scope; must be ignored even though it contains a scaffold marker.
            (repo_root / "notes.txt").write_text("# placeholder\n", encoding="utf-8")
            engine = RuleEngine(
                {
                    "rules": [
                        {
                            "id": "src-quality",
                            "type": "composite",
                            "enabled": True,
                            "logic": "all",
                            "match": ["src/**/*.py"],
                            "rules": [
                                {"type": "long-lines", "max_length": 120},
                                {"type": "placeholder-comments", "patterns": ["placeholder"]},
                            ],
                        }
                    ]
                }
            )
            violations = engine.scan_repository(repo_root)

            flagged_paths = {violation.path for violation in violations}
            self.assertEqual(flagged_paths, {"src/messy.py"})
            self.assertTrue(all(violation.rule_id == "src-quality" for violation in violations))
            messages = " ".join(violation.message for violation in violations)
            self.assertIn("[long-lines]", messages)
            self.assertIn("[placeholder-comments]", messages)

    def test_composite_any_logic_passes_when_one_child_is_satisfied(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            # Fails only long-lines -> satisfied by the scaffold-marker child -> passes "any".
            (repo_root / "long_only.py").write_text(("z" * 200) + "\n", encoding="utf-8")
            # Fails both children -> satisfies neither -> violates "any".
            (repo_root / "both_bad.py").write_text(
                "# placeholder\n" + ("z" * 200) + "\n", encoding="utf-8"
            )
            engine = RuleEngine(
                {
                    "rules": [
                        {
                            "id": "either-form",
                            "type": "composite",
                            "enabled": True,
                            "logic": "any",
                            "match": ["*.py"],
                            "rules": [
                                {"type": "long-lines", "max_length": 120},
                                {"type": "placeholder-comments", "patterns": ["placeholder"]},
                            ],
                        }
                    ]
                }
            )
            violations = engine.scan_repository(repo_root)

            flagged_paths = {violation.path for violation in violations}
            self.assertEqual(flagged_paths, {"both_bad.py"})
            self.assertTrue(any("failed all of" in violation.message for violation in violations))

    def test_merge_conflict_marker_rule_flags_unresolved_markers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            # Build markers dynamically so this test source never matches the rule itself.
            conflict = (
                ("<" * 7) + " HEAD\nkept = 1\n" + ("=" * 7) + "\nother = 2\n" + (">" * 7) + " branch\n"
            )
            (repo_root / "conflicted.py").write_text(conflict, encoding="utf-8")
            engine = RuleEngine(
                {"rules": [{"id": "merge-conflict-markers", "type": "merge-conflict-markers", "enabled": True}]}
            )
            violations = engine.scan_repository(repo_root)

            self.assertIn("merge-conflict-markers", {violation.rule_id for violation in violations})
            self.assertTrue(any(violation.line == 1 for violation in violations))

    def test_secret_scan_rule_flags_high_confidence_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            # Assemble the token dynamically so this test file holds no literal secret.
            fake_key = "AKIA" + ("A" * 16)
            (repo_root / "config.py").write_text(f'AWS_KEY = "{fake_key}"\n', encoding="utf-8")
            engine = RuleEngine({"rules": [{"id": "secret-scan", "type": "secret-scan", "enabled": True}]})
            violations = engine.scan_repository(repo_root)

            self.assertIn("secret-scan", {violation.rule_id for violation in violations})
            self.assertTrue(any("AWS access key" in violation.message for violation in violations))

    def test_debug_artifacts_rule_flags_leftover_debug_statements(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / "ui.js").write_text("function handler() {\n  console.log('x');\n}\n", encoding="utf-8")
            # Assemble the call dynamically so this test source holds no literal debug artifact.
            debug_call = "break" + "point()"
            (repo_root / "svc.py").write_text(f"def run():\n    {debug_call}\n    return 1\n", encoding="utf-8")
            engine = RuleEngine({"rules": [{"id": "debug-artifacts", "type": "debug-artifacts", "enabled": True}]})
            violations = engine.scan_repository(repo_root)

            flagged_paths = {violation.path for violation in violations}
            self.assertEqual(flagged_paths, {"svc.py", "ui.js"})

    def test_validate_manifest_reports_structural_problems(self) -> None:
        clean = validate_manifest({"rules": [{"id": "one", "type": "secret-scan"}]})
        self.assertEqual(clean, [])

        problems = validate_manifest(
            {
                "rules": [
                    {"id": "dup", "type": "secret-scan"},
                    {"id": "dup", "type": "not-a-real-type"},
                    {"type": "composite", "rules": [], "logic": "maybe"},
                    {"id": "sev", "type": "empty-files", "severity": "loud"},
                ]
            }
        )
        self.assertTrue(any("duplicate id" in problem for problem in problems))
        self.assertTrue(any("unknown type" in problem for problem in problems))
        self.assertTrue(any("non-empty 'rules'" in problem for problem in problems))
        self.assertTrue(any("'logic'" in problem for problem in problems))
        self.assertTrue(any("invalid 'severity'" in problem for problem in problems))

    def test_per_rule_include_and_exclude_scope_matching(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / "src").mkdir()
            (repo_root / "generated").mkdir()
            (repo_root / "src" / "app.py").write_text(("z" * 200) + "\n", encoding="utf-8")
            (repo_root / "generated" / "big.py").write_text(("z" * 200) + "\n", encoding="utf-8")

            # include limits the rule to src/**, exclude drops the generated tree.
            engine = RuleEngine(
                {
                    "rules": [
                        {
                            "id": "long-lines",
                            "type": "long-lines",
                            "enabled": True,
                            "max_length": 120,
                            "include": ["src/**/*.py"],
                            "exclude": ["**/generated/**"],
                        }
                    ]
                }
            )
            violations = engine.scan_repository(repo_root)

            flagged_paths = {violation.path for violation in violations}
            self.assertEqual(flagged_paths, {"src/app.py"})

    def test_rule_severity_is_attached_to_violations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / "blank.txt").write_text("", encoding="utf-8")
            engine = RuleEngine(
                {"rules": [{"id": "empty-files", "type": "empty-files", "enabled": True, "severity": "warning"}]}
            )
            violations = engine.scan_repository(repo_root)

            self.assertTrue(violations)
            self.assertTrue(all(violation.severity == "warning" for violation in violations))
            self.assertIn("(warning)", violations[0].format())
            self.assertEqual(violations[0].as_dict()["severity"], "warning")

    def test_trailing_whitespace_and_final_newline_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / "spacey.py").write_text("value = 1   \nok = 2\n", encoding="utf-8")
            (repo_root / "nonl.py").write_text("no_newline = 1", encoding="utf-8")
            (repo_root / "clean.py").write_text("clean = 1\n", encoding="utf-8")
            engine = RuleEngine(
                {
                    "rules": [
                        {"id": "trailing-whitespace", "type": "trailing-whitespace", "enabled": True},
                        {"id": "final-newline", "type": "final-newline", "enabled": True},
                    ]
                }
            )
            violations = engine.scan_repository(repo_root)

            by_rule = {(violation.rule_id, violation.path) for violation in violations}
            self.assertIn(("trailing-whitespace", "spacey.py"), by_rule)
            self.assertIn(("final-newline", "nonl.py"), by_rule)
            self.assertNotIn(("trailing-whitespace", "clean.py"), by_rule)
            self.assertNotIn(("final-newline", "clean.py"), by_rule)

    def test_sbgignore_excludes_matching_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / "keep.py").write_text("# placeholder\n", encoding="utf-8")
            (repo_root / "build").mkdir()
            (repo_root / "build" / "gen.py").write_text("# placeholder\n", encoding="utf-8")
            (repo_root / "vendor").mkdir()
            (repo_root / "vendor" / "lib.py").write_text("# placeholder\n", encoding="utf-8")
            (repo_root / ".sbgignore").write_text("# ignore generated trees\nbuild/\nvendor\n", encoding="utf-8")

            engine = RuleEngine(
                {
                    "rules": [
                        {
                            "id": "placeholder-comments",
                            "type": "placeholder-comments",
                            "enabled": True,
                            "patterns": ["placeholder"],
                        }
                    ]
                }
            )
            violations = engine.scan_repository(repo_root)

            self.assertEqual({violation.path for violation in violations}, {"keep.py"})


if __name__ == "__main__":
    unittest.main()
