import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verification_session.py"


class VerificationTests(unittest.TestCase):
    def run_session(self, command):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()
            git("init", "-q")
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "commit", "--allow-empty", "-qm", "base")
            base = git("rev-parse", "HEAD")
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "commit", "--allow-empty", "-qm", "head")
            head = git("rev-parse", "HEAD")
            manifest = repo / "manifest.json"
            result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--head", head, "--base", base,
                                     "--manifest", str(manifest), "--state", "light/390px", "--expected", "criterion verified",
                                     "--exclude", "R&D live data not exercised", "--", *command], cwd=repo, capture_output=True, text=True)
            return result, json.loads(manifest.read_text())

    def test_mid_run_checkout_change_invalidates_session(self):
        result, manifest = self.run_session(["bash", "-c", "git checkout -q HEAD~1; sleep 3"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Source changed", manifest["observed"])

    def test_failing_pipeline_followed_by_log_printing_stays_nonzero(self):
        result, manifest = self.run_session(["bash", "-o", "pipefail", "-c", "python3 -c 'raise SystemExit(7)' | tail -n 10"])
        self.assertEqual(result.returncode, 7)
        self.assertEqual(manifest["exit_code"], 7)
        self.assertEqual(manifest["exclusions"], ["R&D live data not exercised"])
        result, manifest = self.run_session(["bash", "-c", "printf 'observed result\n'"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("inspect retained output", manifest["observed"])
