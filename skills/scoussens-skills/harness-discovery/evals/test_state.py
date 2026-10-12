"""Run with python3 -B -m unittest discover -s <this directory> -v."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SKILL = Path(__file__).resolve().parent.parent
STATE = SKILL / "scripts" / "state.py"


def discovery_document():
    discovery = json.loads((SKILL / "assets" / "discovery.template.json").read_text())
    facts = discovery["harnesses"].pop("REPLACE_WITH_DISCOVERED_HARNESS_NAME")
    facts.update(context="Local terminal", observed_at="2026-10-09T12:00:00Z", sources=["Inspected tool inventory"],
                 owner_term="session", helper_term="subagent")
    facts["skills"]["load"] = "Load by skill name"
    other = deepcopy(facts)
    other.update(context="Orb", owner_term="thread")
    discovery["harnesses"] = {"Claude Code": facts, "Amp": other}
    return discovery


class StateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repository = self.root / "repository"
        self.discovery_path = self.repository / ".nthplusio-skills" / "discovery.json"
        self.discovery_path.parent.mkdir(parents=True)
        self.save(discovery_document())

    def save(self, discovery):
        self.discovery_path.write_text(json.dumps(discovery))

    def state(self, *arguments, cwd=None, root=True):
        command = [sys.executable, "-B", str(STATE), *arguments] + (["--root", str(self.repository)] if root else [])
        return subprocess.run(command, cwd=cwd or self.root, capture_output=True, text=True)

    def test_resolve_prints_the_entry_with_its_key_and_slug(self):
        for name in ("Claude Code", "claude-code", "CLAUDE CODE"):
            with self.subTest(name=name):
                result = self.state("resolve", "--harness", name)
                self.assertEqual(result.returncode, 0, result.stderr)
                entry = json.loads(result.stdout)
                self.assertEqual(entry["harness"], {"name": "Claude Code", "slug": "claude-code", "context": "Local terminal",
                                                    "owner_term": "session", "helper_term": "subagent"})
                self.assertEqual(entry["skills"]["load"], "Load by skill name")
                self.assertNotIn("run_root", entry)

    def test_unknown_harness_is_not_guessed(self):
        result = self.state("resolve", "--harness", "Claude")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("run harness-discovery in it", result.stderr)

    def test_keys_must_have_distinct_slugs(self):
        discovery = discovery_document()
        discovery["harnesses"]["claude code"] = deepcopy(discovery["harnesses"]["Claude Code"])
        self.save(discovery)
        result = self.state("check", "discovery")
        self.assertEqual(result.returncode, 1)
        self.assertIn("share the slug claude-code", result.stderr)
        discovery["harnesses"] = {"--": discovery["harnesses"]["Amp"]}
        self.save(discovery)
        self.assertIn("needs letters or digits", self.state("check", "discovery").stderr)

    def test_root_defaults_to_the_working_directorys_git_repository(self):
        subprocess.run(["git", "init", "-q", str(self.repository)], check=True)
        inside = self.repository / "nested" / "folder"
        inside.mkdir(parents=True)
        result = self.state("check", cwd=inside, root=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"PASS: discovery {self.discovery_path.resolve()}\n")
        outside = self.root / "not-a-repository"
        outside.mkdir()
        result = self.state("check", cwd=outside, root=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("pass --root", result.stderr)

    def test_versions_this_tool_cannot_read_are_refused(self):
        for found, message in ((0, "is older than 1"), (2, "update these skills"), ("1", "update these skills")):
            with self.subTest(found=found):
                discovery = discovery_document()
                discovery["schema_version"] = found
                self.save(discovery)
                result = self.state("check", "discovery")
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)


if __name__ == "__main__":
    unittest.main()
