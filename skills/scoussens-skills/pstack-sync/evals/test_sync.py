"""Run with python3 -B -m unittest discover -s <this directory> -v."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SKILL = Path(__file__).resolve().parent.parent
DISCOVERY_SKILL = SKILL.parent / "harness-discovery"
SCRIPT = SKILL / "scripts" / "sync.py"
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


def skill(name, body):
    return f"---\nname: {name}\ndescription: {name}\n---\n\n{body}\n"


def plugin(name):
    return {f"{name}/.cursor-plugin/plugin.json": json.dumps({"name": name}), f"{name}/LICENSE": f"{name} license\n"}


ALPHA_DESLOP = "Run `/deslop` from `cursor-team-kit` before each commit.\n"
UPSTREAM = {
    **plugin(sync.ROOT_PLUGIN),
    f"{sync.SUBDIR}/alpha/SKILL.md": skill("alpha", ALPHA_DESLOP + "Spawn `Task` with `subagent_type: \"helper\"`.\n"
                                           "Draft it with Cursor's built-in `create-skill` skill, then use the **beta** skill."),
    f"{sync.SUBDIR}/beta/SKILL.md": skill("beta", "pstack has no `/orchestrate` skill; another plugin provides it.\n"
                                          "Repeat with `/loop` until green, per the **tidy** principle skill."),
    f"{sync.SUBDIR}/principle-tidy/SKILL.md": skill("principle-tidy", "Keep it tidy."),
    f"{sync.ROOT_PLUGIN}/agents/helper.md": "---\nname: helper\n---\n\nYou are helper. Follow the **beta** skill.\n",
    **plugin("cursor-team-kit"),
    "cursor-team-kit/skills/deslop/SKILL.md": skill("deslop", "Collect evidence for `verify`."),
    "cursor-team-kit/skills/verify/SKILL.md": skill("verify", "Prove it."),
    "cursor-team-kit/skills/unused/SKILL.md": skill("unused", "Nobody hands off here."),
    **plugin("orchestrate"),
    "orchestrate/skills/orchestrate/SKILL.md": skill("orchestrate", "Orchestrate."),
}
PROFILE = "# Harness profile: test\n\n| Need | Support | test equivalent | Source |\n| --- | --- | --- | --- |\n"


class DependencyTests(unittest.TestCase):
    """sync against a small cursor/plugins built in a temporary directory and fetched over file://."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name)
        self.skills = self.tmp / "skills"
        (self.skills / sync.SELF / "harness").mkdir(parents=True)
        shutil.copy(SKILL / "needs.json", self.skills / sync.SELF / "needs.json")
        self.profile(PROFILE)

    def profile(self, text):
        durable = self.skills / ".nthplusio-skills" / "pstack-sync" / "harness" / "test.md"
        path = durable if durable.exists() else self.skills / sync.SELF / "harness" / "test.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def upstream(self, files=UPSTREAM):
        repo = self.tmp / "plugins"
        shutil.rmtree(repo, ignore_errors=True)
        for path, text in files.items():
            (repo / path).parent.mkdir(parents=True, exist_ok=True)
            (repo / path).write_text(text)
        git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", "plugins"], check=True)
        return repo

    def run_sync(self, command="sync", *args):
        env = {**os.environ, "HOME": str(self.tmp), "PSTACK_SYNC_UPSTREAM": (self.tmp / "plugins").as_uri()}
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), command, "--harness", "test",
                                 "--repo", str(self.skills), *args], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout) if command != "status" else result.stdout

    def durable(self):
        return self.skills / ".nthplusio-skills" / "pstack-sync"

    def manifest(self, **changes):
        path = self.durable() / "manifest.json"
        data = json.loads(path.read_text())
        data.update(changes)
        path.write_text(json.dumps(data))
        return data

    def test_installs_what_pstack_hands_off_to_transitively_and_nothing_else(self):
        self.upstream()
        report = self.run_sync()
        self.assertEqual(sorted(report["added"]),
                         sorted(["alpha", "beta", "principle-tidy", "deslop", "verify", sync.AGENTS]))
        self.assertEqual(report["dependencies"]["installed"], {
            "deslop": "cursor-team-kit/skills/deslop", "verify": "cursor-team-kit/skills/verify",
            f"{sync.AGENTS}/helper.md": f"{sync.ROOT_PLUGIN}/agents/helper.md"})
        self.assertEqual(sorted(p.name for p in (self.skills / sync.AGENTS).iterdir()), ["helper.md"])
        self.assertEqual(sorted(p.name for p in self.durable().glob("LICENSE-*")),
                         ["LICENSE-cursor-team-kit", f"LICENSE-{sync.ROOT_PLUGIN}"])
        self.assertEqual(list((self.skills / sync.SELF).glob("LICENSE-*")), [])
        self.assertFalse((self.skills / sync.SELF / "manifest.json").exists())
        self.assertNotIn(sync.AGENTS, report["needs_adaptation"], "a definition naming itself dispatches nothing")
        self.assertEqual(report["needs_adaptation"]["alpha"]["SKILL.md"]["needs"]["custom-subagents"], ["helper"])

    def test_a_second_sync_changes_nothing(self):
        self.upstream()
        first = self.run_sync()
        second = self.run_sync()
        self.assertEqual((second["added"], second["updated"], second["removed"]), ([], [], []))
        self.assertEqual(second["unchanged_count"], len(first["added"]))
        self.assertEqual(second["needs_adaptation"], first["needs_adaptation"])

    def test_handoffs_without_a_profile_mapping_are_unresolved(self):
        self.upstream()
        report = self.run_sync("sync", "--dry-run")
        self.assertEqual(report["dependencies"]["unresolved"],
                         {"create-skill": ["alpha/SKILL.md"], "orchestrate": ["beta/SKILL.md"]})
        self.profile(PROFILE + "| `companion-skills` | partial | `create-skill` → the harness's skill writer. | test |\n")
        report = self.run_sync("sync", "--dry-run")
        self.assertEqual(list(report["dependencies"]["unresolved"]), ["orchestrate"])
        self.assertIn("create-skill", report["needs_adaptation"]["alpha"]["SKILL.md"]["needs"]["companion-skills"])

    def test_excluding_a_dependency_drops_what_only_it_needed_and_flags_its_handoffs(self):
        self.upstream()
        self.run_sync()
        self.manifest(exclude=["deslop"])
        report = self.run_sync()
        self.assertEqual(sorted(report["removed"]), ["deslop", "verify"])
        self.assertEqual(report["dependencies"]["excluded"], {"deslop": ["alpha/SKILL.md"]})
        self.assertFalse((self.skills / "deslop").exists())

    def test_a_dependency_an_unmanaged_skill_has_is_left_to_it(self):
        self.upstream()
        (self.skills / "deslop").mkdir()
        (self.skills / "deslop" / "SKILL.md").write_text(skill("deslop", "Mine."))
        report = self.run_sync()
        self.assertEqual(report["dependencies"]["existing"], ["deslop"])
        self.assertNotIn("deslop", report["added"])
        self.assertNotIn("verify", report["added"])
        self.assertEqual((self.skills / "deslop" / "SKILL.md").read_text(), skill("deslop", "Mine."))

    def test_a_name_two_named_plugins_provide_is_ambiguous(self):
        files = {**UPSTREAM, **plugin("thermos"), "thermos/skills/deslop/SKILL.md": skill("deslop", "Other."),
                 f"{sync.SUBDIR}/alpha/SKILL.md": skill("alpha", "Run `/deslop` from `cursor-team-kit` or `thermos`.")}
        self.upstream(files)
        report = self.run_sync("sync", "--dry-run")
        self.assertEqual(report["dependencies"]["ambiguous"],
                         {"deslop": ["cursor-team-kit/skills/deslop", "thermos/skills/deslop"]})
        self.assertNotIn("deslop", report["added"])

    def test_an_adaptation_recorded_before_a_dependency_installed_is_flagged_until_recorded(self):
        self.upstream()
        transforms = {"test": {"accept": [], "global": [], "files": {"alpha/SKILL.md": {
            "transforms": [{"find": ALPHA_DESLOP, "replace": "Strip slop yourself before each commit.\n"}],
            "accepted": []}}}}
        (self.skills / sync.SELF / "transform.json").write_text(json.dumps(transforms))
        report = self.run_sync()
        self.assertEqual(report["needs_adaptation"]["alpha"]["SKILL.md"]["dependencies"], ["deslop", "helper"])
        self.assertNotIn("dependencies", report["needs_adaptation"]["beta"]["SKILL.md"])
        installed = self.skills / "alpha" / "SKILL.md"
        installed.write_text(installed.read_text().replace("Strip slop yourself before each commit.\n", ALPHA_DESLOP))
        self.run_sync("record", "alpha/SKILL.md")
        report = self.run_sync()
        self.assertNotIn("alpha", report["needs_adaptation"])
        self.assertIn("Dependencies (3)", self.run_sync("status"))

    def test_status_reads_the_last_commit_from_a_skills_directory_inside_a_repository(self):
        git = ["git", "-C", str(self.tmp), "-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run(["git", "init", "-q", str(self.tmp)], check=True)
        self.upstream()
        report = self.run_sync()
        subprocess.run([*git, "add", "skills", ".nthplusio-skills"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", "sync"], check=True)
        self.assertIn(f"Upstream cursor/plugins: {report['upstream_commit'][:7]} (unchanged)", self.run_sync("status"))

    def test_an_older_manifest_in_the_skill_directory_moves(self):
        self.upstream()
        skill = self.skills / sync.SELF
        (skill / "manifest.json").write_text(json.dumps({"skills": {}, "exclude": ["beta"]}))
        report = self.run_sync()
        self.assertFalse((skill / "manifest.json").exists())
        self.assertEqual(json.loads((self.durable() / "manifest.json").read_text())["exclude"], ["beta"])
        self.assertNotIn("beta", report["added"])

    def test_a_plain_copy_of_the_skill_keeps_the_install_state(self):
        self.upstream()
        first = self.run_sync()
        self.assertTrue((self.durable() / "manifest.json").is_file())
        self.assertTrue((self.durable() / "transform.json").is_file())
        skill = self.skills / sync.SELF
        shutil.rmtree(skill)
        (skill / "harness").mkdir(parents=True)
        shutil.copy(SKILL / "needs.json", skill / "needs.json")
        shutil.copy(SKILL / "harness" / "TEMPLATE.md", skill / "harness" / "TEMPLATE.md")
        (skill / "transform.json").write_text("{}\n")
        second = self.run_sync()
        self.assertEqual((second["added"], second["removed"]), ([], []))
        self.assertEqual(second["unchanged_count"], len(first["added"]))
        self.assertEqual(json.loads((self.durable() / "manifest.json").read_text())["commit"], first["upstream_commit"])


class HandoffNameTests(unittest.TestCase):
    def test_forms(self):
        text = ("Use the `create-skill` skill, the **tidy** principle skill, `/add-plugin pstack`, Cursor's "
                "built-in babysit skill, and `subagent_type: \"helper\"`. Keep the harness in `/tmp`. "
                "Cursor's built-in for authoring.")
        self.assertEqual(sync.handoff_names(text),
                         {"create-skill", "principle-tidy", "add-plugin", "babysit", "helper"})

    def test_mentions_match_the_forms_renames_rewrite(self):
        text = "Run `/deslop`, `verify`, **beta**, /alpha, and [x](../gamma/SKILL.md); not playbooks/delta.md."
        self.assertEqual(sync.mentions(text), {"deslop", "verify", "beta", "alpha", "gamma"})


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
