"""Regression for asynchronous Data Integrity provenance on the hosted release.

The registered 36 source rows can render before the bundled probe metadata.
The browser readiness gate must wait for the actual visible freshness status.
These tests execute the extracted JavaScript predicate with Node; no mocking
or weakening of the production browser assertions is required.
"""
import ast
import json
import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "verify_live_ui.py"
EVAL_JS = r"""
const vm = require('node:vm');
const source = process.argv[1];
const body = process.argv[2];
const document = {body: {innerText: body}, querySelector: () => null};
const readiness = vm.runInNewContext(source, {document});
const outcome = readiness({
  expected: ['Data Integrity', 'All 36 FMCSA / DOT sources'],
  errors: ['Transport3r could not render this view.'],
  label: 'integrity'
});
process.stdout.write(JSON.stringify(outcome));
"""


def readiness_source():
    parsed = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for statement in parsed.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "READINESS_JS"
            for target in statement.targets
        ):
            return ast.literal_eval(statement.value)
    raise AssertionError("Cannot find hosted browser readiness predicate")


class IntegrityReadinessTests(unittest.TestCase):
    def evaluate(self, content):
        result = subprocess.run(
            ["node", "-e", EVAL_JS, readiness_source(), content],
            check=True, capture_output=True, text=True, timeout=10,
        )
        return json.loads(result.stdout)

    def test_registry_rows_and_unresolved_provenance_are_not_ready(self):
        self.assertFalse(self.evaluate(
            "Data Integrity All 36 FMCSA / DOT sources "
            "Pages manifest commit Not verified Bundled source-probe snapshot Not verified"
        ))

    def test_waits_for_actual_published_probe_freshness(self):
        self.assertEqual(
            self.evaluate(
                "Data Integrity All 36 FMCSA / DOT sources "
                "Bundled source-probe snapshot 14 days old; not a live check"
            ),
            {"ready": True},
        )

    def test_service_checking_state_does_not_pass(self):
        self.assertFalse(self.evaluate(
            "Data Integrity All 36 FMCSA / DOT sources "
            "Checking the installed evidence service "
            "Bundled source-probe snapshot 14 days old; not a live check"
        ))


if __name__ == "__main__":
    unittest.main()
