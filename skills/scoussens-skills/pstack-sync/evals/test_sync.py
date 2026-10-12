"""Run with python3 -B -m unittest discover -s <this directory> -v."""

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SKILL = Path(__file__).resolve().parent.parent
DISCOVERY_SKILL = SKILL.parent / "harness-discovery"
sys.path.insert(0, str(SKILL / "scripts"))
import sync  # noqa: E402

NEEDS = json.loads((SKILL / "needs.json").read_text())["needs"]
MAPPED = {need["id"] for need in NEEDS if need.get("discovery")}


def amp_entry():
    """Facts for every discovery field pstack-sync reads, as harness-discovery saves them."""
    return {
        "context": "Orb",
        "owners": {"launch": "Start a thread", "inspect": "Read a thread", "resume": "Message the thread",
                   "workspace_model": "selectable"},
        "helpers": {"invoke": "Task tool", "collect": "Task result", "blocks_caller": True, "readonly": None},
        "monitoring": {"wake": "A thread schedule"},
        "skills": {"locations": ".agents/skills/ in the project", "reload": "The reload-skills tool"},
        "instructions": {"user": "~/.config/amp/AGENTS.md", "project": "AGENTS.md in each directory"},
        "ask_user": "A choice tool with two to five options",
        "models": {"select": "Start a thread with an agent mode", "list": "List the agent modes"},
    }


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "skills"
        (self.root / "pstack-sync" / "harness").mkdir(parents=True)
        shutil.copy(SKILL / "needs.json", self.root / "pstack-sync" / "needs.json")
        self.profile = self.root / "pstack-sync" / "harness" / "amp.md"
        shutil.copy(SKILL / "harness" / "amp.md", self.profile)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.discovery = self.root / ".nthplusio-skills" / "discovery.json"
        self.discovery.parent.mkdir()
        self.save({"Amp": amp_entry()})

    def save(self, harnesses):
        self.discovery.write_text(json.dumps({"schema_version": 1, "harnesses": harnesses}))

    def state(self, harness="amp"):
        return sync.State(str(self.root), harness)

    def test_discovered_needs_need_no_profile_row(self):
        state = self.state()
        self.assertEqual(state.discovery_key, "Amp")
        self.assertEqual(set(state.facts), MAPPED)
        self.assertEqual(state.gaps(MAPPED | {"modes", "companion-skills"}), [])
        self.assertEqual(state.flagged_facts({"subagents", "modes"}),
                         {"subagents": {"helpers.invoke": "Task tool", "helpers.collect": "Task result",
                                        "helpers.blocks_caller": True}})

    def test_null_is_a_discovered_answer_but_missing_or_unknown_is_a_gap(self):
        entry = amp_entry()
        del entry["ask_user"]
        entry["owners"]["workspace_model"] = "unknown"
        self.save({"Amp": entry})
        state = self.state()
        self.assertEqual(state.facts["readonly-subagents"], {"helpers.readonly": None})
        self.assertEqual(state.gaps({"readonly-subagents", "ask-user", "worktrees"}), ["ask-user", "worktrees"])

    def test_without_an_entry_every_flagged_discovery_need_is_a_gap(self):
        self.discovery.unlink()
        state = self.state()
        self.assertIsNone(state.discovery_key)
        self.assertEqual(state.gaps({"subagents", "modes"}), ["subagents"])
        self.save({"Codex": amp_entry()})
        self.assertEqual(self.state().gaps({"subagents"}), ["subagents"])

    def test_the_harness_is_matched_by_key_or_slug(self):
        self.save({"Claude Code": amp_entry()})
        for harness in ("claude-code", "Claude Code"):
            with self.subTest(harness=harness):
                self.assertEqual(self.state(harness).discovery_key, "Claude Code")

    def test_a_profile_row_overrides_discovery(self):
        self.profile.write_text(self.profile.read_text() + "| `subagents` | native | Task tool as written | Test |\n")
        state = self.state()
        self.assertIn("subagents", state.auto_accept)
        self.assertNotIn("subagents", state.flagged_facts({"subagents"}))
        self.assertNotIn("subagents", state.outstanding("Launch it with the Task tool.", []))

    def test_root_overrides_the_git_repository(self):
        elsewhere = self.root.parent / "elsewhere"
        shutil.copytree(self.discovery.parent, elsewhere / ".nthplusio-skills")
        self.discovery.unlink()
        self.assertEqual(sync.State(str(self.root), "amp", str(elsewhere)).discovery_key, "Amp")

    def test_slug_matches_harness_discovery(self):
        spec = importlib.util.spec_from_file_location("state", DISCOVERY_SKILL / "scripts" / "state.py")
        state = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(state)
        for name in ("Amp", "Claude Code", "Codex CLI", " Cursor ", "GPT-5 Agent"):
            with self.subTest(name=name):
                self.assertEqual(sync.slug(name), state.slug(name))


class ShippedStateTests(unittest.TestCase):
    def test_the_amp_profile_has_rows_only_for_needs_without_discovery_fields(self):
        rows = sync.parse_profile((SKILL / "harness" / "amp.md").read_text())
        self.assertEqual(set(rows), {need["id"] for need in NEEDS} - MAPPED)

    def test_every_discovery_field_exists_in_the_discovery_template(self):
        template = json.loads((DISCOVERY_SKILL / "assets" / "discovery.template.json").read_text())
        entry = next(iter(template["harnesses"].values()))
        for need in NEEDS:
            for field in need.get("discovery", []):
                with self.subTest(need=need["id"], field=field):
                    node = entry
                    for part in field.split("."):
                        self.assertIn(part, node)
                        node = node[part]


if __name__ == "__main__":
    unittest.main()
