"""Run with python3 -B -m unittest discover -s <this directory> -v."""

from copy import deepcopy
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


RUNNER = Path(__file__).resolve().parent.parent
SETUP = RUNNER.parent / "orchestration-setup"
DISCOVERY = RUNNER.parent / "orchestration-discovery"
sys.path.insert(0, str(RUNNER / "scripts"))
from render_dashboard import render


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.ids = []
        self.rows = {}
        self.contexts = {}
        self.row = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if "data-context" in attrs:
            packet = json.loads(attrs["data-context"])
            key = packet["decision"]["id"] if "decision" in packet else packet["tasks"][0]["id"]
            self.contexts[key] = packet
        if tag == "tr" and attrs.get("id", "").startswith("row-"):
            self.row = attrs["id"]
            self.rows[self.row] = []
        if self.row and attrs.get("role") == "img":
            self.rows[self.row].append(attrs["aria-label"])

    def handle_endtag(self, tag):
        if tag == "tr":
            self.row = None


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((RUNNER / "evals" / "dashboard-preview.json").read_text())

    def test_scoped_readiness_and_delivery_are_visibly_distinct(self):
        page = Page(render(self.data))
        self.assertEqual(page.rows["row-UI-101"], ["Verified", "Not requested", "Not requested", "Not requested"])
        self.assertEqual(page.rows["row-SHIP-107"], ["Verified", "Verified", "Verified", "Verified"])
        self.assertEqual(page.rows["row-OPS-105"], ["Verified", "Blocked", "Not requested", "Not requested"])
        self.assertEqual(len(page.rows), 7)
        self.assertEqual(len(page.ids), len(set(page.ids)))

    def test_green_job_cannot_be_used_as_verified_review_proof(self):
        self.data["tasks"][2]["milestones"]["pr_readiness"]["state"] = "verified"
        with self.assertRaisesRegex(ValueError, "accepted supporting proof"):
            render(self.data)

    def test_old_verdict_and_failed_interrupted_evidence_remain(self):
        html = render(self.data)
        self.assertIn('id="proof-E5"', html)
        self.assertIn("passed · superseded", html)
        self.assertIn("failed · limited", html)
        self.assertIn("interrupted · limited", html)
        self.assertIn("posted reviews: []", html)

    def test_pending_obligation_blocks_owner_closure_even_with_green_milestones(self):
        task = self.data["tasks"][0]
        task["obligations"] = ["Required CI still running"]
        with self.assertRaisesRegex(ValueError, "settled obligations"):
            render(self.data)
        task["obligations"] = []
        task["owner"]["handoff"] = ""
        with self.assertRaisesRegex(ValueError, "handoff"):
            render(self.data)

    def test_unfinished_milestone_blocks_complete_owner(self):
        task = self.data["tasks"][0]
        task["milestones"]["code_publication"]["state"] = "pending"
        with self.assertRaisesRegex(ValueError, "unfinished milestone"):
            render(self.data)

    def test_one_owner_cannot_be_assigned_to_two_tickets_even_after_closure(self):
        first, second = self.data["tasks"][:2]
        second["owner"]["id"] = first["owner"]["id"]
        for state in ("active", "closed"):
            with self.subTest(first_owner_state=state):
                first["owner"]["state"] = state
                with self.assertRaisesRegex(ValueError, "API-102: owner ui-owner is already bound to another ticket"):
                    render(self.data)

    def test_completed_but_unclosed_owner_is_visible(self):
        self.data["tasks"][0]["owner"]["state"] = "complete"
        html = render(self.data)
        self.assertIn('<b>1</b><span>complete, not closed</span>', html)
        self.assertIn('<b>1</b><span>closed owners</span>', html)

    def test_missing_and_superseded_proof_do_not_mark_verified(self):
        phase = self.data["tasks"][0]["milestones"]["pr_readiness"]
        for proofs, expected in (([], "accepted supporting proof"), (["missing"], "missing proof"), (["E5"], "accepted supporting proof")):
            with self.subTest(proofs=proofs):
                phase["evidence"] = proofs
                with self.assertRaisesRegex(ValueError, expected):
                    render(self.data)

    def test_hosted_links_reject_private_local_and_script_targets(self):
        for href in ("file:///tmp/receipt.txt", "./receipt.txt", "http://localhost:3000/receipt", "http://127.0.0.1/", "http://[::1]/", "http://10.2.3.4/", "javascript:alert(1)"):
            with self.subTest(href=href):
                self.data["evidence"][0]["href"] = href
                with self.assertRaises(ValueError):
                    render(self.data, hosted=True)
        self.data["evidence"][0]["href"] = "https://example.org/approved-receipt"
        self.assertIn('href="https://example.org/approved-receipt"', render(self.data, hosted=True))

    def test_copied_questions_name_run_task_and_retained_proof(self):
        html = render(self.data)
        self.assertIn("In orchestration run template-preview, task API-104: What does retained proof E5, E6 establish", html)
        self.assertIn("In orchestration run template-preview, decision Q1:", html)
        self.assertIn('data-copy-id="UI-101"', html)
        self.assertIn("Copy does not send", html)

    def test_copied_context_is_scoped_and_keeps_work_owner_distinct_from_answer_route(self):
        self.data["tasks"][4]["owner"]["href"] = "https://example.org/reviewer-owner"
        contexts = Page(render(self.data)).contexts
        packet = contexts["Q1"]
        self.assertEqual(packet["run_id"], "template-preview")
        self.assertEqual(packet["snapshot_time"], "2026-10-08T14:30:00-05:00")
        self.assertEqual([task["id"] for task in packet["tasks"]], ["OPS-105"])
        task = packet["tasks"][0]
        self.assertEqual(task["owner"]["id"], "reviewer-owner")
        self.assertEqual(packet["answer_route"]["owner_id"], "fixture-coordinator")
        self.assertEqual(task["milestones"]["pr_readiness"]["evidence"], ["E7"])
        self.assertEqual(task["milestones"]["code_publication"]["state"], "blocked")
        self.assertEqual(task["milestones"]["deployment"]["state"], "not_requested")
        self.assertIn("unapproved", task["blocker"])
        self.assertIn("no approval", packet["approval_constraints"])
        self.assertEqual(packet["decision"]["task_ids"], ["OPS-105"])
        self.assertEqual(contexts["OPS-105"]["answer_route"], {
            "owner_id": "reviewer-owner", "label": "Reviewer owner",
            "href": "https://example.org/reviewer-owner",
        })
        self.assertNotIn("decision", contexts["OPS-105"])

    def test_decision_questions_route_to_their_owners_and_name_human_only_gates(self):
        self.data["decisions"] = [
            {"id": "Q-local", "text": "Choose the description format?", "recommendation": "Use full labels.",
             "task_ids": ["API-104"], "unblocks": "Description formatting",
             "discussion": {"owner_id": "hierarchy-owner", "label": "Hierarchy owner",
                            "href": "https://example.org/discuss-hierarchy"}},
            {"id": "Q-gate", "text": "Complete the existing sign-in dialog.", "recommendation": "Answer in the runtime thread.",
             "task_ids": ["ENV-106"], "unblocks": "Runtime sign-in", "requires_human": True,
             "discussion": {"owner_id": "runtime-owner", "label": "Runtime owner",
                            "href": "https://example.org/runtime-input"}},
        ]
        html = render(self.data, hosted=True)
        self.assertIn('href="https://example.org/discuss-hierarchy">Open discussion</a>', html)
        self.assertIn('href="https://example.org/runtime-input">Answer in thread</a>', html)
        self.assertIn('href="#task-API-104">API-104</a>', html)
        self.assertIn("Unblocks: Description formatting", html)
        self.assertIn('data-discussion-owner="hierarchy-owner"', html)
        self.assertIn('data-requires-human="true"', html)
        self.assertIn("Human-only gate. A forwarded message cannot answer it.", html)
        self.assertIn('data-copy-id="Q-gate"', html)

    def test_decision_route_validation_and_legacy_coordinator_fallback(self):
        decision = {"id": "Q-old", "text": "Keep publication held?", "recommendation": "Keep the hold."}
        self.data["decisions"] = [decision]
        self.assertIn('data-discussion-owner=""', render(self.data))
        for fields, expected in (
            ({"requires_human": True}, "human-only gate needs a discussion owner"),
            ({"requires_human": "true"}, "requires_human must be boolean"),
            ({"task_ids": ["MISSING"]}, "unknown affected task"),
            ({"discussion": {"owner_id": "runtime-owner", "label": "Runtime owner", "href": "javascript:bad()"}}, "unsupported link scheme"),
            ({"discussion": {"owner_id": "runtime-owner", "label": "Runtime owner", "requires_human": True}},
             "requires_human belongs on the decision"),
        ):
            with self.subTest(fields=fields):
                self.data["decisions"] = [{**decision, **fields}]
                with self.assertRaisesRegex(ValueError, expected):
                    render(self.data, hosted=True)

    def test_text_is_escaped_and_not_reprocessed_as_a_template(self):
        self.data["title"] = '<script>alert("title")</script> {{ROWS}}'
        self.data["tasks"][0]["title"] = '</button><img src=x onerror="bad()">'
        html = render(self.data)
        self.assertIn("&lt;script&gt;alert(&quot;title&quot;)&lt;/script&gt; {{ROWS}}", html)
        self.assertNotIn('<img src=x', html)
        self.assertEqual(html.count('<script>'), 1)

    def test_empty_run_and_cli_failure_preserve_previous_dashboard(self):
        self.data.update(tasks=[], decisions=[], evidence=[], history=[])
        self.assertIn("No assigned tasks.", render(self.data))
        with tempfile.TemporaryDirectory() as directory:
            status, output = Path(directory) / "status.json", Path(directory) / "dashboard.html"
            output.write_text("previous useful dashboard")
            self.data["schema_version"] = 2
            status.write_text(json.dumps(self.data))
            result = subprocess.run([sys.executable, str(RUNNER / "scripts" / "render_dashboard.py"), str(status), str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("unsupported dashboard schema_version", result.stderr)
            self.assertEqual(output.read_text(), "previous useful dashboard")


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.saved = self.root / "repository" / ".orchestration"
        self.saved.mkdir(parents=True)
        self.cwd = self.root / "elsewhere"
        self.cwd.mkdir()
        self.config_path = self.saved / "config.json"
        self.discovery_path = self.saved / "facts" / "discovery.json"
        self.discovery_path.parent.mkdir()
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
        self.config = json.loads((SETUP / "assets" / "config.template.json").read_text())
        profile = self.config["harnesses"].pop("REPLACE_WITH_DISCOVERED_HARNESS_NAME")
        profile.update(run_root="runs/amp", shared_skills=["speak-clearly", "amp-proof"],
                       confirmed_from="User confirmed Amp choices")
        profile["defaults"] = {"finish_line": "merged PRs", "destination": "portal", "interval_seconds": 15}
        other_profile = deepcopy(profile)
        other_profile.update(run_root="runs/claude", shared_skills=["terminal-proof"],
                             confirmed_from="User confirmed terminal choices")
        other_profile["defaults"] = {"finish_line": "review-ready PRs", "destination": None, "interval_seconds": 90}
        self.config["harnesses"] = {"Amp": profile, "Claude Code": other_profile}
        self.config["discovery_file"] = "facts/discovery.json"
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

    def cli(self, skill, path, *arguments):
        script = "check_discovery.py" if skill == DISCOVERY else "check_config.py"
        return subprocess.run([sys.executable, "-B", str(skill / "scripts" / script), str(path), *arguments],
                              cwd=self.cwd, capture_output=True, text=True)

    def selected(self, name):
        result = self.cli(SETUP, self.config_path, "--harness", name)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_saved_discovery_and_setup_validate_without_selecting_a_profile(self):
        for skill, path, label in ((DISCOVERY, self.discovery_path, "discovery"),
                                   (SETUP, self.config_path, "configuration")):
            with self.subTest(label=label):
                result = self.cli(skill, path)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, f"PASS: {label} for {path}\n")
        self.assertFalse(self.marker.exists())

    def test_exact_names_select_asymmetric_capabilities_defaults_and_shared_skills(self):
        amp = self.selected("Amp")
        terminal = self.selected("Claude Code")
        self.assertEqual(amp["harness"], {"name": "Amp", "context": "Orb", "owner_term": "thread", "helper_term": "subagent"})
        self.assertEqual(terminal["harness"], {"name": "Claude Code", "context": "Local terminal", "owner_term": "session", "helper_term": "bounded helper"})
        self.assertEqual(amp["owners"]["inspect"], "Inspect by thread ID")
        self.assertEqual(amp["owners"]["workspace_model"], "isolated")
        self.assertEqual(terminal["owners"]["workspace_model"], "shared")
        self.assertEqual(amp["defaults"], {"finish_line": "merged PRs", "destination": "portal", "interval_seconds": 15})
        self.assertEqual(terminal["defaults"], {"finish_line": "review-ready PRs", "destination": None, "interval_seconds": 90})
        self.assertEqual(amp["skills"], {"load": "Load by skill name", "brief": "Pass applicable instructions explicitly; do not assume inheritance.",
                                        "shared": ["speak-clearly", "test-behavior", "amp-proof"]})
        self.assertEqual(terminal["skills"]["shared"], ["speak-clearly", "test-behavior", "terminal-proof"])
        self.assertFalse(self.marker.exists())

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

    def test_missing_harness_refuses_fallback(self):
        for name in ("amp", "Claude", "Unknown"):
            with self.subTest(name=name):
                result = self.cli(SETUP, self.config_path, "--harness", name)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn("no setup profile", result.stderr)
        del self.discovery["harnesses"]["Claude Code"]
        self.save()
        result = self.cli(SETUP, self.config_path, "--harness", "Claude Code")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no saved discovery", result.stderr)

    def test_unavailable_operations_remain_null(self):
        selected = self.selected("Claude Code")
        self.assertEqual(selected["owners"], {"launch": None, "inspect": None, "message": None,
                                             "collect": None, "close": None, "resume": None, "workspace_model": "shared"})
        self.assertEqual(selected["helpers"], {"invoke": None, "collect": None, "blocks_caller": None, "follow_up": None})
        self.assertEqual(selected["monitoring"], {"notifications": None, "wait": None, "wake": None})
        self.assertEqual(selected["evidence"], {"transfer": None, "retain_before_close": None})
        self.assertEqual(selected["artifacts"], [])
        self.assertEqual(selected["limitations"], ["No independent owners"])
        self.assertIsNone(self.selected("Amp")["artifacts"][0]["interaction"])

    def test_all_orchestration_names_are_excluded_from_shared_worker_skills(self):
        original = deepcopy(self.config)
        for name in ("orchestration-discovery", "orchestration-setup", "orchestration-run"):
            for scope in ("project", "Amp", "Claude Code"):
                with self.subTest(name=name, scope=scope):
                    self.config = deepcopy(original)
                    target = self.config["project"] if scope == "project" else self.config["harnesses"][scope]
                    target["shared_skills"].append(name)
                    self.save()
                    result = self.cli(SETUP, self.config_path, "--harness", "Amp")
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
                for skill, path, args in ((DISCOVERY, self.discovery_path, ()),
                                          (SETUP, self.config_path, ("--harness", "Amp"))):
                    result = self.cli(skill, path, *args)
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, "")
                    self.assertIn("FAIL:", result.stderr)
                self.assertFalse(self.marker.exists())
        self.discovery_path.write_text("{not JSON")
        result = self.cli(SETUP, self.config_path, "--harness", "Amp")
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.marker.exists())

    def test_malformed_setup_fails_before_tools(self):
        original = deepcopy(self.config)
        for field, value in (("schema_version", 1), ("project", None), ("harnesses", []), ("discovery_file", "missing.json")):
            with self.subTest(field=field):
                self.config = deepcopy(original)
                self.config[field] = value
                self.save()
                result = self.cli(SETUP, self.config_path, "--harness", "Amp")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn("FAIL:", result.stderr)
                self.assertFalse(self.marker.exists())
        self.config_path.write_text("{not JSON")
        result = self.cli(SETUP, self.config_path, "--harness", "Amp")
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
