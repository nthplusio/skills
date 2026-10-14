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

NEEDS = json.loads((SKILL / "dialects" / "cursor.json").read_text())["needs"] + [
    need for set_file in sorted((SKILL / "sets").glob("*/set.json"))
    for need in json.loads(set_file.read_text()).get("extra_needs", [])]
MAPPED = {need["id"] for need in NEEDS if need.get("discovery")}


def amp_entry():
    """Facts for every discovery field pstack-sync reads, as harness-discovery saves them."""
    return {
        "context": "Orb",
        "owners": {"launch": "Start a thread", "inspect": "Read a thread", "resume": "Message the thread",
                   "workspace_model": "selectable"},
        "helpers": {"invoke": "Task tool", "collect": "Task result", "blocks_caller": True, "readonly": None,
                    "definitions": None},
        "monitoring": {"wake": "A thread schedule"},
        "skills": {"locations": ".agents/skills/ in the project", "reload": "The reload-skills tool",
                   "frontmatter": "name and description; mode is an agent-mode override"},
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
        shutil.copytree(SKILL / "dialects", self.root / "pstack-sync" / "dialects")
        shutil.copytree(SKILL / "sets", self.root / "pstack-sync" / "sets")
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

    def test_modes_and_custom_subagents_are_answered_by_discovery(self):
        state = self.state()
        self.assertEqual(state.facts["modes"], {"skills.frontmatter": "name and description; mode is an agent-mode override"})
        self.assertEqual(state.facts["custom-subagents"], {"helpers.definitions": None})
        self.assertNotIn("modes", state.profile)
        self.assertNotIn("custom-subagents", state.profile)
        self.assertEqual(state.gaps(["modes", "custom-subagents"]), [])
        entry = amp_entry()
        del entry["skills"]["frontmatter"]
        self.save({"Amp": entry})
        self.assertEqual(self.state().gaps(["modes", "custom-subagents"]), ["modes"])

    def test_discovered_needs_need_no_profile_row(self):
        state = self.state()
        self.assertEqual(state.discovery_key, "Amp")
        self.assertEqual(set(state.facts), MAPPED)
        self.assertEqual(state.gaps(MAPPED | {"cursor-product", "companion-skills"}), [])
        self.assertEqual(state.flagged_facts({"subagents", "cursor-product"}),
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
        self.assertEqual(state.gaps({"subagents", "cursor-product"}), ["subagents"])
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
        shutil.copytree(SKILL / "dialects", self.skills / sync.SELF / "dialects")
        shutil.copytree(SKILL / "sets", self.skills / sync.SELF / "sets")
        (self.skills / sync.SELF / "sets" / "pstack" / "transform.json").unlink()
        self.profile(PROFILE)

    def profile(self, text):
        durable = self.shared() / "harness" / "test.md"
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
        return self.skills / ".nthplusio-skills" / "pstack-sync" / "sets" / "pstack"

    def shared(self):
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
        (self.skills / sync.SELF / "sets" / "pstack" / "transform.json").write_text(json.dumps(transforms))
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
        shutil.copytree(SKILL / "dialects", skill / "dialects")
        shutil.copytree(SKILL / "sets", skill / "sets")
        shutil.copy(SKILL / "harness" / "TEMPLATE.md", skill / "harness" / "TEMPLATE.md")
        (skill / "sets" / "pstack" / "transform.json").write_text("{}\n")
        second = self.run_sync()
        self.assertEqual((second["added"], second["removed"]), ([], []))
        self.assertEqual(second["unchanged_count"], len(first["added"]))
        self.assertEqual(json.loads((self.durable() / "manifest.json").read_text())["commit"], first["upstream_commit"])

    def adapt_alpha(self):
        """Install, then edit alpha the way an adaptation does, so record has something to store."""
        self.upstream()
        self.run_sync()
        installed = self.skills / "alpha" / "SKILL.md"
        installed.write_text(installed.read_text().replace("Spawn `Task`", "Spawn a `Task` subagent"))
        return installed

    def transforms(self):
        return json.loads((self.durable() / "transform.json").read_text())["test"]

    def test_record_local_keeps_the_entry_out_of_the_seed(self):
        self.adapt_alpha()
        self.run_sync("record", "--local", "alpha/SKILL.md")
        block = self.transforms()
        self.assertIn("alpha/SKILL.md", block["local"]["files"])
        self.assertNotIn("alpha/SKILL.md", block["files"])
        out = self.tmp / "seed"
        report = self.run_sync("seed", "--out", str(out))
        self.assertEqual(report["seeded"], ["sets/pstack/transform.json", "harness/test.md"])
        self.assertEqual(report["local_entries_kept_back"], ["alpha/SKILL.md"])
        seed = json.loads((out / "sets" / "pstack" / "transform.json").read_text())["test"]
        self.assertNotIn("local", seed)
        self.assertNotIn("alpha/SKILL.md", seed["files"])
        self.assertEqual((out / "harness" / "test.md").read_text(), PROFILE)
        self.assertEqual(sorted(p.name for p in (out / "harness").iterdir()), ["test.md"])

    def test_record_without_local_moves_a_file_back_to_the_shared_block(self):
        self.adapt_alpha()
        self.run_sync("record", "--local", "alpha/SKILL.md")
        self.run_sync("record", "alpha/SKILL.md")
        block = self.transforms()
        self.assertIn("alpha/SKILL.md", block["files"])
        self.assertNotIn("alpha/SKILL.md", block["local"]["files"])

    def test_local_profile_rows_override_shared_rows(self):
        self.upstream()
        self.run_sync()
        flagged = self.run_sync()["needs_adaptation"]["beta"]["SKILL.md"]["needs"]
        self.assertIn("loop", flagged)
        local = self.shared() / "harness" / "test.local.md"
        local.write_text(PROFILE + "| `loop` | keep | the test harness loops as written | local |\n")
        self.assertNotIn("loop", self.run_sync()["needs_adaptation"]["beta"]["SKILL.md"]["needs"])
        out = self.tmp / "seed"
        self.run_sync("seed", "--out", str(out))
        self.assertEqual(sorted(p.name for p in (out / "harness").iterdir()), ["test.md"])
        self.assertNotIn("local", (out / "harness" / "test.md").read_text())

    def test_a_plain_copy_keeps_local_entries(self):
        self.adapt_alpha()
        self.run_sync("record", "--local", "alpha/SKILL.md")
        skill = self.skills / sync.SELF
        shutil.rmtree(skill)
        (skill / "harness").mkdir(parents=True)
        shutil.copytree(SKILL / "dialects", skill / "dialects")
        shutil.copytree(SKILL / "sets", skill / "sets")
        shutil.copy(SKILL / "harness" / "TEMPLATE.md", skill / "harness" / "TEMPLATE.md")
        (skill / "sets" / "pstack" / "transform.json").write_text(json.dumps({"test": {"accept": [], "global": [], "files": {}}}))
        report = self.run_sync()
        self.assertEqual(report["local_drift"], [])
        self.assertNotIn("alpha", report["needs_adaptation"])
        self.assertIn("alpha/SKILL.md", self.transforms()["local"]["files"])

    def set_config(self, name, **changes):
        """Write a second set beside pstack in the test skills directory, from pstack's config."""
        base = json.loads((SKILL / "sets" / "pstack" / "set.json").read_text())
        base.pop("_doc", None)
        cfg = {**base, "agents_dir": f"{name}-agents", "collision_prefix": f"{name}-", "extra_needs": [], **changes}
        d = self.skills / sync.SELF / "sets" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "set.json").write_text(json.dumps(cfg))
        return cfg

    def test_state_moves_under_the_set_directory(self):
        self.upstream()
        first = self.run_sync()
        shared = self.shared()
        for fn in ("manifest.json", "transform.json", *[p.name for p in self.durable().glob("LICENSE-*")]):
            shutil.move(str(self.durable() / fn), str(shared / fn))
        self.durable().rmdir()
        second = self.run_sync()
        self.assertEqual(second["unchanged_count"], len(first["added"]))
        self.assertTrue((self.durable() / "manifest.json").is_file())
        self.assertFalse((shared / "manifest.json").exists())
        self.assertEqual(sorted(p.name for p in shared.iterdir()), ["harness", "sets"])
        self.assertEqual(json.loads((self.durable() / "manifest.json").read_text())["set"], "pstack")

    def test_status_keeps_its_baseline_across_the_state_move(self):
        self.upstream()
        first = self.run_sync()
        git = ["git", "-C", str(self.skills), "-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run(["git", "init", "-q", str(self.skills)], check=True)
        shared = self.shared()
        for fn in ("manifest.json", "transform.json", *[p.name for p in self.durable().glob("LICENSE-*")]):
            shutil.move(str(self.durable() / fn), str(shared / fn))
        self.durable().rmdir()
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", "before sets"], check=True)
        self.run_sync()
        status = self.run_sync("status")
        self.assertIn(f"Upstream cursor/plugins: {first['upstream_commit'][:7]} (unchanged)", status)
        self.assertIn("0 files touched", status)

    def test_seed_takes_the_header_from_the_pack_and_the_rows_from_the_install(self):
        self.upstream()
        self.run_sync()
        seed_profile = self.skills / sync.SELF / "harness" / "test.md"
        seed_profile.write_text("# Harness profile: test\n\nSee [the catalog](../dialects/cursor.json).\n\n" + PROFILE.split("\n\n", 1)[1])
        durable = self.shared() / "harness" / "test.md"
        durable.write_text("# Old header\n\nSee [the catalog](../needs.json).\n\n| Need | Support | test equivalent | Source |\n| --- | --- | --- | --- |\n| `loop` | keep | loops as written | install |\n")
        out = self.tmp / "seed"
        self.run_sync("seed", "--out", str(out))
        text = (out / "harness" / "test.md").read_text()
        self.assertIn("../dialects/cursor.json", text)
        self.assertNotIn("needs.json", text)
        self.assertIn("| `loop` | keep | loops as written | install |", text)

    def test_a_set_from_another_repository_keeps_its_own_upstream_and_ref(self):
        self.upstream()
        self.set_config("elsewhere", upstream="https://example.com/other/plugins", ref="release")
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "sync", "--harness", "test", "--repo", str(self.skills),
                                 "--set", "elsewhere", "--dry-run"],
                                env={**os.environ, "HOME": str(self.tmp), "PSTACK_SYNC_UPSTREAM": (self.tmp / "plugins").as_uri()},
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0, "the fake upstream must not stand in for another repository")
        self.assertIn("example.com/other/plugins", result.stderr + result.stdout)
        sys.path.insert(0, str(SKILL / "scripts"))
        cfg = sync.load_set(str(self.skills), "elsewhere")
        self.assertEqual((cfg["upstream"], cfg["ref"]), ("https://example.com/other/plugins", "release"))
        sync.configure(cfg)
        try:
            self.assertEqual(sync.UPSTREAM, "https://example.com/other/plugins")
        finally:
            sync.configure(sync.load_set(str(SKILL.parent), "pstack"))

    def test_two_sets_share_one_dependency(self):
        self.upstream()
        self.set_config("kit", root_plugin="cursor-team-kit", skills_subdir="cursor-team-kit/skills")
        kit = self.run_sync("sync", "--set", "kit")
        self.assertEqual(sorted(kit["added"]), ["deslop", "unused", "verify"])
        report = self.run_sync()
        self.assertEqual(report["dependencies"]["existing"], ["deslop"], "verify is deslop's own dependency and stays with the set that owns deslop")
        self.assertNotIn("deslop", report["added"])
        self.assertTrue((self.skills / ".nthplusio-skills" / "pstack-sync" / "sets" / "kit" / "manifest.json").is_file())
        self.assertIn("Upstream", self.run_sync("status", "--set", "kit"))

    def test_a_port_installs_its_adapter_and_reports_upstream_changes(self):
        files = {**UPSTREAM, f"{sync.SUBDIR}/alpha/scripts/run.sh": "#!/bin/sh\necho cursor\n"}
        repo = self.upstream(files)
        cfg = json.loads((self.skills / sync.SELF / "sets" / "pstack" / "set.json").read_text())
        cfg["ports"] = [{"name": "runner", "skill": "alpha", "files": ["scripts/run.sh"]}]
        (self.skills / sync.SELF / "sets" / "pstack" / "set.json").write_text(json.dumps(cfg))
        pending = self.run_sync()
        self.assertEqual(pending["ports_pending"], {"runner": ["alpha/scripts/run.sh"]})
        self.assertFalse((self.skills / "alpha" / "scripts" / "run.sh").exists())
        adapter = self.skills / sync.SELF / "adapters" / "test" / "runner" / "scripts" / "run.sh"
        adapter.parent.mkdir(parents=True)
        adapter.write_text("#!/bin/sh\necho test-harness\n")
        installed = self.run_sync()
        self.assertEqual(installed["ports_pending"], {})
        self.assertEqual((self.skills / "alpha" / "scripts" / "run.sh").read_text(), "#!/bin/sh\necho test-harness\n")
        self.assertNotIn("alpha/scripts/run.sh", installed["needs_security_review"])
        (repo / sync.SUBDIR / "alpha" / "scripts" / "run.sh").write_text("#!/bin/sh\necho cursor v2\n")
        git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run([*git, "commit", "-q", "-am", "port moved"], check=True)
        stale = self.run_sync()
        self.assertEqual(stale["stale_ports"], {"runner": ["alpha/scripts/run.sh"]})
        self.assertEqual((self.skills / "alpha" / "scripts" / "run.sh").read_text(), "#!/bin/sh\necho test-harness\n")
        self.assertEqual(self.run_sync()["stale_ports"], {})

    def test_pending_ports_are_reported_and_not_installed(self):
        files = {**UPSTREAM, f"{sync.SUBDIR}/alpha/scripts/run.sh": "#!/bin/sh\necho cursor\n"}
        self.upstream(files)
        cfg = json.loads((self.skills / sync.SELF / "sets" / "pstack" / "set.json").read_text())
        cfg["ports"] = [{"name": "runner", "skill": "alpha", "files": ["scripts/run.sh"]}]
        (self.skills / sync.SELF / "sets" / "pstack" / "set.json").write_text(json.dumps(cfg))
        for _ in range(2):
            report = self.run_sync()
            self.assertEqual(report["ports_pending"], {"runner": ["alpha/scripts/run.sh"]})
            self.assertFalse((self.skills / "alpha" / "scripts" / "run.sh").exists())
            self.assertTrue((self.skills / "alpha" / "SKILL.md").exists())
        self.assertIn("Outstanding", self.run_sync("status"))

    def test_a_set_can_exclude_and_ignore_upstream_files(self):
        files = {**UPSTREAM, f"{sync.SUBDIR}/alpha/scripts/__tests__/x.test.ts": "test\n",
                 f"{sync.SUBDIR}/alpha/scripts/run.sh": "#!/bin/sh\n"}
        self.upstream(files)
        cfg = json.loads((self.skills / sync.SELF / "sets" / "pstack" / "set.json").read_text())
        cfg["exclude"] = ["verify"]
        cfg["ignore"] = ["scripts/__tests__/*"]
        (self.skills / sync.SELF / "sets" / "pstack" / "set.json").write_text(json.dumps(cfg))
        report = self.run_sync()
        self.assertNotIn("verify", report["added"])
        self.assertEqual(report["dependencies"]["excluded"], {"verify": ["deslop/SKILL.md"]})
        self.assertEqual(report["ignored_count"], 1)
        self.assertFalse((self.skills / "alpha" / "scripts" / "__tests__").exists())
        self.assertTrue((self.skills / "alpha" / "scripts" / "run.sh").exists())
        self.assertEqual(json.loads((self.durable() / "manifest.json").read_text())["exclude"], [],
                         "a set's exclude applies without being written into the install's own list")
        cfg["exclude"] = []
        (self.skills / sync.SELF / "sets" / "pstack" / "set.json").write_text(json.dumps(cfg))
        self.assertIn("verify", self.run_sync()["added"], "dropping the set's exclude un-excludes it")

    def test_record_leaves_ignored_local_files_alone(self):
        self.upstream({**UPSTREAM, f"{sync.SUBDIR}/alpha/scripts/run.sh": "#!/bin/sh\n"})
        cfg = json.loads((self.skills / sync.SELF / "sets" / "pstack" / "set.json").read_text())
        cfg["ignore"] = ["scripts/node_modules/**"]
        (self.skills / sync.SELF / "sets" / "pstack" / "set.json").write_text(json.dumps(cfg))
        self.run_sync()
        dep = self.skills / "alpha" / "scripts" / "node_modules" / "dep" / "index.js"
        dep.parent.mkdir(parents=True)
        dep.write_text("module.exports = 1;\n")
        (self.skills / "alpha" / "SKILL.md").write_text(skill("alpha", "Adapted.\n"))
        self.assertEqual(list(self.run_sync("record", "alpha/SKILL.md")["recorded"]), ["alpha"])
        self.assertTrue(dep.exists(), "an installed dependency the set ignores survives record and sync")
        self.assertEqual(self.run_sync()["local_drift"], [])
        self.assertTrue(dep.exists())

    def test_profile_gaps_offer_the_shipped_row(self):
        self.upstream()
        self.run_sync()
        (self.skills / sync.SELF / "harness" / "test.md").write_text(
            PROFILE + "| `loop` | keep | the test harness loops as written | seed |\n")
        report = self.run_sync()
        self.assertIn("loop", report["profile_gaps"])
        self.assertTrue(report["profile_gaps_in_seed"]["loop"].startswith("| `loop` | keep |"))

    def test_a_port_may_add_a_file_upstream_lacks(self):
        self.upstream()
        cfg = json.loads((self.skills / sync.SELF / "sets" / "pstack" / "set.json").read_text())
        cfg["ports"] = [{"name": "runner", "skill": "alpha", "files": ["scripts/runtime.sh"]}]
        (self.skills / sync.SELF / "sets" / "pstack" / "set.json").write_text(json.dumps(cfg))
        adapter = self.skills / sync.SELF / "adapters" / "test" / "runner" / "scripts" / "runtime.sh"
        adapter.parent.mkdir(parents=True)
        adapter.write_text("#!/bin/sh\necho facade\n")
        report = self.run_sync()
        self.assertEqual(report["ports_pending"], {})
        self.assertEqual((self.skills / "alpha" / "scripts" / "runtime.sh").read_text(), "#!/bin/sh\necho facade\n")
        (self.skills / "alpha" / "scripts" / "runtime.sh").unlink()
        second = self.run_sync()
        self.assertTrue((self.skills / "alpha" / "scripts" / "runtime.sh").exists(), "a sync restores a deleted adapter-only file")
        self.assertEqual(second["updated"], ["alpha"])
        self.assertEqual(self.run_sync()["unchanged_count"], len(report["added"]))
        self.run_sync("record", "alpha/SKILL.md")
        self.assertTrue((self.skills / "alpha" / "scripts" / "runtime.sh").exists())

    def test_dialect_and_set_needs_merge(self):
        self.upstream()
        self.run_sync()
        ids = [n["id"] for n in sync.load_needs(str(self.skills))]
        dialect = [n["id"] for n in json.loads((SKILL / "dialects" / "cursor.json").read_text())["needs"]]
        self.assertEqual(ids[:len(dialect)], dialect)
        self.assertIn("role-model-config", ids)
        self.assertNotIn("role-model-config", dialect)


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

    def test_the_cursor_sdk_import_specifier_is_a_marker(self):
        text = 'import type { Run, SDKAgent } from "@cursor/sdk";\n"@cursor/sdk": "^1.0.12"\n'
        self.assertEqual(sync.needs_in(text, NEEDS).get("cursor-sdk"), ["@cursor/sdk"])

    def test_orchestrate_port_interfaces_name_what_installed_files_import(self):
        ports = {p["name"]: p["interface"] for p in json.loads((SKILL / "sets" / "orchestrate" / "set.json").read_text())["ports"]}
        for name in ("AgentManager", "RespawnSource", "appendAgentFooter", "registerTaskCommands",
                     "registerInspectCommands", "registerForensicsCommands", "Run", "SDKAgent", "RunResult"):
            self.assertIn(f"`{name}`", ports["agent-runtime"])
        self.assertIn("`renderModelCatalog`", ports["models"])

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
