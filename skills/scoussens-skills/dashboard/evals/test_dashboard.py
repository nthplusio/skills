"""Run with python3 -B -m unittest discover -s <this directory> -v."""

from copy import deepcopy
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


DASHBOARD = Path(__file__).resolve().parent.parent
PREVIEW = DASHBOARD / "evals" / "dashboard-preview.json"
sys.path.insert(0, str(DASHBOARD / "scripts"))
from render_dashboard import CONTRACT_VERSION, render


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.ids = []
        self.rows = {}
        self.row_text = {}
        self.work_states = {}
        self.groups = {}
        self.group = None
        self.contexts = {}
        self.row = None
        self.refresh = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("http-equiv") == "refresh":
            self.refresh = attrs["content"]
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if "data-context" in attrs:
            packet = json.loads(attrs["data-context"])
            key = packet["decision"]["id"] if "decision" in packet else packet["tasks"][0]["id"]
            self.contexts[key] = packet
        if tag == "tbody":
            self.group = attrs.get("class", "")
            self.groups[self.group] = []
        if tag == "tr" and attrs.get("id", "").startswith("row-"):
            self.row = attrs["id"]
            self.rows[self.row] = []
            self.row_text[self.row] = []
            self.work_states[self.row] = attrs.get("data-work-state")
            self.groups[self.group].append(self.row)
        if self.row and attrs.get("role") == "img":
            self.rows[self.row].append(attrs["aria-label"])

    def handle_data(self, text):
        if self.row:
            self.row_text[self.row].append(text)

    def handle_endtag(self, tag):
        if tag == "tr":
            self.row = None


STAGE_LABELS = ("Defined", "Researched", "Implemented", "Submitted", "Reviewed", "Verified", "Deployed", "Accepted")


def stage_row(*states):
    return [f"{label}: {state}" for label, state in zip(STAGE_LABELS, states)]


OUT = "Not in scope"


class DashboardTests(unittest.TestCase):
    """The page the renderer draws from the preview record. Rules about what a record may claim
    belong to its producer; orchestration-run tests them against validate_run.py."""

    def setUp(self):
        self.data = json.loads(PREVIEW.read_text())

    def test_scoped_readiness_and_delivery_are_visibly_distinct(self):
        page = Page(render(self.data))
        self.assertEqual(page.rows["row-UI-101"], stage_row("Done", OUT, "Done", OUT, OUT, OUT, OUT, OUT))
        self.assertEqual(page.rows["row-SHIP-107"], stage_row(*["Done"] * 8))
        self.assertEqual(page.rows["row-OPS-105"], stage_row("Done", OUT, "Done", "Blocked", OUT, OUT, OUT, OUT))
        self.assertIn("Submitted — blocked", page.row_text["row-OPS-105"])
        self.assertIn("Target: Submitted", page.row_text["row-OPS-105"])
        self.assertIn("Implemented ✓", page.row_text["row-UI-101"])
        self.assertIn("Accepted ✓", page.row_text["row-SHIP-107"])
        self.assertEqual(len(page.rows), 11)
        self.assertEqual(len(page.ids), len(set(page.ids)))

    def test_grouped_ledger_distinguishes_resolution_from_activity_and_delivery(self):
        html = render(self.data)
        page = Page(html)
        self.assertEqual(page.groups, {
            "group-attention": ["row-REVIEW-103", "row-OPS-105", "row-ENV-106"],
            "group-moving": ["row-API-102", "row-API-104"],
            "group-resolved": ["row-UI-101", "row-SHIP-107", "row-TRIAGE-108", "row-UI-109", "row-UI-110", "row-UI-111"],
        })
        for row, label, stage in (("row-TRIAGE-108", "No change needed", "Researched ✓"),
                                  ("row-UI-109", "Cancelled", "Stopped after Defined"),
                                  ("row-UI-110", "Postponed", "Stopped after Defined")):
            with self.subTest(row=row):
                self.assertIn(label, page.row_text[row])
                self.assertIn(stage, page.row_text[row])
                self.assertEqual(page.rows[row][2:], stage_row(*[OUT] * 8)[2:])
        self.assertNotIn("Reached this run's target", page.row_text["row-UI-110"])
        self.assertIn("We'll revisit: After the authentication fix is accepted.", page.row_text["row-UI-110"])
        self.assertIn('href="#decision-Q1"', html)
        self.assertIn('<b>6 of 11</b> items wrapped up', html)
        self.assertIn('2 done (1 not submitted) · 2 in progress · 3 need attention', html)
        self.assertIn('<b>4</b> Wrapped up without delivery', html)
        self.assertIn('1 decision needs your input', html)
        self.assertIn('<b>2</b> Done', html)
        self.assertIn('<b>2</b> Postponed', html)
        self.assertEqual(page.contexts["UI-110"]["tasks"][0]["work"], {
            "state": "deferred", "summary": "Postponed until the sign-in fix is accepted.",
            "reason": "The user moved draft recovery out of this run.",
            "receipt": "Synthetic Q-auth answer: defer UI-110 until the authentication fix is accepted.",
            "revisit": "After the authentication fix is accepted.",
        })
        self.assertIn("E10 establish", html)

    def test_overview_is_plain_and_drill_in_keeps_technical_detail(self):
        html = render(self.data)
        page = Page(html)
        row = page.row_text["row-OPS-105"]
        self.assertIn("Ready to go, but releasing it would affect more than planned. It needs your approval.", row)
        for technical in ("Publication would trigger a broader deployment; approval is missing.",
                          "Resolve Q1. The old hash is not a separate behavioral hold.", "Reviewer owner"):
            with self.subTest(technical=technical):
                self.assertNotIn(technical, row)
                self.assertIn(technical, html.split('id="task-OPS-105"', 1)[1])
        self.assertIn("<code>needs_decision</code>", html)
        self.assertIn("<b>PR readiness</b> <code>pr_readiness</code><span><code>verified</code></span>", html)
        self.assertIn("<li><b>Submitted</b> The change is shared as a branch or pull request.</li>", html)
        task = self.data["tasks"][4]
        del task["work"]["summary"]
        self.assertIn("Publication would trigger a broader deployment; approval is missing.",
                      Page(render(self.data)).row_text["row-OPS-105"])
        for value in ("", "  ", None):
            with self.subTest(summary=value):
                task["work"]["summary"] = value
                with self.assertRaisesRegex(ValueError, "summary must be nonempty text"):
                    render(self.data)

    def test_legacy_closed_owners_need_classification_not_a_delivery_guess(self):
        for task in self.data["tasks"]:
            del task["work"]
        html = render(self.data)
        page = Page(html)
        self.assertEqual(page.work_states["row-UI-101"], "unknown")
        self.assertEqual(page.work_states["row-UI-109"], "unknown")
        self.assertEqual(page.work_states["row-API-102"], "working")
        self.assertEqual(page.work_states["row-ENV-106"], "blocked")
        self.assertEqual(page.work_states["row-REVIEW-103"], "waiting")
        self.assertIn("Confirming status", page.row_text["row-UI-101"])
        self.assertIn("We're confirming how this item ended.", page.row_text["row-UI-101"])
        self.assertIn('<b>6</b> Confirming status', html)
        self.assertIn('<b>0 of 11</b> items wrapped up', html)
        self.assertNotIn("group-resolved", page.groups)

    def test_business_stage_and_agent_status_are_separate(self):
        html = render(self.data)
        page = Page(html)
        self.assertIn('<b>2</b> Working</span>', html)
        self.assertIn('<b>1</b> Blocked</span>', html)
        self.assertIn('<b>5</b> Closed</span>', html)
        # The business target is reached while the agent is still working on its handoff.
        self.assertIn("Implemented ✓", page.row_text["row-API-102"])
        self.assertIn("Working", page.row_text["row-API-102"])
        self.assertIn("Two subagents are fixing the regressions", html.split('id="task-API-104"', 1)[1])
        task = self.data["tasks"][5]
        task["owner"]["state"] = "unreachable"
        self.assertIn("Not responding", Page(render(self.data)).row_text["row-ENV-106"])
        task["owner"]["activity"] = " "
        with self.assertRaisesRegex(ValueError, "owner activity must be nonempty text"):
            render(self.data)

    def test_stages_reject_unknown_keys_and_tolerate_older_records(self):
        task = self.data["tasks"][0]
        task["milestones"]["shipped"] = {"state": "verified", "note": "", "evidence": ["E1"]}
        with self.assertRaisesRegex(ValueError, "unknown stage shipped"):
            render(self.data)
        del task["milestones"]["shipped"]
        del task["milestones"]["deployment"]
        with self.assertRaisesRegex(ValueError, "missing stage deployment"):
            render(self.data)
        self.data = json.loads(PREVIEW.read_text())
        for task in self.data["tasks"]:
            for key in ("defined", "researched", "review", "verification"):
                del task["milestones"][key]
        page = Page(render(self.data))
        self.assertEqual(page.rows["row-UI-101"], stage_row(OUT, OUT, "Done", OUT, OUT, OUT, OUT, OUT))
        self.assertIn("No stages requested", page.row_text["row-TRIAGE-108"])
        del self.data["tasks"][0]["milestones"]
        self.assertEqual(Page(render(self.data)).rows["row-UI-101"], stage_row(*[OUT] * 8))

    def test_resolutions_render_from_their_fields_and_need_a_reason_and_real_proof_ids(self):
        baseline = deepcopy(self.data)
        for ticket, section, field, value, message in (
            ("TRIAGE-108", "work", "evidence", ["missing"], "retained proof"),
            ("UI-109", "work", "reason", "", "work needs a reason"),
            ("UI-109", "work", "state", "abandoned", "invalid work state"),
        ):
            with self.subTest(ticket=ticket, field=field):
                self.data = deepcopy(baseline)
                task = next(task for task in self.data["tasks"] if task["id"] == ticket)
                task[section][field] = value
                with self.assertRaisesRegex(ValueError, message):
                    render(self.data)
        # The renderer draws what the record says; whether the proof supports it is the producer's rule.
        self.data = deepcopy(baseline)
        self.data["tasks"][0]["work"]["evidence"] = []
        self.assertIn("Done, not submitted", "".join(Page(render(self.data)).row_text["row-UI-101"]))

    def test_unfinished_states_and_check_times_do_not_imply_success_or_stalls(self):
        task = self.data["tasks"][1]
        task["owner"]["state"] = "waiting"
        task["owner"]["last_checked_at"] = "2026-10-01T10:00:00-05:00"
        for state, label, group in (("ready", "Ready to start", "group-moving"),
                                    ("awaiting_acceptance", "Ready for sign-off", "group-moving"),
                                    ("waiting", "On hold", "group-attention"),
                                    ("unknown", "Confirming status", "group-attention")):
            with self.subTest(state=state):
                task["work"] = {"state": state, "reason": "Next inspection must confirm the result."}
                html = render(self.data)
                page = Page(html)
                self.assertIn("row-API-102", page.groups[group])
                self.assertIn(label, page.row_text["row-API-102"])
                self.assertIn("<dt>Last checked</dt><dd>2026-10-01T10:00:00-05:00</dd>", html.split('id="task-API-102"', 1)[1])
        del task["owner"]["last_checked_at"]
        self.assertIn("<dt>Last checked</dt><dd>Check time not recorded</dd>", render(self.data).split('id="task-API-102"', 1)[1])

    def test_auto_refresh_uses_run_interval_even_when_paused_or_finished(self):
        self.data["presentation"]["auto_refresh"] = True
        for interval, hold in ((1, None), (17, "Paused for user input"), (137, "Run complete")):
            with self.subTest(interval=interval, hold=hold):
                self.data["monitoring"].update(interval_seconds=interval, hold=hold, next_check_at=None)
                if hold == "Run complete":
                    self.data.update(tasks=[], decisions=[], evidence=[], history=[], approvals=[], follow_ups=[])
                html = render(self.data, hosted=True)
                self.assertEqual(Page(html).refresh, str(interval))
                unit = "second" if interval == 1 else "seconds"
                self.assertIn(f"This page reloads every {interval} {unit}", html)
                self.assertIn('<time datetime="2026-10-08T14:30:00-05:00" data-local>Oct 8, 2026, 2:30 PM (UTC-05:00)</time>', html)
        self.assertEqual(self.data["updated_at"], "2026-10-08T14:30:00-05:00")

    def test_absent_or_unavailable_auto_refresh_keeps_static_snapshot(self):
        self.data["monitoring"].update(interval_seconds=17)
        for explicit in (False, True):
            with self.subTest(explicit=explicit):
                if explicit:
                    self.data["presentation"]["auto_refresh"] = False
                html = render(self.data)
                self.assertIsNone(Page(html).refresh)
                self.assertIn("This page is a snapshot. It changes when the coordinator posts an update.", html)

    def test_auto_refresh_rejects_invalid_capability_flags_and_intervals(self):
        for value in (None, "true", 1):
            with self.subTest(flag=value):
                self.data["presentation"]["auto_refresh"] = value
                with self.assertRaisesRegex(ValueError, "presentation.auto_refresh must be boolean"):
                    render(self.data)
        self.data["presentation"]["auto_refresh"] = True
        del self.data["monitoring"]["interval_seconds"]
        with self.assertRaisesRegex(ValueError, "positive integer monitoring.interval_seconds"):
            render(self.data)
        for interval in (None, 0, -1, True, "17", 1.5):
            with self.subTest(interval=interval):
                self.data["monitoring"].update(interval_seconds=interval)
                with self.assertRaisesRegex(ValueError, "positive integer monitoring.interval_seconds"):
                    render(self.data)

    def test_old_verdict_and_failed_interrupted_evidence_remain(self):
        html = render(self.data)
        self.assertIn('id="proof-E5"', html)
        self.assertIn("passed · superseded", html)
        self.assertIn("failed · limited", html)
        self.assertIn("interrupted · limited", html)
        self.assertIn("posted reviews: []", html)

    def test_one_owner_cannot_be_assigned_to_two_tickets_even_after_closure(self):
        first, second = self.data["tasks"][:2]
        second["owner"]["id"] = first["owner"]["id"]
        for state in ("active", "closed"):
            with self.subTest(first_owner_state=state):
                first["owner"]["state"] = state
                with self.assertRaisesRegex(ValueError, "API-102: owner ui-owner is already bound to another ticket"):
                    render(self.data)

    def test_completed_but_unclosed_owner_is_visible(self):
        self.data["tasks"] = self.data["tasks"][:7]
        self.data["tasks"][0]["owner"]["state"] = "complete"
        html = render(self.data)
        self.assertIn('<b>1</b> Finished</span>', html)
        self.assertIn('<b>1</b> Closed</span>', html)
        self.assertIn("Complete, closure pending / unavailable", html)

    def test_stage_proof_must_exist_and_invalid_value_sets_are_named(self):
        phase = self.data["tasks"][0]["milestones"]["pr_readiness"]
        phase["evidence"] = ["missing"]
        with self.assertRaisesRegex(ValueError, "UI-101: missing proof missing"):
            render(self.data)
        phase["evidence"] = ["E1"]
        for path, value, message in (
            (("tasks", 0, "milestones", "pr_readiness", "state"), "done", "invalid stage state"),
            (("tasks", 0, "owner", "state"), "finished", "invalid owner state"),
            (("evidence", 0, "result"), "green", "invalid evidence result"),
            (("evidence", 0, "assessment"), "fine", "invalid evidence assessment"),
            (("approvals", 0, "state"), "granted", "A1: invalid approval state"),
            (("tasks", 6, "runtime", 0, "state"), "parked", "SHIP-107: invalid runtime state"),
            (("tasks", 0, "owner", "retained_code", "kind"), "zip", "retained_code.kind must be one of"),
        ):
            with self.subTest(path=path):
                data = deepcopy(self.data)
                target = data
                for step in path[:-1]:
                    target = target[step]
                target[path[-1]] = value
                with self.assertRaisesRegex(ValueError, message):
                    render(data)

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
        self.assertIn("In orchestration run template-preview, task API-104: What does retained proof E11, E5, E6 establish", html)
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
        self.data["decisions"] += [
            {"id": "Q-local", "text": "Choose the description format?", "recommendation": "Use full labels.",
             "task_ids": ["API-104"], "unblocks": "Description formatting",
             "discussion": {"owner_id": "list-owner", "label": "List owner",
                            "href": "https://example.org/discuss-list"}},
            {"id": "Q-gate", "text": "Complete the existing sign-in dialog.", "recommendation": "Answer in the runtime owner conversation.",
             "task_ids": ["ENV-106"], "unblocks": "Runtime sign-in", "requires_human": True,
             "discussion": {"owner_id": "runtime-owner", "label": "Runtime owner",
                            "href": "https://example.org/runtime-input"}},
        ]
        html = render(self.data, hosted=True)
        self.assertIn('href="https://example.org/discuss-list">Open discussion</a>', html)
        self.assertIn('href="https://example.org/runtime-input">Answer in conversation</a>', html)
        self.assertIn('href="#task-API-104">API-104</a>', html)
        self.assertIn("Answering unlocks: Description formatting", html)
        self.assertIn('data-discussion-owner="list-owner"', html)
        self.assertIn('data-requires-human="true"', html)
        self.assertIn("You need to answer this yourself in the linked conversation.", html)
        self.assertIn('data-copy-id="Q-gate"', html)

    def test_decision_route_validation_and_legacy_coordinator_fallback(self):
        self.data["tasks"][4]["work"]["state"] = "waiting"
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
        self.data.update(tasks=[], decisions=[], evidence=[], history=[], approvals=[], follow_ups=[])
        self.assertIn("No items are assigned yet.", render(self.data))
        with tempfile.TemporaryDirectory() as directory:
            status, output = Path(directory) / "status.json", Path(directory) / "dashboard.html"
            output.write_text("previous useful dashboard")
            self.data["schema_version"] = 99
            status.write_text(json.dumps(self.data))
            result = subprocess.run([sys.executable, str(DASHBOARD / "scripts" / "render_dashboard.py"), str(status), str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("unsupported dashboard schema_version", result.stderr)
            self.assertEqual(output.read_text(), "previous useful dashboard")

    def test_unknown_top_level_fields_are_rejected_by_name(self):
        self.data["feedback_coordination"] = {}
        with self.assertRaisesRegex(ValueError, "unknown top-level field feedback_coordination"):
            render(self.data)

    def test_schema_1_records_render_with_extra_fields_and_no_runtime(self):
        self.data["schema_version"] = 1
        self.data.pop("approvals")
        self.data["extra_notes"] = "legacy field"
        for task in self.data["tasks"]:
            task.pop("runtime")
        self.assertIn("Orchestration preview", render(self.data))

    def test_retention_past_its_date_is_called_out_for_cleanup(self):
        html = render(self.data)
        self.assertNotIn("past its cleanup date", html)
        self.assertIn("Kept until 2026-10-15T12:00:00-05:00", html)
        runtime = self.data["tasks"][6]["runtime"][0]
        runtime["until"] = "2026-10-08T12:00:00-05:00"
        html = render(self.data)
        self.assertIn('href="#runtime">1 kept resource is past its cleanup date', html)
        self.assertIn("Cleanup overdue since 2026-10-08T12:00:00-05:00", html)
        del runtime["reason"]
        with self.assertRaisesRegex(ValueError, "runtime.rollback-db.reason"):
            render(self.data)
        runtime["reason"] = "Rollback copy"
        del runtime["until"]
        with self.assertRaisesRegex(ValueError, "runtime.rollback-db.until needs an ISO 8601 timestamp"):
            render(self.data)

    def test_implemented_but_unsubmitted_delivery_is_labelled(self):
        page = render(self.data)
        row = "".join(Page(page).row_text["row-UI-101"])
        self.assertIn("Done, not submitted", row)
        self.assertNotIn("Done, not submitted", "".join(Page(page).row_text["row-SHIP-107"]))
        self.assertIn("2 done (1 not submitted)", page)

    def test_follow_ups_link_their_source_task_and_unowned_ones_are_called_out(self):
        page = render(self.data)
        self.assertIn('href="#follow-ups">1 follow-up needs an owner', page)
        self.assertIn("Owned by OPS-112", page)
        self.data["follow_ups"][1]["from_task"] = "NOPE-1"
        with self.assertRaisesRegex(ValueError, "F2: follow-up needs the assigned task"):
            render(self.data)

    def test_lifecycle_rules_are_not_enforced_here(self):
        """An expired approval, idle scans and an open closed run are the producer's rules; the page still draws them."""
        self.data["approvals"][1]["state"] = "active"
        self.data["monitoring"]["unchanged_scans"] = 9
        self.data["closed_at"] = "2026-10-08T15:00:00-05:00"
        self.data["skill_version"] = "0123abcd4567"
        html = render(self.data)
        self.assertIn("<b>A2</b> Active", html)
        self.assertIn("This run closed at 2026-10-08T15:00:00-05:00", html)
        self.assertNotIn("The coordinator migrates it", html)

    def test_contract_version_is_printed_and_stamped_on_the_page(self):
        self.assertIn(f"<!-- dashboard contract {CONTRACT_VERSION} -->", render(self.data))
        result = subprocess.run([sys.executable, "-B", str(DASHBOARD / "scripts" / "render_dashboard.py"), "--contract-version"],
                                capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), CONTRACT_VERSION)

    def test_minimal_status_renders(self):
        """A producer that is not an orchestration run writes only the required fields and still gets a page."""
        minimal = {
            "schema_version": 2, "run_id": "thread-42", "title": "Child threads of T-42", "presentation": {},
            "tasks": [
                {"id": "T-42-1", "title": "Index last week's meetings",
                 "owner": {"id": "thread-42-1", "label": "Meeting index thread", "state": "active",
                           "activity": "Reading the fourth of nine recordings."}},
                {"id": "T-42-2", "title": "Draft the release brief",
                 "owner": {"id": "thread-42-2", "label": "Release brief thread", "state": "waiting"},
                 "work": {"state": "waiting", "summary": "Waiting for the meeting index to finish.",
                          "reason": "The brief cites the index."}},
                {"id": "T-42-3", "title": "Check the deploy",
                 "owner": {"id": "thread-42-3", "label": "Deploy check thread", "state": "complete"},
                 "work": {"state": "delivered", "summary": "The deploy is healthy.", "reason": "Health page returned green."}},
            ],
        }
        html = render(minimal)
        page = Page(html)
        self.assertEqual(sorted(page.rows), ["row-T-42-1", "row-T-42-2", "row-T-42-3"])
        self.assertEqual(page.groups, {"group-attention": ["row-T-42-2"], "group-moving": ["row-T-42-1"], "group-resolved": ["row-T-42-3"]})
        self.assertIn("No stages requested", page.row_text["row-T-42-1"])
        self.assertIn("Reading the fourth of nine recordings.", html)
        self.assertIn("Snapshot time not recorded", html)
        self.assertIn('<b>1 of 3</b> items wrapped up', html)
        self.assertIn("This page is a snapshot.", html)
        with tempfile.TemporaryDirectory() as directory:
            status, output = Path(directory) / "status.json", Path(directory) / "dashboard.html"
            status.write_text(json.dumps(minimal))
            result = subprocess.run([sys.executable, "-B", str(DASHBOARD / "scripts" / "render_dashboard.py"), str(status), str(output)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.read_text().startswith("<!doctype html>"))
        minimal["tasks"][0]["owner"]["state"] = "running"
        with self.assertRaisesRegex(ValueError, "T-42-1: invalid owner state"):
            render(minimal)


class ServedPageTests(unittest.TestCase):
    def test_served_page_check_compares_bytes_without_a_browser(self):
        import http.server, threading, functools
        with tempfile.TemporaryDirectory() as directory:
            page = Path(directory) / "index.html"
            page.write_text(render(json.loads(PREVIEW.read_text())))
            handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
            handler.log_message = lambda *args: None
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/index.html"
                command = [sys.executable, str(DASHBOARD / "scripts" / "check_served.py"), str(page)]
                self.assertIn("PASS", subprocess.run(command + [url], capture_output=True, text=True).stdout)
                local = Path(directory) / "local.html"
                local.write_text("newer render")
                result = subprocess.run([command[0], command[1], str(local), url], capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                result = subprocess.run(command + [url.replace("index", "missing")], capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertIn("LIMITED", result.stderr)
            finally:
                server.shutdown()


if __name__ == "__main__":
    unittest.main()
