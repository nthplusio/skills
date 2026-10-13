"""The validator checks metadata.needs against the discovery template's vocabulary.

Run with python3 -B -m unittest discover -s <this directory> -v.
"""

from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[4]
VALIDATOR = REPO / "scripts" / "validate-skills.mjs"


def skill(needs):
    metadata = f"metadata:\n  needs: {needs}\n" if needs is not None else ""
    return ("---\nname: sample\ndescription: Does one thing. Use when asked for the sample, the example, or the fixture.\n"
            f"{metadata}---\n\n# Sample\n\nBody.\n")


class NeedsDeclarationTests(unittest.TestCase):
    def validate(self, needs):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "skills" / "sample" / "SKILL.md"
            path.parent.mkdir(parents=True)
            path.write_text(skill(needs))
            return subprocess.run(["node", str(VALIDATOR)], cwd=root, capture_output=True, text=True)

    def test_a_known_path_validates(self):
        result = self.validate("artifacts, skills.load, helpers.invoke")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1 skill(s) valid", result.stdout)

    def test_an_unknown_path_is_an_error_that_names_it(self):
        result = self.validate("owners.nonexistent")
        self.assertEqual(result.returncode, 1)
        self.assertIn("metadata.needs names `owners.nonexistent`", result.stderr)
        self.assertIn("discovery.template.json", result.stderr)

    def test_an_empty_item_is_an_error(self):
        result = self.validate("artifacts,,skills.load")
        self.assertEqual(result.returncode, 1)
        self.assertIn("empty item", result.stderr)

    def test_a_skill_without_needs_still_validates(self):
        self.assertEqual(self.validate(None).returncode, 0)


if __name__ == "__main__":
    unittest.main()
