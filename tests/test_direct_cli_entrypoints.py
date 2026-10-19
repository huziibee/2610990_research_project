"""Exercise script entry points exactly as typed in PowerShell, not as imports.

Unit tests imported the tools as packages, hiding the sys.path failure when
Python executed tools/demo_paper_results.py from the repository root.
"""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

from tools.demo_paper_results import demo_bundle

ROOT = Path(__file__).resolve().parents[1]


def _run(*args):
    return subprocess.run(
        [sys.executable, *map(str, args)],
        cwd=ROOT, capture_output=True, text=True, timeout=90, check=False
    )


class DirectScriptEntrypointTests(unittest.TestCase):
    def test_exact_demo_command_from_repository_root(self):
        with tempfile.TemporaryDirectory(prefix="research-demo-entry-") as folder:
            dest = Path(folder) / "synthetic_demo"
            result = _run("tools/demo_paper_results.py", "--output", dest)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            response = json.loads(result.stdout)
            self.assertEqual(response["status"], "SYNTHETIC_FORMAT_DEMO_ONLY")
            self.assertFalse(response["benchmark_executed"])
            self.assertEqual(len(list(dest.iterdir())), 12)
            for candidate in dest.glob("DEMO_*.tex"):
                self.assertIn("NOT REAL EVIDENCE", candidate.read_text(encoding="utf-8").splitlines()[0])

    def test_direct_scored_renderer_supports_explicit_synthetic_fixture(self):
        with tempfile.TemporaryDirectory(prefix="research-render-entry-") as folder:
            source = Path(folder) / "fixture.json"
            output = Path(folder) / "output"
            source.write_text(json.dumps(demo_bundle()), encoding="utf-8")
            result = _run("tools/render_paper_results.py",
                          "--scored-bundle", source, "--output", output, "--synthetic")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(json.loads(result.stdout)["status"], "REVIEW_CANDIDATES_CREATED")
            self.assertTrue((output / "paired_effects_table.tex").is_file())
            self.assertFalse(json.loads((output / "SOURCE_PROVENANCE.json").read_text())["manuscript_modified"])

    def test_report_clis_launch_without_import_errors_or_inference(self):
        # --help exits before reading data, creating files, or contacting Gemini.
        for name in ("tools/demo_paper_results.py", "tools/render_paper_results.py",
                     "tools/report_route_matrix.py", "tools/audit_run_pairing.py"):
            with self.subTest(name=name):
                result = _run(name, "--help")
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertIn("usage:", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
