from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from sbg.engine import RuleEngine


def _scan(rule_type: str, filename: str, source: str, extra: dict | None = None) -> list:
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        (repo_root / filename).write_text(source, encoding="utf-8")
        rule = {"id": rule_type, "type": rule_type, "enabled": True}
        if extra:
            rule.update(extra)
        return RuleEngine({"rules": [rule]}).scan_repository(repo_root)


class AstRuleTests(unittest.TestCase):
    def test_python_syntax_flags_unparseable_file(self) -> None:
        violations = _scan("python-syntax", "broken.py", "def oops(:\n    pass\n")
        self.assertTrue(violations)
        self.assertEqual(violations[0].rule_id, "python-syntax")

    def test_python_syntax_ignores_non_python(self) -> None:
        violations = _scan("python-syntax", "notes.txt", "def oops(:\n")
        self.assertEqual(violations, [])

    def test_bare_except_detected(self) -> None:
        source = "try:\n    do()\nexcept:\n    pass\n"
        violations = _scan("python-bare-except", "m.py", source)
        self.assertTrue(any(v.rule_id == "python-bare-except" for v in violations))

    def test_broad_except_detected(self) -> None:
        source = "try:\n    do()\nexcept Exception:\n    pass\n"
        violations = _scan("python-broad-except", "m.py", source)
        self.assertTrue(violations)
        self.assertIn("Exception", violations[0].message)

    def test_mutable_default_detected(self) -> None:
        source = "def f(items=[]):\n    return items\n"
        violations = _scan("python-mutable-default", "m.py", source)
        self.assertTrue(violations)
        self.assertIn("mutable default", violations[0].message)

    def test_eval_exec_detected(self) -> None:
        source = "def run(code):\n    return eval(code)\n"
        violations = _scan("python-eval-exec", "m.py", source)
        self.assertTrue(violations)
        self.assertIn("eval", violations[0].message)

    def test_function_args_threshold(self) -> None:
        source = "def f(a, b, c, d):\n    return a\n"
        self.assertEqual(_scan("python-function-args", "m.py", source, {"max_args": 3}) != [], True)
        self.assertEqual(_scan("python-function-args", "m.py", source, {"max_args": 6}), [])

    def test_function_args_excludes_self(self) -> None:
        source = "class C:\n    def m(self, a, b):\n        return a\n"
        # 2 real params, self excluded -> under a max of 2
        self.assertEqual(_scan("python-function-args", "m.py", source, {"max_args": 2}), [])

    def test_function_length_threshold(self) -> None:
        body = "\n".join(f"    x{i} = {i}" for i in range(30))
        source = f"def big():\n{body}\n"
        self.assertTrue(_scan("python-function-length", "m.py", source, {"max_lines": 10}))
        self.assertEqual(_scan("python-function-length", "m.py", source, {"max_lines": 100}), [])

    def test_nesting_depth_threshold(self) -> None:
        source = (
            "def deep():\n"
            "    if a:\n"
            "        for b in c:\n"
            "            while d:\n"
            "                if e:\n"
            "                    return 1\n"
        )
        self.assertTrue(_scan("python-nesting-depth", "m.py", source, {"max_depth": 3}))
        self.assertEqual(_scan("python-nesting-depth", "m.py", source, {"max_depth": 4}), [])

    def test_ast_rules_skip_non_python_files(self) -> None:
        # A string that mentions eval in a .txt file must not be parsed as code.
        self.assertEqual(_scan("python-eval-exec", "notes.txt", "eval(danger)\n"), [])


if __name__ == "__main__":
    unittest.main()
