"""Run with python3 -B -m unittest discover -s <this directory> -v."""

import datetime
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


def git_repo(path, *files_then_message):
    """A git repository at path with an identity; files written and committed when given."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    for key, value in (("user.name", "t"), ("user.email", "t@example.com")):
        subprocess.run(["git", "-C", str(path), "config", key, value], check=True)
    return path


def commit_all(path, message):
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", message], check=True)
    return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


def build_upstream(tmp, files=UPSTREAM):
    """A small cursor/plugins at tmp/plugins, fetched over file:// by the tests."""
    repo = tmp / "plugins"
    shutil.rmtree(repo, ignore_errors=True)
    for path, text in files.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text)
    git_repo(repo)
    commit_all(repo, "plugins")
    return repo


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
        return build_upstream(self.tmp, files)

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

    def shipped(self, replace, key="alpha/SKILL.md", find=ALPHA_DESLOP):
        """Write the pack's seed for pstack with one file entry."""
        seed = {"test": {"accept": [], "global": [], "files": {key: {"transforms": [{"find": find, "replace": replace}], "accepted": []}}}}
        (self.skills / sync.SELF / "sets" / "pstack" / "transform.json").write_text(json.dumps(seed))
        return seed["test"]

    def seed_json(self):
        return json.loads((self.durable() / "seed.json").read_text())

    def test_seed_refresh_bootstraps_an_install_without_seed_json(self):
        self.upstream()
        self.shipped("Shipped one.\n")
        first = self.run_sync()
        self.assertEqual((first["seed_refreshed"], first["seed_conflicts"]), ([], []), "the first run adopts the seed as is")
        self.assertEqual(self.seed_json()["test"]["files"]["alpha/SKILL.md"]["transforms"][0]["replace"], "Shipped one.\n")
        (self.durable() / "seed.json").unlink()  # an install from before seed.json
        shipped = self.shipped("Shipped two.\n")
        report = self.run_sync()
        self.assertEqual(report["seed_refreshed"], ["alpha/SKILL.md"])
        self.assertEqual(report["seed_conflicts"], [])
        self.assertIn("Shipped two.", (self.skills / "alpha" / "SKILL.md").read_text())
        self.assertEqual(self.transforms()["files"]["alpha/SKILL.md"], shipped["files"]["alpha/SKILL.md"])
        self.assertEqual(self.seed_json()["test"], shipped)
        self.assertEqual(self.run_sync()["seed_refreshed"], [], "a second sync has nothing to refresh")

    def test_seed_refresh_applies_a_shipped_change_to_an_unchanged_key(self):
        self.upstream()
        self.shipped("Shipped one.\n")
        self.run_sync()
        self.shipped("Shipped two.\n")
        report = self.run_sync()
        self.assertEqual(report["seed_refreshed"], ["alpha/SKILL.md"])
        self.assertEqual(report["updated"], ["alpha"])
        self.assertIn("Shipped two.", (self.skills / "alpha" / "SKILL.md").read_text())
        self.assertNotIn("alpha", report["local_drift"])
        self.assertEqual(self.run_sync("status")[:1], "#")

    def test_seed_refresh_keeps_entries_the_install_recorded(self):
        self.upstream()
        self.shipped("Shipped one.\n")
        self.run_sync()
        beta = self.skills / "beta" / "SKILL.md"
        beta.write_text(beta.read_text().replace("Keep it tidy", "Keep it neat").replace("Repeat with", "Loop with"))
        self.run_sync("record", "beta/SKILL.md")
        recorded = self.transforms()["files"]["beta/SKILL.md"]
        self.shipped("Shipped two.\n")
        report = self.run_sync()
        self.assertEqual(report["seed_refreshed"], ["alpha/SKILL.md"])
        self.assertEqual(self.transforms()["files"]["beta/SKILL.md"], recorded, "a key the seed never had stays as recorded")
        self.assertEqual(beta.read_text().count("Loop with"), 1)
        installed = self.skills / "alpha" / "SKILL.md"
        installed.write_text(installed.read_text().replace("Shipped two.", "Mine."))
        self.run_sync("record", "alpha/SKILL.md")
        mine = self.transforms()["files"]["alpha/SKILL.md"]
        report = self.run_sync()
        self.assertEqual((report["seed_refreshed"], report["seed_conflicts"]), ([], []), "a key only the install changed keeps it")
        self.assertEqual(self.transforms()["files"]["alpha/SKILL.md"], mine)
        self.assertIn("Mine.", installed.read_text())

    def test_seed_refresh_keeps_the_durable_entry_when_both_changed_and_reports_it(self):
        self.upstream()
        self.shipped("Shipped one.\n")
        self.run_sync()
        installed = self.skills / "alpha" / "SKILL.md"
        installed.write_text(installed.read_text().replace("Shipped one.", "Mine."))
        self.run_sync("record", "alpha/SKILL.md")
        mine = self.transforms()["files"]["alpha/SKILL.md"]
        shipped = self.shipped("Shipped two.\n")
        report = self.run_sync()
        self.assertEqual(report["seed_conflicts"], ["alpha/SKILL.md"])
        self.assertEqual(report["seed_refreshed"], [])
        self.assertEqual(self.transforms()["files"]["alpha/SKILL.md"], mine)
        self.assertIn("Mine.", installed.read_text())
        self.assertEqual(self.seed_json()["test"], shipped, "the seed moves on so the conflict is reported once")
        self.assertEqual(self.run_sync()["seed_conflicts"], [])
        self.assertIn("alpha/SKILL.md", self.transforms()["local"]["files"] | self.transforms()["files"])

    def test_seed_refresh_never_touches_the_local_block(self):
        self.adapt_alpha()
        self.run_sync("record", "--local", "alpha/SKILL.md")
        local = self.transforms()["local"]
        self.shipped("Shipped.\n", key="beta/SKILL.md", find="Keep it tidy.\n")
        report = self.run_sync()
        self.assertEqual(report["seed_refreshed"], ["beta/SKILL.md"])
        self.assertEqual(self.transforms()["local"], local)
        self.assertNotIn("local", self.seed_json()["test"])
        out = self.tmp / "seed"
        self.run_sync("seed", "--out", str(out))
        self.assertEqual(sorted(p.name for p in (out / "sets" / "pstack").iterdir()), ["transform.json"], "seed --out writes no seed.json")
        self.assertIn("beta/SKILL.md", json.loads((out / "sets" / "pstack" / "transform.json").read_text())["test"]["files"])


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


class PublishTests(unittest.TestCase):
    """publish from a temporary pack checkout into a temporary workspace repository."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name)
        build_upstream(self.tmp)
        self.pack = self.make_pack()
        self.ws = self.make_workspace()
        self.plugins_ws = self.tmp / "workspace-plugins"
        (self.plugins_ws / "unrelated").mkdir(parents=True)
        (self.plugins_ws / "unrelated" / "index.ts").write_text("export default 'keep';\n")
        git_repo(self.plugins_ws)
        commit_all(self.plugins_ws, "init plugins")

    def make_pack(self):
        """Two skills and pstack-sync with the pstack and kit sets, a tracked .gitignore, and
        untracked scratch the copy must not pick up."""
        pack = self.tmp / "pack"
        skills = pack / "skills" / "scoussens-skills"
        (skills / "one").mkdir(parents=True)
        (skills / "one" / "SKILL.md").write_text(skill("one", "One."))
        (skills / "two" / "scripts").mkdir(parents=True)
        (skills / "two" / "SKILL.md").write_text(skill("two", "Two."))
        (skills / "two" / "scripts" / "run.sh").write_text("#!/bin/sh\necho two\n")
        (skills / "two" / "scripts" / "run.sh").chmod(0o755)
        me = skills / sync.SELF
        (me / "harness").mkdir(parents=True)
        (me / "SKILL.md").write_text(skill(sync.SELF, "Sync."))
        shutil.copytree(SKILL / "dialects", me / "dialects")
        (me / "sets" / "pstack").mkdir(parents=True)
        base = json.loads((SKILL / "sets" / "pstack" / "set.json").read_text())
        base.pop("_doc", None)
        (me / "sets" / "pstack" / "set.json").write_text(json.dumps(base))
        (me / "sets" / "kit").mkdir()
        (me / "sets" / "kit" / "set.json").write_text(json.dumps({
            **base, "root_plugin": "cursor-team-kit", "skills_subdir": "cursor-team-kit/skills",
            "agents_dir": "kit-agents", "collision_prefix": "kit-", "extra_needs": []}))
        (me / "harness" / "test.md").write_text(PROFILE + "| `loop` | keep | the test harness loops as written | seed |\n")
        self.plugin_source = me / "adapters" / "test" / "plugin"
        for name in ("orchestrate-bridge", "status-panel"):
            plugin = self.plugin_source / name
            plugin.mkdir(parents=True)
            (plugin / "index.ts").write_text(f"export default '{name}';\n")
        (self.plugin_source / "orchestrate-bridge" / "old.txt").write_text("remove on refresh\n")
        executable = self.plugin_source / "orchestrate-bridge" / "run.sh"
        executable.write_text("#!/bin/sh\necho bridge\n")
        executable.chmod(0o755)
        other = me / "adapters" / "other" / "plugin" / "other-harness"
        other.mkdir(parents=True)
        (other / "index.ts").write_text("export default 'other';\n")
        (pack / ".gitignore").write_text("node_modules/\n*.log\n")
        git_repo(pack)
        subprocess.run(["git", "-C", str(pack), "remote", "add", "origin", "https://github.com/nthplusio/skills.git"], check=True)
        commit_all(pack, "pack")
        (skills / "one" / "node_modules" / "dep").mkdir(parents=True)
        (skills / "one" / "node_modules" / "dep" / "index.js").write_text("module.exports = 1;\n")
        (skills / "one" / "scratch.txt").write_text("untracked\n")
        (skills / "one" / "debug.log").write_text("ignored\n")
        plugin = self.plugin_source / "orchestrate-bridge"
        (plugin / "node_modules").mkdir()
        (plugin / "node_modules" / "scratch.js").write_text("ignored dependency\n")
        (plugin / "scratch.txt").write_text("untracked\n")
        (plugin / "debug.log").write_text("ignored\n")
        return pack

    def make_workspace(self, manifest_skills=None, extra=()):
        """A workspace with a stale copy of `one`, a durable profile without the seed's loop row,
        and optionally a previous pack manifest plus extra skill directories."""
        ws = self.tmp / "ws"
        (ws / "one").mkdir(parents=True)
        (ws / "one" / "SKILL.md").write_text(skill("one", "Old one."))
        (ws / "one" / "old.md").write_text("gone after the copy\n")
        profile = ws / ".nthplusio-skills" / sync.SELF / "harness" / "test.md"
        profile.parent.mkdir(parents=True)
        profile.write_text(PROFILE)
        if manifest_skills is not None:
            (ws / ".nthplusio-skills" / "pack-manifest.json").write_text(json.dumps(
                {"pack_commit": "0" * 40, "pack_remote": None, "published_at": "2026-01-01T00:00:00+00:00",
                 "skills": manifest_skills}))
        for name in extra:
            (ws / name).mkdir()
            (ws / name / "SKILL.md").write_text(skill(name, f"{name}."))
        git_repo(ws)
        commit_all(ws, "init")
        return ws

    def publish(self, *args, ok=True, env=None):
        env = {**os.environ, "HOME": str(self.tmp), "PSTACK_SYNC_UPSTREAM": (self.tmp / "plugins").as_uri(), **(env or {})}
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "publish", "--harness", "test",
                                 "--pack", str(self.pack), "--repo", str(self.ws), *args],
                                env=env, capture_output=True, text=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result.returncode, (json.loads(result.stdout) if result.stdout else None), result.stderr

    def git(self, *args, repo=None):
        return subprocess.run(["git", "-C", str(repo or self.ws), *args], capture_output=True, text=True, check=True).stdout

    def destination_state(self):
        return {str(repo): [self.git(*args, repo=repo) for args in (
            ("rev-parse", "HEAD"), ("status", "--porcelain", "--untracked-files=all"),
            ("diff",), ("diff", "--cached"), ("worktree", "list", "--porcelain"))]
            for repo in (self.ws, self.plugins_ws)}

    def test_publish_copies_tracked_files_runs_every_set_and_commits(self):
        head = self.git("rev-parse", "HEAD").strip()
        _, report, _ = self.publish()
        self.assertEqual(report["skills"]["added"], [sync.SELF, "two"])
        self.assertEqual(report["skills"]["updated"], ["one"])
        self.assertEqual((self.ws / "one" / "SKILL.md").read_text(), skill("one", "One."))
        self.assertFalse((self.ws / "one" / "old.md").exists(), "the directory is replaced, not merged")
        self.assertFalse((self.ws / "one" / "node_modules").exists(), "an untracked node_modules is not copied")
        self.assertFalse((self.ws / "one" / "scratch.txt").exists(), "untracked scratch is not copied")
        self.assertFalse((self.ws / "one" / "debug.log").exists(), "a file the pack ignores is not copied")
        self.assertTrue(os.access(self.ws / "two" / "scripts" / "run.sh", os.X_OK), "the executable bit survives")
        self.assertEqual(list(report["sets"]), ["kit", "pstack"], "sets run in name order")
        self.assertEqual(sorted(report["sets"]["kit"]["added"]), ["deslop", "unused", "verify"])
        self.assertIn("alpha", report["sets"]["pstack"]["added"])
        self.assertEqual(report["profile_rows_appended"], {"pstack": ["loop"]})
        self.assertNotIn("loop", report["sets"]["pstack"]["profile_gaps"], "the set is synced again after the row lands")
        self.assertEqual(report["sets"]["pstack"]["profile_gaps_in_seed"], {}, "nothing the seed offers is left to append")
        profile = (self.ws / ".nthplusio-skills" / sync.SELF / "harness" / "test.md").read_text()
        self.assertIn("| `loop` | keep | the test harness loops as written | seed |", profile)
        self.assertNotIn("loop", report["sets"]["pstack"]["needs_adaptation"].get("beta", {}).get("SKILL.md", {}).get("needs", {}))
        self.assertIn("pstack: 2 needs adaptation", report["attention"])
        manifest = json.loads((self.ws / ".nthplusio-skills" / "pack-manifest.json").read_text())
        pack_head = subprocess.run(["git", "-C", str(self.pack), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        self.assertEqual(manifest["pack_commit"], pack_head)
        self.assertEqual(manifest["pack_remote"], "https://github.com/nthplusio/skills.git")
        self.assertEqual(manifest["skills"], ["one", sync.SELF, "two"])
        self.assertEqual(manifest, report["manifest"])
        datetime.datetime.fromisoformat(manifest["published_at"])
        self.assertEqual(report["committed"], self.git("rev-parse", "HEAD").strip())
        self.assertNotEqual(report["committed"], head)
        self.assertEqual(self.git("status", "--porcelain"), "")
        message = self.git("log", "-1", "--format=%B")
        self.assertTrue(message.startswith(f"Refresh workspace skills from nthplusio/skills@{pack_head[:7]}"), message)
        self.assertIn("Added: pstack-sync, two\nUpdated: one\nRemoved: none\n", message)
        self.assertIn("Set kit: cursor/plugins@", message)
        self.assertIn("Set pstack: cursor/plugins@", message)
        self.assertIsNone(report["pushed"])
        self.assertEqual(report["plugins"], {
            "clone": None, "carried": ["orchestrate-bridge", "status-panel"], "status": "not published",
            "added": [], "updated": [], "removed": [], "unchanged_count": 0,
            "committed": None, "pushed": None, "verify": None, "refused": None})
        self.assertFalse((self.ws / "orchestrate-bridge").exists())
        _, again, _ = self.publish()
        self.assertEqual((again["committed"], again["staged_files"], again["skills"]["unchanged_count"]), (None, 0, 3))
        self.assertEqual(again["profile_rows_appended"], {})

    def test_publish_removes_only_the_retired_skills_the_manifest_names(self):
        shutil.rmtree(self.ws)
        self.ws = self.make_workspace(manifest_skills=["gone", "one", sync.SELF, "two"], extra=["gone", "keeper"])
        _, report, _ = self.publish()
        self.assertEqual(report["skills"]["removed"], ["gone"])
        self.assertFalse((self.ws / "gone").exists())
        self.assertTrue((self.ws / "keeper" / "SKILL.md").exists(), "a directory the manifest does not name stays")
        self.assertIn("Removed: gone\n", self.git("log", "-1", "--format=%B"))
        self.assertEqual(json.loads((self.ws / ".nthplusio-skills" / "pack-manifest.json").read_text())["skills"],
                         ["one", sync.SELF, "two"])

    def test_publish_refuses_a_file_over_two_megabytes(self):
        big = self.pack / "skills" / "scoussens-skills" / "two" / "assets" / "big.bin"
        big.parent.mkdir()
        big.write_bytes(b"0" * (3 * 1024 * 1024))
        commit_all(self.pack, "big")
        head = self.git("rev-parse", "HEAD").strip()
        code, report, err = self.publish(ok=False)
        self.assertEqual(code, 2, err)
        self.assertEqual([o["path"] for o in report["refused"]["oversized"]], ["two/assets/big.bin"])
        self.assertEqual(report["refused"]["node_modules"], [])
        self.assertIsNone(report["committed"])
        self.assertIn("two/assets/big.bin", err)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), head, "nothing is committed")
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "", "nothing is left staged")

    def test_publish_refuses_a_node_modules_directory_a_set_would_add(self):
        build_upstream(self.tmp, {**UPSTREAM, f"{sync.SUBDIR}/alpha/scripts/node_modules/dep/index.js": "module.exports = 1;\n"})
        head = self.git("rev-parse", "HEAD").strip()
        code, report, err = self.publish(ok=False)
        self.assertEqual(code, 2, err)
        self.assertEqual(report["refused"]["node_modules"], ["alpha/scripts/node_modules/dep/index.js"])
        self.assertIn("alpha/scripts/node_modules/dep/index.js", err)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), head)

    def test_publish_refuses_a_dirty_workspace(self):
        (self.ws / "stray.txt").write_text("not committed\n")
        code, report, err = self.publish(ok=False)
        self.assertEqual(code, 2)
        self.assertIn("uncommitted changes", err)
        self.assertIn("stray.txt", err)

    def test_dry_run_reports_the_change_and_leaves_the_repository_untouched(self):
        head = self.git("rev-parse", "HEAD").strip()
        _, report, _ = self.publish("--dry-run")
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["skills"]["added"], [sync.SELF, "two"])
        self.assertEqual(report["skills"]["updated"], ["one"])
        self.assertEqual(list(report["sets"]), ["kit", "pstack"])
        self.assertEqual(report["profile_rows_appended"], {"pstack": ["loop"]})
        self.assertGreater(report["staged_files"], 0)
        self.assertTrue(report["commit_message"].startswith("Refresh workspace skills from nthplusio/skills@"))
        self.assertEqual(report["manifest"]["skills"], ["one", sync.SELF, "two"])
        self.assertIsNone(report["committed"])
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), head)
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual((self.ws / "one" / "SKILL.md").read_text(), skill("one", "Old one."))
        self.assertTrue((self.ws / "one" / "old.md").exists())
        self.assertFalse((self.ws / "two").exists())
        self.assertFalse((self.ws / ".nthplusio-skills" / "pack-manifest.json").exists())
        self.assertEqual(len(self.git("worktree", "list").splitlines()), 1, "the throwaway worktree is gone")

    def test_publish_reports_a_seed_conflict_under_attention(self):
        entry = lambda replace: {"transforms": [{"find": ALPHA_DESLOP, "replace": replace}], "accepted": []}
        pack_seed = self.pack / "skills" / "scoussens-skills" / sync.SELF / "sets" / "pstack" / "transform.json"
        pack_seed.write_text(json.dumps({"test": {"accept": [], "global": [], "files": {"alpha/SKILL.md": entry("Shipped two.\n")}}}))
        commit_all(self.pack, "seed")
        durable = self.ws / ".nthplusio-skills" / sync.SELF / "sets" / "pstack"
        durable.mkdir(parents=True)
        (durable / "transform.json").write_text(json.dumps({"test": {"accept": [], "global": [], "files": {"alpha/SKILL.md": entry("Mine.\n")},
                                                                      "local": {"accept": [], "global": [], "files": {}}}}))
        (durable / "seed.json").write_text(json.dumps({"test": {"accept": [], "global": [], "files": {"alpha/SKILL.md": entry("Shipped one.\n")}}}))
        commit_all(self.ws, "state")
        _, report, _ = self.publish()
        self.assertEqual(report["sets"]["pstack"]["seed_conflicts"], ["alpha/SKILL.md"])
        self.assertIn("pstack: 1 seed conflicts", report["attention"])
        self.assertIn("Mine.", (self.ws / "alpha" / "SKILL.md").read_text())
        self.assertEqual(json.loads((durable / "seed.json").read_text())["test"]["files"]["alpha/SKILL.md"], entry("Shipped two.\n"))

    def test_verify_reports_each_skill_or_that_amp_is_absent(self):
        env_path = self.tmp / "bin"
        env_path.mkdir()
        fake = env_path / "amp"
        fake.write_text("#!/bin/sh\n[ \"$1\" = skill ] && [ \"$2\" = info ] || exit 3\n"
                        "case \"$3\" in one|deslop) echo \"Skill: $3\";; *) echo \"Skill \\\"$3\\\" not found.\" >&2; exit 1;; esac\n")
        fake.chmod(0o755)
        env = {**os.environ, "HOME": str(self.tmp), "PSTACK_SYNC_UPSTREAM": (self.tmp / "plugins").as_uri()}
        command = [sys.executable, "-B", str(SCRIPT), "publish", "--harness", "test", "--pack", str(self.pack),
                   "--repo", str(self.ws), "--verify"]
        result = subprocess.run(command, env={**env, "PATH": f"{env_path}:{env['PATH']}"}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        verify = json.loads(result.stdout)["verify"]
        self.assertEqual(verify["amp"], str(fake))
        self.assertEqual({n: v["status"] for n, v in verify["skills"].items()},
                         {"one": "found", "deslop": "found", "alpha": "missing"})
        self.assertEqual({n: v["source"] for n, v in verify["skills"].items()},
                         {"one": "pack", "deslop": "kit", "alpha": "pstack"})
        without = self.tmp / "bin-without-amp"
        without.mkdir()
        (without / "git").symlink_to(shutil.which("git"))
        result = subprocess.run(command, env={**env, "PATH": str(without)}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        verify = json.loads(result.stdout)["verify"]
        self.assertIsNone(verify["amp"])
        self.assertIn("not on PATH", verify["note"])

    def test_publish_plugins_copies_tracks_manifest_commits_and_is_idempotent(self):
        before = self.destination_state()
        _, preview, _ = self.publish("--plugins-repo", str(self.plugins_ws), "--dry-run")
        self.assertEqual(preview["plugins"]["added"], ["orchestrate-bridge", "status-panel"])
        self.assertIsNone(preview["plugins"]["committed"])
        self.assertEqual(self.destination_state(), before)
        _, report, _ = self.publish("--plugins-repo", str(self.plugins_ws))
        plugins = report["plugins"]
        self.assertEqual(plugins["clone"], str(self.plugins_ws))
        self.assertEqual(plugins["carried"], ["orchestrate-bridge", "status-panel"])
        self.assertEqual(plugins["added"], ["orchestrate-bridge", "status-panel"])
        self.assertEqual((plugins["updated"], plugins["removed"], plugins["unchanged_count"]), ([], [], 0))
        self.assertEqual(plugins["status"], "published")
        self.assertEqual((self.plugins_ws / "orchestrate-bridge" / "index.ts").read_text(),
                         "export default 'orchestrate-bridge';\n")
        self.assertTrue(os.access(self.plugins_ws / "orchestrate-bridge" / "run.sh", os.X_OK))
        self.assertEqual(sorted(p.name for p in (self.plugins_ws / "orchestrate-bridge").iterdir()),
                         ["index.ts", "old.txt", "run.sh"])
        self.assertEqual((self.plugins_ws / "unrelated" / "index.ts").read_text(), "export default 'keep';\n")
        manifest_path = self.plugins_ws / ".nthplusio-skills" / "pack-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        pack_head = self.git("rev-parse", "HEAD", repo=self.pack).strip()
        self.assertEqual(manifest["plugins"], ["orchestrate-bridge", "status-panel"])
        self.assertEqual(manifest["pack_commit"], pack_head)
        self.assertEqual(manifest["pack_remote"], "https://github.com/nthplusio/skills.git")
        self.assertNotIn("skills", manifest)
        self.assertEqual(plugins["committed"], self.git("rev-parse", "HEAD", repo=self.plugins_ws).strip())
        self.assertEqual(self.git("log", "-1", "--format=%s", repo=self.plugins_ws).strip(),
                         f"Refresh workspace plugins from nthplusio/skills@{pack_head[:7]}")
        self.assertEqual(self.git("status", "--porcelain", repo=self.plugins_ws), "")
        self.assertIsNone(plugins["pushed"])
        before = self.destination_state()
        _, again, _ = self.publish("--plugins-repo", str(self.plugins_ws))
        self.assertEqual(again["plugins"]["unchanged_count"], 2)
        self.assertEqual(again["plugins"]["added"], [])
        self.assertIsNone(again["plugins"]["committed"])
        self.assertEqual(json.loads(manifest_path.read_text()), manifest)
        self.assertEqual(self.destination_state(), before)
        executable = self.plugin_source / "orchestrate-bridge" / "run.sh"
        executable.chmod(0o644)
        self.git("add", str(executable), repo=self.pack)
        self.git("commit", "-qm", "remove executable bit", repo=self.pack)
        _, changed, _ = self.publish("--plugins-repo", str(self.plugins_ws))
        self.assertEqual(changed["plugins"]["updated"], ["orchestrate-bridge"])
        self.assertEqual(changed["plugins"]["unchanged_count"], 1)
        self.assertFalse(os.access(self.plugins_ws / "orchestrate-bridge" / "run.sh", os.X_OK))

    def test_publish_plugins_replaces_files_and_removes_only_manifest_names(self):
        self.publish("--plugins-repo", str(self.plugins_ws))
        (self.plugin_source / "orchestrate-bridge" / "old.txt").unlink()
        (self.plugin_source / "orchestrate-bridge" / "index.ts").write_text("export default 'new';\n")
        shutil.rmtree(self.plugin_source / "status-panel")
        commit_all(self.pack, "refresh plugins")
        _, report, _ = self.publish("--plugins-repo", str(self.plugins_ws))
        plugins = report["plugins"]
        self.assertEqual((plugins["added"], plugins["updated"], plugins["removed"]),
                         ([], ["orchestrate-bridge"], ["status-panel"]))
        self.assertEqual((self.plugins_ws / "orchestrate-bridge" / "index.ts").read_text(), "export default 'new';\n")
        self.assertFalse((self.plugins_ws / "orchestrate-bridge" / "old.txt").exists())
        self.assertFalse((self.plugins_ws / "status-panel").exists())
        self.assertEqual((self.plugins_ws / "unrelated" / "index.ts").read_text(), "export default 'keep';\n")
        manifest = json.loads((self.plugins_ws / ".nthplusio-skills" / "pack-manifest.json").read_text())
        self.assertEqual(manifest["plugins"], ["orchestrate-bridge"])
        self.assertEqual(manifest["pack_commit"], self.git("rev-parse", "HEAD", repo=self.pack).strip())

    def test_publish_plugins_can_retire_the_last_carried_plugins(self):
        self.publish("--plugins-repo", str(self.plugins_ws))
        shutil.rmtree(self.plugin_source)
        commit_all(self.pack, "retire plugins")
        _, report, _ = self.publish("--plugins-repo", str(self.plugins_ws))
        self.assertEqual(report["plugins"]["removed"], ["orchestrate-bridge", "status-panel"])
        self.assertEqual(report["plugins"]["carried"], [])
        self.assertEqual(sorted(p.name for p in self.plugins_ws.iterdir()), [".git", ".nthplusio-skills", "unrelated"])
        self.assertEqual(json.loads((self.plugins_ws / ".nthplusio-skills" / "pack-manifest.json").read_text())["plugins"], [])

    def test_publish_plugins_refuses_tracked_node_modules_before_changing_either_clone(self):
        path = self.plugin_source / "orchestrate-bridge" / "node_modules" / "scratch.js"
        self.git("add", "-f", str(path), repo=self.pack)
        self.git("commit", "-qm", "track dependency", repo=self.pack)
        before = self.destination_state()
        for flags in ((), ("--dry-run",)):
            with self.subTest(flags=flags):
                code, report, err = self.publish("--plugins-repo", str(self.plugins_ws), *flags, ok=False)
                self.assertEqual(code, 2, err)
                self.assertEqual(report["plugins"]["refused"]["node_modules"], ["orchestrate-bridge/node_modules/scratch.js"])
                self.assertIn("orchestrate-bridge/node_modules/scratch.js", err)
                self.assertEqual(self.destination_state(), before)

    def test_publish_plugins_enforces_the_exact_file_size_boundary(self):
        path = self.plugin_source / "status-panel" / "large.bin"
        path.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
        commit_all(self.pack, "oversized plugin")
        before = self.destination_state()
        code, report, err = self.publish("--plugins-repo", str(self.plugins_ws), ok=False)
        self.assertEqual(code, 2, err)
        self.assertEqual(report["plugins"]["refused"]["oversized"], [{"path": "status-panel/large.bin", "bytes": 2097153}])
        self.assertEqual(self.destination_state(), before)
        path.write_bytes(b"x" * (2 * 1024 * 1024))
        commit_all(self.pack, "at size limit")
        self.publish("--plugins-repo", str(self.plugins_ws))
        self.assertEqual((self.plugins_ws / "status-panel" / "large.bin").read_bytes(), b"x" * 2097152)

    def test_publish_preflights_both_destinations(self):
        for repo in (self.ws, self.plugins_ws):
            with self.subTest(repo=repo):
                stray = repo / "stray.txt"
                stray.write_text("dirty\n")
                before = self.destination_state()
                code, _, err = self.publish("--plugins-repo", str(self.plugins_ws), ok=False)
                self.assertEqual(code, 2, err)
                self.assertIn("uncommitted changes", err)
                self.assertEqual(self.destination_state(), before)
                stray.unlink()
        invalid = self.tmp / "not-a-clone"
        invalid.mkdir()
        unborn = self.tmp / "unborn"
        git_repo(unborn)
        for path in (invalid, self.tmp / "missing-clone", unborn):
            before = self.destination_state()
            code, _, err = self.publish("--plugins-repo", str(path), ok=False)
            self.assertEqual(code, 2, err)
            self.assertEqual(self.destination_state(), before)

    def test_plugin_preflight_rejects_unsafe_manifest_names_and_symlink_destinations(self):
        manifest = self.plugins_ws / ".nthplusio-skills" / "pack-manifest.json"
        manifest.parent.mkdir()
        for name in ("../ws", ".nthplusio-skills"):
            manifest.write_text(json.dumps({"plugins": [name]}))
            commit_all(self.plugins_ws, "invalid removal target")
            before = self.destination_state()
            code, _, err = self.publish("--plugins-repo", str(self.plugins_ws), ok=False)
            self.assertEqual(code, 2, err)
            self.assertIn("unsafe plugin name", err)
            self.assertEqual(self.destination_state(), before)
        manifest.write_text(json.dumps({"plugins": []}))
        (self.plugins_ws / "orchestrate-bridge").symlink_to(self.plugins_ws / "unrelated", target_is_directory=True)
        commit_all(self.plugins_ws, "aliased plugin")
        before = self.destination_state()
        for flags in ((), ("--dry-run",)):
            code, _, err = self.publish("--plugins-repo", str(self.plugins_ws), *flags, ok=False)
            self.assertEqual(code, 2, err)
            self.assertIn("must be a regular directory", err)
            self.assertEqual(self.destination_state(), before)

    def test_publish_refuses_overlapping_destinations_including_symlink_aliases(self):
        alias = self.tmp / "alias"
        alias.symlink_to(self.ws, target_is_directory=True)
        for path in (self.ws, self.ws / "nested", self.tmp, alias, self.pack):
            before = self.destination_state()
            code, _, err = self.publish("--plugins-repo", str(path), "--dry-run", ok=False)
            self.assertEqual(code, 2, err)
            self.assertIn("overlap", err)
            self.assertEqual(self.destination_state(), before)

    def test_plugin_dry_run_uses_destination_heads_and_cleans_worktrees_on_success_and_refusal(self):
        self.publish("--plugins-repo", str(self.plugins_ws))
        (self.plugins_ws / "orchestrate-bridge" / "index.ts").write_text("uncommitted plugin\n")
        (self.plugins_ws / ".nthplusio-skills" / "pack-manifest.json").write_text("invalid dirty manifest\n")
        (self.ws / "one" / "SKILL.md").write_text("uncommitted skill\n")
        self.git("add", "one/SKILL.md")
        before = self.destination_state()
        _, report, _ = self.publish("--plugins-repo", str(self.plugins_ws), "--dry-run", "--push")
        self.assertEqual(report["plugins"]["unchanged_count"], 2)
        self.assertEqual(report["plugins"]["updated"], [])
        self.assertEqual(report["plugins"]["status"], "dry run")
        self.assertIsNone(report["plugins"]["committed"])
        self.assertIsNone(report["plugins"]["pushed"])
        self.assertIsNone(report["pushed"])
        self.assertEqual(self.destination_state(), before)
        build_upstream(self.tmp, {**UPSTREAM, f"{sync.SUBDIR}/alpha/node_modules/index.js": "bad\n"})
        code, report, err = self.publish("--plugins-repo", str(self.plugins_ws), "--dry-run", ok=False)
        self.assertEqual(code, 2, err)
        self.assertEqual(report["refused"]["node_modules"], ["alpha/node_modules/index.js"])
        self.assertEqual(self.destination_state(), before)

    def test_plugin_dry_run_cleans_worktrees_when_sync_fails(self):
        config = self.pack / "skills" / "scoussens-skills" / sync.SELF / "sets" / "kit" / "set.json"
        config.write_text("invalid JSON\n")
        commit_all(self.pack, "broken set")
        before = self.destination_state()
        code, _, err = self.publish("--plugins-repo", str(self.plugins_ws), "--dry-run", ok=False)
        self.assertNotEqual(code, 0, err)
        self.assertEqual(self.destination_state(), before)

    def test_push_publishes_both_repositories_to_disposable_local_remotes(self):
        remotes = {}
        for repo in (self.ws, self.plugins_ws):
            remote = self.tmp / f"{repo.name}.git"
            subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
            self.git("remote", "add", "origin", str(remote), repo=repo)
            remotes[repo] = remote
        _, report, _ = self.publish("--plugins-repo", str(self.plugins_ws), "--push")
        for repo, summary in ((self.ws, report), (self.plugins_ws, report["plugins"])):
            self.assertEqual(summary["pushed"], self.git("branch", "--show-current", repo=repo).strip())
            remote_head = self.git("rev-parse", f"refs/heads/{summary['pushed']}", repo=remotes[repo]).strip()
            self.assertEqual(remote_head, summary["committed"])
            self.assertEqual(remote_head, self.git("rev-parse", "HEAD", repo=repo).strip())

    def test_plugin_verification_matches_only_exact_workspace_headers_once(self):
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "amp"
        calls = self.tmp / "plugin-list-calls"
        headers = self.tmp / "plugin-list-output"
        fake.write_text(f'#!/bin/sh\nif [ "$1 $2" = "plugins list" ]; then\n'
                        f'  echo list >> "{calls}"\n  cat "{headers}"\nelse\n  echo "Skill: $3"\nfi\n')
        fake.chmod(0o755)
        headers.write_text("✓ orchestrate-bridge (Workspace Plugins) active\n"
                           "  tools: status-panel active\n"
                           "○ status-panel (Workspace Plugins) disabled\n")
        _, report, _ = self.publish("--plugins-repo", str(self.plugins_ws), "--verify",
                                    env={"PATH": f"{bin_dir}:{os.environ['PATH']}"})
        self.assertEqual(report["plugins"]["verify"]["plugins"],
                         {"orchestrate-bridge": {"status": "active"}, "status-panel": {"status": "disabled"}})
        self.assertEqual(calls.read_text(), "list\n")
        headers.write_text("✓ orchestrate-bridge-extra (Workspace Plugins) active\n"
                           "  ✓ orchestrate-bridge (Workspace Plugins) active\n"
                           "✓ status-panel (User Plugins) active\n")
        _, report, _ = self.publish("--plugins-repo", str(self.plugins_ws), "--verify",
                                    env={"PATH": f"{bin_dir}:{os.environ['PATH']}"})
        self.assertEqual(report["plugins"]["verify"]["plugins"],
                         {"orchestrate-bridge": {"status": "missing"}, "status-panel": {"status": "missing"}})
        self.assertEqual(calls.read_text(), "list\nlist\n")
        without = self.tmp / "without-amp"
        without.mkdir()
        (without / "git").symlink_to(shutil.which("git"))
        _, report, _ = self.publish("--plugins-repo", str(self.plugins_ws), "--verify", env={"PATH": str(without)})
        self.assertIsNone(report["plugins"]["verify"]["amp"])
        self.assertIn("not on PATH", report["plugins"]["verify"]["note"])
        self.assertEqual(report["plugins"]["verify"]["plugins"], {})


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
