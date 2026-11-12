"""Public CLI contract; temporary repositories only, no tracker or model calls."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SKILL = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def run_config(self, root, *args, skill=SKILL, ok=True):
        result = subprocess.run([sys.executable, "-B", str(skill / "scripts/review_config.py"),
                                 "--root", str(root), *args], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0 if ok else 2, result.stderr)
        if not ok:
            self.assertIn("Review configuration error:", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            return result.stderr
        return json.loads(result.stdout)

    def profile(self, root, **changes):
        path = root / ".nthplusio-skills/review.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"schema_version": 1, **changes}))
        return path

    def test_unconfigured_and_independently_installed_skills_ship_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repository"
            root.mkdir()
            before = list(root.iterdir())
            result = self.run_config(root)
            self.assertIsNone(result["profile"])
            self.assertEqual(result["execution"], {"reviewers": "auto", "policy": []})
            self.assertEqual(result["tracker"], {"policy": []})
            self.assertEqual(set(result["references"]), {"conventions", "data-layer", "integration", "security", "verification"})
            self.assertEqual(list(root.iterdir()), before, "resolution must not run setup")
            installed = Path(tmp) / "installed skill"
            shutil.copytree(SKILL, installed)
            lone = self.run_config(root, skill=installed)
            self.assertEqual(lone["revision"], result["revision"])
            for paths in lone["references"].values():
                self.assertTrue(all(Path(p).is_relative_to(installed) for p in paths))

    def test_per_repository_policies_and_reference_modes_do_not_leak(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            for root, policy in [(a, "Hosted tracker; automation completes after deploy."),
                                 (b, "Local Markdown tickets; owner completes after acceptance.")]:
                root.mkdir()
                (root / "tickets.md").write_text(policy)
                (root / "storage.md").write_text("Repository-specific storage checks")
                (root / "api.md").write_text("Repository-specific integration checks")
                (root / "a11y.md").write_text("Repository-specific accessibility checks")
                (root / "execution.md").write_text("Use this harness's existing execution setup.")
                self.profile(root, guidance=["storage.md"], tracker={"policy": ["tickets.md"]},
                             execution={"reviewers": "serial", "policy": ["execution.md"]}, references={
                                 "data-layer": {"files": ["storage.md"]},
                                 "integration": {"mode": "replace", "files": ["api.md"]},
                                 "security": {"mode": "disable"}, "accessibility": {"files": ["a11y.md"]}})
            first, second = self.run_config(a), self.run_config(b)
            self.assertEqual(first["execution"]["reviewers"], "serial")
            self.assertEqual(first["tracker"]["policy"], [str(a / "tickets.md")])
            self.assertEqual(second["tracker"]["policy"], [str(b / "tickets.md")])
            self.assertEqual(len(first["references"]["data-layer"]), 2)
            self.assertEqual(first["references"]["integration"], [str(a / "api.md")])
            self.assertEqual(first["references"]["accessibility"], [str(a / "a11y.md")])
            self.assertNotIn("security", first["references"])
            self.assertEqual(first["disabled"], ["security"])
            self.assertNotEqual(first["revision"], second["revision"])

    def test_revision_tracks_reference_and_policy_contents_not_repo_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "a"
            root.mkdir()
            rule = root / "rules.md"
            rule.write_text("Current rule")
            self.profile(root, tracker={"policy": ["rules.md"]}, references={"conventions": {"files": ["rules.md"]}})
            first = self.run_config(root)
            clone = Path(tmp) / "b"
            shutil.copytree(root, clone)
            self.assertEqual(first["revision"], self.run_config(clone)["revision"])
            rule.write_text("Changed acceptance and automation rule")
            self.assertNotEqual(first["revision"], self.run_config(root)["revision"])

    def test_template_and_alternate_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template = root / "profile.json"
            shutil.copyfile(SKILL / "assets/review.template.json", template)
            result = self.run_config(root, "--config", "profile.json")
            self.assertEqual(result["profile"], str(template))
            self.assertEqual(len(result["references"]), 5)
            self.run_config(root, "--config", "missing.json", ok=False)
            self.run_config(root, "--config", str(template), ok=False)

    def test_invalid_configuration_never_silently_falls_back(self):
        cases = [
            {"referneces": {}}, {"execution": {"reviewers": "Amp"}},
            {"tracker": {"provider": "invented"}}, {"guidance": "rules.md"},
            {"references": {"data-layer": {"mode": "replace"}}},
            {"references": {"security": {"mode": "optional"}}},
            {"references": {"custom": {}}},
            {"references": {"integration": {"file": ["rules.md"]}}},
            {"references": {"integration": {"mode": "disable", "files": ["rules.md"]}}},
            {"tracker": {"policy": ["missing.md"]}}, {"schema_version": True},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "rules.md").write_text("Rule")
            for case in cases:
                with self.subTest(case=case):
                    self.profile(root, **case)
                    self.run_config(root, ok=False)

    def test_references_cannot_escape_repository_by_path_or_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            outside = Path(tmp) / "private.md"
            outside.write_text("Do not read")
            (root / "link.md").symlink_to(outside)
            for name in ("../private.md", str(outside), "link.md"):
                with self.subTest(path=name):
                    self.profile(root, guidance=[name])
                    error = self.run_config(root, ok=False)
                    self.assertIn("outside-repository", error)


if __name__ == "__main__":
    unittest.main()
