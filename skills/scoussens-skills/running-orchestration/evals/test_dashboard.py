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
SETUP = RUNNER.parent / "setting-up-orchestration"
sys.path.insert(0, str(RUNNER / "scripts"))
sys.path.insert(0, str(SETUP / "scripts"))
from check_config import check
from render_dashboard import render


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.ids = []
        self.rows = {}
        self.row = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
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

    def test_shared_owner_counts_once_and_cannot_be_partially_closed(self):
        first, second = self.data["tasks"][:2]
        first["owner"]["state"] = "active"
        second["owner"]["id"] = first["owner"]["id"]
        html = render(self.data)
        self.assertIn('<b>2</b><span>active owners</span>', html)
        second["owner"]["state"] = "closed"
        with self.assertRaisesRegex(ValueError, "conflicting lifecycle states"):
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
        self.config = json.loads((SETUP / "assets" / "harness-config.template.json").read_text())
        self.config["harness"] = {"id": "fixture", "name": "Fixture harness", "context": "Local test", "owner_term": "session", "helper_term": "bounded helper"}
        self.config["run_root"] = "/tmp/orchestration-fixture"
        self.config["limitations"] = ["No independently addressable owners available"]

    def test_json_roundtrip_retains_unsupported_capabilities_without_faking_owners(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(self.config))
            result = subprocess.run([sys.executable, str(SETUP / "scripts" / "check_config.py"), str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            stored = json.loads(path.read_text())
            self.assertIsNone(stored["owners"]["launch"])
            self.assertEqual(stored["harness"]["owner_term"], "session")
            self.assertEqual(stored["limitations"], ["No independently addressable owners available"])

    def test_shared_skills_exclude_both_orchestration_roles(self):
        self.config["skills"]["shared"] = ["speak-clearly"]
        check(self.config)
        for skill in ("running-orchestration", "setting-up-orchestration"):
            invalid = deepcopy(self.config)
            invalid["skills"]["shared"].append(skill)
            with self.assertRaisesRegex(ValueError, "coordinator"):
                check(invalid)

    def test_bad_version_path_and_helper_types_are_rejected(self):
        for section, key, value in ((None, "schema_version", 2), (None, "run_root", "relative/state"), ("helpers", "blocks_caller", "yes")):
            with self.subTest(key=key):
                invalid = deepcopy(self.config)
                target = invalid if section is None else invalid[section]
                target[key] = value
                with self.assertRaises(ValueError):
                    check(invalid)


if __name__ == "__main__":
    unittest.main()
