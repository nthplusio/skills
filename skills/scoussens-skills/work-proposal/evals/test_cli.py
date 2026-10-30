"""Public CLI contracts, using disposable installed resources and browser stubs."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SKILL = Path(__file__).resolve().parent.parent


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="proposal cli ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scripts = self.root / "installed skill" / "scripts"
        shutil.copytree(SKILL / "scripts", self.scripts)

    def check(self, source, *args, html=False):
        path = self.root / ("proposal.html" if html else "proposal.md")
        path.write_text(source)
        return subprocess.run(
            [sys.executable, str(self.scripts / "check-totals.py"), str(path), *args],
            cwd=self.root, capture_output=True, text=True,
        )

    def test_wrong_single_row_fails_strict(self):
        sources = (
            (False, "| Item | Hours | Cost |\n| --- | --- | --- |\n| Build | 2 | $999 |\n"),
            (True, "<table><tr><th>Item</th><th>Hours</th><th>Cost</th></tr>"
                   "<tr><td>Build</td><td>2</td><td>$999</td></tr></table>"),
        )
        for html, source in sources:
            with self.subTest(html=html):
                result = self.check(source, "--rate", "100", "--strict", html=html)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("does not equal", result.stdout)

    def test_single_row_and_ranges_check_real_arithmetic(self):
        cases = (
            ("| Build | 2 | $200 |\n", "100"),
            ("| Build | 2 | $0 |\n", "0"),
            ("| Build | 1.5–2.5 | $150–$250 |\n| Review | 3–4 | $300–$400 |\n"
             "| Total | 4.5–6.5 | $450–$650 |\n", "100"),
        )
        for rows, rate in cases:
            with self.subTest(rows=rows):
                result = self.check("| Item | Hours | Cost |\n| --- | --- | --- |\n" + rows,
                                    "--rate", rate, "--strict")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("CHECKED 'Cost' = 'Hours'", result.stdout)
                self.assertIn("FAIL 0; UNVERIFIED 0", result.stdout)

    def test_unrelated_numeric_column_is_not_hours(self):
        result = self.check("| ID | Hours | Cost |\n| --- | --- | --- |\n| 71 | 2 | $200 |\n",
                            "--rate", "100", "--strict")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_incorrect_total_and_range_endpoint_fail(self):
        for rows in ("| Build | 2 | $200 |\n| Total | 3 | $200 |\n",
                     "| Build | 2–3 | $200–$400 |\n"):
            with self.subTest(rows=rows):
                result = self.check("| Item | Hours | Cost |\n| --- | --- | --- |\n" + rows,
                                    "--rate", "100", "--strict")
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("FAIL  table 1", result.stdout)

    def test_totals_without_rate_and_rounding_tolerance(self):
        result = self.check("| Item | Cost |\n| --- | --- |\n| Build | $200 |\n| Total | $200 |\n",
                            "--strict")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CHECKED 'Cost' total $200", result.stdout)
        self.assertNotIn("hours × rate", result.stdout)
        for cost, expected in (("$200.50", 0), ("$200.52", 1)):
            with self.subTest(cost=cost):
                result = self.check(f"| Item | Hours | Cost |\n| --- | --- | --- |\n| Build | 2 | {cost} |\n",
                                    "--rate", "100", "--strict")
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def test_skipped_arithmetic_is_unverified_and_strict_fails(self):
        sources = (
            "No tables here.",
            "| Item | Description |\n| --- | --- |\n| Build | Pending |\n",
            "| Item | Units | Cost |\n| --- | --- | --- |\n| Build | 2 | $200 |\n",
            "| Item | Hours | Cost |\n| --- | --- | --- |\n| Build | TBD | $200 |\n",
            "| Item | Hours | Cost |\n| --- | --- | --- |\n| Build | 3–2 | $300–$200 |\n",
            "| Item | Hours | Cost |\n| --- | --- | --- |\n| Build | 2 | $2,00 |\n",
            "| Item | Hours | Cost |\n| --- | --- | --- |\n| Build | 2 | $200 |\n"
            "| Review | 3 | TBD |\n| Total | 5 | $200 |\n",
            "| Item | Hours | Cost |\n| --- | --- | --- |\n| Build | 2–3 pending | $200–$300 |\n",
            "| Item | Hours | Cost |\n| --- | --- | --- |\n| Build | 2 | $200 |\n"
            "| Total | 2 | $200 |\n| Subtotal | 2 | $200 |\n",
            "| Item | Hours | Cost |\n| --- | --- | --- |\n| Build | 2 | $200 |\n"
            "| Credit | 0 | -$50 |\n| Total | 2 | $150 |\n",
        )
        for source in sources:
            with self.subTest(source=source):
                normal = self.check(source, "--rate", "100")
                strict = self.check(source, "--rate", "100", "--strict")
                self.assertEqual(normal.returncode, 0, normal.stdout + normal.stderr)
                self.assertEqual(strict.returncode, 1, strict.stdout + strict.stderr)
                self.assertIn("UNVERIFIED", strict.stdout)
                self.assertNotIn("on every row", strict.stdout)

    def test_invalid_rate_or_tolerance_is_a_usage_error(self):
        for option, value in (("--rate", "nan"), ("--rate", "inf"),
                              ("--tolerance", "-1"), ("--tolerance", "nan")):
            with self.subTest(option=option, value=value):
                result = self.check("No tables.", option, value)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_failed_rerender_preserves_old_pdf(self):
        result, output = self.render("echo 'browser failed' >&2\nexit 37\n")
        self.assertEqual(result.returncode, 37, result.stdout + result.stderr)
        self.assertNotIn("wrote:", result.stdout)
        self.assertIn("browser failed", result.stderr)
        self.assertEqual(output.read_bytes(), b"%PDF-1.4\nprevious proposal\n")

    def test_missing_empty_invalid_or_failed_output_preserves_old_pdf(self):
        for body in ("exit 0\n", ': > "$pdf"\n', 'echo invalid > "$pdf"\n',
                     'printf "%s\\n" "%PDF-1.4" > "$pdf"\nexit 37\n'):
            with self.subTest(body=body):
                result, output = self.render(
                    'for arg in "$@"; do case "$arg" in --print-to-pdf=*) pdf=${arg#*=};; esac; done\n'
                    + body)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn("wrote:", result.stdout)
                self.assertEqual(output.read_bytes(), b"%PDF-1.4\nprevious proposal\n")

    def test_override_writes_fresh_pdf_and_encodes_source_url(self):
        result, output = self.render(
            'for arg in "$@"; do case "$arg" in --print-to-pdf=*) pdf=${arg#*=};; esac; done\n'
            'case "$arg" in file://*proposal%20%231.html) ;; *) exit 44;; esac\n'
            'printf "%s\\n" "%PDF-1.4" "fresh proposal" > "$pdf"\n', override=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("wrote:", result.stdout)
        self.assertEqual(output.read_bytes(), b"%PDF-1.4\nfresh proposal\n")

    def render(self, body, override=False):
        source = self.root / "proposal #1.html"
        source.write_text("<!doctype html><title>Proposal</title><p>New proposal</p>")
        output = self.root / "proposal.pdf"
        output.write_bytes(b"%PDF-1.4\nprevious proposal\n")
        browser = self.root / ("custom browser" if override else "google-chrome")
        browser.write_text("#!/bin/sh\n" + body)
        browser.chmod(0o755)
        env = dict(os.environ, PATH=f"{self.root}:{os.environ['PATH']}")
        env.pop("CHROME_BIN", None)
        env.pop("PAPER", None)
        if override:
            env["CHROME_BIN"] = str(browser)
        result = subprocess.run(
            ["bash", str(self.scripts / "html-to-pdf.sh"), str(source), str(output)],
            cwd=self.root, env=env, capture_output=True, text=True,
        )
        return result, output


if __name__ == "__main__":
    unittest.main()
