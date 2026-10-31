"""Installed checker contracts, not a model evaluation of handoff prose."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SKILL = Path(__file__).resolve().parent.parent
HEADER = "| ID | Action | Blocked by | Done when | Touches |\n| --- | --- | --- | --- | --- |\n"


class InstalledCheckerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="handoff install ")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.installed = root / "installed skills" / "agent-handoff"
        shutil.copytree(SKILL, self.installed)
        self.cwd = root / "foreign cwd"
        self.cwd.mkdir()
        self.handoff = root / "handoff with spaces.md"

    def check(self, rows):
        self.handoff.write_text(HEADER + "\n".join(rows) + "\n")
        return subprocess.run(
            [sys.executable, "-B", str(self.installed / "scripts/check-handoff.py"), str(self.handoff)],
            cwd=self.cwd, capture_output=True, text=True, timeout=10,
        )

    def test_dependency_table_from_foreign_nonrepository_cwd(self):
        result = self.check([
            "| A1 | Obtain repository evidence | EXT owner | Revision and status are recorded | — |",
            "| A2 | Verify remaining work | A1 | Checks agree with the recorded baseline | — |",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.cwd / ".git").exists())
        self.assertEqual(list(self.cwd.iterdir()), [])

    def test_invalid_graphs_fail_after_installation(self):
        for rows in (
            ["| A1 | Work | A2 | Verified | — |"],
            ["| A1 | Work | A2 | Verified | — |", "| A2 | Work | A1 | Verified | — |"],
            ["| A1 | Work | — | | — |"],
            ["| A1 | Work | — | Verified | — |", "| A1 | Work | — | Verified | — |"],
        ):
            with self.subTest(rows=rows):
                self.assertEqual(self.check(rows).returncode, 1)


if __name__ == "__main__":
    unittest.main()
