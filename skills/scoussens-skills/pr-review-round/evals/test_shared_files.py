"""Run with python3 -B -m unittest discover -s <this directory> -v."""

from pathlib import Path
import unittest


SKILL = Path(__file__).resolve().parent.parent
OWNER = SKILL.parent / "pr-digest"


class InstallTests(unittest.TestCase):
    """The skills CLI installs each skill folder alone, so shared files are copies."""

    def test_shared_files_match_their_owning_skill(self):
        for path in ("references/teacher-button.md",):
            with self.subTest(path=path):
                self.assertEqual((SKILL / path).read_bytes(), (OWNER / path).read_bytes(),
                                 f"copy {SKILL.name}/{path} from {OWNER.name}/{path}")


if __name__ == "__main__":
    unittest.main()
