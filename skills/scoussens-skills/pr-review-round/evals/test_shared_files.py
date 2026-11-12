"""Run with python3 -B -m unittest discover -s <this directory> -v."""

from pathlib import Path
import unittest


SKILL = Path(__file__).resolve().parent.parent
SOURCES = {
    "pr-digest": ("references/teacher-button.md",),
    "pr-detail": ("scripts/gather_pr.sh", "scripts/pr_history.py", "assets/pr-history.css"),
    "configuring-reviews": ("scripts/review_config.py", "references/review-profile.md",
                            "references/defaults/conventions.md", "references/defaults/data-layer.md",
                            "references/defaults/integration.md", "references/defaults/security.md",
                            "references/defaults/verification.md"),
}


class InstallTests(unittest.TestCase):
    """The skills CLI installs each skill folder alone, so shared files are copies."""

    def test_shared_files_match_their_owning_skill(self):
        for owner, paths in SOURCES.items():
            for path in paths:
                with self.subTest(owner=owner, path=path):
                    self.assertEqual((SKILL / path).read_bytes(), (SKILL.parent / owner / path).read_bytes(),
                                     f"copy {SKILL.name}/{path} from {owner}/{path}")
        path = "scripts/md_to_html.py"
        self.assertEqual((SKILL / path).read_bytes(), (SKILL.parent / "pr-detail" / path).read_bytes(),
                         "copy pr-detail/scripts/md_to_html.py from pr-review-round")

    def test_family_contract_has_one_owner_and_each_consumer_has_a_local_copy(self):
        path = "references/pr-family.md"
        owner = SKILL.parent / "pr-detail" / path
        for consumer in ("pr-review-round", "pr-digest", "pr-teacher"):
            with self.subTest(consumer=consumer):
                self.assertEqual(owner.read_bytes(), (SKILL.parent / consumer / path).read_bytes(),
                                 f"copy {consumer}/{path} from pr-detail/{path}")


if __name__ == "__main__":
    unittest.main()
