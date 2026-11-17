import contextlib
import importlib.util
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

SCRIPT = Path(__file__).parents[1] / "scripts" / "gh_ci_baseline.py"
spec = importlib.util.spec_from_file_location("gh_ci_baseline", SCRIPT)
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


def at(seconds):
    return f"2026-10-09T00:{seconds // 60:02d}:{seconds % 60:02d}Z"


def job(identifier, name, start, end, conclusion="success", labels=None, created=20):
    return {"id": identifier, "name": name, "status": "completed",
            "created_at": at(created), "started_at": at(start), "completed_at": at(end),
            "conclusion": conclusion, "labels": labels or ["ubuntu-latest"], "steps": []}


class Evidence:
    def __init__(self, attempts, starts):
        self.attempts = attempts
        self.starts = starts
        self.workflows = [{"id": 7, "path": ".github/workflows/ci.yml", "name": "CI", "state": "active"}]
        self.blob = "same"
        self.job_error_page = None
        self.classic = (True, {"contexts": [], "strict": False})

    def gh(self, *args):
        if args[:2] == ("repo", "view"):
            return True, {"visibility": "PRIVATE", "defaultBranchRef": {"name": "main"}}
        return True, [{"databaseId": 1, "event": "push", "headBranch": "main",
                       "headSha": "head", "status": "completed", "conclusion": "success",
                       "createdAt": at(0), "startedAt": at(20), "attempt": len(self.attempts)}]

    def api(self, path):
        url = urlsplit(path)
        page = int(parse_qs(url.query).get("page", ["1"])[0])
        if url.path.endswith("/workflows"):
            return True, {"total_count": len(self.workflows), "workflows": self.workflows[(page - 1) * 100:page * 100]}
        if "/contents/" in url.path:
            return (True, {"sha": self.blob}) if self.blob else (False, "Not Found")
        if "/attempts/" in url.path:
            attempt = int(url.path.split("/attempts/")[1].split("/")[0])
            if url.path.endswith("/jobs"):
                if page == self.job_error_page:
                    return False, "temporary API error"
                jobs = self.attempts[attempt - 1]
                return True, {"total_count": len(jobs), "jobs": jobs[(page - 1) * 100:page * 100]}
            start = self.starts[attempt - 1]
            return (True, {"run_started_at": at(start)}) if start is not None else (False, "Not Found")
        if "/rules/" in url.path:
            return True, [{"type": "required_status_checks", "parameters": {
                "required_status_checks": [{"context": "verify"}], "strict_required_status_checks_policy": True}}]
        if url.path.endswith("/required_status_checks"):
            return self.classic
        raise AssertionError(f"unexpected evidence read: {path}")


class CliMeasurements(unittest.TestCase):
    def invoke(self, evidence, json_output=True):
        output = io.StringIO()
        argv = [str(SCRIPT), "--repo", "example/repo", "--workflow", "ci.yml"]
        with patch.object(baseline, "gh", side_effect=evidence.gh), \
             patch.object(baseline, "api", side_effect=evidence.api), \
             patch("sys.argv", argv + (["--json"] if json_output else [])), \
             contextlib.redirect_stdout(output):
            self.assertEqual(baseline.main(), 0)
        return json.loads(output.getvalue()) if json_output else output.getvalue()

    def test_retry_clocks_and_all_attempt_consumption(self):
        evidence = Evidence([
            [job(1, "verify", 25, 85, "failure")],
            [job(2, "verify", 320, 450, created=300),
             job(3, "db-probe", 330, 390, labels=["self-hosted"], created=300),
             job(4, "deploy", 450, 450, "skipped", created=300)],
        ], [20, 300])
        run = self.invoke(evidence)["runs"][0]
        measurement = run["measure"]
        self.assertTrue(run["measurement_complete"])
        self.assertEqual({key: measurement[key] for key in (
            "elapsed", "attempt_elapsed", "initial_delay", "latest_attempt_delay",
            "runner_time", "attempt_runner_time", "rounded_minutes", "queue")}, {
                "elapsed": 450, "attempt_elapsed": 150, "initial_delay": 20,
                "latest_attempt_delay": 300, "runner_time": 250,
                "attempt_runner_time": 190, "rounded_minutes": 4, "queue": 30})
        self.assertEqual([row["name"] for row in measurement["jobs"]], ["verify", "db-probe"])
        self.assertEqual(measurement["skipped"], ["deploy"])
        report = self.invoke(evidence, False)
        self.assertIn("all-attempt runner time 4m 10s; rounded hosted minutes 4; coverage 1/1", report)
        self.assertIn("no comparable runs", report)

    def test_paginates_workflows_and_more_than_100_jobs(self):
        evidence = Evidence([[job(i, f"test-{i}", 30, 31) for i in range(101)]], [20])
        evidence.workflows = [{"id": i + 100, "path": f"other-{i}.yml", "name": f"other-{i}", "state": "active"}
                              for i in range(100)] + evidence.workflows
        data = self.invoke(evidence)
        self.assertEqual(data["workflow"]["id"], 7)
        self.assertEqual(data["runs"][0]["measure"]["runner_time"], 101)
        self.assertEqual(data["runs"][0]["measure"]["rounded_minutes"], 101)
        self.assertEqual(data["runs"][0]["measure"]["jobs"][-1]["name"], "test-100")

    def test_unknown_revisions_are_not_comparable(self):
        evidence = Evidence([[job(1, "verify", 30, 39)]], [20])
        evidence.blob = None
        run = self.invoke(evidence)["runs"][0]
        self.assertEqual(run["revision"], "unknown")
        self.assertEqual(run["measure"]["runner_time"], 9)
        report = self.invoke(evidence, False)
        self.assertIn("'unknown' workflow revisions cannot establish comparability", report)
        self.assertIn("no comparable runs", report)

    def test_partial_page_is_missing_evidence_not_zero_consumption(self):
        evidence = Evidence([[job(i, f"test-{i}", 30, 31) for i in range(101)]], [20])
        evidence.job_error_page = 2
        run = self.invoke(evidence)["runs"][0]
        self.assertFalse(run["measurement_complete"])
        self.assertIsNone(run["measure"])
        self.assertEqual(run["measurement_notes"], ["cannot read jobs page 2: temporary API error"])
        report = self.invoke(evidence, False)
        self.assertIn("coverage 0/1 completed runs", report)
        self.assertIn("incomplete job reads; excluded from baselines", report)

    def test_unreadable_attempt_clock_excludes_the_measurement(self):
        evidence = Evidence([[job(1, "verify", 30, 39)]], [None])
        run = self.invoke(evidence)["runs"][0]
        self.assertFalse(run["measurement_complete"])
        self.assertEqual(run["measurement_notes"], ["cannot read start of attempt 1"])
        self.assertIsNone(run["measure"])

    def test_rulesets_and_unknown_classic_access_are_distinct(self):
        evidence = Evidence([[job(1, "verify", 30, 39)]], [20])
        evidence.classic = (False, "HTTP 403")
        checks = self.invoke(evidence)["required_checks"]
        self.assertEqual(checks["rulesets"], ["verify"])
        self.assertIsNone(checks["classic"])
        self.assertTrue(checks["strict"])
        report = self.invoke(evidence, False)
        self.assertIn("observed on current revision", report)
        self.assertIn("classic   unknown", report)


class FleetEvidence:
    """Runs across workflows; jobs keyed by (run id, attempt). Attempt start
    clocks are unreadable, so a fleet total that depended on them would fail."""

    def __init__(self, runs, jobs, total=None):
        self.runs = runs
        self.jobs = jobs
        self.total = len(runs) if total is None else total
        self.job_errors = set()
        self.pages = None

    def gh(self, *args):
        if args[:2] == ("repo", "view"):
            return True, {"visibility": "PRIVATE", "defaultBranchRef": {"name": "main"}}
        raise AssertionError(f"unexpected gh call: {args}")

    def api(self, path):
        url = urlsplit(path)
        query = parse_qs(url.query)
        page = int(query.get("page", ["1"])[0])
        if url.path.endswith("/actions/runs"):
            assert query["created"][0].startswith(">="), query
            batch = self.pages[page - 1] if self.pages else self.runs[(page - 1) * 100:page * 100]
            return True, {"total_count": self.total, "workflow_runs": batch}
        if "/attempts/" in url.path and url.path.endswith("/jobs"):
            run_id = int(url.path.split("/runs/")[1].split("/")[0])
            attempt = int(url.path.split("/attempts/")[1].split("/")[0])
            if run_id in self.job_errors:
                return False, "temporary API error"
            jobs = self.jobs.get((run_id, attempt), [])
            return True, {"total_count": len(jobs), "jobs": jobs[(page - 1) * 100:page * 100]}
        if "/attempts/" in url.path:
            return False, "Not Found"
        raise AssertionError(f"unexpected evidence read: {path}")


def fleet_run(identifier, path, event, attempt=1, conclusion="success"):
    return {"id": identifier, "path": path, "name": path, "event": event,
            "run_attempt": attempt, "conclusion": conclusion, "status": "completed"}


class CliByWorkflow(unittest.TestCase):
    def invoke(self, evidence, extra=(), json_output=True):
        output = io.StringIO()
        argv = [str(SCRIPT), "--repo", "example/repo", "--by-workflow", *extra]
        with patch.object(baseline, "gh", side_effect=evidence.gh), \
             patch.object(baseline, "api", side_effect=evidence.api), \
             patch("sys.argv", argv + (["--json"] if json_output else [])), \
             contextlib.redirect_stdout(output):
            self.assertEqual(baseline.main(), 0)
        return json.loads(output.getvalue()) if json_output else output.getvalue()

    def test_totals_every_attempt_per_workflow_and_event(self):
        ci, codeql = ".github/workflows/ci.yml", ".github/workflows/codeql.yml"
        evidence = FleetEvidence(
            [fleet_run(11, ci, "pull_request", attempt=2), fleet_run(12, ci, "push"),
             fleet_run(13, ci, "pull_request", conclusion="failure"), fleet_run(14, codeql, "push")],
            {(11, 1): [job(1, "test", 0, 61, "failure")],
             (11, 2): [job(2, "test", 0, 61), job(3, "deploy", 61, 61, "skipped")],
             (12, 1): [job(4, "matrix", 0, 600), job(5, "probe", 0, 300, labels=["self-hosted"])],
             (13, 1): [job(6, "test", 0, 30, "failure")]})
        evidence.job_errors = {14}
        data = self.invoke(evidence)
        rows = [(g["workflow"], g["event"], g["runs"], g["measured_runs"], g["re_runs"], g["jobs"],
                 g["skipped_jobs"], g["runner_time"], g["rounded_minutes"]) for g in data["groups"]]
        self.assertEqual(rows, [
            (ci, "push", 1, 1, 0, 2, 0, 900, 10),
            (ci, "pull_request", 2, 2, 1, 3, 1, 152, 5),
            (codeql, "push", 1, 0, 0, 0, 0, 0, 0),
        ])
        self.assertEqual(data["groups"][1]["conclusions"], {"success": 1, "failure": 1})
        self.assertEqual([item["run"] for item in data["incomplete_runs"]], [14])
        report = self.invoke(evidence, json_output=False)
        self.assertIn("coverage: 4 of 4 runs read", report)
        self.assertNotIn("partial window", report)
        self.assertIn("1 run(s) have incomplete job reads; their consumption is missing, not zero", report)
        self.assertLess(report.index(f"{ci} / push"), report.index(f"{ci} / pull_request"))

    def test_capped_window_is_reported_as_partial(self):
        runs = [fleet_run(i, "ci.yml", "push") for i in range(1, 151)]
        evidence = FleetEvidence(runs, {}, total=2500)
        # A run created while paging pushes run 100 onto page 2 as well.
        evidence.pages = [runs[:100], runs[99:150]]
        data = self.invoke(evidence)
        self.assertEqual((data["runs_read"], data["runs_in_window"]), (150, 2500))
        self.assertEqual(data["groups"][0]["runs"], 150)
        capped = self.invoke(evidence, ["--limit", "40"])
        self.assertEqual(capped["runs_read"], 40)
        self.assertIn("partial window", self.invoke(evidence, json_output=False))

    def test_rejects_single_workflow_filters(self):
        with patch("sys.argv", [str(SCRIPT), "--by-workflow", "--workflow", "ci.yml"]), \
             contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            baseline.main()


if __name__ == "__main__":
    unittest.main()
