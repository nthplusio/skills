"""Owner decisions asked once across PRs, and answers that unblock every PR they gate."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ledger
from render_round import render
from decision_fixtures import assessment
from test_report import fixture

WORDS = "Accept ADRs 183, 185 and 186; record it and approve what that unblocks"


def adr_gated(number, *others, head="a" * 40, base="b" * 40):
    """A PR gated by the owner accepting ADR 183, plus any other decisions."""
    item = assessment(number, kind="decision", owner="Product owner", head=head, base=base)
    item["decisions"][0].update(id=f"adr-{number}", subject="adr:183", criterion="ADR 183 is accepted",
                                summary="Accept ADR 183, which this PR implements", recommend="accept",
                                unblock="Mark ADR 183 Accepted")
    item["decisions"] += others
    return item


def evidence_gap():
    gap = assessment(kind="evidence", owner="Operator")["decisions"][0]
    return {**gap, "id": "staging-run"}


class OwnerDecisionTests(unittest.TestCase):
    def setUp(self):
        state = tempfile.TemporaryDirectory()
        self.addCleanup(state.cleanup)
        for active in (patch.dict(os.environ, XDG_STATE_HOME=state.name),
                       patch.object(ledger, "repo_slug", return_value="owner/repo")):
            active.start()
            self.addCleanup(active.stop)
        self.files = state.name

    def cli(self, *argv):
        out = io.StringIO()
        with patch.object(sys, "argv", ["ledger.py", *argv]), contextlib.redirect_stdout(out):
            try:
                ledger.main()
            except SystemExit as stop:
                return out.getvalue() + str(stop.code or ""), stop.code
        return out.getvalue(), 0

    def save(self, *items):
        path = Path(self.files) / "assessments.json"
        path.write_text(json.dumps({"repository": "owner/repo", "assessments": list(items)}))
        rid, _ = self.cli("start", "main")
        self.assertEqual(self.cli("record", rid.strip(), str(path))[1], 0)
        return path

    def test_one_answer_clears_every_pr_it_gates_and_names_what_still_blocks(self):
        path = self.save(adr_gated(17), adr_gated(18, evidence_gap()))
        out, code = self.cli("decide", "adr:183", "--answer", "accept", "--instruction", WORDS,
                             "--assessments", str(path))
        self.assertEqual(code, 0, out)
        self.assertIn("#17 clear", out)
        self.assertIn("#18 still blocked: Operator: Run the live workflow and attach its result (18/staging-run)", out)
        self.assertNotIn("adr:183)", out)
        saved = ledger.assessments("owner/repo")
        self.assertEqual(ledger.unresolved(saved[17]), [])
        waiver = saved[17]["decisions"][0]["waiver"]
        self.assertEqual((waiver["source"], waiver["criterion"]), (WORDS, "ADR 183 is accepted"))
        # The round's file carries the answer too, so the write helpers see the same record.
        bundle = json.loads(path.read_text())
        self.assertEqual([len(ledger.unresolved(a)) for a in bundle["assessments"]], [0, 1])
        out, _ = self.cli("waiting", "--assessments", str(path))
        self.assertIn("18/staging-run · #18", out)
        self.assertNotIn("adr:183", out)

    def test_clear_names_the_head_its_saved_assessment_reviewed(self):
        # Live: "#3582 clear" while #3582's head had moved past its saved assessment.
        self.save(adr_gated(17))
        out, code = self.cli("decide", "adr:183", "--answer", "accept", "--instruction", WORDS)
        self.assertEqual(code, 0, out)
        self.assertIn("#17 clear at aaaaaaaaa: nothing unresolved in its saved assessment of that head", out)
        self.assertIn("if the PR's head has moved, review or carry it first", out)

    def test_history_keeps_the_earlier_assessment_beside_the_answered_one(self):
        self.save(adr_gated(17), adr_gated(18))
        self.cli("decide", "adr:183", "--answer", "waive", "--instruction", WORDS)
        history = [a for a in ledger.assessment_history("owner/repo") if a["number"] == 17]
        self.assertEqual(len(history), 2)
        self.assertNotIn("waiver", history[0]["decisions"][0])
        self.assertEqual(history[1]["decisions"][0]["waiver"]["source"], WORDS)
        self.assertEqual(history[0]["round"], history[1]["round"])

    def test_reject_records_the_answer_and_keeps_both_blocked(self):
        self.save(adr_gated(17), adr_gated(18))
        out, code = self.cli("decide", "adr:183", "--answer", "reject", "--instruction", "Do not accept ADR 183")
        self.assertEqual(code, 0, out)
        self.assertIn("#17 still blocked", out)
        self.assertIn("#18 still blocked", out)
        self.assertIn("rejected", out)
        saved = ledger.assessments("owner/repo")
        self.assertEqual(saved[17]["decisions"][0]["rejected"]["source"], "Do not accept ADR 183")
        self.assertEqual(len(ledger.unresolved(saved[18])), 1)
        # Answered, so it is not asked again.
        self.assertIn("Waiting on you: nothing", self.cli("waiting")[0])

    def test_an_owner_answer_cannot_waive_code_or_unfinished_review(self):
        code_gate = assessment(17, kind="code", owner="Author")
        code_gate["decisions"][0]["subject"] = "adr:183"
        self.save(adr_gated(18), code_gate)
        before = len(ledger.assessment_history("owner/repo"))
        out, code = self.cli("decide", "adr:183", "--answer", "waive", "--instruction", WORDS)
        self.assertNotEqual(code, 0)
        self.assertIn("code decision", out)
        self.assertEqual(len(ledger.assessment_history("owner/repo")), before)
        out, code = self.cli("decide", "17/criterion-1", "--answer", "accept", "--instruction", WORDS)
        self.assertNotEqual(code, 0)
        self.assertEqual(len(ledger.assessment_history("owner/repo")), before)

    def test_an_open_subject_decision_holds_approval_at_should_fix(self):
        # Live #3717: the INT-3042 owner's sign-off was should-fix, and decide printed the PR as clear.
        signoff = adr_gated(3717)
        signoff["decisions"][0].update(severity="should-fix", subject="ticket:INT-3042")
        evidence = assessment(3718, kind="evidence", owner="Operator")
        evidence["decisions"][0].update(id="screens", severity="should-fix", subject="ticket:INT-3042")
        path = self.save(signoff, evidence)
        out, code = self.cli("decide", "3718/screens", "--answer", "reject", "--instruction", "x")
        self.assertNotEqual(code, 0, out)  # the key is the subject, not the id
        out, _ = self.cli("waiting", "--assessments", str(path))
        self.assertIn("Waiting on you: 1 decision(s)", out)
        self.assertIn("ticket:INT-3042 · #3717, #3718", out)
        out, code = self.cli("decide", "ticket:INT-3042", "--answer", "reject", "--instruction", "Not signed off")
        self.assertIn("#3717 still blocked", out)
        self.assertNotIn("clear", out)

    def test_a_decision_another_person_answers_waits_on_someone_else(self):
        # Live #3717: the author's screenshots were listed under "Waiting on you".
        screenshots = assessment(3717, kind="evidence", owner="il-bilal (author)")
        screenshots["decisions"][0].update(id="screenshots", subject="evidence:3717-screenshots", owner_login="il-bilal")
        mine = adr_gated(3716)
        mine["decisions"][0]["owner_login"] = "reviewer"
        path = self.save(screenshots, mine)
        login = lambda command, **kwargs: subprocess.CompletedProcess(command, 0, "reviewer\n", "")
        with patch.object(subprocess, "run", side_effect=login):  # `gh api user`: the round's user
            out, _ = self.cli("waiting", "--assessments", str(path))
        yours, others = out.split("Waiting on someone else:")
        self.assertIn("Waiting on you: 1 decision(s)", yours)
        self.assertIn("adr:183 · #3716", yours)
        self.assertNotIn("3717", yours)
        self.assertIn("evidence:3717-screenshots · #3717 · il-bilal (author)", others)

    def test_the_report_asks_a_decision_shared_by_two_prs_once(self):
        records, proposals = [], []
        for number in (482, 483):
            _, record = fixture()
            record["number"] = number
            records.append(record)
            proposals.append(adr_gated(number, head=record["head"], base=record["base"]))
        page = render(records, "main", assessments={"repository": records[0]["repository"], "assessments": proposals})
        waiting = page.split('<section class="waiting">', 1)[1].split("</section>", 1)[0]
        self.assertIn("Waiting on you · 1 decision", waiting)
        self.assertEqual(waiting.count("<li"), 1)
        self.assertIn("<strong>adr:183</strong> · #482, #483", waiting)
        self.assertIn("Recommended: accept", waiting)


if __name__ == "__main__":
    unittest.main()
