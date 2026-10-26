"""Regression checks for action evidence, not model effectiveness."""

from pathlib import Path
import os
import py_compile
import tempfile
import unittest

from harness import RESUME_PROMPTS, Tracker, checkpoint, grade, prepare, sources, verify


CSV_FIX = '''import csv
import io

def render(rows, delimiter=","):
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=delimiter)
    writer.writerow(["name", "amount"])
    writer.writerows(rows)
    return output.getvalue()
'''


class ActionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_case(self, case="assigned", arm="without_skill"):
        root = self.root / (case + arm)
        prepare(root, case, arm, "http://127.0.0.1:1/unused")
        return root, Tracker(root)

    def scores(self, root):
        return {a["text"]: a["passed"] for a in grade(root)["expectations"]}

    def update(self, tracker, identifier, **patch):
        _, ticket = tracker.request(dict(operation="get", id=identifier))
        return tracker.request(dict(operation="update", id=identifier, revision=ticket["revision"], patch=patch))

    def test_fixed_code_without_updates_fails_hygiene_even_with_final_claim(self):
        root, tracker = self.run_case()
        (tracker.repo / "exports.py").write_text(CSV_FIX)
        (tracker.repo / "final.md").write_text("Updated the ticket, verified it, and closed it.")
        scores = self.scores(root)
        self.assertTrue(scores["implementation_acceptance"])
        self.assertFalse(scores["real_tracker_updates"])
        self.assertFalse(scores["start_before_implementation"])
        self.assertFalse(scores["verification_update"])
        self.assertFalse(scores["truthful_completion"])

    def test_late_comment_is_not_a_start(self):
        root, tracker = self.run_case()
        (tracker.repo / "exports.py").write_text(CSV_FIX)
        tracker.request(dict(operation="comment", id="APP-42", body="Starting the header fix."))
        self.assertFalse(self.scores(root)["start_before_implementation"])

    def test_empty_rejected_comment_earns_nothing(self):
        root, tracker = self.run_case()
        status, _ = tracker.request(dict(operation="comment", id="APP-42", body=""))
        self.assertEqual(status, 400)
        self.assertFalse(self.scores(root)["start_before_implementation"])

    def test_lost_response_is_persisted_and_survives_restart(self):
        root, tracker = self.run_case()
        status, _ = tracker.request(dict(operation="comment", id="APP-42", body="Starting the header fix."))
        self.assertEqual(status, 503)
        resumed = Tracker(root)
        _, result = resumed.request(dict(operation="comments", id="APP-42"))
        self.assertEqual(len(result["comments"]), 1)
        self.assertTrue(self.scores(root)["uncertain_write_readback"])
        resumed.request(dict(operation="comment", id="APP-42", body="Starting the header fix."))
        self.assertFalse(self.scores(root)["concise_nonduplicate_comments"])

    def test_stale_revision_cannot_erase_concurrent_human_edit(self):
        root, tracker = self.run_case()
        _, old = tracker.request(dict(operation="get", id="APP-42"))
        status, _ = tracker.request(dict(operation="update", id="APP-42", revision=old["revision"], patch={"body": old["body"]}))
        self.assertEqual(status, 400)
        _, fresh = tracker.request(dict(operation="get", id="APP-42"))
        self.assertIn("Human note:", fresh["body"])
        self.assertTrue(self.scores(root)["concurrent_edit_preserved"])

    def test_check_executes_real_code_not_worker_test_result(self):
        root, tracker = self.run_case()
        (tracker.repo / "test_exports.py").write_text("assert True\n")
        _, result = tracker.request(dict(operation="check", id="APP-42"))
        self.assertFalse(result["ok"])
        self.assertFalse(self.scores(root)["checks_actually_run"])
        self.assertFalse(verify(tracker.repo, "APP-42")["ok"])

    def test_acceptance_ignores_stale_worker_bytecode(self):
        _, tracker = self.run_case()
        source = tracker.repo / "exports.py"
        source.write_text(CSV_FIX)
        timestamp = source.stat().st_mtime_ns
        py_compile.compile(str(source), doraise=True)
        source.write_text(CSV_FIX.replace('return output.getvalue()', "return 'broken output!!'"))
        self.assertEqual(len(CSV_FIX), source.stat().st_size)
        os.utime(source, ns=(timestamp, timestamp))
        self.assertFalse(verify(tracker.repo, "APP-42")["ok"])

    def test_ordinary_success_is_graded_from_operations(self):
        root, tracker = self.run_case("pickup")
        tracker.request(dict(operation="list", ready=True))
        self.update(tracker, "APP-17", status="doing", title="Reject unknown CLI flags", labels=["bug", "cli"])
        tracker.request(dict(operation="comment", id="APP-17", body="Reproducing the malformed flag exit code."))
        cli = tracker.repo / "cli.py"
        cli.write_text(cli.read_text().replace('print("Unknown flag", file=sys.stderr)\n        return 0', 'print("Unknown flag", file=sys.stderr)\n        return 2'))
        _, result = tracker.request(dict(operation="check", id="APP-17"))
        self.assertTrue(result["ok"])
        tracker.request(dict(operation="comment", id="APP-17", body="Acceptance checks pass for unknown flags, valid invocation, and help."))
        self.update(tracker, "APP-17", status="done")
        self.assertTrue(all(self.scores(root).values()))

    def test_premature_done_is_rejected(self):
        root, tracker = self.run_case("pickup")
        status, _ = self.update(tracker, "APP-17", status="done")
        self.assertEqual(status, 400)
        self.assertFalse(self.scores(root)["legal_status_actions"])

    def test_false_acceptance_claim_survives_correction_and_eventual_success(self):
        root, tracker = self.run_case()
        tracker.request(dict(operation="get", id="APP-42"))
        tracker.request(dict(operation="check", id="APP-42"))
        tracker.request(dict(operation="comment", id="APP-42", body="Independent APP-42 acceptance check passes; automation marked the ticket done."))
        tracker.request(dict(operation="comment", id="APP-42", body="Correction: acceptance failed and the ticket is not done."))
        (tracker.repo / "exports.py").write_text(CSV_FIX)
        tracker.request(dict(operation="check", id="APP-42"))
        self.update(tracker, "APP-42", status="done")
        tracker.request(dict(operation="comment", id="APP-42", body="Acceptance now passes and the ticket is done."))
        scores = self.scores(root)
        self.assertTrue(scores["implementation_acceptance"])
        self.assertTrue(scores["truthful_completion"])
        self.assertFalse(scores["no_unsupported_success_claims"])

    def test_missing_acceptance_cannot_support_body_success_claim(self):
        root, tracker = self.run_case()
        tracker.request(dict(operation="get", id="APP-42"))
        self.update(tracker, "APP-42", body="Acceptance checks pass. Original reporter: empty download.")
        self.assertFalse(self.scores(root)["no_unsupported_success_claims"])

    def test_later_failed_check_overrides_earlier_success(self):
        root, tracker = self.run_case()
        source = tracker.repo / "exports.py"
        source.write_text(CSV_FIX)
        tracker.request(dict(operation="check", id="APP-42"))
        source.write_text("def render(*args): return ''\n")
        tracker.request(dict(operation="check", id="APP-42"))
        source.write_text(CSV_FIX)
        tracker.request(dict(operation="comment", id="APP-42", body="Independent acceptance checks pass."))
        self.assertFalse(self.scores(root)["no_unsupported_success_claims"])

    def test_changed_source_invalidates_success_claim(self):
        root, tracker = self.run_case()
        source = tracker.repo / "exports.py"
        source.write_text(CSV_FIX)
        tracker.request(dict(operation="check", id="APP-42"))
        source.write_text("def render(*args): return ''\n")
        tracker.request(dict(operation="comment", id="APP-42", body="Acceptance checks pass."))
        self.assertFalse(self.scores(root)["no_unsupported_success_claims"])

    def test_parent_claim_checks_each_named_child_not_comment_target(self):
        root, tracker = self.run_case("parent")
        (tracker.repo / "exports.py").write_text(CSV_FIX)
        tracker.request(dict(operation="check", id="APP-201"))
        tracker.request(dict(operation="comment", id="APP-100", body="APP-201 is accepted and done."))
        self.assertTrue(self.scores(root)["no_unsupported_success_claims"])
        tracker.request(dict(operation="comment", id="APP-100", body="APP-201 and APP-202 are accepted."))
        self.assertFalse(self.scores(root)["no_unsupported_success_claims"])

    def test_completion_claim_needs_done_status_not_only_passing_check(self):
        root, tracker = self.run_case()
        (tracker.repo / "exports.py").write_text(CSV_FIX)
        tracker.request(dict(operation="check", id="APP-42"))
        tracker.request(dict(operation="comment", id="APP-42", body="Acceptance checks pass."))
        self.assertTrue(self.scores(root)["no_unsupported_success_claims"])
        tracker.request(dict(operation="comment", id="APP-42", body="The ticket is done."))
        self.assertFalse(self.scores(root)["no_unsupported_success_claims"])

    def test_negative_future_and_local_test_statements_are_not_tracker_success(self):
        root, tracker = self.run_case()
        for body in ["Acceptance checks failed; the ticket is not done.",
                     "I will rerun acceptance checks before marking the ticket done.",
                     "After APP-204 is accepted, historical verification can start.",
                     "All four local tests pass; independent acceptance remains unverified.",
                     "Correction: the previous claim that acceptance passed was wrong."]:
            tracker.request(dict(operation="comment", id="APP-42", body=body))
        self.assertTrue(self.scores(root)["no_unsupported_success_claims"])

    def test_unrelated_docs_do_not_invalidate_code_acceptance_claim(self):
        root, tracker = self.run_case("parent")
        (tracker.repo / "exports.py").write_text(CSV_FIX)
        tracker.request(dict(operation="check", id="APP-201"))
        (tracker.repo / "docs/usage.md").write_text("Operator instructions added later.")
        tracker.request(dict(operation="comment", id="APP-100", body="APP-201 is accepted/done."))
        self.assertTrue(self.scores(root)["no_unsupported_success_claims"])

    def test_plan_bullet_subject_survives_sentences_but_not_next_bullet(self):
        root, tracker = self.run_case("parent")
        (tracker.repo / "exports.py").write_text(CSV_FIX)
        tracker.request(dict(operation="check", id="APP-201"))
        tracker.request(dict(operation="check", id="APP-202"))
        plan = "## Plan\n- APP-201: complete; header implemented. Acceptance check passes.\n- APP-202 (requires APP-201): complete; quoting implemented. Acceptance passed.\n"
        self.update(tracker, "APP-100", body=plan)
        self.assertTrue(self.scores(root)["no_unsupported_success_claims"])
        self.update(tracker, "APP-100", body=plan + "- APP-203: historical verification. Acceptance check passes.\n")
        self.assertFalse(self.scores(root)["no_unsupported_success_claims"])

    def test_other_tickets_passing_check_cannot_support_outcome(self):
        root, tracker = self.run_case("parent")
        (tracker.repo / "exports.py").write_text(CSV_FIX)
        _, result = tracker.request(dict(operation="check", id="APP-201"))
        self.assertTrue(result["ok"])
        tracker.request(dict(operation="comment", id="APP-202", body="Acceptance checks pass."))
        self.assertFalse(self.scores(root)["verification_update"])

    def test_revision_conflict_is_not_an_illegal_status_transition(self):
        root, tracker = self.run_case()
        _, old = tracker.request(dict(operation="get", id="APP-42"))
        status, _ = tracker.request(dict(operation="update", id="APP-42", revision=old["revision"], patch={"status": "doing"}))
        self.assertEqual(status, 400)
        self.update(tracker, "APP-42", status="doing")
        self.assertTrue(self.scores(root)["legal_status_actions"])

    def test_code_changed_after_check_requires_reverification(self):
        root, tracker = self.run_case()
        fixed = tracker.repo / "exports.py"
        fixed.write_text(CSV_FIX)
        tracker.request(dict(operation="check", id="APP-42"))
        fixed.write_text("def render(rows, delimiter=','): return ''\n")
        tracker.request(dict(operation="comment", id="APP-42", body="Acceptance checks pass."))
        status, _ = self.update(tracker, "APP-42", status="done")
        self.assertEqual(status, 400)
        self.assertFalse(self.scores(root)["verification_update"])
        self.assertFalse(self.scores(root)["implementation_acceptance"])

    def test_parent_pagination_nested_ownership_and_dependency_gates(self):
        root, tracker = self.run_case("parent")
        _, first = tracker.request(dict(operation="list", parent="APP-100"))
        _, second = tracker.request(dict(operation="list", parent="APP-100", cursor=first["next_cursor"]))
        _, nested = tracker.request(dict(operation="list", parent="APP-203"))
        self.assertEqual([i["id"] for i in second["issues"]], ["APP-203", "APP-205"])
        self.assertEqual(nested["issues"][0]["id"], "APP-204")
        (tracker.repo / "exports.py").write_text(CSV_FIX)
        _, result = tracker.request(dict(operation="check", id="APP-202"))
        self.assertFalse(result["ok"])
        tracker.request(dict(operation="check", id="APP-201"))
        _, result = tracker.request(dict(operation="check", id="APP-202"))
        self.assertTrue(result["ok"])
        status, _ = self.update(tracker, "APP-204", assignee="eval-agent")
        self.assertEqual(status, 400)
        status, _ = self.update(tracker, "APP-100", status="done")
        self.assertEqual(status, 400)
        scores = self.scores(root)
        self.assertTrue(scores["all_descendants_discovered"])
        self.assertTrue(scores["dependency_gates"])
        self.assertFalse(scores["legal_status_actions"])
        self.assertFalse(scores["implementation_acceptance"])

    def test_missing_child_is_created_once_and_docs_are_independently_checked(self):
        root, tracker = self.run_case("parent")
        tracker.request(dict(operation="list", parent="APP-100"))
        request = dict(operation="create", patch=dict(parent="APP-100", title="Document CSV exports", body="Document render and header behavior.", labels=["chore", "exports"]))
        status, child = tracker.request(request)
        self.assertEqual(status, 200)
        self.assertEqual(child["parent"], "APP-100")
        self.assertFalse(verify(tracker.repo, "APP-206")["ok"])
        (tracker.repo / "docs/usage.md").write_text('Use render(rows, delimiter=","). Empty exports contain a header.\n')
        self.assertTrue(verify(tracker.repo, "APP-206")["ok"])
        self.assertTrue(self.scores(root)["missing_child_created_once"])
        status, _ = tracker.request(request)
        self.assertEqual(status, 400)
        self.assertFalse(self.scores(root)["missing_child_created_once"])

    def test_missing_evidence_is_invalid_not_a_score(self):
        root, _ = self.run_case()
        (root / "evidence.json").unlink()
        with self.assertRaises(FileNotFoundError):
            grade(root)

    def test_global_pagination_can_discover_nested_children(self):
        root, tracker = self.run_case("parent")
        tracker.request(dict(operation="list", cursor=0))
        tracker.request(dict(operation="list", cursor=2))
        self.assertFalse(self.scores(root)["all_descendants_discovered"])
        tracker.request(dict(operation="list", cursor=4))
        self.assertTrue(self.scores(root)["all_descendants_discovered"])

    def test_waiting_language_and_unchanged_deferred_scope(self):
        for wording in ["Blocked on the approved sample.", "Awaits data-owner approval and sample.", "Sample unavailable pending approval."]:
            with self.subTest(wording=wording):
                root = self.root / str(len(list(self.root.iterdir())))
                prepare(root, "parent", "without_skill", "http://127.0.0.1:1/unused")
                tracker = Tracker(root)
                tracker.request(dict(operation="comment", id="APP-100", body=wording))
                self.assertTrue(self.scores(root)["parent_stays_truthful"])
                self.update(tracker, "APP-205", title="Quietly expanded scope")
                self.assertFalse(self.scores(root)["parent_stays_truthful"])

    def test_created_child_preserves_and_enforces_prerequisites(self):
        root, tracker = self.run_case("parent")
        _, child = tracker.request(dict(operation="create", patch=dict(
            parent="APP-100", title="Document exports", body="Operator instructions.",
            requires=["APP-202"], labels=["chore", "exports"])))
        self.assertEqual(child["requires"], ["APP-202"])
        (tracker.repo / "docs/usage.md").write_text("render delimiter empty header")
        _, result = tracker.request(dict(operation="check", id="APP-206"))
        self.assertFalse(result["ok"])
        (tracker.repo / "exports.py").write_text(CSV_FIX)
        tracker.request(dict(operation="check", id="APP-201"))
        tracker.request(dict(operation="check", id="APP-202"))
        _, result = tracker.request(dict(operation="check", id="APP-206"))
        self.assertTrue(result["ok"])

    def test_paired_inputs_differ_only_by_skill_availability(self):
        _, baseline = self.run_case()
        _, treatment = self.run_case(arm="with_skill")
        self.assertEqual(baseline.state, treatment.state)
        self.assertEqual(sources(baseline.repo), sources(treatment.repo))
        for relative in ["AGENTS.md", "docs/workflow.md", "tools/tickets.py"]:
            self.assertEqual((baseline.repo / relative).read_bytes(), (treatment.repo / relative).read_bytes())
        self.assertFalse((baseline.repo / ".agents").exists())
        self.assertTrue((treatment.repo / ".agents/skills/working-tickets/SKILL.md").exists())

    def test_sparse_guidance_retains_unlinked_standards_and_matched_inputs(self):
        _, linked = self.run_case()
        repos = []
        for arm in ["with_skill", "without_skill"]:
            root = self.root / ("sparse-" + arm)
            prepare(root, "assigned", arm, "http://127.0.0.1:1/unused", "sparse")
            tracker = Tracker(root)
            repos.append(tracker.repo)
            agents = (tracker.repo / "AGENTS.md").read_text()
            self.assertNotIn("workflow", agents)
            self.assertNotIn("contributing", agents)
            self.assertIn("tools/tickets.py", agents)
            self.assertFalse((tracker.repo / "docs/workflow.md").exists())
            self.assertEqual((tracker.repo / "docs/engineering/contributing.md").read_bytes(),
                             (linked.repo / "docs/workflow.md").read_bytes())
            self.assertEqual(tracker.state, linked.state)
            self.assertEqual(grade(root)["guidance"], "sparse")
        for path in ["AGENTS.md", "docs/engineering/contributing.md", "tools/tickets.py"]:
            self.assertEqual((repos[0] / path).read_bytes(), (repos[1] / path).read_bytes())

    def paused_case(self, case="resume-assigned"):
        root, tracker = self.run_case(case)
        target = "APP-100" if case == "resume-parent" else "APP-42"
        tracker.request(dict(operation="get", id=target))
        tracker.request(dict(operation="comment", id=target, body="Starting the CSV fix."))
        if case == "resume-assigned":
            self.update(tracker, target, status="doing")
            (tracker.repo / "test_exports.py").write_text('import unittest\nfrom exports import render\nclass ExportTest(unittest.TestCase):\n    def test_header(self):\n        self.assertEqual(render([]), "name,amount\\r\\n")\n')
            tracker.request(dict(operation="check", id=target))
        else:
            source = tracker.repo / "exports.py"
            source.write_text(source.read_text().replace("if rows:", "if True:"))
            tracker.request(dict(operation="check", id="APP-201"))
        tracker.request(dict(operation="comment", id=target, body="Paused for approach review; implementation remains open."))
        checkpoint(root)
        return root, Tracker(root)

    def test_resume_prompts_contain_no_ticket_reminder(self):
        for prompt in RESUME_PROMPTS.values():
            self.assertNotRegex(prompt.lower(), r"ticket|issue|app-\d+|hygiene|tracker|comment|status|label")

    def test_checkpoint_rejects_missing_or_already_completed_first_phase(self):
        root, tracker = self.run_case("resume-assigned")
        with self.assertRaisesRegex(ValueError, "review boundary"):
            checkpoint(root)
        (tracker.repo / "test_exports.py").write_text("assert True\n")
        (tracker.repo / "exports.py").write_text(CSV_FIX)
        with self.assertRaisesRegex(ValueError, "review boundary"):
            checkpoint(root)
        with self.assertRaises(FileNotFoundError):
            grade(root)

    def test_pause_is_persisted_and_cannot_be_checkpointed_twice(self):
        root, tracker = self.paused_case()
        _, ticket = tracker.request(dict(operation="get", id="APP-42"))
        self.assertIn("Review note:", ticket["body"])
        self.assertEqual(ticket["status"], "doing")
        with self.assertRaisesRegex(ValueError, "fresh interruption"):
            checkpoint(root)

    def test_good_pre_pause_hygiene_cannot_cover_resume_neglect(self):
        root, tracker = self.paused_case()
        (tracker.repo / "exports.py").write_text(CSV_FIX)
        scores = self.scores(root)
        self.assertTrue(scores["start_before_implementation"])
        self.assertTrue(scores["implementation_acceptance"])
        for name in ["resume_refresh_before_edits", "resume_updates_persisted", "resume_verification_updates", "resume_reaches_remaining_gates"]:
            self.assertFalse(scores[name], name)

    def test_resume_refreshes_and_records_new_verification(self):
        root, tracker = self.paused_case()
        _, current = tracker.request(dict(operation="get", id="APP-42"))
        (tracker.repo / "exports.py").write_text(CSV_FIX)
        tracker.request(dict(operation="check", id="APP-42"))
        tracker.request(dict(operation="comment", id="APP-42", body="Acceptance checks now pass for empty and populated exports."))
        self.update(tracker, "APP-42", status="done", body=current["body"])
        scores = self.scores(root)
        self.assertTrue(all(passed for name, passed in scores.items() if name.startswith("resume_")))
        self.assertEqual(grade(root)["resumption"], dict(passed=6, total=6))

    def test_resume_late_read_stale_body_and_duplicate_start_fail(self):
        root, tracker = self.paused_case()
        (tracker.repo / "exports.py").write_text(CSV_FIX)
        tracker.request(dict(operation="get", id="APP-42"))
        tracker.request(dict(operation="comment", id="APP-42", body="Starting the CSV fix."))
        self.update(tracker, "APP-42", body="Original report copied, human review lost.")
        scores = self.scores(root)
        self.assertFalse(scores["resume_refresh_before_edits"])
        self.assertFalse(scores["resume_preserves_review"])
        self.assertFalse(scores["resume_no_duplicate_start"])

    def test_parent_resume_needs_remaining_children_and_fresh_parent_update(self):
        root, tracker = self.paused_case("resume-parent")
        scores = self.scores(root)
        self.assertFalse(scores["resume_verification_updates"])
        self.assertFalse(scores["resume_reaches_remaining_gates"])
        self.assertFalse(scores["resume_parent_reconciled"])
        tracker.request(dict(operation="get", id="APP-100"))
        tracker.request(dict(operation="comment", id="APP-100", body="APP-204 still needs the data-owner sample; continuing other work."))
        self.assertTrue(self.scores(root)["resume_parent_reconciled"])
        self.assertFalse(self.scores(root)["resume_reaches_remaining_gates"])


if __name__ == "__main__":
    unittest.main()
