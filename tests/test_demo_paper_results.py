"""Demo guarantees formatting artifacts cannot masquerade as benchmark evidence."""
from pathlib import Path
import tempfile
import unittest

from tools.demo_paper_results import CASES, SEEDS, demo_bundle, main
from tools.render_paper_results import render


class DemoPaperResultsTests(unittest.TestCase):
    def test_all_demo_inputs_are_explicitly_synthetic(self):
        bundle = demo_bundle()
        self.assertEqual(bundle["evidence_class"], "SYNTHETIC_ENGINEERING")
        self.assertEqual(len(bundle["case_run_scores"]), 5 * 5 * 7)
        self.assertEqual(bundle["seeds"], SEEDS)
        self.assertTrue(all(case.startswith("SYNTHETIC-") for case in CASES))
        result = render(bundle, synthetic=True)
        self.assertIn("paired_effects_table.tex", result)
        with self.assertRaises(ValueError):
            render(bundle, synthetic=False)

    def test_cli_refuses_overwrite_and_marks_every_tex_file(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "DEMO"
            self.assertEqual(main(["--output", str(output)]), 0)
            self.assertEqual(main(["--output", str(output)]), 2)
            files = list(output.iterdir())
            self.assertEqual(len(files), 12)
            tex_files = [path for path in files if path.suffix == ".tex"]
            self.assertEqual(len(tex_files), 8)
            for path in tex_files:
                self.assertTrue(path.name.startswith("DEMO_"))
                self.assertTrue(path.read_text().startswith("% SYNTHETIC ENGINEERING"))
            self.assertIn("DO NOT CITE OR PUBLISH", (output / "README.txt").read_text())


if __name__ == "__main__":
    unittest.main()
