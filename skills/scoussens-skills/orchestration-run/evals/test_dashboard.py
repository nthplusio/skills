"""Run with python3 -B -m unittest discover -s <this directory> -v."""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


RUNNER = Path(__file__).resolve().parent.parent
SETUP = RUNNER.parent / "orchestration-setup"
DISCOVERY = RUNNER.parent / "harness-discovery"
DASHBOARD = RUNNER.parent / "dashboard"
PREVIEW = DASHBOARD / "evals" / "dashboard-preview.json"
sys.path.insert(0, str(RUNNER / "scripts"))
sys.path.insert(0, str(DASHBOARD / "scripts"))
from render_dashboard import render
from validate_run import notes, skill_version, validate


class LifecycleTests(unittest.TestCase):
    """The run record's own rules, checked by validate_run.py before the dashboard skill renders:
    proof behind claims, settled scope, publication scope, durable code, runtime, approvals,
    idle scans, history length and a clean closed run."""

    def setUp(self):
        self.data = json.loads(PREVIEW.read_text())
        self.data["skill_version"] = skill_version()
        self.tasks = {task["id"]: task for task in self.data["tasks"]}

    def test_the_preview_record_passes_and_the_cli_reports_each_finding(self):
        validate(self.data)
        with tempfile.TemporaryDirectory() as directory:
            status = Path(directory) / "status.json"
            status.write_text(json.dumps(self.data))
            command = [sys.executable, "-B", str(RUNNER / "scripts" / "validate_run.py"), str(status)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PASS", result.stdout)
            self.data["approvals"][1]["state"] = "active"
            self.data["history"].append("x" * 801)
            status.write_text(json.dumps(self.data))
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn("FAIL: A2: approval expired", result.stderr)
            self.assertIn("FAIL: history entries [5] exceed 800 characters", result.stderr)
            # The renderer alone accepts the same record: the rule is the coordinator's, not the page's.
            self.assertIn("<b>A2</b> Active", render(self.data))

    def test_schema_1_records_pass_without_lifecycle_fields(self):
        self.data["schema_version"] = 1
        self.data.pop("approvals")
        self.data.pop("skill_version")
        self.data["extra_notes"] = "legacy field"
        for task in self.data["tasks"]:
            task.pop("runtime")
        validate(self.data)
        self.data["tasks"][2]["milestones"]["pr_readiness"]["state"] = "verified"
        with self.assertRaisesRegex(ValueError, "accepted supporting proof"):
            validate(self.data)

    def test_run_choices_name_target_stage_publication_scope_and_idle_limit(self):
        for field, value, message in (("target_stage", "review-ready PRs", "target_stage must name a business stage"),
                                      ("publication_scope", "push", "publication_scope must be one of"),
                                      ("idle_scan_limit", 0, "idle_scan_limit must be a positive integer"),
                                      ("confirmed_from", "", "confirmed_from must be nonempty")):
            with self.subTest(field=field):
                data = deepcopy(self.data)
                data["run_choices"][field] = value
                with self.assertRaisesRegex(ValueError, message):
                    validate(data)
        del self.data["config_path"]
        with self.assertRaisesRegex(ValueError, "config_path must be nonempty"):
            validate(self.data)

    def test_publication_request_needs_a_publication_scope(self):
        self.data["run_choices"]["publication_scope"] = "none"
        with self.assertRaisesRegex(ValueError, "OPS-105: code publication is requested but this run's publication scope is none"):
            validate(self.data)

    def test_green_job_cannot_be_used_as_verified_review_proof(self):
        self.data["tasks"][2]["milestones"]["pr_readiness"]["state"] = "verified"
        with self.assertRaisesRegex(ValueError, "REVIEW-103: verified stage needs accepted supporting proof"):
            validate(self.data)

    def test_missing_and_superseded_proof_do_not_mark_verified(self):
        phase = self.data["tasks"][0]["milestones"]["pr_readiness"]
        for proofs, expected in (([], "accepted supporting proof"), (["missing"], "missing proof"), (["E5"], "accepted supporting proof")):
            with self.subTest(proofs=proofs):
                phase["evidence"] = proofs
                with self.assertRaisesRegex(ValueError, expected):
                    validate(self.data)

    def test_resolutions_require_proof_or_decisions_and_settled_scope(self):
        baseline = deepcopy(self.data)
        cases = [
            ("UI-101", "work", "evidence", [], "accepted supporting proof"),
            ("TRIAGE-108", "work", "evidence", ["E4"], "accepted supporting proof"),
            ("TRIAGE-108", "work", "evidence", ["missing"], "accepted supporting proof"),
            ("UI-109", "work", "receipt", "", "decision receipt"),
            ("UI-110", "work", "receipt", "", "decision receipt"),
            ("UI-110", "work", "revisit", "", "revisit trigger"),
            ("UI-109", None, "obligations", ["Release runtime"], "settled obligations"),
            ("UI-110", None, "blocker", "Approval missing", "settled obligations"),
            ("UI-109", "work", "reason", "", "work needs a reason"),
        ]
        for ticket, section, field, value, message in cases:
            with self.subTest(ticket=ticket, field=field):
                self.data = deepcopy(baseline)
                task = next(task for task in self.data["tasks"] if task["id"] == ticket)
                (task[section] if section else task)[field] = value
                with self.assertRaisesRegex(ValueError, message):
                    validate(self.data)
        self.data = deepcopy(baseline)
        task = self.data["tasks"][8]
        task["owner"]["state"] = "active"
        task["milestones"]["pr_readiness"]["state"] = "pending"
        with self.assertRaisesRegex(ValueError, "unfinished stage prevents work resolution"):
            validate(self.data)

    def test_attention_states_name_what_holds_them(self):
        task = self.data["tasks"][1]
        task["owner"]["state"] = "waiting"
        task["work"] = {"state": "blocked", "reason": "Next inspection must confirm the result."}
        with self.assertRaisesRegex(ValueError, "API-102: blocked work needs an actionable blocker"):
            validate(self.data)
        task["work"]["state"] = "needs_decision"
        with self.assertRaisesRegex(ValueError, "pending decision"):
            validate(self.data)
        task["work"]["state"] = "working"
        task["owner"].update(state="complete", handoff="Retained")
        with self.assertRaisesRegex(ValueError, "unfinished work prevents owner completion"):
            validate(self.data)
        task = self.data["tasks"][5]
        task["blocker"] = ""
        task["work"] = {"state": "waiting", "reason": "Lane is held."}
        with self.assertRaisesRegex(ValueError, "ENV-106: blocked owner needs an actionable blocker"):
            validate(self.data)

    def test_pending_obligation_blocks_owner_closure_even_with_green_milestones(self):
        task = self.data["tasks"][0]
        task["obligations"] = ["Required CI still running"]
        with self.assertRaisesRegex(ValueError, "settled obligations"):
            validate(self.data)
        task["obligations"] = []
        task["owner"]["handoff"] = ""
        with self.assertRaisesRegex(ValueError, "handoff"):
            validate(self.data)

    def test_unfinished_milestone_blocks_complete_owner(self):
        task = self.data["tasks"][0]
        task["milestones"]["code_publication"]["state"] = "pending"
        with self.assertRaisesRegex(ValueError, "unfinished stage"):
            validate(self.data)

    def test_closed_owner_with_unpublished_code_needs_durable_copy(self):
        owner = self.tasks["UI-101"]["owner"]
        owner.pop("retained_code")
        with self.assertRaisesRegex(ValueError, "UI-101: unpublished code must be kept outside the owner's workspace"):
            validate(self.data)
        owner["retained_code"] = {"kind": "bundle", "ref": "proof/ui-101/pinning.bundle"}
        with self.assertRaisesRegex(ValueError, "retained_code.checksum"):
            validate(self.data)
        owner["retained_code"] = {"kind": "pushed_branch", "ref": "origin/ui-101-pinning"}
        validate(self.data)
        self.assertIn("Pushed branch <code>origin/ui-101-pinning</code>", render(self.data))

    def test_finishing_needs_runtime_released_or_retained(self):
        runtime = self.tasks["SHIP-107"]["runtime"]
        runtime.append({"id": "orb", "kind": "sandbox", "ref": "orb-107", "state": "held"})
        with self.assertRaisesRegex(ValueError, "SHIP-107: release or retain runtime orb"):
            validate(self.data)
        runtime[-1].update(state="retained", reason="Browser session for the expiry check", until="2026-10-15T12:00:00-05:00")
        validate(self.data)

    def test_expired_approval_cannot_stay_active(self):
        approval = self.data["approvals"][1]
        approval["state"] = "active"
        with self.assertRaisesRegex(ValueError, "A2: approval expired; mark it expired and ask again"):
            validate(self.data)
        approval["state"] = "expired"
        validate(self.data)
        self.assertIn("<b>A2</b> Expired", render(self.data))
        approval["task_ids"] = ["NOPE-1"]
        with self.assertRaisesRegex(ValueError, "A2: approval names an unknown task"):
            validate(self.data)

    def test_idle_scans_with_only_people_gated_work_must_stop_scheduling(self):
        for task in self.data["tasks"]:
            if task["work"]["state"] not in ("delivered", "no_change_needed", "cancelled", "deferred", "needs_decision"):
                task["work"]["state"] = "waiting"
                task["blocker"] = task["blocker"] or "Waiting on a person"
        self.data["monitoring"]["unchanged_scans"] = 3
        with self.assertRaisesRegex(ValueError, "3 unchanged scans with only people-gated work left"):
            validate(self.data)
        self.data["monitoring"].update(next_check_at=None, hold="Waiting on Q1; resume when answered")
        validate(self.data)
        self.data["monitoring"].update(next_check_at="2026-10-08T14:40:00-05:00", unchanged_scans=2)
        validate(self.data)

    def test_follow_ups_need_a_source_task_and_text(self):
        self.data["follow_ups"][1]["from_task"] = "NOPE-1"
        with self.assertRaisesRegex(ValueError, "F2: follow-up needs the assigned task"):
            validate(self.data)
        self.data["follow_ups"][1].update(from_task="API-102", text=" ")
        with self.assertRaisesRegex(ValueError, "F2.text must be nonempty"):
            validate(self.data)

    def test_skill_version_is_required_and_a_mismatch_is_a_note(self):
        self.data["skill_version"] = "0123abcd4567"
        validate(self.data)
        self.assertRegex(notes(self.data)[0], f"written for orchestration-run 0123abcd4567; the current version is {skill_version()}")
        self.data["skill_version"] = skill_version()
        self.assertEqual(notes(self.data), [])
        del self.data["skill_version"]
        with self.assertRaisesRegex(ValueError, "skill_version must be nonempty"):
            validate(self.data)

    def test_history_entries_stay_short(self):
        self.data["history"].append("Scan inspected six owners; all idle and unchanged. " * 20)
        with self.assertRaisesRegex(ValueError, "history entries \\[5\\] exceed 800 characters"):
            validate(self.data)

    def test_pending_business_acceptance_names_who_signs_off_and_when(self):
        acceptance = self.tasks["API-102"]["milestones"]["business_acceptance"]
        acceptance.update(state="pending", note="Product owner sign-off")
        with self.assertRaisesRegex(ValueError, "API-102.business_acceptance.accountable"):
            validate(self.data)
        acceptance.update(accountable="Product owner (Sam)")
        with self.assertRaisesRegex(ValueError, "API-102.business_acceptance.revisit"):
            validate(self.data)
        acceptance.update(revisit="Friday demo")
        validate(self.data)
        self.assertIn("Sign-off by Product owner (Sam); revisit Friday demo.", render(self.data))

    def test_closed_run_has_nothing_open_or_scheduled(self):
        self.data["closed_at"] = "2026-10-08T15:00:00-05:00"
        with self.assertRaisesRegex(ValueError, "a closed run cannot keep open owner API-102.*held runtime on API-102"
                                                 ".*unowned follow-up F2.*pending decisions.*a scheduled check"):
            validate(self.data)
        self.data["tasks"] = [task for task in self.data["tasks"] if task["owner"]["state"] in ("complete", "closed")]
        self.data["follow_ups"][1]["owner"] = "API-113"
        self.data["follow_ups"] = [item for item in self.data["follow_ups"]
                                   if item["from_task"] in {task["id"] for task in self.data["tasks"]}]
        self.data.update(decisions=[])
        self.data["monitoring"].update(next_check_at=None, hold="Run closed")
        validate(self.data)
        self.assertIn("This run closed at 2026-10-08T15:00:00-05:00", render(self.data))

    def test_stage_keys_come_from_the_dashboard_contract(self):
        import validate_run
        contract = json.loads((DASHBOARD / "assets" / "stages.json").read_text())
        self.assertEqual(validate_run.STAGES, tuple(item["key"] for item in contract))
        self.assertEqual(validate_run.STAGE_FALLBACK, validate_run.STAGES)


class InstallTests(unittest.TestCase):
    """The skills CLI and Workspace Skills install each skill folder alone."""

    def test_shared_files_match_their_owning_skill(self):
        for owner, copy, path in ((SETUP, RUNNER, "references/ticket-template.md"),
                                  (DISCOVERY, SETUP, "scripts/state.py"),
                                  (DISCOVERY, RUNNER, "scripts/state.py")):
            with self.subTest(path=path):
                self.assertEqual((copy / path).read_bytes(), (owner / path).read_bytes(),
                                 f"copy {copy.name}/{path} from {owner.name}/{path}")


    def test_the_runner_names_the_dashboard_skill_for_rendering(self):
        text = (RUNNER / "SKILL.md").read_text()
        self.assertIn("validate_run.py", text)
        self.assertIn("render_dashboard.py", text)
        self.assertIn("check_served.py", text)
        self.assertNotIn("<this skill's folder>/scripts/render_dashboard.py", text)
        self.assertFalse((RUNNER / "scripts" / "render_dashboard.py").exists())
        self.assertFalse((RUNNER / "assets").exists())


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository = self.root / "repository"
        self.saved = self.repository / ".nthplusio-skills"
        self.saved.mkdir(parents=True)
        self.cwd = self.root / "elsewhere"
        self.cwd.mkdir()
        self.config_path = self.saved / "orchestration.json"
        self.discovery_path = self.saved / "discovery.json"
        self.marker = self.root / "tool-invoked"
        self.discovery = json.loads((DISCOVERY / "assets" / "discovery.template.json").read_text())
        facts = self.discovery["harnesses"].pop("REPLACE_WITH_DISCOVERED_HARNESS_NAME")
        facts.update(context="Orb", observed_at="2026-10-09T12:00:00Z",
                     sources=["Inspected tool inventory"], owner_term="thread", helper_term="subagent")
        facts["owners"].update(launch=f"touch {self.marker}", inspect="Inspect by thread ID",
                               workspace_model="isolated")
        facts["monitoring"]["wait"] = "Wait with timeout_seconds; blocks caller"
        facts["skills"]["load"] = "Load by skill name"
        facts["artifacts"] = [{"id": "portal", "label": "Portal", "present": "Publish HTML",
                               "update": "Replace HTML", "audience": "Project reviewers", "interaction": None}]
        facts["limitations"] = ["No wake after yielding"]
        other = deepcopy(facts)
        other.update(context="Local terminal", owner_term="session", helper_term="bounded helper")
        other["owners"].update(launch=None, inspect=None, workspace_model="shared")
        other["monitoring"]["wait"] = None
        other["skills"]["load"] = None
        other["artifacts"] = []
        other["limitations"] = ["No independent owners"]
        self.discovery["harnesses"] = {"Amp": facts, "Claude Code": other}
        self.config = json.loads((SETUP / "assets" / "orchestration.template.json").read_text())
        profile = self.config["harnesses"].pop("REPLACE_WITH_DISCOVERED_HARNESS_NAME")
        profile.update(run_root="runs/amp", shared_skills=["speak-clearly", "amp-proof"],
                       confirmed_from="User confirmed Amp choices")
        profile["defaults"] = {"finish_line": "merged PRs", "destination": "portal", "interval_seconds": 15}
        other_profile = deepcopy(profile)
        other_profile.update(run_root="runs/claude", shared_skills=["terminal-proof"],
                             confirmed_from="User confirmed terminal choices")
        other_profile["defaults"] = {"finish_line": "review-ready PRs", "destination": None, "interval_seconds": 90}
        self.config["harnesses"] = {"Amp": profile, "Claude Code": other_profile}
        self.config["project"] = {
            "ticket_policy": {"source": "Linear", "location": "ENG team", "definition": "One shipped outcome",
                              "template": "docs/tickets.md", "id_convention": "ENG-N", "criteria_limit": 3,
                              "confirmed_from": "User confirmed project policy"},
            "shared_skills": ["speak-clearly", "test-behavior"],
        }
        self.save()

    def save(self):
        self.discovery_path.write_text(json.dumps(self.discovery))
        self.config_path.write_text(json.dumps(self.config))

    def cli(self, skill, *arguments):
        return subprocess.run([sys.executable, "-B", str(skill / "scripts" / "state.py"), *arguments,
                               "--root", str(self.repository)], cwd=self.cwd, capture_output=True, text=True)

    def selected(self, name):
        result = self.cli(SETUP, "resolve", "--harness", name, "--orchestration")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_saved_discovery_and_setup_validate_without_selecting_a_profile(self):
        for skill, scope, path in ((DISCOVERY, "discovery", self.discovery_path),
                                   (SETUP, "orchestration", self.config_path)):
            with self.subTest(scope=scope):
                result = self.cli(skill, "check", scope)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines()[0], f"PASS: {scope} {path}")
        result = self.cli(RUNNER, "check")
        self.assertEqual(result.stdout, f"PASS: discovery {self.discovery_path}\nPASS: orchestration {self.config_path}\n")
        self.assertFalse(self.marker.exists())

    def test_setup_validates_when_installed_without_its_sibling_skills(self):
        alone = self.root / "installed" / SETUP.name
        shutil.copytree(SETUP, alone, ignore=shutil.ignore_patterns("__pycache__"))
        result = self.cli(alone, "check", "orchestration")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"PASS: orchestration {self.config_path}\n")

    def test_stage_keys_follow_the_dashboard_contract_with_a_fallback(self):
        contract = [item["key"] for item in json.loads((DASHBOARD / "assets" / "stages.json").read_text())]
        for skill in (DISCOVERY, SETUP, RUNNER):
            with self.subTest(skill=skill.name):
                found = subprocess.run([sys.executable, "-B", "-c", "import state; print(list(state.STAGES))"],
                                       cwd=skill / "scripts", capture_output=True, text=True)
                self.assertEqual(json.loads(found.stdout.replace("'", '"')), contract, found.stderr)
        alone = self.root / "installed" / SETUP.name
        shutil.copytree(SETUP, alone, ignore=shutil.ignore_patterns("__pycache__"))
        found = subprocess.run([sys.executable, "-B", "-c", "import state; print(list(state.STAGES))"],
                               cwd=alone / "scripts", capture_output=True, text=True)
        self.assertEqual(json.loads(found.stdout.replace("'", '"')), contract, found.stderr)

    def test_exact_names_select_asymmetric_capabilities_defaults_and_shared_skills(self):
        amp = self.selected("Amp")
        terminal = self.selected("Claude Code")
        self.assertEqual(amp["harness"], {"name": "Amp", "slug": "amp", "context": "Orb", "owner_term": "thread", "helper_term": "subagent"})
        self.assertEqual(terminal["harness"], {"name": "Claude Code", "slug": "claude-code", "context": "Local terminal",
                                               "owner_term": "session", "helper_term": "bounded helper"})
        self.assertEqual(amp["owners"]["inspect"], "Inspect by thread ID")
        self.assertEqual(amp["owners"]["workspace_model"], "isolated")
        self.assertEqual(terminal["owners"]["workspace_model"], "shared")
        self.assertEqual(amp["defaults"], {"finish_line": "merged PRs", "destination": "portal", "interval_seconds": 15})
        self.assertEqual(terminal["defaults"], {"finish_line": "review-ready PRs", "destination": None, "interval_seconds": 90})
        self.assertEqual(amp["skills"], {"load": "Load by skill name", "brief": "Pass applicable instructions explicitly; do not assume inheritance.",
                                        "locations": None, "reload": None, "frontmatter": None,
                                        "shared": ["speak-clearly", "test-behavior", "amp-proof"], "stages": {}})
        self.assertEqual(terminal["skills"]["shared"], ["speak-clearly", "test-behavior", "terminal-proof"])
        self.assertFalse(self.marker.exists())

    def test_stage_skills_are_optional_validated_and_resolved(self):
        self.config["project"]["stage_skills"] = {"code_publication": ["start-work"], "review": ["pr-ready"]}
        self.config_path.write_text(json.dumps(self.config))
        self.assertEqual(self.selected("Amp")["skills"]["stages"], {"code_publication": ["start-work"], "review": ["pr-ready"]})
        for bad in ({"shipping": ["start-work"]}, {"review": [RUNNER.name]}):
            with self.subTest(stage_skills=bad):
                self.config["project"]["stage_skills"] = bad
                self.config_path.write_text(json.dumps(self.config))
                result = self.cli(SETUP, "check", "orchestration")
                self.assertEqual(result.returncode, 1)
        del self.config["project"]["stage_skills"]
        self.config_path.write_text(json.dumps(self.config))
        self.assertEqual(self.selected("Amp")["skills"]["stages"], {})

    def test_project_policy_is_retained_for_both_profiles(self):
        for name in ("Amp", "Claude Code"):
            with self.subTest(name=name):
                self.assertEqual(self.selected(name)["ticket_policy"], {
                    "source": "Linear", "location": "ENG team", "definition": "One shipped outcome",
                    "template": "docs/tickets.md", "id_convention": "ENG-N", "criteria_limit": 3,
                    "confirmed_from": "User confirmed project policy",
                })

    def test_portable_paths_resolve_against_config_directory_not_cwd(self):
        for name, directory in (("Amp", "amp"), ("Claude Code", "claude")):
            with self.subTest(name=name):
                selected = self.selected(name)
                self.assertEqual(selected["config_path"], str(self.config_path))
                self.assertEqual(selected["run_root"], str(self.saved / "runs" / directory))
                self.assertFalse((self.saved / "runs").exists())
        self.assertEqual(list(self.cwd.iterdir()), [])

    def test_a_slug_selects_its_key_and_other_names_refuse_fallback(self):
        self.assertEqual(self.selected("amp"), self.selected("Amp"))
        self.assertEqual(self.selected("claude-code"), self.selected("Claude Code"))
        for name in ("Claude", "Unknown", "amp code"):
            with self.subTest(name=name):
                result = self.cli(SETUP, "resolve", "--harness", name, "--orchestration")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn("no saved discovery for this harness", result.stderr)
        del self.config["harnesses"]["Claude Code"]
        self.save()
        result = self.cli(SETUP, "resolve", "--harness", "Claude Code", "--orchestration")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no setup profile", result.stderr)
        self.assertEqual(json.loads(self.cli(DISCOVERY, "resolve", "--harness", "claude-code").stdout)["harness"]["name"],
                         "Claude Code")
        self.config["harnesses"]["Claude Code"] = {"run_root": "runs/claude", "shared_skills": [], "confirmed_from": "Test",
                                                   "defaults": {"finish_line": "review-ready PRs", "destination": None,
                                                                "interval_seconds": 90}}
        del self.discovery["harnesses"]["Claude Code"]
        self.save()
        result = self.cli(SETUP, "resolve", "--harness", "Amp", "--orchestration")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Claude Code: no saved discovery", result.stderr)

    def test_missing_state_names_the_skill_to_run(self):
        self.config_path.unlink()
        result = self.cli(RUNNER, "resolve", "--harness", "Amp", "--orchestration")
        self.assertEqual(result.returncode, 1)
        self.assertIn("run orchestration-setup", result.stderr)
        self.discovery_path.unlink()
        result = self.cli(DISCOVERY, "check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("run harness-discovery", result.stderr)

    def test_unavailable_operations_remain_null(self):
        selected = self.selected("Claude Code")
        self.assertEqual(selected["owners"], {"launch": None, "inspect": None, "message": None,
                                             "collect": None, "close": None, "resume": None, "workspace_model": "shared"})
        self.assertEqual(selected["helpers"], {"invoke": None, "collect": None, "blocks_caller": None, "follow_up": None,
                                              "readonly": None, "definitions": None})
        self.assertEqual(selected["monitoring"], {"notifications": None, "wait": None, "wake": None})
        self.assertEqual(selected["evidence"], {"transfer": None, "retain_before_close": None})
        self.assertEqual(selected["artifacts"], [])
        self.assertEqual(selected["limitations"], ["No independent owners"])
        self.assertIsNone(self.selected("Amp")["artifacts"][0]["interaction"])

    def test_artifact_auto_refresh_is_an_optional_capability_description(self):
        artifact = self.discovery["harnesses"]["Amp"]["artifacts"][0]
        self.assertNotIn("auto_refresh", self.selected("Amp")["artifacts"][0])
        for value in (None, "Supports HTML meta refresh at the updated page URL"):
            with self.subTest(capability=value):
                artifact["auto_refresh"] = value
                self.save()
                self.assertEqual(self.selected("Amp")["artifacts"][0]["auto_refresh"], value)
        for value in ("", True, 17):
            with self.subTest(invalid=value):
                artifact["auto_refresh"] = value
                self.save()
                result = self.cli(DISCOVERY, "check", "discovery")
                self.assertEqual(result.returncode, 1)
                self.assertIn("artifact.auto_refresh must be nonempty text", result.stderr)

    def test_all_coordinator_names_are_excluded_from_shared_worker_skills(self):
        original = deepcopy(self.config)
        for name in (DISCOVERY.name, SETUP.name, RUNNER.name, DASHBOARD.name):
            for scope in ("project", "Amp", "Claude Code"):
                with self.subTest(name=name, scope=scope):
                    self.config = deepcopy(original)
                    target = self.config["project"] if scope == "project" else self.config["harnesses"][scope]
                    target["shared_skills"].append(name)
                    self.save()
                    result = self.cli(SETUP, "resolve", "--harness", "Amp", "--orchestration")
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, "")
                    self.assertIn("coordinator", result.stderr)

    def test_malformed_discovery_fails_validation_and_resolution_without_tools(self):
        original = deepcopy(self.discovery)
        for field, value in (("schema_version", 2), ("harnesses", []), ("repository", None)):
            with self.subTest(field=field):
                self.discovery = deepcopy(original)
                self.discovery[field] = value
                self.save()
                for skill, args in ((DISCOVERY, ("check", "discovery")),
                                    (SETUP, ("resolve", "--harness", "Amp", "--orchestration"))):
                    result = self.cli(skill, *args)
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, "")
                    self.assertIn("FAIL:", result.stderr)
                self.assertFalse(self.marker.exists())
        self.discovery_path.write_text("{not JSON")
        result = self.cli(SETUP, "resolve", "--harness", "Amp", "--orchestration")
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.marker.exists())

    def test_malformed_setup_fails_before_tools(self):
        original = deepcopy(self.config)
        for field, value in (("schema_version", 2), ("schema_version", 1), ("project", None), ("harnesses", [])):
            with self.subTest(field=field, value=value):
                self.config = deepcopy(original)
                self.config[field] = value
                self.save()
                result = self.cli(SETUP, "resolve", "--harness", "Amp", "--orchestration")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn("FAIL:", result.stderr)
                self.assertFalse(self.marker.exists())
        self.config_path.write_text("{not JSON")
        result = self.cli(SETUP, "resolve", "--harness", "Amp", "--orchestration")
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.marker.exists())

    def test_resolution_does_not_modify_saved_sources(self):
        before = {path: path.read_bytes() for path in (self.config_path, self.discovery_path)}
        self.selected("Amp")
        self.selected("Claude Code")
        self.selected("Amp")
        for path, expected in before.items():
            self.assertEqual(path.read_bytes(), expected)
        self.assertFalse(self.marker.exists())


if __name__ == "__main__":
    unittest.main()
