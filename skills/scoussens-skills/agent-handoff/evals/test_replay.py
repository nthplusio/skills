from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest


FIXTURES = Path(__file__).with_name("fixtures")


class ReplayTests(unittest.TestCase):
    def replay(self, files):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "evidence.tar"
            with tarfile.open(archive, "w") as bundle:
                for name in files:
                    bundle.add(FIXTURES / name, arcname=name)
            extracted = root / "extracted"
            extracted.mkdir()
            with tarfile.open(archive) as bundle:
                bundle.extractall(extracted, filter="data")
            return subprocess.run(
                [sys.executable, "-I", "-S", "replay.py"],
                cwd=extracted, env={}, capture_output=True, text=True, timeout=10,
            )

    def test_missing_transitive_input_fails_without_checkout_rescue(self):
        result = self.replay(["replay.py", "helper.py"])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("FileNotFoundError", result.stderr)
        self.assertIn("input.json", result.stderr)

    def test_complete_package_replays_in_clean_extraction(self):
        result = self.replay(["replay.py", "helper.py", "input.json"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "replay complete\n")
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
